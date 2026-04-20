# Settings Optimization — Capabilities Guide

**Date**: 2026-04-18
**Audience**: Tool users, clinicians, integrators
**Companion docs**: [Research Foundations](research-foundations.md) · [Comprehensive Reference](best-of-breed-settings-capabilities.md)

---

## Overview

The settings optimization pipeline analyzes retrospective CGM + insulin data to recommend therapy settings changes for AID (Automated Insulin Delivery) controllers: Loop, Trio, AAPS, and oref0.

**Key design principles**:
- **Advisory only** — generates recommendations, never changes pump settings directly
- **Fix order matters** — the pipeline enforces a specific optimization sequence (§2)
- **Conservative** — 25% maximum change per cycle, with safety clamps at every level
- **Carb-independent** — basal and ISF advisories do NOT depend on carb entry accuracy

**Data requirements**: Minimum 3 days of CGM + insulin data. Full confidence at 14+ days.

---

## Quick Start: What Does the Pipeline Do?

The pipeline takes your exported CGM + insulin data and produces:

1. **A diagnosis** — which settings are miscalibrated and by how much
2. **A priority order** — which setting to fix first (this matters — see §2)
3. **Specific recommendations** — direction, magnitude, and confidence for each change
4. **A safety assessment** — guardrails, contradiction checks, and graduated transition plan
5. **An exportable profile** — in Loop, Trio, AAPS, or Nightscout format

---

## Capability Maturity Matrix

Each capability is rated by maturity level:

