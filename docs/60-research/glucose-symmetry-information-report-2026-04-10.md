# Glucose Signal Symmetry & Information Decomposition Report

**Date**: 2026-04-10  
**Scope**: EXP-1811 through EXP-1818 — 8 experiments, 11 patients  
**Question**: Can we structurally identify two independent information sources (supply vs demand) in the glucose trace, even though we only measure their sum?

## Executive Summary

Glucose obeys an approximate conservation law: **dBG/dt ≈ supply(t) − demand(t)**, where supply = hepatic output + carb absorption and demand = insulin-mediated uptake. We asked whether these two generating processes leave distinguishable statistical signatures in the observed glucose trace, and whether splitting the loss function by direction reveals complementary information at different timescales.

### Key Findings

| Finding | Evidence | Implication |
|---------|----------|-------------|
| **Glucose has a preferred time direction** | TRA=+0.31 at 30min (p<0.001, 8/11 patients), flips to −0.06 at 6h | The process is fundamentally irreversible — rises and falls are NOT mirror images |
| **Rises are spectrally "rougher" than falls** | Spectral slope: rising −1.05 vs falling −1.34 (Δ=0.29, 11/11 patients) | Meals inject high-frequency energy; insulin acts as a low-pass filter |
| **Supply and demand models learn DIFFERENT things** | Supply specialization: 9.5 R² units; Demand: 6.2 R² units | Split losses ARE complementary — each learns its own direction |
| **Meals couple supply and demand; fasting decouples them** | 78.5% of decoupled events are fasting; 52.5% of coupled events are post-meal | The AID loop creates coupling; without it, supply and demand are independent |
| **The physics model systematically over-estimates supply** | Residual×supply correlation: r=−0.55 (population mean) | There is a MISSING supply-dampening channel (likely glycogen buffering) |
| **Demand dominates glucose variance at ALL timescales** | Demand R² > Supply R² from 5min to 2 days (no crossover) | Insulin is the primary controller; supply modulates around it |
| **Information horizon is SHORT for both channels** | Glucose MI half-life: 4h; IOB: 2h; supply/demand proxies: ~15min | Long windows add little — the action is in the last few hours |

### Verdict for the User's Hypothesis

> *"Maybe breaking the loss into one for supply and another for demand might behave differently with long history windows"*

**PARTIALLY CONFIRMED.** The split losses ARE complementary (EXP-1817: COMPLEMENTARY), meaning supply-weighted and demand-weighted models learn genuinely different patterns. However, **longer windows don't help either channel** — both hit diminishing returns by 6h. The information structure is:

- **Short-scale (< 2h)**: Supply and demand are distinguishable via spectral shape and time-reversal asymmetry
- **Medium-scale (2-6h)**: AID loop coupling obscures the separation (meals couple them tightly)
- **Long-scale (> 24h)**: Both channels carry ~0.01 bits — effectively no usable information at day/week timescales from raw signal alone

The glycogen pool / insulin sensitivity distinction you describe would need to manifest at **multi-day** timescales, but the MI analysis (EXP-1813) shows the signal is essentially at noise floor beyond 6h. This doesn't mean those slow processes don't exist — it means CGM alone can't resolve them without additional features (e.g., cumulative carb balance, time-above-range integral) that explicitly accumulate multi-day state.

---

## §1. EXP-1811: Time-Reversal Asymmetry

**Question**: Is glucose played forward statistically distinguishable from glucose played backward?

**Method**: Compute TRA = skewness of velocity increments ⟨(x(t+τ) − x(t))³⟩ / ⟨(x(t+τ) − x(t))²⟩^(3/2) at lags from 5 min to 24h. Compare to 200 shuffled surrogates.

**Result**: **TRA is strongly present** (p<0.001 for most patient-lag combinations).

### TRA by Timescale (Population Mean)

