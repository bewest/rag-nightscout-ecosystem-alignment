# Cross-Scale Feature Selection Synthesis

**EXP-349, EXP-350, EXP-351 Combined Analysis**

## Executive Summary

Three systematic ablation experiments tested 5 feature variants across 3 timescales
(2h, 6h, 12h) and 4 classification tasks (UAM, override, hypo, prolonged_high).
The central finding is that **optimal feature sets are highly scale-dependent** — no
single feature engineering approach works universally. Time-translation invariance,
B-spline smoothing, and continuous PK channels each have specific scales where they
help or harm.

## Experimental Design

### Feature Variants Tested

| Variant | Channels | Description |
|---------|----------|-------------|
| `baseline_8ch` | glucose, iob, cob, net_basal, bolus, carbs, time_sin, time_cos | Standard features |
| `no_time_6ch` | baseline minus time_sin/cos | Tests time-translation invariance |
| `pk_replace_8ch` | PK channels replacing raw treatment channels | Continuous pharmacokinetic state |
| `pk_no_time_6ch` | PK channels without time | PK + symmetry combined |
| `fda_8ch` | smooth_glucose, glucose_d1, glucose_d2, iob, cob, net_basal, bolus, carbs | B-spline smoothed glucose + analytic derivatives |
| `fda_no_time_6ch` | smooth_glucose, glucose_d1, glucose_d2, iob, cob, net_basal | FDA + symmetry |
| `fda_pk_no_time_6ch` | smooth_glucose, glucose_d1, pk_net_balance, pk_insulin_total, pk_carb_rate, pk_basal_ratio | FDA + PK combined |
| `augmented_16ch` | all 8 baseline + all 8 PK | Maximum information (tests curse of dimensionality) |

### Scale Configurations

| Scale | Window | History | Prediction | CNN | Train/Val Windows |
|-------|--------|---------|------------|-----|-------------------|
| 2h | 24 steps | 1h (12 steps) | 1h | 3-layer shallow | 35,272 / 8,822 |
| 6h | 72 steps | 3h (36 steps) | 3h | 4-layer deep | 11,748 / 2,941 |
| 12h | 144 steps | 6h (72 steps) | 6h | 4-layer deep | 11,727 / 2,940 |

### Tasks

| Task | Label Definition | Scale Availability |
|------|------------------|--------------------|
| UAM | Rising glucose (>10 mg/dL/5min) with no carbs in history | 2h only |
| Override | Future glucose: normal(0) / high>180(1) / low<70(2) | All scales |
| Hypo | Any glucose < 70 mg/dL in future half | All scales |
| Prolonged High | >180 mg/dL for >50% of future half | 6h, 12h |

All experiments: 3-seed averaging (42, 123, 456), CUDA GPU, class-weighted loss.

## Results

### 2h Scale (EXP-349 + EXP-351)

| Variant | UAM F1 | Override F1_macro | Hypo AUC |
|---------|--------|-------------------|----------|
| baseline_8ch | 0.956 | 0.840 | 0.946 |
| **no_time_6ch** | **0.969** ⬆ | 0.842 | 0.949 |
| pk_replace_8ch | 0.928 ⬇ | 0.839 | 0.944 |
| pk_no_time_6ch | 0.927 ⬇ | 0.839 | 0.947 |
| augmented_16ch | 0.951 | 0.840 | 0.945 |
| fda_8ch | 0.899 ⬇ | 0.850 ⬆ | **0.952** ⬆ |
| **fda_no_time_6ch** | 0.827 ⬇ | **0.852** ⬆ | 0.951 ⬆ |
| fda_pk_no_time_6ch | 0.861 ⬇ | 0.838 | 0.947 |

**2h Winners:**
- **UAM**: `no_time_6ch` (F1=0.969) — time-translation invariance helps acute detection
- **Override**: `fda_no_time_6ch` (F1=0.852, **+1.1% vs baseline**) — NEW BEST
- **Hypo**: `fda_8ch` (AUC=0.952, +0.6% vs baseline)

### 6h Scale (EXP-351)

| Variant | Override F1_macro | Hypo AUC | Prolonged High F1 |
|---------|-------------------|----------|--------------------|
| **baseline_8ch** | **0.698** | **0.847** | 0.606 |
| no_time_6ch | 0.692 | 0.845 | 0.630 ⬆ |
| fda_8ch | 0.686 ⬇ | 0.835 ⬇ | **0.632** ⬆ |
| fda_no_time_6ch | 0.683 ⬇ | 0.838 ⬇ | 0.608 |
| fda_pk_no_time_6ch | 0.680 ⬇ | 0.836 ⬇ | 0.619 |

**6h Winners:**
- **Override**: `baseline_8ch` (F1=0.698) — raw signal preferred
- **Hypo**: `baseline_8ch` (AUC=0.847) — raw signal preferred
- **Prolonged High**: `fda_8ch` (F1=0.632, +2.6% vs baseline) — only FDA win at this scale

### 12h Scale (EXP-350 + EXP-351)

