# Productionization vs R&D: Capability-Technique Alignment

**Date**: 2026-04-08  
**Context**: 1,000+ experiments, 30+ capabilities cataloged, 20+ ML techniques evaluated  
**Prior reports**: `top-5-campaign-insights-2026-04-08.md`, `research-to-deployment-strategy-2026-04-08.md`

---

## Executive Summary

This report classifies every discovered capability into one of four categories
based on its relationship to its performance ceiling and the technique best
suited to deliver it:

| Category | Count | Strategy |
|----------|-------|----------|
| **Productionize** — physics + simple ML, proven | 12 capabilities | Ship now |
| **Enhance with targeted ML/DL** — clear ROI, specific technique | 5 capabilities | Focused R&D |
| **Explore with generative/foundation approaches** — speculative, high ceiling | 4 capabilities | Strategic R&D |
| **Accept ceiling** — data-limited, no technique helps | 4 capabilities | Wait for new data |

**The core principle**: A capability should be productionized when it is at or
near its ceiling with current techniques. Additional ML/DL investment is
warranted only when there is a **specific, named technique** with a **clear
mechanism** for how it would break through a currently identified bottleneck.

---

## Part 1: Productionize Now

These capabilities are at or near their performance ceilings using physics
decomposition + simple ML (Ridge, XGBoost, rule engines). Adding neural
complexity would not improve outcomes, only add latency and fragility.

### 1.1 Glucose Forecasting (h5–h120)

| Horizon | MAE | Technique | Why Not DL |
|---------|-----|-----------|-----------|
| h5 | 5.5 mg/dL | Ridge on 8 PK features | At ceiling (R²=0.978) |
| h30 | 11.1 mg/dL | Ridge → PKGroupedEncoder | Transformer adds <0.5 MAE |
| h60 | 14.2 mg/dL | Ridge + circadian correction | At 95% of oracle ceiling |
| h120 | 17.4 mg/dL | PKGroupedEncoder (134K) | Window-independent — 2h history sufficient |

**Production stack**: `continuous_pk.build_continuous_pk_features()` → Ridge
regression for h5–h60, PKGroupedEncoder for h90–h120.

**Why Ridge over DL**: Ridge on 8 physics features achieves R²=0.534. The
full transformer adds +0.029 R² (5% relative). Ridge is interpretable,
has zero hyperparameters beyond regularization, trains in <1ms, and its
predictions can be audited by clinicians.

### 1.2 HIGH Risk Alerts (4 tasks)

| Task | AUC | Technique |
|------|-----|-----------|
| 2h HIGH prediction | 0.844 | 1D-CNN (16ch) |
| Overnight HIGH risk | 0.805 | CNN on 6h evening context |
| HIGH recurrence (24h) | 0.882 | XGBoost |
| HIGH recurrence (3d) | 0.919 | XGBoost |

**Why not DL**: Three independent architectures (CNN, XGBoost, Transformer) all
converge at these AUC values. The ceiling is information-theoretic, not
architectural. XGBoost is preferred for recurrence tasks because it explicitly
encodes treatment features that transformers ignore (86.8% attention to glucose).

### 1.3 Therapy Settings Assessment (physics-only)

| Capability | Technique | Why Physics Suffices |
|-----------|-----------|---------------------|
| Basal adequacy (8/10 too high) | Stable-window drift analysis | Pure measurement, no prediction needed |
| CR effectiveness scoring | Post-meal recovery analysis | Deterministic computation |
| ISF validation (69% overestimate) | Correction bolus analysis | Statistical comparison |
| AID compensation detection | Supply/demand flux decomposition | Physics decomposition IS the product |
| Override timing (F1=0.993) | TIR-impact scoring | Rule engine on physics outputs |

**No ML at all**: These capabilities compute deterministic physics quantities
(IOB, COB, supply, demand, hepatic production) and apply threshold rules.
Adding ML would reduce interpretability without improving accuracy.

### 1.4 Data Quality & Preprocessing

