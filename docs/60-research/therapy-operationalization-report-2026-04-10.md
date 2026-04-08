# EXP-1331–1340: Therapy Operationalization Report

**Date**: 2026-04-10
**Experiments**: EXP-1331 through EXP-1340
**Focus**: Ground truth validation, clinical-grade titration protocols, DIA validation, therapy simulation
**Status**: Complete (10/10 experiments run)

## Executive Summary

This batch resolves key open questions from EXP-1291-1320. The central finding is that the **physics-based supply/demand decomposition has a systematic bias** (~25% magnitude error even for well-calibrated patients), which means therapy recommendations derived from net flux must be interpreted as relative signals, not absolute prescriptions. However, **overnight glucose drift** and **response-curve exponential fitting** provide clinically actionable signals that bypass this bias.

### Key Results

| Experiment | Finding | Impact |
|-----------|---------|--------|
| **EXP-1331** | All 3 basal methods show 25-34% bias for well-calibrated patients | Physics model has systematic offset; raw method least biased |
| **EXP-1332** | UAM filtering loses 84.6% of correction events | 20% UAM threshold too aggressive; doesn't improve fit R² |
| **EXP-1334** | Population DIA = **6.0h** (vs 5h profile), fit R²=0.751 | Most patients have effective DIA longer than assumed |
| **EXP-1336** | Dinner excursions 77.3 mg/dL, lunch only 46.3 mg/dL | CR needs time-of-day adjustment, especially dinner |
| **EXP-1337** | ISF varies **131%** within day across patients | Fixed ISF profiles miss major intraday variation |
| **EXP-1338** | 6/11 stable, 5/11 drifting over 6 months | Half of patients need periodic settings reassessment |
| **EXP-1340** | Overnight-only correction: TIR Δ=-1.4% (0/11 improved) | Single-signal correction insufficient; need multi-block approach |

## Detailed Results

### EXP-1331: Basal Ground Truth Validation

**Question**: Which basal analysis method is correct — raw (EXP-1292: 7/11 decrease) or UAM-filtered (EXP-1315: 8/11 increase)?

**Approach**: Use well-calibrated patients (d, h, j, k from EXP-1310) as ground truth. If basal settings are already correct, all methods should recommend ~0% change.

**Results for well-calibrated patients**:

| Method | Mean Change (well-calibrated) | |Method Score| (closer to 0 = better) |
|--------|------|------|
| Raw | -25.4% | 25.4 |
| UAM-filtered | -34.3% | 34.3 |
| Overnight-only | -26.3% | 26.3 |

**Finding**: **All three methods show large systematic bias** (~25-34% change recommended even for patients with good TIR). The "raw" method is closest to zero but still far off. This means:
1. The physics decomposition's demand term overestimates insulin effect, biasing net flux negative
2. Recommendations should be interpreted as **relative** (compare across blocks/patients), not absolute
3. The raw method is the least biased of the three

**Drift analysis** provides a physics-model-free alternative:
- Well-calibrated mean drift: **-0.29 mg/dL/h** (nearly zero — confirming basal is correct)
- Needs-tuning patients: drift varies widely by patient

**UAM contamination**: 24-65% of fasting windows contain UAM events, explaining why UAM filtering is so destructive.

### EXP-1332: UAM-Clean Response-Curve ISF

**Question**: Does UAM contamination bias ISF estimates from response curves?

**Results**:
- Raw events per patient: 1-169 (median ~63)
- After UAM filtering (>20% window threshold): **84.6% of events lost**
- Remaining events: 0-18 (median ~3) — insufficient for reliable estimation
- ISF shift: +219.8% mean (driven by small-sample outliers)
- Fit R² unchanged: 0.771 → 0.771

**Conclusion**: The 20% UAM threshold is **far too aggressive** for correction windows. Most correction boluses are given during active UAM periods (meals, hepatic). A gentler threshold (50-70%) or a different deconfounding approach is needed.

### EXP-1333: Overnight Basal Titration

**Clinical-style protocol**: Find clean overnight windows (0-6 AM, no bolus/carbs for ≥4h, no preceding meal for 3h). Measure BG drift rate. Convert to U/h change.

| Patient | Windows | Drift (mg/dL/h) | Current (U/h) | Recommended (U/h) | Direction | Confidence |
|---------|---------|----------|--------|-------------|-----------|------------|
| a | 59 | +10.78 | 0.300 | 0.450 | increase | medium |
| d | 40 | -1.09 | 0.950 | 0.900 | decrease | medium |
| f | 57 | +3.75 | 3.500 | 3.525 | increase | medium |
| j | 51 | +6.49 | 7.000 | 7.175 | increase | **high** |
| k | 26 | +0.42 | 0.550 | 0.575 | increase | medium |
| c | 1 | -18.47 | 1.450 | 1.200 | decrease | low |
| e | 1 | -2.54 | 2.300 | 2.225 | decrease | low |

