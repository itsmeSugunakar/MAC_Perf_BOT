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
| **Version**        | 2.1.0                                               |
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
3. **Predicts** memory exhaustion via the Multi-Model Adaptive Forecaster (MMAF) — a 3-model ensemble (linear OLS, quadratic, exponential) that selects the best-fit model per tick to compute Time-to-Exhaustion (TTE)
4. **Remediates** through a 4-tier cascade driven by the Multi-Signal Consensus Escalation Engine (MSCEE) — a 6-signal weighted quorum (RAM %, TTE, kernel oracle, compression CPI, swap velocity, circadian pattern) — using Graduated Thaw Sequencing (GTS) and RSS Velocity Momentum Scoring (RVMS)
5. **Surfaces** everything through a live PWA browser dashboard
6. **Auto-starts** at login via a macOS LaunchAgent
7. **Analyses** memory at kernel depth via the Multi-Dimensional Memory Intelligence Engine (MMIE) and Compression Efficiency Oracle (CEO)
8. **Accumulates** 90 days of metric history on disk (SQLite) for application-level performance predictions and self-calibration
9. **Runs lean** — single `psutil.process_iter()` scan per second, all syscalls cached, `O(1)` event deque
10. **Self-tunes** remediation thresholds via the Adaptive Threshold Calibration Engine (ATCE), learns thermal→memory coupling via the Thermal-Memory Coupling Predictor (TMCP), and applies proactive pre-freezes via the Circadian Memory Pattern Engine (CMPE)
11. **Adapts signal weights** dynamically via Reinforcement-Weighted Arbitration (RWA) and Adaptive Consensus Network (ACN) — remediation outcome history drives hourly EMA updates to the 6-signal quorum weights
12. **Validates signal quality** via Signal Integrity Estimator (SIE) — z-score anomaly detection per signal; noisy signals are down-weighted before entering the quorum
13. **Governs model selection** via Model Ensemble Governance (MEG) — rolling residual history promotes the historically best-fit MMAF model
14. **Predicts state transitions** via Predictive State Machine (PSM) — Markov chain over tier transitions predicts next tier and expected dwell time
15. **Quantifies tier confidence** via Bayesian Reasoning Layer (BRL) — Beta prior over tier-activation frequencies combined with signal agreement likelihood
16. **Profiles thermal–time stability** via Chronothermal Regression Engine (CTRE) — hour-of-day × thermal load OLS regression produces per-hour stability scores
17. **Scores process family impact** via Ancestral Impact Propagation (AIP) — recursive RSS depth scoring across full ppid tree; detects cascading leak patterns
18. **Measures remediation efficacy** via Reinforcement Action Coordinator (RAC) — 30 s delayed outcome evaluation; RAM delta classified as success/failure and stored for RWA
19. **Maintains a dynamic protection zone** via Adaptive Safety Zone Mapping (ASZM) — criticality-scored long-running system daemons are automatically elevated to the PROTECTED set
20. **Diagnoses root causes** via Causal Diagnostic Agent (CDA) — rule-based or ONNX softmax classifier (normal / leak / compressor_collapse / cpu_collision); ONNX model auto-trains from 90-day cache after 200 labeled samples

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
| 1 s | `_collect()` | Single `process_iter()` scan — metrics + CPU throttle detect + `_restore_calmed_procs()` + swap velocity |
| 3 s | `_check_memory()` | MSCEE effective tier + MMIE cascade (uses cached `_last_vm`) |
| 5 s | `_update_pressure_and_forecast()` | sysctl oracle + `vm_stat` + MMAF forecast + CEO CPI + TMCP TTE adjustment + ancestry |
| 10 s | `_check_disk()` | Disk usage — stores `disk_pct` / `disk_free_gb` for snapshot |
| 30 s | `_check_power_mode()` | Battery vs AC detection |
| 30 s | `_detect_xpc_respawn()` | XPC Respawn Guard scan |
| 30 s (IDLE_SWEEP_S) | `_sweep_idle_services()` | Tier 4 idle XPC/widget termination |
| 60 s | `_check_thermal()` | `pmset` thermal throttle check |
| 60 s | `_check_zombies()` | Zombie process detection |
| 60 s | `_track_memory_leaks()` | Per-process RSS growth rate |
| 60 s | `_check_circadian_pressure()` | CMPE hour-of-day profile refresh + proactive pre-freeze |
| 60 s | `cache.flush()` + `cache.prune()` | Batch SQLite write + daily prune gate |
| 300 s | `_check_caches()` | `~/Library/Caches` size warning |
| 3600 s | `_analyse_app_predictions()` | 90-day cache risk analysis (daily gate inside) |
| 3600 s | `_calibrate_thresholds()` | ATCE: recalibrate Tier 2/3/4 thresholds from 30-day cache percentiles |
| 3600 s | `_compute_thermal_coupling()` | TMCP: update thermal→memory EMA coefficient from cache |

