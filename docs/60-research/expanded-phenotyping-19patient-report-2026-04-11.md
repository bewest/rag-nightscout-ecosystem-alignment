# Expanded Cross-Patient Phenotyping & Intervention Targeting (EXP-2081–2088)

**Date**: 2026-04-11
**Dataset**: 19 patients (11 Nightscout + 8 OpenAPS Data Commons), 5–374 days each, 5-minute CGM with AID loop data
**Script**: `tools/cgmencode/exp_phenotyping_2081.py`
**Depends on**: EXP-2041–2078 (all prior therapy analysis), ODC format adapter for ns2parquet
**Prior report**: `docs/60-research/patient-phenotyping-intervention-report-2026-04-10.md` (11-patient baseline)

## Executive Summary

This report extends the 11-patient phenotyping suite (EXP-2081–2088) to a **19-patient expanded cohort** by incorporating 8 patients from the OpenAPS Data Commons (ODC). This is the first unified analysis spanning **four AID controller types**: Loop, Trio, AAPS, and OpenAPS. The ODC data was ingested via a new format adapter in the ns2parquet pipeline that converts AAPS-native JSON and Nightscout-export formats into the same 49-column 5-minute research grid used for the Nightscout patients.

**Key results**:

- **ISF increase generalizes across all AID systems** — top intervention for **15/19 patients** regardless of Loop, Trio, AAPS, or OpenAPS controller
- **AID behavior phenotypes differ systematically by controller type**: Loop/Trio clusters into COMPENSATING (5/11) and PASSIVE (4/11) with high suspend rates; AAPS/OpenAPS clusters into BALANCED (5/8) and AGGRESSIVE (3/8) with lower suspend rates
- **Only 5/19 (26%) meet both TIR≥70% AND TBR≤4%** — remarkably consistent with the 3/11 (27%) rate in the original cohort
- **Supply-demand decomposition differs by controller architecture**: Loop/Trio patients are supply-dominant; AAPS/OpenAPS patients are demand-dominant, suggesting SMB delivery is more insulin-efficient but meal handling lags
- **Temporal stability analysis** possible for only 3/8 ODC patients (observation period ≥30 days required); of those 3, one is declining, one is flat, one is improving
- **Setting mismatch severity remains LOW-to-MODERATE** across all 19 patients — no patient reaches HIGH severity, confirming that AID loops successfully mask extreme miscalibration regardless of controller type
- **Terrarium rebuilt** after `_lookup_schedule()` sort bug fix, ensuring correct ISF/CR/basal interpolation for profiles with unsorted `timeAsSeconds` entries (notably odc-74077367)

---

## Cross-Controller Comparison

### Controller Distribution

| Controller | Patients | Median TIR | Median eA1c | Median Days |
|------------|:--------:|:----------:|:-----------:|:-----------:|
| Loop/Trio | a, b, c, d, e, f, g, h, i, j, k | 66% | 6.9 | 159 |
| AAPS | odc-39819048, odc-49141524, odc-58680324, odc-61403732, odc-84181797 | 77% | 6.2 | 9 |
| OpenAPS | odc-74077367, odc-86025410, odc-96254963 | 68% | 6.7 | 215 |

### Behavioral Differences

The most striking cross-controller finding is the divergence in AID behavior phenotypes:

| Phenotype | Loop/Trio (n=11) | AAPS/OpenAPS (n=8) |
|-----------|:----------------:|:------------------:|
| COMPENSATING | 5 (45%) | 0 (0%) |
| PASSIVE | 4 (36%) | 0 (0%) |
| AGGRESSIVE | 1 (9%) | 3 (38%) |
| BALANCED | 1 (9%) | 5 (63%) |

**Interpretation**: Loop/Trio's predict-and-suspend architecture drives high suspension rates (55–84%), leading to COMPENSATING and PASSIVE phenotypes. AAPS/OpenAPS uses Super Micro Boluses (SMB) for continuous micro-adjustments, producing lower suspension rates (0–65%) and more BALANCED behavior. The 3 AGGRESSIVE ODC patients (odc-39819048, odc-74077367, odc-84181797) show high correction frequency — consistent with SMB issuing many small corrections rather than long suspensions.

### Do the 11-Patient Findings Generalize?

| Finding (11-patient) | Confirmed by ODC? | Evidence |
|-----------------------|:------------------:|----------|
| ISF increase is top intervention | **Yes** | 6/8 ODC patients benefit most from ISF increase |
| CR universally too aggressive | **Partially** | 5/8 ODC patients have CR ratio <1.0; 3 have CR ≥1.0 (odc-39819048: 2.02, odc-86025410: 1.08, odc-84181797: 1.00) |
| Supply RMSE > Demand RMSE | **No — reversed for AAPS** | 5/8 ODC patients are demand-dominant (Supply% < Demand%) |
| Basal drift is small | **Yes** | ODC basal drift range −0.89 to +0.36, comparable to Loop/Trio |
| ~27% meet TIR+TBR targets | **Yes** | 2/8 ODC patients (25%) meet both targets vs 3/11 (27%) original |
| 4 behavior phenotypes exist | **Yes, but distribution shifts** | Same phenotypes emerge but AAPS/OpenAPS clusters differently |

---

## Results

### EXP-2081: Glycemic Fingerprint

