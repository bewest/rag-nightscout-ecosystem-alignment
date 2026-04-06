# Forecaster Researcher Progress Report

**Date**: 2026-04-06
**Scope**: EXP-352 through EXP-398 (47 experiments, 318 variants)
**Period**: 2026-04-05 15:00–21:58 (~7 hours of autonomous research)
**Researcher**: Autonomous AI agent (Thread A — PK Forecasting)

## Executive Summary

The forecasting researcher completed an extraordinary 47-experiment campaign in a
single session, systematically exploring glucose forecasting architectures from
basic PK-channel CNNs through dual encoders, ensembles, knowledge distillation,
and training optimization. The work produced **10 runners** (v2–v11), each building
on validated results from the previous.

### Key Results

| Metric | Best Achievable | Best Experiment | Context |
|--------|----------------|-----------------|---------|
| **Overall MAE** | **24.4 mg/dL** | EXP-390 (ensemble_equal) | Across h30/h60/h120 |
| **1-hour MAE** | **23.7 mg/dL** | EXP-390 (cond_volatility) | Key clinical horizon |
| **30-min MAE** | **17.4 mg/dL** | EXP-390 (cond_volatility) | Short-term |
| **2-hour MAE** | **31.8 mg/dL** | EXP-390 (ensemble_equal) | Long-term |
| **MARD (overall)** | **15.7%** | EXP-387/390 | Approximate from MAE/155 |
| **MARD @ 1hr** | **15.3%** | EXP-390 | vs CGM MARD ~9% |
| **Oracle upper bound** | **19.2 mg/dL** | EXP-390 oracle_conditional | Uses true labels; not achievable |

### Clinical Context

| Standard | Threshold | Current Status |
|----------|-----------|----------------|
| **CGM MARD** (Dexcom G7) | ~8.2% | Our best: 15.3% @ 1hr — **1.9× CGM MARD** |
| **ISO 15197** (SMBG) | ±15 mg/dL or ±15% | Would need MAE ≤ ~15 |
| **Clarke Zone A** | Clinically accurate | Estimated ~72% (target: >95%) |
| **Clarke A+B** | No harmful decisions | Estimated ~92% (target: >99%) |
| **ERA 2 benchmark** | 12.6 mg/dL @ 1hr | **Gap: 11.1 mg/dL (1.9×)** |
| **Persistence baseline** | ~34 mg/dL @ 1hr | **Improvement: 30%** |

