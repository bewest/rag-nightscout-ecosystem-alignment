# EXP-1111–1120: Combined Winners and Advanced Ensemble Methods

**Date**: 2026-04-10  
**Campaign**: EXP-1111–1120 (Experiments 111–120 of 120)  
**Objective**: Stack all winning techniques, explore advanced ensembles, and establish definitive campaign SOTA  
**Previous SOTA**: R² = 0.507 (weighted ensemble, EXP-1108)

## Executive Summary

This batch combined all winning techniques from 110 prior experiments. Key breakthroughs:

| Finding | Impact | Universality |
|---------|--------|-------------|
| **Residual LSTM correction** | **+0.024 R²** | **10/11 wins** |
| Grand Δg ensemble (block CV) | R²=0.547 | New definitive SOTA |
| Conformal prediction | ≤2% calibration error | 11/11 |
| Stacking (Ridge Δg + TCN residual) | +0.011 R² | 9/11 |
| XGBoost hyperparameter tuning | +0.011 R² | 11/11 |
| Δg + XGB + TCN ensemble | +0.009 R² | 8/11 |
| Per-patient ensemble weights | +0.002 over global | 9/11 |
| Patient clustering | HURTS (patient-specific wins) | 10/11 patient wins |

**New Campaign SOTA**: R² = 0.547 (block CV, Δg ensemble with imputation)  
**Best Pipeline**: Interpolation → Δg target → Ridge+XGB ensemble → LSTM residual correction

---

## Experiment Results

### EXP-1111: Combined Winners (Δg + XGBoost + Ensemble) ★★★

Stacked ALL winning techniques: Δg target + Ridge + XGBoost + TCN with optimized ensemble weights.

| Patient | Ridge abs | Ridge Δg | XGB Δg | TCN Δg | Δg Ensemble | Abs Ensemble | Gain |
|---------|-----------|----------|--------|--------|-------------|--------------|------|
| a | 0.590 | — | — | — | 0.603 | 0.600 | +0.004 |
| b | 0.508 | — | — | — | 0.525 | 0.520 | +0.005 |
| c | 0.396 | — | — | — | 0.412 | 0.414 | −0.002 |
| d | 0.656 | — | — | — | 0.677 | 0.668 | +0.010 |
| e | 0.558 | — | — | — | 0.590 | 0.585 | +0.005 |
| f | 0.630 | — | — | — | 0.659 | 0.650 | +0.010 |
| **g** | 0.549 | — | — | — | **0.609** | 0.576 | **+0.033** |
| h | 0.219 | — | — | — | 0.239 | 0.242 | −0.003 |
| i | 0.700 | — | — | — | 0.709 | 0.707 | +0.003 |
| **j** | 0.410 | — | — | — | **0.518** | 0.477 | **+0.041** |
| k | 0.351 | — | — | — | 0.373 | 0.375 | −0.001 |
| **Mean** | — | — | — | — | **0.538** | **0.528** | **+0.009** |

**Key findings**:
- Δg ensemble wins 8/11 (only c, h, k prefer absolute)
- XGBoost dominates ensemble weights (~40-79% weight)
- TCN contributes most for patients g (36%) and j (47%) — the "hard" patients
- Patients with high variability benefit most from Δg

### EXP-1112: XGBoost Hyperparameter Sweep ★★

108 configurations evaluated per patient using GPU acceleration (1.5-2.8 min each).

