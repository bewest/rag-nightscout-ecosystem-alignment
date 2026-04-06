# Overall CGM/AID Machine Learning Research Progress

**Date**: 2026-04-06
**Scope**: Cross-thread synthesis of all forecasting, classification, and coordination work

---

## Executive Summary

This report synthesizes progress across the full CGM/AID machine learning research program. Two autonomous research threads—**Forecasting (Thread A)** and **Classification (Thread B)**—have collectively produced **398+ experiment result files** covering **~1,222 variants** across **11 patients** with approximately **6 months of data each**.

- **57 forecasting experiments** across 14 runner versions (v2–v14)
- **40+ classification experiments** across 5 runners
- **8 FDA analysis experiments** (EXP-328–335)
- **Coordination work**: normalization/conditioning, FDA analysis, clinical metrics, shared infrastructure
- **Total experiment runner code**: 15,000+ lines across 20+ Python files

---

## High-Level Goals and Current Status

### Goal 1: Glucose Forecasting (30/60/90/120 min ahead)

**Status: BREAKTHROUGH** — MAE reduced from 34 → 13.5 mg/dL (60% improvement)

| Metric | Value |
|--------|-------|
| Champion | EXP-408 (PKGroupedEncoder transformer + PK + ISF + FT + ensemble) |
| MAE | 13.5 mg/dL |
| MARD | ~8.7% (approaching CGM-grade 8.2%) |
| Best patients | 3/11 < 10 mg/dL MAE |
| Remaining gap to ERA 2 | 3.6 mg/dL at h60 (tractable) |

### Goal 2: UAM Detection (Unannounced Meals)

**Status: PRODUCTION-VIABLE** — F1 = 0.939, CI = [0.928, 0.949]

- Multi-seed validated with bootstrap confidence intervals
- 1D-CNN with B-spline smoothing at 2h scale
- ECE = 0.014 (well-calibrated)

### Goal 3: Override Prediction (Will glucose go out of range?)

**Status: PRODUCTION-VIABLE at 2h** — F1 = 0.882, CI = [0.871, 0.893]

| Horizon | F1 | Architecture |
|---------|----|--------------|
| 2h | 0.882 | Platt-calibrated CNN |
| 6h | 0.723 | Transformer + kitchen_sink |
| 12h | 0.610 | Feature engineering is bottleneck |

- Platt calibration: ECE = 0.046

### Goal 4: Hypoglycemia Prediction

**Status: VIABLE WITH CALIBRATION** — F1 = 0.676, AUC = 0.958

- Platt multi-task CNN, ECE = 0.014
- Safety-critical: high AUC enables practical threshold selection
- 6.2% prevalence (highly imbalanced)

### Goal 5: ISF Drift Detection

**Status: PROVEN** — 9/11 patients show significant drift

- Biweekly rolling aggregation optimal
- Two groups: sensitivity↑ vs resistance↑
- Real-time detection requires ≥7 days of data

### Goal 6: Pattern Retrieval / Clustering

**Status: EARLY** — Silhouette = +0.326 (transformer, 7d)

- U-shaped window performance curve
- R@K saturated; needs better discriminator

---

## Key Discoveries (Cross-Thread)

1. **Architecture dominates at forecasting scale**: Transformer 25% better than CNN on same data
2. **Feature engineering dominates at classification scale**: All architectures plateau at same 12h level
3. **Scale determines optimal approach**: 2h = CNN, 6h+ = transformer, 12h = features matter most
4. **Platt calibration is universal win**: ECE reduction 88%, enables practical deployment thresholds
5. **Time-translation invariance at ≤12h**: Removing time channels IMPROVES results
6. **PK projection helps forecasting**: Future insulin/carb absorption trajectory improves all horizons
7. **ISF normalization is free lunch**: Consistent −0.4 MAE with zero downside
8. **Kitchen-sink combining HURTS**: Adding all features without architecture support → regression
9. **Per-patient fine-tuning essential**: 2.2× MAE range across patients (7.2–23.3)
10. **FDA: feature engineering YES, compression NO**: Glucodensity, depth, derivatives help; FPCA compression doesn't scale

---

## Experiment Registry

| Range | Owner | Domain |
|-------|-------|--------|
| EXP-001–285 | Legacy | Foundation experiments |
| EXP-286–327 | Pattern thread | Classification, retrieval, ISF drift |
| EXP-328–335 | FDA thread | Functional data analysis |
| EXP-337–351 | Validated results | Multi-seed classification |
| EXP-352–408 | Forecasting (v2–v14) | Glucose prediction |
| EXP-361–362 | Classification arch | Architecture search |
| EXP-369–376 | Normalization | Conditioning primitives |
| EXP-373–374 | Multi-task | Transformer + multi-task |
| EXP-403–404 | v13 (forecasting) | Feature engineering for forecast |
| EXP-405–406 | FDA classify v2 | Head injection features |
| EXP-407+ | Available | Next experiments |

---

## Infrastructure Built

### Experiment Runners (14 forecasting + 5 classification + 2 shared)

**Forecasting runners:**
- `exp_pk_forecast_v2.py` through `v14.py` (14 versions)

**Classification runners:**
- `exp_arch_12h.py`, `exp_transformer_features.py`, `exp_multitask_transformer.py`

**Shared runners:**
- `exp_fda_classification_v2.py`, `exp_normalization_conditioning.py`
- `feature_helpers.py` (shared utilities)

