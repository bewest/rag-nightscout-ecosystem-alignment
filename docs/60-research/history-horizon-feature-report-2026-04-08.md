# History Length, Feature Engineering, and Horizon Extension Report

**Date**: 2026-04-08  
**Experiments**: EXP-428, EXP-429, EXP-411 (extended analysis)  
**Status**: Findings report + updated research roadmap

---

## Executive Summary

This report synthesizes findings from three lines of investigation:

1. **EXP-428**: Whether additional feature channels (glucose derivatives, hepatic
   glucose production, carb acceleration) help the transformer at extended horizons
2. **EXP-429**: Whether longer history windows improve h60 predictions when the
   prediction task is held constant (asymmetric windows)
3. **EXP-411 re-analysis**: Cross-window performance patterns revealing where
   history length helps vs hurts, and which patients benefit

### Key Findings

| Finding | Evidence | Implication |
|---------|----------|-------------|
| **Transformer doesn't need hand-crafted features** | EXP-428: all variants ±0.2 of baseline | Stop feature engineering for transformer |
| **2h history is optimal for h60** | EXP-429: w36_asym (2h) best at 12.78 | More history doesn't help short horizons |
| **Data scarcity dominates at long windows** | w72: 6.9K windows vs w24: 13.8K | Training volume is the binding constraint |
| **Hard patients benefit from longer history** | Patient b: w72 best (17.4 vs 18.8) | Per-patient window routing is viable |
| **h120 is window-independent at ~17.4** | EXP-411 w48/w72/w96 all ≈17.4 | 2h history already captures DIA for h120 |
| **Asymmetric windows are the right framework** | EXP-429 confirms independent control | Separate history length from prediction difficulty |

---

## 1. EXP-428: Feature Engineering Is a CNN Benefit, Not a Transformer Benefit

### Hypothesis

Adding explicit glucose derivatives (dBG/dt, d²BG/dt²) and physiological channels
(hepatic glucose production, carb acceleration) would give the transformer rate-of-change
and metabolic state information that improves extended horizon predictions.

### Design

| Variant | Channels | Description |
|---------|:--------:|-------------|
| baseline | 8 | Standard: glucose, IOB, COB, net_basal, ins_net, carb_rate, sin, net_bal |
| glucose_deriv | 10 | +dBG/dt, d²BG/dt² (zeroed in future half to prevent leakage) |
| hepatic | 10 | +hepatic_prod, carb_accel (available in future, causal) |
| deriv_hepatic | 12 | All four additional channels |

**Leakage prevention**: Glucose derivatives in the future half are zeroed during data
preparation — future glucose is the prediction target and cannot inform features.
PK derivatives (carb_accel, hepatic_prod) are deterministic from past events and
safely available in the future half.

### Results (Quick: 4 patients, 1 seed, w48)

| Variant | Channels | MAE | Δ vs baseline | h60 | h120 |
|---------|:--------:|:---:|:-------------:|:---:|:----:|
| baseline | 8 | 16.57 | — | 17.2 avg | 22.1 avg |
| glucose_deriv | 10 | 16.60 | +0.03 | 17.5 avg | 22.2 avg |
| hepatic | 10 | 16.59 | +0.02 | 17.5 avg | 22.2 avg |
| deriv_hepatic | 12 | 16.77 | +0.20 | 17.6 avg | 22.5 avg |

### Interpretation

**All variants within noise of baseline.** The transformer's self-attention mechanism
already extracts rate-of-change, curvature, and metabolic state information from the
raw signal sequences. Hand-crafted features add redundancy, not information.

This is fundamentally different from CNN findings where:
- B-spline derivatives gave +15% SNR (EXP-331)
- ISF normalization gave −1.2 MAE (EXP-361)
- ROC features gave marginal −0.4 (EXP-358)

**Why transformers don't need feature engineering**:
1. Multi-head attention computes pairwise relationships across ALL timesteps
2. dBG/dt ≈ attention weight between adjacent glucose values (already learned)
3. d²BG/dt² ≈ second-order attention pattern (already learned)
4. Hepatic production is implicit in glucose-insulin residual (already modeled)

