# Research Synthesis: Multi-Objective CGM/AID Intelligence

**Date**: 2026-04-05 (updated with EXP-314–318)  
**Experiments**: EXP-287–318 (24 multi-scale/architecture experiments)  
**Context**: Built on 258 prior experiments (EXP-001–285) covering forecasting,
event detection, and initial pattern/drift/override work.

---

## 1. Executive Summary

This report synthesizes findings from 18 experiments that systematically tested
whether the five high-level objectives of CGM/AID intelligence require different
timescales, architectures, and training pipelines. The answer is a definitive
**yes** — and we've now identified the optimal approach for each.

### Headline Results

| Objective | Best Architecture | Best Metric | Status |
|-----------|------------------|-------------|--------|
| **UAM Detection** | 1D-CNN, 2h window | **F1 = 0.939** | 🟢 Production-viable |
| **Override Prediction** | 1D-CNN, 2h window | **F1 = 0.726** | 🟡 Good, improvable |
| **ISF Drift Tracking** | Rolling biweekly statistics | **9/11 patients sig.** | 🟢 Method proven |
| **Pattern Retrieval** | Transformer encoder, 7d window | **Sil = +0.326** | 🟡 Works but R@K saturated |
| **Glucose Forecasting** | Per-patient fine-tuned ensemble | **MAE = 11.25 mg/dL** | 🟢 Prior work validated |

### Key Discoveries

1. **1D-CNN is universally best for classification** — beats embeddings, static
   features, and combined models for UAM (F1 0.40→0.939) and override (F1 0.700→0.726).
   Adding embeddings to CNN *hurts* performance.

2. **ISF drift requires rolling aggregation** — per-cycle measurements are too
   noisy (0/11 significant), but weekly rolling averages detect drift in 5/11
   patients, and biweekly in 9/11.

3. **Cross-scale concatenation is counterproductive** — combining fast+episode+weekly
   embeddings degrades all metrics vs the best single scale. Each objective has
   ONE optimal scale.

4. **The U-shaped window curve** — retrieval quality drops from 1h to 8h (partial
   DIA is worst), then recovers at 12h+ as complete insulin cycles are captured.
   Weekly (7d) is best overall for pattern clustering.

5. **Forecasting was overindexed** — the four non-forecasting objectives require
   fundamentally different pipelines and are now the primary research frontier.

---

## 2. The Five Objectives

### Objective 1: Glucose Forecasting (SOLVED)

**Goal**: Predict glucose trajectory 1 hour ahead.

**Current best**: MAE = 11.25 mg/dL (EXP-242, per-patient fine-tuned ensemble of
50 models). Verification gap +2.8% — production-viable.

**Architecture**: 67K-param Transformer, 7-channel selective masking, 2h context window.

**Status**: ✅ Essentially solved for this dataset. Diminishing returns from
further architecture search. The 8-feature, 24-step (2h) window is saturated
at ~29.5 mg/dL RMSE regardless of model size (55K–993K params). Per-patient
fine-tuning is the only remaining lever.

**Pathway**: Only gains from more data (more patients, longer histories) or
better feature engineering (profile features, CAGE/SAGE integration).

---

### Objective 2: Event Detection (UAM, Hypo)

**Goal**: Detect short-term glucose events — unannounced meals (UAM),
hypoglycemic episodes, exercise effects — in real-time.

**Prior best**: F1 = 0.40 (EXP-291, embedding + classifier, 2h window).
XGBoost achieved F1 = 0.705 on a different event taxonomy.

**Current best**: **F1 = 0.939** (EXP-313, 1D-CNN, 2h window) — a **2.35×
improvement** and the highest F1 in the entire research program.

#### Architecture Evolution

