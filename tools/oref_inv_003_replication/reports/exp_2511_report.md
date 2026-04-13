# Algorithm-Neutral PK Feature Replacement

**Experiment**: EXP-2511 (sub-experiments: 2511–2518)
**Phase**: Augmentation (Phase 5)
**Date**: 2026-04-12
**Script**: `exp_repl_2511.py`
**Data provenance**: Post-ODC-fix; PK features via `pk_bridge.py`

## Comparison Summary

| Finding | Their Claim | Our Result | Agreement |
|---------|------------|------------|-----------|
| PK-AUC | — | PK replacement improves hypo AUC by +0.0095 | ✅✅ strongly_agrees |
| PK-TRANSFER | — | Cross-algorithm transfer changes by -0.0027 with PK features | ❓ inconclusive |
| PK-UNIVERSAL | — | Per-patient: 19/19 patients improve with PK replacement | ✅✅ strongly_agrees |

## Colleague's Findings (OREF-INV-003)

### F1: iob_basaliob is #3 most important feature (SHAP)

**Evidence**: In our data with original OREF-32, iob_basaliob ranks #12 for hypo. With PK replacement (pk_basal_iob), it ranks #10.
**Source**: OREF-INV-003

### F5: Algorithm predictions are bad (eventualBG R²=0.002)

**Evidence**: PK-derived net_balance provides physics-based prediction that doesn't depend on algorithm-specific eventualBG computation.
**Source**: OREF-INV-003

## Our Findings

### PK-AUC: PK replacement improves hypo AUC by +0.0095 ✅✅

**Evidence**: OREF-32 original: 0.8031 → PK-replaced: 0.8126
**Agreement**: strongly_agrees

### PK-TRANSFER: Cross-algorithm transfer changes by -0.0027 with PK features ❓

**Evidence**: PK features provide algorithm-neutral signals that transfer differently between Loop and AAPS patients.
**Agreement**: inconclusive

### PK-UNIVERSAL: Per-patient: 19/19 patients improve with PK replacement ✅✅

**Evidence**: Loop patients: 11/11 improved
**Agreement**: strongly_agrees

## Methodology Notes

**PK Bridge**: continuous_pk.py computes 8 physiological channels (insulin activity decomposition, carb absorption rate, hepatic production, net metabolic balance) from first-principles insulin pharmacokinetics using oref0/cgmsim-lib exponential activity curves.

**Feature Sets**:
1. OREF-32 original (baseline with 5 approximated features)
2. OREF-32 PK-replaced (5 approximated → 5 PK-derived)
3. OREF-32 PK-augmented (32 original + 8 PK = 40 features)
4. PK-only (~18 algorithm-neutral features)

**Models**: LightGBM classifiers (500 trees, depth 6, subsample 0.8), 5-fold stratified CV, SHAP TreeExplainer for feature importance.

**Data**: 803K rows, 19 patients (11 Loop, 8 AAPS). 4h binary hypo (<70 mg/dL) and hyper (>180 mg/dL) outcomes.

## Limitations

1. **Population imbalance**: 11 Loop vs 8 AAPS patients with very different data volumes (Loop: ~50K rows each, some AAPS: ~3K rows).

2. **PK parameter assumptions**: Fixed DIA=5h and peak=55min for all patients. Individual PK profiling (EXP-2351) showed DIA ranges 2.8-3.8h.

3. **Schedule accuracy**: PK features depend on therapy schedule correctness. If scheduled_basal_rate is wrong, basal_ratio is wrong.

4. **Feature name mapping**: When comparing PK rankings to colleague's, we map PK names back to OREF names (pk_basal_iob→iob_basaliob). This assumes semantic equivalence that is approximate.

5. **SHAP sample**: 50K rows for SHAP (computational constraint). Full-data SHAP may shift rankings.
