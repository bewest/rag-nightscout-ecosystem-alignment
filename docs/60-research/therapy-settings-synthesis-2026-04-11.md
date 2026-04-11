# Therapy Settings Synthesis Report

**Experiments**: EXP-2511–2537 (27 experiments, 40+ sub-experiments)  
**Date**: 2026-04-11  
**Data**: 19 patients (11 NS + 8 ODC), 803K rows, 35K+ corrections, 5K+ meals  
**Status**: AI-generated draft — requires clinical review

---

## 1. Executive Summary

This session produced a complete analysis of the **therapy triangle** (ISF, CR, basal) plus loop decision mechanics. Five key takeaways:

1. **ISF follows a causal power-law** (β=0.9): doubling a correction dose only increases glucose drop by ~7%. SMB is accidentally optimal. Validated by 4 independent causal methods across 17/17 patients with sufficient corrections (2/19 excluded for sparse data).

2. **Effective CR = 1.47× profile CR**: patients systematically under-dose meals, but the two nonlinearities (CR sub-linear absorption + ISF diminishing returns) approximately **cancel**, making standard linear dosing a valid approximation.

3. **Correction threshold should be ~166 mg/dL**: corrections from BG 130–180 rebound 75% of the time (regression to mean, not counter-regulation). Below this threshold, net harm exceeds benefit.

4. **"Scheduled basal" is fiction for AID users**: 18/19 patients show maximally high loop modulation (workload 100/100). The loop rewrites basal constantly, masking settings inadequacy.

5. **PD biology is real but useless for temporal forecasting**: power-law ISF and two-component DIA are statistically validated but fail to improve temporal-CV predictions. They are useful only for **static settings optimization**.

---

## 2. ISF Findings (EXP-2511–2534)

### Power-Law ISF

| Property | Value | Source |
|----------|-------|--------|
| Model | ISF(dose) = ISF_base × dose^(−β) | EXP-2511 |
| Population β | 0.899 ± 0.382 | EXP-2511 |
| Wins | 17/17 patients, +53% MAE improvement | EXP-2512 |
| β universality | CV=43%, 14/17 within 0.3 of mean | EXP-2513 |
| Causal validation | 4 methods (stratification, propensity, matched pairs, BG strata) | EXP-2523 |
| Matched-pair saturation | 68.9% show effect (p<0.0001) | EXP-2523d |
| Forecasting value | +0.006 R² (shuffled CV); **degrades** temporal CV | EXP-2521, 2531 |

**Clinical meaning**: The first 0.5U of a correction does most of the work. A 3U correction achieves only ~1.1× the drop of 1U. **Split dosing** (2×1U, 30+ min apart) theoretically achieves 1.87× the drop of a single 2U dose.

### Two-Component DIA

| Property | Value | Source |
|----------|-------|--------|
| Fast component | τ=0.8h (exponential decay) | EXP-2525a |
| Persistent component | Constant offset ~−50 mg/dL/U, >12h | EXP-2524a, 2525a |
| Best model | Mono-exp + constant (R²=0.827) | EXP-2525a |
| Mechanism | **NOT HGP suppression** — residual IOB + loop basal adjustment | **EXP-2534** |
| Evidence | Correction nights carry +0.85U more residual IOB (p<0.001) | EXP-2534 |

> **⚠️ Mechanistic correction**: Originally attributed to hepatic glucose production (HGP) suppression. EXP-2534 overnight matched-pair validation (280 pairs) showed the "persistent" effect is IOB underestimation by standard DIA curves + loop compensation — not liver physiology. The model remains **predictively valid** (R²=0.827) but the mechanism is different.

### Correction Rebounds = Regression to Mean

| Property | Value | Source |
|----------|-------|--------|
| Overall rebound rate | 53.7% | EXP-2524c |
| From BG 130–180 | **74.7%** rebound | EXP-2526c |
| From BG 260+ | 20.4% rebound | EXP-2526c |
| Counter-regulatory? | **NO** — higher nadirs rebound MORE | EXP-2526c |
| Prediction AUC | 0.775 (top predictor: starting glucose) | EXP-2526d |
| Optimal threshold | ≈ 166 mg/dL (per-patient: 130–290) | EXP-2528a |

### Selection Bias in Correction Evaluation

EXP-2527 showed that simple before/after TIR comparison is **fatally confounded** — corrections are markers of deteriorating control, not causes of TIR loss. Only matched-pair and instrumental-variable designs give reliable results.

### Circadian ISF Variation

