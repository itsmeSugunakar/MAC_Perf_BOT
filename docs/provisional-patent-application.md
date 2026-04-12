# Provisional Patent Application — Technical Specification

**Title of Invention:**
System and Method for Multi-Dimensional Memory Intelligence, Adaptive
Multi-Signal Consensus Escalation, and Autonomous Self-Calibrating Resource
Remediation in a Multitasking Operating System

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

**System and Method for Multi-Dimensional Memory Intelligence (MMIE),
Adaptive Multi-Signal Consensus Escalation, and Autonomous Self-Calibrating
Resource Remediation in a Consumer Multitasking Operating System**

---

## 2. Field of the Invention

The present invention relates to computer system resource management and,
more specifically, to a lightweight, automated software engine that
monitors operating-system-level memory pressure indicators, constructs a
hierarchical attribution model of process memory consumption, applies a
three-model ensemble exhaustion forecaster (Multi-Model Adaptive Forecaster,
MMAF), drives tier escalation through a six-signal weighted quorum
(Multi-Signal Consensus Escalation Engine, MSCEE), executes a reversible
four-tier remediation cascade with genealogy-guided and velocity-momentum-
weighted process scoring (RVMS), applies a graduated SIGCONT thaw sequencer
(GTS), prevents futile remediation loops via an XPC respawn guard, and
continuously self-calibrates remediation thresholds from historical data
(ATCE), learns circadian memory patterns for proactive intervention (CMPE),
and adjusts exhaustion predictions based on thermal coupling (TMCP) — all
without requiring user intervention or elevated (superuser) privileges.

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

4. **A Multi-Model Adaptive Forecaster (MMAF)** that concurrently fits three
   regression models — linear OLS, quadratic (via Vandermonde normal
   equations), and exponential (log-linearised OLS) — to a sliding window of
   historical RAM utilisation samples, selects the winner by minimum residual
   sum of squares, and extrapolates to compute the "Time to Exhaustion" (TTE)
   — the estimated minutes until RAM utilisation reaches a critical threshold
   (95 %) — enabling _predictive_ rather than purely _reactive_ intervention
   with adaptive model selection per tick.

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

9. **An Autonomous Restoration Loop** (Auto-Thaw) implemented as a
   **Graduated Thaw Sequencer (GTS)** that restores suspended processes
   in ascending RSS order with a configurable inter-send gap, aborting if
   RAM rises beyond a memory gate threshold during thaw, ensuring that
   simultaneous SIGCONT delivery does not cause a memory spike.

10. **A Compression Efficiency Oracle (CEO)** that computes a Compression
    Pressure Index (CPI = compressed / (compressed + purgeable)) from
    `vm_stat` output, providing a signal that quantifies compressor headroom
    depletion independently of raw RAM percentage, and emits tiered advisories
    at CPI thresholds.

11. **A Multi-Signal Consensus Escalation Engine (MSCEE)** that replaces
    two-signal `max()` tier selection with a six-signal weighted quorum — RAM
    percentage (weight 0.30), TTE (0.25), kernel oracle level (0.20),
    compression CPI (0.12), swap velocity (0.08), and circadian hour pattern
    (0.05) — adopting a candidate tier only when the summed weight of signals
    voting for that tier meets or exceeds a quorum threshold (0.55), providing
    consensus-based, noise-resistant escalation.

12. **An Adaptive Threshold Calibration Engine (ATCE)** that periodically
    queries the 90-day SQLite metric cache to compute the 75th, 85th, and 93rd
    percentiles of historical RAM utilisation, using these percentiles to
    self-tune the Tier 2, Tier 3, and Tier 4 activation thresholds, making the
    escalation model adapt to each individual system's baseline behaviour.

13. **A Circadian Memory Pattern Engine (CMPE)** that aggregates historical
    RAM utilisation from the metric cache by hour-of-day, constructs a 24-hour
    memory pressure profile, and triggers proactive pre-emptive daemon
    suspension before a predictable high-pressure hour begins, based on learned
    patterns rather than instantaneous measurements.

14. **A Thermal-Memory Coupling Predictor (TMCP)** that learns the empirical
    relationship between CPU thermal throttling (reduced clock speed) and
    elevated memory pressure through exponential moving average regression over
    throttled-state cache rows, and applies this learned coupling coefficient
    to shorten the MMAF time-to-exhaustion estimate in real time when thermal
    throttling is detected, providing thermally-aware predictive escalation.

15. **An RSS Velocity Momentum Scorer (RVMS)** that measures the rate of RSS
    growth for each process candidate (MB/s) and applies a continuous velocity
    multiplier in the range [1.0, 2.0] to the freeze composite score,
    preferentially suspending processes whose memory footprint is growing
    rapidly in addition to being large, thereby targeting the most dynamically
    dangerous processes.

