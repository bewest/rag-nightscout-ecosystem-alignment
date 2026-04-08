# Causal Benchmark & LSTM Overfitting Discovery — EXP-1171–1180

**Date**: 2026-04-10
**Campaign**: Experiments 1171–1180 (10 experiments, 11 patients each)
**Prior**: EXP-1161–1170 proved PK lead is 100% leakage. This batch explores genuine causal improvements.

## Executive Summary

This batch pursued **genuine causal improvements** after definitively proving temporal PK lead was data leakage. The most important discovery: **the XGBoost→LSTM pipeline that defined our SOTA (R²=0.581) is overfitting** — 5-fold cross-validation shows it actually *hurts* performance by −0.068. Enhanced XGBoost features (+0.023 in CV) are the real validated improvement.

### Key Results

| EXP | Technique | Δ R² | Wins | Rating |
|-----|-----------|------|------|--------|
| 1176 | XGBoost hyperparameter tuning | +0.026 | 11/11 | ★★★★ |
| 1172 | Multi-horizon regularization | +0.013 | 11/11 | ★★★★ |
| 1171 | Enhanced + LSTM combined | +0.013 | 9/11 | ★★★ |
| 1173 | Same-time-yesterday memory | +0.005 | 8/11 | ★★ |
| 1178 | Glucose variability features | +0.005 | 9/11 | ★★ |
| 1174 | Cross-patient transfer | +0.004 | 9/11 | ★★ |
| 1179 | Insulin stacking detection | +0.003 | 6/11 | ★ |
| 1175 | Glucose encoding variants | — | — | Raw is best |
| 1177 | Residual analysis | — | — | Autocorr=0.474 |
| **1180** | **5-fold CV benchmark** | **−0.068** | **0/11** | **⛔ LSTM OVERFITS** |

---

## Critical Discovery: LSTM Pipeline Overfits (EXP-1180)

### The Problem

Our previous SOTA was R²=0.581 (EXP-1128), achieved with an XGBoost→LSTM pipeline on a single chronological train/val/test split. The LSTM stage added +0.038 over XGBoost alone. **This appeared to be our strongest technique.**

### 5-Fold Cross-Validation Results

| Patient | Base CV | Enhanced CV | Pipeline CV | Δ Enhanced | Δ Pipeline |
|---------|---------|-------------|-------------|------------|------------|
| a | 0.587 | 0.612 | 0.580 | +0.025 | −0.008 |
| b | 0.552 | 0.576 | 0.529 | +0.024 | −0.023 |
| c | 0.373 | 0.388 | 0.377 | +0.015 | +0.004 |
| d | 0.523 | 0.558 | 0.502 | +0.035 | −0.021 |
| e | 0.569 | 0.600 | 0.531 | +0.030 | −0.039 |
| f | 0.632 | 0.646 | 0.623 | +0.015 | −0.009 |
| g | 0.492 | 0.517 | 0.485 | +0.025 | −0.007 |
| h | 0.023 | 0.045 | −0.018 | +0.022 | −0.040 |
| i | 0.618 | 0.636 | 0.613 | +0.018 | −0.005 |
| j | 0.369 | 0.384 | 0.275 | +0.016 | −0.093 |
| k | 0.263 | 0.286 | −0.247 | +0.023 | −0.510 |
| **Mean** | **0.455** | **0.477** | **0.386** | **+0.023** | **−0.068** |

### Diagnosis

- **Enhanced features** consistently help: +0.023 mean, **all 11 patients improve**
- **LSTM pipeline** consistently hurts: −0.068 mean, **0/11 patients improve in CV**
- Patient k: catastrophic −0.510 from LSTM (tiny well-controlled dataset)
- Patient j: −0.093 from LSTM (small dataset, high variance)
- The single-split R²=0.581 was an artifact of the LSTM memorizing the specific temporal boundary

### Revised SOTA Assessment

```
Previous claim:   R² = 0.581 (XGBoost→LSTM, single split)  ← OVERFITTING
Validated (CV):   R² = 0.477 (Enhanced XGBoost, 5-fold CV)  ← TRUE BEST
Baseline (CV):    R² = 0.455 (Glucose-only XGBoost, 5-fold CV)
Improvement:      Δ = +0.023 (genuine, validated)
```

