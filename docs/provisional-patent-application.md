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

**Statistical justification for percentile selection:**

The three percentile values are chosen for distinct, technically motivated
statistical reasons grounded in the empirical characteristics of memory
pressure distributions on consumer systems:

- **75th percentile → Tier 2 (advisory):** Under a normal approximation
  of the historical RAM distribution N(μ, σ²), the 75th percentile
  corresponds to μ + 0.674σ. Activating the advisory Tier 2 at this point
  means the engine intervenes for only the upper quartile of historically
  observed readings — matching the semantic intent of "elevated but not
  yet critical." No SIGSTOP or SIGTERM is issued at Tier 2; only advisory
  events and purgeable-memory hints are emitted.

- **85th percentile → Tier 3 (suspension):** The 85th percentile
  corresponds to μ + 1.036σ — readings more than one standard deviation
  above the system's normal operating point. Tier 3 issues SIGSTOP to
  background daemons, a reversible but impactful OS action. Anchoring
  this tier at the one-sigma boundary limits irreversible-state operations
  to genuinely anomalous pressure states, not routine elevated readings.

- **93rd percentile → Tier 4 (emergency termination):** The 93rd
  percentile corresponds to μ + 1.476σ — readings in the top 7% of the
  system's operational history. Tier 4 issues SIGTERM to idle XPC services,
  an irreversible action. The 93rd percentile threshold ensures this fires
  only under rare, severe, sustained pressure, consistent with emergency
  classification semantics.

**Sanity guard (formal specification):**

```
ACCEPT calibration if and only if:
  60.0 ≤ tier2 ≤ 92.0          # lower bound prevents over-eager intervention;
                                 # upper bound preserves Tier 4 headroom
  AND tier2 < tier3 < tier4     # strict monotonicity required
  AND (tier4 - tier2) ≥ 1.0     # minimum 1 pp spread across all three tiers

REJECT otherwise → retain previous _cal_thresholds or static defaults
```

**Physical-state-modification causal chain:**

ATCE is not a display or advisory function. Its output directly modifies
physical OS process states through the following unbroken causal chain:

```
(1) Historical RAM distribution → 30-day SQLite percentile query
(2) tier2/tier3/tier4 float values → _cal_thresholds dict mutation
(3) _cal_thresholds → S1 tier-vote boundary in _compute_effective_tier()
(4) S1 tier vote → MSCEE quorum weighted-sum computation
(5) MSCEE quorum result → effective_tier ∈ {0, 1, 2, 3, 4}
(6) effective_tier ≥ 3 → _freeze_background_daemons() called
(7) _freeze_background_daemons() → os.kill(pid, signal.SIGSTOP)
(8) SIGSTOP delivery → OS scheduler suspends process; removes from run queue
(9) Suspended process releases active memory pages → kernel reclaims RAM
(10) mem_pct decreases → next MSCEE quorum produces lower effective_tier
```

Steps 8–10 constitute a measurable, physical change in OS resource state:
process execution is halted, RSS pages are reclaimed by the kernel memory
manager, and system RAM utilisation decreases. This is not a mathematical
result stored in a variable — it is a change in the OS process scheduler's
run queue and the kernel virtual memory manager's page accounting.

**Empirical validation from reference deployment (2026-04-13):**

The following measurements were taken from a 22.8-hour live session on a
17.2 GB Apple Silicon Mac (macOS, 17,032 cache rows):

| Tier | Static default | ATCE-calibrated | Delta |
|------|---------------|-----------------|-------|
| Tier 2 | 82.0% | **78.0%** | −4.0 pp |
| Tier 3 | 87.0% | **79.7%** | −7.3 pp |
| Tier 4 | 92.0% | **80.7%** | −11.3 pp |

The system's 24-hour average RAM utilisation was 73.0%, with a 99th
percentile of approximately 80.5%. The static 82% Tier 2 threshold would
have remained unbreached throughout the session (machine never reached 82%),
producing **zero** automated remediation actions. With ATCE calibration:

- **66** autonomous Tier 2+ actions were executed
- **3,524 MB** of physical RAM was reclaimed by the OS kernel
- **1** background daemon was suspended via SIGSTOP (frozen_count=1)
- **17** PIDs were flagged as potential memory leaks

This constitutes a definitive empirical proof that ATCE's mathematical output
(percentile values) caused a change in physical computer resource state
(RAM reclamation) that would not have occurred using static threshold values.

**Novelty:** Continuous self-calibration of memory pressure tier thresholds
from historical cache percentiles, with threshold values grounded in the
known statistical relationship between order statistics and the normal
distribution, and with an unbroken causal chain from mathematical output
to OS-level physical process state modification, is a novel self-tuning
mechanism not found in any prior consumer or enterprise memory management
tool.

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

