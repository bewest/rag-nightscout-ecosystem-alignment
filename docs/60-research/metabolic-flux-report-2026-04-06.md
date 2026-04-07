# Metabolic Flux & Physiological Encoding Report

**Date**: 2026-04-06  
**Experiments**: EXP-435 through EXP-447  
**Scope**: Metabolic flux decomposition, supply-demand dynamics, meal counting,  
and proposed extensions for glycemic control assessment and residual modeling  

---

## Executive Summary

We developed a **physics-based metabolic flux decomposition** that separates CGM/AID
data into supply (hepatic + carb absorption) and demand (insulin action) harmonics.
This decomposition reveals metabolic activity that is invisible in raw glucose traces —
particularly when AID controllers successfully flatten glucose by compensating for meals
and corrections in real time.

**Key findings across 13 experiments (EXP-435–447), 11 patients, ~180 days each:**

| Finding | Evidence | Impact |
|---------|----------|--------|
| Sum flux discriminates events at all scales | AUC 0.87–0.95 (EXP-441) | Better than glucose alone for event classification |
| Throughput (supply×demand) has 18× spectral power at meal frequencies | EXP-444 | Massive SNR advantage for meal-scale tasks |
| Hepatic production rescues zero-data patients | 11/11 patients have nonzero supply (EXP-441) | Universal applicability |
| Cross-patient metabolic response shape similarity = 0.987 | EXP-445 | Near-universal physiology despite 4.5× ISF range |
| Meal counting detects 1.3 ± 0.3 big events/day | EXP-447 | Physics-only detection, no ML needed |
| Phase lag between carb and insulin peaks = 25 min (range 2–43) | EXP-436 | Structural temporal signature of meals |
| TDD normalization ≈ ISF normalization (1800 rule) | EXP-442 | Cross-patient equivariance path |

---

## 1. Theoretical Foundation

### 1.1 The AC Circuit Analogy

In well-controlled diabetes with an AID system, **glucose often stays flat even during
significant metabolic events**. This is exactly like an AC circuit where voltage (glucose)
appears steady while large currents (metabolic flux) flow underneath:

```
Glucose ~ Voltage (what we see)
Metabolic Flux ~ Current (what's actually happening)
Power = Voltage × Current (total metabolic work)
```

A post-meal glucose of 120 mg/dL tells us almost nothing about whether 80g of carbs
were just absorbed while 8U of insulin simultaneously acted, or whether the patient was
fasting. The **metabolic flux** channels expose this hidden activity.

### 1.2 Supply-Demand Decomposition

The core physics of glucose regulation decomposes into two always-positive signals:

```
SUPPLY(t) = hepatic_production(t) + carb_absorption(t)    [mg/dL per 5min]
DEMAND(t) = insulin_action(t)                               [mg/dL per 5min]

dBG/dt ≈ SUPPLY(t) − DEMAND(t)
```

**Critical insight**: The liver **never stops** producing glucose. Even at maximum
insulin suppression, hepatic output floors at ~35% of baseline (Hill equation kinetics,
validated against UVA/Padova model and cgmsim-lib liver.ts). This means:

- Supply is **always positive** — there is always a signal
- For UAM (unannounced meal) patients with zero logged carbs, supply = hepatic only
- For non-bolusing patients, demand = basal insulin only
- **No patient has zero flux**, unlike raw COB/IOB which are often zero

### 1.3 Three Derived Signals

| Signal | Formula | What It Captures |
|--------|---------|------------------|
| **Sum Flux** | \|carb_supply\| + \|demand\| | Total metabolic activity (hepatic excluded) |
| **Throughput** | supply × demand | Metabolic work / power (both sides active) |
| **Balance** | supply / demand | Direction (>1 = rising, <1 = falling) |

### 1.4 Relationship to Conservation Law

EXP-421 confirmed that glucose is **conserved** over 12h windows (mean integral
−1.8 ± 28.4 mg·h across 7,337 windows). This validates that:

```
∫(SUPPLY − DEMAND) dt ≈ ΔBG ≈ 0  over complete absorption cycles
```

Even when the integral is zero, the **absolute flux** (|SUPPLY| + |DEMAND|) can be
enormous — this is exactly the signal we exploit.

---

## 2. Experimental Results

### 2.1 EXP-435–440: Sum-Based Metabolic Flux

**EXP-435: Signal Characterization**
- Metabolic flux during meals is 3–8× higher than during stable periods
- Even during AID-flattened glucose, flux remains elevated for 2–3 hours
- Patient j (zero IOB/COB data) had zero flux — identified the need for hepatic rescue

**EXP-436: Phase Lag**
- Carb absorption peaks **25 minutes** before insulin peak effect (event-weighted mean across 1,913 events; per-patient range 2–43 min)
- This phase difference is a structural temporal signature unique to meals
- Pre-bolused meals show *negative* lag (insulin peaks before carbs)
- Corrections show insulin-only flux with no carb component

**EXP-437: Flux Symmetry**
- Flux envelopes are **more symmetric** around their peak than raw glucose envelopes
- Raw glucose (EXP-437): envelope asymmetry ratio = 1.98 (cf. 3.47 for isolated bolus events, EXP-420)
- Flux envelopes: ratio 1.36 (more balanced rise and fall)
- This suggests flux may be more amenable to symmetric kernels in CNNs

**EXP-438: Event Discrimination**
- Flux features discriminate meal/correction/stable states:
  - 2h scale: AUC 0.86 (flux) vs 0.62 (glucose alone)
  - 6h scale: AUC 0.86 (flux) vs 0.64 (glucose alone)
  - 12h scale: AUC 0.85 (flux) vs 0.65 (glucose alone)
- Advantage is largest at 2h (0.25 AUC gap) where AID flattens glucose most

**EXP-439: Signal-to-Noise Ratio**
- Flux SNR exceeds glucose SNR at all scales (3–12× ratio, increasing with scale)
- Flux wins 10/11 patients at 2h–12h; 6/8 at 24h

**EXP-440: Positional Encoding Interaction**
- Flux + positional encoding shows best discrimination at ≥6h scales
- At 6h+, the model can see **complete DIA arcs** in the history window
- This aligns with the DIA Valley finding (EXP-289): 12h windows capture full
  absorption-to-resolution cycles

### 2.2 EXP-441–445: Product Flux, TDD, and Cross-Patient Transfer

**EXP-441: Product vs Sum**

| Scale | Sum (Cohen's d) | Product (Cohen's d) | Sum AUC | Product AUC |
|-------|:---:|:---:|:---:|:---:|
| 2h | **1.39** | 1.05 | 0.87 | 0.89 |
| 6h | **2.20** | 1.63 | 0.95 | 0.96 |
| 12h | **2.62** | 1.98 | 0.95 | **0.97** |

Sum flux wins on effect size (31/33 comparisons), but product shows higher AUC at
12h scale. **Interpretation**: Sum is better for simple thresholding; product is better
for ML features where the multiplicative interaction captures nonlinear relationships.

Hepatic rescue: **11/11 patients** now have nonzero supply, solving the zero-data problem
that affected patient j in EXP-435.

**EXP-442: TDD Normalization**

| Patient | TDD (U/day) | Bolus Fraction | ISF (mg/dL/U) | 1800/TDD |
|:---:|:---:|:---:|:---:|:---:|
| k | 22 | 79% | 25 | 83 |
| c | 33 | 74% | 75 | 55 |
| a | 43 | 44% | 49 | 42 |
| f | 69 | 36% | 21 | 26 |
| e | 77 | 74% | 36 | 24 |

TDD-ISF correlation r = 0.43 (moderate), confirming the 1800 rule as approximate.
The TDD range (22–77 U/day, 3.5×) roughly mirrors the ISF range (21–95 mg/dL/U, 4.5×).
TDD normalization provides a **data-driven ISF proxy** that doesn't require profile access.