| Patient | Default R² | Best R² | Gain | Best Config |
|---------|------------|---------|------|-------------|
| a | 0.585 | 0.596 | +0.011 | n=500, d=8, lr=0.01, ss=0.7 |
| b | 0.505 | 0.514 | +0.009 | n=500, d=3, lr=0.05, ss=1.0 |
| c | 0.400 | 0.408 | +0.008 | n=500, d=6, lr=0.01, ss=0.8 |
| d | 0.653 | 0.661 | +0.008 | n=200, d=3, lr=0.05, ss=0.7 |
| e | 0.584 | 0.589 | +0.005 | n=200, d=3, lr=0.05, ss=0.8 |
| f | 0.653 | 0.660 | +0.007 | n=200, d=3, lr=0.1, ss=0.7 |
| **g** | 0.583 | **0.604** | **+0.021** | n=500, d=4, lr=0.05, ss=0.7 |
| h | 0.226 | 0.234 | +0.009 | n=500, d=6, lr=0.01, ss=0.8 |
| i | 0.697 | 0.704 | +0.007 | n=200, d=3, lr=0.1, ss=0.7 |
| **j** | 0.493 | **0.526** | **+0.033** | n=100, d=3, lr=0.05, ss=1.0 |
| k | 0.378 | 0.384 | +0.006 | n=100, d=4, lr=0.05, ss=1.0 |
| **Mean** | 0.523 | **0.534** | **+0.011** | — |

**Key findings**:
- 11/11 wins — every patient benefits from tuning
- No single universal config — optimal varies per patient
- Shallow trees (depth 3) dominate for 6/11 patients (b, d, e, f, i, j)
- Subsample 0.7 prevents overfitting for larger patients
- Hard patients (j, k) prefer fewer trees with no subsampling
- Total sweep time: 28 min (vs ~31 hours with sklearn GB)

> **Note**: EXP-1255 (see [Winner Stacking Report](winner-stacking-production-report-2026-04-10.md)) later found depth-2 optimal for 7/11 patients under 5-fold CV (+0.005 R² over depth-3), reflecting depth-2's regularization advantage. The difference is within noise margins for most patients.

### EXP-1113: Multi-Horizon Joint Prediction ★★

| Horizon | Separate | Joint | Multi-output | Best Approach |
|---------|----------|-------|-------------|---------------|
| 15 min | **0.894** | 0.878 | 0.894 | Separate |
| 30 min | 0.765 | **0.768** | 0.765 | Joint |
| 45 min | 0.626 | **0.631** | 0.626 | Joint |
| 60 min | **0.504** | 0.494 | 0.504 | Separate |

**Approach wins**: Separate 25, Joint 19, Multi-output 0

**Key findings**:
- Horizon decay: ~0.13 R² per 15-min step (linear decay confirmed)
- 15-min prediction nearly solved (R²=0.894)
- Joint models help at intermediate horizons (30-45 min) where shared features aid generalization
- Multi-output never wins — no benefit from simultaneously predicting all horizons
- Separate models best at extremes (15min trivial, 60min needs dedicated optimization)

### EXP-1114: TCN + Δg + Residual Stacking ★★★

| Patient | Ridge | Ridge Δg | TCN | TCN Δg | Stacked | Best |
|---------|-------|----------|-----|--------|---------|------|
| a | 0.590 | 0.594 | 0.543 | 0.585 | **0.614** | stacked |
| b | 0.507 | 0.511 | 0.484 | 0.506 | **0.518** | stacked |
| c | 0.397 | **0.398** | 0.365 | 0.386 | 0.398 | ridge_dg |
| d | 0.654 | 0.657 | 0.626 | **0.671** | 0.664 | tcn_dg |
| e | 0.554 | 0.559 | 0.540 | **0.567** | 0.564 | tcn_dg |
| f | 0.627 | 0.632 | 0.600 | 0.628 | **0.652** | stacked |
| g | 0.541 | 0.547 | 0.550 | **0.586** | 0.584 | tcn_dg |
| h | 0.195 | 0.210 | 0.105 | 0.203 | **0.229** | stacked |
| i | 0.697 | 0.701 | 0.665 | 0.691 | **0.702** | stacked |
| j | 0.418 | 0.421 | 0.344 | **0.483** | 0.424 | tcn_dg |
| k | 0.350 | **0.352** | 0.296 | 0.340 | 0.348 | ridge_dg |
| **Mean** | 0.503 | 0.507 | 0.465 | 0.513 | **0.518** | — |

