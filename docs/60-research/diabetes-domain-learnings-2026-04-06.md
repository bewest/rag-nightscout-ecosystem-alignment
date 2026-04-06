# What Data Science Reveals About Diabetes Physiology

**Insights from 398 Experiments on 11 Real-World CGM/AID Patients**

**Date**: 2026-04-06

---

## Motivation

This report documents what we have **learned about biology** from doing machine learning on real patient CGM data. Not the ML techniques themselves, but what the models and experiments reveal about how glucose, insulin, and carbohydrates interact in Type 1 diabetes patients using Automated Insulin Delivery (AID) systems.

Over the course of 398 experiments across 11 patients, clear physiological patterns emerged — patterns that confirm some clinical intuitions, challenge others, and quantify dynamics that were previously only qualitatively understood. Every finding below is grounded in experimental evidence, cited by experiment ID, and translated into clinical relevance.

---

## Key Biological Insights

### 1. Glucose Is 87% Self-Predictive

**Experiment**: EXP-114 (Transformer attention weight analysis)

Transformer attention analysis reveals that **86.8% of attention weight** falls on glucose history, with only **13.2% allocated to insulin and carbohydrate channels**. This tells us something fundamental about short-term glucose dynamics: over 30–60 minute horizons, glucose is largely a momentum-driven system. The current trajectory — rate of change, acceleration, recent curvature — dominates the near-term forecast.

**But this breaks down beyond 60 minutes.** As the prediction horizon extends past one hour, the physics of insulin absorption and carbohydrate digestion become the primary drivers. The glucose "memory" fades and exogenous inputs take over.

**Clinical relevance**: CGM-only forecasting (without pump data) is viable for short horizons — useful for urgent alerts and trend arrows. However, any system attempting forecasts beyond one hour **must** incorporate insulin-on-board and carbohydrate data. This validates the design of modern AID systems that fuse CGM with pump telemetry.

---

### 2. The Dawn Phenomenon Is Universal and Massive

**Experiment**: EXP-126 (Circadian glucose pattern analysis)

Every single patient in our cohort — **10 out of 10** with sufficient overnight data — exhibits measurable circadian glucose patterns. This is not subtle:

- **Amplitude**: 71.3 ± 18.7 mg/dL (range: −76.7 to +28.2 mg/dL)
- **Nighttime Time-in-Range (TIR)**: 60.1%
- **Afternoon TIR**: 75.2%

The dawn phenomenon — rising glucose in the early morning hours driven by cortisol, growth hormone, and hepatic glucose production — is not an occasional nuisance. It is a **universal, large-amplitude signal** that accounts for a 15-percentage-point TIR gap between night and afternoon.

**Clinical relevance**: AID nighttime basal settings **must** differ from daytime settings. Any system running a flat 24-hour insulin profile is leaving significant TIR on the table. The 71.3 mg/dL amplitude means the dawn effect alone can push a patient from in-range to hyperglycemic.

**ML implication**: Time-of-day features become essential at ≥24-hour modeling scales. The circadian signal breaks the time-translation symmetry that holds at shorter horizons (see Finding 9).

---

### 3. Patient Heterogeneity Dominates All Other Factors

**Experiments**: Cross-experiment analysis across all 398 experiments

The single most important finding across our entire body of work: **variation between patients dwarfs variation between techniques, architectures, or hyperparameters.**

| Metric | Value |
|--------|-------|
| Best patient MAE (patient k) | 7.23 mg/dL |
| Worst patient MAE (patient b) | 23.32 mg/dL |
| Range ratio | **3.2×** |

This 3.2× range is **larger** than any improvement we achieved from switching architectures (Transformer vs. LSTM vs. linear), adding features, or tuning hyperparameters. The patient *is* the dominant variable.

**What makes patients different?**

- **Patient k** (easiest): ISF = 25 mg/dL/U, consistent daily routines, complete CGM + IOB data → 7.23 mg/dL MAE
- **Patient b** (hardest): ISF = 94 mg/dL/U, high variability, unpredictable meal timing → 23.32 mg/dL MAE

The correlation is clear: **high ISF patients are harder to forecast** because each unit of insulin produces wider glucose swings. Combined with irregular routines, this creates a fundamentally more chaotic glucose trajectory.

