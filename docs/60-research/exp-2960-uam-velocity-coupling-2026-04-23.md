# EXP-2960 — UAM/velocity-vs-insulin coupling at PP (CLEAN POSITIVE)

**Date**: 2026-04-23
**Audience**: Open-source AID controller authors

## Scope

Tests whether oref1's UAM (unannounced-meal) detection produces
stronger insulin-vs-rising-velocity coupling at meal events than
Loop AB OFF / AB ON / oref0. Operationalises lever (3) of the
synthesis framework (predict-and-fire on rising velocity early)
between designs at PP — a channel where lever (3) survived
EXP-2955's within-patient critique.

## What this is NOT

- Not a recommendation to enable UAM/SMB for any individual patient.
- Not a head-to-head clinical superiority claim — both Loop and oref
  designs were running with author-chosen settings.
- Not within-patient causal inference; this is between-design slope
  comparison.

## Method

- Meal events: cells with `carbs ≥ 30 g`, no carbs in prior 60 min.
- BG velocity in [0, +30 min]: linear-regression slope of glucose on
  minute-since-onset (mg/dL/min).
- Total insulin in [0, +60 min]: `bolus + bolus_smb +
  max(actual_basal_rate − scheduled_basal_rate, 0) × 5/60`.
- Per-design regression: `ins_60_total ~ vel_30` (single AND
  multi-factor controlling for `carbs_g`, `bg_entry`).
- Decomposed into SMB-only and basal-excess components.
- N = 4,687 meal events.

## Results

### Per-design means

| design | n | vel_30 (mg/dL/min) | ins_total (U) | ins_smb | basal_x | carbs (g) |
|---|---|---|---|---|---|---|
| Loop_AB_OFF | 247 | 1.33 | 12.62 | 0.00 | 0.50 | 56.1 |
| Loop_AB_ON  | 856 | 0.76 | 9.32 | 1.15 | 0.06 | 41.6 |
| oref0       | 1285 | 0.21 | 3.80 | 0.00 | 0.12 | 45.7 |
| oref1       | 2299 | 0.51 | 8.09 | 1.65 | 0.03 | 56.9 |

### Per-design slope: `ins_60_total ~ vel_30` (units U per mg/dL/min)

| design | n | single slope (95% CI) | multi-factor slope (95% CI) | SMB-only slope |
|---|---|---|---|---|
| Loop_AB_OFF | 247 | +1.014 (+0.68, +1.34) | +1.208 (+0.89, +1.52) | n/a (no SMB) |
| Loop_AB_ON  | 856 | +0.617 (+0.40, +0.84) | +0.716 (+0.49, +0.94) | +0.380 |
| oref0       | 1285 | **−0.266 (−0.42, −0.12)** | −0.288 (−0.43, −0.15) | n/a (no SMB) |
| oref1       | 2299 | **+1.365 (+1.21, +1.52)** | +1.327 (+1.18, +1.48) | +0.361 |

All slopes are statistically significant (p < 0.001).

### Headline contrast

- **oref1 vs Loop_AB_ON**: 95% CIs do not overlap (Loop max +0.84 vs
  oref1 min +1.21) → oref1 couples insulin to early rising velocity
  ~2.2× more strongly than Loop with auto-bolus.
- **Loop_AB_OFF** still shows +1.01 — but this is dominated by user
  meal-bolus behaviour (manual users dosing larger boluses for
  faster-rising meals), not autonomous controller response.
- **oref0**'s NEGATIVE slope is striking: in this cohort, oref0
  delivers LESS insulin when velocity is higher — likely a small-n
  artefact of one or two oref0 patient meal patterns dominating
  (oref0 n_pat=3) or oref0's lack of SMB making the controller
  unable to scale up at fast-rise events.

## Interpretation

**Clean independent evidence for lever (3)** at the between-design
PP channel:

1. oref1's autonomous controller response (SMB triggered by
   rising-velocity heuristics + UAM) creates a measurable
   **velocity-insulin coupling slope** that is roughly twice Loop AB
   ON's, with non-overlapping 95% CIs.
2. The SMB component of oref1's response (slope +0.36) is
   **comparable to Loop_AB_ON's SMB component (+0.38)** — Loop's
   automatic boluses do scale with velocity. The difference is in
   the additional UAM-triggered escalation that oref1 layers on top.
3. This is the FORWARD-response analogue of the
   IOB-age-as-consequence story: oref1 ages insulin earlier
   precisely BECAUSE it commits insulin earlier in response to
   rising velocity at PP.

This adds an independent evidence line for the "Finding E" framework
in the synthesis, complementing the IOB-age window observation
(EXP-2944/2950/2954/2957).

## Files

- `tools/cgmencode/exp_uam_velocity_coupling_2960.py`
- `externals/experiments/exp-2960_summary.json` (gitignored)
- `externals/experiments/exp-2960_stdout.txt` (gitignored)

## Provenance

- Input grid: `externals/ns-parquet/training/grid.parquet`
- Cohort: `externals/experiments/exp-2891_simpson_dose_response.parquet`

## Next experiment

- EXP-2963 candidate: same velocity-coupling analysis at sustained-high
  windows (does oref1's velocity-coupling persist outside the meal
  context?).
- EXP-2964 candidate: per-patient velocity-coupling slope to test
  within-design heterogeneity (do all oref1 patients show the +1.36
  slope or is it driven by one or two?).
