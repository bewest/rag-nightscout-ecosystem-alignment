# EXP-2918 — Basal-cut latency by controller design

**Date:** 2026-04-23 (overnight)
**Source:** `tools/cgmencode/exp_basal_latency_2918.py`
**Scope:** Same as EXP-2916 — head-to-head AID controller-design
characterisation for open-source AID author audiences. NOT therapy
advice. Per binding scope statement
(`docs/60-research/exp-2916-design-gap-2026-04-23.md`).

## Question

EXP-2892 showed **utilisation** of basal-cut differs by lineage
(oref0 20 % vs oref1 92 %). EXP-2918 asks the orthogonal **temporal**
question: when a deep cut DOES occur, how quickly does each design
deliver it after descent onset?

## Method (one paragraph)

Walk the 5-min unified grid (`externals/ns-parquet/training/grid.parquet`)
per patient. A descent episode begins when the 30-min rolling
glucose slope drops below −0.5 mg/dL/min while glucose is in the
60–150 range and decreasing vs 30 min prior. From the onset cell,
search forward up to 180 min for the first 5-min cell where
`net_basal` falls below the patient-specific p10 (a normalized
"deep cut" threshold that avoids needing absolute scheduled basal).
Latency = minutes between onset and first deep cut. Patients merged
with EXP-2891 lineage; unknown-lineage patients excluded.

## Headline

| Design        | n events | Median latency | Mean latency | IQR (min) |
|---------------|---------:|---------------:|-------------:|-----------|
| oref1 (modern)| 5 337    | **0 min**      | 17.2 min     | 0–0       |
| Loop (iOS)    | 3 988    | **0 min**      | 23.8 min     | 0–20      |
| oref0 (legacy)| 2 497    | **10 min**     | 27.5 min     | 0–30      |

oref1 is fastest (median + tightest IQR). Loop is fast in median but
has a longer-tailed mean. **oref0 is the only design with a non-zero
median latency** — when it does cut, it cuts late.

## Per-tier breakdown (cf-stratification proxy)

The slow oref0 latency is concentrated where the protection gap is
worst:

| Patient            | Lineage | Tier         | Median lat | Response rate | Notes                        |
|--------------------|---------|--------------|-----------:|--------------:|------------------------------|
| odc-86025410       | oref0   | conservative | 10 min     | 56.7 %        | mechanism_gap (EXP-2902)     |
| odc-96254963       | oref0   | moderate     | 0 min      | 80.5 %        | average performer            |
| odc-74077367       | oref0   | aggressive   | 25 min     | 70.7 %        | manual-SMB outlier (EXP-2905); relies on bolus, not basal |

The mechanism_gap patient now has THREE corroborated dimensions of
the same design failure:
1. EXP-2892: utilisation 20 % (when does it cut)
2. EXP-2916: design gap exposure 0.36 (how big the protection gap is)
3. EXP-2918: latency 10 min (how fast when it does cut)

This is the cleanest mechanism stack we have for any phenotype.

## Loop heterogeneity matches EXP-2894

| Patient | Tier         | Latency | Response rate | EXP-2894 cohort |
|---------|--------------|--------:|--------------:|-----------------|
| f       | moderate     | 0 min   | 98.9 %        | auto-bolus on   |
| g       | moderate     | 0 min   | 85.1 %        | auto-bolus on   |
| i       | aggressive   | 0 min   | 63.8 %        | auto-bolus on   |
| a       | conservative | 0 min   | 44.7 %        | (need lookup)   |
| c       | aggressive   | 5 min   | 43.1 %        | (need lookup)   |
| e       | aggressive   | 15 min  | 35.4 %        | (need lookup)   |
| d       | conservative | 0 min   | 27.5 %        | (need lookup)   |

Latency is fast across Loop, but **response rate** varies from
27 % to 99 % — consistent with the EXP-2894 finding that Loop's
auto-bolus (and basal-cut policy) is configurable per user.
Triage value of latency alone is low for Loop; combine with
response_rate for design-level interpretation.

## oref1 outliers

- ns-d444c120c23a (load_saturation under-performer, EXP-2902): only
  24 % response rate. Latency is 0 when it does cut, but the design
  is not engaging the cut on most descents. Already mechanistically
  explained by load saturation (cf=1.00).
- ns-dde9e7c2e752: 100 % response rate, 0 min latency — the oref1
  ceiling case.

## Design-level interpretation (binding framing)

For open-source AID authors:

- **oref1 design:** sets the temporal ceiling. Deep cut typically
  arrives within the first 5-min cell after descent onset.
- **Loop design:** equally fast in median, but more spread; some
  patient configurations leave deep cuts unfired in 60–70 % of
  episodes.
- **oref0 design:** the only design with a non-zero median latency.
  Combined with EXP-2892 (low utilisation), this characterises the
  oref0 basal-cut path as both **less likely to fire** and **slower
  when it does**. Mechanistically points to the same code path
  (basal-cut decision policy) as the candidate gap to close.

## Caveats

- p10 of net_basal is a patient-normalized threshold; absolute
  cut depth differs by patient pump scheduled rate. Latency is
  therefore comparable across patients but absolute deep-cut
  magnitude is not.
- All three oref0 cells are n=1 (per EXP-2916 caveat). The
  design-level oref0 numbers reflect three case studies.
- Episodes may overlap with meal recovery; no meal-filter applied.
  Adding meal-window exclusion would refine but is unlikely to
  flip the lineage ranking.
- Latency does not capture cut DEPTH or DURATION — only first-cut
  timing.

## Audition matrix implications

No new patient-level flags. Latency is a design-level diagnostic.
The mechanism deepening is added to existing flag explanations
(`regime_mechanism_gap`, `lax_braking_controller_efficacy`).

## Linked artefacts

- `externals/experiments/exp-2918_summary.json`
- `externals/experiments/exp-2918_basal_cut_latency.parquet`
- `docs/60-research/exp-2892-hypo-mechanism-decomposition-2026-04-22.md` (companion)
- `docs/60-research/exp-2894-loop-autobolus-2026-04-22.md` (Loop heterogeneity context)
- `docs/60-research/exp-2916-design-gap-2026-04-23.md` (binding scope statement)

## Next

- EXP-2913: HAAF-adjacent blunting investigation (per plan)
- EXP-2917: bootstrap CIs for design-level cell means
- AAPS data ingestion (EXP-2908) — only path to widening oref-family base
