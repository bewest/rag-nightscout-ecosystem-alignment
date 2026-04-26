# Autoresearch session 2026-04-26 — lessons-learned integration + holdout campaign

## TL;DR

This session closed three pieces of long-standing debt and ran two of four planned hypothesis experiments.

| Track | Status | Headline |
|-------|:------:|----------|
| P1.1 source-aware ascent extraction + scorer provenance | ✅ done | `--source {training,verification}` everywhere; `events_sha256` in JSON; `cf_replay_v3_ledger.tsv` created |
| P1.2 inferred-meal adoption in `_extract_correction_events` | ✅ done | Closes EXP-2739 under-logger ISF-bias mechanism upstream; auto-wired through `run_pipeline` via existing `meals_for_basal` |
| P1.3 regression tests | ✅ done | 5 new tests (`test_correction_events_inferred_meals.py`); 464 production tests still pass |
| P1.4 pipeline wiring | ✅ done | Subsumed by P1.2 — upstream patch means advisors get clean events without per-advisor changes |
| **EXP-3025** verification-stripe holdout | ⚠️ **FAIL** | Composite uplift +0.0418 generalizes (margin +0.0221), per-controller direction matches, but high-stratum cand_hypo 3.3 → 7.7% (n=390) — the holdout caught a real safety regression |
| **EXP-3026** inferred-meal directional shift | ✅ **PASS** | Aligned loggers 0.66 % vs under-loggers 43.3 % correction-event exclusion, Spearman = +0.90; explains the 20–45 % ISF inflation in EXP-2739 |
| EXP-3027 LOO phenotype imputation | ⏸ deferred | Original framing conflated archetype imputation with cf-replay BG-band strata; needs re-design |
| EXP-3028 event-wise carb-aware refit | ⏸ deferred | Should follow EXP-3025-FIX, not failed EXP-3025 |

## Commits landed this session

| SHA | Subject |
|-----|---------|
| `31d8172d` | EXP-3025-prep: source-aware ascent extraction + provenance |
| `73643d26` | EXP-3026-prep: adopt inferred meals in correction-event extraction |
| `5b41a605` | EXP-3025: FAIL — verification-stripe holdout exposes high-stratum safety regression |
| `f7d41373` | EXP-3026: PASS — inferred-meal correction-event shift is directional and monotone |
| `3374bd66` | EXP-3026: append ledger row |

All commits carry the `Co-authored-by: Copilot` trailer per workspace rules. No data parquets / JSON were committed — everything in `externals/experiments/` stays gitignored.

## What the holdout taught us

EXP-3020 picked `per_patient=clamped × proxy=carb_aware × braking_gate=0.15 × braking_mode=drop` as the cohort-final headline. EXP-3025 ran that same policy against the every-10-days verification stripe (2 672 events / 23 patients / 23.6 weeks; 16 % of training). Three-of-four pre-registered criteria passed:

| Criterion | Verdict | Detail |
|-----------|:-------:|--------|
| (a) stratified safety | **FAIL** | high stratum: 3.3 → 7.7 % (+4.4 pp), n=390 |
| (b) non-inferiority to ½ × train Δ | PASS | verif Δ = +0.0418 vs margin +0.0221 |
| (c) per-controller direction match | PASS | Loop −0.016 / Trio −0.040 |
| (d) ≥ 2 strata pass on their own | PASS | mid + low pass; high fails |

The 4.4 pp hypo regression on the high stratum is the kind of finding holdouts exist for. The training fit didn't surface it because the high stratum on training (n ≈ 4 327) absorbed the variance; the smaller verification high stratum (n = 390) didn't. **The EXP-3020 winner is a training-set winner, not yet shippable.**

## What inferred-meal adoption taught us

