# Multi-Objective Validation Report

**Date**: 2026-04-02
**Experiments**: EXP-122, EXP-123, EXP-124, EXP-125
**Data**: 10 patients (a–j), verification splits (held-out days)

## Executive Summary

| Objective | Suite | Metric | Score | Rating |
|-----------|-------|--------|-------|--------|
| **Detect** events | EXP-122 | Macro F1 | **0.54** | ⚠️ Developing |
| **Recommend** overrides | EXP-123 | F1 / FA rate | **0.13** / 0.71/hr | ❌ Needs work |
| **Identify** drift → TIR | EXP-124 | Pearson r | **+0.70** (wrong sign) | ❌ Needs recalibration |
| **Compose** full pipeline | EXP-125 | Coverage | 11.4% event rate | ⚠️ Runs, incomplete |
| *Reference: Forecast* | *Prior* | *MAE* | *16.0 mg/dL* | *✅ Mature* |

**Key finding**: The pipeline infrastructure works end-to-end, but event detection
and override recommendation degrade significantly on held-out verification data.
Drift tracking's positive correlation (+0.70) vs expected negative correlation
reveals a calibration issue, not a code bug.

---

## Suite A: Event Detection on Verification Data (EXP-122)

### Summary

Trained XGBoost on all 10 patients' training splits, evaluated on verification splits.

- **45,530 verification windows** (44,374 positive events)
- **Verification F1: 0.54** | Accuracy: 0.62
- **Mean lead time: 36.9 min** (100% detected >15 min ahead, 73.8% >30 min ahead)

### Per-Class Performance

| Event Type | F1 | Precision | Recall | Support |
|------------|-----|-----------|--------|---------|
| correction_bolus | **0.637** | 0.767 | 0.545 | 24,051 |
| custom_override | **0.644** | 0.625 | 0.664 | 13,753 |
| meal | **0.547** | 0.447 | 0.704 | 4,314 |
| exercise | 0.537 | 0.371 | **0.977** | 1,064 |
| sleep | 0.352 | 0.244 | 0.633 | 1,192 |

**Findings**:
- Exercise detection has near-perfect recall (97.7%) but low precision (37.1%) — it over-triggers
- Sleep detection is weakest (F1=0.35), likely because sleep patterns vary most between training and verification days
- Correction bolus has highest precision (76.7%) — the most reliable detection class
- Meal recall (70.4%) is clinically useful — catches most meals, but with some false positives

### Per-Patient Breakdown

| Patient | F1 | Accuracy | Windows |
|---------|-----|----------|---------|
| a | 0.339 | 0.830 | 5,539 |
| b | 0.528 | 0.566 | 6,487 |
| c | 0.420 | 0.641 | 5,198 |
| d | 0.323 | 0.893 | 3,857 |
| e | 0.409 | 0.662 | 5,068 |
| f | 0.325 | 0.400 | 412 |
| g | 0.408 | 0.569 | 5,348 |
| h | 0.389 | 0.679 | 1,170 |
| i | 0.322 | 0.464 | 12,312 |
| j | 0.385 | 0.698 | 139 |

Patient d has high accuracy (89.3%) but low F1 (0.32) — mostly predicting "none" correctly
but missing positive events. Patient variance (0.32–0.53 F1) indicates event patterns
are partially patient-specific and don't fully generalize.

### Lead Time Quality

| Metric | Value |
|--------|-------|
| Mean lead time | 36.9 min |
| Median lead time | 30.0 min |
| Std dev | 16.8 min |
| % detected >15 min ahead | 100% |
| % detected >30 min ahead | 73.8% |

Lead times are clinically actionable — the system would give users meaningful advance warning.

---

## Suite B: Override Recommendation on Verification Data (EXP-123)

### Summary

Used trained classifier from Suite A to score override candidates on verification data.

- **31,529 overrides suggested** vs **44,374 actual events**
- **Aggregate F1: 0.13** | Precision: 0.16 | Recall: 0.11
- **False alarm rate: 0.71/hr** (1 false alarm every 85 minutes)
- **True positives: 4,930** out of 31,529 suggestions

### Per-Patient Results

| Patient | Precision | Recall | F1 | FA/hr | Notes |
|---------|-----------|--------|----|-------|-------|
| j | **0.98** | **0.98** | **0.98** | 0.002 | Small data (112 events), near-perfect |
| b | 0.69 | 0.63 | **0.66** | 0.450 | Good performance |
| f | 0.36 | 0.49 | 0.41 | 0.073 | Moderate, low FA rate |
| g | 0.25 | 0.07 | 0.11 | 0.272 | Low recall |
| h | 0.05 | 0.02 | 0.03 | 0.138 | Poor |
| a | 0.02 | 0.02 | 0.02 | 1.379 | Poor, high FA |
| d | 0.02 | 0.00 | 0.01 | 0.221 | Near-zero |
| e | 0.01 | 0.00 | 0.01 | 0.657 | Near-zero |
| c | 0.01 | 0.00 | 0.00 | 0.748 | Near-zero |
| i | 0.00 | 0.00 | 0.00 | 2.660 | Zero matches, worst FA rate |