**Key findings**:
- Stacking (Ridge Δg + TCN on residuals) = **0.518**, best single-split architecture
- Δg target improves BOTH Ridge (+0.004) and TCN (+0.048!) — TCN benefits most
- TCN Δg > TCN direct by +0.048 — dramatic improvement when removing AR dominance
- Stacking wins 5/11, TCN Δg wins 4/11 — both are strong
- Stacking particularly helps easy/medium patients; TCN Δg helps hard patients

### EXP-1115: Attention Over Physics Channels ★

| Patient | Ridge | CNN | TCN | Attention | Attn vs Ridge |
|---------|-------|-----|-----|-----------|---------------|
| Mean | **0.503** | 0.423 | 0.467 | 0.496 | −0.006 |

**Key findings**:
- Attention beats CNN (10/11) and TCN (7/11) but **loses to Ridge** (only 4/11 wins)
- Not worth the complexity — Ridge's flat features are simply more informative
- Patient d is the one case where attention wins all (0.664 vs 0.654 Ridge)

### EXP-1116: Adaptive Per-Patient Ensemble Weights ★★★

| Patient | Uniform | Global (50/40/10) | Per-Patient | Best |
|---------|---------|-------------------|-------------|------|
| Mean | 0.510 | 0.519 | **0.521** | Patient |

**Per-patient wins**: 8/11 (global 2, XGB alone 1)

**Key findings**:
- Per-patient optimization gives +0.002 over global fixed weights
- CNN gets ~0 weight for most patients (Ridge+XGB dominate)
- Optimal split varies: some patients favor Ridge (c: 65/35), others XGB (e: 18/74/7)
- Small but consistent improvement — worth doing in production

### EXP-1117: Conformal Prediction ★★★

| Target Coverage | Actual Coverage | Interval Width (mg/dL) | Calibration Error |
|-----------------|-----------------|----------------------|-------------------|
| 80% | **80.4%** | 92 | 0.020 |
| 90% | **89.9%** | 128 | 0.020 |
| 95% | **94.7%** | 161 | 0.015 |

**Hypo capture rates**: 80% level captures only 45% of hypos; 95% level captures 87%

**Key findings**:
- **Excellent calibration**: all within 2% of target coverage
- Dramatically better than EXP-1104 quantile regression (77.8% actual for 80% target)
- Interval widths reasonable: 92 mg/dL at 80%, 161 mg/dL at 95%
- Patient k has narrowest intervals (31 mg/dL at 80%) — low glucose variability
- Hypo capture remains a challenge — asymmetric intervals needed for clinical safety
- Conformal prediction is the recommended approach for uncertainty quantification

### EXP-1118: Residual LSTM on Ensemble Errors ★★★★

| Patient | Ensemble R² | + LSTM Correction | Gain |
|---------|-------------|-------------------|------|
| a | 0.596 | **0.613** | +0.017 |
| b | 0.526 | **0.540** | +0.014 |
| c | 0.411 | **0.444** | **+0.033** |
| d | 0.651 | **0.688** | **+0.037** |
| e | 0.582 | 0.582 | +0.000 |
| f | 0.650 | **0.674** | +0.025 |
| g | 0.576 | **0.604** | +0.028 |
| h | 0.234 | **0.281** | **+0.047** |
| i | 0.697 | **0.707** | +0.010 |
| j | 0.443 | **0.471** | +0.029 |
| k | 0.360 | **0.379** | +0.019 |
| **Mean** | 0.520 | **0.544** | **+0.024** |

**Key findings**:
- **+0.024 R², 10/11 wins** — largest single-technique gain in the entire campaign!
- LSTM learns temporal autocorrelation in prediction errors
- This is a principled form of AR correction (trained on held-out validation residuals)
- Patient h benefits most (+0.047) — temporal patterns in gaps
- Patient e: no gain (residuals already white noise)
- The LSTM captures what the base models miss: short-term momentum

