# CLAUDE.md — Configuration Management Database (CMDB)
## MAC Performance Bot

> Canonical reference for architecture, conventions, deployment, and operational
> procedures for the **MAC Performance Bot** application.
> Keep this file current whenever code, config, or infrastructure changes.

---

## 1. Application Identity

| Field              | Value                                               |
|--------------------|-----------------------------------------------------|
| **App Name**       | MAC Performance Bot                                 |
| **Short Name**     | mac-perf-bot                                        |
| **Version**        | 1.4.0                                               |
| **Owner**          | itsmeSugunakar                                      |
| **Contact**        | sugun.sr@gmail.com                                  |
| **Repository**     | https://github.com/itsmeSugunakar/MAC_Perf_BOT      |
| **Default Branch** | main                                                |
| **Dev Branch**     | dev                                                 |
| **License**        | MIT                                                 |
| **Platform**       | macOS 13 Ventura + (Apple Silicon & Intel)          |
| **Language**       | Python 3.11+                                        |

---

## 2. Purpose

A lightweight, always-on macOS daemon that:

1. **Monitors** CPU, RAM, Disk, and Swap every second
2. **Detects** resource hogs automatically (thresholds configurable)
3. **Predicts** memory exhaustion via OLS linear-regression Time-to-Exhaustion (TTE) forecast
4. **Remediates** through a 4-tier adaptive cascade — renice → freeze → terminate — driven by the Predictive Remediation Engine (PRE)
5. **Surfaces** everything through a live PWA browser dashboard
6. **Auto-starts** at login via a macOS LaunchAgent
7. **Analyses** memory at kernel depth via the Multi-Dimensional Memory Intelligence Engine (MMIE)
8. **Accumulates** 90 days of metric history on disk (SQLite) for application-level performance predictions
9. **Runs lean** — single `psutil.process_iter()` scan per second, all syscalls cached, `O(1)` event deque

---

## 3. Repository Layout

```
MAC_Perf_BOT/
├── CLAUDE.md               ← This file (CMDB)
├── README.md               ← User-facing docs
├── .gitignore
│
├── app/
│   ├── performance_gui.py  ← Web dashboard + HTTP server (MAIN ENTRY POINT)
│   └── performance_bot.py  ← Headless CLI bot (standalone, no GUI)
│
├── config/
│   ├── com.user.performancebot-gui.plist   ← LaunchAgent: GUI/web server
│   └── com.user.performancebot.plist       ← LaunchAgent: headless bot
│
├── scripts/
│   ├── install_gui.sh      ← Install + start the GUI app
│   ├── install.sh          ← Install + start the headless bot
│   └── uninstall.sh        ← Remove all LaunchAgents + stop processes
│
├── docs/
│   ├── architecture.md     ← Component diagram, data-flow, cache design
│   └── provisional-patent-application.md  ← USPTO PPA technical spec
│
└── logs/                   ← Runtime logs (git-ignored)
    └── .gitkeep
```

---

## 4. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     macOS User Session                      │
│                                                             │
│  ┌──────────────────┐        ┌───────────────────────────┐ │
│  │   LaunchAgent    │ starts │   performance_gui.py      │ │
│  │ (login autostart)│───────▶│                           │ │
│  └──────────────────┘        │  ┌─────────────────────┐  │ │
│                              │  │   BotEngine Thread  │  │ │
│                              │  │  • psutil metrics   │  │ │
│                              │  │  • CPU/RAM/Disk/Swap │  │ │
│                              │  │  • Auto-renice hogs  │  │ │
│                              │  └────────┬────────────┘  │ │
│                              │           │ snapshots      │ │
│                              │  ┌────────▼────────────┐  │ │
│                              │  │  HTTP Server :8765  │  │ │
│                              │  │  GET /       → HTML  │  │ │
│                              │  │  GET /stats  → JSON  │  │ │
│                              │  │  GET /pause  → ctrl  │  │ │
│                              │  └────────┬────────────┘  │ │
│                              └───────────┼───────────────┘ │
│                                          │                  │
│  ┌───────────────────────────────────────▼───────────────┐ │
│  │            Browser  http://127.0.0.1:8765             │ │
│  │  • Chart.js live CPU / RAM sparklines                 │ │
│  │  • Stat cards (CPU / MEM / DISK / THROTTLED / …)     │ │
│  │  • Activity log (FIX / WARN / ISSUE / INFO)           │ │
│  │  • Top-process table with CPU bars                   │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Engine Tick Schedule

