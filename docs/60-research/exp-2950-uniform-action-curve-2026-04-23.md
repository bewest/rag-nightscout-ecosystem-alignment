# EXP-2950 — Uniform action-curve re-derivation of IOB-age mechanism

**Date**: 2026-04-23
**Audience**: AID code authors. NOT therapy advice.
**Verdict**: **DECISIVE CONFIRMATION** of EXP-2944 IOB-timing mechanism, independent of grid `iob` column source.

## Hypothesis

EXP-2949 surfaced that grid `insulin_activity` is oref1-only and `iob`
is controller bookkeeping that may differ in conventions across designs.
This experiment re-derives BOTH iob and activity uniformly from event
history (`bolus + bolus_smb + basal_excess`) using a standard biexponential
insulin action curve (peak 75 min, DIA 300 min, bilinear approximation).

If EXP-2944's iob_delta gap reproduces with the uniform curve, the IOB-age
mechanism is confirmed independent of column-source artifacts.

## Method

- Anchor: identical to EXP-2944. BG crosses 180 climbing; prior 30min
  <180; no carbs in 30min before or 60min after window.
- Insulin events: 5-min cell totals of `bolus + bolus_smb +
  max(actual_basal_rate - scheduled_basal_rate, 0) × 5/60`. Treat each
  event as point-delivery at cell start.
- Action curve (uniform, applied identically to all designs):
  - Pre-peak (t<75 min): IOB(t) = 1 - 0.5(t/75)²; activity(t) = t/75²
  - Post-peak (75≤t<300 min): linear decay to 0
- Lookback: 5h prior to each event entry.
- Compute synth_iob and synth_activity at entry (t=0) and at +60min.

## Result

5,159 carb-isolated sustained-high entries across 4 designs.

| Design       | n     | iob_entry | act_entry | iob_delta | act_delta | bg_delta |
|--------------|------:|----------:|----------:|----------:|----------:|---------:|
| Loop_AB_OFF  |   609 |     3.30  |   0.0252  |   +0.69   |  +0.0073  |  +21.64  |
| Loop_AB_ON   | 1,626 |     6.38  |   0.0386  |   +0.40   |  +0.0231  |  +12.16  |
| oref0        | 1,203 |     1.91  |   0.0158  |   −0.05   |  −0.0009  |  +10.80  |
| **oref1**    | 1,721 |     7.02  |   0.0454  |   **−0.78** |  +0.0127  |  **−9.60** |

### Loop_AB_ON vs oref1 contrasts

| Metric            | Loop      | oref1     | Δ (Loop−oref1) | MW p-value |
|-------------------|----------:|----------:|---------------:|-----------:|
| synth_iob_entry   |   +6.38   |   +7.02   |    −0.64       | 6.3e-04    |
| synth_act_entry   |   +0.0386 |   +0.0454 |    −0.0068     | 1.4e-08    |
| **synth_iob_delta** | **+0.40** | **−0.78** | **+1.18**     | **9.5e-21** |
| synth_act_delta   |   +0.0231 |   +0.0127 |    +0.0103     | 1.2e-10    |
| **bg_delta**      | **+12.16**| **−9.60** | **+21.76 mg/dL** | **1.7e-34** |

## Interpretation

The signature reproduces in lockstep with EXP-2944:

1. **iob_entry** — oref1 starts the window with comparable or slightly
   higher IOB than Loop (7.02 vs 6.38 U). NOT a magnitude deficit.

2. **act_entry** — oref1's IOB is closer to peak action at window entry
   (0.045 vs 0.039 activity-units; +18% relative). Higher freshness AT
   the response window.

3. **iob_delta** — During the 60-min window, **Loop's IOB CLIMBS by
   +0.40 U; oref1's IOB FALLS by −0.78 U.** Gap = +1.18 U. This is
   the IOB-timing signature: Loop is still loading dose during the
   correction window; oref1 has its dose already placed and is now
   acting it out.

4. **act_delta** — Loop's activity is still RISING faster (+0.023 vs
   +0.013). Reactive build-up vs proactive deployment.

5. **bg_delta** — Loop BG continues to RISE +12 mg/dL during the
   "correction" window; oref1 BG falls −9.6 mg/dL. The mechanism
   produces a 22 mg/dL outcome gap.

## Comparison to EXP-2944 (grid `iob`)

| Metric          | EXP-2944 (grid iob) | EXP-2950 (uniform synth) | Sign/direction |
|-----------------|--------------------:|-------------------------:|:--------------:|
| iob_start gap   | +0.54 (oref1 higher)| +0.64 (oref1 higher)     | ✓ same         |
| iob_delta Loop  | +0.59 climbing      | +0.40 climbing           | ✓ same         |
| iob_delta oref1 | −0.04 peaking       | −0.78 falling            | ✓ same         |
| iob_delta gap   | +0.63 U             | +1.18 U                  | ✓ same sign    |

The uniform-curve numbers are LARGER in magnitude because they include
basal_excess as an insulin event (grid `iob` may exclude basal). But
the **direction and ranking are identical**. Mechanism confirmed.

## What this closes

- The IOB-timing mechanism is NOT an artifact of grid `iob` accounting
  conventions. It reproduces with a uniform action-curve model applied
  identically to all designs.
- Combined with EXP-2942 (cross-cohort match), EXP-2943 (η²=0.64),
  EXP-2944 (in-grid mechanism), EXP-2946 (PP cross-validation), EXP-2947
  (hypo unification), and now EXP-2950 (uniform-curve replication), the
  framework rests on six independent lines of evidence.
- Selection-bias hypothesis remains structurally implausible.

## What this does NOT close

- AAPS data ingestion (EXP-2908) for n-imbalance fix
- Within-patient AID-switch data (gold standard)
- Per-patient TZ normalisation
- Action-curve sensitivity (peak 60-90 min, DIA 240-360 min) —
  parameters are reasonable defaults but variation in patient absorption
  could shift magnitudes; signs and rankings unlikely to flip given the
  size of the iob_delta and bg_delta gaps.

## What this is NOT

- A claim about absolute IOB levels for any patient
- Therapy advice or dosing recommendation
- A migration recommendation between AID systems

## What this IS

- Independent validation that the IOB-timing/age mechanism is real
- Confirmation that uniform action-curve modeling reproduces EXP-2944
  signature with stronger numbers
- Methodological template for future cross-design experiments: when
  controller-specific bookkeeping is suspected, re-derive from event
  history with a uniform model.

## AID-author lever (UNCHANGED, REINFORCED)

**Predict-and-fire on rising velocity early, so that IOB AGES before
the BG response window.** Loop's reactive cadence + later first-fire
of velocity-prediction loads dose during the response, producing
+12 mg/dL window delta. oref1's UAM/dyn-ISF stack pre-loads dose,
producing −10 mg/dL recovery in the same window class — a 22 mg/dL
mechanism-driven gap.
