# Extended Horizons & Fidelity Report: EXP-1401–1410

**Date**: 2026-04-10  
**Campaign**: Therapy Detection & Recommendation (experiments 121–130 of 130)  
**Patients**: 11 (a–k), ~180 days each, ~50K timesteps  
**Prior batches**: EXP-1281–1400 (120 experiments across 12 reports)

## Executive Summary

This batch extends the therapy pipeline to longer time horizons and introduces
physics-based fidelity scoring. We detect dawn phenomenon, optimize
multi-segment basal patterns, analyze DIA-horizon therapy quality, and build
comprehensive therapy timelines. Key discovery: **9/11 patients need
multi-segment basal patterns**, with afternoon consistently needing less basal
across the population. Dawn phenomenon affects 3/11 patients significantly.
Conservation law fidelity is uniformly low (R²=1.3%) but doesn't affect
recommendation quality.

**Key headline numbers**:
- Dawn phenomenon: **3/11 significant** (patients a, d, j) (EXP-1401)
- Multi-segment basal needed: **9/11** (EXP-1407)
- DIA-horizon problem rate: **23.4%** of 6h windows (EXP-1405)
- Monthly trends reveal more than weekly: 4 improving, 4 declining (EXP-1404)
- Fidelity filtering: **91% agreement** — recommendations robust to physics
  quality (EXP-1408)
- Patient k: 24/24 timeline windows grade A (EXP-1410)

---

## Experiment Results

### EXP-1401: Dawn Phenomenon Detection

**Question**: Which patients have dawn phenomenon (pre-breakfast BG rise from
cortisol/growth hormone without carbs)?

**Results**:

| Patient | Mean Rise | P90 Rise | Prevalence | Significant |
|---------|-----------|----------|------------|-------------|
| **j** | **+34.3** | 63.9 | **83.9%** | ✅ Yes |
| **d** | **+29.6** | 92.4 | **57.6%** | ✅ Yes |
| **a** | **+17.3** | 138.3 | **52.2%** | ✅ Yes |
| f | +8.4 | 115.4 | 51.0% | No (mean < 10) |
| b | 0.0 | 0.0 | 0.0% | No |
| k | -16.0 | 9.9 | 0.0% | No |
| g | -19.8 | 14.9 | 12.5% | No |
| i | -24.3 | 56.4 | 37.5% | No |
| e | -65.5 | 10.6 | 33.3% | No |
| h | -72.4 | -72.4 | 0.0% | No |
| c | -74.3 | 9.8 | 14.3% | No |

**Population mean dawn rise: -16.6 mg/dL** (negative — BG drops on average!)

**Findings**:
1. **3 patients** have clinically significant dawn phenomenon
2. Patient j has strongest: 84% of mornings rise >15 mg/dL without meals
3. Several patients show BG **drops** at dawn — likely AID overcorrection or
   insulin stacking from overnight corrections
4. Dawn phenomenon is a **basal pattern issue** — needs time-of-day basal rate
   increase during 4-7am, not CR adjustment
5. **Reconciles EXP-1396**: breakfast has highest excursions (113 mg/dL) partly
   because dawn phenomenon elevates baseline before breakfast starts

---

### EXP-1402: Time-of-Day Basal Segmentation

**Question**: Do patients need different basal rates at different times of day?

**Results** (mean drift by segment, mg/dL/h):

| Patient | Overnight | Morning | Afternoon | Evening | Flagged |
|---------|-----------|---------|-----------|---------|---------|
| a | +5.5 | -1.6 | **-7.7** | +3.4 | 4 |
| d | -0.3 | +2.9 | **-10.2** | +6.5 | 4 |
| e | -4.3 | -5.0 | -1.8 | **+9.4** | 4 |
| f | +6.9 | **-9.2** | -6.4 | +0.0 | 4 |
| i | +2.3 | **-6.6** | -3.2 | +6.7 | 4 |
| j | +5.3 | +0.4 | +1.0 | **-9.5** | 4 |
| k | +0.7 | -1.0 | +1.9 | -1.4 | 4 |

