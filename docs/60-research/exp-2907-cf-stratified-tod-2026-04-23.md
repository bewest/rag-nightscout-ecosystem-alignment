# EXP-2907 — cf-stratified TOD × lineage report

**Date:** 2026-04-23 (overnight)
**N:** 2,748 descent events across 19 patients × 3 lineages
**Source:** `tools/cgmencode/exp_cf_stratified_tod_2907.py`
**Purpose:** Apply EXP-2904's load-stratification guard (Default Guard
#6) to EXP-2895's TOD × lineage night-degradation finding.

## Headline

Night degradation **survives** cf-conditioning at the event level.
The lineage-conditional severe-rate excess at night (oref0 +15pp,
oref1 +10pp, Loop ~0pp) is essentially identical inside the high-cf
stratum (oref0 +15pp, oref1 +10pp, Loop ~0pp). Statistical
significance strengthens within the high-cf stratum (oref1 p=0.004).

The night degradation is **not** a load-saturation artifact.

## Stratified results

### Marginal (no conditioning)
| Lineage          | n     | Night sev | Day sev | Δ      |
|------------------|------:|----------:|--------:|-------:|
| Loop (iOS)       | 1,125 | 0.410     | 0.404   | +0.006 |
| oref1 (modern)   | 1,200 | 0.388     | 0.287   | +0.101 |
| oref0 (legacy)   |   423 | 0.624     | 0.474   | +0.150 |

### Within high-cf stratum (cf_severe ≥ 0.95, n=2,586)
| Lineage          | n     | Night sev | Day sev | Δ      | χ² p   |
|------------------|------:|----------:|--------:|-------:|-------:|
| Loop (iOS)       | 1,096 | 0.419     | 0.415   | +0.003 | 0.983  |
| oref1 (modern)   | 1,160 | 0.394     | 0.298   | +0.095 | **0.004** |
| oref0 (legacy)   |   330 | 0.768     | 0.617   | +0.151 | **0.012** |

### Within low-cf stratum (cf_severe < 0.95, n=162)
All severe rates are 0 — events whose counterfactual nadir wouldn't
reach severe don't reach severe in observation either. As expected.

## Interpretation

### Night degradation passes Default Guard #6
The hypothesis that night degradation reflected overnight cf
elevation common across lineages is **rejected**. Within the
high-cf stratum, where every event is at the load ceiling, the
lineage-by-TOD severe-rate gradient is preserved with essentially
unchanged magnitude.

This is a **genuine algorithm-mechanism difference** between
overnight and daytime defence, not a behavioural-self-selection
artifact.

### Asymmetry: 94% of events are high-cf
The cf_high stratum contains 2,586 of 2,748 events (94%). Severe
events virtually only occur from high-cf descents. The low-cf
stratum acts as a sanity check (all 0 severe) but has no power for
TOD comparison.

### Loop's TOD-invariance is robust
Loop shows +0.003 δ within the high-cf stratum — even in the most
demanding events, Loop's defence is identical day vs night. This
confirms EXP-2895's lineage signature was not stratum-dependent.

### oref0 / oref1 night gap is mechanism, not load
- oref1: +9.5pp night excess, p=0.004 (n=1,160). With ~33× more
  events than EXP-2895's per-patient analysis, the effect tightens
  to a robust α=0.01 result.
- oref0: +15.1pp night excess, p=0.012 (n=330). Smaller cell, larger
  absolute gap. Same direction as marginal.

### Strengthens lineage-mechanism narrative
Combined with EXP-2904 (oref1>Loop survives cf-conditioning), this
result expands the set of lineage signatures that pass Guard #6:
- Mean protection (cf-conditioned) — survives
- Night degradation (cf-conditioned) — survives
- TOD-invariance (Loop) — survives

The "8-dimension lineage signature table" can now be re-graded:
each dimension is either Guard-#6 verified or pending re-test.

## Audition matrix implications

`night_protection_degraded` flag (EXP-2895) is robust to
cf-conditioning and does not need attenuation. The lineage-conditional
thresholds remain valid:
- oref0 ≥15pp HIGH
- oref1 ≥10pp MEDIUM
- Loop suppressed

These thresholds match the within-stratum effect sizes (oref0 +15.1pp,
oref1 +9.5pp) almost exactly. Coincidental but reassuring.

## Robustness gaps

- Per-patient stratification (instead of per-event) would be more
  conservative; current results pool events across patients.
- Hierarchical model with patient random intercept not tested.
- Hourly resolution (EXP-2896) within cf strata not yet performed.
- Loop stratified result has wide 95% CI given +0.003 effect; consistent
  with true zero but not definitively so.

## Linked artefacts

- `docs/60-research/exp-2895-tod-lineage-report-2026-04-22.md`
- `docs/60-research/exp-2904-cf-conditioned-lineage-2026-04-22.md`
- `docs/60-research/deconfounding-toolkit-2026-04-22.md`
- `tools/cgmencode/exp_cf_stratified_tod_2907.py`
- `externals/experiments/exp-2907_summary.json`

## Next

- Re-grade 8-dimension lineage signature table with Guard-#6 status
- EXP-2908: hourly cf-stratified replay (combine EXP-2896 + EXP-2907)
- AAPS data sourcing plan to grow oref0 cohort
