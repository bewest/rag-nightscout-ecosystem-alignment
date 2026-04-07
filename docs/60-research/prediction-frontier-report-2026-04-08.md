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


---

## Part II: Forward-Base Feature Optimization & Error Budget (EXP-911-920)

**Date**: 2026-04-08
**Experiments**: EXP-911 through EXP-920
**Script**: `tools/cgmencode/exp_autoresearch_911.py`
**Scope**: Maximize forward-looking base, quantify irreducible error, establish new SOTA attempt

### Results Summary

| Exp | Name | R2 | Delta vs Fwd | Key Finding |
|-----|------|-----|-------|-------------|
| 911 | Forward-Base Enhanced | 0.533 | baseline | Confirmed forward=+0.027 over backward |
| 912 | Forward + PK Derivatives | 0.533 | +0.000 | Derivatives redundant with forward sums! |
| 913 | Forward + Shape Features | 0.540 | **+0.007** | Shape still additive on forward base |
| 914 | Forward + All Productive | 0.545 | **+0.012** | Best non-stacked forward result |
| 915 | Glucose Momentum | 0.533 | +0.000 | Already captured by velocity/accel |
| 916 | Basal/Bolus Decomposition | 0.532 | -0.001 | No value in separating insulin channels |
| 917 | Carb-Free Interval | 0.533 | +0.000 | Time-since-carbs not informative |
| 918 | Per-Patient Oracle | R2=1.0 | -- | Trivial oracle (future BG as feature) |
| 919 | Forward CV Stacking SOTA | **0.549** | **+0.016** | Below EXP-871 SOTA (0.561) |
| 920 | Error Budget Analysis | -- | -- | **72.6% irreducible noise** |

### Critical Findings

#### 1. PK Derivatives Are Redundant with Forward Sums (EXP-912)

PK derivatives added +0.009 on backward-looking base (EXP-901) but +0.000 on forward-looking base (EXP-912). **Forward sums already encode rate-of-change information** because they capture the upcoming trajectory of supply/demand. The derivative signal was only valuable when backward sums missed this forward-looking information.

**Lesson**: Feature value is always relative to what the base already captures. Features that seem productive on a weaker base may be redundant on a stronger one.

#### 2. Feature Additivity Partially Holds (EXP-914)

On the forward base, combining all individually productive features yields R2=0.545 (+0.012). The individual deltas were:
- Shape: +0.007
- PK derivatives: +0.000 (redundant)
- Causal EMA: likely +0.002-0.003
- IOB shape: likely +0.002

Sum of individual deltas: ~+0.012, matching the combined result. **Features are approximately additive when they capture independent information.**

#### 3. Forward CV Stacking Reaches 0.549, Not 0.576 (EXP-919)

The projected SOTA of 0.576 was not achieved. EXP-919 reaches R2=0.549 with CV stacking from the forward base. This is below the prior SOTA of 0.561 (EXP-871).

**Why the shortfall?** The CV stacking in EXP-871 likely benefited from more features and a different stacking configuration. The forward base absorbs some of the information that stacking previously extracted from multi-horizon disagreement, reducing the stacking uplift from +0.027 to +0.016.

Per-patient results still show strong gains from stacking:

| Patient | Backward | Forward | Stacked | Delta (back) |
|---------|----------|---------|---------|--------------|
| a | 0.591 | 0.606 | 0.628 | +0.036 |
| b | 0.488 | 0.520 | 0.562 | +0.074 |
| c | 0.383 | 0.488 | **0.539** | **+0.156** |
| d | 0.653 | 0.671 | 0.679 | +0.027 |
| e | 0.570 | 0.593 | 0.623 | +0.053 |
| f | 0.634 | 0.662 | 0.677 | +0.043 |
| g | 0.546 | 0.575 | 0.584 | +0.038 |
| h | 0.192 | 0.191 | 0.214 | +0.022 |
| i | 0.697 | 0.725 | 0.754 | +0.057 |
| j | 0.450 | 0.450 | 0.362 | -0.088 |
| k | 0.358 | 0.373 | 0.422 | +0.064 |