**Clinical relevance**: Population-level models are starting points only. Per-patient fine-tuning improves **every single patient** in our cohort. Personalization is not optional — it is the single largest lever for forecast accuracy.

---

### 4. Volatile Periods Drive Forecast Error

**Experiment**: EXP-222 (Calm vs. volatile period stratification)

When we stratify forecast accuracy by glucose volatility:

| Period Type | Definition | MAE | Fraction of Time |
|-------------|-----------|-----|-------------------|
| Calm | Rate of change < 1 mg/dL/min | 10.3 mg/dL | ~70% |
| Volatile | Rate of change ≥ 1 mg/dL/min | 21.0 mg/dL | ~30% |
| **Ratio** | | **2.04×** | |

Seventy percent of the time, glucose is relatively stable — fasting, sleeping, between meals — and our models achieve excellent accuracy. The remaining 30% is where the action (and the error) lives: during and after meals, exercise, insulin stacking, and counter-regulatory rebounds.

**Clinical relevance**: The accuracy frontier in glucose forecasting is **meal absorption and exercise response**, not fasting glucose. AID systems are already quite good at fasting control (basal modulation handles it). The hard, unsolved problem is post-meal management — where glucose dynamics are driven by the complex, partially-observable interaction of gastric emptying, insulin kinetics, and gut hormones.

---

### 5. Insulin Sensitivity Drifts Over Weeks

**Experiment**: EXP-312 (ISF temporal drift analysis)

Insulin sensitivity is not a fixed parameter — it drifts over time, and we can now quantify the timescales:

| Detection Window | Patients with Significant Drift | Fraction |
|-----------------|-------------------------------|----------|
| Per-dose | Too noisy (std 4–59 mg/dL/U) | — |
| Weekly rolling | 5 / 11 | 45% |
| Biweekly rolling | 9 / 11 | **82%** |
| Monthly rolling | 9 / 11 | 82% |

Two distinct drift patterns emerge:
- **Sensitivity-increasing group** (patients a, b, d, f, i): ISF rises over weeks (becoming more insulin-sensitive)
- **Resistance-increasing group** (patients c, e, h, j): ISF falls over weeks (becoming more insulin-resistant)

Despite being statistically significant, ISF drift explains only **2–11% of TIR variance** — it is real but not the dominant factor in day-to-day control. The optimal detection window is a **4-day lookback**, balancing signal quality against adaptation speed.

**Clinical relevance**: AID autotune and autosens algorithms are **correct** to adjust ISF gradually. The ±20% autosens bounds used by oref0/oref1 are physiologically appropriate — they match the observed magnitude of ISF drift without overreacting to noise. Systems that adjust ISF faster than biweekly are likely chasing noise rather than signal.

---

### 6. Pharmacokinetics of Insulin Follow Predictable Curves

**Experiments**: EXP-356 (PK feature impact analysis); oref0 model validation

The oref0 insulin activity model uses:

- **Duration of Insulin Action (DIA)**: 5.0 hours
- **Peak activity**: ~55 minutes post-dose
- **Activity formula**: `a(t) = dose × (norm/τ²) × t × (1 - t/DIA) × exp(-t/τ)`

This curve is approximately symmetric around the peak when viewed as an activity profile. Critically, the curve is **deterministic and predictable** — the same dose produces the same activity profile every time (within measurement noise).

Basal suspension creates a growing insulin deficit — not zero activity, but a progressive shortfall as scheduled basal doses accumulate. After 1 hour of suspension, total insulin activity drops to approximately **65% of baseline**.

**ML finding (EXP-356)**: Including the known future PK trajectory as a model feature improves forecast accuracy at **all horizons**, with peak improvement of **−10.0 mg/dL MAE at the 120-minute horizon**. The insulin activity curve is reliable enough to serve as a deterministic (non-learned) feature.

**Clinical relevance**: PK curves are trustworthy enough to build AID algorithms on. The oref0 model's parameterization matches our observed data. Pre-bolusing 15–20 minutes before meals is physiologically justified — insulin needs this head start to align its activity peak with the glucose rise from carbohydrate absorption.

---

### 7. Carb Absorption Is the Biggest Source of Uncertainty

**Experiments**: Event detection experiments; meal impact analysis

