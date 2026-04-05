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
The HTTP handler only reads via `snapshot()` — never writes — so lock contention
is minimal.  
`MetricsCache` runs all SQLite I/O on the `bot-engine` thread (flush every 60 s,
prune once per day) — no additional threads.

---

## Engine Tick Schedule

```
Every 1 s   → _collect()                 CPU / RAM / Swap / Disk sampling + cache.record()
Every 1 s   → _check_cpu()               CPU-RAM conflict resolution + renice hogs
Every 3 s   → _check_memory()            PRE effective_tier + MMIE cascade
Every 5 s   → _update_pressure_and_forecast()   kernel oracle + vm_stat + OLS forecast
Every 10 s  → _check_disk()
Every 10 s  → _detect_xpc_respawn()      XPC Respawn Guard scan
Every 30 s  → _check_power_mode()
Every 30 s  → _sweep_idle_services()     Tier 4 emergency termination (on demand)
Every 60 s  → cache.flush()              Batch SQLite write (executemany 60 rows)
Every 60 s  → cache.prune()              Prune rows > 90 days (no-op if not due)
Every 60 s  → cache.db_size_mb() / row_count()   update dashboard stats
Every 60 s  → _check_thermal()
Every 60 s  → _check_zombies()
Every 60 s  → _track_memory_leaks()
Every 300 s → _check_caches()            ~/Library/Caches size warning
Every 3600 s → _analyse_app_predictions()  90-day risk analysis (daily in practice)
```

---

## Remediation Logic

```
_check_cpu() — every second:
  for each throttled pid:
    if cpu < CPU_WARN/2 (35 %):
      if _ram_pressure_lock AND proc is top-3 RAM family:
        → defer nice(0) [CPU-RAM conflict resolution]
      else:
        → nice(0), emit FIX
  if sys_cpu >= CPU_WARN (70 %):
    for each process:
      if cpu >= CPU_THROTTLE (85 %) → nice(10), emit FIX
      elif cpu >= CPU_WARN (70 %)   → emit WARN

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
Capacity : ~90 days × 86400 rows/day ≈ 7.8 M rows ≈ 350–450 MB max on disk

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
