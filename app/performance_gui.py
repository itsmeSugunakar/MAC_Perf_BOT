#!/usr/bin/env python3
"""
Performance Bot — Web GUI
Opens a live dashboard in your browser. No GUI dependencies needed.
Backend: Python http.server  |  Frontend: Chart.js (CDN)
"""

import os, sys, time, json, queue, threading, subprocess, webbrowser
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

PORT         = 8765
HOST         = "127.0.0.1"
LOG_DIR      = Path.home() / "Library" / "Logs" / "performance-bot"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ─── Bot Engine ───────────────────────────────────────────────────────────────
PROTECTED = {
    "kernel_task", "launchd", "WindowServer", "loginwindow", "Finder",
    "Dock", "SystemUIServer", "coreaudiod", "cfprefsd", "mds",
    "mds_stores", "mdworker", "performance_bot", "performance_gui",
    "Python", "python3", "python",
}
# Never terminate even if they match idle patterns
NEVER_TERMINATE = {
    "com.apple.AuthenticationServices.Helper",
    "CredentialProviderExtensionHelper",
    "Keychain Circle Notification",
    "com.apple.iCloud.Keychain",
}
# Patterns that identify safe-to-terminate idle XPC helpers / widget services
IDLE_SERVICE_PATTERNS = (
    "Widget", "Extension", "XPCService", "HelperService",
    "BookkeepingService", "PredictionIntents", "MTLCompilerService",
    "VTEncoderXPCService", "VTDecoderXPCService", "WallpaperVideo",
    "CloudTelemetryService", "IntelligencePlatformComputeService",
    "SAExtensionOrchestrator", "SiriNCService", "SiriSuggestions",
    "SiriInference", "ServiceExtension", "NewsTag",
    "AppPredictionIntents",
)
CPU_WARN      = 70.0
CPU_THROTTLE  = 85.0
MEM_WARN      = 80.0
RENICE_VAL    = 10
HISTORY_LEN   = 90
IDLE_MB_FLOOR = 15      # only target idle services eating more than this
IDLE_SWEEP_S  = 30      # run idle-service sweep every N seconds


