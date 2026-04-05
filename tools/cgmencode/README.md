# 📊 CGMENCODE: CGM/Insulin Representation Learning Pipeline

**The Bridge from Physics Simulation to Artificial Intelligence.**

This package turns physics-simulated and real-world glucose-insulin data into neural network training vectors. It is the foundation for building a **Physiological Digital Twin** that can predict glucose outcomes and evaluate dosing safety.

> **Provenance**: Imported from `t1pal-mobile-workspace/tools/cgmencode/` (2026-03-31).
> This is R&D-phase code brought into the ecosystem alignment workspace to compose with
> the physics simulation (cgmsim-lib/UVA-Padova), algorithm validation (aid-autoresearch),
> and conformance vector infrastructure that already live here. When the approach stabilizes,
> it may be spun out into its own repository.

---

## 🛠 Quick Start

### 1. Environment Setup
```bash
cd tools/cgmencode
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Generate Training Data (Physics → Vectors)
```bash
# Generate 50-patient Latin Hypercube sweep using cgmsim engine
python3 -m tools.cgmencode.generate_training_data \
  --patients 50 --engine cgmsim --output-dir externals/sweep-data

# Or use UVA/Padova physiological engine
python3 -m tools.cgmencode.generate_training_data \
  --patients 50 --engine uva-padova --output-dir externals/sweep-uva
```

### 3. Train a Model
```bash
# Train the Transformer AE (recommended starting point)
python3 -m tools.cgmencode.train --model ae --epochs 50 \
  --data externals/sweep-uva

# Train the Conditioned Transformer (dosing "what-if")
python3 -m tools.cgmencode.train --model conditioned --epochs 50 \
  --data externals/sweep-uva
```

### 4. Evaluate
```bash
# Evaluate against persistence baseline
python3 -m tools.cgmencode.evaluate --model ae \
  --checkpoint checkpoints/ae_best.pt --data externals/sweep-uva