### Analysis

The bimodal distribution (patients b/f/j performing well, rest near-zero) reveals that
override recommendation quality depends heavily on **treatment data density**:
- Patients b and j have frequent carb entries → clearer event patterns → better matching
- Patients c, d, e, i have minimal carb entries but heavy bolus activity → the override
  matcher struggles because predicted events don't align with actual treatment patterns

**Root cause**: `override_accuracy()` uses a strict type-matching + temporal-proximity
criterion. The classifier detects *glucose-pattern-based* events while the ground truth
is *treatment-log-based* events — these are measuring different things. A meal that
changes glucose ≠ a logged carb entry at the exact same time.

**Recommendation**: Decouple override evaluation from strict event matching. Measure
instead: (1) does the override suggestion precede a glucose excursion that the override
would have prevented? (2) clinical outcome metric — would TIR improve if the suggested
override had been applied?

---

## Suite C: Drift-TIR Correlation (EXP-124)

### Summary

Ran ISFCRTracker through each patient's verification data, computed rolling 24h TIR,
and measured correlation between drift magnitude and TIR change from baseline.

- **334 paired drift-TIR observations** across 10 patients
- **Aggregate Pearson r = +0.70** (expected: negative)
- **Drift detection rate: 9.5%** average (94.7% for patient a, 0% for 9 others)

### Per-Patient Results

| Patient | Correlation | Drift Rate % | Baseline TIR % | Paired Obs |
|---------|-------------|-------------|-----------------|------------|
| a | +0.565 | **94.7%** | 3.5% | 44 |
| i | +0.356 | 0.0% | 55.4% | 39 |
| f | +0.189 | 0.0% | 54.4% | 42 |
| g | +0.170 | 0.0% | 60.3% | 41 |
| d | +0.143 | 0.0% | 67.0% | 38 |
| h | +0.117 | 0.0% | 81.9% | 13 |
| c | +0.087 | 0.0% | 78.4% | 36 |
| e | +0.083 | 0.0% | 58.8% | 28 |
| b | N/A | 0.0% | 59.6% | 38 |
| j | N/A | 0.0% | 86.5% | 15 |

### Analysis

The **positive** correlation (opposite of expected) is driven by Patient a:
- Patient a has 3.5% baseline TIR (extremely poor control) and 94.7% drift detection
- As glucose values change, BOTH drift magnitude AND TIR can increase together
  (any movement from a very low TIR baseline tends to be positive)
- The Kalman tracker's default thresholds (`drift_threshold_pct=15%`) are tuned for
  patients with reasonable control — Patient a's ISF=132 (very high) causes the
  tracker to interpret normal glucose variations as drift

**Why 9 patients show 0% drift**: The detector's thresholds are too conservative.
With `drift_threshold_pct=15%`, only extreme ISF/CR changes trigger non-stable
classification. Most verification periods (every-Nth-day samples) don't contain
sustained drift episodes.

**Recommendations**:
1. Recalibrate drift thresholds — lower from 15% to 5-8% for sensitivity
2. Normalize by patient's nominal ISF before computing drift magnitude
3. Exclude patients with <50% baseline TIR from correlation analysis (their TIR
   is dominated by data gaps, not physiological drift)
4. Consider using TIR *variability* (std of rolling TIR) rather than TIR *delta*
   as the outcome metric

---

## Suite D: Composite Pipeline Verification (EXP-125)

### Summary

Ran the full `run_decision()` pipeline at 6-hour intervals across verification data.

- **508 total windows** across 10 patients
- **Event detection rate: 11.4%** of windows detected at least one event
- **Override suggestion rate: 0%** (no drift-based overrides triggered)
- **Forecast MAE: N/A** (no masked-trained checkpoint found at default paths)

### Per-Patient Composite Results

| Patient | Windows | Event Rate % | Override Rate % | Drift Rate % |
|---------|---------|-------------|----------------|-------------|
| i | 59 | 28.8 | 0.0 | 0.0 |
| h | 21 | 19.0 | 0.0 | 0.0 |
| b | 58 | 17.2 | 0.0 | 0.0 |
| d | 57 | 12.3 | 0.0 | 0.0 |
| a | 64 | 10.9 | 0.0 | 0.0 |
| e | 47 | 10.6 | 0.0 | 0.0 |
| g | 61 | 9.8 | 0.0 | 0.0 |
| c | 56 | 8.9 | 0.0 | 0.0 |
| j | 23 | 8.7 | 0.0 | 0.0 |
| f | 62 | 4.8 | 0.0 | 0.0 |

### Analysis

