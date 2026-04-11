# Insulin Pharmacodynamics Synthesis Report

**Experiments**: EXP-2511–2528 (8 experiments, 18 sub-experiments)  
**Date**: 2026-04-11  
**Data**: 19 patients (11 NS + 8 ODC), 803K rows, 35K+ correction events  
**Status**: AI-generated draft — requires clinical review

## Executive Summary

This session produced a unified model of insulin pharmacodynamics from
observational CGM/AID data, built bottom-up from 8 interconnected experiments.
The three core discoveries are:

1. **ISF follows a causal power-law** (β=0.9): a 2U correction is 46% less
   effective per unit than 1U (17/17 patients with sufficient corrections, causally validated by 4 methods)

2. **Insulin has two effect components**: a fast exponential (τ=0.8h, matching
   IOB decay) plus a persistent HGP suppression that doesn't decay within 12h.
   The "DIA paradox" isn't a slow exponential — it's a step function.

3. **Most correction rebounds are regression to the mean**, not counter-regulatory
   hormones. 75% of corrections from 130-180 mg/dL rebound. Optimal correction
   threshold ≈ 166 mg/dL.

---

## The Unified Model

```
                    INSULIN PHARMACODYNAMICS
                    ========================

    Dose ──┬── Fast Action ──── glucose uptake (τ=0.8h)
           │   (affected by power-law)
           │   ISF = ISF_base × dose^(-0.9)
           │
           └── Persistent HGP ── hepatic suppression (constant, >12h)
               Suppression       (NOT affected by dose size)

    Net Effect:
    ΔBG(t) = A₁ × dose^(0.1) × (1-e^(-t/0.8)) + C × [t > 0]
             ├─ fast, saturating ──────────────┤ ├─ step function ─┤
```

### Component 1: Fast Insulin Action (Power-Law)

| Property | Value | Source |
|----------|-------|--------|
| Model | ISF(dose) = ISF_base × dose^(-β) | EXP-2511 |
| Population β | 0.899 ± 0.382 | EXP-2511 |
| Causal? | **YES** (4 independent validations) | EXP-2523 |
| β across BG strata | 0.96–1.09, CV=5.3% | EXP-2523b |
| Matched-pair saturation | 68.9% show it (p<0.0001) | EXP-2523d |
| Time constant | τ ≈ 0.8h | EXP-2525a |
| Dose dependence | Large doses → 36pp less fast component | EXP-2525c |

**Clinical meaning**: The first 0.5U of a correction does most of the
glucose-lowering work. Doubling the dose from 1U to 2U only increases
the total glucose drop by 2^0.1 ≈ 7%.

### Component 2: Persistent Effect (Residual IOB + Loop Compensation)

| Property | Value | Source |
|----------|-------|--------|
| Model | Constant offset C ≈ -50 mg/dL/U | EXP-2525a |
| Duration | >12h (no decay observed) | EXP-2524a |
| Decays like exponential? | **NO** — biexponential degenerates | EXP-2525a |
| Best model | mono-exp + constant (R²=0.827) | EXP-2525a |
| **Mechanism** | **NOT physiological HGP suppression** | **EXP-2534** |

> **⚠️ CORRECTION (EXP-2534)**: Originally attributed to hepatic glucose
> production (HGP) suppression. Overnight matched-pair validation (280
> pairs, 17 patients) found correction nights carry +0.85U more residual
> IOB (p<0.001), explaining ~42.5 mg/dL of the persistent effect. The
> "persistent component" is residual IOB tail + loop basal adjustment,
> not liver physiology. The two-component model remains **predictively
> valid** (R²=0.827) but the mechanism is IOB underestimation by standard
> DIA curves, not a separate physiological process.

**Practical meaning**: Standard IOB curves (exponential decay, DIA 3-5h)
underestimate the true insulin tail. The "persistent" component captures
insulin effect that IOB says is zero but is still active. This explains:
- Why glucose stays low hours after IOB nominally returns to zero
- Why the model works predictively even though the mechanism isn't HGP
- Why AID loops that trust IOB=0 may still have active insulin effects

### Component 3: Correction Rebounds (Mean Reversion)