### Component Responsibilities

| Component                        | File                     | Role                                                                        |
|----------------------------------|--------------------------|-----------------------------------------------------------------------------|
| `BotEngine`                      | `app/performance_gui.py` | Background thread; collects metrics, remediates                             |
| **MMIE methods**                 | `app/performance_gui.py` | Kernel oracle, vm_stat, genealogy, forecast, freeze/thaw                    |
| **MMAF**                         | `app/performance_gui.py` | `_compute_mem_forecast()` — 3-model ensemble (linear/quadratic/exponential); selects winner by minimum RSS error |
| **CEO**                          | `app/performance_gui.py` | `_compute_compression_pressure()` — CPI = compressed/(compressed+purgeable); signals compressor headroom depletion |
| **MSCEE**                        | `app/performance_gui.py` | `_compute_effective_tier()` — 6-signal weighted quorum replaces 2-signal `max()`; tier adopted only when vote ≥ 0.55 |
| **ATCE**                         | `app/performance_gui.py` | `_calibrate_thresholds()` — hourly self-tuning of Tier 2/3/4 thresholds from 30-day cache 75th/85th/93rd percentiles |
| **CMPE**                         | `app/performance_gui.py` | `_check_circadian_pressure()` + `_build_circadian_profile()` — hour-of-day SQL aggregate; proactive pre-freeze |
| **TMCP**                         | `app/performance_gui.py` | `_adjust_tte_for_thermal()` + `_compute_thermal_coupling()` — EMA-learned thermal→memory coefficient; shortens TTE under throttle |
| **GTS**                          | `app/performance_gui.py` | `_thaw_frozen_daemons()` — RSS-ascending sequential SIGCONT with 2 s gap and memory feedback gate |
| **RVMS**                         | `app/performance_gui.py` | `_get_process_velocity()` — velocity multiplier [1×, 2×] on freeze composite score |
| **CPU-RAM Conflict Gate**        | `app/performance_gui.py` | `_restore_calmed_procs()` — defers `nice(0)` for top-RAM families under Tier 3+ lock |
| **Genealogy Freeze Scoring**     | `app/performance_gui.py` | `_freeze_background_daemons()` — `(family×2 + pattern×1) × velocity_boost` |
| **XPC Respawn Guard**            | `app/performance_gui.py` | `_detect_xpc_respawn()` — blocklists respawning launchd services            |
| **MetricsCache**                 | `app/performance_gui.py` | SQLite 90-day disk store; `thermal_pct` column; v2.0 tables: `remediation_outcomes`, `signal_weights` |
| `_restore_calmed_procs()`        | `app/performance_gui.py` | CPU priority restore loop — only touches `self.throttled` (0–3 items)      |
| **App Predictions**              | `app/performance_gui.py` | `_analyse_app_predictions()` — 24 h risk analysis from cache                |
| `Handler` (HTTP)                 | `app/performance_gui.py` | Serves PWA dashboard + JSON API + manifest + SVG icon                       |
| `performance_bot.py`             | `app/performance_bot.py` | Headless variant (LaunchAgent, no browser needed)                           |
| LaunchAgent (GUI)                | `config/*.plist`         | macOS service manager — starts bot at login                                 |
| Dashboard HTML+JS                | Embedded in `gui.py`     | PWA; polls `/stats` every 1 s; v2.0 rows: Root Cause, BRL Confidence, ACN Weights, Signal Integrity, PSM Next Tier, CTRE Zone, Action Efficacy, ASZM Protected+ |
| **SIE**                          | `app/performance_gui.py` | `_compute_signal_confidence()` — z-score integrity validation; confidence [0.5, 1.0] per signal |
| **MEG**                          | `app/performance_gui.py` | Extended `_compute_mem_forecast()` — meta-weight by historical residuals; governs MMAF model selection |
| **ACN**                          | `app/performance_gui.py` | `_compute_effective_tier()` modified — uses `_acn_weights` (RWA-adaptive) × SIE confidence |
| **RWA**                          | `app/performance_gui.py` | `_update_rwa_weights()` — hourly EMA weight update from `remediation_outcomes` |
| **CTRE**                         | `app/performance_gui.py` | `_compute_ctre()` — per-hour variance stability 0–1 from 30-day cache       |
| **AIP**                          | `app/performance_gui.py` | `_compute_aip()` — family-tree RSS impact scores with cascade risk detection |
| **RAC**                          | `app/performance_gui.py` | `_record_rac_action()` + `_evaluate_rac_outcomes()` — records and evaluates remediation efficacy |
| **PSM**                          | `app/performance_gui.py` | `_update_psm()` + `_psm_predict()` — Markov next-tier prediction + dwell estimation |
| **BRL**                          | `app/performance_gui.py` | `_update_brl()` + `_compute_brl_confidence()` — Bayesian posterior confidence for tier decisions |
| **ASZM**                         | `app/performance_gui.py` | `_update_aszm()` — criticality scoring; adds long-lived low-CPU daemons to dynamic PROTECTED set |
| **CDA**                          | `app/performance_gui.py` | `_diagnose_root_cause()` — rule-based or ONNX softmax: normal \| leak \| compressor_collapse \| cpu_collision |

