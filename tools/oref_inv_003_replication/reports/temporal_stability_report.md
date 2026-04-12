# Temporal Stability: Training vs Verification

**Generated**: 2026-04-12 05:13:10 UTC

## SHAP Feature Importance Stability

| Target | Train→Verify ρ | p-value | Interpretation |
|--------|----------------|---------|----------------|
| hypo | 0.848 | 0.0000 | Strong stability |
| hyper | 0.839 | 0.0000 | Strong stability |

## Top-5 Feature Overlap

- **hypo**: 2/5 overlap — train=['cgm_mgdl', 'reason_Dev', 'reason_minGuardBG', 'sug_ISF', 'sug_current_target'], verify=['bg_above_target', 'cgm_mgdl', 'hour', 'sug_CR', 'sug_current_target']
- **hyper**: 4/5 overlap — train=['bg_above_target', 'cgm_mgdl', 'hour', 'sug_current_target', 'sug_threshold'], verify=['bg_above_target', 'cgm_mgdl', 'hour', 'iob_activity', 'sug_current_target']

## CR×hour Interaction Stability

- Training: CR×hour rank #9
- Verification: CR×hour rank #1
- Stable: No (Δ=8)