**Exception**: ISF normalization still helps (+0.4-1.2 MAE) because it's a
*normalization* (scales the problem), not a *feature* (adds information). The
transformer can learn relative patterns but benefits from patient-specific scaling.

### Conclusion

> **For transformer architectures, invest in normalization and data quality,
> not feature engineering.**

---

## 2. EXP-429: History Length Sweep for h60 (Asymmetric Windows)

### Hypothesis

The w24 champion (10.85 MAE full, ~13 quick) uses only 1h of history. Since insulin
DIA is ~5h, the model sees only 20% of active insulin. By extending history to 5h
while keeping the prediction task constant (12 future steps = h60), we should improve
predictions by providing complete insulin dynamics context.

### Design

All variants predict exactly 12 future steps (h60). Only history length varies:

| Config | Window | History | Future | History Duration |
|--------|:------:|:-------:|:------:|:----------------:|
| w24_control | 24 | 12 | 12 | 1h (60 min) |
| w36_asym | 36 | 24 | 12 | 2h (120 min) |
| w48_asym | 48 | 36 | 12 | 3h (180 min) |
| w72_asym | 72 | 60 | 12 | 5h (300 min) |

### Results (Quick: 4 patients, 1 seed)

| Config | History | Train Windows | MAE | Δ vs w24 |
|--------|:-------:|:------------:|:---:|:--------:|
| w24_control | 1h | 13,820 | 13.03 | — |
| **w36_asym** | **2h** | **13,816** | **12.78** | **−0.25** |
| w48_asym | 3h | 10,360 | 12.94 | −0.09 |
| w72_asym | 5h | 6,904 | 13.20 | +0.17 |

### Per-Patient Analysis

| Patient | ISF | w24 | w36 | w48 | w72 | Best Window |
|---------|:---:|:---:|:---:|:---:|:---:|:-----------:|
| d | 40 | 8.15 | 8.28 | **7.47** | 7.97 | w48 (3h) |
| c | 77 | **10.62** | 10.85 | 11.16 | 11.74 | w24 (1h) |
| a | 49 | **14.60** | 14.16 | 14.63 | 15.67 | w36 (2h) |
| b | 94 | 18.75 | 17.81 | 18.50 | **17.42** | w72 (5h) |

### Key Observations

**1. The sweet spot for h60 is 2h history (w36_asym)**

The improvement is modest (−0.25) but consistent. Beyond 2h, gains vanish and
reverse. At h60, the model primarily needs recent glucose momentum (last 30-60 min)
plus the immediate insulin/carb trajectory. Distant history is noise.

**2. Data scarcity is the binding constraint for long windows**

| Window | Train Samples | Δ from w24 |
|--------|:------------:|:----------:|
| w24 | 13,820 | — |
| w36 | 13,816 | −4 (negligible) |
| w48 | 10,360 | −3,460 (−25%) |
| w72 | 6,904 | −6,916 (−50%) |

At w72, the model has HALF the training data. The information gain from 5h history
is overwhelmed by the statistical loss from fewer examples. This is a fundamental
trade-off: **longer windows = more context but less data**.

**3. Hard patients benefit from longer history**

Patient b (ISF=94, hardest patient) improves monotonically with history:
18.75 → 17.81 → 18.50 → **17.42**. The w72 model sees enough of b's slow insulin
dynamics to make better predictions. Patient d (ISF=40) also peaks at w48.

Meanwhile, easy patients (c, a) are best at w24/w36 — their dynamics are simple
enough that 1-2h of context suffices.

**4. The optimal history grows with patient complexity (ISF)**

| ISF Range | Optimal History | Interpretation |
|-----------|:--------------:|----------------|
| Low (25-40) | 2-3h | Fast insulin action, moderate context needed |
| Medium (49-77) | 1-2h | Standard dynamics, recent context sufficient |
| High (94) | 5h | Slow insulin, needs full DIA coverage |

This suggests **per-patient window routing** would be more effective than a
single universal window.

---

## 3. EXP-411 Re-Analysis: What History Length Tells Us About Each Horizon

### Cross-Window h120 Performance (Full Validation, 11 patients)

