# ML Composition Architecture: Disambiguation & Roadmap

## Purpose

This document disambiguates two complementary ML toolkits (`cgmencode` and `aid-autoresearch`) and synthesizes advisor recommendations into a unified architecture for anticipatory diabetes management. It defines which workspace owns which objectives, how techniques compose across layers, and what decision-modeling and policy capabilities are needed beyond the current foundation.

**Audience**: Team members working across either workspace who need to understand how the pieces fit together.

---

## 1. The Two Toolkits: Different Problems, Shared Infrastructure

### 1.1 aid-autoresearch (this workspace)

**Primary objective**: Validate that dosing algorithms (oref0, Loop, Trio) produce correct decisions across realistic simulated scenarios.

| Capability | Status | Technique |
|-----------|--------|-----------|
| Physics simulation (UVA/Padova 18-ODE) | ✅ Done | Compartmental ODE |
| CGM scenario generation (7 scenarios × 3 profiles) | ✅ Done | Physics-based |
| Sensor noise models (Facchinetti, Vettoretti) | ✅ Done | AR(1) stochastic |
| Algorithm scoring (MAE, composite 6-metric) | ✅ Done | Statistical |
| Cross-validation (oref0-JS vs AAPS-JS vs Swift) | ✅ Done | Deterministic replay |
| Hyperparameter mutation search | ✅ Done | Evolutionary/grid |
| Statistical fingerprinting pipeline | ❌ Designed | Wasserstein/DTW/ACF |
| Calibration against real datasets | ❌ Designed | Hierarchical optimization |
| Hybrid physics-ML residual model | ❌ Research | LSTM on (actual − physics) |

**Core question answered**: "Does the algorithm compute the correct rate for this glucose-insulin state?"

### 1.2 cgmencode (t1pal-mobile-workspace)

**Primary objective**: Learn data-driven representations of glucose-insulin dynamics for personalized dosing guidance.

| Capability | Status | Technique |
|-----------|--------|-----------|
| Nightscout fixture → 8-feature vectors | ✅ Done | FixtureEncoder pipeline |
| Self-supervised representation (6 pretext tasks) | ✅ Done | Masked Transformer AE |
| Scenario generation | ✅ Prototype | VAE (32D latent) |
| Counterfactual dosing simulation | ✅ Prototype | Conditioned Transformer |
| Uncertainty quantification | ✅ Prototype | 1D DDPM Diffusion |
| Noise-invariant features | ✅ Prototype | SimCLR contrastive |
| Multi-patient training | ❌ Blocked | Need 100K+ vectors |
| CoreML mobile deployment | ❌ Phase 3 | Swift integration |

**Core question answered**: "Given this patient's history, what happens if we dose X units?"

### 1.3 The Disambiguation

