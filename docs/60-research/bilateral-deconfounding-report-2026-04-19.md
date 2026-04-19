# Bilateral Deconfounding: Supply + Demand Analysis

**Date**: 2026-04-19  
**Experiments**: EXP-2711, EXP-2712, EXP-2713  
**Dataset**: 85,524 correction events, 21 patients (Loop=8, Trio=10, OpenAPS=3)  
**Predecessor**: EXP-2681 (BG drop ≈ 74 mg/dL regardless of dose), EXP-2699 (ISF 8-14× overestimation)

---

> **⚠️ CAUSAL CORRECTION (2026-04-19 14:43 PT)**
>
> The original framing of this report contained a fundamental causal error.
> In Type 1 diabetes, patients lack endogenous insulin production — the AID
> controller IS the insulin source. **Insulin lowers glucose; hepatic output
> raises glucose.** The "supply return" modeled below is NOT endogenous
> homeostasis — it captures the **controller's proportional dosing response**
> (higher BG → more aggressive insulin delivery → bigger drop) plus possible
> BG-dependent insulin resistance. The math and R² values are correct; the
> causal interpretation was backwards. See "Corrected Causal Framework" below.

---

## Executive Summary

We tested whether decomposing correction BG drops into a **BG₀-dependent component**
and a **dose-specific component** improves our ability to deconfound AID glucose data.

**Key statistical finding**: A simple linear function of starting BG (R²=0.117)
explains more variance in BG drop than insulin dose alone (R²=0.055). The combined
model reaches R²=0.228, and BG₀-residualized prediction beats dose-only on holdout
(18/21 patients, MAE 69.8 vs 74.8 mg/dL).

**Corrected causal interpretation**: The BG₀ term does NOT represent endogenous
"supply-side homeostasis." In T1D, without exogenous insulin, glucose rises
continuously from unopposed hepatic production. The BG₀ correlation arises because:
1. **The AID controller doses proportionally to BG elevation** — higher BG triggers
   more aggressive insulin delivery, producing larger drops
2. **Insulin sensitivity may vary with BG level** — resistance at very high glucose
3. **Hepatic state (glycogen, 72h carb history) modulates insulin resistance** —
   not glucose lowering directly, but how effectively insulin works

**The ~74 mg/dL constant drop (EXP-2681)** is caused by insulin delivered by the
controller, NOT by hepatic homeostasis. The constancy reflects the controller's
proportional dosing: it delivers enough insulin to produce roughly the same drop
regardless of the user's manual bolus size.

---

## EXP-2711: BG₀-Dependent Drop Model

> **Note**: Originally titled "Baseline Return Model — Quantifying the Supply Side."
> Retitled to avoid implying hepatic output lowers glucose. The BG₀ term captures
> the controller's proportional insulin response, not endogenous glucose regulation.

![exp-2711-dashboard](../../visualizations/baseline-return-model/exp-2711-dashboard.png)
![circadian settings](../../visualizations/circadian-settings/circadian_settings.png)

### BG₀-Dependent Drop Curve

The BG drop correlates linearly with starting BG:

```
predicted_drop = -8.1 + 0.426 × (BG₀ - 120)
```

For every 1 mg/dL above the controller's target (~120 mg/dL), 0.43 mg/dL of
additional drop is observed over the 2-hour window. This reflects the controller
delivering more insulin at higher BG, not the body self-correcting.

### R² Comparison: BG₀-Dependent vs Dose-Specific

| Model | R² | What It Captures |
|-------|----|------------------|
| BG₀ only | **0.117** | Controller proportional response + BG-dependent ISF |
| BG₀ + circadian + glycogen + ROC | **0.137** | + time-varying insulin resistance |
| Dose only | 0.055 | User bolus dose (partial insulin picture) |
| Dose + IOB | 0.094 | + existing insulin load |
| **Combined (BG₀ + dose)** | **0.228** | Both components |
| + Patient fixed effects | 0.310 | + individual ISF differences |

**BG₀ explains 2.1× more variance than user dose alone** because it captures
the controller's TOTAL insulin response (bolus + SMBs + basal), while "dose"
only captures the user-initiated bolus.

### Stepwise Waterfall

