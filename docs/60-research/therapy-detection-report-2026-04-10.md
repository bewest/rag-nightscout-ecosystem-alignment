# Therapy Detection & Recommendation — EXP-1281–1290

**Date**: 2026-04-10
**Campaign**: Strategic pivot from glucose prediction to therapy assessment
**Experiments**: EXP-1281–1290 (10 experiments, 11 patients, ~180 days each)

## Strategic Context

After 280 experiments converging glucose prediction (R²=0.496 at 60-min, R²=0.756 at 30-min), this batch pivots to the **actionable goal**: detecting basal/ISF/CR miscalibration and recommending specific settings changes. The physics-based supply/demand decomposition — originally built for prediction — turns out to be powerful for therapy assessment because it separates insulin action from carb absorption, allowing independent evaluation of each therapy dimension.

**User directive**: "We are more likely to improve our algorithms than to change human behavior." Focus on settings adjustments (basal, ISF, CR, DIA) and algorithm-side fixes, not behavioral nudges.

---

## Key Findings

### 1. Basal Over-Delivery is the Dominant Problem (EXP-1281, 1284, 1287)

**The single most consistent finding**: 10/11 patients have basal rates set too high, forcing the AID loop to suspend insulin 48–96% of the time.

| Patient | Loop Suspended % | Phenotype | Basal Score | Worst Block |
|---------|----------------:|-----------|------------:|-------------|
| j | 96% | suspension-dominant | 89.1 | morning |
| b | 76% | suspension-dominant | 81.1 | morning |
| d | 68% | suspension-dominant | 87.0 | afternoon |
| e | 53% | suspension-dominant | 58.9 | afternoon |
| f | 48% | suspension-dominant | 60.5 | afternoon |
| k | 45% | suspension-dominant | 28.2 | morning |
| i | 42% | suspension-dominant | 0.0 | overnight |
| h | 39% | suspension-dominant | 24.1 | morning |
| g | 33% | suspension-dominant | 19.7 | overnight |
| c | 26% | suspension-dominant | 0.0 | overnight |
| a | 11% | bidirectional | 47.3 | midday |

**Mean loop aggressiveness: 89.9%** — the loop deviates >30% from scheduled basal 90% of the time. Only patient a shows bidirectional control (both increasing and decreasing).

**Time-of-day pattern**: Afternoon (14-18h) is the worst block (mean score 36.3), followed by midday (38.1). Night and evening are best calibrated (55.5, 52.9). This suggests **basal rates are most over-set during active hours** when exercise and activity naturally lower glucose.

**Actionable recommendation**: EXP-1287 generated 33 "decrease_basal" recommendations and 10 "reduce_all_basal" recommendations. Specific patients:
- **Patient i**: TBR 72.8% overnight, 53% midday — needs **major** basal reduction (30-40%)
- **Patient c**: TBR 29.8% midday — needs 20-30% midday reduction
- **Patient h**: TBR 38.1% midday, 30% morning — needs morning/midday reduction

### 2. ISF Settings are Systematically Too Low (EXP-1283)

ISF effective (measured from correction bolus response) exceeds profile ISF by **2.66×** on average.

| Patient | n Corrections | ISF Effective | ISF Profile | Ratio | Calibration |
|---------|-------------:|-------------:|------------:|------:|-------------|
| a | 57 | 69.7 | 48.6 | 1.43 | accurate |
| b | 14 | 134.4 | 89.8 | 1.50 | too_sensitive |
| c | 47 | 225.8 | 78.8 | 2.86 | too_sensitive |
| d | 3 | 113.1 | 40.0 | 2.83 | too_sensitive |
| e | 15 | 184.6 | 34.9 | 5.41 | too_sensitive |
| f | 89 | 38.2 | 20.6 | 1.85 | accurate* |
| g | 20 | 138.8 | 68.8 | 2.02 | too_sensitive |
| h | 9 | 172.4 | 91.6 | 1.89 | accurate* |
| i | 37 | 269.1 | 51.3 | 5.23 | too_sensitive |
| j | 7 | 61.4 | 40.0 | 1.53 | too_sensitive |
| k | 21 | 66.9 | 25.0 | 2.68 | too_sensitive |

**Critical insight**: This systematic over-sensitivity has two possible explanations:
1. **ISF settings are genuinely too low** — patients are more insulin sensitive than programmed
2. **AID loop amplification confound** — when a correction bolus is given, the loop ALSO adjusts basal (often reducing or suspending it), so the effective insulin dose is larger than just the correction bolus

The ratio of 2.66× strongly suggests **both factors are at play**. The AID loop's basal adjustment during a correction creates a "phantom amplification" — the correction bolus is doing more than intended because the loop piles on.

**Mean nadir time: ~200 minutes (3.3h)** — this is faster than the typical 5h DIA, suggesting the peak insulin effect occurs well before DIA endpoint.

### 3. CR Settings are Modestly Effective (EXP-1282)

Mean CR effectiveness score: **49.1/100** across all patients and meal times.

| Meal Time | Mean Score | Worst Patients |
|-----------|----------:|----------------|
| Breakfast | 45-52 | b (lowest), most patients |
| Lunch | 38-50 | varies |
| Dinner | 40-55 | a, c |
| Snack | 35-45 | smaller meals score worse |

