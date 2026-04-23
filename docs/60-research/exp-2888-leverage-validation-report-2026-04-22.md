# EXP-2888 — Hidden-Leverage Construct Validation (and the Counterfactual-Outcome Problem)

**Date:** 2026-04-22
**Stream:** Construct validation / counter-causal audit
**Status:** Composite score FAILS observed-outcome validation — but
this is itself a counter-causal finding, not a pure null

## 1. Hypothesis

EXP-2886 constructed
`hidden_leverage = stack_score × (1 − braking_ratio)` as a composite
phenotype score.  EXP-2887 rejected the mechanistic lineage story
around it.  This experiment asks the orthogonal question: **does the
composite predict the outcome it was designed to flag (severe hypo
fraction)?**

## 2. Method

- n = 19 patients with full phenotype + HAAF outcome data
- Univariate Spearman correlations: each component and the composite
  vs `severe_fraction` (and `hypo_fraction`)
- OLS comparison: 3-component model (stack, brake, CR) vs composite
  (hidden_leverage alone) predicting `severe_fraction`
- Kruskal-Wallis across archetypes

## 3. Results

### 3.1  Univariate correlations (all non-significant)

| predictor               | ρ       | p     |
| ----------------------- | ------- | ----- |
| hidden_leverage         | −0.174  | 0.48  |
| stack_score             | −0.039  | 0.88  |
| braking_ratio           | +0.196  | 0.42  |
| counter_reg_intercept   | −0.095  | 0.70  |

None of the phenotype axes — not the composite — correlate
monotonically with observed severe-hypo fraction.

### 3.2  Model comparison

| model                     | adj R² |
| ------------------------- | ------ |
| 3-component linear        | +0.208 |
| composite-only (leverage) | −0.019 |

The 3-component model retains ~21 % of outcome variance; the
composite *loses* information relative to its constituents.  The
multiplicative `stack × (1−brake)` compression was convenient but
is not optimal.

### 3.3  Archetype stratification

Severe hypo fraction by archetype (Kruskal-Wallis p = 0.63):

| archetype            | n | mean   | median |
| -------------------- | - | ------ | ------ |
| algorithm_dependent  | 6 | 0.98 % | 0.95 % |
| exposed_stacker      | 2 | 2.19 % | 2.19 % |
| **hidden_leverage**  | 3 | 1.74 % | 0.66 % |
| lax_braking          | 1 | 3.99 % | —      |
| stacker_balanced     | 1 | 0.51 % | —      |
| stacker_weak_defense | 1 | 0.30 % | —      |
| well_defended        | 5 | 0.73 % | 0.69 % |

The three "hidden-leverage" patients look *indistinguishable* from
"well_defended" on observed severe-hypo fraction (median 0.66 %
vs 0.69 %).

## 4. Counter-causal interpretation — why the null is expected

A naive reading:  the composite is invalid; abandon it.

A more careful reading: **we measured the wrong outcome.**

The risk that `hidden_leverage` is designed to flag is *conditional*:
> *What would happen to this patient if the AID controller
> disengaged while it was actively suspending basal against a
> rapidly falling BG?*

The outcome we correlated against — `severe_fraction` — measures
severe hypos that *occurred while AID was running*.  By construction,
the AID is most active for hidden-leverage patients exactly when
they're most fragile — it *prevents* the very outcome we're using
to validate the score.

This is a textbook collider /  intervention problem:

```
   aggressive_settings  ──►  stack_score  ──┐
                                            ├─► hidden_leverage  ──►  counterfactual severe hypo
   AID quality ──►  braking_ratio  ─────────┘                               │
                       │                                                    │
                       ▼                                                    │
                  observed severe_fraction  ◄───────────── AID intervention ┘
                       (validation target)          (selection force)
```

AID intervention is a **selection force** that severs the link
between the construct and the observed outcome.  The construct is
potentially still valid; the validation target is wrong.

### The correct validation targets

To validate `hidden_leverage` rigorously we need *counterfactual*
outcomes:

1. **AID-off simulation** (EXP-2889): replay forward the IOB +
   carb-effect curve assuming the pump delivered scheduled basal
   instead of the suspension the AID executed.  Time-to-hypo under
   this simulated disengagement is the construct's natural outcome.
2. **Natural AID-off windows**: identify real intervals where the
   AID actually failed to suspend (connectivity loss, sensor dropout,
   manual overrides) and measure BG trajectories there.
3. **Brake-saturation escapes**: find events where `actual_basal = 0`
   *and* BG still undershoots the target.  These are the data where
   the brake's protection was insufficient — the observed
   breakthroughs.

EXP-2889 will do #1 as a controlled test.

## 5. What is still recoverable

Even without a validated composite, the three-component linear
model (adj R² = 0.208) *does* have modest explanatory power for
observed severe_fraction.  This is not nothing: it says the axes
are jointly informative even if no single axis is.

Practical consequence: **use the three axes as separate audition
signals, not a single score.**  Drop `hidden_leverage_score` from
the audition matrix; keep `stack_score`, `braking_ratio`, and
`counter_reg_intercept` as orthogonal inputs to clinician review.

## 6. Meta-lesson: counter-causal layers at different timescales

This experiment is a clean illustration of a pattern we've now hit
repeatedly:

| Timescale | Confounder | Technique that addresses it |
| --------- | ---------- | --------------------------- |
| 5-min     | AR(1) dominance hides physics | Hourly aggregation (EXP-2800) |
| Event     | Confounding by indication (harder corrections get more insulin) | Regression-based ISF with explicit confounders (EXP-2754); category-specific AR(2) (EXP-2793) |
| Event     | Controller intervention hides physiology | BGI subtraction; correction-denominator (EXP-2755) |
| Cohort    | Single patient dominates pooled median | Per-patient aggregation before pooling (EXP-2885) |
| Cohort    | Apparent group effect is sampling noise | Significance + mediation audit (EXP-2887) |
| Cohort    | **Outcome itself is modified by the intervention under study** | **Counterfactual simulation (EXP-2888 → EXP-2889)** |

See `docs/60-research/deconfounding-toolkit-2026-04-22.md` for the
consolidated methodology catalog.

## 7. Verdict

- Composite `hidden_leverage` **loses** predictive power relative to
  its components (adj R² −0.019 vs +0.208).  Deprecate the composite.
- Three axes (stack, brake, CR) remain jointly useful — use as
  separate signals.
- Observed `severe_fraction` is the **wrong** outcome to validate a
  counterfactual-risk score against.  Proceed to EXP-2889
  (AID-off simulation) for the correct outcome.
- Archetypes are not outcome-stratified in observed data; do not
  present archetype labels as severity indicators to clinicians
  without the counterfactual outcome attached.

## 8. Artifacts

- `tools/cgmencode/exp_leverage_validation_2888.py`
- `externals/experiments/exp-2888_leverage_validation.parquet`
- `externals/experiments/exp-2888_leverage_validation_summary.json`
- `docs/60-research/figures/exp-2888_leverage_validation.png`
