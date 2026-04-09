# EXP-841–850: Error Anatomy & Information Budget

**Wave theme:** The model class is exhausted (linear R²=0.534, nonlinear +0.002).
The remaining 0.466 gap is **information deficit**, not model deficit.
This wave dissects the error to understand WHERE, WHY, and HOW MUCH
of the gap is reducible — and what new information sources could close it.

**Prior art summary:**

| Result | Value | Source |
|--------|-------|--------|
| Linear SOTA (60 min) | R² = 0.534 | EXP-830: 16-feature ridge |
| Nonlinear best | R² = 0.536 | EXP-831: kernel ridge (+0.002) |
| Linear oracle ceiling | R² = 0.613 | Requires future BG velocity |
| Worst patient (h) | R² = 0.153 | 3.5× below mean |
| Population mean | R² = 0.509 | Across 11 patients |

**Infrastructure reuse from EXP-801:**
`_build_features_base()`, `_build_enhanced_features()`, `_ridge_predict()`,
`_r2()`, `_get_hours()`, `_compute_flux()`, `load_patients()`, `compute_supply_demand()`

**Run command:**
```bash
PYTHONPATH=tools python -m cgmencode.exp_autoresearch_841 --detail --save --max-patients 11
```

---

## EXP-841: Residual Context Fingerprinting

**Description:** Partition prediction residuals by physiological context
(BG range × metabolic state × time-of-day) to build an error heatmap
showing exactly where the model fails.

**What it tests:** Is the R² = 0.466 error gap uniformly distributed, or
concentrated in specific physiological contexts? If concentrated, those
contexts define the information frontier.

**Method:**
1. Run 16-feature ridge at 60 min on all patients (70/30 split).
2. Compute signed residuals `ε = y_pred − y_actual` on validation set.
3. Bin each residual into a 3D context grid:
   - **BG range:** hypo (<70), low-normal (70–100), normal (100–140),
     elevated (140–180), high (180–250), very-high (>250) → 6 bins
   - **Metabolic state:** fasting (COB<5 & IOB<0.5), post-meal (COB≥5),
     correction (IOB≥0.5 & COB<5), active (COB≥5 & IOB≥0.5) → 4 bins
   - **Circadian phase:** overnight (00–06), dawn (06–10), midday (10–14),
     afternoon (14–18), evening (18–22), late (22–00) → 6 bins
4. For each cell: compute count, mean |ε|, mean ε (bias), std(ε), local R².
5. Rank cells by total error contribution (count × mean |ε|²).

**Output schema:**
```python
{
  "per_patient": [{
    "patient": "a",
    "r2_overall": 0.55,
    "top_5_error_cells": [
      {"bg_bin": "high", "state": "post_meal", "phase": "midday",
       "n": 342, "mae": 28.4, "bias": -12.1, "std": 22.3,
       "pct_of_total_error": 18.2}
    ],
    "error_heatmap": {"hypo|fasting|overnight": {...}, ...}
  }],
  "population_top_10_cells": [...],
  "error_concentration_gini": 0.XX  // 1.0 = all error in one cell
}
```

**Expected outcome:** Error is NOT uniform — post-meal + high BG contexts
likely contribute 40–60% of total error despite being 15–20% of timesteps.
This proves meals are the dominant information gap.

**Leakage risk:** ✅ None. Residuals computed on held-out validation set.
Context bins use only current/past values.

---

## EXP-842: Patient-h Forensic Diagnostic

**Description:** Deep forensic analysis of patient h (R² = 0.153) to
determine whether the failure is due to data quality, physiology, or
missing information.

**What it tests:** Is patient h's poor performance caused by (a) sensor
noise / data artifacts, (b) extreme or unusual physiology, (c) missing
treatment data (unlogged meals/corrections), or (d) the model simply
being wrong for this patient's dynamics?

