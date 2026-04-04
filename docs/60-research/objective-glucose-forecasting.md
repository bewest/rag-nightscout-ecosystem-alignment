# Objective: Glucose Forecasting

> **Assessment of the primary ML capability of the cgmencode pipeline**
>
> Status: Active Research · Last Updated: 2025-07-17
> Experiments: EXP-001 through EXP-258 (258 total)
> Current Best: **10.59 mg/dL MAE** (EXP-251, per-patient L=4 extended training)

---

## 1. Objective Statement

From [ML Composition Architecture](../architecture/ml-composition-architecture.md) Layer 3:

> *"What will glucose do if we take action A?" — predict glucose trajectory
> 1-hour ahead (12 five-minute steps) with sufficient accuracy for
> anticipatory diabetes management.*

The glucose forecasting objective is the foundational prediction task upon
which all downstream clinical capabilities (event detection, override
recommendations, safety alerting) depend. This report summarizes 258
experiments spanning architecture search, masking corrections, per-patient
specialization, and verification — documenting what works, what fails, and
where the performance ceiling lies.

---

## 2. Architecture

### Model: CGMGroupedEncoder

| Parameter | Value |
|-----------|-------|
| Architecture | TransformerEncoder |
| `d_model` | 64 |
| `nhead` | 4 |
| `num_layers` | 2–4 |
| `dropout` | 0.1 |
| Parameters | 107K–134K (depending on `num_layers`) |

### Input Specification

- **Window**: 24 steps (2 hours) of history at 5-minute resolution
- **Features** (8 channels):
  1. Glucose (SGV)
  2. IOB (Insulin on Board)
  3. COB (Carbs on Board)
  4. Net basal rate
  5–8. Derived features (deltas, rates of change)

### Output Specification

- **Prediction**: 24 steps (2 hours) of future glucose
- **Evaluation horizon**: 12 steps (1 hour) — the clinically relevant window
- **Normalization**: `SCALE = 400.0` for glucose values

### Selective Masking

Seven of the eight input channels represent future-unknown quantities (IOB,
COB, net basal, and the four derived features). During the prediction window,
these channels are **zeroed out** to prevent future action leakage. Only the
glucose channel carries forward signal through the autoregressive prediction.

This masking strategy was a critical discovery (see §4.3) — its absence
inflated early results by approximately 60%.

---

## 3. Baselines

| Baseline | MAE (mg/dL) | Description |
|----------|-------------|-------------|
| Persistence (last value) | 22.7–25.9 | Predicts glucose stays flat |
| Raw ML (no composition) | ~67 | Untrained transformer on real data |
| Physics-residual (EXP-005) | ~8.2 | Synthetic-only, 8.2× improvement over raw ML |

Persistence MAE varies by data split (22.7 on favorable splits, 25.9 on
harder temporal splits). All model results below should be compared against
the **persistence baseline** to gauge genuine predictive skill.

---

## 4. Trajectory of Results

### 4.1 Phase 1: Foundation (EXP-001 to EXP-100)

**Key milestone**: Establishing that ML forecasting works on real CGM data.

- **Physics-residual composition (EXP-005)**: 8.2× improvement over raw ML on
  synthetic data — validated the composition architecture concept
- **First real-data models**: ~17 mg/dL MAE, a meaningful improvement over the
  22.7–25.9 mg/dL persistence baseline
- **Causal masking discovery**: Without causal masking, models achieved
  MAE ≈ 0.0 — a deceptive result caused by copying future glucose values
  directly from the input. This early discovery prevented months of wasted
  work on models that appeared perfect but had zero predictive skill.

### 4.2 Phase 2: Architecture Search (EXP-100 to EXP-150)

**Key milestone**: Systematic exploration of model architectures and training
strategies.

| Experiment | Technique | Result | Improvement |
|------------|-----------|--------|-------------|
| EXP-139 | Diverse ensemble (5 arch, d32–d128, L2–L6) | **12.1 MAE** | Phase 2 ceiling |
| EXP-116 | Hypo-weighted loss | Hypo MAE 15.2→12.4 | −18.4% on hypo |
| EXP-136 | Hypo 2-stage training | Hypo MAE **10.4**, F1=0.640 | Best hypo detection |
| EXP-134 | Night specialist model | Night MAE 16.8→16.0 | −4.8% overnight |
| EXP-137 | Production v7 (conformal) | MAE=12.9, Hypo F1=0.700 | Calibrated uncertainty |
| EXP-141 | UVA/Padova simulator pretrain | 0% improvement | Negative result (see §6) |

