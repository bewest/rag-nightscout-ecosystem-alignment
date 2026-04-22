# EXP-2862 — Bootstrap confidence on per-patient recovery fraction

**Date**: 2026-04-22
**Driver**: `tools/cgmencode/exp_bootstrap_recovery_2862.py`
**Inputs**: `externals/experiments/exp-2812_pre_post_transitions.parquet`
**Outputs**: `externals/experiments/exp-2862_bootstrap_recovery.parquet`,
`exp-2862_summary.json`, `docs/60-research/figures/exp-2862_bootstrap_recovery.png`

## Hypothesis

Continue generalizing the EXP-2859 bootstrap-confidence pattern. Apply
to the third audition signal: median `recovery_fraction_3w` from
EXP-2812 state-transition windows. Single-point median over ~16
transitions per patient is noisy near the 0.4 audition threshold;
bootstrap gives explicit confidence.

## Method

Per-patient event bootstrap (N=500) of `recovery_fraction_3w` for the
16 patients with ≥5 transitions. Quantify `P(median<0.4)` and
`P(median>0.7)`.

## Results

| Band              | Naive (point) | Bootstrap (P≥0.9) | Δ |
|-------------------|---------------|-------------------|----|
| confident low     | 12            | 10                | −2 |
| confident neutral | 4             | 1                 | −3 |
| confident high    | 0             | 0                 |  0 |
| uncertain         | —             | 5                 | +5 |

**Bootstrap demotes 5 of 16 patients (31%) into "uncertain"**: 2 from
naive-low, 3 from naive-neutral. Median bootstrap CI width is **0.25**
— large relative to the 0.4 threshold.

**Patient `b`**: P(low recovery) = **1.00** — the strongest possible
bootstrap-confident classification. Of `b`'s three canonical "triple
flag" inputs:

- Simpson: P=boundary (EXP-2859) — demoted
- ISF gap under-correction: P=0.63 (EXP-2861) — demoted
- Recovery fraction low: P=1.00 (EXP-2862) — confirmed at maximum

So patient `b` is now formally a **single-flag high-confidence triage
candidate** (low-recovery only), not a triple-flag. This is a
material refinement to the audition triage list and removes signal
inflation from the canonical example.

## Productionization

- `AuditionInputs.p_low_recovery: Optional[float]`
- `classify_triage_flags`: bootstrap branch precedes naive
  `median_recovery_fraction < 0.4` branch:

| Bootstrap state            | Severity | Behavior |
|----------------------------|----------|----------|
| flat + P(low) ≥ 0.9        | high     | emit `flat_low_recovery` |
| flat + 0.1 ≤ P(low) < 0.9  | low      | boundary (provisional) |
| flat + P(low) < 0.1        | suppress | naive branch ignored |
| non-flat phenotype         | n/a      | flag does not fire |

- `RecoveryFactsLoader` (new): bridges EXP-2862 parquet to AuditionInputs.
- 4 new audition tests + 4 loader tests; 36/36 audition+loader tests pass.

## Pattern status

Three audition signals now refined by event bootstrap (Simpson, ISF
gap, recovery). Remaining candidates: `wear_isf_drop_pct`,
`post_high_mg_dl`. The pattern is:

1. Find per-patient event-level data feeding the signal.
2. Event bootstrap → P(crossing each audition threshold).
3. Three-tier severity (high / boundary-low / suppress).
4. Loader bridges parquet to AuditionInputs.
5. Bootstrap branch precedes naive point-estimate branch.

## Charter compliance

Stream B (settings audition); per-patient explicit confidence bands
improve G3 (uncertainty propagation).
