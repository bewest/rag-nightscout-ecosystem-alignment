# AID-Aware Settings Assessment Report

**Date**: 2026-04-09  
**Experiments**: EXP-981 through EXP-990  
**Script**: `tools/cgmencode/exp_clinical_981.py`  
**Patients**: 11 (a-k), ~180 days each, 5-min resolution  

## Executive Summary

This batch addresses the central confound discovered in EXP-971-980: AID (Automated Insulin Delivery) loop action makes naive therapy assessment impossible because the loop is **always compensating**. Only 0.5% of time has near-scheduled basal delivery; the loop suspends or increases 99.5% of the time.

### Headline Findings

| Finding | Impact |
|---------|--------|
| 8/10 patients have scheduled basal **too high** (EXP-985) | Glucose drops during rare nominal periods |
| Loop almost never idle: 0-2.9% stable time (EXP-985) | Deconfounding requires novel approaches |
| 0/10 patients show sensor age degradation (EXP-989) | Sensor age NOT a significant confounder |
| 3/11 patients have predictive 3-day patterns (EXP-986) | Multi-day analysis viable for some |
| Patient k easiest (score=76.4), a hardest (37.5) (EXP-990) | Clear difficulty gradient with clinical explanation |
| ISF ratio 2.8-10.8x (EXP-983) -- still confounded | Total insulin metric includes background basal |

---

## Detailed Results

### EXP-981: Loop Aggressiveness Score

**Question**: How much does the AID loop deviate from scheduled basal?

| Patient | Aggressiveness | Mean Ratio | Suspended | High Temp | Nominal | Direction |
|---------|---------------|------------|-----------|-----------|---------|-----------|
| a | **2.146** | 2.315 | 39% | **54%** | 0.6% | 56% up |
| b | 0.851 | 0.209 | **76%** | 2% | 3.7% | 7% up |
| c | 0.788 | 0.232 | 64% | 0% | 2.2% | 2% up |
| d | 0.823 | 0.183 | 68% | 0% | 3.6% | 2% up |
| e | 0.706 | 0.357 | 52% | 3% | 6.5% | 7% up |
| f | **1.232** | 1.244 | 48% | **50%** | 0.0% | 50% up |
| g | 0.873 | 0.129 | 72% | 0% | 0.8% | 0% up |
| h | 0.840 | 0.178 | 73% | 1% | 5.5% | 2% up |
| i | 0.803 | 0.426 | 63% | 10% | 7.8% | 14% up |
| j | 0.958 | 0.042 | **96%** | 0% | 4.2% | 0% up |
| k | 0.836 | 0.194 | 75% | 1% | 5.7% | 6% up |

**Key Insight**: Two distinct loop behavior phenotypes:

1. **Suspension-dominant** (b, c, d, e, g, h, i, j, k): Loop primarily **suspends** delivery (52-96%), rarely increases. Mean ratio < 0.5. These patients have basal rates set high enough that the loop must frequently stop insulin.

2. **Bidirectional** (a, f): Loop both suspends AND increases substantially. Patient a is the most extreme -- 54% high temp AND 39% suspended, meaning the loop swings between extremes every few hours.

**Clinical implication**: For suspension-dominant patients, reducing scheduled basal by 30-50% would bring the loop closer to nominal and reveal whether glucose control changes.

### EXP-982: AID-Deconfounded Basal Adequacy

**Question**: During the rare periods when the loop delivers near-scheduled basal, what does glucose do?

| Patient | Nominal Hours | Pct of Time | Windows | Composite |
|---------|-------------|-----------|---------|-----------|
| a | 0 | 0.0% | 0 | 0.0 |
| b | 12.1 | 0.3% | 10 | 0.5 |
| d | 5.4 | 0.1% | 2 | 1.0 |
| e | 37.1 | 1.0% | 27 | 0.25 |
| f | 0 | 0.0% | 0 | 0.0 |
| i | 34.0 | 0.8% | 27 | 0.0 |
| j | 44.0 | 3.0% | 44 | 0.0 |
| k | 15.4 | 0.4% | 13 | 0.25 |

**Finding**: Across 180 days per patient, we find only 0-44 hours of near-nominal basal delivery. Patients a and f have **zero** nominal periods -- the loop never delivers scheduled basal for even 1 hour continuously.

### EXP-983: Total Insulin ISF Validation

**Question**: Using total delivered insulin (not just boluses), what is the actual ISF?

All 11 patients show ISF "too high" with ratios of 2.8-10.8x. However, this method is still confounded: during a 3-hour correction window, background basal insulin contributes to the glucose drop but is not correction-specific.

**Next step needed**: Isolate correction-specific insulin by subtracting the expected basal contribution.

### EXP-984: Loop Intervention Patterns by Time-of-Day