**Method:**
1. Compute summary statistics for patient h vs population:
   - BG volatility: std(BG), std(ΔBG/Δt), % readings >250 or <70
   - Treatment density: meals/day, boluses/day, mean IOB, mean COB
   - Data quality: % missing, consecutive-gap lengths, flat-line segments
   - Sensor noise: high-frequency power (FFT > 1/30min), spike rate
2. Feature correlation analysis:
   - Pearson/Spearman correlation of each feature with target for h vs all
   - Are supply/demand features predictive at all for patient h?
3. Sliding-window R² profile:
   - Compute R² in rolling 7-day windows across patient h's data
   - Identify if there are GOOD periods (R² > 0.4) and BAD periods (R² < 0.1)
4. Oracle test:
   - Fit ridge with actual future BG as a feature (oracle ceiling for h alone)
   - If oracle R² is also low → data quality issue; if high → information gap
5. Cross-patient transfer:
   - Train on patients a–g,i–k, predict h → measures population fit
   - Train on h alone → measures personalization ceiling

**Output schema:**
```python
{
  "patient_h_profile": {
    "bg_std": XX, "bg_std_population_rank": "11/11",
    "delta_bg_std": XX, "meals_per_day": XX,
    "pct_missing": XX, "spike_rate_per_day": XX,
    "flat_segments_gt_30min": XX
  },
  "feature_correlations": {
    "h": {"bg": 0.XX, "supply": 0.XX, ...},
    "population_mean": {"bg": 0.XX, ...}
  },
  "rolling_r2": {
    "windows": [{"start": "day_1", "end": "day_7", "r2": 0.XX}, ...],
    "pct_windows_above_0.4": XX,
    "best_window_r2": XX, "worst_window_r2": XX
  },
  "oracle_r2_h": 0.XX,
  "cross_patient_r2": 0.XX,
  "self_trained_r2": 0.XX,
  "diagnosis": "data_quality | physiology | missing_info | model_mismatch"
}
```

**Expected outcome:** Patient h likely has either (a) much higher BG
volatility with unlogged meals, or (b) significant sensor noise / data
gaps. The rolling-window analysis will reveal if h has intermittent good
periods (suggesting missing data) or consistently poor fit (suggesting
different physiology).

**Leakage risk:** ✅ None, except the oracle test which is explicitly
labeled as an oracle upper bound, not a real model.

---

## EXP-843: Conformal Prediction Intervals

**Description:** Construct distribution-free prediction intervals using
split conformal prediction, providing guaranteed coverage without
distributional assumptions.

**What it tests:** Can we produce calibrated uncertainty estimates that
tell the user WHEN the model is likely wrong? And do the interval widths
correlate with the error-context cells from EXP-841?

**Method:**
1. Three-way split: train (60%), calibration (15%), test (25%).
2. Fit 16-feature ridge on train set.
3. **Calibration step:** Compute nonconformity scores on calibration set:
   `s_i = |y_actual_i − y_pred_i|`
4. For coverage level α ∈ {0.80, 0.90, 0.95}:
   - `q_α = quantile(s_calibration, α)`
   - Prediction interval: `[ŷ − q_α, ŷ + q_α]`
5. **Adaptive conformal:** Use local nonconformity (condition on BG range):
   - Separate q_α per BG bin from EXP-841
   - Produces tighter intervals when model is confident, wider when not
6. Evaluate on test set:
   - Empirical coverage: % of test points inside interval
   - Mean interval width (mg/dL)
   - Interval width ratio: adaptive / global
   - Sharpness: correlation between interval width and actual |error|

**Output schema:**
```python
{
  "per_patient": [{
    "patient": "a",
    "global_coverage_90": 0.XX, "global_width_90": XX,
    "adaptive_coverage_90": 0.XX, "adaptive_width_90": XX,
    "sharpness_corr": 0.XX,  // corr(interval_width, |error|)
    "narrowest_context": "normal|fasting|overnight",
    "widest_context": "high|post_meal|midday"
  }],
  "mean_coverage_90": 0.XX,
  "mean_global_width_90": XX,
  "mean_adaptive_width_90": XX,
  "coverage_guaranteed": true  // by conformal theory
}
```

