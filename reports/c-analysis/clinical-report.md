# Clinical Analysis Report — patient `c`

_Generated: 2026-07-01T18:12:32.291945+00:00_  
_Source parquet: `/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/ns-parquet/training`_  
_Profile timezone: `Etc/GMT+7`_  
_Days of data: 180.0_

## 1. Glycemic summary

| Metric | Value |
|---|---|
| Mean glucose (mg/dL) | 162.0 |
| GMI / eA1c (%) | 7.19 |
| TIR 70–180 (%) | 61.6 |
| TBR <70 (%) | 4.70 |
| TBR <54 (%) | 1.56 |
| TAR >180 (%) | 33.7 |
| TAR >250 (%) | 12.07 |
| CV (%) | 43.4 |
| n readings | 42,859 |

## 2. Per-patient EGP (read-only)

- Method: EXP-2739 fasting-drift, deep-fasting subset
- Patient glucose_roc (low-IOB fasting): **1.000** mg/dL/5min  (population _BASE_EGP=1.50)
- Controller basal multiplier in equilibrium: **0.00**
- Sample size: 8,449 deep-fasting rows, 176 equilibrium rows

## 3. Meal-isolation smell test

_Source: inferred meals from the production residual+insulin spectral detector (logged-carb input is treated as an unreliable prior). Logged column is shown for comparison only._

| Floor | Inferred events/day | Logged events/day | Target band | In band? |
|---|---|---|---|---|
| ≥5g | 0.09 | 2.14 | 2.0–10.0 | ❌ |
| ≥10g | 0.09 | 2.09 | 2.0–10.0 | ❌ |
| ≥20g | 0.03 | 1.30 | 2.0–8.0 | ❌ |
| ≥30g | 0.00 | 0.78 | 2.0–6.0 | ❌ |
| ≥50g | 0.00 | 0.01 | 1.0–3.0 | ❌ |

## 4. Meal-logging QC

- Flag: **phantom_logger**
- Logged: 377 (2.09/day)
- Inferred (rises): 17 (0.09/day)
- Logged / inferred ratio: 22.18  _(reconciliation rate; distinct from the `unannounced_meal_warning` fraction in §5, which is unannounced ÷ total detected meals)_

## 4a. Wave-13 facts (read-only)

**Controller dynamics (EXP-2753)**

| Field | Value |
|---|---|
| controller_type | loop |
| n_events | 368 |
| mean_correction_fraction | 0.154 |
| mean_smb_fraction | 0.846 |
| corr_denom_gap_closure | -0.43 |
| isf_profile_median | 75 |
| isf_corr_denom_median | 126 |

**Basal mismatch (EXP-2869)**

| Field | Value |
|---|---|
| p_basal_mismatch | 1.00 |
| median_recommended_mult | 0.00 |

**ISF gap (EXP-2861)**

| Field | Value |
|---|---|
| p_isf_under_correction | 0.00 |
| p_isf_over_correction | 1.00 |

**Recovery dynamics (EXP-2862)**

| Field | Value |
|---|---|
| p_low_recovery | 1.000 |

**Phenotype**

| Field | Value |
|---|---|
| stack_score | 4.100 |
| brake_ratio | 0.625 |
| counter_reg_intercept | None |
| beta_nadir | None |
| p_haaf | None |
| evening_bolus_excess_4h | None |
| evening_iob_at_descent | None |
| controller_lineage | loop |


## 5. Recommendations

### Rec 1: adjust_isf (priority 2), predicted TIR Δ +8.0 pp
- Increase ISF from 75 to 112 mg/dL/U during overnight (00:00-06:00). ISF varies 4.6-9× by time of day (EXP-2271). Observed 709 corrections in this block with median effective ISF 352 mg/dL/U. Consolidated TIR improvement across 6 blocks: +8.0 pp. NOTE: per-step change capped at ±50%; re-evaluate after observing under new setting.
- Settings change: **isf** increase 75.0 → 112.5 (+25 %)
- Rationale: Increase ISF from 75 to 112 mg/dL/U during overnight (00:00-06:00). ISF varies 4.6-9× by time of day (EXP-2271). Observed 709 corrections in this block with median effective ISF 352 mg/dL/U. Consolidated TIR improvement across 6 blocks: +8.0 pp. NOTE: per-step change capped at ±50%; re-evaluate after observing under new setting.