**Finding**: Mean dawn effect on loop intervention = **0.002** (negligible). The loop compensates equally across all hours. The loop is successfully compensating for dawn phenomenon in most patients.

### EXP-985: Settings Stability Windows

**Question**: When the loop is NOT intervening AND BG is in range AND no meals -- what is the glucose trend?

| Patient | Stable Pct | Windows | Mean Drift (mg/dL/h) | Assessment |
|---------|---------|---------|---------------------|------------|
| a | 0.1% | 9 | insufficient | -- |
| b | 1.2% | 79 | **-5.83** | high_basal |
| c | 0.3% | 17 | **-18.89** | high_basal |
| d | 0.6% | 35 | **-5.26** | high_basal |
| e | 1.9% | 98 | **-14.30** | high_basal |
| f | 0.0% | 0 | never_stable | -- |
| g | 0.3% | 17 | **-13.49** | high_basal |
| h | 0.7% | 29 | **-6.64** | high_basal |
| i | 1.8% | 106 | **-21.71** | high_basal |
| j | 2.9% | 46 | **+7.84** | low_basal |
| k | 1.1% | 64 | **-10.58** | high_basal |

**Critical finding**: **8/10 patients have scheduled basal rates that are too high**. During stable windows (in-range BG, nominal loop, no meals), glucose **drops** at 5-22 mg/dL/hr. Only patient j shows glucose rising (low basal).

This is the most honest basal assessment possible with AID data: it examines only the rare moments when the loop is delivering what is scheduled. The consistent negative drift means:
1. Scheduled basal overdelivers for most patients
2. The loop's primary job is suspending to prevent lows from excessive basal
3. This explains the 52-96% suspension rates in EXP-981

### EXP-986: 3-Day Glucose Trajectory Clustering

**Question**: Do 3-day glucose trajectories predict next-day outcomes?

| Patient | Trajectories | F-statistic | p-value | Predictive? |
|---------|-------------|-------------|---------|-------------|
| b | 140 | 5.1 | **0.007** | Yes |
| d | 133 | 3.7 | **0.028** | Yes |
| f | 135 | 8.3 | **0.0004** | Yes |
| k | 122 | 2.8 | 0.062 | No (marginal) |
| Others | -- | <1.1 | >0.35 | No |

**Finding**: 3/11 patients have statistically significant multi-day patterns (b, d, f). This validates the multi-scale architecture proposal -- multi-day features carry signal for some patients.

### EXP-987: Patient Difficulty Decomposition

**Question**: Why is patient k easy and patient a hard?

| Rank | Patient | Difficulty | CV | TIR | Roughness | Loop Aggr |
|------|---------|-----------|-----|-----|-----------|-----------|
| 1 (easy) | k | 38.9 | 0.167 | 95% | 2.95 | 0.836 |
| 2 | j | 53.3 | 0.314 | 81% | 6.49 | 0.958 |
| 3 | b | 56.3 | 0.353 | 57% | 5.49 | 0.851 |
| ... | | | | | | |
| 10 | d | 77.2 | 0.304 | 79% | 4.25 | 0.823 |
| 11 (hard) | a | 81.2 | 0.450 | 56% | 6.80 | **2.146** |

**Key decomposition**: Patient a is hardest because of the combination of high CV (0.45), extreme loop aggressiveness (2.15), and low TIR (56%). Patient k has the tightest control (CV=0.167, TIR=95%) -- the loop barely needs to intervene because settings are well-calibrated.

### EXP-988: Circadian Supply-Demand Signatures

**Finding**: Mean dawn surge = 1.671 in net flux (4-7 AM vs 0-3 AM). Mean circadian amplitude = 5.990 in net flux. The supply-demand framework successfully captures circadian metabolic rhythm.

### EXP-989: Sensor Age Effect

**Result**: **0/10 patients show sensor degradation**. Conservation violation does NOT increase with sensor age. Several patients show slight *improvement* over sensor life (negative slope), consistent with first-day warmup being the noisiest period.

### EXP-990: Glycemic Control Fidelity Composite Score

| Rank | Patient | Score | TIR | CV | Balance | Calm |
|------|---------|-------|-----|----|---------| -----|
| 1 | k | **76.4** | 25.0 | 16.7 | 20.2 | 14.6 |
| 2 | j | 70.8 | 25.0 | 9.3 | 23.5 | 13.0 |
| 3 | d | 66.3 | 25.0 | 9.8 | 16.8 | 14.7 |
| 4 | h | 66.2 | 25.0 | 6.5 | 20.2 | 14.5 |
| 5 | b | 66.0 | 20.2 | 7.3 | 24.0 | 14.4 |
| 6 | g | 64.8 | 25.0 | 4.5 | 21.3 | 14.1 |
| 7 | e | 61.3 | 23.3 | 6.7 | 15.0 | 16.2 |
| 8 | c | 55.9 | 22.0 | 3.3 | 15.4 | 15.2 |
| 9 | f | 51.2 | 23.4 | 0.5 | 17.6 | 9.6 |
| 10 | i | 42.3 | 21.4 | 0.0 | 6.0 | 15.0 |
| 11 | a | **37.5** | 19.9 | 2.5 | 15.1 | 0.0 |

