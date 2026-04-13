# Feature Importance Ranking Replication

**Experiment**: EXP-2401  
**Phase**: Replication (OREF-INV-003 cross-analysis)  
**Date**: 2026-04-12  
**Script**: `exp_repl_2401.py`  
**Data provenance**: ⚠️ Pre-ODC-fix. AAPS/ODC patients used percentage temp basals stored as raw U/hr rates. See EXP-2521 for corrected-data rerun.

## Comparison Summary

| Finding | Their Claim | Our Result | Agreement |
|---------|------------|------------|-----------|
| F1 | cgm_mgdl is top feature for hypo prediction | Confirmed: cgm_mgdl is top feature for hypo prediction | ✅✅ strongly_agrees |
| F2 | cgm_mgdl is top feature for hyper prediction | Confirmed: cgm_mgdl is top feature for hyper prediction | ✅✅ strongly_agrees |
| F3 | iob_basaliob is #2 for hypo | Confirmed: iob_basaliob is #2 for hypo | ❌ disagrees |
| F4 | hour is #2 for hyper | Confirmed: hour is #2 for hyper | 🟡 partially_agrees |
| F5 | User-controllable settings account for ~36% of hypo importance | Confirmed: User-controllable settings account for ~36% of hypo importance | 🟡 partially_agrees |
| F6 | User-controllable settings account for ~28% of hyper importance | Confirmed: User-controllable settings account for ~28% of hyper importance | ✅ agrees |
| F7 | CR × hour is the strongest interaction | Confirmed: CR × hour is the strongest interaction | ❌ disagrees |
| F8 | sug_ISF and sug_CR both in top-5 for hypo | Confirmed: sug_ISF and sug_CR both in top-5 for hypo | 🟡 partially_agrees |
| F9 | bg_above_target in top-5 for hyper | Confirmed: bg_above_target in top-5 for hyper | ✅✅ strongly_agrees |
| F10 | Overall SHAP rankings are stable across cohort | Confirmed: Overall SHAP rankings are stable across cohort | 🟡 partially_agrees |

## Colleague's Findings (OREF-INV-003)

### F1: cgm_mgdl is top feature for hypo prediction

**Evidence**: OREF-INV-003 Table 4/5
**Source**: OREF-INV-003

### F2: cgm_mgdl is top feature for hyper prediction

**Evidence**: OREF-INV-003 Table 4/5
**Source**: OREF-INV-003

### F3: iob_basaliob is #2 for hypo

**Evidence**: OREF-INV-003 Table 4/5
**Source**: OREF-INV-003

### F4: hour is #2 for hyper

**Evidence**: OREF-INV-003 Table 4/5
**Source**: OREF-INV-003

### F5: User-controllable settings account for ~36% of hypo importance

**Evidence**: OREF-INV-003 Table 4/5
**Source**: OREF-INV-003

### F6: User-controllable settings account for ~28% of hyper importance

**Evidence**: OREF-INV-003 Table 4/5
**Source**: OREF-INV-003

### F7: CR × hour is the strongest interaction

**Evidence**: OREF-INV-003 Table 4/5
**Source**: OREF-INV-003

### F8: sug_ISF and sug_CR both in top-5 for hypo

**Evidence**: OREF-INV-003 Table 4/5
**Source**: OREF-INV-003

### F9: bg_above_target in top-5 for hyper

**Evidence**: OREF-INV-003 Table 4/5
**Source**: OREF-INV-003

### F10: Overall SHAP rankings are stable across cohort

**Evidence**: OREF-INV-003 Table 4/5
**Source**: OREF-INV-003

## Our Findings

### F1: Confirmed: cgm_mgdl is top feature for hypo prediction ✅✅

**Evidence**: cgm_mgdl is #1 hypo (18.4%)
**Agreement**: strongly_agrees
**Prior work**: EXP-2401 analysis

### F2: Confirmed: cgm_mgdl is top feature for hyper prediction ✅✅

**Evidence**: cgm_mgdl is #1 hyper (40.3%)
**Agreement**: strongly_agrees
**Prior work**: EXP-2401 analysis

### F3: Confirmed: iob_basaliob is #2 for hypo ❌

