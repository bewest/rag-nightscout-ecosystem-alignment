# EXP-2959 — Per-patient empirical IOB action-curve peak (NULL)

**Date**: 2026-04-23
**Audience**: Open-source AID controller authors

## Scope

Tests whether systematic per-design differences in empirical insulin
action-curve peak time could explain part of the iob_delta gap
(Loop +0.59 vs oref1 −0.04 at sustained-high) found in EXP-2944/2950.
Per-patient peak ∈ {45, 60, 75, 90, 105 min} fit by minimising RSS
of `bg_delta ~ synth_iob_entry`. DIA fixed at 300 min.

## What this is NOT

- Not a recommendation to retune anyone's pump action curve.
- Not a clinical insulin-pharmacology measurement; this is a
  controller-bookkeeping fit using a fixed bilinear curve family.

## Method

- Same sustained-high event definition as EXP-2950 (bg crosses ≥180,
  prior 30 min < 180, no carbs ±60 min, 60-min follow-up).
- For each patient with ≥30 qualifying events, evaluate
  `synth_iob_entry` at each candidate peak; regress `bg_delta`
  (60-min outcome) on synth_iob; pick peak with min RSS.
- 19 patients qualified across 5,159 events.
- Pairwise Mann-Whitney on best-peak distributions across designs.

## Results

### Best-peak by patient

| design | n_pat | peak median | peak mean | range |
|---|---|---|---|---|
| Loop_AB_OFF | 2 | 75 | 75 | 45–105 |
| Loop_AB_ON  | 5 | 75 | 75 | 45–105 |
| oref0       | 3 | 60 | 65 | 45–90 |
| oref1       | 9 | 60 | 65 | 45–105 |

### Pairwise Mann-Whitney p

All p ≥ 0.62. No design pair is statistically distinguishable.

### Improvement vs canonical 75/300

`improve_pct_vs_75` (RSS reduction as % of intercept-only RSS) is
< 1.5% for all but one patient, and < 0.5% for most. The objective
function is essentially flat across the candidate peaks — meaning
the data do not strongly identify a peak.

## Interpretation

**NULL result for the "designs use systematically different empirical
action curves" hypothesis.** The median oref1/oref0 peak is 60 min
vs Loop's 75, but:

1. The Mann-Whitney comparisons are non-significant (smallest p =
   0.62) — likely both because the sample of patients per design is
   small (2–9) and because the within-patient objective is nearly
   flat across the peak grid.
2. Improvement over peak75 is microscopic (<1.5% of RSS).

The iob_delta gap from EXP-2944/2950 is therefore **NOT explained**
by differences in patient-specific empirical insulin curves. The gap
is more likely attributable to the timing/density of insulin event
delivery (when SMBs and basal-excess pulses fire, not how those
pulses pharmacokinetically decay).

This **strengthens the framework's central claim**: between-design
differences are about *event-emission timing* (UAM, SMB triggers,
predict-and-fire) rather than insulin-pharmacokinetic differences.

## Files

- `tools/cgmencode/exp_per_patient_peak_2959.py`
- `externals/experiments/exp-2959_summary.json` (gitignored)
- `externals/experiments/exp-2959_stdout.txt` (gitignored)

## Provenance

- Input grid: `externals/ns-parquet/training/grid.parquet`
- Cohort: `externals/experiments/exp-2891_simpson_dose_response.parquet`

## Next experiment

- EXP-2962 candidate: extend grid to include DIA ∈ {240, 360} and
  finer peak resolution (15-min steps) — but objective flatness
  suggests this won't change conclusions.
- Treat 75/300 canonical curve as adequate for cross-design
  comparison; pivot to event-timing analyses.
