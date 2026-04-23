# EXP-2916 — Algorithm-migration counterfactual delta

**Date:** 2026-04-23 (overnight)
**Source:** `tools/cgmencode/exp_migration_delta_2916.py`
**Purpose:** Translate Guard-#6-verified lineage signatures into
per-patient actionable recommendations: would migration to a different
algorithm reduce expected severe events?

## Method (one paragraph)

For each patient `p` with own (lineage, tercile, cf_severe,
own_protection), look up the cell-mean protection in alternative
lineages at the same tercile. Compute `expected_severe_rate_drop =
(alt_protection − own_protection) × cf_severe`. Positive drop means
migration would reduce severe rate; threshold 0.05 = 5pp drop.

## Headline

**8 of 19 patients (42%) cross the 5pp migration threshold.**

| Own lineage     | n | Recommend migrate | Mean expected drop |
|-----------------|--:|------------------:|-------------------:|
| oref0 (legacy)  | 3 | 2 (67%)           | +0.194             |
| Loop (iOS)      | 7 | 5 (71%)           | +0.091             |
| oref1 (modern)  | 9 | 1 (11%)           | -0.041             |

Direction matches Guard-#6 verified ranking: oref1 is at the surface,
Loop and oref0 have room to gain via migration.

## Top 5 recommendations

| Patient        | Own lineage     | Tier         | Own prot | Best alt lineage | Drop  |
|----------------|-----------------|--------------|---------:|------------------|------:|
| odc-86025410   | oref0           | conservative | 0.125    | oref1            | +0.36 |
| odc-96254963   | oref0           | moderate     | 0.389    | Loop             | +0.22 |
| i              | Loop            | aggressive   | 0.531    | oref0            | +0.19 |
| a              | Loop            | conservative | 0.453    | oref1            | +0.16 |
| c              | Loop            | aggressive   | 0.568    | oref0            | +0.15 |

### Highest-conviction recommendation: odc-86025410
The mechanism_gap regime patient (EXP-2902) — currently 12.5% severe
protection on oref0 conservative. Cohort oref1 conservative cell mean
is 63.5%. Migration projection: severe rate drops from 0.62 to 0.27,
a 56% relative reduction. This is the patient most likely to benefit
from an algorithm change.

### Caveat: oref0-aggressive cell drives some recommendations
Patients `i` and `c` are recommended to migrate **TO oref0**, driven by
the n=1 oref0 aggressive cell mean (0.72 — odc-74077367, the
over_performer_at_load patient). This is a single-patient artifact:
odc-74077367's high protection comes from manual SMB substitution
(EXP-2905), not the oref0 algorithm itself.

**Action:** flag oref0 aggressive cell as low-confidence; do not
recommend migration TO oref0 from this experiment without manual
review.

## Bottom 5 (would lose protection if migrated)

| Patient          | Own lineage | Tier        | Best alt | Drop   |
|------------------|-------------|-------------|----------|-------:|
| ns-1ccae8a375b9  | oref1       | aggressive  | oref0    | -0.040 |
| ns-8b3c1b50793c  | oref1       | aggressive  | oref0    | (similar) |
| ns-d444c120c23a  | oref1       | aggressive  | oref0    | (similar) |
| ns-a9ce2317bead  | oref1       | moderate    | Loop     | (similar) |
| ns-adde5f4af7ca  | oref1       | moderate    | Loop     | (similar) |

All five are oref1 patients near or above their lineage cell mean —
they are already on the verified-best algorithm at their cf-stratum.

## Recommendation surface (Loop → oref1 / oref0)

Loop's 5 recommend-migrate patients break down:
- 2 conservative → oref1 (cell mean 0.63 vs Loop 0.49)
- 1 moderate → oref1 (cell mean 0.62 vs Loop 0.64) — borderline
- 2 aggressive → oref0 (driven by n=1 oref0 cell, see caveat)

After excluding the oref0 artifact recommendations, the robust
recommendation surface is **3 Loop patients → oref1 migration** at
expected drops of 0.10–0.16. Plus the 2 oref0 patients with high
expected gains.

## Limitations and next steps

- Per-cell n=1-4 — point estimates only. Bootstrap CI deferred until
  EXP-2917.
- Does not model migration cost (config burden, hardware swap,
  learning curve, family/HCP support).
- Cell means do not account for within-cell heterogeneity (one
  outlier patient can swing the mean substantially).
- Assumes migration-time protection equals current cohort mean, i.e.
  no individual adaptation period.
- oref0 cells should not be used as migration targets for low-cf
  patients — this would over-extrapolate from n=1 cells.

## Audition matrix implications

Suggest new flag `algorithm_migration_candidate` (severity HIGH if
expected drop ≥ 0.20; MEDIUM if ≥ 0.10):
- HIGH triggers: odc-86025410, odc-96254963 (both oref0)
- MEDIUM triggers: 4 patients (3 Loop → oref1, 1 oref0 patient)

This flag should be paired with the existing `regime_mechanism_gap`
and `regime_load_saturation` flags for context.

Wiring deferred to next experiment (treat the recommendation as
advisory until cell-CIs are added).

## Linked artefacts

- `docs/60-research/exp-2891-simpson-stratified-2026-04-22.md`
- `docs/60-research/exp-2902-regime-stratification-2026-04-22.md`
- `docs/60-research/exp-2904-cf-conditioned-lineage-2026-04-22.md`
- `docs/60-research/exp-2905-vignette-overperformer-aggressive-oref0-2026-04-23.md`
- `docs/60-research/exp-2910-eight-dim-regrade-2026-04-23.md`
- `externals/experiments/exp-2916_summary.json`
- `externals/experiments/exp-2916_migration_delta.parquet`

## Next

- EXP-2917: bootstrap cell-CIs, refine recommendations
- EXP-2918: basal-cut latency by lineage (mechanism deepening)
- EXP-2913: HAAF blunting investigation
