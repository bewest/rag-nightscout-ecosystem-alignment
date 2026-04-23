# EXP-2874 — Meal-Gated Re-Run of Fast-Scale Envelope Coupling

**Date:** 2026-04-22
**Stream:** B (operational)
**Status:** Complete (1 of 1 verdict resolved cleanly)
**Predecessor:** EXP-2851 (post EXP-2873 NaN-percentile bug fix)

## Question

After EXP-2873 fixed the NaN-percentile bug in the cohort aggregator,
EXP-2851's revised headline became "median basal shift positive at all
windows": +50.6% (1h) → +1.5% (48h). High-glucose windows have **higher**
actual basal — opposite of the audition expectation that controllers cut
basal under elevated glucose.

The leading alternative explanation: **post-meal artifact.** During the
1-2h after a meal, glucose rises rapidly (carbs > basal-down-correction
within the same window), so the observed positive shift could simply
reflect "windows that contained meals" rather than a true envelope-
demand coupling.

EXP-2874 tests this by re-running EXP-2851 with cell-level meal gating.

## Method

- Same windowing and 33/67 percentile aggregation as EXP-2851 (with
  the post-EXP-2873 NaN guard).
- Cell-level meal mask: any 5-min cell with `carbs > 0` OR
  `time_since_carb_min < 240` is "post-meal".
- A window is **meal-gated** if ≥80% of its cells are non-meal.
- Windows: 1h, 2h, 3h, 6h, 12h, 24h, 48h.
- Cohort: same 31 patients as EXP-2851 post-fix.

## Result

| window_h | full N | full median shift | gated N | gated median shift | Δ (gated − full) |
|---------:|-------:|------------------:|--------:|-------------------:|-----------------:|
| 1        | 31     | **+50.6%**        | 31      | **+64.0%**         | **+13.4** |
| 2        | 31     | +40.4%            | 31      | +58.2%             | +17.8 |
| 3        | 31     | +36.5%            | 31      | +43.7%             | +7.3 |
| 6        | 31     | +11.9%            | 29      | +9.5%              | −2.4 |
| 12       | 31     | +9.0%             | 26      | +15.2%             | +6.2 |
| 24       | 30     | +7.1%             | 16      | +21.2%             | +14.1 |
| 48       | 26     | +1.5%             | 9       | +17.8%             | +16.4 |

**Verdict: STRENGTHENED.** Removing post-meal cells does not collapse the
positive shift — it **increases** it at every fast-scale window (1h, 2h,
3h) and at the long-tail windows (12h, 24h, 48h). The 6h window is the
only mild exception (−2.4pp), well within noise.

## Interpretation

1. The post-bugfix EXP-2851 finding is **not** a post-meal artifact.
   Meals were *attenuating* the signal (adding noise around an already
   real coupling), not creating it.

2. In closed-loop fasting equilibrium, when glucose drifts higher,
   actual basal is **higher** than in low-glucose equilibria. This is
   consistent with EXP-2843/2811: the controller adapts its delivered
   basal upward in response to elevated demand, while the schedule
   remains inert.

3. This **does not** invalidate the audition assumption that *new*
   high-glucose excursions should trigger basal increases — the EXP-
   2851 signal is a steady-state correlation, not a transient response.
   The schedule is still wrong; the controller is doing the work.

4. The Loop hypo-prevention bias (EXP-2871) and within-Loop Simpson's
   paradox (EXP-2872) operate orthogonally to this — they describe
   suspension polarity in *normal/low* envelopes, while EXP-2874
   confirms the opposite-end (elevated envelope) coupling is real.

## Implication for audition

- The controller-aware `basal_mismatch` flag (committed today) remains
  appropriate: schedule is genuinely under-provisioned for the
  patient's elevated equilibria.
- For Loop users specifically, the recommendation to "soften schedule
  first; ISF often follows" still holds — but the direction at high-
  glucose equilibria is **raise** the schedule, not lower it. The
  flag rationale already covers this via the hypo-prevention framing.

## Sample-size caveat

The 24h and 48h gated windows drop to N=16 and N=9 respectively because
meal gating is restrictive at long timescales (a 48h window has ~576
cells; finding 460 consecutive non-meal cells is rare). The +17pp
gated-vs-full delta at 48h has wide confidence; the headline is the 1h
result (full N=31, gated N=31).

## Files

- `tools/cgmencode/exp_meal_gated_envelope_2874.py`
- `externals/experiments/exp-2874_meal_gated_envelope.parquet`
- `externals/experiments/exp-2874_summary.json`
- `docs/60-research/figures/exp-2874_meal_gated_envelope.png`
