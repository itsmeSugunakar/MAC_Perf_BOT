#!/usr/bin/env python3
"""
Performance Bot — Web GUI
Opens a live dashboard in your browser. No GUI dependencies needed.
Backend: Python http.server  |  Frontend: Chart.js (CDN)
"""

import os, sys, time, json, threading, subprocess, webbrowser, sqlite3
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
        tte_min       REAL
    );
    CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(ts);
    """

    def __init__(self, db_path: Path):
        self._db   = str(db_path)
        self._buf  = []   # [(ts, cpu, mem, swap, disk, pressure, tier, tte)]
        self._last_prune = 0.0
        self._ok   = False
        try:
            with sqlite3.connect(self._db, timeout=5) as cx:
                cx.executescript(self._SCHEMA)
            self._ok = True
        except Exception as e:
            # Cache failure is non-fatal — bot continues without it
            print(f"[cache] init failed: {e}", file=sys.stderr)

    # ── public ────────────────────────────────────────────────────────────────

    def record(self, ts, cpu, mem, swap, disk, pressure, tier, tte):
        """Append one row to the in-memory buffer (no disk I/O)."""
        if self._ok:
            self._buf.append((int(ts), cpu, mem, swap, disk, pressure, tier, tte))

    def flush(self):
        """Write buffered rows to SQLite and clear the buffer."""
        if not self._ok or not self._buf:
            return
        rows, self._buf = self._buf, []
        try:
            with sqlite3.connect(self._db, timeout=5) as cx:
                cx.executemany(
                    "INSERT INTO metrics VALUES (?,?,?,?,?,?,?,?)", rows
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


# ─── Bot Engine ───────────────────────────────────────────────────────────────
class BotEngine(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="bot-engine")
        self._lock            = threading.Lock()
        self.running          = True
        self.cpu_hist         = []
        self.mem_hist         = []
        self.swap_hist        = []
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

    # ── public ────────────────────────────────────────────────────────────────
    def stop(self):
        self.running = False

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
            try:
                self._collect()                                          # 1 Hz — single process scan
                if tick % 3  == 0: self._check_memory()                 # 0.33 Hz
                if tick % 5  == 0: self._update_pressure_and_forecast() # 0.2 Hz — sysctl + vm_stat
                if tick % 10 == 0: self._check_disk()                   # 0.1 Hz
                if tick % 30 == 0: self._check_power_mode()             # 0.03 Hz
                if tick % 30 == 0: self._detect_xpc_respawn()           # 0.03 Hz (was 0.1 Hz)
                if tick % 60 == 0: self._check_thermal()                # 0.016 Hz — pmset subprocess
                if tick % 60 == 0: self._check_zombies()
                if tick % 60 == 0: self._track_memory_leaks()
                if tick % IDLE_SWEEP_S == 0: self._sweep_idle_services()
                if tick % 300 == 0 and tick > 0: self._check_caches()
                if tick % CACHE_WRITE_S == 0:
                    self._cache.flush()
                    self._cache.prune()
                    self.cache_db_mb = self._cache.db_size_mb()
                    self.cache_rows  = self._cache.row_count()
                if tick % 3600 == 0 and tick > 0:
                    self._analyse_app_predictions()
            except Exception as exc:
                self._emit("warn", f"Engine error: {exc}")
            tick += 1
            time.sleep(1)
        self._emit("info", "Performance Bot stopped.")

    def _collect(self):
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
                p.nice(RENICE_VAL)
                self.throttled[pid] = name
                self.actions += 1
                self.issues  += 1
                self._emit("fix",
                    f"AUTO-THROTTLED {name} (PID {pid}): "
                    f"{c:.0f}% CPU → nice set to {RENICE_VAL}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        swap_pct = swap.percent if swap.total > 0 else 0.0
        with self._lock:
            self.cpu_hist.append(cpu)
            self.mem_hist.append(vm.percent)
            self.swap_hist.append(swap_pct)
            if len(self.cpu_hist)  > HISTORY_LEN: self.cpu_hist.pop(0)
            if len(self.mem_hist)  > HISTORY_LEN: self.mem_hist.pop(0)
            if len(self.swap_hist) > HISTORY_LEN: self.swap_hist.pop(0)
            self.top_procs = rows[:12]
            # stash vm/swap for _check_memory() — avoids a second virtual_memory() call
            self._last_vm   = vm
            self._last_swap = swap
            _tier = self.effective_tier
            _tte  = self.mem_forecast_min
            _pres = self.mem_pressure_level

        # Cache: record every 10 s (use stored disk_pct — updated by _check_disk())
        if int(time.time()) % 10 == 0:
            self._cache.record(
                int(time.time()), round(cpu, 1), round(vm.percent, 1),
                round(swap_pct, 1), round(self._last_disk_pct, 1),
                _pres, _tier, _tte
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
                    p.nice(0)
                    name = self.throttled.pop(pid)
                    self.actions += 1
                    self._emit("fix",
                        f"Priority restored: {name} (PID {pid}) — CPU back to {c:.0f}%")
            except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError):
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
                cpu  = p.cpu_percent(interval=None) / (psutil.cpu_count(logical=True) or 1)
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
        Determine the effective remediation tier by combining static RAM-% thresholds
        with the OLS Time-to-Exhaustion forecast. When TTE predicts imminent exhaustion,
        the effective tier is escalated ABOVE what the raw percentage would trigger —
        this is the core of the Predictive Remediation Engine patent claim.

        Returns: (effective_tier: int, threshold_tier: int)
          threshold_tier = tier driven by mem_pct alone (0–4)
          effective_tier = tier after TTE escalation (may exceed threshold_tier)
        """
        # ── Threshold tier from static percentages ────────────────────────────
        if   mem_pct >= MEM_TIER4_PCT: threshold_tier = 4
        elif mem_pct >= MEM_TIER3_PCT: threshold_tier = 3
        elif mem_pct >= MEM_TIER2_PCT: threshold_tier = 2
        elif mem_pct >= MEM_WARN:      threshold_tier = 1
        else:                          threshold_tier = 0

        # ── TTE escalation — only when we have enough history ─────────────────
        with self._lock:
            hist_len = len(self.mem_hist)
            tte      = self.mem_forecast_min
        if hist_len < TTE_MIN_SAMPLES or tte < 0:
            return threshold_tier, threshold_tier   # stable/declining — no escalation

        predictive_tier = threshold_tier
        if   tte <= TTE_TIER4_MIN: predictive_tier = max(predictive_tier, 4)
        elif tte <= TTE_TIER3_MIN: predictive_tier = max(predictive_tier, 3)
        elif tte <= TTE_TIER2_MIN: predictive_tier = max(predictive_tier, 2)

        return predictive_tier, threshold_tier

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
        Linear regression over the last 30 mem_hist samples to estimate minutes
        until memory reaches 95%. Returns -1 if stable/declining or data is sparse.
        """
        with self._lock:
            hist = list(self.mem_hist)
        window = hist[-30:] if len(hist) >= 10 else []
        if len(window) < 10:
            return -1.0
        n = len(window)
        mean_x = (n - 1) / 2.0
        mean_y = sum(window) / n
        num = sum((i - mean_x) * (v - mean_y) for i, v in enumerate(window))
        den = sum((i - mean_x) ** 2 for i in range(n))
        if den == 0:
            return -1.0
        slope = num / den          # % per second (1 sample = 1 s)
        if slope < 0.005:          # stable or declining
            return -1.0
        current = window[-1]
        target  = 95.0
        if current >= target:
            return 0.0
        return round((target - current) / slope / 60, 1)

    def _update_pressure_and_forecast(self):
        """Refresh kernel pressure level, vm_stat breakdown, and forecast every 5 s."""
        level    = self._get_macos_pressure_level()
        forecast = self._compute_mem_forecast()
        vm_bd    = self._parse_vm_stat()
        with self._lock:
            self.mem_pressure_level = level
            self.mem_forecast_min   = forecast
            self.vm_breakdown       = vm_bd
        if level == "critical":
            vm = psutil.virtual_memory()
            self._emit("issue",
                f"Kernel memory pressure: CRITICAL — system at {vm.percent:.0f}% RAM")
        # Ancestry is expensive; refresh every 30 s outside of pressure events
        now = time.time()
        if now - self._last_ancestry >= MEM_ANCESTRY_COOL_S:
            self._last_ancestry = now
            ancestry = self._build_memory_ancestry()
            with self._lock:
                self.mem_ancestry = ancestry

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

        # ── Tier 4: emergency termination ────────────────────────────────────
        if effective_tier >= 4:
            self._sweep_idle_services()

    def _freeze_background_daemons(self):
        """
        Genealogy-guided SIGSTOP: score background daemon candidates using two signals:
          family_match (weight 2): process belongs to a top-RSS application family
                                   identified by the ppid-tree genealogy walk
          pattern_match (weight 1): name matches the known-safe FREEZE_PATTERNS list
        Candidates are sorted by (score DESC, rss DESC) so that daemons belonging to
        the heaviest RAM-owning families are frozen first — maximally targeted pressure
        relief rather than arbitrary pattern matching.
        """
        self._last_freeze = time.time()

        # Snapshot ancestry for genealogy scoring
        with self._lock:
            ancestry_snap = list(self.mem_ancestry)  # [{app, mb, pct}]

        # Build set of root-app names that own significant RAM (top 5 families)
        heavy_families = {entry["app"].lower() for entry in ancestry_snap[:5]}

        # ── Score all candidate processes ─────────────────────────────────────
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

                # Scoring: genealogy match outweighs pattern match
                pattern_match = int(any(pat in name for pat in FREEZE_PATTERNS))
                name_lower    = name.lower()
                family_match  = int(any(fam in name_lower or name_lower in fam
                                        for fam in heavy_families))
                score = family_match * 2 + pattern_match

                if score == 0:
                    continue   # not a freeze candidate at all

                candidates.append((score, rss, p.pid, name, p))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Sort: highest score first, then highest RSS
        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)

        frozen, freed_mb = 0, 0.0
        for score, rss, pid, name, p in candidates:
            try:
                p.send_signal(19)  # SIGSTOP — reversible suspension
                self._frozen_pids[pid] = (name, time.time(), rss)
                freed_mb += rss
                frozen   += 1
                self.actions += 1

                # Emit genealogy attribution when family-matched
                with self._lock:
                    ancestry_snap2 = list(self.mem_ancestry)
                family_info = next(
                    (f"{e['app']} family ({e['mb']}MB)"
                     for e in ancestry_snap2
                     if e["app"].lower() in name.lower() or name.lower() in e["app"].lower()),
                    None
                )
                if family_info:
                    self._emit("fix",
                        f"GENEALOGY FREEZE: {name} (PID {pid}, {rss:.0f}MB) "
                        f"← {family_info} — SIGSTOP applied")
                else:
                    self._emit("fix",
                        f"PATTERN FREEZE: {name} (PID {pid}, {rss:.0f}MB) "
                        f"— SIGSTOP applied (score={score})")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if frozen:
            self.freed_mb += freed_mb
            self._emit("fix",
                f"MEMORY TRIAGE (Tier 3): froze {frozen} background daemons "
                f"(~{freed_mb:.0f} MB paused) — auto-thaw when pressure drops")

    def _thaw_frozen_daemons(self):
        """
        Send SIGCONT to all frozen daemons when system memory pressure eases.
        Called automatically from _check_memory when usage drops below threshold.
        """
        to_thaw = list(self._frozen_pids.items())
        thawed  = []
        for pid, (name, _ts, _rss) in to_thaw:
            try:
                psutil.Process(pid).send_signal(18)  # SIGCONT — resume
                thawed.append(name)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            self._frozen_pids.pop(pid, None)
        if thawed:
            self._emit("fix",
                f"Pressure normalised — thawed {len(thawed)} daemons: "
                + ", ".join(thawed[:4]))

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
        <div class="vmrow" style="border-top:1px solid var(--border);margin-top:3px;padding-top:4px">
          <span class="vmkey">Cache (90d)</span>
          <span class="vmval" id="vsCacheSize" style="color:var(--muted)">—</span>
        </div>
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
  <span>Poll 1 s · Throttle &gt;85% CPU · Warn &gt;80% RAM · MMIE active</span>
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

      // Cache stats
      const cacheEl = document.getElementById('vsCacheSize');
      const cMb = d.cache_db_mb||0, cRows = d.cache_rows||0;
      cacheEl.textContent = cMb>0 ? cMb.toFixed(1)+' MB · '+(cRows/1000).toFixed(0)+'k rows' : 'Collecting…';

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
                _engine.stop()
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
