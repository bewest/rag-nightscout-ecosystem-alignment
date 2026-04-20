# AID Author Recommendations — Data-Driven Findings

**Date**: 2026-04-20  
**Experiments**: EXP-2790, EXP-2792, EXP-2795, EXP-2796, EXP-2798  
**Scope**: Actionable findings for Loop, Trio, and AAPS developers  
**Patients**: 28 (Loop=9, Trio=12, OpenAPS=7)

## Executive Summary

Analysis of 28 AID patients across three controller types reveals **6 actionable findings** for open-source AID developers. The single most impactful: **96% of patients have ISF set too high**, and simply suggesting ISF reduction is almost universally correct.

---

## Finding 1: ISF Over-Estimation is Universal

**96% of patients (27/28) need ISF decreased** (EXP-2798).

| Controller | Mean ISF Correction | Direction |
|-----------|-------------------|-----------|
| Loop | -2.85 mg/dL/5min | ↓ decrease |
| Trio | -2.00 mg/dL/5min | ↓ decrease |
| OpenAPS | -2.93 mg/dL/5min | ↓ decrease |

**Settings impact (EXP-2791)**:

| Controller | Profile ISF | Recommended ISF | Change |
|-----------|-------------|-----------------|--------|
| Loop | 49 | 32 | ↓35% |
| Trio | 58 | 45 | ↓22% |
| OpenAPS | 55 | 46 | ↓16% |

**Recommendation**: After 1 week of data, proactively suggest ISF reduction. This is 96% likely to be the correct direction.

**Validation** (EXP-2795): Pipeline ISF recommendations improve BG prediction on **held-out test data** for 89% of patients (25/28). ISF direction prediction is 93% correct. 100% hypo-safe.

---

## Finding 2: Trio Basal Rates Are Severely Under-Estimated

Actual basal delivery as percentage of total daily dose (EXP-2790):

| Controller | Actual Basal % | Expected | Status |
|-----------|---------------|----------|--------|
| Loop | 22% | ~50% | Low |
| **Trio** | **9%** | ~50% | **Very low** |
| OpenAPS | 33% | ~50% | Moderate |

Trio's oref1+SMB algorithm compensates by delivering insulin through SMBs instead of scheduled basal. While TIR is excellent (87%), this represents a fragile equilibrium.

**Recommendation**: Add a "basal adequacy" warning when actual basal delivery is < 20% of TDD. Suggest increasing scheduled basal rate.

**Trio settings needed** (EXP-2791):
- Basal rate: 0.82 → 1.27 U/h (+55%)
- CR: 10 → 14 (+40%)
- ISF: 58 → 45 (-22%)

---

## Finding 3: Controller Compensation Makes Bolus Behavior Irrelevant

User bolusing behavior (timing, size, frequency) does NOT predict time-in-range (EXP-2792). The controller adjusts basal/SMB to compensate for whatever the user does.

| Predictor | Correlation with TIR |
|-----------|---------------------|
| Glucose CV | **r = -0.82** |
| Mean glucose | r = -0.71 |
| User bolus frequency | r = -0.03 (NS) |
| User bolus size | r = +0.08 (NS) |

**Recommendation**: Don't guilt users about bolus timing. Focus on settings optimization instead.

---

## Finding 4: Glucose CV is the Strongest Quality Metric

Glucose coefficient of variation (CV = std/mean) is the **single strongest predictor** of TIR across all controllers (r = -0.82, EXP-2792).

**Recommendation**: Display glucose CV prominently in AID apps as a "control quality" metric. Target: CV < 36% (standard clinical target).

---

## Finding 5: 68% of Patients Violate the 50/50 Rule

The clinical guideline that ~50% of TDD should be basal and ~50% bolus is violated by >25 percentage points in 68% of patients (EXP-2792).

| Controller | Violators (>25pp off 50/50) |
|-----------|---------------------------|
| Loop | 67% |
| Trio | 83% |
| OpenAPS | 43% |

**Recommendation**: Alert users when actual basal is < 30% or > 70% of TDD. This is a strong signal of mis-calibrated settings.

---

## Finding 6: Different Timescales for Different Tasks

Settings extraction and BG forecasting require different data resolution (EXP-2799/2800):

| Task | Best Timescale | Why |
|------|---------------|-----|
| BG forecasting | 5-min | AR momentum captures CGM dynamics |
| Settings extraction | 1-hour | Insulin physics becomes dominant |
| Circadian adjustment | 1-hour | 5× stronger signal than at 5-min |

**Recommendation**: Internal settings analysis should aggregate data to hourly bins before extracting ISF/CR recommendations.

---

## Controller-Specific Summary

### For Loop Developers
- ISF too high for most users (49 → ~32, ↓35%)
- Consider auto-suggesting ISF reduction from correction patterns
- Basal suspension rate high (65%) but delivery reasonable (22%)
- TIR: 65% (lowest of three controllers)

### For Trio / oref1 Developers
- Basal rates severely under-estimated (9% actual delivery)
- CR may be too aggressive (10 → ~14)
- Add "basal adequacy" warning when actual < 20% of TDD
- oref1+SMB compensates powerfully — **TIR: 87% (best)**
- Despite worst settings, achieves best outcomes — but fragile

### For OpenAPS / oref0 Developers
- Best-calibrated basal rates (33%, closest to 50%)
- CR needs increase (8 → ~12)
- Most physiological delivery pattern (no SMB in dataset)
- TIR: 72% (moderate)

### Universal
- Track 7-day actual basal % of TDD
- ISF over-estimation is universal — suggest reduction proactively
- Glucose CV is the best quality metric (display prominently)
- User bolusing behavior does NOT predict TIR

---

## Validation Evidence

| Claim | Experiment | Evidence |
|-------|-----------|----------|
| ISF direction 96% correct | EXP-2798 | 27/28 patients |
| ISF improves on test data | EXP-2795 | 89% (25/28) |
| ISF direction on test | EXP-2795 | 93% correct |
| Hypo safety | EXP-2795 | 100% safe, zero increase |
| Pipeline generalizes | EXP-2796 | R²=0.418, 28/28 improve |
| Actual basal 14% TDD | EXP-2790 | Corrected data semantics |
| Glucose CV best predictor | EXP-2792 | r=-0.82 |

## Visualizations

![Controller Recommendations](../../tools/visualizations/controller-recommendations/exp-2792-dashboard.png)
![Cross-Patient Transfer](../../tools/visualizations/cross-patient-transfer/exp-2798-dashboard.png)
![Prospective Validation](../../tools/visualizations/prospective-validation/exp-2795-dashboard.png)
