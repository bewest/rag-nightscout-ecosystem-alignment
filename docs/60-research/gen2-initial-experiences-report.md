# Gen-2 cgmencode: Initial Experiences Report

**Date:** 2026-04-03 (updated)
**Scope:** Evaluation of Gen-2 multi-task CGM forecasting pipeline after infrastructure fixes and comprehensive experiment campaign (17+ experiments).

## Executive Summary

The Gen-2 cgmencode multi-task architecture (107K params, CGMGroupedEncoder) has been trained across 10 patients (~32K training windows) with 4 learning objectives: glucose forecasting, event classification, insulin sensitivity drift tracking, and metabolic state detection.

After fixing two critical bugs (ISF unit conversion, Kalman→sliding median drift labels) and running a 17-experiment campaign, performance has improved substantially:

| Metric | Pre-Campaign | Post-Campaign | Best Method | Δ |
|--------|-------------|---------------|-------------|---|
| **Forecast MAE** | 17.34 mg/dL | **12.1 mg/dL** | Diverse ensemble (5 arch) | **-30%** |
| **Hypo MAE** | 15.2 mg/dL | **10.4 mg/dL** | 2-stage hypo detection | **-32%** |
| **Hypo F1** | — | **0.700** | Production v7 | New |
| **Event F1 (XGBoost)** | 0.544 | **0.544** | XGBoost on tabular | — |
| **Clarke Zone A+B** | 97.0% | **97.1%** | Already excellent | — |
| **Conformal 90%** | — | **90.0%** | Production v7 | Calibrated |
| **vs Persistence** | 33% better | **53% better** | Ensemble (25.9→12.1) | +20pp |
| **Drift Correlation** | +0.70 ❌ | **-0.071 ✅** | Sliding median fix | Correct sign |

**The forecast is approaching saturation at ~12 mg/dL MAE** — ensemble diversity helps most; architecture changes have diminishing returns. **Hypo detection is the standout improvement**: 2-stage classification + specialized forecast cuts hypo MAE by 32%. **Event detection remains the weakest link**: the neural event head (F1=0.107) is far inferior to XGBoost (F1=0.544), because the transformer is 87% glucose-dominant and underweights treatment features.

## 1. Infrastructure Fixes (This Session)

Three critical bugs were identified and fixed before meaningful auxiliary head training can proceed:

### 1.1 ISF Unit Conversion (commit `5d7ceee`)

`load_patient_profile()` read ISF values from Nightscout profiles without checking the `units` field. Patient a uses `mmol/L` (ISF=2.7) while patients b–j use `mg/dL` (ISF=21–92). Since all glucose values are stored in mg/dL, this caused an **18× scale mismatch** in the physics model for patient a.

**Fix:** Detect `profile.units` and multiply ISF by 18.0182 when `mmol/L`.

### 1.2 Kalman Filter → Autosens Sliding Median (commit `5d7ceee`)

The `ISFCRTracker` Kalman filter had measurement noise R=5, but real glucose residuals have std≈224 mg/dL. A single 50 mg/dL residual moved the ISF estimate from 40→6.6 (ratio 0.17). The filter saturated at clip boundaries instantly — every patient was monolithically one state class (84% resistance, 0% sensitivity).

**Fix:** Replaced with oref0-style 24-window sliding median of ISF-normalized deviations, matching the clinical autosens algorithm.

| Metric | Before (Kalman) | After (Sliding Median) |
|--------|-----------------|----------------------|
| Resistance | 84.3% | 61.7% |
| Stable | 15.7% | 26.2% |
| Sensitivity | 0.0% | 11.9% |
| Patients with all 3 states | 0/10 | **10/10** |

### 1.3 Path Resolution Bug (commit `0c1ce56`)

Round 21 experiment functions passed split-specific paths (`patients/a/training`) to `build_multitask_windows()` which expected parent dirs (`patients/a`). This caused 0 windows in the label audit smoke test.

**Note for colleagues:** All critical code paths (`generate_aux_labels.py`, `validate_verification.py` Suite C, `hindcast_composite.py`) have been verified to use the corrected sliding median approach. ISFCRTracker is deprecated with a warning in `state_tracker.py` but is not used in any active training or evaluation paths. No retrain is needed — existing labels are correct.

## 2. Experiment Campaign Results

### 2.1 Campaign Overview (17 experiments)

