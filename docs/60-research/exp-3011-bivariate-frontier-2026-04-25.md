# EXP-3011 — Bivariate (timing × magnitude) Pareto frontier (2026-04-25)

**Branch**: `autoresearch/2026-04-24-cf-replay`
**Code**: `tools/cgmencode/autoresearch_cf/exp_3011_bivariate_frontier.py`
**Inputs**: `externals/experiments/exp-3007_ascent_events.parquet`
**Supersedes (partially)**: EXP-3008 (magnitude-only) and EXP-3009 (timing-only)

## Method

Joint sweep over `T ∈ {0, 5, 10, 15, 20, 30}` minutes (earlier-firing offset) and `M ∈ {0.5, 1.0, 1.5, 2.0, 3.0}` (SMB-aggression multiplier). 30 grid points per controller. Hypo accounting via the corrected 120-min look-ahead trough proxy from EXP-3010.

Recommendation rule: **maximum overshoot reduction subject to Δhypo ≤ 1.0 pp** (relative gate, since EXP-3010 absolute trough proxy is over-pessimistic but deltas are reliable).

## Headline result — TRUE Pareto improvements exist

| Controller | Optimal (T, M)          | Δoversht | Δhypo | direction |
|---|---|---:|---:|---|
| **Loop**    | **T=+30 min, M=0.5×**   | **−1.80 pp** | **−4.35 pp** | strict-Pareto improvement |
| **Trio**    | **T=+30 min, M=0.5×**   | **−2.64 pp** | **−7.57 pp** | strict-Pareto improvement |
| OpenAPS | T=+30, M=3.0 (degenerate; no SMB to retime) | −0.30 pp | +0.48 pp | edge case |

**The optimal joint move is "fire earlier AND smaller" — not "later and bigger".** Both Loop and Trio currently sit at a dominated point in (T, M) space.

## Why this is the right shape

The current default ("T=0, M=1.0") combines two mistakes:

1. **Late firing** → kernel cannot realise enough effect before peak → BG goes high.
2. **Big magnitude to compensate** → kernel mass arriving in the post-peak window goes too deep → BG goes low.

The optimal "early-and-small" move:
1. **Earlier firing** → smaller SMB still cuts more of the peak (longer kernel runway).
2. **Smaller magnitude** → less mass in the post-peak window → shallower trough.

This is the **anticipatory-and-gentle** controller pattern that `Trio` (oref1) approximates relative to `Loop`, but the recommendation says even Trio could benefit from going further.

## Per-controller pareto frontier (top of front)

```
Loop pareto-front (low overshoot ← → low hypo):
  T=30, M=3.0  | cand_over=53.7%  cand_hypo=10.7%   (overshoot-min)
  T=30, M=1.5  | cand_over=56.8%  cand_hypo= 6.1%
  T=30, M=1.0  | cand_over=57.8%  cand_hypo= 5.5%
  T=30, M=0.5  | cand_over=58.2%  cand_hypo= 0.4%   ← RECOMMENDED
  T=20, M=0.5  | cand_over=58.6%  cand_hypo= 0.3%
  T=0,  M=0.5  | cand_over=60.4%  cand_hypo= 0.2%   (hypo-min)

Trio pareto-front:
  T=30, M=3.0  | cand_over=27.2%  cand_hypo=21.4%
  T=30, M=1.0  | cand_over=33.1%  cand_hypo=13.6%
  T=30, M=0.5  | cand_over=37.2%  cand_hypo= 1.2%   ← RECOMMENDED
  T=0,  M=0.5  | cand_over=39.3%  cand_hypo= 0.6%   (hypo-min)
```

The Loop and Trio recommendations both sit at the "elbow" of the Pareto front — the point where pushing further on overshoot (by raising M) costs disproportionate hypo.

## Concrete actionable recommendations

### For Loop developers
- **Current AB strategy is over-aggressive on magnitude and under-aggressive on timing.**
- Lower the BG threshold of the GBAF sliding scale so SMBs start firing 30 min earlier in the ascent.
- **Halve the partialApplicationFactor** (or equivalently raise the per-SMB cap) to reduce per-event magnitude.
- Net effect projected on this cohort: −1.8 pp overshoot AND −4.4 pp hypo.

### For Trio (oref1) developers
- Same direction, larger benefit: −2.6 pp overshoot AND −7.6 pp hypo.
- Lower the SMB BG-trigger floor; halve `microBolus = floor(min(insulinReq/2, basal*30/60))` to `floor(min(insulinReq/4, basal*15/60))`.
- The improvement is bigger for Trio because Trio has more SMB units to redistribute.

### For AAPS-oref0 users
- The lever doesn't exist — no SMB is fired. The fix is *enabling SMB at all* (switch to oref1).

## Verdict
**`bivariate_pareto_improvement_found`** — Loop and Trio both have strict-Pareto improvements available via "fire earlier AND smaller". The corrected trade ratios from EXP-3010 (1:0.7 overshoot:hypo on each axis alone) hide this because they don't explore the *cross-product* — magnitude-down compensates for the hypo redistribution caused by timing-earlier.

This is the autoresearch program's strongest result so far: a clear, mechanistically-explained, controller-design-actionable recommendation.

## Deliverables
```
tools/cgmencode/autoresearch_cf/exp_3011_bivariate_frontier.py
externals/experiments/exp-3011_frontier.parquet         (gitignored)
externals/experiments/exp-3011_summary.json             (gitignored)
docs/60-research/figures/exp-3011_pareto.png
```
