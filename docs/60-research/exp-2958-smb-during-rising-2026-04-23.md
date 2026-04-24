# EXP-2958 — SMB-during-rising mechanism within-patient at sustained-high (NEGATIVE / REVERSE-CAUSED)

**Date**: 2026-04-23
**Audience**: Open-source AID controller authors

## Scope

Refines synthesis lever (3) (predict-and-fire on rising velocity).
Tests at sustained-high whether WITHIN-window cumulative SMB volume
in the first 30 min of a high-BG event predicts subsequent recovery
(delta_60 = bg(+60) − bg(entry)) within each patient. AID-author
audience.

## What this is NOT

- Not therapy advice and not a per-patient recommendation.
- Not a refutation of the IOB-age framework — see Interpretation;
  the result here reflects controller reactivity, not insulin
  inefficacy.
- Not a controlled experiment: SMB delivery is not exogenous to BG
  trajectory.

## Method

- Window: bg crosses ≥200 mg/dL with no carbs in prior 120 min and
  no carbs across the 60-min outcome window.
- Outcome: `delta_60 = bg(+60min) − bg(entry)`.
- Predictor: `smb_30 = sum(bolus_smb)` across cells [0, +30 min].
- Per-patient regression (single AND multi-factor controlling for
  bg_entry, scheduled_basal_rate, prior 60 min bolus).
- Sign-test across patients with ≥20 events and SMB variability.
- N = 1,812 events; 13 patients qualified (Loop_AB_OFF and oref0
  excluded by zero-SMB filter).

## Results

### Per-design event-level means

| design | n | smb_30 mean | smb_30 zero% | delta_60 mean (mg/dL) |
|---|---|---|---|---|
| Loop_AB_OFF | 328 | 0.00 | 100% | +16.6 |
| Loop_AB_ON  | 790 | 1.40 | 16% | +9.6 |
| oref0       | 289 | 0.00 | 100% | −1.4 |
| oref1       | 405 | 0.85 | 26% | −23.0 |

The unconditional pattern (oref1 lowest delta_60, highest SMB density)
is consistent with the framework at the design level.

### Per-patient regression

| version | n_pat | n_neg | sign p | median slope | t-test p |
|---|---|---|---|---|---|
| Single (delta_60 ~ smb_30) | 13 | 1 | 1.0 | **+12.98** | 8e-05 |
| Multi-factor (controls bg, sched_basal, pre-bolus) | 13 | 1 | 1.0 | **+11.65** | 0.002 |

12/13 patients show **positive** within-patient slope. Naive reading:
"more SMB → bg goes up more". This is **reverse causation**: the
controller delivers more SMB precisely BECAUSE the rise is steeper.
Within a patient, SMB is endogenous to trajectory.

### By design (single-predictor)

| design | n_pat | median slope | n_neg |
|---|---|---|---|
| Loop_AB_ON | 5 | +9.85 | 1/5 |
| oref1      | 8 | +14.13 | 0/8 |

## Interpretation

This is a **NEGATIVE within-patient result for the original framing**
of lever (3) at sustained-high — but the sign is the wrong way for
"SMB causes faster recovery" because we cannot disentangle dosing
intensity from trajectory severity within a single design's
controller.

The **design-level pattern remains supportive** (oref1 highest SMB
density paired with lowest delta_60 and most negative recovery), but
that's confounded with all the other oref1 vs Loop differences
already established (EXP-2944/2950/2957).

This is the within-patient PP analogue of EXP-2955: the
single-predictor signal is dominated by reverse causation /
confounding with trajectory itself. Within-patient causal inference
on controller-emitted variables requires either:
- An exogenous instrument (e.g., randomised setting changes), or
- A counterfactual simulator (replay the controller with SMB
  suppressed).

Lever (3) is therefore **not contradicted** but is **untestable
within-patient using observational data alone for SMB-recovery
coupling**.

## Files

- `tools/cgmencode/exp_smb_during_rising_2958.py`
- `externals/experiments/exp-2958_summary.json` (gitignored)
- `externals/experiments/exp-2958_stdout.txt` (gitignored)

## Provenance

- Input grid: `externals/ns-parquet/training/grid.parquet`
- Cohort: `externals/experiments/exp-2891_simpson_dose_response.parquet`

## Next experiment

- EXP-2961 candidate: counterfactual SMB-suppression replay (would
  require oref1 reference simulator) — out of scope for observational
  analysis.
- Re-frame lever (3) at sustained-high as **between-design only**;
  remove within-patient causal claim from the synthesis.
