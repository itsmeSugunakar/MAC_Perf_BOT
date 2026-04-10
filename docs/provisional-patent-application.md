# Provisional Patent Application — Technical Specification

**Title of Invention:**
System and Method for Multi-Dimensional Memory Intelligence and Automated
Hierarchical Resource Remediation in a Multitasking Operating System

**Applicant:** itsmeSugunakar
**Contact:** sugun.sr@gmail.com
**Filing Type:** Provisional Patent Application (PPA)
**Recommended Filing Method:** Web ADS (EFS-Web / Patent Center — USPTO)
**Date Prepared:** 2026-04-05

> **Why Web ADS?**
> For a first-time filer without patent counsel, the USPTO Patent Center's
> Web ADS provides real-time field validation, automatic data loading into
> the USPTO database, and eliminates the formatting errors that cause
> "Notice of Omitted Items" rejections when using the PDF/AIA-14 form.
> Use "Upload ADS (PDF)" only if you are working with a registered
> patent agent who generates forms in specialised software.

---

## 1. Title of the Invention

**System and Method for Multi-Dimensional Memory Intelligence (MMIE) and
Automated Hierarchical Resource Remediation in a Consumer Multitasking
Operating System**

---

## 2. Field of the Invention

The present invention relates to computer system resource management and,
more specifically, to a lightweight, automated software engine that
monitors operating-system-level memory pressure indicators, constructs a
hierarchical attribution model of process memory consumption, applies a
linear-regression-based exhaustion forecast, drives a predictive tier-
escalation mechanism, executes a reversible four-tier remediation cascade
with genealogy-guided process scoring, and prevents futile remediation
loops via an XPC respawn guard — all without requiring user intervention
or elevated (superuser) privileges.

---

## 3. Background of the Invention

### 3.1 The Problem

Modern consumer operating systems run hundreds of concurrent processes.
Memory pressure — the condition in which physical RAM is insufficient to
satisfy all active allocations — degrades system responsiveness, causes
aggressive disk-based swap usage, and can ultimately result in out-of-memory
process termination by the operating system kernel.

Existing approaches to consumer-facing resource management share one or more
of the following deficiencies:

1. **Reactive, not predictive.** Tools that alert the user only after RAM
   utilisation crosses a static threshold (e.g., 80 %) provide no advance
   warning and no automated response.

2. **Flat process attribution.** Standard monitors (e.g., Activity Monitor,
   `top`, `htop`) report per-process RSS in isolation. A modern application
   such as a web browser may spawn dozens of helper processes (XPC services,
   renderer processes, GPU helpers) whose combined RSS is never attributed to
   the originating application. This prevents correct identification of the
   true "memory owner."

3. **Binary interventions.** Automated tools typically choose between two
   extremes: do nothing, or terminate a process. Neither approach is
   appropriate for a workstation environment where user state must be
   preserved.

4. **Ignorance of kernel-internal pressure state.** Operating-system kernels
   maintain internal pressure indicators (e.g., `kern.memorystatus_vm_pressure_level`
   on macOS, memory cgroups on Linux) that reflect the true pressure state
   more accurately than user-space RAM utilisation percentages. Existing
   consumer tools do not consult these indicators.

5. **No compressed-memory awareness.** Modern operating systems use
   in-memory compression (e.g., macOS Compressed Memory, Linux zswap).
   A utilisation metric that does not distinguish between active, inactive,
   wired, purgeable, and compressed pages cannot accurately characterise
   true memory availability.

### 3.2 Prior Art Landscape

- **Unix `renice` utilities** — well-known; address CPU priority only; no
  memory dimension.
- **macOS `purge` command** — clears inactive memory; requires superuser;
  is non-selective; does not identify which application caused pressure.
- **Linux OOM Killer** — kernel-level; terminates processes; irreversible;
  no predictive stage; unsuitable for consumer workstations.
- **Commercial "cleaner" applications** — typically flush inactive page cache;
  do not perform process genealogy attribution or predictive forecasting;
  do not implement reversible suspension.
- **macOS `memory_pressure` daemon** — raises kernel notifications; provides
  no automated userspace remediation cascade.

None of the above prior art combines: (a) multi-dimensional kernel-level
pressure sensing, (b) recursive process-tree memory attribution,
(c) linear-regression exhaustion forecasting, and (d) a reversible,
graduated SIGSTOP/SIGCONT suspension cascade — all within a single,
unprivileged, zero-native-dependency software process.

---

## 4. Summary of the Invention

The invention, referred to herein as the **Multi-Dimensional Memory
Intelligence Engine (MMIE)**, is a software method and system comprising:

1. **A Kernel Pressure Oracle** that queries the operating system's
   internal memory pressure level via system call (`sysctl`), providing a
   ground-truth pressure state independent of user-space utilisation
   percentages.

2. **A Memory Anatomy Parser** that decomposes total RAM into six
   semantically distinct categories — wired, active, inactive, purgeable,
   compressed, and free — by parsing the operating system's virtual memory
   statistics interface (`vm_stat`).

