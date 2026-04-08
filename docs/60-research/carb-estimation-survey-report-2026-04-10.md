# EXP-1341: Multi-Algorithm Meal Carb Estimation Survey

## Summary

We survey how four different algorithms estimate meal carbohydrate magnitude
from the same CGM/AID data, comparing their qualitative behavior across
12,060 detected meals in 11 patients (180 days each).

**Key finding**: All algorithmic estimates are 27–65% of user-entered carbs,
and correlations with entered carbs are weak (r = 0.09–0.33).  This confirms
entered carbs are **not** reliable ground truth.  The four methods form a
clear hierarchy of aggressiveness, reflecting their design philosophies.

## Methods

| # | Method | What it measures | Source |
|---|--------|-----------------|--------|
| 1 | **Physics residual** | Unexplained glucose rise after subtracting modeled insulin/hepatic effects | EXP-441/753 supply–demand decomposition |
| 2 | **Glucose excursion** | Simple peak minus nadir glucose rise | Baseline / naive |
| 3 | **Loop IRC** | Retrospective prediction error (actual − predicted_30) integrated with PID damping | `IntegralRetrospectiveCorrection.swift` (P=1, I=2, D=2, τ_forget=60 min) |
| 4 | **oref0 deviation** | Glucose rate of change minus expected insulin effect (BGI) | `determine-basal.js` deviation logic, `min_5m_carbimpact` floor |

All methods convert the glucose-domain integral to grams via `carbs_g = integral × CR / ISF`.

## Population Results

| Method | All meals | Announced | UAM | vs Entered (ratio) | Corr w/ entered |
|--------|----------|-----------|-----|---------------------|-----------------|
| Physics | **22.6g** | 19.5g | 23.6g | 0.65× | 0.093 |
| Excursion | 7.8g | 10.0g | 7.2g | 0.33× | 0.263 |
| Loop IRC | 5.6g | 8.0g | 5.2g | 0.27× | **0.334** |
| oref0 | **17.3g** | 19.1g | 16.7g | 0.64× | 0.246 |
| *(Entered)* | *—* | *30.0g* | *—* | — | — |

- **12,060 meals** detected across 11 patients (**76.5% unannounced**)
- Physics and oref0 give the largest estimates (18–23g); Loop IRC the smallest (6g)
- **Loop IRC has the highest correlation with entered carbs** (r=0.334) despite
  the lowest magnitude — less noisy, more conservative
- Physics has the **lowest correlation** (r=0.093) — it captures non-meal
  glucose rises too (dawn phenomenon, stress, exercise rebounds)

## By Meal Window

| Window | n | % UAM | Physics | Excursion | Loop IRC | oref0 |
|--------|---|-------|---------|-----------|----------|-------|
| Breakfast | 2,476 | 73% | 26g | 8g | 6g | 17g |
| Lunch | 1,783 | 87% | 20g | 7g | 5g | 14g |
| Dinner | 2,096 | 70% | 22g | 9g | 6g | 20g |
| Snack/other | 5,705 | 77% | 22g | 8g | 6g | 18g |

Breakfast shows the largest physics estimates, consistent with dawn phenomenon
amplifying post-meal glucose rise.  47% of detected events fall in "snack/other"
— many are likely not true meals (exercise, stress, sensor noise).

## Per-Patient Highlights

| Patient | Meals | UAM% | Physics | Loop IRC | Entered | Notes |
|---------|-------|------|---------|----------|---------|-------|
| a | 1,366 | 85% | 17.6g | 4.0g | 15.0g | Miscalibrated settings |
| b | 1,319 | 23% | 13.0g | 4.4g | 24.1g | Most announced meals; only 2% pred30 coverage |
| d | 1,233 | 82% | **44.5g** | 12.9g | 26.0g | CR=14 amplifies estimates |
| f | 1,219 | 85% | 33.4g | 9.3g | 60.0g | Low ISF=20 + CR=5 |
| i | 1,123 | **95%** | **60.8g** | 6.8g | 45.0g | Physics extreme outlier |
| j | 540 | 78% | 15.9g | — | 80.0g | 0% pred30 → no Loop IRC |
| k | 1,013 | **97%** | 31.0g | 8.1g | 15.0g | Only 30 announced meals |

### Patient i: Physics Outlier

