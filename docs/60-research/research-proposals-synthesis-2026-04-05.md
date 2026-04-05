# Research Proposals Synthesis: CGM/AID Multi-Objective Intelligence

**Date**: 2026-04-05  
**Based on**: 327 experiments (EXP-001–327), independently verified  
**Purpose**: Map each research objective to its required validation metrics, learning
pipeline, encoding strategy, and next experiments — providing a comprehensive roadmap
for the CGM/AID intelligence system.

---

## 1. Executive Summary

The research program has established five distinct objectives for CGM/AID intelligence,
each requiring fundamentally different approaches. This report synthesizes the verified
findings into actionable proposals, organizing them by:

- **Validation metrics** — what success looks like for each objective
- **Learning pipeline** — how to train and evaluate
- **Encoding strategy** — what data representation to use
- **Architecture** — what model structure
- **Next experiments** — prioritized by expected impact

### The Five Objectives at a Glance

| # | Objective | Maturity | Best Metric | Pipeline Type | Architecture |
|---|-----------|----------|-------------|---------------|--------------|
| 1 | Glucose Forecasting | ✅ Mature | MAE=11.25 mg/dL | Supervised regression | Transformer + physics |
| 2 | Event Detection (UAM/Hypo) | 🟡 Strong | F1=0.939 (UAM) | Supervised classification | 1D-CNN |
| 3 | ISF Drift Tracking | 🟡 Method proven | 9/11 sig. | Statistical time-series | Rolling aggregation |
| 4 | Pattern Retrieval | 🟠 Early | Sil=+0.326 | Metric learning | Transformer encoder |
| 5 | Override Recommendation | 🟡 Strong | F1=0.852 (15min) | Multi-task classification | Attention/CNN |

**Key insight**: No single pipeline serves all objectives. The system needs three
parallel pipelines (fast 2h, weekly 7d, rolling biweekly) with objective-specific
training, evaluation, and deployment strategies.

---

## 2. Objective 1: Glucose Forecasting

### Status: ✅ Mature — Diminishing Returns

**Current best**: MAE = 11.25 mg/dL (EXP-242), verified MAE = 11.14 (EXP-302).
Architecture-saturated at ~29.5 mg/dL RMSE regardless of model size (55K–993K params).

### Validation Metrics

| Metric | Current | Target | Rationale |
|--------|---------|--------|-----------|
| **MAE (mg/dL)** | 11.25 | <10.0 | Primary accuracy measure |
| **Verification gap** | 2.8% | <5% | Generalization indicator |
| **Hypo zone MAE** | 10.1 | <8.0 | Safety-critical region |
| **Clarke Error Grid %A+B** | — | >99% | Clinical acceptability |
| **RMSE (mg/dL)** | 29.5 | <25.0 | Sensitivity to outliers |

### Learning Pipeline

```
Data: 8 channels × 24-step (2h) windows, 5-min resolution
Split: Per-patient 80/20 temporal split
Pre-train: Optional synthetic (UVA/Padova) → real fine-tune
Training: MSE loss, 100 epochs base + 30 epochs per-patient FT
Regularization: Channel dropout 0.15 (ch_drop)
Ensemble: 5-seed mean (EXP-302 protocol)
Masking: Channels [0,4,5,12,13,14,15] masked in forecast window
Evaluation: MAE, RMSE, Clarke Error Grid, per-zone MAE
```

### Encoding Strategy

- **Features**: 8 base channels (glucose, IOB, COB, basal, bolus, carbs, time_sin, time_cos)
- **Window**: 24 steps (2h context) → 12 steps (1h forecast)
- **Normalization**: glucose/400, IOB/10, COB/100, basal/10, bolus/10, carbs/100
- **Note**: Extended features (21f, 39f) consistently overfit (14-29% gaps). 8f is
  the production standard.

### Architecture

- **Model**: 67K-param Transformer with grouped convolution encoder
- **Physics residual**: ΔG = -ΔIOB × ISF + ΔCOB × ISF/CR + liver production
- **Per-patient FT**: 30 epochs on individual patient data (only remaining lever)