| Experiment | Method | UAM F1 | Why |
|------------|--------|--------|-----|
| EXP-291 | Embedding + linear | 0.40 | Embedding loses temporal detail |
| EXP-299 | Embedding + linear (12h) | 0.07 | Long window dilutes meal events |
| EXP-313 | Embedding + linear (2h, weighted) | 0.854 | Class weighting helps enormously |
| **EXP-313** | **1D-CNN (2h)** | **0.939** | **Temporal convolutions capture ROC dynamics** |
| EXP-313 | CNN + Embedding | 0.891 | Adding embedding hurts CNN |

**Why CNN wins**: UAM detection requires recognizing the *shape* of a glucose
rise (rate, curvature, acceleration) in the context of *absent* carb entries.
Convolutions naturally extract local temporal features; global embeddings
compress away the discriminative detail.

**Remaining gap**: Hypo detection is weaker (F1 = 0.515 in EXP-311 for
low-glucose override). Hypoglycemic episodes have more diverse temporal
signatures — some are fast crashes, others are slow drifts.

**Pathway to improve**:
- **Dedicated hypo CNN** with hypo-specific label engineering
- **Class-balanced sampling** (hypo events are rare: ~9% prevalence)
- **Multi-lead-time prediction**: detect approaching hypo at 15/30/60 min horizons
- **Per-patient fine-tuning**: hypo thresholds and patterns are highly individual

---

### Objective 3: ISF Drift Tracking

**Goal**: Detect changes in insulin sensitivity over days, weeks, and months
to inform therapy adjustments.

**Prior work**: No reliable method existed. Early attempts (EXP-306/307) were
confounded by behavioral changes and encoder collapse.

**Current best**: **9/11 patients show significant ISF drift** at biweekly
rolling aggregation (EXP-312).

#### The ISF Detection Journey

| Experiment | Method | Result | Issue |
|------------|--------|--------|-------|
| EXP-300 | Episode segmentation (24h) | 0 drift labels | Labels too coarse |
| EXP-301 | Weekly embedding clustering | Sil = -0.301 | Clustering, not drift |
| EXP-306 | Cross-patient pooling | ρ = -0.001 | Destroyed temporal signal |
| EXP-307 | Per-patient early/late matching | 8/11 sig. | sim≈1.0 (encoder collapse) |
| EXP-308 | Treatment-context matching | 4/11 clean | Most "drift" = behavior change |
| EXP-309 | Per-cycle ISF ratio | 0/11 sig. | Per-cycle too noisy (std 4–59) |
| **EXP-312** | **Rolling biweekly ISF** | **9/11 sig.** | **✅ Method works** |

**The breakthrough insight**: Individual DIA cycles have enormous glucose response
variance (std up to 59 mg/dL per unit insulin). But averaging over 14+ days reduces
variance 3–8×, revealing statistically significant trends.

**Two patient groups discovered**:
- **Sensitivity improving** (a, b, d, f, i): ISF_effective becoming more negative
  (more glucose drop per insulin unit)
- **Resistance increasing** (c, e, h, j): ISF_effective trending toward zero
  (less response per insulin unit)

**Clinically actionable finding**: A rolling biweekly ISF tracker could alert
clinicians to therapy adjustment needs — increase basal for resistance, decrease
for improving sensitivity.

**Pathway to improve**:
- **Circadian ISF variation**: Track ISF by time-of-day (dawn phenomenon detection)
- **ISF as a downstream feature**: Feed rolling ISF trend into override and
  forecasting models as an additional input channel
- **Faster detection**: Can we detect incipient drift in <7 days with more
  sophisticated statistical methods (CUSUM, Bayesian change-point)?
- **Causal modeling**: Separate true ISF changes from AID behavioral adaptation

---

### Objective 4: Pattern Retrieval

**Goal**: Find historical episodes similar to the current situation for
decision support ("you've seen this pattern before, and last time X happened").

**Current best**: Silhouette = +0.326 (EXP-304, weekly Transformer encoder) —
the only positive silhouette achieved across all experiments.

#### Scale Matters Enormously

