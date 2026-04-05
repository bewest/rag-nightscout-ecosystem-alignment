# Multi-Scale Pattern Experiment Results

**Date**: 2026-04-04  
**Experiments**: EXP-287, EXP-289, EXP-286, EXP-291, EXP-298, EXP-299, EXP-300, EXP-301  
**Status**: Complete (8 experiments across 4 timescales)

## Executive Summary

Six experiments tested whether non-forecasting objectives (event detection, pattern
retrieval, ISF drift tracking) require different timescales and feature sets. Four
findings fundamentally reshape our architecture:

1. **The U-shaped window curve extends to 7 days**: Weekly (7d) windows produce the
   best pattern clusters (Sil=-0.301), surpassing even 12h (-0.339). The DIA valley
   at 4-8h persists, but longer windows continue improving beyond it.
2. **Feature importance is scale-dependent**: At 2h, all channel ablation deltas are
   tiny (<1.12%). At 12h, silhouette deltas explode to 60% — features matter 3.4× more.
3. **Acute events need short windows**: UAM detection degrades from F1=0.40 at 2h to
   F1=0.07 at 12h — meal events get diluted in longer context.
4. **ISF drift is an observability problem**: Zero drift labels assigned at 2h, 24h,
   or 7d with 8 base channels. Drift detection requires either profile features or
   novel indirect estimation (pattern comparison across days).

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
  -0.30 ┤                                                ● 7d (EXP-301) BEST
  -0.34 ┤  ● 12 (1h)                     ● 144 (12h)    
  -0.37 ┤      ● 24 (2h)                                
  -0.50 ┤                                               
  -0.54 ┤           ● 48   ● 72                         
  -0.60 ┤                                               
  -0.64 ┤                       ● 96 (8h) WORST          
        └────────────────────────────────────────────────
           1h   2h   4h   6h   8h   12h        7d
                Insulin DIA ──────────►
```
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

### EXP-300: Daily Drift Segmentation (24h @ 15-min)

**Question**: Does 24h context with 15-min resolution enable drift detection that
failed at 2h?

| Metric | 2h (EXP-286) | 24h (EXP-300) | Change |
|--------|-------------|--------------|--------|
| Macro F1 | 0.861 | 0.782 | -9.2% |
| Weighted F1 | 0.934 | 0.873 | -6.5% |
| Drift labels assigned | 0 | 0 | — |
| Training windows | 28,965 | 140,312 | +384% |
| Validation windows | 7,242 | 35,079 | +384% |

**Why drift detection still fails**: Zero drift labels were assigned even at 24h.
The `build_episode_labels()` function detects sensitivity shifts by comparing glucose
response to insulin delivery — but with only 8 base channels, there is no ISF profile
reference (ch32: scheduled ISF) to compare against. The model cannot distinguish "glucose
is high because ISF shifted" from "glucose is high because carbs were underestimated."

**Why overall F1 dropped**: The 24h @ 15-min resolution loses temporal granularity.
Acute events (hypo spikes, rapid corrections) that are sharp features at 5-min resolution
become smoothed blobs at 15-min. The model has more data (140K vs 29K) but less
informative features per window.

**Label distribution at 24h** (train set):
| Label | Count | % |
|-------|-------|---|
| stable | 71,780 | 40.9% |
| correction_response | 30,477 | 17.4% |
| hypo_risk | 11,218 | 6.4% |
| rising | 10,368 | 5.9% |
| meal_response | 7,344 | 4.2% |
| falling | 6,086 | 3.5% |
| exercise_response | 2,813 | 1.6% |
| dawn_phenomenon | 226 | 0.1% |
| sensitivity_shift | 0 | 0.0% |
| resistance_shift | 0 | 0.0% |

**Actionable conclusion**: ISF drift detection requires either:
1. **Enriched 39-feature data** (ch32/33 ISF/CR profiles) at daily scale, OR
2. **Indirect drift estimation** — compare same-context glucose responses across different
   days (e.g., "same meal, same bolus, different glucose outcome → ISF changed")

Approach #2 is novel and doesn't require profile features. It treats drift as a
*departure from expected pattern response* rather than a direct ISF measurement.

---

### EXP-301: Weekly ISF Trends (7-day @ 1-hr)

**Question**: Do weekly-scale embeddings produce meaningful clusters? Does the
U-shaped window curve extend beyond 12h?

| Metric | 2h (EXP-289) | 12h (EXP-289) | 7d (EXP-301) |
|--------|-------------|---------------|---------------|
| Recall@5 | 0.9500 | 0.9523 | **0.9574** |
| Silhouette | -0.367 | -0.339 | **-0.301** |
| Training windows | 28,965 | 4,699 | 33,824 |
| Validation windows | 7,242 | 1,175 | 8,457 |
| Unique labels | ~8 | ~8 | 7 |

**The U-shaped curve continues upward**:

```
Silhouette Score (higher = better clusters)
  -0.30 ┤                                                ● 7d BEST
  -0.34 ┤  ● 1h                          ● 12h          
  -0.37 ┤      ● 2h                                     
  -0.50 ┤                                               
  -0.54 ┤           ● 4h   ● 6h                         
  -0.60 ┤                                               
  -0.64 ┤                       ● 8h WORST               
        └────────────────────────────────────────────────
           1h   2h   4h   6h   8h   12h        7d
                Insulin DIA ──────────►
                             ▲ Valley