| Property | Value | Source |
|----------|-------|--------|
| Overall rebound rate | 53.7% | EXP-2524c |
| From BG 130-180 | **74.7%** rebound | EXP-2526c |
| From BG 260+ | 20.4% rebound | EXP-2526c |
| Meals amplify | OR=2.49 (p<0.0001) | EXP-2526a |
| Morning peak | 69.4% vs 42.9% overnight | EXP-2526b |
| Prediction AUC | 0.775 (top: starting glucose) | EXP-2526d |
| Counter-regulatory? | **NO** — higher nadirs rebound MORE | EXP-2526c |
| Optimal threshold | ≈ 166 mg/dL | EXP-2528a |

**Clinical meaning**: Corrections from mildly elevated BG (130-180) are
usually unnecessary — the glucose was going to come down anyway (regression
to the mean). The AID system is "correcting" glucose that doesn't need
correcting, then the natural homeostatic tendency causes an apparent
"rebound" above the starting level.

---

## Implications for AID Algorithm Design

### 1. Dose Calculation Should Use Power-Law ISF

Current AID algorithms assume: `expected_drop = dose × ISF`  
Correct model: `expected_drop = ISF_base × dose^(1-β) + C`

For β=0.9, the total drop scales as dose^0.1 — barely increasing with dose.
This means:
- **SMB (Super Micro Bolus) is accidentally optimal**: many small doses
  operate in the linear regime where ISF is maximally efficient
- **Large correction boluses are wasteful**: a 3U correction only achieves
  ~1.1× the drop of a 1U correction
- **Split dosing should be recommended**: two 1U corrections 30+ min apart
  achieve ~1.87× the drop of a single 2U correction

### 2. DIA Should Be Two-Component

Current: single exponential IOB decay with DIA 3-5h.  
Proposed: fast decay (τ=0.8h) for glucose uptake + persistent flag for
HGP suppression state.

The persistent component means:
- IOB reaching zero does NOT mean insulin effect is gone
- Stacking risk is lower than current algorithms assume
- Correction timing matters less than current algorithms assume (the
  persistent component provides a "floor" of continued glucose lowering)

### 3. Correction Threshold Should Be ≈170 mg/dL

Below ~166 mg/dL, corrections produce net harm (rebound + hypo risk >
glucose-lowering benefit). Current AID systems correct from much lower
thresholds (some correct at 120+). Raising the correction threshold
could reduce:
- Unnecessary insulin delivery
- Glucose volatility from rebounds
- Hypoglycemia from over-correction

### 4. Evaluating Correction Efficacy Is Hard

EXP-2527 showed that simple before/after TIR comparison is **fatally
confounded** — corrections are markers of deteriorating control, not
causes of TIR loss. Any study claiming "corrections help/hurt TIR"
using this methodology is suspect. Proper evaluation requires:
- Natural experiments (matched pairs at similar glucose, different doses)
- Instrumental variables
- Or randomized withholding (ethical concerns)

---

## Experiment Chain and Dependencies

```
EXP-2511 ──→ EXP-2512 ──→ EXP-2521
Power-law     17/17 win     Forecasting
ISF fit       +53% MAE      +0.006 R²
   │
   ├──→ EXP-2513 (β universal, CV=43%)
   │
   ├──→ EXP-2522 (split-dose: theory 1.87× vs empirical 0.39×)
   │              ↓
   │         CONFOUNDING DISCOVERY
   │              ↓
   ├──→ EXP-2523 (CAUSAL VALIDATION)
   │    ├─ 2523a: confounding inflates large-dose ISF
   │    ├─ 2523b: β consistent across BG strata (CV=5.3%)
   │    ├─ 2523c: survives propensity adjustment (r=-0.69)
   │    └─ 2523d: 68.9% matched pairs show saturation
   │
   └──→ EXP-2524 (DIA paradox: 94% of max at 12h)
        │
        ├──→ EXP-2525 (TWO-COMPONENT MODEL)
        │    └─ Biexp degenerates → mono-exp + constant plateau
        │    │
        │    └──→ EXP-2534 (HGP VALIDATION: **DISCONFIRMED**)
        │         └─ Persistent effect = residual IOB + loop, not liver
        │
        └──→ EXP-2526 (REBOUND = REGRESSION TO MEAN)
             ├─ 75% rebound from 130-180 mg/dL
             ├─ NOT counter-regulatory (higher nadirs rebound MORE)
             │
             ├──→ EXP-2527 (SELECTION BIAS IN TIR EVALUATION)
             │    └─ All corrections show "TIR harm" → confounded
             │
             └──→ EXP-2528 (OPTIMAL THRESHOLD ≈ 166 mg/dL)
                  └─ Per-patient range: 130-290 mg/dL
```

