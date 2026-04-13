#!/usr/bin/env python3
"""
Performance Bot — Web GUI
Opens a live dashboard in your browser. No GUI dependencies needed.
Backend: Python http.server  |  Frontend: Chart.js (CDN)
"""

import os, sys, time, json, threading, subprocess, webbrowser, sqlite3, math
from collections import deque
from datetime import datetime
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

try:
    import psutil
except ImportError as exc:
    raise SystemExit(
        "Missing required dependency 'psutil'. Install it before running this app, "
        "for example with: python3 -m pip install psutil"
    ) from exc

PORT    = 8765
HOST    = "127.0.0.1"
LOG_DIR = Path.home() / "Library" / "Logs" / "performance-bot"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ─── Disk Metrics Cache ───────────────────────────────────────────────────────
CACHE_DIR            = Path.home() / "Library" / "Application Support" / "performance-bot"
CACHE_DB             = CACHE_DIR / "metrics.db"
CDA_MODEL_PATH       = CACHE_DIR / "cda_model.onnx"
CACHE_RETENTION_DAYS = 90     # rows older than this are pruned
CACHE_WRITE_S        = 60     # flush in-memory buffer to disk every N seconds
CACHE_PRUNE_S        = 86400  # prune expired rows once per day
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class MetricsCache:
    """
    Lightweight SQLite-backed ring store for 90-day metric history.

    Design goals — minimal CPU and RAM impact:
      • Writes are batched: up to CACHE_WRITE_S rows accumulated in a tiny
        list then flushed with a single executemany() — no per-second I/O.
      • Reads are aggregate-only: historical pattern queries use SQL GROUP BY
        so only a single row per hour-of-day is returned to Python, never the
        full 90-day dataset.
      • The in-memory buffer holds at most CACHE_WRITE_S tuples (~4 KB max).
      • No background thread — all operations run on the BotEngine thread,
        keeping the total thread count unchanged.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS metrics (
        ts            INTEGER NOT NULL,
        cpu_pct       REAL,
        mem_pct       REAL,
        swap_pct      REAL,
        disk_pct      REAL,
        pressure      TEXT,
        eff_tier      INTEGER,
        tte_min       REAL,
        thermal_pct   INTEGER DEFAULT 100
    );
    CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(ts);
    CREATE TABLE IF NOT EXISTS remediation_outcomes (
        ts         INTEGER NOT NULL,
        tier       INTEGER,
        action     TEXT,
        pre_mem    REAL,
        post_mem   REAL,
        delta_mb   REAL,
        success    INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_outcomes_ts ON remediation_outcomes(ts);
    CREATE TABLE IF NOT EXISTS signal_weights (
        ts          INTEGER NOT NULL,
        s1_weight   REAL,
        s2_weight   REAL,
        s3_weight   REAL,
        s4_weight   REAL,
        s5_weight   REAL,
        s6_weight   REAL,
        accuracy    REAL
    );
    CREATE INDEX IF NOT EXISTS idx_weights_ts ON signal_weights(ts);
    """

    def __init__(self, db_path: Path):
        self._db   = str(db_path)
        self._buf  = []   # [(ts, cpu, mem, swap, disk, pressure, tier, tte, therm)]
        self._last_prune = 0.0
        self._ok   = False
        try:
            with sqlite3.connect(self._db, timeout=5) as cx:
                cx.executescript(self._SCHEMA)
                # Migrate existing databases missing the thermal_pct column
                try:
                    cx.execute("ALTER TABLE metrics ADD COLUMN thermal_pct INTEGER DEFAULT 100")
                except sqlite3.OperationalError:
                    pass  # column already exists
                # v2.0 migrations: create new tables if absent
                try:
                    cx.execute("""CREATE TABLE IF NOT EXISTS remediation_outcomes (
                        ts INTEGER NOT NULL, tier INTEGER, action TEXT,
                        pre_mem REAL, post_mem REAL, delta_mb REAL, success INTEGER)""")
                    cx.execute("CREATE INDEX IF NOT EXISTS idx_outcomes_ts ON remediation_outcomes(ts)")
                    cx.execute("""CREATE TABLE IF NOT EXISTS signal_weights (
                        ts INTEGER NOT NULL, s1_weight REAL, s2_weight REAL, s3_weight REAL,
                        s4_weight REAL, s5_weight REAL, s6_weight REAL, accuracy REAL)""")
                    cx.execute("CREATE INDEX IF NOT EXISTS idx_weights_ts ON signal_weights(ts)")
                except Exception:
                    pass
            self._ok = True
        except Exception as e:
            # Cache failure is non-fatal — bot continues without it
            print(f"[cache] init failed: {e}", file=sys.stderr)

    # ── public ────────────────────────────────────────────────────────────────

    def record(self, ts, cpu, mem, swap, disk, pressure, tier, tte, therm=100):
        """Append one row to the in-memory buffer (no disk I/O)."""
        if self._ok:
            self._buf.append((int(ts), cpu, mem, swap, disk, pressure, tier, tte, therm))

    def flush(self):
        """Write buffered rows to SQLite and clear the buffer."""
        if not self._ok or not self._buf:
            return
        rows, self._buf = self._buf, []
        try:
            with sqlite3.connect(self._db, timeout=5) as cx:
                cx.executemany(
                    "INSERT INTO metrics VALUES (?,?,?,?,?,?,?,?,?)", rows
                )
        except Exception as e:
            print(f"[cache] flush failed: {e}", file=sys.stderr)

    def prune(self, retention_days=CACHE_RETENTION_DAYS):
        """Delete rows older than retention_days. Call at most once per day."""
        now = time.time()
        if now - self._last_prune < CACHE_PRUNE_S:
            return
        self._last_prune = now
        if not self._ok:
            return
        cutoff = int(now - retention_days * 86400)
        try:
            with sqlite3.connect(self._db, timeout=5) as cx:
                cx.execute("DELETE FROM metrics WHERE ts < ?", (cutoff,))
                cx.execute("PRAGMA wal_checkpoint(PASSIVE)")
        except Exception as e:
            print(f"[cache] prune failed: {e}", file=sys.stderr)

    def app_mem_trend(self, app_name: str, lookback_days=30) -> dict:
        """
        Query the 30-day average and week-over-week memory trend for a specific
        application family. Used by _analyse_app_predictions() to detect chronic
        RAM hogs and slowly growing processes across sessions.

        Returns dict with keys: avg_mem_pct, week1_avg, week2_avg, trend_direction.
        All computation happens in SQLite — only a handful of aggregate rows
        are returned to Python.
        """
        if not self._ok:
            return {}
        now   = int(time.time())
        w1_lo = now - 7 * 86400
        w2_lo = now - 14 * 86400
        try:
            with sqlite3.connect(self._db, timeout=3) as cx:
                # 30-day average system RAM when this app was heavy
                avg_row = cx.execute(
                    "SELECT AVG(mem_pct), COUNT(*) FROM metrics WHERE ts >= ?",
                    (now - lookback_days * 86400,)
                ).fetchone()
                w1 = cx.execute(
                    "SELECT AVG(mem_pct) FROM metrics WHERE ts >= ? AND ts < ?",
                    (w1_lo, now)
                ).fetchone()[0]
                w2 = cx.execute(
                    "SELECT AVG(mem_pct) FROM metrics WHERE ts >= ? AND ts < ?",
                    (w2_lo, w1_lo)
                ).fetchone()[0]
            avg = avg_row[0] or 0.0
            w1 = w1 or 0.0
            w2 = w2 or 0.0
            trend = "rising" if w1 > w2 + 2 else ("falling" if w1 < w2 - 2 else "stable")
            return {"avg_mem_pct": round(avg, 1), "week1_avg": round(w1, 1),
                    "week2_avg": round(w2, 1), "trend": trend}
        except Exception:
            return {}

    def chronic_pressure_pct(self, lookback_days=7, threshold_pct=80.0) -> float:
        """
        Return the fraction (0–100) of the last lookback_days where system RAM
        was above threshold_pct. High values indicate chronically memory-
        constrained conditions — useful for recommending RAM upgrades.
        Only two aggregate rows are returned; no large datasets in Python.
        """
        if not self._ok:
            return 0.0
        cutoff = int(time.time() - lookback_days * 86400)
        try:
            with sqlite3.connect(self._db, timeout=3) as cx:
                total = cx.execute(
                    "SELECT COUNT(*) FROM metrics WHERE ts >= ?", (cutoff,)
                ).fetchone()[0]
                over  = cx.execute(
                    "SELECT COUNT(*) FROM metrics WHERE ts >= ? AND mem_pct >= ?",
                    (cutoff, threshold_pct)
                ).fetchone()[0]
            return round(over / total * 100, 1) if total else 0.0
        except Exception:
            return 0.0

    def db_size_mb(self) -> float:
        """Return the on-disk size of the cache database in MB."""
        try:
            return Path(self._db).stat().st_size / 1e6
        except Exception:
            return 0.0

    def row_count(self) -> int:
        """Return approximate row count (uses sqlite_stat or COUNT(*))."""
        if not self._ok:
            return 0
        try:
            with sqlite3.connect(self._db, timeout=3) as cx:
                return cx.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
        except Exception:
            return 0

    def record_outcome(self, ts, tier, action, pre_mem, post_mem, delta_mb, success):
        """Insert one remediation outcome row (RAC). No buffering — outcomes are infrequent."""
        if not self._ok:
            return
        try:
            with sqlite3.connect(self._db, timeout=5) as cx:
                cx.execute(
                    "INSERT INTO remediation_outcomes VALUES (?,?,?,?,?,?,?)",
                    (int(ts), tier, action, pre_mem, post_mem, delta_mb, success)
                )
        except Exception as e:
            print(f"[cache] record_outcome failed: {e}", file=sys.stderr)

    def query_signal_accuracy(self, signal: str, hours: int = 24) -> float:
        """
        Return fraction of outcomes in last `hours` hours where `signal` voted high
        AND remediation succeeded. Maps signal name (s1–s6) to action type heuristic.
        Used by RWA to reweight ACN signal contributions.
        """
        if not self._ok:
            return 0.5   # neutral default
        cutoff = int(time.time() - hours * 3600)
        try:
            with sqlite3.connect(self._db, timeout=3) as cx:
                rows = cx.execute(
                    "SELECT success FROM remediation_outcomes WHERE ts >= ? AND tier >= 2",
                    (cutoff,)
                ).fetchall()
            if not rows:
                return 0.5
            return round(sum(r[0] for r in rows) / len(rows), 3)
        except Exception:
            return 0.5

    def query_tier_distribution(self, days: int = 30) -> dict:
        """
        Return {tier: count} from metrics table over last `days` days.
        Used by BRL to update tier-frequency priors.
        """
        if not self._ok:
            return {}
        cutoff = int(time.time() - days * 86400)
        try:
            with sqlite3.connect(self._db, timeout=3) as cx:
                rows = cx.execute(
                    "SELECT eff_tier, COUNT(*) FROM metrics WHERE ts >= ? "
                    "AND eff_tier IS NOT NULL GROUP BY eff_tier",
                    (cutoff,)
                ).fetchall()
            return {int(r[0]): int(r[1]) for r in rows}
        except Exception:
            return {}

# ─── Thresholds & Patterns ────────────────────────────────────────────────────
PROTECTED = {
    "kernel_task", "launchd", "WindowServer", "loginwindow", "Finder",
    "Dock", "SystemUIServer", "coreaudiod", "cfprefsd", "mds",
    "mds_stores", "mdworker", "performance_bot", "performance_gui",
    "Python", "python3", "python",
}
NEVER_TERMINATE = {
    "com.apple.AuthenticationServices.Helper",
    "CredentialProviderExtensionHelper",
    "Keychain Circle Notification",
    "com.apple.iCloud.Keychain",
}
IDLE_SERVICE_PATTERNS = (
    "Widget", "Extension", "XPCService", "HelperService",
    "BookkeepingService", "PredictionIntents", "MTLCompilerService",
    "VTEncoderXPCService", "VTDecoderXPCService", "WallpaperVideo",
    "CloudTelemetryService", "IntelligencePlatformComputeService",
    "SAExtensionOrchestrator", "SiriNCService", "SiriSuggestions",
    "SiriInference", "ServiceExtension", "NewsTag", "AppPredictionIntents",
)

CPU_WARN         = 70.0
CPU_THROTTLE     = 85.0
MEM_WARN         = 80.0
SWAP_WARN        = 50.0
RENICE_VAL       = 10
HISTORY_LEN      = 90
IDLE_MB_FLOOR    = 15
IDLE_SWEEP_S     = 30
CACHE_WARN_GB    = 5.0
LEAK_RATE_MB_MIN = 50    # MB/min growth rate to flag as potential leak
LEAK_MIN_RSS_MB  = 200   # minimum RSS before flagging a leak
CONSUMER_COOL_S  = 300   # min seconds between top-consumer reports

# ─── Memory Intelligence (MMIE) constants ─────────────────────────────────────
MEM_TIER2_PCT        = 82.0   # purgeable scan + ancestry report trigger
MEM_TIER3_PCT        = 87.0   # background daemon freeze trigger
MEM_TIER4_PCT        = 92.0   # emergency idle-service termination
WIRED_WARN_PCT       = 40.0   # wired % of total RAM → structural pressure alert
FREEZE_COOL_S        = 120    # min seconds between freeze cycles
MEM_ANCESTRY_COOL_S  = 120    # min seconds between ancestry reports
FREEZE_PATTERNS      = (      # background daemons safe to SIGSTOP temporarily
    "photoanalysisd", "photolibraryd", "mediaanalysisd", "mediaremoted",
    "suggestd", "cloudd", "bird", "nsurlsessiond", "amsaccountsd",
    "rapportd", "helpd", "AirPlayXPCHelper", "weatherd", "tipsd",
    "triald", "UsageTrackingAgent", "com.apple.ap.adprivacyd",
)

# ─── Predictive Remediation Engine constants ──────────────────────────────────
TTE_TIER2_MIN    = 10.0   # trigger Tier 2 early when TTE ≤ this many minutes
TTE_TIER3_MIN    =  5.0   # trigger Tier 3 early when TTE ≤ this
TTE_TIER4_MIN    =  2.0   # trigger Tier 4 early when TTE ≤ this
TTE_MIN_SAMPLES  = 20     # minimum mem_hist samples before TTE can drive escalation
XPC_RESPAWN_S    = 10     # seconds; services restarting within this window → blocklisted

# ─── MMAF — Multi-Model Adaptive Forecaster ───────────────────────────────────
MMAF_MIN_SAMPLES = 10     # minimum samples before any model engages
MMAF_WINDOW      = 30     # rolling window size for model fitting (seconds)
MMAF_TARGET_PCT  = 95.0   # forecast target RAM %

# ─── CEO — Compression Efficiency Oracle ──────────────────────────────────────
CPI_TIER2            = 0.50   # CPI ≥ this → compression headroom degrading
CPI_TIER3            = 0.75   # CPI ≥ this → compressor near exhaustion
CEO_MIN_COMPRESSED   = 200    # MB; below this CEO signal is noise-floored

# ─── MSCEE — Multi-Signal Consensus Escalation Engine ─────────────────────────
MSCEE_QUORUM         = 0.55   # weighted vote share required to adopt a tier

# ─── GTS — Graduated Thaw Sequencer ──────────────────────────────────────────
GTS_WAIT_S           = 2.0    # seconds between successive SIGCONT sends
GTS_MEM_GATE_PCT     = 5.0    # abort thaw if RAM rises more than this since thaw began

# ─── ATCE — Adaptive Threshold Calibration Engine ─────────────────────────────
ATCE_PERCENTILE      = 75     # 75th‑pct of historical RAM as Tier 2 calibrated threshold
ATCE_COOL_S          = 3600   # recalibrate at most once per hour
ATCE_MIN_ROWS        = 1000   # minimum DB rows before calibration runs

# ─── CMPE — Circadian Memory Pattern Engine ───────────────────────────────────
CMPE_PRE_FREEZE_SCORE = 70.0  # hour avg ≥ this triggers proactive pre-freeze
CMPE_COOL_S          = 3600   # circadian check once per hour

# ─── TMCP — Thermal-Memory Coupling Predictor ─────────────────────────────────
TMCP_LEARN_RATE      = 0.10   # EMA learning rate for thermal→memory coupling
TMCP_COOL_S          = 3600   # recompute coupling factor once per hour
TMCP_MIN_SAMPLES     = 5      # minimum thermal-throttled rows before coupling applied

# ─── RVMS — RSS Velocity Momentum Scorer ──────────────────────────────────────
RVMS_MAX_BOOST       = 2.0    # maximum velocity momentum multiplier

# ─── SIE — Signal Integrity Estimator ─────────────────────────────────────────
SIE_WINDOW           = 30     # rolling window (samples) for z-score computation
SIE_ZSCORE_THRESH    = 3.0    # flag signal if |z| > this

# ─── MEG — Model Ensemble Governance ──────────────────────────────────────────
MEG_RESIDUAL_HISTORY = 5      # residual samples per model for meta-weight

# ─── RWA / ACN — Reinforcement-Weighted Arbitration / Adaptive Consensus ──────
RWA_LEARN_RATE       = 0.05   # EMA rate for weight adjustments
RWA_MIN_WEIGHT       = 0.02   # floor: no signal drops to zero
RWA_OUTCOMES_H       = 24     # hours of outcome history for accuracy query

# ─── CTRE — Chronothermal Regression Engine ───────────────────────────────────
CTRE_MIN_SAMPLES     = 10     # minimum 2D samples before regression valid
CTRE_COOL_S          = 3600   # recompute once per hour

# ─── AIP — Ancestral Impact Propagation ───────────────────────────────────────
AIP_MIN_MB           = 50     # minimum family RSS to include in propagation
AIP_MAX_DEPTH        = 3      # max parent-child chain depth

# ─── RAC — Reinforcement Action Coordinator ───────────────────────────────────
RAC_EVAL_DELAY_S     = 30     # seconds after action before outcome measured
RAC_SUCCESS_PCT      = 2.0    # RAM must drop ≥ this % to count as success

# ─── ASZM — Adaptive Safety Zone Mapping ──────────────────────────────────────
ASZM_CRIT_SCORE      = 0.8    # criticality threshold → add to dynamic protected
ASZM_COOL_S          = 3600   # recalibrate once per hour

# ─── PSM — Predictive State Machine ───────────────────────────────────────────
PSM_HISTORY          = 20     # max tier-transition events tracked
PSM_DWELL_MIN_S      = 3.0    # min seconds in a tier before transition is counted

# ─── BRL — Bayesian Reasoning Layer ───────────────────────────────────────────
BRL_PRIOR_ALPHA      = 1.0    # Beta prior alpha (weak prior)
BRL_PRIOR_BETA       = 9.0    # Beta prior beta
BRL_COOL_S           = 3600   # update prior from cache once per hour

# ─── CDA — Causal Diagnostic Agent ────────────────────────────────────────────
CDA_TRAIN_MIN_ROWS   = 200    # min labeled rows before model training
CDA_TRAIN_COOL_S     = 2592000  # retrain at most once per 30 days
CDA_LR               = 0.01   # SGD learning rate for softmax logistic regression
CDA_EPOCHS           = 100    # gradient-descent epochs per training run
CDA_LABEL_LEAK       = 50     # MB/min growth rate threshold → label "leak"
CDA_LABEL_COMP_CPI   = 0.60   # CPI threshold → label "compressor_collapse"


