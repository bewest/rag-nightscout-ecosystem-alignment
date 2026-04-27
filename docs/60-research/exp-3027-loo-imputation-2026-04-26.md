# EXP-3027 — LOO validation of EXP-3019 braking-ratio imputation

**Date:** 2026-04-26
**Predecessor:** EXP-3019 (controller-median imputation rule)
**Verdict:** ❌ **FAIL** — diagnostic finding; imputation rule is not safety-conservative

## Hypothesis

EXP-3019's controller-median fallback imputes `braking_ratio` for unknown-controller patients. The imputed values feed `cf_replay_score_v3`'s stratified safety gate. EXP-3027 asks: *if I held out an observed patient and predicted their braking_ratio via the same rule, would I get the right stratum?*

## Method

For each of 19 patients with both observed `braking_ratio` and known controller, drop them, recompute the controller medians, predict their braking_ratio via EXP-3019's rule, compare.

| Gate | Threshold | Result | Status |
|---|---|---|:---:|
| Median |error| | ≤ 0.05 | 0.041 | ✅ PASS |
| Stratum agreement | ≥ 70 % | 31.6 % | ❌ FAIL |
| Catastrophic low→high | ≤ 1 | 0 | ✅ PASS |

**Verdict: FAIL on stratum agreement.**

## Findings

### 1. Within-controller braking heterogeneity dwarfs the imputation signal

Observed `braking_ratio` distributions per controller:

| Controller | Obs n | Min | Median | Max |
|---|---:|---:|---:|---:|
| Loop | 6 | 0.025 | 0.051 | 0.310 |
| Trio | 9 | 0.020 | 0.052 | 0.146 |
| AAPS | 3 | 0.222 | 0.421 | 0.962 |

For Loop and Trio, the median (~0.05) sits right at the low/mid boundary (`STRAT_BRAKING_EDGES = (0.05, 0.10)`). Imputation predictions cluster in the 0.045–0.067 band → land on either side of the boundary depending on tiny LOO shifts.

### 2. Two **catastrophic high→low** mis-predictions (under-protective)

| Patient | Controller | Observed | Predicted | Stratum flip |
|---|---|---:|---:|---|
| ns-8f3527d1ee40 | Trio | 0.146 (high) | 0.045 (low) | high → low |
| ns-6bef17b4c1ec | Trio | 0.113 (high) | 0.045 (low) | high → low |

These patients' events would **not** be dropped at gate=0.10 if their braking_ratio were imputed. In practice both have observed values so they are not affected, but if a future Trio patient with high braking arrives and needs imputation, the rule will under-protect them.

### 3. AAPS heterogeneity makes its imputation unreliable

The 3 observed AAPS patients span 0.22–0.96 (4× spread). LOO median bounces between 0.32, 0.59, 0.69 depending on which one is held out — meaning the imputed value for any unknown AAPS patient is essentially noise.

### 4. The MAE gate passes only because the median is robust

Median |error| = 0.041 hides a long right tail (mean = 0.117). The two AAPS predictions miss by 0.47 and 0.64. AAPS imputation is essentially uninformative.

## Operational implications

This is a diagnostic FAIL — the imputation rule **works** for the production hot path (the verification stripe is dominated by observed-value patients) but is fragile for new unknown-controller patients.

Concrete mitigations (priority order):

1. **Safety-conservative imputation** (recommended): when imputing, set `braking_ratio = max(controller_median, 0.10)`. This forces unknown patients into the "high" stratum by default, which under cf-replay-score-v3 means their events are *dropped* (with `braking_mode='drop'`). Trades composite Δ (slightly lower) for safety (no chance of unknown patient slipping into low/mid stratum and missing the safety gate).
2. **Tag-and-drop alternative**: add `imputed_uncertain=True` flag to phenotype rows where imputation crosses a stratum boundary; have the scorer treat them as `unknown` stratum (already excluded from per-stratum safety asserts).
3. **Don't use AAPS-controller imputation at all**: too few observations to derive a stable median (n=3, IQR > median).

## Why this experiment matters even though it failed

LOPO of EXP-3025 confirmed that the gate=0.10 ship-candidate is robust over the *current* cohort. EXP-3027 is the equivalent check for a prior step (imputation). It's saying: the cf-replay gate is safe today because every unknown-controller patient happens to be either truly low-braking or unaffected. That's a happy accident, not a property of the imputation rule.

Recommend follow-up `EXP-3027-FIX`: implement the safety-conservative imputation in EXP-3019, regenerate `exp-3019_phenotype_imputed.parquet`, and re-run cf_replay_score_v3 verification to confirm the gate=0.10 result is preserved (Δ should drop slightly because more events get dropped, but safety should strictly improve).

## Files

- `tools/aid-autoresearch/exp_3027_loo_imputation.py` (this experiment)
- `externals/experiments/exp-3027_loo_results.csv` (gitignored; per-patient detail)
- `externals/experiments/exp-3027_loo_summary.json` (gitignored; verdict)
