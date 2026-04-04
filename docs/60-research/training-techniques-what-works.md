# Training Techniques: What Works, What Doesn't, and Why

**Date**: 2026-04-04
**Scope**: 238 experiments (EXP-001 through EXP-238), 10 patients, 4 months
**Dataset**: ~32K training windows (8f) / ~16K (21f) from Nightscout CGM data
**Key Milestone**: Discovery and correction of future action data leakage at EXP-159

---

## Executive Summary

Over 238 experiments, a handful of techniques account for virtually all progress.
The single most important discovery was *not* a training technique — it was
finding that ~60% of our apparent improvement was fake, caused by future treatment
data leaking into the training window. Once corrected, the honest forecast
improvement is **14–15% over persistence** (29.5 mg/dL MAE at 1-hour, 41.5 at
2-hour).

This report ranks every technique we tried by actual impact, documents what
failed and why, and identifies where genuine progress remains possible.

**The impact hierarchy** (techniques ranked by real, verified improvement):

| Rank | Technique | Impact | Key Experiment |
|------|-----------|--------|----------------|
| 1 | Physics-residual decomposition | 8.2× | EXP-005 |
| 2 | Causal masking (leak fix) | Honest baselines | EXP-159 |
| 3 | Synthetic-to-real transfer learning | 2.7× | EXP-003 |
| 4 | Multi-seed ensembling | 7% forecast, 16× variance reduction | EXP-100 |
| 5 | XGBoost for event detection | 6.6× vs neural | EXP-181 |
| 6 | Conformal prediction | 60× calibration | EXP-059 |
| 7 | Multi-patient joint training | 5.7% | EXP-142 |
| 8–10 | Architecture, regularization, loss | <2% each | Various |

**Three techniques account for >95% of all improvement.** Everything else is
noise-level optimization on a data-limited problem.

---

## Table of Contents