| Property | Value | Source |
|----------|-------|--------|
| Within-day ISF ratio | 2–4× (population), up to 9× | EXP-2271, 2051 |
| ISF nadir | 4pm (71 mg/dL/U) | EXP-2051 |
| ISF peak | 1pm (126 mg/dL/U) | EXP-2051 |
| 2-zone (day/night) | Captures 61–90% of benefit | EXP-2271 |
| TIR worst hour | 8am (59%) | EXP-2051 |
| TIR best hour | 5pm (84%) | EXP-2051 |

---

## 3. CR Findings (EXP-2535–2537)

### Effective CR vs Profile

| Property | Value | Source |
|----------|-------|--------|
| Population CR ratio (effective/profile) | **1.47** (median) | EXP-2535b |
| Interpretation | Systematic under-dosing — patients use 47% more carbs per unit than profile says | EXP-2535b |
| Per-patient range | 0.85–2.3× | EXP-2535b |

**Most patients are under-dosing meals.** The effective CR is consistently higher than the profile CR, meaning patients eat more carbs per unit of insulin than their profile intends. This could reflect conservative CR settings, carb under-counting, or both.

### CR Nonlinearity: Large Meals Are Easier Per Gram

| Meal Size | Rise/gram (mg/dL/g) | TIR 4h | Source |
|-----------|---------------------|--------|--------|
| Small (0–20g) | ~5.50 | Lower | EXP-2535c |
| Medium (20–50g) | ~2.40 | Moderate | EXP-2535c |
| Large (50–100g) | ~1.20 | Higher | EXP-2535c |
| XL (100g+) | ~0.59 | Highest* | EXP-2535c |

BG rise per gram **decreases** with meal size — the opposite direction from ISF nonlinearity. This likely reflects slower gastric emptying for larger meals, buffer capacity, and the glycemic index ceiling effect.

### CR–ISF Independence

| Property | Value | Source |
|----------|-------|--------|
| CR–ISF correlation | r = 0.17 | EXP-2535b |
| Interpretation | CR and ISF are **independent** parameters | EXP-2535b |

This confirms CR and ISF should be tuned independently, not linked as some AID profiles assume.

### Circadian CR Variation

| Time Block | Excursion/g | Effective CR | Key Finding |
|------------|-------------|-------------|-------------|
| Breakfast | Highest | Tightest (most under-dosed) | Dawn phenomenon amplifies meal impact |
| Lunch | Moderate | Moderate | Most predictable period |
| Afternoon | Low | — | Snack patterns, hard to assess |
| Dinner | Moderate-high | Variable | Largest meal variability |

Breakfast is the hardest meal to dose correctly — consistent with the dawn phenomenon findings from the ISF circadian analysis (8am = worst TIR hour).

### CR × ISF Cancellation: Linear Dosing Remains Valid

| Property | Value | Source |
|----------|-------|--------|
| CR nonlinearity (γ_carb) | <1.0 (sub-linear absorption) | EXP-2537c |
| ISF nonlinearity (δ_dose) | <1.0 (diminishing returns) | EXP-2537c |
| Net R² improvement of nonlinear model | ~+0.001–0.005 | EXP-2537c |
| Verdict | **CANCEL** — nonlinearities largely offset | EXP-2537a |
| Net 4h outcome range across size bins | <15 mg/dL | EXP-2537a |

**This is the most important CR finding**: despite both CR and ISF being individually nonlinear, they go in **opposite directions** for meal boluses:
- Larger meal → less BG rise per gram (CR nonlinearity helps)
- Larger bolus → less BG drop per unit (ISF nonlinearity hurts)

These approximately cancel, meaning **standard linear dosing (carbs/CR) is a reasonable approximation**. The nonlinear model offers negligible R² improvement.

### Sweet Spot: 15–30g Meals

| Bin | TIR 4h | |Net 4h| | Source |
|-----|--------|---------|--------|
| 0–15g | Lower | Higher | EXP-2537d |
| **15–30g** | **Best** | **Lowest** | EXP-2537d |
| 30–50g | Good | Moderate | EXP-2537d |
| 50–75g | Declining | Rising | EXP-2537d |
| 100g+ | Worst | Highest | EXP-2537d |

Meals around 15–30g achieve the best post-meal TIR and smallest absolute 4h BG displacement. Very small meals (<15g) paradoxically have worse TIR, likely because they often go unbolused.

---

## 4. Basal Findings (EXP-2371–2396)

### Overnight Basal Assessment

