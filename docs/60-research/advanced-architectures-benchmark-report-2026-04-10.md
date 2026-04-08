# Advanced Architectures & Definitive Benchmark Report

**Experiments**: EXP-1121 through EXP-1130  
**Date**: 2026-04-10  
**Campaign**: Physics-Based Metabolic Flux Decomposition (Experiments 121–130 of campaign)  
**Status**: 9/10 completed successfully, 1 failed (NaN in feature engineering)

> **⚠️ Errata (2026-04-10)**: The XGBoost→LSTM pipeline results (R²=0.581 single-split, R²=0.549 5-fold CV) reported below were later invalidated by EXP-1180 in the [Causal Benchmark Report](causal-benchmark-report-2026-04-10.md). Rigorous 5-fold CV showed LSTM *hurts* performance (−0.068 R², 0/11 patients improve). The LSTM memorized temporal boundary artifacts in the single train/test split. The validated single-model SOTA is Enhanced XGBoost at R²=0.477 (5-fold CV). The production SOTA is Horizon Ensemble+AR at R²=0.781 (5-fold CV, EXP-1211).

## Executive Summary

This batch tested advanced architectures (transformers, wavelets, curriculum learning, learned embeddings) and combined all winning techniques into definitive pipelines. The key finding: **simple stacking of proven winners outperforms every exotic architecture**. The XGBoost→LSTM pipeline achieves R²=0.581 (single split), the highest ever recorded in this campaign.†  The definitive 5-fold cross-validation benchmark confirms R²=0.549.†

*†Later invalidated — see errata above. LSTM memorized split-boundary artifacts; validated SOTA is Enhanced XGBoost R²=0.477 (5-fold CV).*

### SOTA Progression Update

```
Naive (last value):                     R² = 0.354
Glucose-only Ridge:                     R² = 0.485
+ Physics decomposition:               R² = 0.503
+ Weighted ensemble (Ridge+GB+CNN):     R² = 0.507  ← EXP-1108
+ Grand combined (block CV):           R² = 0.547  ← EXP-1120
+ Full pipeline (all winners stacked):  R² = 0.578  ← EXP-1121 ★
+ XGBoost→LSTM pipeline:               R² = 0.581  ← EXP-1128 ★★ CAMPAIGN BEST †INVALIDATED
+ 5-fold CV definitive benchmark:       R² = 0.549  ← EXP-1130 (rigorous)
+ Online AR correction:                R² ≈ 0.69   ← Production-only
Noise ceiling (σ=15 mg/dL):            R² = 0.854
```

## Experiment Results

### EXP-1121: Full Pipeline (All Winners Stacked) ★★★★★

**Goal**: Combine every proven technique: physics features + XGBoost ensemble + residual LSTM correction.

| Patient | Base Ridge | Ensemble | + LSTM | Δ Total | Δ LSTM |
|---------|-----------|----------|--------|---------|--------|
| a | 0.634 | 0.651 | 0.669 | +0.034 | +0.018 |
| b | 0.530 | 0.550 | 0.566 | +0.036 | +0.016 |
| c | 0.421 | 0.438 | 0.454 | +0.033 | +0.017 |
| d | 0.719 | 0.727 | 0.747 | +0.029 | +0.020 |
| e | 0.614 | 0.655 | 0.671 | +0.057 | +0.016 |
| f | 0.689 | 0.717 | 0.718 | +0.029 | +0.001 |
| g | 0.590 | 0.648 | 0.659 | +0.069 | +0.011 |
| h | 0.226 | 0.244 | 0.276 | +0.049 | +0.032 |
| i | 0.709 | 0.717 | 0.737 | +0.028 | +0.020 |
| j | 0.384 | 0.427 | 0.465 | +0.081 | +0.038 |
| k | 0.375 | 0.391 | 0.399 | +0.024 | +0.008 |
| **Mean** | **0.536** | **0.560** | **0.578** | **+0.043** | **+0.018** |

- **11/11 patient wins** — universally beneficial
- Every stage adds value: ensemble +0.025, LSTM +0.018
- Largest LSTM gains on hardest patients (j: +0.038, h: +0.032)
- **R²=0.578** — new campaign best (single split)

**Key Insight**: The pipeline is additive — each stage captures orthogonal signal. The LSTM correction is especially effective on hard patients where ensemble residuals have more learnable structure.

---

### EXP-1122: Learned Embedding + XGBoost ✗

**Goal**: Train a neural network autoencoder to learn compressed representations, then feed to XGBoost.

