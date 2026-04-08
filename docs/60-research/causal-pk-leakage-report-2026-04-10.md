# Causal PK Analysis & Leakage Resolution Report

**Experiments**: EXP-1161 through EXP-1170  
**Date**: 2026-04-10  
**Campaign**: Physics-Based Metabolic Flux Decomposition (Experiments 161–170)  
**Status**: 10/10 completed — **leakage hypothesis confirmed**

## Executive Summary

This batch definitively resolved the PK temporal lead leakage question. The results are
clear and unambiguous:

### ⛔ VERDICT: PK Lead Is 100% Leakage

| Experiment | Causal Δ R² | Leaked Δ R² | Leakage Fraction |
|-----------|------------|------------|-----------------|
| EXP-1161: Simple projection | **+0.000** | +0.125 | **100%** |
| EXP-1166: Projection + enhanced | **+0.000** | — | **100%** |
| EXP-1168: All lead times | **+0.000** at all | +0.024 to +0.184 | **100%** |
| EXP-1169: 5-fold CV | **+0.000** | +0.134 | **100%** |

The causal PK projection (projecting IOB/COB forward using known absorption curves) adds
**exactly zero** information beyond what the model already extracts from the PK window.
All R²=0.658 improvement from EXP-1151 was future information leakage.

### ✅ Causal Alternatives That Work

| Feature | Δ R² | Wins | Mechanism |
|---------|------|------|-----------|
| PK momentum (EWM trend) | **+0.010** | **10/11** | ★★★ Insulin trend direction |
| PK trajectory (slopes/curvature) | +0.008 | 8/11 | ★★ Linear PK trends |
| PK rate of change | +0.006 | 7/11 | ★★ PK derivatives |
| Full causal SOTA pipeline | **+0.021** | — | ★★★ All causal combined |

### Updated Validated SOTA

```
Naive (last value):                     R² = 0.354
Glucose-only Ridge:                     R² = 0.485
+ Physics decomposition:               R² = 0.503
+ Grand combined (block CV):           R² = 0.547  ← EXP-1120
+ Causal SOTA pipeline:                R² = 0.531  ← EXP-1170 (new causal best)
+ Enhanced features XGBoost:            R² = 0.543  ← EXP-1141
+ XGBoost→LSTM pipeline:               R² = 0.581  ← EXP-1128 ★ VALIDATED BEST
+ PK lead (leaked):                    R² = 0.658  ← EXP-1151 ⛔ INVALID
Noise ceiling (σ=15 mg/dL):            R² = 0.854
```

**Validated leakage-free SOTA: R²=0.581** (EXP-1128, XGBoost→LSTM with base features)

## Detailed Results

### EXP-1161: Causal PK Projection ★★★★★ (Definitive)

Projected current PK state forward using exponential decay curves (DIA=6h, carb_abs=3h):

| Patient | Base R² | Leaked Lead R² | Causal Proj R² | Leak Fraction |
|---------|---------|---------------|---------------|--------------|
| a | 0.588 | 0.764 | 0.588 | 100% |
| b | 0.515 | 0.546 | 0.515 | 100% |
| c | 0.406 | 0.691 | 0.406 | 100% |
| d | 0.657 | 0.750 | 0.657 | 100% |
| e | 0.574 | 0.725 | 0.574 | 100% |
| f | 0.655 | 0.809 | 0.655 | 100% |
| g | 0.614 | 0.706 | 0.614 | 100% |
| h | 0.218 | 0.382 | 0.218 | 100% |
| i | 0.699 | 0.844 | 0.699 | 100% |
| j | 0.498 | 0.491 | 0.498 | 0% (lead hurts) |
| k | 0.374 | 0.464 | 0.374 | 100% |

**Why causal projection = zero**: The XGBoost model with a 2h PK window already has access
to the PK trajectory. Adding the projected future value is redundant — the model can
internally learn `IOB_future ≈ IOB_current × decay_factor` from the existing features.
The *leaked* lead contains NEW information: future bolus deliveries that change the IOB
trajectory in unpredictable ways.

---

### EXP-1162: Basal-Only Lead ★★★ (Partially Causal)

Leading only basal_iob and basal_activity channels:

| Metric | Δ R² | Notes |
|--------|------|-------|
| Basal-only lead | +0.059 | Partially causal |
| Full lead | +0.125 | Contains bolus leakage |
| Basal share | 47.5% | — |

