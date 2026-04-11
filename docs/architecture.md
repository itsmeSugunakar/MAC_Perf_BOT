# Architecture — MAC Performance Bot

## Design Diagram (Mermaid)

```mermaid
flowchart TD
  LA[LaunchAgent\nlogin autostart] --> GUI[performance_gui.py]

  subgraph APP[performance_gui.py Runtime]
    BE[BotEngine\n1 second tick]
    HTTP[HTTP Handler\n127.0.0.1:8765]
    DB[(SQLite Metrics Cache\n90 days)]

    BE -->|snapshot()| HTTP
    BE -->|cache.record + flush| DB
    DB -->|aggregates| BE
  end

  subgraph OS[macOS Signals and Metrics]
    PS[psutil.process_iter]
    SYS[sysctl kern.memorystatus]
    VM[vm_stat]
    PM[pmset thermal and power]
  end

  PS --> BE
  SYS --> BE
  VM --> BE
  PM --> BE

  subgraph ENGINES[Inference and Remediation Engines]
    MMAF[MMAF\n3-model adaptive forecaster\nlinear + quadratic + exponential]
    CEO[CEO\nCompression Efficiency Oracle\nCPI signal]
    MSCEE[MSCEE\n6-signal weighted quorum\neffective tier 0 to 4]
    ATCE[ATCE\nAdaptive Threshold Calibration\nhourly self-tuning]
    CMPE[CMPE\nCircadian Pattern Engine\nhour-of-day pre-freeze]
    TMCP[TMCP\nThermal-Memory Coupling\nEMA-learned TTE adjustment]
    RVMS[RVMS\nRSS Velocity Scorer\nfreeze boost 1x to 2x]
    GTS[GTS\nGraduated Thaw Sequencer\nRSS-ascending SIGCONT]
    XG[XPC Respawn Guard\nno-kill blocklist]
  end

  BE --> MMAF
  BE --> CEO
  MMAF --> MSCEE
  CEO --> MSCEE
  ATCE --> MSCEE
  CMPE --> MSCEE
  TMCP --> MMAF
  MSCEE -->|tier 3| RVMS
  RVMS --> GTS
  MSCEE --> XG
  DB -->|30-day percentiles| ATCE
  DB -->|hour-of-day avgs| CMPE
  DB -->|throttled rows| TMCP

  BR[Browser PWA\nChart.js dashboard] -->|GET / and GET /stats| HTTP
  HTTP -->|JSON metrics| BR
```

## Data Flow

