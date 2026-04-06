# Use-Case Alignment Guide

> **The Prescription Document**: Given a use case, look up exactly what you need.
>
> Generated from 398+ experiments (EXP-001 through EXP-408+) across 11 patients.
> Every claim references a specific experiment. No theoretical reasoning — empirical evidence only.

---

## Part 1: Executive Summary

This workspace has executed **398+ controlled experiments** across 11 patients with ~85 days of CGM/AID data each. The central, non-obvious finding:

**What appears to be ONE problem ("predict glucose") is actually 37 distinct sub-use-cases**, each requiring a *different* combination of:

- Time scale and history window
- Feature channels and encoding
- Architecture and learning technique
- Normalization and post-processing
- Validation metrics and methodology

This document is a **prescription guide**. For any sub-use-case, look up its entry to find the empirically optimal configuration — not a suggestion, but the result of systematic experimentation.

The key insight driving this structure: *different events and horizons require different data, history amounts, encodings and representations/feature sets, and different architectures and learning techniques, as well as different validation techniques in a much more fine-grained way than many people realize.*

A 2-hour UAM detector needs 1D-CNN with B-spline smoothing and **no time features**. A 12-hour override predictor needs a Transformer with carbs as the #1 feature and time features restored. Using the wrong recipe degrades performance by 10–30%. This document eliminates that guesswork.

---

## Part 2: The Physiological Time Scales

Every sub-use-case maps to a physiological driver. The biology dictates the time scale, which dictates the engineering.

| Time Scale | Physiological Driver | Duration | Key Physics |
|------------|---------------------|----------|-------------|
| **Momentum** | Glucose rate of change, CGM sensor lag | 5–30 min | dG/dt, CGM smoothing delay (~10 min) |
| **Absorption** | Insulin subcutaneous→plasma, carb gut→blood | 30–120 min | Isc1→Isc2→Ip (UVA/Padova), Qsto→Qgut→Ra |
| **DIA Completion** | Full insulin action curve, DIA ≈ 5–6h | 2–6h | The "DIA Valley" — partial action curves are ambiguous |
| **Circadian** | Dawn phenomenon, cortisol cycle, meal timing | 12–24h | 71.3 ± 18.7 mg/dL amplitude (EXP-126), 100% of patients |
| **Strategic** | Multi-day routine, metabolic load accumulation | 6h–4 days | **NEW**: The "treatment planning" horizon — event likelihoods, not point forecasts |
| **Lifestyle** | Weekly routines, exercise, work schedules | 3–7 days | U-shaped curve: 7d Sil = -0.301 (best window, EXP-289) |
| **Drift** | ISF changes, menstrual cycle, seasonal | Weeks–months | 9/11 patients show significant ISF drift at biweekly scale (EXP-194) |
| **Seasonal** | Temperature, activity level, illness frequency | Months | NOT TESTED — data insufficient (~85 days/patient) |

**Why this matters**: Choosing a 4-hour history window for a task governed by circadian physiology is a category error. The biology doesn't fit. The DIA Valley section below shows how dramatic the consequences are.

**The Strategic Scale** is a newly identified layer between Circadian (AID handles automatically) and Lifestyle (endocrinologist handles quarterly). It requires a fundamentally different output: calibrated event probabilities that patients can act on when attention is available, not real-time control signals. See Category E (Strategic Plan) for the 6 sub-use-cases that populate this scale.

---

## Part 3: The DIA Valley Phenomenon

One of the most important discoveries in this workspace. Duration of Insulin Action (DIA) is typically 5–6 hours. When your history window captures *part* of an insulin action curve but not its resolution, the model sees ambiguous, overlapping signals.

**The U-shaped curve** (EXP-289, pattern retrieval Silhouette scores):

| History Window | Sil Score | Why |
|----------------|-----------|-----|
| 2h | -0.424 | See onset only → clear but limited signal |
| 4h | -0.524 | See onset + peak but NOT resolution → ambiguous |
| **8h** | **-0.642** | **WORST** — overlapping incomplete insulin action curves |
| 12h | -0.472 | See complete rise→peak→resolution → improves |
| **7d** | **-0.301** | **BEST** — multiple complete DIA cycles, weekly patterns emerge |

The 8-hour window is maximally confusing: it captures enough of 2–3 overlapping insulin curves to create interference, but never sees any single curve resolve. This is not a modeling failure — it is a *physics* failure. The data is genuinely ambiguous at that scale.

**Implications**:
- For classification: use **2h** (pre-DIA, clean signal) or **≥12h** (post-DIA, complete cycles)
- For forecasting: include **future PK projection** to resolve the ambiguity explicitly (EXP-356)
- Avoid 4–8h windows for tasks that depend on insulin dynamics unless using PK encoding

### History Window × PK Interaction (EXP-353)

The DIA Valley applies differently depending on feature encoding. **PK channels resolve the valley**:

| History | Baseline MAE | PK MAE | PK Δ | Interpretation |
|---------|-------------|--------|------|----------------|
| 1h | 31.3 | 32.8 | +1.5 | PK is noise — too little history for DIA curves |
| 2h | 32.5 | 32.9 | +0.4 | Near-neutral — DIA curve barely begins |
| 4h | 35.7 | 34.9 | **-0.9** | **Crossover** — PK starts resolving partial DIA |
| 6h | 43.5 | 36.1 | **-7.4** | **Maximum PK benefit** — baseline collapses, PK stabilizes |
| 12h | 45.4 | 43.0 | -2.4 | Both degrade, PK still helps |

**Key insight**: Without PK, the model with raw sparse bolus/carb events *catastrophically degrades* at 6h+ history (h30 MAE: 20.5→38.9). PK encoding converts the DIA Valley from a performance cliff into a plateau. This means **longer history windows (3–6h) are viable and potentially superior when paired with PK encoding and appropriate architecture** (EXP-353).

**Critical gap**: The champion architecture (PKGroupedEncoder Transformer, EXP-408) has only been tested with **2h history** (window_size=48 = 24 history + 24 future). The architecture most suited to benefit from longer history + PK (positional grouping + attention) has never been tested at 4–6h lookback. EXP-372/376 showed monotonic improvement from 6h→12h with overlapping windows (MAE: 26.8→27.5), suggesting longer history could close the gap to CGM-grade at all horizons.

---

## Part 4: Complete Sub-Use-Case Registry

### A: PREDICT GLUCOSE

---

#### A1: Short-Term Trend/Alert (≤30 min)

**Physiological Basis**: Glucose momentum — rate of change (dG/dt) dominates at this horizon. CGM sensor lag (~10 min) means current readings already encode recent history.

**Optimal Configuration**:

| Dimension | Specification | Evidence |
|-----------|---------------|----------|
| Scale | ≤30 min @ 5-min steps | EXP-408 |
| History window | 24 steps (2h) | EXP-408 |
| Features | 8ch baseline + PK channels | EXP-408 |
| Encoding | BG/400, ISF-normalized | EXP-407 |
| Architecture | PKGroupedEncoder Transformer | EXP-408 |
| Normalization | BG/400 + ISF normalization | EXP-407 |
| Post-processing | 5-seed ensemble, conformal bands | EXP-137 |
| Validation | MAE + MARD + Clarke zones | EXP-408 |

**Current Best Result**: MAE = 13.50 mg/dL, MARD ≈ 8.7% (EXP-408)
**Status**: ✅ Production (but improvement likely available)
**Key Finding**: Glucose-only carries 87% of transformer attention (EXP-162). **Untested opportunity**: EXP-408 uses only 2h history. EXP-353 showed PK channels stabilize MAE at 6h history (Δ=-7.4), and PKGroupedEncoder has never been tested at 4–6h lookback.

---

#### A2: Medium-Term Dosing Support (60 min)

**Physiological Basis**: Absorption physics — insulin subcutaneous kinetics (Isc1→Isc2→Ip) and carb absorption (Qsto→Qgut→Ra) become the dominant signals. Dosing decisions require resolving active insulin and carbs.

**Optimal Configuration**:

| Dimension | Specification | Evidence |
|-----------|---------------|----------|
| Scale | 60 min @ 5-min | EXP-409 (in progress) |
| History window | 24 steps (2h) + future PK | EXP-356 |
| Features | 8ch + PK history + future PK projection | EXP-356 |
| Encoding | PK curve encoding for bolus/carb→continuous | EXP-353 |
| Architecture | Transformer + PKGroupedEncoder | EXP-408 |
| Normalization | ISF-normalized BG | EXP-407 |
| Post-processing | Per-patient fine-tuning, conformal | EXP-408 |
| Validation | MAE + MARD per horizon + Clarke zones | EXP-408 |

**Current Best Result**: MAE = 13.50 (multi-horizon), h60 specialist (EXP-409) in progress
**Status**: 🟡 Research (h60 specialist optimization ongoing)
**Key Finding**: Future PK projection reduces h120 error by -10.0 mg/dL (EXP-356); benefit scales with horizon.

---

#### A3: Long-Term Meal Planning (90–120 min)

**Physiological Basis**: Full absorption cycle plus counterregulatory hormone response. At 90–120 min, the liver's glycogenolysis response to falling glucose and the tail of carb absorption both matter.