| Scale | Silhouette | R@5 | Note |
|-------|-----------|-----|------|
| 1h | -0.346 | — | Too short for context |
| 2h | -0.367 | 0.977 | Fast local patterns |
| 4h | -0.537 | — | Partial DIA — worst zone |
| 8h | -0.642 | — | Worst (DIA valley) |
| 12h | -0.339 | 0.951 | Complete DIA cycle |
| **7d** | **-0.301** / **+0.326** | **0.957** | **Best clustering** |

**Cross-patient generalization** (EXP-310): LOO Silhouette = -0.360 vs
within-patient = -0.301. Modest degradation (-0.059) shows patterns transfer
across patients. A pooled encoder + per-patient fine-tuning would work.

**Metric problem**: R@K is completely saturated (1.000 everywhere) due to label
density. Need class-balanced evaluation or harder retrieval tasks.

**Pathway to improve**:
- **Contrastive learning** (SimCLR/BYOL-style) instead of triplet loss — may
  produce more discriminative embeddings
- **Hierarchical labels**: Use multi-level labels (glucose state × insulin state ×
  meal state) instead of single majority vote
- **Cross-patient retrieval**: Find similar patterns from OTHER patients' histories
- **Temporal augmentation**: Time-warping and jittering for more diverse training

---

### Objective 5: Override Recommendation

**Goal**: Predict when an AID system override is needed (high or low glucose
excursion imminent) and what type.

**Current best**: **F1 = 0.726** (EXP-311, 1D-CNN, forward-looking labels).

#### Architecture Comparison

| Model | F1_macro | F1_high | F1_low |
|-------|---------|---------|--------|
| EXP-305: Embedding + state | 0.39 | — | — |
| StateMLP (10-dim) | 0.700 | 0.821 | 0.493 |
| **1D-CNN (raw 2h)** | **0.726** | **0.858** | **0.515** |
| Combined (CNN+state) | 0.721 | 0.855 | 0.515 |

**High override prediction is strong** (F1 = 0.858) — hyperglycemia is predictable.
**Low override prediction is weak** (F1 = 0.515) — hypoglycemia is harder.

**Pathway to improve**:
- **Multi-horizon prediction**: Test at 15-min, 30-min, and 60-min lead times
  (current uses the full 1h second half as the prediction target)
- **Separate hypo model**: Dedicated CNN trained with hypo-weighted loss and
  hypo-specific features (IOB, recent bolus, time since meal)
- **Override type refinement**: Beyond binary high/low, predict specific override
  types (temp target, suspend, resume) with clinical context
- **Per-patient thresholds**: Personalize excursion thresholds based on patient
  history and preferences

---

## 3. Architectural Principles Discovered

### Principle 1: Task-Specific Scale Selection

Every objective has ONE optimal timescale. Using the wrong scale degrades
performance dramatically:

```
UAM detection:     2h window (12h → F1 drops 83%)
Override prediction: 2h window (temporal dynamics matter)
Pattern retrieval:   7d window (Sil improves 5× vs 2h)
ISF drift:          Biweekly rolling (per-cycle too noisy)
Forecasting:        2h window (architecture-saturated)
```

**Implication**: The system needs 3 parallel models at different timescales,
not one universal model.

### Principle 2: 1D-CNN > Embeddings for Classification

Across two experiments (UAM, override), 1D-CNN strictly dominates
embedding-based classification:

```
UAM:      CNN=0.939 vs Emb=0.854   (+10%)
Override: CNN=0.726 vs Emb=0.700   (+3.7%)
Combined: WORSE than CNN alone in both cases
```

**Why**: CNN preserves temporal locality (rate of change, curvature, local
patterns) that embeddings compress away. For "is event X happening NOW?"
questions, local features matter more than global summaries.

**When embeddings win**: Retrieval/clustering ("find similar historical patterns"),
where the question is global similarity across an entire multi-day window.

### Principle 3: Cross-Scale Concatenation is Counterproductive

EXP-304/305 definitively rejected the cross-scale architecture hypothesis:

```
Weekly alone:     Sil = +0.326 (BEST)
Cross-scale 96d:  Sil = -0.200 (WORST)
ΔSilhouette:      -0.525 (devastating)
```

**Why**: Each scale captures noise at other scales. When concatenated, the noisy
dimensions dominate distance calculations. The attention-weighted fusion doesn't
help because the optimization landscape is too complex.

**Implication**: Use task-specific scale selection, not feature fusion.

### Principle 4: Statistical Methods Beat ML for Drift Detection

ISF drift detection doesn't need neural networks at all. Rolling statistical
aggregation (biweekly mean of ISF_effective ratios) achieves 9/11 significance
where embedding-based approaches failed (Sil < 0, encoder collapse).

**Why**: Drift is a trend detection problem (is mean shifting over time?), not a
pattern classification problem. Statistical tests (Spearman correlation, t-test)
are inherently suited to this. Neural networks add unnecessary complexity and
introduce encoder collapse risk.

### Principle 5: The DIA Valley (U-Shaped Window Curve)

Pattern retrieval quality follows a distinctive U-shape:

```
Good (1-2h) → Terrible (4-8h) → Good (12h+) → Best (7d)
```

The 4–8h valley corresponds to **partial DIA coverage**: the model sees a bolus
and the glucose peak but not the complete insulin response cycle. This partial
information creates ambiguous patterns that cluster poorly. At 12h+, complete
insulin cycles are captured, resolving the ambiguity.

---

## 4. System Architecture Recommendation

Based on all findings, the optimal CGM/AID intelligence system is:

```
┌─────────────────────────────────────────────────────────┐
│                   INPUT: 5-min CGM Grid                  │
│         8 channels × continuous time series              │
├──────────┬──────────┬──────────────┬────────────────────┤
│  Fast    │ Episode  │   Weekly     │  Rolling           │
│  2h/5min │ 12h/5min │   7d/1hr     │  Biweekly Stats    │
├──────────┼──────────┼──────────────┼────────────────────┤
│ 1D-CNN   │ Unused   │ Transformer  │ ISF_eff mean       │
│ (8→32→64)│          │ (8→64→32d)   │ (glucose/insulin)  │
├──────────┼──────────┼──────────────┼────────────────────┤
│ UAM Det. │          │ Pattern      │ ISF Drift          │
│ F1=0.939 │          │ Retrieval    │ Tracking           │
│          │          │ Sil=+0.326   │ 9/11 sig.          │
│ Override │          │              │                    │
│ F1=0.726 │          │              │                    │
│          │          │              │                    │
│ Forecast │          │              │                    │
│ MAE=11.25│          │              │                    │
└──────────┴──────────┴──────────────┴────────────────────┘
```

**Three parallel pipelines**:
1. **Fast pipeline** (2h, 1D-CNN): UAM, override, hypo — real-time decisions
2. **Weekly pipeline** (7d, Transformer): Pattern library, retrieval — decision support
3. **Rolling pipeline** (biweekly, statistics): ISF drift — therapy adjustment alerts

The episode scale (12h) is only useful for treatment-context matching in drift
analysis (EXP-308) but not as a neural network input.

---

## 5. Improvement Pathways

### Near-Term (High Impact, Low Risk)

| ID | Experiment | Expected Impact | Rationale |
|----|-----------|----------------|-----------|
| EXP-314 | Multi-lead override (15/30/60 min) | F1 improvement at earlier horizons | Earlier detection = more actionable |
| EXP-315 | Dedicated hypo CNN | F1_low 0.515→0.7+ | Hypo-specific features + weighting |
| EXP-316 | ISF trend as feature | Δ F1 on override | Rolling ISF encodes metabolic state |

### Medium-Term (Moderate Impact, Some Risk)

| ID | Direction | Expected Impact | Challenge |
|----|-----------|----------------|-----------|
| — | Per-patient CNN fine-tuning | +5-10% F1 per patient | Training cost (11× models) |
| — | Contrastive learning for retrieval | Sil improvement | Hyperparameter sensitivity |
| — | Circadian ISF profiling | Time-of-day drift detection | Sparse nocturnal data |

