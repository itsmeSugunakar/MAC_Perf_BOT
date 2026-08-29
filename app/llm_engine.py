"""
llm_engine.py — offline, on-device LLM subsystem (MLX) for performance-bot.

Optional. If `mlx-lm` isn't installed, LLM_AVAILABLE is False and every public
function degrades cleanly instead of raising — mirrors the onnx/onnxruntime
optional-dependency pattern already used by the CDA engine in
performance_gui.py.

Powers three features surfaced by the dashboard's Insights tab:
  - crash report explanations (on-demand)
  - daily/weekly narrative digests (schedule-driven, see performance_gui.py's
    tick-loop cooldown checks)
  - free-form "Ask" questions grounded in recent telemetry

Design constraints (CLAUDE.md §10 — "must not measurably degrade the system
it monitors"):
  - The model loads lazily on first actual generation call, never at import
    and never at BotEngine.__init__.
  - An idle-unload watchdog drops the model (and its ~2GB RSS) after
    LLM_IDLE_UNLOAD_S of no use.
  - All generation runs on a single serialized background worker thread —
    callers get a job_id immediately (submit_*) and poll get_job() for the
    result, so a slow generation never blocks the HTTP-serving thread.
"""

import gc
import json
import os
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from queue import Queue

try:
    from mlx_lm import load as _mlx_load, generate as _mlx_generate
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

# ─── Constants ──────────────────────────────────────────────────────────────
LLM_MODEL_REPO              = "mlx-community/Qwen2.5-3B-Instruct-4bit"
LLM_IDLE_UNLOAD_S           = 600     # unload model from RAM after 10 min of no generation calls
LLM_IDLE_CHECK_S            = 60      # watchdog poll interval for the idle-unload check
LLM_CRASH_PROMPT_MAX_CHARS  = 6000    # cap on .ips content fed into the crash-explain prompt
LLM_DIGEST_MAX_ROWS         = 200     # max hourly rows fed into a digest prompt (downsample above this)
LLM_DIGEST_PROMPT_MAX_CHARS = 8000    # hard cap on assembled digest prompt
LLM_ASK_PROMPT_MAX_CHARS    = 8000    # hard cap on assembled ask-panel context prompt
LLM_MAX_NEW_TOKENS_EXPLAIN  = 300     # generation length cap — crash explanation
LLM_MAX_NEW_TOKENS_DIGEST   = 400     # generation length cap — digest
LLM_MAX_NEW_TOKENS_ASK      = 400     # generation length cap — ask answers
LLM_JOB_RETENTION_S         = 3600    # sweep completed job entries from memory after this long

CACHE_DIR = Path.home() / "Library" / "Application Support" / "performance-bot"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CRASH_CACHE_PATH  = CACHE_DIR / "llm_crash_explanations.json"
DIGEST_CACHE_PATH = CACHE_DIR / "llm_digests.json"

# ─── Module state ───────────────────────────────────────────────────────────
_model = None
_tokenizer = None
_model_lock = threading.Lock()
_last_used_ts = 0.0
_watchdog_started = False
_watchdog_lock = threading.Lock()

_job_queue = Queue()
_jobs = {}                     # job_id -> {status, result, error, created_ts, kind, payload}
_jobs_lock = threading.Lock()
_worker_started = False
_worker_lock = threading.Lock()


def _log(msg: str) -> None:
    print(f"[llm_engine] {msg}", file=sys.stderr)


# ─── Disk caches (mirrors metrics.db / cda_model.onnx living under CACHE_DIR) ──
def _atomic_write_json(path: Path, data: dict) -> None:
    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(tmp_path, str(path))
    except Exception as e:
        _log(f"atomic write failed for {path.name}: {e}")


def _read_json(path: Path) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def get_cached_crash_explanation(crash_key: str):
    entry = _read_json(CRASH_CACHE_PATH).get(crash_key)
    return entry["explanation"] if entry else None


def _cache_crash_explanation(crash_key: str, explanation: str) -> None:
    data = _read_json(CRASH_CACHE_PATH)
    data[crash_key] = {"explanation": explanation, "ts": int(time.time())}
    _atomic_write_json(CRASH_CACHE_PATH, data)


def recent_crash_summaries(hours: int = 48, limit: int = 5) -> list:
    """Short (app: explanation-prefix) strings for crashes explained in the
    last `hours` — used to ground the Ask panel without feeding it the full
    explanation history."""
    data = _read_json(CRASH_CACHE_PATH)
    cutoff = time.time() - hours * 3600
    items = [(v.get("ts", 0), k, v.get("explanation", "")) for k, v in data.items()
             if v.get("ts", 0) >= cutoff]
    items.sort(reverse=True)
    return [f"{key}: {expl[:200]}" for _, key, expl in items[:limit]]