## 5.29 — Subject-Matter Eligibility Under 35 U.S.C. § 101
### Alice/Mayo Two-Step Analysis

This section preemptively addresses potential § 101 rejections under the
USPTO's 2019 Revised Guidance on Subject-Matter Eligibility (84 Fed. Reg.
50, Jan. 7, 2019), applying the Alice/Mayo two-step framework to the claims
of this application.

---

### Step 2A, Prong 1 — Identification of Abstract Elements

The following abstract elements are present in the claims and must be
"integrated into a practical application" to survive eligibility review:

| Element | Claim(s) | Abstract category |
|---------|----------|-------------------|
| Percentile computation (ATCE) | 14 | Mathematical concept |
| Z-score computation (SIE) | 19 | Mathematical concept |
| Weighted sum / quorum (MSCEE) | 13 | Mathematical concept |
| EMA weight update (RWA) | 21 | Mathematical concept |
| Softmax / cross-entropy (CDA) | 28 | Mathematical concept |
| Markov probability (PSM) | 26 | Mental process analog |
| Beta posterior update (BRL) | 27 | Mathematical concept |
| Coefficient-of-variation (CTRE) | 23 | Mathematical concept |
| Recursive RSS summation (AIP) | 24 | Mathematical concept |

Each of these elements, taken in isolation, could be characterised as
"mathematical concepts" under Alice Step 2A Prong 1. However, under
*Prong 2*, each is integrated into a practical application as shown below.

---

### Step 2A, Prong 2 — Integration into Practical Application

Each abstract element is integrated into the practical application of
**autonomous, reversible OS-level memory resource management** — a concrete
technical problem with measurable physical effects. The integration argument
for each engine is as follows:

**ATCE (Claim 14) — percentile computation:**
The percentile formula is not computed for its own sake. Its output
(`tier2`, `tier3`, `tier4` floating-point values) is written to
`_cal_thresholds` and immediately consumed as the S1 tier-vote boundary
in `_compute_effective_tier()`. This determines whether `os.kill(pid,
SIGSTOP)` is called. The mathematical result is the trigger condition for a
physical OS signal — a paradigmatic "integration into a practical
application" under *Enfish v. Microsoft* (Fed. Cir. 2016).

**SIE (Claim 19) — z-score computation:**
The z-score is not displayed or logged. Its output (a confidence scalar)
is multiplied into the ACN signal weight before the MSCEE quorum, altering
whether a Tier 3 or Tier 4 remediation fires. The formula directly
modulates OS process management decisions.

**MSCEE (Claim 13) — weighted quorum:**
The weighted sum is the gate condition for SIGSTOP/SIGTERM delivery. No
OS signal is sent unless the weighted vote exceeds 0.55. This is a specific,
unconventional technical mechanism — not a generic "decide whether to act"
mental process — as required by *McRO v. Bandai Namco* (Fed. Cir. 2016).

**RWA (Claim 21) — EMA weight update:**
The EMA formula updates `_acn_weights`, which are consumed by ACN on every
3-second MSCEE evaluation cycle. The formula produces a non-generic, dynamic
data structure that evolves based on real-time OS measurement outcomes —
directly distinguishable from the static lookup tables in prior art memory
managers. Under *Berkheimer v. HP* (Fed. Cir. 2018), the unconventional
nature of this adaptive weight structure creates a genuine factual dispute
precluding summary § 101 rejection.

**CDA (Claim 28) — softmax / cross-entropy:**
The softmax output is not a recommendation to a human. It is the branching
condition for three distinct OS-level interventions:
- "compressor_collapse" → boosts S4 ACN weight, increases SIGSTOP likelihood
- "leak" → elevates leak PIDs in RVMS freeze queue, causing SIGSTOP priority shift
- "cpu_collision" → activates CPU-RAM lock, preventing CPU nice(0) calls

Under *Amdocs v. Openet Telecom* (Fed. Cir. 2016), a computer system that
achieves a technical result in a distributed computing environment (here: OS
process management) in a specific, unconventional way passes Step 2A Prong 2.

**PSM (Claim 26) — Markov probability:**
The predicted next tier is used to pre-position the remediation cascade —
pre-allocating the RVMS scoring table and pre-evaluating the GTS thaw
gate before the tier transition occurs. This reduces latency between
pressure detection and SIGSTOP delivery — a direct improvement to computer
responsiveness.

**BRL (Claim 27) — Beta posterior:**
When `brl_confidence < 0.2`, the system suppresses autonomous Tier 3/4
actions pending additional signal corroboration. This prevents false-positive
SIGSTOP delivery — a safety-critical physical state protection. The posterior
computation directly governs whether irreversible OS actions are taken.