| Interval | Method | What it does |
|----------|--------|--------------|
| 1 s | `_collect()` | Single `process_iter()` scan — metrics + CPU throttle detect + `_restore_calmed_procs()` |
| 3 s | `_check_memory()` | PRE effective tier + MMIE cascade (uses cached `_last_vm`) |
| 5 s | `_update_pressure_and_forecast()` | sysctl oracle + `vm_stat` + OLS forecast + ancestry |
| 10 s | `_check_disk()` | Disk usage — stores `disk_pct` / `disk_free_gb` for snapshot |
| 30 s | `_check_power_mode()` | Battery vs AC detection |
| 30 s | `_detect_xpc_respawn()` | XPC Respawn Guard scan |
| 60 s | `_check_thermal()` | `pmset` thermal throttle check |
| 60 s | `_check_zombies()` | Zombie process detection |
| 60 s | `_track_memory_leaks()` | Per-process RSS growth rate |
| 60 s | `cache.flush()` + `cache.prune()` | Batch SQLite write + daily prune gate |
| 300 s | `_check_caches()` | `~/Library/Caches` size warning |
| 3600 s | `_analyse_app_predictions()` | 90-day cache risk analysis (daily gate inside) |
| 30 s (IDLE_SWEEP_S) | `_sweep_idle_services()` | Tier 4 idle XPC/widget termination |

### Component Responsibilities

| Component                        | File                     | Role                                                                        |
|----------------------------------|--------------------------|-----------------------------------------------------------------------------|
| `BotEngine`                      | `app/performance_gui.py` | Background thread; collects metrics, remediates                             |
| **MMIE methods**                 | `app/performance_gui.py` | Kernel oracle, vm_stat, genealogy, OLS forecast, freeze/thaw                |
| **Predictive Remediation Engine**| `app/performance_gui.py` | `_compute_effective_tier()` — TTE-driven tier escalation above static %     |
| **CPU-RAM Conflict Gate**        | `app/performance_gui.py` | `_check_cpu()` — defers `nice(0)` for top-RAM families under Tier 3+ lock  |
| **Genealogy Freeze Scoring**     | `app/performance_gui.py` | `_freeze_background_daemons()` — `family×2 + pattern×1` weighted scoring   |
| **XPC Respawn Guard**            | `app/performance_gui.py` | `_detect_xpc_respawn()` — blocklists respawning launchd services            |
| **MetricsCache**                 | `app/performance_gui.py` | SQLite 90-day disk store; batch writes every 60 s; aggregate-only reads     |
| `_restore_calmed_procs()`        | `app/performance_gui.py` | CPU priority restore loop — only touches `self.throttled` (0–3 items)      |
| **App Predictions**              | `app/performance_gui.py` | `_analyse_app_predictions()` — 24 h risk analysis from cache                |
| `Handler` (HTTP)                 | `app/performance_gui.py` | Serves PWA dashboard + JSON API + manifest + SVG icon                       |
| `performance_bot.py`             | `app/performance_bot.py` | Headless variant (LaunchAgent, no browser needed)                           |
| LaunchAgent (GUI)                | `config/*.plist`         | macOS service manager — starts bot at login                                 |
| Dashboard HTML+JS                | Embedded in `gui.py`     | PWA; polls `/stats` every 1 s; installable via browser                      |

---

## 5. Runtime Thresholds (defaults)