3. **A Memory Genealogy Engine** that performs a recursive parent-process-ID
   (ppid) tree traversal across all running processes to aggregate RSS
   (Resident Set Size) into "application families," attributing all helper
   processes, XPC services, and child daemons to their root-level originating
   application.

4. **A Linear-Regression Exhaustion Forecaster** that applies ordinary
   least-squares regression to a sliding window of historical RAM utilisation
   samples to calculate the estimated "Time to Exhaustion" (TTE) — the
   number of minutes until RAM utilisation is projected to reach a critical
   threshold (95 %) — enabling _predictive_ rather than purely _reactive_
   intervention.

5. **A Predictive Remediation Engine** that compares the TTE estimate
   against tier-specific time thresholds (TTE ≤ 10 min → Tier 2 early,
   TTE ≤ 5 min → Tier 3 early, TTE ≤ 2 min → Tier 4 early) to escalate
   the effective remediation tier _before_ static RAM-percentage thresholds
   are breached, enabling pre-emptive intervention under a rising memory
   trend.

6. **A CPU-RAM Conflict Resolution Gate** that prevents the CPU-throttling
   subsystem from restoring normal process priority (`nice(0)`) to processes
   that have calmed in CPU usage but belong to application families
   identified as top RAM owners during active Tier 3 or higher memory
   pressure — preventing those processes from re-expanding their memory
   footprint immediately after the CPU intervention.

7. **A Genealogy-Guided Freeze Scoring System** that ranks background
   daemon candidates for SIGSTOP suspension by combining a genealogy signal
   (process belongs to a heavy-RSS application family identified by the
   ppid-tree walk, weight = 2) with a pattern signal (process name matches
   the known-safe allowlist, weight = 1), sorting by composite score and
   RSS descending so that the daemons most responsible for memory pressure
   are targeted first.

8. **An XPC Respawn Guard** that records the timestamp of every SIGTERM
   termination and monitors running processes for services that reappear
   within a short observation window (default 10 seconds). Services
   relaunched within this window are identified as `launchd`-managed and
   are added to a persistent blocklist (`_no_kill`) to prevent futile
   kill-loops that consume CPU without yielding lasting memory relief.

9. **An Autonomous Restoration Loop** (Auto-Thaw) that monitors pressure
   recovery and automatically reverses suspension-based interventions when
   system pressure normalises, without user interaction.

---

## 5. Detailed Description of the Preferred Embodiment

### 5.1 System Architecture

The MMIE is implemented as a background thread (`BotEngine`) within an
unprivileged Python 3.11+ process. It does not require superuser (`sudo`)
privileges. It is auto-started at user login via the operating system's
service manager (macOS `launchd`) and communicates telemetry to a co-located
HTTP server that serves a Progressive Web Application (PWA) dashboard.

The engine operates on a 1-second polling cycle. Computationally expensive
MMIE sub-routines are scheduled at longer intervals with independent
cooldown timers to prevent excessive CPU consumption by the monitoring
process itself (the "observer effect").

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

   subgraph MMIE[MMIE + PRE]
      PRE[Predictive Remediation Engine\ncompute effective tier 0 to 4]
      FG[Genealogy-Guided Freeze\nSIGSTOP and SIGCONT]
      XG[XPC Respawn Guard\nno-kill blocklist]
   end

   BE --> PRE
   PRE --> FG
   PRE --> XG

   BR[Browser PWA\nChart.js dashboard] -->|GET / and GET /stats| HTTP
   HTTP -->|JSON metrics| BR
