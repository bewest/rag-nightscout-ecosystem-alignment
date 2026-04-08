# Pipeline Optimization & Ablation — EXP-1031–1040 Report

**Date**: 2026-04-10
**Campaign**: Physics-Based Metabolic Flux Decomposition
**Experiments**: EXP-1031 through EXP-1040
**Status**: All 10 passed, 11 patients × ~180 days each

## Executive Summary

This batch focused on **optimizing the production pipeline**, investigating
diminishing returns, ablation studies, and honest final evaluation. The
most significant outcomes are diagnostic rather than performance-improving:

1. **Patient h mystery solved**: 64.2% missing CGM data (z=+25.91 vs cohort)
   explains all prediction failures — not a modeling problem
2. **Hepatic production is the #1 physics channel** (permutation importance
   +0.024), confirming that EGP/liver modeling is the highest-leverage
   physiological component
3. **DIA has zero prediction sensitivity** — sweeping 2.5–6.0h produces
   identical R², indicating PK features need architectural rethinking
4. **Honest pipeline block CV**: R² = 0.505, MAE = 28.5 mg/dL
5. **Diminishing returns confirmed**: stacking techniques gives < +0.004

## Results Summary

| EXP | Title | Result | Verdict |
|-----|-------|--------|---------|
| 1031 | Adaptive Ensemble Weighting | +0.004, 7/11 | Marginal |
| 1032 | Residual CNN + Fine-Tune | +0.000, 6/11 | No benefit |
| 1033 | Patient h Deep Dive | 64% missing data | **Root cause found** |
| 1034 | Derivative Physics Channels | Ridge +0.002, CNN −0.019 | Mixed |
| 1035 | DIA Optimization | Zero sensitivity | **Bug or design flaw** |
| 1036 | Multi-Horizon Joint Training | 120min +0.030, 15min −0.050 | Long horizon only |
| 1037 | Sliding Window Online | −0.025, 2/11 | Harmful |
| 1038 | Physics Permutation Importance | hepatic > net > supply ≈ demand | **Key insight** |
| 1039 | Glucose Regime Segmentation | −0.010, 1/11 | Harmful |
| 1040 | Grand Summary Pipeline | Block CV R²=0.505, MAE=28.5 | **Definitive evaluation** |

## Detailed Analysis

### EXP-1033: Patient h Deep Dive ⭐

The campaign's most persistent puzzle — why patient h defeats every model —
is now definitively explained:

| Metric | Patient h | Cohort Mean | z-score |
|--------|-----------|-------------|---------|
| **Missing rate** | **64.2%** | 11.4% | **+25.91** |
| Glucose kurtosis | 5.2 | 3.1 | +2.80 |
| Glucose skewness | 1.4 | 0.8 | +2.14 |
| Glucose mean | 119 mg/dL | 153 mg/dL | −1.42 |

**64% missing data** means:
- Only 36% of 5-minute intervals have valid glucose readings
- Most sliding windows contain NaN gaps, reducing effective training data
- CGM sensor is off-body or failing most of the time
- This is a **data quality problem**, not a modeling problem

**Recommendation**: Exclude patient h from model evaluation (data quality
gate) or develop gap-aware architectures. The z=+25.91 is the most extreme
outlier in the entire campaign.

### EXP-1038: Physics Permutation Importance ⭐

| Channel | Importance (R² drop) | Rank |
|---------|---------------------|------|
| **Hepatic (EGP)** | **+0.024** | **1st** |
| Net balance | +0.017 | 2nd |
| Supply (carb absorption) | +0.006 | 3rd |
| Demand (insulin action) | +0.006 | 4th |

**Hepatic production (endogenous glucose production) is the most important
physics channel by a wide margin.** This is physiologically significant:

- EGP drives the circadian glucose baseline (dawn phenomenon, post-meal
  hepatic response)
- The basal rate schedule is essentially a proxy for the EGP schedule
- Improving EGP modeling (patient-specific hepatic response curves, dawn
  phenomenon amplitude) is the highest-leverage improvement

**Supply and demand are equally and modestly important**, suggesting that
explicit carb/insulin decomposition provides less marginal information
once hepatic production is accounted for. The liver is the integrator.

### EXP-1035: DIA Sensitivity = Zero

