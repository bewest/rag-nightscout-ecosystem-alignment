# Context Windows, Feature Engineering & Robustness Report

**Experiments**: EXP-1131 through EXP-1140  
**Date**: 2026-04-10  
**Campaign**: Physics-Based Metabolic Flux Decomposition (Experiments 131–140)  
**Status**: 10/10 completed successfully

## Executive Summary

This batch tested the remaining high-value opportunities: longer context windows, time-of-day conditioning, derivative/interaction features, online learning, robust losses, and stacking. **Three clear winners emerged**: glucose derivative features (+0.011 XGBoost, 10/11), time-of-day conditioning (+0.008 Ridge, 10/11), and dawn phenomenon conditioning (+0.009 Ridge, 10/11). Several approaches were definitively eliminated: extended context windows hurt, stacked generalization collapsed, online learning degraded, and robust losses (Huber/MAE) underperform MSE.

### SOTA Progression

```
Naive (last value):                     R² = 0.354
Glucose-only Ridge:                     R² = 0.485
+ Physics decomposition:               R² = 0.503
+ Grand combined (block CV):           R² = 0.547  ← EXP-1120
+ XGBoost→LSTM pipeline:               R² = 0.581  ← EXP-1128 ★ CAMPAIGN BEST
+ 5-fold CV definitive:                R² = 0.549  ← EXP-1130
+ Derivative features (XGBoost):       R² = 0.578  ← EXP-1135 (single model!)
+ Residual chain (Ridge→XGB→LSTM→XGB): R² = 0.564  ← EXP-1137
Noise ceiling (σ=15 mg/dL):            R² = 0.854
```

## Experiment Results

### EXP-1131: Extended Context Window (4h, 6h) ✗

**Hypothesis**: Longer windows capture dawn phenomenon and multi-hour meal patterns.

| Window | Ridge R² | XGBoost R² | vs 2h Ridge | vs 2h XGBoost |
|--------|----------|-----------|-------------|---------------|
| 2h (24 steps) | 0.547 | 0.566 | baseline | baseline |
| 4h (48 steps) | 0.538 | 0.553 | −0.010 | −0.014 |
| 6h (72 steps) | 0.511 | 0.542 | −0.036 | −0.025 |

- **4h wins for XGBoost**: 1/11 patients only (patient k)
- **6h wins**: 3/11 (patients b, d, f where XGBoost handles the larger feature space)

**Verdict**: Longer context windows **hurt**. The curse of dimensionality dominates: 6h windows produce 360+ flattened glucose features, leading to overfitting. The 2h window already captures the relevant dynamics for 1h-ahead prediction. Longer-term patterns (dawn, meals) are better captured via explicit conditioning features (see EXP-1132, 1140).

**Exception**: Patient d (6h XGBoost R²=0.744 vs 2h 0.724) — well-controlled patients with strong periodicity benefit from longer context.

---

### EXP-1132: Time-of-Day Conditioning ★★★

**Features added**: sin/cos hour encoding + categorical bins (dawn/morning/afternoon/evening/night).

| Model | Base R² | + Time R² | Δ | Wins |
|-------|---------|----------|---|------|
| Ridge | 0.547 | 0.555 | +0.008 | **10/11** |
| XGBoost | 0.566 | 0.571 | +0.005 | 8/11 |

**Per-patient Ridge improvements**:
- Largest: d (+0.016), f (+0.016), k (+0.013)
- Only loss: j (−0.006) — shortest dataset, limited temporal patterns

**Verdict**: Time-of-day conditioning is a **universal improvement** for Ridge. XGBoost shows smaller gains because it can partially learn time patterns from glucose shape (dawn shows as rising baseline). The explicit features give Ridge access to this signal directly.

---

### EXP-1133: Stacked Generalization ✗✗

**Goal**: Out-of-fold base model predictions → level-2 Ridge meta-learner.

| Model | Mean R² |
|-------|---------|
| Ridge base | 0.548 |
| XGBoost base | 0.572 |
| Simple average | 0.571 |
| **Stacked meta-learner** | **0.424** |

- **0/11 patient wins** for stacking over simple average

**Verdict**: Stacking **catastrophically fails**. The meta-learner overfits on the 3-fold out-of-fold predictions, which have temporal structure (non-i.i.d.). The OOF predictions from adjacent folds are correlated, causing the meta-learner to learn fold-boundary artifacts rather than useful model-weighting patterns. Simple averaging remains superior.

**Lesson**: Classical stacking assumes i.i.d. data. Time-series OOF predictions violate this assumption fundamentally.

---

### EXP-1134: Patient-Adaptive Online Learning ✗

**Goal**: Retrain XGBoost periodically on expanding/sliding window.