**Expected outcome:** Global 90% intervals will be ~40–60 mg/dL wide
(clinically marginal). Adaptive intervals will be ~25 mg/dL in overnight/
fasting and ~70 mg/dL post-meal — proving the model "knows when it
doesn't know." Coverage guarantee holds by construction.

**Leakage risk:** ✅ None. Three-way split ensures calibration scores are
computed on data not seen during training. Test set is held out from both.

---

## EXP-844: Metabolic Regime Segmentation

**Description:** Use unsupervised clustering on metabolic features to
discover natural physiological regimes, then measure per-regime R²
to identify which regimes are predictable vs unpredictable.

**What it tests:** Are there fundamentally different metabolic operating
modes? If the model performs R² = 0.7 in regime A but R² = 0.2 in
regime B, then the aggregate R² = 0.534 is misleading — the model is
good in some modes and fundamentally limited in others.

**Method:**
1. For each timestep, compute a 6D context vector:
   `[BG, ΔBG/Δt, IOB, COB, metabolic_activity, hour_sin]`
2. Standardize and apply k-means with k ∈ {3, 4, 5, 6}.
3. Select k by silhouette score.
4. Label each regime by its centroid characteristics (e.g., "fasting-
   stable", "post-meal-rising", "correction-falling", "overnight-flat",
   "high-volatile").
5. Fit separate ridge models per regime (using only timesteps in that
   regime for train/val).
6. Compare:
   - Per-regime R² vs global R² (0.534)
   - Within-regime R² weighted sum vs global R²
   - Regime transition boundaries: are errors higher at transitions?

**Output schema:**
```python
{
  "best_k": 4,
  "regimes": [
    {"id": 0, "label": "fasting_stable", "pct_timesteps": 35.2,
     "centroid": {"bg": 112, "dbg": -0.1, "iob": 0.3, "cob": 0},
     "r2_within": 0.72, "mae_within": 8.1},
    {"id": 1, "label": "post_meal_rising", "pct_timesteps": 18.4,
     "centroid": {"bg": 168, "dbg": 2.1, "iob": 2.5, "cob": 32},
     "r2_within": 0.31, "mae_within": 29.7},
    ...
  ],
  "global_r2": 0.534,
  "weighted_regime_r2": 0.XX,  // Σ(pct_i × r2_i)
  "transition_error_premium": 0.XX,  // extra MAE at regime boundaries
  "per_patient": [...]
}
```

**Expected outcome:** 3–4 natural regimes will emerge. "Fasting/stable"
regime R² ≈ 0.7+ (highly predictable). "Post-meal" regime R² ≈ 0.25–0.35
(poorly predictable). This proves the R² gap is dominated by meal
uncertainty, not model inadequacy.

**Leakage risk:** ✅ None. Clustering uses only current/past features.
Per-regime models still use proper train/val splits within each regime.

---

## EXP-845: Bias-Variance-Noise Decomposition

**Description:** Decompose total prediction error into bias², variance,
and irreducible noise using bootstrap resampling, establishing what
fraction of error is fixable vs fundamental.

**What it tests:** Of the MSE = (1 − 0.534) × Var(y), how much is:
- **Bias²** — systematic under/over-prediction (fixable with better features)
- **Variance** — instability across training sets (fixable with more data or regularization)
- **Noise** — irreducible (sensor error + unobserved inputs like stress, exercise)

**Method:**
1. For each patient, create B=50 bootstrap training sets (sample with
   replacement from training portion).
2. Fit 16-feature ridge on each bootstrap sample.
3. Predict on the fixed validation set → matrix of predictions (B × N_val).
4. At each validation point i:
   - `ŷ_mean_i = mean over B bootstraps`
   - `bias²_i = (ŷ_mean_i − y_actual_i)²`
   - `variance_i = var over B bootstraps of ŷ_b_i`
   - `noise_i = MSE_i − bias²_i − variance_i` (residual)