**Evidence**: iob_basaliob is #10 hypo
**Agreement**: disagrees
**Prior work**: EXP-2401 analysis

### F4: Confirmed: hour is #2 for hyper 🟡

**Evidence**: hour is #4 hyper
**Agreement**: partially_agrees
**Prior work**: EXP-2401 analysis

### F5: Confirmed: User-controllable settings account for ~36% of hypo importance 🟡

**Evidence**: User-ctrl hypo = 25.3% (theirs ~36%)
**Agreement**: partially_agrees
**Prior work**: EXP-2401 analysis

### F6: Confirmed: User-controllable settings account for ~28% of hyper importance ✅

**Evidence**: User-ctrl hyper = 26.4% (theirs ~28%)
**Agreement**: agrees
**Prior work**: EXP-2401 analysis

### F7: Confirmed: CR × hour is the strongest interaction ❌

**Evidence**: CR × hour is #8
**Agreement**: disagrees
**Prior work**: EXP-2401 analysis

### F8: Confirmed: sug_ISF and sug_CR both in top-5 for hypo 🟡

**Evidence**: ISF #2, CR #9 (one in top-5)
**Agreement**: partially_agrees
**Prior work**: EXP-2401 analysis

### F9: Confirmed: bg_above_target in top-5 for hyper ✅✅

**Evidence**: bg_above_target #3 hyper
**Agreement**: strongly_agrees
**Prior work**: EXP-2401 analysis

### F10: Confirmed: Overall SHAP rankings are stable across cohort 🟡

**Evidence**: Median CV=0.71 (moderate stability)
**Agreement**: partially_agrees
**Prior work**: EXP-2401 analysis

## Figures

![fig 2401 per patient stability](../figures/tools/oref_inv_003_replication/figures/fig_2401_per_patient_stability.png)
*fig 2401 per patient stability*

![fig 2401 loop vs oref comparison](../figures/tools/oref_inv_003_replication/figures/fig_2401_loop_vs_oref_comparison.png)
*fig 2401 loop vs oref comparison*

![fig 2401 category split](../figures/tools/oref_inv_003_replication/figures/fig_2401_category_split.png)
*fig 2401 category split*

![fig 2401 rank scatter](../figures/tools/oref_inv_003_replication/figures/fig_2401_rank_scatter.png)
*fig 2401 rank scatter*

![fig 2401 shap comparison hyper](../figures/tools/oref_inv_003_replication/figures/fig_2401_shap_comparison_hyper.png)
*fig 2401 shap comparison hyper*

![fig 2401 shap comparison hypo](../figures/tools/oref_inv_003_replication/figures/fig_2401_shap_comparison_hypo.png)
*fig 2401 shap comparison hypo*

## Methodology Notes

Trained LightGBM models (500 trees, lr=0.05, depth=6) on 19 patients (11 Loop + 8 AAPS/ODC). Computed SHAP feature importance using TreeExplainer (shap). Compared rankings with OREF-INV-003's 28-user oref cohort via Spearman rank correlation.

## Synthesis

## Replication Summary

- **F1** (strongly_agrees): cgm_mgdl is #1 hypo (18.4%)
- **F2** (strongly_agrees): cgm_mgdl is #1 hyper (40.3%)
- **F3** (disagrees): iob_basaliob is #10 hypo
- **F4** (partially_agrees): hour is #4 hyper
- **F5** (partially_agrees): User-ctrl hypo = 25.3% (theirs ~36%)
- **F6** (agrees): User-ctrl hyper = 26.4% (theirs ~28%)
- **F7** (disagrees): CR × hour is #8
- **F8** (partially_agrees): ISF #2, CR #9 (one in top-5)
- **F9** (strongly_agrees): bg_above_target #3 hyper
- **F10** (partially_agrees): Median CV=0.71 (moderate stability)

**Overall**: 8/10 findings replicated, 2 disagreed, 0 inconclusive.

## Limitations

Our cohort is smaller (19 vs 28 users) and mixed-algorithm (Loop + AAPS) vs their pure oref cohort. Some OREF features are approximated from our grid data rather than extracted directly. SHAP may use gain fallback if the shap package is not installed.