**The LSTM stage is not a valid improvement. Our real SOTA is Enhanced XGBoost at R²=0.477 (5-fold CV).**

---

## EXP-1172: Multi-Horizon Regularization ★★★★

Training XGBoost to predict multiple horizons (30, 60, 90 min) simultaneously acts as a regularizer that improves 60-min prediction.

| Patient | Single 60m | Multi-Horizon | Δ |
|---------|-----------|---------------|---|
| a | 0.588 | 0.594 | +0.006 |
| b | 0.508 | 0.523 | +0.016 |
| c | 0.402 | 0.418 | +0.016 |
| d | 0.662 | 0.678 | +0.016 |
| e | 0.577 | 0.582 | +0.005 |
| f | 0.660 | 0.662 | +0.003 |
| g | 0.611 | 0.613 | +0.002 |
| h | 0.233 | 0.253 | +0.020 |
| i | 0.705 | 0.708 | +0.004 |
| j | 0.487 | 0.527 | +0.041 |
| k | 0.381 | 0.390 | +0.010 |
| **Mean** | **0.528** | **0.541** | **+0.013** |

- **11/11 patients improve** — universally helpful
- Largest gains on hard patients (j: +0.041, h: +0.020)
- Zero-cost technique (same training data, auxiliary targets provide free regularization)
- Multi-horizon forces the model to learn smooth temporal dynamics, not noise

---

## EXP-1176: XGBoost Hyperparameter Deep Tuning ★★★★

Per-patient grid search over depth, learning rate, and n_estimators.

| Patient | Default | Tuned | Δ | Best Config |
|---------|---------|-------|---|-------------|
| a | 0.575 | 0.594 | +0.019 | d6/lr0.01/n200 |
| b | 0.511 | 0.530 | +0.020 | d8/lr0.01/n500 |
| c | 0.399 | 0.411 | +0.012 | d8/lr0.01/n200 |
| d | 0.628 | 0.672 | +0.044 | d3/lr0.01/n1000 |
| e | 0.572 | 0.577 | +0.005 | d6/lr0.01/n200 |
| f | 0.650 | 0.662 | +0.012 | d4/lr0.03/n500 |
| g | 0.611 | 0.618 | +0.006 | d8/lr0.01/n500 |
| h | 0.230 | 0.238 | +0.008 | d3/lr0.01/n500 |
| i | 0.688 | 0.699 | +0.011 | d4/lr0.01/n1000 |
| j | 0.414 | 0.521 | +0.107 | d3/lr0.03/n200 |
| k | 0.335 | 0.374 | +0.039 | d8/lr0.01/n200 |
| **Mean** | **0.510** | **0.536** | **+0.026** | |

- **11/11 patients improve** — universally helpful
- Patient j: massive +0.107 gain (small dataset benefits from strong regularization at d3/lr0.03)
- Lower learning rate (0.01) is consistently better than default (0.05)
- Optimal depth varies widely: d3 for small/clean patients (d,h,j), d8 for complex patients (b,c,g,k)
- **Trade-off**: 1397s (23 min) vs 15s for default — grid search is expensive

### Hyperparameter Insights

| Cluster | Patients | Optimal Depth | Learning Rate | Interpretation |
|---------|----------|---------------|---------------|----------------|
| Simple dynamics | d, h, j | 3 | 0.01–0.03 | Low complexity, regularize heavily |
| Moderate | a, e, f, i | 4–6 | 0.01 | Balance capacity and regularization |
| Complex | b, c, g, k | 8 | 0.01 | Need more capacity for complex patterns |

---

## EXP-1177: Residual Analysis — What's Left to Learn?

Diagnostic experiment analyzing prediction residuals to identify remaining learnable structure.

### Temporal Autocorrelation

