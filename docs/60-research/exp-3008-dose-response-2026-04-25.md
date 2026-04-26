# EXP-3008 — Controller-discriminating cf-replay (dose-response) (2026-04-25)

**Branch**: `autoresearch/2026-04-24-cf-replay`
**Code**:
- `tools/cgmencode/autoresearch_cf/exp_3008_dose_response.py` (sweep)
- `tools/aid-autoresearch/cf_replay_score_v2.py` (autoresearch hookup)
**Inputs**: `externals/experiments/exp-3007_ascent_events.parquet`

## Hypothesis
A candidate controller's **SMB-aggression dose-response slope** on real ascent events is a *discriminating* fitness signal — different controllers (Loop, Trio, AAPS-oref0) have different marginal SMB efficacies. A controller-tuning candidate should be ranked by:
1. how much overshoot it removes per unit of extra SMB, and
2. how much hypo risk it accepts in exchange.

## Method
For each ascent event from EXP-3007, compute counterfactual peak under hypothetical SMB delivery `smb_candidate = smb_observed × multiplier`. Sweep `multiplier ∈ {0, 0.5, 1.0, 1.5, 2.0, 3.0}`. Score per-controller using:

```
ctrl_score = 0.70 × (1 − cand_overshoot) + 0.30 × (1 − 2·cand_hypo)
```

Hypo proxy = post-peak 60-min look-ahead via oref0 PK kernel (peak=75 min) over the *extra* SMB above baseline, flagged below 70 mg/dL.

## Results — dose-response per controller

| Controller | obs over | cand@0 | cand@1 | cand@2 | cand@3 | dOver/dMult | hypo@3 |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Trio**    | 39.8% | 41.6% | 39.8% | 37.5% | 35.7% | **−2.0 pp** | 0.30% |
| **Loop**    | 60.0% | 60.7% | 60.0% | 58.5% | 57.1% | **−1.2 pp** | 0.10% |
| **OpenAPS** | 51.6% | 51.6% | 51.6% | 51.5% | 51.4% | −0.07 pp | 0.03% |

**Headline: Trio's SMB lever is ~1.7× more responsive than Loop's, and ~30× more responsive than AAPS-oref0's** (which has essentially no SMB to multiply).

This *directly discriminates* candidate controllers by their marginal-SMB-efficacy profile on the real cohort, without re-implementing controller logic.

## Why the absolute reductions stay modest

Same fundamental PK constraint as EXP-3004: the 75-min insulin peak cannot fully realise inside a ~37-min ascent window. Even at multiplier=3.0, only ~10 % of nominal effect lands by peak time. The reduction is real but small in absolute terms; the *slope* is what discriminates.

## Best multiplier per controller
All controllers' composite score increases monotonically with multiplier through 3.0, with `cand_hypo_rate ≤ 0.30 %` (well below the 1.0 % safety gate). This means the cohort has **substantial unrealised SMB headroom on ascents** — none of the controllers are at the safety frontier yet.

But the **Loop=60 % overshoot rate cannot be substantially closed by SMB-aggression alone** within physical PK limits; achieving Trio-like overshoot rates would require Loop to **fire earlier in the ascent**, not just bigger.

## Autoresearch hookup — `cf_replay_score_v2.py`

Composite candidate fitness:

```
score = 0.50 × descent_v1_score              (severe-hypo protection)
      + 0.35 × ascent_score                   (overshoot + per-ctrl mean)
      + 0.15 × (1 − 2·max_hypo_rate)          (ascent safety penalty)
```

Hard safety gates:
- v1 descent gate (any patient with `cf_severe == 1.0` and `obs_severe > 0.5`)
- v2 ascent gate (any controller with `cand_hypo_rate > 1.0 %`)

Sample run (`mult=2.0`):
```
score=0.7100  safety=True  mult=2.0
  descent_v1     = 0.6613
  ascent_score   = 0.6556
  max_hypo_rate  = 0.0003  (gate ≤ 0.01)
```

The score function is **monotonic in multiplier across the safe regime**, suitable for ranking algorithm-mutation candidates that differ in dosing aggressiveness. Three TSV rows were appended (mult={0.5, 1.0, 2.0}) demonstrating live ledger integration.

## Deliverables
```
tools/cgmencode/autoresearch_cf/exp_3008_dose_response.py
tools/aid-autoresearch/cf_replay_score_v2.py
externals/experiments/exp-3008_dose_response.parquet     (gitignored)
externals/experiments/exp-3008_summary.json              (gitignored)
docs/60-research/figures/exp-3008_dose_response.png
```
Ledger now at 19 rows (added EXP-3008 sweep + 3 v2-scorer demo rows).

## Verdict
**`controller_discriminating_signal_confirmed`** — dose-response slopes are 30× different across controllers (Trio:OpenAPS), giving a clean ranking signal. v2 score function works and is wired into the autoresearch fitness pipeline.

## Open question for next phase
The ascent score plateaus monotonically without a peak inside multiplier=[0,3], i.e. the cohort never reaches the safety frontier. To make the score *bivariate* (find an OPTIMUM, not just a maximum), EXP-3009 should add a **per-event SMB-timing axis** (multiplier on `time-of-first-SMB`, e.g., fire SMB X minutes earlier) — Loop's earliest plausible improvement is on timing, not magnitude.
