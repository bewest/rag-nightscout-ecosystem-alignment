# Patient Vignette — `odc-86025410` (Conservative-Legacy-oref0 Safety Case)

**Date:** 2026-04-22
**Purpose:** Concrete illustration of the conservative-oref0
exposure identified by EXP-2891/2892/2893.  This is a real safety
case; the phenotype signals in `production/audition_matrix.py`
should trigger high-severity recommendations for this patient.

## 1. Snapshot

| Metric | Value | Guideline | Status |
| ------ | ----- | --------- | ------ |
| Days of data | 375 | — | — |
| Median BG | 136 mg/dL | — | — |
| TIR 70–180 | 67.1 % | ≥ 70 % | slightly below |
| TBR < 70 | **5.9 %** | < 4 % | **exceeds** |
| TBR < 54 (severe) | **3.9 %** | < 1 % | **~4× limit** |
| TAR > 180 | 25.2 % | < 25 % | at limit |
| TAR > 250 | 7.4 % | < 5 % | exceeds |
| Controller | OpenAPS (oref0 legacy) | — | — |
| Median scheduled basal | 0.35 U/h | — | conservative |
| Median actual basal | 0.325 U/h | — | 93 % of scheduled |
| Total SMBs in 375 days | **0 U** | — | — |
| Time at zero basal | 17.1 % | — | — |

The patient spends **~56 minutes/day in severe hypoglycaemia
(<54 mg/dL)** — roughly four times the consensus target and
enough to cause chronic HAAF (per EXP-2878's null, HAAF metric
was inconclusive, but the clinical risk remains).

## 2. Phenotype axes (EXP-2886 / 2889 / 2892)

| Axis | Value | Interpretation |
| ---- | ----- | -------------- |
| `stack_score` | 0.208 | low |
| `braking_ratio` | **0.962** | controller keeps ~96 % of scheduled basal during descents — barely brakes |
| `counter_reg_intercept` | 0.901 | strong positive (BG rebounds post-nadir) |
| `hidden_leverage` | 0.008 | near-zero; aggressive-insulin lever not engaged |
| `archetype` | **lax_braking** | — |
| `tercile` | **conservative** | aggressiveness rank bottom |
| `basal-cut utilization` | **0.198** | uses only 20 % of available basal-cut ceiling |
| `SMB fraction` | **0.000** | zero automatic corrections (oref0 legacy) |
| `observed severe rate` | **0.579** | 58 % of descent events go < 54 mg/dL |
| `counterfactual severe` | 0.705 | even without AID, 70 % would go severe |
| `aid_protection_severe` | **0.125** | only 12.5 percentage points protected |

## 3. Mechanism interpretation

Three reinforcing failures:

1. **Conservative scheduled basal (0.35 U/h)** makes the basal-cut
   channel small even at 100 % utilization: max possible drop-saving
   ≈ 17 mg/dL per event per hour.
2. **Algorithm uses only 20 % of that small ceiling** — not a
   user-tunable gap; the legacy oref0 cut logic doesn't engage
   aggressively enough during descents from low baselines
   (EXP-2892).
3. **No SMB channel at all** — when BG rebounds, there is no
   automatic correction, so the patient over-corrects manually,
   returning insulin into a body that was just suspended.
   Counter-regulation intercept 0.90 is consistent with repeated
   rebound-→-manual-bolus cycles.

These three failures are orthogonal and multiplicative.  No single
tuning change removes all three.

## 4. Audition matrix routing

Given the new wiring from EXP-2889 + EXP-2892, this patient triggers:

- `lax_braking_controller_efficacy` (severity: medium)
  — `braking_ratio ≥ 0.40 AND aid_protection_severe ≤ 0.15`
  — YES: 0.96 ≥ 0.40 and 0.125 ≤ 0.15
- The *opposite* of `aid_safety_dependence_high` — this patient
  is **not** dependent on the AID, because the AID is not
  protecting them.  The correct semantic flag is the
  `lax_braking_controller_efficacy` flag, which reads:
  "the controller is leaving safety on the table."

The audition recommender should surface this as an **algorithm
migration** candidate, **not** a settings-tuning candidate, per
EXP-2892: lineage migration from oref0 legacy → AAPS (oref1) or
Loop gives a step-change improvement.

## 5. Counterfactual comparison

If transplanted to oref1 (with setting unchanged), the cohort
benchmark predicts:

- Conservative-oref1 median `aid_protection_severe` = 0.635
  vs this patient's 0.125 → delta = +51 pp
- Conservative-oref1 SMB fraction ~ 0.48 → would introduce an
  entirely new correction channel for this patient

On counterfactual severe baseline of 0.705, moving to oref1
would take observed severe from 0.579 down to approximately
0.705 − 0.705·0.635 = 0.257.  That is a reduction from
~56 min/day severe to ~25 min/day, still above guideline but
within the achievable range.

## 6. Recommendation package

Ordered by expected impact:

1. **Algorithm migration** (high impact, high friction).  AAPS
   (oref1) or Loop.  Provides SMB channel, responsive basal-cut,
   and better descent prediction.
2. **Settings review in context of current algorithm** (medium
   impact, low friction).  Even within oref0:
   - Increase scheduled basal — ceiling grows proportionally
   - Review `max_iob` and `autosens` enable — may improve
     utilization within existing code
3. **Education** (low impact, low friction).  Counsel patient
   that legacy oref0 does not automatically correct post-hypo
   rebound.  Avoid reactive corrections that will stack with
   impending IOB normalisation.

## 7. What this vignette validates

- The **audition matrix** correctly flags this patient via
  `lax_braking_controller_efficacy` triage.
- The **counterfactual pipeline** (EXP-2889) generates the
  evidence for step-change migration advice — "this patient's
  algorithm is under-protecting them by 51 pp relative to what
  oref1 would deliver at the same settings."
- The **mechanism decomposition** (EXP-2892/2893) supplies the
  reason: absent channel + under-utilized channel + small
  ceiling.  Without these three axes, advice collapses to
  "manage your settings better," which is ineffective.

## 8. Contrast — patient `a`, `ns-8b3c1b50793c`, etc.

A future vignette should pair this case with a
**conservative-oref1** patient showing how the same user
aggressiveness profile with a modern algorithm yields very
different outcomes.  This comparative pair would make the
lineage-mechanism story concrete for non-technical audiences.

## 9. Artifacts

- `externals/experiments/exp-2886_phenotype.parquet` (phenotype)
- `externals/experiments/exp-2889_counterfactual_replay.parquet`
- `externals/experiments/exp-2892_mechanism.parquet`
- `externals/experiments/exp-2893_hyper_channels.parquet`
- This vignette: `docs/60-research/vignette-odc-86025410-conservative-oref0-safety-2026-04-22.md`