These toolkits are **not competing**—they occupy different layers of the same stack:

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 4: DECISION & POLICY (neither toolkit — new work)    │
│  "When should we suggest an override? What type? How early?" │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: LEARNED DYNAMICS (cgmencode)                      │
│  "What will glucose do if we take action A?"                │
│  Conditioned Transformer · VAE · Diffusion · Contrastive    │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: CALIBRATION & RESIDUAL (shared bridge)            │
│  "How far is physics from reality? What's missing?"         │
│  Fingerprinting · Wasserstein distance · Residual ML        │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: PHYSICS SIMULATION (aid-autoresearch)             │
│  "Given insulin + carbs + parameters, what BG trajectory?"  │
│  UVA/Padova · cgmsim-lib · Sensor noise · Algorithm replay  │
└─────────────────────────────────────────────────────────────┘
```

**Key principle**: Physics (Layer 1) provides causal grounding that pure ML cannot. ML (Layer 3) provides speed, personalization, and uncertainty that physics alone cannot. Calibration (Layer 2) connects them. Decision modeling (Layer 4) consumes them all.

---

## 2. Advisor Recommendations: Anticipatory Context-Aware Management

### 2.1 Vision Statement

The core goal is to shift diabetes management from reactive, moment-to-moment intervention into **anticipatory, context-aware support** that works alongside existing controllers (Loop, oref0). The system should:

- **Detect** short-term events (meals, exercise, glucose excursions) — minutes to hours
- **Recognize** medium-term patterns (daily routines, sleep transitions) — hours to a day
- **Identify** long-term physiological drift (basal/ISF/CR changes, hormone cycles) — days to weeks
- **Infer** when overrides are needed without requiring button presses
- **Schedule** interventions ahead of time using learned behavior + contextual signals

### 2.2 Three Time Horizons

| Horizon | Window | Examples | Primary Technique |
|---------|--------|----------|-------------------|
| Immediate | Minutes → 2 hours | Meal detection, hypo prediction, exercise onset | Sequence classification (Transformer, TCN) |
| Daily | 2 hours → 24 hours | Sleep transition, work vs weekend, routine prediction | Pattern matching + calendar context |
| Longitudinal | Days → weeks | Basal drift, ISF seasonal change, hormone cycles, illness | State-space / Bayesian filtering |

### 2.3 Key Advisor Additions Beyond Current Work

| Addition | Rationale | Priority |
|----------|-----------|----------|
| **Explicit decision modeling** | Current models predict glucose but don't predict *when an override should occur* | High |
| **Supervised override classifiers** | Train on historical override behavior: type, timing, duration | High |
| **Bayesian / state-space for latent drift** | Track slow physiological changes with uncertainty | Medium |
| **Policy layer** (supervised → bandits → offline RL) | Evaluate and select among candidate overrides safely | Medium |
| **Calendar/activity context signals** | Time-of-day already in cgmencode; extend to weekday, travel, calendar | Low |
| **Constrained offline RL** | Learn optimal override policies from historical data without online risk | Future |

---

## 3. Technique Inventory: What Exists, What's Proposed, What's New

### 3.1 Representation Learning — ✅ EXISTS (cgmencode)

**What it does**: Encodes 6-hour glucose-insulin windows into compact representations via masked self-supervised learning.

**Techniques in use**:
- Transformer Autoencoder (64D, 2 layers, 4 heads)
- 6 pretext tasks: fill_actions, fill_readings, forecast, denoise, random_patch, shuffled_mask
- Circadian encoding (sin/cos hour-of-day)

**Serves objectives**: Feature extraction backbone for all downstream tasks.

**Gap**: Trained on ~1,000 vectors from single patient. Needs 100K+ from diverse population.

### 3.2 Generative / Scenario Modeling — ✅ PROTOTYPE (cgmencode + aid-autoresearch)

**cgmencode models**:
- **VAE** (32D Gaussian latent): Generates synthetic scenarios by sampling latent space. Produces "blurred" traces — good for augmentation, weak on sharp events.
- **1D DDPM Diffusion**: Generates probability clouds (50+ samples). Captures one-to-many dynamics. Current implementation simplified.

**aid-autoresearch simulation**:
- **UVA/Padova 18-ODE**: Causally valid BG trajectories. Deterministic per parameter set. Cannot learn from data directly.
- **Corruption-based augmentation**: Designed (§7 of cgm-trace-generation-methodologies.md) but not coded. Perturb real traces using physics for counterfactuals.

**The composition**: Physics generates the causal backbone → VAE/Diffusion add behavioral variability → Corruption augments edge cases from real data. These are **not alternatives but layers**.

### 3.3 Counterfactual / Digital Twin — ✅ PROTOTYPE (cgmencode)

**Conditioned Transformer**: Takes `(history[72×8], future_actions[12×3])` → predicts `future_glucose[12]`.

**How it differs from physics**:
- **UVA/Padova**: `P(BG | insulin, carbs, θ_physiology)` — requires known physiological parameters
- **Conditioned Transformer**: `P(BG | history, future_actions)` — learns parameters implicitly from data

**Composition path**: Train Conditioned Transformer on UVA/Padova output first (unlimited synthetic data), then fine-tune on real patient data (transfer learning). This is a standard sim-to-real approach.

### 3.4 Uncertainty Quantification — ✅ PROTOTYPE (cgmencode)

**Diffusion-based probability clouds**: Generate 50+ samples for a given state → compute percentile bands → estimate P(hypo | dose).

**Value for decision layer**: The policy layer (§3.7) needs uncertainty estimates to constrain actions. A dose with 15% P(BG < 54) should be rejected even if mean prediction looks good.

### 3.5 Statistical Fingerprinting & Calibration — ❌ DESIGNED (aid-autoresearch)

**What it does**: Compute 4-tier distribution fingerprints from real data streams, then optimize UVA/Padova parameters to minimize Wasserstein/DTW/ACF distance.

**The three deliverables** (from simulation-validation-architecture.md §3):
1. **Fingerprint engine**: Extract population-level BG distribution statistics
2. **Scenario classification**: Common (70-180, meals, sleep), edge (DKA, compression lows, pump failures), impossible (negative BG, 2000 mg/dL)
3. **Calibrated parameter sets**: UVA/Padova θ that reproduces real population statistics

**Serves objectives**: Grounds the physics engine in reality; provides the training data pipeline for ML layers above.

### 3.6 Decision Modeling — ❌ NEW (advisor recommendation)

**The gap**: No model in either toolkit predicts *when an override should occur*. cgmencode predicts glucose trajectories; aid-autoresearch validates algorithm decisions. Neither asks "should we suggest 'Eating Soon' override at 11:45am?"

**Proposed approach** (progressive complexity):

| Stage | Technique | Input | Output | Training Data |
|-------|-----------|-------|--------|---------------|
| 1. Event classifier | Gradient-boosted trees (XGBoost/LightGBM) | 1-hour window features | Event type (meal, exercise, sleep, none) | Historical events with timestamps |
| 2. Temporal sequence classifier | TCN or Transformer head on cgmencode embeddings | 6-hour encoded history | (event_type, time_until_event, confidence) | Same, with timing labels |
| 3. Multitask model | Shared Transformer encoder → 3 prediction heads | Encoded history + context | (event_type, timing, duration, intensity) | Override history + outcomes |
| 4. Joint prediction-decision | Conditioned Transformer + decision head | History + candidate overrides | (glucose_trajectory, override_score) | Counterfactual evaluation |

**Key insight from advisors**: Start simple (Stage 1 with tabular features) before building complex architectures. Gradient-boosted trees trained on historical override logs can provide surprisingly strong baselines.

### 3.7 Policy Layer — ❌ NEW (advisor recommendation)

**What it does**: Given a predicted event and a set of candidate overrides, select the safest effective action.

**Progressive approach**:

1. **Supervised learning** (immediate): Train on historical user override decisions. "When the user saw this pattern, they chose X override Y minutes before the meal." Limitation: learns to imitate the user, including their mistakes.

2. **Contextual bandits** (near-term): Given state → propose override → observe outcome. Uses Thompson sampling or UCB to balance exploration/exploitation. Safer than full RL because actions don't change future state distribution much (the controller still runs underneath).

3. **Constrained offline RL** (future): Learn from logged data without online interaction. Conservative Q-learning (CQL) or Decision Transformer. **Critical constraint**: Must never suggest an action worse than "do nothing" (safety floor).

**Safety architecture**:
```
Candidate Override → Physics Check (UVA/Padova "will this cause hypo?")
                   → Uncertainty Check (Diffusion P(hypo) < threshold?)
                   → Controller Check (does Loop/oref0 agree this is safe?)
                   → Human Approval (notify with confidence, await accept/reject)