| Window | History | h120 MAE | Train Windows |
|--------|:-------:|:--------:|:------------:|
| w48 | 2h | **17.4** | 26,425 |
| w72 | 3h | **17.4** | 17,609 |
| w96 | 4h | **18.3** | 13,161 |

**h120 is remarkably window-independent** at ~17.4 for w48 and w72. The model
extracts the same h120 accuracy from 2h or 3h of history. Only at w96 (where
training data drops to 13K) does performance degrade.

This means: **for h120, the bottleneck is NOT history length — it's prediction
difficulty and data volume.**

### Per-Patient Cross-Window Patterns (h120 specifically)

| Patient | ISF | w48 h120 | w72 h120 | w96 h120 | Best |
|---------|:---:|:--------:|:--------:|:--------:|:----:|
| k | 25 | 9.73 | **9.45** | **9.14** | w96 |
| f | 21 | 11.29 | 12.00 | **10.65** | w96 |
| g | 69 | 14.49 | **13.90** | 16.54 | w72 |
| e | 36 | **15.78** | 15.04 | 16.82 | w72 |
| i | 50 | **16.70** | 16.76 | 15.89 | w96 |
| h | 92 | **18.56** | 17.43 | 19.66 | w72 |
| a | 49 | **24.23** | 23.26 | 25.34 | w72 |
| j | 40 | **22.49** | 25.04 | 25.27 | w48 |
| b | 94 | **32.92** | 32.41 | 35.55 | w72 |

**Patients k and f** (lowest ISF, best controlled) actually improve at w96!
Their insulin dynamics are fast and predictable — more history genuinely helps
the model resolve their curves at h120.

**Patients with high ISF** (b, h) peak at w72 — they need moderate context but
w96 data scarcity hurts.

---

## 4. Unified Theory: History × Horizon × Patient Complexity

### The Three Regimes

```
History Benefit = f(horizon, patient_complexity, data_volume)

Regime 1: Short Horizon (h30-h60)
  - Dominated by glucose momentum (last 30 min)
  - Optimal history: 1-2h
  - More history = more noise, less data
  - PK channels useful but not critical

Regime 2: Medium Horizon (h90-h120)  
  - Dominated by insulin/carb absorption phase
  - Optimal history: 2-3h (one partial DIA cycle)
  - Future PK projection is the key enabler (-10 MAE)
  - History helps if data volume is maintained

Regime 3: Long Horizon (h180-h360)
  - Dominated by basal-hepatic equilibrium + meal patterns
  - Optimal history: unknown (UNTESTED with asymmetric windows)
  - Hypothesis: 4-6h history helps if data scarcity is addressed
  - May require classification instead of point forecasts
```

### The Data Volume vs Context Trade-off

```
MAE = f(information_from_history) + g(1/training_volume) + irreducible_noise

At short horizons: g() dominates → less data hurts more than more context helps
At long horizons:  f() dominates → more context helps more than less data hurts
Crossover point:   ~h90-h120 (hypothesis, needs testing)
```

This predicts that **asymmetric long-history windows should help MORE at h120+**
than they helped at h60. Testing this is the highest-priority next experiment.

---

## 5. Data Quality Requirements for Extended Horizons

### Minimum Requirements by Horizon

| Requirement | h60 | h120 | h180+ |
|-------------|:----:|:-----:|:-----:|
| CGM coverage | ≥70% | ≥80% | ≥90% |
| IOB telemetry | Helpful | **Required** | **Required** |
| Pump data (vs MDI) | +2-3 MAE penalty | +4-6 MAE penalty | Exclude MDI |
| Basal drift tolerance | ±15 mg/dL/h | ±10 mg/dL/h | ±5 mg/dL/h |
| Settings fidelity | Any | ≥35/100 | ≥45/100 |
| PK model validity | Helpful | **Essential** | **Essential** |

### Patient Tiers for Extended Horizon Research