**Optimal Configuration**:

| Dimension | Specification | Evidence |
|-----------|---------------|----------|
| Scale | 90–120 min @ 5-min | EXP-406 |
| History window | 24 steps (2h) + extended PK | EXP-406 |
| Features | 8ch + future PK projection (critical) | EXP-406 |
| Encoding | PK curve encoding | EXP-356 |
| Architecture | Multi-horizon encoder Transformer | EXP-408 |
| Normalization | ISF-normalized BG | EXP-407 |
| Post-processing | 5-seed ensemble, conformal prediction | EXP-137 |
| Validation | MAE + MARD + per-horizon breakdown | EXP-408 |

**Current Best Result**: MAE = 13.50 multi-horizon; future PK gives -0.66 MAE per horizon step (EXP-406)
**Status**: 🟡 Research
**Key Finding**: Every additional horizon step benefits -0.66 MAE from future PK projection (EXP-406). This is the horizon where PK encoding transitions from "nice to have" to "essential."

---

#### A4: Overnight Basal Adequacy (6–8h)

**Physiological Basis**: Circadian hormones (cortisol, growth hormone) drive dawn phenomenon. Basal rate adequacy is the dominant variable overnight — no meals, minimal boluses.

**Optimal Configuration**:

| Dimension | Specification | Evidence |
|-----------|---------------|----------|
| Scale | 6–8h overnight window | EXP-134 |
| History window | Extended (pre-sleep context) | EXP-134 |
| Features | glucose, IOB, basal_rate, time_sin/cos | EXP-134 |
| Encoding | BG/400 | EXP-134 |
| Architecture | Night-specialist model | EXP-134 |
| Normalization | Per-patient baseline | EXP-134 |
| Post-processing | Conformal bands for safety | EXP-137 |
| Validation | MAE + overnight-specific metrics | EXP-134 |

**Current Best Result**: MAE = 16.0 mg/dL (EXP-134)
**Status**: 🟡 Research
**Key Finding**: Overnight is simpler (no meals) but circadian effects create systematic bias without time features — one of the few cases where time_sin/cos helps.

---

#### A5: Multi-Day Trends (>24h)

**Physiological Basis**: Lifestyle patterns, weekly exercise schedules, ISF drift, and cumulative effects of insulin sensitivity changes require multi-day context.

**Optimal Configuration**: NOT TESTED

**Current Best Result**: None — major gap
**Status**: ❌ Gap
**Key Finding**: The DIA Valley data (Part 3) suggests 7-day windows have the best signal (Sil = -0.301, EXP-289), but no forecasting experiments have been run at this scale. Requires STL decomposition or multi-rate encoding.

---

#### A6: Conformal Prediction / Alert Calibration

**Physiological Basis**: Not a physiological task per se — this is a *statistical wrapper* that converts point predictions into calibrated prediction intervals for clinical safety.

**Optimal Configuration**:

| Dimension | Specification | Evidence |
|-----------|---------------|----------|
| Scale | Any (wraps other forecasters) | EXP-137 |
| Method | Split conformal prediction | EXP-137 |
| Coverage target | 90% | EXP-137 |
| Architecture | Applied on top of base forecaster | EXP-137 |
| Validation | Coverage %, Clarke A+B zone % | EXP-137 |

**Current Best Result**: Coverage 90%, Clarke A+B 97.1% (EXP-137)
**Status**: ✅ Production
**Key Finding**: Conformal prediction provides distribution-free coverage guarantees regardless of the base model's assumptions.

---

### B: DETECT/CLASSIFY EVENTS

---

#### B1: Unannounced Meal (UAM) Detection

**Physiological Basis**: Carb absorption produces a characteristic glucose rise (Ra from gut) without preceding bolus insulin. The dG/dt signature is distinct from insulin-driven drops.

**Optimal Configuration**:

| Dimension | Specification | Evidence |
|-----------|---------------|----------|
| Scale | 2h @ 5-min (24 steps) | EXP-337 |
| History window | 24 steps | EXP-337 |
| Features | no_time_6ch (glucose, IOB, COB, bolus, carbs, basal) | EXP-349 |
| Encoding | B-spline smoothing + analytic derivatives | EXP-331, EXP-337 |
| Architecture | 1D-CNN (3-layer 32→64→64) | EXP-337 |
| Normalization | BG/400 | EXP-337 |
| Post-processing | B-spline smoothing | EXP-331 |
| Validation | F1 + bootstrap 95% CI, multi-seed | EXP-337 |

**Current Best Result**: F1 = 0.939 [0.928–0.949] (EXP-337), or F1 = 0.971 without time features (EXP-349)
**Status**: ✅ Production
**Key Finding**: Removing time features *improves* UAM by +0.9% (EXP-349) — UAM is time-translation invariant. B-spline derivatives provide +15% SNR (EXP-331).

---

#### B2: Hypoglycemia Prediction

**Physiological Basis**: Glucose dropping below 70 mg/dL triggers counterregulatory hormones (glucagon, epinephrine). Prediction requires detecting the descent trajectory early — the rate of fall, active IOB, and recent bolus timing are critical.

**Optimal Configuration**:

| Dimension | Specification | Evidence |
|-----------|---------------|----------|
| Scale | 2h @ 5-min | EXP-345 |
| History window | 24 steps | EXP-345 |
| Features | Baseline channels + functional depth feature | EXP-335, EXP-345 |
| Encoding | BG/400 + functional depth scoring | EXP-335 |
| Architecture | Multi-task 1D-CNN + Platt calibration | EXP-345 |
| Normalization | BG/400 | EXP-345 |
| Post-processing | Platt calibration (ECE 0.114→0.016) | EXP-345 |
| Validation | F1 + AUC-ROC + ECE + enrichment ratio | EXP-345 |

**Current Best Result**: F1 = 0.676, AUC = 0.955 (EXP-345); functional depth feature provides 112× hypo enrichment (EXP-335)
**Status**: 🟡 Research (F1 target: 0.80)
**Key Finding**: The functional depth feature (EXP-335) is a breakthrough — it scores how "atypical" a glucose trajectory is relative to the patient's distribution, yielding 112× enrichment for hypo events. Platt calibration is essential for practical thresholds.

---

#### B3: Meal Detection

**Physiological Basis**: Carbohydrate ingestion triggers gut absorption (Qsto→Qgut→Ra) producing glucose rise 15–30 min post-meal. Detection requires distinguishing meal-driven rises from other causes (dawn phenomenon, rebound highs, compression artifacts).

**Optimal Configuration**:

| Dimension | Specification | Evidence |
|-----------|---------------|----------|
| Scale | 12h @ 5-min | EXP-049, EXP-221 |
| History window | Extended (captures meal context) | EXP-221 |
| Features | carbs_total is #1 feature | EXP-221 |
| Encoding | BG/400 | EXP-221 |
| Architecture | Transformer (12h needs capacity) | EXP-221 |
| Normalization | BG/400 | EXP-221 |
| Post-processing | Platt calibration | EXP-221 |
| Validation | Per-class F1, macro F1 | EXP-049, EXP-221 |

**Current Best Result**: F1 = 0.565 (EXP-049/221)
**Status**: 🟡 Research (hardest classification task)
**Key Finding**: Meal detection is the hardest event class because meals are irregular, variable in size, and their glucose signature overlaps with many other events. carbs_total is the single most predictive feature at 12h (EXP-221).

---

#### B4: Override WHEN Prediction

**Physiological Basis**: AID system overrides (temporary targets, activity modes) are triggered by anticipated or detected physiological changes — upcoming exercise, persistent highs, or meal preloading. The pattern is a human anticipating a state change.

**Optimal Configuration**:

| Dimension | Specification | Evidence |
|-----------|---------------|----------|
| Scale (production) | 2h @ 5-min | EXP-343 |
| Scale (research) | 6h (F1=0.715), 12h (F1=0.610) | EXP-287, EXP-298 |
| History window | 24 steps (2h) | EXP-343 |
| Features | kitchen_sink_10ch (2h), baseline_plus_fda_10ch (6h+) | EXP-343, EXP-287 |
| Encoding | BG/400, B-spline at 2h only | EXP-331, EXP-343 |
| Architecture | 1D-CNN (2h), Transformer (6h+) | EXP-343 |
| Normalization | BG/400 | EXP-343 |
| Post-processing | Platt calibration (ECE 0.084→0.046) | EXP-343 |
| Validation | F1 + utility (F1=0.993) + ECE | EXP-227, EXP-343 |

**Current Best Result**: F1 = 0.882 at 2h (EXP-343), utility F1 = 0.993 (EXP-227)
**Status**: ✅ Production (2h), 🟡 Research (6h, 12h)
**Key Finding**: Override prediction at 2h achieves 0.993 utility F1 (EXP-227). Scaling to 6h/12h degrades due to the DIA Valley and increased feature sensitivity (3.4× higher at 12h, EXP-287/298).

---

#### B5: Prolonged High Detection

**Physiological Basis**: Sustained hyperglycemia (>180 mg/dL for >2h) indicates basal inadequacy, missed bolus, or insulin resistance episode.

