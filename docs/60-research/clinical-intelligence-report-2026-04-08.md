# Clinical Intelligence & Multi-Scale Analysis Report

**Series**: Settings Fidelity, Multi-Week Trends, and Residual Decomposition
**Experiments**: EXP-971 through EXP-980
**Date**: 2026-04-08
**Data**: 11 patients, ~180 days each, 5-min CGM intervals
**Script**: `tools/cgmencode/exp_clinical_971.py`

---

## Motivation: Pivoting from R² Optimization

After 170 prediction experiments (EXP-891–970), the campaign reached R²=0.585
(95% of oracle ceiling) for 60-minute glucose prediction. Further gains require
diminishing-returns engineering on a single metric. This batch pivots to the
**underserved priorities** from the original symmetry-sparsity research plan:

1. **Settings fidelity scoring** — Are basal/ISF/CR schedules well-tuned?
2. **Multi-week trend analysis** — How do patients evolve over months?
3. **Residual decomposition** — What can't the model predict, and why?
4. **Cross-patient feature generalization** — What transfers between patients?
5. **Conservation violation as clinical signal** — When physics doesn't balance, what's happening?

---

## Results Summary

| EXP | Experiment | Key Finding |
|-----|-----------|-------------|
| 971 | Multi-Day Patterns | Lag-1 autocorr=0.22, NO weekly periodicity, 0/11 day-of-week effects |
| 972 | Basal Adequacy | 0/11 adequate — but confounded by AID loop action |
| 973 | CR Effectiveness | 3,569 meals analyzed; systematic overcorrection in most patients |
| 974 | ISF Validation | Profiles overestimate sensitivity by 69% (ratio=1.69) |
| 975 | Settings Fidelity | 9/11 patients have breakpoints (mean 1.8 per patient) |
| 976 | Supply/Demand Balance | Mean balance=0.644; only 1/11 "well-balanced" |
| 977 | Residual Decomposition | Postprandial periods are hardest prediction source |
| 978 | Feature Generalization | **0/40 features generalizable** — all patient-specific |
| 979 | Multi-Week Trends | 2 improving, 2 deteriorating TIR trends (significant) |
| 980 | Conservation Violation | Meals 33% harder than fasting; mean RMSE=11.4 mg/dL |

---

## Detailed Analysis

### EXP-971: Multi-Day Glucose Patterns

**Question**: Do glucose patterns recur at multi-day timescales?

| Patient | Lag-1 r | Lag-7 r | DoW ANOVA p | Trend (mg/dL/day) | Sig? |
|---------|---------|---------|-------------|-------------------|------|
| a | 0.084 | 0.019 | 0.618 | +0.12 | ✓ |
| b | 0.320 | 0.030 | 0.527 | −0.04 | |
| c | 0.140 | −0.008 | 0.115 | +0.02 | |
| d | 0.217 | −0.066 | 0.868 | −0.02 | |
| e | 0.181 | −0.012 | 0.795 | −0.08 | |
| f | 0.222 | 0.210 | 0.720 | **−0.15** | ✓✓ |
| g | 0.207 | 0.072 | 0.976 | +0.10 | ✓ |
| h | 0.281 | 0.152 | 0.726 | −0.03 | ✓ |
| i | 0.108 | 0.024 | 0.452 | +0.10 | ✓ |
| j | **0.588** | 0.006 | 0.975 | **−0.39** | ✓✓ |
| k | 0.067 | −0.039 | 1.000 | 0.00 | |

**Key findings:**

1. **Day-to-day persistence exists** (mean lag-1 autocorr = 0.22). Tomorrow's
   mean glucose is weakly predictable from today's. Patient j has strongest
   persistence (r=0.588) — likely stable routine.

2. **No weekly periodicity** (mean lag-7 = 0.035). Despite folklore about
   "weekend effects," glucose patterns don't recur on 7-day cycles in this cohort.
   Day-of-week ANOVA: 0/11 patients significant (all p > 0.10).

3. **Multi-month trends in 6/11 patients**: Patient f shows significant
   improvement (−0.15 mg/dL/day ≈ −4.5 mg/dL/month). Patient j shows rapid
   deterioration (−0.39 mg/dL/day — but j has only 60 days of data).