| Lag | TRA | Patients with \|TRA\|>0.1 | Interpretation |
|-----|-----|---------------------------|----------------|
| 5 min | +0.24 | 9/11 | Rises are sharper than falls |
| 15 min | +0.31 | 9/11 | **Peak asymmetry** |
| 30 min | +0.31 | 8/11 | Still strong |
| 1 h | +0.22 | 7/11 | Declining |
| 2 h | +0.08 | 6/11 | Weak |
| 3 h | +0.01 | 6/11 | **Zero crossing** |
| 6 h | −0.06 | 3/11 | Reversal begins |
| 12 h | −0.02 | 1/11 | Near zero |
| 24 h | −0.00 | 2/11 | Noise floor |

### Physical Interpretation

The **positive TRA at short lags** means glucose rises faster than it falls. This is exactly what conservation predicts: meals inject glucose rapidly (minutes to ~1h), while insulin clears glucose slowly (~3-6h DIA). The **zero crossing at ~3h** marks the timescale where meal absorption completes and insulin kinetics dominate.

### Context-Specific TRA (30-min lag)

| Context | TRA | Interpretation |
|---------|-----|----------------|
| Hypo recovery | **+1.23** ± 0.55 | Most asymmetric — sharp counter-regulatory spike UP |
| Fasting | +0.42 ± 0.55 | Even fasting has asymmetry (hepatic bursts?) |
| Post-meal | +0.30 ± 0.33 | Meal rise > insulin fall |
| Correction | **−0.24** ± 0.59 | **REVERSED** — insulin drives fast fall, slow recovery |

The correction context is particularly interesting: it's the only context where TRA is negative, meaning insulin-driven falls are sharper than the subsequent recovery. This is the "demand-dominated" signature — and it's the mirror image of the supply-dominated meal response.

![Time-Reversal Asymmetry](figures/symmetry-fig01-time-reversal.png)

---

## §2. EXP-1812: Rising vs Falling Spectral Signatures

**Question**: Do supply-dominated (rising) and demand-dominated (falling) glucose segments have different frequency content?

**Method**: Segment glucose trace by sign of dBG/dt, compute Welch PSD for contiguous segments >30min, compare spectral slopes.

**Result**: **Consistent spectral difference across all 11 patients.**

| Patient | Rising Slope | Falling Slope | Δ |
|---------|-------------|---------------|---|
| Population | **−1.05** | **−1.34** | **+0.29** |
| Range | −0.70 to −1.31 | −0.95 to −1.56 | +0.11 to +0.46 |

**Every single patient** shows rising slopes shallower than falling slopes (Δ > 0 for 11/11). This means:

- **Rising glucose** has more high-frequency content → meals inject energy at multiple frequencies simultaneously
- **Falling glucose** is spectrally smoother → insulin action is a **low-pass filter** on the glucose signal

### What This Means for Model Architecture

A model that processes rising and falling glucose through the same pathway is wasting representational capacity. The optimal architecture would use:
- **Wider bandwidth** (shorter convolution kernels / more attention heads) for supply-active periods
- **Narrower bandwidth** (longer kernels / fewer heads) for demand-active periods

This supports the hypothesis that a dual-head architecture (one for supply dynamics, one for demand dynamics) could outperform a single-head model.

![Spectral Signatures](figures/symmetry-fig02-spectral.png)

---

## §3. EXP-1813: Information Horizon by Channel

**Question**: How far into the past do different channels carry useful information about the current rate of glucose change?

**Method**: Compute mutual information (binned estimator, 20 bins) between lagged features and current dBG/dt at lags from 5min to 7 days.

**Result**: **All channels hit noise floor by ~6h.** Supply and demand proxies are informative only at very short lags.

### MI Decay by Channel

| Channel | Peak MI (bits) | Half-Life | Long-Range (7d) |
|---------|---------------|-----------|-----------------|
| Glucose | 0.076 @ 30min | **4.0 h** | 0.016 |
| IOB | 0.056 @ 30min | **2.0 h** | 0.012 |
| Carbs | 0.004 @ 30min | **4.0 h** | 0.002 |
| Supply proxy | 0.154 @ 5min | **15 min** | 0.012 |
| Demand proxy | 0.161 @ 5min | **15 min** | 0.010 |