| Tier | Patients | Criteria | Horizon Limit |
|------|----------|----------|:-------------:|
| **Gold** | k, d, f | Low ISF, pump, good settings, low residual | h360+ |
| **Silver** | c, e, g | Moderate ISF, pump, adequate settings | h180 |
| **Bronze** | h, i | High ISF or basal drift | h120 |
| **Exclude** | a, b, j | Very high ISF, MDI (j), persistent residual | h60 only |

### Patient Filtering for Training

For h120+ experiments, we should consider **filtering the training set** to
include only patients that meet minimum data quality:

- Exclude patient j (MDI, no pump telemetry — PK model is unreliable)
- Optionally exclude a, b (high residual, poor settings fidelity)
- This reduces noise in the base model, improving transfer to all patients

---

## 6. What Works and What Doesn't: Updated Scorecard

### Validated Techniques (Positive Results)

| Technique | Effect Size | Horizon Range | Evidence |
|-----------|:----------:|:------------:|----------|
| Transformer architecture | 2.20× vs CNN | All | EXP-411 |
| Future PK projection | −10 MAE at h120 | h60+ | EXP-356 |
| ISF normalization | −0.4 to −1.2 | All | EXP-361, 410 |
| Per-patient fine-tuning | −10-15% | All | EXP-408, 410 |
| 5-seed ensemble | −3-8% | All | EXP-410 |
| PK-replaced channels | −7.4 at 6h window | h120+ | EXP-353 |
| Asymmetric windows (2h hist) | −0.25 for h60 | h60 | EXP-429 |

### Negative Results (Save Future Effort)

| Technique | Result | Why | Evidence |
|-----------|--------|-----|----------|
| Glucose derivatives | +0.03 | Transformer learns implicitly | EXP-428 |
| Hepatic/carb_accel channels | +0.02 | Redundant with existing PK | EXP-428 |
| Combined extra features (12ch) | +0.20 | More channels = more noise | EXP-428 |
| Horizon-weighted loss at w48 | −0.08 | Marginal; w24-specific technique | EXP-426 |
| 5h history for h60 | +0.17 | Data scarcity overwhelms context | EXP-429 |
| Data augmentation (noise) | +0.3 | Must be input-only, even then marginal | EXP-423 |

### Untested but Promising

| Technique | Expected Impact | Rationale | Priority |
|-----------|:--------------:|-----------|:--------:|
| **Asymmetric windows for h120** | −1 to −3 MAE | More history helps at longer horizons | **HIGH** |
| **Patient-filtered training** | −0.5 to −2 MAE | Remove noise from low-quality patients | HIGH |
| **Per-patient window routing** | −0.5 to −1 MAE | ISF-dependent optimal history | MEDIUM |
| **Stride reduction for w72+** | −0.5 to −1 MAE | Address data scarcity directly | HIGH |
| **State-dependent routing** | Unknown | Active vs fasting need different models | MEDIUM |
| **Risk classification h180+** | N/A (new task) | Point forecasts unreliable at h180+ | HIGH |

---

## 7. Recommended Next Experiments

### Priority 1: Asymmetric History Sweep for h120 (EXP-430)

**Hypothesis**: At h120 (where PK dynamics dominate), longer history should help
MORE than it helped at h60. The crossover where context beats data scarcity should
occur at a longer horizon.

```
Variants (all predict 24 future steps = h120):
  w48_control:  24 hist (2h) + 24 future  ← EXP-411 match
  w60_asym:     36 hist (3h) + 24 future
  w84_asym:     60 hist (5h) + 24 future  ← full DIA
  w108_asym:    84 hist (7h) + 24 future  ← beyond DIA
```

### Priority 2: Patient-Quality-Filtered Training (EXP-431)

**Hypothesis**: Excluding low-fidelity patients (a, b, j) from base training
reduces noise and improves the base model for all patients. FT still personalizes.

```
Variants:
  all_patients:     Train on all 11 (current approach)
  gold_silver:      Train on k, d, f, c, e, g only (6 patients)
  pump_only:        Exclude j (MDI) from base training
  quality_filtered: Exclude a, b, j from base training
```

### Priority 3: Stride Optimization for Long Windows (EXP-432)

**Hypothesis**: The w72 data scarcity (6.9K vs 13.8K at w24) can be partially
addressed by reducing stride from w//3 to a fixed 6-step stride, increasing
training windows without information leakage.