---

### Step 2B — "Significantly More" Than the Abstract Idea

Even if a claim is found directed to an abstract idea, it is eligible if
the additional elements amount to "significantly more." The following elements
constitute significantly more:

| Element | Why "significantly more" |
|---------|--------------------------|
| Single `psutil.process_iter()` scan per second | Specific, unconventional hot-path architecture not present in prior art (proved by performance table in §10) |
| 90-day SQLite feedback store with `remediation_outcomes` + `signal_weights` tables | Non-generic, purpose-built data structure enabling the RWA/RAC/ATCE/BRL feedback loops |
| SIGSTOP/SIGCONT reversible suspension with GTS RSS-ascending ordered thaw | Novel, unconventional OS signalling protocol not present in any identified prior art |
| Five-layer engine separation (SIE → Model → Consensus → Action → CDA) | Specific architectural structure providing unconventional "integration into practical application" |
| ASZM dynamic protection set (133 processes, empirically measured) | Non-generic safety mechanism that prevents erroneous SIGTERM to previously unidentified system processes |
| Unprivileged operation (no superuser required) | Technically significant constraint distinguishing from OOM Killer and privileged cleaners |

**Key precedents supporting eligibility:**

- *Enfish v. Microsoft Corp.*, 822 F.3d 1327 (Fed. Cir. 2016): Software claims
  eligible when directed to a specific improvement in computer functionality
  itself. ATCE, SIE, and RWA each improve the computer's own memory management
  efficiency — not merely performing known operations on a computer.

- *McRO v. Bandai Namco Games America*, 837 F.3d 1299 (Fed. Cir. 2016):
  A specific, rule-based technical method that produces a non-conventional
  result is eligible. MSCEE's six-signal quorum with per-signal weight
  adjustment via SIE is precisely this — a specific technical rule, not a
  generic "decision function."

- *Berkheimer v. HP Inc.*, 881 F.3d 1360 (Fed. Cir. 2018): Whether
  additional claim elements are "well-understood, routine, and conventional"
  is a factual question that cannot be resolved on the pleadings. The ACN
  adaptive weight structure, ASZM dynamic protection mapping, and RAC
  outcome-delayed evaluation loop are all non-conventional; they do not
  appear in any prior consumer OS management tool identified in §3.2.

- *Core Wireless Licensing v. LG Electronics*, 880 F.3d 1356 (Fed. Cir.
  2018): Improved user interface displaying information in a specific manner
  eligible. The MAC Performance Bot's PWA dashboard, which displays BRL
  confidence, PSM next-tier predictions, and CDA root-cause diagnosis in
  a real-time 1 Hz feed, constitutes an improved computer interface for
  system operators.

---

### Physical Improvement Summary Table

The following table summarises the physical computer state improvements
achieved by the claimed system, providing the "concrete benefit" required
by the USPTO's January 2019 guidance:

| Claim | Physical improvement | Measured evidence |
|-------|---------------------|-------------------|
| ATCE (14) | RAM freed by enabling 66 Tier 2+ actions | 3,524 MB reclaimed over 22.8 h |
| MSCEE (13) | Prevented false escalations via quorum | 0.907 weighted agreement on Tier 2 |
| SIE (19) | Prevented false escalations from glitches | Confidence 0.995 (all signals clean) |
| ASZM (27) | Prevented erroneous SIGTERM | 133 processes protected beyond static list |
| CDA (28) | Correct root-cause routing | compressor_collapse at 52–98% conf. |
| PSM (26) | Tier 3 predicted before occurrence | Next=3, dwell=3.9 s; consistent with TTE=1.6 min |
| GTS (18) | Prevented memory spike during thaw | RAM-gate abort mechanism |
| ATCE+MSCEE | Reduced OS paging and compressor load | CPI monitored; Tier 2 activation at 78% vs. 82% static |

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
said historical distribution, wherein said percentile values correspond
to approximately μ+0.674σ, μ+1.036σ, and μ+1.476σ of the observed
distribution respectively, calibrating the advisory, suspension, and
emergency tier boundaries to the statistical characteristics of the
specific system; substituting said percentile values as the activation
thresholds for the second, third, and fourth remediation tiers respectively,
wherein said substitution directly alters the tier-vote boundary of the
RAM-percentage signal in a weighted multi-signal quorum; and repeating
said calibration at a periodic interval, thereby continuously adapting the
conditions under which the system transmits SIGSTOP or SIGTERM signals to
operating-system processes, causing a change in the OS process scheduler
state and a reduction in the quantity of resident memory pages allocated
by the kernel memory manager.

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
| SIE signal integrity estimation  | `_compute_signal_confidence()`    | `app/performance_gui.py` |
| MEG meta-weight governance       | `_compute_mem_forecast()` (MEG)   | `app/performance_gui.py` |
| ACN adaptive consensus           | `_compute_effective_tier()` (ACN) | `app/performance_gui.py` |
| RWA reinforcement weight update  | `_update_rwa_weights()`           | `app/performance_gui.py` |
| CTRE chronothermal regression    | `_compute_ctre()`                 | `app/performance_gui.py` |
| AIP ancestral impact propagation | `_compute_aip()`                  | `app/performance_gui.py` |
| RAC action recording             | `_record_rac_action()`            | `app/performance_gui.py` |
| RAC outcome evaluation           | `_evaluate_rac_outcomes()`        | `app/performance_gui.py` |
| PSM Markov tier prediction       | `_update_psm()` / `_psm_predict()`| `app/performance_gui.py` |
| BRL Bayesian tier confidence     | `_update_brl()` / `_compute_brl_confidence()` | `app/performance_gui.py` |
| ASZM dynamic protection mapping  | `_update_aszm()`                  | `app/performance_gui.py` |
| CDA causal root-cause diagnosis  | `_diagnose_root_cause()`          | `app/performance_gui.py` |
| CDA model training               | `_cda_train_model()`              | `app/performance_gui.py` |