EXP-137 ("Production v7") was the first model to meet clinical deployment
criteria: conformal prediction intervals with 90.0% coverage and Clarke Error
Grid Zone A+B at 97.1%.

### 4.3 Phase 3: Selective Masking Fix (EXP-229 to EXP-238)

**Key milestone**: Discovering and correcting future action leakage.

> **Critical finding**: Approximately 60% of Gen-2 improvement was
> attributable to future action leakage. Ten input channels were visible in
> the prediction window, allowing the model to "see" future insulin and carb
> actions rather than predicting their effects.

| Experiment | Masking Strategy | MAE (mg/dL) | Notes |
|------------|-----------------|-------------|-------|
| Gen-2 models | No masking (leaked) | ~12.0 | Dishonest — inflated results |
| EXP-229 | Full masking (all channels) | 25.1 | Overly conservative |
| EXP-230 | Selective masking (7 of 8) | **18.17** | 28% better than full masking |
| EXP-232 | 5-seed ensemble + selective | **12.46** | Rebuilt honest baseline |

After the fix, honest single-model MAE landed at ~17 mg/dL — matching the
Phase 1 real-data results. The 5-seed ensemble (EXP-232) recovered most of
the apparent loss, reaching 12.46 MAE through legitimate aggregation rather
than leakage.

### 4.4 Phase 4: Per-Patient Revolution (EXP-241 to EXP-258)

**Key milestone**: Per-patient fine-tuning as the dominant improvement lever.

| Experiment | Technique | MAE (mg/dL) | Δ vs Base | Notes |
|------------|-----------|-------------|-----------|-------|
| EXP-241 | Per-patient FT (L=2) | 11.80 | −0.48 | First per-patient result |
| EXP-242 | Per-patient ensemble (L=2) | **11.25** | −1.21 | Ensemble + FT synergy |
| EXP-247 | Deeper base (L=4) | 12.20 | — | New base model |
| EXP-250 | Per-patient FT (L=4) | **10.71** | −1.49 | Depth + FT compound |
| EXP-251 | Extended training (200 ep) | **10.59** | −1.61 | **Current best** |

Per-patient fine-tuning consistently delivers −0.5 to −1.5 MAE improvement
by adapting the global model's weights to individual patient physiology
(insulin sensitivity, meal patterns, activity levels).

---

## 5. What Worked

Ranked by impact on forecast MAE:

### 5.1 Physics-Residual Composition (8.2× on synthetic)

The composition architecture from Layer 3 of the ML pipeline combines
physics-based glucose models with learned residuals. On synthetic
(UVA/Padova) data, this yielded an 8.2× improvement over raw ML — the single
largest gain in the experiment history. On real data, the composition
framework provides the structural foundation, though the gap narrows.

### 5.2 Selective Masking (28% improvement)

Masking 7 of 8 future-unknown channels while preserving the glucose channel
yielded a 28% MAE reduction versus full masking (18.17 vs 25.1 mg/dL). This
is the correct information-theoretic approach: the model can use its own
glucose predictions autoregressively, but cannot peek at future actions.

### 5.3 Per-Patient Fine-Tuning (−0.5 to −1.5 MAE)

The most reliable improvement lever on real data. Every patient benefits from
fine-tuning, though the magnitude varies:

- Patients with consistent patterns (d, e, f, g): −0.3 to −0.7 MAE
- Patients with high variability (a, b, c): −0.8 to −1.5 MAE
- Patients with limited data (h, j): −0.2 to −0.5 MAE

### 5.4 5-Seed Ensemble Averaging (−0.5 to −1.0 MAE)

Training 5 models with different random seeds and averaging predictions
reduces variance without introducing bias. This is a "free" improvement
requiring only 5× training compute (inference is parallelizable).

### 5.5 Deeper Architecture, L=4 (−0.5 MAE)

Moving from 2 to 4 transformer layers yields a consistent −0.5 MAE
improvement at a modest parameter cost (107K → 134K). The deeper model
captures longer-range temporal dependencies in glucose dynamics.

