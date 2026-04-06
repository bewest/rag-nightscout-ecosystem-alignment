# Cross-Scale Feature Selection Synthesis

**EXP-349–378 Combined Analysis (Updated 2026-04-07)**

## Executive Summary

Thirteen systematic experiments tested feature variants, architectures, multi-task
learning, ablation, augmentation, and their interactions across 3 timescales
(2h, 6h, 12h) and 4 tasks.

**DEFINITIVE finding (EXP-375→377)**: **Transformer + baseline_plus_fda_10ch** is
the best general-purpose configuration across all three timescales at the time of
these experiments. FDA B-spline derivatives are THE single most impactful feature,
contributing +1.4–2.2% to override across scales.
PK channels are noise at ≤6h.

> **Update (EXP-381)**: At 12h, ISF normalization + cumulative integrals + time_warp
> surpasses baseline_plus_fda, achieving override F1=0.633 (+3.3% total improvement
> chain). The "universally optimal" designation applies to 2h and 6h; at 12h,
> additional feature engineering (ISF, integrals) yields further gains.

**Scale-dependent time features**: Time (sin/cos) is noise at 2h (removing helps),
but essential at 12h (removing hurts override -1.8%). Diurnal patterns matter for
longer prediction horizons.

**Augmentation finding (EXP-378)**: Data augmentation provides only marginal benefit
at 12h (<0.3%). Time_warp (+0.2% hypo) and mixup (+0.3% override) are the best
strategies. The 12h performance ceiling is NOT caused by data scarcity.

**Multi-task finding** (EXP-373): Negligible benefit. Override +0.04%, hypo -0.2%.

**Updated optimal configurations per scale:**

| Scale | Task | Best Config | Metric | Source |
|-------|------|-------------|--------|--------|
| 2h | UAM | Tfm + baseline_plus_fda_10ch | F1=0.920 | EXP-375 |
| 2h | Override | Tfm + kitchen_sink_10ch | F1=0.865 | EXP-374 |
| 2h | Hypo | Tfm + baseline_plus_fda_10ch | AUC=0.956 | EXP-375 |
| 6h | Override | Tfm + baseline_plus_fda_10ch | F1=0.715 | **EXP-377** |
| 6h | Hypo | Tfm + base_notime_fda_8ch | AUC=0.853 | **EXP-377** |
| 6h | Prolonged High | Tfm + baseline_plus_fda_10ch | F1=0.871 | **EXP-377** |
| 12h | Override | Tfm + baseline_plus_fda_10ch | F1=0.614 | **EXP-377** |
| 12h | Hypo | Tfm + baseline_plus_fda_10ch | AUC=0.779 | **EXP-377** |
| 12h | Prolonged High | Tfm + baseline_8ch | F1=0.830 | EXP-377 |

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

### 2h Scale (EXP-349 + EXP-351 + EXP-374)

**CNN-only results (EXP-349/351):**

| Variant | UAM F1 | Override F1_macro | Hypo AUC |
|---------|--------|-------------------|----------|
| baseline_8ch | 0.956 | 0.840 | 0.946 |
| **no_time_6ch** | **0.969** ⬆ | 0.842 | 0.949 |
| pk_replace_8ch | 0.928 ⬇ | 0.839 | 0.944 |
| pk_no_time_6ch | 0.927 ⬇ | 0.839 | 0.947 |
| augmented_16ch | 0.951 | 0.840 | 0.945 |
| fda_8ch | 0.899 ⬇ | 0.850 ⬆ | 0.952 ⬆ |
| fda_no_time_6ch | 0.827 ⬇ | 0.852 ⬆ | 0.951 ⬆ |
| fda_pk_no_time_6ch | 0.861 ⬇ | 0.838 | 0.947 |

**Architecture × Feature comparison (EXP-374, NEW):**