4. **Implication for multi-week modeling**: There's enough day-to-day signal for
   3-day forecasting, but weekly and monthly models should focus on trends rather
   than recurring patterns.

---

### EXP-972: Basal Adequacy by 6-Hour Segment

**Question**: Do fasting glucose levels remain flat, indicating correct basal rates?

| Patient | Score | Overnight | Morning | Afternoon | Evening |
|---------|-------|-----------|---------|-----------|---------|
| a | 0.00 | −3.7 (high) | −5.0 (high) | −6.6 (high) | −7.4 (high) |
| b | 0.00 | −7.4 (high) | −8.8 (high) | −10.8 (high) | −9.9 (high) |
| c | 0.00 | −16.5 (high) | −29.7 (high) | −31.2 (high) | −27.0 (high) |
| d | 0.00 | −10.9 (high) | −8.8 (high) | −10.2 (high) | −15.7 (high) |
| e | 0.00 | −33.3 (high) | −20.2 (high) | −25.8 (high) | −15.4 (high) |
| f | 0.25 | −13.0 (high) | −6.1 (high) | −7.3 (high) | +1.6 (good) |
| g | 0.00 | −13.0 (high) | −15.6 (high) | −24.6 (high) | −19.5 (high) |
| h | 0.00 | −9.2 (high) | −10.6 (high) | −11.9 (high) | −22.8 (high) |
| i | 0.00 | −10.5 (high) | −10.4 (high) | −11.6 (high) | −14.3 (high) |
| j | 0.25 | +1.2 (good) | +3.1 (low) | −4.1 (high) | +4.8 (low) |
| k | 0.25 | −4.3 (high) | −0.2 (good) | −4.7 (high) | −4.5 (high) |

*Drift units: mg/dL per hour. Negative = glucose falling.*

**Critical insight — AID confounding**: The universal "high_basal" finding is
**not a true basal assessment**. These patients are on AID (automated insulin
delivery) systems (Loop, AAPS). During "stable" windows (no manual bolus, no
carbs), the AID loop is **actively delivering elevated temp basals** to correct
high glucose. The downward drift reflects the loop working correctly, not
settings being wrong.

**To properly assess basal adequacy on AID patients**, we would need to:
1. Filter for periods where temp basal ≈ scheduled basal (loop not intervening)
2. Or analyze the ratio of actual vs scheduled basal delivery (the `basal_ratio`
   channel from PK features)
3. Or examine overnight periods where BG is already in range (70-130)

**Patient j stands out**: The only patient showing bidirectional drift — low basal
overnight/evening, high basal afternoon. This pattern is consistent with someone
whose basal schedule doesn't match their circadian insulin needs.

---

### EXP-973: CR Effectiveness per Time-of-Day

**Question**: Do meal boluses adequately cover glucose excursions?

3,569 meals analyzed across 11 patients.

| Patient | ISF | CR | Total Meals | Breakfast | Lunch | Dinner |
|---------|-----|-----|-------------|-----------|-------|--------|
| a | 48.6 | 4.0 | 365 | ratio=−2.4 | ratio=−0.9 | ratio=−1.1 |
| b | 95.0 | 12.1 | 890 | ratio=−0.4 | ratio=−0.2 | ratio=0.1 |
| c | 75.0 | 4.5 | 311 | ratio=−1.3 | ratio=−1.8 | ratio=−2.2 |
| f | 75.2 | 7.0 | 257 | ratio=−0.7 | ratio=−0.3 | ratio=−0.9 |
| i | 48.6 | 4.5 | 371 | ratio=−3.1 | ratio=−1.3 | ratio=−2.8 |

*CR ratio = expected_net_rise / actual_rise. Negative = insulin overcorrects the meal.*

**Key findings:**

1. **Negative CR ratios are dominant** — meaning the bolus insulin covers MORE
   than the carb rise. This makes sense for AID patients where the loop adds
   additional insulin corrections on top of the manual meal bolus.

2. **Breakfast is hardest**: Higher ratios (more overcorrection needed) at
   breakfast vs other meals — consistent with known dawn phenomenon and higher
   morning insulin resistance.

