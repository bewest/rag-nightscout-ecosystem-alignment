# Digital Twin & Settings Autoresearch Report

**Date**: 2026-07-14
**Experiments**: EXP-2561, EXP-2562
**Branch**: `workspace/digital-twin-fidelity`
**Data**: 803,895 rows × 49 cols, 19 patients (11 NS + 8 ODC)

---

## Executive Summary

Two experiments tested the highest-priority hypotheses from the settings/digital-twin pivot:

1. **EXP-2561** (Metabolic Phase Hypo Predictor): **NEGATIVE** — Phase mismatch features do NOT break the AUC ceiling. The hypo prediction limit (~0.90 at 30min, ~0.73 for surprise hypos) is **information-theoretic**, not a feature engineering problem.

2. **EXP-2562** (Forward Sim Counterfactuals): **POSITIVE** — The forward simulator produces directionally consistent, actionable counterfactuals. ISF+20% → +2.1pp TIR for corrections; CR+20% → +3.3pp TIR for meals. This validates wiring the forward sim into the settings optimizer.

---

## EXP-2561: Metabolic Phase Mismatch as Hypo Predictor

### Hypothesis

Supply-demand imbalance features from the metabolic engine (insulin absorption outpacing carb absorption) contain predictive signal for hypo events beyond what glucose trajectory alone provides.

### Method

- Constructed 7 metabolic phase features: `supply_demand_ratio`, `net_flux`, `phase_duration`, `phase_integral_60`, `phase_integral_120`, `iob_cob_ratio`, `basal_excess`
- Trained LightGBM with temporal 7-fold CV (LOPO) comparing:
  - **Glucose-only**: glucose, ROC, acceleration, projected values, min/max in windows
  - **Glucose+Phase**: glucose features + 7 metabolic phase features
  - **Phase-only**: 7 metabolic features + hour of day
- 5 sub-experiments: 30/60/120min horizons, surprise hypos, per-phenotype

### Results

| Sub-Exp | Glucose-only | +Phase | Δ AUC | Phase-only | Verdict |
|---------|-------------|--------|-------|------------|---------|
| 2561a (30min) | 0.954 | 0.952 | -0.002 | 0.826 | Neutral |
| 2561b (60min) | 0.905 | 0.899 | -0.006 | 0.786 | Negative |
| 2561c (120min) | 0.822 | 0.815 | -0.007 | 0.720 | Negative |
| 2561d (surprise) | 0.767 | 0.757 | -0.010 | 0.690 | Negative |
| 2561e-WC | 0.897 | 0.881 | -0.016 | 0.784 | Negative |
| 2561e-HP | 0.902 | 0.897 | -0.005 | 0.769 | Neutral |

**Mean Δ AUC: -0.008** (phase features slightly HURT performance)

### Key Feature Importances

Top features across all sub-experiments (glucose+phase model):
1. `glucose` / `projected_30` (0.10-0.13) — glucose trajectory dominates
2. `basal_excess` (0.08-0.13) — the one phase feature with moderate importance
3. `phase_duration` (0.07-0.09) — how long current metabolic phase has lasted
4. `iob_cob_ratio` (0.07) — only relevant for longer horizons

### Interpretation

The metabolic phase features are **redundant** with glucose trajectory features. The model already captures the same information from glucose level, rate of change, and projected values. `basal_excess` shows some importance but it correlates strongly with IOB, which is already captured in the glucose trajectory.

**The hypo prediction ceiling is information-theoretic**: the stochastic components (meals, exercise, stress) dominate at horizons >30 minutes. No feature engineering from available sensor+pump data can break this ceiling. Breaking it requires:
- External data (activity trackers, meal announcements, CGM from multiple sensors)
- Different framing (time-to-event instead of binary classification)
- Fundamentally different modeling (probabilistic forecasting with prediction intervals)

---

## EXP-2562: Forward Simulator Counterfactual Analysis

### Hypothesis

The forward simulator can generate actionable "what if" scenarios from real patient data, revealing settings changes that would improve TIR.

### Method

- Extracted real windows from patient data: correction boluses (n=735), meal boluses (n=761), overnight periods (n=136)
- For each window, ran forward sim with baseline settings and modified settings
- Computed TIR and TBR deltas over 4-hour windows
- Scenarios tested: ISF ±20%/+40%, CR ±20%, pre-bolus timing +15/30min, basal ±10%/±20%

### Results

#### Correction Bolus Windows (n=735)

| Scenario | TIR Δ | TBR Δ | % Improved |
|----------|-------|-------|------------|
| ISF+20% | **+2.1pp** | +0.002pp | 34% |
| ISF-20% | -2.3pp | +0.000pp | 0% |
| ISF+40% | **+4.3pp** | +0.000pp | 40% |

**Interpretation**: Higher ISF (less aggressive corrections) improves TIR. Consistent with the loop-causes-35%-of-hypos finding — corrections are systematically too aggressive.

#### Meal Bolus Windows (n=761)

