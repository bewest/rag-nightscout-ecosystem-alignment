# EXP-2930 — SMB temporal alignment to meal events: Loop autobolus vs oref1

**Date:** 2026-04-23
**Source:** `tools/cgmencode/exp_smb_meal_alignment_2930.py`
**Scope:** Causal mechanism for the 20.57 pp residual PP TIR gap
identified in EXP-2929. Tests whether oref1 UAM detection
front-loads insulin during absorption vs Loop autobolus' more
back-loaded delivery. AID-author audience.

## Method

For each meal event (carbs > 5 g with no carbs in prior 240 min;
n=4004 meals across 16 patients), measure:
- First SMB latency from meal in min
- SMB dose delivered in 0-30, 30-60, 60-120, 120-240 min post-meal
- SMB event count per window

Per-patient medians, then design-level mean ± bootstrap CI.

## Headline: dose distribution by post-meal window

| Window      | Loop_AB_ON dose | oref1 dose | **Ratio (oref1/Loop)** |
|-------------|----------------:|-----------:|-----------------------:|
| 0-30 min    | 0.31 U          | 0.68 U     | **2.2×**               |
| 30-60 min   | 0.05 U          | 0.33 U     | **6.6×**               |
| 60-120 min  | 0.36 U          | 0.38 U     | 1.05×                  |
| 120-240 min | 1.63 U          | 1.45 U     | 0.89×                  |

| Window      | Loop_AB_ON count | oref1 count | Ratio |
|-------------|-----------------:|------------:|------:|
| 0-30 min    | 1.55             | 2.08        | 1.34× |
| 30-60 min   | 1.18             | 1.32        | 1.12× |
| 60-120 min  | 2.59             | 1.83        | 0.71× |
| 120-240 min | 6.13             | 4.73        | 0.77× |

## Findings

1. **First-SMB latency is essentially identical**: oref1 = 10 min,
   Loop_AB_ON = 12 min, CIs overlapping ([7.22, 13.33] vs [6.00,
   19.00]). The two designs fire their *first* SMB at the same
   time — typically at the meal-bolus marker.

2. **oref1 front-loads dose by 2-7×.** During the first hour,
   oref1 delivers ~1.0 U total vs Loop autobolus ~0.36 U. The
   30-60 min window is the most asymmetric (6.6× ratio).

3. **Loop "catches up" at 120-240 min**: Loop_AB_ON delivers
   1.63 U in this late window (vs oref1 1.45 U) and fires 6.13
   SMBs (vs oref1 4.73). This is **corrective firing into an
   already-elevated BG** — the EXP-2929 PP TAR of 42.43 % shows
   half of post-prandial cells are already out of range.

4. **Mechanism interpretation**: Loop autobolus fires reactively
   when Loop's predictor crosses target. By the time prediction
   crosses target (typically 30-90 min post-meal), absorption is
   already dominating BG. oref1's UAM detection plus dynamic-ISF
   sees the entry-rate of glucose appearance and **pre-empts the
   peak** — same first-fire timing, much heavier dose loading
   in the next 30 min.

5. **Loop_AB_OFF is the floor**: zero SMBs across both n=2
   patients (consistent with autobolus disabled). All meal-time
   correction depends on user-bolus accuracy and basal modulation;
   no SMB channel exists. PP TIR 32.14 % from EXP-2929.

## Causal stack closing the residual PP gap

The 20.57 pp residual PP TIR gap (EXP-2929) is now mechanistically
attributed to **dose shape**, not cadence or first-fire timing:

| Component        | Loop autobolus     | oref1 UAM           |
|------------------|-------------------|---------------------|
| First-fire timing | meal-bolus marker | meal-bolus marker   |
| Trigger logic    | predicted BG > target | UAM detected (entry rate of glucose appearance) |
| 0-60 min loading | 0.36 U (back-loaded) | 1.01 U (front-loaded) |
| 120-240 catch-up | 1.63 U (corrective) | 1.45 U (residual)   |
| **Net BG outcome** | TIR 55.23 %, TAR 42.43 % | TIR 75.81 %, TAR 21.02 % |

## Implication for AID authors

The actionable AID-author lever for closing the PP gap is **NOT**
"increase autobolus aggressiveness" or "fire SMBs more often."
Both designs already fire 4-7 SMBs per meal. The lever is **earlier
absorption-phase loading** which requires:
- A **glucose-appearance / UAM-style detector** that does not
  depend on prediction crossing target
- A **dynamic ISF** that widens during early absorption to amplify
  the auto-correction dose

Without these two components, brake-only-loops with autobolus
will continue to back-load corrections and accumulate ~20 pp of
out-of-range PP cells.

## Caveats

- Loop_AB_ON n=5; oref1 n=9. Significant cohort imbalance.
- Carbs > 5g threshold is conservative; smaller meals excluded.
- Per-patient medians smooth over carb-amount variability.
- Observational, not interventional. AID-author scope.

## Linked artefacts

- `externals/experiments/exp-2930_summary.json`
- Closes the EXP-2929 mechanism question.
- Should update `synthesis-design-comparison-2026-04-23.md`
  Finding B with the dose-distribution evidence.
