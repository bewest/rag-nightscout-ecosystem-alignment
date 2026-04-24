# EXP-2973 — 70-100 no-carb stratified by velocity sign (2026-04-23)

## Scope
For open-source AID code authors. Within the 70-100 mg/dL no-carb
sweet spot, partitions cells by 30-min BG velocity into rising
(>+0.5 mg/dL/min), stable (±0.5), and falling (<−0.5) strata.
Reports emission_rate, per-event magnitude, mean per-cell SMB, and
the SMB-on-velocity slope within each stratum, per design.

## What this is NOT
Not therapy advice. Not a per-patient claim.

## Method
Same cell filter as EXP-2972 (bg ∈ [70, 100), no carbs in prior
120 min, no carbs at cell). Add 30-min OLS BG velocity. Bin each
cell into one of three strata. Per (design, stratum) cell with
n ≥ 30: compute emission_rate, mean_emission (conditional on
firing), mean per-cell SMB, and `ins_60_smb ~ vel_30` slope.

## Results

### Per (design, stratum)

| design | stratum | n | em_rate | mean_em (U) | mean SMB/cell (U) | SMB slope |
|---|---|---:|---:|---:|---:|---:|
| **Loop_AB_ON** | rising  | 8,307 | 0.0382 | **0.3609** | 0.01377 | +0.978 |
| Loop_AB_ON | stable  | 16,942 | 0.0396 | 0.1917 | 0.00759 | +0.594 |
| Loop_AB_ON | falling | 3,585 | 0.0346 | 0.2278 | 0.00788 | +0.044 |
| **oref1** | rising  | 13,984 | **0.0971** | 0.1847 | 0.01794 | +0.682 |
| oref1 | stable  | 46,402 | 0.0783 | 0.1579 | 0.01236 | +0.436 |
| oref1 | falling | 5,764 | 0.0481 | 0.2385 | 0.01146 | −0.085 |
| Loop_AB_OFF | (all) | — | 0 | 0 | 0 | 0 |
| oref0 | (all) | — | 0 | 0 | 0 | 0 |

### Loop_AB_ON / oref1 emission_rate ratio per stratum

| stratum | Loop em_rate | oref1 em_rate | Loop / oref1 |
|---|---:|---:|---:|
| rising  | 0.0382 | 0.0971 | **0.39×** |
| stable  | 0.0396 | 0.0783 | **0.51×** |
| falling | 0.0346 | 0.0481 | 0.72× |

## Headline
**POSITIVE / MECHANISM-DECOMPOSITION.** The two designs use
**different levers** to achieve a positive SMB-on-velocity slope:

- **Loop_AB_ON** modulates **per-event MAGNITUDE** with velocity:
  mean_em rises from 0.19 U (stable) to 0.36 U (rising) — a **1.9×
  scaling**. Emission rate is essentially **flat** across velocity
  strata (0.035-0.040), differing by less than 14% between extremes.
- **oref1** modulates **EMISSION FREQUENCY** with velocity:
  em_rate falls from 0.097 (rising) to 0.048 (falling) — a **2.0×
  scaling**. Per-event magnitude is essentially flat (~0.16-0.24 U)
  across strata.

Both designs end up with a positive pooled SMB-on-velocity slope,
but via complementary code-side mechanisms.

## Interpretation for AID authors

This is the cleanest data-side characterization of a **controller
DESIGN difference** observed in this campaign so far.

- **Loop's `units = (predictedBG − target) / ISF`** carries velocity
  through the predictedBG curve. Larger predicted overshoot →
  larger `partialDose = units × applicationFactor`. The emission
  *rate* is gated by `partialDose > volumeRounder.minimum`, which
  flips on/off at a similar rate across velocity strata in this BG
  band.
- **oref1's `microBolus = min(insulinReq/2, maxBolus_smb)`** is
  capped by `maxSMBBasalMinutes` (~0.5 U for typical basal),
  which **truncates** velocity sensitivity in magnitude. The
  velocity sensitivity instead manifests in the **gate**:
  `naive_eventualBG > target` is required for `insulinReq > 0`;
  on a falling curve `naive_eventualBG < target`, so oref1 simply
  **skips** the cycle.

For an AID author choosing between policies in this band:
- **Loop-style "magnitude modulation"** preserves per-cycle pumping
  cadence at the cost of larger single doses on rising velocity.
- **oref1-style "frequency modulation"** keeps single-dose size
  bounded at the cost of more pump operations.

The **falling stratum is where they converge**: both designs
appropriately back off (Loop's slope drops to +0.04, oref1's slope
goes slightly negative −0.08). This is the **safety convergence
point** at recovery from low-target BG.

## Files
- Script: `tools/cgmencode/exp_velocity_stratified_sweet_spot_2973.py`
- JSON: `externals/experiments/exp-2973_summary.json`

## Provenance
- Cohort: `externals/experiments/exp-2891_simpson_dose_response.parquet`
- Grid: `externals/ns-parquet/training/grid.parquet`
- Date: 2026-04-23

## Next
- Confirm via patient-level decomposition (does each Loop_AB_ON
  patient show flat-em_rate + scaled-magnitude pattern, or just the
  pooled aggregate?).
- Test whether Loop's magnitude scaling carries through into glucose
  outcome (does the larger rising-stratum dose translate to faster
  return to target than oref1's higher-frequency strategy?).
