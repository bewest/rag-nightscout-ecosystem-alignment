# EXP-2957 — Action-curve sensitivity sweep (ROBUST)

**Date**: 2026-04-23
**Audience**: AID-author / methodological audit
**Purpose**: Confirm EXP-2950's iob_delta gap conclusion is not an
artifact of the specific uniform action-curve parameters (peak 75
min, DIA 300 min).

## Scope

Reviewer-objection audit: "what if you'd used a different IOB curve?"

## Method

Same uniform biexponential action-curve template as EXP-2950, swept
over peak ∈ {60, 75, 90} min × DIA ∈ {240, 300, 360} min (9 combos).
For each, recomputed sustained-high mechanism: iob_delta = synth_iob
at +60 min minus synth_iob at event entry, contrasted oref1 vs
Loop_AB_ON via Welch t-test.

Event detection: bg crosses above 200 with no carbs in prior 120 min.
N = 3,959 events (887 oref1, 1,675 Loop_AB_ON).

## Results

| peak | DIA | oref1 mean | Loop_AB_ON mean | gap (o−L) | p |
|-----:|----:|-----------:|----------------:|----------:|--:|
|   60 | 240 |     −0.645 |          +0.367 |    −1.012 | 3.0e-12 |
|   60 | 300 |     −0.603 |          +0.380 |    −0.983 | 1.1e-11 |
|   60 | 360 |     −0.549 |          +0.386 |    −0.934 | 1.1e-10 |
|   75 | 240 |     −0.369 |          +0.774 |    −1.143 | 2.3e-14 |
|   75 | 300 |     −0.329 |          +0.773 |    −1.103 | 1.7e-13 |
|   75 | 360 |     −0.275 |          +0.770 |    −1.046 | 2.8e-12 |
|   90 | 240 |     −0.129 |          +1.110 |    −1.239 | 3.2e-16 |
|   90 | 300 |     −0.083 |          +1.102 |    −1.185 | 5.2e-15 |
|   90 | 360 |     −0.025 |          +1.094 |    −1.119 | 1.5e-13 |

- **9/9 combos**: negative gap (oref1 sheds faster than Loop).
- **8/9 combos**: p < 1e-10 (1 combo at p = 1.1e-10, just above threshold).
- Median gap: −1.10 U.

## Interpretation

The IOB-age mechanism is robust to action-curve parameterisation
across a clinically plausible range. Magnitude varies slightly:
peak 90 (longer activity) inflates Loop's positive iob_delta because
more units remain active during the sustained-high window. But the
SIGN and SIGNIFICANCE are stable across all 9 combos.

This closes a natural reviewer objection: the uniform-curve choice
in EXP-2950 was not cherry-picked.

## Implication for synthesis

The IOB-age framework can be summarised: regardless of specific
action-curve assumption (within the standard fast-analog peak 60–90,
DIA 4–6 hour range), oref1 has *less unspent insulin activity* during
sustained-high windows than Loop_AB_ON. This is a property of
**when** the dose was delivered (predict-and-fire) not **how much**.

## Files

- `tools/cgmencode/exp_action_curve_sensitivity_2957.py`
- `externals/experiments/exp-2957_summary.json` (gitignored)

## Provenance

- Input grids: `externals/ns-parquet/training/grid.parquet`
- Cohort: `externals/experiments/exp-2891_simpson_dose_response.parquet`

## Next experiment

- EXP-2956: per-patient hourly recovery heatmap (visualization)
- AAPS ingestion (EXP-2908) structural unblock
- Patient `b` low_recovery vignette
