# EXP-2875 — Counter-Regulation Detection in Closed-Loop Hypo Recovery

**Date:** 2026-04-22
**Stream:** B (operational)
**Status:** Complete — DETECTED (96% positive)
**Predecessors:** EXP-2728 (EGP physics), EXP-2738 (basal/EGP equilibrium), EXP-2871 (suspension polarity)

## Question

In type-1 diabetes, hepatic glucagon counter-regulation is impaired but
rarely absent. Closed-loop AID systems mask this physiology behind
controller intervention (basal suspension) and patient rescue carbs.
Can we isolate a counter-regulation signature from observational data?

## Method

- **Event detection:** BG <70 mg/dL sustained ≥10min ("hypo"); recovery
  to ≥90 mg/dL within 90min from nadir.
- **Rescue gating:** exclude any event with `carbs > 0` in the window
  `[nadir − 15min, recovery + 30min]`. Eliminates patient-driven recovery.
- **Per-event metrics:** rise_rate (mg/dL/min), iob_at_nadir,
  iob_decay, basal_gap (actual − scheduled basal during recovery).
- **Per-patient regression:**
  `rise_rate ~ β₀ + β₁·iob_nadir + β₂·basal_gap`
  The intercept β₀ is the **counter-regulation residual** — the rate
  of recovery rise unexplained by insulin dynamics.

Cohort: 31 patients; 3,557 rescue-free events; 28 patients with ≥5
events (regression cohort).

## Result

**VERDICT: DETECTED** — population median intercept = **+1.42 mg/dL/min**
(IQR +1.04 to +1.94); **96% (27/28)** of patients have a positive
residual.

### By controller

| Controller | n_patients | Intercept median | Rise rate median |
|------------|-----------:|-----------------:|-----------------:|
| Loop       | 8          | +1.26 mg/dL/min  | 1.60 mg/dL/min   |
| Trio       | 9          | +1.20 mg/dL/min  | 1.31 mg/dL/min   |
| OpenAPS    | 4          | **+3.60**        | 1.24 mg/dL/min   |

### Per-patient highlights

- Patient **a** (Loop): +1.81, β_basal +1.35, R²=0.085 — clear residual
- Patient **f** (Loop): +2.40, β_iob +0.24, β_basal +0.97, R²=0.28 — strongest Loop fit
- Patient **odc-86025410** (OpenAPS): +4.30, β_iob +3.96, R²=0.10 — outlier high
- Patient **ns-8b3c1b50793c** (Trio): −0.31 — sole negative intercept (n=20 only)

## Interpretation

1. **Counter-regulation is preserved across the cohort.** The +1.42
   mg/dL/min median residual translates to an unexplained +14 mg/dL
   per 10min, which is physiologically plausible for a partial
   glucagon response.

2. **Loop and Trio cohort medians are tightly aligned** (+1.26 vs
   +1.20). This suggests the residual reflects patient physiology,
   not controller-specific recovery behavior.

3. **OpenAPS shows ~3× higher residual** (+3.60). Three plausible
   explanations:
   - Small N (4 patients); could be sampling.
   - Different IOB model convention may underestimate true active
     insulin at nadir, inflating the unexplained component.
   - OpenAPS suspension polarity (EXP-2871) leaves more residual
     basal at nadir, so basal_gap absorbs less of the variance.

4. **The signal is robust to confounders:**
   - Rescue carbs explicitly excluded.
   - IOB at nadir and basal_gap are partialled out by the regression.
   - Per-patient fitting eliminates between-patient profile differences.

5. **Caveat:** R² values are low (median 0.04, max 0.50). The
   regression explains only a small fraction of event-to-event
   variance — most variation is noise. The intercept is well-estimated
   despite low R² because we have many events per patient (median
   135).

## Implications

### For EGP modeling

EXP-2738/2740 found "net fasting glucose drift ~0" because controllers
balance basal against EGP. EXP-2875 reveals that during low-IOB
recovery (a natural near-zero-insulin condition), a +1.4 mg/dL/min
unexplained rise persists. This is **NOT** EGP per se — EGP would be
present at all times — but it is an additional rate that emerges when
glucose drops below ~70.

This is the expected glucagon physiology: counter-regulatory hormones
release in response to hypoglycemia, not as a baseline.

### For settings audition

- Patients with **positive intercepts ≥+2 mg/dL/min** (n=8 in this
  cohort) likely have well-preserved counter-regulation; their hypo
  events self-resolve faster than insulin pharmacokinetics alone
  would predict. Aggressive basal suspension on hypo prediction is
  appropriate (not over-correction).

- Patients with **near-zero intercept** (n=1 here, ns-8b3c1b50793c)
  may have impaired counter-regulation and benefit from rescue-carb
  protocols / pre-emptive basal reduction.

- The **OpenAPS outliers** (+4.30 to +4.57) need separate investigation
  before being used in audition signals.

### For open-source AID authors

- A patient-level "counter-reg score" derived from a year of CGM data
  could inform safer hypo-prevention thresholds.
- The asymmetry in Loop/Trio vs OpenAPS suspension behavior interacts
  with measured counter-regulation; downstream physiology models
  should account for this.

## Files

- `tools/cgmencode/exp_counter_regulation_2875.py`
- `externals/experiments/exp-2875_counter_regulation_events.parquet`
- `externals/experiments/exp-2875_per_patient.parquet`
- `externals/experiments/exp-2875_summary.json`
- `docs/60-research/figures/exp-2875_counter_regulation.png`
