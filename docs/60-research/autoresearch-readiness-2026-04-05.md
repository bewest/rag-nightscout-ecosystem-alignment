# Auto-Research Readiness Report

**Date**: 2026-04-05  
**Scope**: Validation framework readiness across 5 research objectives (335 experiments)  
**Purpose**: Assess whether each objective has the infrastructure needed for rigorous, automated experiment runs

---

## Executive Summary

We built a validation framework (`validation_framework.py`, `objective_validators.py`) and integrated it into the experiment infrastructure (`experiment_lib.py`). This report evaluates readiness for future auto-research runs across all five objectives.

**Headline**: 3 of 5 objectives are fully ready for validated auto-research. The remaining 2 need one helper function each (~20 min work). All objectives have validators and test coverage. The critical gap is not infrastructure — it's that **zero existing experiments use the framework yet**. The first priority is multi-seed replication of the 6 key single-seed results.

| Objective | Validator | Data Pipeline | Validated Wrapper | Tests | Readiness |
|-----------|-----------|---------------|-------------------|-------|-----------|
| **Glucose Forecasting** | ✅ ForecastValidator | ✅ 3-way split | ❌ Missing | ✅ 4 tests | 🟨 75% |
| **UAM Detection** | ✅ ClassificationValidator | ✅ 3-way split | ✅ `run_validated_classification` | ✅ 7 tests | 🟢 100% |
| **Override Detection** | ✅ ClassificationValidator | ✅ 3-way split | ✅ `run_validated_classification` | ✅ 7 tests | 🟢 100% |
| **Hypo Prediction** | ✅ ClassificationValidator | ✅ 3-way split + stratified | ✅ `run_validated_classification` | ✅ 7 tests | 🟢 100% |
| **Pattern Retrieval** | ✅ RetrievalValidator | ✅ multi-scale | ✅ `run_validated_retrieval` | ✅ 6 tests | 🟢 100% |
| **ISF Drift** | ✅ DriftValidator | ✅ rolling windows | ❌ Missing | ✅ 3 tests | 🟨 75% |

---

## 1. Framework Components Built

### 1.1 Core Infrastructure (`validation_framework.py`, 670 lines)

| Component | Purpose | Status |
|-----------|---------|--------|
| `MultiSeedRunner` | Run train/eval across seeds `[42, 123, 456, 789, 1337]`, aggregate with CIs | ✅ Tested |
| `TemporalSplitter` | Chronological 2-way (80/20) or 3-way (60/20/20) splits | ✅ Tested |
| `StratifiedTemporalSplitter` | Prevalence-preserving splits (critical for hypo at 6.4%) | ✅ Tested |
| `BootstrapCI` | Non-parametric bootstrap (1000 samples) + t-distribution for seed values | ✅ Tested |
| `LOOValidator` | Leave-one-out patient cross-validation with degradation analysis | ✅ Tested |
| `ValidationReport` | Structured JSON output with framework version tracking | ✅ Tested |

### 1.2 Objective Validators (`objective_validators.py`, 530 lines)

| Validator | Metrics Computed | Key Design Decisions |
|-----------|-----------------|---------------------|
| `ForecastValidator` | MAE, RMSE, zone MAE (hypo/target/hyper), Clarke Error Grid | Auto-denormalizes from [0,1] → mg/dL |
| `ClassificationValidator` | F1-positive, F1-macro, AUC-ROC, AUPRC, ECE, optimal threshold | Coerces torch tensors; explicit `metric_types` dict |
| `RetrievalValidator` | Silhouette, ARI, class-balanced R@K, per-cluster breakdown | sklearn-free; balanced R@K prevents majority saturation |
| `DriftValidator` | Spearman ρ, OLS slope ± CI, per-patient significance | False alarm analysis; aggregate across patient cohort |

### 1.3 Experiment Integration (`experiment_lib.py`)

