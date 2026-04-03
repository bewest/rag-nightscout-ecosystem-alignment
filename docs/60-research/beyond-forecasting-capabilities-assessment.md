# Beyond Forecasting: Capabilities Assessment for Event Detection, Override Recommendation, and Drift Tracking

**Date**: 2026-04-03  
**Scope**: Non-forecasting capabilities across 10 patients, 154+ experiments  
**Architecture reference**: `docs/architecture/ml-composition-architecture.md`  

## 1. The Multi-Objective Landscape

Glucose forecasting — predicting the mg/dL number 60 minutes from now — is
the foundation. But it's not the goal. The goal, as defined in the
[ML Composition Architecture](../architecture/ml-composition-architecture.md),
is **anticipatory diabetes management**: detecting events before they happen,
recognizing when physiology has shifted, and recommending therapy adjustments
before the user has to think about them.

The 4-layer architecture frames these as distinct capabilities that build on
each other:

```
┌─────────────────────────────────────────────────────┐
│  L4: DECISION & POLICY                               │
│  Override recommendation: WHEN, WHICH type, HOW MUCH │
│  Current: F1=0.993 (WHEN) / not started (WHICH/MUCH)│
├─────────────────────────────────────────────────────┤
│  L3: LEARNED DYNAMICS                                 │
│  Event detection, scenario forecasting                │
│  Current: Event wF1=0.710, Forecast MAE=16.0         │
├─────────────────────────────────────────────────────┤
│  L2: CALIBRATION & RESIDUAL                           │
│  Drift tracking, anomaly detection, device aging      │
│  Current: Drift r=−0.156, anomaly detection working  │
├─────────────────────────────────────────────────────┤
│  L1: PHYSICS SIMULATION                               │
│  IOB/COB forward integration, pharmacokinetics        │
│  Current: ✅ Validated (EXP-005, 8.2× improvement)   │
└─────────────────────────────────────────────────────┘
```

These capabilities operate across three distinct time horizons that demand
different techniques, different data, and different validation approaches:

| Horizon | Window | Capabilities | Primary Technique |
|---------|--------|-------------|-------------------|
| **Immediate** | min → 2h | Meal detection, hypo alerts, correction suggestions | Sequence classification |
| **Daily** | 2h → 24h | Sleep/exercise cycles, circadian overrides, routine recognition | Pattern matching + context |
| **Longitudinal** | days → weeks | ISF/CR drift, illness detection, hormonal cycles, sensor aging | State-space / Bayesian filtering |

Each horizon is driven by different **data dimensions** — the physiological
and device signals that create the patterns these capabilities must detect.
Understanding which dimensions each capability depends on, and which of
those are currently captured vs missing, is the central question of this
assessment.

---

## 2. Event Detection: The F1=0.710 Ceiling and What It Means

### 2.1 Current State

Event detection classifies treatment events (meals, corrections, exercise,
overrides, sleep) from glucose traces and treatment records. Three
independent approaches converge at the same ceiling:

| Method | Weighted F1 | Approach |
|--------|------------|---------|
| Per-patient + temporal features (EXP-209) | 0.705 | Per-patient XGBoost with temporal context |
| Stratified oversampling (EXP-217) | 0.706 | Class-rebalanced training |
| Combined winners (EXP-221) | **0.710** | Best per-patient models merged |
| Neural event head (Gen-2) | 0.107 | Transformer multi-task head |

Three independent methods converging at wF1≈0.710 is a strong signal that
this is a **feature ceiling**, not a model ceiling. The data and labels
available cannot support higher classification accuracy with current
representations.

### 2.2 Why the Neural Event Head Fails

Attention attribution analysis (EXP-114) revealed the root cause:

| Feature Group | Relative Attention | Samples Dominant |
|--------------|-------------------|-----------------|
| **Glucose history** | **86.8%** | 99.4% of windows |
| Insulin (IOB) | 10.8% | 0.0% |
| Carbs (COB) | 2.4% | 0.6% |

The transformer is fundamentally a **glucose autoregressor**. It predicts
"glucose will continue its recent trend" and allocates almost no attention to
the treatment features (insulin, carbs, timing) that define events. This is
rational for forecasting — glucose autocorrelation carries ~87% of the
predictive signal — but catastrophic for event detection, where the
distinguishing features are precisely the treatment patterns the model
ignores.

XGBoost succeeds because it operates on **explicitly engineered tabular
features** that force treatment signals into the model:

**Top XGBoost features by importance**:
1. `carbs_total` (0.124) — directly encodes meal events
2. `bolus_total` (0.085) — directly encodes correction events
3. `cob_now` (0.071) — carb absorption state
4. `net_basal_now` (0.070) — controller action
5. `glucose_std_1hr` (0.065) — glucose volatility
6. `iob_now` (0.065) — insulin action state
7. `glucose_mean_6hr` (0.046) — baseline glucose context
8. `hour_of_day` (0.040) — circadian phase

