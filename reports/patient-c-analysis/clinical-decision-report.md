# Clinical Decision Support — patient `c`

_Generated: 2026-07-01T18:25:15.515186+00:00_

## Insulin sufficiency

Overall insulin delivery shows opportunity for improvement (TIR 62%, TBR<70 4.7%, TAR>180 34%). 4 risk(s) identified; 0 parameter change(s) proposed this cycle.

**Main risks:**
- Hypoglycemia burden elevated (TBR<70 4.7% vs target 4%).
- Clinically significant lows present (TBR<54 1.56%).
- Hyperglycemia burden elevated (TAR>180 33.7% vs target 25%).
- Glycemic variability high (CV 43% vs target 36%).

**What's working:**
- Settings are internally consistent; no single parameter is grossly miscalibrated.

**Time-in-range distribution**

![Stacked bar of time spent in each glucose range.](figures/fig_time_in_range.png)

_Share of time in each glycemic band over 42,859 readings. Green is the 70-180 mg/dL target; reds are lows, ambers are highs._

**Ambulatory glucose profile (AGP)**

![Ambulatory glucose profile percentile bands by hour of day.](figures/fig_agp.png)

_Median glucose by time of day with interquartile (25–75%) and 10–90% bands. The green zone is the 70–180 mg/dL target; a flat median inside it is the goal._

## Recommendations

### Basal

**Decision:** NO CHANGE  
**Hold reason:** insufficient_evidence  
**Summary:** Basal: no change recommended (insufficient evidence (confidence 0.20 below 0.50)).

**Justification:** Basal reviewed: a directional signal exists (theoretical target 1.12) but is held due to insufficient evidence (confidence 0.20 below 0.50). Re-evaluate at the next review.

**Expected outcomes (2-week):**

| Metric | Baseline | Expected | Direction |
|---|---|---|---|
| TIR | 61.6% | 61.6% | stable |
| TBR<70 | 4.7% | 4.7% | stable |
| TAR>180 | 33.7% | 33.7% | stable |

**Overnight glucose profile (00:00–06:00)**

![Overnight median glucose by hour with interquartile band.](figures/fig_overnight.png)

_Median overnight glucose with IQR. A rising trend suggests basal is too low; a falling trend suggests it is too high. Used to contextualize the basal recommendation._

**Scheduled vs actual basal**

![Scheduled vs actual basal](figures/04_basal_pattern.png)

_Median programmed basal vs what the loop actually delivered by hour. Persistent loop deviation indicates the scheduled rate is mismatched in that direction._

**Success criteria** (revisit in 14 days):
- Basal held: glycemic metrics remain within tolerance of baseline over the 2-week window.
- No new hypoglycemia signal (TBR<70 stays below 4%).

**Stop / escalate criteria:**
- TBR<70 rises by more than 1 pp -> escalate review.
- TIR declines materially -> re-open Basal for change.

### ISF

**Decision:** NO CHANGE  
**Hold reason:** insufficient_evidence  
**Summary:** ISF: no change recommended (insufficient evidence (confidence 0.30 below 0.50)).

**Justification:** ISF reviewed: a directional signal exists (theoretical target 112.5) but is held due to insufficient evidence (confidence 0.30 below 0.50). Re-evaluate at the next review.

**Expected outcomes (2-week):**

| Metric | Baseline | Expected | Direction |
|---|---|---|---|
| TIR | 61.6% | 61.6% | stable |
| TBR<70 | 4.7% | 4.7% | stable |
| TAR>180 | 33.7% | 33.7% | stable |

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
**Hold reason:** insufficient_evidence  
**Summary:** Carb ratio: no change recommended (insufficient evidence (confidence 0.34 below 0.50)).

**Justification:** Carb ratio reviewed: a directional signal exists (theoretical target 3.8) but is held due to insufficient evidence (confidence 0.34 below 0.50). Re-evaluate at the next review.

**Expected outcomes (2-week):**

| Metric | Baseline | Expected | Direction |
|---|---|---|---|
| TIR | 61.6% | 61.6% | stable |
| TBR<70 | 4.7% | 4.7% | stable |
| TAR>180 | 33.7% | 33.7% | stable |

**Post-meal glucose excursion**

![Mean post-meal glucose excursion curve with interquartile band.](figures/fig_cr_excursion.png)

_Median glucose rise after 143 carb-counted, bolused meals (peak +40 mg/dL at 30 min; -66 mg/dL vs baseline at 4 h). Carb ratio held this cycle; this profile is the baseline to compare against at the next review._

**Success criteria** (revisit in 14 days):
- Carb ratio held: glycemic metrics remain within tolerance of baseline over the 2-week window.
- No new hypoglycemia signal (TBR<70 stays below 4%).

**Stop / escalate criteria:**
- TBR<70 rises by more than 1 pp -> escalate review.
- TIR declines materially -> re-open Carb ratio for change.

## Overall justification

No parameter changes are recommended this cycle; all domains were reviewed and held with documented rationale. Held/deferred: Basal (insufficient_evidence), ISF (insufficient_evidence), Carb ratio (insufficient_evidence).

## Addenda

- Factors considered: time-in-range distribution, hypo/hyper burden, glycemic variability, per-parameter advisory evidence, and cross-parameter sequencing.
- Basal theoretical optimum: 1.12 (-20% vs current 1.4); held this cycle.
- ISF theoretical optimum: 112.5 (+50% vs current 75); held this cycle.
- Carb ratio theoretical optimum: 3.8 (-16% vs current 4.5); held this cycle.
- Risks reviewed and mitigated: Hypoglycemia burden elevated (TBR<70 4.7% vs target 4%). Clinically significant lows present (TBR<54 1.56%). Hyperglycemia burden elevated (TAR>180 33.7% vs target 25%). Glycemic variability high (CV 43% vs target 36%).
- Mitigations: changes are bounded by a per-cycle titration cap; carb ratio is sequenced after basal/ISF to avoid confounded adjustment; explicit stop/escalate criteria accompany every recommendation for the 2-week feedback loop.

## Reimbursement justification

**Data sufficiency:** Analysis based on 180 days of CGM data (42,859 readings). Sufficient for time-in-range and titration assessment.

**Risks reviewed:**
- Hypoglycemia burden elevated (TBR<70 4.7% vs target 4%).
- Clinically significant lows present (TBR<54 1.56%).
- Hyperglycemia burden elevated (TAR>180 33.7% vs target 25%).
- Glycemic variability high (CV 43% vs target 36%).

**Mitigations:**
- Recommendations bounded by a safe per-cycle titration cap.
- Carb ratio sequenced after basal/ISF to prevent confounded change.
- Explicit stop/escalate criteria defined for each recommendation.

**Alternatives discussed:**
- Considered no-change vs incremental titration vs settings reboot.
- Theoretical optima documented but deferred in favor of safe steps.

**Patient-specific barriers:**
- No patient-reported adherence, supply, or prescription barriers noted at this review.

**Agreed plan:** Agreed plan: maintain current settings with documented rationale; re-evaluate in 2 weeks.

**Expected trajectory:** Projected time-in-range at next review: ~62% (baseline 62%). Outcome will be scored against the per-recommendation success and stop/escalate criteria.

**Follow-up date:** 2026-07-15
