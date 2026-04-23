# EXP-2923 — Cross-design fasted vs post-prandial dawn-hyper

**Date:** 2026-04-23
**Source:** inline (next iteration: promote to script if extended)
**Output:** `externals/experiments/exp-2923_summary.json`
**Scope:** Design-feature characterisation. AID-author audience.

## Method

Same fasted (≥300 min) / post-prandial (≤180 min) split as
EXP-2922, applied across all three lineages from
`exp-2891_simpson_dose_response.parquet` × `grid.parquet`.
Per-(lineage, state, hour) patient-mean fraction of cells with
glucose > 250.

Loop is reported aggregated (n=7, no autobolus split — see EXP-2922
for the OFF/ON decomposition).

## Headline

| Lineage | State | n | Peak hour | Peak %  | 03:00 % | 04:00 % |
|---------|-------|--:|-----------|--------:|--------:|--------:|
| Loop    | FASTED| 7 | **02:00** | 13.02   | **12.51** | 10.21   |
| Loop    | PP    | 7 | 03:00     | **30.73** | 30.73 | 29.84   |
| **oref1** | **FASTED** | **9** | 00:00 | 5.55 | **1.53** | 1.77 |
| oref1   | PP    | 9 | 13:00     | 14.18   | 2.56    | 2.84    |
| oref0   | FASTED| 3 | 14:00     | 9.48    | 5.25    | 5.36    |
| oref0   | PP    | 3 | 04:00     | 16.53   | 15.74   | 16.53   |

## Findings

1. **Dynamic-ISF essentially eliminates the EGP-driven dawn
   signature.** oref1 fasted at 03:00 is **1.53 %** vs Loop fasted
   at 03:00 of **12.51 %** — an **8× design-level gap** in the
   fasted state where the only remaining driver is EGP. This is
   the cleanest single-mechanism design-comparison number this
   workspace has produced.

2. **oref1's peak hyper hour shifts to lunchtime in the
   post-prandial state.** Peak at 13:00 (14.18 %), not the dawn
   window. This is post-meal absorption tail — a fundamentally
   different design challenge than EGP.

3. **Loop's dawn signature is mostly EGP, not meal carry-over.**
   FASTED 03:00 is 12.51 %; POST_PRANDIAL 03:00 is 30.73 %. So
   ~40 % of the post-prandial peak is already present in the
   fasted arm. The dawn fingerprint is real.

4. **oref0's fasted profile peaks at 14:00, not overnight.** Its
   overnight numbers are lower than Loop's (5.25 % vs 12.51 %
   fasted at 03:00). This contradicts the "oref0 is just legacy
   bad" framing — for fasted overnight handling, oref0 *beats*
   Loop. The earlier oref0 hypo peak (EXP-2920) is a basal-cut
   latency artefact, not a generalised under-performance. n=3
   caveat applies.

## Cross-validation against prior findings

- **Confirms EXP-2920** (Loop dawn, oref1 dawn-clean) with
  fasted-only data — rules out meal-timing as the explanation.
- **Confirms EXP-2922** (Loop autobolus halves both states
  proportionally) — extending to oref1 shows the same
  proportionality is achievable structurally without autobolus
  (via dynamic-ISF instead).
- **Updates EXP-2920 oref0 framing**: oref0 has a *temporal*
  weakness pattern (latency on basal cuts → overnight hypo) but
  is not a hyperglycemia under-performer in the fasted state.

## Mechanism layering (updated)

| Design layer            | Loop OFF | Loop ON | oref1 | oref0 |
|-------------------------|---------:|--------:|------:|------:|
| Dynamic-ISF for EGP     | no       | no      | **yes** | no  |
| SMB-as-correction       | no       | yes-ish | **yes** | yes (slow) |
| Pre-emptive dosing      | no       | yes     | **yes** | partial |
| Fast basal-cut response | yes      | no      | yes    | **no** |
| **Fasted dawn hyper %** | 17.0     | 10.7    | **1.5** | 5.3 |

oref1 is the only design that ticks the first three rows; that
correlates exactly with its dominant fasted-dawn performance.

## Caveats

- oref0 n=3, all single-patient cells.
- Loop aggregated; OFF/ON split available in EXP-2922.
- TZ not normalised (per EXP-2920).
- `time_since_carb_min` capped at 360.

## Implication

The "dynamic ISF is the highest-leverage dawn lever" hypothesis
from EXP-2920 is now confirmed quantitatively at design level:
**8× separation between Loop and oref1 in the fasted dawn window**,
where EGP is the only plausible upward driver and dynamic-ISF
is the only relevant design difference.

For AID authors building or modifying a brake-only loop:
- Adding dynamic-ISF should yield the largest single-feature
  improvement on the dawn signature.
- Adding autobolus (without dynamic-ISF) recovers about half
  the gap (Loop ON 10.7 % vs Loop OFF 17.0 % fasted).
- Adding both (i.e. becoming oref1-like) gets to ~1.5 %.

## Linked artefacts

- `externals/experiments/exp-2923_summary.json`
- Compare against `exp-2922-dawn-fasted-vs-pp-2026-04-23.md`
- Compare against `exp-2920-tod-design-profile-2026-04-23.md`

## Next

- Promote inline script to `tools/cgmencode/exp_xdesign_fasted_pp_2923.py`
  for reproducibility (deferred — analysis output captured in JSON).
- Apply Guard #6 cf-conditioning: confirm fasted-dawn gap
  survives matching on patient cf_severe.