### Validation Framework

| Component | Size | Purpose |
|-----------|------|---------|
| `validation_framework.py` | 670 lines | Core validation logic |
| `objective_validators.py` | 530 lines | Objective-specific validators |
| `rescore_forecasts.py` | — | Clinical re-scoring |

- Multi-seed protocol: seeds `[42, 123, 456, 789, 1337]` with bootstrap CIs

### Clinical Metrics

All integrated into `evaluate_model()` for every new experiment:

- **MARD** — Mean Absolute Relative Difference
- **Clarke Error Grid** — zone distribution
- **ISO 15197** — standards compliance
- **ECE** — Expected Calibration Error

### Data Pipeline

| Layer | Channels |
|-------|----------|
| Base (8-channel) | glucose, IOB, COB, net_basal, bolus, carbs, time_sin, time_cos |
| Extended (+PK, 8ch) | Pharmacokinetic projection channels |
| Extended (+FDA, 3ch) | Glucodensity, depth, B-spline derivatives |
| Extended (+ISF, z-score) | Per-patient ISF normalization |

- Per-patient chronological split (80/20)
- Windowing at 2h / 6h / 12h / 24h / 7d scales

---

## Timeline of Milestones

| # | Milestone | Experiments | Key Outcome |
|---|-----------|-------------|-------------|
| 1 | Foundation | EXP-001–285 | Established baselines, 8-channel pipeline, per-patient evaluation |
| 2 | Pattern classification breakthrough | EXP-286–327 | UAM F1=0.939, Override F1=0.882, ISF drift 9/11 |
| 3 | FDA analysis | EXP-328–335 | Glucodensity, depth, B-spline derivatives validated |
| 4 | Multi-seed validation | EXP-337–351 | Bootstrap CIs, Platt calibration, ECE reporting |
| 5 | Forecasting ERA 3 | EXP-352–398 | CNN champion at 24.4 MAE |
| 6 | Cross-scale synthesis | EXP-349–362 | Feature importance is scale-dependent |
| 7 | Multi-task + transformer | EXP-373–374 | Marginal benefit, architecture not bottleneck |
| 8 | ERA Bridge breakthrough | EXP-405–408 | Transformer + PK → 13.5 MAE (44.7% improvement) |
| 9 | Clinical metrics integration | — | MARD, Clarke, ISO 15197, ECE now standard |
| 10 | Researcher coordination | — | Shared utilities, cross-thread hints, non-conflicting assignments |

---

## Research Reports Inventory

| Report | Size | Focus |
|--------|------|-------|
| `evidence-synthesis-normalization-long-horizon-2026-04-06.md` | 1,179 lines | Normalization & long-horizon evidence |
| `forecasting-progress-2026-04-06.md` | — | Forecasting thread companion |
| `classification-progress-2026-04-06.md` | — | Classification thread companion |
| `era-bridge-report-2026-04-06.md` | 395 lines | v14 breakthrough analysis |
| `research-synthesis-2026-04-05.md` | 509 lines | Prior day synthesis |
| `cross-scale-feature-synthesis-2026-04-06.md` | 626 lines | Scale-dependent feature analysis |
| `validated-classification-results-2026-04-05.md` | 385 lines | Validated classification with CIs |
| `accuracy-validation-2026-04-05.md` | 301 lines | Accuracy audit |
| `symmetry-sparsity-feature-selection-2026-04-05.md` | 621 lines | Feature selection analysis |
| `multi-scale-experiment-results.md` | 1,456 lines | Full multi-scale results |
| FDA experiment proposals/results | 1,047 lines combined | FDA methodology |
| `autoresearch-readiness-2026-04-05.md` | 351 lines | Autonomy readiness assessment |
| `continuous-physiological-state-modeling-2026-04-05.md` | 592 lines | Physiological state modeling |

---

## Strategic Roadmap

### Immediate — High Impact

| # | Action | Thread | Expected Impact |
|---|--------|--------|-----------------|
| 1 | Run EXP-405/406 (FDA head features for classification) | Classification | Improved 12h classification |
| 2 | h60-only specialist on transformer | Forecasting | Close remaining 3.6 MAE gap |
| 3 | Multi-seed validate v14 breakthrough results | Forecasting | Confirm 13.5 MAE with CIs |

### Medium-Term

| # | Action | Thread | Expected Impact |
|---|--------|--------|-----------------|
| 4 | Match ERA 2 window size for forecasting | Forecasting | Fair comparison, potential improvement |
| 5 | Hyperparameter optimization on champion | Forecasting | Squeeze remaining performance |
| 6 | Address 12h classification data scarcity | Classification | Unlock longer-horizon classification |
| 7 | ISF-normalized glucose for classification (EXP-369) | Classification | Free lunch from forecasting insight |

### Long-Term

| # | Action | Thread | Expected Impact |
|---|--------|--------|-----------------|
| 8 | Multi-day / multi-week analysis scales | Both | Longer-term pattern detection |
| 9 | Real-time inference pipeline | Both | Production deployment path |
| 10 | Clinical safety validation | Both | Regulatory readiness |
| 11 | Controller integration (AID-specific objectives) | Forecasting | Closed-loop optimization |

---

*This report synthesizes work across both autonomous research threads and shared coordination efforts. For thread-specific details, see the companion reports: `forecasting-progress-2026-04-06.md` and `classification-progress-2026-04-06.md`.*