---

## 5. Runtime Thresholds (defaults)

### Core thresholds
| Parameter        | Default | Description                                      |
|------------------|---------|--------------------------------------------------|
| `CPU_WARN`       | 70 %    | Log a warning when a process hits this           |
| `CPU_THROTTLE`   | 85 %    | Renice the process to `nice=10`                  |
| `MEM_WARN`       | 80 %    | Emit a RAM pressure issue event (Tier 1)         |
| `DISK_WARN`      | 90 %    | Emit a low-disk **issue** event; 80 % emits a warning |
| `SWAP_WARN`      | 50 %    | Warn once when swap exceeds this; reset at 30 %  |
| `RENICE_VALUE`   | 10      | Nice increment applied to throttled processes    |
| `HISTORY_LEN`    | 90      | Seconds of CPU/RAM history shown in charts       |
| `CHECK_INTERVAL` | 1 s     | Polling cadence of `BotEngine`                   |
| `HTTP_PORT`      | 8765    | Localhost port for the web dashboard             |
| `CONSUMER_COOL_S`| 300 s   | Min seconds between top-RSS consumer reports     |
| `IDLE_MB_FLOOR`  | 15 MB   | Minimum RSS for a service to be Tier-4 eligible  |
| `IDLE_SWEEP_S`   | 30 s    | Frequency of `_sweep_idle_services()` calls      |

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

### MMAF — Multi-Model Adaptive Forecaster constants
| Parameter         | Default | Description                                              |
|-------------------|---------|----------------------------------------------------------|
| `MMAF_MIN_SAMPLES`| 10      | Minimum `mem_hist` samples before any model engages      |
| `MMAF_WINDOW`     | 30      | Rolling window size (seconds) for model fitting          |
| `MMAF_TARGET_PCT` | 95 %    | RAM % target for TTE extrapolation                       |

### CEO — Compression Efficiency Oracle constants
| Parameter             | Default | Description                                          |
|-----------------------|---------|------------------------------------------------------|
| `CPI_TIER2`           | 0.50    | CPI ≥ this emits an "efficiency degrading" issue     |
| `CPI_TIER3`           | 0.75    | CPI ≥ this emits a "compressor exhaustion" warning   |
| `CEO_MIN_COMPRESSED`  | 200 MB  | Minimum compressed memory before CEO signal is valid |

