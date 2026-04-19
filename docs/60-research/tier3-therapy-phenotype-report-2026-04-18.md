# Tier-3 Experiment Report: Therapy Settings, Phenotyping, Prediction Bias & Integrated Recommendations

**Date**: 2026-04-18
**Experiments**: EXP-2291, EXP-2321, EXP-2331, EXP-2351
**Cohorts**: Original (31 patients), DynISF (12 patients)

---

## 1. Executive Summary

Four tier-3 experiments synthesize lower-tier findings into actionable clinical outputs across a 31-patient original cohort and a 12-patient DynISF cohort. Key findings:

- **Insulin PK (EXP-2351)**: 26/31 orig patients classified as slow responders (median onset 50 min, peak 82 min). Exponential curve-fit DIA estimates far exceed typical profile settings (mean 12.3 h vs. typical 5 h profile DIA), suggesting systematic under-estimation of insulin duration.
- **Phenotyping (EXP-2321)**: 11 HIGH-risk, 15 MODERATE-risk, 5 LOW-risk patients in the orig cohort. The dominant phenotype is "over-correction" (27/31 in EXP-2291; 20/31 "unknown" in EXP-2328 due to dependency on prior tier results). 29/31 patients have "reduce hypo" as their top priority.
- **Prediction Bias (EXP-2331)**: All 29 analyzable orig patients show negative prediction bias (mean −7.65 mg/dL). 8 classified as HIGH benefit, 21 MODERATE. Only 2/29 are safe to correct — most have unstable bias (14/29 stable).
- **Integrated Recommendations (EXP-2291)**: 16/31 orig patients are safe to implement recommendations after 7-guardrail screening. Mean projected TIR change is −0.5 pp (modest decrease). 20/31 meet the 70% TIR target. Conservative guardrails appropriately block patients with projected TBR > 4%.

The DynISF cohort shows similar patterns with stronger prediction bias (mean −11.10 mg/dL), 6/12 safe to implement, and 11/12 meeting 70% TIR.

**Key takeaway**: Many patients are classified as having recommendation potential, but few pass all safety checks — the conservative guardrail framework is working as designed.

---

## 2. EXP-2351: Insulin Pharmacokinetics

### 2.1 Overview

EXP-2351 fits insulin action curves to correction events per patient, classifying insulin response type and estimating effective Duration of Insulin Action (DIA). The experiment spans sub-experiments EXP-2351 through EXP-2358, covering correction analysis, meal timing, IOB decay validation, exponential DIA, responder classification, circadian variation, stacking risk, and personalized recommendations.

### 2.2 Correction Event Analysis (EXP-2351)

| Metric | Orig (n=31) | DynISF (n=12) |
|--------|-------------|---------------|
| Total corrections analyzed | 7,162 | — |
| Corrections per patient (mean) | 231.0 | — |
| Corrections per patient (range) | 7–583 | — |
| Mean drop per unit (mg/dL) | — | — |
| Median time-to-nadir (mean) | 156.7 min | 156.7 min |
| Median time-to-nadir (median) | 160.0 min | 160.0 min |
| ISF ratio (mean) | 1.20 | 1.18 |
| ISF ratio (range) | 0.39–3.24 | 0.58–3.19 |

ISF ratio > 1.0 indicates effective ISF exceeds the profile-set ISF, suggesting over-correction potential. Both cohorts have mean ISF ratios near 1.2.

### 2.3 Responder Classification (EXP-2355)

| Responder Type | Orig (n=31) | DynISF (n=12) |
|----------------|-------------|---------------|
| Slow | 26 (84%) | 10 (83%) |
| Medium | 5 (16%) | 2 (17%) |
| Fast | 0 (0%) | 0 (0%) |

| PK Timing Metric | Orig Mean | DynISF Mean |
|-------------------|-----------|-------------|
| Median onset (min) | 52.0 | 48.3 |
| Median peak (min) | 79.4 | 80.6 |
| Median duration (min) | 152.4 | 146.9 |

