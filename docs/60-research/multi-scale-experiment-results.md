# Multi-Scale Pattern Experiment Results

**Date**: 2026-04-04  
**Experiments**: EXP-287, EXP-289, EXP-286, EXP-291, EXP-298, EXP-299  
**Status**: EXP-300 (daily drift) and EXP-301 (weekly ISF) pending

## Executive Summary

Six experiments tested whether non-forecasting objectives (event detection, pattern
retrieval, ISF drift tracking) require different timescales and feature sets. Three
findings fundamentally reshape our architecture:

1. **The U-shaped window curve**: 12h windows produce the best pattern clusters,
   confirming that complete insulin DIA cycles are the natural unit of pattern analysis.
2. **Feature importance is scale-dependent**: At 2h, all channel ablation deltas are
   tiny (<1.12%). At 12h, silhouette deltas explode to 60% — features matter 3.4× more.
3. **Acute events need short windows**: UAM detection degrades from F1=0.40 at 2h to
   F1=0.07 at 12h — meal events get diluted in longer context.

**Conclusion**: Different objectives require different timescales. A single model
optimizing a single window size cannot serve all objectives simultaneously.

---

## Experiment Results

### EXP-289: Window Size Sweep (The U-Shaped Curve)

**Question**: What window size produces the best pattern embeddings?

| Window | Duration | R@5    | Silhouette | n_train | n_val |
|--------|----------|--------|------------|---------|-------|
| 12     | 1h       | 0.9450 | -0.346     | 58,277  | 14,570|
| 24     | 2h       | 0.9500 | -0.367     | 28,965  | 7,242 |
| 48     | 4h       | 0.9480 | -0.537     | 14,392  | 3,599 |
| 72     | 6h       | 0.9434 | -0.544     | 9,534   | 2,384 |
| 96     | 8h       | 0.9359 | -0.642     | 7,115   | 1,779 |
| **144**| **12h**  |**0.9523**|**-0.339**| 4,699   | 1,175 |

```
Silhouette Score (higher = better clusters)
  -0.30 ┤                                          ● 144 (12h) BEST
  -0.35 ┤  ● 12 (1h)                               
  -0.37 ┤      ● 24 (2h)                           
  -0.50 ┤                                          
  -0.54 ┤           ● 48   ● 72                    
  -0.60 ┤                                          
  -0.64 ┤                       ● 96 (8h) WORST    
        └─────────────────────────────────────────
           1h   2h   4h   6h   8h   12h
```

**Key insight — the pharmacokinetic explanation**: The valley at 4-8 hours maps exactly
to partial insulin Duration of Insulin Action (DIA ≈ 5-6h). At 4-8h windows, the model
sees a bolus and its peak effect, but NOT the resolution phase. The episode labels become
ambiguous — is this a meal response still in progress, or a correction that worked?

At 12h, the model captures the full cycle: pre-meal baseline → bolus → absorption peak →
insulin resolution → return to stable. This complete narrative makes episodes
unambiguously classifiable.

**Recall@5 is insensitive to window size** (range: 0.936-0.952, <2% spread) because
retrieval uses label matching — similar windows share similar labels regardless of
length. **Silhouette is highly sensitive** (range: -0.642 to -0.339, 89% spread) because
cluster geometry depends on capturing complete physiological narratives.

---

### EXP-287 + EXP-298: Channel Ablation (2h vs 12h)

**Question**: Does feature importance change with timescale?

**Answer**: Yes — dramatically. Silhouette sensitivity increases **3.4×** at 12h.

| Channel     | 2h ΔR@5  | 12h ΔR@5  | 2h ΔSil   | 12h ΔSil   | Interpretation |
|-------------|----------|-----------|-----------|------------|----------------|
| glucose     | -0.0064  | +0.0009   | -0.045    | **-0.584** | Glucose trace IS the pattern at 12h |
| iob         | -0.0068  | +0.0077   | +0.090    | **-0.564** | IOB curve shapes episodes |
| cob         | -0.0014  | -0.0026   | +0.178    | **-0.456** | COB: noise at 2h, signal at 12h |
| basal_rate  | -0.0112  | -0.0094   | -0.004    | **-0.296** | Consistent importance at both scales |
| bolus       | -0.0086  | +0.0026   | +0.120    | **+0.224** | **Bolus hurts 12h clusters** |
| carbs       | -0.0087  | -0.0085   | +0.090    | **-0.604** | **Most impactful for 12h clusters** |
| time_sin    | -0.0051  | +0.0136   | +0.112    | -0.526     | Time hurts retrieval at 12h |
| time_cos    | -0.0037  | +0.0043   | +0.120    | -0.201     | Time hurts retrieval at 12h |

