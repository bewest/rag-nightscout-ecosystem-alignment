# Capability Report: Glucose Forecasting

**Date**: 2026-04-07 | **Overnight batch**: EXP-800 → EXP-875 (76 experiments) | **Patients**: 11

---

## Capability Definition

Predict future blood glucose from CGM readings, insulin delivery, and carbohydrate records at horizons from 5 to 60 minutes.

---

## Current State of the Art

| Horizon | Best R² | Best MAE (mg/dL) | Method |
|---------|---------|-------------------|--------|
| 5 min | 0.978 | 5.5 | Ridge + physics + circadian |
| 15 min | 0.902 | ~9 | Ridge + 16 enhanced features (EXP-830 validated) |
| 30 min | 0.775 | ~17 | Ridge + 16 enhanced features (EXP-830 validated) |
| 60 min | 0.534 | ~27 | Ridge + 16 extended features |

**Production champion**: Ridge regression on physics features: `[bg, Σsupply, Σdemand, Σhepatic, residual, sin(h), cos(h), bias]`. This beat the 134K-parameter transformer at all horizons beyond 15 minutes — physics provides features, statistics provides prediction.

**Alternative (transformer)**: Per-patient fine-tuned CGMGroupedEncoder (d=48, L=3, 67K params) achieves 10.59 mg/dL MAE overall. Clarke Error Grid Zone A+B = 97.1%.

### How the Architecture Evolved

| Phase | Key Advance | Impact |
|-------|-------------|--------|
| Physics-residual composition | Supply/demand decomposition | 8.2× on synthetic |
| Per-patient fine-tuning | Patient-specific adaptation | −8–15% MAE |
| Spike cleaning (σ=2.0) | Data quality | +52% R² (largest single gain) |
| Circadian correction | sin/cos(2πh/24) | +0.474 R² at 60 min |
| Asymmetric windows | More history, less future | −1.47 MAE at h30 |
| Window transfer (w48→w144) | Curriculum pretraining | −1.21 MAE at w144 |
| Ridge on physics features | Linear model on rich features | SOTA — simpler is better |

---

## Overnight Results (EXP-800–875): What Moved the Needle

### Validated improvements (EXP-830: Final Validated Benchmark)

| Horizon | Prior Base | Enhanced | Δ | Method |
|---------|-----------|----------|---|--------|
| 15 min | 0.899 | **0.902** | +0.003 | Combined best features (16 feat) |
| 30 min | 0.765 | **0.775** | +0.010 | Lagged BG + velocity + accel |
| 60 min | 0.509 | **0.534** | +0.025 | Combined best features (16 feat) |

### What contributed to the +0.025 gain

| Experiment | 60-min Δ | What it adds |
|------------|----------|-------------|
| EXP-803 Extended features | +0.021 | Lagged supply/demand, rate-of-change |
| EXP-824 Combined best | +0.022 | Cherry-picked features from 801–823 |
| EXP-822 Proper causal AR | +0.013 | AR corrections with lag ≥ horizon |
| EXP-818 BG accel | +0.009 | d²BG/dt² as feature |
| EXP-823 Extended history (1h) | +0.012 | More lookback context |
| EXP-812 Lagged BG | +0.015 | BG values at t-3, t-6, t-12 |

### Two-Stage Ridge+AR: Data leakage (EXP-811)

| Horizon | Ridge alone | Ridge+AR | Δ |
|---------|------------|---------|---|
| 30 min | 0.765 | **0.936** | +0.171 |
| 60 min | 0.509 | **0.941** | +0.432 |

⚠️ **Critical caveat**: AR residual correction at horizon h requires lag ≥ h steps to be causal. EXP-811 uses lag-1 AR on 60-min predictions — accesses glucose 55 minutes into the future. **This is data leakage.** Properly causal AR (EXP-822, lag-12) yields only +0.013.

### Information-theoretic ceiling (EXP-826, EXP-850)

| Estimate | 60-min R² |
|----------|-----------|
| Current best (validated) | 0.534 |
| Per-patient oracle ceiling | 0.613 |
| Oracle + velocity + accel | 0.620 |
| **Remaining headroom** | **~0.09** |

---

## What the 76 Overnight Experiments Ruled Out

| Approach | 60-min Δ | Verdict |
|----------|----------|---------|
| Kernel Ridge (RFF) | +0.027 | ⚠️ Minor nonlinear gain |
| Piecewise linear | +0.025 | ⚠️ Same as combined linear |
| Stacked generalization | +0.024 | ⚠️ Marginal over base |
| Multi-horizon cascade | +0.002 | ❌ Negligible |
| Nonlinear supply-demand | −0.016 | ❌ Harmful |
| Adaptive feature selection | −0.012 | ❌ Harmful |
| Feature interaction terms | −0.001 | ❌ No signal |
| Ridge ensemble | −0.001 | ❌ Single model sufficient |
| Lasso / ElasticNet | catastrophic | ❌ Dead end |

**Bias-variance decomposition** (EXP-843): 99.9% bias, 0.1% variance. The model isn't overfitting — it's **underfitting** because the available features lack information to predict 60-minute glucose.

---

## Error Anatomy

| BG Range | MAE (mg/dL) | Fraction |
|----------|-------------|----------|
| < 80 | 26.6 | 8% |
| 80–120 | 21.5 | 33% |
| 120–180 | 29.8 | 32% |
| 180–250 | 37.0 | 18% |
| > 250 | 46.0 | 9% |

Error scales with BG level — MAE nearly doubles from target range to hyperglycemia. Worst context: "night + rising" (MAE = 38.4 mg/dL). Residual autocorrelation decorrelates at 13.9 lags (70 min) — the model systematically under-reacts to rapid changes.

---

## Validation Vignette

**Patient h — the hardest case**: R² = 0.200 at 60 min (base), ceiling 0.359. Patient h has tightest control (TIR 85%, mean BG 119) — so little variance that sensor noise dominates signal.

**Patient i — the best case**: R² = 0.660 at 60 min (base), ceiling 0.754. High glycemic variability (TBR 10.7%) — paradoxically easier to predict because signal dominates noise.

---

## Key Insight

Physics provides features; statistics provides prediction. The overnight batch confirms the Ridge architecture is **near-optimal for available data**: 76 experiments produced a maximum validated gain of +0.025 R². The information-theoretic ceiling (R²≈0.61) leaves ~0.08 headroom — achievable only with new data dimensions (activity, meal composition, hormonal state), not better models.