### Proposed Next Experiments

| Priority | Experiment | Expected Impact | Success Criterion |
|----------|-----------|----------------|-------------------|
| Low | Longer patient histories | +5-10% MAE | MAE < 10.0 |
| Low | CAGE/SAGE device features | Unknown | Δ MAE > 0.5 |
| Low | Probabilistic forecasting | Calibrated intervals | Coverage > 90% at 80% CI |

**Rationale**: Forecasting is the most mature objective. Further gains require more
data (more patients, longer timelines) rather than architecture changes. Research
investment should prioritize the less-mature objectives.

---

## 3. Objective 2: Event Detection (UAM, Hypoglycemia)

### Status: 🟡 Strong UAM, Improving Hypo

**UAM**: F1=0.939 (EXP-313) — production-viable.  
**Hypo**: F1=0.676 (EXP-322+324 multi-task+Platt) — viable with calibration.  
**Key finding**: Hypo F1 is data-limited (6.4% prevalence), not architecture-limited
(CNN, attention, and ensemble all plateau at ~0.66).

### Validation Metrics

| Metric | UAM Current | Hypo Current | Target | Rationale |
|--------|-------------|-------------|--------|-----------|
| **F1 (positive class)** | 0.939 | 0.676 | >0.70 hypo | Primary performance |
| **AUC-ROC** | — | 0.958 | >0.95 | Discrimination ability |
| **ECE (calibration)** | — | 0.010 | <0.02 | Probability reliability |
| **Sensitivity (recall)** | 0.934 | 0.665 | >0.80 hypo | Miss rate for safety |
| **PPV at clinical threshold** | 0.944 | ~0.50 | >0.30 hypo | Acceptable alarm rate |
| **Lead time** | Real-time | 15-60 min | 15 min | Actionability |
| **LOO degradation** | — | -4.0% | <5% | Cross-patient viability |

### Learning Pipeline

```
UAM Pipeline:
  Data: 8ch × 24-step (2h), ~29K train windows
  Labels: Binary (UAM event present in window)
  Training: 1D-CNN, weighted BCE (prevalence-balanced), 30 epochs
  Evaluation: Positive-class F1, precision, recall

Hypo Pipeline:
  Data: 8ch × 24-step (2h), ~29K train windows  
  Labels: Multi-task (override + hypo dual heads)
  Training: 1D-CNN shared backbone, weighted BCE, 30 epochs
  Post-processing: Platt scaling (essential — ECE 0.21→0.01)
  Threshold: Optimized per-task (hypo threshold ~0.28 after Platt)
  Evaluation: F1, AUC, ECE, sensitivity, PPV
```

### Encoding Strategy

- **Features**: 8 base channels only (feature engineering hurts CNN — EXP-316, EXP-320)
- **Window**: 24 steps (2h) — longer windows catastrophically degrade UAM (F1 0.40→0.07)
- **Labels**: Forward-looking (will glucose cross threshold in next N minutes)
- **Class weighting**: Inverse prevalence for positive class

### Architecture

- **UAM**: 1D-CNN (8→32→64 channels, 3 kernel sizes)
- **Hypo**: Multi-task 1D-CNN (shared backbone + dual classification heads)
- **Post-processing**: Platt calibration sigmoid (trivial compute cost)
- **Do NOT use**: Embedding features, cross-scale concatenation, engineered IOB features

### Proposed Next Experiments

| Priority | Experiment | Expected Impact | Success Criterion |
|----------|-----------|----------------|-------------------|
| **High** | Multi-seed replication (EXP-313) | Confidence intervals | σ(F1) < 0.02 |
| **High** | Time-split hold-out evaluation | True temporal generalization | Δ F1 < 5% |
| Medium | Data augmentation (time-warp, jitter) | +2-5% hypo F1 | Hypo F1 > 0.70 |
| Medium | Curriculum learning (easy→hard) | Better convergence | Hypo F1 > 0.70 |
| Medium | Per-patient Platt calibration | Better individual thresholds | Per-patient ECE < 0.02 |
| Low | Synthetic hypo oversampling | More training signal | Hypo recall > 0.80 |
| Low | GAN-based minority generation | Diverse hypo patterns | Hypo F1 > 0.72 |