def get_latest_digest(period: str):
    return _read_json(DIGEST_CACHE_PATH).get(period)


def _save_digest(period: str, text: str) -> None:
    data = _read_json(DIGEST_CACHE_PATH)
    data[period] = {"ts": int(time.time()), "text": text}
    _atomic_write_json(DIGEST_CACHE_PATH, data)


# ─── Availability ───────────────────────────────────────────────────────────
def is_available() -> bool:
    """Cheap check — never triggers a model download."""
    return LLM_AVAILABLE


# ─── Model lifecycle ────────────────────────────────────────────────────────
def _ensure_loaded() -> bool:
    """Load the model on first use. Never called at import or BotEngine.__init__ —
    a multi-GB first-download/load is not the cheap/fast-fail operation CDA's
    ONNX load is, so this deliberately stays lazy."""
    global _model, _tokenizer, _last_used_ts, _watchdog_started
    if not LLM_AVAILABLE:
        return False
    with _model_lock:
        if _model is None:
            try:
                _log(f"loading {LLM_MODEL_REPO} (first use — may download ~2GB) ...")
                _model, _tokenizer = _mlx_load(LLM_MODEL_REPO)
                _log("model loaded")
            except Exception as e:
                _log(f"model load failed: {e}")
                _model, _tokenizer = None, None
                return False
        _last_used_ts = time.time()
    with _watchdog_lock:
        if not _watchdog_started:
            _watchdog_started = True
            threading.Thread(target=_idle_watchdog_loop, daemon=True).start()
    return True


def _idle_watchdog_loop() -> None:
    """Drops the model reference (freeing its RAM) after LLM_IDLE_UNLOAD_S of
    no generation calls — MLX/Metal unified memory is released back to the OS
    once refs are dropped and gc runs, no explicit unload API needed."""
    global _model, _tokenizer
    while True:
        time.sleep(LLM_IDLE_CHECK_S)
        with _model_lock:
            if _model is not None and (time.time() - _last_used_ts) > LLM_IDLE_UNLOAD_S:
                _log("idle timeout reached — unloading model")
                _model = None
                _tokenizer = None
                gc.collect()


def _generate(prompt: str, max_tokens: int) -> str:
    """`prompt` is a plain instruction string — wrapped in the model's chat
    template before generation. Qwen2.5-Instruct (like most instruct-tuned
    models) is trained on chat-formatted input; feeding it a raw completion
    prompt causes it to run past the assistant turn's EOS token and
    hallucinate a fake follow-up conversation instead of stopping cleanly."""
    global _last_used_ts
    if not _ensure_loaded():
        raise RuntimeError("model not available")
    with _model_lock:
        _last_used_ts = time.time()
        messages = [{"role": "user", "content": prompt}]
        formatted = _tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
        text = _mlx_generate(_model, _tokenizer, prompt=formatted, max_tokens=max_tokens, verbose=False)
        _last_used_ts = time.time()
    return text.strip()


def shutdown() -> None:
    """Best-effort cleanup — drop model references so the process can exit
    without holding onto GPU/unified-memory state."""
    global _model, _tokenizer
    with _model_lock:
        _model = None
        _tokenizer = None


# ─── Job queue / single serialized worker ──────────────────────────────────
# A 3-4B model on M1 unified memory won't usefully parallelize concurrent
# generations anyway, so one worker thread processing one job at a time keeps
# behavior predictable and avoids two generations fighting over the same
# weights.

def _ensure_worker_started() -> None:
    global _worker_started
    with _worker_lock:
        if not _worker_started:
            _worker_started = True
            threading.Thread(target=_worker_loop, daemon=True).start()


def _worker_loop() -> None:
    while True:
        job_id = _job_queue.get()
        try:
            _run_job(job_id)
        except Exception as e:
            # Defense in depth: _run_job already catches per-job errors, but a
            # bad job must never be able to kill the worker loop itself.
            _log(f"worker: unhandled error running job {job_id}: {e}")
            with _jobs_lock:
                if job_id in _jobs:
                    _jobs[job_id]["status"] = "error"
                    _jobs[job_id]["error"] = str(e)
        finally:
            _sweep_old_jobs()


def _run_job(job_id: str) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job["status"] = "running"
        kind, payload = job["kind"], job["payload"]

    try:
        if kind == "crash_explain":
            result = _do_crash_explain(payload)
        elif kind == "digest":
            result = _do_digest(payload)
        elif kind == "ask":
            result = _do_ask(payload)
        else:
            raise ValueError(f"unknown job kind: {kind}")
        with _jobs_lock:
            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["result"] = result
    except Exception as e:
        _log(f"job {job_id} ({kind}) failed: {e}")
        with _jobs_lock:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"] = str(e)
    finally:
        _fire_on_done(job_id)


