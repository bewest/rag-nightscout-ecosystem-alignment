# Inference Evaluation Report: Model Capabilities on Verification Data

**Date**: 2026-04-02
**Evaluated on**: Held-out verification splits for 10 patients (a–j)
**Evaluation method**: Hindcast masked-future forecast, 1-hour horizon, stride=6 (30 min)

---

## Executive Summary

We evaluated 8 model checkpoints and 1 ensemble against **held-out verification
data** that was never seen during training. The verification split contains
every Nth day (chronological holdout), providing a realistic test of
generalization.

### Key Finding

The **5-seed ensemble** is the strongest forecaster at **16.0 ± 1.9 mg/dL MAE**
across 10 patients, beating persistence baseline by 26%. The best single model
(seed456) achieves **17.5 mg/dL**, and per-patient fine-tuning achieves
**18.4 mg/dL** (less than expected due to overfitting risk on small
verification sets).

### Critical Context: Training vs Verification Gap

The overnight experiment campaign reported 11.7–13.0 mg/dL MAE on
training/random splits. On held-out verification data, the same models achieve
16.0–19.6 mg/dL. This **~35% degradation** is expected for temporal
generalization and represents the true production performance.

---

## Model Rankings

All models evaluated on identical verification windows across 10 patients.
Persistence baseline: predict last known glucose for the entire horizon.

| Rank | Model | MAE (mg/dL) | Std | vs Persistence | Training |
|------|-------|-------------|-----|----------------|----------|
| 1 | **5-seed ensemble** | **16.0** | 1.9 | **+26%** | 5× seed42-2024 averaged |
| 2 | seed456 (best single) | 17.5 | 2.2 | +19% | EXP-051, masked, seed=456 |
| 3 | per-patient fine-tuned | 18.4 | 2.2 | +15% | EXP-057, selective FT |
| 4 | seed789 | 19.0 | 2.1 | +12% | EXP-051, seed=789 |
| 5 | seed42 | 19.2 | 2.7 | +11% | EXP-051, seed=42 |
| 6 | masked_1hr (base) | 19.6 | 2.9 | +9% | EXP-043, masked training |
| 7 | seed123 | 20.3 | 2.4 | +6% | EXP-051, seed=123 |
| 8 | walkforward | 20.7 | 2.2 | +4% | EXP-046, temporal split |
| — | **persistence** | **21.6** | 3.7 | — | Last glucose repeated |
| 9 | seed2024 | 24.1 | 2.3 | -11% | EXP-051, seed=2024 (overfit) |
| 10 | arch_d64 (EXP-044) | 35.4 | 5.6 | -64% | Not masked-trained |

### Observations

1. **Ensembling is the single biggest win** — averaging 5 seeds reduces MAE from
   17.5–24.1 (individual range) to 16.0 (ensemble). The ensemble smooths out
   seed-specific biases.

2. **Seed matters enormously** — seed456 (17.5) vs seed2024 (24.1) is a 38%
   gap. Two of five seeds underperform persistence. This validates the ensemble
   approach: no single seed is reliably best.

3. **Per-patient fine-tuning underperforms ensemble** (18.4 vs 16.0). On
   training data it was the best approach (11.4 mg/dL), but it overfits to
   training distribution patterns that don't transfer to verification days.

4. **The walk-forward model barely beats persistence** (20.7 vs 21.6). Walk-
   forward training is more conservative but less accurate than random-split
   training with seed ensembling.

5. **Non-masked models are useless for forecasting** — arch_d64 at 35.4 mg/dL
   is 64% worse than persistence. These models learned to copy future glucose
   from the input, not to predict it.

---

## Per-Patient Results

### 5-Seed Ensemble (Best Model)

| Patient | Ensemble MAE | Persistence MAE | Improvement | Windows |
|---------|-------------|-----------------|-------------|---------|
| a | 15.1 | 22.2 | +32% | 815 |
| b | 18.2 | 19.1 | +5% | 810 |
| c | 15.4 | 30.5 | +50% | 708 |
| d | 13.8 | 16.5 | +16% | 751 |
| e | 13.9 | 19.0 | +27% | 658 |
| f | 15.5 | 21.1 | +27% | 790 |
| g | 15.0 | 23.4 | +36% | 782 |
| h | 18.0 | 20.9 | +14% | 278 |
| i | 15.0 | 24.0 | +38% | 802 |
| j | 19.7 | 18.9 | **-4%** | 274 |

