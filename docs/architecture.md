# Architecture — MAC Performance Bot

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
      ├── events[]                              ← ring buffer (200 entries)
      │
      ├── MMIE state
      │   ├── mem_pressure_level                ← kernel sysctl oracle
      │   ├── vm_breakdown{}                    ← vm_stat anatomy
      │   ├── mem_forecast_min                  ← OLS TTE (minutes)
      │   ├── mem_ancestry[]                    ← ppid-tree RSS families
      │   ├── effective_tier                    ← PRE output (0–4)
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
               ├── app_mem_trend()        → week-over-week RAM trends
               ├── chronic_pressure_pct() → % time above MEM_WARN
               └── _analyse_app_predictions() → risk ratings per app
                    │
                    ▼ snapshot() called by HTTP handler
      HTTP Handler (main thread)
            │
            ├── GET /             → HTML page (embedded, ~25 KB)
            ├── GET /stats        → JSON snapshot (< 8 KB)
            ├── GET /manifest.json → PWA manifest
            ├── GET /icon.svg     → PWA icon
            └── GET /pause?state= → toggle engine.running
                  │
                  ▼  polling every 1 s via setInterval
      Browser (Chart.js PWA)
            ├── Metric strip      — ring gauges: CPU / MEM / Swap / Disk
            ├── Memory Intelligence panel — arc gauge, vm_stat breakdown,
            │   Active Tier row, predictive escalation banner, CPU-RAM Lock,
            │   XPC Blocked, Cache (90d) size, App Predictions panel
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

| Field | Set by | Read by | Syscall saved |
|---|---|---|---|
| `self._ncpu` | `__init__` (once) | `_collect`, `_restore_calmed_procs` | `cpu_count()` per tick |
| `self._last_vm` | `_collect` (1 Hz) | `_check_memory` (0.33 Hz) | `virtual_memory()` every 3 s |
| `self._last_swap` | `_collect` (1 Hz) | `_check_memory` (0.33 Hz) | `swap_memory()` every 3 s |
| `self.disk_pct` / `disk_free_gb` | `_check_disk` (0.1 Hz) | `snapshot()` / HTTP handler | `disk_usage()` per request |
| `self._last_disk_pct` | `_check_disk` (0.1 Hz) | `_collect` cache record | `disk_usage()` per second |

---

## Engine Tick Schedule

```
Every 1 s   → _collect()
               ONE psutil.process_iter() scan — collects metrics AND detects
               CPU hogs inline using p.info[] (cached attrs, no extra syscalls).
               Stores _last_vm / _last_swap for downstream methods.
               Records 1 cache row every 10 s (time % 10 gate, no disk I/O otherwise).

               _restore_calmed_procs() — restores nice(0) only for processes in
               self.throttled (typically 0–3 items); no process scan.

Every 3 s   → _check_memory()
               Reads _last_vm (no syscall). Calls _compute_effective_tier()
               (arithmetic + lock read), then _tiered_memory_remediation().

Every 5 s   → _update_pressure_and_forecast()
               Spawns sysctl + vm_stat subprocesses. Updates mem_pressure_level,
               vm_breakdown, mem_forecast_min, mem_ancestry.

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

Every 300 s → _check_caches()        ~/Library/Caches du scan
Every 3600 s→ _analyse_app_predictions()  guarded by 86400 s internal cooldown
```

---

## Remediation Logic

```
_collect() — every second (replaces separate _check_cpu scan):
  sys_cpu = psutil.cpu_percent()          ← one call
  vm      = psutil.virtual_memory()       ← one call, stored as _last_vm
  swap    = psutil.swap_memory()          ← one call, stored as _last_swap

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

_check_memory() — every 3 s:
  _compute_effective_tier(mem_pct):
    threshold_tier  ← static % lookup (0–4)
    if TTE ≤ TTE_TIER4_MIN (2 min)  → predictive_tier = 4
    elif TTE ≤ TTE_TIER3_MIN (5 min) → predictive_tier = 3
    elif TTE ≤ TTE_TIER2_MIN (10 min) → predictive_tier = 2
    effective_tier = max(threshold_tier, predictive_tier)
    _ram_pressure_lock = (effective_tier >= 3)

  if effective_tier >= 1:   emit ISSUE + consumer report
  if was predictive:        emit PREDICTIVE ESCALATION event
  if effective_tier >= 2:   _tiered_memory_remediation(mem_pct, effective_tier)
  if mem_pct < MEM_WARN-5:  release lock + _thaw_frozen_daemons()

_tiered_memory_remediation(mem_pct, effective_tier):
  Tier 2 (eff ≥ 2): vm_stat parse → purgeable advisory → wired warning → genealogy report
  Tier 3 (eff ≥ 3): _freeze_background_daemons() — genealogy-guided scoring:
                       score = family_match×2 + pattern_match×1
                       sort by (score DESC, rss DESC) → SIGSTOP
  Tier 4 (eff ≥ 4): _sweep_idle_services() — respects _no_kill blocklist → SIGTERM

_detect_xpc_respawn() — every 10 s:
  if terminated_name reappears within XPC_RESPAWN_S (10 s):
    → _no_kill.add(name), emit XPC RESPAWN GUARD warning
```

---

## Disk Cache Design

```
Location : ~/Library/Application Support/performance-bot/metrics.db
Schema   : metrics(ts INTEGER, cpu_pct REAL, mem_pct REAL, swap_pct REAL,
                   disk_pct REAL, pressure TEXT, eff_tier INTEGER, tte_min REAL)
Index    : idx_metrics_ts ON metrics(ts)

Write    : cache.record() appends to a Python list (no I/O, ≤ 4 KB RAM)
           cache.flush()  executemany() every 60 s — one batch write per minute
Read     : aggregate-only queries (AVG / COUNT / GROUP BY) — ≤ 10 rows returned
Prune    : DELETE WHERE ts < now − 90 days, once per day + WAL checkpoint
Capacity : ~90 days × 8640 rows/day ≈ 777 K rows ≈ 35–45 MB max on disk
           (1 row per 10 s, not per second — 10× reduction from v1.3.0)

Analysis methods (all run aggregate SQL — zero raw rows loaded into Python):
  app_mem_trend(app, 30d)    → {avg_mem_pct, week1_avg, week2_avg, trend}
  chronic_pressure_pct(7d)   → float: % of time RAM above MEM_WARN
  _analyse_app_predictions() → [{app, mb, pct, trend, risk, chronic_pct}]
                                runs every 24 h; emits APP PREDICTION events
```

---

## Security Constraints

- Loopback-only HTTP server (`127.0.0.1:8765`) — no network exposure.
- All process signals (`SIGSTOP`, `SIGCONT`, `SIGTERM`) target user-owned processes only.
- `PROTECTED` set blocks touching kernel, window server, and the bot itself.
- `_no_kill` blocklist prevents looping SIGTERM on launchd-managed services.
- Disk cache contains only aggregate metric numbers — no process names, no user data.
- No credentials, tokens, or secrets anywhere in code, config, or cache.
