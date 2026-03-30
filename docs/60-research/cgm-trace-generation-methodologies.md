# CGM Trace Generation Methodologies: Research Exploration

> **Status**: Research document — methodologies worth exploration for simulation validation
> **Parent**: `docs/architecture/simulation-validation-architecture.md` §8
> **Created**: 2025-07-18
> **Scope**: How to generate realistic synthetic CGM traces and treatment streams for algorithm validation

---

## Table of Contents

1. [Motivation: Why Generation Methodology Matters](#1-motivation)
2. [Current State: What We Have](#2-current-state)
3. [Methodology 1: Physics-Based Models](#3-physics-based)
4. [Methodology 2: Supervised ML (Prediction, Not Generation)](#4-supervised-ml)
5. [Methodology 3: Generative Models](#5-generative)
6. [Methodology 4: Hybrid Physics-ML Models](#6-hybrid)
7. [Methodology 5: Corruption-Based Augmentation (Diffusion-Adjacent)](#7-corruption)
8. [UVA/Padova: Validation History and Improvement Processes](#8-uva-padova)
9. [Comparison Matrix](#9-comparison)
10. [Recommended Exploration Roadmap](#10-roadmap)
11. [Open Questions](#11-open-questions)
12. [References](#12-references)

---

## 1. Motivation: Why Generation Methodology Matters {#1-motivation}

### The Core Problem

Our algorithm validation infrastructure needs to generate synthetic CGM traces that:

1. **Reflect the statistical distribution of real human glucose** (SD 50-65 mg/dL, range 40-350+)
2. **Respond causally to simulated treatments** (insulin → BG drop, carbs → BG rise)
3. **Produce realistic counterfactuals** ("what if we gave 20% less insulin?")
4. **Cover edge cases** that are rare in observational data but critical for safety

### The Known Problem

Our current tooling uses cgmsim-lib's simplified CGMSIM engine, which produces an
artificially narrow BG range (89-140 mg/dL). Algorithm rankings **reverse** between
synthetic and real data:

| Data Source | Best Algorithm | MAE  | BG Range    |
|-------------|---------------|------|-------------|
| CGMSIM synthetic | Persistence | 2.3  | 89-140 mg/dL |
| Real TV-* vectors | oref0     | 14.6 | 40-350+ mg/dL |

**Source**: `tools/aid-autoresearch/in-silico-bridge.js` (uses `CGMSIMsimulator`),
`tools/aid-autoresearch/score-in-silico.js`

This means our synthetic data is **not valid for algorithm comparison**. Choosing a
generation methodology that closes this gap is a prerequisite for autonomous algorithm
improvement.

### What Makes a Generated Trace "Good"?

A generated CGM trace is considered realistic when it matches real data across
**four statistical layers** (see parent doc §5):

| Layer | Metric | What It Measures |
|-------|--------|-----------------|
| **Distribution** | Wasserstein-1 distance | Overall BG histogram shape |
| **Temporal dynamics** | ACF RMSE (lags 1-72) | Serial correlation, oscillation patterns |
| **Event shapes** | DTW on meal/hypo windows | Response curves to meals, corrections |
| **Prediction residuals** | Residual distribution match | How well the model explains transitions |

---

## 2. Current State: What We Have {#2-current-state}

### 2.1 CGMSIM Engine (Simplified Physics)

**Location**: `externals/cgmsim-lib/src/CGMSIMsimulator.ts`

The current BG equation:

```
nextBG = lastBG + insulinEffect×18 + carbsEffect×18 + liverEffect×18
```

Where:
- `insulinActivity = units × (norm/τ²) × t × (1-t/D) × e^(-t/τ)` (15-min ramp)
- `carbAbsorption` = dual-phase: fast (~60min) + slow (~240min), trapezoidal
- `liverOutput = baseRate × weight × Hill_suppression(1.5) × circadian_sine`
- Clamped to [40, 400]

**Limitations**:
- No inter-compartmental dynamics (single BG pool)
- No glucagon counter-regulation
- No exercise effects
- 3 patient profiles, all with "correct" therapy settings

### 2.2 UVA/Padova Engine (Full Physics, ✅ Integrated)

**Location**: `externals/cgmsim-lib/src/lt1/core/models/UvaPadova_T1DMS.ts` (817 lines)

18 coupled ODEs modeling:
- Two-compartment insulin absorption (Isc1→Isc2→plasma)
- Nonlinear gastric emptying (tanh function of stomach load)
- Glucagon counter-regulation
- Hepatic glucose production with insulin suppression
- Peripheral glucose utilization
- Renal clearance

**Status**: ✅ Integrated into `in-silico-bridge.js` via `--engine uva-padova` flag
(commit `9c857e9`, 2025-03-30). Uses low-level Patient API with RK1/2 ODE solver
at 1-minute resolution. Optional sensor noise via `--sensor facchinetti` or
`--sensor vettoretti`. BG range improved from 89–140 (CGMSIM) to 40–210+ mg/dL.
CGMSIM remains the default engine for backward compatibility.

### 2.3 GluPredKit ML Models (Prediction Only)

**Location**: `externals/GluPredKit/glupredkit/models/`

15 models available:

| Type | Models | Can Generate? |
|------|--------|---------------|
| Physics | UVA/Padova (via ReplayBG), Hovorka | No (parameter ID only) |
| Supervised ML | LSTM, TCN, Random Forest, SVR, Ridge, Stacking | No (predict next BG, can't generate traces) |
| Hybrid | Loop (physics-informed features) | No |
| Baseline | Naive/Persistence | No |

**Zero generative models** exist in our ecosystem (no GAN, VAE, diffusion).

### 2.4 Sensor Noise Models (Corruption-Ready)

**Location**: `externals/cgmsim-lib/src/lt1/core/sensors/`

Three published sensor noise models:

| Model | Paper | Structure | Used By |
|-------|-------|-----------|---------|
| Facchinetti2014 | AR(2) measurement + AR(2) common + bias/gain drift | UVA/Padova only |
| Vettoretti2019 | Same structure, G6-specific lower noise | UVA/Padova only |
| Breton2008 | AR(1) + Johnson transform + MA smoothing | UVA/Padova only |

**Key insight**: These noise models are currently ONLY used in the UVA/Padova engine.
They could be extracted and applied retrospectively to real CGM streams as a corruption
tool (see §7).

---

## 3. Methodology 1: Physics-Based Models {#3-physics-based}

### 3.1 How Physics Models Work

Physics-based models encode **known physiology** as differential equations. They take
physiological parameters (insulin sensitivity, absorption rates, body weight) and
compute glucose trajectories deterministically (plus optional sensor noise).

**Generation mechanism**: Forward integration of ODEs from initial conditions.

```
dx/dt = f(x, u, θ)    where:
  x = state vector (glucose pools, insulin compartments, gut contents)
  u = inputs (insulin delivery, carb intake)
  θ = patient parameters (ISF, CR, absorption rates, body weight)
```

### 3.2 Models Available in cgmsim-lib

| Model | Equations | Fidelity | Speed | Notes |
|-------|-----------|----------|-------|-------|
| **UVA/Padova T1DMS** | 18 ODEs | High | Moderate | FDA-accepted for in-silico trials |
| **UVA/Padova Visentin2015** | 18 ODEs + circadian | Higher | Moderate | Time-of-day ISF variation |
| **Cambridge** | ~12 ODEs | Medium | Fast | Simpler insulin model |
| **Cambridge Jacobs2015** | ~12 ODEs + mods | Medium | Fast | Exercise extensions |
| **Roy-Parker 2007** | ~8 ODEs | Low-Medium | Fast | Minimal model |
| **Deichmann 2021** | ~12 ODEs + exercise | Medium | Fast | Exercise-focused extensions |

### 3.3 Strengths

- **Causal**: Can answer "what if" questions (what if insulin dose changes?)
- **Interpretable**: Every parameter has a physiological meaning
- **Compositional**: Can add new mechanisms (exercise, hormones) as new equations
- **No training data required**: Parameters come from clinical literature

### 3.4 Weaknesses

- **Parameter identification**: Requires fitting ~20 parameters per virtual patient
- **Model mismatch**: Real physiology is more complex than any ODE system
- **Missing phenomena**: Stress hormones, immune response, fat metabolism, microbiome effects
- **Calibration gap**: No automated pipeline connecting real data to model parameters
- **Narrow variability**: Default parameters produce narrower BG ranges than real T1D

### 3.5 Improvement Processes for Physics Models

How are physics-based models improved? Three main processes:

**A. Clinical parameter identification**:
1. Recruit subjects, perform controlled experiments (OGTT, clamp studies)
2. Measure glucose, insulin, C-peptide at frequent intervals
3. Fit model parameters to minimize prediction error
4. Publish updated parameter distributions

**B. Model structure expansion**:
1. Identify missing physiological mechanism (e.g., exercise, glucagon)
2. Derive equations from physiology literature
3. Add new state variables and equations to ODE system
4. Re-identify parameters on expanded model
5. Validate against held-out data

**C. Population expansion**:
1. Identify underrepresented populations (children, elderly, pregnancy)
2. Collect new clinical data
3. Identify population-specific parameter distributions
4. Add virtual patient cohorts

---

## 4. Methodology 2: Supervised ML (Prediction, Not Generation) {#4-supervised-ml}

### 4.1 How Supervised ML Models Work

These models learn `f: (BG_history, insulin, carbs, features) → BG_future` from
real data. They predict future BG given context, but cannot generate de novo traces.

### 4.2 Models in GluPredKit

| Model | Architecture | Horizons | Per-Subject? |
|-------|-------------|----------|--------------|
| LSTM | 2-layer LSTM, hidden=128 | 30-360 min | Yes (trained per subject) |
| TCN | Temporal CNN, dilated causal | 30-360 min | Yes |
| Random Forest | 500 trees, max_depth=10 | 30-360 min | Yes |
| SVR | RBF kernel, grid search C/γ | 30-360 min | Yes |
| Ridge | Linear ridge regression | 30-360 min | Yes |
| Stacking | RF + SVR + Ridge ensemble | 30-360 min | Yes |

### 4.3 Why They Can't Generate

Supervised models are **conditional predictors**, not generators:

```
✓ "Given last 4 hours of BG/insulin/carbs, what's BG in 60 minutes?"
✗ "Generate a realistic 48-hour CGM trace for a newly created virtual patient"
✗ "What would BG look like if we changed the insulin dose 3 hours ago?"
```

**Autoregressive generation** (feed predictions back as input) is theoretically possible
but suffers from **compounding error**: small prediction errors accumulate, producing
unrealistic drift or collapse to mean.

### 4.4 Where They Add Value

- **Calibration**: Compare supervised ML predictions against physics model predictions
  to identify systematic model mismatch
- **Residual modeling**: Train ML model on residuals (real - physics prediction) to
  learn what the physics model misses
- **Feature discovery**: Feature importance in RF/Ridge reveals what physiological
  factors the physics model omits (e.g., heart rate, activity)

---

## 5. Methodology 3: Generative Models {#5-generative}

### 5.1 Overview

Generative models learn the **data distribution** and can sample new traces from it.
Unlike supervised models, they don't need explicit input→output mapping.

**Status in our ecosystem**: NONE implemented. This section documents approaches
worth exploring.

### 5.2 Generative Adversarial Networks (GANs)

**Mechanism**: Generator network produces synthetic traces; discriminator network
tries to distinguish real from synthetic. Training optimizes both simultaneously.

**For CGM traces**:
```
Generator: z (random noise) → synthetic 288-point daily CGM trace
Discriminator: CGM trace → P(real)
Conditional GAN: (z, patient_features, treatment_history) → CGM trace
```

**Relevant literature**:
- TimeGAN (Yoon et al., 2019): GAN for realistic time series with temporal dynamics
- RCGAN (Esteban et al., 2017): Recurrent conditional GAN for medical time series
- SigCGAN (Ni et al., 2020): Conditional GAN using signature features

**Strengths**:
- Can capture complex multi-modal distributions
- Produces realistic-looking individual traces
- Conditional variants support "what if" scenarios

**Weaknesses**:
- Mode collapse: generator may only produce a few trace "archetypes"
- Training instability: requires careful hyperparameter tuning
- No causal mechanism: generated traces may violate physiological constraints
  (e.g., BG rising during high insulin without carbs)
- Difficult to evaluate: standard GAN metrics (FID) don't apply directly to time series
- **Cannot guarantee safety-critical edge cases appear** in generated data

### 5.3 Variational Autoencoders (VAEs)

**Mechanism**: Encoder compresses real traces to latent space; decoder reconstructs
traces from latent codes. Latent space is regularized to be Gaussian, enabling sampling.

**For CGM traces**:
```
Encoder: real CGM trace → μ, σ (latent distribution)
Decoder: z ~ N(μ, σ) → reconstructed CGM trace
Conditional: (z, patient_features) → CGM trace
```

**Strengths**:
- More stable training than GANs
- Latent space is interpretable (can interpolate between patient types)
- Explicit density model: can compute P(trace), useful for anomaly detection

**Weaknesses**:
- Tends to produce blurry/smoothed traces (mean of distribution)
- May not capture sharp meal spikes or rapid hypo events well
- Same causal limitation as GANs

### 5.4 Diffusion Models

**Mechanism**: Forward process gradually adds noise to real data over T steps.
Reverse process (learned neural network) removes noise step by step.

**For CGM traces**:
```
Forward: real_trace → slightly_noisy → more_noisy → ... → pure_noise (T steps)
Reverse: pure_noise → slightly_less_noisy → ... → realistic_trace (T steps)
```

**This is directly related to the advisor's "corrupt and reconstruct" recommendation**
(see §7 for detailed exploration).

**Strengths**:
- State-of-the-art generation quality in images, audio, and increasingly time series
- Stable training (no adversarial dynamics)
- Can be conditioned on patient features, treatments, time of day
- Natural framework for "corrupt real data" approach

**Weaknesses**:
- Slow generation (requires many reverse steps)
- Computationally expensive to train
- Requires substantial training data (thousands of trace-days)
- Same causal limitation: may generate physiologically impossible transitions

### 5.5 Neural ODEs / Neural SDEs

**Mechanism**: Replace hand-crafted ODE right-hand-side with a neural network,
trained end-to-end on real data.

```
dx/dt = f_θ(x, u, t)    where f_θ is a neural network
```

**Strengths**:
- Combines ODE structure (continuous dynamics) with data-driven flexibility
- Can incorporate known physics as inductive bias
- Naturally handles irregular time sampling
- Continuous-time: generates at any time resolution

**Weaknesses**:
- Harder to train than standard neural networks (adjoint method)
- May still violate physiological constraints without explicit regularization
- Less interpretable than hand-crafted ODEs

### 5.6 Causal Requirement for Counterfactual Generation

**Critical consideration**: For algorithm validation, we need **counterfactual
generation** — "what would BG be if treatment X had been given instead of treatment Y?"

Only models with **causal structure** can answer this:

| Model Type | Causal? | Counterfactual? | Notes |
|------------|---------|-----------------|-------|
| Physics ODE | ✅ Yes | ✅ Yes | Treatments are explicit inputs |
| GAN | ❌ No | ❌ No | Correlational, not causal |
| VAE | ❌ No | ❌ No | Correlational |
| Diffusion | ❌ No* | ❌ No* | *Unless physics-informed |
| Neural ODE | ⚠️ Partial | ⚠️ Partial | If treatments are inputs |
| Hybrid (§6) | ✅ Yes | ✅ Yes | Physics provides causal backbone |

**Implication**: Pure generative models are useful for generating realistic **background
traces** (CGM behavior between events), but physics-based models are needed for
**treatment response** (how BG responds to specific insulin/carb inputs).

---

## 6. Methodology 4: Hybrid Physics-ML Models {#6-hybrid}

### 6.1 The Core Idea

Use physics-based models for the **causal backbone** (treatment effects) and ML for
the **residual** (everything the physics model gets wrong).

```
BG_predicted = Physics_Model(insulin, carbs, θ) + ML_Residual(features, context)
```

### 6.2 Architecture Variants

**A. Residual learning**:
```
1. Run UVA/Padova with best-fit parameters
2. Compute residual: real_BG - physics_BG
3. Train ML model to predict residual from (features, time, history)
4. Generate: physics_BG + sampled_residual
```

**B. Physics-informed neural network (PINN)**:
```
1. Neural network predicts BG directly
2. Loss function includes physics constraint terms:
   loss = prediction_error + λ × physics_violation_penalty
3. Physics constraints: mass balance, insulin decay kinetics, etc.
```

**C. Latent physics model**:
```
1. VAE/diffusion model generates in latent space
2. Decoder is structured as a physics model
3. Latent variables map to physiological parameters
4. Generation: sample latent → physics decoder → realistic trace
```

**D. Neural ODE with physics priors**:
```
dx/dt = f_known(x, u) + g_θ(x, u, t)
where f_known = known physiological dynamics
      g_θ = learned correction term
```

### 6.3 Why Hybrid Is Recommended

| Requirement | Physics | ML | Hybrid |
|-------------|---------|-----|--------|
| Causal treatment response | ✅ | ❌ | ✅ |
| Realistic variability | ❌ | ✅ | ✅ |
| Edge case generation | ✅ | ❌ | ✅ |
| Counterfactual queries | ✅ | ❌ | ✅ |
| Real-world fidelity | ⚠️ | ✅ | ✅ |
| Interpretability | ✅ | ❌ | ⚠️ |
| Training data needs | None | Large | Moderate |

### 6.4 Implementation Path

```
Phase 1: Integrate UVA/Padova into in-silico-bridge.js (pure physics)
Phase 2: Fit per-subject parameters using ReplayBG (calibrated physics)
Phase 3: Train residual model on (real - calibrated_physics) errors
Phase 4: Generate: calibrated_physics + sampled_residual
Phase 5: Validate hybrid against held-out real data
```

---

## 7. Methodology 5: Corruption-Based Augmentation {#7-corruption}

### 7.1 The Advisor's Recommendation

> "Take the historical data streams that can be collected, and corrupt them somehow."

This approach starts with **real data** and modifies it, rather than generating from
scratch. Several related techniques exist.

### 7.2 Relationship to Diffusion Models

Diffusion models ARE a formal version of "corrupt and reconstruct":

```
Forward process (corruption):
  x_0 (real trace) → x_1 → x_2 → ... → x_T (pure noise)
  x_t = √(α_t) × x_{t-1} + √(1-α_t) × ε    where ε ~ N(0,I)

Reverse process (reconstruction):
  x_T (noise) → x_{T-1} → ... → x_0 (realistic trace)
  Learned: p_θ(x_{t-1} | x_t)
```

The connection:
- **Forward process** = the advisor's "corruption" step
- **Reverse process** = what the model learns = how to generate realistic data
- **Partial corruption** = "corrupt to step t < T, then reconstruct" = data augmentation
  that preserves macro-structure while varying details

### 7.3 Corruption Techniques for CGM Traces

**A. Additive sensor noise (available now)**:
Apply existing sensor noise models from cgmsim-lib retrospectively:
```
corrupted_trace = real_trace + Facchinetti2014_noise(seed)
corrupted_trace = real_trace + Vettoretti2019_noise(seed)
corrupted_trace = real_trace + Breton2008_noise(seed)
```
**Existing code**: `externals/cgmsim-lib/src/lt1/core/sensors/`
- Facchinetti2014: AR(2) measurement noise + AR(2) common component + time-varying bias/gain drift
- Vettoretti2019: Same structure, Dexcom G6-specific parameters (lower noise)
- Breton2008: AR(1) + Johnson transform + moving average smoothing
**Status**: These exist but are ONLY used inside UVA/Padova engine. They can be
extracted as standalone corruption functions.

**B. Treatment perturbation**:
Modify the treatment stream associated with a real CGM trace:
```
corrupted_insulin = real_insulin × (1 + perturbation)  # ±10-50%
corrupted_carbs = real_carbs × (1 + perturbation)      # ±20-100%
corrupted_timing = real_timing + jitter                  # ±15-60 min
```
Then use a physics model to predict what BG **would have been** with corrupted
treatments, creating a counterfactual training pair.

**C. Physiological corruption (time warping)**:
Stretch or compress time segments to simulate faster/slower metabolism:
```
warped_trace = time_warp(real_trace, warp_factor)
# warp_factor > 1: faster metabolism (BG changes happen quicker)
# warp_factor < 1: slower metabolism (BG changes are more gradual)
```

**D. Missing data injection**:
Randomly remove CGM readings to simulate sensor gaps:
```
corrupted_trace = inject_gaps(real_trace, gap_probability=0.05, max_gap_length=6)
```

**E. Event injection/removal**:
Add or remove simulated meals/corrections into real traces using physics model
for the response shape, preserving the real background behavior.

### 7.4 Three-Level Corruption Framework

| Level | Technique | Preserves | Varies | Use Case |
|-------|-----------|-----------|--------|----------|
| **L1: Sensor** | Add CGM noise | True glucose | Measurement | Robustness to noisy sensors |
| **L2: Treatment** | Perturb insulin/carbs | Patient physiology | Treatment decisions | Counterfactual testing |
| **L3: Physiology** | Time warp, parameter shift | Event structure | Response dynamics | Virtual patient variation |

### 7.5 Advantages of Corruption-Based Approaches

1. **Grounded in reality**: Start from real data, so macro-structure is automatically realistic
2. **Controllable**: Know exactly what was changed and by how much
3. **Efficient**: Requires less training data than pure generative models
4. **Causal when combined with physics**: Treatment perturbation + physics model
   produces valid counterfactuals
5. **Scalable**: One real trace → many augmented variants

### 7.6 Limitations

1. **Distribution limited by source data**: Can't generate scenarios not present in
   training data (e.g., if no DKA episodes in training set, corruption can't create one)
2. **Corruption level is subjective**: How much corruption is "realistic"?
3. **Compound corruption**: Multiple simultaneous corruptions may produce unrealistic
   combinations
4. **Requires physics model for treatment corruption**: Pure corruption of CGM without
   corresponding treatment adjustment breaks the causal relationship

### 7.7 Formal Diffusion Model Training for CGM

If we were to train a full diffusion model on CGM traces:

**Training data needed**: ~1,000-10,000 trace-days (see §3.3 of parent doc for
dataset sizes — IOBP2 alone has 332 subjects × ~30 days ≈ 10,000 trace-days)

**Architecture choices**:
- **TimeGrad** (Rasul et al., 2021): Autoregressive diffusion for time series
- **CSDI** (Tashiro et al., 2021): Conditional score-based diffusion for imputation
- **SSSD** (Alcaraz & Strodthoff, 2023): Structured state space diffusion model

**Training process**:
1. Normalize CGM traces to 5-min resolution, segment into 24-hour windows
2. Forward process: add Gaussian noise at T=1000 steps
3. Train U-Net or transformer to predict noise at each step
4. Condition on: patient demographics, mean TIR, treatment intensity, time of day

**Generation**:
```
z ~ N(0, I)                    # Start from noise
for t in T, T-1, ..., 1:
    z = denoise_step(z, t, condition)  # Progressively denoise
return z                         # Realistic CGM trace
```

**Partial corruption variant** (advisor's approach):
```
real_trace → corrupt to step t=200 → denoise from t=200
# Preserves global structure, varies local details
# Lower t = more similar to original; higher t = more variation
```

---

## 8. UVA/Padova: Validation History and Improvement {#8-uva-padova}

### 8.1 What Makes It "Known Good"

The UVA/Padova Type 1 Diabetes Simulator is the most widely validated physics-based
glucose simulator in the field. Its credibility rests on four pillars:

#### Pillar 1: Published Physiology (Decades of Research)

The model encodes glucose-insulin dynamics from controlled clinical experiments:

| Component | Equations | Source |
|-----------|-----------|--------|
| Glucose kinetics | 2-compartment (plasma + interstitial) | Dalla Man, IEEE TBME, 2007 |
| Insulin kinetics | 2-compartment subcutaneous absorption | Dalla Man, IEEE TBME, 2007 |
| Gastric emptying | Nonlinear (tanh of stomach load) | Dalla Man, IEEE TBME, 2006 |
| Hepatic glucose production | Insulin-suppressed + glucagon-stimulated | Dalla Man, JDST, 2014 |
| Glucagon dynamics | Counter-regulatory response | Lv, 2013 |
| Renal clearance | Threshold-based glucose excretion | Dalla Man, IEEE TBME, 2007 |

Every parameter is sourced from published clinical studies, not ad-hoc fitting:
```
// From UvaPadova_T1DMS.ts, lines 340-382
VG: 1.88 dl/kg           // Dalla Man, IEEE TBME, 2007
k1: 0.065 1/min          // Dalla Man, IEEE TBME, 2007
k2: 0.079 1/min          // Dalla Man, IEEE TBME, 2007
kmax: 0.0558 1/min       // Dalla Man, IEEE TBME, 2007
kmin: 0.008 1/min        // Dalla Man, IEEE TBME, 2007
```

#### Pillar 2: Gold-Standard Clinical Validation

Parameters were identified from:
- **Oral Glucose Tolerance Tests (OGTT)**: Controlled carb loads with frequent blood sampling
- **Euglycemic-Hyperinsulinemic Clamps**: Gold standard for measuring insulin sensitivity
- **Mixed Meal Tests**: Standardized meals (e.g., 30g carb) with time-course measurements

The 2006 paper specifically titled: "A System Model of Oral Glucose Absorption:
**Validation on Gold Standard Data**"

#### Pillar 3: FDA Acceptance as In-Silico Testing Platform

The UVA/Padova simulator (as T1DMS — Type 1 Diabetes Metabolic Simulator) was
**accepted by the FDA as a substitute for animal trials** in pre-clinical testing
of closed-loop insulin delivery algorithms. This is a significant regulatory milestone:

- Used as primary pre-clinical testing tool for multiple AP (Artificial Pancreas)
  clinical trials
- Enabled the Control-IQ (Tandem) and Medtronic 670G/780G development pipelines
- The 2014 paper ("New Features") extended the model specifically to support
  regulatory submissions

**Important nuance**: The FDA accepted the simulator as **a substitute for animal
trials**, not as a substitute for human clinical trials. It demonstrates that an
algorithm is safe enough to proceed to human testing, not that it's safe for
deployment.

#### Pillar 4: Community Adoption

| Platform | Usage |
|----------|-------|
| cgmsim-lib (our ecosystem) | Full 18-ODE implementation |
| GluPredKit (via ReplayBG) | Per-subject parameter identification |
| LoopInsighT1 | Closed-loop simulation |
| OpenAPS Autotune | Reference model for parameter identification |
| Multiple AP clinical trials | Pre-clinical algorithm validation |

### 8.2 Known Limitations

Despite its validation, the model has documented issues:

| Limitation | Impact | Evidence |
|------------|--------|----------|
| **Meal size extrapolation** | Model was developed for 30g meals; other sizes use undocumented corrections | `UvaPadova_T1DMS.ts:221-229` |
| **No exercise model** (base) | Exercise is a major glucose driver, absent from core equations | Extension in Deichmann2021 |
| **Glucagon parameters uncertain** | Multiple TODO comments for glucagon-related parameters | `UvaPadova_T1DMS.ts:387, 405-442` |
| **No stress/illness** | Cortisol, growth hormone, catecholamine effects not modeled | Missing entirely |
| **No fat/protein** | Only carbohydrate absorption modeled | Missing entirely |
| **Narrow population** | Default parameters represent average adult T1D | No pediatric, geriatric, pregnancy |
| **Insulin secretion** | Uses equilibrium value; problematic for T1D with zero secretion | `UvaPadova_T1DMS.ts:260-262` |
| **Sensor model separate** | BG-to-CGM delay and noise modeled separately | In `/sensors/` directory |

### 8.3 How Physics Models Are Improved

Three parallel improvement tracks:

#### Track A: Clinical Data → Parameter Refinement

```
1. Design clinical protocol
   - Controlled meals at varying sizes
   - Insulin dose-response curves
   - Exercise challenges
   
2. Collect data
   - Frequent blood glucose sampling (every 5-15 min)
   - Plasma insulin measurements
   - CGM in parallel for sensor model calibration
   - Activity, HR, other covariates
   
3. Parameter identification
   - Bayesian estimation (MCMC or particle filter)
   - Maximum likelihood on time-course data
   - Per-subject and population-level fits
   
4. Validate
   - Leave-one-out cross-validation
   - Prediction on held-out meal/insulin challenges
   - Compare population statistics with epidemiological data
   
5. Publish and integrate
   - Updated parameter distributions
   - New virtual patient cohorts
```

**Tools available**: ReplayBG (in GluPredKit) performs Bayesian particle filter
parameter identification from real CGM data. This is the most practical path
for our ecosystem.

#### Track B: Model Structure Expansion

```
1. Identify missing mechanism
   - Literature review of glucose physiology
   - Analysis of model residuals (what patterns does the model miss?)
   - Clinical expert input
   
2. Derive equations
   - Physiological mechanism → differential equations
   - Example: exercise model adds:
     - Muscle glucose uptake rate ∝ exercise intensity
     - Insulin sensitivity amplification ∝ exercise duration
     - Hepatic glucose release ∝ glycogen depletion
   
3. Integrate with existing model
   - Add new state variables
   - Connect to existing compartments
   - Ensure mass balance is maintained
   
4. Re-identify all parameters
   - New mechanism parameters from dedicated clinical data
   - Existing parameters may need adjustment
```

**Example**: The Deichmann2021 model in cgmsim-lib adds exercise effects to the
Cambridge model: `externals/cgmsim-lib/src/lt1/core/models/Deichmann2021.ts`

#### Track C: Population Expansion via Retrospective Data

```
1. Obtain real-world diabetes data (see parent doc §3.3 for datasets)
   - OpenAPS Data Commons: 142 subjects
   - IOBP2: 332 subjects
   - T1DEXI: 414 subjects
   
2. Per-subject parameter identification
   - Run ReplayBG or similar on each subject's data
   - Extract: ISF, CR, basal, absorption rate, body weight
   
3. Build population distributions
   - Joint distribution of parameters across subjects
   - Capture correlations (e.g., high ISF correlates with low weight)
   - Identify clusters (children, adults, elderly; MDI, pump; etc.)
   
4. Generate virtual patients by sampling
   - Sample parameter vectors from identified distribution
   - Each sample = one virtual patient
   - Run UVA/Padova with sampled parameters
```

**This is the recommended improvement path for our ecosystem** because it:
- Uses data we can already access
- Uses tools already available (ReplayBG, GluPredKit parsers)
- Doesn't require new clinical trials
- Produces calibrated virtual patients automatically

### 8.4 Validation Metrics for Physics Models

How do you know if improvements actually help?

| Metric | What It Measures | Target |
|--------|-----------------|--------|
| **RMSE** (per-subject) | Point prediction accuracy | < 25 mg/dL at 60-min horizon |
| **BG distribution match** | Wasserstein distance real vs sim | W₁ < 5 mg/dL |
| **TIR match** | Time-in-range similarity | Within 5% of real |
| **Hypo frequency** | Events < 54 mg/dL per week | Within ±0.5 of real |
| **Meal response shape** | DTW on 4-hour post-meal windows | DTW < 15 |
| **ACF match** | Temporal dynamics | RMSE < 0.05 over lags 1-72 |
| **Event counts** | Hyper/hypo/meal events per day | Within 20% of real |

---

## 9. Comparison Matrix {#9-comparison}

### 9.1 Full Methodology Comparison

| Criterion | CGMSIM (current) | UVA/Padova | GAN/VAE | Diffusion | Neural ODE | Hybrid | Corruption |
|-----------|-----------------|------------|---------|-----------|------------|--------|------------|
| **Realism** | ❌ Low | ⚠️ Medium | ✅ High* | ✅ High* | ⚠️ Medium | ✅ High | ✅ High |
| **Causal** | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ⚠️ Partial | ✅ Yes | ⚠️ Partial |
| **Counterfactual** | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ⚠️ Partial | ✅ Yes | ✅ Yes** |
| **Edge cases** | ⚠️ Limited | ⚠️ Limited | ❌ None | ❌ None | ❌ None | ✅ Good | ⚠️ Limited |
| **Training data** | None | None | ~5k days | ~5k days | ~2k days | ~1k days | ~100 days |
| **Implementation** | ✅ Done | ⚠️ Exists | ❌ None | ❌ None | ❌ None | ❌ None | ⚠️ Partial |
| **Interpretable** | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ❌ No | ⚠️ Partial | ✅ Yes |
| **Speed** | ✅ Fast | ⚠️ Moderate | ✅ Fast*** | ❌ Slow | ⚠️ Moderate | ⚠️ Moderate | ✅ Fast |
| **Regulatory** | ❌ No | ✅ FDA-accepted | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No |

*After sufficient training; **When combined with physics model for treatment effects;
***After training

### 9.2 Recommended Combination

No single methodology is sufficient. The recommended architecture combines:

```
┌──────────────────────────────────────────────────────────┐
│                    Generation Pipeline                     │
│                                                           │
│  Real Data ──→ Parameter ID ──→ Calibrated UVA/Padova    │
│       │              │                    │                │
│       │              ▼                    ▼                │
│       │        Population         Physics Traces          │
│       │        Distributions            │                 │
│       │              │                  │                 │
│       ▼              ▼                  ▼                 │
│  Corruption    Virtual Patient    ML Residual Model       │
│  Augmentation   Sampling               │                 │
│       │              │                  │                 │
│       ▼              ▼                  ▼                 │
│  Augmented      Physics           Hybrid Traces           │
│  Real Traces    Traces           (Physics + Residual)     │
│       │              │                  │                 │
│       └──────────────┼──────────────────┘                 │
│                      ▼                                    │
│              Validation Against                           │
│              Statistical Fingerprints                     │
│                      │                                    │
│                      ▼                                    │
│              Algorithm Testing                            │
└──────────────────────────────────────────────────────────┘
```

---

## 10. Recommended Exploration Roadmap {#10-roadmap}

### Phase 1: Foundation (Use What Exists)

**Goal**: Get UVA/Padova producing realistic traces

| Task | Effort | Dependencies |
|------|--------|-------------|
| Integrate UVA/Padova engine into `in-silico-bridge.js` | Medium | ODE state persistence |
| Extract sensor noise models as standalone corruption tools | Low | None |
| Apply Facchinetti/Vettoretti noise to real traces | Low | Extracted noise models |
| Validate UVA/Padova output against real data fingerprints | Medium | Fingerprint engine (parent §3) |

### Phase 2: Calibration (Make Physics Match Reality)

**Goal**: Per-subject parameter identification

| Task | Effort | Dependencies |
|------|--------|-------------|
| Integrate ReplayBG parameter identification pipeline | Medium | Phase 1 |
| Run per-subject fitting on OhioT1DM (12 subjects, immediate access) | Low | ReplayBG |
| Build population parameter distributions | Medium | Per-subject fits |
| Generate calibrated virtual patients | Low | Distributions |
| Validate: do calibrated traces match Wasserstein/ACF targets? | Medium | Calibrated patients |

### Phase 3: Augmentation (Corruption-Based, Advisor's Approach)

**Goal**: Multiply real data with controlled corruption

| Task | Effort | Dependencies |
|------|--------|-------------|
| Build treatment perturbation pipeline (dose ±%, timing jitter) | Medium | None |
| Physics-model counterfactual: real data + modified treatment → new BG | High | Phase 1 |
| Time-warping augmentation for metabolic variability | Low | None |
| Missing data injection for robustness testing | Low | None |
| Validate: do augmented traces remain within fingerprint bounds? | Medium | Fingerprint engine |

### Phase 4: Hybrid Model (Physics + ML)

**Goal**: Close the gap between physics and reality

| Task | Effort | Dependencies |
|------|--------|-------------|
| Compute residuals: real_BG - calibrated_physics_BG | Low | Phase 2 |
| Train residual model (start with Ridge/RF, then LSTM) | Medium | Residuals |
| Characterize residual patterns (meal-related? time-of-day? exercise?) | Medium | Residual model |
| Generate hybrid traces: calibrated physics + sampled residual | Medium | Residual model |
| Validate: do hybrid traces match ALL 4 statistical layers? | High | Full fingerprint engine |

### Phase 5: Generative Models (Research Exploration)

**Goal**: Determine if pure generative adds value beyond hybrid

| Task | Effort | Dependencies |
|------|--------|-------------|
| Prototype TimeGrad or CSDI on CGM traces | High | ~5k trace-days |
| Compare generation quality: generative vs hybrid vs corruption | High | Phase 4 |
| Physics-informed diffusion: condition on treatment stream | Very High | Research |
| Evaluate: does generative produce better edge cases? | High | All phases |

---

## 11. Open Questions {#11-open-questions}

### Generation Methodology

1. **Is corruption sufficient, or do we need full generative models?**
   Corruption preserves real data structure but can't create entirely new scenarios.
   Full generative models can create novel scenarios but may not be physiologically valid.

2. **How do we validate counterfactual traces?**
   We can't observe the true counterfactual (what would have happened with different
   treatment). How do we evaluate the quality of counterfactual generation?

3. **What's the minimum data for hybrid model training?**
   ReplayBG needs ~36 hours per subject for parameter identification. How many
   subjects do we need for a useful population distribution?

4. **Can diffusion models learn physiological constraints?**
   If we condition on treatment streams, can a diffusion model learn that insulin
   should decrease BG? Or do we need explicit physics constraints?

### UVA/Padova Specific

5. **Which extensions should we prioritize?**
   The Deichmann2021 exercise model exists. Should we integrate it before or after
   calibrating the base model?

6. **How do we handle the glucagon TODOs?**
   Multiple parameters are marked as uncertain. Should we disable glucagon until
   parameters are validated, or use the current defaults?

7. **Is the 30g meal assumption problematic?**
   The scaling correction for non-30g meals is undocumented. How much error does
   this introduce for typical T1D meals (5-150g carbs)?

### Safety and Edge Cases

8. **How do we generate safety-critical edge cases?**
   Physics models can be pushed to extreme parameters, but are the resulting traces
   physiologically plausible? Who validates edge case realism?

9. **What scenarios must be tested that real data may never contain?**
   DKA, severe hypoglycemia, pump failures, sensor compression artifacts — these
   are critical safety scenarios that may not appear in observational data.

10. **How do we test for scenarios we haven't thought of?**
    Adversarial testing: can we train a model to find algorithm failure modes, then
    generate targeted traces that expose weaknesses?

---

## 12. References {#12-references}

### Physics Models

- Dalla Man C, et al. "A System Model of Oral Glucose Absorption: Validation on
  Gold Standard Data." IEEE TBME, 2006.
- Dalla Man C, et al. "Meal Simulation Model of the Glucose-Insulin System."
  IEEE TBME, 2007.
- Dalla Man C, et al. "The UVA/PADOVA Type 1 Diabetes Simulator: New Features."
  JDST, 2014.
- Visentin R, et al. "The UVA/Padova Type 1 Diabetes Simulator Goes From Single
  Meal to Single Day." JDST, 2015.
- Deichmann J, et al. "A comprehensive model of glucose, insulin and free fatty
  acid dynamics including exercise." Plos One, 2021.

### Sensor Noise Models

- Facchinetti A, et al. "Modeling the glucose sensor error." IEEE TBME, 2014.
- Vettoretti M, et al. "Development of an error model for a factory-calibrated
  continuous glucose monitoring sensor." Sensors, 2019.
- Breton M, Kovatchev B. "Analysis, modeling, and simulation of the accuracy
  of continuous glucose sensors." JDST, 2008.

### Generative Models for Time Series

- Yoon J, et al. "Time-series Generative Adversarial Networks." NeurIPS, 2019.
- Esteban C, et al. "Real-valued (Medical) Time Series Generation with Recurrent
  Conditional GANs." arXiv, 2017.
- Rasul K, et al. "Autoregressive Denoising Diffusion Models for Multivariate
  Probabilistic Time Series Forecasting." ICML, 2021.
- Tashiro Y, et al. "CSDI: Conditional Score-based Diffusion Models for
  Probabilistic Time Series Imputation." NeurIPS, 2021.
- Alcaraz J, Strodthoff N. "Diffusion-based Time Series Imputation and
  Forecasting with Structured State Space Models." TMLR, 2023.

### Neural ODEs

- Chen R, et al. "Neural Ordinary Differential Equations." NeurIPS, 2018.
- Rubanova Y, et al. "Latent ODEs for Irregularly-Sampled Time Series." NeurIPS, 2019.

### Hybrid Physics-ML

- Raissi M, et al. "Physics-informed neural networks." J Comp Physics, 2019.
- Karniadakis GE, et al. "Physics-informed machine learning." Nature Reviews Physics, 2021.

### Datasets Referenced (Full Catalog in Parent Doc §3.3)

- IOBP2: 332 subjects, 9.7M data points (iLet Bionic Pancreas trial)
- T1DEXI: 414 pump users with rich exercise metadata
- OpenAPS Data Commons: 142 subjects with real AID system data
- OhioT1DM: 12 subjects (immediate access, commonly used benchmark)

---

*Cross-references: `docs/architecture/simulation-validation-architecture.md` (parent),
`docs/architecture/therapy-optimization-feature-pipeline.md` (sibling)*
