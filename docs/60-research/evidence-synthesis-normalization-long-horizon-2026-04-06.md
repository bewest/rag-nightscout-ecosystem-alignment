# Evidence Synthesis: Normalization, Regularization, and Long-Horizon Strategies

**Date**: 2026-04-06 (updated 2026-04-06)
**Context**: Synthesis of EXP-001–368 findings, symmetry/sparsity analysis,
continuous PK modeling, FDA features, and cross-scale feature selection experiments.
Covers what the evidence shows so far, untried normalization/conditioning techniques,
strategies for extending to multi-day and multi-month analysis, and prioritized
experiment proposals for the next phase.

> **Addendum (2026-04-06)**: Two concurrent research threads discovered running
> EXP-360–368 in parallel with overlapping IDs. The forecasting thread
> (`exp_pk_forecast_v3/v4.py`) claimed EXP-360–368 for dual-branch CNN, ISF
> normalization, conservation regularization, learned PK kernels, ensemble methods,
> dilated TCN, horizon conditioning, and ResNet experiments. The classification
> thread (`exp_arch_12h.py`, `exp_transformer_features.py`) independently claimed
> EXP-360–362 for hybrid features, architecture search, and transformer+features.
> All experiment proposals below have been renumbered **+6** (EXP-363→369 through
> EXP-378→384) to avoid conflicts. New best forecasting result: **Dilated TCN +
> future PK = MAE 26.7** (EXP-366, supersedes EXP-356's MAE=35.4).

**Prior Reports Referenced**:
- `symmetry-sparsity-feature-selection-2026-04-05.md` — Symmetry hypotheses & sparse/dense problem
- `cross-scale-feature-synthesis-2026-04-06.md` — EXP-349/350/351 combined analysis
- `continuous-physiological-state-modeling-2026-04-05.md` — UVA/Padova PK models
- `research-synthesis-2026-04-05.md` — Multi-objective intelligence summary (EXP-287–327)
- `validated-classification-results-2026-04-05.md` — Validated classifiers with CIs

---

## 1. State of the Evidence: What 362 Experiments Tell Us

### 1.1 Production-Viable Results

| Objective | Best Metric | Experiment | Architecture | Status |
|-----------|-------------|------------|--------------|--------|
| UAM Detection | **F1=0.969** | EXP-349 `no_time_6ch` | 1D-CNN, 2h | ✅ Deployment-ready |
| Override Prediction | **F1=0.882** CI=[0.871,0.893] | EXP-343 Platt-CNN | 1D-CNN + Platt, 2h | ✅ Deployment-ready |
| Hypo Prediction | **F1=0.676, AUC=0.958** | EXP-345 MT-CNN+Platt | Multi-task CNN, 2h | ✅ Viable w/ calibration |
| ISF Drift | **10/11 patients** detected | EXP-334 FPCA biweekly | Rolling statistics | ✅ Method proven |
| Glucose Forecasting (1hr) | **MAE=11.25 mg/dL, MARD≈7.3%** | EXP-251 ensemble | GroupedEncoder, 2h | ✅ CGM-grade |
| Multi-Horizon PK Forecast | **MAE=26.7** (−35% vs baseline) | EXP-366 dilated TCN | Dilated TCN + future PK | ⚠️ Regression |

> **Updated (2026-04-06)**: Clinical metrics added. ERA 2 glucose forecasting
> (EXP-043–171) achieves MARD≈8% at 1hr — **CGM-grade accuracy** (Dexcom G7
> real-time MARD≈8.2%). ERA 3 multi-horizon forecasters (EXP-352–372) regressed
> to MARD≈17% at the same 1hr horizon. This 2.2× gap persists even after
> controlling for data split method (EXP-046: random vs temporal = 0.2 mg/dL
> difference). Root causes: (1) multi-patient pooling without fine-tuning,
> (2) CNN vs Transformer architecture, (3) multi-horizon objective diluting
> single-horizon optimization. See §1.8 below.
>
> EXP-366 (dilated TCN deep with future PK channels) supersedes EXP-356/357
> (MAE=35.4). Also notable: EXP-367 horizon conditioning + ISF + future PK
> = MAE=27.1; EXP-365 learned ensemble = MAE=30.7.

### 1.2 Definitively Proven Principles

**Principle 1: Time-Translation Invariance (EXP-349, EXP-298)**

Removing sin/cos time features at ≤12h windows improves all tasks:

| Task | With Time | Without Time | Δ | Interpretation |
|------|-----------|-------------|---|----------------|
| UAM | F1=0.962 | **F1=0.971** | +0.9% | Meals are time-invariant events |
| Override | F1=0.840 | **F1=0.844** | +0.4% | Glucose trajectory shape matters, not clock |
| Hypo AUC | 0.947 | **0.949** | +0.2% | Low BG risk is time-independent at 2h |

At ≥24h scales, time features become essential (circadian rhythm IS the pattern).

**Principle 2: Scale-Dependent Feature Importance (EXP-287, EXP-298, EXP-349–351)**

No universal feature set works across scales:

| Feature Engineering | 2h Effect | 6h Effect | 12h Effect |
|--------------------|-----------|-----------|------------|
| Remove time (sin/cos) | **Helps** all tasks | Neutral/hurts | Helps hypo, hurts override |
| B-spline smoothing | **Helps** override (+1.1%), hypo (+0.6%) | **Hurts** most tasks | **Hurts** all tasks |
| PK channels (replace) | **Hurts** UAM (−3.4%) | Not tested alone | **Helps** override (+1.5%) |
| Augmented 16ch | Hurts (UAM −1.1%) | Not tested | Not tested |
| Hybrid raw+FDA | Not tested at 2h | Helps override (+0.6%) | Hurts (−3.5%) |

**Why**: At 2h the CNN sees 12 history steps — smoothing helps because noise dominates.
At 12h with 72 steps, the CNN learns its own multi-scale features — external smoothing
destroys information. PK channels encode absorption state that requires ≥6h of visible
DIA to be informative.

**Principle 3: The DIA Valley (EXP-289)**

Pattern matching quality follows a U-curve across window sizes:

| Window | Silhouette | Interpretation |
|--------|-----------|---------------|
| 2h | −0.367 | Sees onset only — one side of absorption arc |
| 4h | −0.537 | Onset + peak — no resolution context |
| 8h | **−0.642** (worst) | Overlapping incomplete envelopes |
| 12h | −0.339 (best) | Complete rise→peak→resolution |
| 7d | −0.301 (global best) | Full circadian + weekly pattern |

Models need complete absorption arcs: window ≥ 2 × max(DIA, carb_absorption_time).

**Principle 4: 1D-CNN Universally Best for Classification (EXP-313, EXP-339)**

| Architecture | UAM F1 | Override F1 | Notes |
|-------------|--------|-------------|-------|
| 1D-CNN | **0.939** | **0.726** (60min) | Best across all tasks |
| Self-Attention | 0.937 | **0.852** (15min) | Comparable, slightly better at short lead |
| Transformer Embedding | 0.400 | — | Fails for classification |
| CNN + Embedding | 0.920 | 0.700 | Adding embeddings **hurts** |

Attention ≈ CNN (Δ=0.002). Adding embeddings to CNN hurts — don't concatenate
heterogeneous representations.

**Principle 5: Platt Calibration Is Essential (EXP-324, EXP-343, EXP-345)**

| Task | ECE Before | ECE After | F1 Preserved? | Threshold Shift |
|------|-----------|-----------|----------------|-----------------|
| Override | 0.084 | **0.046** (−45%) | ✅ +0.018 gain | 0.87→0.28 |
| Hypo | 0.114 | **0.014** (−88%) | ✅ preserved | 0.92→0.47 |
| UAM | 0.018 | **0.014** | ✅ preserved | minimal |

Platt scaling makes probability thresholds practical for clinical use.

**Principle 6: Future PK Projection — Biggest Forecasting Breakthrough (EXP-356→366)**

Known-future insulin decay and carb absorption are legitimate inputs (no information
leakage — these are deterministic consequences of past events):

| Variant | MAE Overall | h120 MAE | h720 MAE | Δ vs glucose_only |
|---------|------------|----------|----------|-------------------|
| glucose_only | 44.2 | 43.6 | 54.7 | — |
| glucose+future_pk | **39.9** | **40.4** | **51.6** | −4.3 (−10%) |
| baseline_8ch | 42.0 | 41.8 | 51.0 | −2.2 |
| baseline_8ch+future_pk | **37.6** | **38.2** | **42.1** | −6.6 (−15%) |
| dilated_tcn_deep+future_pk | **26.7** | — | — | **−17.5 (−40%)** |

> **Updated (EXP-365–368)**: Dilated TCN architecture with future PK channels
> achieves MAE=26.7 (EXP-366), a 40% reduction from glucose-only baseline. The
> dilated convolutions (d=[1,2,4,8,16]) provide receptive field covering the full
> history, while future PK channels provide absorption trajectory. Horizon
> conditioning (EXP-367) with ISF normalization + future PK reaches MAE=27.1.
> Learned ensemble of ISF-normalized and standard models reaches MAE=30.7 (EXP-365).

Peak gain at h120 (−10 mg/dL). At h720 (12 hours), future_pk advantage grows to
−12.6 mg/dL when combined with full 8ch history.

**Principle 7: Architecture Matters at Long Scales (EXP-361 arch_12h)**

At 12h episode scale, standard deep CNN receptive field (RF=9 steps = 45min) covers
only 6.2% of the window. Architecture search across 6 architectures × 2 feature
sets (3 seeds each) shows:

| Architecture | Override F1 | Hypo AUC | Prolonged High F1 | RF Coverage |
|-------------|------------|----------|-------------------|-------------|
| deep_cnn (control) | 0.605 | 0.778 | 0.518 | 6.2% |
| transformer (global attn) | **0.610** | 0.778 | **0.528** | 100% |
| cnn_downsample (2×) | 0.608 | 0.778 | 0.521 | 12.5% |
| dilated_cnn (d=1..16) | 0.598 | **0.780** | 0.491 | 43.8% |
| large_kernel (k=7) | 0.602 | 0.775 | 0.513 | 34.0% |
| se_cnn (channel attn) | 0.603 | 0.777 | 0.520 | 6.2% |

Transformer wins override and prolonged_high but margins are tiny (+0.5–1.0%).
Dilated CNN wins hypo AUC. pk_no_time_6ch features HURT all architectures at 12h
(control baseline_8ch consistently better). This suggests the 12h classification
bottleneck is not architecture but feature engineering for long episodes.

### 1.3 Approaches That Failed

| Approach | Experiment | Result | Why It Failed |
|----------|-----------|--------|---------------|
| VAE bottleneck | EXP-001 | MAE=42.78 | 32D latent destroys sequence structure |
| DDPM diffusion | EXP-020 | MAE=28.66 | Conditioning too crude; data scarcity |
| Conditioned Transformer | EXP-004/006 | MAE=26.14 | Immediate overfitting |
| Multi-task shared encoder | EXP-145 | −0.08–0.12 F1 | Shared encoder hurts all objectives |
| 39f enrichment (unmasked) | EXP-260 | Data leaks | Ch34 glucose_vs_target: 35× leakage |
| PK channels alone | EXP-348 | r=0.18 (target 0.30) | Helps but doesn't dominate |
| Functional inner products | EXP-359 | +0.83 MAE (hurt) | Scalar features give CNN zero temporal gradient |
| Conservation regularization | EXP-362 | +0.58 MAE (hurt) | Constraint too weak or wrong formulation |
| Augmented 16ch | EXP-349 | −1.1% UAM F1 | Curse of dimensionality (50K params, 35K samples) |

### 1.4 Partial Successes (Promising But Not Yet Fully Realized)

| Approach | Experiment | Result | What's Missing |
|----------|-----------|--------|---------------|
| Rolling ISF drift | EXP-312 | 9/11 biweekly | No ML model built on top yet |
| Glucodensity | EXP-330 | Sil=+0.508 | Not integrated into classification pipeline |
| Functional depth (hypo) | EXP-335 | Q1=33.7% vs Q4=0.3% hypo | Not used as model feature |
| PK history channels | EXP-353 | Δ=−7.4 at 6h window | Only tested for forecasting, not classification |
| Hybrid raw+FDA at 6h | EXP-360 | +0.6% override | Small gain; needs more architectures |
| Dual-branch CNN | EXP-360b | MAE=27.2 (−18%) | Single-seed; needs multi-seed validation |

### 1.5 Clinical Forecast Metrics: ERA 2 → ERA 3 Performance Gap (2026-04-06)

**Problem**: ERA 2 glucose forecasting (EXP-043–171) achieves MARD≈8% at 1hr,
matching CGM real-time accuracy (Dexcom G7 MARD≈8.2%). ERA 3 multi-horizon
forecasters (EXP-352–372) regressed to MARD≈17% at the same 1hr horizon.

**Clinical Scoring Summary** (approximate MARD from stored MAE, population
glucose mean=155 mg/dL):

| Experiment | Horizon | MAE | MARD≈ | Clarke A+B≈ | Notes |
|-----------|---------|-----|-------|-------------|-------|
| EXP-057 patient_d | 1hr | 8.1 | 5.2% | 100% | Per-patient finetuned |
| EXP-048 physics residual | 1hr | 11.5 | 7.4% | 99.6% | Physics-informed |
| EXP-043 masked transformer | 1hr | 12.4 | 8.0% | 99.3% | CGM-grade |
| EXP-171 production ensemble | 1hr | 12.5 | 8.1% | 99.3% | Latest ERA 2 |
| EXP-169 calm segments | 1hr | 10.9 | 7.0% | 99.6% | Segment-specialized |
| EXP-169 volatile segments | 1hr | 19.0 | 12.3% | 96.4% | Hard cases |
| EXP-362 (ERA 3) | h30=30min | 18.7 | 12.1% | 96.6% | Multi-horizon CNN |
| EXP-362 (ERA 3) | h60=1hr | 25.9 | 16.7% | 91.3% | Multi-horizon CNN |
| EXP-367+ISF (ERA 3) | h60=1hr | 26.3 | 17.0% | 91.0% | Best ERA 3 at 1hr |
| Persistence baseline | 1hr | 34.3 | 22.1% | — | Both eras |

**Benchmark**: Dexcom G7 real-time MARD ≈ 8.2%, Clarke A+B > 99%.
Note: MARD for forecasts is not directly comparable to real-time CGM MARD since
forecasts predict future glucose, not current sensor readings.

**Controlled Analysis**:
- **Data leakage?** No — EXP-046 showed random vs temporal split = 0.2 mg/dL
  difference (12.9 vs 12.7), negligible
- **Same persistence baseline**: ERA 2 ~34.3, ERA 3 ~33.2 at h60 → same data
  distribution, very different model performance

**Root Causes of the 2.2× Gap**:

1. **Per-patient fine-tuning**: ERA 2 (EXP-057) fine-tunes per patient → 8.1–16.6
   mg/dL. ERA 3 pools 11 patients with no fine-tuning → loses personalization.
   EXP-371 (finetune experiment in our runner) directly addresses this.

2. **Architecture mismatch**: ERA 2 uses 4-layer GroupedEncoder (transformer).
   ERA 3 uses 1D-CNN. For 1hr forecasting, the transformer may have inherent
   advantages in capturing temporal attention patterns.

3. **Multi-horizon objective dilution**: ERA 3 optimizes MAE across h30–h720
   simultaneously. The model compromises short-horizon accuracy to serve
   long-horizon predictions. Single-horizon models (ERA 2) don't face this
   tradeoff.

4. **Window size / history length**: ERA 2 uses 2hr windows (12 steps history +
   12 steps forecast). ERA 3 uses 10hr windows (72 steps history + 48+ steps
   forecast). More context isn't always better — noise accumulates.

**Recommended Actions**:
- **Bridge experiment (high priority)**: Run ERA 2 transformer architecture on
  ERA 3 data pipeline with chronological split and per-patient fine-tuning.
  Expected to close the gap to ≤15 mg/dL.
- **Horizon-specific models**: Train separate 1hr-only model alongside multi-horizon.
  Compare clinical metrics head-to-head.
- **Clinical-loss fine-tuning**: Use existing `clinical_loss.py` (19:1 hypo/hyper
  asymmetry) to fine-tune best model. Evaluate MARD specifically in hypo range.

---

## 2. Current Normalization and Preprocessing Inventory

### 2.1 What's Implemented

| Technique | Location | Method | Scale |
|-----------|----------|--------|-------|
| Domain-specific linear | `schema.py:197-226` | `feature / SCALE[key]` | glucose/400, IOB/20, COB/100 |
| Glucose clipping | `schema.py:229-230` | Clip to [40, 400] mg/dL | Sensor physical limits |
| Per-patient basal normalization | `real_data_adapter.py:163-169` | `actual − median(basal)` | Removes patient baseline |
| Circadian sin/cos | `real_data_adapter.py:172-177` | `sin/cos(2π × hour/24)` | [-1, 1] |
| IOB exponential decay | `real_data_adapter.py:83-104` | Convolution with DIA kernel | DIA=5h, peak=55min |
| COB linear decay | `real_data_adapter.py:106-124` | Linear absorption over 3h | carb_abs_time=3h |
| B-spline smoothing | `fda_features.py:61-95` | Cubic B-spline fit | n_basis ≈ n_points−2 |
| Analytic derivatives | `fda_features.py:222-251` | d/dt of B-spline fit | 1st + 2nd order |
| Glucodensity histograms | `fda_features.py:186-220` | 50-bin KDE of glucose | [0, 1] normalized |
| FPCA decomposition | `fda_features.py:114-145` | B-spline + PCA | K=2–5 components |
| Functional depth | `fda_features.py:254-270` | Modified Band Depth | [0, 1] per sample |
| PK activity curves | `continuous_pk.py:50-88` | oref0 exponential model | 8 PK channels |
| Hill equation hepatic | `continuous_pk.py:346-413` | IOB suppression + circadian | coeff=1.5, 65% max |
| Multi-scale downsampling | `run_pattern_experiments.py:832` | Temporal aggregation | 5min→15min→1h→4h |
| Time-since capping | `real_data_adapter.py:673-680` | Cap at 360 min | 6h memory window |
| CAGE/SAGE normalization | `real_data_adapter.py:684-690` | `age / device_life` | 72h / 240h |

### 2.2 What's NOT Implemented (Gaps)

| Technique | Why It Matters | Tested? |
|-----------|---------------|---------|
| ISF-normalized glucose | Cross-patient equivariance | ❌ Not tested |
| Per-patient z-score | Equalizes patient variance | ❌ Not tested |
| Log-transform of doses | Compresses skewed bolus/carb range | ❌ Not tested |
| Physics-residual normalization | Removes explainable signal | Partial (EXP-358 roc only) |
| Cumulative integral features | Captures exposure at long scales | ❌ Not tested |
| Multi-rate EMA | Implicit multi-scale without windows | ❌ Not tested |
| Absorption phase encoding | Continuous state from sparse events | ❌ Not tested |
| Heteroscedastic loss | Weights by sensor reliability | ❌ Not tested |
| STL trend decomposition | Separates drift/circadian/residual | ❌ Not tested |
| Bayesian hierarchical state | Pools patients at multi-week | ❌ Not tested |
| Kalman filter state tracking | Latent ISF/CR/basal evolution | ❌ Not tested |

---

## 3. Proposed Normalization, Regularization, and Conditioning Techniques

### 3.1 ISF-Normalized Glucose (Priority: ★★★★★)

**Rationale**: Patient A (ISF=40) receiving 2U sees a 80 mg/dL drop. Patient B (ISF=80)
sees 160 mg/dL. Currently the model must learn this patient-specific scaling from data.
ISF normalization makes the response curves identical:

```
BG_isf(t) = (BG(t) - BG_target) / ISF_scheduled(t)
```

**Why not yet tested**: Requires patient-specific ISF from profile.json. The data is
available (`real_data_adapter.py` loads profiles) but normalization uses fixed /400.

**Expected impact**: Reduces LOO generalization gap (currently 2.9% override, 4.0%
hypo per EXP-326). Profile features (ch 32-33: scheduled_isf, scheduled_cr) partially
address this as auxiliary channels, but explicit normalization is cleaner — the model
shouldn't have to learn division.

**Implementation**: Modify `build_nightscout_grid()` to accept ISF schedule, compute
`(glucose - target) / ISF` as channel 0 instead of `glucose / 400`.

**Caveat**: ISF schedules are often approximate. Patient may have outdated profile.
Use scheduled ISF (from profile.json) as best estimate; the residual encodes the
true patient state.

### 3.2 Per-Patient Z-Score + Raw Hybrid (Priority: ★★★★)

**Rationale**: Patient glucose ranges vary (80–200 vs 60–350). Fixed /400 normalization
means Patient B's variance dominates training.

```
BG_z(t) = (BG(t) - μ_patient) / σ_patient
```

**Risk**: Loses absolute magnitude (below 70 = hypo). Solution: keep both raw/400
AND z-scored as separate channels. The CNN learns to use z-scored for pattern shape
and raw for threshold detection.

**Expected impact**: Improved cross-patient pattern retrieval (currently Sil=+0.326
at weekly scale). z-scoring makes patient contributions more uniform.

### 3.3 Physics-Residual as Primary Target (Priority: ★★★★)

**Rationale**: The physics model (`physics_model.py`) predicts glucose from IOB×ISF +
COB×ISF/CR. The neural net should learn the **residual** — unexplained effects
(exercise, stress, sensor drift, dawn phenomenon).

```
target(t) = actual_glucose(t) - physics_predicted(t)
```

**Prior work**: EXP-358 tested `glucose_roc − PK_roc` (derivative-space residual) with
modest gains (+0.5 MAE). EXP-362 tested conservation loss (∫residual≈0) which actually
**hurt** (+0.58 MAE) — suggesting the conservation constraint is too aggressive or
wrongly formulated (residual doesn't actually integrate to zero due to unmodeled effects).

**Open question**: Is the raw residual (not derivative) more informative? The physics
model explains ~60% of glucose variance — the remaining 40% is the interesting signal.

### 3.4 Log-Transform of Doses (Priority: ★★★)

**Rationale**: Bolus doses range 0.5–15U, carbs 5–120g — heavily right-skewed. A 0.5U
correction and a 15U mega-bolus are treated very differently by the body, but in raw
normalization (bolus/10) they appear as 0.05 vs 1.5 — the correction is barely visible.

```
log_bolus = log(1 + bolus_units) / log(1 + 15)   # normalized [0, 1]
log_carbs = log(1 + carb_grams) / log(1 + 120)
```

**Expected impact**: Most relevant at episode/daily scales where multiple events
accumulate. May help the model distinguish correction-heavy days from meal-heavy days.

### 3.5 Cumulative Integral Features (Priority: ★★★★ for long scales)

**Rationale**: At multi-day scales, cumulative exposure matters more than instantaneous:

```
glucose_load(t, τ) = ∫_{t-τ}^{t} max(0, BG(s) - 180) ds   # hyperglycemic exposure
hypo_load(t, τ) = ∫_{t-τ}^{t} max(0, 70 - BG(s)) ds       # hypoglycemic exposure
insulin_total(t, τ) = ∫_{t-τ}^{t} IOB(s) ds                 # total insulin delivered
```

These are naturally smooth, monotonically informative at longer windows, and directly
relate to clinical metrics (A1C ∝ glucose_load over 90 days).

**Implementation**: Rolling cumulative sums at 6h, 12h, 24h windows. Add as
auxiliary channels at episode+ scales.

### 3.6 Multi-Rate Exponential Moving Averages (Priority: ★★★)

**Rationale**: Implicit multi-scale representation without separate windows:

```
ema_fast(t)   = 0.30 × BG(t) + 0.70 × ema_fast(t-1)    # ~15min half-life
ema_medium(t) = 0.05 × BG(t) + 0.95 × ema_medium(t-1)   # ~2h half-life
ema_slow(t)   = 0.005 × BG(t) + 0.995 × ema_slow(t-1)   # ~24h half-life
```

Differences capture "how unusual is right now":
- `ema_fast − ema_medium` = acute deviation from recent trend
- `ema_medium − ema_slow` = multi-hour deviation from daily baseline

**Expected impact**: Especially useful for 3-day and weekly windows where the model
needs both fine-grained and coarse context simultaneously.

### 3.7 Absorption Phase Encoding (Priority: ★★★)

**Rationale**: Instead of raw bolus spike (0.7% of temporal extent at 12h), encode
the absorption state as a continuous signal:

```
phase ∈ {no_event, rising, peak, falling, recovery}  (one-hot or ordinal)
fraction_absorbed ∈ [0.0, 1.0]                        (continuous)
time_to_peak ∈ [-DIA/2, +DIA/2]                       (signed distance)
```

The PK channels (`continuous_pk.py`) partially achieve this via activity curves, but
phase encoding is more explicit and interpretable.

### 3.8 Heteroscedastic Loss (Priority: ★★)

**Rationale**: CGM accuracy varies with sensor age (SAGE), glucose level (less accurate
at extremes), and sensor type (Dexcom MARD ~9%, Libre ~11%):

```
loss_i = (y_i - ŷ_i)² / (2σ²_i) + log(σ_i)
σ_i = f(SAGE_i, BG_level_i, sensor_type_i)
```

**Expected impact**: Modest. Currently SAGE is available as a feature (ch 19) but not
used to weight the loss. Most impactful for multi-patient models where sensor types vary.

### 3.9 STL Trend Decomposition (Priority: ★★★★★ for multi-week)

**Rationale**: At scales ≥3 days, glucose exhibits three distinct components:

```
glucose(t) = trend(t) + seasonal(t) + remainder(t)
```

- **trend**: Slow ISF/CR drift, therapy changes, illness (the signal for drift detection)
- **seasonal**: Circadian pattern (dawn phenomenon, post-meal timing)
- **remainder**: Acute events, sensor noise (the signal for event detection)

Each component has different normalization needs and is best learned by different models.
The ISF drift detector should operate on trend only; the event detector on remainder only.

**Implementation**: Use `statsmodels.tsa.seasonal.STL` with period=288 (24h at 5-min)
for daily seasonality, or period=2016 (7d at 5-min) for weekly.

---

## 4. Strategies for Extending to Multi-Day and Multi-Month Analysis

### 4.1 The Fundamental Challenge

| Scale | Resolution | Steps | Windows/Patient | Total Windows (11 pts) | Viable Model |
|-------|-----------|-------|----------------|----------------------|-------------|
| 2h | 5-min | 24 | ~2,000 | ~22,000 | CNN/Transformer ✅ |
| 12h | 5-min | 144 | ~360 | ~4,000 | Deep CNN ✅ |
| 3d | 15-min | 288 | ~30 | ~330 | Dilated CNN ⚠️ |
| 7d | 1h | 168 | ~13 | ~143 | GRU/small Transformer ⚠️ |
| 30d | 4h | 180 | ~3 | ~33 | Statistical only ❌ for NN |
| 90d | daily | 90 | ~1 | ~11 | Bayesian/mixed-effects ❌ for NN |

Neural networks require ~1,000+ training samples for stable convergence. Above 7d
windows, sample counts become insufficient. The strategy must shift from neural
architectures to statistical models, using short-scale neural nets as feature extractors.

### 4.2 Three-Day Scale (Practical CNN Extension)

**Target resolution**: 15-min intervals → 288 steps
**Architecture**: Dilated 1D-CNN (proven effective; TCN-style)

Key techniques:

**Dilated Convolutions**: kernel_size=3 with dilation=[1,2,4,8,16,32] gives 192-step
receptive field without pooling — the network sees ~48 hours in a single pass.

**Hierarchical Pooling**: Process in 12h blocks using the proven episode-scale CNN,
pool to block-level features, then sequence model over 6 blocks. Each 12h block uses
the architecture already validated in EXP-350.

**Weekday/Weekend Feature**: At 3-day scale, day-of-week genuinely matters. Sleep timing,
exercise patterns, and eating schedules differ. Add binary `is_weekend` or sin/cos
day-of-week encoding.

**Rolling Net-Balance Integrals**: Rather than instantaneous PK channels, compute:
- `∫net_balance dt` over rolling 6h, 12h, 24h windows
- These capture "is insulin keeping up with carbs over the last day?"

**Realistic Objective at 3d**: **Behavioral episode segmentation** — classify 3-day
windows as "well-controlled", "high-carb-struggling", "illness-affected",
"sensor-degraded". This requires ~100+ labeled examples, achievable with 11 patients.

### 4.3 Seven-Day Scale (Current Frontier)

**Target resolution**: 1h intervals → 168 steps
**Architecture**: GRU or small Transformer (proven in EXP-301)

Key techniques:

**Per-Day Summary → Sequence Model**: Compute daily feature vectors:
- Time-in-range (TIR), glucose mean/std/CV, glucose min/max
- Total daily dose (TDD), basal fraction, bolus count, carb total
- Event counts from 2h/12h classifiers (UAM count, hypo count, override triggers)
- Glucodensity histogram (50-bin)

Feed 7 daily vectors to a small Transformer/GRU. This reduces 168×8 → 7×D with D~20-50.

**Glucodensity per Day**: The 50-bin histogram captures distribution shape (bimodal,
skewed, heavy-tailed). 7 daily histograms → (7, 50) tensor → 2D CNN or attention.
EXP-330 showed glucodensity Sil=+0.508 vs TIR — it captures what summary statistics miss.

**Rolling ISF_effective as Conditioning**: The proven ISF drift detector (EXP-312,
9/11 patients at biweekly) provides a trajectory of insulin sensitivity. Use this as
a conditioning signal (FiLM-style) that tells the model "this patient is becoming more
insulin resistant this week."

**Realistic Objective at 7d**: **Weekly pattern retrieval and clustering** (current
best Sil=+0.326 per EXP-304). Target: positive silhouette > 0.5 with ISF conditioning
and glucodensity features.

### 4.4 Multi-Week Scale (2–4 Weeks)

**Target resolution**: 4h intervals or daily summaries
**Architecture**: Statistical models, NOT neural networks (~33 windows insufficient)

**FPCA on Weekly Trajectories**: Each week becomes a single functional observation.
FPCA across weeks captures dominant modes of week-to-week variation. EXP-329 showed
K=2 captures 90% of glucose variance at 2h — extend to weekly curves.

Weekly FPCA scores become a low-dimensional time series that tracks behavioral drift:
```
week_1_scores = [pc1_w1, pc2_w1]
week_2_scores = [pc1_w2, pc2_w2]
...
```

A shift in PC1 trajectory flags changing glucose dynamics. PC1 likely encodes mean
glucose level; PC2 likely encodes variability pattern.

**Change-Point Detection (CUSUM/PELT)**: Rather than sliding windows, detect structural
breaks. EXP-325 tested CUSUM for ISF drift. Extend to detect:
- Sensor replacements (discontinuity in noise floor)
- Infusion site changes (temporary absorption variation)
- Illness onset (sudden glucose elevation + insulin resistance)
- Travel/timezone shifts (circadian phase shift)

**Mixed-Effects Models**: Pool across patients with patient-level random effects:
```
daily_glucose_mean ~ β₁ × TDD + β₂ × carb_total + β₃ × exercise
                     + b_patient  (random intercept)
                     + b_patient × time  (random slope = drift)
```

This is the statistical workhorse for multi-week clinical trials. It works with
N < 100 observations per patient and naturally handles missing data.

### 4.5 Multi-Month Scale (1–6 Months)

**Target resolution**: Daily or weekly summaries
**Architecture**: Bayesian hierarchical models, Kalman filters, survival analysis

**A1C-Equivalent Trajectory Modeling**: Rolling 30-day glucose mean ≈ estimated A1C.
Model this summary statistic:

```
eA1C(t) = (rolling_30d_mean_glucose + 46.7) / 28.7   # ADAG formula
```

Track eA1C(t) trajectory — is it rising, falling, stable? This is what endocrinologists
care about at the quarterly visit scale.

**Bayesian Hierarchical State Model**:
```
ISF_patient[t] ~ Normal(ISF_population[t] + patient_offset, σ_patient)
ISF_population[t] ~ RandomWalk(ISF_population[t-1], σ_drift)
observed_effective_ISF ~ Normal(ISF_patient[t], σ_obs)
```

This pools information across patients while estimating patient-specific trends.
Even with 11 patients × 90 days, Bayesian methods provide meaningful posterior
distributions over parameters.

**Kalman Filter for Physiological State Tracking**:
- Hidden states: ISF(t), CR(t), basal_need(t)
- Observations: daily TDD, mean glucose, hypo count, event classifier outputs
- Process model: slow random walk (σ_process small)
- Observation model: physics-informed mapping from states to observations

Naturally handles missing data, sensor gaps, and provides uncertainty estimates.

**Survival Analysis for Event Recurrence**:
- Model: time-to-next-hypo or time-to-next-prolonged-high
- Method: Cox proportional hazards with time-varying covariates
- Covariates: rolling TDD, mean glucose, ISF trajectory, CAGE/SAGE
- Output: hazard ratio changes over months (e.g., "hypo risk doubled this month")

### 4.6 The Hierarchical Pipeline Architecture

The key architectural insight: **each scale consumes outputs of the scale below**.
Short-scale neural nets are feature extractors for long-scale statistical models.

```
Layer 0: Raw 5-min CGM + treatments
    │
    ├── Layer 1: 2h 1D-CNN
    │   ├── UAM events (F1=0.969)
    │   ├── Hypo alerts (AUC=0.958)
    │   └── Override predictions (F1=0.882)
    │
    ├── Layer 2: 12h Deep CNN
    │   ├── Episode patterns (prolonged high/low)
    │   └── Absorption envelope features
    │
    ├── Layer 3: Daily Aggregation
    │   ├── Event counts from L1/L2 models
    │   ├── Glucodensity histogram
    │   ├── TIR / TDD / glucose mean / glucose CV
    │   └── Rolling ISF_effective (from PK model)
    │
    ├── Layer 4: Weekly (7 × daily vectors)
    │   ├── Sequence model (GRU/Transformer)
    │   ├── FPCA scores for week trajectory
    │   └── Pattern clustering (Sil target >0.5)
    │
    ├── Layer 5: Biweekly Rolling
    │   ├── ISF drift detection (proven 9-10/11 patients)
    │   └── Change-point detection (CUSUM/PELT)
    │
    └── Layer 6: Monthly/Quarterly
        ├── eA1C trajectory modeling
        ├── Bayesian hierarchical ISF/CR state estimation
        ├── Survival analysis (event recurrence risk)
        └── Clinical visit summary generation
```

Each layer adds **interpretable features** and avoids raw 5-min data at long scales.

---

## 5. Prioritized Experiment Proposals

### Tier 1: High Impact, Ready to Run (Next Available: EXP-369+)

#### EXP-369: ISF-Normalized Glucose for Cross-Patient Generalization

**Hypothesis**: Using `(BG - target) / ISF` as glucose channel (replacing `BG / 400`)
reduces LOO generalization gap by ≥1% on override and hypo tasks.

**Method**: Rerun EXP-326 (LOO validation) with ISF-normalized glucose.
- Load patient ISF schedules from profile.json
- Compute ISF-interpolated normalization per timestep
- Run same 1D-CNN architecture, same evaluation protocol

**Success Criterion**: LOO F1 gap < 2.0% (vs current 2.9% override, 4.0% hypo)

**Priority**: ★★★★★ — Single highest-leverage normalization change untested.
Directly tests the scaling equivariance hypothesis from symmetry doc §2.4.

**Dependencies**: None. Profile data available in `real_data_adapter.py`.

---

#### EXP-370: Per-Patient Z-Score + Raw Dual-Channel

**Hypothesis**: Providing both `BG/400` and `(BG−μ_patient)/σ_patient` as separate
channels improves cross-patient pattern retrieval Silhouette by ≥0.05.

**Method**:
- Compute per-patient μ, σ over training data
- Channel 0: `BG/400` (preserves absolute threshold for hypo)
- Channel 1: z-scored (equalizes patient variance)
- Replace single glucose channel with dual; total channels 9

**Success Criterion**: Weekly Silhouette > +0.376 (baseline +0.326 per EXP-304)

**Priority**: ★★★★ — Addresses known cross-patient variance issue.

---

#### EXP-371: Functional Depth as Hypo Enrichment Feature

**Hypothesis**: Adding functional depth score as a model feature improves hypo
F1 by ≥0.02, exploiting EXP-335's finding that Q1 depth has 33.7% hypo rate
vs Q4's 0.3%.

**Method**:
- Compute Modified Band Depth per window (already in `fda_features.py`)
- Append as auxiliary channel to 2h CNN
- Run validated hypo classification pipeline

**Success Criterion**: Hypo F1 > 0.696 (vs current 0.676 per EXP-345)

**Priority**: ★★★★ — Low implementation cost, strong prior signal.

---

#### EXP-372: Glucodensity-Augmented Override Classifier

**Hypothesis**: Appending 8-bin glucodensity histogram to CNN classifier head
improves override F1 by ≥0.01 at 6h scale.

**Method**:
- Compute glucodensity of history half of window
- Inject at classifier head (NOT as conv input — per EXP-338 finding)
- Test at 2h, 6h, 12h scales

**Success Criterion**: Override F1_macro > 0.710 at 6h (vs 0.698 baseline)

**Priority**: ★★★★ — Glucodensity showed Sil=+0.508 (EXP-330) but never
integrated into supervised classification. Head injection proven (EXP-338).

---

#### EXP-373: Multi-Seed Future PK Validation

**Hypothesis**: EXP-356's future PK breakthrough (−10 mg/dL at h120) replicates
across 5 seeds with CI excluding zero improvement.

**Method**:
- Rerun `glucose+future_pk` and `baseline_8ch+future_pk` variants with seeds
  42, 123, 456, 789, 1337
- Compute 95% bootstrap CIs on MAE improvement
- Test at horizons h30, h60, h120, h240

**Success Criterion**: 95% CI for h120 improvement excludes zero.

**Priority**: ★★★★★ — Must validate the biggest forecasting breakthrough before
building on it. EXP-356 used 3 seeds; needs 5 for publication-grade CIs.

---

### Tier 2: Medium Impact, Extends Proven Methods

#### EXP-374: Cumulative Glucose Load Features at 3-Day Scale

**Hypothesis**: Rolling 6h/12h/24h hyperglycemic exposure integrals improve 3-day
episode classification by ≥0.03 F1_macro.

**Method**:
- New feature: `hyper_load_τ(t) = Σ max(0, BG(s) - 180)` for τ ∈ {6h, 12h, 24h}
- New feature: `hypo_load_τ(t) = Σ max(0, 70 - BG(s))` for same τ
- Normalize by τ (per-hour average exposure)
- Add as channels to 3-day dilated CNN
- Task: classify 3-day windows by control quality

**Success Criterion**: 3-class (good/mixed/poor) F1_macro > 0.65

**Priority**: ★★★ — First test of 3-day scale classification. Cumulative integrals
are the natural representation at this timescale.

---

#### EXP-375: Multi-Rate EMA Channels

**Hypothesis**: Adding fast/medium/slow EMA channels (and their differences) improves
6h/12h classification without increasing window size.

**Method**:
- Compute 3 EMA channels with half-lives ~15min, ~2h, ~24h
- Compute 2 difference channels: fast−medium, medium−slow
- Total: 5 new channels (13ch total with 8ch baseline)
- Test on override and hypo at 6h and 12h scales

**Success Criterion**: Override F1_macro improvement ≥ 0.01 at either scale.

**Priority**: ★★★ — Multi-rate features provide implicit multi-scale context.
Addresses the 6h performance plateau (baseline_8ch wins everything there).

---

#### EXP-376: STL Decomposition Channels at 3-Day Scale

**Hypothesis**: Decomposing glucose into trend+seasonal+residual and providing
each as separate channels improves 3-day classification vs raw glucose.

**Method**:
- Apply STL decomposition with period=288 (24h)
- 3 channels replace 1 glucose channel: trend, seasonal, residual
- Each normalized independently
- Compare 3-day classification: raw glucose vs decomposed

**Success Criterion**: ≥0.02 F1_macro improvement on 3-day behavioral classification

**Priority**: ★★★ — Directly enables the separate-normalization principle. Trend
channel feeds drift detection; residual channel feeds event detection.

---

#### EXP-377: Hierarchical 12h-Block → Sequence Model at 3-Day Scale

**Hypothesis**: Processing 3 days as six 12h blocks (using proven episode CNN)
then sequencing with GRU outperforms flat 3-day dilated CNN.

**Method**:
- Freeze pretrained 12h CNN from EXP-350
- Extract 64D embedding per 12h block (6 blocks per 3-day window)
- GRU or attention over 6-block sequence → classification head
- Compare vs flat dilated CNN on same 3-day task

**Success Criterion**: Hierarchical model F1 ≥ flat model F1 with <50% parameters.

**Priority**: ★★★ — Tests the hierarchical pipeline concept from §4.6. Reuses
proven components rather than training from scratch.

---

#### EXP-378: Daily Glucodensity Sequences for Weekly Patterns

**Hypothesis**: 7 × 50-bin daily glucodensity histograms → 2D CNN produces
weekly pattern Silhouette > +0.40 (vs current +0.326 with raw embeddings).

**Method**:
- For each day in 7-day window, compute 50-bin glucodensity
- Stack to (7, 50) image-like tensor
- Train small 2D CNN (3 layers) or treat as 7-step sequence of 50D vectors
- Evaluate with Silhouette score on weekly clustering

**Success Criterion**: Silhouette > +0.40

**Priority**: ★★★ — Combines two proven signals (glucodensity from EXP-330,
weekly embedding from EXP-304) in a novel way.

---

### Tier 3: Exploratory, Higher Risk

#### EXP-379: Log-Transformed Dose Channels

**Hypothesis**: `log(1 + dose)` normalization of bolus and carb channels improves
episode-scale (6h/12h) classification by making small corrections visible.

**Method**:
- Replace bolus/10 with log(1+bolus)/log(16)
- Replace carbs/100 with log(1+carbs)/log(121)
- Run override + hypo classification at 6h and 12h scales

**Success Criterion**: Any improvement ≥ 0.005 F1_macro at either scale.

**Priority**: ★★ — Low-cost change, but sparse channels are less important at
episode scale (EXP-298 shows bolus removal helps at 12h).

---

#### EXP-380: Absorption Symmetry Quantification

**Hypothesis**: Isolated insulin bolus glucose responses have symmetry ratio
0.7–1.3 around nadir; carb responses are more asymmetric (ratio 0.4–0.8).

**Method**: (From symmetry doc §4.2)
- Extract isolated events (no other events within ±3h)
- Compute pre-peak/post-peak area ratio for each
- Separate into insulin-only and carb-only responses
- Test for distinct distributions

**Success Criterion**: Insulin ratio distribution mean ∈ [0.7, 1.3] with 95% CI
not overlapping carb ratio distribution.

**Priority**: ★★ — Foundational hypothesis test. If confirmed, enables
symmetry-aware regularization (absorption_symmetry_loss from symmetry doc §5.3).

---

#### EXP-381: Time-Translation Invariance Quantification

**Hypothesis**: Meal glucose responses have cosine similarity > 0.7 regardless of
time-of-day, with Spearman r < 0.15 between time_diff and similarity.

**Method**: (From symmetry doc §4.1)
- Extract all isolated meal events (no other events within ±3h)
- Compute pairwise 6h glucose response cosine similarity
- Correlate similarity with absolute time-of-day difference

**Success Criterion**: Spearman r < 0.15

**Priority**: ★★ — Provides quantitative evidence for a principle we're already
exploiting (time feature removal). Negative result would indicate circadian
effects are stronger than expected at meal scale.

---

#### EXP-382: Kalman Filter ISF/CR State Tracking

**Hypothesis**: A Kalman filter tracking latent ISF and CR as hidden states
with daily TDD and mean glucose as observations achieves smoother drift
detection than rolling statistics, with lead time ≥1 week.

**Method**:
- State vector: [ISF, CR, basal_need]
- Process model: random walk with σ calibrated from EXP-312 drift rates
- Observation model: `expected_mean_BG = f(TDD, carbs, ISF, CR)`
- Run forward pass on all 11 patients
- Compare ISF trajectory smoothness and significance vs EXP-312 rolling

**Success Criterion**: ≥9/11 patients show significant drift (matching EXP-312)
with smoother trajectories (lower high-frequency jitter).

**Priority**: ★★ — Exploratory but high potential for clinical utility.
Kalman filter is the right formalism for slow-moving hidden physiological states.

---

#### EXP-383: Bayesian Hierarchical A1C Trajectory

**Hypothesis**: A Bayesian hierarchical model pooling across patients estimates
eA1C trajectory with narrower posterior intervals than per-patient models.

**Method**:
- Compute daily eA1C from rolling 30-day mean glucose
- Hierarchical model: patient intercepts + slopes + population trend
- Fit with PyMC or NumPyro
- Compare posterior width: hierarchical vs per-patient

**Success Criterion**: Posterior 95% interval width for eA1C slope ≤ 80% of
per-patient width.

**Priority**: ★★ — The right model for multi-month analysis. Demonstrates the
statistical approach needed when neural networks can't be trained.

---

#### EXP-384: Heteroscedastic Loss Weighted by Sensor Age

**Hypothesis**: Weighting forecast loss by inverse SAGE (newer sensors = higher
weight) improves late-sensor-life MAE by ≥0.5 mg/dL without hurting overall.

**Method**:
- Weight function: `w(t) = 1.0 + 0.5 × max(0, 1 - SAGE/240)`
- Apply to MSE loss: `loss = w × (y - ŷ)²`
- Evaluate MAE stratified by SAGE quartiles

**Success Criterion**: Q4 SAGE (oldest sensors) MAE improvement ≥ 0.5 mg/dL.

**Priority**: ★ — Low priority but tests an important principle for production
deployment where sensor quality varies.

---

## 6. Experiment Dependency Graph

```
                    ┌─────────────────────────────────┐
                    │  EXP-373: Multi-Seed Future PK   │ (validate breakthrough)
                    └─────────────┬───────────────────┘
                                  │
                    ┌─────────────▼───────────────────┐
                    │  EXP-369: ISF-Normalized Glucose │ (highest leverage)
                    └─────────────┬───────────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
    ┌─────────▼─────────┐ ┌──────▼──────────┐ ┌──────▼──────────┐
    │ EXP-370: Z-Score  │ │ EXP-371: Depth  │ │ EXP-372: Gluco- │
    │ Dual Channel      │ │ Hypo Feature    │ │ density Override │
    └─────────┬─────────┘ └──────┬──────────┘ └──────┬──────────┘
              │                   │                   │
              └───────────────────┼───────────────────┘
                                  │
         ┌────────────────────────┼────────────────────────┐
         │                        │                        │
  ┌──────▼──────────┐  ┌─────────▼─────────┐  ┌───────────▼─────────┐
  │ EXP-374: Cumul. │  │ EXP-375: Multi-   │  │ EXP-376: STL        │
  │ Load Features   │  │ Rate EMA          │  │ Decomposition       │
  └──────┬──────────┘  └─────────┬─────────┘  └───────────┬─────────┘
         │                        │                        │
         └────────────────────────┼────────────────────────┘
                                  │
                    ┌─────────────▼───────────────────┐
                    │ EXP-377: Hierarchical 12h→3d    │ (3-day scale)
                    └─────────────┬───────────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
    ┌─────────▼─────────┐ ┌──────▼──────────┐ ┌──────▼──────────┐
    │ EXP-378: Weekly   │ │ EXP-380: Absorp.│ │ EXP-381: Time   │
    │ Glucodensity      │ │ Symmetry        │ │ Invariance      │
    └─────────┬─────────┘ └──────┬──────────┘ └──────┬──────────┘
              │                   │                   │
              └───────────────────┼───────────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
    ┌─────────▼─────────┐ ┌──────▼──────────┐ ┌──────▼──────────┐
    │ EXP-382: Kalman   │ │ EXP-383: Bayes  │ │ EXP-384: Hetero │
    │ Filter ISF        │ │ Hierarchical    │ │ scedastic Loss  │
    └───────────────────┘ └─────────────────┘ └─────────────────┘
```

---

## 7. Summary of Key Recommendations

### Immediate Actions (Run This Week)

1. **EXP-373**: Validate future PK breakthrough with 5 seeds — this is the single
   most important finding to confirm (EXP-356: −10 mg/dL at h120)
2. **EXP-369**: ISF-normalized glucose — highest leverage normalization change
3. **EXP-371**: Functional depth as hypo feature — lowest cost, strong prior signal
4. **EXP-372**: Glucodensity at classifier head — proven signal, untried integration

### Near-Term (2–4 Weeks)

5. **EXP-370**: Z-score dual-channel for cross-patient work
6. **EXP-374**: Cumulative load features for 3-day scale (first multi-day experiment)
7. **EXP-377**: Hierarchical 12h→3d (tests the pipeline architecture concept)
8. **EXP-378**: Weekly glucodensity sequences

### Longer-Term (1–2 Months)

9. **EXP-376**: STL decomposition (enables clean separation for drift vs event detection)
10. **EXP-382**: Kalman filter ISF tracking (bridge to clinical decision support)
11. **EXP-383**: Bayesian hierarchical A1C (multi-month methodology)

### Techniques to Avoid

- Don't add more channels without more data (augmented 16ch consistently hurts)
- Don't use functional inner products as CNN input (zero temporal gradient)
- Don't use conservation regularization as formulated in EXP-362 (hurts)
- Don't smooth at 6h/12h scales (CNN already learns smoothing)
- Don't concatenate embeddings + CNN features (hurts classification)

---

## 8. Source File Index

| File | Role | Lines | Key Content |
|------|------|-------|-------------|
| `tools/cgmencode/continuous_pk.py` | PK feature computation | 1,015 | 8 PK channels, Hill equation, oref0 curves |
| `tools/cgmencode/real_data_adapter.py` | Data loading/normalization | 1,504 | 8/21/39-feature pipelines, multi-patient loading |
| `tools/cgmencode/fda_features.py` | FDA feature engineering | ~400 | B-spline, FPCA, glucodensity, depth |
| `tools/cgmencode/schema.py` | Normalization constants | ~250 | NORMALIZATION_SCALES, GLUCOSE_CLIP |
| `tools/cgmencode/run_pattern_experiments.py` | Multi-scale experiments | 7,502 | Scale configs, aligned loading, cross-scale |
| `tools/cgmencode/experiments_validated.py` | Validated classifiers | ~800 | EXP-336–347 with CIs |
| `tools/cgmencode/exp_pk_forecast_v2.py` | PK forecasting (Thread A) | ~800 | EXP-356–359, future PK projection |
| `tools/cgmencode/exp_pk_forecast_v3.py` | PK extensions (Thread A) | 1,463 | EXP-360–364, ISF norm, conservation, learned PK |
| `tools/cgmencode/exp_pk_forecast_v4.py` | Horizon-adaptive (Thread A) | 1,258 | EXP-365–368, ensemble, dilated TCN, ResNet |
| `tools/cgmencode/exp_arch_12h.py` | Architecture search (Thread B) | 577 | EXP-361, 6 archs × 2 feature sets at 12h |
| `tools/cgmencode/exp_transformer_features.py` | Transformer+features (Thread B) | 461 | EXP-362, transformer × feature variants |
| `tools/cgmencode/exp_normalization_conditioning.py` | **Next-phase runner** | ~TBD | EXP-369+, normalization/conditioning proposals |
| `tools/cgmencode/experiment_lib.py` | Shared ML infrastructure | 967 | Training loops, model creation, evaluation |
| `externals/experiments/` | Result JSONs | 368+ files | All experiment metrics and configurations |
