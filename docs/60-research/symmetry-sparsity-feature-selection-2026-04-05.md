# Symmetry, Sparsity, and Feature Selection in CGM/AID Intelligence

**Date**: 2026-04-05
**Context**: Synthesis of EXP-001–341 findings, FDA proposals, and multi-scale
architecture experiments. Addresses symmetries in physiological data, scale-dependent
feature importance, and the dense-CGM/sparse-treatment architectural challenge.

---

## 1. Feature Importance Is Scale-Dependent (Empirically Verified)

Our channel ablation experiments (EXP-287 at 2h, EXP-298 at 12h) provide definitive
evidence that **feature importance is not a fixed property — it's a function of
timescale and objective.**

### 1.1 Feature × Scale × Objective Matrix

| Feature | 2h Event Det | 12h Episode | 24h Drift | 7d Trend | Why |
|---------|-------------|-------------|-----------|----------|-----|
| **glucose** | Medium (ΔSil=-0.045) | **Critical** (ΔSil=-0.584) | Critical | Critical | The glucose trace IS the pattern at episode+ scales |
| **IOB** | Low (ΔSil=+0.090) | **Critical** (ΔSil=-0.564) | Important | Medium | Continuous effect channel; captures insulin action |
| **COB** | **Noise** (ΔSil=+0.178) | **Critical** (ΔSil=-0.456) | Important | Medium | Absorption arc meaningless at 2h, essential at 12h |
| **basal** | Important (ΔR@5=-1.12%) | Important (ΔSil=-0.296) | Medium | Low | Unique signal not captured by IOB/bolus |
| **bolus** | Low (ΔSil=+0.120) | **Noise** (ΔSil=+0.224) | Noise | Noise | Sparse spikes — worse than useless at 12h+ |
| **carbs** | Low (ΔSil=+0.089) | **#1** (ΔSil=-0.604) | Medium | Medium | Meal timing drives episode structure |
| **time_sin** | Neutral (ΔSil=+0.112) | **Hurts** (ΔSil=-0.526) | **Essential** | Important | Breaks time-translation symmetry |
| **time_cos** | Neutral (ΔSil=+0.120) | **Hurts** (ΔSil=-0.200) | **Essential** | Important | Same — circadian IS the daily pattern |

### 1.2 Recommended Feature Sets by Scale

**Fast (2h, 8ch)**: All channels. Small ablation deltas = high redundancy.

**Episode (12h, 5ch)**: glucose, IOB, COB, basal_rate, carbs.
- Drop bolus (sparse spike noise, ΔSil=+0.224)
- Drop time_sin/cos (patterns should be time-invariant, ΔR@5=+1.4%)

**Daily (24h, 8ch+profile)**: All 8ch + ISF/CR from profile (ch 32-33).
- Time features essential (circadian rhythm IS the pattern)
- Profile features are 4.4× more valuable than device features (EXP-261)

**Weekly (7d, 5ch)**: glucose, IOB, COB, basal, carbs at 1hr resolution.
- Drop bolus + time (same logic as episode; weekly pattern = trajectory shape)

### 1.3 The 39f Paradox

Adding features from 8→21→39 **hurts** without architectural change:
- 8f: MAE=11.56, gap=2.8% ✅
- 39f (no reg): MAE=17.06, gap=28.6% ❌
- 87% of transformer attention focuses on glucose alone (EXP-162)

**Resolution**: The problem is not "more features" — it's **which features for which
objective**. Profile features (ISF/CR) are critical for drift detection but noise for
UAM detection. The multi-scale pipeline naturally solves this by giving each objective
its own feature set.

---

## 2. Symmetries in CGM/AID Data

### 2.1 Time-Translation Invariance (Experimentally Confirmed)

**Observation**: A post-meal glucose spike at 8am and 8pm are physiologically
equivalent events. The metabolic response (carb absorption → glucose rise → insulin
action → glucose fall) follows the same trajectory regardless of clock time.

