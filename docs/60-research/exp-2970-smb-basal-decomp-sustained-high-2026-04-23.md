# EXP-2970 — SMB-vs-basal decomposition at sustained-high (2026-04-23)

## Scope
For open-source AID code authors. Applies the EXP-2964 decomposition
pattern at sustained-high windows. Tests whether Loop_AB_ON's
autobolus-on policy is more aggressive than oref1's SMB triggering
at sustained-high — both as mean SMB delivered and as SMB-channel
velocity-coupling slope.

## What this is NOT
Not per-patient therapy advice. Not a within-patient causal claim.

## Method
Sustained-high entry: BG crosses 200 mg/dL with zero carbs in prior
120 min, ≥60 min spacing. For each design, pooled per-channel
regression of `ins_60_X ~ vel_30` plus per-patient breakdown
(min 10 events).

## Results

**Sustained-high events:** 3,375.

### Component MEANS at sustained-high (U over 60 min)

| design | n | n_pat | bolus | smb | basal_x | total |
|---|---:|---:|---:|---:|---:|---:|
| Loop_AB_OFF | 662 | 2 | 2.40 | 0.00 | 1.575 | 3.97 |
| Loop_AB_ON | 1392 | 5 | 3.40 | **2.06** | 0.124 | 5.58 |
| oref0 | 534 | 3 | 0.83 | 0.00 | 0.286 | 1.12 |
| oref1 | 787 | 9 | 2.47 | **1.26** | 0.067 | 3.80 |

### Pooled per-channel velocity-coupling slopes (U per mg/dL/min)

| design | bolus slope (95% CI) | SMB slope (95% CI) | basal_x slope (95% CI) | total |
|---|---|---|---|---|
| Loop_AB_OFF | +1.06 [+0.88, +1.24] | 0 (n/a) | +0.116 [+0.08, +0.15] | +1.18 |
| Loop_AB_ON | +1.24 [+1.11, +1.37] | **+0.781 [+0.71, +0.85]** | +0.033 [+0.015, +0.050] | +2.05 |
| oref0 | +0.04 (n.s.) | 0 (n/a) | +0.019 (n.s.) | +0.06 (n.s.) |
| oref1 | +0.59 [+0.46, +0.73] | **+0.385 [+0.32, +0.45]** | +0.006 (n.s.) | +0.98 |

### Per-patient SMB-channel slopes (sustained-high)

| Design | n_pat | median | mean | (+/−) |
|---|---:|---:|---:|---|
| Loop_AB_ON | 5 | +0.598 | +0.588 | 5+/0− |
| oref1 | 9 | +0.386 | +0.410 | 9+/0− |

### MWU Loop_AB_ON vs oref1 SMB slopes (two-sided)
U = 31.0, **p = 0.298** — NOT significant.

Loop_AB_ON SMB slopes: [0.227, 0.391, 0.598, 0.640, 1.085]
oref1 SMB slopes: [0.100, 0.225, 0.247, 0.324, 0.386, 0.420, 0.545, 0.617, 0.825]

## Interpretation

**MIXED — disentangling two real effects:**

1. **Mean SMB dose at sustained-high IS substantially larger for
   Loop_AB_ON than for oref1** (2.06 U vs 1.26 U over 60 min, ~63%
   higher). This is a real controller-design difference: Loop AB ON's
   triggering plus accumulation policy delivers more SMB per
   sustained-high entry than oref1's SMB heuristic.

2. **The SMB-channel velocity-coupling SLOPE is steeper for
   Loop_AB_ON pooled** (+0.78 vs +0.39, ~2× — 95% CIs disjoint:
   [0.71, 0.85] vs [0.32, 0.45]). At pooled level this looks like a
   genuine design difference.

3. **But per-patient SMB slopes do not separate** (MWU p = 0.30).
   The Loop_AB_ON distribution [0.23–1.09] overlaps the oref1
   distribution [0.10–0.83] heavily; only the top Loop_AB_ON patient
   (+1.09, "i") exceeds every oref1 patient. The pooled +0.78 vs
   +0.39 slope difference reflects within-design variance plus a
   moderate central-tendency shift, not a controller-uniform doubling.

4. **Net call:** The EXP-2964 conclusion (controller-channel SMB
   slopes near-equivalent at PP) **partially extends** to
   sustained-high: per-patient MWU still says equivalent, but mean
   SMB dose AND pooled slope show Loop_AB_ON is meaningfully more
   aggressive. The mean-dose difference is the cleaner signal.
   AID authors implementing autobolus / SMB heuristics for
   sustained-high should focus on **trigger frequency / IOB-budget
   ceilings** (which control mean dose) more than on per-event
   velocity-modulation strength (which is similar).

5. **basal_excess channel slope is small in all designs**
   (≤ +0.12). Temp-basal velocity modulation is not a competitive
   sustained-high lever in any of the four designs.

## Files
- Script: `tools/cgmencode/exp_smb_basal_decomp_sustained_high_2970.py`
- JSON: `externals/experiments/exp-2970_summary.json`

## Provenance
- Cohort: `externals/experiments/exp-2891_simpson_dose_response.parquet`
- Grid: `externals/ns-parquet/training/grid.parquet`
- Repo HEAD: 15b0d75
- Date: 2026-04-23

## Next
- Decompose mean-SMB-dose difference into emission frequency vs
  per-event magnitude (next batch).
- Map Loop AB ON's SMB-cap policy code-path against oref1's
  `microBolusAllowed` ceiling to identify the code-level lever.