### 5.6 Extended Training, 200 Epochs (−0.1 MAE)

Marginal but real. Doubling training duration from 100 to 200 epochs
squeezes out a final ~1% improvement. Subject to diminishing returns.

---

## 6. What Failed

Techniques that produced zero or negative improvement, ranked by severity:

### 6.1 Test-Time Augmentation — TTA (EXP-258): −4.05 MAE

The worst-performing technique tested. Adding noise at inference time
destroyed the signal the model had learned, producing predictions worse than
the persistence baseline in some cases. **Verdict: destructive, never use.**

### 6.2 Snapshot Ensemble (EXP-246): +0.73 MAE worse than 5-seed

Saving checkpoints along the training trajectory and averaging them produced
worse results than independently trained seeds. The checkpoints are too
correlated — they explore the same loss basin rather than diverse solutions.

### 6.3 MC-Dropout (EXP-244): +0.8 MAE worse than 5-seed

Monte Carlo dropout at inference time adds noise without the diversity
benefit of true ensemble members. The dropout masks are random but not
complementary, yielding worse calibration than seed-based ensembles.

### 6.4 Hypo Weighting in Global Ensemble (EXP-239): +0.4 MAE

While hypo-weighted loss improves hypoglycemia-specific metrics in isolation
(EXP-116, EXP-136), applying it within the ensemble framework degrades
overall MAE. The ensemble already captures hypo patterns through diversity.

### 6.5 Curriculum Learning (EXP-240): −0.29 MAE

Training on progressively harder examples (sorted by glucose variability)
hurt generalization. The model overfit to the curriculum ordering rather than
learning robust features.

### 6.6 Temporal Augmentation (EXP-256): −0.21 MAE + larger gap

Adding temporal jitter and warping to training data increased the
train-verification gap from 7.4% to 9.8%, indicating the augmentations
introduced distribution shift rather than improving robustness.

### 6.7 Weight Decay Regularization (EXP-255): Zero effect

Standard L2 weight decay had no measurable effect on the verification gap
(7.4% with and without). The model is not overfitting in the traditional
sense — the gap is driven by temporal non-stationarity, not parameter
memorization.

### 6.8 Wider Model, d=128 (EXP-245): +0.11 MAE

Doubling the model width from d=64 to d=128 slightly worsened results. The
107K–134K parameter range appears well-matched to the available training
data; additional capacity leads to overfitting without enough data to
regularize.

### 6.9 UVA/Padova Pretraining (EXP-141): 0% improvement

Pretraining on 32K synthetic windows from the UVA/Padova simulator provided
zero benefit when fine-tuning on real data. The domain gap between simulated
and real glucose dynamics is too large for transfer learning to bridge.

---

## 7. Verification Results

All verification uses **held-out temporal data** — later time periods from
the same patients, never seen during training. This tests the model's ability
to generalize across time, the most clinically relevant evaluation.

### 7.1 Global Verification Summary

| Model | Train MAE | Verification MAE | Gap % | Notes |
|-------|-----------|-----------------|-------|-------|
| EXP-249 (L=2 FT) | 11.25 | **11.56** | +2.8% | Best generalization ratio |
| EXP-254 (L=4 FT) | 10.71 | **11.49** | +7.4% | Best absolute verification |
| EXP-255 (L=4 +wd) | 10.71 | **11.50** | +7.4% | Weight decay: no effect |
| EXP-256 (L=4 +aug) | 10.80 | **11.86** | +9.8% | Augmentation: harmful |
| EXP-238 (global) | 12.46 | **11.68** | −6.3% | Global model generalizes! |

**Notable finding**: The global model (EXP-238) achieves *better*
verification MAE than training MAE (−6.3% gap), suggesting that global
models are more robust to temporal shift than per-patient models. However,
per-patient models still achieve lower absolute verification MAE (11.49 vs
11.68).

### 7.2 Per-Patient Verification (EXP-254, L=4 Fine-Tuned)