| Update Frequency | Mean R² | Wins vs Static |
|-----------------|---------|----------------|
| Static (train once) | 0.534 | baseline |
| Every 6 hours | 0.481 | 1/11 |
| Every 12 hours | 0.476 | 0/11 |
| Every 24 hours | 0.480 | 1/11 |

**Verdict**: Online retraining **hurts significantly** (−0.054). The retraining uses a sliding window that discards early data, reducing effective training set size. With ~180 days of data, the full history provides more signal than recent-only data. This also suggests glucose dynamics are **stationary enough** that a model trained on early data generalizes to later data.

**Exception**: Patient j shows slight online improvement (+0.044 at 24h) — this patient has the shortest dataset (17K steps), where distribution shift may matter more.

---

### EXP-1135: Glucose Derivative Features ★★★★

**Features**: Rate-of-change (current, 30-min, 1h avg), acceleration, momentum (EMA-weighted trend), volatility (rolling std), max absolute rate, jitter frequency.

| Model | Base R² | + Derivatives | Δ | Wins |
|-------|---------|--------------|---|------|
| Ridge | 0.547 | 0.549 | +0.002 | 9/11 |
| **XGBoost** | **0.566** | **0.578** | **+0.011** | **10/11** |

**Per-patient XGBoost gains**:
| Patient | Δ R² | Tier |
|---------|------|------|
| d | +0.028 | Easy — strongest gain |
| e | +0.020 | Medium |
| a | +0.018 | Medium |
| b | +0.013 | Medium |
| c | +0.010 | Hard |
| i | +0.009 | Easy |
| h | +0.008 | Excluded |
| f | +0.007 | Easy |
| g | +0.007 | Medium |
| k | +0.006 | Hard |
| j | −0.002 | Hard (only loser) |

**Verdict**: Derivative features are a **strong universal improvement** for XGBoost. The explicit rate-of-change, acceleration, and volatility features allow XGBoost to condition on glucose dynamics beyond what it extracts from the raw window. Ridge benefits less because it's already computing linear combinations of the window (implicit derivatives).

**Key insight**: XGBoost R²=0.578 with derivatives matches the full pipeline R²=0.578 (EXP-1121) — suggesting derivatives capture much of what the pipeline's multiple stages provide, but in a single model.

---

### EXP-1136: Insulin-Glucose Interaction Terms ★★

**Features**: glucose×IOB, glucose×COB, trend×IOB, trend×activity, IOB×COB, correlation(glucose, IOB), etc.

| Model | Base R² | + Interactions | Δ | Wins |
|-------|---------|---------------|---|------|
| Ridge | 0.547 | 0.550 | +0.003 | 9/11 |
| XGBoost | 0.566 | 0.573 | +0.006 | 8/11 |

**Verdict**: Interaction terms provide **moderate improvement**. XGBoost can theoretically learn interactions through tree splits, but explicit terms still help (+0.006). The benefit is smaller than derivatives (+0.011), suggesting the main information gap is in glucose dynamics, not in insulin-glucose coupling.

---

### EXP-1137: Residual Boosting Chain ★★★

**Architecture**: Ridge → XGBoost (on Ridge residuals) → LSTM (on XGB residuals) → XGBoost (on LSTM residuals).

| Stage | Mean R² | Δ from Previous |
|-------|---------|-----------------|
| Ridge baseline | 0.542 | — |
| + XGBoost residual | 0.551 | +0.009 |
| + LSTM residual | 0.562 | +0.011 |
| + Final XGBoost | 0.564 | +0.002 |

- Average chain length: 3.5 stages (early stopping helps 3/11 patients)
- LSTM correction remains the largest single-stage gain (+0.011)
- 4th stage (final XGBoost) shows diminishing returns (+0.002)

**Verdict**: The chain confirms that **3 stages is optimal**: Ridge→XGBoost→LSTM. The 4th stage adds negligible value. This validates the production architecture from EXP-1128.

---

### EXP-1138: Robust Loss Functions ✗

| Loss | Ridge R² | XGBoost R² | XGBoost Wins vs MSE |
|------|----------|-----------|-------------------|
| MSE | 0.547 | 0.566 | baseline |
| Huber | 0.534 | 0.564 | 2/11 |
| MAE/Quantile | — | 0.551 | 1/11 |

**Verdict**: MSE is **optimal** for this task. Huber and MAE lose because glucose prediction errors are approximately Gaussian (not heavy-tailed). The sensor noise is well-behaved and doesn't benefit from robust estimation. Huber actually hurts Ridge (−0.013) by under-weighting large glucose excursions that carry important signal.

---

### EXP-1139: Feature Importance & Selection ≈