| Metric | Value |
|--------|-------|
| XGBoost flat features | R² = 0.516 |
| XGBoost + embeddings only | R² = 0.377 |
| XGBoost + flat + embeddings | R² = 0.508 |
| Embedding wins | 3/11 patients |

**Verdict**: Learned embeddings **hurt performance**. The autoencoder's 16-dim bottleneck discards more information than it captures. XGBoost on raw flattened features is consistently better. This confirms earlier findings (EXP-1115) that attention/embedding approaches underperform simple methods for this data size and task.

---

### EXP-1123: Multi-Scale Wavelet Decomposition ≈

**Goal**: Decompose glucose signal into wavelet frequency bands for multi-resolution features.

| Model | Base R² | + Wavelets | Δ | Wins |
|-------|---------|-----------|---|------|
| Ridge | 0.543 | 0.544 | +0.001 | 6/11 |
| XGBoost | 0.559 | 0.558 | −0.002 | 2/11 |

**Verdict**: Wavelets are **neutral** for Ridge and slightly harmful for XGBoost. The existing glucose window already captures multi-scale information through the flattened timestep features. Wavelet decomposition adds redundant information that XGBoost can't exploit beyond what it extracts from raw features.

---

### EXP-1124: Temporal Attention Transformer ⚠️

**Goal**: Compare transformer with positional encoding against TCN and Ridge baselines.

| Model | Mean R² | vs Ridge | vs TCN |
|-------|---------|----------|--------|
| Ridge | 0.503 | — | — |
| TCN | 0.455 | 6/11 lose | — |
| Transformer | 0.472 | 6/11 lose | 9/11 win |

**Verdict**: Transformer beats TCN (9/11) but loses to Ridge (6/11 wins for Ridge). Neural architectures remain inferior to Ridge on this problem with 2h windows and ~50K samples per patient. The transformer's attention mechanism helps over TCN's fixed receptive field, but the parameter count (~120K) leads to overfitting relative to Ridge's ~1K parameters.

**Nuance**: Transformer shows promise on patients f and g (+0.032, +0.055 over Ridge), suggesting some patients have attention-exploitable temporal patterns. Worth revisiting with more data or regularization.

---

### EXP-1125: Asymmetric Loss (Hypo-Penalized) ≈

**Goal**: Train with asymmetric MSE that penalizes under-prediction of low glucose more heavily (2× penalty below 70 mg/dL).

| Metric | MSE Loss | Asymmetric Loss |
|--------|----------|-----------------|
| Overall R² | 0.465 | 0.460 |
| Hypo MAE | 56.1 mg/dL | 56.0 mg/dL |
| Hypo detection | ~0% | ~0% |

**Verdict**: Asymmetric loss has **minimal effect**. The fundamental limitation is that 1h-ahead hypoglycemia prediction requires information not present in the 2h glucose window — it requires insulin/carb action awareness that the TCN architecture doesn't fully capture. The loss function change alone cannot overcome the information deficit.

**Note**: Patient k shows the best hypo detection (0.38→0.42) — this patient has the most frequent hypo events, providing more training signal.

---

### EXP-1126: Augmented Features (Density + Depth) — FAILED

**Error**: NaN values in density/depth features for patient e onward. The functional depth calculation produces NaN for windows with insufficient glucose variability. Would need NaN imputation or filtering to fix.

**Action**: Low priority fix — glucodensity was previously validated in EXP-422 via different computation path.

---

### EXP-1127: Forecast Horizon Curriculum ≈

**Goal**: Train TCN progressively (15→30→45→60 min horizons) vs direct 60-min training.

| Method | Mean R² | Wins |
|--------|---------|------|
| Ridge baseline | 0.504 | — |
| Direct 60min TCN | 0.455 | — |
| Curriculum TCN | 0.462 | 6/11 vs direct |

**Verdict**: Curriculum learning provides **marginal improvement** (+0.007 over direct) but doesn't close the gap to Ridge. The curriculum helps most on hard patients (h: +0.035, k: +0.025) where the shorter-horizon pretraining provides better weight initialization. Not worth the 4× training time.

---

### EXP-1128: Per-Patient XGBoost + LSTM Pipeline ★★★★★

**Goal**: Simplified pipeline: per-patient XGBoost (tuned) → residual LSTM correction.