Basal lead gives +0.059, which accounts for 47.5% of the full lead improvement. However,
even basal lead has partial leakage in AID systems: temp basal adjustments are algorithm
decisions not known in advance. For manual-mode users, basal lead would be fully causal.

Per-patient variability is high: a (+0.150), f (+0.125), h (+0.114) vs d (+0.020), j (+0.007).

---

### EXP-1163: Bolus-Only Lead (Leakage Quantification) ⛔

| Metric | Value |
|--------|-------|
| Bolus lead Δ R² | +0.095 |
| Bolus share of full lead | **76.4%** |

Bolus lead dominates the improvement. Patient i: bolus accounts for 96.9% of lead benefit.
This confirms the main leakage source is **future bolus decisions** — insulin the AID
system or user will administer between now and now+45 minutes.

---

### EXP-1164: PK Rate of Change (Causal) ★★

| Metric | Base | + PK RoC | Δ | Wins |
|--------|------|---------|---|------|
| Mean R² | 0.523 | 0.529 | +0.006 | 7/11 |

Computing PK derivatives (rate of change + acceleration) within the current window.
Small but real causal improvement. Best for patients j (+0.034), h (+0.015), b (+0.011).

---

### EXP-1165: PK Trajectory Features (Causal) ★★

| Metric | Base | + Trajectory | Δ | Wins |
|--------|------|-------------|---|------|
| Mean R² | 0.523 | 0.531 | +0.008 | 8/11 |

Richer trajectory features (slopes, curvature, peaks, position within range) provide
slightly more than simple RoC. Patient j benefits most (+0.045).

---

### EXP-1166: Causal Projection + Enhanced Features

| Metric | Base | Enhanced | + Causal Proj | Proj Gain |
|--------|------|----------|-------------|-----------|
| Mean R² | 0.527 | 0.543 | 0.543 | **+0.000** |

The causal projection adds ZERO even on top of enhanced features. This completely confirms
that the projection is redundant — the model already captures PK decay from the window.

---

### EXP-1167: PK Momentum Features (Causal) ★★★

| Metric | Base | + Momentum | Δ | Wins |
|--------|------|-----------|---|------|
| Mean R² | 0.523 | **0.533** | **+0.010** | **10/11** |

**Best causal PK feature discovered.** Exponentially weighted momentum captures whether
insulin is ramping up or declining:
```
momentum = EMA_fast(PK) - EMA_slow(PK)
```

10/11 patient wins makes this nearly universal. Best for patients j (+0.029), b (+0.027),
h (+0.020). Only patient k shows slight degradation (−0.003).

---

### EXP-1168: Systematic Leakage Table ★★★★★

```
 Lead    Actual    Basal   Causal  Δ_total Δ_causal   Leak%
------  --------  ------  ------  -------  --------  ------
  15m    0.551    0.540   0.527   +0.024   +0.000   100.0%
  30m    0.603    0.568   0.527   +0.077   +0.000   100.0%
  45m    0.652    0.585   0.527   +0.126   +0.000   100.0%
  60m    0.703    0.600   0.527   +0.177   +0.000   100.0%
  75m    0.710    0.592   0.527   +0.184   +0.000   100.0%
```

Key observations:
1. **Causal projection = 0 at ALL lead times** — not just 45 min
2. **Actual lead R² increases monotonically** — no physiological optimum, confirming leakage
3. **Basal lead peaks at 60 min** then declines — more consistent with physiology
4. The gap between actual and basal widens with lead time (more future boluses captured)

---

### EXP-1169: 5-Fold CV — Causal vs Leaked ★★★★★

| Metric | Base CV | Causal CV | Leaked CV |
|--------|---------|-----------|-----------|
| Mean R² | 0.458 | **0.458** | **0.592** |
| Δ vs base | — | **+0.000** | +0.134 |

Under rigorous 5-fold TimeSeriesSplit:
- Causal projection: exactly zero improvement (0 wins out of 11)
- Leaked lead: +0.134 improvement (10/11 wins)

This is the most definitive validation. Even cross-validation cannot save the causal
projection because the information is genuinely redundant.

---

### EXP-1170: Best Causal SOTA Pipeline ★★★

Combined all causal features: enhanced + PK RoC + trajectory + momentum:

| Metric | Base | Enhanced | Causal SOTA | Δ_total |
|--------|------|----------|------------|---------|
| Mean R² | 0.510 | 0.529 | **0.531** | **+0.021** |
| Wins vs enhanced | — | — | 6/11 | — |