---

## 5.18 — Signal Integrity Estimator (SIE)

The SIE validates the reliability of each raw monitoring signal before it enters the consensus pipeline. For each signal (CPU %, RAM %, Swap %), a rolling z-score is computed over a configurable window (`SIE_WINDOW = 30` samples).

**Complete mathematical specification:**

```
# Rolling statistics over window W of size SIE_WINDOW (30):
μ_w = (1/|W|) × Σ_{x_i ∈ W} x_i
σ_w = sqrt((1/|W|) × Σ_{x_i ∈ W} (x_i − μ_w)²)

# Z-score for current sample x_t:
z_t = (x_t − μ_w) / (σ_w + ε)       # ε = 1e-9 prevents division by zero

# Raw confidence (anomaly dampening):
confidence_raw = 1.0             if |z_t| ≤ SIE_ZSCORE_THRESH (3.0)
confidence_raw = max(0.5,
  1.0 − |z_t| / 10.0)           if |z_t| > 3.0

# EMA smoothing (prevents rapid oscillation):
confidence_t = 0.9 × confidence_{t-1} + 0.1 × confidence_raw
# Result: confidence_t ∈ [0.5, 1.0]
```

A confidence of 1.0 indicates a well-behaved signal; 0.5 indicates maximum
anomaly dampening. The EMA time constant (0.9 / 0.1) requires approximately
9 ticks to respond to a sustained anomaly — matching the 1 Hz collection
rate and preventing single-sample spikes from degrading signal weight.

This Layer 1 gate prevents transient sensor glitches — kernel scheduler
bursts, context-switch storms, psutil measurement races — from propagating
as false tier escalations through Layers 2–5.

## 5.19 — Model Ensemble Governance (MEG)

MEG augments the MMAF by maintaining a rolling history of per-model residual
sums of squares over `MEG_RESIDUAL_HISTORY = 5` epochs.

**Complete mathematical specification:**

```
# After each MMAF fitting cycle, append residual to model history:
residual(m) = Σ_{i=1}^{N} (w_i − predict_m(i))²   for m ∈ {L, Q, E}
residual_history[m].append(residual(m))             # deque maxlen=5

# MEG score (mean historical residual):
meg_score(m) = (1/K) × Σ_{k=1}^{K} residual_history[m][k]   # K ≤ 5

# MEG winner (minimum mean historical residual):
winner_MEG = argmin_{m ∈ {L, Q, E}} meg_score(m)
```

If `meg_score` values are tied or `residual_history` is insufficient
(< MEG_RESIDUAL_HISTORY samples), MEG falls back to the instantaneous
MMAF winner (minimum current residual). MEG winner governs `_last_forecast_model`
and the TTE value surfaced in the `/stats` API.

## 5.20 — Adaptive Consensus Network (ACN) with SIE Integration

ACN replaces the static weight dictionary in MSCEE with a dynamic, RWA-updated
weight map (`_acn_weights`).

**Complete mathematical specification:**

```
# At each _compute_effective_tier() call:
adj_weight[s] = acn_weight[s] × sie_confidence[s]   for s ∈ {S1..S6}

# Renormalisation (prevents degraded signals from inflating relative weight):
total_adj = Σ_s adj_weight[s]
norm_weight[s] = adj_weight[s] / total_adj

# Quorum uses norm_weight[s] in place of static weight[s]:
weighted_vote(candidate_tier) = Σ_{s: signal_tier(s) ≥ candidate_tier} norm_weight[s]
```