class BotEngine(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="bot-engine")
        self._lock        = threading.Lock()
        self.running      = True
        self.cpu_hist     = []
        self.mem_hist     = []
        self.top_procs    = []
        self.throttled    = {}      # pid → name
        self.events       = []      # ring-buffer of last 200 events
        self.actions      = 0
        self.issues       = 0
        self.freed_mb     = 0.0     # cumulative RAM freed by terminating idle services
        self._swap_warned = False
        self._terminated  = set()   # PIDs we already terminated this session
        psutil.cpu_percent(interval=None)

    # ── public ────────────────────────────────────────────────────────────────
    def stop(self):
        self.running = False

    def snapshot(self):
        with self._lock:
            return {
                "cpu_hist":  list(self.cpu_hist),
                "mem_hist":  list(self.mem_hist),
                "top_procs": list(self.top_procs),
                "throttled": dict(self.throttled),
                "events":    list(self.events[-60:]),
                "actions":   self.actions,
                "issues":    self.issues,
                "freed_mb":  round(self.freed_mb, 0),
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
            except Exception as exc:
                self._emit("warn", f"Engine error: {exc}")
            tick += 1
            time.sleep(1)
        self._emit("info", "Performance Bot stopped.")

    def _collect(self):
        cpu  = psutil.cpu_percent(interval=None)
        mem  = psutil.virtual_memory().percent
        rows = []
        for p in psutil.process_iter(["pid","name","cpu_percent",
                                       "memory_percent","status"]):
            try:
                c = p.cpu_percent(interval=None) / (psutil.cpu_count(logical=True) or 1)
                rows.append((c, p.memory_percent(), p.pid,
                              p.name()[:30], p.status()))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        rows.sort(reverse=True)
        with self._lock:
            self.cpu_hist.append(cpu)
            self.mem_hist.append(mem)
            if len(self.cpu_hist) > HISTORY_LEN: self.cpu_hist.pop(0)
            if len(self.mem_hist) > HISTORY_LEN: self.mem_hist.pop(0)
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
                    self._emit("fix", f"Priority restored: {name} (PID {pid}) — CPU back to {c:.0f}%")
            except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError):
                self.throttled.pop(pid, None)
        if hist[-1] < CPU_WARN: return
        # throttle hogs
        for p in psutil.process_iter(["pid","name","cpu_percent","nice"]):
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
            self._emit("issue",
                f"RAM pressure: {vm.percent:.0f}% used "
                f"({(vm.total-vm.available)/1e9:.1f}/{vm.total/1e9:.1f} GB)")
        swap = psutil.swap_memory()
        if swap.total > 0:
            if swap.percent >= 50 and not self._swap_warned:
                self._swap_warned = True
                self._emit("warn",
                    f"Swap active: {swap.percent:.0f}% ({swap.used/1e9:.1f} GB used)")
            elif swap.percent < 30:
                self._swap_warned = False

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
                f"Idle sweep done: {len(swept)} services cleared, "
                f"~{total:.0f} MB freed (total freed this session: {self.freed_mb:.0f} MB)")

    def _check_disk(self):
        try:
            d = psutil.disk_usage("/")
            if d.percent >= 90:
                self.issues += 1
                self._emit("issue",
                    f"Low disk: {d.percent:.0f}% full ({d.free/1e9:.1f} GB free)")
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
    --text:#e6edf3;--muted:#656d76;
    --green:#3fb950;--yellow:#d29922;--red:#f85149;
    --blue:#58a6ff;--orange:#e3b341;--accent:#1f6feb;
    --cpu:#ff7b54;--mem:#7ee787;
  }
  body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text',sans-serif;font-size:13px}

  /* ── title bar ── */
  .titlebar{
    display:flex;align-items:center;gap:10px;
    background:var(--panel);padding:14px 18px;
    border-bottom:1px solid var(--border);position:sticky;top:0;z-index:99;
  }
  .dots{display:flex;gap:6px}
  .dot{width:12px;height:12px;border-radius:50%}
  .titlebar h1{font-size:14px;font-weight:700;letter-spacing:.3px}
  .status{display:flex;align-items:center;gap:5px;margin-left:6px}
  .status-dot{width:8px;height:8px;border-radius:50%;background:var(--green);
               box-shadow:0 0 6px var(--green);animation:pulse 2s infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
  .status-text{font-size:11px;font-weight:700;color:var(--green)}
  .spacer{flex:1}
  .btn{
    background:var(--border);color:var(--text);border:none;
    padding:5px 14px;border-radius:6px;cursor:pointer;font-size:12px;
    transition:background .15s;
  }
  .btn:hover{background:var(--accent)}

  /* ── cards ── */
  .cards{display:flex;gap:10px;padding:12px 14px}
  .card{
    flex:1;background:var(--panel);border:1px solid var(--border);
    border-radius:10px;padding:14px 16px;
  }
  .card-label{font-size:10px;font-weight:700;color:var(--muted);
               letter-spacing:.6px;text-transform:uppercase;margin-bottom:6px}
  .card-val{font-size:28px;font-weight:700;line-height:1}

  /* ── main grid ── */
  .main{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px;padding:0 14px 14px}

  /* ── chart panel ── */
  .chart-panel{
    background:var(--panel);border:1px solid var(--border);
    border-radius:10px;padding:14px;
  }
  .panel-title{font-size:12px;font-weight:700;color:var(--muted);
                letter-spacing:.5px;text-transform:uppercase;margin-bottom:10px}
  .chart-wrap{position:relative;height:160px}

  /* ── activity feed ── */
  .feed{
    background:var(--panel);border:1px solid var(--border);
    border-radius:10px;padding:14px;display:flex;flex-direction:column;
    grid-row:span 2;
    min-width:0;overflow:hidden;        /* prevent grid blowout */
  }
  .feed-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;min-width:0}
  .feed-title{font-size:12px;font-weight:700;color:var(--muted);letter-spacing:.5px;text-transform:uppercase}
  .event-count{font-size:11px;color:var(--muted);white-space:nowrap}
  .feed-body{flex:1;overflow-y:auto;overflow-x:hidden;font-family:'SF Mono',monospace;font-size:11px;min-width:0}
  .ev{display:flex;gap:6px;padding:3px 0;border-bottom:1px solid var(--border);min-width:0;width:100%}
  .ev-ts{color:var(--muted);white-space:nowrap;flex-shrink:0}
  .ev-badge{font-weight:700;white-space:nowrap;flex-shrink:0;font-size:10px}
  .ev-msg{color:var(--text);word-break:break-all;overflow-wrap:anywhere;min-width:0;overflow:hidden}
  .fix   .ev-badge{color:var(--green)}
  .warn  .ev-badge{color:var(--yellow)}
  .issue .ev-badge{color:var(--red)}
  .info  .ev-badge{color:var(--blue)}

  /* ── process table ── */
  .proc-panel{
    background:var(--panel);border:1px solid var(--border);
    border-radius:10px;padding:14px;
    grid-column:1/-1;
  }
  table{width:100%;border-collapse:collapse}
  th{text-align:left;font-size:10px;font-weight:700;color:var(--muted);
     letter-spacing:.5px;text-transform:uppercase;padding:4px 10px;
     border-bottom:1px solid var(--border)}
  td{padding:4px 10px;font-family:'SF Mono',monospace;font-size:11px;
     border-bottom:1px solid var(--border)}
  tr:last-child td{border:none}
  .hi  td:nth-child(3){color:var(--yellow)}
  .thr td:nth-child(3){color:var(--orange);font-weight:700}
  .bar-cell{width:80px}
  .bar{height:6px;border-radius:3px;background:var(--border)}
  .bar-fill{height:100%;border-radius:3px}

  /* ── footer ── */
  .footer{
    padding:8px 18px;background:var(--panel);
    border-top:1px solid var(--border);
    font-size:10px;color:var(--muted);
    display:flex;justify-content:space-between;
  }

  /* scrollbar */
  ::-webkit-scrollbar{width:5px;height:5px}
  ::-webkit-scrollbar-track{background:var(--bg)}
  ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
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
  <button class="btn" id="pauseBtn" onclick="togglePause()">Pause Bot</button>
  <button class="btn" onclick="clearFeed()">Clear Log</button>
