# Strategic Exploration Map: Frontiers in Glucose Forecasting

**Date**: 2026-04-07  
**Context**: 410 experiments (EXP-001 through EXP-410), 11 real-world patients  
**Predecessors**:
- [diabetes-domain-learnings-2026-04-06.md](diabetes-domain-learnings-2026-04-06.md)
- [evidence-synthesis-normalization-long-horizon-2026-04-06.md](evidence-synthesis-normalization-long-horizon-2026-04-06.md)
- [gap-closing-report-2026-04-07.md](gap-closing-report-2026-04-07.md)

---

## Part 1: What We Know — A Unified Theory of Glucose Forecasting

### The Causal Structure of Blood Glucose

Through 410 experiments, we've empirically mapped the causal hierarchy:

```
                        ┌─────────────────┐
                        │  Glucose @ t+h  │
                        └────────┬────────┘
                    ┌────────────┼────────────┐
                    ▼            ▼             ▼
              ┌──────────┐ ┌─────────┐ ┌──────────────┐
              │ Glucose   │ │ Insulin │ │ Unmeasured   │
              │ Momentum  │ │ PK      │ │ Physiology   │
              │ (87%)     │ │ (~8%)   │ │ (~5%)        │
              └──────────┘ └─────────┘ └──────────────┘
                  ▲            ▲              ▲
              Past CGM    Pump data      EGP, exercise,
              trend       (IOB, bolus,   stress, hormones,
                          carbs, basal)  circadian rhythm
```

At short horizons (≤30 min), glucose momentum dominates — the best predictor
of glucose in 30 minutes is recent glucose trend. At longer horizons (≥2h),
insulin and carb absorption become the primary drivers of glucose direction.
At very long horizons (≥6h), unmeasured physiological factors (hepatic glucose
production, circadian rhythms, meal timing patterns) become significant.

### The Three Horizons of Forecasting

Our experiments reveal three distinct forecasting regimes, each with different
optimal strategies:

| Regime | Horizon | Dominant Signal | Best Approach | Current MAE |
|--------|---------|----------------|---------------|:-----------:|
| **Momentum** | h5–h30 | CGM trend | Any architecture works | **~6–10 mg/dL** |
| **PK-driven** | h30–h120 | Insulin/carb absorption | Transformer + PK channels | **~10–16 mg/dL** |
| **Physiological** | h120–h720 | EGP, circadian, patterns | Future PK + CNN/Transformer | **~38–50 mg/dL** |

Each regime has different data requirements, feature importance, and model
architecture preferences. **Optimizing for one regime may harm another**.
Multi-horizon loss helps within-regime but across-regime, specialized models
may be needed.

### The Big Testable Theories

From our experimental evidence, five overarching theories have emerged:

#### Theory 1: Dense Equivariant Representations Win ✅ CONFIRMED

**Evidence**: EXP-349 (no_time beats time features), EXP-352-356 (PK channels
outperform sparse bolus/carbs), EXP-410 (PK transformer matches ERA 2).

**Principle**: Signals should be dense (every timestep non-zero) and
equivariant (same physical meaning regardless of when they occur). Sparse
event indicators (bolus=0 except at injection time) force the model to learn
temporal alignment from scratch. Continuous absorption curves encode the same
information as a dense, smooth function that CNNs and transformers can easily
process.

**Status**: Fully validated for insulin and carbs. **Untested** for:
- Glucose derivatives as explicit channels (rather than implicit)
- Multi-rate moving averages as additional channels
- ISF-normalized derivative channels

#### Theory 2: Future PK Projection Is Causally Valid ✅ CONFIRMED

**Evidence**: EXP-356 breakthrough (−10 mg/dL at h120), EXP-366 (−17.5 mg/dL
with dilated TCN).

**Principle**: Insulin and carb absorption in the future are deterministic
consequences of past events — there is no information leakage. If someone
took 5 units of insulin 30 minutes ago, we KNOW with certainty that ~3.8 units
are still being absorbed 90 minutes from now. This is physically different from
"predicting the future" — it's projecting a known decay process.

**Status**: Validated for CNN architectures at w48 (h120-h720). **Untested** for:
- PKGroupedEncoder transformer with future PK (should be a high-value experiment)
- Horizon-specific future PK masking (progressively less certain at longer horizons)
- Stochastic future PK (add noise to future channels reflecting meal uncertainty)

#### Theory 3: Architecture + Features Must Be Co-Optimized ✅ CONFIRMED

