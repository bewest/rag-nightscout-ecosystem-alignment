# EXP-2857: TOD Stability of Audition Bootstrap Signals (2026-04-22)

## Hypothesis

The single-pool bootstrap (EXP-2861) computes one P(under) and one
P(over) per patient by resampling all corrections together. If the
ISF gap varies materially by time-of-day, this pooling hides
heterogeneity that should be acted on (e.g. an evening-only
under-correction). EXP-2857 stratifies the EXP-2847 per-event
corrections into 4 TOD blocks (night/morning/afternoon/evening) and
re-runs the per-patient bootstrap inside each block.

## Method

* Source: `externals/experiments/exp-2847_correction_events.parquet`
  filtered to `drop > 0`, `bolus > 0`, `sched_isf > 0`.
* TOD blocks: night `[0–6)`, morning `[6–12)`, afternoon `[12–18)`,
  evening `[18–24)` (UTC, as stored).
* Per (patient, TOD) with ≥ 20 events: N=300 bootstrap of median ISF
  gap = (median(obs) − median(sched)) / median(sched).
* Compute P(gap < −10%) and P(gap > 30%) per block.
* Per patient, take min/max across TOD blocks → spread; mark
  "explicit disagreement" when one TOD block has P ≥ 0.9 and another
  has P < 0.1 (i.e. would land in opposite severity tiers).

## Results

| Metric | Value |
|--------|-------|
| TOD buckets evaluated | 55 |
| Patients total | 16 |
| Patients with ≥ 2 TOD blocks | 15 |
| Median per-patient spread P(over) | **0.30** |
| Median per-patient spread P(under) | 0.00 |
| Max per-patient spread P(under) | 0.95 |
| Explicit TOD disagreement on under | 1 |
| Explicit TOD disagreement on over | 2 |

TOD coverage is even (13–15 buckets per block).

## Interpretation

The single-pool bootstrap is **adequate for under-correction signal in
most patients** (median spread 0) but **systematically hides
over-correction TOD heterogeneity** (median spread 0.30 ≈ a third of
the [0,1] probability range). At least 3 patients (~20% of the
multi-TOD cohort) would receive the *opposite* triage outcome
depending on which TOD block is asked.

## Productionization implication

Bootstrap-gated audition should expose **per-TOD probabilities** for
the ISF-gap signal, not only the pooled probability. The
production-side change is small:

1. Add optional `p_isf_under_correction_by_tod` /
   `p_isf_over_correction_by_tod` (dict[TOD → float]) to
   `AuditionInputs`.
2. In `classify_triage_flags`, when present, emit a per-TOD flag at
   the strongest TOD's severity rather than collapsing.
3. `IsfGapFactsLoader` reads from `exp-2857_tod_isf_gap.parquet` if
   the file is present, falling through to single-pool otherwise.

This is left for a follow-on commit to keep this experiment isolated.

## Patient `b` revisited

Patient `b`'s pooled `p_isf_under_correction = 0.63` (boundary). The
TOD breakdown should be inspected before promoting/suppressing the
flag — TOD analysis may resolve the boundary ambiguity into a clear
"evenings-only" under-correction, for example.

## Artifacts

* `externals/experiments/exp-2857_tod_isf_gap.parquet`
* `externals/experiments/exp-2857_summary.json`
* `docs/60-research/figures/exp-2857_tod_stability.png`
* `tools/cgmencode/exp_tod_stability_2857.py`