</div>

<!-- Stat cards -->
<div class="cards">
  <div class="card"><div class="card-label">CPU</div>
    <div class="card-val" id="cCpu" style="color:var(--cpu)">—</div></div>
  <div class="card"><div class="card-label">Memory</div>
    <div class="card-val" id="cMem" style="color:var(--mem)">—</div></div>
  <div class="card"><div class="card-label">Disk</div>
    <div class="card-val" id="cDisk" style="color:var(--blue)">—</div></div>
  <div class="card"><div class="card-label">Throttled Now</div>
    <div class="card-val" id="cThr" style="color:var(--orange)">0</div></div>
  <div class="card"><div class="card-label">Actions Taken</div>
    <div class="card-val" id="cAct" style="color:var(--green)">0</div></div>
  <div class="card"><div class="card-label">Issues Found</div>
    <div class="card-val" id="cIss" style="color:var(--red)">0</div></div>
  <div class="card"><div class="card-label">RAM Freed</div>
    <div class="card-val" id="cFreed" style="color:var(--blue)">0 MB</div></div>
</div>

<!-- Main grid -->
<div class="main">

  <!-- CPU chart -->
  <div class="chart-panel">
    <div class="panel-title">CPU Usage — 90 s</div>
    <div class="chart-wrap"><canvas id="cpuChart"></canvas></div>
  </div>

  <!-- Activity feed (spans 2 rows) -->
  <div class="feed" style="grid-row:span 2">
    <div class="feed-header">
      <span class="feed-title">Activity Log</span>
      <span class="event-count" id="evCount">0 events</span>
    </div>
    <div class="feed-body" id="feedBody"></div>
  </div>

  <!-- MEM chart -->
  <div class="chart-panel">
    <div class="panel-title">Memory Usage — 90 s</div>
    <div class="chart-wrap"><canvas id="memChart"></canvas></div>
  </div>

  <!-- Process table -->
  <div class="proc-panel">
    <div class="panel-title" style="margin-bottom:8px">Top Processes</div>
    <table>
      <thead>
        <tr>
          <th>Process</th><th>PID</th><th>CPU %</th>
          <th>CPU Bar</th><th>MEM %</th><th>Status</th>
        </tr>
      </thead>
      <tbody id="procBody"></tbody>
    </table>
  </div>