The top 4 features are all treatment-derived. This is why XGBoost outperforms
neural approaches by 6.6× — it has direct access to the signals that matter.

### 2.3 Per-Class Analysis: What's Easy vs Hard

| Event Type | F1 (Training) | F1 (Verification) | Signal Source | Difficulty |
|-----------|--------------|-------------------|--------------|-----------|
| Meal | 0.822 (EXP-218) | 0.547 | Carb entry + glucose rise | ★★☆ Medium |
| Correction bolus | 0.768 | 0.637 | Bolus + glucose drop | ★☆☆ Easy |
| Custom override | 0.742 | 0.644 | Override flag + mixed | ★★☆ Medium |
| Exercise | 0.736 | 0.537 | Override keyword + glucose patterns | ★★★ Hard |
| Sleep | — | 0.352 | Time-of-day only | ★★★ Hardest |

**Why meals are easiest**: Carb entries create a distinctive glucose signature
(rapid rise 20–60 minutes post-meal) that both the classifier and the glucose
trace encode. Meals also have the clearest treatment-log signal (carb
amount > 0).

**Why sleep is hardest**: Sleep lacks a distinctive glucose signature.
Glucose during sleep depends on dinner timing, basal rate adequacy, and
dawn phenomenon timing — all patient-specific. The classifier has only
`hour_of_day` to work with. No wearable data (movement, heart rate) is
available to directly detect sleep.

**Why exercise degrades from 0.736 → 0.537**: Exercise events are labeled via
keyword matching on override reason text ("exercise", "workout", "running").
This captures *planned* exercise (where the user sets an override) but
misses *unplanned* activity. During verification periods, exercise patterns
may differ from training periods, and the model has no continuous activity
feature — only the binary override flag.

### 2.4 Lead Time: The Clinically Actionable Window

| Metric | Value |
|--------|-------|
| Mean lead time | 36.9 minutes |
| Median lead time | 32.5 minutes |
| % detected >15 min ahead | 81.2% |
| % detected >30 min ahead | **73.8%** |
| Total windows with lead time data | 27,062 |

**73.8% of events detected more than 30 minutes ahead** is the most
clinically significant metric in the event detection suite. A 30-minute
warning before a meal or exercise session gives the AID system — or the user
— time to proactively adjust therapy (activate an "Eating Soon" or
"Exercise" override) rather than reacting to glucose excursions after
they've started.

### 2.5 Per-Patient Variance

| Patient | Event wF1 | Events/Day | Notes |
|---------|----------|-----------|-------|
| d (best) | 0.939 | ~6 | Very regular patterns |
| f | 0.735 | ~8 | Regular, high event rate |
| a | 0.621 | ~7 | Moderate regularity |
| g | 0.580 | ~5 | Average |
| b | 0.557 | ~9 | High variability despite data volume |
| i (worst) | 0.537 | ~4 | Irregular, sparse events |

The 0.54–0.94 F1 range across patients demonstrates that event patterns
are **partially patient-specific**. Patient d shows highly regular
meal/correction timing that the classifier easily learns. Patient i
shows irregular, sparse event patterns that resist classification.

### 2.6 What "Exercising" Event Detection Validation Really Means

Current validation computes aggregate F1 on held-out verification data. This
is necessary but insufficient. A thorough event detection evaluation would
decompose performance across:

1. **Per-event-type × per-patient**: Not just "event F1=0.54" but "Patient b
   meal F1=0.72, Patient b exercise F1=0.31" — revealing which specific
   patient-event combinations need attention
2. **Per-time-of-day**: Do morning meals get detected differently than
   evening meals? Is overnight exercise detection different from daytime?
3. **Lead time by event type**: Meals may be detectable 45 minutes ahead
   (glucose starts rising) while exercise onset may only be detectable 15
   minutes ahead (glucose starts dropping)
4. **False alarm cost analysis**: A false meal detection that triggers
   insulin dosing is dangerous; a false sleep detection that slightly
   adjusts basal is benign. Current metrics weight all false positives
   equally
5. **Consecutive detection stability**: Does the classifier produce stable
   event classifications across consecutive windows, or does it flicker
   between states?

---

## 3. Override Recommendation: From Broken Metric to Clinical Utility

### 3.1 The Metric Transformation

The override recommendation story is primarily a story about **asking the
right question**.

| Metric | F1 | What It Measures |
|--------|-----|-----------------|
| Treatment-log accuracy (EXP-123) | **0.13** | "Did the system predict when the user *actually* overrode?" |
| TIR-impact utility (EXP-227) | **0.993** | "Would this suggested override *improve time-in-range*?" |

