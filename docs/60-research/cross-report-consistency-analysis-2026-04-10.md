# Cross-Report Consistency Analysis

**Date**: 2026-04-10
**Scope**: All reports in `docs/60-research/`
**Purpose**: Identify contradictions, assess severity, recommend corrections

---

## 1. LSTM Validity Contradiction

### The Claims

| Report | Claim | Evidence |
|--------|-------|----------|
| `advanced-architectures-benchmark-report` | XGBoost→LSTM R²=0.581 (single split); 0.549 (5-fold CV) | EXP-1128, EXP-1130 |
| `causal-benchmark-report` | LSTM **hurts** by −0.068 in 5-fold CV; R²=0.386 pipeline CV | EXP-1180 |

### Analysis: **REAL CONTRADICTION — partially acknowledged**

These are **not** the same experiment. The key differences:

1. **Baseline differs**: The advanced-architectures report measures LSTM on top of base XGBoost (R²≈0.570 single split). The causal-benchmark report measures LSTM on top of *enhanced* XGBoost with causal features (R²=0.477 CV).

2. **CV methodology differs**: EXP-1130 (advanced-architectures) reports R²=0.549 in 5-fold CV for the full pipeline. EXP-1180 (causal-benchmark) reports R²=0.386 for the pipeline, with **0/11 patients improving** from LSTM in CV. These cannot both be correct for the same pipeline.

3. **The later report supersedes**: The causal-benchmark report explicitly states: *"The single-split R²=0.581 was an artifact of the LSTM memorizing the specific temporal boundary."* It also notes three separate experiments (EXP-1171, 1142, 1180) confirming LSTM hurts in CV.

### Verdict

**The contradiction is real but chronologically resolved.** The advanced-architectures report was written first and contains an optimistic 5-fold CV result (R²=0.549) that was later invalidated by more rigorous evaluation. However, the advanced-architectures report **was never updated** to reflect this invalidation.

### Corrections Needed

1. **`advanced-architectures-benchmark-report`** needs a prominent disclaimer at the top: the LSTM results were later invalidated by EXP-1180 in the causal-benchmark report. The validated SOTA is Enhanced XGBoost at R²=0.477 (5-fold CV), not XGBoost→LSTM at R²=0.581.

2. The SOTA progression tables in multiple reports still cite R²=0.581 as validated. Any report written *before* the causal-benchmark discovery should carry a note that this figure was superseded.

---

## 2. AR Correction Mechanism: Near-Zero Coefficients vs. +0.332 Improvement

### The Claims

| Report | Claim | Evidence |
|--------|-------|----------|
| `pipeline-diagnostics-report` | AR(2) coefficients ≈ 0 at lag-12 (α=0.002, β=0.021) | EXP-1237 |
| `ensemble-validation-robustness-report` | Ensemble+AR R²=0.781 (+0.332 over single model) | EXP-1211 |

### Analysis: **APPARENT CONTRADICTION — well explained**

This is the strongest-explained "paradox" in the research. The mechanism is:

1. **AR coefficients ARE near-zero at 60-minute lags** — the pipeline-diagnostics report is correct. Autocorrelation decays from 0.48 at lag-1 (5 min) to ≈0.00 at lag-12 (60 min).

2. **The ensemble operates at multiple horizons** (30, 45, 60, 90, 120 min). The 30-minute sub-model uses lag-6 residuals where ACF is still ~0.05-0.10 — enough to provide useful correction.

3. **The gain is multiplicative, not additive**:
   - Naive AR on single 60-min model: +0.004 (confirms near-zero coefficients)
   - Ensemble alone (no AR): +0.028
   - Ensemble + AR: **+0.332**

4. The pipeline-diagnostics report explicitly explains: *"It's not the AR correction on the FINAL prediction that matters — it's the AR-enhanced SHORT-horizon sub-models that improve the ensemble."*

### Verdict

**Apparent contradiction only.** Both claims are correct and the multi-scale mechanism is well-documented. The short-horizon sub-models (30 min) have meaningful AR signal; the stacking meta-learner exploits the decorrelated errors across horizons. The individual coefficient near-zero finding is actually *necessary context* for understanding why the ensemble architecture is required.

### Corrections Needed

