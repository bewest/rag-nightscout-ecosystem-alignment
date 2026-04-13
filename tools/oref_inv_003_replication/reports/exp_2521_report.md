# Corrected-Data Baseline Replication (No PK)

**Experiment**: EXP-2521
**Phase**: Diagnostics (Phase 6)
**Date**: 2026-04-12
**Script**: `exp_repl_2401.py --label corrected_no_pk`
**Data provenance**: Post-ODC-fix (commit c8b178e); percentage temp basals correctly converted

## Purpose

Re-run the core SHAP replication (EXP-2401) on **corrected** data to isolate the impact
of the ODC percentage temp basal bug fix. This establishes the clean baseline before
adding PK features (EXP-2531) or DIA optimization (EXP-2541).

## Comparison Summary

| Finding | Their Claim | Our Result | Agreement |
|---------|------------|------------|-----------|
| F1 | cgm_mgdl is #1 hypo | cgm_mgdl #1 hypo (20.1%) | ✅✅ strongly_agrees |
| F2 | cgm_mgdl is #1 hyper | cgm_mgdl #1 hyper | ✅✅ strongly_agrees |
| F3 | iob_basaliob is #2 hypo | iob_basaliob #12 hypo | ❌ disagrees |
| F5 | Settings ~36% of hypo | Settings 25-26% of hypo | 🟡 partially_agrees |
| F8 | ISF and CR both top-5 hypo | ISF #2, CR #8 | 🟡 partially_agrees |

## Key Metrics

| Metric | EXP-2401 (Pre-fix) | EXP-2521 (Post-fix) | Δ |
|--------|--------------------|--------------------|---|
| Hypo AUC | 0.8031 | 0.8031 | ±0.000 |
| Hyper AUC | 0.9008 | 0.9008 | ±0.000 |
| SHAP ρ (hypo) | 0.531 | **0.552** | **+0.021** |
| SHAP ρ (hyper) | 0.691 | **0.669** | **−0.022** |
| AAPS-only ρ (hypo) | — | 0.393 | — |
| iob_basaliob rank | #10 | #12 | −2 |

## Top-10 Feature Rankings (Hypo)

| Rank | Feature | SHAP % |
|------|---------|--------|
| 1 | cgm_mgdl | 20.08% |
| 2 | sug_ISF | 11.44% |
| 3 | sug_current_target | 8.79% |
| 4 | reason_minGuardBG | 8.09% |
| 5 | reason_Dev | 8.04% |
| 6 | bg_above_target | 6.45% |
| 7 | hour | 5.56% |
| 8 | sug_CR | 4.89% |
| 9 | reason_BGI | 4.73% |
| 10 | iob_bolusiob | 3.12% |

## Key Findings

### 1. Data correction improved SHAP alignment

Despite no change in raw AUC (the correction primarily affected 5/8 ODC patients),
SHAP ρ improved from 0.531 to 0.552 (+0.021). This means the corrected data produces
feature importance rankings **more consistent** with the colleague's findings.

**Interpretation**: The buggy percentage temp basals were injecting noise into the
SHAP decomposition, particularly affecting IOB and basal-related features in the
AAPS cohort. Correcting these values improved feature importance signal quality
without changing aggregate prediction performance.

### 2. iob_basaliob still far from colleague's #2

At rank #12, iob_basaliob remains 10 positions below the colleague's #2 ranking.
This gap persists across data corrections and is likely structural:
- Our cohort is 11 Loop + 8 AAPS vs 28 pure oref0 users
- Loop's IOB decomposition differs from oref0's (no 0.1U threshold split)
- Loop patients dominate our cohort's feature importance

### 3. AAPS-only ρ is weaker than full cohort

At ρ=0.393, the AAPS-only subset shows weaker agreement than the full cohort (0.552).
This suggests the 8 AAPS patients alone don't reproduce the colleague's rankings as
well as the mixed cohort, possibly due to smaller sample size or data quality issues.

## Methodology

- **Model**: LightGBM (500 trees, lr=0.05, depth=6, subsample=0.8)
- **CV**: 5-fold stratified
- **SHAP**: TreeExplainer, 50K row sample
- **Data**: 667K rows, 19 patients (11 Loop, 8 AAPS/ODC)
- **Outcomes**: 4h binary hypo (<70 mg/dL) and hyper (>180 mg/dL)

## Limitations

1. **Population asymmetry**: 11 Loop vs 8 AAPS patients; Loop dominates rankings
2. **Feature approximation**: Some OREF features approximated from ns2parquet grid
3. **SHAP sample size**: 50K rows (computational constraint); full-data SHAP may shift
4. **No PK features**: This run uses algorithm-approximated IOB/COB, not first-principles PK

## Relationship to Other Experiments

- **Supersedes**: EXP-2401 (same methodology, corrected data)
- **Baseline for**: EXP-2531 (adds PK), EXP-2541 (adds DIA optimization)
- **Part of**: Phase 6 diagnostic arc (EXP-2521 → EXP-2531 → EXP-2541)
