# Inferred-Meal Mask vs Logged-Carbs Mask in EGP/ISF Experiments (2026-04-24)

## Background

Three priority EGP/ISF experiments — **EXP-2724** (basal-circadian),
**EXP-2739** (EGP-personalization + ISF correction events), and
**EXP-2740** (basal-EGP-equilibrium) — historically defined "fasting"
rows and "correction events" using **logged carbs only**
(`carb_roll < 0.5 g` or `carbs_in_window < ISF_MAX_CARBS`).  This is
unsafe in the presence of under-loggers: any meal eaten without a
manual carb entry would silently contaminate either:

  1. the **fasting EGP estimate** (post-meal residual ROC counted as
     hepatic glucose production), **or**
  2. the **ISF correction event sample** (a post-meal hyperglycemic
     bolus mis-classified as a fasting correction; the meal-driven BG
     rise then shrinks the apparent ΔBG per unit insulin, depressing
     the ISF estimate).

## Patches

Each experiment now accepts an optional `patient_id` and applies an
**inferred-meal exclusion overlay** on top of the legacy logged-carb
test:

```python
# Fasting (EXP-2740/2739): mask &= ~within(±[2h, 4h], inferred_meals)
mask = identify_fasting_mask(pdf, patient_id=pid)

# ISF correction (EXP-2739): reject events where any inferred meal
# starts within [event_idx − 1h, event_idx + ISF_POST_WINDOW]
pop_events, pers_events = extract_correction_events(pdf, patient_egp, pid)

# Basal-circadian (EXP-2724): pre-compute exclusion mask, skip rows
periods = extract_steady_periods(patient_df, patient_id=pid)
```

The overlay is sourced from `InferredMealsLoader`
(`production/inferred_meals_facts_loader.py`), backed by the spectral
residual+insulin meal detector cached at
`externals/experiments/inferred_meals_<pid>.parquet`.

The behavior is **opt-in by patient_id**.  When `patient_id=None` the
experiment is byte-identical to the legacy logged-only behavior, so
cohort re-runs without inferred-meal cache produce no change.

## Diagnostic — Live Cohort (5 patients)

`tools/diagnostic_inferred_meal_mask.py` runs the patched masks and
extractors on cohort patients with an inferred-meal cache:

| pid | inferred meals | fasting rows excluded | ISF events excluded | **ISF median (logged → inferred)** |
|-----|---------------:|----------------------:|--------------------:|-----------------------------------:|
| a   |            353 |             **25.4 %** |           **82.4 %** | **29.3 → 42.5 mg/dL/U  (+45 %)** |
| d   |            246 |             **29.1 %** |             49.6 %  | 23.1 → 27.7 mg/dL/U  (+20 %)     |
| c   |             17 |              1.4 %    |              2.2 %  | 26.9 → 26.9 mg/dL/U  (≈ 0 %)     |
| e   |              4 |              0.5 %    |              1.0 %  | 15.8 → 15.9 mg/dL/U  (≈ 0 %)     |

**Median across cohort sample**:
- 13.4 % of "fasting" rows were actually post-meal contamination.
- 12.2 % of "correction" events were actually post-meal hyperglycemia.
- Median ISF correction: **+2.4 mg/dL/U**, with the heaviest
  under-loggers seeing **+13 mg/dL/U** corrections.

## Clinical Implication

ISF was **under-estimated** for under-loggers by ~20–45 %.  An
under-estimated ISF causes an AID controller (or human) to dose
**more** insulin per mg/dL of correction than the body actually
needs — directly increasing hypoglycemia risk during low-meal-logging
days.  Sites that import ISF from a fasting-correction analysis
should opt-in to inferred-meal masking before publishing a
recommended setting change.

Patients who log diligently (c, e) see negligible change, confirming
the overlay is well-targeted: it only moves estimates for patients
whose logged-carb stream is unreliable.

## Files Changed

- `tools/cgmencode/exp_egp_personalization_2739.py`
  - `identify_fasting_mask(pdf, patient_id=None, *, use_inferred_meals=True)`
  - `extract_correction_events(pdf, patient_egp, patient_id=None,
    *, use_inferred_meals=True)` — rejects events whose [−1h, +2h]
    window contains any inferred meal.
- `tools/cgmencode/exp_basal_egp_equilibrium_2740.py`
  - `identify_fasting_mask(pdf, patient_id=None, *, use_inferred_meals=True)`
- `tools/cgmencode/exp_basal_circadian_2724.py`
  - `extract_steady_periods(patient_df, patient_id=None)` precomputes
    the exclusion overlay and short-circuits per-row.
- `tools/cgmencode/production/fasting_helpers.py` — shared
  `apply_inferred_meal_exclusion()` helper.
- `tools/diagnostic_inferred_meal_mask.py` — diagnostic script.

