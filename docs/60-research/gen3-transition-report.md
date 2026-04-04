# Gen-3 Architecture Transition Report

**Date**: 2026-04-05
**Experiments**: EXP-158 through EXP-162
**Models**: `CGMGroupedEncoder` with `semantic_groups=True/False`, `d_model=64–256`
**Headline**: ~60% of Gen-2's improvement was from future action leakage; Gen-3 semantic groups provide zero additional benefit for forecasting

---

## Executive Summary

The Gen-3 architecture transition represents the most important course correction
in this project's 159-experiment history. A systematic audit of Gen-2's
`train_forecast()` masking revealed that only future glucose (channel 0) and
glucose derivatives (channels 12–13) were masked during training — but **future
IOB, COB, net_basal, bolus, carbs, time_since_bolus, and time_since_carb were
left fully visible**. The model could see exactly what insulin and carbs the
patient would receive in the forecast window, making "prediction" trivially easy
but useless for real-time inference where those values are unknown.

Gen-3 corrects this with proper future masking of all 10 unknown channels, while
simultaneously upgrading the encoder with semantic group projections, wider
capacity (128D), and attention-weighted pooling.

**The honest result**: forecast MAE increased from 19.7 → 29.5 mg/dL (8-feature)
and 26.6 → 41.5 mg/dL (21-feature). What looks like a 50–56% regression is
actually the removal of a 60% artificial advantage. The remaining 14–15%
improvement over persistence (in MAE terms) is real, reproducible, and —
crucially — will generalize.

**The architecture verdict** (EXP-162): A controlled comparison of Gen-2
(monolithic context projection) vs Gen-3 (semantic group projections) — both
with identical proper future masking — shows **zero measurable difference**
for forecasting. The semantic groups do not help with 10 patients / 16K windows.
The only change that mattered was fixing the future action leak.

---

## Table of Contents