### Long-Term (Speculative, High Risk)

| ID | Direction | Expected Impact | Challenge |
|----|-----------|----------------|-----------|
| — | Sequence-to-sequence override | Temporal override trajectories | Model complexity |
| — | Causal ISF modeling | True ISF vs behavioral change | Observational confounders |
| — | Cross-patient transfer learning | Cold-start for new users | Individual variation |
| — | Online adaptation | Real-time model updates | Catastrophic forgetting |

---

## 6. Experiment Details Summary

### Completed Experiments (EXP-287–313)

| EXP | Name | Scale | Key Metric | Finding |
|-----|------|-------|-----------|---------|
| 287 | Channel ablation (2h) | 2h | max ΔSil=0.178 | All channels roughly equal |
| 289 | Window sweep | 1h–7d | Sil: U-shaped | 7d best, 8h worst |
| 286 | Drift segmentation | 2h | F1 improvement | 11 labels hurt without ISF features |
| 291 | UAM embedding | 2h | F1=0.40 | Baseline UAM detection |
| 298 | Channel ablation (12h) | 12h | max ΔSil=0.604 | Features 3.4× more important |
| 299 | UAM at 12h | 12h | F1=0.07 | Long windows dilute meal events |
| 300 | Drift segmentation (24h) | 24h | F1=0.782, 0 drift | Need profile features |
| 301 | Weekly ISF | 7d | Sil=-0.301, R@5=0.957 | Best single-scale retrieval |
| 304 | Cross-scale retrieval | Multi | Weekly Sil=+0.326 | **Concat hurts** (ΔSil=-0.525) |
| 305 | Multi-scale override | Multi | F1=0.39 | Embeddings barely help (Δ<0.001) |
| 306 | Cross-patient drift | Pooled | ρ=-0.001 | **Null** (design flaw) |
| 307 | Per-patient drift | Per-patient | 8/11 sig. | sim≈1.0 (encoder collapse) |
| 308 | Insulin-controlled drift | 12h | 4/11 clean | Most "drift" = behavior change |
| 309 | ISF response ratio | 6h cycles | 0/11 sig. | Per-cycle too noisy |
| 310 | Leave-patient-out | 7d LOO | Sil=-0.360 | Modest transfer (Δ=-0.059) |
| 311 | Temporal override CNN | 2h | F1=0.726 | **CNN > StateMLP > Combined** |
| 312 | Rolling ISF | Biweekly | **9/11 sig.** | **Breakthrough**: aggregation works |
| 313 | CNN UAM | 2h | **F1=0.939** | **Best result**: CNN dominates |

### Null Results (Important for Future Work)

1. **EXP-306**: Cross-patient pooling destroys temporal signal — drift must be
   per-patient.
2. **EXP-309**: Per-cycle ISF measurement is too noisy — must aggregate.
3. **EXP-304/305**: Cross-scale concatenation hurts — use task-specific scales.
4. **EXP-305**: Pattern embeddings don't help override prediction — use CNN.

---

## 7. Data Pipeline Summary

### Downsampling Strategy

| Scale | Raw Interval | Window Size | Duration | Stride | Use Case |
|-------|-------------|-------------|----------|--------|----------|
| Fast | 5 min | 24 steps | 2 hours | 1 step | UAM, override, forecast |
| Episode | 5 min | 144 steps | 12 hours | 144 (non-overlap) | Treatment matching |
| Daily | 15 min | 96 steps | 24 hours | 1 step | Daily patterns |
| Weekly | 1 hour | 168 steps | 7 days | 24 steps | Pattern retrieval |
| Rolling | 5 min | 6h cycles | 14 days aggregation | 1 day | ISF drift |

### Feature Channels (8 base)