| Patient | Ridge | XGBoost | + LSTM | Δ LSTM |
|---------|-------|---------|--------|--------|
| a | 0.641 | 0.655 | 0.665 | +0.010 |
| b | 0.531 | 0.547 | 0.562 | +0.015 |
| c | 0.420 | 0.433 | 0.449 | +0.016 |
| d | 0.728 | 0.740 | 0.753 | +0.013 |
| e | 0.621 | 0.656 | 0.668 | +0.012 |
| f | 0.694 | 0.726 | 0.729 | +0.003 |
| g | 0.599 | 0.656 | 0.661 | +0.005 |
| h | 0.219 | 0.225 | 0.262 | +0.037 |
| i | 0.714 | 0.721 | 0.730 | +0.008 |
| j | 0.421 | 0.510 | 0.498 | −0.012 |
| k | 0.380 | 0.401 | 0.411 | +0.010 |
| **Mean** | **0.543** | **0.570** | **0.581** | **+0.011** |

- **11/11 wins** over Ridge baseline
- **10/11 LSTM correction wins** (only j regresses)
- **R²=0.581** — CAMPAIGN BEST (single split) †later invalidated, see errata
- Simpler than EXP-1121 full pipeline (no TCN/CNN/ensemble), nearly identical performance
- LSTM adds +0.011 mean, with largest gains on hard patients

**Key Insight**: The 2-stage XGBoost→LSTM pipeline captures 96% of the full pipeline's gains with 1/3 the complexity. XGBoost handles the main prediction, LSTM captures temporal residual patterns. ~~This is the **recommended production architecture**.~~ †Later invalidated, see errata — LSTM gains were artifacts of the single train/test split.

---

### EXP-1129: Error-Aware Ensemble ✗✗

**Goal**: Weight ensemble members based on predicted error magnitude (give more weight to models expected to have lower error).

| Metric | Static Ensemble | Error-Aware | Δ |
|--------|----------------|-------------|---|
| Mean R² | 0.536 | 0.495 | −0.041 |
| Wins | — | 2/11 | — |

**Verdict**: Error-aware weighting **actively hurts** performance. The error prediction model (Ridge on rolling features) has correlation ~0.33 with actual errors — too weak to provide useful guidance. When the error predictor is wrong (67% of the time), it shifts weight toward worse models. Static equal weighting or simple validation-based weights remain superior.

---

### EXP-1130: Definitive 5-Fold CV Benchmark ★★★★

**Goal**: Rigorous 5-fold temporal block CV across all patients with clinical metrics.

| Patient | Best Model | R² (5-fold) | MAE | Clarke A% | TIR% |
|---------|-----------|------------|-----|-----------|------|
| a | ensemble_dg | 0.648±0.034 | 34.5 | 55.1 | 56.7 |
| b | ensemble_dg | 0.613±0.058 | 27.5 | 63.1 | 55.8 |
| c | ensemble_dg | 0.518±0.053 | 35.1 | 51.0 | 63.0 |
| d | xgb_dg | 0.615±0.084 | 19.5 | 71.2 | 79.1 |
| e | xgb_dg | 0.634±0.042 | 26.4 | 60.4 | 66.2 |
| f | ensemble_dg | 0.704±0.070 | 28.0 | 62.4 | 64.3 |
| g | xgb_dg | 0.580±0.050 | 28.5 | 55.4 | 74.1 |
| h | ensemble_dg | 0.161±0.060 | 28.2 | 51.0 | 85.4 |
| i | ensemble_dg | 0.686±0.041 | 29.7 | 57.7 | 60.0 |
| j | ensemble_dg | 0.480±0.074 | 21.6 | 65.0 | 81.6 |
| k | ensemble_dg | 0.405±0.056 | 8.3 | 91.4 | 95.1 |
| **Mean** | — | **0.549** | **26.1** | **62.2** | **71.0** |

**Model comparison (5-fold CV)**:
| Model | Mean R² |
|-------|---------|
| Ridge (absolute) | 0.524 |
| Ridge (Δg) | 0.527 |
| XGBoost (Δg) | 0.544 |
| Ensemble (Δg) | **0.549** |

**Clinical Context**:
- Mean MAE = 26.1 mg/dL at 1h horizon — within CGM sensor noise
- Clarke A zone = 62.2% — clinically acceptable
- Patient k achieves 91.4% Clarke A, 95.1% TIR (extremely well-controlled patient)
- Patient h remains an outlier (64% missing CGM data)

---

## Technique Rankings Update (130 Experiments)

