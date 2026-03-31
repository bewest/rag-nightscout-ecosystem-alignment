# ML Technique Catalog

Reference catalog of ML techniques for anticipatory diabetes management. Each entry describes what the technique does, where it fits in the [4-layer architecture](../architecture/ml-composition-architecture.md), and current status.

For design rationale and composition principles, see `docs/architecture/ml-composition-architecture.md`.
For gap tracking, see `traceability/ml-gaps.md`.
For implementation details, see `tools/cgmencode/README.md`.

---

## Layer 1: Physics Simulation

### UVA/Padova 18-ODE
- **Objective**: Causally valid BG trajectory simulation from insulin + carbs + patient parameters
- **Mechanism**: 18 coupled ordinary differential equations modeling glucose-insulin pharmacokinetics
- **Status**: ✅ Done — `tools/aid-autoresearch/in-silico-bridge.js` with `--engine uva-padova`
- **Limitations**: Only accepts BW (body weight) and Gpeq (initial glucose) as physiological params; ISF/CR/DIA only affect the oref0 controller layer
- **Explore further**: `externals/cgmsim-lib/src/UVAsimulator.ts`, `docs/architecture/simulation-validation-architecture.md`

### Facchinetti/Vettoretti Sensor Noise
- **Objective**: Realistic CGM jitter via AR(1) stochastic noise models
- **Status**: ✅ Done — `--sensor facchinetti|vettoretti` flag in bridge
- **Explore further**: `externals/cgmsim-lib/src/lt1/`

### cgmsim Simplified Engine
- **Objective**: Fast pharmacokinetic simulation for rapid iteration
- **Mechanism**: `nextBG = lastBG + (-insulinActivity*ISF + carbRate*ISF/CR + liver)*18`
- **Status**: ✅ Done — `--engine cgmsim` (default)
- **Limitations**: Narrow BG range (89–140), algorithm rankings can reverse vs real data
- **Explore further**: `externals/cgmsim-lib/src/sgv.ts`, `docs/architecture/simulation-validation-architecture.md`

---

## Layer 2: Calibration & Residual

### Statistical Fingerprinting (Wasserstein/DTW/ACF)
- **Objective**: Measure how far physics simulation is from real patient data
- **Mechanism**: Compute distribution distance metrics between simulated and real BG traces
- **Status**: ❌ Designed only — no code exists
- **Explore further**: `docs/architecture/simulation-validation-architecture.md` §3, `docs/architecture/therapy-optimization-feature-pipeline.md`

### Parameter Optimization (Nelder-Mead/Bayesian)
- **Objective**: Tune UVA/Padova patient parameters to minimize physics-reality gap
- **Status**: ❌ Designed only
- **Note**: Lower priority — §8.2 residual approach in the architecture doc bypasses explicit calibration

### Physics-ML Residual
- **Objective**: Train ML to predict `actual_glucose − physics_predicted` rather than raw glucose
- **Mechanism**: Standard scientific ML composition — physics provides causal backbone, ML learns behavioral residual
- **Status**: ❌ Not implemented — requires real patient data paired with physics predictions
- **Explore further**: Architecture doc §8.2 for design rationale

---

## Layer 3: Learned Dynamics (cgmencode)

### Masked Transformer Autoencoder
- **Objective**: Learn fundamental glucose-insulin-carb relationships via self-supervised representation
- **Mechanism**: Transformer (64D, 2 layers, 4 heads) trained on 6 pretext tasks (fill_actions, fill_readings, forecast, denoise, random_patch, shuffled_mask)
- **Parameters**: ~68K
- **Status**: ✅ **Verified** — 2.12 MAE mg/dL on UVA/Padova, 4.64 on cgmsim. Beats persistence by 55–88%.
- **Implementation**: `tools/cgmencode/model.py`

### Conditioned Transformer (Digital Twin)
- **Objective**: Predict future glucose given history + proposed future actions (dosing "what-if")
- **Mechanism**: Encodes `history[12×8]` + `future_actions[12×3]` → predicts `future_glucose[12]`
- **Parameters**: ~844K
- **Status**: ✅ **Verified** — 3.47 MAE mg/dL on UVA/Padova, 4.67 on cgmsim
- **Key property**: Treats future actions as exogenous control inputs → enables counterfactual intervention (fix history, sweep doses)
- **Implementation**: `tools/cgmencode/toolbox.py` `ConditionedTransformer`

### Variational Autoencoder (VAE)
- **Objective**: Generate synthetic scenarios by sampling 32D Gaussian latent space; cluster physiological phenotypes
- **Parameters**: ~1.1M
- **Status**: ❌ **Broken** — 42.78 MAE (worse than persistence). 32D bottleneck loses too much sequence information for trajectory forecasting.
- **Root cause**: Architectural mismatch. The global latent bottleneck is appropriate for classification/clustering but destructive for sequence forecasting. KL annealing (β: 0→0.01 over 30% warmup) prevents collapse but doesn't fix the fundamental issue.
- **Path forward**: Redesign as Conditional VAE with per-timestep conditioning or hierarchical latent structure
- **Implementation**: `tools/cgmencode/toolbox.py` `CGMTransformerVAE`

### Denoising Diffusion (1D-DDPM)
- **Objective**: Generate probability clouds capturing one-to-many outcome distribution
- **Status**: ❌ **Toy implementation** — forward process is `x + noise`, not proper DDPM β-schedule. Uncertainty estimates are meaningless.
- **Path forward**: Implement proper linear/cosine β-schedule, train noise prediction network, validate calibration
- **Implementation**: `tools/cgmencode/toolbox.py` `CGMDenoisingDiffusion`