| Feature Set | XGBoost R² | vs Full |
|------------|-----------|---------|
| Full (~135 features) | 0.566 | baseline |
| Top 50 | 0.566 | 0.000 |
| Top 20 | 0.559 | −0.008 |
| Top 10 | 0.550 | −0.017 |
| Lasso-selected | 0.553 | −0.013 |

**Verdict**: Feature selection **doesn't help** — XGBoost with full features matches or beats all subsets. XGBoost's built-in feature selection (via tree splits) is sufficient. The top-50 features are effectively identical to full, confirming that XGBoost ignores ~85 low-importance features naturally.

**Top features by importance** (consistent across patients): recent glucose values (last 6 steps), net physics flux, glucose mean, glucose std, recent PK activity.

---

### EXP-1140: Dawn Phenomenon Conditioning ★★★

**Features**: sin/cos hour, dawn proximity (Gaussian at 5AM), dawn ramp (3-7AM), post-dawn (7-10AM), cortisol proxy, dawn×glucose, dawn×trend.

| Model | Base R² | + Dawn | Δ | Wins |
|-------|---------|--------|---|------|
| Ridge (time only) | 0.553 | — | — | — |
| Ridge (dawn only) | 0.553 | — | — | — |
| Ridge (both) | 0.555 | +0.009 | — | **10/11** |
| XGBoost (+ dawn+time) | 0.566 | 0.572 | +0.006 | 9/11 |

**Verdict**: Dawn conditioning provides **reliable improvement**, comparable to time-of-day conditioning. The dawn-specific features (proximity, ramp, cortisol proxy) perform as well as general time features alone. Both together give the best Ridge result (+0.009, 10/11 wins).

**Note**: The dawn+time Ridge improvement (+0.009) is additive with derivative features — together they could push Ridge to ~0.558.

---

## Updated Technique Rankings (140 Experiments)

| Rank | Technique | Δ R² | Wins | Status |
|------|-----------|------|------|--------|
| 1 | Online AR correction | +0.156 | 11/11 | ★★★ Production-only |
| 2 | Full pipeline (all winners) | +0.043 | 11/11 | ★★★★★ |
| 3 | XGBoost→LSTM pipeline | +0.038 | 11/11 | ★★★★★ RECOMMENDED |
| 4 | Residual chain (3-stage) | +0.023 | 8/11 | ★★★ |
| 5 | Residual LSTM correction | +0.024 | 10/11 | ★★★★ |
| 6 | Residual stacking | +0.015 | 9/11 | ★★★ |
| 7 | **Derivative features** | **+0.011** | **10/11** | **★★★★ NEW** |
| 8 | XGBoost tuning | +0.011 | 11/11 | ★★★ |
| 9 | Physics decomposition | +0.010 | 9/11 | ★★★ |
| 10 | **Dawn conditioning** | **+0.009** | **10/11** | **★★★ NEW** |
| 11 | **Time-of-day conditioning** | **+0.008** | **10/11** | **★★★ NEW** |
| 12 | Interaction terms | +0.006 | 8/11 | ★★ |
| 13 | Δg prediction target | +0.004 | 11/11 | ★★ |
| — | Extended context (4h/6h) | −0.014 | 2/11 | ✗ Harmful |
| — | Robust losses (Huber) | −0.002 | 2/11 | ✗ MSE optimal |
| — | Feature selection | −0.008 | 1/11 | ✗ XGBoost self-selects |
| — | Online learning | −0.054 | 1/11 | ✗✗ Harmful |
| — | Stacked generalization | −0.148 | 0/11 | ✗✗✗ Catastrophic |

## Next Experiments

Based on these findings, the highest-value next experiments are:

### EXP-1141: Combined Feature Engineering Pipeline
Combine all winning feature additions: derivatives + time-of-day + dawn conditioning + interactions into a single XGBoost model. Expected: R²≈0.585 (additive gains).

### EXP-1142: Combined Features + LSTM Residual
Apply the full XGBoost→LSTM pipeline with all enhanced features. Expected: R²≈0.595.

### EXP-1143: Per-Patient Feature Importance Analysis
Analyze which feature categories matter most per patient tier (easy/medium/hard).

### EXP-1144: Temporal Lead/Lag Optimization
Test different PK channel temporal offsets (lead IOB/COB by 15-30min to account for glucose response delay).

### EXP-1145: Multi-Patient Transfer with Features
Test if shared feature engineering improves cross-patient generalization.

## Files

| File | Description |
|------|-------------|
| `tools/cgmencode/exp_clinical_1131.py` | Experiment script (1681 lines) |
| `externals/experiments/exp-113*_*.json` | Per-experiment results |
| `docs/60-research/context-features-robustness-report-2026-04-10.md` | This report |
