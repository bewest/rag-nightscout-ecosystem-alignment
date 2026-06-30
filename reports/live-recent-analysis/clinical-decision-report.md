# Clinical Decision Support — patient `live-recent`

_Generated: 2026-06-30T19:36:31.290613+00:00_

## Insulin sufficiency

Overall insulin delivery shows opportunity for improvement (TIR 58%, TBR<70 2.0%, TAR>180 40%). 2 risk(s) identified; 1 parameter change(s) proposed this cycle.

**Main risks:**
- Hyperglycemia burden elevated (TAR>180 40.1% vs target 25%).
- Glycemic variability high (CV 37% vs target 36%).

**What's working:**
- Hypoglycemia within target (TBR<70 2.0%).

**Time-in-range distribution**

![Stacked bar of time spent in each glucose range.](figures/fig_time_in_range.png)

_Share of time in each glycemic band over 23,948 readings. Green is the 70-180 mg/dL target; reds are lows, ambers are highs._

**Ambulatory glucose profile (AGP)**

![Ambulatory glucose profile percentile bands by hour of day.](figures/fig_agp.png)

_Median glucose by time of day with interquartile (25–75%) and 10–90% bands. The green zone is the 70–180 mg/dL target; a flat median inside it is the goal._

## Recommendations

### Basal

**Decision:** CHANGE  
**Summary:** Basal: increase from 1.7 to 1.87 (+10%).

| Field | Value |
|---|---|
| Current | 1.7 |
| Practical (implement now) | 1.87 (+10%) |
| Time block | 06:00–12:00 |
| Confidence | 0.67 |

**Justification:** Basal increase: implement the practical step 1.7 -> 1.87 (+10%) now. Theoretical optimum is 1.87 (+10%); the practical step honors a safe titration cap of 20% per cycle. This derives from a validated deconfounded estimate (the controller-masking confound is already removed), so it is not down-weighted for controller masking. Increase basal by 10% during morning (6:00-12:00). This is a narrow deconfounded step: inferred-meal windows are excluded, Loop is consistently adding basal, and TBR is below 4%. Use the 2-week TBR guardrail before considering another step.

**Expected outcomes (2-week):**

| Metric | Baseline | Expected | Direction |
|---|---|---|---|
| TIR | 57.9% | 59.2% | increase |
| TBR<70 | 1.99% | 1.99% | stable |
| TAR>180 | 40.1% | 38.8% | decrease |

**Overnight glucose profile (00:00–06:00)**

![Overnight median glucose by hour with interquartile band.](figures/fig_overnight.png)

_Median overnight glucose with IQR. A rising trend suggests basal is too low; a falling trend suggests it is too high. Used to contextualize the basal recommendation._

**Scheduled vs actual basal**

![Scheduled vs actual basal](figures/04_basal_pattern.png)

_Median programmed basal vs what the loop actually delivered by hour. Persistent loop deviation indicates the scheduled rate is mismatched in that direction._

**Success criteria** (revisit in 14 days):
- TIR improves by at least +0.6 pp toward the projected 59% within 2 weeks.
- TBR<70 does not worsen by more than 1 pp.

**Stop / escalate criteria:**
- TBR<70 increases by more than 1 pp after the Basal change -> revert and escalate.
- Severe hypoglycemia (TBR<54) emerges -> revert immediately.
- No measurable TIR improvement at 2 weeks -> reassess direction.

### ISF

**Decision:** NO CHANGE  
**Hold reason:** insufficient_evidence  
**Summary:** ISF: no change recommended (insufficient evidence (confidence 0.35 below 0.50)).

**Justification:** ISF reviewed: a directional signal exists (theoretical target 30) but is held due to insufficient evidence (confidence 0.35 below 0.50). Re-evaluate at the next review.

**Expected outcomes (2-week):**

| Metric | Baseline | Expected | Direction |
|---|---|---|---|
| TIR | 57.9% | 57.9% | stable |
| TBR<70 | 1.99% | 1.99% | stable |
| TAR>180 | 40.1% | 40.1% | stable |

**Demand-phase ISF decomposition**

![Bar chart of profile, apparent, and demand-phase ISF with CI.](figures/fig_demand_isf.png)

_Profile ISF vs the apparent/correction ISF (amplified by AID compensation) vs the demand-phase ISF — the validated 0–2h insulin effect (EXP-2651) and the true target, shown with its 95% confidence interval. The apparent value is not the target; the recommendation tracks the demand-phase value, bounded by a safety margin (EXP-2738)._

**ISF reconciliation (profile vs observed)**

![ISF reconciliation (profile vs observed)](figures/03_isf_reconciliation.png)

