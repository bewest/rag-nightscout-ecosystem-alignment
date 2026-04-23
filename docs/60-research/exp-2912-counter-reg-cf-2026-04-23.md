# EXP-2912 — cf-conditioned counter-reg moderation (axis 7 re-grade)

**Date:** 2026-04-23 (overnight)
**Source:** `tools/cgmencode/exp_counter_reg_cf_2912.py`
**Purpose:** Re-grade EXP-2898 counter-regulation lineage finding
under Default Guard #6 (cf-conditioning).

## Headline (axis 7 fails Guard #6)

The lineage effect on counter-reg intercept **does not survive
cf-conditioning**:

| Test                              | H    | p      |
|-----------------------------------|-----:|-------:|
| Marginal Kruskal-Wallis           | 7.22 | 0.027  |
| Cf-residualized Kruskal-Wallis    | 2.82 | 0.245  |

The marginal "lineage matters for counter-reg" claim (EXP-2898
p=0.037) **drops below significance** once cf is partialled out.
oref0's elevated intercept is consistent with being entirely
load-mediated.

## Per-lineage residuals (after cf-residualization)

| Lineage          | n | Mean intercept resid | Std    |
|------------------|--:|---------------------:|-------:|
| Loop (iOS)       | 7 | -0.16                | 0.62   |
| oref1 (modern)   | 9 | -0.26                | 0.79   |
| oref0 (legacy)   | 3 | +1.15                | 1.43   |

oref0 still has the highest residual (+1.15), but the within-group
variance (1.43) is wider than the cross-group difference. With n=3
this fails any reasonable significance threshold.

## Surprising sub-finding: ρ(cf, intercept) is NEGATIVE in Loop/oref1

| Lineage          | n | ρ(cf, intercept) | p    |
|------------------|--:|-----------------:|-----:|
| Loop (iOS)       | 7 | -0.56            | 0.20 |
| oref1 (modern)   | 9 | -0.20            | 0.60 |
| oref0 (legacy)   | 3 | +0.50            | 0.67 |

For Loop and oref1, **patients with higher load have LOWER counter-reg
intercept** (slower rebound). This is counterintuitive — one might
expect harder events to provoke faster physiological rebound. Possible
mechanisms:
- Selection effect: aggressive Loop/oref1 patients with high load
  also have richer hypoglycemia experience → blunted counter-reg
  (HAAF-adjacent, c.f. EXP-2878)
- Survivorship: events that reach low-cf nadir without becoming severe
  may have larger physiological excursions
- Sample noise — none of the per-lineage ρ values reach significance

oref0 shows the opposite (+0.50) but n=3 makes it useless.

## ρ(protection, intercept) per lineage

| Lineage          | n | ρ      | p    |
|------------------|--:|-------:|-----:|
| Loop (iOS)       | 7 | -0.25  | 0.59 |
| oref1 (modern)   | 9 | -0.37  | 0.33 |
| oref0 (legacy)   | 3 | +0.50  | 0.67 |

EXP-2898's cohort-wide ρ(frac_smb, intercept) = -0.43 was framed as
"rapid recovery is a LAGGING indicator of upstream AID failure."
At per-lineage resolution (Loop ρ=-0.25, oref1 ρ=-0.37) the
direction is consistent but each individually fails significance.

The cohort-wide ρ was driven partly by lineage being a confounder:
oref0 patients have low frac_smb AND elevated intercept (driven by
their higher cf), inflating the negative correlation.

## Implications

### Axis 7 fails Guard #6
The narrative "oref0 patients have rapid hypo recovery" cannot be
maintained as an independent algorithm signature. It is more
parsimoniously explained as load-mediated: oref0 cohort experiences
more severe events (higher cf), and severe events provoke larger
counter-regulatory rebound.

### EXP-2898's "lagging indicator" framing requires revision
The "rapid recovery as lagging indicator of upstream failure" insight
**survives at the cohort level** as a directional pattern, but the
mechanism is ambiguous between:
- Algorithm-mediated (oref0 fails upstream → physiology rebounds harder)
- Load-mediated (oref0 cohort has harder events → more rebound)
- A combination

These cannot be separated with current cohort sizes.

### Audition matrix implications
The `counter_reg_*` flags from EXP-2876 (impaired/preserved) are
**event-level physiology metrics**, not cross-lineage comparisons.
They remain valid as triage signals — they just don't carry
algorithm-attribution power.

## Updates to 8-dim re-grade table (EXP-2910)

Axis 7 (counter-reg moderation):
- Was: **Pending**
- Now: **Failed Guard #6** — lineage Kruskal p=0.027 marginal drops
  to p=0.245 after cf-residualization. Effect is plausibly entirely
  load-mediated.

## Power caveat

oref0 n=3 dominates uncertainty in this analysis. With more oref0
patients (per EXP-2908 plan), this could be re-tested at higher power.
The current null result should not be over-interpreted.

## Linked artefacts

- `docs/60-research/exp-2898-counter-reg-by-lineage-2026-04-22.md`
- `docs/60-research/exp-2910-eight-dim-regrade-2026-04-23.md`
- `externals/experiments/exp-2912_summary.json`

## Next

- Update EXP-2910 axis 7 status: Pending → **Failed Guard #6**
- Update lineage characterization narrative: 6 verified + 1 partially
  verified + 1 failed = 7 of 8 axes still inform the algorithm-migration
  recommendation; axis 7 (counter-reg) deferred from cross-lineage claims
- Consider EXP-2913: re-test once AAPS data lands (per EXP-2908)