16. **A 90-Day Metric History Store** (SQLite disk cache) that records system
    metrics at a 10-second cadence, retaining up to 90 days of history for
    aggregate queries powering ATCE, CMPE, TMCP, and application-level risk
    prediction, with automatic daily pruning and self-migrating schema.

17. **An Application Performance Prediction System** that analyses 90 days of
    cached metric history to classify per-application memory risk as high,
    medium, or low, computing week-over-week trend, average RAM contribution,
    and chronic pressure percentage for each application, with results exposed
    via the dashboard and JSON API.

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

### 5.5 Component 4 — Multi-Model Adaptive Forecaster (MMAF)

**Method:** `_compute_mem_forecast() → float`

The MMAF concurrently fits three mathematical models to the most recent
`MMAF_WINDOW` (30) RAM utilisation samples and selects the best-fit model
by minimum residual sum of squares, yielding an adaptive Time-to-Exhaustion
(TTE) estimate.

**Models:**

*Linear OLS:*
```
slope = Σ[(i − x̄)(wᵢ − ȳ)] / Σ[(i − x̄)²]
intercept = ȳ − slope × x̄
predict(t) = slope × t + intercept
```

*Quadratic (Vandermonde normal equations, pure Python):*
```
Solves [Σx⁴ Σx³ Σx²][a]   [Σx²y]
       [Σx³ Σx² Σx ][b] = [Σxy ]  via Cramer's rule (3×3 determinant)
       [Σx² Σx  n  ][c]   [Σy  ]
predict(t) = a·t² + b·t + c
```

*Exponential (log-linearised OLS, activated only when all samples > 0):*
```
fit log(wᵢ) = mₑ·i + bₑ   via standard OLS
predict(t) = e^(mₑ·t + bₑ)
```

**Winner selection:** The model with the lowest residual sum of squares
`Σ(wᵢ − predict(i))²` is selected. Its name is stored in
`_last_forecast_model` and surfaced in the dashboard "Forecast Model" row.

**TTE computation:** The winning model is extrapolated forward to the
`MMAF_TARGET_PCT` (95 %) threshold using numerical search (quadratic/exponential)
or closed-form solution (linear). If slope ≤ 0.005, returns -1 (stable).

**TMCP adjustment:** The raw TTE is passed to `_adjust_tte_for_thermal()`,
which shortens it proportionally to the thermal coupling coefficient when
CPU throttling is detected (see Section 5.17).

**Novelty:** The concurrent fitting, residual-based selection, and unified
TTE extrapolation across linear, quadratic, and exponential models — without
external numerical libraries — constitutes a novel adaptive forecasting
approach for consumer RAM management not present in prior art.

### 5.6 Component 5 — Multi-Signal Consensus Escalation Engine (MSCEE)

**Method:** `_compute_effective_tier(mem_pct: float) → int`

The MSCEE replaces the prior two-signal `max(threshold_tier, predictive_tier)`
with a six-signal weighted quorum that adopts a candidate tier only when
the aggregate weight of signals voting for that tier meets a quorum threshold.

**Six signals and weights:**

| Signal | Source | Weight |
|--------|--------|--------|
| S1: RAM % | `psutil.virtual_memory()` | 0.30 |
| S2: TTE | MMAF output | 0.25 |
| S3: Kernel oracle | `sysctl kern.memorystatus` | 0.20 |
| S4: CPI | CEO output | 0.12 |
| S5: Swap velocity | delta swap.used / elapsed | 0.08 |
| S6: Circadian hour | CMPE profile lookup | 0.05 |

**Quorum algorithm:**

```
for candidate_tier in [4, 3, 2, 1]:
    weighted_vote = Σ(weight_s for each signal s voting ≥ candidate_tier)
    if weighted_vote >= MSCEE_QUORUM (0.55):
        effective_tier = candidate_tier
        break
else:
    effective_tier = 0
```

Each signal independently computes which tier it votes for based on its
own thresholds (e.g., S1 votes tier from static % lookup; S2 votes from
TTE thresholds; S3 maps kernel level; S4 from CPI tiers; S5 from MB/s
threshold; S6 from hour profile score).

**S5 swap velocity tier thresholds:**

| Swap velocity | S5 vote tier |
|---------------|-------------|
| ≥ 100 MB/s    | 3           |
| ≥ 50 MB/s     | 2           |
| ≥ 20 MB/s     | 1           |
| < 20 MB/s     | 0           |

**Fallback:** If no candidate tier 1–4 achieves quorum, `effective_tier` falls back to `threshold_tier` (the RAM-percentage signal S1 alone). S1 is always applied as an unconditional floor — the quorum only determines whether additional tier escalation is warranted.