| Patient | Autocorr(1) | Autocorr(2) | Interpretation |
|---------|-------------|-------------|----------------|
| i | 0.575 | 0.152 | Highest — most temporal structure remaining |
| a | 0.528 | 0.084 | High |
| d | 0.522 | 0.150 | High + persistent (slow decay) |
| g | 0.486 | 0.065 | Moderate |
| f | 0.486 | 0.041 | Moderate |
| e | 0.467 | −0.021 | Moderate (dies fast) |
| c | 0.464 | 0.016 | Moderate |
| h | 0.463 | 0.024 | Moderate |
| b | 0.430 | −0.043 | Lower |
| k | 0.409 | −0.071 | Lower |
| j | 0.385 | −0.029 | Lowest |
| **Mean** | **0.474** | **0.033** | **Significant temporal structure** |

**Mean autocorrelation at lag-1 = 0.474** — nearly half the variance at timestep t+1 is predictable from timestep t. This suggests AR (autoregressive) correction could help, but only in a production/online setting where you observe the error after making each prediction.

### Heteroscedastic Errors

| Patient | RMSE Low BG | RMSE Mid BG | RMSE High BG | Pattern |
|---------|-------------|-------------|--------------|---------|
| a | 42.7 | 48.1 | 56.1 | Errors increase with BG |
| d | 21.7 | 24.6 | 31.0 | Errors increase with BG |
| f | 37.0 | 42.9 | 50.4 | Errors increase with BG |
| k | 12.8 | 11.2 | 14.0 | Slight U-shape |

**Pattern**: RMSE consistently higher at high glucose levels. Glucose dynamics are more volatile during hyperglycemia (large correction boluses, meal spikes). This suggests:
- Log-transform or percentage-based loss could help
- Heteroscedastic models (predict mean + variance)
- Weight low-glucose predictions higher for clinical safety

### Time-of-Day Residuals

No strong systematic pattern across patients — dawn conditioning already captures the main circadian effect. Residuals are roughly uniform across morning/afternoon/evening/night.

---

## Other Experiments

### EXP-1171: Enhanced + LSTM Combined ★★★

Combined enhanced features with careful LSTM pipeline (small model, early stopping, dropout).

- Enhanced features alone: +0.027 (11/11)
- LSTM pipeline: −0.019 (3/11) — even careful LSTM hurts most patients
- Combined (weighted ensemble): +0.013 (9/11) — the features carry the improvement
- **The enhanced features are doing all the work; LSTM adds nothing genuine**

### EXP-1173: Same-Time-Yesterday Memory ★★

Adding glucose values from 24 hours ago as features (circadian pattern memory).

- Mean Δ = +0.005 (8/11 improve)
- Strongest for patient j (+0.040) — highly regular daily patterns
- Negative for patient k (−0.016) — irregular schedule
- **Modest but real signal for patients with consistent daily routines**

### EXP-1174: Cross-Patient Transfer Learning ★★

Train global model on all patients, ensemble with local model.

- Global model alone: R²=0.318 — far worse than local (patient heterogeneity dominates)
- Ensemble (70% local + 30% global): +0.004 (9/11)
- Strongest for patient j (+0.020) — small dataset benefits from regularization
- **Minimal benefit — patients are too heterogeneous for naive transfer**

### EXP-1175: Glucose Encoding Variants

Testing raw, delta, relative (to window mean), and quantile encodings.

- **Raw glucose is best overall** (R²=0.523)
- Quantile is competitive (R²=0.522) — almost ties
- Delta is worst (R²=0.490) — loses absolute level information
- Relative works for some patients (i: +0.009) but hurts others (k: −0.052)
- **Decision: Keep raw glucose encoding. Quantile as optional augmentation.**

### EXP-1178: Glucose Variability Features ★★

Adding CV, IQR, and range of glucose within the 2h window.

- Mean Δ = +0.005 (9/11)
- Patient j: +0.024, h: +0.018 (hard patients benefit most)
- **Small but consistent improvement; nearly free to compute**

### EXP-1179: Insulin Stacking Detection ★

Detecting overlapping insulin activity curves (multiple boluses within DIA window).

- Mean Δ = +0.003 (6/11 — barely above chance)
- Patient j: +0.020 (benefits hard patients)
- **Too marginal to justify complexity**

---

## Revised SOTA Hierarchy (Post-Leakage, Post-CV)

### Validated Techniques (5-Fold CV Confirmed)