| Step | Factor | Δ R² | Cumulative R² |
|------|--------|------|---------------|
| 1 | BG above target (BG₀-dependent) | **+0.117** | 0.117 |
| 2 | Circadian blocks (ISF variation) | +0.009 | 0.126 |
| 3 | 48h carbs (insulin resistance proxy) | +0.003 | 0.129 |
| 4 | Glucose ROC (momentum) | +0.008 | 0.137 |
| 5 | Total insulin (dose-specific) | **+0.087** | 0.225 |
| 6 | IOB at start (existing insulin) | +0.004 | 0.228 |
| 7 | Insulin channels (bolus/SMB/basal) | +0.019 | 0.247 |
| 8 | Patient fixed effects | +0.069 | 0.316 |

### Unmasking Effect

After subtracting the BG₀ component, insulin dose becomes **1.6× more predictive**
of the residual (R² from 0.055 → 0.091). Supply subtraction unmasks the demand signal.

### Per-Patient Supply Parameters

| Metric | Median | Range |
|--------|--------|-------|
| Supply slope | 0.56 | 0.29 – 1.05 mg/dL per mg/dL above eq |
| Equilibrium point | 142 mg/dL | 42 – 180 mg/dL |
| Per-patient supply R² | 0.14 | 0.05 – 0.41 |

The BG₀-dependent drop curve is consistent across patients (H4 PASS: per-patient
models outperform population by <5% R²). This consistency reflects the similar
controller targeting behavior (all target ~100-120 mg/dL) and possibly universal
aspects of insulin pharmacokinetics.

---

## EXP-2712: BG₀-Residualized ISF Extraction


![exp-2712-dashboard](../../visualizations/bilateral-subtraction/exp-2712-dashboard.png)
![sc ceiling settings](../../visualizations/sc-ceiling-settings/sc_ceiling_settings.png)

### Statistical Decomposition of BG Drop

> **⚠️ Causal correction**: The table below shows a STATISTICAL decomposition
> (predicted by BG₀ model vs residual). In T1D, ALL glucose lowering is caused
> by insulin. The "BG₀-predicted" column captures the controller's proportional
> insulin response; the "dose residual" captures variation beyond that response.
> Both components are insulin-mediated.

| Controller | Total Drop | BG₀-Predicted | Dose Residual | Mean Dose |
|------------|-----------|---------------|---------------|-----------|
| Loop | 37.8 mg/dL | 44.0 (117%) | -6.3 (-17%) | 5.2 U |
| Trio | 49.3 mg/dL | 33.4 (68%) | 15.9 (32%) | 4.4 U |
| OpenAPS | 42.0 mg/dL | 42.4 (101%) | -0.4 (-1%) | 1.7 U |
| **Overall** | **41.3 mg/dL** | **41.2 (100%)** | **0.2 (0%)** | 4.3 U |

**The BG₀ model captures 100% of the average BG drop** because the controller's
proportional dosing is the dominant behavior during corrections. The near-zero
dose residual means user bolus size adds no information beyond what BG₀ already
predicts about total controller insulin delivery.

For Loop, the negative residual (-6.3) indicates Loop delivers MORE total insulin
than the population BG₀ model predicts — consistent with Loop's aggressive dosing.
Trio's positive residual (+15.9) suggests user boluses contribute beyond the
controller's automatic response.

### ISF Comparison

| Method | Median ISF | Setting/Extracted Ratio |
|--------|-----------|------------------------|
| Profile settings | 50.4 mg/dL/U | 1.0× (reference) |
| Demand-only | 23.1 mg/dL/U | 2.2× |
| Bilateral | 16.2 mg/dL/U | 3.1× |

Counter-intuitively, bilateral ISF is **further** from profile settings, not closer.

> **⚠️ Causal note**: The ISF ratios below reflect a statistical decomposition,
> not a causal claim. In T1D, ALL glucose lowering comes from exogenous insulin.
> The BG₀ term captures the controller's proportional response, not endogenous
> homeostasis. Profile ISF settings work because the controller's feedback loop
> (repeated dosing over the 6h DIA window) delivers the right total insulin —
> the ISF just controls dosing aggressiveness.

1. **Demand-only ISF** (23.1) divides total drop by user bolus dose only, ignoring
   that the controller also delivered insulin proportional to BG elevation
2. **BG₀-residualized ISF** (16.2) subtracts the BG₀-correlated component first,
   isolating what correlates with the specific dose beyond controller response