**Example:** RAM at 79 % (S1→tier 0), TTE = 4.2 min (S2→tier 3),
kernel=warn (S3→tier 2), CPI=0.6 (S4→tier 2), swap stable (S5→tier 0),
circadian peak (S6→tier 2).
At candidate_tier=3: vote = 0.25 (S2 only) < 0.55; no adoption.
At candidate_tier=2: vote = 0.25+0.20+0.12+0.05 = 0.62 ≥ 0.55; effective_tier=2.
Fallback would be threshold_tier = 0 (S1 alone, since RAM is 79 % < all static thresholds).

When escalation occurs, the engine:

- Sets `effective_tier` in the snapshot (dashboard "Active Tier" row)
- Sets `_ram_pressure_lock = True` when effective_tier ≥ 3
- Emits `PREDICTIVE ESCALATION` event if TTE drove above static tier
- Displays amber "PREDICTIVE ESCALATION ACTIVE" banner in the PWA

**Novelty:** Multi-signal weighted quorum escalation — combining kernel
oracle, compression CPI, swap velocity, circadian pattern, MMAF TTE, and
RAM percentage into a single consensus vote — constitutes a novel,
noise-resistant tier escalation mechanism not present in any prior consumer
or enterprise memory management tool.

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

3. For each candidate process, compute a composite score incorporating
   **RVMS — RSS Velocity Momentum Scoring:**

   ```
   family_match  = 1  if process.name.lower() ∈ heavy_families (or substring match)
                   0  otherwise
   pattern_match = 1  if process.name matches any FREEZE_PATTERNS entry
                   0  otherwise

   # RVMS velocity boost
   delta_mb = rss_mb − _rss_velocity[pid].last_mb
   elapsed  = now − _rss_velocity[pid].ts
   rate     = delta_mb / elapsed              # MB/s
   vboost   = min(1.0 + rate / 10.0, RVMS_MAX_BOOST)   # capped at 2.0×

   score = (family_match × 2 + pattern_match × 1) × vboost
   ```

4. Retain only candidates with `score ≥ 1.0` (at least one signal present).

5. Sort candidates by `score DESC` — daemons belonging to the highest-RAM
   and fastest-growing application families are processed first.

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

### 5.10 Component 9 — Graduated Thaw Sequencer (GTS)

**Method:** `_thaw_frozen_daemons()` — called from `_check_memory()` when
`vm.percent < MEM_WARN − 5` and `_frozen_pids` is non-empty.

Prior implementations sent SIGCONT to all frozen processes simultaneously.
This bulk restore caused a simultaneous re-expansion of memory footprints,
potentially pushing RAM back above threshold and triggering an immediate
re-freeze cycle.

**GTS algorithm:**

```
baseline_mem = current_vm.percent
sorted_pids = sorted(_frozen_pids.items(), key=lambda kv: kv[1].rss_mb)  # ascending RSS

for (pid, (name, freeze_ts, rss_mb)) in sorted_pids:
    current_mem = psutil.virtual_memory().percent
    if current_mem − baseline_mem > GTS_MEM_GATE_PCT (5 %):
        emit WARN "GTS: RAM rising — aborting thaw"
        break
    SIGCONT(pid) → remove from _frozen_pids → emit FIX "thawed {name}"
    time.sleep(GTS_WAIT_S)   # 2-second gap
```

**Properties:**
- **RSS-ascending order:** smallest-footprint daemons restored first,
  minimising memory impact of each step.
- **Memory gate:** if RAM rises more than 5 % from baseline during thaw,
  the sequence aborts, leaving remaining processes frozen until next cycle.
- **Inter-send gap:** 2-second delay between sends allows the OS compressor
  to react to each restore before the next.

After completion (or abort): releases `_ram_pressure_lock` and resets
`effective_tier` if all pids are thawed.

**Novelty:** Graduated, ordered SIGCONT delivery with mid-sequence RAM
monitoring and abort capability constitutes a novel safe restoration
mechanism not present in prior process management tools.

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

**MMAF constants:**

| Constant           | Default | Description                                                |
| ------------------ | ------- | ---------------------------------------------------------- |
| `MMAF_MIN_SAMPLES` | 10      | Minimum `mem_hist` samples before any model engages        |
| `MMAF_WINDOW`      | 30      | Rolling window size (seconds) for model fitting            |
| `MMAF_TARGET_PCT`  | 95 %    | RAM % target for TTE extrapolation                         |

**CEO constants:**

| Constant             | Default | Description                                            |
| -------------------- | ------- | ------------------------------------------------------ |
| `CPI_TIER2`          | 0.50    | CPI ≥ this emits an "efficiency degrading" issue       |
| `CPI_TIER3`          | 0.75    | CPI ≥ this emits a "compressor exhaustion" warning     |
| `CEO_MIN_COMPRESSED` | 200 MB  | Minimum compressed memory before CEO signal is valid   |

**MSCEE constants:**