```

```
┌────────────────────────────────────────────────────────────┐
│  BotEngine (background thread, 1 Hz)                       │
│                                                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 1. _collect()              — psutil CPU/RAM/Swap    │   │
│  │ 2. _check_cpu()            — renice + CPU-RAM lock  │   │
│  │ 3. _check_memory()         — tier 1 + MMIE cascade  │   │
│  │    ├─ _compute_effective_tier() — TTE escalation    │   │
│  │    └─ _tiered_memory_remediation(effective_tier)    │   │
│  │ 4. _update_pressure_and_forecast()  (every 5 s)     │   │
│  │    ├─ _get_macos_pressure_level()  — sysctl oracle  │   │
│  │    ├─ _parse_vm_stat()             — memory anatomy │   │
│  │    ├─ _compute_mem_forecast()      — OLS regression │   │
│  │    └─ _build_memory_ancestry()    (every 120 s)     │   │
│  │ 5. _tiered_memory_remediation(mem_pct, eff_tier)    │   │
│  │    ├─ Tier 2: advisory + genealogy report           │   │
│  │    ├─ Tier 3: _freeze_background_daemons()          │   │
│  │    │          (genealogy-guided scoring + SIGSTOP)  │   │
│  │    └─ Tier 4: _sweep_idle_services() SIGTERM        │   │
│  │               (respects _no_kill blocklist)         │   │
│  │ 6. _thaw_frozen_daemons()         (on recovery)     │   │
│  │ 7. _detect_xpc_respawn()          (every 10 s)      │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │ snapshot()                       │
│                  ┌───────▼────────┐                        │
│                  │  HTTP :8765    │  → PWA Dashboard        │
│                  │  GET /stats    │  (JSON, 1 Hz poll)      │
│                  │  GET /manifest │  (PWA installable)      │
│                  └────────────────┘                        │
└────────────────────────────────────────────────────────────┘
```

### 5.2 Component 1 — Kernel Pressure Oracle

**Method:** `_get_macos_pressure_level() → str`

The oracle queries `kern.memorystatus_vm_pressure_level` via `sysctl -n`.
The kernel returns one of three integer values: `1` (Normal), `2` (Warning),
`4` (Critical). These are mapped to the symbolic levels `normal`, `warn`,
and `critical`.

This is distinct from and superior to user-space RAM utilisation in that:

- It reflects the kernel's _actual_ ability to satisfy new allocation
  requests, including compressed memory headroom and I/O-bounded swap state.
- It is updated by the kernel in real time, not sampled at a fixed interval.
- It accounts for wired memory that cannot be compressed or paged, which
  inflates the user-space utilisation percentage without reflecting
  recoverable pressure.

**Fallback:** If `sysctl` is unavailable (e.g., SIP restriction), the
oracle falls back to a percent-derived tier: ≥ 92 % → critical, ≥ 82 % → warn,
otherwise normal.

**Novelty:** Consumer monitoring tools universally derive memory "status"
from `psutil.virtual_memory().percent` or equivalent. Querying the kernel's
own `memorystatus_vm_pressure_level` sysctl as the primary pressure indicator
— and using the percent as a fallback — is a key distinguishing element of
this invention.

### 5.3 Component 2 — Memory Anatomy Parser

**Method:** `_parse_vm_stat() → dict`

The parser executes the operating system's `vm_stat` utility and parses its
output to decompose physical RAM into six semantically meaningful categories:

| Category   | Meaning                                                          |
| ---------- | ---------------------------------------------------------------- |
| Wired      | Kernel-reserved pages; cannot be paged, compressed, or purged    |
| Active     | Pages in active use by running processes                         |
| Inactive   | Pages no longer actively referenced; reclaimable                 |
| Purgeable  | Application-marked pages that can be discarded without data loss |
| Compressed | Pages compressed in-memory by the OS compressor                  |
| Free       | Immediately available pages                                      |

Page counts are multiplied by the system's page size (16 KB on Apple Silicon,
4 KB on Intel) to produce values in megabytes.

**Novelty over prior art:** Existing tools present a single "used %"
figure. The anatomy parser enables the MMIE to distinguish between
_structurally unavoidable_ pressure (high wired memory) and _recoverable_
pressure (high inactive or purgeable memory), triggering qualitatively
different advisories and interventions for each.

**Wired Memory Alert:** If wired memory exceeds 40 % of total RAM, the
engine emits a "structural pressure" warning, since wired memory cannot
be reclaimed by any userspace action — it requires process termination or
kernel module unloading.

### 5.4 Component 3 — Memory Genealogy Engine

**Method:** `_build_memory_ancestry() → list[dict]`

Modern applications spawn numerous child processes. A web browser may have
30–50 helper processes; an IDE may have 10–20. Standard process monitors
attribute memory to each child individually, making it impossible to answer
the question "which application is responsible for my RAM pressure?"

The Genealogy Engine solves this by:

1. Collecting the PID, PPID (parent PID), process name, and RSS for every
   running process via `psutil.process_iter()`.

2. For each process, recursively walking the PPID chain until reaching a
   process whose parent is PID 1 (the system service manager, `launchd`).
   This "root ancestor" is defined as the originating application.

3. Aggregating the RSS of all processes sharing the same root ancestor into
   a single "application family" entry.

4. Returning the families sorted by total aggregated RSS, descending,
   providing a ranked list of application ecosystems by memory ownership.

**Output format:**

```json
[
  { "app": "Microsoft Edge", "mb": 3474, "pct": 35.1 },
  { "app": "Code", "mb": 2579, "pct": 26.0 },
  { "app": "Slack", "mb": 299, "pct": 3.0 }
]
```

**Cycle prevention:** The walker maintains a `visited` set per traversal
to prevent infinite loops caused by reparented or malformed process entries.

**Novelty:** The recursive ppid-tree walk for _consumer workstation_
RAM attribution — as opposed to server-side container/cgroup accounting —
combined with real-time dashboard presentation, constitutes a novel
application of process genealogy to consumer memory management.

### 5.5 Component 4 — Linear-Regression Exhaustion Forecaster

**Method:** `_compute_mem_forecast() → float`

The forecaster applies Ordinary Least Squares (OLS) linear regression to
a sliding window of the most recent 30 RAM utilisation samples (representing
30 seconds of history at 1 Hz sampling) to compute the slope of memory growth.

**Algorithm:**

Given a window `W = [w₀, w₁, …, w_{n-1}]` of RAM % readings:

```
mean_x = (n - 1) / 2
mean_y = Σ(wᵢ) / n
slope  = Σ[(i − mean_x)(wᵢ − mean_y)] / Σ[(i − mean_x)²]   (% per second)
```

If `slope < 0.005` (stable or declining), the method returns `-1` (stable).

Otherwise, the estimated time to reach the critical threshold `T = 95 %`
from the current level `c = W[-1]` is:

```
TTE (seconds) = (T − c) / slope
TTE (minutes) = TTE (seconds) / 60
```

**Interpretation:**

- `TTE = -1` → Memory stable; no predictive alert.
- `TTE = 0` → Memory already at or above critical threshold.
- `TTE > 0` → System will reach 95 % RAM in approximately `TTE` minutes
  at the current growth rate.

The forecaster is evaluated every 5 seconds. Its output is:

- Displayed in the dashboard as a countdown ("↑ ~12 min to 95%")
- Optionally used to escalate tier thresholds earlier under a rising trend

**Novelty:** Applying linear regression to a sliding historical window to
produce a human-readable "Time to Exhaustion" countdown for consumer RAM
management — and surfacing this in real time in a dashboard — constitutes
a novel combination not found in prior consumer-facing tools.

### 5.6 Component 5 — Predictive Remediation Engine

**Method:** `_compute_effective_tier(mem_pct: float) → (int, int)`

The Predictive Remediation Engine translates the TTE forecast into an
**effective remediation tier** that may exceed what the raw RAM percentage
would trigger, enabling pre-emptive intervention before static thresholds
are breached.

**Algorithm:**

```
threshold_tier ← static tier from mem_pct alone (0–4)