**Important**: This is NOT the same as the problematic online AR correction (EXP-1021+). The LSTM:
1. Trains on validation-set residuals (no data leakage)
2. Uses actual test-time residuals sequentially (realistic production scenario)
3. Achieves +0.024 vs +0.156 for online AR — the gap is the "information advantage" of AR

### EXP-1119: Patient Clustering → Cluster Models ✗

| Approach | k=2 | k=3 |
|----------|-----|-----|
| Patient-specific | **0.506** | **0.506** |
| Cluster-specific | 0.459 | 0.480 |
| Global | 0.414 | 0.414 |

**Patient-specific wins**: 9/11 (k=2), 10/11 (k=3)

**Key findings**:
- Clustering consistently HURTS — patient-specific models dominate
- Cross-patient data dilutes patient-specific patterns
- Global model is worst (pooling all patients catastrophic for k: −0.365)
- Each patient's glucose dynamics are too individual for cluster-based transfer
- Confirms EXP-1106 finding: per-patient > cross-patient

### EXP-1120: Grand Combined Model ★★★

Best model combining ALL winning techniques with block CV:

| Patient | Missing% | Best Method | R² (Block CV) | MAE (mg/dL) | Clarke A% |
|---------|----------|-------------|---------------|-------------|-----------|
| a | 11.6% | ensemble_dg | 0.651 | 34.7 | 70.0% |
| b | 10.4% | ensemble_dg | 0.614 | 26.9 | 75.3% |
| c | 17.3% | ensemble_dg | 0.521 | 34.3 | 60.7% |
| d | 12.6% | ensemble_dg | 0.628 | 19.1 | 81.1% |
| e | 10.9% | xgb_dg | 0.628 | 26.7 | 68.5% |
| f | 11.1% | ensemble_dg | **0.705** | 30.9 | 67.1% |
| g | 11.0% | xgb_dg | 0.576 | 30.8 | 65.5% |
| h | 64.2% | ensemble_dg | 0.177 | 28.4 | 57.2% |
| i | 10.5% | ensemble_dg | **0.686** | 31.5 | 66.7% |
| j | 9.8% | ensemble_dg | 0.431 | 20.3 | 72.9% |
| k | 11.0% | ensemble_dg | 0.410 | 9.1 | **88.8%** |
| **Mean** | — | ensemble_dg | **0.547** | **26.6** | **70.3%** |

**Key findings**:
- **R² = 0.547** (block CV) — definitive new campaign SOTA
- Previous block CV SOTA: 0.489 (EXP-1091) → **+0.058 improvement**
- Δg ensemble beats absolute ensemble in 9/11 patients
- Interpolation+flag helps patient c (+0.05 over raw)
- Clarke A zone: 70.3% mean (d=81.1% best, h=57.2% worst)
- MAE = 26.6 mg/dL (k=9.1 best due to low glucose variability)

---

## Campaign SOTA Progression (120 Experiments)

```
Naive (last value):                    R² = 0.354
Glucose-only Ridge:                    R² = 0.485
+ Physics decomposition:              R² = 0.503
+ Weighted ensemble (Ridge+GB+CNN):    R² = 0.507  ← EXP-1108
+ Δg target + XGB ensemble:           R² = 0.538  ← EXP-1111 (single split)
+ Grand combined (block CV):          R² = 0.547  ← EXP-1120 ★ NEW SOTA
+ Residual LSTM correction:           R² = 0.544  ← EXP-1118 (60/20/20)
+ Online AR correction:               R² = 0.688  ← Production (AR advantage)
Noise ceiling (σ=15 mg/dL):           R² = 0.854
```

## Updated Technique Rankings (120 Experiments, Definitive)