</div><!-- /main -->

<!-- Footer -->
<div class="footer">
  <span id="lastUpdate">Initializing…</span>
  <span>Monitor: 1 s &nbsp;·&nbsp; Throttle: &gt;85% CPU &nbsp;·&nbsp; Warn: &gt;80% RAM</span>
</div>

<script>
// ── Chart setup ──────────────────────────────────────────────────────────────
function makeChart(id, color, fill) {
  const ctx = document.getElementById(id).getContext('2d');
  return new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        data: [], borderColor: color, borderWidth: 2,
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
          ticks: { color: '#656d76', stepSize: 25, callback: v => v + '%' },
          grid: { color: '#21262d' },
          border: { display: false },
        }
      },
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
    }
  });
}

const cpuChart = makeChart('cpuChart', '#ff7b54', 'rgba(255,123,84,.15)');
const memChart = makeChart('memChart', '#7ee787', 'rgba(126,231,135,.15)');

function updateChart(chart, data) {
  chart.data.labels = data.map((_, i) => i);
  chart.data.datasets[0].data = data;
  chart.update('none');
}

// ── State ────────────────────────────────────────────────────────────────────
let evCount = 0;
let seenEvents = new Set();
let paused = false;

// ── Stat cards ───────────────────────────────────────────────────────────────
function colorFor(val, lo=60, hi=80, def='') {
  return val > hi ? 'var(--red)' : val > lo ? 'var(--yellow)' : def;
}

function setCard(id, text, color) {
  const el = document.getElementById(id);
  el.textContent = text;
  if (color) el.style.color = color;
}

// ── Process table ─────────────────────────────────────────────────────────────
function barHtml(pct, color) {
  return `<td class="bar-cell">
    <div class="bar"><div class="bar-fill" style="width:${Math.min(pct,100)}%;background:${color}"></div></div>
  </td>`;
}

function buildProcTable(procs, throttledPids) {
  const body = document.getElementById('procBody');
  body.innerHTML = procs.map(([cpu, mem, pid, name, status]) => {
    const thr = throttledPids.includes(pid);
    const hi  = !thr && cpu >= 70;
    const cls = thr ? 'thr' : hi ? 'hi' : '';
    const cpuColor = thr ? 'var(--orange)' : hi ? 'var(--yellow)' : 'var(--cpu)';
    return `<tr class="${cls}">
      <td>${name}</td>
      <td>${pid}</td>
      <td>${cpu.toFixed(1)}%</td>
      ${barHtml(cpu, cpuColor)}
      <td>${mem.toFixed(1)}%</td>
      <td>${status}</td>
    </tr>`;
  }).join('');
}

// ── Activity feed ─────────────────────────────────────────────────────────────
const BADGE = {fix:'✓ FIX  ', warn:'⚠ WARN ', issue:'✗ ISSUE', info:'ℹ INFO '};

function addEvent(ev) {
  const key = ev.ts + ev.msg;
  if (seenEvents.has(key)) return;
  seenEvents.add(key);
  evCount++;
  document.getElementById('evCount').textContent = evCount + ' events';
  const div = document.createElement('div');
  div.className = 'ev ' + ev.kind;
  div.innerHTML = `<span class="ev-ts">${ev.ts}</span>
    <span class="ev-badge">${BADGE[ev.kind]||'?'}</span>
    <span class="ev-msg">${ev.msg}</span>`;
  const body = document.getElementById('feedBody');
  body.prepend(div);
}