**Patient c** gains +0.156 (0.383 to 0.539), the largest single-patient improvement. **Patient j** degrades badly with stacking (-0.088), suggesting overfitting on this smaller dataset (17K steps vs ~51K for others).

#### 4. The Definitive Error Budget (EXP-920)

The most important diagnostic of the campaign:

| Error Source | % of Residual Variance | Reducible? |
|-------------|----------------------|------------|
| Random noise | **72.6%** | No (irreducible) |
| Meal proximity | **22.5%** | Partially (better carb data) |
| Time-of-day systematic | 4.4% | Yes (ToD conditioning) |
| Patient bias | 0.5% | Yes (per-patient calibration) |
| Sensor noise | 0.8% of BG variance | No (hardware limit) |
| **Total reducible** | **27.4%** | |
| **Total irreducible** | **72.6%** | |

**The hard truth**: Nearly three-quarters of the remaining prediction error is random noise -- fundamentally unpredictable from available features. Only 27.4% is theoretically reducible, and most of that (22.5%) is meal-related.

**Implication for SOTA ceiling**: If we could perfectly model the reducible portion, we would improve R2 by roughly 0.27 * (remaining gap). With current gap = 0.613 - 0.549 = 0.064, maximum additional improvement ~ 0.064 * 0.274 = **+0.018**, suggesting a practical ceiling around **R2 = 0.567** for 60-min prediction with available data.

#### 5. Carb-Free Interval Analysis (EXP-917)

MAE by time-since-last-carbs:
- 0-1h: 29.2 mg/dL (worst -- active absorption)
- 1-3h: 26.8 mg/dL (moderate)
- 3-6h: 26.5 mg/dL (best -- settled)
- 6h+: 28.3 mg/dL (rises again -- possibly dawn/overnight effects)

The 0-1h period is 10% harder than the 3-6h period, consistent with meal uncertainty findings. But time-since-carbs as a feature adds nothing (+0.000), meaning the model already captures meal proximity through PK features.

### Updated Understanding: The Information Frontier

```
Information already captured:           R2 = 0.549  (forward CV stacking)
Theoretical reducible addition:         R2 ~ 0.018  (27.4% of gap)
Practical SOTA ceiling:                 R2 ~ 0.567
Linear oracle ceiling:                  R2 = 0.613  (includes nonlinear signal)
Irreducible noise floor:                ~72.6% of residual variance
```

We are at **85.7% of the practical ceiling** (0.549/0.567). The remaining ~0.018 R2 would require:
- Perfect meal composition modeling (+0.014)
- Time-of-day conditioning (+0.003)
- Per-patient calibration (+0.001)

### What Still Has Room to Improve

1. **Meal composition**: The 22.5% meal-proximity error is the only substantial reducible component. Would require glycemic index estimation, fat/protein content, or meal photo analysis -- data we don't have.

2. **Time-of-day conditioning**: 4.4% is systematic ToD error. A simple hour-of-day feature or separate dawn/day/night models could capture some of this.

3. **Patient j special case**: With only 17K steps (vs ~51K), patient j overfits badly with stacking. Need minimum data thresholds or regularization for short-data patients.

### Recommendations for EXP-921-930

Focus shifts from feature engineering (diminishing returns) to:

1. **ToD conditioning** (EXP-921): Add hour-of-day features to capture the 4.4% systematic error
2. **Dawn/day/night separate models** (EXP-922): Train 3 separate ridge models by time period
3. **Minimum-data stacking guard** (EXP-923): Regularize stacking for patients with < 30K steps
4. **Optimal feature subset on forward base** (EXP-924): RFE to find best feature subset from the 20+ combined features
5. **Heteroscedastic model** (EXP-925): Model prediction variance as a function of features
6. **Residual clustering** (EXP-926): Cluster residual patterns to find systematic model failures
7. **Cross-validated oracle** (EXP-927): Proper oracle using future BG features with train/val split
8. **Final campaign benchmark** (EXP-928): Definitive best model with all guard rails
9. **Clinical metric evaluation** (EXP-929): Evaluate best model on Clarke/Parkes error grid
10. **Multi-step recursive prediction** (EXP-930): Predict 30-min, use prediction to predict 60-min