EXP-3026 measured the mechanism behind the EXP-2739 under-logger ISF bias. On the 5 cohort patients with cached inferred-meal frames, the correction-event filter excluded 0.66 % of events on aligned loggers vs 43.3 % on under-loggers, with a Spearman rank correlation of +0.90 between under-logging severity and exclusion fraction. Patient `d` (severity 0.43, 2 628 baseline events): 25.4 % excluded. Patient `a` (severity 0.38, 186 baseline events): 61.3 % excluded.

The mechanism is now closed in the production pipeline (`_extract_correction_events` + `run_pipeline` wiring) and pinned by 5 regression tests. Aligned loggers see no behavior change; under-loggers no longer have post-meal boluses mis-classified as fasting corrections. The 20–45 % ISF inflation envelope from memory is structurally explained by these exclusion rates.

## High-value next experiments (not opened in this session)

1. **EXP-3025-FIX** (highest value): Sweep `--braking-gate` (0.20, 0.25, 0.30) restricted to phenotype-`high` patients on the training stripe; re-evaluate stratified safety on the verification stripe. Hypothesis: a higher gate on the high stratum trades small composite gain for safety pass. **Critical**: holdout has now been evaluated once on the EXP-3020 winner; further sweeps must use a *new* holdout or accept the loss of true holdout status. Either commit to an out-of-stripe leave-one-patient-out evaluation, or use bootstrap on the verification stripe and document the inflation.
2. **EXP-3025-N**: Patient-level (not event-level) bootstrap of EXP-3025 to confirm the high-stratum failure isn't carried by 1–2 patients.
3. **EXP-3026-EXT**: Extend inferred-meal cache to the other 26 cohort patients (cheap; `InferredMealsLoader.compute_for(pid, grid)`), re-run EXP-3026 to confirm the +0.90 Spearman holds at n ≥ 30.
4. **EXP-3026-ISF**: End-to-end advisor pipeline run with and without the inferred-meal-filtered correction set; report ISF magnitude shift per patient and confirm it falls within the 20–45 % EXP-2739 envelope on heavy under-loggers. This directly closes the loop from upstream mechanism (EXP-3026) to clinical advisory output.
5. **EXP-3027 (re-designed)**: LOO of phenotype *archetype* imputation — hold out one observed patient, re-impute via the same controller-median + prefix-heuristic, check archetype agreement. Independent of cf-replay BG-band strata.
6. **EXP-3028** (deferred): Only run after EXP-3025-FIX produces a verified-on-holdout policy.

## Working-rules audit

* Code & reports in git: ✅ all 5 commits include source + report
* Data artifacts in `externals/experiments/` only: ✅ `exp-3007_ascent_events__verification.parquet`, `exp-3025_holdout_summary.json`, `exp-3026_correction_event_shift.{json,csv}`
* One commit per EXP: ✅
* `Co-authored-by: Copilot` trailer: ✅
* Append to ledger: ✅ `cf_replay_v3_ledger.tsv` — 2 rows added this session
* Existing tests still green: ✅ `test_cf_replay_score_v3.py` and full `test_production.py` (464 pass)

## Files touched

* `tools/cgmencode/autoresearch_cf/exp_3007_ascent_extraction.py` — source-aware extraction
* `tools/aid-autoresearch/cf_replay_score_v3.py` — `--source` / `--events-path` + provenance
* `tools/aid-autoresearch/cf_replay_v3_ledger.tsv` — new ledger
* `tools/aid-autoresearch/exp_3025_holdout.py` — EXP-3025 runner
* `tools/aid-autoresearch/exp_3026_advisor_shift.py` — EXP-3026 runner
* `tools/cgmencode/production/pipeline.py` — `inferred_meals` kwarg in `_extract_correction_events` + wiring in `run_pipeline`
* `tools/cgmencode/production/test_correction_events_inferred_meals.py` — new (5 regression tests)
* `docs/60-research/exp-3025-verification-holdout-2026-04-26.md`
* `docs/60-research/exp-3026-advisor-inferred-meal-shift-2026-04-26.md`
* `docs/60-research/AUTORESEARCH-SESSION-2026-04-26.md` (this file)
