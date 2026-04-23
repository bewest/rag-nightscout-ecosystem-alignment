# EXP-2949 — IOB-age unified test via insulin_activity / iob ratio

**Date**: 2026-04-23
**Audience**: AID code authors. NOT therapy advice.
**Verdict**: **MIXED** — operationalisation candidate falsified for cross-design use due to data-availability artifact. tsb_min ≈ equivalent at first-fire moments. Mechanism remains in iob_delta (EXP-2944), not in first-fire latency or activity ratio.

## Hypothesis

Cleaner operationalisation of EXP-2944/2946/2947 IOB-age framework via the ratio:

```
freshness = insulin_activity / iob
```

Predicted at three event types:
- HYPO descent (BG=80 falling): oref1 < Loop_AB_ON (staler IOB at hazard)
- SUSTAINED-HIGH (BG=180 climbing): oref1 > Loop_AB_ON (peak action when needed)
- MEAL onset: oref1 > Loop_AB_ON (UAM pre-fire)

## Data caveat — surfaced by this experiment

`insulin_activity` in `grid.parquet` is **populated only for oref1 patients**.
Loop and oref0 designs leave the column at 0/NaN. This is not a measurement
of insulin physiology; it is a data-pipeline artifact. The activity column
is the controller's own bookkeeping (the integrated curve oref* compute
internally), not a re-derivation from insulin events.

| Design        | Mean activity at hypo entry | Mean activity at high entry |
|---------------|----------------------------:|----------------------------:|
| Loop_AB_OFF   | 0.000                       | 0.000                       |
| Loop_AB_ON    | 0.000                       | 0.000                       |
| oref0         | 0.000                       | 0.000                       |
| oref1         | 0.007                       | 0.016                       |

`freshness` is therefore identically 0 for non-oref1 designs and
**cannot be used as a cross-design metric**.

## Secondary measurement — `time_since_bolus_min`

This column IS populated across designs. Median tsb_min at each event:

| Event              | Loop_AB_OFF | Loop_AB_ON | oref0 | oref1 |
|--------------------|------------:|-----------:|------:|------:|
| HYPO entry (BG=80) |         360 |         70 |   180 |    60 |
| SUSTAINED-HIGH     |         360 |          0 |    65 |     0 |
| MEAL onset         |           0 |          0 |     0 |     0 |

Findings:
- At sustained-high entry, Loop_AB_ON and oref1 BOTH fire at the
  threshold-crossing moment (median tsb=0). First-fire latency is NOT
  the differentiator. **EXP-2937/2940 already established this; tsb
  confirms.**
- At hypo entry, Loop_AB_ON tsb=70 vs oref1 tsb=60 — oref1 actually
  has FRESHER bolus, opposite of the hypothesis. Yet oref1 has 2×
  LOWER severe-hypo rate (EXP-2947).
- At meal onset, all designs bolus at t=0 (user-driven event).

## Implication

The IOB-age mechanism identified in EXP-2944 (iob_delta during the
60-min sustained-high window) **cannot be reduced to first-fire
latency or last-bolus age**. Both designs fire at the threshold; the
mechanism is the **shape of insulin delivery DURING the response
window**, integrated against the action curve.

Two implications for future work:

### 1. Methodological invariant

Cross-design comparisons cannot use `insulin_activity` as a
freshness metric because the column is design-specific output.
The principled operationalisation requires re-computing insulin
activity from `bolus + bolus_smb + actual_basal_rate` event
history with a uniform action-curve model (e.g., bilinear or
biexponential). EXP-2950 should construct this.

### 2. Mechanism stays in iob_delta

The IOB-age framework from EXP-2944/2946/2947 stands on the
**within-window iob_delta** measurement, not on tsb proxies or
the activity ratio. EXP-2944's headline (Loop iob_delta +0.59
climbing vs oref1 −0.04 peaking) is the cleanest available
operationalisation.

## Pairwise contrasts (freshness, where defined)

All Mann-Whitney p ≪ 0.001, but the contrasts are dominated by
the activity-column data-availability artifact, not biology.

```
HYPO_ENTRY:    Loop_AB_ON vs oref1: Δ −0.0264 (MW p=3e-216)  [artifact]
SUSTAINED-HIGH: Loop_AB_ON vs oref1: Δ −0.0080 (MW p=0)      [artifact]
MEAL_ONSET:    Loop_AB_ON vs oref1: Δ −0.0080 (MW p=3e-72)   [artifact]
```

These are NOT reportable as cross-design mechanism findings.

## What this is NOT

- A refutation of the IOB-age framework
- A measurement of physiological insulin freshness (the column is
  controller bookkeeping, not physiology)
- A first-fire latency finding (already established in EXP-2937/2940)

## What this IS

- A negative result that protects the framework against a flawed
  operationalisation
- A spec for EXP-2950: re-compute insulin activity from event
  history with a uniform action curve, then compare across designs
- A confirmation that first-fire timing is NOT the lever (median
  tsb=0 for both at sustained-high, similar at hypo)

## n

| Event                  | n     |
|------------------------|------:|
| HYPO entry             | 5,205 |
| SUSTAINED-HIGH entry   | 5,165 |
| MEAL onset             | 2,029 |