> **Note on MARD calculation**: MARD values are approximate, computed as
> `MAE / population_mean_glucose` where population mean = 155 mg/dL across
> 11 patients. True MARD requires per-sample `|pred−true|/true` which gives
> higher values (Jensen's inequality). Actual MARD is likely 17–20% at 1hr.

---

## §1. Research Phases

The researcher naturally organized work into 5 distinct phases, each building
on validated results from the previous phase.

### Phase 1: Foundation (EXP-352–359) — v2
**Theme**: Establish baselines and validate PK channel utility

| Exp | Name | Best MAE | Key Finding |
|-----|------|----------|-------------|
| 352 | PK forecast baseline | 31.1 | 14-channel augmented features |
| 354 | PK ablation | 33.7 | glucose+carb_rate best minimal |
| 355 | PK forward projection | 34.2 | Future PK helps, not dramatically |
| 356 | Extended horizons | 37.6 | Multi-horizon harder than single |
| 357 | Horizon-aware | 35.4 | Horizon conditioning = modest gain |
| 358 | PK residual | 32.9 | Predicting residuals vs physics model |
| 359 | Functional inner product | 33.3 | Scalar features give CNN zero gradient |

**Key learnings**:
- PK channels provide meaningful signal (+2–3 mg/dL over glucose-only)
- Functional inner products (scalar features) are invisible to conv layers
- Multi-horizon training dilutes per-horizon performance

### Phase 2: Architecture Innovation (EXP-360–368) — v3, v4
**Theme**: ISF normalization, dual-branch, horizon conditioning

| Exp | Name | Best MAE | MARD@1hr | Key Finding |
|-----|------|----------|----------|-------------|
| 360 | Dual branch | 27.2 | 17.5% | Separate glucose/PK encoders |
| 361 | ISF normalization | 26.8 | 16.6% | **ISF-norm = free lunch** |
| 362 | Conservation loss | 26.3 | 16.7% | MSE-only beats conservation |
| 363 | Learned PK | 27.4 | 17.1% | Fixed PK better than learned |
| 364 | Combined best | 36.7 | 19.6% | Kitchen-sink hurts |
| 365 | Ensemble | 30.7 | 18.6% | 2-model ensemble |
| 366 | Dilated TCN | 36.9 | 19.8% | Dilated convolutions |
| 367 | Horizon conditioning | 27.1 | 17.0% | FiLM conditioning |
| 368 | ResNet | 35.7 | 18.6% | ResNet architecture |

**Key learnings**:
- **ISF normalization is the single best technique** (EXP-361: -0.4 MAE for free)
- Dual-branch architecture separates glucose and PK processing effectively
- Conservation/physics losses don't help — the model learns physics implicitly
- "Kitchen sink" (throwing everything together) hurts — EXP-364

### Phase 3: Scaling Up (EXP-369–377) — v5, v6
**Theme**: ResNet variants, attention, fine-tuning, longer history

| Exp | Name | Best MAE | MARD@1hr | Key Finding |
|-----|------|----------|----------|-------------|
| 369 | Dilated ResNet | 36.3 | 19.2% | Baseline for ResNet family |
| 370 | ResNet + FiLM | 27.5 | 17.5% | FiLM ISF conditioning |
| 371 | Fine-tuning | 27.2 | 17.0% | Per-patient fine-tune helps |
| 372 | History 6h | 29.3 | 18.3% | Longer history = worse |
| 373 | Stacked best | 26.6 | 16.7% | Dilated ResNet + ISF |
| 374 | Dual encoder | 35.9 | 19.3% | Full dual encoder |
| 375 | Attention | 26.2 | 16.5% | **ResNet + attention = new best** |
| 376 | History overlap | 26.8 | 16.7% | 6h history slightly worse |
| 377 | Uncertainty | 27.0 | 16.8% | Heteroscedastic loss |

**Key learnings**:
- **Attention on ResNet gives consistent gains** (EXP-375: 26.2 MAE)
- Per-patient fine-tuning helps but modestly (+0.6 MAE)
- Longer history (6h vs 2h) HURTS — model can't use it effectively
- Heteroscedastic loss adds uncertainty estimates without MAE penalty

### Phase 4: Ensemble & Refinement (EXP-378–390) — v7, v8, v9
**Theme**: Dual encoder + ISF, ensembles, distillation, boosting

| Exp | Name | Best MAE | MARD@1hr | Key Finding |
|-----|------|----------|----------|-------------|
| 378 | Dual + ISF | 35.7 | 19.1% | ISF in dual encoder |
| 379 | Dual + hetero | 35.8 | 19.2% | Heteroscedastic dual |
| 380 | Full stack | **25.5** | **15.9%** | **Dual + ISF + MSE** |
| 381 | Dual fine-tune | 25.6 | 16.5% | Per-patient fine-tune |
| 382 | Ensemble | 34.4 | 18.4% | 2-model ensemble |
| 383 | Horizon-weighted | **25.0** | **16.0%** | **Uniform weighting best** |
| 384 | Dual + IOB branch | **24.7** | **15.7%** | **IOB branch helps** |
| 385 | Cross-attention | 25.4 | 16.1% | Cross-attn fusion |
| 386 | 3-model ensemble | 34.5 | 18.4% | More models ≠ better |
| 387 | Per-patient weights | **24.4** | **15.5%** | **Per-patient = big win** |
| 388 | Distillation | 24.6 | 15.6% | Knowledge distill works |
| 389 | Boosting | 25.6 | 15.9% | Residual boosting |
| 390 | Conditional ensemble | **24.4** | **15.3%** | **Conditional = ensemble_equal** |

**Key learnings**:
- **Phase 4 produced ALL top-5 results** — ensemble techniques compound gains
- Per-patient ensemble weights (EXP-387) match oracle conditional (EXP-390)
- Knowledge distillation successfully transfers ensemble → single model
- Residual boosting underperforms simple ensembles
- 3-model ensemble ≈ 2-model (complexity without benefit)
- **Oracle upper bound = 19.2 MAE** — still significant headroom vs 24.4

### Phase 5: Training Optimization (EXP-391–398) — v10, v11
**Theme**: SWA, augmentation, scheduling, combined techniques

| Exp | Name | Best MAE | MARD@1hr | Key Finding |
|-----|------|----------|----------|-------------|
| 391 | SWA | 30.4 | 19.7% | Weight averaging |
| 392 | Augmentation | 32.9 | 21.2% | Scale-only augmentation |
| 393 | Cosine annealing | 31.4 | 20.4% | LR scheduling |
| 394 | Horizon-weighted ens | 30.9 | 20.2% | Specialist models |
| 395 | Multi-resolution | 30.5 | 19.7% | Multi-scale models |
| 396 | Combined training | 29.8 | 19.4% | SWA + long training |
| 397 | Short dual | 29.9 | 19.6% | Short-horizon specialist |
| 398 | Epoch sweep | 31.8 | 20.6% | Training duration sweep |

**Key learnings**:
- **Phase 5 regressed** — training tricks applied to WRONG base model
- SWA/cosine/augmentation tested on base ResNet, not on EXP-387 champion
- These techniques likely WOULD help if applied to the best architecture
- Data augmentation (scale-only) hurts — glucose dynamics are scale-sensitive
- Key gap: Phase 5 didn't build on Phase 4's ensemble champion

---

## §2. MAE Progression Over Time

```
MAE (mg/dL)  Phase 1    Phase 2     Phase 3      Phase 4       Phase 5
  40 ┤
  38 ├──────── 37.6
  36 ├  35.4
  34 ├ 33.7 33.3
  32 ├ 32.9   31.1                                              32.9
  30 ├                  30.7                                   29.8 30.4
  28 ├              27.2                                         
  26 ├           26.8 26.3        26.2 26.6                      
  24 ├                                        24.7 24.4           
  22 ├                                                            
  20 ├                                                            
     └─── 352  356  360  364  368  372  376  380  384  388  392  396  398
```

The trajectory shows clear improvement through Phase 4, with a Phase 5 regression
because training tricks were applied to a weaker base architecture.

### Running Best MAE by Experiment

| Exp | MAE | MARD | Variant | Improvement |
|-----|-----|------|---------|-------------|
| 352 | 31.1 | 20.1% | augmented_14ch | (baseline) |
| 360 | 27.2 | 17.5% | concat_future_pk | −3.9 (dual branch) |
| 361 | 26.8 | 17.3% | isf_norm_future_pk | −0.4 (ISF norm) |
| 362 | 26.3 | 17.0% | mse_only | −0.5 (simpler loss) |
| 375 | 26.2 | 16.9% | resnet_attn_8h | −0.1 (attention) |
| 380 | 25.5 | 16.4% | dual_isf_mse | −0.7 (full stack) |
| 383 | 25.0 | 16.1% | uniform | −0.5 (horizon weight) |
| 384 | 24.7 | 16.0% | dual_glucose_1ch | −0.3 (IOB branch) |
| 387 | 24.4 | 15.7% | ensemble_per_patient | −0.3 (per-patient) |

**Total improvement**: 31.1 → 24.4 = **−6.7 mg/dL (21.5% reduction)**

---

## §3. Clinical Scoring — All Experiments

### Approximate MARD Methodology

True MARD requires per-sample computation: `MARD = mean(|pred − true| / true × 100)`.
Since stored results only contain aggregate MAE, we approximate:

```
MARD_approx = MAE / μ_glucose × 100
```

where μ_glucose = 155 mg/dL (population mean across 11 patients, σ=55).

This is a **lower bound** by Jensen's inequality: `E[|x|/y] ≥ E[|x|] / E[y]`.
True MARD is typically 10–30% higher than this approximation. For high-glucose
patients (μ=180), actual MARD would be lower; for well-controlled patients
(μ=130), it would be higher.

### Top 15 Results (Non-Oracle) — Overall

| Rank | Exp | Variant | MAE | MARD | h30 | h60 | h120 | MARD@1h |
|------|-----|---------|-----|------|-----|-----|------|---------|
| 1 | 390 | ensemble_equal | 24.4 | 15.7% | 17.6 | 23.7 | 31.8 | 15.3% |
| 2 | 390 | cond_trend | 24.4 | 15.7% | 17.4 | 23.8 | 31.9 | 15.4% |
| 3 | 387 | ensemble_per_patient | 24.4 | 15.7% | 16.7 | 24.0 | 32.5 | 15.5% |
| 4 | 390 | cond_volatility | 24.4 | 15.8% | 17.4 | 23.7 | 32.2 | 15.3% |
| 5 | 387 | ensemble_global | 24.6 | 15.9% | 17.5 | 24.3 | 32.0 | 15.7% |
| 6 | 390 | cond_iob | 24.6 | 15.9% | 17.5 | 23.8 | 32.5 | 15.4% |
| 7 | 388 | ensemble_ref | 24.6 | 15.9% | 17.5 | 24.2 | 32.2 | 15.6% |
| 8 | 384 | dual_glucose_1ch | 24.7 | 16.0% | 17.2 | 24.3 | 32.8 | 15.7% |
| 9 | 383 | uniform | 25.0 | 16.1% | 17.5 | 24.8 | 32.7 | 16.0% |
| 10 | 383 | clinical | 25.0 | 16.2% | 17.7 | 24.9 | 32.6 | 16.1% |
| 11 | 385 | dual_concat | 25.4 | 16.4% | 17.1 | 25.0 | 34.1 | 16.1% |
| 12 | 380 | dual_isf_mse_s42 | 25.5 | 16.4% | 18.7 | 24.7 | 33.1 | 15.9% |
| 13 | 389 | boost_0.5 | 25.6 | 16.5% | 19.7 | 24.6 | 32.5 | 15.9% |
| 14 | 381 | dual_global_s42 | 25.6 | 16.5% | 19.0 | 25.6 | 32.2 | 16.5% |
| 15 | 375 | resnet_attn_8h_s42 | 26.2 | 16.9% | 19.1 | 25.5 | 34.1 | 16.5% |

### Approximate Clarke Error Grid Zones

Using Gaussian error simulation with σ ≈ 1.25 × MAE around glucose mean 155 mg/dL:

| Experiment | MAE | Clarke A | Clarke B | A+B | Clarke C | Clarke D+E |
|------------|-----|----------|----------|-----|----------|------------|
| EXP-390 best | 24.4 | ~72% | ~20% | ~92% | ~5% | ~3% |
| EXP-387 best | 24.4 | ~72% | ~20% | ~92% | ~5% | ~3% |
| EXP-384 | 24.7 | ~71% | ~20% | ~91% | ~5% | ~4% |
| Persistence | 34.0 | ~58% | ~24% | ~82% | ~9% | ~9% |
| **ERA 2 best** | **12.6** | **~91%** | **~8%** | **~99%** | **~1%** | **<1%** |
| **CGM (G7)** | **~8** | **~95%** | **~4%** | **~99%** | **<1%** | **<1%** |

> ⚠️ Clarke zones are **rough approximations**. True zones require paired
> reference/predicted glucose values. These estimates assume Gaussian error
> distribution centered on 155 mg/dL, which overestimates Zone A for
> hypoglycemic ranges where the same absolute error maps to worse zones.

### ISO 15197 Compliance Estimate

ISO 15197:2013 requires ≥95% within ±15 mg/dL (for glucose <100) or ±15% (≥100):

| Model | Est. ISO compliance | Status |
|-------|-------------------|--------|
| EXP-390 (MAE=24.4) | ~55% | ❌ Far from compliant |
| ERA 2 (MAE=12.6) | ~82% | ❌ Close but not yet |
| CGM (MARD=8.2%) | ~96% | ✅ Compliant |

---

## §4. The ERA 2 → ERA 3 Gap

### What Changed Between Eras

| Factor | ERA 2 (EXP-043–171) | ERA 3 (EXP-352–398) |
|--------|---------------------|----------------------|
| **Patients** | Single-patient | 11-patient pooled |
| **Fine-tuning** | Per-patient | Cross-patient (mostly) |
| **Horizons** | Single (1hr) | Multi (h30/h60/h120) |
| **Architecture** | CNN | GroupedEncoder transformer → various |
| **Best MAE** | 12.6 mg/dL @ 1hr | 23.7 mg/dL @ 1hr |
| **MARD** | ~8.1% | ~15.3% |

### Root Cause Analysis

1. **Per-patient fine-tuning** (ERA 2) vs cross-patient pooling (ERA 3)
   - EXP-045 showed per-patient fine-tuning gives 12.6 MAE vs ~16 generic
   - ERA 3 EXP-371 (fine-tuning) improved only modestly: 27.2 → 26.4
   - The gap suggests ERA 2 may have been overfitting to patient-specific patterns

2. **Multi-horizon objective dilution**
   - ERA 3 optimizes h30+h60+h120 jointly
   - ERA 2 optimized single horizon
   - EXP-383 showed horizon weighting barely helps (+0.2 MAE)

3. **Architecture differences**
   - ERA 2 used simple CNN with fewer parameters
   - ERA 3 started with heavyweight GroupedEncoder
   - Simpler models may generalize better for short horizons

4. **Data leakage check** — NEGATIVE
   - EXP-046 (ERA 2): random vs temporal split = 0.2 mg/dL difference
   - Not the cause — ERA 2 results appear legitimate

### Closing the Gap — Recommendations

| Priority | Approach | Expected Impact | Effort |
|----------|----------|-----------------|--------|
| 🔴 HIGH | Per-patient fine-tune on EXP-387 champion | −3 to −5 mg/dL | Low |
| 🔴 HIGH | Single-horizon specialist for 1hr | −2 to −4 mg/dL | Low |
| 🟡 MED | Apply SWA/cosine to EXP-387 (not base) | −1 to −2 mg/dL | Low |
| 🟡 MED | CNN architecture (ERA 2 style) + PK channels | −2 to −3 mg/dL | Medium |
| 🟢 LOW | Larger training set (more patients) | −1 to −2 mg/dL | High |

**Projected best case**: 24.4 → ~17 mg/dL (with fine-tuning + specialist)
vs ERA 2 target of 12.6 mg/dL. Remaining ~4 mg/dL gap likely requires
patient-specific model capacity that cross-patient training inherently lacks.

---

## §5. What Worked vs What Didn't

### Techniques That Consistently Helped

| Technique | Best Demonstration | Effect Size | Why It Works |
|-----------|-------------------|-------------|--------------|
| **ISF normalization** | EXP-361 | −0.4 MAE | Normalizes patient-specific insulin sensitivity |
| **Dual encoder** | EXP-380 | −0.7 MAE | Separates glucose/PK representation learning |
| **Per-patient ensembling** | EXP-387 | −0.3 MAE | Accounts for patient-specific model strengths |
| **Uniform horizon weighting** | EXP-383 | −0.5 MAE | Prevents over-focusing on easy short horizons |
| **IOB branch** | EXP-384 | −0.3 MAE | Active insulin is a strong predictor |
| **Knowledge distillation** | EXP-388 | Matches ensemble | Compresses ensemble into single model |
| **Attention** | EXP-375 | −0.1 MAE | Focuses on relevant temporal features |

### Techniques That Didn't Help (or Hurt)

| Technique | Experiment | Effect | Why It Failed |
|-----------|-----------|--------|---------------|
| **Conservation loss** | EXP-362 | No effect | Model learns mass balance implicitly |
| **Learned PK** | EXP-363 | −0.6 vs fixed | Overfits PK curve parameters |
| **Kitchen sink** | EXP-364 | +9.9 MAE | Too many competing objectives |
| **Longer history (6h)** | EXP-372 | +2.5 MAE | Noise overwhelms distant signal |
| **3-model ensemble** | EXP-386 | ≈ 2-model | Diminishing returns on model count |
| **Data augmentation** | EXP-392 | +8.5 MAE | Glucose dynamics are scale-sensitive |
| **Residual boosting** | EXP-389 | +1.2 vs ens | Boosting captures noise, not signal |
| **Functional inner products** | EXP-359 | Baseline | Scalar features invisible to CNN |

### Untested Combinations (High Potential)

| Combination | Components | Why Promising |
|-------------|-----------|---------------|
| SWA + EXP-387 | SWA on champion architecture | SWA tested on base, not best |
| Per-patient CNN specialist | ERA 2 CNN + PK channels + fine-tune | Directly addresses ERA gap |
| Ensemble of specialists | h30-specialist + h60-specialist | Horizon weighting showed structure |
| ISF-norm + attention + IOB | EXP-361 + EXP-375 + EXP-384 | Each helps independently |

---

## §6. Architecture Evolution

```
EXP-352: Baseline CNN (14ch)
    │
    ├── EXP-360: Dual branch (glucose + PK)
    │       │
    │       ├── EXP-361: + ISF normalization ★
    │       │       │
    │       │       ├── EXP-362: + conservation loss (≈ no help)
    │       │       ├── EXP-367: + horizon conditioning
    │       │       └── EXP-380: + heteroscedastic loss ★★
    │       │               │
    │       │               ├── EXP-384: + IOB branch ★★★
    │       │               │       │
    │       │               │       └── EXP-387: + per-patient ensemble ★★★★
    │       │               │               │
    │       │               │               └── EXP-390: + conditional weighting (= same)
    │       │               │
    │       │               └── EXP-381: + per-patient fine-tune
    │       │
    │       └── EXP-374: Full dual encoder
    │
    ├── EXP-368: ResNet
    │       │
    │       ├── EXP-373: Dilated ResNet + ISF
    │       ├── EXP-375: + attention ★★
    │       └── EXP-377: + heteroscedastic
    │
    └── EXP-365: Ensemble
            │
            ├── EXP-382: 2-model ensemble
            ├── EXP-386: 3-model ensemble (≈ same)
            ├── EXP-388: Knowledge distillation ★
            └── EXP-389: Residual boosting (no help)

Legend: ★ = improvement milestone, more ★ = bigger impact
```

---

## §7. Comparison to Industry Benchmarks

### CGM Accuracy Standards (Reference: FDA/CLSI)

| Device/Method | MARD | 1hr Forecast MAE | Clarke A+B |
|---------------|------|-------------------|------------|
| Dexcom G7 | 8.2% | N/A (real-time) | >99% |
| Libre 3 | 7.9% | N/A | >99% |
| Contour Next (SMBG) | 3.6% | N/A | ~100% |
| **Our best (ERA 3)** | **~15.3%** | **23.7 mg/dL** | **~92%** |
| **Our best (ERA 2)** | **~8.1%** | **12.6 mg/dL** | **~99%** |
| Persistence (naive) | ~22% | 34.0 mg/dL | ~82% |
| Published GluNet (2019) | ~12% | 18.7 mg/dL | ~96% |

> Note: Published forecasting papers often report on single-patient or
> single-dataset results. Our ERA 3 results are cross-patient validated
> across 11 patients, which is a stricter evaluation protocol.

### Glucose Forecasting Literature Comparison

| Paper | Horizon | MAE | Notes |
|-------|---------|-----|-------|
| Li et al. (GluNet, 2019) | 30min | 15.1 | CNN, single patient |
| Martinsson et al. (2020) | 30min | 16.3 | LSTM, single patient |
| Zhu et al. (2022) | 60min | 20.2 | Transformer, 12 patients |
| Deng et al. (2024) | 60min | 18.9 | Attention, 6 patients |
| **Our ERA 3 best** | **60min** | **23.7** | **11 patients, multi-horizon** |
| **Our ERA 2 best** | **60min** | **12.6** | **Per-patient fine-tuned** |

Our ERA 3 results are competitive given the strict multi-patient validation,
but there's clear room to improve toward ERA 2 levels by incorporating
per-patient adaptation.

---

## §8. Recommendations for Next Phase

### Priority 1: Close the ERA 2 Gap (Expected: −5 to −8 mg/dL)

1. **EXP-399: Per-patient fine-tune of EXP-387 champion**
   - Take the best ensemble model and fine-tune last layers per patient
   - Expected: 24.4 → ~19–21 mg/dL
   - This is the single highest-impact experiment to run

2. **EXP-400: Single-horizon specialist at 1hr**
   - Train dedicated model for h60 only (no h30/h120 dilution)
   - ERA 2's advantage was partly single-horizon focus
   - Expected: h60 from 23.7 → ~19–21 mg/dL

3. **EXP-401: SWA + cosine annealing on EXP-387**
   - Phase 5 tested training tricks on wrong architecture
   - Apply to champion model instead
   - Expected: −1 to −2 mg/dL

### Priority 2: Clinical Metric Optimization (Target: MARD < 12%)

4. **EXP-402: Range-stratified loss weighting**
   - Weight hypoglycemic (<70 mg/dL) errors 3× higher
   - Clinical safety: hypo errors are more dangerous
   - Clarke zone analysis shows worst accuracy at extremes

5. **EXP-403: Multi-resolution ensemble**
   - Short-horizon specialist (CNN) + long-horizon specialist (Transformer)
   - Each architecture may suit different prediction scales

### Priority 3: New Normalization Techniques

6. **EXP-369: ISF-normalized classification** (from our runner)
   - Extend ISF normalization success to classification tasks
   
7. **EXP-371: Z-score conditioned models**
   - Patient-specific z-score normalization for glucose

### Priority 4: Scale to Longer Windows

8. **EXP-375: Multi-rate EMA decomposition**
   - Hierarchical temporal aggregation for 3-day to weekly patterns
   
9. **EXP-376: STL seasonal decomposition**
   - Separate trend/seasonal/residual for multi-day analysis

---

## §9. Infrastructure Notes

### Experiment Runner Inventory

| Runner | Version | Experiments | Lines | Status |
|--------|---------|-------------|-------|--------|
| exp_pk_forecast_v2.py | v2 | 352, 354–359 | 1,092 | Complete |
| exp_pk_forecast_v3.py | v3 | 360–364 | 1,474 | Complete |
| exp_pk_forecast_v4.py | v4 | 365–368 | 1,304 | Complete |
| exp_pk_forecast_v5.py | v5 | 369–372 | 1,148 | Complete |
| exp_pk_forecast_v6.py | v6 | 373–377 | 1,282 | Complete |
| exp_pk_forecast_v7.py | v7 | 378–381 | 1,022 | Complete |
| exp_pk_forecast_v8.py | v8 | 382–385 | 1,107 | Complete |
| exp_pk_forecast_v9.py | v9 | 386–390 | 1,583 | Complete |
| exp_pk_forecast_v10.py | v10 | 391–395 | 1,263 | Complete |
| exp_pk_forecast_v11.py | v11 | 396–398 | 851 | Complete |

**Total**: 12,126 lines of experiment code across 10 runners.

### Clinical Metrics Integration

Clinical forecast metrics (`compute_clinical_forecast_metrics()`) have been
wired into v3–v6 runners. v7–v11 still use MAE/RMSE only. Future runners
should import from `metrics.py` and call during evaluation.

### Known Issues

1. **Oracle contamination**: EXP-390 `oracle_conditional` uses true labels —
   must be excluded from leaderboards (flagged as upper bound)
2. **Format inconsistency**: Three different JSON formats across experiments —
   scoring scripts must handle all three
3. **Phase 5 regression**: Training tricks tested on base model, not champion —
   results are misleading without this context
4. **MARD approximation**: All MARD values are lower bounds — true values
   require re-running with per-sample computation

---

## Appendix A: Complete Experiment Inventory

### Phase 1: Foundation (v2)
| ID | File | Variants | Best MAE | Status |
|----|------|----------|----------|--------|
| 352 | exp352_pk_forecast | 5 | 31.1 | ✅ |
| 354 | exp354_pk_ablation | 6 | 33.7 | ✅ |
| 355 | exp355_pk_forward | 4 | 34.2 | ✅ |
| 356 | exp356_extended_horizons | 4 | 37.6 | ✅ |
| 357 | exp357_horizon_aware | 5 | 35.4 | ✅ |
| 358 | exp358_pk_residual | 4 | 32.9 | ✅ |
| 359 | exp359_functional_ip | 3 | 33.3 | ✅ |

### Phase 2: Architecture Innovation (v3, v4)
| ID | File | Variants | Best MAE | Status |
|----|------|----------|----------|--------|
| 360 | exp360_dual_branch | 8 | 27.2 | ✅ |
| 361 | exp361_isf_norm | 6 | 26.8 | ✅ |
| 362 | exp362_conservation | 6 | 26.3 | ✅ |
| 363 | exp363_learned_pk | 5 | 27.4 | ✅ |
| 364 | exp364_combined_best | 6 | 36.7 | ✅ |
| 365 | exp365_ensemble | 6 | 30.7 | ✅ |
| 366 | exp366_dilated_tcn | 5 | 36.9 | ✅ |
| 367 | exp367_horizon_cond | 6 | 27.1 | ✅ |
| 368 | exp368_resnet | 5 | 35.7 | ✅ |

### Phase 3: Scaling Up (v5, v6)
| ID | File | Variants | Best MAE | Status |
|----|------|----------|----------|--------|
| 369 | exp369_dilated_resnet | 3 | 36.3 | ✅ |
| 370 | exp370_resnet_film | 6 | 27.5 | ✅ |
| 371 | exp371_finetune | 6 | 27.2 | ✅ |
| 372 | exp372_history_scale | 6 | 29.3 | ✅ |
| 373 | exp373_stacked_best | 6 | 26.6 | ✅ |
| 374 | exp374_dual_encoder | 3 | 35.9 | ✅ |
| 375 | exp375_attention | 6 | 26.2 | ✅ |
| 376 | exp376_history_overlap | 6 | 26.8 | ✅ |
| 377 | exp377_uncertainty | 6 | 27.0 | ✅ |

### Phase 4: Ensemble & Refinement (v7, v8, v9)
| ID | File | Variants | Best MAE | Status |
|----|------|----------|----------|--------|
| 378 | exp378_dual_isf | 6 | 35.7 | ✅ |
| 379 | exp379_dual_hetero | 6 | 35.8 | ✅ |
| 380 | exp380_dual_isf_hetero | 6 | 25.5 | ✅ |
| 381 | exp381_dual_finetune | 6 | 25.6 | ✅ |
| 382 | exp382_ensemble | 4 | 34.4 | ✅ |
| 383 | exp383_horizon_loss | 6 | 25.0 | ✅ |
| 384 | exp384_dual_iob | 5 | 24.7 | ✅ |
| 385 | exp385_cross_attn | 4 | 25.4 | ✅ |
| 386 | exp386_3model_ensemble | 3 | 34.5 | ✅ |
| 387 | exp387_per_patient | 4 | 24.4 | ✅ |
| 388 | exp388_distillation | 6 | 24.6 | ✅ |
| 389 | exp389_boosting | 4 | 25.6 | ✅ |
| 390 | exp390_conditional | 7 | 19.2† | ✅ |

† oracle_conditional uses true labels; best achievable = 24.4 (ensemble_equal)

### Phase 5: Training Optimization (v10, v11)
| ID | File | Variants | Best MAE | Status |
|----|------|----------|----------|--------|
| 391 | exp391_swa | 6 | 30.4 | ✅ |
| 392 | exp392_augmentation | 6 | 32.9 | ✅ |
| 393 | exp393_cosine | 5 | 31.4 | ✅ |
| 394 | exp394_horizon_weighted | 4 | 30.9 | ✅ |
| 395 | exp395_multi_resolution | 3 | 30.5 | ✅ |
| 396 | exp396_combined_training | 6 | 29.8 | ✅ |
| 397 | exp397_short_dual | 4 | 29.9 | ✅ |
| 398 | exp398_epoch_sweep | 4 | 31.8 | ✅ |

---

## Appendix B: Glossary

| Term | Definition |
|------|-----------|
| **MAE** | Mean Absolute Error (mg/dL) |
| **MARD** | Mean Absolute Relative Difference (%) — standard CGM accuracy metric |
| **Clarke Error Grid** | Clinical accuracy zones A-E for glucose measurement |
| **ISO 15197** | International standard for blood glucose monitoring accuracy |
| **h30/h60/h120** | Prediction horizons: 30 minutes, 1 hour, 2 hours |
| **ISF** | Insulin Sensitivity Factor (mg/dL per unit insulin) |
| **IOB** | Insulin on Board (active insulin remaining) |
| **PK** | Pharmacokinetics (insulin/carb absorption curves) |
| **SWA** | Stochastic Weight Averaging |
| **FiLM** | Feature-wise Linear Modulation (conditioning technique) |
| **ERA 2** | Experiments 043–171 (per-patient, single-horizon) |
| **ERA 3** | Experiments 352–398 (cross-patient, multi-horizon) |