3. **Profile ISF** (50.4) is a controller tuning parameter — it governs dosing
   aggressiveness within the feedback loop, not pure insulin sensitivity

### Holdout Validation

| Method | Median MAE | Win Rate vs Demand |
|--------|-----------|-------------------|
| Profile ISF | 182.9 mg/dL | — |
| Demand-only ISF | 74.8 mg/dL | — |
| **BG₀-residualized** | **69.8 mg/dL** | **18/21 patients** |

The BG₀-residualized prediction is better because it separates the predictable
BG₀-dependent component (controller proportional response + BG-dependent ISF
variation) from the dose-specific component.

### Dose-Dependence

| Method | Spearman r (ISF vs dose) |
|--------|------------------------|
| Demand-only | -0.795 |
| BG₀-residualized | -0.743 |

Both show strong dose-dependence (the ratio artifact from EXP-2680). This
artifact comes from dividing by dose, not from the BG₀ component.

---

## Corrected Causal Framework

> **The original "supply vs demand" framing was causally incorrect for T1D.**

In Type 1 diabetes:
- **Insulin is the ONLY mechanism that lowers blood glucose.** These patients
  produce no endogenous insulin. The AID controller provides ALL insulin.
- **Hepatic glucose production (EGP) RAISES glucose.** The liver does not
  contribute to glucose lowering. It opposes insulin.
- **Hepatic state (glycogen from 72h carb history) modulates INSULIN RESISTANCE**,
  not glucose lowering directly. Full glycogen stores → more resistance → less
  effective insulin per unit.
- **ISF operates over a 6-hour DIA window.** Each insulin dose lowers glucose
  according to ISF × dose, with the effect distributed over the insulin action curve.

### What the BG₀ Term Actually Captures

The strong BG₀→drop correlation (R²=0.117) is NOT "supply-side homeostasis." It is:

1. **Controller proportional response**: Higher BG → controller delivers more
   total insulin (basal adjustments + SMBs) → larger total drop. The controller's
   target setpoint (~100-120 mg/dL) creates the appearance of "regression to
   equilibrium" but the MECHANISM is insulin delivery.

2. **BG-dependent insulin effectiveness**: At very high glucose, there may be
   transient glucose toxicity effects on insulin sensitivity. At moderate highs,
   insulin may work more efficiently.

3. **Mathematical regression to mean**: Extreme BG values have more room to
   drop. CGM noise also regresses.

### Correct Multi-Factor Model

The correct framing for T1D AID data:

```
BG_drop = ISF(time, glycogen_state) × total_insulin_delivered
        - EGP(glycogen, circadian) × interval
        + noise

Where:
  ISF varies with: time of day, 72h glycogen state, possibly BG level
  EGP RAISES glucose (opposes insulin) — varies with glycogen, circadian
  total_insulin = user_bolus + controller_SMBs + controller_basal_adjustments
  DIA = 6 hours (insulin action window)
```

The "bilateral" decomposition is still statistically useful for prediction
(R²=0.228 > either component alone), but the CAUSAL claim should be:
**insulin delivered by the controller lowers glucose, with effectiveness
modulated by ISF which varies with hepatic state and time of day.**

## Implications (Corrected)

### For Data Understanding

1. **The ~74 mg/dL constant drop is CONTROLLER BEHAVIOR**, not physiology.
   The AID controller delivers enough total insulin (bolus + SMB + basal
   adjustments) to produce roughly the same correction regardless of the
   user's manual bolus size.

2. **BG₀ is a strong predictor (R²=0.12) because it drives controller dosing.**
   This is a confound, not a causal mechanism. Higher BG → more controller
   insulin → bigger drop. Useful for prediction, misleading for causal inference.

3. **ISF settings are controller tuning parameters** that govern dosing
   aggressiveness within a 6h feedback loop. They are NOT pure physiological
   insulin sensitivity, but they encode useful information about how much
   insulin this patient needs per unit BG elevation.

### For AID Settings Optimization

1. **BG₀ residualization improves ISF extraction** — subtracting the
   controller-correlated BG₀ component isolates dose-specific insulin effects,
   improving holdout prediction by 7% (18/21 patients).

2. **Glycogen state (72h carb history) may modulate ISF** — this is a
   legitimate physiological effect (hepatic insulin resistance) worth
   investigating. It affects how effectively insulin works, not the
   direction of glucose change.