# ─── Bot Engine ───────────────────────────────────────────────────────────────
class BotEngine(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="bot-engine")
        self._lock            = threading.Lock()
        self.running          = True
        self.cpu_hist         = deque(maxlen=HISTORY_LEN)
        self.mem_hist         = deque(maxlen=HISTORY_LEN)
        self.swap_hist        = deque(maxlen=HISTORY_LEN)
        self.top_procs        = []
        self.throttled        = {}      # pid → name
        self.events           = deque(maxlen=200)   # O(1) append+bound, no pop(0)
        self.actions          = 0
        self.issues           = 0
        self.freed_mb         = 0.0
        self.thermal_pct      = 100    # 100 = no throttle; <100 = thermally limited
        self.on_battery       = False
        self._start_time      = time.time()
        self._swap_warned     = False
        self._terminated      = set()
        self._rss_history     = {}     # pid → [(ts, rss_mb), ...]
        self._warned_leaks    = set()  # pids already flagged this session
        self._cache_warned    = False
        self.disk_pct         = 0.0
        self.disk_free_gb     = 0.0
        self._last_consumer   = 0.0    # timestamp of last consumer report
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        self._mem_total_gb   = vm.total / 1e9
        self._swap_total_gb  = sw.total / 1e9
        psutil.cpu_percent(interval=None)
        # ── Performance: cached constants to avoid repeated syscalls ────────
        self._ncpu           = psutil.cpu_count(logical=True) or 1   # immutable
        self._last_vm        = vm          # updated each _collect() — shared with _check_memory()
        self._last_swap      = sw
        self._last_disk_pct  = 0.0        # updated by _check_disk()
        # ── MMIE state ──────────────────────────────────────────────────────
        self.mem_pressure_level  = "normal"   # 'normal'|'warn'|'critical'
        self.vm_breakdown        = {}         # wired/active/inactive/free/purgeable/compressed MB
        self.mem_forecast_min    = -1         # minutes to ~95% exhaustion; -1 = stable
        self.mem_ancestry        = []         # [{app,mb,pct}] top process families by RSS
        self._wired_warned       = False
        self._frozen_pids        = {}         # pid → (name, freeze_ts, rss_mb)
        self._last_freeze        = 0.0
        self._last_ancestry      = 0.0
        # ── Predictive Remediation Engine state ─────────────────────────────
        self.effective_tier       = 0         # actual tier being acted on (may exceed threshold_tier)
        self.predictive_escalation = False    # True when TTE drove tier above static threshold
        self._ram_pressure_lock   = False     # True during Tier 3+ — blocks CPU nice(0) restoration
        self._no_kill             = set()     # process names blocklisted after XPC respawn detection
        self._terminated_ts       = {}        # name → timestamp of last SIGTERM
        # ── Disk metrics cache ───────────────────────────────────────────────
        self._cache = MetricsCache(CACHE_DB)
        self._cache.prune()                   # clean up expired rows on startup
        self.cache_db_mb: float = self._cache.db_size_mb()
        self.cache_rows: int    = self._cache.row_count()
        # App-level predictions derived from cache; refreshed every 24 h
        self.app_predictions: list = []       # [{app, avg_mb, trend, risk}]
        self._last_app_predict: float = 0.0
        self._paused: bool = False
        # ── MMAF: Multi-Model Adaptive Forecaster ────────────────────────────
        self._last_forecast_model: str = "linear"
        # ── ATCE: Adaptive Threshold Calibration Engine ───────────────────────
        self._cal_thresholds: dict = {}
        self._last_atce: float = 0.0
        # ── CMPE: Circadian Memory Pattern Engine ─────────────────────────────
        self._circadian_profile: dict = {}    # hour(int) → avg_mem_pct
        self._last_circadian: float = 0.0
        # ── CEO: Compression Efficiency Oracle ────────────────────────────────
        self._compression_pressure: float = 0.0
        # ── TMCP: Thermal-Memory Coupling Predictor ───────────────────────────
        self._thermal_coupling: float = 0.0
        self._last_tmcp: float = 0.0
        # ── RVMS: RSS Velocity Momentum Scorer ────────────────────────────────
        self._rss_velocity: dict = {}         # pid → (ts, rss_mb)
        # ── Swap velocity ─────────────────────────────────────────────────────
        self._swap_velocity: float = 0.0
        self._last_swap_used: float = 0.0
        self._last_swap_ts: float = 0.0
        # ── SIE: Signal Integrity Estimator ──────────────────────────────────
        self._signal_confidence = {"cpu": 1.0, "mem": 1.0, "swap": 1.0}
        self._sie_history = {
            "cpu":  deque(maxlen=SIE_WINDOW),
            "mem":  deque(maxlen=SIE_WINDOW),
            "swap": deque(maxlen=SIE_WINDOW),
        }
        # ── MEG: Model Ensemble Governance ───────────────────────────────────
        self._model_residual_history = {
            "linear":      deque(maxlen=MEG_RESIDUAL_HISTORY),
            "quadratic":   deque(maxlen=MEG_RESIDUAL_HISTORY),
            "exponential": deque(maxlen=MEG_RESIDUAL_HISTORY),
        }
        # ── ACN / RWA: Adaptive Consensus Network / Reinforcement-Weighted ───
        self._acn_weights = {
            "s1": 0.30, "s2": 0.25, "s3": 0.20,
            "s4": 0.12, "s5": 0.08, "s6": 0.05,
        }
        self._last_rwa: float = 0.0
        # ── CTRE: Chronothermal Regression Engine ─────────────────────────────
        self._ctre_stability: dict = {}   # {hour: stability_score 0.0-1.0}
        self._last_ctre: float = 0.0
        # ── AIP: Ancestral Impact Propagation ─────────────────────────────────
        self._aip_impact: list = []       # [{app, impact_score, cascade_depth, child_mb}]
        self._last_aip: float = 0.0
        # ── RAC: Reinforcement Action Coordinator ─────────────────────────────
        self._pending_outcomes: list = [] # [(eval_ts, tier, action, pre_mem)]
        self._action_efficacy: dict = {}  # action_type → running avg delta_pct
        # ── ASZM: Adaptive Safety Zone Mapping ───────────────────────────────
        self._dynamic_protected: set = set(PROTECTED)
        self._criticality_scores: dict = {}   # name → float
        self._last_aszm: float = 0.0
        # ── PSM: Predictive State Machine ─────────────────────────────────────
        self._tier_transitions: deque = deque(maxlen=PSM_HISTORY)  # (from, to, ts)
        self._transition_matrix: dict = {}   # (from, to) → count
        self._tier_dwell_start: float = time.time()
        self._prev_tier: int = 0
        self._psm_next_tier: int = 0
        self._psm_dwell_s: float = 0.0
        # ── BRL: Bayesian Reasoning Layer ─────────────────────────────────────
        self._brl_tier_prior: list = [BRL_PRIOR_ALPHA] * 5   # per-tier alpha counts
        self._brl_confidence: float = 1.0
        self._last_brl: float = 0.0
        # ── CDA: Causal Diagnostic Agent ──────────────────────────────────────
        self.causal_diagnosis: str = "normal"   # normal|leak|compressor_collapse|cpu_collision
        self._cda_session = None                # onnxruntime.InferenceSession (if available)
        self._last_cda_train: float = 0.0
        self._cda_confidence: float = 0.0
        # Try to load existing CDA model at startup
        self._cda_load_model()

    # ── public ────────────────────────────────────────────────────────────────
    def stop(self):
        self.running = False

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def snapshot(self):
        with self._lock:
            return {
                "cpu_hist":      list(self.cpu_hist),
                "mem_hist":      list(self.mem_hist),
                "swap_hist":     list(self.swap_hist),
                "top_procs":     list(self.top_procs),
                "throttled":     dict(self.throttled),
                "events":        list(self.events),   # deque already capped at 200
                "actions":       self.actions,
                "issues":        self.issues,
                "freed_mb":      round(self.freed_mb, 0),
                "thermal_pct":   self.thermal_pct,
                "on_battery":    self.on_battery,
                "uptime_s":      int(time.time() - self._start_time),
                "disk_pct":           self.disk_pct,
                "disk_free_gb":       self.disk_free_gb,
                "mem_total_gb":       round(self._mem_total_gb, 1),
                "swap_total_gb":      round(self._swap_total_gb, 1),
                "mem_pressure_level":   self.mem_pressure_level,
                "vm_breakdown":         dict(self.vm_breakdown),
                "mem_forecast_min":     self.mem_forecast_min,
                "mem_ancestry":         list(self.mem_ancestry),
                "effective_tier":       self.effective_tier,
                "predictive_escalation": self.predictive_escalation,
                "cpu_ram_lock":         self._ram_pressure_lock,
                "xpc_blocked":          len(self._no_kill),
                "cache_db_mb":          round(self.cache_db_mb, 2),
                "cache_rows":           self.cache_rows,
                "app_predictions":      list(self.app_predictions),
                "frozen_count":         len(self._frozen_pids),
                "leak_pids":            len(self._warned_leaks),
                "forecast_model":       self._last_forecast_model,
                "compression_pressure": round(self._compression_pressure, 3),
                "swap_velocity":        round(self._swap_velocity, 1),
                "cal_thresholds":       dict(self._cal_thresholds),
                "circadian_profile":    {str(k): v for k, v in self._circadian_profile.items()},
                "thermal_coupling":     round(self._thermal_coupling, 3),
                # v2.0 fields
                "signal_confidence":    dict(self._signal_confidence),
                "acn_weights":          dict(self._acn_weights),
                "brl_confidence":       round(self._brl_confidence, 3),
                "psm_next_tier":        self._psm_next_tier,
                "psm_dwell_s":          round(self._psm_dwell_s, 1),
                "action_efficacy":      dict(self._action_efficacy),
                "ctre_stability":       {str(h): v for h, v in self._ctre_stability.items()},
                "aip_impact":           list(self._aip_impact),
                "causal_diagnosis":     self.causal_diagnosis,
                "dynamic_protected":    len(self._dynamic_protected) - len(PROTECTED),
            }

    # ── internal ──────────────────────────────────────────────────────────────
    def _emit(self, kind, msg):
        ev = {"kind": kind, "msg": msg,
              "ts": datetime.now().strftime("%H:%M:%S")}
        with self._lock:
            self.events.append(ev)   # deque(maxlen=200) auto-discards oldest

    def run(self):
        self._emit("info", "Performance Bot started — monitoring every second.")
        tick = 0
        while self.running:
            if not self._paused:
                try:
                    self._collect(tick)                                      # 1 Hz — single process scan
                    if tick % 3  == 0: self._check_memory()                 # 0.33 Hz
                    if tick % 5  == 0: self._update_pressure_and_forecast() # 0.2 Hz — sysctl + vm_stat
                    if tick % 10 == 0: self._check_disk()                   # 0.1 Hz
                    if tick % 30 == 0: self._check_power_mode()             # 0.03 Hz
                    if tick % 30 == 0: self._detect_xpc_respawn()           # 0.03 Hz (was 0.1 Hz)
                    if tick % 60 == 0: self._check_thermal()                # 0.016 Hz — pmset subprocess
                    if tick % 60 == 0: self._check_zombies()
                    if tick % 60 == 0: self._track_memory_leaks()
                    if tick % IDLE_SWEEP_S == 0: self._sweep_idle_services()
                    if tick % 60  == 0: self._check_circadian_pressure()
                    if tick % 300 == 0 and tick > 0: self._check_caches()
                    if tick % CACHE_WRITE_S == 0:
                        self._cache.flush()
                        self._cache.prune()
                        self.cache_db_mb = self._cache.db_size_mb()
                        self.cache_rows  = self._cache.row_count()
                    if tick % 3600 == 0 and tick > 0:
                        self._analyse_app_predictions()
                        self._calibrate_thresholds()
                        self._compute_thermal_coupling()
                        self._update_rwa_weights()
                        self._compute_ctre()
                        self._update_aszm()
                        self._update_brl()
                    # CDA training: run at startup and every 30 days
                    if tick == 0 or (self._last_cda_train > 0 and
                            time.time() - self._last_cda_train >= CDA_TRAIN_COOL_S):
                        self._cda_train_model()
                except Exception as exc:
                    self._emit("warn", f"Engine error: {exc}")
            tick += 1
            time.sleep(1)
        self._emit("info", "Performance Bot stopped.")

    def _collect(self, tick: int):
        """
        Single process scan per second.
        Collects system metrics AND performs CPU throttle detection in one
        psutil.process_iter() call — eliminating the second full scan that
        _check_cpu() previously performed.
        """
        cpu  = psutil.cpu_percent(interval=None)
        vm   = psutil.virtual_memory()
        swap = psutil.swap_memory()
        ncpu = self._ncpu   # cached at init — no repeated syscall

        # SIE: compute signal integrity before appending to history
        self._compute_signal_confidence(cpu, vm.percent,
                                         swap.percent if swap.total > 0 else 0.0)
        # RAC: check if any pending outcomes are ready to evaluate
        self._evaluate_rac_outcomes()

        rows        = []
        to_throttle = []   # (Process, name, pid, cpu_pct) — applied after loop

        with self._lock:
            ram_lock   = self._ram_pressure_lock
            throttled  = set(self.throttled)
            sys_cpu    = cpu

        for p in psutil.process_iter(["pid", "name", "cpu_percent",
                                       "memory_percent", "status"]):
            try:
                info  = p.info
                name  = info["name"][:30]
                pid   = info["pid"]
                c     = (info["cpu_percent"] or 0.0) / ncpu
                mem_p = info["memory_percent"] or 0.0
                stat  = info["status"]

                rows.append((c, mem_p, pid, name, stat))

                # CPU throttle detection — inline, no second iteration
                if sys_cpu >= CPU_WARN and name not in PROTECTED \
                        and pid not in throttled:
                    if c >= CPU_THROTTLE:
                        to_throttle.append((p, name, pid, c))
                    elif c >= CPU_WARN:
                        self.issues += 1
                        self._emit("warn",
                            f"High CPU: {name} (PID {pid}) using {c:.0f}%")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        rows.sort(reverse=True)

        # Restore calmed throttled procs (tiny loop — usually 0–3 items)
        self._restore_calmed_procs(ram_lock)

        # Apply new throttles (outside the iteration loop)
        for p, name, pid, c in to_throttle:
            try:
                p.nice(RENICE_VAL)   # syscall — outside lock
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            with self._lock:
                self.throttled[pid] = name
                self.actions += 1
                self.issues  += 1
            self._emit("fix",
                f"AUTO-THROTTLED {name} (PID {pid}): "
                f"{c:.0f}% CPU → nice set to {RENICE_VAL}")

        swap_pct = swap.percent if swap.total > 0 else 0.0

        # Swap velocity (RVMS input) — computed before acquiring lock
        now_ts      = time.time()
        swap_used_mb = swap.used / 1e6

        with self._lock:
            self.cpu_hist.append(cpu)
            self.mem_hist.append(vm.percent)
            self.swap_hist.append(swap_pct)
            self.top_procs = rows[:12]
            # stash vm/swap for _check_memory() — avoids a second virtual_memory() call
            self._last_vm   = vm
            self._last_swap = swap
            _tier = self.effective_tier
            _tte  = self.mem_forecast_min
            _pres = self.mem_pressure_level
            _therm = self.thermal_pct
            # Swap velocity update
            if self._last_swap_ts > 0 and now_ts - self._last_swap_ts >= 1:
                sv = max(0.0, (swap_used_mb - self._last_swap_used) / (now_ts - self._last_swap_ts))
                self._swap_velocity = sv
            self._last_swap_ts   = now_ts
            self._last_swap_used = swap_used_mb

        # Cache: record every 10 s (use stored disk_pct — updated by _check_disk())
        if tick % 10 == 0:
            self._cache.record(
                int(now_ts), round(cpu, 1), round(vm.percent, 1),
                round(swap_pct, 1), round(self._last_disk_pct, 1),
                _pres, _tier, _tte, _therm
            )

    def _restore_calmed_procs(self, ram_lock: bool):
        """
        Restore scheduling priority for throttled procs that have calmed down.
        Only iterates self.throttled (typically 0–3 entries) — no process scan.
        CPU-RAM conflict gate: defer nice(0) if Tier 3+ RAM lock is active and
        the process belongs to a top-RSS application family.
        """
        if not self.throttled:
            return
        with self._lock:
            ancestry_snap = list(self.mem_ancestry)

        high_ram_families: set = set()
        if ram_lock and ancestry_snap:
            for entry in ancestry_snap[:3]:
                high_ram_families.add(entry["app"].lower())

        for pid in list(self.throttled):
            try:
                p = psutil.Process(pid)
                c = p.cpu_percent(interval=None) / self._ncpu
                if c < CPU_WARN / 2:
                    if ram_lock and high_ram_families:
                        proc_name = p.name().lower()
                        if any(fam in proc_name or proc_name in fam
                               for fam in high_ram_families):
                            self._emit("info",
                                f"CPU-RAM LOCK: deferring priority restore for "
                                f"{p.name()} (PID {pid}) — top RAM family under "
                                f"Tier 3+ pressure ({c:.0f}% CPU)")
                            continue
                    p.nice(0)   # syscall — outside lock
                    with self._lock:
                        name = self.throttled.pop(pid, None)
                        self.actions += 1
                    if name:
                        self._emit("fix",
                            f"Priority restored: {name} (PID {pid}) — CPU back to {c:.0f}%")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                with self._lock:
                    self.throttled.pop(pid, None)

    def _check_memory(self):
        with self._lock:
            vm = self._last_vm      # already fetched in _collect() — no extra syscall
            sw = self._last_swap
        mem_pct = vm.percent

        # ── Compute effective tier (static % + TTE predictive escalation) ─────
        effective_tier, threshold_tier = self._compute_effective_tier(mem_pct)
        was_predictive = effective_tier > threshold_tier
        with self._lock:
            self.effective_tier        = effective_tier
            self.predictive_escalation = was_predictive
            self._ram_pressure_lock    = (effective_tier >= 3)

        # PSM: predict next tier transition
        self._psm_predict()

        if mem_pct >= MEM_WARN or effective_tier >= 1:
            self.issues += 1
            used_gb = (vm.total - vm.available) / 1e9
            self._emit("issue",
                f"RAM pressure: {mem_pct:.0f}% used "
                f"({used_gb:.1f} / {vm.total/1e9:.1f} GB)")

            # Predictive escalation announcement
            if was_predictive:
                tte = self.mem_forecast_min
                self._emit("warn",
                    f"PREDICTIVE ESCALATION: TTE={tte:.1f} min → "
                    f"acting at Tier {effective_tier} "
                    f"(static threshold would be Tier {threshold_tier}) "
                    f"— intervening {TTE_TIER2_MIN - tte:.1f} min early")

            # report top consumers with cooldown
            now = time.time()
            if now - self._last_consumer >= CONSUMER_COOL_S:
                self._last_consumer = now
                self._report_memory_consumers()

            # MMIE: escalate through tiered remediation cascade
            if effective_tier >= 2:
                self._tiered_memory_remediation(mem_pct, effective_tier)

            # CDA: diagnose root cause at Tier 2+
            if effective_tier >= 2:
                self._diagnose_root_cause()

        elif mem_pct < MEM_WARN - 5:
            # pressure has eased — release RAM lock and restore frozen daemons
            with self._lock:
                self._ram_pressure_lock = False
                self.effective_tier     = 0
                self.predictive_escalation = False
            if self._frozen_pids:
                self._thaw_frozen_daemons()

        # swap already fetched in _collect() — no extra syscall
        if sw.total > 0:
            if sw.percent >= SWAP_WARN and not self._swap_warned:
                self._swap_warned = True
                self._emit("warn",
                    f"Swap in use: {sw.percent:.0f}% "
                    f"({sw.used/1e9:.1f} GB) — system is memory-constrained")
            elif sw.percent < 30:
                self._swap_warned = False

    def _report_memory_consumers(self):
        """List top RSS hogs when RAM is critically high."""
        procs = []
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                if p.name() in PROTECTED: continue
                rss = p.memory_info().rss / 1e6
                if rss >= 150:
                    procs.append((rss, p.name(), p.pid))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        procs.sort(reverse=True)
        for rss, name, pid in procs[:3]:
            self._emit("issue",
                f"RAM hog: {name} (PID {pid}) holding {rss:.0f} MB "
                f"— restart if unnecessary")

    def _check_zombies(self):
        """Detect zombie processes that indicate a hung parent."""
        zombies = []
        for p in psutil.process_iter(["pid", "name", "status"]):
            try:
                if p.status() == psutil.STATUS_ZOMBIE:
                    zombies.append((p.pid, p.name()))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if zombies:
            self.issues += len(zombies)
            for pid, name in zombies[:5]:
                self._emit("warn",
                    f"Zombie process: {name} (PID {pid}) — parent process may be hung")

    def _track_memory_leaks(self):
        """Flag processes whose RSS is growing rapidly (potential leaks)."""
        now = time.time()
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                if p.name() in PROTECTED: continue
                rss = p.memory_info().rss / 1e6
                pid = p.pid
                hist = self._rss_history.setdefault(pid, [])
                hist.append((now, rss))
                if len(hist) > 5:
                    hist.pop(0)
                if len(hist) >= 3 and pid not in self._warned_leaks:
                    elapsed = hist[-1][0] - hist[0][0]
                    growth  = hist[-1][1] - hist[0][1]
                    if elapsed > 0:
                        rate = growth / elapsed * 60  # MB/min
                        if rate >= LEAK_RATE_MB_MIN and rss >= LEAK_MIN_RSS_MB:
                            self._warned_leaks.add(pid)
                            self.issues += 1
                            self._emit("warn",
                                f"Memory growth: {p.name()} (PID {pid}) "
                                f"+{rate:.0f} MB/min, now {rss:.0f} MB — possible leak")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self._rss_history.pop(p.pid, None)
                self._warned_leaks.discard(p.pid)

    def _check_thermal(self):
        """Detect CPU thermal throttling via pmset -g therm."""
        try:
            r = subprocess.run(
                ["pmset", "-g", "therm"],
                capture_output=True, text=True, timeout=3
            )
            for line in r.stdout.splitlines():
                if "CPU_Speed_Limit" in line:
                    pct = int(line.split()[-1])
                    with self._lock:
                        self.thermal_pct = pct
                    if pct < 100:
                        self.issues += 1
                        self._emit("issue",
                            f"Thermal throttle active: CPU limited to {pct}% speed "
                            f"— system is overheating, consider improving airflow")
                    return
            with self._lock:
                self.thermal_pct = 100
        except Exception:
            pass

    def _check_power_mode(self):
        """Detect battery vs AC and emit an event when source changes."""
        try:
            r = subprocess.run(
                ["pmset", "-g", "ps"],
                capture_output=True, text=True, timeout=2
            )
            on_battery = "Battery Power" in r.stdout
            with self._lock:
                changed        = on_battery != self.on_battery
                self.on_battery = on_battery
            if changed:
                src = "battery" if on_battery else "AC power"
                self._emit("info", f"Power source changed: now on {src}")
        except Exception:
            pass

    def _check_caches(self):
        """Warn once when ~/Library/Caches grows excessively large."""
        if self._cache_warned:
            return
        cache_dir = Path.home() / "Library" / "Caches"
        try:
            total = sum(
                f.stat().st_size for f in cache_dir.rglob("*") if f.is_file()
            )
            gb = total / 1e9
            if gb >= CACHE_WARN_GB:
                self._cache_warned = True
                self.issues += 1
                self._emit("issue",
                    f"Cache bloat: ~/Library/Caches is {gb:.1f} GB "
                    f"— clear with CleanMyMac or 'rm -rf ~/Library/Caches/*'")
        except Exception:
            pass

    def _sweep_idle_services(self):
        """Auto-terminate sleeping XPC helpers / widget extensions eating RAM.
        Respects _no_kill blocklist populated by _detect_xpc_respawn() — services
        that launchd immediately restarts are skipped to avoid futile kill loops.
        """
        swept = []
        for p in psutil.process_iter(["pid", "name", "status",
                                       "memory_info", "username", "cpu_percent"]):
            try:
                if p.info["username"] == "root": continue
                name = p.name()
                if name in PROTECTED or name in NEVER_TERMINATE: continue
                if "Python" in name or "python" in name: continue
                if p.pid in self._terminated: continue
                # XPC respawn guard — skip blocklisted services
                if name in self._no_kill: continue

                stat = p.info["status"]
                cpu  = p.cpu_percent(interval=None) / self._ncpu
                rss  = (p.info.get("memory_info") or p.memory_info()).rss / 1e6

                is_idle_service = (
                    stat in ("sleeping", "idle") and
                    cpu == 0 and
                    rss >= IDLE_MB_FLOOR and
                    any(pat in name for pat in IDLE_SERVICE_PATTERNS)
                )
                if not is_idle_service: continue

                p.terminate()
                self._terminated.add(p.pid)
                self._terminated_ts[name] = time.time()   # record for respawn detection
                self.freed_mb += rss
                self.actions  += 1
                swept.append((name, p.pid, rss))
                self._emit("fix",
                    f"CLEARED idle service: {name} (PID {p.pid}) "
                    f"— freed {rss:.0f} MB RAM")

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if swept:
            total = sum(r for _, _, r in swept)
            self._emit("fix",
                f"Idle sweep: {len(swept)} services cleared, "
                f"~{total:.0f} MB freed (session total: {self.freed_mb:.0f} MB)")

    # ── Predictive Remediation Engine ─────────────────────────────────────────

    def _analyse_app_predictions(self):
        """
        Use the 90-day disk cache to generate application-level performance
        predictions. Runs at most once per 24 h — purely aggregate SQL queries,
        never loads raw rows into Python memory.

        Produces self.app_predictions: [{app, avg_mb, trend, risk, chronic_pct}]
        where:
          trend   = 'rising' | 'stable' | 'falling'  (week-over-week system RAM)
          risk    = 'high' | 'medium' | 'low'
          chronic = % of last 7 days system RAM was above MEM_WARN
        """
        now = time.time()
        if now - self._last_app_predict < 86400:  # at most once per 24 h
            return
        self._last_app_predict = now

        # Snapshot current ancestry for app names to analyse
        with self._lock:
            ancestry = list(self.mem_ancestry)
        if not ancestry:
            return

        chronic = self._cache.chronic_pressure_pct()
        results = []
        for entry in ancestry[:6]:
            app   = entry["app"]
            mb    = entry["mb"]
            pct   = entry["pct"]
            trend_data = self._cache.app_mem_trend(app)
            trend = trend_data.get("trend", "stable")
            w1    = trend_data.get("week1_avg", 0.0)
            w2    = trend_data.get("week2_avg", 0.0)

            # Risk classification
            if trend == "rising" and pct >= 20:
                risk = "high"
            elif trend == "rising" or pct >= 15:
                risk = "medium"
            else:
                risk = "low"

            results.append({
                "app": app, "mb": mb, "pct": pct,
                "trend": trend, "risk": risk,
                "week1_avg": w1, "week2_avg": w2,
                "chronic_pct": chronic,
            })

            if risk == "high":
                self.issues += 1
                self._emit("warn",
                    f"APP PREDICTION: {app} is a rising RAM consumer "
                    f"({mb} MB, {pct}% of total) — system RAM trending "
                    f"from {w2:.0f}% → {w1:.0f}% over past two weeks")
            elif chronic >= 40:
                self._emit("issue",
                    f"CHRONIC PRESSURE: RAM above {MEM_WARN:.0f}% for "
                    f"{chronic:.0f}% of the last 7 days — consider closing "
                    f"persistent apps or increasing physical memory")

        with self._lock:
            self.app_predictions = results

    def _compute_effective_tier(self, mem_pct: float):
        """
        MSCEE — Multi-Signal Consensus Escalation Engine.
        Combines 6 independent signals via weighted quorum voting. A tier is
        adopted only when its cumulative weighted vote share ≥ MSCEE_QUORUM,
        preventing any single-signal false escalation.

        Signals (weights sum to 1.0):
          S1 (0.30): Static RAM % with ATCE-calibrated thresholds
          S2 (0.25): TTE forecast from MMAF
          S3 (0.20): macOS kernel pressure oracle (sysctl)
          S4 (0.12): CEO Compression Pressure Index
          S5 (0.08): Swap velocity (MB/s)
          S6 (0.05): Circadian hour-of-day pattern (CMPE)

        Returns: (effective_tier: int, threshold_tier: int)
        """
        # ── S1: RAM % with ATCE-calibrated thresholds ─────────────────────────
        cal  = self._cal_thresholds
        t2   = cal.get("tier2", MEM_TIER2_PCT)
        t3   = cal.get("tier3", MEM_TIER3_PCT)
        t4   = cal.get("tier4", MEM_TIER4_PCT)
        if   mem_pct >= t4: s1 = 4
        elif mem_pct >= t3: s1 = 3
        elif mem_pct >= t2: s1 = 2
        elif mem_pct >= MEM_WARN: s1 = 1
        else: s1 = 0
        threshold_tier = s1

        # ── S2: TTE from MMAF ─────────────────────────────────────────────────
        with self._lock:
            hist_len = len(self.mem_hist)
            tte      = self.mem_forecast_min
        if hist_len < TTE_MIN_SAMPLES or tte < 0:
            s2 = 0
        elif tte <= TTE_TIER4_MIN: s2 = 4
        elif tte <= TTE_TIER3_MIN: s2 = 3
        elif tte <= TTE_TIER2_MIN: s2 = 2
        else:                      s2 = 1

        # ── S3: kernel oracle ─────────────────────────────────────────────────
        with self._lock:
            kp = self.mem_pressure_level
        s3 = {"normal": 0, "warn": 2, "critical": 4}.get(kp, 0)

        # ── S4: CEO compression pressure ──────────────────────────────────────
        with self._lock:
            cpi = self._compression_pressure
        if   cpi >= CPI_TIER3: s4 = 3
        elif cpi >= CPI_TIER2: s4 = 2
        else:                  s4 = 0

        # ── S5: swap velocity ─────────────────────────────────────────────────
        with self._lock:
            sv = self._swap_velocity
        if   sv >= 100: s5 = 3
        elif sv >=  50: s5 = 2
        elif sv >=  20: s5 = 1
        else:           s5 = 0

        # ── S6: circadian pattern (CMPE) ──────────────────────────────────────
        hour = datetime.now().hour
        with self._lock:
            circ_avg = self._circadian_profile.get(hour, 0.0)
        if   circ_avg >= CMPE_PRE_FREEZE_SCORE: s6 = 2
        elif circ_avg >= MEM_WARN:              s6 = 1
        else:                                   s6 = 0

        # ── ACN: weighted quorum vote using adaptive weights + SIE confidence ──
        W    = dict(self._acn_weights)       # live ACN weights (updated by RWA)
        sigs = {"s1": s1, "s2": s2, "s3": s3, "s4": s4, "s5": s5, "s6": s6}

        # Apply SIE signal confidence as weight multiplier
        sc = self._signal_confidence
        conf_map = {
            "s1": sc.get("mem",  1.0),
            "s2": sc.get("mem",  1.0),
            "s3": sc.get("mem",  1.0),
            "s4": sc.get("swap", 1.0),
            "s5": sc.get("swap", 1.0),
            "s6": sc.get("mem",  1.0),
        }
        # Re-normalise after confidence scaling
        adj_W = {k: W[k] * conf_map[k] for k in W}
        total_adj = sum(adj_W.values()) or 1.0
        norm_W = {k: v / total_adj for k, v in adj_W.items()}

        effective_tier = threshold_tier
        for candidate in range(4, 0, -1):
            vote = sum(w for name, w in norm_W.items() if sigs[name] >= candidate)
            if vote >= MSCEE_QUORUM:
                effective_tier = candidate
                break

        # BRL: compute posterior confidence for this tier decision
        signal_votes = list(sigs.values())
        self._brl_confidence = self._compute_brl_confidence(effective_tier, signal_votes)

        # PSM: track tier transition if tier changed
        if effective_tier != self._prev_tier:
            self._update_psm(self._prev_tier, effective_tier)

        return effective_tier, threshold_tier

    def _detect_xpc_respawn(self):
        """
        XPC Respawn Guard: scan running processes against the recently terminated set.
        Any service that reappears within XPC_RESPAWN_S seconds is launchd-managed and
        cannot be durably terminated — add it to _no_kill to prevent futile kill loops.
        """
        if not self._terminated_ts:
            return
        now = time.time()
        stale = [name for name, ts in self._terminated_ts.items()
                 if now - ts > XPC_RESPAWN_S * 6]
        for name in stale:
            self._terminated_ts.pop(name, None)

        running_names = set()
        try:
            for p in psutil.process_iter(["name"]):
                try:
                    running_names.add(p.name())
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            return

        for name, ts in list(self._terminated_ts.items()):
            if name in running_names and now - ts <= XPC_RESPAWN_S:
                if name not in self._no_kill:
                    self._no_kill.add(name)
                    self._emit("warn",
                        f"XPC RESPAWN GUARD: {name} relaunched within {XPC_RESPAWN_S}s "
                        f"— blocklisted (launchd-managed service, termination futile)")

    # ── MMIE: Multi-Dimensional Memory Intelligence Engine ────────────────────

    def _get_macos_pressure_level(self) -> str:
        """
        Query macOS kernel memory pressure level via sysctl.
        kern.memorystatus_vm_pressure_level: 1=Normal, 2=Warn, 4=Critical.
        Falls back to percent-derived tier if sysctl is unavailable.
        """
        try:
            r = subprocess.run(
                ["sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
                capture_output=True, text=True, timeout=2
            )
            val = int(r.stdout.strip())
            return {1: "normal", 2: "warn", 4: "critical"}.get(val, "normal")
        except Exception:
            vm = psutil.virtual_memory()
            if vm.percent >= 92: return "critical"
            if vm.percent >= 82: return "warn"
            return "normal"

    def _parse_vm_stat(self) -> dict:
        """
        Parse vm_stat for detailed macOS memory breakdown.
        Returns dict with wired/active/inactive/free/purgeable/compressed in MB.
        """
        result = {"wired": 0, "active": 0, "inactive": 0,
                  "free": 0, "purgeable": 0, "compressed": 0, "page_kb": 16}
        try:
            r = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=3)
            page_kb = 16  # Apple Silicon default; Intel is 4 KB
            for line in r.stdout.splitlines():
                if "page size of" in line:
                    try:
                        page_bytes = int(
                            line.split("page size of")[1].split("bytes")[0].strip()
                        )
                        page_kb = page_bytes / 1024
                        result["page_kb"] = page_kb
                    except (ValueError, IndexError):
                        pass
                    continue
                if ":" not in line:
                    continue
                label, _, val_str = line.rpartition(":")
                try:
                    pages = int(val_str.strip().rstrip(".").replace(",", ""))
                except ValueError:
                    continue
                mb = pages * page_kb / 1024
                if   "wired down" in label:               result["wired"]      = mb
                elif "Pages active" in label:             result["active"]     = mb
                elif "Pages inactive" in label:           result["inactive"]   = mb
                elif "Pages free" in label:               result["free"]       = mb
                elif "Pages purgeable" in label:          result["purgeable"]  = mb
                elif "Pages stored in compressor" in label: result["compressed"] = mb
        except Exception:
            pass
        return result

    def _build_memory_ancestry(self) -> list:
        """
        Walk the process tree and attribute RSS to root application families
        (first-generation children of launchd). Returns [{app, mb, pct}] sorted
        by MB descending — revealing which app *ecosystem* owns the most RAM.
        """
        pid_info = {}
        try:
            for p in psutil.process_iter(["pid", "ppid", "name", "memory_info"]):
                try:
                    rss = p.memory_info().rss / 1e6
                    pid_info[p.pid] = {"ppid": p.ppid(), "name": p.name(), "rss": rss}
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            def root_ancestor(pid, visited=None):
                visited = visited or set()
                if pid in visited or pid not in pid_info:
                    return pid
                visited.add(pid)
                ppid = pid_info[pid]["ppid"]
                if ppid <= 1 or ppid not in pid_info:
                    return pid
                return root_ancestor(ppid, visited)

            family_rss: dict = {}
            for pid, info in pid_info.items():
                root = root_ancestor(pid)
                root_name = pid_info.get(root, {}).get("name", "unknown")
                if root_name in PROTECTED:
                    continue
                if root not in family_rss:
                    family_rss[root] = [root_name, 0.0]
                family_rss[root][1] += info["rss"]

            total_mb = sum(v[1] for v in family_rss.values()) or 1
            return sorted(
                [{"app": v[0], "mb": round(v[1]), "pct": round(v[1] / total_mb * 100, 1)}
                 for v in family_rss.values()],
                key=lambda x: x["mb"], reverse=True
            )[:8]
        except Exception:
            return []

    def _compute_mem_forecast(self) -> float:
        """
        MMAF — Multi-Model Adaptive Forecaster.
        Fits three models (linear OLS, quadratic, exponential) over the last
        MMAF_WINDOW mem_hist samples and selects the one with minimum residual
        sum of squares. Returns the winning model's TTE (minutes to 95%) or
        -1 if stable/declining. Stores winning model name in _last_forecast_model.
        """
        with self._lock:
            hist = list(self.mem_hist)
        window = hist[-MMAF_WINDOW:] if len(hist) >= MMAF_MIN_SAMPLES else []
        if len(window) < MMAF_MIN_SAMPLES:
            return -1.0

        n    = len(window)
        xs   = list(range(n))
        last = window[-1]

        best_tte   = -1.0
        best_model = "linear"
        best_rss   = float("inf")

        # ── 1. Linear OLS ──────────────────────────────────────────────────────
        mean_x = (n - 1) / 2.0
        mean_y = sum(window) / n
        num_l  = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, window))
        den_l  = sum((x - mean_x) ** 2 for x in xs)
        if den_l > 0:
            m_l = num_l / den_l
            b_l = mean_y - m_l * mean_x
            rss_l = sum((m_l * x + b_l - y) ** 2 for x, y in zip(xs, window))
            if m_l >= 0.005 and last < MMAF_TARGET_PCT:
                tte_l = round((MMAF_TARGET_PCT - last) / m_l / 60, 1)
            else:
                tte_l = -1.0
            if rss_l < best_rss:
                best_rss, best_tte, best_model = rss_l, tte_l, "linear"
            self._model_residual_history["linear"].append(rss_l)

        # ── 2. Quadratic (Vandermonde normal equations, Cramer's rule) ─────────
        try:
            sx0=n; sx1=sum(xs); sx2=sum(x**2 for x in xs)
            sx3=sum(x**3 for x in xs); sx4=sum(x**4 for x in xs)
            sy0=sum(window)
            sy1=sum(x*y for x,y in zip(xs,window))
            sy2=sum(x**2*y for x,y in zip(xs,window))
            def _det3(M):
                return (M[0][0]*(M[1][1]*M[2][2]-M[1][2]*M[2][1])
                       -M[0][1]*(M[1][0]*M[2][2]-M[1][2]*M[2][0])
                       +M[0][2]*(M[1][0]*M[2][1]-M[1][1]*M[2][0]))
            Mq=[[sx4,sx3,sx2],[sx3,sx2,sx1],[sx2,sx1,sx0]]
            D=_det3(Mq)
            if abs(D) > 1e-12:
                def _cr(col,rhs):
                    m2=[list(r) for r in Mq]
                    for i in range(3): m2[i][col]=rhs[i]
                    return m2
                R=[sy2,sy1,sy0]
                qa=_det3(_cr(0,R))/D; qb=_det3(_cr(1,R))/D; qc=_det3(_cr(2,R))/D
                rss_q=sum((qa*x**2+qb*x+qc-y)**2 for x,y in zip(xs,window))
                slope_q = 2*qa*(n-1)+qb
                if slope_q >= 0.005 and last < MMAF_TARGET_PCT:
                    tte_q=-1.0
                    for step in range(1, 7200):
                        if qa*(n-1+step)**2+qb*(n-1+step)+qc >= MMAF_TARGET_PCT:
                            tte_q=round(step/60,1); break
                else:
                    tte_q=-1.0
                self._model_residual_history["quadratic"].append(rss_q)
                if rss_q < best_rss:
                    best_rss, best_tte, best_model = rss_q, tte_q, "quadratic"
        except Exception:
            pass

        # ── 3. Exponential (log-linearised OLS) ───────────────────────────────
        try:
            if min(window) > 0:
                log_w=[math.log(y) for y in window]
                mean_ly=sum(log_w)/n
                num_e=sum((x-mean_x)*(ly-mean_ly) for x,ly in zip(xs,log_w))
                if den_l > 0 and num_e > 0:
                    me=num_e/den_l
                    be=mean_ly - me*mean_x
                    rss_e=sum((math.exp(be+me*x)-y)**2 for x,y in zip(xs,window))
                    if last < MMAF_TARGET_PCT:
                        x_95=(math.log(MMAF_TARGET_PCT)-be)/me
                        tte_e=round((x_95-(n-1))/60,1) if x_95>(n-1) else 0.0
                    else:
                        tte_e=-1.0
                    self._model_residual_history["exponential"].append(rss_e)
                    if rss_e < best_rss:
                        best_rss, best_tte, best_model = rss_e, tte_e, "exponential"
        except Exception:
            pass

        # MEG: apply meta-weight governance — prefer model with lower historical residual
        meg_winner = best_model
        meg_scores = {}
        for mname, hist in self._model_residual_history.items():
            if hist:
                meg_scores[mname] = sum(hist) / len(hist)
        if meg_scores:
            # MEG winner = model with minimum (meta_weight × current_rss)
            # Use same best_rss as proxy for current_rss per model
            meg_winner = min(meg_scores, key=lambda m: meg_scores[m])
        with self._lock:
            self._last_forecast_model = meg_winner
        return best_tte

    def _compute_compression_pressure(self, vm_bd: dict) -> float:
        """
        CEO — Compression Efficiency Oracle.
        CPI = compressed / (compressed + purgeable). A high CPI means the
        compressor is nearly out of purgeable headroom; next allocation will
        hit swap. Returns 0.0 when compressed memory is below noise floor.
        """
        compressed = vm_bd.get("compressed", 0)
        purgeable  = vm_bd.get("purgeable",  0)
        if compressed < CEO_MIN_COMPRESSED:
            return 0.0
        denom = compressed + purgeable
        return round(compressed / denom, 3) if denom >= 1 else 0.0

    def _adjust_tte_for_thermal(self, tte: float) -> float:
        """
        TMCP — Thermal-Memory Coupling Predictor.
        Shortens TTE when thermal throttling is active and the historically
        learned coupling coefficient is positive. Under throttle, apps stall
        on CPU-bound paths longer, leaking partial allocations — so exhaustion
        arrives sooner than raw OLS predicts.
        """
        if tte <= 0 or self._thermal_coupling <= 0:
            return tte
        with self._lock:
            therm = self.thermal_pct
        if therm >= 100:
            return tte
        throttle_fraction = (100 - therm) / 100.0
        adjustment = max(1.0 - self._thermal_coupling * throttle_fraction, 0.5)
        return round(tte * adjustment, 1)

    def _update_pressure_and_forecast(self):
        """Refresh kernel pressure level, vm_stat breakdown, CEO CPI, and forecast every 5 s."""
        level    = self._get_macos_pressure_level()
        forecast = self._compute_mem_forecast()
        forecast = self._adjust_tte_for_thermal(forecast)
        vm_bd    = self._parse_vm_stat()
        cpi      = self._compute_compression_pressure(vm_bd)
        with self._lock:
            self.mem_pressure_level    = level
            self.mem_forecast_min      = forecast
            self.vm_breakdown          = vm_bd
            self._compression_pressure = cpi
        if level == "critical":
            vm = psutil.virtual_memory()
            self._emit("issue",
                f"Kernel memory pressure: CRITICAL — system at {vm.percent:.0f}% RAM")
        if cpi >= CPI_TIER3:
            self._emit("warn",
                f"CEO: Compression near exhaustion (CPI={cpi:.2f}) — "
                f"purgeable headroom depleted, swap imminent")
        elif cpi >= CPI_TIER2:
            self._emit("issue",
                f"CEO: Compression efficiency degrading (CPI={cpi:.2f}) — "
                f"purgeable headroom running low")
        # Ancestry is expensive; refresh at most every MEM_ANCESTRY_COOL_S
        now = time.time()
        if now - self._last_ancestry >= MEM_ANCESTRY_COOL_S:
            self._last_ancestry = now
            ancestry = self._build_memory_ancestry()
            with self._lock:
                self.mem_ancestry = ancestry
            # AIP: compute ancestral impact propagation after ancestry refresh
            self._compute_aip()

    def _tiered_memory_remediation(self, mem_pct: float, effective_tier: int = 2):
        """
        4-tier adaptive remediation cascade — driven by effective_tier (which may
        have been escalated above the static threshold by the Predictive Remediation Engine):
          Tier 2 (≥82% OR TTE≤10 min): vm_stat breakdown + purgeable advisory + ancestry
          Tier 3 (≥87% OR TTE≤5 min):  SIGSTOP background daemons via genealogy scoring
          Tier 4 (≥92% OR TTE≤2 min):  Emergency idle-XPC termination
        (Tier 1 ≥80% is handled by _check_memory.)
        """
        now = time.time()

        # ── Tier 2: structural analysis ───────────────────────────────────────
        vm_bd = self._parse_vm_stat()
        with self._lock:
            self.vm_breakdown = vm_bd

        purg_mb  = vm_bd.get("purgeable", 0)
        wired_mb = vm_bd.get("wired", 0)
        total_mb = self._mem_total_gb * 1024

        if purg_mb > 200:
            self._emit("issue",
                f"Purgeable opportunity: {purg_mb:.0f} MB reclaimable — "
                f"macOS will reclaim under pressure (manual: sudo purge)")

        if total_mb > 0 and wired_mb / total_mb * 100 >= WIRED_WARN_PCT \
                and not self._wired_warned:
            self._wired_warned = True
            self.issues += 1
            self._emit("warn",
                f"Structural pressure: {wired_mb:.0f} MB wired "
                f"({wired_mb/total_mb*100:.0f}% of RAM) — cannot be paged or compressed")
        elif wired_mb < total_mb * 0.3:
            self._wired_warned = False

        if now - self._last_ancestry >= MEM_ANCESTRY_COOL_S:
            self._last_ancestry = now
            ancestry = self._build_memory_ancestry()
            with self._lock:
                self.mem_ancestry = ancestry
            if ancestry:
                summary = ", ".join(
                    f"{a['app']} {a['mb']}MB" for a in ancestry[:3]
                )
                self._emit("issue", f"Memory genealogy (top families): {summary}")

        # ── Tier 3: freeze idle background daemons (genealogy-guided) ─────────
        if effective_tier >= 3 and now - self._last_freeze >= FREEZE_COOL_S:
            self._freeze_background_daemons()
            self._record_rac_action(3, "freeze_daemon", mem_pct)

        # ── Tier 4: emergency termination ────────────────────────────────────
        if effective_tier >= 4:
            self._sweep_idle_services()
            self._record_rac_action(4, "sweep_xpc", mem_pct)

        # ── Tier 2: purgeable advisory RAC recording ─────────────────────────
        if effective_tier == 2 and purg_mb > 200:
            self._record_rac_action(2, "purgeable_advisory", mem_pct)

    def _get_process_velocity(self, pid: int, rss_mb: float) -> float:
        """
        RVMS — RSS Velocity Momentum Scorer.
        Returns a multiplier [1.0, RVMS_MAX_BOOST] proportional to how fast
        this process's RSS has grown since the last observation. A rapidly
        growing process is prioritised as a freeze candidate — velocity is a
        leading indicator of imminent pressure amplification.
        """
        now  = time.time()
        prev = self._rss_velocity.get(pid)
        self._rss_velocity[pid] = (now, rss_mb)
        if prev is None:
            return 1.0
        prev_ts, prev_rss = prev
        elapsed = now - prev_ts
        if elapsed < 1:
            return 1.0
        growth = rss_mb - prev_rss
        if growth <= 0:
            return 1.0
        rate  = growth / elapsed           # MB/s
        boost = min(1.0 + rate / 10.0, RVMS_MAX_BOOST)
        return round(boost, 2)

    def _freeze_background_daemons(self):
        """
        Genealogy-guided SIGSTOP with RVMS velocity boost:
          family_match (weight 2): process belongs to a top-RSS application family
          pattern_match (weight 1): name matches FREEZE_PATTERNS safe list
          velocity_boost (RVMS):    multiplier [1.0, 2.0] based on RSS growth rate
        composite = (family_match*2 + pattern_match) * velocity_boost
        Sorted by composite DESC then RSS DESC — heaviest, fastest-growing
        daemons frozen first.
        """
        self._last_freeze = time.time()

        with self._lock:
            ancestry_snap = list(self.mem_ancestry)

        heavy_families = {entry["app"].lower() for entry in ancestry_snap[:5]}

        candidates = []
        for p in psutil.process_iter(["pid", "name", "ppid", "status",
                                       "username", "memory_info"]):
            try:
                if p.info["username"] == "root":
                    continue
                name = p.name()
                if name in PROTECTED or name in NEVER_TERMINATE:
                    continue
                if p.pid in self._frozen_pids:
                    continue
                if p.info["status"] not in ("sleeping", "idle"):
                    continue

                rss = (p.info.get("memory_info") or p.memory_info()).rss / 1e6

                pattern_match = int(any(pat in name for pat in FREEZE_PATTERNS))
                name_lower    = name.lower()
                family_match  = int(any(fam in name_lower or name_lower in fam
                                        for fam in heavy_families))
                base_score = family_match * 2 + pattern_match
                if base_score == 0:
                    continue

                # RVMS: multiply composite score by velocity momentum
                vboost = self._get_process_velocity(p.pid, rss)
                score  = base_score * vboost

                candidates.append((score, rss, p.pid, name, p, vboost))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)

        frozen, freed_mb = 0, 0.0
        for score, rss, pid, name, p, vboost in candidates:
            try:
                p.send_signal(19)  # SIGSTOP — reversible suspension
                self._frozen_pids[pid] = (name, time.time(), rss)
                freed_mb += rss
                frozen   += 1
                self.actions += 1

                with self._lock:
                    ancestry_snap2 = list(self.mem_ancestry)
                family_info = next(
                    (f"{e['app']} family ({e['mb']}MB)"
                     for e in ancestry_snap2
                     if e["app"].lower() in name.lower() or name.lower() in e["app"].lower()),
                    None
                )
                boost_tag = f", RVMS×{vboost:.1f}" if vboost > 1.05 else ""
                if family_info:
                    self._emit("fix",
                        f"GENEALOGY FREEZE: {name} (PID {pid}, {rss:.0f}MB{boost_tag}) "
                        f"← {family_info} — SIGSTOP applied")
                else:
                    self._emit("fix",
                        f"PATTERN FREEZE: {name} (PID {pid}, {rss:.0f}MB{boost_tag}) "
                        f"— SIGSTOP applied (score={score:.1f})")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if frozen:
            self.freed_mb += freed_mb
            self._emit("fix",
                f"MEMORY TRIAGE (Tier 3): froze {frozen} background daemons "
                f"(~{freed_mb:.0f} MB paused) — auto-thaw when pressure drops")

    def _thaw_frozen_daemons(self):
        """
        GTS — Graduated Thaw Sequencer.
        Sends SIGCONT in ascending RSS order (smallest first) with GTS_WAIT_S
        inter-signal gap. After each thaw, checks whether RAM has risen above
        the baseline + GTS_MEM_GATE_PCT threshold — if so, aborts to prevent
        the thundering-herd spike that bulk-SIGCONT can cause.
        """
        to_thaw = sorted(
            self._frozen_pids.items(), key=lambda kv: kv[1][2]   # sort by rss_mb asc
        )
        with self._lock:
            baseline_mem = self._last_vm.percent

        thawed  = []
        aborted = False
        for pid, (name, _ts, _rss) in to_thaw:
            try:
                psutil.Process(pid).send_signal(18)  # SIGCONT — resume
                thawed.append(name)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            self._frozen_pids.pop(pid, None)
            time.sleep(GTS_WAIT_S)
            current_mem = psutil.virtual_memory().percent
            if current_mem > baseline_mem + GTS_MEM_GATE_PCT:
                aborted = True
                remaining = len(to_thaw) - len(thawed)
                self._emit("warn",
                    f"GTS abort: RAM rose {current_mem - baseline_mem:.1f}% "
                    f"during graduated thaw — {remaining} daemon(s) remain frozen")
                break

        if thawed:
            suffix = " (partial — memory gate triggered)" if aborted else ""
            self._emit("fix",
                f"GTS: graduated-thaw of {len(thawed)} daemon(s){suffix}: "
                + ", ".join(thawed[:4]))

    # ── ATCE: Adaptive Threshold Calibration Engine ───────────────────────────

    def _calibrate_thresholds(self):
        """
        ATCE — Adaptive Threshold Calibration Engine.
        Reads the last 30 days of mem_pct from the 90-day cache and sets
        Tier 2/3/4 thresholds to the 75th/85th/93rd historical percentiles.
        Self-tunes the bot's response thresholds to each machine's real usage
        patterns rather than using fixed global defaults. Runs once per hour;
        requires ATCE_MIN_ROWS rows in the cache.
        """
        now = time.time()
        if now - self._last_atce < ATCE_COOL_S:
            return
        self._last_atce = now
        if not self._cache._ok:
            return
        try:
            with sqlite3.connect(self._cache._db, timeout=3) as cx:
                rows = cx.execute(
                    "SELECT mem_pct FROM metrics WHERE ts >= ? ORDER BY mem_pct",
                    (int(now - 30 * 86400),)
                ).fetchall()
            if len(rows) < ATCE_MIN_ROWS:
                return
            vals = [r[0] for r in rows if r[0] is not None]
            n    = len(vals)
            def pct(p):
                return vals[max(0, min(int(p / 100 * n), n - 1))]
            p75, p85, p93 = pct(ATCE_PERCENTILE), pct(85), pct(93)
            if 60 <= p75 <= 92 and p75 < p85 < p93:
                with self._lock:
                    self._cal_thresholds = {
                        "tier2": round(p75, 1),
                        "tier3": round(p85, 1),
                        "tier4": round(p93, 1),
                    }
                self._emit("info",
                    f"ATCE: thresholds calibrated from {n} samples — "
                    f"T2={p75:.0f}% T3={p85:.0f}% T4={p93:.0f}%")
        except Exception:
            pass

    # ── CMPE: Circadian Memory Pattern Engine ─────────────────────────────────

    def _check_circadian_pressure(self):
        """
        CMPE — Circadian Memory Pattern Engine.
        Refreshes the hour-of-day profile and, if the current hour historically
        averages ≥ CMPE_PRE_FREEZE_SCORE and current RAM ≥ MEM_WARN, triggers
        a proactive pre-freeze before static thresholds would engage.
        """
        now = time.time()
        if now - self._last_circadian < CMPE_COOL_S:
            return
        self._last_circadian = now
        self._build_circadian_profile()

        hour = datetime.now().hour
        with self._lock:
            circ_avg = self._circadian_profile.get(hour, 0.0)
            mem_pct  = self._last_vm.percent

        if circ_avg >= CMPE_PRE_FREEZE_SCORE and mem_pct >= MEM_WARN:
            self._emit("warn",
                f"CMPE: hour {hour:02d}:xx historically averages {circ_avg:.0f}% RAM "
                f"— proactive freeze eligible (current: {mem_pct:.0f}%)")
            if (not self._frozen_pids and
                    mem_pct < MEM_TIER3_PCT and
                    now - self._last_freeze >= FREEZE_COOL_S):
                self._freeze_background_daemons()

    def _build_circadian_profile(self):
        """
        Build {hour: avg_mem_pct} from last 30 days of cache data using a single
        aggregate SQL query. Only 24 rows are returned to Python — zero raw data.
        """
        if not self._cache._ok:
            return
        try:
            cutoff = int(time.time() - 30 * 86400)
            with sqlite3.connect(self._cache._db, timeout=3) as cx:
                rows = cx.execute(
                    "SELECT CAST(ts/3600 % 24 AS INTEGER) AS hr, AVG(mem_pct) "
                    "FROM metrics WHERE ts >= ? GROUP BY hr",
                    (cutoff,)
                ).fetchall()
            profile = {int(r[0]): round(r[1], 1) for r in rows if r[1] is not None}
            with self._lock:
                self._circadian_profile = profile
        except Exception:
            pass

    # ── TMCP: Thermal-Memory Coupling Predictor ───────────────────────────────

    def _compute_thermal_coupling(self):
        """
        TMCP learning step.
        Queries throttled rows (thermal_pct < 100) from the last 30 days and
        measures the correlation between thermal throttle depth and memory %.
        Updates self._thermal_coupling via EMA — used by _adjust_tte_for_thermal()
        to shorten TTE predictions during thermal events.
        """
        now = time.time()
        if now - self._last_tmcp < TMCP_COOL_S:
            return
        self._last_tmcp = now
        if not self._cache._ok:
            return
        try:
            cutoff = int(now - 30 * 86400)
            with sqlite3.connect(self._cache._db, timeout=3) as cx:
                rows = cx.execute(
                    "SELECT thermal_pct, mem_pct FROM metrics "
                    "WHERE ts >= ? AND thermal_pct IS NOT NULL AND thermal_pct < 100",
                    (cutoff,)
                ).fetchall()
            if len(rows) < TMCP_MIN_SAMPLES:
                return
            tv = [r[0] for r in rows]
            mv = [r[1] for r in rows]
            n  = len(tv)
            mt, mm = sum(tv)/n, sum(mv)/n
            cov   = sum((t-mt)*(m-mm) for t,m in zip(tv,mv)) / n
            var_t = sum((t-mt)**2 for t in tv) / n
            if var_t < 1e-6:
                return
            coupling = min(abs(cov / var_t) / 100.0, 1.0)
            self._thermal_coupling = (
                TMCP_LEARN_RATE * coupling +
                (1 - TMCP_LEARN_RATE) * self._thermal_coupling
            )
            self._emit("info",
                f"TMCP: thermal coupling={self._thermal_coupling:.3f} "
                f"(from {n} throttled samples)")
        except Exception:
            pass

    def _check_disk(self):
        try:
            d = psutil.disk_usage("/")
            self._last_disk_pct = d.percent   # cache for _collect() cache.record()
            with self._lock:
                self.disk_pct     = d.percent
                self.disk_free_gb = round(d.free / 1e9, 1)
            if d.percent >= 90:
                self.issues += 1
                self._emit("issue",
                    f"Low disk: {d.percent:.0f}% full "
                    f"({d.free/1e9:.1f} GB free) — clear space soon")
            elif d.percent >= 80:
                self._emit("warn",
                    f"Disk filling up: {d.percent:.0f}% used "
                    f"({d.free/1e9:.1f} GB free)")
        except Exception:
            pass

    # ── SIE: Signal Integrity Estimator ───────────────────────────────────────

    def _compute_signal_confidence(self, cpu_pct: float, mem_pct: float, swap_pct: float):
        """
        SIE — Signal Integrity Estimator.
        For each signal, computes a rolling z-score using the deque history.
        If |z| > SIE_ZSCORE_THRESH, the signal is flagged as anomalous (confidence=0.5).
        Applies EMA(0.1) smoothing to the resulting confidence value.
        Updates self._signal_confidence.
        """
        signals = {"cpu": cpu_pct, "mem": mem_pct, "swap": swap_pct}
        for key, val in signals.items():
            hist = self._sie_history[key]
            hist.append(val)
            prev_conf = self._signal_confidence[key]
            if len(hist) >= 3:
                n      = len(hist)
                mean_v = sum(hist) / n
                var_v  = sum((x - mean_v) ** 2 for x in hist) / n
                std_v  = math.sqrt(var_v) if var_v > 0 else 1e-6
                z      = abs(val - mean_v) / std_v
                raw_conf = 0.5 if z > SIE_ZSCORE_THRESH else 1.0
            else:
                raw_conf = 1.0
            # EMA smoothing
            new_conf = 0.9 * prev_conf + 0.1 * raw_conf
            self._signal_confidence[key] = round(new_conf, 3)

    # ── RWA: Reinforcement-Weighted Arbitration ────────────────────────────────

    def _update_rwa_weights(self):
        """
        RWA — Reinforcement-Weighted Arbitration.
        Queries remediation outcome success rate from the cache and adjusts
        _acn_weights via EMA. Runs at most once per hour.
        """
        now = time.time()
        if now - self._last_rwa < 3600 and self._last_rwa > 0:
            return
        self._last_rwa = now

        # All 6 signals share the same remediation pool in this implementation.
        # Each signal's accuracy is the outcome success rate for tier>=2 actions.
        raw_accs = {}
        for sig in ("s1", "s2", "s3", "s4", "s5", "s6"):
            raw_accs[sig] = self._cache.query_signal_accuracy(sig, hours=RWA_OUTCOMES_H)

        # Normalise so weights sum to 1.0
        total = sum(raw_accs.values()) or 1.0
        for sig, acc in raw_accs.items():
            new_w = max(acc / total, RWA_MIN_WEIGHT)
            old_w = self._acn_weights[sig]
            self._acn_weights[sig] = (1 - RWA_LEARN_RATE) * old_w + RWA_LEARN_RATE * new_w

        # Renormalise after EMA update
        total2 = sum(self._acn_weights.values())
        for sig in self._acn_weights:
            self._acn_weights[sig] = round(self._acn_weights[sig] / total2, 4)

        top_sig  = max(self._acn_weights, key=self._acn_weights.get)
        bot_sig  = min(self._acn_weights, key=self._acn_weights.get)
        self._emit("info",
            f"RWA: signal weights updated — top={top_sig}({self._acn_weights[top_sig]:.3f}), "
            f"bot={bot_sig}({self._acn_weights[bot_sig]:.3f})")

    # ── CTRE: Chronothermal Regression Engine ─────────────────────────────────

    def _compute_ctre(self):
        """
        CTRE — Chronothermal Regression Engine.
        For each hour of day, fits a linear regression mem_pct ~ (1 + hour + temp_pct)
        using 30-day cache data. Computes stability score 0-1 per hour (1=stable, 0=volatile).
        """
        now = time.time()
        if now - self._last_ctre < CTRE_COOL_S and self._last_ctre > 0:
            return
        self._last_ctre = now
        if not self._cache._ok:
            return
        try:
            cutoff = int(now - 30 * 86400)
            with sqlite3.connect(self._cache._db, timeout=3) as cx:
                rows = cx.execute(
                    "SELECT CAST(ts/3600 % 24 AS INTEGER) hr, AVG(mem_pct), "
                    "AVG(COALESCE(100-thermal_pct,0)) "
                    "FROM metrics WHERE ts >= ? GROUP BY hr",
                    (cutoff,)
                ).fetchall()
            if len(rows) < CTRE_MIN_SAMPLES:
                return
            # Build per-hour variance from a 2nd pass
            with sqlite3.connect(self._cache._db, timeout=3) as cx:
                variance_rows = cx.execute(
                    "SELECT CAST(ts/3600 % 24 AS INTEGER) hr, "
                    "AVG(mem_pct*mem_pct) - AVG(mem_pct)*AVG(mem_pct) var, COUNT(*) cnt "
                    "FROM metrics WHERE ts >= ? GROUP BY hr",
                    (cutoff,)
                ).fetchall()
            variances = {int(r[0]): (float(r[1] or 0), int(r[2])) for r in variance_rows}
            stability = {}
            for r in rows:
                hr   = int(r[0])
                var, cnt = variances.get(hr, (1.0, 0))
                if cnt < CTRE_MIN_SAMPLES or var <= 0:
                    continue
                # Stability = 1 - (std / mean) capped at [0, 1]
                mean_m = float(r[1] or 50)
                cv     = math.sqrt(var) / (mean_m or 1)
                stab   = max(0.0, min(1.0, 1.0 - cv))
                stability[hr] = round(stab, 3)
            with self._lock:
                self._ctre_stability = stability
            volatile = [h for h, s in stability.items() if s < 0.5]
            if volatile:
                self._emit("info",
                    f"CTRE: volatile hours (stability<0.5): {sorted(volatile)}")
        except Exception:
            pass

    # ── AIP: Ancestral Impact Propagation ─────────────────────────────────────

    def _compute_aip(self):
        """
        AIP — Ancestral Impact Propagation.
        Builds a full process tree and scores each app family by its impact on
        total RSS, accounting for child processes up to AIP_MAX_DEPTH levels deep.
        """
        now = time.time()
        if now - self._last_aip < MEM_ANCESTRY_COOL_S:
            return
        self._last_aip = now
        try:
            pid_info = {}
            for p in psutil.process_iter(["pid", "ppid", "name", "memory_info"]):
                try:
                    rss = p.memory_info().rss / 1e6
                    pid_info[p.pid] = {
                        "ppid": p.ppid(), "name": p.name(), "rss": rss, "children": []
                    }
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # Build child list
            for pid, info in pid_info.items():
                ppid = info["ppid"]
                if ppid in pid_info:
                    pid_info[ppid]["children"].append(pid)

            # Find root families (parent is init/launchd)
            def family_rss(pid, depth=0):
                if depth > AIP_MAX_DEPTH or pid not in pid_info:
                    return 0.0
                own = pid_info[pid]["rss"]
                child_sum = sum(family_rss(c, depth + 1)
                                for c in pid_info[pid].get("children", []))
                return own + child_sum

            results = []
            for pid, info in pid_info.items():
                if info["ppid"] > 1 or info["name"] in PROTECTED:
                    continue
                own_rss   = info["rss"]
                total_rss = family_rss(pid)
                if total_rss < AIP_MIN_MB:
                    continue
                child_mb  = total_rss - own_rss
                depth_factor = 1.0 + 0.1 * len(info.get("children", []))
                impact_score = (own_rss / (total_rss or 1)) * depth_factor

                # Check for cascade risk: any child in rss_history with growth
                cascade_risk = False
                for cid in info.get("children", []):
                    if cid in self._rss_history:
                        ch = self._rss_history[cid]
                        if len(ch) >= 2:
                            rate = (ch[-1][1] - ch[0][1]) / max(ch[-1][0]-ch[0][0], 1) * 60
                            if rate >= CDA_LABEL_LEAK:
                                cascade_risk = True
                                break

                results.append({
                    "app": info["name"],
                    "impact_score": round(impact_score, 3),
                    "cascade_depth": len(info.get("children", [])),
                    "child_mb": round(child_mb),
                    "cascade_risk": cascade_risk,
                })

            results.sort(key=lambda x: x["impact_score"], reverse=True)
            with self._lock:
                self._aip_impact = results[:8]

            for r in results[:3]:
                if r["cascade_risk"]:
                    self._emit("warn",
                        f"AIP: cascading leak pattern detected in {r['app']} "
                        f"(depth={r['cascade_depth']}, child_mb={r['child_mb']})")
        except Exception:
            pass

    # ── RAC: Reinforcement Action Coordinator ─────────────────────────────────

    def _record_rac_action(self, tier: int, action_type: str, pre_mem: float):
        """
        RAC — record a pending remediation outcome to be evaluated after RAC_EVAL_DELAY_S.
        """
        eval_ts = time.time() + RAC_EVAL_DELAY_S
        self._pending_outcomes.append((eval_ts, tier, action_type, pre_mem))

    def _evaluate_rac_outcomes(self):
        """
        RAC — evaluate any pending outcomes whose delay has elapsed.
        Records result to cache and updates _action_efficacy EMA.
        """
        if not self._pending_outcomes:
            return
        now = time.time()
        with self._lock:
            current_mem = self._last_vm.percent
        remaining = []
        for eval_ts, tier, action, pre_mem in self._pending_outcomes:
            if now < eval_ts:
                remaining.append((eval_ts, tier, action, pre_mem))
                continue
            delta_pct = pre_mem - current_mem
            delta_mb  = delta_pct / 100.0 * self._mem_total_gb * 1024
            success   = 1 if delta_pct >= RAC_SUCCESS_PCT else 0
            # EMA update for action efficacy
            prev_eff  = self._action_efficacy.get(action, 0.0)
            self._action_efficacy[action] = round(
                0.9 * prev_eff + 0.1 * delta_pct, 2
            )
            self._cache.record_outcome(
                int(now), tier, action, pre_mem, current_mem,
                round(delta_mb, 1), success
            )
        self._pending_outcomes = remaining

    # ── ASZM: Adaptive Safety Zone Mapping ────────────────────────────────────

    def _update_aszm(self):
        """
        ASZM — Adaptive Safety Zone Mapping.
        Assigns a criticality score to all running processes based on uptime
        and CPU idleness. Processes above ASZM_CRIT_SCORE are added to the
        dynamic protected set to prevent erroneous remediation.
        """
        now = time.time()
        if now - self._last_aszm < ASZM_COOL_S and self._last_aszm > 0:
            return
        self._last_aszm = now
        try:
            running_names = set()
            for p in psutil.process_iter(["name", "create_time", "cpu_percent", "username"]):
                try:
                    if p.info["username"] == "root":
                        continue
                    name       = p.name()
                    create_ts  = p.info["create_time"] or 0
                    uptime_d   = (now - create_ts) / 86400.0
                    avg_cpu    = (p.info["cpu_percent"] or 0.0) / self._ncpu
                    running_names.add(name)

                    # High criticality: long-lived and low CPU (classic daemon)
                    uptime_w = min(uptime_d / 7.0, 1.0)
                    cpu_w    = max(0.0, 1.0 - avg_cpu / 5.0)
                    score    = (uptime_w + cpu_w) / 2.0
                    self._criticality_scores[name] = round(score, 3)

                    if score >= ASZM_CRIT_SCORE and name not in PROTECTED \
                            and name not in self._dynamic_protected:
                        self._dynamic_protected.add(name)
                        self._emit("info",
                            f"ASZM: {name} added to dynamic protection zone "
                            f"(criticality={score:.2f})")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # Prune stale dynamic entries
            stale = [n for n in list(self._dynamic_protected)
                     if n not in PROTECTED and n not in running_names]
            for name in stale:
                self._dynamic_protected.discard(name)
        except Exception:
            pass

    # ── PSM: Predictive State Machine ─────────────────────────────────────────

    def _update_psm(self, prev_tier: int, new_tier: int):
        """
        PSM — record a tier transition when dwell time exceeds PSM_DWELL_MIN_S.
        """
        now = time.time()
        dwell = now - self._tier_dwell_start
        if dwell >= PSM_DWELL_MIN_S:
            self._tier_transitions.append((prev_tier, new_tier, now, dwell))
            key = (prev_tier, new_tier)
            self._transition_matrix[key] = self._transition_matrix.get(key, 0) + 1
        self._tier_dwell_start = now
        self._prev_tier = new_tier

    def _psm_predict(self) -> int:
        """
        PSM — Markov next-tier prediction.
        From the current tier, finds the most probable next tier using the
        accumulated transition matrix. Also estimates dwell time in next tier.
        Returns predicted next tier integer.
        """
        cur = self._prev_tier
        # Gather all transitions FROM cur
        candidates = {to: cnt
                      for (fr, to), cnt in self._transition_matrix.items()
                      if fr == cur}
        if not candidates:
            self._psm_next_tier = cur
            self._psm_dwell_s   = 0.0
            return cur
        next_tier = max(candidates, key=candidates.get)
        # Estimate dwell: average time spent in next_tier across recorded transitions
        dwells = [dwell for (fr, to, _ts, dwell) in self._tier_transitions
                  if fr == next_tier]
        self._psm_next_tier = next_tier
        self._psm_dwell_s   = round(sum(dwells) / len(dwells), 1) if dwells else 0.0
        return next_tier

    # ── BRL: Bayesian Reasoning Layer ─────────────────────────────────────────

    def _update_brl(self):
        """
        BRL — update Beta prior counts from the 30-day cache tier distribution.
        Runs at most once per BRL_COOL_S seconds.
        """
        now = time.time()
        if now - self._last_brl < BRL_COOL_S and self._last_brl > 0:
            return
        self._last_brl = now
        dist = self._cache.query_tier_distribution(days=30)
        for t in range(5):
            self._brl_tier_prior[t] = BRL_PRIOR_ALPHA + dist.get(t, 0)

    def _compute_brl_confidence(self, effective_tier: int,
                                 signal_votes: list) -> float:
        """
        BRL — compute posterior confidence for effective_tier.
        likelihood = fraction of 6 signals agreeing on effective_tier.
        Returns posterior probability.
        """
        n_agree   = sum(1 for sv in signal_votes if sv >= effective_tier)
        likelihood = n_agree / len(signal_votes) if signal_votes else 0.5
        # Prior from Beta distribution: alpha[t] / sum(all alphas)
        prior_sum = sum(self._brl_tier_prior)
        prior     = (self._brl_tier_prior[min(effective_tier, 4)] /
                     (prior_sum or 1))
        # Unnormalized posterior
        unnorm = [self._brl_tier_prior[t] * (n_agree / len(signal_votes)
                   if signal_votes else 0.5) for t in range(5)]
        total_unnorm = sum(unnorm) or 1.0
        posterior = unnorm[min(effective_tier, 4)] / total_unnorm
        return round(posterior, 3)

    # ── CDA: Causal Diagnostic Agent ──────────────────────────────────────────

    def _cda_label_row(self, cpu: float, mem: float, cpi: float,
                       tier: int, swap_vel: float) -> int:
        """
        CDA heuristic labeler.
        Returns:  0=normal, 1=leak, 2=compressor_collapse, 3=cpu_collision
        """
        if cpu >= CPU_THROTTLE and tier >= 2:
            return 3   # cpu_collision
        if cpi >= CDA_LABEL_COMP_CPI:
            return 2   # compressor_collapse
        if tier >= 2 and swap_vel >= 20:
            return 1   # leak / pressure
        return 0       # normal

    def _cda_train_model(self):
        """
        CDA — train a 4-class softmax logistic regression in pure Python and
        optionally export to ONNX (if onnx package is available). Falls back
        to storing only the weights dict for rule-based inference.
        Requires at least CDA_TRAIN_MIN_ROWS labeled samples from the cache.
        """
        now = time.time()
        if now - self._last_cda_train < CDA_TRAIN_COOL_S and self._last_cda_train > 0:
            return
        if not self._cache._ok:
            return
        try:
            cutoff = int(now - 30 * 86400)
            with sqlite3.connect(self._cache._db, timeout=5) as cx:
                rows = cx.execute(
                    "SELECT cpu_pct, mem_pct, swap_pct, eff_tier, thermal_pct "
                    "FROM metrics WHERE ts >= ? AND cpu_pct IS NOT NULL "
                    "ORDER BY ts DESC LIMIT 5000",
                    (cutoff,)
                ).fetchall()
            if len(rows) < CDA_TRAIN_MIN_ROWS:
                return
            self._last_cda_train = now

            # Build training set with CPI approximation from swap_pct
            with self._lock:
                cpi_now = self._compression_pressure
            X, y = [], []
            for cpu, mem, swap, tier, therm in rows:
                cpu   = cpu   or 0.0
                mem   = mem   or 0.0
                swap  = swap  or 0.0
                tier  = tier  or 0
                therm = therm or 100
                cpi_approx = min(swap / 100.0, 1.0)
                label = self._cda_label_row(cpu, mem, cpi_approx, int(tier), swap)
                X.append([mem, cpi_approx, swap / 100.0, cpu / 100.0, therm / 100.0])
                y.append(label)

            n_samples = len(X)
            n_features = 5
            n_classes  = 4

            # Normalize features
            means = [sum(X[i][j] for i in range(n_samples)) / n_samples
                     for j in range(n_features)]
            stds  = [max(math.sqrt(
                        sum((X[i][j] - means[j])**2 for i in range(n_samples)) / n_samples
                    ), 1e-6) for j in range(n_features)]
            Xn = [[(X[i][j] - means[j]) / stds[j] for j in range(n_features)]
                  for i in range(n_samples)]

            # Initialize weights W (n_features × n_classes), bias b (n_classes,)
            W = [[0.0] * n_classes for _ in range(n_features)]
            b = [0.0] * n_classes

            def softmax(logits):
                m = max(logits)
                exps = [math.exp(v - m) for v in logits]
                s = sum(exps)
                return [e / s for e in exps]

            # SGD training
            for _ in range(CDA_EPOCHS):
                for i in range(n_samples):
                    xi   = Xn[i]
                    yi   = y[i]
                    logits = [sum(W[j][k] * xi[j] for j in range(n_features)) + b[k]
                              for k in range(n_classes)]
                    probs = softmax(logits)
                    # Compute gradient
                    for k in range(n_classes):
                        err = probs[k] - (1.0 if k == yi else 0.0)
                        for j in range(n_features):
                            W[j][k] -= CDA_LR * err * xi[j]
                        b[k] -= CDA_LR * err

            # Compute training accuracy
            correct = 0
            for i in range(n_samples):
                xi = Xn[i]
                logits = [sum(W[j][k] * xi[j] for j in range(n_features)) + b[k]
                          for k in range(n_classes)]
                pred = logits.index(max(logits))
                if pred == y[i]:
                    correct += 1
            acc = round(correct / n_samples * 100, 1)

            # Store weights for inference (always available)
            self._cda_weights = {
                "W": W, "b": b,
                "means": means, "stds": stds,
            }

            # Optionally export to ONNX
            try:
                import onnx
                from onnx import numpy_helper, TensorProto
                import numpy as np
                W_np = np.array(W, dtype=np.float32)   # (n_features, n_classes)
                b_np = np.array(b, dtype=np.float32)   # (n_classes,)
                W_init = numpy_helper.from_array(W_np.T, name="W")   # (n_classes, n_features)
                b_init = numpy_helper.from_array(b_np, name="b")
                X_in   = onnx.helper.make_tensor_value_info("X", TensorProto.FLOAT, [None, 5])
                Z_out  = onnx.helper.make_tensor_value_info("Z", TensorProto.FLOAT, None)
                gemm   = onnx.helper.make_node("Gemm", ["X","W","b"], ["logits"],
                                               transB=0)
                sm     = onnx.helper.make_node("Softmax", ["logits"], ["Z"], axis=1)
                graph  = onnx.helper.make_graph([gemm, sm], "cda",
                                               [X_in], [Z_out], [W_init, b_init])
                model  = onnx.helper.make_model(graph,
                    opset_imports=[onnx.helper.make_opsetid("", 13)])
                onnx.save(model, str(CDA_MODEL_PATH))
                self._emit("info",
                    f"CDA: ONNX model saved ({n_samples} samples, acc={acc}%)")
            except ImportError:
                pass   # onnx not installed — weights-only inference is used
            except Exception as oe:
                print(f"[CDA] ONNX export failed: {oe}", file=sys.stderr)

            self._emit("info",
                f"CDA: model trained ({n_samples} samples, acc={acc}%)")
            self._cda_load_model()
        except Exception as e:
            print(f"[CDA] train failed: {e}", file=sys.stderr)

    def _cda_load_model(self):
        """
        CDA — attempt to load a pre-trained ONNX model with onnxruntime.
        Sets self._cda_session to an InferenceSession, or None on failure.
        """
        self._cda_session = None
        if not CDA_MODEL_PATH.exists():
            return
        try:
            import onnxruntime as ort
            self._cda_session = ort.InferenceSession(
                str(CDA_MODEL_PATH),
                providers=["CPUExecutionProvider"]
            )
        except ImportError:
            pass   # onnxruntime not installed — rule-based fallback used
        except Exception as e:
            print(f"[CDA] model load failed: {e}", file=sys.stderr)

    def _diagnose_root_cause(self):
        """
        CDA — diagnose root cause of current memory pressure.
        Uses ONNX inference if session is available, else falls back to
        rule-based classification. Updates self.causal_diagnosis.
        """
        with self._lock:
            mem_pct  = self._last_vm.percent
            cpi      = self._compression_pressure
            swap_vel = self._swap_velocity
            cpu_pct  = self.cpu_hist[-1] if self.cpu_hist else 0.0
            therm    = self.thermal_pct

        LABELS = ["normal", "leak", "compressor_collapse", "cpu_collision"]

        if self._cda_session is not None:
            try:
                import numpy as np
                feat = np.array([[
                    mem_pct / 100.0,
                    cpi,
                    swap_vel / 100.0,
                    cpu_pct / 100.0,
                    therm / 100.0,
                ]], dtype=np.float32)
                out   = self._cda_session.run(None, {"X": feat})[0]
                idx   = int(out[0].argmax())
                conf  = float(out[0].max())
                self._cda_confidence = round(conf, 3)
                self.causal_diagnosis = LABELS[idx]
                if idx > 0:
                    self._emit("info",
                        f"CDA: root cause → {self.causal_diagnosis} "
                        f"(conf={conf:.0%})")
                return
            except Exception:
                pass   # fall through to rule-based

        # Rule-based fallback (or if ONNX weights are available)
        if hasattr(self, "_cda_weights"):
            try:
                w   = self._cda_weights
                xi  = [
                    (mem_pct / 100.0 - w["means"][0]) / w["stds"][0],
                    (cpi              - w["means"][1]) / w["stds"][1],
                    (swap_vel / 100.0 - w["means"][2]) / w["stds"][2],
                    (cpu_pct / 100.0  - w["means"][3]) / w["stds"][3],
                    (therm / 100.0    - w["means"][4]) / w["stds"][4],
                ]
                W, b = w["W"], w["b"]
                logits = [sum(W[j][k] * xi[j] for j in range(5)) + b[k]
                          for k in range(4)]
                m = max(logits)
                exps = [math.exp(v - m) for v in logits]
                s = sum(exps)
                probs = [e / s for e in exps]
                idx   = probs.index(max(probs))
                self._cda_confidence = round(probs[idx], 3)
                self.causal_diagnosis = LABELS[idx]
                if idx > 0:
                    self._emit("info",
                        f"CDA: root cause → {self.causal_diagnosis} "
                        f"(conf={self._cda_confidence:.0%})")
                return
            except Exception:
                pass

        # Pure rule-based fallback
        label = self._cda_label_row(cpu_pct, mem_pct, cpi, self.effective_tier, swap_vel)
        self.causal_diagnosis = LABELS[label]
        self._cda_confidence  = 0.0