**Question**: What is the multidimensional glycemic profile of each patient?

Each patient's radar shows 6 normalized dimensions (higher = better):

| Patient | TIR | CV | eA1c | Hypo Events | Circ. Range | Controller | Days | Profile |
|---------|:---:|:--:|:----:|:-----------:|:-----------:|:----------:|:----:|---------|
| a | 56% | 45% | 7.9 | 237 | 22 mg/dL | Loop/Trio | 159 | High variability, hyperglycemic |
| b | 57% | 35% | 7.7 | 115 | 19 mg/dL | Trio/oref | 161 | Moderate variability, hyperglycemic |
| c | 62% | 43% | 7.3 | 337 | 26 mg/dL | Loop/Trio | 149 | Mixed risk, frequent hypos |
| d | 79% | 30% | 6.7 | 95 | 33 mg/dL | Loop/Trio | 157 | Well-controlled, stable |
| e | 65% | 37% | 7.3 | 179 | 21 mg/dL | Loop/Trio | 141 | Moderate, hyperglycemic |
| f | 66% | 49% | 7.1 | 230 | 50 mg/dL | Loop/Trio | 160 | Highest circadian amplitude (NS) |
| g | 75% | 41% | 6.7 | 328 | 17 mg/dL | Loop/Trio | 180 | Good TIR but frequent hypos |
| h | 85% | 37% | 5.8 | 264 | 15 mg/dL | Loop/Trio | 60 | Excellent TIR, hypo-prone |
| i | 60% | 51% | 6.9 | 515 | 27 mg/dL | Loop/Trio | 180 | **Most hypos (NS), highest CV** |
| j | 81% | 31% | 6.5 | 66 | 50 mg/dL | Loop/Trio | 55 | Good control, few events |
| k | 95% | 17% | 4.9 | 477 | 12 mg/dL | Loop/Trio | 179 | **Tightest control, many hypos** |
| odc-39819048 | 77% | 38% | 5.8 | 35 | 85 mg/dL | AAPS | 10 | Strong circadian swing |
| odc-49141524 | 61% | 36% | 7.4 | 9 | 94 mg/dL | AAPS | 12 | Hyperglycemic, large circadian range |
| odc-58680324 | 82% | 35% | 6.2 | 12 | 42 mg/dL | AAPS | 9 | Good TIR, moderate circadian |
| odc-61403732 | 94% | 26% | 5.4 | 14 | 40 mg/dL | AAPS | 8 | **Near-optimal (short window)** |
| odc-74077367 | 86% | 33% | 6.1 | 240 | 29 mg/dL | OpenAPS | 215 | Excellent TIR, persistent hypos |
| odc-84181797 | 63% | 46% | 7.3 | 6 | 157 mg/dL | AAPS | 5 | **Largest circadian range in cohort** |
| odc-86025410 | 68% | 45% | 6.7 | 772 | 22 mg/dL | OpenAPS | 374 | **Most hypos in entire cohort** |
| odc-96254963 | 67% | 44% | 6.7 | 324 | 14 mg/dL | OpenAPS | 183 | High variability, many hypos |

**Key insights**:
- **odc-86025410 replaces patient i as the highest hypo-event patient** in the expanded cohort (772 events over 374 days). At 2.06 hypos/day, the rate is comparable to patient i (2.86/day) and k (2.66/day).
- **odc-84181797 has the largest circadian range in the entire cohort** (157 mg/dL) — more than 3× patient f (50 mg/dL), the previous leader. However, this is based on only 5 days of data.
- **odc-61403732 achieves 94% TIR** — comparable to patient k (95%) but with far fewer hypo events (14 vs 477). At only 8 days, this needs longer confirmation but suggests excellent AAPS tuning.
- **Circadian ranges are notably larger for AAPS patients**: median 42 mg/dL (AAPS) vs 22 mg/dL (Loop/Trio). This may reflect differences in how SMB vs suspend-based algorithms handle overnight and dawn-period glucose.

---

### EXP-2082: AID Behavior Clustering

**Question**: Can we classify patients by how their AID loop behaves?

**Method**: Plot suspension rate vs correction frequency. Divide into quadrants by population median.

**Four phenotypes across 19 patients**:

| Phenotype | Patients | Characteristics | Intervention Strategy |
|-----------|----------|----------------|----------------------|
| **COMPENSATING** | b, c, d, e, i | High suspend + high corrections. Loop constantly fighting settings. | Comprehensive settings overhaul |
| **PASSIVE** | f, g, h, k | High suspend, few corrections. Loop managing via suspension. | Reduce basal to stop suspension |
| **AGGRESSIVE** | a, odc-39819048, odc-74077367, odc-84181797 | Low-to-moderate suspend, many corrections. Frequent micro-dosing or manual overcorrection. | Increase ISF, review correction behavior |
| **BALANCED** | j, odc-49141524, odc-58680324, odc-61403732, odc-86025410, odc-96254963 | Lower suspend, fewer corrections. Settings more aligned. | Fine-tune, monitor |

Full data:

| Patient | Phenotype | Suspend% | Corrections/day | TIR | Controller |
|---------|-----------|:--------:|:---------------:|:---:|:----------:|
| a | AGGRESSIVE | 55% | 5.3 | 56% | Loop/Trio |
| b | COMPENSATING | 76% | 10.1 | 57% | Trio/oref |
| c | COMPENSATING | 74% | 11.2 | 62% | Loop/Trio |
| d | COMPENSATING | 80% | 5.3 | 79% | Loop/Trio |
| e | COMPENSATING | 72% | 11.3 | 65% | Loop/Trio |
| f | PASSIVE | 80% | 2.5 | 66% | Loop/Trio |
| g | PASSIVE | 80% | 4.7 | 75% | Loop/Trio |
| h | PASSIVE | 84% | 3.4 | 85% | Loop/Trio |
| i | COMPENSATING | 77% | 20.7 | 60% | Loop/Trio |
| j | BALANCED | 0% | 1.7 | 81% | Loop/Trio |
| k | PASSIVE | 76% | 0.1 | 95% | Loop/Trio |
| odc-39819048 | AGGRESSIVE | 43% | 5.3 | 77% | AAPS |
| odc-49141524 | BALANCED | 26% | 1.2 | 61% | AAPS |
| odc-58680324 | BALANCED | 49% | 1.8 | 82% | AAPS |
| odc-61403732 | BALANCED | 65% | 1.2 | 94% | AAPS |
| odc-74077367 | AGGRESSIVE | 36% | 6.2 | 86% | OpenAPS |
| odc-84181797 | AGGRESSIVE | 0% | 21.3 | 63% | AAPS |
| odc-86025410 | BALANCED | 23% | 1.8 | 68% | OpenAPS |
| odc-96254963 | BALANCED | 52% | 3.3 | 67% | OpenAPS |

**Key findings**:

- **Controller type strongly predicts phenotype**: Loop/Trio's predict-and-suspend architecture produces high suspension rates (median 77%) that cluster patients into COMPENSATING and PASSIVE. AAPS/OpenAPS's SMB architecture produces lower suspension rates (median 38%) that cluster into BALANCED and AGGRESSIVE.
- **Patient odc-84181797 is an extreme outlier**: 0% suspension AND 21.3 corrections/day — the highest correction frequency in the entire cohort. This suggests highly aggressive manual bolusing or very active SMB behavior. With only 5 days of data, this could also reflect a new-user calibration period.
- **BALANCED phenotype now includes 6 patients** (up from 3) — 5 of the 6 additions are AAPS/OpenAPS users. This suggests SMB-based systems achieve better settings alignment, possibly because continuous micro-dosing is more forgiving of miscalibration than suspend-based systems.
- **Patient i remains the sole COMPENSATING patient with extreme correction frequency** (20.7/day), though odc-84181797 exceeds it (21.3/day) — both represent maximally stressed AID behavior through different mechanisms.

---

### EXP-2083: Setting Mismatch Severity

**Question**: How far off is each patient's therapy settings?

**Method**: Composite score (0–10) from ISF mismatch ratio (effective/profile), CR mismatch ratio (actual/expected spike), and fasting basal drift.

| Patient | Severity | ISF Ratio | CR Ratio | Basal Drift | Composite | Controller |
|---------|:--------:|:---------:|:--------:|:-----------:|:---------:|:----------:|
| a | MODERATE | 0.53× | 0.28× | −0.06 | 2.1 | Loop/Trio |
| b | MODERATE | 0.56× | 0.28× | −0.73 | 3.1 | Trio/oref |
| c | LOW | 1.13× | 0.24× | −0.12 | 1.7 | Loop/Trio |
| d | LOW | 1.58× | 0.81× | +0.01 | 1.3 | Loop/Trio |
| e | MODERATE | 1.46× | 0.14× | −1.18 | 4.2 | Loop/Trio |
| f | MODERATE | 0.61× | 0.36× | −0.41 | 2.4 | Loop/Trio |
| g | LOW | 0.94× | 0.45× | −0.23 | 1.4 | Loop/Trio |
| h | MODERATE | 0.53× | 0.17× | +0.44 | 2.9 | Loop/Trio |
| i | LOW | 1.38× | 0.32× | +0.01 | 1.8 | Loop/Trio |
| j | MODERATE | 0.13× | 0.12× | −0.26 | 3.4 | Loop/Trio |
| k | LOW | 1.35× | 0.52× | −0.04 | 1.5 | Loop/Trio |
| odc-39819048 | MODERATE | 1.50× | 2.02× | −0.89 | 4.0 | AAPS |
| odc-49141524 | LOW | 1.47× | 1.00× | +0.36 | 1.4 | AAPS |
| odc-58680324 | LOW | 0.94× | 0.19× | +0.13 | 1.7 | AAPS |
| odc-61403732 | LOW | 0.76× | 0.28× | −0.12 | 1.8 | AAPS |
| odc-74077367 | LOW | 1.16× | 0.35× | −0.01 | 1.4 | OpenAPS |
| odc-84181797 | MODERATE | 1.77× | 1.00× | −0.47 | 2.1 | AAPS |
| odc-86025410 | LOW | 0.70× | 1.08× | −0.33 | 1.2 | OpenAPS |
| odc-96254963 | MODERATE | 0.49× | 0.24× | −0.13 | 2.3 | OpenAPS |

**Key findings**:

- **Patient e still has the highest composite mismatch** (4.2/10), closely followed by odc-39819048 (4.0) — the only AAPS patient with MODERATE severity. odc-39819048's CR ratio of 2.02× (the only value >1.0 by a wide margin) indicates CR is set too conservatively, under-covering meals.
- **CR ratio distribution differs by controller**: Loop/Trio patients have CR ratio 0.12–0.81× (all <1.0, meaning CR is too aggressive). Three AAPS/OpenAPS patients have CR ≥1.0 (odc-39819048: 2.02×, odc-49141524: 1.00×, odc-84181797: 1.00×, odc-86025410: 1.08×). This partially challenges the universal "CR too aggressive" finding from the 11-patient cohort.
- **No patient reaches HIGH severity (>5/10)** — this holds across all 19 patients and all controller types, confirming that AID loops universally mask extreme miscalibration.
- **odc-86025410 has the lowest composite score** (1.2) — the best-calibrated settings in the entire cohort, despite only 68% TIR. With 374 days of OpenAPS data, this patient may represent naturally well-tuned settings with a different primary issue (hypo risk: LBGI 9.9).

---

### EXP-2084: Intervention Impact Ranking

**Question**: Which single setting change helps each patient most?

| Patient | Top Intervention | TIR Gain | Controller |
|---------|-----------------|:--------:|:----------:|
| a | increase_isf_20pct | +2.1pp | Loop/Trio |
| b | dawn_basal_ramp | +1.9pp | Trio/oref |
| c | increase_isf_20pct | +3.0pp | Loop/Trio |
| d | dinner_cr | +1.7pp | Loop/Trio |
| e | dawn_basal_ramp | +1.8pp | Loop/Trio |
| f | increase_isf_20pct | +2.1pp | Loop/Trio |
| g | increase_isf_20pct | +2.6pp | Loop/Trio |
| h | **increase_isf_20pct** | **+4.5pp** | Loop/Trio |
| i | **increase_isf_20pct** | **+6.3pp** | Loop/Trio |
| j | circadian_isf | +2.0pp | Loop/Trio |
| k | **increase_isf_20pct** | **+3.7pp** | Loop/Trio |
| odc-39819048 | **increase_isf_20pct** | **+8.1pp** | AAPS |
| odc-49141524 | increase_isf_20pct | +1.6pp | AAPS |
| odc-58680324 | increase_isf_20pct | +3.5pp | AAPS |
| odc-61403732 | increase_isf_20pct | +2.6pp | AAPS |
| odc-74077367 | increase_isf_20pct | +1.8pp | OpenAPS |
| odc-84181797 | circadian_isf | +1.8pp | AAPS |
| odc-86025410 | increase_isf_20pct | +2.0pp | OpenAPS |
| odc-96254963 | increase_isf_20pct | +4.0pp | OpenAPS |

**Key findings**:

- **ISF increase is the top intervention for 15/19 patients** (79%) — up from 7/11 (64%) in the original cohort. This is the strongest cross-controller finding: profiles systematically underestimate insulin sensitivity regardless of AID system.
- **odc-39819048 has the largest single-intervention gain** (+8.1pp), surpassing patient i (+6.3pp) as the patient who would benefit most. Despite having 77% TIR already, the ISF correction would bring this patient to ~85% TIR.
- **Only 4 patients have a different top intervention**: b and e (dawn_basal_ramp), d (dinner_cr), j and odc-84181797 (circadian_isf). These are the patients whose primary issue is circadian or meal-specific, not global ISF miscalibration.
- **The gain range is wider with ODC data** (1.6–8.1pp vs 1.7–6.3pp) — suggesting more settings variability in the AAPS/OpenAPS population, possibly due to less standardized onboarding compared to Loop/Trio.

---

### EXP-2085: Risk Stratification

**Question**: Which patients have hypo-priority vs hyper-priority risk?

| Patient | LBGI | HBGI | Risk Type | Controller |
|---------|:----:|:----:|:---------:|:----------:|
| a | 0.8 | 11.4 | HYPER | Loop/Trio |
| b | 0.4 | 9.3 | HYPER | Trio/oref |
| c | 1.2 | 8.1 | HYPO | Loop/Trio |
| d | 0.4 | 4.3 | BALANCED | Loop/Trio |
| e | 0.6 | 7.2 | HYPER | Loop/Trio |
| f | 1.1 | 8.1 | HYPER | Loop/Trio |
| g | 0.9 | 5.3 | HYPER | Loop/Trio |
| h | 1.8 | 2.2 | HYPO | Loop/Trio |
| i | 2.6 | 7.4 | HYPO | Loop/Trio |
| j | 0.6 | 3.9 | BALANCED | Loop/Trio |
| k | 2.4 | 0.0 | HYPO | Loop/Trio |
| odc-39819048 | 2.6 | 2.5 | HYPO | AAPS |
| odc-49141524 | 0.6 | 7.9 | HYPER | AAPS |
| odc-58680324 | 1.6 | 3.2 | HYPO | AAPS |
| odc-61403732 | 1.5 | 0.8 | BALANCED | AAPS |
| odc-74077367 | 1.1 | 2.6 | BALANCED | OpenAPS |
| odc-84181797 | 1.0 | 8.7 | HYPER | AAPS |
| odc-86025410 | 9.9 | 6.0 | HYPO | OpenAPS |
| odc-96254963 | 2.4 | 5.9 | HYPO | OpenAPS |