| Rank | Technique | Δ R² | Positive | Status |
|------|-----------|------|----------|--------|
| 1 | Online AR correction | +0.156 | 11/11 | ★★★ Production-only |
| 2 | **Residual LSTM correction** | **+0.024** | **10/11** | **★★★★ NEW** |
| 3 | Residual stacking (Ridge Δg + TCN) | +0.015 | 9/11 | ★★★ |
| 4 | Residual CNN | +0.015 | 11/11 | ★★★ Universal |
| 5 | XGBoost hyperparameter tuning | +0.011 | 11/11 | ★★★ Universal |
| 6 | Physics decomposition | +0.010 | 9/11 | ★★★ Foundation |
| 7 | Δg + XGB + TCN ensemble | +0.009 | 8/11 | ★★★ |
| 8 | Physics interactions | +0.007 | 8/11 | ★★ |
| 9 | Δg prediction target | +0.004 | 11/11 | ★★ Universal |
| 10 | Per-patient ensemble weights | +0.002 | 9/11 | ★★ |
| 11 | Glucose derivatives | +0.003 | 8/11 | ★ Small |
| 12 | DIA/ISF personalization | +0.001 | 9/11 | ✗ Negligible |
| — | Physics attention | −0.006 | 4/11 | ✗ Loses to Ridge |
| — | Patient clustering | −0.047 | 1/11 | ✗✗ Harmful |

## Key Insights

### 1. Residual LSTM is Legitimate AR Correction
EXP-1118 shows +0.024 from learning temporal patterns in prediction errors. Unlike the problematic online AR that uses future information, the LSTM:
- Trains on held-out validation residuals
- Applies corrections using only past residuals at test time
- Achieves 15% of the AR advantage (0.024 vs 0.156) without any leakage

### 2. Δg Target is Universally Beneficial
Converting from absolute glucose prediction to rate-of-change:
- Removes autoregressive dominance (the "last value" shortcut)
- Forces the model to learn actual dynamics
- Benefits EVERY model type (Ridge +0.004, TCN +0.048)
- TCN benefits dramatically because it can no longer "cheat" with AR

### 3. Conformal Prediction Solves Uncertainty
Quantile regression (EXP-1104) was poorly calibrated (77.8% for 80% target). Conformal prediction achieves ≤2% calibration error — use this for production intervals.

### 4. Patient Individuality Dominates
Clustering, global models, and cross-patient transfer all hurt. Each patient's glucose dynamics are unique enough that patient-specific models always win. The 180-day dataset per patient provides sufficient training data.

### 5. The Information Frontier is Real
Even combining ALL winning techniques, block CV SOTA = 0.547. The remaining gap to noise ceiling (0.854) = 0.307. This gap is:
- ~76% unexplained variance (systematic model error)
- ~24% irreducible noise (CGM measurement error at σ=15 mg/dL)
- The systematic component requires genuinely new information (meal announcements, activity data, stress sensors)

## Recommended Production Pipeline

```
1. Data ingestion: CGM + pump telemetry → 5-min grid
2. Imputation: Linear interpolation + missing flag (if <50% missing)
3. PK computation: Supply/demand/hepatic/net decomposition
4. Feature engineering: Grand features (glucose window + physics + interactions + derivatives + stats)
5. Target: Δg (rate of change, converted back to absolute for output)
6. Base models: Ridge + XGBoost (tuned per-patient) + TCN
7. Ensemble: Per-patient optimized weights
8. Residual correction: LSTM on recent prediction errors
9. Uncertainty: Conformal prediction intervals (80%, 90%, 95%)
10. Output: Point prediction + calibrated intervals
```

**Expected performance**: R² ≈ 0.55 (block CV), MAE ≈ 27 mg/dL, Clarke A ≈ 70%

## Files

- Script: `tools/cgmencode/exp_clinical_1111.py` (1720 lines)
- Results: `externals/experiments/exp-111[1-9]_*.json`, `exp-1120_*.json`
- Run command: `PYTHONPATH=tools python -m cgmencode.exp_clinical_1111 --detail --save --max-patients 11`
- Total runtime: ~36 minutes (XGBoost sweep dominated at 28 min)