| Finding | Value | Source |
|---------|-------|--------|
| Well-calibrated patients | **1/19** (patient j only) | EXP-2371 |
| Under-basaled | 6/19 patients | EXP-2371 |
| Over-basaled | 8/19 patients | EXP-2371 |
| Mixed / loop-dependent | 4/19 patients | EXP-2371 |
| Mean basal suspension rate (overnight) | 60% | EXP-2373 |
| Dawn phenomenon present | 6/19 patients | EXP-2375 |
| Circadian model R² | 0.002–0.070 | EXP-2376 |

### Loop Workload Distribution

| Finding | Value | Source |
|---------|-------|--------|
| Saturated workload (100/100) | 18/19 patients | EXP-2391 |
| Only adequate patient | Patient j | EXP-2391 |
| Workload vs TIR correlation | r = −0.165 (**none**) | EXP-2392 |
| Workload vs hypo risk | r = 0.238 (weak positive) | EXP-2393 |
| Loop direction dominant | REDUCING (basal suspension) in 14/19 | EXP-2391 |

**Key insight**: The scheduled basal rate is a fiction. The loop overrides it constantly. Settings quality does not predict TIR outcomes (r = −0.165). However, excessive loop workload may weakly increase hypo risk.

---

## 5. Unified Recommendations

| Parameter | Current State | Evidence Shows | Confidence | Production Status |
|-----------|--------------|----------------|------------|-------------------|
| **ISF (power-law)** | Profile ISF = constant | ISF(dose) = ISF_base × dose^(−0.9); 2U correction ~46% less effective/unit than 1U | **High** (17/17, causally validated) | ✅ `advise_isf_nonlinearity()` |
| **ISF (circadian)** | Usually single value | 2–4× within-day variation; 2-zone day/night captures 61–90% | **High** (11+ patients) | ✅ `advise_circadian_isf()`, `advise_circadian_isf_profiled()` |
| **ISF (discrepancy)** | Profile ISF | Effective ISF = 2.91× profile on average | **High** | ✅ `advise_isf()` |
| **CR (adequacy)** | Profile CR | Effective CR = 1.47× profile (under-dosing) | **Moderate** (population avg) | ✅ `advise_cr_adequacy()` |
| **CR (circadian)** | Usually flat | Breakfast hardest to dose; tightest CR needed | **Moderate** | ✅ `advise_context_cr()` |
| **CR (nonlinearity)** | Linear: dose = carbs/CR | Nonlinear per component, but cancels → linear valid | **High** | 🔬 Research only |
| **Basal (overnight)** | Scheduled rate | Loop overrides 60% of the time; 18/19 miscalibrated | **High** (2,397 nights) | ✅ `assess_overnight_drift()` |
| **Basal (workload)** | N/A | Workload ≠ TIR; can't assess settings from outcomes | **High** | 🔬 Research only |
| **Correction threshold** | System-dependent (often 120+) | Optimal ≈ 166 mg/dL (range 130–290) | **High** (35K+ corrections) | ✅ `advise_correction_threshold()` |
| **DIA** | Single exponential, 3–5h | Two-component: fast τ=0.8h + persistent tail (IOB underestimation) | **Moderate** (mechanism corrected) | 🔬 Research only |
| **Split dosing** | Single bolus | Theoretically 87% more effective at 2×half-dose | **Low** (confounded empirically) | 🔬 Research only |

---

## 6. Forecasting Lessons (EXP-2529, 2531–2533)

### PD Features Don't Help Temporal-CV Forecasting

| Experiment | Finding | Source |
|------------|---------|--------|
| EXP-2529 | Unified PD features: +0.011 R² under **shuffled** CV | `exp_unified_pd.py` |
| EXP-2531 | GBM > Ridge, but PD features **degrade** temporal CV | `exp_nonlinear_pd.py` |
| EXP-2532 | Ratio features stable but weak under temporal CV | `exp_temporal_pd.py` |
| EXP-2533 | PD biology is real but swamped at h60 by meals, exercise, sensor drift | `exp_temporal_pd.py` |

**Methodological lesson**: The distinction between **shuffled CV** (measures association) and **temporal CV** (measures forward prediction) is critical. PD features that improve shuffled R² may **degrade** temporal R² because they overfit to patient-level constants that change over time. PD signal is real but only useful for **static settings optimization**, not dynamic forecasting.

This confirms our production strategy: use PD models for `settings_advisor.py` (static recommendations), use physics-based features (supply/demand, IOB, COB) for the forecasting pipeline.

---

## 7. Production Status

### Advisories in `settings_advisor.py`

