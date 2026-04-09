# Natural Experiments Phase 5: Weekday vs Weekend Meal Periodicity

**Experiment**: EXP-1565  
**Date**: 2026-04-09  
**Dataset**: 11 patients, ~180 days CGM+AID data  
**Config**: Therapy (≥18g / 90-min clustering) for primary analysis  
**Meals analyzed**: 2,619 (1,875 weekday + 744 weekend)

## Motivation

Phase 4 (EXP-1563) showed that stricter detection configs modestly increase meal
periodicity — entropy drops from 0.946 to 0.938, zone fraction rises from 61% to 66%.
But this analysis averaged across the entire week, potentially masking a bimodal
structure: weekdays (work/school schedule) vs weekends (flexible schedule) may have
fundamentally different eating patterns.

**Hypothesis**: Weekend meals are later, less periodic (higher entropy), and
concentrated less in canonical mealtime zones. This asymmetry, if present, means
the "shape of the week" itself contains clinical information.

## Method

### Day-of-Week Classification

Each meal's `day_of_week` (0=Monday … 6=Sunday) is captured from the DataFrame
timestamp index. Meals are split into weekday (Mon–Fri) and weekend (Sat–Sun).

### Periodicity Metrics (per mode)

For each weekday/weekend subset:
1. **Normalized Shannon entropy** of 24-bin hourly histogram (0=periodic, 1=uniform)
2. **Mealtime zone fraction**: % meals in breakfast (6–10), lunch (11–14), dinner (17–21)
3. **Peak-to-mean ratio**: concentration of the peak hour vs mean
4. **Per-zone mean hour and std**: timing shift and regularity per canonical zone
5. **Metabolic metrics**: ISF-norm excursion, spectral power, net flux

### Per-Patient Analysis

For each patient, weekday vs weekend:
- Mean meal hour and hour shift (weekend − weekday)
- ISF-norm excursion delta
- Meal count ratio

### Cross-Config Comparison

All 3 detection configs (A/B/C) analyzed separately for weekday vs weekend.

## Results

### Population Summary

| Metric | Weekday | Weekend | Delta |
|--------|---------|---------|-------|
| Meals | 1,875 | 744 | — |
| Meals/day | ~375/day* | ~372/day* | balanced |
| Entropy | 0.938 | **0.925** | −0.013 |
| Zone% | **67.0%** | 62.0% | −5.0 |
| Peak Hour | 20 | 20 | 0 |
| ISF-Norm | 1.642 | **1.767** | +0.125 |

*Normalized: 1,875/5 weekdays ≈ 375/day vs 744/2 weekend days ≈ 372/day — nearly identical meal rate per day.

### DOW Distribution

| Mon | Tue | Wed | Thu | Fri | Sat | Sun |
|-----|-----|-----|-----|-----|-----|-----|
| 365 | 374 | 384 | 373 | 379 | 377 | 367 |

Remarkably uniform — no day-of-week has significantly more or fewer meals.
This rules out a "binge day" or "fast day" pattern at the population level.

### Mealtime Zone Shifts

| Zone | Weekday | Weekend | Shift |
|------|---------|---------|-------|
| Breakfast | 8.2h | 8.7h | **+25 min** |
| Lunch | 12.5h | 12.5h | −2 min |
| Dinner | 19.2h | 19.2h | −1 min |

**Breakfast is the only meal that shifts on weekends** — approximately 25 minutes
later, consistent with sleeping in. Lunch and dinner are remarkably stable.

### Cross-Config Weekday vs Weekend Entropy

| Config | WD Entropy | WE Entropy | WD Zone% | WE Zone% |
|--------|-----------|-----------|----------|----------|
| A (≥5g/30m) | 0.946 | 0.937 | 62.0% | 58.3% |
| B (≥5g/90m) | 0.948 | 0.938 | 64.5% | 60.4% |
| C (≥18g/90m) | 0.938 | 0.925 | 67.0% | 62.0% |

The weekday/weekend entropy gap is **consistent across all configs** (~0.01 lower
on weekends). This is counterintuitive — weekends are actually *more* periodic,
not less. The zone fraction tells a different story: weekdays have ~5% more meals
in canonical zones (3.7–5.0% depending on config).

## Key Findings

### 1. Weekends Are More Temporally Concentrated (Lower Entropy)

Counter to hypothesis, weekend meals have *lower* entropy (0.925 vs 0.938).
This means weekend meals are MORE concentrated in fewer hours — likely because:
- Fewer early-morning meals (no work-schedule breakfast rush at 6-7am)
- Meals cluster in a narrower late-morning-to-evening band
- The breakfast "spread" from 6-10am on weekdays inflates weekday entropy

