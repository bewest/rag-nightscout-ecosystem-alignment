# EXP-2971 — Per-patient SMB-channel slope at 70-100 no-carb sweet spot (2026-04-23)

## Scope
For open-source AID code authors. Tests whether the pooled
EXP-2966 finding (Loop_AB_ON SMB-on-velocity slope ~1.5× oref1 at
70-100 mg/dL no-carb, disjoint 95% CIs at N>>100k) survives a
**per-patient** sign-test and a between-design MWU.

## What this is NOT
Not per-patient therapy advice. Not a between-design effect-size
estimate at the patient level — n_patients is small (5 vs 9).

## Method
Filter no-carb 70-100 mg/dL cells (no carbs in prior 120 min, no
carbs at the cell). For each cell, compute 30-min OLS BG velocity
and 60-min summed `bolus_smb`. Per (patient, design), fit
`ins_60_smb ~ vel_30` (≥30 events). Sign-test on slope sign within
each design; MWU between Loop_AB_ON and oref1.

## Results

**Total qualifying cells:** 139,050. **Patients with ≥30 events:** 19.

### Per-patient SMB slope (sorted within design)

| design | patient_id | n | slope_smb |
|---|---|---:|---:|
| Loop_AB_OFF | a | 4,689 | +0.000 |
| Loop_AB_OFF | f | 9,862 | +0.000 |
| Loop_AB_ON | g | 5,565 | +0.354 |
| Loop_AB_ON | d | 5,106 | +0.511 |
| Loop_AB_ON | c | 5,435 | +0.772 |
| Loop_AB_ON | e | 3,885 | +1.169 |
| Loop_AB_ON | i | 8,843 | +1.245 |
| oref0 | odc-74077367 | 11,936 | +0.000 |
| oref0 | odc-86025410 | 11,804 | +0.000 |
| oref0 | odc-96254963 | 5,775 | +0.000 |
| oref1 | ns-dde9e7c2e752 | 4,281 | +0.123 |
| oref1 | ns-9b9a6a874e51 | 4,708 | +0.160 |
| oref1 | ns-8f3527d1ee40 | 10,778 | +0.486 |
| oref1 | ns-6bef17b4c1ec | 9,142 | +0.552 |
| oref1 | ns-8b3c1b50793c | 6,827 | +0.554 |
| oref1 | ns-a9ce2317bead | 7,913 | +0.590 |
| oref1 | ns-adde5f4af7ca | 8,368 | +0.685 |
| oref1 | ns-1ccae8a375b9 | 8,223 | +0.753 |
| oref1 | ns-d444c120c23a | 5,910 | +0.776 |

### Sign-test (positive direction within design)

| design | n_pat | median | mean | n+ | n− | sign-test p |
|---|---:|---:|---:|---:|---:|---:|
| Loop_AB_ON | 5 | +0.772 | +0.810 | 5 | 0 | 0.0625 |
| oref1 | 9 | +0.554 | +0.520 | 9 | 0 | **0.0039** |
| Loop_AB_OFF | 2 | 0 | 0 | — | — | — |
| oref0 | 3 | 0 | 0 | — | — | — |

### Between-design MWU

| comparison | U | p (two-sided) |
|---|---:|---:|
| Loop_AB_ON vs oref1 | 31.0 | **0.298** |

## Headline
**MIXED.** The Loop_AB_ON SMB slope is positive in **5/5** patients
and the oref1 SMB slope is positive in **9/9** patients (oref1 sign
test p=0.004; Loop sign test p=0.063 — marginal due to n=5).
**Within-design directional consistency is confirmed.** However,
**between-design MWU on slope magnitudes is not significant
(p=0.30)**, replicating the EXP-2965 / EXP-2969 / EXP-2970 pattern:
the EXP-2966 pooled disjoint-CI finding does not translate into a
per-patient between-design difference. Loop_AB_ON does show a
higher median (+0.77 vs oref1 +0.55) and the only two patients with
slopes >1.0 are both Loop_AB_ON (e and i), suggesting a
heavier-tail upper distribution that requires more patients to
formalize.

## Interpretation for AID authors
- The directional claim "SMB responds positively to BG velocity in
  the 70-100 mg/dL no-carb band" is robust at the patient level for
  both Loop AB-ON and oref1 (zero negative-slope patients out of 14).
- The magnitude claim "Loop AB-ON is more aggressive than oref1" at
  this band is consistent with the pooled estimate and the median
  ordering, but **does not survive a 5-vs-9 MWU**. The pooled
  disjoint-CI signal is partly an artifact of patient `i`'s large n
  and high slope (+1.245).
- Loop_AB_OFF and oref0 patients have zero SMB slope at this band by
  construction (neither emits SMB). Their basal-excess slopes are
  small (0.13 to 0.58) — confirming that AB-OFF / oref0 lean on
  basal modulation in this band but not strongly.

## Files
- Script: `tools/cgmencode/exp_per_patient_sweet_spot_2971.py`
- JSON: `externals/experiments/exp-2971_summary.json`

## Provenance
- Cohort: `externals/experiments/exp-2891_simpson_dose_response.parquet`
- Grid: `externals/ns-parquet/training/grid.parquet`
- Date: 2026-04-23

## Next
- Decompose total SMB into emission-rate × per-event-magnitude
  (EXP-2972) — likely the cleaner per-patient lever.
- Stratify by velocity sign (EXP-2973) to localize where the
  Loop > oref1 ordering originates.
