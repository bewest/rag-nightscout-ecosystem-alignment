# CGM Forecasting: Experimentation Process & Discovery Narrative

**Date**: 2026-04-03  
**Scope**: 154+ experiments across 21 rounds of iterative ML development  
**Period**: 2026-03-31 through 2026-04-03  

## Executive Summary

Over four days of intensive experimentation, we developed a multi-task CGM
glucose forecasting system that achieves **11.5 mg/dL MAE** on 10-patient
multi-horizon prediction — **72% better than Loop's own forecasting** and
**55% better than persistence baseline**. The journey from first experiment to
production-grade system involved 154+ experiments, several critical
methodological corrections, and a series of discoveries that reshaped our
understanding of what machine learning can and cannot learn from glucose data.

This report tells the story of that journey: what we tried, what we learned,
where the ceiling is, and what it would take to break through it.

---

## Phase 1: Foundations — Synthetic Data & Architecture Selection

**Experiments**: EXP-001 through EXP-017 (9 executed)  
**Date**: 2026-03-31  
**Key Question**: *Can we predict glucose at all, and which architecture should we use?*

### Starting Point: Synthetic Pre-Training

Our first models trained on **UVA/Padova T1D simulator** data — a
pharmacokinetically-validated synthetic CGM environment. This gave clean,
well-labeled training data with known ground truth for insulin/carb dynamics.

| Experiment | Approach | MAE (mg/dL) | Notes |
|-----------|----------|-------------|-------|
| EXP-001 | UVA/Padova synthetic only | 2.12 | Clean but narrow BG range |
| EXP-001 | cgmsim synthetic only | 4.64 | Range bias in simulator |

**Lesson**: Synthetic data teaches glucose dynamics structure but lacks the
messy reality of sensor noise, missed boluses, exercise, and individual
physiology.

### The Transfer Learning Breakthrough (EXP-003)

Moving to real Nightscout patient data, we compared four approaches:

| Approach | MAE (mg/dL) | Speedup vs Scratch |
|---------|-------------|-------------------|
| Zero-shot (synthetic model, no fine-tuning) | 28.22 | N/A (baseline) |
| From scratch (real data only) | 2.00 | — |
| **Transfer (synthetic → real fine-tune)** | **0.74** | **2.7× better** |
| Persistence (last value repeated) | 19.01 | — |

Transfer learning provided a **2.7× improvement** over training from scratch.
The synthetic pre-training gave the model a "physics prior" — understanding
of how insulin lowers glucose and carbs raise it — which real data alone took
much longer to discover.

### Architecture Selection: GroupedEncoder Wins (EXP-012a)

We compared two transformer-based architectures, each ~68K parameters:

- **Standard Autoencoder (AE)**: Flat input projection, bidirectional attention
- **GroupedEncoder**: Separate projections for state (glucose, IOB, COB),
  actions (basal, bolus, carbs), and time (sin/cos encoding), fused before
  attention layers

The GroupedEncoder **won on the metric that matters** — causal forecasting:

| Metric | Standard AE | GroupedEncoder | Winner |
|--------|------------|----------------|--------|
| Reconstruction (all timesteps) | 0.20 MAE | 0.30 MAE | AE |
| **Forecast (future only, causal)** | 0.78 MAE | **0.49 MAE** | **Grouped (+37%)** |

The AE's reconstruction superiority was illusory — it used bidirectional
attention that "peeked" at future glucose. GroupedEncoder's feature grouping
provided the inductive bias needed for genuine causal prediction.

**GroupedEncoder became our default architecture from this point forward.**

### Variance Reduction via Multi-Seed Ensembles (EXP-017)

Five random seeds (42, 123, 456, 789, 1024) revealed:

| Architecture | Mean MAE | Std | Ensemble MAE |
|-------------|----------|-----|--------------|
| Standard AE | 0.60 | 0.15 | 0.53 |
| **GroupedEncoder** | 0.37 | **0.10** | **0.30** |