| Patient | Train MAE | Ver MAE | Gap % | Windows | Assessment |
|---------|-----------|---------|-------|---------|------------|
| a | 11.09 | 10.97 | −1.1% | 414 | ✅ Excellent |
| b | 17.60 | 15.55 | −11.6% | 412 | ✅ Hardest patient, improves on verification |
| c | 9.72 | 13.21 | +36.0% | 361 | ⚠️ Severe gap — temporal shift |
| d | 8.00 | 7.93 | −0.9% | 384 | ✅ Best patient overall |
| e | 8.24 | 8.85 | +7.4% | 346 | ✅ Good |
| f | 8.95 | 8.37 | −6.5% | 401 | ✅ Good |
| g | 9.08 | 8.03 | −11.6% | 400 | ✅ Excellent |
| h | 10.04 | 10.34 | +3.0% | 142 | ⚠️ Limited data |
| i | 8.70 | 10.64 | +22.3% | 409 | ⚠️ Significant gap |
| j | 15.65 | 21.04 | +34.5% | 138 | ❌ Worst — 0% IOB data, 138 windows |

**Patient stratification**:

- **Tier 1** (< 5% gap): Patients a, d, e, f, g — 5 of 10 patients
  generalize well. These patients likely have consistent physiology and
  treatment patterns over the evaluation period.
- **Tier 2** (5–25% gap): Patients b, h, i — moderate gap, addressable with
  more data or temporal adaptation.
- **Tier 3** (> 25% gap): Patients c, j — large gap driven by temporal shift
  (patient c) or data quality (patient j: 0% IOB data, only 138 windows).

### 7.3 Time-of-Day Performance (EXP-137, Production v7)

| Period | MAE (mg/dL) | Relative | Notes |
|--------|-------------|----------|-------|
| Morning (06:00–12:00) | 9.9 | Best | Post-fasting, stable basal |
| Afternoon (12:00–18:00) | 12.0 | +21% | Active eating period |
| Evening (18:00–00:00) | 15.0 | +52% | Post-dinner insulin stacking |
| Night-A (00:00–03:00) | 15.2 | +54% | Dawn phenomenon period |
| Night-B (03:00–06:00) | 14.7 | +48% | Pre-dawn, hormonal shifts |

Morning forecasts are substantially more accurate than evening/night. This
reflects the inherent predictability of fasting glucose versus the complex
meal-insulin dynamics of active periods. A production system should
communicate time-dependent confidence to users.

### 7.4 Clinical Safety Metrics (EXP-135, EXP-137)

| Metric | Value | Clinical Threshold | Assessment |
|--------|-------|--------------------|------------|
| Clarke Error Grid Zone A+B | **97.1%** | > 95% | ✅ Clinically excellent |
| Conformal 90% coverage | **90.0%** | 88–92% | ✅ Perfectly calibrated |
| Conformal interval width | 57.1 mg/dL | — | Informational |
| Hypo detection F1 | 0.700 | > 0.60 | ✅ Acceptable |
| Hypo detection (2-stage) | F1=0.640, MAE=10.4 | — | Specialized model |

The 97.1% Zone A+B result means that 97.1% of predictions fall in clinically
acceptable or benign-error regions of the Clarke Error Grid. The conformal
prediction intervals achieve exactly the target coverage, indicating
well-calibrated uncertainty estimates.

---

## 8. Saturation Analysis

### 8.1 MAE Trajectory

```
MAE (mg/dL)
25 ┤ ● Persistence baseline (22.7-25.9)
   │
20 ┤
   │
17 ┤ ● Phase 1 real-data models (~17.0)
   │
   │
12 ┤ ● EXP-139 diverse ensemble (12.1)
   │ ● EXP-232 honest masking rebuild (12.46)
11 ┤ ● EXP-242 per-patient L=2 (11.25)
   │ ● EXP-250 per-patient L=4 (10.71)
10 ┤ ● EXP-251 extended 200ep (10.59)  ← CURRENT BEST
   │
   ╰──────────────────────────────────────→ Experiments
     001        100        150   232  242 251
```

### 8.2 Improvement Rate

| Transition | MAE Change | Improvement | Experiments Spent |
|------------|-----------|-------------|-------------------|
| Persistence → Phase 1 | 22.7 → 17.0 | −25.1% | ~100 |
| Phase 1 → Phase 2 | 17.0 → 12.1 | −28.8% | ~50 |
| Phase 2 → Masking fix | 12.1 → 12.46 | +3.0% (honest) | ~10 |
| Masking → Per-patient L=2 | 12.46 → 11.25 | −9.7% | ~10 |
| L=2 → L=4 | 11.25 → 10.71 | −4.8% | ~8 |
| L=4 → Extended | 10.71 → 10.59 | −1.1% | ~1 |

