# Therapy Advanced Analytics & Population Insights Report

**Experiments**: EXP-1471 through EXP-1480  
**Date**: 2026-04-10  
**Campaign**: Therapy Detection & Recommendation (experiments 191–200)  
**Patients**: 11 (a–k), ~180 days each, ~50K timesteps per patient

## Executive Summary

This batch explores population-level insights and advanced analytics, reaching the **200-experiment milestone**. Key findings: 4 natural patient clusters emerge from therapy profiles, recommendation direction transfers perfectly between similar patients (10/10), weekend vs weekday differences are statistically insignificant (0/11 p<0.05), insulin stacking is prevalent (9/11) with 2-18% hypo risk, and all patients have low glycemic risk (LBGI/HBGI). The sequential fix protocol (Strategy C) outperforms single-parameter fixes by 40-90% for multi-flag patients.

## Experiment Results

### EXP-1471: Population Clustering by Therapy Profile

**Objective**: Cluster patients by multi-dimensional therapy features.

**Findings**:
- **4 natural clusters** (optimal k=4 by silhouette):
  - Cluster 0 (e, f, i): moderate TIR, high variability — "volatile improvers"
  - Cluster 1 (b, j): mixed TIR, low CV — "consistent but suboptimal"
  - Cluster 2 (h, k): high TIR, moderate-low CV — "well-controlled"
  - Cluster 3 (a, c, d, g): wide TIR range, high CV — "diverse needs"
- Cluster 3 is heterogeneous (TIR 56-79%) — subclustering may help

**Clinical Implication**: Clustering identifies natural patient groupings beyond simple grading. Cluster-based protocol assignment could streamline clinical workflows for larger populations.

---

### EXP-1472: Inter-Patient Transfer of Recommendations

**Objective**: Test whether similar patients share recommendation directions.

**Findings**:
- **Direction agreement: 100% for 10/11 pairs** (nearest neighbor by features)
- Patient k is the only exception (0% agreement with nearest neighbor h — opposite therapy needs)
- Grade agreement: 8/11 pairs match grades
- Feature distances: 0.787-1.085 (moderate spread)

**Clinical Implication**: For patients with insufficient data, recommendations can be bootstrapped from similar patients. Exception: well-controlled outliers (k) should not transfer to others.

---

### EXP-1473: Meal Pattern Deep Dive

**Objective**: Detailed meal analysis by time-of-day category.

**Findings**:
- **Patient b is an extreme outlier**: 23.4 meals/day (likely micro-dosing or data artifact)
- Typical range: 0.4-4.5 meals/day
- Snacks dominate carb entry counts for most patients
- Patients i and k have very low meal frequency (0.6 and 0.4/day) — possibly unlogged meals
- Meal regularity score: 0.79-1.19 (d and g most regular)

**Clinical Implication**: Meal logging practices vary enormously. Patient b's 23.4 meals/day suggests automated carb entries or micro-corrections counted as meals. Low-frequency patients may have unlogged meals confounding CR analysis.

---

### EXP-1474: Activity/Exercise Proxy Detection

**Objective**: Detect exercise-like glucose drops without explicit activity data.

**Findings**:
- Detection rate: 1.8-7.5 events/day (high — likely includes non-exercise drops)
- Mean glucose drop: 18-52 mg/dL per event
- Post-event TIR: 62-86% (higher TIR patients have better post-event recovery)
- Most common timing: variable by patient (morning for f, afternoon for b/e/i, overnight for d, evening for g)

**Clinical Implication**: The proxy detection is too sensitive — 7+ events/day likely includes insulin-driven and AID-driven drops, not just exercise. Tighter criteria (>3 mg/dL/5min sustained >20min, no IOB >2U) needed for clinical use.

---

### EXP-1475: Weekend vs Weekday Protocol Differences

**Objective**: Test for statistically significant weekday/weekend TIR differences.