_Profile ISF vs the correction-derived (observed/apparent) ISF. The observed value is amplified by AID compensation (basal suspension during corrections), so it is NOT a direct ISF target: the recommendation deliberately preserves the controller's residual safety margin (EXP-2738) rather than chasing the apparent value. Separately, a lower effective ISF for large single corrections is dose-shaping guidance (split the dose), not a baseline schedule change._

**Success criteria** (revisit in 14 days):
- ISF held: glycemic metrics remain within tolerance of baseline over the 2-week window.
- No new hypoglycemia signal (TBR<70 stays below 4%).

**Stop / escalate criteria:**
- TBR<70 rises by more than 1 pp -> escalate review.
- TIR declines materially -> re-open ISF for change.

### Carb ratio

**Decision:** NO CHANGE  
**Hold reason:** no_meaningful_deviation  
**Summary:** Carb ratio: no change recommended.

**Justification:** Carb ratio reviewed: the data do not support a change this cycle. Maintaining the current setting and re-evaluating at the next review.

**Expected outcomes (2-week):**

| Metric | Baseline | Expected | Direction |
|---|---|---|---|
| TIR | 57.9% | 57.9% | stable |
| TBR<70 | 1.99% | 1.99% | stable |
| TAR>180 | 40.1% | 40.1% | stable |

**Post-meal glucose excursion**

![Mean post-meal glucose excursion curve with interquartile band.](figures/fig_cr_excursion.png)

_Median glucose rise after 5 carb-counted, bolused meals (peak +45 mg/dL at 45 min; -108 mg/dL vs baseline at 4 h). Carb ratio held this cycle; this profile is the baseline to compare against at the next review._

**Success criteria** (revisit in 14 days):
- Carb ratio held: glycemic metrics remain within tolerance of baseline over the 2-week window.
- No new hypoglycemia signal (TBR<70 stays below 4%).

**Stop / escalate criteria:**
- TBR<70 rises by more than 1 pp -> escalate review.
- TIR declines materially -> re-open Carb ratio for change.

## Overall justification

Practical changes this cycle: Basal 1.7->1.87. Each practical step is the safe-titration projection of a larger theoretical optimum (documented in the addenda). Held/deferred: ISF (insufficient_evidence), Carb ratio (no_meaningful_deviation).

## Addenda

- Factors considered: time-in-range distribution, hypo/hyper burden, glycemic variability, per-parameter advisory evidence, and cross-parameter sequencing.
- Basal theoretical optimum: 1.87 (+10% vs current 1.7); practical step capped at 20%/cycle -> 1.87.
- ISF theoretical optimum: 30 (-25% vs current 40); held this cycle.
- Risks reviewed and mitigated: Hyperglycemia burden elevated (TAR>180 40.1% vs target 25%). Glycemic variability high (CV 37% vs target 36%).
- Deconfounding applied: Basal recommendation(s) derive from validated deconfounded estimates (e.g. demand-phase ISF EXP-2651, correction-denominator/bilateral EXP-2741, deconfounded basal EXP-3447). The controller-masking confidence penalty does not apply to these, improving accuracy without removing the controller's residual safety margin (EXP-2738).
- Mitigations: changes are bounded by a per-cycle titration cap; carb ratio is sequenced after basal/ISF to avoid confounded adjustment; explicit stop/escalate criteria accompany every recommendation for the 2-week feedback loop.
- Dose-shaping guidance (ISF, NOT a baseline schedule change): Correction doses above 1.5U show diminishing returns. At 2.8U, each unit achieves only 16 mg/dL drop vs 40 mg/dL at 1U. Consider: (1) splitting large corrections into smaller doses spaced 30+ min apart, (2) using ISF=16 for doses ≥3U. This is a pharmacokinetic property (β=0.9), not circadian. This describes a dose-conditional effective value for large corrections; prefer splitting large corrections over altering the baseline ISF schedule.

## Reimbursement justification

**Data sufficiency:** Analysis based on 90 days of CGM data (23,948 readings). Sufficient for time-in-range and titration assessment.

**Risks reviewed:**
- Hyperglycemia burden elevated (TAR>180 40.1% vs target 25%).
- Glycemic variability high (CV 37% vs target 36%).

**Mitigations:**
- Recommendations bounded by a safe per-cycle titration cap.
- Carb ratio sequenced after basal/ISF to prevent confounded change.
- Explicit stop/escalate criteria defined for each recommendation.

**Alternatives discussed:**
- Considered no-change vs incremental titration vs settings reboot.
- Theoretical optima documented but deferred in favor of safe steps.

**Patient-specific barriers:**
- No patient-reported adherence, supply, or prescription barriers noted at this review.

**Agreed plan:** Agreed plan: Basal -> 1.87. Re-evaluate in 2 weeks.

**Expected trajectory:** Projected time-in-range at next review: ~59% (baseline 58%). Outcome will be scored against the per-recommendation success and stop/escalate criteria.

**Follow-up date:** 2026-07-14