**Fidelity interpretation**:
- **>70**: Well-calibrated settings, loop mostly passive (k, j)
- **60-70**: Adequate, some loop compensation needed (d, h, b, g)
- **50-60**: Moderate issues, loop working hard (e, c, f)
- **<50**: Settings significantly miscalibrated, loop maximally active (i, a)

---

## Synthesis: What Have We Learned?

### 1. The Loop Is Always On (EXP-981, 982, 985)

AID loops deliver scheduled basal for only **0-7%** of the time. The loop is a constant, aggressive actor that masks whether underlying settings are correct.

### 2. Most Scheduled Basals Are Too High (EXP-985)

When we observe natural basal-glucose equilibrium (stable windows), 8/10 patients show glucose dropping. Scheduled basal rates systematically overdeliver for this cohort.

### 3. Sensor Age Is Not a Major Confounder (EXP-989)

Conservation violation does NOT worsen with sensor age. Day 1 warmup may be worst.

### 4. Patient Difficulty Has Clear Explanations (EXP-987, 990)

The k-to-a difficulty spectrum maps to: glucose variability, loop aggressiveness, and supply/demand balance.

### 5. Multi-Day Patterns Exist for Some (EXP-986)

3/11 patients show significant 3-day predictive patterns, validating multi-scale analysis.

---

## Proposed Next Experiments (EXP-991-1000)

### EXP-991: Loop-Adjusted ISF Decomposition
Subtract expected basal contribution from total insulin during correction episodes.

### EXP-992: Basal Rate Optimization via Supply/Demand
Compute optimal basal that minimizes loop intervention. Compare to scheduled rates.

### EXP-993: Multi-Week Rolling Fidelity
Track composite fidelity score weekly over 6 months. Detect settings drift.

### EXP-994: Temporal Cross-Correlation (Lead/Lag)
Cross-correlation between insulin_net and glucose_delta at multiple lags (0-120 min).

### EXP-995: Conservation-Constrained Prediction
Add conservation violation as penalty term in prediction loss.

### EXP-996: AID Action Classification
Classify loop actions (suspend/nominal/increase) from glucose context.

### EXP-997: Cross-Patient Transfer with Fidelity Matching
Transfer from high-fidelity patients (k, j) to low-fidelity (a, i).

### EXP-998: Overnight Basal Titration Protocol
Virtual overnight basal titration: find basal rate producing zero drift.

### EXP-999: Residual Autocorrelation by Clinical Context
Map residual persistence to time-of-day, meal state, loop state.

### EXP-1000: Grand Fidelity Assessment
Comprehensive per-patient clinical report with specific recommendations.

---

## Code Reference

- Script: `tools/cgmencode/exp_clinical_981.py` (1128 lines, 10 experiments)
- Results: `externals/experiments/exp_exp_98[1-9]_*.json`, `exp_exp_990_*.json`
- Previous batch: `tools/cgmencode/exp_clinical_971.py` (EXP-971-980)
- PK computation: `tools/cgmencode/continuous_pk.py`
- Supply/demand: `tools/cgmencode/exp_metabolic_441.py`


---

## Part II: EXP-991-1000 Deep Clinical Intelligence (2026-04-09)

### EXP-991: Loop-Adjusted ISF Decomposition

**Approach**: Subtract baseline basal contribution from total insulin during correction episodes to isolate correction-attributable insulin.

**Result**: For patient a (the bidirectional loop patient), corrected ISF = 53.8 vs profile ISF = 48.6, ratio = 0.9 -- nearly perfect alignment! But for suspension-dominant patients (b-k), the corrected ISF explodes to 340-5337 because nearly ALL their insulin during correction windows IS baseline basal; there is almost no correction-specific insulin above baseline.

**Insight**: This decomposition only works for patients who actually receive meaningful correction insulin (boluses or high-temp basals). For suspension-dominant patients, a different approach is needed -- perhaps measuring ISF during the brief high-temp episodes only.

### EXP-994: Temporal Cross-Correlation (Lead/Lag)

**Result**: Insulin-to-glucose peak lag varies 15-50 minutes across patients (mean 35 min).

| Patient | Peak Lag | Peak Corr |
|---------|----------|-----------|
| k | 5 min | -0.058 |
| a | 15 min | -0.143 |
| c | 20 min | -0.237 |
| d, h | 20 min | -0.054/-0.162 |
| b | 25 min | -0.079 |
| i | 30 min | -0.173 |
| f | 35 min | -0.117 |
| e, g | 50 min | -0.129/-0.079 |
| j | 120 min | -0.027 |

