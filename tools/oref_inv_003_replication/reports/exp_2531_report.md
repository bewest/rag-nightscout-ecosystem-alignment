# Corrected-Data Replication with PK Features

**Experiment**: EXP-2531
**Phase**: Diagnostics (Phase 6)
**Date**: 2026-04-12
**Script**: `exp_repl_2401.py --label corrected_pk --use-pk`
**Data provenance**: Post-ODC-fix (commit c8b178e); PK features via `pk_bridge.py`

## Purpose

Re-run the core SHAP replication on corrected data WITH physics-based PK features
(insulin pharmacokinetics). Builds on EXP-2521 (no PK) to quantify the value of
first-principles insulin modeling for both prediction accuracy and SHAP alignment.

## Comparison Summary

| Finding | Their Claim | Our Result | Agreement |
|---------|------------|------------|-----------|
| F1 | cgm_mgdl is #1 hypo | cgm_mgdl #1 hypo (18.4%) | ✅✅ strongly_agrees |
| F3 | iob_basaliob is #2 hypo | iob_basaliob #10 hypo (PK-replaced) | 🟡 partially_agrees |
| F5a | Settings ~36% hypo | Settings ~26% hypo | 🟡 partially_agrees |
| F8 | ISF and CR both top-5 | ISF #2, CR #10 | 🟡 partially_agrees |

## Key Metrics

| Metric | EXP-2521 (No PK) | EXP-2531 (PK) | Δ | Significance |
|--------|------------------|----------------|---|-------------|
| Hypo AUC | 0.8031 | **0.8150** | **+0.012** | PK improves prediction |
| Hyper AUC | 0.9008 | **0.9057** | **+0.005** | Consistent improvement |
| SHAP ρ (hypo) | 0.552 | **0.609** | **+0.057** | Major alignment gain |
| SHAP ρ (hyper) | 0.669 | **0.691** | **+0.022** | Good improvement |
| AAPS-only ρ (hypo) | 0.393 | **0.474** | **+0.081** | Strongest gain |
| iob_basaliob rank | #12 | **#10** | **+2** | Closer to colleague's #2 |
| iob_basaliob (AAPS) | #14 | **#9** | **+5** | Major improvement |

## Top-10 Feature Rankings (Hypo, PK-replaced)

| Rank | Feature | SHAP % | vs EXP-2521 |
|------|---------|--------|-------------|
| 1 | cgm_mgdl | 18.39% | = (was #1) |
| 2 | sug_ISF | 10.99% | = (was #2) |
| 3 | sug_current_target | 7.98% | = (was #3) |
| 4 | reason_minGuardBG | 7.60% | = (was #4) |
| 5 | reason_Dev | 5.93% | = (was #5) |
| 6 | bg_above_target | 6.01% | = (was #6) |
| 7 | reason_BGI | **5.46%** | ↑ from #9 |
| 8 | hour | 5.12% | ↓ from #7 |
| 9 | sug_CR | 4.21% | ↓ from #8 |
| 10 | iob_basaliob | **3.45%** | ↑ from #12 |

## Key Findings

### 1. PK features universally improve prediction

Hypo AUC rose from 0.8031 to 0.8150 (+0.012). This is a meaningful improvement,
especially given that baseline performance was already strong. The PK bridge replaces
5 algorithm-approximated features (IOB, activity, BGI, deviation, net IOB) with
physics-based equivalents computed from raw insulin delivery data.

### 2. SHAP alignment shows largest gain in AAPS cohort

The AAPS-only SHAP ρ jumped from 0.393 to 0.474 (+0.081), the single largest
improvement of any intervention. This makes sense: oref0/AAPS patients contribute
algorithm-specific IOB decomposition that PK normalizes, bringing their feature
importance closer to the colleague's pure-oref0 cohort.

### 3. iob_basaliob enters top-10 for AAPS subset

With PK features, iob_basaliob improved from #14 to #9 in the AAPS-only analysis.
This 5-position jump demonstrates that the PK bridge partially recovers the
physiological signal that oref0's basal IOB tracking captures natively.

### 4. reason_BGI gains importance with PK

reason_BGI moved from #9 to #7, reflecting that PK-derived BGI (blood glucose
impact from insulin) is a better-calibrated signal than the algorithm-approximated
version. This feature captures the instantaneous rate of insulin-driven BG change.

### 5. Remaining gap to colleague's #2 for iob_basaliob

Even with PK, iob_basaliob is #10 overall (colleague: #2). The 8-position gap
likely reflects:
- **Population structure**: 11 Loop + 8 AAPS vs 28 pure oref0
- **oref0's IOB semantics**: 0.1U threshold splits basal/bolus IOB uniquely
- **DIA assumption**: Using profile DIA (5-6h) rather than fitted DIA

## PK Bridge Architecture

The PK bridge (`pk_bridge.py`) replaces 5 OREF features:

| Original (approximated) | PK Replacement | Source |
|--------------------------|----------------|--------|
| iob_basaliob | pk_basal_iob | Exponential decay of basal delivery |
| iob_bolusiob | pk_bolus_iob | Exponential decay of bolus delivery |
| iob_activity | pk_activity | Insulin activity curve (derivative of IOB) |
| reason_BGI | pk_bgi | BGI from activity × ISF |
| sr_deviation | PK_dev | Actual BG change − predicted (from PK) |

Additionally, 8 augmentation features are available (used in EXP-2511):
pk_net_balance, pk_carb_rate, pk_hepatic, pk_total_iob, pk_basal_ratio,
pk_bolus_ratio, pk_time_since_bolus, pk_active_carbs

## Methodology

- **Model**: LightGBM (500 trees, lr=0.05, depth=6, subsample=0.8)
- **CV**: 5-fold stratified
- **SHAP**: TreeExplainer, 50K row sample
- **PK parameters**: DIA from patient profiles (5-6h), peak=75min (rapid-acting)
- **Data**: 803K rows, 19 patients (11 Loop, 8 AAPS/ODC)

## Limitations

1. **Fixed PK parameters**: Profile DIA used for all patients; EXP-2541 later showed
   per-patient optimization yields ρ=0.679
2. **Peak assumption**: Fixed peak=75min; actual peak varies by insulin type (Fiasp=55min)
3. **Population imbalance**: Loop patients still dominate feature rankings
4. **Basal schedule accuracy**: PK computation relies on scheduled_basal_rate correctness

## Relationship to Other Experiments

- **Builds on**: EXP-2521 (same data, no PK) — isolates PK contribution
- **Baseline for**: EXP-2541 (adds per-patient DIA optimization → ρ=0.679)
- **Validates**: EXP-2511 (PK-only features match 32-feature baseline)
- **Part of**: Phase 6 diagnostic arc (EXP-2521 → EXP-2531 → EXP-2541)

## ρ Progression Context

| Experiment | ρ (hypo) | Enhancement |
|-----------|---------|-------------|
| EXP-2401 (pre-fix) | 0.531 | Original Phase 1 |
| EXP-2521 (post-fix) | 0.552 | +0.021 from data correction |
| **EXP-2531 (+ PK)** | **0.609** | **+0.057 from PK features** |
| EXP-2541 (+ DIA opt) | 0.679 | +0.070 from DIA tuning |