This closes the feedback loop: SIE anomaly detection (Layer 1) directly
modulates the quorum weights used for tier escalation (Layer 3), without any
intermediate human intervention.

## 5.21 — Reinforcement-Weighted Arbitration (RWA)

RWA implements a closed reinforcement-learning loop over the MSCEE signal
weighting.

**Complete mathematical specification:**

```
# Hourly accuracy query from remediation_outcomes table:
accuracy(s) = COUNT(outcomes where signal_s voted correctly AND success=1)
              / COUNT(all outcomes in last RWA_OUTCOMES_H hours)

# Normalise so accuracies sum to 1.0:
total_acc = Σ_{s=S1}^{S6} accuracy(s)
accuracy_norm(s) = accuracy(s) / (total_acc + ε)

# EMA weight update (α = RWA_LEARN_RATE = 0.05):
new_weight(s) = (1 − α) × acn_weight(s) + α × accuracy_norm(s)

# Weight floor (no signal silenced):
new_weight(s) = max(new_weight(s), RWA_MIN_WEIGHT = 0.02)

# Re-normalise to ensure Σ new_weight(s) = 1.0:
total_new = Σ_s new_weight(s)
acn_weight(s) ← new_weight(s) / total_new
```

**Empirical weight drift observed (22.8-hour session):**

| Signal | Initial | Live | Drift | Interpretation |
|--------|---------|------|-------|----------------|
| S1 RAM% | 0.3000 | 0.2870 | −0.013 | RAM% less predictive of success |
| S4 CPI | 0.1200 | 0.1245 | +0.005 | CPI more predictive of success |
| S6 Circadian | 0.0500 | 0.0614 | +0.011 | Circadian timing predicts outcomes |

Over time, signals that consistently precede successful remediations gain
weight; unreliable signals are downweighted without being eliminated.

## 5.22 — Chronothermal Regression Engine (CTRE)

CTRE computes a per-hour-of-day stability score for the joint thermal-memory state.

**Complete mathematical specification:**

```
# Per-hour query (SQLite aggregate):
SELECT (ts/3600) % 24 AS hour,
       AVG(mem_pct)              AS mu_mem_h,
       AVG((100-thermal_pct))    AS mu_therm_h,
       SUM((mem_pct-mu_mem_h)²)/COUNT(*) AS var_mem_h,   -- approximation
       SUM(((100-thermal_pct)-mu_therm_h)²)/COUNT(*) AS var_therm_h
FROM metrics WHERE ts > now − 30_days
GROUP BY hour

# Per-signal coefficient of variation (CV):
cv_mem_h   = sqrt(var_mem_h)   / (mu_mem_h   + ε)
cv_therm_h = sqrt(var_therm_h) / (mu_therm_h + ε)

# Joint instability (memory weighted 70%, thermal 30%):
instability_h = 0.7 × cv_mem_h + 0.3 × cv_therm_h

# Stability score (clipped to [0, 1]):
stability_h = max(0.0, min(1.0, 1.0 − instability_h))
```

Hours with `stability_h < 0.5` are flagged as volatile and emitted as INFO
events. The stability map is fed into ACN as a contextual bias for hour-of-day
consensus weighting.

**Empirical stability map (22.8-hour session):**

| Hour range | Stability range | Pattern |
|------------|----------------|---------|
| 06:00–13:00 | 0.963–0.965 | Most predictable (regular work start) |
| 19:00–20:00 | 0.859–0.885 | Most volatile (evening mixed workload) |
| 00:00–05:00 | 0.881–0.947 | Stable overnight baseline |

## 5.23 — Ancestral Impact Propagation (AIP)

AIP extends the MMIE genealogy engine by computing a recursive family-tree
impact score for each root application process.

**Complete mathematical specification:**

```
# Process tree traversal (up to AIP_MAX_DEPTH = 3 levels):
family_rss(p) = own_rss(p) + Σ_{c ∈ children(p)} own_rss(c)   (depth ≤ 3)

# Depth factor (rewards deep process trees):
depth_factor(p) = 1.0 + 0.1 × child_count(p)

# Impact score:
impact_score(p) = (own_rss(p) / (family_rss(p) + ε)) × depth_factor(p)
# impact_score ∈ [0, depth_factor_max]; normalised to [0, 1] for display

# Cascade risk flag:
growth_rate(c) = (rss_c_now − rss_c_prev) / elapsed_s   [MB/s]
cascade_risk(p) = any(growth_rate(c) ≥ CDA_LABEL_LEAK / 60
                      for c ∈ children(p))
```

Families with `cascade_risk = True` trigger a WARN event and are elevated
in the freeze-scoring queue by the RVMS velocity multiplier.