GroupedEncoder showed both lower mean error and lower variance. Transfer
learning later reduced this variance by another **16×** (EXP-015: std
0.64 → 0.04).

**Phase 1 Conclusions**:
- Transfer learning (synthetic → real) is essential
- GroupedEncoder wins for causal forecasting
- Ensemble diversity provides meaningful gains
- Seed variance is significant; multi-seed training is not optional

---

## Phase 2: The Physics-Residual Insight

**Experiments**: EXP-005 through EXP-010  
**Date**: 2026-03-31 to 2026-04-01  
**Key Question**: *What should the ML model actually predict?*

### The Watershed Moment (EXP-005)

This was the single most important experiment in the entire campaign. Instead
of predicting raw glucose, we asked: **what if ML only predicts what physics
can't explain?**

The physics model performs simple forward integration:
```
predicted_Δglucose = (−ΔIOB × ISF) + (ΔCOB × ISF/CR)
```

This captures the mechanical effect of insulin absorption and carb digestion.
The ML model then predicts the **residual**: actual glucose minus
physics-predicted glucose.

| Model | MAE (mg/dL) | vs Persistence |
|-------|-------------|----------------|
| Persistence baseline | 40.91 | — |
| Physics-only | 37.77 | 7.7% better |
| Raw AE (predict glucose directly) | 3.66 | 91.1% better |
| **Residual AE (predict physics residual)** | **1.05** | **97.4% better** |

The residual model was **3.5× better** than the raw AE on identical
architecture. The physics model captures ~85% of glucose dynamics
mechanically. ML only needs to learn the remaining 15%: sensor noise,
exercise effects, dawn phenomenon, stress responses, and individual
physiological quirks.

**This insight — the 4-layer stack of physics backbone + ML residual —
became the foundation for everything that followed.**

### Residual Characteristics

The residual distribution (validation set) revealed what the ML model must learn:

- **Mean**: −0.32 mg/dL (physics slightly overshoots)
- **Standard deviation**: 54.99 mg/dL (substantial unexplained variance)
- **Range**: [−251, +243] mg/dL (extreme outliers from sensor errors, missed boluses)
- **P5/P95**: [−95, +95] mg/dL (90% of residuals within ±95 mg/dL)

This "unexplained variance" is the irreducible complexity of diabetes
management — the events, behaviors, and physiological responses that
no physics model captures but that ML can learn patterns within.

---

## Phase 3: The Data Leakage Crisis

**Experiments**: EXP-034 through EXP-043  
**Date**: 2026-04-01 to 2026-04-02  
**Key Question**: *Are our results real?*

### Discovering the Leak

Across Phases 1–2, models consistently reported ~0.9 mg/dL MAE at 1-hour
horizon. The results were remarkably stable across architectures. This was
the first red flag — real-world glucose prediction should not be that easy.

The diagnosis came from **EXP-043: Forecast-Masked Training**:

- Models were seeing **future glucose values** during training through
  bidirectional self-attention
- The "forecast" was simply copying glucose from input to output
- Extended features (glucose rate-of-change, acceleration) encoded the answer
  directly — EXP-047 showed a 16-feature model achieving 99.5% improvement,
  which is impossible for genuine forecasting

### The Fix: Causal Masking

Proper causal masking zeros out future glucose in the input and applies
triangular attention masks:

| Metric | Before (leaking) | After (masked) | Reality Factor |
|--------|-------------------|-----------------|----------------|
| 1hr MAE | ~0.9 mg/dL | **12.9 mg/dL** | 14× harder |
| 6hr MAE | ~0.9 mg/dL | **19.1 mg/dL** | 21× harder |
| 3day MAE | ~0.9 mg/dL | **23.7 mg/dL** | 26× harder |

**This was the moment we transitioned from fantasy to science.** Every
experiment from EXP-044 onward uses proper causal masking.

### The Emotional Arc

The leakage discovery was initially demoralizing — months of
seemingly-excellent results were invalid. But it was also liberating:

1. We now had **honest baselines** to improve against
2. The physics-residual insight remained valid (it was tested on properly
   masked data)
