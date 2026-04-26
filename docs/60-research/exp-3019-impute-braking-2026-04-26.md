# EXP-3019 — Impute braking_ratio for unknown-stratum patients

**Date:** 2026-04-26
**Hypothesis:** EXP-3018's stratified safety gate fell back to a generic
`unknown` stratum for 939 events from 12 patients absent from the EXP-2886
phenotype parquet. Per-controller median imputation, with prefix heuristics
to recover missing controllers, should eliminate that stratum cleanly while
keeping all per-stratum gates passing.
**Verdict:** Confirmed. `unknown` stratum drops from 939 events → 0.
Stratified safety still passes for the deployable invocation.

## Method

`tools/cgmencode/autoresearch_cf/exp_3019_impute_braking.py`:

1. Compute per-controller median braking_ratio from observed (EXP-2886) data:
   - Loop: 0.057
   - Trio: 0.052
   - AAPS: 0.421
   - OpenAPS (treat as legacy AAPS per stored memory): 0.421
2. For each patient missing braking_ratio, resolve controller in order:
   phenotype.controller → ascent.controller (mode) → prefix heuristic
   (`odc-*` → AAPS, `ns-*` → Trio, single-letter alpha → Loop).
3. Assign braking_ratio = controller-median (cohort median fallback only if
   controller still unresolved). Mark with `imputed=True` and source.

Output: `externals/experiments/exp-3019_phenotype_imputed.parquet`.

`cf_replay_score_v3.py` gains `--phenotype-source {observed, imputed}`
(default `imputed`).

## Imputation footprint (24 → 31 patients)

| Source | n |
|---|---|
| Observed (EXP-2886)               | 19 |
| Imputed via known controller      |  3 |
| Imputed via prefix heuristic      |  9 |
| Imputed via cohort fallback       |  0 |

The 12 imputations:

| Patient | Controller | Source | β   |
|---|---|---|---|
| b              | Loop    | phenotype/ascent  | 0.057 |
| h, j, k        | Loop    | prefix heuristic  | 0.057 |
| ns-554b16de…   | Trio    | prefix heuristic  | 0.052 |
| ns-8ffa739…    | Trio    | prefix heuristic  | 0.052 |
| ns-c422538…    | Trio    | prefix heuristic  | 0.052 |
| odc-39819048   | AAPS    | prefix heuristic  | 0.421 |
| odc-49141524   | OpenAPS | phenotype/ascent  | 0.421 |
| odc-58680324   | OpenAPS | phenotype/ascent  | 0.421 |
| odc-61403732   | AAPS    | prefix heuristic  | 0.421 |
| odc-84181797   | AAPS    | prefix heuristic  | 0.421 |

## Stratified safety after imputation (m_unity policy)

| Stratum  | n (observed → imputed) | base_hypo  | cand_hypo  | Δ          | passes |
|----------|----------------------:|-----------:|-----------:|-----------:|--------|
| high     | 6 131 → 6 254         | 0.416 %    | 1.071 %    | +0.66 pp   | ✓ |
| mid      | 3 446 → 4 262         | 4.388 %    | 0.563 %    | −3.82 pp   | ✓ |
| low      | 4 838 → 4 838         | 5.002 %    | 0.909 %    | −4.09 pp   | ✓ |
| unknown  |   939 → 0             | —          | —          | —          | (gone) |

The imputed ODC patients (5 events totals) move from `unknown` (low risk by
coincidence) to `high` braking, expanding the high stratum by 123 events.
This raises the high stratum baseline hypo slightly (0.391 → 0.416 %) but
the +0.66 pp Δ still passes the 1 pp + 2 % ceiling gate. Imputed Loop/Trio
patients populate the `mid` stratum (Loop median = 0.057 sits in [0.05,
0.10)); their addition slightly *lowers* the mid baseline (5.31 → 4.39 %)
since the imputed-mid patients have lower observed event hypo.

## Score impact

| Mode         | Before EXP-3019 | After EXP-3019 |
|--------------|----------------:|---------------:|
| baseline     | 0.6888          | 0.6888         |
| uniform frontier | 0.7088      | 0.7088         |
| per+drop     | 0.7031          | 0.7075 (+0.0044) |
| per+m_unity  | 0.7051          | 0.7050 (~unchanged) |

The drop-mode score *improves* slightly because the imputed high-braking
ODC patients (123 events) are now correctly dropped from cohort
aggregation, removing their high overshoot baseline from the cohort score.
The m_unity score is unchanged within rounding.

## Deployable invocation (final)

```
cf_replay_score_v3 \\
    --per-patient \\
    --per-patient-source clamped \\      # EXP-3017
    --braking-gate \\                     # EXP-3013
    --braking-mode m_unity \\             # EXP-3015b/3016
    --safety-mode stratified \\           # EXP-3018
    --phenotype-source imputed            # EXP-3019 (default)
```

All defaults now align with the most-correct interpretation of the program.
A bare `cf_replay_score_v3 --per-patient --braking-gate` invocation will
pick up clamped + imputed automatically.

## Files

- New: `tools/cgmencode/autoresearch_cf/exp_3019_impute_braking.py`
- New: `externals/experiments/exp-3019_phenotype_imputed.parquet` (gitignored)
- Modified: `tools/aid-autoresearch/cf_replay_score_v3.py` (`--phenotype-source`,
  imputed default in stratification + braking gate).
- Source: this report.