**Optimal Configuration**: Implicit in override detection — not standalone.
**Current Best Result**: Subsumed by B4 override detection
**Status**: 🟡 Research (no dedicated model)
**Key Finding**: Prolonged high is an exception to B-spline smoothing hurting at 6h — it shows +2.6% improvement, likely because the sustained nature of the signal benefits from smoothing.

---

#### B6: Exercise Detection

**Physiological Basis**: Exercise increases insulin-independent glucose uptake (GLUT4 translocation) and insulin sensitivity for 24–48h. The glucose signature is a rapid drop during activity with potential rebound hours later.

**Optimal Configuration**:

| Dimension | Specification | Evidence |
|-----------|---------------|----------|
| Scale | 2h @ 5-min | EXP-221 |
| Features | Baseline channels | EXP-221 |
| Architecture | 1D-CNN | EXP-221 |
| Validation | F1 | EXP-221 |

**Current Best Result**: F1 = 0.736 (EXP-221)
**Status**: 🟡 Research
**Key Finding**: Exercise accounts for >80% of overrides (EXP-221). A dedicated exercise detector would likely improve override prediction significantly.

---

#### B7: Infusion Set Failure Detection

**Physiological Basis**: Insulin pump infusion sets degrade over 2–3 days — kinking, occlusion, or tissue lipohypertrophy cause progressive insulin delivery failure, producing unexplained persistent hyperglycemia.

**Status**: ❌ Gap — NOT TESTED
**Key Finding**: Would require modeling the *absence* of expected insulin effect — a counterfactual reasoning problem.

---

#### B8: Compression Low / Sensor Artifact Detection

**Physiological Basis**: Pressure on the CGM sensor (sleeping on it) produces false low readings. The pattern is a sharp drop to abnormally low values followed by rapid recovery — physiologically impossible glucose kinetics.

**Status**: ❌ Gap — NOT TESTED
**Key Finding**: The dG/dt signature of compression lows is likely distinctive (rate of fall faster than physiologically possible). B-spline derivatives (EXP-331) could potentially identify these.

---

#### B9: Insulin Stacking Detection

**Physiological Basis**: Multiple boluses within one DIA window create overlapping insulin action curves that can produce delayed, severe hypoglycemia.

**Status**: 🟡 Research (implicit)
**Key Finding**: Implicit in IOB feature — IOB already represents stacked insulin. A dedicated detector is not needed if IOB is accurately computed.

---

#### B10: Rebound High Post-Hypoglycemia

**Physiological Basis**: Counterregulatory hormones (glucagon, epinephrine, cortisol) released during hypoglycemia cause hepatic glucose output that overshoots, producing hyperglycemia 1–3h after the hypo event.

**Status**: ❌ Gap — NOT TESTED
**Key Finding**: The physiological mechanism is well-understood but no experiments have isolated this pattern. The hypo detector (B2) could be extended with a post-hypo phase.

---

### C: RECOMMEND/PLAN

---

#### C1: Override Timing (WHEN to Override)

**Physiological Basis**: Same as B4 but framed as recommendation — the model recommends initiating an override based on detected physiological state and predicted trajectory.

**Optimal Configuration**: Same as B4 (2h production configuration)

**Current Best Result**: F1 = 0.993 utility (EXP-227)
**Status**: ✅ Production
**Key Finding**: WHEN is the solved part of override recommendation. Lead time data shows 73.8% of overrides have >30 min lead time (EXP-221), giving adequate warning.

---

#### C2: Override Type Selection (WHICH Override)

**Physiological Basis**: Different overrides target different physiology — exercise mode (increase target, reduce basal), eating soon (decrease target, increase basal), or custom targets.

**Status**: ❌ Gap — NOT STARTED
**Key Finding**: Blocked on counterfactual simulation. To recommend WHICH override, the model must predict *what would happen* under each option — requires a physics-based simulator, not just pattern matching.

---

#### C3: Override Magnitude (HOW MUCH)

**Physiological Basis**: The degree of override (target BG level, basal rate percentage) should match the expected physiological perturbation.

**Status**: ❌ Gap — NOT STARTED
**Key Finding**: Same blocker as C2 — requires counterfactual reasoning. The space of possible magnitudes is continuous, making this harder than classification.

---

#### C4: Bolus Advice / CR Adjustment

**Physiological Basis**: Carb ratio (CR = grams carb per unit insulin) varies by time of day, stress, activity, and menstrual cycle. Recommending adjusted CRs requires understanding the patient's current insulin sensitivity state.

**Status**: ❌ Gap (requires C2/C3 first)
**Key Finding**: Implicit in override recommendations. CR adjustment is a special case of "HOW MUCH" override.

---

#### C5: Pre-Bolus Timing Suggestion

**Physiological Basis**: Rapid-acting insulin takes ~15 min to begin acting, while carbs can raise BG in 10 min. Pre-bolusing (dosing before eating) allows insulin to "get ahead" of the meal.

**Optimal Configuration**: Partially characterized.
**Current Best Result**: Lead time data exists — 73.8% of overrides have >30 min lead (EXP-221)
**Status**: 🟡 Research (data exists, no optimization)
**Key Finding**: The lead time distribution is characterized but no experiment has optimized pre-bolus timing recommendations.

---

#### C6: Temporary Target Recommendation

**Physiological Basis**: Temporary BG targets adjust AID aggressiveness — lower targets increase insulin delivery, higher targets reduce it.

**Current Best Result**: Override types identified but not mapped to recommendations
**Status**: 🟡 Research
**Key Finding**: Types of temporary targets are enumerated in the data but the recommendation engine is blocked on C2.

---

### D: TRACK PHYSIOLOGICAL STATE

---

#### D1: ISF Drift Detection

**Physiological Basis**: Insulin Sensitivity Factor (ISF = mg/dL drop per unit insulin) changes over weeks due to weight changes, fitness, menstrual cycle, seasonal factors, and medication adjustments.

**Optimal Configuration**:

| Dimension | Specification | Evidence |
|-----------|---------------|----------|
| Scale | Biweekly rolling windows | EXP-194 |
| Features | ISF_effective (computed) | EXP-194 |
| Encoding | Per-patient z-score | EXP-308 |
| Architecture | Statistical tests (not ML) | EXP-194 |
| Normalization | Per-patient baseline | EXP-194 |
| Validation | Spearman r + p-value per patient | EXP-194 |

**Current Best Result**: r = -0.328, 9/11 patients show significant drift (EXP-194); two groups: sensitivity↑ vs resistance↑
**Status**: ✅ Production
**Key Finding**: ISF drift is real and clinically significant — 9/11 patients show measurable drift at biweekly resolution (EXP-194). Two distinct subpopulations emerge: patients becoming more sensitive and patients becoming more resistant.

---

#### D2: Pattern Retrieval / Similarity Search

**Physiological Basis**: Recurring physiological patterns (weekly exercise, weekend meals, work-day stress) produce similar glucose trajectories. Retrieving similar past episodes aids decision-making.

**Optimal Configuration**:

| Dimension | Specification | Evidence |
|-----------|---------------|----------|
| Scale | 7d @ 1-hour resolution | EXP-289, EXP-296 |
| History window | 168 steps (7d × 24h) | EXP-289 |
| Features | glucose + insulin + carbs | EXP-296 |
| Encoding | Transformer encoder embeddings | EXP-296 |
| Architecture | Transformer encoder + cosine similarity | EXP-296 |
| Normalization | Per-patient z-score | EXP-308 |
| Validation | Silhouette + R@5 + R@10 | EXP-289, EXP-296 |

**Current Best Result**: Sil = +0.326 (EXP-289/296)
**Status**: 🟡 Research
**Key Finding**: 7-day windows at 1-hour resolution produce the best pattern separation (Sil = -0.301 raw → +0.326 with learned embeddings, EXP-289/296). The DIA Valley makes shorter windows inferior.

---

#### D3: Circadian Profile Characterization

**Physiological Basis**: Cortisol peaks at 6–8 AM (dawn phenomenon), melatonin onset affects insulin sensitivity, and meal timing creates reliable daily glucose patterns.

**Optimal Configuration**:

| Dimension | Specification | Evidence |
|-----------|---------------|----------|
| Scale | 24h | EXP-126 |
| Features | glucose, time_sin/cos (essential here) | EXP-126 |
| Architecture | Statistical (amplitude/phase extraction) | EXP-126 |
| Validation | Amplitude ± SD across patients | EXP-126 |

**Current Best Result**: Amplitude = 71.3 ± 18.7 mg/dL, present in 100% of patients (EXP-126)
**Status**: ✅ Production
**Key Finding**: Circadian variation is universal (100% of patients) and large (71.3 mg/dL average swing). This is one of the few tasks where time_sin/cos features are essential.

---

#### D4: Illness Detection

**Physiological Basis**: Illness (infection, fever) triggers stress hormones that dramatically increase insulin resistance, producing unexplained persistent hyperglycemia.

**Status**: ❌ Gap — NOT TESTED
**Key Finding**: Requires external signals (self-reported symptoms, heart rate, temperature) not available in current CGM/AID data.