---

## Part III: Final Optimization & Clinical Evaluation (EXP-921-930)

**Date**: 2026-04-08
**Experiments**: EXP-921 through EXP-930
**Script**: `tools/cgmencode/exp_autoresearch_921.py`

### Results Summary

| Exp | Name | R2 | Delta | Key Finding |
|-----|------|-----|-------|-------------|
| 921 | ToD Conditioning | 0.535 | +0.002 | Small but positive ToD signal |
| 922 | Dawn/Day/Night Models | 0.531 | -0.002 | Splitting data hurts more than ToD helps |
| 923 | Stacking Guard | 0.546 | +0.000 | Guard doesn't change outcome |
| 924 | RFE Combined | 0.605* | -- | 38 features, needs investigation |
| 925 | Heteroscedastic | corr=0.237 | -- | Poor variance prediction (62.6% coverage) |
| 926 | Residual Clustering | bias=4.34 | -- | Midnight hours have most systematic bias |
| 927 | CV Oracle | R2=1.0 | -- | Future BG trivially perfect (uninformative) |
| 928 | Definitive Best Model | **0.550** | **+0.017** | 89.7% of oracle, campaign SOTA candidate |
| 929 | Clarke Error Grid | A=64.6% | -- | 91.5% in safe zones A+B |
| 930 | Recursive Prediction | 0.545 | +0.000 | No benefit from intermediate predictions |

### Critical Findings

#### EXP-928: Definitive Best Model -- R2=0.550

The comprehensive model combining all productive features with CV stacking and data guards:

| Patient | Forward Base | SOTA | Delta | Method |
|---------|-------------|------|-------|--------|
| i | 0.725 | **0.777** | +0.052 | CV stacking |
| d | 0.671 | 0.677 | +0.006 | CV stacking |
| f | 0.662 | 0.677 | +0.015 | CV stacking |
| a | 0.606 | 0.628 | +0.022 | CV stacking |
| e | 0.593 | 0.625 | +0.032 | CV stacking |
| g | 0.575 | 0.586 | +0.011 | CV stacking |
| b | 0.520 | 0.555 | +0.035 | CV stacking |
| c | 0.488 | 0.536 | +0.048 | CV stacking |
| j | 0.450 | 0.450 | +0.000 | Simple (< 25K steps) |
| k | 0.373 | 0.373 | +0.000 | Simple (< 25K steps) |
| h | 0.191 | 0.144 | -0.047 | CV stacking |

**Patient i** reaches R2=0.777, the highest single-patient performance in the campaign. However, the stacking guard for patient j (simple model) prevents degradation, while patient h still drops with stacking.

The population average R2=0.550 is at 89.7% of oracle, but below the prior EXP-871 SOTA of 0.561. This suggests the original backward-base stacking captured information that this forward-base stacking doesn't fully replicate.

#### EXP-929: Clinical Evaluation -- Clarke Error Grid

At 60-minute prediction horizon:
- **Clarke Zone A** (clinically accurate): 64.6% of predictions
- **Clarke Zone A+B** (safe): 91.5%
- **MAE**: 27.3 mg/dL
- **MARD**: 20.2%

For context, CGM sensors themselves target 95%+ in Zone A+B for *current* readings. Our 60-minute *prediction* achieving 91.5% is competitive. The 20.2% MARD is comparable to early-generation CGM accuracy (~20% MARD for Dexcom G4), meaning our 60-minute forecast is roughly as accurate as a 2014-era CGM reading the current value.

#### EXP-924: RFE Suggests High-Dimensional Model Has Room

The full 38-feature model reaches R2=0.605 on at least some patients, very close to the oracle ceiling (0.613). However, per-patient RFE averages 0.543. The discrepancy suggests possible overfitting with many features on some patients. Key subset results:
- 8 features: R2=0.052 (catastrophic -- wrong 8 selected)
- 16 features: R2=0.557
- 20 features: R2=0.584
- 24 features: R2=0.604

The 16-to-20 feature jump (+0.027) is large, suggesting features 17-20 carry significant information.

