# Gen-2 Multi-Task Baseline Report

**Date**: 2026-04-02  
**Model**: `checkpoints/gen2_multitask.pth` (107,543 params)  
**Architecture**: CGMGroupedEncoder, 16-feature, 3-layer, 4 aux heads

## Summary

Gen-2 is the first model trained with multi-task composite loss across all four
objectives: glucose forecasting, event detection, ISF/CR drift tracking, and
metabolic state classification. It uses a two-stage sim-to-real transfer
strategy: pre-training on synthetic data (sweep-uva-250) then fine-tuning on
10 real Nightscout patients.

## Training Pipeline

### Stage 1: Synthetic Pre-Training (EXP-150)

| Parameter | Value |
|-----------|-------|
| Data | sweep-uva-250 (10K vectors, padded 8→16 features) |
| Objective | Forecast-only MSE (no event/drift labels in synthetic data) |
| Architecture | CGMGroupedEncoder(input_dim=16, d_model=64, nhead=4, num_layers=3) |
| Epochs | 50 (converged) |
| Best val loss | 0.000150 |
| Checkpoint | `checkpoints/gen2_pretrain.pth` |

The grouped architecture naturally supports transfer: `state_proj(3)`,
`action_proj(3)`, `time_proj(2)` learn glucose dynamics from synthetic;
`context_proj(8)` starts fresh for real-data context features.

### Stage 2: Real Data Multi-Task Fine-Tuning (EXP-151)

| Parameter | Value |
|-----------|-------|
| Data | 10 real Nightscout patients (15,663 windows: 12,530 train / 3,133 val) |
| Objective | Composite: 1.0×forecast + 0.3×event + 0.2×drift + 0.1×state |
| Pre-trained from | `gen2_pretrain.pth` (strict=False, 6 new aux head keys) |
| Epochs | 37 (early stop at patience 10) |
| Best val loss | 0.2855 |
| Checkpoint | `checkpoints/gen2_multitask.pth` |

#### Training Loss Breakdown (epoch 30)

| Head | Loss | Weight | Weighted |
|------|------|--------|----------|
| Forecast MSE | 0.0028 | 1.0 | 0.0028 |
| Event CE | 0.7441 | 0.3 | 0.2232 |
| Drift MSE | 0.0942 | 0.2 | 0.0188 |
| State CE | 0.0084 | 0.1 | 0.0008 |
| **Composite** | | | **0.2456** |

## Label Generation

### Event Labels (11,527 across 10 patients)

| Event | Count | Pct |
|-------|-------|-----|
| correction_bolus | 8,421 | 53.8% |
| none | 4,136 | 26.4% |
| custom_override | 2,585 | 16.5% |
| exercise | 297 | 1.9% |
| sleep | 166 | 1.1% |
| meal | 58 | 0.4% |
| override/eating_soon/sick | 0 | 0% |

Heavy class imbalance: `correction_bolus` dominates. Future work: class
weighting, focal loss, or data augmentation for minority classes.

### Drift Labels (signed fractional deviation)

| Channel | Mean | Std | Min | Max |
|---------|------|-----|-----|-----|
| ISF drift | -0.54 | 0.60 | -0.95 | 1.00 |
| CR drift | 0.32 | 0.78 | -0.93 | 1.00 |

ISF consistently below nominal (negative = resistance direction). CR varies
more widely. Values clipped to [-1, 1] to cap Kalman filter divergence.

### State Labels

| State | Count | Pct |
|-------|-------|-----|
| resistance | 11,398 | 72.8% |
| stable | 2,462 | 15.7% |
| sensitivity | 1,801 | 11.5% |
| carb_change | 2 | 0.0% |

Resistance dominates because ISF is consistently below profile nominal
for most patients. The 15% threshold provides meaningful separation.

## Verification Results

### Forecast Accuracy

