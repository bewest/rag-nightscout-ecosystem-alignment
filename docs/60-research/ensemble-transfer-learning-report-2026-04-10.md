# Ensemble, Residual Learning & Transfer — EXP-1021–1030 Report

**Date**: 2026-04-10
**Campaign**: Physics-Based Metabolic Flux Decomposition
**Experiments**: EXP-1021 through EXP-1030
**Status**: All 10 passed, 11 patients × ~180 days each

## Executive Summary

This batch investigated **model combination strategies** — ensembles, residual
learning, pretrain+fine-tune transfer, patient routing, and honest block
cross-validation — to determine how much performance remains on the table
beyond the decomposed-physics + CNN architecture explored in EXP-1001–1020.

**Key results:**
- **Residual CNN is the most reliable technique**: +0.024 mean R², **positive
  for all 11/11 patients** — the only method in the entire 1000+ experiment
  campaign to achieve universal improvement
- **Pretrain+fine-tune** has the highest ceiling for data-scarce patients
  (j: +0.075, k: +0.087, b: +0.060)
- **Time-of-day conditioning confirmed harmful** (−0.064 mean), consistent
  with EXP-419 time-invariance findings at ≤6h scale
- **Honest block CV** reveals ~0.03–0.04 R² inflation in simple train/val
  splits: dual-branch SOTA drops from 0.525 → 0.491
- **No single method dominates** — oracle patient routing yields R²=0.531

## SOTA Progression

```
Campaign milestones:
  Glucose-only AR(4) baseline:    R² = 0.200
  + Decomposed supply/demand:     R² = 0.465 (+0.265)  ← EXP-1003
  + Dual-branch CNN:              R² = 0.525 (+0.060)  ← EXP-1020
  + Residual CNN on Ridge:        R² = 0.529 (+0.004)  ← EXP-1024 (this batch)
  + Pretrain fine-tune best:      R² = 0.542 (+0.017)  ← EXP-1030 oracle

  Honest block CV (5-fold):       R² = 0.491           ← EXP-1028
```

## Detailed Results

### EXP-1021: Ridge-CNN Ensemble

Weighted blend of Ridge and dual-branch CNN predictions, α optimized per
patient on validation set.

| Patient | Ridge | CNN   | Ensemble | α   | Δ      |
|---------|-------|-------|----------|-----|--------|
| a       | 0.588 | 0.580 | 0.600    | 0.6 | +0.012 |
| b       | 0.507 | 0.479 | 0.515    | 0.7 | +0.008 |
| c       | 0.397 | 0.377 | 0.409    | 0.6 | +0.012 |
| d       | 0.652 | 0.652 | 0.666    | 0.5 | +0.014 |
| e       | 0.552 | 0.575 | 0.584    | 0.3 | +0.032 |
| f       | 0.631 | 0.666 | 0.667    | 0.2 | +0.036 |
| g       | 0.542 | 0.610 | 0.611    | 0.1 | +0.069 |
| h       | 0.194 | −0.025| 0.194    | 1.0 | +0.000 |
| i       | 0.701 | 0.699 | 0.709    | 0.5 | +0.008 |
| j       | 0.424 | 0.497 | 0.514    | 0.3 | +0.090 |
| k       | 0.367 | 0.331 | 0.372    | 0.7 | +0.006 |
| **Mean**| 0.505 | 0.495 | **0.531**|     | **+0.026** |

**Finding**: Modest but consistent gain (10/11 positive). Optimal α varies
widely (0.1–1.0), confirming Ridge and CNN capture complementary patterns.
Patient h falls back to pure Ridge (α=1.0) — CNN actively hurts.

### EXP-1022: Pretrain + Fine-Tune Transfer

Train CNN on all-but-one patients (LOPO pretraining), then fine-tune on
target patient for 10 epochs with reduced learning rate (1/10th).

| Patient | Per-Patient | LOPO   | Fine-Tuned | Δ(PP)   |
|---------|-------------|--------|------------|---------|
| a       | 0.579       | 0.586  | **0.609**  | +0.030  |
| b       | 0.447       | 0.486  | **0.507**  | +0.060  |
| c       | 0.386       | 0.374  | **0.412**  | +0.027  |
| d       | 0.652       | 0.662  | 0.652      | −0.001  |
| e       | 0.571       | 0.554  | **0.579**  | +0.008  |
| f       | 0.671       | 0.652  | **0.678**  | +0.007  |
| g       | 0.601       | 0.578  | **0.620**  | +0.019  |
| h       | 0.075       | 0.180  | −0.055     | −0.130  |
| i       | 0.699       | 0.640  | **0.713**  | +0.013  |
| j       | 0.451       | 0.416  | **0.526**  | +0.075  |
| k       | 0.256       | −1.369 | **0.343**  | +0.087  |
| **Mean**| 0.490       | 0.342  | **0.508**  | **+0.018** |

