# MAC Performance Bot

A lightweight, always-on macOS performance monitor with **auto-remediation**, a **Multi-Dimensional Memory Intelligence Engine (MMIE)**, and an installable PWA dashboard.

## Features

- **Live PWA dashboard** — installable from the browser, ring gauges, memory arc, activity log
- **Auto-throttles CPU hogs** via `nice()` — no manual intervention needed
- **4-tier memory remediation cascade** — warn → purgeable advisory → SIGSTOP idle daemons → emergency termination
- **Memory Intelligence (MMIE)**
  - macOS kernel pressure level (`kern.memorystatus_vm_pressure_level` sysctl)
  - `vm_stat` breakdown — wired / active / inactive / purgeable / compressed / free
  - Memory genealogy — attributes RAM to root application families by walking the `ppid` tree
  - Linear-regression forecast — predicts minutes until 95 % RAM exhaustion
  - Auto-freeze/thaw of safe background daemons under Tier 3 pressure
- **Detects** RAM pressure, swap usage, low disk, thermal throttling, zombie processes, memory leaks
- **Autostart** via macOS LaunchAgent (login item)
- **Zero heavy dependencies** — only `psutil` + Python stdlib

## Quick Start

```bash
git clone https://github.com/itsmeSugunakar/MAC_Perf_BOT.git
cd MAC_Perf_BOT
bash scripts/install_gui.sh
open http://127.0.0.1:8765
```

To install as a standalone app: open `http://127.0.0.1:8765` in Chrome/Safari → **Add to Dock / Install app**.

## Project Structure

```
MAC_Perf_BOT/
├── CLAUDE.md               # CMDB — architecture, thresholds, API reference
├── app/
│   ├── performance_gui.py  # Web dashboard + MMIE bot engine  ← main entry point
│   └── performance_bot.py  # Headless CLI bot
├── config/                 # LaunchAgent plists
├── scripts/                # install / uninstall helpers
└── docs/                   # Architecture deep-dive
```

## Requirements

- macOS 13 Ventura or later
- Python 3.11+ (Homebrew: `/opt/homebrew/bin/python3.11`)
- `psutil` (auto-installed by the install script)

## Manual Usage

```bash
# Run the dashboard (opens browser automatically)
/opt/homebrew/bin/python3.11 app/performance_gui.py

# Stop the autostart agent
launchctl unload ~/Library/LaunchAgents/com.user.performancebot-gui.plist

# Restart to pick up code changes
launchctl stop com.user.performancebot-gui
launchctl start com.user.performancebot-gui

# Remove everything
bash scripts/uninstall.sh
```

## How It Works

Every second the bot engine:
1. Samples CPU, RAM, Disk, Swap via `psutil`
2. Identifies processes exceeding **85 % CPU** per core and renices them to `nice=10`
3. Restores `nice(0)` automatically when CPU drops back below 35 %
4. Every 3 s — checks RAM and triggers the MMIE cascade if pressure is elevated
5. Every 5 s — queries macOS kernel pressure level, parses `vm_stat`, updates memory forecast
6. Every 30–120 s — rebuilds memory genealogy tree, sweeps idle XPC/widget services
7. Pushes events (FIX / WARN / ISSUE / INFO) to the live dashboard

### MMIE Remediation Tiers

| Tier | Trigger | Action |
|------|---------|--------|
| 1 | ≥ 80 % RAM | Log issue + identify top RSS consumers |
| 2 | ≥ 82 % RAM | Report purgeable memory + wired pressure + memory genealogy |
| 3 | ≥ 87 % RAM | SIGSTOP safe background daemons; SIGCONT auto-restores on pressure drop |
| 4 | ≥ 92 % RAM | Emergency termination of idle XPC / widget services |

## Dashboard

The dashboard is a **Progressive Web App** served at `http://127.0.0.1:8765`.

| Panel | Contents |
|-------|----------|
| Metric strip | SVG ring gauges for CPU / Memory / Swap / Disk + Actions / Issues |
| Memory Intelligence | Arc gauge, % + GB, memory forecast ETA, composition bar (wired/active/inactive/compressed/free), vm_stat details, memory families list |
| CPU / Swap charts | 90-second sparklines with warn threshold line |
| Bot Status | Throttled count, total actions, issues, RAM freed |
| Activity Log | Live event feed — FIX / WARN / ISSUE / INFO |
| Process Table | Top 12 processes with CPU/MEM bars; throttled badge; toggleable memory trend chart |

Activity log colours: 🟢 FIX &nbsp; 🟡 WARN &nbsp; 🔴 ISSUE &nbsp; 🔵 INFO

## License

MIT