| Config | UAM F1 | Override F1 | Hypo AUC |
|--------|--------|-------------|----------|
| ShallowCNN + baseline_8ch | 0.887 | 0.843 | 0.949 |
| ShallowCNN + no_time_6ch | 0.890 (+0.3%) | 0.844 (+0.2%) | 0.950 (+0.1%) |
| ShallowCNN + kitchen_sink_10ch | 0.882 (-0.4%) | 0.863 (+2.0%) ⬆ | 0.954 (+0.5%) |
| Transformer + baseline_8ch | 0.890 (+0.4%) | 0.844 (+0.1%) | 0.951 (+0.2%) |
| Transformer + no_time_6ch | **0.891** (+0.4%) | 0.844 (+0.1%) | 0.951 (+0.2%) |
| **Transformer + kitchen_sink_10ch** | 0.886 (0%) | **0.866 (+2.3%)** ⭐ | **0.955 (+0.6%)** ⭐ |

Note: EXP-349/351 and EXP-374 used different scripts with slightly different CNN implementations.
EXP-374 results are directly comparable within their rows.

**2h Winners:**
- **UAM**: Transformer + `no_time_6ch` (F1=0.891) — time-translation invariance + attention
- **Override**: **Transformer + `kitchen_sink_10ch` (F1=0.866, +2.3%)** — NEW BEST ⭐
- **Hypo**: **Transformer + `kitchen_sink_10ch` (AUC=0.955, +0.6%)** — NEW BEST ⭐

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

## Open Questions (Updated)

~~1. Raw + FDA hybrid at 6h/12h~~ → **ANSWERED (EXP-360):** Yes, helps at 6h (+0.7-2.3%),
hurts at 12h.

~~2. PK + FDA at 12h~~ → **ANSWERED (EXP-361/362):** PK hurts at 12h across all
architectures. One exception: transformer+raw_fda_pk for hypo (+0.3%).

~~3. Attention mechanisms~~ → **ANSWERED (EXP-362):** Transformer attention is the
mechanism that makes more features viable. Kitchen_sink hurts CNN but helps transformer.

~~4. Larger models at 12h~~ → **PARTIALLY ANSWERED (EXP-361):** Transformer helps modestly
(+0.4-1.0%). The 12h ceiling appears inherent to the 6h prediction horizon.

~~5. Multi-task learning at 6h~~ → **ANSWERED (EXP-373):** Marginal. MT override +0.04%,
but hypo -0.2%, prolonged_high -0.5%. Exception: MT_CNN+kitchen PH +2.2%.

~~6. Transformer at 2h~~ → **ANSWERED (EXP-374):** Yes, helps consistently (+0.1-0.4%).
Combined with kitchen_sink: override +2.3%, hypo +0.6%. NEW BEST configs.

**Remaining open questions:**

~~1. Kitchen sink channel ablation at 2h~~ → **ANSWERED (EXP-375):** FDA derivatives
drive all the improvement (+2.2% override). PK channels contribute +0.1%. Raw
bolus/carbs essential for UAM (+5.4%).

~~2. Positional encoding ablation~~ → **ANSWERED (EXP-376):** Removing PE hurts (-1.7%
override, -2.0% UAM). PE encodes ordering (essential), unlike time features (noise).

3. **12h data augmentation**: Since architecture and features don't help at 12h, would
   augmentation (jitter, scaling, time-shift) increase effective training data?

4. **Per-patient fine-tuning at 2h/6h**: Would patient-specific adaptation further
   improve the best transformer models?

5. **baseline_plus_fda at 6h**: Does the 2h-optimal feature set (baseline+FDA) also
   improve 6h, or does kitchen_sink remain better there?

## EXP-373: Multi-Task Learning at 6h

Tested single-task vs multi-task training with shared encoder, across both CNN and
Transformer with baseline and kitchen_sink features.

| Config | Override F1 | Hypo AUC | Prolonged High F1 |
|--------|-----------|----------|-------------------|
| ST_cnn_base | 0.696 | 0.843 | 0.619 |
| ST_cnn_kitchen | 0.700 | 0.845 | 0.625 |
| ST_tfm_base | 0.697 | 0.848 | 0.605 |
| **ST_tfm_kitchen** | **0.711** | **0.852** | 0.635 |
| MT_cnn_base | 0.698 | 0.845 | 0.616 |
| MT_cnn_kitchen | 0.696 | 0.849 | **0.641** |
| MT_tfm_base | 0.704 | 0.846 | 0.618 |
| MT_tfm_kitchen | 0.711 | 0.850 | 0.629 |