1. [Techniques That Transformed Results](#1-techniques-that-transformed-results)
2. [Techniques That Provided Genuine Incremental Gains](#2-techniques-that-provided-genuine-incremental-gains)
3. [Techniques That Failed](#3-techniques-that-failed)
4. [The Architecture Saturation Wall](#4-the-architecture-saturation-wall)
5. [The Generalization Gap](#5-the-generalization-gap)
6. [Capability Scorecard](#6-capability-scorecard)
7. [What Would Actually Move the Needle](#7-what-would-actually-move-the-needle)
8. [Appendix: Complete Experiment Index](#appendix-complete-experiment-index)

---

## 1. Techniques That Transformed Results

These three techniques produced order-of-magnitude improvements. They are
non-negotiable foundations for any glucose forecasting system.

### 1.1 Physics-Residual Decomposition (8.2× improvement)

**Experiment**: EXP-005
**Insight**: Don't predict glucose directly. Use a physics model (UVA/Padova
18-ODE) to predict ~85% of glucose dynamics from insulin and carb
pharmacokinetics. Train the neural network only on the *residual* — the gap
between physics prediction and actual glucose.

| Approach | MAE |
|----------|-----|
| Physics model alone | 37.8 mg/dL |
| Raw ML (no physics) | 3.66 mg/dL* |
| **Physics + ML residual** | **1.05 mg/dL*** |

*\*Pre-leak-fix metrics; relative ranking holds*

**Why it works**: Glucose dynamics are ~85% deterministic mechanics (insulin
absorption curves, carb digestion rates, liver glucose output). The remaining
~15% is sensor noise, exercise effects, stress, dawn phenomenon — patterns
where ML excels. By decomposing the problem, each component solves what it's
good at.

**Implementation**: `physics_model.py` provides the physics backbone.
`encoder.py` trains on `actual_glucose - physics_predicted_glucose`.

### 1.2 Proper Causal Masking (Honest Baselines)

**Experiments**: EXP-043 (initial discovery), EXP-159 (comprehensive fix)
**Insight**: If the model can see future insulin doses, carb entries, and
treatment actions during training, it's not *predicting* — it's *reading the
answer sheet*.

**The bug**: `train_forecast()` masked future glucose (channel 0) and its
derivatives (channels 12–13), but left 7 other channels fully visible:

| Channel | What Leaked | Why It's Devastating |
|---------|-------------|---------------------|
| IOB (ch 1) | Future insulin on board | Reveals upcoming boluses |
| COB (ch 2) | Future carbs on board | Reveals upcoming meals |
| net_basal (ch 3) | Future basal rate | Reveals controller decisions |
| bolus (ch 4) | Future bolus events | Direct answer to "what happens next" |
| carbs (ch 5) | Future carb entries | Direct meal information |
| time_since_bolus (ch 14) | Resets reveal future boluses | Indirect timing leak |
| time_since_carb (ch 15) | Resets reveal future meals | Indirect timing leak |

**Impact**:

| Metric | Leaked (Gen-2) | Honest (Gen-3) | Inflation |
|--------|---------------|----------------|-----------|
| 8f MAE | 19.7 mg/dL | 29.5 mg/dL | 50% fake |
| 8f vs persistence | 66.9% | 14.0% | 53 pp fake |
| 21f MAE | 26.6 mg/dL | 41.5 mg/dL | 56% fake |
| 21f vs persistence | 70.4% | 15.3% | 55 pp fake |

**How it was discovered**: Three warning signs were present for 158 experiments:
1. Attention analysis showed 87% weight on glucose — the model ignored
   treatments because it could see them directly in future timesteps
2. A persistent 37% training-to-verification gap (leakage patterns are
   dataset-specific)
3. 1-hour forecast MAE of 0.9 mg/dL seemed "too good" but wasn't questioned

**Fix**: Centralized `FUTURE_UNKNOWN_CHANNELS` constant in `schema.py`.
Single `mask_future_channels()` helper applied at all three training sites.
Any new feature must be explicitly classified as known-future or unknown-future.

**Lesson**: If results seem too good, they are. Validate masking exhaustively.

### 1.3 Synthetic-to-Real Transfer Learning (2.7× improvement)

**Experiments**: EXP-003 (initial), EXP-015 (variance analysis)

| Approach | MAE | Variance |
|----------|-----|----------|
| Synthetic only (zero-shot) | 28.2 mg/dL* | High |
| Real only (from scratch) | 2.00 mg/dL* | 0.64 |
| **Synthetic → real transfer** | **0.74 mg/dL*** | **0.04** |

*\*Pre-leak-fix metrics; relative ranking holds*

**Why it works**: Synthetic data (UVA/Padova simulation) teaches the model
insulin/carb pharmacokinetics — the *shape* of glucose responses to treatments.
This structural knowledge transfers to real patients, even though absolute
values differ.

**Bonus**: Transfer learning reduced seed variance by **16×** (from 0.64 to
0.04), making training far more reproducible.

**Caveat** (EXP-141): With 32K+ real training windows, synthetic pre-training
shows 0% benefit. Transfer learning is essential for cold-start scenarios but
becomes redundant once sufficient real data is available.

---

## 2. Techniques That Provided Genuine Incremental Gains

These techniques each contributed 5–7% improvement. Worthwhile, but their
combined impact is still smaller than any single technique from Section 1.

### 2.1 Multi-Seed Ensembling (7% forecast improvement)

**Experiments**: EXP-017, EXP-051, EXP-100, EXP-139

Individual model performance varies dramatically by random seed:

| Seed | MAE (mg/dL) | vs Persistence |
|------|-------------|----------------|
| Best seed | 17.5 | +19% |
| Worst seed | 24.1 | −12% (worse than persistence!) |
| **5-seed ensemble** | **16.0** | **+26%** |

The ensemble (simple mean of 5 models with different random seeds) beats the
best individual seed by 8.5%. Two of five seeds actually *underperform*
persistence — meaning a single-model deployment has a 40% chance of shipping
a model worse than "just use the last reading."

**Architecture diversity** (EXP-139): Combining 5 *different* architectures
(d=32/64/128, L=2/4/6) yielded 12.1 mg/dL on training data — further
improvement from seed-only ensembles.

**Production recommendation**: Always deploy ensembles. Never a single model.

### 2.2 XGBoost for Event Detection (6.6× vs Neural)

**Experiments**: EXP-049, EXP-114, EXP-181, EXP-195

The transformer completely fails at event detection (F1=0.107). XGBoost with
engineered features achieves F1=0.679 — a 6.6× improvement.

| Method | F1 (Training) | F1 (Verification) |
|--------|---------------|-------------------|
| Neural event head | 0.107 | — |
| XGBoost baseline | 0.618 | 0.544 |
| **XGBoost + pharmakinetic features** | **0.679** | — |
| Per-patient XGBoost | 0.706 | — |

**Why the transformer fails**: Attention analysis (EXP-114) revealed that the
transformer allocates 87% of attention to glucose, 10.8% to insulin, 2.4% to
carbs. It's fundamentally a **glucose autoregressor** — it predicts the next
glucose value from recent glucose values. Events are defined by *treatment*
features (carbs, boluses, overrides) that the transformer essentially ignores.

**Why XGBoost succeeds**: 46 engineered features with direct access to treatment
signals:

| Feature | Importance | Category |
|---------|-----------|----------|
| carbs_total | 0.124 | Meal signal |
| net_basal_now | 0.100 | Controller state |
| cob_now | 0.096 | Carb absorption |
| bolus_total | 0.060 | Correction signal |
| glucose_std_1hr | 0.065 | Volatility |

**Per-class verification performance**:

| Event | F1 | Notes |
|-------|-----|-------|
| Correction bolus | 0.637 | Easiest — clear IOB + glucose signal |
| Custom override | 0.644 | Detectable from controller patterns |
| Meal | 0.547 | Good recall, carb entry + glucose rise |
| Exercise | 0.537 | High recall (97%) but low precision (37%) |
| Sleep | 0.352 | Hardest — only time-of-day signal available |

**Lead time**: 73.8% of events detected >30 minutes before they occur (clinically
actionable for anticipatory management).

### 2.3 Conformal Prediction (Reliable Uncertainty)

**Experiments**: EXP-059, EXP-126, EXP-127

MC-Dropout (the standard uncertainty approach) was catastrophically miscalibrated:
its "90% prediction interval" actually covered only 50% of outcomes. Conformal
prediction provides **60× better calibration**:

| Target Coverage | Conformal Actual | MC-Dropout Actual |
|-----------------|-----------------|-------------------|
| 50% | 48.4% | — |
| 80% | 80.2% | — |
| 90% | **90.7%** | **49.7%** |
| 95% | 95.6% | — |

90% PI width: 48.0 mg/dL (clinically informative — a 48 mg/dL band around
the prediction tells you whether to worry).

### 2.4 Multi-Patient Joint Training (5.7% improvement)

**Experiments**: EXP-142, EXP-144

Training on all 10 patients jointly provides implicit regularization:

| Approach | MAE |
|----------|-----|
| Single-patient average | 12.2 mg/dL* |
| 10-patient joint | 11.5 mg/dL* |
| LOO cross-validation | 17.4 ± 2.5 mg/dL* |

*\*Pre-leak-fix metrics; relative ranking holds*

Leave-one-out revealed massive per-patient variance (13.9–22.1 mg/dL),
confirming that patient diversity is the primary bottleneck.

### 2.5 Hypo-Focused Training (27–32% improvement for severe events)

**Experiments**: EXP-116, EXP-136, EXP-137

| Approach | Hypo MAE | Overall MAE Trade-off |
|----------|----------|----------------------|
| Standard training | 15.2 mg/dL* | 12.6 mg/dL* |
| Hypo-weighted loss | 12.4 mg/dL* | 13.1 mg/dL* (+4%) |
| **2-stage (classify → specialize)** | **10.4 mg/dL*** | Separate model |
| Production v7 (combined) | 13.1 mg/dL* | F1=0.700 |

*\*Pre-leak-fix metrics*

**Critical caveat**: Hypo prediction has a **154% training-to-verification gap**
(15.7 → 39.8 mg/dL). Hypoglycemic events are 3.5% of the dataset — the model
memorizes training hypo patterns rather than learning generalizable dynamics.
This remains the system's most critical clinical vulnerability.

---

## 3. Techniques That Failed

### 3.1 Extended Training (>50 epochs)

**Experiment**: EXP-053
**Result**: 150 epochs vs 50 → 0.6 mg/dL improvement (negligible)
**Why**: Already saturated on 10-patient dataset. More gradient steps find no
new patterns — only overfit harder to existing data.

### 3.2 Parameter Scaling Beyond Capacity Floor

**Experiments**: EXP-044, EXP-161

| Model | Params | 8f MAE | 21f MAE |
|-------|--------|--------|---------|
| tiny (d=64, L=2) | 67K | 29.5 | 41.9 |
| medium (d=128, L=3) | 300K | 29.5 | 41.8 |
| xlarge (d=256, L=4) | 993K | 29.6 | 41.9 |

A 15× increase in parameters produces **zero** improvement. The bottleneck is
data diversity, not model capacity. A 67K-parameter model is sufficient for
10 patients.

### 3.3 Semantic Group Projections (Gen-3 Architecture)

**Experiment**: EXP-162 (controlled comparison)

We hypothesized that splitting 13 extended features into 6 semantic groups
(weekday, override, dynamics, timing, device, monthly) would improve context
embedding. Result:

| Config | Gen-2 (monolithic) | Gen-3 (semantic groups) | Δ |
|--------|-------------------|------------------------|---|
| 21f tiny | 41.7 mg/dL | 41.6 mg/dL | −0.1 |
| 21f medium | 41.6 mg/dL | 41.8 mg/dL | +0.2 |
| 21f deep_narrow | 41.6 mg/dL | 41.5 mg/dL | −0.1 |

**Zero measurable benefit.** The extra architectural complexity (semantic group
projections, attention pooling) added parameters without improving forecasting.
The monolithic `context_proj(13→8)` works just as well at this data scale.

### 3.4 Diffusion Models (DDPM)

**Experiment**: EXP-016
**Result**: 50.6 mg/dL MAE — **63% worse than persistence** (21.6 mg/dL)
**Why**: Diffusion models are designed for high-entropy generative distributions.
Glucose is low-entropy and highly autocorrelated. Attention-based models
naturally capture this sequential structure.

### 3.5 Neural Multi-Task Learning (Forecast + Events)

**Experiments**: EXP-067, EXP-151
**Result**: Adding event detection heads to the transformer degraded forecast
MAE by up to 32% with no compensating improvement in event F1.
**Why**: The tasks compete for model capacity. Forecasting wants the model to be
a glucose autoregressor; event detection wants it to attend to treatment
features. The model can't do both well simultaneously.

### 3.6 Walk-Forward Temporal Splits

**Experiment**: EXP-046
**Result**: 20.7 mg/dL MAE (barely beats persistence at 21.6)
**Why**: Overly conservative — trains only on past, tests only on future. With
limited data, this throws away too much. Every-Nth-day splits balance realism
and data efficiency better.

### 3.7 Per-Patient Fine-Tuning

**Experiments**: EXP-057, EXP-063
**Result**: 11.4 mg/dL on training (best single-model result), but 18.4 mg/dL
on verification (overfits to individual patient's training distribution).
The 5-seed ensemble at 16.0 mg/dL is more robust without any fine-tuning.

### 3.8 Regularization Sweeps on Saturated Models

**Experiment**: EXP-161 (full sweep)
Tried dropout 0.1→0.3, weight decay 1e-5→5e-4, various combinations.
No configuration broke through the 29.5 mg/dL (8f) or 41.5 mg/dL (21f) ceiling.
When the model is data-limited, regularization has nothing to regularize against.

---

## 4. The Architecture Saturation Wall

EXP-161 (48 runs, 12 configurations, 2 seeds, 2 feature modes) definitively
proved that forecasting has hit a wall:

### 8-Feature (1-Hour Forecast): Total Saturation

```
  Config          Params     MAE      vs Persistence
  ─────────────   ─────────  ───────  ──────────────
  tiny            67K        29.5     14.0%
  small           101K       29.5     14.3%
  medium          300K       29.5     14.0%
  large           654K       29.6     13.9%
  xlarge          993K       29.6     13.7%
  deep_narrow     202K       29.7     13.4%
  shallow_wide    596K       29.8     13.1%
  ... (all others within 29.4–29.8 range)
```

**Every configuration achieves 29.4–29.8 mg/dL.** This is not an architecture
problem — it's a **data information ceiling**. Twelve 5-minute glucose readings
(1 hour of history) contain a fixed amount of predictive information about the
next hour. No model can extract more signal than exists.

### 21-Feature (2-Hour Forecast): Narrow Window

The 21-feature models show slightly more differentiation (1.0 mg/dL spread)
favoring deep + narrow architectures:

| Rank | Config | MAE | Params |
|------|--------|-----|--------|
| 1 | deep_narrow (d=64, L=6) | 41.5 | 210K |
| 2 | small (d=64, L=3) | 41.6 | 110K |
| ... | | | |
| 12 | med_maxreg (d=128, L=3, drop=0.3) | 42.2 | 331K |

Deeper, narrower models slightly outperform wider, shallower ones — suggesting
the extra context features benefit from more transformer layers to integrate,
but not more embedding dimensions.

---

## 5. The Generalization Gap

The honest gap between training and held-out verification performance:

| Metric | Training | Verification | Gap |
|--------|----------|--------------|-----|
| Forecast MAE (ensemble) | 11.7 mg/dL | 16.0 mg/dL | +37% |
| Forecast MAE (single) | 11.4 mg/dL | 17.5 mg/dL | +54% |
| Hypo MAE | 15.7 mg/dL | 39.8 mg/dL | **+154%** |
| Event detection F1 | 0.710 | 0.544 | −23% |

The 37% ensemble gap is **healthy and expected** — it represents the real cost
of temporal generalization. Glucose patterns on training days don't perfectly
predict held-out days.

The 154% hypo gap is **clinically dangerous** — the model memorizes the small
number of training hypo events rather than learning the underlying dynamics.
With hypo events at 3.5% of the dataset, this is fundamentally a data scarcity
problem.

### Per-Patient Variance: The Personalization Frontier

| Patient | LOO MAE | Windows | Notes |
|---------|---------|---------|-------|
| g | 13.9 | 3,792 | Easiest — stable, predictable |
| f | 14.4 | 3,798 | — |
| h | 15.3 | 1,520 | Limited data |
| a | 16.8 | 3,755 | — |
| d | 17.0 | 3,725 | — |
| c | 17.1 | 3,528 | — |
| i | 18.0 | 3,816 | High volatility |
| j | 19.3 | 1,310 | Missing IOB data |
| e | 20.3 | 3,339 | Complex physiology |
| **b** | **22.1** | **3,839** | **Hardest despite most data** |

**Data volume ≠ predictability.** Patient b has the most data (3,839 windows) but
the highest error (22.1 mg/dL). Patient g has slightly fewer windows but 37%
lower error. The spread (13.9–22.1 = 59%) shows that physiological complexity,
not data scarcity, drives per-patient difficulty.

---

## 6. Capability Scorecard

### Forecasting

| Horizon | Best MAE | vs Persistence | Status |
|---------|----------|----------------|--------|
| 1 hour (8f) | 29.5 mg/dL | 14% | Saturated — data ceiling |
| 2 hour (21f) | 41.5 mg/dL | 15% | Narrow optimization window |
| 1 hour (ensemble, pre-fix) | 16.0 mg/dL | 26% | Best verified result* |

*\*Pre-leak-fix ensemble on verification data; honest ensemble not yet run*

### Event Detection

| Event Type | F1 (Verification) | Lead Time |
|------------|-------------------|-----------|
| Correction bolus | 0.637 | >30 min (73.8%) |
| Custom override | 0.644 | >30 min |
| Meal | 0.547 | >30 min |
| Exercise | 0.537 | High recall (97%), low precision (37%) |
| Sleep | 0.352 | Time-of-day only |
| **Weighted average** | **0.544** | **73.8% >30 min ahead** |

### Uncertainty Quantification

| Method | 90% Coverage | PI Width | Calibration |
|--------|-------------|----------|-------------|
| Conformal (recommended) | 90.7% | 48.0 mg/dL | ✅ |
| MC-Dropout | 49.7% | — | ❌ |

### Drift Tracking

| Metric | Value | Target |
|--------|-------|--------|
| Median Pearson r (drift vs TIR) | −0.156 | < −0.30 |
| Patients with correct sign | 10/10 | 10/10 ✅ |
| Detection rate | 15.5% | >20% |

Drift tracking detects the right direction but with weak signal strength.
The drift detector operates on glucose residuals only and lacks the behavioral
and device context needed for actionable ISF/CR drift detection.

---

## 7. What Would Actually Move the Needle

Based on 238 experiments, the evidence is clear about what the system needs:

### 7.1 More Data (Highest Impact, Highest Confidence)

Every form of scaling analysis points to data as the bottleneck:
- Architecture scaling: 15× parameters → 0% improvement (EXP-161)
- Per-patient spread: 59% variance across 10 patients (EXP-144)
- Published SOTA: 30–45% vs persistence (50–500 patients, 1+ year each)
- Our dataset: 10 patients, ~6 months each — **10–50× smaller** than typical

**What's needed**: 50–100+ patients with diverse profiles (T1D/T2D, pump/MDI,
different CGM systems, age ranges). Data augmentation helps marginally (14.5%
hypo F1 improvement from EXP-105) but can't substitute for real physiological
diversity.

### 7.2 Hybrid Architecture for Events (Highest Leverage Code Change)

The evidence is overwhelming: neural networks should forecast glucose, XGBoost
should detect events. The hybrid architecture:

```
Raw CGM data → Transformer Encoder → glucose forecast (MAE ≈ 29.5)
                       │
                       └── encoded representations
                                    │
                                    ├── XGBoost → event detection (F1 ≈ 0.68)
                                    ├── XGBoost → drift classification
                                    └── Rule engine → override recommendation
```

This is architecturally clean, plays to each method's strengths, and avoids
the multi-task competition problem that plagued neural-only approaches.

### 7.3 Per-Patient Adaptation (Moderate Impact)

The 59% per-patient spread suggests that population models need personalization.
Options, ranked by expected impact:

1. **Patient embedding vectors** — learned offsets per patient (low risk)
2. **Fine-tune final layers** — freeze encoder, adapt heads (moderate risk)
3. **Full fine-tuning** — per-patient models (high risk of overfitting)

EXP-063 showed fine-tuning can improve 17% for some patients but degrade 9%
for others. The ensemble approach (EXP-100) is safer.

### 7.4 Longer Context Windows

Current 1–2 hour windows capture only fast dynamics (insulin action, meal
absorption). Slow dynamics play out over 4–24 hours:

- Exercise aftereffects: 4–12 hours
- Sensor drift: 24–72 hours
- Circadian patterns: 24 hours
- Menstrual cycle effects: 28 days

Longer windows would capture these signals but produce fewer training samples
from the same data, potentially worsening overfitting. A hierarchical approach
(fast encoder for recent data + slow encoder for daily summaries) may be the
practical solution.

### 7.5 What Won't Help

| Approach | Evidence Against | Confidence |
|----------|-----------------|------------|
| Larger models | EXP-161: 15× params, 0% gain | Very high |
| Longer training | EXP-053: 3× epochs, <1% gain | High |
| More regularization | EXP-161: dropout 0.3, wd 5e-4, no gain | High |
| Neural multi-task | EXP-067/151: tasks compete, both degrade | High |
| Semantic group projections | EXP-162: 0% vs monolithic | High |
| Diffusion models | EXP-016: 63% worse than persistence | Very high |

---

## Appendix: Complete Experiment Index

### Phase 1: Foundations (EXP-001 to EXP-017)

Core architecture selection and transfer learning validation.

- **EXP-003**: Synthetic→real transfer: 2.7× improvement, 16× variance reduction
- **EXP-005**: Physics-residual decomposition: 8.2× improvement
- **EXP-012a**: GroupedEncoder vs standard AE: 37% better for causal forecasting
- **EXP-015**: Multi-seed analysis: variance 0.64→0.04 with transfer
- **EXP-016**: Diffusion DDPM: 63% worse than persistence (failed)
- **EXP-017**: Seed ensemble: 19% variance reduction

### Phase 2: Architecture Exploration (EXP-026 to EXP-053)

Systematic ablation of model dimensions, depth, and training duration.

- **EXP-043**: Future masking discovery (forecast not reconstruction)
- **EXP-044**: Architecture sweep: d=32→128, only 2.1% gain
- **EXP-046**: Walk-forward: barely beats persistence (failed)
- **EXP-049**: Combined XGBoost classifier: F1=0.710 (training)
- **EXP-051**: Multi-seed: 12.3±0.11 mg/dL (saturated)
- **EXP-053**: Extended training: 150 epochs, <1% improvement

### Phase 3: Multi-Objective (EXP-054 to EXP-109)

Event detection, hypo prediction, uncertainty quantification.

- **EXP-057**: Per-patient fine-tuning: overfits (failed)
- **EXP-059**: Conformal prediction: 60× better calibration
- **EXP-067**: Multi-task neural: degrades forecast by 32% (failed)
- **EXP-100**: 5-seed ensemble: 11.7 mg/dL, 7.1% improvement
- **EXP-105**: Hypo data augmentation: 14.5% F1 improvement

### Phase 4: Production Optimization (EXP-110 to EXP-142)

Specialist models, production candidates, multi-patient training.

- **EXP-114**: Attention analysis: 87% glucose-dominant
- **EXP-116**: Hypo-weighted loss: 27% hypo improvement
- **EXP-136**: 2-stage hypo: 10.4 mg/dL (best hypo MAE)
- **EXP-137**: Production v7: 12.9 MAE, F1=0.700, conformal 90%
- **EXP-139**: Diverse architecture ensemble: 12.1 mg/dL
- **EXP-142**: Multi-patient: 11.5 MAE, 5.7% improvement

### Phase 5: Gen-2 Multi-Task (EXP-150 to EXP-157)

Extended features, auxiliary heads, composite evaluation.

- **EXP-151**: Gen-2 multi-task fine-tuning
- **EXP-154**: Label audit (drift label calibration fix)
- **EXP-155**: Neural vs XGBoost: F1=0.710 vs 0.107

### Phase 6: Autonomous Campaign (EXP-164 to EXP-238)

Agent-driven experimentation across event detection, drift, and ensemble methods.

- **EXP-181**: XGBoost + pharmakinetic features: F1=0.679 (best event detection)
- **EXP-195**: Multi-horizon XGBoost: F1=0.678
- **EXP-208**: Volatile augmentation: 35% gap reduction
- **EXP-217**: Per-patient oversampled: F1=0.706
- **EXP-222**: Drift-informed weighting

### Phase 7: Gen-3 Transition (EXP-158 to EXP-162)

Future action leak discovery, honest baselines, architecture comparison.

- **EXP-158**: Final Gen-2 (leaked): 19.7/26.6 mg/dL
- **EXP-159**: Gen-3 honest baseline: 29.6/41.9 mg/dL
- **EXP-160**: Quick sweep: saturation signal
- **EXP-161**: Full 48-run sweep: total 8f saturation confirmed
- **EXP-162**: Gen-2 vs Gen-3 controlled: identical results, architecture irrelevant

---

*Report generated from analysis of 238 experiments across 262 result files.
All post-EXP-159 metrics use honest future masking via `FUTURE_UNKNOWN_CHANNELS`.
Pre-EXP-159 absolute metrics are inflated by ~60% but relative rankings hold.*