```

### 3.8 Latent Physiological State Tracking — ❌ NEW (advisor recommendation)

**The problem**: Insulin sensitivity, carb absorption, and basal needs change over hours to weeks due to illness, hormones, stress, exercise adaptation, weight change. Current models treat these as static.

**Proposed techniques**:

| Approach | Mechanism | Advantage | Limitation |
|----------|-----------|-----------|------------|
| **State-space model** (linear Kalman filter) | Hidden state `z_t` evolves: `z_{t+1} = Az_t + noise`; observations `y_t = Cz_t + noise` | Fast, interpretable, uncertainty for free | Assumes linear dynamics |
| **Nonlinear state-space** (Extended Kalman / particle filter) | Same but `f(z)` nonlinear | Captures nonlinear drift | Harder to train, particle collapse |
| **Deep state-space** (structured SSM / S4) | Learned transition matrix via neural network | Captures complex drift patterns | Needs more data, less interpretable |
| **Bayesian online learning** | Update posterior over ISF/CR/basal each day | Principled uncertainty, degrades gracefully | Requires prior specification |

**Composition with cgmencode**: The VAE latent space (32D) already captures something like "physiological phenotype." Adding an explicit temporal transition model over this latent space creates a **deep state-space model** that tracks drift:

```
z_t = VAE_encode(window_t)           # Current physiological state
z_{t+1} = f_θ(z_t) + process_noise   # State evolution (learned)
ŷ_{t+1} = Decoder(z_{t+1})           # Predicted next window
```

**Existing related work**: oref0's `autosens` already does a simple version of this — it computes a rolling sensitivity multiplier from deviations. The ML version would be richer (multivariate, uncertainty-aware, longer memory).

---

## 4. Composition Architecture: How the Layers Connect

### 4.1 Data Flow

```
                    ┌──────────────────────────────┐
                    │   REAL PATIENT DATA STREAMS   │
                    │  Nightscout · CGM · Pump · HR │
                    └──────────┬───────────────────┘
                               │
                    ┌──────────▼───────────────────┐
                    │   LAYER 2: CALIBRATION        │
                    │                               │
                    │  Fingerprint extraction        │
                    │  Distance: Wasserstein/DTW/ACF │
         ┌─────────┤  Parameter optimization        │
         │         │  Scenario classification       │
         │         └──────────┬───────────────────┘
         │                    │
         │         ┌──────────▼───────────────────┐
         │         │   LAYER 1: PHYSICS ENGINE     │
         │         │                               │
         │         │  UVA/Padova 18-ODE            │
         │         │  + Calibrated patient params   │
         │         │  + Sensor noise (Facchinetti)  │
         │         │  + Corruption augmentation     │
         │         │                               │
         │         │  Output: Unlimited synthetic   │
         │         │  CGM traces (causally valid)   │
         │         └──────────┬───────────────────┘
         │                    │
         │    ┌───────────────┼───────────────────┐
         │    │               │                   │
         │    ▼               ▼                   ▼
         │  ┌─────────┐  ┌────────────┐  ┌──────────────┐
         │  │Algorithm │  │ cgmencode  │  │  Decision    │
         │  │Validation│  │ Training   │  │  Model       │
         │  │(oref0,   │  │(Transf AE, │  │  Training    │
         │  │ Loop,    │  │ VAE, Diff, │  │  (XGBoost,   │
         │  │ Trio)    │  │ Conditioned│  │   TCN, RL)   │
         │  └────┬─────┘  └─────┬──────┘  └──────┬───────┘
         │       │              │                 │
         │       ▼              ▼                 ▼
         │  ┌─────────────────────────────────────────────┐
         │  │   LAYER 3+4: INFERENCE PIPELINE             │
         │  │                                             │
         │  │  Encoder(history) → latent state            │
         │  │  + State tracker(latent_t-1 → latent_t)     │
         │  │  + Event classifier(latent → override?)     │
         │  │  + Conditioned sim(latent + action → BG)    │
         │  │  + Uncertainty(diffusion → P(hypo))         │
         │  │  + Policy(candidates → best safe action)    │
         │  │  + Physics guard(UVA/Padova safety check)   │
         │  └──────────────────┬──────────────────────────┘
         │                     │
         │                     ▼
         │  ┌──────────────────────────────────────────────┐
         │  │  USER-FACING OUTPUT                          │
         │  │                                              │
         │  │  "Meal likely in ~30min. Suggest 'Eating     │
         │  │   Soon' override now? (82% confidence,       │
         │  │   based on your Tuesday pattern)"            │
         │  │                                              │
         │  │  "Current ISF trending 15% lower than last   │
         │  │   week — consider review with endo"          │
         │  └──────────────────────────────────────────────┘
         │
         └──── FEEDBACK: Accepted/rejected overrides,
               actual outcomes → retrain all layers
