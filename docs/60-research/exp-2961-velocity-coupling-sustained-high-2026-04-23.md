# EXP-2961 — Velocity-vs-insulin coupling at sustained-high (no meal) — POSITIVE w/ surprise

**Date**: 2026-04-23
**Audience**: Open-source AID controller authors

## Scope

Tests whether the velocity-vs-insulin coupling observed at PP
(EXP-2960) persists OUTSIDE the meal context, isolating it as a
controller property rather than a meal-detection artefact.

## What this is NOT

- Not a per-patient therapy claim.
- Not a head-to-head clinical superiority statement.
- Not within-patient causal inference; between-design slopes only.

## Method

- Sustained-high entry: BG crosses above 200 mg/dL with **no carbs in
  prior 120 min**.
- Non-overlapping windows: skip events whose window overlaps a
  previous accepted event's `[0, +60min]`.
- BG velocity in [0, +30 min]: linear-regression slope on minutes.
- Total insulin in [0, +60 min]: `bolus + bolus_smb +
  max(actual_basal_rate − scheduled_basal_rate, 0) × 5/60`.
- Per-design regression `ins_60_total ~ vel_30` (single + multi-factor
  controlling `bg_entry`); component breakdown for SMB and basal
  excess.

## Results

### Per-design means (3,375 events)

| design | n | n_pat | vel_mean | ins_total | smb | basal_x | bolus |
|---|---|---|---|---|---|---|---|
| Loop_AB_OFF | 662 | 2 | 0.695 | 3.97 | 0.00 | 1.58 | 2.40 |
| Loop_AB_ON  | 1392 | 5 | 0.359 | 5.58 | 2.06 | 0.12 | 3.40 |
| oref0       | 534 | 3 | 0.087 | 1.12 | 0.00 | 0.29 | 0.83 |
| oref1       | 787 | 9 | 0.026 | 3.80 | 1.26 | 0.07 | 2.47 |

### Per-design `ins_60_total ~ vel_30` slope (U per mg/dL/min)

| design | n | single (95% CI) | multi-factor | SMB-only | basal-excess-only |
|---|---|---|---|---|---|
| Loop_AB_OFF | 662 | +1.18 (+1.00, +1.35) | +1.18 | n/a | +0.116 |
| Loop_AB_ON  | 1392 | **+2.05 (+1.88, +2.23)** | +2.06 | +0.781 | +0.033 |
| oref0       | 534 | **+0.06 (−0.02, +0.15)** | +0.07 | n/a | +0.019 |
| oref1       | 787 | +0.98 (+0.81, +1.15) | +0.97 | +0.385 | +0.006 |

## Interpretation

1. **Velocity-coupling persists outside meal context** for Loop and
   oref1 designs — it is a controller property, not a meal-detection
   artefact. Adds an independent evidence line for lever (3).
2. **SURPRISE**: at sustained-high, **Loop_AB_ON's slope (+2.05) is
   ~2× oref1's (+0.98)** — the OPPOSITE ordering from PP (EXP-2960).
   Loop's auto-bolus appears more aggressive at non-meal high-velocity
   excursions; the SMB-only sub-slope (+0.78) is also ~2× oref1's
   (+0.39).
3. **oref0 slope is essentially zero** (+0.06, CI crosses 0). The
   oref0 cohort lacks SMB so its only velocity-response channel is
   temp-basal, which is too small/slow to register here. This is
   consistent with the EXP-2963 finding that the −0.27 oref0 slope at
   PP was a user-bolus artefact, not a controller property.
4. The cross-context flip (oref1 > Loop at PP, Loop > oref1 at
   sustained-high) suggests **oref1 is more aggressive at meal
   onset** while **Loop's auto-bolus is more aggressive at
   non-announced excursions**. AID-author lever map needs both
   contexts.

## Files

- `tools/cgmencode/exp_velocity_coupling_sustained_high_2961.py`
- `externals/experiments/exp-2961_summary.json` (gitignored)
- `externals/experiments/exp-2961_stdout.txt` (gitignored)

## Provenance

- Input grid: `externals/ns-parquet/training/grid.parquet`
- Cohort: `externals/experiments/exp-2891_simpson_dose_response.parquet`
- Loop_AB_OFF n_pat=2, Loop_AB_ON n_pat=5, oref0 n_pat=3, oref1 n_pat=9.

## Next experiment

- EXP-2965 candidate: per-patient slopes at sustained-high (analogue
  to EXP-2962) to test heterogeneity of the Loop_AB_ON +2.05 finding.
- EXP-2966 candidate: time-series of velocity-coupling slope across
  bg-bands to map lever (3) into a controller-design surface.
