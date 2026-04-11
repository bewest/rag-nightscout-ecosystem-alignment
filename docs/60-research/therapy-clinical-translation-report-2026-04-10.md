# Therapy Clinical Translation & Actionability Report

**Experiments**: EXP-1481 through EXP-1490  
**Date**: 2026-04-10  
**Campaign**: Therapy Detection & Recommendation (experiments 201–210)  
**Patients**: 11 (a–k), ~180 days each, ~50K timesteps per patient

## Executive Summary

This batch translates pipeline findings into clinically actionable outputs. Key breakthroughs: 9/11 patients are insulin-sensitive phenotype (AID reduces effective ISF), dose-response curves have very low R² (0.003-0.082) confirming AID confounding, ISF circadian amplitude averages 12.3 mg/dL/U absolute (mean 16.9% of mean ISF) but sinusoidal fit R² is poor (<0.03 for 10/11), and **pipeline-vs-ADA guideline alignment is only 64%** — primarily because the pipeline ignores time-below-range (TBR) which ADA considers critical. Carb counting quality scores reveal systematic overcounting bias in 9/11 patients.

## Experiment Results

### EXP-1481: Treatment-Response Phenotyping

**Findings**:
- **9/11 classified as insulin_sensitive** — high glucose drop per insulin unit
- Patient a: carb_sensitive (large glucose rise per gram, moderate insulin response)
- Patient f: balanced (moderate on both axes)
- Insulin response range: 17-310 mg/dL per unit (enormous variation)
- Correction effectiveness: 0-87% (patient k has 0% — no corrections needed)

**Clinical Implication**: The "insulin_sensitive" dominance likely reflects AID amplification — temp basal adjustments compound manual bolus effects. Phenotyping should account for AID contribution to distinguish true sensitivity from algorithmic amplification.

---

### EXP-1482: Empirical Dose-Response Curves

**Findings**:
- **R² extremely low**: 0.002-0.082 for 10/11 patients (patient j: 0.329 but only 7 events)
- Empirical ISF slopes: -5.9 to 76.6 mg/dL per unit (2 patients have negative slopes!)
- Residual std: 15.7-90.1 mg/dL — glucose outcome is highly unpredictable from bolus size alone
- Profile-vs-empirical ISF ratio: 0.11-76.6× (wildly inconsistent)

**Clinical Implication**: Simple dose-response relationships don't hold in AID-managed patients. The AID algorithm's real-time adjustments confound the bolus→glucose relationship. Dose-response curves are NOT suitable for ISF calibration in AID users.

---

### EXP-1483: ISF Circadian Modeling

**Findings**:
- Mean ISF amplitude: 12.3 mg/dL/U absolute (mean 16.9% of mean ISF; range 5.4-72.8%)
- **Sinusoidal fit R² < 0.03 for 10/11 patients** — circadian pattern is real but noisy
- Patient j: R²=0.52 (only 7 events — overfitting)
- Common pattern: peak sensitivity overnight (hour 0-5), trough afternoon (hour 12-17)
- Patient d has clinically relevant amplitude: 16.8% with peak at hour 19

**Clinical Implication**: ISF varies predictably across the day but the variation is obscured by meal/bolus noise. Simple sinusoidal models are too crude — a 4-segment (overnight/morning/afternoon/evening) average would be more practical than a continuous model.

---

### EXP-1484: Personalized Target Setting

**Findings**:
- Glucose mode: 85-145 mg/dL (wide range across patients)
- IQR width: 17-91 mg/dL (patient k=17, patient a=91)
- Personalized targets would improve apparent TIR for 9/11 patients (+2.7 to +28.0%)
- **Patient k: personalized range WORSENS TIR** (-22.1%) because tight control means 70-180 is already generous
- Patient h: slight worsening (-3.1%) — already well-targeted

**Clinical Implication**: Personalized targets are misleading — they inflate TIR by relaxing standards for poor-control patients and tightening for good-control patients. Standard 70-180 should remain the universal benchmark. Per-patient targets useful only for setting individual glucose targets in AID systems.

---

### EXP-1485: Carb Counting Quality Score

**Findings**:
- **9/11 patients systematically overcount carbs** (median ratio < 1.0)
- Patient g: extreme undercounting (ratio=26.2 — likely missing boluses, not carb error)
- Patient d: only true undercounter (ratio=1.84)
- Quality scores: 0-69 out of 100 (no patient achieves "good" counting)
- Best counters: i (69), b (59), f/k (53)

**Clinical Implication**: Systematic overcounting (entering more carbs than consumed) leads to larger boluses and potential hypoglycemia. However, AID systems partially compensate. Patient g's extreme ratio suggests data quality issues rather than counting errors. CR adjustments should account for systematic counting bias.

---

### EXP-1486: AID Algorithm Parameter Inference

**Findings**:
- Inferred target glucose: 64-149 mg/dL (wide range)
- Effective max IOB: 0.0-12.8 U (patients b,j have 0 — likely open-loop or minimal AID)
- Correction aggressiveness: -0.022 to -0.230 (all negative = glucose-dependent correction)
- Suspend threshold: 39-53 mg/dL (consistently near 40 for most)
- Patient i: unusually low target (64 mg/dL) — aggressive settings

**Clinical Implication**: AID parameter inference reveals significant variation in how aggressively each patient's system is configured. Patients with low targets (<90) and high max IOB (>10) are running aggressive configurations that may contribute to hypoglycemia.

---

### EXP-1487: Therapy Change Impact Prediction