---

## 4. Objective 3: ISF Drift Tracking

### Status: 🟡 Method Proven — Needs Clinical Integration

**Current best**: 9/11 patients show significant biweekly ISF drift (EXP-312).  
**Key finding**: Statistical methods (rolling averages + Spearman correlation) beat ML
approaches. Neural networks add complexity without benefit for trend detection.

### Validation Metrics

| Metric | Current | Target | Rationale |
|--------|---------|--------|-----------|
| **Significant patients (p<0.05)** | 9/11 | N/A | Method validation |
| **Variance reduction vs per-cycle** | 3-8× | >3× | Signal quality |
| **Detection latency (days)** | 14 | <10 | Actionability |
| **False alarm rate** | — | <20% | Clinical trust |
| **Spearman |ρ|** | 0.16-0.47 | >0.15 | Trend strength |
| **Direction accuracy** | 2 groups identified | Validated | Clinical utility |

### Learning Pipeline

```
No ML training required.

Pipeline:
  1. Identify 6h non-overlapping insulin cycles (EXP-309 protocol)
  2. Compute ISF_effective = glucose_change / insulin_delivered per cycle
  3. Rolling biweekly (14-day) mean of ISF_effective
  4. Spearman rank correlation test for temporal trend
  5. OLS slope for direction and magnitude
  6. Alert if |ρ| > 0.15 AND p < 0.05 over rolling 30-day lookback

Evaluation:
  - Spearman significance count (threshold p<0.05)
  - Variance reduction ratio (rolling std / per-cycle std)
  - Concordance with clinical ISF changes (if available)
```

### Encoding Strategy

- **No neural encoding** — raw ISF_effective values
- **Aggregation**: 14-day rolling mean (optimal variance reduction)
- **Cycle definition**: 6h non-overlapping windows, glucose and insulin integrated
- **Confound control**: Match on treatment context (EXP-308) to separate true ISF
  change from behavioral adaptation

### Architecture

- **Model**: None (statistical tests only)
- **Method**: Rolling biweekly mean → Spearman rank correlation → OLS trend line
- **Do NOT use**: CUSUM/EWMA on daily data (85-100% false alarm rate — EXP-325),
  embedding similarity (encoder collapse — EXP-307), cross-patient pooling (destroys
  signal — EXP-306)

### Proposed Next Experiments

| Priority | Experiment | Expected Impact | Success Criterion |
|----------|-----------|----------------|-------------------|
| **High** | Circadian ISF profiling | Time-of-day sensitivity map | Dawn phenomenon detected |
| **High** | Pre-smoothed CUSUM (7d rolling → CUSUM) | Faster detection | Latency < 10 days, FA < 20% |
| Medium | Bayesian change-point (BOCPD) | Principled uncertainty | Calibrated detection probability |
| Medium | ISF ↔ clinical outcome correlation | Validate actionability | TIR improvement when acted on |
| Low | Causal ISF modeling | True ISF vs AID adaptation | Separable factors identified |

---

## 5. Objective 4: Pattern Retrieval

### Status: 🟠 Early — Metric Limitations

**Current best**: Silhouette = +0.326 (EXP-304, weekly Transformer) — the only
positive silhouette achieved.  
**Key finding**: R@K is completely saturated (1.000 everywhere) due to label density.
Silhouette is the discriminating metric but remains challenging.

### Validation Metrics

| Metric | Current | Target | Rationale |
|--------|---------|--------|-----------|
| **Silhouette score** | +0.326 | >+0.50 | Cluster quality |
| **Adjusted Rand Index** | — | >0.40 | Cluster-label agreement |
| **Recall@K (hard)** | Saturated | Use class-balanced | Retrieval precision |
| **Cross-patient retrieval accuracy** | — | >70% | Generalization |
| **Clinical relevance score** | — | User-rated | Practical utility |
| **LOO Silhouette** | -0.360 | >0.00 | Cross-patient transfer |