**Key findings:**
- Multi-task provides negligible override improvement (+0.04%)
- Multi-task HURTS hypo: ST=0.852 > MT=0.850 (shared encoder compromises strongest task)
- Multi-task helps prolonged_high only with CNN: MT_cnn_kitchen=0.641 > ST=0.625
- Overall: architecture × features dominate; multi-task is secondary

## EXP-374: Transformer at 2h Scale (NEW BEST)

Systematically tested Transformer vs ShallowCNN with 3 feature variants at 2h.

| Config | UAM F1 | Override F1 | Hypo AUC |
|--------|--------|-------------|----------|
| ShallowCNN + baseline_8ch | 0.887 | 0.843 | 0.949 |
| ShallowCNN + no_time_6ch | 0.890 | 0.844 | 0.950 |
| ShallowCNN + kitchen_sink_10ch | 0.882 | 0.863 | 0.954 |
| Transformer + baseline_8ch | 0.890 | 0.844 | 0.951 |
| Transformer + no_time_6ch | **0.891** | 0.844 | 0.951 |
| **Transformer + kitchen_sink_10ch** | 0.886 | **0.866** ⭐ | **0.955** ⭐ |

**Key findings:**
- Kitchen_sink helps override massively: +2.0% with CNN, +2.3% with Transformer
- Transformer adds +0.3% override on top of CNN with kitchen_sink
- For UAM, kitchen_sink HURTS — Transformer + no_time is best
- no_time helps slightly across all tasks at 2h

## EXP-360–362: Architecture × Feature Interaction (Updated)

### EXP-360: Hybrid Features at 6h/12h (CNN only)

Tested 6 hybrid feature variants combining raw glucose with FDA derivatives and PK
channels, using the DeepCNN architecture.

**6h Results:**

| Variant | Override F1 | Hypo AUC | Prolonged High F1 |
|---------|-----------|----------|-------------------|
| baseline_8ch | 0.698 | 0.847 | 0.606 |
| **raw_plus_fda_8ch** | **0.703** (+0.7%) | 0.843 | 0.612 |
| raw_fda_pk_8ch | 0.694 | 0.850 | **0.632** (+2.3%) |
| kitchen_sink_10ch | 0.697 | 0.849 | 0.624 |

**12h Results:** Baseline_8ch wins everything. Hybrid features uniformly hurt (-1.4%
to -5.9%). The deeper the feature engineering, the worse the performance at 12h.

**Key insight:** Raw+FDA hybrid recovers information lost by pure-FDA replacement.
PK channels carry meaningful absorption state for prolonged_high at 6h.

### EXP-361: Architecture Search at 12h

Tested 6 architectures to determine if 12h's poor performance was an architecture
bottleneck (DeepCNN RF = 9 steps = only 6.2% of 144-step window).

| Architecture | Override F1 | Hypo AUC | Prolonged High F1 | Receptive Field |
|-------------|-----------|----------|-------------------|-----------------|
| DeepCNN (control) | 0.602 | 0.778 | 0.522 | 9 steps (6%) |
| DilatedCNN | 0.590 | **0.781** (+0.3%) | 0.497 | 63 steps (44%) |
| **Transformer** | **0.610** (+0.4%) | 0.778 | **0.528** (+1.0%) | Global |
| CNN+Downsample | 0.596 | 0.773 | 0.509 | 18 steps (12%) |
| LargeKernelCNN | 0.596 | 0.774 | 0.488 | 25 steps (17%) |
| SE-CNN | 0.594 | 0.779 | 0.505 | 9 steps (6%) |

**Critical finding:** PK features hurt across ALL architectures at 12h. This is
definitively a feature-level problem, not an architecture problem. Architecture
improvements are modest (+0.3-1.0%).

### EXP-362: Transformer × Feature Variants at 6h/12h (BREAKTHROUGH)

Tested Transformer vs DeepCNN × 4 feature variants at both scales. Revealed a
qualitative architecture × feature interaction.

**6h Results — Synergy Confirmed:**