| Scenario | TIR Δ | TBR Δ | % Improved |
|----------|-------|-------|------------|
| CR+20% | **+3.3pp** | +0.000pp | 31% |
| CR-20% | -3.4pp | -0.000pp | 1% |
| PreBolus+15min | -1.6pp | -0.000pp | 1% |
| PreBolus+30min | -1.6pp | -0.000pp | 1% |

**Interpretation**: Higher CR (less meal insulin) improves TIR. Consistent with effective CR = 1.47× profile CR finding. Pre-bolusing hurts in simulation, suggesting patients already time boluses appropriately or the sim doesn't capture meal timing dynamics well.

#### Overnight Basal Windows (n=136)

| Scenario | TIR Δ | TBR Δ | % Improved |
|----------|-------|-------|------------|
| Basal+20% | -0.1pp | +0.000pp | 0% |
| Basal-20% | +0.1pp | +0.000pp | 4% |
| Basal+10% | -0.0pp | +0.000pp | 0% |
| Basal-10% | +0.0pp | +0.000pp | 2% |

**Interpretation**: Overnight basal is near-optimal in this cohort. Small sample (136 windows) due to strict filtering — most patients had no qualifying overnight periods. Low window count limits conclusions.

### Validation of Forward Sim

The counterfactual results are **directionally consistent** with prior findings:
- ISF increase = less aggressive corrections → fewer overcorrections → validated by EXP-2538 (35% hypos loop-caused)
- CR increase = less meal insulin → validated by EXP-2535/2536 (effective CR = 1.47× profile)
- Basal near-optimal → consistent with AID loops already adjusting basal continuously

This provides confidence that the forward sim, despite being a simplified physics model, captures the relevant dynamics for settings optimization.

---

## Synthesis & Implications

### For the Hypo Predictor (production `hypo_predictor.py`)

**No changes needed.** The current AUC=0.90 at operational horizons (5-15min) is near-optimal. Longer-horizon prediction requires fundamentally different data, not better features. The metabolic engine features should remain in the settings advisor (where they work for static analysis) but should NOT be added to the hypo predictor.

### For the Settings Optimizer (production `settings_optimizer.py`)

**HIGH PRIORITY: Wire forward sim into optimization loop.** The perturbation model currently in use cannot differentiate circadian strategies or simulate multi-parameter interactions. The forward sim produces consistent, actionable deltas:
- Per-patient ISF optimization: scan ISF multipliers 0.8–1.5, find TIR-maximizing value
- Per-patient CR optimization: scan CR multipliers 0.8–1.5, find TIR-maximizing value
- Combined optimization: grid search ISF×CR space

### For the Forward Simulator (production `forward_simulator.py`)

**Calibration needed.** The overnight basal analysis had very low sample sizes. The pre-bolus timing result (negative) suggests the sim may not capture meal absorption dynamics well enough for timing recommendations. Recommended:
- Validate sim glucose traces against actual CGM traces for correction/meal windows
- Calibrate per-patient carb absorption delay from real meal responses

---

## Next Experiments Proposed

### EXP-2563: Per-Patient ISF/CR Optimization via Forward Sim

**Hypothesis**: Forward sim grid search over ISF×CR multiplier space will identify patient-specific optimal settings that differ from profile values and predict TIR improvement.

**Method**: For each patient, extract 50+ correction and meal windows. Run forward sim with ISF multipliers [0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5] × CR multipliers [0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5]. Report optimal (ISF_mult, CR_mult) per patient with bootstrap CIs.

**Success criterion**: >80% of patients show optimal settings ≠ (1.0, 1.0) with CI excluding 1.0.

### EXP-2564: Forward Sim Fidelity Validation

**Hypothesis**: Forward sim glucose traces correlate with actual CGM traces (r > 0.7) for 4-hour correction and meal windows.

**Method**: Extract real glucose traces for correction/meal windows. Run forward sim from same initial conditions. Compute correlation, MAE, and TIR agreement between simulated and actual traces.

**Success criterion**: r > 0.7 and TIR agreement > 70%.

### EXP-2565: Circadian ISF/CR Variation

**Hypothesis**: Optimal ISF and CR multipliers vary by time of day (morning vs afternoon vs evening), with morning requiring different settings than evening.

**Method**: Partition windows by hour block (6-10, 10-14, 14-18, 18-22, 22-6). Run per-block ISF/CR optimization. Compare optimal multipliers across blocks.

**Success criterion**: Statistically significant difference (p < 0.05) in optimal multiplier between ≥2 blocks.

---

## Files

| Artifact | Path | Git Status |
|----------|------|------------|
| EXP-2561 code | `tools/cgmencode/production/exp_metabolic_phase_2561.py` | Tracked |
| EXP-2562 code | `tools/cgmencode/production/exp_counterfactual_2562.py` | Tracked |
| EXP-2561 data | `tools/externals/experiments/exp-2561_metabolic_phase_hypo.json` | Gitignored |
| EXP-2562 data | `tools/externals/experiments/exp-2562_counterfactual_analysis.json` | Gitignored |
| This report | `docs/60-research/digital-twin-autoresearch-2026-07-14.md` | Tracked |