5. Aggregate:
   - `E[bias²]`, `E[variance]`, `E[noise]` across all validation points
   - Fraction of MSE from each component
6. Stratify by BG range: does bias dominate at extremes, variance in the
   middle?

**Output schema:**
```python
{
  "per_patient": [{
    "patient": "a",
    "total_mse": XX,
    "bias_sq": XX, "bias_pct": XX,
    "variance": XX, "variance_pct": XX,
    "noise": XX, "noise_pct": XX
  }],
  "population_mean": {
    "bias_pct": XX, "variance_pct": XX, "noise_pct": XX
  },
  "by_bg_range": {
    "hypo":    {"bias_pct": XX, "variance_pct": XX, "noise_pct": XX},
    "normal":  {...},
    "high":    {...}
  }
}
```

**Expected outcome:** Variance will be very small (ridge is stable,
λ-regularized). Bias² will be moderate (~20–30% of MSE) — the model
systematically underpredicts excursions. Noise will dominate (~50–70%) —
confirming the information deficit hypothesis: most error comes from
inputs the model simply cannot observe.

**Leakage risk:** ✅ None. Bootstrap resamples from training data only.
Validation set is fixed and never seen during training.

---

## EXP-846: Contextual Error Attribution

**Description:** Attribute prediction error to specific causal contexts
(meals, corrections, basal drift, sensor noise, dawn phenomenon) using
counterfactual analysis.

**What it tests:** What percentage of total error is "caused by" each
context? This answers the practical question: if we had perfect meal
information, how much would R² improve?

**Method:**
1. Classify each validation timestep into overlapping event windows:
   - **Post-meal:** within 4h of carb entry > 5g
   - **Post-correction:** within 3h of bolus without carbs
   - **Dawn phenomenon:** 04:00–09:00 AND BG rising > 1 mg/dL per 5min
   - **Basal-only:** no meals or boluses within 4h
   - **Sensor-suspect:** |ΔBG| > 15 mg/dL in single 5min step (noise)
2. For each context c:
   - `MSE_c = mean(ε² for timesteps in context c)`
   - `MSE_not_c = mean(ε² for timesteps NOT in context c)`
   - `N_c = count of timesteps in context c`
   - `error_share_c = (N_c × MSE_c) / Σ(N_j × MSE_j)`
   - `R²_without_c`: R² if we exclude context c from evaluation
3. Compute mutual information I(ε²; context) to validate.
4. **Counterfactual test:** For post-meal windows, add perfect carb timing
   (exact carb onset ± 0) as a feature. Does R² improve? This estimates
   the "meal information value."

**Output schema:**
```python
{
  "per_patient": [{
    "patient": "a",
    "contexts": {
      "post_meal":       {"pct_time": 32, "mse": XX, "error_share": 0.48,
                          "r2_if_excluded": 0.68},
      "post_correction": {"pct_time": 15, "mse": XX, "error_share": 0.18,
                          "r2_if_excluded": 0.59},
      "dawn":            {"pct_time":  8, "mse": XX, "error_share": 0.07,
                          "r2_if_excluded": 0.55},
      "basal_only":      {"pct_time": 38, "mse": XX, "error_share": 0.15,
                          "r2_if_excluded": 0.54},
      "sensor_suspect":  {"pct_time":  3, "mse": XX, "error_share": 0.12,
                          "r2_if_excluded": 0.57}
    }
  }],
  "population_error_budget": {
    "meals": 0.XX, "corrections": 0.XX, "dawn": 0.XX,
    "basal": 0.XX, "sensor": 0.XX
  },
  "meal_counterfactual_r2_gain": 0.XX
}
```

