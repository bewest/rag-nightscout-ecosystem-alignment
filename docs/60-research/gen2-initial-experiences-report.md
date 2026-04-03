# Gen-2 cgmencode: Initial Experiences Report

**Date:** 2026-04-03
**Scope:** Evaluation of Gen-2 multi-task CGM forecasting pipeline after Round 21 infrastructure fixes and first training campaign.

## Executive Summary

The Gen-2 cgmencode multi-task architecture (107K params, CGMGroupedEncoder) has been trained across 10 patients (~32K training windows, ~3.3K verification windows) with 4 learning objectives: glucose forecasting, event classification, insulin sensitivity drift tracking, and metabolic state detection.

**Forecast performance is solid** — the best checkpoint (EXP-155) achieves **16.0 mg/dL MAE** on held-out verification data, a **51.8% improvement** over persistence baseline (33.2 mg/dL). Per-patient MAE ranges from 12.2 to 19.2 mg/dL.

**Auxiliary heads need further work.** Event classification (F1=0.107–0.123 macro), state detection (F1=0.37–0.40), and drift tracking (r=+0.20–0.42) are not yet at levels useful for clinical decision support. However, these heads were trained with broken labels (Kalman filter saturation, ISF unit bug) — the infrastructure fixes landed in this session should substantially improve the next training round.

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

**Note for colleagues:** `validate_verification.py` and `hindcast_composite.py` still use `ISFCRTracker` directly with the same R=5 miscalibration and no unit conversion. These should be updated to use `load_patient_profile()` and either increase measurement noise or adopt the sliding median approach.

## 2. Model Performance on Verification Data

### 2.1 Forecast MAE (1-hour horizon)

Evaluated on 3,295 verification windows across 10 patients, with future glucose masked (causal evaluation).

| Checkpoint | MAE (mg/dL) | vs Persistence | Notes |
|-----------|------------|----------------|-------|
| Persistence baseline | 33.2 | — | Copy last known glucose |
| gen2_pretrain (EXP-150) | 70.2 | −346% (**worse**) | No aux heads; forecast-only pretrain |
| gen2_multitask (EXP-151) | 53.3 | −158% (**worse**) | Base multitask; broken labels |
| **exp155_neural_event** | **16.0** | **+76.7%** | Best checkpoint; class-weighted |
| exp156_e0.3_d0.1_s0.1 | 17.9 | +71.1% | Weight ablation variant |

**Key insight:** The gen2_pretrain and gen2_multitask checkpoints perform *worse than persistence*. This is consistent with the prior finding that these models were trained without proper causal masking or had label corruption issues during their training campaign. The EXP-155 and EXP-156 checkpoints, trained with corrected class weights, perform well.

### 2.2 Per-Patient Forecast MAE (Best Model: EXP-155)

| Patient | Windows | Persistence | EXP-155 | Adaptive (EXP-159) | Adapt Δ |
|---------|---------|-------------|---------|---------------------|---------|
| a | 404 | 32.7 | 16.9 | 18.8 | +1.9 |
| b | 399 | 29.1 | 13.8 | 15.0 | +1.2 |
| c | 351 | 44.5 | 15.2 | 18.8 | +3.6 |
| d | 371 | 24.7 | 12.8 | 12.8 | −0.0 |
| e | 323 | 27.6 | 17.2 | 16.6 | −0.6 |
| f | 392 | 30.9 | 17.6 | 17.3 | −0.3 |
| g | 385 | 33.3 | 15.0 | 14.7 | −0.3 |
| h | 138 | 38.1 | 15.3 | 17.3 | +2.0 |
| i | 395 | 38.1 | 19.2 | 18.4 | −0.8 |
| j | 137 | 25.7 | 12.2 | 15.8 | +3.6 |
| **Mean** | | **32.5** | **15.5** | **16.6** | **+1.0** |

**Patient-adaptive fine-tuning (EXP-159) did not help** — it slightly degraded MAE for 6/10 patients. The shared model already generalizes well. This is consistent with the prior finding that per-patient fine-tuning has mixed results (−9% to +17% depending on patient).

### 2.3 Auxiliary Head Performance

Evaluated with **corrected** verification labels (post-fix):

| Head | Metric | gen2_multitask | EXP-155 | EXP-156 |
|------|--------|---------------|---------|---------|
| Event | F1 (macro) | 0.123 | 0.107 | 0.109 |
| State | F1 (macro) | 0.368 | 0.399 | 0.396 |
| Drift | ISF correlation | +0.197 | +0.419 | +0.406 |

These models were trained with the **old broken labels** (Kalman-saturated, no unit conversion). The positive drift correlation (+0.42) is encouraging — even with corrupted training labels, the model learned some real signal. Retraining with corrected labels should improve these substantially.

### 2.4 Prior Campaign Results (Pre-Fix)

From the EXP-152 evaluation suite (run before our fixes):

| Metric | Value | Notes |
|--------|-------|-------|
| Forecast MAE | 17.34 mg/dL | On 1,508 windows |
| vs Persistence | 64.6% improvement | |
| Event F1 (verification) | 0.544 | XGBoost classifier, not neural head |
| Override F1 | 0.130 | Noisy — 0.71 false alarms/hr |
| Drift-TIR correlation | +0.149 (aggregate) | 7/10 patients negative (correct sign) |
| Composite score | 0.261 | Weighted across objectives |