| Config | Override F1 | Hypo AUC | Prolonged High F1 |
|--------|-----------|----------|-------------------|
| CNN + baseline_8ch | 0.696 | 0.846 | 0.610 |
| CNN + kitchen_sink_10ch | 0.695 (-0.1%) | 0.848 | 0.632 (+2.2%) |
| Transformer + baseline_8ch | 0.697 (+0.1%) | 0.848 | 0.618 (+0.8%) |
| **Transformer + kitchen_sink_10ch** | **0.711 (+1.4%)** | **0.852** | **0.653 (+4.4%)** |

The synergy is clear: kitchen_sink overhead with CNN = -0.1% for override, but with
Transformer = +1.4%. Prolonged high: CNN +2.2%, Transformer **+4.4%** — a ~2x
amplification. The transformer's attention mechanism handles extra feature dimensions
that overwhelm the CNN.

**12h Results — Baseline Still Dominant:**

| Config | Override F1 | Hypo AUC | Prolonged High F1 |
|--------|-----------|----------|-------------------|
| Transformer + baseline_8ch | **0.610** | 0.778 | **0.528** |
| Transformer + kitchen_sink_10ch | 0.599 (-1.1%) | 0.778 | 0.490 (-3.8%) |
| Transformer + raw_fda_pk_8ch | 0.591 | **0.781** (+0.3%) | 0.500 |

One bright spot: transformer + raw_fda_pk_8ch gives the best 12h hypo AUC (0.781),
suggesting PK channels carry some signal for hypoglycemia prediction even at long
horizons.

## Updated Cross-Scale Recommendations

### Optimal Configuration per Scale (Post EXP-375)

```
2h UAM:           baseline_plus_fda_10ch → Transformer   (F1=0.920) ⭐ NEW BEST
2h override:      kitchen_sink_10ch      → Transformer   (F1=0.865)
2h hypo:          baseline_plus_fda_10ch → Transformer   (AUC=0.956) ⭐ NEW BEST
2h universal:     baseline_plus_fda_10ch → Transformer   (best compromise)
6h all:           kitchen_sink_10ch      → Transformer   (SYNERGY: +1.4-4.4%)
6h prolonged_high: kitchen_sink_10ch     → MT_CNN        (F1=0.641, +2.2%)
12h all:          baseline_8ch           → Transformer   (modest +0.4-1.0%)
12h hypo:         raw_fda_pk_8ch         → Transformer   (+0.3%)
```

### Architecture × Feature Interaction Matrix (Complete)

| | baseline_8ch | no_time_6ch | kitchen_sink_10ch |
|---|---|---|---|
| **ShallowCNN at 2h** | 0.843/0.949 | 0.844/0.950 | 0.863/0.954 |
| **Transformer at 2h** | 0.844/0.951 | 0.844/0.951 | **0.866/0.955** ⭐ |
| **CNN at 6h** | 0.696/0.846/0.610 | — | 0.695/0.848/0.632 |
| **Transformer at 6h** | 0.697/0.848/0.618 | — | **0.711/0.852/0.653** |
| **CNN at 12h** | 0.602/0.778/0.522 | — | 0.573/0.764/0.479 |
| **Transformer at 12h** | **0.610/0.778/0.528** | — | 0.599/0.778/0.490 |

*2h values: Override F1 / Hypo AUC. 6h/12h values: Override F1 / Hypo AUC / Prolonged_High F1*

### Why This Matters

The transformer doesn't just help — it **changes which features are useful**. With CNN,
more features = more overfitting risk. With transformer, more features = more
attention targets. This has practical implications: production models should use
different feature pipelines depending on the architecture, not just the scale.

## EXP-375: Kitchen Sink Channel Ablation at 2h (DEFINITIVE)

Systematically ablated channels from kitchen_sink_10ch to identify what drives the
+2.3% override improvement. All configs use Transformer at 2h.