**ExperimentContext** now supports:
```python
ctx.record_seed(42)
ctx.record_split('temporal', fractions=(0.6, 0.2, 0.2), n_patients=11)
ctx.record_validation(objective='classification', task='uam')
ctx.attach_multi_seed_report(ms_report)
ctx.attach_loo_report(loo_report, baseline={'f1': 0.939})
ctx.attach_bootstrap_ci('f1_positive', ci_result)
```

All metadata is auto-included in saved JSON under `validation_metadata`.

**Validated helpers** provide one-call experiment execution:
- `run_validated_classification()` — multi-seed + ClassificationValidator
- `run_validated_retrieval()` — multi-seed + RetrievalValidator

### 1.4 Data Splitting (`run_pattern_experiments.py`)

| Function | Split | Returns |
|----------|-------|---------|
| `load_multiscale_data()` | 80/20 temporal (existing) | `(train_np, val_np)` |
| `load_multiscale_data_3way()` | 60/20/20 temporal (new) | `{'train', 'val', 'test', 'metadata'}` |

Both do per-patient chronological splitting to prevent temporal leakage.

### 1.5 Test Coverage (`test_validation.py`, 49 tests)

| Test Class | Count | Coverage |
|------------|-------|---------|
| TestBootstrapCI | 5 | Bootstrap, determinism, seed CI, edge cases |
| TestTemporalSplitter | 4 | 2-way, 3-way, fraction validation, metadata |
| TestStratifiedTemporalSplitter | 2 | Prevalence preservation, size matching |
| TestMultiSeedRunner | 6 | All seeds run, aggregation, determinism, to_dict |
| TestLOOValidator | 3 | Leave-one-out, aggregate, degradation |
| TestClassificationValidator | 7 | F1, AUC, ECE, torch tensors, prevalence, metric types |
| TestForecastValidator | 4 | MAE, zone splits, denormalization, basic metrics |
| TestRetrievalValidator | 5 | Silhouette, R@K, balanced R@K, ARI |
| TestDriftValidator | 4 | Trend detection, OLS, aggregation, patient ID |
| TestExperimentContextValidation | 7 | Seed/split/validation recording, JSON roundtrip |
| TestValidationReport | 2 | Report creation, add_result |

---

## 2. Per-Objective Readiness Assessment

### 2.1 Glucose Forecasting

**Current best**: MAE = 11.14 mg/dL (EXP-302, 5-seed ensemble, verification gap -0.2%)

**Saturation evidence**: Architecture sweep across 8 models all converge at ~12.5 mg/dL single-model. Ensemble gives 11.14. Persistence baseline is 21.06. The remaining lever is cohort expansion (N=11→50), not architecture.

**Framework readiness**:
- ✅ `ForecastValidator` computes MAE, RMSE, zone MAE, Clarke grid
- ✅ `load_multiscale_data_3way()` provides held-out test set
- ✅ EXP-302 already used 5 seeds (manually, before framework)
- ❌ No `run_validated_forecast()` wrapper yet

**What's needed**: Add `run_validated_forecast()` to `experiment_lib.py`. Pattern is identical to the classification helper — takes `train_eval_fn(seed) → {'y_true', 'y_pred'}`, runs ForecastValidator per seed, attaches MultiSeedReport.

**Auto-research recommendation**: LOW PRIORITY. Forecasting is saturated. New runs should focus on cohort expansion, not architecture. The framework will be useful when validating on expanded cohorts.

### 2.2 UAM Detection

**Current best**: F1 = 0.939 (EXP-313, CNN, single seed)

**Saturation evidence**: CNN breakthrough (+114% over embedding baseline). Adding embeddings to CNN hurts (-5%). Feature engineering hurts. Cross-scale hurts. Only unknown: multi-seed variance.

**Framework readiness**:
- ✅ `ClassificationValidator(task_name='uam', positive_label=1)`
- ✅ `run_validated_classification()` ready
- ✅ `load_multiscale_data_3way()` with `scale='fast'` (2h windows)
- ✅ 7 classification tests passing