| Constant       | Default | Description                                                |
| -------------- | ------- | ---------------------------------------------------------- |
| `MSCEE_QUORUM` | 0.55    | Weighted vote share required to adopt a candidate tier     |

**GTS constants:**

| Constant           | Default | Description                                              |
| ------------------ | ------- | -------------------------------------------------------- |
| `GTS_WAIT_S`       | 2.0 s   | Gap between successive SIGCONT sends                     |
| `GTS_MEM_GATE_PCT` | 5.0 %   | Abort thaw if RAM rises more than this since thaw began  |

**ATCE constants:**

| Constant         | Default | Description                                                |
| ---------------- | ------- | ---------------------------------------------------------- |
| `ATCE_PERCENTILE`| 75      | 75th-pct → Tier 2; 85th → Tier 3; 93rd → Tier 4           |
| `ATCE_COOL_S`    | 3600 s  | Recalibrate at most once per hour                          |
| `ATCE_MIN_ROWS`  | 1000    | Minimum cache rows before calibration runs                 |

**CMPE constants:**

| Constant               | Default | Description                                          |
| ---------------------- | ------- | ---------------------------------------------------- |
| `CMPE_PRE_FREEZE_SCORE`| 70 %    | Hour avg ≥ this triggers proactive pre-freeze        |
| `CMPE_COOL_S`          | 3600 s  | Circadian profile refresh and check once per hour    |

**TMCP constants:**

| Constant          | Default | Description                                              |
| ----------------- | ------- | -------------------------------------------------------- |
| `TMCP_LEARN_RATE` | 0.10    | EMA learning rate for thermal→memory coupling            |
| `TMCP_COOL_S`     | 3600 s  | Recompute coupling factor once per hour                  |
| `TMCP_MIN_SAMPLES`| 5       | Minimum throttled-state rows before coupling is applied  |

**RVMS constants:**

| Constant        | Default | Description                                              |
| --------------- | ------- | -------------------------------------------------------- |
| `RVMS_MAX_BOOST`| 2.0×    | Maximum velocity momentum multiplier on freeze score     |

### 5.12 Component 10 — Compression Efficiency Oracle (CEO)

**Method:** `_compute_compression_pressure(vm_bd: dict) → float`

The CEO computes a **Compression Pressure Index (CPI)** from the `vm_stat`
anatomy parsed by Component 2:

```
CPI = compressed / (compressed + purgeable)
```

A CPI approaching 1.0 indicates that the OS compressor has little remaining
headroom — nearly all compressible pages are already compressed, and purgeable
pages are depleted. This state signals impending memory exhaustion more
sensitively than raw RAM percentage, since the compressor is the OS's last
defence before swap usage accelerates.

**Advisory thresholds:**

- `CPI ≥ CEO_MIN_COMPRESSED` (200 MB of compressed memory required for signal validity)
- `CPI ≥ CPI_TIER2` (0.50) → emit ISSUE "compression efficiency degrading"
- `CPI ≥ CPI_TIER3` (0.75) → emit WARN "compressor approaching exhaustion"

The CPI is stored in `_compression_pressure` and fed as Signal S4 into the
MSCEE weighted quorum (Section 5.6), with weight 0.12.

**Novelty:** Deriving a real-time compression headroom index from `vm_stat`
output and integrating it as a weighted escalation signal — rather than as
a standalone alert — constitutes a novel use of OS memory anatomy data in
an automated remediation decision engine.

### 5.13 Component 11 — Adaptive Threshold Calibration Engine (ATCE)

**Method:** `_calibrate_thresholds()` — called hourly, guarded by `ATCE_COOL_S`

Static tier thresholds (82 / 87 / 92 %) represent population averages, not
the behaviour of any specific system. A machine with sustained workloads
typically at 75 % RAM may benefit from a lower Tier 2 threshold; a server
regularly at 88 % would generate excessive Tier 3 interventions at the same
defaults.

**Algorithm:**

```
rows = SELECT mem_pct FROM metrics WHERE ts > now − 30 days ORDER BY mem_pct
n = len(rows)
if n < ATCE_MIN_ROWS (1000): return  # insufficient history

tier2 = rows[int(n × 0.75)]    # 75th percentile
tier3 = rows[int(n × 0.85)]    # 85th percentile
tier4 = rows[int(n × 0.93)]    # 93rd percentile

_cal_thresholds = {"tier2": tier2, "tier3": tier3, "tier4": tier4}
```

**Sanity guard:** A calibration result is rejected unless `60 ≤ tier2 ≤ 92`
and `tier2 < tier3 < tier4`. If the historical distribution is too flat,
constant, or inverted, the calibration is skipped and static defaults remain.

The calibrated thresholds are used by `_compute_effective_tier()` in place
of the static defaults once `_cal_thresholds` is populated. They are
surfaced in the `/stats` JSON as `cal_thresholds` and displayed on the dashboard.