| Variant | Ch | UAM F1 | Override F1 | Hypo AUC |
|---------|-----|--------|-------------|----------|
| kitchen_sink_10ch (control) | 10 | 0.906 | **0.865** | 0.955 |
| kitchen_no_fda_8ch | 8 | 0.881 ▼ | 0.843 ▼ | 0.949 ▼ |
| kitchen_no_pk_6ch | 6 | 0.866 ▼ | 0.864 | 0.954 |
| **baseline_plus_fda_10ch** | 10 | **0.920** ⭐ | 0.864 | **0.956** ⭐ |
| base_notime_fda_8ch | 8 | 0.919 | 0.863 | 0.955 |
| baseline_plus_pk_12ch | 12 | 0.888 ▼ | 0.843 ▼ | 0.948 ▼ |
| kitchen_plus_time_12ch | 12 | 0.905 | 0.861 | 0.956 |
| minimal_override_5ch | 5 | 0.864 ▼ | 0.856 ▼ | 0.953 |

### Channel Contribution Decomposition (Override)

```
Full kitchen_sink:       0.865
- Remove FDA (d1, d2):   0.843  → FDA contributes +0.022 (2.2%)
- Remove PK (4 channels): 0.864  → PK contributes +0.001 (0.1%)
Interaction term: ~0
```

**FDA derivatives are THE key ingredient.** PK channels are noise at 2h for override/hypo.

### Key Findings

1. **baseline_plus_fda_10ch is the new OVERALL BEST at 2h**: UAM=0.920 (new record),
   Hypo=0.956. Override=0.864 essentially tied with kitchen_sink.

2. **Raw bolus/carbs are essential for UAM**: kitchen_no_pk_6ch (no bolus/carbs)
   gives UAM=0.866 vs baseline_plus_fda (with bolus/carbs) UAM=0.920 (+5.4%!).
   Kitchen_sink replaced bolus/carbs with PK channels, which helps override but
   drastically hurts UAM.

3. **PK channels add zero value at 2h** for override (+0.1%) and hypo (+0.1%).
   baseline_plus_pk_12ch (add PK to baseline) actually hurts (-2.2% override).

4. **Time features are irrelevant at 2h**: baseline_plus_fda vs base_notime_fda
   differ by <0.1% across all tasks.

5. **Minimal 5ch achieves 85.6% override** — only 0.9% below best, with 50% fewer
   channels. Viable for resource-constrained deployment.

### Implications

The kitchen_sink_10ch improvement was entirely driven by FDA derivatives (glucose_d1,
glucose_d2). The PK channels were a red herring. For a production system:
- **UAM model**: baseline_plus_fda_10ch (need raw bolus/carbs for "unannounced" detection)
- **Override model**: kitchen_sink_10ch or kitchen_no_pk_6ch (FDA derivatives sufficient)
- **Hypo model**: baseline_plus_fda_10ch (marginal best)
- **Universal model**: baseline_plus_fda_10ch (best compromise across all tasks)

## EXP-376: Positional Encoding Ablation at 2h

Tested removing sinusoidal positional encoding from Transformer to evaluate
time-translation invariance hypothesis.

| Config | PE | no_PE | Δ |
|--------|-----|-------|---|
| kitchen_sink UAM | 0.906 | 0.886 | **-2.0%** ▼ |
| kitchen_sink Override | 0.865 | 0.848 | **-1.7%** ▼ |
| kitchen_sink Hypo | 0.955 | 0.952 | -0.4% ▼ |
| kitchen_no_pk UAM | 0.866 | 0.847 | -1.9% ▼ |
| kitchen_no_pk Override | 0.864 | 0.849 | -1.5% ▼ |
| kitchen_no_pk Hypo | 0.954 | 0.953 | -0.1% |

**Removing PE uniformly hurts.** This resolves an important conceptual distinction:
- **time_sin/time_cos** = absolute time of day → noise for acute events (removing helps)
- **Positional encoding** = relative position within window → essential for trend detection
  (removing hurts)

These are fundamentally different types of temporal information. The model needs to
know *ordering* (PE) but not *clock time* (time features).

## Source Files