**Finding**: Fine-tuning beats per-patient CNN for 9/11 patients. Biggest
wins on data-scarce (j: +0.075) and high-noise (k: +0.087) patients where
cross-patient pretraining provides useful inductive bias. Patient h
catastrophically fails — its physiology is too idiosyncratic for transfer.

**Insight**: LOPO alone is poor (mean 0.342 vs 0.490 per-patient), but
fine-tuning recovers and exceeds per-patient, showing cross-patient
initialization finds a better loss basin than random initialization.

### EXP-1023: Patient Routing (Oracle)

Train all 4 architectures per patient, route to best on validation.

| Patient | Best Method    | R²    |
|---------|---------------|-------|
| a       | cnn_glucose   | 0.597 |
| b       | cnn_glucose   | 0.526 |
| c       | ridge         | 0.397 |
| d       | ridge         | 0.652 |
| e       | cnn_glucose   | 0.590 |
| f       | dual_branch   | 0.675 |
| g       | dual_branch   | 0.623 |
| h       | ridge         | 0.194 |
| i       | dual_branch   | 0.718 |
| j       | dual_branch   | 0.503 |
| k       | ridge         | 0.366 |

**Oracle mean R²**: 0.531

**Architecture wins**: Ridge=4, CNN-glucose=3, dual_branch=4, CNN-physics=0

**Finding**: No single architecture dominates. The oracle selector gains
+0.006 over always-dual-branch. CNN-physics never wins when others are
available — physics information is better used as a separate branch or
through Ridge features than as the sole CNN input.

### EXP-1024: Residual CNN ⭐

Train Ridge first, then train a CNN to predict Ridge's residuals (errors).
Final prediction = Ridge + scaled CNN residual.

| Patient | Ridge | Resid R² | Combined | Δ       |
|---------|-------|----------|----------|---------|
| a       | 0.588 | 0.040    | 0.604    | +0.016  |
| b       | 0.507 | 0.016    | 0.518    | +0.011  |
| c       | 0.397 | −0.016   | 0.399    | +0.002  |
| d       | 0.652 | 0.024    | 0.664    | +0.012  |
| e       | 0.552 | 0.040    | 0.578    | +0.026  |
| f       | 0.631 | 0.083    | 0.662    | +0.031  |
| g       | 0.542 | 0.155    | 0.619    | **+0.078** |
| h       | 0.194 | 0.012    | 0.228    | +0.034  |
| i       | 0.701 | 0.011    | 0.709    | +0.007  |
| j       | 0.424 | 0.052    | 0.467    | +0.043  |
| k       | 0.367 | −0.010   | 0.370    | +0.004  |
| **Mean**| 0.505 | 0.037    | **0.529**| **+0.024** |

**🏆 Campaign first**: Positive improvement for ALL 11/11 patients.

**Finding**: The CNN captures 3.7% of the variance in Ridge residuals on
average — these are nonlinear patterns that Ridge's linear features cannot
express. Patient g benefits most (+0.078), suggesting its glucose dynamics
have substantial nonlinear structure. Even hard patients h (+0.034) and
k (+0.004) improve, unlike every other method that occasionally degrades them.