**Key pattern**: Afternoon drift is consistently **negative** across most
patients (BG dropping). This suggests:
- Lunch bolus tail effect (insulin activity exceeding need)
- OR afternoon basal rates too high
- Most pronounced in patients d (-10.2) and a (-7.7)

**6/11 patients** formally need multi-segment basal patterns (n_flagged ≥ 2).

---

### EXP-1403: Conservation Law Fidelity Scoring

**Question**: How well does the glucose conservation law (ΔBG = supply - demand)
hold at 5-minute resolution?

**Results**:

| Patient | R² | Fidelity Score | Residual (mg/dL) | High-Fid Days |
|---------|----|--------------:|:----------------:|:--------------|
| i | 0.0332 | 3.3 | 5.63 | 145/180 |
| f | 0.0205 | 2.1 | 5.08 | 134/180 |
| c | 0.0185 | 1.8 | 6.95 | 160/180 |
| a | 0.0159 | 1.6 | 6.65 | 155/180 |
| h | 0.0153 | 1.5 | 6.04 | 65/180 |
| e | 0.0150 | 1.5 | 5.17 | 110/157 |
| b | 0.0136 | 1.4 | 5.43 | 149/180 |
| g | 0.0092 | 0.9 | 5.74 | 123/180 |
| d | 0.0091 | 0.9 | 4.20 | 118/180 |
| k | 0.0037 | 0.4 | 2.92 | 122/179 |
| j | -0.0090 | 49.6* | 6.48 | 9/61 |

*j's fidelity score mapping is anomalous due to negative R² formula

**Mean R²: 0.0132** — conservation law explains only **1.3% of 5-min variance**

**Findings**:
1. The physics model is **essentially useless** at 5-minute resolution — R²≈0
   means supply-demand balance explains almost no instantaneous glucose change
2. However, recommendations based on **aggregate** metrics (drift over 8h,
   excursions over 4h) work well — the physics doesn't need to be accurate at
   individual timesteps
3. Patient k has lowest residual (2.92 mg/dL) — tightest glucose control =
   smallest prediction errors
4. **Fidelity gating is unnecessary** — the pipeline already bypasses physics
   for recommendations (using drift, excursions directly)

---

### EXP-1404: Multi-Week Trend Analysis

**Question**: At what time scale do therapy trends become detectable?

**Results**:

| Scale | Improving | Declining | Stable |
|-------|-----------|-----------|--------|
| Weekly | 1 | 0 | 10 |
| Biweekly | 1 | 0 | 10 |
| **Monthly** | **4** | **4** | **3** |
| Bimonthly | 3 | 3 | 3 |

**Findings**:
1. **Weekly/biweekly scales are too noisy** — nearly everything looks stable
2. **Monthly scale is optimal** for trend detection — splits population into
   meaningful groups (4/4/3)
3. Bimonthly shows same pattern as monthly — diminishing returns beyond 30 days
4. **Production recommendation**: Report trends at monthly granularity; weekly
   is for acute monitoring only

---

### EXP-1405: DIA-Horizon Therapy Metrics

**Question**: What does therapy quality look like at the DIA (6h) time scale?

**Results**:

| Patient | DIA TIR | DIA CV | Problem Rate | Granularity Ratio |
|---------|---------|--------|-------------|-------------------|
| k | 95.0% | 11.0% | 1.9% | 1.50 |
| h | 84.8% | 26.5% | 1.9% | 1.98 |
| j | 80.9% | 20.8% | 10.5% | 1.67 |
| d | 79.3% | 18.7% | 14.4% | 1.68 |
| g | 75.0% | 25.0% | 17.0% | 1.67 |
| e | 65.3% | 24.8% | 28.8% | 1.70 |
| f | 64.8% | 25.1% | 31.2% | 1.90 |
| c | 61.3% | 31.2% | 31.1% | 1.70 |
| i | 59.8% | 31.1% | 38.0% | 1.63 |
| b | 56.5% | 21.6% | 40.0% | 1.51 |
| a | 55.7% | 27.3% | 42.8% | 1.72 |