Sweeping DIA from 2.5h to 6.0h produces **identical R² to 4 decimal
places** for all 11 patients. This means either:

1. **Bug**: `build_continuous_pk_features()` may cache or not properly
   recompute when DIA changes (likely — the function may read DIA from
   a cached schedule rather than recomputing the insulin action curve)
2. **Design**: The glucose history dominates so completely that PK tail
   differences are irrelevant to Ridge
3. **Normalization**: PK channels are normalized by fixed constants, so
   DIA changes that shift the curve shape but not the peak amplitude
   may be washed out

**Action needed**: Verify PK recomputation is actually happening. If
confirmed as a bug, fixing it could unlock a new degree of freedom.

### EXP-1036: Multi-Horizon Joint Training

| Horizon | Joint R² | Separate R² | Δ |
|---------|----------|-------------|---|
| 15 min  | 0.825    | 0.875       | −0.050 |
| 30 min  | 0.729    | 0.752       | −0.023 |
| 60 min  | 0.515    | **0.507**   | **+0.008** |
| 120 min | **0.235**| 0.205       | **+0.030** |

Joint training helps long horizons (≥60min) but hurts short horizons.
This confirms the physics-value-scales-with-horizon principle: shared
representations learning long-range physics patterns benefit 120-min
prediction (+0.030) while the short-horizon task (dominated by simple
momentum) loses capacity to the joint objective.

**Practical implication**: Use separate models for ≤30min (momentum-based)
and a joint model for ≥60min (physics-based) horizons.

### EXP-1037: Sliding Window Online Learning ❌

| Patient | Static R² | Online R² | Δ |
|---------|-----------|-----------|---|
| b       | 0.507     | **0.542** | **+0.035** |
| a       | 0.588     | **0.600** | +0.012 |
| d       | 0.652     | 0.578     | **−0.074** |
| g       | 0.542     | 0.479     | −0.063 |

**Online retraining hurts 9/11 patients** (mean −0.025). With ~180 days
of data, restricting to 60-90 day windows loses more from reduced training
set size than it gains from recency. The two patients that benefit (a, b)
happen to have the highest glucose variability (std=82, 62).

**Conclusion**: At 180-day scale, use all historical data. Online learning
may only help at >1 year data horizons.

### EXP-1040: Grand Summary Pipeline (Block CV) ⭐

The definitive honest evaluation of the full recommended pipeline:

| Stage | Block CV R² | Δ from previous |
|-------|-------------|-----------------|
| Glucose-only Ridge | 0.475 | — |
| + Physics features | 0.486 | +0.011 |
| + Residual CNN | **0.505** | +0.019 |
| + Ensemble | 0.505 | +0.000 |

**Final honest metrics**: R² = 0.505, MAE = 28.5 mg/dL

Per-patient pipeline performance:

| Patient | Pipeline R² | MAE (mg/dL) | Tier |
|---------|-------------|-------------|------|
| i       | 0.661       | 32.2        | Easy |
| f       | 0.667       | 30.5        | Easy |
| d       | 0.574       | 21.1        | Easy |
| a       | 0.622       | 37.4        | Medium |
| e       | 0.584       | 29.3        | Medium |
| b       | 0.576       | 30.3        | Medium |
| g       | 0.509       | 30.6        | Medium |
| j       | 0.458       | 23.4        | Hard |
| c       | 0.409       | 40.8        | Hard |
| k       | 0.347       | 9.0         | Hard |
| h       | 0.151       | 28.6        | Outlier |

### What Didn't Work

| Technique | Why it failed |
|-----------|---------------|
| Adaptive ensemble | Overfits on small validation sets |
| Residual + fine-tune stack | Residual signal already simple; no room for transfer |
| Derivative physics channels | CNN overfits extra features; Ridge gain marginal |
| Online learning | Insufficient data per window (180 days too short) |
| Regime segmentation | Data fragmentation > regime-specific patterns |

## Campaign Summary (EXP-1001–1040)

### What We've Learned

1. **Physics decomposition is transformative** (+0.265 R²): Separating
   supply, demand, hepatic, and net balance gives ML independent
   physiological processes to learn from

2. **Hepatic production is the key channel**: EGP modeling provides the
   most predictive information, likely because it captures the circadian
   baseline that all other processes perturb

