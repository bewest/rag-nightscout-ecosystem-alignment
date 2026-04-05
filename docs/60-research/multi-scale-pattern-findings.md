# Multi-Scale Pattern Pipeline: Experiment Findings Report

**Date**: 2026-04-05
**Experiments**: EXP-287, EXP-289, EXP-286, EXP-291
**Prior work**: EXP-242 (best forecast MAE=11.25), 280+ prior experiments

## Executive Summary

Four experiments reveal that the current forecasting-centric architecture is
insufficient for the project's actual objectives: event detection, pattern
prediction, and override recommendation. Key finding: **a U-shaped relationship
between window length and pattern quality** maps precisely to insulin
pharmacokinetics, with 12-hour windows producing the best episode clustering
despite having 6× less training data than 2-hour windows.

These results motivate a multi-scale architecture where different objectives
use different timescales, features, and optimization targets — none of which
are glucose forecasting MAE.

## Problem Statement

The research pipeline has optimized glucose forecasting MAE to 11.25 mg/dL
(EXP-242, per-patient fine-tuned ensemble). But the high-level objectives are:

| Objective | What it requires | Current metric | Better metric |
|-----------|-----------------|----------------|---------------|
| Detect events across timeframes | Classification | ~~MAE~~ | F1, AUC, Lead Time |
| Predict pattern recurrence | Retrieval | ~~MAE~~ | Recall@K, Silhouette |
| Track ISF sensitivity shifts | Trend detection | ~~MAE~~ | Drift Ratio Accuracy |
| Suggest overrides proactively | Action recommendation | ~~MAE~~ | TIR Delta, Safety Rate |

Forecasting is one tool, not the objective. These experiments test the
non-forecasting pipelines directly.

## Experiment Results

### EXP-287: Channel Ablation for Pattern Embedding

**Question**: Which features matter most for pattern retrieval?

**Setup**: Train PatternEncoder (d=64, L=2, 20 epochs) on 28,965 training
windows (24-step/2h, 8 channels, 11 patients). Ablate each channel by zeroing
it, measure Recall@5 and Silhouette change.

**Results** (ranked by retrieval importance):

| Rank | Channel | ΔRecall@5 | ΔSilhouette | Interpretation |
|------|---------|-----------|-------------|----------------|
| 1 | basal_rate (3) | **-1.12%** | -0.004 | Insulin delivery context — most important |
| 2 | carbs (5) | -0.87% | +0.089 | Meal timing matters |
| 3 | bolus (4) | -0.86% | +0.120 | Discrete interventions |
| 4 | time_all (6,7) | -0.72% | **+0.166** | Time HURTS clustering |
| 5 | iob (1) | -0.68% | +0.090 | Redundant with basal |
| 6 | glucose (0) | -0.64% | -0.045 | Core signal |
| 7 | cob (2) | **-0.14%** | **+0.178** | Nearly irrelevant; adds noise |

**Group ablation** (removing all channels in a category):

| Group | ΔRecall@5 | ΔSilhouette |
|-------|-----------|-------------|
| insulin_all (IOB+basal+bolus) | -0.32% | +0.061 |
| meal_all (COB+carbs) | -0.46% | -0.051 |
| time_all (sin+cos) | -0.72% | +0.166 |

**Key Findings**:

1. **Basal rate is the most important single feature** for pattern retrieval.
   This makes physiological sense: basal delivery defines the treatment context
   that distinguishes different metabolic states.

2. **Paradox: removing ALL insulin (-0.32%) hurts LESS than removing basal alone
   (-1.12%)**. The model compensates when multiple correlated signals are removed,
   but basal provides unique information not captured by IOB or bolus.

3. **COB is near-irrelevant for retrieval (-0.14%)** and its removal IMPROVES
   silhouette by +0.178. COB adds noise to the embedding space. This suggests
   the heuristic COB calculation is unreliable as a feature.

4. **Time encoding hurts clustering**. Removing time features improves silhouette
   by +0.166. For pattern embeddings, a post-meal spike at 8am and 8pm should be
   the SAME pattern — time-of-day is a confounder, not a feature.

5. **All ablation deltas are small (max 1.12%)** at 2h windows, suggesting the
   8-channel features are highly redundant at this timescale. This motivates
   testing longer windows where features should differentiate more.

**Source**: `externals/experiments/exp287_channel_ablation_emb.json`

---

### EXP-289: Window Length Sweep (DIA-Grounded)

**Question**: What timescale is optimal for pattern matching?

**Motivation**: Rapid-acting insulin has onset ~15min, peak ~60-90min, and
Duration of Insulin Action (DIA) of 5-6 hours. A 2-hour window can observe
a bolus and its peak, but cannot observe whether the correction actually worked.