if TTE < 0 or history_samples < TTE_MIN_SAMPLES (20):
    return (threshold_tier, threshold_tier)   # insufficient data — no escalation

predictive_tier = threshold_tier
if TTE ≤ TTE_TIER4_MIN (2 min):  predictive_tier = max(predictive_tier, 4)
elif TTE ≤ TTE_TIER3_MIN (5 min): predictive_tier = max(predictive_tier, 3)
elif TTE ≤ TTE_TIER2_MIN (10 min): predictive_tier = max(predictive_tier, 2)

return (predictive_tier, threshold_tier)
```

**Example:** RAM at 79 % (below all static thresholds, threshold_tier = 0),
but OLS slope yields TTE = 4.2 minutes → predictive_tier = 3. The engine
executes Tier 3 (SIGSTOP daemons) **before** RAM reaches 87 %, providing
a 4-minute head start on pressure relief.

When escalation occurs, the engine:

- Sets `effective_tier` in the snapshot (dashboard "Active Tier" row)
- Sets `_ram_pressure_lock = True` (activates CPU-RAM conflict gate)
- Emits a `PREDICTIVE ESCALATION: TTE=N.N min → acting at Tier X` event
- Displays an amber "PREDICTIVE ESCALATION ACTIVE" banner in the PWA

**Novelty:** This constitutes a _Predictive Remediation Engine_ — the use
of a linear-regression time-to-exhaustion forecast to escalate a graduated
remediation cascade earlier than static percentage thresholds would permit,
enabling predictive rather than purely reactive memory management. This
specific combination — OLS TTE → dynamic tier selection → graduated signal-
based interventions — is not present in any prior consumer monitoring tool.

### 5.7 Component 6 — CPU-RAM Conflict Resolution Gate

**Method:** `_check_cpu()` — restoration branch

When the CPU-throttling subsystem detects that a previously throttled
process has calmed (CPU usage dropped below `CPU_WARN / 2 = 35 %`), it
normally restores the process to normal scheduling priority via `nice(0)`.

However, restoring priority to a CPU-calmed process that is also a _top
RAM owner_ would allow it to immediately resume full CPU execution and
potentially re-expand its memory footprint — negating the Tier 3 freeze
applied to its daemon siblings.

**Conflict detection logic:**

```python
if _ram_pressure_lock:   # set by effective_tier ≥ 3
    ancestry_top3 = {entry["app"].lower() for entry in mem_ancestry[:3]}
    if any(family in process_name or process_name in family
           for family in ancestry_top3):
        emit "CPU-RAM LOCK: deferring priority restore"
        continue   # skip nice(0)
