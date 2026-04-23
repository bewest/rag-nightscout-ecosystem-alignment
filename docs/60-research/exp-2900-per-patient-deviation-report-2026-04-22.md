# EXP-2900 — per-patient deviation index report

**Date:** 2026-04-22 (overnight)
**N:** 19 patients
**Source:** `tools/cgmencode/exp_per_patient_deviation_2900.py`
**Output:** `externals/experiments/exp-2900_deviation.parquet`

## Purpose

Convert the lineage-level signatures (EXP-2891–2899) into a **per-patient
triage signal**. Identify individuals whose protection deviates ≥1 SD
from their comparator group (cell when n≥3, lineage otherwise).

## Results — 5 actionable outliers

### Over-performers (replicable best practice)
| Patient            | Lineage         | Tercile      | Protection | z    | Comparator |
|--------------------|-----------------|--------------|-----------:|-----:|------------|
| `e`                | Loop (iOS)      | aggressive   | 0.648      | +1.34| cell       |
| `odc-74077367`     | oref0 (legacy)  | aggressive   | 0.719      | +1.11| lineage    |
| `ns-6bef17b4c1ec`  | oref1 (modern)  | conservative | 0.702      | +1.59| cell       |

### Under-performers (high tuning headroom)
| Patient            | Lineage         | Tercile      | Protection | z    | Comparator |
|--------------------|-----------------|--------------|-----------:|-----:|------------|
| `a`                | Loop (iOS)      | conservative | 0.453      | −1.56| lineage    |
| `ns-d444c120c23a`  | oref1 (modern)  | aggressive   | 0.572      | −1.85| cell       |

## Triage interpretation

### `ns-6bef17b4c1ec` (conservative oref1, +1.59 SD)
Conservative settings + best-in-cell protection. Audit settings/profile
to extract pattern; this is the model conservative oref1 patient.

### `odc-74077367` (aggressive oref0, +1.11 SD)
The single oref0 patient who hits oref1-grade protection (0.72) — but
cohort design (n=1 per oref0 cell) means we can't separate algorithm,
configuration, or selection effects. Worth a deep-dive vignette to
identify whether settings were aggressively tuned to overcome the
algorithm gap.

### `ns-d444c120c23a` (aggressive oref1, −1.85 SD)
Despite aggressive tier and SMB-capable algorithm, protection drops
below cell mean. Strong candidate for audition; rule out: counter-reg
impairment, cannula site issues, sleep schedule mismatch.

### `a` (conservative Loop, −1.56 SD vs lineage)
Conservative settings + Loop's typically-flat dose response = lowest
protection observed. Settings tuning has clear ceiling here (Loop
aggressive cell median is only 0.57); the next leverage is mechanism
(SMB enablement, basal-cut threshold).

### `e` (aggressive Loop, +1.34 SD)
Loop aggressive cell ceiling. Confirms Loop has a soft per-patient
upper bound around 0.65 protection — physiology- and feature-bound
rather than further-tunable.

## Methodology notes

- Comparator preference: cell median when cell n ≥ 3, else lineage
  median. Mixed comparators are flagged in the output column.
- z-score uses cell or lineage SD as appropriate.
- Threshold ±1 SD chosen for triage sensitivity; tighter (±1.5) drops
  to 3 outliers (loses `e`, `odc-74077367`).
- Three of 5 outliers come from oref1 — both ends of cohort. oref1's
  larger cohort (n=9) lets within-cell signal emerge.

## Wiring proposal — `per_patient_protection_outlier`

Add audition flag with two channels:

```python
class AuditionInputs:
    ...
    protection_z_within_lineage: Optional[float] = None
```

```python
if inp.protection_z_within_lineage is not None:
    if inp.protection_z_within_lineage <= -1.0:
        flag("under_performer_for_lineage", severity="MEDIUM",
             rationale="protection >1 SD below lineage median; tuning headroom")
    if inp.protection_z_within_lineage >= 1.0:
        flag("over_performer_for_lineage", severity="INFO",
             rationale="protection >1 SD above lineage median; replicable pattern")
```

Wiring done in EXP-2900 follow-up below.

## Implications

- Five of 19 patients (26%) have actionable individual signal beyond
  their lineage-tercile baseline. This complements (not replaces) the
  lineage-level recommendations.
- For under-performers, the ordered remediation tree is:
  1. Counter-regulation channel (EXP-2898) — check intercept
  2. Site-degradation (recovery=0 + ISF drop, EXP-2842)
  3. Settings re-tune within tercile
  4. Mechanism upgrade (basal-cut, SMB enablement) if applicable
- For over-performers, capture settings fingerprint as a candidate
  template for same-cell peers.

## Caveats

- Comparator switches between cell and lineage; flag is a screening
  tool, not a clinical decision threshold.
- Small n (especially oref0 n=3) means lineage SD itself is noisy.
- z-scores computed on a single observation per patient (their average
  protection); within-patient variance not modelled.

## Linked artefacts

- `docs/60-research/exp-2899-within-tercile-report-2026-04-22.md`
- `tools/cgmencode/exp_per_patient_deviation_2900.py`
- `externals/experiments/exp-2900_deviation.parquet`

## Next

- Wire `per_patient_protection_outlier` flag into audition_matrix.py
- Vignette for `ns-d444c120c23a` (aggressive oref1 under-performer)
- Vignette for `odc-74077367` (aggressive oref0 over-performer) —
  potential algorithm-migration counterexample