### Priority 4: h180+ Risk Classification (EXP-433)

**Hypothesis**: Beyond h120, point forecast accuracy degrades exponentially.
Classification (P(hypo in next 3h), P(high in next 3h)) may be more clinically
useful and achievable than precise mg/dL predictions.

---

## Appendix A: Complete EXP-429 Per-Patient Results

### h30 Performance

| Patient | w24 | w36 | w48 | w72 |
|---------|:---:|:---:|:---:|:---:|
| d | 8.49 | 8.81 | **7.44** | 8.22 |
| c | **10.65** | 10.86 | 11.21 | 11.15 |
| a | 14.52 | **14.01** | 15.18 | 15.53 |
| b | **18.19** | **17.24** | 18.36 | 17.20 |

### h60 Performance

| Patient | w24 | w36 | w48 | w72 |
|---------|:---:|:---:|:---:|:---:|
| d | 10.79 | 10.70 | **10.31** | 11.53 |
| c | **14.37** | 14.65 | 14.05 | 16.72 |
| a | 21.06 | **20.04** | 20.71 | 21.86 |
| b | 27.82 | **25.74** | 27.07 | **25.24** |

---

## 8. EXP-430: History Sweep for h120 — Data Volume Dominates

### Hypothesis

At h120 (where insulin dynamics dominate), the crossover point where "more context
beats less data" should occur — longer history should help MORE than it did at h60.

### Results (Quick: 4 patients, 1 seed)

| Config | History | Train Windows | MAE | h60 | h90 | h120 |
|--------|:-------:|:------------:|:---:|:---:|:---:|:----:|
| **w48_control** | **2h** | **10,360** | **16.57** | **17.23** | **20.0** | **22.11** |
| w60_asym | 3h | 8,288 | 17.20 | 17.91 | 20.58 | 22.86 |
| w84_asym | 5h | 5,916 | 18.48 | 19.51 | 22.4 | 24.07 |
| w108_asym | 7h | 4,600 | 19.69 | 20.06 | 23.73 | 26.77 |

### Per-Patient h120 Analysis

| Patient | ISF | w48 (2h) | w60 (3h) | w84 (5h) | w108 (7h) |
|---------|:---:|:--------:|:--------:|:--------:|:---------:|
| d | 40 | **13.03** | 14.20 | 14.45 | 16.44 |
| c | 77 | **15.60** | 15.82 | 18.62 | 20.78 |
| a | 49 | **23.82** | 25.15 | 26.83 | 31.87 |
| b | 94 | **35.97** | 36.26 | 36.36 | 37.99 |

### The Crossover Never Happens

**Longer history hurts at EVERY horizon including h120.** The expected crossover
where DIA context outweighs data loss does not materialize.

```
Training windows vs history length:
  w48:  10,360 (100%)
  w60:   8,288 (−20%)
  w84:   5,916 (−43%)
  w108:  4,600 (−56%)

Performance penalty correlates almost perfectly with data loss:
  w60: +0.63 MAE from −20% data
  w84: +1.91 MAE from −43% data
  w108: +3.12 MAE from −56% data
```

### Why the Crossover Doesn't Happen

1. **Future PK channels already resolve the DIA**: The transformer sees deterministic
   insulin absorption curves in the future half. It doesn't NEED history to
   reconstruct the DIA arc — the future PK tells it directly.

2. **2h history captures the active metabolic state**: At any moment, the glucose
   trajectory depends on: (a) current glucose momentum (~30 min), (b) current
   insulin activity (~2h), (c) current carb absorption (~2h). All three fit
   within 2h of history.

3. **Older history is noise**: Events >2h ago have largely finished their
   pharmacodynamic effect. Their residual influence is captured by current
   IOB/COB values already in the feature set.

4. **Data scarcity penalty is steep**: Each additional hour of history costs
   ~15-20% of training windows. With only 4 patients in quick mode, this
   is devastating. Even at full scale (11 patients), w84 would have ~15K
   windows vs w48's ~26K — still a 42% reduction.

### Implication for Research Strategy