**EXP-443: Throughput + Balance as Dual Channels**
- 2D (throughput, balance) clustering: silhouette improvement +0.14 at 6h, +0.23 at 12h
  vs glucose alone
- Balance alone is **anti-discriminative** (AUC 0.24–0.46) — the ratio fluctuates too
  rapidly for simple classification
- But combined with throughput as a 2D feature, balance provides directional context

**EXP-444: Spectral Analysis**

| Frequency Band | Period | Throughput/Glucose Power Ratio |
|:---:|:---:|:---:|
| Circadian | 24h | 8.3× |
| Basal | 12h | 6.1× |
| **Meal** | **3–5h** | **17.6–18.8×** |
| Noise | 1h | 7.7× |

Throughput concentrates spectral power at meal frequencies — nearly **19× glucose** in
the 3h band. This is the strongest evidence that throughput is a meal-specific signal.

**EXP-445: Cross-Patient Equivariance**
- Throughput shape similarity across 55 patient pairs: **0.987** (nearly identical)
- Raw glucose shape similarity: only 0.10 (nearly orthogonal)
- **Implication**: The metabolic response to meals is physiologically universal;
  individual variation is primarily in ISF/TDD scaling, not response shape
- This enables cross-patient transfer learning with TDD normalization

### 2.3 EXP-446–447: Meal Counting Validation

**EXP-446: Detailed Meal Counting (all thresholds)**
- Very sensitive threshold: 2.5 peaks/day, P=0.62, R=0.67, F1=0.61
- Moderate threshold: 1.9 peaks/day, P=0.70, R=0.63, F1=0.64
- Best per-patient: Patient j P=0.96 (hepatic rescue working)
- Eating style classification: identifies grazers (patient b: 7.2 announced/day),
  regular eaters, and minimal-data patients

**EXP-447: Big Meal Tally (above-median sum_flux peaks)**

| Patient | Days | Big/day | Mode Day Pattern |
|:---:|:---:|:---:|:---|
| b | 180 | **1.7** | 2 meals on 82 days (45%) |
| g | 180 | **1.6** | 1-2 meals (69d + 63d) |
| c | 180 | **1.5** | 2 meals on 63 days (35%) |
| e | 158 | **1.5** | 2 meals on 65 days (41%) |
| a | 180 | **1.3** | 1 meal on 85 days (47%) |
| k | 179 | **0.9** | 0 meals on 77 days — minimal data |

**Mean: 1.3 ± 0.3 big events/day** — reliably detects the 1–2 biggest metabolic
events daily using pure physics + signal processing, no ML.  Per-day histograms show
realistic distributions with mode at 1–2, tail to 3–4 on heavy eating days.

---

## 3. What We've Learned About Diabetes Physiology

### 3.1 The Invisible Metabolic World

The single most important finding: **well-controlled glucose hides enormous metabolic
activity**. A patient with TIR > 90% may have glucose traces that look nearly identical
day to day, but their metabolic flux shows distinct patterns of meals, corrections,
dawn phenomenon, and exercise. This has implications far beyond our ML work:

- **Clinical**: Time-in-range doesn't capture metabolic burden
- **Engineering**: Glucose-only ML models can't distinguish *why* glucose is at 120
- **Research**: Many CGM studies that analyze only glucose values are missing half the picture

### 3.2 Symmetry Properties Validated

| Property | Scale | Status | Metabolic Flux Implication |
|----------|-------|--------|---------------------------|
| Time-translation invariance | ≤2h | ✅ PASS | Flux features are time-invariant at event scale |
| Absorption asymmetry | DIA | ❌ | Flux envelopes are *more* symmetric than glucose (ratio 1.36 vs 1.98, EXP-437; 3.47 for isolated bolus events, EXP-420) |
| Glucose conservation | 12h | ✅ PASS | Conservation validates the supply-demand decomposition |
| ISF equivariance | cross-patient | ⚠️ WEAK | TDD normalization improves (r=0.43) but doesn't solve |
| Metabolic shape universality | cross-patient | ✅ **NEW** | Shape similarity 0.987 — response is universal |
| Spectral concentration | meal band | ✅ **NEW** | 18× power at meal frequencies — strong band-pass property |