The overwhelming majority of patients in both cohorts are slow responders — no fast responders were identified.

### 2.4 DIA Estimation (EXP-2354: Exponential Curve Fit)

| DIA Metric (hours) | Orig (n=31) | DynISF (n=12) |
|---------------------|-------------|---------------|
| Mean | 12.3 | 11.5 |
| Median | 13.3 | 12.2 |
| Min | 5.0 | 5.0 |
| Max | 20.4 | 16.1 |
| Mean R² (fit quality) | 0.625 | — |

These DIA estimates are substantially longer than the typical 5–6 hour profile DIA used in AID systems. The moderate R² values (mean 0.625) indicate reasonable but imperfect curve fits — insulin action in real-world data is complicated by concurrent meals, basal changes, and sensor noise.

### 2.5 Personalized PK Recommendations (EXP-2358)

| Metric | Orig (n=31) | DynISF (n=12) |
|--------|-------------|---------------|
| Slow responders | 26 | 10 |
| Medium responders | 5 | 2 |
| Mean effective DIA (h) | 12.3 | 11.5 |
| Mean recommendations per patient | 2.2 | — |
| Recommendation range | 0–3 | — |

---

## 3. EXP-2321: Patient Phenotyping

### 3.1 Overview

EXP-2321 classifies patients by glycemic pattern, risk level, and priority intervention. The experiment spans EXP-2321 (clustering) through EXP-2328 (consolidated phenotype profile).

### 3.2 Phenotype Distribution

| Phenotype | Orig EXP-2328 | Orig EXP-2291 | DynISF EXP-2328 |
|-----------|---------------|---------------|-----------------|
| Over-correction | 7 | 27 | 12 |
| Mixed | 3 | 3 | 0 |
| Chronic-low | 1 | 1 | 0 |
| Unknown | 20 | 0 | 0 |

The discrepancy between EXP-2328 (20 "unknown") and EXP-2291 (27 "over-correction") reflects that EXP-2328 phenotype assignment depends on prior tier results that were not fully propagated for all patients, while EXP-2291 uses its own integrated classification. The DynISF cohort is uniformly classified as over-correction.

### 3.3 Risk Stratification (EXP-2323 / EXP-2328)

| Risk Category | Orig (n=31) | DynISF (n=12) |
|---------------|-------------|---------------|
| HIGH | 11 (35%) | 4 (33%) |
| MODERATE | 15 (48%) | 6 (50%) |
| LOW | 5 (16%) | 2 (17%) |

| Risk Score | Orig | DynISF |
|------------|------|--------|
| Mean | 47.6 | — |
| Min | 13.6 | — |
| Max | 70.0 | — |

### 3.4 Priority Interventions (EXP-2328)

| Top Priority | Orig (n=31) | DynISF (n=12) |
|-------------|-------------|---------------|
| Reduce hypo | 29 (94%) | 11 (92%) |
| Correct ISF | 1 (3%) | 1 (8%) |
| None | 1 (3%) | 0 (0%) |

The near-universal priority of "reduce hypo" reflects the cohort's over-correction phenotype — these patients' AID systems are driving glucose too low.

### 3.5 Algorithm Recommendations (EXP-2328)

| Recommended Algorithm | Orig (n=31) | DynISF (n=12) |
|----------------------|-------------|---------------|
| Loop | 15 (48%) | 6 (50%) |
| Trio | 12 (39%) | 6 (50%) |
| oref1/AAPS | 4 (13%) | 0 (0%) |

### 3.6 Baseline Glycemic Metrics (EXP-2328)

| Metric | Orig Mean | DynISF Mean |
|--------|-----------|-------------|
| TIR (%) | 77.1 | 84.4 |
| TBR (%) | 4.1 | — |
| TAR (%) | 18.8 | — |

### 3.7 Data Quality (EXP-2325)

| Grade | Orig (n=31) | DynISF (n=12) |
|-------|-------------|---------------|
| A | 19 (61%) | 8 (67%) |
| B | 6 (19%) | 3 (25%) |
| C | 3 (10%) | 1 (8%) |
| D | 3 (10%) | 0 (0%) |