**Expected outcome:** Post-meal contexts contribute ~45–55% of total error
despite being ~30% of timesteps. Perfect meal timing as a counterfactual
feature yields R² gain of ~0.03–0.06 — meaningful but not transformative,
because even with timing, absorption rate varies. Sensor-suspect steps
contribute ~10% of error from ~3% of timesteps — disproportionate.

**Leakage risk:** ⚠️ **Mild risk in counterfactual test only.** The
counterfactual adds "exact carb onset time" which is derived from
treatment data already in the feature set. This is labeled as an oracle
estimate, not a deployable feature. All other analyses are leakage-free.

---

## EXP-847: Mutual Information Feature Ceiling

**Description:** Compute mutual information between each feature and the
prediction target to establish the information-theoretic ceiling of the
current feature set.

**What it tests:** How much predictive information do the 16 features
collectively carry about BG(t+60)? Is ridge regression extracting all
available information, or is there nonlinear information being left on
the table?

**Method:**
1. Estimate mutual information I(X_i; y) for each of 16 features using
   k-nearest-neighbor estimator (Kraskov et al.):
   - KSG estimator with k=5 neighbors (bias-corrected, works for
     continuous variables)
2. Estimate joint MI I(X_1,...,X_16; y):
   - Use concatenated feature vector → KSG in 16D
   - Compare to sum of individual MIs (redundancy measure)
3. Compute conditional MI I(X_i; y | X_j) for top feature pairs:
   - Does feature i add information beyond feature j?
4. Compute **information utilization ratio**:
   - Ridge R² converted to bits: `H(y) × R² ≈ bits explained`
   - Joint MI I(X; y) = total bits available
   - Ratio = bits_explained / bits_available
5. Synthetic ceiling: add Gaussian noise with known MI and verify
   estimator accuracy.

**Output schema:**
```python
{
  "per_feature_mi": {
    "bg": {"mi_bits": XX, "rank": 1},
    "supply_sum": {"mi_bits": XX, "rank": 2},
    ...
  },
  "joint_mi_bits": XX,
  "sum_individual_mi_bits": XX,
  "redundancy_ratio": XX,  // joint / sum (< 1 means redundancy)
  "ridge_bits_explained": XX,
  "information_utilization": XX,  // ratio of bits used / available
  "nonlinear_info_gap": XX,  // joint_MI - ridge_bits (unexploited info)
  "per_patient": [...]
}
```

**Expected outcome:** Individual features are highly redundant (BG
dominates, supply/demand correlate with BG). Joint MI ≈ 0.55–0.70 bits
(in R²-equivalent terms). Information utilization ≈ 85–95%, confirming
that ridge extracts nearly all **linear** information. The nonlinear
gap (joint MI − ridge R²) ≈ 0.02–0.05 R² equivalent — consistent with
EXP-831's kernel ridge finding of +0.002.

**Leakage risk:** ✅ None. MI is estimated on training data and describes
feature informativeness, not prediction performance.

---

## EXP-848: Sensor Noise Floor Estimation

**Description:** Estimate the irreducible prediction error contributed by
CGM sensor noise using Allan deviation and consecutive-difference analysis.

**What it tests:** CGM sensors have ±10–15 mg/dL noise (MARD ~9–11%).
At 60-min horizon, how much of the MSE is simply sensor measurement
error that NO model could overcome?

**Method:**
1. **Allan deviation analysis:**
   - Compute overlapping Allan deviation σ_A(τ) for τ = 5, 10, 15, ...,
     120 min on raw BG traces.
   - At τ = 60 min, σ_A gives the expected BG uncertainty from sensor
     noise alone.
2. **Consecutive-difference estimator:**
   - For stable periods (|ΔBG_5min| < 2 mg/dL for 30+ min), estimate
     sensor noise as σ_sensor = std(ΔBG) / √2.
3. **Flat-line detection:**
   - Periods where BG is identical for 3+ readings → sensor is likely
     interpolating internally → count these as "sensor-limited" periods.
