# EXP-2946 — IOB-timing mechanism in post-prandial windows

**Date**: 2026-04-23
**Audience**: AID code authors (PP-window cross-validation)

## Scope

Cross-validates the EXP-2944 IOB-timing mechanism in 180-min
post-prandial windows (≥20 g carbs, 3-h quiet-pre, no overlap).
Tests whether the same lever explains the PP TIR gap (EXP-2929
showed autobolus closes 53% of Loop→oref1 PP gap; +21 pp residual).

## What this is NOT

- Not therapy advice. Insulin dose-per-gram differences reflect
  algorithm policy + per-patient settings, not a quality ranking.
- Not a meal-bolus calculator comparison.

## Result

**2 507 quiet-pre meals across 19 patients.**

| Design       |   n  | carbs | iob_peak | iob_peak_min | iob_delta_60 | bg_peak | TIR    |
|--------------|-----:|------:|---------:|-------------:|-------------:|--------:|-------:|
| Loop_AB_OFF  |  170 | 49.0  |  12.77   |     5        |    +6.73     |  273    | 39.7%  |
| Loop_AB_ON   |  697 | 37.9  |   9.01   |    20        |    +5.40     |  229    | 58.9%  |
| oref0        |  622 | 41.5  |   3.45   |    10        |    +1.75     |  199    | 69.1%  |
| oref1        | 1018 | 56.6  |   4.49   |    20        |    +1.85     |  187    | 80.3%  |

### Loop_AB_ON vs oref1 head-to-head (the +21 pp PP TIR gap)

| Measure              | Loop_AB_ON | oref1   | Δ      |
|----------------------|-----------:|--------:|-------:|
| iob_start            |    1.405   |  1.434  | −0.029 |
| **iob_peak**         | **9.01**   | **4.49**|**+4.51**|
| **iob_delta_60**     | **+5.40**  |**+1.85**|**+3.55**|
| iob_peak_min         |   20       |  20     |  0     |
| **iob_at_bg_peak**   | **6.43**   | **3.28**|**+3.16**|
| bg_peak              |  229       | 187     |  +42   |
| **iob_lead_bg_min**  | **−35**    | **−55** | **+20**|
| TIR                  |   58.9%    |  80.3%  | −21.4% |

### Within-design TIR by iob_delta_60 tertile

| Design     | lo Δ60        | mid Δ60       | hi Δ60        |
|------------|---------------|---------------|---------------|
| Loop_AB_ON | 0.606 (+1.55) | 0.549 (+4.68) | 0.612 (+9.97) |
| oref1      | 0.797 (−0.39) | 0.804 (+1.24) | 0.809 (+5.14) |

Within neither design does total IOB delivered in 0–60 min PP affect
TIR. **More insulin doesn't help** — within-design.

## Mechanism interpretation

Two distinct PP signals separate from sustained-high (EXP-2944):

1. **Insulin-per-gram gap.** Loop_AB_ON 0.24 U/g, oref1 0.08 U/g —
   3× difference in dose density. Loop uses much more insulin yet
   reaches higher BG peak (229 vs 187 mg/dL). Reflects bolus-calc
   policy + standing CR/ISF tuning, not closed-loop sensitivity per
   se.

2. **IOB-vs-BG-peak lead.** oref1 IOB peaks 55 min BEFORE BG peak;
   Loop_AB_ON only 35 min. The 20-min extra "head start" lets oref1's
   IOB act on the rising BG slope before peak. iob_at_bg_peak is
   therefore CLOSER to oref1's iob_peak (3.28 / 4.49 = 73%) than for
   Loop (6.43 / 9.01 = 71%) — so the lead doesn't translate to a
   peak-IOB-utilisation advantage. The lead is the timing lever.

The within-design tertile flatness confirms: **dose magnitude
within a given algorithm policy is exhausted as a lever**. The
gap is between policies, not within them.

## Cross-window mechanism comparison

| Window           | EXP   | Mechanism                                     |
|------------------|-------|-----------------------------------------------|
| Sustained-high   | 2944  | iob_delta during window: Loop +0.59 (climbing); oref1 −0.04 (peaking). Same iob_start. |
| Post-prandial    | 2946  | iob-peak-relative-to-bg-peak lead: Loop −35 min, oref1 −55 min. Different iob_peak (Loop 2× higher). |

**Common theme: TIMING of IOB delivery relative to BG response.**
Different operationalisation:
- Sustained-high: front-loaded so IOB is acting (not climbing) during
  the 60-min recovery window.
- Post-prandial: IOB peak occurs 55 min before BG peak (vs 35 for
  Loop), giving the dose more time to act on the rising slope.

## oref0 pattern — different from sustained-high

In PP windows, oref0 (TIR 69.1%) sits CLOSER to oref1 (80.3%) than
to Loop_AB_ON (58.9%). Opposite of sustained-high where oref0 (30%)
matched Loop_AB_OFF (30%).

Reading: in PP windows the **bolus-calc + basal channel** dominates
(both available to oref0), and the absent SMB-as-correction is
secondary. In sustained-high (carb-isolated) windows the SMB-as-
correction channel is essential and oref0's absence puts it at the
no-SMB floor.

This further weakens any simple "selection bias" interpretation —
oref0 patients shift relative position based on which channel is
controlling, exactly as algorithm-mechanism predicts.

## Three-tier mechanism stack — extended

| Window           | Tier 1 (channel)           | Tier 2 (timing)              | Tier 3 (dose policy)       |
|------------------|----------------------------|------------------------------|----------------------------|
| Sustained-high   | SMB-as-correction present  | IOB front-loaded; peaking during window | (subsumed in tier 2) |
| Post-prandial    | bolus-calc + basal cut     | IOB-peak lead BG-peak by ≥50 min | dose-per-gram policy (3× spread Loop vs oref1) |

## AID-author levers (consolidated, post EXP-2946)

1. **UAM/glucose-appearance + dynamic-ISF** (PP offence; channel + timing)
2. **SMB-as-correction during sustained-high** (channel for recovery)
3. **Predict-and-fire on rising velocity** for IOB peak 50+ min
   ahead of BG peak (PP) and within 20–25 min of high crossing
   (sustained-high) — UNIFIED TIMING LEVER
4. Enable autobolus by default for AID-OFF correction loops
5. Basal-cut latency (defence-side temporal)

The dose-per-gram gap (3× Loop vs oref1) is informational but NOT
recommended as a tunable: it's the result of integrated bolus-calc +
absorption-model + ISF tuning policy, and within-design dose
tertile is flat. AID authors should not "make oref1 dose more like
Loop" or vice versa as an isolated change.

## Carry-forward invariants

- **Timing > magnitude** for both PP and sustained-high recovery.
- **oref0 channel-positioning shifts by window class** — natural
  cross-window control supporting algorithm-channel framework.
- Within-design dose tertile is flat in PP (and EXP-2944 IOB tertile
  is flat for Loop in sustained-high). Magnitude is exhausted as a
  within-design lever.

## Artefacts

- `tools/cgmencode/exp_pp_iob_timing_2946.py`
- `externals/experiments/exp-2946_summary.json` (gitignored)