**Population distribution (19 patients)**:

| Risk Type | Loop/Trio (n=11) | AAPS/OpenAPS (n=8) | Total |
|-----------|:----------------:|:------------------:|:-----:|
| HYPO | 4 (36%) | 4 (50%) | 8 (42%) |
| HYPER | 5 (45%) | 2 (25%) | 7 (37%) |
| BALANCED | 2 (18%) | 2 (25%) | 4 (21%) |

**Key findings**:

- **odc-86025410 has the highest LBGI in the entire cohort** (9.9) — nearly 4× the next highest (i and odc-39819048 at 2.6). This patient has 772 hypo events over 374 days, averaging 2.06/day. Despite OpenAPS's SMB capability, this patient has severe hypo-risk likely driven by over-aggressive settings.
- **AAPS/OpenAPS patients skew toward HYPO risk** (4/8 = 50% vs 4/11 = 36% for Loop/Trio). This may reflect SMB's tendency to deliver more insulin more frequently, increasing hypoglycemia risk when settings are overcalibrated.
- **Patient i retains the highest combined risk** (LBGI 2.6 + HBGI 7.4 = 10.0) among Loop/Trio patients, but odc-86025410 has the highest combined (LBGI 9.9 + HBGI 6.0 = 15.9) in the entire cohort — the most dangerous glucose profile observed.
- **BALANCED risk is equally distributed**: 2/11 Loop/Trio (d, j) and 2/8 AAPS/OpenAPS (odc-61403732, odc-74077367) achieve balanced risk — roughly 20% of each group.

---

### EXP-2086: Temporal Stability

**Question**: Do patients' glycemic profiles change over the observation period?

**Note**: Requires ≥2 full calendar months of data. 7 patients excluded (d, j with insufficient data in original cohort; odc-39819048, odc-49141524, odc-58680324, odc-61403732, odc-84181797 with <2 weeks of ODC data).

| Patient | Pattern | TIR Range | Slope/mo | Months | Controller |
|---------|---------|:---------:|:--------:|:------:|:----------:|
| a | VARIABLE DECLINING | 13.3% | −0.033 | 5 | Loop/Trio |
| b | VARIABLE IMPROVING | 16.7% | +0.024 | 5 | Trio/oref |
| c | STABLE FLAT | 3.8% | −0.001 | 4 | Loop/Trio |
| e | MODERATE IMPROVING | 7.6% | +0.020 | 4 | Loop/Trio |
| f | VARIABLE IMPROVING | 19.2% | +0.037 | 5 | Loop/Trio |
| g | VARIABLE DECLINING | 11.5% | −0.018 | 5 | Loop/Trio |
| h | MODERATE IMPROVING | 5.4% | +0.054 | 2 | Loop/Trio |
| i | VARIABLE DECLINING | 19.1% | −0.016 | 5 | Loop/Trio |
| k | MODERATE DECLINING | 6.3% | −0.011 | 5 | Loop/Trio |
| odc-74077367 | VARIABLE DECLINING | 11.4% | −0.015 | 7 | OpenAPS |
| odc-86025410 | VARIABLE FLAT | 27.7% | +0.002 | 12 | OpenAPS |
| odc-96254963 | VARIABLE IMPROVING | 17.7% | +0.018 | 5 | OpenAPS |

**Key findings**:

- **odc-86025410 provides the longest observation window** in the entire cohort (12 months, 374 days) — classifying as VARIABLE FLAT with a TIR range of 27.7% and near-zero slope (+0.002/month). This patient's TIR swings month-to-month but shows no systematic trend, suggesting stable-but-volatile glycemic control.
- **5/12 analyzable patients are DECLINING** (a, g, i, k, odc-74077367) — the addition of odc-74077367 (7 months, OpenAPS) confirms that settings drift affects all AID systems, not just Loop/Trio.
- **4/12 analyzable patients are IMPROVING** (b, e, f, h, odc-96254963) — odc-96254963 is improving at +0.018/month over 5 months on OpenAPS.
- **Clinical implication remains unchanged**: Settings are NOT static. Approximately 40% of patients show meaningful monthly decline regardless of controller type — periodic re-assessment is universally needed.

---

### EXP-2087: Supply-Demand Loss Decomposition

**Question**: Can we separate model error into supply (insulin/carb) and demand (hepatic/utilization) components?

**Method**: Classify each 5-minute step by IOB level:
- **Supply-dominated**: IOB > 1.0 U (insulin actively working)
- **Demand-dominated**: IOB < 0.3 U (minimal insulin influence)