**Mean problem rate: 23.4%** — nearly 1 in 4 DIA-windows has <50% TIR

**Findings**:
1. **Granularity ratio ≈ 1.7** — DIA-scale TIR is 70% more variable than daily
   TIR. This means daily aggregation hides significant within-day quality swings
2. Patient a has **42.8% problem windows** — nearly half the time, a 6-hour
   window has <50% TIR
3. Patient k has only **1.9%** problem windows — 98% of DIA-windows are good
4. **DIA-scale analysis reveals hidden therapy failures** that daily metrics
   smooth over

---

### EXP-1406: Seasonal/Monthly Pattern Detection

**Results**:
- **3/11 patients** show seasonal TIR variation >15%
- Mean TIR range across months: **11.3 percentage points**
- Most patients (8/11) have relatively stable monthly patterns

---

### EXP-1407: Multi-Segment Basal Optimization

**Question**: Can we optimize basal rates for 4 time-of-day segments?

**Results**:

| Patient | Needs Multi | Key Adjustments |
|---------|-------------|-----------------|
| a | ✅ | morning ↓17%, afternoon ↓30% |
| b | ✅ | afternoon ↓24%, evening ↑30% |
| c | ✅ | all segments ↓ (16-30%) |
| d | ✅ | morning ↑26%, afternoon ↓30%, evening ↑30% |
| e | ✅ | midnight ↓30%, morning ↑30%, evening ↓30% |
| f | ✅ | morning ↓30%, afternoon ↓30% |
| g | ✅ | midnight ↓30%, afternoon ↓30% |
| h | ✅ | midnight ↓30%, morning ↓19%, evening ↓23% |
| **i** | **No** | insufficient data for most segments |
| j | ✅ | midnight ↑23%, evening ↓30% |
| **k** | **No** | no adjustments needed |

**9/11 patients need multi-segment basal** — far more than the single-rate
pipeline currently handles.

**Key patterns**:
1. **Afternoon ↓**: 8/11 patients need afternoon basal reduction (lunch bolus
   tail effect)
2. **Morning variable**: Mix of ↑ (dawn phenomenon patients) and ↓
3. **Evening variable**: Some ↑ (need more overnight coverage), some ↓ (dinner
   bolus tail)
4. **Patient k**: No adjustments needed — confirms gold-standard calibration

**This is the most actionable finding of the batch** — current pipeline only
recommends single-rate basal adjustments. Multi-segment is clinically standard
practice and this data supports it.

---

### EXP-1408: Fidelity-Filtered Recommendations

**Question**: Do recommendations change when using only high-fidelity days?

**Results**: **91% agreement** — only 1/11 patients (h) has different
recommendations when filtering by physics fidelity.

Mean TIR gap between high and low fidelity days: **-1.1 points** (negligible).

**Conclusion**: Fidelity filtering is unnecessary. The recommendation pipeline
is already robust because it uses aggregate metrics (drift, excursion) that
average over physics noise.

---

### EXP-1409: Weekly vs Daily Aggregation

**Results**:

| Parameter | Daily Flag Rate | Weekly Flag Rate | Change |
|-----------|----------------|-----------------|--------|
| Basal | 57.1% | 35.3% | ↓ 38% fewer flags |
| Dinner CR | 63.2% | 80.3% | ↑ 27% more flags |
| Lunch CR | 60.8% | 71.2% | ↑ 17% more flags |

**Findings**:
1. **Weekly aggregation reduces basal false positives** by 38% — daily overnight
   drift is noisy, weekly mean is more reliable
2. **Weekly aggregation increases CR flags** — the mean excursion is pulled up
   by bad days, smoothing doesn't help