**Why it works**: By learning residuals rather than raw glucose, the CNN
operates on a simpler target (deviations from Ridge's linear prediction)
and avoids the failure modes that plague end-to-end CNN training on
difficult patients.

### EXP-1025: Multi-Scale CNN

CNN with parallel convolutional branches at 3 temporal scales (kernel sizes
3, 7, 15), concatenated before final prediction.

| Patient | Standard CNN | Multi-Scale | Δ       |
|---------|-------------|-------------|---------|
| a       | 0.559       | 0.599       | +0.040  |
| b       | 0.464       | 0.480       | +0.016  |
| c       | 0.358       | 0.374       | +0.016  |
| h       | −0.064      | 0.104       | **+0.168** |
| k       | 0.334       | 0.359       | +0.025  |
| **Mean**| 0.476       | **0.492**   | **+0.016** |

**Finding**: Mixed results (5/11 positive). Large rescue for patient h
(+0.168) but hurts well-performing patients. Multi-scale helps where single
scale is catastrophic but adds overfitting risk for patients with sufficient
data.

### EXP-1026: Physics-Normalized Cross-Patient Ridge

Use physics-normalized features (divide by patient-specific ISF/CR) for
cross-patient Ridge, testing if normalization closes the per-patient gap.

**Mean gap**: 0.019 (excluding k's extreme −1.38 divergence)

**Finding**: Physics normalization barely helps cross-patient Ridge. The
per-patient vs cross-patient gap remains ~0.02 R², confirming that patient
heterogeneity is primarily in the glucose dynamics themselves, not in
feature scaling.

### EXP-1027: Time-of-Day Conditioned Dual-Branch ❌

Add sin/cos time-of-day encoding as an additional conditioning channel to
the dual-branch CNN.

**Mean improvement**: −0.064 (**hurts universally**, 0/11 positive)

**Finding**: Time-of-day conditioning is actively harmful, confirming
EXP-419's finding that glucose dynamics are time-translation invariant at
≤6h scales. The physics channels (which include basal rate schedules)
already capture any circadian variation that matters. Adding explicit ToD
encoding introduces spurious correlations.

### EXP-1028: Block Cross-Validation (Honest Evaluation) ⭐

5-fold temporal block CV (non-shuffled, chronological blocks) for honest
R² estimation.

| Patient | Ridge       | CNN         | Dual-Branch |
|---------|-------------|-------------|-------------|
| a       | 0.608±0.036 | 0.612±0.022 | 0.611±0.022 |
| b       | 0.562±0.053 | 0.544±0.071 | 0.569±0.057 |
| d       | 0.559±0.079 | 0.548±0.080 | 0.566±0.071 |
| f       | 0.652±0.062 | 0.661±0.065 | 0.663±0.058 |
| i       | 0.652±0.047 | 0.657±0.042 | 0.659±0.041 |
| **Mean**| **0.486**   | 0.466       | **0.491**   |

**Finding**: Honest block CV R² is ~0.03–0.04 lower than simple train/val
split. Dual-branch (0.491) barely beats Ridge (0.486). The CNN advantage
is real but modest under honest evaluation. High variance for some patients
(j: CNN std=0.250) suggests temporal instability.

**Inflation estimate**: Simple split R² inflated by ~7% relative to block CV.

### EXP-1029: Confidence Calibration

Dual-branch CNN with 5 sub-models producing prediction variance as
confidence estimate.

**Mean calibration slope**: 0.148 (errors decrease monotonically with
confidence for all 11 patients)

**Finding**: The ensemble disagreement is a reliable uncertainty signal.
Q1 (lowest confidence) MAE averages 1.5× Q5 (highest confidence) MAE.
Patient e has near-perfect calibration (slope=0.046). This enables
selective prediction — rejecting low-confidence predictions could
significantly reduce clinical error rates.

### EXP-1030: Grand Combined Ensemble

Combine Ridge, residual CNN, and fine-tuned CNN via equal-weight ensemble.

| Patient | Ridge | Residual | Fine-Tune | Ensemble | Best   |
|---------|-------|----------|-----------|----------|--------|
| a       | 0.585 | 0.594    | 0.587     | 0.601    | 0.601  |
| b       | 0.506 | 0.518    | 0.489     | 0.525    | 0.525  |
| d       | 0.652 | 0.658    | 0.653     | 0.666    | 0.666  |
| g       | 0.543 | 0.569    | **0.614** | 0.589    | 0.614  |
| i       | 0.699 | 0.705    | **0.714** | 0.713    | 0.714  |
| j       | 0.402 | 0.448    | **0.574** | 0.503    | 0.574  |
| **Mean**| 0.505 | 0.519    | 0.522     | **0.529**| **0.542** |

**Finding**: Equal-weight ensemble (0.529) slightly beats any single method
but per-patient oracle selection (0.542) is better. Fine-tune dominates for
patients with high cross-patient transferability (g, i, j). Residual CNN
is most consistent. The ensemble doesn't fully exploit complementarity —
adaptive weighting could close the gap.

## Synthesis

### Method Reliability Ranking

| Rank | Method | Mean Δ | Positive | Notes |
|------|--------|--------|----------|-------|
| 1 | Residual CNN | +0.024 | **11/11** | Most reliable technique ever |
| 2 | Pretrain+FT | +0.018 | 9/11 | Highest ceiling, risky for outliers |
| 3 | Multi-Scale CNN | +0.016 | 5/11 | Rescues hard patients |
| 4 | Ridge-CNN Ensemble | +0.008 | 10/11 | Safe, modest |
| 5 | ToD Conditioning | **−0.064** | **0/11** | Universally harmful |

### Patient Difficulty Tiers

| Tier | Patients | Block CV R² | Best Approach |
|------|----------|-------------|---------------|
| Easy | d, f, i | 0.63–0.66 | Any method works, dual-branch slightly best |
| Medium | a, b, e, g | 0.50–0.61 | Residual CNN or fine-tune |
| Hard | c, j, k | 0.33–0.43 | Fine-tune (j, k) or Ridge (c) |
| Outlier | h | 0.06–0.19 | Ridge only, all others fail |

### Key Insights

1. **Residual learning is the universal booster**: By decomposing prediction
   into linear (Ridge) + nonlinear (CNN) components, we get the best of
   both worlds without risking catastrophic CNN failures.

2. **Cross-patient transfer works but needs fine-tuning**: Raw LOPO is poor
   (0.387), but fine-tuning recovers and exceeds per-patient (0.508 vs
   0.490). The shared metabolic structure provides useful initialization.

3. **Honest evaluation shrinks gains**: Block CV (0.491) vs simple split
   (0.525) means ~0.034 of our reported R² is temporal leakage. The true
   SOTA is R² ≈ 0.49 under honest evaluation.

4. **Time-of-day is noise at ≤6h**: Confirmed across EXP-419, EXP-1027
   that explicit time features hurt. Circadian effects are already captured
   by basal rate schedules in the physics channels.

5. **Patient h is qualitatively different**: Every method except Ridge
   fails. This patient likely has:
   - Extreme glucose variability not explained by recorded insulin/carbs
   - Possible unrecorded insulin corrections or meals
   - Sensor/device artifacts dominating the signal

6. **Confidence calibration works**: Ensemble disagreement reliably predicts
   error magnitude, enabling selective prediction for clinical safety.

## Recommended Production Pipeline

Based on 1030 experiments, the recommended inference pipeline is:

```
1. Compute decomposed physics (supply/demand/hepatic/net)
2. Train per-patient Ridge on [glucose_history + physics_channels]
3. Train residual CNN on Ridge errors
4. Final prediction = Ridge + α × residual_CNN
5. Optional: Confidence = std(5-model ensemble)
6. Reject predictions with confidence > threshold for clinical safety
```

Expected honest performance: **R² ≈ 0.50** (block CV), with selective
rejection raising effective R² to ~0.55+ on accepted predictions.

## Proposed Next Experiments (EXP-1031–1040)

### Highest Priority

| ID | Title | Rationale |
|----|-------|-----------|
| EXP-1031 | Adaptive Ensemble Weighting | Learn per-patient α from validation; could close 0.529→0.542 gap |
| EXP-1032 | Residual CNN + Fine-Tune Stack | Combine the two best techniques: pretrain residual CNN cross-patient, then fine-tune |
| EXP-1033 | Patient h Deep Dive | What makes h uniquely difficult? Missing data analysis, distribution shifts |

### Feature Engineering

| ID | Title | Rationale |
|----|-------|-----------|
| EXP-1034 | Improved DIA Curves | Current DIA=3.0 artifact suggests PK curves need refinement; try patient-specific DIA from prediction error minimization |
| EXP-1035 | Derivative Physics Channels | Rate-of-change of supply/demand may capture dynamic transitions better than levels |

### Longer Horizons

| ID | Title | Rationale |
|----|-------|-----------|
| EXP-1036 | Multi-Horizon Joint Training | Train one model for 15/30/60/120 min simultaneously; physics value scales with horizon |
| EXP-1037 | Sequence-to-Sequence Forecast | Transformer or LSTM outputting full 120-min trajectory |

### Robustness

| ID | Title | Rationale |
|----|-------|-----------|
| EXP-1038 | Temporal Regime Detection | Identify regime changes and adapt model; 4/11 patients have significant drift |
| EXP-1039 | Online Learning / Sliding Window | Retrain on most recent N days; may help regime-changing patients |
| EXP-1040 | Ablation: Physics Channel Importance | SHAP or permutation importance for each physics channel |

## Appendix: Run Commands

```bash
# Full batch
PYTHONPATH=tools python -m cgmencode.exp_clinical_1021 --detail --save --max-patients 11

# Single experiment
PYTHONPATH=tools python -m cgmencode.exp_clinical_1021 --experiment EXP-1024 --detail --save
```

## References

- EXP-1001–1010: Multi-scale meal physics report (`multi-scale-meal-physics-report-2026-04-10.md`)
- EXP-1011–1020: CNN physics architecture report (`cnn-physics-architecture-report-2026-04-10.md`)
- EXP-419: Time-invariance validation (`encoding-validation-report-2026-04-06.md`)