### Core thresholds
| Parameter        | Default | Description                                      |
|------------------|---------|--------------------------------------------------|
| `CPU_WARN`       | 70 %    | Log a warning when a process hits this           |
| `CPU_THROTTLE`   | 85 %    | Renice the process to `nice=10`                  |
| `MEM_WARN`       | 80 %    | Emit a RAM pressure issue event (Tier 1)         |
| `DISK_WARN`      | 90 %    | Emit a low-disk issue event                      |
| `SWAP_WARN`      | 50 %    | Warn once when swap exceeds this                 |
| `RENICE_VALUE`   | 10      | Nice increment applied to throttled processes    |
| `HISTORY_LEN`    | 90      | Seconds of CPU/RAM history shown in charts       |
| `CHECK_INTERVAL` | 1 s     | Polling cadence of `BotEngine`                   |
| `HTTP_PORT`      | 8765    | Localhost port for the web dashboard             |

### MMIE thresholds
| Parameter             | Default  | Description                                              |
|-----------------------|----------|----------------------------------------------------------|
| `MEM_TIER2_PCT`       | 82 %     | Trigger purgeable scan + memory genealogy report         |
| `MEM_TIER3_PCT`       | 87 %     | SIGSTOP safe background daemons (auto-thaws on drop)     |
| `MEM_TIER4_PCT`       | 92 %     | Emergency idle-XPC service termination                   |
| `WIRED_WARN_PCT`      | 40 %     | Warn when wired memory exceeds this % of total RAM       |
| `LEAK_RATE_MB_MIN`    | 50 MB/m  | Flag a process as a potential memory leak                |
| `LEAK_MIN_RSS_MB`     | 200 MB   | Minimum RSS before leak flagging applies                 |
| `CACHE_WARN_GB`       | 5 GB     | Warn when `~/Library/Caches` exceeds this size           |
| `FREEZE_COOL_S`       | 120 s    | Minimum seconds between daemon freeze cycles             |
| `MEM_ANCESTRY_COOL_S` | 120 s    | Minimum seconds between genealogy reports                |

### Predictive Remediation Engine thresholds
| Parameter          | Default | Description                                              |
|--------------------|---------|----------------------------------------------------------|
| `TTE_TIER2_MIN`    | 10 min  | TTE at or below this → escalate to Tier 2 early         |
| `TTE_TIER3_MIN`    | 5 min   | TTE at or below this → escalate to Tier 3 early         |
| `TTE_TIER4_MIN`    | 2 min   | TTE at or below this → escalate to Tier 4 early         |
| `TTE_MIN_SAMPLES`  | 20      | Minimum `mem_hist` samples before TTE can drive escalation |
| `XPC_RESPAWN_S`    | 10 s    | Services reappearing within this window are blocklisted  |

### Disk cache constants
| Parameter               | Default | Description                                          |
|-------------------------|---------|------------------------------------------------------|
| `CACHE_RETENTION_DAYS`  | 90      | Rows older than this are pruned from SQLite          |
| `CACHE_WRITE_S`         | 60 s    | Flush interval — `executemany()` batch write cadence |
| `CACHE_PRUNE_S`         | 86400 s | Minimum interval between prune operations            |

To change a threshold, edit the constants at the top of `app/performance_gui.py`
and reload the LaunchAgent (`scripts/install_gui.sh`).

---

## 6. Dependencies

### Runtime
| Package  | Version  | Source   | Purpose                      |
|----------|----------|----------|------------------------------|
| `psutil` | ≥ 5.9    | PyPI     | Cross-platform process/system metrics |

All other imports are Python standard library (`http.server`, `threading`,
`sqlite3`, `json`, `subprocess`, `webbrowser`, `pathlib`).

### Front-end (CDN, no install)
| Library    | Version | URL                                          |
|------------|---------|----------------------------------------------|
| `Chart.js` | 4.x     | `cdn.jsdelivr.net/npm/chart.js@4/dist/...`   |

### Toolchain
| Tool        | Min Version | Notes                           |
|-------------|-------------|---------------------------------|
| Python      | 3.11        | Homebrew (`/opt/homebrew/bin/python3.11`) |
| pip         | any         | Used only to bootstrap `psutil` |
| macOS       | 13 Ventura  | `launchctl` + `ProcessType=Interactive` |
| Browser     | Modern      | Chrome / Safari / Firefox — for dashboard |

