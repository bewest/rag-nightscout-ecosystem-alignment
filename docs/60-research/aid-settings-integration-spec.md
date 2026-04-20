# AID Settings Pipeline: Integration Specification

## Overview

This specification translates findings from EXP-2719b through EXP-2754 into
actionable recommendations for AID system authors (Loop, Trio, AAPS) and users.

**Pipeline validation**: 5/5 temporal cross-validation (EXP-2753). Settings
derived from 70% of data improve predictions on unseen 30% with median 59%
MAE reduction. Zero patients harmed (>20% worse).

---

## 1. ISF Settings Assessment

### Finding
Profile ISF is miscalibrated in 96% of patients (EXP-2719b). The direction
depends on controller: Loop/Trio tend to have ISF set too aggressively (need
increase), while OpenAPS patients vary. Controller type explains 47.5% of
correction variance (EXP-2754).

### Method: Waterfall Residual Analysis

```
For each correction episode (BG ≥ 180, bolus > 0):
  1. Compute actual BG drop over 2h
  2. Compute expected BG drop: excess_insulin × profile_ISF
  3. Correction factor = median(actual / expected) across episodes
  4. Corrected ISF = profile_ISF × correction_factor
```

### Implementation Notes
- Requires ≥20 correction episodes (typically 2-4 weeks of data)
- Clip correction factor to [0.2, 5.0] for safety
- Excess insulin = bolus + SMB + (net_basal - scheduled_basal) × Δt
- Use 2h horizon (24 steps × 5min) — validated as optimal (EXP-2719)

### Expected Impact
- 68% of patients improve with corrected ISF
- Median MAE improvement: 28% on correction episodes
- Temporally stable: train/test correlation r=0.488

---

## 2. CR Settings Assessment

### Finding
Bilateral deconfounding reveals CR after subtracting controller compensation.
Raw post-meal glucose underestimates true carb impact by ~30% because the
controller suspends basal during meals (EXP-2744).

### Method: Bilateral Meal Deconfounding

```
For each meal episode (carbs ≥ 10g):
  1. Compute raw BG rise (peak - baseline over 2h)
  2. Compute insulin effect: total_insulin × ISF (use corrected ISF!)
  3. Carb-attributable rise = raw_rise + insulin_effect
  4. Effective CR = carbs / (carb_rise / ISF)
  5. Compensated CR = median(effective_CR) across episodes
```

### Implementation Notes
- MUST use corrected ISF from step 1 (not profile ISF)
- Clip effective CR to [1, 50] per episode
- Requires ≥20 meal episodes
- Controller suspension is automatic — no need to detect it manually

### Expected Impact
- 73% of patients improve with compensated CR
- Population median CR ratio: 1.23 (increase profile CR by ~23%)

---

## 3. Meal-Size-Dependent CR (Optional)

### Finding
Large meals produce only 60% of per-gram glucose impact compared to small
meals (EXP-2750). This is universal across all 22 patients. The mechanism
is gastric emptying: larger meals empty more slowly, spreading absorption.

### Method: Size-Stratified CR

```
For each patient:
  1. Split meals at median carbs threshold
  2. Compute separate CR for small and large meals
  3. Small CR: use bilateral deconfounding on small meals only
  4. Large CR: use bilateral deconfounding on large meals only
  5. Apply safety clamp: large_CR ≤ 2.5 × small_CR
```

### Population Medians
| Meal Size | Peak Time | Excursion Width | Peak per Gram |
|-----------|-----------|-----------------|---------------|
| Small | 92 min | 62 min | 2.99 mg/dL/g |
| Large | 108 min | 80 min | 1.81 mg/dL/g |

### Implementation Notes
- Offer as OPTIONAL enhancement for users with variable meal sizes
- Benefits 41% of patients (those with large/small CR ratio >1.5)
- The threshold (small vs large) should be patient's median meal size
- If a user consistently eats similar-sized meals, flat CR is sufficient

### Implication for AID Authors
Current linear carb absorption models in all AID systems assume proportional
absorption. A meal-size-dependent absorption curve would better match reality:
- Small meals: standard absorption rate, standard duration
- Large meals: reduce peak absorption rate, extend duration

---

## 4. Basal Rate Assessment

### Finding
Do NOT recommend basal rate changes (EXP-2745). Fasting glucose drift
reflects the AID controller's temp basal adjustments, not patient
physiology. Adjusting scheduled basal improves only 1/22 patients.

