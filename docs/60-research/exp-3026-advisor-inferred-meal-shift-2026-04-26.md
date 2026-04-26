# EXP-3026 — inferred-meal correction-event shift, group comparison

**Date**: 2026-04-26
**Verdict**: **PASS** — directional, monotone, anchored to under-logging severity.
**Inputs**: 5 cohort patients (a, b, c, d, e) with cached inferred-meal frames.

## Pre-registered hypothesis

Adopting inferred meals in `pipeline._extract_correction_events` produces a *directional* shift consistent with under-logging severity. Aligned loggers should see near-null change; under-loggers should see substantial event reclassification — anchored to the EXP-2739 memory of 20–45 % ISF inflation on heavy under-loggers.

## Pre-registered success criteria

| Crit | Description |
|------|-------------|
| direction | mean fraction excluded(under-loggers) > mean fraction excluded(aligned loggers) |
| monotone | Spearman(severity, fraction_excluded) > 0 |

## Method

For each patient with a cached inferred-meal frame:

1. Materialize per-step glucose / bolus / carbs from `externals/ns-parquet/training/grid.parquet` (5-min cadence; bolus / carbs are already on-grid).
2. Compute correction events twice via `pipeline._extract_correction_events`:
   * baseline: `inferred_meals=None`
   * filtered: `inferred_meals=loader.lookup(pid).events`
3. Define `under_log_severity = n_inferred / (n_inferred + n_logged_carbs_5g)` — the share of meals that the production detector found but the patient never logged.
4. Compare aligned (`severity < 0.10`) vs under-logger (`severity ≥ 0.20`) groups.

The 0.20 threshold was set empirically — cohort severity range in the inferred-meal cache is 0.0 – 0.43, so 0.50 (the original anchor from the plan) was unreachable on the available cache.

## Per-patient results

| pid | n_logged_carbs (≥5 g) | n_inferred meals | under_log_severity | baseline corr_events | filtered corr_events | excluded | % excluded |
|-----|---:|---:|---:|---:|---:|---:|---:|
| a | 572 | 353 | 0.38 | 186 | 72 | 114 | **61.3 %** |
| b | 1 292 | 0 | 0.00 | 2 272 | 2 272 | 0 | 0.0 % |
| c | 377 | 17 | 0.04 | 2 904 | 2 856 | 48 | 1.7 % |
| d | 327 | 246 | 0.43 | 2 628 | 1 961 | 667 | **25.4 %** |
| e | 322 | 4 | 0.01 | 4 133 | 4 120 | 13 | 0.3 % |

## Group comparison

| Group | n | mean fraction excluded |
|-------|---:|---:|
| aligned (severity < 0.10) | 3 (b, c, e) | **0.66 %** |
| under-logger (severity ≥ 0.20) | 2 (a, d) | **43.3 %** |

* Direction: under-logger > aligned — **PASS**
* Monotonicity: Spearman(severity, fraction_excluded) = **+0.90** — **PASS**

## Anchoring to memory

EXP-2739 (under-logger ISF bias): heavy under-loggers had ISF estimates inflated by 20–45 % because post-meal boluses were mis-classified as fasting corrections. EXP-3026 measures the *upstream* mechanism: the share of correction events that were spurious. Patient `d` (25.4 %) and patient `a` (61.3 %) are exactly the two patients in the cache with non-trivial inferred-meal counts — and they are precisely the patients whose ISF advisor would have been biased downward by the absent filter.

## Limits / honest caveats

* Only 5 patients have a cached inferred-meal frame. The remaining 26 cohort patients would need `InferredMealsLoader.compute_for(pid, grid)` runs to extend coverage; cheap but not done in this commit.
* The "fraction excluded" metric is a structural lower bound on ISF impact: an excluded event is one whose ΔBG/dose contribution leaves the ISF estimator. Magnitude of the resulting ISF shift is not measured here — that would require an end-to-end advisor pipeline run, which is the natural follow-up.
* Patient `a` has only 186 baseline correction events (small denominator), so the 61.3 % rate is high-leverage. The conclusion does not hinge on `a` alone — patient `d` has 2 628 baseline events and still excludes 25.4 %.

## Follow-ups (proposed; not opened)

* **EXP-3026-EXT**: Extend inferred-meal cache to the remaining 26 cohort patients (`compute_for` over the training grid). Re-run EXP-3026 to confirm the Spearman holds at n ≥ 30.
* **EXP-3026-ISF**: End-to-end advisor pipeline comparison — run `_pipeline.generate_settings_advice` with and without the inferred-meal-filtered correction set; report ISF magnitude shift per patient and confirm it falls within the 20–45 % EXP-2739 envelope on heavy under-loggers.

## Reproducibility

```
python3 tools/aid-autoresearch/exp_3026_advisor_shift.py
# writes externals/experiments/exp-3026_correction_event_shift.{json,csv}
```