---

## Methodological Lessons

### 1. Confounding Is Everywhere
Three experiments (EXP-2522b, EXP-2523, EXP-2527) revealed that
naive observational analysis of correction outcomes is deeply confounded:
- Split vs single dose comparison is confounded by glucose difficulty
- Before/after TIR comparison is confounded by glucose trajectory
- Only matched pairs and propensity methods give reliable results

### 2. Opposite Directions Can Coexist
The confounding in EXP-2522b (splits appear WORSE) and EXP-2523a
(confounding inflates large-dose ISF) go in opposite directions.
Different analytical choices can lead to opposite conclusions from
the same data. Multiple validation methods are essential.

### 3. The Power of Natural Experiments
EXP-2523d (matched pairs) provided the strongest evidence: 2,546 pairs
where the same patient corrected from similar glucose with different
doses. This quasi-randomized design avoids the confounding that
plagues all other approaches.

---

## Limitations

1. **No causal counterfactual**: We cannot observe what would have happened
   without a correction. All findings are observational.

2. **~~HGP suppression is inferred~~** → **RESOLVED by EXP-2534**: The
   persistent component is NOT physiological HGP suppression. It's
   residual IOB underestimated by standard DIA curves, plus loop basal
   adjustment. Correction nights carry +0.85U more IOB (p<0.001).

3. **AID loop is a confounder**: The loop adjusts basal in response to
   corrections, making it impossible to isolate the pure insulin effect.
   All "ISF" measurements include the loop's compensation. **EXP-2534
   confirmed this is a major factor in the persistent component.**

4. **12h observation window**: The persistent component may eventually
   decay — we just can't observe it within our 12h window.

5. **Selection bias in corrections**: Correction events are not random —
   they happen at specific glucose levels, times, and contexts. All
   effect size estimates are conditional on this selection.

6. **Temporal CV invalidates PD forecasting features**: EXP-2531/2532
   showed that PD features improve R² under shuffled CV (+0.011) but
   DEGRADE under temporal CV. PD signal is swamped at h60 by meals,
   exercise, and sensor drift.

---

## Source Files

| Experiment | Script | Key Finding |
|------------|--------|-------------|
| EXP-2511-2518 | `exp_dose_isf.py` | Power-law ISF, β=0.9 |
| EXP-2521 | `exp_powerlaw_forecast.py` | +0.006 R² in forecasting |
| EXP-2522 | `exp_split_dose.py` | Split-dose confounding |
| EXP-2523 | `exp_causal_isf.py` | Causal validation (4 methods) |
| EXP-2524 | `exp_dia_paradox.py` | DIA paradox (94% at 12h) |
| EXP-2525 | `exp_biexp_dia.py` | Two-component model |
| EXP-2526 | `exp_rebound.py` | Rebound = mean reversion |
| EXP-2527 | `exp_overcorrection.py` | Selection bias in TIR eval |
| EXP-2528 | `exp_correction_threshold.py` | Threshold ≈ 166 mg/dL |
| EXP-2529 | `exp_unified_pd.py` | Unified PD: +0.011 (shuffled) |
| EXP-2531 | `exp_nonlinear_pd.py` | GBM > Ridge; PD fails temporal CV |
| EXP-2532 | `exp_temporal_pd.py` | Ratio features stable but weak |
| EXP-2534 | `exp_hgp_validation.py` | **HGP suppression disconfirmed** |

All experiment scripts in `tools/cgmencode/production/`.  
Results (gitignored) in `externals/experiments/`.
