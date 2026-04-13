# Provisional Patent Application — Gap Analysis
## MAC Performance Bot v2.0.0 · Alice/Mayo Eligibility Review

**Prepared:** 2026-04-13
**Against:** `docs/provisional-patent-application.md`
**Based on:** Alice/Mayo Two-Step Test, 35 U.S.C. § 101, § 112 (PHOSITA standard)
**Status:** All 5 gaps resolved — see PPA §5.13, §5.18–5.29, Claims 14/19/21/26/27/28

---

## Summary of Gaps Identified and Resolved

| # | Gap | Severity | PPA location of fix |
|---|-----|----------|---------------------|
| 1 | ATCE: no statistical justification for 75/85/93rd percentile selection | HIGH | §5.13 |
| 2 | ATCE: no explicit physical-state-modification causal chain | HIGH | §5.13 |
| 3 | ATCE: no empirical validation with live deployment data | HIGH | §5.13 |
| 4 | §5.18–5.28 (SIE/MEG/RWA/BRL/PSM/CDA): prose-only, no mathematical formulas | HIGH | §5.18–5.28 |
| 5 | CDA §5.28: ONNX described as standalone module, not wired into remediation loop | MEDIUM | §5.28 |
| 6 | No § 101 Alice eligibility argument section | HIGH | §5.29 (new) |
| 7 | Claims 14, 19, 21, 26, 27, 28: "what" language; missing physical-state-change tail | HIGH | Claims section |

---

## Gap 1–3 — ATCE: Three Missing Elements

### What was added to §5.13

**Statistical justification (Gap 1):**
```
75th pct ≈ μ + 0.674σ  →  upper-quartile advisory zone
85th pct ≈ μ + 1.036σ  →  one-sigma anomaly; SIGSTOP warranted
93rd pct ≈ μ + 1.476σ  →  rare extreme; SIGTERM warranted
```

**Physical-state causal chain (Gap 2):**
```
percentile_query → _cal_thresholds → S1 tier-vote boundary →
MSCEE quorum → effective_tier → os.kill(SIGSTOP/SIGTERM) →
OS scheduler removes process → kernel reclaims RAM pages
```

**Empirical validation (Gap 3) from 22.8-hour live session:**

| Tier | Static | ATCE-calibrated | Impact |
|------|--------|-----------------|--------|
| Tier 2 | 82.0% | 78.0% (−4.0 pp) | Enabled 66 actions (vs 0 with static) |
| Tier 3 | 87.0% | 79.7% (−7.3 pp) | 1 daemon frozen |
| Tier 4 | 92.0% | 80.7% (−11.3 pp) | Emergency path enabled |
| **Total** | | | **3,524 MB** reclaimed |

---

## Gap 4 — Full Mathematical Formulas Added to §5.18–5.28

| Engine | Key formulas added |
|--------|-------------------|
| SIE (§5.18) | `z = (x−μ)/(σ+ε)`, `conf = max(0.5, 1−\|z\|/10)`, EMA smoothing |
| MEG (§5.19) | `meg_score(m) = mean(residual_history[m])`, `winner = argmin meg_score` |
| ACN (§5.20) | `adj_weight[s] = acn_weight[s] × sie_confidence[s]`, renormalisation |
| RWA (§5.21) | Full accuracy normalisation, EMA update `α=0.05`, floor `0.02`, re-normalise |
| CTRE (§5.22) | Joint CV: `instability = 0.7×cv_mem + 0.3×cv_therm`, stability clip |
| AIP (§5.23) | `impact = (own_rss/family_rss) × (1+0.1×child_count)`, cascade flag |
| RAC (§5.24) | `delta_pct = pre_mem − post_mem`, `success = delta ≥ 2.0%`, efficacy EMA |
| PSM (§5.25) | `P(j\|i) = count(i→j)/Σcount(i→k)`, `dwell = mean(observed_dwells_for_i)` |
| BRL (§5.26) | `α_t += count_t`, `L_t = signals_agreeing/6`, `conf = P*(t)/ΣP*(t)` |
| CDA (§5.28) | Feature vector, softmax `P(k\|x) = exp(logits_k)/Σexp`, SGD update formulas |