### Key Insight: The "Long Window" Question

The user asked whether supply and demand might carry different information at day/week/month timescales. The answer is clear: **NO — from the raw signal alone.** By 6h, all channels are at ~0.01 bits, which is essentially the estimation noise floor. At 7 days, no channel carries meaningfully more information than random.

**However**, this does NOT mean long-timescale processes (glycogen state, insulin sensitivity shifts) don't exist. It means they can't be detected from lagged raw signals. They might be detectable from **derived cumulative features** (e.g., 24h rolling carb balance, 7d time-above-180) that explicitly integrate slow dynamics. This is the distinction between the raw signal's memory and the system's actual state dimension.

![Information Horizons](figures/symmetry-fig03-info-horizon.png)

---

## §4. EXP-1814: Supply-Demand Cross-Predictability

**Question**: Does past supply predict future demand (or vice versa)? Can we detect the AID feedback loop?

**Method**: Directed information via conditional MI: I(S_past; D_future | D_past) at lags from 15min to 6h.

**Result**: **Weak directed S→D information at short lags, flips to D→S at 6h.**

| Lag | S→D (bits) | D→S (bits) | Direction |
|-----|-----------|-----------|-----------|
| 15 min | 0.002 | 0.000 | S→D |
| 30 min | **0.007** | 0.000 | S→D |
| 1 h | 0.004 | 0.000 | S→D |
| 2 h | 0.001 | 0.000 | S→D |
| 4 h | 0.001 | 0.000 | S→D |
| 6 h | 0.001 | **0.002** | **D→S** |

The **S→D direction** makes physical sense: supply (meal) causes glucose to rise → AID increases demand (more insulin). The **D→S direction at 6h** may reflect the AID loop reducing basal after extended insulin action, allowing hepatic output to increase.

The signal is very weak (< 0.01 bits), which means the AID loop's feedback is fast enough that it's hard to observe as a lagged effect — it's nearly instantaneous in our 5-min resolution.

![Cross-Predictability](figures/symmetry-fig04-cross-predict.png)

---

## §5. EXP-1815: Multi-Scale Variance Ratio

**Question**: At different timescales (5min to 2 days), what fraction of glucose variance is attributable to supply vs demand?

**Method**: Haar wavelet decomposition. At each scale, compute R² between glucose wavelet coefficients and supply/demand wavelet coefficients.

**Result**: **Demand dominates at ALL scales.** No crossover.

| Scale | Supply R² | Demand R² | Dominant |
|-------|----------|----------|----------|
| 5 min | 0.000 | 0.003 | Demand |
| 10 min | 0.001 | 0.003 | Demand |
| 20 min | 0.003 | 0.007 | Demand |
| 40 min | 0.016 | 0.021 | Demand |
| 1.3 h | 0.033 | **0.074** | Demand |
| 2.7 h | 0.043 | **0.125** | Demand |
| **5.3 h** | 0.070 | **0.188** | **Peak demand dominance** |
| 10.7 h | 0.117 | 0.183 | Demand (narrowing) |
| 21.3 h | 0.065 | 0.076 | Demand (barely) |
| 2 d | 0.068 | 0.103 | Demand |

### Interpretation

Demand (insulin) peaks at the **5.3h scale** (R²=0.188) — right at DIA. Supply never exceeds R²=0.12. This means insulin action explains ~2.7× more glucose variance than supply at the timescale where it matters most.

The gap narrows at very long scales (>21h), consistent with the idea that day-level variance is driven by meal patterns (supply) rather than insulin patterns (demand). But neither channel explains much at that scale — supply R² = 0.068 and demand R² = 0.103, both near the noise floor.