def _fire_on_done(job_id: str) -> None:
    """Best-effort completion callback (e.g. so performance_gui.py can post an
    Activity Log entry) — failures here must never affect job state itself."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        on_done = job.get("on_done") if job else None
        snapshot = {"status": job["status"], "result": job["result"], "error": job["error"]} if job else None
    if on_done and snapshot:
        try:
            on_done(snapshot)
        except Exception as e:
            _log(f"on_done callback for job {job_id} raised: {e}")


def _sweep_old_jobs() -> None:
    cutoff = time.time() - LLM_JOB_RETENTION_S
    with _jobs_lock:
        stale = [jid for jid, j in _jobs.items() if j.get("created_ts", 0) < cutoff]
        for jid in stale:
            del _jobs[jid]


def _new_job(kind: str, payload: dict, on_done=None) -> str:
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {"status": "pending", "result": None, "error": None,
                          "created_ts": time.time(), "kind": kind, "payload": payload,
                          "on_done": on_done}
    _ensure_worker_started()
    _job_queue.put(job_id)
    return job_id


def get_job(job_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return {"status": "error", "result": None, "error": "unknown job id"}
        return {"status": job["status"], "result": job["result"], "error": job["error"]}


# ─── Feature 1: crash report explainer ─────────────────────────────────────
def submit_crash_explain(ips_path: str, crash_key: str, on_done=None) -> str:
    return _new_job("crash_explain", {"ips_path": ips_path, "crash_key": crash_key}, on_done=on_done)


def _build_crash_prompt(ips_path: str):
    """Returns (prompt, app_name). Extracts only the crashed thread (not the
    dozens of idle threads also present in a modern .ips body) and hard-caps
    length so a huge crash report can't blow the prompt budget."""
    app_name = "Unknown app"
    try:
        with open(ips_path, "r", errors="replace") as f:
            header_line = f.readline()
            body_line = f.readline()
    except Exception as e:
        return f"A crash report could not be read ({e}).", app_name

    try:
        header = json.loads(header_line)
        app_name = header.get("app_name", app_name)
    except Exception:
        header = {}

    crashed_thread_text = ""
    try:
        body = json.loads(body_line)
        exception = body.get("exception", {})
        termination = body.get("termination", {})
        threads = body.get("threads", [])
        crashed = next((t for t in threads if t.get("triggered")), threads[0] if threads else {})
        frame_lines = [f"  {fr.get('symbol', fr.get('imageName', '?'))}"
                       for fr in crashed.get("frames", [])]
        crashed_thread_text = (
            f"Exception: {json.dumps(exception)}\n"
            f"Termination: {json.dumps(termination)}\n"
            f"Crashed thread frames:\n" + "\n".join(frame_lines)
        )
    except Exception:
        # Legacy/non-JSON body (already silently skipped by
        # _check_crash_reports()'s own alerting) — fall back to a raw slice.
        try:
            with open(ips_path, "r", errors="replace") as f:
                crashed_thread_text = f.read()
        except Exception:
            crashed_thread_text = "(crash body unavailable)"

    if len(crashed_thread_text) > LLM_CRASH_PROMPT_MAX_CHARS:
        crashed_thread_text = crashed_thread_text[:LLM_CRASH_PROMPT_MAX_CHARS] + "\n[...truncated]"

    prompt = (
        "You are a macOS systems expert explaining a crash report to a non-expert Mac user. "
        "Be concise (3-6 sentences), plain-English, no jargon dumps. Say what likely crashed "
        "and why, in terms a normal user can understand. If you're not sure, say so honestly "
        "rather than guessing confidently.\n\n"
        f"App: {app_name}\n"
        f"{crashed_thread_text}\n"
    )
    return prompt, app_name


def _do_crash_explain(payload: dict) -> dict:
    ips_path = payload["ips_path"]
    crash_key = payload["crash_key"]
    prompt, app_name = _build_crash_prompt(ips_path)
    explanation = _generate(prompt, LLM_MAX_NEW_TOKENS_EXPLAIN)
    _cache_crash_explanation(crash_key, explanation)
    return {"explanation": explanation, "app_name": app_name, "crash_key": crash_key}


# ─── Feature 2: daily/weekly narrative digest ──────────────────────────────
def submit_digest(period: str, context: dict, on_done=None) -> str:
    return _new_job("digest", {"period": period, **context}, on_done=on_done)