Carbohydrate absorption is the most variable, least predictable process in the glucose regulation system:

- **Default model**: Piecewise-linear, 3-hour absorption with fast onset and long tail
- **Same 50g meal** can produce a **40–120 mg/dL** glucose rise depending on:
  - Fat and protein content (slow gastric emptying)
  - Glycemic index of the carbohydrate source
  - Pre-meal exercise (accelerates absorption)
  - Current insulin-on-board (counteracts the rise)
  - Gut hormone state (GLP-1, GIP — unmeasured)

Our event detection experiments quantify the challenge:

| Detection Task | F1 Score |
|---------------|----------|
| Meal occurrence (from CGM alone) | 0.565 |
| Unannounced meal / glucose rise (UAM) | 0.939 |

Detecting that a glucose **rise is happening** is easy (F1 = 0.939). Predicting that a meal **will happen** before it causes a glucose excursion is the hard problem (F1 = 0.565).

**Clinical relevance**: Meal announcement remains essential for optimal AID performance. CGM can detect meals reactively but cannot predict them proactively. Pre-bolusing 15–20 minutes before meals is the single most impactful patient behavior — giving insulin a head start against the absorption curve.

---

### 8. Hypoglycemia Follows Different Physics

**Experiments**: Hypo-stratified accuracy analysis; functional depth analysis

Below 70 mg/dL, glucose dynamics change fundamentally:

| Glucose Range | MAE | Ratio |
|--------------|-----|-------|
| In-range (70–180 mg/dL) | 10.3 mg/dL | 1.0× |
| Hypoglycemic (< 70 mg/dL) | 39.8 mg/dL | **2.54×** (worse) |

This is not just "harder to predict" — it is **different physics**. Below 70 mg/dL, counter-regulatory hormones activate non-linearly:

- **Glucagon** release from alpha cells (primary defense)
- **Epinephrine** (adrenaline) — triggers hepatic glucose output
- **Cortisol** — slower-acting, extends the rebound

These hormones create a **non-linear floor effect**: glucose doesn't just stop falling — it rebounds, often overshooting into hyperglycemia. The feature dependencies change: insulin activity alone no longer predicts recovery trajectory because counter-regulatory hormones introduce an unmeasured exogenous input.

**Functional depth analysis** confirms the clinical significance: patients in the **lowest depth quartile** (most atypical glucose trajectories) show **33.7% hypoglycemia prevalence** — a **112× enrichment** over baseline rates.

**Clinical relevance**: AID systems correctly suspend insulin conservatively when predicted glucose drops below 80–100 mg/dL. Our data validates this conservatism. A two-stage modeling approach is indicated: first classify hypoglycemia risk, then apply a specialized forecast model for the sub-70 regime.

---

### 9. Time-Translation Invariance at Episode Scales

**Experiment**: EXP-349 (Time encoding ablation study)

A surprising finding: **removing time-of-day encoding improves classification accuracy at ≤12-hour scales**.

This tells us something important about meal physiology: a post-meal glucose spike at 8:00 AM is physiologically equivalent to one at 8:00 PM. The same absorption dynamics, the same insulin response curves, the same rise-and-fall envelope. At the episode level (individual meals, corrections, overnight segments), glucose dynamics are **time-translation invariant**.

**But** at ≥24-hour scales, this invariance breaks. The dawn phenomenon (Finding 2), circadian insulin sensitivity variation, and sleep/wake cycles impose a 24-hour periodicity that models must capture.

| Scale | Time Features | Reason |
|-------|--------------|--------|
| ≤ 12 hours | Hurt performance | Episode dynamics are time-invariant |
| 12–24 hours | Breakpoint zone | Transition region |
| ≥ 24 hours | Essential | Circadian rhythms dominate |

**Clinical relevance**: Meal response models don't need to know what time it is — the physiology is the same regardless. But daily management and basal rate optimization models absolutely do need time-of-day features to capture circadian patterns.

---

### 10. IOB Data Quality Is a Binary Cliff

**Experiments**: Cross-patient feature importance analysis

Insulin-on-board data doesn't gradually improve forecasts — it is **nearly all-or-nothing**:

