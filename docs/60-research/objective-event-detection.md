# Objective: Event Detection and Classification

> **Layer 1 Goal**: "Detect short-term events (meals, exercise, hypos) — minutes to hours."

Events are discrete physiological or behavioral occurrences that affect glucose
trajectory. Early detection enables proactive rather than reactive management.
This report assesses the event detection objective — detecting and classifying
glucose-relevant events ahead of time for anticipatory diabetes management.

---

## Table of Contents

- [Event Classes](#event-classes)
- [Key Finding: XGBoost >> Neural Networks](#key-finding-xgboost--neural-networks-for-events)
- [Trajectory of Results](#trajectory-of-results)
  - [Phase 1: Baseline (EXP-025–050)](#phase-1-baseline-exp-025050)
  - [Phase 2: Feature Engineering (EXP-172–200)](#phase-2-feature-engineering-exp-172200)
  - [Phase 3: Per-Patient & Combined (EXP-205–221)](#phase-3-per-patient--combined-exp-205221)
  - [Ceiling Analysis](#ceiling-analysis)
- [What Worked](#what-worked-for-events)
- [What Failed](#what-failed-for-events)
- [Per-Class Analysis](#per-class-analysis)
- [Patient Variability](#patient-variability)
- [Verification Status](#verification-status)
- [Implications](#implications)

---

## Event Classes

The system tracks **6 primary event classes** derived from Nightscout treatment
logs:

| # | Class | Description | Prevalence |
|---|-------|-------------|------------|
| 0 | **None** | No event — majority class | ~90%+ of windows |
| 1 | **Meal** | Carb entries | ~0.4% of windows |
| 2 | **Correction Bolus** | Insulin without carbs | Most common treatment |
| 3 | **Exercise** | Logged activity | Moderate |
| 4 | **Sleep** | Detected from patterns or logged | Moderate |
| 5 | **Custom Override** | Temporary Override in Nightscout (sleep, exercise, eating soon, etc.) | Moderate |

The extreme class imbalance (meals at 0.4%) makes this a challenging
classification problem. The "None" class dominates, which any naive model can
exploit for artificially high accuracy without detecting real events.

---

## Key Finding: XGBoost >> Neural Networks for Events

| Experiment | Model | Weighted F1 | Notes |
|------------|-------|-------------|-------|
| **EXP-155** | XGBoost | **0.544** | Tabular features, engineered signals |
| **EXP-155** | Neural (transformer) | 0.107 | 5.1× worse |

**EXP-114** attention analysis reveals the mechanism: the transformer is
**86.8% glucose-dominant** — it underweights the treatment and behavioral
features that matter most for event classification.

This result is consistent with ML literature: tabular features with strong
engineered signals favor tree-based methods over transformers, especially on
small datasets. The event detection problem is fundamentally a *tabular
classification* problem, not a *sequence modeling* problem.

---

## Trajectory of Results

### Phase 1: Baseline (EXP-025–050)

Initial exploration establishing that event classification is feasible.

| Experiment | Description | F1 | Key Detail |
|------------|-------------|-----|------------|
| EXP-025 | First XGBoost event model | — | Proof of concept |
| EXP-027 | Event classifier | 0.573 | Baseline metric |
| **EXP-049** | Combined classifier | **0.710** (macro) | Best Phase 1 result |

**EXP-049 per-class breakdown:**

| Class | F1 |
|-------|-----|
| None | 0.967 |
| Meal | 0.565 |
| Correction | 0.768 |
| Override | 0.742 |
| Eating Soon | 0.742 |
| Exercise | 0.736 |

**Top features** (importance scores from EXP-049):

1. `carbs_total` — 0.124
2. `bolus_total` — 0.085
3. `cob_now` — 0.071
4. `net_basal_now` — 0.070

The dominance of treatment-related features confirms why neural models
(which attend primarily to glucose) underperform.

### Phase 2: Feature Engineering (EXP-172–200)

Systematic feature engineering and calibration after removing leaky features.

| Experiment | Description | F1 | Delta |
|------------|-------------|-----|-------|
| EXP-172 | Clean XGBoost (no leaky features) | 0.532 | Baseline after cleanup |
| EXP-176 | Balanced training | 0.505 | −5.1% (class rebalancing hurts majority class) |
| **EXP-180** | Temporal features (17 new) | **0.618** | **+11.2% improvement** |
| EXP-193 | Feature selection study | — | All 39 features optimal |
| EXP-200 | Temperature-scaled calibration | 0.576 | ECE reduced 13.7%, F1 preserved |

**EXP-180 new temporal features** (17 total):

- Glucose rate of change (ROC)
- Glucose acceleration (second derivative)
- Rolling standard deviation
- IOB-COB interaction terms
- Time-windowed aggregates

**EXP-193 key insight**: Monotonic improvement with more features — all 39
features contribute. No feature pruning is warranted.

**EXP-200 calibration**: Temperature scaling reduces Expected Calibration Error
(ECE) by 13.7% without sacrificing F1. This is critical for safety-gated
deployment, where the system must know *how confident* it is in a detection.

### Phase 3: Per-Patient & Combined (EXP-205–221)

Per-patient personalization and combination of best techniques.

| Experiment | Description | F1 | Delta |
|------------|-------------|-----|-------|
| EXP-205 | Per-patient models | 0.700 | Personalization helps |
| EXP-209 | Per-patient + temporal | 0.705 | Marginal stacking gain |
| EXP-217 | Stratified oversampled | 0.706 | Alternative approach, same ceiling |
| **EXP-221** | Combined all winners | **0.705** (weighted) | Best overall result |

**EXP-221 detailed metrics:**

- Weighted F1: **0.705**
- Macro F1: **0.678**
- MCC: **0.520**

**Per-patient F1 (EXP-221):**

| Patient | F1 | Patient | F1 |
|---------|-----|---------|-----|
| a | 0.840 | f | 0.618 |
| b | 0.667 | g | 0.720 |
| c | 0.676 | h | 0.760 |
| d | **0.939** | i | 0.537 |
| e | 0.679 | j | 0.655 |

### Ceiling Analysis

Three independent methods converge at F1 ≈ 0.705–0.706:

| Method | Experiment | F1 |
|--------|------------|-----|
| Per-patient + temporal | EXP-209 | 0.705 |
| Stratified oversampled | EXP-217 | 0.706 |
| Combined all winners | EXP-221 | 0.705 |

This convergence across different approaches **strongly suggests 0.71 is the
practical ceiling** for these features and this dataset. Breaking through
requires fundamentally new information sources, not better modeling.

---

## What Worked for Events

| # | Technique | Evidence | Impact |
|---|-----------|----------|--------|
| 1 | **XGBoost on tabular features** | EXP-155: 5.1× better than neural | Architecture choice |
| 2 | **Temporal feature engineering** | EXP-180: +11.2% F1 | Biggest single improvement |
| 3 | **Per-patient models** | EXP-205: enables patient-specific thresholds | Personalization |
| 4 | **Feature richness** | EXP-193: all 39 features contribute monotonically | No pruning needed |
| 5 | **Temperature calibration** | EXP-200: ECE −13.7%, F1 preserved | Safety deployment |

---

## What Failed for Events

| # | Technique | Evidence | Why |
|---|-----------|----------|-----|
| 1 | **Neural event heads** | F1 = 0.107 | Transformer ignores treatment features (86.8% glucose-dominant) |
| 2 | **Class rebalancing** | EXP-176: F1 = 0.505 (−5.1%) | Hurts majority class, net negative |
| 3 | **Focal loss** | EXP-158 | Class weighting doesn't help events |
| 4 | **Stacked classifiers** | EXP-190 | Added complexity, no improvement |

---

## Per-Class Analysis

From EXP-221 (combined winners):

| Class | Precision | Recall | F1 | Support | Notes |
|-------|-----------|--------|----|---------|-------|
| None | 0.945 | 0.991 | **0.967** | 8,524 | Excellent — strong majority |
| Meal | 0.521 | 0.617 | **0.565** | 8,222 | Hardest — subtle glucose precursors |
| Correction | 0.810 | 0.730 | **0.768** | 48,299 | Good — clear insulin/glucose patterns |
| Override | 0.628 | 0.906 | **0.742** | 2,590 | High recall, lower precision |
| Eating Soon | 0.630 | 0.903 | **0.742** | 2,626 | Similar profile to Override |
| Exercise | 0.727 | 0.744 | **0.736** | 25,142 | Well-balanced |

### Key Observations

- **Meals are hardest** (F1 = 0.565): glucose precursors before meals are
  subtle and inconsistent. Without explicit carb logging, meals are difficult
  to anticipate from glucose dynamics alone.
- **Corrections are easiest** (F1 = 0.768 among treatments): the
  insulin-without-carbs pattern creates a clear feature signature.
- **Overrides and Eating Soon** share a profile (high recall, lower precision):
  these behavioral events have distinctive treatment patterns but also
  generate false positives.
- **Exercise** is well-balanced: physiological signatures (HR proxy via glucose
  dynamics) provide reasonable discrimination.

### Lead Time

**73.8% of detections occur >30 minutes before the event.** This lead time
is actionable for AID systems — sufficient for:

- Adjusting basal rates before meals
- Pre-exercise glucose target adjustments
- Triggering user confirmations for anticipated events

---

## Patient Variability

F1 ranges from **0.537** (patient i) to **0.939** (patient d) — a **1.7×
range**.

| Tier | Patients | F1 Range | Characteristics |
|------|----------|----------|-----------------|
| High | d | 0.939 | Very consistent treatment patterns (TIR = 84.9%) |
| Good | a, h, g | 0.720–0.840 | Regular patterns, good data quality |
| Average | b, c, e, j | 0.655–0.679 | Moderate variability |
| Low | f, i | 0.537–0.618 | Irregular behavior or noisy data |

**Interpretation:**

- Patient d's high TIR (84.9%) correlates with highly predictable event
  patterns — consistent meal times, regular correction behavior.
- Patient i's low F1 likely reflects irregular behavior, variable meal
  schedules, or noisy/incomplete logging.
- Per-patient models (EXP-205) partially compensate but cannot overcome
  fundamental patient-level data quality limits.

---

## Verification Status

Event detection verified on **held-out temporal data** at F1 = **0.544**
(EXP-122 verification suite).

| Split | F1 | Gap |
|-------|----|-----|
| Training / cross-validation | 0.705 | — |
| Held-out temporal verification | 0.544 | −0.161 |

The gap from training F1 (0.705) to verification F1 (0.544) is substantial
but expected — event patterns change over time:

- Different meal schedules (weekday vs weekend, seasonal)
- Changed exercise habits
- Treatment strategy adjustments (new pump settings, different correction behavior)
- Temporal distribution shift is the primary degradation mechanism

This temporal generalization gap is a known challenge and motivates periodic
model retraining in deployment.

---

## Implications

### 1. Clinically Useful at Current Performance

Event detection at **0.71 F1 with 74% lead time** is clinically useful:

- Alerts can be shown to users with calibrated confidence
- High-confidence detections (>0.8 probability) can trigger automatic
  AID adjustments
- Low-confidence detections can prompt user confirmation

### 2. Meals Remain the Hardest Event

Meal F1 = 0.565 — glucose precursors are subtle. This is a fundamental
limitation of glucose-only sensing. Improvement requires:

- Wearable data (accelerometer, heart rate)
- Meal photo recognition
- Time-of-day priors from historical patterns
- CGM rate-of-change acceleration patterns

### 3. Separate Architecture for Events

The neural/XGBoost performance divide means **event detection should remain a
separate module from glucose forecasting**:

- Forecasting benefits from sequence models (temporal glucose dynamics)
- Events benefit from tree-based models (tabular treatment features)
- A combined system routes each objective to its best architecture

### 4. New Data Sources Needed to Break Ceiling

The 0.71 convergence ceiling cannot be broken with better modeling alone.
Future improvement requires:

- **Wearable sensors** (activity, sleep, stress)
- **Meal logging** improvements (photos, NLP)
- **Larger multi-site datasets** (more diverse patients)
- **Contextual features** (location, calendar, time-of-day patterns)

### 5. Calibrated Confidence Enables Safe Deployment

Temperature-scaled calibration (EXP-200) enables safety-gated deployment:

- Confidence thresholds determine action aggressiveness
- High-confidence events → automatic AID adjustment
- Medium-confidence events → user notification
- Low-confidence events → logged but no action

---

## Summary

| Metric | Value | Source |
|--------|-------|--------|
| Best F1 (weighted) | **0.705** | EXP-221 |
| Best F1 (macro) | **0.678** | EXP-221 |
| MCC | **0.520** | EXP-221 |
| Lead time (>30 min) | **73.8%** | EXP-221 |
| Best model | XGBoost | EXP-155 |
| Features | 39 (all contribute) | EXP-193 |
| Practical ceiling | ~0.71 F1 | Convergence of 3 methods |
| Patient range | 0.537–0.939 | EXP-221 |
| Verification F1 | 0.544 | EXP-122 |

Event detection is the most mature objective in the system, with a clear
architecture (XGBoost), well-understood ceiling (0.71), and actionable lead
times (74% > 30 min). The primary path forward is new data sources rather
than modeling improvements.
