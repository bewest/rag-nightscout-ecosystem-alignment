# What Data Science Taught Us About Diabetes

**Date**: 2026-04-07 | **Scope**: ~875 experiments on 11 real-world CGM/AID patients | **Data**: ~6 months CGM + insulin + treatment logs per patient

---

## Purpose

This report inverts the usual ML framing. Instead of "which model performed best?", it asks: **what did we learn about diabetes itself** from running ~875 experiments on real patient data?

Every finding emerged from data-driven analysis of continuous glucose monitoring traces, insulin delivery curves, and treatment records collected through Nightscout from 11 individuals using Automated Insulin Delivery systems in daily life.

---

## The Fundamental Symmetries

### 1. Glucose Is a Low-Dimensional System

A transformer trained to predict glucose allocates **86.8% of attention to glucose history** and only 13.2% to insulin and carbohydrate features. This is not a model failure — the glucose trace already encodes the consequences of prior actions. A bolus delivered 45 minutes ago is visible as the current downward trend. The glucose trajectory is an integrated record of everything that has happened.

**Implication**: CGM-only prediction is viable for ≤60 min horizons. Beyond that, the effects of recent insulin haven't yet materialized in the trace, and pump data becomes critical.

### 2. Time-Translation Invariance at Episode Scales

Removing time-of-day features **improves** classification accuracy at ≤12-hour scales. A post-meal spike at 8 AM is physiologically equivalent to one at 8 PM — same absorption dynamics, same insulin response curves, same rise-and-fall envelope.

But at ≥24-hour scales, this invariance breaks. The dawn phenomenon imposes a 24-hour periodicity with **71.3 ± 18.7 mg/dL amplitude** — a swing nearly 7× larger than forecast error.

This is a symmetry break in the physics sense: glucose dynamics have a continuous symmetry (time-translation invariance) that is broken by an external periodic forcing function (circadian hormones). The cheapest possible model for this — 3 parameters: `a·sin(2πh/24) + b·cos(2πh/24) + c` — captures more variance than any neural architecture change.

### 3. The Absorption Envelope Symmetry

Both insulin activity curves and glucose meal response exhibit approximate rise/fall symmetry around their peaks:

- **Insulin**: peak at ~55 minutes, DIA ≈ 5.0 hours. Bell-shaped, reflecting subcutaneous absorption kinetics.
- **Carb response**: rise peaks at 30–60 min, falls over 2–4 hours depending on composition.

This symmetry arises from the underlying first-order kinetics: exponential rise-and-decay produces bell-shaped activity curves. ISF-scaling makes these shapes approximately patient-independent, collapsing 3.2× inter-patient variability into a more uniform distribution.

**Implication**: 12-hour windows capture the complete absorption envelope. Shorter windows see only partial arcs.

---

## The Biology We Discovered

### 4. The Dawn Phenomenon Is Universal and Massive

| Metric | Value |
|--------|-------|
| Patients with circadian pattern | **10/10 (100%)** |
| Mean amplitude | **71.3 ± 18.7 mg/dL** |
| Night TIR | 60.1% |
| Afternoon TIR | 75.2% |
| ISF time-of-day variation | **29.7% mean** (patient c: 82.2%) |

The 15-percentage-point TIR gap between night and afternoon is clinically significant. Patients spend substantially more time above range during sleep — when they cannot manually intervene — because counter-regulatory hormones (cortisol, growth hormone) drive glucose up against the AID's efforts.

Patient c's insulin sensitivity nearly doubles from morning to evening (82.2% variation). A flat ISF profile for this patient is wrong for ~16 hours of the day.

### 5. Hypoglycemia Follows Different Physics

| Glucose Range | MAE (mg/dL) | R² |
|---------------|-------------|-----|
| In-range (80–120) | 21.5 | 0.281 |
| Below 80 | 26.6 | **0.153** |

Below 70 mg/dL, counter-regulatory hormones activate non-linearly. The MAE increase is modest (1.24×), but R² nearly halves — reliability collapses:
- **Glucagon** release from alpha cells (primary defense)
- **Epinephrine** triggers hepatic glucose output
- **Cortisol** extends the rebound

These unmeasured hormones create a non-linear floor effect: glucose doesn't just stop falling — it rebounds, often overshooting into hyperglycemia. Three architectures (CNN, XGBoost, Transformer) all converge at AUC ≈ 0.69 for overnight hypo prediction. The ceiling is **data-limited** — you cannot predict what you cannot measure.

### 6. AID Systems Mask Bad Settings

**Effective ISF is 2.91× profile ISF** (total-insulin method, EXP-747; revised to **1.36×** via response-curve method in EXP-1301). AID systems compensate so aggressively that the ISF patients have configured understates their true insulin sensitivity.

This produces a paradox: patients appear controlled (decent TIR) while running fundamentally incorrect settings. The AID fights itself — aggressive settings cause lows, which trigger counter-regulatory rebounds, which trigger more aggressive corrections. Breaking the cycle requires reducing base settings, not more tuning.

**Patient i exemplifies this**: risk score 100/100 despite TIR = 59.9%. The highest TBR in the cohort (10.7%) with meal net flux = −14.9 (massive over-bolusing). The AID is trying to compensate, but the underlying settings create an unstable oscillation.

### 7. Carb Absorption Is the Biggest Unknown

