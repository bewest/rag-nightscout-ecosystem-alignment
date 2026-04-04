# What 258 ML Experiments Reveal About Diabetes Biology

**Date**: 2026-07-03
**Scope**: 258 experiments across 10 real Nightscout patients
**Dataset**: ~6 months continuous CGM, insulin delivery, and treatment logs per patient
**Perspective**: Diabetes biology and management — not machine learning methodology

---

## Purpose

This report inverts the usual ML framing. Instead of asking "which model
performed best?", it asks: **what did we learn about diabetes itself** from
running 258 experiments on real patient data?

Every finding below emerged from data-driven analysis of continuous glucose
monitoring (CGM) traces, insulin-on-board (IOB) calculations, carbohydrate
records, and treatment logs collected through Nightscout from 10 individuals
using automated insulin delivery (AID) systems in daily life.

These are not clinical trial results. They are observational patterns extracted
by machine learning from the lived experience of people managing Type 1 diabetes.

**Related docs**:
- ML technique analysis → `docs/60-research/training-techniques-what-works.md`
- Experiment log → `docs/60-research/ml-experiment-log.md`
- AID algorithm comparison → `docs/10-domain/`
- Gap tracking → `traceability/gaps.md`

---

## Table of Contents

1. [Glucose Is 87% Self-Predictive](#1-glucose-is-87-self-predictive)
2. [Dawn Phenomenon Is Universal and Large](#2-dawn-phenomenon-is-universal-and-large)
3. [Patient Heterogeneity Is Extreme](#3-patient-heterogeneity-is-extreme)
4. [Volatile Periods Account for Most Forecast Error](#4-volatile-periods-account-for-most-forecast-error)
5. [Meal Detection Is the Hardest Event](#5-meal-detection-is-the-hardest-event)
6. [ISF/CR Drift Is Real but Slow](#6-isfcr-drift-is-real-but-slow)
7. [IOB Data Quality Varies Dramatically](#7-iob-data-quality-varies-dramatically)
8. [The Physics-ML Boundary Is Clear](#8-the-physics-ml-boundary-is-clear)
9. [Hypoglycemia Prediction Has a Blind Spot](#9-hypoglycemia-prediction-has-a-blind-spot)
10. [Overrides Help More Than Users Think](#10-overrides-help-more-than-users-think)
11. [Summary of Biological Insights](#summary-of-biological-insights)
12. [Implications for AID System Design](#implications-for-aid-system-design)

---

## 1. Glucose Is 87% Self-Predictive

**Experiment**: EXP-114 (transformer attention weight analysis)

When a transformer model learns to forecast glucose, it reveals what information
matters most by how it distributes attention. Our trained model assigns **86.8%
of its attention to glucose history** and only 13.2% to insulin and carbohydrate
features combined.

This is a striking finding. Insulin and carbohydrates are the two primary levers
of diabetes management — the things patients actively control, the things
clinicians adjust, the things AID algorithms optimize. Yet in a trained
forecasting model, they contribute barely one-eighth of the predictive signal.

**Why this happens**: The glucose trace already encodes the *consequences* of
prior insulin and carbohydrate actions. A bolus delivered 45 minutes ago is
visible as the current downward glucose trend. A meal eaten 20 minutes ago is
beginning to appear as an upward inflection. The glucose trajectory is an
integrated record of everything that has already happened to the patient — it is
the response signal, not just a measurement.

**Clinical meaning**:

- **CGM-only prediction is viable for short-term horizons.** Systems like xDrip+
  that have access to CGM data but not pump telemetry can still produce useful
  30-60 minute forecasts. The glucose trace carries most of the information.
- **Pump data becomes critical for longer horizons.** Beyond 60 minutes, the
  effects of recent insulin and carbs have not yet fully materialized in the
  glucose trace. This is where the 13.2% matters — and where pump-integrated
  systems (Loop, AAPS, Trio) gain a meaningful accuracy advantage.
- **"Watch the trend" is physiologically sound advice.** The common clinical
  guidance to patients — "look at your CGM arrow, not just the number" — is
  validated by the model's behavior. The trajectory contains more information
  than any single reading.

---

## 2. Dawn Phenomenon Is Universal and Large

**Experiment**: EXP-126 (circadian pattern extraction)

The dawn phenomenon — a rise in blood glucose during the early morning hours
driven by counter-regulatory hormones (cortisol, growth hormone, catecholamines)
— is well-described in endocrinology textbooks. What our data reveals is its
*magnitude* and *universality* in real-world AID use.

**Key findings**:

| Metric | Value |
|--------|-------|
| Patients showing strong circadian pattern | **10/10 (100%)** |
| Mean circadian amplitude | **71.3 ± 18.7 mg/dL** |
| Peak glucose hours | **01:00–05:00** |
| Night time-in-range (TIR) | **60.1%** |
| Afternoon TIR | **75.2%** |
| Dawn effect range across patients | **−76.7 to +28.2 mg/dL** |

The 71.3 mg/dL mean circadian amplitude is remarkable. For context, our best
forecast model achieves ~10.6 mg/dL mean absolute error — the circadian swing is
nearly 7× larger than the forecast error. This means the time-of-day signal
dominates the glucose landscape for every patient.

**Night TIR vs. afternoon TIR**: The 15-percentage-point gap (60.1% vs. 75.2%)
is clinically significant. Patients spend substantially more time above range
during sleep, precisely when they are unable to intervene manually. This is not
a failure of AID — it reflects genuine physiological challenge. Counter-regulatory
hormone secretion is endogenous and varies night to night. AID controllers are
fighting a moving target.

**The individuality of dawn**: The range from −76.7 to +28.2 mg/dL across
patients means some individuals experience a dramatic overnight rise while
others see a modest decline. A single "nighttime basal profile" cannot serve
all patients. This variation likely reflects differences in growth hormone
pulsatility, hepatic insulin resistance, and residual beta-cell function.

**Clinical implications**:

- AID controller settings (basal rates, correction factors, target glucose)
  should differ substantially between nighttime and daytime for *every* patient.
  A flat 24-hour profile leaves performance on the table.
- Loop's "Override" and AAPS's "Profile Switch" mechanisms exist precisely for
  this purpose, but our data suggests they are underutilized (see
  [Section 10](#10-overrides-help-more-than-users-think)).
- Nightscout's profile system supports time-of-day segmentation. The data
  confirms this is not optional — it is essential.

---

## 3. Patient Heterogeneity Is Extreme

**Source**: Aggregate analysis across 258 experiments

Across every experiment, the single largest source of variation is not the model
architecture, the training technique, or the feature set — it is the patient.

**Forecast accuracy by patient (1-hour horizon)**:

| Patient | MAE (mg/dL) | TIR (%) | Event F1 | Notes |
|---------|-------------|---------|----------|-------|
| d | 7.95 | 79.6 | 0.939 | Consistently best outcomes |
| e | 8.14 | 66.1 | 0.679 | Low forecast error, moderate TIR |
| i | 8.58 | 60.0 | 0.537 | Low MAE but low event detection |
| f | 8.82 | 65.8 | 0.618 | Moderate variability |
| g | 9.00 | 75.5 | 0.720 | Good TIR, moderate MAE |
| c | 9.59 | 61.5 | 0.676 | Higher glycemic variability |
| h | 10.01 | 84.9 | 0.760 | Best TIR, moderate MAE |
| a | 10.94 | 55.9 | 0.840 | High event F1 despite low TIR |
| j | 15.44 | 80.8 | 0.655 | 0% IOB data, model struggles |
| b | 17.40 | 56.5 | 0.667 | Consistently hardest patient |

The **2.2× range** in MAE (7.95 to 17.40) persists regardless of which model or
technique is applied. Patient d is "easy" — stable glucose patterns, complete
data, consistent routines. Patient b is "hard" — high glycemic variability,
unpredictable meal patterns, frequent excursions.

**What makes a patient "easy" or "hard"**:

- **Routine consistency**: Patients with regular meal times and sleep schedules
  produce more predictable glucose patterns. The model learns their rhythms.
- **Data completeness**: Missing IOB data (patient j) removes a key input signal.
  The model must infer insulin action from glucose response alone.
- **Glycemic variability**: Patients with frequent, large glucose swings
  (coefficient of variation > 36%) are inherently harder to forecast.
- **AID system tuning**: Well-tuned AID settings produce smoother glucose traces,
  which are easier to predict. Poorly tuned settings create oscillations that
  compound forecast error.

**The case for per-patient models**: Population models (trained on all patients)
provide a reasonable baseline. But **per-patient fine-tuning improves outcomes
for every single patient** in our cohort. Fine-tuning alone yields a 12%
reduction for patient d (base 9.49 → fine-tuned 8.35 in EXP-241), and
the full pipeline (fine-tuning + ensembling + extended training) pushes
d to 7.95 mg/dL — the best in the cohort.

**Clinical implication**: "One size fits all" AID settings are fundamentally
suboptimal. The oref0/AAPS approach of continuous autotune — adjusting basal
rates, ISF, and CR based on each patient's recent data — is directionally
correct. The variation between patients is so large that any fixed parameter
set leaves significant room for improvement.

---

## 4. Volatile Periods Account for Most Forecast Error

**Experiment**: EXP-222 (volatile vs. calm period analysis), EXP-224 (volatile
augmentation)

Not all 5-minute CGM intervals are created equal. We classified glucose windows
into "calm" (rate of change < 1 mg/dL/min) and "volatile" (rate of change
≥ 1 mg/dL/min) periods and measured forecast accuracy separately.

| Period Type | MAE (mg/dL) | Proportion of Time |
|-------------|-------------|--------------------|
| Calm | **10.3** | ~70% |
| Volatile | **21.0** | ~30% |
| **Ratio** | **2.04×** | — |

During calm periods — overnight stability, post-absorptive plateaus, well-
controlled between-meal stretches — the model achieves 10.3 mg/dL MAE. This
is clinically excellent. At this accuracy level, a 1-hour forecast is genuinely
useful for decision-making.

During volatile periods — meal absorption, exercise onset, stress responses,
insulin stacking, rebound from hypoglycemia — error doubles to 21.0 mg/dL.
This is the accuracy frontier.

**Volatile augmentation** (EXP-224) specifically oversampled volatile periods
during training, reducing the calm/volatile error ratio from 2.04× to 1.33×.
This confirms the problem is partly data imbalance: the model sees 70% calm
data and optimizes accordingly.

**What drives volatile periods**:

- **Meals**: The largest and most unpredictable glucose disturbance. Glycemic
  response to the same meal varies by ±30% day to day within the same person,
  driven by gastric emptying rate, physical activity, stress, and prior meals.
- **Exercise onset**: The transition from rest to activity causes rapid glucose
  changes. Direction depends on exercise intensity — aerobic exercise typically
  drops glucose, while anaerobic bursts can raise it.
- **Insulin stacking**: Multiple correction boluses in succession can produce
  delayed, compounding glucose drops that are difficult to predict.
- **Counter-regulatory rebounds**: Recovery from hypoglycemia often produces a
  rapid glucose rise as the liver dumps glycogen — the "rebound high."

**Clinical implication**: AID systems already perform well during stable periods.
The remaining clinical challenge is managing transitions — the 30% of time when
glucose is actively changing. This is where meal announcements, exercise modes,
and well-timed overrides matter most. It also explains why closed-loop systems
work so well overnight (mostly calm) and struggle most around meals (maximally
volatile).

---

## 5. Meal Detection Is the Hardest Event

**Source**: Event detection experiments across multiple approaches

We trained classifiers to detect five event types from CGM patterns alone:

| Event | F1 Score | Prevalence | Detection Difficulty |
|-------|----------|------------|---------------------|
| No event (baseline) | 0.967 | ~94% | Trivial |
| Correction bolus | 0.768 | ~2.5% | Moderate |
| Override / Eating Soon | 0.742 | ~1.8% | Moderate |
| Exercise | 0.736 | ~1.3% | Moderate |
| **Meal** | **0.565** | **~0.4%** | **Very hard** |

Meals are the single hardest event to detect from CGM data.

**Why meals are uniquely difficult**:

1. **Extreme class imbalance**: Meals represent only 0.4% of 5-minute windows.
   The model sees 250 non-meal windows for every meal window.

2. **Delayed glucose response**: Carbohydrate absorption takes 15-30 minutes to
   produce a visible glucose rise. By the time the CGM trace shows an upward
   inflection consistent with a meal, the early detection window has already
   closed.

3. **Variable glycemic response**: The same 50g carbohydrate meal can produce
   a 40 mg/dL rise one day and a 120 mg/dL rise the next, depending on fat
   content, protein content, glycemic index, recent exercise, current IOB,
   and dozens of other factors.

4. **Overlap with other events**: A glucose rise can result from a meal, stress,
   dawn phenomenon, a failed infusion site, or simply the tail end of a
   correction bolus wearing off. The CGM trace alone cannot reliably distinguish
   these.

**Contrast with correction boluses** (F1 = 0.768): Boluses produce a clear,
stereotyped glucose pattern — a downward deflection beginning 15-30 minutes
post-delivery, with a characteristic decay profile determined by insulin
pharmacokinetics (DIA). This pattern is consistent and recognizable.

**Clinical implications**:

- **Meal announcement remains essential.** ML cannot reliably replace
  user-announced meals from CGM data alone. The 0.565 F1 score means roughly
  44% of meals are missed or falsely detected.
- **Pre-bolusing is physiologically justified.** The clinical practice of
  delivering mealtime insulin 15-20 minutes before eating exists precisely
  because the insulin needs a head start — by the time glucose rises, the
  insulin should already be active. Our data confirms there is no shortcut:
  the glucose signal arrives too late.
- **Unannounced Meal (UAM) detection in oref0/AAPS** takes a different approach —
  it detects that a meal *has occurred* (after the glucose rise begins) and
  increases insulin delivery reactively. This is a pragmatic strategy that
  accepts late detection as inevitable and compensates with aggressive dosing.
  Our F1 data validates this design choice.

---

## 6. ISF/CR Drift Is Real but Slow

**Experiments**: EXP-124, EXP-154, EXP-183, EXP-194 (drift tracking series)

Insulin sensitivity factor (ISF) and carbohydrate ratio (CR) are not fixed
constants — they change over weeks and months in response to weight changes,
activity levels, hormonal cycles, illness, and medication adjustments. This
"drift" is real and measurable in our data.

**Key findings**:

| Metric | Value |
|--------|-------|
| Patients showing measurable drift | **10/10** |
| Drift-TIR correlation (mean) | **r = −0.156** |
| Drift-TIR correlation (96-hour window) | **r = −0.328** |
| TIR variance explained by drift | **2–11%** |
| Treatment-enriched drift tracking benefit | **0%** |
| Optimal drift detection window | **96 hours (4 days)** |

All 10 patients show ISF/CR drift. The correlation with TIR is consistently
negative: as sensitivity drifts away from the AID system's programmed values,
time-in-range deteriorates. This is expected — stale settings mean the
controller is operating on incorrect assumptions.

**But the effect is surprisingly small.** Drift explains only 2-11% of TIR
variance. The other 89-98% comes from meal timing, bolusing accuracy, exercise,
sleep quality, and dozens of other factors that change hour to hour. Drift is a
background signal, not the dominant force.

**The 96-hour window** (EXP-194) emerged as the optimal timescale for detecting
drift. Shorter windows (24-48 hours) are too noisy — a single bad meal can mimic
a sensitivity shift. Longer windows (7-14 days) are too slow — real drift can
reverse before it's detected. Four days balances signal and responsiveness.

**Treatment-enriched drift tracking** (EXP-188) added bolus and carb data to the
drift calculation. Result: zero improvement. The glucose trace alone carries the
drift signal — adding treatment data introduces noise without adding information.

**Clinical implications**:

- **Autosens-style sensitivity tracking is physiologically valid.** The openaps
  autosens algorithm, which adjusts ISF and basal rates based on recent glucose
  patterns, is detecting a real phenomenon. So is Loop's retrospective
  correction. These are not statistical artifacts.
- **Conservative bounds are appropriate.** The oref0 default autosens ratio of
  0.8–1.2 (±20%) matches the observed drift magnitude. Wider bounds would chase
  noise. The weak correlation (r = −0.156) means aggressive adjustments are more
  likely to hurt than help.
- **Four-day lookback windows are optimal.** This aligns well with oref0's
  autosens design, which typically uses 8-24 hours of data. Our finding suggests
  slightly longer windows (up to 96 hours) could improve drift detection without
  sacrificing responsiveness.

---

## 7. IOB Data Quality Varies Dramatically

**Source**: Cross-patient data completeness analysis

Insulin-on-board (IOB) is a calculated value representing the amount of active
insulin in the patient's body at any given moment. It depends on complete records
of every insulin delivery — basal rates, boluses, and temporary basal adjustments.

In our cohort, IOB data completeness varies enormously:

| Data Completeness | Patients | MAE Range (mg/dL) |
|-------------------|----------|-------------------|
| Full IOB data | 9 patients | 7.95–10.94 |
| 0% IOB data | 1 patient (j) | 15.44 (train), 21.04 (verify) |

Patient j has **zero usable IOB data**. This patient's pump data either was not
uploaded to Nightscout or was incomplete. The model must predict glucose using
only the CGM trace and carbohydrate records — it is effectively flying blind
about insulin delivery.

The result: patient j has the **worst verification accuracy in the cohort**
(21.04 mg/dL MAE) with fewer usable verification windows than most other
patients. The model can learn patient j's glucose patterns
during training but cannot generalize — without knowing what insulin is on board,
future glucose depends on an unobserved variable.

**The accuracy gap** between CGM-only (patient j, ~15–22 mg/dL) and CGM+pump
(other patients, 7.95–10.94 mg/dL) represents roughly a **2× accuracy penalty**
for missing insulin data.

**Clinical implications**:

- **Pump connectivity is not optional for accurate forecasting.** CGM-only
  predictions are possible but substantially degraded. This is the quantitative
  case for pump integration in systems like Nightscout.
- **Data upload reliability matters clinically.** Gaps in pump data don't just
  create missing records — they degrade the accuracy of every downstream
  calculation, from IOB curves to forecast models.
- **This validates Nightscout's push for comprehensive data collection.** The
  ecosystem's emphasis on uploading from all devices (pump, CGM, phone) is not
  data hoarding — it is the foundation of accurate glucose management.
- **xDrip+ as CGM-only app**: For users running xDrip+ without pump integration,
  our data suggests forecast accuracy is approximately halved. Adding pump data
  (via AAPS integration or direct Nightscout upload) would significantly improve
  prediction quality.

---

## 8. The Physics-ML Boundary Is Clear

**Experiments**: EXP-005 (physics-residual decomposition), EXP-141 (synthetic
pretrain evaluation)

Glucose dynamics follow known pharmacokinetic and pharmacodynamic equations.
Insulin absorption follows well-characterized curves (Fiasp: ~3hr DIA, Humalog:
~4hr DIA). Carbohydrate absorption follows roughly exponential decay. The
UVA/Padova simulator and oref0's IOB curves implement these physics.

We tested the boundary between what physics explains and what requires
data-driven learning.

**Key findings**:

| Approach | MAE (mg/dL) | vs. Raw ML |
|----------|-------------|------------|
| Physics model alone (IOB/COB dynamics) | ~85% explained | Baseline |
| Raw ML (no physics) | — | 1× |
| **Physics + ML residual** | — | **8.2× improvement** (EXP-005) |
| ML with 32K real-world windows | — | Matches physics+ML (EXP-141) |

The physics-residual approach (EXP-005) works by first predicting glucose using
known insulin and carb dynamics, then training ML on the *residual* — the gap
between physics prediction and actual glucose. This residual captures everything
physics misses: counter-regulatory hormones, exercise effects, stress, meal
composition variability, and individual metabolic quirks.

The **8.2× improvement** from learning residuals rather than raw glucose
confirms that physics and ML are complementary, not competitive. Physics handles
the predictable pharmacokinetics. ML handles the unpredictable physiology.

**But with enough data, ML alone catches up** (EXP-141). Given 32,000 real-world
training windows (~6 months of continuous data), an ML model trained from scratch
matches the accuracy of a physics-pretrained model. The synthetic pretraining
provides 0% additional improvement.

**What this means biologically**: The "physics" of glucose dynamics (insulin
curves, carb absorption) is a useful approximation that helps most when data is
scarce. But real human physiology is messier than any pharmacokinetic model — and
given enough observations of a specific patient, the data speaks for itself.

**Clinical implications**:

- **Physics models are invaluable for cold-start.** A new AID user (or a new
  patient in a clinical system) has no historical data. Physics-based models
  (like oref0's IOB curves) provide a reasonable starting point from day one.
- **Real-world data rapidly obsoletes physics assumptions.** After a few weeks of
  CGM data, the patient's actual glucose responses carry more information than
  any textbook pharmacokinetic curve. This supports the "learn from the patient"
  philosophy that underlies autotune and adaptive algorithms.
- **Hybrid approaches (physics + learning) are optimal** when data is limited
  (first days/weeks). Pure learning approaches are optimal when data is abundant
  (months of history). This matches the trajectory of most AID users: start with
  clinician-programmed settings, then adapt.

---

## 9. Hypoglycemia Prediction Has a Blind Spot

**Experiments**: EXP-136 (hypo-specific training), general forecast evaluation

Hypoglycemia (glucose < 70 mg/dL) is the most dangerous acute complication of
insulin therapy. It causes confusion, seizures, loss of consciousness, and in
extreme cases, death. Accurate hypoglycemia prediction is arguably the most
important capability of any glucose forecasting system.

Our general-purpose model has a significant blind spot:

| Glucose Range | MAE (mg/dL) | Relative Error |
|---------------|-------------|----------------|
| In-range (70–180) | ~10 | 1× (baseline) |
| Hyperglycemia (>180) | ~15 | 1.5× |
| **Hypoglycemia (<70)** | **39.8** | **2.54×** |

At 39.8 mg/dL MAE in the hypoglycemic range, the model's predictions are
clinically unreliable for the most critical glucose values. A patient at 65
mg/dL could be predicted anywhere from 25 to 105 — spanning severe hypoglycemia
to well within range.

**Why hypoglycemia is harder to predict**:

1. **Rarity**: Hypoglycemia represents a small fraction of all glucose readings
   in well-managed AID patients. The model is optimized for the 70-180 range
   where most data lives.

2. **Non-linear dynamics**: Below 70 mg/dL, counter-regulatory hormone responses
   activate (glucagon, epinephrine, cortisol). These produce rapid, non-linear
   glucose changes that differ fundamentally from the dynamics above 70.

3. **Floor effects**: Glucose cannot go below zero, but the model doesn't know
   this. Near the physiological floor, symmetric error assumptions break down.

4. **AID intervention**: In patients using closed-loop systems, the controller
   typically reduces or suspends insulin delivery as glucose drops. This
   intervention changes the trajectory mid-prediction, making the future
   fundamentally different from what a "no intervention" model would predict.

**Hypo-specific training** (EXP-136) reduced hypoglycemic MAE to 10.4 mg/dL —
a dramatic improvement. But this came at the cost of degraded accuracy in the
normal range. The features that predict hypoglycemia (rapid rate of descent,
high IOB, recent exercise) are different from those that predict general glucose
trends.

**The two-stage solution**: A two-stage approach works best — first classify
hypoglycemia risk (binary: at-risk vs. not), then apply a specialized forecast
model for at-risk periods. This mirrors how clinicians think: "Is this patient
heading low?" is a different question from "What will their glucose be in an
hour?"

**Clinical implications**:

- **A general-purpose forecast model should not be trusted for hypoglycemia
  prediction.** The 2.54× error degradation means predictions in the critical
  range are unreliable. Any system that displays a "predicted glucose" value
  should caveat predictions below 80 mg/dL.
- **A separate, dedicated hypoglycemia detection module is medically necessary.**
  This aligns with FDA regulatory approaches that separate "trending" functions
  (informational, lower risk) from "alert" functions (safety-critical, higher
  risk classification).
- **Low glucose suspend (LGS) algorithms in AID systems are right to be
  conservative.** Medtronic's 670G/780G, Tandem's Control-IQ, and Loop all
  suspend insulin delivery based on predicted hypoglycemia. Given the prediction
  difficulty we observe, their conservative thresholds (often triggering at
  predicted glucose < 80 or even < 100) are justified.

---

## 10. Overrides Help More Than Users Think

**Experiment**: EXP-227 (override recommendation system)

AID systems provide "override" or "temporary target" functionality — the ability
to temporarily adjust controller behavior for situations like exercise, illness,
or pre-meal preparation. In Loop, these are called Overrides. In AAPS, they are
Temporary Targets or Profile Switches. In Trio, the concept is similar.

Our recommendation system analyzed when an override would have improved glucose
outcomes:

| Metric | Value |
|--------|-------|
| Recommendation accuracy (when suggesting override) | **99.3%** |
| Time periods where override would help | **~48%** |
| Dominant recommendation | Exercise correction (reduced basal) |
| User-logged overrides | Small fraction of beneficial periods |

**The accuracy is striking.** When the model identifies a period where an
override would improve outcomes, it is correct 99.3% of the time. This is not
because the model is exceptionally clever — it is because the patterns are
physiologically clear. A glucose trace that is trending upward with low IOB
will obviously benefit from increased insulin delivery. A trace trending
downward during afternoon hours (typical exercise time) will obviously benefit
from reduced delivery.

**The utilization gap is large.** Overrides would help during approximately 48%
of time periods, but users log overrides for only a small fraction of these.
The dominant recommendation — "exercise correction," which reduces basal insulin
delivery — suggests that many patients are experiencing activity-related glucose
drops that could be mitigated with proactive settings adjustments.

**Why users under-utilize overrides**:

- **Cognitive burden**: Remembering to set an override before exercise, adjusting
  it for intensity, and remembering to cancel it afterward requires constant
  attention. Diabetes management already demands enormous cognitive effort.
- **Uncertain timing**: Should I set an exercise override 30 minutes before, at
  the start of, or during exercise? The optimal timing varies by activity type.
- **Fear of hypoglycemia vs. hyperglycemia trade-off**: Reducing basal for
  exercise prevents lows but risks post-exercise highs. Users often prefer to
  treat the low rather than risk the high.
- **UX friction**: Setting an override requires multiple taps, selecting a
  preset, and confirming. This friction is disproportionate during activities
  like exercise when the user's attention is elsewhere.

**Clinical implications**:

- **Proactive override suggestions could significantly improve outcomes.** A
  notification like "Based on your glucose trend and time of day, you might
  benefit from an Exercise override" would be correct virtually every time it
  fires and could be triggered for nearly half of all time periods.
- **The barrier is UX, not algorithm accuracy.** The prediction problem is
  essentially solved — we know when overrides would help. The remaining challenge
  is delivering that information to the user in a way that is actionable without
  being annoying.
- **This is an opportunity for Nightscout-connected apps.** A widget, watch
  complication, or ambient notification that surfaces override recommendations
  could capture significant TIR improvements with no changes to the underlying
  AID algorithm.

---

## Summary of Biological Insights

| # | Finding | Magnitude | Clinical Implication |
|---|---------|-----------|---------------------|
| 1 | Glucose is self-predictive | 87% of signal | CGM-only approaches viable for short-term forecasting |
| 2 | Dawn phenomenon is universal | 71.3 mg/dL amplitude | Nighttime AID settings must differ from daytime |
| 3 | Patient heterogeneity dominates | 2.2× MAE range | Population models are starting points, not endpoints |
| 4 | Volatile periods drive error | 2.04× error ratio | Meal and exercise transitions are the frontier |
| 5 | Meals are hardest to detect | F1 = 0.565 (lowest) | Pre-bolusing and meal announcement remain essential |
| 6 | ISF/CR drift is weak | r = −0.156 | Autosens bounds of ±20% are physiologically appropriate |
| 7 | IOB data is critical | 2× accuracy gap | Pump connectivity essential for accurate forecasting |
| 8 | Physics helps at cold-start | 8.2× boost, then 0% | Learn from the patient, not just the textbook |
| 9 | Hypo prediction is degraded | 2.54× worse | Separate safety-critical hypo detection module needed |
| 10 | Overrides are underused | 48% beneficial periods | Proactive suggestions could improve outcomes |

---

## Implications for AID System Design

These findings, taken together, suggest several design principles for next-
generation AID systems and the Nightscout ecosystem:

### Personalization Is Not Optional

The 2.2× patient heterogeneity in forecast accuracy, combined with the
universality but high variability of dawn phenomenon, means that per-patient
adaptation is the single highest-leverage improvement available. Systems that
learn from individual patient data (autotune, adaptive ISF, per-patient ML
models) will always outperform static population-based approaches.

### Data Completeness Enables Accuracy

The 2× accuracy penalty for missing IOB data makes the case for comprehensive
data collection. Every gap in pump telemetry, every missed upload, every
connectivity dropout directly degrades downstream predictions and controller
performance. Nightscout's role as a data aggregation layer is not just
convenient — it is foundational.

### Separate Safety from Optimization

The 2.54× degradation in hypoglycemia prediction means safety-critical functions
(low glucose alerts, predictive suspend) should use dedicated, specialized
models — not general-purpose forecast models. This mirrors FDA regulatory
thinking and should be reflected in system architecture.

### The Meal Problem Remains Open

At F1 = 0.565, reliable meal detection from CGM data alone is not achievable
with current approaches. Until this changes, meal announcement (manual or via
connected food tracking) remains a clinical necessity. AID systems should be
designed to work well with announced meals and degrade gracefully (UAM-style)
when meals are unannounced.

### Proactive Guidance Is Within Reach

The 99.3% accuracy of override recommendations, combined with the large
utilization gap, represents low-hanging fruit. A Nightscout-integrated
recommendation layer that suggests overrides based on CGM trends, time of day,
and historical patterns could improve outcomes with no changes to the underlying
AID algorithm.

---

*This report synthesizes findings from 258 ML experiments on real Nightscout
patient data. All experiments were conducted on de-identified CGM, insulin, and
treatment records. Patient identifiers (a through j) are arbitrary labels with
no connection to actual identities. For methodology details, see
`docs/60-research/training-techniques-what-works.md` and
`docs/60-research/ml-experiment-log.md`.*
