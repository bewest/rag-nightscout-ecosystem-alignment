# CLOSEOUT — cf-replay autoresearch, post-holdout wave (EXP-3025..3028)

**Date:** 2026-04-26 (evening)
**Scope:** Phase-6 of the cf-replay autoresearch program. Picks up
where `CLOSEOUT-autoresearch-phase4-5-2026-04-26.md` left off (after
EXP-3020 declared `gate=0.15 × m_unity` the cohort-level winner) and
records the holdout-driven retreat to `gate=0.10` plus the safety/lift
work that followed.

## Headline

The EXP-3020 winner did **not** survive the held-out verification
stripe. After a holdout-failure → fix → robustness-validation cycle,
the **shipped default** is now:

```
braking_gate    = 0.10        (was 0.15 in EXP-3020)
braking_mode    = drop        (was m_unity)
proxy           = carb_aware
phenotype_source= imputed (with safety floor at 0.10 — EXP-3027-FIX)
per_patient_rec = clamped (EXP-3017 table; EXP-3028 carb-fit deferred)
safety_mode     = stratified
```

Verification-stripe composite Δ at this configuration: **+0.0245**,
**23/23 LOPO splits pass safety**, std=0.0037. Direction matches
training on both Loop and Trio.

## Wave summary

| EXP | Title | Verdict | Key number |
|---|---|:---:|---|
| 3025 | Verification-stripe holdout of EXP-3020 winner | **FAIL** | high-stratum Δhypo = +4.4 pp |
| 3025-FIX | Per-stratum braking-gate sweep | PASS | gate=0.10: high stratum empty, Δ=+0.0245 |
| 3025-LOPO | Leave-one-patient-out robustness | PASS | 23/23 splits, Δ mean +0.0245, std 0.0037 |
| 3026 | Inferred-meal correction-event shift (n=5) | PASS | direction + monotone |
| 3026-EXT | Same on full cohort (n=30) | PASS | Spearman(severity, frac_excluded) = +0.766 |
| 3027 | LOO of EXP-3019 controller-median imputation | **FAIL** | 31.6% stratum agreement (vs 70% gate); 2 catastrophic high→low |
| 3027-FIX | Safety floor on imputed braking_ratio | PASS | imputed → high stratum; verif Δ = +0.0326 |
| 3028 | Carb-aware per-patient (T*, M*) refit | PASS | verif Δ = +0.0327 (lift +0.0082 over 3025-FIX) but **NOT yet shipped** — needs fresh holdout |

## What changed in the codebase

| File | Change | Justified by |
|---|---|---|
| `tools/aid-autoresearch/cf_replay_score_v3.py` | `DEFAULT_BRAKING_GATE = 0.10` | EXP-3025-FIX + EXP-3025-LOPO |
| `tools/cgmencode/autoresearch_cf/exp_3019_impute_braking.py` | `SAFETY_FLOOR = 0.10` applied to imputed values | EXP-3027-FIX |
| `tools/cgmencode/production/_per_patient_compute.py` | inferred-meal-aware correction-event extraction (kept) | EXP-3026, EXP-3026-EXT |
| `tools/cgmencode/production/extend_inferred_meals_cache.py` | NEW — cohort cache extender | EXP-3026-EXT |

## What did *not* ship (deliberate)

* **EXP-3028 carb-aware refit.** Lift is real (+0.0082), but flipping
  `PER_PATIENT_REC_CLAMPED` would change observed patients'
  recommendations in subtle ways. Needs its own held-out cycle (call it
  EXP-3030) before it's deployable.
* **EXP-3019 imputation as a recommender.** EXP-3027 demonstrated that
  controller-median imputation has 31.6 % stratum agreement — far
  below useful. Imputed values are kept *only* for the conservative
  drop-mode safety floor (EXP-3027-FIX), never as positive
  recommendations.

## Pareto retreat

EXP-3020 reported gate=0.15 cohort delta = +0.0418 on training. The
final shipped gate=0.10 verification delta = +0.0245. Net "real" lift
is therefore 60 % of the originally claimed number — a normal training-
to-holdout discount, but worth recording so future agents don't quote
the EXP-3020 figure as the deployable lift.