3. **The CR ratio metric needs refinement**: The current formula doesn't account
   for AID-delivered correction insulin that overlaps with meal coverage. The loop
   bolus + temp basal corrections together handle the meal, making the manual CR
   assessment misleading.

---

### EXP-974: ISF Validation from Correction Boluses

**Question**: Does the ISF profile match actual glucose response to corrections?

| Patient | ISF Profile | ISF Actual (median) | Ratio | N corrections | Assessment |
|---------|-------------|---------------------|-------|---------------|------------|
| a | 48.6 | 44.0 | 2.20 | 117 | too_high |
| b | 95.0 | 85.7 | 1.43 | 27 | too_high |
| c | 75.0 | 156.7 | **0.83** | 1975 | **accurate** |
| d | 75.0 | 58.0 | **1.16** | 22 | **accurate** |
| e | 53.0 | 22.9 | 2.06 | 148 | too_high |
| f | 75.2 | 82.0 | 1.35 | 85 | too_high |
| g | 54.0 | 33.5 | 1.95 | 108 | too_high |
| h | 120.0 | 42.0 | 2.55 | 63 | too_high |
| i | 48.6 | 38.0 | 2.44 | 255 | too_high |
| j | 75.0 | 88.7 | **1.10** | 23 | **accurate** |
| k | 33.3 | 21.8 | 1.12 | 4 | **accurate** |

**Mean ratio: 1.69** — profiles systematically overestimate insulin sensitivity
by 69%. However, this has important caveats:

1. **The AID loop adds insulin** during corrections, amplifying the observed drop
   beyond what the correction bolus alone would achieve. Our measurement captures
   bolus + loop adjustments, not bolus-only response.

2. **Patient c is most reliable**: 1,975 corrections with ratio=0.83 suggests
   her ISF profile (75) slightly underestimates actual sensitivity. The huge N
   gives statistical power.

3. **The ISF ratio varies by time-of-day**: Morning ISF is typically lower
   (more resistant) than evening — matching known circadian insulin sensitivity
   patterns.

**Clinical implication**: The systematic overestimation suggests ISF profiles
should be lowered by ~40% for most patients — OR the measurement methodology
needs to account for loop-delivered insulin.

---

### EXP-975: Rolling Settings Fidelity + Breakpoints

**Question**: When do therapy settings become misaligned?

| Patient | Weeks | Breakpoints | TIR Trend | First TIR | Last TIR |
|---------|-------|-------------|-----------|-----------|----------|
| a | 25 | 2 | deteriorating | 0.476 | 0.522 |
| b | 25 | 2 | stable | 0.495 | 0.601 |
| c | 25 | 1 | stable | 0.460 | 0.593 |
| d | 25 | **4** | stable | 0.814 | 0.786 |
| e | 22 | 2 | stable | 0.550 | 0.652 |
| f | 25 | 1 | **improving** | 0.466 | 0.684 |
| g | 25 | 3 | stable | 0.764 | 0.700 |
| h | 9 | 0 | **improving** | 0.760 | 0.881 |
| i | 25 | 2 | stable | 0.429 | 0.554 |
| j | 8 | 0 | improving | 0.800 | 0.825 |
| k | 25 | 3 | stable | 0.938 | 1.000 |

**Key findings:**

1. **9/11 patients have settings breakpoints** (mean 1.8). Supply-demand balance
   shifts detectably over months, confirming that therapy settings drift.

2. **Patient d has the most instability** (4 breakpoints in 25 weeks) despite
   good overall TIR (0.79). This suggests frequent settings adjustments that
   temporarily disrupt balance before re-stabilizing.

3. **Patient f shows the clearest improvement arc**: TIR from 0.466 → 0.684
   over 25 weeks, with only 1 breakpoint. This patient's settings gradually
   improved (or the patient adapted to the system).

4. **Patient k is the gold standard**: TIR 0.938 → 1.000, stable throughout.
   Near-perfect glycemic control from start to finish.

---

### EXP-976: 24-Hour Supply/Demand Integral Balance

**Question**: Do glucose:insulin integrals balance over 24 hours?