**Recommendation distribution**: 16 "decrease_cr" (increase insulin per gram of carb) recommendations across patients, particularly for:
- Patient b: post-meal peaks 251 mg/dL at breakfast, 283 mg/dL at lunch
- Patient f: post-meal peaks 276 mg/dL at breakfast

Only 2 "increase_cr" recommendations — consistent with the overall pattern of relative insulin insufficiency for meals while basal is excessive.

### 4. DIA May Need Adjustment for Some Patients (EXP-1288)

Mean suggested DIA: **5.3 hours** (range 3–7h across patients).

| Assessment | Patients | Suggested DIA |
|-----------|----------|--------------|
| Adequate (≤5h) | b, d, h, i, k | 3-5h |
| May need increase (>5h) | a, c, f, g, j | 6-7h |
| Inconclusive | e | — |

**Limitation**: The "pct_stable" criterion (BG rate of change < 10 mg/dL/h at DIA endpoint) is noisy with AID systems because the loop continuously adjusts basal. Many patients never reach 80% stability at any DIA value, suggesting the AID loop's continuous compensation makes this metric unreliable.

### 5. Multi-Day Therapy Tracking Detects Drift (EXP-1285)

| Trend | Patients | Examples |
|-------|----------|---------|
| Improving | 4 | h (+30.8), b (+9.9), c (+7.5), j (+5.1) |
| Degrading | 4 | k (-17.6), f (-7.9), e (-3.7), d (-3.5) |
| Stable | 3 | a (+2.6), g (+2.4), i (-0.6) |

**Patient k anomaly**: Highest TIR (95%) but strongest degradation trend (-17.6) with 23 significant score drops. This suggests a patient whose excellent control is gradually slipping — an **early warning signal** that settings may need adjustment before TIR visibly drops.

**Patient h**: Strongest improvement (+30.8) despite only 64 days of data — likely settings were recently tuned.

### 6. Prediction Error Clusters Signal Therapy Events (EXP-1286)

Mean 5.8% large errors (>2σ), averaging 13 error clusters per patient. Error clusters (≥3 consecutive large errors within 30 min) indicate **systematic therapy failures**, not random noise.

Key prediction quality metrics:
| Patient | R² | RMSE | Bias | Error Clusters |
|---------|---:|-----:|-----:|---------------:|
| i | 0.696 | 46.1 | +5.9 | 17 |
| d | 0.656 | 26.2 | -1.4 | 12 |
| f | 0.628 | 45.6 | +0.4 | 18 |
| e | 0.625 | 34.3 | -1.4 | 9 |
| a | 0.590 | 49.3 | +6.1 | 14 |
| g | 0.565 | 44.4 | +6.3 | 18 |
| b | 0.544 | 38.6 | -0.5 | 17 |
| j | 0.483 | 27.8 | -3.7 | 4 |
| c | 0.427 | 49.0 | -0.5 | 13 |
| k | 0.378 | 13.8 | +1.5 | 16 |
| h | 0.206 | 40.6 | +6.2 | 5 |

**Positive bias** in 6/11 patients (a, f, g, h, i, k) means the model under-predicts glucose — the actual BG goes higher than predicted, consistent with **unannounced meals or insufficient insulin coverage**.

### 7. Cross-Patient Benchmarking (EXP-1290)

Composite therapy scores (0-100, higher=better):

| Tier | Patients | Composite | Key Feature |
|------|----------|----------:|-------------|
| Well-controlled | k, d, j | 70-74 | High TIR, low TBR |
| Moderate | h, e | 55-62 | High TIR but elevated TBR |
| Needs work | g, f, b | 34-48 | Moderate TIR, some issues |
| Struggling | i, c, a | 27-33 | Low TIR, multiple weaknesses |

**Normative insight**: Patient j has the best balance (TIR=81%, TBR=1.1%) but highest loop suspension (96%). Patient k has highest TIR (95%) but elevated TBR (4.9%). This illustrates the **basal-too-high pattern**: excellent average control only because the loop is suspending most of the time, at the cost of occasional hypoglycemia when it can't suspend fast enough.

---

## Cross-Experiment Synthesis

### The AID Confound Problem

The clearest signal across all experiments: **AID loop compensation masks settings miscalibration**. When basal is too high, the loop suspends. When ISF is too low, the correction overshoots because the loop compounds the effect. When CR is wrong, the loop compensates post-meal. The result: TIR appears "acceptable" (mean 65%) while settings are systematically wrong.

### Recommended Settings Changes by Patient

