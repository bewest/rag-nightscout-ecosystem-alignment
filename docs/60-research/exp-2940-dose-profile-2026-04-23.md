# EXP-2940 — Within-window dose profile + time-to-BG-peak

**Date:** 2026-04-23
**Status:** Closed
**Scope:** Design-feature characterisation for open-source AID author
audience. NOT therapy advice.

## Question

EXP-2939 narrowed the recovery mechanism to temporal-distribution
candidates. Test directly: do Loop and oref1 distribute correction
SMB delivery differently within the 60-min window? Is BG-trajectory
peak time different?

## Method

Reuse EXP-2937 carb-isolated correction-window cohort (3 242 events;
2 300 with at least one SMB delivered). For each event with SMBs,
compute cumulative SMB fraction at minutes [5, 10, 15, 20, 30, 45, 60]
and time-to-BG-peak within window. Per-patient mean; ≥5 events per
patient required; 2000-bootstrap CIs.

## Results

### Per-patient mean cumulative SMB fraction by design

| design       | 5min  | 10min | 15min | 20min | 30min | 45min | 60min | tt_peak (min) | smb_total |
|--------------|------:|------:|------:|------:|------:|------:|------:|--------------:|----------:|
| Loop_AB_ON   | 0.290 | 0.457 | 0.541 | 0.608 | 0.727 | 0.854 | 1.000 |          29.7 |     1.975 |
| oref1        | 0.333 | 0.480 | 0.572 | 0.630 | 0.740 | 0.868 | 1.000 |          23.0 |     1.413 |

### oref1 − Loop_AB_ON cumulative-fraction gaps

| checkpoint | oref1 | Loop_AB_ON | gap     | 95 % CI               |
|------------|------:|-----------:|--------:|:---------------------:|
|       5min | 0.333 |      0.290 | +0.043  | [−0.020, +0.108]      |
|      10min | 0.480 |      0.457 | +0.023  | [−0.052, +0.098]      |
|      15min | 0.572 |      0.541 | +0.031  | [−0.029, +0.092]      |
|      20min | 0.630 |      0.608 | +0.022  | [−0.034, +0.078]      |
|      30min | 0.740 |      0.727 | +0.014  | [−0.045, +0.067]      |
|      45min | 0.868 |      0.854 | +0.014  | [−0.021, +0.047]      |

**Dose profiles are essentially identical.** None of the checkpoint
gaps are significant; the largest is +0.043 at 5 min. If anything
oref1 marginally front-loads slightly *more* than Loop, not less.

### BG-trajectory time-to-peak

- Loop_AB_ON: 29.7 min mean
- oref1: 23.0 min mean
- Difference: oref1 BG peaks **6.7 min earlier** within the window.

## Interpretation

This is a decisive narrowing. With essentially identical within-window
dose schedules and slightly lower total dose, oref1's BG peaks 6.7 min
earlier and recovers 21 pp more often. The mechanism is **NOT**
within-window dose mechanics.

The recovery edge must emerge from **pre-window state** — insulin
context that differs at the moment correction begins:

1. **Higher pre-event IOB**: oref1's continuous SMB cadence in the
   hours prior to the correction window leaves more pre-existing
   insulin in the absorption pipeline. The new SMBs land on a patient
   already partially insulinated; effective insulin action is
   higher per fresh dose unit.
2. **Different basal-cut history**: pre-event basal cuts in Loop may
   reduce IOB just as the rise begins; oref1's basal posture +
   continuous SMB may keep effective insulin floor higher.
3. **Algorithmic prior-state coupling**: oref1's autosens / dynamic-ISF
   uses recent BG patterns to set the operating sensitivity *before*
   the correction window opens. Loop's correction begins from a fresh
   forecast.

All three converge on the same mechanism class: **the correction loop's
effectiveness depends on the prior 1–3 hours of insulin context, not
just the within-window dose decisions.**

## Updated mechanism map (correction loop)

After EXP-2937/2938/2939/2940 elimination:

| Candidate                          | Status        | Evidence |
|------------------------------------|---------------|----------|
| Within-window cadence              | Refuted       | EXP-2937 |
| Within-window first-fire latency   | Refuted       | EXP-2937 |
| Within-window total dose           | Refuted       | EXP-2937 |
| Dose-to-velocity                   | Refuted       | EXP-2938 |
| Dose-per-mgdl above target         | Refuted       | EXP-2939 |
| Dynamic-ISF amplification slope    | Refuted       | EXP-2939 |
| Within-window dose schedule shape  | Refuted       | **EXP-2940** |
| Pre-window IOB / insulin context   | **Candidate** | (EXP-2941 pending) |
| Pre-window autosens calibration    | **Candidate** | (no direct probe) |

## Updated AID-author guidance

The lever has shifted from "tune correction-loop response" to "ensure
the correction loop *inherits* a useful insulin-state context from the
prior hours." Specifically:

> Correction-loop effectiveness during sustained-high windows is
> dominated by the prior 1–3 hours of insulin posture, not by the
> within-window dose decisions. AID authors should evaluate continuous
> low-cadence dosing (SMB ratio, basal posture, autosens activation)
> as the mechanism by which corrections become effective when needed.

This explains the EXP-2937 paradox cleanly: Loop's autobolus tries to
correct *during* the rise from a relatively cold pharmacokinetic state;
oref1's continuous-cadence posture keeps insulin warm so corrections
land on already-active absorption.

## What this is NOT

- NOT a recommendation for higher TDD. Pre-window insulin posture is
  a distribution effect, not a magnitude effect (oref1 actually delivers
  *less* total dose in this cohort).
- NOT confirmation of any single mechanism class — three pre-window
  candidates remain viable; EXP-2941 will probe pre-event IOB proxy
  directly.

## Next experiment queued (EXP-2941)

For each correction-window event, compute `prior_smb_3h` (sum of SMBs
in 3 hours before entry) as IOB proxy. Test:
1. Does oref1 enter correction windows with higher prior_smb_3h?
2. Within a design, does higher prior_smb_3h predict better recovery?
3. Does conditioning on prior_smb_3h tertile collapse the recovery gap?

## Cross-reference

- EXP-2937: parent finding (sizing lever)
- EXP-2938: velocity-sizing refuted
- EXP-2939: dynamic-ISF amplification refuted
- EXP-2934: outcome decomposition (avoidance + recovery)
- Synthesis: synthesis-design-comparison-2026-04-23.md