4. **Noise floor in MSE terms:**
   - `MSE_noise = 2 × σ_sensor² × (1 − autocorr(noise, lag=12))`
     (both prediction and target carry independent sensor noise)
   - `R²_ceiling_noise = 1 − MSE_noise / Var(y)`
5. Compare across patients — does patient h have worse sensor noise?

**Output schema:**
```python
{
  "per_patient": [{
    "patient": "a",
    "allan_dev_60min": XX,
    "sensor_noise_std": XX,  // mg/dL, from consecutive-difference
    "flat_line_pct": XX,
    "mse_from_noise": XX,
    "r2_ceiling_from_noise": 0.XX,  // max R² given sensor noise
    "current_r2": 0.XX,
    "gap_to_noise_ceiling": 0.XX  // ceiling - current
  }],
  "population_mean_noise_std": XX,
  "population_r2_noise_ceiling": 0.XX,
  "population_current_r2": 0.534,
  "noise_explains_pct_of_gap": XX  // % of (1-0.534) due to noise
}
```

**Expected outcome:** Sensor noise σ ≈ 8–12 mg/dL. At 60-min horizon,
noise-induced MSE ≈ 150–250 (mg/dL)². This accounts for ~15–25% of
total MSE, setting a hard R² ceiling of ~0.62–0.68. The remaining
gap between 0.534 and 0.62 (~0.08 R²) is the "accessible improvement
frontier" — achievable with better information but not a different model.

**Leakage risk:** ✅ None. Uses only raw BG time series properties.

---

## EXP-849: Error Temporal Autocorrelation & Persistence

**Description:** Analyze the temporal structure of prediction errors to
determine if errors are transient (random) or persistent (systematic
episodes the model consistently gets wrong).

**What it tests:** If errors are IID, the model is doing its best and
failures are random. If errors are autocorrelated and cluster into
"error episodes," there are systematic failure modes that could
potentially be detected and flagged in real-time.

**Method:**
1. Compute error time series ε(t) on validation set.
2. **Autocorrelation function:** ACF(ε², lag) for lag = 1...72 (6 hours).
3. **Error episode detection:**
   - Define "error episode" as consecutive run where |ε| > 1.5 × median(|ε|).
   - Measure: episode count, mean duration, max duration.
   - What triggers episodes? (Correlate onset with meals, corrections, etc.)
4. **Stationarity test:**
   - Augmented Dickey-Fuller test on ε(t) — are errors stationary?
   - Rolling mean/std of |ε| in 24h windows — does error level change
     over the 180-day period?
5. **Transition matrix:**
   - Discretize errors into {small, medium, large} by tertiles.
   - Compute 3×3 transition matrix P(error_size_{t+1} | error_size_t).
   - If diagonal-dominant → errors are persistent.
6. **Real-time error predictor:**
   - Can recent error magnitude predict next-step error magnitude?
   - Fit AR(3) on |ε(t)| → if R² > 0.3, error episodes are predictable.

**Output schema:**
```python
{
  "per_patient": [{
    "patient": "a",
    "acf_lag1": 0.XX, "acf_lag6": 0.XX, "acf_lag12": 0.XX,
    "acf_half_life_steps": XX,  // lag where ACF drops to 0.5
    "n_error_episodes": XX,
    "mean_episode_duration_min": XX,
    "max_episode_duration_min": XX,
    "episode_triggers": {"meal": XX, "correction": XX, "unknown": XX},
    "error_stationarity_p": 0.XX,
    "transition_matrix": [[0.6, 0.3, 0.1], ...],
    "error_ar3_r2": 0.XX  // predictability of error magnitude
  }],
  "population_mean_acf_lag1": 0.XX,
  "population_mean_episode_duration_min": XX,
  "error_predictable": true  // if mean AR3 R² > 0.3
}
```

**Expected outcome:** Errors are strongly autocorrelated (ACF lag-1 ≈
0.85+) with half-life of ~30–60 min. Error episodes last 1–3 hours on
average, triggered primarily by meals (60%) and corrections (25%).
The error-magnitude AR(3) achieves R² ≈ 0.4–0.6, meaning we can
PREDICT when the model is unreliable — enabling adaptive uncertainty
bands (feeds back to EXP-843).

