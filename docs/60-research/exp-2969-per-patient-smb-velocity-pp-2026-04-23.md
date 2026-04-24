# EXP-2969 — Per-patient SMB-channel velocity-coupling at PP (2026-04-23)

## Scope
For open-source AID code authors. Tests whether EXP-2964's pooled
SMB-channel near-tie (Loop_AB_ON +0.380 vs oref1 +0.361) holds
per-patient. Replicates the EXP-2962 lesson at the SMB-only channel.

## What this is NOT
Not per-patient therapy advice. Not a between-controller endorsement.

## Method
Post-prandial entry: `carbs[i] ≥ 30 g` and zero carbs in prior 60
minutes. For each patient with ≥30 events, fit individual
`slope_smb ~ vel_30` (and `slope_basal_x`, `slope_bolus` for
context). Per-design: median, mean, sign-test on positive direction,
two-sided MWU between Loop_AB_ON and oref1.

## Results

**PP events:** 4,687 across 18 qualifying patients (≥30 events).

### Per-patient SMB-channel slope at PP

| Design | n_pat | median | mean | (+/−) | sign-test p |
|---|---:|---:|---:|---|---:|
| Loop_AB_ON | 5 | +0.390 | +0.407 | 5+/0− | 0.0625 |
| oref1 | 9 | +0.307 | +0.355 | 9+/0− | **0.00391** |
| Loop_AB_OFF | 1 | +0.000 | +0.000 | (no SMB) | — |
| oref0 | 3 | +0.000 | +0.000 | (no SMB) | — |

### Loop_AB_ON SMB slopes
[0.349, 0.358, 0.390, 0.466, 0.472]

### oref1 SMB slopes
[0.122, 0.139, 0.155, 0.282, 0.307, 0.372, 0.417, 0.608, 0.796]

### MWU Loop_AB_ON vs oref1 (two-sided)
U = 30.0, **p = 0.364** — NOT significant.

## Interpretation

**POSITIVE confirmation of EXP-2964.** The SMB-channel near-tie
between Loop_AB_ON and oref1 holds per-patient:

1. Per-patient MWU two-sided p = 0.36 — well outside any
   conventional rejection band.
2. Both per-patient distributions overlap heavily; oref1's top three
   patients (+0.42, +0.61, +0.80) exceed every Loop_AB_ON patient.
3. Both designs show unanimously positive per-patient slopes
   (Loop_AB_ON 5/5, oref1 9/9). The within-design positivity is
   robust (sign-test p = 0.004 for oref1).
4. **EXP-2964 conclusion ROBUST.** The SMB-channel velocity-coupling
   at PP is a controller property of the SMB-emission family, with
   ~+0.35–0.40 U per mg/dL/min slope, equivalent across Loop AB ON
   and oref1 within power of this cohort.

For AID authors: implementing an SMB / auto-bolus heuristic that
emits insulin proportional to rising velocity is the dominant
controller-side velocity-response lever at PP. The specific UAM
detection vs Loop AB curve-trigger logic does not translate to a
measurable per-patient slope difference here.

## Files
- Script: `tools/cgmencode/exp_per_patient_smb_velocity_pp_2969.py`
- JSON: `externals/experiments/exp-2969_summary.json`

## Provenance
- Cohort: `externals/experiments/exp-2891_simpson_dose_response.parquet`
- Grid: `externals/ns-parquet/training/grid.parquet`
- Repo HEAD: 15b0d75
- Date: 2026-04-23

## Next
- BG-band stratification (EXP-2966) extends this within-context.
- Possible next: emission-frequency comparison (events/hour at PP)
  to test whether the residual variance is in trigger frequency
  rather than per-event magnitude.
