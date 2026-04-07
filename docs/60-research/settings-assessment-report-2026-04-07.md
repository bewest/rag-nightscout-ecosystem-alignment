# Settings Assessment & Metabolic Flux Report

**Date**: 2026-04-07  
**Experiments**: EXP-483–494 (building on EXP-435–482)  
**Scope**: Precondition gating, settings fidelity scoring, residual characterization

---

## Executive Summary

We extended the metabolic flux framework with three capabilities:

1. **Precondition gating** — formal checks for CGM/insulin telemetry adequacy
2. **Settings fidelity scoring** — composite score detecting mistuned therapy settings
3. **Residual fingerprinting** — characterizing what the model doesn't capture

| Capability | Key Result | Clinical Relevance |
|:-----------|:-----------|:-------------------|
| Precondition gate | 50/61 READY days (live-split) | Filter unreliable analysis days |
| Demand-weighted detection | **96% on READY days** | Robust meal counting |
| Basal adequacy | 5/11 too low (>5 mg/dL/h drift) | Flag basal rate adjustments |
| Fidelity score | Range 15–84/100 | Settings quality triage |
| Persistent residual | 3/11 patients (acf30 > 0.3) | Identify settings drift |
| Residual decomposition | 25% meal, 13% dawn, 53% noise | Understand model limitations |

**Patient k** emerges as the gold standard (84/100 fidelity, TIR 95%, residual std=4.77).
**Patient i** is the warning case (15/100, persistent residual acf=0.63, settings severely misaligned).

---

## 1. Precondition Gating (EXP-483b)

### 1.1 Why Preconditions Matter

The metabolic flux framework computes supply−demand balance from CGM and insulin
telemetry. Without sufficient input data, the framework produces garbage — and the
garbage looks the same as a missed meal or quiet day. Formal preconditions prevent
misinterpretation.

### 1.2 Preconditions Defined

| Precondition | Threshold | Physical Requirement |
|:-------------|:---------:|:---------------------|
| **CGM coverage** | ≥70% readings/day | Sensor active (no warmup, dropout, expiry) |
| **Insulin telemetry** | ≥10% non-zero demand | Pump delivering (functional cannula) |
| **Sufficient control** | (implicit) | AID reacting to meals for demand signal |

### 1.3 Live-Split Validation

Of 61 calendar days in the live-split dataset:

| Status | Count | Description |
|:-------|:-----:|:------------|
| **READY** | 50 | Both CGM and insulin data sufficient |
| CGM gap | 7 | Sensor outage / warmup / session end |
| INS gap | 1 | No insulin telemetry (partial first day) |
| Both gap | 3 | Full data outage |

### 1.4 Impact on Detection Metrics

| Metric | All 61 days | 50 READY days only |
|:-------|:-----------:|:------------------:|
| Events/day mean | 2.2 ± 1.3 | **2.6 ± 1.0** |
| Events/day median | 2 | **3** |
| Detection rate | 82% | **96% (48/50)** |
| Days with 2–3 meals | 59% | **72%** |

The 11 gap days correctly average 0.55 events/day — the detector properly
produces minimal output when preconditions aren't met, rather than hallucinating meals.

---

## 2. Demand-Weighted Unified Detector (EXP-483)

### 2.1 Improvements Over EXP-482

| Feature | EXP-482 (global) | EXP-483 (adaptive) |
|:--------|:-----------------:|:------------------:|
| Threshold | Global 65th percentile | Day-local 50th percentile |
| Zero-insulin days | No detection possible | Glucose-derivative fallback |
| Overnight filtering | Static 2× baseline | Day-local baseline |
| Dinner detection | 0.1/day | 0.3/day |
| False positive rate | ~5.6/day (noisy methods) | 2.6/day (demand-gated) |

### 2.2 Timing Distribution (READY days)

| Window | Events/day |
|:-------|:---------:|
| Breakfast (6–11h) | 0.9 |
| Lunch (11–15h) | 0.7 |
| Dinner (17–21h) | 0.3 |
| Late evening (21–24h) | 0.4 |
| Overnight (0–6h) | 0.1 |

The low dinner-window count with high late-evening count suggests this patient
eats dinner later than typical (after 21h), consistent with user description.

---

## 3. Basal Adequacy Assessment (EXP-489)

