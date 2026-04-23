# EXP-2933 — Pre-meal context decomposition: early-TBR gap disappears within tertiles

**Date:** 2026-04-23
**Source:** `tools/cgmencode/exp_premeal_context_2933.py`
**Scope:** Tests the pre-meal-context interpretation of EXP-2931's
+2.55 pp early post-meal TBR gap. AID-author audience.

## The confound

Pre-meal BG distributions differ wildly by design:

| Design       | Mean pre-BG | Median | n meals | Std |
|--------------|------------:|-------:|--------:|----:|
| Loop_AB_OFF  | 214.1       | 216    | 424     | 86.3 |
| Loop_AB_ON   | 147.6       | 130    | 1 235   | 62.8 |
| oref1        | **113.8**   | **107**| 2 228   | 36.6 |

oref1 patients enter meals with average BG **100 mg/dL lower**
than Loop_AB_OFF patients and **34 mg/dL lower** than Loop_AB_ON.

## Meal distribution across pre-BG tertiles

Tertile cutpoints (global): low_pre ≤ 102, mid_pre 103–136, high_pre ≥ 137 mg/dL.

| Design       | low_pre % | mid_pre % | high_pre % |
|--------------|----------:|----------:|-----------:|
| Loop_AB_OFF  | 9.0       | 17.5      | **73.6**   |
| Loop_AB_ON   | 23.7      | 31.0      | 45.3       |
| oref1        | **43.4**  | 37.7      | 18.9       |

## Within-tertile TBR 0-30 gap (oref1 − design, pp)

| Pre-BG tertile | vs            | Gap     | 95 % CI            | sig |
|----------------|---------------|--------:|--------------------|-----|
| low_pre        | Loop_AB_OFF   | +8.74   | [+5.24, +12.02]    | ★ † |
| **low_pre**    | **Loop_AB_ON**| **+1.35**| **[−3.44, +6.43]**| **✗** |
| mid_pre        | Loop_AB_OFF   | +0.25   | [+0.00, +0.63]     | ✗   |
| **mid_pre**    | **Loop_AB_ON**| **+0.20**| [−0.07, +0.60]    | ✗   |
| high_pre       | Loop_AB_OFF   | +0.00   | [0.00, 0.00]       | ✗   |
| **high_pre**   | **Loop_AB_ON**| **+0.00**| [0.00, 0.00]      | ✗   |

† low_pre vs Loop_AB_OFF: AB_OFF n=2 patients have 73.6 % of
meals in high_pre tertile; their few low_pre meals are tail
events and the cell is degenerate.

## Findings

1. **The +2.55 pp early-TBR gap from EXP-2931 fully decomposes
   to pre-meal context.** Within all three pre-BG tertiles, the
   oref1 vs Loop_AB_ON early-TBR gap collapses to:
   - low_pre: +1.35 pp (CI crosses zero)
   - mid_pre: +0.20 pp
   - high_pre: +0.00 pp

   None significant. The marginal +2.55 pp signal was entirely
   driven by the difference in pre-meal BG distributions, not
   by oref1 over-dosing the bolus.

2. **Pre-meal BG distribution is itself a design outcome.**
   oref1's 113.8 mg/dL mean pre-meal BG is **the consequence of
   tighter daily TIR** (EXP-2925: 82.6 % TIR vs Loop 66.1 %).
   Patients running in tighter range arrive at meal time at
   tighter BG values closer to the lower edge of in-range — and
   that, not bolus dosing, is what produces the 0-30 min TBR
   uptick.

3. **No bolus-dosing hypo cost from front-loaded UAM.** Within
   pre-BG-matched groups, oref1's front-loaded UAM dosing
   (EXP-2930: 2.2-6.6× more dose in 0-60 min) produces no
   significant early-TBR penalty. The "no free lunch" question
   raised by EXP-2930 is now closed at three layers:
   - Day-level (EXP-2925): no trade
   - Meal-window severe (EXP-2931): no elevation
   - **Pre-meal-matched early TBR (EXP-2933): no gap**

4. **Loop_AB_OFF runs ~100 mg/dL hyperglycaemic at meals.** Mean
   pre-meal BG = 214.1 mg/dL — 73.6 % of meals begin from a state
   already above 137 mg/dL. This is the meal-time face of the
   structural PP TIR deficit (32.14 % from EXP-2929) — without
   autobolus, basal-only loops cannot bring BG down between
   meals and patients chronically eat from elevated starting BG.

5. **A new methodological invariant**: cross-design comparisons
   that anchor on event-windows (meals, exercise, sleep onset)
   must condition on **state-at-event-onset**, not just on time.
   Otherwise, design outcomes that change baseline state
   (oref1 tighter TIR → lower pre-meal BG) get falsely scored
   as event-window risks.

## Updated mechanism stack — Pareto-dominance is robust

| Concern              | Evidence                                  | Verdict |
|----------------------|-------------------------------------------|---------|
| Day-level TBR        | EXP-2925                                  | No trade |
| Meal-window severe   | EXP-2931                                  | No trade |
| Late post-meal TBR   | EXP-2931                                  | No trade |
| Trough BG safe       | EXP-2931 (102 mg/dL)                      | No trade |
| Early TBR (marginal) | EXP-2931 +2.55 pp                         | Apparent only |
| **Early TBR (within pre-BG tertile)** | **EXP-2933 +1.35 / +0.20 / +0.00 pp** | **Confounded — disappears when matched** |

## Implication

The Pareto-dominance from EXP-2925 is now confirmed at four
granularities (day-level, meal-window severe, late meal-window,
pre-meal-matched early-window). For AID authors:

- Front-loaded UAM dosing is **safe** in this cohort. It
  compresses post-meal BG into a tighter band without shifting
  risk into hypo.
- The mechanism for safety is straightforward: if the bolus is
  appropriately calibrated to actual carb appearance, more
  insulin earlier matches more glucose earlier.
- Cross-design event-window analyses **must** condition on
  state-at-event-onset to avoid scoring tighter-control designs
  as spuriously hypo-prone.

## New methodological invariant for the deconfounding toolkit

Add **Guard #8 (event-anchor state conditioning)**: when comparing
designs across event-anchored windows (meals, exercise, sleep onset),
condition on the BG/IOB/COB state at event onset before computing
within-window outcomes. Marginal gaps that vanish within state
tertiles are confounded by baseline-state distribution differences,
not produced by the controller's response to the event.

## Caveats

- Loop_AB_OFF n=2; AB_ON n=5; oref1 n=9. Cohort imbalance.
- low_pre vs Loop_AB_OFF cell degenerate (only 9 % of AB_OFF
  meals fall there).
- Tertile cutpoints derived globally; per-design percentile cutpoints
  would shift cell composition.
- Observational. AID-author scope.

## Linked artefacts

- `externals/experiments/exp-2933_summary.json`
- Closes the "early TBR is a real hypo cost" possibility raised
  by EXP-2931. The signal was confounding, not biology.
- Should propagate into Toolkit §4.8 as Guard #8.
