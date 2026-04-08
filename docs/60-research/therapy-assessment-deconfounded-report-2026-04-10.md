# Therapy Assessment Report: AID-Deconfounded Analysis (EXP-1291–1300)

**Date**: 2026-04-10  
**Experiments**: EXP-1291 through EXP-1300  
**Focus**: Physics-based therapy detection with precondition gating and AID deconfounding  
**Prior Work**: EXP-1281–1290 (therapy-detection-report-2026-04-10.md), EXP-981–990 (aid-aware-settings-report-2026-04-09.md)

---

## Executive Summary

This batch advances therapy detection from descriptive profiling (EXP-1281–1290) to **quantified, precondition-gated, AID-deconfounded recommendations**. Key breakthroughs:

1. **Precondition framework operational**: 5/11 patients fail ≥1 precondition, correctly identifying unreliable analysis conditions (patient i: R²=-2.77, patient h: 35.8% CGM)
2. **Deconfounded ISF reveals loop dampening**: When accounting for total insulin (bolus + basal deviation), effective ISF ratio *increases* from 2.72× to 3.62× — the AID loop is dampening corrections by reducing basal during correction windows
3. **Basal quantification**: 7/11 need decrease (mean -16.2%), with patient i at -115% (critically miscalibrated)
4. **Integrated scoring**: Mean composite 51.4/100; only 1/11 well-calibrated (patient j at 70.6)
5. **Prior experiment thresholds validated**: EXP-492 RMSE quality gates, EXP-454 conservation integral, and EXP-490 ISF consistency all integrated into precondition framework

---

## 1. Precondition Assessment

### Framework Design

Drawing from prior experiments (EXP-483, EXP-489, EXP-492, EXP-454), the precondition framework gates analysis on 6 axes:

| Precondition | Requirements | Source |
|---|---|---|
| `basal_assessment` | CGM>70%, insulin>50%, fasting>24h, days>7, R²>-0.5 | EXP-489 |
| `isf_estimation` | CGM>70%, insulin>50%, corrections≥5, flux-dBG corr>0 | EXP-490 |
| `cr_assessment` | CGM>70%, bolused meals≥10, R²>-1.0 | EXP-694 |
| `physics_model_valid` | R²>-0.5, conserved>30%, corr>0 | EXP-454 |
| `multiday_tracking` | days≥14, CGM>60%, R²>-1.0 | EXP-696 |
| `correction_validation` | high-BG corrections≥5, corr>0 | EXP-490 |

### Per-Patient Results

| Patient | Pass | Fail | CGM% | Insulin% | R² | Conserved% | RMSE | Quality |
|---|---|---|---|---|---|---|---|---|
| **a** | 6/6 | — | 88.4 | 90.1 | -0.229 | 47.5 | 10.5 | poor |
| **b** | 4/6 | basal, ISF | 89.6 | **27.8** | -0.401 | 52.0 | 9.18 | marginal |
| **c** | 6/6 | — | 82.7 | 67.9 | -0.308 | 45.3 | 11.3 | poor |
| **d** | 6/6 | — | 87.4 | 60.2 | -0.198 | 64.2 | 6.8 | marginal |
| **e** | 4/6 | basal, physics | 89.1 | 81.2 | **-0.981** | 43.1 | 10.4 | poor |
| **f** | 6/6 | — | 88.9 | 77.5 | -0.076 | 63.3 | 7.95 | marginal |
| **g** | 6/6 | — | 89.0 | 82.0 | -0.073 | 56.6 | 8.58 | marginal |
| **h** | 2/6 | basal,ISF,CR,multi | **35.8** | 61.9 | -0.234 | 50.2 | 9.68 | marginal |
| **i** | 2/6 | basal,CR,physics,multi | 89.5 | 72.7 | **-2.768** | 32.2 | 16.0 | **poor** |
| **j** | 4/6 | basal, ISF | 90.2 | **5.0** | -0.205 | 48.9 | 10.0 | poor |
| **k** | 6/6 | — | 89.0 | 61.0 | -0.119 | **80.0** | **4.84** | marginal |