| Metric | Gen-2 | Persistence Baseline |
|--------|-------|---------------------|
| **MAE** | **17.34 mg/dL** | 48.93 mg/dL |
| Improvement | **64.6%** | — |
| Windows | 1,508 | 1,508 |

### Multi-Objective Validation (EXP-122→125)

| Suite | Metric | Value |
|-------|--------|-------|
| EXP-122: Event Detection | Verification F1 | 0.544 |
| EXP-123: Override Recommendation | F1 | 0.130 |
| EXP-124: Drift-TIR Correlation | Pearson r | 0.700 |
| EXP-125: Composite Verification | — | Established |

Event detection F1 is the XGBoost classifier on verification data (the neural
model's event head is not yet independently evaluated in EXP-122). Drift-TIR
correlation of 0.70 validates that ISF/CR tracking relates to outcomes.

### Composite Score

`evaluate_and_promote` composite: **0.261** (first Gen-2 baseline).

## Bug Fixes During Development

Three critical bugs in `generate_aux_labels.py` were discovered and fixed
during the Gen-2 campaign:

1. **Event labels always zero**: `extract_override_events()` returns events
   with `timestamp` but no `step_index`. Fixed by computing step_index from
   grid start time.

2. **Drift scale mismatch**: `ISFCRTracker` returns absolute percentages
   (0-3000%). Changed to signed fractional deviation with [-1, 1] clipping.
   Reduced drift MSE from ~200K to ~0.09.

3. **State threshold mismatch**: After normalization, the 5% threshold was
   applied to fractional values. Raised to 15% (clinically meaningful) and
   used signed deviation to enable resistance detection.

4. **Architecture mismatch in promote_best**: Hardcoded `num_layers=2` and
   `window_size=12` didn't match Gen-2's 3 layers and 24-step windows.
   Added automatic detection from checkpoint state dict.

5. **forecast_mse dict handling**: Multi-task models return `dict` not
   `tensor`. Added `isinstance(pred, dict)` extraction in experiment_lib.

## Gen-1 vs Gen-2 Comparison

| Aspect | Gen-1 | Gen-2 |
|--------|-------|-------|
| Features | 8 | 16 |
| Objectives | 1 (forecast) | 4 (forecast + event + drift + state) |
| Pre-training | None or single-task | Synthetic → real transfer |
| Params | 106,568 | 107,543 |
| Forecast MAE | 11.5–16.0 mg/dL* | 17.34 mg/dL |
| Event F1 | N/A | 0.544 (XGB on representations) |
| Drift RMSE | N/A | Baseline established |
| State Accuracy | N/A | Baseline established |

*Gen-1 MAE was measured on different window sizes and evaluation protocols.
Direct comparison requires standardized evaluation on identical windows.

## Next Steps

1. **Task weight ablation** (EXP-153): Test forecast-dominant, balanced, and
   event-heavy weight configurations to find optimal balance.

2. **Class-weighted event loss**: Address correction_bolus dominance with
   inverse-frequency weighting or focal loss.

3. **State threshold tuning**: The 15% threshold yields 73% resistance.
   Consider patient-specific thresholds or adaptive percentile-based classification.

4. **Neural event evaluation**: Directly evaluate the model's `event_logits`
   head on verification data, rather than relying on XGBoost over features.

5. **Multi-seed stability**: Run 3–5 seeds to confirm variance < 2 mg/dL.

## Files

| File | Description |
|------|-------------|
| `checkpoints/gen2_pretrain.pth` | Stage 1 synthetic pre-trained model |
| `checkpoints/gen2_multitask.pth` | Stage 2 multi-task fine-tuned model |
| `checkpoints/grouped_prod.pth` | Production copy (promoted) |
| `externals/experiments/exp150_gen2_pretrain.json` | Stage 1 results |
| `externals/experiments/exp151_gen2_finetune.json` | Stage 2 results |
| `externals/experiments/exp152_gen2_eval.json` | Evaluation results |