# Test the real-data adapter (self-test with synthetic trace)
python3 -m tools.cgmencode.real_data_adapter --test
```

### 5. Legacy Commands (from original fixtures)
```bash
# These require Nightscout algorithm-replay fixtures in fixtures/ — 
# use the sim_adapter or generate_training_data workflows above instead.
python3 -m tools.cgmencode.model          # Basic AE on fixture data
python3 -m tools.cgmencode.toolbox vae 5  # Experimental architectures
```

---

## 📈 Benchmark Results (2026-04)

### Physics-ML Residual (Recommended Approach)

Train ML on `actual_glucose - physics_predicted` rather than raw glucose.
The AE learns only what physics can't explain (sensor noise, exercise, model mismatch).

| Model | Physics | Params | Recon MAE | Forecast MAE | vs Persistence |
|-------|---------|--------|-----------|-------------|----------------|
| **GroupedEncoder** | Enhanced | 68K | 0.30 | **0.49** | **↓97.4%** |
| Transformer AE | Enhanced | 68K | **0.20** | 0.78 | ↓95.9% |
| Transformer AE | Simple | 68K | 0.31 | — | ↓98.4% |
| Physics-only | Enhanced | — | 15.34 | 15.34 | ↓19.3% |
| Persistence | — | — | 19.01 | 19.01 | — |

- **Recon MAE**: Bidirectional attention, all timesteps (model sees full window)
- **Forecast MAE**: Causal attention, future-only (model can only look backward — clinically relevant)
- **GroupedEncoder wins on forecast** despite worse reconstruction — feature-grouped inductive bias helps causal prediction

### Per-Horizon Forecast MAE (mg/dL, causal, enhanced residual)

| Horizon | Grouped | AE | Winner |
|---------|---------|-----|--------|
| 5min | **0.35** | 0.70 | Grouped |
| 10min | **0.85** | 0.95 | Grouped |
| 15min | 0.84 | **0.78** | AE |
| 20min | **0.29** | 0.63 | Grouped |
| 25min | **0.24** | 0.78 | Grouped |
| 30min | **0.39** | 0.82 | Grouped |

### Key Takeaways
- **Physics-ML residual is the winning approach** — 0.20–0.49 MAE vs 2.00+ raw AE (EXP-005/007/012a)
- **GroupedEncoder is the best forecaster** — 0.49 mg/dL future-only MAE (37% better than AE, EXP-012a)
- **Reconstruction MAE ≠ forecast MAE** — AE wins recon (0.20) but Grouped wins forecast (0.49)
- Enhanced physics (liver + circadian) creates more learnable residuals than simple or UVA/Padova (EXP-007)
- Transfer learning helps: synth→real gives 0.22 MAE vs 0.30 from scratch (EXP-009)
- Scales to 3hr horizons: 1.41 MAE at 180min, still ↓96.4% vs persistence (EXP-010)
- Conditioned Transformer and VAE are dead ends on single-patient data (EXP-004/006)

---

## 🧠 For the T1D Expert: What is this doing?

To an ML researcher, this is "Self-Supervised Representation Learning." To a T1D expert, here is what our "Toolbox" actually does:

### 1. The Pattern Recognizer (Transformer AE)
*   **T1D Analogy**: Like a seasoned patient looking at a Nightscout graph and "feeling" that something is off because the insulin and carbs don't match the curve.
*   **Goal**: It learns the fundamental relationship between Insulin, Carbs, and Glucose. We hide parts of the graph and ask the AI to "draw in" what's missing.

### 2. The Scenario Generator (VAE)
*   **T1D Analogy**: A tool that can "imagine" 1,000 different ways a Friday night pizza might go, based on real historical data.
*   **Goal**: It turns our small set of test fixtures into an infinite library of "Synthetic Scenarios" to train other models.
*   **⚠️ Current status**: Architectural mismatch — 32D bottleneck too narrow for trajectory forecasting. Needs redesign as Conditional VAE.

### 3. The Digital Twin / Dosing Counselor (Conditioned Transformer)
*   **T1D Analogy**: A "What-if" simulator. You tell it: *"I'm at 150 mg/dL, I have 1U on board, and I want to eat 40g of carbs. What happens if I bolus 3U vs 5U?"*
*   **Goal**: It predicts the future curve based on a **specific proposed action**. This is the core of an automated dosing advisor.

### 4. The Stochastic Risk Predictor (Diffusion)
*   **T1D Analogy**: Instead of showing one "perfect" line for the future, it shows a **cloud of possibilities**. It captures the reality that sometimes a 5U bolus works perfectly, and sometimes (due to stress or exercise) it causes a crash.
*   **Goal**: It models the **uncertainty and risk** of T1D, not just the average outcome.
*   **⚠️ Current status**: Toy implementation — needs proper DDPM β-schedule.

---

## 🔬 For the ML Researcher: Architecture & Dynamics

This toolbox treats T1D management as a sequence-to-sequence problem across four distinct modeling paradigms.

### 1. The Global Imputer (VAE)
*   **Task**: Joint Density Estimation $P(X_{past}, X_{future})$.
*   **Architecture**: Transformer-based Variational Autoencoder.
*   **Latent Space**: Maps sequences to a $d=32$ Gaussian manifold representing "Physiological Phenotypes" (e.g., specific insulin sensitivity or carb absorption modes).
*   **Usage**: Generative scenario augmentation and physiological clustering.

### 2. The World Model / Digital Twin (Conditioned Transformer)
*   **Task**: Forward Dynamics $P(G_{future} \mid H_{past}, A_{future})$.
*   **Distinction**: Unlike the VAE (which performs imputation), this model treats future actions as **exogenous control inputs**.
*   **Causal Utility**: Allows for **Counterfactual Intervention**. By fixing $H_{past}$ and sweeping $A_{future}$ (Interventional Calculus), we can evaluate the stability of control policies without real-world risk.

### 3. The Stochastic Forecaster (Diffusion)
*   **Task**: Learning the Score Function of the physiological distribution.
*   **Architecture**: 1D-DDPM (Denoising Diffusion Probabilistic Model).
*   **Goal**: Captures the "one-to-many" nature of T1D (where one history can lead to a distribution of outcomes). By sampling the reverse diffusion process, we generate a probability cloud rather than a point estimate, mapping the "Value at Risk" for any given dose.

### 4. Robust Representation (Contrastive)
*   **Task**: Maximizing Mutual Information $I(z_i; z_j)$ between augmented views.
*   **Implementation**: SimCLR-style contrastive loss.
*   **Goal**: Forces the encoder to ignore "nuisance variables" (sensor jitter, dropouts) and focus on the invariant physiological signal.

---

## 📐 The Data Pipeline

Raw data → AI-ready vectors via three critical steps:

1.  **The 5-Minute Grid**: Align every sensor reading, bolus, and carb entry onto a synchronized timeline.
2.  **Circadian Awareness**: Map "Time of Day" to a circle (Sin/Cos). Tells the AI that 11:55 PM and 12:05 AM are close together.
3.  **Feature Scaling**: Normalize all 8 features to [0,1] or [−1,1] range (see `SCHEMA.md` for exact scales).

### 8-Feature Vector (per 5-min timestep)
| Index | Feature | Type |
|-------|---------|------|
| 0 | glucose | State |
| 1 | iob | State |
| 2 | cob | State |
| 3 | net_basal | Action |
| 4 | bolus | Action |
| 5 | carbs | Action |
| 6 | time_sin | Temporal |
| 7 | time_cos | Temporal |

## 📂 File Map

### Core Pipeline
- `encoder.py` — FixtureEncoder: JSON → 5-min grid → 8-feature normalized vectors
- `model.py` — CGMTransformerAE: primary representation learning backbone
- `toolbox.py` — Experimental models: VAE, Conditioned Transformer, Diffusion, Contrastive
- `SCHEMA.md` — Formal 8-feature vector schema with normalization scales

### Training & Evaluation
- `sim_adapter.py` — Bridge: SIM-*/TV-* conformance vectors → training tensors
- `generate_training_data.py` — Latin Hypercube parameter sweep via in-silico-bridge
- `train.py` — Unified training CLI (all 4 architectures, KL annealing for VAE)
- `evaluate.py` — Evaluation metrics: MAE/RMSE in mg/dL, persistence baseline

### Data Adapters
- `real_data_adapter.py` — Bridge: GluPredKit/OhioT1DM/CSV → 8-feature format

### Utilities
- `inference.py` — T1PalPredictor wrapper for loading trained models
- `viz.py` — Stochastic forecast cloud + dose comparison plots
- `requirements.txt` — Dependencies: pandas, numpy, torch, matplotlib, scipy

### Validation Framework
- `validation_framework.py` — Reusable validation infrastructure for auto-research experiments:
  - `MultiSeedRunner` — Run any train/eval function across multiple seeds (default: `[42, 123, 456, 789, 1337]`), aggregate with mean ± CI
  - `TemporalSplitter` — Chronological 2-way (80/20) or 3-way (60/20/20) data splits
  - `StratifiedTemporalSplitter` — Prevalence-preserving splits for imbalanced tasks (e.g., hypo at 6.4%)
  - `BootstrapCI` — Non-parametric bootstrap CIs on predictions, t-distribution CIs from seed values
  - `LOOValidator` — Leave-one-out patient cross-validation with degradation analysis
  - `ValidationReport` — Structured report builder for experiment JSON output
- `objective_validators.py` — Objective-specific metric computation:
  - `ForecastValidator` — MAE, RMSE, per-zone MAE (hypo/target/hyper), Clarke Error Grid
  - `ClassificationValidator` — Positive-class F1, macro F1, AUC-ROC, AUPRC, ECE, optimal threshold
  - `RetrievalValidator` — Silhouette, ARI, class-balanced Recall@K, per-cluster breakdown
  - `DriftValidator` — Spearman ρ, OLS slope ± CI, per-patient significance, aggregation

### Experiment Infrastructure
- `experiment_lib.py` — `ExperimentContext` with validation integration (`record_seed`, `record_split`, `attach_multi_seed_report`)
- `run_pattern_experiments.py` — Multi-scale pattern experiments (EXP-286+), `load_multiscale_data_3way()` for held-out test sets
- `experiments_agentic.py` — Agentic experiment runner (EXP-328+)

### Tests
- `test_cgmencode.py` — 46 test classes covering data pipeline, models, training
- `test_validation.py` — 49 tests covering validation framework and objective validators