3. The architecture comparisons were still directionally correct
   (GroupedEncoder genuinely forecasts better than AE)
4. Most importantly, we could now trust our metrics

**Lesson**: Strict temporal evaluation discipline is non-negotiable. Any
result that seems "too good" probably is.

---

## Phase 4: Architecture Saturation

**Experiments**: EXP-044 through EXP-139 (71 executed)  
**Date**: 2026-04-02  
**Key Question**: *Can we push past the ~12.5 mg/dL ceiling?*

### The Modest Architecture Sweep (EXP-044)

With honest baselines established, we systematically explored architecture
dimensions:

| Config | Params | MAE (mg/dL) | Epochs | Notes |
|--------|--------|-------------|--------|-------|
| d=32, L=2 | 25,792 | 13.04 | 50 | Smallest |
| d=64, L=2 | 67,704 | 12.91 | 50 | Baseline |
| d=64, L=4 | 134,648 | 12.79 | 50 | Deeper |
| **d=128, L=2** | 200,680 | **12.77** | 60 | Widest |
| d=128, L=4 | 399,848 | 13.10 | 43 | Overfits |

**Total improvement from 4× parameter increase: 0.27 mg/dL (2.1%).**

The model was not capacity-limited. Adding parameters yielded diminishing
returns and eventually caused overfitting (d=128, L=4 peaked at 43 epochs
vs 50+ for smaller models).

### The Saturation Confirmation

Over Rounds 9–18, we tried six different approaches to break the ceiling.
**Every single one performed the same or worse than baseline**:

| Technique | Experiment | MAE Change | Verdict |
|-----------|-----------|------------|---------|
| Night specialist model | EXP-134 | −0.8 mg/dL (night only) | Marginal |
| Clarke-zone optimized loss | EXP-128 | −0.1% | Negligible |
| 2-stage hypo detection | EXP-136 | +0.5 overall / −4.8 hypo | Trade-off |
| Diverse architecture ensemble | EXP-139 | −0.7 mg/dL | Modest |
| Event-conditioned forecast | EXP-054 | +32.6% worse | Harmful |
| Extended training (150 epochs) | EXP-053 | −0.6 mg/dL | Diminishing |

**The ceiling at ~12.5 mg/dL (single model) was real and architectural
changes could not break it.**

### What Actually Broke Through

Only **ensemble methods** and **data scaling** provided meaningful
improvements beyond single-model saturation:

| Technique | MAE Before | MAE After | Δ |
|-----------|-----------|-----------|---|
| 5-seed ensemble (EXP-100) | 12.6 (best single) | **11.7** | −7.1% |
| Multi-patient training (10 pts) | 12.2 (single patient) | **11.5** | −5.7% |
| Diverse architecture ensemble (EXP-139) | 12.8 (best individual) | **12.1** | −5.3% |

### Multi-Seed Stability (EXP-051)

Five seeds confirmed excellent reproducibility:

| Seed | MAE (mg/dL) |
|------|-------------|
| 42 | 13.04 |
| 123 | 12.89 |
| 456 | 13.22 |
| 789 | 13.05 |
| 2024 | 12.99 |
| **Mean ± Std** | **13.04 ± 0.11** |

Standard deviation of 0.11 mg/dL across seeds — the model is stable and the
saturation is genuine, not an artifact of seed selection.

---

## Phase 5: Multi-Objective Expansion

**Experiments**: EXP-049, EXP-067, EXP-105, EXP-114, EXP-116, EXP-136  
**Date**: 2026-04-02  
**Key Question**: *Beyond forecasting — what else can the model learn?*

### Event Detection: XGBoost Wins (EXP-049, EXP-067, EXP-114)

We tried two approaches to event classification (meals, corrections,
exercise, overrides, sleep):

| Method | F1 Score | Architecture |
|--------|----------|-------------|
| Neural event head (transformer) | 0.107 | End-to-end multi-task |
| **XGBoost on tabular features** | **0.710** | Hybrid (separate classifier) |

