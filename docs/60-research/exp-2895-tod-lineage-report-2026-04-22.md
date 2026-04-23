# EXP-2895 — TOD × lineage protection report

**Date:** 2026-04-22
**N:** 3,912 descent events, 19+ patients across 4 lineage groups
**Source:** `tools/cgmencode/exp_tod_lineage_2895.py`
**Output:**
- `externals/experiments/exp-2895_tod_lineage.parquet`
- `externals/experiments/exp-2895_summary.json`

## Question

Does oref1's setting-independence (EXP-2891: protection 0.63→0.72 across
aggressiveness terciles) extend to **hour of day**? Or do certain
lineages have an hour-of-day Achilles heel?

## Result — three distinct TOD signatures

| Lineage          | n    | TOD chi² p | TOD range (severe %) | Pattern                   |
|------------------|------|-----------|----------------------|---------------------------|
| **Loop (iOS)**   | 1185 | 0.52      | **5.1 pp**           | TOD-invariant             |
| oref0 (legacy)   |  468 | **0.020** | **19.5 pp**          | Heavy night degradation   |
| oref1 (modern)   | 1270 | **0.008** | **11.2 pp**          | Moderate night degradation|
| unknown (mixed)  |  906 | 0.66      | 4.5 pp               | TOD-invariant (mixture)   |

## Cell-level severe-hypo rates (BG nadir < 54 mg/dL)

| Lineage / TOD  | morning | afternoon | evening | night |
|----------------|--------:|----------:|--------:|------:|
| Loop           |   41.3% |     41.2% |   36.2% | 40.2% |
| oref0          |   50.3% |     43.4% |   49.3% |**62.9%**|
| oref1          |   30.1% |     26.1% |   26.3% |**37.3%**|

## Interpretation

### Loop is the TOD-stable lineage
Loop's severe-hypo rate stays in a ~5 pp band across all four day
periods. The anticipatory dosing model (predicted-glucose-to-low) and
opt-in automatic bolus channel produce hour-invariant protection.

### oref0 is doubly exposed
Already setting-sensitive (EXP-2891: 0.13→0.72 across terciles), it is
also hour-sensitive: night severe-hypo rate (63%) is ~20 pp worse than
afternoon (43%). Two compounding axes of vulnerability.

Mechanism candidate: oref0's basal-cut response is slow (EXP-2892
utilization 20% at conservative tier) AND has no SMB channel
(EXP-2893). At night, when the patient is not interacting and meals
are absent, the controller's reactive-only behaviour has no fallback.

### oref1 partially generalises EXP-2891
The setting-independence finding (EXP-2891) does NOT transfer cleanly
to hour-of-day. oref1 still shows a significant night degradation
(p=0.008, +11 pp). However, the night rate (37%) is still better than
oref0's daytime baseline. Lineage helps, but does not eliminate the
diurnal pattern.

## Implication for audition matrix

Add a **time-of-day audition channel** for legacy-lineage patients:
- oref0 patients warrant `night_protection_degraded` flag if
  `nighttime_severe_rate - daytime_severe_rate > 0.15`.
- oref1 patients with this gap >0.10 should also be flagged but with
  lower severity.
- Loop patients do not need this flag.

This is a **conditional** flag — the threshold differs by lineage
(Loop already showed in EXP-2873/2872 why one-size-fits-all
thresholds bias decisions).

## Caveats

- "unknown" lineage bucket holds patients without a controller field
  in EXP-2891; their TOD-invariance is not informative (mixture of
  algorithms washes out signal).
- Severe rate is observed (post-AID), not counterfactual. We cannot
  separate "AID degrades at night" from "physiology demands more at
  night and AID can't keep up". The contrast across lineages, holding
  patient-set fixed within each, is the relevant signal.
- 4 TOD bins (morning/afternoon/evening/night) are coarse. A
  follow-up could use hourly bins to pinpoint dawn vs late-night.

## Linked artefacts

- `externals/experiments/exp-2891_simpson_dose_response.parquet`
  (lineage labels)
- `externals/experiments/exp-2881_evening_drivers.parquet`
  (descent events)
- `docs/60-research/exp-2891-simpson-dose-response-report-2026-04-22.md`
- `docs/60-research/exp-2892-mechanism-report-2026-04-22.md`
- `docs/60-research/exp-2894-loop-smb-equivalence-report-2026-04-22.md`
- `docs/60-research/deconfounding-toolkit-2026-04-22.md` (§2.10)

## Next experiments

- EXP-2896: hourly resolution, identify exact dawn/dusk inflection.
- EXP-2897: counterfactual replay (EXP-2889 method) within each TOD
  bin. Does the AID *prevent* a higher fraction at certain hours, or
  is the absolute night demand simply larger?
- Audition wiring: `night_protection_degraded` flag with lineage-
  conditional thresholds.
