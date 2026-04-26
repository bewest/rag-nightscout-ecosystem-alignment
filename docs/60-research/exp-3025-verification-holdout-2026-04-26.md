# EXP-3025 — cf-replay v3 verification-stripe holdout

**Date**: 2026-04-26
**Verdict**: **FAIL (stratum-specific safety regression)** — composite uplift generalizes; postprandial-high stratum violates the safety guard on the holdout.
**Status**: Honest negative. Policy is *not* ready to be shipped without a tightened high-stratum guard.

## Pre-registered hypothesis

The cf-replay v3 headline policy (`per_patient=clamped × proxy=carb_aware × braking_gate=0.15 × braking_mode=drop × safety_mode=stratified × phenotype=imputed`, the EXP-3020 sweep winner) generalizes from the training stripe to the previously-unused every-10-days verification stripe.

## Pre-registered success criteria (from `plan.md`)

| Crit | Description |
|------|-------------|
| (a) | Stratified safety passes on verification stripe |
| (b) | Δcomposite (verif) ≥ 0.5 × Δcomposite (train) — non-inferior |
| (c) | Per-controller direction matches training (Loop & Trio) |
| (d) | At least 2 of 3 strata pass safety on their own |

All four must pass for an overall PASS.

## Inputs (frozen, sha256 in JSON)

| File | Notes |
|------|-------|
| `externals/experiments/exp-3007_ascent_events__training.parquet` | 17 919 events / 31 patients |
| `externals/experiments/exp-3007_ascent_events__verification.parquet` | **2 672 events / 23 patients** (16% of training; 23.6 weeks) |
| `externals/experiments/exp-3012_per_patient.parquet` | Per-patient (T*, M*) trained on training only |
| `externals/experiments/exp-3019_phenotype_imputed.parquet` | Phenotype trained on training only |

`fit_source = training` for all per-patient and phenotype fits; `eval_source` differs.

## Headline numbers

| Metric | Training | Verification |
|--------|---------:|-------------:|
| Score (baseline, no policy) | 0.6691 | 0.6837 |
| Score (headline policy) | **0.7133** | **0.7255** |
| **Δscore** | **+0.0442** | **+0.0418** |
| Non-inferiority margin (½ × train Δ) | — | +0.0221 |
| Stratified safety | PASS (training) | **FAIL (high stratum)** |

Composite verification uplift exceeds the non-inferiority margin (+0.0418 vs +0.0221). Direction of improvement holds on both controllers.

## Per-controller (verification)

| Controller | n | obs_overshoot | cand_overshoot | Δ |
|------------|---:|---:|---:|---:|
| Loop | 511 | 0.591 | 0.575 | −0.016 |
| Trio | 1 607 | 0.369 | 0.329 | −0.040 |

Direction matches training for both (training Δ_Loop = −0.028; Δ_Trio = −0.038).

## Per-stratum safety (verification) — **the failure mode**

| Stratum | n | baseline_hypo | cand_hypo | Δpp | Passes |
|---------|---:|---:|---:|---:|:---:|
| high (post-prandial) | **390** | 3.3 % | **7.7 %** | **+4.4 pp** | **FAIL** |
| mid | 815 | 3.9 % | 0.49 % | −3.4 pp | PASS |
| low | 913 | 2.8 % | 0.22 % | −2.6 pp | PASS |

The high-stratum hypo count goes from ~13 to ~30 of 390 events. Small absolute count, but a clear directional safety regression on the holdout that did not appear on the training fit.

## Criteria summary

| Criterion | Verdict |
|-----------|:-------:|
| (a) stratified safety passes | **FAIL** |
| (b) non-inferior to ½ × train Δ | PASS |
| (c) per-controller direction matches | PASS |
| (d) ≥ 2 strata pass on their own | PASS |
| **Overall** | **FAIL** |

## Interpretation

This is the result the holdout was designed to expose. The composite headline (+0.04 score, both controllers in the right direction) **does** generalize, but the stratified-safety guard catches a high-stratum hypo regression that the training fit didn't surface — likely because the high stratum on verification (n=390) is smaller and sampled differently than on training (n=4 327).

Three honest readings:

1. The high-stratum guard is doing its job — it's a real holdout signal, not a lab artifact.
2. The policy is **directionally** validated on a held-out stripe (criteria b + c + d), but **not safe to ship as-is** without a tightened high-stratum gate.
3. This invalidates any claim that the EXP-3020 cohort-level winner is "the" final policy. It's a *training-set winner*. The holdout has spoken.

## Follow-ups (proposed; not opened in this commit)

* **EXP-3025-FIX**: Sweep `--braking-gate` upward (0.20, 0.25, 0.30) restricted to `phenotype.archetype == 'high'` patients on the training stripe; re-evaluate on verification. Hypothesis: a higher gate on the high stratum trades small composite gain for safety pass.
* **EXP-3025-N**: Repeat with bootstrap resampling of patients (not events) to confirm the high-stratum failure isn't carried by 1–2 patients.

## Working-rules compliance

* Code in git (`tools/aid-autoresearch/exp_3025_holdout.py`); data artifacts only in `externals/experiments/exp-3025_holdout_summary.json` (gitignored).
* Provenance fields (`fit_source`, `eval_source`, `events_path`, `events_sha256`) recorded.
* Existing `tools/aid-autoresearch/test_cf_replay_score_v3.py` and the new `test_correction_events_inferred_meals.py` regression tests both green.
* No retroactive change to the headline parameters; we report what we measured.

## Reproducibility

```
python3 tools/aid-autoresearch/exp_3025_holdout.py
# writes externals/experiments/exp-3025_holdout_summary.json
```
