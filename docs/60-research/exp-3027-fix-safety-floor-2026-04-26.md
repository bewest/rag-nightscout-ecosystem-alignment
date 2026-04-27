# EXP-3027-FIX — Safety-conservative braking imputation

**Date:** 2026-04-26
**Predecessor:** EXP-3027 (FAIL diagnostic on median imputation)
**Verdict:** ✅ **PASS** — strict safety win + verification Δ improvement

## Change

In `tools/cgmencode/autoresearch_cf/exp_3019_impute_braking.py`: imputed `braking_ratio` values are now floored at `SAFETY_FLOOR = 0.10` (the upper edge of `STRAT_BRAKING_EDGES`). Observed values are untouched. Imputed patients land in the `high` braking stratum and, under `braking_mode='drop'`, are excluded from the candidate policy by default.

## Effect on imputed cohort (n=12)

| Patient class | Before (raw) | After (FIX) | Stratum |
|---|---:|---:|:---:|
| Loop unknown (b, h, j, k) | 0.057 → mid | 0.100 → high | shift |
| Trio unknown (ns-554b…, ns-8ffa…, ns-c422…) | 0.052 → mid | 0.100 → high | shift |
| AAPS/OpenAPS unknown (5 patients) | 0.421 → high | 0.421 → high | no change (already above floor) |

7 of 12 imputed patients flipped mid→high; 5 were already high.

## Verification stripe (gate=0.10, drop, EXP-3017 clamped table)

| Configuration | Δ | events used | safety_ok |
|---|---:|---|:---:|
| Pre-FIX imputation (median only) | +0.0245 | 1 822 / 2 822 | ✅ |
| Post-FIX imputation (safety-floor) | **+0.0326** | 1 640 / 2 822 | ✅ |

The conservative floor drops 182 additional events (Loop+Trio unknown patients now treated as high-braking). Their events were dragging the candidate cohort metric down; removing them improves cand_overshoot/cand_hypo simultaneously, lifting Δ by +0.0081.

## Composition with EXP-3028

| Configuration | Verification Δ |
|---|---:|
| EXP-3017 clamped + median imputation (old default) | +0.0245 |
| EXP-3017 clamped + EXP-3027-FIX imputation | +0.0326 |
| EXP-3028 carb-aware fit + median imputation | +0.0327 |
| **EXP-3028 carb-aware fit + EXP-3027-FIX imputation** | **+0.0348** |
| Original gate=0.15 (pre EXP-3025-FIX) | +0.0418 |

Combined improvements reclaim 60 % of the +0.0173 composite Δ cost of moving the gate from 0.15 → 0.10. Both improvements provide stronger safety guarantees than the gate=0.15 configuration they partly replace.

## Why EXP-3027-FIX can ship while EXP-3028 cannot (yet)

EXP-3027-FIX is purely a safety hardening: imputed values move *into* the high stratum (more conservative). The change cannot make any *observed* patient more aggressively dosed; the only behavior change is that more *unknown* patients get their events dropped. Worst-case cost is composite Δ; there is no safety regression possible.

EXP-3028 is a different category: it changes per-patient (T*, M*) recommendations. Even though the verification stripe shows a lift, recommendations could move some observed patients more-aggressively (or less-aggressively in unforeseen ways). It deserves a fresh holdout before flipping `PER_PATIENT_REC_CLAMPED`.

## Code change

```python
# tools/cgmencode/autoresearch_cf/exp_3019_impute_braking.py
SAFETY_FLOOR = 0.10  # = STRAT_BRAKING_EDGES.upper

# In imputation loop:
br = max(br_raw, SAFETY_FLOOR)
if br > br_raw:
    src = src + f'+safety_floor({SAFETY_FLOOR})'
```

A new `braking_ratio_raw` column is also written to the parquet for diagnostic transparency (preserves the median-only value for analysis).

## Files

- `tools/cgmencode/autoresearch_cf/exp_3019_impute_braking.py` (modified)
- `externals/experiments/exp-3019_phenotype_imputed.parquet` (regenerated; gitignored)
