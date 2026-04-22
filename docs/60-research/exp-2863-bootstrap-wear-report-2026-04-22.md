# EXP-2863 — Bootstrap confidence on wear/site-degradation signal

**Date**: 2026-04-22
**Driver**: `tools/cgmencode/exp_bootstrap_wear_2863.py`
**Inputs**: `externals/ns-parquet/training/grid.parquet` (re-extracted per-event ISFs with cage_hours)
**Outputs**: `externals/experiments/exp-2863_bootstrap_wear.parquet`,
`exp-2863_per_event_isf_wear.parquet`, `exp-2863_summary.json`,
`docs/60-research/figures/exp-2863_bootstrap_wear.png`

## Hypothesis

Apply the EXP-2859/2861/2862 bootstrap-confidence pattern to the
fourth audition signal: `wear_isf_drop_pct` (EXP-2831). The naive
flag fires when (median ISF aged ≥48h) − (median ISF fresh <24h)
divided by fresh median is < −20%. Per-patient sample sizes are
small (typically 5–25 events per band); bootstrap quantifies whether
the apparent degradation is statistically distinguishable from
sampling noise.

## Method

Re-extracted 723 correction events across 27 patients from
`grid.parquet` mirroring EXP-2831's filtering logic
(BG≥180, bolus≥0.5U, no recent carbs, IOB≤2, sensor not in warmup,
1≤time-in-high≤6h, drop>0). For the 10 patients with ≥5 fresh
(cage<24h) **and** ≥5 aged (cage≥48h) events:

1. Bootstrap-resample fresh and aged event-ISFs independently with
   replacement, N=500 replicates.
2. Per replicate, compute `delta_pct = (median_aged − median_fresh) / median_fresh × 100`.
3. Quantify `P(degradation < −20%)` and `P(improvement > +20%)`.

## Results — strong negative finding

| Band               | Naive (point) | Bootstrap (P≥0.9) | Δ |
|--------------------|---------------|-------------------|----|
| confident degrade  | 4             | **0**             | −4 |
| confident improve  | 1             | **0**             | −1 |
| confident neutral  | 5             | **0**             | −5 |
| uncertain          | —             | **10**            | +10 |

**All 10 patients land in "uncertain"**. **Median bootstrap CI width:
107 percentage points** — the wear signal is essentially indistinguishable
from sampling noise at typical event volumes (median 14 fresh + 14 aged
events).

The naive flag's HIGH severity for `wear_isf_drop_pct < −20` is
**overconfident**: every flagged patient has 95% CIs that easily span
both the −20% threshold and zero.

## Productionization

- `AuditionInputs.p_site_degradation: Optional[float]`
- `classify_triage_flags`: bootstrap branch precedes naive
  `wear_isf_drop_pct` branch:

| Bootstrap state           | Severity | Behavior |
|---------------------------|----------|----------|
| `P(degrade) ≥ 0.9`        | high     | emit `site_degradation` |
| `0.1 ≤ P(degrade) < 0.9`  | low      | boundary (provisional) |
| `P(degrade) < 0.1`        | suppress | naive branch ignored |

For the present cohort, the bootstrap branch will downgrade **all**
naive HIGH wear flags to LOW (boundary). Patient `b`'s site_degradation
flag — part of the canonical "triple-flag" — does not survive bootstrap
either (insufficient data: only 3 fresh events) and is dropped from
audition entirely (no bootstrap result, no naive trigger because not
in the cohort with enough events).

`WearFactsLoader` (new): bridges EXP-2863 parquet to AuditionInputs.
4 new audition tests + 4 loader tests; **44/44** audition+loader tests
pass.

## Pattern status & implication

Four audition signals now use the bootstrap-confidence pattern:

| EXP | Signal | % patients demoted to "uncertain" |
|-----|--------|------------------------------------|
| 2859 | Simpson paradox | 12/26 (46%) |
| 2861 | ISF gap | 5/16 (31%) |
| 2862 | Recovery fraction | 5/16 (31%) |
| **2863** | **Wear/site-degradation** | **10/10 (100%)** |

**Across all four signals, ~30–100% of naive HIGH-severity flags
do not survive bootstrap.** The audition triage system as previously
configured was systematically over-flagging. Bootstrap-confidence
gating is now the single most important production refinement to the
audition matrix.

## Patient `b` final canonical reclassification

| Signal | Naive | Bootstrap | Confidence-aware verdict |
|--------|-------|-----------|--------------------------|
| Simpson | flagged | boundary | downgrade to LOW |
| ISF under-correction | flagged | boundary (P=0.63) | downgrade to LOW |
| Recovery low | flagged | **P=1.00** | **HIGH (confirmed)** |
| Wear/site-degradation | (unscored: insufficient) | n/a | suppress |

Patient `b` is now formally a **single-flag (low recovery, P=1.00)**
high-confidence triage candidate, not the previously canonical
"triple/quadruple flag" archetype.

## Charter compliance

Stream B (settings audition); explicit confidence bands for all four
audition inputs improve G3 (uncertainty propagation). The per-event
re-extraction reuses the EXP-2831 filtering logic verbatim (no
methodology drift).