| Capability | Technique | Status |
|-----------|-----------|--------|
| Spike cleaning (+52% R²) | MAD filter σ=2.0 | Statistical, no ML needed |
| Sensor age validation (no degradation) | Correlation analysis | Pure analytics |
| Longitudinal stability (40% less degradation) | Trend analysis | Pure analytics |

### 1.5 Event Detection

| Event | F1 | Technique |
|-------|-----|-----------|
| Meal detection | 0.822 (train) / 0.547 (verify) | XGBoost |
| Correction bolus | 0.768 / 0.637 | XGBoost |
| Override detection | 0.742 / 0.644 | XGBoost |

**Why XGBoost beats neural**: XGBoost's feature importance shows `carbs_total`
(0.124), `bolus_total` (0.085) as top features — explicit treatment signals.
The transformer allocates 86.8% of attention to glucose history and effectively
ignores treatment channels. For event detection, **features matter more than
architecture** (EXP-155: XGBoost F1=0.705 vs Transformer F1=0.107).

### 1.6 Real-Time Pipeline & Cold Start

| Capability | Metric | Status |
|-----------|--------|--------|
| End-to-end latency | 118.5 ms | Production-ready |
| Model footprint | <3 MB, 134K params | On-device capable |
| Population warm-start (day 1) | R²=0.437 | Validated |
| Personal calibration (day 7) | R²=0.652 | Validated |

### 1.7 Patient Risk Stratification

| Capability | Technique | Status |
|-----------|-----------|--------|
| Composite fidelity scoring | Multi-metric weighted index | Production |
| Loop behavior phenotyping | Delivery ratio analysis | Production |
| Patient difficulty ranking | CV + TIR + aggressiveness | Production |
| Settings change detection | Rolling RMSD breakpoints | Production |

---

**Summary**: 12 capabilities across 25+ specific tasks ready for Nightscout
plugin deployment. Total compute: ~600K params, <15ms inference, <3MB memory.

---

## Part 2: Enhance with Targeted ML/DL

These capabilities have **identified bottlenecks** where a **specific named
technique** has a clear mechanism for improvement. These are focused R&D
investments with measurable success criteria.

### 2.1 Conformal Prediction → Calibrated Uncertainty Bounds

**Current gap**: The production forecaster outputs point predictions only. Clinical
dosing decisions require knowing *how confident* the prediction is.

**Why this technique**: Conformal prediction provides distribution-free coverage
guarantees — "the true value will be inside this interval 90% of the time" —
without distributional assumptions. A prototype already exists (60× calibration
improvement, EXP training-techniques) but isn't systematized.

**Mechanism**:
```
Point forecast (Ridge/Transformer) → historical conformity scores →
prediction interval that adapts width by:
  - Patient (h has wider intervals)
  - Time of day (postprandial wider)
  - Glucose level (>250 mg/dL: 2× wider)
  - Recent data quality (missing data → wider)
```

**Success criteria**: Coverage within 2% of target (88–92% for 90% target)
across all 11 patients and all horizons h30–h120.

**ROI**: Unlocks dosing guidance — "take 4U ± 1U" instead of just "take 4U."
Transforms forecasting from informational to actionable.

**Estimated effort**: Small — infrastructure exists in `validation_framework.py`
(`BootstrapCI`). Needs formalization into production pipeline.

### 2.2 Causal Inference → True ISF/CR Estimation

**Current gap**: AID loop compensation masks true patient sensitivity. Profile
ISF overestimates by 69% on average (EXP-974). Current statistical analysis
can detect the problem but can't disentangle AID effect from patient physiology.

**Why this technique**: The AID loop creates a *treatment-confounder feedback
loop* — the very insulin delivery we're measuring is adjusted by the loop
based on glucose it's trying to control. Standard regression confounds the
loop's action with the patient's response.

**Mechanism**: Inverse Probability Weighting (IPW) or G-computation to estimate
the *counterfactual*: "What would glucose have done if the loop hadn't
intervened?"

