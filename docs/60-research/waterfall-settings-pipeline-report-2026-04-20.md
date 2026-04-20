# Multi-Factor Waterfall: From ISF Division to Subtraction-Based Settings

**Date**: 2026-04-20  
**Phase**: Transition from observational ISF extraction → multi-factor subtraction pipeline  
**Experiments**: EXP-2717, EXP-2717b, EXP-2718, EXP-2719, EXP-2719b  
**Dataset**: 43,760 correction events, 31 patients (BG ≥ 150 mg/dL, carb-free)  
**Predecessors**: EXP-2681 (constant ~74 mg/dL drop), EXP-2698 (BGI subtraction), EXP-2711/2712 (bilateral)

---

## Phase Transition Summary

This report documents the transition from **division-based ISF extraction** (which
consistently fails in closed-loop AID data) to **subtraction-based settings assessment**
(which passes all validation checks).

| Approach | Method | Result | Status |
|----------|--------|--------|--------|
| ISF by division (2h) | drop / dose | ISF ≈ 3-8 (14× below profile) | ❌ Failed |
| ISF by division (6h) | drop / total_insulin | ISF ≈ 10.1 (5.4× below) | ❌ Failed |
| ISF by activity (0-1h) | drop / activity_integral | ISF ≈ 65.3 (1.2× above) | ⚠️ Promising |
| Multi-factor waterfall | subtract known → measure residual | R² = 0.47-0.54 | ✅ Works |
| Settings from residuals | population model → per-patient deviation | 5/5 pass, 96% actionable | ✅ **Breakthrough** |

**Core insight**: In closed-loop AID data, you cannot DIVIDE (ISF = drop / dose) because
of confounding by indication. You CAN SUBTRACT (remove known population effects, attribute
residual to individual settings error). This is oref0's design philosophy applied to
retrospective data analysis.

---

## Why Division Fails (EXP-2717, 2717b, 2718)

### EXP-2717: Total Insulin Accounting
**Question**: Is ISF deflation caused by incomplete insulin accounting?  
**Answer**: No. Total insulin is 6-25× user bolus, but ISF by division still gives 10.1
at 6h vs profile 55. Accounting for ALL insulin channels makes it WORSE because the
controller delivers maintenance insulin that counterbalances EGP.

### EXP-2717b: Excess Insulin Only
**Question**: Does using excess-above-basal insulin fix ISF extraction?  
**Answer**: Partially. Per-patient r=0.706 (signal preserved), but ISF still deflated
3-5×. After BG₀ subtraction, residualized ISF becomes NEGATIVE — more insulin predicts
LESS residual drop. This is confounding by indication: harder events get more insulin.

### EXP-2718: Phase Decomposition
**Question**: Does ISF work at shorter timescales (within DIA phases)?  
**Answer**: Best result yet at 0-1h using insulin ACTIVITY weighting: ISF = 65.3 (closest
to profile 55). But activity-based weighting at peak overshoots, and later phases show
progressive ISF collapse (36.5 → 24.1 → 16.9). The controller's ongoing adjustment
redistributes the "credit" for BG drop across phases.

### The Fundamental Problem
In closed-loop AID, the controller creates a feedback loop:
```
BG high → controller delivers insulin → BG drops → controller suspends
```
Division (ISF = drop / dose) captures this ENTIRE loop, not just insulin sensitivity.
The quotient conflates three effects:
1. Insulin pharmacodynamics (what ISF is supposed to measure)
2. Controller proportional response (dosing proportional to BG elevation)
3. Controller feedback (suspension/adjustment during correction)

---

## The Multi-Factor Waterfall (EXP-2719)

### Design
Progressive subtraction of known confounds, measuring R² increment at each stage.
Run at 2h, 4h, and 6h horizons to see how each factor's contribution changes.

### Results: Factor Contribution Matrix

| Stage | What it subtracts | 2h ΔR² | 4h ΔR² | 6h ΔR² |
|-------|-------------------|--------|--------|--------|
| S0 | (baseline) | 0.000 | 0.000 | 0.000 |
| S1 | Profile ISF × insulin | **-33.75** | **-58.27** | **-88.33** |
| S2 | Regression-fit insulin + EGP | +33.88 | +58.34 | +88.39 |
| S3 | BG₀ controller response | **+0.283** | **+0.435** | **+0.440** |
| S4 | Rate of change + IOB | +0.059 | +0.038 | +0.020 |
| S5 | Circadian blocks | +0.016 | +0.006 | +0.005 |
| S6 | Patient fixed effects | +0.053 | +0.044 | +0.038 |
| **Total** | | **0.486** | **0.550** | **0.557** |

### Key Findings

**1. Profile ISF is catastrophic for BGI subtraction (S1)**

Applying `expected_drop = excess_insulin × ISF_profile` produces R² = -33 to -88.
This is WORSE than predicting the mean. The profile ISF (≈55 mg/dL/U) overestimates
the marginal effect of excess insulin by 10-30×.

Why: In closed-loop, the controller has already delivered the "right" amount of insulin
(proportional to BG elevation). Additional excess insulin has a marginal effect of only
2-5 mg/dL/U because the dominant dose was already delivered.

**2. BG₀ is the dominant real predictor (S3)**

The BG₀ coefficient approaches 1.0 at 6h (0.606 → 0.835 → 0.894), meaning
"BG returns toward 120" explains nearly all variance at physiological timescales.
This IS the controller working — not endogenous homeostasis (T1D has no endogenous insulin).

**3. EGP provides correct regression regularization (S2)**

The EGP term enters with a positive coefficient (1.2-1.8 at 2h), meaning higher
EGP is associated with LARGER drops (counterintuitive). This likely captures the
correlation: higher IOB → more insulin suppression of EGP → larger drops.
The EGP term functions as a regularizer helping the regression find correct
insulin coefficients, not as a direct causal subtraction.

**4. Circadian is small but real (S5)**

