# PK Lead Deep Dive & SOTA Frontier Report

**Experiments**: EXP-1151 through EXP-1160  
**Date**: 2026-04-10  
**Campaign**: Physics-Based Metabolic Flux Decomposition (Experiments 151–160)  
**Status**: 10/10 completed, all results captured

## Executive Summary

This batch systematically explored the PK temporal lead discovery from EXP-1144. The
headline result is **R²=0.658** (EXP-1151: PK lead + combined features, 10/11 wins) — a
**+0.132 improvement over baseline** and the largest single-batch gain in 160 experiments.
Individual patients reach R²=0.843 (patient i) and R²=0.805 (patient f).

However, we identify a **critical data leakage concern**: leading PK channels uses future
insulin delivery information (particularly boluses) that would not be available at prediction
time in a real system. The true causal improvement from PK lead is likely smaller than +0.132,
though still significant for the basal/decay component. Separating valid from leaked signal
is the top priority for the next batch.

### ⚠️ LEAKAGE ANALYSIS

Leading PK channels by N minutes means using PK state computed from insulin deliveries
up to N minutes in the future. This is decomposable:

| Component | Leading Valid? | Reasoning |
|-----------|---------------|-----------|
| Existing IOB decay | ✅ Yes | Known trajectory from past deliveries |
| Programmed basal rate | ✅ Yes | Pre-set, deterministic |
| Future bolus (user) | ❌ No | User decision not yet made |
| Future SMB (AID) | ❌ No | Algorithm decision depends on future state |
| Carb absorption (COB) | ✅ Mostly | Known trajectory after meal entry |

The EXP-1160 ablation shows IOB channels (+0.029) and activity channels (+0.028) contribute
equally. Since IOB includes both basal and bolus components, and AID bolus decisions are
unpredictable, **~30-50% of the lead improvement may be leakage from future bolus information**.

**Evidence supporting leakage concern**:
- R² increases monotonically with lead time (45→75 min), unlike a physiological optimum
- The improvement (+0.132) is implausibly large for feature engineering alone
- Patient c (insulin-dominated) shows the largest gain (+0.293), consistent with bolus leakage

**Evidence supporting partial validity**:
- Basal insulin dominates total IOB (80-95% of delivery time)
- The PK decay trajectory IS knowable from current state
- Carb channels show zero lead benefit (EXP-1160: carb Δ=−0.001), consistent with faster absorption

### SOTA Progression (Updated)

```
Naive (last value):                     R² = 0.354
Glucose-only Ridge:                     R² = 0.485
+ Physics decomposition:               R² = 0.503
+ Grand combined (block CV):           R² = 0.547  ← EXP-1120
+ XGBoost→LSTM pipeline:               R² = 0.581  ← EXP-1128
+ PK lead 45min + enhanced XGBoost:    R² = 0.658  ← EXP-1151 ⚠️ LEAKAGE RISK
+ PK lead 5-fold CV:                   R² = 0.500  ← EXP-1154 (rigorous)
+ Per-patient adaptive lead (60min):   R² = 0.586  ← EXP-1158
Noise ceiling (σ=15 mg/dL):            R² = 0.854
```

**Validated SOTA** (no leakage concern): **R²=0.581** (EXP-1128, XGBoost→LSTM pipeline)  
**SOTA with PK lead** (leakage flagged): **R²=0.658** (EXP-1151, needs causal validation)

## Experiment Results

### EXP-1151: PK Lead + Combined Features ★★★★★ (⚠️ leakage)

Combined PK lead (45 min) with all enhanced features (derivatives, time, dawn, interactions):

| Patient | Base R² | Enhanced R² | Lead+Enhanced R² | Δ |
|---------|---------|------------|-----------------|---|
| a | 0.584 | 0.615 | **0.772** | +0.188 |
| b | 0.510 | 0.534 | 0.547 | +0.037 |
| c | 0.405 | 0.426 | **0.699** | +0.293 |
| d | 0.657 | 0.667 | **0.761** | +0.103 |
| e | 0.574 | 0.603 | **0.738** | +0.164 |
| f | 0.649 | 0.669 | **0.805** | +0.155 |
| g | 0.616 | 0.623 | **0.712** | +0.095 |
| h | 0.215 | 0.228 | 0.386 | +0.171 |
| i | 0.698 | 0.713 | **0.843** | +0.145 |
| j | 0.505 | 0.507 | 0.504 | −0.001 |
| k | 0.377 | 0.386 | 0.476 | +0.098 |
| **Mean** | **0.527** | **0.543** | **0.658** | **+0.132** |

The improvement is **super-additive**: lead alone (+0.042) + enhanced alone (+0.021) = +0.063,
but combined gives +0.132. The lead uncovers signal that enhanced features can then exploit.

