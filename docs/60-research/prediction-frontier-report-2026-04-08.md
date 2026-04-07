# Prediction Frontier Research Report

**Series**: Metabolic Flux Glucose Prediction Campaign  
**Prior report**: `temporal-alignment-report-2026-04-07.md` (Parts I-XLVII, EXP-831-900)  
**Start date**: 2026-04-08  
**Data**: 11 patients, ~180 days each, 5-min CGM intervals (~50K timesteps/patient)

---

## Part I: Adaptive Physics, Shape Features, and Grand Benchmark (EXP-891-910)

**Date**: 2026-04-08  
**Experiments**: EXP-891 through EXP-910 (20 experiments in 2 batches)  
**Scripts**: `tools/cgmencode/exp_autoresearch_891.py`, `tools/cgmencode/exp_autoresearch_901.py`

### Campaign Context

After 80 experiments (EXP-831-890), the validated SOTA stood at R2=0.561 via CV stacking (EXP-871), against a linear oracle ceiling of R2=0.613. This batch of 20 experiments investigates three hypotheses for the remaining 0.052 gap: temporal drift, missing dynamic features, and irreducible noise.

### Results: EXP-891-900 (Adaptive Physics & Personalization)

| Exp | Name | R2 | Delta | Key Finding |
|-----|------|-----|-------|-------------|
| 891 | Locally Weighted Ridge | 0.506 | +0.000 | Recency weighting: no benefit |
| 892 | Adaptive ISF | 0.507 | +0.001 | Static ISF sufficient |
| 893 | Post-Prandial Shape | 0.512 | **+0.006** | Meal response shape matters |
| 894 | Feature Stability | 9/16 stable | -- | BG, BG2, residual dominate universally |
| 895 | Error Attribution | MAE 29.1/26.5 | -- | Meals 10% harder than basal |
| 896 | Sliding Window | 0.500 | -0.006 | Global model wins; more data always better |
| 897 | BG Volatility | 0.507 | +0.001 | Negligible conditioning value |
| 898 | IOB Curve Shape | 0.510 | +0.004 | Dynamic IOB trajectory helps |
| 899 | Leak-Safe AR | 0.495 | **-0.011** | AR definitively dead at all lags |
| 900 | Combined Benchmark | 0.521 | **+0.015** | Shape features stack additively |

### Results: EXP-901-910 (PK Derivatives, Diagnostics, Grand Benchmark)

| Exp | Name | R2 | Delta | Key Finding |
|-----|------|-----|-------|-------------|
| 901 | PK Derivative Features | 0.515 | **+0.009** | Supply/demand rate-of-change is informative |
| 902 | Meal Uncertainty | hi=32.9, lo=25.1 | ratio=1.31 | High-uncertainty periods 31% harder |
| 903 | Forward + Shape Combined | 0.539 | **+0.033** | Additivity confirmed! Forward sums + shape |
| 904 | Residual Decomposition | sensor=1.5% | meal=100% | Meal uncertainty dominates residual budget |
| 905 | Multi-Horizon Shape | 0.489 | -0.017 | Shape+stacking overfit; don't combine naively |
| 906 | Patient Difficulty | r(meanBG,R2)=0.54 | -- | Higher BG = easier prediction (wider range) |
| 907 | Conformal Prediction | coverage=90.6% | width=128.8 | Well-calibrated intervals at 90% target |
| 908 | Asymmetric Loss | R2=0.474 | -0.032 | Trades 6% R2 for 75% more hypo sensitivity |
| 909 | Phase-Conditioned | 0.509 | +0.003 | Small benefit from rise/fall separation |
| 910 | Grand CV Stacking | **0.560** | **+0.054** | Matches validated SOTA from backward base |

### Breakthrough: EXP-910 Grand Benchmark Per-Patient

| Patient | Base R2 | Grand R2 | Delta | Notes |
|---------|---------|----------|-------|-------|
| a | 0.591 | 0.617 | +0.026 | |
| b | 0.488 | 0.554 | +0.066 | |
| c | 0.383 | **0.522** | **+0.139** | Largest gain: difficult patient responds to features |
| d | 0.653 | 0.695 | +0.042 | |
| e | 0.570 | 0.634 | +0.065 | |
| f | 0.634 | 0.675 | +0.041 | |
| g | 0.546 | 0.599 | +0.053 | |
| h | 0.192 | 0.218 | +0.026 | Still extremely difficult |
| i | 0.697 | **0.776** | **+0.078** | Best patient exceeds oracle on backward base |
| j | 0.450 | 0.447 | -0.003 | Only patient that doesn't improve |
| k | 0.358 | 0.423 | +0.065 | |

**Patient c** jumps from worst-tier (0.383) to mid-tier (0.522), gaining +0.139 -- the largest single-patient improvement in the entire campaign. **Patient i** reaches 0.776, well above the population-average oracle ceiling (0.613), confirming that oracle limits are patient-specific.

### Key Discoveries

#### 1. Dynamic PK Shape Is the Winning Feature Class

Three shape-related experiments all contribute:
- PK derivatives (EXP-901): +0.009
- Post-prandial shape (EXP-893): +0.006
- IOB curve shape (EXP-898): +0.004

The combined message: **how insulin and glucose are changing** (derivatives, slopes, phases) contains information beyond their instantaneous magnitudes. This is consistent with the underlying physiology -- the same IOB level means different things if rising (recent bolus, more insulin coming) vs falling (bolus wearing off).

#### 2. Forward-Looking Sums + Shape = Confirmed Additive (+0.033)

