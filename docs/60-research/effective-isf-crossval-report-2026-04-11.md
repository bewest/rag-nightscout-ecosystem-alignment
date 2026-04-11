# Effective ISF Cross-Validation Report

**Experiments**: EXP-2501–2508
**Date**: 2026-04-11
**Data**: 19 patients (11 NS + 8 ODC), 803K rows
**Status**: AI-generated draft — requires clinical review

## Executive Summary

Two independent methods for estimating effective ISF (Insulin Sensitivity Factor)
give dramatically different results: **1.22× (loop suspension model)** vs
**4.26× (response-curve fitting)**. Cross-validation reveals that:

1. Loop suspension explains only **1.33× of the 4.26× total discrepancy** — profile ISF is fundamentally wrong for most patients, not merely confounded
2. ISF is **non-linear**: 15/16 patients show diminishing returns with larger doses (r = -0.3 to -0.7)
3. ISF is **temporally unstable**: 13/15 patients show CV > 60% over time
4. The two methods don't even **rank patients the same way** (ρ = -0.036)

**Clinical implication**: ISF is not a single number. It depends on dose size,
time of day, recent insulin exposure, and physiological state. Conservative
10-20% adjustments are safer than the full response-curve correction.

## Background

### Two Methods for Estimating Effective ISF

| Method | Source | Approach | Mean Ratio |
|--------|--------|----------|------------|
| Loop suspension | EXP-2387 | ISF_eff = ISF / (1 - 0.3 × susp%) | 1.22× |
| Response-curve | EXP-1301 | BG(t) = BG₀ - A(1-e^(-t/τ)), ISF = A/dose | 4.26× |

The 3.5× discrepancy between these methods motivated this cross-validation.

## Key Findings

### EXP-2501: Methods Are Uncorrelated

| Metric | Value |
|--------|-------|
| Pearson r | -0.128 |
| Spearman ρ | -0.036 (p=0.92) |
| Mean discrepancy | 3.05× |

The two methods **do not agree** on which patients have the largest ISF
mismatch. This means they are measuring fundamentally different things:

- **Loop suspension model**: measures a single confound (basal suspension)
- **Response-curve model**: measures the complete glucose response, which
  includes suspension + time-varying sensitivity + counter-regulatory + dose saturation

### EXP-2502: Decomposition Reveals Profile ISF Is Wrong

The response-curve ratio decomposes multiplicatively:

```
Total ratio (4.47×) = Suspension component (1.33×) × Residual component (3.36×)
```

The **residual component** (3.36×) represents ISF error that is NOT explained
by loop suspension. This means:

| Patient | Total | Suspension | Residual | Interpretation |
|---------|-------|-----------|----------|----------------|
| f | 1.14× | 1.16× | 0.98× | Suspension explains everything |
| j | 1.22× | 1.00× | 1.22× | No suspension; mild ISF error |
| a | 2.29× | 1.15× | 1.99× | ISF ~2× too low |
| g | 6.52× | 1.30× | 5.02× | ISF ~5× too low |
| odc-84181797 | 8.39× | 1.32× | 6.35× | ISF ~6× too low |

For most patients, **the profile ISF is fundamentally wrong**, not merely
confounded by loop behavior. The AID loop masks this by aggressively
modulating basal rates.

### EXP-2504: Loop Suspends 62% During Corrections

| Metric | Value |
|--------|-------|
| Population mean suspension | 61.9% |
| Range | 0% (patient j) to 97.5% (odc-58680324) |
| Dose-suspension correlation | Near zero (mean r ≈ 0.06) |

The loop **does not scale its response** with correction dose — it applies
a similar suspension pattern regardless of whether the correction is 0.5U
or 3U. This makes the suspension-based ISF correction a fixed factor
rather than a dose-dependent adjustment.

### EXP-2506: ISF Is Non-Linear (Major Finding)

**15 of 16 patients show non-linear dose-response** (|r| > 0.3):

| Pattern | Count | Explanation |
|---------|-------|-------------|
| Negative correlation | 15/16 | Larger dose → smaller ISF |
| Linear | 1/16 | ISF constant across doses |

All correlations are **negative**: larger correction boluses produce
**less glucose drop per unit** than smaller ones. This is consistent with:

1. **Insulin receptor saturation** at higher concentrations
2. **Counter-regulatory response** activation at lower glucose
3. **Loop compensation** — larger corrections trigger more aggressive
   basal suspension, absorbing part of the correction

**Implication**: ISF is not a constant. The clinical concept of "50 mg/dL
per Unit" breaks down because it depends on the dose being given. A 3U
correction may achieve 35 mg/dL/U while a 0.5U correction achieves
60 mg/dL/U. This is a fundamental challenge for AID algorithms that
assume linear insulin-glucose relationship.

### EXP-2505: Circadian ISF Variation

| Period | Mean ISF (mg/dL/U) | n Patients |
|--------|-------------------|------------|
| Overnight (00-06) | 239.5 ± 120.3 | 14 |
| Evening (18-24) | 224.0 ± 103.9 | 16 |
| Morning (06-12) | 204.5 ± 94.1 | 14 |
| Afternoon (12-18) | 197.0 ± 85.8 | 16 |

Insulin is ~22% more effective in the afternoon than overnight, consistent
with known cortisol and growth hormone rhythms. This validates the circadian
ISF 2-zone approach (EXP-2271) and the clinical practice of adjusting ISF
by time of day.

### EXP-2507: ISF Is Temporally Unstable

| Metric | Value |
|--------|-------|
| Stable patients | 2/15 (13%) |
| Median CV | 71% |
| Drift range | -41% to +90% |

ISF changes substantially over the data collection period. This instability
reflects:
- Changing insulin sensitivity (exercise, illness, stress)
- Seasonal variation
- Weight changes
- Medication adjustments

**Implication**: Any ISF recommendation has a short shelf life. Settings
should be re-evaluated frequently rather than treated as stable parameters.

## Reconciled ISF Recommendation Strategy

Given these findings, we recommend:

### 1. Use Conservative Adjustment (10-20%)
The loop-suspension model (1.22×) is the only component we can directly
measure and attribute. Use this as the conservative recommendation.

### 2. Do NOT Use Full Response-Curve ISF
The 4.26× ratio includes unmeasured confounds (dose saturation,
counter-regulatory, temporal instability) that would be dangerous to
apply directly to pump settings.

### 3. Acknowledge Non-Linearity
ISF is dose-dependent. Consider separate ISF for small corrections
(<1U) vs large corrections (>2U), or cap the correction bolus size
and rely on the loop for the remainder.

### 4. Re-Evaluate Frequently
With CV > 60% over time, ISF recommendations expire quickly. Monthly
re-evaluation is the minimum; weekly is preferable with sufficient data.

### 5. Trust the Loop's Judgment
The AID loop effectively compensates for ISF errors (AID Compensation
Theorem, EXP-2291). Rather than changing the ISF dramatically, reduce
loop workload by making smaller, conservative adjustments.

## Visualizations

| Figure | Description |
|--------|-------------|
| `fig1_method_comparison.png` | Scatter: response-curve vs loop-suspension ratio |
| `fig2_isf_decomposition.png` | Bar: total vs suspension vs residual by patient |
| `fig3_correction_suspension.png` | Bar: loop suspension % during corrections |

## Source Files

- Experiment: `tools/cgmencode/production/exp_effective_isf.py`
- Prior results: `externals/experiments/exp-1301_therapy.json` (response-curve)
- Prior results: `externals/experiments/exp-2381-2388_settings_simulation.json` (suspension)
- Results: `externals/experiments/exp-2501-2508_effective_isf_crossval.json`
- Figures: `visualizations/effective-isf/fig{1,2,3}_*.png`

## Open Questions

1. **Is the non-linear dose-response driven by insulin kinetics or glucose
   dynamics?** Insulin stacking at higher doses could produce pharmacokinetic
   saturation, while glucose-dependent counter-regulation is a glucodynamic
   effect. These have different clinical implications.

2. **Can we build a dose-dependent ISF model?** Rather than a single ISF,
   model ISF(dose) = ISF_base × dose^(-β) where β captures the saturation
   exponent. This would allow more accurate correction dose calculations.

3. **Does ISF instability correlate with glycemic variability?** If patients
   with high ISF CV also have high glucose CV, the instability may be
   partially predictable from CGM data alone.
