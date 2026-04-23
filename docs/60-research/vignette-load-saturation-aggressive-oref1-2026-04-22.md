# Vignette — `ns-d444c120c23a`: aggressive oref1 under-performer

**Date:** 2026-04-22 (overnight)
**Audition:** EXP-2900 flagged this patient as `under_performer_for_lineage`
(z = −1.85 vs the aggressive-oref1 cell median).

## Profile snapshot

| Field                          | Value         |
|--------------------------------|---------------|
| Lineage / controller           | oref1 / Trio  |
| Aggressiveness tercile         | aggressive (45.0) |
| Scheduled basal (mean U/h)     | 1.05          |
| Mean 4-h pre-event bolus (U)   | 4.44          |
| Descent events                 | 180           |
| Hyper-side events              | 406           |

## Phenotype panel

| Field                         | Value     | Interpretation |
|-------------------------------|-----------|----------------|
| `aid_protection_severe`       | **0.572** | −1.85 SD below cell median (0.755) |
| `cf_severe`                   | 1.000     | Maximum physiology load — every descent would reach severe without AID |
| `braking_ratio`               | 0.052     | Strong braking (basal cut to 5%) |
| `stack_score`                 | 0.292     | Moderate bolus-stacking frequency |
| `counter_reg_intercept`       | 1.34      | Within typical preserved range (no flag) |
| `hidden_leverage`             | 0.28      | Modest — bolus stacking not the primary driver |
| `archetype`                   | well_defended | Mismatch with the −1.85 SD outcome |
| `frac_smb`                    | 0.602     | Functional SMB channel (~60% of hyper-side correction) |

The "well_defended" archetype assigned by EXP-2886 is *contradicted* by
the EXP-2900 z-score. Strong braking + capable SMB channel + preserved
counter-reg should produce cell-typical (~0.75) protection; observed
0.57 is materially below.

## Diagnosis — why is this patient under-performing?

### Mechanism channels say "intact"
- **Basal-cut utilization**: 95% (braking_ratio 0.05 → near-full
  suspension). EXP-2892 capacity-vs-utilization channel passes.
- **SMB channel**: present, 60% of hyper-side delivery. EXP-2893
  presence channel passes.
- **Counter-reg intercept**: 1.34 mg/dL/min, in preserved band. No
  EXP-2898 rebound-overshoot conjunction.

### Load is at the ceiling
- **`cf_severe = 1.00`**: every single descent event would reach <54
  mg/dL without AID. This is the maximum possible physiology load —
  no other oref1 patient in the aggressive tercile tops 1.00 because
  they have at least *some* descents that wouldn't reach severe.
- The 0.57 protection translates to: of the 180 descent events that
  WOULD have hit <54 mg/dL, the AID prevented 103 (57%). The other
  77 reached severe.
- Settings are aggressive (tercile 45.0, near top of cohort) — meaning
  the patient's bolus inputs are aggressive enough to put every meal
  on a near-hypo trajectory. The AID then has to catch all of them.

### The pattern
This is a **load-saturation** under-performer, not a mechanism-deficit
under-performer. The AID's defensive channels are all working; the
patient's settings/behaviour push the system to its ceiling so often
that the absolute count of breakthroughs is high.

Differential vs other under-performers (e.g. patient `a`, conservative
Loop): `a` lacks mechanism; `ns-d444c120c23a` has mechanism but exceeds
its operating envelope.

## Audition flag interaction

| Flag                                | Fires? | Reason |
|-------------------------------------|--------|--------|
| `under_performer_for_lineage`       | ✅ MED | EXP-2900 z=−1.85 |
| `impaired_counter_regulation`       | ❌     | cr=1.34, in preserved band |
| `rebound_overshoot_algorithm_gap`   | ❌     | cr<3.0; no overshoot |
| `lax_braking_controller_efficacy`   | ❌     | braking_ratio=0.05 (excellent) |
| `smb_absent_algorithm_gap`          | ❌     | frac_smb=0.60 |
| `evening_stacker`                   | (TBD)  | needs TOD breakdown |

The single firing flag (`under_performer_for_lineage`) plus the
mechanism panel ALL passing is itself the diagnosis: nothing is
mechanically broken, so the recommendation surface is "settings
de-escalation" rather than "algorithm migration" or "mechanism
upgrade".

## Recommendations (per EXP-2900 ordered remediation tree)

1. **Counter-reg channel**: PASS (cr=1.34) — no action.
2. **Site-degradation**: needs cannula-rotation audit; not assessable
   from this aggregate. Defer to per-day analysis.
3. **Settings re-tune within tercile**: PRIMARY recommendation. With
   `cf_severe = 1.00`, every meal is at the hypo precipice. CR less
   aggressive (insulin per gram), or basal slightly lower — would shift
   `cf_severe` down off the ceiling and make the AID's 60% protection
   yield fewer absolute breakthroughs.
4. **Mechanism upgrade**: NOT applicable (oref1 + SMB + Trio is the
   modern stack).

### Quantitative target
Reducing `cf_severe` from 1.00 to 0.85 (a 15-pp pullback achievable
by ~10% CR de-aggression) at constant 0.57 protection ratio would
drop observed severe rate from 0.43 to 0.36 — closer to the cell
median 0.245.

## Methodological note

This vignette demonstrates the value of the EXP-2897 decomposition:
**observed = (1 − protection) × cf**. When a patient deviates negatively
from cell median, the diagnosis depends on which factor moved:
- low protection (mechanism gap) → algorithm migration
- high cf (load saturation) → settings de-aggression

`ns-d444c120c23a` is a load-saturation case. Without the cf channel
the recommendation would be "more aggressive AID" — exactly wrong.

## Linked artefacts

- `docs/60-research/exp-2900-per-patient-deviation-report-2026-04-22.md`
- `docs/60-research/exp-2897-hourly-cf-report-2026-04-22.md`
- `externals/experiments/exp-2891_simpson_dose_response.parquet`
- `externals/experiments/exp-2893_hyper_channels.parquet`
