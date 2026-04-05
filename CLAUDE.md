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
| **Version**        | 1.0.0                                               |
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
3. **Remediates** by renicing over-consuming processes — no manual intervention
4. **Surfaces** everything through a live browser-based dashboard
5. **Auto-starts** at login via a macOS LaunchAgent

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
│   └── architecture.md     ← Component diagram and data-flow notes
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

### Component Responsibilities

| Component               | File                     | Role                                              |
|-------------------------|--------------------------|---------------------------------------------------|
| `BotEngine`             | `app/performance_gui.py` | Background thread; collects metrics, remediates   |
| `Handler` (HTTP)        | `app/performance_gui.py` | Serves HTML dashboard + JSON API                  |
| `performance_bot.py`    | `app/performance_bot.py` | Headless variant (LaunchAgent, no browser needed) |
| LaunchAgent (GUI)       | `config/*.plist`         | macOS service manager — starts bot at login       |
| Dashboard HTML+JS       | Embedded in `gui.py`     | Live UI; polls `/stats` every 1 s                 |

---

## 5. Runtime Thresholds (defaults)

| Parameter        | Default | Description                                      |
|------------------|---------|--------------------------------------------------|
| `CPU_WARN`       | 70 %    | Log a warning when a process hits this           |
| `CPU_THROTTLE`   | 85 %    | Renice the process to `nice=10`                  |
| `MEM_WARN`       | 80 %    | Emit a RAM pressure issue event                  |
| `DISK_WARN`      | 90 %    | Emit a low-disk issue event                      |
| `SWAP_WARN`      | 50 %    | Warn once when swap exceeds this                 |
| `RENICE_VALUE`   | 10      | Nice increment applied to throttled processes    |
| `HISTORY_LEN`    | 90      | Seconds of CPU/RAM history shown in charts       |
| `CHECK_INTERVAL` | 1 s     | Polling cadence of `BotEngine`                   |
| `HTTP_PORT`      | 8765    | Localhost port for the web dashboard             |

To change a threshold, edit the constants at the top of `app/performance_gui.py`
and reload the LaunchAgent (`scripts/install_gui.sh`).

---

## 6. Dependencies

### Runtime
| Package  | Version  | Source   | Purpose                      |
|----------|----------|----------|------------------------------|
| `psutil` | ≥ 5.9    | PyPI     | Cross-platform process/system metrics |

All other imports are Python standard library (`http.server`, `threading`,
`queue`, `json`, `webbrowser`).

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

| Endpoint       | Method | Returns                   | Description                    |
|----------------|--------|---------------------------|--------------------------------|
| `/`            | GET    | `text/html`               | Full dashboard page            |
| `/stats`       | GET    | `application/json`        | Snapshot: metrics + events     |
| `/pause?state=1` | GET  | `{"ok":true}`             | Pause the bot engine           |
| `/pause?state=0` | GET  | `{"ok":true}`             | Resume the bot engine          |

### `/stats` JSON schema
```json
{
  "cpu_hist":  [float],          // last 90 CPU % readings
  "mem_hist":  [float],          // last 90 RAM % readings
  "top_procs": [[cpu, mem, pid, name, status]],
  "throttled": {"pid": "name"},  // currently reniced processes
  "events":    [{"kind","msg","ts"}],  // last 60 events
  "actions":   int,              // total auto-remediations performed
  "issues":    int,              // total issues detected
  "disk_pct":  float             // current boot-volume usage %
}
```

---

## 10. Logging

| Log file                    | Content                             |
|-----------------------------|-------------------------------------|
| `~/Library/Logs/performance-bot/gui_stdout.log`  | Server startup, port binding |
| `~/Library/Logs/performance-bot/gui_stderr.log`  | Python tracebacks (if any)   |
| `~/Library/Logs/performance-bot/stdout.log`      | Headless bot output          |

Logs are **not** rotated automatically. Truncate manually or add `newsyslog`
config if the bot runs for months.

---

## 11. Security Considerations

- Listens on **loopback only** (`127.0.0.1`) — not accessible from the network.
- Uses `nice()` only (no `kill`, no `SIGSTOP`). Cannot crash processes.
- `PROTECTED` set prevents touching system processes and the bot itself.
- No credentials, tokens, or secrets in code or config.
- Renicing unprivileged processes does not require `sudo`.

---

## 12. Known Limitations

| Limitation | Notes |
|------------|-------|
| System Python 3.9 (Xcode) | Crashes on macOS 15+ due to bundled Tcl/Tk 8.5. Use Homebrew Python 3.11. |
| No authentication on dashboard | Acceptable — loopback-only. Do not expose port 8765 externally. |
| Chart.js loaded from CDN | Requires internet on first load. Embed locally for air-gapped envs. |
| Swap-warn fires once per session | Intentional — avoids log spam. |

---

## 13. Branch Strategy

| Branch  | Purpose                                   |
|---------|-------------------------------------------|
| `main`  | Stable, production-ready                  |
| `dev`   | Active development, integration testing   |
| `feat/*`| Feature branches — merge into `dev`       |
| `fix/*` | Bug-fix branches — merge into `dev`       |

---

## 14. Change Log

| Date       | Version | Author         | Change                                      |
|------------|---------|----------------|---------------------------------------------|
| 2026-04-04 | 1.0.0   | itsmeSugunakar | Initial release: headless bot + web GUI     |

---

*This file is the single source of truth for the MAC Performance Bot application.
Update it whenever architecture, thresholds, or deployment procedures change.*