### MSCEE — Multi-Signal Consensus Escalation Engine constants
| Parameter        | Default | Description                                              |
|------------------|---------|----------------------------------------------------------|
| `MSCEE_QUORUM`   | 0.55    | Weighted vote share required to adopt a candidate tier   |

**S5 swap velocity tier thresholds (hard-coded in `_compute_effective_tier`):**

| Swap velocity  | S5 vote |
|----------------|---------|
| ≥ 100 MB/s     | tier 3  |
| ≥ 50 MB/s      | tier 2  |
| ≥ 20 MB/s      | tier 1  |
| < 20 MB/s      | tier 0  |

**MSCEE fallback:** If no candidate tier 1–4 achieves quorum, `effective_tier` falls back to `threshold_tier` (S1 / RAM-% signal alone), not to 0. S1 is always applied as a floor.

### GTS — Graduated Thaw Sequencer constants
| Parameter          | Default | Description                                            |
|--------------------|---------|--------------------------------------------------------|
| `GTS_WAIT_S`       | 2.0 s   | Gap between successive SIGCONT sends                   |
| `GTS_MEM_GATE_PCT` | 5.0 %   | Abort thaw if RAM rises more than this since thaw began|

### ATCE — Adaptive Threshold Calibration Engine constants
| Parameter        | Default | Description                                              |
|------------------|---------|----------------------------------------------------------|
| `ATCE_PERCENTILE`| 75      | 75th-pct → Tier 2 threshold; 85th → Tier 3; 93rd → Tier 4 |
| `ATCE_COOL_S`    | 3600 s  | Recalibrate at most once per hour                        |
| `ATCE_MIN_ROWS`  | 1000    | Minimum cache rows before calibration runs               |

### CMPE — Circadian Memory Pattern Engine constants
| Parameter              | Default | Description                                          |
|------------------------|---------|------------------------------------------------------|
| `CMPE_PRE_FREEZE_SCORE`| 70 %    | Hour avg ≥ this triggers proactive pre-freeze        |
| `CMPE_COOL_S`          | 3600 s  | Circadian profile refresh and check once per hour    |

### TMCP — Thermal-Memory Coupling Predictor constants
| Parameter         | Default | Description                                              |
|-------------------|---------|----------------------------------------------------------|
| `TMCP_LEARN_RATE` | 0.10    | EMA learning rate for thermal→memory coupling coefficient|
| `TMCP_COOL_S`     | 3600 s  | Recompute coupling factor once per hour                  |
| `TMCP_MIN_SAMPLES`| 5       | Minimum throttled-state rows before coupling is applied  |

### RVMS — RSS Velocity Momentum Scorer constants
| Parameter        | Default | Description                                              |
|------------------|---------|----------------------------------------------------------|
| `RVMS_MAX_BOOST` | 2.0×    | Maximum velocity momentum multiplier on freeze score     |

### SIE — Signal Integrity Estimator constants
| Parameter          | Default | Description                                              |
|--------------------|---------|----------------------------------------------------------|
| `SIE_WINDOW`       | 30      | Rolling window (samples) for z-score computation         |
| `SIE_ZSCORE_THRESH`| 3.0     | Flag signal as anomalous if \|z\| > this                 |

### MEG — Model Ensemble Governance constants
| Parameter               | Default | Description                                          |
|-------------------------|---------|------------------------------------------------------|
| `MEG_RESIDUAL_HISTORY`  | 5       | Residual samples per model for meta-weight           |

### RWA / ACN — Reinforcement-Weighted Arbitration / Adaptive Consensus Network
| Parameter          | Default | Description                                              |
|--------------------|---------|----------------------------------------------------------|
| `RWA_LEARN_RATE`   | 0.05    | EMA rate for weight adjustments                          |
| `RWA_MIN_WEIGHT`   | 0.02    | Floor: no signal weight drops to zero                    |
| `RWA_OUTCOMES_H`   | 24      | Hours of outcome history for accuracy query              |