| Patient | Total RMSE | Supply RMSE | Demand RMSE | Supply% | Demand% | Controller |
|---------|:----------:|:-----------:|:-----------:|:-------:|:-------:|:----------:|
| a | 24.83 | 28.53 | 18.86 | 65% | 17% | Loop/Trio |
| b | 47.89 | 58.62 | 21.59 | 60% | 23% | Trio/oref |
| c | 29.82 | 41.97 | 12.15 | 46% | 40% | Loop/Trio |
| d | 8.39 | 9.85 | 6.69 | 47% | 40% | Loop/Trio |
| e | 34.81 | 39.34 | 22.21 | 70% | 20% | Loop/Trio |
| f | 14.78 | 18.79 | 7.18 | 56% | 31% | Loop/Trio |
| g | 29.99 | 34.34 | 24.76 | 58% | 22% | Loop/Trio |
| h | 40.80 | 71.21 | 8.29 | 32% | 47% | Loop/Trio |
| i | 15.81 | 20.27 | 8.67 | 52% | 37% | Loop/Trio |
| j | 9.41 | N/A | 9.41 | 0% | 100% | Loop/Trio |
| k | 6.60 | 7.65 | 5.96 | 39% | 42% | Loop/Trio |
| odc-39819048 | 12.64 | 16.63 | 7.51 | 47% | 37% | AAPS |
| odc-49141524 | 7.94 | 9.72 | 7.55 | 20% | 74% | AAPS |
| odc-58680324 | 28.14 | 44.48 | 12.91 | 33% | 57% | AAPS |
| odc-61403732 | 25.96 | 48.09 | 9.98 | 25% | 56% | AAPS |
| odc-74077367 | 38.05 | 44.66 | 26.73 | 56% | 30% | OpenAPS |
| odc-84181797 | 6.03 | N/A | 6.01 | 0% | 100% | AAPS |
| odc-86025410 | 17.62 | 34.07 | 13.49 | 6% | 76% | OpenAPS |
| odc-96254963 | 43.35 | 61.34 | 20.09 | 44% | 46% | OpenAPS |

**Cross-controller decomposition comparison**:

| Metric | Loop/Trio (n=11) | AAPS/OpenAPS (n=8) |
|--------|:----------------:|:------------------:|
| Median Supply% | 52% | 25% |
| Median Demand% | 31% | 57% |
| Patients with Supply% > Demand% | 8/11 (73%) | 3/8 (38%) |
| Supply RMSE / Demand RMSE ratio | ~2.0× | ~3.0× |

**Key findings**:

1. **Supply-demand balance differs fundamentally by controller architecture**:
   - **Loop/Trio patients are supply-dominant** — they spend more time with IOB >1.0 (median Supply% 52%), consistent with higher basal rates that the loop then suspends.
   - **AAPS/OpenAPS patients are demand-dominant** — they spend more time with IOB <0.3 (median Demand% 57%), consistent with SMB's strategy of delivering smaller, more frequent doses that decay faster.

2. **Two patients have no measurable supply component**: j (Loop/Trio, 0% suspend, effectively open-loop) and odc-84181797 (AAPS, 0% suspend, 5 days). Both have 100% demand-dominated error — their insulin delivery is minimal enough that all observed glucose variance comes from endogenous processes.

3. **When AAPS/OpenAPS patients DO have supply error, the ratio is even more extreme**: odc-58680324 (Supply RMSE 44.48 vs Demand RMSE 12.91 = 3.4×), odc-61403732 (48.09 vs 9.98 = 4.8×). This suggests that when SMB does deliver significant insulin, the pharmacokinetic model error is even larger — possibly because SMB pulse timing doesn't match the assumed exponential absorption curve.

4. **odc-86025410 is an anomaly**: Supply% is only 6% despite 374 days of OpenAPS data. This patient operates in a persistently low-IOB state while having the highest LBGI (9.9) — suggesting that even small insulin doses cause disproportionate hypoglycemia, pointing to extreme insulin sensitivity.

**Implications for phased estimation**:
- The phased estimation approach (basal from demand windows, ISF from supply windows, CR from transitions) remains valid but **the available estimation windows differ by controller type**:
  - Loop/Trio: abundant supply-dominated windows for ISF estimation
  - AAPS/OpenAPS: abundant demand-dominated windows for basal estimation, but fewer supply-dominated windows for ISF
  - This means **ISF estimation may be less reliable for AAPS/OpenAPS patients** using this decomposition — an important methodological caveat

---

### EXP-2088: Actionable Summary

**Question**: What is the single most important recommendation for each patient?

| Patient | Status | TIR | TBR | eA1c | Top Recommendation | Controller |
|---------|:------:|:---:|:---:|:----:|-------------------|:----------:|
| a | ✗ | 56% | 3.0% | 7.9 | HYPERGLYCEMIA: Reduce CR for more aggressive meal coverage | Loop/Trio |
| b | ✗ | 57% | 1.0% | 7.7 | BASAL: Reduce basal rate (loop suspending >70%) | Trio/oref |
| c | ✗ | 62% | 4.7% | 7.3 | **SAFETY: Increase ISF to reduce overcorrection hypos** | Loop/Trio |
| d | ✓ | 79% | 0.8% | 6.7 | BASAL: Reduce basal rate (loop suspending >70%) | Loop/Trio |
| e | ✗ | 65% | 1.8% | 7.3 | BASAL: Reduce basal rate (loop suspending >70%) | Loop/Trio |
| f | ✗ | 66% | 3.0% | 7.1 | BASAL: Reduce basal rate (loop suspending >70%) | Loop/Trio |
| g | ✓ | 75% | 3.2% | 6.7 | BASAL: Reduce basal rate | Loop/Trio |
| h | ✗ | 85% | 5.9% | 5.8 | **SAFETY: Increase ISF to reduce overcorrection hypos** | Loop/Trio |
| i | ✗ | 60% | 10.7% | 6.9 | **SAFETY: Increase ISF to reduce overcorrection hypos** | Loop/Trio |
| j | ✓ | 81% | 1.1% | 6.5 | MONITOR — settings adequate | Loop/Trio |
| k | ✗ | 95% | 4.9% | 4.9 | **SAFETY: Increase ISF to reduce overcorrection hypos** | Loop/Trio |
| odc-39819048 | ✗ | 77% | 11.0% | 5.8 | **SAFETY: Increase ISF to reduce overcorrection hypos** | AAPS |
| odc-49141524 | ✗ | 61% | 1.8% | 7.4 | HYPERGLYCEMIA: Reduce CR for more aggressive meal coverage | AAPS |
| odc-58680324 | ✗ | 82% | 5.3% | 6.2 | **SAFETY: Increase ISF to reduce overcorrection hypos** | AAPS |
| odc-61403732 | ✓ | 94% | 2.6% | 5.4 | MONITOR — settings adequate | AAPS |
| odc-74077367 | ✓ | 86% | 2.3% | 6.1 | MONITOR — settings adequate | OpenAPS |
| odc-84181797 | ✗ | 63% | 1.5% | 7.3 | HYPERGLYCEMIA: Reduce CR for more aggressive meal coverage | AAPS |
| odc-86025410 | ✗ | 68% | 6.0% | 6.7 | **SAFETY: Increase ISF to reduce overcorrection hypos** | OpenAPS |
| odc-96254963 | ✗ | 67% | 7.5% | 6.7 | **SAFETY: Increase ISF to reduce overcorrection hypos** | OpenAPS |