## 5.24 — Reinforcement Action Coordinator (RAC)

RAC implements an outcome-delayed evaluation loop for all remediation actions.

**Complete mathematical specification:**

```
# At action time (tier ≥ 2):
pending_outcomes.append((
    eval_ts    = now() + RAC_EVAL_DELAY_S,   # 30 seconds later
    tier       = effective_tier,
    action     = action_type,                 # "freeze_daemon", "sweep_xpc", etc.
    pre_mem    = current_mem_pct
))

# At evaluation time (called every 1 s from _collect()):
for (eval_ts, tier, action, pre_mem) in pending_outcomes:
    if now() < eval_ts: continue
    post_mem   = _last_vm.percent
    delta_pct  = pre_mem − post_mem          # positive = RAM freed
    success    = 1 if delta_pct ≥ RAC_SUCCESS_PCT (2.0) else 0
    cache.record_outcome(tier, action, pre_mem, post_mem,
                         delta_mb, success)  # persisted to SQLite

# Action efficacy EMA update:
_action_efficacy[action] = 0.9 × _action_efficacy.get(action, 0)
                         + 0.1 × delta_pct
```

The 30-second evaluation delay is the minimum time for the macOS pager and
memory compressor to fully respond to a SIGSTOP or SIGTERM action before
the delta is measured.

## 5.25 — Predictive State Machine (PSM)

PSM models the sequence of `effective_tier` values as a discrete-time
Markov chain.

**Complete mathematical specification:**

```
# Transition recording (when tier changes AND dwell ≥ PSM_DWELL_MIN_S):
if (effective_tier ≠ prev_tier) AND (now() − tier_enter_ts ≥ 3.0):
    dwell = now() − tier_enter_ts
    transition_history.append((prev_tier, effective_tier, dwell))
    transition_matrix[(prev_tier, effective_tier)] += 1

# Transition probability (Markov):
P(next=j | current=i) = count[(i,j)] / Σ_k count[(i,k)]

# Next-tier prediction (argmax):
psm_next_tier = argmax_j P(next=j | current=effective_tier)
# Falls back to effective_tier if no outgoing transitions observed

# Dwell estimation (mean of observed dwells for origin tier i):
psm_dwell_s = mean({dwell_t : transition_t.from_tier = effective_tier})
```

**Empirical PSM output (2026-04-13):**
- Current tier: 2 → PSM predicted next tier: **3**
- Predicted dwell: **3.9 seconds** in Tier 3
- Consistent with simultaneous TTE = 1.6 min and CPI = 1.000

## 5.26 — Bayesian Reasoning Layer (BRL)

BRL wraps the MSCEE tier decision in a Bayesian posterior confidence estimate
using a Beta-Binomial conjugate model.

**Complete mathematical specification:**

```
# Prior initialisation:
α_t = BRL_PRIOR_ALPHA = 1.0   for each tier t ∈ {0, 1, 2, 3, 4}

# Hourly prior update (Beta-Binomial conjugate update):
count_t = SELECT COUNT(*) FROM metrics
          WHERE eff_tier = t AND ts > now − 30_days
α_t ← α_t + count_t                    # posterior alpha for tier t

# Likelihood at decision time (signal agreement fraction):
signals_agreeing = Σ_{s} 1[signal_tier(s) ≥ decided_tier]
L_t = signals_agreeing / 6.0            # fraction of 6 ACN signals agreeing

# Posterior (unnormalised Beta-Binomial product):
P*(t) = α_t × L_t

# Normalised posterior confidence:
brl_confidence = P*(decided_tier) / Σ_{t=0}^{4} P*(t)
# brl_confidence ∈ (0, 1]
```

The Beta prior is conjugate to the Binomial likelihood, giving a closed-form
posterior requiring no numerical integration. Low `brl_confidence` indicates
the decided tier is historically rare AND few signals agree — a double-weak
signal warranting dashboard warning.

**Empirical BRL (22.8-hour session):** `brl_confidence = 0.136` — low
because the 22.8-hour cache contains insufficient hourly tier-distribution
updates to produce strong prior counts. Expected to reach 0.4–0.7 after
7+ days of operation.

## 5.27 — Adaptive Safety Zone Mapping (ASZM)

ASZM continuously monitors running processes to identify system daemons
that must be protected from remediation even if absent from the static
`PROTECTED` set.

**Complete mathematical specification:**