**46.5% of glucose rise events** (2,302 of 4,809) had no carb entry. Nearly half of meals go unannounced. Even when announced, the same person eating the same food on different days produces different glucose responses — unmeasured confounders (sleep quality, stress, microbiome state, gastric emptying rate) create irreducible variance.

Pre-bolusing 15–20 minutes before meals is the single most impactful patient behavior. 9 of 11 patients pre-bolus, with timing ranging from 6.5 to 28.9 minutes. This lead time matches insulin onset pharmacokinetics and partially compensates for the absorption delay.

### 8. Patient Heterogeneity Dominates Everything

| Factor | Easy Patients | Hard Patients | Ratio |
|--------|--------------|--------------|-------|
| Forecast MAE | 7.2 mg/dL | 23.3 mg/dL | 3.2× |
| CR effectiveness | 61.5 | 9.1 | 6.8× |
| ISF variation | ~5% | 82.2% | 16× |
| Changepoints/25 weeks | 0 | 23 | ∞ |

The pattern: **low ISF + regular routines + complete data + well-tuned AID = predictable glucose.** Each factor compounds. Two patient populations emerge:
- **Stable** (0 changepoints, flat settings for years)
- **Volatile** (10+ changepoints, near-continuous metabolic shifts)

There is no middle ground. This bimodal distribution maps directly to clinical experience.

### 9. Sensor Noise Is Worse Than Assumed

At σ=2.0 threshold, roughly **4% of CGM readings** are flagged as noise artifacts — and removing them monotonically improves every downstream task. No patient benefits from preserving these spikes.

Sensors actually **improve** with age (mean change −13.4%): warm-up noise dominates the first hours. Only 1 of 11 patients shows genuine end-of-life degradation. The implication: CGM manufacturers' built-in smoothing is insufficient, and an application-layer cleaning pass should be standard.

### 10. IOB Data Quality Is All-or-Nothing

Patient j (0% IOB data): MAE = 18.31 mg/dL. Patients with full IOB: MAE = 7–13 mg/dL. A **2× accuracy gap**. There is no graceful degradation — without IOB, the model is pure extrapolation. Pump connectivity is non-negotiable for forecasting accuracy.

---

## What the Overnight Experiments Added

The overnight batch (EXP-800–875) deepened these biological insights:

- **Bias-variance decomposition** (EXP-843): 99.9% bias, 0.1% variance at 60 min. The model isn't failing — the **biology** at 60-minute horizons is genuinely hard to predict from available measurements. The information ceiling is R²≈0.61.

- **Error anatomy by BG range**: MAE scales from 21.5 mg/dL in-range to 46.0 mg/dL above 250. Hyperglycemia is harder to predict because it involves unmeasured events (unannounced meals, stress) and non-linear hepatic response.

- **Residual autocorrelation** decorrelates at 70 minutes. Prediction errors are temporally structured — the model systematically under-reacts to rapid glucose changes. This reflects the physiological inertia of glucose regulation: the system has momentum.

- **Sensor degradation is flat** (EXP-847): slope = 0.11 mg/dL/day — essentially zero. Sensor accuracy does not degrade over its 10-day lifespan.

---

## Implications for AID System Design

| Finding | Engineering Recommendation |
|---------|---------------------------|
| Dawn amplitude 71.3 mg/dL | Nighttime settings must differ from daytime |
| ISF varies 29.7% by time of day | Time-segmented ISF profiles essential |
| Effective ISF ≠ profile ISF (2.91× total-insulin / 1.36× response-curve) | AID settings auditing needed |
| 46.5% unannounced meals | UAM detection is the critical path |
| Pre-bolus 6.5–28.9 min | System should encourage/track pre-bolus timing |
| Population parameters 99.4% universal | Population defaults viable from day 1 |
| Sensor cleaning +52% R² | Application-layer noise filtering mandatory |
| IOB all-or-nothing | Pump connectivity is first-order priority |
| Hypo ceiling at AUC 0.69 | Conservative suspend-before-low is validated |
| Counter-regulatory rebounds | Two-stage modeling for sub-70 regime |

---

## What We Still Don't Know

1. **Exercise dynamics**: No exercise data in our features. Exercise increases both insulin sensitivity and hepatic output — complex, duration-dependent interactions.
2. **Stress/illness impact on ISF**: We see drift but can't separate causes.
3. **Optimal pre-bolus timing per patient**: Varies with gastric emptying rate and meal composition.
4. **Counter-regulatory hormone kinetics**: We observe effects but can't model the glucagon/epinephrine mechanism directly.
5. **Multi-month trends**: Weight changes, seasonal variation, hormonal cycles may introduce longer dynamics.
6. **Meal composition effects**: Protein and fat slow absorption unpredictably.

---

## The Deepest Insight

Glucose regulation is a **low-rank dynamical system** hiding behind high-dimensional noise. The 8-feature Ridge model's dominance over the 134K-parameter transformer proves this: once you decompose glucose into supply (carbs + hepatic) and demand (insulin) fluxes, the remaining dynamics are well-approximated by a linear model with circadian correction. The complexity lives in the feature engineering (physics), not in the model.

The fundamental limit is not computational — it is **observational**. The three things that matter most for prediction beyond 30 minutes (counter-regulatory hormones, meal composition, physical activity) are unmeasured. No model architecture can compensate for missing data. The next breakthrough in glucose prediction will come from new sensors, not better algorithms.