**Evidence**: EXP-298 shows that removing time encoding **improves** episode-scale
pattern matching by +1.4% recall and +0.224 silhouette. The model learns better
representations when it can't distinguish 8am from 8pm meals.

**Formalization**: If we denote a CGM trace as x(t) and a time-shifted version as
x(t + τ), then for episode classification:

```
f(x(t)) = f(x(t + τ))    ∀τ  (desired time-translation invariance)
```

This is broken by time_sin/cos features which encode absolute clock time.

**Exception — Circadian Scale**: At 24h+ windows, time-translation invariance
**should be broken** because circadian physiology creates real time-dependent effects:
- Dawn phenomenon (5am cortisol spike → insulin resistance)
- Evening insulin sensitivity changes
- Sleep/wake metabolic shifts

**Principle**: Symmetry should be respected at scales **below** the circadian period
(≤12h) and broken at scales **at or above** the circadian period (≥24h).

### 2.2 Absorption Envelope Symmetry (Hypothesized, Not Yet Tested)

**Hypothesis**: Carb and insulin absorption curves exhibit approximate **reflection
symmetry around their peak disturbance**. Specifically:

For an insulin bolus at t=0 with peak glucose-lowering effect at t=t_peak:
```
ΔBG(t_peak - δ) ≈ ΔBG(t_peak + δ)    for δ ∈ [0, t_peak]
```

The rising phase (absorption) and falling phase (clearance) should be approximately
mirror images, modulated by:
- Insulin type (rapid-acting: ~symmetric; long-acting: asymmetric)
- Injection site absorption variability
- Concurrent carb absorption (breaks symmetry)

For carb absorption (simpler model — linear decay in our codebase):
```
COB(t) = carbs × max(0, 1 - t/abs_time)    [linear, inherently asymmetric]
```
The glucose RESPONSE to carbs is closer to symmetric: rise (absorption) then fall
(insulin-mediated clearance), with peak at ~60-90 minutes.

**Why this matters**: If absorption envelopes are approximately symmetric, then:
1. The model needs to see BOTH sides of the peak to understand the event (minimum
   window = 2 × time_to_peak, explaining the 4-8h valley in EXP-289)
2. We could regularize models to produce symmetric response predictions
3. FDA's phase-amplitude decomposition (F-FDA-5) could separate the symmetric
   response shape from its time-warped alignment

**The DIA Valley as Symmetry Evidence**: The U-shaped window performance curve
(EXP-289) provides indirect evidence:

| Window | Silhouette | Interpretation |
|--------|-----------|---------------|
| 2h | -0.367 | Sees onset only — one side of symmetry |
| 4h | -0.537 | Sees onset + peak — no resolution context |
| 6h (DIA) | -0.544 | Sees peak + partial resolution — asymmetric view |
| 8h | -0.642 | Worst — overlapping incomplete envelopes |
| **12h** | **-0.339** | **Best** — sees full rise + peak + resolution = complete envelope |

The model performs best when it can see the **complete symmetric arc**: pre-event
baseline → disturbance rise → peak → resolution → return to baseline.

### 2.3 Glucose Conservation Under Insulin/Carb Balance

**Hypothesis**: In steady-state, the integral of glucose deviation from baseline
is approximately conserved:

```
∫ (BG(t) - BG_baseline) dt ≈ carbs × absorption_factor - insulin × ISF
```

This is essentially what the physics model (`physics_model.py`) implements:
```python
delta_iob = window_raw_iob[t-1] - window_raw_iob[t]
delta_cob = window_raw_cob[t-1] - window_raw_cob[t]
insulin_effect = -delta_iob * isf
carb_effect = delta_cob * (isf / cr)
pred[t] = pred[t-1] + insulin_effect + carb_effect
```

**Implication**: The neural network's residual (actual - physics_predicted) should
integrate to approximately zero over a full absorption cycle. This is a testable
conservation constraint that could be used as a regularizer.

### 2.4 Patient-Relative Symmetry (Scaling Equivariance)

