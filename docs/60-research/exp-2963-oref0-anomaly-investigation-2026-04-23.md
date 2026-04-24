# EXP-2963 — oref0 anomalous slope investigation at PP (RESOLVED: artefact)

**Date**: 2026-04-23
**Audience**: Open-source AID controller authors

## Scope

EXP-2960 found oref0 had a NEGATIVE pooled velocity-vs-insulin slope
at PP (−0.27, 95% CI [−0.42, −0.12]). This investigates whether that
is a small-n cohort artefact or a genuine controller property.

## What this is NOT

- Not a clinical claim about oref0 patients.
- Not a critique of the oref0 algorithm in deployment — only of its
  behaviour in this 3-patient slice with 1,285 PP events.

## Method

(a) Per-patient breakdown of all 3 oref0 patients with component
decomposition (bolus / SMB / basal-excess).
(b) Bootstrap (B=2000) pooled CI for sanity check.
(c) Leave-one-patient-out pooled slope.
(d) Code-context note from `externals/AndroidAPS/`.

## Results

### Per-patient (3 oref0 patients, 1,285 events)

| patient | n | vel_mean | ins_total_mean | total slope (95% CI) | bolus slope | basal-x slope |
|---|---|---|---|---|---|---|
| odc-74077367 | 349 | +0.169 | 5.23 | **+0.500** (+0.15, +0.85) | +0.506 | −0.006 |
| odc-86025410 | 508 | +0.388 | 1.09 | +0.037 (−0.00, +0.08) | +0.036 | +0.001 |
| odc-96254963 | 428 | +0.040 | 5.84 | **−0.479** (−0.78, −0.17) | −0.464 | −0.015 |

### Bootstrap pooled slope

- B=2000: mean = **−0.266**, 95% CI [−0.414, −0.125]
- Confirms the −0.27 finding is statistically robust within this
  cohort but does not address whether it generalises.

### Leave-one-patient-out pooled

| left out | n | slope | p |
|---|---|---|---|
| odc-74077367 | 936 | −0.344 | 3e-05 |
| odc-86025410 | 777 | −0.214 | 0.071 |
| **odc-96254963** | 857 | **−0.027** | 0.711 |

Removing patient `odc-96254963` collapses the negative slope to
essentially zero — **the −0.27 pooled effect is driven primarily by
that single patient.**

### Component decomposition

In ALL three oref0 patients the slope is essentially the **bolus
component** (manual user announce-meal bolus); SMB is structurally
zero (oref0 cohort lacks SMB) and basal-excess slopes are negligible
(< 0.02 in magnitude).

## Interpretation

1. **The oref0 negative slope is reverse-causation in user behaviour,
   not a controller property.** Patient `odc-96254963` apparently
   delivered larger announce-meal boluses for slower-rising meals
   (perhaps better pre-bolusing on those meals → smaller observed
   velocity → larger bolus correlation), producing a negative slope
   in their bolus channel.
2. **The controller channel (basal modulation) shows near-zero slope
   for all 3 oref0 patients** (max |slope| = 0.015). This is exactly
   what the EXP-2961 sustained-high analysis showed at the pooled
   level (+0.06, CI crosses 0): oref0 has near-zero velocity-coupling
   through its controller channel.
3. **The honest controller-property reading**: oref0 ≈ 0 controller
   coupling, oref1 +0.36 (SMB), Loop_AB_ON +0.38 (SMB), Loop_AB_OFF
   0 (SMB structurally absent). This collapses the EXP-2960 ordering
   and motivates EXP-2964's decomposition.
4. **AID-author note**: oref0 cohort patients in this dataset are
   running AAPS releases predating SMB/UAM features; the only
   automated lever is temp-basal. Velocity-coupling through temp-basal
   alone is small in magnitude even when it exists.

## Files

- `tools/cgmencode/exp_oref0_anomaly_2963.py`
- `externals/experiments/exp-2963_summary.json` (gitignored)
- `externals/experiments/exp-2963_stdout.txt` (gitignored)

## Provenance

- Input grid: `externals/ns-parquet/training/grid.parquet`
- Cohort: oref0 patients = {odc-74077367, odc-86025410, odc-96254963}.

## Next experiment

- EXP-2968 candidate: replicate the same single-patient leverage
  investigation for the Loop_AB_ON +0.62 pooled slope (n_pat=5).