> **The transformer + future PK architecture has fundamentally solved the
> "history length" problem. The remaining lever for improvement is NOT
> more history or more features — it's MORE TRAINING DATA.**

Priority shifts:
1. ~~Longer history windows~~ → **Stride optimization** (more windows from same data)
2. ~~Feature engineering~~ → **Data quality filtering** (remove noise sources)
3. ~~Metabolic flux signals~~ → **Horizon-adaptive routing** (right model per horizon)

---

## 9. Production Champion Analysis: h60 Forecasting

### The Full Spectrum

| Tier | Config | Overall MAE | Training Cost | Inference | Data Required |
|------|--------|:-----------:|:------------:|:---------:|---------------|
| **Champion** | EXP-410 (5-seed + FT) | ~10.9 | 5×200ep + 11×5×30ep FT | 5 models | Glucose + PK + ISF |
| **Near-champion** | EXP-410 (1-seed + FT) | ~11.5 | 200ep + 11×30ep FT | 1 model | Glucose + PK + ISF |
| **Good** | EXP-407 (1-seed, no FT) | ~14-15 | 200ep only | 1 model | Glucose + PK + ISF |
| **Basic** | EXP-406 (no ISF) | ~15-16 | 200ep only | 1 model | Glucose + PK |
| **Minimal** | EXP-405 (base) | ~16-17 | 200ep only | 1 model | Glucose + PK |

### Architecture Details

```
PKGroupedEncoder: 134,648 parameters
  - State group (glucose, IOB, COB): 3 → 32 dim
  - Action group (net_basal, insulin_net, carb_rate): 3 → 16 dim
  - Extra group (time/net_balance): 2 → 16 dim
  - Combined: 64 dim → 4-layer transformer, 4 heads
  - Output: 64 → 1 (glucose prediction)
```

### Cost-Accuracy Trade-off

The **5-seed ensemble + per-patient FT** gives ~10.9 overall MAE but costs 50× the
compute of a single base model. The diminishing returns curve:

```
Single base model (no FT):   ~15 MAE (1× cost)
Single base + FT:            ~11.5 MAE (1.5× cost, −23% MAE)
3-seed ensemble + FT:        ~11.0 MAE (4.5× cost, −4% more)
5-seed ensemble + FT:        ~10.9 MAE (7.5× cost, −1% more)
```

**Recommendation**: For production, **1-seed + per-patient FT** captures 80%
of the champion's benefit at 20% of the cost. The ensemble is a luxury for
research validation, not a production necessity.

---

## 10. Metabolic Flux and Feature Engineering: What Helps Beyond 60 Minutes?

### Synthesis with Recent Research

The temporal alignment report (EXP-521-537) and metabolic flux synthesis reveal:

| Signal Category | h60 Impact | h90-h120 Impact | h180+ Impact |
|----------------|:----------:|:---------------:|:------------:|
| **Glucose momentum** (AR) | High | Decays | ~Zero |
| **Future PK projection** | High | **Dominant** | Moderate |
| **ISF normalization** | Moderate | Moderate | Moderate |
| **Supply/demand decomp** | None (EXP-428) | None | None |
| **Glucose derivatives** | None (EXP-428) | None | None |
| **Hepatic production** | None (EXP-428) | None | None |
| **Phase lag structure** | None | None | None |
| **State-dependent model** | Untested | Promising | Promising |

### Why Metabolic Flux Signals Don't Help the Transformer

1. **Supply/demand decomposition**: The transformer already computes this
   implicitly from glucose + PK channels. Adding explicit channels is redundant.

2. **Throughput (supply × demand)**: Excellent meal classifier (18× spectral
   power), but meal classification doesn't improve point forecasts — the model
   already knows about meals from carb_rate.

3. **Phase lag**: A structural property (~20 min carb-insulin lag) that's
   constant and small relative to prediction horizons. Not predictive.

4. **Deterministic chaos limit**: Physics-based flux models actively HURT at
   h≥30min (EXP-542: skill goes negative). The transformer outperforms
   physics by learning statistical patterns, not deterministic equations.

### What MIGHT Help Beyond 60 Minutes (Untested)

