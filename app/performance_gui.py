#!/usr/bin/env python3
"""
Performance Bot — Web GUI
Opens a live dashboard in your browser. No GUI dependencies needed.
Backend: Python http.server  |  Frontend: Chart.js (CDN)
"""

import os, sys, time, json, threading, subprocess, webbrowser
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
        self.events           = []      # ring-buffer of last 200 events
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
        self._last_consumer   = 0.0    # timestamp of last consumer report
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        self._mem_total_gb   = vm.total / 1e9
        self._swap_total_gb  = sw.total / 1e9
        psutil.cpu_percent(interval=None)

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
                "events":        list(self.events[-60:]),
                "actions":       self.actions,
                "issues":        self.issues,
                "freed_mb":      round(self.freed_mb, 0),
                "thermal_pct":   self.thermal_pct,
                "on_battery":    self.on_battery,
                "uptime_s":      int(time.time() - self._start_time),
                "mem_total_gb":  round(self._mem_total_gb, 1),
                "swap_total_gb": round(self._swap_total_gb, 1),
            }

    # ── internal ──────────────────────────────────────────────────────────────
    def _emit(self, kind, msg):
        ev = {"kind": kind, "msg": msg,
              "ts": datetime.now().strftime("%H:%M:%S")}
        with self._lock:
            self.events.append(ev)
            if len(self.events) > 200:
                self.events.pop(0)

    def run(self):
        self._emit("info", "Performance Bot started — monitoring every second.")
        tick = 0
        while self.running:
            try:
                self._collect()
                self._check_cpu()
                if tick % 3  == 0: self._check_memory()
                if tick % 10 == 0: self._check_disk()
                if tick % IDLE_SWEEP_S == 0: self._sweep_idle_services()
                if tick % 30  == 0: self._check_power_mode()
                if tick % 60  == 0: self._check_thermal()
                if tick % 60  == 0: self._check_zombies()
                if tick % 60  == 0: self._track_memory_leaks()
                if tick % 300 == 0 and tick > 0: self._check_caches()
            except Exception as exc:
                self._emit("warn", f"Engine error: {exc}")
            tick += 1
            time.sleep(1)
        self._emit("info", "Performance Bot stopped.")

    def _collect(self):
        cpu  = psutil.cpu_percent(interval=None)
        vm   = psutil.virtual_memory()
        swap = psutil.swap_memory()
        rows = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent",
                                       "memory_percent", "status"]):
            try:
                c = p.cpu_percent(interval=None) / (psutil.cpu_count(logical=True) or 1)
                rows.append((c, p.memory_percent(), p.pid,
                              p.name()[:30], p.status()))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        rows.sort(reverse=True)
        with self._lock:
            self.cpu_hist.append(cpu)
            self.mem_hist.append(vm.percent)
            self.swap_hist.append(swap.percent if swap.total > 0 else 0)
            if len(self.cpu_hist)  > HISTORY_LEN: self.cpu_hist.pop(0)
            if len(self.mem_hist)  > HISTORY_LEN: self.mem_hist.pop(0)
            if len(self.swap_hist) > HISTORY_LEN: self.swap_hist.pop(0)
            self.top_procs = rows[:12]

    def _check_cpu(self):
        with self._lock:
            hist = list(self.cpu_hist)
        if not hist: return
        # restore calmed procs
        for pid in list(self.throttled):
            try:
                p = psutil.Process(pid)
                c = p.cpu_percent(interval=None) / (psutil.cpu_count(logical=True) or 1)
                if c < CPU_WARN / 2:
                    p.nice(0)
                    name = self.throttled.pop(pid)
                    self.actions += 1
                    self._emit("fix",
                        f"Priority restored: {name} (PID {pid}) — CPU back to {c:.0f}%")
            except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError):
                self.throttled.pop(pid, None)
        if hist[-1] < CPU_WARN: return
        # throttle hogs
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "nice"]):
            try:
                if p.name() in PROTECTED: continue
                c = p.cpu_percent(interval=None) / (psutil.cpu_count(logical=True) or 1)
                if c >= CPU_THROTTLE and p.pid not in self.throttled:
                    p.nice(RENICE_VAL)
                    self.throttled[p.pid] = p.name()
                    self.actions += 1
                    self.issues  += 1
                    self._emit("fix",
                        f"AUTO-THROTTLED {p.name()} (PID {p.pid}): "
                        f"{c:.0f}% CPU → nice set to {RENICE_VAL}")
                elif c >= CPU_WARN:
                    self.issues += 1
                    self._emit("warn",
                        f"High CPU: {p.name()} (PID {p.pid}) using {c:.0f}%")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    def _check_memory(self):
        vm = psutil.virtual_memory()
        if vm.percent >= MEM_WARN:
            self.issues += 1
            used_gb = (vm.total - vm.available) / 1e9
            self._emit("issue",
                f"RAM pressure: {vm.percent:.0f}% used "
                f"({used_gb:.1f} / {vm.total/1e9:.1f} GB)")
            # report top consumers with cooldown
            now = time.time()
            if now - self._last_consumer >= CONSUMER_COOL_S:
                self._last_consumer = now
                self._report_memory_consumers()

        swap = psutil.swap_memory()
        if swap.total > 0:
            if swap.percent >= SWAP_WARN and not self._swap_warned:
                self._swap_warned = True
                self._emit("warn",
                    f"Swap in use: {swap.percent:.0f}% "
                    f"({swap.used/1e9:.1f} GB) — system is memory-constrained")
            elif swap.percent < 30:
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
        """Auto-terminate sleeping XPC helpers / widget extensions eating RAM."""
        swept = []
        for p in psutil.process_iter(["pid", "name", "status",
                                       "memory_info", "username", "cpu_percent"]):
            try:
                if p.info["username"] == "root": continue
                name = p.name()
                if name in PROTECTED or name in NEVER_TERMINATE: continue
                if "Python" in name or "python" in name: continue
                if p.pid in self._terminated: continue

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

    def _check_disk(self):
        try:
            d = psutil.disk_usage("/")
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
<title>Performance Bot</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  :root{
    --bg:#0d1117;--panel:#161b22;--border:#21262d;
    --text:#e6edf3;--muted:#656d76;--muted2:#484f58;
    --green:#3fb950;--yellow:#d29922;--red:#f85149;
    --blue:#58a6ff;--orange:#e3b341;--accent:#1f6feb;--purple:#bc8cff;
    --cpu:#ff7b54;--mem:#7ee787;--swap:#58a6ff;
  }
  body{
    background:var(--bg);color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text',sans-serif;
    font-size:13px;min-height:100vh;display:flex;flex-direction:column;
  }

  /* ── title bar ── */
  .titlebar{
    display:flex;align-items:center;gap:10px;
    background:var(--panel);padding:11px 16px;
    border-bottom:1px solid var(--border);
    position:sticky;top:0;z-index:99;
  }
  .dots{display:flex;gap:6px}
  .dot{width:12px;height:12px;border-radius:50%}
  .titlebar h1{font-size:13px;font-weight:700;letter-spacing:.3px}
  .status{display:flex;align-items:center;gap:5px;margin-left:4px}
  .status-dot{
    width:7px;height:7px;border-radius:50%;
    background:var(--green);box-shadow:0 0 6px var(--green);
    animation:pulse 2s infinite;
  }
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
  .status-text{font-size:11px;font-weight:700;color:var(--green)}
  .spacer{flex:1}
  .meta-pills{display:flex;align-items:center;gap:8px}
  .pill{
    display:inline-flex;align-items:center;gap:4px;
    background:var(--bg);border:1px solid var(--border);
    border-radius:20px;padding:3px 10px;font-size:11px;color:var(--muted);
    transition:border-color .2s,color .2s;
  }
  .pill.battery{color:var(--green);border-color:rgba(63,185,80,.3)}
  .pill.thermal-hot{color:var(--red);border-color:rgba(248,81,73,.4)}
  .btn{
    background:var(--border);color:var(--text);border:none;
    padding:5px 13px;border-radius:6px;cursor:pointer;font-size:11px;
    transition:background .15s;
  }
  .btn:hover{background:var(--accent)}

  /* ── cards ── */
  .cards-section{padding:10px 12px 0;display:flex;flex-direction:column;gap:8px}
  .cards-row{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
  .card{
    background:var(--panel);border:1px solid var(--border);
    border-radius:10px;padding:13px 15px;
    transition:border-color .2s;
  }
  .card:hover{border-color:#30363d}
  .card-label{
    font-size:10px;font-weight:700;color:var(--muted);
    letter-spacing:.6px;text-transform:uppercase;margin-bottom:5px;
  }
  .card-val{
    font-size:26px;font-weight:700;line-height:1;
    margin-bottom:5px;transition:color .3s;
  }
  .card-sub{
    font-size:10px;color:var(--muted);
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
  }

  /* ── main grid (3 columns) ── */
  .main{
    display:grid;
    grid-template-columns:minmax(0,1fr) minmax(0,1fr) minmax(0,320px);
    gap:10px;padding:10px 12px 12px;
  }

  /* ── chart panels ── */
  .chart-panel{
    background:var(--panel);border:1px solid var(--border);
    border-radius:10px;padding:13px;
  }
  .panel-hdr{
    display:flex;justify-content:space-between;align-items:baseline;
    margin-bottom:10px;
  }
  .panel-title{
    font-size:10px;font-weight:700;color:var(--muted);
    letter-spacing:.5px;text-transform:uppercase;
  }
  .panel-live{font-size:18px;font-weight:700;transition:color .3s}
  .chart-wrap{position:relative;height:120px}

  /* ── system info panel ── */
  .sysinfo-panel{
    background:var(--panel);border:1px solid var(--border);
    border-radius:10px;padding:13px;
  }
  .sysinfo-row{
    display:flex;justify-content:space-between;align-items:center;
    padding:5px 0;border-bottom:1px solid var(--border);font-size:11px;
  }
  .sysinfo-row:last-child{border:none}
  .sysinfo-key{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.4px;font-weight:700}
  .sysinfo-val{font-family:'SF Mono',monospace;font-size:11px}
  .throttled-list{
    margin-top:6px;font-size:10px;font-family:'SF Mono',monospace;
    color:var(--orange);line-height:1.6;
  }

  /* ── activity feed ── */
  .feed{
    background:var(--panel);border:1px solid var(--border);
    border-radius:10px;padding:13px;
    display:flex;flex-direction:column;
    grid-column:3;grid-row:1/5;
    min-width:0;overflow:hidden;
  }
  .feed-hdr{
    display:flex;justify-content:space-between;align-items:center;
    margin-bottom:10px;flex-shrink:0;
  }
  .feed-title{font-size:10px;font-weight:700;color:var(--muted);letter-spacing:.5px;text-transform:uppercase}
  .ev-count{font-size:11px;color:var(--muted)}
  .feed-body{flex:1;overflow-y:auto;overflow-x:hidden;min-width:0;min-height:0}
  .ev{
    display:flex;gap:7px;padding:5px 7px;margin-bottom:2px;
    border-radius:5px;min-width:0;
    border-left:2px solid transparent;
    background:rgba(255,255,255,.015);
  }
  .ev:hover{background:rgba(255,255,255,.04)}
  .ev-ts{color:var(--muted);white-space:nowrap;flex-shrink:0;font-size:10px;font-family:'SF Mono',monospace;padding-top:1px}
  .ev-badge{font-weight:700;white-space:nowrap;flex-shrink:0;font-size:10px;padding-top:1px;min-width:42px}
  .ev-msg{color:var(--text);word-break:break-word;min-width:0;font-size:11px;font-family:'SF Mono',monospace;line-height:1.5}
  .fix   {border-left-color:var(--green)} .fix   .ev-badge{color:var(--green)}
  .warn  {border-left-color:var(--yellow)}.warn  .ev-badge{color:var(--yellow)}
  .issue {border-left-color:var(--red)}   .issue .ev-badge{color:var(--red)}
  .info  {border-left-color:var(--blue)}  .info  .ev-badge{color:var(--blue)}

  /* ── process table ── */
  .proc-panel{
    background:var(--panel);border:1px solid var(--border);
    border-radius:10px;padding:13px;
    grid-column:1/3;
  }
  table{width:100%;border-collapse:collapse}
  th{
    text-align:left;font-size:10px;font-weight:700;color:var(--muted);
    letter-spacing:.5px;text-transform:uppercase;padding:4px 8px;
    border-bottom:1px solid var(--border);
  }
  td{
    padding:5px 8px;font-family:'SF Mono',monospace;font-size:11px;
    border-bottom:1px solid var(--border);
  }
  tr:last-child td{border:none}
  tr:hover td{background:rgba(255,255,255,.02)}
  .hi  td:nth-child(3){color:var(--yellow)}
  .thr td:nth-child(3){color:var(--orange);font-weight:700}
  .bar-cell{width:60px}
  .bar{height:4px;border-radius:2px;background:var(--border)}
  .bar-fill{height:100%;border-radius:2px;transition:width .4s}
  .thr-badge{
    display:inline-block;
    background:rgba(227,179,65,.12);color:var(--orange);
    border:1px solid rgba(227,179,65,.3);
    border-radius:3px;font-size:9px;font-weight:700;
    padding:0 4px;margin-left:5px;letter-spacing:.3px;
  }

  /* ── footer ── */
  .footer{
    margin-top:auto;padding:7px 16px;
    background:var(--panel);border-top:1px solid var(--border);
    font-size:10px;color:var(--muted);
    display:flex;justify-content:space-between;align-items:center;gap:16px;
  }

  /* scrollbar */
  ::-webkit-scrollbar{width:4px;height:4px}
  ::-webkit-scrollbar-track{background:transparent}
  ::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}
</style>
</head>
<body>

<!-- Title bar -->
<div class="titlebar">
  <div class="dots">
    <div class="dot" style="background:#ff5f57"></div>
    <div class="dot" style="background:#ffbd2e"></div>
    <div class="dot" style="background:#28c840"></div>
  </div>
  <h1>Performance Bot</h1>
  <div class="status">
    <div class="status-dot" id="statusDot"></div>
    <span class="status-text" id="statusText">RUNNING</span>
  </div>
  <span class="spacer"></span>
  <div class="meta-pills">
    <span id="uptimePill" class="pill">⏱ 0s</span>
    <span id="powerPill"  class="pill">⚡ AC</span>
    <span id="thermalPill" class="pill">🌡 Normal</span>
  </div>
  <button class="btn" id="pauseBtn" onclick="togglePause()">Pause Bot</button>
  <button class="btn" onclick="clearFeed()">Clear Log</button>
</div>

<!-- Cards row 1: resources -->
<div class="cards-section">
  <div class="cards-row">
    <div class="card">
      <div class="card-label">CPU</div>
      <div class="card-val" id="cCpu" style="color:var(--cpu)">—</div>
      <div class="card-sub" id="cCpuSub">system-wide</div>
    </div>
    <div class="card">
      <div class="card-label">Memory</div>
      <div class="card-val" id="cMem" style="color:var(--mem)">—</div>
      <div class="card-sub" id="cMemSub">— / — GB</div>
    </div>
    <div class="card">
      <div class="card-label">Swap</div>
      <div class="card-val" id="cSwap" style="color:var(--swap)">—</div>
      <div class="card-sub" id="cSwapSub">— GB used</div>
    </div>
    <div class="card">
      <div class="card-label">Disk</div>
      <div class="card-val" id="cDisk" style="color:var(--blue)">—</div>
      <div class="card-sub" id="cDiskSub">— GB free</div>
    </div>
  </div>
  <!-- Cards row 2: bot stats -->
  <div class="cards-row">
    <div class="card">
      <div class="card-label">Throttled Now</div>
      <div class="card-val" id="cThr" style="color:var(--muted)">0</div>
      <div class="card-sub" id="cThrSub">no active throttles</div>
    </div>
    <div class="card">
      <div class="card-label">Actions Taken</div>
      <div class="card-val" id="cAct" style="color:var(--muted)">0</div>
      <div class="card-sub">auto-remediations</div>
    </div>
    <div class="card">
      <div class="card-label">Issues Found</div>
      <div class="card-val" id="cIss" style="color:var(--muted)">0</div>
      <div class="card-sub">warnings + issues</div>
    </div>
    <div class="card">
      <div class="card-label">RAM Freed</div>
      <div class="card-val" id="cFreed" style="color:var(--muted)">0 MB</div>
      <div class="card-sub">idle service sweep</div>
    </div>
  </div>
</div>

<!-- Main grid -->
<div class="main">

  <!-- CPU chart (col 1, row 1) -->
  <div class="chart-panel">
    <div class="panel-hdr">
      <span class="panel-title">CPU — 90 s</span>
      <span class="panel-live" id="cpuLive" style="color:var(--cpu)">—</span>
    </div>
    <div class="chart-wrap"><canvas id="cpuChart"></canvas></div>
  </div>

  <!-- Memory chart (col 2, row 1) -->
  <div class="chart-panel">
    <div class="panel-hdr">
      <span class="panel-title">Memory — 90 s</span>
      <span class="panel-live" id="memLive" style="color:var(--mem)">—</span>
    </div>
    <div class="chart-wrap"><canvas id="memChart"></canvas></div>
  </div>

  <!-- Activity feed (col 3, rows 1-4) -->
  <div class="feed">
    <div class="feed-hdr">
      <span class="feed-title">Activity Log</span>
      <span class="ev-count" id="evCount">0 events</span>
    </div>
    <div class="feed-body" id="feedBody"></div>
  </div>

  <!-- Swap chart (col 1, row 2) -->
  <div class="chart-panel">
    <div class="panel-hdr">
      <span class="panel-title">Swap — 90 s</span>
      <span class="panel-live" id="swapLive" style="color:var(--swap)">—</span>
    </div>
    <div class="chart-wrap"><canvas id="swapChart"></canvas></div>
  </div>

  <!-- System info panel (col 2, row 2) -->
  <div class="sysinfo-panel">
    <div class="panel-title" style="margin-bottom:10px">System</div>
    <div class="sysinfo-row">
      <span class="sysinfo-key">Total RAM</span>
      <span class="sysinfo-val" id="siMemTotal">—</span>
    </div>
    <div class="sysinfo-row">
      <span class="sysinfo-key">Total Swap</span>
      <span class="sysinfo-val" id="siSwapTotal">—</span>
    </div>
    <div class="sysinfo-row">
      <span class="sysinfo-key">Disk Free</span>
      <span class="sysinfo-val" id="siDiskFree">—</span>
    </div>
    <div class="sysinfo-row">
      <span class="sysinfo-key">Throttled</span>
      <span class="sysinfo-val" id="siThrCount" style="color:var(--muted)">none</span>
    </div>
    <div class="throttled-list" id="siThrList"></div>
  </div>

  <!-- Process table (col 1-2, row 3) -->
  <div class="proc-panel">
    <div class="panel-title" style="margin-bottom:8px">Top Processes</div>
    <table>
      <thead>
        <tr>
          <th>Process</th><th>PID</th>
          <th>CPU %</th><th>CPU</th>
          <th>MEM %</th><th>MEM</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody id="procBody"></tbody>
    </table>
  </div>

</div><!-- /main -->

<!-- Footer -->
<div class="footer">
  <span id="lastUpdate">Initializing…</span>
  <span id="footerRight">Poll: 1 s · Throttle: &gt;85% CPU · Warn: &gt;80% RAM · Sweep: idle XPC/widgets</span>
</div>

<script>
// ── Chart factory ─────────────────────────────────────────────────────────────
function makeChart(id, color, fill, warnPct) {
  const ctx = document.getElementById(id).getContext('2d');
  const warnPlugin = {
    id: 'warnLine',
    beforeDraw(chart) {
      if (!warnPct) return;
      const {ctx: c, chartArea, scales} = chart;
      if (!chartArea) return;
      const y = scales.y.getPixelForValue(warnPct);
      c.save();
      c.strokeStyle = 'rgba(248,81,73,.3)';
      c.lineWidth = 1;
      c.setLineDash([3, 5]);
      c.beginPath();
      c.moveTo(chartArea.left, y);
      c.lineTo(chartArea.right, y);
      c.stroke();
      c.setLineDash([]);
      c.restore();
    }
  };
  return new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        data: [], borderColor: color, borderWidth: 1.5,
        backgroundColor: fill, fill: true,
        tension: 0.3, pointRadius: 0,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      scales: {
        x: { display: false },
        y: {
          min: 0, max: 100,
          ticks: {
            color: '#656d76', stepSize: 25,
            callback: v => v + '%', font: { size: 10 }
          },
          grid: { color: '#21262d' },
          border: { display: false },
        }
      },
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
    },
    plugins: [warnPlugin],
  });
}

