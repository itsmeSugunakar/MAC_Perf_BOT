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
linear-regression-based exhaustion forecast, and executes a reversible,
four-tier remediation cascade to prevent system memory exhaustion without
requiring user intervention or elevated (superuser) privileges.

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
   threshold (95 %) — enabling *predictive* rather than purely *reactive*
   intervention.

5. **A Four-Tier Adaptive Remediation Cascade** that selects and executes
   an appropriate automated intervention from a graduated set of actions,
   each chosen to be the minimum necessary intervention for the observed
   pressure level, and each designed to be fully reversible where possible.

6. **An Autonomous Restoration Loop** (Auto-Thaw) that monitors pressure
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

```
┌────────────────────────────────────────────────────────────┐
│  BotEngine (background thread, 1 Hz)                       │
│                                                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 1. _collect()          — psutil CPU/RAM/Swap/procs  │   │
│  │ 2. _check_cpu()        — renice CPU hogs            │   │
│  │ 3. _check_memory()     — tier 1 + MMIE cascade      │   │
│  │ 4. _update_pressure_and_forecast()  (every 5 s)     │   │
│  │    ├─ _get_macos_pressure_level()  — sysctl oracle  │   │
│  │    ├─ _parse_vm_stat()             — memory anatomy │   │
│  │    ├─ _compute_mem_forecast()      — OLS regression │   │
│  │    └─ _build_memory_ancestry()    (every 120 s)     │   │
│  │ 5. _tiered_memory_remediation()   (at Tier 2+)      │   │
│  │    ├─ Tier 2: advisory + genealogy report           │   │
│  │    ├─ Tier 3: _freeze_background_daemons() SIGSTOP  │   │
│  │    └─ Tier 4: _sweep_idle_services() SIGTERM        │   │
│  │ 6. _thaw_frozen_daemons()         (on recovery)     │   │
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
- It reflects the kernel's *actual* ability to satisfy new allocation
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

| Category   | Meaning                                                    |
|------------|------------------------------------------------------------|
| Wired      | Kernel-reserved pages; cannot be paged, compressed, or purged |
| Active     | Pages in active use by running processes                   |
| Inactive   | Pages no longer actively referenced; reclaimable           |
| Purgeable  | Application-marked pages that can be discarded without data loss |
| Compressed | Pages compressed in-memory by the OS compressor            |
| Free       | Immediately available pages                                |

Page counts are multiplied by the system's page size (16 KB on Apple Silicon,
4 KB on Intel) to produce values in megabytes.

**Novelty over prior art:** Existing tools present a single "used %"
figure. The anatomy parser enables the MMIE to distinguish between
*structurally unavoidable* pressure (high wired memory) and *recoverable*
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
  { "app": "Code",           "mb": 2579, "pct": 26.0 },
  { "app": "Slack",          "mb":  299, "pct":  3.0 }
]
```

**Cycle prevention:** The walker maintains a `visited` set per traversal
to prevent infinite loops caused by reparented or malformed process entries.

**Novelty:** The recursive ppid-tree walk for *consumer workstation*
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
- `TTE = 0`  → Memory already at or above critical threshold.
- `TTE > 0`  → System will reach 95 % RAM in approximately `TTE` minutes
  at the current growth rate.

The forecaster is evaluated every 5 seconds. Its output is:
- Displayed in the dashboard as a countdown ("↑ ~12 min to 95%")
- Optionally used to escalate tier thresholds earlier under a rising trend

**Novelty:** Applying linear regression to a sliding historical window to
produce a human-readable "Time to Exhaustion" countdown for consumer RAM
management — and surfacing this in real time in a dashboard — constitutes
a novel combination not found in prior consumer-facing tools.

### 5.6 Component 5 — Four-Tier Adaptive Remediation Cascade

**Method:** `_tiered_memory_remediation(mem_pct: float)`

The cascade applies the *minimum necessary intervention* for the observed
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

#### Tier 3 — Reversible Process Suspension (≥ 87 % RAM)

**Trigger:** `mem_pct ≥ MEM_TIER3_PCT` (default 87 %) AND
`time.time() − _last_freeze ≥ FREEZE_COOL_S` (default 120 s cooldown)

**Actions:**

