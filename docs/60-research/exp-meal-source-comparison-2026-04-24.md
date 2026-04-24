# Inferred-Meal Mask vs Logged-Carbs Mask in EGP Experiments (2026-04-24)

## Background

Three priority EGP experiments — **EXP-2724** (basal-circadian),
**EXP-2739** (EGP-personalization), and **EXP-2740**
(basal-EGP-equilibrium) — historically defined "fasting" rows using
**logged carbs only** (`carb_roll < 0.5 g`).  This is unsafe in the
presence of under-loggers: any meal eaten without a manual carb entry
would silently contaminate the fasting EGP estimate, biasing both the
median EGP and the variance.

## Patch

Each experiment now accepts an optional `patient_id` and applies an
**inferred-meal exclusion overlay** on top of the logged-carb test:

```python
mask = identify_fasting_mask(pdf, patient_id=pid)
# internally:
#   mask &= ~within(±[2h-pre, 4h-post], inferred_meal_centers)
```

The overlay is sourced from
`production/inferred_meals_facts_loader.InferredMealsLoader`, which
caches the spectral residual+insulin meal detector outputs at
`externals/experiments/inferred_meals_<pid>.parquet`.  The default
window matches the production advisor masks (`PRE_MEAL_STEPS=24`,
`POST_MEAL_STEPS=48` at 5-min cadence).

The behavior is **opt-in by patient_id**.  When `patient_id=None` the
mask is byte-identical to the legacy logged-only mask, so cohort
re-runs without inferred-meal cache produce no change.

## Diagnostic — Live Cohort (5 patients)

`tools/diagnostic_inferred_meal_mask.py` runs the EXP-2740 mask under
both strategies on cohort patients with an inferred-meal cache:

| pid | inferred meals | n_fasting (logged) | n_fasting (inferred-aware) | % excluded |
|-----|---------------:|-------------------:|---------------------------:|-----------:|
| a   |            353 |             22 592 |                     16 847 |    **25.4 %** |
| c   |             17 |              4 643 |                      4 580 |       1.4 % |
| d   |            246 |             11 759 |                      8 340 |    **29.1 %** |
| e   |              4 |              2 131 |                      2 120 |       0.5 % |

**Median: 13.4 %** of previously-classified fasting rows were actually
within the post-meal window of an unlogged meal.  Patients with
high-frequency unlogged meals (a, d) lose a quarter of their "fasting"
data; patients who log diligently (c, e) lose almost nothing.

## Implication

Any historical EGP estimate that used `identify_fasting_mask(pdf)` for
under-loggers includes meal-elevated EGP in its sample.  The expected
direction of bias is **EGP overestimated** (post-meal residual ROC is
positive after PK insulin processing).  Patches preserve all callers'
behavior unless they thread `patient_id`; downstream analyses should
opt-in deliberately and re-verify their EGP curves.

## Files Changed

- `tools/cgmencode/exp_egp_personalization_2739.py` — `identify_fasting_mask` now `(pdf, patient_id=None, *, use_inferred_meals=True)`.
- `tools/cgmencode/exp_basal_egp_equilibrium_2740.py` — same signature.
- `tools/cgmencode/exp_basal_circadian_2724.py` — `extract_steady_periods(patient_df, patient_id=None)` precomputes the overlay and short-circuits per-row.
- `tools/cgmencode/production/fasting_helpers.py` — shared `apply_inferred_meal_exclusion()` helper.
- `tools/diagnostic_inferred_meal_mask.py` — diagnostic script.