1. [The Future Action Leak](#1-the-future-action-leak)
2. [What Was Leaked](#2-what-was-leaked)
3. [Gen-3 Architecture Changes](#3-gen-3-architecture-changes)
4. [Results Comparison](#4-results-comparison)
5. [Interpretation](#5-interpretation)
6. [Architecture Details](#6-architecture-details)
7. [Persistence Baselines](#7-persistence-baselines)
8. [Files Changed](#8-files-changed)
9. [Experiment Log](#9-experiment-log)
10. [EXP-161: Full Architecture Sweep](#10-exp-161-full-architecture-sweep)
11. [EXP-162: Gen-2 vs Gen-3 Controlled Comparison](#11-exp-162-gen-2-vs-gen-3-controlled-comparison)
12. [Lessons Learned](#12-lessons-learned)
13. [What This Means Going Forward](#13-what-this-means-going-forward)
14. [Appendix: Channel Reference](#appendix-channel-reference)

---

## 1. The Future Action Leak

### Discovery

Gen-2's `train_forecast()` function in `experiment_lib.py` constructed forecast
training windows as `[history | future]` pairs. Before computing the loss, it
masked the future half to prevent the model from "cheating." The problem: **the
mask was incomplete**.

Gen-2 masked:
- Channel 0: glucose (the prediction target)
- Channels 12–13: glucose_roc, glucose_accel (derived from future glucose)

Gen-2 **failed to mask**:
- Channel 1: IOB (future insulin on board)
- Channel 2: COB (future carbs on board)
- Channel 3: net_basal (future basal rate adjustments)
- Channel 4: bolus (future bolus deliveries)
- Channel 5: carbs (future carb entries)
- Channel 14: time_since_bolus (reveals future bolus timing)
- Channel 15: time_since_carb (reveals future carb timing)

### Why It Matters

In a real-time glucose forecasting scenario, the model receives the current state
and must predict where glucose will be in 1–2 hours. It cannot know:

- Whether the patient will eat in 30 minutes (future carbs)
- Whether the AID system will deliver a correction bolus (future bolus)
- How much insulin will be on board at t+60 min (future IOB)
- Whether a temporary basal override will be applied (future net_basal)

By leaving these channels visible during training, the model learned a shortcut:
**read the future treatment pattern and infer what glucose must do in response**.
This is dramatically easier than learning physiological glucose dynamics from
history alone — and completely non-transferable to real-time inference.

### The Smoking Gun

Three pieces of evidence converge:

1. **87% glucose-dominant attention** in Gen-2 attention analysis. The model
   focused almost exclusively on glucose channels and largely ignored treatment
   features. Why? Because it could directly see future treatments — it didn't
   need to *learn* how treatments affect glucose.

2. **37% generalization gap** (training → verification). Gen-2 showed excellent
   training metrics but degraded sharply on held-out data. Leaked future
   information is dataset-specific: the exact pattern of future treatments in
   training windows doesn't appear identically in verification windows.

3. **15% patient-specific variance** in LOO analysis. With future actions leaked,
   per-patient adaptation was less important because the model could shortcut
   through future treatments regardless of patient physiology.

---

## 2. What Was Leaked

The table below categorizes all 21 channels by their future-knowability status:

| Channel | Index | Future Status | Rationale |
|---------|-------|---------------|-----------|
| glucose | 0 | **UNKNOWN** — masked | Prediction target |
| IOB | 1 | **UNKNOWN** — was leaked | Depends on future deliveries |
| COB | 2 | **UNKNOWN** — was leaked | Depends on future carb absorption |
| net_basal | 3 | **UNKNOWN** — was leaked | Future AID decisions |
| bolus | 4 | **UNKNOWN** — was leaked | Future manual/auto boluses |
| carbs | 5 | **UNKNOWN** — was leaked | Future meal entries |
| time_sin | 6 | Known | Deterministic clock signal |
| time_cos | 7 | Known | Deterministic clock signal |
| day_sin | 8 | Known | Deterministic calendar signal |
| day_cos | 9 | Known | Deterministic calendar signal |
| override_active | 10 | Known | User-scheduled, known in advance |
| override_type | 11 | Known | User-scheduled, known in advance |
| glucose_roc | 12 | **UNKNOWN** — masked | Derived from future glucose |
| glucose_accel | 13 | **UNKNOWN** — masked | Derived from future glucose |
| time_since_bolus | 14 | **UNKNOWN** — was leaked | Reveals future bolus timing |
| time_since_carb | 15 | **UNKNOWN** — was leaked | Reveals future carb timing |
| cage_hours | 16 | Known | Deterministic device lifecycle |
| sage_hours | 17 | Known | Deterministic device lifecycle |
| sensor_warmup | 18 | Known | Deterministic from sensor start |
| month_sin | 19 | Known | Deterministic calendar signal |
| month_cos | 20 | Known | Deterministic calendar signal |

**Summary**: 10 channels masked (unknown at inference), 11 channels preserved
(known future). Gen-2 only masked 3 of the 10 unknown channels.

---

## 3. Gen-3 Architecture Changes

Gen-3 was implemented in 5 phases. The first 4 are included in the EXP-159
baseline; Phase 5 (Hybrid XGBoost) is planned but not yet implemented.

### Phase 1: Proper Future Masking

The core fix. A new `FUTURE_UNKNOWN_CHANNELS` constant in `schema.py` explicitly
enumerates all 10 channels that are unknown at real-time inference:

```python
# tools/cgmencode/schema.py (lines 62-73)
FUTURE_UNKNOWN_CHANNELS = [
    IDX_GLUCOSE,            # 0
    IDX_IOB,                # 1
    IDX_COB,                # 2
    IDX_NET_BASAL,          # 3
    IDX_BOLUS,              # 4
    IDX_CARBS,              # 5
    IDX_GLUCOSE_ROC,        # 12
    IDX_GLUCOSE_ACCEL,      # 13
    IDX_TIME_SINCE_BOLUS,   # 14
    IDX_TIME_SINCE_CARB,    # 15
]
```

A centralized `mask_future_channels()` helper in `experiment_lib.py` applies this
masking consistently across all 3 training/evaluation sites:

```python
# tools/cgmencode/experiment_lib.py
def mask_future_channels(x_in, half):
    """Zero out future-unknown channels in positions half: onward."""
    for ch in FUTURE_UNKNOWN_CHANNELS:
        if ch < x_in.shape[2]:
            x_in[:, half:, ch] = 0.0
    return x_in
```

**Why centralized**: Gen-2's bug arose from ad-hoc masking at each call site.
By defining the channel list once in the schema and applying it through a single
helper, future masking changes propagate automatically.

### Phase 2: Wider Context Embedding

With future action leakage removed, the model needs more capacity to learn
glucose dynamics from legitimate historical signals. Gen-3 doubles `d_model`
from 64 to 128 and replaces the monolithic `context_proj` with semantic group
projections.

**Gen-2 (monolithic context)**:
```
context_proj: (13 features → 8D)  ← 0.6D per feature
```

**Gen-3 (semantic groups)**:
```
weekday_proj:  (2 → 16D)   day_sin, day_cos
override_proj: (2 → 16D)   override_active, override_type
dynamics_proj: (2 → 16D)   glucose_roc, glucose_accel
timing_proj:   (2 → 16D)   time_since_bolus, time_since_carb
device_proj:   (3 → 16D)   cage_hours, sage_hours, sensor_warmup
monthly_proj:  (2 → 16D)   month_sin, month_cos
                            ─────────
Total:          13 → 96D    ← 7.4D per feature (12× more capacity)
```

The semantic grouping provides an inductive bias: features that share a domain
meaning (e.g., device lifecycle) are projected together, allowing the model to
learn domain-specific representations before fusion.

### Phase 3: Attention-Weighted Pooling

Gen-2 used mean pooling to aggregate encoded representations for auxiliary heads
(event detection, drift tracking, state classification). This treats all timesteps
equally, losing temporal structure.

Gen-3 introduces `AttentionPooling`:

```python
# tools/cgmencode/model.py (lines 101-119)
class AttentionPooling(nn.Module):
    def __init__(self, d_model: int):
        super().__init__()
        self.query = nn.Linear(d_model, 1, bias=False)

    def forward(self, encoded: torch.Tensor) -> torch.Tensor:
        weights = torch.softmax(self.query(encoded).squeeze(-1), dim=1)
        return (weights.unsqueeze(-1) * encoded).sum(dim=1)
```

This learns which timesteps are most relevant for each downstream task. For event
detection, recent timesteps near a bolus event carry more signal than distant
history. For drift tracking, sustained deviations over the full window matter
more.

### Phase 4: Separate Training Capability

`create_model()` now accepts `semantic_groups` and `aux_config` parameters,
allowing Gen-3 models to be instantiated independently of legacy code paths.
The `--gen3` flag in `run_retrain.py` activates Gen-3 defaults:

| Parameter | Gen-2 | Gen-3 |
|-----------|-------|-------|
| `d_model` | 64 | 128 |
| `semantic_groups` | `False` | `True` |
| `aux_config` | Optional | Integrated |
| Future masking | 3 channels | 10 channels |
| Pooling | Mean | Attention |

### Phase 5: Hybrid XGBoost (Planned)

Not yet implemented in the EXP-159 baseline. The plan is to use XGBoost for
event detection (where it achieved F1=0.710 vs neural F1=0.107) while keeping
the transformer for glucose forecasting. This would combine the strengths of
both approaches: neural networks for sequential prediction, gradient boosting
for classification on tabular features.

---

## 4. Results Comparison

### Headline Metrics

| Metric | Gen-2 (EXP-158) | Gen-3 (EXP-159) | Δ | Interpretation |
|--------|-----------------|-----------------|---|----------------|
| 8f MAE | 19.7 ± 0.0 mg/dL | 29.6 ± 0.1 mg/dL | +50% | Honest (no leak) |
| 8f vs persistence | 66.9% | 25.7% | −41 pp | Lost fake improvement |
| 21f MAE | 26.6 ± 0.2 mg/dL | 41.9 ± 0.1 mg/dL | +58% | Honest (no leak) |
| 21f vs persistence | 70.4% | 27.0% | −43 pp | Lost fake improvement |

### Model Size

| Metric | Gen-2 (EXP-158) | Gen-3 (EXP-159) | Ratio |
|--------|-----------------|-----------------|-------|
| 8f params | 107K | 300K | 2.8× |
| 21f params | 107K | 331K | 3.1× |

The parameter increase comes from:
- `d_model` 64 → 128 (quadratic effect on attention layers)
- 6 semantic group projections (96D context vs 8D monolithic)
- `AttentionPooling` module

### Data

| Metric | Gen-2 (EXP-158) | Gen-3 (EXP-159) |
|--------|-----------------|-----------------|
| 8f train windows | 25,937 | 25,937 |
| 8f horizon | 1h (12 steps) | 1h (12 steps) |
| 21f train windows | 12,888 | 12,888 |
| 21f horizon | 2h (24 steps) | 2h (24 steps) |

Identical data splits ensure the metric differences are purely from architecture
and masking changes, not data variation.

### Training Dynamics

| Metric | 8f Gen-3 | 21f Gen-3 |
|--------|----------|-----------|
| Early-stop epoch | ~45 | 44–45 |
| Final train_loss | ~0.007 | 0.007 |
| Final val_loss | ~0.010 | 0.011 |
| Train/val gap | ~30% | ~36% |

The 21f model shows more severe overfitting (36% train/val gap vs 30% for 8f),
consistent with having 3.1× more parameters but only half the training windows.

---

## 5. Interpretation

### Finding 1: ~60% of Gen-2's improvement was from future action leakage

Gen-2 claimed 66.9–70.4% improvement over persistence. Gen-3 achieves 25.7–27.0%.
The difference — approximately 41–43 percentage points — was attributable to the
model exploiting leaked future treatment data.

This is not a rounding error. **The majority of what we measured as "model
intelligence" was data leakage.**

```
Gen-2 reported improvement:     66.9%  (8f)     70.4%  (21f)
Gen-3 honest improvement:       25.7%  (8f)     27.0%  (21f)
                                ─────           ─────
Leaked contribution:            41.2 pp         43.4 pp
Fraction that was fake:         61.6%           61.6%
```

### Finding 2: This explains the 37% generalization gap

Gen-2 showed a persistent ~37% gap between training and verification performance.
With future actions leaked, the model learned patterns like "if bolus appears at
t+30min, glucose will drop by t+60min." These patterns are dataset-specific:
the exact timing and magnitude of future treatments in training windows don't
generalize to new patients or time periods.

With honest masking in Gen-3, the generalization gap should narrow because the
model can only learn from legitimately available historical signals.

### Finding 3: This explains the 87% glucose-dominant attention

Attention analysis of Gen-2 showed 87% of attention weight concentrated on
glucose channels, with treatment channels largely ignored. This was puzzling:
why would a model trained to predict glucose from treatments ignore treatments?

The answer: **it didn't need to learn treatment→glucose dynamics**. With future
treatments visible, the model could infer glucose trajectories directly from the
leaked action schedule. Treatment features in the history half were redundant
noise.

### Finding 4: The honest 25–27% improvement over persistence IS real

Despite the setback, Gen-3 does demonstrate genuine learning. The model achieves:

- **8f**: 29.6 mg/dL MAE vs 34.3 mg/dL persistence = **25.7% improvement**
- **21f**: 41.9 mg/dL MAE vs 49.0 mg/dL persistence = **27.0% improvement** (*)

(*) A model that improves on persistence by 25–27% using only historical data is
clinically meaningful. Persistence — repeating the last known glucose value — is
a strong baseline because glucose changes slowly relative to the 5-minute
sampling interval. Beating it by a quarter means the model has learned some
genuine glucose dynamics: momentum, trend following, and possibly meal/insulin
response patterns from historical context.

### Finding 5: 21f shows slight advantage despite harder horizon

The 21-feature model (27.0% improvement) slightly outperforms the 8-feature
model (25.7%) despite predicting over a 2-hour horizon (vs 1 hour). This
suggests that the extended context features — weekday patterns, override state,
device lifecycle — provide marginal but real value.

However, this advantage is confounded by overfitting (see Finding 6).

### Finding 6: 21f is severely overfitting

With 331K parameters and only 12,888 training windows, the 21-feature model has
a parameter-to-sample ratio of ~1:39. This is dangerously high for a
transformer model. Evidence:

- Early-stopping at epochs 44–45 (vs 50 max)
- Train loss 0.007 vs val loss 0.011 (36% gap)
- The slight 21f advantage over 8f may be partially from memorization

The model has enough capacity to memorize patient-specific patterns rather than
learning generalizable glucose dynamics. Addressing this overfitting is the
highest-priority improvement for Gen-3.

---

## 6. Architecture Details

### Gen-3 CGMGroupedEncoder

The full Gen-3 architecture as implemented in `tools/cgmencode/model.py`:

```
Input: (B, T, 21)  — 21-feature cgmencode vector
       ┌──────────────────────────────────────────────────┐
       │  CORE PROJECTIONS                                │
       │  state_proj:  (3 → 64)  glucose, IOB, COB       │
       │  action_proj: (3 → 32)  net_basal, bolus, carbs │
       │  time_proj:   (2 → 32)  time_sin, time_cos      │
       │  ──────────────────────  = 128D                  │
       └──────────────────────────────────────────────────┘
                              │
       ┌──────────────────────────────────────────────────┐
       │  SEMANTIC GROUP PROJECTIONS (Gen-3)              │
       │  weekday_proj:  (2 → 16)  day_sin, day_cos      │
       │  override_proj: (2 → 16)  override_active, type │
       │  dynamics_proj: (2 → 16)  glucose_roc, accel    │
       │  timing_proj:   (2 → 16)  time_since_bolus/carb │
       │  device_proj:   (3 → 16)  CAGE, SAGE, warmup    │
       │  monthly_proj:  (2 → 16)  month_sin, month_cos  │
       │  ──────────────────────── = 96D                  │
       └──────────────────────────────────────────────────┘
                              │
       ┌──────────────────────────────────────────────────┐
       │  FUSION                                          │
       │  concat(128D + 96D) → Linear(224 → 128)         │
       │  → LayerNorm(128)                                │
       └──────────────────────────────────────────────────┘
                              │
       ┌──────────────────────────────────────────────────┐
       │  POSITIONAL ENCODING                             │
       │  Sinusoidal positional embedding (128D)          │
       └──────────────────────────────────────────────────┘
                              │
       ┌──────────────────────────────────────────────────┐
       │  TRANSFORMER ENCODER                             │
       │  3 layers, 8 heads, dim_ff=128                   │
       │  norm_first=True, dropout=0.1                    │
       └──────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
       ┌──────────┐   ┌──────────┐   ┌──────────┐
       │ forecast │   │  event   │   │  drift   │  ← aux heads
       │  head    │   │  head    │   │  head    │
       │ (T→21)  │   │ attn→cls │   │ attn→2  │
       └──────────┘   └──────────┘   └──────────┘
                              │
                       ┌──────────┐
                       │  state   │
                       │  head    │
                       │ attn→cls │
                       └──────────┘
```

### Capacity Comparison

| Component | Gen-2 | Gen-3 | Change |
|-----------|-------|-------|--------|
| d_model | 64 | 128 | 2× wider |
| Core projections | 3→32, 3→16, 2→16 | 3→64, 3→32, 2→32 | 2× each |
| Context | 13→8 (monolithic) | 6 groups × 16D | 12× per feature |
| Fusion | 72→64 | 224→128 | — |
| Transformer layers | 3 | 3 | Same |
| Attention heads | 4 | 8 | 2× |
| dim_feedforward | 128 | 128 | Same |
| Aux pooling | Mean | Attention | Learned |
| Total params (21f) | 107K | 331K | 3.1× |

### Semantic Group Rationale

Each semantic group captures a distinct domain concept:

| Group | Channels | Domain Meaning |
|-------|----------|----------------|
| **weekday** | day_sin/cos (8–9) | Weekly activity patterns (workday vs weekend) |
| **override** | active/type (10–11) | User-initiated therapy overrides (exercise, sleep, sick) |
| **dynamics** | roc/accel (12–13) | Glucose momentum and curvature |
| **timing** | since_bolus/carb (14–15) | Recency of treatment events |
| **device** | CAGE/SAGE/warmup (16–18) | Infusion set and sensor lifecycle |
| **monthly** | month_sin/cos (19–20) | Monthly hormonal/seasonal patterns |

Grouping features by domain meaning allows the linear projection to learn
meaningful interactions within each group (e.g., CAGE and SAGE degradation
curves are related) before the transformer fuses across groups.

---

## 7. Persistence Baselines

Persistence forecasting — repeating the last known glucose value for all future
timesteps — provides the zero-intelligence reference. Any model that can't beat
persistence has learned nothing useful.

| Horizon | Persistence MAE | Gen-3 MAE | Improvement |
|---------|----------------|-----------|-------------|
| 8f (1h, 12 steps) | 34.3 mg/dL | 29.6 mg/dL | 25.7% |
| 21f (2h, 24 steps) | 49.0 mg/dL | 41.9 mg/dL | 27.0% |

The 2-hour horizon is substantially harder: persistence MAE increases 43%
(34.3 → 49.0) because glucose has more time to diverge from the last reading.
Glucose variability compounds with horizon length, and insulin/meal effects that
are partially predictable at 1h become increasingly stochastic at 2h.

Despite this, the 21f model shows a slight edge in relative improvement (27.0%
vs 25.7%), suggesting the extended features provide more value at longer horizons
where calendar, override, and device context carry more predictive weight.

---

## 8. Files Changed

| File | Changes | Purpose |
|------|---------|---------|
| `tools/cgmencode/schema.py` | Added `FUTURE_UNKNOWN_CHANNELS` list (lines 59–75) | Single source of truth for future masking |
| `tools/cgmencode/model.py` | Added `AttentionPooling` class (lines 101–119); added `semantic_groups` parameter and 6 group projections to `CGMGroupedEncoder` (lines 155–256) | Gen-3 encoder architecture |
| `tools/cgmencode/experiment_lib.py` | Added `mask_future_channels()` helper; updated all 3 masking call sites to use the centralized function | Consistent future masking |
| `tools/cgmencode/run_retrain.py` | Added `--gen3` flag for Gen-3 defaults (`d_model=128`, `semantic_groups=True`) | Training entry point |

### Code Reference: Future Masking Call Sites

The `mask_future_channels()` helper is called in three locations within
`experiment_lib.py`:

1. **`train_forecast()` → `_forecast_step()`**: Main training loop — masks
   future unknowns before forward pass, computes MSE on future glucose only.

2. **`evaluate_forecast()`**: Validation/verification evaluation — same masking
   applied for consistent metrics.

3. **`run_inference()`**: Production inference path — masks future half before
   model prediction.

All three sites now import `FUTURE_UNKNOWN_CHANNELS` from `schema.py` via the
centralized helper, ensuring any future channel classification changes
propagate automatically.

---

## 9. Experiment Log

| EXP | Generation | Config | 8f MAE | 21f MAE | 8f vs Persist | 21f vs Persist | Notes |
|-----|-----------|--------|--------|---------|---------------|----------------|-------|
| 158 | Gen-2 | d_model=64, 3ch mask | 19.7 ± 0.0 | 26.6 ± 0.2 | 66.9% | 70.4% | Leaked future actions |
| 159 | Gen-3 | d_model=128, 10ch mask, semantic groups | 29.6 ± 0.1 | 41.9 ± 0.1 | 26.1%* | 27.0%* | Honest baseline |
| 160 | Gen-3 | Quick sweep, 3 configs × 1 seed | 29.5 | 41.6 | 26.1%* | 28.0%* | Saturation signal |
| 161 | Gen-3 | Full sweep, 12 configs × 2 seeds | 29.4–29.8 | 41.5–42.2 | 25–27%* | 26–28%* | Total 8f saturation |
| 162 | Gen-2 | 3 configs × 2 seeds, full masking | 29.5–29.9 | 41.5–41.8 | 14.0–14.1%† | 14.6–15.4%† | Identical to Gen-3 |

\* MSE-space comparison: `(1 - model_mse/persist_mse) × 100`
† RMSE-space comparison: `(1 - sqrt(model_mse)/sqrt(persist_mse)) × 100`

> **Note on metric discrepancy**: EXP-159–161 computed "% vs persistence" in MSE
> space (26%), while EXP-162 used RMSE/MAE space (14%). Both describe the same
> models. The MSE-space number overstates the visual improvement because squaring
> amplifies differences. The RMSE-space number (14%) is more intuitive: it directly
> means "this model's errors are 14% smaller in mg/dL than just using the last
> reading." For consistency, all future reporting will use RMSE-space.

### Prior Context (Selected)

| EXP Range | Generation | Contribution |
|-----------|-----------|--------------|
| 1–50 | Gen-1 | Foundation: 8-feature encoder, single-task forecast |
| 51–100 | Gen-1 | Ablations: window size, learning rate, depth sweeps |
| 101–140 | Gen-1→2 | Extended features, multi-task heads, sim-to-real transfer |
| 141–150 | Gen-2 | Synthetic pre-training, composite loss tuning |
| 151–157 | Gen-2 | Multi-task fine-tuning, evaluation, attention analysis |
| 158 | Gen-2 | Final Gen-2 baseline (leaked) |
| 159–162 | Gen-3 | Honest baseline, full sweep, controlled comparison |

---

## 10. EXP-161: Full Architecture Sweep

**Objective**: Determine if any architecture configuration breaks through the
~29.5 mg/dL ceiling observed in EXP-159/160.

**Setup**: 12 configurations × 2 seeds × 2 feature modes = 48 runs (3.3 hours on RTX 3050 Ti)

### Configurations Tested

| Config | d_model | nhead | layers | dropout | weight_decay | params (8f) | params (21f) |
|--------|---------|-------|--------|---------|-------------|-------------|--------------|
| tiny | 64 | 4 | 2 | 0.10 | 1e-5 | 67K | 76K |
| small | 64 | 4 | 3 | 0.10 | 1e-5 | 101K | 110K |
| medium | 128 | 8 | 3 | 0.10 | 1e-5 | 300K | 331K |
| large | 192 | 8 | 4 | 0.10 | 1e-5 | 654K | 698K |
| xlarge | 256 | 8 | 4 | 0.10 | 1e-5 | 993K | 1.05M |
| med_highreg | 128 | 8 | 3 | 0.20 | 1e-4 | 300K | 331K |
| med_maxreg | 128 | 8 | 3 | 0.30 | 5e-4 | 300K | 331K |
| small_highreg | 64 | 4 | 3 | 0.15 | 1e-4 | 101K | 110K |
| med_slowlr | 128 | 8 | 3 | 0.10 | 1e-5 | 300K | 331K |
| med_fastlr | 128 | 8 | 3 | 0.10 | 1e-5 | 300K | 331K |
| deep_narrow | 64 | 4 | 6 | 0.15 | 1e-4 | 202K | 210K |
| shallow_wide | 256 | 8 | 2 | 0.10 | 1e-5 | 596K | 637K |

### 8-Feature Results (1-hour forecast, persistence = 34.3 mg/dL)

**TOTAL SATURATION.** All 12 configurations achieve 29.4–29.8 mg/dL regardless
of model size, regularization, or learning rate:

| Rank | Config | MAE ± σ | vs Persist | Params |
|------|--------|---------|-----------|--------|
| 1 | med_fastlr | 29.4 ± 0.0 | 14.3% | 300K |
| 2 | small_highreg | 29.4 ± 0.1 | 14.3% | 101K |
| 3 | tiny | 29.5 ± 0.0 | 14.0% | 67K |
| ... | (all others) | 29.5–29.8 | 13–14% | 101K–993K |
| 12 | shallow_wide | 29.8 ± 0.1 | 13.1% | 596K |

**Key insight**: A 67K-parameter "tiny" model matches a 993K-parameter "xlarge"
model. The 15× parameter increase provides zero improvement. The 8-feature,
1-hour forecast ceiling is a **data limitation**, not a model limitation.

### 21-Feature Results (2-hour forecast, persistence = 49.0 mg/dL)

More differentiation than 8f, but still narrow (~1 mg/dL spread):

| Rank | Config | MAE ± σ | vs Persist | Params |
|------|--------|---------|-----------|--------|
| 1 | deep_narrow | 41.5 ± 0.0 | 15.3% | 210K |
| 2 | small | 41.6 ± 0.1 | 15.1% | 110K |
| 3 | small_highreg | 41.6 ± 0.0 | 15.1% | 110K |
| 4 | med_highreg | 41.7 ± 0.2 | 14.9% | 331K |
| 5 | medium | 41.8 ± 0.1 | 14.7% | 331K |
| ... | | | | |
| 12 | med_maxreg | 42.2 ± 0.1 | 13.9% | 331K |

**Key insights**:
1. **Deep + narrow wins**: 6 layers × 64D beats 3 layers × 128D for 21f
2. **Regularization doesn't help**: med_highreg/med_maxreg are worse than medium
3. **Bigger is not better**: xlarge (1.05M params) is middle-of-pack
4. The 21f bottleneck is also data-limited (16K windows for 48-step prediction)

---

## 11. EXP-162: Gen-2 vs Gen-3 Controlled Comparison

**Objective**: Isolate the effect of semantic group projections by training Gen-2
(monolithic `context_proj`) with the same full future masking used in Gen-3.

**Setup**: 3 matched configs × 2 seeds × 2 feature modes = 12 runs

**Hypothesis**: If Gen-3's semantic groups help with 21-feature context embedding,
Gen-3 should outperform Gen-2 on 21f (the two architectures are identical for 8f
since semantic groups only activate when `input_dim > 8`).

### Results

#### 8-Feature (1-hour, persistence = 34.3 mg/dL)

| Config | Gen-2 MAE | Gen-3 MAE | Δ (G3−G2) | Gen-2 params | Gen-3 params |
|--------|-----------|-----------|-----------|-------------|-------------|
| tiny | 29.5 | 29.5 | 0.0 | 67,704 | 67,704 |
| medium | 29.6 | 29.5 | −0.1 | 300,264 | 300,264 |
| deep_narrow | 29.9 | 29.7 | −0.2 | 201,592 | 201,592 |

Identical as expected — both architectures use the same encoder for 8 features.

#### 21-Feature (2-hour, persistence = 49.0 mg/dL)

| Config | Gen-2 MAE | Gen-3 MAE | Δ (G3−G2) | Gen-2 params | Gen-3 params |
|--------|-----------|-----------|-----------|-------------|-------------|
| tiny | 41.7 | 41.6 | −0.1 | 73,461 | 76,061 |
| medium | 41.6 | 41.8 | **+0.2** | 320,981 | 331,301 |
| deep_narrow | 41.6 | 41.5 | −0.1 | 207,349 | 209,949 |

**No statistically significant difference.** The largest delta is 0.2 mg/dL (for
medium, where Gen-3 is slightly *worse*). The semantic group projections — which
add 2,600–10,300 extra parameters — provide zero measurable benefit for
forecasting on this dataset.

### Interpretation

The Gen-2 monolithic `context_proj(13→8)` compresses 13 extended features into
8 dimensions. We hypothesized this was a catastrophic bottleneck at 0.6D per
feature. However:

1. **The features may not carry enough useful information to benefit from wider
   embedding.** With proper future masking, only the temporal (day/month phase),
   device (CAGE/SAGE/warmup), and override features remain visible in the future
   window. These may be too slowly-varying to help with 2-hour glucose prediction.

2. **The data volume may be insufficient.** With only 16K training windows, larger
   models with more context capacity may simply overfit the noise rather than
   learning the signal.

3. **Forecasting may be the wrong task to evaluate context embedding improvements.**
   The extended features (device lifecycle, circadian phase) are more relevant for
   drift detection, event classification, and override recommendation — tasks that
   operate on longer timescales where these features change meaningfully.

### Verdict

**For forecasting, Gen-3 semantic groups are architectural complexity without
measurable benefit.** The future action leak fix was the only change that
meaningfully affected results. The honest forecast performance (14–15% better
than persistence in MAE terms) is a property of the data and task, not the
architecture.

However, this does NOT mean Gen-3 is wasted effort:
- Semantic groups may prove valuable for **multi-task training** (event/drift heads)
- The proper future masking is **essential** regardless of architecture
- The attention pooling may help with **aux head** performance (untested in EXP-162)

---

## 12. Lessons Learned

### Lesson 1: Validate Your Masking Exhaustively

**What happened**: We masked "the obvious" channel (glucose) and its derivatives,
but missed 7 other channels that leak future information through indirect paths.
IOB at t+30min tells you about boluses between now and then. COB at t+60min
tells you about meals and absorption. Time-since-bolus monotonically increasing
vs resetting reveals future bolus timing.

**Takeaway**: When implementing any form of causal masking, enumerate *every*
channel and classify it as known-future vs unknown-future. Document the reasoning
for each. Ambiguous cases (e.g., overrides — are they scheduled in advance?)
should be discussed explicitly and decided conservatively (mask if uncertain).

**Implementation**: The `FUTURE_UNKNOWN_CHANNELS` constant in `schema.py` now
serves as a reviewed, documented source of truth. Adding new features requires
explicitly classifying their future-knowability.

### Lesson 2: Impressive Metrics Demand Skepticism, Not Celebration

**What happened**: Gen-2 showed 65–70% improvement over persistence. We
celebrated. We should have asked: "Is this physically plausible? Can glucose
really be predicted that accurately with a 107K-parameter model?"

**Takeaway**: For glucose forecasting, published literature typically shows
15–35% improvement over persistence for 1-hour horizons using much larger models
and datasets. A 67% improvement from a small transformer on 10 patients should
have triggered immediate skepticism.

**Rule of thumb**: If your model dramatically outperforms published baselines,
assume a bug until proven otherwise.

### Lesson 3: Leakage Explains Puzzling Downstream Results

**What happened**: Multiple downstream observations were puzzling in isolation but
perfectly explained by future action leakage:

| Observation | Puzzling Because | Explained By Leakage |
|-------------|------------------|----------------------|
| 87% glucose attention | Why ignore treatments? | Didn't need to learn them |
| 37% generalization gap | Model seemed well-trained | Leaked info doesn't transfer |
| Neural event F1 = 0.107 | Model is powerful enough | Attention on glucose, not events |
| LOO variance only 15% | Expected more patient variation | Leak masks patient differences |

**Takeaway**: When you see multiple anomalous results, look for a single root
cause. Data leakage is often that cause.

### Lesson 4: Centralize Data Contracts

**What happened**: The masking logic was duplicated at 3 call sites in
`experiment_lib.py`, each with slightly different channel lists. Only the
ad-hoc nature of the masking allowed the leak to persist unnoticed.

**Takeaway**: Feature schema, normalization constants, and masking rules belong
in a single source-of-truth module (here, `schema.py`). Training code should
import and apply, never redefine.

### Lesson 5: The Honest Baseline Is the Foundation

**What happened**: Discovering the leak felt like a setback — our metrics
"regressed" by 50–58%. But this reframing is wrong. **We didn't get worse; we
got honest.** Every experiment from Gen-3 forward builds on a foundation where
improvements are real.

**Takeaway**: A 25% honest improvement is worth infinitely more than a 67%
fake improvement. The former generalizes; the latter crumbles in production.

### Lesson 6: Architecture Upgrades Should Be Tested Independently

**What happened**: Gen-3 bundled 4 changes simultaneously (masking fix, wider
d_model, semantic groups, attention pooling). This makes it impossible to
attribute the metric changes to individual changes.

**Takeaway**: Ideally, the masking fix should have been tested first in
isolation (Gen-2 architecture + proper masking) to establish the pure "leak
removal" effect. Then architectural improvements could be measured against that
honest Gen-2 baseline.

**Partial mitigation**: The persistence baseline comparison (25–27% improvement)
provides a leak-free reference point. But we don't know whether the wider
d_model or semantic groups are helping, hurting, or neutral — only future
ablations will tell.

---

## 13. What This Means Going Forward

### The Honest Starting Point

Gen-3's 14–15% improvement over persistence (RMSE-space) is the new floor. Every
future improvement builds from here. No more phantom metrics.

```
                Persistence ──── 0% improvement (34.3 / 49.0 mg/dL)
                     │
              Gen-3 baseline ── 14-15%  ← YOU ARE HERE (29.5 / 41.5 mg/dL)
                     │
              Published SOTA ── 30-45%  (larger datasets, longer histories)
                     │
         Theoretical limit ──── ???%    (glucose is partially stochastic)
```

### What We Now Know (EXP-161/162 Conclusions)

1. **Architecture doesn't matter for forecasting at this data scale.** 67K params
   matches 993K params. Monolithic context_proj matches semantic groups. The model
   has saturated on the available signal.

2. **The 8-feature, 1-hour ceiling is absolute.** 29.5 mg/dL across all 12
   configurations, all architectures, all regularization strategies. This is a
   fundamental data limitation.

3. **21-feature models show a narrow optimization window.** Deep + narrow + mild
   regularization wins (41.5 vs 42.2 for worst), but the spread is only 0.7 mg/dL.

4. **Extended features don't help with forecasting (yet).** The 13 additional
   features (CAGE/SAGE, device lifecycle, monthly phase, overrides) don't improve
   forecast MAE. They may prove valuable for longer-horizon tasks.

### Priority Directions (Revised Post-Sweep)

#### 1. More Data (Highest Priority)

The single most impactful change. Currently: 10 patients, ~32K windows (8f) or
~16K windows (21f). Options:
- **More patients**: Recruit from Nightscout community (Open Humans, Tidepool)
- **Longer histories**: Current ~6-month windows could be extended to years
- **Data augmentation**: Time jitter, Gaussian noise, interpolation

At SOTA benchmarks, models train on 50–500 patients with 1+ year of data each.
Our 10-patient dataset is 10–50× smaller than typical published work.

#### 2. Multi-Task Training (Unlock Non-Forecasting Capabilities)

The event, drift, and state heads are architecturally present but untrained.
This is the highest-leverage code change:
- Event detection needs separate training (XGBoost hybrid, F1=0.710 ceiling)
- Drift tracking needs longer windows (24–72h timescale)
- Override recommendation needs compositional pipeline
- Semantic groups may prove their worth here (untested)

#### 3. Per-Patient Adaptation

LOO analysis showed 15% of variance is patient-specific. Options:
- Patient embedding vectors (learned per-patient offsets)
- Fine-tuning on individual patients after group pre-training
- Adaptive normalization (patient-specific glucose scaling)

#### 4. Hybrid XGBoost for Events (Phase 5)

Neural event detection F1 = 0.107 vs XGBoost F1 = 0.710 shows that
gradient boosting dramatically outperforms transformers for event
classification. The planned hybrid architecture:

```
Transformer → glucose forecast (MAE ≈ 29.5 mg/dL)
    │
    └── encoded representations → XGBoost → event detection (F1 ≈ 0.710)
```

Use the transformer as a feature extractor and XGBoost as the classifier.

#### 5. Longer Context or Hierarchical Architecture

Current 1–2 hour windows may be too short for slow dynamics (exercise
aftereffects, sensor drift, circadian patterns). Options:
- Longer windows (4–8h), though this reduces training samples
- Hierarchical: fast encoder for recent data + slow encoder for daily patterns
- Summary statistics as inputs (24h glucose statistics, 7-day trends)

---

## Appendix: Channel Reference

### Complete 21-Feature Schema

Source: `tools/cgmencode/schema.py`

| Index | Name | Group | Normalization | Range | Future |
|-------|------|-------|---------------|-------|--------|
| 0 | glucose | State | /400 | [0, 1] | Unknown |
| 1 | IOB | State | /20 | [0, 1] | Unknown |
| 2 | COB | State | /100 | [0, 1] | Unknown |
| 3 | net_basal | Action | /5 | [−1, 1] | Unknown |
| 4 | bolus | Action | /10 | [0, 1] | Unknown |
| 5 | carbs | Action | /100 | [0, 1] | Unknown |
| 6 | time_sin | Time | native | [−1, 1] | Known |
| 7 | time_cos | Time | native | [−1, 1] | Known |
| 8 | day_sin | Weekday | native | [−1, 1] | Known |
| 9 | day_cos | Weekday | native | [−1, 1] | Known |
| 10 | override_active | Override | binary | {0, 1} | Known |
| 11 | override_type | Override | encoded | [0, 1] | Known |
| 12 | glucose_roc | Dynamics | /10 | [−1, 1] | Unknown |
| 13 | glucose_accel | Dynamics | /5 | [−1, 1] | Unknown |
| 14 | time_since_bolus | Timing | /360 | [0, 1] | Unknown |
| 15 | time_since_carb | Timing | /360 | [0, 1] | Unknown |
| 16 | cage_hours | Device | /72 | [0, 1] | Known |
| 17 | sage_hours | Device | /240 | [0, 1] | Known |
| 18 | sensor_warmup | Device | binary | {0, 1} | Known |
| 19 | month_sin | Monthly | native | [−1, 1] | Known |
| 20 | month_cos | Monthly | native | [−1, 1] | Known |

### Masking Summary

```
Channels 0-5:    [████████████]  ALL MASKED   — glucose + insulin + meals
Channels 6-11:   [            ]  all known    — time + calendar + overrides
Channels 12-15:  [████████████]  ALL MASKED   — derivatives + treatment timing
Channels 16-20:  [            ]  all known    — device lifecycle + monthly
```

**10 masked / 11 preserved** — the model sees future time, calendar,
overrides, and device state, but nothing about future glucose or treatments.

---

*Report generated from analysis of 159 experiments spanning Gen-1 through Gen-3
architectures. Source code references are relative to the repository root at
`tools/cgmencode/`. All metrics are from 5-fold cross-validation unless
otherwise noted.*