### CTRE — Chronothermal Regression Engine constants
| Parameter          | Default | Description                                              |
|--------------------|---------|----------------------------------------------------------|
| `CTRE_MIN_SAMPLES` | 10      | Minimum samples per hour before regression valid         |
| `CTRE_COOL_S`      | 3600 s  | Recompute once per hour                                  |

### AIP — Ancestral Impact Propagation constants
| Parameter       | Default | Description                                                  |
|-----------------|---------|--------------------------------------------------------------|
| `AIP_MIN_MB`    | 50 MB   | Minimum family RSS to include in propagation                 |
| `AIP_MAX_DEPTH` | 3       | Max parent-child chain depth for recursive RSS sum           |

### RAC — Reinforcement Action Coordinator constants
| Parameter           | Default | Description                                              |
|---------------------|---------|----------------------------------------------------------|
| `RAC_EVAL_DELAY_S`  | 30 s    | Seconds after action before outcome is measured          |
| `RAC_SUCCESS_PCT`   | 2.0 %   | RAM must drop ≥ this % for an action to count as success |

### ASZM — Adaptive Safety Zone Mapping constants
| Parameter          | Default | Description                                              |
|--------------------|---------|----------------------------------------------------------|
| `ASZM_CRIT_SCORE`  | 0.8     | Criticality threshold → add process to dynamic protected |
| `ASZM_COOL_S`      | 3600 s  | Recalibrate dynamic protection set once per hour         |

### PSM — Predictive State Machine constants
| Parameter          | Default | Description                                              |
|--------------------|---------|----------------------------------------------------------|
| `PSM_HISTORY`      | 20      | Max tier-transition events tracked in Markov deque       |
| `PSM_DWELL_MIN_S`  | 3.0 s   | Min seconds in a tier before transition is counted       |

### BRL — Bayesian Reasoning Layer constants
| Parameter          | Default | Description                                              |
|--------------------|---------|----------------------------------------------------------|
| `BRL_PRIOR_ALPHA`  | 1.0     | Beta prior alpha (weak prior: ~10% tier activation)      |
| `BRL_PRIOR_BETA`   | 9.0     | Beta prior beta                                          |
| `BRL_COOL_S`       | 3600 s  | Update prior from cache once per hour                    |

### CDA — Causal Diagnostic Agent constants
| Parameter              | Default     | Description                                          |
|------------------------|-------------|------------------------------------------------------|
| `CDA_TRAIN_MIN_ROWS`   | 200         | Min labeled rows before model training runs          |
| `CDA_TRAIN_COOL_S`     | 2592000 s   | Retrain at most once per 30 days                     |
| `CDA_LR`               | 0.01        | SGD learning rate for softmax logistic regression    |
| `CDA_EPOCHS`           | 100         | Gradient-descent epochs per training run             |
| `CDA_LABEL_LEAK`       | 50 MB/min   | Growth rate threshold to label a row as "leak"       |
| `CDA_LABEL_COMP_CPI`   | 0.60        | CPI threshold to label a row as "compressor_collapse"|

To change a threshold, edit the constants at the top of `app/performance_gui.py`
and reload the LaunchAgent (`scripts/install_gui.sh`).

---

## 6. Dependencies

### Runtime
| Package  | Version  | Source   | Purpose                      |
|----------|----------|----------|------------------------------|
| `psutil`       | ≥ 5.9    | PyPI     | Cross-platform process/system metrics |
| `onnx`         | ≥ 1.14   | PyPI     | **Optional** — build + serialize CDA ONNX model graph |
| `onnxruntime`  | ≥ 1.16   | PyPI     | **Optional** — run CDA ONNX inference (CPU provider) |

All other imports are Python standard library (`http.server`, `threading`,
`sqlite3`, `json`, `subprocess`, `webbrowser`, `pathlib`, `math`).