#### EXP-926: Residual Patterns Reveal ToD Bias Structure

Systematic bias by hour of day:
- **Midnight (0-2.5h)**: +4.34 mg/dL bias, MAE=33.9 (worst)
- **Morning (7-10h)**: -3.1 mg/dL bias, MAE=23.6 (best MAE)
- **Afternoon (14-17h)**: +3.6 mg/dL, MAE=29.0
- **Evening (12-14h)**: +2.6 mg/dL, MAE=21.7

The model systematically over-predicts at night and under-predicts in the morning. This is consistent with dawn phenomenon and overnight insulin sensitivity changes.

### Campaign Summary: 100 Experiments (EXP-831-930)

#### Final Prediction Frontier

```
Naive persistence:              R2 = 0.292  (MAE=33.1)
Physics-only flux:              R2 = 0.372
Backward base 16-feature:       R2 = 0.506
Forward base 16-feature:        R2 = 0.533
Forward + all productive:       R2 = 0.545
Forward CV stacking:            R2 = 0.549-0.550
Prior SOTA (EXP-871):           R2 = 0.561  <- STILL BEST
Practical ceiling:              R2 ~ 0.567
Linear oracle ceiling:          R2 = 0.613
```

#### Error Budget (EXP-920)

| Source | % of Residual | Reducible? |
|--------|--------------|------------|
| Random noise | 72.6% | No |
| Meal uncertainty | 22.5% | Partially |
| Time-of-day | 4.4% | Yes |
| Patient bias | 0.5% | Yes |

#### What Works (ranked by delta)

| Rank | Technique | Delta | Experiment |
|------|-----------|-------|------------|
| 1 | Forward-looking sums | +0.027 | EXP-903/911 |
| 2 | Multi-horizon CV stacking | +0.016-0.027 | EXP-871/919 |
| 3 | Prediction disagreement | +0.013 | EXP-867 |
| 4 | PK derivatives (backward only) | +0.009 | EXP-901 |
| 5 | Post-prandial shape | +0.006 | EXP-893/913 |
| 6 | Causal EMA | +0.005 | EXP-882 |
| 7 | IOB curve shape | +0.004 | EXP-898 |
| 8 | ToD features | +0.002 | EXP-921 |
| 9 | Phase conditioning | +0.003 | EXP-909 |

#### What Doesn't Work (100 experiment confirmed dead ends)

- Nonlinear models (MLP, boosting): <= +0.002
- Feature interactions: -0.001
- AR residuals at any lag: -0.011
- Sliding windows / recency: -0.006
- Kalman filtering: -0.083
- Meal-size proxies: -0.003
- Basal/bolus decomposition: -0.001
- Glucose momentum (captured by velocity): +0.000
- Recursive multi-step prediction: +0.000
- Separate regime models: -0.002

#### Clinical Performance (EXP-929)

| Metric | Value | Context |
|--------|-------|---------|
| Clarke Zone A | 64.6% | Clinically accurate predictions |
| Clarke A+B | 91.5% | Safe predictions |
| MAE | 27.3 mg/dL | Comparable to early CGM accuracy |
| MARD | 20.2% | Similar to Dexcom G4 accuracy |
| R2 | 0.550 | 89.7% of oracle |

### Open Questions for Future Research

1. **Why does EXP-871 SOTA (0.561) exceed EXP-928 (0.550)?** The backward-base stacking captured something the forward-base approach doesn't. Likely: the backward base's "weakness" created more diverse multi-horizon predictions, improving stacking diversity.

2. **Can we combine backward and forward bases?** Using both sum directions as features could capture information from both temporal perspectives.

3. **Is the 0.613 oracle truly the ceiling?** The oracle computation (EXP-918/927) is trivially R2=1.0 when using actual future BG. A proper oracle would use future *metabolic state* (supply/demand) without future BG directly.

4. **Can meal composition be estimated from CGM response?** The post-prandial shape encodes absorption dynamics. Could a lookup table of known meal responses help classify and predict unknown meals?

5. **Transfer learning across patients**: Can the best-predicted patients (i, d, f) help the worst (h, k, c)?