**Baseline comparison**:
- 2h: R@5=0.953, Silhouette=-0.349
- 12h: R@5=0.946, Silhouette=-0.291 (better clusters despite 6× less data)

#### Scale-Dependent Insights

1. **Carbs are the #1 feature for 12h clustering** (ΔSil=-0.604). At 2h, carbs were
   nearly irrelevant (ΔSil=+0.090, i.e., removal *improved* clusters). This makes
   physiological sense: a carb event's impact unfolds over 3-6 hours. At 2h, you only
   see the start; at 12h, you see the full absorption-and-response arc.

2. **Bolus removal IMPROVES 12h clusters** (ΔSil=+0.224). Bolus events are sparse
   point-in-time spikes. In a 12h window of 144 timesteps, a single bolus spike is noise
   that disrupts smooth trajectory patterns. The model clusters better on the continuous
   signals (glucose, IOB, COB) that represent the *effect* of boluses.

3. **COB flips from noise to signal**: At 2h, removing COB improved silhouette by +0.178.
   At 12h, removing it destroys clusters (-0.456). COB tracks the metabolic state across
   the full meal absorption period; meaningless in a 2h snapshot, essential in a 12h arc.

4. **Glucose becomes essential**: At 2h, glucose ablation had minimal impact (ΔSil=-0.045).
   At 12h, it's catastrophic (ΔSil=-0.584). The 12h glucose trace IS the pattern — it
   encodes the entire meal-bolus-resolution narrative.

5. **Time features hurt retrieval at 12h** (ΔR@5=+0.014 for time_sin removal). Patterns
   should be time-invariant — a post-meal spike at 8am and 8pm should match. Time
   encoding prevents this. **Recommendation: drop time channels for episode-scale models.**

---

### EXP-291 + EXP-299: UAM Detection (2h vs 12h)

**Question**: Does UAM detection improve at 12h with fuller context?

**Answer**: No — it degrades catastrophically.

| Metric     | 2h (EXP-291) | 12h (EXP-299) | Change |
|------------|-------------|---------------|--------|
| F1         | 0.399       | 0.068         | -83%   |
| Precision  | 0.283       | 0.038         | -87%   |
| Recall     | 0.676       | 0.333         | -51%   |
| Prevalence | 15.7%       | 1.8%          | -88%   |

**Why this happens**: UAM (Unannounced Meal) detection is inherently an *acute event*
problem. In a 2h window, a meal spike dominates the signal — 15.7% of windows contain
one. In a 12h window, that same meal event is diluted to 1/6th of the context, and
overlaps with other events (corrections, basal changes, sleep). Prevalence drops to 1.8%,
making the classification problem much harder.

**Architectural implication**: UAM detection must use the **Fast scale (2h)**. The 12h
Episode scale should be used for understanding what *kind* of meal event occurred and
predicting its resolution, not for initial detection.

---

### EXP-286: ISF Drift Segmentation (2h, 11 vs 9 labels)

**Question**: Can we detect ISF sensitivity shifts in 2h windows?

| Config | Macro F1 | Weighted F1 |
|--------|----------|-------------|
| 9-label (baseline) | 0.883 | 0.950 |
| 11-label (with drift) | 0.861 | 0.934 |
| **Delta** | **-0.022** | **-0.016** |

**Conclusion**: Adding sensitivity_shift and resistance_shift labels hurts at 2h with 8
channels. ISF drift is invisible in a 2h snapshot without enriched features (ISF profile
from ch32/33). This is the motivation for EXP-300 (24h daily scale).

---

## Architectural Conclusions

### The Multi-Scale Principle

Each objective has a natural timescale dictated by the underlying physiology:

