# EXP-3005: CF-Replay Fitness Wrapper for Autoresearch (2026-04-25)

**Branch**: `autoresearch/2026-04-24-cf-replay`
**Scorer**: `tools/aid-autoresearch/cf_replay_score.py`
**Sister scorer**: `tools/aid-autoresearch/algorithm_score.py`

## Mandate
Wire EXP-3000-3003's mature counterfactual-replay engine into a fitness
function with the same JSON contract as `algorithm_score.py`
(`{"score": float, "safety_ok": bool, "components": dict}`) so the
autoresearch loop can score candidate parameter sets against real
descent-event data.

## What shipped
A standalone `cf_replay_score.py` with composite v1:

| Weight | Component | Source |
|---:|---|---|
| 45 % | protection_rank | Mean per-patient `aid_protection_severe` |
| 25 % | obs_penalty | `max(0, 1 − 2·pop_obs_severe)` |
| 20 % | robustness | Spearman ρ(realistic config, instantaneous fallback) |
| 10 % | construct | Spearman ρ(braking_ratio, cf_severe) → linear[-0.5, 0] |

**Hard safety gate**: any patient with `cf_severe ≈ 1.0` AND
`obs_severe > 0.50` → score 0 (controller magnifies hypo without
commensurate protection).

CLI flags expose every engine knob: `--isf-source`, `--kernel`, `--peak-min`,
`--dia-min`, `--duration`, `--stretch`, `--label`, `--append-tsv`.

## Sweep results (5 candidates)

| Label | ISF | Kernel | Duration | Score | protection_rank | braking_ρ |
|---|---|---|---|---:|---:|---:|
| realistic-canonical | profile | oref0_peak75 | sigmoid_s400 | 0.6613 | 0.6015 | −0.868 |
| fast-acting-pk      | profile | oref0_peak55 | sigmoid_s400 | 0.6620 | 0.6031 | −0.869 |
| slow-acting-pk      | profile | oref0_peak95 | sigmoid_s400 | 0.6619 | 0.6008 | −0.868 |
| legacy-2889         | profile | instantaneous | linear      | 0.6670 | 0.5963 | −0.878 |
| pop-isf-pk          | population | oref0_peak75 | sigmoid_s400 | 0.6625 | 0.5993 | −0.801 |

## Honest finding: score is *engine-discriminating*, not yet
*controller-discriminating*

Range across 5 candidates is 0.006 (range/mean = 0.9 %). This is **not a
bug** in the scorer — it's a structural property of the current setup:

> `cf_replay_score.py` describes the *existing* AID-on event stream. It can
> tell you which **engine configuration** (ISF source, kernel, duration) is
> most defensible. It cannot tell you whether a *candidate controller* would
> behave differently, because the events themselves don't depend on the
> controller's parameters.

To make the score discriminate controllers, EXP-3007 (out of scope this
session) needs to:
1. Take a candidate parameter set (basal, ISF, target, max_iob, SMB rules).
2. Run the candidate against per-patient time-series (5-min CGM + insulin
   history) to *generate* a hypothetical event stream.
3. Replay that stream through the engine.

Pre-requisite: per-patient 5-min time-series ingestion (currently only the
already-extracted descent-event parquet is loaded by `load_inputs`).

## What the score *is* useful for today
- **Choosing the canonical engine config** for any cf-replay analysis.
  The `legacy-2889` config scores marginally higher (0.667) because the
  instantaneous kernel has perfect rank correlation with itself
  (`robustness_rho = 1.0`) — a reminder that the robustness component
  rewards the fallback config and the realistic config agreeing.
- **Catching cohort regressions**: if a future re-ingestion changes which
  patients are flagged severe, the safety gate or `protection_rank`
  component will move.
- **Populating the autoresearch ledger** with a single fitness number per
  iteration, joinable to the EXP-3000-3003 maturation iterations.

## Verdict
**`autoresearch_hookup_complete`** — composite v1 ships, sister scorer to
`algorithm_score.py`, ledger integration validated on 5 candidate sweep.
Controller-discriminating score (v2) deferred to EXP-3007 pending
time-series ingestion.

## Next
EXP-3006: phenotype-conditional synthetic patient sampler (k-NN in the
braking_ratio × stack_score × hidden_leverage space) — feeds candidate
controllers with realistic parameter+behaviour pairs.
