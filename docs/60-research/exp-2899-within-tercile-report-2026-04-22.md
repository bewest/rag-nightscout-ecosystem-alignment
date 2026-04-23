# EXP-2899 — within-lineage protection consistency report

**Date:** 2026-04-22 (overnight)
**N:** 19 patients across 3 known lineages
**Source:** `tools/cgmencode/exp_within_tercile_2899.py`
**Output:** `externals/experiments/exp-2899_summary.json`

## Question

Lineages differ in *mean* protection (EXP-2891). Do they also differ in
*consistency* — i.e., how much patient-to-patient variance exists at the
same lineage and aggressiveness?

## Result — two consistency tiers

| Lineage          | n | Median protection | Std   | Range       | Consistency score |
|------------------|--:|------------------:|------:|------------:|------------------:|
| **Loop (iOS)**   | 7 | 0.568             | 0.074 | 0.45 → 0.65 | **0.87**          |
| **oref1**        | 9 | 0.628             | 0.084 | 0.57 → 0.79 | **0.87**          |
| **oref0**        | 3 | 0.389             | 0.298 | 0.13 → 0.72 | **0.24**          |

`consistency_score = 1 − std / median`. Higher = tighter.

## Cell-level (lineage × tercile)

| Lineage          | Tercile      | n | Median | Range      |
|------------------|--------------|--:|-------:|-----------:|
| Loop             | conservative | 2 | 0.486  | 0.066      |
| Loop             | moderate     | 2 | 0.637  | **0.004**  |
| Loop             | aggressive   | 3 | 0.568  | 0.117      |
| oref1            | conservative | 3 | 0.608  | 0.108      |
| oref1            | moderate     | 2 | 0.615  | 0.025      |
| oref1            | aggressive   | 4 | 0.755  | 0.219      |
| oref0            | conservative | 1 | 0.125  | n/a        |
| oref0            | moderate     | 1 | 0.389  | n/a        |
| oref0            | aggressive   | 1 | 0.719  | n/a        |

## Interpretation

### Loop & oref1 normalise across users
Both modern lineages have consistency score 0.87. Within-tercile ranges
are small (0.004 to 0.22). Patients with similar settings get similar
outcomes — the algorithm absorbs configuration variance.

### oref0 amplifies user variability
Across-tercile range 0.13 → 0.72 (5.7× spread). The conservative oref0
patient gets protection 0.13; the aggressive one gets 0.72 — same
algorithm, different settings, dramatically different results.

This is the **fourth distinct lineage signature** discovered in this
arc:
1. EXP-2891: lineage affects mean protection
2. EXP-2892: lineage affects basal-cut utilization (capacity vs use)
3. EXP-2893: lineage affects SMB channel availability
4. **EXP-2899: lineage affects user-configuration sensitivity**

## Implications for therapy guidance

### For oref0 patients
Settings tuning has VERY large leverage. A conservative-→-aggressive
shift in basal/CR could move protection from 0.13 to 0.72. But this
also implies a high failure cost for under-tuning. Algorithm migration
to a less sensitive lineage de-risks the operating envelope.

### For Loop / oref1 patients
Settings tuning has modest leverage at the high end. The aggressive
oref1 cell tops out at 0.79 protection; further aggressiveness gains
diminishing returns. Within-cell variance gives a soft ceiling: even
the best-tuned conservative oref1 patient won't outperform the median
aggressive oref1 patient.

### Audition matrix v3 sketch
A new `lineage_amplifies_settings` flag could fire on:
- Lineage = oref0 AND patient_protection > cell_median + 1 std
  (over-performer; can be replicated)
- Lineage = oref0 AND patient_protection < cell_median - 1 std
  (under-performer; large headroom from settings tuning)
Wiring deferred until cohort grows beyond n=3 oref0.

## Caveats

- **n=3 for oref0** — within-tercile variance is undefined (n=1 per
  cell). The across-tercile spread is the signal but rests on a thin
  base.
- All n's are small; consistency-score differences are descriptive,
  not inferentially tested.
- Within-tercile variance for oref1 *does* grow at the aggressive end
  (range 0.22), suggesting some non-algorithm factors at the high end
  too. Possibly individual physiology takes over once basal/SMB are
  saturated.

## Linked artefacts

- `docs/60-research/exp-2891-simpson-dose-response-report-2026-04-22.md`
- `docs/60-research/exp-2892-mechanism-report-2026-04-22.md`
- `docs/60-research/exp-2893-hyper-channels-report-2026-04-22.md`
- `tools/cgmencode/exp_within_tercile_2899.py`

## Cumulative arc summary (EXP-2880-2899)

| Dimension                          | Strongest lineage    | Weakest lineage   |
|------------------------------------|---------------------|-------------------|
| Mean protection (EXP-2891)         | oref1               | oref0             |
| Setting-independence (EXP-2891)    | oref1               | oref0             |
| Basal-cut utilization (EXP-2892)   | oref1, Loop         | oref0             |
| SMB availability (EXP-2893/2894)   | oref1, Loop         | oref0             |
| TOD-invariance (EXP-2895)          | Loop                | oref0             |
| Hourly worst-case mitigation (2897)| oref1, Loop         | oref0             |
| Counter-reg moderation (EXP-2898)  | oref1, Loop         | oref0             |
| User-config consistency (EXP-2899) | Loop, oref1         | oref0             |

oref0 is now characterised across 8 dimensions as the lineage with
both the lowest mean performance AND the highest patient-to-patient
variance AND the strongest TOD degradation AND the longest mechanism
deficit list. The audition recommendation surface concentrates on
algorithm migration for these patients.

## Next experiments

- Migrate the AAPS gap from "data not available" to a sourcing plan;
  current oref-line claims rest on Trio + 3 OpenAPS patients.
- EXP-2900: per-patient protection profile vs lineage-tercile median
  (individual deviation index for triage).