**Novelty:** Continuous self-calibration of memory pressure tier thresholds
from historical cache percentiles — adapting intervention aggressiveness to
observed system behaviour over 30 days — is a novel self-tuning mechanism
not found in prior consumer memory management tools.

### 5.14 Component 12 — Circadian Memory Pattern Engine (CMPE)

**Method:** `_check_circadian_pressure()` + `_build_circadian_profile()`
— called every 60 seconds, guarded by `CMPE_COOL_S` (3600 s).

Workstation memory usage follows strong circadian patterns: video-call hours
drive browser and codec memory peaks; batch processing jobs fire overnight;
end-of-day workspace accumulation repeats daily. CMPE learns these patterns
and acts proactively before the peak begins.

**Profile construction:**

```sql
SELECT (ts / 3600) % 24 AS hour, AVG(mem_pct)
FROM metrics
GROUP BY hour
```

This produces a 24-entry dictionary mapping each hour-of-day to its historical
average RAM utilisation percentage (`_circadian_profile`).

**Proactive pre-freeze trigger:**

```
current_hour_avg = _circadian_profile.get(current_hour, 0)
if current_hour_avg >= CMPE_PRE_FREEZE_SCORE (70 %)
   AND current_mem_pct >= MEM_WARN:
    → _freeze_background_daemons()   # proactive, before MSCEE tier 3
```

The circadian hour score is also fed as Signal S6 into the MSCEE quorum
(weight 0.05) to bias escalation during predictable high-pressure periods.

**Implementation note:** The current reference implementation groups rows
by `ts/3600 % 24` (Unix epoch seconds / 3600 mod 24), which produces UTC
hours. On machines in non-UTC time zones the learned profile is offset from
the user's perceived local time by the UTC offset. A production deployment
should normalise timestamps to local time before grouping.

**Novelty:** Learning per-hour-of-day memory pressure profiles from historical
cache data and using them to trigger proactive process suspension before a
predictable pressure peak constitutes a novel circadian-aware remediation
approach not present in any known consumer monitoring tool.

### 5.15 Component 13 — Thermal-Memory Coupling Predictor (TMCP)

**Methods:** `_adjust_tte_for_thermal(tte)` + `_compute_thermal_coupling()`
— coupling coefficient recomputed hourly, guarded by `TMCP_COOL_S`.

On thermally constrained systems (Apple Silicon, thin-and-light laptops),
CPU thermal throttling (reduction of clock speed below rated frequency)
causes a measurable increase in memory pressure — processes complete tasks
more slowly, keeping working-set pages resident longer. TMCP quantifies and
exploits this empirical relationship.

**Coupling coefficient learning:**

```
rows = SELECT thermal_pct, mem_pct FROM metrics
       WHERE thermal_pct < 100 AND ts > now − 30 days

# OLS regression on throttled rows
cov   = Σ[(thermal_pct_i − t̄)(mem_pct_i − m̄)] / n
var_t = Σ[(thermal_pct_i − t̄)²] / n
coupling_raw = abs(cov / var_t) / 100.0   # normalise to [0, 1]

_thermal_coupling = (1 − TMCP_LEARN_RATE) × _thermal_coupling
                    + TMCP_LEARN_RATE × coupling_raw   # EMA update
```

**TTE adjustment:**

```
throttle_fraction = (100 − thermal_pct) / 100.0
adjustment = max(1.0 − _thermal_coupling × throttle_fraction, 0.5)
adjusted_tte = raw_tte × adjustment   # shortened by up to 50 %
```

When the CPU is at 60 % of rated speed (throttle_fraction = 0.40) and
coupling = 0.80, TTE is shortened by 32 %, triggering earlier escalation
than thermal-unaware tools would permit.

**Novelty:** Learning the empirical thermal→memory coupling coefficient from
historical data via exponential moving average, and applying it to shorten
real-time exhaustion forecasts during active thermal throttle, constitutes
a novel thermally-aware predictive memory management mechanism.

### 5.16 Component 14 — RSS Velocity Momentum Scorer (RVMS)

**Method:** `_get_process_velocity(pid: int, rss_mb: float) → float`

The RVMS augments the freeze composite score with a velocity dimension:
a process growing at 5 MB/s is a more imminent threat than a static process
of the same RSS, even if the genealogy score is identical.

**Algorithm:**

```
if pid not in _rss_velocity:
    _rss_velocity[pid] = (rss_mb, now)
    return 1.0   # no history — neutral boost

(last_mb, last_ts) = _rss_velocity[pid]
_rss_velocity[pid] = (rss_mb, now)

delta_mb = rss_mb − last_mb
elapsed  = now − last_ts
if elapsed <= 0: return 1.0

rate = delta_mb / elapsed               # MB/s
boost = min(1.0 + rate / 10.0, RVMS_MAX_BOOST)   # capped at 2.0×
return max(boost, 1.0)                  # never penalise shrinking processes
```