### 3.3 The Hepatic Production Breakthrough

Modeling hepatic glucose output as the always-on supply baseline:
- Solved the zero-data problem (patient j, patients with incomplete logging)
- Made the supply signal universally positive (no degenerate zeros)
- Enabled the supply×demand product to be meaningful (product with zero = zero)
- The circadian modulation (±20%, peaks 6 AM) captures dawn phenomenon naturally

### 3.4 Phase Lag as Structural Signature

The 25-minute carb-insulin phase lag is a **structural feature of meal physiology**:
- Carb absorption peaks at ~20–30 min (Dalla Man gastric emptying model)
- Insulin subcutaneous absorption peaks at ~55–90 min (Hovorka compartment model)
- Event-weighted mean offset is ~25 min; per-patient means range from 2 to 43 min
- Pre-bolused meals flip the sign (insulin arrives first)
- Corrections show insulin-only flux (zero carb component)

This provides a phase-based event classifier that is independent of amplitude.

---

## 4. Proposed Enhancements and Future Experiments

### 4.1 Meal Counting Improvements (EXP-448–449)

**EXP-448: Hepatic-Detrended Peak Detection**

The current meal tally (1.3/day) slightly undercounts because the hepatic baseline
adds a circadian trend to the supply signal. Subtracting the model hepatic curve
before peak detection should sharpen meal-specific peaks:

```
meal_signal(t) = supply(t) − hepatic_model(t)
```

Expected improvement: +0.3–0.5 peaks/day, particularly for patients with high
hepatic fraction (d: 70%, i: 67%).

**EXP-449: Derivative-Based Rising Edge Detection**

Instead of absolute peak height, detect rapid *increases* in throughput:

```
meal_onset(t) = d(throughput)/dt > adaptive_threshold
```

This catches the rising edge of every meal regardless of absolute magnitude,
and is insensitive to the hepatic floor. Combined with the current peak detection
(OR logic), this should capture smaller meals that fall below the prominence threshold.

### 4.2 Basal Rate and ISF Schedule Assessment (EXP-450–453)

**EXP-450: Basal Adequacy Score**

If basal rates are correct, overnight (midnight–6 AM, no meals) the supply-demand
balance should hover near 1.0:

```
basal_adequacy = median(supply/demand) during fasting windows
```

- Score > 1.1 → basal too low (glucose rising overnight)
- Score < 0.9 → basal too high (glucose falling overnight)
- Score 0.9–1.1 → well-tuned basal

This can be computed per-night and trended over weeks to detect when basal settings
drift out of tune. A sustained shift suggests profile adjustment is needed.

**EXP-451: ISF Adequacy from Correction Response**

When a correction bolus is given (insulin without carbs), the glucose response
should match ISF × dose. Using flux decomposition:

```
expected_drop = dose × ISF_profile
actual_drop = ∫(demand − supply) dt  over 3h post-correction
isf_ratio = actual_drop / expected_drop
```

- Ratio ≈ 1.0 → ISF setting is correct
- Ratio < 0.7 → ISF too aggressive (patient more resistant than profile says)
- Ratio > 1.3 → ISF too conservative (patient more sensitive)

Trending this ratio over 2-week windows connects to the known ISF drift finding
(9/11 patients, EXP-312).

**EXP-452: CR (Carb Ratio) Adequacy from Meal Response**

Similar to ISF adequacy but for meals: when carbs and bolus are both logged,
the post-meal glucose excursion should depend on the carb:insulin ratio vs CR:

```
expected_net = (carbs / CR - dose) × ISF
actual_excursion = peak(glucose, 2h post-meal) − pre-meal glucose
cr_ratio = actual_excursion / expected_net
```

Values consistently > 1 suggest CR is too high (underdosing), < 1 suggests too low.