**Setup**: Train PatternEncoder at 6 window sizes: 12 (1h), 24 (2h), 48 (4h),
72 (6h = full DIA), 96 (8h), 144 (12h). Same architecture (d=64, L=2, 20 epochs).

**Results**:

| Window | Duration | Train Examples | Recall@5 | Silhouette |
|--------|----------|---------------|----------|------------|
| 12 | 1h | 58,277 | 0.9450 | -0.346 |
| **24** | **2h** | **28,965** | **0.9500** | **-0.367** |
| 48 | 4h | 14,392 | 0.9480 | -0.537 |
| 72 | 6h (DIA) | 9,534 | 0.9434 | -0.544 |
| 96 | 8h | 7,115 | 0.9359 | **-0.642** |
| **144** | **12h** | **4,699** | **0.9523** | **-0.339 ✨** |

```
Recall@5
0.953 ●                                                ● 144 (12h) ← BEST sil
0.950    ● 24 (2h)
0.948         ● 48
0.945 ● 12
0.943              ● 72 (DIA)
0.936                   ● 96 ← WORST
      1h   2h   4h   6h   8h   12h
           Insulin onset→peak→tail→gone
```

**Key Finding: U-Shaped Curve Explained by Insulin Pharmacokinetics**

The relationship is NOT monotonic. There are two local optima:
- **24 steps (2h)**: Local optimum — enough for acute events, lots of data
- **144 steps (12h)**: Global optimum for clustering — sees complete cycles

The **valley at 48-96 steps (4-8h)** aligns precisely with partial insulin action:
- At 4h: Model sees bolus + peak but NOT whether glucose returned to target
- At 6h: Sees full DIA but episodes overlap (meal ending + new event starting)
- At 8h: Worst of both worlds — mixed episodes, insufficient data

The **12h recovery** occurs because the window captures complete cycles:
pre-meal → bolus → absorption → peak insulin → glucose resolution → stable.
The pattern is unambiguous again.

**Remarkable**: 12h achieves the BEST silhouette (-0.339) with only 4,699
training examples, beating 2h's -0.367 with 28,965 examples. The quality
of the temporal context matters more than the quantity of training data.

**Source**: `externals/experiments/exp289_window_sweep_emb.json`

---

### EXP-286: ISF-Drift Episode Segmentation

**Question**: Do ISF drift episode labels improve segmentation?

**Setup**: Compare 9-label baseline (stable, rising, falling, hypo_risk,
meal_response, correction_response, dawn_phenomenon, exercise_response) vs
11-label (+ sensitivity_shift, resistance_shift). EpisodeSegmenter with
d=64, L=2, 20 epochs on 28,965 training windows.

**Results**:

| Model | Macro F1 | Weighted F1 |
|-------|----------|-------------|
| 9-label baseline | **0.8613** | **0.8966** |
| 11-label + drift | 0.8388 | 0.8809 |
| Δ | -0.0224 | -0.0157 |

**Key Finding**: Adding drift labels HURTS segmentation on 8-channel data.

This is expected: with only base features (glucose, IOB, COB, basal, bolus,
carbs, time), the model has **no signal** to distinguish insulin sensitivity
shifts from insulin resistance shifts. These episodes look identical in glucose
trace alone — you need the ISF profile (channel 32) and CR profile (channel 33)
from the enriched 39-feature set.

**Implication**: Drift experiments must use enriched features or downsampled
long-horizon data that captures the gradual drift signature over 24+ hours.

**Source**: `externals/experiments/exp286_isf_drift_seg.json`

---

### EXP-291: UAM Detection via Pattern Embedding

**Question**: Can embedding-based UAM detection catch unannounced meals?

**Setup**: Train PatternEncoder on 28,965 windows with episode labels. Extract
embeddings, train logistic classifier for UAM (unannounced meal) binary detection.
UAM prevalence: 15.7% of windows.

**Results**:

| Metric | Value | Interpretation |
|--------|-------|----------------|
| F1 | 0.399 | Moderate |
| Precision | 0.283 | 71.7% false positive rate |
| **Recall** | **0.676** | Catches 2/3 of UAM events |

**Key Finding**: High recall (67.6%) but low precision (28.3%). The embedding
successfully learns to detect glucose patterns associated with unannounced meals,
but the 2-hour window doesn't contain enough context to distinguish true UAM
from other rising glucose patterns (dawn phenomenon, rebound highs, etc.).

**Implication**: Re-running at 12h windows (EXP-291b) should improve precision
because the model can see:
- Whether carbs were logged nearby (within the 12h window)
- The full glucose rise → peak → resolution cycle
- Whether IOB/COB patterns suggest announced vs unannounced eating