---

## 7. Installation & Deployment

### Quick install (GUI + autostart)
```bash
cd ~/performance-bot
bash scripts/install_gui.sh
open http://127.0.0.1:8765
```

### Headless install (background only)
```bash
bash scripts/install.sh
```

### Uninstall everything
```bash
bash scripts/uninstall.sh
```

### Manual start (dev/test)
```bash
/opt/homebrew/bin/python3.11 app/performance_gui.py
```

---

## 8. LaunchAgent Configuration

| Key              | GUI plist value                              |
|------------------|----------------------------------------------|
| `Label`          | `com.user.performancebot-gui`                |
| `ProgramArguments` | `[python3.11, app/performance_gui.py]`     |
| `RunAtLoad`      | `true` — starts at login                     |
| `KeepAlive`      | `false` — user can close the window          |
| `ProcessType`    | `Interactive` — required for GUI/Aqua session|
| `Nice`           | `5` — bot runs at lower priority             |
| `LowPriorityIO`  | `true` — minimal I/O contention              |

Plist location (installed): `~/Library/LaunchAgents/com.user.performancebot-gui.plist`

---

## 9. API Reference

Dashboard server listens on `http://127.0.0.1:8765`.

| Endpoint         | Method | Returns                        | Description                    |
|------------------|--------|--------------------------------|--------------------------------|
| `/`              | GET    | `text/html`                    | Full PWA dashboard page        |
| `/stats`         | GET    | `application/json`             | Full snapshot: metrics + MMIE  |
| `/manifest.json` | GET    | `application/manifest+json`    | PWA web app manifest           |
| `/icon.svg`      | GET    | `image/svg+xml`                | PWA app icon                   |
| `/pause?state=1` | GET    | `{"ok":true}`                  | Pause the bot engine           |
| `/pause?state=0` | GET    | `{"ok":true}`                  | Resume the bot engine          |

### `/stats` JSON schema
```json
{
  "cpu_hist":             [float],   // last 90 CPU % readings
  "mem_hist":             [float],   // last 90 RAM % readings
  "swap_hist":            [float],   // last 90 Swap % readings
  "top_procs":            [[cpu, mem, pid, name, status]],
  "throttled":            {"pid": "name"},
  "events":               [{"kind", "msg", "ts"}],
  "actions":              int,
  "issues":               int,
  "freed_mb":             float,     // MB reclaimed by idle sweeps + freezes
  "disk_pct":             float,
  "disk_free_gb":         float,
  "mem_total_gb":         float,
  "swap_total_gb":        float,
  "thermal_pct":          int,       // CPU speed limit % (100 = normal)
  "on_battery":           bool,
  "uptime_s":             int,
  "mem_pressure_level":   "normal"|"warn"|"critical",  // macOS kernel sysctl
  "vm_breakdown":         {          // parsed from vm_stat
    "wired": float, "active": float, "inactive": float,
    "free": float, "purgeable": float, "compressed": float
  },
  "mem_forecast_min":     float,     // minutes to 95% exhaustion; -1 = stable
  "mem_ancestry":         [{"app": str, "mb": int, "pct": float}],
  "effective_tier":       int,       // 0–4; PRE output (may exceed static threshold)
  "predictive_escalation": bool,     // true when TTE drove tier above static %
  "cpu_ram_lock":         bool,      // true when Tier 3+ RAM lock blocks nice(0)
  "xpc_blocked":          int,       // count of names in _no_kill blocklist
  "cache_db_mb":          float,     // current size of metrics.db in MB
  "cache_rows":           int,       // approximate row count in metrics table
  "app_predictions":      [          // populated after first 24-h analysis cycle
    {
      "app":         str,
      "mb":          int,
      "pct":         float,
      "trend":       "rising"|"stable"|"falling",
      "risk":        "high"|"medium"|"low",
      "week1_avg":   float,          // avg system mem_pct, last 7 days
      "week2_avg":   float,          // avg system mem_pct, 7–14 days ago
      "chronic_pct": float           // % of last 7 days RAM above MEM_WARN
    }
  ]
}
```