**Observation**: Patient A with ISF=40 and Patient B with ISF=80 respond to the same
bolus with glucose drops of 40 mg/dL and 80 mg/dL respectively. The *shape* of the
response is identical; only the *amplitude* differs.

**Formalization**: If we denote ISF-normalized glucose as:
```
BG_normalized(t) = BG(t) / ISF
```
then the response curves should be equivariant under ISF scaling.

**Current approach**: We normalize glucose by /400 (fixed), not by ISF (patient-specific).
This means the model must learn ISF-dependent response magnitudes for each patient.

**Potential improvement**: ISF-normalized glucose as an input feature (or ISF as a
conditioning signal) could improve cross-patient generalization. Profile features
(ch 32-33: scheduled_isf, scheduled_cr) partially address this but as auxiliary
channels rather than as a normalization basis.

---

## 3. The Sparse/Dense Problem and Proposed Solutions

### 3.1 The Problem

| Signal | Density | Points/day | Character |
|--------|---------|------------|-----------|
| CGM glucose | Dense | 288 (every 5 min) | Continuous, smooth |
| IOB (derived) | Dense | 288 (computed from bolus+DIA) | Continuous, smooth (decay curve) |
| COB (derived) | Dense | 288 (computed from carbs+abs_time) | Continuous, smooth (linear decay) |
| Basal rate | Semi-sparse | 24-48 (changes ~hourly) | Step function |
| Bolus events | **Sparse** | 3-8 per day | Point impulses |
| Carb entries | **Sparse** | 3-5 per day | Point impulses |

In a 12h window (144 timesteps), a single bolus event occupies **1/144 = 0.7%** of
the temporal extent. This creates a massive density mismatch: the model sees 144
glucose values but only 1-3 bolus spikes.

### 3.2 Current Approach: Sparse → Dense Conversion

The codebase already converts sparse events to dense signals:
- **Bolus → IOB**: Exponential decay with DIA half-life (`real_data_adapter.py:83-103`)
- **Carbs → COB**: Linear decay over absorption time (`real_data_adapter.py:106-124`)

This is effective because IOB/COB carry the *continuous metabolic effect* of the
sparse event. EXP-298 confirms: removing bolus (sparse) IMPROVES 12h clustering
by +0.224, while removing IOB (dense) DESTROYS it at -0.564.

**The existing approach already partially solves the sparsity problem.** The question
is whether we can do better.

### 3.3 Proposed Solutions (Building on Existing Work)

#### Solution A: Absorption Envelope Features (FDA-Inspired)

Instead of raw IOB/COB decay curves, compute **functional features of the
absorption process**:

```
For each bolus event at t_bolus:
  1. Extract glucose[t_bolus - 1h : t_bolus + 5h]  (the response window)
  2. Fit B-spline to glucose response
  3. Compute:
     - t_nadir: time of maximum glucose drop
     - amplitude: |BG(t_nadir) - BG(t_bolus)|
     - symmetry_ratio: area_before_nadir / area_after_nadir
     - ISF_effective: amplitude / bolus_size
     - recovery_time: time from nadir to return to within 10% of baseline
```

These features are **dense in information** (one rich vector per bolus event) even
though they come from sparse events. They can be appended as auxiliary features
to the windows containing those events.

**Relationship to EXP-309**: This is essentially what ISF_effective computes, but
only for the glucose-lowering aspect. Extending to symmetric rise+fall analysis
would capture absorption dynamics more completely.

#### Solution B: Event-Conditional Encoding

Treat sparse treatment events as **conditions** rather than channels:

```
Instead of: [glucose, IOB, COB, basal, bolus, carbs, time_sin, time_cos]
                                        ↑sparse  ↑sparse

Use:        [glucose, IOB, COB, basal, time_sin, time_cos]  (dense channels)
            + event_type_embedding(bolus_size, carb_amount, time_since_last)
```

The event embedding becomes a conditioning vector (like FiLM conditioning in vision)
that modulates the dense-channel processing. This separates the two data regimes:
- Dense channels processed by convolution/attention (temporal structure)
- Sparse events processed by embedding (categorical/magnitude information)