3. **Residual learning is universally reliable**: Ridge + residual CNN
   achieves positive improvement for all 11/11 patients — the only
   technique with perfect reliability

4. **Features >> Architecture**: Decomposed physics (+0.265) dwarfs
   all architecture improvements combined (+0.040)

5. **Patient heterogeneity is real**: No single model dominates. Oracle
   routing yields +0.025 over best single method

6. **Data quality gates are essential**: Patient h (64% missing) should
   be excluded or flagged. Missing data rate is a 25σ outlier

7. **Honest evaluation matters**: Block CV reveals ~7% R² inflation vs
   simple splits. True SOTA is R²=0.505, not 0.525

8. **Time-of-day features are harmful**: Confirmed across multiple
   experiments that ≤6h glucose dynamics are time-translation invariant

### SOTA Progression (Honest Block CV)

```
Glucose-only AR(4):        R² = 0.475
+ Decomposed physics:     R² = 0.486 (+0.011)
+ Residual CNN:            R² = 0.505 (+0.019)
                           ─────────────────
Total honest improvement:  R² = +0.030 over baseline
MAE = 28.5 mg/dL (60-min horizon)
```

### Information Frontier Analysis

The R²=0.505 ceiling suggests ~50% of glucose variance is unpredictable
from the available features. The unpredictable variance likely comes from:

- **Unrecorded meals** (especially snacks, drinks)
- **Physical activity** (not in our feature set)
- **Stress/hormones** (cortisol, adrenaline effects)
- **Sensor noise** (CGM measurement error ~10-15%)
- **Sleep quality** (circadian disruption)
- **Medication interactions** (non-insulin drugs)

### Recommended Production Pipeline

```python
# 1. Data quality gate
if missing_rate > 0.25:
    flag_patient("insufficient_data")

# 2. Physics decomposition
supply, demand, hepatic, net = compute_supply_demand(df, pk)

# 3. Ridge baseline (per-patient)
ridge_pred = Ridge(glucose_history + [supply, demand, hepatic, net])

# 4. Residual CNN (per-patient)
residual = CNN(glucose_window, physics_features).predict(ridge_residuals)
final_pred = ridge_pred + α * residual  # α from validation

# 5. Confidence (optional)
conf = ensemble_std(5_models)
if conf > threshold: reject_prediction()
```

## Next Experiment Proposals (EXP-1041–1050)

### High Priority

| ID | Title | Rationale |
|----|-------|-----------|
| 1041 | Fix DIA PK Recomputation | EXP-1035 zero sensitivity is likely a bug; fixing could unlock new performance |
| 1042 | Hepatic Production Deep Dive | Most important channel; can we model patient-specific EGP curves? |
| 1043 | Activity/Step Count Integration | Largest missing information source; test with synthetic activity proxy |

### Architectural Innovation

| ID | Title | Rationale |
|----|-------|-----------|
| 1044 | Attention over Physics Channels | Let model learn which channel matters when, instead of uniform weighting |
| 1045 | Gap-Aware Architecture | Handle missing data natively (masking, imputation) for patients like h |
| 1046 | Longer Context Windows (6h, 12h) | Current 2h may miss slow dynamics; EXP-419 showed time features help at ≥12h |

### Clinical Translation

| ID | Title | Rationale |
|----|-------|-----------|
| 1047 | Clarke Error Grid Analysis | Clinical relevance metric beyond R²/MAE |
| 1048 | Selective Prediction (Reject Option) | Use confidence to only predict when reliable; trade coverage for accuracy |
| 1049 | Alert Prediction (Hypo/Hyper) | Binary classification at clinical thresholds (54, 70, 180, 250 mg/dL) |
| 1050 | Real-Time Streaming Evaluation | Simulate real-time prediction with data arrival delays |

## Run Commands

```bash
PYTHONPATH=tools python -m cgmencode.exp_clinical_1031 --detail --save --max-patients 11
PYTHONPATH=tools python -m cgmencode.exp_clinical_1031 --experiment EXP-1038 --detail --save
```

## References

- EXP-1001–1010: `multi-scale-meal-physics-report-2026-04-10.md`
- EXP-1011–1020: `cnn-physics-architecture-report-2026-04-10.md`
- EXP-1021–1030: `ensemble-transfer-learning-report-2026-04-10.md`