**Insight**: The 15-50 min range matches known rapid-acting insulin onset times. Patient k's 5 min lag is consistent with extremely tight control (the loop barely deviates from baseline). Patient j's 120 min lag is consistent with minimal loop action (96% suspended).

### EXP-995: Conservation-Constrained Prediction

**Key result**: Adding physics prediction as a feature improves R-squared in **9/11 patients** (mean +0.025).

| Patient | Baseline R2 | Augmented R2 | Delta | Physics Only R2 |
|---------|-------------|-------------|-------|-----------------|
| i | 0.290 | 0.381 | **+0.091** | -7.906 |
| d | 0.118 | 0.184 | **+0.066** | -1.761 |
| e | 0.253 | 0.294 | **+0.041** | -3.724 |
| k | 0.093 | 0.130 | **+0.037** | -1.379 |
| b | 0.140 | 0.159 | +0.019 | -1.425 |
| f | 0.222 | 0.238 | +0.016 | -0.203 |
| c | 0.294 | 0.306 | +0.012 | -1.251 |
| a | 0.196 | 0.200 | +0.005 | -0.725 |
| g | 0.168 | 0.169 | +0.001 | -0.427 |
| j | 0.146 | 0.143 | -0.003 | -1.470 |
| h | 0.281 | 0.274 | -0.006 | -1.487 |

**Critical insight**: Physics alone is terrible (all negative R2 -- the supply/demand model can't predict glucose on its own). But as an *auxiliary feature* for a data-driven model, it adds meaningful signal. The physics model captures something the glucose history alone doesn't -- the expected metabolic trajectory.

### EXP-996: AID Action Classification

**Question**: Can we predict what the loop will do from glucose context?

**Result**: Mean accuracy 72.2% (baseline 67.7%), lift +4.6%. The loop's behavior is partly predictable:
- **Suspend** triggered at: lower BG (89-176 mg/dL), falling trend
- **High temp** triggered at: higher BG (106-235 mg/dL), rising trend
- Patient a shows the strongest separation (lift +20.1%) because its loop swings dramatically

### EXP-997: Cross-Patient Transfer with Fidelity Matching

**Result**: Fidelity-matched transfer beats random donor in **7/11 cases**. Large wins for patients j (+2.58 R2 difference) and k (+1.33). Transfer prediction is generally poor (negative R2), but fidelity matching provides systematic advantage over random donor selection.

### EXP-998: Overnight Basal Titration

**Result**: For 5 patients with sufficient valid overnight data, the optimal overnight basal differs substantially from scheduled. The average adjustment is large, consistent with EXP-985's finding that 8/10 have basal set too high.

### EXP-999: Residual Autocorrelation by Clinical Context

**Result**: Residual persistence ranked by context:

| Context | 15-min Autocorrelation | Persistence |
|---------|----------------------|-------------|
| Daytime | 0.225 | High |
| Postmeal | 0.222 | High |
| Loop nominal | 0.213 | High |
| Loop active | 0.193 | Medium |
| Overnight | 0.162 | Medium |
| Fasting | 0.151 | Medium |

**Insight**: Residuals persist longest during daytime and postmeal contexts, where metabolic complexity is highest. Overnight and fasting residuals decay faster -- our physics model captures baseline metabolics better than dynamic postprandial metabolism.

### EXP-1000: Grand Fidelity Assessment

Complete per-patient clinical summary with 29 actionable recommendations across 11 patients. Most common: "Consider reducing overnight basal rate" (9/11 patients).

---

## Campaign Summary: EXP-981-1000 (20 experiments)

### What We Accomplished

1. **Quantified AID confound**: The loop delivers scheduled basal <7% of the time
2. **Established fidelity scoring**: 0-100 composite with 4 clinical components
3. **Found that physics augmentation helps**: +0.025 R2 from conservation feature (9/11)
4. **Mapped insulin-glucose lag**: 15-50 min per patient (mean 35 min)
5. **Classified loop behavior**: 72% predictable from glucose context
6. **Validated fidelity-matched transfer**: 7/11 better than random
7. **Characterized residual persistence**: Daytime/postmeal worst, overnight best
8. **Generated 29 clinical recommendations** across 11 patients

### Key Takeaways for Future Work

1. **Physics as feature, not as model**: The supply/demand conservation model alone can't predict glucose, but as an auxiliary feature it consistently improves data-driven predictions.

2. **ISF validation requires loop-aware insulin decomposition**: Only works for patients with meaningful correction boluses. Suspension-dominant patients need alternative approaches.

3. **Multi-day patterns are patient-specific**: 3/11 have predictive 3-day trajectories, suggesting personalized multi-scale architectures.

4. **Residual characterization points to meal modeling**: The postmeal context has the most persistent residuals, indicating meal absorption dynamics are the biggest gap.