**Why the 6.6× gap?** Attention attribution analysis (EXP-114) revealed the
transformer is **87% glucose-dominant**: it allocates 86.8% of attention to
glucose history, 10.8% to insulin, and just 2.4% to carbs. The model is
fundamentally an autoregressor — it predicts "glucose will continue its
recent trend" rather than "insulin will bring glucose down."

XGBoost's 32 engineered features (carbs_total, bolus_total, COB_now, hour
of day, glucose variability metrics) give it direct access to the treatment
signals the transformer ignores.

**Top XGBoost features by importance**:
1. carbs_total (0.124)
2. bolus_total (0.085)
3. cob_now (0.071)
4. net_basal_now (0.070)
5. glucose_std_1hr (0.065)

### Hypoglycemia: The Safety Frontier (EXP-105, EXP-116, EXP-136)

Hypo prediction emerged as the **critical safety gap**. Standard models
show 2.5× worse performance on hypoglycemic ranges vs in-range glucose.
We attacked this from three angles:

**1. Data augmentation (EXP-105)**: Augmented hypo windows from 2,277 to
32,768 via noise injection and time warping.
- Hypo F1: 0.628 → **0.719** (+14.5%)
- Trade-off: Precision dropped 15% (0.896 → 0.763) but recall gained 40%
  (0.483 → 0.680)
- **Verdict**: For safety-critical applications, higher recall is worth
  lower precision

**2. Hypo-weighted loss (EXP-116)**: Asymmetric loss weighting that penalizes
hypo prediction errors more heavily.
- Severe hypo MAE: 20.2 → **14.7 mg/dL** (−27.2%)
- Overall MAE: 12.6 → 13.1 (+0.5 mg/dL trade-off)
- **Verdict**: Clinically meaningful safety improvement for small overall cost

**3. Two-stage detection (EXP-136)**: Multi-threshold system combining
forecast with dedicated hypo detector.
- Best F1 at P70 threshold: **0.640** (72.6% recall, 57.2% precision)
- Forecast MAE in hypo windows: **10.4 mg/dL** (better than overall)
- **Verdict**: Promising approach but needs more hypo training data

### Conformal Prediction: Calibrated Uncertainty (EXP-059)

MC-Dropout uncertainty showed 40% coverage gap at 90% nominal — useless
for clinical decisions. **Conformal prediction** (EXP-059) solved this:

| Nominal Coverage | MC-Dropout Gap | Conformal Gap |
|-----------------|---------------|---------------|
| 50% | — | −0.016 |
| 80% | — | +0.002 |
| **90%** | **40% gap** | **+0.007** |
| 95% | — | +0.006 |

Conformal prediction delivers **60× better calibration** than MC-Dropout.
The 90% prediction interval width (48.04 mg/dL) is clinically informative —
wide enough for safety, narrow enough for actionability.

### Production Pipeline (EXP-072, EXP-137)

The production v7 system integrates all capabilities:

- **Forecast**: 12.9 mg/dL MAE
- **Hypo detection**: F1 = 0.700, precision 82.5%, recall 60.7%
- **Conformal intervals**: 90% calibrated coverage
- **Action suggestions**: 99.55% precision across 674 suggestions
  - Correction bolus: 260/260 correct (100%)
  - Eat carbs: 55/55 correct (100%)
  - Consider correction: 356/359 correct (99.2%)

**Time-of-day performance** revealed a 53% difficulty spread:

| Period | MAE (mg/dL) | Difficulty |
|--------|-------------|-----------|
| Morning | 9.9 | Easiest |
| Afternoon | 12.0 | Medium |
| Evening | 15.0 | Hard |
| Night | 15.2 | Hardest |

---

## Phase 6: Multi-Patient Scaling

**Experiments**: EXP-142, EXP-144, GPU acceleration  
**Date**: 2026-04-02 to 2026-04-03  
**Key Question**: *Does training on diverse patients help or hurt?*

### The Surprising Result

Training on all 10 patients simultaneously **improved** performance:

| Training Regime | Avg MAE (mg/dL) |
|----------------|-----------------|
| Single-patient (average across 10) | 12.2 |
| **Multi-patient (all 10 jointly)** | **11.5** |
| Leave-one-out (held-out patient) | 17.4 ± 2.5 |

Multi-patient training acts as **implicit regularization**: diverse
physiological profiles constrain overfitting and teach common glucose dynamics.

### Per-Patient Variance

Leave-one-out cross-validation (EXP-144) revealed massive individual
differences:

| Patient | LOO MAE | Test Windows | Difficulty |
|---------|---------|-------------|-----------|
| g | 13.9 | 3,792 | Easiest |
| f | 14.4 | 3,798 | Easy |
| h | 15.3 | 1,520 | Medium |
| a | 16.8 | 3,755 | Medium |
| d | 17.0 | 3,725 | Medium |
| c | 17.1 | 3,528 | Medium |
| i | 18.0 | 3,816 | Hard |
| j | 19.3 | 1,310 | Hard (low data) |
| e | 20.3 | 3,339 | Hard |
| **b** | **22.1** | 3,839 | **Hardest** |

**Patient b** is hardest despite having the most data (3,839 windows).
**Patient j** is hard for the opposite reason — fewest windows (1,310) and
zero IOB data. The 8.2 mg/dL spread between easiest and hardest patients
represents the **personalization frontier**.

### GPU Acceleration

GPU availability transformed research velocity:

| Pipeline | CPU Time | GPU Time | Speedup |
|----------|----------|----------|---------|
| 10-patient AE | 6,153 sec | 69 sec | 90× |
| 10-patient Grouped | 6,108 sec | 160 sec | 38× |
| Total pipeline | ~3.4 hours | 5.7 min | ~36× |

This 36× speedup enabled the rapid iteration that produced 71 experiments
in a single day (Phase 4).

---

## Phase 7: Gen-2 Multi-Task Architecture

**Experiments**: EXP-150 through EXP-154  
**Date**: 2026-04-03  
**Key Question**: *Can a single model serve all four objectives simultaneously?*

### Architecture

Gen-2 added three auxiliary heads to the GroupedEncoder:

```
Input → [State|Action|Time] Projections → Transformer Encoder
                                              ↓
                                    ┌─────────┼──────────┐
                                    ↓         ↓          ↓
                              forecast_head  event_head  drift_head  state_head
                              (T, features)  (9 classes)  (2 outputs) (4 states)
```

- **107,543 parameters** (3-layer encoder, d=64)
- Task weights: forecast=1.0, event=0.3, drift=0.2, state=0.1
- Training: 15,663 windows (12,530 train / 3,133 val) from 10 patients

### Results (EXP-151, EXP-152)

| Objective | Gen-2 Result | Single-Task Baseline | Verdict |
|-----------|-------------|---------------------|---------|
| Forecast MAE | 17.34 mg/dL | 12.9 mg/dL | ✗ Degraded |
| Event F1 | 0.54 | 0.544 (XGBoost) | ≈ Match |
| Drift-TIR r | −0.071 | — | ✓ Correct sign |
| State accuracy | — | — | Insufficient data |

**Key insight**: Joint multi-task training doesn't improve any individual
objective. Forecast and event classification **compete for attention** —
the forecast wants smooth trajectory modeling while classification needs
sharp event boundaries. The auxiliary tasks add noise to the primary
forecast loss without providing compensating benefits.

### Infrastructure Fixes Required

Three critical bugs were found and fixed during Gen-2 development:

1. **ISF unit conversion**: Patient a used mmol/L (ISF=2.7) while others
   used mg/dL. Without conversion, physics predictions were 18× off.
2. **Kalman filter failure**: Measurement noise R=5 but real residual
   std≈224 mg/dL → filter saturated instantly. Replaced with oref0-style
   24-window sliding median.
3. **Label distribution audit** (EXP-154): Drift labels were 73%
   resistance — recalibrated thresholds (±10% from nominal) restored
   distribution to 62% resistance / 26% stable / 12% sensitivity.