```

### 4.2 Workspace Ownership

| Component | Owner | Workspace |
|-----------|-------|-----------|
| UVA/Padova engine, in-silico-bridge | aid-autoresearch | `rag-nightscout-ecosystem-alignment` |
| Algorithm validation (oref0/Loop/Trio) | aid-autoresearch | `rag-nightscout-ecosystem-alignment` |
| Statistical fingerprinting, calibration | aid-autoresearch | `rag-nightscout-ecosystem-alignment` |
| Scenario classification (common/edge/impossible) | aid-autoresearch | `rag-nightscout-ecosystem-alignment` |
| Conformance vectors, scoring | aid-autoresearch | `rag-nightscout-ecosystem-alignment` |
| Feature encoding (FixtureEncoder, 8-feature vector) | cgmencode | `t1pal-mobile-workspace` |
| Self-supervised representation learning | cgmencode | `t1pal-mobile-workspace` |
| Generative models (VAE, Diffusion) | cgmencode | `t1pal-mobile-workspace` |
| Conditioned Transformer (digital twin) | cgmencode | `t1pal-mobile-workspace` |
| Contrastive learning (noise robustness) | cgmencode | `t1pal-mobile-workspace` |
| CoreML mobile inference | cgmencode | `t1pal-mobile-workspace` |
| Decision modeling (override classifier) | **NEW** — TBD | Likely t1pal-mobile-workspace |
| Policy layer (override selection) | **NEW** — TBD | Likely t1pal-mobile-workspace |
| State tracking (latent drift) | **NEW** — shared | VAE encoder from cgmencode + transition model |
| Context signals (calendar, activity) | **NEW** — TBD | Likely t1pal-mobile-workspace |

### 4.3 Integration Points (Bridges Between Workspaces)

| Bridge | From → To | Mechanism | Status |
|--------|-----------|-----------|--------|
| Synthetic training data | aid-autoresearch → cgmencode | in-silico-bridge generates SIM-* vectors → cgmencode FixtureEncoder ingests | ❌ Not wired |
| Calibrated patient parameters | aid-autoresearch → cgmencode | Fingerprint-optimized UVA/Padova params → realistic synthetic diversity | ❌ Depends on fingerprinting |
| Residual ML feedback | cgmencode → aid-autoresearch | LSTM residual model identifies physics model blind spots → improve UVA/Padova scenarios | ❌ Research |
| Algorithm decision vectors | aid-autoresearch → cgmencode | Cross-validated oref0/Loop decisions → training labels for decision model | ❌ Not wired |
| Scenario library | aid-autoresearch → cgmencode | Classified common/edge/impossible scenarios → structured training curriculum | ❌ Depends on classification |

---

## 5. What's Missing: Gap Analysis vs. Advisor Vision

### 5.1 Immediate Gaps (blocks near-term progress)

| Gap | Description | Blocking | Owner |
|-----|-------------|----------|-------|
| **GAP-ML-001** | No bridge between SIM-* vectors and cgmencode FixtureEncoder format | Prevents sim-to-real transfer learning | Shared |
| **GAP-ML-002** | cgmencode trained on ~1,000 vectors from single patient | All models underfit; no generalization evidence | cgmencode |
| **GAP-ML-003** | No override event labels in any dataset | Cannot train decision models (§3.6) | NEW |
| **GAP-ML-004** | Conditioned Transformer produces point estimates only | No uncertainty for safety-critical decisions | cgmencode |

### 5.2 Medium-Term Gaps (needed for anticipatory management)

| Gap | Description | Blocking | Owner |
|-----|-------------|----------|-------|
| **GAP-ML-005** | No explicit event classifier (meal/exercise/sleep detection) | Cannot infer "Eating Soon" without button press | NEW |
| **GAP-ML-006** | No temporal state tracker (ISF/CR drift over days) | Cannot detect "insulin resistance trending up" | NEW |
| **GAP-ML-007** | No context signal ingestion (calendar, weekday, travel) | Pattern recognition limited to glucose-insulin-carbs | NEW |
| **GAP-ML-008** | Statistical fingerprinting pipeline not implemented | Cannot calibrate physics engine against real population | aid-autoresearch |

### 5.3 Longer-Term Gaps (needed for autonomous optimization)

| Gap | Description | Blocking | Owner |
|-----|-------------|----------|-------|
| **GAP-ML-009** | No policy layer for override selection | System can predict but not recommend actions | NEW |
| **GAP-ML-010** | No safety constraint framework for learned policies | RL/bandit could suggest dangerous overrides | NEW |
| **GAP-ML-011** | No feedback loop from override acceptance/rejection | Models cannot improve from user behavior | NEW |
| **GAP-ML-012** | Diffusion implementation simplified (not proper DDPM forward process) | Uncertainty estimates may be miscalibrated | cgmencode |

---

## 6. Recommended Sequencing

### Phase A: Foundation Strengthening (current focus)

**Goal**: Make existing toolkits robust before adding decision layer.

1. **Wire SIM-* → cgmencode** (GAP-ML-001): Write format adapter so UVA/Padova output can train cgmencode models. Enables unlimited synthetic data.
2. **Scale cgmencode training data** (GAP-ML-002): Ingest historical Nightscout data via `iob-clean-windows` pipeline. Target: 10K vectors from 5+ patients.
3. **Implement fingerprinting extractor** (GAP-ML-008): Build the 4-tier fingerprint computation from simulation-validation-architecture.md §3.
4. **Validate Conditioned Transformer against UVA/Padova** (trust building): Run same scenarios through both, compare glucose trajectories. Establishes whether ML learns the physics.

### Phase B: Decision Modeling (new capability)

**Goal**: Predict when overrides should occur.

5. **Collect override event labels** (GAP-ML-003): Extract from Nightscout treatment logs where `eventType` contains override-like actions (Eating Soon, Exercise, custom notes). Even noisy labels suffice for Stage 1.
6. **Train event classifier** (GAP-ML-005): Start with XGBoost on tabular features (BG trend, IOB, time-of-day, day-of-week). Evaluate on historical: "did user actually activate override within next 30 min?"
7. **Add temporal prediction**: Upgrade to TCN/Transformer on cgmencode embeddings predicting (event_type, minutes_until, confidence).

### Phase C: State Tracking & Personalization

**Goal**: Track slow physiological changes.

8. **Implement Bayesian ISF/CR tracker** (GAP-ML-006): Start with online linear Kalman filter over daily ISF/CR estimates from autotune-style math. Compare to autosens.
9. **Upgrade to deep state-space**: Wire VAE latent as state, learn transition dynamics. This is where cgmencode's latent space meets longitudinal tracking.

### Phase D: Policy & Safety

**Goal**: Move from prediction to recommendation.

10. **Implement supervised policy** (GAP-ML-009): Given predicted event + state estimate, suggest override from historical user behavior.
11. **Add safety constraints** (GAP-ML-010): Physics guard (UVA/Padova check) + uncertainty guard (diffusion P(hypo)) + controller agreement check.
12. **Contextual bandits** (when sufficient online data): Thompson sampling over override candidates with safety floor.

---

## 7. Technique-to-Objective Mapping

This table maps every ML technique (existing, planned, or recommended) to the specific objective it serves.

| Technique | Layer | Objective | Status | Workspace |
|-----------|-------|-----------|--------|-----------|
| UVA/Padova 18-ODE | 1-Physics | Causally valid BG simulation | ✅ Done | aid-autoresearch |
| Facchinetti/Vettoretti sensor noise | 1-Physics | Realistic CGM jitter | ✅ Done | aid-autoresearch |
| Corruption-based augmentation | 1-Physics | Edge case generation from real traces | ❌ Designed | aid-autoresearch |
| Wasserstein/DTW/ACF distance | 2-Calibration | Measure physics-reality gap | ❌ Designed | aid-autoresearch |
| Nelder-Mead/Bayesian optimization | 2-Calibration | Optimize UVA/Padova patient params | ❌ Designed | aid-autoresearch |
| Masked Transformer AE | 3-Dynamics | Representation learning backbone | ✅ Prototype | cgmencode |
| SimCLR contrastive | 3-Dynamics | Noise-invariant features | ✅ Prototype | cgmencode |
| VAE (32D) | 3-Dynamics | Scenario generation + phenotyping | ✅ Prototype | cgmencode |
| Conditioned Transformer | 3-Dynamics | Counterfactual dosing (what-if) | ✅ Prototype | cgmencode |
| 1D DDPM Diffusion | 3-Dynamics | Uncertainty quantification | ✅ Prototype | cgmencode |
| LSTM residual | 2→3 Bridge | Learn physics model blind spots | ❌ Research | Shared |
| XGBoost/LightGBM event classifier | 4-Decision | Detect meals, exercise, sleep onset | ❌ NEW | TBD |
| TCN/Transformer sequence classifier | 4-Decision | Predict event type + timing + duration | ❌ NEW | TBD |
| Multitask prediction heads | 4-Decision | Joint event-type/timing/intensity | ❌ NEW | TBD |
| Kalman filter (ISF/CR tracking) | 3.5-State | Track slow physiological drift | ❌ NEW | Shared |
| Deep state-space (S4/SSM) | 3.5-State | Nonlinear drift with uncertainty | ❌ Research | Shared |
| Supervised policy (imitation) | 4-Policy | Learn override behavior from history | ❌ NEW | TBD |
| Contextual bandits (Thompson) | 4-Policy | Adaptive override selection | ❌ Future | TBD |
| Constrained offline RL (CQL) | 4-Policy | Optimal policy from logged data | ❌ Research | TBD |

---

## 8. Key Design Decisions & Rationale

### 8.1 "Start with trees, not transformers" (advisor recommendation)

For decision modeling (Stage 1 event classification), gradient-boosted trees on tabular features will likely match or beat deep learning on small labeled datasets. This provides:
- Fast iteration (minutes to train, not hours)
- Interpretable feature importances ("time_of_day and BG_slope drove this prediction")
- Strong baseline that deep models must beat to justify complexity
- Works with hundreds of examples, not millions

### 8.2 "Physics backbone, ML residual" (composition principle)

The UVA/Padova model encodes 60+ years of metabolic research. A pure ML model would need millions of patient-hours to learn what the ODEs already know. The correct composition is:

```
BG_predicted = UVA_Padova(insulin, carbs, θ_patient)  +  ML_residual(context, history)
               └── Causal, interpretable, zero-shot ──┘   └── Behavioral, personalized ──┘