### SimCLR Contrastive Learning
- **Objective**: Force encoder to ignore sensor jitter/dropouts, focus on invariant physiological signal
- **Mechanism**: Maximize mutual information between augmented views of same trajectory
- **Status**: ✅ Prototype — loss function implemented, not systematically evaluated
- **Implementation**: `tools/cgmencode/toolbox.py` `ContrastiveLoss`

---

## Layer 3.5: State Tracking (proposed)

### Bayesian ISF/CR Tracker
- **Objective**: Track slow physiological drift (insulin sensitivity, carb ratio) over days/weeks
- **Mechanism**: Online linear Kalman filter over daily ISF/CR estimates
- **Status**: ❌ Not started
- **Existing baseline**: oref0's `autosens` (rolling sensitivity multiplier from BG deviations)

### Deep State-Space Model
- **Objective**: Nonlinear drift tracking with uncertainty via learned transition dynamics
- **Mechanism**: Wire VAE/AE latent as state, learn `z_{t+1} = f_θ(z_t) + noise`
- **Status**: ❌ Research
- **Note**: Requires VAE to be fixed first, or can use AE encoder as state extractor

---

## Layer 4: Decision & Policy (proposed)

### Event Classifier (XGBoost)
- **Objective**: Detect meals, exercise, sleep onset from glucose-insulin patterns
- **Mechanism**: Gradient-boosted trees on tabular features (BG trend, IOB, time-of-day, day-of-week)
- **Status**: ❌ Not started — needs override event labels from Nightscout treatment logs
- **Rationale**: Start simple; trees on tabular features beat deep models on small labeled datasets

### Temporal Sequence Classifier (TCN/Transformer)
- **Objective**: Predict (event_type, time_until_event, confidence) from encoded history
- **Mechanism**: TCN or Transformer head on cgmencode embeddings
- **Status**: ❌ Not started — depends on event classifier baseline

### Policy Layer (supervised → bandits → offline RL)
- **Objective**: Select safest effective override given predicted events
- **Progressive approach**:
  1. Supervised imitation learning from historical user override decisions
  2. Contextual bandits (Thompson sampling) for exploration/exploitation
  3. Constrained offline RL (CQL) for optimal policies from logged data
- **Status**: ❌ Not started
- **Critical constraint**: Safety floor — never suggest action worse than "do nothing"

---

## Technique-to-Objective Matrix

| Technique | Layer | Objective | Status |
|-----------|-------|-----------|--------|
| UVA/Padova 18-ODE | 1 | Causally valid BG simulation | ✅ Done |
| Facchinetti/Vettoretti noise | 1 | Realistic CGM jitter | ✅ Done |
| Corruption-based augmentation | 1 | Edge case generation | ❌ Designed |
| Wasserstein/DTW/ACF distance | 2 | Measure physics-reality gap | ❌ Designed |
| Nelder-Mead/Bayesian opt. | 2 | Optimize patient params | ❌ Designed |
| Masked Transformer AE | 3 | Representation backbone | ✅ 2.12 MAE |
| SimCLR contrastive | 3 | Noise-invariant features | ✅ Prototype |
| VAE (32D) | 3 | Scenario generation | ❌ Broken |
| Conditioned Transformer | 3 | Counterfactual dosing | ✅ 3.47 MAE |
| 1D DDPM Diffusion | 3 | Uncertainty quantification | ❌ Toy |
| LSTM/Transformer residual | 2→3 | Physics model blind spots | ❌ Research |
| Kalman filter | 3.5 | Slow physiological drift | ❌ Not started |
| Deep state-space (S4/SSM) | 3.5 | Nonlinear drift | ❌ Research |
| XGBoost event classifier | 4 | Detect meals/exercise/sleep | ❌ Not started |
| TCN/Transformer classifier | 4 | Event type + timing | ❌ Not started |
| Supervised policy | 4 | Imitate user overrides | ❌ Not started |
| Contextual bandits | 4 | Adaptive override selection | ❌ Future |
| Constrained offline RL | 4 | Optimal logged-data policy | ❌ Research |

---

## Glossary

| Term | Definition |
|------|-----------|
| **Masked AE** | Autoencoder trained by masking input portions and reconstructing them |
| **VAE** | Variational Autoencoder — generative model with Gaussian latent space |
| **DDPM** | Denoising Diffusion Probabilistic Model — iterative noise→signal generation |
| **SimCLR** | Simple Contrastive Learning of Representations — learn invariances |
| **Conditioned Transformer** | Transformer that takes future actions as exogenous inputs |
| **Wasserstein distance** | Earth-mover's distance between probability distributions |
| **DTW** | Dynamic Time Warping — elastic distance between time series |
| **ACF** | Autocorrelation Function — captures temporal structure |
| **XGBoost** | Gradient-boosted decision trees for tabular data |
| **TCN** | Temporal Convolutional Network — dilated causal convolutions |
| **Kalman filter** | Bayesian state estimation with linear dynamics + Gaussian noise |
| **S4/SSM** | Structured State-Space Model — deep learning on long sequences |
| **CQL** | Conservative Q-Learning — offline RL with pessimistic value estimates |
| **Thompson sampling** | Bayesian bandit algorithm sampling from posterior |
| **Autosens** | oref0's rolling sensitivity multiplier from BG deviations |
| **Autotune** | oref0's statistical basal/ISF/CR optimizer |