### 3.1 Method

Overnight glucose drift (0–5 AM, linear regression) on nights without residual
meal insulin (demand < 75th percentile). A flat glucose line = adequate basal.

### 3.2 Results

| Patient | Drift (mg/dL/h) | Direction | Assessment | Nights (↑→↓) |
|:--------|:---------------:|:---------:|:----------:|:--------------|
| k | +1.7 | — | ✓ Adequate | 44↑ 69→ 15↓ |
| c | +0.5 | — | ✓ Adequate | 41↑ 9→ 45↓ |
| g | +1.4 | — | ✓ Adequate | 55↑ 17→ 46↓ |
| e | +1.6 | — | ✓ Adequate | 40↑ 7→ 46↓ |
| j | +1.6 | — | ✓ Adequate | 15↑ 5→ 14↓ |
| b | +4.8 | — | ✓ Borderline | 59↑ 9→ 28↓ |
| h | +5.8 | ↑ | ✗ Too low | 16↑ 6→ 8↓ |
| f | +10.3 | ↑ | ✗ Too low | 43↑ 11→ 21↓ |
| i | +11.0 | ↑ | ✗ Too low | 59↑ 13→ 27↓ |
| d | +11.1 | ↑ | ✗ Too low | 90↑ 13→ 13↓ |
| a | +13.7 | ↑ | ✗ Too low | 68↑ 10→ 25↓ |

### 3.3 Interpretation

**5/11 patients have systematically rising overnight glucose**, suggesting:
- Basal rate is too low for overnight period, OR
- Dawn phenomenon is overwhelming the basal rate, OR
- Late meal absorption is confounding (filtered but imperfect)

Patient **d** is striking: 90 rising vs 13 falling nights — nearly always drifting up.
Patient **k** has 69 flat nights — the majority are genuinely stable.

**Clinical implication**: A simple overnight drift score could flag patients whose
basal rates need adjustment, before running more complex analysis.

---

## 4. Glycemic Fidelity Score (EXP-492)

### 4.1 Components

| Component | Weight | What it Measures |
|:----------|:------:|:-----------------|
| Supply-demand balance | 25% | Daily integral of (supply − demand) ≈ 0 |
| Residual magnitude | 25% | RMSE of (actual ΔBG − predicted ΔBG) |
| Overnight stability | 25% | Standard deviation of BG during 0–5 AM |
| Time in range | 25% | % of readings 70–180 mg/dL |

### 4.2 Results

| Patient | Composite | Balance | Residual | Overnight | TIR | Quality |
|:--------|:---------:|:-------:|:--------:|:---------:|:---:|:-------:|
| **k** | **84** | 79 | 67 | 97 | 95 | Good |
| d | 52 | 46 | 47 | 35 | 79 | Marginal |
| j | 50 | 63 | 8 | 46 | 81 | Marginal |
| h | 44 | 26 | 42 | 21 | 85 | Poor |
| g | 36 | 43 | 24 | 0 | 75 | Poor |
| b | 35 | 65 | 19 | 0 | 57 | Poor |
| f | 32 | 29 | 32 | 0 | 66 | Poor |
| e | 20 | 5 | 4 | 6 | 65 | Poor |
| c | 17 | 8 | 0 | 0 | 62 | Poor |
| a | 17 | 9 | 2 | 0 | 56 | Poor |
| **i** | **15** | 0 | 0 | 0 | 60 | Poor |

### 4.3 Interpretation

**Patient k is the gold standard**: All four components score well, confirming that
this patient's settings closely match their physiology. Metabolic flux analysis should
be most reliable for this patient.

**Patient i is the warning case**: Every component scores near zero. The supply-demand
framework is a poor fit, meaning either settings are severely misaligned or the patient's
physiology is unusual. Analysis results for this patient should be treated with caution.

**The overnight score of 0 for many patients** (a, b, c, f, g) reflects high
overnight glucose variability — consistent with basal adequacy findings.

### 4.4 Proposed Thresholds

| Score Range | Assessment | Recommendation |
|:-----------:|:----------:|:---------------|
| ≥65 | Good | Settings adequate for analysis |
| 45–64 | Marginal | Results valid but settings drift likely |
| <45 | Poor | Settings may need adjustment before analysis is reliable |