---

#### D5: Menstrual Cycle Effects

**Physiological Basis**: Progesterone and estrogen fluctuations across the ~28-day menstrual cycle affect insulin sensitivity, with the luteal phase (post-ovulation) typically increasing insulin resistance.

**Status**: ❌ Gap — NOT TESTED
**Key Finding**: Requires cycle phase labels not available in current data. The biweekly ISF drift (D1) may partially capture this signal but cannot attribute causation.

---

#### D6: Seasonal Trends

**Physiological Basis**: Temperature affects insulin absorption rate, activity levels vary seasonally, and vitamin D status affects insulin sensitivity.

**Status**: ❌ Gap — NOT TESTED
**Key Finding**: Requires >6 months of data per patient. Current dataset (~85 days) is insufficient. The biweekly drift detector (D1) would be the starting point for extension.

---

### E: STRATEGIC PLAN (Treatment Planning Layer)

> **The Missing Clinical Layer**: Real-time AID handles moment-to-moment (≤2h). Endocrinologists handle quarterly adjustments. **Nothing fills the 6h–4 day strategic gap** — where patients/caregivers can plan ahead when attention is available, then go "hands off" while still improving TIR. The output is **event likelihoods and state assessments**, not glucose point predictions.
>
> **Clinical value proposition**: Less effort, better results — strategic planning vs. constant monitoring.

---

#### E1: Overnight Risk Assessment (6–8h)

**Physiological Basis**: Overnight physiology is distinct: no meals, reduced cortisol (until dawn phenomenon ~3–5 AM), basal insulin dominance. Overnight glucose trajectory is highly predictable from evening state. Nocturnal hypoglycemia is the highest-risk event in diabetes management.

**Optimal Configuration**:

| Dimension | Specification | Evidence |
|-----------|---------------|----------|
| Scale | 6h evening context → 6h overnight prediction | EXP-126: night TIR=60.1% (worst period) |
| History window | 72 steps (6h @ 5min) | EXP-353: PK stabilizes at 6h |
| Features | glucose, IOB, COB, basal_rate, time_sin/cos, last_meal_hours_ago | EXP-162: IOB dominates overnight |
| Encoding | PK channels (IOB trajectory critical for basal adequacy) | EXP-353 |
| Architecture | 1D-CNN (proven at 2h, should extend to 6h with PK) | EXP-313 |
| Post-processing | Platt calibration (essential for probability output) | EXP-324: ECE 0.21→0.01 |
| Validation | AUC-ROC (rare event), ECE, per-patient F1 | — |

**Output**: P(hypo tonight), P(high overnight), expected overnight TIR
**Clinical Action**: "Set higher/lower temp target before bed" or "Have a snack — 40% hypo risk tonight"
**Data Feasibility**: ~85 nights per patient, ~935 pooled. **Sufficient for CNN.**
**Status**: ❌ Gap — DESIGNED (EXP-412), NOT YET RUN
**Key Finding**: Night TIR (60.1%) is the worst period (EXP-126). Dawn effect varies −76.7 to +28.2 mg/dL per patient. Volatile periods show 2.04× MAE (EXP-222). Time features ARE relevant here (circadian matters).

---

#### E2: Next-Day TIR Prediction (24h)

**Physiological Basis**: Day-to-day glucose control has strong autocorrelation — "bad days" cluster due to illness, stress, schedule disruption, or cumulative insulin resistance. Today's distributional features (not sequence details) predict tomorrow's outcome.

**Optimal Configuration**:

| Dimension | Specification | Evidence |
|-----------|---------------|----------|
| Scale | 24h context → 24h prediction | EXP-126: circadian amp=71.3 mg/dL |
| History window | 288 steps (24h @ 5min) or 96 steps (24h @ 15min) | — |
| Features | glucodensity (distributional), TIR per 6h block, event counts, IOB_mean, carb_total, day-of-week | EXP-330: glucodensity ΔSil=+0.508 |
| Encoding | Distributional (histograms), not sequential | EXP-330 |
| Architecture | XGBoost (tabular features, ~85 samples/patient) OR 1D-CNN on 15-min series | — |
| Validation | MAE on TIR regression, F1 on binary bad-day (TIR<60%) | — |

**Output**: Expected tomorrow TIR, P(bad day), likely problem periods (night/morning/afternoon/evening)
**Clinical Action**: "Tomorrow looks like a high-risk day (similar to last Tuesday). Consider proactive override."
**Data Feasibility**: ~85 days per patient, ~935 pooled. **Abundant for both XGBoost and CNN.**
**Status**: ❌ Gap — DESIGNED (EXP-413), NOT YET RUN
**Key Finding**: Circadian amplitude (71.3 mg/dL) is larger than forecast error (13.50 MAE), so time-of-day is already a dominant factor (EXP-126). Day-of-week should be explored (weekday vs weekend patterns).

---

#### E3: Multi-Day Control Quality Forecast (3–4 days)

**Physiological Basis**: 96-hour (4-day) windows capture the natural cycle of insulin sensitivity variation, medication adherence patterns, and meal routine stability. The U-shaped silhouette curve (EXP-289/301) shows 3–4 day windows should fall in the "recovery zone" between the 12h episode peak and the 7d weekly peak. A 4-day window = 8 consecutive 12-hour episodes, enabling hierarchical analysis.

**Optimal Configuration**:

| Dimension | Specification | Evidence |
|-----------|---------------|----------|
| Scale | 4-day context → 4-day prediction | EXP-194: 96h wavelet best drift correlation |
| History window | 1152 steps (4d @ 5min) or 96 steps (4d @ 1hr) | EXP-301: 7d Sil=-0.301 (best tested) |
| Features | Hierarchical: 8 × 12h episode features → sequence | EXP-350: 12h episode CNN proven |
| Encoding | Per-episode: glucodensity, TIR, event counts, IOB stats | EXP-330, EXP-335 |
| Architecture | Episode CNN embeddings → GRU/attention → classification head | EXP-377 (proposed) |
| Validation | Macro F1, ECE, LOSO (leave-one-subject-out) | EXP-326: LOO gap only 3-4% |

**Output**: Next 4-day control quality (Good/Moderate/Poor), P(declining control), recommended adjustment
**Clinical Action**: "Your control has been trending down for 3 days. Consider ISF adjustment." Or: "This week looks stable — no changes needed."
**Data Feasibility**: 21–42 windows per patient (non-overlapping/50% overlap), ~500–1000 pooled. **Borderline for deep learning** — use pooled training + LOSO validation. Classical ML (XGBoost) is safer.
**Status**: ❌ Gap — DESIGNED (EXP-414), NOT YET RUN
**Key Finding**: EXP-194 wavelet analysis at 8h windows showed strongest drift-TIR correlation (r=-0.328). 3-day CUSUM triggers earliest reliable change-point detection (EXP-325). Data is borderline but feasible with hierarchical approach (reuses proven episode embeddings, fewer parameters).

---

#### E4: Event Recurrence Prediction (6h–3d variable)

**Physiological Basis**: Glucose events cluster in time — a hypo at 3 PM today increases P(hypo at 3 PM tomorrow) due to persistent causes (activity pattern, basal rate mismatch, meal timing). Events are not independent; they recur with circadian and multi-day periodicity.

**Optimal Configuration**:

| Dimension | Specification | Evidence |
|-----------|---------------|----------|
| Scale | 7-day event history → 6h/24h/3d recurrence prediction | EXP-126: circadian clustering |
| History window | 28 time slots (7d × 4 blocks/day of 6h each) | — |
| Features | Hypo count, high count, override count per 6h slot, rolling 24h/3d TIR, day-of-week | EXP-312: biweekly rolling optimal |
| Encoding | Tabular (event counts per block) + temporal (1D sequence) | — |
| Architecture | XGBoost (tabular) + 1D-CNN (temporal) ensemble | — |
| Validation | AUC-ROC (rare events), precision-recall, ECE | — |

**Output**: P(hypo in next 6h/24h/3d), P(prolonged high), P(override needed)
**Clinical Action**: "You've had 3 hypos this week around 3 PM. Consider lowering afternoon basal."
**Data Feasibility**: ~78 7-day windows per patient with overlap. **Sufficient.**
**Status**: ❌ Gap — DESIGNED (EXP-415), NOT YET RUN
**Key Finding**: Not yet tested. Builds on proven event detection (B1, B2, B4) by adding temporal recurrence. The approach is tabular-first (low-dimensional summary statistics), not sequential deep learning.

---

#### E5: Weekly Routine Hotspot Identification (7 days)

**Physiological Basis**: Patients have weekly routines — work days vs. weekends, exercise schedules, social eating patterns. These create predictable glucose response patterns. Identifying the 2–3 worst 6-hour blocks in a patient's typical week enables targeted intervention with minimal effort.

**Optimal Configuration**:

| Dimension | Specification | Evidence |
|-----------|---------------|----------|
| Scale | 7-day @ 1-hour resolution (168 steps) | EXP-301: 7d Sil=-0.301 (best) |
| History window | 168 steps (7d @ 1hr) | EXP-289/301: 7d outperforms 12h |
| Features | Per-block TIR, event counts, variability (CV), IOB/carb means | EXP-126: time-of-day effect |
| Encoding | 28-slot grid (4 blocks/day × 7 days) | — |
| Architecture | Self-supervised ranking (no labels needed — rank by TIR/events) | — |
| Validation | Hotspot stability across weeks, simulated TIR improvement from intervention | — |

**Output**: Ranked list of weekly hotspots with risk profiles ("Sunday evenings: 3× hypo rate, lowest TIR")
**Clinical Action**: "Focus on these 2–3 time windows. Ignore the rest — your AID handles them well."
**Data Feasibility**: ~22–44 7-day windows per patient. **Sufficient for statistical analysis.** No deep learning needed — this is primarily descriptive analytics with temporal stability checks.
**Status**: ❌ Gap — DESIGNED (EXP-416), NOT YET RUN
**Key Finding**: EXP-301 showed 7d windows produce best embedding quality (Sil=-0.301). EXP-126 showed circadian amplitude of 71.3 mg/dL — the raw signal is large enough to detect routine-level patterns. This is the lowest-complexity, highest-impact treatment planning use case.

---

#### E6: Strategic Override Planning (Multi-day)

**Physiological Basis**: Override recommendations today (C1–C6) operate in real-time — "override NOW because of current glucose." Strategic planning operates on a longer horizon: "Based on this week's pattern, SCHEDULE these overrides." Moves from reactive to proactive management.

**Optimal Configuration**:

| Dimension | Specification | Evidence |
|-----------|---------------|----------|
| Scale | 7-day history → next 3–4 day override plan | EXP-227: TIR-impact utility=0.993 |
| Features | Combines E5 hotspots + E3 control quality + E4 event recurrence | — |
| Architecture | Rule-based layer on top of E3/E4/E5 predictions (no additional ML needed) | — |
| Validation | Simulated TIR improvement from applying planned overrides | — |

**Output**: "For this week, I recommend: (1) Sleep override every night at 10 PM, (2) Pre-dinner higher target on Tuesdays and Thursdays, (3) Reduce afternoon basal on weekends."
**Clinical Action**: Patient/caregiver sets up planned overrides for the week, then monitors passively.
**Data Feasibility**: Depends on E3, E4, E5 outputs. No additional data needed.
**Status**: ❌ Gap — CONCEPTUAL, depends on E3+E4+E5
**Key Finding**: This is the **capstone use case** that combines overnight risk (E1), daily prediction (E2), multi-day quality (E3), event recurrence (E4), and weekly hotspots (E5) into actionable weekly plans. It represents the "less effort, better results" vision.

---

#### E7: Proactive Meal Scheduling (UAM → Eating Soon Mode)

**Physiological Basis**: Meal timing is highly routine for most patients — breakfast, lunch, dinner occur within ±60 min windows on workdays. UAM detection (F1=0.971) identifies meals *after* they happen. If meals recur at predictable times, the system can proactively activate "eating soon" mode (higher temp target, reduced basal) *before* the meal, reducing postprandial spikes. Pre-bolus timing analysis (EXP-221) shows 73.8% of overrides have >30 min lead time — the biology supports proactive action.

**Optimal Configuration**:

| Dimension | Specification | Evidence |
|-----------|---------------|----------|
| Scale | 3-day UAM event history → next-day meal schedule | EXP-349: UAM F1=0.971, time-invariant |
| History window | 3 days of UAM event timestamps (not raw glucose) | EXP-126: circadian patterns 100% of patients |
| Features | Per-6h-block UAM count, mean meal time ± std, day-of-week, regularity score | EXP-349, EXP-126 |
| Encoding | Tabular (event summary statistics, not raw sequence) | — |
| Architecture | Heuristic first (if 3+ UAMs at similar time ±60min in 7 days → schedule), then XGBoost | — |
| Validation | Precision of meal timing prediction (within ±30 min), false schedule rate | — |

**Output**: "Based on the last 3 days, you typically eat around 12:30 PM ±20 min and 6:45 PM ±35 min. Scheduling eating-soon mode at 12:00 PM and 6:15 PM."
**Clinical Action**: Pre-activate higher temp target or reduced basal 30 min before predicted meal time. Patient confirms or dismisses.
**Data Feasibility**: ~85 days × ~3 meals/day = ~255 meal events per patient. **Abundant.** Regularity scoring needs only timestamps, not glucose traces.
**Status**: ❌ Gap — NOT YET DESIGNED
**Key Finding**: UAM detection is production-ready (F1=0.971). The **missing link** is temporal clustering of UAM events to discover meal schedules. Key question: what fraction of patients have regular enough meal timing for this to work? Circadian analysis (EXP-126) confirms 100% of patients have strong circadian glucose patterns (71.3 mg/dL amplitude), but meal regularity may vary. K-means clustering on {hour_of_day, day_of_week} of UAM events would quantify this directly.

**Symmetry Note**: Time-translation invariance (Principle 1) applies to *detecting* meals — a meal is a meal at any hour. But *scheduling* meals breaks this symmetry intentionally — we exploit the patient's routine to predict future events. This is the correct symmetry: invariant for detection, variant for scheduling.

---

#### E8: Acute Absorption Degradation Detection (Canula Aging / Sick / Resistance)

**Physiological Basis**: Insulin absorption degrades from multiple causes: (1) infusion site aging (canula lipohypertrophy, typically days 2-3), (2) illness (counter-regulatory hormones), (3) stress/bloating/hormonal shifts. All manifest as **effective ISF dropping** — same insulin dose produces less glucose reduction. The signature is a divergence between *expected* insulin effect (from PK model) and *observed* glucose response. This differs from gradual ISF drift (D1, biweekly): acute degradation happens over hours to 1-2 days.

**Optimal Configuration**:

| Dimension | Specification | Evidence |
|-----------|---------------|----------|
| Scale | Rolling 6-12h residual monitoring | EXP-308: insulin-controlled matching needed |
| History window | 12h rolling, compared against 7-day patient baseline | EXP-222: volatile MAE 2.04× calm |
| Features | PK-predicted glucose response, actual glucose, residual = actual − predicted, residual z-score | EXP-353: PK channels capture expected effect |
| Encoding | Residual time series + cumulative residual integral | — |
| Architecture | Threshold-based (if residual z-score > 3σ for >30 min, flag) + CUSUM on residual | EXP-325: CUSUM earliest detection at day 3 |
| Validation | Detection latency (hours to flag), false alarm rate, per-patient sensitivity | — |

**Output**: "Insulin appears less effective than usual over the last 8 hours. Possible causes: infusion site aging (change site?), illness, or temporary resistance. Consider a temporary ISF adjustment of −15%."
**Clinical Action**: Prompt site change, temporary ISF override, or flag for attention.
**Data Feasibility**: Every 12h window is a sample = ~170 per patient, ~1870 pooled. **Abundant.** But labeling is hard — we don't have canula change timestamps or illness logs.
**Status**: ❌ Gap — NOT YET DESIGNED
**Key Finding**: Gradual ISF drift is proven (9/11 patients, biweekly, EXP-194/312). Acute degradation is **completely untested**. EXP-325 showed online CUSUM has 85-100% false alarm rate on non-drift patients — but that was for ISF *drift*, not *residual* analysis. The key insight is to compare against the PK model's *expected* insulin effect, not raw glucose. If the PK model says "this insulin should have dropped glucose by 40 mg/dL" and it only dropped 15 mg/dL, that's a 62.5% absorption degradation signal. EXP-222 showed volatile periods have 2.04× MAE — some of that variance may be canula/sick effects currently treated as noise.

**Symmetry Note**: This use case exploits PK *equivariance* — ISF-normalized insulin response should be constant across time for the same patient. Deviations from equivariance ARE the signal. The ISF equivariance test (Section 4.4 of symmetry-sparsity document) would directly validate this approach.

---

#### E9: Override Pattern → Profile Recommendation (Repeated Overrides → Basal/ISF/CR Changes)

**Physiological Basis**: When a patient repeatedly applies the same override at similar times (e.g., exercise mode every weekday at 5 PM, sleep override every night at 10 PM), this indicates a **persistent mismatch** between their current profile (basal rates, ISF, CR schedules) and their actual physiology/routine. The overrides are compensating for a profile that doesn't fit. Instead of requiring daily manual overrides, the system should recognize the pattern and recommend a permanent profile change.

This is analogous to how oref0 autotune works — detecting persistent over/under-delivery patterns and suggesting basal/ISF/CR adjustments. But autotune operates on insulin delivery data, while this operates on *override behavior* data, capturing patient intent.

**Optimal Configuration**:

| Dimension | Specification | Evidence |
|-----------|---------------|----------|
| Scale | 14-day override history → profile change recommendation | EXP-227: override utility F1=0.993 |
| History window | 14-day rolling window of override events | EXP-312: biweekly is minimum reliable scale |
| Features | Override frequency per (time-of-day × day-of-week) cell, override type, associated glucose patterns, TIR before/after override | EXP-221: 73.8% have >30 min lead |
| Encoding | Tabular: 28-cell grid (4 blocks/day × 7 days) with override counts + mean TIR delta | — |
| Architecture | Rule-based heuristic: if override frequency > 3/week in same time block, flag for profile review. Optionally: XGBoost to predict TIR improvement from profile change | — |
| Validation | Simulated TIR improvement from applying profile change vs. continuing manual overrides | — |