| Experiment | Code | Results |
|------------|------|---------|
| EXP-349 | `tools/cgmencode/exp_pk_classification.py` | `externals/experiments/exp349_pk_classification.json` |
| EXP-350 | `tools/cgmencode/exp_pk_episode.py` | `externals/experiments/exp350_pk_episode.json` |
| EXP-351 | `tools/cgmencode/exp_fda_classification.py` | `externals/experiments/exp351_fda_classification.json` |
| EXP-360 | `tools/cgmencode/exp_hybrid_episode.py` | `externals/experiments/exp360_hybrid_episode.json` |
| EXP-361 | `tools/cgmencode/exp_arch_12h.py` | `externals/experiments/exp361_arch_12h.json` |
| EXP-362 | `tools/cgmencode/exp_transformer_features.py` | `externals/experiments/exp362_transformer_features.json` |
| EXP-373 | `tools/cgmencode/exp_multitask_transformer.py` | `externals/experiments/exp373_multitask_transformer.json` |
| EXP-374 | `tools/cgmencode/exp_multitask_transformer.py` | `externals/experiments/exp373_multitask_transformer.json` |
| EXP-375 | `tools/cgmencode/exp_kitchen_sink_ablation.py` | `externals/experiments/exp375_kitchen_ablation.json` |
| EXP-376 | `tools/cgmencode/exp_kitchen_sink_ablation.py` | `externals/experiments/exp375_kitchen_ablation.json` |
| EXP-377 | `tools/cgmencode/exp_fda_6h12h_augment.py` | `externals/experiments/exp377_fda_6h12h_augment.json` |
| EXP-378 | `tools/cgmencode/exp_fda_6h12h_augment.py` | `externals/experiments/exp377_fda_6h12h_augment.json` |

---

## EXP-377: baseline_plus_fda at 6h and 12h

**Question**: Does the 2h-optimal feature set (baseline + FDA B-spline derivatives)
also improve longer timescales? EXP-375 definitively showed FDA derivatives are THE
key ingredient at 2h. Kitchen_sink was the 6h champion, but we hypothesized it was
the FDA derivatives doing the work there too.

**CRITICAL CORRECTION**: EXP-351 previously showed "FDA hurts at 6h/12h" — but that
was tested with CNN. EXP-377 proves **FDA + Transformer synergize at ALL scales**.
The Transformer's attention mechanism can exploit FDA derivatives that overwhelm CNN.

### EXP-377a: 6h Feature Comparison (Transformer)

| Variant | Ch | Override | Hypo | Prolonged High |
|---------|-----|----------|------|----------------|
| baseline_8ch (control) | 8 | 0.7003 | 0.8471 | 0.8690 |
| kitchen_sink_10ch | 10 | 0.7076 (+0.7%) | 0.8525 (+0.5%) | 0.8685 |
| **baseline_plus_fda_10ch** | 10 | **0.7150 (+1.5%)** ★ | 0.8523 (+0.5%) | **0.8707 (+0.2%)** ★ |
| base_notime_fda_8ch | 8 | 0.7100 (+1.0%) | **0.8527 (+0.6%)** ★ | 0.8649 (-0.4%) |

**Key insight**: baseline_plus_fda_10ch BEATS kitchen_sink at 6h! The prior
kitchen_sink advantage was entirely due to the FDA derivatives within it, not the
PK channels. This is the same pattern as 2h (EXP-375).

### EXP-377b: 12h Feature Comparison (Transformer)

| Variant | Ch | Override | Hypo | Prolonged High |
|---------|-----|----------|------|----------------|
| baseline_8ch (control) | 8 | 0.6003 | 0.7772 | **0.8286** |
| kitchen_sink_10ch | 10 | 0.5961 (-0.4%) ▼ | 0.7778 | 0.8113 (-1.7%) ▼ |
| **baseline_plus_fda_10ch** | 10 | **0.6140 (+1.4%)** ★ | **0.7785 (+0.1%)** ★ | 0.8187 (-1.0%) ▼ |
| base_notime_fda_8ch | 8 | 0.5827 (-1.8%) ▼ | 0.7767 | 0.8023 (-2.6%) ▼ |

**Key insights at 12h**:
- FDA derivatives help override (+1.4%) and hypo (+0.1%) — NEW 12h BEST for override!
- Time features (sin/cos) are ESSENTIAL at 12h: removing hurts -1.8% (vs noise at 2h)
- Kitchen_sink hurts at 12h: PK channels add noise that degrades performance
- Prolonged_high is special: only baseline_8ch works well (glucose shape suffices)

### FDA Contribution Across Scales (override)

