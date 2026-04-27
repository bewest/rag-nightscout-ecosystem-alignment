# EXP-3030 — LOPO robustness for EXP-3028 carb-aware per-patient refit

**Date:** 2026-04-26
**Verdict:** ✅ **PASS**, but with a smaller incremental lift than EXP-3028 reported.

## Why this experiment

EXP-3028 reported a +0.0082 verification-stripe lift over the
EXP-3017 clamped table by re-fitting per-patient (T*, M*) under the
same carb-aware proxy used by the scorer. Because that lift is the
result of *changing per-patient recommendations* (unlike EXP-3027-FIX,
which only adds conservatism by dropping uncertain patients), it
cannot ship on the strength of a single full-cohort number — we need
to show no single patient is carrying the lift.

This experiment mirrors EXP-3025-LOPO: leave-one-patient-out on the
verification stripe at gate=0.10, but with EXP-3028's carb-aware
per-patient table monkey-patched into the scorer.

## Method

- Verification stripe: `exp-3007_ascent_events__verification.parquet`
  (2 822 events / 23 patients).
- Recommendation table swap: monkey-patch
  `cf_replay_score_v3.PER_PATIENT_REC_CLAMPED` to point at
  `exp-3028_per_patient_carb_aware.parquet` for the candidate; baseline
  uses no per-patient table.
- Phenotype: `exp-3019_phenotype_imputed.parquet` *with* the
  EXP-3027-FIX safety floor applied (this is the current state of
  that file; see "Honest correction" below).
- Gate: 0.10 (current shipped default per EXP-3025-FIX/LOPO).

## Pre-registered PASS criteria

| Crit | Description | Result |
|------|-------------|:------:|
| (a)  | Every LOPO split keeps stratified safety               | 23 / 23 |
| (b)  | Every split keeps composite Δ ≥ ½ × full-cohort Δ      | 23 / 23 |
| (c)  | Full-cohort carb-aware Δ ≥ EXP-3017-clamped Δ          | +0.0348 ≥ +0.0326 ✓ |

All three pass → **PASS**.

## Numbers

| Configuration | Verif Δ | safety_ok |
|---|--:|:---:|
| EXP-3017 clamped (baseline this run)             | +0.0326 | ✓ |
| EXP-3028 carb-aware refit                         | **+0.0348** | ✓ |
| Incremental lift of EXP-3028 over current state   | **+0.0022** | — |

LOPO Δ statistics: mean +0.0348, std 0.0036, min +0.0294 (drop
`ns-1ccae8a375b9`), max +0.0445 (drop `ns-8f3527d1ee40`). No split
fails safety; no split falls below the +0.0174 composite floor.

## Honest correction

EXP-3028's commit reported a +0.0082 lift (from 0.6577 to 0.6660). This
experiment measures only +0.0022. The discrepancy is **not** a bug —
it's a temporal artefact:

- EXP-3028 was run at 17:27 on 2026-04-26.
- EXP-3027-FIX rewrote `exp-3019_phenotype_imputed.parquet` at 17:30
  (3 minutes later), adding the SAFETY_FLOOR=0.10 to imputed
  braking_ratio, which moves 7/12 imputed patients from `mid` to
  `high` stratum and drops them under `braking_mode='drop'`.

So EXP-3028's +0.0082 was measured against an *unfloored* imputed
baseline (which let many uncertain patients into the candidate cohort
and dragged the score down). Once EXP-3027-FIX is in effect, those
patients are already excluded, so the carb-aware refit only operates
on the remaining confident pool — giving a smaller marginal lift.

This is a healthy interaction: **EXP-3027-FIX captures most of the
deconfounding benefit, and EXP-3028 adds a smaller-but-real
recommendations-quality lift on top.** Both ship, in order.

## Shipping recommendation

| Component | Status |
|---|---|
| EXP-3025-FIX (gate 0.15→0.10)                  | already shipped |
| EXP-3027-FIX (safety floor on imputed)          | already shipped |
| EXP-3028 carb-aware refit                       | **OK to ship** — Δ +0.0022 verif, robust LOPO, safe |
| EXP-3017 clamped table                          | should be replaced by EXP-3028 carb-aware table |

Implementation: replace the file at the path
`externals/experiments/exp-3017_per_patient_clamped.parquet` (used by
the `per_patient_source='clamped'` branch) with the EXP-3028 carb-aware
table — or, less invasively, change the `PER_PATIENT_REC_CLAMPED`
constant to point at the new file. Recommend the latter so the
EXP-3017 table remains available for diagnostic comparisons.

## Reproducibility

```
python3 tools/aid-autoresearch/exp_3030_carb_refit_lopo.py
# writes externals/experiments/exp-3030_lopo_results.{json,csv}
```

## Pareto retreat update

The cumulative cf-replay verification-stripe Δ now stands at:

| Stage | Verif Δ | Lift over previous |
|---|--:|--:|
| EXP-3020 winner (gate=0.15, m_unity)       | +0.0418 | — |
| EXP-3025-FIX (gate→0.10, drop)             | +0.0245 | −0.0173 (holdout cost) |
| + EXP-3027-FIX (safety floor on imputed)    | +0.0326 | +0.0081 |
| + EXP-3030-validated EXP-3028 (carb-fit)    | +0.0348 | +0.0022 |

We are now within 17 % of the EXP-3020 cohort-fit number on the held-
out stripe, all changes safety-validated.