**Output**: "You've applied exercise mode 12 times in the last 2 weeks, always between 5-7 PM on weekdays. Consider reducing your 5-7 PM basal rate by 20% permanently — this would eliminate the need for daily overrides while maintaining the same glucose control."
**Clinical Action**: Suggest specific profile schedule changes. Patient/provider reviews and applies.
**Data Feasibility**: ~85 days = ~6 biweekly windows per patient. **Borderline for ML** but sufficient for heuristic detection. Override events are sparse — typically 2-5 per day.
**Status**: ❌ Gap — NOT YET DESIGNED
**Key Finding**: Override WHEN prediction is solved (F1=0.993, EXP-227). Override TYPE classification (C2) is NOT STARTED. The feedback loop from "detect override pattern" → "recommend profile change" requires: (1) override type classification, (2) temporal clustering of same-type overrides, (3) mapping override effect to profile parameter. Step 1 (C2) is the blocker. However, a simpler heuristic version — just counting overrides per time block and recommending investigation when frequency exceeds threshold — is immediately feasible.

**Connection to AID autotune**: oref0 autotune detects persistent basal under/over-delivery from pump data. This approach detects persistent *override* patterns from user behavior data. They are complementary: autotune fixes the *insulin delivery* side, while E9 fixes the *user behavior* side. Both converge on the same goal: a profile that requires minimal manual intervention.

**Symmetry Note**: Profile changes should be validated against the biweekly ISF drift signal (D1). A profile recommendation is only valid if the underlying physiology is stable — if ISF is actively drifting, a profile change would be chasing a moving target. The ±20% autosens bounds (Finding 5 from diabetes-domain-learnings) provide the appropriate guard rails.

---

## Part 5: Cross-Cutting Principles (Evidence-Based)

These are not opinions. Each principle is proven by specific experiments with measurable effect sizes.

### Principle 1: Time-Translation Invariance (≤12h)

**Remove time features for all tasks at ≤12h scale.**

| Task | Δ without time | Experiment |
|------|---------------|------------|
| UAM (2h) | +0.9% F1 | EXP-349 |
| Override (2h) | +0.4% F1 | EXP-349 |
| Hypo (2h) | +0.2% F1 | EXP-349 |

Time features (sin/cos of hour-of-day) inject circadian information that *confuses* short-scale classifiers — a 2h window should not know what time of day it is because the physics (insulin action, carb absorption) are time-invariant at that scale. Break this symmetry only at ≥24h for circadian tasks (D3).

### Principle 2: Scale-Dependent Feature Importance

Feature sensitivity is **3.4× higher at 12h than 2h** (EXP-287/298).

At 2h, the model is relatively robust to feature choice — glucose dominates. At 12h, every feature choice matters enormously:
- **COB**: Noise at 2h, **critical** at 12h
- **bolus**: Useful at 2h, **hurts** at 12h
- **carbs_total**: Moderate at 2h, **#1 feature** at 12h

This is because short windows are dominated by glucose momentum (one signal), while long windows must disentangle multiple overlapping physiological processes (many signals).

### Principle 3: The 39-Feature Paradox

**More features ≠ better. Often dramatically worse.**

8 features → 39 features: MAE degrades 11.56 → 17.06, gap widens 2.8% → 28.6% (EXP-162).

87% of transformer attention focuses on glucose alone (EXP-162). Adding irrelevant features does not just fail to help — it actively creates noise that the model memorizes, destroying generalization. The solution is task-specific feature sets (see Part 6).

### Principle 4: 1D-CNN Universally Best for 2h Classification

For any binary or multi-class classification at 2h scale:

| Architecture | UAM F1 | Evidence |
|--------------|--------|----------|
| **1D-CNN** | **0.939** | EXP-337 |
| Embedding | 0.854 | EXP-337 |
| CNN + Embedding | Worse than CNN alone | EXP-337 |

Adding embedding layers to CNN *hurts* — the CNN's inductive bias (local temporal patterns) perfectly matches the 2h physiology. Transformers only help at 6h+ where long-range dependencies matter.

### Principle 5: Platt Calibration Is Essential

Raw model probabilities are miscalibrated. Platt scaling fixes this universally:

| Task | ECE Before | ECE After | Threshold shift | Experiment |
|------|-----------|-----------|----------------|------------|
| Override | 0.084 | 0.046 | 0.87 → 0.28 | EXP-343 |
| Hypo | 0.114 | 0.016 | Impractical → usable | EXP-345 |

Without Platt calibration, the hypo detector requires a threshold of ~0.87 probability to avoid false positives — making it useless in practice. After calibration, a threshold of ~0.28 is sufficient.

### Principle 6: Architecture < Features at 12h

| Architecture | 12h Override F1 | Experiment |
|--------------|----------------|------------|
| DeepCNN | 0.602 | EXP-298 |
| Transformer | 0.610 | EXP-298 |

Difference: +0.8% only. At 12h, the bottleneck is *feature engineering*, not model capacity. Investing in better features (PK encoding, ISF normalization, glucodensity) yields larger gains than architecture search.

### Principle 7: Per-Patient Heterogeneity

**3.2× MAE spread across patients**: 7.23–23.32 mg/dL (EXP-408).

A model that works well on average may be clinically dangerous for the hardest patients. Per-patient fine-tuning is essential for deployment. The good news: LOO (leave-one-out) gap is only 3–4% for classification tasks, suggesting reasonable generalization with fine-tuning.

### Principle 8: B-Spline Derivatives Help 2h Only

B-spline smoothing provides +15% SNR and -25% noise for analytic derivatives (EXP-331).

| Scale | B-spline effect | Experiment |
|-------|----------------|------------|
| 2h | +1.1% (UAM), +0.6% (override, hypo) | EXP-331, EXP-337 |
| 6h | -1% to -6% (hurts) | EXP-331 |
| 12h | Hurts | EXP-331 |
| 6h prolonged_high | +2.6% (exception) | EXP-331 |

At longer scales, the smoothing removes real high-frequency information that the model needs.

### Principle 9: FPCA Compression Is Scale-Locked

Functional PCA provides excellent compression at 2h but degrades at longer scales:

| Scale | Components (K) | Compression | Quality | Experiment |
|-------|----------------|-------------|---------|------------|
| 2h | K=2 | 12× | Excellent (90% variance) | EXP-329 |
| 7d | K=20+ | 8× | Barely viable | EXP-329 |

FPCA is not a general-purpose compression technique — its efficiency depends on the intrinsic dimensionality of the signal at each scale.

### Principle 10: PK Channels Are Scale-Dependent

PK (pharmacokinetic) encoding converts sparse bolus/carb events into continuous insulin-on-board and carbs-on-board curves.

| Configuration | Scale | Effect | Experiment |
|---------------|-------|--------|------------|
| PK history channels | 6h | Δ = -7.4 MAE (helps) | EXP-353 |
| PK history channels | 2h UAM | Δ = -3.4% F1 (hurts) | EXP-353 |
| Future PK projection | All horizons | h120: -10.0 mg/dL (helps) | EXP-356 |

PK history channels *hurt* UAM at 2h because UAM detection specifically looks for *absence* of insulin before a glucose rise — PK smoothing obscures this absence. But future PK projection helps at all horizons because it gives the model explicit knowledge of planned insulin/carb activity.

### Principle 11: Representation Validation — Scale-Specific Symmetry Tests

**Every encoding choice should be validated by testing that it respects the appropriate symmetry for its time scale.** This is not optional — it's how we verify that the representation captures the right structure rather than artifacts.

| Scale | Expected Symmetry | Test | Status | Evidence |
|-------|-------------------|------|--------|----------|
| **2h** (Fast) | Time-translation invariance | Remove time features → performance improves | ✅ Confirmed | EXP-349: +0.9% F1 |
| **2h** (Fast) | Absorption reflection symmetry | Pre-peak area ≈ post-peak area for isolated events | ❌ Proposed | symmetry-sparsity doc §4.2 |
| **6h** (DIA) | PK-resolves-ambiguity | PK channels stabilize long-window performance | ✅ Confirmed | EXP-353: Δ=-7.4 MAE at 6h |
| **12h** (Episode) | Time-translation invariance | Remove time features → performance stable or improves | ✅ Confirmed | EXP-298: Sil +0.224 |
| **12h** (Episode) | Conservation (integral) | Glucose integral ≈ physics-predicted integral | ❌ Proposed | symmetry-sparsity doc §4.3 |
| **24h** (Daily) | Circadian breaks time-invariance | Time features SHOULD help | ⚠️ Partial | EXP-126: 71.3 mg/dL amp |
| **6h–4d** (Strategic) | Event recurrence regularity | Same-type events cluster in time-of-day | ❌ Proposed | E7 meal scheduling hypothesis |
| **6h–4d** (Strategic) | ISF equivariance | ISF-normalized responses more similar cross-patient | ❌ Proposed | symmetry-sparsity doc §4.4 |
| **7d** (Weekly) | Day-of-week matters | Weekday vs weekend patterns distinguishable | ⚠️ Partial | EXP-301: Sil=-0.301 |
| **Biweekly** (Drift) | PK equivariance deviation = signal | Residual of actual vs PK-predicted glucose | ❌ Proposed | E8 absorption degradation |