The causal PK features (momentum, trajectory, RoC) add a modest +0.001 on top of enhanced
features. Combined with enhanced features (derivatives, time, dawn, interactions), the
total causal improvement is +0.021 over base. The causal SOTA R²=0.531 is below the
XGBoost→LSTM pipeline (R²=0.581 from EXP-1128).

---

## Key Conclusions

### 1. The PK Lead Was Pure Leakage
The entire +0.132 improvement from PK temporal lead (EXP-1151) was information leakage
from future insulin delivery decisions. The causal PK projection (using known absorption
curves) provides exactly zero additional information because the ML model already extracts
decay patterns from the PK window.

### 2. Causal PK Dynamics Provide Small Real Gains
PK momentum (+0.010), trajectory (+0.008), and rate of change (+0.006) are legitimate
causal features capturing insulin trend direction. PK momentum is the best, with 10/11
patient wins. However, these stack weakly with enhanced features (+0.001 additional).

### 3. The Information Frontier is Real
The validated leakage-free SOTA remains R²=0.581 (EXP-1128, XGBoost→LSTM). The gap to
the noise ceiling (R²=0.854) cannot be closed with current features and causal information.
The remaining gap likely requires:
- Better glucose history encoding (attention, wavelets)
- External features (activity, stress, sleep)
- Longer-term physiological state (ISF drift, insulin resistance)
- Per-patient personalization beyond simple feature engineering

### 4. Basal Lead Is Semi-Legitimate
Basal-only lead (+0.059) is partially valid for pump users with stable basal rates. For
manual-mode users, this is fully causal (known basal schedule). For AID users, temp basal
modifications add some leakage. This could be a useful feature in production systems where
the basal schedule is known.

## Updated Technique Rankings (170 Experiments, Causal Only)

| Rank | Technique | Δ R² | Wins | Causal? |
|------|-----------|------|------|---------|
| 1 | XGBoost→LSTM pipeline | +0.038 | 11/11 | ✅ VALIDATED |
| 2 | Combined feature engineering | +0.021 | 11/11 | ✅ VALIDATED |
| 3 | Causal SOTA pipeline | +0.021 | — | ✅ VALIDATED |
| 4 | Residual stacking | +0.015 | 9/11 | ✅ |
| 5 | Optimal ensemble (enhanced) | +0.013 | 11/11 | ✅ |
| 6 | Derivative features | +0.011 | 10/11 | ✅ |
| 7 | **PK momentum** | **+0.010** | **10/11** | **✅ NEW** |
| 8 | Physics decomposition | +0.010 | 9/11 | ✅ |
| 9 | Dawn conditioning | +0.009 | 10/11 | ✅ |
| 10 | Time-of-day conditioning | +0.008 | 10/11 | ✅ |
| 11 | **PK trajectory** | **+0.008** | **8/11** | **✅ NEW** |
| 12 | Multi-window fusion | +0.007 | 9/11 | ✅ |
| 13 | **PK rate of change** | **+0.006** | **7/11** | **✅ NEW** |
| — | PK temporal lead | +0.125 | 10/11 | ⛔ LEAKED |
| — | Causal PK projection | +0.000 | 0/11 | ✅ but redundant |

## Next Directions

### A. AR Leakage Investigation
The online AR correction (+0.156) also needs scrutiny. Does it use future information
through the autoregressive residual pattern? This is the other anomalously large improvement.

### B. Deeper Causal Features
- Patient-specific insulin sensitivity (ISF) estimation from data
- Meal pattern detection and absorption modeling
- Sleep/wake cycle detection from glucose variability patterns
- Insulin stacking detection (overlapping bolus curves)

### C. Architecture Improvements
- Attention mechanisms for glucose history (already tested, neutral)
- Larger context with summarization (multi-window fusion was +0.007)
- Per-patient fine-tuning from a global model
- Quantile regression for prediction intervals

### D. Basal Lead for Production
For production systems with known basal schedules, basal-only lead (+0.059) is a
legitimate and significant improvement. Worth implementing as a configurable feature.

## Files

| File | Description |
|------|-------------|
| `tools/cgmencode/exp_clinical_1161.py` | Experiment script (1859 lines) |
| `externals/experiments/exp-116*_*.json` | Per-experiment results |
| `docs/60-research/causal-pk-leakage-report-2026-04-10.md` | This report |