**Findings**:
- **0/11 patients show statistically significant difference** (all p>0.05)
- TIR differences range from -4.0% to +5.9% but none reach significance
- CV differences are negligible (<3% absolute)
- Patient a has the largest trend (+5.9% weekend advantage, p=0.07 — borderline)

**Clinical Implication**: Weekend vs weekday therapy protocol differentiation is NOT justified for this cohort. Consistent therapy settings are appropriate 7 days/week.

---

### EXP-1476: Insulin Stacking Detection

**Objective**: Detect multi-bolus insulin stacking and its consequences.

**Findings**:
- **9/11 patients have stacking events** (all except j and b≈0)
- Stacking rates: 0.1-25.7 events/week (k highest at 25.7)
- **Hypo rate after stacking**: 2.1-18.3% (patient h worst at 18.3%)
- Patient f has highest peak IOB during stacking (14.3 U)
- Dominant stacking type: correction stacking (6/11) > mixed (4/11)

**Clinical Implication**: Correction stacking is the primary hypo risk mechanism. Patients with >10% post-stacking hypo rate (a, c, g, h, i, k) need real-time stacking alerts. AID systems' auto-corrections are a major stacking contributor.

---

### EXP-1477: Glycemic Risk Scoring (LBGI/HBGI)

**Objective**: Compute standardized glycemic risk indices.

**Findings**:
- **All 11 patients: LOW risk** on both LBGI and HBGI
- LBGI range: 0.04-0.26 (all <2.5 threshold)
- HBGI range: 0.00-1.14 (all <4.5 threshold)
- Patient a has highest HBGI (1.14) — consistent with grade D
- Patient i has highest LBGI (0.26) — tight control causes mild low risk

**Clinical Implication**: All patients are in the low-risk category by standard LBGI/HBGI metrics. This is expected for AID users — the algorithm prevents extreme values. LBGI/HBGI may not discriminate well within AID populations where extremes are actively mitigated.

---

### EXP-1478: Comparative Effectiveness of Fix Strategies

**Objective**: Compare single-fix vs all-fix vs sequential-fix strategies.

**Findings**:
- **Strategy C (sequential) wins for all multi-flag patients** (a, d, g, j): +40-90% vs single fix
- **Strategy A (single best) = B = C for single-flag patients** (b, c, e, f, h, i): no difference
- Sequential advantage for patient a: 26.1% vs 15.5% (single) — 68% improvement
- Patient k: all strategies = 0% (no fix needed)

**Clinical Implication**: The sequential protocol adds significant value only for multi-parameter patients. For single-issue patients, just fixing the one flagged parameter is sufficient. This validates the failure-mode routing approach.

---

### EXP-1479: Temporal Glucose Entropy

**Objective**: Quantify glycemic complexity via information-theoretic measures.

**Findings**:
- **Sample entropy correlates positively with TIR** (r≈0.76): higher entropy = more random = better control
- Patient k: highest SampEn (0.81) and PermEn (0.94) — most "random" (well-controlled)
- Patient f: lowest SampEn (0.22) — most predictable/structured glucose patterns
- PermEn range: 0.75-0.94 (less discriminating than SampEn)

**Clinical Implication**: Counter-intuitively, higher glucose entropy indicates better control — glucose varies randomly within range rather than showing structured excursion patterns. Low entropy patients have systematic glucose patterns (dawn phenomenon, post-meal spikes) that could be targeted.

---

### EXP-1480: 200-Experiment Campaign Milestone Summary

**Objective**: Comprehensive campaign summary at the 200-experiment milestone.

**Findings**:
- **Grade distribution**: 1 D, 8 C, 1 B, 1 A
- **All 11 patients: low glycemic risk** (LBGI/HBGI both low)
- **Deployment ready**: 2/11 (h, k) — grade B+ and stable recommendations
- **Failure modes**: 6 mixed, 2 well-controlled, 2 correction-dominant, 1 basal-dominant
- **First-fix priority**: basal adjustment for 7/11, ISF for 2/11, none for 2/11 (note: top overall recommendation by impact is CR adjustment for 6/11)