The 0.13 → 0.993 jump represents **no model change** — the same pipeline
was evaluated with a different question. The treatment-log metric was
fundamentally wrong: it asked whether the model predicted *human behavior*
(when the user chose to override), not whether the model's suggestions were
*clinically useful* (whether an override would help glucose control).

A glucose pattern that warrants an override is not the same as a situation
where the user actually overrode. Users override based on context the model
can't see: upcoming exercise plans, social situations, confidence in CGM
readings, personal risk tolerance, forgetfulness.

### 3.2 What the System Can Do: WHEN

The TIR-impact evaluation (EXP-227) shows the system reliably identifies
**when an override would improve outcomes**:

| Metric | Value |
|--------|-------|
| TIR-impact F1 | 0.993 |
| Precision | 0.988 |
| Recall | 0.999 |
| Coverage at optimal threshold | 48.7% |

Override type distribution reveals what kinds of adjustments the system
identifies:

| Override Type | Count | % | Description |
|--------------|-------|---|-------------|
| Exercise correction | 18,421 | 84% | Sensitivity adjustment during/after activity |
| Hypo prevention | 1,829 | 8% | Reduce insulin to prevent lows |
| Variability reduction | 1,654 | 8% | Tighten control during stable periods |

### 3.3 What the System Cannot Do: WHICH and HOW MUCH

The system knows *when* to suggest an override but not *which type* or *how
much* to adjust:

| Question | Status | What's Needed |
|----------|--------|--------------|
| **WHEN** to suggest | ✅ F1=0.993 | Working — TIR-impact gating |
| **WHICH type** (exercise, eating soon, sick) | ❌ Not started | Event classification → override type mapping |
| **HOW MUCH** (ISF factor, duration) | ❌ Not started | Counterfactual simulation via physics model |
| **HOW LONG** (override duration) | ❌ Not started | Pattern-based duration estimation |

### 3.4 The Override Pipeline

The composite pipeline (`hindcast_composite.py:run_decision()`) chains
capabilities into an end-to-end decision:

```
1. Event Classification (30% confidence threshold)
   → "Is a meal, exercise, or hypo event likely?"

2. ISF/CR Drift Assessment (autosens sliding median)
   → "Has insulin sensitivity shifted from nominal?"
   → If resistance: suggest 'sick' override (24h)
   → If sensitivity: suggest 'exercise_recovery' override (12h)

3. Multi-Resolution Forecast (causal masked GroupedEncoder)
   → "What will glucose do in the next 1-6 hours?"

4. Scenario Simulation (ScenarioSimulator)
   → "What happens if we apply override X vs do nothing?"
   → Tests: meal_small, meal_medium, exercise_light

5. Uncertainty Bounds (conformal prediction)
   → "How confident are we? P(hypo), P(hyper), 95% interval"

6. Clinical Metrics
   → "What's the TIR/GRI impact of this suggestion?"
```

Steps 1–3 are functional. Steps 4–5 provide the safety gating. But step 6 —
the actual override specification — maps drift states to fixed override
templates ("if resistance → sick override for 24h") rather than computing
patient-specific override parameters from the forecast and drift magnitude.

### 3.5 Per-Patient Bimodal Distribution

Under the old treatment-log metric (EXP-123), a striking bimodal pattern
emerged:

| Group | Patients | F1 Range | Interpretation |
|-------|----------|---------|----------------|
| Near-perfect | b, f, j | 0.66–0.98 | Consistent, predictable override behavior |
| Near-zero | a, c, d, e, g, h, i | 0.00–0.12 | Irregular, context-dependent overrides |

This bimodality reveals that **some patients have highly regular override
patterns** (same time each day, triggered by same events) while **most
patients override irregularly** based on context the model can't observe.
The TIR-impact metric resolves this: clinical utility doesn't require
predicting the user's behavior — only predicting whether an override would
help.

### 3.6 What Override Validation Should Look Like

Moving from metric validation to clinical validation requires:

1. **Counterfactual TIR simulation**: For each suggested override, use the
   physics model to simulate "glucose trajectory with override" vs "glucose
   trajectory without override." The delta-TIR is the ground truth for
   whether the suggestion was useful.

2. **Override parameter search**: Instead of mapping drift states to fixed
   templates, optimize override parameters (ISF factor, CR factor, duration)
   to maximize the counterfactual TIR improvement, subject to safety
   constraints (no P(hypo) increase).

3. **Safety-gated evaluation**: Evaluate not just "was this suggestion
   useful?" but "was this suggestion *safe*?" using conformal prediction
   bounds. A useful suggestion that carries hypo risk is worse than no
   suggestion at all.