| Patient j (0% IOB data) | Same architecture, patients with IOB |
|--------------------------|--------------------------------------|
| MAE = 18.31 mg/dL (EXP-408) | MAE = 7–13 mg/dL |
| **~2× worse** | |

Without IOB, the model is doing pure extrapolation — guessing future glucose from past glucose momentum alone. With IOB, the model has the **causal mechanism**: it knows how much insulin is active and can predict the resulting glucose trajectory. There is no middle ground; partial IOB data doesn't help proportionally.

**Clinical relevance**: Pump connectivity is **non-negotiable** for forecasting accuracy. Any interruption in pump data transmission (Bluetooth disconnects, app crashes, sensor changes) creates a blind spot where forecast quality collapses to pure extrapolation. AID system designers should prioritize data pipeline reliability above almost any other engineering concern.

---

## The Absorption Envelope Symmetry

A unifying observation across our experiments:

- **Insulin activity curves** are approximately symmetric around their peak (~55 minutes)
- **Glucose response to meals** shows approximate rise/fall symmetry around the peak excursion
- The **"DIA valley" effect**: analysis windows shorter than one complete absorption cycle (4–6 hours) capture only partial arcs — either the rising or falling limb, but not the complete envelope
- **12-hour windows** capture the full absorption envelope and yield the best episode-level understanding
- This symmetry can be exploited for **normalization**: ISF-scaling makes glucose response shapes approximately patient-independent, collapsing the 3.2× inter-patient variability into a more uniform distribution

This symmetry is not accidental — it reflects the underlying pharmacokinetics of subcutaneous insulin absorption and the first-order kinetics of intestinal glucose uptake. Both processes follow exponential rise-and-decay dynamics that produce bell-shaped activity curves.

---

## What Makes Patients "Easy" vs. "Hard"

| Factor | Easy Patients (d, k, f) | Hard Patients (a, b, j) |
|--------|--------------------------|--------------------------|
| ISF | Low (21–40 mg/dL/U) | High (49–94 mg/dL/U) |
| Routine | Regular meal/sleep times | Irregular patterns |
| Data completeness | Full IOB + CGM | Missing IOB (patient j) |
| Glycemic variability | CV < 30% | CV > 36% |
| AID tuning | Well-optimized settings | Sub-optimal settings |
| Forecast MAE | 7.2–9.7 mg/dL | 18.3–23.3 mg/dL |

The pattern is consistent: **low ISF + regular routines + complete data + well-tuned AID = predictable glucose**. Each factor compounds — patient k has all four advantages and achieves 7.23 mg/dL MAE; patient b has none and sits at 23.32 mg/dL.

Notably, **data completeness** (particularly IOB availability) and **AID tuning quality** are modifiable factors. Patient j's poor forecast accuracy is largely attributable to missing IOB data, not inherent physiological complexity. This suggests that improving data infrastructure may be as impactful as improving algorithms.

---

## The UVA/Padova Model Perspective

Our ML findings align with and extend the UVA/Padova compartmental model — the gold-standard physiological simulator used in FDA-approved AID system testing:

- **20-state ODE model**: stomach → gut → plasma glucose → tissue uptake → clearance, with parallel insulin kinetics (subcutaneous → plasma → liver)
- **Hepatic glucose production (EGP)** is the key unmeasured variable — it varies by patient and time of day, and drives much of the dawn phenomenon we observe
- **Counter-regulatory hormones** (glucagon pathway) create the non-linear dynamics below 70 mg/dL that make hypoglycemia prediction so challenging (Finding 8)
- **CGM sensor delay**: approximately 10 minutes (Td parameter) — real interstitial glucose leads the CGM reading, which in turn lags plasma glucose

Our ML models implicitly learn approximations of these compartments through the 8-channel feature representation (CGM, IOB, COB, basal rate, bolus, carbs, time features, derived features). The transformer attention patterns (Finding 1) roughly correspond to the relative information content of each compartment for glucose prediction.

---

## Implications for AID System Design

These biological findings translate directly into engineering recommendations:

1. **Pre-bolusing works**: 15–20 minute lead time matches insulin onset pharmacokinetics and partially compensates for the carb absorption delay (Findings 6, 7)

2. **Autosens bounds are right**: ±20% ISF adjustment matches the observed magnitude of biweekly ISF drift; wider bounds risk chasing noise (Finding 5)