| # | Experiment | Key Finding | Impact |
|---|-----------|-------------|--------|
| 1 | **EXP-139 Diverse Ensemble** | 5 architectures → MAE=12.1 | **Best forecast** |
| 2 | **EXP-137 Production v7** | Hypo-weighted + quantile + conformal | **Best combined** |
| 3 | **EXP-136 Hypo 2-Stage** | Classify then specialize → MAE=10.4 | **Best hypo** |
| 4 | EXP-116 Hypo-Weighted | Hypo MAE 15.2→12.4 (18.4%) | ✅ Significant |
| 5 | EXP-134 Night Specialist | Night MAE 16.8→16.0 (4.8%) | ✅ Modest |
| 6 | EXP-159 Patient Adaptive | 10 patients, val 0.205–0.447 | ⚠️ Mixed |
| 7 | EXP-155 Neural vs XGBoost | XGB F1=0.544 >> Neural F1=0.107 | ✅ Use XGBoost |
| 8 | EXP-156 Weight Ablation | 18 configs, e=0.1–0.3 optimal | ✅ Informative |
| 9 | EXP-158 Focal Loss | Class weighting doesn't help events | ❌ No gain |
| 10 | EXP-141 UVA Pretrain | Marginal 2% (domain gap) | ❌ Minimal |
| 11 | EXP-135 Clarke Optimized | Already 97% Zone A+B | — Saturated |
| 12 | EXP-117 Insulin-Aware | Marginal 0.8% (IOB captures it) | ❌ Minimal |
| 13 | EXP-114 Attention Events | Glucose 87% dominant | ✅ Diagnostic |
| 14 | EXP-125 Multi-Resolution | 5min=5.6, 60min=13.3, 120min=17.9 | ✅ Informative |
| 15 | EXP-122 Volatile-Focused | 3× weight: volatile 15.1→14.8 | ⚠️ Marginal |
| 16 | EXP-152 Gen-2 Baseline | MAE=17.34, composite=0.261 | ✅ Baseline |
| 17 | Full 6-Suite Validation | Event F1=0.544, Drift r=-0.071 | ✅ Baseline |

### 2.2 Forecast Performance (1-hour horizon)

| Model | MAE (mg/dL) | vs Persistence (25.9) | Notes |
|-------|------------|----------------------|-------|
| Persistence baseline | 25.9 | — | Copy last known glucose |
| Gen-2 baseline (EXP-152) | 17.34 | 33% better | Single model, default weights |
| Production v7 (EXP-137) | 12.9 | 50% better | Hypo-weighted + conformal |
| **Diverse Ensemble (EXP-139)** | **12.1** | **53% better** | **5 architectures, best overall** |

#### Architecture sweep within ensemble:

| Config | d_model | Layers | MAE |
|--------|---------|--------|-----|
| d32_L2 | 32 | 2 | 14.3 |
| d64_L2 | 64 | 2 | 12.8 |
| d64_L4 | 64 | 4 | 13.0 |
| d128_L6 | 128 | 6 | 13.3 |
| d32_L6 | 32 | 6 | 13.4 |
| **Ensemble** | mixed | mixed | **12.1** |

d64_L2 is individually best; adding diversity via ensembling gains another 5.3%.

### 2.3 Hypo Detection (Critical Safety Metric)

| Approach | Hypo MAE | Severe MAE | Hypo F1 | Notes |
|----------|----------|------------|---------|-------|
| Baseline | 15.2 | 20.2 | — | No weighting |
| Hypo-weighted (EXP-116) | 12.4 | 14.7 | — | 5× weight on <70 mg/dL |
| **2-Stage (EXP-136)** | **10.4** | — | **0.640** | Classify risk → specialize |
| Production v7 (EXP-137) | 13.1 | — | **0.700** | Combined pipeline |

The 2-stage approach achieves the best hypo-specific MAE (10.4), while production v7 achieves the best hypo F1 (0.700) with conformal calibration for uncertainty quantification.

### 2.4 Event Detection

| Method | F1 | Notes |
|--------|-----|-------|
| Neural event head | 0.107 | Transformer underweights treatments |
| **XGBoost (tabular)** | **0.544** | Uses engineered features from windows |
| Lead time | 36.9 min | 100% >15min, 73.8% >30min |

**Root cause of neural weakness**: Attention analysis (EXP-114) shows the transformer allocates 86.8% of attention to glucose, 10.8% to insulin, 2.4% to carbs. Treatment features that matter for event detection are effectively ignored by the self-attention mechanism. XGBoost, operating on handcrafted tabular features, exploits these features properly.

### 2.5 Time-of-Day Breakdown (Production v7)