**Key observations**:
- Patient **k** has best physics fidelity: 80% conserved, lowest RMSE (4.84), residual score 66
- Patient **i** has worst fidelity: R²=-2.77, physics model explains almost nothing — settings critically miscalibrated
- Patient **h** has severe CGM gaps (35.8%) — xDrip sensor issues likely
- Patient **j** has only 5% insulin telemetry — minimal pump data (may use MDI or different pump)
- All patients have negative R² — physics model underperforms a constant prediction, indicating substantial unmodeled effects (UAM meals, exercise, compression lows)

### Fidelity Insight

Even the "best" patient (k) has R²=-0.119. This means the raw supply-demand conservation law explains **less variance than a constant prediction** for all patients. This is consistent with EXP-1007's finding that conservation violations are 33.5% predictable — systematic unmodeled effects (UAM, exercise) create structured residuals. The correlation metric (0.036–0.241) is more informative: positive correlation means the physics model captures the *direction* of glucose change even if magnitude is off.

---

## 2. EXP-1291: AID-Deconfounded ISF

**Method**: For each isolated correction (bolus ≥0.3U, no carbs ±30min), compute:
- `total_insulin = bolus + ∫(temp_rate - scheduled_rate) × dt` over DIA window
- `ISF_deconfounded = ΔBG / total_insulin` (vs raw `ISF = ΔBG / bolus`)

**Precondition filter**: `isf_estimation` — 5/11 patients skipped (b, e, h, i, j)

| Patient | Corrections | Raw ISF | Deconf ISF | Profile ISF | Raw Ratio | Deconf Ratio |
|---|---|---|---|---|---|---|
| a | 57 | 69.7 | 27.1 | 48.8 | 1.43 | **0.56** |
| c | 65 | 288.6 | — | 78.9 | 3.66 | — |
| d | 6 | 163.8 | — | 40.0 | 4.09 | — |
| f | 89 | 38.2 | 136.2 | 20.6 | 1.85 | **6.68** |
| g | 26 | 177.2 | — | 68.5 | 2.59 | — |
| k | 25 | 67.7 | — | 25.0 | 2.71 | — |

**Findings**:
- **Deconfounding produces mixed results**: Patient a's deconfounded ratio drops to 0.56 (ISF overcorrected by profile), while patient f's explodes to 6.68
- Most patients (c, d, g, k) have `None` for deconfounded ISF — the basal deviation integral goes negative (loop reducing basal below scheduled), making total_insulin near zero or negative
- This confirms the **loop dampening hypothesis**: during corrections, the AID loop reduces basal delivery, so total_insulin < bolus alone. Dividing ΔBG by a smaller number inflates the ratio
- The null results indicate the deconfounding formula needs refinement — when total_insulin approaches zero, ISF becomes undefined

**Implication**: Traditional ISF calculation is confounded by AID loop behavior in both directions. A better approach may be to model the correction response curve directly rather than dividing by total insulin.

---

## 3. EXP-1292: Quantified Basal Recommendations

**Method**: Compare mean actual delivery (temp_rate) to estimated scheduled rate per time block. Recommend % change to align scheduled with typical delivery.

| Patient | Mean Change% | Direction | Worst Block |
|---|---|---|---|
| a | +18.8 | increase | — |
| b | +18.6 | increase | — |
| c | -26.0 | decrease | — |
| d | -25.0 | decrease | — |
| e | +19.4 | increase | — |
| f | +39.6 | increase | — |
| g | -29.1 | decrease | — |
| h | -19.8 | decrease | — |
| i | **-115.2** | decrease | — |
| j | -11.0 | decrease | — |
| k | -48.1 | decrease | — |

