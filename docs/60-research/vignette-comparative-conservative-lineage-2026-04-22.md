# Comparative vignette — conservative oref0 vs conservative oref1

**Date:** 2026-04-22
**Source experiments:** EXP-2891 (Simpson dose-response), EXP-2892 (hypo mechanism), EXP-2893 (hyper mechanism), EXP-2889 (counterfactual)
**Audition flags:** `lax_braking_controller_efficacy`, `smb_absent_algorithm_gap`

## Why this comparison matters

Both patients sit in the **conservative** aggressiveness tercile (modest
total daily insulin relative to body demand). Conventional wisdom would
predict similar outcomes: same input class → same output class.

**They don't.** The lineage of the AID algorithm — which automatic-
correction tools the controller has access to — produces a 4.9× difference
in severe-hypo protection at identical scheduling aggressiveness.

This is the cleanest available demonstration that **lineage acts as an
effect-modifier**, not just a level shift. The conservative-oref0 patient
is the worst-off in the whole 19-patient cohort despite running similar
scheduled basal magnitudes to the conservative-oref1 patient.

## The pair

| Field                    | `odc-86025410`              | `ns-dde9e7c2e752`           |
|--------------------------|-----------------------------|-----------------------------|
| Controller               | OpenAPS                     | Trio                        |
| Lineage                  | **oref0 (legacy)**          | **oref1 (modern)**          |
| Tercile                  | conservative                | conservative                |
| Aggressiveness rank      | 5 / 19                      | 9 / 19                      |
| Mean scheduled basal     | 0.34 U/h                    | 0.26 U/h                    |
| Descent events           | 271                         | 120                         |
| Counterfactual severe    | 70 %                        | 91 %                        |
| Observed severe          | 58 %                        | 30 %                        |
| **AID severe protection**| **12.5 %**†                 | **60.8 %**†                 |
| Braking ratio (descent)  | 0.96 (almost no cut)        | 0.025 (near-full suspension)|
| SMB delivery (rise)      | 0.00 U                      | 0.67 U                      |
| Excess-basal share       | 17 %                        | 0.1 %                       |
| User-bolus share         | 83 %                        | 75 %                        |

## Mechanism decomposition

### Hypo side — `EXP-2892` capacity vs utilization

Both patients have similar **basal-cut capacity** (small scheduled basal
≈ small ceiling on how much insulin the AID can withhold during a
descent). What differs is **utilization**:

- `odc-86025410` (oref0): when BG is descending, the controller still
  delivers 96 % of scheduled basal. Capacity available, not used.
- `ns-dde9e7c2e752` (oref1): when BG is descending, only 2.5 % of
  scheduled basal flows. The same small ceiling is used aggressively.

The audition flag for the oref0 patient is
`lax_braking_controller_efficacy` (EXP-2890). The diagnostic note in
the flag rationale points to controller responsiveness, not settings,
as the lever.

### Hyper side — `EXP-2893` channel taxonomy

Both patients see comparable BG rises (≈ 240 mg/dL cumulative across
post-nadir windows), so they have similar correction *demand*. The
*supply* differs:

- `odc-86025410` (oref0): zero SMB delivery; 100 % of correction is
  user-driven bolus + a small excess-basal trickle. Hyper correction
  cannot happen between user interactions.
- `ns-dde9e7c2e752` (oref1): SMB contributes 25 % of correction insulin;
  user remains primary (75 %), but the AID provides a baseline of
  micro-corrections.

The audition flag for the oref0 patient is `smb_absent_algorithm_gap`
(this PR). The diagnostic note routes to algorithm migration or, for
Loop users, the auto-bolus feature toggle.

## Therapy-discussion implications

**†Protection metric disclosure:** The AID severe protection values use the `aid_protection_severe` field from EXP-2891 aggregate model (which may differ from direct calculation). Direct calculation using (cf_severe − obs_severe) / cf_severe yields: oref0 patient = 17.8%, oref1 patient = 67.0%, shifting the ratio to 3.8×. Core findings (mechanism, channel gaps, audition flags) remain unchanged.

For `odc-86025410`:
- Settings adjustments (ISF/CR/basal) cannot fully close the gap because
  the limiting factor is **algorithm utilization**, not parameter values.
- TBR<54 = 3.9 % (≈ 56 min/day severe hypo, 4× the ADA guideline) is
  driven by the controller passing through scheduled basal during
  descents.
- Counterfactual estimate from EXP-2889 + EXP-2891: migration to an
  oref1-family controller (Trio or AAPS) at current settings would
  raise protection from 12.5 % to ~60 % — projected severe TBR drop
  56 → 25 min/day.
- A safer interim measure if migration is deferred: lower scheduled
  basal during the high-risk hours (typically overnight) so that the
  oref0 controller's pass-through behaviour is materially less harmful.

For `ns-dde9e7c2e752`:
- Already realising the lineage benefit; the residual 30 % observed
  severe rate is dominated by event physics, not algorithm shortfall.
- Setting aggressiveness up by ~1 tercile (carb ratio tighter, ISF
  slightly lower) would raise correction performance further; the
  conservative tercile leaves room.

## Why these two patients are the comparative pair

- Same tercile (conservative). Holds settings-aggressiveness roughly
  fixed, so the lineage signal isn't confounded with "uses more insulin".
- Different lineage (oref0 vs oref1). Isolates the algorithm dimension.
- Same controller family (OpenAPS algorithms — both run oref-line code,
  not Loop). Removes the Loop-vs-oref controller-implementation
  confound.
- Both have ≥ 100 descent events. Per-patient estimates are stable.
- Both have similar bg_rise totals. Hyper *demand* matched, so channel
  comparisons aren't confounded by event severity.

## Caveats

- n = 1 per cell. The cohort-level finding (EXP-2891, p=0.018) is what
  generalises; the vignette pair is illustrative.
- Both patients are conservative; the dose-response slope of oref0
  (EXP-2891: 0.13 → 0.72 across terciles) means an aggressive oref0
  patient would not show this protection deficit.
- We cannot rule out a controller-platform confound (OpenAPS hardware
  vs Trio iOS) absent direct A/B migration data.

## Linked artefacts

- `docs/60-research/exp-2891-simpson-dose-response-report-2026-04-22.md`
- `docs/60-research/exp-2892-mechanism-report-2026-04-22.md`
- `docs/60-research/exp-2893-hyper-channels-report-2026-04-22.md`
- `docs/60-research/exp-2894-loop-smb-equivalence-report-2026-04-22.md`
- `docs/60-research/vignette-odc-86025410-conservative-oref0-safety-2026-04-22.md`
- `docs/60-research/deconfounding-toolkit-2026-04-22.md` (§2.10)
- `tools/cgmencode/production/audition_matrix.py`
  (`lax_braking_controller_efficacy`, `smb_absent_algorithm_gap`)