const cpuChart  = makeChart('cpuChart',  '#ff7b54', 'rgba(255,123,84,.1)',   80);
const memChart  = makeChart('memChart',  '#7ee787', 'rgba(126,231,135,.1)',  80);
const swapChart = makeChart('swapChart', '#58a6ff', 'rgba(88,166,255,.1)',   50);

function updateChart(chart, data) {
  chart.data.labels = data.map((_, i) => i);
  chart.data.datasets[0].data = data;
  chart.update('none');
}

// ── State ─────────────────────────────────────────────────────────────────────
let evCount = 0, seenEvents = new Set(), paused = false;
let memTotalGb = 0, swapTotalGb = 0;

// ── Helpers ───────────────────────────────────────────────────────────────────
function colorFor(v, lo, hi, def) {
  return v > hi ? 'var(--red)' : v > lo ? 'var(--yellow)' : def;
}
function setCard(id, text, color) {
  const el = document.getElementById(id);
  el.textContent = text;
  if (color !== undefined) el.style.color = color;
}
function setSub(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}
function fmtUptime(s) {
  if (s < 60)   return s + 's';
  if (s < 3600) return Math.floor(s/60) + 'm ' + (s % 60) + 's';
  return Math.floor(s/3600) + 'h ' + Math.floor((s % 3600) / 60) + 'm';
}