**Findings**:
- Basal +10% impact: varies widely (-25% to +0% TIR change depending on natural variance)
- CR -30% excursion reduction: 19.9-81.2 mg/dL mean post-meal glucose
- ISF +10% correction success: 0-100% (highly variable)
- Natural experiment sample sizes: 0-523 for basal, 21-334 for CR, 2-215 for ISF
- Patient f: basal+10% shows TIR drop to 40.2% — contradicts expectation

**Clinical Implication**: Natural experiments provide directional guidance but sample sizes are often too small for reliable impact estimates. The approach works best for CR (most meal events) and worst for ISF (fewest isolated correction events).

---

### EXP-1488: Long-Term Outcome Projection

**Findings**:
- 3-month projected TIR: 59.8-100.0% (optimistic for patients with positive trends)
- Patients with negative trends (a, c, d, g, i, k): projected decline despite therapy fixes
- Patient f: strongest positive trajectory (65.5→95.9% at 12mo)
- Patient a: therapy fixes offset by negative trend (55.8→60.6→45.0)
- Trend dominates long-term projection for 6/11 patients

**Clinical Implication**: Long-term projections are unreliable beyond 3 months — trend extrapolation amplifies small slopes into large changes. Projections useful for motivational purposes (show potential improvement) but should not be used for clinical planning.

---

### EXP-1489: Clinical Report Generation

**Findings**:
- Urgency distribution: 1 immediate, 8 soon, 1 routine, 1 monitoring-only
- Mean report length: 117 words (concise and actionable)
- Key concerns per patient: 1-3 (mean 2)
- Recommendations per patient: 1-3 (mean 2)
- Hypo risk: 7 low, 3 moderate (c, h, k), 1 high (i)

**Clinical Implication**: Reports are appropriately concise for clinical workflow integration. The hypo risk flagging identifies patients c, h, i, and k for additional safety monitoring — this information was NOT in the original pipeline v9 and should be added.

---

### EXP-1490: Validation Against Clinical Guidelines (ADA/AACE)

**Findings**:
- **Mean pipeline-ADA alignment: 0.64 (64%)** — significant discrepancies
- Key discrepancy: **Pipeline ignores TBR** — 4/11 patients have TBR>4% (ADA threshold) but pipeline doesn't flag it
- Patient d: meets ALL ADA targets (TIR=79.2%, TBR=0.8%, CV=30.4%) but pipeline grades as C
- Patient k: pipeline grades A but ADA flags TBR=4.9% (above 4% threshold)
- Patients c, h, i: ADA flags excessive TBR not reflected in pipeline

**Discrepancy Analysis**:

| Type | Count | Description |
|------|-------|-------------|
| Pipeline too lenient on TBR | 4/11 | Patients with >4% TBR not flagged |
| Pipeline too strict on TIR | 3/11 | Patients meeting ADA TIR but graded C |
| Aligned | 2/11 | Full agreement (e, f) |
| Mixed | 2/11 | Partial alignment |

**Clinical Implication**: **Critical finding — the pipeline needs a TBR component.** Time-below-range is a safety metric that ADA considers essential. Adding TBR<4% as a mandatory check would improve guideline alignment from 64% to an estimated 85%+.

---

## Key Findings Summary

| # | Finding | Impact |
|---|---------|--------|
| 1 | 9/11 insulin-sensitive phenotype | AID amplifies apparent sensitivity |
| 2 | Dose-response R²<0.08 — AID confounds | Can't calibrate ISF from bolus outcomes |
| 3 | ISF circadian amplitude 12.3 mg/dL/U but R²<0.03 | Real pattern, noisy measurement |
| 4 | Personalized targets inflate TIR artificially | Keep standard 70-180 benchmark |
| 5 | 9/11 systematically overcount carbs | Compensated by AID but adds risk |
| 6 | AID target range 64-149 mg/dL | Configuration variation is huge |
| 7 | Natural experiments: CR best, ISF worst | Sample size limits ISF estimation |
| 8 | Projections unreliable beyond 3 months | Trend extrapolation amplifies errors |
| 9 | Clinical reports average 117 words | Appropriate for workflow integration |
| 10 | **Pipeline-ADA alignment only 64% — TBR missing** | Critical gap to address |

## Pipeline v10 Recommendation

Based on EXP-1490 guideline validation, Pipeline v10 should add:

```
NEW: TIME-BELOW-RANGE SAFETY CHECK
  TBR < 4% (time below 70 mg/dL) — ADA mandatory
  TBR < 1% (time below 54 mg/dL) — ADA mandatory
  If TBR exceeds threshold:
    - Flag as safety concern
    - Adjust ISF recommendation conservatively
    - Add "reduce correction aggressiveness" to recommendations
    - Increase follow-up frequency

NEW: HYPO RISK SCORING (from EXP-1489)
  Low: TBR<4%, no stacking, insulin_sensitive=false
  Moderate: TBR 4-8%, stacking<10/wk, OR insulin_sensitive
  High: TBR>8%, stacking>10/wk, AND insulin_sensitive

UPDATED GRADING (incorporate TBR):
  Score = TIR*0.5 + (100-CV*2)*0.25 + overnight_TIR*0.1 + (100-TBR*10)*0.15
  This gives TBR 15% weight, matching ADA emphasis on safety
```

## Campaign Status: 210 Experiments

20 batches complete (EXP-1281-1490). Pipeline v9→v10 evolution identified.
Next priority: implement TBR integration and re-validate against ADA guidelines.