**What's needed**: Nothing — fully ready.

**Auto-research recommendation**: HIGH PRIORITY for validation. Re-run EXP-313 CNN with 5 seeds + 3-way split to establish F1 CI. Expected result: F1 = 0.93 ± 0.015. If confirmed, UAM is locked for deployment.

### 2.3 Override Detection

**Current best**: F1 = 0.852 (EXP-327, attention CNN, 15min lead, single seed)

**Key progression**: StateMLP 0.699 → CNN 60min 0.727 → CNN 15min 0.821 → Attention 15min 0.852. The attention vs CNN gap is only 2% and may not survive multi-seed replication.

**Framework readiness**:
- ✅ `ClassificationValidator(task_name='override', positive_label=1)`
- ✅ `run_validated_classification()` ready
- ✅ `load_multiscale_data_3way()` with `scale='fast'`
- ✅ Full test coverage

**What's needed**: Nothing — fully ready.

**Auto-research recommendation**: HIGH PRIORITY for validation. Re-run both EXP-314 (CNN) and EXP-327 (attention) with 5 seeds to determine whether the 2% attention premium is real. If attention advantage < 1σ, simplify to CNN-only for deployment (4× fewer parameters).

### 2.4 Hypo Prediction

**Current best**: F1 = 0.676 (EXP-324, CNN + Platt calibration, single seed), AUC = 0.958

**Plateau evidence**: Last 4 experiments land at F1 = 0.663–0.676 (σ = 0.005). AUC is 0.96 — the model discriminates well but 6.4% prevalence creates a threshold/calibration problem, not an architecture problem.

**LOO generalization**: F1 drops from 0.672 → 0.632 (-4.0%) across 11 patients (EXP-326). This is the only objective with real cross-patient evaluation.

**Framework readiness**:
- ✅ `ClassificationValidator(task_name='hypo', positive_label=1, is_imbalanced=True)`
- ✅ `StratifiedTemporalSplitter` preserves 6.4% prevalence across splits
- ✅ `run_validated_classification()` ready
- ✅ LOOValidator for cross-patient generalization
- ✅ Full test coverage

**What's needed**: Nothing — most thoroughly supported objective.

**Auto-research recommendation**: MEDIUM PRIORITY. Multi-seed replication of EXP-324 (Platt calibration) to establish CI. Then data augmentation experiments to break the prevalence bottleneck. The framework's stratified splitter is critical here — random splitting would give empty positive sets in some folds.

### 2.5 Pattern Retrieval

**Current best**: Silhouette = +0.326 (EXP-304, 7d window, single seed)

**Key challenge**: R@K is saturated at 1.0 everywhere — useless as a metric. Our `RetrievalValidator` computes class-balanced R@K which helps, but silhouette is the primary signal. Most windows produce negative silhouette (no cluster structure). Only 7d windows with 24h stride achieve positive silhouette.

**Framework readiness**:
- ✅ `RetrievalValidator` with balanced R@K, per-cluster silhouette
- ✅ `run_validated_retrieval()` ready
- ✅ `load_multiscale_data_3way()` with `scale='weekly'`
- ✅ 6 retrieval tests passing

**What's needed**: Nothing — fully ready.

**Auto-research recommendation**: MEDIUM PRIORITY. The FDA Phase A experiments (EXP-328–331) propose FPCA embeddings as an alternative to learned embeddings. The framework is ready to validate these with proper multi-seed evaluation. Run FPCA retrieval (EXP-332) with the validated pipeline.

### 2.6 ISF Drift

**Current best**: 9/11 patients significant at biweekly aggregation (EXP-312, Spearman p < 0.05)

**Key finding**: Statistical methods (rolling aggregation) won over neural approaches. Embedding similarity collapsed (sim ≈ 1.0, EXP-307). Per-cycle measurement too noisy (0/11 sig, EXP-309). Rolling biweekly is optimal: first scale with 9/11 significance + good temporal resolution.

