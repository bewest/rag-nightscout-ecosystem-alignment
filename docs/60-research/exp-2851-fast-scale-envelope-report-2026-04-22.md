# EXP-2851 — Fast-scale envelope dissolution (2026-04-22)

## Question
EXP-2849 established envelope→basal coupling at 6–48h windows. Does
this signal extend down to 1–3h (fast, reactive-loop scale), or does
it dissolve into AR(1) noise per the dual-timescale architecture?

## Method
Same as EXP-2849 (per-patient top-tertile vs bottom-tertile glucose
envelope, non-overlapping windows, Mann-Whitney U on `actual_basal_rate`)
extended to windows = [1, 2, 3, 6, 12, 24, 48] h. Patient qualifies
at each window only if enough contiguous filled cells exist for ≥6
non-overlapping windows (hence N varies by window).

## Result — Checks: **2/4 PASS**

| window_h | N | frac_sig_p<0.01 | median shift % |
|---------:|--:|----------------:|---------------:|
| 1 | 4 | 1.000 | −44.2 |
| 2 | 7 | 0.714 | −48.4 |
| 3 | 8 | 0.750 | −28.2 |
| 6 | 11 | 0.818 | −35.7 |
| 12 | 13 | 0.462 | −17.6 |
| 24 | 25 | 0.280 | +8.7 |
| 48 | 22 | 0.227 | +1.5 |

**The sign flips between 12h and 24h.**

## Interpretation
Hypothesis **refuted**: the envelope signal does NOT dissolve at 1h.
But it means something **qualitatively different** at short vs long
scales:

- **1–12h (reactive-loop regime)**: basal is systematically
  **lower** in elevated-glucose windows (median −30 to −48%). This
  is the controller's **suspension during highs** — it stacks IOB
  from SMBs/corrections, expects a drop, and withholds basal.
  Highly significant in short-window qualifiers because it is a
  dominant tactical behavior.

- **24–48h (envelope regime)**: basal is slightly **higher** in
  elevated-demand windows (+1 to +9%). This is the envelope-demand
  coupling that EXP-2843 / EXP-2810 validated (77% patients, p<0.001,
  median 18% shift at 48h).

- **12h is the crossover**: neither regime dominates; signal is
  neutral and weak.

## Implication for audition matrix
The 48h audition window choice is NOT arbitrary — it is the regime
where **envelope demand** dominates over **tactical suspension**.
Shorter audition cycles would invert the signal meaning and
mislead clinicians.

## Implication for multi-scale modeling
This is a **natural demonstration of the dual-timescale / two-
stream architecture**:
- Short scales = Stream A reactive loop (intervention artifacts)
- Long scales = Stream B envelope physics (demand signal)
- The sign-flip is the observational fingerprint of the boundary

## Caveats
- N is very small at 1h (4 patients) because of the contiguous-
  window requirement. Treat 1h numbers as directional only.
- Shifts are % of the low-envelope basal; a patient with near-zero
  basal in the low envelope yields large % even with small deltas.
- This does NOT revise Stream A ceiling claims (EXP-2841); it
  clarifies that short-scale basal variance IS recoverable but
  encodes different information.

## Artifacts
- `externals/experiments/exp-2851_fast_scale_envelope.parquet`
- `externals/experiments/exp-2851_summary.json`
- `docs/60-research/figures/exp-2851_fast_scale_envelope.png`

---

## Addendum 2026-04-22: NaN-percentile bug fix (EXP-2873)

A `np.percentile` NaN-propagation bug silently excluded patients
with high glucose-NaN cell rates. Fix: dropna before percentile.
See `exp-2873-nan-percentile-bug-fix-report-2026-04-22.md`.

**New cohort summary (N grew from 25 → 31):**

| window_h | N | frac_sig p<0.01 | median shift % |
|--:|--:|--:|--:|
| 1 | 31 | 0.871 | **+50.6** |
| 2 | 31 | 0.806 | +40.4 |
| 3 | 31 | 0.774 | +36.4 |
| 6 | 31 | 0.645 | +11.9 |
| 12 | 31 | 0.516 | +9.0 |
| 24 | 30 | 0.300 | +7.1 |
| 48 | 26 | 0.231 | +1.5 |

**The sign-flip hypothesis is REFUTED**. Median shift is positive at
every window, decaying smoothly from +50% (1h) to +1% (48h). The old
"sign flip 12h → 24h" was an artifact of which patients qualified at
each window. The new picture: at fast scales the controller responds
proportionally (basal up when glucose elevated), and at long scales
the elev/norm basal averages converge — meaning the basal SCHEDULE
is roughly correct over multi-day spans. This is a much cleaner story
and is consistent with the dual-timescale architecture memory (5-min
AR(1) momentum dominates, hourly+ shows BGI/setting structure).
