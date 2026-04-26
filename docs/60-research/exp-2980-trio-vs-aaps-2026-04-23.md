# EXP-2980 — Trio vs AAPS platform isolation (within oref1 lineage)

**Date**: 2026-04-23
**Audience**: Open-source AID code authors
**Scope**: Test whether oref1 dosing patterns differ between Trio
(iOS) and AAPS (Android) — same algorithm, different platform.
**What this is NOT**: a Trio vs AAPS clinical comparison.

## Result — MERGED LABEL, CANNOT SEPARATE

Cohort controller distribution:

| controller | n patients |
|------------|----:|
| Trio       | 9 |
| Loop       | 7 |
| AAPS       | 3 |

**All 9 patients in the `oref1 (modern)` lineage are
controller=Trio.** The cohort contains no AAPS patients. Therefore
Trio-vs-AAPS platform isolation **cannot be performed in this
dataset**.

## Implication — re-label oref1 findings as Trio-specific

The "oref1" label in EXP-2972 / 2973 / 2975 / 2978 is technically
**Trio (oref1 lineage)**. Findings such as:

- em_rate 0.080 at 70-100 no-carb (vs Loop_AB_ON 0.039)
- frequency-lever vs Loop's magnitude-lever decomposition
- U-shape with vertex 347 mg/dL (out-of-range)
- per-patient sustained-high em_rate range 0.11–0.34

are **measured on Trio**, not on AAPS. They likely transfer to
AAPS-on-Android because the algorithm code is the same fork, but
**iOS / Android implementation differences** that could shift
results include:

- BLE callback timing (iOS coalesces; Android Doze can delay)
- Profile-sync cadence and basal-segment boundaries
- Treatment write-back latency to Nightscout
- 5-min loop-cycle scheduler granularity (iOS BackgroundTasks vs
  Android AlarmManager)

## Future work to close this gap

- Add AAPS-NS exports to the cohort (target: 3–5 patients).
- Re-run EXP-2972 / 2973 / 2978 stratified by controller; if
  Trio-vs-AAPS estimates overlap, the algorithmic generalization
  is confirmed; if they diverge, the gap **isolates platform
  effects from algorithm effects** — a direct AID-author lever
  (improve Android scheduling, or improve iOS BLE wake-up).

## Honest limitation

EXP-2980 produces a **null verdict by data availability**, not by
test outcome. We re-label our prior "oref1" claims to be precise
and document the missing AAPS sub-cohort as a known gap.

## Source / data

- Script: `tools/cgmencode/exp_trio_vs_aaps_2980.py`
- Output: `externals/experiments/exp-2980_summary.json`
- Cohort: `exp-2891_simpson_dose_response.parquet`