| Capability | Maturity | Evidence | Module |
|-----------|----------|----------|--------|
| **Optimization sequencing** (§2) | 🟢 Production | EXP-1765, 1479, 1386 | `advisor/_pipeline.py` |
| **Basal adequacy** (§3) | 🟢 Production | EXP-2371, 2375, 2052 | `advisor/_basal_advisors.py`, `settings_optimizer.py` |
| **ISF discrepancy detection** (§4) | 🟢 Production | EXP-747, 1703 | `advisor/_isf_advisors.py` |
| **ISF power-law nonlinearity** (§4) | 🟢 Production | EXP-2511, 2523 | `advisor/_isf_advisors.py` |
| **Circadian ISF** (§4) | 🟢 Production | EXP-2271, 2051 | `advisor/_isf_advisors.py` |
| **Demand-phase ISF** (§4) | 🟢 Production | EXP-2651, 2663–2666 | `clinical_rules.py` |
| **CR adequacy** (§5) | 🟢 Production | EXP-2535b, 1705 | `advisor/_cr_advisors.py` |
| **Correction threshold** (§6) | 🟢 Production | EXP-2526c, 2528 | `advisor/_pipeline.py` |
| **Controller-specific trust** (§7) | 🟢 Production | EXP-2624 | `recommender.py` |
| **Profile export** (§8) | 🟢 Production | — | `profile_generator.py` |
| **Safety guardrails** (§9) | 🟢 Production | EXP-2624, 2626 | `advisor/_pipeline.py`, `settings_optimizer.py` |
| **SC suppression ceiling** | 🟢 Production | EXP-2656, 2660 | `clinical_rules.py` |
| **Patience mode advisory** | 🟢 Production | EXP-2662 | `advisor/_isf_advisors.py` |
| **Stacking prevention** | 🟢 Production | EXP-2624 | `clinical_rules.py` |
| **Forward simulation** (§10) | 🟡 Beta | EXP-2525, 2534, 2551 | `forward_simulator.py` |
| **Detected-meal CR** | 🟡 Partial | EXP-1341, 1569 | `settings_optimizer.py` |
| **Context-aware CR** | 🔬 Research | EXP-2341 | `advisor/_cr_advisors.py` |
| **Split-dose recommendation** | ❌ Disproved | EXP-2522 | — |
| **Circadian demand ISF** | ❌ Disproved | EXP-2664–2666, 2721 | Flat ISF wins MAE (40.3 vs 41.9) — circadian real but not actionable |
| **Individual-event ISF estimation** | ❌ Disproved | EXP-2680–2683, 2690 | Multi-channel R²=0.296 but individual events still too noisy |
| **Cross-controller ISF normalization** | 🔬 Research | EXP-2722 | η² reduced 55%; enables controller-switching ISF transfer |
| **Independent-event ISF extraction** | 🔬 Research | EXP-2720 | 29% lower MAE with independence-filtered events |
| **Deconfounding pipeline** | 🔬 Research | EXP-2698, 2710–2712 | R²=0.228 bilateral; 0.839 per-patient deconfounding |
| **Per-patient settings extraction** | 🔬 Research | EXP-2723 | 90.5% of patients improve; median 75.8% MAE reduction |
| **Basal circadian drift analysis** | 🔬 Research | EXP-2724 | Per-patient drift heatmap; patient-specific, not universal dawn |
| **DynISF algorithm deconfounding** | 🔬 Research | EXP-2725 | sensitivity_ratio orthogonal to ISF (r=0.008); dose captures effect |
| **Prospective ISF validation** | 🔬 Research | EXP-2726/2726b | Profile ISF catastrophic in sim (65% TBR); empirical ISF 5/5 PASS, 29/31 improve |
| **ISF gap decomposition** | 🔬 Research | EXP-2727 | 10× gap: EGP 42%, controller 44%; profile+EGP beats empirical ISF |
| **EGP-aware simulation** | 🔬 Research | EXP-2728 | Physics (profile+EGP+CR) beats empirical ISF; 4/5 PASS |
| **Deconfounded CR extraction** | 🔬 Research | EXP-2729 | Profile CR ~2× off; deconfounded MAE 6.19→3.42, 95.5% improve |
| **Basal drift optimization** | 🔬 Research | EXP-2730 | 22 patients, 207K events; all need adjustment; aggressive recs flagged |
| **Unified calibration scoring** | 🔬 Research | EXP-2731 | ISF 0/100, CR 56/100, basal 19.5/100; controller predicts quality |
| **Multi-factor EGP deconfounding** | 🔬 Research | EXP-2732 | EGP as regressor closes ISF gap 2.5×→2.2×; R² +33% |
| **Simulator-based ISF extraction** | 🔬 Research | EXP-2733 | Causal ISF via physics sim; dose artifact reduced 32% |
| **Cross-validation robustness** | 🔬 Research | EXP-2734 | 75/25 temporal split: test/train ratio=0.997; settings generalize |
| **Controller compensation model** | 🔬 Research | EXP-2735 | Compensation ratio=0.497; basal suspension 185%; closes ISF gap |
| **ISF reconciliation framework** | 🔬 Research | EXP-2736 | ~4× gap = 1.93× (EGP) × 2.66× (controller); all ISFs correct in context |

