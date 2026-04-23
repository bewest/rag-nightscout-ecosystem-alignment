# EXP-2947 — hypo-side IOB decay timing

**Date**: 2026-04-23
**Audience**: AID code authors

## Scope

Tests whether the EXP-2944/2946 timing mechanism extends to hypo
prevention. Anchor: BG crosses 80 from above, prior 30 min all
>80, no carbs ±60 min. 60 min forward and backward window.

## What this is NOT

- Not therapy advice. Hypo characterisation for design-feature analysis.

## Result (5 205 carb-isolated descend events)

| Design       |   n  | iob_at_entry | iob_decay_pre60 | iob_decay_fwd60 | bg_min_60 | tbr_70 | tbr_54 | basal_cut_frac |
|--------------|-----:|-------------:|----------------:|----------------:|----------:|-------:|-------:|---------------:|
| Loop_AB_OFF  |  606 |    0.469     |    −1.180       |    −0.225       |   65.7    | 22.0%  |  5.3%  |   75.5%        |
| Loop_AB_ON   | 1442 |    0.373     |    **−1.452**   |    −0.530       |   63.2    | 28.2%  |  7.0%  | **96.1%**      |
| oref0        |  835 |    0.272     |    −0.375       |    −0.256       |   54.9    | 29.2%  | 17.0%  |   52.8%        |
| oref1        | 2322 |  **0.564**   |    −0.537       |    −0.242       |   67.3    | 19.1%  |  3.2%  |   91.1%        |

### Counter-intuitive Loop_AB_ON pattern

Loop_AB_ON arrives at the descend event with LESS IOB (0.373 vs
0.564), has shed MORE IOB in the prior 60 min (−1.452 vs −0.537),
and cuts basal in MORE cells (96.1% vs 91.1%) — yet lands in
DEEPER hypo (bg_min 63.2 vs 67.3, tbr_54 7.0% vs 3.2% — 2× more
severe).

Loop's reactive cutting is too late. It is winning the race to
shed IOB but losing the BG outcome. oref1 has more IOB at entry
but it is "stale" (post-peak action; decaying gracefully). Loop's
IOB at entry is "fresh" (recently delivered from prior SMBs and
still actively driving down).

### oref0 outlier — confirms timing framework

oref0 has the lowest iob_at_entry (0.27) AND the deepest hypo
(bg_min 54.9, tbr_54 17% — 5× oref1). Lowest basal-cut fraction
(52.8%) reflects coarser actuation. The IOB-stale framework
predicts: oref0 also has IOB still acting but cannot brake fast
enough (latency from EXP-2918: median 10 min).

### Pareto-dominance reconfirmed at hypo granularity

oref1 BOTH higher TIR (EXP-2925) AND lower TBR-54 (here, 3.2%
vs Loop_AB_ON 7.0%, oref0 17.0%). No hypo trade for the IOB-timing
advantage.

## Mechanism interpretation — IOB age, not IOB magnitude

The timing framework needed an extension. EXP-2944/2946 measured
IOB-magnitude-vs-window-position. EXP-2947 reveals **IOB age** as
the deeper mechanism:

- **Fresh IOB** (recently delivered, pre-peak action) is a hypo risk
  even when total IOB is small.
- **Stale IOB** (post-peak action, gracefully decaying) is a hypo
  buffer.
- Loop's reactive SMB pattern keeps IOB fresh; oref1's predictive
  pattern lets IOB age before it is needed.

This unifies all three windows under a single framework:

| Window           | Outcome  | Mechanism                                                  |
|------------------|----------|------------------------------------------------------------|
| Sustained-high   | Recovery | Fresh IOB *during* window (oref1 pre-loaded; peaking now)  |
| Post-prandial    | TIR      | IOB peak ahead of BG peak (oref1 −55 min vs Loop −35 min)  |
| Hypo descent     | TBR      | Stale IOB *at* event (oref1 IOB-aged; Loop fresh-IOB-driven) |

oref1's predict-and-fire pattern produces fresh IOB during BG rise
windows AND aged IOB during BG descent windows. Loop's react-to-BG
pattern produces fresh IOB during BG descent (still acting,
deepening hypo) AND climbing IOB during sustained-high (not yet
acting, missing recovery).

## Carry-forward invariants

- **IOB age — not just IOB magnitude — is the timing lever.** The
  same IOB value can be a buffer (stale) or a hazard (fresh).
- **More aggressive basal cutting does not compensate for fresh
  IOB.** Loop_AB_ON cuts basal in 96% of pre-event cells and still
  has 2× the severe-hypo rate of oref1 (91% basal cuts).
- **Pareto-dominance reconfirmed** at hypo-event granularity; no
  free lunch question is closed at this finer resolution too.

## Updated AID-author lever (refined — UNIFIED)

**Predict-and-fire on rising velocity early; let IOB age before
the BG response window so that during BG rise it is acting, and
during BG descent it is buffer rather than driver.**

This is a single design principle that flows through all three
windows. It distinguishes oref1 from Loop_AB_ON and explains
both offence and defence advantages without invoking separate
mechanisms.

## Artefacts

- `tools/cgmencode/exp_hypo_iob_decay_2947.py`
- `externals/experiments/exp-2947_summary.json` (gitignored)
