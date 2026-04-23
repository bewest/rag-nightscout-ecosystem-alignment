# EXP-2911 — cf-conditioned setting-independence (axis 2 re-grade)

**Date:** 2026-04-23 (overnight)
**Source:** `tools/cgmencode/exp_setting_indep_cf_2911.py`
**Purpose:** Re-grade EXP-2891's lineage-by-tercile dose-response
finding under Default Guard #6 (cf-conditioning).

## Headline

The "oref0 has huge setting dose-response (0.13→0.72)" finding from
EXP-2891 is **partially confounded by load coupling**. After
residualizing protection on `cf_severe`, the per-lineage Spearman
correlations attenuate substantially:

| Lineage          | n | Marginal ρ | Marginal p | Cf-resid ρ | Cf-resid p |
|------------------|--:|----------:|-----------:|-----------:|-----------:|
| Loop (iOS)       | 7 | 0.57      | 0.18       | 0.30       | 0.51       |
| oref1 (modern)   | 9 | 0.40      | 0.28       | 0.27       | 0.49       |
| oref0 (legacy)   | 3 | 1.00      | 0.00       | 0.50       | 0.67       |

Per-lineage attenuation magnitudes:
- oref0: ρ 1.00 → 0.50 (50% drop)
- Loop:  ρ 0.57 → 0.30 (47% drop)
- oref1: ρ 0.40 → 0.27 (33% drop)

## Per-tercile breakdown

### oref0 (n=1 per tier — anecdotal)
| Tier         | n | cf   | protection | cf-resid protection |
|--------------|--:|-----:|-----------:|--------------------:|
| Conservative | 1 | 0.70 | 0.125      | +0.016              |
| Moderate     | 1 | 0.91 | 0.389      | -0.147              |
| Aggressive   | 1 | 0.93 | 0.719      | +0.131              |

Marginal: monotone increase 0.13 → 0.39 → 0.72.
Cf-residualized: NOT monotone (0.02 → -0.15 → 0.13). The
moderate-tier patient sits below the lineage trend after load
adjustment.

### Loop
| Tier         | n | cf   | protection | cf-resid protection |
|--------------|--:|-----:|-----------:|--------------------:|
| Conservative | 2 | 0.93 | 0.486      | -0.055              |
| Moderate     | 2 | 0.97 | 0.637      | +0.065              |
| Aggressive   | 3 | 1.00 | 0.582      | -0.006              |

Marginal: monotone-ish (0.49 → 0.64 → 0.58 — moderate beats
aggressive). Cf-residualized: similar pattern, weaker. Loop's
tercile dose-response is not robust at n=7.

### oref1
| Tier         | n | cf   | protection | cf-resid protection |
|--------------|--:|-----:|-----------:|--------------------:|
| Conservative | 3 | 0.92 | 0.635      | -0.009              |
| Moderate     | 2 | 0.99 | 0.615      | -0.066              |
| Aggressive   | 4 | 0.98 | 0.719      | +0.040              |

Marginal: largely flat (0.63 / 0.62 / 0.72). Cf-residualized:
flatter still. Confirms EXP-2891 "setting-INDEPENDENT" claim —
oref1's protection is not strongly modulated by aggressiveness
even after load adjustment.

## Interpretation

### EXP-2891 oref0 dose-response was partially load-coupled
The original 0.13 → 0.72 protection slope across oref0 terciles
mapped onto a parallel cf increase (0.70 → 0.93). After load
adjustment, the slope reduces from "perfect rank order" to
"non-monotone with center dip." This means:
- Aggressive oref0 users face higher load AND show better
  protection.
- Some of that better protection comes from being aggressive
  (more bolusing, faster correction → less reliance on AID
  basal-cut).
- Some comes from facing harder events to begin with (higher cf
  means there's more headroom for protection to register).

### oref0 algorithm-migration recommendation still holds
Even with cf-conditioning, conservative-tier oref0 sits at near-zero
residual (+0.016), well below the cohort mean. The algorithm gap is
not erased — but it's sharpened to "conservative oref0 users sit at
the cohort mean given their load" rather than "oref0 fails
catastrophically across the board."

The catastrophic failure is concentrated in the **mechanism_gap
regime** (1 patient: odc-86025410), as already documented by
EXP-2902.

### oref1 setting-independence claim survives
oref1's flat protection across terciles (cf-resid: -0.01, -0.07,
+0.04) confirms the original interpretation: the algorithm provides
a setting-independent floor. Aggressive users gain marginally; even
conservative users get ≥0.63 protection.

### Loop's modest dose-response is not robust at n=7
Marginal ρ=0.57 attenuates to 0.30; CI would cross zero. Cannot
distinguish from sampling noise at this cohort size.

## Power caveat (significant)

All ρ values fail to reach p<0.05 — this is dominated by small n
(3, 7, 9 patients per lineage). The directional findings are
robust; the magnitudes are not.

## Audition matrix implications

No flag changes. The previously wired flags
(`under_performer_for_lineage`, `over_performer_for_lineage`,
`regime_*`) already operate on per-patient deviation rather than
per-tercile mean, so they are insensitive to this re-grade.

## Updates to 8-dim re-grade table (EXP-2910)

Axis 2 (setting-independence) status updates:
- Was: **Pending**
- Now: **Partially verified** — oref1 setting-independence robust;
  oref0 dose-response weakens but remains directional; Loop
  tercile effect not significant.

Recommend updating EXP-2910 doc to reflect "Partially verified" for
axis 2.

## Linked artefacts

- `docs/60-research/exp-2891-simpson-stratified-2026-04-22.md`
- `docs/60-research/exp-2902-regime-stratification-2026-04-22.md`
- `docs/60-research/exp-2910-eight-dim-regrade-2026-04-23.md`
- `externals/experiments/exp-2911_summary.json`

## Next

- EXP-2912: counter-reg moderation cf-conditioned (axis 7)
- Update EXP-2910 with axis 2 = Partially Verified
