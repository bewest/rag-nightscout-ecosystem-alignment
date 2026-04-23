# EXP-2939 — Dynamic-ISF amplification proxy test (refuted)

**Date:** 2026-04-23
**Status:** Closed
**Scope:** Design-feature characterisation for open-source AID author
audience. NOT therapy advice.

## Question

EXP-2937 found a +21 pp recovery gap that EXP-2938 showed is constant
across BG-velocity bins. The next refined candidate from EXP-2938 was
**dynamic-ISF amplification**: oref1's correction sensitivity multiplier
scales with hyperglycaemia, so dose-per-mg/dL-above-target should grow
faster in oref1 than Loop as peak BG rises.

## Method

Reuse EXP-2937 carb-isolated correction-window cohort (3 242 events).
Bin events on `bg_peak` tertile (low ≤198, mid 198–225, high >225).
Compute `dose_per_50mgdl = smb_total_u / ((bg_peak − 100) / 50)` —
units of insulin per 50 mg/dL of hyperglycaemia. Per-patient mean
within (design, bg_bin); 2000-bootstrap CIs.

## Results

### Per (design, bg_bin) per-patient means

| design       | bg_bin  | n_pat | bg_peak | smb_total_u | dose_per_50 | recovered_% |
|--------------|---------|------:|--------:|------------:|------------:|------------:|
| Loop_AB_OFF  | low_bg  |     2 |  189.09 |       0.000 |       0.000 |       83.45 |
| Loop_AB_OFF  | mid_bg  |     2 |  210.91 |       0.000 |       0.000 |       29.56 |
| Loop_AB_OFF  | high_bg |     2 |  274.47 |       0.000 |       0.000 |        3.52 |
| Loop_AB_ON   | low_bg  |     5 |  189.07 |       0.819 |       0.455 |       77.70 |
| Loop_AB_ON   | mid_bg  |     5 |  211.29 |       1.448 |       0.646 |       28.27 |
| Loop_AB_ON   | high_bg |     5 |  259.26 |       2.643 |       0.807 |        5.54 |
| oref1        | low_bg  |     9 |  188.65 |       0.626 |       0.350 |       86.16 |
| oref1        | mid_bg  |     9 |  210.71 |       1.248 |       0.566 |       44.15 |
| oref1        | high_bg |     9 |  251.06 |       1.979 |       0.645 |       16.67 |

### Within-design dose_per_50 slope across bg_bins

- oref1: 0.350 → 0.566 → 0.645 (+84 % low→high)
- Loop_AB_ON: 0.455 → 0.646 → 0.807 (+78 % low→high)

**Both designs scale dose_per_50 with peak BG by similar factor.**
This refutes the hypothesis that oref1 alone uses dynamic-ISF
amplification.

### Dose-per-50 contrast (oref1 − Loop_AB_ON)

| bg_bin  | dose_per_50 gap | 95 % CI               |
|---------|----------------:|:---------------------:|
| low_bg  |          −0.106 | [−0.295, +0.075]      |
| mid_bg  |          −0.080 | [−0.354, +0.178]      |
| high_bg |          −0.162 | [−0.508, +0.162]      |

Loop **delivers MORE dose per mg/dL of hyperglycaemia than oref1
across all bins** (none significant due to small n). Yet:

### Recovery gap holds at every bg_bin

| bg_bin  | recovery gap | 95 % CI               |
|---------|-------------:|:---------------------:|
| low_bg  |       +0.085 ★ | [+0.012, +0.146]    |
| mid_bg  |       +0.159 ★ | [+0.027, +0.286]    |
| high_bg |       +0.111 ★ | [+0.052, +0.169]    |

## Interpretation: mechanism narrowed by elimination

Across EXP-2937, 2938, 2939 the +21 pp recovery gap is **NOT** explained
by:

| Candidate                         | EXP    | Status   |
|-----------------------------------|--------|----------|
| SMB cadence                       | 2937   | Refuted (Loop more) |
| First-fire latency                | 2937   | Refuted (Loop faster) |
| Total dose                        | 2937   | Refuted (Loop ≈ or higher) |
| Dose-to-velocity                  | 2938   | Refuted (gap constant) |
| Dose-per-mgdl above target        | 2939   | Refuted (Loop more) |
| Dynamic-ISF amplification slope   | 2939   | Refuted (similar slopes) |

**The remaining viable candidates are temporal-distribution and
pharmacokinetic-effective:**

1. **Within-window dose timing**: Loop's autobolus may concentrate
   dose at an earlier point in the rise where BG is still rising
   exogenously (peak-anticipating); oref1 may distribute dose later
   when BG is at its actual peak and most responsive. The decline rate
   inversion (oref1 +0.21 vs Loop_AB_ON −0.17 mg/dL/min) is consistent
   with this — Loop's BG is *still rising* at window end despite
   higher cumulative dose.
2. **Phantom-IOB / forecast bias**: Loop's IOB calculation may credit
   insulin that is not yet bioavailable, preventing additional
   dosing; oref1's correction-fraction logic may better account for
   absorption delay.
3. **Basal-cut interaction**: Loop's defence side relies on basal cuts
   that don't manifest as `bolus_smb`. If Loop is *cutting basal* less
   aggressively during these windows, the net delivery is comparable
   but the trajectory differs.

## What this is NOT

- NOT a refutation of dynamic-ISF as a feature in oref1; only a
  refutation that dynamic-ISF *as a peak-BG amplification slope*
  explains the recovery gap.
- NOT a claim that more dose would help Loop. Loop already doses more
  per mg/dL than oref1 in this cohort and recovers less.

## Next experiment queued (EXP-2940)

**Within-window cumulative-dose profile**: for each correction event,
compute fraction of total SMB delivered by 15, 30, 45, 60 min, and
align to BG trajectory. Test whether Loop concentrates dose earlier
(at lower BG, less effective) and oref1 distributes dose to align
with peak. If true, the AID-author lever becomes "schedule correction
SMBs to BG trajectory shape, not to forecast-error magnitude."

## Cross-reference

- EXP-2937: parent finding (sizing lever — now needs refinement to
  "trajectory alignment" not "magnitude calibration")
- EXP-2938: velocity-sizing refuted
- EXP-2934: outcome decomposition (avoidance + recovery)

## Methodological note

This is the **second negative finding refining a positive one**.
EXP-2937's "sizing lever" interpretation has now been narrowed
substantially: it is not magnitude (more dose), not velocity-aware
(velocity-tracked), and not nonlinear-ISF (similar slopes). The
remaining mechanism is in the temporal/pharmacokinetic axis —
*when* dose lands relative to the BG trajectory peak, not *how much*.

This narrowing is itself useful for AID authors: telling them
"increase correction dose under hyperglycaemia" is contraindicated by
this evidence (Loop already does that and loses). The actionable
guidance is now "review the dose-trajectory alignment of your
correction loop," not "raise correction sensitivity."
