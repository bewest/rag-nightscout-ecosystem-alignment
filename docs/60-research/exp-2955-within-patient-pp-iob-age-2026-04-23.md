# EXP-2955 — Within-patient IOB-age framework at PP windows (NUANCED)

**Date**: 2026-04-23
**Audience**: AID-author / open-source controller authors
**Purpose**: Cross-validate EXP-2954's within-patient gold-standard
template on the post-prandial channel.

## Scope

This experiment tests whether the IOB-age mechanism that explains
between-design PP TIR differences (EXP-2946) and was confirmed
within-patient at hypo (EXP-2954) ALSO holds within-patient at PP.
AID-author audience; not therapy advice.

## What this is NOT

- Not a recommendation to migrate patients between AIDs.
- Not a per-patient dosing recommendation.
- Not a refutation of the IOB-age framework — see Findings.

## Method

- Same uniform biexponential action-curve as EXP-2950/2953/2954
  (peak 75 min, DIA 300 min) over event history (`bolus + bolus_smb +
  basal_excess`).
- Window: meal events with carbs ≥ 30 g, no carbs in prior 60 min,
  follow-up 0–180 min for `bg_peak_180`.
- Outcome: `delta_peak = bg_peak_180 − bg_entry`.
- Predictor of interest: `synth_act_entry` (uniform-curve activity at
  meal onset).
- Per-patient regression, then sign-test on slope direction across
  patients (mirrors EXP-2954). ALSO multi-factor regression
  controlling for carbs and bg_entry.
- N = 4,676 events across 18 patients with ≥20 events.

## Results

### Single-predictor `delta_peak ~ synth_act_entry`

- **18/18 patients** show negative slope.
- Sign-test p = **3.8e-06**.
- Median slope = −542.5 mg/dL per activity-unit (units arbitrary).
- One-sample t-test p = 3.8e-04.

This naively reproduces EXP-2954's pattern at PP — strong cross-window
support for the framework.

### Multi-factor `delta_peak ~ synth_act_entry + carbs_g + bg_entry`

- **11/18 patients** show negative `act_entry` slope.
- Sign-test p = **0.24** (NOT significant).
- Median multi-factor slope = −76 (vs −542 single-predictor).
- One-sample t-test p = 0.13.

After controlling for meal size and starting BG, the within-patient
PP `act_entry` effect substantially weakens. The single-predictor
signal is largely explained by:

- Larger meals → smaller pre-meal IOB (people pre-bolus less for big
  meals? or more often eat at high BG that suppressed prior bolusing?)
- High bg_entry → smaller pre-meal IOB AND larger delta_peak.

Both confounders push single-predictor slope strongly negative without
implying causal IOB-age effect at PP within-patient.

## Interpretation

**The IOB-age framework remains supported at PP between designs
(EXP-2946) and at hypo within-patient (EXP-2954)**, but the
within-patient PP channel is dominated by meal context (carbs,
starting BG) rather than by pre-meal IOB-age per se.

This is biologically reasonable:
- At hypo, the system has already crashed; the *trajectory* into the
  hypo is dominated by accumulated insulin activity.
- At PP, the *response* to a meal is dominated by the meal itself
  (carbs absorbed) and the starting-BG ceiling effect.

Between-design PP differences (EXP-2946) reflect HOW each design
RESPONDS to the meal (UAM, dynamic ISF, SMB-as-correction) — not
pre-meal IOB age. The "predict-and-fire on rising velocity early"
lever in the synthesis framework is about the FORWARD response
(SMB during the rise), not about pre-meal preloading.

## Lever-priority recalibration

The synthesis Section 9 listed lever (3) as: "Predict-and-fire on
rising velocity early so IOB AGES before the BG response window —
UNIFIED across PP TIR, sustained-high recovery, and hypo defence."

This experiment refines that:

- The IOB-AGE-AS-CAUSE claim is strongest at **hypo** (within-patient
  validated EXP-2954).
- At **sustained-high**, it's between-design with strong mechanism
  support (EXP-2944/2950).
- At **PP**, the cleanest framing is: SMBs during the rising window
  mean active insulin EXISTS during the response window — not that
  pre-meal IOB-age determines outcome. Lever (3) phrasing is correct
  but the WITHIN-WINDOW activity matters more than PRE-WINDOW age.

## Files

- `tools/cgmencode/exp_within_patient_pp_iob_age_2955.py`
- `externals/experiments/exp-2955_summary.json` (gitignored)

## Provenance

- Input grids: `externals/ns-parquet/training/grid.parquet`
- Cohort: `externals/experiments/exp-2891_simpson_dose_response.parquet`

## Next experiment

- EXP-2956: per-patient hourly recovery heatmap (visualization)
- EXP-2957: action-curve sensitivity sweep (peak 60-90, DIA 240-360)
- Update synthesis Section 9 lever (3) phrasing per refinement above.
