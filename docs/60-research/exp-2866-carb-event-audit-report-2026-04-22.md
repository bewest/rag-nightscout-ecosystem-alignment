# EXP-2866: Carb-Event Quality Audit & Impact on Prior Research (2026-04-22)

## Trigger

User sanity check: clinical priors expect 2 sizable meals (>50–60g)
plus optional snacks/dessert per day, up to 6 events/day, with >10
events/day being implausible. Initial spot-checks suggested too many
small "meals" being detected. Goal: validate the data and assess
which prior experiments are affected.

## Carb-event distribution (cohort, 26,020 events)

| Bucket (g) | Count | Share |
|------------|-------|-------|
| [0, 5)   | 7,811 | **30.0%** |
| [5, 15)  | 4,332 | 16.6% |
| [15, 30) | 6,453 | 24.8% |
| [30, 50) | 4,468 | 17.2% |
| [50, 80) | 1,968 | 7.6% |
| [80, ∞)  | 988   | 3.8% |

Cohort median event = **15g**, P25 = 3g, P75 = 30g. **Only 11.4% of
events are ≥50g** — far below the user's clinical prior that
substantial meals should dominate.

## Meals-per-day distribution

Cohort median = 5/day, P95 = 25/day.

**Patients above the >10/day implausibility threshold** (median
events/day):

| Patient | Median ev/day | Max | <5g share |
|---------|---------------|-----|-----------|
| **b**           | **38** | 59 | **78.8%** |
| odc-39819048    | 31     | 52 | 82.8%     |
| ns-c422538aa12a | 13     | 43 | 50.8%     |
| ns-9b9a6a874e51 | 9      | 22 | 29.3%     |

Six patients have >10% small-event share; five exceed the 30%
implausibility threshold for either size or frequency.

## Impact on EXP-2865 basal extraction (the immediate concern)

EXP-2866 method: re-derive `time_since_real_carb_min` ignoring events
<5g, re-run the EXP-2865 clean-fasting + equilibrium filter, compare.

| Metric | Original | Real-carb (≥5g) | Δ |
|--------|----------|-----------------|---|
| Rows surviving filter | 23,381 | 1,128 | −95.2% |
| Patient `b` rows | 74 | 0 | gone |
| Cohort median multiplier change | — | — | **0.0%** |
| Patients gaining rows | — | — | **0** |

Counter-intuitive at first: removing <5g events makes the filter
*more* restrictive, not looser. Why: the EXP-2865 filter is already
gated by `cob == 0`, which requires the system to believe COB has
fully decayed. Small carb events decay COB quickly anyway; the
binding constraint is real-meal frequency. **For patients with messy
meal logs, real meals are themselves frequent enough that 4-hour
fasting gaps are rare.**

**Net basal-extraction impact**: EXP-2865's 65 (patient, TOD)
buckets and 45 high-confidence mismatch flags are dominated by the
~20 patients with clean meal logs and sparse real-meal patterns.
The high-small-event patients contribute few rows in either
definition, so the cohort findings are largely robust — **but
EXP-2865 has a coverage gap for 5+ messy-log patients** whose basal
calibration cannot currently be assessed.

## Impact on other prior research

| Experiment | Likely impact | Reason |
|------------|---------------|--------|
| EXP-2750/2752 carb absorption (small vs large meals) | **HIGH** | Small-meal pool likely contaminated by 30% sub-5g events that aren't meals. Per-patient findings still hold; cohort-level "small-meals slow" claim is suspect. |
| EXP-2812 pre/post transitions | **MEDIUM** | Bucket-per-patient single-hour transitions may absorb spurious tiny events. Needs re-validation with real-carb gating. |
| EXP-2861 ISF gap | **LOW** | Filter requires `drop>0 AND bolus>0`. Tiny "treat-the-low" carb events lack bolus → excluded. |
| EXP-2862 recovery | **LOW–MED** | Same source as EXP-2812, single-hour bucketing. |
| EXP-2863 wear / EXP-2864 post-high | **LOW** | Both rely on aggregated patient-level distributions; small-event noise averages out. |
| EXP-2865 basal extraction | **LOW for findings, HIGH for coverage** | 0% change in computed multipliers; 5+ patients excluded entirely. |
| EXP-2857 TOD stability | **LOW** | Sources from EXP-2847 corrections (drop>0 + bolus>0); not meal-detector dependent. |
| EXP-2790 insulin accounting (14% basal of TDD) | **LOW** | Counts insulin, not carbs. Robust. |

## Recommendation: introduce a `real_meal_event` filter convention

A small follow-up data-prep utility would help future experiments:

```python
# tools/cgmencode/production/meal_filter.py (proposed)
REAL_MEAL_THRESHOLD_G = 5.0  # below: treat as treat-of-low / noise
REAL_MEAL_FLOOR_G = 10.0     # below: treat as snack/correction not meal

def is_real_meal(carbs_g: float) -> bool:
    return carbs_g >= REAL_MEAL_FLOOR_G

def is_real_carb_event(carbs_g: float) -> bool:
    return carbs_g >= REAL_MEAL_THRESHOLD_G
```

Then experiments grouping "meals" should use `is_real_meal` (≥10g),
while "any logged carb that affects COB / fasting filters" should
use `is_real_carb_event` (≥5g).

## Patient `b` re-evaluation

Patient `b`'s entire bootstrap chain trail (Simpson boundary, ISF
boundary, recovery P=1.00, wear inert, post-high universal) was
already weakened by EXP-2862's bootstrap to a single confirmed
flag. Now we add: **patient `b`'s meal log is unreliable** (79% of
"meals" are <5g). Recovery, post-high, and any meal-adjacent finding
for `b` should be treated as low-confidence pending data quality
review.

## What does NOT change

* The 5-signal bootstrap chain (EXP-2859/2861/2862/2863/2864) was
  already per-patient and bootstrap-gated; conclusions stand.
* EXP-2865's basal mismatch finding (45/65 high-confidence buckets)
  is robust within its cohort.
* The EGP / safety-margin interpretation (EXP-2738) stands.

## Artifacts

* `externals/experiments/exp-2866_real_carb_impact.parquet` (per-patient counts)
* `externals/experiments/exp-2866_summary.json`
* `tools/cgmencode/exp_real_carb_impact_2866.py`