| Advisory | Function | Research Basis | Tests |
|----------|----------|---------------|-------|
| Basal assessment | `advise_basal()` | EXP-693 | ✅ `TestBasalAssessment` |
| CR effectiveness | `advise_cr()` | EXP-694 | ✅ `TestSettingsOptimizerModule` |
| ISF discrepancy | `advise_isf()` | EXP-747 | ✅ `TestSettingsOptimizerModule` |
| ISF nonlinearity | `advise_isf_nonlinearity()` | EXP-2511–2518 | ✅ `TestISFNonlinearityFunction` + Integration |
| Correction threshold | `advise_correction_threshold()` | EXP-2528 | ✅ `TestCorrectionThresholdFunction` + Integration |
| Circadian ISF 2-zone | `advise_circadian_isf()` | EXP-2271 | ✅ `TestCircadianISF` |
| Circadian ISF profiled | `advise_circadian_isf_profiled()` | EXP-2271 | ✅ `TestCircadianISFProfiledFunction` + Integration |
| Context-aware CR | `advise_context_cr()` | EXP-2341 | ✅ `TestContextCR` |
| Overnight drift | `assess_overnight_drift()` | EXP-2371–2378 | ✅ `TestOvernightDriftFunction` + Integration |
| CR adequacy | `advise_cr_adequacy()` | EXP-2535/2536 | ✅ `TestCRAdequacyFunction` + Integration |
| Period analysis | `analyze_periods()` | Combined | ✅ `TestSettingsOptimizerPipeline` |
| Segmented ISF | `advise_isf_segmented()` | EXP-765 | ✅ `TestSettingsOptimizerModule` |

**Test coverage**: 226 tests across 46 test classes in `test_production.py`.

### What Remains Research-Only

| Finding | Why Not Productionized | Priority |
|---------|----------------------|----------|
| CR × ISF cancellation | **Confirms linear dosing** — no action needed | Low (validates status quo) |
| Two-component DIA | Mechanism corrected; needs AID algorithm changes | Medium (AID firmware) |
| Split-dose recommendation | Empirically confounded; needs RCT | Low |
| Loop workload metric | Insight, not actionable recommendation | Low |
| 15–30g meal sweet spot | Lifestyle guidance, not settings change | Medium (educational) |

---

## 8. Cross-Experiment Confirmations and Contradictions

### Confirmations ✓

| Finding A | Finding B | Relationship |
|-----------|-----------|-------------|
| ISF power-law β=0.9 (EXP-2511) | ISF nonlinearity δ<1 in meal context (EXP-2537c) | **Confirms** ISF diminishing returns across corrections AND meals |
| Correction rebounds = mean reversion (EXP-2526) | Selection bias in TIR eval (EXP-2527) | **Confirms** both are manifestations of confounded observational analysis |
| Overnight basal 18/19 miscalibrated (EXP-2371) | Loop workload 18/19 saturated (EXP-2391) | **Confirms** miscalibrated settings → high workload |
| Circadian ISF variation 2–4× (EXP-2051) | Breakfast hardest CR (EXP-2536) | **Confirms** morning = universal worst period for glycemia |
| Persistent DIA component (EXP-2525) | Residual IOB on correction nights (EXP-2534) | **Confirms** the effect but **corrects** the mechanism |

### Contradictions / Corrections ✗

| Original Claim | Correction | Experiment |
|---------------|-----------|------------|
| Persistent component = HGP suppression | = Residual IOB + loop compensation | EXP-2534 |
| PD features improve forecasting (+0.011) | Only under shuffled CV; **degrade** temporal CV | EXP-2531/2532 |
| Split dosing 1.87× more effective | Empirically 0.39× (confounded by glucose difficulty) | EXP-2522b |
| Large meals should be harder to dose | CR nonlinearity makes them **easier per gram** | EXP-2535c |

---

## 9. Experiment Index

