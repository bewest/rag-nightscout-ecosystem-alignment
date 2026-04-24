# EXP-2982 — Loop overshoot-governor counterfactual (patient `i`)

**Date**: 2026-04-23
**Audience**: Open-source AID code authors
**Scope**: For patient `i`'s 361 rising-70-100 no-carb SMB
events, project counterfactual outcomes when SMB dose is capped
at fractions {1.0, 0.8, 0.6, 0.4, 0.2} of observed (proxy for
Loop's `maxPartialApplicationFactor` / glucose-based
applicationFactor strategy).
**What this is NOT**: a Loop simulator. The projection adds a
**linear** insulin-action correction (Bateman approximation,
peak 75 min, DIA 360 min, ISF 50 mg/dL/U) to the observed
post-event trajectory:

```
bg_cf(t) = bg_obs(t) + ISF * (D_obs - D_cf) * cum_activity(t)
```

This ignores feedback (IOB-aware re-cancellation, basal
modulation, sensor noise, autosens). It brackets the marginal
effect of cap reduction only.

## Result — NEGATIVE / NULL

Across all caps from 1.0 → 0.2:

| cap | projected overshoot 180 (60 min) | projected Δ-TTT (min) |
|----:|---------------------------------:|---------------------:|
| 1.00 | **10.5%** (observed) | 0.0 |
| 0.80 | 11.6% | 0.0 |
| 0.60 | 11.9% | 0.0 |
| 0.40 | 12.2% | 0.0 |
| 0.20 | 12.5% | 0.0 |

Observation: under the linear projection the overshoot rate
**slightly INCREASES** as cap shrinks (smaller dose → less
counter-rise → marginally more 180 crossings). Median TTT
is unchanged because in the events where BG reaches 100 within
60 min, it does so within the first one or two 5-min bins
regardless of dose magnitude.

## Mechanism interpretation

In the rising-70-100 stratum, the **rise is endogenous** (carb
absorption residual, dawn phenomenon, exercise rebound,
counter-regulation). The SMB Loop fires (median 0.40 U,
ISF 50 ⇒ ~20 mg/dL "headroom") is **small relative to the
rise**. The trajectory ends above 180 because the rise is
already in motion, not because the SMB pushed it there.
Therefore, **capping the SMB does not prevent the overshoot**;
it only marginally reduces the post-peak fall.

The implication for Loop authors: the lever to reduce overshoot
in this stratum is **not** PAF reduction. Candidates that this
analysis cannot test but are worth investigating:

- Earlier dosing (when BG was 110-130 ascending) so the SMB has
  more time to act before the peak. Loop's
  `glucoseBasedApplicationFactor` actually *suppresses* dosing
  at low BG, which delays the response.
- Pre-emptive temp basal increase rather than SMB.
- Tighter `eventualBG` target to fire SMB earlier in the rise.

## Cite

- `externals/LoopWorkspace/Loop/Loop/Managers/LoopDataManager.swift:1825-1839`
  — `ApplicationFactorStrategy`, `effectiveBolusApplicationFactor`,
  `maxPartialApplicationFactor`.
- `externals/LoopWorkspace/Loop/Loop/Managers/LoopDataManager.swift:68,873-877`
  — `timeBasedDoseApplicationFactor` clamp on partial doses
  shortly after the previous loop cycle.

## Verdict

**NEGATIVE**: PAF-style cap reduction does not reduce projected
overshoot in the rising-70-100 stratum for patient `i`.
Recommended cap = 1.00 (i.e., **do not reduce**). The overshoot
risk is in the rise dynamic, not in the SMB magnitude.

## Honest caveats

- Single patient (`i`); EXP-2981 confirms `i` is an outlier in
  this stratum so generalization to other Loop users is not
  warranted.
- Linear projection ignores closed-loop feedback. A real Loop
  re-evaluation would observe `bg_cf` higher and might trigger
  *additional* SMBs in subsequent cycles, which could change the
  trajectory in either direction.
- ISF=50 mg/dL/U is a population default; patient `i`'s actual
  ISF is unknown to this dataset.

## Source / data
- `tools/cgmencode/exp_loop_overshoot_governor_2982.py`
- `externals/experiments/exp-2982_summary.json`