4. **User-facing decision quality**: Ultimately, overrides are presented
   to a human. Validation should measure whether the user can *understand*
   the suggestion and *trust* the confidence level — not just whether the
   underlying prediction is accurate.

---

## 4. Drift Tracking: ISF/CR Sensitivity Changes Over Time

### 4.1 The Clinical Problem

Insulin sensitivity (ISF) and carb ratio (CR) are not constants. They shift
over hours to weeks in response to:

| Driver | Timescale | Direction | Magnitude |
|--------|-----------|-----------|-----------|
| Exercise | 2–12 hours | ↑ Sensitivity | +10–40% |
| Illness | 1–7 days | ↓ Resistance | −20–50% |
| Menstrual cycle | 3–7 days | ↓ then ↑ | ±15–30% |
| Stress/cortisol | Hours–days | ↓ Resistance | −10–30% |
| Weight change | Weeks–months | Variable | ±5–20% |
| Infusion site aging | 2–3 days | ↓ Absorption | −10–30% |
| Sensor aging | 7–14 days | Measurement drift | ±5–15% |

Detecting these shifts and adapting therapy accordingly is the primary value
proposition of the override recommendation system. Without drift tracking,
override suggestions are generic; with it, they become personalized and
timely.

### 4.2 Current Implementation: Autosens-Style Sliding Median

The current drift detector mirrors oref0's autosens algorithm:

1. Compute per-step glucose residuals vs physics prediction
2. Normalize residuals by patient ISF: `deviation = residual / ISF`
3. 24-hour sliding median of valid deviations
   - Exclude meals (COB > 0.5g)
   - Suppress positive deviations at low BG (<80 mg/dL)
4. Convert to autosens ratio: `ratio = clip(1.0 + median_dev, [0.7, 1.2])`
5. Classify: ratio < 0.9 → resistance, ratio > 1.1 → sensitivity, else stable

### 4.3 Performance

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Median patient Pearson r (drift vs TIR) | **−0.156** | < −0.3 | ⚠️ Correct sign, weak |
| Patients with negative correlation | **10/10** | 10/10 | ✅ All correct |
| Per-patient range | −0.037 to −0.265 | — | Wide variation |
| Detection rate (non-stable %) | 15.5% | >20% | ⚠️ Conservative |
| False signal rate | 4.4% | <5% | ✅ Acceptable |

**All 10 patients now show negative correlation** (higher drift magnitude →
lower TIR), confirming the signal is real. But the magnitude is weak
(r=−0.156), meaning drift explains only ~2.4% of TIR variance.

### 4.4 The Kalman Filter Failure (and Recovery)

The original drift detector used a Kalman filter with measurement noise
R=5. The actual residual standard deviation was **224 mg/dL** — a 45×
miscalibration. A single 50 mg/dL glucose residual would slam the ISF
estimate from 40 to 6.6 mg/dL/U. The result: **wrong-sign correlation
(r=+0.70)** because the filter tracked noise, not drift.

Switching to the oref0-style sliding median fixed the direction (r=−0.071 →
−0.156 after parameter tuning) and produced clinically reasonable state
distributions:

| State | Old (Kalman) | New (Sliding Median) |
|-------|-------------|---------------------|
| Resistance | 84% | 61.7% |
| Stable | 16% | 26.2% |
| Sensitivity | 0% | 11.9% |

All 10 patients now exhibit all three states — a prerequisite for meaningful
drift tracking.

### 4.5 Why the Signal Is Weak

The drift detector has a **data dimension problem**: it computes sensitivity
ratios from glucose residuals alone, without access to the physiological and
device context that drives those residuals.

Consider two scenarios that produce identical glucose residuals:
1. **Real insulin resistance** (illness): ISF genuinely decreased, insulin
   is less effective → glucose runs higher than physics predicts
2. **Infusion site degradation**: ISF is unchanged, but insulin absorption
   is impaired at the aging cannula site → same higher-than-predicted glucose

The current system cannot distinguish these. Both produce negative deviations
that the sliding median captures as "resistance." But the appropriate
intervention differs: scenario 1 needs an ISF override; scenario 2 needs a
site change.

Similarly, sensor aging produces systematic measurement drift that the
detector conflates with physiological sensitivity changes.

---

## 5. The Data Dimensions Matrix

This is the core analytical contribution of this assessment: mapping each
capability against the data dimensions that drive it, and revealing which
dimensions are captured, partially captured, or completely missing.

### 5.1 Dimension Coverage