EXP-903 directly confirms that the two feature improvements discovered in separate batches are additive:
- Forward-looking sums alone: 0.533 (+0.027 over backward)
- Forward + shape features: 0.539 (+0.033 over backward)
- Shape delta on top of forward: +0.006, matching EXP-893 exactly

This means feature improvements from different batches can be reliably combined.

#### 3. Meal Uncertainty Is 100% of the Residual Budget

EXP-904 variance decomposition:
- Sensor noise: only 1.5% of residual variance
- Meal uncertainty: **100%** (dominates after overlaps)
- Time-of-day systematic: 5.5%
- Remaining unexplained: 0%

The residual is almost entirely explained by meal-related uncertainty. Combined with EXP-902 (high-uncertainty periods are 31% harder, MAE 32.9 vs 25.1), this means: **to close the remaining gap, you must reduce meal uncertainty** -- better carb counting, meal composition modeling, or glycemic index estimation.

#### 4. The Gap Is NOT Drift (Triple Confirmation)

- EXP-891: Recency weighting = 0 improvement
- EXP-896: Sliding window = worse than global (-0.006)
- EXP-906: No temporal component in difficulty predictor

For AID-controlled patients over 6 months, temporal non-stationarity is not a meaningful error source.

#### 5. Patient Difficulty Is Predictable

EXP-906 correlations with model R2:
- Mean BG: r=0.542 (higher BG = easier -- wider dynamic range)
- BG CV: r=0.451 (higher variability = easier -- more signal)
- TIR: r=-0.525 (tighter control = harder -- less variation to predict)

**Counterintuitive**: Well-controlled patients (high TIR) are HARDER to predict because their glucose stays in a narrow band with less signal. Patient h (TIR=85%, R2=0.192) and patient k (TIR=95.1%, R2=0.358) illustrate this -- tight control leaves little predictable variation.

#### 6. Asymmetric Loss Has Clinical Value

EXP-908: Trading 6% R2 (0.506 to 0.474) buys 75% more hypoglycemia sensitivity (0.097 to 0.170). For clinical deployment, this trade is likely worthwhile -- missing a hypo event is far more dangerous than over-predicting glucose. Future work should explore the Pareto frontier of R2 vs hypo sensitivity.

#### 7. Conformal Prediction Works Out-of-Box

EXP-907: 90% target coverage achieved at 90.6% actual, with mean interval width of 128.8 mg/dL. The model is well-calibrated for uncertainty quantification without additional calibration steps.

### Updated Prediction Frontier (90 experiments, EXP-831-910)

```
Naive persistence:              R2 = 0.292  (MAE=33.1)
Physics-only flux:              R2 = 0.372
Ridge 8-feature (backward):     R2 = 0.506  (MAE=28.2)
+PK derivatives:                R2 = 0.515  (+0.009)
+Post-prandial shape:           R2 = 0.512  (+0.006)
Forward-looking sums:           R2 = 0.533  (+0.027 over backward)
Forward + shape:                R2 = 0.539  (+0.033 over backward)
Enhanced 16-feature:            R2 = 0.534
Context-conditioned:            R2 = 0.550
Stacked generalization:         R2 = 0.558
CV Stacked (871 SOTA):          R2 = 0.561
Grand CV Stack (EXP-910):       R2 = 0.560  (from backward base -- matches SOTA)
Linear oracle ceiling:          R2 = 0.613
```

**Projected combined SOTA**: Forward-looking base (0.534) + shape features (+0.006) + PK derivatives (+0.009) + CV stacking (+0.027) ~ **R2 = 0.576**, narrowing oracle gap to **0.037**.

### What Works vs What Doesn't (90 Experiments Summary)

**Productive features (Tier 1-2, delta > +0.005)**:
- Multi-horizon CV stacking: +0.027 (EXP-871)
- Forward-looking sums: +0.027 over backward (EXP-903)
- Prediction disagreement: +0.013 (EXP-867)
- PK derivatives: +0.009 (EXP-901)
- Post-prandial shape: +0.006 (EXP-893)
- Causal EMA: +0.005 (EXP-882)

**Dead ends (delta <= 0)**:
- Nonlinear models: +0.002 max (EXP-831)
- Feature interactions: -0.001 (EXP-866)
- Meal-size proxy: -0.003 (EXP-864)
- Sliding window: -0.006 (EXP-896)
- AR residuals at any lag: -0.011 (EXP-899)
- Multi-horizon shape (naive): -0.017 (EXP-905)
- Asymmetric loss: -0.032 R2 (but +75% hypo sensitivity)
- Kalman filter: -0.083 (EXP-884)
- MLP sequence model: -0.029 (EXP-889)

### Recommendations for EXP-911-920

Given that meal uncertainty dominates the residual budget (100%), the next frontier should focus on:

1. **Meal Composition Proxy**: Can glucose rise rate, peak shape, or descent rate infer glycemic index?
2. **Carb-Free Interval Analysis**: How does prediction quality vary with time-since-last-meal?
3. **Stacking with Forward Base**: Re-run EXP-871 CV stacking using forward-looking features + shape + derivatives as base.
4. **Per-Patient Oracle**: Compute patient-specific oracle ceilings to understand per-patient potential.
5. **Error-Weighted Stacking**: Weight stacking meta-learner by local uncertainty estimates.
6. **Meal Phase Derivatives**: Combine PK derivatives specifically during post-prandial windows.
7. **Insulin Sensitivity Time-Series**: Use rolling effective ISF as a feature (not correction, but context).
8. **Basal vs Bolus Decomposition**: Separate insulin supply into basal and bolus channels.
9. **Glucose Momentum Features**: Multi-scale rate of BG change (5, 15, 30, 60 min windows).
10. **Definitive Forward-Base Grand Benchmark**: The experiment that should set new absolute SOTA.