Invoke `_freeze_background_daemons()`:

1. Enumerate all running processes via `psutil.process_iter()`.
2. Filter to processes matching the `FREEZE_PATTERNS` allowlist — a
   curated set of background daemon name patterns known to be safe for
   temporary suspension (e.g., photo analysis daemons, cloud sync agents,
   telemetry reporters, weather and news services).
3. Further filter to processes with `status ∈ {sleeping, idle}` (not
   actively handling a user request).
4. Exclude root-owned processes, system-critical processes (`PROTECTED`
   set), and processes already suspended.
5. Send `SIGSTOP` (signal 19) to each qualifying process. `SIGSTOP`
   unconditionally suspends execution without terminating the process or
   losing its memory state or open file descriptors.
6. Record each suspended process in `_frozen_pids: dict[int, tuple]`
   with its name, suspension timestamp, and RSS at time of suspension.

**Auto-Thaw (Restoration Loop — Component 6):** When RAM utilisation
subsequently drops below `MEM_WARN − 5 %` (default 75 %), the engine
automatically sends `SIGCONT` (signal 18) to all entries in `_frozen_pids`,
resuming their execution transparently, and clears the frozen set.

**Safety guarantees:**
- Only user-owned processes can be suspended without elevated privileges.
  The engine makes no attempt to suspend root-owned processes.
- The `FREEZE_PATTERNS` allowlist is the primary safety mechanism;
  processes not matching any pattern are never targeted.
- The 120-second cooldown prevents repeated freeze cycles from disrupting
  system usability.

**Reversibility:** Fully reversible via `SIGCONT`. Process state, memory,
and file descriptors are fully preserved during suspension.

#### Tier 4 — Emergency Termination (≥ 92 % RAM)

**Trigger:** `mem_pct ≥ MEM_TIER4_PCT` (default 92 %)

**Actions:**

Invoke `_sweep_idle_services()`:

1. Enumerate processes matching `IDLE_SERVICE_PATTERNS` — XPC helpers,
   widget extensions, wallpaper video services, Siri inference services,
   etc.
2. Further filter to: user-owned, not in `PROTECTED` or `NEVER_TERMINATE`
   sets, CPU usage = 0, status = sleeping/idle, RSS ≥ 15 MB.
3. Send `SIGTERM` to qualifying processes. These are XPC services that
   `launchd` will re-spawn on demand when next needed.
4. Accumulate freed RSS into the session `freed_mb` counter.

**Reversibility:** Services terminated at Tier 4 are re-launched on demand
by the OS service manager (`launchd`). This is a standard macOS service
lifecycle pattern; it does not result in data loss.

**Irreversibility caveat:** Unlike Tier 3, Tier 4 terminates processes.
Any in-flight work within the terminated service is lost. The `PROTECTED`
and `NEVER_TERMINATE` sets, combined with the `IDLE_SERVICE_PATTERNS`
allowlist, ensure only services with no active user-facing work are targeted.

### 5.7 Component 6 — Autonomous Restoration Loop (Auto-Thaw)

**Method:** Called from `_check_memory()` on every memory check cycle.

**Logic:**
```python
if vm.percent < MEM_WARN - 5 and self._frozen_pids:
    self._thaw_frozen_daemons()
```

When the condition is met:
1. Iterate `_frozen_pids`.
2. Send `SIGCONT` to each suspended PID.
3. Clear `_frozen_pids`.
4. Emit a "pressure normalised — thawed N daemons" FIX event to the log.

This loop ensures that Tier 3 suspensions are temporary and self-healing,
making the overall system behaviour non-destructive across its entire
operating range.

### 5.8 Threshold Configuration

All thresholds are defined as named constants at the top of the engine
module and can be modified by the operator without source code changes to
business logic:

| Constant              | Default | Description                              |
|-----------------------|---------|------------------------------------------|
| `MEM_WARN`            | 80 %    | Tier 1 activation threshold              |
| `MEM_TIER2_PCT`       | 82 %    | Tier 2 activation threshold              |
| `MEM_TIER3_PCT`       | 87 %    | Tier 3 activation threshold              |
| `MEM_TIER4_PCT`       | 92 %    | Tier 4 activation threshold              |
| `WIRED_WARN_PCT`      | 40 %    | Wired structural pressure threshold      |
| `FREEZE_COOL_S`       | 120 s   | Minimum interval between Tier 3 cycles   |
| `MEM_ANCESTRY_COOL_S` | 120 s   | Minimum interval between genealogy scans |
| `LEAK_RATE_MB_MIN`    | 50 MB/m | RSS growth rate to flag potential leak   |

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