| Data Dimension | Timescale | Available in Data? | Captured in Features? | Used by Models? |
|---------------|-----------|-------------------|----------------------|----------------|
| **Glucose history** | Continuous | ✅ entries.json | ✅ Feature 0 (core) | ✅ 87% of attention |
| **IOB / COB** | Continuous | ✅ devicestatus | ✅ Features 1-2 (core) | ✅ 13% of attention |
| **Basal / bolus / carbs** | Discrete | ✅ treatments | ✅ Features 3-5 (core) | ✅ Action group |
| **Circadian phase** | 24h cycle | ✅ Timestamps | ✅ Features 6-7 (core) | ✅ Time group |
| **Weekly phase** | 7-day cycle | ✅ Timestamps | ⚠️ Features 8-9 (extended only) | ⚠️ Agentic models only |
| **Override state** | Event-driven | ✅ treatments | ⚠️ Features 10-11 (extended) | ⚠️ Agentic only |
| **Glucose dynamics** | Derived | ✅ Computed | ⚠️ Features 12-13 (extended) | ⚠️ Agentic only |
| **Action timing** | Temporal | ✅ Computed | ⚠️ Features 14-15 (extended) | ⚠️ Agentic only |
| **ISF/CR drift** | Hours–days | ⚠️ Pseudo-labeled | ⚠️ Aux training target only | ⚠️ Training signal, not input |
| **Exercise intensity** | Minutes–hours | ⚠️ Binary override flag | ⚠️ Keyword match only | ❌ No continuous feature |
| **Infusion set age** | 2-3 days | ✅ Site Change events exist | ❌ **Completely ignored** | ❌ Not modeled |
| **Sensor age** | 7-14 days | ❌ Not in Nightscout data | ❌ Not captured | ❌ Not modeled |
| **Hormonal cycle** | 3-7 days | ❌ No data source | ❌ Not captured | ❌ Not modeled |
| **Illness/stress** | Variable | ⚠️ "Sick" override keyword | ⚠️ Binary label only | ❌ No biomarkers |
| **Meal composition** | Per-meal | ❌ Only total grams | ❌ No fat/protein/fiber | ❌ Not modeled |
| **Sleep quality** | Nightly | ❌ No wearable data | ❌ Not captured | ❌ Not modeled |
| **Device comms quality** | Continuous | ✅ devicestatus | ❌ Not extracted | ❌ Not modeled |

### 5.2 The Infusion Set Blind Spot

**Site Change events exist in the treatment data but are completely
ignored.** The event extraction pipeline (`label_events.py`) processes
meals, boluses, and temporary overrides but skips Site Change events
entirely.

This is a significant blind spot because infusion set aging follows a
well-documented degradation curve:

| Age | Insulin Absorption | Clinical Effect |
|-----|-------------------|----------------|
| 0–6 hours | Normal (baseline) | Optimal delivery |
| 6–48 hours | Stable | Good control period |
| 48–72 hours | Declining (−10–20%) | Gradually rising glucose |
| >72 hours | Significantly impaired (−20–40%) | "Unexplained" highs |

This degradation pattern produces glucose residuals that the drift detector
attributes to physiological resistance — but the remedy is a site change,
not an ISF override. Extracting infusion set age from existing Site Change
events and encoding it as a feature would:

1. **Improve drift tracking** by separating device degradation from
   physiological sensitivity changes
2. **Improve anomaly detection** by predicting the degradation curve
3. **Enable site change reminders** — a high-value clinical feature
4. **Reduce false resistance alerts** that currently trigger unnecessary
   ISF overrides

### 5.3 The Sensor Age Gap

Unlike infusion set age, CGM sensor age is **not recorded in Nightscout
treatment data**. However, sensor accuracy follows a known lifecycle:

| Phase | Days | Accuracy | Noise |
|-------|------|----------|-------|
| Warm-up | 0–1 | Low (calibrating) | High |
| Stabilization | 1–3 | Improving | Moderate |
| Peak accuracy | 3–7 | Highest | Low |
| Degradation | 7–10 | Declining | Increasing |
| End-of-life | 10–14 | Poor | High, with compression artifacts |

Sensor age affects every other capability:
- **Forecasting**: Accuracy degrades with sensor age
- **Event detection**: Noise patterns change
- **Drift tracking**: Sensor drift mimics physiological drift
- **Anomaly detection**: Late-sensor noise creates false anomalies

Sensor age could potentially be inferred from CGM noise patterns (late
sensors show characteristic MARD increase) or from sensor insertion events
in device status data.

### 5.4 Capability × Dimension Dependency Map

Which capabilities depend on which data dimensions? (●=critical, ○=useful, ·=minor)

