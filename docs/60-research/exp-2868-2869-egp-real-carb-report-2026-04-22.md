# EXP-2868 + EXP-2869: Does Meal-Quality Gating Affect EGP Modeling? (2026-04-22)

## Question

EXP-2866 established that 30% of cohort carb events are < 5 g
(treat-of-low / detector noise). All prior EGP and fasting-window
experiments (EXP-2739 EGP personalization, EXP-2757 quantification,
EXP-2758 reconciliation, EXP-2740 basal-EGP equilibrium, EXP-2865
stratified basal) declare "fasting" using `time_since_carb_min >= 240`,
which is reset by ANY carb event. Does noise-carb contamination
affect these findings?

## Method

EXP-2868 builds `time_since_real_carb_min` that resets only on events
with `carbs >= REAL_CARB_EVENT_THRESHOLD_G` (5 g). Applies the
EXP-2865 fasting+equilibrium filter under naive vs real-carb gating.
Compares cohort EGP-proxy (median glucose ROC) and basal multiplier.
EXP-2869 re-runs the full EXP-2865 per-(patient, TOD) stratified
bootstrap under the new gate.

## Findings

### 1. EGP drift is ROBUST (the core EGP result holds)

| Metric | Naive gate | Real-carb gate |
|--------|-----------|----------------|
| Cohort median drift (mg/dL / 5 min) | **0.0** | **0.0** |
| Cohort IQR of drift | [0.0, 0.0] | [0.0, 0.0] |

The EXP-2758 conclusion — **"controller balances EGP to near-zero
net drift in fasting equilibrium"** — is NOT driven by noise-carb
contamination. No EGP experiment needs to be redone for this reason.

### 2. Prior coverage-gap hypothesis was WRONG

Both messy-log patients (`b` 79% events < 5 g; `odc-39819048`) were
already present in the naive fasting pool. The gate just sampled
fewer of their rows — the patients weren't excluded.

| Check | Naive | Real-carb |
|-------|-------|-----------|
| `b` has fasting rows | ✅ | ✅ |
| `odc-39819048` has fasting rows | ✅ | ✅ |
| Newly covered patients | — | 0 |
| Patients lost | — | 0 |

### 3. Pooled vs per-patient basal multiplier — views diverge

| View | Metric | Naive (EXP-2865) | Real-carb (EXP-2869) |
|------|--------|------------------|----------------------|
| Row-pooled cohort | median mult | 0.086 | 0.125 |
| Per-patient-TOD | median mult | 0.07 | **0.054** |
| Per-patient-TOD | % high-mismatch | 69% | **52%** |
| Per-patient-TOD | bucket count | 65 | 61 |
| Per-patient-TOD | n patients | 26 | 25 |

Interpretation:

* **Row-pooled view** (dominated by patients with many rows): real-carb
  gating shifts median up to 0.125 because it removes some low-drift
  rows from messy-log patients (their post-noise-carb "pseudo-fasting"
  rows).
* **Per-patient-TOD view** (equal weight per patient, what the audition
  matrix uses): signal becomes LESS alarmist under real-carb gating —
  52% of buckets retain high-mismatch vs 69% before. The cohort median
  drops from 0.07 → 0.054 multiplier, but the overall triage finding
  (controller delivers << scheduled in fasting equilibrium) remains.

The direction disagreement between pooled and per-patient views is
itself informative: **EXP-2865's "69% of buckets are flagged"
headline was slightly inflated** by noise-carb contamination. The
real number is 52%, still a strong triage signal but less universal.

## Productionization

`BasalMismatchFactsLoader` default path updated to
`exp-2869_per_patient_summary.parquet` (with graceful fallback to
the EXP-2865 artifact). Audition tests unchanged, all 41 pass.

## Impact on other experiments

| Experiment | Re-run needed? | Reason |
|------------|---------------|--------|
| EXP-2739 EGP personalization | No | Uses drift-based EGP estimate; drift robust (0 under both gates). |
| EXP-2740 basal-EGP equilibrium | No | Same mechanism. |
| EXP-2757 EGP quantification | No (already superseded by 2758) | Circularity artifact, not carb-gate issue. |
| EXP-2758 ISF reconciliation | No | Net drift ≈ 0 confirmed under both gates. |
| EXP-2865 stratified basal | **Yes → EXP-2869** | Per-patient-TOD mismatch share drops 69%→52%. |
| EXP-2861 ISF bootstrap | No | Drop/bolus gating independent of carb events. |
| EXP-2862 recovery bootstrap | Pending (queued) | Patient `b` recovery P=1.00 is the one confirmed `b` flag. |

## Artifacts

* `externals/experiments/exp-2868_fasting_compare.parquet` — per-patient delta
* `externals/experiments/exp-2868_summary.json`
* `externals/experiments/exp-2869_per_patient_tod_basal.parquet`
* `externals/experiments/exp-2869_per_patient_summary.parquet`
* `externals/experiments/exp-2869_summary.json`
* `tools/cgmencode/exp_fasting_egp_real_carb_2868.py`
* `tools/cgmencode/exp_stratified_basal_real_carb_2869.py`

## Bottom line

* The **EGP / net-drift finding survives** data-quality cleanup
  untouched (0 under both gates; no EGP experiment needs redoing).
* The **basal-mismatch headline is moderated**: 69% → 52% flagged
  buckets, median multiplier 0.07 → 0.054 per-patient. Still a strong
  triage signal, but the cohort-level universality claim from
  EXP-2865 was slightly inflated by noise-carb contamination.
* Audition loader now uses the corrected artifact by default.
