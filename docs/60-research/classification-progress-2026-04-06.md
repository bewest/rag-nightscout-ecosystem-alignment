# CGM Pattern Classification Research Progress Report

**Date**: 2026-04-06
**Scope**: EXP-287 through EXP-406 — classification thread across all scales and architectures

---

## Overview

The classification research thread spans experiments EXP-287 through EXP-406, executed across multiple dedicated runners:

| Runner Script | Experiments | Purpose |
|---|---|---|
| `run_pattern_experiments.py` | EXP-287–327 | Original pattern experiments, multi-seed validated |
| `exp_arch_12h.py` | EXP-361 | Architecture search at 12h |
| `exp_transformer_features.py` | EXP-362 | Transformer + features at 6h/12h |
| `exp_multitask_transformer.py` | EXP-373/374 | Multi-task learning |
| `exp_fda_classification_v2.py` | EXP-405/406 | FDA head features (ready, not yet run) |
| `exp_normalization_conditioning.py` | EXP-369–376 | Normalization primitives |

**Infrastructure**: 5 experiment runners, ~3,000+ lines of code. Multi-seed validation framework using seeds `[42, 123, 456, 789, 1337]` with bootstrap confidence intervals. Per-patient chronological split (first 80% train, last 20% val); only training set is shuffled after splitting. 11 patients, ~6 months data each. Shared utility `feature_helpers.py` (multi-rate EMA, glucodensity, depth).

---

## Best Results Per Task (Validated)

### UAM Detection (Unannounced Meals)

| Metric | Value |
|---|---|
| **Best F1** | 0.939 |
| **95% CI** | [0.928, 0.949] |
| **ECE** | 0.014 |
| **Architecture** | 1D-CNN with B-spline smoothing |
| **Experiment** | EXP-337 |
| **Scale** | 2h (24 steps at 5 min) |
| **Status** | **Production-viable** ✓ |

> Also: EXP-349 `pk_no_time_6ch` F1=0.9707 (single seed, needs multi-seed validation).

### Override Prediction (Will Patient Go High/Low?)

| Scale | Best F1 | Architecture | Features | Experiment | Status |
|---|---|---|---|---|---|
| **2h** | 0.882 | Platt CNN | — | EXP-343 | **Production-viable** ✓ |
| **6h** | 0.723 | Transformer | kitchen_sink_10ch | EXP-362 | Research |
| **12h** | 0.610 | Transformer | — | EXP-361 | Research |

2h details: CI=[0.871, 0.893], ECE=0.046.

### Hypoglycemia Prediction

| Metric | Value |
|---|---|
| **Best F1** | 0.676 |
| **95% CI** | [0.662, 0.690] |
| **ECE** | 0.014 |
| **AUC** | 0.958 |
| **Architecture** | Platt multi-task CNN |
| **Experiment** | EXP-345 |
| **Scale** | 2h |
| **Prevalence** | ~6.2% (highly imbalanced) |
| **Status** | **Production-viable with calibration** ✓ |

### Prolonged High

| Scale | Best F1 | AUC | Architecture | Experiment |
|---|---|---|---|---|
| **6h** | 0.656 | 0.869 | Transformer | EXP-362 |
| **12h** | 0.528 | 0.829 | Transformer | EXP-361 |

### ISF Drift Detection

- **9 of 11 patients** show significant drift at biweekly rolling window (EXP-312).
- Optimal detection: biweekly aggregation (first scale achieving 9/11 significance).
- Two drift groups identified:
  - **Sensitivity ↑**: patients a, b, d, f, i
  - **Resistance ↑**: patients c, e, h, j

### Pattern Retrieval / Clustering

| Metric | Value |
|---|---|
| **Best Silhouette** | +0.326 |
| **Method** | Transformer embeddings |
| **Scale** | 7 days |
| **Experiment** | EXP-296 |

U-shaped window curve observed: 7d best > 12h > DIA valley (4–8h).

---

## Scale-Dependent Performance Matrix

| Task | 2h | 6h | 12h |
|---|---|---|---|
| UAM Detection | **F1=0.939** ✓ | — | — |
| Override Prediction | **F1=0.882** ✓ | F1=0.723 | F1=0.610 |
| Hypoglycemia | **F1=0.676** ✓ | — | — |
| Prolonged High | — | **F1=0.656** | F1=0.528 |
| ISF Drift | — | — | Biweekly window |
| Clustering | — | — | **Sil=+0.326** (7d) |

**Sample counts by scale**: 35,272 at 2h vs 5,867 at 12h (6× reduction).

---

## Architecture Comparison by Scale

### At 2h (24 Steps)

| Architecture | UAM F1 | Override F1 | Hypo F1 | Notes |
|---|---|---|---|---|
| **1D-CNN** | **0.939** | — | — | Universally best at 2h |
| **Platt CNN** | — | **0.882** | **0.676** | Calibrated CNN |
| Transformer | Lower | Lower | Lower | Overhead not justified |
| Embeddings | Lower | Lower | Lower | Too indirect |

### At 6h

| Architecture | Override F1 | Prolonged High F1 | Notes |
|---|---|---|---|
| **Transformer + kitchen_sink_10ch** | **0.723** | **0.656** | Modest gain (+0.4–1.6%) |
| 1D-CNN | ~0.71 | ~0.64 | Still competitive |
| Multi-task Transformer | +0.04% | — | Marginal benefit (EXP-373) |

### At 12h

| Architecture | Override F1 | Prolonged High F1 | Notes |
|---|---|---|---|
| Transformer | **0.610** | **0.528** | All architectures plateau |
| 1D-CNN | ~0.61 | ~0.53 | Same level — feature bottleneck |