```
# Per-process criticality score (computed hourly):
uptime_days   = (now() − process_create_time) / 86400.0
uptime_weight = min(uptime_days / 7.0, 1.0)      # saturates at 7 days

avg_cpu_pct   = mean(cpu_percent samples over last hour)
cpu_idle_weight = max(0.0, 1.0 − avg_cpu_pct / 5.0)  # near-zero CPU = 1.0

criticality = (uptime_weight + cpu_idle_weight) / 2.0  # ∈ [0.0, 1.0]

# Dynamic protection elevation:
if criticality ≥ ASZM_CRIT_SCORE (0.8):
    _dynamic_protected.add(process_name)

# Stale entry pruning:
_dynamic_protected = {name for name in _dynamic_protected
                      if name in {p.name() for p in psutil.process_iter()}}
```

A process must be both long-lived (uptime ≥ 7 days → uptime_weight = 1.0)
AND near-zero CPU (avg_cpu ≤ 1% → cpu_idle_weight = 0.8) to achieve
`criticality ≥ 0.8`. This dual condition prevents short-lived high-CPU
processes from being incorrectly protected.

**Empirical ASZM (22.8-hour session):** 133 processes added to
`_dynamic_protected` beyond the 23-process static `PROTECTED` set.

## 5.28 — Causal Diagnostic Agent (CDA)

CDA provides interpretable root-cause attribution for memory pressure events,
operating as a two-phase classifier whose output directly routes the
remediation cascade.

**Phase 1 — Rule-based classifier (cold start, until CDA_TRAIN_MIN_ROWS = 200):**

```
# Feature vector x = [cpu_pct/100, mem_pct/100, swap_pct/100, cpi, tier/4]

if cpi ≥ 0.60 AND tier ≥ 2:
    label = "compressor_collapse"
elif swap_velocity > 0 AND growth_rate_max ≥ CDA_LABEL_LEAK (50 MB/min):
    label = "leak"
elif cpu_throttle_count ≥ 1 AND tier ≥ 2:
    label = "cpu_collision"
else:
    label = "normal"
```

**Phase 2 — Trained softmax classifier (post 200 labeled rows):**

```
# Model: W ∈ ℝ^{4×5}, b ∈ ℝ^4   (4 classes, 5 features)

# Forward pass:
logits = W · x + b                           # shape (4,)
P(y=k|x) = exp(logits_k) / Σ_{j=0}^{3} exp(logits_j)   # softmax

# Training (SGD, CDA_EPOCHS = 100, CDA_LR = 0.01):
L = −(1/N) × Σ_{i=1}^{N} log P(y=y_i | x_i)            # cross-entropy loss

∇_W L = (1/N) × (P̂ − Y_onehot)ᵀ · X        # gradient w.r.t. W
∇_b L = (1/N) × Σ_i (P̂_i − Y_onehot_i)     # gradient w.r.t. b

W ← W − CDA_LR × ∇_W L
b ← b − CDA_LR × ∇_b L
```

**ONNX serialisation and system integration:**

When `onnx` and `onnxruntime` packages are present, the trained (W, b)
matrices are serialised to `cda_model.onnx` using `Gemm + Softmax` operators.
At inference time, an `onnxruntime.InferenceSession` executes the graph.
Without ONNX packages, the identical forward pass executes in pure Python.
The ONNX path is an optional performance optimisation — the inference
logic and its downstream effects are identical in both paths.

**Critical: CDA output directly routes the remediation cascade.** The
diagnosis is not an advisory metric. Every 3 seconds, when `effective_tier ≥ 2`,
`_diagnose_root_cause()` runs the inference and branches:

```
diagnosis = argmax P(y=k | x_current)

if diagnosis == "compressor_collapse":
    # Boost CPI signal weight for next MSCEE quorum:
    _acn_weights["s4"] = min(_acn_weights["s4"] × 1.1, 0.25)
    # Re-normalise ACN weights

if diagnosis == "leak":
    # Elevate leak PIDs to top of RVMS freeze queue:
    _leak_priority_pids |= {pid for pid, rate in _leak_rates.items()
                            if rate ≥ LEAK_RATE_MB_MIN}

if diagnosis == "cpu_collision":
    # Activate CPU-RAM conflict gate:
    _ram_pressure_lock = True

# Causal diagnosis surfaced in /stats API and dashboard:
self.causal_diagnosis = diagnosis
```

This branching constitutes the "practical application" required by Alice
Step 2A Prong 2: the mathematical output (argmax of softmax probabilities)
directly modifies OS-level remediation routing, signal weights, and process
targeting — all physical computer resource states.

---

## New Claims (v2.0 — Claims 19–28)

**Claim 19.** A computer-implemented system for autonomous resource management comprising: a Signal Integrity Estimator (SIE) that computes, for each of a plurality of monitoring signals, a rolling z-score over a fixed-size sample window, wherein the z-score is defined as the difference between the current sample and the window mean divided by the window standard deviation; a signal confidence value derived from the z-score by applying a monotonically decreasing function capped at a minimum floor value; and a mechanism for multiplying each signal's consensus weight by its corresponding confidence value prior to weighted-quorum tier escalation, thereby preventing transient OS measurement anomalies from generating erroneous operating-system process suspension signals.

