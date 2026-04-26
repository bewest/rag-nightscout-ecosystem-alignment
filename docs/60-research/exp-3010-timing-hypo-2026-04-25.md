# EXP-3010 — Timing-axis hypo-redistribution check (CORRECTS EXP-3009) (2026-04-25)

**Branch**: `autoresearch/2026-04-24-cf-replay`
**Code**: `tools/cgmencode/autoresearch_cf/exp_3010_timing_hypo.py`
**Inputs**: `externals/experiments/exp-3007_ascent_events.parquet`

## Why this experiment exists

EXP-3009 claimed earlier-firing was a strict-Pareto improvement (overshoot ↓, no hypo penalty) because *total insulin units are unchanged*. EXP-3010 tests that assumption honestly by integrating the kernel over a 120-min post-peak look-ahead window. **The Pareto claim does not survive the honest accounting.**

## Method

For each ascent event with timing offset T:

```
cf_trough = cf_peak − [kernel(t_peak + W) − kernel(t_peak)] × smb × isf
```

with `t_peak = duration_min/2 + T` (time-from-shifted-delivery to peak) and W ∈ {60, 120} min. Hypo flagged if `cf_trough < 70 mg/dL`. **No EGP/carb-continued-absorption modelled** → this is a *worst-case* trough proxy; absolute levels are upper bounds, but offset-delta is informative.

## Results — W = 120 min

| Controller | Δoversht 0→30 min | Δhypo 0→30 min | trade ratio | verdict |
|---|---:|---:|---:|---|
| **Loop**    | **−5.0 pp** | **+3.68 pp** | 1 : 0.74 | **unsafe** (>1% gate) |
| **Trio**    | **−6.7 pp** | **+4.80 pp** | 1 : 0.72 | **unsafe** (>1% gate) |
| OpenAPS | −0.09 pp | +0.15 pp | — | safe (no SMB to retime) |

## Headline correction

> **EXP-3009 was wrong about "no hypo penalty".** Earlier-firing redistributes the kernel mass into the post-peak window, deepening the trough by ~70-75 % of the overshoot reduction. The trade ratio is approximately **1 pp overshoot prevented per 0.7 pp hypo created** for both Loop and Trio.

The claim that timing alone is a strict-Pareto lever is **rejected**.

## What survives

The *direction* of EXP-3009 is still useful — timing IS a real lever — but it has a comparable safety cost to magnitude. The lever choice question becomes:

- If the patient's hypo cost is HIGH (severe-hypo recent history, hypoglycaemia unawareness): no offset > 0 passes the 1% gate; status quo is optimal.
- If the patient's hypo cost is LOW relative to overshoot harm (HbA1c-driven, microvascular-risk-dominant): a +30 min offset trades 5 pp overshoot for 3.7 pp mild hypo — defensible.

This is fundamentally a **patient-level utility tradeoff**, not a controller-design free lunch.

## Important caveat on absolute levels

Baseline hypo rates at offset=0 are high under our worst-case proxy:

| Controller | hypo @0min | mean BG-trough proxy at 1st percentile |
|---|---:|---:|
| Loop | 4.76 % | 19.1 mg/dL |
| Trio | 8.75 % | 4.3 mg/dL |

These are clearly upper bounds — real hypo from CGM is much lower because:
1. We assume bg_peak − full kernel effect with **no EGP, no continuing carb absorption**, and
2. We compute the trough from the kernel's full *additional* drop over [peak, peak+120], even though the carbs that drove the ascent are still absorbing in that window.

The **deltas** (Δhypo with T) are reliable; **absolute levels** are over-stated by a substantial but unmeasured factor. A future EXP-3011 should integrate carb-absorption into the trough model to get realistic absolutes.

## Verdict
**`timing_axis_pareto_claim_rejected_with_useful_remainder`** — timing is still a lever, but with a 1:0.7 trade ratio comparable to magnitude. EXP-3009's commit message and report should be read with this correction in mind. The actionable Loop recommendation (lower the AB sliding-scale BG threshold) holds *only for patients with explicit high-overshoot/low-hypo cost tradeoffs*, not as a universal improvement.

## Next phase
EXP-3011 should joint-optimise timing × magnitude on a 2-D grid with the corrected hypo accounting, producing per-controller Pareto frontiers and a recommended (T, M) point for each.

## Deliverables
```
tools/cgmencode/autoresearch_cf/exp_3010_timing_hypo.py
externals/experiments/exp-3010_timing_hypo.parquet      (gitignored)
externals/experiments/exp-3010_summary.json             (gitignored)
docs/60-research/figures/exp-3010_timing_hypo.png
```

## Self-correcting-research note

This experiment is a *load-bearing* example of the autoresearch program working as intended: EXP-3009 made a clean claim, EXP-3010 checked the load-bearing assumption (zero hypo penalty), found it false, and the program updates its conclusion. The git history preserves both the original (over-)claim and the correction; readers should consult both.