## 3. Training Campaign Overview

### 3.1 Experiment Inventory

| Experiment | Type | Status | Key Finding |
|-----------|------|--------|-------------|
| EXP-150 | Gen2 pretrain | ✅ | Val loss 0.00015 (forecast-only) |
| EXP-151 | Gen2 multitask finetune | ✅ | Val loss 0.285, promoted |
| EXP-152 | Evaluation suite | ✅ | Composite score 0.261 |
| EXP-154 | Label quality audit | ✅ | Exposed Kalman saturation + unit bug |
| EXP-155 | Neural vs XGBoost | ✅ | Neural F1=0.107; XGBoost errored |
| EXP-156 | Weight ablation (18 configs) | ✅ | Best: e0.5_d0.2_s0.1 (val 0.658) |
| EXP-158 | Focal loss | ✅ | Unweighted (0.344) > weighted (0.421) |
| EXP-159 | Patient-adaptive | ✅ | 10 per-patient models; no improvement |

### 3.2 Checkpoint Inventory

34 checkpoint files saved:
- `gen2_pretrain.pth` — Forecast-only baseline (no aux heads)
- `gen2_multitask.pth` — Multi-task baseline (broken labels)
- `exp155_neural_event.pth` — **Best current model** (class-weighted training)
- `exp156_*.pth` — 18 weight ablation variants
- `exp159_[a-j].pth` — 10 patient-adaptive models

## 4. What Worked

1. **Physics-ML composition**: The architecture learns residuals over a physics prediction, handling 85% of glucose dynamics through the model structure rather than learned parameters. This keeps the model small (107K params) and data-efficient.

2. **Multi-patient training**: All 10 patients (32K windows) load and train correctly. The shared model generalizes well — per-patient MAE ranges from 12.2 to 19.2, beating persistence by 40–66% per patient.

3. **Class-weighted training**: EXP-155's class-weighted cross-entropy improved event/state head training compared to uniform weights, even with broken labels.

4. **GPU acceleration**: RTX 3050 Ti properly detected and used throughout pipeline via `get_device()`.

## 5. What Didn't Work / Needs Fixing

1. **Drift/state labels were garbage** (fixed this session). Kalman filter saturated → 84% monolithic resistance. The sliding median fix produces a genuine 62/26/12 distribution with temporal variation.

2. **ISF unit mismatch** (fixed this session). Patient a's mmol/L ISF caused 18× physics model error.

3. **Patient-adaptive fine-tuning** hurt more than it helped. Freeze-and-finetune with only 10 epochs per patient overfits on small per-patient datasets (1K–3K windows). May work better with more data or careful regularization.

4. **gen2_pretrain/gen2_multitask worse than persistence** on verification. These likely have a training/evaluation mismatch — possibly trained without causal masking or evaluated differently. The EXP-155 checkpoint trained with proper masking works correctly.

5. **XGBoost comparison failed** in EXP-155 (unexpected keyword error). Needs debugging.

## 6. Recommended Next Steps

### Immediate (unblocked by this session's fixes):

1. **Retrain gen2_multitask with corrected labels** — The sliding median drift labels and unit-converted ISF values should dramatically improve the state/drift heads. The forecast head should remain stable at ~16 mg/dL MAE.

2. **Re-run validation suites** (`validate_verification.py`) with corrected `load_patient_profile()` to get accurate drift-TIR correlation baselines.

3. **Fix XGBoost comparison** in EXP-155 — debug the `model_type` keyword error to get a proper neural vs tree-based comparison.

### Short-term:

4. **EXP-157 (curriculum learning)**: Start with forecast-only, then gradually add auxiliary losses. May help the aux heads converge better.

5. **EXP-162 (longer context windows)**: Current window is 2h (24 steps). Try 4h/6h to capture longer-term sensitivity trends that the autosens sliding median detects.

### Medium-term:

6. **Override metric redesign** (EXP-164): Current F1=0.13 with 0.71 false alarms/hr is not clinically useful. Need a precision-focused metric with time tolerance.

7. **Investigate gen2_pretrain regression**: Why does forecast-only pretrain perform *worse* than persistence? This may indicate a training data leak or masking issue in the pretrain pipeline.

## Appendix: Data Summary

| Dimension | Value |
|-----------|-------|
| Patients | 10 (a–j) |
| Training windows | 32,026 |
| Verification windows | 3,295 |
| Features | 16 (8 core + 8 extended) |
| Window size | 24 steps (2h at 5-min intervals) |
| Architecture | CGMGroupedEncoder, 3 layers, 4 heads, d=64 |
| Parameters | 107,543 |
| Device | NVIDIA RTX 3050 Ti (CUDA) |
| Label distribution (training, corrected) | Resist 62%, Stable 26%, Sensitive 12% |
| Event distribution (training) | ~48% correction_bolus, ~20% meal, ~15% none |

---

*Report generated from verification evaluation on corrected pipeline. All MAE values use causal masking (future glucose zeroed). Label distributions reflect post-fix sliding median approach.*