**Leakage risk:** ✅ None. All analysis on validation-set residuals.
The AR(3) error predictor uses only past errors, not future.

---

## EXP-850: Grand Error Budget

**Description:** Synthesize findings from EXP-841–849 into a single
quantitative error budget that accounts for every component of the
R² = 0.466 unexplained variance.

**What it tests:** Can we fully account for all prediction error?
This experiment produces no new models — it combines the decompositions
from this wave into a coherent error attribution that answers: "What
would it take to reach R² = 0.7? 0.8? 0.9?"

**Method:**
1. Pull results from EXP-841–849 (or recompute if not available).
2. Construct layered error budget:
   - **Layer 1 — Sensor noise floor** (from EXP-848):
     MSE_sensor → R² ceiling from hardware alone
   - **Layer 2 — Model bias** (from EXP-845):
     MSE_bias → systematic errors (e.g., underpredicting excursions)
   - **Layer 3 — Model variance** (from EXP-845):
     MSE_variance → training instability (likely small)
   - **Layer 4 — Meal uncertainty** (from EXP-846):
     MSE_meal → error from meal-related contexts
   - **Layer 5 — Correction uncertainty** (from EXP-846):
     MSE_correction → error from insulin correction contexts
   - **Layer 6 — Physiological variability** (from EXP-844):
     MSE_regime → error from regime transitions and rare states
   - **Layer 7 — Temporal error clustering** (from EXP-849):
     MSE_episode → error concentrated in predictable episodes
3. Cross-validate: do layers sum to total MSE? Adjust for overlap.
4. **Improvement roadmap:** For each layer, estimate achievable R² gain:
   - Better sensor: reduces Layer 1 → +0.03–0.05 R²
   - Meal announcement: reduces Layer 4 → +0.04–0.08 R²
   - Adaptive uncertainty: doesn't reduce MSE but flags Layer 7
   - Patient-h intervention: reduces outlier drag → +0.02 R² on mean
5. **Theoretical R² ceiling** with all improvements combined.

**Output schema:**
```python
{
  "total_mse": XX,
  "total_unexplained_r2": 0.466,
  "error_budget": {
    "sensor_noise":       {"mse": XX, "pct": XX, "reducible": false},
    "model_bias":         {"mse": XX, "pct": XX, "reducible": true,
                           "how": "better features or nonlinear"},
    "model_variance":     {"mse": XX, "pct": XX, "reducible": true,
                           "how": "more data"},
    "meal_uncertainty":   {"mse": XX, "pct": XX, "reducible": "partially",
                           "how": "meal announcement, absorption modeling"},
    "correction_uncertainty": {"mse": XX, "pct": XX, "reducible": true,
                           "how": "better insulin PK model"},
    "regime_transitions": {"mse": XX, "pct": XX, "reducible": "partially",
                           "how": "regime detection + switching"},
    "unexplained":        {"mse": XX, "pct": XX, "reducible": "unknown"}
  },
  "improvement_roadmap": [
    {"intervention": "meal_announcement", "r2_gain": 0.XX, "effort": "low"},
    {"intervention": "better_sensor", "r2_gain": 0.XX, "effort": "hardware"},
    {"intervention": "patient_h_fix", "r2_gain": 0.XX, "effort": "low"},
    {"intervention": "regime_switching", "r2_gain": 0.XX, "effort": "medium"}
  ],
  "theoretical_ceiling_all_improvements": 0.XX,
  "patient_h_impact_on_population_mean": 0.XX
}
```

