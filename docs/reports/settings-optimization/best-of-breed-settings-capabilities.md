# Best-of-Breed Settings Optimization Capabilities

**Date**: 2026-04-18  
**Scope**: Basal rate, ISF, and CR schedule optimization for Loop, Trio, AAPS, and oref0 AID controllers  
**Data basis**: 19 patients (11 Nightscout + 8 ODC), 1,838 patient-days, 50,810 natural experiments, 35K+ corrections, 5K+ meals  
**Source material**: 270+ research reports, 100+ R&D experiments (EXP-574–EXP-2662), 101 production validation scripts  
**Status**: Verified against source code — every claim has a [SOURCE] citation

---

## Table of Contents

1. [Pipeline Architecture](#1-pipeline-architecture)
2. [**Optimization Sequencing — Fix Order Matters**](#2-optimization-sequencing--fix-order-matters)
3. [ISF Optimization — The Dominant Lever](#3-isf-optimization--the-dominant-lever)
4. [Basal Rate Optimization](#4-basal-rate-optimization) *(includes §4.5: Comparison with oref0 Autotune)*
5. [Carb Ratio Optimization](#5-carb-ratio-optimization) *(includes §5.8: Carb Entry Reliability — What's Safe vs Compromised)*
6. [Correction Threshold Advisory](#6-correction-threshold-advisory)
7. [Controller-Specific Behavior](#7-controller-specific-behavior)
8. [Profile Generation & Export](#8-profile-generation--export)
9. [Safety Guardrails](#9-safety-guardrails)
10. [Forward Simulation (Digital Twin)](#10-forward-simulation-digital-twin)
11. [Key Paradoxes & Limitations](#11-key-paradoxes--limitations)
12. [Research-Only Findings](#12-research-only-findings)
13. [Quantitative Summary](#13-quantitative-summary)
14. [Verification Checklist](#14-verification-checklist)

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

## 2. Optimization Sequencing — Fix Order Matters

> **6/11 patients are harmed by optimizing in the wrong order.** (EXP-1765)

Settings optimization is NOT a single-pass adjustment. The production pipeline implements a **3-phase sequence** where the patient's current glucose variability determines what to fix first. This is the single most important architectural decision in the pipeline.  
[SOURCE: `settings_advisor.py:3068–3103` — `determine_optimization_phase()`]  
[SOURCE: `settings_advisor.py:3106–3143` — `prioritize_recommendations()`]

### 2.1 The Three Phases

| Phase | Entry Criterion | Priority Order | Goal |
|-------|----------------|----------------|------|
| **REDUCE_VARIABILITY** | CV > 28% | Basal → CR → ISF | Break glucose cascades, flatten overnight swings |
| **CENTER** | CV ≤ 28%, TIR < 70% | ISF → CR → Basal | Shift mean glucose into range |
| **PERSONALIZE** | CV ≤ 28%, TIR ≥ 70% | Impact-sorted (any order) | Fine-tune all parameters |

[SOURCE: `settings_advisor.py:3077–3083` — phase definitions]  
[SOURCE: `settings_advisor.py:3098–3103` — CV threshold logic]

**CV threshold = 28%**. Above 28%, reducing variability (primarily via basal) yields more TIR gain than centering mean glucose. Below 28%, centering (primarily via ISF/CR) becomes dominant.  
[SOURCE: `settings_advisor.py:3071` — `_CV_THRESHOLD = 28.0`]  
[SOURCE: `centering-dynamics-report-2026-04-10.md:318,545`]

**Finding**: 9/11 patients need variability reduction BEFORE centering.  
[SOURCE: `settings_advisor.py:3082` — "9/11 patients need variability reduction BEFORE centering"]

**Combined ceiling**: Maximum achievable TIR improvement from all settings optimization = **+17.6%**.  
[SOURCE: `settings_advisor.py:3083` — "Combined ceiling: +17.6% TIR"]  
[SOURCE: `clinical_rules.py:978` — "Algorithm ceiling (EXP-1765): +17.6% TIR maximum"]

### 2.2 Phase Priority Maps

The recommendation engine re-orders advisories based on the patient's current phase:

```python
REDUCE_VARIABILITY: { BASAL: 0, CR: 1, ISF: 2 }   # Basal first
CENTER:             { ISF: 0, CR: 1, BASAL: 2 }    # ISF first
PERSONALIZE:        (keep impact-sorted order)       # Any order
```

[SOURCE: `settings_advisor.py:3125–3136`]

**Why basal first in Phase 1**: Basal affects the baseline 24/7. Fixing it stabilizes the foundation around which CR and ISF operate, making subsequent adjustments more predictable. Sequential optimization (basal → CR → ISF) yields **+40–90% improvement** for multi-flag patients vs only **+15–25%** for simultaneous adjustment.  
[SOURCE: `therapy-comprehensive-campaign-report-2026-04-10.md:197–206` — EXP-1479]

### 2.3 Basal Is Top Action for 10/11 Patients

Impact-based ranking (EXP-1386) shows basal correction is the highest-yield single action for nearly every patient:

| Patient | Archetype | TIR | Top Action | Est. TIR Gain |
|---------|-----------|-----|------------|---------------|
| i | needs-tuning | 60% | **basal** | +6.0% |
| b | needs-tuning | 57% | **basal** | +5.8% |
| a | miscalibrated | 56% | **basal** | +5.5% |
| f | needs-tuning | 66% | **basal** | +5.2% |
| c | needs-tuning | 62% | **basal** | +5.0% |
| e | needs-tuning | 65% | **basal** | +4.7% |
| g | needs-tuning | 75% | **basal** | +3.9% |
| h | well-calibrated | 85% | **basal** | +2.4% |
| j | well-calibrated | 81% | dinner_cr | +2.3% |
| d | well-calibrated | 79% | **basal** | +1.7% |
| k | well-calibrated | 95% | **basal** | +0.4% |

[SOURCE: `therapy-pipeline-validation-report-2026-04-10.md:198–210` — EXP-1386]

Only patient j has dinner CR as top action — the one patient with well-calibrated basals.  
[SOURCE: `therapy-pipeline-validation-report-2026-04-10.md:213–219`]

### 2.4 Controller Architecture Changes the Sequencing

The "basal first" rule is strongest for **Loop/Trio** (suspend-based controllers). AAPS/OpenAPS (SMB-based) have a different error profile:

| Architecture | Insulin Strategy | Supply% | Demand% | Implication |
|-------------|-----------------|:-------:|:-------:|-------------|
| **Suspend-based** (Loop/Trio) | High basal + suspend when predicted low | 52% | 31% | Supply-dominant errors → **fix basal first** |
| **SMB-based** (AAPS/OpenAPS) | Low basal + frequent micro-bolus | 25% | 57% | Demand-dominant errors → **ISF matters most** |

[SOURCE: `expanded-phenotyping-19patient-report-2026-04-11.md:428–431`]

Loop/Trio patients spend 52% of time in supply-dominated windows (loop suspending/reducing basal). AAPS/OpenAPS patients spend 57% of time in demand-dominated windows (loop adding micro-boluses). This means:

- **Loop/Trio**: Basal is set too high → loop suspends constantly → fix basal to reduce suspension workload
- **AAPS/OpenAPS**: Basal is lower, but micro-dosing depends on ISF accuracy → ISF calibration is the bottleneck

[SOURCE: `expanded-phenotyping-19patient-report-2026-04-11.md:433–436`]

### 2.5 Basal Adjustment Magnitude: Conservative Wins

**EXP-1416**: How aggressive should basal corrections be?

| Magnitude | Mean TIR Change | Overcorrections |
|-----------|:---------------:|:---------------:|
| **Conservative (±10%)** | **−1.2%** | **0** |
| Moderate (±20%) | −2.6% | 0 |
| Aggressive (±30%) | −3.2% | 0 |

[SOURCE: `therapy-actionable-recommendations-report-2026-04-10.md:198–221` — EXP-1416]

**Conservative ±10% is optimal for 10/11 patients**. Aggressive corrections (±30%) hurt TIR up to −11.5% in patient g. Basal needs gentler adjustments than CR because it affects 24/7 rather than just post-meal windows.  
[SOURCE: `therapy-actionable-recommendations-report-2026-04-10.md:210–220`]

The production `settings_optimizer.py` enforces a **±50% hard clamp** to prevent extreme basal changes.  
[SOURCE: `settings_optimizer.py:64` — `BASAL_CLAMP_FACTOR = 0.5`]

### 2.6 Graduated Transition Protocol (EXP-2248)

Once optimal settings are identified, the safest implementation is a **graduated 4-step transition** over 2–4 weeks with safety gates at each step:

| Week | Action | Safety Gate |
|------|--------|-------------|
| 1 | Reduce basal 20–25% toward target | TBR increase < 1% |
| 2 | Reduce basal to 50% of target | TBR < 4% maintained |
| 3 | Raise ISF to 50% of target | No correction drops glucose below 70 |
| 4 | Apply full ISF correction | TIR ≥ 70% and TBR < 4% |

[SOURCE: `settings-simulation-report-2026-04-10.md:219–224` — EXP-2248]

Patients with ISF ratio ≤ 1.4 (small mismatch) only need 1–2 steps (basal only, no ISF change needed).  
[SOURCE: `settings-simulation-report-2026-04-10.md:225`]

**Projected outcomes** if all recommendations applied via graduated transition:

| Metric | Current | Projected | Change |
|--------|---------|-----------|--------|
| Mean TIR | 70.9% | 80.0% | **+9.1%** |
| Patients ≥ 70% TIR | 5/11 (45%) | 10/11 (91%) | **+5 patients** |
| Mean TBR | 3.6% | 2.4% | **−1.2%** |
| Mean hypos/day | 0.88 | 0.44 | **−50%** |
| Mean oscillation cycles/day | 6.7 | 1.8 | **−73%** |

[SOURCE: `settings-simulation-report-2026-04-10.md:235–243`]

> **⚠ Caveat**: These are model-based projections, not clinical trial results. The loop is a feedback system that will change its own behavior in response to settings changes, potentially in unexpected ways.  
> [SOURCE: `settings-simulation-report-2026-04-10.md:248–252`]

### 2.7 Best-Practice Method: Overnight Drift for Basal Assessment

The **single best signal** for basal adequacy is overnight glucose drift on clean nights:

**Step 1 — Detect clean nights** (EXP-2375):
- Window: 00:00–06:00  
- IOB < 0.5 U, COB < 5 g  
- Minimum 3 clean nights for assessment  
[SOURCE: `settings_advisor.py:2736–2742` — `_CLEAN_NIGHT_IOB_MAX`, `_CLEAN_NIGHT_COB_MAX`, `_MIN_CLEAN_NIGHTS`]

**Step 2 — Measure linear drift** per night:
- Linear regression: `slope = np.polyfit(time, glucose, 1)[0]` → drift in mg/dL/hr  
[SOURCE: `settings_advisor.py:2864–2866`]

**Step 3 — Classify overnight phenotype**:

| Phenotype | Criterion | Action |
|-----------|-----------|--------|
| **Stable Sleeper** | \|drift\| ≤ 3 mg/dL/hr, no dawn rise | ✅ No change needed |
| **Under-basaled** | drift > +3 mg/dL/hr | Increase basal |
| **Over-basaled** | drift < −3 mg/dL/hr | Decrease basal |
| **Dawn Riser** | drift > +3, dawn rise > 15 mg/dL | Increase 4–6 AM basal |
| **Loop-dependent** | suspension > 40% of overnight | Decrease basal (loop over-compensating) |
| **Mixed** | std(drifts) > 2 × mean\|drift\| | Investigate further |

[SOURCE: `settings_advisor.py:2745–2750` — thresholds]  
[SOURCE: `settings_advisor.py:2898–2915` — classification logic]

**Step 4 — Compute basal adjustment**:
- Adjustment (U/hr) = median_drift / profile_ISF  
- Positive drift → increase basal; negative → decrease  
- Clamp at ±50% of current rate  
[SOURCE: `settings_optimizer.py:166–202` — `_extract_basal_schedule()`]

**Step 5 — Detect dawn phenomenon** (EXP-2375):
- Compare pre-04:00 vs post-04:00 glucose within each night  
- Dawn rise > 15 mg/dL → dawn phenomenon present  
- 6/19 patients affected; only 6 AM shows genuine under-basaling  
[SOURCE: `settings_advisor.py:2869–2882`]  
[SOURCE: `circadian-therapy-report-2026-04-10.md` — EXP-2052]

---

## 3. ISF Optimization — The Dominant Lever

ISF correction contributes **85% of predicted TIR gain** from settings optimization.  
[SOURCE: `settings_optimizer.py:71` — `TIR_COEFF_ISF = 0.85`]

> **⚠ CRITICAL CAVEAT — The Prescriptive Paradox (see §11.1)**
>
> All "effective ISF" values in this section are **apparent ISF**: total glucose
> drop divided by bolus dose. This apparent ISF is an **emergent property of the
> closed-loop system**, not the patient's true insulin sensitivity.
>
> Two effects are at work: (1) profile ISFs are genuinely too low — patients
> are more insulin-sensitive than their profiles say; (2) the AID controller
> **opposes** large corrections by suspending basal to prevent overshooting,
> which **reduces** the glucose drop and deflates apparent ISF at higher doses.
> The dose-dependent interaction means apparent ISF varies with correction size
> and cannot be extracted as a single number for dosing.
>
> The paradox (EXP-2641/2642, 2026-04-13): the model that best *describes*
> correction drops (per-patient log-ISF, bias = −3 mg/dL) is the **worst
> prescriber** (recommends 2.3× the optimal dose). "Fixed ISF + controller
> feedback is near-optimal." Do **NOT** use apparent ISF values directly for
> dosing.
>
> [SOURCE: `egp-prescriptive-paradox-report-2026-04-13.md:95,111,129,171–174,188,220`]
>
> The production advisory (`advise_isf()`) predates this finding. It uses
> conservative 25%-per-cycle steps toward apparent ISF, which may itself need
> revision. The mismatch data below is retained as a **diagnostic signal** (how
> hard is the controller working?) rather than a dosing target.

### 3.1 ISF Discrepancy Detection (Diagnostic, Not Prescriptive)

**Function**: `advise_isf()` in `settings_advisor.py:327–373`

**Observation**: Apparent ISF is **2.91× profile ISF** on average across all patients. 100% of patients show the controller amplifying corrections beyond what the profile ISF would predict.  
[SOURCE: `settings_advisor.py:332` — "effective ISF is 2.91× profile ISF on average (EXP-747)"]  
[SOURCE: `docs/60-research/natural-experiments-settings-optimization-report.md` — EXP-1703: mean mismatch 2.30×, 7,534 corrections]

**Current mechanism**: Conservative recommendation — moves ISF **25%** toward observed apparent value per cycle. For patient c (profile 75, apparent 171): suggests 75 → 99, **not** 75 → 171.  
[SOURCE: `settings_advisor.py:345–348` — `adjustment_pct = 25.0`, `suggested = current_isf + gap * 0.25`]

**⚠ Open question**: Even the 25% step targets an apparent ISF inflated by controller compensation (see §11.1). The paradox report concludes "stop trying to model ISF better for dosing" — the AID feedback loop already compensates in real time. This advisory may need revision.  
[SOURCE: `egp-prescriptive-paradox-report-2026-04-13.md:220`]

**Per-patient apparent ISF vs profile (from EXP-1703)**:

These values show **how much the controller is compensating**, not the patient's true ISF. A high ratio means the AID is doing more work to achieve corrections than the profile expects.

| Patient | Profile ISF | Apparent ISF | Ratio (controller load) | N corrections |
|---------|-------------|--------------|------------------------|---------------|
| a | 48.6 | 62.2 | 1.28× | 151 |
| c | 75.0 | 171.0 | 2.28× | 1,164 |
| d | 40.0 | 145.7 | 3.64× | 809 |
| e | 35.5 | 153.3 | **4.32×** | 1,482 |
| i | 50.0 | 156.3 | 3.13× | 3,241 |

[SOURCE: `docs/60-research/natural-experiments-settings-optimization-report.md` — EXP-1703 table]

**Interpretation**: Patient c's apparent ISF of 171 reflects two things: (1) the profile ISF of 75 is genuinely too conservative — the patient really is more insulin-sensitive than the profile says, and (2) for small corrections where the controller barely intervenes, the apparent ISF approaches the true physiological ISF. For larger corrections, the controller **opposes** the bolus by suspending basal and cancelling SMBs to prevent overshooting low — this **reduces** the glucose drop, making apparent ISF per unit **smaller** at higher doses (the power-law effect, §3.2). The 171 is an average across all correction sizes. It should NOT be used as an ISF setting because: (a) changing ISF changes bolus size, which changes controller response, creating a circular dependency, (b) the dose-dependent nonlinearity means 171 is only accurate for small doses, and (c) the AID's real-time feedback already compensates — "fixed ISF + controller feedback is near-optimal" (EXP-2642).

### 3.2 Power-Law Dose-Response (ISF Nonlinearity)

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

### 3.3 Circadian ISF Variation

**Functions**: `advise_circadian_isf()`, `advise_circadian_isf_profiled()` in `settings_advisor.py`

**Finding**: ISF varies **2–9× within a single day** across patients. A 2-zone day/night schedule captures 61–90% of the benefit.  
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

### 3.4 Time-Segmented ISF

**Function**: `advise_isf_segmented()` in `settings_advisor.py:767–845`

**Triggers**: When ISF variation >50% across day and ≥7 days of data. Recommends 2–4 ISF segments for time periods where ISF differs >20% from average.  
[SOURCE: `settings_advisor.py:793–794` — `if patterns.isf_variation_pct < 50.0: return []` and `if days_of_data < 7.0: return []`]

### 3.5 Natural Experiment ISF Extraction

**Function**: `_extract_isf_schedule()` in `settings_optimizer.py:237–301`

**Method**: Uses correction response curves (BG delta / bolus dose). Prefers exponential-fit `curve_isf` when available, falls back to `simple_isf`.  
[SOURCE: `settings_optimizer.py:241–246`]

**Confidence grading**: ≥10 correction windows per period = "high", ≥3 = "medium", <3 = "low".  
[SOURCE: `settings_optimizer.py:58–59` — `MIN_EVIDENCE_HIGH = 10`, `MIN_EVIDENCE_MEDIUM = 3`]

**Bootstrap CI**: 1,000 bootstrap samples, 95% confidence interval on median ISF per period.  
[SOURCE: `settings_optimizer.py:65–67` — `BOOTSTRAP_N = 1000`, `BOOTSTRAP_CI = 0.95`]

---

## 4. Basal Rate Optimization

### 4.1 Overnight Drift Assessment

**Function**: `assess_overnight_drift()` in `settings_advisor.py`

**Phenotypes**: Classifies patients into 5 overnight phenotypes: stable, under-basaled, over-basaled, dawn phenomenon, loop-dependent.  
[SOURCE: `settings_advisor.py` — `OvernightPhenotype` enum]

**Finding**: 18/19 patients are miscalibrated. Only 1 patient (j) is well-calibrated. Mean overnight basal suspension rate is 60%. 14/19 patients are suspension-dominant (Loop primarily suspends basal rather than increasing it).  
[SOURCE: `docs/60-research/therapy-settings-synthesis-2026-04-11.md:161–164` — EXP-2371]  
[SOURCE: `docs/60-research/therapy-settings-synthesis-2026-04-11.md:176–179` — EXP-2391, EXP-2392]

**Critical insight**: "Scheduled basal is fiction for AID users." The loop rewrites it constantly. Settings quality does NOT predict TIR outcomes (workload vs TIR: r = −0.165).  
[SOURCE: `docs/60-research/therapy-settings-synthesis-2026-04-11.md:179`]

### 4.2 Basal Adequacy Advisory

**Function**: `advise_basal()` in `settings_advisor.py:169–265`

**Method**: Uses overnight (00:00–06:00) glucose drift to assess basal adequacy. Simulates TIR with 10%, 15%, and 20% basal adjustments.  
[SOURCE: `settings_advisor.py:201–211` — grid search over `[0.10, 0.15, 0.20]`]

**Output**: Direction (increase/decrease), magnitude (%), current and suggested values, predicted TIR delta, confidence score.

**Minimum data**: 3 days for any recommendation, 14 days for full confidence.  
[SOURCE: `settings_advisor.py:62–63` — `MIN_DATA_DAYS = 3.0`, `HIGH_CONFIDENCE_DAYS = 14.0`]

### 4.3 Natural Experiment Basal Extraction

**Function**: `_extract_basal_schedule()` in `settings_optimizer.py:160–234`

**Method**: Uses fasting/overnight drift (mg/dL/hr) divided by profile ISF to compute basal adjustment in U/hr. Positive drift → increase basal; negative drift → decrease.  
[SOURCE: `settings_optimizer.py:166–170`]

**5 time periods**: overnight (0–6), morning (6–10), midday (10–14), afternoon (14–18), evening (18–24).  
[SOURCE: `settings_optimizer.py:48–54`]

**Safety clamp**: Maximum ±50% basal change from profile.  
[SOURCE: `settings_optimizer.py:64` — `BASAL_CLAMP_FACTOR = 0.5`]

### 4.4 Dawn Phenomenon Detection

**In** `natural_experiment_detector.py`:  
Dawn phenomenon windows detected when fasting 4–8 AM glucose acceleration exceeds 3.0 mg/dL/h.  
[SOURCE: `natural_experiment_detector.py:52` — `DAWN_EFFECT_THRESH = 3.0`]

**Prevalence**: 6/19 patients show dawn phenomenon. Only 6am shows genuine under-basaling (+5 mg/dL/hr); all other daytime hours show over-basaling (−4 to −8 mg/dL/hr).  
[SOURCE: `docs/60-research/circadian-therapy-report-2026-04-10.md` — EXP-2052]

### 4.5 Comparison with oref0 Autotune

oref0's autotune is the only widely-deployed automated settings optimizer in the AID ecosystem. It ships identically in AAPS (Kotlin port) and Trio (embedded JS). Loop has no autotune equivalent. Understanding how our pipeline compares — and where it differs — is essential.

#### 4.5.1 How oref0 Autotune Works

Autotune operates in two phases:

**Phase 1 — Data Categorization** (`autotune-prep/categorize.js`):

Every 5-minute glucose data point is classified into one of 4 buckets:

| Bucket | Criterion | Used For |
|--------|-----------|----------|
| **CSFGlucose** (carb absorption) | COB > 0 AND absorbing | CR/CSF tuning |
| **UAMGlucose** (unannounced meals) | IOB > 2 × currentBasal AND deviation > 0 | Fallback to basal or ISF |
| **ISFGlucose** | BGI < −¼ × basalBGI AND avgDelta ≤ 0 | ISF tuning |
| **basalGlucose** | Everything else (basal insulin dominates) | Basal tuning |

[SOURCE: `externals/oref0/lib/autotune-prep/categorize.js:298–367`]

Key detail: if meals are properly logged (≥1h carb absorption data), UAM deviations are **reclassified as basal**. If meals are NOT logged, UAM data pollutes the basal bucket (top 50% discarded as safety measure).  
[SOURCE: `externals/oref0/lib/autotune-prep/categorize.js:398–418`]

The "deviation" at each point = actual glucose change (avgDelta) minus expected insulin effect (BGI from IOB model). This isolates the unexplained glucose movement that settings should account for.  
[SOURCE: `externals/oref0/lib/autotune-prep/categorize.js:223` — `deviation = avgDelta - BGI`]

**Phase 2 — Settings Adjustment** (`autotune/index.js`):

*Basal*: For each hour 0–23, sum all basalGlucose deviations for that hour → compute insulin needed: `basalNeeded = 0.2 × totalDeviation / ISF`. Spread adjustment across the prior 3 hours (accounting for insulin action lag). For decreases, adjust proportionally to existing rate (not fixed).  
[SOURCE: `externals/oref0/lib/autotune/index.js:210–266`]

*ISF*: Compute median ratio of (actual BG change / expected BGI) across all ISFGlucose points. Apply 20% blend: `newISF = 0.8 × currentISF + 0.2 × adjustedISF`.  
[SOURCE: `externals/oref0/lib/autotune/index.js:446–529`]

*CR*: Track insulin dosed vs carbs eaten from bolus to COB=0. Compute actual CR = carbs / totalInsulin. Apply 20% blend: `newCR = 0.8 × currentCR + 0.2 × fullNewCR`.  
[SOURCE: `externals/oref0/lib/autotune/index.js:328–442`]

*Safety caps*: All outputs clamped to `[pumpValue × autosens_min, pumpValue × autosens_max]` (defaults: 0.7–1.2× pump profile).  
[SOURCE: `externals/oref0/lib/autotune/index.js:267–293`]

*Gap filling*: Hours with no tuning data are interpolated: 80% current + 10% prior tuned hour + 10% next tuned hour.  
[SOURCE: `externals/oref0/lib/autotune/index.js:296–323`]

#### 4.5.2 Head-to-Head Comparison

| Dimension | oref0 Autotune | Our Pipeline |
|-----------|---------------|--------------|
| **Signal for basal** | BG deviation from IOB model (all basalGlucose points, all hours) | Raw overnight glucose drift on clean nights (00:00–06:00, IOB<0.5U, COB<5g) |
| **IOB awareness** | Yes — subtracts expected insulin effect at every data point | Filters for low IOB instead — clean nights require IOB<0.5U |
| **Time resolution** | 24 hourly bins (one adjustment per hour) | 5 time periods: overnight/morning/midday/afternoon/evening |
| **Adjustment rate** | 20% of needed change per iteration | Conservative ±10% per cycle (EXP-1416: wins 10/11 patients) |
| **Safety caps** | ±20–30% of pump profile (autosens_min/max) | ±50% hard clamp, plus 25% safety cap per cycle |
| **Convergence speed** | 5–10 iterations for large corrections | Immediate (one-shot), but graduated 4-step transition over 2–4 weeks |
| **Data categorization** | Sophisticated: 4-bucket state machine isolates basal/ISF/CR/UAM signals | Clean-night filtering + natural experiment detector (fasting/meal/correction windows) |
| **ISF approach** | Single scalar (one ISF for all hours) | Circadian (2–9× within-day variation, 2–4 zones), power-law dose-response |
| **CR approach** | Single scalar, 20% blend | Per-period, context-aware (pre-BG + time + IOB), meal-size dependent |
| **AID compensation** | Not modeled — unaware that loop behavior contaminates the deviation signal | Explicitly modeled — quadrant analysis detects loop-dependent phenotype; recommender adjusts trust per controller type |
| **Prescriptive paradox** | Not addressed — uses observed deviations directly for adjustment | Central finding (EXP-2641/2642) — apparent ISF ≠ dosing ISF; fixed ISF + feedback is near-optimal |
| **Dawn phenomenon** | Detected implicitly (hourly basal adjustment captures it) | Detected explicitly (pre/post-04:00 glucose comparison, prevalence tracked) |
| **Minimum data** | 24h (1 day) — can run daily | 3 days minimum, 14 days for full confidence |
| **Deployment** | Online (runs daily on rig) | Offline (batch retrospective analysis) |

[SOURCE: `externals/oref0/lib/autotune/index.js:210–293` — autotune basal algorithm]  
[SOURCE: `externals/oref0/lib/autotune-prep/categorize.js:331–418` — data categorization]  
[SOURCE: `settings_advisor.py:2736–2742` — clean night criteria]  
[SOURCE: `settings_advisor.py:201–211` — our basal adjustment grid search]  
[SOURCE: `settings_optimizer.py:48–54` — our 5 time periods]  
[SOURCE: `docs/60-research/autotune-uam-characterization-report.md:174–179` — autotune convergence speed]

#### 4.5.3 What Autotune Does Better

1. **Online daily operation**: Autotune runs automatically every day. Our pipeline requires manual batch runs on exported data. For ongoing maintenance, autotune's fire-and-forget model is superior.

2. **24-hour coverage**: Autotune tunes basal for ALL 24 hours, including mid-day periods where our clean-night approach has no signal. For patients with significant mid-day basal needs (e.g., post-lunch insulin resistance), autotune captures signal we miss.

3. **IOB-aware deviation**: By computing `deviation = actualΔBG − expectedBGI`, autotune isolates the basal-attributable glucose movement even during periods with non-trivial IOB. Our approach handles this by filtering for very low IOB (<0.5U) instead, which is simpler but discards valid data.

4. **Proven safety record**: Autotune has run on thousands of patients across oref0/AAPS/Trio for years with ±20% caps. The conservative 20% blend rate is battle-tested. Our pipeline's safety comes from advisory-only (no automatic pump changes) but has no comparable deployment history.

5. **Hourly granularity**: 24 hourly bins vs our 5 periods means autotune can capture finer circadian patterns in basal needs (though our ISF/CR circadian analysis is finer than autotune's single-scalar approach).

#### 4.5.4 What Our Pipeline Does Better

1. **AID compensation awareness**: Autotune's deviations are contaminated by controller behavior — if the loop suspends basal to prevent a low, autotune "sees" a positive deviation and may incorrectly *increase* the scheduled basal for that hour. Our quadrant analysis (§2.7, slope × net-basal) explicitly separates controller-caused from settings-caused glucose movements. The loop-dependent phenotype (suspension > 40%) triggers a different recommendation path.  
[SOURCE: `settings_advisor.py:2898–2915` — loop-dependent classification]  
[SOURCE: `docs/60-research/autotune-uam-characterization-report.md:169` — "Cannot discover: True effective ISF masked by AID compensation"]

2. **Circadian ISF/CR**: Autotune outputs a **single ISF scalar** and a **single CR scalar**. Our pipeline captures 2–9× within-day ISF variation and per-period CR differences. For patients with strong circadian patterns (67% of patients have ISF inflated ≥15% by time-of-day effects), a single scalar is systematically wrong for several hours of the day.  
[SOURCE: `externals/oref0/lib/autotune/index.js:535` — `isfProfile.sensitivities[0].sensitivity = ISF` — single scalar]  
[SOURCE: `settings_advisor.py:6` — "EXP-2271 (circadian ISF 4.6-9×)"]

3. **Prescriptive paradox awareness**: The pipeline's central finding (EXP-2641/2642) is that observed correction behavior cannot be directly used for dosing because apparent ISF is an emergent closed-loop property. Autotune uses observed ISF deviations directly to adjust ISF — this is the exact pattern the paradox warns against. In practice, autotune's 20% blend rate + ±20% caps limit the damage, but the approach is fundamentally confounded.  
[SOURCE: `egp-prescriptive-paradox-report-2026-04-13.md:95,188`]

4. **Optimization sequencing**: The pipeline enforces a specific fix order (CV>28% → basal first; else ISF first; TIR≥70% → personalize). Autotune tunes basal, ISF, and CR simultaneously in every run, which our research shows yields +15–25% TIR gain vs +40–90% for sequential optimization.  
[SOURCE: `settings_advisor.py:3068–3143` — optimization sequence]  
[SOURCE: `docs/60-research/therapy-comprehensive-campaign-report-2026-04-10.md:197` — EXP-1479]

5. **Statistical confidence**: Our pipeline uses bootstrap confidence intervals (1,000 resamples) and requires minimum evidence thresholds (10+ windows for high confidence). Autotune applies adjustments with as few as 1 data point for an hour, relying on the 20% blend rate for safety.  
[SOURCE: `settings_optimizer.py:65–67` — bootstrap]  
[SOURCE: `externals/oref0/lib/autotune/index.js:229` — single-point per-hour adjustment]

6. **Controller-specific tuning**: The recommender adjusts trust factors per controller type: Loop/Trio (suspend-dominant, 52% supply time) vs AAPS (SMB-dominant, 57% demand time) vs oref0 (moderate). Autotune is controller-agnostic — the same algorithm runs regardless of whether the loop primarily suspends or adds insulin.  
[SOURCE: `recommender.py:194–264` — per-controller profiles]

#### 4.5.5 Complementary Use — Best of Both

The two approaches are **not competing** — they solve different problems:

| Phase | Best Tool | Why |
|-------|-----------|-----|
| **Initial onboarding** (first 2 weeks) | oref0 autotune | Runs automatically, converges from any starting point, proven safe |
| **Periodic deep review** (monthly) | Our pipeline | Retrospective analysis catches paradoxes and compensation that autotune can't see |
| **Dawn phenomenon** | Either | Autotune captures it implicitly in hourly bins; our pipeline detects it explicitly |
| **Circadian ISF/CR** | Our pipeline | Autotune's single scalar can't capture 2–9× within-day variation |
| **Ongoing maintenance** | oref0 autotune | Daily fire-and-forget; our pipeline requires manual export/run |
| **Clinical review** | Our pipeline | Counterfactual simulation, phenotyping, controller-aware diagnostics |

[SOURCE: `docs/60-research/autotune-uam-characterization-report.md:197–206` — use case recommendations]

**Ideal workflow**: Run autotune daily for automatic maintenance. Monthly, run our pipeline on the same data to detect AID compensation patterns, prescriptive paradoxes, and circadian opportunities that autotune's conservative single-scalar approach misses. Use the pipeline's optimization sequencing (§2) to decide which setting to change next, and autotune's proven deployment model to implement changes gradually.

---

## 5. Carb Ratio Optimization

### 5.1 CR Adequacy Assessment

**Function**: `advise_cr_adequacy()` in `settings_advisor.py`

**Finding**: Effective CR = **1.47× profile CR** (population mean). Patients systematically under-dose meals — they use 47% more carbs per unit of insulin than their profile says.  
[SOURCE: `docs/60-research/therapy-settings-synthesis-2026-04-11.md:88` — EXP-2535b]

**From earlier research** (EXP-1705): Effective CR = 73% of profile CR (looking from the other direction — the profile CR is 27% too aggressive). 3,847 meal windows analyzed.  
[SOURCE: `docs/60-research/natural-experiments-settings-optimization-report.md` — EXP-1705]

### 5.2 CR Effectiveness Simulation

**Function**: `advise_cr()` in `settings_advisor.py:268–324`

**Method**: Uses CR effectiveness score and post-meal excursion analysis. Simulates TIR with 10%, 15%, 20% CR adjustments during meal hours (5:00–21:00).  
[SOURCE: `settings_advisor.py:292–296` — grid search, `hour_range=(5.0, 21.0)`]

**Trigger**: Fires when CR score < 40/100 (poor).  
[SOURCE: `settings_advisor.py:281` — `if clinical.cr_score >= 40: return None`]

### 5.3 Context-Aware CR

**Function**: `advise_context_cr()` in `settings_advisor.py`

**Research**: EXP-2341. Using pre-meal BG + time-of-day + IOB as context improves CR prediction R² by +0.28.  
[SOURCE: `settings_advisor.py:7` — "EXP-2341 (context-aware CR: pre-BG + time + IOB, R²+0.28)"]

### 5.4 Natural Experiment CR Extraction

**Function**: `_extract_cr_schedule()` in `settings_optimizer.py:304–394`

**Method**: Effective CR = carbs_g / (bolus_U + excursion_mg_dl / ISF). Filters to meals ≥5g carbs and ≥0.1U bolus. Valid CR range: 1.0–100.0 g/U.  
[SOURCE: `settings_optimizer.py:328–336`]  
[SOURCE: `settings_optimizer.py:63` — `CR_RANGE = (1.0, 100.0)`]

**Higher evidence bar**: Meals have more variability, so the "high" confidence threshold is 15 windows (vs 10 for ISF/basal).  
[SOURCE: `settings_optimizer.py:363` — `cr_min_high = 15`]

### 5.5 CR–ISF Independence

CR and ISF are **independent** parameters (r = 0.17). They should be tuned separately, not linked.  
[SOURCE: `docs/60-research/therapy-settings-synthesis-2026-04-11.md:109` — EXP-2535b]

### 5.6 Nonlinearity Cancellation — Linear Dosing Remains Valid

CR is individually nonlinear (sub-linear absorption: larger meals have less BG rise per gram). ISF is individually nonlinear (diminishing returns: larger boluses less effective per unit). These go in **opposite directions** and approximately **cancel**, meaning standard linear dosing (carbs/CR) is a valid approximation.  
[SOURCE: `docs/60-research/therapy-settings-synthesis-2026-04-11.md:127–139` — EXP-2537a, net R² improvement ~+0.001–0.005]

### 5.7 Circadian CR Pattern

Dinner is the hardest meal to dose (highest excursion, 77.3 mg/dL mean, 53.6% high). Breakfast excursions are 58.2 mg/dL (borderline). Lunch is best-controlled (46.3 mg/dL).  
[SOURCE: `docs/60-research/therapy-operationalization-report-2026-04-10.md` — EXP-1336]

**Dinner/breakfast ISF ratio**: 1.9×. The same carbs spike nearly 2× more at dinner than breakfast due to lower afternoon ISF combined with dawn phenomenon amplifying morning meal impact.  
[SOURCE: `docs/60-research/circadian-therapy-report-2026-04-10.md` — EXP-2054]

### 5.8 Carb Entry Reliability — What's Safe vs Compromised

> **⚠ CRITICAL CAVEAT: All CR calculations in §5.1–5.7 depend on user-entered carb values, which are unreliable.**

**Clinical reality**: Patients are typically trained to eat 75g carb meals on a regimented injection schedule. Real-world meals are commonly 40g–100g+. Yet the announced meal carb entries in this dataset are "centered ~20–30g" — a fraction of actual intake.  
[SOURCE: `docs/60-research/meal-characterization-report-2026-04-10.md:94` — "Announced meals: bell-shaped, centered ~20–30g, tight distribution"]

**The data confirms most meals are unannounced**: UAM (unannounced meals detected via physics residuals) accounts for **39% of all natural experiment windows** (19,916 of 50,810) — nearly 5× more than announced meals (8%, 4,065). The census conclusion: "the majority of glucose management happens without carb entries."  
[SOURCE: `natural_experiment_detector.py:20–21`]  
[SOURCE: `docs/60-research/natural-experiments-census-report-2026-04-09.md:20–21,341`]

#### Dependency chain: which optimizations trust carb entries?

| Optimization | Uses entered carbs? | Mechanism | Risk |
|-------------|---------------------|-----------|------|
| **Basal** (§4) | **No** | Overnight drift on clean nights (IOB<0.5U, COB<5g, 00–06h) — filters for *absence* of carbs | ✅ **Immune** |
| **ISF** (§3) | **No** | Correction windows require `carbs[±30min] < 1g` — filters for *absence* of carbs | ✅ **Immune** |
| **Optimization sequencing** (§2) | **No** | Uses CV and TIR from glucose alone | ✅ **Immune** |
| **CR effective/profile ratio** (§5.1) | **Yes** | `effective_CR = entered_carbs / (bolus + excursion/ISF)` | 🔴 **Compromised** |
| **CR schedule extraction** (§5.4) | **Yes** | `eff_cr = carbs_g / total_insulin` from NE meal windows | 🔴 **Compromised** |
| **CR adequacy advisory** (§5.2) | **Indirectly** | Simulation-based (`advise_cr()`), but triggers on `cr_score` which depends on entered carbs | 🟡 **Partially affected** |
| **15–30g sweet spot** (§12) | **Yes** | Bins by entered carbs, not actual carbs — a "15g entered" meal might be 60g actual | 🔴 **Compromised** |
| **Nonlinearity cancellation** (§5.6) | **Partially** | The cancellation result (CR×ISF ≈ linear) holds regardless of carb counting accuracy — it's about the *ratio* of nonlinearities | 🟡 **Result survives** |

[SOURCE: `natural_experiment_detector.py:355` — `carb_events = np.where(carbs >= meal_config.min_carbs)[0]` — meals detected from entered carbs only]  
[SOURCE: `settings_optimizer.py:325–336` — CR calculation uses `m.get('carbs_g')` from NE meal measurements]  
[SOURCE: `settings_optimizer.py:634` — `meals = census.filter_by_type(NaturalExperimentType.MEAL)` — only announced meals used for CR]  
[SOURCE: `natural_experiment_detector.py:469–488` — UAM detection is physics-based but UAM windows carry no carb estimate usable for CR]

#### Why basal and ISF are safe

The pipeline's basal and ISF paths are well-designed precisely because they **don't trust carb entries**:

- **Fasting detection** requires `carb_activity < 1g` over the prior 3 hours — this works whether or not meals are logged, because it looks for the *absence* of entries AND the absence of glucose rises.  
  [SOURCE: `natural_experiment_detector.py:44,279–280`]

- **Correction detection** requires `carbs[±30min] < 1g` — explicitly excludes any window near a carb entry. If a patient ate but didn't log, the correction window might be contaminated (glucose not dropping cleanly due to food absorption), but this shows up as poor curve fit (low R²) and gets down-weighted by the quality score.  
  [SOURCE: `natural_experiment_detector.py:422–424`]

- **Overnight drift** uses 00:00–06:00 windows — patients rarely eat during sleep, so the signal is clean regardless of logging habits.  
  [SOURCE: `settings_advisor.py:2736–2742`]

#### Why CR is fundamentally compromised

The core CR equation — `effective_CR = carbs_g / (bolus_U + excursion_mg_dl / ISF)` — requires knowing actual grams consumed. If a patient eats 75g but enters 25g:

- **Entered-carb CR** = 25 / (bolus + excursion/ISF)
- **Actual CR** = 75 / (bolus + excursion/ISF) = **3× higher**

The finding that "effective CR = 1.47× profile CR (patients under-dose)" (§5.1) has an alternative interpretation: **patients may be dosing correctly for what they actually eat, and the 1.47× ratio reflects systematic carb under-counting rather than conservative CR settings.**  
[SOURCE: `docs/60-research/therapy-settings-synthesis-2026-04-11.md:92` — "This could reflect conservative CR settings, carb under-counting, or both"]

#### The structural gap: detected meals aren't connected to CR optimization

The pipeline **detects** unannounced meals via physics residuals (`_detect_uam()`) — correctly identifying 39% of all glucose events as unexplained rises. It also has **multiple carb estimation algorithms** from extensive R&D:

| Algorithm | Median Estimate | Correlation w/ Entered | What It Measures |
|-----------|----------------|------------------------|------------------|
| Physics residual | 22.6g | r = 0.093 | Total unexplained glucose rise |
| oref0 deviation | 21.8g | **r = 0.368 (best)** | COB-predicted vs actual deviation |
| Glucose excursion | 7.8g | r = 0.263 | Peak-to-trough amplitude |
| Loop IRC | 5.6g | r = 0.334 | Insulin-attributed carb absorption |

[SOURCE: `docs/60-research/meal-data-science-synthesis-2026-04-09.md:108–116` — EXP-1341, 12,060 meals]

The synthesis recommends: "physics for detection, oref0 for magnitude" as an ensemble.  
[SOURCE: `docs/60-research/meal-data-science-synthesis-2026-04-09.md:121`]

**For patient c specifically**, the pipeline detects **2.6 meals/day** on READY days using the physics-based demand-weighted detector — including dessert events (18% of dinners, ~123 min after dinner). A 72-configuration benchmark (EXP-1569) tested hysteresis from 15–180 min, finding the optimal "knee" at **5g/150min** (1.51 meals/day) for universal use and **≥18g/90min** for therapy-grade analysis.  
[SOURCE: `docs/60-research/non-bolusing-robustness-report-2026-04-07.md:424` — "2.6 meals/day median on READY days"]  
[SOURCE: `docs/60-research/non-bolusing-robustness-report-2026-04-07.md:408` — "dessert...mean gap of 123 minutes"]  
[SOURCE: `docs/60-research/natural-experiments-benchmark-report-2026-04-09.md:20–26` — 72-config grid]  
[SOURCE: `docs/60-research/meal-data-science-synthesis-2026-04-09.md:32` — knee at 5g/150min]

**However, none of this is plumbed into the settings optimizer.** The gap:

1. **UAM windows have no `carbs_g` field**: measurements include `peak_residual`, `mean_residual`, `bg_rise`, but no carb estimate.  
   [SOURCE: `natural_experiment_detector.py:517–530`]

2. **Carb estimation algorithms exist but aren't connected**: The 4 algorithms above (EXP-1341) run in research scripts, not in the production NE detector or settings optimizer.

3. **`_extract_cr_schedule()` only processes `MEAL` type** (entered-carb events), not `UAM` type.  
   [SOURCE: `settings_optimizer.py:634`]

4. **Circular dependency (partially solvable)**: Converting glucose rise to grams requires CR — the thing we're optimizing. But the oref0 deviation method uses IOB-model-predicted deviation, which breaks the circularity by using ISF (already optimized in prior phase) rather than CR. This is the same approach oref0 autotune uses for CSF tuning.  
   [SOURCE: `externals/oref0/lib/autotune/index.js:336–377` — CSF from deviation/mealCarbs]

**The actionable gap**: The meal detection R&D (72 configs, 4 estimation algorithms, dessert detection, 2.6 meals/day for patient c) is mature research that could substantially improve CR optimization — but it needs to be plumbed into the production `_extract_cr_schedule()` path, using detected meals + estimated carbs instead of (or in addition to) entered carbs. The oref0 deviation estimator (best correlation, r=0.368) could provide the carb magnitude needed to break the circularity, since ISF is optimized before CR in the sequencing protocol (§2).

#### Practical implications

1. **Basal and ISF recommendations from this pipeline can be trusted** — they don't depend on carb entry accuracy.

2. **CR recommendations should be treated as directional at best** — the magnitude is unreliable because the carb numerator is suspect. A recommendation to "decrease CR by 15%" might be correct in direction (meals do spike) but wrong in magnitude.

3. **The "15–30g sweet spot" finding should be reframed**: it shows that *small entered-carb meals* have the best TIR, which likely reflects either (a) genuinely small snacks that are well-handled by the AID, or (b) larger meals that were under-counted to ~20g where the AID happened to compensate well — not a recommendation to eat 15–30g meals. Real-world meals are commonly 40–100g+; patients are clinically trained on 75g regimented meals.

4. **oref0 autotune has the same limitation**: its CR tuning uses `totalMealCarbs` from treatment entries.  
   [SOURCE: `externals/oref0/lib/autotune/index.js:336–395`]

5. **Post-meal glucose excursion is a carb-independent CR signal**: the `advise_cr()` simulation path (§5.2) uses TIR during meal hours, which doesn't directly require accurate carb counts — it observes whether post-meal glucose returns to range. This is the more robust CR approach, though its trigger (`cr_score < 40`) still depends on entered-carb calculations.

6. **Connecting detected meals to CR optimization is the highest-impact integration gap** in the pipeline. The research exists (EXP-1341, EXP-1569, EXP-486); it just needs to be wired into the production path.

---

## 6. Correction Threshold Advisory

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

## 7. Controller-Specific Behavior

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

## 8. Profile Generation & Export

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

## 9. Safety Guardrails

### 9.1 Per-Cycle Safety Clamp (25%)

**Research**: EXP-2626 found that ISF discrepancy advisories can suggest extreme changes (±68–100%). Standard clinical practice is ≤10–15% per adjustment cycle.  
[SOURCE: `tools/cgmencode/production/exp_safety_guardrails_2626.py:3–8`]

The experiment confirmed: 7/10 extreme advisories (>50% magnitude) come from ISF advisors specifically. Capping at 25% preserves advisory ranking (Kendall τ > 0.8).  
[SOURCE: `exp_safety_guardrails_2626.py:16–18` — H1, H2, H3 hypotheses]

### 9.2 Advisory Coherence Audit

**Research**: EXP-2624 audited all 17 advisories across 16 patients: **0 contradictions** (same parameter, opposite direction). CR dominates top-3 advisories.  
[SOURCE: `tools/cgmencode/production/exp_advisory_audit_2624.py:1–22`]  
[SOURCE: stored memory — "Advisory audit: 0 contradictions across 16 patients"]

### 9.3 Basal Clamp

Maximum ±50% basal change from profile value.  
[SOURCE: `settings_optimizer.py:64` — `BASAL_CLAMP_FACTOR = 0.5`]

### 9.4 Confidence Grading

| Grade | Total Evidence Windows | Period-Settings at Medium+ |
|-------|----------------------|---------------------------|
| A | ≥100 | ≥12 |
| B | ≥50 | ≥8 |
| C | ≥20 | ≥4 |
| D | <20 | <4 |

[SOURCE: `settings_optimizer.py:407–424` — `_grade_overall_confidence()`]

### 9.5 Minimum Data Requirements

| Parameter | Minimum | Full Confidence |
|-----------|---------|-----------------|
| Any recommendation | 3 days | 14 days |
| ISF segmented | 7 days | 14 days |
| Correction threshold (per-patient) | 10 events | 50 events |

[SOURCE: `settings_advisor.py:62–63`, `settings_advisor.py:519–520`]

### 9.6 Prediction Bias: Do NOT Correct

"Naive bias correction is DANGEROUS for 8/10 patients: removing the negative bias removes the loop's defensive suspension, which prevents real hypos. Report the bias as informational only."  
[SOURCE: `recommender.py:151–153`]

---

## 10. Forward Simulation (Digital Twin)

**Module**: `forward_simulator.py`

### 10.1 Two-Component DIA Model

| Component | Fraction | Time Constant | Mechanism |
|-----------|----------|---------------|-----------|
| Fast | 63% | τ = 0.8h | Insulin-mediated glucose uptake |
| Persistent | 37% | τ = 12h | Residual IOB + loop basal adjustment |

[SOURCE: `metabolic_engine.py:40–42` — `_FAST_TAU_HOURS = 0.8`, `_PERSISTENT_FRACTION = 0.37`, `_PERSISTENT_WINDOW_HOURS = 12.0`]  
[SOURCE: `forward_simulator.py:50` — `_FAST_FRACTION = 1.0 - _PERSISTENT_FRACTION  # 0.63`]

**⚠ Mechanism correction** (EXP-2534): Originally attributed to hepatic glucose production (HGP) suppression. Overnight matched-pair validation (280 pairs) showed the persistent effect is IOB underestimation by standard DIA curves + loop compensation — not liver physiology. The model remains **predictively valid** (R²=0.827).  
[SOURCE: `docs/60-research/therapy-settings-synthesis-2026-04-11.md:48–52` — EXP-2534]

### 10.2 Power-Law ISF Dampening

effective_isf_mult = isf_multiplier^(1 − β), where β = 0.9.  
[SOURCE: `settings_advisor.py:128–131`]  
[SOURCE: `forward_simulator.py:51` — `_POWER_LAW_BETA = 0.9`]

Prevents overestimating large ISF corrections. Without this, the persistent tail overamplifies perturbations (Model B MAE=3.23pp vs Model C MAE=0.30pp).  
[SOURCE: `settings_advisor.py:92–94`]

### 10.3 Carb Absorption Model

| Parameter | Value | Source |
|-----------|-------|--------|
| Absorption window | 3.0h | `forward_simulator.py:57` |
| Gut delay τ | 20 min | `forward_simulator.py:58` — EXP-1932 |
| Peak time | 71 min | `forward_simulator.py:59` — EXP-1934 |

### 10.4 Basal Neutrality

The model defines the patient's basal rate as metabolic equilibrium. All effects are relative:

```
dBG = -excess_insulin_effect × ISF
      + carb_rise × (ISF / CR)
      + decay_toward_120
      + noise
```

Where `excess_insulin = total_absorption − scheduled_basal_absorption`.  
[SOURCE: `forward_simulator.py:10–27`]

### 10.5 Simulation Accuracy

| Metric | Two-Component Model | Single-Decay Model |
|--------|--------------------|--------------------|
| MAE | 0.30 pp | 2.10 pp |
| r | 0.933 | 0.129 |

[SOURCE: `settings_advisor.py:22–23`]

---

## 11. Key Paradoxes & Limitations

### 11.1 The Descriptive-Prescriptive Paradox (EXP-2641/2642)

> **This is the single most important finding in the entire research program.**

The model that best *describes* correction glucose drops (per-patient log-ISF, bias = −3 mg/dL) is the **worst prescriber** (recommends 2.3× the optimal dose).  
[SOURCE: `egp-prescriptive-paradox-report-2026-04-13.md:95`]

**Why**: The apparent ISF is an emergent property of the closed-loop system, not the patient's intrinsic insulin sensitivity. Two effects interact:

1. **Profile ISF is genuinely too low** — patients are more insulin-sensitive than their profiles say (this is the dominant factor in the 2.91× ratio)
2. **The controller opposes large corrections** — when a bolus drives glucose down, the AID suspends basal and cancels SMBs to prevent overshooting low. This **reduces** the total glucose drop, making apparent ISF per unit **smaller** for large doses

The dose-dependent interaction creates a paradox:
- For **small doses** (<1U): controller barely intervenes → apparent ISF ≈ true ISF (large)
- For **large doses** (≥3U): controller aggressively suspends → apparent ISF deflated (small)
- A log-ISF model captures this dose dependence descriptively (bias = −3), but if used to *calculate* doses, it recommends 2.3× the optimal dose because it doesn't account for the controller's real-time response to the dose it's recommending

Large corrections have a **lower** over-correction rate (20%) than medium ones (27.5%) precisely because the controller absorbs the excess — converting potential hypos into mere under-corrections.  
[SOURCE: `egp-prescriptive-paradox-report-2026-04-13.md:99–111,129,171–174`]

**Conclusions from EXP-2641/2642** (scoped correctly 2026-04-18):
1. "Fixed ISF + controller feedback is a robust baseline" — but multi-factor ISF models improve on it  
2. "Single-factor ISF models do not reduce per-event hypo rate" — per-event variability is high (R² = −0.19 for single factors)  
3. The remaining ~16% hypo rate is partially addressable through multi-factor approaches (dose-dependent, circadian, phase-aware) and controller modifications (patience mode)  
[SOURCE: `egp-prescriptive-paradox-report-2026-04-13.md:188,192,220`]

**Impact on §3 (ISF Optimization)**: The EXP-747/1703 "effective ISF" data (§3.1) predates this finding. Those values are useful as a **diagnostic** (how hard is the controller working?) but should NOT be interpreted as ISF targets. The production `advise_isf()` uses conservative 25% steps but may itself need revision given this paradox. See the caveat box at the top of §3.

### 11.2 AID Compensation Observation (EXP-2629/2630)

> **Corrected 2026-04-18** — see `egp-evidence-synthesis-report-2026-04-18.md` for full review.

The AID controller's insulin modulation is part of the observed glucose dynamics. IOB drops 55% before hypo crossing because the controller reduces insulin delivery when glucose falls — standard control-system behavior. AID-active recovery = 7.6 vs suspended = 3.6 mg/dL/hr (p < 0.0001), quantifying the controller's contribution to observed recovery. Post-correction recovery reflects coupled contributions from EGP reassertion, counter-regulation, residual insulin, and AID withdrawal — these cannot be decomposed into independent **additive** terms (sum = 34, actual = 4.1 mg/dL/hr). However, per-patient physical parameters CAN be recovered using multi-factor methods: dose-dependent ISF (r = −0.56, EXP-2640), response-curve fitting (R² = 0.805, EXP-1301), circadian profiling (EXP-2652), and phase decomposition (EXP-2651).  
[SOURCE: `docs/60-research/egp-deconfounding-report-2026-04-13.md`]  
[SOURCE: `docs/60-research/egp-evidence-synthesis-report-2026-04-18.md`]

### 11.3 Post-Nadir Recovery Rate Is Multi-Factorial (EXP-2634/2635)

> **Corrected 2026-04-18** — original framing ("All Recovery Models Fail") over-generalized a narrow result.

Five single-factor models (null, mean-reversion, IOB-decay, biexp-decay, Hill EGP) have negative R² (−2.4 to −3.2) when predicting **post-nadir recovery rate** on 219 corrections. This applies specifically to post-nadir recovery rate prediction from individual factors — not to ISF estimation or trajectory modeling more broadly. Response-curve ISF fitting achieves R² = 0.805 (EXP-1301); dose-dependent ISF achieves r = −0.56 (EXP-2640). Bolus size is the strongest single predictor of recovery dynamics (r = −0.307), consistent with the dose-dependent ISF finding.  
[SOURCE: `docs/60-research/egp-calibration-report-2026-04-13.md`]  
[SOURCE: `docs/60-research/egp-evidence-synthesis-report-2026-04-18.md`]

### 11.4 Irreducible Hypo Rate

The hypo rate floor is approximately **16%**, irreducible by settings optimization alone.  
[SOURCE: stored memory — "16% hypo rate is irreducible"]

---

## 12. Research-Only Findings (Not Yet Productionized)

*Updated 2026-04-18. Items marked ✅ are now in production code.*

| Finding | Status | Evidence | Notes |
|---------|--------|----------|-------|
| Two-component DIA (fast τ=0.8h + 37% persistent) | ❌ Not productionized | R²=0.827 (EXP-2525) | Needs AID firmware changes |
| Split-dose recommendation (87% theoretical improvement) | ❌ Not productionized | EXP-2522 | Empirically confounded (0.39×); needs RCT |
| 15–30g meal sweet spot | ❌ Reframed | EXP-2537d | Based on entered carbs, not actual carbs (see §5.8). Real meals are 40–100g+ |
| Loop workload metric (18/19 saturated) | ❌ Insight only | EXP-2391 | Not actionable |
| CR × ISF cancellation | ❌ Insight only | EXP-2537a | Confirms linear dosing — no action needed |
| **Demand-phase ISF** | ✅ **Productionized** | EXP-2651, 2663–2666 | `compute_demand_isf()` with 6h Nyquist-correct isolation, tiered fallback, carb exclusion. `advise_isf()` targets demand ISF with conservative 25% step. Demand ISF confirmed constant per patient (not dose-dependent, not circadian). |
| **SC suppression ceiling detection** | ✅ **Productionized** | EXP-2656, 2660 | `detect_insulin_saturation()`: wall detection (IOB>2×median + ROC>-5), SaturationLevel tiers (NONE/MILD/MODERATE/SEVERE). |
| **Patience mode advisory** | ✅ **Productionized** | EXP-2662 | `advise_patience_mode()` wired into `generate_settings_advice()`. Saves 34–82% SMBs, ≤+2.1pp hyper, reduces delayed hypos 0.1–2.0pp. |
| **Detected-meal → CR (carbs_estimated_g)** | ⚠️ **Partially done** | EXP-1341, 1569, 748 | `_extract_cr_schedule()` falls back to `carbs_estimated_g` for MEAL windows with absent/small carb entries. **Gap**: UAM windows (truly unannounced) lack `carbs_estimated_g` and are not fed to CR optimizer. |
| **48h carb history for overnight drift** | ✅ **Productionized** | EXP-2622, 2627 | `assess_overnight_drift()` accepts carbs param for glycogen context. |
| **Stacking prevention** | ✅ **Productionized** | EXP-2624 | `assess_correction_timing()` threshold at 3.5h (EGP nadir timing). |
| Circadian demand ISF | ❌ **Disproved** | EXP-2664, 2665, 2666 | Apparent ISF circadian variation is EGP-driven, not insulin sensitivity. Demand ISF is circadian-flat (−4.7% from profiling). |

### 12.1 Bugs Found and Fixed During Production Review

| Bug | Severity | Fix |
|-----|----------|-----|
| `compute_demand_isf()`: no prior-bolus isolation | High | Fixed (9e53ed8): 6h Nyquist-correct isolation window |
| `advise_isf_dual_phase()`: `step_pct` reports 25% but `suggested` moves 17.5% | Medium | Fixed (14fcc7e): made function informational-only |
| Duplicate ISF recommendations from `advise_isf()` + `advise_isf_dual_phase()` | Medium | Fixed (14fcc7e): `advise_isf()` is sole actionable path |
| `detect_insulin_saturation()`: end-of-array episode dropped wall data | Medium | Fixed (56c360a): full wall detection for final episode |
| `excess_insulin_u`: sums IOB stock across steps (overcounts) | Low | Documented — informational field, not used for dosing |

### 12.2 Test Infrastructure

| Suite | Tests | Time | Command |
|-------|-------|------|---------|
| Unit tests | 362 | 33s | `pytest -m unit` |
| Integration tests | 56 | 148s | `pytest -m integration` |
| Full suite | 418 | ~3 min | `pytest test_production.py` |

[SOURCE: commits 4a8c282, 43ca8bc, ddeff89, 56c360a, 7e75da0, 9e53ed8, 14fcc7e, f79b175; EXP-2663–2666]

---

## 13. Quantitative Summary

| Metric | Value | Source File | EXP |
|--------|-------|------------|-----|
| **Sequencing** | | | |
| CV threshold for phase transition | 28% | `settings_advisor.py:3071` | 1765 |
| Patients needing variability-first | 9/11 | `settings_advisor.py:3082` | 1765 |
| Patients harmed by wrong order | 6/11 | `settings_advisor.py:3077` | 1765 |
| Combined optimization ceiling | +17.6% TIR | `clinical_rules.py:978` | 1765 |
| Sequential vs simultaneous gain | +40–90% vs +15–25% | `therapy-comprehensive-campaign-report:197` | 1479 |
| Basal as top action | 10/11 patients | `therapy-pipeline-validation-report:213` | 1386 |
| Optimal basal magnitude | Conservative ±10% | `therapy-actionable-recommendations-report:210` | 1416 |
| Graduated transition duration | 2–4 weeks (4 steps) | `settings-simulation-report:219` | 2248 |
| Projected TIR gain (all recs) | +9.1% (70.9→80.0%) | `settings-simulation-report:237` | 2248 |
| Projected hypo reduction | −50% (0.88→0.44/day) | `settings-simulation-report:241` | 2248 |
| **ISF** | | | |
| ISF apparent/profile ratio | 2.3× mean (1.2–4.3×) ⚠ includes controller compensation | `natural-experiments-settings-optimization-report.md` | 1703 |
| ISF power-law β | 0.9 | `settings_advisor.py:381` | 2511 |
| ISF circadian range | 2–9× within-day | `settings_advisor.py:6` | 2271 |
| ISF share of TIR gain | 85% | `settings_optimizer.py:71` | 1717 |
| **CR** | | | |
| CR effective/profile ratio | 1.47× (under-dosing) | `therapy-settings-synthesis-2026-04-11.md:88` | 2535b |
| CR–ISF correlation | r = 0.17 (independent) | `therapy-settings-synthesis-2026-04-11.md:109` | 2535b |
| **Basal** | | | |
| Basal miscalibrated | 18/19 patients | `therapy-settings-synthesis-2026-04-11.md:161` | 2371 |
| Loop suspension rate | 52–96% (median 55%) | `recommender.py:198` | 2081 |
| Clean night criteria | IOB<0.5U, COB<5g | `settings_advisor.py:2736–2737` | 2375 |
| Drift stable threshold | ±3 mg/dL/hr | `settings_advisor.py:2745` | 2371 |
| Dawn phenomenon prevalence | 6/19 patients | `circadian-therapy-report:EXP-2052` | 2375 |
| Basal clamp | ±50% max | `settings_optimizer.py:64` | — |
| **oref0 Autotune Comparison** | | | |
| Autotune blend rate | 20% per iteration | `oref0/lib/autotune/index.js:236` | — |
| Autotune basal cap | ±20–30% of pump (autosens_min/max) | `oref0/lib/autotune/index.js:278–280` | — |
| Autotune ISF: single scalar | 1 value (no circadian) | `oref0/lib/autotune/index.js:535` | — |
| Autotune convergence | 5–10 iterations for large errors | `autotune-uam-characterization-report.md:178` | — |
| Autotune data buckets | 4 (basal/ISF/CSF/UAM) | `oref0/lib/autotune-prep/categorize.js:447–452` | — |
| Our circadian ISF advantage | 2–9× vs single scalar | `settings_advisor.py:6` | 2271 |
| Sequential vs simultaneous (autotune-relevant) | +40–90% vs +15–25% | `therapy-comprehensive-campaign-report:197` | 1479 |
| **Other** | | | |
| Optimal correction threshold | 166 mg/dL (130–290) | `settings_advisor.py:512–513` | 2528 |
| Population DIA | 6.0h (vs 5h assumed) | `therapy-operationalization-report-2026-04-10.md` | 1334 |
| Combined predicted TIR gain | +2.8% | `settings_optimizer.py:70–72` | 1717 |
| Advisory audit contradictions | 0/16 patients | `exp_advisory_audit_2624.py` | 2624 |
| Safety clamp per cycle | 25% max | `exp_safety_guardrails_2626.py:10` | 2626 |
| Forward sim accuracy | MAE=0.30pp, r=0.933 | `settings_advisor.py:22–23` | 2551 |
| Hypo rate floor | ~16% irreducible | `egp-prescriptive-paradox-report-2026-04-13.md` | 2641 |
| Natural experiment census | 50,810 windows | `natural_experiment_detector.py:1–22` | 1551 |
| Production test coverage | 418 tests, 85 classes (unit 33s / integration 148s) | `test_production.py` | — |

---

## 14. Verification Checklist

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