```

This means cgmencode's Conditioned Transformer should be trained to predict the *residual* (actual − physics), not the raw glucose. This dramatically reduces what the neural network must learn.

### 8.3 "Safety floor, not safety ceiling"

The policy layer must guarantee a minimum safety level (never worse than "do nothing") but need not be optimal. This is the **constrained** in constrained offline RL. Practically:
- Every candidate override is simulated through UVA/Padova
- Diffusion generates uncertainty bands
- If P(BG < 54 | override) > P(BG < 54 | do_nothing), the override is rejected
- Human always has veto power

### 8.4 "Sim-to-real transfer, not sim-only"

cgmencode should be pre-trained on unlimited UVA/Padova synthetic data, then fine-tuned on real patient data. This is the standard sim-to-real transfer pattern from robotics. The physics engine provides the curriculum; the real data provides the calibration.

---

## 9. Relationship to Existing Documentation

| Document | Relationship to This Doc |
|----------|-------------------------|
| `simulation-validation-architecture.md` | §1-8 detail Layer 1+2 internals. This doc references it for calibration pipeline design. |
| `cgm-trace-generation-methodologies.md` | §2-7 detail 5 generation approaches. This doc places them in the composition framework. |
| `therapy-optimization-feature-pipeline.md` | Describes fingerprinting as therapy assessment. This doc shows how fingerprinting feeds calibration (Layer 2). |
| `cross-validation-assessment.md` | Tracks algorithm correctness validation. This doc shows how algorithm scores feed decision model training. |
| cgmencode `README.md` / `TODO.md` | Describes cgmencode internals and roadmap. This doc positions cgmencode as Layer 3 in the stack. |

---

## 10. Open Questions for Team Discussion

1. **Override label source**: Where do we get override event labels? Nightscout `treatments` with `eventType` containing override-like entries? Loop's `overrideStatus`? Manual annotation?

2. **Single-patient vs multi-patient**: cgmencode currently trains on one patient. Should we build population models first, then personalize? Or start with strong single-patient models?

3. **Context signal scope**: The advisor mentions calendar, travel, activity. What signals are actually available from Nightscout ecosystem today? (HealthKit steps? Google Fit? Manual notes?)

4. **Workspace boundary**: Should decision modeling (Layer 4) live in cgmencode (t1pal-mobile-workspace) or here (ecosystem-alignment)? Recommendation: cgmencode, since it's closer to the mobile inference path.

5. **Evaluation criteria**: What makes a good override recommendation? Time-in-range improvement? User acceptance rate? Hypo avoidance? Need explicit metrics before training.

---

## Appendix A: cgmencode Architecture Reference

### Feature Vector (8 elements per 5-min timestep)

| Index | Feature | Type | Scale |
|-------|---------|------|-------|
| 0 | glucose | State | [0-400] → [0-1] |
| 1 | iob | State | [0-20] → [0-1] |
| 2 | cob | State | [0-100] → [0-1] |
| 3 | net_basal | Action | [-5,5] → [-1,1] |
| 4 | bolus | Action | [0-10] → [0-1] |
| 5 | carbs | Action | [0-100] → [0-1] |
| 6 | time_sin | Temporal | sin(2π·hour/24) |
| 7 | time_cos | Temporal | cos(2π·hour/24) |

### Window Structure
```
[History: 72 steps = 6h | Lead: 3 steps = 15min | Target: 12 steps = 1h]
```

### Model Architectures

| Model | Parameters | Input | Output | Loss |
|-------|-----------|-------|--------|------|
| Transformer AE | ~50K | [B, 96, 8] | [B, 96, 8] | MSE |
| VAE | ~80K | [B, 96, 8] | [B, 96, 8] + z_μ, z_σ | MSE + β·KL |
| Conditioned | ~60K | [B, 72, 8] + [B, 12, 3] | [B, 12] glucose | MSE |
| Diffusion | ~50K | [B, 96, 8] + t_embed | [B, 96, 8] noise | MSE(ε) |
| Contrastive | N/A | z_i, z_j pairs | scalar sim | SimCLR CE |

### Training Data Pipeline
```
Nightscout JSON → FixtureEncoder → 5-min grid → normalize → window → DataLoader
                                                                        ↓
                                                              (Batch, 96, 8)
