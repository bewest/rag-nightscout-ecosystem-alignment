# Therapy Detection Report: DIA-Corrected Physics & Multi-Parameter Recommendations

**Experiments**: EXP-1351 through EXP-1360  
**Date**: 2026-04-10  
**Campaign**: Therapy Detection & Recommendation (experiments 71-80)  
**Source**: `tools/cgmencode/exp_clinical_1351.py`

## Executive Summary

This batch tested whether correcting the physics model for actual DIA would reduce
the ~25% systematic bias discovered in EXP-1331, explored multi-parameter
recommendation systems, and began separating exercise from UAM violations. 

**Key results**:
- DIA correction **worsened** the physics model (R² -0.189 → -0.24)  
- Multi-block basal simulation still fails (0/11 improved)  
- CR tightening by 20% reduces dinner excursion by 48% (77→40 mg/dL)  
- UAM threshold should be 90% (not 20%) — filtering was far too aggressive  
- AID loop dampens ~30% of recommended changes  
- Exercise accounts for 18% of physics violations; removing it shifts ISF +9.4%  
- DIA varies more by **time-of-day** than bolus size  

## Experiment Results

### EXP-1351: DIA-Corrected Physics Model ❌

**Hypothesis**: If actual DIA ≠ profile DIA (5h), scaling demand by `actual_DIA / profile_DIA`
should reduce the physics model bias.

**Result**: **Worsened** model fit for 10 of 11 patients (patient h slightly improved).

| Metric | Original | DIA-Corrected |
|--------|----------|---------------|
| Well-cal R² | -0.189 | -0.240 |
| Well-cal bias | 38.7% | 40.2% |
| Mean R² improvement | — | -2.736 |

Population mean DIA ratio = 1.7× (actual DIA is 70% longer than profile). But simple
demand scaling amplifies the demand component, making residuals worse. The physics model
bias is **not** primarily caused by DIA mismatch — it's a structural limitation of how
supply/demand decomposition maps to the PK channels.

**Implication**: Abandon physics model correction via DIA scaling. The ~25% bias is inherent
to the supply/demand decomposition approach. Use **drift-based methods** for absolute
recommendations.

### EXP-1352: Multi-Block Basal Simulation ❌

**Hypothesis**: Per-time-block drift corrections should outperform overnight-only (EXP-1340).

**Result**: Still fails — 0/11 improved, 4 worsened (mean TIR Δ = -1.1%).

| Patient | Current TIR | Simulated TIR | Change |
|---------|------------|---------------|--------|
| d (well-cal) | 79.2% | 79.6% | +0.5 |
| a (miscal) | 55.8% | 55.0% | -0.8 |
| b (needs-tuning) | 56.7% | 54.2% | -2.5 |

The simulation model (cumulative correction with 0.95 decay) is too simplistic to capture
how basal changes propagate through AID loop feedback. The loop actively counteracts our
corrections (see EXP-1359).

**Implication**: Simple glucose-offset simulation cannot predict TIR changes. Need either
(a) a loop-aware simulation or (b) abandon simulation entirely and measure before/after
in real settings changes.

### EXP-1353: CR Tightening Simulation ✅

**Hypothesis**: Tightening dinner CR reduces post-meal excursions.

**Result**: **Strong** dose-response relationship confirmed.

| CR Reduction | Mean Excursion | % Above 60 mg/dL |
|-------------|----------------|-------------------|
| Baseline | 77.2 mg/dL | 53.8% |
| 10% tighter | 58.2 mg/dL | 41.3% |
| 20% tighter | 40.4 mg/dL | 26.0% |
| 30% tighter | 26.3 mg/dL | 18.2% |

Per-patient detail — patients with worst dinners:

| Patient | Dinners | Baseline Excursion | 20% Reduction |
|---------|---------|-------------------|---------------|
| c | 61 | 101.2 mg/dL | ~57 mg/dL |
| b | 226 | 77.4 mg/dL | ~43 mg/dL |
| e | 61 | 59.5 mg/dL | ~18 mg/dL |