### Learning Pipeline

```
Data: 8ch × 168-step (7d) windows, 1-hour resolution, stride=24h
Labels: Majority-vote episode labels (9 classes)
Training: GRU pattern encoder, triplet loss, 30 epochs
  - Positive: same label within patient
  - Negative: different label, any patient
  - Margin: adaptive based on label distance
Evaluation: Silhouette, ARI, class-balanced R@K
```

### Encoding Strategy

- **Features**: 8 base channels downsampled to 1-hour resolution
- **Window**: 168 steps (7 days) — the only scale with positive silhouette
- **Drop**: Bolus (point-event noise at 7d scale), time features (patterns should
  be time-invariant — EXP-298)
- **Keep**: Glucose, IOB, COB, basal, carbs (5 channels effective)

### Architecture

- **Model**: GRU-based PatternEncoder → 32-dimensional embedding
- **Loss**: Triplet margin loss with online hard mining
- **Library**: Nearest-neighbor retrieval from embedded pattern library
- **Do NOT use**: Cross-scale concatenation (devastating ΔSil=-0.525 — EXP-304)

### Proposed Next Experiments

| Priority | Experiment | Expected Impact | Success Criterion |
|----------|-----------|----------------|-------------------|
| **High** | Contrastive learning (SimCLR/BYOL) | Better embeddings | Sil > +0.50 |
| **High** | Hierarchical labels (glucose × insulin × meal) | Richer supervision | ARI > 0.40 |
| **High** | Class-balanced R@K evaluation | Meaningful retrieval metric | Differentiated scores |
| Medium | Cross-patient retrieval benchmark | Generalization | Cross-patient R@5 > 70% |
| Medium | Temporal augmentation (time-warp, jitter) | More diverse training | Sil improvement |
| Low | Graph neural networks for temporal patterns | Novel architecture | Sil > +0.50 |

---

## 6. Objective 5: Override Recommendation

### Status: 🟡 Strong — Best Recent Progress

**Current best**: F1=0.852 at 15min lead (EXP-327 attention), F1=0.726 at 60min
(EXP-311 CNN). Multi-task with hypo achieves F1=0.809 override + F1=0.672 hypo.  
**Key finding**: Shorter lead times dramatically improve prediction (+13% from 60→15min).
Attention architecture edges out CNN for override (+2%).

### Validation Metrics

| Metric | Current (15min) | Current (60min) | Target | Rationale |
|--------|----------------|-----------------|--------|-----------|
| **F1 macro** | 0.852 | 0.726 | >0.85 | Overall performance |
| **F1 high** | 0.931 | 0.858 | >0.90 | Hyperglycemia prediction |
| **F1 low** | 0.607 | 0.515 | >0.65 | Hypoglycemia prediction |
| **Multi-task hypo F1** | 0.672 | — | >0.70 | Dual-head performance |
| **ECE (calibrated)** | 0.010 | — | <0.02 | Decision reliability |
| **LOO degradation** | -2.9% | — | <5% | Cross-patient viability |

### Learning Pipeline

```
Single-Task Pipeline:
  Data: 8ch × 24-step (2h), labels = glucose exits [70,180] in next N min
  Training: Self-attention encoder (d=64, 4 heads, 2 layers), 30 epochs
  Lead times: 15min (primary), 30min, 60min (separate models)
  Evaluation: Per-class F1, macro F1, confusion matrix

Multi-Task Pipeline (recommended for deployment):
  Data: Same as above
  Labels: Override (3-class: none/high/low) + Hypo (binary: <70 in next 30min)
  Training: Shared 1D-CNN backbone + dual classification heads
  Loss: 0.5 × override_wce + 0.5 × hypo_wce
  Post-processing: Platt calibration on hypo head
  Evaluation: Override F1, hypo F1, hypo AUC, ECE
```

### Encoding Strategy