// ── Process table ─────────────────────────────────────────────────────────────
function barCell(pct, color) {
  return `<td class="bar-cell">
    <div class="bar">
      <div class="bar-fill" style="width:${Math.min(pct,100).toFixed(1)}%;background:${color}"></div>
    </div>
  </td>`;
}
function buildProcTable(procs, thrPids) {
  document.getElementById('procBody').innerHTML = procs.map(([cpu, mem, pid, name, status]) => {
    const thr = thrPids.includes(pid);
    const hiCpu = !thr && cpu >= 70;
    const cls = thr ? 'thr' : hiCpu ? 'hi' : '';
    const cpuColor = thr ? 'var(--orange)' : hiCpu ? 'var(--yellow)' : 'var(--cpu)';
    const memColor = mem >= 10 ? 'var(--red)' : mem >= 4 ? 'var(--yellow)' : 'var(--mem)';
    const badge = thr ? '<span class="thr-badge">THROTTLED</span>' : '';
    return `<tr class="${cls}">
      <td>${name}${badge}</td>
      <td>${pid}</td>
      <td>${cpu.toFixed(1)}%</td>
      ${barCell(cpu, cpuColor)}
      <td>${mem.toFixed(1)}%</td>
      ${barCell(mem * 8, memColor)}
      <td>${status}</td>
    </tr>`;
  }).join('');
}