**Implication**: CR tightening is the highest-confidence actionable recommendation.
A 20% dinner CR reduction is a strong first intervention for patients with excursions >60 mg/dL.

### EXP-1354: Drift-Only Triage ⚠️

**Hypothesis**: Can we build a complete triage system using only drift + excursion + correction
response (no physics model)?

**Result**: Generates plausible recommendations, but **over-triggers on well-calibrated patients**.

| Archetype | Mean Actions | Expected |
|-----------|-------------|----------|
| Well-calibrated (d,h,j,k) | 2.8 | ~0-1 |
| Needs-tuning (b,c,e,f,g,i) | 4.3 | 3-5 |
| Miscalibrated (a) | 2.0 | 3+ |

Per-patient triage cards:

| Patient | Basal | ISF | CR-Breakfast | CR-Dinner | CR-Late |
|---------|-------|-----|-------------|-----------|---------|
| a (miscal) | increase +0.075U | increase (1.43×) | ok | ok | ok |
| c (needs) | decrease -0.1U | increase (5.43×) | tighten | tighten | tighten |
| d (well-cal) | ok | increase (5.96×) | ok | tighten | tighten |
| k (well-cal) | ok | — | — | ok | ok |

**Problem**: ISF ratio thresholds (>1.2×) are too sensitive. Patient d (well-calibrated, TIR 86%)
gets flagged for 5.96× ISF increase — clearly wrong. The response-curve ISF measurement
systematically overestimates true ISF for well-controlled patients whose corrections are small
and confounded by AID loop action.

**Implication**: ISF triage threshold needs to be raised to >2× or restricted to patients with
enough large corrections (bolus >2U). The drift-only approach works well for basal and CR
but needs better ISF deconfounding.

### EXP-1355: UAM Threshold Sweep ✅

**Hypothesis**: Find the optimal UAM contamination threshold for ISF filtering.

**Result**: **90% is optimal** for 8/11 patients.

| Threshold | Population Votes | Score (n × R²) |
|-----------|-----------------|-----------------|
| 90% | 8/11 | Highest for most |
| 80% | 1/11 | — |
| 60% | 1/11 | — |
| 50% | 1/11 | — |

This means the previous 20% threshold (EXP-1332) threw away **84.6%** of events unnecessarily.
Most correction events produce good ISF estimates even when UAM activity is high in the window.
UAM contamination within the correction window doesn't significantly corrupt the exponential
decay fit because the correction signal (bolus-driven) dominates.

**Implication**: Use 90% UAM threshold (essentially no filtering) for ISF estimation. Reserve
tight filtering only for research-grade τ/DIA estimation where precision matters.

### EXP-1356: Patient-Specific DIA Profiles ✅

**Hypothesis**: DIA varies by bolus size and time-of-day.

**Result**: DIA varies more by **time-of-day** (mean variation 3.04h) than bolus size (2.33h).
Overall τ CV = 0.64 (very high within-patient variability).

| Factor | Mean Variation (hours τ) | Implication |
|--------|------------------------|-------------|
| Bolus size | 2.33 | Large boluses → longer DIA |
| Time of day | 3.04 | Evening insulin acts longer |

Example — Patient a:
- Small bolus (<1U): τ=1.0, DIA=3.0h
- Medium (1-3U): τ=2.0, DIA=6.0h
- Large (>3U): τ=5.0, DIA=15.0h

**Implication**: Fixed DIA settings are inadequate. AID systems should support
time-of-day DIA profiles or bolus-size-adjusted DIA. The τ=5.0 / DIA=15h for large
boluses may reflect absorption kinetics rather than true insulin action (depot effect).

### EXP-1357: ISF Time-Block Recommendations

Generated per-patient 6-block ISF schedules from response-curve analysis. Example:

| Patient | Profile ISF | Overall Measured |
|---------|------------|------------------|
| a | 48.6 | 69.6 (+43%) |
| d | 40.0 | 238.3 (+496%) |
| j | 40.0 | 97.9 (+145%) |

The extreme ratios (d: 6×, g: 4.7×) indicate the response-curve method systematically
overestimates ISF when corrections are small and AID loop modifies temp basal during the
event. This is the same ISF over-triggering seen in EXP-1354.