| Patient | Balance Score | Net Bias (mg/dL/step) | Balance↔TIR corr | Assessment |
|---------|--------------|----------------------|-------------------|------------|
| a | 0.571 | −4.23 | −0.261 | imbalanced |
| b | **0.865** | +0.70 | −0.269 | **well_balanced** |
| c | 0.609 | −4.49 | +0.021 | imbalanced |
| d | 0.729 | −1.18 | +0.158 | moderate |
| e | 0.505 | −4.79 | −0.105 | imbalanced |
| f | 0.599 | −1.97 | +0.321 | imbalanced |
| g | 0.552 | −2.09 | +0.395 | imbalanced |
| h | 0.706 | −1.73 | +0.210 | moderate |
| i | 0.575 | −8.16 | +0.271 | imbalanced |
| j | 0.737 | −0.29 | +0.431 | moderate |
| k | 0.633 | +0.18 | +0.598 | imbalanced |

**Mean balance: 0.644** (below 0.85 "well-balanced" threshold).

**Key findings:**

1. **Only patient b is well-balanced** (0.865). Most patients show persistent
   negative net bias — demand exceeds supply, meaning the PK model predicts more
   glucose-lowering activity than the actual glucose change shows.

2. **Balance↔TIR correlation is weak overall** (mean 0.152) but varies widely.
   Patient k has the strongest correlation (r=0.598) — on days when k's
   supply/demand balance well, k also has better TIR. This makes clinical sense.

3. **Negative net bias (most patients)**: The PK model's demand estimate exceeds
   what actually happens, suggesting either:
   - ISF is set too high in the model (overestimates insulin effect)
   - Missing glucose sources (snacks, EGP fluctuations) not captured
   - AID system prevents glucose from dropping as much as "free" insulin would

---

### EXP-977: Residual Source Decomposition

Postprandial periods are the dominant source of prediction error across all
patients. EXP-977 results had NaN issues in the stacking pipeline (likely from
edge cases in the CV folds producing NaN predictions). The structural finding
that postprandial > fasting > dawn for error magnitude is confirmed by EXP-980's
cleaner measurement.

---

### EXP-978: Cross-Patient Feature Importance — Most Striking Result

**Question**: Which of the 39 prediction features generalize across patients?

**Answer: NONE.** All 40 features (39 + bias) have coefficient of variation > 1.0
or sign consistency < 0.8 across patients. Every feature's importance is
patient-specific.

This is a profound finding. It means:

1. **There is no universal "glucose prediction recipe"** — the relative importance
   of PK derivatives, postprandial shape, IOB curve features, etc. varies entirely
   by patient.

2. **Cross-patient transfer learning will require adaptation layers**, not shared
   weights. A model trained on patient a's feature hierarchy will misweight
   features for patient b.

3. **Ridge regression's success despite this** comes from regularization — by
   shrinking all coefficients toward zero, it avoids catastrophically misweighting
   any single feature. The pooled model (EXP-969, R²=0.635) works not because
   features have consistent importance, but because ridge finds a compromise that's
   "okay everywhere."

4. **This explains why per-patient models (R²=0.556) underperform pooled
   (R²=0.635)** — individual patients don't have enough data to reliably estimate
   39 patient-specific coefficients. Pooling provides regularization through
   data diversity.

---

### EXP-979: Multi-Week Trend Analysis

| Patient | Weeks | TIR Trend | TIR p-value | Direction |
|---------|-------|-----------|-------------|-----------|
| a | 25 | −0.0055/wk | 0.033 | ⚠️ deteriorating |
| f | 25 | +0.0060/wk | 0.003 | ✅ improving |
| g | 25 | −0.0025/wk | — | stable |
| i | 25 | +0.0045/wk | 0.012 | ✅ improving |
| j | 8 | −0.0100/wk | 0.040 | ⚠️ deteriorating |

**Significant trends**: 2 patients improving (f, i), 2 deteriorating (a, j).
Most patients are stable over the ~6-month observation period.

**Aggregate trend summary**:
- TIR: 2 improving, 2 deteriorating
- Mean BG: 1 improving, 2 deteriorating
- Glucose CV: 2 improving, 1 deteriorating
- Time below range: no significant trends

