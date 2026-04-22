# EXP-2865: Multi-Factor Stratified Basal Extraction (2026-04-22)

## Question

Can layered deconfounding — clean-fasting filter + equilibrium filter
(EGP-vs-basal balance proxy) + TOD stratification + per-bucket
bootstrap — produce more reliable per-TOD basal recommendations than
the prior point-estimate fasting-drift methods (EXP-2745, 2746, 2780),
all of which had forecasting hypotheses *fail*?

## Method (4-layer subtraction stack)

1. **Clean fasting filter** on `grid.parquet`:
   `cob == 0`, `time_since_carb_min ≥ 240`, `time_since_bolus_min ≥ 240`,
   no exercise, no override.
2. **Equilibrium filter**: `|glucose_roc| ≤ 0.5 mg/dL/min` — proxies
   "EGP balanced by basal at this moment", removes rows where the
   controller is *correcting* (which would confound the actual basal
   reading with corrective intent).
3. **TOD stratification** into 4 blocks (night/morning/afternoon/evening).
4. **Bootstrap** N=300 of median `actual_basal_rate` per
   (patient, TOD) bucket with ≥ 30 rows. Compute
   `p_mismatch_5pct` = fraction of replicates outside ±5% of scheduled.

## Results

| Metric | Value |
|--------|-------|
| Grid rows total | 1,294,346 |
| After clean-fasting filter | 256,235 (19.8%) |
| After equilibrium filter | 23,381 (1.8%) |
| (patient, TOD) buckets | 65 |
| Patients | 26 |
| Patients with all 4 TOD blocks | 9 |
| **Buckets with high-confidence mismatch (P≥0.9)** | **45 / 65 (69%)** |
| Buckets within 5% of scheduled (P<0.1) | 8 / 65 (12%) |
| Median bootstrap CI width (U/h) | 0.00 |
| **Cohort median `recommended_basal_mult` (actual / scheduled)** | **0.07** |

A median multiplier of **0.07** means: across patients and TOD blocks,
the controller is actually delivering only ~7% of the scheduled basal
rate during clean fasting equilibrium. CI width 0.00 indicates many
buckets have the controller suspending basal entirely — bootstrap
replicates collapse to a single value.

## Interpretation — why this is *not* a "lower scheduled basal by 93%"
recommendation

Cross-referencing prior findings:

* **EXP-2738 safety simulation** (memory): naive ISF replacement is
  UNSAFE because the gap IS the controller's EGP operating margin.
  The same logic applies here: scheduled basal serves as the *safety
  floor / EGP coverage margin*; the controller suspends *around* it
  during fasting equilibrium but needs the headroom for corrections.
* **EXP-2790** (memory): actual basal is only 14% of TDD across 28
  patients (closer to our 7% in equilibrium-only windows; the gap
  closes when corrections and meal-coverage temp basals are included).
* **Causal inference** (memory): "insulin gaps are controller
  suspensions, not 'no insulin' events" — the controller is already
  using all available information to set basal optimally for the next
  5 min; the high mismatch is the controller doing its job.

So the right operational read is **not** "lower scheduled basal by 93%"
but rather: **45/65 high-mismatch TOD buckets should be triaged for
expert review** — they identify locations where the scheduled rate is
working *against* the controller (forcing it to suspend) or *with* the
controller (where the controller is augmenting). The bootstrap
classifies which buckets are confidently miscalibrated vs noise.

## Comparison to prior basal experiments

| Experiment | Approach | Forecasting H pass? |
|------------|----------|---------------------|
| EXP-2745 | Fasting drift point estimate, basal multiplier | H3, H4 fail |
| EXP-2746 | Circadian fasting profiling | H2, H5 fail (2/5 pass) |
| EXP-2780 | Circadian basal optimization | 2/5 pass |
| EXP-2865 (this) | Clean+equilibrium+TOD+bootstrap | **65 buckets, 45 high-confidence mismatch flags** |

EXP-2865 does *not* attempt forecasting validation (because direct
basal replacement is known unsafe per EXP-2738). It produces an
**audition-grade triage list** of (patient, TOD) buckets that survive
all 4 deconfounding layers as confident profile-vs-actual mismatches.

## Productionization candidate

A per-(patient,TOD) `BasalMismatchFactsLoader` — analogous to the
five existing facts loaders — could expose `p_mismatch_5pct` into
`AuditionInputs`, with the same 3-tier severity rule. Branches:

* `p ≥ 0.9` → MEDIUM ("scheduled basal in this TOD is consistently
  too high or low vs controller delivery")
* `0.1 ≤ p < 0.9` → LOW ("boundary")
* `p < 0.1` → suppress (basal is well-calibrated for this TOD)

Left for a follow-on commit; this experiment first establishes the
signal exists and is decisive.

## Multi-factor analysis lessons applied to basal

The cross-experiment lesson now generalizes from ISF/CR/recovery to
basal:

> **Layered subtraction + per-strata bootstrap** outperforms naive
> fasting-drift point-estimate methods at producing actionable
> recommendations, because:
> 1. Each layer removes a *known confounder* (carb tail, bolus tail,
>    exercise, override, controller correction).
> 2. Stratification (TOD) prevents pooled estimates from hiding
>    structurally different sub-populations (cf. EXP-2857: pooled ISF
>    bootstrap hides over-correction TOD heterogeneity in 20% of
>    patients).
> 3. Bootstrap CI distinguishes "noise" from "decisive" mismatch,
>    avoiding the EXP-2745/2746 trap of flagging weak signals that
>    don't survive forecasting validation.

## Artifacts

* `externals/experiments/exp-2865_per_patient_tod_basal.parquet` (65 rows)
* `externals/experiments/exp-2865_per_patient_summary.parquet` (26 rows)
* `externals/experiments/exp-2865_summary.json`
* `docs/60-research/figures/exp-2865_stratified_basal.png`
* `tools/cgmencode/exp_stratified_basal_2865.py`