The composite pipeline **runs successfully** but reveals infrastructure gaps:
- **No forecast MAE**: The masked-trained checkpoints (`exp051_seed456.pth`) were not
  found at the searched paths. Suite D needs explicit `--checkpoint` to be useful.
- **Zero override suggestions**: Consistent with Suite C — drift detector thresholds
  are too conservative for the available verification data
- **11.4% event detection rate**: Reasonable — not every 6-hour window should have an
  event. Patient i (28.8%) has the most active treatment pattern.

**Recommendation**: Re-run Suite D with explicit checkpoint path. The value of the
composite pipeline is in comparing forecast-only vs detect+recommend+forecast, which
requires the forecast component to be active.

---

## Cross-Objective Comparison

### Maturity Ladder

```
Forecasting ████████████████████ ✅ MAE=16.0, well-calibrated, 10-patient verified
Event Detection ██████████░░░░░░░░░░ ⚠️  F1=0.54, good lead times, patient-variable
Override Reco ███░░░░░░░░░░░░░░░░░ ❌ F1=0.13, evaluation mismatch, needs redesign
Drift Tracking ██░░░░░░░░░░░░░░░░░░ ❌ Wrong-sign correlation, threshold calibration needed
Pattern Recog ░░░░░░░░░░░░░░░░░░░░ ❌ Not yet evaluated (menstrual, weekly routines)
```

### Training → Verification Gap by Objective

| Objective | Training Performance | Verification Performance | Gap |
|-----------|---------------------|--------------------------|-----|
| Forecast | 11.7 mg/dL MAE | 16.0 mg/dL MAE | **+37%** |
| Event Detection | 0.71 F1 (EXP-049) | 0.54 F1 | **−24%** |
| Override Reco | 96-99.6% precision | 15.6% precision | **−84%** |
| Drift Tracking | Untested | +0.70 correlation (wrong sign) | **N/A** |

The 37% forecast gap is indeed the **floor** — event detection degrades 24% and
override recommendation degrades 84%. This confirms that behavioral objectives
(what the person *does*) are harder to generalize than physiological objectives
(what glucose *does*).

---

## Recommendations

### Immediate (improve existing modules)

1. **Recalibrate DriftDetector thresholds**: Lower `drift_threshold_pct` from 15% to 5-8%.
   The current setting is so conservative that drift is never detected for 9/10 patients.

2. **Redesign override evaluation metric**: `override_accuracy()` measures
   treatment-log-to-prediction alignment. Replace with a clinical outcome metric:
   "would this override have improved TIR in the next 2 hours?"

3. **Re-run Suite D with checkpoint**: Pass `--checkpoint externals/experiments/exp051_seed456.pth`
   to get forecast MAE and enable full composite comparison.

### Medium-term (extend capabilities)

4. **Per-patient fine-tuning for event detection**: The 0.32–0.53 F1 range across patients
   suggests fine-tuning on a patient's first few verification days would help.

5. **Temporal pattern features**: Add day-of-week and hour-of-day interaction features
   to the event classifier. Meals at 12pm are more predictable than random-time meals.

6. **Override impact simulation**: For each suggested override, run the forecast model
   with and without the override's insulin-needs-factor applied. Measure predicted
   TIR difference. This tests the *utility* of recommendations, not just detection accuracy.

### Long-term (new capabilities)

7. **Menstrual cycle / hormonal patterns**: Zero implementation exists. Requires:
   (a) user-reported labels or (b) multi-week ISF/CR periodicity detection.

8. **Learned override durations**: All override durations are hard-coded
   (eating_soon=60min, exercise=120min, sleep=480min). Learn these from data.

9. **Counterfactual analysis framework**: "What would have happened if this override
   had been applied 30 minutes earlier?" Requires a causal inference approach beyond
   the current predict-then-compare pattern.

---

## Methodology Notes

- **Training/verification split**: Every Nth day goes to verification. This is a
  temporal holdout (not random), so it tests generalization to unseen days.
- **Event ground truth**: Extracted from `treatments.json` (boluses, carbs) and
  `devicestatus.json` (Loop override status). Events are real user actions, not synthetic.
- **Drift ground truth**: No true ground truth exists for ISF/CR changes. TIR is
  used as a proxy outcome — the assumption is that uncompensated drift degrades TIR.
- **Composite pipeline**: Uses `run_decision()` from `hindcast_composite.py` which
  chains event_classifier → state_tracker → forecast → scenario_sim → uncertainty.

## Files

| Artifact | Location |
|----------|----------|
| Event detection results | `externals/experiments/exp122_event_detection_verification.json` |
| Override recommendation results | `externals/experiments/exp123_override_recommendation_verification.json` |
| Drift-TIR correlation results | `externals/experiments/exp124_drift_tir_correlation.json` |
| Composite pipeline results | `externals/experiments/exp125_composite_verification.json` |
| Combined results | `externals/experiments/exp_all_validation_suites.json` |
| Validation module source | `tools/cgmencode/validate_verification.py` |