None — this is properly handled. The pipeline-diagnostics report contains an explicit "AR-Ensemble Mechanism Explained" section that resolves the paradox. One suggestion: add a forward-reference from the near-zero coefficient finding to the mechanism explanation for readers who encounter them in order.

---

## 3. PK Lead Leakage Paradox: "100% Leakage" vs. +0.045 in 5-fold CV

### The Claims

| Report | Claim | Evidence |
|--------|-------|----------|
| `causal-pk-leakage-report` | 100% leakage; causal projection adds exactly +0.000 | EXP-1161, EXP-1169 |
| `pk-lead-deep-dive-report` | +0.045 R² improvement in 5-fold CV; 11/11 patients improve | EXP-1154 |

### Analysis: **REAL CONTRADICTION — different definitions of "leakage"**

These reports use different methodologies and reach incompatible conclusions:

1. **The deep-dive report** (written first) tests "PK lead" = shifting raw PK channels forward by 45 minutes. In 5-fold CV, this gives +0.045 (all patients win). It estimates 30-50% is leakage.

2. **The causal-leakage report** (written later) decomposes the signal into:
   - **Causal projection**: project current IOB forward using known decay curves → +0.000 (zero benefit, because XGBoost already learns the decay from the 2h PK window)
   - **Leaked component**: future bolus decisions that change the IOB trajectory → +0.125 (single-split; +0.134 in 5-fold CV per EXP-1169)

3. **How "100% leakage" and "+0.045 CV" coexist**: The "100% leakage" refers specifically to the *causal projection method* — the model can already predict IOB decay internally, so the projection adds zero *new* information. But the raw PK lead (+0.045 in CV) contains *both* the redundant decay signal AND future bolus information. The +0.045 CV improvement comes from learnable bolus patterns in historical data, which is technically leakage (future information unavailable at prediction time) but survives CV because bolus patterns are statistically consistent across time folds.

