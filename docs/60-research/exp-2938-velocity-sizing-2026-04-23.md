# EXP-2938 — Correction events binned by BG velocity (sizing test)

**Date:** 2026-04-23
**Status:** Closed
**Scope:** Design-feature characterisation for open-source AID author
audience. NOT therapy advice.

## Question

EXP-2937 found that Loop_AB_ON delivers more SMBs faster at comparable
total dose than oref1 yet recovers 21 pp less. Hypothesis: Loop's
correction is sized to IOB-shortfall vs forecast and underperforms
specifically when **BG velocity is high** (forecast model lags
acceleration). If true, the recovery gap should be largest in the
high-velocity tertile.

## Method

Re-isolate the 3 240 sustained-high correction events from EXP-2937.
Compute `velocity_30` = mean BG slope over 30 min before crossing
>180 mg/dL. Tertile cuts: low ≤1.00, mid 1.00–1.83, high >1.83 mg/dL/min.
Per-patient mean within (design, vel_bin); 2000-bootstrap CIs on
oref1 − Loop_AB_ON contrasts.

## Results

### Per (design, vel_bin) recovery_% and decline rate

| design       | vel_bin  | n_pat | smb_count | smb_total_u | decline | recovered_% |
|--------------|----------|------:|----------:|------------:|--------:|------------:|
| Loop_AB_OFF  | low_vel  |     2 |      0.00 |        0.00 |  −0.29  |       34.57 |
| Loop_AB_OFF  | mid_vel  |     2 |      0.00 |        0.00 |  −0.33  |       33.18 |
| Loop_AB_OFF  | high_vel |     2 |      0.00 |        0.00 |  −0.50  |       23.19 |
| Loop_AB_ON   | low_vel  |     5 |      4.87 |        1.57 |  −0.14  |       38.92 |
| Loop_AB_ON   | mid_vel  |     5 |      4.20 |        1.62 |  −0.23  |       32.27 |
| Loop_AB_ON   | high_vel |     5 |      3.80 |        2.07 |  −0.16  |       34.73 |
| oref1        | low_vel  |     9 |      3.01 |        1.10 |  +0.17  |       60.18 |
| oref1        | mid_vel  |     9 |      2.82 |        1.11 |  +0.20  |       55.56 |
| oref1        | high_vel |     9 |      2.49 |        1.24 |  +0.21  |       54.11 |

### oref1 − Loop_AB_ON recovery gap by velocity

| vel_bin  | recovery gap | 95 % CI               | decline gap | 95 % CI               |
|----------|-------------:|:---------------------:|------------:|:---------------------:|
| low_vel  | +0.213 ★    | [+0.116, +0.323]      | +0.312 ★   | [+0.151, +0.499]      |
| mid_vel  | +0.233 ★    | [+0.096, +0.374]      | +0.425 ★   | [+0.147, +0.689]      |
| high_vel | +0.194 ★    | [+0.063, +0.302]      | +0.365 ★   | [+0.057, +0.654]      |

## Interpretation

**The velocity-sizing hypothesis is refuted.** The recovery gap is
essentially constant across velocity bins (+19, +23, +19 pp; CIs
overlap heavily). Loop's deficit is **not** a velocity-response
deficit. It is a general correction-effectiveness offset that holds
across the entire correction-window distribution.

Two surprising sub-findings:

1. **Loop_AB_ON fires *fewer* SMBs as velocity rises** (4.87 → 4.20 →
   3.80) but slightly *higher* total dose (1.57 → 1.62 → 2.07 U). The
   forecast model evidently anticipates the rise and front-loads dose
   but does not sustain cadence.
2. **oref1 also fires fewer SMBs at high velocity** (3.01 → 2.82 →
   2.49) with slightly larger mean dose. Both designs reduce cadence
   under acceleration, suggesting both anticipate via forecast.

The constant-gap pattern means the EXP-2937 "sizing lever" needs
refinement. It is **not** "dose to BG-velocity." Candidate refined
levers:

- **Dynamic-ISF / autosens** acting as a multiplier on the correction-
  factor calculation. Would produce a roughly constant relative dose
  amplification across all correction windows.
- **SMB ratio / `maxIOB` ceiling** raising the acceptable IOB envelope
  during sustained-high, allowing oref1 to stack corrections that
  Loop's `maxBolus`/safety constraints prevent.
- **Forecast model bias**: Loop's predicted-glucose model may be
  systematically optimistic about correction trajectory, causing
  consistent under-dose regardless of velocity.

## Updated AID-author lever interpretation (post EXP-2938)

Lever 3 from EXP-2937 should be restated as:

> **Calibrate correction-loop dose-to-BG sensitivity (e.g. via
> dynamic-ISF / autosens / safety-envelope tuning) so that delivered
> insulin during sustained-high windows actually reverses BG, not
> merely slows the rise.** The specific physiological signal driving
> the calibration (velocity, IOB-vs-forecast, time-since-rise) is less
> important than the calibration result.

## What this is NOT

- NOT a refutation of EXP-2937's main finding. The recovery gap
  remains +21 pp at the marginal level and across all velocity bins.
- NOT a claim that BG velocity is irrelevant to AID design. Velocity
  remains relevant for offence (UAM, EXP-2930). It is the defence /
  correction loop where velocity stratification fails to separate the
  designs.

## Cross-reference

- EXP-2937: parent finding (sizing lever discovery)
- EXP-2934: outcome decomposition (avoidance + recovery)
- EXP-2930: offence-side velocity-aware front-loading

## Methodological note

This is a **negative finding that refines a positive one**. The
EXP-2937 sizing lever is real (constant +21 pp gap). What EXP-2938
rules out is the specific candidate mechanism "dose-to-velocity." The
underlying lever is more abstract — a calibration of the dose response
itself, not its velocity dependence. Future experiments should test
each candidate explicitly (dynamic-ISF rate scan, maxIOB envelope,
forecast-bias measurement) rather than assume a single mechanism.
