# Clinical Analysis Report — patient `live-recent`

_Generated: 2026-04-24T17:34:30.247480+00:00_  
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

| Floor | Events/day | In 2–8 target? |
|---|---|---|
| ≥5g | 1.00 | ❌ |
| ≥10g | 1.00 | ❌ |
| ≥20g | 1.00 | ❌ |
| ≥30g | 1.00 | ❌ |
| ≥50g | 1.00 | ❌ |

## 4. Meal-logging QC

- Flag: **under_logger**
- Logged: 2 (0.03/day)
- Inferred (rises): 176 (2.93/day)
- Logged / inferred ratio: 0.01  _(reconciliation rate; distinct from the `unannounced_meal_warning` fraction in §5, which is unannounced ÷ total detected meals)_

## 4a. Wave-13 facts (read-only)

**Basal mismatch (EXP-2869)**

| Field | Value |
|---|---|
| p_basal_mismatch | 0.00 |
| median_recommended_mult | 1.24 |

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

### Rec 1: adjust_isf (priority 2), predicted TIR Δ +26.0 pp
- Correction doses above 1.5U show diminishing returns. At 2.5U, each unit achieves only 18 mg/dL drop vs 40 mg/dL at 1U. Consider: (1) splitting large corrections into smaller doses spaced 30+ min apart, (2) using ISF=18 for doses ≥2U. This is a pharmacokinetic property (β=0.9), not circadian.
- Settings change: **isf** decrease 40.0 → 18.0 (+25 %)
- Rationale: Correction doses above 1.5U show diminishing returns. At 2.5U, each unit achieves only 18 mg/dL drop vs 40 mg/dL at 1U. Consider: (1) splitting large corrections into smaller doses spaced 30+ min apart, (2) using ISF=18 for doses ≥2U. This is a pharmacokinetic property (β=0.9), not circadian.

### Rec 2: adjust_basal_rate (priority 2), predicted TIR Δ +1.4 pp
- Increase overnight basal by 20% (from 1.70 to 2.04 U/hr). In closed-loop, combining glucose direction with loop compensation direction provides more reliable basal assessment than glucose alone.
- Settings change: **basal_rate** increase 1.7000000476837158 → 2.04 (+17 %)
- Rationale: Increase overnight basal by 20% (from 1.70 to 2.04 U/hr). In closed-loop, combining glucose direction with loop compensation direction provides more reliable basal assessment than glucose alone.

### Rec 3: adjust_correction_threshold (priority 2), predicted TIR Δ +0.1 pp
- Decrease correction threshold from 180 to 166 mg/dL. Corrections below 166 mg/dL show net-negative outcomes: glucose rebounds and hypo risk exceed the glucose-lowering benefit. Per-patient thresholds range 130-290 mg/dL. Predicted TIR improvement: +0.1pp.
- Settings change: **correction_threshold** decrease 180.0 → 166.0 (+8 %)
- Rationale: Decrease correction threshold from 180 to 166 mg/dL. Corrections below 166 mg/dL show net-negative outcomes: glucose rebounds and hypo risk exceed the glucose-lowering benefit. Per-patient thresholds range 130-290 mg/dL. Predicted TIR improvement: +0.1pp.

### Rec 4: unannounced_meal_warning (priority 3), predicted TIR Δ +2.0 pp
- 98% of detected meals have no carb entry. Logging meals improves prediction accuracy and enables better pre-bolus timing.

### Rec 5: clinical_insight (priority 3), predicted TIR Δ +1.0 pp
- Time above range is 33.6%. Consider reviewing correction factors and carb counting.

## 6. Plots

- ![AGP](plots/01_agp.png)
- ![Basal pattern](plots/04_basal_pattern.png)
- ![Meal floors](plots/05_meal_floors.png)
- ![EGP](plots/06_per_patient_egp.png)