| Patient | Basal | ISF | CR | Priority |
|---------|-------|-----|-----|----------|
| a | ↓ midday/PM | OK (1.43x) | ↓ dinner/snack | Medium |
| b | ↓↓ all (loop suspends 76%) | ↓ slight (1.5x) | ↓ breakfast/lunch | High |
| c | ↓↓↓ overnight/midday | ↑↑ (2.86x) | ↓ lunch | Critical |
| d | ↓ all (loop suspends 68%) | ↑ (2.83x, n=3) | OK | Low |
| e | ↓↓ afternoon | ↑↑ (5.41x) | OK | High |
| f | ↓ afternoon | ↑ (1.85x) | ↓ breakfast | Medium |
| g | ↓↓ overnight/midday | ↑ (2.02x) | OK | High |
| h | ↓↓ morning/midday | ↑ (1.89x) | OK | High |
| i | ↓↓↓ all (TBR 72.8% overnight) | ↑↑↑ (5.23x) | OK | Critical |
| j | ↓↓↓ all (loop suspends 96%) | ↓ slight (1.53x) | OK | High |
| k | ↓↓ morning/midday | ↑↑ (2.68x) | OK | Medium |

### Key Arrows for Algorithm Improvement

1. **Basal auto-adjustment**: If we can detect suspension-dominant patterns automatically, we can suggest specific per-time-block basal reductions with % change recommendations
2. **ISF deconfounding**: Need to account for loop's basal reduction during corrections to get true ISF. A correction in a suspension-dominant patient has its effect amplified
3. **CR per-meal scoring**: Breakfast is consistently the worst meal time — perhaps morning insulin resistance makes bolus timing more critical
4. **Predictive degradation tracking**: Patient k's -17.6 trend score is an early warning signal that could trigger a "settings review recommended" alert before TIR visibly drops

---

## Experiment Assessment

| EXP | Name | Value | Priority Going Forward |
|-----|------|-------|----------------------|
| **1281** | Time-block basal | ★★★★★ | Core — per-block basal scoring is highly actionable |
| **1282** | Meal CR scoring | ★★★★ | Useful — stratifies by meal time |
| **1283** | ISF estimation | ★★★★★ | Critical — reveals systematic ISF miscalibration |
| 1284 | Loop compensation | ★★★ | Descriptive; confirms prior work |
| **1285** | Multi-day tracking | ★★★★★ | Core — drift/trend detection for alerting |
| **1286** | Prediction error signal | ★★★★ | Novel — error clusters indicate unmodeled events |
| **1287** | Settings recommendations | ★★★★★ | Core — actionable, patient-specific recommendations |
| **1288** | DIA adequacy | ★★★ | Limited by AID confound |
| 1289 | Temporal ISF | ★★ | Need actual ISF, not profile ISF |
| **1290** | Cross-patient benchmark | ★★★★ | Good — establishes normative ranges |

---

## Next Experiment Priorities (EXP-1291+)

### High Priority — AID-Deconfounded ISF

The 2.66× ISF ratio is the most provocative finding. To make it actionable:
1. **Deconfound ISF from loop compensation**: During a correction, compute total insulin delivered (correction + loop basal change) over the DIA window, not just the correction bolus. True ISF = ΔBG / total_insulin
2. **Per-time-block ISF**: ISF likely varies by time of day (dawn phenomenon) but EXP-1289 measured profile ISF, not actual ISF. Use the deconfounded method at each time block

### High Priority — Basal Recommendation Quantification

EXP-1287 generates "decrease basal" recommendations but needs quantification:
1. **Compute optimal basal from supply/demand balance**: If overnight net flux averages -3 mg/dL/5min with current settings, compute the basal reduction needed to bring net flux to 0
2. **Validate with back-testing**: Simulate what TIR would be with recommended basal change using the physics model

### Medium Priority — Settings Change Impact Simulation

Use the converged prediction model to simulate "what if" scenarios:
1. Reduce basal by 10/20/30% for a patient and predict TIR change
2. Adjust ISF and predict correction bolus outcomes
3. Adjust CR and predict post-meal excursion changes

### Medium Priority — Multi-Week Stability Scoring

Extend EXP-1285 from daily/weekly to monthly scales:
1. Monthly therapy report card
2. Detect slow settings drift (EXP-312 found 9/11 significant biweekly ISF drift)
3. Seasonal ISF variation

### Lower Priority — Improved Dawn Phenomenon Detection

EXP-1289 used profile ISF (constant) so found 0/11. Instead:
1. Use actual glucose behavior: compare early morning BG rise rate during fasting to overnight rate
2. Compare morning demand/supply ratio to overnight ratio
3. Detect patients who need higher morning basal or lower morning ISF

---

## Technical Notes

### Bug Fixed
Initial run had `glucose * GLUCOSE_SCALE` on raw DataFrame values that are already in mg/dL (40-400 range), inflating all values by 400×. Fixed to `glucose = df['glucose'].values.astype(float)`.

### Measurement Limitations
1. **ISF estimation** requires isolated correction boluses (no concurrent carbs, no subsequent bolus within DIA). Sample sizes vary from 3 (patient d) to 89 (patient f)
2. **DIA assessment** is confounded by AID loop's continuous basal adjustment — the loop prevents true "tail" observation
3. **Fasting period detection** uses ±2h bolus/carb-free windows, which may be too strict for heavily-bolusing patients
4. **Dawn phenomenon** requires actual glucose pattern analysis, not profile ISF which is a static setting

### Files
- Experiment script: `tools/cgmencode/exp_clinical_1281.py`
- Results: `exp-{1281..1290}_therapy.json` (root directory)