### Rec 2: adjust_cr (priority 2), predicted TIR Δ -4.1 pp
- Decrease morning CR from 4.5 to 3.8 g/U (15% more insulin). Mean post-meal excursion is 71 mg/dL.
- Settings change: **cr** decrease 4.5 → 3.8 (+25 %)
- Rationale: Decrease morning CR from 4.5 to 3.8 g/U (15% more insulin). Mean post-meal excursion is 71 mg/dL.

### Rec 3: adjust_correction_threshold (priority 2), predicted TIR Δ +0.7 pp
- Increase correction threshold from 180 to 250 mg/dL. Corrections below 250 mg/dL show net-negative outcomes: glucose rebounds and hypo risk exceed the glucose-lowering benefit. Per-patient thresholds range 130-290 mg/dL. Predicted TIR improvement: +0.7pp.
- Settings change: **correction_threshold** increase 180.0 → 250.0 (+25 %)
- Rationale: Increase correction threshold from 180 to 250 mg/dL. Corrections below 250 mg/dL show net-negative outcomes: glucose rebounds and hypo risk exceed the glucose-lowering benefit. Per-patient thresholds range 130-290 mg/dL. Predicted TIR improvement: +0.7pp.

### Rec 4: adjust_basal_rate (priority 3), predicted TIR Δ +2.2 pp
- Decrease overnight basal by 20% (from 1.40 to 1.12 U/hr). In closed-loop, combining glucose direction with loop compensation direction provides more reliable basal assessment than glucose alone.  ⚠️ Conflicts with overnight assessment (suggested +3.8% basal change, confidence 0.49). Possible alcohol- or EGP-suppression overnight pattern; do not act on this without clinician review.
- Settings change: **basal_rate** decrease 1.399999976158142 → 1.12 (+25 %)
- Rationale: Decrease overnight basal by 20% (from 1.40 to 1.12 U/hr). In closed-loop, combining glucose direction with loop compensation direction provides more reliable basal assessment than glucose alone.

### Rec 5: clinical_insight (priority 3), predicted TIR Δ +1.0 pp
- Time below range is 4.7% (target <4%). Review insulin delivery around low glucose periods.

### Rec 6: loop_override_recommendation (priority 3), predicted TIR Δ +1.5 pp
- Consider configuring a controller override named "Dinner Aggressive" active 18:00–06:00 with target 100 mg/dL and ISF ratio 0.85 (75 → 64). Late-night peak (290 mg/dL) sits 132 mg/dL above the dinner baseline (158 mg/dL), indicating sustained post-dinner overshoot — current evening settings under-cover the late absorption phase.

### Rec 7: design_migration_hypothetical (priority 3), predicted TIR Δ +14.0 pp
- Cross-design hypothetical (EXP-2916–2944): a patient with your current profile (TIR 62%, TBR 4.7%, TAR 34%) on Loop migrating to Trio or AAPS (oref1) would expect roughly +14.0 pp TIR (+0.0 pp TBR, -16.3 pp TAR) based on cohort means. ⚠️ Caveat: TBR<70 is 4.7% and TBR<54 is 1.17%. The oref1 SMB-as-correction profile fires more aggressively and may deepen overnight hypos when the underlying cause is hepatic suppression (alcohol, late meals) rather than under-dosing. Discuss with your clinician before migrating.

## 6. Plots

- ![AGP](plots/01_agp.png)
- ![Channel mix](plots/02_controller_donut.png)
- ![ISF reconciliation](plots/03_isf_reconciliation.png)
- ![Basal pattern](plots/04_basal_pattern.png)
- ![Meal floors](plots/05_meal_floors.png)
- ![EGP](plots/06_per_patient_egp.png)