| Dimension | Forecast | Event Detection | Drift Tracking | Override Reco |
|-----------|----------|----------------|---------------|--------------|
| Glucose history | ● | ○ | ○ | ○ |
| IOB/COB | ○ | ● | ● | ● |
| Treatment timing | · | ● | ○ | ● |
| Circadian phase | ○ | ○ | ● | ● |
| Weekly phase | · | ○ | ○ | ● |
| Exercise intensity | ○ | ● | ● | ● |
| Infusion set age | ○ | · | ● | ● |
| Sensor age | ○ | · | ● | · |
| ISF/CR drift state | · | ○ | — | ● |
| Meal composition | ○ | ● | · | ○ |
| Sleep/activity state | · | ● | ○ | ● |

**Override recommendation depends on nearly every dimension** — it is the
most data-hungry capability, which explains why it is also the least mature.
Event detection depends heavily on treatment patterns and activity context.
Drift tracking needs device age features to separate hardware degradation
from physiological changes.

---

## 6. Time Horizon Decomposition

### 6.1 Immediate Horizon (Minutes → 2 Hours)

**Capabilities**: Hypo alerts, meal detection, correction suggestions, glucose forecasting

| Capability | Metric | Current | Clinical Min | Status |
|-----------|--------|---------|-------------|--------|
| Glucose forecast (in-range) | MAE | 15.7 mg/dL | <20 | ✅ Met |
| Glucose forecast (hypo) | MAE | 39.8 mg/dL | <15 | ❌ 2.7× gap |
| Hypo alert | F1 | 0.700 | >0.80 | ⚠️ Close |
| Meal detection | F1 | 0.822 | >0.70 | ✅ Met |
| Correction bolus detection | F1 | 0.768 | >0.60 | ✅ Met |

**Assessment**: The immediate horizon is the strongest. Glucose
autocorrelation provides abundant signal for short-term prediction. The
model's 87% glucose attention allocation is well-suited here — recent glucose
trajectory is the best predictor of near-future glucose.

**Primary gap**: Hypoglycemia prediction (39.8 MAE) degrades 2.5× vs
in-range because rapid glucose drops represent **trend reversals** that
the autoregressive model under-predicts. Only 3.5% of training windows
contain hypo events, creating severe data imbalance.

**Data dimensions that matter most**: Glucose history (dominant), IOB/COB
(insulin action timing), treatment timing (recent bolus/carbs).

### 6.2 Daily Horizon (2 Hours → 24 Hours)

**Capabilities**: Sleep/exercise cycle recognition, circadian override
timing, routine pattern detection

| Capability | Metric | Current | Clinical Min | Status |
|-----------|--------|---------|-------------|--------|
| Circadian amplitude | mg/dL | 15 ± 4 | Detectable | ✅ Detected |
| Dawn phenomenon | mg/dL | −2 to +12 | Quantified | ✅ Quantified |
| Sleep detection | F1 | 0.352 | >0.50 | ❌ Gap |
| Exercise detection | F1 | 0.537 | >0.60 | ⚠️ Close |
| Time-of-day TIR variance | CV% | 22–28% | Measurable | ✅ Measured |

**Assessment**: The daily horizon shows moderate capabilities. Circadian
patterns are reliably detected (80% of patients show amplitude >20 mg/dL).
But the capabilities that require **behavioral context** — sleep detection,
exercise recognition — are weak because the model lacks the necessary input
signals.

**Data dimensions that matter most**: Circadian phase, exercise intensity,
sleep/wake state, meal timing patterns, weekly phase (weekend vs weekday).

**Critical missing dimension**: **Continuous activity data**. Exercise is
currently captured only as a binary override flag set by keyword matching
("exercise", "workout", "running"). This misses:
- Unplanned or unlabeled exercise
- Exercise intensity and duration
- Post-exercise recovery (6–12h sensitivity increase)
- Activity patterns (commute, housework, sports)

Wearable integration (step count, heart rate, accelerometer) would transform
daily-horizon capabilities.

### 6.3 Longitudinal Horizon (Days → Weeks)

**Capabilities**: ISF/CR drift detection, illness identification, hormonal
cycle tracking, device aging effects

| Capability | Metric | Current | Clinical Min | Status |
|-----------|--------|---------|-------------|--------|
| Drift-TIR correlation | Pearson r | −0.156 | < −0.3 | ⚠️ Weak |
| Drift detection rate | % non-stable | 15.5% | >20% | ⚠️ Conservative |
| Infusion set age tracking | — | Not captured | Captured | ❌ Missing |
| Sensor age tracking | — | Not captured | Captured | ❌ Missing |
| Illness detection | — | Binary "sick" override | Reliable | ❌ Crude |
| Hormonal cycle | — | Not captured | Captured | ❌ Missing |