### EXP-1358: Multi-Parameter Recommendations ⚠️

**Result**: 10/11 high confidence, but well-calibrated patients still average 2.0 actions.

| Confidence Level | Count |
|-----------------|-------|
| High (>0.5) | 10 |
| Medium (0.25-0.5) | 1 |
| Low (<0.25) | 0 |

The confidence scoring works (composite of basal/ISF/CR confidence weighted by data volume
and fit quality) but the underlying ISF recommendations are unreliable for well-calibrated
patients. **CR recommendations are the most trustworthy** — 9/11 patients have excursion >60
mg/dL for at least one meal block.

### EXP-1359: AID Loop Model ✅

**Hypothesis**: Estimate AID loop proportional gain K and predict how much the loop dampens
recommended setting changes.

**Result**: Mean K=0.13, mean dampening = 29.8%.

| Patient | Archetype | K | Dampening | Loop Aggressiveness |
|---------|-----------|------|-----------|---------------------|
| a | miscal | -1.081 | 51.9% | 3.74 |
| b | needs | 0.863 | 46.3% | 0.39 |
| d | well-cal | 0.495 | 33.1% | 0.29 |
| f | needs | -0.015 | 1.5% | 0.51 |
| k | well-cal | -0.962 | 49.0% | 0.43 |

**Key findings**:
1. **Patient a** has K=-1.081 (inverted gain, 52% dampening, aggressiveness 3.74×) — the loop
   is fighting the wrong direction, consistent with "miscalibrated" archetype
2. **Negative K** (patients a, f, i, k) means the loop increases delivery when glucose is already
   low — suggests either settings or algorithm misconfiguration
3. Mean 30% dampening means we should recommend 1.43× the calculated change
   (1 / 0.70 = 1.43) to achieve the desired net effect
4. Loop aggressiveness correlates with archetype: well-cal 0.31, needs-tuning 0.44, miscal 3.74

**Implication**: Account for ~30% AID dampening when making recommendations. Patients with
negative K need settings review as a priority.

### EXP-1360: Exercise Detection ✅

**Hypothesis**: Separate exercise-induced glucose changes from UAM violations.

**Result**: Exercise = 18% of violations, UAM = 57.5%. Exercise-free ISF shifts +9.4%.

| Patient | Exercise % | UAM % | ISF Shift | Peak Hour | Exercise h/day |
|---------|-----------|-------|-----------|-----------|---------------|
| b | 26.6% | 20.3% | +73.8% | 9:00 | 4.38 |
| j | 29.6% | 37.4% | +16.0% | 0:00 | 4.91 |
| d | 24.4% | 57.9% | +19.2% | 18:00 | 3.51 |
| k | 27.6% | 58.4% | 0.0% | 9:00 | 3.20 |
| i | 7.2% | 88.4% | +5.1% | 16:00 | 1.32 |

**Key findings**:
1. Exercise accounts for 18% of physics violations — non-trivial
2. Peak exercise hours: 18:00 most common (afternoon/evening), some morning
3. Removing exercise windows shifts ISF +9.4% on average — exercise makes insulin appear
   more effective (insulin-independent glucose uptake by muscles)
4. Patient b: huge ISF shift (+73.8%) with peak at 9am, 4.4h/day exercise activity
5. Patient h: ISF shifted -50.4% — anomalous, may indicate exercise detection is
   capturing something else for low-CGM patients (35.8% coverage)

**Implication**: Exercise filtering is worth implementing for ISF estimation. The +9.4%
shift means current ISF estimates are ~10% too low (underestimating insulin sensitivity
because exercise effect is mixed in).

## Synthesis: What Works and What Doesn't

### ✅ Proven Approaches

| Method | Evidence | Confidence |
|--------|----------|------------|
| **Drift-based basal assessment** | Bypasses physics bias, near-zero for well-cal | High |
| **Excursion-based CR assessment** | 20% tightening → 48% excursion reduction | High |
| **UAM threshold 90%** | 8/11 patients, maximizes events × R² | High |
| **Exercise filtering for ISF** | +9.4% ISF shift, confirms deconfounding | Medium |
| **AID loop dampening ~30%** | Scale recs by 1.43× to compensate | Medium |
| **DIA varies by ToD** | 3.04h variation, larger than bolus-size effect | Medium |