This is architecturally similar to how language models handle rare tokens — you don't
need the token at every position, just its embedding when it appears.

#### Solution C: FDA Curve Registration for Sparse Events

Use **curve registration** (FDA concept F-FDA-5) to time-warp glucose traces so that
meal/bolus events are **aligned to a canonical time**:

```
Raw:       Patient A meal at t=47, Patient B meal at t=12, Patient C meal at t=98
Registered: All meals aligned to t=0, glucose traces warped accordingly
```

After registration, the model sees glucose responses to meals aligned in time,
removing the temporal sparsity problem entirely. The **warping function itself**
becomes a feature (encoding when events happened).

**Advantage**: Naturally captures the absorption envelope symmetry — after registration,
you can directly compare the pre-peak and post-peak phases across patients and events.

**Challenge**: Requires reliable event detection as a preprocessing step. For bolus
events (logged by pump), this is trivial. For unannounced meals (the UAM problem),
this becomes circular.

#### Solution D: Multi-Resolution Temporal Encoding

Process the same window at **multiple temporal resolutions** simultaneously:

```
Channel group 1 (glucose): 5-min resolution, full 144 steps
Channel group 2 (IOB/COB): 15-min resolution, 48 steps (smooth signals don't need 5-min)
Channel group 3 (bolus/carbs): Event-level, variable-length sequence of (time, magnitude)
```

Each group uses the architecture best suited to its data character:
- Dense glucose → 1D-CNN (proven best, EXP-313)
- Smooth IOB/COB → Downsampled CNN or FDA B-spline coefficients
- Sparse events → Set encoder or attention over event sequence

Outputs are fused after per-group processing, similar to the failed GroupedEncoder
(EXP-162) but with the critical difference that **each group uses different temporal
resolution** rather than just different projection matrices.

---

## 4. Evaluating Symmetry Properties (Proposed Methods)

### 4.1 Time-Translation Invariance Test

**Method**: For each pair of similar events (e.g., two 50g meals) at different times
of day, compute the cosine similarity of their glucose response curves.

```python
def time_translation_test(events, glucose_traces):
    """Test if similar events produce similar responses regardless of time."""
    similarities = []
    for (e1, e2) in same_type_pairs(events):
        response1 = glucose_traces[e1.start : e1.start + 6h]
        response2 = glucose_traces[e2.start : e2.start + 6h]
        sim = cosine_similarity(response1, response2)
        time_diff = abs(e1.hour_of_day - e2.hour_of_day)
        similarities.append((time_diff, sim))
    # If time-invariant: sim should NOT correlate with time_diff
    return spearman_correlation(time_diffs, similarities)
```

**Expected**: Low correlation → time-translation invariance holds for meal responses.
High correlation → circadian effects create genuine time-dependence.

**Null hypothesis**: r < 0.15 (weak or no correlation between time difference and
response similarity).

### 4.2 Absorption Symmetry Test

**Method**: For each isolated bolus or carb event, measure the symmetry of the
glucose response around its peak/nadir:

```python
def absorption_symmetry_test(events, glucose_traces):
    """Test if glucose response is symmetric around peak disturbance."""
    ratios = []
    for event in isolated_events(events):  # no overlapping events within ±3h
        response = glucose_traces[event.start - 1h : event.start + 5h]
        peak_idx = argmax(abs(response - response[0]))  # peak disturbance
        pre_peak = response[:peak_idx]
        post_peak = response[peak_idx:]
        # Measure asymmetry
        if len(pre_peak) > 0 and len(post_peak) > 0:
            pre_area = trapz(abs(pre_peak - pre_peak[0]))
            post_area = trapz(abs(post_peak - post_peak[-1]))
            ratio = pre_area / (post_area + 1e-8)
            ratios.append(ratio)
    # ratio ≈ 1.0 → symmetric; ratio >> 1 → fast rise, slow recovery
    return np.mean(ratios), np.std(ratios)
```