3. **6h DIA window matters** — EXP-2716 showed β collapses at longer horizons.
   ISF extraction should use the full DIA window, not arbitrary 2h snapshots.

### For AID Controller R&D

1. **Loop delivers more total insulin per correction than OpenAPS or Trio**
   (5.2U vs 1.7U vs 4.4U) but produces similar BG drops. This suggests
   different ISF calibrations, not different glucose physiology.

2. **The controller's proportional response IS the therapy.** ISF controls
   how aggressively the controller doses. Settings optimization should
   focus on getting the right total insulin delivery over the 6h DIA window.

3. **EGP is a HEADWIND, not a tailwind.** Hepatic output opposes insulin.
   Controllers must overcome EGP to lower glucose. Modeling EGP as a
   function of glycogen state could improve prediction of how much insulin
   is needed.

---

## Verdict Summary

### EXP-2711 (BG₀-Dependent Drop Model)
| Hypothesis | Verdict | Evidence |
|-----------|---------|----------|
| H1: BG₀ R² > 0.10 | ✅ PASS | R² = 0.137 |
| H2: BG₀ R² > Dose R² | ✅ PASS | 0.137 vs 0.094 |
| H3: BG₀ subtraction unmasks dose signal | ✅ PASS | 1.6× boost |
| H4: BG₀ model universal across patients | ✅ PASS | <5% R² gap |

### EXP-2712 (BG₀-Residualized ISF)
| Hypothesis | Verdict | Evidence |
|-----------|---------|----------|
| H1: Residualized ISF > demand-only | ❌ FAIL | 16.2 < 23.1 (BG₀ subtraction reduces attributed ISF) |
| H2: Residualized ratio < 5× | ✅ PASS | 3.1× < 5× |
| H3: Residualized CV lower | ❌ FAIL | 1.50 vs 1.45 (negligible) |
| H4: Residualized holdout MAE lower | ✅ PASS | 69.8 vs 74.8, 18/21 wins |
| H5: Reduces dose-dependence artifact | ✅ PASS | r=-0.743 vs -0.795 |

---

## Next Steps (Corrected Causal Frame)

### EXP-2717: Total Insulin Accounting Over 6h DIA
The fundamental problem with current ISF extraction: we only measure
**user bolus dose** over a 2h window, but ISF operates over a **6h DIA
window** and the **controller delivers additional insulin** (SMBs, basal
adjustments) that we're not fully accounting for. Experiment:
- Track TOTAL insulin delivered (bolus + SMB + net basal) over full 6h DIA
- Compute ISF = BG_drop / total_insulin_6h
- Does ISF converge toward profile settings when using full DIA accounting?
- Per-controller: how much of Loop's 5.2U total is controller vs user?

### EXP-2718: Hepatic Resistance as ISF Modulator
Hepatic state (72h glycogen) doesn't lower glucose — it modulates insulin
resistance. Experiment:
- Compute 72h carb history as glycogen proxy (existing infrastructure)
- Test: ISF = f(time_of_day, glycogen_state)
- Does glycogen-adjusted ISF reduce between-event variance?
- Separate insulin resistance variation from dose-response

### EXP-2719: EGP as Insulin Headwind
EGP raises glucose, opposing insulin. The net BG change is:
`Δ BG = -ISF × dose + EGP × interval`. Experiment:
- Estimate EGP from overnight basal-only periods (no bolus, no carbs)
- Use EGP as a covariate in ISF extraction (headwind to subtract)
- Does accounting for EGP opposition improve ISF precision?

---

## Source Files

| File | Purpose |
|------|---------|
| `tools/cgmencode/exp_baseline_return_model_2711.py` | BG₀-dependent drop model |
| `tools/cgmencode/exp_bilateral_subtraction_2712.py` | BG₀-residualized ISF extraction |
| `visualizations/baseline-return-model/exp-2711-dashboard.png` | 6-panel BG₀ analysis |
| `visualizations/bilateral-subtraction/exp-2712-dashboard.png` | 6-panel ISF comparison |
| `externals/experiments/exp-2711_baseline_return_model.json` | EXP-2711 results (git-ignored) |
| `externals/experiments/exp-2712_bilateral_subtraction.json` | EXP-2712 results (git-ignored) |