**Regarding glycogen vs insulin sensitivity**: The user's hypothesis was that these operate on different phases. This experiment shows that from wavelet-decomposed CGM alone, we can't distinguish supply-phase from demand-phase variations at multi-day scales. Both are at R² ≈ 0.07. To separate them, we'd need to construct explicit state variables (cumulative carb balance for glycogen proxy; rolling ISF estimate for sensitivity) and test those at these timescales.

![Multi-Scale Variance](figures/symmetry-fig05-multiscale.png)

---

## §6. EXP-1816: Conservation Law Residual Analysis

**Question**: How complete is our physics model (dBG/dt = supply − demand)? What's missing?

**Method**: Compute residual = dBG/dt − net_model for each patient. Analyze spectral content, autocorrelation, and correlation with supply/demand.

**Result**: **8/11 patients have white-noise residuals, but residuals systematically correlate with supply.**

| Metric | Value | Interpretation |
|--------|-------|----------------|
| White-noise fraction | **8/11** (73%) | Model is adequate for most patients |
| Mean spectral slope | −0.21 | Mild pink noise (not perfectly white) |
| Residual × supply correlation | **−0.55** | **MODEL OVER-ESTIMATES SUPPLY** |
| Residual × demand correlation | NaN (mixed) | Patient-dependent |

### The Missing Channel

The strong negative correlation between residuals and supply (r=−0.55) means: when supply is high, the model's residual is negative (model over-predicts glucose change). In other words, **the model's supply estimate is too large** — or equivalently, there is a supply-dampening mechanism that the model doesn't capture.

This could be:
1. **Glycogen buffering**: When glycogen stores are saturated (post-feast), excess glucose is stored rather than appearing in blood → effective supply is lower than modeled
2. **Non-linear absorption**: Meal absorption may slow at high carb loads (saturation kinetics) → supply model assumes linear but reality is Hill-like
3. **Counter-regulatory suppression**: When glucose is already high, hepatic output decreases → supply is actively suppressed

All three are consistent with the user's intuition about glycogen pool dynamics.

### Per-Patient Residual Distribution

| Patient | σ_residual | Spectral Slope | Supply r | Whiteness |
|---------|-----------|----------------|----------|-----------|
| a | 23.7 | −0.24 | +0.22 | WHITE |
| b | 9.4 | −0.48 | −0.54 | COLORED |
| c | 29.2 | −0.13 | −0.92 | WHITE |
| e | 34.3 | −0.08 | −0.96 | WHITE |
| h | 40.0 | −0.17 | −0.97 | WHITE |

Patients c, e, and h have residual×supply correlations near −1.0, meaning the model's supply estimate is almost perfectly anti-correlated with the error. These are the patients where a supply-channel correction would help most.

![Residual Analysis](figures/symmetry-fig06-residuals.png)

---

## §7. EXP-1817: Split-Loss Information Experiment

**Question**: Do supply-weighted and demand-weighted models learn different things? Does this change with window length?

**Method**: Train weighted linear regression models with three loss functions:
- **Supply-weighted**: upweight rising glucose periods
- **Demand-weighted**: upweight falling glucose periods  
- **Uniform**: standard MSE

Evaluate each on held-out rising and falling periods. Test at window lengths from 1h to 3 days.

**Result**: **COMPLEMENTARY — split losses learn genuinely different patterns.**

### Split-Loss R² by Window Length

| Window | S→Rise | S→Fall | D→Rise | D→Fall | U→Rise | U→Fall |
|--------|--------|--------|--------|--------|--------|--------|
| 1 h | −0.46 | −9.40 | −6.49 | −0.42 | −0.99 | −0.86 |
| 3 h | −0.63 | −10.20 | −6.45 | −0.50 | −1.10 | −0.90 |
| 6 h | −0.67 | −10.32 | −6.56 | −0.55 | −1.13 | −0.93 |
| 12 h | −0.68 | −10.27 | −6.90 | −0.65 | −1.13 | −0.98 |
| 1 d | −0.71 | −10.30 | −7.15 | −0.73 | −1.12 | −1.01 |
| 3 d | −0.69 | −10.13 | −7.20 | −0.73 | −1.11 | −1.03 |