**Expected**: Insulin responses approximately symmetric (ratio ~0.8-1.2) due to
exponential decay pharmacokinetics. Carb responses asymmetric (ratio ~0.5-0.8) due
to faster absorption than resolution.

### 4.3 Conservation Test

**Method**: Over complete absorption cycles, test whether the integral of glucose
deviation is predicted by the physics model:

```python
def conservation_test(windows, physics_predictions):
    """Test if glucose integral is conserved under insulin/carb balance."""
    residual_integrals = []
    for w, p in zip(windows, physics_predictions):
        glucose_actual = w[:, IDX_GLUCOSE] * 400  # denormalize
        glucose_physics = p * 400
        residual = glucose_actual - glucose_physics
        integral = trapz(residual)  # should be ~0 if physics captures dynamics
        residual_integrals.append(integral)
    # Near-zero mean → conservation holds; large variance → unmodeled effects
    return np.mean(residual_integrals), np.std(residual_integrals)
```

### 4.4 ISF Scaling Equivariance Test

**Method**: Test whether ISF-normalized glucose responses are more similar across
patients than raw glucose responses:

```python
def isf_equivariance_test(patients):
    """Test if ISF normalization improves cross-patient similarity."""
    raw_sims, norm_sims = [], []
    for (p1, p2) in patient_pairs(patients):
        for (e1, e2) in matched_events(p1, p2):  # similar bolus sizes
            raw_sim = cosine_similarity(e1.glucose_response, e2.glucose_response)
            norm_sim = cosine_similarity(
                e1.glucose_response / p1.isf,
                e2.glucose_response / p2.isf
            )
            raw_sims.append(raw_sim)
            norm_sims.append(norm_sim)
    # If equivariant: norm_sims should be higher than raw_sims
    return np.mean(norm_sims) - np.mean(raw_sims)  # positive = equivariance helps
```

---

## 5. Unified Hypothesis: Symmetry-Aware Multi-Scale Architecture

### 5.1 The Central Insight

Combining our experimental evidence and symmetry analysis, the strongest hypothesis is:

> **Each timescale has a natural symmetry group that should be respected by the
> architecture and broken only when physiologically justified.**

| Scale | Symmetry | Should Respect | Should Break |
|-------|----------|---------------|-------------|
| 2h (Fast) | Time-translation | Meals at any hour are meals | — |
| 12h (Episode) | Time-translation + absorption reflection | Full absorption arcs match | Overlapping events break symmetry |
| 24h (Daily) | Absorption reflection | Within-day arcs | **Circadian** (dawn phenomenon, evening sensitivity) |
| 7d (Weekly) | Time-translation (day of week irrelevant) | Weekly patterns | **Weekday vs weekend** (behavior shifts) |

### 5.2 Proposed Architecture: Symmetry-Respecting Multi-Scale Pipeline

```
                    ┌─────────────────────────────────────────────┐
                    │           Sparse Event Encoder              │
                    │  (bolus, carbs → event embeddings)          │
                    │  Input: [(t, dose, type), ...] variable-len │
                    │  Output: 16D event context vector           │
                    └─────────────┬───────────────────────────────┘
                                  │ (conditioning signal)
                                  ▼
┌──────────────┐   ┌──────────────────────────────┐   ┌────────────────┐
│ Dense Signals │──▶│    Scale-Specific Encoder     │──▶│   Objective    │
│ glucose, IOB, │   │                              │   │   Head         │
│ COB, basal    │   │ Fast (2h): 1D-CNN, 6ch       │   │ Event F1      │
│               │   │   → time-invariant (no time)  │   │               │
│               │   │ Episode (12h): CNN, 5ch       │   │ Silhouette    │
│               │   │   → time-invariant, no bolus  │   │               │
│               │   │ Daily (24h): FDA + CNN, 8ch   │   │ Drift F1      │
│               │   │   → circadian-aware           │   │               │
│               │   │ Weekly (7d): GRU, 5ch         │   │ Trend R@K     │
│               │   │   → time-invariant            │   │               │
│               │   └──────────────────────────────┘   └────────────────┘
└──────────────┘
```

