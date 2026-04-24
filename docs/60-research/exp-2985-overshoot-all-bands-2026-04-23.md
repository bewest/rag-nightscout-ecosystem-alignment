# EXP-2985 — Cross-patient overshoot rate at all BG bands (Loop_AB_ON)

**Date**: 2026-04-23
**Audience**: Open-source AID code authors
**Scope**: Per Loop_AB_ON patient (c, d, e, g, i), compute
overshoot rate (>180 mg/dL within 60 min) and 60-min hypo
rate following each no-carb SMB, stratified by BG band of the
SMB origin. Bands: <70, 70-100, 100-140, 140-180, 180-220,
>220.  47,105 qualifying events pooled.
**What this is NOT**: a Loop_AB_ON outcome generalization (n=5
patients only). Not a per-patient recommendation.

## Result — POSITIVE: at bands where everyone fires, `i` is representative

| band | i overshoot | others median | others max | i within others' range? |
|---|---:|---:|---:|---|
| 100-140 | 14.6% | 11.96% | 32.5% (c) | **YES** |
| 140-180 | 35.6% | 32.1% | 53.6% (c) | **YES** |
| 180-220 | 95.6% | 95.2% | 96.6% | YES |
| 220-999 | 100% | 100% | 100% | YES |
| 70-100  | 7.3% | 0% (only 0-18 events) | 100% (one event) | n/a |

At every band where the other Loop_AB_ON patients fire
meaningful numbers of SMBs (100-140, 140-180, 180-220, 220+),
patient `i`'s overshoot rate is **inside the cohort range** —
in fact, patient `c` shows higher overshoot at 100-140 (32.5%)
and 140-180 (53.6%). `i` is **not** an overshoot outlier.

## Pooled per-band view (Loop_AB_ON, no-carb, n=47,105)

| band | n events | smb median (U) | overshoot 180 60min | hypo 70 60min |
|---|---:|---:|---:|---:|
| <70    |     2 | 0.50 | 100% | 0% |
| 70-100 | 1,112 | 0.15 | 7.3% | **15.2%** |
| 100-140 | 13,176 | 0.10 | 13.4% | 3.1% |
| 140-180 | 14,185 | 0.15 | 35.3% | 1.0% |
| 180-220 |  8,612 | 0.20 | **95.6%** | 0.4% |
| 220+    | 10,018 | 0.30 | **100%** | 0.1% |

Even for 100% of events in 220+ ending above 180 within 60 min,
this is partly tautological (BG already above 220) — the
correct read is the **rate at which dosing brings BG below 180
within 60 min** (here, 0%). At 180-220 the cohort virtually never
returns to ≤180 within an hour.

## Implication for EXP-2979's directional claim

EXP-2979 reported Loop_AB_ON overshoot 10.7% vs oref1 (Trio) 3.5%
**in the rising 70-100 stratum**. EXP-2985 shows:

1. The 10.7% number was patient `i` alone (1097 of 1112 events
   in the 70-100 band are his — `c/d/e/g` collectively fired
   only 15 there).
2. At bands where all 5 patients fire, `i`'s overshoot is
   **typical** — Loop_AB_ON has a population-level overshoot
   characteristic that is band-driven, not patient-`i`-driven.
3. The Loop-vs-oref1 mechanism comparison from EXP-2979 still
   holds **directionally** but should be downgraded from "Loop
   magnitude lever creates 3× overshoot" to "the only Loop
   patient who fires SMB at 70-100 rising shows 10.7%
   overshoot, vs 3.5% Trio pooled across 9 patients in the same
   stratum."

## Headline relabel for EXP-2979

> The 10.7% Loop overshoot in the rising-70-100 stratum is
> **patient-`i`-only** because no other Loop_AB_ON patient
> fires SMB there. `i` is not an outlier on overshoot rate at
> bands where peers do fire (100-140, 140-180), so the value
> is plausible. But the **Loop arm of the EXP-2979 mechanism
> claim is single-patient-bound** and the directional
> "magnitude-lever ⇒ overshoot" prediction cannot be tested
> at cohort level in this dataset.

## Verdict

**POSITIVE**: `i` is overshoot-representative at bands where
peers fire. EXP-2979's directional finding stands but is
appropriately scoped to "the Loop_AB_ON configuration that
fires SMB at low BG" rather than "Loop_AB_ON in general."

## Source / data
- `tools/cgmencode/exp_overshoot_all_bands_2985.py`
- `externals/experiments/exp-2985_summary.json`
