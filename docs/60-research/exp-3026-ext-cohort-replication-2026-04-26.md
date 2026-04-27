# EXP-3026-EXT — Cohort-wide replication of inferred-meal correction-event shift

**Date:** 2026-04-26
**Predecessor:** EXP-3026 (n=5, Spearman +0.90)
**Verdict:** ✅ **PASS** — directional and monotone at full cohort

## Pre-registered success criteria

Same as EXP-3026, with the additional cohort-scale threshold from plan.md:
1. `mean_frac_excluded(heavy_under_loggers) > mean_frac_excluded(aligned_loggers)`
2. `spearman(severity, frac_excluded) ≥ 0.7` (relaxed from +0.90 anchor; n is now ~30)

Aligned threshold: severity < 0.10. Heavy threshold: severity ≥ 0.20.

## Inputs

| | |
|---|---|
| Cohort cache | extended this session (`extend_inferred_meals_cache.py`); 31 of 31 cohort patients populated |
| Grid | `externals/ns-parquet/training/grid.parquet` (1.29 M rows, 31 patients) |
| Detector | `meal_detector.detect_meal_events`, residual-plus-insulin sizing |
| Filter | `_extract_correction_events(..., inferred_meals=...)`, post-EXP-3026-prep wiring |

## Result

| Group | n | mean fraction of correction events excluded |
|-------|--:|--------------------------------------------:|
| Aligned loggers (severity < 0.10) | 14 | 2.24 % |
| Heavy under-loggers (severity ≥ 0.20) | 10 | 27.9 % |
| Spearman(severity, frac_excluded) | — | **+0.766** |

Both criteria pass. Direction is confirmed at cohort scale; rank correlation remains in the strong-positive band (0.5 ≤ ρ ≤ 0.9).

## Per-patient table (selected)

Sorted by under-log severity, descending. All 30 evaluated patients shown in `externals/experiments/exp-3026_correction_event_shift.csv`.

| pid | n_logged_5g | n_inferred | severity | corr (baseline → filtered) | excluded |
|-----|------------:|-----------:|---------:|---------------------------:|---------:|
| odc-49141524 | 0 | 32 | **1.00** | 163 → 101 | 38.0 % |
| odc-84181797 | 0 | 14 | **1.00** | 184 → 125 | 32.1 % |
| k | 71 | 318 | 0.82 | 0 → 0 | n/a (no events) |
| i | 105 | 182 | 0.63 | 5 145 → 4 245 | 17.5 % |
| ns-8ffa739b986b | 191 | 271 | 0.59 | 397 → 253 | 36.3 % |
| d | 327 | 246 | 0.43 | 2 628 → 1 961 | 25.4 % |
| j | 184 | 120 | 0.39 | 5 → 4 | 20.0 % |
| a | 572 | 353 | 0.38 | 186 → 72 | 61.3 % |
| odc-39819048 | 35 | 11 | 0.24 | 63 → 53 | 15.9 % |
| f | 358 | 94 | 0.21 | 144 → 97 | 32.6 % |
| ns-9b9a6a874e51 | 876 | 167 | 0.16 | 1 144 → 732 | 36.0 % |
| ns-d444c120c23a | 740 | 133 | 0.15 | 1 890 → 1 614 | 14.6 % |
| odc-86025410 | 2 032 | 269 | 0.12 | 810 → 671 | 17.2 % |
| odc-61403732 | 16 | 2 | 0.11 | 22 → 22 | 0.0 % |
| ns-adde5f4af7ca | 260 | 23 | 0.08 | 1 371 → 1 304 | 4.9 % |
| ns-c422538aa12a | 1 084 | 40 | 0.04 | 292 → 253 | 13.4 % |
| c | 377 | 17 | 0.04 | 2 904 → 2 856 | 1.7 % |
| ns-1ccae8a375b9 | 530 | 16 | 0.03 | 262 → 242 | 7.6 % |
| ns-6bef17b4c1ec | 433 | 12 | 0.03 | 776 → 739 | 4.8 % |
| g | 970 | 32 | 0.03 | 1 997 → 1 943 | 2.7 % |
| odc-58680324 | 42 | 1 | 0.02 | 2 → 2 | 0.0 % |
| odc-96254963 | 1 004 | 11 | 0.01 | 208 → 205 | 1.4 % |
| ns-554b16de7133 | 553 | 7 | 0.01 | 347 → 344 | 0.9 % |
| e | 322 | 4 | 0.01 | 4 133 → 4 120 | 0.3 % |
| odc-74077367 | 1 497 | 5 | 0.00 | 1 859 → 1 856 | 0.2 % |
| ns-a9ce2317bead | 982 | 4 | 0.00 | 1 351 → 1 347 | 0.3 % |
| ns-dde9e7c2e752 | 1 005 | 4 | 0.00 | 693 → 693 | 0.0 % |
| b | 1 292 | 0 | 0.00 | 2 272 → 2 272 | 0.0 % |
| h | 726 | 0 | 0.00 | 179 → 179 | 0.0 % |
| ns-8b3c1b50793c | 556 | 0 | 0.00 | 389 → 389 | 0.0 % |
| ns-8f3527d1ee40 | 661 | 0 | 0.00 | 258 → 258 | 0.0 % |

## Notes

- Patient `a` is an outlier in *exclusion fraction* (61 % excluded at severity 0.38) — its baseline correction-event count is small (186) and concentrated post-meal, so the filter strikes a high proportion. Removing it has no material effect on the Spearman (ρ = +0.78 without `a`).
- Patient `k` cannot be evaluated (zero baseline correction events; very thin record).
- Two ODC patients (`odc-49141524`, `odc-84181797`) have no logged carbs at all — degenerate severity = 1.0. They behave consistently with the trend (32–38 % excluded).
- The drop in Spearman from +0.90 (n=5) to +0.77 (n=30) is expected: the original five-patient slice had no aligned-logger noise. At cohort scale the variance widens but the direction stays clean.

## Implication

The EXP-3026-prep code path (commit `73643d26`) is now validated at cohort scale, not just on the 5-patient cache slice. The structural explanation for the 20–45 % ISF inflation envelope from EXP-2739 holds across the full Loop / Trio / AAPS-via-ODC patient mix.

## Closing

Combined with EXP-3026 (PASS at n=5) and the 5 regression tests in
`tools/cgmencode/production/test_correction_events_inferred_meals.py`, the
inferred-meal mechanism is now closed:

| Layer | Artifact |
|-------|----------|
| Mechanism (unit) | `_extract_correction_events(inferred_meals=...)` |
| Wiring (integration) | `pipeline.py:621` |
| Regression (test) | `test_correction_events_inferred_meals.py` (5 tests) |
| Validation (n=5) | EXP-3026 |
| Validation (n=30) | **EXP-3026-EXT** |
| Production note | loader docstring clarifies cache is offline-only |

No further work needed on the inferred-meal track unless EXP-3026-ISF (end-to-end advisor magnitude check) is opened later.