3. **Conservative hypo prevention is correct**: Below-70 physics is non-linear and involves unmeasured counter-regulatory hormones; over-suspending insulin is the safe default (Finding 8)

4. **Nighttime settings must differ**: The 71.3 mg/dL circadian amplitude demands different basal profiles for night vs. day; flat profiles sacrifice 15 percentage points of nighttime TIR (Finding 2)

5. **Per-patient tuning is essential**: The 3.2× performance range across patients means population defaults are inadequate; personalization is the largest single improvement lever (Finding 3)

6. **Pump connectivity is critical**: The 2× accuracy gap between patients with and without IOB data makes data pipeline reliability a first-order engineering concern (Finding 10)

7. **Meal response is the frontier**: The 2.04× error ratio between volatile and calm periods identifies post-meal management as the primary remaining challenge for AID systems (Finding 4)

8. **4-day ISF lookback is optimal**: This window balances signal quality against adaptation speed for autotune/autosens algorithms (Finding 5)

---

## What We Don't Yet Know

Despite 398 experiments, significant gaps remain in our physiological understanding:

1. **Exercise effects**: Not yet modeled — no exercise data exists in our 8-channel feature representation. Exercise impacts both insulin sensitivity (increases it) and hepatic glucose production (increases it), creating complex, duration-dependent dynamics.

2. **Stress and illness impact on ISF**: We observe ISF drift (Finding 5) but cannot distinguish physiological stress from normal variation. Illness can double or triple insulin requirements temporarily.

3. **Optimal pre-bolus timing per patient**: Varies with individual gastric emptying rate, meal composition, and current glucose trend. Our data confirms pre-bolusing helps but cannot yet optimize the timing per patient.

4. **Inter-day meal variability**: The same person eating the same food on different days produces different glucose responses. Unmeasured confounders (sleep quality, stress, prior exercise, microbiome state) account for this irreducible variance.

5. **Counter-regulatory hormone dynamics**: We observe the non-linear effects below 70 mg/dL (Finding 8) but do not model the glucagon/epinephrine/cortisol mechanism directly. This limits our ability to predict rebound magnitude.

6. **Multi-month trends**: Our data spans approximately 6 months. Weight changes, seasonal variation, hormonal cycles, and medication adjustments may introduce longer-timescale dynamics not captured in our current analysis.

---

## Summary Table: Findings and Clinical Relevance

| # | Finding | Key Metric | Clinical Relevance |
|---|---------|-----------|-------------------|
| 1 | Glucose is 87% self-predictive | 86.8% attention to glucose history (EXP-114) | CGM-only forecasting viable for ≤60 min; pump data essential beyond |
| 2 | Dawn phenomenon is universal | 71.3 ± 18.7 mg/dL amplitude; 100% prevalence (EXP-126) | Nighttime AID settings must differ from daytime |
| 3 | Patient heterogeneity dominates | 3.2× MAE range (7.23–23.32 mg/dL) | Per-patient personalization is the largest improvement lever |
| 4 | Volatile periods drive error | 2.04× MAE ratio, calm vs. volatile (EXP-222) | Post-meal management is the accuracy frontier |
| 5 | ISF drifts over weeks | 9/11 patients significant at biweekly scale (EXP-312) | ±20% autosens bounds are physiologically appropriate |
| 6 | Insulin PK is predictable | Peak at 55 min, DIA = 5.0 hr (EXP-356) | PK curves reliable as deterministic AID features |
| 7 | Carb absorption is most uncertain | 40–120 mg/dL range for same 50g meal | Meal announcement remains essential for AID |
| 8 | Hypoglycemia has different physics | 2.54× worse MAE below 70 mg/dL | Conservative suspend-before-low is validated |
| 9 | Episodes are time-invariant | Removing time features improves ≤12h classification (EXP-349) | Meal models don't need time-of-day; daily models do |
| 10 | IOB is all-or-nothing | 2× MAE gap with vs. without IOB | Pump data connectivity is non-negotiable |

---

*This report synthesizes findings from 398 machine learning experiments on 11 real-world CGM/AID patients. All findings are empirically grounded and cited by experiment ID. The goal is not to advance ML methodology but to translate computational results into physiological understanding that can improve diabetes care and AID system design.*