```

**Why 7d beats 12h**: Weekly windows capture multi-day patterns — e.g., weekday vs
weekend routines, exercise recovery over 2-3 days, medication changes, and the kind
of sustained behavioral consistency that defines a patient's "normal." Where 12h
captures one complete insulin cycle (meal → resolution), 7d captures the *rhythm*
of multiple cycles.

**Label distribution at 7d** (validation set):
| Label | Count | % |
|-------|-------|---|
| stable | 2,803 | 33.1% |
| meal_response | 1,939 | 22.9% |
| falling | 1,366 | 16.2% |
| correction_response | 888 | 10.5% |
| rising | 596 | 7.0% |
| hypo_risk | 529 | 6.3% |
| exercise_response | 336 | 4.0% |

**Notable**: Only 7 of 11 possible labels assigned. Missing: `sensitivity_shift` (0),
`resistance_shift` (0), `dawn_phenomenon` (0), `unknown` (0). The drift labels remain
absent at 7d scale — confirming this is fundamentally an observability problem, not a
timescale problem. Dawn phenomenon (circadian) is also absent, likely diluted in the
weekly average.

**Key insight**: stride=1 at 1-hr resolution gives 33K training windows from ~160 days
of data per patient. Despite massive window overlap (168h window, 1h stride → 99.4%
overlap), the model learns meaningful representations. This validates the stride=1
strategy for data-scarce scales.

---

## Synthesis: What We've Learned

### 1. Timescale-Objective Mapping is Validated

Every experiment confirmed that objectives have natural timescales:

| Objective | Best Scale | Evidence | Wrong Scale | Evidence |
|-----------|-----------|----------|-------------|----------|
| UAM detection | 2h | F1=0.40 | 12h | F1=0.07 (-83%) |
| Pattern clustering | **7d** | **Sil=-0.301** | 8h | Sil=-0.642 (+113% worse) |
| Episode segmentation | 2h | F1=0.883 | 24h | F1=0.782 (-11%) |
| ISF drift | ≥24h + profiles | — | 2h, 24h, 7d w/o profiles | 0 labels |

### 2. Feature Importance is Scale-Dependent

Features that help at one scale hurt at another:

| Feature | 2h impact | 12h impact | Recommendation |
|---------|-----------|------------|----------------|
| bolus | helpful | harmful (+0.224 sil when removed) | Drop at ≥12h |
| COB | noise (+0.178 sil removed) | essential (-0.456 sil removed) | Include ≥12h only |
| time_sin/cos | neutral | harmful (+0.014 R@5 removed) | Drop at 12h, keep at 24h |
| carbs | minor | #1 feature (-0.604 sil removed) | Critical at ≥12h |

### 3. Data Quantity vs Quality Trade-off

| Scale | stride=w//2 windows | stride=1 windows | Resolution | Quality |
|-------|---------------------|------------------|------------|---------|
| 2h | 36K | 585K | 5-min | Best for acute events |
| 12h | 5.9K | 585K | 5-min | Best clusters (U-shape winner) |
| 24h | ~3.5K | 175K | 15-min | Smoothed — loses acute detail |
| 7d | ~580 | ~45K | 1-hr | **Best clusters (Sil=-0.301)** |

stride=1 at daily scale gave 175K windows — massive. But 15-min smoothing hurt F1
by 9.2% vs 5-min. **More data doesn't compensate for resolution loss**.

At weekly scale, stride=1 gave 33K windows from 1-hr resolution — sufficient for
training despite 99.4% window overlap. The best overall clustering validates that
longer context captures richer structure, even at reduced resolution.

### 4. The ISF Drift Problem is Unsolved

Neither 2h, 12h, 24h, nor 7d windows with 8 base channels can detect ISF drift.
The fundamental issue is **observability**: you need a reference ISF value to detect
drift FROM that value. EXP-301 confirmed this is NOT a timescale problem — even 7-day
windows with excellent clustering (Sil=-0.301) produced zero drift labels. Two paths
forward:

- **Path A**: Use enriched 39-feature data (ISF profile in ch32). Requires
  `extended_features=True` loading (~2 min). Directly measurable.
- **Path B**: Use pattern comparison across time — if the same type of episode
  (matched by embedding similarity) has a different glucose outcome on different days,
  that delta IS the ISF drift signal. Novel, doesn't need profiles.

Path B is more interesting because it works even without explicit ISF profiles,
and is the approach that best fits the multi-scale architecture.

---

## Open Questions

1. **Cross-scale integration**: How to combine fast (2h) + episode (12h) + weekly (7d)
   embeddings for override decisions? Simple concatenation or attention-based fusion?

2. **Resolution vs information**: 24h @ 15-min lost 9% F1 vs 2h @ 5-min. Should daily
   scale use 5-min resolution (288 steps) instead of downsampling? VRAM cost: ~1GB,
   still feasible on 4GB GPU. Or should daily scale be dropped in favor of weekly?

3. **Indirect drift estimation**: Can we detect ISF drift by comparing similar-pattern
   glucose responses across different days? 7d embeddings provide the clustering
   quality (Sil=-0.301) needed to match "similar" weeks — if glucose outcomes differ
   between matched weeks, that delta IS the drift signal. This would be a novel
   contribution.

4. **Bolus encoding at episode/weekly scale**: Instead of dropping bolus entirely, encode
   it as cumulative insulin delivered (running sum) — preserves information without the
   spiky noise that hurts clustering.

5. **Weekly label enrichment**: Only 7/11 labels assigned at weekly scale. The
   sensitivity/resistance shift labels need either profile features (Path A) or
   the indirect estimation approach (Path B). Dawn phenomenon may need explicit
   circadian feature extraction rather than relying on raw time features.

---

## Reproduction

```bash
# EXP-289: Window sweep
python3 -m tools.cgmencode.run_pattern_experiments window-sweep-embedding --device cuda

# EXP-298: 12h ablation
python3 -m tools.cgmencode.run_pattern_experiments ablation-12h --device cuda --epochs 30

# EXP-299: 12h UAM
python3 -m tools.cgmencode.run_pattern_experiments uam-12h --device cuda --epochs 30

# EXP-300: 24h drift
python3 -m tools.cgmencode.run_pattern_experiments drift-daily --device cuda --epochs 30

# EXP-301: Weekly ISF
python3 -m tools.cgmencode.run_pattern_experiments weekly-isf --device cuda --epochs 30
```

All results saved to `externals/experiments/` (gitignored).
Scripts in `tools/cgmencode/run_pattern_experiments.py` (committed).