**Legend**: 🟢 Production (validated, tested, in pipeline) · 🟡 Beta/Partial (functional but incomplete) · 🔬 Research (experimental) · ❌ Disproved (tried, doesn't work)

---

## 1. Pipeline Architecture

The pipeline runs 11 stages in sequence. If data is missing for a stage, it degrades gracefully:

| Stage | What It Does | Degrades When |
|-------|-------------|---------------|
| Data quality | Spike cleaning, gap filling | — (always runs) |
| Patient onboarding | Determines available data & models | — |
| Metabolic engine | Physics: supply/demand decomposition | No insulin data |
| Risk + clinical | Hypo prediction, pattern analysis, clinical rules | <1 week of data |
| Meal detection | Extracts meal events | No carb entries (UAM still detected) |
| Natural experiments | Detects fasting/correction/meal windows | — |
| Settings optimizer | Optimal per-period settings from natural experiments | <3 days of data |
| Settings advisor | Counterfactual simulation + advisories | — |
| Recommender | Prioritized, controller-aware recommendations | — |
| Advanced analytics | DIA analysis, phenotyping, loop quality | — |

**Orchestrator**: `tools/cgmencode/production/pipeline.py`
**Target latency**: <500ms per patient

---

## 2. Optimization Sequencing — Fix Order Matters

> **6/11 patients are harmed by optimizing in the wrong order.** Sequential optimization yields **+40–90%** improvement vs **+15–25%** for simultaneous adjustment.

The pipeline determines which phase a patient is in and prioritizes accordingly:

| Phase | When | Fix Order | Goal |
|-------|------|-----------|------|
| **REDUCE_VARIABILITY** | CV > 28% | Basal → CR → ISF | Flatten swings first |
| **CENTER** | CV ≤ 28%, TIR < 70% | ISF → CR → Basal | Shift mean into range |
| **PERSONALIZE** | CV ≤ 28%, TIR ≥ 70% | Impact-sorted | Fine-tune everything |

**Why basal first when variable**: Basal affects glucose 24/7. Fixing it stabilizes the foundation, making subsequent ISF/CR adjustments predictable.

**Controller architecture changes the priority**:
- **Loop/Trio** (suspend-based): Supply-dominant errors → fix basal first
- **AAPS/OpenAPS** (SMB-based): Demand-dominant errors → ISF matters most

**Graduated transition** (EXP-2248): Once targets identified, implement over 2–4 weeks in 4 steps with safety gates at each step. Patients with small mismatches (ISF ratio ≤ 1.4) need only 1–2 steps.

---

## 3. Basal Rate Advisories

### What fires and when

| Advisory | Trigger | Output |
|---------|---------|--------|
| `advise_basal()` | Always (≥3 days data) | Direction, magnitude (±10/15/20%), predicted TIR delta |
| `assess_overnight_drift()` | Always | Overnight phenotype classification |
| Dawn phenomenon | Drift >+3 mg/dL/hr, dawn rise >15 mg/dL | Flag + 4–6 AM basal increase suggestion |

### How it works

1. **Detect clean nights**: 00:00–06:00, IOB < 0.5U, COB < 5g (minimum 3 nights)
2. **Measure drift**: Linear regression → mg/dL/hr slope per night
3. **Classify phenotype**: Stable (|drift| ≤ 3), under-basaled (+drift), over-basaled (−drift), dawn riser, loop-dependent (suspension > 40%), or mixed
4. **Compute adjustment**: median_drift / profile_ISF → U/hr change, clamped at ±50%
5. **Simulate**: Test ±10%, ±15%, ±20% adjustments, pick best TIR outcome

### Key findings

- **18/19 patients** are basal-miscalibrated (only patient j is well-calibrated)
- **Conservative ±10% wins** for 10/11 patients — aggressive ±30% hurts up to −11.5% TIR
- **Basal is the top single action** for 10/11 patients
- **6/19 patients** show dawn phenomenon (only 6 AM is genuinely under-basaled)
- Carb entries are NOT used — this advisory is immune to carb logging quality

### Inputs/Outputs

**Inputs**: CGM glucose, insulin delivery (basal + bolus), current profile settings
**Outputs**: `BasalAdvisory(direction, magnitude_pct, current_rate, suggested_rate, tir_delta, confidence, phenotype)`

---

## 4. ISF Advisories

### Important caveat

Apparent ISF (total glucose drop / dose) is an **emergent property** of the closed-loop system, not the patient's true insulin sensitivity. The AID controller opposes large corrections by suspending basal, which deflates apparent ISF for larger doses. See [Research Foundations §1](research-foundations.md#1-the-descriptive-prescriptive-paradox) for details.

The ISF advisories are diagnostic tools that show **how hard the controller is working**, not prescriptive targets.

### What fires and when

| Advisory | Trigger | Output |
|---------|---------|--------|
| `advise_isf()` | Always (≥3 days) | Direction toward demand-phase ISF, 25% conservative step |
| `advise_isf_nonlinearity()` | Typical dose > 1.5U, ≥3 days | Power-law β, clinical meaning |
| `advise_circadian_isf()` | ≥7 days | Day/night zones, peak/nadir times |
| `advise_isf_segmented()` | ISF variation > 50%, ≥7 days | 2–4 time segments |
| `compute_demand_isf()` | ≥3 days | True demand-phase ISF (0–2h drop/dose) |

### Demand-phase ISF (latest research, productionized)

The demand-phase ISF (glucose drop in first 0–2 hours divided by dose) is:
- **2–10× smaller** than apparent ISF
- **Circadian-flat** (−4.7% from profiling — disproved)

> **⚠️ Important caveat (EXP-2680–2683, 2690–2691)**: At larger sample sizes (N=7986),
> demand ISF IS dose-dependent (r=−0.418). EXP-2681 showed this is a **ratio
> artifact**: BG drop ≈74 mg/dL regardless of dose, so ISF = drop/dose creates
> artificial 1/dose dependence. 83.5% of BG drop variance is irreducible
> stochastic noise (EXP-2683). However, multi-channel regression (EXP-2690)
> recovers R²=0.296 when controlling for all insulin channels simultaneously —
> bolus uniquely explains 7.3%, excess basal 6.4%. Settings affect outcomes
> through a mediation path: ISF → SMB rate → TIR (EXP-2691, R²=0.335).
> Individual-event ISF estimation remains unreliable, but settings DO matter
> through their effect on controller behavior. Demand ISF remains useful as a
> **per-patient aggregate** for relative comparisons and conservative
> step-down recommendations.

The `advise_isf()` function uses conservative 25% steps toward the demand-phase value.

### Key findings

- **ISF varies 2–9× within a day** (circadian). A 2-zone day/night schedule captures 61–90% of benefit
- **Power-law dose-response**: β = 0.9 — a 2U correction is 46% less effective per unit than 1U
- **Population peak**: 10am–1pm (most effective correction window)
- **Population nadir**: 4pm–6pm (least effective)

---

## 5. Carb Ratio Advisories

### ⚠ Carb entry caveat

CR advisories depend on user-entered carb values, which are unreliable. 39% of all glucose events are unannounced meals (UAM). The finding "effective CR = 1.47× profile" may reflect carb under-counting rather than conservative settings. See §5.8 in the [Comprehensive Reference](best-of-breed-settings-capabilities.md#58-carb-entry-reliability--whats-safe-vs-compromised).

**What's safe**: Basal and ISF recommendations (don't use carb entries)
**What's compromised**: CR magnitude recommendations (use entered carbs)
**What's partially safe**: CR direction recommendations (simulation-based)

### What fires and when

| Advisory | Trigger | Output |
|---------|---------|--------|
| `advise_cr()` | CR score < 40/100 | Direction, magnitude, predicted TIR delta |
| `advise_cr_adequacy()` | Always | Effective/profile CR ratio |
| `advise_context_cr()` | Research only | Context-adjusted CR (pre-BG + time + IOB) |

### Key findings

- **CR and ISF are independent** (r = 0.17) — tune them separately
- **Dinner is hardest** (77 mg/dL mean excursion, 54% high)
- **Nonlinearities cancel**: CR sub-linear absorption + ISF diminishing returns ≈ linear dosing remains valid
- **Detected-meal CR** (partially done): `_extract_cr_schedule()` falls back to `carbs_estimated_g` when entered carbs are missing/small, but UAM windows aren't yet fed to the CR optimizer

---

## 6. Correction Threshold Advisory

**Function**: `advise_correction_threshold()`
**Trigger**: Always (≥10 correction events for per-patient calibration)

**Finding**: Population optimal threshold ≈ **166 mg/dL** (range 130–290). Corrections from BG 130–180 rebound 75% of the time — this is regression to the mean, not counter-regulation.

**Method**: Scans BG bins (130–290, 10 mg/dL steps) to find the per-patient zero-crossing where net correction benefit turns positive.

---

## 7. Controller-Specific Behavior

The recommender adjusts confidence based on controller type:

| Controller | ISF Trust | CR Trust | Why |
|-----------|-----------|----------|-----|
| **Loop** | 0.30 | 0.40 | Heavy suspension masks ISF errors; focus on CR/timing |
| **Trio** | 0.35 | 0.45 | Moderate suspension; similar to Loop |
| **AAPS** | 0.60 | 0.60 | Balanced SMB/suspend; settings more visible |
| **OpenAPS** | 0.70 | 0.65 | Less aggressive compensation; settings most visible |

**Auto-detection**: Controller identified from metadata or suspension fraction (>60% → Loop, >40% → Trio, >15% → AAPS).

---

## 8. Profile Export

Generates complete AID profiles in 4 formats from optimized settings:

| Format | Used By | Time Representation |
|--------|---------|-------------------|
| **oref0** | OpenAPS rigs | Minutes from midnight + "HH:MM:SS" |
| **Loop** | Loop iOS | Seconds from midnight (TimeInterval) |
| **Trio** | Trio iOS | Dual: minutes + "HH:MM:SS" |
| **Nightscout** | NS REST API | "HH:MM" strings |

**Constraints enforced**: Basal 0.025–10.0 U/hr, ISF 10–500 mg/dL/U, CR 3–150 g/U, DIA 2–12h.
**Warnings**: Low-confidence blocks flagged. Changes >50% flagged with "verify with endocrinologist."

---

## 9. Safety Guardrails

| Guardrail | Limit | Evidence |
|-----------|-------|----------|
| Per-cycle change cap | **25% max** per parameter per cycle | EXP-2626: preserves ranking (τ > 0.8) |
| Basal clamp | **±50%** of profile value | Production constant |
| Advisory coherence | **0 contradictions** across 16 patients | EXP-2624 |
| Minimum data | **3 days** for any rec, **14 days** for full confidence | Production constants |
| Prediction bias | **Do NOT correct** — bias is defensive | 8/10 patients harmed by bias removal |
| Confidence grading | A (≥100 windows) through D (<20 windows) | Per-period + overall grade |

---

## 10. Forward Simulation (Digital Twin)

**Status**: 🟡 Beta — predictively valid (MAE = 0.30 pp, r = 0.933) but mechanism needs refinement.

The forward simulator predicts TIR outcomes for proposed settings changes using a two-component insulin model:

| Component | Fraction | Time Constant | What It Captures |
|-----------|----------|---------------|-----------------|
| Fast | 63% | τ = 0.8h | Direct insulin-mediated glucose uptake |
| Persistent | 37% | τ = 12h | IOB underestimation + loop compensation tail |

**Used for**: Counterfactual "what-if" analysis — "if we change ISF by +15%, what happens to TIR?"

**Caveat**: The loop is a feedback system. Model projections assume the controller responds similarly to settings changes, which may not hold for large changes. The graduated transition protocol (§2) mitigates this risk.

---

## 11. Newer Production Capabilities

### SC Suppression Ceiling Detection

**Function**: `detect_insulin_saturation()` in `clinical_rules.py`

Detects when insulin delivery hits a ceiling where additional insulin has diminishing effect. Uses wall detection: IOB > 2× median AND glucose rate of change > −5 mg/dL/5min.

**Tiers**: NONE → MILD → MODERATE → SEVERE
**Finding**: SC insulin can suppress at most ~30% of hepatic EGP (range 30–56% across patients). Ceiling correlates with sticky hyper rate (r = −0.60).

### Patience Mode Advisory

**Function**: `advise_patience_mode()` in `advisor/_isf_advisors.py`

Recommends capping SMB delivery when insulin is likely saturating. Fires when IOB > 2× median AND glucose not dropping fast.

**Impact**: Saves 34–82% of SMBs, ≤+2.1pp hyper increase, reduces delayed hypos 0.1–2.0pp.

### Stacking Prevention

**Function**: `assess_correction_timing()` in `clinical_rules.py`

Recommends minimum 3.5h between corrections (aligned with EGP nadir timing) to prevent insulin stacking.

---

## Test Infrastructure

| Suite | Tests | Time | Command |
|-------|-------|------|---------|
| Full | 448 | ~3 min | `pytest test_production.py` |

93 test classes covering all production modules. (`test_unit.py` and `test_integration.py` are stubs — the pytest mark split is not yet functional.)

---

*For research background, paradoxes, evidence chains, and autotune comparison, see [Research Foundations](research-foundations.md).*
*For full source-cited reference with per-patient data, see [Comprehensive Reference](best-of-breed-settings-capabilities.md).*