| ID | Name | Script | Key Finding |
|----|------|--------|-------------|
| EXP-2511 | Power-law ISF fit | `exp_dose_isf.py` | β=0.9, 17/17 patients |
| EXP-2512 | Power-law validation | `exp_dose_isf.py` | +53% MAE improvement |
| EXP-2513 | β universality | `exp_dose_isf.py` | CV=43%, transfers across patients |
| EXP-2521 | Forecasting w/ power-law | `exp_powerlaw_forecast.py` | +0.006 R² (shuffled only) |
| EXP-2522 | Split-dose analysis | `exp_split_dose.py` | Theory 1.87× vs empirical 0.39× (confounded) |
| EXP-2523a | Confounding analysis | `exp_causal_isf.py` | Confounding inflates large-dose ISF |
| EXP-2523b | BG strata consistency | `exp_causal_isf.py` | β consistent: 0.96–1.09, CV=5.3% |
| EXP-2523c | Propensity adjustment | `exp_causal_isf.py` | Survives adjustment (r=−0.69) |
| EXP-2523d | Matched-pair saturation | `exp_causal_isf.py` | 68.9% of 2,546 pairs show saturation |
| EXP-2524 | DIA paradox | `exp_dia_paradox.py` | 94% of max effect at 12h |
| EXP-2525 | Two-component model | `exp_biexp_dia.py` | Mono-exp + constant (R²=0.827) |
| EXP-2526a | Rebound risk factors | `exp_rebound.py` | Meals amplify OR=2.49 |
| EXP-2526b | Circadian rebound | `exp_rebound.py` | Morning 69.4% vs overnight 42.9% |
| EXP-2526c | Rebound = mean reversion | `exp_rebound.py` | Higher nadirs rebound MORE |
| EXP-2526d | Rebound prediction | `exp_rebound.py` | AUC=0.775, top: starting glucose |
| EXP-2527 | Selection bias in TIR | `exp_overcorrection.py` | All corrections show "TIR harm" → confounded |
| EXP-2528 | Optimal threshold | `exp_correction_threshold.py` | ≈166 mg/dL (range 130–290) |
| EXP-2529 | Unified PD features | `exp_unified_pd.py` | +0.011 R² (shuffled CV only) |
| EXP-2531 | Nonlinear PD | `exp_nonlinear_pd.py` | GBM > Ridge; PD fails temporal CV |
| EXP-2532 | Temporal PD | `exp_temporal_pd.py` | Ratio features stable but weak |
| EXP-2533 | PD signal analysis | `exp_temporal_pd.py` | PD real but swamped at h60 |
| EXP-2534 | HGP validation | `exp_hgp_validation.py` | **HGP suppression disconfirmed** |
| EXP-2535a | Meal extraction | `exp_cr_response.py` | 5K+ meals, size distribution |
| EXP-2535b | Effective CR | `exp_cr_response.py` | CR ratio = 1.47× (under-dosing) |
| EXP-2535c | Dose-dependent CR | `exp_cr_response.py` | Rise/g decreases: 5.50→0.59 mg/dL/g |
| EXP-2535d | CR adequacy | `exp_cr_response.py` | Per-patient ideal CR computation |
| EXP-2535e | Post-meal TIR | `exp_cr_response.py` | Post-meal TIR vs overall TIR |
| EXP-2536a | Circadian meals | `exp_cr_circadian.py` | Time-block distribution |
| EXP-2536b | Excursion by block | `exp_cr_circadian.py` | Breakfast worst excursion/g |
| EXP-2536c | Effective CR by block | `exp_cr_circadian.py` | Breakfast tightest CR |
| EXP-2537a | Net meal outcome | `exp_cr_isf_interaction.py` | CANCEL — nonlinearities offset |
| EXP-2537b | Linear model error | `exp_cr_isf_interaction.py` | No size-dependent bias |
| EXP-2537c | Nonlinear model | `exp_cr_isf_interaction.py` | γ<1, δ<1, marginal R² gain |
| EXP-2537d | Clinical sweet spot | `exp_cr_isf_interaction.py` | 15–30g meals best TIR |

All scripts in `tools/cgmencode/production/`. Results (gitignored) in `externals/experiments/`.

---

## 10. Limitations

1. **All findings are observational** — no randomized interventions. Causal claims rely on natural experiments and matched-pair designs, not RCTs.

2. **AID loop confounding is pervasive** — the loop adjusts in response to everything, making pure insulin/carb effects impossible to isolate. All "ISF" and "CR" measurements include the loop's compensation.

3. **Population heterogeneity** — β=0.9 with CV=43% means some patients may have substantially different nonlinearity. Per-patient calibration is preferable when sufficient data exists.

4. **Temporal CV invalidates some features** — findings that are statistically significant under shuffled CV (e.g., PD forecasting features) fail under temporal CV. Only temporal-CV-validated findings should be used for predictions.

5. **CR findings depend on meal logging accuracy** — carb counting errors directly affect effective CR calculations. Systematic under-counting would inflate the apparent CR ratio.

---

*All experiment scripts in `tools/cgmencode/production/`.  
Settings advisor: `tools/cgmencode/production/settings_advisor.py` (226 tests, 46 classes).  
Prior ISF synthesis: `docs/60-research/insulin-pharmacodynamics-synthesis-2026-04-11.md`.  
Prior basal reports: `docs/60-research/overnight-basal-report-2026-04-11.md`, `loop-workload-report-2026-04-11.md`.*