```

## Appendix B: Glossary of Techniques

| Term | Definition | Where Used |
|------|-----------|------------|
| **Masked AE** | Autoencoder trained by masking input portions and reconstructing them | cgmencode pretext tasks |
| **VAE** | Variational Autoencoder — generative model with Gaussian latent space | cgmencode scenario generation |
| **DDPM** | Denoising Diffusion Probabilistic Model — iterative noise→signal generation | cgmencode uncertainty |
| **SimCLR** | Simple Contrastive Learning of Representations — learn invariances | cgmencode robustness |
| **Conditioned Transformer** | Transformer that takes future actions as exogenous inputs | cgmencode digital twin |
| **Wasserstein distance** | Earth-mover's distance between probability distributions | Calibration (aid-autoresearch) |
| **DTW** | Dynamic Time Warping — elastic distance between time series | Calibration (aid-autoresearch) |
| **ACF** | Autocorrelation Function — captures temporal structure | Calibration (aid-autoresearch) |
| **XGBoost** | Gradient-boosted decision trees for tabular data | Proposed event classifier |
| **TCN** | Temporal Convolutional Network — dilated causal convolutions | Proposed sequence classifier |
| **Kalman filter** | Bayesian state estimation with linear dynamics + Gaussian noise | Proposed drift tracker |
| **S4/SSM** | Structured State-Space Model — deep learning on long sequences | Research: nonlinear drift |
| **CQL** | Conservative Q-Learning — offline RL with pessimistic value estimates | Research: policy learning |
| **Thompson sampling** | Bayesian bandit algorithm sampling from posterior | Proposed override selection |
| **Autosens** | oref0's rolling sensitivity multiplier from BG deviations | Existing heuristic baseline |
| **Autotune** | oref0's statistical basal/ISF/CR optimizer | Existing heuristic baseline |