```
macOS kernel  (sysctl, vm_stat, pmset)
      │
      ▼  psutil + subprocess
BotEngine (background thread, 1 Hz)
      │
      ├── cpu_hist[], mem_hist[], swap_hist[]   ← in-RAM ring buffer (90 s)
      ├── top_procs[]                           ← sorted by CPU, top-12
      ├── throttled{}                           ← pid → name map
      ├── events[]                              ← deque(maxlen=200), O(1)
      │
      ├── MMIE / Engine state
      │   ├── mem_pressure_level                ← kernel sysctl oracle
      │   ├── vm_breakdown{}                    ← vm_stat anatomy
      │   ├── mem_forecast_min                  ← MMAF TTE (minutes)
      │   ├── _last_forecast_model              ← "linear"|"quadratic"|"exponential"
      │   ├── _compression_pressure             ← CEO CPI (0.0–1.0)
      │   ├── _swap_velocity                    ← MB/s swap growth rate
      │   ├── _thermal_coupling                 ← TMCP EMA coefficient
      │   ├── _circadian_profile{}              ← CMPE hour→avg RAM %
      │   ├── _cal_thresholds{}                 ← ATCE live tier thresholds
      │   ├── mem_ancestry[]                    ← ppid-tree RSS families
      │   ├── effective_tier                    ← MSCEE output (0–4)
      │   ├── predictive_escalation             ← TTE drove tier up
      │   ├── _ram_pressure_lock                ← CPU-RAM conflict gate
      │   ├── _frozen_pids{}                    ← SIGSTOP'd daemons
      │   └── _no_kill                          ← XPC respawn blocklist
      │
      └── MetricsCache (disk)
          └── ~/Library/Application Support/performance-bot/metrics.db
              ← 90-day SQLite store, flushed every 60 s
              ← pruned daily (DELETE WHERE ts < now - 90 days)
               │
               ├── app_mem_trend()              → week-over-week RAM trends
               ├── chronic_pressure_pct()       → % time above MEM_WARN
               ├── _analyse_app_predictions()   → risk ratings per app
               ├── _calibrate_thresholds()      → ATCE percentile query (30d)
               ├── _build_circadian_profile()   → CMPE GROUP BY hour (all rows)
               └── _compute_thermal_coupling()  → TMCP regression (throttled rows)
                    │
                    ▼ snapshot() called by HTTP handler
      HTTP Handler (main thread)
            │
            ├── GET /             → HTML page (embedded, ~30 KB)
            ├── GET /stats        → JSON snapshot (< 10 KB)
            ├── GET /manifest.json → PWA manifest
            ├── GET /icon.svg     → PWA icon
            └── GET /pause?state= → toggle engine.running
                  │
                  ▼  polling every 1 s via setInterval
      Browser (Chart.js PWA)
            ├── Metric strip      — ring gauges: CPU / MEM / Swap / Disk
            ├── Memory Intelligence panel — arc gauge, vm_stat breakdown,
            │   Active Tier row, predictive escalation banner, CPU-RAM Lock,
            │   XPC Blocked, Cache (90d) size, Forecast Model, CPI,
            │   Swap Velocity, Thermal Coupling, App Predictions panel
            ├── CPU / Swap sparklines (90 s canvas charts)
            ├── Bot Status cards  — Throttled / Actions / Issues / RAM Freed
            ├── Activity log      — FIX / WARN / ISSUE / INFO events
            └── Process table     — top-12 with CPU/MEM bars + memory trend
```

---

## Thread Model

```
Main thread      → HTTPServer.serve_forever()
bot-engine       → BotEngine.run()  (daemon=True)
timer thread     → webbrowser.open() after 0.8 s  (one-shot)
```

All shared state is protected by `BotEngine._lock` (threading.Lock).
The HTTP handler reads only via `snapshot()` — never writes — so lock contention
is minimal and brief.
`MetricsCache` runs all SQLite I/O on the `bot-engine` thread — no additional threads.

### Cached values (avoid repeated syscalls)

| Field                            | Set by                 | Read by                             | Syscall saved                |
| -------------------------------- | ---------------------- | ----------------------------------- | ---------------------------- |
| `self._ncpu`                     | `__init__` (once)      | `_collect`, `_restore_calmed_procs` | `cpu_count()` per tick       |
| `self._last_vm`                  | `_collect` (1 Hz)      | `_check_memory` (0.33 Hz)           | `virtual_memory()` every 3 s |
| `self._last_swap`                | `_collect` (1 Hz)      | `_check_memory` (0.33 Hz)           | `swap_memory()` every 3 s    |
| `self.disk_pct` / `disk_free_gb` | `_check_disk` (0.1 Hz) | `snapshot()` / HTTP handler         | `disk_usage()` per request   |
| `self._last_disk_pct`            | `_check_disk` (0.1 Hz) | `_collect` cache record             | `disk_usage()` per second    |
| `self._last_forecast_model`      | `_compute_mem_forecast()` (0.2 Hz) | `snapshot()`            | recomputation every tick     |
| `self._compression_pressure`     | `_update_pressure_and_forecast()` (0.2 Hz) | `snapshot()`, MSCEE | CEO per 5 s only        |
| `self._thermal_coupling`         | `_compute_thermal_coupling()` (hourly) | `_adjust_tte_for_thermal()` | DB regression once/h |

---

## Engine Tick Schedule