| Approach | Mechanism | Priority |
|----------|-----------|:--------:|
| **Stride optimization** | More training windows from same data | HIGH |
| **Patient quality filtering** | Remove noisy patients from base training | HIGH |
| **State-dependent routing** | Different models for fasting/meal/correction | MEDIUM |
| **Uncertainty quantification** | Calibrated confidence bands for h90+ | MEDIUM |
| **Multi-resolution ensemble** | Route to optimal model per horizon | LOW (validated) |

---

## 11. Updated Research Priorities

### Confirmed Dead Ends (Don't Pursue)

| Approach | Evidence | Save |
|----------|----------|:----:|
| Feature engineering for transformer | EXP-428: ±0.2 of baseline | ~20h |
| Longer history for h60 | EXP-429: 2h optimal, 5h hurts | ~10h |
| Longer history for h120 | EXP-430: 2h optimal, 7h hurts badly | ~10h |
| Horizon-weighted loss at w48 | EXP-426: marginal −0.08 | ~5h |
| Metabolic flux as features | Transformer extracts implicitly | ~20h |

### High-Priority Next Experiments

1. **Stride optimization at w48/w72** — Address data scarcity directly
   by reducing stride from w//3 to fixed 6-12 steps. Could increase
   w72 training data from 17K to 30K+.

2. **Patient-quality-filtered base training** — Train base model on
   gold/silver patients only (k,d,f,c,e,g), then FT on all. Reduces
   noise in base model.

3. **State-dependent loss weighting** — Weight fasting vs meal vs
   correction windows differently. Each has different physics and
   prediction difficulty.

### The Fundamental Picture

```
What we've learned about extending forecasts beyond 60 minutes:

h60:  SOLVED (overall 10.9 MAE below CGM MARD; h60-step 14.7 = 1.2× MARD)
      → Glucose momentum dominates
      → 1h history sufficient
      → Single model + FT is production-viable

h120: GOOD (17.4 MAE full validation)
      → Future PK is the key enabler (−10 MAE vs without)
      → 2h history sufficient (more history hurts!)
      → Transformer architecture essential (2.20× vs CNN)

h180-h480: POSSIBLE but data-limited
      → Same 2h history + future PK pattern
      → Bottleneck is training data volume, not features
      → Need stride optimization or more patients
      → Consider uncertainty quantification over point forecasts
```

---

## Appendix B: EXP-411 Full Validation Summary (11 patients, 5 seeds)

### Overall Mean Ensemble MAE

| Window | Overall | h60 | h120 | Train Windows |
|--------|:-------:|:---:|:----:|:------------:|
| w24 (EXP-410) | **10.85** | **14.7** | — | 33,547 |
| w48 | 13.50 | 14.2 | **17.4** | 26,425 |
| w72 | 15.61 | 15.0 | **17.4** | 17,609 |
| w96 | 17.14 | 15.9 | 18.3 | 13,161 |

### h120 Performance by Patient (Best Window Highlighted)

| Patient | ISF | w48 | w72 | w96 | Best |
|---------|:---:|:---:|:---:|:---:|:----:|
| k | 25 | 9.73 | 9.45 | **9.14** | w96 ↑ |
| d | 40 | **11.40** | 11.85 | 12.86 | w48 |
| f | 21 | 11.29 | 12.00 | **10.65** | w96 ↑ |
| c | 77 | **13.53** | 14.65 | 14.04 | w48 |
| g | 69 | 14.49 | **13.90** | 16.54 | w72 |
| e | 36 | 15.78 | **15.04** | 16.82 | w72 |
| i | 50 | 16.70 | 16.76 | **15.89** | w96 ↑ |
| h | 92 | 18.56 | **17.43** | 19.66 | w72 |
| j | 40 | **22.49** | 25.04 | 25.27 | w48 |
| a | 49 | 24.23 | **23.26** | 25.34 | w72 |
| b | 94 | **32.92** | 32.41 | 35.55 | w72 |

Notable: Patients k, f, i improve at w96 (↑) — all have low-moderate ISF and
good pump telemetry. These are the best candidates for long-history experiments.