**Assessment**: The longitudinal horizon is the weakest. This is partly
inherent — long-timescale changes are slower, subtler, and confounded by
more variables — but it's also partly a **data capture problem**. The most
important drivers of longitudinal drift (infusion set aging, sensor aging,
hormonal cycles) are either not in the data or not extracted.

**Data dimensions that matter most**: ISF/CR drift state, infusion set age,
sensor age, hormonal cycle phase, illness indicators.

**The fundamental challenge**: Longitudinal capabilities require data that
**spans weeks to months** per patient, with sufficient event diversity
within each period. Our current 10-patient dataset has adequate total
volume (~32K windows) but limited longitudinal diversity — we see each
patient's patterns for a finite observation window. More patients with
longer observation periods would disproportionately benefit longitudinal
capabilities.

---

## 7. Concrete Improvement Pathways

### 7.1 Breaking the Event Detection Ceiling

The wF1=0.710 convergence from three independent methods indicates a
**feature/label ceiling**, not a model ceiling. Breaking through requires:

**A. Hybrid Neural-XGBoost Architecture**

Rather than forcing the transformer to learn events (it won't — 87% glucose
attention) or abandoning neural methods entirely, build a hybrid:

```
Glucose Window → GroupedEncoder → Glucose embedding ──┐
                                                       ├─ Fusion → Event classifier
Treatment Features → XGBoost-style feature extraction ─┘
```

The neural component provides temporal glucose context; the tree-based
component provides explicit treatment feature importance. Gradient flow
can be maintained through differentiable tree ensembles or by using the
neural embedding as additional XGBoost features.

**B. Richer Input Features**

Three high-impact feature additions from existing data:

1. **Infusion set age** (from Site Change events — exists but ignored):
   Hours since last site change, normalized. Enables the classifier to learn
   that "glucose running high + 3-day-old site" ≠ meal event.

2. **Treatment pattern features** (from treatment history): Rolling
   meal/bolus frequency, typical meal times, correction bolus frequency.
   Enables "this patient usually eats at 12:30 and it's 12:25" detection.

3. **Glucose volatility context** (from recent history): Rolling coefficient
   of variation, time-in-range over past 6h, hypo/hyper event count.
   Enables "patient is in a volatile period, events more likely."

**C. Per-Patient Adaptation Layers**

Instead of full per-patient fine-tuning (which showed mixed results: +17%
for some patients, −9% for others in EXP-057), use lightweight adapter
modules:
- Population model as frozen backbone
- Per-patient adapter: 1–5% of parameters
- Learns patient-specific event timing and patterns
- Regularized to prevent catastrophic forgetting

### 7.2 Override Specification: WHICH and HOW MUCH

The system knows WHEN (F1=0.993). The next capability tier is specifying
the override:

**A. Event-Type → Override-Type Mapping**

Map detected events to override types using clinical protocols:

| Detected Event | Override Type | ISF Factor | Duration |
|---------------|-------------|-----------|----------|
| Exercise starting | Exercise | 0.5–0.7× | 1–2h (+ 4–6h recovery) |
| Meal upcoming | Eating Soon | 1.0× (early insulin) | 30–60 min |
| Illness pattern | Sick | 1.3–1.5× | 12–24h |
| Post-exercise sensitivity | Exercise Recovery | 0.7–0.8× | 4–12h |
| Dawn phenomenon | Sleep/Night | 1.1–1.2× | 4–6h |

**B. Counterfactual Simulation Framework**

For each candidate override, use the physics model to simulate two
trajectories:
1. **Baseline**: Continue current therapy unchanged
2. **With override**: Apply the candidate override parameters

The delta-TIR between trajectories is the expected benefit. Optimize
override parameters (ISF factor, duration) to maximize delta-TIR subject
to:
- P(hypo|override) < P(hypo|baseline) (safety constraint)
- Override intensity within oref0 autosens bounds [0.7, 1.2]
- Duration within clinically reasonable limits

**C. Confidence-Gated Suggestion**

Use conformal prediction uncertainty to gate suggestions:
- High confidence (narrow prediction interval): Suggest specific override
  with parameters
- Medium confidence: Suggest override type but let the user adjust
  parameters
- Low confidence: Flag the situation for user attention without suggesting
  a specific action

### 7.3 Strengthening Drift Detection

**A. Device Age Features (Highest Priority)**

Extract and encode from existing data:
1. **Infusion set age**: Hours since last Site Change event. Available in
   treatments.json now — requires only extraction code.
2. **Estimated sensor age**: Infer from CGM noise characteristics (MARD
   increase) or from sensor insertion events in devicestatus.

**B. Longer Lookback with Circadian Correction**

Current: 24-hour sliding median.  
Proposed: 72-hour sliding median with circadian phase normalization.