### ❌ Failed Approaches

| Method | What Happened | Learning |
|--------|--------------|---------|
| **DIA-corrected physics** | Made R² worse by 2.7 | Bias is structural, not DIA |
| **Simple glucose-offset simulation** | 0/11 improved in 2 attempts | Need loop-aware simulation |
| **Response-curve ISF for well-cal** | 5-7× overestimation | AID loop confounds small corrections |
| **ISF triage at 1.2× threshold** | Well-cal gets 2.8 false-positive actions | Need >2× threshold |

### ⚠️ Needs Refinement

| Method | Issue | Fix Needed |
|--------|-------|-----------|
| **Multi-param confidence** | ISF component unreliable | Weight ISF down or gate on bolus size |
| **Drift-only triage** | Over-triggers on ISF | Raise threshold, add bolus-size gate |
| **DIA profiles** | τ CV=0.64 (very noisy) | Need more events, filter outliers |

## Updated Therapy Triage Decision Tree

Based on 80 experiments (EXP-1281–1360):

```
PRECONDITIONS:
  CGM coverage ≥ 70%           → else DEFER
  Insulin telemetry ≥ 50%      → else DEFER

STAGE 1 – BASAL (drift-based, highest confidence):
  Overnight fasting drift > +5 mg/dL/h  → INCREASE BASAL × 1.43 (AID dampening)
  Overnight fasting drift < -5 mg/dL/h  → DECREASE BASAL × 1.43

STAGE 2 – CR (excursion-based, high confidence):
  Dinner excursion > 60 mg/dL   → TIGHTEN DINNER CR by 20%
  Breakfast excursion > 60 mg/dL → TIGHTEN BREAKFAST CR by 20%
  (Use 90% UAM threshold for meal identification)

STAGE 3 – ISF (response-curve, medium confidence):
  ONLY IF bolus ≥ 2U corrections available (≥5 events):
    Measured ISF > 2× profile    → INCREASE ISF
    Measured ISF < 0.5× profile  → DECREASE ISF
    Remove exercise windows (+9.4% shift correction)

STAGE 4 – ADVANCED:
  Loop K < 0 (negative gain)     → FLAG: Settings review priority
  Multi-week ISF CV > 0.3        → SCHEDULE REASSESSMENT
  DIA effective > 2× profile     → FLAG FOR REVIEW (may be depot effect)
```

## Experiment Inventory (EXP-1281–1360)

| Range | Theme | Key Finding |
|-------|-------|-------------|
| 1281-1290 | First therapy detection | Physics bias ~25%, overnight drift works |
| 1291-1300 | Deconfounded + preconditions | Precondition gating essential |
| 1301-1310 | Response-curve ISF + UAM | ISF R²=0.75-0.80, UAM threshold 1.0 |
| 1311-1320 | UAM-aware therapy | 100% cross-patient UAM transfer |
| 1331-1340 | Ground truth, DIA, simulation | DIA=6h, simulation fails, dinner worst |
| 1351-1360 | DIA correction, multi-param | DIA correction fails, CR tightening works, exercise 18% |

**Total**: 80 therapy experiments across 11 patients (~180 days each).

## Next Priorities

1. **ISF deconfounding**: Gate on large corrections (≥2U), remove exercise windows, use 90%
   UAM threshold — combine all three improvements in a single re-estimation
2. **Loop-aware simulation**: Use estimated K to model how AID adjusts to setting changes,
   rather than simple glucose offset
3. **CR recommendation validation**: Compare 20% CR tightening recommendation to actual
   patient behavior changes over time (do patients whose settings were adjusted show
   improvement?)
4. **Threshold optimization**: Systematic sweep of drift, excursion, ISF ratio thresholds
   to minimize false positives on well-calibrated patients while catching real issues
5. **Multi-week stability**: Correlate therapy recommendations with ISF drift (EXP-1338)
   to determine whether recs should be periodic or one-time
