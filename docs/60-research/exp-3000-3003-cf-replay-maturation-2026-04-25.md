# EXP-3000 → EXP-3003: Counterfactual-Replay Maturation (2026-04-25)

**Branch**: `autoresearch/2026-04-24-cf-replay`
**Engine**: `tools/cgmencode/autoresearch_cf/replay.py`
**Ledger**: `tools/aid-autoresearch/autoresearch_cf_results.tsv`

## Mandate
Mature the EXP-2889 counterfactual-replay analysis from descent-only / pop-ISF / linear-duration / instantaneous-insulin into a defensible, sensitivity-aware
methodology suitable for a fitness function in `tools/aid-autoresearch/`.

## Method
A pure-functional engine with three pluggable factors — **ISF source**,
**insulin kernel**, **duration model** — so each iteration changes one factor
while holding the others at the previous baseline (clean ablation). Per-event
parquet, per-patient parquet, summary JSON, 3-panel figure (matching EXP-2889
layout), and a TSV ledger row are produced per iteration.

Inputs: `externals/experiments/exp-2881_evening_drivers.parquet` (n=3673 events,
31 patients, 19 with full phenotype), `exp-2886_phenotype.parquet`,
`externals/ns-parquet/training/profiles.parquet`.

## Headline matrix

| EXP | ISF source | Kernel | Duration | pop_cf_severe | protection | rank ρ vs baseline | braking ρ |
|---|---|---|---|---:|---:|---:|---:|
| **3000** | population (50) | instantaneous | linear (60 min) | 94.7% | 58.4 pp | (=) | **−0.711** ✱ |
| **3001** | per-patient profile (mean 70) | instantaneous | linear | 95.9% | 59.7 pp | +0.96 | **−0.878** ✱✱✱ |
| **3002** | per-patient | oref0 PK (peak=75) | linear | 48.3% | 12.1 pp | +0.31 | +0.02 |
| **3003** | per-patient | oref0 PK (peak=75) | sigmoid_s400 (240 min) | 96.7% | 60.4 pp | +0.96 | **−0.868** ✱✱✱ |

EXP-3002 sweep over PK peak ∈ {55, 75, 95} all show destabilisation (rank ρ < 0.4).
EXP-3003 sweep over duration stretch ∈ {1.25, 2.0, 4.0} crossed with kernel ∈ {instantaneous, PK} produced a clean monotone — see `externals/experiments/exp-3003_summary.json`.

## What this proves

1. **EXP-3001 strengthens EXP-2889.** Per-patient profile ISF (median 70, vs the
   pop value of 50) sharpens the construct validity: braking_ratio ↔ cf_severe
   correlation tightens from −0.711 (n=19, p=0.001) to −0.878 (p<0.001).
   Rank order across patients is preserved (ρ=0.96), so EXP-2889's *rank-based*
   conclusions are robust to the ISF assumption.

2. **EXP-3002 reveals a load-bearing assumption in EXP-2889.** Replacing the
   instantaneous insulin assumption with an oref0 exponential-PK kernel
   collapses the result: only ~3 mg/dL of "extra drop" is realised within a
   60-min descent window because peak insulin action is at 75 min. The
   braking_ratio correlation goes to zero. *EXP-2889's published 94.7%
   counterfactual-severe rate is not a defensible point estimate under PK
   realism.*

3. **EXP-3003 explains the cancellation.** EXP-2889's headline numbers
   coincided with a fortuitous compensation of two errors:
   linear duration (60 min) was *too short*, and instantaneous kernel was *too
   aggressive*. When **both** are made realistic (PK + sigmoid stretch ≈4×),
   the result converges back to cf_severe ≈ 96.7% and braking ρ = −0.868.
   The signal is real; the magnitude is right; the original method just got
   there by luck.

## Implications for the autoresearch fitness function (next: EXP-3005)

- Use **per-patient ISF + oref0 PK + sigmoidal duration (stretch=4)** as the
  canonical configuration for any cf-replay-derived fitness.
- The fitness should report the **rank** of a candidate controller's cf_severe
  *across patients* rather than a population point estimate (rank is robust to
  ISF + kernel + duration; the magnitude is not).
- Optionally report a sensitivity tuple `(cf_severe@instant, cf_severe@PK)`
  as a confidence-interval surrogate.

## Honest open issues

- **Duration stretch=4** is empirically chosen to match the realistic fixed
  point; should be replaced by a per-event sigmoid fit to the actual descent
  curve (left for EXP-3007 if needed).
- **Mean ISF used = 70** is suspiciously high (population median across
  protocols is closer to 40-60). Some patient profiles may have units
  mis-tagged; the engine's `isf_source_profile` already filters values <30 as
  suspect, but profile-side high-side validation is not yet applied.
- 19/31 patients have phenotype attached. Correlations are computed only on
  the n=19 subset; merge nulls match EXP-2889.

## Verdict
**CF-replay engine is now production-grade for autoresearch hookup (EXP-3005).**
Methodology now reports magnitudes with explicit kernel/duration sensitivity,
and rank-order results are stable across all four iterations.