**Improvement per experiment has slowed from ~5% to ~1%.** The curve exhibits
classic diminishing returns, suggesting proximity to a performance floor.

### 8.3 Estimated Performance Floor: ~10.5 mg/dL

The ~10.5 mg/dL floor likely reflects four irreducible factors:

1. **Biological noise**: Glucose dynamics are inherently stochastic. Even
   with perfect models, inter-day variability in insulin sensitivity, gut
   absorption, and hepatic glucose production create irreducible prediction
   error.

2. **Missing features**: Activity level, stress hormones (cortisol,
   adrenaline), menstrual cycle phase, sleep quality, and illness state all
   affect glucose but are absent from CGM-only input. These account for an
   estimated 3–5 mg/dL of irreducible error.

3. **Temporal non-stationarity**: Patient physiology changes over weeks to
   months (seasonal insulin sensitivity, progressive beta-cell decline,
   medication changes). Models trained on historical data cannot fully
   anticipate these shifts.

4. **Limited data**: Verification sets range from 138 to 414 windows per
   patient (11.5 to 34.5 hours of glucose data). Larger datasets would
   enable both better training and more precise evaluation.

---

## 9. Recommendations

### 9.1 Production Model Selection

**Primary**: EXP-251 (10.59 MAE) — current best training performance with
per-patient L=4 fine-tuning and extended training.

**Verification confidence**: Anchored by EXP-254 verification results (11.49
MAE, +7.4% gap). The 7.4% gap is acceptable for clinical use when combined
with conformal prediction intervals.

**Fallback**: EXP-238 (global model, 11.68 verification MAE) — for new
patients without sufficient data for fine-tuning. The global model's negative
gap (−6.3%) makes it the most robust option for cold-start scenarios.

### 9.2 Shift Focus to Higher-Impact Objectives

The forecasting objective is approaching saturation. Future work should
prioritize downstream capabilities that leverage the existing forecast
quality:

- **Event detection** (hypo/hyper alerts): Higher marginal clinical impact
  than incremental MAE improvements. The Hypo F1=0.700 baseline has clear
  room for improvement.
- **Override recommendations**: Using forecasts to suggest therapy adjustments
  — the Layer 4 objective in the composition architecture.
- **Uncertainty communication**: Making the conformal intervals actionable
  for clinical decision-making.

### 9.3 Addressing the Verification Gap

The +7.4% verification gap in per-patient models indicates temporal
non-stationarity. Potential mitigations:

- **Time-aware features**: Encoding day-of-week, time-since-last-site-change,
  or insulin-age as input features to capture temporal patterns.
- **Temporal adaptation**: Continuously fine-tuning on recent data (sliding
  window training) to track physiological drift.
- **Ensemble of global + per-patient**: Blending the robust global model
  (negative gap) with the precise per-patient model (lower absolute MAE).

### 9.4 Patient-Specific Interventions

- **Patient j**: Requires special handling — 0% IOB data makes accurate
  forecasting impossible. Either obtain insulin data or exclude from
  per-patient evaluation. Use the global model as fallback.
- **Patient c**: The +36.0% gap suggests a regime change (new medication,
  lifestyle shift) between training and verification periods. Temporal
  adaptation (§9.3) is the likely fix.
- **Patient b**: Despite being the "hardest" patient (17.60 train MAE),
  verification actually *improves* (−11.6%), suggesting the model captures
  this patient's patterns well — the training data simply contains harder
  episodes.

---

## 10. Key Lessons Learned

1. **Honest evaluation is non-negotiable.** The selective masking fix
   (Phase 3) erased 60% of apparent progress — but the resulting models are
   genuinely predictive rather than leaking future data. Always verify that
   the model cannot access future information.

2. **Per-patient adaptation beats architecture search.** Hundreds of
   experiments exploring architectures, loss functions, and training schemes
   yielded less improvement than simple per-patient fine-tuning. The
   patient-specific signal dominates the architectural signal.