**Population target achievement**:

| Criteria | Loop/Trio (n=11) | AAPS/OpenAPS (n=8) | Total (n=19) |
|----------|:----------------:|:------------------:|:------------:|
| TIR ≥70% | 5 (45%) | 5 (63%) | 10 (53%) |
| TBR ≤4% | 6 (55%) | 4 (50%) | 10 (53%) |
| **Both TIR≥70% AND TBR≤4%** | **3 (27%)** | **2 (25%)** | **5 (26%)** |

Patients meeting both targets: **d, g, j** (Loop/Trio) and **odc-61403732, odc-74077367** (AAPS/OpenAPS)

**Action distribution across 19 patients**:

| Action Category | Count | Patients |
|----------------|:-----:|----------|
| SAFETY: Increase ISF | 8 | c, h, i, k, odc-39819048, odc-58680324, odc-86025410, odc-96254963 |
| BASAL: Reduce basal | 4 | b, d, e, f |
| HYPERGLYCEMIA: Reduce CR | 3 | a, odc-49141524, odc-84181797 |
| MONITOR | 3 | j, odc-61403732, odc-74077367 |
| BASAL: Reduce basal (minor) | 1 | g |

---

## Cross-Experiment Synthesis

### Patient Phenotype × Controller × Intervention Matrix

| Phenotype | Loop/Trio Patients | AAPS/OpenAPS Patients | Primary Issue | Top Intervention |
|-----------|-------------------|----------------------|---------------|-----------------|
| COMPENSATING | b, c, d, e, i | — | Swinging extremes, high suspend + corrections | Settings overhaul (ISF + basal) |
| PASSIVE | f, g, h, k | — | Over-basaling → suspension | Reduce basal |
| AGGRESSIVE | a | odc-39819048, odc-74077367, odc-84181797 | Frequent corrections / micro-dosing | Increase ISF |
| BALANCED | j | odc-49141524, odc-58680324, odc-61403732, odc-86025410, odc-96254963 | Stable but suboptimal | Fine-tune or monitor |

### The Settings Optimization Cascade (Updated for Multi-Controller)

Based on all experiments (EXP-2041–2088) across 19 patients and 4 controller types:

1. **Increase ISF** (+20% minimum) → Prevents overcorrection; **top intervention for 79% of patients across ALL controller types**
2. **Reduce basal** (−12% population mean, Loop/Trio primarily) → Stops the suspension cycle
3. **Adjust dinner CR** (50% more aggressive, controller-dependent) → Controls the hardest meal
4. **Add dawn ramp** (+0.4–1.8 U/hr, onset 1–2am) → Prevents morning highs
5. **Monitor for drift** (monthly TIR check) → Catches the ~40% of patients with declining control

**Controller-specific notes**:
- **Loop/Trio**: Steps 1–2 are equally important; the suspend cycle must be broken
- **AAPS/OpenAPS**: Step 1 is dominant; SMB already manages micro-dosing but ISF miscalibration causes over-delivery

### Supply-Demand Decomposition: Controller Architecture Matters

The most significant new finding from the expanded cohort:

| Architecture | Insulin Strategy | Supply% | Demand% | Implication |
|-------------|-----------------|:-------:|:-------:|-------------|
| **Suspend-based** (Loop/Trio) | High basal + suspend when predicted low | 52% | 31% | Supply-dominant errors; fix basal first |
| **SMB-based** (AAPS/OpenAPS) | Low basal + frequent micro-bolus | 25% | 57% | Demand-dominant errors; ISF matters most |

This architectural difference means the **phased estimation approach** needs controller-aware windowing:
- Loop/Trio provides ample supply-dominated windows for ISF estimation
- AAPS/OpenAPS provides ample demand-dominated windows for basal estimation but fewer supply windows for ISF
- A unified estimation pipeline must account for this structural difference

---