The boost is applied to the freeze composite score in
`_freeze_background_daemons()`:

```
score = (family_match × 2 + pattern_match × 1) × vboost
```

**Novelty:** Incorporating a continuous RSS growth-rate velocity multiplier
into the freeze candidate scoring function — ensuring that rapidly-expanding
processes are prioritised over same-size static processes — constitutes a
novel velocity-momentum dimension in process suspension decision-making.

### 5.17 Component 15 — 90-Day Metric History Store (MetricsCache)

**Class:** `MetricsCache`

The MetricsCache provides persistent, bounded, aggregate-queryable storage
for system telemetry, enabling all historical analysis components (ATCE,
CMPE, TMCP, App Predictions).

**Schema (v1.5.0):**

```sql
CREATE TABLE IF NOT EXISTS metrics (
    ts          INTEGER,
    cpu_pct     REAL,
    mem_pct     REAL,
    swap_pct    REAL,
    disk_pct    REAL,
    pressure    TEXT,
    eff_tier    INTEGER,
    tte_min     REAL,
    thermal_pct INTEGER DEFAULT 100
)
```

The `thermal_pct` column was added in v1.5.0 to support TMCP. Existing
databases are automatically migrated via:

```sql
ALTER TABLE metrics ADD COLUMN thermal_pct INTEGER DEFAULT 100
```

wrapped in `try/except OperationalError` — safe on already-migrated schemas.

**Write path:** `cache.record()` appends to an in-memory Python list (no
I/O). `cache.flush()` executes `INSERT INTO metrics VALUES (?,?,?,?,?,?,?,?,?)`
as a single `executemany()` batch every 60 seconds.

**Read path:** All queries are aggregate-only — no raw rows are ever loaded
into Python memory. This ensures that even at 777 K rows (90 days), query
latency remains under 50 ms.

**Pruning:** `DELETE WHERE ts < now − CACHE_RETENTION_DAYS × 86400` runs
at most once per 24 hours. After pruning, a WAL checkpoint is issued to
reclaim disk space.

**Novelty:** The combination of 10-second cadence sampling, 9-column schema
including thermal state, self-migrating `ALTER TABLE` logic, batch-write
buffering, and aggregate-only read access — all within a single-threaded,
zero-dependency Python process — constitutes a novel lightweight telemetry
store design optimised for consumer workstation deployment.

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

**Claim 11 (Method — Multi-Model Adaptive Forecasting):**
The method of Claim 4, wherein the time-to-exhaustion estimate is computed
by concurrently fitting a linear ordinary least squares model, a quadratic
model via Vandermonde normal equations solved with Cramer's rule, and an
exponential model via log-linearised ordinary least squares, to a sliding
window of RAM utilisation samples; selecting the model with minimum residual
sum of squares as the winner; extrapolating the winning model to a critical
threshold percentage to produce the time-to-exhaustion estimate; and storing
the identity of the winning model for display in a user-facing dashboard.

**Claim 12 (Method — Compression Efficiency Oracle):**
A computer-implemented method comprising: parsing virtual memory statistics
to obtain the quantities of compressed and purgeable memory pages; computing
a compression pressure index as the ratio of compressed memory to the sum
of compressed and purgeable memory; comparing said index against one or more
threshold values; emitting tiered advisory events when thresholds are
exceeded; and supplying said index as a weighted input signal to a multi-
signal consensus escalation engine for tier determination.

**Claim 13 (Method — Multi-Signal Consensus Escalation):**
A computer-implemented method for memory pressure tier determination
comprising: computing, for each of a plurality of signals including RAM
utilisation percentage, time-to-exhaustion estimate, operating system kernel
pressure level, compression pressure index, swap memory growth velocity, and
circadian hour pattern, a per-signal candidate remediation tier; assigning
a predetermined weight to each signal; summing the weights of all signals
whose candidate tier meets or exceeds a test tier level; comparing said
weighted sum against a quorum threshold; and adopting the test tier as the
effective remediation tier only when the weighted sum meets or exceeds the
quorum threshold, thereby requiring consensus across multiple independent
signals before escalating interventions.

**Claim 14 (Method — Adaptive Threshold Calibration):**
A computer-implemented method comprising: querying a persistent metric
history store to retrieve system RAM utilisation values over a preceding
retention window; computing the 75th, 85th, and 93rd percentile values of
said historical distribution; substituting said percentile values as the
activation thresholds for a second, third, and fourth remediation tier
respectively; and repeating said calibration at a periodic interval, thereby
continuously adapting remediation aggressiveness to the observed baseline
behaviour of the specific system on which the method executes.