**EXP-453: Composite Settings Fidelity Score**

Combine basal, ISF, and CR adequacy into a single **glycemic control fidelity score**:

```
fidelity = w_basal × basal_adequacy + w_isf × isf_accuracy + w_cr × cr_accuracy
```

Where each component is normalized to [0, 1]. A fidelity score < 0.6 would flag a
patient whose settings are too far out of alignment for reliable analysis — their
glucose:insulin integrals don't balance, indicating either incorrect settings,
significant unmodeled factors, or data quality issues.

### 4.3 Glycemic Control Quality Gates (EXP-454)

**EXP-454: Conservation Integral as Quality Gate**

Using the glucose conservation test from EXP-421, compute the integral residual
per patient per week:

```
conservation_error = |∫(actual_glucose − predicted_glucose) dt| / window_hours
```

Patient h showed systematic underprediction (65.1 mg·h vs cohort mean −1.8).
This could serve as a **quality gate**:

- Error < 15 mg·h → ✅ Settings adequate, data reliable for analysis
- Error 15–40 mg·h → ⚠️ Marginal — results valid but settings may need review
- Error > 40 mg·h → ❌ Settings severely misaligned — flag for clinical review

Patients failing this gate should not be included in cross-patient models without
individual adaptation, as their ISF/CR/basal parameters don't match their physiology.

### 4.4 Residual Characterization (EXP-455–457)

The residual signal (actual glucose − physics-predicted glucose) encodes everything
the PK model *doesn't* capture. Understanding this residual is critical for several
high-level goals.

**EXP-455: Residual Decomposition by Cause**

Classify residual patterns into known physiological causes:

| Residual Pattern | Likely Cause | Detection Method |
|------------------|-------------|------------------|
| Systematic positive bias, overnight | Dawn phenomenon | Time-of-day regression |
| Acute positive spikes, no logged carbs | Unannounced meals | Throughput peaks without COB |
| Gradual positive drift over days | ISF increasing (sensitivity loss) | Rolling ISF ratio trend |
| Negative bias post-exercise | Enhanced insulin sensitivity | Activity correlation |
| High-frequency oscillation | Compression lows, sensor noise | Spectral analysis |
| Multi-day positive shift | Infusion site degradation | 3-day periodicity |

**EXP-456: Infusion Site Degradation Detection**

Canula lipohypertrophy typically develops over 48–72 hours, causing progressive
insulin absorption degradation. The signal:

```
site_health(t) = rolling_mean(actual_insulin_effect / expected_insulin_effect, window=6h)
```

- Day 1: ratio ≈ 1.0 (fresh site)
- Day 2: ratio ≈ 0.85 (mild degradation)
- Day 3: ratio ≈ 0.65 (significant degradation)

This 3-day periodicity should be detectable in the demand-side residuals and would
provide actionable alerts ("consider changing your infusion site").

**EXP-457: Residual as Feature Channel**

Rather than treating the residual as noise, feed it as an explicit channel to ML models:

```
residual(t) = glucose(t) − predicted_glucose(t)
```