```
Every 1 s   → _collect()
               ONE psutil.process_iter() scan — collects metrics AND detects
               CPU hogs inline using p.info[] (cached attrs, no extra syscalls).
               Stores _last_vm / _last_swap for downstream methods.
               Computes _swap_velocity (MB/s) from delta vs _last_swap_used.
               Records 1 cache row every 10 s (time % 10 gate, no disk I/O otherwise).
               Cache row includes thermal_pct column (9-column INSERT).

               _restore_calmed_procs() — restores nice(0) only for processes in
               self.throttled (typically 0–3 items); no process scan.

Every 3 s   → _check_memory()
               Reads _last_vm (no syscall). Calls _compute_effective_tier()
               via MSCEE 6-signal quorum, then _tiered_memory_remediation().

Every 5 s   → _update_pressure_and_forecast()
               Spawns sysctl + vm_stat subprocesses. Updates mem_pressure_level,
               vm_breakdown, mem_ancestry.
               Calls _compute_mem_forecast() [MMAF: 3-model ensemble, best-RSS winner].
               Calls _compute_compression_pressure() [CEO: CPI = compressed/(compressed+purgeable)].
               Calls _adjust_tte_for_thermal() [TMCP: shorten TTE under thermal throttle].

Every 10 s  → _check_disk()
               Single psutil.disk_usage("/") call; stores disk_pct / disk_free_gb
               for snapshot(). No per-request disk reads in Handler.

Every 30 s  → _check_power_mode()   (pmset -g ps subprocess)
Every 30 s  → _detect_xpc_respawn() (process name set scan)
Every 30 s  → _sweep_idle_services() (IDLE_SWEEP_S default)

Every 60 s  → cache.flush()          executemany() — 6 rows (1 per 10 s × 60 s)
Every 60 s  → cache.prune()          DELETE WHERE ts < cutoff (no-op if < 24 h since last)
Every 60 s  → _check_thermal()       (pmset -g therm subprocess)
Every 60 s  → _check_zombies()
Every 60 s  → _track_memory_leaks()
Every 60 s  → _check_circadian_pressure()   [CMPE: hour-of-day profile refresh + pre-freeze]

Every 300 s → _check_caches()        ~/Library/Caches du scan
Every 3600 s→ _analyse_app_predictions()    guarded by 86400 s internal cooldown
Every 3600 s→ _calibrate_thresholds()       [ATCE: recalibrate Tier 2/3/4 from 30-day cache]
Every 3600 s→ _compute_thermal_coupling()   [TMCP: update EMA coefficient from throttled rows]
```

---

## Remediation Logic

```
_collect() — every second (replaces separate _check_cpu scan):
  sys_cpu = psutil.cpu_percent()          ← one call
  vm      = psutil.virtual_memory()       ← one call, stored as _last_vm
  swap    = psutil.swap_memory()          ← one call, stored as _last_swap
  _swap_velocity computed from delta swap.used vs _last_swap_used / elapsed

  for p in psutil.process_iter(attrs):    ← ONE scan total
      c = p.info["cpu_percent"] / _ncpu   ← cached attr, no extra syscall
      rows.append(...)                    ← build top_procs
      if sys_cpu >= CPU_WARN and c >= CPU_THROTTLE:
          to_throttle.append(p)           ← defer; apply after loop
      elif sys_cpu >= CPU_WARN and c >= CPU_WARN:
          emit WARN

  _restore_calmed_procs(ram_lock)         ← iterates self.throttled only (0–3 items)
  for p in to_throttle: p.nice(RENICE_VAL)

_restore_calmed_procs() — called from _collect(), no process scan:
  for each pid in self.throttled (typically 0–3):
    c = psutil.Process(pid).cpu_percent() / _ncpu
    if c < CPU_WARN/2 (35 %):
      if _ram_pressure_lock AND proc is top-3 RAM family:
        → defer nice(0) [CPU-RAM conflict resolution]
      else:
        → nice(0), emit FIX
  (throttle detection handled inline in _collect loop above)
```

\_check_memory() — every 3 s:

\_compute_effective_tier(mem_pct)  **[MSCEE — Multi-Signal Consensus Escalation Engine]**:
```
Six weighted signals:
  S1 = RAM %            weight 0.30 → vote for threshold_tier
  S2 = TTE              weight 0.25 → vote for predictive_tier (MMAF output)
  S3 = kernel oracle    weight 0.20 → vote for pressure_tier (normal/warn/critical)
  S4 = CPI              weight 0.12 → vote for cpi_tier (CEO output)
  S5 = swap velocity    weight 0.08 → vote for swap_tier
  S6 = circadian hour   weight 0.05 → vote based on CMPE profile

For candidate_tier in [4, 3, 2, 1]:
  weighted_vote = sum(signal_weight for each signal voting ≥ candidate_tier)
  if weighted_vote >= MSCEE_QUORUM (0.55):
    effective_tier = candidate_tier; break
else:
  effective_tier = 0

_ram_pressure_lock = (effective_tier >= 3)
```

if effective_tier >= 1: emit ISSUE + consumer report
if predictive escalation: emit PREDICTIVE ESCALATION event
if effective_tier >= 2: \_tiered_memory_remediation(mem_pct, effective_tier)
if mem_pct < MEM_WARN-5: release lock + \_thaw_frozen_daemons() [GTS]

\_tiered_memory_remediation(mem_pct, effective_tier):
```
Tier 2 (eff ≥ 2): vm_stat parse → purgeable advisory → wired warning → genealogy report
                   CEO CPI advisory if CPI ≥ CPI_TIER2

Tier 3 (eff ≥ 3): _freeze_background_daemons() — RVMS-enhanced scoring:
  vboost = _get_process_velocity(pid, rss_mb)   ← RVMS boost [1.0, 2.0]
  score  = (family_match×2 + pattern_match×1) × vboost
  sort by (score DESC) → SIGSTOP

Tier 4 (eff ≥ 4): _sweep_idle_services() — respects _no_kill blocklist → SIGTERM
```

\_thaw_frozen_daemons() **[GTS — Graduated Thaw Sequencer]**:
```
baseline_mem = current RAM %
sorted ascending by rss_mb (smallest first)
for each (pid, name, rss_mb) in sorted(_frozen_pids):
  if current_mem - baseline_mem > GTS_MEM_GATE_PCT (5 %):
    abort thaw — RAM rising too fast
  SIGCONT → remove from _frozen_pids → emit FIX
  time.sleep(GTS_WAIT_S)   ← 2 s gap between sends
```

\_get_process_velocity(pid, rss_mb) **[RVMS — RSS Velocity Momentum Scorer]**:
```
delta_mb = rss_mb - _rss_velocity[pid].last_mb
elapsed  = now - _rss_velocity[pid].ts
rate     = delta_mb / elapsed   (MB/s)
boost    = min(1.0 + rate / 10.0, RVMS_MAX_BOOST)   ← capped at 2.0×
```

\_compute_mem_forecast() **[MMAF — Multi-Model Adaptive Forecaster]**:
```
window = min(MMAF_WINDOW, len(mem_hist)) samples
Fit 3 models on (x=index, y=mem_pct):
  linear      : OLS slope/intercept
  quadratic   : Vandermonde normal equations, Cramer's rule (pure Python)
  exponential : log-linearised OLS (only when all y > 0)
Select winner by minimum residual sum of squares.
Extrapolate winner to MMAF_TARGET_PCT (95 %) → TTE in minutes.
Store _last_forecast_model = "linear" | "quadratic" | "exponential".
```

\_compute_compression_pressure(vm_bd) **[CEO — Compression Efficiency Oracle]**:
```
CPI = compressed / (compressed + purgeable)
if CEO_MIN_COMPRESSED not met: return 0.0
if CPI >= CPI_TIER3 (0.75): emit WARN "compressor exhaustion"
if CPI >= CPI_TIER2 (0.50): emit ISSUE "efficiency degrading"
Store in _compression_pressure → fed as S4 signal into MSCEE.
```

\_adjust_tte_for_thermal(tte) **[TMCP — Thermal-Memory Coupling Predictor]**:
```
throttle_fraction = (100 - thermal_pct) / 100.0
adjustment = max(1.0 - _thermal_coupling × throttle_fraction, 0.5)
return tte × adjustment       ← TTE shortened by up to 50 % under full throttle
```