| Period | MAE (mg/dL) | Notes |
|--------|-------------|-------|
| Morning | 9.9 | Best — stable after overnight |
| Afternoon | 12.0 | Postprandial variability |
| Evening | 15.0 | Meals + activity variation |
| Night A (10PM–2AM) | 15.2 | Digestion tail |
| Night B (2AM–6AM) | 14.7 | Dawn phenomenon |

Night specialist model reduces overnight MAE from 16.8→16.0 (4.8%), but even with specialization nights remain the hardest period.

### 2.6 Multi-Resolution Forecast Performance

| Horizon | MAE (mg/dL) |
|---------|-------------|
| 5 min | 5.6 |
| 15 min | 7.6 |
| 30 min | 9.8 |
| 60 min | 13.3 |
| 90 min | 16.3 |
| 120 min | 17.9 |

Performance degrades predictably with horizon — the 60-min horizon is the practical sweet spot for AID systems (Loop/AAPS/Trio typically use 30–60 min predictions).

### 2.7 Drift & State Tracking

| Metric | Value | Notes |
|--------|-------|-------|
| Drift-TIR correlation (median) | -0.071 | 7/10 patients negative (correct sign ✅) |
| Detection rate | 15.5% | |
| False signal rate | 4.4% | |
| State distribution | 62% resist / 26% stable / 12% sensitive | Real patient skew |

The weak correlation (-0.071) suggests drift tracking captures some real signal but the feature set is too limited for strong predictive power. Enriched features (circadian, treatment patterns) may help.

### 2.8 Validation Scorecard

| Objective | Metric | Value | Target | Status |
|-----------|--------|-------|--------|--------|
| Forecast | MAE | 12.1 mg/dL | <15 | ✅ |
| Hypo safety | Hypo MAE | 10.4 mg/dL | <12 | ✅ |
| Hypo detection | F1 | 0.700 | >0.60 | ✅ |
| Clinical accuracy | Clarke A+B | 97.1% | >95% | ✅ |
| Event detection | F1 | 0.544 | >0.60 | ⚠️ |
| Override suggestion | F1 | 0.130 | >0.30 | ❌ |
| Drift tracking | Correlation | -0.071 | <-0.20 | ⚠️ |
| Uncertainty | Conformal 90% | 90.0% | 88–92% | ✅ |
| Cross-patient | CV | 28.5% | — | Personalization needed |

## 3. Training Campaign Overview

### 3.1 Infrastructure Fixes (Pre-Campaign)

Three critical bugs were fixed before the campaign:

**1. ISF Unit Conversion** — `load_patient_profile()` read ISF values without checking `units`. Patient a uses mmol/L (ISF=2.7) while patients b–j use mg/dL (ISF=21–92), causing an 18× scale mismatch. **Fix:** Detect units and multiply by 18.0182 when mmol/L.

**2. Kalman Filter → Sliding Median** — ISFCRTracker had R=5, but real residuals std≈224 mg/dL. A single 50 mg/dL residual moved ISF from 40→6.6. **Fix:** Replaced with oref0-style 24-window sliding median, matching the clinical autosens algorithm.

| Metric | Before (Kalman) | After (Sliding Median) |
|--------|-----------------|----------------------|
| Resistance | 84.3% | 61.7% |
| Stable | 15.7% | 26.2% |
| Sensitivity | 0.0% | 11.9% |
| Patients with all 3 states | 0/10 | **10/10** |

**3. Path Resolution Bug** — Round 21 experiments passed split-specific paths to `build_multitask_windows()`.

### 3.2 Contamination Audit (Verified Clean)

A post-campaign audit verified that all active code paths use corrected labels:

| Component | Method | Status |
|-----------|--------|--------|
| `generate_aux_labels._generate_drift_labels()` | Sliding median | ✅ |
| `generate_aux_labels._generate_state_labels()` | ±10% thresholds | ✅ |
| `validate_verification.py` Suite C | `_compute_drift_sliding_median()` | ✅ |
| `hindcast_composite._compute_drift_at_index()` | Sliding median | ✅ |
| `gen2_multitask.pth` training pipeline | Via `build_multitask_dataset()` | ✅ |

ISFCRTracker is deprecated with a runtime warning and is not called in any active training/evaluation path.

## 4. Key Insights

### What Worked

1. **Diverse ensemble** is the single highest-impact technique for forecast accuracy. Five architectures (d32–d128, L2–L6) with simple averaging gives 5.3% gain over the best individual model.

