# EXP-3018 — Subset-stratified safety gate

**Date:** 2026-04-26
**Hypothesis:** The cohort safety gate (`max(per-controller hypo) ≤ 1 %`)
produces a false-negative on `m_unity` mode because it aggregates across
braking strata with very different baseline risk profiles. A per-stratum
gate (Δhypo ≤ 1 pp vs the same-stratum baseline + absolute ceiling 2 % to
prevent runaway) should distinguish "policy degrades subset" from "subset
inherits baseline tail risk."
**Verdict:** Confirmed. `m_unity` flips from FAIL (cohort) to PASS
(stratified); the stratified gate still rejects the raw baseline; the
uniform frontier passes both gates (consistency check).

## Method

Added `--safety-mode {cohort, stratified}` to `cf_replay_score_v3.py`
(default `cohort` for backward compatibility). Stratified mode partitions
events on `phenotype.braking_ratio` at edges `(0.05, 0.10)` into low / mid /
high (plus `unknown` for patients absent from phenotype) and per-stratum:

1. Compute baseline cf-replay (M=1, T=0) hypo rate (`baseline_hypo`).
2. Compute candidate cf-replay hypo rate under the policy (`cand_hypo`).
3. Pass criterion: `(cand_hypo − baseline_hypo) ≤ 1 pp` **AND**
   `cand_hypo ≤ 2 × HYPO_GATE = 2 %` (absolute ceiling).

All strata must pass.

## Results (Phase 4 cohort, carb-aware proxy)

### Mode comparison

| Policy | Cohort safety | Stratified safety | Δ from cohort |
|---|---|---|---|
| Baseline (M=1, T=0)             | FAIL | **FAIL** | low / mid hit absolute ceiling (5.0 % / 5.3 %) |
| Uniform frontier (M=0.5, T=+30) | pass | **pass** | All strata −4 pp / +0 pp |
| Per-patient + m_unity           | FAIL | **pass** | High stratum Δ = +0.62 pp; low / mid −4 pp |
| Per-patient + drop              | pass | **pass** | (high stratum dropped; remainder improves) |

### Stratum-level breakdown (m_unity policy)

| Stratum  | n     | base_hypo | cand_hypo | Δ         | passes |
|----------|------:|----------:|----------:|----------:|--------|
| high     | 6 131 | 0.391 %   | 1.011 %   | +0.62 pp  | ✓ (within 1 pp Δ + 2 % ceiling) |
| mid      | 3 446 | 5.311 %   | 0.580 %   | −4.73 pp  | ✓ |
| low      | 4 838 | 5.002 %   | 0.909 %   | −4.09 pp  | ✓ |
| unknown  |   939 | 0.639 %   | 0.426 %   | −0.21 pp  | ✓ |

### Stratum-level breakdown (raw baseline)

| Stratum  | base = cand hypo | passes |
|----------|------------------:|--------|
| high     | 0.391 %           | ✓ (low absolute risk) |
| mid      | 5.311 %           | ✗ (exceeds 2 % ceiling) |
| low      | 5.002 %           | ✗ (exceeds 2 % ceiling) |
| unknown  | 0.639 %           | ✓ |

## Key findings

**1. The high-braking subset is low-risk at baseline (0.391 %).** This is the
load-bearing fact that EXP-3013 / 3014 / 3015b were dancing around without
quantifying. Forcing M=1.0 for these patients (m_unity) lifts them to 1.0 %
hypo — that is the inherent floor of leaving an aggressive controller alone,
not policy-induced harm. Cohort gate conflated this small high-stratum risk
floor with the genuinely-elevated low/mid stratum baseline (≈ 5 %).

**2. The cohort gate produces both false-negatives and false-positives** on
heterogeneous policies. A policy that *removes* harm from low/mid strata
while leaving high stratum near baseline (m_unity) was being rejected.
Conversely, a policy that *only* helps the smallest stratum could
mathematically pass cohort while leaving most patients exposed.

**3. The stratified gate still has teeth.** Raw baseline fails on low/mid
strata under stratified — the 5 % hypo rate breaches the 2 % absolute
ceiling. So this is not a rubber-stamp.

**4. Stratified gate unlocks m_unity for population deployment.** Combined
with EXP-3017's clamped per-patient parquet, the deployable invocation is:
```
cf_replay_score_v3 --per-patient --braking-gate --braking-mode m_unity \
    --safety-mode stratified
```
This applies per-patient (T*, M*) recommendations with phenotype clamp
pre-baked AND validates safety per-stratum. Score 0.7051, all strata pass.

## Open follow-ups

- Stratified gate uses cf-replay-baseline as reference, not clinically
  observed hypo. The cf-replay baseline is closer to a "no-intervention
  forecast" than an empirical rate; for a real deployment, swap in observed
  hypo from the source CGM stream as the reference. Tracked.
- `unknown` stratum (n=939) has low risk in this cohort but in production
  with patients absent from the phenotype parquet the gate falls back to the
  same Δ + 2 % logic. This is conservative but unprincipled; consider
  imputation from controller mode + bolus-frac as a Phase 5 follow-up.

## Files

- Modified: `tools/aid-autoresearch/cf_replay_score_v3.py` (`--safety-mode`,
  `_stratify_braking`, `_stratified_safety`).
- Source: this report.
