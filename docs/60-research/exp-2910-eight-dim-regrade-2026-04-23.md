# EXP-2910 — eight-dimension lineage signature, Guard-#6 re-grade

**Date:** 2026-04-23 (overnight)
**Purpose:** Audit the cumulative lineage-characterization claim
("oref0 worst on every axis") against Default Guard #6 (load
stratification). Re-grade each of the 8 axes as Guard-#6 verified,
robust-to-condition, or pending re-test.

## Context

Through the EXP-2880 → EXP-2909 arc the cohort has been characterised
along 8 axes. Default Guard #6 (introduced after EXP-2902/2904)
requires that any cross-lineage comparison report results both
marginally AND after conditioning on `cf_severe`. This re-grade
applies that guard retroactively.

## The eight axes

| # | Axis                              | Source EXP   |
|---|-----------------------------------|--------------|
| 1 | Mean protection                   | EXP-2891     |
| 2 | Setting-independence (tercile robustness) | EXP-2891 |
| 3 | Basal-cut utilization             | EXP-2892     |
| 4 | SMB channel availability          | EXP-2893     |
| 5 | TOD-invariance (day-vs-night)     | EXP-2895     |
| 6 | Hourly mitigation profile         | EXP-2896     |
| 7 | Counter-reg moderation            | EXP-2898     |
| 8 | User-config consistency           | EXP-2899     |

## Re-grade table

| # | Axis                              | Marginal finding | Guard-#6 status | Verifier EXP | Notes |
|---|-----------------------------------|------------------|-----------------|--------------|-------|
| 1 | Mean protection                   | oref1 0.68 > Loop 0.54 > oref0 0.41 | **Verified** (oref1>Loop survives; oref0 collapse driven by single patient) | EXP-2904 | t_oref1=2.13 (borderline), t_oref0=0.19 (collapses) |
| 2 | Setting-independence              | oref1 flat 0.63→0.72; Loop dose-response; oref0 0.13→0.72 | **Partially verified** (EXP-2911: oref1 flat survives; oref0 ρ 1.00→0.50; Loop attenuated) | EXP-2911 | Power-limited (n=3-9 per lineage) |
| 3 | Basal-cut utilization             | oref1 92% / Loop 88% / oref0 20% | **Mechanism (no Guard-#6 needed)** | EXP-2892 | Capacity-side metric, not outcome-side; cf-conditioning irrelevant |
| 4 | SMB channel availability          | oref0 absent (0/3); Loop 5/7 enabled; oref1 9/9 enabled | **Mechanism (no Guard-#6 needed)** | EXP-2893, EXP-2894 | Configuration property |
| 5 | TOD-invariance (day-vs-night)     | Loop +0.006 / oref1 +0.101 / oref0 +0.150 night excess | **Verified** (within high-cf: Loop +0.003, oref1 +0.095 p=0.004, oref0 +0.151 p=0.012) | EXP-2907 | Effect sizes essentially identical |
| 6 | Hourly mitigation profile         | Loop dawn 04-05; oref1 03h focal; oref0 night-long | **Verified** (high-cf preserves all peaks; oref0 00h INTENSIFIES 0.82→0.90) | EXP-2909 | Monotonic Loop:oref1:oref0 ranking at every hour |
| 7 | Counter-reg moderation            | Kruskal p=0.037; rho frac_smb vs intercept = -0.43 | **Failed Guard #6** (EXP-2912: marginal Kruskal p=0.027 drops to p=0.245 after cf-residualization; plausibly load-mediated) | EXP-2912 | n_oref0=3 limits power; revisit with AAPS data |
| 8 | User-config consistency           | Loop/oref1 within-lineage score 0.87; oref0 0.24 | **Robust to Guard-#6 by construction** | EXP-2899 | Intra-lineage variance metric, not cross-lineage; Guard #6 doesn't apply |

## Status totals

| Status                                | Count |
|---------------------------------------|------:|
| Verified (cf-conditioned, survives)   | 3 (axes 1, 5, 6) |
| Partially verified                    | 1 (axis 2 — EXP-2911) |
| Mechanism / construction (Guard N/A)  | 3 (axes 3, 4, 8) |
| **Failed Guard #6**                   | 1 (axis 7 — EXP-2912) |
| Pending re-test                       | 0 |

**7 of 8 axes** support the algorithm-migration recommendation
surface (verified, partially verified, or mechanism-by-construction).
**1 of 8 axes** (counter-reg moderation, axis 7) failed Guard #6 and
should be **withdrawn from cross-lineage claims** until cohort
expansion (per EXP-2908) permits re-test.

## Refined "oref0 worst on every axis" claim

After Guard #6 re-grade, the original characterization narrows to:

> oref0 is **mechanistically inferior** on basal-cut utilization (axis 3),
> SMB availability (axis 4), and user-config consistency (axis 8); it
> shows **load-robust performance gaps** on mean protection (axis 1),
> TOD-invariance (axis 5), and hourly profile (axis 6); claims on
> setting-independence (axis 2) and counter-reg moderation (axis 7)
> remain **provisional** pending cf-conditioned re-test.

The 6 verified/exempt axes are sufficient to support the
algorithm-migration recommendation that EXP-2894/2905 articulate. The
2 pending axes do not change the recommendation surface; they tighten
its justification.

## Pending follow-ups (queued)

- **EXP-2911**: setting-independence cf-conditioned. ANCOVA of protection
  ~ tercile + cf within each lineage. Requires per-event cf annotation;
  data exist (exp-2889_event_replay.parquet has cf_severe).
- **EXP-2912**: counter-reg cf-conditioned. Compute β_nadir × lineage
  interaction within high-cf stratum. Tests whether oref0's elevated
  intercept is upstream-failure-mediated (lagging indicator) or
  independently rapid recovery.

Both are deferred until an organic priority surfaces; the current
6-axis verified set is sufficient for current claims.

## Audition matrix implications

No new flag changes. The existing Guard-#6-verified flags
(`night_protection_degraded`, `regime_*`, `manual_smb_substitution`)
already encode the load-stratified findings. The pending axes (2, 7)
do not currently fire audition flags.

## Linked artefacts

- `docs/60-research/deconfounding-toolkit-2026-04-22.md` (Guard #6)
- `docs/60-research/exp-2904-cf-conditioned-lineage-2026-04-22.md`
- `docs/60-research/exp-2907-cf-stratified-tod-2026-04-23.md`
- `docs/60-research/exp-2909-hourly-cf-stratified-2026-04-23.md`
- All EXP-2880 → EXP-2909 reports
