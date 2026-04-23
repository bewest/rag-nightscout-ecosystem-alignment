# Vignette — `odc-74077367`: aggressive oref0 over-performer

**Date:** 2026-04-23 (overnight)
**Audition:** EXP-2900 flagged this patient as `over_performer_for_lineage`
(z = +1.11 vs the oref0 lineage median).
**Regime (EXP-2902):** `defended` (protection 0.72, cf 0.93).

This is the **only** oref0 patient in the cohort that escapes both the
`mechanism_gap` and `load_saturation` regimes — the exception that
proves the rule for oref0 deficits.

## Profile snapshot

| Field                          | Value             |
|--------------------------------|-------------------|
| Lineage / controller           | oref0 / OpenAPS   |
| Aggressiveness tercile         | aggressive (44.0) |
| Scheduled basal (mean U/h)     | 1.18              |
| Mean 4-h pre-event bolus (U)   | 3.86              |
| Descent events                 | 57                |
| Hyper-side events              | 303               |

## Phenotype panel

| Field                         | Value     | Interpretation |
|-------------------------------|-----------|----------------|
| `aid_protection_severe`       | **0.719** | +1.1 SD above oref0 median (0.39) |
| `cf_severe`                   | 0.930     | High but not at ceiling (defended regime) |
| `braking_ratio`               | 0.222     | Moderate brake — basal cut to ~22% (vs ns-d444c120c23a 0.05) |
| `stack_score`                 | **0.750** | High bolus stacking |
| `counter_reg_intercept` (EXP-2891) | 1.45 | Preserved range |
| `counter_reg_intercept` (EXP-2875) | 4.57 | Different window, would trigger overshoot |
| `hidden_leverage`             | **0.584** | High — bolus stacking IS driving outcomes |
| `archetype`                   | stacker_balanced | Matches the data |
| `frac_smb`                    | **0.000** | Zero SMB (oref0 has no SMB feature) |
| `frac_user_bolus`             | **0.986** | User-bolus discipline absorbs almost all hyper-side correction |

## Diagnosis — how does this patient escape oref0's mechanism gap?

### oref0 has no SMB → patient supplies SMB-equivalent manually
98.6% of hyper-side insulin comes from user bolus. The oref0 algorithm
contributes only 1.4% via excess basal. Compare with the same-tercile
oref1 patient (`ns-d444c120c23a`) where the algorithm supplies 60% via
SMB. **This patient is hand-compensating for the SMB channel oref0
lacks.**

### High stacking IS the mechanism, not a problem
Stack score 0.75 (top of cohort) and hidden_leverage 0.58 indicate
this user is actively pre-bolusing and re-bolusing meals in a pattern
that effectively replicates a closed-loop SMB pulse train. Without
this discipline, the same oref0 settings would put the patient in
mechanism_gap regime (per EXP-2902 cohort distribution).

### Moderate braking, not aggressive
braking_ratio 0.22 — basal cut to 22% during pre-nadir descents.
Ineffective compared to oref1 (~5%). The defence is not on the basal
side; it's on the bolus-discipline side.

### cf_severe 0.93 (not at ceiling)
The patient does NOT exhibit load saturation — settings are calibrated
to keep ~7% of descents safely above hypo without AID. This is the
behavioural complement to manual bolus discipline: settings tuned with
self-knowledge of the hand-compensation strategy.

## What this vignette implies

### The oref0 mechanism gap is REAL but compensable
Three of 19 patients are oref0; one (this patient) escapes the gap
through user behaviour. The other two are in mechanism_gap (severe
deficit) and moderate (modest performance) regimes. The escape route
is **manual SMB substitution + carefully calibrated cf**, not
algorithm tuning.

### Implication for AID developers
The oref0→oref1 migration value is largest for users WITHOUT this
discipline. A user already practicing high-frequency manual bolusing
gains less from algorithm-supplied SMB; their leverage is already
captured. Migration to oref1 may even *reduce* their agency.

### Implication for therapy guidance
Identifying this pattern — high stack_score + high frac_user_bolus +
non-saturated cf — could mark patients who are "happy on oref0" and
should not be pushed to migrate. Counter to the default
`regime_mechanism_gap` recommendation, this profile flags algorithm
satisfaction.

### Implication for audition
A new flag candidate: `manual_smb_substitution`
- Fires when: lineage = oref0 AND frac_smb < 0.05 AND frac_user_bolus
  > 0.85 AND stack_score > 0.50 AND aid_protection_severe > 0.60
- Severity: INFO
- Rationale: "Patient is hand-compensating for missing SMB channel.
  Algorithm migration recommendations should be tempered."

Wiring deferred to EXP-2906; flag would cover 1 patient currently.

## Counter-reg discrepancy

Two intercept values exist:
- EXP-2875 (per-patient rescue-free regression): 4.57 mg/dL/min
- EXP-2891 (event-conditioned): 1.45 mg/dL/min

EXP-2898 documents the same multi-source pattern. The 4.57 value would
trigger `rebound_overshoot_algorithm_gap` (intercept ≥3.0 + protection
<0.30) — but this patient's protection is 0.72, so the conjunction
fails. Correctly suppressed: rapid recovery here is not a lagging
indicator; this patient genuinely defends well.

## Caveats

- **N=1**: this is a single oref0 patient. Cannot generalise to "many
  oref0 users escape the gap with bolus discipline." Best read as
  existence proof.
- **Cohort selection**: patient may have been selected into the dataset
  because of high engagement (Open Diabetes Cohort participation
  signals technical user behaviour).
- The intercept discrepancy (1.45 vs 4.57) deserves its own
  reconciliation experiment.

## Linked artefacts

- `docs/60-research/exp-2900-per-patient-deviation-report-2026-04-22.md`
- `docs/60-research/exp-2902-regime-stratification-2026-04-22.md`
- `docs/60-research/vignette-load-saturation-aggressive-oref1-2026-04-22.md`
- `docs/60-research/vignette-comparative-conservative-lineage-2026-04-22.md`
- `externals/experiments/exp-2891_simpson_dose_response.parquet`
- `externals/experiments/exp-2893_hyper_channels.parquet`

## Three oref0 patients summarised

| Patient            | Tercile      | Regime         | prot | cf   | Story |
|--------------------|--------------|----------------|-----:|-----:|-------|
| `odc-86025410`     | conservative | mechanism_gap  | 0.13 | 0.70 | Algorithm migration case (vignette 1) |
| `odc-96254963`     | moderate     | moderate       | 0.39 | 0.91 | Modest performance, cohort baseline |
| `odc-74077367`     | aggressive   | defended       | 0.72 | 0.93 | Manual SMB substitution; "happy on oref0" |

The 0.13 → 0.72 protection range across these 3 patients is what drives
EXP-2899's oref0 consistency_score = 0.24. The mechanism here is now
identifiable: oref0 protection depends on whether the user supplies the
missing SMB channel themselves.