Key design decisions:
1. **Sparse events are NEVER raw channels** at episode+ scale — always encoded
   as conditioning signals or absorbed into IOB/COB
2. **Time features included/excluded based on scale-specific symmetry**
3. **Each scale-objective pair gets its own feature set** (not universal features)
4. **FDA encoding used for smooth/continuous signals** (B-spline for glucose,
   glucodensity for daily distributions)

### 5.3 Absorption-Aware Regularization

**New loss term**: Encourage the model to produce symmetric absorption predictions:

```python
def absorption_symmetry_loss(predicted_glucose, event_times, alpha=0.1):
    """Regularize for symmetric glucose response around peak disturbance."""
    loss = 0.0
    for t_event in event_times:
        window = predicted_glucose[t_event - 12 : t_event + 60]  # -1h to +5h
        if len(window) < 72:
            continue
        peak_idx = torch.argmax(torch.abs(window - window[0]))
        pre = window[:peak_idx]
        post = window[peak_idx:peak_idx + len(pre)]
        if len(post) == len(pre) and len(pre) > 0:
            # Encourage pre-peak ≈ reverse of post-peak (shape symmetry)
            loss += F.mse_loss(pre, post.flip(0))
    return alpha * loss
```

### 5.4 Sparse Event Encoding via Set Transformer

Replace raw bolus/carbs channels with a learned encoding of the event sequence:

```python
class SparseEventEncoder(nn.Module):
    """Encode variable-length sparse events into fixed-size context."""
    def __init__(self, event_dim=4, hidden=32, out_dim=16):
        super().__init__()
        # event_dim: (time_relative, magnitude, type_embed, iob_at_event)
        self.event_proj = nn.Linear(event_dim, hidden)
        self.attention = nn.MultiheadAttention(hidden, num_heads=4)
        self.out_proj = nn.Linear(hidden, out_dim)

    def forward(self, events, mask):
        # events: (batch, max_events, event_dim), mask: (batch, max_events)
        x = self.event_proj(events)  # (B, E, H)
        x = x.permute(1, 0, 2)      # (E, B, H)
        x, _ = self.attention(x, x, x, key_padding_mask=~mask)
        x = x.mean(dim=0)           # pool over events → (B, H)
        return self.out_proj(x)      # (B, out_dim)
```

This encodes 3-8 daily events into a 16D vector that captures:
- Total insulin/carb load
- Temporal distribution of events
- Event-event interactions (e.g., correction bolus after meal)

### 5.5 FDA + Symmetry Integration

**B-spline absorption decomposition**:

For each 12h window containing a bolus+meal:
1. Fit B-spline to glucose trace (noise-robust continuous representation)
2. Compute 1st derivative (functional velocity) — zero crossing = peak
3. Compute area under curve before and after peak (symmetry ratio)
4. Use FPCA to decompose the symmetric component vs asymmetric residual

```python
def decompose_absorption_symmetry(glucose_fd, event_time):
    """Decompose glucose response into symmetric + asymmetric components."""
    deriv = glucose_fd.derivative()
    # Find peak (zero crossing of derivative near event)
    grid = deriv.grid_points[0]
    deriv_vals = deriv.data_matrix[0, :, 0]
    peak_idx = find_zero_crossing(deriv_vals, near=event_time)

    # Extract pre-peak and post-peak
    pre = glucose_fd.data_matrix[0, :peak_idx, 0]
    post = glucose_fd.data_matrix[0, peak_idx:, 0]

    # Symmetric component: average of forward and time-reversed
    min_len = min(len(pre), len(post))
    symmetric = (pre[-min_len:] + post[:min_len][::-1]) / 2
    asymmetric = glucose_fd.data_matrix[0, :, 0] - symmetric_padded

    return symmetric, asymmetric
```

The **symmetric component** captures the expected pharmacokinetic response.
The **asymmetric residual** captures what's physiologically interesting:
concurrent events, exercise, stress, sensor artifacts.

---

## 6. Concrete Experiment Proposals