`onnx` and `onnxruntime` are **optional**. Without them, the CDA engine falls back to
pure-Python softmax weight inference using the same trained coefficients. To enable full
ONNX export and inference: `pip install onnx onnxruntime`.

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
| `/stats`         | GET    | `application/json`             | Full snapshot: metrics + MMIE + product metrics |
| `/history`       | GET    | `application/json`             | 7-day hourly aggregates `[{hour, mem, cpu, swap}]` |
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
  ],
  "frozen_count":         int,       // number of processes currently SIGSTOP'd by Tier 3
  "leak_pids":            int,       // number of PIDs flagged as potential memory leaks this session
  "forecast_model":       str,       // MMAF winner: "linear"|"quadratic"|"exponential"|"none"
  "compression_pressure": float,     // CEO CPI: compressed/(compressed+purgeable); 0.0–1.0
  "swap_velocity":        float,     // MB/s swap growth rate (negative = shrinking)
  "cal_thresholds":       {          // ATCE live thresholds (null until 1000 cache rows)
    "tier2": float, "tier3": float, "tier4": float
  },
  "circadian_profile":    {          // CMPE hour-of-day avg RAM %; null until 30-day data
    "0": float, "1": float, ..., "23": float
  },
  "thermal_coupling":     float,     // TMCP learned coefficient (0.0 = none, 1.0 = strong)
  // ── v2.0 fields ────────────────────────────────────────────────────────────
  "signal_confidence":    {          // SIE confidence per signal (0.5–1.0)
    "cpu": float, "mem": float, "swap": float
  },
  "acn_weights":          {          // Live ACN weights updated by RWA (sum to 1.0)
    "s1": float, "s2": float, "s3": float,
    "s4": float, "s5": float, "s6": float
  },
  "brl_confidence":       float,     // BRL posterior confidence for current tier (0–1)
  "psm_next_tier":        int,       // PSM Markov-predicted next effective_tier (0–4)
  "psm_dwell_s":          float,     // Predicted dwell time in next tier (seconds)
  "action_efficacy":      {          // RAC avg RAM-drop % per action type
    "freeze_daemon": float, "sweep_xpc": float, "purgeable_advisory": float
  },
  "ctre_stability":       {          // CTRE stability score 0–1 per hour-of-day
    "0": float, ..., "23": float
  },
  "aip_impact":           [          // AIP ancestral impact rankings
    {
      "app": str, "impact_score": float,
      "cascade_depth": int, "child_mb": int, "cascade_risk": bool
    }
  ],
  "causal_diagnosis":     str,       // CDA root cause: normal|leak|compressor_collapse|cpu_collision
  "dynamic_protected":    int,       // ASZM net additions to PROTECTED set (not in base set)
  // ── v2.1 product metrics ───────────────────────────────────────────────────
  "performance_score":    int,       // 0–100 daily score; -1 = warming up (<10 min data)
                                     // formula: 100 − (0.5×avg_mem + 0.3×avg_cpu + 0.2×avg_swap) 24h
  "longterm_avg_mem":     float,     // 30-day average RAM %; >80% triggers upgrade recommendation
  "leak_pids_list":       [int]      // PIDs currently flagged as memory leaks
}
```

---

## 10. Performance Characteristics

The bot is designed to be self-effacing — it must not measurably degrade the system it monitors.

### Hot-path optimisations (v1.4.0 → v1.5.0)

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
| TTE forecast models | 1 (linear OLS) | 3 (MMAF: linear + quadratic + exponential; best RSS wins) |
| Tier escalation signals | 2 (RAM %, TTE) | 6 (MSCEE quorum: RAM, TTE, kernel oracle, CPI, swap velocity, circadian) |
| Daemon freeze scoring | `family×2 + pattern×1` | `(family×2 + pattern×1) × RVMS velocity boost [1×–2×]` |
| SIGCONT delivery | Bulk, simultaneous | GTS: RSS-ascending order, 2 s gap, RAM-gate abort |
| Tier thresholds | Static (82 / 87 / 92 %) | ATCE self-tunes hourly from 30-day cache percentiles |
| MetricsCache schema | 8 columns | 9 columns (`thermal_pct` added; auto-migrates existing DB) |

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
- `PROTECTED` set prevents touching system processes and the bot itself (includes `kernel_task`, `launchd`, `WindowServer`, `loginwindow`, `Finder`, `Dock`, `SystemUIServer`, `coreaudiod`, `cfprefsd`, `mds*`, `performance_bot`, `performance_gui`, `Python`, `python3`, `python`). `NEVER_TERMINATE` additionally guards authentication and Keychain services.
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
| SIGSTOP ≠ memory freed | SIGSTOP suspends a process but does NOT release its RSS. The "Memory Paused" counter shows MB suspended (v2.1 corrected label — was "RAM Freed"). Memory is only reclaimed when the process is SIGCONT'd and the OS reclaims its pages over time. |
| Menu bar requires `rumps` | `_start_menubar()` silently no-ops if `rumps` is not installed. Install with `pip install rumps`. On macOS 14+, the process may need `LSUIElement=1` in the plist to suppress a Dock icon. |
| `memory_pressure` sysctl | `kern.memorystatus_vm_pressure_level` may require SIP adjustments on some configurations. Falls back to percent-derived level automatically. |
| App Predictions cold start | The `_analyse_app_predictions()` panel is empty for the first 24 h. After the first full day the cache has enough data to show risk ratings. |
| Cache disk size | At 1 row/10 s for 90 days the database reaches ~35–45 MB — acceptable on all Macs. Reduce `CACHE_RETENTION_DAYS` only if storage is extremely limited. |
| PRE TTE requires 20 samples | The Predictive Remediation Engine requires `TTE_MIN_SAMPLES` (20) seconds of `mem_hist` before TTE-driven escalation activates. |
| ATCE cold start | `_calibrate_thresholds()` requires `ATCE_MIN_ROWS` (1 000) cache rows before self-tuning activates. Static defaults remain in effect until then. |
| GTS thaw latency | Graduated Thaw Sequencing introduces a `GTS_WAIT_S` (2 s) delay per daemon. Thawing 5 frozen daemons takes up to 10 s. |
| CMPE circadian cold start | `_build_circadian_profile()` needs at least 24 h (ideally 30 days) of cache data to produce meaningful hour-of-day averages. Proactive pre-freeze is suppressed during this period. |
| CMPE UTC vs local time | `_build_circadian_profile()` groups rows by `ts/3600 % 24` (Unix epoch hours = UTC). On systems more than a few hours from UTC the hour-of-day profile will be offset from the user's perceived local clock. |
| ATCE sanity guard | `_calibrate_thresholds()` rejects a calibration result unless `60 ≤ tier2 ≤ 92` and `tier2 < tier3 < tier4`. If the 30-day distribution is too flat or inverted, static defaults remain in effect. |
| `_check_disk` 80 % warning | Disk usage emits an ISSUE at ≥ 90 % and a WARN at ≥ 80 %. Only the 90 % threshold is user-configurable (`DISK_WARN`). |
| BRL cold start | `_update_brl()` requires at least some rows in the cache `metrics` table; prior counts remain at `BRL_PRIOR_ALPHA` until the first hourly BRL update. |
| CTRE 10-sample minimum | `_compute_ctre()` requires `CTRE_MIN_SAMPLES` (10) rows per hour-of-day before computing stability; first valid result available after ~2 days of data. |
| ASZM uptime window | `_update_aszm()` runs once per hour; newly spawned processes may not appear in `_dynamic_protected` for up to 1 hour. |
| CDA cold start | `_cda_train_model()` requires `CDA_TRAIN_MIN_ROWS` (200) labeled rows from `remediation_outcomes`; rule-based fallback is active until training succeeds. |
| CDA ONNX optional | ONNX/onnxruntime are optional dependencies. Without them, CDA uses pure-Python weight inference (same model, no file serialisation). |
| PSM Markov cold start | `_psm_predict()` returns current tier until `PSM_HISTORY` (20) tier transitions have been observed; predictions improve with uptime. |
| RAC evaluation delay | Each remediation action's outcome is evaluated `RAC_EVAL_DELAY_S` (30 s) later. Fast pressure spikes may clear before evaluation completes, inflating success rate. |

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
| 2026-04-10 | 1.5.0   | itsmeSugunakar | 8 patent-level engine innovations: **MMAF** — 3-model adaptive forecaster (linear/quadratic/exponential, best-RSS selection); **CEO** — Compression Efficiency Oracle (CPI signal); **MSCEE** — 6-signal weighted quorum replaces 2-signal `max()` (signals: RAM %, TTE, kernel oracle, CPI, swap velocity, circadian); **GTS** — Graduated Thaw Sequencing (RSS-ascending SIGCONT, 2 s gap, RAM gate); **RVMS** — RSS Velocity Momentum Scorer (1×–2× freeze boost); **ATCE** — Adaptive Threshold Calibration Engine (hourly self-tuning from 30-day cache percentiles); **CMPE** — Circadian Memory Pattern Engine (hour-of-day SQL profile, proactive pre-freeze); **TMCP** — Thermal-Memory Coupling Predictor (EMA-learned TTE shortening under thermal throttle); `MetricsCache` schema extended with `thermal_pct` column (auto-migrates); 4 new dashboard vmrows (Forecast Model, CPI, Swap Velocity, Thermal Coupling); `/stats` extended with 6 new fields |
| 2026-04-18 | 2.1.0   | itsmeSugunakar | **Product UX Layer** — 10 user-outcome improvements on top of the v2.0 engine: **Performance Score** (0–100 daily, `daily_performance_score()` from 24h SQLite); **Memory Paused** (accurate label for SIGSTOP — was "RAM Freed"); **Tier labels** renamed to user language (All Good / Watching / Intervening / Rescue Mode / Emergency); **Root Cause Banner** (plain-English, prominent, hidden when normal); **Simple/Expert mode** toggle (10 engine-telemetry rows hidden by default, `localStorage` persisted); **Activity Log filter** (`category="bot"` on calibration `_emit()` calls, "Bot Logs" toggle in titlebar); **7-Day History tab** (`hourly_history()` MetricsCache method, `/history` HTTP endpoint, Chart.js multi-line chart); **RAM Recommendation** (`longterm_avg_mem()` 30d query, advisory card when avg > 80%); **Leak hints** in process table (LEAK badge + 💡 Restart? for leak-flagged processes); **macOS Menu Bar** (`_start_menubar()` via `rumps`, daemon thread, optional); LaunchAgent path updated to `~/Documents/performance-bot/` |
| 2026-04-12 | 2.0.0   | itsmeSugunakar | **Autonomous Dynamic Resource Management Agent** — 11 new cognitive engines across a 5-layer governed control model: **SIE** — Signal Integrity Estimator (z-score anomaly confidence per signal); **MEG** — Model Ensemble Governance (meta-weight historical residuals over MMAF models); **ACN** — Adaptive Consensus Network (RWA-driven adaptive weights replace static MSCEE weights); **RWA** — Reinforcement-Weighted Arbitration (hourly EMA weight update from `remediation_outcomes` table); **CTRE** — Chronothermal Regression Engine (per-hour variance stability from 30-day cache); **AIP** — Ancestral Impact Propagation (family-tree RSS depth scoring + cascade risk detection); **RAC** — Reinforcement Action Coordinator (records and evaluates remediation outcomes via new SQLite table); **PSM** — Predictive State Machine (Markov next-tier prediction + dwell estimation); **BRL** — Bayesian Reasoning Layer (Beta prior tier-frequency + likelihood posterior confidence); **ASZM** — Adaptive Safety Zone Mapping (criticality scoring → dynamic `_dynamic_protected` set); **CDA** — Causal Diagnostic Agent (pure-Python softmax LR + optional ONNX export: normal \| leak \| compressor_collapse \| cpu_collision); new SQLite tables `remediation_outcomes` + `signal_weights` (auto-migrates existing DB); 8 new dashboard vmrows (Root Cause, BRL Confidence, ACN Weights, Signal Integrity, PSM Next Tier, CTRE Zone, Action Efficacy, ASZM Protected+); `/stats` extended with 10 new fields |

---

*This file is the single source of truth for the MAC Performance Bot application.
Update it whenever architecture, thresholds, or deployment procedures change.*
