# EXP-2898 — counter-regulation intercept by lineage

**Date:** 2026-04-22 (overnight)
**N:** 24 patients with known lineage (19 patients + 5 with unknown lineage = 24 total)
**Source:** `tools/cgmencode/exp_counter_reg_lineage_2898.py`
**Output:** `externals/experiments/exp-2898_summary.json`

## Question

EXP-2875 found counter-regulation preserved cohort-wide (β_intercept
≈ +1.42 mg/dL/min). Does the magnitude differ by lineage? A priori
hypothesis: oref1's SMB channel might over-correct after nadir → high
intercept variance / over-shoot rebound.

## Result — overturning prior hypothesis

| Lineage          | n | Median intercept (mg/dL/min) | Median frac_smb |
|------------------|--:|-----------------------------:|----------------:|
| Loop (iOS)       | 7 |        1.06                  |   0.45          |
| oref1 (modern)   | 9 |        1.20                  |   0.51          |
| **oref0 (legacy)** | 3 |  **4.30**                  |   0.00          |
| unknown          | 5 |        1.38                  |   0.37          |

- Kruskal-Wallis across lineages: **H = 8.46, p = 0.037** (significant)
- Spearman intercept vs frac_smb (n=23): **ρ = −0.43, p = 0.040**
  (more SMB → SLOWER recovery)

## Interpretation — recovery is a *symptom*, not a strength

The intuitive reading "oref0 patients recover fastest, so they're
fine" is wrong. The mechanism story:

1. **SMB-rich lineages (Loop, oref1) catch the descent earlier**.
   Nadirs are shallower (EXP-2892: protection 0.49–0.72 vs oref0
   0.13). Smaller deficits → smaller counter-regulatory burst →
   gentler rebound.

2. **oref0 lets descents reach deeper nadirs** (low basal-cut
   utilization, no SMB). When counter-regulation kicks in, it has
   more work to do, AND the user is more likely to take rescue
   carbs (panic-treatment), producing a sharp 4.3 mg/dL/min rebound.

3. **Negative ρ between intercept and frac_smb (−0.43)** confirms:
   SMB delivery moderates rebound speed. This is the AID actively
   braking the recovery (small SMB doses post-nadir), not just
   passive observation.

## What the rebound speed actually predicts

A high counter-reg intercept is associated with:
- Larger preceding nadir excursion (deficit was bigger)
- Greater rescue-carb intake (user-driven over-correction)
- Higher subsequent hyper risk (the rebound shoots past target)

Therefore high intercept is a **lagging indicator of upstream AID
failure**, not a marker of resilience.

## Audition implications

The existing `counter_reg_impaired` flag (EXP-2876) fires on LOW
intercept (≤+0.5 mg/dL/min). This experiment suggests adding a
*counterpart* flag for HIGH intercept — but with care, because high
intercept can mean either:

- (a) sharp rebound from a deep nadir (oref0 pattern; problem is
  upstream descent, not recovery)
- (b) genuinely brisk physiology with adequate SMB braking

A useful flag would condition on `aid_protection_severe`:
- **`rebound_overshoot_algorithm_gap`**: intercept ≥ 3.0 AND
  `aid_protection_severe` < 0.30 → upstream descent control failing.
  Fires for the oref0 patients here (intercept 3.9–4.3, protection
  0.13). Routes to algorithm-migration recommendation.

Wiring deferred to next experiment unless cohort confirms.

## Caveats

- n=3 for oref0 in this analysis (only 3 patients in cohort with this
  lineage). The intercept difference (4.3 vs 1.2) is large but the
  cell is underpowered.
- Counter-reg intercept regression in EXP-2875 had a low R² (0.04–0.08
  per patient). The intercept point estimates are stable but
  individual-event prediction is weak.
- Cannot separate physiologic counter-regulation from rescue-carb
  response with these data.

## Linked artefacts

- `docs/60-research/exp-2875-counter-regulation-report-2026-04-22.md`
- `docs/60-research/exp-2876-counter-reg-audition-report-2026-04-22.md`
  (existing impaired flag)
- `docs/60-research/exp-2891-simpson-dose-response-report-2026-04-22.md`
- `docs/60-research/exp-2892-mechanism-report-2026-04-22.md`
- `docs/60-research/exp-2893-hyper-channels-report-2026-04-22.md`
- `tools/cgmencode/exp_counter_reg_lineage_2898.py`

## Next experiments

- EXP-2899: within-tercile heterogeneity — variance in protection
  per (lineage, tercile) cell.
- Audition wiring: `rebound_overshoot_algorithm_gap` flag (deferred,
  pending validation in next replication).