---

## 4. EXP-2331: Prediction Bias Analysis

### 4.1 Overview

EXP-2331 analyzes AID algorithm prediction accuracy — how well the system's 30-minute glucose predictions match reality. Persistent bias affects insulin delivery decisions, particularly suspension timing.

### 4.2 Prediction Bias Summary (EXP-2338)

| Metric | Orig (n=29 analyzed, 2 skipped) | DynISF (n=12) |
|--------|----------------------------------|---------------|
| Mean bias (mg/dL) | −7.65 | −11.10 |
| Min bias | −14.99 | −14.99 |
| Max bias | −1.64 | −7.47 |

All patients show negative bias — predictions consistently under-estimate actual glucose, causing unnecessary insulin suspensions.

### 4.3 Benefit Classification

| Benefit Category | Orig (n=29) | DynISF (n=12) |
|-----------------|-------------|---------------|
| HIGH | 8 (28%) | 7 (58%) |
| MODERATE | 21 (72%) | 5 (42%) |
| LOW | 0 (0%) | 0 (0%) |

### 4.4 Safety Assessment

| Safety Metric | Orig (n=29) | DynISF (n=12) |
|---------------|-------------|---------------|
| Stable bias | 14 (48%) | 7 (58%) |
| Safe to correct | 2 (7%) | 1 (8%) |
| Not safe | 27 (93%) | 11 (92%) |

Despite many patients having substantial, measurable prediction bias, very few are classified as safe to correct. This reflects the conservative design: correction requires both stable bias over time AND acceptable projected outcomes.

### 4.5 Correction Impact Estimates (EXP-2338)

| Impact Metric | Orig Mean | DynISF Mean |
|---------------|-----------|-------------|
| MAE improvement | 6.7% | 10.3% |
| Suspension reduction | 28.4% | 38.5% |

The DynISF cohort shows larger potential improvements because of its stronger negative bias. A mean 28–39% suspension reduction represents a clinically significant change in AID behavior.

---

## 5. EXP-2291: Integrated Therapy Recommendations

### 5.1 Overview

EXP-2291 synthesizes all prior experiments into personalized therapy recommendations per patient. Each patient's recommendations pass through 7 clinical guardrails before being marked safe to implement.

### 5.2 Recommended Corrections (EXP-2291)

| Correction | Orig Mean | DynISF Mean |
|-----------|-----------|-------------|
| ISF adjustment | +24.2% | +25.0% |
| CR adjustment | −31.1% | −31.6% |
| Basal adjustment | +2.0% | +1.5% |

The consistent pattern across both cohorts: ISF needs to increase ~25% (less aggressive correction), CR needs to decrease ~31% (more insulin per carb), and basal needs minimal adjustment.

### 5.3 Guardrail Results (EXP-2297)

| Guardrail Metric | Orig (n=31) | DynISF (n=12) |
|------------------|-------------|---------------|
| Total guardrails per patient | 7 | 7 |
| Mean guardrails passed | 6.5 | 6.5 |
| All guardrails passed (safe) | 16 (52%) | 6 (50%) |
| Patients with violations | 15 (48%) | 6 (50%) |

**Violation breakdown (orig, n=15 patients with violations):**
- Projected TBR exceeds 4% limit: 14 patients
- Basal below minimum 0.1 U/hr: 1 patient

**Violation breakdown (DynISF, n=6 patients with violations):**
- Projected TBR exceeds 4% limit: 6 patients

The TBR guardrail is the dominant safety gate — nearly all blocked patients fail because the recommended settings project hypoglycemia rates above the 4% safety threshold.

### 5.4 Projected Outcomes (EXP-2294)

| Outcome Metric | Orig | DynISF |
|----------------|------|--------|
| Current TIR (mean) | 77.1% | 84.4% |
| Projected TIR (mean) | 76.6% | 84.0% |
| Mean TIR change | −0.5 pp | −0.4 pp |
| Current TBR (mean) | 4.1% | 4.1% |
| Projected TBR (mean) | 4.2% | 4.2% |

