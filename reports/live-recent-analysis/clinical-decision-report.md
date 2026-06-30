# Clinical Decision Support — patient `live-recent`

_Generated: 2026-06-30T18:01:20.934581+00:00_

## Insulin sufficiency

Overall insulin delivery shows opportunity for improvement (TIR 58%, TBR<70 2.0%, TAR>180 40%). 2 risk(s) identified; 0 parameter change(s) proposed this cycle.

**Main risks:**
- Hyperglycemia burden elevated (TAR>180 40.1% vs target 25%).
- Glycemic variability high (CV 37% vs target 36%).

**What's working:**
- Hypoglycemia within target (TBR<70 2.0%).

## Recommendations

### Basal

**Decision:** NO CHANGE  
**Hold reason:** insufficient_evidence  
**Summary:** Basal: no change recommended (insufficient evidence (confidence 0.22 below 0.50)).

**Justification:** Basal reviewed: a directional signal exists (theoretical target 2.52) but is held due to insufficient evidence (confidence 0.22 below 0.50). Re-evaluate at the next review.

**Expected outcomes (2-week):**

| Metric | Baseline | Expected | Direction |
|---|---|---|---|
| TIR | 57.9% | 57.9% | stable |
| TBR<70 | 1.99% | 1.99% | stable |
| TAR>180 | 40.1% | 40.1% | stable |

**Success criteria** (revisit in 14 days):
- Basal held: glycemic metrics remain within tolerance of baseline over the 2-week window.
- No new hypoglycemia signal (TBR<70 stays below 4%).

**Stop / escalate criteria:**
- TBR<70 rises by more than 1 pp -> escalate review.
- TIR declines materially -> re-open Basal for change.

### ISF

**Decision:** NO CHANGE  
**Hold reason:** insufficient_evidence  
**Summary:** ISF: no change recommended (insufficient evidence (confidence 0.18 below 0.50)).

**Justification:** ISF reviewed: a directional signal exists (theoretical target 16) but is held due to insufficient evidence (confidence 0.18 below 0.50). Re-evaluate at the next review.

**Expected outcomes (2-week):**

| Metric | Baseline | Expected | Direction |
|---|---|---|---|
| TIR | 57.9% | 57.9% | stable |
| TBR<70 | 1.99% | 1.99% | stable |
| TAR>180 | 40.1% | 40.1% | stable |

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

**Success criteria** (revisit in 14 days):
- Carb ratio held: glycemic metrics remain within tolerance of baseline over the 2-week window.
- No new hypoglycemia signal (TBR<70 stays below 4%).

**Stop / escalate criteria:**
- TBR<70 rises by more than 1 pp -> escalate review.
- TIR declines materially -> re-open Carb ratio for change.

## Overall justification

No parameter changes are recommended this cycle; all domains were reviewed and held with documented rationale. Held/deferred: Basal (insufficient_evidence), ISF (insufficient_evidence), Carb ratio (no_meaningful_deviation).

## Addenda

- Factors considered: time-in-range distribution, hypo/hyper burden, glycemic variability, per-parameter advisory evidence, and cross-parameter sequencing.
- Basal theoretical optimum: 2.52 (+48% vs current 1.7); held this cycle.
- ISF theoretical optimum: 16 (-60% vs current 40); held this cycle.
- Risks reviewed and mitigated: Hyperglycemia burden elevated (TAR>180 40.1% vs target 25%). Glycemic variability high (CV 37% vs target 36%).
- Mitigations: changes are bounded by a per-cycle titration cap; carb ratio is sequenced after basal/ISF to avoid confounded adjustment; explicit stop/escalate criteria accompany every recommendation for the 2-week feedback loop.

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

**Agreed plan:** Agreed plan: maintain current settings with documented rationale; re-evaluate in 2 weeks.

**Expected trajectory:** Projected time-in-range at next review: ~58% (baseline 58%). Outcome will be scored against the per-recommendation success and stop/escalate criteria.

**Follow-up date:** 2026-07-14