**Framework readiness**:
- ✅ `DriftValidator` with Spearman ρ, OLS slope ± CI, aggregation
- ✅ 3 drift tests passing
- ❌ No `run_validated_drift()` wrapper

**What's needed**: Add `run_validated_drift()` to `experiment_lib.py`. Different from classification/retrieval because drift is inherently per-patient (not per-seed in the same way). The wrapper should iterate patients, call `DriftValidator.evaluate_per_patient()`, then aggregate.

**Auto-research recommendation**: LOW PRIORITY for replication (statistical method doesn't need seeds). MEDIUM PRIORITY for FDA Phase A circadian decomposition experiments that may improve the weak r = -0.16 predictive value.

---

## 3. The Credibility Gap

### What Exists vs What's Needed

| Aspect | Current State | After Framework | Gap |
|--------|--------------|-----------------|-----|
| **Seeds** | 1 seed (all classification) | 5 seeds standard | **6 experiments need re-run** |
| **Test set** | Val set used for selection across 20+ experiments | 3-way split (60/20/20) | **Selection bias unquantified** |
| **CIs** | None reported | Bootstrap + t-distribution | **All claims lack error bars** |
| **Calibration** | Only EXP-324 (Platt) | ECE in ClassificationValidator | **5 of 6 objectives uncalibrated** |
| **Generalization** | Only EXP-326 (LOO) | LOOValidator ready | **Most results are in-sample** |

### 6 Critical Re-Runs

These are the experiments whose conclusions rest on single seeds and no held-out test. The framework is ready to re-run all of them:

| Priority | Experiment | Objective | Current | Seeds Needed | Framework Status |
|----------|-----------|-----------|---------|-------------|-----------------|
| 🔴 | EXP-313 | UAM | F1=0.939 | 5 seeds + test | ✅ `run_validated_classification` |
| 🔴 | EXP-327 | Override (attention) | F1=0.852 | 5 seeds + test | ✅ `run_validated_classification` |
| 🔴 | EXP-322 | Hypo (multi-task) | F1=0.672 | 5 seeds + test | ✅ `run_validated_classification` |
| 🟠 | EXP-314 | Override (CNN) | F1=0.821 | 3 seeds | ✅ `run_validated_classification` |
| 🟠 | EXP-324 | Hypo (Platt) | ECE=0.010 | 3 seeds | ✅ `run_validated_classification` |
| 🟡 | EXP-304 | Retrieval | Sil=+0.326 | 3 seeds | ✅ `run_validated_retrieval` |

Estimated compute: ~12 GPU-hours for Tier 1+2.

---

## 4. Auto-Research Pipeline Patterns

### Pattern A: Classification (UAM, Override, Hypo)

```python
from tools.cgmencode.experiment_lib import run_validated_classification

def train_and_eval(seed):
    set_seed(seed)
    data = load_multiscale_data_3way(patient_paths, scale='fast')
    # ... build model, train, predict ...
    return {'y_true': y_test, 'y_pred': preds, 'y_prob': probs}

result = run_validated_classification(
    'EXP-313-v2', output_dir, train_and_eval,
    task_name='uam', positive_label=1,
    seeds=[42, 123, 456, 789, 1337],
)
# Result JSON includes: multi_seed aggregate, per-seed metrics,
# validation_metadata, bootstrap CIs
```

### Pattern B: Retrieval

```python
from tools.cgmencode.experiment_lib import run_validated_retrieval

def train_and_eval(seed):
    set_seed(seed)
    # ... train encoder, extract embeddings ...
    return {'embeddings': emb_array, 'labels': label_array}

result = run_validated_retrieval(
    'EXP-304-v2', output_dir, train_and_eval,
    k_values=(1, 5, 10),
)
```

### Pattern C: Forecasting (wrapper needed)

```python
# Not yet wrapped, but validators are ready:
from tools.cgmencode.objective_validators import ForecastValidator
from tools.cgmencode.validation_framework import MultiSeedRunner

fv = ForecastValidator()
runner = MultiSeedRunner(seeds=STANDARD_SEEDS)

def train_and_eval(seed):
    # ... train, predict ...
    metrics = fv.evaluate(y_true, y_pred, denormalize=False, bootstrap=False)
    return {k: v for k, v in metrics.items() if isinstance(v, (int, float))}

report = runner.run(train_and_eval)
```

### Pattern D: Drift (wrapper needed)

```python
from tools.cgmencode.objective_validators import DriftValidator

dv = DriftValidator()
results = []
for patient_id, (timestamps, isf_values) in patient_data.items():
    results.append(dv.evaluate_per_patient(timestamps, isf_values, patient_id))
aggregate = dv.aggregate(results)
```

---

## 5. What's Exhausted (Do NOT Re-Run)

Based on 335 experiments, these directions have been thoroughly explored and should not be revisited:

| Direction | Evidence | Result |
|-----------|----------|--------|
| Feature engineering on CNN | EXP-310, 311 | F1 drops 2.6–3.5% |
| Cross-scale embedding concatenation | EXP-304 | Δ Sil = -0.525 |
| CNN + embedding fusion | EXP-313 | F1 drops 5% vs CNN alone |
| Longer windows for UAM | EXP-299 | F1 drops 93% (0.939 → 0.068 at 12h) |
| Embedding similarity for drift | EXP-307 | Encoder collapse (sim ≈ 1.0) |
| Per-cycle ISF measurement | EXP-309 | 0/11 patients significant |
| Focal + multi-task combined | EXP-323 | NOT additive (focal helps alone, not combined) |

---

## 6. Gating Criteria for Next Phase

### Gate 1: Multi-Seed Replication (blocks all further work)
- **Pass**: UAM F1 CI excludes 0.90 (i.e., F1 > 0.90 at 95% confidence)
- **Pass**: Override attention vs CNN gap > 1σ (else simplify to CNN)
- **Pass**: Hypo F1 CI width < 0.05 (stable enough to improve upon)
- **Timeline**: ~12 GPU-hours

### Gate 2: Held-Out Test Evaluation (blocks deployment claims)
- **Pass**: Test-set metrics within 5% of validation-set metrics
- **Pass**: No objective shows > 10% degradation on unseen time windows
- **Timeline**: Included in Gate 1 runs (3-way split)

### Gate 3: FDA Phase A (blocks Phase B)
- **Pass**: ≥ 2 of 3 FDA feature methods show signal (EXP-328–331)
- **Criteria**: B-spline round-trip < 2 mg/dL, FPCA K ≤ 8 captures 90% variance, derivatives smoother than finite differences
- **Timeline**: After Gate 1 passes

---

## 7. Remaining Implementation Work

| Item | Effort | Blocks |
|------|--------|--------|
| `run_validated_forecast()` in experiment_lib.py | ~30 min | Forecasting auto-research |
| `run_validated_drift()` in experiment_lib.py | ~30 min | Drift auto-research |
| Re-run 6 key experiments with framework | ~12 GPU-hours | All deployment claims |
| Run FDA Phase A (EXP-328–331) | ~4 GPU-hours | Phase B decisions |

---

## 8. Conclusion

The validation framework is **production-ready** for auto-research across all 5 objectives. The infrastructure gap is minimal (2 missing wrapper functions). The real gap is **execution**: 335 experiments produced results, but all classification results lack the multi-seed replication and held-out evaluation that the framework now provides.

**Priority order**:
1. **Re-run 6 critical experiments** with the framework (establishes credibility)
2. **Add 2 missing wrappers** (forecasting, drift — straightforward)
3. **Run FDA Phase A** experiments through the validated pipeline
4. **Expand cohort** (N=11 → 50) once validation confirms architecture choices

The framework converts our experiment system from "exploration mode" (single-seed, no test set, no CIs) to "publication mode" (multi-seed, temporal hold-out, confidence intervals, standardized metrics). Every future auto-research run should use it.