2. **Hypo-weighted loss** and **2-stage hypo detection** dramatically improve safety-critical predictions. The 2-stage approach (classify hypo risk → specialized forecast) achieves 32% better hypo MAE than baseline.

3. **Physics-ML composition** remains effective. The 107K-param model captures 53% improvement over persistence with efficient data use across 10 patients.

4. **Conformal calibration** achieves exactly 90% coverage at the 90% target — uncertainty quantification is properly calibrated.

5. **XGBoost for events** beats the neural event head by 5× (F1=0.544 vs 0.107). Hybrid architecture (neural forecast + tree-based events) is the right approach.

### What Didn't Work

1. **Synthetic pre-training** (UVA/Padova): Only 2% gain after fine-tuning. The domain gap between simulated and real CGM data is too large for simple transfer learning.

2. **Patient-adaptive fine-tuning**: Mixed results — helps some patients, hurts others. The shared model already generalizes well enough.

3. **Focal loss for events**: No improvement over standard cross-entropy. The event detection bottleneck is feature representation, not loss function.

4. **Insulin-aware auxiliary loss**: Only 0.8% gain. The IOB feature already captures insulin dynamics.

5. **Clarke optimization**: Already at 97% Zone A+B — effectively saturated.

6. **Volatile-period weighting**: Only 2% improvement on volatile windows (15.1→14.8), at the cost of calm period accuracy (9.1→9.4). The model's difficulty with volatile periods is a feature engineering problem, not a loss weighting problem.

### Architectural Lessons

- **Attention is glucose-dominated** (87%): The self-attention mechanism naturally focuses on the most predictive signal (glucose trajectory) and underweights treatment features. This is optimal for forecasting but suboptimal for event detection which needs treatment context.

- **Forecast MAE is saturating at ~12 mg/dL** for 1-hour horizon. Further gains likely require longer context windows, richer features (circadian encoding, treatment timing), or fundamentally different architectures.

- **Event detection and override recommendation remain the weakest objectives.** These require treatment-aware features that the current 8-feature core representation doesn't adequately capture.

## 5. Remaining Gaps and Next Steps

### High Priority (target objectives not yet met)

| Gap | Current | Target | Approach |
|-----|---------|--------|----------|
| Event F1 | 0.544 | >0.60 | XGBoost feature engineering; add treatment-timing features |
| Override F1 | 0.130 | >0.30 | Redesign metric as utility-based TIR-impact; tune override rules |
| Drift correlation | -0.071 | <-0.20 | Enrich drift features (circadian, treatment patterns, longer lookback) |
| Night MAE | 16.0 | <14 | Circadian-conditioned model; dinner/basal features |

### Medium Priority (incremental improvements)

1. **Curriculum learning** (EXP-157): Start forecast-only, gradually add auxiliary losses
2. **Longer context** (EXP-162): 4h/6h windows for better trend capture
3. **Mixed synthetic+real augmentation**: Better domain adaptation than naive pretrain
4. **Production ensemble**: Combine best techniques — ensemble + hypo-weighting + conformal

### Research Directions

1. **Override recommendations as treatment planning**: Move from binary override classification to graduated utility scoring — how much would TIR improve with a given override?

2. **Patient embeddings**: Instead of per-patient fine-tuning, learn a patient embedding vector that conditions the shared model.

3. **Treatment attention masking**: Force the model to attend to insulin/carb features during event-relevant windows through attention masking or auxiliary feature loss.

## Appendix: Data Summary

| Dimension | Value |
|-----------|-------|
| Patients | 10 (a–j) |
| Training windows | 32,422 |
| Features | 8 core (glucose, IOB, COB, delta, bolus, carbs, basal, rate) + 8 extended |
| Window size | 24 steps (2h at 5-min intervals) |
| Architecture | CGMGroupedEncoder, 3 layers, 4 heads, d=64 |
| Parameters | 107,543 |
| Device | NVIDIA RTX 3050 Ti (CUDA) |
| Persistence baseline | 25.9 mg/dL MAE (1hr) |
| State distribution (corrected) | 62% resist / 26% stable / 12% sensitive |
| Circadian amplitude | 71.3 mg/dL (100% patients with strong pattern) |
| Cross-patient CV | 28.5% (personalization recommended) |

---

*Report updated 2026-04-03 after 17-experiment campaign. All metrics use causal masking. Labels verified correct (sliding median, ±10% thresholds). Persistence baseline = 25.9 mg/dL (1hr).*
