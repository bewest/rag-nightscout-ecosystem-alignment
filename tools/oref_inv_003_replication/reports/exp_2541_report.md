# Per-Patient DIA Fitting for PK Feature Optimization

**Experiment**: EXP-2541  
**Phase**: Augmentation (OREF-INV-003 cross-analysis)  
**Date**: 2026-04-12  

## Comparison Summary

| Finding | Their Claim | Our Result | Agreement |
|---------|------------|------------|-----------|
| F_DIA_COHORT | — | Best DIA source: optimal (AUC=0.8144 vs profile=0.8141) | ↔️ not_comparable |
| F_DIA_SHAP | — | Optimized-DIA SHAP ρ=0.679 (Δ=+0.070 vs profile-DIA PK) | 🟡 partially_agrees |

## Colleague's Findings (OREF-INV-003)

### F_DIA: PK models use fixed DIA (5-6h from profiles) for all patients

**Evidence**: Profile settings across cohort; OREF-INV-003 uses whatever the user set
**Source**: OREF-INV-003

## Our Findings

### F_DIA_COHORT: Best DIA source: optimal (AUC=0.8144 vs profile=0.8141) ↔️

**Evidence**: Compared 5 DIA sources at cohort level: ['optimal', 'profile', 'fixed_5.0', 'fixed_3.3', 'exp2353']
**Agreement**: not_comparable

### F_DIA_SHAP: Optimized-DIA SHAP ρ=0.679 (Δ=+0.070 vs profile-DIA PK) 🟡

**Evidence**: iob_basaliob rank: #9 (colleague: #2). Baseline ρ=0.609 from EXP-2531.
**Agreement**: partially_agrees
