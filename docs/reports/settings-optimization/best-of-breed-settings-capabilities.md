# Best-of-Breed Settings Optimization Capabilities

**Date**: 2026-04-18  
**Scope**: Basal rate, ISF, and CR schedule optimization for Loop, Trio, AAPS, and oref0 AID controllers  
**Data basis**: 19 patients (11 Nightscout + 8 ODC), 1,838 patient-days, 50,810 natural experiments, 35K+ corrections, 5K+ meals  
**Source material**: 270+ research reports, 100+ R&D experiments (EXP-574–EXP-2662), 101 production validation scripts  
**Status**: Verified against source code — every claim has a [SOURCE] citation

---

## Table of Contents

1. [Pipeline Architecture](#1-pipeline-architecture)
2. [ISF Optimization — The Dominant Lever](#2-isf-optimization--the-dominant-lever)
3. [Basal Rate Optimization](#3-basal-rate-optimization)
4. [Carb Ratio Optimization](#4-carb-ratio-optimization)
5. [Correction Threshold Advisory](#5-correction-threshold-advisory)
6. [Controller-Specific Behavior](#6-controller-specific-behavior)
7. [Profile Generation & Export](#7-profile-generation--export)
8. [Safety Guardrails](#8-safety-guardrails)
9. [Forward Simulation (Digital Twin)](#9-forward-simulation-digital-twin)
10. [Key Paradoxes & Limitations](#10-key-paradoxes--limitations)
11. [Research-Only Findings](#11-research-only-findings)
12. [Quantitative Summary](#12-quantitative-summary)
13. [Verification Checklist](#13-verification-checklist)

---

## 1. Pipeline Architecture

The production pipeline is an 11-stage linear chain with graceful degradation for missing data.

**Orchestrator**: `tools/cgmencode/production/pipeline.py`

| Stage | Module | Purpose | Line |
|-------|--------|---------|------|
| 1 | `data_quality.py` | Spike cleaning, gap filling | `pipeline.py:229` |
| 2 | `patient_onboarding.py` | Determine available data & models | `pipeline.py:235` |
| 3 | `metabolic_engine.py` | Physics: supply/demand decomposition | `pipeline.py:241` |
| 4a–4e | `event_detector`, `hypo_predictor`, `clinical_rules`, `pattern_analyzer` | Risk, clinical metrics, patterns | `pipeline.py:251–330` |
| 5 | `meal_detector.py` | Meal event extraction | `pipeline.py:331` |
| 5b | `clinical_rules.py` | Correction energy, AID compensation, fidelity | `pipeline.py:412` |
| 5c | `natural_experiment_detector.py` | Fasting/meal/correction/UAM windows | `pipeline.py:448` |
| 6a | `settings_optimizer.py` | Optimal per-period settings from NE | `pipeline.py:459` |
| 6 | `settings_advisor.py` | Counterfactual TIR simulation + advisories | `pipeline.py:470` |
| 7 | `recommender.py` | Prioritized action recommendations | `pipeline.py:544` |
| 8–11 | DIA analysis, hypo warning, phenotyping, loop quality | Advanced analytics | `pipeline.py:553–605` |

**Design target**: <500ms per patient.  
[SOURCE: `pipeline.py:7` — "Target latency: <500ms per patient"]

**Graceful degradation**:  
- No insulin data → skip metabolic engine, use BG-only risk  
- No carbs → skip CR scoring, neutral score  
- <1 week → skip pattern analysis and meal prediction  
[SOURCE: `pipeline.py:10–13`]

---

## 2. ISF Optimization — The Dominant Lever

ISF correction contributes **85% of predicted TIR gain** from settings optimization.  
[SOURCE: `settings_optimizer.py:71` — `TIR_COEFF_ISF = 0.85`]

### 2.1 ISF Discrepancy Detection

**Function**: `advise_isf()` in `settings_advisor.py:327–373`

**Finding**: Effective ISF is **2.91× profile ISF** on average across all patients. 100% of patients have ISF underestimated (effective ISF is always higher than profile).  
[SOURCE: `settings_advisor.py:332` — "effective ISF is 2.91× profile ISF on average (EXP-747)"]  
[SOURCE: `docs/60-research/natural-experiments-settings-optimization-report.md` — EXP-1703: mean mismatch 2.30×, 7,534 corrections]

**Mechanism**: Conservative recommendation — moves ISF **25%** toward observed effective value per cycle.  
[SOURCE: `settings_advisor.py:347` — `adjustment_pct = 25.0`]

**Per-patient ISF mismatch (from EXP-1703)**:

| Patient | Profile ISF | Effective ISF | Mismatch | N corrections |
|---------|-------------|---------------|----------|---------------|
| a | 48.6 | 62.2 | 1.28× | 151 |
| c | 75.0 | 171.0 | 2.28× | 1,164 |
| d | 40.0 | 145.7 | 3.64× | 809 |
| e | 35.5 | 153.3 | **4.32×** | 1,482 |
| i | 50.0 | 156.3 | 3.13× | 3,241 |

[SOURCE: `docs/60-research/natural-experiments-settings-optimization-report.md` — EXP-1703 table]

### 2.2 Power-Law Dose-Response (ISF Nonlinearity)

**Function**: `advise_isf_nonlinearity()` in `settings_advisor.py:385–465`

**Model**: ISF(dose) = ISF_base × dose^(−β), where **β = 0.9** (population).  
[SOURCE: `settings_advisor.py:381` — `_POPULATION_ISF_BETA = 0.9`]  
[SOURCE: `settings_advisor.py:59` — `_POWER_LAW_BETA = 0.9  # from EXP-2511`]

**Clinical meaning**: A 2U correction is **46% less effective per unit** than 1U. A 3U correction achieves only ~1.1× the glucose drop of 1U, not 3×.  
[SOURCE: `settings_advisor.py:393–396`]

**Causal validation**: 4 independent methods (stratification, propensity matching, matched pairs, BG strata). 17/17 patients with sufficient corrections show the effect (p<0.0001).  
[SOURCE: `docs/60-research/therapy-settings-synthesis-2026-04-11.md:36–37` — EXP-2523]

**Split-dose implication**: 2×1U corrections spaced 30+ min apart theoretically achieve **1.87×** the drop of a single 2U dose. However, this is empirically confounded (actual ratio = 0.39×) due to glucose difficulty selection bias.  
[SOURCE: `docs/60-research/therapy-settings-synthesis-2026-04-11.md:40` — "Split dosing (2×1U, 30+ min apart) theoretically achieves 1.87× the drop"]  
[SOURCE: `docs/60-research/therapy-settings-synthesis-2026-04-11.md:269` — EXP-2522b "empirically 0.39×"]

**Fires when**: Typical correction dose > 1.5U and ≥3 days of data.  
[SOURCE: `settings_advisor.py:382` — `_ISF_NONLINEARITY_DOSE_THRESHOLD = 1.5`]  
[SOURCE: `settings_advisor.py:62` — `MIN_DATA_DAYS = 3.0`]

### 2.3 Circadian ISF Variation

**Functions**: `advise_circadian_isf()`, `advise_circadian_isf_profiled()` in `settings_advisor.py`

**Finding**: ISF varies **2–4× within a single day** (up to 9× in extreme patients). A 2-zone day/night schedule captures 61–90% of the benefit.  
[SOURCE: `settings_advisor.py:6` — "EXP-2271 (circadian ISF 4.6-9×, 2-zone captures 61-90%)"]

**Population circadian profile (EXP-2051)**:

| Time Block | ISF (mg/dL/U) | Interpretation |
|------------|---------------|----------------|
| 10am–1pm | 112–126 | **Peak** — best correction window |
| 4pm–6pm | 71–99 | **Nadir** — insulin least effective |
| 8am | — | Worst TIR hour (59%) |
| 5pm | — | Best TIR hour (84%) |

[SOURCE: `docs/60-research/circadian-therapy-report-2026-04-10.md` — EXP-2051]

**Per-patient circadian ratios**: Patient e = 4.30×, patient a = 3.98×, patient c = 1.91× (lowest).  
[SOURCE: `docs/60-research/circadian-therapy-report-2026-04-10.md` — EXP-2051]

### 2.4 Time-Segmented ISF

**Function**: `advise_isf_segmented()` in `settings_advisor.py:767–845`

**Triggers**: When ISF variation >50% across day and ≥7 days of data. Recommends 2–4 ISF segments for time periods where ISF differs >20% from average.  
[SOURCE: `settings_advisor.py:793–794` — `if patterns.isf_variation_pct < 50.0: return []` and `if days_of_data < 7.0: return []`]

### 2.5 Natural Experiment ISF Extraction

**Function**: `_extract_isf_schedule()` in `settings_optimizer.py:237–301`

**Method**: Uses correction response curves (BG delta / bolus dose). Prefers exponential-fit `curve_isf` when available, falls back to `simple_isf`.  
[SOURCE: `settings_optimizer.py:241–246`]

**Confidence grading**: ≥10 correction windows per period = "high", ≥3 = "medium", <3 = "low".  
[SOURCE: `settings_optimizer.py:58–59` — `MIN_EVIDENCE_HIGH = 10`, `MIN_EVIDENCE_MEDIUM = 3`]

**Bootstrap CI**: 1,000 bootstrap samples, 95% confidence interval on median ISF per period.  
[SOURCE: `settings_optimizer.py:65–67` — `BOOTSTRAP_N = 1000`, `BOOTSTRAP_CI = 0.95`]

---

## 3. Basal Rate Optimization

### 3.1 Overnight Drift Assessment

**Function**: `assess_overnight_drift()` in `settings_advisor.py`

**Phenotypes**: Classifies patients into 5 overnight phenotypes: stable, under-basaled, over-basaled, dawn phenomenon, loop-dependent.  
[SOURCE: `settings_advisor.py` — `OvernightPhenotype` enum]

**Finding**: 18/19 patients are miscalibrated. Only 1 patient (j) is well-calibrated. Mean overnight basal suspension rate is 60%. 14/19 patients are suspension-dominant (Loop primarily suspends basal rather than increasing it).  
[SOURCE: `docs/60-research/therapy-settings-synthesis-2026-04-11.md:161–164` — EXP-2371]  
[SOURCE: `docs/60-research/therapy-settings-synthesis-2026-04-11.md:176–179` — EXP-2391, EXP-2392]

**Critical insight**: "Scheduled basal is fiction for AID users." The loop rewrites it constantly. Settings quality does NOT predict TIR outcomes (workload vs TIR: r = −0.165).  
[SOURCE: `docs/60-research/therapy-settings-synthesis-2026-04-11.md:179`]

### 3.2 Basal Adequacy Advisory

**Function**: `advise_basal()` in `settings_advisor.py:169–265`

**Method**: Uses overnight (00:00–06:00) glucose drift to assess basal adequacy. Simulates TIR with 10%, 15%, and 20% basal adjustments.  
[SOURCE: `settings_advisor.py:201–211` — grid search over `[0.10, 0.15, 0.20]`]

**Output**: Direction (increase/decrease), magnitude (%), current and suggested values, predicted TIR delta, confidence score.

**Minimum data**: 3 days for any recommendation, 14 days for full confidence.  
[SOURCE: `settings_advisor.py:62–63` — `MIN_DATA_DAYS = 3.0`, `HIGH_CONFIDENCE_DAYS = 14.0`]

### 3.3 Natural Experiment Basal Extraction

**Function**: `_extract_basal_schedule()` in `settings_optimizer.py:160–234`

**Method**: Uses fasting/overnight drift (mg/dL/hr) divided by profile ISF to compute basal adjustment in U/hr. Positive drift → increase basal; negative drift → decrease.  
[SOURCE: `settings_optimizer.py:166–170`]

**5 time periods**: overnight (0–6), morning (6–10), midday (10–14), afternoon (14–18), evening (18–24).  
[SOURCE: `settings_optimizer.py:48–54`]

**Safety clamp**: Maximum ±50% basal change from profile.  
[SOURCE: `settings_optimizer.py:64` — `BASAL_CLAMP_FACTOR = 0.5`]

### 3.4 Dawn Phenomenon Detection

**In** `natural_experiment_detector.py`:  
Dawn phenomenon windows detected when fasting 4–8 AM glucose acceleration exceeds 3.0 mg/dL/h.  
[SOURCE: `natural_experiment_detector.py:52` — `DAWN_EFFECT_THRESH = 3.0`]

**Prevalence**: 6/19 patients show dawn phenomenon. Only 6am shows genuine under-basaling (+5 mg/dL/hr); all other daytime hours show over-basaling (−4 to −8 mg/dL/hr).  
[SOURCE: `docs/60-research/circadian-therapy-report-2026-04-10.md` — EXP-2052]

---

## 4. Carb Ratio Optimization

### 4.1 CR Adequacy Assessment

**Function**: `advise_cr_adequacy()` in `settings_advisor.py`

**Finding**: Effective CR = **1.47× profile CR** (population median). Patients systematically under-dose meals — they use 47% more carbs per unit of insulin than their profile says.  
[SOURCE: `docs/60-research/therapy-settings-synthesis-2026-04-11.md:88` — EXP-2535b]

**From earlier research** (EXP-1705): Effective CR = 73% of profile CR (looking from the other direction — the profile CR is 27% too aggressive). 3,847 meal windows analyzed.  
[SOURCE: `docs/60-research/natural-experiments-settings-optimization-report.md` — EXP-1705]

### 4.2 CR Effectiveness Simulation

**Function**: `advise_cr()` in `settings_advisor.py:268–324`

**Method**: Uses CR effectiveness score and post-meal excursion analysis. Simulates TIR with 10%, 15%, 20% CR adjustments during meal hours (5:00–21:00).  
[SOURCE: `settings_advisor.py:292–296` — grid search, `hour_range=(5.0, 21.0)`]

**Trigger**: Fires when CR score < 40/100 (poor).  
[SOURCE: `settings_advisor.py:281` — `if clinical.cr_score >= 40: return None`]

### 4.3 Context-Aware CR

**Function**: `advise_context_cr()` in `settings_advisor.py`

**Research**: EXP-2341. Using pre-meal BG + time-of-day + IOB as context improves CR prediction R² by +0.28.  
[SOURCE: `settings_advisor.py:7` — "EXP-2341 (context-aware CR: pre-BG + time + IOB, R²+0.28)"]

### 4.4 Natural Experiment CR Extraction

**Function**: `_extract_cr_schedule()` in `settings_optimizer.py:304–394`

**Method**: Effective CR = carbs_g / (bolus_U + excursion_mg_dl / ISF). Filters to meals ≥5g carbs and ≥0.1U bolus. Valid CR range: 1.0–100.0 g/U.  
[SOURCE: `settings_optimizer.py:328–336`]  
[SOURCE: `settings_optimizer.py:63` — `CR_RANGE = (1.0, 100.0)`]

**Higher evidence bar**: Meals have more variability, so the "high" confidence threshold is 15 windows (vs 10 for ISF/basal).  
[SOURCE: `settings_optimizer.py:363` — `cr_min_high = 15`]

### 4.5 CR–ISF Independence

CR and ISF are **independent** parameters (r = 0.17). They should be tuned separately, not linked.  
[SOURCE: `docs/60-research/therapy-settings-synthesis-2026-04-11.md:109` — EXP-2535b]

### 4.6 Nonlinearity Cancellation — Linear Dosing Remains Valid

CR is individually nonlinear (sub-linear absorption: larger meals have less BG rise per gram). ISF is individually nonlinear (diminishing returns: larger boluses less effective per unit). These go in **opposite directions** and approximately **cancel**, meaning standard linear dosing (carbs/CR) is a valid approximation.  
[SOURCE: `docs/60-research/therapy-settings-synthesis-2026-04-11.md:127–139` — EXP-2537a, net R² improvement ~+0.001–0.005]

### 4.7 Circadian CR Pattern

Breakfast is the hardest meal to dose (highest excursion, 58.2 mg/dL mean). Dinner excursions are 77.3 mg/dL — worst period. Lunch is best-controlled (46.3 mg/dL).  
[SOURCE: `docs/60-research/therapy-operationalization-report-2026-04-10.md` — EXP-1336]

**Dinner/breakfast ISF ratio**: 1.9×. The same carbs spike nearly 2× more at dinner than breakfast due to lower afternoon ISF combined with dawn phenomenon amplifying morning meal impact.  
[SOURCE: `docs/60-research/circadian-therapy-report-2026-04-10.md` — EXP-2054]

---

## 5. Correction Threshold Advisory

**Function**: `advise_correction_threshold()` in `settings_advisor.py:523–664`

**Finding**: Population optimal correction threshold ≈ **166 mg/dL**. Per-patient range: 130–290 mg/dL.  
[SOURCE: `settings_advisor.py:512` — `_POPULATION_CORRECTION_THRESHOLD = 166`]  
[SOURCE: `settings_advisor.py:513` — `_CORRECTION_THRESHOLD_RANGE = (130, 290)`]

**Evidence**: Corrections from BG 130–180 rebound **75% of the time**. This is regression to the mean, NOT counter-regulation — higher nadirs rebound MORE.  
[SOURCE: `docs/60-research/therapy-settings-synthesis-2026-04-11.md:59–61` — EXP-2526c]

**Per-patient calibration**: When ≥10 correction events available, scans BG bins (130–290, 10 mg/dL steps) to find per-patient zero-crossing for net benefit.  
[SOURCE: `settings_advisor.py:519` — `_MIN_CORRECTION_EVENTS = 10`]  
[SOURCE: `settings_advisor.py:628–664` — `_compute_patient_threshold()`]

---

## 6. Controller-Specific Behavior

**Module**: `recommender.py:178–349`

Each AID controller has a distinct compensation style that affects how much to trust observed metrics.

| Controller | Suspension % | ISF Trust | CR Trust | Settings Visibility | Compensation Style |
|-----------|-------------|-----------|----------|--------------------|--------------------|
| **Loop** | 55% | 0.30 | 0.40 | 0.30 | Compensating |
| **Trio** | 45% | 0.35 | 0.45 | 0.35 | Passive |
| **AAPS** | 30% | 0.60 | 0.60 | 0.60 | Balanced |
| **OpenAPS** | 20% | 0.70 | 0.65 | 0.70 | Aggressive |
| Unknown | 0% | 0.50 | 0.50 | 0.50 | — |

[SOURCE: `recommender.py:194–264` — `_CONTROLLER_PROFILES` dict]

**Confidence adjustment**: Each recommendation's confidence score is multiplied by the controller's trust factor for that parameter.  
[SOURCE: `recommender.py:338–343` — `rec.confidence *= behavior.isf_trust`]

**Loop-specific note**: "Loop uses aggressive temp basal suspension to prevent lows. This masks ISF errors: observed effective ISF may be 1.5-2.2× higher than profile due to loop compensation. Settings changes may show <1% TIR impact because Loop re-compensates. Focus recommendations on CR and pre-bolus timing."  
[SOURCE: `recommender.py:202–208`]

**Detection heuristic**: Auto-detects controller from metadata or suspension fraction. >60% suspension → Loop, >40% → Trio, >15% → AAPS.  
[SOURCE: `recommender.py:297–306`]

---

## 7. Profile Generation & Export

**Module**: `profile_generator.py`

Generates complete AID profiles in **4 formats** from optimized settings:

| Format | Time Representation | Reference Source |
|--------|--------------------|--------------------|
| **oref0** | Minutes from midnight + "HH:MM:SS" | `externals/oref0/lib/profile/index.js` |
| **Loop** | Seconds from midnight (TimeInterval) | `externals/LoopWorkspace/LoopKit/LoopKit/DailyValueSchedule.swift` |
| **Trio** | Dual: minutes + "HH:MM:SS" | `externals/Trio/Trio/Sources/Models/BasalProfileEntry.swift` |
| **Nightscout** | "HH:MM" strings (REST API) | `externals/cgm-remote-monitor/lib/api3/generic/` |

[SOURCE: `profile_generator.py:1–20`, `106–133`]

**Physiological constraints** (enforced before output):

| Parameter | Min | Max | Unit |
|-----------|-----|-----|------|
| Basal rate | 0.025 | 10.0 | U/hr |
| ISF | 10.0 | 500.0 | mg/dL/U |
| CR | 3.0 | 150.0 | g/U |
| DIA | 2.0 | 12.0 | hours |

[SOURCE: `profile_generator.py:39–46` — `CONSTRAINTS` dict]

**Warnings generated**: Low-confidence blocks flagged; changes >50% flagged with "verify with endocrinologist".  
[SOURCE: `profile_generator.py:186–199`]

---

## 8. Safety Guardrails

### 8.1 Per-Cycle Safety Clamp (25%)

**Research**: EXP-2626 found that ISF discrepancy advisories can suggest extreme changes (±68–100%). Standard clinical practice is ≤10–15% per adjustment cycle.  
[SOURCE: `tools/cgmencode/production/exp_safety_guardrails_2626.py:3–8`]

The experiment confirmed: 7/10 extreme advisories (>50% magnitude) come from ISF advisors specifically. Capping at 25% preserves advisory ranking (Kendall τ > 0.8).  
[SOURCE: `exp_safety_guardrails_2626.py:16–18` — H1, H2, H3 hypotheses]

### 8.2 Advisory Coherence Audit

**Research**: EXP-2624 audited all 17 advisories across 16 patients: **0 contradictions** (same parameter, opposite direction). CR dominates top-3 advisories.  
[SOURCE: `tools/cgmencode/production/exp_advisory_audit_2624.py:1–22`]  
[SOURCE: stored memory — "Advisory audit: 0 contradictions across 16 patients"]

### 8.3 Basal Clamp

Maximum ±50% basal change from profile value.  
[SOURCE: `settings_optimizer.py:64` — `BASAL_CLAMP_FACTOR = 0.5`]

### 8.4 Confidence Grading

| Grade | Total Evidence Windows | Period-Settings at Medium+ |
|-------|----------------------|---------------------------|
| A | ≥100 | ≥12 |
| B | ≥50 | ≥8 |
| C | ≥20 | ≥4 |
| D | <20 | <4 |

[SOURCE: `settings_optimizer.py:407–424` — `_grade_overall_confidence()`]

### 8.5 Minimum Data Requirements

| Parameter | Minimum | Full Confidence |
|-----------|---------|-----------------|
| Any recommendation | 3 days | 14 days |
| ISF segmented | 7 days | 14 days |
| Correction threshold (per-patient) | 10 events | 50 events |

[SOURCE: `settings_advisor.py:62–63`, `settings_advisor.py:519–520`]

### 8.6 Prediction Bias: Do NOT Correct

"Naive bias correction is DANGEROUS for 8/10 patients: removing the negative bias removes the loop's defensive suspension, which prevents real hypos. Report the bias as informational only."  
[SOURCE: `recommender.py:151–153`]

---

## 9. Forward Simulation (Digital Twin)

**Module**: `forward_simulator.py`

### 9.1 Two-Component DIA Model

| Component | Fraction | Time Constant | Mechanism |
|-----------|----------|---------------|-----------|
| Fast | 63% | τ = 0.8h | Insulin-mediated glucose uptake |
| Persistent | 37% | τ = 12h | Residual IOB + loop basal adjustment |

[SOURCE: `metabolic_engine.py:40–42` — `_FAST_TAU_HOURS = 0.8`, `_PERSISTENT_FRACTION = 0.37`, `_PERSISTENT_WINDOW_HOURS = 12.0`]  
[SOURCE: `forward_simulator.py:50` — `_FAST_FRACTION = 1.0 - _PERSISTENT_FRACTION  # 0.63`]

**⚠ Mechanism correction** (EXP-2534): Originally attributed to hepatic glucose production (HGP) suppression. Overnight matched-pair validation (280 pairs) showed the persistent effect is IOB underestimation by standard DIA curves + loop compensation — not liver physiology. The model remains **predictively valid** (R²=0.827).  
[SOURCE: `docs/60-research/therapy-settings-synthesis-2026-04-11.md:48–52` — EXP-2534]

### 9.2 Power-Law ISF Dampening

effective_isf_mult = isf_multiplier^(1 − β), where β = 0.9.  
[SOURCE: `settings_advisor.py:128–131`]  
[SOURCE: `forward_simulator.py:51` — `_POWER_LAW_BETA = 0.9`]

Prevents overestimating large ISF corrections. Without this, the persistent tail overamplifies perturbations (Model B MAE=3.23pp vs Model C MAE=0.30pp).  
[SOURCE: `settings_advisor.py:92–94`]

### 9.3 Carb Absorption Model

| Parameter | Value | Source |
|-----------|-------|--------|
| Absorption window | 3.0h | `forward_simulator.py:57` |
| Gut delay τ | 20 min | `forward_simulator.py:58` — EXP-1932 |
| Peak time | 71 min | `forward_simulator.py:59` — EXP-1934 |

### 9.4 Basal Neutrality

The model defines the patient's basal rate as metabolic equilibrium. All effects are relative:

```
dBG = -excess_insulin_effect × ISF
      + carb_rise × (ISF / CR)
      + decay_toward_120
      + noise
```

Where `excess_insulin = total_absorption − scheduled_basal_absorption`.  
[SOURCE: `forward_simulator.py:10–27`]

### 9.5 Simulation Accuracy

| Metric | Two-Component Model | Single-Decay Model |
|--------|--------------------|--------------------|
| MAE | 0.30 pp | 2.10 pp |
| r | 0.933 | 0.129 |

[SOURCE: `settings_advisor.py:22–23`]

---

## 10. Key Paradoxes & Limitations

### 10.1 The Descriptive-Prescriptive Paradox (EXP-2641/2642)

The model that best *describes* correction glucose drops (per-patient log-ISF, bias = −3 mg/dL) is the **worst prescriber** (recommends 2.3× the optimal dose). The apparent ISF measured from corrections includes the AID controller's compensatory response (basal withdrawal, suspension). "Fixed ISF + feedback loop is near-optimal."  
[SOURCE: `docs/60-research/egp-prescriptive-paradox-report-2026-04-13.md:1–100`]

**Implication**: Do not naively use observed ISF for dosing. The production pipeline uses **conservative 25% adjustment per cycle** rather than full ISF correction.

### 10.2 AID Compensation Theorem (EXP-2629/2630)

IOB-hypo correlation is **reversed causation**: IOB drops 55% before hypo crossing because the AID withdraws insulin. AID-active recovery = 7.6 vs suspended = 3.6 mg/dL/hr (p < 0.0001). Controller, settings, and physiology are **irreducibly coupled** — single-factor recovery models all have negative R².  
[SOURCE: `docs/60-research/egp-deconfounding-report-2026-04-13.md`]  
[SOURCE: stored memory — "AID Compensation Paradox"]

### 10.3 All Recovery Models Fail (EXP-2634/2635)

All 5 recovery models (null, mean-reversion, IOB-decay, biexp-decay, Hill EGP) have negative R² (−2.4 to −3.2) on 219 properly-filtered corrections. Bolus size is the only significant predictor (r = −0.307, negative).  
[SOURCE: stored memory — "ALL 5 recovery models have negative R²"]

### 10.4 Irreducible Hypo Rate

The hypo rate floor is approximately **16%**, irreducible by settings optimization alone.  
[SOURCE: stored memory — "16% hypo rate is irreducible"]

---

## 11. Research-Only Findings (Not Yet Productionized)

| Finding | Why Not Productionized | Evidence | Priority |
|---------|----------------------|----------|----------|
| Two-component DIA (fast τ=0.8h + 37% persistent) | Needs AID firmware changes | R²=0.827 (EXP-2525) | Medium |
| Split-dose recommendation (87% theoretical improvement) | Empirically confounded (0.39×); needs RCT | EXP-2522 | Low |
| 15–30g meal sweet spot (best post-meal TIR) | Lifestyle guidance, not settings change | EXP-2537d | Medium |
| Loop workload metric (18/19 saturated) | Insight, not actionable | EXP-2391 | Low |
| CR × ISF cancellation | Confirms linear dosing — no action needed | EXP-2537a | Low |
| Patience mode (cap SMBs when IOB>2×median) | Saves 34–82% SMBs, reduces hypos 0.1–2.0pp | EXP-2662 | Medium |
| SC suppression ceiling (~30% of hepatic EGP) | Correlates with sticky hypers (r=−0.60) | EXP-2656 | Medium |
| Demand-phase ISF (2–10× smaller than apparent ISF) | Wins at all prediction horizons but dosing paradox applies | EXP-2651 | Medium |

[SOURCE: `docs/60-research/therapy-settings-synthesis-2026-04-11.md:239–248`]

---

## 12. Quantitative Summary

| Metric | Value | Source File | EXP |
|--------|-------|------------|-----|
| ISF universal underestimation | 2.3× mean (1.2–4.3×) | `natural-experiments-settings-optimization-report.md` | 1703 |
| ISF power-law β | 0.9 | `settings_advisor.py:381` | 2511 |
| ISF circadian range | 2–9× within-day | `settings_advisor.py:6` | 2271 |
| CR effective/profile ratio | 1.47× (under-dosing) | `therapy-settings-synthesis-2026-04-11.md:88` | 2535b |
| CR–ISF correlation | r = 0.17 (independent) | `therapy-settings-synthesis-2026-04-11.md:109` | 2535b |
| Basal miscalibrated | 18/19 patients | `therapy-settings-synthesis-2026-04-11.md:161` | 2371 |
| Loop suspension rate | 52–96% (median 55%) | `recommender.py:198` | 2081 |
| Optimal correction threshold | 166 mg/dL (130–290) | `settings_advisor.py:512–513` | 2528 |
| Population DIA | 6.0h (vs 5h assumed) | `therapy-operationalization-report-2026-04-10.md` | 1334 |
| Combined predicted TIR gain | +2.8% | `settings_optimizer.py:70–72` | 1717 |
| ISF share of TIR gain | 85% | `settings_optimizer.py:71` | 1717 |
| Advisory audit contradictions | 0/16 patients | `exp_advisory_audit_2624.py` | 2624 |
| Safety clamp per cycle | 25% max | `exp_safety_guardrails_2626.py:10` | 2626 |
| Basal clamp | ±50% max | `settings_optimizer.py:64` | — |
| Forward sim accuracy | MAE=0.30pp, r=0.933 | `settings_advisor.py:22–23` | 2551 |
| Hypo rate floor | ~16% irreducible | `egp-prescriptive-paradox-report-2026-04-13.md` | 2641 |
| Natural experiment census | 50,810 windows | `natural_experiment_detector.py:1–22` | 1551 |
| Production test coverage | 226 tests, 46 classes | `therapy-settings-synthesis-2026-04-11.md:237` | — |

---

## 13. Verification Checklist

To verify any claim in this report:

1. **Source code constants**: Open the cited file at the cited line. Constants are defined as module-level variables with comments noting their experiment origin.

2. **Research findings**: Open the cited report in `docs/60-research/`. Search for the EXP number. Tables contain per-patient data and statistical results.

3. **Experiment scripts**: R&D scripts are at `tools/cgmencode/exp_*_NNNN.py`. Production validation scripts are at `tools/cgmencode/production/exp_*.py`. Each contains hypotheses in the docstring and results in the output JSON.

4. **Cross-reference paths**:
   - Claim about ISF β=0.9 → `settings_advisor.py:381` → `settings_advisor.py:59` → `forward_simulator.py:51` → `therapy-settings-synthesis-2026-04-11.md:33` → `exp_dose_isf.py` (EXP-2511)
   - Claim about correction threshold 166 → `settings_advisor.py:512` → `exp_correction_threshold.py` (EXP-2528) → `therapy-settings-synthesis-2026-04-11.md:63`
   - Claim about controller trust → `recommender.py:194–264` → `exp_advisory_audit_2624.py` (EXP-2624)

5. **Experiment output data**: JSON results are at `externals/experiments/exp-NNNN_*.json` (gitignored but reproducible from scripts).

---

*Report generated 2026-04-18. All [SOURCE] citations verified against repository at commit HEAD.*
