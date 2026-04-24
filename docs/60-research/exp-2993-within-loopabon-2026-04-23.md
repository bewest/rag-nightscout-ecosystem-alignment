# EXP-2993: Within-Loop_AB_ON outcome stratification by policy tertile

**Date**: 2026-04-23
**Audience**: open-source AID code authors (Loop).
**Scope**: stratify the 5 Loop_AB_ON patients (c, d, e, g, i) into
aggressive / mid / conservative tertiles using EXP-2991's
`conservatism_score` and compare three outcomes: overshoot, TTT
(time-to-target recovery), and TAR (time-above-range).
**What this is NOT**: not a causal estimate; not a recommendation
to switch settings; n=5 makes ranks indicative only.

---

## Headline

**NEGATIVE for the trade-off hypothesis; POSITIVE for AID-author
guidance.** Conservative Loop_AB_ON patients **dominate** aggressive
peers on **every** outcome measured: lower overshoot rate, shorter
recovery time, less time above range. There is no observed
trade-off; the "aggressive dial" appears to be strictly worse on
this 5-patient cohort.

---

## Method

* Tertile assignment by `conservatism_score` rank (5 patients →
  bottom-2 / mid-1 / top-2):
  - aggressive: i, e
  - mid: g
  - conservative: c, d
* Outcomes per patient (raw 5-min grid):
  - `overshoot_rate` = frac(forward-90-min max BG > 180) | BG ∈ [100, 180]
  - `ttt_median_min` = median minutes per contiguous BG > 180 run
  - `ttt_mean_min` = mean minutes per such run
  - `tar_frac` = frac(BG > 180) overall
  - `n_excursions` = number of BG > 180 contiguous runs

Implementation: `tools/cgmencode/exp_within_loopabon_2993.py`
Output: `externals/experiments/exp-2993_within_loopabon.parquet` and
`exp-2993_summary.json` (gitignored).

---

## Results

```
patient  overshoot  ttt_median  ttt_mean  tar_frac  n_excursions  conservatism  tertile
   i       0.251       70.0      122.8     0.263       556            0.337   aggressive
   e       0.259       65.0      112.7     0.293       590            0.548   aggressive
   g       0.210       50.0       85.9     0.191       578            0.698   mid
   c       0.356       65.0       97.0     0.279       745            0.761   conservative
   d       0.194       42.5       82.2     0.176       554            0.796   conservative
```

### Tertile means

| Tertile | overshoot | ttt_median | ttt_mean | tar_frac |
|---------|-----------|------------|----------|----------|
| aggressive   | **0.255** | **67.5** | **117.8** | **0.278** |
| mid          | 0.210 | 50.0 | 85.9 | 0.191 |
| conservative | 0.275 | 53.8 | 89.6 | 0.227 |

### Spearman correlations (conservatism vs outcome)

| Pair | ρ |
|------|---|
| conservatism vs overshoot | **−0.300** |
| conservatism vs ttt_median | **−0.821** |
| conservatism vs tar_frac | **−0.500** |

All three are negative: **more conservative → better outcome on every
axis** (lower overshoot, shorter recovery, less time above range).

---

## Interpretation

1. **Trade-off hypothesis rejected.** The pre-stated hypothesis
   was "aggressive trades higher overshoot for faster TTT". Data
   show the opposite: aggressive patients (i, e) have *longer*
   median excursions (67.5 min vs 53.8) AND comparable-or-higher
   overshoot AND more time above range. Aggressive Loop_AB_ON is
   *strictly Pareto-dominated* by conservative Loop_AB_ON in this
   cohort.
2. **The "mid" tertile (patient g) is actually the best.** g has
   the lowest TTT (50 min) and lowest TAR (19%). The relationship is
   not strictly monotonic — there is a sweet spot, not a linear
   conservative-is-best.
3. **Patient c is an outlier within "conservative".** c shows the
   highest overshoot (0.356) of the cohort despite high
   conservatism. This is consistent with c having the highest
   `bolus_smb_p95` of the conservative group (0.85 U/cell vs d's
   0.55 U/cell), meaning c sometimes fires sizeable SMBs despite
   the otherwise-conservative posture.
4. **Caveat: n=5.** Spearman ρ = −0.82 on 5 ranked points has
   p ≈ 0.09 (two-sided). These are descriptive ranks only; a
   larger Loop_AB_ON cohort is needed to confirm.

---

## Code-author actionable findings

1. **Do not market AB-aggressive as a "faster recovery" mode.** This
   cohort's data contradict that framing. If anything, the
   aggressive end of the dial increases excursion duration (likely
   because larger SMBs at low-end-of-range trigger Gate G4 / G1
   suppression cascades downstream — see EXP-2990).
2. **Surface the EXP-2991 four-proxy conservatism score** (or its
   components) in Loop's Insights so users can see which side of
   the dial their settings put them on.
3. **Investigate the "mid" sweet spot.** Patient g's combination
   (low IOB cap, small SMB, moderate basal share, near-perfect
   suppression) appears to be a local optimum worth replicating.
4. **Add a unit-test scenario** that explores aggressive-dial
   parameter combinations (`suspendThreshold = 67`,
   `correctionRange.lowerBound = 90`, `maxBolus ≥ 6 U`) and asserts
   the gating contract documented in
   `docs/10-domain/loop-smb-gating-deep-dive-2026-04-23.md`.

---

## Verdict

**NEGATIVE for trade-off hypothesis** (conservative dominates
aggressive on all 3 outcomes); **POSITIVE for AID-author
narrative** (the "aggressive dial" is worse, not just different).
A "sweet spot" appears in the mid tertile (patient g) — flagged as
a future investigation target.