**Claim 15 (Method — Circadian Memory Pattern Learning):**
A computer-implemented method comprising: querying a persistent metric
history store to compute, for each hour of the day, an average RAM
utilisation value, thereby constructing a twenty-four-entry circadian
memory pressure profile; detecting when the current hour's historical
average meets or exceeds a pre-freeze score threshold; and, when said
threshold is met and current RAM utilisation exceeds a warning threshold,
proactively suspending background daemon processes before a predicted high-
pressure hour commences, thereby enabling pre-emptive rather than reactive
remediation based on learned temporal patterns.

**Claim 16 (Method — Thermal-Memory Coupling Prediction):**
A computer-implemented method comprising: querying a persistent metric
history store to retrieve contemporaneous CPU thermal throttle state and
RAM utilisation measurements during periods of thermal throttling;
computing an ordinary least squares regression coefficient representing
the empirical relationship between thermal throttle depth and RAM
utilisation increase; updating a stored coupling coefficient via exponential
moving average; and, when active thermal throttling is detected, multiplying
a time-to-exhaustion forecast by an adjustment factor derived from the
coupling coefficient and current throttle depth, thereby shortening the
forecast and triggering earlier remediation escalation on thermally
constrained systems.

**Claim 17 (Method — RSS Velocity Momentum Scoring):**
The method of Claim 7, further comprising: recording the resident set size
and timestamp for each candidate process at each evaluation cycle; computing
a memory growth rate in megabytes per second for each candidate as the
change in resident set size divided by elapsed time; computing a velocity
multiplier as a monotonically increasing function of the growth rate, capped
at a maximum value; and applying said velocity multiplier to the genealogy-
and-pattern composite score prior to sorting, such that processes exhibiting
rapid memory growth are prioritised for suspension over same-size processes
with stable or declining memory footprints.

**Claim 18 (Method — Graduated Thaw Sequencing):**
The method of Claim 3, wherein the autonomous restoration loop comprises:
recording the current RAM utilisation percentage as a baseline; sorting
suspended processes in ascending order of resident set size; sequentially
sending a SIGCONT signal to each process in said sorted order; pausing for
a configurable inter-send gap between successive signals to allow the
operating system memory compressor to react; measuring current RAM
utilisation after each send; and aborting the sequence when the difference
between current RAM utilisation and the baseline exceeds a memory gate
threshold, thereby leaving the remaining processes suspended to prevent
a simultaneous memory re-expansion spike.

---

## 7. Abstract

A Multi-Dimensional Memory Intelligence Engine (MMIE) monitors a consumer
multitasking operating system using a kernel pressure oracle (`sysctl
kern.memorystatus_vm_pressure_level`), virtual memory anatomy parsing
(`vm_stat`), recursive process-tree genealogy attribution, and a
Multi-Model Adaptive Forecaster (MMAF) that concurrently fits linear,
quadratic, and exponential regression models to RAM utilisation history,
selecting the best fit by minimum residual sum of squares to compute
Time-to-Exhaustion (TTE). A Compression Efficiency Oracle (CEO) derives
a Compression Pressure Index (CPI) from compressed and purgeable page
counts as an independent measure of compressor headroom depletion. A
Multi-Signal Consensus Escalation Engine (MSCEE) combines six weighted
signals — RAM percentage, TTE, kernel oracle level, CPI, swap velocity,
and circadian hour pattern — into a quorum vote, adopting a remediation
tier only when the aggregate weight meets a consensus threshold (0.55),
replacing brittle two-signal max() selection. An Adaptive Threshold
Calibration Engine (ATCE) continuously self-tunes the Tier 2/3/4
activation thresholds from 30-day historical percentiles. A Circadian
Memory Pattern Engine (CMPE) learns hour-of-day RAM pressure profiles
from the metric cache and triggers proactive pre-emptive daemon suspension
before predictable high-pressure periods. A Thermal-Memory Coupling
Predictor (TMCP) learns the empirical relationship between CPU thermal
throttling and memory pressure via exponential moving average regression,
shortening TTE forecasts during active thermal throttle. A CPU-RAM
Conflict Resolution Gate prevents CPU priority restoration for processes
identified by genealogy as dominant RAM owners. Upon reaching elevated
pressure, the engine executes a four-tier cascade: observation, advisory
structural analysis, reversible genealogy-guided SIGSTOP suspension with
RSS Velocity Momentum Scoring (RVMS) velocity boost on freeze candidates,
and emergency SIGTERM termination. Suspended processes are restored via a
Graduated Thaw Sequencer (GTS) that delivers SIGCONT in ascending RSS
order with per-send gaps and a RAM-gate abort. An XPC Respawn Guard
blocklists launchd-managed services to prevent futile kill-loops. A
90-day SQLite metric store enables all historical analysis. The system
operates without superuser privileges and delivers real-time telemetry to
an installable Progressive Web Application dashboard. The invention
provides 18 patent claims covering adaptive forecasting, consensus
escalation, thermal coupling, circadian learning, velocity-momentum
scoring, graduated thaw, self-calibrating thresholds, and compression
awareness — none of which are present in prior consumer memory management
art.

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
vm_stat detail rows, Forecast Model row, CPI row, Swap Velocity row,
Thermal Coupling row, and memory families list with proportional bars.