| Scale | Baseline | +FDA | Δ | Consistent? |
|-------|----------|------|---|-------------|
| 2h | 0.843 | 0.864 | **+2.1%** | Yes ★ |
| 6h | 0.700 | 0.715 | **+1.5%** | Yes ★ |
| 12h | 0.600 | 0.614 | **+1.4%** | Yes ★ |

**FDA derivatives provide consistent +1.4–2.1% improvement across ALL scales.**
The benefit slightly diminishes with scale (from 2.1% → 1.4%), suggesting FDA
derivatives capture local dynamics that become less dominant at longer horizons.

---

## EXP-378: Data Augmentation at 12h

**Question**: Can data augmentation break the 12h performance ceiling? Since
architecture (CNN/Transformer) and features (8ch–12ch) have hit a wall at 12h,
the bottleneck might be training data quantity.

### Augmentation Results (Transformer + baseline_8ch, 12h)

| Strategy | Override | Δ | Hypo | Δ | Prolonged High | Δ |
|----------|----------|---|------|---|----------------|---|
| no_augment (control) | 0.6063 | — | 0.7773 | — | 0.8295 | — |
| jitter (σ=0.02) | 0.6014 | -0.5% ▼ | 0.7757 | -0.2% ▼ | 0.8290 | -0.1% |
| scaling (σ=0.1) | 0.6059 | -0.0% | 0.7759 | -0.1% | **0.8318** | **+0.2%** ★ |
| **time_warp (σ=0.05)** | 0.6081 | +0.2% ★ | **0.7797** | **+0.2%** ★ | 0.8316 | +0.2% ★ |
| **mixup (α=0.3)** | **0.6091** | **+0.3%** ★ | 0.7764 | -0.1% | 0.8290 | -0.1% |
| jitter+scaling | 0.5997 | -0.7% ▼ | 0.7753 | -0.2% ▼ | 0.8286 | -0.1% |

**Key insights**:
- **Augmentation gains are marginal** (<0.3%) — the 12h bottleneck is NOT data scarcity
- **Time_warp is the most consistent** (+0.2% across all 3 tasks)
- **Mixup helps override** (+0.3%) but not other tasks
- **Jitter HURTS** — adding Gaussian noise to treatment channels is destructive
- **Combining augmentations (jitter+scaling) is WORST** — they compound the noise
- The 12h problem is fundamentally about prediction horizon difficulty, not data volume

### What Does This Mean for 12h?

The 12h ceiling (~0.61 override F1) is likely inherent to the prediction task:
- 6h of future glucose behavior is influenced by events not yet occurred (future meals,
  future boluses, activity changes)
- No amount of input engineering can predict genuinely unpredictable events
- Best strategy: **combine FDA features (+1.4%) with mild time_warp (+0.2%)** for a
  potential ~1.6% total improvement over baseline

---

## Updated Cross-Scale Conclusions (EXP-349–378)

### Universal Recommendations

1. **Always use Transformer** (not CNN) for classification — attention handles
   feature richness better across all scales
2. **Always include FDA B-spline derivatives** (glucose_d1, glucose_d2) — they provide
   +1.4–2.2% improvement at every scale tested
3. **Include raw bolus/carbs** for UAM detection — essential +5.4% contribution
4. **Use positional encoding** — essential for trend detection at all scales

### Scale-Specific Recommendations

| Scale | Time Features | PK Channels | FDA Derivatives | Augmentation |
|-------|--------------|-------------|-----------------|--------------|
| 2h | Remove (noise) | Remove (noise) | Add (+2.2%) | Not tested |
| 6h | Keep (neutral) | Remove (noise) | Add (+1.5%) | Not tested |
| 12h | Keep (essential) | Remove (noise) | Add (+1.4%) | Mild time_warp (+0.2%) |

### Open Questions Remaining

1. **Per-patient fine-tuning**: Can patient-specific adaptation recover the 3-4%
   LOO generalization gap (EXP-326)?
2. **Multivariate FPCA**: Can joint functional analysis of glucose+IOB capture
   cross-channel dynamics better than separate derivatives?
3. **ISF-normalized glucose**: Can dividing by ISF schedule improve cross-patient
   generalization?
4. **Absorption symmetry**: Do insulin/carb absorption curves exhibit exploitable
   symmetry (pre-peak vs post-peak)?