- **Features**: 8 base channels only (ISF-as-feature hurts: -3.5% override — EXP-316)
- **Window**: 24 steps (2h context)
- **Labels**: Forward-looking threshold crossing (configurable lead time)
- **Class definition**: no_override (glucose stays in [70,180]), high (>180), low (<70)

### Architecture

- **15min lead**: Self-attention encoder (d_model=64, 4 heads, 2 layers, 71K params)
- **60min lead**: 1D-CNN (8→32→64, 3 kernel sizes, 24K params)
- **Multi-task**: Shared CNN backbone + override_head + hypo_head
- **Post-processing**: Platt calibration (essential for hypo head)
- **Do NOT use**: Feature engineering (EXP-316, 320), embedding features (EXP-305),
  focal loss stacking with multi-task (EXP-323)

### Proposed Next Experiments

| Priority | Experiment | Expected Impact | Success Criterion |
|----------|-----------|----------------|-------------------|
| **High** | Multi-seed attention (EXP-327) | Confidence intervals | σ(F1) < 0.02 |
| **High** | Time-split evaluation | Temporal generalization | Δ F1 < 5% |
| Medium | Attention + multi-task | Combine best architecture + training | Override F1 > 0.86, hypo > 0.68 |
| Medium | Per-patient calibration | Personalized thresholds | Per-patient ECE < 0.02 |
| Medium | Override type prediction (beyond high/low) | Finer clinical actions | 5-class F1 > 0.70 |
| Low | Sequence-to-sequence override | Predict override trajectory | Temporal F1 > 0.80 |
| Low | Reinforcement learning policy | Optimal override timing | Simulated TIR improvement |

---

## 7. Cross-Objective Architecture

### The Three-Pipeline System

Based on all 327 experiments, the optimal deployment architecture uses three parallel
pipelines operating at different timescales:

```
┌─────────────────────────────────────────────────────────────────┐
│                  CGM/AID Intelligence System                     │
├─────────────────┬───────────────────┬──────────────────────────┤
│   FAST PIPELINE │  WEEKLY PIPELINE  │   ROLLING PIPELINE       │
│   (Real-time)   │  (Decision support)│  (Therapy adjustment)   │
├─────────────────┼───────────────────┼──────────────────────────┤
│ Scale: 2h/5min  │ Scale: 7d/1hr     │ Scale: 14d rolling       │
│ Arch: CNN/Attn  │ Arch: GRU encoder │ Arch: Statistics         │
│ Features: 8ch   │ Features: 5ch     │ Features: glucose+insulin│
├─────────────────┼───────────────────┼──────────────────────────┤
│ ✅ UAM (F1=0.94)│ ✅ Retrieval      │ ✅ ISF drift (9/11)      │
│ ✅ Override      │   (Sil=+0.33)    │                          │
│   (F1=0.85)    │                   │                          │
│ ✅ Hypo (F1=0.68│                   │                          │
│   AUC=0.96)    │                   │                          │
│ ✅ Forecast     │                   │                          │
│   (MAE=11.25)  │                   │                          │
└─────────────────┴───────────────────┴──────────────────────────┘
```

### Shared Infrastructure

Despite different pipelines, all objectives share:

1. **Data ingestion**: Nightscout JSON → 5-min grid with 8 base channels
2. **Per-patient data split**: 80% train / 20% validation (temporal)
3. **Channel normalization**: glucose/400, IOB/10, COB/100, etc.
4. **Evaluation protocol**: Per-patient metrics + macro averages
5. **Deployment format**: ONNX export with Platt calibration parameters

### What Does NOT Transfer Between Objectives

| Aspect | Fast Pipeline | Weekly Pipeline | Rolling Pipeline |
|--------|--------------|----------------|-----------------|
| Window size | 24 steps (2h) | 168 steps (7d) | 6h cycles × 14d |
| Resolution | 5 min | 1 hour | Per-cycle |
| Loss function | Cross-entropy | Triplet margin | N/A (statistics) |
| Architecture | CNN/Attention | GRU | None |
| Key channels | All 8 | 5 (drop bolus, time) | 2 (glucose, insulin) |
| Output | Classification | Embedding | Trend + p-value |
| Post-processing | Platt calibration | k-NN retrieval | Spearman test |