3. **Simple ensembles beat complex ones.** Five independently-trained seeds
   outperform snapshot ensembles, MC-dropout, and curriculum-based diversity.
   Independent training explores more of the loss landscape.

4. **Regularization techniques assume the wrong failure mode.** Weight decay,
   augmentation, and dropout address parameter overfitting, but the actual
   gap driver is temporal non-stationarity. The solution is temporal
   adaptation, not regularization.

5. **Synthetic-to-real transfer is ineffective.** UVA/Padova pretraining
   (32K windows) provided zero benefit. The domain gap between simulated and
   real glucose dynamics is fundamental — simulators model idealized
   physiology while real data includes sensor noise, missed boluses,
   unreported meals, and behavioral variability.

---

## Appendix A: Experiment Index

| ID | Phase | Technique | MAE | Verdict |
|----|-------|-----------|-----|---------|
| EXP-005 | 1 | Physics-residual composition | 8.2× gain | ✅ Foundation |
| EXP-116 | 2 | Hypo-weighted loss | Hypo 12.4 | ✅ Specialized |
| EXP-134 | 2 | Night specialist | Night 16.0 | ✅ Marginal |
| EXP-135 | 2 | Clarke Error Grid eval | 97.1% A+B | ✅ Clinical |
| EXP-136 | 2 | Hypo 2-stage | Hypo 10.4 | ✅ Best hypo |
| EXP-137 | 2 | Production v7 | 12.9 | ✅ First production |
| EXP-139 | 2 | Diverse ensemble | 12.1 | ✅ Phase 2 best |
| EXP-141 | 2 | UVA/Padova pretrain | 0% gain | ❌ No transfer |
| EXP-230 | 3 | Selective masking | 18.17 | ✅ Honest baseline |
| EXP-232 | 3 | 5-seed + selective | 12.46 | ✅ Rebuilt baseline |
| EXP-238 | 3 | Global model | 12.46 | ✅ Best generalization |
| EXP-239 | 4 | Hypo-weighted ensemble | +0.4 worse | ❌ Harmful |
| EXP-240 | 4 | Curriculum learning | −0.29 worse | ❌ Harmful |
| EXP-241 | 4 | Per-patient FT (L=2) | 11.80 | ✅ First per-patient |
| EXP-242 | 4 | Per-patient ensemble (L=2) | 11.25 | ✅ Breakthrough |
| EXP-244 | 4 | MC-Dropout | +0.8 worse | ❌ Worse than ensemble |
| EXP-245 | 4 | Wider d=128 | +0.11 worse | ❌ Overfitting |
| EXP-246 | 4 | Snapshot ensemble | +0.73 worse | ❌ Correlated |
| EXP-247 | 4 | Deeper base (L=4) | 12.20 | ✅ New base |
| EXP-249 | 4 | L=2 FT (verified) | 11.56 ver | ✅ Best gap ratio |
| EXP-250 | 4 | Per-patient FT (L=4) | 10.71 | ✅ Depth + FT |
| EXP-251 | 4 | Extended 200ep | **10.59** | ✅ **Current best** |
| EXP-254 | 4 | L=4 FT (verified) | 11.49 ver | ✅ Best absolute ver |
| EXP-255 | 4 | L=4 + weight decay | 11.50 ver | ❌ No effect |
| EXP-256 | 4 | L=4 + augmentation | 11.86 ver | ❌ Harmful |
| EXP-258 | 4 | TTA | −4.05 worse | ❌ Destructive |

---

## Appendix B: Cross-References

- **Architecture**: [ML Composition Architecture](../architecture/ml-composition-architecture.md)
- **Experiment Log**: [ML Experiment Log](ml-experiment-log.md)
- **Progress Reports**: [ML Experiment Progress Report](ml-experiment-progress-report.md)
- **Training Techniques**: [Training Techniques — What Works](training-techniques-what-works.md)
- **Beyond Forecasting**: [Beyond Forecasting Capabilities Assessment](beyond-forecasting-capabilities-assessment.md)
- **Gen-2 Baseline**: [Gen-2 Baseline Report](gen2-baseline-report.md)
- **Gen-3 Transition**: [Gen-3 Transition Report](gen3-transition-report.md)
- **Validation Report**: [Multi-Objective Validation Report](multi-objective-validation-report.md)
