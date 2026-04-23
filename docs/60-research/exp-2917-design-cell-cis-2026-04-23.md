# EXP-2917 — Bootstrap CIs for design-cell protection means

**Date:** 2026-04-23 (overnight)
**Source:** `tools/cgmencode/exp_design_cell_cis_2917.py`
**Scope:** Honest uncertainty quantification on EXP-2916 design-gap
claims. Design-level. NOT therapy advice.

## Method

Per (lineage, tercile) cell: percentile bootstrap of patient
means (5 000 resamples). For pairwise design gaps: independent
bootstrap of each cell, gap = mean_a − mean_b, 95 % CI from
gap distribution.

**Critical n=1 caveat:** for cells with one patient, the bootstrap
treats the single observation as the population and returns a
**zero-width CI**. This is not a real sampling-distribution CI;
it ignores between-patient variance. All oref0 cells are n=1.

## Cell CIs

| Lineage         | Tier         | n | Mean prot | 95 % CI            | CI possible |
|-----------------|--------------|--:|----------:|--------------------|-------------|
| Loop            | conservative | 2 | 0.486     | [0.453, 0.519]     | yes         |
| Loop            | moderate     | 2 | 0.637     | [0.635, 0.639]     | yes         |
| Loop            | aggressive   | 3 | 0.582     | [0.531, 0.648]     | yes         |
| oref0           | conservative | 1 | 0.125     | (n=1; no CI)       | **NO**      |
| oref0           | moderate     | 1 | 0.389     | (n=1; no CI)       | **NO**      |
| oref0           | aggressive   | 1 | 0.719     | (n=1; no CI)       | **NO**      |
| oref1           | conservative | 3 | 0.635     | [0.594, 0.702]     | yes         |
| oref1           | moderate     | 2 | 0.615     | [0.602, 0.628]     | yes         |
| oref1           | aggressive   | 4 | 0.719     | [0.619, 0.782]     | yes         |

The non-oref0 cells have CI widths of 0.004–0.16. Loop-conservative
[0.45, 0.52] and oref1-conservative [0.59, 0.70] are non-overlapping
— a meaningful design separation **independent of oref0 noise**.

## Pairwise design-gap CIs (sorted by |gap|)

| Tier         | A      | B      | Gap (A−B) | 95 % CI            | Sig | n_a, n_b |
|--------------|--------|--------|----------:|--------------------|-----|----------|
| conservative | oref0  | oref1  | −0.509    | [−0.576, −0.468]   | ★   | 1, 3 †   |
| conservative | Loop   | oref0  | +0.360    | [+0.327, +0.393]   | ★   | 2, 1 †   |
| moderate     | Loop   | oref0  | +0.248    | [+0.245, +0.250]   | ★   | 2, 1 †   |
| moderate     | oref0  | oref1  | −0.226    | [−0.238, −0.213]   | ★   | 1, 2 †   |
| **conservative** | **Loop** | **oref1** | **−0.149** | **[−0.218, −0.080]** | **★** | **2, 3** |
| aggressive   | Loop   | oref0  | −0.137    | [−0.188, −0.071]   | ★   | 3, 1 †   |
| **aggressive**   | **Loop** | **oref1** | **−0.136** | **[−0.228, −0.032]** | **★** | **3, 4** |
| **moderate**     | **Loop** | **oref1** | **+0.022** | **[+0.007, +0.037]** | **★** | **2, 2** |
| aggressive   | oref0  | oref1  | +0.001    | [−0.062, +0.100]   | n.s.| 1, 4 †   |

★ = 95 % CI excludes zero. † = involves an n=1 oref0 cell, so the
CI is artificially narrow (oref0 contributes zero sampling variance
to the bootstrap).

## Honest reporting after CI accounting

**Robustly significant design gaps** (BOTH cells n≥2, CI excludes zero):
- **oref1 > Loop at conservative:** +0.149, CI [+0.080, +0.218]
- **oref1 > Loop at aggressive:** +0.136, CI [+0.032, +0.228]
- **Loop > oref1 at moderate:** +0.022, CI [+0.007, +0.037] —
  small effect, narrow CI (n=2 vs n=2 with low variance both sides;
  treat with caution)

**Underpowered (n=1 oref0)** — point estimates only, NO inferential
claim:
- oref0_cons (0.125) is well below oref1_cons (0.635). The 0.51
  point gap is corroborated mechanistically by EXP-2892 / EXP-2918.
- oref0_mod (0.389) is below Loop_mod and oref1_mod by ~0.23.
- oref0_agg (0.719) is the EXP-2905 manual-SMB outlier; not
  representative.

## Implication for EXP-2916 design-gap report

- The "oref1 > Loop" claim at conservative and aggressive tiers
  now has honest CIs that exclude zero — **statistically robust**
  at this cohort size for those two cells.
- The "oref0 lags" claim is **point-estimate-only** and should
  always be stated alongside "n=1 per cell, mechanism corroborated
  by EXP-2892 utilization (20 %) and EXP-2918 latency (10 min)
  — the 3D mechanism stack is the evidence, not the protection
  point estimate alone".

## Methodological note for the toolkit

Add to deconfounding-toolkit §2.X (small-n caveat): when bootstrap
includes n=1 cells, the per-cell CI is degenerate (zero-width).
Paired comparisons against n=1 cells inherit only the multi-patient
side's variance. Reported CIs in such pairs are LOWER bounds on
true uncertainty. Always flag in tables.

## Caveats

- Bootstrap of patient means assumes patients within cell are
  exchangeable; doesn't model within-patient day variation.
- Cell sample sizes are 1–4 — bootstrap is informative but not a
  substitute for cohort expansion.
- AAPS data ingestion (EXP-2908) is the only path to widening
  oref-family base.

## Linked artefacts

- `externals/experiments/exp-2917_summary.json`
- `externals/experiments/exp-2917_design_cell_cis.parquet`
- `docs/60-research/exp-2916-design-gap-2026-04-23.md` (parent)

## Next

- Update EXP-2916 doc with link to honest-CI table
- AAPS data ingestion (per EXP-2908)
- Visualization: forest plot of design-gap CIs
