# EXP-2943 — within-design vs between-design variance decomposition

**Date**: 2026-04-23
**Audience**: AID code authors

## Scope

Variance decomposition test for the selection-bias hypothesis.
If patient-cohort differences drive the +21 pp recovery gap, within-
design variance should be large and patient-level covariates (BG
mean, BG variability, SMB usage rates, carbs/day) should explain a
substantial fraction of recovery differences.

Reused EXP-2942 carb-isolated event extraction. 19 patients across
4 design cells.

## What this is NOT

- Not a per-patient performance ranking.
- Not therapy advice. Within-design correlations may reflect
  reverse causation (harder-to-control patients get more
  aggressive settings).

## Results

### Per-design recovery distribution

| Design       | n | mean   | std   | min   | max   |
|--------------|--:|-------:|------:|------:|------:|
| Loop_AB_OFF  | 2 | 0.296  | 0.069 | 0.248 | 0.345 |
| Loop_AB_ON   | 5 | 0.357  | 0.084 | 0.253 | 0.449 |
| oref0        | 3 | 0.300  | 0.064 | 0.237 | 0.364 |
| oref1        | 9 | 0.570  | 0.122 | 0.357 | 0.776 |

### Variance decomposition (one-way ANOVA-style)

- SS_between (design): 0.286 → **64.0%**
- SS_within  (patient within design): 0.160 → 36.0%
- **η² = 0.640** → DESIGN-DOMINATED

The design cell explains nearly twice as much variance as
patient-to-patient differences within designs. Combined with
EXP-2942's cross-cohort match between Loop_AB_OFF and oref0,
the selection-bias hypothesis is no longer parsimonious.

### Within-design covariate correlations (Spearman ρ)

| Covariate          | Loop_AB_ON | oref0 | oref1 |
|--------------------|-----------:|------:|------:|
| bg_mean            |   −0.50    |  0.50 | −0.83 |
| bg_cv              |   −0.70    |  0.50 | −0.75 |
| bg_pct_high        |   −0.60    | −0.50 | −0.83 |
| smb_total_per_day  |   −0.90    |   n/a | −0.08 |

Within-design patterns are physiologically expected: better-controlled
patients (lower mean BG, lower variability) tend to recover better
once they do go high. The Loop_AB_ON `smb_total_per_day` ρ=−0.9 is
likely reverse causation — patients with worse glycemic control
have AID configurations tuned more aggressively.

The oref0 cell flips sign on `bg_mean` (n=3, low power; one
overshoot patient).

## Interpretation

Combined with EXP-2942 cross-cohort matching:

| Test                     | EXP   | Result                       |
|--------------------------|-------|------------------------------|
| Cross-cohort match       | 2942  | oref0≈Loop_AB_OFF (29.6 vs 30.0) |
| Variance decomposition   | 2943  | η²=0.64 (design dominates)   |
| Within-design covariates | 2943  | physiologically reasonable; insufficient to explain 21pp gap |

**Selection-bias hypothesis is now structurally weak.** It would
need to (a) coincidentally match Loop_AB_OFF and oref0 patient
cohorts on recovery determinants, AND (b) generate 64% of variance
from design assignment. The simpler explanation is that algorithm
channel availability + dose-sizing logic determine recovery.

## Carry-forward invariants

- **η² > 0.5 + cross-cohort matching = selection-bias rejected.**
  Combined test template for cross-design claims.
- Within-design covariate correlations are useful for *describing*
  patient heterogeneity but cannot resolve causation in observational
  AID data (reverse causation via setting tuning).

## AID-author levers (re-affirmed)

1. UAM/glucose-appearance + dynamic-ISF (PP offence)
2. SMB-as-correction during sustained-high
3. Size correction SMBs to BG AND BG velocity (oref1 lever)
4. Enable autobolus by default for AID-OFF correction loops
5. Basal-cut latency

## Artefacts

- `tools/cgmencode/exp_within_design_2943.py`
- `externals/experiments/exp-2943_summary.json` (gitignored)