```
Observed: glucose(t) = f(patient_physiology, loop_action, meals)
                                             ↑
                        loop_action = g(glucose(t-1), ...) ← confound

Causal estimate: E[glucose | do(insulin=x)] ≠ E[glucose | insulin=x]
```

**Data available**: The stable windows (0.1–2.9% of time) provide natural
experiments where the loop IS idle. These could serve as instrumental variables
or natural control periods. Additionally, the full treatment log provides
the propensity score basis (probability of each loop action given glucose state).

**Success criteria**: ISF estimates with <20% coefficient of variation across
repeat measurements within the same patient.

**ROI**: Directly fixes the "8/10 patients have basal too high" finding with
precise correction values. Transforms settings assessment from "directional"
to "quantitative."

### 2.3 Residual CNN → Universal Stacking Layer

**Current status**: EXP-1024 showed Residual CNN (learn Ridge errors with CNN)
is the **only technique in 1,000+ experiments to improve all 11/11 patients**
(+0.024 mean R²). But it's only validated for h60 prediction.

**Enhancement needed**: Extend to all horizons (h30–h360) and all capabilities
(not just forecasting). The residual pattern — train a simple model first,
then learn its errors with a neural model — could be applied to:

- HIGH risk prediction (Ridge → residual CNN)
- Event detection (XGBoost → residual CNN on misclassified events)
- Settings drift detection (physics baseline → CNN on violations)

**Mechanism**: The residual has lag-1 autocorrelation ≈ 0.50 (short-range
error persistence). CNN captures this 25–30 minute error pattern that Ridge
can't model. Universal application would add +0.02 R² across all tasks
at minimal compute cost.

**Success criteria**: Positive improvement on ≥10/11 patients across ≥3
different capability types, validated under block CV.

**Estimated effort**: Medium — architecture exists, needs multi-task validation.

### 2.4 Proper Diffusion Models → Probabilistic Forecasting

**Current gap**: The toy DDPM implementation (1D diffusion) has incorrect
forward process and no proper β-schedule — uncertainty estimates are
meaningless.

**Why this technique**: Diffusion models generate *distributions* of possible
futures rather than point estimates. For glucose forecasting, this maps directly
to clinical need:

```
Instead of: "Glucose will be 150 mg/dL in 2 hours"
Generate:   "Here are 100 plausible glucose trajectories for the next 2 hours"
            → 5th percentile = worst-case hypo risk
            → 95th percentile = worst-case high risk
            → Median = best estimate
```

**Why not conformal**: Conformal prediction gives intervals, but diffusion gives
*trajectories*. A trajectory shows "you'll spike to 220 then come down to 140"
vs conformal's "you'll be between 120 and 200." Trajectories are clinically
richer — they show the *shape* of the glucose path, not just bounds.

**Mechanism**: Condition the diffusion process on the physics features (IOB, COB,
supply/demand) to generate physiologically constrained samples. This naturally
handles the meal uncertainty problem: unannounced meals create multi-modal
futures (meal vs no-meal), which diffusion models capture as separate trajectory
clusters.

**Success criteria**: Calibrated 90% CI (88–92% empirical coverage) with
narrower intervals than conformal prediction (which tends to be conservative).

**Estimated effort**: Large — requires proper implementation (DDPM or score-based),
physics conditioning, and extensive calibration. ~2–4 weeks.

### 2.5 Multi-Horizon Joint Training → Extended Forecast Quality

**Current gap**: Each horizon has a separate model. The h150–h360 models are
undertrained (8,792 windows for w144 vs 26,425 for w48).

**Why this technique**: Training a single model to predict *all* horizons
simultaneously shares statistical strength across horizons. The shared
representation captures glucose dynamics, while horizon-specific heads specialize.

**Mechanism**:
```
Shared encoder (PKGroupedEncoder, 134K params)
  ├── Head h30  (linear, 64→1)
  ├── Head h60  (linear, 64→1)
  ├── Head h120 (linear, 64→1)
  └── Head h360 (linear, 64→1)
```