```

**Gate release:** The lock is released automatically when RAM drops below
`MEM_WARN − 5 %` and effective_tier resets to 0.

**Novelty:** The coordination between the CPU-throttling subsystem and the
RAM pressure cascade — specifically, using a RAM-pressure lock to veto CPU
priority restoration for processes identified by genealogy as dominant RAM
holders — constitutes a novel cross-dimensional resource management decision
not implemented in any known consumer tool.

### 5.8 Component 7 — Four-Tier Adaptive Remediation Cascade

**Method:** `_tiered_memory_remediation(mem_pct: float, effective_tier: int)`

The cascade applies the _minimum necessary intervention_ for the observed
pressure level, in ascending order of severity. Each tier is strictly
additive — Tier 3 also performs all Tier 2 actions.

#### Tier 1 — Observational (≥ 80 % RAM)

**Trigger:** `psutil.virtual_memory().percent ≥ 80`

**Actions:**

- Log a RAM pressure event to the activity feed.
- Identify the top-3 RSS consumers by process name and emit individual
  "RAM hog" advisories with a 5-minute cooldown (to prevent log flooding).

**Reversibility:** Fully reversible (read-only observation).

#### Tier 2 — Advisory and Structural Analysis (≥ 82 % RAM)

**Trigger:** `mem_pct ≥ MEM_TIER2_PCT` (default 82 %)

**Actions:**

a. **Purgeable Opportunity Advisory:** If the Memory Anatomy Parser
reports purgeable pages exceeding 200 MB, emit an advisory quantifying
the reclaimable amount. The kernel will reclaim these pages automatically;
the advisory informs the user that relief may arrive without intervention.

b. **Wired Memory Structural Warning:** If wired memory exceeds 40 % of
total RAM (configurable via `WIRED_WARN_PCT`), emit a one-time-per-session
structural warning. This is a qualitatively distinct alert because wired
memory cannot be reclaimed by any userspace action.

c. **Memory Genealogy Report:** If more than `MEM_ANCESTRY_COOL_S` seconds
(default 120) have elapsed since the last genealogy report, invoke the
Memory Genealogy Engine and emit a "top memory families" advisory
identifying the 3 largest application ecosystems by combined RSS.

**Reversibility:** Fully reversible (advisory only; no process signals).

#### Tier 3 — Reversible Process Suspension (≥ 87 % RAM or TTE ≤ 5 min)

**Trigger:** `effective_tier ≥ 3` AND
`time.time() − _last_freeze ≥ FREEZE_COOL_S` (default 120 s cooldown)

**Actions:**

Invoke `_freeze_background_daemons()` with **Genealogy-Guided Scoring:**

1. Snapshot the current Memory Genealogy ancestry list (top application
   families by aggregated RSS).

2. Build a `heavy_families` set from the top 5 families:

   ```
   heavy_families = {entry["app"].lower() for entry in ancestry[:5]}
   ```

3. For each candidate process, compute a composite score:

   ```
   family_match = 1  if process.name.lower() ∈ heavy_families (or substring match)
                  0  otherwise
   pattern_match = 1 if process.name matches any FREEZE_PATTERNS entry
                   0  otherwise
   score = family_match × 2 + pattern_match × 1
   ```

4. Retain only candidates with `score ≥ 1` (at least one signal present).

5. Sort candidates by `(score DESC, rss DESC)` — daemons belonging to the
   highest-RAM application families, with the most RSS, are processed first.

6. Apply safety filters: user-owned only; not in `PROTECTED` or
   `NEVER_TERMINATE`; `status ∈ {sleeping, idle}`; not already frozen.

7. Send `SIGSTOP` (signal 19) to each qualifying process in sorted order.
   Record in `_frozen_pids` with name, timestamp, and RSS.

8. Emit a `GENEALOGY FREEZE` event (for family-matched processes) or
   `PATTERN FREEZE` event (for pattern-only matches), with family name and
   MB attribution included in the event message.

**Auto-Thaw (Component 9):** When RAM drops below `MEM_WARN − 5 %`,
`SIGCONT` is sent to all frozen PIDs automatically.

**Safety guarantees:**

- Root-owned processes are excluded unconditionally.
- Processes not reaching score ≥ 1 are never targeted.
- 120-second cooldown between freeze cycles.

**Reversibility:** Fully reversible via `SIGCONT`. No process state, memory,
or file descriptors are lost during suspension.

**Novelty of genealogy-guided scoring:** Prior art freezes daemons by name
pattern alone. The combination of (a) ppid-tree RSS aggregation to identify
which application family is causing pressure, and (b) preferential targeting
of daemons belonging to that family via a weighted composite score,
constitutes a novel genealogy-guided suspension mechanism not present in
prior consumer or server-side tools.

#### Tier 4 — Emergency Termination (≥ 92 % RAM or TTE ≤ 2 min)

**Trigger:** `effective_tier ≥ 4`

**Actions:**

Invoke `_sweep_idle_services()` with **XPC Respawn Guard** enforcement:

1. Enumerate processes matching `IDLE_SERVICE_PATTERNS` — XPC helpers,
   widget extensions, wallpaper video services, Siri inference services,
   etc.
2. Exclude any process whose name is in `_no_kill` (the XPC Respawn Guard
   blocklist populated by `_detect_xpc_respawn()`).
3. Further filter to: user-owned, not in `PROTECTED` or `NEVER_TERMINATE`
   sets, CPU usage = 0, status = sleeping/idle, RSS ≥ 15 MB.
4. Send `SIGTERM` to qualifying processes. Record `{name: timestamp}` in
   `_terminated_ts` for respawn detection.
5. Accumulate freed RSS into the session `freed_mb` counter.

**Reversibility:** Services terminated at Tier 4 are re-launched on demand
by `launchd`. No user data loss occurs.

**Irreversibility caveat:** Any in-flight work within the terminated service
is lost. The allowlists and `_no_kill` guard ensure only genuinely idle,
automatically-restartable services are targeted.

### 5.9 Component 8 — XPC Respawn Guard

**Method:** `_detect_xpc_respawn()` — called every 10 seconds

macOS `launchd` automatically relaunches XPC services and system daemons
within milliseconds of termination. Repeatedly sending SIGTERM to such
services consumes CPU cycles, generates system log noise, and yields no
lasting RAM relief — a futile kill-loop.

**Detection algorithm:**

```
every 10 s:
  for name, ts in _terminated_ts:
    if name in running_process_names and (now - ts) ≤ XPC_RESPAWN_S (10 s):
        _no_kill.add(name)
        emit "XPC RESPAWN GUARD: {name} relaunched within 10s — blocklisted"

  # prune stale entries (> 60 s old)
  remove entries from _terminated_ts where (now - ts) > XPC_RESPAWN_S × 6
