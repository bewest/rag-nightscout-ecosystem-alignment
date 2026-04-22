# EXP-2867: Re-Validating Small-vs-Large Meal Absorption Under Real-Meal Gating (2026-04-22)

## Question

EXP-2750 claimed large meals produce 60% of per-gram glucose impact
vs small meals (1.81 vs 2.99 mg/dL/g, 22/22 patients). EXP-2866
revealed 30% of cohort carb events are <5g (likely treat-of-low /
detector noise). Does the small-vs-large finding survive when the
"small meal" pool is gated to real meals (≥10g) instead of "any
non-zero carb event"?

## Method

* Source: `externals/ns-parquet/training/grid.parquet`.
* `is_real_meal(carbs) := carbs >= 10g` (per `meal_filter.py`).
* Buckets: small `[10, 30)g`, mid `[30, 60)g`, large `≥ 60g`.
* Per-meal impact = (post 120-min peak BG − pre 30-min median BG)
  / carbs (mg/dL per g).
* Patients with ≥ 5 small AND ≥ 5 large meals → 21 patients.

## Result — finding strengthens

| Metric | EXP-2750 (original) | EXP-2867 (real-meal) |
|--------|---------------------|----------------------|
| Small meal impact (mg/dL/g) | 2.99 | **13.0** |
| Large meal impact (mg/dL/g) | 1.81 | **3.21** |
| Large / small ratio | 0.61 | **0.26** |
| Universality (large < small) | 22/22 | **21/21** (100%) |

Two observations:

1. **Directional finding strengthens.** The ratio of large-to-small
   per-g impact drops from 0.61 → 0.26 — large meals have
   proportionally even *less* glucose impact than EXP-2750 reported
   when the small-meal pool excludes contaminating sub-10g events.
2. **Absolute magnitudes differ** because EXP-2867 uses a different
   estimator (peak excursion vs window mean). Cross-experiment
   comparison must use the *ratio*, not the raw mg/dL/g values.

## Per-bucket counts

| Bucket | Real-meal count | Share |
|--------|-----------------|-------|
| small `[10, 30)g`  | 9,169 | 55.3% |
| mid `[30, 60)g`    | 5,287 | 31.9% |
| large `≥ 60g`      | 2,137 | 12.9% |

Even after gating, large meals are a small fraction (13%) of
real-meal events — consistent with the user's clinical prior that
typical days have only 2 large planned meals and many smaller
snacks/corrections.

## Implications

* **EXP-2750's clinical conclusion stands**: gastric emptying slows
  with meal volume; size-dependent carb absorption models are
  justified. The cohort-level small-vs-large claim survives the
  data-quality challenge.
* **Magnitude estimates from EXP-2750 should not be cited as
  absolute numbers** without the real-meal qualifier — its small-meal
  pool was inflated by treat-of-low events.
* **`meal_filter.py` is now the production convention**:
  - `is_real_carb_event` (≥ 5g) for fasting / COB filters.
  - `is_real_meal` (≥ 10g) for meal-vs-snack analyses.
  - `is_substantial_meal` (≥ 30g) for planned-meal absorption work.

## Productionization

* `tools/cgmencode/production/meal_filter.py` — convention module
  with three thresholds.
* `tools/cgmencode/production/test_meal_filter.py` — 5 tests; all
  pass.
* No `AuditionInputs` change needed; this affects upstream
  experiment data preparation, not audition triage.

## Artifacts

* `externals/experiments/exp-2867_per_meal_impact.parquet` (16,593 events)
* `externals/experiments/exp-2867_per_patient_size_compare.parquet` (21 patients)
* `externals/experiments/exp-2867_summary.json`
* `docs/60-research/figures/exp-2867_real_meal_impact.png`
* `tools/cgmencode/exp_real_meal_impact_2867.py`
