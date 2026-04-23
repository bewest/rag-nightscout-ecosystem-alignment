# EXP-2871 — Controller deconfound: suspension polarity is INVERTED (2026-04-22)

## Question
EXP-2870 found the envelope crossover hour is a controller signature
(all Loop patients stream_B_normal; stream_A_dominant patients all
Trio/OpenAPS). Was that signature driven by:
- (a) controller suspension/SMB behavior (algorithmic), or
- (b) underlying scheduled-basal structure differences?

## Method
Replace `actual_basal_rate` shift with **suspension depth shift**:
`suspension = scheduled_basal − actual_basal`. This isolates the
controller's CHOICE to deviate from schedule, removing the schedule
itself from the metric.

Compute, per patient × window: median suspension in top vs bottom
glucose tertile, take difference (`susp_shift_uph`). Positive shift
= controller suspends more when BG is elevated.

Windows: [1, 2, 3, 6, 12, 24, 48] h. Same selection criteria as
EXP-2851/2870.

## Result — Checks: **0/3 PASS** (all checks falsified, finding is the falsification)

### Per-patient classification (`all_positive` = suspends more in highs at every window)

| Controller | all_positive=True | all_positive=False |
|---|--:|--:|
| Loop | **0** | 6 |
| Trio | 5 | 3 |
| OpenAPS | 2 | 3 |

### Cohort suspension shift by window (positive = more suspension when elevated)

| window_h | N | frac_positive_shift | median_shift (U/h) |
|--:|--:|--:|--:|
| 1 | 4 | 0.75 | +0.086 |
| 2 | 7 | 0.57 | +0.056 |
| 3 | 8 | 0.62 | +0.053 |
| 6 | 11 | 0.73 | +0.066 |
| 12 | 13 | 0.54 | +0.030 |
| 24 | 25 | 0.36 | **−0.012** |
| 48 | 22 | 0.46 | −0.002 |

## Headline — controller suspension polarity is **OPPOSITE** between Loop and Trio

- **Loop (0/6 patients all_positive)**: suspends MORE in NORMAL/LOW
  envelopes than in elevated ones. Per-patient median shift is
  consistently negative across all windows (most patients between
  −0.03 and −0.48 U/h).
- **Trio (5/8 all_positive)**: suspends MORE in ELEVATED envelopes
  than in normal ones at every timescale.
- **OpenAPS (2/5 all_positive)**: mixed.

## Mechanism (proposed)

**Loop's suspension peaks in the normal/low envelope.** This is
straightforward closed-loop safety: when BG drops toward the bottom
tertile (hypo-adjacent), suspend basal to prevent overshoot. When BG
is elevated, deliver scheduled basal (no special suspension); meal
boluses + small temp basal corrections handle the high.

**Trio's suspension peaks in the elevated envelope.** This is the
**SMB-driven basal substitution** pattern: when BG is high, oref1
issues SMB micro-boluses to correct — those SMBs add IOB → to avoid
double-dose, basal is suspended underneath them. So high BG
co-occurs with high basal suspension *because the controller
substituted SMB for basal*, not because of safety hedging.

These are both rational, but **they create observationally OPPOSITE
basal-vs-glucose signatures**.

## Implications

1. **EXP-2870's "controller signature" finding is RE-CONFIRMED and
   sharpened**: it is causal at the algorithmic level. The crossover
   phenotype reflects an actual difference in how Loop vs Trio
   modulate basal in response to elevated BG.

2. **Any audition signal built on raw `actual_basal_rate` vs
   glucose envelope is observing a CONTROLLER-DEPENDENT MIXTURE of
   two distinct strategies** and cannot be interpreted as a
   "demand" signal without controller stratification.

3. **The basal_mismatch loader (audition signal #7) needs a
   controller flag**: a "high mismatch in elevated windows"
   reading means very different things for Loop (controller doesn't
   suspend in highs → schedule may genuinely be too aggressive) vs
   Trio (controller suspends as part of SMB substitution → not a
   schedule problem).

4. **For settings extraction / per-patient ISF and basal
   recommendations, Loop and Trio should use different
   deconfounding pipelines.** Pooling them masks the substitution
   pattern.

5. **Patient C re-interpretation**: she is Loop. Her near-zero
   delivered basal suggests she is in the *opposite* of the typical
   Loop pattern — her controller is suspending almost everywhere,
   not preferentially in low envelopes. That is consistent with
   a genuinely over-aggressive scheduled basal (the audition story
   stands).

## Caveats

- Small N: 6 Loop, 8 Trio, 5 OpenAPS, 6 unknown-controller. Cannot
  generalize beyond cohort.
- Suspension depth is censored at 0 (cannot deliver negative basal);
  positive suspension depth is bounded by `scheduled_basal`. Patients
  with low scheduled basal can show smaller absolute shifts.
- Glucose-envelope tertiles are within-patient — robust to
  inter-patient TIR differences.
- 4 of 25 patients have NaN controller (`j`, `k`, `ns-554...`,
  `ns-8ffa...`, `odc-39819048`); cohort sums to 21 with controller.

## Checks
- ❌ majority_uniformly_positive: only 7/25 (Loop drags this down)
- ❌ signature_dissolves: it does NOT dissolve (mean delta 0.83 between
  controller groups — well above 0.3 threshold)
- ❌ no_inverted_long_scale: 48h is at frac=0.46 (not ≥0.7)

All three checks were designed to test the "schedule-driven artifact"
hypothesis. All three falsifications are consistent with the
algorithmic-causation interpretation.

## Artifacts
- `externals/experiments/exp-2871_suspension_envelope.parquet`
- `externals/experiments/exp-2871_per_patient.parquet`
- `externals/experiments/exp-2871_summary.json`
- `docs/60-research/figures/exp-2871_suspension_phenotype.png`

## Follow-ups

- **EXP-2872**: subtract SMB-attributable basal suspension (when SMB
  > 0, treat suspension as substitution rather than safety) → does
  Trio's pattern collapse onto Loop's?
- **Audition matrix update**: add `controller` to AuditionInputs;
  change basal_mismatch interpretation rules per controller.
- **Vignette**: explain to Loop patients that "your basal is being
  suspended in elevated windows" is unusual and worth a closer
  look (this is patient C's archetype). For Trio patients, same
  observation is normal SMB behavior.
- **Stream-A ceiling re-examination**: if Loop and Trio differ this
  much in basal modulation strategy, the Stream A ceiling should
  be measured per-controller.