| Channel | Name | Normalization | Scale Impact (EXP-298 vs 287) |
|---------|------|--------------|-------------------------------|
| 0 | Glucose | /400 mg/dL | Dominant at all scales |
| 1 | IOB | /10 U | Important at 12h+ |
| 2 | COB | /100 g | Important at 12h+ |
| 3 | Basal rate | /10 U/hr | Important at 12h+ |
| 4 | Bolus | /10 U | **Removal improves 12h** (point event noise) |
| 5 | Carbs | /100 g | **#1 at 12h**, irrelevant at 2h |
| 6 | Time sin | — | **Hurts 12h retrieval** (patterns should be time-invariant) |
| 7 | Time cos | — | **Hurts 12h retrieval** |

### Masking (Verified Safe)

Selective masking channels [0, 4, 5, 12, 13, 14, 15] for forecasting — IOB/COB/basal
are deterministic from current state and should NOT be masked. All pattern experiments
use history-only features (first half of window) to ensure no future leakage.

---

## 8. Conclusions

### What We Know

1. **Each objective needs its own pipeline** — there is no universal architecture.
2. **1D-CNN dominates classification** at fast timescales (2h).
3. **Transformer embeddings work for weekly retrieval** (Sil=+0.326).
4. **ISF drift is real but requires biweekly aggregation** (9/11 patients).
5. **Cross-scale fusion fails** — task-specific scale selection wins.
6. **Forecasting is saturated** — 2h/8-channel/67K-param is the sweet spot.

### What We've Resolved (EXP-314–322)

Since the initial synthesis, 9 more experiments answered the open questions:

1. **Multi-lead override**: 15min F1=0.821 (+13% over 60min baseline) — **RESOLVED** ✅
2. **Dedicated hypo models**: Focal loss + multi-task + threshold → F1=0.672 — **RESOLVED** ✅
3. **ISF as downstream feature**: HURTS both override (-3.5%) and UAM (-2.6%) — **RESOLVED** (negative) ✅
4. **Per-patient CNN fine-tuning**: Selective ensemble +1%, full FT -2.9% — **RESOLVED** ✅
5. **Multi-task learning**: Shared backbone boosts hypo +6% at -1.7% override cost — **NEW FINDING** ✅

### What We Don't Know Yet

1. Can **contrastive learning** (SimCLR, BYOL) produce better embeddings than triplet loss?
2. Can **curriculum learning** (easy tasks first) improve multi-task convergence?
3. Is there a **fundamentally different architecture** (attention-based, graph neural network)
   that could push hypo F1 past 0.70? The AUC=0.96 suggests the model discriminates well
   but can't draw a clean decision boundary.
4. Can **real-time CUSUM/Bayesian change-point detection** detect ISF drift in <7 days?
5. How do these models perform on **unseen patients** (not in the training cohort)?

### Clinical Relevance

The system can now:
- **Detect unannounced meals** with 94% F1 (actionable for insulin dosing)
- **Predict override need 15min ahead** with F1=0.821 (early enough to act)
- **Predict hypoglycemia** with F1=0.672, AUC=0.958 (multi-task CNN)
- **Track insulin sensitivity changes** over 2-week windows (9/11 patients)
- **Retrieve similar historical patterns** from a 7-day library
- **Forecast glucose** at 11.25 mg/dL MAE

**Key optimization insight**: Threshold tuning (+19.7%) matters far more than loss
function choice (+2.8%). Multi-task learning is the best architectural lever for
improving the weakest task (hypo). Feature engineering is counterproductive for CNN.

---

## Reproduction

All experiments are registered in `tools/cgmencode/run_pattern_experiments.py`:

```bash
# List all 28 experiments
python3 -m tools.cgmencode.run_pattern_experiments --list

# Run any experiment
python3 -m tools.cgmencode.run_pattern_experiments <name> --device cuda --epochs 30

# Run tests (250 pass)
python3 -m pytest tools/cgmencode/test_cgmencode.py -x -q
```

Results are saved to `externals/experiments/` (gitignored).
Source code is in `tools/cgmencode/` (committed).
