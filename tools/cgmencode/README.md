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

### Real Patient Data (85-day Nightscout, Loop-controlled, 1 patient)
| Model | Params | MAE mg/dL | RMSE mg/dL | vs Persistence |
|-------|--------|-----------|------------|----------------|
| Persistence (baseline) | — | 19.01 | 26.76 | — |
| **Transformer AE** | 68K | **6.11** | **8.09** | **↓67.9%** |
| Conditioned Transformer | 844K | 26.14 | 32.27 | ❌ overfits |

### UVA/Padova Engine (18-ODE physiological model, 50 patients)
| Model | Params | MAE mg/dL | RMSE mg/dL | vs Persistence |
|-------|--------|-----------|------------|----------------|
| Persistence (baseline) | — | 4.74 | 7.68 | — |
| **Transformer AE** | 68K | **2.12** | **3.94** | **↓55%** |
| Conditioned Transformer | 844K | 3.47 | 5.49 | ↓27% |
| VAE (32D latent) | 1.1M | 42.78 | 57.57 | ❌ broken |

### cgmsim Engine (simplified pharmacokinetic, 50 patients)
| Model | Params | MAE mg/dL | RMSE mg/dL | vs Persistence |
|-------|--------|-----------|------------|----------------|
| Persistence (baseline) | — | 39–43 | 58–61 | — |
| Transformer AE | 68K | 4.64 | 6.89 | ↓88% |
| Conditioned Transformer | 844K | 4.67 | 7.83 | ↓87% |

### Key Takeaways
- **6.11 mg/dL MAE on real patient data** — clinically useful for 1-hour glucose forecasting
- Real data is ~3× harder than synthetic (6.11 vs 2.12 MAE) — expected due to sensor noise, meal variability, exercise
- **AE achieves sub-4 mg/dL MAE** on realistic UVA/Padova physiology
- Models generalize across 50 diverse patient profiles (ISF 15–80, CR 5–20)
- **Conditioned Transformer overfits on real data** — val loss oscillates; needs dropout, weight decay, or more data
- **VAE architecture is mismatched** — 32D bottleneck loses too much sequence info; needs Conditional VAE redesign
- **Diffusion model is a toy** — simplified forward process (`x + noise`), not proper DDPM β-schedule

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