---

## 8. Prioritized Research Roadmap

### Phase 1: Validation & Robustness (Immediate)

| ID | Experiment | Objectives | Expected Outcome |
|----|-----------|-----------|-----------------|
| P1-1 | Multi-seed replication (EXP-313, 327) | Event, Override | Confidence intervals on key results |
| P1-2 | Time-split hold-out evaluation | All | True temporal generalization estimate |
| P1-3 | Standardized evaluation protocol | All | Reproducible benchmarks |

### Phase 2: Improving the Weakest Links (Near-term)

| ID | Experiment | Objectives | Expected Outcome |
|----|-----------|-----------|-----------------|
| P2-1 | Hypo data augmentation | Event | Hypo F1 > 0.70 |
| P2-2 | Contrastive learning for retrieval | Pattern | Sil > +0.50 |
| P2-3 | Pre-smoothed CUSUM for drift | ISF Drift | Detection < 10 days |
| P2-4 | Attention + multi-task override | Override | Override F1 > 0.86 |

### Phase 3: Clinical Integration (Medium-term)

| ID | Experiment | Objectives | Expected Outcome |
|----|-----------|-----------|-----------------|
| P3-1 | Per-patient calibration | Event, Override | Personalized thresholds |
| P3-2 | Circadian ISF profiling | ISF Drift | Dawn phenomenon detection |
| P3-3 | Override type prediction | Override | Beyond binary high/low |
| P3-4 | Cross-patient retrieval benchmark | Pattern | Population-level patterns |

### Phase 4: Deployment Readiness (Longer-term)

| ID | Experiment | Objectives | Expected Outcome |
|----|-----------|-----------|-----------------|
| P4-1 | ONNX model export pipeline | All | Deployable inference |
| P4-2 | Online adaptation framework | Event, Override | Real-time model updates |
| P4-3 | Prospective validation design | All | Clinical trial protocol |
| P4-4 | Patient cohort expansion (N>50) | All | Population generalizability |

---

## 9. Key Principles (Verified by 327 Experiments)

1. **Each objective needs its own pipeline** — universal models fail
2. **1D-CNN dominates short-timescale classification** — embeddings hurt
3. **Self-attention edges out CNN for override** — but not for hypo
4. **Cross-scale concatenation is counterproductive** — task-specific scales only
5. **Statistical methods beat ML for drift** — neural networks add noise
6. **Feature engineering hurts CNN** — prefer raw channels
7. **Threshold tuning > loss function choice** — +19.7% vs +2.8%
8. **Multi-task learning helps the weakest task** — +6% hypo at -1.7% override cost
9. **Platt calibration is essential** — ECE 0.21→0.01, trivial compute
10. **Optimization improvements are NOT additive** — focal+MT < MT alone
11. **Biweekly is the minimum for ISF drift** — daily is too noisy
12. **Models generalize with only 3-4% LOO degradation** — deployment-viable
13. **The DIA valley (4-8h) is a universal obstacle** — avoid mid-range windows

---

## 10. Conclusion

The research program has progressed from a single forecasting objective to a
comprehensive five-objective intelligence system. Each objective is now well-characterized
with verified metrics, proven architectures, and clear improvement pathways.

The most impactful near-term investments are:
1. **Multi-seed validation** of key results (establish confidence)
2. **Hypo data augmentation** (the biggest remaining gap: F1=0.68 → target 0.70+)
3. **Contrastive retrieval learning** (unlock the pattern library objective)
4. **Pre-smoothed CUSUM** (faster ISF drift detection)

The system is deployment-viable today for UAM detection (F1=0.94), override prediction
(F1=0.85 at 15min), and glucose forecasting (MAE=11.25). Hypoglycemia prediction
is viable with calibration (AUC=0.96, ECE=0.01) but needs F1 improvement for
stand-alone deployment. ISF drift tracking works as a monitoring tool but needs
clinical validation.