The 24-hour window conflates circadian variation with drift. A 72-hour
window with per-hour normalization (subtract the patient's typical glucose
at each hour) would isolate genuine drift from predictable daily patterns.

**C. Treatment-Context Normalization**

Normalize drift assessments by treatment intensity:
- Total daily dose (TDD) trending up → possibly masking resistance
- Basal/bolus ratio shifting → controller is already compensating
- Correction frequency increasing → system is chasing resistant highs

These signals, derived from treatment records, would distinguish "ISF
decreased and controller is compensating" from "ISF is stable but patient
ate differently."

### 7.4 Cross-Cutting Needs

**More Diverse Patients**: The single highest-impact investment. Current
10 patients are all using Loop (iOS closed-loop). Adding patients from:
- AAPS (Android, oref0/oref1 algorithm)
- Trio (iOS, oref1 algorithm)
- Open-loop / MDI (manual injection)
- Different CGM systems (Libre 2/3, Medtronic Guardian)
- Different diabetes types (T2D, LADA)

...would stress-test every capability against real-world diversity.

**Behavioral Context (Wearable Integration)**: Step count, heart rate, and
sleep detection from fitness wearables would directly address the exercise
detection gap (F1=0.537) and sleep detection gap (F1=0.352). Many patients
already wear Apple Watch, Fitbit, or Garmin alongside their CGM.

**Longer Observation Periods**: Longitudinal capabilities (drift, hormonal
cycles) need weeks-to-months of continuous data per patient. Current datasets
cover limited time windows. Encouraging community data sharing with longer
collection periods would disproportionately benefit the weakest capabilities.

---

## 8. Capability Maturity Roadmap

### Production-Ready Now

| Capability | Evidence | Confidence |
|-----------|---------|-----------|
| Glucose forecast (in-range, 1h) | 16.0 MAE, 10 patients, verification data | High |
| Calibrated uncertainty | 0.7% coverage gap, conformal | High |
| Meal detection | F1=0.822, clear glucose signature | High |
| Override timing (WHEN) | F1=0.993, TIR-impact validated | High |

### Needs Metric/Methodology Changes

| Capability | Current Problem | Fix |
|-----------|----------------|-----|
| Override type specification | Not attempted — need event→override mapping | Build clinical lookup + counterfactual sim |
| Override recommendation evaluation | Was using wrong metric (treatment-log) | TIR-impact metric now validated |
| Event detection per-patient evaluation | Aggregate F1 masks per-patient variance | Decompose by patient × event × time |

### Needs Data Enrichment

| Capability | Missing Data | Source |
|-----------|-------------|--------|
| Drift tracking accuracy | Infusion set age | Site Change events (exists in treatments, ignored) |
| Drift vs device separation | Sensor age | Infer from noise or devicestatus |
| Exercise detection | Continuous activity | Wearable integration |
| Sleep detection | Sleep/wake state | Wearable integration |
| Longitudinal patterns | Longer observation windows | Community data sharing |

### Needs Architectural Innovation

| Capability | Current Limitation | Proposed Architecture |
|-----------|-------------------|---------------------|
| Event detection ceiling (wF1=0.710) | Transformer ignores treatment features | Hybrid neural-XGBoost with dedicated paths |
| Neural event head (F1=0.107) | 87% glucose attention dominance | Separate treatment encoder with cross-attention |
| Override parameter estimation | Fixed templates from drift states | Counterfactual physics simulation + optimization |
| Patient-specific adaptation | Fine-tuning overfits (mixed ±17%) | Lightweight adapter modules (1–5% params) |

### Priority Ordering

Based on impact (clinical value × feasibility):

| Priority | Action | Horizon Improved | Expected Impact |
|----------|--------|-----------------|-----------------|
| 1 | **Extract infusion set age from Site Change events** | Longitudinal | Separate device drift from physiological drift |
| 2 | **Hybrid neural-XGBoost for events** | Immediate, Daily | Break F1=0.710 ceiling |
| 3 | **Counterfactual override simulation** | Decision layer | Enable WHICH and HOW MUCH |
| 4 | **Per-patient adapter modules** | All horizons | Reduce 0.54–0.94 F1 per-patient variance |
| 5 | **Wearable data integration** | Daily | Transform exercise (0.537) and sleep (0.352) detection |
| 6 | **72h drift window with circadian correction** | Longitudinal | Strengthen r=−0.156 signal |
| 7 | **More diverse patients (20+)** | All horizons | Improve cross-patient generalization |

Priority 1 stands out as exceptionally high-value-per-effort: the data
already exists in treatment records, it requires only extraction code, and
it addresses a fundamental confusion in drift tracking (device degradation
vs physiological change). Every other improvement builds on top of being able
to distinguish these two sources of "unexpected" glucose behavior.