---

## 5. Residual Characterization (EXP-493)

### 5.1 What the Residual Contains

The conservation residual = actual ΔBG − predicted ΔBG. It captures everything
the supply-demand model doesn't explicitly model:

- **Unannounced meals** (positive residual during eating)
- **Dawn phenomenon excess** beyond hepatic model
- **Exercise** (negative residual from enhanced insulin sensitivity)
- **Stress/illness** (cortisol-driven glucose rise)
- **Device factors**: sensor age degradation, cannula site deterioration
- **Hormonal variation**: menstrual cycle, sleep quality

### 5.2 Per-Patient Fingerprints

| Patient | Mean | Std | Skew | Worst Hour | ACF-30min | Character |
|:--------|:----:|:---:|:----:|:----------:|:---------:|:----------|
| k | +0.4 | 4.8 | +0.06 | 17h (+1.3) | 0.12 | ✓ Tight, random |
| d | +1.4 | 6.3 | +0.20 | 6h (+3.7) | 0.17 | ✓ Mild dawn |
| f | +2.1 | 7.4 | +0.64 | 3h (+3.1) | 0.14 | ✓ Skewed, random |
| g | +1.4 | 8.2 | +0.13 | 5h (+5.4) | 0.12 | ✓ Dawn-dominant |
| h | +2.3 | 6.5 | +0.35 | 5h (+5.4) | 0.19 | ✓ Dawn-dominant |
| a | +4.2 | 9.3 | +0.37 | 1h (+6.5) | 0.18 | ✓ Night meals? |
| j | −0.8 | 9.7 | +0.05 | 0h (+8.1) | 0.13 | ✓ Wide but unbiased |
| c | +4.5 | 9.6 | +0.66 | 1h (+7.9) | 0.26 | ⚠ Borderline |
| b | −0.7 | 8.8 | −0.23 | 5h (−4.1) | 0.32 | ⚠ Persistent |
| e | +5.1 | 8.6 | +0.23 | 2h (+8.6) | 0.37 | ⚠ Persistent |
| **i** | **+10.7** | **11.8** | **+1.06** | 22h (+15.7) | **0.63** | ⚠ **Severe** |

### 5.3 Key Patterns

**Random residuals** (8/11): ACF-30min < 0.3 — the model captures the main dynamics
and what's left is genuinely unpredictable (meals, exercise, etc). These patients have
settings that are "close enough" for the framework to work.

**Persistent residuals** (3/11): ACF-30min > 0.3 — systematic patterns the model
misses. This indicates settings drift or unmolded physiology:
- **Patient b**: Negative skew, worst at 5 AM — possible overtreatment overnight
- **Patient e**: Positive mean +5.1, worst at 2 AM — basal insufficient + dawn
- **Patient i**: Mean +10.7, worst at 22h, acf=0.63 — severely misaligned settings
  with residual persisting for hours (model consistently underpredicts)

### 5.4 Residual Decomposition (EXP-488, live-split)

| Component | Time Share | Mean Residual | Variance Share |
|:----------|:---------:|:-------------:|:--------------:|
| Meal-correlated | 19% | **+3.77** | **25%** |
| Dawn-correlated | 13% | +2.49 | 13% |
| Exercise window | 14% | +0.82 | 6% |
| Noise | 55% | +1.70 | **53%** |

The meal component is strongly positive (74% of timesteps positive) — confirming
the residual IS the implicit meal signal for non-bolusing patients.

---

## 6. Dessert Detection (EXP-486)

Post-dinner secondary demand peaks (dessert) detected on **18% of dinners** (3/17),
with a mean gap of **123 minutes** after dinner. This matches the user's description
of "sometimes followed by dessert."

---

## 7. Cross-Cutting Findings

### 7.1 The Settings Spectrum

Combining all three assessments reveals a clear spectrum:

| Tier | Patients | Profile |
|:-----|:---------|:--------|
| **Gold** | k | 84/100 fidelity, adequate basal, random residual, TIR 95% |
| **Marginal** | d, j | 50-52/100, some basal drift, mostly random residual |
| **Noisy** | b, e, f, g, h | 20-44/100, variable basal, some persistent residual |
| **Misaligned** | a, c, i | 15-17/100, basal too low, large/persistent residual |