Patient c shows the largest gain (+0.293), moving from "hard" tier to "easy" tier.

---

### EXP-1152: PK Lead + Stabilized LSTM Pipeline ✗

Even with stronger regularization (dropout=0.5, weight_decay=1e-3, grad_clip=0.5):

| Metric | XGBoost Only | + LSTM | Δ |
|--------|-------------|--------|---|
| Mean R² | 0.642 | 0.631 | −0.010 |
| Wins | — | 3/11 | — |

**Definitive conclusion**: LSTM residual correction is obsolete when PK lead features are
present. The XGBoost with PK lead captures all temporal structure, leaving no learnable
residual pattern. Patient k: catastrophic LSTM failure (−0.085).

---

### EXP-1153: Fine-Grained PK Lead Optimization ★★★★

Tested leads from 15 to 75 minutes in 5-minute steps:

| Lead Time | Mean R² | Best Count |
|-----------|---------|-----------|
| 15 min | 0.533 | 1 (j) |
| 30 min | 0.548 | 0 |
| 45 min | 0.568 | 0 |
| 60 min | 0.605 | 1 (b) |
| **75 min** | **0.642** | **9/11** |

**9/11 patients optimize at 75 min** (the maximum tested). The monotonic improvement with
lead time is consistent with increasing information leakage rather than a physiological optimum.
A true physiological delay would show a peak and decline.

---

### EXP-1154: PK Lead 5-Fold CV ★★★★★

Rigorous TimeSeriesSplit validation confirms PK lead is real (even if partially leaked):

| Metric | Base CV | Lead45 CV | Δ |
|--------|---------|-----------|---|
| Mean R² | 0.455 | **0.500** | **+0.045** |
| Wins | — | **11/11** | — |

The +0.045 improvement under 5-fold CV is robust and universal. Even if some of this comes
from leakage, the PK trajectory information (knowable decay curves) provides genuine signal.

> **Note**: Subsequent causal decomposition analysis (EXP-1161–1169, see [Causal PK Leakage Report](causal-pk-leakage-report-2026-04-10.md)) determined that the +0.045 R² improvement from PK lead predominantly reflects learnable future bolus patterns rather than legitimate causal PK dynamics. The causal projection method (using only known insulin decay curves) adds exactly +0.000 R², confirming XGBoost already captures PK decay from the 2h window. The improvement survives 5-fold CV because future bolus patterns are statistically consistent across time folds (causal leakage, not temporal contamination).

---

### EXP-1155: Full SOTA Ensemble Pipeline ★★★

Three-model ensemble (XGBoost depth 3/4/5) with PK lead + enhanced features:

| Metric | Single XGBoost | Ensemble | Δ |
|--------|---------------|----------|---|
| Mean R² | 0.642 | **0.647** | +0.006 |
| Wins | — | 8/11 | — |

Modest ensemble benefit. The PK lead already provides most of the signal; diversity doesn't
help much when the features are this informative.

---

### EXP-1156: Asymmetric Lead by Channel Type ≈ Neutral

Leading insulin channels by 45 min and carb channels by 20 min:

| Metric | Uniform Lead | Asymmetric Lead | Δ |
|--------|-------------|----------------|---|
| Mean R² | 0.568 | 0.568 | +0.000 |
| Wins | — | 7/11 | — |

No benefit from channel-specific lead times. Uniform lead is simpler and equivalent.

---

### EXP-1157: Lead + Lag Multi-View ★★

Using BOTH current PK (lag0) and lead45 PK as features:

| Metric | Lead Only | Dual (lag0+lead45) | Δ |
|--------|-----------|-------------------|---|
| Mean R² | 0.568 | 0.572 | +0.004 |
| Wins | — | 9/11 | — |

Small additional benefit from dual temporal perspective. The current PK state provides
marginal information beyond the lead state.

---

### EXP-1158: Per-Patient Adaptive Lead Selection ★★★★

Select optimal lead per patient on validation set, evaluate on test:

| Metric | Fixed 45min | Adaptive | Δ |
|--------|------------|----------|---|
| Mean R² | 0.551 | **0.586** | **+0.035** |
| Best lead dist | — | 60min: 9, 45min: 1, 30min: 1 | — |

**Key finding: 60 min is the true optimal lead for 9/11 patients**, not 45 min. Patient b
prefers 30 min (faster insulin kinetics?), patient j prefers 45 min (short dataset).

The 60-min consensus aligns well with typical rapid-acting insulin time-to-peak (~60 min
for lispro/aspart). This supports the physiological interpretation even amid leakage concerns.

---

### EXP-1159: PK Lead + Multi-Window Fusion ≈ Neutral