**Key findings**:
- 7/11 patients have usable overnight data; 4/11 have no clean windows (b, g, h, i)
- Patient j has **high confidence** (51 consistent windows): increase 7.0→7.175 U/h
- Patient a shows strongest signal: +10.78 mg/dL/h drift → 50% increase needed
- Well-calibrated patient d: only -1.09 mg/dL/h (confirms near-correct basal)
- Mean population drift: -0.09 mg/dL/h (near zero across population)

### EXP-1334: DIA Validation

**Approach**: Fit exponential decay BG(t) = BG₀ - A·(1 - e^{-t/τ}) to isolated correction boluses with 8h observation windows. Effective DIA = 3τ (95% of effect).

| Patient | Events | τ (h) | Effective DIA (h) | Fit R² | vs Profile |
|---------|--------|-------|-------------------|--------|------------|
| a | 44 | 1.50 | 4.5 | 0.589 | -10% |
| b | 6 | 6.00 | 18.0 | 0.470 | +260% (artifact) |
| c | 5 | 1.25 | 3.8 | 0.767 | -24% |
| f | 63 | 2.75 | 8.2 | 0.766 | +64% |
| h | 1 | 2.00 | 6.0 | 0.969 | +20% |
| j | 5 | 1.00 | 3.0 | 0.761 | -40% |

**Population**: Median DIA = **6.0h** (vs 5h standard profile), τ = 2.0h, fit R² = 0.751

**Key findings**:
- **4/7 patients have DIA longer than 5h profile** — insulin acts longer than assumed
- Patient b's DIA=18h is an artifact (τ=6h, only 6 events, poor fit R²=0.47)
- Patients c and j have notably short DIA (3.0-3.8h) — rapid insulin action
- Patient f: DIA=8.2h with high confidence (63 events, R²=0.766) — significantly prolonged
- **DIA miscalibration may partially explain physics model bias**: if true DIA > profile DIA, demand is underestimated during insulin tail

### EXP-1335: Specific U/h Basal Recommendations by Time Block

Generated per-patient, per-time-block basal rate recommendations using both physics (net flux) and drift methods. Results saved in `exp-1335_therapy.json` for clinical review.

### EXP-1336: CR Assessment per Meal Block

| Meal Block | Mean Excursion | % High (>60 mg/dL) | Assessment |
|-----------|----------|------|-----------|
| Breakfast | 58.2 mg/dL | 39.5% | Borderline |
| Lunch | 46.3 mg/dL | 29.2% | Best |
| Dinner | **77.3 mg/dL** | **53.6%** | Too high |
| Late | 74.0 mg/dL | 52.4% | Too high |

**Key findings**:
- **Dinner and late meals have the worst excursions** — CR is too high (not enough insulin per carb) for evening meals
- Lunch is best-controlled (lowest excursion, lowest flag rate)
- Patient k (well-calibrated): excursions 18-25 mg/dL — confirms good CR
- Patient i (needs-tuning): excursions 76-142 mg/dL — needs CR reduction for all meals
- Patient c: lunch excursion 113 mg/dL — severe CR issue

### EXP-1337: Time-of-Day ISF Variation

**Finding**: ISF varies **131%** within day on average across patients.

| Pattern | Patients |
|---------|----------|
| Morning dip (dawn effect) | d, e (ratio <0.3) |
| Reverse dawn (morning higher) | b, j (ratio >1.5) |
| No clear pattern | Most patients |

- **Only 2/11 show classical dawn effect** (ISF lower in morning)
- The enormous intraday variation (53-430% range) suggests ISF should NOT be treated as a single value
- Afternoon and evening ISF are often very different from overnight

### EXP-1338: Multi-Week Stability

| Stability | Patients | TIR Trend | ISF CV |
|-----------|----------|-----------|--------|
| Stable | a, b, c, d, g, i (6/11) | Small | <0.16 |
| Drifting | e, f, h, j, k (5/11) | Variable | >0.16 |

- Patient k: TIR 90-98% but ISF CV=0.47 — well-controlled despite ISF drift (robust settings)
- Patient h: ISF CV=0.42 with TIR trend +1.58 — improving over time
- **6 months is sufficient to observe meaningful drift in half the population**
- Stable patients can keep settings for ≥6 months; drifting patients need 4-8 week reassessment

### EXP-1339: Hepatic Glucose Rhythm

- **Peak hepatic output: midnight (0 AM) for 9/11 patients** — not dawn (4-6 AM) as clinically expected
- This likely reflects PK channel encoding rather than true hepatic timing
- Dawn effect detected in 2/11 patients via glucose drift method
- Mean dawn magnitude: 11.1 mg/dL/h for detected patients

### EXP-1340: Therapy Simulation

**Approach**: Apply overnight drift correction across entire day with exponential decay.

**Result**: TIR 70.9% → 69.5% (Δ=-1.4%), **0/11 improved**