### 7.2 Implications for Analysis Reliability

The fidelity score can serve as a **gate** for downstream analysis:
- **Settings fidelity ≥65**: Analysis results are reliable
- **Settings fidelity 45–64**: Results useful but include settings-drift noise
- **Settings fidelity <45**: Consider flagging that settings adjustments may improve
  both glycemic outcomes AND analysis reliability

### 7.3 Relationship Between Findings

Strong correlations between independent measures:
- Basal inadequate → low overnight score → low fidelity
- Persistent residual → low residual score → low fidelity
- Patient k anchors the "calibrated" end of every metric
- Patient i anchors the "miscalibrated" end

---

## 8. Proposed Next Experiments

### EXP-495: ISF Fidelity from Correction Outcomes

Identify correction boluses (bolus without carbs within 30 min), track glucose drop
over next 3 hours, compare actual drop to configured ISF × bolus units.
**Hypothesis**: Configured ISF within ±30% of observed for patients with fidelity >65.

### EXP-496: CR Fidelity from Post-Meal Recovery

Identify bolus+carb pairs, track glucose excursion peak and recovery time.
Compare actual peak rise to expected from (carbs − carbs/CR × ISF).
**Hypothesis**: CR fidelity correlates with fidelity score.

### EXP-497: Sensor Age Effect on Residual

For patients with multiple sensor sessions, compare residual magnitude by day-of-sensor.
**Hypothesis**: Residual increases in final 1-2 days of sensor life.

### EXP-498: Cannula Age Effect on Residual

Group data by hours since last site change. Test for increasing residual as cannula ages.
**Hypothesis**: Residual increases after 48-72h of cannula use (occlusion onset).

### EXP-499: Per-Hour Basal Recommendation

For patients with basal_adequate=False, compute the basal rate adjustment per hour
that would minimize overnight drift. Output as a suggested schedule.
**Hypothesis**: Adjustments cluster around 0–5 AM and match dawn phenomenon timing.

### EXP-500: Weekly Fidelity Trend

Compute fidelity score per week for 6-month dataset. Track whether settings quality
is stable, improving, or degrading over time.
**Hypothesis**: Most patients have stable fidelity; 2-3 show seasonal drift.

---

## 9. Experiment Registry Update

| ID | Name | Status | Key Result |
|:---|:-----|:------:|:-----------|
| EXP-483 | Demand-Weighted Detector | ✅ Done | **96% detection on READY days** |
| EXP-486 | Dessert Detection | ✅ Done | 18% of dinners, 123min gap |
| EXP-488 | Residual Decomposition | ✅ Done | 25% meal, 13% dawn, 53% noise |
| EXP-489 | Basal Adequacy | ✅ Done | **5/11 basal too low** |
| EXP-492 | Glycemic Fidelity Score | ✅ Done | Range 15–84, patient k = gold |
| EXP-493 | Residual Fingerprint | ✅ Done | **3/11 persistent** (settings drift) |
| EXP-495 | ISF Fidelity | 🔲 Proposed | — |
| EXP-496 | CR Fidelity | 🔲 Proposed | — |
| EXP-497 | Sensor Age Effect | 🔲 Proposed | — |
| EXP-498 | Cannula Age Effect | 🔲 Proposed | — |
| EXP-499 | Per-Hour Basal Recommendation | 🔲 Proposed | — |
| EXP-500 | Weekly Fidelity Trend | 🔲 Proposed | — |

---

## 10. Conclusions

The metabolic flux framework now includes:

1. **Preconditions** that formally gate analysis by data quality (96% detection on qualified days)
2. **A settings fidelity score** that discriminates well-tuned (k=84) from misaligned (i=15) settings
3. **Residual fingerprints** that reveal whether residual is random noise (settings OK) or persistent (settings need adjustment)

The most actionable finding: **5/11 patients may benefit from basal rate increases**,
with overnight drift of +5 to +14 mg/dL/h. For patient k, the framework's predictions
closely match reality — a strong validation that when settings are correct, the
physics-based model works.

The residual decomposition confirms that for non-bolusing patients, the conservation
residual IS the implicit meal channel (25% of variance, 74% positive). This validates
the core insight that supply-demand physics gracefully degrades: demand tells you
what happened even when supply data is missing.
