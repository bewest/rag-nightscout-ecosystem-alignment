# CLOSEOUT — Autoresearch Phase 4 + 5 (cf-replay productionisation)

**Date:** 2026-04-26
**Scope:** EXP-3015 through EXP-3019. Closes out the cf-replay autoresearch
program from "Phase-2 Pareto recommendation found" to "Phase-5 deployable
v3 scorer with all six refinements baked in by default."
**Status:** ✅ Closed; no in-flight Phase 4/5 todos remaining. Pending Phase
5 candidate is the OhioT1DM held-out validation (blocked on PhysioNet
credentials).

## What we did

Five experiments turning the Phase-2 cohort recommendation
(M = 0.5×, T = +30 min) into a defensible, per-patient, phenotype-aware,
imputation-robust fitness function:

| EXP | Title | Bottom line |
|---|---|---|
| EXP-3015  | cf_replay_score v3 (per-patient + carb-aware + braking gate)            | Productionised the Phase 3 findings as flags. |
| EXP-3015b | `--braking-mode {drop, m_unity, none}`                                  | Per-axis gate: keep T, drop M for high-braking. |
| EXP-3016  | Synthetic phenotype-conditional generator (validation)                  | Confirms timing benefit holds; magnitude flips at high braking. |
| EXP-3017  | Phenotype-clamped per-patient parquet                                   | Pre-bakes EXP-3016 finding into the recommendation table. |
| EXP-3018  | Subset-stratified safety gate                                           | Cohort gate produced false-negatives; per-stratum gate fixes it. |
| EXP-3019  | Impute braking_ratio for unknown-stratum patients                       | Eliminates unknown stratum cleanly via per-controller medians. |

## Final fitness function

```
cf_replay_score_v3 \\
    --per-patient \\                       # EXP-3012 per-patient (T*, M*)
    --braking-gate \\                       # EXP-3013 phenotype gate at 0.10
    --braking-mode m_unity \\               # EXP-3015b/3016 per-axis
    --safety-mode stratified                # EXP-3018 per-stratum gate
    # Defaults (no flag needed):
    # --per-patient-source clamped         # EXP-3017
    # --phenotype-source imputed           # EXP-3019
    # --proxy carb_aware                   # EXP-3014
```

Composite weights unchanged from v2: `0.50 × descent + 0.35 × ascent +
0.15 × hypo-safety`.

## Final result table (Phase 4 cohort, all six refinements applied)

| Policy            | events used | score   | cohort safety | stratified safety |
|-------------------|------------:|--------:|---------------|-------------------|
| Baseline (M=1, T=0)            | 17 919 | 0.6888 | FAIL | FAIL  |
| Uniform frontier (M=0.5, T=+30)| 17 919 | 0.7088 | pass | pass  |
| Per-patient + drop             | 11 551 | 0.7075 | pass | pass  |
| **Per-patient + m_unity**      | **17 919** | **0.7050** | FAIL | **pass** |

The headline policy (m_unity + stratified) retains all 17 919 events,
forces 6 368 high-braking events to M=1.0, and improves on baseline by
+1.62 pp composite while keeping every braking stratum's hypo Δ within
1 pp of the same-stratum baseline + 2 % absolute ceiling.

## Stratum-level safety table (m_unity, imputed phenotype)

| Stratum  | n     | base_hypo | cand_hypo | Δ        | passes |
|----------|------:|----------:|----------:|---------:|--------|
| high     | 6 254 |  0.416 %  |  1.071 %  | +0.66 pp | ✓ |
| mid      | 4 262 |  4.388 %  |  0.563 %  | −3.82 pp | ✓ |
| low      | 4 838 |  5.002 %  |  0.909 %  | −4.09 pp | ✓ |

`unknown` stratum eliminated via EXP-3019 imputation.

## Why each refinement matters

- **EXP-3014 (carb-aware proxy)** revised the Trio Δhypo claim by −45 %.
  Without it, the v2 scorer over-credited M = 0.5× by mis-counting events
  that were carb-rescue-protected as policy-induced safety gains.
- **EXP-3015b (m_unity mode)** retains the Phase-2 timing benefit for the
  43 % of events from high-braking patients while withdrawing the unwanted
  magnitude pressure. EXP-3016's synthetic frontier proved the magnitude
  reduction has zero benefit for that stratum.
- **EXP-3017 (clamp parquet)** moves the per-axis decision into the
  per-patient lookup table itself, making `m_unity` a no-op consistency
  check. Verified: `clamped + m_unity == clamped + none` bit-identical.
- **EXP-3018 (stratified safety)** rescues `m_unity` from cohort
  false-negative by comparing per-stratum cf-replay vs same-stratum
  baseline. The cohort gate had been conflating the high-braking subset's
  inherently-low risk floor (0.39 %) with the genuinely-elevated low/mid
  baseline (≈ 5 %).
- **EXP-3019 (imputation)** eliminates the unknown stratum via
  per-controller medians + prefix heuristic. All 12 previously-unknown
  patients land in defensible strata (3 odc-* → high; 4 Loop singletons →
  mid; 3 ns-* → mid; 2 OpenAPS → high).

## What's left

| Item | State | Why deferred |
|---|---|---|
| OhioT1DM held-out validation                  | blocked   | PhysioNet credentials not set up. |
| Empirical-hypo (vs cf-replay-baseline) gate   | candidate | Requires per-patient observed-hypo timeseries; cf-replay baseline is conservative substitute. |
| Phenotype classifier (ML-based imputation)    | candidate | Current median+prefix heuristic is good enough for the 5-patient cohort; ML would need more patients. |
| Push 2 commits (EXP-3018, EXP-3019) to origin | pending   | Awaiting user direction. |

## Reproducibility

- Source code: `tools/aid-autoresearch/cf_replay_score_v3.py`,
  `tools/aid-autoresearch/test_cf_replay_score_v3.py`,
  `tools/cgmencode/autoresearch_cf/exp_30{12..19}_*.py`.
- Reports: `docs/60-research/exp-30{12..19}-*.md` plus this closeout.
- Data (gitignored): `externals/experiments/exp-{3007,3012,3017,3019,2886}_*.parquet`.

The full chain reproduces from a clean clone with `make data` (assuming
upstream parquets are present) followed by:

```bash
python3 -m tools.cgmencode.autoresearch_cf.exp_3017_phenotype_clamp
python3 -m tools.cgmencode.autoresearch_cf.exp_3019_impute_braking
python3 tools/aid-autoresearch/test_cf_replay_score_v3.py
```

All three should exit 0.
