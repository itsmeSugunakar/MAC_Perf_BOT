# Architecture — MAC Performance Bot

## Data Flow

```
macOS kernel
    │
    ▼  psutil
BotEngine (background thread, 1 Hz)
    │
    ├── cpu_hist[], mem_hist[]      ← ring buffer (90 samples)
    ├── top_procs[]                 ← sorted by CPU, top-12
    ├── throttled{}                 ← pid → name map
    └── events[]                   ← ring buffer (200 entries)
         │
         ▼  snapshot() called by HTTP handler
    HTTP Handler (main thread)
         │
         ├── GET /        → HTML page (embedded string, ~8 KB)
         ├── GET /stats   → JSON snapshot (< 5 KB per response)
         └── GET /pause   → toggle engine.running flag
              │
              ▼  polling every 1 s via setInterval
    Browser (Chart.js)
         ├── CPU sparkline (canvas)
         ├── RAM sparkline (canvas)
         ├── Stat cards (6 × live values)
         ├── Activity log (prepend newest events)
         └── Process table (CPU progress bars)
```

## Thread Model

```
Main thread      → HTTPServer.serve_forever()
bot-engine       → BotEngine.run()  (daemon=True)
timer thread     → webbrowser.open() after 0.8 s  (one-shot)
```

All shared state is protected by `BotEngine._lock` (threading.Lock).
The HTTP handler only reads via `snapshot()` — never writes — so contention
is minimal.

## Remediation Logic

```
Every second:
  collect()        → update cpu_hist, mem_hist, top_procs
  check_cpu()
    if sys_cpu < CPU_WARN (70 %)  → try to restore any throttled procs
    else
      for each process:
        if cpu >= CPU_THROTTLE (85 %)  → nice(10), emit FIX event
        elif cpu >= CPU_WARN (70 %)    → emit WARN event
  check_memory()   (every 3 s)
    if ram >= MEM_WARN (80 %)          → emit ISSUE event
    if swap >= 50 %                    → emit WARN (once per spike)
  check_disk()     (every 10 s)
    if disk >= 90 %                    → emit ISSUE event
```