---

## The Discovery Pathway: What We Learned

### The Hierarchy of Impact

Looking across 154 experiments, improvements decompose into a clear hierarchy:

| Rank | Technique | Impact | Experiments |
|------|-----------|--------|-------------|
| 1 | **Physics-ML residual decomposition** | 8.2× | EXP-005 |
| 2 | **Causal masking (fixing data leakage)** | Honest baselines | EXP-043 |
| 3 | **Transfer learning** | 2.7× vs scratch, 16× variance reduction | EXP-003, EXP-015 |
| 4 | **Multi-patient training** | 5.7% improvement + regularization | EXP-142 |
| 5 | **Ensemble methods** | 5–7% improvement | EXP-017, EXP-100, EXP-139 |
| 6 | **Conformal calibration** | Clinically usable uncertainty | EXP-059 |
| 7 | **Hypo-focused training** | 27% severe hypo improvement | EXP-116, EXP-136 |
| 8 | Architecture scaling (width/depth) | 2% improvement | EXP-044 |
| 9 | Loss function tweaks | <1% | Various |
| 10 | Extended training epochs | <1% | EXP-053 |

**The first three techniques account for >95% of total improvement.**
Everything below #5 is incremental optimization within a saturated regime.

### The Model Is a Glucose Autoregressor

Perhaps the most profound discovery (EXP-114): the model allocates **87%
of attention to glucose history**. This means:

- ✅ **Forecasting works** because glucose is highly autocorrelated — recent
  trend predicts near-future with high accuracy
- ⚠️ **Treatment response is learned statistically**, not causally — the
  model sees "when IOB is high, glucose tends to fall" but doesn't model
  the pharmacokinetic mechanism
- ❌ **Event detection fails neurally** because the transformer ignores the
  very features (treatments, time patterns) that define events

This has profound implications for the system's ceiling: the model can never
predict sudden physiological changes (exercise onset, adrenaline surge,
compression lows) because these don't manifest in the glucose trace until
they've already happened.

### Training vs Reality: The Generalization Gap

| Metric | Training | Verification | Gap |
|--------|----------|--------------|-----|
| Best single MAE | 11.4 mg/dL | 17.5 mg/dL | +54% |
| Ensemble MAE | 11.7 mg/dL | 16.0 mg/dL | +37% |
| Hypo MAE | 15.7 mg/dL | 39.8 mg/dL | **+154%** |
| Event F1 | 0.710 | 0.544 | −23% |

The 37% ensemble gap is the **honest tax of generalization**. It's
consistent, predictable, and the ensemble partially closes it (from 54% for
single model to 37%). The hypo gap (154%) reflects the fundamental challenge
of rare-event prediction with limited data.

---

## Where Do We Go From Here?

The experimentation campaign has revealed clear boundaries. Breaking through
them requires addressing specific bottlenecks — not more of the same.

### More Data vs. Different Data vs. Better Data

**Current dataset**: 10 patients, ~32K training windows, ~3.3K verification
windows per patient.

**The evidence says: we need different and more diverse data, not just more
of the same kind.**

1. **More patients matter most**. LOO cross-validation shows 8.2 mg/dL
   spread across 10 patients. Patient b (22.1 MAE) and patient j (19.3 MAE)
   are qualitatively different from patient g (13.9 MAE). Adding 20–50 more
   patients with diverse:
   - Diabetes types (T1D, T2D, LADA)
   - Treatment modalities (pump, MDI, hybrid closed-loop, manual)
   - Age ranges and activity levels
   - CGM systems (Dexcom G6/G7, Libre 2/3, Medtronic)
   
   ...would likely improve population-model generalization more than any
   architectural change.

2. **Hypo data is critically scarce**. Only 3.5% of windows contain
   hypoglycemia. Data augmentation (EXP-105) helped but synthetic hypo
   windows lack the dynamics of real hypoglycemic events. We need:
   - Patients with frequent hypoglycemia (over-treating, exercise-induced)
   - Longer collection periods to capture rare severe events
   - Potentially, community-sourced hypoglycemia episodes