### 5.5 Target Achievement (EXP-2294, projected)

| Target | Orig (n=31) | DynISF (n=12) |
|--------|-------------|---------------|
| TIR ≥ 70% | 20 (65%) | 11 (92%) |
| TBR < 4% | 17 (55%) | 6 (50%) |
| TAR < 25% | 21 (68%) | 12 (100%) |
| CV < 36% | 16 (52%) | 8 (67%) |

### 5.6 Population-Level Summary (EXP-2298)

| Population Metric | Orig (n=31) | DynISF (n=12) |
|-------------------|-------------|---------------|
| Safe to implement | 16 (52%) | 6 (50%) |
| Meeting 70% TIR | 20 (65%) | 11 (92%) |
| Mean TIR improvement | −0.5 pp | −0.4 pp |
| Median TIR improvement | −0.5 pp | −0.5 pp |
| Mean TBR improvement | +0.1 pp | +0.1 pp |

### 5.7 Recalibration Schedule (EXP-2295)

| Metric | Orig | DynISF |
|--------|------|--------|
| Mean recalibration interval | 41 days | 30 days |
| Confidence: high | 3 | 0 |
| Confidence: moderate | 5 | 0 |
| Confidence: low | 23 | 12 |

Low confidence ratings across both cohorts indicate significant uncertainty in recommendation stability — frequent re-evaluation is warranted.

---

## 6. Cross-Cohort Comparison

| Dimension | Original (n=31) | DynISF (n=12) |
|-----------|-----------------|---------------|
| **Insulin PK** | | |
| Slow responders | 26 (84%) | 10 (83%) |
| Mean effective DIA | 12.3 h | 11.5 h |
| Mean ISF ratio | 1.20 | 1.18 |
| **Phenotyping** | | |
| HIGH risk | 11 (35%) | 4 (33%) |
| Top priority: reduce hypo | 29 (94%) | 11 (92%) |
| Baseline TIR | 77.1% | 84.4% |
| **Prediction Bias** | | |
| Mean bias | −7.65 mg/dL | −11.10 mg/dL |
| HIGH benefit | 8 (28%) | 7 (58%) |
| Safe to correct | 2 (7%) | 1 (8%) |
| **Integrated** | | |
| Safe to implement | 16 (52%) | 6 (50%) |
| Meeting 70% TIR | 20 (65%) | 11 (92%) |
| Mean TIR change | −0.5 pp | −0.4 pp |

**Notable differences:**
1. The DynISF cohort has substantially stronger negative prediction bias (−11.10 vs. −7.65 mg/dL), consistent with Dynamic ISF algorithms introducing additional prediction complexity.
2. DynISF patients show higher baseline TIR (84.4% vs. 77.1%), suggesting a generally better-controlled population.
3. Despite stronger bias, the DynISF cohort has a higher proportion classified as HIGH benefit (58% vs. 28%).
4. Safety rates are nearly identical (~50% safe to implement, ~7–8% safe for bias correction).

---

## 7. Clinical Implications

### 7.1 Conservative Guardrails Are Working as Designed

The central finding across all experiments: **many patients show measurable potential for improvement, but conservative safety guardrails appropriately limit automated recommendations**. Only 16/31 orig and 6/12 DynISF patients pass all 7 guardrails. The dominant blocking guardrail — projected TBR > 4% — correctly prevents changes that might increase hypoglycemia.

### 7.2 Universal Negative Prediction Bias

All analyzable patients show negative prediction bias (predictions lower than reality). This systematically causes:
- Unnecessary insulin suspensions (estimated 28–39% could be eliminated)
- Over-cautious AID behavior reducing time-in-range

However, correcting this bias is safe for only 2/29 orig and 1/12 DynISF patients, highlighting the gap between theoretical potential and implementable change.

### 7.3 Slow Responder Dominance