def _downsample(rows: list, max_rows: int) -> list:
    if len(rows) <= max_rows:
        return rows
    step = max(1, len(rows) // max_rows)
    return rows[::step]


def _build_digest_prompt(period: str, hourly: list, outcomes: list) -> str:
    hourly = _downsample(hourly, LLM_DIGEST_MAX_ROWS)
    hour_lines = [
        f"{row.get('hour', '?')}  mem={row.get('mem', '?')}%  "
        f"cpu={row.get('cpu', '?')}%  swap={row.get('swap', '?')}%"
        for row in hourly
    ]
    outcome_lines = []
    for o in outcomes[:50]:
        ts_str = time.strftime("%H:%M", time.localtime(o.get("ts", 0)))
        delta = o.get("delta_mb")
        delta_str = f"{delta:+.0f}MB" if isinstance(delta, (int, float)) else "?MB"
        outcome_lines.append(
            f"{ts_str} tier{o.get('tier', '?')} {o.get('action', '?')} "
            f"{delta_str} {'success' if o.get('success') else 'failed'}"
        )

    body = (
        f"Hourly telemetry ({period}):\n" + "\n".join(hour_lines) + "\n\n"
        "Remediation actions taken:\n" + ("\n".join(outcome_lines) if outcome_lines else "(none)")
    )
    if len(body) > LLM_DIGEST_PROMPT_MAX_CHARS:
        body = body[:LLM_DIGEST_PROMPT_MAX_CHARS] + "\n[...truncated]"

    period_word = "day" if period == "daily" else "week"
    return (
        f"You are summarizing a Mac's performance over the past {period_word} for its owner. "
        "Write a short, friendly, plain-English narrative (4-8 sentences): what was normal, "
        "what stood out (spikes, trends, repeated remediation actions), and one practical "
        "takeaway if there is one. Do not just restate every number — synthesize.\n\n"
        f"{body}\n"
    )


def _do_digest(payload: dict) -> str:
    period = payload["period"]
    prompt = _build_digest_prompt(period, payload.get("hourly", []), payload.get("outcomes", []))
    text = _generate(prompt, LLM_MAX_NEW_TOKENS_DIGEST)
    _save_digest(period, text)
    return text


# ─── Feature 3: Ask panel ───────────────────────────────────────────────────
def submit_ask(question: str, context: dict) -> str:
    return _new_job("ask", {"question": question, **context})


def _build_ask_prompt(question: str, hourly: list, digest_text: str, crash_summaries: list) -> str:
    hour_lines = [
        f"{row.get('hour', '?')}  mem={row.get('mem', '?')}%  "
        f"cpu={row.get('cpu', '?')}%  swap={row.get('swap', '?')}%"
        for row in hourly
    ]
    hourly_block = ("Recent hourly telemetry:\n" + "\n".join(hour_lines)) if hour_lines else ""
    digest_block = f"Today's summary:\n{digest_text}" if digest_text else ""
    crash_block = ("Recent crash explanations:\n" + "\n".join(f"- {c}" for c in crash_summaries)
                   ) if crash_summaries else ""

    def _assemble(blocks):
        return "\n\n".join(b for b in blocks if b)

    # Budget: drop crash explanations first (least essential), then trim
    # hourly rows, keep the digest text intact longest (densest signal).
    context_text = _assemble([hourly_block, digest_block, crash_block])
    if len(context_text) > LLM_ASK_PROMPT_MAX_CHARS:
        context_text = _assemble([hourly_block, digest_block])
    if len(context_text) > LLM_ASK_PROMPT_MAX_CHARS and hour_lines:
        keep = max(1, len(hour_lines) // 2)
        hourly_block = "Recent hourly telemetry:\n" + "\n".join(hour_lines[-keep:])
        context_text = _assemble([hourly_block, digest_block])
    if len(context_text) > LLM_ASK_PROMPT_MAX_CHARS:
        context_text = context_text[:LLM_ASK_PROMPT_MAX_CHARS] + "\n[...truncated]"

    return (
        "You are a helpful assistant answering questions about a Mac's own performance "
        "history, using the telemetry below. Be concise and specific; if the data doesn't "
        "answer the question, say so honestly rather than guessing.\n\n"
        f"{context_text}\n\n"
        f"Question: {question}\n"
        "Answer:"
    )


def _do_ask(payload: dict) -> str:
    prompt = _build_ask_prompt(
        payload["question"],
        payload.get("hourly", []),
        payload.get("digest_text", ""),
        payload.get("crash_summaries", []),
    )
    return _generate(prompt, LLM_MAX_NEW_TOKENS_ASK)