```

**Integration with Tier 4:** `_sweep_idle_services()` checks `_no_kill`
before sending SIGTERM. Blocklisted services are skipped permanently for
the session, preventing the engine from wasting resources on unwinnable
terminations.

**Dashboard:** The `xpc_blocked` field in the `/stats` JSON reports the
current blocklist count; the dashboard displays it as "XPC Blocked: N".

**Novelty:** Automated detection of launchd-managed process respawning
at the userspace level — and dynamic blocklisting to avoid futile kill
loops — is a novel safety mechanism not present in any known consumer or
enterprise monitoring tool.

### 5.10 Component 9 — Autonomous Restoration Loop (Auto-Thaw)

**Method:** Called from `_check_memory()` on every memory check cycle.

**Logic:**

```python
if vm.percent < MEM_WARN - 5 and self._frozen_pids:
    self._thaw_frozen_daemons()
    _ram_pressure_lock = False
    effective_tier = 0
    predictive_escalation = False
```

When the condition is met:

1. Iterate `_frozen_pids`.
2. Send `SIGCONT` to each suspended PID.
3. Clear `_frozen_pids`.
4. Release `_ram_pressure_lock` (re-enables CPU priority restoration).
5. Emit a "pressure normalised — thawed N daemons" FIX event to the log.

This loop ensures that Tier 3 suspensions are temporary and self-healing,
and that the CPU-RAM conflict gate is lifted as soon as pressure abates.

### 5.11 Threshold Configuration

All thresholds are defined as named constants at the top of the engine
module and can be modified by the operator without source code changes to
business logic:

| Constant              | Default | Description                                      |
| --------------------- | ------- | ------------------------------------------------ |
| `MEM_WARN`            | 80 %    | Tier 1 activation threshold                      |
| `MEM_TIER2_PCT`       | 82 %    | Tier 2 static threshold                          |
| `MEM_TIER3_PCT`       | 87 %    | Tier 3 static threshold                          |
| `MEM_TIER4_PCT`       | 92 %    | Tier 4 static threshold                          |
| `TTE_TIER2_MIN`       | 10 min  | TTE value that predictively escalates to Tier 2  |
| `TTE_TIER3_MIN`       | 5 min   | TTE value that predictively escalates to Tier 3  |
| `TTE_TIER4_MIN`       | 2 min   | TTE value that predictively escalates to Tier 4  |
| `TTE_MIN_SAMPLES`     | 20      | Min history samples before TTE drives escalation |
| `XPC_RESPAWN_S`       | 10 s    | Respawn detection window for XPC guard           |
| `WIRED_WARN_PCT`      | 40 %    | Wired structural pressure threshold              |
| `FREEZE_COOL_S`       | 120 s   | Minimum interval between Tier 3 freeze cycles    |
| `MEM_ANCESTRY_COOL_S` | 120 s   | Minimum interval between genealogy scans         |
| `LEAK_RATE_MB_MIN`    | 50 MB/m | RSS growth rate to flag potential leak           |

---

## 6. Claims (Informal — Provisional)

The following informal claims are provided to establish the scope of the
invention for purposes of this Provisional Patent Application. Formal claims
will be drafted in the non-provisional application.

**Claim 1 (Method — Core Cascade):**
A computer-implemented method for automated memory resource management
comprising: (a) querying an operating system kernel's internal memory
pressure level via a system call; (b) parsing virtual memory statistics to
decompose RAM into wired, active, inactive, purgeable, compressed, and free
categories; (c) applying ordinary least squares regression to a sliding
window of utilisation samples to compute a time-to-exhaustion estimate; and
(d) executing a tiered remediation cascade comprising, in ascending severity,
an observational tier, an advisory tier, a reversible process-suspension
tier, and an emergency termination tier, wherein the minimum necessary
intervention for the observed pressure level is selected.

**Claim 2 (Method — Genealogy):**
The method of Claim 1, wherein the advisory tier further comprises performing
a recursive parent-process-ID tree traversal to aggregate resident set size
across all descendant processes to a root application, thereby attributing
memory consumption to application families rather than individual processes.

**Claim 3 (Method — Reversible Suspension):**
The method of Claim 1, wherein the reversible process-suspension tier
comprises sending a SIGSTOP signal to background daemon processes matching
a curated allowlist pattern, and wherein an autonomous restoration loop
subsequently sends a SIGCONT signal to restore said processes upon detection
that system memory pressure has normalised below a recovery threshold.

**Claim 4 (Method — Predictive Forecasting):**
The method of Claim 1, wherein the time-to-exhaustion estimate is computed
by applying ordinary least squares linear regression to a sliding window of
historical RAM utilisation samples, yielding an estimated number of minutes
until utilisation reaches a critical threshold, and wherein said estimate is
displayed in real time to a user via a Progressive Web Application dashboard.

**Claim 5 (Method — Predictive Remediation Engine):**
The method of Claim 4, further comprising: comparing the time-to-exhaustion
estimate against one or more tier-specific time thresholds; and, when the
estimate falls below a tier-specific threshold, escalating the active
remediation tier to a higher severity level than the current RAM utilisation
percentage alone would trigger, thereby executing a more aggressive
intervention in advance of the static percentage threshold being breached,
and emitting a predictive escalation notification to a user-facing dashboard.

**Claim 6 (Method — CPU-RAM Conflict Resolution):**
The method of Claim 5, further comprising: maintaining a RAM pressure lock
flag that is set to active when the effective remediation tier reaches or
exceeds a third severity level; and, within a CPU-priority-management
subsystem, deferring the restoration of normal scheduling priority for any
process whose parent application family is identified as a top resident-set-
size holder by the recursive ppid-tree genealogy engine while said RAM
pressure lock remains active, thereby preventing CPU-calmed processes from
re-expanding their memory footprint during active memory pressure.

**Claim 7 (Method — Genealogy-Guided Suspension Scoring):**
The method of Claim 2, wherein the reversible process-suspension tier further
comprises: computing, for each candidate process, a composite suspension score
as a weighted sum of a genealogy signal — wherein the process belongs to an
application family identified as a heavy RSS holder by the recursive ppid-tree
walk, assigned weight 2 — and a pattern signal — wherein the process name
matches a curated background-daemon allowlist, assigned weight 1; sorting
candidate processes by composite score descending and then by resident set
size descending; and applying SIGSTOP to candidates in sorted order, such
that daemons most responsible for application-family memory pressure are
suspended preferentially.

**Claim 8 (Method — XPC Respawn Guard):**
A computer-implemented method for preventing futile process-termination loops
in a managed-service operating environment, comprising: recording a timestamp
at the moment of each process termination signal; subsequently scanning
running processes at a periodic interval; detecting when a previously
terminated process reappears within a defined observation window; adding said
process name to a persistent blocklist; and excluding blocklisted processes
from all subsequent termination decisions within the monitoring session,
thereby preventing repeated futile terminations of automatically-restarting
system services.

**Claim 9 (System):**
A system for automated memory resource management comprising: a monitoring
thread executing at a polling interval of approximately 1 Hz; a kernel
pressure oracle; a virtual memory anatomy parser; a process genealogy engine
performing recursive ppid-chain traversal; a linear-regression forecasting
module; a predictive remediation tier escalation engine; a CPU-RAM conflict
resolution gate; a genealogy-guided freeze scoring module; an XPC respawn
guard and blocklist; a four-tier remediation cascade module; an autonomous
restoration loop; and a co-located HTTP server serving telemetry as JSON to
a browser-based Progressive Web Application.

**Claim 10 (Unprivileged Operation):**
The system of Claim 9, wherein all monitoring and remediation operations are
performed without superuser (root) privileges, relying exclusively on signals
(SIGSTOP, SIGCONT, SIGTERM) directed at user-owned processes and read-only
system call interfaces.

---

## 7. Abstract

A Multi-Dimensional Memory Intelligence Engine (MMIE) monitors a consumer
multitasking operating system using a kernel pressure oracle (`sysctl
kern.memorystatus_vm_pressure_level`), virtual memory anatomy parsing
(`vm_stat`), recursive process-tree genealogy attribution, and ordinary
least squares linear-regression exhaustion forecasting. A Predictive
Remediation Engine translates the Time-to-Exhaustion forecast into a
dynamic effective remediation tier that may escalate above static RAM-
percentage thresholds, enabling pre-emptive intervention before memory
exhaustion is imminent. A CPU-RAM Conflict Resolution Gate prevents CPU-
priority restoration for processes identified by genealogy as dominant RAM
owners during active memory pressure. Upon reaching elevated pressure, the
engine executes a four-tier adaptive remediation cascade: observation,
advisory structural analysis, reversible genealogy-guided SIGSTOP
suspension of background daemons (scored by ppid-tree family membership
and name-pattern allowlist), and emergency SIGTERM termination of idle XPC
services. An XPC Respawn Guard detects launchd-managed services that
immediately respawn after termination and blocklists them to prevent futile
kill-loops. Suspended processes are automatically restored via SIGCONT when
pressure normalises. The entire system operates without superuser privileges
and delivers real-time telemetry to an installable Progressive Web
Application dashboard. The invention addresses deficiencies in existing
reactive, flat, binary, and respawn-unaware consumer memory management
approaches.

---

## 8. Brief Description of Drawings

The following drawings should accompany the non-provisional application:

**FIG. 1 — System Architecture Diagram**
Block diagram showing the BotEngine thread, MMIE sub-components, HTTP
server, and PWA dashboard, with data-flow arrows indicating the 1 Hz
polling cycle and JSON telemetry path.

**FIG. 2 — Predictive Remediation Engine Decision Diagram**
Flowchart showing: (1) OLS regression over 30-sample window → TTE value;
(2) TTE compared to TTE_TIER4/3/2_MIN thresholds; (3) effective_tier
selection as max(threshold_tier, predictive_tier); (4) `_ram_pressure_lock`
gate set/released; (5) CPU-RAM conflict resolution branch in `_check_cpu()`.

**FIG. 3 — Four-Tier Cascade Flowchart**
Decision flowchart beginning at "effective_tier check," branching at each
tier level (1–4), showing static % triggers, TTE escalation override,
genealogy-guided scoring at Tier 3, XPC guard at Tier 4, and the Auto-Thaw
recovery path when pressure drops below MEM_WARN − 5 %.

**FIG. 4 — Memory Genealogy Tree + Freeze Scoring**
Illustrative process tree showing a root application (e.g., "Microsoft Edge")
with child renderer processes, GPU helper, XPC services, and network service,
all attributed to the root with aggregated RSS. A scoring table alongside
shows how each candidate daemon receives a `family_match` and `pattern_match`
score, with final sort order determining SIGSTOP priority.

**FIG. 5 — XPC Respawn Guard Timeline**
Sequence diagram showing: SIGTERM sent → `_terminated_ts[name]` recorded →
`_detect_xpc_respawn()` fires 10 s later → process still running → name added
to `_no_kill` → subsequent Tier 4 sweep skips the blocklisted service.

**FIG. 6 — Linear Regression Forecast Diagram**
Time-series graph of RAM utilisation samples with the OLS regression line
overlaid, showing the projected intersection with the 95 % threshold, the
resulting TTE value, and the TTE_TIER3_MIN threshold that triggers predictive
Tier 3 escalation before the static 87 % threshold is reached.

**FIG. 7 — PWA Dashboard Screenshot**
Annotated screenshot of the Memory Intelligence panel showing: arc gauge,
predictive escalation banner (amber), Active Tier row (colour-coded),
CPU-RAM Lock indicator, XPC Blocked count, memory composition bar,
vm_stat detail rows, and memory families list with proportional bars.

---

## 9. Enablement

The invention is fully enabled by the reference implementation:

- **Language:** Python 3.11+
- **Dependencies:** `psutil ≥ 5.9` (PyPI); all other imports are Python
  standard library (`subprocess`, `threading`, `http.server`, `json`)
- **Platform:** macOS 13 Ventura or later (Apple Silicon and Intel)
- **Deployment:** macOS LaunchAgent (`launchd`) for autostart at user login
- **Dashboard:** Progressive Web Application served at `http://127.0.0.1:8765`;
  installable via browser "Add to Dock" on macOS
