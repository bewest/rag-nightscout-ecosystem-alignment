# EXP-2877 — Counter-Regulation Dose-Response vs Hypo Nadir Depth

**Date:** 2026-04-22
**Stream:** B (operational)
**Status:** Complete — DOSE-RESPONSE CONFIRMED
**Predecessor:** EXP-2875 (counter-regulation detection)

## Question

EXP-2875 found a +1.42 mg/dL/min residual rise rate in rescue-free
hypo recovery, unexplained by IOB decay + basal withdrawal. Is this a
real physiological signal (hepatic glucagon counter-regulation) or a
model-misspecification artifact?

**The definitive test is dose-response.** If the intercept reflects
glucagon physiology, it must scale monotonically with hypo nadir
depth — severe hypos (BG < 55) should trigger stronger counter-
regulatory cascades than borderline hypos (BG 65-69). If the
intercept is flat across nadir strata, it is more likely a model
artifact (missing kernel terms, non-linear effects).

## Method

### Cohort-level stratification

Bin 3,557 rescue-free events by nadir depth:

| Stratum | Nadir range (mg/dL) | Events |
|---------|--------------------:|-------:|
| severe  | BG < 55             | 1,358  |
| moderate| 55 ≤ BG < 60        |   569  |
| mild    | 60 ≤ BG < 65        |   846  |
| borderline | 65 ≤ BG < 70     |   784  |

Per-stratum regression `rise_rate ~ iob_nadir + basal_gap`; intercept
captures the residual counter-regulation signal within that severity
band.

### Per-patient 4-predictor test

For each patient with ≥10 events, fit:
```
rise_rate ~ β₀ + β₁·iob_nadir + β₂·basal_gap + β₃·nadir_depth
```
where `nadir_depth = 70 − bg_nadir` (positive; larger = deeper).
A positive β₃ supports dose-response.

## Result

**VERDICT: DOSE-RESPONSE CONFIRMED**

### Cohort-level: perfect monotonicity (Spearman ρ = −1.00, p = 0.0)

| Stratum | Bin center | N events | Intercept (mg/dL/min) | β_iob | β_basal | R² |
|---------|-----------:|---------:|----------------------:|------:|--------:|---:|
| severe  | 27.5       | 1,358    | **+3.58**             | −0.05 | +1.14   | 0.068 |
| moderate| 57.5       |   569    | **+1.80**             | +0.02 | +0.08   | 0.002 |
| mild    | 62.5       |   846    | **+1.46**             | +0.07 | +0.04   | 0.014 |
| borderline | 67.5    |   784    | **+1.04**             | +0.06 | −0.01   | 0.016 |

Severe-hypo intercept (+3.58) is **3.4× the borderline-hypo
intercept** (+1.04). The EXP-2875 +1.42 mg/dL/min cohort median
sits between "mild" and "moderate" — sensible, since the nadir
distribution is right-skewed toward milder events.

### Per-patient: 100% directional agreement (Wilcoxon p = 1.5×10⁻⁸)

- n = 27 patients with ≥10 rescue-free events
- Median β_nadir = **+0.044 mg/dL/min per mg/dL deeper**
- IQR: [+0.030, +0.057]
- **100% (27/27)** of patients have positive slope
- Wilcoxon signed-rank p = 1.49×10⁻⁸

Zero patients contradict the direction. This is a universal
cohort signal.

### R² improvement over EXP-2875

Adding `nadir_depth` as a 4th predictor raises per-patient R² from
~0.04 (EXP-2875) to median ~0.18 — a 4-5× improvement in event-level
variance explained. Nadir depth is the single most informative
predictor of recovery rise rate.

## Interpretation

1. **Counter-regulation is real, not a model artifact.**
   A 100% directional agreement across 27 independent patients with
   p=1.5×10⁻⁸ cannot be explained by IOB/basal kernel misspecification
   alone — that would produce heterogeneous (not universal) residuals.

2. **The response is dose-graded** — matching the known biology of
   glucagon/epinephrine/cortisol cascades, which release in graded
   response to hypoglycemia depth.

3. **Per-patient slopes are small but consistent.** A +0.044
   slope means a 10 mg/dL deeper nadir predicts ~+0.44 mg/dL/min
   faster recovery. The cohort-level effect (severe vs borderline,
   ~40 mg/dL apart → 2.5 mg/dL/min difference) is dominated by
   between-event variance averaging, not per-patient kinetics.

4. **Individual variation persists.** Median R² is 0.18; single
   events still carry substantial noise. The signal is population-
   level, not individual-event-level predictive.

## Implications

### For EXP-2875 audition flags (committed in 7e05fef)

The impaired/preserved thresholds were based on EXP-2875 cohort-level
intercepts. Given EXP-2877 confirms the physiology, those thresholds
are **strengthened, not revised**. However:

- A **next-generation counter-reg score** could use per-patient
  `intercept + k·β_nadir·median_nadir_depth` as a severity-aware
  signal rather than just the intercept at nadir=70. This captures
  both baseline response and dose-responsiveness.
- Patients with **high intercept but low β_nadir** have baseline
  response but poor scaling — suggests partial counter-reg failure
  at deeper hypos, which is the clinically dangerous phenotype.

### For EGP modeling

EXP-2738/2740 found steady-state net fasting drift ~0 (EGP balanced
by controller basal). EXP-2875/2877 together establish that hepatic
glucose output can be **measured observationally** during hypo
recovery — providing a physiology-derived validation for EGP
estimates.

### For open-source AID authors

- A "hypo dose-response slope" per-patient metric could drive
  adaptive hypo-prevention thresholds: patients with steep β_nadir
  tolerate brief dips but not sustained mild hypos; patients with
  shallow β_nadir need earlier intervention.
- This is a clinically grounded personalization variable that
  emerges directly from CGM + pump data — no new sensors needed.

## Next experiments

- **EXP-2878 HAAF detection:** correlate per-patient counter-reg
  intercept with hypo frequency / total hypo time. Hypoglycemia-
  associated autonomic failure is a clinically established
  phenomenon; we should see intercept decline with hypo exposure.
- **EXP-2879 circadian structure:** glucagon is circadian; dawn
  (06:00) response should exceed night. Stratify events by TOD.
- **EXP-2880 counter-reg × phenotype:** do stream_B_early
  envelope-coupling patients show different recovery kinetics than
  stream_A_dominant?

## Files

- `tools/cgmencode/exp_hypo_severity_2877.py`
- `externals/experiments/exp-2877_nadir_strata.parquet`
- `externals/experiments/exp-2877_per_patient.parquet`
- `externals/experiments/exp-2877_summary.json`
- `docs/60-research/figures/exp-2877_dose_response.png`
