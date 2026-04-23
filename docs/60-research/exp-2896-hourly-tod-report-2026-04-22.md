# EXP-2896 — hourly TOD × lineage report

**Date:** 2026-04-22 (overnight)
**N:** 2,923 events with known lineage (3,829 total minus 906 unknown)
**Source:** `tools/cgmencode/exp_hourly_tod_2896.py`
**Outputs:** `externals/experiments/exp-2896_hourly.parquet`, `_summary.json`

## Refines EXP-2895

EXP-2895 used 4 coarse TOD bins. EXP-2896 resolves to 24 hourly bins
to identify the **exact hours** of degradation per lineage.

## Day vs Night (08:00–22:00 vs 22:00–08:00) severe-hypo rates

| Lineage          | Day rate | Night rate | Night excess |
|------------------|---------:|-----------:|-------------:|
| **Loop (iOS)**   |  40.1%   |  38.9%     | **−1.2 pp**  |
| oref1 (modern)   |  27.7%   |  33.5%     | +5.8 pp      |
| oref0 (legacy)   |  47.3%   |  57.3%     | **+10.0 pp** |

## Worst hours per lineage (≥5 events)

| Lineage          | #1 hour      | #2 hour      | #3 hour      |
|------------------|-------------|-------------|-------------|
| Loop (iOS)       | 04:00 (54%) | 05:00 (54%) | 09:00 (51%) |
| oref0 (legacy)   | 00:00 (82%) | 02:00 (74%) | 05:00 (67%) |
| oref1 (modern)   | 03:00 (54%) | 02:00 (43%) | 08:00 (41%) |

## Lineage signatures — three different shapes

### Loop: focal dawn-phenomenon blip (04:00–05:00)
Loop's overnight (00:00–03:00) severe rates are 27–41% — actually *better*
than its daytime mean. The single elevated cluster is 04:00–05:00 (54%),
the canonical dawn surge. The morning recovery period (08:00–11:00) is
mildly elevated (32–51%) likely from fasting + dawn-phenomenon insulin
demand. Loop's day-night excess is **−1.2 pp** — net TOD-invariant.

### oref0: night-long catastrophe (00:00–06:00)
Late-night/early-AM is uniformly elevated for oref0:
hour 0 = 82%, hour 1 = 58%, hour 2 = 74%, hour 3 = 65%, hour 5 = 67%.
This is consistent with EXP-2892's mechanism finding (low basal-cut
utilization, 20%) compounded by patient inactivity and absence of
manual corrections. Day rates (47%) are also bad but night (57%) is
materially worse.

### oref1: focal 03:00 spike + small day-night drift
oref1 shows a 03:00 spike (54%) with cleaner hours 04:00–07:00 (19–36%).
This pattern suggests dawn-phenomenon onset at 03:00 that the modern
controller still mostly handles by 04:00. The day-night excess is
+5.8 pp, half of oref0.

## Implications

### For oref0 patients (algorithm migration triage)
The night-long degradation suggests the controller is essentially
inert during sleep. Two non-mutually-exclusive remediations:
1. Lower scheduled basal 22:00–06:00 substantially (≥30%) so that
   the controller's pass-through behaviour is less dangerous.
2. Migrate to oref1-family or Loop. Both halve the night excess.

### For Loop patients (dawn tuning)
Loop's 04:00–05:00 blip suggests the dawn-phenomenon model under-
anticipates demand. Possible levers:
- ISF `dawn_basal_offset` if the install supports it.
- Check whether glucose-momentum target tracks dawn rise.

### For oref1 patients (focal 03:00 audit)
03:00 spike is unique to oref1 and may reflect SMB momentum from
late-evening meals. Worth auditing whether `enableSMB_after_carbs`
extends too late.

## Audition matrix

EXP-2895 added `night_protection_degraded` with a 4-bin definition.
This experiment supports keeping that flag's threshold but adds a
finer-grained variant for clinical reports:
- `dawn_phenomenon_loop`: Loop patients with hours 04–06 severe rate
  ≥ 1.5× their daytime baseline.
- `night_inertia_oref0`: oref0 patients with any night hour ≥ 70% severe.
Wiring deferred to keep audition-matrix surface stable.

## Caveats

- Per-hour cell sizes for oref0 are small (n = 9–40). Hour-level rates
  are noisy; the lineage-level pattern is the robust signal.
- Severe rate is observed (post-AID); not counterfactual. The Loop
  04:00 blip could reflect **physiological dawn surge alone** rather
  than algorithm gap. Counterfactual replay (next experiment) needed
  to separate.
- "unknown" lineage bucket excluded from day/night analysis.

## Linked artefacts

- `docs/60-research/exp-2895-tod-lineage-report-2026-04-22.md`
- `docs/60-research/exp-2891-simpson-dose-response-report-2026-04-22.md`
- `tools/cgmencode/exp_hourly_tod_2896.py`

## Next experiment

EXP-2897: hourly counterfactual replay (extends EXP-2889 mechanism to
24 bins). Question: does the AID *prevent* a higher fraction of would-be
severe events at certain hours, or is night demand simply larger?