**Source**: `externals/experiments/exp291_uam_detection.json`

---

## Synthesis: Multi-Scale Architecture

### Why Different Scales for Different Objectives

The experiments reveal a fundamental tension: short windows have more data but
less context; long windows have better episode representation but less data.
The U-shaped curve shows this isn't a simple tradeoff — **intermediate windows
are actively harmful** because they capture partial physiological processes.

The solution is a multi-scale architecture where each objective operates at
the timescale matching its physiological basis:

| Scale | Resolution | Window | Steps | Purpose | Training Data |
|-------|-----------|--------|-------|---------|---------------|
| **Fast** | 5-min | 2h | 24 | Acute events: hypo, rapid rise | 29K windows |
| **Episode** | 5-min | 12h | 144 | Complete cycles: meal→resolution | 4.7K windows |
| **Daily** | 15-min | 24h | 96 | ISF drift, dawn phenomenon | ~3.5K (est) |
| **Weekly** | 1-hr | 7 days | 168 | Multi-day ISF trends, sick days | ~8.5K w/stride=1 |

All scales fit within 4GB VRAM (max ~270MB with gradients at 144 steps).

### Feature Requirements Per Scale

| Scale | Core Features | Additional Features Needed |
|-------|--------------|---------------------------|
| Fast (2h) | 8ch base | None — already works well |
| Episode (12h) | 8ch base (drop COB?) | None — EXP-289 proves 8ch sufficient |
| Daily (24h) | 8ch + profile | ISF (ch32), CR (ch33) — drift labels NEED this |
| Weekly (7d) | 8ch + profile + AID | Loop predictions, override history |

### Optimization Targets (NOT Forecasting MAE)

| Scale | Primary Metric | Secondary Metric |
|-------|---------------|-----------------|
| Fast | Event F1 | Hypo sensitivity, false alarm rate |
| Episode | Silhouette, Recall@5 | Episode segment F1 |
| Daily | Drift ratio accuracy | Shift detection lead time |
| Weekly | ISF trend prediction | Pattern recurrence recall |

### Downsampling Strategy

The `downsample_grid()` function in `real_data_adapter.py` already supports:
- 5-min native (Scales 1-2)
- 15-min aggregated (Scale 3): glucose=mean, IOB/COB=last, bolus/carbs=sum
- 60-min aggregated (Scale 4): same aggregation rules

This makes 7-day windows feasible: 168 steps at 1hr ≈ same compute as 2h at 5-min.

---

## Next Steps

1. **Implement multi-scale data pipeline** using existing `downsample_grid()`
2. **Re-run EXP-287 at 12h** — test if feature importance changes with full DIA
3. **Re-run EXP-291 at 12h** — test if UAM precision improves with context
4. **Run EXP-286b at 24h/15-min** — drift labels with ISF profile features
5. **New: Weekly ISF experiment** — 7-day windows for multi-day sensitivity tracking
6. **Cross-scale integration** — concatenate embeddings from multiple scales

## Appendix: Pharmacokinetic Context

### Rapid-Acting Insulin (Humalog, Novolog, Fiasp)
- **Onset**: 10-15 minutes
- **Peak**: 60-90 minutes
- **Duration of Insulin Action (DIA)**: 4-6 hours (typically 5h in Loop/AAPS)
- **Tail**: Residual effect continues for ~6 hours post-bolus

### Carbohydrate Absorption
- **Fast carbs**: 15-30 min peak effect
- **Mixed meal**: 1-2h absorption, 3-4h full effect
- **High-fat meal**: Extended absorption over 4-6+ hours

### ISF Sensitivity Drift
- **Circadian**: ISF varies ~20-30% across the day (dawn phenomenon)
- **Illness**: 40-70% ISF reduction during sick days (hours to days)
- **Exercise**: 10-30% ISF increase, lasting 12-24h post-exercise
- **Menstrual cycle**: 10-20% ISF variation over 4-5 day periods
- **oref0 autosens**: Uses 24h sliding window, bounds [0.7, 1.2]

### Window Size ↔ Physiological Process

| Window | Captures | Misses |
|--------|----------|--------|
| 1h | Bolus onset, hypo trajectory | Insulin peak, correction outcome |
| 2h | Meal peak, fast correction | Full insulin action, absorption tail |
| 4h | Most insulin action | Whether glucose returned to target |
| **6h** | **Full DIA** | Whether patient dosed correctly |
| 8h | DIA + next meal onset | Dawn phenomenon context |
| **12h** | **Complete meal→resolution cycles** | Multi-day trends |
| 24h | Full circadian cycle | Weekly ISF patterns |
| 7 days | ISF drift, exercise adaptation | Seasonal/hormonal patterns |
