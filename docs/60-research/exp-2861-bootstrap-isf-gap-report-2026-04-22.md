# EXP-2861 — Bootstrap confidence on per-patient ISF gap

**Date**: 2026-04-22
**Driver**: `tools/cgmencode/exp_bootstrap_isf_gap_2861.py`
**Inputs**: `externals/experiments/exp-2847_correction_events.parquet`
**Outputs**: `externals/experiments/exp-2861_bootstrap_isf_gap.parquet`,
`exp-2861_summary.json`, `docs/60-research/figures/exp-2861_bootstrap_isf_gap.png`

## Hypothesis

The audition-matrix `isf_gap_pct` signal (EXP-2847) is currently a single
point estimate per patient. Patients near the ±10% / +30% audition
thresholds are likely sensitive to per-event noise. Generalize the
EXP-2859 bootstrap-confidence pattern to give each patient an explicit
probability of being a true under- or over-corrector.

## Method

For each of the 16 patients with ≥20 valid correction events
(`drop>0`, `bolus>0`, `sched_isf>0`):

1. Compute event-level `gap_pct = 100·(obs_isf − sched_isf)/sched_isf`.
2. Bootstrap-resample events with replacement, N=500 replicates.
3. Per replicate, record the median gap.
4. From the 500 medians, compute:
   - 95% CI (2.5/97.5 quantiles)
   - `P(under) = P(median < −10%)`
   - `P(over)  = P(median > +30%)`
   - `P(within band) = 1 − P(under) − P(over)`
5. Classify each patient into one of four bands at the P≥0.9 threshold:
   confident_under, confident_over, confident_neutral, uncertain.

## Results

**Cohort**: 16 patients with sufficient correction events
(median 355 events / patient).

**Bootstrap classification vs naive point-estimate**:

| Band             | Naive (point) | Bootstrap (P≥0.9) | Δ |
|------------------|---------------|-------------------|----|
| under-correction | 2             | 1                 | −1 |
| over-correction  | 9             | 8                 | −1 |
| neutral (in band)| 5             | 2                 | −3 |
| uncertain        | —             | 5                 | +5 |

**Bootstrap demotes 5 of 16 patients (31%) into "uncertain"**: 1 over-
corrector, 1 under-corrector, and 3 of 5 naive-neutral patients whose
CIs straddle the −10% or +30% thresholds. Median bootstrap CI width is
**23.4 percentage points** — substantial relative to the ±10/+30 gates.

Patient `b` — the canonical triple-flag triage candidate — has
`P(under-correction)=0.63`, classified **uncertain** by bootstrap. The
canonical "under-correction" call from the point estimate (~−14%) is
not statistically robust given event-level variance. This is a
material refinement to the audition triage list.

## Productionization

`AuditionInputs` extended with two fields:

```python
p_isf_under_correction: Optional[float] = None  # EXP-2861 bootstrap
p_isf_over_correction:  Optional[float] = None  # EXP-2861 bootstrap
```

`classify_triage_flags` precedence (when bootstrap fields present):

| Bootstrap state              | Severity | Behavior |
|------------------------------|----------|----------|
| `P(under) ≥ 0.9`             | high     | emit `isf_under_correction` |
| `P(over)  ≥ 0.9`             | medium   | emit `isf_over_correction` |
| `0.1 ≤ max(P) < 0.9`         | low      | emit boundary flag (provisional) |
| both `P < 0.1`               | suppress | naive `isf_gap_pct` branch ignored |

Bootstrap fields take precedence over the naive `isf_gap_pct` branch
(verified by `test_p_isf_takes_precedence_over_point_estimate`).

`IsfGapFactsLoader` (new): per-patient bridge from
`exp-2861_bootstrap_isf_gap.parquet` to `AuditionInputs`. Smoke test
loads 16 patients.

## Tests

- 5 new audition-matrix tests covering the four severity bands plus
  precedence: `test_p_isf_under_high_emits_high_severity`,
  `test_p_isf_over_high_emits_medium`, `test_p_isf_boundary_emits_low`,
  `test_p_isf_within_band_suppresses`,
  `test_p_isf_takes_precedence_over_point_estimate`
- 4 new loader tests
- All 904 production tests pass.

## Pattern generalization

This is the second audition signal (after EXP-2859 Simpson) refined by
block/event bootstrap. The pattern is:

1. Point estimate of patient-level summary statistic.
2. Bootstrap (block or event-level, depending on signal structure) →
   per-patient probability of crossing each audition threshold.
3. Three-tier severity gating (high / boundary-low / suppress) replaces
   single-threshold gate.
4. Loader bridges parquet artifact to `AuditionInputs`.

The pattern is now ready to apply to the remaining audition signals
(`median_recovery_fraction`, `wear_isf_drop_pct`, `post_high_mg_dl`).

## Charter compliance

Stream B (settings audition). Bootstrap operates on observed
closed-loop data only; no Stream A magnitude claims. The flag now
carries explicit confidence rather than a hidden boolean — improves
G3 (uncertainty propagation).