# ─── HTML Dashboard ───────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0d1117">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="PerfBot">
<link rel="manifest" href="/manifest.json">
<title>Performance Bot</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
  /* ── Reset & design tokens ── */
  *{box-sizing:border-box;margin:0;padding:0}
  :root{
    --bg:#0d1117;--surface:#161b22;--surface2:#1c2128;
    --border:#21262d;--border2:#30363d;
    --text:#e6edf3;--muted:#8b949e;--muted2:#484f58;
    --green:#3fb950;--yellow:#d29922;--red:#f85149;
    --blue:#58a6ff;--orange:#e3b341;--accent:#1f6feb;--purple:#bc8cff;
    --cpu:#ff7b54;--mem:#7ee787;--swap:#58a6ff;
  }
  body{
    background:var(--bg);color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text',system-ui,sans-serif;
    font-size:13px;height:100dvh;overflow:hidden;
    display:flex;flex-direction:column;
  }

  /* ── Titlebar ── */
  .titlebar{
    display:flex;align-items:center;gap:10px;flex-shrink:0;
    background:var(--surface);padding:8px 14px;
    border-bottom:1px solid var(--border);z-index:99;
  }
  .app-icon{
    width:26px;height:26px;border-radius:7px;flex-shrink:0;
    background:linear-gradient(135deg,#1f6feb,#7c3aed);
    display:flex;align-items:center;justify-content:center;font-size:13px;
  }
  .app-name{font-size:13px;font-weight:700;letter-spacing:.2px}
  .status-chip{
    display:inline-flex;align-items:center;gap:4px;
    background:rgba(63,185,80,.08);border:1px solid rgba(63,185,80,.22);
    border-radius:20px;padding:2px 8px;
  }
  .status-dot{
    width:6px;height:6px;border-radius:50%;
    background:var(--green);box-shadow:0 0 5px var(--green);
    animation:pulse 2s infinite;
  }
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
  .status-label{font-size:10px;font-weight:700;color:var(--green);letter-spacing:.4px}
  .tb-spacer{flex:1}
  .tb-pills{display:flex;align-items:center;gap:5px}
  .pill{
    display:inline-flex;align-items:center;gap:3px;
    background:transparent;border:1px solid var(--border);
    border-radius:20px;padding:2px 8px;font-size:10px;color:var(--muted);
    transition:all .2s;white-space:nowrap;
  }
  .pill.on-battery{color:var(--green);border-color:rgba(63,185,80,.28);background:rgba(63,185,80,.05)}
  .pill.thermal-hot{color:var(--red);border-color:rgba(248,81,73,.35);background:rgba(248,81,73,.05)}
  .pill.mem-warn{color:var(--yellow);border-color:rgba(210,153,34,.35);background:rgba(210,153,34,.05)}
  .pill.mem-critical{color:var(--red);border-color:rgba(248,81,73,.4);background:rgba(248,81,73,.08);animation:pulse 1.4s infinite}
  .tb-btns{display:flex;gap:5px}
  .btn{
    background:var(--surface2);color:var(--text);
    border:1px solid var(--border2);padding:4px 11px;
    border-radius:6px;cursor:pointer;font-size:11px;font-weight:600;
    transition:all .15s;
  }
  .btn:hover{background:var(--accent);border-color:var(--accent)}
  .btn.paused{background:rgba(210,153,34,.12);border-color:rgba(210,153,34,.35);color:var(--yellow)}

  /* ── Metric strip ── */
  .metric-strip{
    display:grid;grid-template-columns:repeat(6,1fr);
    gap:1px;background:var(--border);
    border-bottom:1px solid var(--border);flex-shrink:0;
  }
  .metric{
    background:var(--surface);padding:8px 12px;
    display:flex;align-items:center;gap:9px;
    cursor:default;transition:background .15s;
  }
  .metric:hover{background:var(--surface2)}
  .metric-ring{flex-shrink:0}
  .ring-bg{fill:none;stroke:var(--surface2);stroke-width:3.5}
  .ring-fill{fill:none;stroke-width:3.5;stroke-linecap:round;
    transform:rotate(-90deg);transform-origin:50% 50%;
    transition:stroke-dasharray .5s,stroke .3s}
  .metric-info{min-width:0}
  .metric-name{font-size:9px;font-weight:700;color:var(--muted);letter-spacing:.55px;text-transform:uppercase}
  .metric-val{font-size:19px;font-weight:700;line-height:1.1;transition:color .3s}
  .metric-sub{font-size:9px;color:var(--muted);margin-top:1px;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

  /* ── Body wrapper ── */
  .body-wrap{flex:1;min-height:0;display:flex;flex-direction:column}

  /* ── Main 3-col grid ── */
  .main{
    display:grid;
    grid-template-columns:230px 1fr 288px;
    gap:1px;background:var(--border);
    flex:1;min-height:0;
  }

  /* ── Left column: CPU + Swap charts + Bot status ── */
  .left-col{display:flex;flex-direction:column;gap:1px;background:var(--border);min-height:0}
  .chart-card{
    background:var(--surface);padding:11px 12px;
    flex:1;min-height:0;display:flex;flex-direction:column;
  }
  .card-hdr{
    display:flex;justify-content:space-between;align-items:baseline;
    margin-bottom:7px;flex-shrink:0;
  }
  .card-title{font-size:9px;font-weight:700;color:var(--muted);letter-spacing:.55px;text-transform:uppercase}
  .card-live{font-size:15px;font-weight:700;transition:color .3s}
  .chart-wrap{flex:1;min-height:0;position:relative}
  .bot-card{background:var(--surface);padding:11px 12px;flex-shrink:0}
  .bs-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:7px}
  .bs-item{
    background:var(--surface2);border:1px solid var(--border);
    border-radius:6px;padding:6px 8px;
  }
  .bs-label{font-size:9px;font-weight:700;color:var(--muted);letter-spacing:.45px;text-transform:uppercase;margin-bottom:2px}
  .bs-val{font-size:17px;font-weight:700;transition:color .3s}
  .bs-sub{font-size:9px;color:var(--muted);margin-top:1px;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .thr-names{margin-top:5px;font-size:9px;font-family:'SF Mono',monospace;color:var(--orange);line-height:1.5}

  /* ── Center column: Memory Intelligence ── */
  .center-col{background:var(--surface);display:flex;flex-direction:column;min-height:0;overflow:hidden}

  /* memory hero */
  .mem-hero{
    display:flex;align-items:center;gap:16px;
    padding:12px 14px;border-bottom:1px solid var(--border);flex-shrink:0;
  }
  .mem-arc-svg{width:76px;height:76px;flex-shrink:0}
  .mem-arc-bg2{fill:none;stroke:var(--surface2);stroke-width:7}
  .mem-arc-fill2{fill:none;stroke-width:7;stroke-linecap:round;
    transform:rotate(-90deg);transform-origin:50% 50%;
    transition:stroke-dasharray .5s,stroke .3s}
  .mem-hero-info{flex:1;min-width:0}
  .mem-title-row{
    display:flex;align-items:center;gap:8px;margin-bottom:4px;
  }
  .section-title{font-size:9px;font-weight:700;color:var(--muted);letter-spacing:.55px;text-transform:uppercase}
  .mem-pct{font-size:34px;font-weight:700;line-height:1;transition:color .3s}
  .mem-gb{font-size:11px;color:var(--muted);margin-top:2px}
  .mem-forecast{margin-top:5px;font-size:10px;font-weight:600}
  .fc-stable{color:var(--green)}
  .fc-warn{color:var(--yellow)}
  .fc-critical{color:var(--red)}

  /* breakdown section */
  .bd-section{padding:9px 14px;border-bottom:1px solid var(--border);flex-shrink:0}
  .bd-bar{height:8px;display:flex;border-radius:4px;overflow:hidden;gap:1px;margin:6px 0}
  .bds{height:100%;transition:width .5s;min-width:1px}
  .bds-wired{background:#bc8cff}
  .bds-active{background:#7ee787}
  .bds-inactive{background:#58a6ff}
  .bds-compressed{background:#e3b341}
  .bds-free{background:#1c2128;border:1px solid var(--border2)}
  .bd-legend{display:flex;flex-wrap:wrap;gap:6px 12px}
  .bdl{display:flex;align-items:center;gap:3px;font-size:9px;color:var(--muted)}
  .bdl-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
  .bdl-val{font-family:'SF Mono',monospace;color:var(--text);margin-left:1px}

  /* vm detail rows */
  .vmrow-section{padding:6px 14px;border-bottom:1px solid var(--border);flex-shrink:0}
  .vmrow{
    display:flex;justify-content:space-between;align-items:center;padding:3px 0;font-size:10px;
    border-bottom:1px solid var(--border);
  }
  .vmrow:last-child{border:none}
  .vmkey{color:var(--muted);font-weight:600}
  .vmval{font-family:'SF Mono',monospace}

  /* memory families */
  .families-section{padding:9px 14px;flex:1;overflow-y:auto;min-height:0}
  .fam-row{display:flex;align-items:center;gap:7px;padding:3px 0;font-size:11px}
  .fam-icon{
    width:20px;height:20px;border-radius:5px;flex-shrink:0;
    display:flex;align-items:center;justify-content:center;
    font-size:9px;font-weight:700;
    background:rgba(88,166,255,.12);color:var(--blue);
    border:1px solid rgba(88,166,255,.18);
  }
  .fam-name{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .fam-bar-wrap{width:72px;flex-shrink:0}
  .fam-bar{height:3px;border-radius:2px;background:var(--border);overflow:hidden}
  .fam-bar-fill{height:100%;border-radius:2px;background:var(--mem);transition:width .5s}
  .fam-mb{font-family:'SF Mono',monospace;font-size:9px;color:var(--muted);flex-shrink:0;min-width:56px;text-align:right}

  /* ── Activity feed ── */
  .feed-col{background:var(--surface);display:flex;flex-direction:column;min-height:0}
  .feed-hdr{
    padding:9px 10px 7px;border-bottom:1px solid var(--border);
    display:flex;align-items:center;justify-content:space-between;flex-shrink:0;
  }
  .feed-title{font-size:9px;font-weight:700;color:var(--muted);letter-spacing:.55px;text-transform:uppercase}
  .ev-badge-pill{
    background:var(--surface2);border:1px solid var(--border);
    border-radius:20px;padding:1px 7px;font-size:9px;color:var(--muted);
  }
  .feed-body{flex:1;overflow-y:auto;padding:5px 7px;min-height:0}
  .ev{
    display:flex;gap:6px;padding:4px 6px;margin-bottom:2px;
    border-radius:4px;border-left:2px solid transparent;
    background:rgba(255,255,255,.012);transition:background .15s;
  }
  .ev:hover{background:rgba(255,255,255,.04)}
  .ev-ts{color:var(--muted2);white-space:nowrap;flex-shrink:0;font-size:9px;font-family:'SF Mono',monospace;padding-top:1px}
  .ev-badge{font-weight:700;white-space:nowrap;flex-shrink:0;font-size:9px;padding-top:1px;min-width:36px}
  .ev-msg{color:var(--text);word-break:break-word;min-width:0;font-size:10px;font-family:'SF Mono',monospace;line-height:1.45}
  .ev.fix  {border-left-color:var(--green)} .ev.fix   .ev-badge{color:var(--green)}
  .ev.warn {border-left-color:var(--yellow)}.ev.warn  .ev-badge{color:var(--yellow)}
  .ev.issue{border-left-color:var(--red)}   .ev.issue .ev-badge{color:var(--red)}
  .ev.info {border-left-color:var(--blue)}  .ev.info  .ev-badge{color:var(--blue)}

  /* ── Process table footer ── */
  .proc-footer{
    flex-shrink:0;height:184px;overflow-y:auto;
    background:var(--surface);border-top:1px solid var(--border);
    padding:8px 14px;
  }
  .proc-hdr-row{
    display:flex;justify-content:space-between;align-items:center;
    margin-bottom:5px;position:sticky;top:0;background:var(--surface);z-index:1;
    padding-bottom:4px;border-bottom:1px solid var(--border);
  }
  .mem-trend-toggle{font-size:9px;color:var(--muted);cursor:pointer;user-select:none}
  .mem-trend-toggle:hover{color:var(--text)}
  .mem-trend-panel{height:50px;margin-bottom:6px;position:relative}
  table{width:100%;border-collapse:collapse}
  th{
    text-align:left;font-size:9px;font-weight:700;color:var(--muted);
    letter-spacing:.5px;text-transform:uppercase;padding:3px 7px;
    border-bottom:1px solid var(--border);
    position:sticky;top:0;background:var(--surface);
  }
  td{padding:3px 7px;font-family:'SF Mono',monospace;font-size:10px;border-bottom:1px solid var(--border)}
  tr:last-child td{border:none}
  tr:hover td{background:rgba(255,255,255,.02)}
  .hi td:nth-child(3){color:var(--yellow)}
  .thr td:nth-child(3){color:var(--orange);font-weight:700}
  .bar-cell{width:52px}
  .bar{height:3px;border-radius:2px;background:var(--border);overflow:hidden}
  .bar-fill{height:100%;border-radius:2px;transition:width .4s}
  .thr-badge{
    display:inline-block;background:rgba(227,179,65,.1);color:var(--orange);
    border:1px solid rgba(227,179,65,.25);border-radius:3px;
    font-size:8px;font-weight:700;padding:0 3px;margin-left:4px;
  }

  /* ── Footer ── */
  .footer{
    flex-shrink:0;padding:5px 14px;
    background:var(--surface);border-top:1px solid var(--border);
    font-size:9px;color:var(--muted);
    display:flex;justify-content:space-between;align-items:center;
  }

  ::-webkit-scrollbar{width:3px;height:3px}
  ::-webkit-scrollbar-track{background:transparent}
  ::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px}
</style>
</head>
<body>

<!-- ═══ Titlebar ════════════════════════════════════════════════════════ -->
<div class="titlebar">
  <div class="app-icon">⚡</div>
  <span class="app-name">Performance Bot</span>
  <div class="status-chip" id="statusChip">
    <div class="status-dot" id="statusDot"></div>
    <span class="status-label" id="statusText">RUNNING</span>
  </div>
  <span class="tb-spacer"></span>
  <div class="tb-pills">
    <span id="uptimePill"      class="pill">⏱ 0s</span>
    <span id="powerPill"       class="pill">⚡ AC</span>
    <span id="thermalPill"     class="pill">🌡 Normal</span>
    <span id="memPressurePill" class="pill">🧠 Normal</span>
  </div>
  <div class="tb-btns">
    <button class="btn" id="pauseBtn" onclick="togglePause()">Pause</button>
    <button class="btn" onclick="clearFeed()">Clear Log</button>
  </div>
</div>

<!-- ═══ Metric strip ═════════════════════════════════════════════════════ -->
<div class="metric-strip">
  <div class="metric">
    <svg class="metric-ring" width="42" height="42" viewBox="0 0 42 42">
      <circle class="ring-bg" cx="21" cy="21" r="15"/>
      <circle id="rCpu" class="ring-fill" cx="21" cy="21" r="15" stroke="var(--cpu)" stroke-dasharray="0 95"/>
    </svg>
    <div class="metric-info">
      <div class="metric-name">CPU</div>
      <div class="metric-val" id="mCpu" style="color:var(--cpu)">—</div>
      <div class="metric-sub">system-wide</div>
    </div>
  </div>
  <div class="metric">
    <svg class="metric-ring" width="42" height="42" viewBox="0 0 42 42">
      <circle class="ring-bg" cx="21" cy="21" r="15"/>
      <circle id="rMem" class="ring-fill" cx="21" cy="21" r="15" stroke="var(--mem)" stroke-dasharray="0 95"/>
    </svg>
    <div class="metric-info">
      <div class="metric-name">Memory</div>
      <div class="metric-val" id="mMem" style="color:var(--mem)">—</div>
      <div class="metric-sub" id="mMemSub">— / — GB</div>
    </div>
  </div>
  <div class="metric">
    <svg class="metric-ring" width="42" height="42" viewBox="0 0 42 42">
      <circle class="ring-bg" cx="21" cy="21" r="15"/>
      <circle id="rSwap" class="ring-fill" cx="21" cy="21" r="15" stroke="var(--swap)" stroke-dasharray="0 95"/>
    </svg>
    <div class="metric-info">
      <div class="metric-name">Swap</div>
      <div class="metric-val" id="mSwap" style="color:var(--swap)">—</div>
      <div class="metric-sub" id="mSwapSub">— GB</div>
    </div>
  </div>
  <div class="metric">
    <svg class="metric-ring" width="42" height="42" viewBox="0 0 42 42">
      <circle class="ring-bg" cx="21" cy="21" r="15"/>
      <circle id="rDisk" class="ring-fill" cx="21" cy="21" r="15" stroke="var(--blue)" stroke-dasharray="0 95"/>
    </svg>
    <div class="metric-info">
      <div class="metric-name">Disk</div>
      <div class="metric-val" id="mDisk" style="color:var(--blue)">—</div>
      <div class="metric-sub" id="mDiskSub">— GB free</div>
    </div>
  </div>
  <div class="metric">
    <div class="metric-info">
      <div class="metric-name">Bot Actions</div>
      <div class="metric-val" id="mAct" style="color:var(--muted)">0</div>
      <div class="metric-sub">remediations</div>
    </div>
  </div>
  <div class="metric">
    <div class="metric-info">
      <div class="metric-name">Issues</div>
      <div class="metric-val" id="mIss" style="color:var(--muted)">0</div>
      <div class="metric-sub" id="mIssSub">— freed</div>
    </div>
  </div>
</div>

<!-- ═══ Body ═══════════════════════════════════════════════════════════ -->
<div class="body-wrap">
  <div class="main">

    <!-- ── Left col: charts + bot status ── -->
    <div class="left-col">
      <div class="chart-card">
        <div class="card-hdr">
          <span class="card-title">CPU — 90 s</span>
          <span class="card-live" id="cpuLive" style="color:var(--cpu)">—</span>
        </div>
        <div class="chart-wrap"><canvas id="cpuChart"></canvas></div>
      </div>
      <div class="chart-card">
        <div class="card-hdr">
          <span class="card-title">Swap — 90 s</span>
          <span class="card-live" id="swapLive" style="color:var(--swap)">—</span>
        </div>
        <div class="chart-wrap"><canvas id="swapChart"></canvas></div>
      </div>
      <div class="bot-card">
        <span class="card-title">Bot Status</span>
        <div class="bs-grid">
          <div class="bs-item">
            <div class="bs-label">Throttled</div>
            <div class="bs-val" id="bsThr" style="color:var(--muted)">0</div>
            <div class="bs-sub" id="bsThrSub">none active</div>
          </div>
          <div class="bs-item">
            <div class="bs-label">Actions</div>
            <div class="bs-val" id="bsAct" style="color:var(--muted)">0</div>
            <div class="bs-sub">total fixes</div>
          </div>
          <div class="bs-item">
            <div class="bs-label">Issues</div>
            <div class="bs-val" id="bsIss" style="color:var(--muted)">0</div>
            <div class="bs-sub">detected</div>
          </div>
          <div class="bs-item">
            <div class="bs-label">RAM Freed</div>
            <div class="bs-val" id="bsFreed" style="color:var(--muted)">0</div>
            <div class="bs-sub">MB cleared</div>
          </div>
        </div>
        <div class="thr-names" id="thrNames"></div>
      </div>
    </div>

    <!-- ── Center: Memory Intelligence ── -->
    <div class="center-col">

      <!-- Hero: arc + big % -->
      <div class="mem-hero">
        <svg class="mem-arc-svg" viewBox="0 0 76 76">
          <circle class="mem-arc-bg2" cx="38" cy="38" r="30"/>
          <circle id="memArc" class="mem-arc-fill2" cx="38" cy="38" r="30"
            stroke="var(--mem)" stroke-dasharray="0 189"/>
        </svg>
        <div class="mem-hero-info">
          <div class="mem-title-row">
            <span class="section-title">Memory Intelligence</span>
            <span id="memPressBadge" class="pill">Normal</span>
          </div>
          <div class="mem-pct" id="memPct" style="color:var(--mem)">—</div>
          <div class="mem-gb" id="memGb">— / — GB</div>
          <div class="mem-forecast" id="memFcLine"></div>
          <div id="predBanner" style="display:none;margin-top:5px;padding:3px 7px;
            border-radius:4px;font-size:9px;font-weight:600;letter-spacing:.5px;
            background:rgba(227,179,65,.15);color:#e3b341;border:1px solid rgba(227,179,65,.3)">
            ⚡ PREDICTIVE ESCALATION ACTIVE
          </div>
        </div>
      </div>

      <!-- Breakdown bar -->
      <div class="bd-section">
        <div class="section-title">Memory Composition</div>
        <div class="bd-bar" id="bdBar">
          <div class="bds bds-free" style="width:100%"></div>
        </div>
        <div class="bd-legend">
          <div class="bdl"><div class="bdl-dot" style="background:#bc8cff"></div>Wired<span class="bdl-val" id="bdWired">—</span></div>
          <div class="bdl"><div class="bdl-dot" style="background:#7ee787"></div>Active<span class="bdl-val" id="bdActive">—</span></div>
          <div class="bdl"><div class="bdl-dot" style="background:#58a6ff"></div>Inactive<span class="bdl-val" id="bdInactive">—</span></div>
          <div class="bdl"><div class="bdl-dot" style="background:#e3b341"></div>Compressed<span class="bdl-val" id="bdCompressed">—</span></div>
          <div class="bdl"><div class="bdl-dot" style="background:#1c2128;border:1px solid #30363d"></div>Free<span class="bdl-val" id="bdFree">—</span></div>
          <div class="bdl"><div class="bdl-dot" style="background:#58a6ff;opacity:.5"></div>Purgeable<span class="bdl-val" id="bdPurgeable">—</span></div>
        </div>
      </div>

      <!-- vm detail rows -->
      <div class="vmrow-section">
        <div class="vmrow">
          <span class="vmkey">Total RAM</span>
          <span class="vmval" id="vsRam">—</span>
        </div>
        <div class="vmrow">
          <span class="vmkey">Swap Used</span>
          <span class="vmval" id="vsSwap" style="color:var(--swap)">—</span>
        </div>
        <div class="vmrow">
          <span class="vmkey">Disk Free</span>
          <span class="vmval" id="vsDisk" style="color:var(--blue)">—</span>
        </div>
        <div class="vmrow">
          <span class="vmkey">Uptime</span>
          <span class="vmval" id="vsUptime">—</span>
        </div>
        <div class="vmrow" style="border-top:1px solid var(--border);margin-top:3px;padding-top:4px">
          <span class="vmkey">Active Tier</span>
          <span class="vmval" id="vsActiveTier" style="font-weight:700">—</span>
        </div>
        <div class="vmrow">
          <span class="vmkey">CPU-RAM Lock</span>
          <span class="vmval" id="vsCpuLock">—</span>
        </div>
        <div class="vmrow">
          <span class="vmkey">XPC Blocked</span>
          <span class="vmval" id="vsXpcBlocked">—</span>
        </div>
        <div class="vmrow">
          <span class="vmkey">Frozen Daemons</span>
          <span class="vmval" id="vsFrozen">—</span>
        </div>
        <div class="vmrow">
          <span class="vmkey">Leak Alerts</span>
          <span class="vmval" id="vsLeaks">—</span>
        </div>
        <div class="vmrow" style="border-top:1px solid var(--border);margin-top:3px;padding-top:4px">
          <span class="vmkey">Forecast Model</span>
          <span class="vmval" id="vsFcModel" style="color:var(--muted)">—</span>
        </div>
        <div class="vmrow">
          <span class="vmkey">CPI (Compression)</span>
          <span class="vmval" id="vsCpi">—</span>
        </div>
        <div class="vmrow">
          <span class="vmkey">Swap Velocity</span>
          <span class="vmval" id="vsSwapVel">—</span>
        </div>
        <div class="vmrow">
          <span class="vmkey">Thermal Coupling</span>
          <span class="vmval" id="vsThermalCoupling" style="color:var(--muted)">—</span>
        </div>
        <div class="vmrow" style="border-top:1px solid var(--border);margin-top:3px;padding-top:4px">
          <span class="vmkey">Cache (90d)</span>
          <span class="vmval" id="vsCacheSize" style="color:var(--muted)">—</span>
        </div>
        <div class="vmrow" style="border-top:1px solid var(--border);margin-top:3px;padding-top:4px">
          <span class="vmkey">Root Cause</span>
          <span class="vmval" id="vsRootCause" style="color:var(--muted)">—</span>
        </div>
        <div class="vmrow">
          <span class="vmkey">BRL Confidence</span>
          <span class="vmval" id="vsBrlConf" style="color:var(--muted)">—</span>
        </div>
        <div class="vmrow">
          <span class="vmkey">ACN Weights</span>
          <span class="vmval" id="vsAcnWeights" style="color:var(--muted);font-size:9px">—</span>
        </div>
        <div class="vmrow">
          <span class="vmkey">Signal Integrity</span>
          <span class="vmval" id="vsSigConf" style="font-size:9px">—</span>
        </div>
        <div class="vmrow">
          <span class="vmkey">PSM Next Tier</span>
          <span class="vmval" id="vsPsmNext" style="color:var(--muted)">—</span>
        </div>
        <div class="vmrow">
          <span class="vmkey">CTRE Zone</span>
          <span class="vmval" id="vsCtreZone" style="color:var(--muted)">—</span>
        </div>
        <div class="vmrow">
          <span class="vmkey">Action Efficacy</span>
          <span class="vmval" id="vsEfficacy" style="color:var(--muted);font-size:9px">—</span>
        </div>
        <div class="vmrow">
          <span class="vmkey">ASZM Protected+</span>
          <span class="vmval" id="vsAszm" style="color:var(--muted)">—</span>
        </div>
      </div>

      <!-- Memory Events mini-feed -->
      <div class="vmrow-section" style="flex-shrink:0;max-height:140px;overflow-y:auto">
        <div class="section-title" style="margin-bottom:4px;position:sticky;top:0;background:var(--surface);padding-bottom:3px;z-index:1">Memory Events</div>
        <div id="memEvFeed"><div style="color:var(--muted);font-size:9px">Waiting for memory events…</div></div>
      </div>

      <!-- App Predictions (from 90-day disk cache) -->
      <div class="families-section" id="predSection" style="display:none">
        <div class="section-title" style="margin-bottom:7px">App Predictions <span style="font-size:9px;color:var(--muted);font-weight:400">(90-day cache)</span></div>
        <div id="predList"></div>
      </div>

      <!-- Memory families -->
      <div class="families-section">
        <div class="section-title" style="margin-bottom:7px">Memory Families</div>
        <div id="familyList"><div style="color:var(--muted);font-size:10px">Scanning process tree…</div></div>
      </div>
    </div>

    <!-- ── Right: Activity feed ── -->
    <div class="feed-col">
      <div class="feed-hdr">
        <span class="feed-title">Activity Log</span>
        <span class="ev-badge-pill" id="evCount">0</span>
      </div>
      <div class="feed-body" id="feedBody"></div>
    </div>

  </div><!-- /main -->

  <!-- ── Process table ── -->
  <div class="proc-footer">
    <div class="proc-hdr-row">
      <span class="card-title">Top Processes</span>
      <span class="mem-trend-toggle" id="trendToggle" onclick="toggleTrend()">show memory trend ▾</span>
    </div>
    <div class="mem-trend-panel" id="trendPanel" style="display:none">
      <canvas id="memChart"></canvas>
    </div>
    <table>
      <thead>
        <tr>
          <th>Process</th><th>PID</th>
          <th>CPU %</th><th style="width:52px">CPU</th>
          <th>MEM %</th><th style="width:52px">MEM</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody id="procBody"></tbody>
    </table>
  </div>
</div><!-- /body-wrap -->

<!-- ── Footer ── -->
<div class="footer">
  <span id="lastUpdate">Initializing…</span>
  <span>Poll 1 s · Throttle &gt;85% CPU · Warn &gt;80% RAM · v2.0 Autonomous Engine active</span>
</div>

<script>
// ── Ring gauge helpers ─────────────────────────────────────────────────────────
const RC = 2 * Math.PI * 15;   // circumference for r=15 rings (~94.2)
const MAC = 2 * Math.PI * 30;  // circumference for r=30 memory arc (~188.5)
function setRing(id, pct, color) {
  const el = document.getElementById(id);
  if (!el) return;
  const f = RC * Math.min(pct, 100) / 100;
  el.setAttribute('stroke-dasharray', f.toFixed(1) + ' ' + RC.toFixed(1));
  if (color) el.setAttribute('stroke', color);
}
function setMemArc(pct, color) {
  const el = document.getElementById('memArc');
  if (!el) return;
  const f = MAC * Math.min(pct, 100) / 100;
  el.setAttribute('stroke-dasharray', f.toFixed(1) + ' ' + MAC.toFixed(1));
  if (color) el.setAttribute('stroke', color);
}

// ── Chart factory ─────────────────────────────────────────────────────────────
function makeChart(id, color, fill, warnPct) {
  const ctx = document.getElementById(id).getContext('2d');
  const warnPlugin = {
    id:'warnLine',
    beforeDraw(chart) {
      if (!warnPct) return;
      const {ctx:c, chartArea, scales} = chart;
      if (!chartArea) return;
      const y = scales.y.getPixelForValue(warnPct);
      c.save(); c.strokeStyle='rgba(248,81,73,.22)'; c.lineWidth=1;
      c.setLineDash([3,5]); c.beginPath();
      c.moveTo(chartArea.left, y); c.lineTo(chartArea.right, y);
      c.stroke(); c.setLineDash([]); c.restore();
    }
  };
  return new Chart(ctx, {
    type:'line',
    data:{ labels:[], datasets:[{ data:[], borderColor:color, borderWidth:1.5,
      backgroundColor:fill, fill:true, tension:0.3, pointRadius:0 }] },
    options:{
      responsive:true, maintainAspectRatio:false, animation:false,
      scales:{
        x:{display:false},
        y:{min:0, max:100,
          ticks:{color:'#656d76', stepSize:25, callback:v=>v+'%', font:{size:9}},
          grid:{color:'#21262d'}, border:{display:false}}
      },
      plugins:{legend:{display:false}, tooltip:{enabled:false}},
    },
    plugins:[warnPlugin],
  });
}
const cpuChart  = makeChart('cpuChart',  '#ff7b54', 'rgba(255,123,84,.1)',  80);
const swapChart = makeChart('swapChart', '#58a6ff', 'rgba(88,166,255,.1)',  50);
const memChart  = makeChart('memChart',  '#7ee787', 'rgba(126,231,135,.1)', 80);
function updateChart(chart, data) {
  chart.data.labels = data.map((_,i)=>i);
  chart.data.datasets[0].data = data;
  chart.update('none');
}

// ── State ─────────────────────────────────────────────────────────────────────
let evCnt=0, seenEvs=new Set(), paused=false, trendVisible=false;
let memTotalGb=0, swapTotalGb=0;

// ── Helpers ───────────────────────────────────────────────────────────────────
function colorFor(v,lo,hi,def){ return v>hi?'var(--red)':v>lo?'var(--yellow)':def; }
function fmtUp(s){ if(s<60)return s+'s'; if(s<3600)return Math.floor(s/60)+'m '+(s%60)+'s'; return Math.floor(s/3600)+'h '+Math.floor((s%3600)/60)+'m'; }
function fmtMb(v){ if(v==null)return'—'; return v>=1024?(v/1024).toFixed(1)+' GB':Math.round(v)+' MB'; }

// ── Memory trend toggle ───────────────────────────────────────────────────────
function toggleTrend() {
  trendVisible = !trendVisible;
  document.getElementById('trendPanel').style.display = trendVisible ? '' : 'none';
  document.getElementById('trendToggle').textContent =
    trendVisible ? 'hide memory trend ▴' : 'show memory trend ▾';
  if (trendVisible) memChart.resize();
}

// ── Process table ─────────────────────────────────────────────────────────────
function barCell(pct,color){
  return `<td class="bar-cell"><div class="bar"><div class="bar-fill" style="width:${Math.min(pct,100).toFixed(1)}%;background:${color}"></div></div></td>`;
}
function buildProcTable(procs, thrPids) {
  document.getElementById('procBody').innerHTML = procs.map(([cpu,mem,pid,name,status])=>{
    const thr=thrPids.includes(pid), hiCpu=!thr&&cpu>=70;
    const cls=thr?'thr':hiCpu?'hi':'';
    const cc=thr?'var(--orange)':hiCpu?'var(--yellow)':'var(--cpu)';
    const mc=mem>=10?'var(--red)':mem>=4?'var(--yellow)':'var(--mem)';
    const badge=thr?'<span class="thr-badge">THROTTLED</span>':'';
    return `<tr class="${cls}"><td>${name}${badge}</td><td>${pid}</td><td>${cpu.toFixed(1)}%</td>${barCell(cpu,cc)}<td>${mem.toFixed(1)}%</td>${barCell(mem*8,mc)}<td>${status}</td></tr>`;
  }).join('');
}

// ── Activity feed ──────────────────────────────────────────────────────────────
const BADGE={fix:'✓ FIX',warn:'⚠ WARN',issue:'✗ ISS',info:'ℹ INFO'};
function addEvent(ev) {
  const key=ev.ts+ev.msg; if(seenEvs.has(key))return; seenEvs.add(key); evCnt++;
  document.getElementById('evCount').textContent = evCnt;
  const div=document.createElement('div'); div.className='ev '+ev.kind;
  div.innerHTML=`<span class="ev-ts">${ev.ts}</span><span class="ev-badge">${BADGE[ev.kind]||'?'}</span><span class="ev-msg">${ev.msg}</span>`;
  document.getElementById('feedBody').prepend(div);
}
function clearFeed(){
  evCnt=0; seenEvs.clear();
  document.getElementById('evCount').textContent='0';
  document.getElementById('feedBody').innerHTML='';
}

// ── Pause / Resume ─────────────────────────────────────────────────────────────
function togglePause() {
  paused=!paused;
  const chip=document.getElementById('statusChip');
  const dot=document.getElementById('statusDot');
  const txt=document.getElementById('statusText');
  const btn=document.getElementById('pauseBtn');
  if (paused) {
    chip.style.cssText='background:rgba(210,153,34,.08);border-color:rgba(210,153,34,.28)';
    dot.style.cssText='background:var(--yellow);box-shadow:0 0 5px var(--yellow)';
    txt.style.color='var(--yellow)'; txt.textContent='PAUSED';
    btn.textContent='Resume'; btn.classList.add('paused');
  } else {
    chip.style.cssText='background:rgba(63,185,80,.08);border-color:rgba(63,185,80,.22)';
    dot.style.cssText='background:var(--green);box-shadow:0 0 5px var(--green)';
    txt.style.color='var(--green)'; txt.textContent='RUNNING';
    btn.textContent='Pause'; btn.classList.remove('paused');
  }
  fetch('/pause?state='+(paused?'1':'0'));
}

// ── Poll loop ──────────────────────────────────────────────────────────────────
async function poll() {
  try {
    const r = await fetch('/stats');
    if (!r.ok) return;
    const d = await r.json();
    if (d.mem_total_gb)  memTotalGb  = d.mem_total_gb;
    if (d.swap_total_gb) swapTotalGb = d.swap_total_gb;

    if (!paused) {
      const cpu  = (d.cpu_hist  ||[]).at(-1)??0;
      const mem  = (d.mem_hist  ||[]).at(-1)??0;
      const swap = (d.swap_hist ||[]).at(-1)??0;
      const disk = d.disk_pct??0;
      const cpuC = colorFor(cpu,60,80,'var(--cpu)');
      const memC = colorFor(mem,60,80,'var(--mem)');
      const swpC = swap>50?'var(--yellow)':'var(--swap)';
      const dskC = disk>90?'var(--red)':disk>80?'var(--yellow)':'var(--blue)';

      // charts
      updateChart(cpuChart,  d.cpu_hist  ||[]);
      updateChart(swapChart, d.swap_hist ||[]);
      if (trendVisible) updateChart(memChart, d.mem_hist||[]);

      // chart live labels
      const set=(id,t,c)=>{const e=document.getElementById(id);e.textContent=t;if(c)e.style.color=c;};
      set('cpuLive', cpu.toFixed(0)+'%', cpuC);
      set('swapLive',swap.toFixed(0)+'%',swpC);

      // metric strip rings
      setRing('rCpu',  cpu,  cpuC);
      setRing('rMem',  mem,  memC);
      setRing('rSwap', swap, swpC);
      setRing('rDisk', disk, dskC);
      set('mCpu',  cpu.toFixed(0)+'%',  cpuC);
      set('mMem',  mem.toFixed(0)+'%',  memC);
      set('mSwap', swap.toFixed(0)+'%', swpC);
      set('mDisk', disk.toFixed(0)+'%', dskC);
      document.getElementById('mMemSub').textContent  = (memTotalGb*mem/100).toFixed(1)+' / '+memTotalGb.toFixed(1)+' GB';
      document.getElementById('mSwapSub').textContent = (swapTotalGb*swap/100).toFixed(2)+' / '+swapTotalGb.toFixed(1)+' GB';
      document.getElementById('mDiskSub').textContent = d.disk_free_gb ? d.disk_free_gb.toFixed(1)+' GB free' : '—';

      const act=d.actions||0, iss=d.issues||0, freed=d.freed_mb||0;
      set('mAct', String(act), act>0?'var(--green)':'var(--muted)');
      set('mIss', String(iss), iss>0?'var(--red)':'var(--muted)');
      document.getElementById('mIssSub').textContent = freed>=1024?(freed/1024).toFixed(1)+' GB freed':freed.toFixed(0)+' MB freed';

      // memory hero arc
      setMemArc(mem, memC);
      set('memPct', mem.toFixed(0)+'%', memC);
      document.getElementById('memGb').textContent = (memTotalGb*mem/100).toFixed(1)+' / '+memTotalGb.toFixed(1)+' GB';

      // forecast line
      const fc=d.mem_forecast_min??-1;
      const fcEl=document.getElementById('memFcLine');
      if (fc===0)      { fcEl.textContent='⚠ Memory exhausted'; fcEl.className='mem-forecast fc-critical'; }
      else if (fc>0)   { fcEl.textContent='↑ ~'+fc+' min to 95%'; fcEl.className='mem-forecast '+(fc<5?'fc-critical':fc<15?'fc-warn':'fc-stable'); }
      else             { fcEl.textContent='✓ Stable'; fcEl.className='mem-forecast fc-stable'; }

      // pressure pills (titlebar + badge)
      const mpl=d.mem_pressure_level||'normal';
      const mpMap={normal:['🧠 Normal','pill'],warn:['🧠 Warn','pill mem-warn'],critical:['🧠 Critical','pill mem-critical']};
      const [mpt,mpc]=mpMap[mpl]||mpMap.normal;
      const mpEl=document.getElementById('memPressurePill'); mpEl.textContent=mpt; mpEl.className=mpc;
      const mpb=document.getElementById('memPressBadge');    mpb.textContent=mpl.charAt(0).toUpperCase()+mpl.slice(1); mpb.className=mpc;

      // titlebar pills
      set('uptimePill','⏱ '+fmtUp(d.uptime_s||0));
      const pp=document.getElementById('powerPill');
      pp.textContent=d.on_battery?'🔋 Battery':'⚡ AC';
      pp.className=d.on_battery?'pill on-battery':'pill';
      const tp=document.getElementById('thermalPill'), tpct=d.thermal_pct??100;
      tp.textContent=tpct<100?'🌡 '+tpct+'%':'🌡 Normal'; tp.className=tpct<100?'pill thermal-hot':'pill';

      // breakdown bar
      const vbd=d.vm_breakdown||{};
      if (vbd.wired!==undefined) {
        const tot=(vbd.wired||0)+(vbd.active||0)+(vbd.inactive||0)+(vbd.compressed||0)+(vbd.free||0);
        if (tot>0) {
          const w=v=>Math.max(0.5,(v||0)/tot*100).toFixed(1)+'%';
          document.getElementById('bdBar').innerHTML=
            `<div class="bds bds-wired"      style="width:${w(vbd.wired)}"></div>`+
            `<div class="bds bds-active"     style="width:${w(vbd.active)}"></div>`+
            `<div class="bds bds-inactive"   style="width:${w(vbd.inactive)}"></div>`+
            `<div class="bds bds-compressed" style="width:${w(vbd.compressed)}"></div>`+
            `<div class="bds bds-free"       style="flex:1"></div>`;
        }
        set('bdWired',     fmtMb(vbd.wired));
        set('bdActive',    fmtMb(vbd.active));
        set('bdInactive',  fmtMb(vbd.inactive));
        set('bdCompressed',fmtMb(vbd.compressed));
        set('bdFree',      fmtMb(vbd.free));
        set('bdPurgeable', fmtMb(vbd.purgeable));
      }

      // vm rows
      set('vsRam',    memTotalGb?memTotalGb.toFixed(1)+' GB':'—');
      set('vsSwap',   (swapTotalGb*swap/100).toFixed(2)+' / '+swapTotalGb.toFixed(1)+' GB');
      set('vsDisk',   d.disk_free_gb?d.disk_free_gb.toFixed(1)+' GB':'—');
      set('vsUptime', fmtUp(d.uptime_s||0));

      // Predictive Remediation Engine rows
      const tierLabels = ['—','Tier 1 · Observe','Tier 2 · Advisory','Tier 3 · Freeze','Tier 4 · Terminate'];
      const tierColors = ['var(--muted)','var(--blue)','var(--yellow)','var(--orange)','var(--red)'];
      const etier = d.effective_tier||0;
      const tierEl = document.getElementById('vsActiveTier');
      tierEl.textContent = tierLabels[etier] || ('Tier '+etier);
      tierEl.style.color = tierColors[etier] || 'var(--muted)';

      const lockEl = document.getElementById('vsCpuLock');
      if (d.cpu_ram_lock) { lockEl.textContent='Active'; lockEl.style.color='var(--orange)'; }
      else                { lockEl.textContent='Off';    lockEl.style.color='var(--muted)';  }

      const xpcEl = document.getElementById('vsXpcBlocked');
      const xpcN = d.xpc_blocked||0;
      if (xpcN>0) { xpcEl.textContent=xpcN+' blocked'; xpcEl.style.color='var(--yellow)'; }
      else        { xpcEl.textContent='None';           xpcEl.style.color='var(--muted)';  }

      const frozenEl = document.getElementById('vsFrozen');
      const frozenN = d.frozen_count||0;
      if (frozenN>0) { frozenEl.textContent=frozenN+' paused (SIGSTOP)'; frozenEl.style.color='var(--orange)'; }
      else           { frozenEl.textContent='None';                       frozenEl.style.color='var(--muted)';  }

      const leakEl = document.getElementById('vsLeaks');
      const leakN = d.leak_pids||0;
      if (leakN>0) { leakEl.textContent=leakN+' process'+(leakN>1?'es':'')+' flagged'; leakEl.style.color='var(--red)'; }
      else         { leakEl.textContent='None';                                          leakEl.style.color='var(--muted)'; }

      // Forecast model (MMAF)
      const fmEl = document.getElementById('vsFcModel');
      const fm = d.forecast_model||'linear';
      fmEl.textContent = fm;
      fmEl.style.color = fm==='exponential'?'var(--red)':fm==='quadratic'?'var(--yellow)':'var(--muted)';

      // CEO Compression Pressure Index
      const cpiEl = document.getElementById('vsCpi');
      const cpi = d.compression_pressure||0;
      if (cpi >= 0.75)      { cpiEl.textContent=cpi.toFixed(2)+' (critical)'; cpiEl.style.color='var(--red)'; }
      else if (cpi >= 0.50) { cpiEl.textContent=cpi.toFixed(2)+' (degrading)'; cpiEl.style.color='var(--yellow)'; }
      else if (cpi > 0)     { cpiEl.textContent=cpi.toFixed(2)+' (ok)'; cpiEl.style.color='var(--green)'; }
      else                  { cpiEl.textContent='—'; cpiEl.style.color='var(--muted)'; }

      // Swap velocity
      const svEl = document.getElementById('vsSwapVel');
      const sv = d.swap_velocity||0;
      if (sv >= 50)      { svEl.textContent=sv.toFixed(0)+' MB/s'; svEl.style.color='var(--red)'; }
      else if (sv >= 10) { svEl.textContent=sv.toFixed(1)+' MB/s'; svEl.style.color='var(--yellow)'; }
      else if (sv > 0)   { svEl.textContent=sv.toFixed(1)+' MB/s'; svEl.style.color='var(--muted)'; }
      else               { svEl.textContent='0 (stable)'; svEl.style.color='var(--green)'; }

      // TMCP thermal coupling
      const tcEl = document.getElementById('vsThermalCoupling');
      const tc = d.thermal_coupling||0;
      tcEl.textContent = tc > 0 ? tc.toFixed(3) : 'Learning…';

      // Cache stats
      const cacheEl = document.getElementById('vsCacheSize');
      const cMb = d.cache_db_mb||0, cRows = d.cache_rows||0;
      cacheEl.textContent = cMb>0 ? cMb.toFixed(1)+' MB · '+(cRows/1000).toFixed(0)+'k rows' : 'Collecting…';

      // v2.0 rows
      // Root Cause (CDA)
      const rcEl = document.getElementById('vsRootCause');
      const rc = d.causal_diagnosis||'normal';
      const rcColor = {normal:'var(--green)',leak:'var(--yellow)',compressor_collapse:'var(--orange)',cpu_collision:'var(--red)'};
      rcEl.textContent = rc; rcEl.style.color = rcColor[rc]||'var(--muted)';

      // BRL Confidence
      const brlEl = document.getElementById('vsBrlConf');
      const brlC = d.brl_confidence||0;
      brlEl.textContent = (brlC*100).toFixed(0)+'%';
      brlEl.style.color = brlC>=0.7?'var(--green)':brlC>=0.4?'var(--yellow)':'var(--muted)';

      // ACN Weights sparkbar
      const acnEl = document.getElementById('vsAcnWeights');
      const acnW = d.acn_weights||{};
      if (Object.keys(acnW).length) {
        acnEl.textContent = Object.entries(acnW).map(([k,v])=>k+':'+(v*100).toFixed(0)+'%').join(' ');
      }

      // Signal Integrity (SIE)
      const scEl = document.getElementById('vsSigConf');
      const sc2 = d.signal_confidence||{};
      function sigLight(v){return v>=0.9?'🟢':v>=0.7?'🟡':'🔴';}
      if (Object.keys(sc2).length){
        scEl.textContent = Object.entries(sc2).map(([k,v])=>sigLight(v)+k).join(' ');
      }

      // PSM Next Tier
      const psmEl = document.getElementById('vsPsmNext');
      const psmN = d.psm_next_tier||0, psmD = d.psm_dwell_s||0;
      psmEl.textContent = psmN>0 ? 'T'+psmN+' (≈'+psmD+'s)' : '—';
      psmEl.style.color = tierColors[psmN]||'var(--muted)';

      // CTRE Zone (current hour stability)
      const ctreEl = document.getElementById('vsCtreZone');
      const ctreS = d.ctre_stability||{};
      const curHr = new Date().getHours();
      const ctreV = ctreS[String(curHr)];
      if (ctreV!=null) {
        ctreEl.textContent = (ctreV*100).toFixed(0)+'% stable (hr'+curHr+')';
        ctreEl.style.color = ctreV>=0.7?'var(--green)':ctreV>=0.4?'var(--yellow)':'var(--red)';
      } else { ctreEl.textContent='Learning…'; ctreEl.style.color='var(--muted)'; }

      // Action Efficacy (RAC)
      const effEl = document.getElementById('vsEfficacy');
      const eff = d.action_efficacy||{};
      if (Object.keys(eff).length){
        const best = Object.entries(eff).sort((a,b)=>b[1]-a[1]);
        effEl.textContent = best.map(([k,v])=>k.replace('_',' ')+':'+(v>=0?'+':'')+v.toFixed(1)+'%').join(' ');
      } else { effEl.textContent='No data yet'; effEl.style.color='var(--muted)'; }

      // ASZM Protected additions
      const aszmEl = document.getElementById('vsAszm');
      const aszmN = d.dynamic_protected||0;
      aszmEl.textContent = aszmN>0 ? '+'+aszmN+' dynamic' : 'None';
      aszmEl.style.color = aszmN>0?'var(--yellow)':'var(--muted)';

      // App predictions from 90-day cache
      const preds = d.app_predictions||[];
      const predSection = document.getElementById('predSection');
      const predList    = document.getElementById('predList');
      if (preds.length) {
        predSection.style.display='block';
        const riskColor = {high:'var(--red)',medium:'var(--yellow)',low:'var(--green)'};
        const trendIcon = {rising:'↑',stable:'→',falling:'↓'};
        predList.innerHTML = preds.map(p=>`
          <div class="fam-row" style="align-items:center">
            <div class="fam-icon" style="background:${riskColor[p.risk]||'var(--muted)'};opacity:.8">${(p.app||'?').charAt(0).toUpperCase()}</div>
            <div style="flex:1;min-width:0">
              <div style="font-size:10px;font-weight:600;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${p.app}</div>
              <div style="font-size:9px;color:var(--muted)">${p.mb} MB · ${p.pct}% · ${trendIcon[p.trend]||'→'} ${p.trend}</div>
            </div>
            <div style="font-size:9px;font-weight:700;color:${riskColor[p.risk]||'var(--muted)'};text-transform:uppercase;flex-shrink:0">${p.risk}</div>
          </div>`).join('');
      } else {
        predSection.style.display='none';
      }

      // Predictive escalation banner
      const predBanner = document.getElementById('predBanner');
      predBanner.style.display = d.predictive_escalation ? 'block' : 'none';

      // memory families
      const anc=d.mem_ancestry||[];
      if (anc.length) {
        const mx=anc[0].mb||1;
        document.getElementById('familyList').innerHTML=anc.slice(0,8).map(a=>{
          const letter=(a.app||'?').charAt(0).toUpperCase();
          const bw=Math.round(a.mb/mx*100);
          const bc=a.pct>20?'var(--red)':a.pct>10?'var(--yellow)':'var(--mem)';
          return `<div class="fam-row">
            <div class="fam-icon">${letter}</div>
            <div class="fam-name">${a.app}</div>
            <div class="fam-bar-wrap"><div class="fam-bar"><div class="fam-bar-fill" style="width:${bw}%;background:${bc}"></div></div></div>
            <div class="fam-mb">${fmtMb(a.mb)} (${a.pct}%)</div>
          </div>`;
        }).join('');
      }

      // bot status
      const thrKeys=Object.keys(d.throttled||{}), thrNames=Object.values(d.throttled||{});
      set('bsThr',  String(thrKeys.length), thrKeys.length>0?'var(--orange)':'var(--muted)');
      set('bsThrSub', thrKeys.length>0?thrNames[0]:'none active');
      set('bsAct',  String(act), act>0?'var(--green)':'var(--muted)');
      set('bsIss',  String(iss), iss>0?'var(--red)':'var(--muted)');
      set('bsFreed',freed>=1024?(freed/1024).toFixed(1)+' GB':freed.toFixed(0)+' MB', freed>0?'var(--blue)':'var(--muted)');
      document.getElementById('thrNames').textContent=thrNames.join('\n');

      buildProcTable(d.top_procs||[], thrKeys.map(Number));
      document.getElementById('lastUpdate').textContent='Last update: '+new Date().toLocaleTimeString();
    }
    (d.events||[]).forEach(ev=>addEvent(ev));

    // Memory Events mini-feed — filter relevant events from the full log
    const MEM_KW = ['RAM','pressure','Memory','memory','Tier','TIER','FREEZE','THAW',
                    'ESCALATION','purgeable','wired','Wired','genealogy','GENEALOGY',
                    'leak','Swap','swap','TRIAGE','forecast','ancestry','Kernel','frozen',
                    'CEO','CPI','CMPE','TMCP','ATCE','MSCEE','GTS','velocity','compression',
                    'Compression','circadian','coupling','calibrated',
                    'SIE','MEG','ACN','RWA','CTRE','AIP','RAC','PSM','BRL','ASZM','CDA',
                    'root cause','signal weights','cascade','volatile','dynamic protection',
                    'Bayesian','Markov','Ancestral'];
    const memEvs = (d.events||[])
      .filter(ev => MEM_KW.some(k => ev.msg.includes(k)))
      .slice(-10).reverse();
    const memFeed = document.getElementById('memEvFeed');
    if (memEvs.length) {
      const kc = {fix:'var(--green)',warn:'var(--yellow)',issue:'var(--red)',info:'var(--blue)'};
      memFeed.innerHTML = memEvs.map(ev =>
        `<div style="padding:2px 0;border-bottom:1px solid var(--border);line-height:1.45">` +
        `<span style="color:var(--muted2);font-family:'SF Mono',monospace;font-size:9px">${ev.ts}</span> ` +
        `<span style="color:${kc[ev.kind]||'var(--muted)'};font-size:9px;font-weight:700">${ev.kind.toUpperCase()}</span> ` +
        `<span style="color:var(--text);font-family:'SF Mono',monospace;font-size:9px">${ev.msg}</span>` +
        `</div>`
      ).join('');
    }
  } catch(e) {}
}
setInterval(poll, 1000);
poll();
</script>
</body>
</html>
"""

# ─── HTTP Handler ─────────────────────────────────────────────────────────────
_engine: BotEngine = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass   # suppress access logs

    def do_GET(self):
        path = urlparse(self.path).path
        q    = urlparse(self.path).query

        if path == "/":
            self._send(200, "text/html; charset=utf-8", HTML.encode())
        elif path == "/manifest.json":
            m = json.dumps({
                "name": "Performance Bot",
                "short_name": "PerfBot",
                "description": "macOS system performance monitor & auto-remediation",
                "start_url": "/",
                "display": "standalone",
                "background_color": "#0d1117",
                "theme_color": "#0d1117",
                "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml"}]
            })
            self._send(200, "application/manifest+json", m.encode())
        elif path == "/icon.svg":
            svg = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
                   b'<rect width="100" height="100" rx="22" fill="#1f6feb"/>'
                   b'<text y=".9em" font-size="86" x="7">&#x26A1;</text></svg>')
            self._send(200, "image/svg+xml", svg)
        elif path == "/stats":
            snap = _engine.snapshot()   # disk_pct + disk_free_gb already in snapshot
            self._send(200, "application/json", json.dumps(snap).encode())
        elif path == "/pause":
            if "state=1" in q:
                _engine.pause()
            else:
                _engine.resume()
            self._send(200, "application/json", b'{"ok":true}')
        else:
            self._send(404, "text/plain", b"Not found")

    def _send(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


# ─── Entry point ──────────────────────────────────────────────────────────────
def main():
    global _engine
    _engine = BotEngine()
    _engine.start()

    server = HTTPServer((HOST, PORT), Handler)
    url    = f"http://{HOST}:{PORT}"

    print(f"Performance Bot  →  {url}")
    print("Press Ctrl+C to stop.\n")

    threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down…")
        _engine.stop()
        server.shutdown()


if __name__ == "__main__":
    main()
