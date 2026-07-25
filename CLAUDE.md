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
| **Version**        | 2.6.0                                               |
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
21. **Surfaces AI-driven recommendations** via the Neural Performance Analyzer (NPA) — a pure-Python 3-layer MLP (11→12→6→3) trained every 6 hours on a stratified sample of the full 30-day cache; predicts next-60-second RAM and CPU levels plus an anomaly score, then generates up to 5 prioritised plain-English recommendations displayed in the dashboard "AI Insights" panel; each actionable recommendation (memory leak, RAM pressure, CPU hog) carries a one-click button that fires directly into the remediation cascade via `POST /remediate` or `POST /action`; recent bot action outcomes (MB freed, success/fail) surface in the AI panel as a "Recent Actions" feed

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
│                              │  │ThreadingHTTPServer:8765│ │ │
│                              │  │  GET /       → HTML  │  │ │
│                              │  │  GET /stats  → JSON  │  │ │
│                              │  │  GET /pause  → ctrl  │  │ │
│                              │  │  /llm/*   → LLM Insights│ │
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
| 60 s | `_check_crash_reports()` | Crash Report Monitor — surfaces new `~/Library/Logs/DiagnosticReports/*.ips` entries into the Activity Log |
| 60 s | `_track_memory_leaks()` | Per-process RSS growth rate |
| 60 s | `_check_circadian_pressure()` | CMPE hour-of-day profile refresh + proactive pre-freeze |
| 60 s | `_run_npa()` | NPA inference — predict next-60s RAM/CPU + generate recommendations; trains from DB on first tick and every 6 h |
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
| **Crash Report Monitor**         | `app/performance_gui.py` | `_check_crash_reports()` — reads only the first-line JSON header of new `~/Library/Logs/DiagnosticReports/*.ips` files; seeds pre-existing backlog silently on first run, then emits an `issue` event per new crash via `_emit()` |
| **MetricsCache**                 | `app/performance_gui.py` | SQLite 90-day disk store; `thermal_pct` column; v2.0 tables: `remediation_outcomes`, `signal_weights`; WAL journal mode (`PRAGMA journal_mode=WAL`) so the once-daily `prune()` writer doesn't block the once-a-second `/stats` reader; `interventions_today()` result cached ~20s for the same reason |
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
| **NPA**                          | `app/performance_gui.py` | `_run_npa()` + `NeuralPerformanceAnalyzer` class — 3-layer MLP trained on stratified 30-day cache sample; `fetch_training_data()` / `fetch_recent_window()` on `MetricsCache`; `generate_recommendations()` combines NN predictions with live bot state; every rec now carries `pid` + `action_type` (`"freeze"` / `"remediate"` / `"throttle"` / `None`) so the dashboard can render actionable buttons; `_run_npa()` injects `tte_min`, `throttled_names`, `throttled_pids` into `bot_state`; `BotEngine.trigger_remediation(tier)` is the user-initiated entry point |
| **LLM Insights**                 | `app/llm_engine.py`      | Offline, on-device MLX language model (**optional** — degrades cleanly if `mlx-lm` isn't installed) powering the dashboard's Insights tab: crash-report explanations (on-demand), daily/weekly narrative digests (cooldown-gated in `BotEngine.run()`, generated by a background worker, never inline), and free-form Ask-panel questions grounded in recent telemetry. Model loads lazily on first use and unloads after `LLM_IDLE_UNLOAD_S` of inactivity; all generation runs on a single serialized job-queue worker thread so it never blocks the `ThreadingHTTPServer`. |

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
| `RAC_EVAL_DELAY_S`  | 120 s   | Seconds after action before outcome is measured (raised from 30 s — OS needs time to reclaim pages after SIGSTOP) |
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

### NPA — Neural Performance Analyzer constants
| Parameter              | Default  | Description                                                    |
|------------------------|----------|----------------------------------------------------------------|
| `NPA_TRAIN_MIN_ROWS`   | 150      | Minimum training samples before the model is used for inference|
| `NPA_RETRAIN_COOL_S`   | 21600 s  | Retrain at most every 6 hours                                  |
| `NPA_LR`               | 0.002    | SGD learning rate (low to prevent gradient explosion)          |
| `NPA_EPOCHS`           | 40       | SGD epochs per training run                                    |
| `NPA_MAX_ROWS`         | 600      | Maximum training samples (strided from full 30-day history)    |

**NPA architecture:** 11 inputs → 12 hidden (ReLU) → 6 hidden (ReLU) → 3 outputs

| Layer | Activation | Gradient | Purpose |
|-------|-----------|----------|---------|
| Output 0 (pred_mem) | Clipped linear `max(0, min(1, raw))` | `out − target` (bounded to [-1,1]) | Next-60s RAM forecast |
| Output 1 (pred_cpu) | Clipped linear `max(0, min(1, raw))` | `out − target` (bounded to [-1,1]) | Next-60s CPU forecast |
| Output 2 (anomaly)  | Sigmoid | `(out − target) × out × (1 − out)` | Anomaly score 0–1 |

**Training data:** `fetch_training_data()` fetches **all** rows from the past 30 days and strides every N-th row to produce ≤600 stratified samples covering the full history. The `y` target for each sample uses the **actual next 6 consecutive rows** (60 s window) — not subsampled rows — so targets are always the true immediate future. Xavier weight init (seed 42) with z-score feature normalisation; means/stds stored on the model instance for inference.

**Recommendation priorities:** 0 = critical (red), 1 = warning (orange), 2 = info (blue), 3 = tip (muted), 4 = all-clear (green). Triggers in priority order: pred_mem ≥ 90 % → critical; pred_mem ≥ 85 % / anomaly ≥ 0.70 / leak_pids / thermal throttle → warning; pred_cpu ≥ 75 % / disk ≥ 88 % → info; disk 80–88 % / circadian peak / longterm_avg ≥ 82 % → tip; nothing triggered → all-clear.

To change a threshold, edit the constants at the top of `app/performance_gui.py`
and reload the LaunchAgent (`scripts/install_gui.sh`).

### LLM Insights constants (offline MLX — optional, see `app/llm_engine.py`)
| Parameter                    | Default     | Description                                                   |
|-------------------------------|-------------|----------------------------------------------------------------|
| `LLM_DAILY_DIGEST_COOL_S`     | 86400 s     | Generate the daily digest at most once/day (in `performance_gui.py`, checked in `BotEngine.run()`) |
| `LLM_WEEKLY_DIGEST_COOL_S`    | 604800 s    | Generate the weekly digest at most once/week (same)            |
| `LLM_MODEL_REPO`              | `mlx-community/Qwen2.5-3B-Instruct-4bit` | MLX-community HF repo, ~2GB, 4-bit quantized |
| `LLM_IDLE_UNLOAD_S`           | 600 s       | Unload the model from RAM after this long with no generation calls |
| `LLM_IDLE_CHECK_S`            | 60 s        | Idle-unload watchdog poll interval                              |
| `LLM_CRASH_PROMPT_MAX_CHARS`  | 6000        | Cap on `.ips` content fed into the crash-explain prompt          |
| `LLM_DIGEST_MAX_ROWS`         | 200         | Max hourly rows fed into a digest prompt (downsampled above this)|
| `LLM_DIGEST_PROMPT_MAX_CHARS` | 8000        | Hard cap on the assembled digest prompt                          |
| `LLM_ASK_PROMPT_MAX_CHARS`    | 8000        | Hard cap on the assembled Ask-panel context prompt                |
| `LLM_MAX_NEW_TOKENS_EXPLAIN`  | 300         | Generation length cap — crash explanation                        |
| `LLM_MAX_NEW_TOKENS_DIGEST`   | 400         | Generation length cap — digest                                   |
| `LLM_MAX_NEW_TOKENS_ASK`      | 400         | Generation length cap — Ask answers                               |
| `LLM_JOB_RETENTION_S`         | 3600 s      | Sweep completed job entries from memory after this long           |

The model loads lazily on first actual generation call (never at import, never at
`BotEngine.__init__`) and all generation runs on a single serialized background worker
thread — callers get a `job_id` immediately and poll `GET /llm/job?id=` for the result, so a
slow generation never blocks the dashboard's `/stats` polling.

---

## 6. Dependencies

### Runtime
| Package  | Version  | Source   | Purpose                      |
|----------|----------|----------|------------------------------|
| `psutil`       | ≥ 5.9    | PyPI     | Cross-platform process/system metrics |
| `onnx`         | ≥ 1.14   | PyPI     | **Optional** — build + serialize CDA ONNX model graph |
| `onnxruntime`  | ≥ 1.16   | PyPI     | **Optional** — run CDA ONNX inference (CPU provider) |
| `mlx-lm`       | latest   | PyPI     | **Optional** — offline on-device LLM inference (Apple MLX) powering the Insights tab (crash explanations, daily/weekly digests, Ask panel) |

All other imports are Python standard library (`http.server`, `threading`,
`sqlite3`, `json`, `subprocess`, `webbrowser`, `pathlib`, `math`).

`onnx` and `onnxruntime` are **optional**. Without them, the CDA engine falls back to
pure-Python softmax weight inference using the same trained coefficients. To enable full
ONNX export and inference: `pip install onnx onnxruntime`.

`mlx-lm` is **optional**. Without it, the dashboard's Insights tab shows an install-hint
state and none of the LLM features are exposed — nothing else in the app is affected.
Install with `pip install mlx-lm`; first use downloads
`mlx-community/Qwen2.5-3B-Instruct-4bit` (~2GB) from Hugging Face, cached under
`~/.cache/huggingface`. Everything after that first download runs fully offline, on-device,
with no network calls. Requires Apple Silicon (MLX is Apple's own ML framework).

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
| `KeepAlive`      | `true` — launchd restarts the bot if it crashes or is killed |
| `ThrottleInterval` | `30` — minimum 30 s between restarts to prevent rapid respawn loops |
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
| `/action`        | POST   | `{"ok":bool}`                  | Process action: `{pid, action: "freeze"\|"thaw"\|"kill"\|"throttle"}` |
| `/remediate`     | POST   | `{"ok":true}`                  | User-initiated remediation: `{tier: 1–4}` — calls `trigger_remediation(tier)` directly |
| `/llm/status`    | GET    | `{"available":bool}`           | Whether `mlx-lm` is installed — gates the Insights tab UI |
| `/llm/job?id=`   | GET    | `{"status","result","error"}`  | Poll a background LLM job (`status`: `pending`\|`running`\|`done`\|`error`) |
| `/llm/digest?period=daily\|weekly` | GET | digest object or `{"status":"not_yet_generated"}` | Latest persisted daily/weekly narrative digest |
| `/llm/crash-explain` | POST | `{"ok":true,"job_id"}` or `{"ok":true,"cached":true,"explanation"}` | Explain a crash report: `{crash_key: "<file>.ips"}` — cached, so a repeat call for the same crash is instant |
| `/llm/digest/regenerate` | POST | `{"ok":true}` | Manually enqueue a fresh digest, bypassing the cooldown: `{period: "daily"\|"weekly"}` |
| `/llm/ask`       | POST   | `{"ok":true,"job_id"}`         | Ask a free-form question grounded in recent telemetry: `{question: str}` |

All `/llm/*` endpoints besides `/llm/status`/`/llm/job`/`/llm/digest` return
`{"ok":false,"error":"LLM not available"}` if `mlx-lm` isn't installed, rather than erroring.
See `app/llm_engine.py` and CLAUDE.md §5's "LLM Insights constants" for the underlying job
queue / model lifecycle.

### `/stats` JSON schema
```json
{
  "cpu_hist":             [float],   // last 90 CPU % readings
  "mem_hist":             [float],   // last 90 RAM % readings
  "swap_hist":            [float],   // last 90 Swap % readings
  "top_procs":            [[cpu, mem, pid, name, status]],
  "throttled":            {"pid": "name"},
  "events":               [{"kind", "msg", "ts", "category", "meta"}],  // "meta" optional, e.g. {"crash_key": "..."} on crash issue events
  "actions":              int,
  "issues":               int,
  "freed_mb":             float,     // MB reclaimed by actual process termination only
  "suspended_mb":         float,     // MB of SIGSTOP'd processes (not freed — RSS stays until SIGCONT)
  "crises_averted":       int,       // session count of RAC-confirmed rescues (tier ≥ 2, delta_pct ≥ 2 %)
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
  // ── v2.2 value-add metrics ─────────────────────────────────────────────────
  "value_add": {
    "total":                 int,    // interventions today
    "succeeded":             int,    // successful interventions today
    "success_rate":          float,  // today's success rate (0.0–1.0)
    "ram_saved_mb":          float,  // MB saved by successful interventions today
    "pct_below_87":          float,  // all-time % of metric rows where RAM < 87 % (containment proof)
    "alltime_interventions": int,    // total interventions in remediation_outcomes
    "alltime_success_rate":  float,  // all-time success rate
    "alltime_ram_saved_gb":  float,  // total GB saved across all successful interventions
    "alltime_best_save_mb":  float   // largest single-intervention RAM recovery
  },
  // ── v2.1 product metrics ───────────────────────────────────────────────────
  "performance_score":    int,       // 0–100 daily score; -1 = warming up (<10 min data)
                                     // formula: 100 − (0.5×avg_mem + 0.3×avg_cpu + 0.2×avg_swap) 24h
  "longterm_avg_mem":     float,     // 30-day average RAM %; >80% triggers upgrade recommendation
  "leak_pids_list":       [int],     // PIDs currently flagged as memory leaks
  // ── v2.3 NPA — Neural Performance Analyzer ────────────────────────────────
  "npa_trained":          bool,      // true once the MLP has completed at least one training run
  "npa_next_hour": {                 // NN predictions; empty {} until first training completes
    "mem":     float,                // Predicted RAM % over next 60 s (0–100)
    "cpu":     float,                // Predicted CPU % over next 60 s (0–100)
    "anomaly": float                 // Anomaly score 0–1; > 0.70 triggers a warning recommendation
  },
  "npa_recs": [                      // Up to 5 ranked recommendations; empty [] until trained
    {
      "priority":    int,            // 0=critical 1=warning 2=info 3=tip 4=all-clear
      "icon":        str,            // Emoji icon for the recommendation
      "title":       str,            // Short headline
      "detail":      str,            // Explanatory sentence
      "action":      str,            // Plain-English next step shown as "→ …" text
      "confidence":  float,          // Model confidence 0–1
      "pid":         int|null,       // Target process PID for actionable recs; null for informational
      "action_type": str|null        // "freeze"|"terminate"|"remediate"|"throttle"|null
                                     // Drives dashboard button: null = informational only
    }
  ],
  // ── v2.4 actionable recs + recent actions feed ─────────────────────────────
  "recent_actions": [                // Last 5 RAC-evaluated remediation outcomes (newest first)
    {
      "ts":       int,               // Unix timestamp of the action
      "tier":     int,               // Remediation tier (1–4)
      "action":   str,               // "freeze_daemon"|"sweep_xpc"|"purgeable_advisory"
      "pre_mem":  float,             // RAM % before action
      "post_mem": float,             // RAM % 120 s after action
      "delta_mb": float,             // MB freed (positive = improvement)
      "success":  bool               // delta_mb ≥ RAC_SUCCESS_PCT (2 %)
    }
  ]
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
| `~/Library/Application Support/performance-bot/llm_crash_explanations.json` | `{crash_key: {explanation, ts}}` — cached crash-report explanations (optional, `mlx-lm` only) |
| `~/Library/Application Support/performance-bot/llm_digests.json`       | `{"daily": {ts, text}, "weekly": {...}}` — latest narrative digests (optional, `mlx-lm` only) |

The cache records 1 row every 10 seconds → ~8 640 rows/day → ~35–45 MB at 90 days.
Rows older than `CACHE_RETENTION_DAYS` (90) are deleted automatically once per day.
To manually clear: `rm ~/Library/Application\ Support/performance-bot/metrics.db`
(the bot recreates the schema on next start).

The two `llm_*.json` files are small (a handful of cached strings) and atomically
written (temp file + `os.replace`) by `app/llm_engine.py`; they're only created once
`mlx-lm` is installed and a first crash-explain/digest job actually runs.

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
- Crash Report Monitor reads `~/Library/Logs/DiagnosticReports/*.ips` — the only place the bot reads files outside its own metrics/log directories. It parses only the first JSON line of each report (app name, timestamp, bug type); the full report (which can contain a stack trace and, rarely, user data referenced in it) is never opened or transmitted anywhere — the parsed summary only ever reaches the local Activity Log.

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
| SIGSTOP ≠ memory freed | SIGSTOP suspends a process but does NOT release its RSS. The dashboard tracks this separately: `freed_mb` = actual RAM reclaimed via termination; `suspended_mb` = RSS of SIGSTOP'd processes (held in suspension). Memory is only reclaimed when the process is SIGCONT'd and the OS reclaims its pages over time. |
| Menu bar requires `rumps` | `_start_menubar()` silently no-ops if `rumps` is not installed. Install with `pip install rumps`. On macOS 14+, the process may need `LSUIElement=1` in the plist to suppress a Dock icon. |
| `memory_pressure` sysctl | `kern.memorystatus_vm_pressure_level` may require SIP adjustments on some configurations. Falls back to percent-derived level automatically. |
| App Predictions cold start | The `_analyse_app_predictions()` panel is empty for the first 24 h. After the first full day the cache has enough data to show risk ratings. |
| Cache disk size | At 1 row/10 s for 90 days the database reaches ~35–45 MB — acceptable on all Macs. Reduce `CACHE_RETENTION_DAYS` only if storage is extremely limited. Prune was silently broken from initial release until 2026-07-21 (see Change Log 2.4.1) — a long-running install may still be working through a one-time backlog of rows older than 90 days as `prune()` catches up. |
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
| RAC evaluation delay | Each remediation action's outcome is evaluated `RAC_EVAL_DELAY_S` (120 s) later. The delay was raised from 30 s to 120 s because the OS needs time to reclaim pages after a SIGSTOP, so shorter windows produced false negatives. |
| NPA cold start | The "AI Insights" panel shows "Warming Up" until the first training run completes (requires ≥150 rows in the 30-day cache; typically fires on the very first 60-second tick given the existing 62K-row history). |
| NPA prediction horizon | Outputs represent the average of the *next 60 seconds*, not the next hour — the label "AI Insights" describes the trend direction. The recommendation text is worded to avoid implying 60-minute precision. |
| NPA training time | Fetching all 30-day rows (~62K) takes ~0.5 s; 600 samples × 40 epochs of pure-Python SGD takes ~2–3 s. Both run in the engine thread; no perceived dashboard lag because the engine sleeps 1 s/tick. |
| NPA distribution shift | If the machine undergoes a sustained change in workload type (e.g., new always-on process), predictions drift until the next 6-hour retrain incorporates recent data. |
| Crash Report Monitor scope | `_check_crash_reports()` only parses the first-line JSON header of `.ips` files (`app_name`, `timestamp`, `bug_type`) — it does not read the stack-trace body, and silently skips legacy plain-text `.crash` files (pre-macOS 12 format) if any are ever present. It also doesn't distinguish severity — every new report emits one `issue` event regardless of `bug_type`. |
| High-CPU warning cooldown | The per-process "High CPU" warning uses raw (unnormalized) CPU and a 60 s per-pid cooldown (`_cpu_warned_ts`) — a process pegging one core continuously logs one warning per minute, not one per second. The auto-throttle *action* threshold is unchanged and still requires system-wide CPU ≥ `CPU_WARN` as well as the process ≥ `CPU_THROTTLE` (normalized) — so a visible warning does not always mean the bot will act. |
| LLM Insights needs internet once | `mlx-lm` (optional) downloads its ~2GB model from Hugging Face on first use only — this is the one point where the feature needs a network connection. Every generation after that first download runs fully offline, on-device, with no network calls. Requires Apple Silicon. |
| LLM crash explanations are best-effort | The model reasons from the crashed thread's frame symbols only (no debug symbols/dSYMs are resolved) — explanations can be wrong or overly general for stripped/obfuscated binaries. It's a plain-English starting point, not a substitute for `Console.app`/`atos`. |

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
| 2026-07-25 | 2.6.0   | itsmeSugunakar | **Offline LLM Insights** — new `app/llm_engine.py` (optional, `mlx-lm`/Apple MLX, degrades cleanly if not installed, same pattern as the CDA engine's optional `onnx`/`onnxruntime`) powers a new "Insights" dashboard tab with three features: (1) **crash-report explanations** — click "Explain" on a crash Activity Log entry to get a plain-English explanation from the crashed thread's frames only (not the full multi-KB body); cached per crash so repeats are instant. (2) **daily/weekly narrative digests** — cooldown-gated in `BotEngine.run()` (`LLM_DAILY_DIGEST_COOL_S`/`LLM_WEEKLY_DIGEST_COOL_S`, mirrors the existing `CDA_TRAIN_COOL_S` pattern) but only *enqueues* a background job, never generates inline. (3) **Ask panel** — free-form questions grounded in recent hourly telemetry + today's digest + recent crash explanations. Model (`mlx-community/Qwen2.5-3B-Instruct-4bit`, ~2GB) loads lazily on first actual generation call and unloads after `LLM_IDLE_UNLOAD_S` (10 min) idle — this app's whole premise is not measurably degrading the system it monitors, so a resident multi-GB model between uses was a non-starter. All generation runs on a single serialized background worker thread; callers get a `job_id` and poll `GET /llm/job?id=`. **`HTTPServer` → `ThreadingHTTPServer`** — the single most load-bearing change here: without it, a slow (5-30s) LLM request would have frozen `/stats`/`/pause`/`/action`/`/remediate` for every connected client until it finished. `_emit()` gained an optional `meta` param so crash issue events can carry their `.ips` filename through to the Activity Log's new "Explain" button. New endpoints: `/llm/status`, `/llm/job`, `/llm/digest`, `/llm/crash-explain`, `/llm/digest/regenerate`, `/llm/ask`. No changes to `install.sh`/`scripts/install_gui.sh`'s automated bootstrap — `mlx-lm` stays fully optional/manual, same precedent as onnx. |
| 2026-07-21 | 2.5.0   | itsmeSugunakar | **Close the Activity Monitor gap** — user pointed out the bot's own GUI showed no sign of things visibly wrong in native Activity Monitor. Found and fixed two real gaps: (1) **single-core CPU spikes were invisible** — `top_procs` (`_collect()`) sorted memory-only, so a CPU-heavy/RAM-light process never made the top-12 table; the "High CPU" warning also required *system-wide* CPU ≥70% before firing, so a process pegging one core on this 8-core Mac (e.g. `yes`, reproduced live at 98.7% raw CPU) never crossed that bar since the system-wide average stayed low. Deeper bug once the system-wide gate was removed: the per-process CPU value (`c`) was normalized by `ncpu` for the warning comparison too — 98.7% raw showed as ~12.4% normalized, still under `CPU_WARN=70`. Fixed by introducing `raw_c` (unnormalized, matches `ps`/Activity Monitor's "100% = one core" convention) for `top_procs` display/sort and the warning threshold, while keeping the normalized `c` + system-wide gate for the auto-throttle *action* only (deliberately unchanged — auto-renicing a process doing legitimate one-core work while the Mac has headroom is a bigger call than just showing it). `top_procs` selection now unions top-9-by-memory with top-4-by-CPU so a spike is never hidden behind the memory sort. Added a 60s per-pid cooldown (`_cpu_warned_ts`) after finding the fix initially produced a "High CPU" line every second a process stayed elevated. (2) **Real crash/exception reports were a total gap** — the bot never read `~/Library/Logs/DiagnosticReports/` at all, despite that being exactly the kind of "error" Activity Monitor-adjacent tooling (Console.app) surfaces; found a live, real crash report (`lsd` exception fault) sitting there unsurfaced. New `_check_crash_reports()` (60s tick) reads only the lightweight first-line JSON header of each `.ips` file (never the full stack-trace body), emits an `issue` event via the existing `_emit()` pipeline — no new dashboard UI needed. Seeds the pre-existing backlog silently on first run so a restart doesn't dump historical crashes into the Activity Log. All three fixes verified live: `yes` pegging one core now appears in `top_procs` at ~99% and produces exactly one Activity Log warning (not a flood); crash backlog seeded with zero spam. |
| 2026-07-21 | 2.4.1   | itsmeSugunakar | **Fix: 90-day cache retention had silently never worked** — `[cache] prune failed: database table is locked` had fired on essentially every one of ~118 daily prune attempts logged to date; verified live that `metrics.db` had grown to 186,935 rows / 106.5 days, well past the documented `CACHE_RETENTION_DAYS=90` cap. Root cause (two parts, both confirmed by direct reproduction against the live DB): (1) `MetricsCache.__init__` never set `PRAGMA journal_mode=WAL` — DB sat in default rollback-journal mode, despite `prune()` already calling `PRAGMA wal_checkpoint(PASSIVE)` (a silent no-op outside WAL mode, the tell that WAL was the original intent); (2) `interventions_today()` (called from `BotEngine.snapshot()` on *every* `/stats` poll — the dashboard polls once/second) ran two unindexed full-table scans, holding a read lock that starved the once-daily `prune()` writer as the table grew — a self-reinforcing loop. **The actual proximate trigger, found only after WAL mode alone didn't fully fix it**: `prune()` called `PRAGMA wal_checkpoint(PASSIVE)` immediately after `DELETE`, in the same uncommitted transaction — reproduced directly that this combination reliably raises `database table is locked` even though the DELETE and the checkpoint each succeed independently. Fix: enabled WAL (`__init__`), added an explicit `cx.commit()` between the DELETE and the checkpoint in `prune()`, bumped `prune()`'s connection timeout 5s→15s as a safety margin, and added a ~20s result cache to `interventions_today()` so its two full scans don't re-run on every 1Hz poll. Verified fix by calling the live `MetricsCache.prune()` directly against the running bot's real database, 5 consecutive times under real concurrent load, zero exceptions (previously reproduced the failure the same way before the fix). |
| 2026-04-04 | 1.0.0   | itsmeSugunakar | Initial release: headless bot + web GUI                                |
| 2026-04-05 | 1.1.0   | itsmeSugunakar | MMIE engine: kernel pressure oracle, vm_stat breakdown, memory genealogy, linear-regression forecast, 4-tier remediation cascade, SIGSTOP/SIGCONT freeze-thaw; PWA dashboard redesign with ring gauges, Memory Intelligence panel, metric strip, `/manifest.json` |
| 2026-04-05 | 1.2.0   | itsmeSugunakar | Predictive Remediation Engine (`_compute_effective_tier`); CPU-RAM Conflict Resolution Gate; genealogy-guided SIGSTOP scoring (`family×2 + pattern×1`); XPC Respawn Guard (`_detect_xpc_respawn`, `_no_kill`); dashboard: Active Tier, CPU-RAM Lock, XPC Blocked, predictive escalation banner; PPA document added |
| 2026-04-05 | 1.3.0   | itsmeSugunakar | 90-day SQLite disk cache (`MetricsCache`): batch writes every 60 s, daily prune, aggregate-only reads; `_analyse_app_predictions()` for app-level risk classification; `app_mem_trend()` and `chronic_pressure_pct()` queries; dashboard App Predictions panel + Cache (90d) vmrow; `/stats` extended with `effective_tier`, `predictive_escalation`, `cpu_ram_lock`, `xpc_blocked`, `cache_db_mb`, `cache_rows`, `app_predictions` |
| 2026-04-05 | 1.4.0   | itsmeSugunakar | Lightweight engine: merged `_check_cpu` throttle-detection into `_collect` (single `process_iter` per second); `_check_cpu` → `_restore_calmed_procs` (no process scan); `psutil.cpu_count` cached as `self._ncpu`; `virtual_memory`/`swap_memory` fetched once per tick, shared via `_last_vm`/`_last_swap`; `disk_usage` moved to `_check_disk` (10 s), cached in `disk_pct`/`disk_free_gb`; handler no longer calls `disk_usage` per request; `events` list → `deque(maxlen=200)` (O(1)); cache record rate 1/s → 1/10 s; `_detect_xpc_respawn` 10 s → 30 s |
| 2026-04-10 | 1.5.0   | itsmeSugunakar | 8 patent-level engine innovations: **MMAF** — 3-model adaptive forecaster (linear/quadratic/exponential, best-RSS selection); **CEO** — Compression Efficiency Oracle (CPI signal); **MSCEE** — 6-signal weighted quorum replaces 2-signal `max()` (signals: RAM %, TTE, kernel oracle, CPI, swap velocity, circadian); **GTS** — Graduated Thaw Sequencing (RSS-ascending SIGCONT, 2 s gap, RAM gate); **RVMS** — RSS Velocity Momentum Scorer (1×–2× freeze boost); **ATCE** — Adaptive Threshold Calibration Engine (hourly self-tuning from 30-day cache percentiles); **CMPE** — Circadian Memory Pattern Engine (hour-of-day SQL profile, proactive pre-freeze); **TMCP** — Thermal-Memory Coupling Predictor (EMA-learned TTE shortening under thermal throttle); `MetricsCache` schema extended with `thermal_pct` column (auto-migrates); 4 new dashboard vmrows (Forecast Model, CPI, Swap Velocity, Thermal Coupling); `/stats` extended with 6 new fields |
| 2026-04-18 | 2.1.0   | itsmeSugunakar | **Product UX Layer** — 10 user-outcome improvements on top of the v2.0 engine: **Performance Score** (0–100 daily, `daily_performance_score()` from 24h SQLite); **Memory Paused** (accurate label for SIGSTOP — was "RAM Freed"); **Tier labels** renamed to user language (All Good / Watching / Intervening / Rescue Mode / Emergency); **Root Cause Banner** (plain-English, prominent, hidden when normal); **Simple/Expert mode** toggle (10 engine-telemetry rows hidden by default, `localStorage` persisted); **Activity Log filter** (`category="bot"` on calibration `_emit()` calls, "Bot Logs" toggle in titlebar); **7-Day History tab** (`hourly_history()` MetricsCache method, `/history` HTTP endpoint, Chart.js multi-line chart); **RAM Recommendation** (`longterm_avg_mem()` 30d query, advisory card when avg > 80%); **Leak hints** in process table (LEAK badge + 💡 Restart? for leak-flagged processes); **macOS Menu Bar** (`_start_menubar()` via `rumps`, daemon thread, optional); LaunchAgent path updated to `~/Documents/performance-bot/` |
| 2026-04-26 | 2.2.0   | itsmeSugunakar | **Value-Add Metrics + Reliability Fixes** — **Achievement banner** replaces Actions/Issues cards in metric strip (Crises Averted / Total RAM Saved / Time Below 87% / Biggest Save); **`interventions_today()`** MetricsCache method aggregates today's and all-time remediation_outcomes; **`crises_averted`** session counter (RAC-confirmed rescues at tier ≥ 2); **`suspended_mb`** split from `freed_mb` — SIGSTOP RSS tracked separately from actual termination reclamation; **`RAC_EVAL_DELAY_S` 30 s → 120 s** to give OS time to reclaim pages post-SIGSTOP; **CEO collapse response** — CPI ≥ 0.75 AND RAM ≥ 80 % now triggers proactive daemon freeze; **`longterm_avg_mem`** pre-loaded from DB at startup (was 0.0 until first hourly update); **LaunchAgent `KeepAlive: true` + `ThrottleInterval: 30`** — bot now survives crashes/kills without 5-day gaps; **JS null-guard on `set()` helper** + **duplicate `const contain` SyntaxError fixed** (caused "no metrics showing" on dashboard); `/stats` extended with `suspended_mb`, `crises_averted`, `value_add` |
| 2026-05-29 | 2.4.0   | itsmeSugunakar | **Actionable AI Recommendations + Remediation Integration** — bridged NPA recommendations to the remediation cascade: every rec dict now carries `pid` (target process) and `action_type` (`"freeze"` / `"remediate"` / `"throttle"` / `None`); dashboard buttons fire `POST /action` or new `POST /remediate {tier}` endpoint; `BotEngine.trigger_remediation(tier)` is the user-initiated entry point bypassing threshold gates; `throttle` action added to `/action` handler (`nice(10)`); **TTE velocity recommendations** — two new NPA rec types fire when memory is growing fast: `⏱ Memory filling fast — ~N min` (warning, TTE < 15 min) and `⏳ Steady memory growth — ~N min runway` (info, TTE 15–30 min); CPU rec now names the specific throttled process from `self.throttled`; `_run_npa()` injects `tte_min`, `throttled_names`, `throttled_pids` into `bot_state`; **Recent Bot Actions feed** — `MetricsCache.recent_outcomes(n)` queries `remediation_outcomes` table; `recent_actions` added to `/stats` JSON; Summary AI panel shows last 5 outcomes (✅/❌, action label, MB freed, timestamp) in a "Recent Actions" section below recommendations; **confidence % now shown in Summary tab** recommendation cards (was Live-tab only); CSS `.npa-btn`, `.sum-actions-hdr`, `.sum-action-row` added |
| 2026-05-04 | 2.3.0   | itsmeSugunakar | **Neural Performance Analyzer (NPA)** — pure-Python 3-layer MLP (11→12→6→3, no external deps) trained every 6 h on a stratified stride-sample of the full 30-day SQLite cache; predicts next-60s RAM and CPU; anomaly score flags unusual hour-of-day patterns; `generate_recommendations()` produces up to 5 prioritised plain-English cards (critical / warning / info / tip / all-clear) shown in a new "AI Insights" panel on the dashboard; `MetricsCache.fetch_training_data()` fetches all 30-day rows and strides to ≤600 representative samples (fixes prior bug where only the oldest 11-minute burst was used); gradient uses post-clip output `out − target` (bounded [-1,1], prevents explosion); pre-update weight snapshots fix backprop correctness; LR reduced 0.008 → 0.002; `/stats` extended with `npa_trained`, `npa_next_hour`, `npa_recs` |
| 2026-04-12 | 2.0.0   | itsmeSugunakar | **Autonomous Dynamic Resource Management Agent** — 11 new cognitive engines across a 5-layer governed control model: **SIE** — Signal Integrity Estimator (z-score anomaly confidence per signal); **MEG** — Model Ensemble Governance (meta-weight historical residuals over MMAF models); **ACN** — Adaptive Consensus Network (RWA-driven adaptive weights replace static MSCEE weights); **RWA** — Reinforcement-Weighted Arbitration (hourly EMA weight update from `remediation_outcomes` table); **CTRE** — Chronothermal Regression Engine (per-hour variance stability from 30-day cache); **AIP** — Ancestral Impact Propagation (family-tree RSS depth scoring + cascade risk detection); **RAC** — Reinforcement Action Coordinator (records and evaluates remediation outcomes via new SQLite table); **PSM** — Predictive State Machine (Markov next-tier prediction + dwell estimation); **BRL** — Bayesian Reasoning Layer (Beta prior tier-frequency + likelihood posterior confidence); **ASZM** — Adaptive Safety Zone Mapping (criticality scoring → dynamic `_dynamic_protected` set); **CDA** — Causal Diagnostic Agent (pure-Python softmax LR + optional ONNX export: normal \| leak \| compressor_collapse \| cpu_collision); new SQLite tables `remediation_outcomes` + `signal_weights` (auto-migrates existing DB); 8 new dashboard vmrows (Root Cause, BRL Confidence, ACN Weights, Signal Integrity, PSM Next Tier, CTRE Zone, Action Efficacy, ASZM Protected+); `/stats` extended with 10 new fields |

---

*This file is the single source of truth for the MAC Performance Bot application.
Update it whenever architecture, thresholds, or deployment procedures change.*