- **Repository:** https://github.com/itsmeSugunakar/MAC_Perf_BOT

The complete source code constitutes the enablement disclosure. Key methods
and their locations in the reference implementation:

| Claim Element                    | Method                          | Module                   |
| -------------------------------- | ------------------------------- | ------------------------ |
| Kernel pressure oracle           | `_get_macos_pressure_level()`   | `app/performance_gui.py` |
| Memory anatomy parser            | `_parse_vm_stat()`              | `app/performance_gui.py` |
| Genealogy engine                 | `_build_memory_ancestry()`      | `app/performance_gui.py` |
| Exhaustion forecaster            | `_compute_mem_forecast()`       | `app/performance_gui.py` |
| Predictive Remediation Engine    | `_compute_effective_tier()`     | `app/performance_gui.py` |
| CPU-RAM Conflict Resolution Gate | `_check_cpu()` (restore branch) | `app/performance_gui.py` |
| Remediation cascade              | `_tiered_memory_remediation()`  | `app/performance_gui.py` |
| Genealogy-guided freeze scoring  | `_freeze_background_daemons()`  | `app/performance_gui.py` |
| XPC Respawn Guard + blocklist    | `_detect_xpc_respawn()`         | `app/performance_gui.py` |
| Auto-Thaw restoration loop       | `_thaw_frozen_daemons()`        | `app/performance_gui.py` |

