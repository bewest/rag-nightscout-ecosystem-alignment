# Research Program Overview

**Date**: 2026-04-07 | **Total experiments**: ~875 | **Patients**: 11 | **CGM readings**: ~570K

---

## Executive Summary

The cgmencode research program has run ~875 experiments across 20+ research phases to build a complete glucose analytics pipeline — from raw CGM data to clinical recommendations. The work spans glucose forecasting, event detection, hypoglycemia prediction, clinical decision support, data quality, pattern recognition, transfer learning, and real-time deployment.

**Bottom line**: The system achieves production-grade performance on 7 of 8 target capabilities. The remaining gaps are data-limited, not model-limited.

---

## Architecture Evolution

The program passed through three architectural eras:

### Era 1: Transformer Discovery (EXP-001 → ~258)

Built a 134K-parameter CGMGroupedEncoder transformer on 10 patients. Per-patient fine-tuning + 5-seed ensembles reached 10.59 mg/dL MAE. Key discovery: the transformer allocates 86.8% of attention to glucose history — it's fundamentally an autoregressor, not a treatment-effects model.

### Era 2: Physics Decomposition (EXP-~300 → ~700)

Decomposed glucose into supply (carbs + hepatic) and demand (insulin) metabolic fluxes. Ridge regression on 8 physics features beat the 134K-parameter transformer at horizons ≥15 min. Circadian correction (+0.474 R² at 60 min) was the single largest gain. Discovered that physics provides features and statistics provides prediction.

### Era 3: Systematic Ceiling Characterization (EXP-700 → 875)

76 overnight Ridge experiments exhaustively tested nonlinear models, feature engineering, ensembles, stacking, and architecture variants. Maximum validated gain: +0.025 R². Information-theoretic ceiling estimated at R²=0.61 (current: 0.534). Bias-variance decomposition: 99.9% bias — the model is underfitting because the available features don't contain enough information.

---

## Current SOTA by Capability

| Capability | Key Metric | SOTA | Status |
|------------|-----------|------|--------|
| Glucose forecasting (30 min) | R² | **0.803** | ✅ Production |
| Glucose forecasting (60 min) | R² | **0.534** | ✅ Near ceiling |
| Event detection | wF1 | **0.710** | ✅ At ceiling |
| 2h HIGH prediction | AUC | **0.907** | ✅ Deployable |
| 2h HYPO prediction | AUC | **0.860** | ✅ Deployable |
| Overnight HYPO prediction | AUC | **0.690** | ❌ Hard ceiling |
| Basal rate assessment | Coverage | **11/11** | ✅ Production |
| CR effectiveness scoring | Coverage | **10/11** | ✅ Production |
| Override timing | F1 | **0.993** | ✅ Solved |
| Spike cleaning | R² gain | **+52%** | ✅ Foundation |
| Circadian correction | R² gain | **+0.474** | ✅ Essential |
| Cold start (day 1) | R² | **0.437** | ✅ Viable |
| Warm-start + 1 week | R² | **0.652** | ✅ Optimal |
| Real-time pipeline | Latency | **118.5 ms** | ✅ Production |
| Streaming fidelity | R² gap | **0.002** | ✅ Negligible |

---

## The 10 Most Important Findings

1. **Physics features beat neural networks.** Ridge on 8 metabolic flux features outperforms a 134K-param transformer. Simpler, interpretable, faster.

2. **Spike cleaning is the single largest gain.** Removing sensor noise artifacts at σ=2.0 improves R² by 52% (+0.159) — more than any model change.

3. **Circadian correction adds +0.474 R² at 60 min.** Three parameters (a·sin + b·cos + c) capture the dawn phenomenon. The cheapest possible model for the largest single improvement.

4. **AR residual correction is data leakage at long horizons.** Two-stage Ridge+AR produces R²=0.941 at 60 min, but uses future glucose. Properly causal AR yields only +0.013.

5. **Effective ISF is 2.91× profile ISF** (total-insulin method, EXP-747; revised to **1.36×** via response-curve method in EXP-1301). AID systems compensate so aggressively that configured settings wildly understate actual insulin sensitivity. The AID masks bad settings.