**Validation Protocol for New Encodings**:
1. **Invariance check**: Ablate features that should be irrelevant (e.g., time at 2h). Performance should not degrade.
2. **Equivariance check**: Normalize by the appropriate patient-specific factor (ISF). Cross-patient similarity should increase.
3. **Conservation check**: Over complete physiological cycles, integral quantities should balance.
4. **Augmentation check**: Apply symmetry-respecting augmentations (time shift at 2h, amplitude scaling). Performance should be robust.

If an encoding fails its symmetry test, the representation is capturing artifacts rather than physiology. This is the data science equivalent of a unit test for feature engineering.

---

## Part 6: Feature × Scale × Task Matrix

Optimal feature inclusion by task and scale. ✅ = include, ❌ = exclude (hurts), ➖ = untested/neutral.

| Feature | 2h UAM | 2h Override | 2h Hypo | 6h Override | 12h Override | 7d Pattern | Biweekly Drift |
|---------|--------|-------------|---------|-------------|--------------|------------|----------------|
| glucose | ✅ | ✅ | ✅ | ✅ | ✅ (13× critical) | ✅ | ✅ |
| IOB | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| COB | ❌ (noise) | ✅ | ✅ | ✅ (critical) | ✅ (critical) | ✅ | ➖ |
| bolus | ✅ | ✅ | ✅ | ➖ | ❌ (hurts) | ➖ | ➖ |
| carbs | ✅ | ✅ | ✅ | ✅ | ✅ (#1 at 12h) | ✅ | ➖ |
| basal_rate | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ | ✅ |
| time_sin/cos | ❌ (hurts) | ❌ (hurts) | ❌ (hurts) | neutral | ❌ (hurts) | ✅ | ✅ (essential) |
| B-spline smooth | ✅ (+1.1%) | ✅ (+0.6%) | ✅ (+0.6%) | ❌ (hurts) | ❌ (hurts) | ➖ | ➖ |
| glucose_d1 | ✅ | ✅ | ✅ | ❌ | ❌ | ➖ | ➖ |
| PK channels | ❌ (-3.4%) | ❌ | ❌ | ✅ (Δ=-7.4) | needs test | ➖ | ➖ |
| Future PK | ➖ | ➖ | ➖ | ✅ (best) | needs test | ➖ | ➖ |
| ISF_normalized | helps | helps | helps | helps | ➖ | ➖ | ✅ |
| Functional depth | ➖ | ➖ | ✅ (112×) | ➖ | ➖ | ➖ | ➖ |
| Glucodensity | ✅ (head) | ✅ (head) | ✅ (head) | scale-free | scale-free | ✅ | ➖ |

**Reading this table**: For a 2h UAM detector, use glucose, IOB, bolus, carbs, basal_rate — but NOT COB (noise), NOT time_sin/cos (hurts), NOT PK channels (hurts). Add B-spline smoothing and glucodensity as head injection.

---

## Part 7: Normalization & Encoding Guide

| Technique | When to Use | Why | Evidence |
|-----------|-------------|-----|----------|
| BG/400 | Short-term forecast, 2h classification | Simple, preserves absolute levels, clinically interpretable | Default across most experiments |
| ISF-normalized BG | Cross-patient models, longer horizons | Removes patient-specific sensitivity scaling; "free lunch" | EXP-407: -0.44 MAE improvement |
| Per-patient z-score | Drift detection, pattern retrieval | Removes baseline, focuses on shape/dynamics | EXP-308 |
| B-spline smoothing | 2h classification only | Analytic derivatives, +15% SNR, -25% noise | EXP-331, EXP-337 |
| PK curve encoding | ≥4h forecasting, future PK projection | Converts sparse bolus/carb to continuous physiology | EXP-356: -10.0 MAE at h120 |
| Multi-rate EMA | Long horizons (12h+) | τ={15min, 1h, 4h, 24h} captures multiple dynamics | Proposed, not yet tested |
| FPCA compression | 2h only (K=2 → 12× compression) | Dimensionality reduction while preserving shape | EXP-329: K=2 captures 90% variance |
| Glucodensity (KDE) | Any scale (head injection) | Distributional summary, scale-free representation | EXP-330: +0.54 Silhouette vs TIR |
| Functional depth | Hypo detection specifically | Scores trajectory atypicality relative to patient distribution | EXP-335: 112× hypo enrichment |
| STL decomposition | Multi-day/weekly analysis | Separates trend, seasonal, and residual components | Proposed for multi-week analysis |

**Decision rule**: Start with BG/400. If building cross-patient models, add ISF normalization (free lunch). For 2h classification, add B-spline. For ≥4h forecasting, add PK encoding. For hypo specifically, add functional depth.

---

## Part 8: Architecture Decision Tree

```
What is your task?
│
├── CLASSIFICATION (detect/classify event)?
│   │
│   ├── Scale ≤ 2h?
│   │   └── 1D-CNN (3-layer, 32→64→64) — ALWAYS
│   │       ├── UAM?
│   │       │   └── B-spline + no_time_6ch
│   │       │       F1 = 0.939 [0.928-0.949] (EXP-337)
│   │       ├── Override WHEN?
│   │       │   └── Platt + kitchen_sink_10ch
│   │       │       F1 = 0.882 (EXP-343)
│   │       └── Hypo?
│   │           └── Multi-task + Platt + depth features
│   │               F1 = 0.676, AUC = 0.955 (EXP-345)
│   │
│   ├── Scale 6h?
│   │   └── Transformer + baseline_plus_fda_10ch
│   │       F1 = 0.715 override (EXP-287)
│   │
│   └── Scale 12h?
│       └── Transformer + baseline_plus_fda_10ch
│           (Bottleneck is features, not architecture)
│           F1 = 0.610 override (EXP-298)
│
├── FORECASTING (predict future glucose)?
│   │
│   ├── Single horizon (h30 or h60)?
│   │   └── PKGroupedEncoder Transformer
│   │       + PK channels + ISF normalization
│   │       + per-patient fine-tuning
│   │       MAE = 13.50 (EXP-408)
│   │
│   └── Multi-horizon (h30–h120)?
│       └── Multi-horizon encoder
│           + future PK projection
│           + 5-seed ensemble
│           -0.66 MAE per horizon step (EXP-406)
│
├── PATTERN RETRIEVAL / CLUSTERING?
│   └── 7d @ 1hr resolution
│       → Transformer encoder + cosine similarity
│       Sil = +0.326 (EXP-289/296)
│
├── DRIFT DETECTION?
│   └── Biweekly rolling ISF_effective
│       → Statistical tests (Spearman, not ML)
│       r = -0.328, 9/11 patients (EXP-194)
│
└── RECOMMENDATION (override WHICH/HOW)?
    └── ❌ NOT YET SOLVED
        Requires counterfactual simulation
        (physics-based, not pattern-matching)
```

---

## Part 9: Validation Framework by Use Case

| Task Type | Primary Metric | Secondary | Clinical Metric | Method |
|-----------|---------------|-----------|-----------------|--------|
| Forecast | MAE (mg/dL) | RMSE | **MARD (%)**, Clarke zones, ISO 15197 | Per-patient, multi-horizon, conformal |
| Binary classification | F1 | AUC-ROC | **ECE** (calibration), sensitivity @ specificity | Multi-seed (5), bootstrap 95% CI |
| Multi-class | Macro F1 | Per-class F1 | Confusion matrix, per-class ECE | Chronological 3-way split |
| Drift detection | Spearman r | p-value | Clinical significance (ISF change %) | Per-patient, biweekly rolling |
| Pattern retrieval | Silhouette | R@5, R@10 | Domain expert review | Held-out temporal windows |

### Critical Validation Rules

1. **Never use random splits for time series** — always chronological. Data leakage from future-to-past invalidates all results.
2. **Multi-seed (5) for all classification** — single-seed results are unreliable. Report mean ± std or bootstrap CI.
3. **Per-patient breakdown always** — aggregate metrics hide 3.2× performance spread (EXP-408). A model "averaging" 13.5 MAE may have 23.3 MAE on the hardest patient.
4. **ECE for any deployed classifier** — F1 alone is insufficient. Platt calibration + ECE reporting is mandatory (Principle 5).
5. **Conformal prediction for any deployed forecaster** — point predictions without uncertainty bands are clinically irresponsible (EXP-137: 90% coverage, Clarke A+B 97.1%).

---

## Part 10: Gap Analysis & Research Roadmap

### Tier 1: Blocks Deployment

| Gap | Why It Blocks | Difficulty | Approach |
|-----|---------------|------------|----------|
| Override WHICH + HOW MUCH (C2, C3) | Cannot recommend actions without knowing which action | Very Hard | Counterfactual physics simulation (UVA/Padova or similar) |
| Multi-day forecast >24h (A5) | Cannot support multi-day planning | Hard | Multi-rate encoding, STL decomposition, extended datasets |
| Treatment planning layer (E1–E6) | Missing entire clinical layer between AID and endocrinologist | Medium-Hard | Event likelihood prediction at 6h–4d horizons (EXP-411–418) |
| External signal integration | Illness/menstrual/HR data missing | Medium | API integration + prospective data collection |

### Tier 1.5: High-Probability Improvements (Untested Combinations)

| Gap | Current State | Expected Impact | Approach |
|-----|--------------|-----------------|----------|
| PKGroupedEncoder + 4–6h history (A1/A2) | Champion uses only 2h lookback | Potentially large: EXP-353 showed PK Δ=-7.4 at 6h | Test window_size=96 (48 history) and 144 (72 history) with v14 architecture |
| Multi-rate EMA for 12h+ classification (B4) | Proposed, code skeleton exists, never run | Unknown but theoretically motivated | Run EXP-375/406 with α=0.1/0.3/0.7 EMA channels |
| STL decomposition for multi-day | Proposed, no implementation | Enables trend/seasonal/residual separation | Implement and test 3-day windows |
| Cumulative glucose load features | Skeleton in exp_normalization_conditioning.py | Captures metabolic load accumulation | Run 12h/24h/72h integral features |
| Overnight risk assessment (E1) | Designed, not run | High: night TIR=60.1% is worst period, biggest clinical impact | EXP-412: 6h evening context → overnight P(hypo), P(high), TIR |
| Next-day TIR prediction (E2) | Designed, not run | Medium: enables proactive planning | EXP-413: 24h context → next-day TIR prediction |
| Extended history for classification (B1/B2/B4) | Only 2h tested | PK channels should resolve DIA Valley for classifiers too | EXP-417: test 4h/6h with PK channels |

### Tier 2: Improves Quality

| Gap | Current State | Target | Approach |
|-----|--------------|--------|----------|
| Hypo F1 improvement (B2) | F1 = 0.676 | F1 ≥ 0.80 | Better negative sampling, PK-aware features, multi-task learning |
| 12h feature engineering (B4) | F1 = 0.610 | F1 ≥ 0.70 | PK encoding at 12h, multi-rate EMA, carb-type features |
| Sensor artifact detection (B8) | Not tested | F1 ≥ 0.90 | dG/dt thresholding, compression low signature detection |

### Tier 3: Future Capabilities

| Gap | Requires | Estimated Effort |
|-----|----------|-----------------|
| Seasonal ISF tracking (D6) | >6 months data per patient | Low (extend D1 to longer windows) |
| Illness detection (D4) | External signals (HR, temp, symptoms) | Medium |
| Infusion set failure (B7) | Counterfactual insulin effect modeling | Hard |
| Pre-bolus timing optimization (C5) | Simulation + optimization loop | Hard |
| Rebound high detection (B10) | Post-hypo labeling + dedicated model | Low-Medium |

---

## Part 11: Summary Table (Quick Reference)

All 28 sub-use-cases in one view:

| ID | Sub-Use-Case | Scale | Key Features | Architecture | Best Result | Status |
|----|-------------|-------|-------------|-------------|-------------|--------|
| **A: PREDICT GLUCOSE** | | | | | | |
| A1 | Short-term forecast (≤30 min) | 2h | 8ch + PK | PKGroupedEnc Transformer | 13.50 MAE, MARD ≈ 8.7% | ✅ |
| A2 | Medium-term dosing (60 min) | 2h + future PK | 8ch + PK + future PK | PKGroupedEnc Transformer | 13.50 MAE (multi-h) | 🟡 |
| A3 | Long-term meal (90–120 min) | 2h + future PK | 8ch + future PK projection | Multi-horizon encoder | -0.66 MAE/step | 🟡 |
| A4 | Overnight basal (6–8h) | 6–8h | glucose, IOB, basal, time | Night specialist | 16.0 MAE | 🟡 |
| A5 | Multi-day trends (>24h) | Multi-day | Unknown | Unknown | None | ❌ |
| A6 | Conformal / alert calibration | Any | Wraps base model | Conformal prediction | 90% cov, 97.1% Clarke A+B | ✅ |
| **B: DETECT/CLASSIFY** | | | | | | |
| B1 | UAM detection | 2h | no_time_6ch + B-spline | 1D-CNN | F1 = 0.971 | ✅ |
| B2 | Hypo prediction | 2h | Baseline + func. depth | Multi-task CNN + Platt | F1 = 0.676, AUC = 0.955 | 🟡 |
| B3 | Meal detection | 12h | carbs_total #1 | Transformer | F1 = 0.565 | 🟡 |
| B4 | Override WHEN | 2h / 6h / 12h | kitchen_sink (2h) | CNN (2h) / Transformer (6h+) | F1 = 0.882 (2h) | ✅ / 🟡 |
| B5 | Prolonged high | Implicit | Implicit in B4 | — | — | 🟡 |
| B6 | Exercise detection | 2h | Baseline | 1D-CNN | F1 = 0.736 | 🟡 |
| B7 | Infusion set failure | — | — | — | — | ❌ |
| B8 | Compression low / artifact | — | — | — | — | ❌ |
| B9 | Insulin stacking | Implicit | IOB feature | — | Implicit | 🟡 |
| B10 | Rebound high post-hypo | — | — | — | — | ❌ |
| **C: RECOMMEND/PLAN** | | | | | | |
| C1 | Override timing (WHEN) | 2h | Same as B4 | Same as B4 | F1 = 0.993 utility | ✅ |
| C2 | Override type (WHICH) | — | — | Counterfactual sim | — | ❌ |
| C3 | Override magnitude (HOW MUCH) | — | — | Counterfactual sim | — | ❌ |
| C4 | Bolus / CR adjustment | — | — | Requires C2/C3 | — | ❌ |
| C5 | Pre-bolus timing | — | Lead time characterized | — | 73.8% >30 min lead | 🟡 |
| C6 | Temp target recommendation | — | Types identified | — | — | 🟡 |
| **D: TRACK STATE** | | | | | | |
| D1 | ISF drift | Biweekly | ISF_effective | Statistical tests | r = -0.328, 9/11 patients | ✅ |
| D2 | Pattern retrieval | 7d @ 1hr | glucose + insulin + carbs | Transformer + cosine | Sil = +0.326 | 🟡 |
| D3 | Circadian profile | 24h | glucose + time_sin/cos | Statistical | 71.3 ± 18.7 mg/dL, 100% | ✅ |
| D4 | Illness detection | — | Requires external signals | — | — | ❌ |
| D5 | Menstrual cycle effects | — | Requires cycle labels | — | — | ❌ |
| D6 | Seasonal trends | — | Requires >6 months data | — | — | ❌ |
| **E: STRATEGIC PLAN** | | | | | | |
| E1 | Overnight risk assessment | 6h | glucose, IOB, time, PK | 1D-CNN + Platt | — | ❌ Designed (EXP-412) |
| E2 | Next-day TIR prediction | 24h | glucodensity, events, day-of-week | XGBoost / CNN | — | ❌ Designed (EXP-413) |
| E3 | Multi-day control quality | 3–4d | 8×12h episode features → GRU | Hierarchical CNN+GRU | — | ❌ Designed (EXP-414) |
| E4 | Event recurrence | 7d→6h/24h/3d | event counts per 6h block | XGBoost + CNN | — | ❌ Designed (EXP-415) |
| E5 | Weekly routine hotspots | 7d | per-block TIR, events, CV | Descriptive + ranking | — | ❌ Designed (EXP-416) |
| E6 | Strategic override planning | 7d→3-4d | Combines E1-E5 outputs | Rule-based on top of ML | — | ❌ Conceptual |
| E7 | Proactive meal scheduling | 3d UAM history | UAM timestamps, regularity score | Heuristic + XGBoost | — | ❌ Gap |
| E8 | Acute absorption degradation | 12h rolling | PK residual (actual − predicted) | CUSUM on residual | — | ❌ Gap |
| E9 | Override → profile recommendation | 14d overrides | Override frequency per time block | Heuristic + rule-based | — | ❌ Gap |

**Production-ready (✅)**: 7 sub-use-cases — A1, A6, B1, B4-2h, C1, D1, D3
**Active research (🟡)**: 11 sub-use-cases
**Designed but untested (❌ Designed)**: 6 sub-use-cases — E1-E5, EXP-411-418
**Undesigned gaps (❌ Gap)**: 13 sub-use-cases — including E7 (meal scheduling), E8 (absorption), E9 (override→profile)

---

*This document synthesizes 410+ experiments across 11 patients. It is a living prescription guide — as new experiments fill gaps, entries should be updated with fresh evidence. The structure (physiological basis → optimal config → evidence → status) ensures every recommendation is traceable to empirical results, not theoretical reasoning. The newly added Category E (Strategic Plan) represents the critical insight that the 6h–4 day horizon requires a fundamentally different approach: event likelihood prediction and state assessment, not glucose point forecasts.*