**Patient j is the only patient where the model underperforms persistence.**
Patient j has the fewest verification entries (3,063) and the smallest data
volume. Patient d is easiest (13.8 mg/dL), patient j hardest (19.7 mg/dL).

### Per-Step MAE Breakdown (seed456, Best Single Model)

How accuracy degrades with forecast horizon:

| Patient | 15 min | 30 min | 60 min | Degradation (60/15) |
|---------|--------|--------|--------|---------------------|
| a | 12.4 | 14.0 | 23.4 | 1.89× |
| b | 14.6 | 17.7 | 30.3 | 2.08× |
| c | 13.6 | 16.7 | 27.0 | 1.99× |
| d | 10.8 | 12.1 | 20.5 | 1.90× |
| e | 13.0 | 15.2 | 21.6 | 1.66× |
| f | 14.6 | 13.5 | 17.6 | 1.21× |
| g | 13.9 | 13.9 | 24.1 | 1.73× |
| h | 16.6 | 14.0 | 19.4 | 1.17× |
| i | 13.9 | 12.8 | 16.9 | 1.22× |
| j | 16.3 | 17.9 | 27.5 | 1.69× |
| **Mean** | **14.0** | **14.8** | **22.8** | **1.65×** |

**15-minute forecasts (14.0 mg/dL) are nearly 2× better than 60-minute
forecasts (22.8 mg/dL).** The degradation ratio varies: patients f, h, i show
only 1.2× degradation (stable glucose patterns) while b shows 2.1×
(volatile patterns).

---

## Range-Stratified Accuracy

Forecast accuracy varies dramatically by glucose range. Evaluated using the
EXP-043 masked model:

| Range | MAE (mg/dL) | N samples | vs In-Range |
|-------|-------------|-----------|-------------|
| **In-range** (70–180) | **15.7** | 52,333 | — |
| Hypo (<70) | **39.8** | 2,716 | 2.5× worse |
| Hyper (>180) | **27.0** | 22,967 | 1.7× worse |

### Per-Patient Range Breakdown

| Patient | Hypo MAE (n) | In-Range MAE (n) | Hyper MAE (n) |
|---------|-------------|------------------|---------------|
| a | 38.5 (98) | 13.2 (5,423) | 22.8 (4,259) |
| b | 50.7 (58) | 17.5 (5,132) | 38.7 (4,530) |
| c | 35.9 (536) | 13.5 (5,330) | 25.4 (2,630) |
| d | 36.6 (74) | 15.7 (6,896) | 25.9 (2,042) |
| e | 30.3 (88) | 16.3 (5,350) | 21.2 (2,458) |
| f | 34.7 (166) | 15.7 (6,540) | 24.0 (2,774) |
| g | 35.5 (205) | 13.6 (6,553) | 24.2 (2,626) |
| h | 42.3 (169) | 17.0 (2,892) | 29.1 (275) |
| i | 34.2 (1,282) | 16.3 (5,410) | 20.8 (2,932) |
| j | 59.1 (40) | 18.0 (2,807) | 37.8 (441) |

**Hypo prediction is the weakest capability** — 2.5× worse than in-range. This
is expected: hypo events are rare (3.5% of samples), have fast dynamics, and
the model's glucose-autoregressive nature means it underreacts to rapid drops.

Patient i has the most hypo windows (1,282) and the best hypo accuracy (34.2),
suggesting more training data in this range helps. Patient j has the fewest (40)
and worst accuracy (59.1).

---

## Checkpoint Recommendations

### For Production Use

| Use Case | Recommended Checkpoint(s) | MAE | Notes |
|----------|--------------------------|-----|-------|
| **General 1hr forecast** | 5-seed ensemble (exp051_seed*.pth) | 16.0 | Best accuracy, 5× inference cost |
| **Single-model 1hr** | exp051_seed456.pth | 17.5 | Best individual seed |
| **Budget inference** | exp043_forecast_mh_1hr_5min.pth | 19.6 | Single model, baseline |
| **Reconstruction/anomaly** | checkpoints/grouped_multipatient.pth | N/A | Not for forecasting |
| **Multi-hour forecast** | exp043_forecast_mh_6hr_15min.pth | ~23* | Trained for 6hr horizon |

*Multi-hour MAE estimated from EXP-093/111 training evaluation.

### Checkpoints to Retire

| Checkpoint | Reason |
|-----------|--------|
| `checkpoints/ae_multipatient.pth` | Not masked-trained; 301 mg/dL forecast MAE |
| `checkpoints/grouped_multipatient.pth` | Not masked-trained; 181 mg/dL forecast MAE |
| `checkpoints/ae_best.pth` | Single-patient, pre-masked era |
| `externals/experiments/exp044_d64_L2.pth` | Not masked-trained (35.4 MAE) |
| `externals/experiments/exp046_random.pth` | Random split, barely beats persistence |