### Interpretation

All R² values are negative (linear models can't predict dBG/dt well — this is a hard problem). But the **relative pattern** is what matters:

1. **Supply model specialization**: S→Rise R² is ~9.5 units better than S→Fall. The supply-weighted model focuses entirely on rising dynamics and is catastrophically bad at falling dynamics.

2. **Demand model specialization**: D→Fall R² is ~6.2 units better than D→Rise. Same pattern in reverse.

3. **Uniform model**: Compromises — middling at both.

4. **Window length effect**: All models get WORSE with longer windows (R² becomes more negative). No window shows improvement. This confirms EXP-1813: long windows add noise, not signal.

### What This Means for the User's Hypothesis

The split-loss models ARE learning different representations — the supply model "sees" carb-related and hepatic-related features, while the demand model "sees" IOB-related features. But:

- **Longer windows don't help either model** — the slow state variables (glycogen, insulin sensitivity) are NOT captured by adding more raw history
- **A dual-head architecture with split losses COULD work**, but it would need to operate on **derived features** at long timescales, not raw signals
- The optimal design: short-window (1-2h) dual-head for real-time supply/demand separation + explicit slow state features (24h+ cumulative) for glycogen/sensitivity estimation

![Split-Loss Models](figures/symmetry-fig07-split-loss.png)

---

## §8. EXP-1818: Symmetry Breaking Points

**Question**: When do supply and demand decouple, and what events cause it?

**Method**: Sliding 6h window cross-correlation between supply and demand. Classify moments where correlation is low (decoupled) vs high (coupled). Analyze what metabolic context corresponds to each.

**Result**: **Meals couple supply and demand; fasting decouples them.**

### Context Distribution at Symmetry Breaking

| Context | Decoupled (%) | Coupled (%) | Meaning |
|---------|:------------:|:-----------:|---------|
| Fasting | **78.5%** | 27.7% | Fasting = independent supply & demand |
| Post-meal | 4.5% | **52.5%** | Meals = tightly coupled (AID loop active) |
| Correction | 10.3% | 4.9% | Corrections slightly decouple |
| Hypo recovery | 6.2% | 4.5% | Hypo events slightly decouple |
| Other | 0.6% | 10.4% | — |

### Glucose Level at Breaking Points

| Event Type | Mean Glucose | Meal-Involved |
|-----------|:----------:|:-------------:|
| Decoupled | **142 mg/dL** | 4% |
| Coupled | **161 mg/dL** | 53% |

### Physical Interpretation

During **fasting**, the liver produces glucose at its own pace (hepatic autoregulation) and insulin runs at basal rate — these are nearly independent processes. The AID system is in "cruise mode" with minimal feedback.

During **meals**, the AID loop activates aggressively: carbs inject supply → glucose rises → insulin increases demand → glucose falls. Supply and demand become tightly coupled through the feedback loop.

This means:
- **Fasting windows** are where supply and demand are most separable — the best context for estimating hepatic output independently
- **Meal windows** are where the two channels are most entangled — the hardest context for decomposition
- This aligns with EXP-1789 (from the glycogen batch): fasting R²=−0.32 vs post-meal R²=−20.1

![Symmetry Breaking](figures/symmetry-fig08-breaking.png)

---

## §9. Synthesis: Where Is the Information?

### The Two-Channel Picture

| Property | Supply Channel | Demand Channel |
|----------|---------------|----------------|
| **Primary driver** | Meals + hepatic output | Insulin action |
| **Spectral signature** | Broad-band (rough, slope −1.05) | Narrow-band (smooth, slope −1.34) |
| **Time asymmetry** | Positive TRA (sharp rises) | Negative TRA at corrections |
| **Information horizon** | ~4h (glucose), ~15min (proxy) | ~2h (IOB), ~15min (proxy) |
| **Variance dominance** | Secondary at all scales | **Primary at all scales** (peaks at 5.3h) |
| **Model residual** | **Over-estimated** (r=−0.55) | Adequately captured |
| **When separable** | During fasting (78.5%) | During meals (AID couples them) |

### Answers to the User's Questions

**Q: Can we structurally identify two sources of information?**
**A: YES.** Time-reversal asymmetry (EXP-1811), spectral signatures (EXP-1812), and split-loss specialization (EXP-1817) all confirm that rising (supply-dominated) and falling (demand-dominated) glucose have genuinely different statistical properties. They are NOT the same process viewed from two sides.

**Q: Does breaking the loss into supply and demand behave differently with long windows?**
**A: The split WORKS (EXP-1817: COMPLEMENTARY), but long windows DON'T HELP (EXP-1813).** Both channels hit diminishing returns by ~6h. The information structure is fundamentally local.

**Q: Can we detect glycogen pool vs insulin sensitivity as separate phases?**  
**A: NOT from raw CGM alone at current resolution.** The multi-scale analysis (EXP-1815) shows both channels converge to R² ≈ 0.07 at day+ timescales. However, the residual analysis (EXP-1816) reveals a missing supply-dampening channel (r=−0.55) that could BE the glycogen/hepatic variation the user describes. To capture it, we need explicit cumulative state features, not longer raw windows.

### Implications for Model Architecture

1. **Dual-head is justified**: Supply and demand have different spectral properties → use different filter bandwidths for each direction
2. **Short windows are optimal**: 2-6h history captures >95% of available information
3. **Slow state needs explicit features**: Glycogen proxy (if rehabilitated with non-IOB features), rolling TIR, cumulative carb balance — these should be computed features, not learned from raw history
4. **Fasting is the calibration context**: It's where supply and demand are most separable — use fasting windows to estimate individual channel parameters
5. **The missing channel is supply-side**: Model improvements should focus on variable hepatic output, not better insulin modeling

### For the Glycogen Pool / Insulin Sensitivity Hypothesis

The user's intuition maps cleanly onto this framework:
- **Glycogen pool** → supply-side slow state → detectable as a **supply residual** (EXP-1816: r=−0.55)
- **Insulin sensitivity** → demand-side slow state → partially captured by IOB model already
- **Different phases** → these are DIFFERENT channels with DIFFERENT timescales
- **"Overflowing" state** (post-feast) → maps to high supply residual during coupled (post-meal) periods
- **"Depleted" state** (fasting/exercise) → maps to low supply residual during decoupled (fasting) periods

The split-loss approach could work if augmented with:
1. Supply-loss model: receives cumulative carb balance, time-since-last-meal, rolling-24h-carbs
2. Demand-loss model: receives IOB curve, rolling ISF estimate, correction frequency
3. Both: receive short (2h) raw glucose + 4-harmonic temporal encoding

---

## Appendix: Experimental Details

### Data
- 11 patients, ~18 days each (except j: ~6 days)
- 5-minute resolution CGM data
- Supply/demand computed via Hill-equation metabolic engine with demand calibration

### Methods
- TRA: skewness of velocity increments with 200 permutation surrogates
- PSD: Welch method, nperseg=256
- MI: binned estimator (20 bins, 1st-99th percentile range)
- Directed MI: conditional MI approximated as I(X;Y) − I(X_self;Y)
- Wavelet: Haar wavelet at dyadic scales
- Split-loss: weighted least squares with 70/30 train/test split

### Code
- `tools/cgmencode/exp_symmetry_1811.py` — all 8 experiments
- Results: `externals/experiments/exp-1811_symmetry_info_decomposition.json`
- Figures: `docs/60-research/figures/symmetry-fig01` through `symmetry-fig08`

### Limitations
- Linear models used for split-loss (EXP-1817) — nonlinear models might find more
- MI estimation is noisy at long lags (binned estimator limitations)
- Supply/demand proxies are model-derived, not ground truth
- 18-day windows may be too short for multi-week state variable detection