**Evidence**: ERA 2 (good arch + sparse features = 10.59), ERA 3 (good features
+ poor arch = 24.4), ERA 3.5 (both = **10.42**).

**Principle**: Neither features nor architecture alone can compensate for the
other. The GroupedEncoder's feature-group projections need dense signals to
form meaningful internal representations. CNNs with dense PK features couldn't
match transformers because attention captures long-range dependencies that
convolution kernels miss at standard depths.

**Status**: Validated at w24/h60. **Untested** for:
- Longer windows (w48, w96) where architecture matters more
- Deeper transformers (6-8 layers) with PK channels
- Hybrid CNN-encoder + Transformer-decoder architectures

#### Theory 4: ISF Normalization Reduces Inter-Patient Variability ✅ CONFIRMED

**Evidence**: EXP-361 (ISF-norm −1.2 MAE), EXP-407 (ISF ablation), EXP-410
(ISF-scaled patients more consistent). Easy patients (ISF 21-40) have MAE
6-9; hard patients (ISF 77-94) have MAE 12-17. ISF-scaling collapses this gap.

**Principle**: The insulin sensitivity factor (ISF) scales the glucose response
to insulin. Patient k (ISF=25) drops 25 mg/dL per unit; patient b (ISF=94) drops
94 mg/dL. Normalizing glucose by ISF makes the "insulin dose → glucose change"
relationship approximately patient-independent, so the model learns universal
pharmacokinetics rather than patient-specific scales.

**Status**: Validated for simple scaling. **Untested** for:
- Dynamic ISF that adapts with circadian rhythm (higher at dawn, lower at night)
- ISF-normalized loss function (weight errors by 1/ISF)
- ISF drift compensation (biweekly adaptation per EXP-312)

#### Theory 5: The DIA Valley Constrains Minimum Window Size ⚠️ PARTIALLY CONFIRMED

**Evidence**: EXP-289 (U-curve in pattern quality), EXP-353 (PK crossover at 4h),
EXP-376 (6h > 9h > 12h for forecasting). DIA = 5-6h means windows must see at
least one complete absorption arc.

**Principle**: Windows shorter than DIA capture only partial absorption curves —
either the rising or falling limb, never both. This prevents the model from
learning the full insulin → glucose causal pathway.

**Status**: Confirmed for classification and CNN forecasting. **NOT YET TESTED**
for transformer forecasting:
- Can the transformer's attention mechanism partially compensate for short windows
  by attending to the right part of the absorption arc?
- Does w48 (2h history) PKGroupedEncoder beat w24 (1h) if we add future PK?
  (EXP-409 found w48 beats w24 for h60 without future PK)

---

## Part 2: Explored vs. Unexplored Territory

### Territory Map

```
                    EXPLORED                          UNEXPLORED
                    (strong evidence)                 (hypothesis stage)

  ┌─────────────────────────────┐     ┌──────────────────────────────┐
  │ FEATURES                    │     │ FEATURES                     │
  │ ✅ Dense PK channels        │     │ ❓ Glucose 1st/2nd derivatives│
  │ ✅ ISF normalization        │     │ ❓ Multi-rate EMA channels    │
  │ ✅ Future PK projection     │     │ ❓ Stochastic future PK      │
  │ ✅ Time features (hurt ≤12h)│     │ ❓ ISF-normalized derivatives │
  │ ✅ Sparse channels (hurt)   │     │ ❓ Hepatic glucose prod. est. │
  │ ❌ Functional inner products│     │ ❓ Dawn/dusk binary indicator │
  │ ❌ Conservation regularize  │     │ ❓ Meal pattern embeddings    │
  └─────────────────────────────┘     └──────────────────────────────┘

  ┌─────────────────────────────┐     ┌──────────────────────────────┐
  │ ARCHITECTURES               │     │ ARCHITECTURES                │
  │ ✅ GroupedEncoder (best)     │     │ ❓ Encoder-decoder transformer│
  │ ✅ ResNet + future PK       │     │ ❓ Patched time series (PatchTST)│
  │ ✅ Dual-encoder CNN         │     │ ❓ Mamba / state-space models │
  │ ✅ Dilated TCN              │     │ ❓ Graph neural networks      │
  │ ❌ VAE / diffusion          │     │ ❓ Mixture of experts (MoE)   │
  │ ❌ State-transfer LSTM      │     │ ❓ Regime-switching models    │
  └─────────────────────────────┘     └──────────────────────────────┘

  ┌─────────────────────────────┐     ┌──────────────────────────────┐
  │ TRAINING                    │     │ TRAINING                     │
  │ ✅ Multi-horizon loss       │     │ ❓ Curriculum (short→long)    │
  │ ✅ Per-patient fine-tuning  │     │ ❓ Cosine LR with warmup     │
  │ ✅ 5-seed ensemble          │     │ ❓ Knowledge distillation     │
  │ ✅ Early stopping + LR decay│     │ ❓ Meta-learning (MAML)       │
  │ ❌ SWA (not on champion)    │     │ ❓ Horizon-weighted loss      │
  │ ❌ Data augmentation (CNN)  │     │ ❓ Adversarial training       │
  └─────────────────────────────┘     └──────────────────────────────┘

  ┌─────────────────────────────┐     ┌──────────────────────────────┐
  │ EVALUATION                  │     │ EVALUATION                   │
  │ ✅ h5-h60 (well validated)  │     │ ❓ h120-h360 (PK territory)  │
  │ ✅ 11-patient cross-val     │     │ ❓ Temporal generalization    │
  │ ✅ ISO 15197 compliance     │     │ ❓ Real-time deployment test  │
  │ ✅ Per-patient breakdown    │     │ ❓ Robustness to sensor noise │
  └─────────────────────────────┘     └──────────────────────────────┘
```

