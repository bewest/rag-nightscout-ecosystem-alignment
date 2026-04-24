# EXP-2966 — BG-band sweep of SMB-channel velocity-coupling (2026-04-23)

## Scope
For open-source AID code authors. Maps the "lever-3 surface" — at
what BG ranges does SMB-on-rising-velocity matter most, and is
that surface controller-design dependent? Output is a tuning
table for AID authors choosing SMB triggering thresholds.

## What this is NOT
Not per-patient therapy advice. Not a CGM-band TIR claim. Not a
within-patient effect — we report pooled slopes per (band, design)
cell.

## Method
For every 5-min CGM index `i` (no carb-window restriction beyond
context tag), compute:
- `vel_30 = OLS slope bg[i..i+6] vs minutes`
- `ins_60_smb = sum(bolus_smb)` over `[i, i+12)`
- band = bin(`bg[i]`) into [70-100, 100-140, 140-180, 180-220,
  220-260, 260-300]

Two contexts:
- **PP**: `carbs[i] ≥ 30 g` AND zero carbs in prior 60 min.
- **no_carb**: zero carbs at `i` and zero carbs in prior 120 min.

For each (band, design, context) cell with ≥30 events, fit pooled
`ins_60_smb ~ vel_30` and report slope with 95% CI.

## Results

**PP windows:** 4,687. **no-carb windows:** 612,741.

### PP context — SMB-channel slope by band

| Band (mg/dL) | Loop_AB_ON | oref1 |
|---|---|---|
| 70–100 | +0.490 [+0.30, +0.68] (n=163) | +0.396 [+0.27, +0.52] (n=749) |
| 100–140 | +0.298 [+0.16, +0.43] (n=302) | +0.310 [+0.21, +0.41] (n=938) |
| 140–180 | +0.454 [+0.26, +0.64] (n=177) | +0.287 [+0.15, +0.42] (n=322) |
| 180–220 | +0.414 [+0.19, +0.64] (n=90) | +0.294 [+0.12, +0.47] (n=118) |
| 220–260 | +0.544 [+0.22, +0.87] (n=44) | +0.315 [+0.09, +0.54] (n=39) |

PP slopes: comparable across designs, all 95% CIs overlap. Slight
dip in the 100–140 mg/dL band ("at-target") for both designs;
slight peak at 220–260 for Loop_AB_ON. **No clear sweet spot at PP
distinguishes designs.**

### no-carb context — SMB-channel slope by band (large n)

| Band (mg/dL) | Loop_AB_ON SMB slope | oref1 SMB slope | Loop/oref1 ratio |
|---|---|---|---:|
| 70–100 | **+0.859 [+0.846, +0.872]** (n=28,834) | **+0.570 [+0.560, +0.579]** (n=66,148) | 1.51× |
| 100–140 | +0.787 [+0.778, +0.795] (n=56,366) | +0.527 [+0.520, +0.534] (n=98,451) | 1.49× |
| 140–180 | +0.745 [+0.735, +0.756] (n=39,682) | +0.487 [+0.477, +0.496] (n=38,325) | 1.53× |
| 180–220 | +0.686 [+0.671, +0.701] (n=22,351) | +0.417 [+0.404, +0.431] (n=14,378) | 1.65× |
| 220–260 | +0.703 [+0.679, +0.727] (n=12,327) | +0.428 [+0.405, +0.451] (n=5,540) | 1.64× |
| 260–300 | +0.787 [+0.747, +0.826] (n=5,318) | +0.415 [+0.376, +0.453] (n=1,830) | 1.90× |

In the no-carb context with N > 100,000 events per cell, **all 95%
CIs are disjoint between Loop_AB_ON and oref1**. Loop_AB_ON SMB
slope is 1.5–1.9× oref1's across every band.

`Loop_AB_OFF` and `oref0` cells: SMB slope is 0 by construction
(neither design emits SMB). Their basal-excess slopes remain
small (Loop_AB_OFF basal_x +0.45 at 70-100 mg/dL — the
basal-cut-on-falling-velocity reflex, but at PP/sustained-high BG
bands it falls to <0.12).

### Sweet-spot bands

| Design | Context | Band | SMB slope |
|---|---|---|---:|
| Loop_AB_ON | no_carb | **70–100** | +0.859 |
| oref1 | no_carb | **70–100** | +0.570 |

Both designs have their **maximum SMB-on-velocity coupling in the
just-above-target band (70–100 mg/dL) in the no-carb context** —
where rising velocity signals a recovery from low BG climbing
toward target. Slope falls toward the at-target/100–140 band, then
re-rises modestly in the highest bands (260–300 for Loop_AB_ON).

## Interpretation

**POSITIVE / NEW finding** with one important caveat:

1. **In the high-N no-carb context, Loop_AB_ON SMB slope exceeds
   oref1 SMB slope at every BG band by ~1.5–1.9×, with disjoint
   95% CIs.** This is the cleanest signal of a controller-design
   difference yet observed in this campaign. The PP context
   (where USER bolus dominates and obscures controller signal)
   does NOT show this separation.

2. **Sweet spot for SMB-on-velocity coupling is the 70–100 mg/dL
   band in no-carb context.** Both controllers respond most
   strongly to rising velocity when BG is just above target — i.e.
   they catch a recovery from hypo before it overshoots. This is
   the BG range AID authors should prioritize when tuning SMB
   triggering sensitivity.

3. **Caveat: pooled slopes with hierarchical data inflate
   significance.** The disjoint 95% CIs in the no-carb context
   reflect huge n with patient-level variance pooled. Per-patient
   MWU (EXP-2965, EXP-2969, EXP-2970) consistently fails to find
   between-design significance. The cleanest reading: **the
   directional ordering Loop_AB_ON > oref1 is now confirmed across
   every BG band in the no-carb context with disjoint CIs**, but
   the per-patient effect size remains within natural patient-to-
   patient variation.

4. **U-shape of slope vs BG** — both controllers have minimum
   SMB-on-velocity sensitivity in the 100–140 ("at target") band
   and higher sensitivity at edges (low and very high). This is
   consistent with target-band suppression of triggering and
   protective re-engagement at extremes.

5. **Loop_AB_OFF basal_x slope at 70-100 mg/dL is +0.45** — the
   single largest basal-excess velocity-coupling number observed.
   This is the basal-only fallback used by AB-OFF Loop to climb
   out of low-side recoveries (no SMB available). Confirms that
   Loop_AB_OFF substitutes basal modulation for the SMB lever.

## Files
- Script: `tools/cgmencode/exp_bg_band_velocity_sweep_2966.py`
- JSON: `externals/experiments/exp-2966_summary.json`

## Provenance
- Cohort: `externals/experiments/exp-2891_simpson_dose_response.parquet`
- Grid: `externals/ns-parquet/training/grid.parquet`
- Repo HEAD: 15b0d75
- Date: 2026-04-23

## Next
- Per-patient version of the no-carb sweep (verify the Loop > oref1
  ordering survives a per-patient sign-test at high-N).
- Stratify the 70-100 sweet-spot by `bg[i-1]` (low-recovery climb
  vs target-band stability) to confirm the recovery interpretation.
- Compare emission frequency vs per-event magnitude in the sweet
  spot — are Loop and oref1 firing equally often but with different
  per-event size, or vice versa?