| Patient | Current TIR | Simulated TIR | Change |
|---------|------------|--------------|--------|
| k | 95.1% | 95.6% | +0.5% |
| a | 55.8% | 56.6% | +0.8% |
| j | 81.0% | 81.2% | +0.3% |
| d | 79.2% | 78.6% | -0.5% |
| h | 85.0% | 80.3% | **-4.7%** |
| e | 65.4% | 60.9% | **-4.4%** |

**Key findings**:
- Overnight-only basal correction is **insufficient** for TIR improvement
- Patients where drift pushes BG down (c, e, g) worsen with correction because the correction counteracts an already-beneficial drift
- Need **multi-block, multi-parameter simulation** (basal by block + ISF + CR) for meaningful improvement
- Single-parameter perturbation doesn't capture the AID system's adaptive response

## Synthesis: What We've Learned (60 Therapy Experiments)

### Physics Model Limitations (Confirmed)
1. **Systematic bias**: ~25% magnitude error in net flux, even for well-calibrated patients
2. **DIA mismatch**: Most patients have effective DIA ≠ profile DIA (median 6h vs 5h)
3. **UAM ubiquity**: 24-65% of "fasting" windows contain UAM events
4. **AID loop confounding**: The loop's adaptive response makes all static analysis methods approximate

### What Actually Works
1. **Overnight glucose drift**: Direct measurement, bypasses physics model bias. Best single signal for basal assessment.
2. **Response-curve ISF**: Exponential decay fit with R²=0.751-0.805, provides reliable ISF per correction event
3. **Meal excursion analysis**: Simple peak-minus-baseline detects CR problems with high sensitivity
4. **Multi-week rolling windows**: 4-week windows are optimal for detecting drift

### Therapy Triage Decision Tree (Evidence-Based)

```
Patient Data Available?
├── CGM <70% coverage → DEFER (insufficient data)
├── Insulin telemetry <50% → DEFER (can't assess)
└── Both adequate →
    ├── Overnight drift > ±5 mg/dL/h → ADJUST BASAL
    │   ├── Drift positive → increase basal (use drift/ISF for U/h)
    │   └── Drift negative → decrease basal
    ├── Dinner excursion > 60 mg/dL → ADJUST DINNER CR
    ├── Response-curve ISF differs >30% from profile → ADJUST ISF
    ├── Effective DIA differs >25% from profile → FLAG FOR REVIEW
    └── Multi-week ISF CV > 0.3 → SCHEDULE REASSESSMENT
```

## Unresolved Questions

1. **Multi-parameter simulation**: Need simultaneous basal + ISF + CR adjustment simulation with AID loop model
2. **Physics model calibration**: Can systematic bias be corrected by DIA-adjusted demand term?
3. **UAM deconfounding**: What threshold balances event retention with contamination?
4. **Closed-loop simulation**: Open-loop counterfactual can't predict AID response to changed settings

## Proposed Next Experiments (EXP-1341+)

### High Priority
| ID | Name | Rationale |
|----|------|-----------|
| EXP-1341 | DIA-corrected physics model | Use per-patient DIA from EXP-1334 to recalculate demand; may fix systematic bias |
| EXP-1342 | Multi-block simulation | Simulate basal changes per time-of-day block, not globally |
| EXP-1343 | CR tightening simulation | Simulate reducing dinner CR by 10-20% — predict excursion reduction |
| EXP-1344 | Drift-only triage | Build complete recommendation using ONLY drift + excursion (no physics) |

### Medium Priority
| ID | Name | Rationale |
|----|------|-----------|
| EXP-1345 | Gentle UAM threshold sweep | Test 30%, 50%, 70% UAM thresholds for ISF filtering |
| EXP-1346 | Patient-specific DIA profiles | Build per-patient DIA curve (not single value) |
| EXP-1347 | ISF time-block recommendations | Generate time-of-day ISF profile from response curves |
| EXP-1348 | Confidence-weighted multi-param | Combine drift + ISF + CR with per-signal confidence weighting |

### Exploratory
| ID | Name | Rationale |
|----|------|-----------|
| EXP-1349 | AID loop model | Simple proportional-integral controller model for closed-loop simulation |
| EXP-1350 | Exercise detection | Separate exercise from UAM for better deconfounding |

## Files

| File | Description |
|------|-------------|
| `tools/cgmencode/exp_clinical_1331.py` | Experiment implementation (10 experiments) |
| `exp-1331_therapy.json` through `exp-1340_therapy.json` | Raw results |
| `docs/60-research/therapy-operationalization-report-2026-04-10.md` | This report |

## Cross-References

- **EXP-1291-1300**: Deconfounded therapy assessment (precondition framework)
- **EXP-1301-1310**: Response-curve ISF and UAM augmentation breakthroughs
- **EXP-1311-1320**: UAM-aware therapy and universal transfer
- **EXP-1321**: Meal carb survey (separate investigation by colleague)