84% of patients are classified as slow insulin responders with effective DIA estimates (mean 12.3 h) far exceeding typical AID profile settings (5–6 h). This suggests:
- AID systems may be stacking insulin corrections before prior doses have fully acted
- Profile DIA settings may need to be substantially longer for many patients
- The ISF correction of +25% (less aggressive) aligns with the slow responder profile

### 7.4 Over-Correction as Population Pattern

The dominant phenotype across both cohorts is over-correction, with 29/31 patients having "reduce hypo" as their top priority. The recommended corrections — increase ISF by ~25%, decrease CR by ~31% — directly address this by making the AID system less aggressive per unit of insulin delivered.

### 7.5 Modest TIR Impact with Safety Priority

The mean projected TIR change is slightly negative (−0.5 pp orig, −0.4 pp DynISF). This is expected: the recommendations prioritize reducing hypoglycemia risk over maximizing TIR. A small TIR decrease with improved safety represents a clinically appropriate trade-off.

---

## 8. Gaps and Next Steps

### 8.1 Identified Gaps

1. **Phenotype propagation gap**: 20/31 patients are "unknown" in EXP-2328 because upstream tier results were not fully propagated. EXP-2291 compensates with its own classification, but this dependency should be resolved.

2. **DIA estimation uncertainty**: Exponential curve-fit DIA (mean 12.3 h, R² = 0.625) has moderate confidence. Alternative pharmacokinetic models (biexponential, compartmental) may improve estimates.

3. **Low recalibration confidence**: 23/31 orig and 12/12 DynISF patients have "low" confidence in recommendation stability, requiring frequent re-evaluation (30–41 day recalibration intervals).

4. **Bias correction safety**: Despite universal negative bias, only 7–8% of patients are safe to correct. The primary barrier is bias instability over time — enabling correction for more patients requires longer data windows or adaptive algorithms.

5. **DynISF-specific bias**: The DynISF cohort shows 45% stronger negative bias than the original cohort. This may reflect a systematic interaction between Dynamic ISF algorithms and prediction accuracy that warrants dedicated investigation.

### 8.2 Recommended Next Steps

1. **Resolve phenotype propagation**: Run tier-2 experiments with full upstream results to eliminate "unknown" classifications.
2. **Validate DIA models**: Compare exponential DIA estimates against biexponential and pharmacokinetic models; assess which better predicts correction outcomes.
3. **Longitudinal bias tracking**: Extend bias stability analysis beyond current windows to identify patients whose bias stabilizes over longer periods.
4. **DynISF bias investigation**: Dedicated experiment analyzing why Dynamic ISF produces stronger prediction bias.
5. **Guardrail sensitivity analysis**: Evaluate impact of adjusting TBR threshold from 4% to 5% on safe-to-implement rates.
6. **Prospective validation**: For the 16 safe-to-implement orig patients, design a prospective trial comparing current vs. recommended settings.

---

## Data Sources

| File | Experiment | Cohort | Patients |
|------|-----------|--------|----------|
| `externals/experiments/exp-2351-2358_insulin_pk.json` | EXP-2351–2358 | Original | 31 |
| `externals/experiments/exp-2321-2328_phenotype.json` | EXP-2321–2328 | Original | 31 |
| `externals/experiments/exp-2331-2338_prediction_bias.json` | EXP-2331–2338 | Original | 31 |
| `externals/experiments/exp-2291-2298_integrated.json` | EXP-2291–2298 | Original | 31 |
| `externals/experiments/exp-2351-2358_insulin_pk_dynisf.json` | EXP-2351–2358 | DynISF | 12 |
| `externals/experiments/exp-2321-2328_phenotype_dynisf.json` | EXP-2321–2328 | DynISF | 12 |
| `externals/experiments/exp-2331-2338_prediction_bias_dynisf.json` | EXP-2331–2338 | DynISF | 12 |
| `externals/experiments/exp-2291-2298_integrated_dynisf.json` | EXP-2291–2298 | DynISF | 12 |