---

## 10. Performance Characteristics

The bot is designed to be self-effacing — it must not measurably degrade the system it monitors.

### Hot-path optimisations (v1.4.0)

| Optimisation | Before | After |
|---|---|---|
| `psutil.process_iter()` calls/s | 2 (`_collect` + `_check_cpu`) | 1 (merged into `_collect`) |
| CPU throttle detection | Second full process scan | Inline in the same `_collect` scan using `p.info[]` cache |
| `psutil.cpu_count()` | Called inside per-process loop every tick | Cached as `self._ncpu` at init |
| `psutil.virtual_memory()` | Every tick + every 3 s in `_check_memory` | Once per tick; shared as `self._last_vm` |
| `psutil.swap_memory()` | Every tick + every 3 s | Once per tick; shared as `self._last_swap` |
| `psutil.disk_usage("/")` | Every tick in `_collect` + every `/stats` HTTP request | Every 10 s in `_check_disk` only; cached in `self.disk_pct` |
| Event ring-buffer | `list` with `pop(0)` — O(n) on every emit | `collections.deque(maxlen=200)` — O(1) append + auto-discard |
| Cache record rate | 1 row/s → 86 400 rows/day | 1 row/10 s → 8 640 rows/day (−90 % disk I/O) |
| `_detect_xpc_respawn()` frequency | Every 10 s | Every 30 s |

### Subprocess budget
Subprocesses are the most expensive operations. Frequency:

| Subprocess | Command | Frequency |
|---|---|---|
| Kernel pressure | `sysctl -n kern.memorystatus_vm_pressure_level` | Every 5 s |
| VM anatomy | `vm_stat` | Every 5 s |
| Thermal | `pmset -g therm` | Every 60 s |
| Power source | `pmset -g ps` | Every 30 s |

All other operations use `psutil` (pure Python + cached libc calls) or read from `self._last_*` cached values.

---

## 11. Logging & Persistent Storage

### Runtime logs
| Log file                                          | Content                      |
|---------------------------------------------------|------------------------------|
| `~/Library/Logs/performance-bot/gui_stdout.log`  | Server startup, port binding |
| `~/Library/Logs/performance-bot/gui_stderr.log`  | Python tracebacks (if any)   |
| `~/Library/Logs/performance-bot/stdout.log`      | Headless bot output          |

Logs are **not** rotated automatically. Truncate manually or add `newsyslog`
config if the bot runs for months.

### Disk cache
| Path                                                                    | Content                           |
|-------------------------------------------------------------------------|-----------------------------------|
| `~/Library/Application Support/performance-bot/metrics.db`             | 90-day SQLite metric history      |

The cache records 1 row every 10 seconds → ~8 640 rows/day → ~35–45 MB at 90 days.
Rows older than `CACHE_RETENTION_DAYS` (90) are deleted automatically once per day.
To manually clear: `rm ~/Library/Application\ Support/performance-bot/metrics.db`
(the bot recreates the schema on next start).

---

## 12. Security Considerations

- Listens on **loopback only** (`127.0.0.1`) — not accessible from the network.
- Uses `nice()` and `SIGSTOP`/`SIGCONT` only — cannot crash or delete processes.
- `PROTECTED` and `NEVER_TERMINATE` sets prevent touching system processes and the bot itself.
- `FREEZE_PATTERNS` list restricts SIGSTOP to known-safe background daemons only.
- `_no_kill` blocklist (XPC Respawn Guard) prevents repeated SIGTERM to launchd-managed services.
- No credentials, tokens, or secrets in code or config.
- Renicing and signalling unprivileged processes does not require `sudo`.
- Disk cache (`metrics.db`) contains only numeric metric values — no process names, file paths, or user-identifiable data are stored.

---

## 13. Known Limitations