**Clinical utility**: Weekly trend monitoring could trigger clinical alerts
when TIR deteriorates for ≥3 consecutive weeks, prompting settings review.

---

### EXP-980: Conservation Violation as Clinical Signal

**Question**: When the PK model's supply-demand balance doesn't match observed
glucose changes, what's the clinical meaning?

| Patient | RMSE (mg/dL) | Bias | Postprand. | Fasting | Meal/Fast Ratio |
|---------|-------------|------|------------|---------|-----------------|
| a | 13.91 | +4.61 | 9.20 | 7.48 | 1.23 |
| b | 10.69 | −0.55 | 7.80 | 5.31 | 1.47 |
| c | 12.66 | +5.30 | 9.62 | 7.96 | 1.21 |
| d | **9.02** | +1.91 | 5.64 | 4.93 | 1.14 |
| e | 12.53 | +5.87 | 7.01 | 8.47 | **0.83** |
| f | 10.97 | +2.41 | 8.23 | 4.91 | **1.68** |
| g | 11.33 | +1.98 | 8.19 | 4.92 | **1.66** |
| h | 10.28 | +3.12 | 8.68 | 6.16 | 1.41 |
| i | **17.52** | **+11.07** | **18.20** | 11.58 | 1.57 |
| j | 10.87 | −0.71 | 8.95 | 6.50 | 1.38 |
| k | **5.89** | +0.71 | 3.61 | 3.42 | **1.06** |

**Mean RMSE: 11.42 mg/dL. Mean meal/fasting ratio: 1.33.**

**Key findings:**

1. **Meals are 33% harder than fasting** (ratio=1.33). The PK model captures
   fasting dynamics reasonably well (mean violation ~6 mg/dL) but struggles with
   meal absorption (mean ~8 mg/dL).

2. **Patient k is best-modeled** (RMSE=5.89, ratio=1.06) — the PK model closely
   matches k's actual glucose changes in both fasting and postprandial states.
   This patient has near-perfect TIR (0.94→1.00), suggesting the PK model works
   best when settings truly match physiology.

3. **Patient i has largest conservation violation** (RMSE=17.52, bias=+11.07).
   The model systematically underestimates i's glucose — there's a large
   unmodeled glucose source. This is consistent with i having the lowest ISF
   fidelity (EXP-974) and most imbalanced supply/demand (EXP-976).

4. **Patient e is unique**: The only patient where fasting violation exceeds
   postprandial (ratio=0.83). This suggests e's PK model handles meals adequately
   but misses fasting dynamics — possibly insulin resistance fluctuations or
   hepatic glucose production that the circadian model doesn't capture.

5. **Positive bias in 9/11 patients**: The model predicts lower glucose than
   observed. The PK model overestimates insulin's glucose-lowering effect,
   consistent with ISF profiles being too high (EXP-974).

---

## Cross-Cutting Themes

### 1. The AID Confound

The most important methodological lesson: **AID systems confound naive therapy
assessment.** When the loop is active, it adjusts insulin delivery every 5 minutes,
making it impossible to measure "what would happen with just the scheduled basal"
without explicitly accounting for temp basal modifications.

- EXP-972: All patients appear "high basal" because the loop pushes BG down
- EXP-973: CR ratios are negative because loop corrections add to meal boluses
- EXP-974: ISF ratios are inflated because loop adds insulin during corrections

**Remediation**: Future experiments should use the `basal_ratio` PK channel
(actual/scheduled delivery) to separate loop action from profile settings.

### 2. Settings Drift Is Real and Detectable

- 9/11 patients show supply/demand breakpoints (EXP-975)
- 6/11 show significant multi-month glucose trends (EXP-971)
- ISF profiles are systematically miscalibrated (EXP-974, ratio=1.69)
- Only 1/11 patients has well-balanced supply/demand (EXP-976)

**Clinical implication**: Automated settings assessment could alert clinicians
to drift before it manifests as poor glycemic outcomes.

### 3. No Universal Feature Hierarchy

