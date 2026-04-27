# MAC Performance Bot

A lightweight, always-on macOS performance monitor with **autonomous closed-loop resource management**, a **19-engine 5-layer control architecture**, and an installable PWA dashboard.

Current version: **2.2.0**

---

## Features

- **Live PWA dashboard** — installable from browser, ring gauges, memory arc, activity log
- **Auto-throttles CPU hogs** via `nice()` — no manual intervention needed
- **5-layer engine architecture** — Signal Sensing → Model Layer → Consensus → Action/Learning → Causal Intelligence
- **Adaptive signal weights** — RWA/ACN reinforcement learning adjusts the 6-signal quorum weights hourly from remediation outcomes
- **Root-cause diagnosis** — CDA classifies system state as normal / leak / compressor_collapse / cpu_collision
- **Bayesian tier confidence** — BRL maintains a Beta posterior over tier-activation frequencies
- **Markov next-tier prediction** — PSM predicts the next effective tier and expected dwell time
- **Chronothermal regression** — CTRE maps hour-of-day × thermal load to memory stability zones
- **Ancestral impact propagation** — AIP scores process families by cascading RSS depth
- **Dynamic protected set** — ASZM elevates long-running, low-CPU system daemons to the protection list automatically
- **Reinforcement action coordinator** — RAC measures post-action RAM deltas (evaluated at 120 s to allow page reclaim) to label each remediation as success/failure; confirmed rescues increment `crises_averted`
- **Value-add achievement panel** — live dashboard strip: crises averted / all-time GB saved / % time RAM held below 87% / biggest single save; backed by `interventions_today()` SQLite aggregate
- **Signal integrity validation** — SIE applies z-score anomaly detection per signal; low-confidence signals are down-weighted in ACN
- **Model ensemble governance** — MEG tracks rolling residuals per MMAF model and promotes the historically best-fit model
- **4-tier memory remediation cascade** — observe → advisory → SIGSTOP idle daemons → emergency termination
- **MSCEE 6-signal quorum** — RAM %, TTE, kernel oracle, CPI, swap velocity, circadian pattern; requires 0.55 weighted vote to escalate
- **Graduated Thaw Sequencing (GTS)** — RSS-ascending SIGCONT with 2 s gap and RAM-gate abort
- **RSS Velocity Momentum Scoring (RVMS)** — 1×–2× freeze-priority boost for fast-growing processes
- **MMAF 3-model forecaster** — linear OLS / quadratic / exponential; best-RSS winner per tick drives TTE
- **Compression Efficiency Oracle (CEO)** — CPI signal flags compressor headroom depletion before RAM saturates
- **Adaptive threshold calibration (ATCE)** — hourly self-tuning of Tier 2/3/4 thresholds from 30-day cache percentiles
- **Circadian pre-freeze (CMPE)** — proactive daemon freeze during historically high-pressure hours
- **Thermal-memory coupling (TMCP)** — EMA-learned coefficient shortens TTE estimate under CPU throttle
- **CPU-RAM Conflict Resolution Gate** — blocks CPU priority restoration when the process is a top RAM owner during active memory pressure
- **XPC Respawn Guard** — detects launchd-managed services that respawn within 10 s and blocklists them
- **90-day disk cache** — SQLite store of metric history; flushed every 60 s; pruned daily; powers all engine learning loops
- **Zero heavy dependencies** — only `psutil` + Python stdlib; optional `onnx`/`onnxruntime` for CDA ONNX export
- **Lightweight by design** — single `psutil.process_iter()` call per second; all syscall results cached; `O(1)` event ring-buffer

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
│   ├── performance_gui.py     # Web dashboard + full engine stack  ← main entry point
│   └── performance_bot.py     # Headless CLI bot
├── config/                    # LaunchAgent plists
├── scripts/                   # install / uninstall helpers
├── docs/
│   ├── architecture.md        # 5-layer diagram + data-flow + engine schedule
│   └── provisional-patent-application.md   # USPTO PPA technical spec
└── logs/                      # Runtime logs (git-ignored)
```

---

## Requirements

- macOS 13 Ventura or later (Apple Silicon & Intel)
- Python 3.11+ (Homebrew: `/opt/homebrew/bin/python3.11`)
- `psutil` (auto-installed by the install script)
- `onnx ≥ 1.14` + `onnxruntime ≥ 1.16` — optional; enables CDA ONNX model export after 200 training samples

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

Every second the bot runs a **single** `psutil.process_iter()` call that collects metrics and detects CPU hogs inline. Additionally:

| Interval | What happens |
|----------|--------------|
| 1 s | `_collect()` — metrics + CPU throttle + SIE signal confidence + RAC outcome evaluation |
| 3 s | `_check_memory()` — MSCEE/ACN tier decision + PSM Markov prediction + CDA root-cause diagnosis |
| 5 s | `sysctl` + `vm_stat` + MMAF/MEG forecast + CEO CPI + TMCP TTE + AIP ancestry |
| 10 s | `psutil.disk_usage("/")` — cached; no per-request disk reads |
| 30 s | XPC Respawn Guard scan; battery/AC detection; idle XPC sweep |
| 60 s | Thermal check (`pmset`); zombie scan; memory leak tracking; CMPE circadian check; SQLite batch flush |
| 300 s | `~/Library/Caches` size warning |
| 3600 s | ATCE threshold calibration; TMCP coupling update; RWA weight update; CTRE stability regression; ASZM zone recalibration; BRL prior update |
| 30 days | CDA model training (requires ≥ 200 labeled samples) |

Events are stored in a `deque(maxlen=200)` — O(1) append, automatic discard of oldest.

---

## 5-Layer Engine Architecture

| Layer | Name | Engines |
|-------|------|---------|
| 1 | Signal Sensing | SIE |
| 2 | Model Layer | MMAF, MEG, CEO, TMCP, CTRE, AIP |
| 3 | Consensus and Decision | ACN, MSCEE, PSM, BRL |
| 4 | Action and Learning | ATCE, CMPE, RVMS, GTS, ASZM, RAC, RWA, XPC Guard |
| 5 | Causal Intelligence | CDA |

---

## Remediation Tiers

| Tier | Static trigger | Predictive trigger | Action |
|------|---------------|-------------------|--------|
| 1 | ≥ 80 % RAM | — | Log issue + identify top RSS consumers |
| 2 | ≥ 82 % RAM | TTE ≤ 10 min | Purgeable advisory + wired pressure warning + genealogy report |
| 3 | ≥ 87 % RAM | TTE ≤ 5 min | Genealogy-guided SIGSTOP of background daemons; auto-SIGCONT on recovery |
| 4 | ≥ 92 % RAM | TTE ≤ 2 min | Emergency SIGTERM of idle XPC / widget services (XPC guard enforced) |

Thresholds self-tune hourly via ATCE. When TTE-driven escalation fires, an amber **PREDICTIVE ESCALATION ACTIVE** banner appears on the dashboard.

---

## Dashboard Panels

| Panel | Contents |
|-------|----------|
| Metric strip | SVG ring gauges — CPU / Memory / Swap / Disk + **Achievement banner** (Crises Averted / Total RAM Saved / Time Below 87% / Biggest Save) |
| Memory Intelligence | Arc gauge, % + GB, MMAF forecast ETA, predictive escalation banner, Active Tier, CPU-RAM Lock, XPC Blocked, Cache size |
| vm_stat rows | RAM, Swap, Disk, Uptime, Active Tier, CPU-RAM Lock, XPC Blocked, Cache, Forecast Model, CPI, Swap Velocity, Thermal Coupling |
| v2.0 rows | Root Cause (CDA), BRL Confidence, ACN Weights sparkbar, Signal Integrity traffic-light, PSM Next Tier, CTRE Zone stability, Action Efficacy, ASZM Protected+ |
| Memory Composition | `vm_stat` bar — wired / active / inactive / compressed / free / purgeable |
| App Predictions | Risk-rated app cards from 90-day cache (appears after first 24 h analysis cycle) |
| Memory Families | Top-8 app families by aggregated RSS with proportional bars |
| CPU / Swap charts | 90-second sparklines |
| Bot Status | Throttled count, total actions, issues, RAM freed (terminated), Memory Paused (SIGSTOP'd) |
| Activity Log | Live event feed — FIX / WARN / ISSUE / INFO |
| Process Table | Top-12 processes with CPU/MEM bars; throttled badge; toggleable memory trend |

Activity log colours: 🟢 FIX &nbsp; 🟡 WARN &nbsp; 🔴 ISSUE &nbsp; 🔵 INFO

---

## Disk Cache

| Property | Value |
|----------|-------|
| Location | `~/Library/Application Support/performance-bot/metrics.db` |
| Format | SQLite (Python `sqlite3` stdlib — no extra dependency) |
| Core schema | `ts, cpu_pct, mem_pct, swap_pct, disk_pct, pressure, eff_tier, tte_min, thermal_pct` |
| v2.0 tables | `remediation_outcomes` (RAC outcome log); `signal_weights` (RWA weight history) |
| Retention | 90 days (pruned automatically each day) |
| Write cadence | Batch flush every 60 s via `executemany()` |
| Max disk size | ~35–45 MB at 90 days / 1 row per 10 seconds |
| Reads | Aggregate SQL only — `AVG`, `COUNT`, `GROUP BY` — no raw rows in Python |

---

## License

Itzzdata