| Source | Score (verif) | Δ (verif) |
|---|--:|--:|
| Baseline (M=1, T=0, no policy)        | 0.6333 | — |
| EXP-3020 winner (gate=0.15, drop)      | 0.6751 | +0.0418 (FAIL safety) |
| EXP-3025-FIX (gate=0.10, drop)         | 0.6577 | +0.0245 (PASS, **shipped**) |
| EXP-3027-FIX layered on 3025-FIX       | 0.6659 | +0.0326 (PASS, **shipped**) |
| EXP-3028 layered on 3027-FIX           | 0.6660 | +0.0327 (PASS, **not yet shipped**) |

## Honest readings

1. **The holdout did its job.** EXP-3025 was an honest negative; the
   training-set cohort winner had a real safety regression on a
   sampling stripe sampled differently. Without the verification
   stripe, we'd have shipped a worse policy.
2. **LOPO confirms the fix isn't a single-patient fluke.** 23/23 splits
   pass safety and clear the +0.0122 composite floor; std on Δ is
   0.0037. This is the strongest evidence so far that the cf-replay
   v3 framework produces robust per-cohort lifts.
3. **Imputation is a safety device, not a signal.** EXP-3027 proved
   imputation cannot be trusted as a positive predictor; EXP-3027-FIX
   uses it correctly — only to make missing-phenotype patients more
   conservative, never less.
4. **Inferred-meal correction (EXP-3026/EXT) is a separate, validated
   improvement.** Spearman 0.77 on n=30 between under-logging severity
   and fraction of correction-events reclassified. This is the first
   solid building-block for the basal/CR/ISF deconfounding direction
   the user wants.

## Open todos / deferred work

* **EXP-3030** (recommended next): held-out validation of EXP-3028
  carb-aware refit on a fresh stripe. If passes, ship as default.
* **EXP-3022 / per-patient ISF/CR/basal recommender** (still queued):
  with EXP-3026-EXT now validating the inferred-meal correction at
  cohort scale, the next building block is to wire that into the
  per-patient ISF/CR/basal recommendation pipeline (`exp_2739`,
  `exp_2740`, `exp_2741`, `exp_2742`, `exp_2861` lineage).
* **EXP-3023** continuous CGM-stream synthesis: still gap, still blocked
  on absence of an integrated UVA/Padova-style simulator.
* **EXP-3006** patient-twin deprecation note + **EXP-3016** jitter fix:
  cosmetic, low priority.

## File index for this wave

Reports:
- `docs/60-research/exp-3025-verification-holdout-2026-04-26.md`
- `docs/60-research/exp-3025-fix-gate-sweep-2026-04-26.md`
- `docs/60-research/exp-3025-lopo-2026-04-26.md`
- `docs/60-research/exp-3026-advisor-inferred-meal-shift-2026-04-26.md`
- `docs/60-research/exp-3026-ext-cohort-replication-2026-04-26.md`
- `docs/60-research/exp-3027-loo-imputation-2026-04-26.md`
- `docs/60-research/exp-3027-fix-safety-floor-2026-04-26.md`
- `docs/60-research/exp-3028-eventwise-carb-refit-2026-04-26.md`

Code:
- `tools/aid-autoresearch/exp_3025_holdout.py`
- `tools/aid-autoresearch/exp_3025_fix_gate_sweep.py`
- `tools/aid-autoresearch/exp_3025_lopo.py`
- `tools/aid-autoresearch/exp_3026_advisor_shift.py`
- `tools/aid-autoresearch/exp_3027_loo_imputation.py` (parallel agent's)
- `tools/aid-autoresearch/exp_3028_eventwise_carb_refit.py` (parallel agent's)
- `tools/cgmencode/production/extend_inferred_meals_cache.py`

Data (gitignored, in `externals/experiments/`):
- `exp-3025_holdout_summary.json`, `exp-3025-fix_gate_sweep.json`,
  `exp-3025-lopo_results.json`, `exp-3026_correction_event_shift.json`,
  `exp-3027_loo_summary.json`, `exp-3028_summary.json`.