3. **Recommendation**: Use **weekly** aggregation for basal, **daily** for CR

---

### EXP-1410: Comprehensive Therapy Timeline

**Results**:

| Patient | Trend | Score Range | Dominant Grade | Transitions |
|---------|-------|-------------|----------------|-------------|
| k | stable | 93.3–99.6 | A (24/24) | 0 |
| d | stable | 50.2–95.6 | B(11)/C(11) | 6 |
| g | stable | 45.1–70.0 | C(13)/D(9) | 7 |
| f | improving | 33.7–63.8 | D(17)/C(7) | 8 |
| h | improving | 52.6–78.6 | C(8)/B(2) | 3 |
| j | improving | 51.9–60.8 | C (7/7) | 0 |
| e | stable | 38.0–53.8 | D(16)/C(5) | 5 |
| b | stable | 30.9–52.9 | D(22)/C(2) | 2 |
| a | stable | 31.4–46.5 | D (24/24) | 0 |
| c | stable | 37.1–45.8 | D (24/24) | 0 |
| i | stable | 34.1–48.8 | D (24/24) | 0 |

**3 improving, 0 declining, 8 stable** (at timeline resolution)

**Findings**:
1. Patients a, c, i are **persistently grade D** — every 14-day window for 6
   months. These need aggressive intervention.
2. Patient k is **persistently grade A** — every window. No intervention needed.
3. Patient d fluctuates widely (50-96) with 6 grade transitions — responsive to
   external factors (possibly lifestyle/exercise variation)
4. The timeline view reveals therapy **stability** — most patients are either
   consistently good or consistently poor, not fluctuating

---

## Campaign Summary: 130 Experiments Complete

### New Pipeline Additions (v5)

```
PIPELINE v5 (additions from EXP-1401-1410):

├─ DAWN PHENOMENON CHECK (EXP-1401)
│   If dawn_prevalence > 0.3 AND mean_rise > 10:
│     → Recommend 4-7am basal increase (not CR change)
│
├─ MULTI-SEGMENT BASAL (EXP-1402, 1407) [NEW — replaces single-rate]
│   Compute drift per 4 segments (midnight/morning/afternoon/evening)
│   Afternoon ↓ is most common adjustment (8/11 patients)
│   Use weekly aggregation for basal flags (EXP-1409)
│
├─ TREND REPORTING (EXP-1404, 1410)
│   Report at monthly granularity (weekly too noisy)
│   Identify persistent grade D patients for escalation
│
└─ DIA-HORIZON MONITORING (EXP-1405) [NEW]
    Report problem_dia_rate alongside daily TIR
    >30% problem rate = active intervention needed
```

### Validated Negative Results (don't pursue)

| Approach | Why | Experiment |
|----------|-----|-----------|
| Fidelity gating | 91% agreement, adds complexity | EXP-1408 |
| Physics R² as quality gate | R²=1.3%, useless | EXP-1403 |
| Weekly CR aggregation | Increases false positives | EXP-1409 |
| Seasonal adjustment | Only 3/11 affected | EXP-1406 |

### Open Questions for Next Batch

1. **Multi-segment basal implementation**: How to translate drift-based
   recommendations into actual rate adjustments (U/h)?
2. **Dawn phenomenon + AID interaction**: Does the AID loop already compensate
   for dawn phenomenon? If so, recommending basal increase could overshoot.
3. **Persistent grade D escalation**: What additional triage steps for patients
   who are chronically poorly controlled?
4. **Cross-parameter interactions at multi-segment level**: Does fixing afternoon
   basal affect dinner CR needs?

---

## Files

| Artifact | Location |
|----------|----------|
| Experiment script | `tools/cgmencode/exp_clinical_1401.py` |
| EXP-1401–1410 results | `externals/experiments/exp-140{1..0}_therapy.json` |
| This report | `docs/60-research/therapy-extended-horizons-report-2026-04-10.md` |