**FIG. 8 — MMAF Three-Model Ensemble Diagram**
Side-by-side overlay of linear, quadratic, and exponential regression curves
fit to a 30-sample RAM utilisation window, with residual sum of squares values
annotated for each model, the winning model highlighted, and the extrapolation
to 95 % threshold showing the resulting TTE countdown value.

**FIG. 9 — MSCEE Six-Signal Quorum Flowchart**
Voting diagram showing the six signals (S1–S6) with their weights, each
independently computing a candidate tier, feeding into a weighted-sum column
for candidate tiers 4→1, with the quorum threshold (0.55) indicated as a
horizontal line and the adopted tier highlighted where the sum first crosses it.

**FIG. 10 — ATCE Self-Calibration Timeline**
Time-series graph of historical mem_pct samples over 30 days with the 75th,
85th, and 93rd percentile lines overlaid, alongside a side panel showing how
the Tier 2/3/4 thresholds shift from static defaults to calibrated values
as the cache accumulates data.

**FIG. 11 — GTS Graduated Thaw Sequence Diagram**
Sequence diagram showing five frozen processes sorted by RSS ascending;
SIGCONT delivered sequentially with 2 s gaps; RAM utilisation measured
after each send; the RAM-gate abort path indicated when RAM rises > 5 %
from baseline; and the final state (some processes thawed, some still frozen).

---

## 9. Enablement

The invention is fully enabled by the reference implementation:

- **Language:** Python 3.11+
- **Dependencies:** `psutil ≥ 5.9` (PyPI); all other imports are Python
  standard library (`subprocess`, `threading`, `http.server`, `json`, `math`,
  `sqlite3`, `collections`, `pathlib`)
- **Platform:** macOS 13 Ventura or later (Apple Silicon and Intel)
- **Deployment:** macOS LaunchAgent (`launchd`) for autostart at user login
- **Dashboard:** Progressive Web Application served at `http://127.0.0.1:8765`;
  installable via browser "Add to Dock" on macOS
- **Repository:** https://github.com/itsmeSugunakar/MAC_Perf_BOT

The complete source code constitutes the enablement disclosure. Key methods
and their locations in the reference implementation:

| Claim Element                    | Method                            | Module                   |
| -------------------------------- | --------------------------------- | ------------------------ |
| Kernel pressure oracle           | `_get_macos_pressure_level()`     | `app/performance_gui.py` |
| Memory anatomy parser            | `_parse_vm_stat()`                | `app/performance_gui.py` |
| Genealogy engine                 | `_build_memory_ancestry()`        | `app/performance_gui.py` |
| MMAF 3-model ensemble forecaster | `_compute_mem_forecast()`         | `app/performance_gui.py` |
| MSCEE 6-signal quorum escalation | `_compute_effective_tier()`       | `app/performance_gui.py` |
| CEO compression pressure index   | `_compute_compression_pressure()` | `app/performance_gui.py` |
| TMCP thermal TTE adjustment      | `_adjust_tte_for_thermal()`       | `app/performance_gui.py` |
| TMCP coupling coefficient EMA    | `_compute_thermal_coupling()`     | `app/performance_gui.py` |
| ATCE self-calibrating thresholds | `_calibrate_thresholds()`         | `app/performance_gui.py` |
| CMPE circadian profile + prefrez | `_check_circadian_pressure()`     | `app/performance_gui.py` |
| CMPE hour-of-day SQL aggregate   | `_build_circadian_profile()`      | `app/performance_gui.py` |
| CPU-RAM Conflict Resolution Gate | `_restore_calmed_procs()`         | `app/performance_gui.py` |
| Remediation cascade              | `_tiered_memory_remediation()`    | `app/performance_gui.py` |
| RVMS velocity momentum scorer    | `_get_process_velocity()`         | `app/performance_gui.py` |
| RVMS + genealogy freeze scoring  | `_freeze_background_daemons()`    | `app/performance_gui.py` |
| GTS graduated thaw sequencer     | `_thaw_frozen_daemons()`          | `app/performance_gui.py` |
| XPC Respawn Guard + blocklist    | `_detect_xpc_respawn()`           | `app/performance_gui.py` |
| 90-day metric history store      | `MetricsCache`                    | `app/performance_gui.py` |
| App performance prediction       | `_analyse_app_predictions()`      | `app/performance_gui.py` |

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
