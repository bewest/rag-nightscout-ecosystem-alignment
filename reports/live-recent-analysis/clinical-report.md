# Clinical Analysis Report — patient `live-recent`

_Generated: 2026-04-24T23:15:16.044053+00:00_  
_Source parquet: `/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/ns-parquet/live-recent`_  
_Profile timezone: `Etc/GMT+8`_  
_Days of data: 60.0_

## 1. Glycemic summary

| Metric | Value |
|---|---|
| Mean glucose (mg/dL) | 160.3 |
| GMI / eA1c (%) | 7.14 |
| TIR 70–180 (%) | 63.8 |
| TBR <70 (%) | 2.68 |
| TBR <54 (%) | 0.14 |
| TAR >180 (%) | 33.5 |
| TAR >250 (%) | 8.76 |
| CV (%) | 39.3 |
| n readings | 16,035 |

## 2. Per-patient EGP (read-only)

- Method: EXP-2739 fasting-drift, deep-fasting subset
- Patient glucose_roc (low-IOB fasting): **-1.000** mg/dL/5min  (population _BASE_EGP=1.50)
- Controller basal multiplier in equilibrium: **1.22**
- Sample size: 6,734 deep-fasting rows, 1,537 equilibrium rows

## 3. Meal-isolation smell test

_Source: inferred meals from the production residual+insulin spectral detector (logged-carb input is treated as an unreliable prior). Logged column is shown for comparison only._

| Floor | Inferred events/day | Logged events/day | Target band | In band? |
|---|---|---|---|---|
| ≥5g | 2.42 | 0.03 | 2.0–10.0 | ✅ |
| ≥10g | 2.42 | 0.03 | 2.0–10.0 | ✅ |
| ≥20g | 2.35 | 0.03 | 2.0–8.0 | ✅ |
| ≥30g | 2.15 | 0.03 | 2.0–6.0 | ✅ |
| ≥50g | 1.33 | 0.02 | 1.0–3.0 | ✅ |

## 4. Meal-logging QC

- Flag: **under_logger**
- Logged: 2 (0.03/day)
- Inferred (rises): 145 (2.42/day)
- Logged / inferred ratio: 0.01  _(reconciliation rate; distinct from the `unannounced_meal_warning` fraction in §5, which is unannounced ÷ total detected meals)_

## 4a. Wave-13 facts (read-only)

**Basal mismatch (EXP-2869)**

| Field | Value |
|---|---|
| p_basal_mismatch | 0.97 |
| median_recommended_mult | 1.23 |

**Phenotype**

| Field | Value |
|---|---|
| stack_score | 2.000 |
| brake_ratio | 0.254 |
| counter_reg_intercept | None |
| beta_nadir | None |
| p_haaf | None |
| evening_bolus_excess_4h | None |
| evening_iob_at_descent | None |
| controller_lineage | None |


## 5. Recommendations

### Rec 1: adjust_isf (priority 2), predicted TIR Δ +1.5 pp
- PATIENCE MODE (EXP-2662): Cap IOB at 1.6U (1.5× median IOB of 1.1U) during wall episodes. Saves 60–82% of SMBs with ≤+2.1pp hyper increase. Additional insulin at the SC suppression ceiling has negligible glucose-lowering effect but increases delayed hypo risk.
- Settings change: **isf** informational 1.08 → 1.62 (+0 %)
- Rationale: PATIENCE MODE (EXP-2662): Cap IOB at 1.6U (1.5× median IOB of 1.1U) during wall episodes. Saves 60–82% of SMBs with ≤+2.1pp hyper increase. Additional insulin at the SC suppression ceiling has negligible glucose-lowering effect but increases delayed hypo risk.

### Rec 2: adjust_basal_rate (priority 2), predicted TIR Δ -0.5 pp
- Decrease basal by 10% (from 1.70 to 1.53 U/hr) between 00:00-06:00. Predicted to improve overnight TIR by -0.5 percentage points. Confirmable within 1 week of data.
- Settings change: **basal_rate** decrease 1.7000000476837158 → 1.53 (+10 %)
- Rationale: Decrease basal by 10% (from 1.70 to 1.53 U/hr) between 00:00-06:00. Predicted to improve overnight TIR by -0.5 percentage points. Confirmable within 1 week of data.

### Rec 3: adjust_correction_threshold (priority 2), predicted TIR Δ +0.1 pp
- Decrease correction threshold from 180 to 166 mg/dL. Corrections below 166 mg/dL show net-negative outcomes: glucose rebounds and hypo risk exceed the glucose-lowering benefit. Per-patient thresholds range 130-290 mg/dL. Predicted TIR improvement: +0.1pp.
- Settings change: **correction_threshold** decrease 180.0 → 166.0 (+8 %)
- Rationale: Decrease correction threshold from 180 to 166 mg/dL. Corrections below 166 mg/dL show net-negative outcomes: glucose rebounds and hypo risk exceed the glucose-lowering benefit. Per-patient thresholds range 130-290 mg/dL. Predicted TIR improvement: +0.1pp.

### Rec 4: unannounced_meal_warning (priority 3), predicted TIR Δ +2.0 pp
- 98% of detected meals have no carb entry. Logging meals improves prediction accuracy and enables better pre-bolus timing.

### Rec 5: clinical_insight (priority 3), predicted TIR Δ +1.0 pp
- Time above range is 33.6%. Consider reviewing correction factors and carb counting.

### Rec 6: loop_override_recommendation (priority 3), predicted TIR Δ +1.5 pp
- Consider configuring a controller override named "Dinner Aggressive" active 18:00–06:00 with target 100 mg/dL and ISF ratio 0.85 (40 → 34). Late-night peak (317 mg/dL) sits 186 mg/dL above the dinner baseline (131 mg/dL), indicating sustained post-dinner overshoot — current evening settings under-cover the late absorption phase.

### Rec 7: design_migration_hypothetical (priority 3), predicted TIR Δ +14.0 pp
- Cross-design hypothetical (EXP-2916–2944): a patient with your current profile (TIR 64%, TBR 2.6%, TAR 34%) on Loop migrating to Trio or AAPS (oref1) would expect roughly +14.0 pp TIR (+0.0 pp TBR, -16.3 pp TAR) based on cohort means. This is a directional estimate from cross-design pooling, not a per-patient simulation. Settings tuning on the current controller may capture much of the same benefit (see other recommendations in this report).

## 6. Plots

- ![AGP](plots/01_agp.png)
- ![Basal pattern](plots/04_basal_pattern.png)
- ![Meal floors](plots/05_meal_floors.png)
- ![EGP](plots/06_per_patient_egp.png)