**Key insight**: At 12h, architecture is NOT the bottleneck. All architectures converge to the same performance ceiling. Feature engineering is the limiting factor.

---

## Key Discoveries

1. **1D-CNN is universally best for classification at 2h** — beats embeddings, transformers, and combined models across all tasks at this scale.

2. **Transformer provides modest gains at 6h+ (+0.4–1.6%)** but architecture is NOT the bottleneck at longer horizons.

3. **Feature engineering is the bottleneck at 12h** — all architectures plateau at the same level, indicating the input representation limits performance, not model capacity.

4. **Platt calibration is essential** — ECE drops from 0.21 → 0.01 (88% reduction), enabling practical threshold selection (threshold shifts from 0.87 → 0.28).

5. **B-spline smoothing helps UAM only** (+0.021 F1) — does not transfer to other classification tasks.

6. **Time-translation invariance confirmed at ≤12h** — removing time channels IMPROVES results (EXP-349), indicating circadian features are noise at short scales.

7. **PK channels hurt at 2h** (−3.4% UAM F1) — 1h history is too short for 5–6h DIA curves to provide useful information.

8. **Multi-task learning gives marginal benefit** (+0.04% at 6h, EXP-373) — not worth the added complexity at current data scales.

9. **Data scarcity at 12h** — only 5,867 samples vs 35,272 at 2h (6× less), likely contributing to the performance ceiling.

10. **Head injection required for scalar features** — feeding scalar features as input channels gives zero gradient; injecting at the classifier head is necessary (EXP-338).

---

## Scale-Dependent Feature Importance

| Scale | Feature Behavior |
|---|---|
| **2h** | All features OK, high redundancy, small ablation deltas. Features are not the limiting factor. |
| **6h** | `kitchen_sink_10ch` (raw + FDA + PK) wins with transformer architecture. Feature selection starts to matter. |
| **12h** | Features are the bottleneck. `pk_no_time_6ch` HURTS all architectures. CNN learns better features than hand-crafted ones. |
| **24h+** | Time features shift from noise to essential (circadian patterns). |

---

## FDA Feature Analysis (EXP-328–335, 351)

### Functional Data Analysis Results

| FDA Technique | Finding |
|---|---|
| **FPCA K=2** | Captures 91.7% glucose variance at 2h (good compression) |
| **Glucodensity** | +0.54 Silhouette vs TIR bins — superior phenotyping |
| **B-spline derivatives** | +15% SNR, −25% noise vs finite differences |
| **Functional depth** | Q1 = 33.7% hypo prevalence, 112× enrichment over population rate |

### Scale-Dependent FDA Impact

| Scale | FDA Effect on Classification |
|---|---|
| **2h** | Helps — good compression, useful features |
| **6h** | Hurts (−1.9% F1) |
| **12h** | Hurts more (−6.5% F1) |

**Root cause at 12h+**: The CNN learns better features from raw data than FDA provides as hand-crafted inputs.

> **Update (EXP-375–377)**: With Transformer architecture, FDA B-spline derivatives
> HELP at all scales (+1.4–2.2%). The hurt observed here was CNN-specific — Transformers
> leverage FDA features effectively via learned attention. See
> [cross-scale-feature-synthesis](cross-scale-feature-synthesis-2026-04-06.md)
> and [classification-research-synthesis](classification-research-synthesis-2026-04-07.md).

---

## Calibration (EXP-324, 343–345)

| Method | ECE Reduction | Notes |
|---|---|---|
| **Platt scaling** | 0.21 → 0.01 (88%) | Best overall — stable, effective |
| Isotonic regression | Similar ECE | Less stable across seeds |
| Temperature scaling | Moderate improvement | Simpler but less effective |

All classification results now report ECE alongside F1/AUC as standard practice.

---

## Next Experiments (Ready to Run)

| Priority | Experiment | Description | Script |
|---|---|---|---|
| 1 | **EXP-405** | Glucodensity + depth head injection at 2h and 12h | `exp_fda_classification_v2.py` |
| 2 | **EXP-406** | Multi-rate EMA channels at 12h | `exp_fda_classification_v2.py` |
| 3 | **EXP-369** | ISF-normalized glucose | `exp_normalization_conditioning.py` |
| 4 | **EXP-371** | Functional depth as hypo feature | `exp_normalization_conditioning.py` |
| 5 | **EXP-372** | Glucodensity at classifier head | `exp_normalization_conditioning.py` |

---

## Recommendations

1. **Run EXP-405/406** — FDA features at classifier head (head injection) is the most promising untested approach for breaking the 12h ceiling, given that input-channel FDA features hurt but head injection resolved the scalar gradient problem (EXP-338).

2. **Apply Platt calibration to ALL new experiments** — 88% ECE reduction is too significant to skip. Every new result should report calibrated ECE alongside F1/AUC.

3. **Focus feature engineering on 12h scale** — this is the biggest performance gap (F1=0.610 override vs 0.882 at 2h) and the scale where architecture has demonstrably plateaued.

4. **Consider transformer + head injection combo** — transformer provides modest architecture gains at 6h+, head injection solves the scalar feature gradient problem. The combination is untested.

5. **Address data scarcity at 12h** — with only 5,867 samples (6× less than 2h), consider data augmentation or transfer learning from the 2h scale to improve 12h performance.

6. **Multi-seed validate any new single-seed results** — EXP-349 (F1=0.9707 UAM) is a reminder that single-seed results can be misleading. Use the 5-seed framework `[42, 123, 456, 789, 1337]` with bootstrap CIs before claiming improvement.
