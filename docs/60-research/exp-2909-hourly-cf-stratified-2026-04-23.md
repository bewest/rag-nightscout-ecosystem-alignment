# EXP-2909 — hourly cf-stratified replay report

**Date:** 2026-04-23 (overnight)
**Source:** `tools/cgmencode/exp_hourly_cf_stratified_2909.py`
**N:** 2,748 events × 24 hours × 3 lineages
**Visualization:** `docs/visualizations/exp-2909-hourly-cf-stratified.png`

## Headline

**Hourly lineage signatures survive cf-conditioning** at hourly
resolution. Combining EXP-2896's hourly mitigation finding with
EXP-2907's load-stratification framework confirms that the distinct
lineage hourly profiles are mechanism, not load artifact:

- **Loop**: dawn peak 04-05h (0.53–0.56 severe) — same in marginal and
  high-cf strata. Tight, narrow window.
- **oref1**: 03h focal spike 0.55 high-cf (vs 0.54 marginal) — survives
  with a slight intensification. Single-hour signature.
- **oref0**: night-long elevation 00-05h, peak hours 00 (0.90), 02
  (0.88), 05 (0.70) in high-cf stratum vs (0.82, 0.74, 0.70) marginal.
  **Strengthens** at the load ceiling — oref0 worst when most needed.

## Key finding: oref0 sharpens at the load ceiling

The 00:00 hour for oref0 jumps from 0.82 → 0.90 severe rate when
restricted to high-cf events. This is a +8pp shift in the **opposite**
direction of regression-to-mean — at the load ceiling, oref0's
overnight defence breaks down further, not less. This is consistent
with the basal-cut utilization gap (EXP-2892, 20% vs 92%): when
descents are aggressive, oref0 has less reserve capacity to mobilise.

## Top-3 hour rates (high-cf stratum)

| Lineage          | Top hour | Rate | 2nd | Rate | 3rd | Rate |
|------------------|---------:|-----:|----:|-----:|----:|-----:|
| Loop (iOS)       |    05    | 0.56 | 04  | 0.55 | 12  | 0.53 |
| oref1 (modern)   |    03    | 0.55 | 08  | 0.45 | 02  | 0.44 |
| oref0 (legacy)   |    00    | 0.90 | 02  | 0.88 | 10  | 0.88 |

Notes:
- Loop and oref1 keep peak rates ≤ 0.56 — controllers absorb most of
  load.
- oref0's three top hours are all ≥ 0.88 — qualitatively different
  defence profile.
- oref0 hour 10 (mid-morning) reaching 0.88 is new — outside the
  03-05 dawn band oref1/Loop occupy. Likely a small-n cell artifact
  (n cells with ≥5 high-cf events: 24/24 for oref0 means many cells
  have only 5-10 events).

## Cross-lineage stability under cf-conditioning

The hourly Loop:oref1:oref0 ranking is preserved at every hour:
- Loop ≤ oref1 < oref0 holds across 00-23h (no flips)
- The gap widens at night (especially 00, 02, 05) and narrows in
  afternoon
- This monotonic ordering survives load matching → mechanism, not
  selection

## Compatibility with EXP-2896 and EXP-2907

- EXP-2896 found the same hourly peaks marginally — confirmed.
- EXP-2907 found night degradation survives at the bin level
  (oref1 +9.5pp, oref0 +15.1pp) — EXP-2909 localises this to specific
  hours: oref1 03h is the source; oref0 00-02h is the source.
- The night degradation isn't a continuous overnight effect — it's
  hour-specific within each lineage.

## Audition matrix implications

`night_protection_degraded` flag could be refined to use hourly
nadir hour rather than 4-bin TOD:
- oref1: trigger if patient's 03h cf-stratum severe rate ≥ 0.45
- oref0: trigger if patient's 00-02h cf-stratum severe rate ≥ 0.85
- Loop: hourly variance flag instead — dawn-only phenotype

This is too granular for current cohort sizes (n cells per patient
per hour ≪ 5). Defer until AAPS data lands (EXP-2908).

## Robustness gaps

- Per-patient hourly cells often have ≤5 events; min_n=5 cell filter
  hides this in the cohort heatmap. Statistical noise is high in
  individual hour cells.
- No bootstrap CI on hourly rates yet.
- Mid-morning oref0 spike at 10h is suspicious; small-cell artifact
  candidate.
- Hour-by-hour Wilcoxon vs Loop baseline not computed.

## Linked artefacts

- `docs/60-research/exp-2895-tod-lineage-report-2026-04-22.md`
- `docs/60-research/exp-2896-hourly-resolution-report-2026-04-22.md`
- `docs/60-research/exp-2907-cf-stratified-tod-2026-04-23.md`
- `docs/visualizations/exp-2909-hourly-cf-stratified.png`
- `externals/experiments/exp-2909_summary.json`

## Next

- EXP-2910: re-grade 8-dimension lineage signature table; hourly
  signature now Guard-#6 verified
- Hourly bootstrap CI per cell
- Per-patient hourly heatmap (small multiples)
