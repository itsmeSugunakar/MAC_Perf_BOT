# MAC Performance Bot

A lightweight, always-on macOS performance monitor with **auto-remediation** and a live browser dashboard.

## Features

- **Live dashboard** — CPU & RAM sparklines, stat cards, process table, activity log
- **Auto-throttles** CPU hogs via `nice()` — no manual intervention needed
- **Restores priority** automatically when a process calms down
- **Detects** RAM pressure, swap usage, and low disk space
- **Autostart** via macOS LaunchAgent (login item)
- **Zero heavy dependencies** — only `psutil` + Python stdlib

## Quick Start

```bash
git clone https://github.com/itsmeSugunakar/MAC_Perf_BOT.git
cd MAC_Perf_BOT
bash scripts/install_gui.sh
open http://127.0.0.1:8765
```

## Project Structure

```
MAC_Perf_BOT/
├── CLAUDE.md               # CMDB — architecture, thresholds, API reference
├── app/
│   ├── performance_gui.py  # Web dashboard + bot engine  ← main entry point
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

# Remove everything
bash scripts/uninstall.sh
```

## How It Works

Every second the bot engine:
1. Samples CPU, RAM, Disk via `psutil`
2. Identifies processes exceeding **85 % CPU** per core
3. Calls `nice(10)` on offenders — lowers their scheduling priority
4. Restores `nice(0)` when their CPU drops back below 35 %
5. Pushes events (FIX / WARN / ISSUE / INFO) to the dashboard

See [`CLAUDE.md`](CLAUDE.md) for full CMDB documentation.

## Dashboard

| Card | Meaning |
|------|---------|
| CPU | System-wide CPU % (colour-coded) |
| Memory | RAM utilisation |
| Disk | Boot volume usage |
| Throttled Now | Processes currently reniced |
| Actions Taken | Total auto-remediations since start |
| Issues Found | Total warnings/issues detected |

Activity log colours: 🟢 FIX &nbsp; 🟡 WARN &nbsp; 🔴 ISSUE &nbsp; 🔵 INFO

## License

MIT