All heads train on the same windows, but only the relevant horizon contributes
to each head's loss. This gives w144's h360 head the benefit of w48's 26K
windows for representation learning.

**Success criteria**: h300–h360 MAE improvement of ≥1.5 mg/dL vs current
single-horizon specialist.

**Estimated effort**: Medium — architecture change is simple, but training
dynamics (horizon loss balancing) need tuning.

---

## Part 3: Explore with Generative/Foundation Approaches

These are higher-risk, higher-reward R&D directions. The mechanism is plausible
but unproven in this domain. Worth exploring but not betting the roadmap on.

### 3.1 LLM-Powered Clinical Narrative Generation

**Opportunity**: The production pipeline outputs structured JSON (forecasts,
risk scores, settings assessments). Translating this to natural-language
clinical narratives would dramatically increase accessibility.

**Concept**:
```
Input:  Structured pipeline output
        {forecast: [120, 135, 155], risk: "high", basal: "too_high",
         cr_score: 37.4, isf_ratio: 2.91}

Output: "Your glucose is trending upward toward 155 mg/dL over the next
         90 minutes. Based on 6 months of data, your basal rate appears
         30% higher than needed — your pump suspends insulin 76% of the
         time to compensate. Consider discussing a basal reduction with
         your endocrinologist."
```

**Why generative**: The combinatorial explosion of clinical contexts
(time of day × glucose trend × recent meals × AID state × patient history)
makes template-based generation brittle. An LLM can compose natural,
context-appropriate narratives.

**Risk**: Hallucination in clinical context is dangerous. Requires strict
grounding in pipeline outputs — the LLM should *narrate*, not *analyze*.
All numbers must come from the structured output, never generated.

**Approach**: Fine-tuned small LLM (7B) or prompted large LLM with structured
output as context. Validate against clinician-written reference narratives.

### 3.2 Foundation Models for Time Series Pre-training

**Opportunity**: With only 11 patients, patient-specific models are data-limited.
Public CGM datasets (OhioT1DM, REPLACE-BG, DIaMonD) contain hundreds of patients.
A foundation model pre-trained on public data could provide better representations
than training from scratch.

**Concept**: Pre-train a transformer encoder on masked glucose prediction
(predict missing 5-min intervals) across 200+ public patients. Fine-tune
on our 11 patients for specific tasks.

**Current evidence**: Population warm-start already achieves 99.4% of personal
model quality (EXP-697). Foundation pre-training could push this further and
improve cold-start performance (day 1 R² from 0.437 toward 0.55+).

**Risk**: Domain shift between public datasets (different CGMs, different
populations, different AID systems) may limit transfer. The 99.4% population
result suggests diminishing returns.

**Prerequisite**: Need 50+ patients before this investment pays off. With 11,
LOPO transfer already covers the cross-patient signal.

### 3.3 Hierarchical VAE for Latent Patient State

**Opportunity**: Patients drift over months (EXP-975: 5.3 changepoints/patient).
Currently this is detected post-hoc via breakpoint analysis. A latent state
model could track drift in real time.

**Concept**: Learn a low-dimensional latent state z(t) that captures the patient's
current physiological regime (insulin sensitivity, carb absorption speed,
circadian amplitude). As z(t) drifts, the forecast model adapts automatically.

**Current evidence**: The simple VAE (32D bottleneck) failed catastrophically
(42.78 MAE). However, the failure was due to a global bottleneck destroying
sequence structure. A *hierarchical* VAE — with temporal latent states at
multiple scales (per-step, per-day, per-week) — avoids this by not forcing
all information through one bottleneck.

**Risk**: Architectural complexity. The simple approach (retrain Ridge weekly)
may be equally effective at tracking drift.

### 3.4 Offline Reinforcement Learning for Dosing Optimization

**Opportunity**: Instead of predicting glucose and letting the AID loop act,
learn an optimal *policy* directly from logged treatment decisions and outcomes.