| Limitation | Notes |
|------------|-------|
| System Python 3.9 (Xcode) | Crashes on macOS 15+ due to bundled Tcl/Tk 8.5. Use Homebrew Python 3.11. |
| No authentication on dashboard | Acceptable — loopback-only. Do not expose port 8765 externally. |
| Chart.js loaded from CDN | Requires internet on first load. Embed locally for air-gapped envs. |
| Swap-warn fires once per session | Intentional — avoids log spam. |
| MMIE genealogy scan cost | `_build_memory_ancestry()` iterates all processes; runs every 120 s max. |
| SIGSTOP requires user ownership | MMIE Tier 3 freeze only works on processes owned by the current user. |
| `memory_pressure` sysctl | `kern.memorystatus_vm_pressure_level` may require SIP adjustments on some configurations. Falls back to percent-derived level automatically. |
| App Predictions cold start | The `_analyse_app_predictions()` panel is empty for the first 24 h. After the first full day the cache has enough data to show risk ratings. |
| Cache disk size | At 1 row/10 s for 90 days the database reaches ~35–45 MB — acceptable on all Macs. Reduce `CACHE_RETENTION_DAYS` only if storage is extremely limited. |
| PRE TTE requires 20 samples | The Predictive Remediation Engine requires `TTE_MIN_SAMPLES` (20) seconds of `mem_hist` before TTE-driven escalation activates. |

---

## 14. Branch Strategy

| Branch  | Purpose                                   |
|---------|-------------------------------------------|
| `main`  | Stable, production-ready                  |
| `dev`   | Active development, integration testing   |
| `feat/*`| Feature branches — merge into `dev`       |
| `fix/*` | Bug-fix branches — merge into `dev`       |

---

## 15. Change Log

| Date       | Version | Author         | Change                                                                 |
|------------|---------|----------------|------------------------------------------------------------------------|
| 2026-04-04 | 1.0.0   | itsmeSugunakar | Initial release: headless bot + web GUI                                |
| 2026-04-05 | 1.1.0   | itsmeSugunakar | MMIE engine: kernel pressure oracle, vm_stat breakdown, memory genealogy, linear-regression forecast, 4-tier remediation cascade, SIGSTOP/SIGCONT freeze-thaw; PWA dashboard redesign with ring gauges, Memory Intelligence panel, metric strip, `/manifest.json` |
| 2026-04-05 | 1.2.0   | itsmeSugunakar | Predictive Remediation Engine (`_compute_effective_tier`); CPU-RAM Conflict Resolution Gate; genealogy-guided SIGSTOP scoring (`family×2 + pattern×1`); XPC Respawn Guard (`_detect_xpc_respawn`, `_no_kill`); dashboard: Active Tier, CPU-RAM Lock, XPC Blocked, predictive escalation banner; PPA document added |
| 2026-04-05 | 1.3.0   | itsmeSugunakar | 90-day SQLite disk cache (`MetricsCache`): batch writes every 60 s, daily prune, aggregate-only reads; `_analyse_app_predictions()` for app-level risk classification; `app_mem_trend()` and `chronic_pressure_pct()` queries; dashboard App Predictions panel + Cache (90d) vmrow; `/stats` extended with `effective_tier`, `predictive_escalation`, `cpu_ram_lock`, `xpc_blocked`, `cache_db_mb`, `cache_rows`, `app_predictions` |
| 2026-04-05 | 1.4.0   | itsmeSugunakar | Lightweight engine: merged `_check_cpu` throttle-detection into `_collect` (single `process_iter` per second); `_check_cpu` → `_restore_calmed_procs` (no process scan); `psutil.cpu_count` cached as `self._ncpu`; `virtual_memory`/`swap_memory` fetched once per tick, shared via `_last_vm`/`_last_swap`; `disk_usage` moved to `_check_disk` (10 s), cached in `disk_pct`/`disk_free_gb`; handler no longer calls `disk_usage` per request; `events` list → `deque(maxlen=200)` (O(1)); cache record rate 1/s → 1/10 s; `_detect_xpc_respawn` 10 s → 30 s |

---

*This file is the single source of truth for the MAC Performance Bot application.
Update it whenever architecture, thresholds, or deployment procedures change.*