---

## Gap 5 — CDA ONNX System Integration (§5.28)

Added "System Integration" subsection showing complete diagnosis-to-remediation
branching:
```
compressor_collapse → boost S4 (CPI) ACN weight
leak               → elevate leak PIDs in RVMS freeze queue
cpu_collision      → activate CPU-RAM conflict gate (_ram_pressure_lock=True)
```
ONNX is framed as a performance optimisation of the inference path, not a
standalone AI feature. The downstream OS effects are identical in both
pure-Python and ONNX inference paths.

---

## Gap 6 — New §5.29: Alice § 101 Eligibility Argument

New section added covering:

- **Step 2A Prong 1:** Identified abstract elements per claim (9 mathematical
  concept / mental process analogs across Claims 13–28)
- **Step 2A Prong 2:** Integration argument per engine — each formula output
  is the direct trigger condition for an OS SIGSTOP/SIGCONT/SIGTERM signal
- **Step 2B:** "Significantly more" table — 7 elements that are unconventional
  and not present in any identified prior art
- **Legal precedents cited:**
  - *Enfish v. Microsoft* (2016) — improvement to computer functionality itself
  - *McRO v. Bandai Namco* (2016) — specific technical rule, not generic decision
  - *Berkheimer v. HP* (2018) — unconventional elements preclude summary rejection
  - *Amdocs v. Openet* (2016) — technical result in distributed computing eligible
  - *Core Wireless v. LG* (2018) — improved interface eligible

---

## Gap 7 — Claims 14, 19, 21, 26, 27, 28 Strengthened

Each claim rewritten to replace "what" endings with "how + physical state" language:

| Claim | Old ending | New ending |
|-------|-----------|-----------|
| 14 (ATCE) | "…adapting remediation aggressiveness…" | "…transmitting SIGSTOP/SIGTERM signals, causing a change in OS process scheduler state and reduction in kernel-allocated resident memory pages" |
| 19 (SIE) | "…prior to weighted-quorum tier escalation." | "…preventing transient OS measurement anomalies from generating erroneous process suspension signals" |
| 21 (RWA) | "…derived from success rates stored in a table." | "…wherein said weight updates directly modify the quorum vote totals that determine whether SIGSTOP/SIGTERM signals are dispatched" |
| 26 (PSM) | "…estimating expected dwell…" | "…using said predicted next tier to pre-position the remediation cascade, reducing latency between detection and process suspension delivery" |
| 27 (BRL) | "…exposing posterior confidence in API." | "…suppressing autonomous irreversible remediation actions when confidence is low, preventing false-positive process termination" |
| 28 (CDA) | "…probability distribution over root-cause categories." | "…routing cascade to category-specific OS interventions: SIGSTOP for leak, compressor-weight boost for collapse, CPU renice deferral for cpu_collision" |

---

## Reference Deployment Data (2026-04-13)

| Metric | Value |
|--------|-------|
| Hardware | 17.2 GB Apple Silicon Mac |
| Session duration | 22.8 hours |
| Cache rows | 17,032 |
| ATCE Tier 2 | 82% → 78.0% |
| ATCE Tier 3 | 87% → 79.7% |
| ATCE Tier 4 | 92% → 80.7% |
| Actions taken | 66 |
| RAM reclaimed | 3,524 MB |
| CPI at session | 1.000 (compressor fully saturated) |
| CDA diagnosis | compressor_collapse (dominant) |
| PSM prediction | Tier 3 next, 3.9 s dwell |
| ASZM protected | 133 processes dynamically elevated |
| BRL confidence | 0.136 (cold start; rises with uptime) |
| Bot RSS | < 28 MB |

---

_This document is internal working material for the non-provisional patent filing._
_It does not constitute legal advice. Consult a registered USPTO patent attorney._
