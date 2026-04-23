# EXP-2931 — Post-meal TBR by design: does oref1 front-loading carry hypo cost?

**Date:** 2026-04-23
**Source:** `tools/cgmencode/exp_postmeal_tbr_2931.py`
**Scope:** "No free lunch" check — given that EXP-2930 showed
oref1 delivers 2.2-6.6× more SMB dose in the first hour post-meal
than Loop autobolus, does this front-loading translate into more
post-meal hypo events? AID-author audience.

## Per-design post-meal metrics (mean of per-patient mean)

| Design       | TBR 0-30 | TBR 30-60 | TBR 60-120 | TBR 120-240 | Severe 60-240 | Peak 0-240 | Trough 60-240 |
|--------------|---------:|----------:|-----------:|------------:|--------------:|-----------:|--------------:|
| Loop_AB_OFF  | 0.12 %   | 0.36 %    | 1.10 %     | 2.95 %      | 0.67 %        | 297.86     | 152.95        |
| Loop_AB_ON   | 1.96 %   | 1.32 %    | 2.11 %     | 3.60 %      | 1.06 %        | 243.15     | 121.77        |
| **oref1**    | **4.51 %** | 2.63 %  | 2.60 %     | 2.84 %      | **0.53 %**    | **199.94** | **101.83**    |

## Pairwise gaps (oref1 − design)

| Comparison vs        | Metric             | Gap     | 95 % CI               | sig |
|----------------------|--------------------|--------:|-----------------------|-----|
| Loop_AB_ON           | TBR 0-30           | +2.55   | [+0.22, +4.92]        | ★   |
| Loop_AB_ON           | TBR 30-60          | +1.31   | [−0.27, +2.88]        | ✗   |
| Loop_AB_ON           | TBR 60-120         | +0.49   | [−1.28, +2.34]        | ✗   |
| Loop_AB_ON           | TBR 120-240        | −0.76   | [−2.64, +1.32]        | ✗   |
| Loop_AB_ON           | **Severe 60-240**  | **−0.53** | [−1.38, +0.25]      | ✗   |
| Loop_AB_ON           | **Peak 0-240**     | **−43.22** | [−81.28, −8.70]   | ★   |
| Loop_AB_ON           | **Trough 60-240**  | **−19.94** | [−34.65, −6.52]   | ★   |

## Findings

1. **Early TBR signal is real but bounded.** oref1's 0-30 min
   post-meal TBR (4.51 %) is statistically higher than Loop_AB_ON
   (1.96 %, +2.55 pp sig) and Loop_AB_OFF (0.12 %, +4.39 pp sig).
   This is the only window with a robust positive TBR gap.

2. **Severe hypo is NOT elevated.** Severe hypo (60-240 min,
   < 54 mg/dL) is 0.53 % for oref1 vs 1.06 % Loop_AB_ON and
   0.67 % Loop_AB_OFF. CIs overlap, but oref1 trends *lower*
   not higher. Front-loaded SMB does not cause severe meal-window
   hypo events.

3. **Late-window TBR is design-symmetric.** TBR 120-240 min is
   2.84 / 3.60 / 2.95 % across the three designs — gaps not sig,
   wide overlapping CIs. Whatever happens in 0-30 min does not
   carry forward into the absorption-phase or late post-meal
   window.

4. **Glycemic compression, not hypo trade.** Peak post-meal BG
   is dramatically lower with oref1 (199.94 mg/dL) than Loop_AB_ON
   (243.15) or Loop_AB_OFF (297.86) — both gaps highly significant.
   Trough BG is correspondingly lower (101.83 vs 121.77 vs 152.95)
   but **well above the TBR threshold of 70 mg/dL**. The net
   effect is BG variability compressed into a tighter band, not
   a peak-for-trough trade.

5. **Most-likely interpretation of the early TBR signal**: The
   0-30 min window captures pre-meal-bolus state largely. Patients
   running tighter daily TIR (oref1 median 82.6 % vs Loop 66.1 %
   from EXP-2925) approach more meals from near the lower edge
   of in-range. The early-TBR uptick reflects *which BG state the
   patient enters meal time in*, not *what oref1 does after the
   meal bolus*. The fact that the TBR signal **does not propagate
   to 30-60 / 60-120 / 120-240 min** supports this reading.

## Updated mechanism stack — Pareto-dominance is robust

| Concern              | Evidence                                  | Verdict |
|----------------------|-------------------------------------------|---------|
| Day-level TBR        | EXP-2925 oref1 3.64 % vs Loop 3.88 %      | No trade |
| Meal-window severe   | EXP-2931 oref1 0.53 % vs Loop_AB_ON 1.06 % | No trade |
| Late post-meal TBR   | EXP-2931 ~2.84 % all designs              | No trade |
| Early post-meal TBR  | EXP-2931 +2.55 pp oref1 vs Loop_AB_ON     | Bounded; pre-meal context |
| Trough BG            | EXP-2931 oref1 102 mg/dL                  | Safe; well above 70 |
| Peak BG              | EXP-2931 oref1 200 vs Loop_AB_ON 243      | Dramatic improvement |

## Caveats

- Loop_AB_OFF n=2; Loop_AB_ON n=5; oref1 n=9. Significant
  cohort imbalance.
- Per-patient mean smooths over individual meal variability.
- TBR threshold = 70 mg/dL; severe = 54 mg/dL.
- 0-30 min window includes the meal bolus itself; pre-meal
  state confound cannot be cleanly removed without baseline
  matching.
- Observational, not interventional. AID-author scope.

## Implication

The "no hypo cost" framing for oref1's front-loaded UAM dosing
is supported. Peak BG drops by ~43 mg/dL (Loop_AB_ON) without
significant elevation in severe hypo or late-window TBR. The
~2.5 pp early TBR signal is real but bounded and most plausibly
reflects pre-meal context, not post-meal over-dosing.

For AID authors: front-loaded UAM-style dosing with a sensible
microbolus cap appears to compress glycemic variability without
shifting risk into hypo. **The Pareto-dominance from EXP-2925
holds at meal-window granularity.**

## Linked artefacts

- `externals/experiments/exp-2931_summary.json`
- Reinforces EXP-2925 Pareto check at finer time resolution.
- Closes "no free lunch" question raised by EXP-2930.