**Claim 5 (System):**
A system for automated memory resource management comprising: a monitoring
thread executing at a polling interval of approximately 1 Hz; a kernel
pressure oracle; a virtual memory anatomy parser; a process genealogy engine
performing recursive ppid-chain traversal; a linear-regression forecasting
module; a four-tier remediation cascade module; an autonomous restoration
loop; and a co-located HTTP server serving telemetry as JSON to a browser-
based Progressive Web Application.

**Claim 6 (Unprivileged Operation):**
The system of Claim 5, wherein all monitoring and remediation operations are
performed without superuser (root) privileges, relying exclusively on signals
(SIGSTOP, SIGCONT, SIGTERM) directed at user-owned processes and read-only
system call interfaces.

---

## 7. Abstract

A Multi-Dimensional Memory Intelligence Engine (MMIE) monitors a consumer
multitasking operating system using a kernel pressure oracle, virtual memory
anatomy parsing, recursive process-tree genealogy attribution, and linear-
regression exhaustion forecasting. Upon detecting elevated memory pressure,
the engine executes a four-tier adaptive remediation cascade: observation,
advisory analysis, reversible process suspension via SIGSTOP, and emergency
termination of idle services. Suspended processes are automatically restored
via SIGCONT when pressure normalises. The entire system operates without
superuser privileges and is implemented as an always-on background process
with telemetry delivered to an installable Progressive Web Application
dashboard. The invention provides predictive, graduated, reversible memory
management for consumer operating systems, addressing deficiencies in
existing reactive, flat, and binary approaches.

---

## 8. Brief Description of Drawings

The following drawings should accompany the non-provisional application:

**FIG. 1 — System Architecture Diagram**
Block diagram showing the BotEngine thread, MMIE sub-components, HTTP
server, and PWA dashboard, with data-flow arrows indicating the 1 Hz
polling cycle and JSON telemetry path.

**FIG. 2 — Four-Tier Cascade Flowchart**
Decision flowchart beginning at "RAM utilisation check," branching at each
tier threshold (80 %, 82 %, 87 %, 92 %), showing the specific actions at
each tier and the Auto-Thaw recovery path.

**FIG. 3 — Memory Genealogy Tree**
Illustrative process tree showing a root application (e.g., "Microsoft Edge")
with child renderer processes, GPU helper, XPC services, and network service,
all attributed to the root with aggregated RSS.

**FIG. 4 — Linear Regression Forecast Diagram**
Time-series graph of RAM utilisation samples with the OLS regression line
overlaid, showing the projected intersection with the 95 % threshold and
the resulting TTE value.

**FIG. 5 — PWA Dashboard Screenshot**
Annotated screenshot of the Memory Intelligence panel showing the arc gauge,
memory composition bar, vm_stat detail rows, and memory families list with
proportional bars.

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

| Claim Element              | Method                          | Module                  |
|----------------------------|---------------------------------|-------------------------|
| Kernel pressure oracle     | `_get_macos_pressure_level()`   | `app/performance_gui.py`|
| Memory anatomy parser      | `_parse_vm_stat()`              | `app/performance_gui.py`|
| Genealogy engine           | `_build_memory_ancestry()`      | `app/performance_gui.py`|
| Exhaustion forecaster      | `_compute_mem_forecast()`       | `app/performance_gui.py`|
| Remediation cascade        | `_tiered_memory_remediation()`  | `app/performance_gui.py`|
| Tier 3 suspension          | `_freeze_background_daemons()`  | `app/performance_gui.py`|
| Auto-Thaw restoration loop | `_thaw_frozen_daemons()`        | `app/performance_gui.py`|

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

*Prepared by: itsmeSugunakar · 2026-04-05*
*This document is a technical specification for a Provisional Patent
Application. It does not constitute legal advice. For formal patent
prosecution, consult a registered USPTO patent attorney or agent.*