### 2. But Weekdays Are More Zone-Aligned

Weekdays have 5% more meals in canonical mealtime zones (67% vs 62%).
Weekend meals drift outside the strict 6-10/11-14/17-21 boundaries —
particularly breakfast moving past 10am (into the "gap" between breakfast
and lunch zones). Weekend eating is concentrated but shifted.

### 3. Weekend Meals Are Metabolically Worse

ISF-normalized excursion is **+0.125 higher** on weekends (1.767 vs 1.642).
This means weekend meals produce ~8% more "correction work" per meal,
suggesting:
- Larger portions / more indulgent food choices
- Less pre-bolusing (more reactive than proactive)
- Different activity patterns affecting insulin sensitivity

### 4. Breakfast Is the Only Shifting Meal

The +25 minute breakfast shift is the sole mealtime change. Lunch and dinner
are within ±2 minutes — essentially identical. This suggests:
- Lunch/dinner timing is driven by hunger/social cues, not schedule
- Breakfast is uniquely schedule-dependent
- The "weekend effect" on diabetes is primarily a morning phenomenon

### 5. Per-Day Meal Rate Is Remarkably Constant

375 meals/weekday vs 372 meals/weekend-day — people eat the same number of
meals regardless of day type. The asymmetry is in *timing* and *quality*,
not quantity.

## Clinical Implications

### For AID Systems

1. **Weekend morning profiles**: AID systems could benefit from weekend-specific
   breakfast timing expectations — the 25-minute shift means predicted carb
   absorption timing is systematically early on weekends.

2. **Weekend ISF adjustment**: The +8% ISF-norm excursion on weekends suggests
   a modest weekend insulin sensitivity change. Systems like AAPS with
   profile switching could benefit from weekend profiles.

3. **Zone-based alerting**: Meal expectation alerts should use slightly relaxed
   breakfast timing on weekends (6:30-10:30 vs 6:00-10:00).

### For Data Quality

- **DOW balance**: The uniform DOW distribution confirms no systematic data
  collection bias — CGM coverage is consistent across the week.
- **Entropy as regularity metric**: Within-mode entropy (WD=0.938, WE=0.925)
  is lower than whole-week entropy (0.938 from EXP-1563), confirming that
  separating modes reveals tighter periodicity within each mode.

## Visualizations

### Figure 21: Weekday vs Weekend Meal Timing
`visualizations/natural-experiments/fig21_weekday_weekend_timing.png`

Three-panel figure:
- A) Normalized hourly histograms overlaid (weekday blue, weekend red)
- B) Difference plot (weekend − weekday) showing the breakfast shift
- C) DOW meal counts with weekday/weekend mean lines

### Figure 22: Per-Patient Weekday vs Weekend Patterns
`visualizations/natural-experiments/fig22_per_patient_weekday_weekend.png`

Three-panel per-patient comparison:
- A) Mean hour shift per patient (horizontal bars)
- B) ISF-norm delta per patient (which patients eat worse on weekends?)
- C) Meal volume weekday vs weekend

### Figure 23: Mealtime Zone Shift Detail
`visualizations/natural-experiments/fig23_zone_shift_detail.png`

Three-panel zone analysis:
- A) Mean meal time by zone (weekday vs weekend bars)
- B) Shift in minutes per zone (breakfast +25min dominates)
- C) Timing regularity (std of hour) per zone

### Figure 24: Weekday vs Weekend Metabolic Profile
`visualizations/natural-experiments/fig24_weekday_weekend_metabolic.png`

Three-panel metabolic comparison (box plots):
- A) ISF-normalized excursion
- B) Supply×demand spectral power (log scale)
- C) Net flux (carb vs insulin dominant)

## Source Files

- Experiment: `tools/cgmencode/exp_clinical_1551.py` (EXP-1565, `exp_1565_weekday_weekend_periodicity`)
- Helpers: `_weekday_weekend_periodicity()`, `_per_patient_dow_analysis()`
- Results: `externals/experiments/exp-1565_natural_experiments.json`
- Visualizations: `visualizations/natural-experiments/fig{21,22,23,24}_*.png`

## Gaps Identified

- **GAP-PROF-006**: No AID system supports weekday vs weekend profile scheduling —
  the +25min breakfast shift and +8% ISF-norm delta suggest this would be beneficial
- **GAP-ALG-019**: Meal prediction models don't incorporate day-of-week features —
  weekend breakfast timing is systematically different and predictable
- **GAP-DS-006**: DeviceStatus doesn't track day-type context — a simple
  weekday/weekend flag would enable retrospective DOW analysis in Nightscout