**Expected outcome:** The budget will show:
- ~20% sensor noise (irreducible without better hardware)
- ~40–50% meal/correction uncertainty (partially reducible with announcements)
- ~5–10% model bias (small, confirms model class is adequate)
- ~2–3% model variance (negligible, ridge is stable)
- ~15–20% physiological variability + unknown
- Theoretical ceiling with all feasible improvements: R² ≈ 0.65–0.72
- This establishes that R² ≈ 0.70 is the practical ceiling for
  60-min prediction from retrospective CGM data.

**Leakage risk:** ✅ None. This is a synthesis experiment — no new models,
only aggregation of prior results.

---

## Dependency Graph

```
EXP-841 (Residual Context)  ──────────┐
EXP-842 (Patient h Forensic)          │
EXP-843 (Conformal Intervals) ◄──────┤
EXP-844 (Regime Segmentation) ◄──────┤
EXP-845 (Bias-Variance-Noise) ◄──────┤──► EXP-850 (Grand Error Budget)
EXP-846 (Error Attribution)   ◄──────┤
EXP-847 (Mutual Information)          │
EXP-848 (Sensor Noise Floor)  ────────┤
EXP-849 (Error Persistence)   ────────┘
```

All experiments 841–849 are independent and can run in parallel.
EXP-850 synthesizes all results and should run last.

---

## Implementation Notes

### Shared helpers to add in `exp_autoresearch_841.py`:

```python
def _classify_context(bg, iob, cob, hour):
    """Return (bg_bin, metabolic_state, circadian_phase) tuple."""
    ...

def _ksg_mutual_information(x, y, k=5):
    """KSG mutual information estimator for continuous variables."""
    ...

def _allan_deviation(bg_series, tau_steps):
    """Overlapping Allan deviation at given tau."""
    ...

def _conformal_quantile(residuals, alpha):
    """Split conformal prediction quantile."""
    ...
```

### Risk Register

| Exp | Risk | Mitigation |
|-----|------|------------|
| 841 | Sparse cells in 3D grid | Collapse low-count cells; require n≥30 |
| 842 | Patient h may have legitimate different physiology | Include cross-patient baseline for comparison |
| 843 | Three-way split reduces training data | Use 60/15/25 to preserve most training data |
| 844 | k-means sensitive to initialization | Run 10 restarts, report silhouette stability |
| 845 | Bootstrap variance estimate noisy for small B | Use B=50, report confidence intervals on decomposition |
| 846 | Context windows overlap (post-meal + post-correction) | Allow overlap, report both exclusive and inclusive attribution |
| 847 | KSG estimator unreliable in 16D | Also report 2D pairwise MI as sanity check |
| 848 | Sensor noise varies with BG level (heteroscedastic) | Stratify noise estimation by BG range |
| 849 | Validation set may be too short for ACF at long lags | Limit ACF to lag ≤ 72 (6h), require n>500 for stationarity test |
| 850 | Error components may not be additive | Report overlap-adjusted budget + raw sum for transparency |

---

## Summary Table

| Exp | Name | Question | Key Metric |
|-----|------|----------|------------|
| 841 | Residual Context Fingerprinting | WHERE does the model fail? | Error concentration Gini coefficient |
| 842 | Patient-h Forensic Diagnostic | WHY does patient h fail? | Diagnosis category |
| 843 | Conformal Prediction Intervals | WHEN is the model uncertain? | Coverage & interval width |
| 844 | Metabolic Regime Segmentation | WHAT physiological modes exist? | Per-regime R² spread |
| 845 | Bias-Variance-Noise Decomposition | HOW MUCH error is fixable? | Noise % of total MSE |
| 846 | Contextual Error Attribution | WHAT CAUSES the error? | Per-context error share |
| 847 | Mutual Information Feature Ceiling | HOW MUCH info do features carry? | Information utilization ratio |
| 848 | Sensor Noise Floor Estimation | WHAT is the hardware limit? | R² ceiling from noise |
| 849 | Error Persistence & Autocorrelation | ARE errors predictable? | Error AR(3) R² |
| 850 | Grand Error Budget | WHAT would it take to improve? | Layered MSE attribution |