// ── Activity feed ──────────────────────────────────────────────────────────────
const BADGE = { fix:'✓ FIX', warn:'⚠ WARN', issue:'✗ ISSUE', info:'ℹ INFO' };
function addEvent(ev) {
  const key = ev.ts + ev.msg;
  if (seenEvents.has(key)) return;
  seenEvents.add(key);
  evCount++;
  document.getElementById('evCount').textContent = evCount + ' events';
  const div = document.createElement('div');
  div.className = 'ev ' + ev.kind;
  div.innerHTML =
    `<span class="ev-ts">${ev.ts}</span>` +
    `<span class="ev-badge">${BADGE[ev.kind] || '?'}</span>` +
    `<span class="ev-msg">${ev.msg}</span>`;
  document.getElementById('feedBody').prepend(div);
}
function clearFeed() {
  evCount = 0; seenEvents.clear();
  document.getElementById('evCount').textContent = '0 events';
  document.getElementById('feedBody').innerHTML = '';
}

// ── Pause / Resume ─────────────────────────────────────────────────────────────
function togglePause() {
  paused = !paused;
  const dot = document.getElementById('statusDot');
  const txt = document.getElementById('statusText');
  const btn = document.getElementById('pauseBtn');
  if (paused) {
    dot.style.cssText = 'background:var(--yellow);box-shadow:0 0 6px var(--yellow)';
    txt.style.color = 'var(--yellow)'; txt.textContent = 'PAUSED';
    btn.textContent = 'Resume Bot';
  } else {
    dot.style.cssText = 'background:var(--green);box-shadow:0 0 6px var(--green)';
    txt.style.color = 'var(--green)'; txt.textContent = 'RUNNING';
    btn.textContent = 'Pause Bot';
  }
  fetch('/pause?state=' + (paused ? '1' : '0'));
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
      // ── charts ──
      updateChart(cpuChart,  d.cpu_hist  || []);
      updateChart(memChart,  d.mem_hist  || []);
      updateChart(swapChart, d.swap_hist || []);

      const cpu  = (d.cpu_hist  || []).at(-1) ?? 0;
      const mem  = (d.mem_hist  || []).at(-1) ?? 0;
      const swap = (d.swap_hist || []).at(-1) ?? 0;

      document.getElementById('cpuLive').textContent  = cpu.toFixed(0)  + '%';
      document.getElementById('memLive').textContent  = mem.toFixed(0)  + '%';
      document.getElementById('swapLive').textContent = swap.toFixed(0) + '%';
      document.getElementById('cpuLive').style.color  = colorFor(cpu,  60, 80, 'var(--cpu)');
      document.getElementById('memLive').style.color  = colorFor(mem,  60, 80, 'var(--mem)');
      document.getElementById('swapLive').style.color = swap > 50 ? 'var(--yellow)' : 'var(--swap)';

      // ── resource cards ──
      setCard('cCpu',  cpu.toFixed(0) + '%', colorFor(cpu, 60, 80, 'var(--cpu)'));
      setSub('cCpuSub', 'system-wide');

      const memUsed = (memTotalGb * mem / 100).toFixed(1);
      setCard('cMem',  mem.toFixed(0) + '%', colorFor(mem, 60, 80, 'var(--mem)'));
      setSub('cMemSub', memUsed + ' / ' + memTotalGb.toFixed(1) + ' GB');

      const swapUsed = (swapTotalGb * swap / 100).toFixed(2);
      setCard('cSwap', swap.toFixed(0) + '%', swap > 50 ? 'var(--yellow)' : 'var(--swap)');
      setSub('cSwapSub', swapUsed + ' / ' + swapTotalGb.toFixed(1) + ' GB');

      const disk = d.disk_pct ?? 0;
      setCard('cDisk', disk.toFixed(0) + '%',
        disk > 90 ? 'var(--red)' : disk > 80 ? 'var(--yellow)' : 'var(--blue)');
      setSub('cDiskSub', d.disk_free_gb ? d.disk_free_gb.toFixed(1) + ' GB free' : '');

      // ── bot stat cards ──
      const thrKeys  = Object.keys(d.throttled || {});
      const thrNames = Object.values(d.throttled || {});
      setCard('cThr', String(thrKeys.length),
        thrKeys.length > 0 ? 'var(--orange)' : 'var(--muted)');
      setSub('cThrSub',
        thrKeys.length > 0 ? thrNames.slice(0, 2).join(', ') : 'no active throttles');

      setCard('cAct',   String(d.actions), d.actions > 0 ? 'var(--green)' : 'var(--muted)');
      setCard('cIss',   String(d.issues),  d.issues  > 0 ? 'var(--red)'   : 'var(--muted)');

      const freed = d.freed_mb || 0;
      setCard('cFreed',
        freed >= 1024 ? (freed / 1024).toFixed(1) + ' GB' : freed.toFixed(0) + ' MB',
        freed > 0 ? 'var(--blue)' : 'var(--muted)');

      // ── process table ──
      buildProcTable(d.top_procs || [], thrKeys.map(Number));

      // ── system info panel ──
      document.getElementById('siMemTotal').textContent =
        memTotalGb ? memTotalGb.toFixed(1) + ' GB' : '—';
      document.getElementById('siSwapTotal').textContent =
        swapTotalGb ? swapTotalGb.toFixed(1) + ' GB' : 'none';
      document.getElementById('siDiskFree').textContent =
        d.disk_free_gb ? d.disk_free_gb.toFixed(1) + ' GB' : '—';

      const siThr = document.getElementById('siThrCount');
      const siList = document.getElementById('siThrList');
      if (thrKeys.length > 0) {
        siThr.textContent = thrKeys.length + ' process' + (thrKeys.length > 1 ? 'es' : '');
        siThr.style.color = 'var(--orange)';
        siList.textContent = thrNames.join('\n');
      } else {
        siThr.textContent = 'none'; siThr.style.color = 'var(--muted)';
        siList.textContent = '';
      }

      // ── titlebar pills ──
      document.getElementById('uptimePill').textContent = '⏱ ' + fmtUptime(d.uptime_s || 0);

      const pp = document.getElementById('powerPill');
      if (d.on_battery) {
        pp.textContent = '🔋 Battery'; pp.className = 'pill battery';
      } else {
        pp.textContent = '⚡ AC'; pp.className = 'pill';
      }

      const tp = document.getElementById('thermalPill');
      const tpct = d.thermal_pct ?? 100;
      if (tpct < 100) {
        tp.textContent = '🌡 ' + tpct + '%'; tp.className = 'pill thermal-hot';
      } else {
        tp.textContent = '🌡 Normal'; tp.className = 'pill';
      }

      // ── footer ──
      document.getElementById('lastUpdate').textContent =
        'Last update: ' + new Date().toLocaleTimeString();
    }

    // events always drain (even when paused)
    (d.events || []).forEach(ev => addEvent(ev));

  } catch (e) { /* server restarting */ }
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
        elif path == "/stats":
            snap = _engine.snapshot()
            try:
                d = psutil.disk_usage("/")
                snap["disk_pct"]     = d.percent
                snap["disk_free_gb"] = round(d.free / 1e9, 1)
            except Exception:
                snap["disk_pct"]     = 0
                snap["disk_free_gb"] = 0
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