6. **46.5% of glucose rises are unannounced.** Nearly half of meal events have no carb entry. This is the irreducible blind spot for predictive detection.

7. **Population physics parameters are 99.4% universal.** New patients can use population defaults from day 1. The supply-demand decomposition captures patient-specific physiology; prediction parameters are essentially universal.

8. **The information-theoretic ceiling at 60 min is R²≈0.61.** Only ~0.08 headroom remains. Further gains require new data dimensions (activity, meal composition, hormones).

9. **Patient heterogeneity dominates everything.** The best and worst patients differ by 3× in forecast accuracy, 7× in CR effectiveness, and 82% in ISF variation. No single model tuning matters as much as which patient you're looking at.

10. **Hypoglycemia follows different physics than hyperglycemia.** Counter-regulatory hormones (glucagon, epinephrine, cortisol) below 70 mg/dL are unmeasured, creating a fundamental prediction ceiling at AUC ≈ 0.69 for overnight horizons.

---

## Confirmed Dead Ends

| Approach | Why it fails |
|----------|-------------|
| AR rollout without PK | Catastrophic error compounding |
| Horizon-weighted loss | Uniform MSE already optimal |
| ISF-threshold routing | w144 universally better |
| Extended windows >w144 | Data scarcity ceiling |
| Curriculum learning (calm→volatile) | Doesn't transfer (−146%) |
| Test-time augmentation | Model too sensitive (−35%) |
| Neural event detection | Transformer ignores treatments (5.1× worse) |
| Class rebalancing | Hurts majority class |
| Wider transformers (d=128) | Overparameterized |
| UVA/Padova pretraining | 0% gain with sufficient real data |
| Nonlinear supply-demand features | Harmful (−0.016) |
| Lasso / ElasticNet | Catastrophic for physics features |
| Residual regime decomposition | Failed (R²=0.250) |

---

## Deployment Readiness

| Component | Latency | Size | Status |
|-----------|---------|------|--------|
| Physics flux computation | 107 ms (91% of pipeline) | N/A | ✅ Bottleneck |
| ML inference | 2.7 ms | 67K params (260 KB) | ✅ Fast |
| Spike cleaning | 4.1 ms | N/A | ✅ Fast |
| End-to-end per patient | 118.5 ms | — | ✅ Under 5-min CGM interval |
| Streaming gap vs batch | R² 0.002 | — | ✅ Negligible |
| Edge-viable model | 0.8 ms | 13K params (52 KB) | ✅ Wearable-ready |

The production pipeline processes all 11 patients in 1.3 seconds total. The bottleneck is physics (IOB/COB curve integration), not ML.

---

## What's Next

The program has reached diminishing returns on the current data dimensions. Three paths forward:

1. **New data sources**: Activity sensors (heart rate, accelerometer), meal composition (protein/fat/carb ratios), sleep quality, stress markers. Each would expand the information-theoretic ceiling.

2. **Larger patient cohorts**: 11 patients establish patterns but limit statistical power for subgroup analysis. 50–100 patients would enable robust phenotype clustering.

3. **Prospective deployment**: The pipeline is production-ready (118.5 ms, 260 KB). Real-world deployment would generate the feedback loop needed to validate clinical impact.

---

## Capability Report Index

| Report | Focus |
|--------|-------|
| [Glucose Forecasting](capability-report-glucose-forecasting.md) | Prediction accuracy, ceiling analysis |
| [Event Detection](capability-report-event-detection.md) | Classification, lead time, AID-aware rules |
| [Hypoglycemia Prediction](capability-report-hypoglycemia-prediction.md) | HYPO ceiling, physics boost, alert tuning |
| [Clinical Decision Support](capability-report-clinical-decision-support.md) | Basal/CR assessment, ISF discrepancy |
| [Data Quality](capability-report-data-quality.md) | Spike cleaning, sensor age, stability |
| [Pattern & Drift](capability-report-pattern-drift.md) | Circadian, ISF variation, changepoints |
| [Transfer Learning](capability-report-transfer-learning.md) | Cold start, population defaults |
| [Real-Time Operations](capability-report-realtime-operations.md) | Pipeline timing, model sizing |