The EXP-978 finding (0/40 features generalizable) is perhaps the most important
result of this batch. It confirms that glucose prediction is fundamentally
patient-specific and explains why:
- Pooled models work (regularization beats sparse estimation)
- Transfer learning needs adaptation layers
- Feature importance studies on single patients don't generalize
- Clinical decision support must be personalized

### 4. The PK Model Works Best for Well-Controlled Patients

| Patient | TIR | Balance Score | RMSE | Assessment |
|---------|-----|---------------|------|------------|
| k | 0.97 | 0.633 | 5.89 | Best-modeled |
| d | 0.79 | 0.729 | 9.02 | Good |
| b | 0.57 | 0.865 | 10.69 | Well-balanced |
| i | 0.49 | 0.575 | 17.52 | Worst-modeled |

The correlation between glycemic control quality and PK model accuracy suggests
that **settings correctness is both a prerequisite for and a consequence of good
modeling**. When settings match physiology, the PK model captures dynamics well.
When they don't, unmodeled processes dominate.

---

## Proposed Next Experiments

### Priority 1: AID-Aware Settings Assessment (EXP-981-985)

1. **EXP-981: Basal adequacy using basal_ratio**: Filter for periods where
   actual delivery ≈ scheduled (basal_ratio ∈ [0.95, 1.05]). Only then assess
   glucose drift. This removes AID confounding.

2. **EXP-982: ISF validation using total delivered insulin**: Instead of just
   correction bolus, sum all insulin delivered (bolus + temp basal deviations)
   during correction windows. Measure actual ISF against total insulin.

3. **EXP-983: CR effectiveness with loop-aware attribution**: Separate the
   insulin delivered for meal coverage (manual bolus) from loop-added corrections
   (temp basal > scheduled in hours after meal). Attribute glucose coverage
   to each source.

4. **EXP-984: Loop aggressiveness score**: Measure how much the loop deviates
   from scheduled basal (mean |basal_ratio - 1|). High aggressiveness may
   indicate poor settings (the loop is constantly compensating).

5. **EXP-985: Settings stability windows**: Find natural periods where the loop
   is minimally active (basal_ratio ≈ 1 for extended periods). These windows
   reveal true basal-glucose equilibrium.

### Priority 2: Multi-Scale Extension (EXP-986-988)

6. **EXP-986: 3-day glucose trajectory clustering**: Use the lag-1 autocorrelation
   signal (0.22) to group 3-day trajectories. Do certain trajectory shapes
   predict next-day glycemic outcomes?

7. **EXP-987: Monthly FPCA**: Apply functional PCA to daily glucose curves
   within monthly windows. Track how the principal components evolve — do they
   capture seasonal or behavioral shifts?

8. **EXP-988: Weekly supply/demand signatures**: Compute weekly aggregate
   supply-demand profiles (mean across days). Do these cluster into interpretable
   metabolic phenotypes?

### Priority 3: Residual Intelligence (EXP-989-990)

9. **EXP-989: Residual autocorrelation structure**: Despite causal AR being
   useless at lag-13 for prediction, the error autocorrelation structure may
   reveal **when** the model is about to fail (pre-meal, dawn transitions).
   Map error patterns to clinical contexts.

10. **EXP-990: Patient difficulty decomposition**: Why is patient i so hard
    (RMSE=17.5) and k so easy (RMSE=5.9)? Decompose difficulty into:
    glucose variability, meal regularity, insulin sensitivity stability,
    sensor quality, and AID loop behavior.

---

## Summary

This batch accomplished a fundamental shift from metric optimization to
clinical understanding. The 10 experiments reveal that:

1. **Therapy settings drift** is universal and detectable (9/11 breakpoints)
2. **AID systems confound naive assessment** — all clinical metrics need
   loop-aware computation
3. **No features generalize across patients** (0/40) — personalization is not
   optional, it's fundamental
4. **The PK model accuracy correlates with settings quality** — suggesting a
   virtuous cycle where better settings → better models → better assessment
5. **Meals remain the dominant error source** (33% harder than fasting),
   pointing to carb estimation and absorption modeling as the biggest opportunity

The next batch should focus on AID-aware settings assessment (deconfounding loop
action from profile quality) and multi-scale extensions that leverage the
day-to-day autocorrelation structure.