function clearFeed() {
  evCount = 0;
  seenEvents.clear();
  document.getElementById('evCount').textContent = '0 events';
  document.getElementById('feedBody').innerHTML = '';
}

// ── Pause/Resume ──────────────────────────────────────────────────────────────
function togglePause() {
  paused = !paused;
  const dot = document.getElementById('statusDot');
  const txt = document.getElementById('statusText');
  const btn = document.getElementById('pauseBtn');
  if (paused) {
    dot.style.background='var(--yellow)'; dot.style.boxShadow='0 0 6px var(--yellow)';
    txt.style.color='var(--yellow)'; txt.textContent='PAUSED';
    btn.textContent='Resume Bot';
  } else {
    dot.style.background='var(--green)'; dot.style.boxShadow='0 0 6px var(--green)';
    txt.style.color='var(--green)'; txt.textContent='RUNNING';
    btn.textContent='Pause Bot';
  }
  fetch('/pause?state=' + (paused ? '1' : '0'));
}

// ── Poll loop ─────────────────────────────────────────────────────────────────
async function poll() {
  try {
    const r = await fetch('/stats');
    if (!r.ok) return;
    const d = await r.json();

    if (!paused) {
      // Charts
      updateChart(cpuChart, d.cpu_hist);
      updateChart(memChart, d.mem_hist);

      // Cards
      const cpu = d.cpu_hist.at(-1) ?? 0;
      const mem = d.mem_hist.at(-1) ?? 0;
      setCard('cCpu',  cpu.toFixed(0)+'%',  colorFor(cpu, 60, 80, 'var(--cpu)'));
      setCard('cMem',  mem.toFixed(0)+'%',  colorFor(mem, 60, 80, 'var(--mem)'));
      setCard('cDisk', d.disk_pct.toFixed(0)+'%',
              d.disk_pct > 90 ? 'var(--red)' : 'var(--blue)');
      const n = Object.keys(d.throttled).length;
      setCard('cThr', String(n), n > 0 ? 'var(--orange)' : 'var(--muted)');
      setCard('cAct', String(d.actions));
      setCard('cIss', String(d.issues), d.issues > 0 ? 'var(--red)' : 'var(--muted)');
      const freed = d.freed_mb || 0;
      setCard('cFreed', freed >= 1024 ? (freed/1024).toFixed(1)+' GB' : freed.toFixed(0)+' MB',
              freed > 0 ? 'var(--blue)' : 'var(--muted)');

      // Table
      buildProcTable(d.top_procs, Object.keys(d.throttled).map(Number));

      // Footer
      let thr = '';
      if (n > 0) thr = '  ·  Throttled: ' + Object.entries(d.throttled)
          .map(([pid,name]) => `${name}(${pid})`).join(', ');
      document.getElementById('lastUpdate').textContent =
          'Last update: ' + new Date().toLocaleTimeString() + thr;
    }

    // Events always drain (even when paused)
    d.events.forEach(ev => addEvent(ev));

  } catch(e) { /* server restarting */ }
}

// Start polling
setInterval(poll, 1000);
poll();
</script>
</body>
</html>
"""

# ─── HTTP Handler ─────────────────────────────────────────────────────────────
_engine: BotEngine = None   # set in main


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
                snap["disk_pct"] = psutil.disk_usage("/").percent
            except Exception:
                snap["disk_pct"] = 0
            self._send(200, "application/json",
                       json.dumps(snap).encode())
        elif path == "/pause":
            if "state=1" in q:
                _engine.stop()
            else:
                pass   # resume handled client-side (data just keeps flowing)
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

    # Open browser after a short delay (let server bind first)
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down…")
        _engine.stop()
        server.shutdown()


if __name__ == "__main__":
    main()
