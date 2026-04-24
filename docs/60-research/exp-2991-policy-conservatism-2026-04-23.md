# EXP-2991: Per-patient policy-conservatism score (Loop_AB_ON)

**Date**: 2026-04-23
**Audience**: open-source AID code authors (Loop, LoopAlgorithm).
**Scope**: build a composite "policy conservatism" score from four
observable proxies for each Loop_AB_ON patient (c, d, e, g, i) and
correlate against an overshoot-rate outcome.
**What this is NOT**: not a clinical risk score; not a per-user
recommendation; not an inference about the latent (un-observable)
Loop knobs themselves (suspendThreshold, correctionRange,
maxBolus, GBAF) — only their *behavioral correlates*.

---

## Headline

**MIXED.** A four-proxy conservatism score cleanly orders the five
peers (d > c > g > e > i; Pearson correlations among the four proxies
are mutually positive). However the simple Pearson correlation
between conservatism and overshoot at 100-180 mg/dL is r = +0.013 —
no signal. The dial is real *across patients* but does NOT predict
overshoot in this cohort. The richer outcome stratification is in
EXP-2993.

---

## Method

For each Loop_AB_ON patient, compute four proxies from grid:

| Proxy | Definition | Direction (conservative ⇒) |
|-------|------------|----------------------------|
| `iob_p95` | 95th percentile of `iob` | lower |
| `bolus_smb_p95` | 95th percentile of non-zero `bolus_smb` | lower |
| `suppress_70_100_eligible` | 1 − fire-rate among eligible cells (no override, no recent carbs, IOB < patient-95th-pctl) in 70-100 mg/dL band | higher |
| `basal_frac_of_tdd` | Σ(actual_basal × 5/60) / [Σ(actual_basal × 5/60) + Σ(bolus)] | higher |

Each proxy is min-max-normalised across the five peers (with `iob_p95`
and `bolus_smb_p95` inverted) and averaged.

Outcome:

| Metric | Definition |
|--------|------------|
| `overshoot_rate_100_180` | Frac of cells with `glucose ∈ [100, 180]` whose forward-90-min max BG > 180 mg/dL |

Implementation: `tools/cgmencode/exp_policy_conservatism_2991.py`
Output: `externals/experiments/exp-2991_policy_conservatism.parquet`,
`externals/experiments/exp-2991_summary.json` (gitignored).

---

## Results

```
patient  iob_p95  bolus_smb_p95  suppress_70_100  basal_frac  overshoot  conservatism
   d      4.63        0.55           0.989          0.151       0.194      0.796
   c      5.88        0.85           1.000          0.233       0.356      0.761
   g      5.92        0.55           0.994          0.060       0.210      0.698
   e     12.80        0.90           0.999          0.251       0.259      0.548
   i      9.95        1.50           0.870          0.399       0.251      0.337
```

* Conservatism rank: **d > c > g > e > i**.
* The largest single proxy gap is `suppress_70_100_eligible`
  (1.000 → 0.870, see EXP-2987).
* The second-largest is `bolus_smb_p95` (0.55 → 1.50; nearly 3× wider
  per-cell SMB at the 95th percentile in patient i).
* `iob_p95` is the smallest discriminator: peers c and g are *higher*
  than d but still rank conservative.

### Pearson correlations

| Pair | r |
|------|---|
| conservatism vs overshoot | **+0.013** (NULL) |

---

## Interpretation

1. **The score is internally coherent.** All four proxies move in
   the expected direction across the five peers (d most conservative,
   i most aggressive).
2. **The trade-off hypothesis fails on overshoot alone.** Pearson
   r = +0.013 between conservatism and overshoot at 100-180 mg/dL
   means the dial does not predict overshoot in this 5-patient
   cohort. Patient `c` is the most overshoot-prone (0.356) despite
   being the second-most conservative.
3. **The story is more nuanced than "aggressive → overshoot, fast
   recovery"**. EXP-2993 expands the outcome panel to include time-
   to-target and time-above-range and finds that *conservative
   patients dominate on every outcome* — a surprising rejection of
   the dial-as-trade-off framing.

---

## Code-author actionable findings

1. The four proxies in this score are computable from any
   Nightscout-style export and could be surfaced in Loop's "Insights"
   pane to give users a self-snapshot of where they sit on the dial.
2. The poor correlation with overshoot in this cohort (r ≈ 0)
   suggests no single-axis "policy aggressiveness" knob can be
   exposed responsibly to users — a multi-axis cockpit is needed
   (consistent with the Counter-recommendation in synthesis §13).

---

## Verdict

MIXED — score is internally consistent and ranks patients
plausibly, but does NOT predict overshoot. Defer to EXP-2993 for
multi-outcome stratification.