---

## 10. Filing Checklist (Web ADS — USPTO Patent Center)

Before submitting, confirm the following items are ready:

- [ ] **Specification** — this document (upload as PDF)
- [ ] **Abstract** — Section 7 above (250 words max; copy into ADS field)
- [ ] **Drawings** — FIG. 1–5 described in Section 8 (PDF or TIFF, 300 dpi)
- [ ] **Application Data Sheet** — complete via Web ADS wizard in Patent Center
  - Applicant name and address
  - Inventor name(s) and address(es)
  - Title of invention (from Section 1)
  - Correspondence address
- [ ] **Filing fee** — current PPA fee: USD 320 (small entity) / USD 160 (micro-entity)
  - Micro-entity: income ≤ 3× U.S. median household income; ≤ 4 prior patents
- [ ] **Confirmation number** — save the USPTO-issued confirmation and
      application number; this establishes your **Priority Date**

> **Priority Date Note:** A Provisional Patent Application establishes a
> priority date but does NOT become a patent. A non-provisional application
> must be filed within **12 months** of the PPA filing date to claim the
> priority date. Mark your calendar.

---

_Prepared by: itsmeSugunakar · 2026-04-05_
_This document is a technical specification for a Provisional Patent
Application. It does not constitute legal advice. For formal patent
prosecution, consult a registered USPTO patent attorney or agent._
