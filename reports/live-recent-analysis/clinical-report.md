# Clinical Analysis Report — patient `live-recent`

_Generated: 2026-04-27T16:33:36.731905+00:00_  
_Source parquet: `/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/ns-parquet/live-recent`_  
_Profile timezone: `Etc/GMT+7`_  
_Days of data: 60.0_

## 1. Glycemic summary

| Metric | Value |
|---|---|
| Mean glucose (mg/dL) | 165.8 |
| GMI / eA1c (%) | 7.28 |
| TIR 70–180 (%) | 59.7 |
| TBR <70 (%) | 2.63 |
| TBR <54 (%) | 0.52 |
| TAR >180 (%) | 37.7 |
| TAR >250 (%) | 9.92 |
| CV (%) | 38.4 |
| n readings | 14,804 |

## 2. Per-patient EGP (read-only)

- Method: EXP-2739 fasting-drift, deep-fasting subset
- Patient glucose_roc (low-IOB fasting): **-1.000** mg/dL/5min  (population _BASE_EGP=1.50)
- Controller basal multiplier in equilibrium: **1.32**
- Sample size: 6,223 deep-fasting rows, 1,311 equilibrium rows

## 3. Meal-isolation smell test

_Source: inferred meals from the production residual+insulin spectral detector (logged-carb input is treated as an unreliable prior). Logged column is shown for comparison only._

| Floor | Inferred events/day | Logged events/day | Target band | In band? |
|---|---|---|---|---|
| ≥5g | 1.95 | 0.03 | 2.0–10.0 | ❌ |
| ≥10g | 1.95 | 0.03 | 2.0–10.0 | ❌ |
| ≥20g | 1.92 | 0.02 | 2.0–8.0 | ❌ |
| ≥30g | 1.82 | 0.02 | 2.0–6.0 | ❌ |
| ≥50g | 1.32 | 0.00 | 1.0–3.0 | ✅ |

## 4. Meal-logging QC

- Flag: **under_logger**
- Logged: 2 (0.03/day)
- Inferred (rises): 117 (1.95/day)
- Logged / inferred ratio: 0.02  _(reconciliation rate; distinct from the `unannounced_meal_warning` fraction in §5, which is unannounced ÷ total detected meals)_

## 4a. Wave-13 facts (read-only)

**Basal mismatch (EXP-2869)**

| Field | Value |
|---|---|
| p_basal_mismatch | 0.00 |
| median_recommended_mult | 1.28 |

**Phenotype**

| Field | Value |
|---|---|
| stack_score | 3.000 |
| brake_ratio | 0.295 |
| counter_reg_intercept | None |
| beta_nadir | None |
| p_haaf | None |
| evening_bolus_excess_4h | None |
| evening_iob_at_descent | None |
| controller_lineage | None |


## 5. Recommendations

### Rec 1: adjust_isf (priority 2), predicted TIR Δ +1.5 pp
- PATIENCE MODE (EXP-2662): Cap IOB at 1.9U (1.5× median IOB of 1.2U) during wall episodes. Saves 60–82% of SMBs with ≤+2.1pp hyper increase. Additional insulin at the SC suppression ceiling has negligible glucose-lowering effect but increases delayed hypo risk.
- Settings change: **isf** informational 1.23 → 1.85 (+0 %)
- Rationale: PATIENCE MODE (EXP-2662): Cap IOB at 1.9U (1.5× median IOB of 1.2U) during wall episodes. Saves 60–82% of SMBs with ≤+2.1pp hyper increase. Additional insulin at the SC suppression ceiling has negligible glucose-lowering effect but increases delayed hypo risk.

### Rec 2: adjust_basal_rate (priority 2), predicted TIR Δ +1.0 pp
- Increase overnight basal by 20% (from 1.70 to 2.04 U/hr). In closed-loop, combining glucose direction with loop compensation direction provides more reliable basal assessment than glucose alone.
- Settings change: **basal_rate** increase 1.7000000476837158 → 2.04 (+20 %)
- Rationale: Increase overnight basal by 20% (from 1.70 to 2.04 U/hr). In closed-loop, combining glucose direction with loop compensation direction provides more reliable basal assessment than glucose alone.

### Rec 3: adjust_correction_threshold (priority 2), predicted TIR Δ +0.1 pp
- Decrease correction threshold from 180 to 166 mg/dL. Corrections below 166 mg/dL show net-negative outcomes: glucose rebounds and hypo risk exceed the glucose-lowering benefit. Per-patient thresholds range 130-290 mg/dL. Predicted TIR improvement: +0.1pp.
- Settings change: **correction_threshold** decrease 180.0 → 166.0 (+8 %)
- Rationale: Decrease correction threshold from 180 to 166 mg/dL. Corrections below 166 mg/dL show net-negative outcomes: glucose rebounds and hypo risk exceed the glucose-lowering benefit. Per-patient thresholds range 130-290 mg/dL. Predicted TIR improvement: +0.1pp.

### Rec 4: unannounced_meal_warning (priority 3), predicted TIR Δ +2.0 pp
- 99% of detected meals have no carb entry. Logging meals improves prediction accuracy and enables better pre-bolus timing.

### Rec 5: clinical_insight (priority 3), predicted TIR Δ +1.0 pp
- Time above range is 37.7%. Consider reviewing correction factors and carb counting.

### Rec 6: loop_override_recommendation (priority 3), predicted TIR Δ +1.5 pp
- Consider configuring a controller override named "Dinner Aggressive" active 18:00–06:00 with target 100 mg/dL and ISF ratio 0.85 (40 → 34). Late-night peak (303 mg/dL) sits 179 mg/dL above the dinner baseline (124 mg/dL), indicating sustained post-dinner overshoot — current evening settings under-cover the late absorption phase.

### Rec 7: design_migration_hypothetical (priority 3), predicted TIR Δ +14.0 pp
- Cross-design hypothetical (EXP-2916–2944): a patient with your current profile (TIR 60%, TBR 2.6%, TAR 38%) on Loop migrating to Trio or AAPS (oref1) would expect roughly +14.0 pp TIR (+0.0 pp TBR, -16.3 pp TAR) based on cohort means. This is a directional estimate from cross-design pooling, not a per-patient simulation. Settings tuning on the current controller may capture much of the same benefit (see other recommendations in this report).

## 6. Plots

- ![AGP](plots/01_agp.png)
- ![Basal pattern](plots/04_basal_pattern.png)
- ![Meal floors](plots/05_meal_floors.png)
- ![EGP](plots/06_per_patient_egp.png)
