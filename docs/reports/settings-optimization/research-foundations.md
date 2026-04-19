# Settings Optimization — Research Foundations

**Date**: 2026-04-18
**Audience**: Researchers, developers, reviewers
**Companion docs**: [Capabilities Guide](capabilities-guide.md) · [Comprehensive Reference](best-of-breed-settings-capabilities.md)

---

## Overview

This document collects the research evidence, paradoxes, and limitations behind the settings optimization pipeline. It answers: *Why does the pipeline work the way it does? What experiments back each capability? What was tried and failed? Where are the promising research directions?*

For practical "how to use" guidance, see the [Capabilities Guide](capabilities-guide.md).
For full source-cited per-patient data, see the [Comprehensive Reference](best-of-breed-settings-capabilities.md).

---

## Table of Contents

1. [The Descriptive-Prescriptive Paradox](#1-the-descriptive-prescriptive-paradox)
2. [AID Compensation Observation](#2-aid-compensation-observation)
3. [Post-Nadir Recovery Is Multi-Factorial](#3-post-nadir-recovery-is-multi-factorial)
4. [Irreducible Hypo Rate](#4-irreducible-hypo-rate)
5. [Evidence Inventory](#5-evidence-inventory)
6. [Comparison with oref0 Autotune](#6-comparison-with-oref0-autotune)
7. [Disproved Hypotheses](#7-disproved-hypotheses)
8. [Promising Research Directions](#8-promising-research-directions)
9. [Experiment Cross-Reference](#9-experiment-cross-reference)

---

## 1. The Descriptive-Prescriptive Paradox

> **This is the single most important finding in the research program.**

**Source**: EXP-2641/2642 (`egp-prescriptive-paradox-report-2026-04-13.md`)

The model that best *describes* correction glucose drops (per-patient log-ISF, bias = −3 mg/dL) is the **worst prescriber** (recommends 2.3× the optimal dose).

### Why this happens

Apparent ISF (total glucose drop / bolus dose) is an **emergent property** of the closed-loop system, not the patient's intrinsic insulin sensitivity. Two effects interact:

1. **Profile ISF is genuinely too low** — patients are more insulin-sensitive than their profiles say (dominant factor in the 2.91× apparent/profile ratio)
2. **The controller opposes large corrections** — when a bolus drives glucose down, the AID suspends basal and cancels SMBs to prevent overshooting. This **reduces** the total drop, deflating apparent ISF for larger doses

The dose-dependent interaction creates a paradox:
- **Small doses** (<1U): controller barely intervenes → apparent ISF ≈ true ISF
- **Large doses** (≥3U): controller aggressively suspends → apparent ISF deflated
- A log-ISF model captures this descriptively, but using it to *calculate* doses recommends 2.3× the optimal dose

### Implications

1. "Fixed ISF + controller feedback is a robust baseline" — but multi-factor ISF models improve on it
2. Single-factor ISF models do not reduce per-event hypo rate (R² = −0.19)
3. The ~16% hypo rate is partially addressable through multi-factor approaches and controller modifications (patience mode)
4. **Do NOT use apparent ISF values directly for dosing**

### Impact on pipeline

The production `advise_isf()` predates this finding. It uses conservative 25% steps toward apparent ISF, which provides a safe diagnostic signal. The demand-phase ISF (EXP-2651, 2663–2666) was initially the validated prescriptive target — circadian-flat and useful as a per-patient aggregate. However, EXP-2680 (N=7986) showed demand ISF IS dose-dependent (r=−0.418), and EXP-2681 revealed this is a ratio artifact: BG drop ≈74 mg/dL regardless of dose. See §5 "Disproved" for details.

---

## 2. AID Compensation Observation

**Source**: EXP-2629/2630 (`egp-deconfounding-report-2026-04-13.md`, corrected in `egp-evidence-synthesis-report-2026-04-18.md`)

The AID controller's insulin modulation is part of the observed glucose dynamics:
- IOB drops **55%** before hypo crossing because the controller reduces insulin delivery
- AID-active recovery = **7.6** vs suspended = **3.6** mg/dL/hr (p < 0.0001)
- Post-correction forces (EGP, counter-regulation, residual insulin, AID withdrawal) **cannot be decomposed into independent additive terms** (sum = 34, actual = 4.1 mg/dL/hr)

### What succeeded despite this

Per-patient physical parameters CAN be recovered using **multi-factor** methods:

| Method | Result | EXP |
|--------|--------|-----|
| Dose-dependent ISF | r = −0.56 | 2640 |
| Response-curve ISF fitting | R² = 0.805 | 1301 |
| Circadian ISF profiling | 10–20% RMSE improvement | 2652 |
| Phase decomposition (demand vs apparent) | 2–10× separation | 2651 |

### Corrected framing

The early label "AID Compensation Theorem" was an over-generalization. Controllers changing the system they control is a tautology, not a theorem. The correct statement: single-factor *additive* decomposition of post-nadir recovery fails, but multi-factor parameter recovery succeeds.

---

## 3. Post-Nadir Recovery Is Multi-Factorial

**Source**: EXP-2634/2635 (`egp-calibration-report-2026-04-13.md`, corrected in `egp-evidence-synthesis-report-2026-04-18.md`)

Five single-factor models (null, mean-reversion, IOB-decay, biexp-decay, Hill EGP) have **negative R²** (−2.4 to −3.2) when predicting post-nadir recovery rate on 219 corrections.

**Scope**: This applies specifically to post-nadir recovery rate from individual factors — NOT to ISF estimation or trajectory modeling more broadly. Response-curve ISF fitting achieves R² = 0.805 (EXP-1301); dose-dependent ISF achieves r = −0.56 (EXP-2640).

Bolus size is the strongest single predictor (r = −0.307), consistent with the dose-dependent ISF finding.

---

## 4. Irreducible Hypo Rate

The hypo rate floor is approximately **16%**, irreducible by settings optimization alone. This was established across EXP-2641/2642 and confirmed by the patience mode experiments (EXP-2662) which achieved partial reduction through controller modification rather than settings changes.

---

## 5. Evidence Inventory

### ✅ Validated & Productionized

| Capability | Key Evidence | When Added | Notes |
|-----------|-------------|------------|-------|
| Optimization sequencing | EXP-1765, 1479, 1386, 1416 | Early | CV threshold, phase priorities, sequential vs simultaneous |
| Overnight basal assessment | EXP-2371, 2375, 2052 | Early | Clean-night drift, dawn phenomenon |
| ISF discrepancy detection | EXP-747, 1703 | Early | 2.91× mean apparent/profile ratio |
| ISF power-law (β=0.9) | EXP-2511, 2523 | Early | 17/17 patients, 4 causal methods |
| Circadian ISF (2–9×) | EXP-2271, 2051 | Early | 2-zone captures 61–90% |
| CR adequacy | EXP-2535b, 1705 | Early | 1.47× effective/profile |
| CR independence (r=0.17) | EXP-2535b | Early | Tune separately from ISF |
| Correction threshold (166 mg/dL) | EXP-2526c, 2528 | Early | 75% rebound from 130–180 |
| Controller trust profiles | EXP-2624 | Early | 0 contradictions across 16 patients |
| Safety guardrails (25% cap) | EXP-2626 | Early | Preserves ranking (τ > 0.8) |
| Forward simulation (two-component) | EXP-2525, 2534, 2551 | Early | MAE=0.30pp, r=0.933 |
| **Demand-phase ISF** | EXP-2651, 2663–2667 | 2026-04 | Dose-independent, circadian-flat, 6h isolation |
| **SC suppression ceiling** | EXP-2656, 2660 | 2026-04 | Wall detection, 30% SC ceiling |
| **Patience mode** | EXP-2662 | 2026-04 | 34–82% SMB savings, ≤+2.1pp hyper |
| **SC ceiling + demand ISF** | EXP-2667 | 2026-04 | SC ceiling 30–56%, demand ISF validated |
| **Controller ISF signatures** | EXP-2668 | 2026-04 | Loop/AB vs Loop/TBR bolus spacing affects ISF measurement |
| **Wall resolution mechanism** | EXP-2669 | 2026-04 | 65% of wall resolutions are unaccounted (out-of-band intervention) |
| **CR sanity-check contrast** | EXP-2670 | 2026-04 | Meal-quality filters for CR adequacy assessment |
| **Cross-controller validation** | EXP-2671 | 2026-04 | 31-patient multi-controller data fidelity validation |
| **Autoprepare gate** | EXP-2672 | 2026-04 | Data qualification pipeline for expanded cohort |
| **Autoresearch wave 1** | EXP-2673 | 2026-04 | Automated experiment replication framework |
| **DynISF SR deep dive** | EXP-2674 | 2026-04 | Sensitivity ratio characterization for DynISF cohort |
| **Cross-controller ISF** | EXP-2675 | 2026-04 | ISF measurement differences across controller types |
| **PK model comparison** | EXP-2676 | 2026-04 | Pharmacokinetic model alternatives |
| **AID compensation artifact** | EXP-2677 | 2026-04 | Controller response confounds ISF measurement |
| **BG floor sensitivity** | EXP-2678 | 2026-04 | BG≥180 filter effect on ISF sign and magnitude |
| **Circadian ISF deep dive** | EXP-2679 | 2026-04 | Time-of-day ISF variation with BG≥180 corrections |
| **Definitive demand ISF** | EXP-2680 | 2026-04 | 7986 events, demand ISF IS dose-dependent (r=−0.418) |
| **BG drop direct modeling** | EXP-2681 | 2026-04 | BG drop ≈74 mg/dL regardless of dose — ISF dose-dependence is ratio artifact |
| **Controller vs bolus** | EXP-2682 | 2026-04 | Total insulin (bolus+controller) R²=0.001 for BG drop |
| **Unexplained variance** | EXP-2683 | 2026-04 | 83.5% of BG drop variance is irreducible stochastic noise |
| **Aggregate outcomes** | EXP-2684 | 2026-04 | Population-level outcome modeling |
| **Controller strategy** | EXP-2685 | 2026-04 | Loop bang-bang vs Trio proportional vs OpenAPS SMB dosing strategies |
| **Safety analysis** | EXP-2686 | 2026-04 | IOB at hypo onset ≈0 — controller suspension response, not cause |
| **Null model benchmark** | EXP-2687 | 2026-04 | Patient-mean baseline for BG drop prediction |
| **Temporal trends** | EXP-2688 | 2026-04 | Within-patient ISF stability over time |
| **Confounding analysis** | EXP-2689 | 2026-04 | Confounding by indication: rising BG → larger bolus → steeper drop |
| **Multi-channel decomposition** | EXP-2690 | 2026-04 | R²=0.296 multivariate; bolus uniquely 7.3%, excess basal 6.4%, SMB 0.9% |
| **Settings mediation** | EXP-2691 | 2026-04 | ISF→SMB rate→TIR mediation path; patient-level R²=0.335 |
| **Per-channel dose-response** | EXP-2692 | 2026-04 | Non-linear dose-response per insulin channel |
| **TIR gap decomposition** | EXP-2693 | 2026-04 | Decomposing time-in-range gaps by contributor |
| **Time-resolved channels** | EXP-2694 | 2026-04 | Temporal dynamics of channel decomposition |
| **Causal bolus effect (PSM)** | EXP-2695 | 2026-04 | Propensity score matching for causal inference |
| **Impulse response functions** | EXP-2696 | 2026-04 | Insulin channel impulse responses |
| **Within-patient variance** | EXP-2697 | 2026-04 | Variance decomposition within vs between patients |
| **Deconfounding pipeline** | EXP-2698 | 2026-04 | oref0-inspired multi-factor deconfounding; R²=0.839 per-patient |
| **ISF calibration** | EXP-2699 | 2026-04 | Per-patient ISF via deviation analysis; 21/21 dose-dependent; calibration ratio 14.5× |
| **Parameter recovery** | EXP-2700 | 2026-04 | CR calibration + full parameter recovery pipeline |
| **Predictive validation** | EXP-2701 | 2026-04 | 4-model comparison on 23 patients; model D wins vs flat ISF in 23/23 |
| **Circadian demand ISF (expanded)** | EXP-2702 | 2026-04 | 22-patient circadian ISF replication |
| **SC ceiling per patient** | EXP-2703 | 2026-04 | Per-patient SC absorption ceiling estimation |
| **Glycogen state detection** | EXP-2704 | 2026-04 | Glycogen state proxy on 22-patient cohort |
| **Midday ISF peak** | EXP-2705 | 2026-04 | Investigating midday ISF peak confound |
| **SC ceiling dose-response slope** | EXP-2706 | 2026-04 | SC ceiling via dose-response slope |
| **Glycogen confound** | EXP-2707 | 2026-04 | Glycogen confound analysis |
| **BG-adjusted circadian ISF** | EXP-2708 | 2026-04 | Circadian variation 5.57× after BG adjustment vs 2.02× raw |
| **SC ceiling BG-controlled** | EXP-2709 | 2026-04 | SC ceiling detected in all 6 BG bands |
| **Multi-factor deconfounding** | EXP-2710 | 2026-04 | Comprehensive deconfounding model |
| **Baseline return model** | EXP-2711 | 2026-04 | Supply-side quantification; bilateral R²=0.228 |
| **Bilateral subtraction** | EXP-2712 | 2026-04 | Supply + demand ISF decomposition; supply=99.6% of total drop |
| **Independence-corrected validation** | EXP-2714 | 2026-04 | Robustness after removing correlated features |
| **Shrinkage circadian ISF** | EXP-2715 | 2026-04 | Shrinkage estimator for circadian ISF stability |
| **β horizon sensitivity** | EXP-2716 | 2026-04 | SC ceiling β vanishes at longer prediction horizons |
| **Total insulin accounting** | EXP-2717 | 2026-04 | Supply-side contamination of ISF over variable DIA horizons |
| **Phase decomposition** | EXP-2718 | 2026-04 | Correction phase: insulin activity vs BG response timing |
| **Extended waterfall** | EXP-2719 | 2026-04 | Systematic subtraction pipeline for multi-factor ISF |
| **Independent-event ISF** | EXP-2720 | 2026-04 | 29% lower MAE with independence-filtered events (48.5 vs 68.2) |
| **Circadian shrinkage ISF** | EXP-2721 | 2026-04 | Flat ISF wins MAE (40.3 vs 41.9); circadian real but not helpful |
| **Cross-controller normalization** | EXP-2722 | 2026-04 | η² reduced 55%, ISFs converge across controllers |
| **Stacking prevention** (3.5h) | EXP-2624 | 2026-04 | EGP nadir timing |
| **48h carb history** | EXP-2622, 2627 | 2026-04 | Glycogen context for overnight drift |

### ⚠️ Partially Done / In Progress

| Capability | Evidence | Gap |
|-----------|----------|-----|
| Detected-meal CR | EXP-1341, 1569, 748 | `_extract_cr_schedule()` uses `carbs_estimated_g` for MEAL windows but UAM windows lack estimates and aren't fed to CR optimizer |
| Context-aware CR | EXP-2341 | R²+0.28 from pre-BG + time + IOB context; not wired into optimizer |
| Carb estimation ensemble | EXP-1341, 1569 | 4 algorithms exist (physics, oref0 deviation, excursion, Loop IRC); best r=0.368; not plumbed into production |

### ❌ Disproved / Does Not Work

| Hypothesis | Evidence | Why It Failed |
|-----------|----------|---------------|
| Circadian demand ISF | EXP-2664, 2665, 2666, 2721 | Apparent ISF circadian variation is EGP-driven, not insulin sensitivity. Demand ISF is circadian-flat (−4.7%). EXP-2721 confirms: flat ISF wins MAE (40.3 vs 41.9) — circadian signal is real but doesn't improve prediction |
| Split-dose recommendation | EXP-2522 | 87% theoretical improvement, but empirically 0.39× due to glucose difficulty selection bias |
| 15–30g meal sweet spot | EXP-2537d | Based on entered carbs, not actual carbs. Real meals are 40–100g+ |
| Additive force decomposition | EXP-2634, 2635 | Sum = 34, actual = 4.1 — forces are coupled, not additive |
| Single-factor recovery prediction | EXP-2634, 2635 | All 5 models negative R² on post-nadir recovery rate |
| Naive bias correction | Recommender EXP | Harmful for 8/10 patients — removes defensive suspension |
| **Individual-event ISF estimation** | EXP-2680–2683, 2690, 2711–2712 | BG drop ≈74 mg/dL regardless of dose; ISF∝1/dose is a ratio artifact. 83.5% of BG drop variance is irreducible stochastic noise. Multi-channel regression (EXP-2690) recovers R²=0.296 when controlling for all insulin channels simultaneously — bolus uniquely explains 7.3%. Bilateral decomposition (EXP-2712) shows supply (baseline return) accounts for 99.6% of total drop, insulin residual only 0.4%. Individual-event ISF remains unreliable, but insulin IS measurably relevant in aggregate via multi-channel and deconfounding approaches. |

---

## 6. Comparison with oref0 Autotune

oref0's autotune is the only widely-deployed automated settings optimizer in the AID ecosystem. It ships identically in AAPS (Kotlin port) and Trio (embedded JS). Loop has no equivalent.

### How autotune works

**Phase 1 — Categorization** (`autotune-prep/categorize.js`): Every 5-minute glucose point is classified into 4 buckets:

| Bucket | Used For | Criterion |
|--------|----------|-----------|
| basalGlucose | Basal tuning | Default (no other category) |
| ISFGlucose | ISF tuning | BGI < −¼ × basalBGI AND avgDelta ≤ 0 |
| CSFGlucose | CR tuning | COB > 0 AND absorbing |
| UAMGlucose | Fallback | IOB > 2× currentBasal AND deviation > 0 |

The "deviation" at each point = actual glucose change − expected insulin effect (BGI from IOB model).

**Phase 2 — Adjustment** (`autotune/index.js`):
- **Basal**: Sum basalGlucose deviations per hour → `basalNeeded = 0.2 × totalDeviation / ISF`, spread across prior 3 hours
- **ISF**: Median ratio of actual/expected BG change across ISFGlucose points, 20% blend
- **CR**: Actual CR = carbs / totalInsulin from bolus to COB=0, 20% blend
- **Safety**: All outputs clamped to [pumpValue × autosens_min, pumpValue × autosens_max] (defaults: 0.7–1.2×)

### Head-to-head comparison

| Dimension | oref0 Autotune | Our Pipeline |
|-----------|---------------|--------------|
| **Basal signal** | BG deviation from IOB model (all hours) | Overnight drift on clean nights (00–06h, IOB<0.5U) |
| **IOB awareness** | Yes — subtracts expected insulin effect | Filters for low IOB instead |
| **Time resolution** | 24 hourly bins | 5 time periods |
| **Adjustment rate** | 20% blend per iteration | ±10% per cycle (conservative wins 10/11) |
| **Safety caps** | ±20–30% of pump (autosens limits) | ±50% hard clamp + 25% per-cycle cap |
| **ISF** | Single scalar | Circadian (2–9×), power-law, demand-phase |
| **CR** | Single scalar, 20% blend | Per-period, context-aware |
| **AID compensation** | Not modeled | Quadrant analysis, loop-dependent phenotype |
| **Prescriptive paradox** | Not addressed | Central finding — apparent ISF ≠ dosing ISF |
| **Deployment** | Online (daily, automatic) | Offline (batch, retrospective) |
| **Minimum data** | 24h (1 day) | 3 days (14 for full confidence) |

### What autotune does better

1. **Online daily** — fire-and-forget, runs automatically
2. **24-hour coverage** — tunes all hours, not just overnight
3. **IOB-aware deviations** — isolates basal-attributable movement during active insulin
4. **Proven safety** — thousands of patients, years of deployment
5. **Hourly granularity** — 24 bins vs 5 periods for basal

### What our pipeline does better

1. **AID compensation awareness** — autotune's deviations are contaminated by controller behavior
2. **Circadian ISF/CR** — 2–9× within-day variation vs single scalar
3. **Prescriptive paradox awareness** — autotune uses observed ISF directly (the pattern the paradox warns against)
4. **Optimization sequencing** — enforced fix order (+40–90% vs +15–25% for simultaneous)
5. **Statistical confidence** — bootstrap CIs, minimum evidence thresholds
6. **Controller-specific tuning** — trust factors per Loop/Trio/AAPS/OpenAPS

### Complementary use

| Phase | Best Tool | Why |
|-------|-----------|-----|
| Initial onboarding (first 2 weeks) | Autotune | Automatic, converges from any start, proven safe |
| Periodic deep review (monthly) | Our pipeline | Catches paradoxes and compensation autotune can't see |
| Circadian ISF/CR optimization | Our pipeline | Autotune's single scalar can't capture 2–9× variation |
| Ongoing maintenance | Autotune | Daily fire-and-forget |
| Clinical review | Our pipeline | Counterfactual simulation, phenotyping |

**Ideal workflow**: Run autotune daily for maintenance. Monthly, run our pipeline to detect compensation patterns, prescriptive paradoxes, and circadian opportunities. Use pipeline sequencing to decide *what* to change; autotune's deployment model to implement gradually.

---

## 7. Disproved Hypotheses — Lessons Learned

### 7.1 Circadian Demand ISF (EXP-2664–2666)

**Hypothesis**: Demand-phase ISF varies with time of day, enabling circadian ISF schedules.
**Result**: Disproved. Apparent ISF shows circadian variation (2–9×), but this is driven by EGP (endogenous glucose production) variation, not insulin sensitivity. When measured in the demand phase (0–2h), ISF is circadian-flat (only −4.7% from profiling). Nyquist minimum block for circadian ISF = 12h (DIA=6h), making fine-grained circadian ISF unmeasurable from corrections.

**Lesson**: Apparent ISF circadian variation is real but is a property of the glucose system (EGP), not of insulin sensitivity. The pipeline correctly captures it with circadian ISF zones but should not attribute it to insulin pharmacology.

### 7.2 Split-Dose Superiority (EXP-2522)

**Hypothesis**: 2×1U corrections spaced 30+ min apart achieve 1.87× the drop of a single 2U dose.
**Result**: Theoretically correct from the power-law model, but empirically **0.39×** — split doses are associated with *worse* outcomes. The confound: split doses are administered when the first dose *fails* (glucose difficulty selection bias).

**Lesson**: Observational data cannot validate dosing strategies that are correlated with glucose difficulty. Needs a randomized trial.

### 7.3 Additive Force Decomposition (EXP-2634/2635)

**Hypothesis**: Post-nadir recovery can be decomposed into additive contributions from EGP, counter-regulation, residual insulin, and AID withdrawal.
**Result**: Sum of independent estimates = 34, actual recovery = 4.1 mg/dL/hr. The forces are coupled and partially cancel.

**Lesson**: The AID creates a coupled dynamical system where components cannot be analyzed in isolation. Multi-factor methods that fit the coupled system (response curves, dose-dependent ISF) succeed where additive decomposition fails.

### 7.4 Naive Bias Correction

**Hypothesis**: Forward simulation prediction bias should be corrected to improve accuracy.
**Result**: Harmful for 8/10 patients. The negative bias IS the loop's defensive suspension — removing it removes hypo prevention.

**Lesson**: In a controlled system, prediction errors may be features, not bugs.

---

## 8. Promising Research Directions

### 8.1 UAM → CR Pipeline (Highest Impact Gap)

**Status**: Research exists, needs production plumbing.
**Evidence**: EXP-1341 (4 carb estimation algorithms, best r=0.368), EXP-1569 (72-config benchmark), EXP-486 (throughput detection).

The pipeline **detects** unannounced meals (39% of all windows) and has **multiple estimation algorithms**, but none are wired into the CR optimizer. The oref0 deviation estimator could provide carb magnitude using ISF (already optimized before CR in the sequencing protocol).

**Impact**: Would make CR recommendations usable for patients who don't log carbs (the majority).

### 8.2 Two-Component DIA Model

**Status**: Predictively validated, not productionized.
**Evidence**: EXP-2525, 2534 (R² = 0.827, 280 overnight matched pairs).

The persistent tail (37%, τ=12h) is IOB underestimation by standard DIA curves + loop compensation, not liver physiology as originally thought. Implementing this in AID firmware would improve bolus-on-board calculations.

**Barrier**: Requires AID firmware changes (Loop, AAPS, Trio), not just advisory changes.

### 8.3 Patience Mode Refinement

**Status**: Productionized, but parameters could be patient-specific.
**Evidence**: EXP-2660, 2662. Current thresholds (IOB > 2× median, ROC > −5) work population-wide. The SC suppression ceiling (30–56% across patients) correlates with sticky hyper rate (r = −0.60).

**Opportunity**: Patient-specific ceiling detection could tune patience mode aggressiveness per individual, potentially improving the 34–82% SMB savings range.

### 8.4 Online/Streaming Pipeline

**Status**: Conceptual.

The current pipeline is offline (batch retrospective). An online version running daily (like autotune) but with our circadian ISF, sequencing, and paradox awareness would combine the best of both approaches. The main barrier is the 14-day minimum for full confidence — a streaming approach would need incremental confidence building.

### 8.5 Controller-Aware ISF Targeting

**Status**: Early research.

The demand-phase ISF (constant per patient) could replace apparent ISF as the AID's ISF setting, with the controller's compensation explicitly modeled as a separate gain term. This would address the prescriptive paradox at the firmware level rather than the advisory level.

**Risk**: Changing ISF settings changes controller behavior, which changes observed ISF — the same circular dependency the paradox describes. Simulation studies needed before any clinical application.

---

## 9. Experiment Cross-Reference

### Core Settings Research (EXP-574–2662)

| EXP | Topic | Key Result | Used In |
|-----|-------|-----------|---------|
| 747 | ISF discrepancy | 2.91× apparent/profile mean | `advise_isf()` |
| 1301 | Response-curve ISF | R² = 0.805 | ISF extraction |
| 1334 | DIA estimation | 6.0h population (vs 5h assumed) | Profile generation |
| 1336 | Meal timing | Dinner worst (77 mg/dL excursion) | CR circadian |
| 1341 | Carb estimation | 4 algorithms, best r=0.368 | Research (not plumbed) |
| 1386 | Impact ranking | Basal top for 10/11 patients | Sequencing |
| 1416 | Basal magnitude | Conservative ±10% wins | `advise_basal()` |
| 1479 | Sequential optimization | +40–90% vs +15–25% simultaneous | Sequencing |
| 1569 | Meal benchmark | 72-config grid, 5g/150min knee | Research |
| 1703 | ISF effective/profile | 2.30× mean, 7,534 corrections | `advise_isf()` |
| 1705 | CR effective/profile | 73% of profile (1.47× ratio) | `advise_cr()` |
| 1765 | Fix order | 6/11 harmed by wrong order, CV=28% threshold | Sequencing |
| 2051 | Circadian ISF | Peak 10am–1pm, nadir 4–6pm | `advise_circadian_isf()` |
| 2052 | Dawn phenomenon | 6/19 patients affected | `assess_overnight_drift()` |
| 2248 | Graduated transition | 4-step protocol, 2–4 weeks | Recommender |
| 2271 | ISF circadian range | 2–9× within-day | `advise_circadian_isf()` |
| 2341 | Context-aware CR | R²+0.28 with pre-BG + time + IOB | Research |
| 2371 | Basal calibration | 18/19 miscalibrated | `advise_basal()` |
| 2375 | Clean-night detection | IOB<0.5U, COB<5g, 00–06h | `assess_overnight_drift()` |
| 2391 | Loop workload | 18/19 saturated | Insight only |
| 2511 | Dose-ISF power law | β=0.9, 17/17 patients | `advise_isf_nonlinearity()` |
| 2522 | Split-dose | Theoretical 1.87×, empirical 0.39× | ❌ Disproved |
| 2523 | Dose-ISF causal | 4 methods, p<0.0001 | `advise_isf_nonlinearity()` |
| 2525 | Two-component DIA | R²=0.827 | `forward_simulator.py` |
| 2526c | Correction rebound | 75% rebound from 130–180 | `advise_correction_threshold()` |
| 2528 | Threshold scan | 166 mg/dL optimal | `advise_correction_threshold()` |
| 2534 | DIA mechanism | IOB underestimation, not HGP | `forward_simulator.py` |
| 2535b | CR independence | r=0.17 (ISF independent) | CR optimization |
| 2537a | Nonlinearity cancel | Net R²+0.001–0.005 | Linear dosing validated |
| 2537d | Meal sweet spot | ❌ Based on entered carbs | Reframed |
| 2551 | Forward sim accuracy | MAE=0.30pp, r=0.933 | `forward_simulator.py` |

### EGP Phase Research (EXP-2621–2667)

| EXP | Topic | Key Result |
|-----|-------|-----------|
| 2622 | 48h carb history | Glycogen context for overnight drift |
| 2624 | Advisory audit | 0 contradictions, stacking at 3.5h |
| 2626 | Safety guardrails | 25% cap preserves ranking (τ>0.8) |
| 2627 | Carb history integration | 48h carbs in overnight drift |
| 2629 | AID compensation cascade | IOB drops 55% before hypo |
| 2630 | EGP deconfounding | AID-active 7.6 vs suspended 3.6 mg/dL/hr |
| 2634 | Recovery models | All 5 negative R² on recovery rate |
| 2635 | Recovery attribution | Bolus size r=−0.307 (strongest) |
| 2640 | Dose-dependent ISF | r=−0.56, log model wins 5/6 |
| 2641 | Prescriptive paradox (sim) | Log-ISF prescribes 2.3× optimal dose |
| 2642 | Prescriptive paradox (audit) | Fixed ISF + feedback near-optimal |
| 2651 | Two-phase ISF | Demand 2–10× smaller than apparent |
| 2652 | Circadian ISF profiling | 10–20% RMSE improvement |
| 2653 | Nyquist multiscale | 87% of overnight drift unmeasured |
| 2654 | CR adequacy | Per-patient CR validation |
| 2656 | SC suppression ceiling | 30–56%, correlates with sticky hyper |
| 2658 | Extended horizon | Additive EGP 19–76% worse at 4–8h |
| 2660 | Sticky hyper/wall detection | 61–84% show wall detection |
| 2661 | Dual ISF (harm test) | Naive demand ISF → +12–42pp hypo |
| 2662 | Patience mode | 34–82% SMB savings, ≤+2.1pp hyper |
| 2663 | Demand dose-dependence | |r|=0.156 at N=23 (overturned by EXP-2680: r=−0.418 at N=7986) |
| 2664 | Circadian demand ISF | ❌ Circadian-flat (−4.7%) |
| 2665 | Nyquist circadian ISF | Min block = 12h (DIA=6h) |
| 2666 | Isolation sweep | 6h optimal, rank order rho=0.964 |
| 2667 | SC ceiling + demand ISF | Combined validation, 17 patients |
| 2668 | Tier-2 expanded cohort | 29 patients, demand ISF validation |
| 2669 | DynISF characterization | 12 DynISF-v2 patients |
| 2670 | CR sanity-check | Cohort-wide CR analysis |
| 2671 | Cross-controller validation | Phase 1–3: controller strategy comparison |
| 2672–2679 | BG floor, circadian deep-dives | BG≥180 filter effects, circadian ISF sub-analyses |
| 2680 | Definitive demand ISF | N=7986, r=−0.418 (overturns EXP-2663) |
| 2681 | BG drop direct modeling | BG drop ≈74 mg/dL regardless of dose |
| 2682 | Controller vs bolus | Total insulin R²=0.001 for BG drop |
| 2683 | Unexplained variance | 83.5% irreducible stochastic noise |
| 2684 | Aggregate outcomes | Population-level TIR modeling |
| 2685 | Controller strategy | Loop bang-bang vs Trio proportional vs OpenAPS SMB |
| 2686 | Safety analysis | IOB≈0 at hypo onset = controller response |
| 2687 | Null model benchmark | Patient-mean baseline for BG drop |
| 2688 | Temporal trends | Within-patient ISF stability |
| 2689 | Confounding analysis | Rising BG → larger bolus → steeper drop |
| 2690 | Multi-channel decomposition | R²=0.296 multivariate; bolus 7.3%, basal 6.4% |
| 2691 | Settings mediation | ISF→SMB→TIR path; patient R²=0.335 |

### Production Validation (101 scripts)

The production test suite (85 classes, 418 tests) validates all productionized capabilities. Key validation experiments:

| Script | Tests |
|--------|-------|
| `exp_safety_guardrails_2626.py` | 25% cap doesn't distort rankings |
| `exp_advisory_audit_2624.py` | 0 contradictions across 16 patients |

---

## Methodology Notes

### Data Basis
- **43 patients**: 11 Nightscout (a–k), 8 ODC (odc-*), 12 DynISF-v2 (ns-*), others
- **5-min CGM intervals** across all patients
- **50,810+ natural experiment windows** (fasting, correction, meal, UAM)
- **35K+ corrections**, **5K+ meals**, **7986 demand-phase events** (EXP-2680)
- **AID controllers**: Loop/AB, Loop/TBR, Trio/AB, AAPS/SMB, AAPS/TBR (corrected 2026-04-18 from devicestatus metadata)

### Statistical Standards
- Bootstrap confidence intervals: 1,000 resamples, 95% CI
- Evidence thresholds: ≥10 windows/period for "high", ≥3 for "medium"
- Power analysis: Min detectable r=0.187 at N=219 corrections
- Sampling independence: Bolus autocorrelation r=0.36, but ISF/drop autocorrelation ~0

### Controller Classification
Controller labels are derived from the `controller` column in `devicestatus.parquet`, NOT from SMB ratio heuristics. Loop's "Automatic Bolus" dosing strategy records micro-boluses as `bolus_smb`, which previously caused misclassification. Corrected 2026-04-18 (commit `03db99b`).

---

*For practical usage guidance, see [Capabilities Guide](capabilities-guide.md).*
*For full source-cited reference, see [Comprehensive Reference](best-of-breed-settings-capabilities.md).*