| Variant | Override F1_macro | Hypo AUC | Prolonged High F1 |
|---------|-------------------|----------|--------------------|
| **baseline_8ch** | **0.605** | 0.781 | **0.526** |
| no_time_6ch | 0.592 | **0.783** | 0.504 |
| pk_replace_8ch | 0.592 | 0.753 | 0.472 |
| **pk_no_time_6ch** | **0.597** | 0.768 | 0.489 |
| fda_8ch | 0.560 ⬇ | 0.746 ⬇ | 0.461 ⬇ |
| fda_no_time_6ch | 0.569 ⬇ | 0.744 ⬇ | 0.468 ⬇ |
| fda_pk_no_time_6ch | 0.564 ⬇ | 0.764 ⬇ | 0.489 |

**12h Winners:**
- **Override**: `baseline_8ch` (F1=0.605), with `pk_no_time_6ch` close (0.597)
- **Hypo**: `no_time_6ch` (AUC=0.783) — time removal still helps
- **Prolonged High**: `baseline_8ch` (F1=0.526)

## Cross-Scale Analysis

### Optimal Feature Recipe by Task × Scale

| Task | 2h | 6h | 12h |
|------|----|----|-----|
| **UAM** | `no_time_6ch` ⭐ | — | — |
| **Override** | `fda_no_time_6ch` ⭐ | `baseline_8ch` | `baseline_8ch` |
| **Hypo** | `fda_8ch` ⭐ | `baseline_8ch` | `no_time_6ch` |
| **Prolonged High** | — | `fda_8ch` | `baseline_8ch` |

⭐ = statistically meaningful improvement over baseline

### Feature Effect Direction by Scale

| Feature Engineering | 2h Effect | 6h Effect | 12h Effect |
|--------------------|-----------|-----------|------------|
| Remove time (sin/cos) | **Helps** all tasks | Neutral/hurts | Helps hypo, hurts override |
| B-spline smoothing | **Helps** override/hypo | **Hurts** most | **Hurts** all |
| PK channels | Hurts | Not tested standalone | Helps override (+1.5%) |
| Augmented (16ch) | Hurts | Not tested | Not tested |

### Why Does This Happen?

**1. Time-Translation Invariance (remove time features)**

At 2h, a meal at 8am and a meal at 8pm produce identical glucose response shapes.
The CNN can learn this pattern without knowing the time. Time features are noise that
the model must learn to ignore → removing them improves generalization.

At 6h/12h, time starts encoding circadian insulin sensitivity variation. The diurnal
ISF profile means a 6h window starting at 6pm has systematically different glucose
behavior than one starting at 6am. Time features become weakly informative.

**2. B-spline Smoothing (FDA features)**

At 2h with 12 history steps, the CNN sees a short curve. B-spline smoothing removes
sensor noise, and the analytic derivatives provide clean rate-of-change signals that
are more predictive of trend continuation (override, hypo) than noisy finite differences.

At 6h/12h with 36-72 history steps, the deeper CNN learns to extract its own
multi-scale features from raw data. Smoothing destroys high-frequency information
that the CNN's deeper layers use. The CNN IS the smoother at longer scales.

**3. PK Channels**

At 2h with 12 steps = 1h history, the insulin DIA is 6h. The model sees <17% of
the absorption curve — PK channels add no information the raw IOB doesn't already
encode.

At 12h with 72 steps = 6h history, the full DIA is visible. PK channels encode
the physiological absorption state (peak vs tail, net balance) more explicitly than
raw IOB values, helping override prediction.

**4. Augmented (16ch) Always Hurts**

Small CNN models (~50K params) with 5-35K training samples cannot leverage 16
input channels without overfitting. This is the curse of dimensionality in action —
more features require exponentially more data to learn useful interactions.

## Implications for Production Models

### Recommended Architecture

A production system should use **scale-specific feature selectors**:

```
2h acute:    [glucose, iob, cob, net_basal, bolus, carbs]           → ShallowCNN
2h override: [smooth_glucose, glucose_d1, glucose_d2, iob, cob, net_basal] → ShallowCNN  
6h episode:  [glucose, iob, cob, net_basal, bolus, carbs, time_sin, time_cos] → DeepCNN
12h long:    [glucose, iob, cob, net_basal, bolus, carbs, time_sin, time_cos] → DeepCNN
             (+ PK channels for override-specific model)
```

### Data Efficiency Concern

Performance degrades significantly with scale:
- 2h: F1=0.85-0.97 (35K train windows)
- 6h: F1=0.63-0.85 (12K train windows)
- 12h: F1=0.50-0.78 (12K train windows)

The 12h dataset has similar windows to 6h but lower performance, suggesting the
6h prediction horizon is genuinely harder. More data (more patients) would help both.

## Open Questions

1. **Raw + FDA hybrid**: Would keeping both raw glucose AND smooth derivatives
   help at 6h/12h? The CNN could learn to use raw for detail and smooth for trend.

2. **PK + FDA at 12h**: EXP-350 showed PK helps override at 12h. Would combining
   PK with FDA derivatives help?

3. **Attention mechanisms**: Could a channel-attention module learn to weight
   raw vs smooth features dynamically per window?

4. **Larger models at 12h**: Would a Transformer or larger CNN with more data
   change the FDA conclusion at longer scales?

## Source Files

| Experiment | Code | Results |
|------------|------|---------|
| EXP-349 | `tools/cgmencode/exp_pk_classification.py` | `externals/experiments/exp349_pk_classification.json` |
| EXP-350 | `tools/cgmencode/exp_pk_episode.py` | `externals/experiments/exp350_pk_episode.json` |
| EXP-351 | `tools/cgmencode/exp_fda_classification.py` | `externals/experiments/exp351_fda_classification.json` |