4. **The leakage survives CV** because:
   - Future boluses are *in the features* during both training and validation
   - TimeSeriesSplit prevents temporal contamination but doesn't prevent the model from learning that "bolus patterns at time T+45 are statistically predictable from features at time T"
   - This is a feature that would be *unavailable in production* (you don't know future boluses), making it real leakage despite CV survival

### Verdict

**Real contradiction in headline claims, but resolvable upon careful reading.** The 100% figure applies to the *causal projection method*, not to all PK lead approaches. The +0.045 is real in a statistical sense (it survives CV) but represents information that would be unavailable in production. The reports use "leakage" in subtly different ways.

### Corrections Needed

1. **`causal-pk-leakage-report`** should clarify that "100% leakage" refers to the causal projection method, not to the raw PK lead feature. A sentence like: *"The raw PK lead still shows +0.045 in CV (EXP-1154), but this reflects learnable future bolus patterns, not causal PK dynamics"* would resolve the apparent contradiction.

2. **`pk-lead-deep-dive-report`** should be updated with a note acknowledging the later causal decomposition that reinterprets the +0.045 as predominantly leakage rather than legitimate signal.

3. Both reports should converge on the same terminology: "causal leakage" (future information unavailable at prediction time) vs. "temporal contamination" (training data leaking into validation). The PK lead has the former but not the latter, which is why it survives CV.

---

## 4. Noise Ceiling Plausibility: Is the 0.073 Gap Realistic?

### The Claims

| Report | Claim | Source |
|--------|-------|--------|
| Multiple reports | Noise ceiling R²=0.854 (σ=15 mg/dL CGM noise) | EXP-1055 |
| `ensemble-validation-robustness-report` | Ensemble+AR achieves R²=0.781 | EXP-1211 |
| `combination-ablation-report` | Gap = 0.073; requires external data to close | EXP-1226 |
| `diabetes-domain-learnings` | Unmodeled: meals (~0.03-0.05), exercise (~0.01-0.02), AID (~0.01-0.02) | Domain review |

### Analysis: **PLAUSIBILITY CONCERN — under-acknowledged**

The noise ceiling is calculated by adding Gaussian noise (σ=15 mg/dL) to clean targets and computing R² between clean and noisy. This gives R²=0.854. The gap to the SOTA (0.781) is only 0.073.

**Problem**: The unmodeled variance sources sum to more than 0.073:

| Source | Estimated R² impact | Notes |
|--------|-------------------|-------|
| Meal composition | +0.03–0.05 | No meal data in features |
| Exercise/activity | +0.01–0.02 | No exercise data |
| AID algorithm decisions | +0.01–0.02 | Future temp basals/SMBs unknown |
| Inter-day variability | Unknown | Sleep, stress, hormones |
| CGM noise reduction | +0.01–0.02 | Hardware limitation |

**Sum of midpoints**: ~0.09 — already exceeds the 0.073 gap.

This raises a critical question: **Is the ensemble+AR R²=0.781 overfitting, or is the noise ceiling underestimated?**

The `combination-ablation-report` does break this down: 76% systematic error, 24% irreducible noise. But the systematic error (meals, exercise, etc.) should plausibly account for more than 0.073 R² units given that:

- Post-meal glucose excursions are the dominant source of glucose variability
- No meal data whatsoever is in the feature set
- The domain-learnings report calls meals *"the hard, unsolved problem"*

**Possible explanations for why the gap is small**:

1. The glucose window (2h of prior readings) already captures post-meal trajectories implicitly — the model sees the rising glucose and learns to predict the continuation
2. The AR correction at short horizons effectively acts as a "meal echo" detector
3. The noise ceiling calculation may be too optimistic — real CGM noise is non-Gaussian (has drift, compression artifacts)

### Verdict

**The 0.073 gap is suspiciously small** given the known unmodeled factors. The reports acknowledge this gap but don't adequately interrogate it. Two scenarios:

- **Optimistic**: The 2h glucose window captures most meal information implicitly, and the remaining 0.073 truly represents only the unpredictable component of meals/exercise.
- **Pessimistic**: The noise ceiling is poorly calibrated (real CGM noise is non-Gaussian), or the ensemble+AR is slightly overfit despite 5-fold CV (e.g., AR correction exploiting data-specific autocorrelation patterns).

### Corrections Needed

1. A sensitivity analysis of the noise ceiling at different σ values (10, 15, 20, 25 mg/dL) should be presented, with discussion of non-Gaussian CGM noise characteristics.

2. The gap analysis should explicitly address: if meals account for 0.03-0.05 R² and the total gap is 0.073, then the model is already implicitly capturing most meal effects through the glucose window alone. This should be stated and validated (e.g., test on meal-annotated subsets).

3. Consider whether σ=15 mg/dL is appropriate. Modern CGMs (Dexcom G7) have MARD ~8-9%, which at mean glucose ~153 mg/dL gives σ≈13-14 mg/dL. At σ=13, ceiling would be higher (~0.88), making the gap larger (~0.10) and more plausible.

---

## 5. Patient h Interpolation Paradox

### The Claims

| Report | Claim | Evidence |
|--------|-------|----------|
| Multiple reports | Patient h's poor R² is caused by 64% NaN rate | EXP-1033 |
| `ensemble-validation-robustness-report` | Full interpolation **hurts** patient h by −0.141 | EXP-1214 |
| `clinical-metrics-diagnostics-report` | No strategy rescues patient h; recommend exclusion | EXP gap analysis |

### Analysis: **APPARENT CONTRADICTION — well explained**

The paradox: if NaN is the problem, why does filling NaN make it worse?

The explanation is sound and consistently presented across reports:

1. **For patients with 10-20% NaN**: Interpolation smooths small gaps, improves prediction quality. 10/11 patients benefit (+0.010 to +0.067).

2. **For patient h (64% NaN)**: Cubic interpolation *fabricates* most of the signal. The model trains on smooth interpolated curves and learns to predict smoothness. When evaluated on *real* (noisy, gapped) glucose data, the model's learned smooth predictions fail catastrophically (−0.141).

3. **The root cause is not "NaN" per se** — it's *insufficient real data*. Only 36% of timesteps have valid readings. No statistical method can recover information that was never measured.

4. The recommendation to exclude patient h (>50% NaN threshold) is consistent across reports and well-justified.

### Verdict

**Apparent contradiction only — well explained.** The reports correctly distinguish between "small gaps that interpolation can fix" and "majority-missing data where interpolation fabricates signal." The −0.141 result is actually *evidence for* the NaN diagnosis: it proves the remaining 36% of real data has insufficient information content to support accurate prediction.

### Corrections Needed

None — this is the best-explained paradox in the report set. The only minor improvement would be adding a sentence to the executive summaries: *"NaN is the root cause because it indicates insufficient data, not because the NaN values themselves need filling."*

---

## 6. Depth-2 vs. Depth-3 Contradiction

### The Claims

| Report | Claim | Evidence |
|--------|-------|----------|
| `combined-winners-ensemble-report` | Depth-3 dominates for 6/11 patients | EXP-1112 |
| `winner-stacking-production-report` | Depth-2 optimal for 7/11 patients; +0.005 R² over depth-3 | EXP-1255 |

### Analysis: **REAL CONTRADICTION — partially explained**

The reports give opposite recommendations using different patient counts ("6/11" vs "7/11"):

1. **Same feature set**: Both experiments use the same 186-feature builder. This rules out "different features" as the explanation.

2. **The production report's explanation**: *"With 186 features and ~30K training samples, depth-3 trees overfit by creating too many interaction terms. Depth-2 restricts to pairwise feature interactions, which is sufficient for the linear metabolic dynamics."*

3. **But this doesn't explain the flip**: If the feature set is the same, why did depth-3 win in EXP-1112 but depth-2 win in EXP-1255? Possible explanations not stated in the reports:
   - **Different CV methodology**: EXP-1112 may have used a single train/test split while EXP-1255 used 5-fold CV, where depth-2's regularization advantage shows
   - **Different hyperparameters**: Other XGBoost settings (learning rate, n_estimators, regularization) may have changed between experiments
   - **Different evaluation metric**: Though both report R², the aggregation method may differ
   - **Feature count growth**: The 186-feature count may have grown between experiments, pushing the optimal depth down

4. **The magnitude is small**: The difference is only 0.005 R² — within the noise band for many patients. This suggests both depths are near-equivalent, and the "winner" depends on subtle evaluation details.

### Verdict

**Real but minor contradiction.** The flip from depth-3 to depth-2 is not adequately explained by the reports. The most likely cause is a change in CV methodology (single-split → 5-fold), where depth-2's stronger regularization shows its advantage. The practical impact is small (0.005 R²).

### Corrections Needed

1. **`winner-stacking-production-report`** (EXP-1255) should acknowledge the prior depth-3 finding (EXP-1112) and explain what changed. A sentence like: *"This contradicts EXP-1112 which found depth-3 optimal on a single split; the difference reflects depth-2's regularization advantage under 5-fold CV"* would suffice.

2. Both reports should note that depth-2 and depth-3 are within noise margins for most patients, and the choice is not critical.

---

## Summary of Findings

| # | Contradiction | Type | Severity | Acknowledged? | Correction Needed? |
|---|---------------|------|----------|---------------|-------------------|
| 1 | LSTM R²=0.581 vs. −0.068 CV | **Real** | **High** | Partially (later report invalidates, earlier not updated) | **Yes** — add disclaimer to earlier report |
| 2 | AR coefficients ≈0 vs. +0.332 gain | Apparent | Low | **Yes** — multi-scale mechanism explained | No |
| 3 | 100% leakage vs. +0.045 CV | **Real** | **Medium** | Partially (different definitions not reconciled) | **Yes** — align terminology |
| 4 | 0.073 gap vs. unmodeled variance | **Concern** | **Medium** | Partially (gap listed but not interrogated) | **Yes** — sensitivity analysis needed |
| 5 | NaN root cause vs. interpolation hurts | Apparent | Low | **Yes** — well explained | No |
| 6 | Depth-2 vs. depth-3 | **Real** | **Low** | Partially (not cross-referenced) | **Yes** — minor cross-reference |

### Priority Actions

1. **High**: Add invalidation notice to `advanced-architectures-benchmark-report` re: LSTM results
2. **Medium**: Reconcile PK leakage terminology between the two PK reports
3. **Medium**: Add noise ceiling sensitivity analysis (varying σ, non-Gaussian noise)
4. **Low**: Cross-reference depth-2/depth-3 findings between reports
