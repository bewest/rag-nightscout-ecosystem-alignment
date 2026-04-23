# EXP-2879 — Counter-Regulation Circadian Structure (Time-of-Day)

**Date:** 2026-04-22
**Stream:** B (operational)
**Status:** Complete — NO MEANINGFUL TOD STRUCTURE (effect <10% of mean)
**Predecessors:** EXP-2875 (detection), EXP-2877 (dose-response), EXP-2878 (HAAF)

## Question

Counter-regulatory hormones (glucagon, cortisol, catecholamines,
growth hormone) have strong circadian rhythms; the dawn phenomenon
classically peaks at 02:00-08:00. If EXP-2875/2877 recovery kinetics
reflect real hormone-mediated counter-regulation, we expect time-of-
day structure with stronger response during dawn/early-morning vs
evening/afternoon.

## Method

- Re-detected 3,557 rescue-free hypo events (same logic as EXP-2875).
- Annotated each event with nadir hour-of-day (UTC).
- Binned into 4 TOD bands: night (00-06), morning (06-12),
  afternoon (12-18), evening (18-24).
- Cohort-level stratum regression `rise_rate ~ iob_nadir + basal_gap`
  per band.
- Per-patient morning-median vs night-median comparison via Wilcoxon.

## Result

**VERDICT: NO MEANINGFUL CIRCADIAN STRUCTURE**

### Cohort stratum intercepts (tightly clustered)

| TOD band  | UTC hours | N events | Intercept | Median rise |
|-----------|-----------|---------:|----------:|------------:|
| night     | 00-06     |    875   | **+2.46** | +1.30       |
| morning   | 06-12     |  1,010   | +2.27     | +1.24       |
| afternoon | 12-18     |    859   | +2.21     | +1.37       |
| evening   | 18-24     |    813   | +2.20     | +1.37       |

Range across all four bands: **0.26 mg/dL/min (10% of mean)** —
effectively flat.

### Per-patient morning − night

- n = 25 patients with ≥5 events in both bands
- Median diff = **−0.114 mg/dL/min** (night slightly higher)
- 44% of patients show morning > night (near 50/50)
- Wilcoxon signed-rank p = 0.67 — clearly null

## Interpretation

### 1. UTC-bin caveat (modest)

Growth-hormone and cortisol peaks are classically 02:00-05:00 *local*
time. With UTC timestamps and an unknown mix of timezones, our
"night" (00:00-06:00 UTC) bin partially overlaps the pre-dawn peak
for Western Europe patients and is mid-sleep for US patients. This
could explain night's slightly higher intercept if dawn *is* real
but smeared across bins. However the effect size (0.26) is too small
to matter regardless.

### 2. The dominant explanation: AID suppresses circadian signal

AID controllers have circadian-aware basal profiles that already
compensate for dawn phenomenon *before* it causes hypoglycemia.
Consequently, the hypos captured in this dataset are predominantly
insulin-driven (post-bolus stacking, over-correction), not hormone-
driven. Recovery from an insulin-driven hypo depends primarily on
IOB decay + basal-rate adjustment — exactly what we observe in the
regressions — not on circadian hormone amplification.

This is itself a meaningful finding: **for AID users, counter-
regulation magnitude is a patient-level property, not a time-of-day
property.**

### 3. Consistency with EXP-2875/2877

- EXP-2877 confirmed dose-response: deeper hypo → stronger rise.
  This can be driven by IOB-BG gradient amplification AND/OR
  hormonal scaling; both yield the same observational signature.
- EXP-2879 null TOD effect suggests **the amplification source is
  hypo-depth, not time-of-day**. The counter-reg "intercept" is
  better interpreted as a steady-state hepatic responsiveness
  (glycogen availability + portal glucagon reserve) rather than
  a circadian modulator.
- EXP-2878 HAAF signal on β_nadir (not intercept) is therefore the
  more clinically actionable channel.

### 4. What would change this conclusion?

- Patient-local-time timestamps (currently UTC only)
- Meal-/activity-aware TOD subclassification (post-breakfast vs
  fasted morning have different counter-reg backgrounds)
- Dedicated dawn-phenomenon pre-nadir analysis (pre-hypo BG
  trajectory by TOD) — may show circadian structure in *risk*
  even if recovery is invariant

## Implications

### For audition framework

- **Do NOT stratify counter-reg audition flags by TOD.** The signal
  is TOD-invariant, so per-patient thresholds are sufficient.
- Per-patient intercept + β_nadir (from EXP-2877, 2878) fully
  parameterize the counter-reg signal.

### For algorithm authors

- Time-of-day adaptation for hypo-prevention should be driven by
  the pre-hypo *risk* profile (BG trajectory, basal adequacy), not
  the post-hypo *recovery* profile — recovery is invariant to TOD.
- In other words: **adjust the offense based on TOD; the defense is
  constant.**

### For meal/basal modeling

Since recovery is TOD-invariant, the IOB-subtracted residual
(EXP-2840 two-stream framework) can be computed without TOD
stratification — one less layer of complexity.

## Limitations

- UTC-only timestamps, unknown patient timezones
- Cohort is AID users → pre-dawn-phenomenon has already been
  compensated by controller. Conclusion may not generalize to
  pumps / MDI / or uncontrolled T1D.
- Does not test pre-nadir BG trajectory (risk vs recovery dichotomy).

## Three-experiment counter-reg summary

| EXP | Question | Result |
|-----|---------|--------|
| 2875 | Is there a counter-reg signal? | YES — +1.42 mg/dL/min intercept, 27/28 patients |
| 2877 | Is it real physiology (dose-response)? | CONFIRMED — ρ=−1.00, 100% positive β_nadir |
| 2878 | Does it degrade with exposure (HAAF)? | WEAK — β_nadir ρ=−0.40 p=0.04; intercept null |
| 2879 | Does it vary by TOD (dawn)? | NO — <10% range across 4 bands |

**Composite picture:** counter-regulation is a patient-level trait,
dose-graded by hypo depth, weakly degraded by exposure (via β_nadir),
and invariant across time-of-day. The three channels — intercept
(baseline), β_nadir (gradient), HAAF sensitivity — are the
clinically actionable parameterization.

## Next experiments

- **EXP-2880 Pre-nadir trajectory by TOD:** does dawn phenomenon
  show up in the *risk* side (BG slope approaching hypo) rather
  than recovery?
- **EXP-2881 Counter-reg × site age:** does CAGE > 72h weaken
  counter-reg (parallel to weakening ISF)?
- **Longitudinal counter-reg drift:** does intercept or β_nadir
  decline over weeks of continuous AID use in a patient?

## Files

- `tools/cgmencode/exp_counter_reg_tod_2879.py`
- `externals/experiments/exp-2879_tod_events.parquet`
- `externals/experiments/exp-2879_tod_summary.json`
- `docs/60-research/figures/exp-2879_tod.png`