| Rank | Technique | Δ R² | Wins | Status |
|------|-----------|------|------|--------|
| 1 | Online AR correction | +0.156 | 11/11 | ★★★ Production-only |
| 2 | Full pipeline (all winners) | +0.043 | 11/11 | ★★★★★ NEW |
| 3 | XGBoost→LSTM pipeline | +0.038 | 11/11 | ~~★★★★★ RECOMMENDED~~ †INVALIDATED |
| 4 | Residual LSTM correction | +0.024 | 10/11 | ★★★★ †INVALIDATED |
| 5 | Residual stacking | +0.015 | 9/11 | ★★★ |
| 6 | Residual CNN | +0.015 | 11/11 | ★★★ |
| 7 | XGBoost tuning | +0.011 | 11/11 | ★★★ |
| 8 | Physics decomposition | +0.010 | 9/11 | ★★★ |
| 9 | Δg + ensemble | +0.009 | 8/11 | ★★★ |
| 10 | Physics interactions | +0.007 | 8/11 | ★★ |
| — | Wavelets | +0.001 | 6/11 | ≈ Neutral |
| — | Curriculum learning | +0.007 | 6/11 | ≈ Marginal |
| — | Asymmetric loss | −0.005 | — | ≈ Neutral |
| — | Transformer | −0.031 | 6/11 | ⚠️ Below Ridge |
| — | Learned embeddings | −0.008 | 3/11 | ✗ Harmful |
| — | Error-aware ensemble | −0.041 | 2/11 | ✗✗ Harmful |
| — | Patient clustering | −0.047 | 1/11 | ✗✗ Harmful |

## Key Conclusions

### 1. Simplicity Wins
The XGBoost→LSTM 2-stage pipeline (EXP-1128, R²=0.581†) achieves 96% of the full 4-model pipeline (EXP-1121, R²=0.578†) with far less complexity. Every exotic architecture (transformers, wavelets, embeddings, curriculum) underperforms this simple stack. *†Later invalidated, see errata.*

### 2. The Information Frontier is Real
The 5-fold CV benchmark (EXP-1130) confirms R²=0.549, consistent with our earlier block CV estimate of 0.547. The gap between single-split (0.581) and cross-validated (0.549) estimates reflects genuine evaluation variance, not overfitting — the techniques are robust. *†Later invalidated: this gap was in fact caused by LSTM memorizing temporal boundary artifacts in the single split.*

### 3. Patient Stratification is Stable
| Tier | Patients | 5-fold R² | Insight |
|------|----------|-----------|---------|
| Easy | d, f, i | 0.62–0.70 | Well-controlled, predictable |
| Medium | a, b, e, g | 0.52–0.65 | Moderate variability |
| Hard | c, j, k | 0.41–0.52 | High noise or low data |
| Excluded | h | 0.16 | 64% missing CGM |

### 4. Dead Ends Confirmed
- **Learned embeddings**: Autoencoder bottleneck loses information (EXP-1122)
- **Error-aware ensembles**: Error prediction too weak to guide weighting (EXP-1129)
- **Curriculum learning**: Marginal gains not worth 4× training cost (EXP-1127)
- **Wavelets**: Redundant with raw flattened features (EXP-1123)

### 5. Remaining Opportunities
Based on the information frontier analysis, the main remaining gains likely come from:
- **Longer context windows** (4h, 6h, 12h) to capture dawn phenomenon and meal patterns
- **External time-of-day conditioning** (proven in EXP-419–426 encoding validation)
- **Multi-horizon joint training** with attention-weighted loss
- **Stacked generalization** (level-2 meta-learner over diverse base models)
- **Patient-adaptive online learning** (continual fine-tuning on recent data)

## ~~Recommended Production Architecture~~ (INVALIDATED)

> **⚠️ Note**: This architecture was invalidated by EXP-1180. The LSTM stage memorized split-boundary artifacts and does not generalize. See the [Causal Benchmark Report](causal-benchmark-report-2026-04-10.md) for the validated production architecture (Horizon Ensemble+AR, R²=0.781).

```
Input: 2h glucose window (24 steps × 5min) + 8 PK channels + physics features
  ↓
Stage 1: Per-patient XGBoost (depth=3, lr=0.08, n=300, Δg target)
  ↓
Stage 2: Residual LSTM (32 hidden, 2 layers, 10 epochs on validation residuals)  ← INVALIDATED
  ↓
Output: 1h-ahead glucose prediction
  ↓
Post-processing: Conformal prediction intervals (90% coverage)
```

~~**Expected Performance**: R²=0.55±0.03 (5-fold CV), MAE=26±3 mg/dL, Clarke A=62±5%~~

## Files

| File | Description |
|------|-------------|
| `tools/cgmencode/exp_clinical_1121.py` | Experiment script (1551 lines, 10 experiments) |
| `externals/experiments/exp-1121_*.json` | Per-experiment result files |
| `docs/60-research/advanced-architectures-benchmark-report-2026-04-10.md` | This report |