### EXP-342: Time-Translation Invariance Quantification

**Hypothesis**: Meal glucose responses have cosine similarity > 0.7 regardless of
time-of-day, confirming time-translation invariance at episode scale.

**Method**: Extract all isolated meal events (no other events within ±3h), compute
pairwise response similarity as a function of time-of-day difference.

**Success**: Spearman r < 0.15 between time_diff and similarity.

### EXP-343: Absorption Envelope Symmetry Analysis

**Hypothesis**: Insulin bolus glucose responses have symmetry ratio 0.7-1.3 around
nadir, while carb responses are more asymmetric (ratio 0.4-0.8).

**Method**: For each isolated bolus/carb event, compute pre-peak/post-peak area ratio.

**Success**: Distinct distributions for insulin vs carb symmetry; insulin ratio
closer to 1.0.

### EXP-344: Sparse Event Encoder vs Raw Channels

**Hypothesis**: Replacing raw bolus/carbs channels with a Set Transformer event
encoder improves 12h episode silhouette by ≥0.1.

**Method**: Train episode-scale pattern encoder with:
- Baseline: 5ch (glucose, IOB, COB, basal, carbs)
- Test: 4ch (glucose, IOB, COB, basal) + 16D event encoder conditioning

**Success**: Silhouette improvement ≥ 0.1 (from -0.339 baseline).

### EXP-345: ISF-Normalized Glucose for Cross-Patient Generalization

**Hypothesis**: Using BG/ISF as the glucose channel (instead of BG/400) reduces
LOO generalization gap by ≥1%.

**Method**: Rerun EXP-326 (LOO validation) with ISF-normalized glucose.

**Success**: LOO F1 gap < 2% (vs current 2.9% override, 4.0% hypo).

### EXP-346: Conservation Regularization

**Hypothesis**: Adding a loss term that penalizes non-zero integral of
(predicted - physics_predicted) residuals over complete absorption cycles improves
forecast MAE by ≥0.3 mg/dL.

**Method**: Augment forecast loss with:
`L_total = L_mse + 0.1 × |∫ residual dt|²`

**Success**: MAE improvement ≥ 0.3 mg/dL (from 11.14 baseline).

### EXP-347: FDA Curve Registration for Meal Response Library

**Hypothesis**: Time-warping glucose traces to align meal events produces a pattern
library with silhouette > 0.0 (vs current -0.339 unregistered).

**Method**: Use scikit-fda's elastic registration to align meal events, then cluster
in registered space.

**Success**: Positive silhouette score in registered space.

---

## 7. Summary of Actionable Insights

1. **Feature selection is solved**: Use the empirically-validated feature sets per
   scale (§1.2). Don't search for universal features.

2. **Time-translation invariance is real**: Drop time features at ≤12h, keep at ≥24h.
   This is the simplest symmetry to exploit and is already confirmed by EXP-298.

3. **The DIA valley proves absorption symmetry matters**: The U-shaped performance
   curve (EXP-289) shows models need complete absorption envelopes. Window size should
   be ≥ 2 × max(DIA, carb_absorption_time) for pattern tasks.

4. **Sparse events should be encoded, not channelized**: At episode+ scales, replace
   raw bolus/carbs with set-encoded event embeddings or lean entirely on IOB/COB
   effect channels. This addresses the density mismatch architecturally.

5. **ISF normalization could improve cross-patient transfer**: The scaling equivariance
   hypothesis (§2.4) predicts that ISF-normalized glucose reduces the generalization
   gap. Profile features (ch 32-33) are a partial solution; explicit normalization
   is cleaner.

6. **FDA tools are ready for symmetry analysis**: B-spline decomposition, functional
   derivatives, and curve registration can quantify absorption symmetry and time-
   translation invariance. The toolchain (fda_features.py) is implemented.

7. **Conservation constraints are low-hanging fruit**: The physics model already
   predicts glucose from IOB/COB changes. Regularizing the neural residual to have
   zero integral over absorption cycles is a simple, physics-motivated loss term.
