# MAC Performance Bot

A lightweight, always-on macOS performance monitor with **auto-remediation**, a **Multi-Dimensional Memory Intelligence Engine (MMIE)**, a **Predictive Remediation Engine**, and an installable PWA dashboard.

## Features

- **Live PWA dashboard** — installable from browser, ring gauges, memory arc, activity log
- **Auto-throttles CPU hogs** via `nice()` — no manual intervention needed
- **CPU-RAM Conflict Resolution** — blocks CPU priority restoration when the process is a top RAM owner during active memory pressure
- **Predictive Remediation Engine** — OLS linear-regression TTE forecast escalates the remediation tier *before* static RAM % thresholds are breached
- **4-tier memory remediation cascade** — observe → advisory → SIGSTOP idle daemons → emergency termination
- **Genealogy-guided freeze scoring** — daemons are ranked by `(family_match × 2 + pattern_match × 1)` so the family causing the most RAM pressure is frozen first
- **XPC Respawn Guard** — detects launchd-managed services that respawn within 10 s and blocklists them to avoid futile kill loops
- **90-day disk cache** — SQLite store of metric history (`~/Library/Application Support/performance-bot/metrics.db`); flushed every 60 s; pruned daily; used for app-level performance predictions with near-zero CPU/RAM overhead
- **Memory Intelligence (MMIE)**
  - macOS kernel pressure level (`kern.memorystatus_vm_pressure_level` sysctl)
  - `vm_stat` breakdown — wired / active / inactive / purgeable / compressed / free
  - Memory genealogy — attributes RAM to root application families via `ppid` tree walk
  - OLS linear-regression forecast — predicts minutes until 95 % RAM exhaustion
  - Auto-freeze/thaw of safe background daemons under Tier 3 pressure
- **App Predictions** — 90-day cache powers week-over-week trend analysis; classifies top-RSS apps as high / medium / low risk; emits `APP PREDICTION` and `CHRONIC PRESSURE` events
- **Detects** RAM pressure, swap usage, low disk, thermal throttling, zombie processes, memory leaks
- **Autostart** via macOS LaunchAgent (login item)
- **Zero heavy dependencies** — only `psutil` + Python stdlib (`sqlite3`, `collections.deque` included)
- **Lightweight by design** — single `psutil.process_iter()` call per second; all syscall results cached; `O(1)` event ring-buffer; disk I/O batched every 60 s

---

## Quick Start

```bash
git clone https://github.com/itsmeSugunakar/MAC_Perf_BOT.git
cd MAC_Perf_BOT
bash scripts/install_gui.sh
open http://127.0.0.1:8765
```

To install as a standalone app: open `http://127.0.0.1:8765` in Chrome or Safari → **Add to Dock / Install app**.

---

## Project Structure

```
MAC_Perf_BOT/
├── CLAUDE.md                  # CMDB — architecture, thresholds, API reference
├── README.md                  # This file
├── app/
│   ├── performance_gui.py     # Web dashboard + MMIE bot engine  ← main entry point
│   └── performance_bot.py     # Headless CLI bot
├── config/                    # LaunchAgent plists
├── scripts/                   # install / uninstall helpers
├── docs/
│   ├── architecture.md        # Component diagram + data-flow + cache design
│   └── provisional-patent-application.md   # USPTO PPA technical spec
└── logs/                      # Runtime logs (git-ignored)
```

---

## Requirements

- macOS 13 Ventura or later (Apple Silicon & Intel)
- Python 3.11+ (Homebrew: `/opt/homebrew/bin/python3.11`)
- `psutil` (auto-installed by the install script)

---

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

---

## How It Works

Every second the bot runs a **single** `psutil.process_iter()` call that does two things at once:

1. **Collects** CPU %, RAM %, Swap % (all three syscalls executed once and cached for the whole tick)
2. **Detects CPU hogs inline** — processes over 85 % CPU per core are reniced to `nice=10`; processes that have calmed are restored via `_restore_calmed_procs()` (touches only `self.throttled`, usually 0–3 items — no full scan)

Less frequently:

| Interval | What happens |
|----------|--------------|
| 3 s | PRE `_compute_effective_tier()` + MMIE cascade (uses cached RAM reading — no extra syscall) |
| 5 s | `sysctl` kernel pressure oracle + `vm_stat` anatomy + OLS TTE forecast |
| 10 s | `psutil.disk_usage("/")` — result cached; no per-request disk reads |
| 30 s | XPC Respawn Guard scan; battery/AC detection |
| 60 s | Thermal check (`pmset`); zombie scan; memory leak tracking; SQLite batch flush (8 640 rows/day) |
| 24 h | App Predictions risk analysis from 90-day cache (aggregate SQL only) |

Events are stored in a `deque(maxlen=200)` — O(1) append, automatic discard of oldest.

---

## MMIE Remediation Tiers

| Tier | Static trigger | Predictive trigger | Action |
|------|---------------|-------------------|--------|
| 1 | ≥ 80 % RAM | TTE any | Log issue + identify top RSS consumers |
| 2 | ≥ 82 % RAM | TTE ≤ 10 min | Purgeable advisory + wired pressure warning + memory genealogy report |
| 3 | ≥ 87 % RAM | TTE ≤ 5 min | Genealogy-guided SIGSTOP of background daemons; auto-SIGCONT on recovery |
| 4 | ≥ 92 % RAM | TTE ≤ 2 min | Emergency SIGTERM of idle XPC / widget services (XPC guard enforced) |

When TTE-driven escalation fires, an amber **PREDICTIVE ESCALATION ACTIVE** banner appears on the dashboard.

---

## Dashboard Panels

| Panel | Contents |
|-------|----------|
| Metric strip | SVG ring gauges — CPU / Memory / Swap / Disk + Actions / Issues |
| Memory Intelligence | Arc gauge, % + GB, memory forecast ETA, predictive escalation banner, Active Tier (colour-coded), CPU-RAM Lock, XPC Blocked count, Cache (90d) size |
| Memory Composition | `vm_stat` bar — wired / active / inactive / compressed / free / purgeable |
| vm_stat rows | Total RAM, Swap Used, Disk Free, Uptime, Active Tier, CPU-RAM Lock, XPC Blocked, Cache (90d) |
| App Predictions | Risk-rated app cards from 90-day cache (appears after first 24 h analysis cycle) |
| Memory Families | Top-8 app families by aggregated RSS with proportional bars |
| CPU / Swap charts | 90-second sparklines |
| Bot Status | Throttled count, total actions, issues, RAM freed |
| Activity Log | Live event feed — FIX / WARN / ISSUE / INFO |
| Process Table | Top-12 processes with CPU/MEM bars; throttled badge; toggleable memory trend |

Activity log colours: 🟢 FIX &nbsp; 🟡 WARN &nbsp; 🔴 ISSUE &nbsp; 🔵 INFO

---

## Disk Cache

| Property | Value |
|----------|-------|
| Location | `~/Library/Application Support/performance-bot/metrics.db` |
| Format | SQLite (Python `sqlite3` stdlib — no extra dependency) |
| Schema | `ts, cpu_pct, mem_pct, swap_pct, disk_pct, pressure, eff_tier, tte_min` |
| Retention | 90 days (pruned automatically each day) |
| Write cadence | Batch flush every 60 s via `executemany()` |
| RAM usage | ≤ 4 KB in-memory buffer (60 tuples between flushes) |
| Max disk size | ~35–45 MB at 90 days / 1 row per 10 seconds |
| Reads | Aggregate SQL only — `AVG`, `COUNT`, `GROUP BY` — no raw rows in Python |

---

## License

Itzzdata