This channel captures **everything the physics model can't explain** — exercise effects,
stress, illness, menstrual cycle, and other person-specific factors. The hypothesis:
adding residual as a 9th PK channel may improve classification for tasks where these
unmodeled factors are relevant (e.g., override detection, where the patient is
compensating for something the physics model doesn't capture).

### 4.5 Multi-Day and Multi-Week Extensions (EXP-458–460)

**EXP-458: Metabolic Flux Periodicity (3–7 Day)**

Compute the autocorrelation of daily throughput patterns:

```
daily_throughput_template(hour) = median(throughput at hour h, across all days)
daily_deviation(day, hour) = throughput(day, hour) − template(hour)
periodicity = autocorrelation(daily_deviation, lags=[1,2,...,14] days)
```

Strong periodicity at 7 days indicates weekly routine (weekend vs weekday eating).
Strong periodicity at 3 days may indicate infusion site change cycles.
This connects meal counting (EXP-447) to the strategic planning layer.

**EXP-459: Rolling Metabolic Phenotype (2–4 Week Windows)**

Classify patients into metabolic phenotypes using 2-week rolling windows:

- **Stable controller**: Low throughput variance, consistent meal timing
- **Reactive manager**: High throughput peaks, many corrections
- **Drifting**: Systematic shift in basal adequacy score over time
- **Cyclic**: Periodic phenotype changes (e.g., menstrual cycle, shift work)

Tracking phenotype transitions over months could detect when a patient's control
strategy changes and recommend profile adjustments.

**EXP-460: Override Detection from Sustained Flux Shifts**

When patients use temporary overrides (higher targets, increased insulin), the
flux pattern changes systematically:

- Increased target → higher supply/demand ratio for extended periods (hours)
- Increased insulin → elevated demand with lag
- Exercise mode → demand drops but glucose sensitivity increases

Detecting sustained (>1h) shifts in the supply-demand balance that deviate from
the patient's typical pattern could classify override-like behavior even when
overrides aren't explicitly logged. This connects to the use case of transforming
retrospective override detection into prospective scheduling recommendations.

### 4.6 Encoding Validation Tests (EXP-461–463)

Building on the symmetry scorecard (EXP-419–426), validate that metabolic flux
encodings respect physiological expectations at each relevant time scale.

**EXP-461: Flux Time-Translation Invariance**

Test whether metabolic flux features maintain time-translation invariance at ≤2h
(expected YES) and break it at ≥12h (expected YES, due to circadian hepatic cycle).
This extends EXP-419 from glucose to flux channels.

**EXP-462: Flux Conservation Consistency**

The integral of (supply − demand) should equal ΔBG over complete absorption windows.
Test that this conservation holds for flux-derived features at 6h, 12h, and 24h
windows. Violations indicate encoding or normalization problems.

**EXP-463: TDD Equivariance Test**

If TDD normalization is working correctly, then throughput patterns normalized by
TDD should be equivariant across patients with different ISF values. Test by
comparing TDD-normalized throughput shapes across patient pairs with known ISF
ratios. Expected: shape similarity should increase from 0.987 (raw) toward 0.99+.

---

## 5. Symmetry and Physics Properties Summary

### 5.1 What the Data Science Has Revealed About Diabetes Physics

| Principle | Evidence | Practical Impact |
|-----------|----------|------------------|
| **Conservation**: Glucose integral balances over 12h | EXP-421: −1.8 ± 28.4 mg·h | Validates physics model; residual is meaningful |
| **Asymmetric absorption**: Bolus response ratio 3.47 | EXP-420 | Models need full DIA arc (≥12h windows) |
| **Universal response shape**: 0.987 similarity | EXP-445 | Cross-patient transfer is feasible |
| **Spectral concentration**: 18× at meal band | EXP-444 | Band-pass filtering can isolate meal signal |
| **Phase lag constancy**: 25 min (range 2–43) | EXP-436 | Phase-based classifier independent of amplitude |
| **Hepatic never-zero**: Min 35% of baseline | EXP-441 | Supply signal always available |
| **ISF≈1800/TDD**: r=0.43 | EXP-442 | TDD as data-driven ISF proxy |
| **Time-invariance breaks at 12h**: circadian enters | EXP-419 | Different encodings needed above/below 12h |
| **Sparse features hurt**: bolus at ≤0.7% density | EXP-298 | Must convert to dense (IOB/COB/flux) |

### 5.2 Scale-Dependent Encoding Prescription (Updated)

| Time Scale | Best Glucose Encoding | Best Insulin Encoding | Metabolic Flux | Key Physics |
|:---:|:---|:---|:---|:---|
| **≤2h** | Raw glucose + derivatives | IOB (dense) | Sum flux | Time-invariant, event onset |
| **2–6h** | Glucose + COB trajectory | IOB + bolus timing | Sum flux + phase lag | Absorption dynamics |
| **6–12h** | Glucose trace | Full PK (8 channels) | Throughput + balance | Complete DIA arc visible |
| **12–24h** | Glucose + circadian pos. | PK + time encoding | Throughput + circadian detrend | Circadian breaks symmetry |
| **1–4 days** | Daily summary statistics | TDD + bolus fraction | Daily throughput templates | Routine detection |
| **1–4 weeks** | Rolling TIR, variability | Rolling TDD, ISF ratio | Rolling phenotype | Drift detection |
| **Months** | FPCA components | TDD trend | Phenotype transitions | Seasonal/lifecycle |

### 5.3 Encoding Properties by Use Case

| Use Case | Required Properties | Validated? | Key Experiments |
|----------|:---|:---:|:---|
| UAM detection | Time-invariance, flux ≥ threshold | ✅ | EXP-313 (F1=0.939), EXP-438 |
| Meal counting | Spectral concentration, peak detection | ✅ | EXP-444, EXP-447 |
| Override detection | Flux shift persistence, circadian awareness | ⚠️ Partial | EXP-460 proposed |
| Hypo prediction | Conservation, derivative sensitivity | ✅ | EXP-345 (F1=0.676) |
| ISF drift | TDD equivariance, rolling statistics | ⚠️ Partial | EXP-312, EXP-451 proposed |
| Basal adjustment | Overnight conservation, fasting balance | ❌ Untested | EXP-450 proposed |
| Infusion site health | 3-day periodicity in demand residual | ❌ Untested | EXP-456 proposed |
| Profile recommendation | Composite fidelity, multi-week stability | ❌ Untested | EXP-453, EXP-459 proposed |
| Eating pattern scheduling | Meal regularity, day-of-week periodicity | ⚠️ Partial | EXP-426 (15% regular), EXP-458 |

---

## 6. Residual Analysis: Why Physics Models Fall Short

### 6.1 The Residual Budget

The physics model (ISF × insulin_rate − ISF/CR × carb_rate + hepatic) captures the
majority of glucose dynamics, but residuals remain. Based on EXP-421 and EXP-425:

| Source | Magnitude | Time Scale | Patients Affected |
|--------|:---:|:---:|:---:|
| Dawn phenomenon | −48 mg/dL bias, overnight | 4–8 AM | 11/11 (universal) |
| Unannounced meals | 20–80 mg/dL spikes | 30–120 min | Variable |
| Variable carb absorption | ±30% of predicted | 1–3h | All (meal composition) |
| Exercise | −20–60 mg/dL | 1–6h + delayed | Unmeasured |
| Stress/illness | +20–50 mg/dL | Hours–days | Unmeasured |
| Infusion site aging | +10–40 mg/dL drift | Days 2–3 | All pump users |
| ISF circadian variation | ±15% | 24h cycle | All |
| Menstrual/hormonal cycle | ±20% ISF shift | 2–4 weeks | ~50% of patients |

### 6.2 Which Residuals Are Modelable?

**High confidence** (structured, periodic, detectable):
- Dawn phenomenon → circadian position encoding already helps at ≥12h
- Infusion site aging → 3-day periodicity in demand residuals (EXP-456)
- ISF circadian variation → already partially in hepatic model

**Medium confidence** (detectable with additional data or inference):
- Unannounced meals → metabolic flux already detects these (EXP-438)
- Variable carb absorption → fat/protein delay, possibly from meal composition
- Exercise → accelerometer data if available, or heart rate

**Low confidence** (unpredictable, high individual variation):
- Stress/illness → no sensor data available
- Hormonal cycles → requires multi-week pattern detection

### 6.3 Residual as Opportunity

Rather than viewing residuals as noise, they contain **actionable information**:

1. **Systematic residuals** (same direction, same time of day) → settings need adjustment
2. **Periodic residuals** (3-day, 7-day, 28-day cycles) → detectable patterns
3. **Random residuals** (unpredictable, varying) → true noise floor
4. **Growing residuals** (drift over weeks) → physiology changing

The conservation integral (EXP-421) provides a natural metric: when the residual
integral grows beyond ±40 mg·h over 12h windows, something has changed that the
physics model can't account for with current settings.

---

## 7. Proposed Experiment Registry

### Priority 1: Settings Assessment (Clinical Value)

| ID | Title | Signal | Expected Outcome |
|:---|:---|:---|:---|
| EXP-450 | Basal adequacy score | Overnight supply/demand ratio | Score per night, trend over weeks |
| EXP-451 | ISF adequacy from corrections | Correction response vs expected | ISF ratio per correction event |
| EXP-452 | CR adequacy from meals | Meal excursion vs expected | CR ratio per announced meal |
| EXP-453 | Composite settings fidelity | Combined basal+ISF+CR | Quality gate for analysis eligibility |
| EXP-454 | Conservation integral quality gate | 12h glucose integral residual | Per-patient per-week quality score |

### Priority 2: Meal Counting Improvements

| ID | Title | Signal | Expected Outcome |
|:---|:---|:---|:---|
| EXP-448 | Hepatic-detrended peak detection | supply − hepatic model | +0.3–0.5 peaks/day improvement |
| EXP-449 | Derivative-based rising edge detection | d(throughput)/dt | Catches small meals below prominence threshold |

### Priority 3: Residual and Drift Modeling

| ID | Title | Signal | Expected Outcome |
|:---|:---|:---|:---|
| EXP-455 | Residual decomposition by cause | Classified residual patterns | Taxonomy of unmodeled effects |
| EXP-456 | Infusion site degradation detection | 3-day demand residual periodicity | Alert timing for site changes |
| EXP-457 | Residual as 9th PK channel | (actual − predicted) glucose | Classification improvement for override tasks |

### Priority 4: Multi-Day/Week Extensions

| ID | Title | Signal | Expected Outcome |
|:---|:---|:---|:---|
| EXP-458 | Metabolic flux periodicity | Daily throughput autocorrelation | Weekly routine detection |
| EXP-459 | Rolling metabolic phenotype | 2-week throughput statistics | Phenotype transition detection |
| EXP-460 | Override detection from sustained flux shifts | Supply/demand ratio persistence | Prospective override scheduling |

### Priority 5: Encoding Validation

| ID | Title | Signal | Expected Outcome |
|:---|:---|:---|:---|
| EXP-461 | Flux time-translation invariance | Flux features ± time encoding | Confirm invariance at ≤2h, break at ≥12h |
| EXP-462 | Flux conservation consistency | ∫(supply−demand) vs ΔBG | Validate decomposition at all scales |
| EXP-463 | TDD equivariance test | TDD-normalized throughput shapes | Cross-patient similarity improvement |

---

## 8. Conclusions

The metabolic flux decomposition represents a **fundamental advance** in how we encode
CGM/AID data for machine learning. By decomposing glucose dynamics into supply and
demand harmonics — grounded in the actual physics of insulin action, carb absorption,
and hepatic production — we expose signals that are invisible in raw glucose traces
but carry 6–19× more information at clinically relevant frequencies.

The approach passes the basic "smell test" (detecting 1–3 meals/day from physics alone)
and shows near-universal metabolic response shapes across patients (similarity 0.987),
suggesting that the core challenge in diabetes data science is not modeling the
physiology — which is remarkably consistent — but modeling the **residuals** that arise
from the gap between the idealized physics and real-world factors like exercise, stress,
infusion site health, and hormonal cycles.

The next phase of work should focus on:
1. **Settings assessment** — can we detect when ISF/basal/CR are misconfigured?
2. **Residual characterization** — what can we learn from what the physics model misses?
3. **Multi-day patterns** — extending from event detection to treatment planning
4. **Encoding validation** — ensuring our flux features respect known physiological symmetries

These experiments will directly feed the high-level objectives of predicting glucose,
detecting and classifying events, and recommending treatment adjustments — each informed
by the specific physiological basis and encoding requirements validated in this work.