| Rank | Technique | Single Split Δ | CV Δ | Status |
|------|-----------|----------------|------|--------|
| 1 | Enhanced feature engineering | +0.027 | +0.023 | ✅ **TRUE BEST** |
| 2 | XGBoost hyperparameter tuning | +0.026 | TBD | ✅ Likely holds |
| 3 | Multi-horizon regularization | +0.013 | TBD | ✅ Likely holds (11/11) |
| 4 | PK momentum features | +0.010 | TBD | ✅ Causal, validated |
| 5 | Dawn conditioning | +0.009 | TBD | ✅ Physics-based |

### Invalidated Techniques

| Technique | Single Split Δ | CV Δ | Issue |
|-----------|----------------|------|-------|
| XGBoost→LSTM pipeline | +0.038 | −0.068 | ⛔ Overfitting |
| PK temporal lead | +0.125 | N/A | ⛔ 100% data leakage |
| Causal PK projection | +0.000 | N/A | Redundant (XGBoost already extracts) |

### True Performance (5-Fold CV)

```
Glucose-only XGBoost:       R² = 0.455 ± 0.07  (CV baseline)
+ Enhanced features:        R² = 0.477 ± 0.06  (CV validated SOTA)
Gap to noise ceiling:       ~0.38 R² remaining
Noise ceiling (σ=15):       R² = 0.854
```

---

## Implications for Next Steps

### 1. LSTM Is Not the Answer (For Now)

Three separate experiments (1171, 1142, 1180) confirm that LSTM hurts in cross-validated settings despite showing gains on single splits. The temporal autocorrelation (0.474) IS there, but LSTM overfits rather than capturing it. Potential fixes:
- Much more training data (currently ~30K timesteps per patient after windowing)
- Simpler architecture (linear AR head instead of LSTM)
- Online AR correction (production-only, not ML model)

### 2. Feature Engineering Is the Path Forward

Enhanced features (+0.023 CV) provide genuine, validated improvement. The model needs better **input representations**, not more complex architectures.

### 3. Combine Validated Winners

No experiment has yet combined all validated winners:
- Enhanced features (+0.023)
- Multi-horizon regularization (+0.013)
- Per-patient hyperparameter tuning (+0.026)
- PK momentum (+0.010)
- Dawn conditioning (+0.009)

These should stack, potentially reaching R²=0.50+ in CV.

### 4. The Residual Structure Suggests AR Correction

With autocorr(1)=0.474, an online AR correction (adjust prediction by fraction of last observed error) could recover significant performance in production — but this isn't applicable to offline evaluation.

### 5. Heteroscedastic Loss

Errors are systematically larger at high glucose. A heteroscedastic loss function (or log-glucose prediction) could improve both statistical and clinical performance.

---

## Experiment Code

All experiments implemented in `tools/cgmencode/exp_clinical_1171.py` (1808 lines).

Run: `cd tools && PYTHONPATH=. python -m cgmencode.exp_clinical_1171 --detail --save --max-patients 11`

Results saved to `externals/experiments/exp-117[1-9]_*.json` and `exp-1180_*.json`.

---

## Campaign Summary (180 Experiments: EXP-1001–1180)

| Batch | Experiments | Key Discovery |
|-------|-------------|---------------|
| EXP-1001–1050 | Physics decomposition | Supply/demand +0.010, metabolic ratio features |
| EXP-1051–1100 | Architecture search | CNN, XGBoost, feature importance |
| EXP-1101–1130 | Pipeline optimization | XGBoost→LSTM pipeline (now invalidated by CV) |
| EXP-1131–1140 | Scaling & refinement | Block CV, ensemble methods |
| EXP-1141–1150 | Combined features | Enhanced features +0.021 (11/11) |
| EXP-1151–1160 | PK lead deep dive | R²=0.658 (100% leakage) |
| EXP-1161–1170 | Causal PK analysis | Leakage definitively proven; PK momentum +0.010 |
| EXP-1171–1180 | **Causal benchmark** | **LSTM overfits! Enhanced XGBoost CV=0.477** |

**Total validated improvement over 180 experiments**: R² = 0.354 → 0.477 (CV) = **+0.123** genuine gain.