**Concept**: Conservative Q-Learning (CQL) on the treatment log:
- State: glucose history + PK features + time of day
- Action: insulin dose adjustment (increase/decrease/maintain)
- Reward: time-in-range in next 2–4 hours

**Current evidence**: The AID confound analysis (EXP-981–985) shows existing
policies are suboptimal (8/10 basal too high). An RL agent trained on outcomes
could learn a better policy from the same data.

**Risk**: Safety — RL policies can recommend dangerous actions in
out-of-distribution states. Requires conservative constraints (CQL), extensive
simulation testing, and human-in-the-loop deployment.

**Prerequisite**: Would need UVA/Padova simulator integration for safe
policy evaluation before any real-patient deployment.

---

## Part 4: Accept Ceiling — Data-Limited, No Technique Helps

These capabilities have **fundamental information limits** that no ML technique
can overcome. The bottleneck is missing input data, not modeling power.

### 4.1 Hypoglycemia Prediction Beyond 2 Hours

**Ceiling**: AUC = 0.69 (CNN ≈ XGBoost ≈ Transformer)

**Why no technique helps**: Counter-regulatory hormones (glucagon, epinephrine,
cortisol) activate non-linearly below 70 mg/dL. These create the rebound
dynamics that make hypo trajectories unpredictable. No feature of CGM + insulin
+ carbs encodes this information.

**What would break it**: Continuous glucagon monitoring (research-grade only),
wearable stress/activity sensors (heart rate variability as cortisol proxy),
or continuous ketone monitoring (metabolic state indicator).

### 4.2 Unannounced Meal Prediction

**Ceiling**: F1 = 0.565 (predictive, before glucose moves)

**Why no technique helps**: 46.5% of meals have no carb entry. The model cannot
predict when a human will eat. Reactive detection (F1=0.939, once glucose rises)
is already excellent and sufficient for AID safety.

**What would break it**: Meal photo recognition, calendar/routine integration,
or wearable gut motility sensing.

### 4.3 Precision Dose Calculation

**Ceiling**: MARD ~14% at h60 (need <10%)

**Why no technique helps**: The 4% MARD gap is entirely explained by meal
uncertainty. Glycemic index, meal composition (protein/fat ratio), and gut
absorption rate are unmeasured.

**What would break it**: Automated meal composition estimation from food photos,
or continuous ketone monitoring for macronutrient absorption tracking.

### 4.4 h360+ Forecast Accuracy

**Ceiling**: MAE ~22 mg/dL (data-limited at w144, 8,792 windows)

**Why no technique helps within current data**: Stride reduction from 48→24→12
at w144 increases windows but only adds correlated data, not diverse data
(EXP-480: +0.40 MAE, opposite direction). More patients are needed, not more
windows from the same 11 patients.

**What would break it**: Expanding from 11 to 50–100 patients. The 0.74×
quick-to-full scaling factor suggests that doubling training data would yield
~1.5 mg/dL MAE improvement at h360.

---

## Decision Matrix