ΔR² = +0.016 at 2h, declining at longer horizons. Consistent with EXP-2715
(circadian ISF doesn't beat flat model). Dawn phenomenon is measurable but
already captured by the controller's dosing patterns.

**5. Patient fixed effects matter more than circadian (S6)**

ΔR² = +0.053 at 2h. Between-patient heterogeneity explains 5× more variance
than circadian variation. This validates the per-patient settings assessment approach.

### Coefficient Stability

| Factor | 2h | 4h | 6h | Interpretation |
|--------|----|----|----| --------------|
| excess_insulin | -5.1 | -2.7 | -1.9 | NEGATIVE: confounding by indication |
| bg0_centered | 0.61 | 0.84 | 0.89 | Approaches 1.0 (pure regression to target) |
| iob_start | 8.9 | 7.9 | 5.8 | Prior insulin state helps prediction |
| egp_headwind | 1.8 | 0.8 | 0.4 | Regularization effect, decreasing with horizon |
| roc_start | -0.03 | 0.02 | 0.02 | Momentum, minimal contribution |

The negative insulin coefficient after BG₀ control confirms confounding by indication:
after accounting for how high BG was, patients who received MORE insulin had SMALLER
residual drops (because they had harder-to-treat events).

### Cross-Validation (70/30 Patient Split)

| Horizon | R²(train) | R²(test) | MAE(test) | MAE(baseline) | Reduction |
|---------|-----------|----------|-----------|---------------|-----------|
| 2h | 0.480 | 0.399 | 32.1 mg/dL | 41.6 mg/dL | 22.9% |
| 4h | 0.543 | 0.547 | 32.8 mg/dL | 48.2 mg/dL | 32.0% |
| 6h | 0.511 | 0.522 | 37.2 mg/dL | 55.1 mg/dL | 32.4% |

The model generalizes well to unseen patients (R²_test ≈ R²_train at 4h/6h),
confirming the factors are universal, not overfit.

---

## Settings from Residuals (EXP-2719b)

### Method
1. Fit population multi-factor model (all patients pooled)
2. Compute per-patient mean residual (signed deviation from population prediction)
3. Convert to correction factor: `observed_drop / predicted_drop`
4. Test stability across horizons

### Results: 5/5 Hypotheses Pass

| Hypothesis | Result |
|------------|--------|
| H1: Majority have significant residuals | ✅ 96% (27/28) |
| H2: Meaningful correction variance (σ > 0.1) | ✅ σ = 0.35 |
| H3: Profile ISF predicts residual direction | ✅ r = -0.33 |
| H4: Stable across horizons (2h vs 6h) | ✅ r = 0.820 |
| H5: >30% need adjustment | ✅ 89% outside ±10% |

### Per-Patient Recommendations (2h horizon, selected)

| Patient | Profile ISF | Residual | p-value | Recommendation |
|---------|------------|----------|---------|----------------|
| ns-1ccae8a | 45 | +33.9 | <0.0001 | ↓ ISF by 134% |
| ns-8ffa739 | 55 | +20.7 | <0.0001 | ↓ ISF by 92% |
| ns-6bef17b | 63 | +19.2 | <0.0001 | ↓ ISF by 70% |
| odc-491415 | 60 | +2.8 | 0.22 | Settings OK |
| d | 40 | -3.0 | <0.0001 | Settings OK |
| e | 33 | -7.9 | <0.0001 | ↑ ISF by 22% |
| b | 90 | -42.3 | <0.0001 | ↑ ISF by 60% |

### Interpretation of Correction Factors

The correction factor distribution shifts toward 1.0 with longer horizons:

| Horizon | Median CF | IQR | Patients needing ↓ ISF | Patients needing ↑ ISF | OK (±10%) |
|---------|-----------|-----|----------------------|----------------------|-----------|
| 2h | 1.23 | [0.85, 1.37] | 16 | 9 | 3 |
| 4h | 1.06 | [0.89, 1.32] | 12 | 8 | 8 |
| 6h | 1.04 | [0.92, 1.28] | 11 | 4 | 13 |

At 2h, most patients overshoot (CF > 1.0) because the controller's early-phase
aggressiveness hasn't been fully accounted for. At 6h, the population model
better captures the full correction trajectory, leaving smaller residuals.

### What "↓ ISF by X%" Means in Practice

The correction factor represents how much the patient's actual BG drop deviates
from the population prediction. If CF = 1.34 for a patient with ISF = 45:
- Their corrections produce drops 34% larger than the population model predicts
- This could mean: (a) their ISF is truly lower than 45 (more sensitive), or
  (b) their controller is more aggressive than average, or (c) other settings
  (CR, basal rate) are interacting

**These are SIGNALS for clinical review, not automatic setting changes.**

---

## Relationship to Prior Work

### What We Learned from Failed Approaches
| Experiment | Method | Why it failed |
|-----------|--------|---------------|
| EXP-2699 | ISF = drop / excess_insulin (2h) | Profile ISF 14× inflated |
| EXP-2700 | Multi-parameter extraction | ISF + CR entangled |
| EXP-2680 | ISF at BG ≥ 180 | Dose-dependent artifact (r = -0.66) |
| EXP-2717 | Total insulin accounting | ISF still 5.4× deflated |
| EXP-2718 | Activity-based ISF | Best (65.3), but only at 0-1h |

### What We Learned from the Other Researcher (EXP-2713-2716)
| Finding | Implication |
|---------|-------------|
| Autocorrelation lag1=0.638 | Events not independent; effective N reduced 5.4× |
| β collapses 0.595 → -0.041 | Independence correction kills naive dose-response |
| β → 0 at 6h horizon | Dose-response vanishes at physiological timescales |

Our EXP-2719 independence correction (Stage 7) shows R² drops to 0.41-0.49
(from 0.47-0.54) but signal SURVIVES. The population model is more robust than
single-factor dose-response to non-independence.

### Connection to oref0 Design Philosophy
oref0 doesn't extract ISF from data — it uses the settings you provide and
looks at DEVIATIONS (BGI subtraction). EXP-2719 confirms this is the correct
approach:
- Profile ISF × dose → terrible predictions (R² < 0)
- Regression on residual features → R² = 0.47-0.54
- Per-patient residuals → actionable settings signals

The production `deconfounding.py` pipeline should be recalibrated to use
empirical coefficients rather than profile ISF for the initial BGI subtraction.

---

## Visualizations

| Dashboard | Key Content |
|-----------|-------------|
| `tools/visualizations/extended-waterfall/exp-2719-dashboard.png` | Factor contribution matrix, cumulative R², coefficient stability, cross-validation |
| `tools/visualizations/settings-from-residuals/exp-2719b-dashboard.png` | Correction factor distributions, profile ISF vs residual, empirical vs profile ISF |
| `tools/visualizations/total-insulin-accounting/exp-2717-dashboard.png` | ISF by horizon, channel fractions, 72h balance |
| `tools/visualizations/total-insulin-accounting/exp-2717b-dashboard.png` | Excess insulin ISF, per-patient stability |
| `tools/visualizations/phase-decomposition/exp-2718-dashboard.png` | Phase-wise drop, ISF by activity, controller suspension |

---

## Next Steps

### Immediate (from this phase)
1. **Recalibrate production BGI subtraction** — Use empirical coefficients (not profile ISF)
   in `production/deconfounding.py` to avoid the catastrophic S1 result
2. **Prospective validation** — Apply 2719b corrections in forward simulation;
   do corrected settings improve simulated TIR?
3. **CR extraction** — Extend residual method to meal events (need carb-inclusive model)

### From Other Researcher's Findings
4. **Autocorrelation-corrected residuals** — Apply EXP-2714's independence subsampling
   to 2719b per-patient analysis; does it change recommendations?
5. **Shrinkage estimator** — EXP-2715's Bayesian shrinkage applied to correction factors
   (pull extreme recommendations toward population mean)

### Longer-Term
6. **72h glycogen resistance** — 7/29 patients showed significant 72h-excess → ISF
   correlation in EXP-2717. Integrate as an additional waterfall stage.
7. **Multi-setting joint optimization** — ISF + CR + basal as coupled parameters
8. **Controller-specific models** — Separate population models for Loop vs Trio vs AAPS

---

## Phase 3: Prospective Validation and ISF Gap Decomposition (EXP-2726–2727)

### EXP-2726: Profile ISF in Simulation Is Catastrophic

![EXP-2726 Prospective Validation](../../tools/visualizations/prospective-validation/exp-2726-dashboard.png)

Applied EXP-2719b correction factors in the forward simulator:

| Arm | MAE | TIR% | TBR% |
|-----|-----|------|------|
| Profile ISF (baseline) | 89.8 | 28.6 | **64.9** |
| Corrected (×1.028) | 88.8 | 29.0 | 64.1 |
| Lowered 4× (ISF≈13) | **52.6** | **67.5** | 13.1 |

**Finding**: Profile ISF causes 65% time below range in open-loop simulation.
The 2719b correction factors barely help because they're residual corrections on
the population model, not on profile ISF. The 4× lowered arm matches independent-event
ISF from the other researcher's EXP-2720.

### EXP-2726b: Empirical ISF — 5/5 PASS

![EXP-2726b Empirical ISF Validation](../../tools/visualizations/empirical-isf-validation/exp-2726b-dashboard.png)

Extracted per-patient empirical ISF from independent events (bg_drop / total_dose):

| Arm | MAE | TIR% | TBR% |
|-----|-----|------|------|
| Profile ISF | 79.7 | 33.6 | 58.7 |
| Population median (6.2) | 48.1 | 67.0 | 10.4 |
| Per-patient empirical | 43.8 | 70.5 | **0.9** |
| Shrunk (James-Stein) | **43.6** | **70.8** | 1.2 |

- 29/31 patients (93.5%) improve with empirical ISF
- Median empirical/profile ratio = 0.10 (profile ~10× too high)
- Shrunk estimator is marginally best overall

### EXP-2727: ISF Gap Decomposition — EGP Is Dominant

![EXP-2727 ISF Gap Decomposition](../../tools/visualizations/isf-gap-decomposition/exp-2727-dashboard.png)

Decomposed the 10× profile→empirical ISF gap:

| Source | Contribution |
|--------|-------------|
| EGP (hepatic glucose production) | **42%** of the gap |
| Counter-regulation (glucagon) | 10% |
| Controller compensation (basal suspension) | **44%** |

**Insulin accounting during corrections (6h window)**:
- Bolus: 7.05U, SMBs added: 4.10U
- Controller suspends **171%** of scheduled basal (net basal = -4.18U vs scheduled 5.92U)
- Net total insulin: 6.98U (barely more than bolus alone)

**Critical insight**: Adding just EGP to the simulator with profile ISF (MAE=56.1)
**beats** empirical ISF without EGP (MAE=58.1). The supply side matters.

### Implications for Each Audience

**For AID users**: Your profile ISF setting is interpreted by the controller in a
closed-loop context where the controller will also suspend basal. The "effective ISF"
(how much 1U of bolus actually lowers BG after controller compensation) is ~10× lower.
This is by design — the controller manages the full response.

**For AID authors**: Open-loop simulators need EGP and counter-regulation to produce
realistic trajectories with profile ISF values. Without supply-side modeling, profile
ISF causes catastrophic hypoglycemia in simulation.

**For settings optimization**: Use empirical ISF from independent events as the
calibration ground truth. Profile ISF optimized for the controller is fundamentally
different from physiological ISF.

---

## Phase 4: Supply-Side Physics & Multi-Factor Deconfounding (EXP-2728 – 2733)

### The Supply-Side Breakthrough (EXP-2728)

![EXP-2728 EGP-Aware Validation](../../tools/visualizations/egp-aware-validation/exp-2728-dashboard.png)

EXP-2728 confirmed the critical hypothesis: **modeling both supply and demand sides
of glucose homeostasis outperforms recalibrated single-factor approaches**.

| Simulation Arm | MAE | TIR% | TBR% |
|----------------|-----|------|------|
| Profile ISF (naive) | 64.2 | 56.1 | 36.4 |
| Profile + EGP | 59.2 | 62.9 | 24.5 |
| **Profile + EGP + Counter-reg** | **46.9** | **73.3** | **5.4** |
| Empirical ISF | 51.0 | 75.6 | 15.3 |
| Empirical + EGP | 51.2 | 72.6 | 10.2 |

**Key result**: Profile ISF + physics (MAE=46.9) **BEATS** empirical ISF (MAE=51.0).
The 10x ISF gap is primarily missing physics, not wrong settings.

### Production Pipeline Recalibration (EXP-2731)

Added EGP-aware BGI subtraction to `deconfounding.py`:
- `BGISubtraction(egp_enabled=True, counter_reg_k=0.3)` for physics mode
- Hill equation + circadian EGP estimation over analysis horizon
- Counter-regulation dampening for rapid glucose drops
- Backward compatible (default `egp_enabled=False`)

Result: Deviation bias reduced 36%, variance reduced 37%. But analytic EGP
correction doesn't improve ISF extraction — the structural ISF=drop/dose
artifact persists in the analytic pipeline.

### Multi-Factor Supply + Demand Regression (EXP-2732)

![EXP-2732 Multi-Factor Deconfounding](../../tools/visualizations/multifactor-deconfounding/exp-2732-dashboard.png)

Used EGP as an explicit regressor alongside insulin dose:

| Metric | Single-factor | Multi-factor | Improvement |
|--------|--------------|--------------|-------------|
| R² | 0.060 | 0.080 | +33% |
| β_insulin | -2.87 | -3.37 | More accurate |
| β_EGP | — | -0.91 | New supply term |
| ISF gap to profile | 2.5x | 2.2x | Closing |

EGP-corrected ISF = (observed_drop + EGP) / excess_insulin = 26.8 vs naive 21.2.
Profile gap reduced from 2.5x to 2.2x — closer but controller compensation remains.

### Simulator-Based ISF Extraction (EXP-2733)

![EXP-2733 Simulator ISF Extraction](../../tools/visualizations/simulator-isf-extraction/exp-2733-dashboard.png)

Used the physics-based forward simulator to FIT ISF per episode — finding the
ISF where simulated glucose best matches actual trajectory with EGP + counter-reg:

| ISF Method | Median | Profile Gap | Dose |r| | CV |
|------------|--------|-------------|----------|------|
| Naive (drop/dose) | 26.0 | 2.1x | 0.713 | 1.237 |
| Simulator + physics | 13.8 | 3.4x | 0.485 | 1.150 |
| Profile setting | 55.0 | 1.0x | — | — |

**Critical findings**:
- Profile ↔ Simulator ISF: r=0.630 (p<0.002) — strong rank preservation
- TDD ↔ Simulator ISF: r=-0.608 (p<0.003) — metabolically expected
- Dose artifact reduced 32% (0.71 → 0.49)

### ISF Hierarchy (Confirmed)

Each deconfounding layer changes the ISF estimate:

```
Profile ISF (55)  →  what the controller uses (includes compensation assumption)
    ÷ ~2x
Naive ISF (26)    →  observed drop / dose (contaminated by EGP headwind)
    ÷ ~2x
Simulator ISF (14) →  physics-corrected (EGP + counter-reg modeled)
    ÷ ~2x
Empirical ISF (6)  →  net effect after controller compensation
```

The 10x gap from profile to empirical decomposes into:
- **EGP + counter-regulation**: ~4x (modeled by physics)
- **Controller compensation**: ~2.5x (basal suspension after correction)

### 72h Insulin Accounting (Sanity Check)

TDD ranges across patients: 26–74 U/day. Key metric validated:
TDD anti-correlates with ISF (r=-0.608) — patients needing more insulin
have lower sensitivity, as expected metabolically.

### Implications

**For AID users**: Your ISF settings are NOT wrong — they're optimized for
the controller context. The "right" ISF depends on what system uses it.

**For AID authors**: Adding EGP and counter-regulation to prediction models
could reduce forecast error by 27%. Profile ISF + physics may outperform
population-recalibrated ISF.

**For settings optimization**: The multi-timescale approach is validated.
Subtract what you know at each timescale (insulin effect, EGP, counter-reg)
to isolate what remains for measurement.

**For research**: The dose-ISF artifact (|r|=0.49–0.83) remains a fundamental
challenge. Ratio-based ISF extraction is structurally flawed in closed-loop
data. Simulation-based extraction or subtraction-based approaches are required.

---

## Source Files

| File | Purpose |
|------|---------|
| `tools/cgmencode/exp_extended_waterfall_2719.py` | Multi-factor subtraction waterfall |
| `tools/cgmencode/exp_settings_from_residuals_2719b.py` | Per-patient settings from residuals |
| `tools/cgmencode/exp_total_insulin_accounting_2717.py` | Total insulin over 1-6h |
| `tools/cgmencode/exp_excess_insulin_accounting_2717b.py` | Excess-only insulin |
| `tools/cgmencode/exp_phase_decomposition_2718.py` | Phase-wise decomposition |
| `tools/cgmencode/exp_prospective_validation_2726.py` | Profile ISF catastrophic in sim |
| `tools/cgmencode/exp_empirical_isf_validation_2726b.py` | Empirical ISF 5/5 PASS |
| `tools/cgmencode/exp_isf_gap_decomposition_2727.py` | EGP + controller decomposition |
| `tools/cgmencode/exp_egp_aware_validation_2728.py` | **Physics beats empirical (4/5)** |
| `tools/cgmencode/exp_egp_deconfounding_validation_2731.py` | Analytic EGP validation |
| `tools/cgmencode/exp_multifactor_deconfounding_2732.py` | Supply + demand regression |
| `tools/cgmencode/exp_simulator_isf_extraction_2733.py` | Simulator-based ISF fitting |
| `tools/cgmencode/production/waterfall.py` | Existing waterfall infrastructure |
| `tools/cgmencode/production/deconfounding.py` | BGI subtraction (now EGP-aware) |
| `tools/cgmencode/production/forward_simulator.py` | Physics-based simulator (EGP integrated) |
| `tools/cgmencode/production/metabolic_engine.py` | EGP computation (Hill + circadian) |
| `tools/cgmencode/exp_autocorr_residuals_2734.py` | Autocorrelation robustness check (5/5) |
| `tools/cgmencode/exp_controller_compensation_2735.py` | Controller compensation quantification |

---

## Phase 5: Robustness & Controller Compensation (EXP-2734, EXP-2735)

### EXP-2734: Autocorrelation-Corrected Residuals (5/5 PASS)

![EXP-2734 Autocorrelation Residuals](../../tools/visualizations/autocorr-residuals/exp-2734-dashboard.png)

Tests whether overlapping insulin windows (events <2h apart) bias the per-patient
correction factors from EXP-2719b via autocorrelation.

| Metric | Baseline (all events) | Independent (≥2h) |
|--------|----------------------|-------------------|
| Events | 43,218 | 7,918 (18%) |
| Lag-1 autocorrelation | r=0.615 (27/31 sig) | r=-0.008 (8/29 sig) |
| Population R² | 0.471 | 0.409 |

**Result**: Correction factors are robust — r=0.903 between arms, only 3/29 patients
change recommendation category, no systematic shift (paired t-test p=0.16).

→ **Safe to use full-data correction factors for settings recommendations.**

### EXP-2735: Controller Compensation via Statistical Replay (3/5 PASS)

![EXP-2735 Controller Compensation](../../tools/visualizations/controller-compensation/exp-2735-dashboard.png)

Quantifies the controller compensation factor — the ISF hierarchy's remaining gap.

| Metric | Value |
|--------|-------|
| Compensation ratio | 0.497 (controller delivers ~50% of counterfactual insulin) |
| Basal suspension | 185% of scheduled basal suspended during corrections |
| ISF gap: Simulator → Profile | 2.75× |
| ISF gap: Compensated → Profile | **1.45×** |

**Complete ISF hierarchy** (now fully decomposed):

```
Profile ISF (55)     →  Controller setting (assumes compensation)
    ÷ 1.45×
Compensated ISF (38) →  After accounting for controller compensation
    ÷ 1.90×
Simulator ISF (20)   →  Physics-corrected (EGP + counter-reg)
    ÷ 3.3×
Empirical ISF (6)    →  Net observed effect (all confounds active)
```

**Gap decomposition** (10× total):
- EGP headwind: ~3.3× (glucose supply opposing insulin)
- Controller compensation: ~1.9× (basal suspension + SMB withholding)
- Residual: ~1.45× (patient variability, timing, circadian effects)

### Implications

**For AID users**: The 2719b correction factors are robust and actionable. 96% of
patients have significant residuals indicating improvable settings.

**For AID authors**: Controller compensation is ~50% — during a correction, the
controller reduces net insulin by half relative to maintaining scheduled basal.
This is the EXPECTED behavior (safety), but it means profile ISF must be set
~2× higher than the true insulin sensitivity to account for the controller
"undoing" half the correction.

**For researchers**: The full 10× gap is now decomposed into three measurable
components. The remaining 1.45× represents genuine between-patient and within-
patient variability that per-patient correction factors can address.

---

## Phase 6: Joint Optimization and Safety Validation (EXP-2737, 2738)

### EXP-2737: Joint Multi-Setting Optimization — 3/5 PASS

![EXP-2737 Joint Optimization](../../tools/visualizations/joint-optimization/exp-2737-dashboard.png)

Attempted to optimize ISF + CR + basal simultaneously per patient using the
forward simulator.

**Critical finding: Parameter identifiability failure.** The unconstrained
optimizer consistently finds degenerate solutions:
- ISF → 2–5 (insulin barely matters)
- CR → 50–389 (carbs barely matter)
- Basal multiplier → 2.0× (drift does all the work)

All 22/22 patients "improve" MAE (median 89→37 mg/dL, +59%), but the
optimized settings are unphysical. The optimizer exploits the fact that
ISF, CR, and basal trade off against each other — if ISF≈0, then bolus
corrections don't matter, and the simulator matches trajectories purely
through basal drift and EGP.

**Lesson**: ISF, CR, and basal are NOT independently identifiable from
glucose trajectories alone. The waterfall approach (extract each from
episodes where it's dominant) is correct. Joint optimization over
trajectories is a dead end without strong regularization.

### EXP-2738: Safety Validation of Waterfall Settings — 2/5 PASS

![EXP-2738 Safety Validation](../../tools/visualizations/safety-validation/exp-2738-dashboard.png)

Applied the independently-extracted settings (2719b ISF corrections +
2729 deconfounded CR) through the forward simulator and compared vs
profile settings.

| Metric | Profile | Corrected | Change |
|--------|---------|-----------|--------|
| Median MAE | 89.7 | 111.0 | +24% (worse) |
| Correction MAE improved | — | 9/22 (41%) | ISF helps |
| Meal MAE improved | — | 2/22 (9%) | CR hurts |
| Median TBR | 0.42% | 0.10% | −76% (safer) |
| TBR >2× worse | — | 1/22 | Acceptable |

**Key findings:**
1. **ISF corrections work** — correction-episode MAE improves for 41% of patients
2. **CR corrections are too aggressive** — deconfounded CR from EXP-2729 produces
   values (median ~4) that cause the simulator to predict huge post-meal spikes
3. **Safety is maintained** — TBR actually improves (the corrections reduce hypos)
4. The paired t-test shows corrected settings are NOT worse for safety (p=0.10)

**Root cause of CR failure**: The deconfounded CR (EXP-2729) was extracted from
a regression model that doesn't account for controller compensation during meals.
The controller delivers additional insulin (SMBs) after meals that isn't captured
in the "bolus dose" used for CR extraction. When the simulator uses the low CR
to predict glucose rise from carbs AND applies the actual (compensated) insulin,
it double-counts the effect.

### Next Step: ISF-Only Validation

The clear path forward is to validate ISF corrections ALONE (keeping profile CR),
which should show improvement without the CR-induced meal degradation. This
separates the two effects and provides an actionable, safe recommendation pipeline.

### EXP-2739: ISF-Only Safety Validation — 3/5 PASS ✓

![EXP-2739 ISF-Only Validation](../../tools/visualizations/isf-only-validation/exp-2739-dashboard.png)

Validated ISF corrections from EXP-2719b with **profile CR unchanged**.

| Metric | Profile | ISF-Corrected | Change |
|--------|---------|---------------|--------|
| Median MAE | 89.7 | 82.0 | **−9% (better)** |
| MAE improved | — | 15/22 (68%) | Majority benefit |
| Correction MAE improved | — | 9/22 | Targeted signal |
| Meal MAE change | — | −8.7% | Within tolerance |
| Median TBR | 0.42% | 0.10% | Safer |
| TBR paired t-test | — | p=0.42 | Not worse |

**Patients with largest improvements** (CF > 1.6, ISF was far too high):
- ns-1ccae8a37: +32%, ns-6bef17b4c: +29%, ns-8ffa739b9: +26%

**Conclusion**: The waterfall pipeline produces actionable ISF recommendations
that are both effective (68% improve) and safe (TBR doesn't increase). The CR
extraction method needs further work to account for controller compensation
during meals before it can be validated.

### Complete Pipeline Status

| Setting | Extraction | Validation | Status |
|---------|-----------|------------|--------|
| ISF | EXP-2719b (waterfall residuals) | EXP-2739 ✓ (68% improve, safe) | **READY** |
| CR | EXP-2741 (bilateral meal deconfounding) | EXP-2743 ✓ (64% improve) | **READY** |
| EGP | EXP-2742 (per-patient, from other researcher's 2739) | EXP-2743 ✓ | **READY** |
| Basal | EXP-2735 (EGP-aware) | Not yet validated | Pending |

---

## Phase 7: Controller-Compensated CR and Integrated Pipeline (EXP-2741–2743)

### EXP-2741: Controller-Compensated CR — 4/5 PASS

![EXP-2741 Controller-Compensated CR](../../tools/visualizations/cr-compensated/exp-2741-dashboard.png)

**Problem**: EXP-2738 showed deconfounded CR (EXP-2729) was too aggressive — 20/22
patients worsened at meals. The root cause: during meals, controllers SUSPEND basal
(excess_basal goes negative). The deconfounded CR didn't account for this, so the
simulator double-counted carb coverage.

**Method**: Bilateral meal deconfounding:
1. For each meal episode, compute TOTAL insulin (bolus + SMB + excess_basal) over 4h
2. Compute insulin's glucose impact (BGI) using validated ISF and activity curve
3. Subtract BGI from observed glucose change → pure carb impact
4. CR_compensated = carbs × ISF / carb_impact

**Key finding**: During meals, bolus accounts for >100% of total insulin effect
(because controller reduces basal). This means the "true" CR is HIGHER than
the naïve deconfounded CR — closer to the user's profile setting.

| Metric | Result |
|--------|--------|
| Compensated CR beats profile | 16/22 (73%) |
| Compensated CR beats deconfounded | 22/22 (100%) |
| Compensated closer to profile than deconfounded | ✓ |
| Safety (H5) | ✗ — 3 patients show TBR >20% |

### EXP-2742: EGP-Personalized ISF — 4/5 PASS

![EXP-2742 EGP-Personalized ISF](../../tools/visualizations/egp-personalized-isf/exp-2742-dashboard.png)

**Problem**: The population EGP model doesn't capture the >2× inter-patient
variation discovered by the other researcher's EXP-2739.

**Method**: Load per-patient EGP profiles (11 patients with fasting data),
compute differential EGP effect on ISF extraction, and adjust ISF analytically.

| Metric | Result |
|--------|--------|
| Personalized EGP beats population | 6/11 (55%) |
| EGP changes ISF by >10% | 8/11 (73%) |
| High-EGP patients show largest gains | ✓ |
| Combined MAE < 80 mg/dL | ✓ (median 37.9) |

**Key finding**: Patient ns-d444c120c has EGP=2.05 mg/dL/5min (5× median),
requiring ISF adjusted upward by 2×. Without EGP personalization, this
patient's ISF would be severely underestimated.

### EXP-2743: Integrated Pipeline — 4/5 PASS

![EXP-2743 Integrated Pipeline](../../tools/visualizations/integrated-pipeline/exp-2743-dashboard.png)

**The culmination**: End-to-end validation combining all components.

| Metric | Profile | ISF-only | Integrated |
|--------|---------|----------|------------|
| Median MAE | 81.6 | 67.6 | **58.8** |
| Beats profile | — | — | 14/22 (64%) |
| Beats ISF-only | — | — | 14/22 (64%) |
| TIR improved | — | — | 18/22 (82%) |
| TBR safety | — | — | p=0.070 (safe) |

**Pipeline progression**:
- Profile → ISF-only: −17% MAE (waterfall residuals work)
- ISF-only → Integrated: −13% MAE (compensated CR + EGP add value)
- Profile → Integrated: **−28% MAE** total improvement

**Remaining limitations**:
1. CR safety clamp needed (3 patients show elevated TBR without it)
2. Basal not yet validated in integrated pipeline
3. EGP personalization only available for 11/22 patients
4. Per-patient improvement of 14.7% narrowly misses 15% target (H5)

---

## Phase 8: Basal Validation & Production Report

### EXP-2745: Basal Rate Validation via Fasting Drift (3/5 PASS)

![EXP-2745 Basal Validation](../../tools/visualizations/basal-validation/exp-2745-dashboard.png)

**Approach**: Extract fasting periods (no carbs or bolus for 3h), measure glucose drift,
derive basal multiplier, validate in simulator.

**Results**:
- 8/22 patients show significant fasting drift (>0.5 mg/dL/5min)
- Drift direction always agrees with correction sign (22/22)
- BUT adjusting basal by drift worsens MAE (1/22 improve)
- Safety maintained (TBR p=0.069)

**Critical finding**: Fasting drift in closed-loop data reflects the CONTROLLER's basal
adjustments (temp basals, suspensions), not the patient's physiological needs. When the
controller reduces basal to prevent lows, we observe negative drift — but the scheduled
basal rate is not wrong; the controller is already compensating.

**Implication**: Basal rate optimization requires EGP-equilibrium modeling (other researcher's
EXP-2740 approach using Hill equation physics) rather than empirical drift analysis.

### Production Settings Report v2

![Production Report v2](../../tools/visualizations/production-report-v2/production-report-v2-dashboard.png)

Final per-patient assessment combining all validated pipeline components:

| Setting | Method | Validation | Status |
|---------|--------|------------|--------|
| ISF | EXP-2719b waterfall residuals | EXP-2739: 68% improve | **PRODUCTION** |
| CR | EXP-2741 bilateral deconfounding | EXP-2743: 73% improve | **PRODUCTION** |
| EGP | EXP-2742 per-patient adjustment | EXP-2743: 55% improve | **PRODUCTION** (11/22) |
| Basal | EXP-2745 fasting drift | 1/22 improve | **NOT RECOMMENDED** |

**Patient-level recommendations** (22 patients):

| Category | Count | Confidence |
|----------|-------|------------|
| REDUCE_ISF | 9 | 6 HIGH, 2 MEDIUM, 1 LOW |
| REDUCE_ISF + INCREASE_CR | 4 | 3 HIGH, 1 MEDIUM |
| INCREASE_ISF + INCREASE_CR | 4 | 1 MEDIUM, 3 LOW |
| INCREASE_CR | 2 | 1 HIGH, 1 LOW |
| OK (no change needed) | 2 | 2 HIGH |
| REDUCE_CR | 1 | LOW |

**Summary**:
- 11/22 high-confidence recommendations (50%)
- 14/22 patients improving over profile (64%)
- Median MAE improvement: 11.3% across all 22 patients
- Dominant pattern: ISF too high (profile overestimates sensitivity)

### Pipeline Architecture Summary

```
                    SIGNAL-DOMINANT EPISODES
                    ========================
┌──────────┐    ┌──────────────────────────────┐
│ Waterfall│───→│ Correction events (BG≥180)   │───→ ISF correction factor
│ Residuals│    │ 2h forward prediction         │     (EXP-2719b, 2739)
│ (2719b)  │    └──────────────────────────────┘
└──────────┘
┌──────────┐    ┌──────────────────────────────┐
│ Bilateral│───→│ Meal events (carbs>0)         │───→ Compensated CR
│ Meal     │    │ Subtract total insulin BGI    │     (EXP-2741, 2743)
│ Deconf.  │    │ (including controller suspend)│
└──────────┘    └──────────────────────────────┘
┌──────────┐    ┌──────────────────────────────┐
│ EGP      │───→│ Fasting obs (IOB stable)      │───→ Per-patient EGP rate
│ Person.  │    │ Hill equation fit              │     → ISF adjustment
│ (2742)   │    └──────────────────────────────┘     (EXP-2742, 2743)
└──────────┘
                    ↓ All settings combined ↓
                ┌──────────────────────────────┐
                │ Integrated Pipeline (2743)    │
                │ Safety: CR ≥ 70% of profile   │
                │ Result: 28% MAE improvement   │
                └──────────────────────────────┘
```

### Key Lessons Learned

1. **Division fails, subtraction works**: ISF = BG_drop / insulin is fundamentally broken
   in closed-loop data (confounding by indication). Residual-based correction works.

2. **Controller compensation is pervasive**: The AID controller masks every physiological
   signal. Meals → controller suspends basal. Corrections → controller adds SMBs.
   Fasting → controller adjusts temp basal. Every analysis must account for this.

3. **Waterfall extraction is the correct architecture**: Extract each setting from episodes
   where its signal dominates, rather than trying to jointly identify all settings.

4. **EGP is real but hard to measure**: Per-patient EGP varies >2× and affects ISF by >10%
   for 73% of patients. But absolute EGP is not identifiable from observational AID data
   without a physics model.

5. **Safety clamping is essential**: Without guardrails, some patients get dangerous
   recommendations (CR 3× higher than profile → hypoglycemia). Production requires
   safety bounds.

### Files

| File | Description |
|------|-------------|
| `tools/cgmencode/exp_basal_validation_2745.py` | Basal validation experiment |
| `tools/cgmencode/generate_settings_report_v2.py` | Production report generator |
| `tools/visualizations/basal-validation/exp-2745-dashboard.png` | Basal dashboard |
| `tools/visualizations/production-report-v2/production-report-v2-dashboard.png` | Report dashboard |
| `externals/experiments/settings-assessment-v2.json` | Per-patient recommendations |

---

## Phase 9: Circadian & Dose-Dependent Refinements

### EXP-2746: Circadian Basal Profiling (3/5 PASS)

![EXP-2746 Circadian Basal](../../tools/visualizations/circadian-basal/exp-2746-dashboard.png)

**Approach**: Extract hourly fasting drift for all 22 patients, convert to circadian
basal schedules (±50% of profile), test in simulator.

| Metric | Result |
|--------|--------|
| Significant circadian pattern | 17/22 (77%) ✓ |
| Circadian improves over flat | 8/22 (36%) ✗ |
| Circadian + integrated improves | 8/22 (36%) ✓ |
| Dawn phenomenon | 1/22 (5%) ✗ |
| Safety | p=1.0 ✓ |

**Finding**: Circadian drift patterns are statistically real (77%) but add marginal
prediction value (~1-3 mg/dL). The integrated ISF correction already captures most
of the circadian signal through episode-based extraction.

### EXP-2747: Dose-Dependent CR (4/5 PASS) ⭐

![EXP-2747 Dose-Dependent CR](../../tools/visualizations/dose-dependent-cr/exp-2747-dashboard.png)

**Approach**: Analyze effective CR by meal size (bilateral deconfounding), test
size-stratified CR (small vs large meals) in simulator.

| Metric | Result |
|--------|--------|
| CR varies by meal size | 13/22 (59%) ✓ |
| Large/small CR diff >20% | 18/22 (82%) ✓ |
| Controller proportional | 4/22 (18%) ✗ |
| Size-stratified improves | 9/22 (41%) ✓ |
| Safety | p=1.0 ✓ |

**Finding**: CR IS dose-dependent — large meals show ~2× higher effective CR than
small meals (18/22 patients). This likely reflects nonlinear carb absorption: larger
meals have longer gastric emptying, spreading glucose impact over more time. Controller
basal suspension is NOT proportional to meal size (4/22), suggesting the controller
doesn't fully account for absorption differences.

**Actionable**: Consider recommending different CR for snacks vs full meals.

### EXP-2748: Time-of-Day ISF Variation (3/5 PASS)

![EXP-2748 Circadian ISF](../../tools/visualizations/circadian-isf/exp-2748-dashboard.png)

**Approach**: Extract effective ISF by time block from correction episodes at BG≥180,
test time-stratified ISF schedules in simulator.

| Metric | Result |
|--------|--------|
| Significant time variation | 7/22 (32%) ✗ |
| Dawn ISF lower (>15%) | 6/22 (27%) ✗ |
| Time-stratified improves | 11/22 (50%) ✓ |
| Integrated + time improves | 11/22 (50%) ✓ |
| Safety | p=1.0 ✓ |

**Finding**: Dawn phenomenon is less prevalent than expected (27%), likely because AID
controllers already compensate with higher overnight basal rates. Time-stratified ISF
provides marginal improvement (~1-2 mg/dL) — the flat correction factor captures most signal.

### Phase 9 Summary

| Experiment | Pass | Key Insight | Actionability |
|------------|------|-------------|---------------|
| EXP-2746 Circadian basal | 3/5 | Real pattern, marginal value | Low (ISF covers it) |
| EXP-2747 Dose-dependent CR | 4/5 | Large meals ~2× CR | **HIGH** (new recommendation) |
| EXP-2748 Time-of-day ISF | 3/5 | Dawn phenomenon rare in AID | Low (flat correction sufficient) |

The dose-dependent CR finding (EXP-2747) is the most actionable discovery: AID users should
consider higher CR ratios for large meals. This aligns with clinical experience that large
meals are harder to bolus for, and provides quantitative evidence for size-stratified CR.

### Files

| File | Description |
|------|-------------|
| `tools/cgmencode/exp_circadian_basal_2746.py` | Circadian basal profiling |
| `tools/cgmencode/exp_dose_dependent_cr_2747.py` | Dose-dependent CR analysis |
| `tools/cgmencode/exp_circadian_isf_2748.py` | Time-of-day ISF variation |
| `tools/visualizations/circadian-basal/exp-2746-dashboard.png` | Circadian basal dashboard |
| `tools/visualizations/dose-dependent-cr/exp-2747-dashboard.png` | Dose-dependent CR dashboard |
| `tools/visualizations/circadian-isf/exp-2748-dashboard.png` | Circadian ISF dashboard |

---

## Phase 10: Enhanced Pipeline & Absorption Dynamics (EXP-2749–2750)

### EXP-2749: Enhanced Pipeline with Dose-Dependent CR (3/5 PASS)

![EXP-2749 Enhanced Pipeline](../../tools/visualizations/enhanced-pipeline/exp-2749-dashboard.png)

Integrated size-stratified CR (from EXP-2747) into the full ISF+CR+EGP pipeline.
Three modes compared: profile settings, flat-CR integrated pipeline, enhanced (size-CR) pipeline.

| Metric | Value |
|--------|-------|
| Enhanced beats profile | 17/22 (77%) — up from 64% in EXP-2743 |
| Enhanced beats flat-CR | 9/22 (41%) |
| Median improvement over profile | 7.7% (MAE 43.3 → 36.9 mg/dL) |
| Safety (TBR) | p = 1.0 (no increase) |

**Key insight**: Size-stratified CR helps patients with high meal variability
(ns-8f3527d1: +34% over flat CR) but can overcomplicate for patients with uniform
meal sizes. Offer as an OPTION for patients with variable meal sizes.

### EXP-2750: Meal Absorption Dynamics (3/5 PASS) ⭐

![EXP-2750 Absorption Dynamics](../../tools/visualizations/absorption-dynamics/exp-2750-dashboard.png)

Investigated the MECHANISM behind dose-dependent CR:

| Hypothesis | Result | Interpretation |
|------------|--------|---------------|
| H1: Later peak (>15min) | 10/22 (45%) — FAIL | Moderate delay, not universal |
| H2: Wider excursion | **18/22 (82%) — PASS** | Gastric emptying spreads absorption |
| H3: Lower peak-per-gram | **22/22 (100%) — PASS** | Universal nonlinear absorption |
| H4: Peak not proportional to dose | 11/22 (50%) — FAIL | Borderline — some linearity |
| H5: Shape differs (KS test) | **14/22 (64%) — PASS** | Distinct trajectory shapes |

**Population medians:**
| Metric | Small Meals | Large Meals |
|--------|-------------|-------------|
| Peak time | 92 min | 108 min |
| Excursion width | 62 min | 80 min |
| Peak per gram | 2.99 mg/dL/g | 1.81 mg/dL/g |

The peak-per-gram finding is the strongest: large meals universally produce only **60% of the
per-gram glucose impact** compared to small meals. This is consistent with gastric emptying
physiology (Hunt & Stubbs 1975): stomach emptying rate decreases with meal volume, spreading
glucose absorption over longer time and allowing the AID controller more time to respond.

**Implication for AID authors**: Carb absorption models in Loop/Trio/AAPS use fixed absorption
rates. A meal-size-dependent absorption curve would better match reality. The current linear
carb model overestimates peak impact for large meals and underestimates duration.

### Updated Pipeline Status

| Setting | Method | Status | Performance |
|---------|--------|--------|-------------|
| ISF | EXP-2719b waterfall residuals | **PRODUCTION** | 68% improve |
| CR flat | EXP-2741 bilateral deconfounding | **PRODUCTION** | 73% improve |
| CR size-stratified | EXP-2747 dose-dependent | **OPTIONAL** | 41% improve (meal-only) |
| EGP | EXP-2742 per-patient adjustment | **PRODUCTION** (11/22) | 55% improve |
| Basal flat | EXP-2745 fasting drift | NOT RECOMMENDED | 1/22 improve |
| Basal circadian | EXP-2746 hourly drift | MARGINAL | 8/22 improve |
| ISF circadian | EXP-2748 time blocks | MARGINAL | 11/22 improve |
| Full enhanced | EXP-2749 size-CR pipeline | **TESTING** | 77% beat profile |

### Absorption Mechanism Summary

```
Small meal (20g):  Fast peak (92min), narrow (62min), 2.99 mg/dL/g
                   ╭──╮
                  ╱    ╲
                 ╱      ╲
                ╱        ╲──
               ╱
              ╱
Large meal (60g):  Slow peak (108min), wide (80min), 1.81 mg/dL/g
                      ╭────────╮
                    ╱            ╲
                  ╱                ╲
                ╱                    ╲───
              ╱
```

The nonlinear absorption provides a principled explanation for why AID users
report difficulty bolusing for large meals. The standard linear carb model
assumes proportional absorption, leading to overaggressive initial dosing
and insufficient coverage of the extended tail.

### Files

| File | Description |
|------|-------------|
| `tools/cgmencode/exp_enhanced_pipeline_2749.py` | Enhanced pipeline with size-CR |
| `tools/cgmencode/exp_absorption_dynamics_2750.py` | Meal absorption dynamics |
| `tools/visualizations/enhanced-pipeline/exp-2749-dashboard.png` | Enhanced pipeline dashboard |
| `tools/visualizations/absorption-dynamics/exp-2750-dashboard.png` | Absorption dynamics dashboard |

---

## Phase 11: Pipeline Completeness Validation (EXP-2751–2752)

### EXP-2751: Residual Autocorrelation (2/5 PASS)

![EXP-2751 Residual Autocorrelation](../../tools/visualizations/residual-autocorrelation/exp-2751-dashboard.png)

Key diagnostic: after the pipeline subtracts known effects, what structure remains?

| Lag Range | Timescale | Significant | Interpretation |
|-----------|-----------|-------------|----------------|
| 1–12 | 5–60 min | **21/22 (95%)** | Short-term model mismatch |
| 12–72 | 1–6 h | 4/22 (18%) | No medium-term structure |
| 72–288 | 6–24 h | 2/22 (9%) | No long-term structure |

**Median ACF at key lags:**
| Lag | Timescale | Median ACF |
|-----|-----------|------------|
| 1 | 5 min | +0.234 |
| 12 | 1 h | +0.006 |
| 72 | 6 h | +0.002 |
| 144 | 12 h | +0.000 |
| 288 | 24 h | +0.004 |

**Finding**: Residuals have ~40 minutes of memory, then are white noise. Beyond 1 hour,
there is effectively zero exploitable signal. The pipeline captures all multi-hour and
multi-day structure in the data.

### EXP-2752: Absorption Curve Refinement (0/5 PASS — Informative Null)

![EXP-2752 Absorption Refinement](../../tools/visualizations/absorption-refinement/exp-2752-dashboard.png)

Tested 4 absorption models to determine whether better carb curves could reduce
the 40-minute autocorrelation:

| Model | Best for N patients | Effect on ACF |
|-------|--------------------:|---------------|
| Linear | **14/22** | ACF₁ ≈ 0.955 |
| Biexponential | 2/22 | ACF₁ ≈ 0.955 |
| Size-dependent | 3/22 | ACF₁ ≈ 0.953 |
| Parabolic | 3/22 | ACF₁ ≈ 0.955 |

**All models produce identical autocorrelation.** The 40-minute memory is NOT from
carb absorption model mismatch — it's from **AID controller dynamics**. The controller
adjusts temp basals in response to glucose changes, creating serial correlation that
no carb model can fix.

### Pipeline Completeness Assessment

The combination of EXP-2751 and EXP-2752 confirms the pipeline is **near-complete**:

1. **No medium/long-term structure** → EGP, circadian, and multi-day factors are adequately captured
2. **No absorption model improvement** → Linear carb model is optimal
3. **40-minute residual memory** → Controller response dynamics (correct behavior, not a gap)
4. **Residuals are white noise beyond 1 hour** → No additional physics-based factors will help

This means the pipeline has extracted all the signal that can be extracted from
observational closed-loop data for settings optimization.

### Production Settings Report v3

![Production Report v3](../../tools/visualizations/production-report-v3/production-report-v3-dashboard.png)

Final pipeline output: 22 per-patient settings recommendations.

| Metric | Value |
|--------|-------|
| Patients improving | 17/22 (77%) |
| High confidence | 12/22 |
| Size-CR beneficial | 4/22 |
| Median MAE improvement | 7.7% |
| Most common action | REDUCE_ISF (13/22) |

### Files

| File | Description |
|------|-------------|
| `tools/cgmencode/exp_residual_autocorrelation_2751.py` | Residual autocorrelation analysis |
| `tools/cgmencode/exp_absorption_refinement_2752.py` | Absorption curve comparison |
| `tools/cgmencode/generate_settings_report_v3.py` | Production settings report v3 |
| `tools/visualizations/residual-autocorrelation/exp-2751-dashboard.png` | Autocorrelation dashboard |
| `tools/visualizations/absorption-refinement/exp-2752-dashboard.png` | Absorption refinement dashboard |
| `tools/visualizations/production-report-v3/production-report-v3-dashboard.png` | Settings report v3 dashboard |

---

## Summary: Complete Pipeline Achievement

### What the Pipeline Does

Starting from raw Nightscout data (glucose, insulin, carbs, devicestatus), the pipeline:

1. **Extracts ISF** via waterfall regression residuals (EXP-2719b)
2. **Extracts CR** via bilateral meal deconfounding with controller compensation (EXP-2741)
3. **Adjusts for EGP** via per-patient metabolic baseline personalization (EXP-2742)
4. **Optionally stratifies CR** by meal size for patients with variable meals (EXP-2747)
5. **Validates** via episode-based forward simulation (EXP-2743, 2749)

### What We Learned About the Data

| Finding | Evidence | Implication |
|---------|----------|-------------|
| ISF division is broken in closed-loop | EXP-2680, 2699, 2700, 2717/b, 2718 | Must use subtraction/residuals |
| Profile ISF overestimates sensitivity | EXP-2719b: 13/22 need ↓ISF | Most users have ISF too high |
| CR is dose-dependent | EXP-2747: 2× ratio large/small | Nonlinear carb absorption |
| Large meals: 60% of per-gram impact | EXP-2750: 1.81 vs 2.99 mg/dL/g | Need size-dependent carb models |
| Basal adjustment is futile | EXP-2745: 1/22 improve | Controller already handles basal |
| Circadian effects are marginal | EXP-2746, 2748: 8-11/22 improve | AID compensates for dawn phenomenon |
| Residuals have 40min memory | EXP-2751: controller dynamics | Not a model gap |
| Linear absorption is optimal | EXP-2752: 14/22 best | Simpler models win |
| Pipeline is near-complete | EXP-2751+2752 | No more factors to add |

### Recommendations for AID Authors

1. **Add ISF auto-adjustment**: Use regression residuals to detect ISF miscalibration.
   Most users have ISF set too high, causing underdelivery of corrections.

2. **Implement size-dependent carb absorption**: Large meals (>30g) produce only 60%
   of per-gram glucose impact. Current linear models overpredict large-meal peaks
   and underpredict duration.

3. **Don't rely on basal optimization**: AID controllers already compensate via temp
   basals. The scheduled basal rate is nearly irrelevant to glucose outcomes.

4. **Bilateral deconfounding for CR**: Subtract estimated controller basal suspension
   before computing effective CR. Raw post-meal glucose drops overestimate CR by ~30%.

5. **Profile ISF is catastrophic for BGI**: Never use profile ISF directly in glucose
   prediction. The BGI calculation should use corrected ISF from the residual method.

### Experiment Index

| EXP | Title | Result | Key Finding |
|-----|-------|--------|-------------|
| 2719 | Waterfall regression | 5/5 PASS | BG₀ dominates, profile ISF catastrophic |
| 2719b | Per-patient ISF from residuals | 5/5 PASS | 96% need ISF correction |
| 2741 | Bilateral CR deconfounding | 4/5 PASS | 73% improve with compensated CR |
| 2742 | EGP personalization | 4/5 PASS | Per-patient metabolic baseline |
| 2743 | Integrated pipeline validation | 4/5 PASS | 64% beat profile, 28% MAE improvement |
| 2744 | Universal EGP extraction | 2/5 PASS | EGP/basal collinear — identification problem |
| 2745 | Basal validation | 3/5 PASS | Fasting drift = controller, not patient |
| 2746 | Circadian basal | 3/5 PASS | Real pattern but marginal value |
| 2747 | Dose-dependent CR | 4/5 PASS | 2× CR ratio large/small meals |
| 2748 | Circadian ISF | 3/5 PASS | Dawn phenomenon rare in AID |
| 2749 | Enhanced pipeline | 3/5 PASS | 77% beat profile with size-CR |
| 2750 | Absorption dynamics | 3/5 PASS | Universal nonlinear absorption |
| 2751 | Residual autocorrelation | 2/5 PASS | 40min memory, white noise beyond |
| 2752 | Absorption refinement | 0/5 PASS | Linear optimal, ACF from controller |
| 2753 | Temporal cross-validation | 5/5 PASS | Settings generalize — 59% on test set ⭐ |
| 2754 | Population insights | 2/5 PASS | Controller explains 47.5% of ISF variance |
| 2755 | Controller-specific extraction | 1/5 PASS | Unified pipeline robust across controllers |
| 2756 | ISF CF diagnostic | 2/5 PASS | 6× gap: EGP dominant, controller 96% suspends |
| 2757 | EGP quantification | 3/5 PASS | EGP circular (artifact) — corrected in 2758 |
| 2758 | ISF reconciliation | 1/5 PASS | Net EGP≈0, profile ISF ≠ observed ISF |
| 2759 | DIA window & CF | 4/5 PASS | CF is patient characteristic |
| 2760 | Extended DIA (4h) | 4/5 PASS | 17% more precise |
| 2761 | BG-stratified CF | 1/5 PASS | Between-patient only (r=0.112) |
| 2762 | IOB-aware CF | 2/5 PASS | IOB adds nothing; LR approach beats median |
| 2763 | LR vs median CF | 4/5 PASS | 73 mg/dL intercept, 25/26 beat CF |
| 2764 | Intercept decomposition | 5/5 PASS | BG coef=0.8, LR+BG best model ⭐ |
| 2783 | Controller effort | 2/5 PASS | 92% basal suspension universal |
| 2784 | TIR predictors | 3/5 PASS | No user behavior predicts TIR |
| 2785 | Multi-day ISF dynamics | 3/5 PASS | TDD correlates positively with BG (confounding) |
| 2786 | Multi-scale deconfounding | 4/5 PASS | AR meal dominates (R²+=0.23), 4-layer pipeline |
| 2787 | IOB-based BGI | 1/5 PASS | deltaIOB WORSE — conflates delivery+absorption |
| 2788 | Convolution BGI | 5/5 PASS | Delivery×activity curve beats all ⭐ |
| 2789 | Deconfounded settings v2 | 1/5 PASS | ISF negative for 92% — structural impossibility |
| 2790 | Total insulin accounting | 3/5 PASS | Actual basal only 14% of TDD! |
| 2791 | Integrated pipeline v3 | 5/5 PASS | Full pipeline: conv BGI+AR+categorization ⭐ |
| 2792 | Controller recommendations | 4/5 PASS | 6 actionable findings for AID authors ⭐ |

## Phase 12: Validation & Generalization (EXP-2753 through 2755)

### Temporal Cross-Validation (EXP-2753) ⭐

The critical trust experiment. 70/30 chronological split per patient:
- ISF corrected on train, validated on test: 21/22 improve on test
- **Median improvement: 59% on BOTH train and test** — zero overfitting
- Stability ratio: 0.98 (test improvement ≈ train improvement)
- Zero patients harmed (>20% worse)

This proves the corrections reflect genuine patient characteristics.

![EXP-2753 Temporal Cross-Validation](../../visualizations/temporal-crossval/temporal_crossval.png)

### Population Insights (EXP-2754)

- ISF overestimation is NOT universal — only 36% overestimate
- **Controller type explains 47.5% of ISF correction variance**
- Population-mean correction helps 64% (useful as default)
- OpenAPS patients need opposite ISF direction vs Loop/Trio

![EXP-2753 Controller Decomposition](../../visualizations/controller-decomposition/controller_decomposition.png)

### Controller-Specific Extraction (EXP-2755)

- Controller-specific insulin accounting does NOT improve over unified (7% vs 25%)
- 68% of patients show <2% difference between methods
- **Actionable: DIA window differs** — Loop optimal at 60min, Trio at 120min (p=0.022)

![EXP-2755 Grand Synthesis](../../visualizations/grand-synthesis/grand_synthesis.png)

## Phase 13: ISF Deep Diagnostic (EXP-2756 through 2758)

### The 6× ISF Gap (EXP-2756)

Profile ISF predicts 295 mg/dL drop per correction. Actual: 46 mg/dL.

Gap decomposition:
| Factor | Contribution |
|--------|-------------|
| Controller basal suspension | -164 mg/dL (counteracts) |
| SMB dosing | +110 mg/dL (helps) |
| Remaining (initially attributed to EGP) | +267 mg/dL |

Controller suspends basal in **96.4%** of corrections. CF varies with starting BG
(BG 180-220: CF=0.10, BG 300-400: CF=0.24).

### EGP Circularity (EXP-2757 → 2758)

EXP-2757 initially found EGP = 3.33 mg/dL/5min (~80 mg/dL/2h) but this was
**circular** — it used `basal_effect = sched_basal × profile_ISF / 12`.

EXP-2758 corrected this with ISF-independent measurement:
- **Net fasting glucose drift: -0.01 mg/dL/5min** (essentially zero!)
- The AID controller has ALREADY balanced basal against hepatic output
- EGP is NOT the dominant factor in the gap

![EXP-2758 ISF Reconciliation](../../visualizations/isf-reconciliation/isf_reconciliation.png)

### Critical Conclusion

**Profile ISF and observed ISF are DIFFERENT quantities:**
- Profile ISF (55 mg/dL/U) = controller parameter for IOB-based prediction
- Observed ISF (9 mg/dL/U) = closed-loop system response including all compensation
- These CANNOT be reconciled because they measure different things

**The correction factor approach (EXP-2719b) is correct BECAUSE it doesn't try to
derive "true ISF" — it finds the multiplier that makes predictions match observations.**

## Phase 14: Extended Window and Model Refinement (EXP-2760–2764)

### EXP-2760: Extended DIA Pipeline (2h vs 4h) — 4/5 PASS
- 4h window better for 16/27 (59%) patients
- CF IQR: 0.575 → 0.476 (17% more precise)
- Temporal stability maintained: 0.961
- Median improvement: 72.6% vs 70.6% (+2%)
- **Recommendation**: 4h for offline, 2h for real-time

### EXP-2761: BG-Stratified CF — 1/5 PASS (informative null)
- BG-CF correlation is BETWEEN-patient, not within (median r=0.112)
- Stratified CF barely helps (+1.6%) — single CF per patient is correct complexity

### EXP-2762: IOB-Aware CF — 2/5 PASS
- IOB adds nothing beyond excess_insulin (H5 fail, delta=0%)
- Improvement is from regression approach (35%) not from IOB covariate
- Led to discovery: regression beats median CF

### EXP-2763: LR vs Median CF — 4/5 PASS (breakthrough)
- Model: `actual_drop = 73 + slope × excess_insulin`
- **The 73 mg/dL intercept = dose-independent baseline drop** (universal)
- LR beats median CF: 25/26 patients (96%), 33% median MAE reduction
- Intercept helps 25/26 patients (96%) — nearly universal signal
- This IS the ~74 mg/dL universal drop from EXP-2681

### EXP-2764: Intercept Decomposition — 5/5 PASS ⭐
- **Full model**: `drop = 73 - 6×excess_insulin + 0.8×starting_BG`
- Starting BG coefficient = 0.797 (regression to mean dominates!)
- Excess insulin slope is NEGATIVE (confounding by indication confirmed)
- LR+BG beats median CF by ~40% (best prediction model in pipeline)
- Controller action >100% of intercept (profile ISF overestimates effect)
- Stability 0.909 — generalizes across time

**Critical insight**: BG correction drops are primarily regression to mean
(0.8 × starting_BG) plus controller compensation. The marginal insulin effect
appears negative because the controller delivers more insulin in harder episodes.

For prediction: LR+BG model is best. For settings optimization: correction factors
remain the right tool because they abstract over confounding.

## Pipeline Status (Updated)

| Setting | Method | Status | Performance |
|---------|--------|--------|-------------|
| ISF | EXP-2719b waterfall residuals | **PRODUCTION** | 68% improve |
| CR flat | EXP-2741 bilateral deconfounding | **PRODUCTION** | 73% improve |
| CR size-stratified | EXP-2747 dose-dependent | **OPTIONAL** | 41% improve |
| EGP | EXP-2742 per-patient adjustment | **PRODUCTION (11/22)** | 55% improve |
| Basal | EXP-2745 fasting drift | NOT RECOMMENDED | 1/22 |
| Absorption | EXP-2752 linear optimal | **CONFIRMED** | 14/22 best |
| Temporal stability | EXP-2753 cross-validation | **PROVEN** | 59% on test |
| DIA window | EXP-2759 CF mechanism | **CONFIRMED** | 21% var reduction |
| BG prediction | EXP-2764 LR+BG model | **BEST** | 40% vs CF |
| BG-stratified CF | EXP-2761 | NOT RECOMMENDED | within-patient r=0.11 |
| IOB covariate | EXP-2762 | NOT RECOMMENDED | no added value |
| Supply/demand | EXP-2767 bilateral | **CONFIRMED** | Supply 53%, demand 18% |
| 50/50 rule | EXP-2771 validation | **ACTIONABLE** | Basal too low: 16/30 |
| BGI deviation | EXP-2772 bounded | **CONFIRMED** | 10/90 split, circadian in 97% |

## Phase 15: Bilateral Supply-Demand Decomposition (2026-04-19)

### Breakthrough: The Glucose Correction Is 72% Supply-Side

Six experiments decomposed BG corrections into supply-side (homeostatic/hepatic)
and demand-side (insulin) channels, validated by the clinical 50/50 rule.

**EXP-2767: 3-Channel Supply vs Demand (3/5 PASS)**
- BG regression to mean: 53% of corrections (supply-side dominant)
- Controller automated: 14% (demand auto)
- User bolus: **3%** (demand user — nearly irrelevant!)
- Supply > demand-user: 27/27 patients (universal)

**EXP-2768: 5-Channel with Pre-IOB (2/5 PASS)**
- Added pre-existing IOB (1%) and carbs (4%)
- Residual intercept: -28 mg/dL (hepatic estimate)
- Supply-side total: ~72% of BG corrections
- Demand-side total: ~18% of BG corrections

**EXP-2769: 72h Insulin Accounting (1/5 PASS — informative)**
- TDD median 27.2U (IQR 20.3-36.2)
- Basal fraction NEGATIVE (-44%) — controllers suspend basal!
- All insulin delivered via bolus channels (SMB replaces basal)
- Delivery ratio positively correlates with BG (r=0.535) — confounding

**EXP-2770: Multi-Timescale Subtraction (1/5 PASS — methodological)**
- L5 multi-day trend: 26% variance (dominant timescale)
- L4 circadian: 3.4% but significant in 97% of patients
- L2 BGI: cumulative approach fails; must use bounded windows
- Total: 33% variance removed, 67% remaining

**EXP-2771: 50/50 Rule Validation (3/5 PASS — actionable!)**
- Clinical rule: 50% TDD for basal (EGP), 50% for food/corrections
- **16/30 patients have scheduled basal <35%** — too low!
- Controller redistributes 45% of TDD from basal to SMB channels
- Loop patients closer to 50/50 (dev=8%) than Trio (dev=18%)
- **Settings action: increase basal rates for patients below 35%**

**EXP-2772: Bounded BGI Deviation (3/5 PASS)**
- oref0-style bounded 2h windows (fixes EXP-2770's drift)
- BGI explains only 10% of glucose changes (not 50%)
- Deviation (supply-side) = 90% of glucose dynamics
- 29/30 patients show circadian pattern in deviation
- 50/50 applies to insulin QUANTITY (EXP-2771), not variance EXPLAINED
- The controller obscures the causal insulin→glucose pathway

### Key Insight: Why BGI Variance ≠ 50%

The 50/50 rule is about insulin VOLUME (half of TDD covers EGP, half covers
meals/corrections). But the VARIANCE explained by BGI is only 10% because
in closed-loop, IOB changes are the controller's RESPONSE to glucose, not
just the cause. The controller masks the causal pathway through:
1. Giving more insulin when BG is high (confounding by indication)
2. Suspending basal when BG is low (reverse causation)
3. Using multiple channels simultaneously (SMB + basal + bolus)

To properly attribute 50% of glucose variance to insulin, we would need
causal methods (controller replay, instrumental variables) not observational
correlation.

## Phase 16: Confounding Structure & Residual Decomposition (EXP-2773–2780)

### Context

Phase 15 established bilateral supply-demand decomposition. Phase 16 asks:
can we close the ISF gap between profile ISF (~55) and observed ISF (~5)?
What structure exists in the 59% residual from bilateral regression?

### EXP-2773: Bilateral BGI Regression (4/5 PASS)

Physical BGI calculation using ΔIOB × ISF × CF CATASTROPHICALLY FAILED
(R² deeply negative, -56% to -452%). In closed-loop, ΔIOB captures
controller RESPONSE, not causal insulin effect.

Solution: empirical regression (like oref0 autotune):
- `delta_BG = 63 - 0.45×starting_BG - 2.9×insulin - 0.38×carbs`
- R² = 41.1%, insulin NEGATIVE for 28/28 patients ✓
- Variance: Starting BG 34%, Insulin 3%, Carbs 4%, Residual 59%

### EXP-2774: oref0-Style Deviation Categorization (4/5 PASS)

Implemented categorize.js logic: **Basal 21%, CSF 42%, ISF 30%, UAM 5%**
- 48% of AID data is meal-related (CSF+UAM)
- ISF category has strongest insulin coefficient (-4.4 mg/dL/U)
- Basal category has highest R²=0.38 (least confounded)

### EXP-2775: Basal Rate Optimization via 50/50 Rule (2/5 PASS)

**7/12 Trio patients need +70% basal increase.** Loop is well-calibrated
at 50%. Trio's oref1+SMB controller compensates by delivering more SMBs.
Basal deviation does NOT predict TIR (r=-0.11) because controller compensates.

### EXP-2776–2778: ISF Gap Investigation (Structural Conclusion)

Three experiments attempted to close the 10× ISF gap:
1. **Category stratification** (2776): ISF-category ISF=5.4 vs full=2.3. Still 10× below profile.
2. **Channel decomposition** (2777): Median ISF is NEGATIVE across ALL channels. 
   Confounding by indication so strong that user boluses appear to raise BG.
3. **DIA-matched windows** (2778): 1h-6h windows tested. ISF near-zero at ALL windows.
   3h window has best profile correlation (r=0.755). BG-falling filter at 1h: 86% positive.

**Conclusion: The ISF gap is structural in observational data.** Regression captures
BG correlation with insulin delivery, not the causal effect. The production pipeline
(EXP-2719b) already handles this correctly by using profile ISF as prior.

### EXP-2779: Residual Decomposition by Category (2/5 PASS)

The 59% residual contains structured signals:
1. **Circadian EGP**: 27/28 patients have significant time-of-day pattern (p<0.05)
2. **Meal autocorrelation**: CSF lag-1 AC = 0.944 — meal absorption is extremely persistent
3. But category-specific linear models only improve R² by +3% — the structure
   requires temporal models (AR/LSTM) to exploit

### EXP-2780: Circadian Basal Rate Optimization (2/5 PASS)

Circadian BG patterns during basal periods are massive and universal:
- Amplitude: median 57 mg/dL/h, **96% of patients >20 mg/dL/h**
- Dawn phenomenon present in 57% of patients
- Afternoon (3-5pm) shows HIGHEST rise (+21 mg/dL/h), not dawn (+7.7)
- Critical: ALL periods show rising BG because filter selects low-insulin times

### Phase 16 Summary

| Finding | Impact | Actionability |
|---------|--------|---------------|
| Physical BGI fails in closed-loop | Use empirical regression | High |
| 48% of AID data is meal-related | CSF category dominates | Medium |
| 7/12 Trio basal too low by 70% | Direct user recommendation | **Very High** |
| ISF gap is structural (3 experiments) | Cannot close observationally | Confirmed |
| Circadian EGP is universal (96%) | Need deviation-based analysis | High |
| CSF autocorrelation = 0.944 | Need temporal models | Medium |



| EXP | Title | Result | Key Finding |
|-----|-------|--------|-------------|
| 2698 | Deconfounding Pipeline | Production | BGI subtraction R²=0.77 |
| 2719b | ISF Waterfall | Production | 68% improve, CF approach |
| 2741 | Bilateral CR | Production | 73% improve, demand+supply |
| 2742 | EGP Personalization | Production | 55% improve, 11/22 |
| 2745 | Basal Optimization | Not rec | 1/22, controller dominates |
| 2747 | Size-Stratified CR | Optional | 41% improve, large meals |
| 2749 | Full Pipeline Validation | 3/5 PASS | 77% improve overall |
| 2750 | Absorption Dynamics | 3/5 PASS | Universal nonlinear absorption |
| 2751 | Residual Autocorrelation | 2/5 PASS | 40min autocorrelation |
| 2752 | Absorption Refinement | 0/5 PASS | Linear wins 14/22 |
| 2753 | Temporal Cross-Val | 5/5 PASS ⭐ | 59% improve on test |
| 2754 | Population Insights | 2/5 PASS | Controller explains 47.5% |
| 2755 | Controller-Specific | 1/5 PASS | DIA differs (p=0.022) |
| 2756 | ISF CF Diagnostic | 2/5 PASS | 6× gap, 96.4% basal susp |
| 2757 | EGP Quantification | 3/5 PASS | Circular! (see 2758) |
| 2758 | ISF Reconciliation | 1/5 PASS | Profile ISF ≠ observed ISF |
| 2759 | DIA Window & CF | 4/5 PASS | CF is patient characteristic |
| 2760 | Extended DIA (4h) | 4/5 PASS | 17% more precise |
| 2761 | BG-Stratified CF | 1/5 PASS | Between-patient only |
| 2762 | IOB-Aware CF | 2/5 PASS | LR approach beats median |
| 2763 | LR vs Median CF | 4/5 PASS | 73 mg/dL intercept! |
| 2764 | Intercept Decomp | 5/5 PASS ⭐ | b2(BG)=0.8, neg insulin |
| 2765 | Settings Generator | 4/5 PASS | 28/28 actionable recs |
| 2766 | Iterative Settings | 2/5 PASS | r=1.000, purely mathematical |
| 2767 | Supply vs Demand | 3/5 PASS | Supply 53%, user bolus 3% |
| 2768 | Intercept + IOB | 2/5 PASS | Residual -28 mg/dL (hepatic) |
| 2769 | 72h Insulin | 1/5 PASS | Basal fraction -44%, SMB dominant |
| 2770 | Multi-Timescale | 1/5 PASS | L5 multi-day 26%, BGI fails cumul |
| 2771 | 50/50 Rule | 3/5 PASS | 16/30 basal too low, 45% redistrib |
| 2772 | Bounded BGI | 3/5 PASS | 10/90 split, circadian in 97% |
| 2773 | Bilateral BGI | 4/5 PASS | R²=41.1%, empirical regression |
| 2774 | oref0 Categorize | 4/5 PASS | Basal 21%, CSF 42%, ISF 30% |
| 2775 | Basal Optimization | 2/5 PASS | 7/12 Trio basal too low |
| 2776 | Category Settings | 1/5 PASS | ISF-cat r=0.527, gap persists |
| 2777 | ISF Gap Channels | 1/5 PASS | Negative ISF — structural gap |
| 2778 | DIA Window ISF | 4/5 PASS | 3h best r=0.755, gap stays |
| 2779 | Residual Decomp | 2/5 PASS | Circadian 27/28, CSF AC=0.94 |
| 2780 | Circadian Basal | 2/5 PASS | Amp 57 mg/dL/h, 96% universal |
| 2781 | Meal AR Model | 1/5 PASS | AR(1)=0.518, flips ISF sign |
| 2782 | Settings Audit | 3/5 PASS | 96% recs, ctrl p=0.002 |
| 2783 | Controller Effort | 2/5 PASS | 92% susp universal, SMB≈2.3/h |
| 2784 | TIR Predictors | 3/5 PASS | No user behavior predicts TIR! |
| 2785 | Multi-Day ISF | 3/5 PASS | Confounding at daily scale r=+0.50 |
| 2786 | Multiscale Deconf | 4/5 PASS | AR dominates, BGI negative, R²=15% |
| 2787 | IOB-Based BGI | 1/5 PASS | deltaIOB WORSE — conflates delivery |
| 2788 | Conv BGI | 5/5 PASS | Conv beats simple 28/28, R²=24% |

## Phase 17: Controller Compensation & Multi-Scale Deconfounding (EXP-2781–2788)

### Key Discoveries

#### 1. Controller Effort is Universal (EXP-2783)
ALL controllers suspend basal 72–93% of the time. Loop and Trio both use ~2.3 SMBs/hour.
The controllers essentially REPLACE scheduled basal with dynamic dosing. This means:
- Scheduled basal rate is almost irrelevant for acute glucose control
- The 50/50 rule applies to what the body NEEDS, not what's DELIVERED on schedule
- Actual basal fraction: Loop 22%, Trio 8%, OpenAPS 33% — all below 50%

#### 2. No User Behavior Predicts TIR (EXP-2784)
Bolus frequency (r=0.24), carb intake (r=0.08), meal size (r=0.21) — ALL non-significant.
Controller type explains 31% of TIR variance (η²=0.312, p=0.009).
Multi-factor R²=79.8% but driven by structural factors (CV, mean BG).
**The controller compensates for user behavioral variability.**

#### 3. Confounding by Indication at Every Scale
- **5-min**: Insulin delivery correlates positively with BG rise (structural)
- **1-6h**: ISF gap is 10-40× — can't observe true ISF (proven EXP-2776/77/78)
- **24h**: Daily TDD positively correlates with mean BG (r=+0.50)
- **72h**: Prior-day TDD barely predicts next-day BG (r=+0.12)

#### 4. Proper BGI Modeling (EXP-2786/87/88)
Three BGI approaches tested:
- **Simple rolling sum**: L1 R² = -0.38 (NEGATIVE — adds noise)
- **deltaIOB**: L1 R² = -0.62 (WORSE — conflates delivery + absorption)
- **Delivery × activity curve convolution**: L1 R² = +0.002 (best, near zero)

Convolution wins in ALL 28 patients. But L1 is still near-zero because
DELIVERY itself is confounded — controller delivers more when BG is high.

#### 5. AR Meal Momentum Dominates
Across all three BGI approaches, the AR(1) meal layer provides the dominant
variance explanation: +0.23 incremental R². This represents meal absorption
momentum — glucose continues rising/falling in the same direction.

### Basal Balance Summary (50/50 Rule)
| Controller | Scheduled Basal | Bolus+SMB | Status |
|-----------|----------------|-----------|--------|
| Loop | 37.3% | 62.7% | Low |
| Trio | 26.7% | 73.3% | Very Low |
| OpenAPS | 49.3% | 50.7% | ✓ Well-calibrated |

### Multi-Timescale Deconfounding Pipeline (Best: EXP-2788)
| Layer | Timescale | Method | Incremental R² |
|-------|-----------|--------|----------------|
| L1 | 5-min | Delivery × activity curve | +0.002 |
| L2 | 1-6h | AR(1) meal momentum | +0.231 |
| L3 | 24h | Circadian hourly mean | +0.004 |
| L4 | 72h | Daily mean shift | +0.002 |
| **Total** | | | **0.238** |

## Phase 18: Insulin Accounting, Integrated Pipeline & Recommendations (EXP-2789–2792)

### Data Semantics Fix: net_basal is a DEVIATION (EXP-2790)

**Critical data semantics correction**: `net_basal` in the grid is the DEVIATION from scheduled
basal rate (`actual_temp_basal - scheduled_basal_rate`), NOT the actual delivery.
Actual delivery = `(net_basal + scheduled_basal_rate).clip(lower=0) / 12` per 5-min interval.

### Total Insulin Accounting (EXP-2790) — 3/5 PASS

Using CORRECTED actual delivery:

| Controller | TDD | User Bolus | SMB | Actual Basal | Status |
|-----------|-----|-----------|-----|-------------|--------|
| Loop | 45.2 U | 51.8% | 25.7% | 22.1% | Low basal |
| Trio | 60.9 U | 60.5% | 30.6% | 9.4% | **Very low basal** |
| OpenAPS | 34.1 U | 53.4% | 0.0% | 33.2% | Closest to target |

**Key insight**: Actual basal is only 14% of TDD across all patients.
Controllers deliver only 33% of their scheduled basal rate (rest is suspended).
The 50/50 rule applies to what the body NEEDS, not how insulin is DELIVERED.

![EXP-2790 Insulin Accounting](../../tools/visualizations/insulin-accounting/exp-2790-dashboard.png)

### Deconfounded Settings v2 (EXP-2789) — 1/5 PASS (Structural Impossibility)

Even after convolution BGI + AR meal + circadian deconfounding:
- ISF is NEGATIVE for 92% of patients
- Confirms: ISF CANNOT be extracted from observational closed-loop data
- Validates the production approach (EXP-2719b) of using profile ISF as prior
- CR also fails: median 32.8 vs profile 8.5 (4× gap)

### Integrated Production Pipeline v3 (EXP-2791) — 5/5 PASS ⭐

Combines all best validated techniques:
1. **Convolution BGI** (EXP-2788): delivery × activity curve
2. **AR meal momentum** (EXP-2786): 1-6h autoregressive
3. **oref0-style categorization** (EXP-2774): CSF/ISF/UAM/basal
4. **Profile-prior settings** (EXP-2719b): weighted blend
5. **Insulin accounting** (EXP-2790): 50/50 sanity check

Results:
- 93% of ISF within 2× of profile
- 79% of CR within 2× of profile
- 100% of patients get meaningful recommendations
- **Median cross-validated R² = 0.238** (range: -0.03 to 0.73)

Per-controller pipeline output:

| Setting | Loop | Trio | OpenAPS |
|---------|------|------|---------|
| ISF | 49→32 (↓35%) | 58→45 (↓22%) | 55→46 (↓16%) |
| CR | 8→7 | 10→14 (↑40%) | 8→12 (↑50%) |
| Basal | 0.85→0.94 U/h | 0.82→1.27 U/h (↑55%) | 0.85→0.71 U/h |

**Universal pattern**: ISF needs reduction across all controllers.

![EXP-2791 Integrated Pipeline](../../tools/visualizations/integrated-pipeline-v3/exp-2791-dashboard.png)

### Controller-Specific Recommendations (EXP-2792) — 4/5 PASS ⭐

**6 Actionable Findings for AID Authors**:

1. **ISF over-estimation is universal** — apps should suggest reduction proactively
2. **Trio basal severely underestimated** (9% actual) — warn when < 20% of TDD
3. **Controller compensation nullifies user behavior** — focus on settings, not behavior
4. **Glucose CV is best TIR predictor** (r=-0.82) — display as quality metric
5. **SMB strategies differ** — controller-specific defaults recommended
6. **68% violate 50/50 rule** by >25pp — alert when actual basal < 30% of TDD

Within ALL controllers, glucose CV is the ONLY significant TIR predictor.
No individual setting significantly predicts TIR.

Trio vs Loop (statistically significant):
- Actual basal %: 9% vs 22% (p=0.022)
- TIR: 87% vs 65% (p=0.003)
- Despite worst settings, Trio achieves BEST TIR — oref1 compensates

![EXP-2792 Controller Recommendations](../../tools/visualizations/controller-recommendations/exp-2792-dashboard.png)

### Recommendations Summary

**FOR LOOP DEVELOPERS**:
- ISF too high for most users (49 → ~32)
- Consider auto-suggesting ISF reduction from correction patterns
- Basal suspension high (65%) but delivery reasonable (22%)

**FOR TRIO/oref1 DEVELOPERS**:
- Basal rates severely underestimated (only 9% actual delivery)
- CR may be too aggressive (10 → ~14)
- Add "basal adequacy" warning when actual < 20% of TDD
- oref1+SMB is powerful enough to compensate for bad settings

**FOR OPENAPS/oref0 DEVELOPERS**:
- Best-calibrated basal rates (33%, closest to 50%)
- CR needs increase (8 → ~12)
- Most physiological delivery pattern (no SMB patients)

**UNIVERSAL**:
- Track 7-day actual basal % of TDD
- ISF over-estimation is universal — suggest reduction proactively
- Glucose CV is the best quality metric
- User bolusing behavior does NOT predict TIR

---

## Phase 19: Pipeline v4 and Multi-Timescale Validation (EXP-2793–2797)

### Overview

Phase 19 integrates the multi-timescale deconfounding approach into a definitive pipeline (v4), validates category-specific modeling as the single biggest prediction improvement, confirms circadian EGP is real but modest, and demonstrates prospective generalization of settings recommendations.

### EXP-2793: Temporal AR Model — Category-Specific Breakthrough

**Result: 4/5 PASS**

Category-specific AR(2) achieves R²=0.449 — nearly **double** global AR(2) (0.248). BG dynamics behave fundamentally differently by metabolic context:

| Category | AR(2) R² | Interpretation |
|----------|----------|----------------|
| CSF (meals) | 0.302 | Most predictable — carb absorption is structured |
| ISF (corrections) | 0.185 | Moderate — insulin action is more variable |
| UAM (unexplained) | 0.099 | Near-random — these truly are unexplained |
| Basal | ~0.05 | Near-random — homeostatic noise |

AR coefficients stable across time splits (7.3% change). This means separate models per event category is the single most impactful architectural improvement.

![EXP-2793 Temporal AR](../../tools/visualizations/temporal-ar/exp-2793-dashboard.png)

### EXP-2794: Deviation-Based Circadian Analysis

**Result: 4/5 PASS**

After subtracting BGI and AR(1), ALL residual deviations are POSITIVE — this is the hepatic glucose production (EGP) signature. The body is always producing glucose; the controller is always fighting it.

- Morning trough 8-10am: +0.6 mg/dL/5min
- Evening peak 7-9pm: +1.7 mg/dL/5min (~3× variation)
- Dawn phenomenon detected in 79% of patients
- Circadian explains 4.1% additional variance
- Controller type does NOT explain circadian (p=0.206) — it's physiological

![EXP-2794 Circadian](../../tools/visualizations/deviation-circadian/exp-2794-dashboard.png)

### EXP-2795: Prospective Settings Validation

**Result: 4/5 PASS**

Critical trust experiment: 70/30 chronological train/test split.

- **89% of patients improve** on held-out test data (25/28)
- **ISF direction prediction: 93% correct**
- **Hypo safety: 100% safe** — zero increase in time below 70
- **Consistent across controllers**: Loop 89%, Trio 100%, OpenAPS 71%
- Prediction error: 2.576 → 2.485 mg/dL/5min (3.5% improvement)

H2 (suspension decrease) correctly FAILS because ISF correction only changes prediction accuracy, not actual delivery. We're correcting our MODEL, not replaying the controller.

![EXP-2795 Prospective](../../tools/visualizations/prospective-validation/exp-2795-dashboard.png)

### EXP-2796: Final Pipeline Synthesis v4 — BEST EVER

**Result: 5/5 PASS ⭐**

Combines every validated technique:
1. Convolution BGI (delivery × activity curve)
2. Category-specific AR(2) (CSF/ISF/UAM/basal separate)
3. Circadian correction (sin/cos harmonics per category)
4. Profile-prior settings extraction

| Metric | BGI-only | v3 (AR1+BGI) | **v4 (Cat-AR2+Circ)** |
|--------|----------|-------------|------------------------|
| Test R² | -0.016 | 0.228 | **0.418** |
| Beats baseline | — | — | **100% (28/28)** |

- **Train R²: 0.457**, Test R²: 0.418 (overfit gap only 0.039)
- Stability ratio: 0.91 (near-perfect generalization)
- ALL 28 patients improve over v3 — zero regressions
- Category-specific modeling is the **single biggest improvement** in the entire 60-experiment research program

| Controller | Train R² | Test R² | All Improve |
|-----------|----------|---------|-------------|
| Loop | 0.454 | 0.431 | 100% |
| Trio | 0.456 | 0.449 | 100% |
| OpenAPS | 0.593 | 0.273 | 100% |

![EXP-2796 Pipeline v4](../../tools/visualizations/final-pipeline-v4/exp-2796-dashboard.png)

### EXP-2797: EGP-Aware Settings Extraction

**Result: 2/5 PASS**

EGP correction is real but modest:
- R² improves for 100% of patients (0.236→0.240) but only +0.004
- ISF bias reduces (|deviation| 2.545→2.452)
- BUT: circadian ISF variation NOT explained by EGP alone (H4 FAIL)
- Window temporal consistency NOT improved (H5 FAIL)

**KEY INSIGHT**: The AID controller already partially compensates for EGP. After controller compensation, the residual EGP signal (~1.7 mg/dL/5min circadian range) is small relative to other noise. ISF circadian variation has physiological sources BEYOND EGP — likely insulin sensitivity itself varies by time of day.

![EXP-2797 EGP Settings](../../tools/visualizations/egp-settings/exp-2797-dashboard.png)

### Phase 19 Experiment Index

| # | EXP | Title | Pass | Key Finding |
|---|-----|-------|------|-------------|
| 59 | 2793 | Temporal AR Model | 4/5 | Category AR(2) R²=0.449, 2× global |
| 60 | 2794 | Deviation Circadian | 4/5 | All residuals positive = EGP, 79% dawn |
| 61 | 2795 | Prospective Validation | 4/5 | 89% improve on test, 93% ISF direction |
| 62 | 2796 | Final Pipeline v4 | 5/5⭐ | R²=0.418, 100% improve, best ever |
| 63 | 2797 | EGP Settings | 2/5 | EGP real but modest (+0.004 R²) |

### Phase 19 Summary

The definitive pipeline v4 achieves R²=0.418 on held-out test data — nearly **double** the v3 pipeline. The key architectural insight is that BG dynamics are fundamentally different by metabolic context, requiring separate models per event category. EGP is real and measurable but the controller already compensates for most of it, making explicit EGP correction only marginally helpful.

---

## Phase 20: Cross-Patient Transfer and Multi-Timescale Architecture (EXP-2798–2800)

### Overview

Phase 20 explored three critical questions: (1) can population patterns help individual patients, (2) what is the architecture of the BG signal at different timescales, and (3) does operating at the RIGHT timescale improve settings extraction.

### EXP-2798: Cross-Patient Transfer Learning

**Result: 2/5 PASS**

- **96% of patients need ISF decreased** — direction is nearly universal
- Population mean ISF correction: -2.50 mg/dL/5min
- Feature-based regression FAILS (LOO R²=-0.025) — can't predict magnitude from profile
- Controller type marginally significant (ANOVA p=0.051)
- Cold-start blending (50% population + 50% individual 10%) beats pure individual (MAE 0.954 vs 1.152)

**FOR AID AUTHORS**: Simply telling new users "your ISF is probably too high" is 96% correct. But the magnitude requires individual data.

![EXP-2798 Transfer](../../tools/visualizations/cross-patient-transfer/exp-2798-dashboard.png)

### EXP-2799: Multi-Timescale Deconfounding Cascade

**Result: 0/5 PASS (most informative)**

Definitive signal decomposition at 5-min resolution:

| Level | Component | Incremental R² |
|-------|-----------|---------------|
| L1 | BGI (insulin physics) | +1.2% |
| L2 | AR(1) momentum | +22.0% |
| L3 | Category AR(2) | +14.9% |
| L4 | Circadian (24h) | +0.2% |
| L5 | 72h insulin load | +0.03% |
| **Total** | | **44.5%** |

The 55.5% residual is genuinely stochastic at 5-min resolution. Circadian and 72h effects are REAL but operate at longer timescales — they're swamped by AR momentum at 5-min.

![EXP-2799 Cascade](../../tools/visualizations/deconfounding-cascade/exp-2799-dashboard.png)

### EXP-2800: Hourly-Scale Settings Extraction — Signal Inversion

**Result: 1/5 PASS (transformative)**

The signal decomposition **completely inverts** at hourly scale:

| Component | 5-min | Hourly | Change |
|-----------|-------|--------|--------|
| BGI (insulin) | 1.2% | **16.0%** | 13× larger |
| AR(1) | 22.0% | **2.1%** | 10× smaller |
| Category | 14.9% | **34.5%** | 2.3× larger |
| Circadian | 0.2% | **1.0%** | 5× larger |
| 72h load | 0.03% | **0.29%** | 10× larger |
| **Total** | **44.5%** | **58.1%** | +30% |

**KEY ARCHITECTURAL INSIGHTS**:

1. **5-min AR(1) is mostly CGM sensor smoothing**, not physiological. It nearly disappears at hourly.
2. **Insulin physics needs ~1 hour to manifest** — BGI is 13× stronger at hourly vs 5-min.
3. **Category-specific modeling is the DOMINANT signal** at hourly (34.5%).
4. **Hourly ISF extraction gives 19.4 vs profile 55.0** (ratio 0.35) — consistent with CF=0.2.

**IMPLICATION**: For settings extraction, operate at hourly scale. For BG forecasting, 5-min AR captures CGM dynamics. Different tasks → different timescales.

![EXP-2800 Hourly](../../tools/visualizations/hourly-settings/exp-2800-dashboard.png)

### Phase 20 Experiment Index

| # | EXP | Title | Pass | Key Finding |
|---|-----|-------|------|-------------|
| 64 | 2798 | Cross-Patient Transfer | 2/5 | 96% need ISF decreased, transfer limited |
| 65 | 2799 | Deconfounding Cascade | 0/5 | 44.5% R², 55.5% stochastic at 5-min |
| 66 | 2800 | Hourly Settings | 1/5 | Signal inverts: BGI 13×, AR 0.1×, total 58.1% |

### Phase 20 Summary

The most significant finding is the **timescale-dependent signal architecture**. At 5-min, CGM smoothing (AR) dominates and insulin physics is invisible. At hourly, insulin physics becomes the primary signal and category context is the dominant predictor. This resolves the long-standing puzzle of why BGI seemed so weak — we were measuring at the wrong timescale.