## Data Quality & Limitations

### ODC Data Quality Summary

| Patient | Days | Coverage | Quality Notes |
|---------|:----:|:--------:|---------------|
| odc-39819048 | 10 | Good | Sufficient for fingerprint/clustering; insufficient for temporal stability |
| odc-49141524 | 12 | Good | Short observation; supply-demand decomposition may be unrepresentative |
| odc-58680324 | 9 | Good | Very short; results should be interpreted as preliminary |
| odc-61403732 | 8 | Good | Shortest observation; 94% TIR needs longer confirmation |
| odc-74077367 | 215 | Good | Robust dataset; profile had unsorted `timeAsSeconds` (fixed by terrarium rebuild) |
| odc-84181797 | 5 | **4% glucose coverage** | **Critically sparse**; fingerprint metrics unreliable; 157 mg/dL circadian range likely artifact |
| odc-86025410 | 374 | Good | Longest observation in cohort; robust temporal analysis possible |
| odc-96254963 | 183 | Good | Robust dataset comparable to NS patients |

### Systematic Limitations

1. **Observation period asymmetry**: Loop/Trio patients have median 159 days; AAPS patients have median 9 days; OpenAPS patients have median 215 days. Cross-controller comparisons must account for this — particularly for metrics that aggregate over time (hypo event counts, temporal stability).

2. **ODC format adapter**: The ns2parquet pipeline was extended with a new format adapter to ingest AAPS-native JSON and Nightscout-export formats. While the 49-column research grid is identical, field availability differs:
   - AAPS-native JSON provides detailed SMB/TBR records but different IOB calculation methods
   - Some ODC patients may have gaps in pump/loop data that don't exist in the Nightscout patients' direct upload pipeline

3. **Terrarium rebuild**: The `_lookup_schedule()` sort bug fix ensures correct ISF/CR/basal interpolation for profiles with unsorted `timeAsSeconds` entries. This primarily affected odc-74077367 and may have had minor effects on other ODC patients. All results in this report use the corrected terrarium.

4. **odc-84181797 should be treated as provisional**: With only 5 days and 4% glucose coverage, this patient's metrics (157 mg/dL circadian range, 21.3 corrections/day, 0% suspend) may not represent stable behavior. All findings involving this patient should be flagged as low-confidence.

5. **Simplified phenotyping**: The 4-phenotype classification uses only 2 dimensions (suspension rate, correction frequency). The strong controller-type correlation suggests that the phenotype may partly reflect algorithmic architecture rather than patient/settings characteristics. A future analysis should control for controller type when clustering.

6. **Intervention simulation is static**: TIR gains from individual interventions don't account for interaction effects. The true combined benefit may be larger or smaller. Cross-controller intervention modeling assumes ISF/CR/basal have equivalent physiological meaning across controller types — this is approximately but not exactly true (e.g., Loop's ISF is used for correction predictions; AAPS's ISF feeds into SMB sizing differently).

7. **No causal inference**: We observe correlations between settings, loop behavior, and outcomes. We cannot prove that changing settings will produce the predicted improvement without prospective testing. This is especially important for the ODC patients, where we have no longitudinal setting-change data.

---

## Conclusions

1. **ISF increase is the most universally impactful intervention across ALL AID systems** — top intervention for 15/19 patients (79%) regardless of Loop, Trio, AAPS, or OpenAPS controller. This is the strongest finding from the expanded cohort: profiles systematically underestimate insulin sensitivity, and this bias is controller-independent.

2. **AID behavior phenotypes are real but controller-correlated** — the 4-phenotype framework (Compensating, Passive, Aggressive, Balanced) holds in the expanded cohort, but phenotype distribution is strongly predicted by controller architecture. Loop/Trio's suspend-based design produces Compensating and Passive phenotypes; AAPS/OpenAPS's SMB design produces Balanced and Aggressive phenotypes.

3. **Supply-demand decomposition reveals controller architecture effects** — Loop/Trio is supply-dominant (median 52% supply time), AAPS/OpenAPS is demand-dominant (median 57% demand time). This means ISF estimation reliability differs by controller type and the phased estimation pipeline needs controller-aware windowing.

4. **The 26% target-achievement rate is controller-independent** — 3/11 Loop/Trio (27%) and 2/8 AAPS/OpenAPS (25%) meet both TIR≥70% AND TBR≤4%. The consistency across controller types suggests the bottleneck is settings calibration, not algorithmic capability.

5. **Settings drift affects all AID systems** — 5/12 analyzable patients show declining TIR including one OpenAPS patient with a 7-month observation window. Monthly re-assessment is universally needed.

6. **ODC data confirms core findings while revealing controller-specific nuances** — the expanded cohort validates the intervention hierarchy (ISF > basal > CR > dawn ramp) while showing that the mechanism by which settings errors manifest differs by controller architecture.

---

## Reproducibility

```bash
PYTHONPATH=tools python3 tools/cgmencode/exp_phenotyping_2081.py --figures --include-odc
```

Output: 8 experiments, 19 patients, 8 figures (`pheno-fig01` through `pheno-fig08`), 8 JSON result files in `externals/experiments/`.

ODC data ingestion:
```bash
PYTHONPATH=tools python3 tools/ns2parquet/odc_adapter.py --input externals/odc/ --output externals/parquet/
```