| Capability | Ceiling Status | Technique Now | Enhance With | Action |
|-----------|---------------|---------------|-------------|--------|
| h5–h60 forecast | **At ceiling** | Ridge + PK | — | **Ship** |
| h90–h120 forecast | **At ceiling** | Transformer | — | **Ship** (after 11pt val) |
| HIGH risk (4 tasks) | **At ceiling** | CNN/XGBoost | — | **Ship** |
| Settings assessment | **At ceiling** | Physics only | — | **Ship** |
| Spike cleaning | **At ceiling** | MAD filter | — | **Ship** |
| Event detection | **At ceiling** | XGBoost | Residual CNN | **Ship** + enhance |
| Cold start | **At ceiling** | Transfer learning | Foundation models | **Ship** + explore |
| Risk stratification | **At ceiling** | Rule engine | — | **Ship** |
| Pipeline | **At ceiling** | Production code | — | **Ship** |
| Forecast uncertainty | **Gap** | Prototype only | **Conformal prediction** | R&D → ship |
| ISF/CR estimation | **Gap** | Statistical | **Causal inference** | R&D |
| Residual patterns | **Below ceiling** | Single-horizon CNN | **Multi-task residual** | R&D |
| Probabilistic forecast | **Missing** | Toy DDPM | **Proper diffusion** | R&D |
| Extended horizons | **Below ceiling** | Per-horizon | **Multi-horizon joint** | R&D |
| Clinical narratives | **Missing** | — | **LLM generation** | Explore |
| Patient state tracking | **Gap** | Breakpoints | **Hierarchical VAE** | Explore |
| Dosing optimization | **Missing** | — | **Offline RL** | Explore |
| HYPO >2h | **Hard ceiling** | All converge | — | **Wait for data** |
| UAM prediction | **Hard ceiling** | — | — | **Wait for data** |
| Dose calculation | **Hard ceiling** | — | — | **Wait for data** |
| h360+ accuracy | **Data ceiling** | w144 | — | **Wait for patients** |

---

## Recommended Roadmap

### Phase 1: Ship the Physics Layer (Immediate)

Deploy the 12 production-ready capabilities as a Nightscout plugin:

```
Nightscout CGM + treatments + profile
  → Spike cleaning (MAD σ=2.0)
  → PK features (continuous_pk.py)
  → Ridge forecast (h5–h60)
  → XGBoost event detection
  → Physics settings assessment
  → Rule-based clinical recommendations
  → Structured JSON + dashboard overlay
```

**No neural networks in Phase 1.** Ridge + XGBoost + physics rules cover
all Tier 1 capabilities with <3MB footprint and <15ms latency.

### Phase 2: Add Calibrated Uncertainty (Short-term R&D)

Implement conformal prediction on top of the Phase 1 forecaster:

- Prediction intervals at 50%/80%/90% coverage levels
- Patient-specific, time-of-day-specific, glucose-level-specific width
- Enables "take 4U ± 1U" dosing guidance

**Deliverable**: Forecast band overlay on Nightscout dashboard.

### Phase 3: Add Transformer for Extended Horizons (Medium-term R&D)

Deploy the PKGroupedEncoder for h90–h360 via 3-window routing:
- Validate at full scale (11pt, 5-seed)
- Add multi-horizon joint training
- Add residual CNN stacking layer

**Deliverable**: "What will my glucose be in 3 hours?" with calibrated
uncertainty intervals.

### Phase 4: Causal Settings & Clinical Intelligence (Longer-term R&D)

- Causal inference for true ISF/CR estimation (IPW/G-computation)
- LLM-powered clinical narrative generation
- Offline RL for dosing optimization (simulation-validated)

**Deliverable**: "Your ISF is actually 78, not 49. Here's the evidence and
a suggested settings change to discuss with your doctor."

### Phase 5: New Data Integration (Strategic)

- Activity sensor integration (heart rate, accelerometer)
- Meal photo recognition for carb estimation
- Continuous ketone monitoring for metabolic state
- Expanded patient cohort (11 → 50–100)

**Deliverable**: Break the HYPO ceiling (AUC 0.69 → 0.80+) and enable
precision dose calculation.

---

## Source Code References

| Component | Location | Status |
|-----------|----------|--------|
| Production pipeline (20 modules) | `tools/cgmencode/production/` | Ship |
| PK feature engine | `tools/cgmencode/continuous_pk.py` | Ship |
| Forecast models | `tools/cgmencode/exp_pk_forecast_v14.py` | Ship |
| Event detection | `tools/cgmencode/exp_refined_483.py` | Ship |
| Settings assessment | `tools/cgmencode/exp_clinical_981.py` | Ship |
| Validation framework | `tools/cgmencode/validation_framework.py` | Ship |
| Visualization module | `tools/cgmencode/report_viz.py` | Ship |
| Experiment library | `tools/cgmencode/experiment_lib.py` | Ship |