**Campaign Statistics**:
- Total experiments: 200 (EXP-1281 through EXP-1480)
- Total patient-experiments: 2,200 (200 × 11 patients)
- Reports written: 20
- Pipeline version: v9 (deployment-ready)

---

## Key Findings Summary

| # | Finding | Impact |
|---|---------|--------|
| 1 | 4 natural patient clusters | Enables cluster-based protocol assignment |
| 2 | 100% direction transfer for 10/11 pairs | Bootstrap recommendations for new patients |
| 3 | Meal logging varies enormously (0.4-23.4/day) | CR analysis needs logging quality filter |
| 4 | Exercise proxy too sensitive (7+/day) | Needs tighter criteria for clinical use |
| 5 | Weekend≠weekday: 0/11 significant | No schedule-based protocol needed |
| 6 | Insulin stacking in 9/11, 2-18% hypo risk | Stacking alerts high priority |
| 7 | All patients low LBGI/HBGI | Standard risk scores don't discriminate AID users |
| 8 | Sequential fix +40-90% for multi-flag patients | Validates protocol for complex cases |
| 9 | Higher entropy = better control (r≈0.76) | Low-entropy patients have targetable patterns |
| 10 | 200 experiments complete, pipeline v9 validated | Campaign milestone reached |

## 200-Experiment Campaign Summary

### Major Breakthroughs (Top 10)

1. **Supply/demand glucose decomposition** works for therapy detection (EXP-1281-1290)
2. **Precondition gating** eliminates false positives (EXP-1291-1300)
3. **ISF response curves** R²=0.75-0.80 with τ=2.0h (EXP-1301-1310)
4. **UAM universal threshold** 1.0 mg/dL/5min transfers across all patients (EXP-1311-1320)
5. **Sequential fix order** basal→CR→ISF proven independent (EXP-1414)
6. **Conservative basal ±10%** optimal, aggressive hurts (EXP-1416)
7. **CR needs -30% adjustment** (not ±10% like basal) (EXP-1423)
8. **Observational TIR gaps** bypass simulation limitations (EXP-1441)
9. **Pipeline robust to 50% data dropout** (EXP-1461)
10. **Detection within 8 days** for all patients (EXP-1457)

### Validated Negative Results (Top 5)

1. Simulation cannot capture AID feedback — 0/11 grade transitions (EXP-1421, 1431)
2. Physics model fidelity R²=1.3% at 5-min resolution (EXP-1403)
3. Meal regularity has ZERO TIR correlation (EXP-1427)
4. Weekend vs weekday differences not significant (EXP-1475)
5. LBGI/HBGI don't discriminate within AID population (EXP-1477)

### Pipeline v9 Final Specification

```
PROVEN CAPABILITIES:
  ✅ Basal drift detection (overnight glucose, ±10% adjustment)
  ✅ CR miscalibration detection (per-meal excursion, -30% adjustment)
  ✅ ISF discordance detection (correction vs meal context)
  ✅ Failure mode classification (5-way routing)
  ✅ Sequential fix ordering (proven independent)
  ✅ Confidence gating (bootstrap CIs, coverage-aware)
  ✅ Priority scoring (ρ=0.782 with severity)
  ✅ Noise/sparsity robustness (σ≤10, coverage≥50%)
  ✅ Integration validated (11/11 pass, <20ms)
  ✅ Population clustering (4 natural groups)
  ✅ Insulin stacking detection (hypo risk)

KNOWN LIMITATIONS:
  ❌ Prospective simulation (AID feedback invalidates)
  ❌ Exercise detection (proxy too sensitive)
  ❌ Dual-ISF implementation (ratio too variable)
  ❌ LBGI/HBGI discrimination in AID users
  ❌ Meal logging quality varies too much for universal CR
```