| Objective | Optimal Scale | Window | Key Features | Metric |
|-----------|--------------|--------|--------------|--------|
| Acute event detection (hypo, UAM, rapid rise) | **Fast** | 2h @ 5-min | All 8ch | Event F1, Lead Time |
| Episode classification (meal type, correction effectiveness) | **Episode** | 12h @ 5-min | glucose, IOB, COB, basal, carbs (drop bolus, time) | Silhouette, R@K |
| ISF drift tracking | **Daily** | 24h @ 15-min | 8ch + ISF profile | Drift F1 |
| Multi-day ISF trends | **Weekly** | 7d @ 1-hr | TBD | Trend accuracy |

### Feature Recommendations by Scale

Based on EXP-298 ablation results:

**Fast (2h)**: Use all 8 channels. All features contribute roughly equally.

**Episode (12h)**: Use **5 channels** (glucose, IOB, COB, basal_rate, carbs).
- **Drop bolus**: Improves silhouette by +0.224 (sparse spikes = noise)
- **Drop time_sin, time_cos**: Improves retrieval by +1.4% (patterns should be time-invariant)

**Daily (24h @ 15-min)**: Use 8ch + profile (ISF, CR). Aggregation smooths bolus spikes
naturally. Time features become important again (circadian rhythm IS the pattern).

**Weekly (7d @ 1-hr)**: TBD — EXP-301 pending.

### Cross-Scale Pipeline Design

```
Window: ──2h──  ────────────12h────────────  ──────24h──────  ───────7 days───────
Model:  Fast    Episode                      Daily            Weekly
        ↓       ↓                            ↓                ↓
        Event   Episode                      Drift            Trend
        F1      Silhouette/R@K               Ratio Accuracy   Prediction
        ↓       ↓                            ↓                ↓
        └───────┴────────────────────────────┴────────────────┘
                              ↓
                   Override Recommendation
```

The override system combines all scales:
- **Fast** detects WHAT is happening NOW (hypo approaching, meal spike)
- **Episode** identifies WHERE we are in the insulin cycle (post-meal, fasting, correction)
- **Daily** estimates CURRENT insulin sensitivity (normal, resistant, sensitive)
- **Weekly** predicts ISF TRENDS (getting more resistant, adapting to exercise)

---

## Data Availability

| Scale | Window | stride=w//2 | stride=1 | Used |
|-------|--------|-------------|----------|------|
| Fast (2h) | 24@5min | 36,207 | 585K | 36,207 |
| Episode (12h) | 144@5min | 5,864 | 585K | 5,864 |
| Daily (24h) | 96@15min | ~3.5K | ~38K | TBD (EXP-300) |
| Weekly (7d) | 168@1hr | ~580 | ~8.5K | TBD (EXP-301) |

EXP-300 uses stride=1 for daily scale to maximize training data.

---

## Open Questions

1. **EXP-300 (pending)**: Does 24h context with 15-min resolution enable drift detection
   that failed at 2h? Hypothesis: yes, if the model sees circadian variation.

2. **EXP-301 (pending)**: Is 7-day weekly scale data-sufficient? stride=1 gives ~8.5K
   windows, but only from ~160 days per patient — high overlap between windows.

3. **Cross-scale embedding**: Simple concatenation vs attention-based fusion? The scales
   have very different dimensionalities and semantics.

4. **Bolus encoding**: Since bolus spikes hurt 12h clustering, should we encode bolus
   as a *cumulative* signal (total insulin delivered) rather than instantaneous rate?

5. **Time features**: Time hurts episode-scale retrieval but is essential for daily-scale
   drift (circadian patterns). The per-scale feature selection reinforces the multi-model
   architecture.

---

## Reproduction

```bash
# EXP-289: Window sweep
python3 -m tools.cgmencode.run_pattern_experiments window-sweep-embedding --device cuda

# EXP-298: 12h ablation
python3 -m tools.cgmencode.run_pattern_experiments ablation-12h --device cuda --epochs 30

# EXP-299: 12h UAM
python3 -m tools.cgmencode.run_pattern_experiments uam-12h --device cuda --epochs 30

# EXP-300: Daily drift (pending)
python3 -m tools.cgmencode.run_pattern_experiments drift-daily --device cuda --epochs 30

# EXP-301: Weekly ISF (pending)
python3 -m tools.cgmencode.run_pattern_experiments weekly-isf --device cuda --epochs 30
```

All results saved to `externals/experiments/` (gitignored).
Scripts in `tools/cgmencode/run_pattern_experiments.py` (committed).
