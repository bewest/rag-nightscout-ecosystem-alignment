# EXP-2904 — cf-conditioned lineage protection comparison

**Date:** 2026-04-22 (overnight)
**N:** 19 patients
**Source:** `tools/cgmencode/exp_cf_conditioned_lineage_2904.py`
**Purpose:** Test whether the EXP-2891 lineage protection effect survives
conditioning on `cf_severe`, after EXP-2902 revealed 42% of cohort is
load-saturated and Loop is concentrated there.

## Headline

The lineage effect **partially attenuates** when cf is controlled for.
A residual oref1 > Loop signal persists; the oref0 contribution becomes
indistinguishable from noise (small-n limitation, not a real
disappearance).

## Statistical results

| Test                                         | Statistic           | p-value |
|----------------------------------------------|---------------------|---------|
| Raw Kruskal (lineage, all n=19)              | H = 4.06            | 0.131   |
| Kruskal within high-cf stratum (n=11)        | H = 2.70            | 0.100   |
| Kruskal within low-cf stratum (n=8)          | H = 1.36            | 0.506   |
| Stratified permutation (lineage spread)      | spread = 0.238      | 0.123   |
| **ANCOVA: oref1 vs Loop (base) coefficient** | **t = 2.13**        | **~0.05** |
| ANCOVA: oref0 vs Loop coefficient            | t = 0.19            | 0.85    |
| ANCOVA: cf_severe coefficient                | t = 3.52            | <0.01   |
| ANCOVA r²                                    | 0.652               |         |

(ANCOVA n=19, df_resid=15, two-sided p approximation.)

## Lineage medians by cf stratum

| cf stratum | Lineage         | n | Median protection | Std    |
|------------|-----------------|--:|------------------:|-------:|
| high (≥0.95) | Loop (iOS)    | 5 | 0.568             | 0.059  |
| high (≥0.95) | oref1 (modern)| 6 | **0.665**         | 0.089  |
| low (<0.95)  | Loop (iOS)    | 2 | 0.546             | 0.132  |
| low (<0.95)  | oref0 (legacy)| 3 | 0.389             | 0.298  |
| low (<0.95)  | oref1 (modern)| 3 | 0.608             | 0.087  |

oref1 leads Loop by 0.097 in the high-cf stratum and 0.062 in the low-cf
stratum. The advantage is present in both regimes, but n is small and
within-stratum Kruskal does not reach α=0.05.

## Interpretation

### Reframing the EXP-2891 finding
EXP-2891 reported a robust lineage effect (perm p=0.018; ANCOVA
Kruskal p=0.034). The current re-test, with `cf_severe` as a covariate
and stratifier, shows:

- **cf_severe is the strongest predictor** (ANCOVA t=3.52 vs
  oref1-vs-Loop t=2.13). Roughly two-thirds of variance in protection
  is explained by load and lineage together; cf carries the larger
  share.
- **oref1 vs Loop still has independent positive coefficient** (t=2.13,
  borderline) → the modern-oref algorithm advantage is *consistent*
  with mechanism, not purely behavioural. With n=19 we cannot prove it
  robustly, but the direction and effect size match prior arc results.
- **oref0 vs Loop coefficient collapses** (t=0.19). With only 3 oref0
  patients (1 in mechanism_gap, 1 in moderate, 1 in defended), the raw
  EXP-2891 oref0-vs-Loop gap was likely driven by `odc-86025410`
  (protection 0.13) — a single patient. cf-conditioning effectively
  removes that influence.

### What the strata tell us individually
- **High-cf stratum**: 5 Loop + 6 oref1 + 0 oref0. Within this load
  ceiling, oref1 protection median (0.665) exceeds Loop's (0.568) by
  0.097 — and Loop tops out at 0.65 while oref1 tops out at 0.79.
  This is the cleanest mechanism-level comparison the dataset
  supports.
- **Low-cf stratum**: only 8 patients. Lineage spread is dominated by
  the single conservative-oref0 patient. Removing that patient: Loop
  0.55, oref1 0.61 — same ~0.06 gap as high-cf stratum.

### Methodological invariant (carry forward)
**Cross-lineage protection comparisons require cf-conditioning** to
separate algorithm capability from load-intensity self-selection. The
oref1>Loop effect appears robust to this; the oref0<Loop effect was
small-n driven and should not be over-claimed.

## Audition matrix implications

- The `algorithm_lineage` field should remain as a recommendation
  surface input, but lineage-tercile thresholds (e.g.
  `night_protection_degraded`) should be re-derived from cf-stratified
  pools when the cohort grows.
- The 8-dimension lineage signature table (EXP-2899 report) overstates
  the oref0 vs Loop gap for any dimension that loads on cf. Affected:
  mean protection, hourly mitigation, possibly setting-independence.

## Robustness gaps

- n=19 underpowers within-stratum Kruskal even at large effect sizes
  (~0.10 protection units). Need cohort 3-5× larger for definitive
  cf-conditioned lineage tests.
- Low-cf stratum has only 8 patients across 3 lineages.
- ANCOVA assumes linearity; protection has a 0-1 ceiling. Logit
  transform sensitivity not explored.
- Patient-level aggregation only; no per-event hierarchical model.

## Action items

1. **Update EXP-2891 / EXP-2899 reports** with addendum referencing
   EXP-2904's attenuation finding. Specifically annotate that the
   oref0 contribution to lineage spread is dominated by 1 patient and
   that oref1>Loop is the more robust comparison.
2. **Sourcing plan for AAPS / additional oref0 patients** elevated in
   priority — current n=3 oref0 cannot support definitive lineage
   claims.
3. **Future cross-lineage experiments** must report stratified results
   alongside marginal ones (deconfounding-toolkit Default Guard #6,
   draft).

## Linked artefacts

- `docs/60-research/exp-2891-simpson-dose-response-report-2026-04-22.md`
- `docs/60-research/exp-2902-regime-stratification-2026-04-22.md`
- `docs/60-research/deconfounding-toolkit-2026-04-22.md`
- `tools/cgmencode/exp_cf_conditioned_lineage_2904.py`
- `externals/experiments/exp-2904_summary.json`