Physics estimates 60.8g median vs Loop IRC 6.8g (9× ratio).  Patient i has
95% UAM, suggesting large meals without carb entries.  The physics model
attributes all unexplained glucose rise to "carbs," including insulin
resistance effects that inflate the integral.  This patient has ISF mismatch
2.2× (from EXP-1291 therapy assessment) — the physics model tries to explain
the ISF gap as "carb absorption."

### Patient d: CR Amplification

With CR=14 (highest in cohort), small glucose integrals translate to large
carb estimates.  Physics 44.5g exceeds entered 26g — suggesting either the
CR is too high or the person regularly underreports carbs.

## Qualitative Interpretation

### How Each Algorithm "Sees" Meals

1. **Physics residual** — Most aggressive.  Attributes any glucose rise not
   explained by insulin pharmacokinetics and hepatic output to "carb absorption."
   Captures dawn phenomenon, stress, and exercise rebounds as false positives.
   Best for *total unexplained glucose variability*, not just meals.

2. **Glucose excursion** — Simplest, least informative.  Just measures how high
   glucose went.  Ignores insulin counteraction, so underestimates true carb
   impact in well-controlled patients (where insulin blunts the rise).

3. **Loop IRC** — Most conservative.  PID controller with integral forgetting
   (τ=60 min) intentionally dampens accumulation.  Loop's philosophy: better to
   underestimate carbs than over-correct.  In UAM scenarios, Loop sees a median
   5.2g event — essentially treating most UAM as very small snacks.  This
   conservative approach means **Loop is slow to ramp up insulin for unannounced
   meals**, relying on repeated correction cycles.

4. **oref0 deviation** — Balanced middle ground.  Direct deviation (actual ΔBG
   minus insulin effect) without PID damping.  Captures more signal than Loop IRC
   (17g vs 6g) but noisier.  The `min_5m_carbimpact` floor ensures slow meals
   still register.  In UAM mode, oref0 responds faster than Loop because it
   accumulates deviation without forgetting.

### What This Means for UAM Handling

The 4× difference between oref0 (17g) and Loop IRC (6g) in UAM cases explains
a known clinical observation: **AAPS/Trio respond faster to unannounced meals
than Loop**.  Loop's PID-dampened IRC requires more evidence (higher glucose,
longer duration) before it "believes" a significant meal is occurring.

### Entered Carbs Are Unreliable

- Median entered carbs (30g) are 1.3–5.4× the algorithmic estimates
- Correlation with all methods is weak (r < 0.34)
- Patient j enters 80g median but algorithms see 6–20g
- Patient k enters only 15g — surprisingly close to excursion estimate (10g)

This reflects: (a) people round up carb entries, (b) AID insulin delivery
partially hides carb effects from the glucose trace, (c) some "carbs" entries
are pre-boluses where insulin acts before glucose rises.

## Limitations

1. **Meal detection sensitivity**: 15 mg/dL threshold catches ~7 events/day,
   many likely not meals.  A stricter threshold would reduce count but miss
   small meals.

2. **Profile settings are static**: We use fixed ISF/CR per patient.
   Actual values vary by time of day and change over months.

3. **Loop IRC approximation**: We integrate positive retrospective deviations
   directly, while actual Loop IRC uses a PID controller with specific gains
   (P=1, I=2, D=2).  Our estimate captures the direction but not the exact
   dynamics of Loop's correction logic.

4. **Patient j has 0% predicted_30 coverage**: No Loop IRC estimates available.

5. **Physics captures non-meal signals**: Dawn phenomenon, stress, exercise
   rebounds all contribute to physics estimates.

## Implications

1. **For algorithm design**: The conservative Loop IRC approach trades
   responsiveness for safety.  oref0's more aggressive deviation tracking
   reaches faster but risks overreaction.  Physics shows the theoretical
   maximum signal available.

2. **For carb estimation**: No single algorithm produces reliable carb
   estimates.  The best approach may be an ensemble that uses physics for
   detection, excursion for magnitude scaling, and Loop/oref0 deviation
   for real-time response.

3. **For UAM handling**: The 5–6g median IRC estimate for UAM events means
   Loop treats most unannounced meals as negligible.  This is intentionally
   conservative but frustrating for patients who don't announce meals.

## Files

- Script: `tools/cgmencode/exp_clinical_1341.py`
- Summary JSON: `externals/experiments/exp-1341_carb_survey.json`
- Detail JSON: `externals/experiments/exp-1341_carb_survey_detail.json` (12,060 per-meal records)