### Explored Territory: Confidence Levels

| Area | Experiments | Finding | Confidence |
|------|:-----------:|---------|:----------:|
| Dense PK > sparse | 352-356, 405-410 | Always better | 🟢 Very High |
| Transformer > CNN for forecast | 399-408 | −44% MAE improvement | 🟢 Very High |
| Future PK projection | 355-356, 366 | −10 to −17 mg/dL | 🟢 Very High |
| ISF normalization helps | 361, 407, 410 | −0.5 to −1.2 MAE | 🟡 High |
| Multi-horizon > single-horizon | 409 | h60-only hurts h60 | 🟡 High |
| More params hurt at scale | 369-372, 409 | Consistent | 🟡 High |
| Per-patient FT essential | 402, 408, 410 | −0.9 to −2 MAE | 🟢 Very High |
| w24 best for h60 evaluation | 409-410 | Protocol-dependent | 🟡 Medium |
| Data augmentation hurts | 390-394 | CNN/ResNet only | 🟠 Medium-Low |
| PK helps most at h120+ | 353, 356 | Crossover at 4h | 🟡 High |

### Unexplored Territory: Prioritized by Expected Impact

#### Tier 1: High Expected Impact, Low Risk (Do These Next)

1. **🔬 Future PK on PKGroupedEncoder (w48)**
   - **What**: Add future PK projection (EXP-356's breakthrough) to the
     now-proven PKGroupedEncoder transformer
   - **Why**: Future PK gave −10 to −17 mg/dL with CNN. Transformer should
     be even better at exploiting projected absorption state.
   - **Expected impact**: −3 to −8 mg/dL at h120, potentially matching or
     beating ERA 2 at extended horizons
   - **Effort**: Low — concatenate PK channels into future timesteps
   - **Risk**: Low — both components proven independently

2. **🔬 Extended history for extended horizons (w48, w72, w96)**
   - **What**: Test PKGroupedEncoder at 2h/3h/4h history for h120-h360 targets
   - **Why**: Theory 5 (DIA Valley) predicts that longer history captures
     complete absorption arcs. EXP-353 showed PK crossover at ≥4h with CNN.
     Transformer's attention can selectively focus on relevant parts of
     longer history without the curse of diluted gradients.
   - **Expected impact**: −2 to −5 mg/dL at h120+, but may hurt h30 slightly
   - **Effort**: Low — change window_size parameter
   - **Risk**: Low-medium — data volume changes with window size

3. **🔬 Glucose derivative channels**
   - **What**: Add explicit dBG/dt and d²BG/dt² as input channels
   - **Why**: Rate of change is the most informative glucose feature after
     absolute value (EXP-358: glucose_roc −0.4 MAE). Currently the model
     must learn to compute derivatives internally. Providing them explicitly
     frees model capacity for higher-order reasoning.
   - **Expected impact**: −0.5 to −1.5 mg/dL (modest but compound-able)
   - **Effort**: Very low — already computed in PK features
   - **Risk**: Very low — easily ablated

4. **🔬 Per-patient hard case optimization**
   - **What**: Longer FT (50-100ep), data augmentation, patient-specific
     hyperparameters for patients b (17.1), j (15.2), a (13.3)
   - **Why**: These 3 patients account for 42% of total error. Patient j
     has 0% IOB data — may benefit from glucose-only features. Patient b
     has ISF=94 — may need stronger ISF normalization.
   - **Expected impact**: −1 to −3 MAE for these patients → −0.3 to −1 overall
   - **Effort**: Medium — requires per-patient experimentation
   - **Risk**: Low — FT is safe, won't harm other patients

#### Tier 2: Medium Expected Impact, Medium Risk

5. **🔬 Horizon-weighted loss function**
   - **What**: Weight loss by 1/horizon or learned weights per horizon
   - **Why**: Equal weighting means h5 (easy, MAE ~6) contributes as much
     gradient as h60 (hard, MAE ~15). Weighting toward harder horizons should
     improve long-range accuracy without degrading short-range much.
   - **Expected impact**: −0.5 to −2 mg/dL at h60
   - **Effort**: Low — simple loss weight change
   - **Risk**: Medium — may hurt h30 performance

6. **🔬 Dynamic ISF normalization**
   - **What**: ISF that varies by time-of-day (dawn: ISF×0.8, evening: ISF×1.2)
   - **Why**: ISF drift is real (9/11 patients, EXP-312). Circadian patterns
     mean insulin works differently at 3am vs 3pm. Static ISF normalization
     leaves this signal for the model to learn from scratch.
   - **Expected impact**: −0.5 to −1 MAE (specifically for dawn/dusk periods)
   - **Effort**: Medium — requires circadian ISF estimation
   - **Risk**: Medium — bad ISF estimates could add noise

7. **🔬 Cosine LR with warmup**
   - **What**: Replace step-decay LR with cosine annealing + linear warmup
   - **Why**: Current LR schedule (1e-3, halve on plateau) is generic. Cosine
     annealing is proven in transformer training literature and often gives
     0.5-2% improvement for free.
   - **Expected impact**: −0.3 to −0.8 MAE
   - **Effort**: Very low — 3 lines of code
   - **Risk**: Very low

8. **🔬 Encoder-decoder transformer**
   - **What**: Separate encoder (history) and decoder (future) with cross-attention
   - **Why**: Current architecture uses encoder-only with future masking. A
     decoder would naturally handle the sequential prediction structure and
     could incorporate future PK channels as decoder "prompt" tokens.
   - **Expected impact**: Unclear — could be −2 MAE or neutral
   - **Effort**: Medium-high — new architecture implementation
   - **Risk**: Medium — architecture changes often don't hold at scale (Phase 4 lesson)

#### Tier 3: Speculative / Research-Grade

9. **🔬 Stochastic future PK channels**
   - **What**: Instead of deterministic future PK, sample from uncertainty
     distributions (e.g., carb absorption timing ±30min)
   - **Why**: Carb absorption is the most uncertain parameter (Finding 7:
     40-120 mg/dL range for same meal). Deterministic future PK assumes
     perfect absorption timing, which is unrealistic.
   - **Expected impact**: Unknown — could improve calibration if not MAE
   - **Effort**: Medium — requires uncertainty modeling
   - **Risk**: High — more noise might hurt more than it helps

10. **🔬 PatchTST / modern time series transformers**
    - **What**: Test patching (group consecutive timesteps) architectures
    - **Why**: PatchTST has shown state-of-the-art results on standard
      benchmarks. Our 5-minute resolution with 12-24 steps could benefit
      from patching (group 3 consecutive → 4/8 tokens for w24/w48).
    - **Expected impact**: Unknown — could be significant
    - **Effort**: Medium — new architecture
    - **Risk**: High — may not translate from general to glucose-specific

11. **🔬 Regime-switching model**
    - **What**: Separate models for "calm" vs "volatile" periods, with
      a classifier to select which model to use
    - **Why**: Volatile periods have 2.04× worse MAE (Finding 4). A
      specialized model for post-meal dynamics might learn carb-insulin
      interactions better than a general model.
    - **Expected impact**: −1 to −3 MAE for volatile periods
    - **Effort**: High — classifier + two models + blending
    - **Risk**: High — classifier errors cascade

12. **🔬 Hepatic glucose production estimation**
    - **What**: Estimate EGP from glucose patterns during fasting periods
      and provide as an input channel
    - **Why**: EGP is the primary unmeasured variable driving glucose during
      fasting and overnight. It's the "dark matter" of glucose prediction.
    - **Expected impact**: Potentially large for overnight/fasting periods
    - **Effort**: Very high — requires physiological modeling
    - **Risk**: Very high — EGP estimation is an open research problem

---

## Part 3: Use Case Differentiation

### Not All Forecasts Serve the Same Purpose

Through our experiments, we've identified that "glucose forecasting" is actually
several distinct use cases with different requirements:

| Use Case | Horizon | Tolerance | Critical Feature | Key Challenge |
|----------|:-------:|:---------:|-----------------|---------------|
| **Hypo prevention alert** | 15-30 min | Must be sensitive (low FP) | Trend + IOB | False negatives → danger |
| **Meal bolus decision** | 30-60 min | ±15 mg/dL | Full PK | Post-meal peak prediction |
| **Basal rate adjustment** | 1-3 hours | ±20 mg/dL | IOB + trend | Smooth, not reactive |
| **Overnight management** | 3-8 hours | Direction matters more | EGP, circadian | Dawn phenomenon |
| **Daily pattern learning** | 12-24 hours | Trend-level accuracy | Weekly patterns | Routine vs chaos |

### Where We're Strong vs. Weak

```
Accuracy vs Horizon

MAE  ▲
(mg) │
 50  │                                                    ●——● Physiological regime
     │                                               ●——●     (unmeasured factors dominate)
 40  │                                          ●——●
     │                                     ●
 35  │                               PK advantage zone
     │                          ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
 30  │                     ●                              BIGGEST OPPORTUNITY
     │                                                    FOR IMPROVEMENT
 25  │               ●                                    (Future PK + longer history)
     │          ●
 20  │     ●
     │  ●      Well-explored         Partially explored        Under-explored
 15  │●        territory             territory                 territory
     │ ╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱         ╱╱╱╱╱╱╱╱╱╱╱╱╱╱            ╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱
 10  │●  Near CGM MARD
     │
  5  │ Sensor noise floor
     └─────────────────────────────────────────────────────────────► Horizon
       h5   h30   h60   h90  h120  h180  h240  h360  h480  h720
```

**The biggest opportunity for improvement is h120-h360** (2-6 hours), where:
1. We have proven PK advantage (EXP-356: −10 mg/dL)
2. We have not yet tested the PKGroupedEncoder transformer
3. Future PK projection should have maximum impact
4. Longer history windows capture full DIA

This is also the most clinically valuable zone for AID systems — it's where
basal rate decisions are made and where overnight management happens.

---

## Part 4: The Unifying Synthesis

### What Diabetes Teaches About Machine Learning

Our glucose forecasting work has revealed ML principles that may generalize:

1. **Domain-specific dense representations beat generic features**: Converting
   sparse events (bolus, carbs) to their physical absorption curves (insulin_net,
   carb_rate) worked because the continuous representation matches the underlying
   causal process. This is a form of **physics-informed feature engineering**.

2. **Causal projections are legitimate inputs**: When a causal process is
   deterministic and known (insulin decay), its future trajectory is a valid
   model input — it's not "looking at the future," it's "computing the
   consequences of the past." This principle likely applies to any domain
   with known decay/diffusion processes.

3. **Multi-task loss as regularization**: Predicting multiple horizons
   simultaneously improves each horizon individually. This is the "free lunch"
   of multi-horizon forecasting — the shared gradient structure prevents
   overfitting to any single target.

4. **Normalization by causal factors**: ISF normalization works because it
   removes a known source of inter-patient variance. The principle: if you
   know WHY examples differ (ISF), normalize by that factor so the model
   learns the universal relationship rather than patient-specific scales.

5. **Architecture ceiling exists**: At our data scale (35K training windows,
   11 patients), more parameters consistently hurt. The ceiling is ~134-240K
   params. Beyond this, more capacity = more overfitting. This suggests
   data collection (more patients, longer histories) is more valuable than
   architecture search.

### The Remaining Gaps

| Gap | Estimated Impact | Difficulty | Current Status |
|-----|:----------------:|:----------:|:--------------:|
| Future PK on transformer | −3 to −8 MAE at h120+ | Low | **NOT TESTED** ⭐ |
| Extended history (w48-w96) | −2 to −5 MAE at h120+ | Low | **NOT TESTED** ⭐ |
| Hard patient optimization | −1 to −3 overall | Medium | Not tested |
| Glucose derivatives | −0.5 to −1.5 overall | Very Low | Not tested |
| Dynamic ISF | −0.5 to −1 overall | Medium | Not tested |
| Horizon-weighted loss | −0.5 to −2 at h60 | Low | Not tested |
| Encoder-decoder architecture | Unknown | Medium-High | Not tested |
| Overnight-specific model | −3 to −5 for overnight | High | Not tested |
| Exercise integration | Unknown (no data) | Very High | Not feasible yet |

### Recommended Priority Order

**Phase A: Low-hanging fruit (⭐ starred items)**
1. Future PK on PKGroupedEncoder at w48 (Tier 1, item 1)
2. Extended history sweep (w48, w72, w96) (Tier 1, item 2)
3. Glucose derivative channels (Tier 1, item 3)
4. Cosine LR with warmup (Tier 2, item 7)

**Phase B: Patient-specific improvements**
5. Hard patient optimization (Tier 1, item 4)
6. Dynamic ISF normalization (Tier 2, item 6)
7. Horizon-weighted loss (Tier 2, item 5)

**Phase C: Architecture exploration (only if Phase A/B plateau)**
8. Encoder-decoder transformer (Tier 2, item 8)
9. PatchTST / modern architectures (Tier 3, item 10)

**Phase D: Research frontier (long-term)**
10. Stochastic PK (Tier 3, item 9)
11. Regime-switching (Tier 3, item 11)
12. EGP estimation (Tier 3, item 12)

---

## Part 5: Should We Use Longer History?

### The Case For 12-Hour History

| Argument | Evidence | Strength |
|----------|---------|:--------:|
| Full DIA visibility | EXP-289: 12h windows have best pattern quality | 🟢 Strong |
| PK crossover at 4h | EXP-353: PK channels help at ≥4h history | 🟢 Strong |
| Circadian capture | 12h captures dawn→afternoon or evening→morning | 🟡 Medium |
| More context for hard patients | Patient b (ISF=94) has slow dynamics | 🟡 Medium |

### The Case Against

| Argument | Evidence | Strength |
|----------|---------|:--------:|
| 6h > 9h > 12h in EXP-376 | Tested on CNN, but consistent | 🟡 Medium |
| Data scarcity at long windows | 9h: 2819→4229 (stride fix helped) | 🟠 Weakened |
| Attention dilution | More tokens → attention more spread | 🟠 Theoretical |
| Overfitting | More params needed for longer sequences | 🟡 Medium |

### Recommendation

**Test extended history SPECIFICALLY for extended horizons**. Don't use 12h
history to predict h30 (overkill). Instead:

| Prediction Target | Recommended History | Window Size | Rationale |
|:-----------------:|:-------------------:|:-----------:|-----------|
| h5–h60 | 1h (w24) | 24 | **Already optimal** — EXP-410 proves this |
| h60–h120 | 2h (w48) | 48 | Captures one DIA cycle |
| h120–h240 | 4h (w96) | 96 | Captures post-meal return to baseline |
| h240–h360 | 6h (w144) | 144 | Full overnight or daytime arc |
| h360–h720 | 8-12h (w192-w288) | 192-288 | Circadian half-cycle |

This "horizon-adaptive history" approach avoids the pitfall of over-long
windows for short predictions while giving long-range predictions the context
they need.

---

## Part 6: Summary and Decision Matrix

### What to Do Next

| Priority | Experiment | Expected Δ MAE | Effort | Confidence |
|:--------:|-----------|:--------------:|:------:|:----------:|
| **1** | Future PK + PKGroupedEncoder (w48, h120+) | −3 to −8 | Low | High |
| **2** | Horizon-adaptive history sweep | −2 to −5 at h120+ | Low | Medium |
| **3** | Glucose derivative channels | −0.5 to −1.5 | Very Low | Medium |
| **4** | Cosine LR + warmup | −0.3 to −0.8 | Very Low | Medium |
| **5** | Hard patient optimization (b, j, a) | −1 to −3 overall | Medium | High |
| **6** | Dynamic ISF | −0.5 to −1 | Medium | Medium |
| **7** | Horizon-weighted loss | −0.5 to −2 at h60 | Low | Medium |

### Key Principle Going Forward

> **Pursue the PK advantage zone (h120-h360) with proven components
> (PKGroupedEncoder + future PK + ISF) before chasing diminishing returns
> in the well-optimized h30-h60 range.**

At h60, we're already within 1% of CGM MARD — further improvements there have
diminishing clinical returns. At h120-h360, we're 2-4× worse than h60, AND we
have proven techniques (future PK, PK channels) that haven't been applied to
the transformer architecture yet. This is where the highest-impact work remains.

---

*This report synthesizes findings from 410 experiments across 4 research eras.
It aims to guide resource allocation toward the highest-impact unexplored
territories while acknowledging the considerable success already achieved in
short-horizon forecasting.*