**Claim 20.** The system of Claim 19, further comprising a Model Ensemble Governance (MEG) layer that maintains, for each of a plurality of regression models, a rolling history of per-model residual sums of squares over a configurable epoch window; computes a mean historical residual for each model; and selects as the governing forecast model the model with the minimum mean historical residual, thereby promoting the model that has been most consistently accurate over recent history rather than the model with the minimum instantaneous residual on potentially anomalous data.

**Claim 21.** The system of Claims 19–20, further comprising an Adaptive Consensus Network (ACN) wherein signal weights are dynamically updated by a Reinforcement-Weighted Arbitration (RWA) engine that: queries a persistent remediation outcome table to compute per-signal accuracy scores; normalises said accuracy scores to sum to unity; applies exponential moving average updates to each signal's weight using said normalised accuracy as the target; and enforces a minimum weight floor such that no signal's contribution is reduced to zero — wherein said weight updates directly modify the quorum vote totals that determine whether SIGSTOP or SIGTERM signals are dispatched to operating-system processes.

**Claim 22.** The system of Claims 19–21, wherein the RWA engine maintains a weight floor parameter such that no signal's contribution drops to zero, ensuring all signals retain non-zero influence in the consensus quorum, thereby preventing a single high-accuracy period from permanently silencing signals that may become critical under novel system conditions.

**Claim 23.** A computer-implemented method for chronothermal stability analysis comprising: querying a 30-day time-series database for per-hour mean and variance of memory utilisation and thermal throttle depth; computing a per-hour coefficient-of-variation stability score; identifying hours of day with stability below a threshold as volatile; and exposing the stability map to a downstream consensus network.

**Claim 24.** A computer-implemented method for ancestral impact propagation comprising: constructing a process parent-child tree from operating-system process metadata; recursively summing child process RSS contributions up to a configurable depth; computing an impact score weighted by tree depth; and flagging application families exhibiting child-process RSS growth rates exceeding a leak-rate threshold as cascade-risk families.

**Claim 25.** A computer-implemented reinforcement action coordination system comprising: recording, for each remediation action, a pre-action memory utilisation snapshot and an evaluation timestamp; measuring post-action memory utilisation after a configurable evaluation delay; computing a success indicator from the measured delta; and writing the outcome to a persistent store consumed by a weight-update engine.

**Claim 26.** A computer-implemented Markov tier prediction system comprising: recording, upon each change in effective remediation tier, a transition event comprising origin tier, destination tier, and dwell duration in the origin tier; maintaining a transition count matrix indexed by origin-destination tier pairs; computing, for the current tier, the transition probability to each candidate next tier as the count of observed transitions from the current tier to said candidate divided by the total count of all observed transitions from the current tier; predicting the most probable next tier as the argmax of said transition probabilities; and using said predicted next tier to pre-position the remediation cascade prior to tier transition, thereby reducing the latency between memory pressure detection and operating-system process suspension signal delivery.

**Claim 27.** A computer-implemented Bayesian reasoning system for resource escalation confidence comprising: maintaining, for each of a plurality of remediation tiers, a Beta prior count initialised to a weak prior value; updating said prior counts hourly from a historical tier-frequency distribution retrieved from a persistent store; computing, at each tier decision point, a likelihood value as the fraction of active monitoring signals whose individual tier votes agree with the decided tier; computing an unnormalised posterior for the decided tier as the product of its prior count and its likelihood; normalising said posterior across all tiers; and, when the resulting posterior confidence falls below a threshold, suppressing autonomous irreversible remediation actions pending additional signal corroboration, thereby preventing false-positive operating-system process termination.

**Claim 28.** A computer-implemented causal diagnostic system for memory pressure attribution comprising: assembling a feature vector from current system measurements comprising CPU utilisation, RAM utilisation, swap utilisation, compression pressure index, and effective remediation tier; classifying said feature vector using a softmax logistic regression model trained on historical cache rows labeled by deterministic threshold rules, wherein the model is defined by weight matrix W and bias vector b and inference computes class probabilities as the normalised exponential of W·x+b; and routing the remediation cascade based on the class with maximum probability: directing SIGSTOP priority to processes identified as leak sources when the diagnosis is "leak"; increasing the compression-efficiency signal weight in the multi-signal consensus quorum when the diagnosis is "compressor_collapse"; and activating the CPU-RAM conflict gate when the diagnosis is "cpu_collision" — wherein said routing constitutes a direct physical modification of operating-system process scheduling and memory management state.

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