\_calibrate_thresholds() **[ATCE — Adaptive Threshold Calibration Engine]**:
```
Requires ATCE_MIN_ROWS (1000) cache rows and ATCE_COOL_S (3600 s) cooldown.
SELECT mem_pct ORDER BY mem_pct from last 30 days.
MEM_TIER2_PCT ← 75th percentile
MEM_TIER3_PCT ← 85th percentile
MEM_TIER4_PCT ← 93rd percentile
Store in _cal_thresholds{tier2, tier3, tier4}.
```

\_check_circadian_pressure() **[CMPE — Circadian Memory Pattern Engine]**:
```
Requires CMPE_COOL_S (3600 s) cooldown.
SELECT ts/3600 % 24, AVG(mem_pct) GROUP BY hour → _circadian_profile
current_hour_avg = _circadian_profile.get(current_hour, 0)
if current_hour_avg >= CMPE_PRE_FREEZE_SCORE (70 %) AND mem_pct >= MEM_WARN:
  → proactive _freeze_background_daemons() pre-emptively
```

\_compute_thermal_coupling() **[TMCP — EMA coefficient update]**:
```
Requires TMCP_MIN_SAMPLES (5) throttled-state cache rows.
SELECT thermal_pct, mem_pct WHERE thermal_pct < 100 (last 30 days).
Compute OLS covariance / variance → coupling_raw (normalised to [0,1]).
_thermal_coupling = (1-TMCP_LEARN_RATE) × _thermal_coupling
                    + TMCP_LEARN_RATE × coupling_raw   ← EMA update
```

\_detect_xpc_respawn() — every 30 s:
```
if terminated_name reappears within XPC_RESPAWN_S (10 s):
  → _no_kill.add(name), emit XPC RESPAWN GUARD warning
```

---

## Disk Cache Design

```
Location : ~/Library/Application Support/performance-bot/metrics.db
Schema   : metrics(ts INTEGER, cpu_pct REAL, mem_pct REAL, swap_pct REAL,
                    disk_pct REAL, pressure TEXT, eff_tier INTEGER,
                    tte_min REAL, thermal_pct INTEGER DEFAULT 100)
Index    : idx_metrics_ts ON metrics(ts)
Migration: ALTER TABLE metrics ADD COLUMN thermal_pct INTEGER DEFAULT 100
           (wrapped in try/except OperationalError — safe on existing DBs)

Write    : cache.record() appends to a Python list (no I/O, ≤ 4 KB RAM)
           cache.flush() executemany() every 60 s — one batch write per minute
Read     : aggregate-only queries (AVG / COUNT / GROUP BY) — ≤ 10 rows returned
Prune    : DELETE WHERE ts < now − 90 days, once per day + WAL checkpoint
Capacity : ~90 days × 8640 rows/day ≈ 777 K rows ≈ 35–45 MB max on disk
           (1 row per 10 s, not per second — 10× reduction from v1.3.0)

Analysis methods (all run aggregate SQL — zero raw rows loaded into Python):
  app_mem_trend(app, 30d)        → {avg_mem_pct, week1_avg, week2_avg, trend}
  chronic_pressure_pct(7d)       → float: % of time RAM above MEM_WARN
  _analyse_app_predictions()     → [{app, mb, pct, trend, risk, chronic_pct}]
                                    runs every 24 h; emits APP PREDICTION events
  _calibrate_thresholds()        → ATCE: 75th/85th/93rd percentile of mem_pct (30d)
  _build_circadian_profile()     → CMPE: AVG(mem_pct) GROUP BY ts/3600 % 24
  _compute_thermal_coupling()    → TMCP: OLS regression on throttled-state rows
```

---

## Security Constraints

- Loopback-only HTTP server (`127.0.0.1:8765`) — no network exposure.
- All process signals (`SIGSTOP`, `SIGCONT`, `SIGTERM`) target user-owned processes only.
- `PROTECTED` set blocks touching kernel, window server, and the bot itself.
- `_no_kill` blocklist prevents looping SIGTERM on launchd-managed services.
- Disk cache contains only aggregate metric numbers — no process names, no user data.
- No credentials, tokens, or secrets anywhere in code, config, or cache.