### Missing Checkpoints (Training Needed)

| Gap | What's Missing | Expected MAE |
|-----|----------------|-------------|
| Hypo-weighted ensemble | Combine EXP-105 augmentation + EXP-116 loss + 5-seed | ~14.5 overall, ~30 hypo |
| Multi-patient masked base | Retrain grouped_multipatient with future masking | ~16-18 |
| Conformal calibration set | Need conformal thresholds computed on verification data | N/A |

---

## Comparison: Experiment Claims vs Verification Reality

| Metric | Training Eval | Verification Eval | Gap |
|--------|--------------|-------------------|-----|
| Best single MAE | 11.4 mg/dL (EXP-057) | 17.5 mg/dL (seed456) | +54% |
| Ensemble MAE | 11.7 mg/dL (EXP-100) | 16.0 mg/dL (5-seed) | +37% |
| vs Persistence | +40% improvement | +26% improvement | -14pp |
| Hypo MAE | 15.7 mg/dL (EXP-115) | 39.8 mg/dL | +154% |
| In-range MAE | 10.3 mg/dL (EXP-115) | 15.7 mg/dL | +52% |

**The verification gap is significant.** Training evaluation overestimates
performance by 37–54% depending on the model. This is consistent with temporal
generalization: the model learns time-specific patterns (e.g., "patient c
always rises at 7am on training days") that don't transfer to held-out days.

**Hypo accuracy degrades most** (154% gap) — the model memorizes specific hypo
patterns rather than learning generalizable hypo dynamics.

---

## Evaluation Methodology

### Data Split

- **Training**: All days except every Nth day per patient
- **Verification**: Every Nth day (chronological holdout)
- Patients a–j: 10 real Nightscout users, 18K–90K training entries each

### Forecast Protocol

1. Slide a 24-step window (2 hours) across verification data, stride=6 (30 min)
2. First 12 steps = history (real data, all features)
3. Last 12 steps = forecast horizon (glucose zeroed, other features preserved)
4. Model predicts the full 24-step window
5. Score only the future 12 steps against actual glucose
6. Skip windows containing any NaN in glucose column

### Metrics

- **MAE**: Mean Absolute Error in mg/dL (denormalized from [0,1] by ×400)
- **Persistence**: Repeat last known glucose for entire horizon
- **Range-stratified**: MAE computed separately for hypo (<70), in-range (70–180), hyper (>180)
- **Per-step**: MAE at each 5-minute forecast step (3rd=15min, 6th=30min, 12th=60min)

### Models Evaluated

| Name | Source | Architecture | Training |
|------|--------|-------------|----------|
| masked_1hr | EXP-043 | Grouped d=64 L=2 | 10-patient, future-masked |
| seed42–seed2024 | EXP-051 | Grouped d=64 L=2 | 10-patient, masked, 5 seeds |
| arch_d64 | EXP-044 | Grouped d=64 L=2 | 10-patient, NOT masked |
| walkforward | EXP-046 | Grouped d=64 L=2 | Temporal split (80/20) |
| per_patient_ft | EXP-057 | Grouped d=64 L=2 | Fine-tuned per patient |
| 5-seed ensemble | EXP-051 | 5× Grouped d=64 L=2 | Average of 5 seed outputs |

---

## Conclusions

1. **The 5-seed ensemble at 16.0 mg/dL is the production-ready model.** It
   provides the best trade-off between accuracy and robustness.

2. **All "checkpoints/" models must be retrained with future masking** before
   they can be used for forecasting. They are currently only valid for
   reconstruction/anomaly detection tasks.

3. **Hypo prediction remains the critical gap.** At 39.8 mg/dL on verification
   data, the model's hypo forecasting is not clinically reliable. Augmentation
   and weighted loss (EXP-105, 116) showed promise on training data but need
   verification evaluation.

4. **Per-patient fine-tuning helps less than expected on unseen days.** The
   ensemble approach is more robust: it averages out seed-specific biases
   without overfitting to patient-specific temporal patterns.

5. **The 37% training-to-verification gap is the key metric to close.** Future
   work should focus on reducing temporal overfitting through:
   - Stronger data augmentation (time-shifting, noise injection)
   - Walk-forward training with ensemble aggregation
   - Larger patient cohorts for population-level generalization
