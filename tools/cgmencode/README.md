# 📊 CGMENCODE: CGM/Insulin Representation Learning Pipeline

**The Bridge from JSON Fixtures to Artificial Intelligence.**

This package turns raw Nightscout-style data (JSON) into "Neural Network Training Vectors." It is the foundation for building a **Physiological Digital Twin** that can predict glucose outcomes and evaluate dosing safety.

> **Provenance**: Imported from `t1pal-mobile-workspace/tools/cgmencode/` (2026-03-31).
> This is R&D-phase code brought into the ecosystem alignment workspace to compose with
> the physics simulation (cgmsim-lib/UVA-Padova), algorithm validation (aid-autoresearch),
> and conformance vector infrastructure that already live here. When the approach stabilizes,
> it may be spun out into its own repository.

---

## 🛠 For the Software Team: How to Run

If you can maintain Nightscout, you can run this. No ML knowledge required for setup.

### 1. Environment Setup
```bash
cd tools/cgmencode
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Run the Verification Tests
These scripts load our local test fixtures, process them, and prove the AI is learning.
```bash
# From the repo root:

# Get data stats (How much training data do we have?)
python3 -m tools.cgmencode.toolbox stats

# Test the basic Pattern Recognizer (Transformer) for 10 epochs
python3 -m tools.cgmencode.model

# Test the Experimental Toolbox (VAE, Conditioned, or Diffusion)
python3 -m tools.cgmencode.toolbox vae 5
python3 -m tools.cgmencode.toolbox conditioned 5
python3 -m tools.cgmencode.toolbox diffusion 5
```

---

## 🧠 For the T1D Expert: What is this doing?

To an ML researcher, this is "Self-Supervised Representation Learning." To a T1D expert, here is what our "Toolbox" actually does:

### 1. The Pattern Recognizer (Transformer AE)
*   **T1D Analogy**: Like a seasoned patient looking at a Nightscout graph and "feeling" that something is off because the insulin and carbs don't match the curve.
*   **Goal**: It learns the fundamental relationship between Insulin, Carbs, and Glucose. We hide parts of the graph and ask the AI to "draw in" what's missing.

### 2. The Scenario Generator (VAE)
*   **T1D Analogy**: A tool that can "imagine" 1,000 different ways a Friday night pizza might go, based on real historical data.
*   **Goal**: It turns our small set of test fixtures into an infinite library of "Synthetic Scenarios" to train other models.

### 3. The Digital Twin / Dosing Counselor (Conditioned Transformer)
*   **T1D Analogy**: A "What-if" simulator. You tell it: *"I'm at 150 mg/dL, I have 1U on board, and I want to eat 40g of carbs. What happens if I bolus 3U vs 5U?"*
*   **Goal**: It predicts the future curve based on a **specific proposed action**. This is the core of an automated dosing advisor.

### 4. The Stochastic Risk Predictor (Diffusion)
*   **T1D Analogy**: Instead of showing one "perfect" line for the future, it shows a **cloud of possibilities**. It captures the reality that sometimes a 5U bolus works perfectly, and sometimes (due to stress or exercise) it causes a crash.
*   **Goal**: It models the **uncertainty and risk** of T1D, not just the average outcome.

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

## 📐 The Data Pipeline (The "Magic" in `encoder.py`)

Raw Nightscout data is messy. To make it "AI-Ready," we perform three critical steps:

1.  **The 5-Minute Grid**: We align every sensor reading, bolus, and carb entry onto a perfectly synchronized timeline.
2.  **Circadian Awareness**: We map the "Time of Day" to a circle (Sin/Cos). This tells the AI that 11:55 PM and 12:05 AM are close together, helping it learn dawn phenomena and nighttime sensitivity.
3.  **Feature Scaling**: We "squash" all numbers (Glucose 40-400, Insulin 0-10) into a range of 0 to 1. This ensures the AI doesn't ignore the tiny (but vital) insulin doses just because the glucose numbers are bigger.

## 📂 File Map
- `SCHEMA.md`: The technical definition of the data vectors.
- `encoder.py`: The logic that cleans and transforms JSON into AI vectors.
- `model.py`: Our primary Transformer Neural Network.
- `toolbox.py`: Experimental advanced models (VAE, Diffusion, etc.).
- `inference.py`: Helper for loading models and making real predictions.
- `viz.py`: Plotting tools to show the "Cloud of Possibilities."

---

## 📈 Visualizing the Digital Twin

Once you have trained a model, you can use our visualization tools to see what the AI is thinking. 

### Generating a Forecast Cloud (Diffusion)
The Diffusion model doesn't just give one answer; it generates a **probability cloud**. The `viz.py` tool shows this as a shaded region, allowing you to see the "Value at Risk" (the chance of going low).

### Dosing "What-If" Analysis
You can compare multiple doses side-by-side. For example, comparing a 2U bolus vs. a 5U bolus will show two different predicted glucose curves on the same graph, helping you identify the safest path.
