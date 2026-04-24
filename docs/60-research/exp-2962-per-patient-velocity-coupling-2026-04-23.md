# EXP-2962 — Per-patient velocity-coupling at PP (CLEAN POSITIVE)

**Date**: 2026-04-23
**Audience**: Open-source AID controller authors

## Scope

Tests whether the +1.36 oref1 pooled velocity-coupling slope from
EXP-2960 is consistent across the cohort or is driven by 1–2 high-
leverage patients.

## What this is NOT

- Not a clinical recommendation.
- Not a within-patient causal claim — slopes are within-design,
  between-event regressions per patient.

## Method

- Same PP events as EXP-2960 (`carbs ≥ 30 g`, no carbs prior 60 min).
- Within each patient with ≥ 30 events, fit `ins_60_total ~ vel_30`.
- Sign-test on per-design slope distribution.
- Mann-Whitney one-sided (oref1 > Loop_AB_ON).
- Leave-one-patient-out (LOO) pooled oref1 slope robustness.

## Results

### Per-patient slope distribution

| design | n_pat | min | median | max | n+ | n− | sign-test p |
|---|---|---|---|---|---|---|---|
| Loop_AB_OFF | 1  | +1.01 | +1.01 | +1.01 | 1 | 0 | 1.00 |
| Loop_AB_ON  | 5  | +0.60 | +0.79 | +1.04 | 5 | 0 | 0.0625 |
| oref0       | 3  | −0.48 | +0.04 | +0.50 | 2 | 1 | 1.00 |
| **oref1**   | **9**  | **+0.27** | **+0.95** | **+1.76** | **9** | **0** | **0.0039** |

All 9 oref1 patients individually show a positive slope (sign-test
p = 0.0039).

### oref1 leave-one-patient-out pooled slopes

| left out | n events | pooled slope |
|---|---|---|
| ns-1ccae8a375b9 | 1983 | +1.33 |
| ns-6bef17b4c1ec | 2059 | +1.38 |
| ns-8b3c1b50793c | 2029 | +1.21 |
| ns-8f3527d1ee40 | 1927 | +1.48 |
| ns-9b9a6a874e51 | 1962 | +1.28 |
| ns-a9ce2317bead | 2003 | +1.41 |
| ns-adde5f4af7ca | 2082 | +1.38 |
| ns-d444c120c23a | 2260 | +1.38 |
| ns-dde9e7c2e752 | 2087 | +1.38 |

LOO pooled slopes range +1.21 to +1.48 — the +1.36 finding from
EXP-2960 is **not** driven by any single patient.

### Mann-Whitney oref1 vs Loop_AB_ON per-patient slopes

- U = 29.0, p (one-sided, oref1 > Loop_AB_ON) = **0.219**
- oref1 sorted: [0.27, 0.45, 0.73, 0.84, 0.95, 1.04, 1.36, 1.62, 1.76]
- Loop_AB_ON  : [0.60, 0.62, 0.79, 0.87, 1.04]

The medians are similar (0.95 vs 0.79) and the Loop_AB_ON
distribution sits inside the oref1 distribution. The pooled-slope
between-design effect IS real but its magnitude does NOT survive
patient-as-unit inference (n_pat=5 vs 9, MWU not significant).

## Interpretation

1. **The oref1 +1.36 pooled slope is robust to LOO and consistent
   across all 9 oref1 patients individually** — this is a real
   within-design phenomenon, not a one-patient artefact.
2. **HONEST DOWNGRADE of EXP-2960's headline**: oref1 vs Loop_AB_ON
   per-patient slopes are NOT significantly different by Mann-Whitney
   (p=0.22). The pooled-events comparison conflates patient-count and
   event-count weighting; per-patient is the correct unit for
   between-design inference. The framework should describe this as a
   **trend** (median +0.95 vs +0.79) consistent with lever (3), not a
   confirmed between-design contrast.
3. The within-design positive sign for all 9 oref1 patients
   (p = 0.0039 sign-test) IS strong evidence that **as a controller
   class, oref1 couples insulin to early rising velocity** — it just
   doesn't significantly exceed Loop_AB_ON's coupling at the per-
   patient level in this cohort.

## Files

- `tools/cgmencode/exp_per_patient_velocity_coupling_2962.py`
- `externals/experiments/exp-2962_summary.json` (gitignored)
- `externals/experiments/exp-2962_stdout.txt` (gitignored)

## Provenance

- Input grid: `externals/ns-parquet/training/grid.parquet`
- Cohort: `externals/experiments/exp-2891_simpson_dose_response.parquet`

## Next experiment

- EXP-2967 candidate: bootstrap CI on the median-of-per-patient-slope
  per design to formalise the patient-as-unit framing.