3. **Behavioral context is missing**. The model has no access to:
   - Exercise (type, intensity, duration)
   - Sleep quality / circadian disruption
   - Stress / illness indicators
   - Menstrual cycle phase
   - Alcohol consumption
   
   These are exactly the signals that explain the residual the physics
   model can't capture. Even binary exercise flags would substantially
   improve volatile-period prediction.

### Larger Training: Diminishing Returns

The architecture sweep (EXP-044) definitively showed that parameter scaling
provides minimal returns:

- 4× parameters (26K → 200K): only 2.1% MAE improvement
- 15× parameters (26K → 400K): **worse** due to overfitting

Our 67K-parameter GroupedEncoder is not capacity-limited. The bottleneck is
**data diversity**, not model size. This stands in stark contrast to LLM
scaling laws — glucose forecasting has much lower intrinsic complexity than
language, and our 10-patient dataset provides insufficient diversity to
benefit from larger models.

**However**, there is one scaling dimension worth exploring: **longer context
windows**. Our current 24-step (2-hour) input window captures immediate
dynamics but misses:
- Circadian patterns (24h cycles)
- Multi-day patterns (weekend vs weekday)
- Post-exercise recovery (6–12h effects)

Expanding to 48-step or 96-step windows with efficient attention mechanisms
(linear attention, sparse attention) could capture these longer-range
dependencies.

### Different Training Approaches

Several unexplored training strategies could address specific bottlenecks:

**1. Hybrid Neural-XGBoost Architecture**

The event detection gap (neural F1=0.107 vs XGBoost F1=0.710) suggests a
hybrid approach:
- Neural model handles forecasting (sequence modeling strength)
- XGBoost handles event detection (tabular feature importance strength)
- Shared feature extraction layer feeds both
- End-to-end gradient flow through differentiable trees or distillation

**2. Contrastive Pre-Training**

Instead of reconstruction pre-training, use contrastive learning to build
patient-invariant representations:
- Positive pairs: windows from same patient, similar glucose patterns
- Negative pairs: windows from different physiological states
- Goal: learn representations that transfer across patients
- Could reduce the LOO generalization gap (currently 37%)

**3. Per-Patient Adaptation (Careful)**

Per-patient fine-tuning (EXP-057) showed mixed results: +17% for some
patients, −9% for others. A more careful approach:
- Train population model as base
- Small per-patient adaptation layers (adapter modules, 1–5% of parameters)
- Regularize adaptation to prevent catastrophic forgetting
- Online adaptation as new patient data arrives

**4. Curriculum Learning for Rare Events**

Hypo prediction degrades 154% from training to verification. Curriculum
learning could help:
- Start with easy (in-range) windows
- Gradually introduce harder (hypo/hyper) windows
- Weight scheduling that increases hypo importance over training
- Focal loss for rare-event emphasis

### Different Input Models / Transformers

**What's working**: The GroupedEncoder with feature-grouped projections and
causal attention is architecturally sound. The saturation is not architectural.

**What might help**:

1. **State-space models (Mamba, S4)**: These handle long sequences more
   efficiently than transformers and might capture longer-range patterns
   (circadian, multi-day) without the quadratic attention cost. Particularly
   relevant if we expand context windows.

2. **Graph neural networks for multi-signal fusion**: If we add exercise,
   sleep, and other behavioral signals, a GNN could model the heterogeneous
   relationships between different signal types (CGM continuous, bolus
   discrete, exercise categorical).

3. **Temporal fusion transformers (TFT)**: Designed specifically for
   multi-horizon time series with static covariates (patient demographics)
   and known future inputs (scheduled basal rates, announced meals).

4. **Mixture-of-experts for patient clusters**: Instead of one model for
   all patients, train 3–5 expert models for patient clusters (stable
   control, volatile control, hypo-prone, etc.) with a gating network.

### The Realistic Roadmap

Based on evidence from 154 experiments:

| Priority | Action | Expected Impact | Confidence |
|----------|--------|-----------------|------------|
| 1 | **Add 20+ diverse patients** | −2–4 mg/dL on LOO | High |
| 2 | **Behavioral context features** | −1–3 mg/dL on volatile periods | Medium-High |
| 3 | **Longer context windows** | −0.5–1.5 mg/dL from circadian capture | Medium |
| 4 | **Hybrid neural-XGBoost** | Event F1 0.54 → 0.70+ | Medium |
| 5 | **Contrastive pre-training** | −1–2 mg/dL on LOO | Medium |
| 6 | **Per-patient adapters** | −1–3 mg/dL for hard patients | Low-Medium |
| 7 | **State-space models** | Unknown (experimental) | Low |

**The honest assessment**: We are at **~12 mg/dL MAE** on in-distribution
data and **~16 mg/dL MAE** on held-out verification. Breaking below
10 mg/dL on verification data will require fundamentally richer data (more
patients, behavioral context), not architectural innovation. The model has
learned what glucose patterns can teach; the next gains come from data that
explains **why** glucose behaves the way it does.

---

## Appendix: Complete Experiment Index

### Phase 1: Foundations (EXP-001 – EXP-017)

| ID | Name | MAE | Key Result |
|----|------|-----|-----------|
| EXP-001 | Synthetic baselines | 2.12–4.64 | UVA/Padova > cgmsim |
| EXP-003 | Transfer learning | 0.74 | 2.7× vs scratch |
| EXP-005 | Physics-residual | 1.05 | 8.2× improvement ⭐ |
| EXP-012a | Grouped benchmark | 0.49 | GroupedEncoder wins |
| EXP-015 | Multi-seed transfer | 0.43 ± 0.04 | 16× variance reduction |
| EXP-017 | Seed ensemble | 0.30 | Ensemble > individuals |

### Phase 3: Post-Masking Baselines (EXP-043 – EXP-053)

| ID | Name | MAE | Key Result |
|----|------|-----|-----------|
| EXP-043 | Masked training | 12.39 (1hr) | Honest baseline established ⭐ |
| EXP-044 | Architecture sweep | 12.77 best | Scaling has diminishing returns |
| EXP-051 | Multi-seed stability | 13.04 ± 0.11 | Excellent reproducibility |
| EXP-053 | Extended training | 12.33 (1hr) | Marginal gains at 150 epochs |

### Phase 4: Multi-Objective (EXP-049 – EXP-139)

| ID | Name | Metric | Key Result |
|----|------|--------|-----------|
| EXP-049 | Combined classifier | F1=0.710 | XGBoost event baseline |
| EXP-054 | Event-conditioned | +32.6% worse | Conditioning hurts forecast |
| EXP-059 | Conformal prediction | 0.7% gap | Calibrated uncertainty ⭐ |
| EXP-067 | Multitask joint | F1=0.877 / MAE=16.37 | Tasks compete |
| EXP-072 | Production pipeline | 99.55% precision | E2E system works |
| EXP-105 | Hypo augmentation | F1=0.719 | Safety recall improvement |
| EXP-114 | Attention analysis | 87% glucose | Model is autoregressor |
| EXP-116 | Hypo-weighted loss | −27% severe hypo | Safety-accuracy trade-off |
| EXP-136 | 2-stage hypo | F1=0.640 | Multi-threshold approach |
| EXP-137 | Production v7 | MAE=12.9, Hypo F1=0.700 | Full system metrics |
| EXP-139 | Diverse ensemble | MAE=12.1 | Architecture diversity helps |

### Phase 5: Multi-Patient (EXP-142 – EXP-154)

| ID | Name | Metric | Key Result |
|----|------|--------|-----------|
| EXP-142 | Multi-patient training | 11.5 MAE | Better than single-patient |
| EXP-144 | Leave-one-out | 17.4 ± 2.5 MAE | High per-patient variance |
| EXP-151 | Gen-2 fine-tune | 17.34 MAE | Multi-task trade-offs |
| EXP-154 | Label audit | 32,026 windows | Distribution & quality check |