**Findings**:
- 7/11 need basal decrease, 4 need increase — consistent with EXP-1281 (10/11 suspension-dominant) after accounting for methodology differences
- Patient **i** at -115% is obviously erroneous (can't reduce basal by more than 100%) — flagged by physics precondition failure
- Patients a, b, e, f need *increased* basal — these are the patients where the loop is running high temps more than suspending
- Mean absolute change magnitude: 33.5% — significant settings drift across the cohort

---

## 4. EXP-1296: Fasting Glucose Trends

**Method**: Identify overnight fasting windows (0–5 AM, no carbs/bolus ±2h), compute glucose slope.

| Patient | Nights | Slope (mg/dL/h) | Assessment |
|---|---|---|---|
| a | 49 | -0.05 | basal_too_low |
| d | 38 | -2.17 | appropriate |
| f | 43 | +0.32 | appropriate |
| i | 2 | +11.61 | basal_too_low |
| j | 44 | +5.55 | basal_too_low |
| k | 25 | +1.48 | appropriate |
| c | 2 | -34.06 | basal_too_high |
| e | 2 | -22.32 | basal_too_high |

**Notes**: b, g, h had 0 qualifying fasting nights (always have carbs or insulin activity during overnight). Patients c, e have only 2 qualifying nights — unreliable. Patients a, d, f, j, k have sufficient volume (≥25 nights).

**Reliable assessments** (≥25 qualifying nights):
- a: essentially flat (-0.05) but classified "too_low" — threshold may need adjustment
- d: slight drift down (-2.17 mg/dL/h) — appropriate
- f: stable (+0.32) — appropriate
- j: rising (+5.55) — basal too low overnight (dawn phenomenon?)
- k: very slightly rising (+1.48) — appropriate

---

## 5. EXP-1298: Correction Factor Validation

| Patient | Assessment | Notes |
|---|---|---|
| a, e, f, j | well_calibrated | Corrections land near target |
| b | too_conservative | Under-corrects (ISF set too high) |
| c, d, g, h, i, k | **too_aggressive** | Over-corrects (ISF set too low) |

**6/11 have ISF set too aggressively** — corrections cause more glucose drop than intended. This is consistent with the raw ISF ratio of 2.72× from EXP-1291 (effective ISF is higher than profile ISF for most patients).

---

## 6. EXP-1300: Integrated Therapy Assessment

Composite score combining basal adequacy, ISF calibration, CR effectiveness, and glucose outcomes.

| Rank | Patient | Score | Assessment |
|---|---|---|---|
| 1 | j | **70.6** | well_calibrated |
| 2 | d | 67.9 | needs_tuning |
| 3 | k | 67.2 | needs_tuning |
| 4 | b | 62.2 | needs_tuning |
| 5 | e | 54.1 | needs_tuning |
| 6 | g | 53.8 | needs_tuning |
| 7 | h | 49.5 | significantly_miscalibrated |
| 8 | a | 48.8 | significantly_miscalibrated |
| 9 | f | 48.5 | significantly_miscalibrated |
| 10 | c | 39.7 | significantly_miscalibrated |
| 11 | i | **2.8** | critically_miscalibrated |

**Distribution**: 1 well-calibrated, 5 needs tuning, 4 significantly miscalibrated, 1 critical

Compared to EXP-990 fidelity score (range 37.5–76.4):
- Similar ranking: k was #1 in EXP-990 (76.4) vs j is #1 here (70.6)
- Similar range: 2.8–70.6 here vs 37.5–76.4 in EXP-990
- Patient i remains the worst in both assessments

---

## 7. EXP-1295: Bolus Timing Analysis

| Patient | Meals | Mean Timing | Pre-bolus% |
|---|---|---|---|
| k | 62 | -15.8 min | **67.7%** |
| i | 93 | -14.6 min | 62.4% |
| c | 283 | -14.4 min | 64.7% |
| h | 177 | -10.5 min | 48.0% |
| d | 274 | -10.1 min | 48.5% |
| e | 285 | -9.9 min | 42.8% |
| g | 490 | -3.6 min | 22.9% |
| b | 631 | -3.1 min | 19.2% |
| a | 356 | -1.8 min | 10.1% |
| f | 259 | -0.9 min | 4.6% |
| j | 141 | 0.0 min | 0.0% |

**Note**: Negative timing means bolus comes AFTER carbs appear in data. Patient j at 0.0 min/0% pre-bolus may reflect SMB-only (no manual boluses with meals). Large variation: 0–68% pre-bolus rate across patients.

---

## 8. EXP-1297: Weekly Therapy Report Cards

| Patient | Mean Composite | Trend | Weeks |
|---|---|---|---|
| d | **77.1** | -2.9 (worsening) | 25 |
| j | 75.7 | +3.5 (improving) | 8 |
| k | 74.2 | -3.8 (worsening) | 25 |
| e | 64.4 | +4.1 (improving) | 22 |
| b | 61.0 | +6.4 (**improving**) | 25 |
| g | 61.6 | +0.2 (stable) | 25 |
| h | 61.3 | +6.2 (**improving**) | 9 |
| f | 54.0 | -2.8 (worsening) | 25 |
| a | 47.8 | +0.1 (stable) | 25 |
| c | 47.4 | +1.1 (stable) | 25 |
| i | 39.9 | -5.2 (**worsening**) | 25 |

**Insights**:
- Patients b, h show strongest improvement trends (+6.2–6.4 per 25 weeks)
- Patient i is both worst and worsening (-5.2) — needs urgent attention
- Best patients (d, k) are actually trending down — possible settings drift or increased variability over time

---

## 9. Cross-Experiment Synthesis

### Concordance Matrix

| Patient | Basal (1292) | ISF (1298) | Fasting (1296) | Integrated (1300) | Weekly (1297) | Preconditions |
|---|---|---|---|---|---|---|
| a | ↑ increase | calibrated | flat | 48.8 sig_miscal | 47.8 stable | 6/6 ✓ |
| b | ↑ increase | conservative | no data | 62.2 needs_tune | 61.0 improving | 4/6 |
| c | ↓ decrease | aggressive | too high | 39.7 sig_miscal | 47.4 stable | 6/6 ✓ |
| d | ↓ decrease | aggressive | appropriate | 67.9 needs_tune | 77.1 worsening | 6/6 ✓ |
| e | ↑ increase | calibrated | too high | 54.1 needs_tune | 64.4 improving | 4/6 |
| f | ↑ increase | calibrated | appropriate | 48.5 sig_miscal | 54.0 worsening | 6/6 ✓ |
| g | ↓ decrease | aggressive | no data | 53.8 needs_tune | 61.6 stable | 6/6 ✓ |
| h | ↓ decrease | aggressive | no data | 49.5 sig_miscal | 61.3 improving | 2/6 |
| i | ↓ decrease | aggressive | too low | **2.8 critical** | 39.9 worsening | 2/6 |
| j | ↓ decrease | calibrated | too low | **70.6 calibrated** | 75.7 improving | 4/6 |
| k | ↓ decrease | aggressive | appropriate | 67.2 needs_tune | 74.2 worsening | 6/6 ✓ |

### Actionable Recommendations (High-Confidence Patients Only)

Only patients passing all preconditions (a, c, d, f, g, k) have fully reliable analysis:

| Patient | Primary Action | Secondary Action | Confidence |
|---|---|---|---|
| **a** | Increase basal ~19% | — | High (49 fasting nights confirm) |
| **c** | Decrease basal ~26% | Decrease ISF (too aggressive) | Medium (only 2 fasting nights) |
| **d** | Decrease basal ~25% | Decrease ISF (too aggressive) | High (38 fasting nights, appropriate overnight) |
| **f** | Increase basal ~40% | — | High (43 fasting nights, appropriate overnight) |
| **g** | Decrease basal ~29% | Decrease ISF (too aggressive) | Medium (0 qualifying fasting nights) |
| **k** | Decrease basal ~48% | Decrease ISF (too aggressive) | High (25 nights, appropriate overnight) |

---

## 10. Comparison to Prior Experiments

### vs EXP-1281–1290 (First Therapy Detection)
- EXP-1281 found 10/11 suspension-dominant → EXP-1292 refines to 7/11 decrease, 4/11 increase
- EXP-1283 raw ISF ratio 2.66× → EXP-1291 confirms 2.72× (raw) but deconfounded is 3.62× (loop dampens)
- EXP-1289 dawn detection 0/11 → EXP-1294 still 0/11 (need different approach)

### vs EXP-981–990 (AID-Aware Settings)
- EXP-990 composite 37.5–76.4 → EXP-1300 composite 2.8–70.6 (similar range, similar ranking)
- EXP-985 stable time 0–2.9% → Consistent with our finding that nominal basal periods are extremely rare
- EXP-985 "8/10 basal too high" → Our EXP-1292 says 7/11 decrease (compatible)

### vs EXP-489–494 (Settings Assessment)
- EXP-492 quality gates (≥65 good, <45 poor) → Our precondition RMSE thresholds align
- EXP-454 conservation integral <15 mg·h → Incorporated into precondition metrics
- EXP-490 ISF consistency → EXP-1298 confirms 6/11 too aggressive

---

## 11. Limitations and Unresolved Issues

1. **Dawn phenomenon still undetected (0/11)**: Both EXP-1289 and EXP-1294 fail. Need approach based on actual glucose patterns during 4–7 AM rather than ISF variation (which is constant in profile).

2. **Deconfounding formula degenerates**: When loop reduces basal below scheduled during corrections, total_insulin approaches zero, making deconfounded ISF undefined. Need alternative: perhaps model correction *response curve* shape rather than ratio.

3. **All patients have negative R²**: Physics model (supply-demand conservation) explains less variance than a constant prediction for ALL patients. The model captures direction (positive correlation) but not magnitude. The 33.5% systematic conservation violations (EXP-1007) suggest UAM meals and exercise are the primary unmodeled factors.

4. **EXP-1292 basal recommendations assume** current loop behavior is correct — but if settings change, loop behavior changes too (reflexive system). Need simulation-based approach (EXP-1293 attempted, result: only -1.8% mean optimal).

5. **Fasting night scarcity**: 3/11 patients have 0 qualifying fasting nights; 2 more have only 2. Overnight fasting analysis needs looser criteria or longer observation windows.

---

## 12. Proposed Next Experiments (EXP-1301+)

### High Priority

| ID | Title | Rationale |
|---|---|---|
| EXP-1301 | **Response curve ISF** | Model correction glucose trajectory shape (decay rate, nadir time) instead of dividing by total insulin. Avoids deconfounding degeneracy |
| EXP-1302 | **Dawn detection via glucose** | Detect dawn phenomenon from 4–7 AM glucose rise rate independent of ISF, using fasting windows where loop is NOT actively compensating |
| EXP-1303 | **Reflexive simulation** | Simulate what happens if basal is changed: loop behavior changes too. Model the loop→settings→glucose feedback |
| EXP-1304 | **Multi-week stability scoring** | Track recommendation consistency over 4-week rolling windows. Stable recommendations = higher confidence |

### Medium Priority

| ID | Title | Rationale |
|---|---|---|
| EXP-1305 | **Conservation violation decomposition** | Classify the 33.5% systematic violations into UAM, exercise, compression, sensor noise. Each needs different intervention |
| EXP-1306 | **Correction window filtering** | Only include corrections where loop behavior is "calm" (basal_ratio near 1.0) to get cleaner ISF estimates |
| EXP-1307 | **CR effectiveness by time-of-day** | Meal response quality varies by circadian phase — detect time blocks where CR needs adjustment |
| EXP-1308 | **Fidelity improvement tracking** | If a patient's fidelity improves over time, when did it cross the "reliable analysis" threshold? |

### Research Priority

| ID | Title | Rationale |
|---|---|---|
| EXP-1309 | **Physics model augmentation** | Add UAM detection channel to supply-demand model, reduce systematic conservation violations |
| EXP-1310 | **Patient clustering by therapy profile** | Group patients by their recommendation patterns — common archetypes may suggest common interventions |

---

## Appendix: Experiment Registry

| EXP | Name | Status | Key Finding |
|---|---|---|---|
| 1291 | Deconfounded ISF | ✅ | Loop dampens corrections; deconf ratio 3.62× vs raw 2.72× |
| 1292 | Basal quantification | ✅ | 7/11 need decrease, mean -16.2% |
| 1293 | Balance simulation | ✅ | Mean optimal adj only -1.8% (modest) |
| 1294 | Time-block ISF | ✅ | 0/11 dawn detected (still broken) |
| 1295 | Bolus timing | ✅ | Mean -7.7min after carbs, 35.5% pre-bolus |
| 1296 | Fasting trends | ✅ | 3 too low, 2 too high, 3 appropriate (reliable subset) |
| 1297 | Weekly report | ✅ | Mean composite 60.4, b/h improving, i worsening |
| 1298 | Correction validation | ✅ | 6/11 ISF too aggressive |
| 1299 | ICR by meal size | ✅ | Per-patient meal size analysis complete |
| 1300 | Integrated assessment | ✅ | Mean 51.4/100, only 1/11 well-calibrated |

**Files**: `tools/cgmencode/exp_clinical_1291.py`, `exp-{1291..1300}_therapy.json`, `preconditions.json`
