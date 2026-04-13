# Algorithm Prediction Quality Validation

**Experiment**: EXP-2581 (sub-experiments: 2581–2584)
**Phase**: Validation (Phase 7)
**Date**: 2026-04-12
**Script**: `exp_repl_2581.py`
**Data provenance**: Post-ODC-fix; tests algorithm-reported predictions vs actual outcomes

## Purpose

Validate the colleague's finding (F5) that oref0's `eventualBG` is a poor predictor
of actual future blood glucose. Extend the analysis to Loop's predictions and to
physics-based PK predictions, providing the first cross-algorithm prediction quality
comparison.

## Comparison Summary

| Finding | Their Claim | Our Result | Agreement |
|---------|------------|------------|-----------|
| F5a | eventualBG R²=0.002 vs 4h BG | eventualBG R²=**−3.197** vs 4h BG | ✅✅ strongly_agrees |
| F5b | — | Loop predicted_60 R²=−0.156 vs 1h BG | ↔️ not_comparable |
| F5c | — | PK net_balance R²=0.045 at 1h | ↔️ novel_finding |

## Key Results

### EXP-2581: eventualBG vs Actual 4h BG (oref0/AAPS patients)

| Patient | R² (4h) | MAE (mg/dL) | n |
|---------|---------|-------------|---|
| Cohort mean | **−3.197** | — | 8 patients |

**Interpretation**: R² = −3.20 means eventualBG is **worse than predicting the mean**.
It doesn't just fail to predict — it actively misleads. This strongly confirms the
colleague's F5 finding (they reported R² = 0.002, which is essentially zero).

Our result is even more extreme (−3.20 vs 0.002), likely because:
- We test on AAPS patients (AAPS uses the same oref algorithm)
- Different R² computation methodology (we use scikit-learn's definition which
  penalizes variance inflation; colleague may have used correlation-based R²)
- Both agree: **eventualBG is not a reliable prediction of future BG**

### EXP-2582: Loop Predictions vs Actual BG

| Metric | Value |
|--------|-------|
| Mean R² (1h) | −0.156 |
| Median R² (1h) | 0.170 |
| Per-patient MAE | 23–47 mg/dL |

**Interpretation**: Loop's 60-minute prediction (`predicted_60`) performs better than
eventualBG but is still poor on average (negative mean R²). The positive median
suggests most patients have marginally useful predictions, but outliers drag the mean
negative. This is not directly comparable to the colleague's work (they didn't study
Loop predictions).

### EXP-2583: PK-Derived Net Balance Predictions

| Horizon | Mean R² | Median R² |
|---------|---------|-----------|
| 1h | 0.045 | 0.039 |
| 2h | 0.037 | 0.031 |
| 4h | 0.031 | 0.027 |

**Interpretation**: Physics-based PK predictions (insulin net balance) show slight
positive R² at all horizons, meaning they weakly predict BG direction. However,
R² < 0.05 means they explain less than 5% of variance. This is expected — glucose
dynamics involve many factors beyond insulin (meals, exercise, stress, dawn phenomenon).

### EXP-2584: Cross-Comparison Summary

| Prediction Source | Best Horizon | R² | Status |
|------------------|-------------|-----|--------|
| eventualBG (oref) | 4h | −3.20 | ❌ Worse than mean |
| Loop predicted_60 | 1h | −0.16 / 0.17 | ⚠️ Marginal |
| PK net_balance | 1h | 0.045 | ⚠️ Weak positive |

**Key insight**: None of the single-point prediction approaches work well for glucose
forecasting. This validates the colleague's argument that feature importance (what the
model learns from history) is more informative than algorithm predictions (what the
algorithm says will happen).

## Implications for OREF-INV-003 Replication

### Strongly Confirms F5

The colleague argued that eventualBG should not be trusted as a direct prediction,
and that settings optimization should rely on historical pattern analysis (SHAP)
rather than algorithm-predicted outcomes. Our R² = −3.20 provides even stronger
evidence for this claim.

### Extends Beyond F5

We show that this is not unique to oref0 — Loop predictions also underperform.
The fundamental issue is that **AID predictions are dosing decisions, not forecasts**.
They are optimized to decide insulin delivery, not to accurately predict future BG.

### Supports PK Augmentation Strategy

The weak but positive PK net_balance R² (0.045) shows that physics-based features
capture real physiological signal, even if insufficient alone. When used as input
features to LightGBM (EXP-2531), they improve AUC by +0.012 and ρ by +0.057,
demonstrating that the value is in the feature representation, not point prediction.

## Methodology

- **eventualBG source**: `sug_eventualBG` from ns2parquet grid (oref0/AAPS records)
- **Loop prediction source**: `loop_predicted_60` through `loop_predicted_360`
- **PK prediction**: `pk_net_balance` from `pk_bridge.py`
- **R² computation**: scikit-learn `r2_score(y_true, y_pred)` — penalizes variance
- **Horizons**: 1h, 2h, 4h actual future BG from entries
- **Patients**: 8 AAPS/oref0 for eventualBG; 11 Loop for predicted_60

## Limitations

1. **Horizon mismatch**: eventualBG has no fixed horizon (it's "eventually"); we test at
   4h which is the colleague's convention
2. **R² definition**: Our negative R² uses variance-penalizing definition vs possible
   correlation-based R² in the colleague's work
3. **No Loop eventualBG**: Loop doesn't report eventualBG, so cross-algorithm comparison
   is across different prediction types
4. **AID interference**: All predictions are made while the AID is actively adjusting
   delivery, creating a feedback loop that degrades linear prediction quality

## Relationship to Other Experiments

- **Validates**: Colleague's F5 finding (eventualBG is unreliable)
- **Supports**: EXP-2531/2541 strategy of using PK features rather than algorithm
  predictions as model inputs
- **Contrasts with**: EXP-2511 which showed PK features improve LightGBM despite
  weak standalone prediction R²