### Rationale
The AID controller already optimizes effective basal delivery in real time.
Changing the scheduled rate just changes the baseline the controller works
from, with no meaningful effect on glucose outcomes.

---

## 5. EGP Personalization

### Finding
Endogenous glucose production varies between patients (EXP-2742). Adding
per-patient metabolic baseline to the simulation model improves 55% of
patients (11/22 with sufficient data).

### Implementation Notes
- EGP is modeled via Hill equation in `production/metabolic_engine.py`
- Per-patient EGP requires glycemic variability analysis
- Only useful for patients with sufficient fasting data
- Does NOT require user-facing UI — internal model parameter

---

## 6. Pipeline Completeness

### Confirmed Complete (EXP-2751, 2752)
- Residual autocorrelation is 40 minutes (controller dynamics)
- No carb absorption model beats linear
- No medium-term (1-6h) or long-term (6-24h) signal in residuals
- Pipeline extracts all available signal from observational AID data

### What Cannot Be Improved
- Basal rate optimization (controller's job)
- Circadian adjustments (AID already compensates)
- Complex absorption curves (linear is optimal)
- Multi-day factors (no signal in residuals)

---

## 7. Data Requirements

### Minimum Data
| Component | Minimum Episodes | Typical Duration |
|-----------|-----------------|------------------|
| ISF correction | 20 corrections | 2-4 weeks |
| CR correction | 20 meals | 1-2 weeks |
| Size-CR | 20 small + 20 large | 3-4 weeks |
| EGP | 10 fasting periods | 2+ weeks |

### Required Nightscout Fields
| Field | Collection | Used For |
|-------|------------|----------|
| `glucose` / `sgv` | entries | All analyses |
| `bolus`, `insulin` | treatments | ISF, CR extraction |
| `carbs` | treatments | CR extraction |
| `iob` | devicestatus | Insulin accounting |
| `basal` / `temp_basal` | treatments | Excess insulin calculation |
| `profile` | profile | Scheduled ISF, CR, basal |

---

## 8. Safety Constraints

1. **ISF correction clamp**: [0.2, 5.0] × profile value
2. **CR correction clamp**: [1, 50] absolute
3. **Large CR clamp**: ≤ 2.5 × small CR
4. **Temporal validation**: Require cross-validated improvement before recommending
5. **No basal changes**: Controller compensates
6. **Minimum data**: Require ≥20 episodes per setting type
7. **Direction consistency**: Population-mean correction should agree with per-patient direction

---

## 9. Controller-Specific Notes

### Loop
- ISF correction median: ×1.36 (increase ISF — less aggressive corrections)
- CR correction median: ×1.28 (increase CR — reduce meal bolus)
- Lowest test improvement (34%) — may already be well-tuned
- Small sample (n=2) — interpret cautiously

### Trio / OpenAPS (SMB-capable)
- ISF correction median: ×1.26 (increase ISF)
- CR correction median: ×1.21 (increase CR)
- Highest test improvement (60%) — most to gain
- SMB dosing is included in excess insulin calculation

### OpenAPS (oref0)
- ISF correction median: ×0.87 (DECREASE ISF — opposite direction!)
- CR correction median: ×2.93 (large increase in CR)
- Test improvement: 0% — settings may already be near-optimal
- Or: different controller dynamics require different extraction method

---

## 10. Experiment Index

| EXP | Title | Pass | Key Finding |
|-----|-------|------|-------------|
| 2719b | ISF from residuals | 5/5 | 96% need correction |
| 2741 | Bilateral CR | 4/5 | 73% improve |
| 2742 | EGP personalization | 3/5 | 55% improve |
| 2743 | Integrated pipeline | 3/5 | 64% beat profile |
| 2744 | CR compensation | 3/5 | ~30% controller suspension |
| 2745 | Basal validation | 3/5 | Don't adjust basal |
| 2747 | Dose-dependent CR | 4/5 | 2× large/small ratio |
| 2749 | Enhanced pipeline | 3/5 | 77% beat profile |
| 2750 | Absorption dynamics | 3/5 | Universal nonlinear |
| 2751 | Autocorrelation | 2/5 | 40min, controller |
| 2752 | Absorption curves | 0/5 | Linear optimal |
| 2753 | Temporal crossval | 5/5 | 59% test improvement |
| 2754 | Population insights | 2/5 | Controller matters |