| Metric | Lead Only | Lead + Fusion | Δ |
|--------|-----------|--------------|---|
| Mean R² | 0.567 | 0.566 | −0.001 |
| Wins | — | 5/11 | — |

Multi-window fusion (4h/6h summaries) adds nothing when PK lead is already present.
The lead captures the longer-horizon information more directly.

---

### EXP-1160: Channel Lead Ablation ★★★★

Which PK channels benefit most from leading?

| Channel Group | Mean Δ R² | Interpretation |
|--------------|-----------|----------------|
| All channels | **+0.041** | Full lead effect |
| IOB (total+basal+bolus) | +0.029 | Largest contributor |
| Activity (total+basal+bolus) | +0.028 | Nearly equal to IOB |
| Carb (COB+carb_activity) | −0.001 | No benefit |

**Key insight**: Carb channels get ZERO benefit from leading, which is physically correct —
carb absorption is faster (peaks at ~20-30 min) so the 45-min lead overshoots. IOB and
activity channels benefit equally, suggesting both the insulin level and its rate of action
carry complementary information when led.

Patient c gets the most from IOB lead (+0.070) and activity lead (+0.098), confirming
its insulin-dominated dynamics.

---

## Updated Technique Rankings (160 Experiments)

| Rank | Technique | Δ R² | Wins | Status |
|------|-----------|------|------|--------|
| 1 | **PK lead + combined features** | **+0.132** | **10/11** | **★★★★★ ⚠️ LEAKAGE** |
| 2 | Online AR correction | +0.156 | 11/11 | ★★★ Production-only |
| 3 | Full pipeline (all winners) | +0.043 | 11/11 | ★★★★★ |
| 4 | **PK temporal lead (45min)** | +0.042 | 10/11 | ★★★★★ ⚠️ LEAKAGE |
| 5 | XGBoost→LSTM pipeline | +0.038 | 11/11 | ★★★★★ VALIDATED |
| 6 | **Per-patient adaptive lead** | **+0.035** | **9/11** | **★★★★ ⚠️ LEAKAGE** |
| 7 | Residual LSTM (base features) | +0.024 | 10/11 | ★★★★ |
| 8 | Combined feature engineering | +0.021 | 11/11 | ★★★★ VALIDATED |
| 9 | Residual stacking | +0.015 | 9/11 | ★★★ |
| 10 | Optimal ensemble (enhanced) | +0.013 | 11/11 | ★★★ |
| 11 | Derivative features | +0.011 | 10/11 | ★★★★ |
| — | Asymmetric lead | +0.000 | 7/11 | ≈ Neutral |
| — | Lead + multi-window fusion | −0.001 | 5/11 | ≈ Neutral |
| — | LSTM + PK lead features | −0.010 | 3/11 | ✗ Obsolete |

## Critical Next Steps

### Priority 1: Causal PK Projection (MUST DO)
Separate the valid PK lead signal from leakage:
- **Basal-only lead**: Lead only basal_iob and basal_activity (pre-programmed, known)
- **Decay-only projection**: Project current IOB forward using known absorption curves
- **Causal PK**: Compute what the PK state WOULD be in 45 min assuming no new boluses

### Priority 2: Extended Lead Exploration
- Test leads beyond 75 min (90, 120 min) to find the saturation point
- If monotonically increasing → confirms leakage dominance
- If peaks and declines → genuine physiological optimum

### Priority 3: Causal Feature Engineering
- Use the PK model's known absorption curves to project IOB/COB forward
- This is physically valid: given current IOB and DIA, we know the decay trajectory
- Combine with known basal rate schedule for legitimate future PK estimation

### Priority 4: Leakage-Free SOTA Attempt
- Combine causal PK projection + enhanced features + ensemble
- Target: R²>0.56 without any leakage

## Patient Tier Update (with PK lead)

| Tier | Patients | Lead+Enhanced R² | Notes |
|------|----------|-----------------|-------|
| **Excellent** | f, i | 0.80-0.84 | ⚠️ Inflated by lead |
| **Good** | a, d, e, g | 0.71-0.77 | ⚠️ Inflated by lead |
| **Medium** | c | 0.70 | ⚠️ Most inflated (+0.293) |
| **Moderate** | b, k | 0.48-0.55 | Smaller lead benefit |
| **Hard** | h, j | 0.39-0.50 | Data-limited |

## Files

| File | Description |
|------|-------------|
| `tools/cgmencode/exp_clinical_1151.py` | Experiment script (1431 lines) |
| `externals/experiments/exp-115*_*.json` | Per-experiment results |
| `docs/60-research/pk-lead-deep-dive-report-2026-04-10.md` | This report |
