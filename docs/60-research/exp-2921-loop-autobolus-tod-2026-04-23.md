# EXP-2921 — Loop TOD profile split by autobolus on/off

**Date:** 2026-04-23
**Source:** `tools/cgmencode/exp_loop_autobolus_tod_2921.py`
**Scope:** Design-feature characterisation. AID-author audience.
NOT therapy advice.

## Method

Reuses `exp-2920_hourly.parquet` per-patient hourly fractions.
Splits Loop patients by EXP-2919 autobolus mapping (derived
from `bolus_smb` column):
- **autobolus OFF**: a, f (n=2)
- **autobolus ON**: c, d, e, g, i (n=5)

Patient-mean within (autobolus, hour) before pooling. 95 %
bootstrap CI (2 000 resamples).

## Headline

| Subgroup        | Peak HYPO hour | Peak HYPO % | Peak HYPER hour | Peak HYPER %    |
|-----------------|----------------|------------:|-----------------|----------------:|
| Loop autobolus OFF (n=2) | 09:00 | 2.41 % | **04:00** | **30.65 %** |
| Loop autobolus ON  (n=5) | 09:00 | 2.60 % | 03:00     | **14.30 %**     |

**Counter-hypothesis confirmed.** Autobolus more than halves
Loop's dawn-hyperglycemia signature (30.6 % → 14.3 % at peak).
Morning hypo signature (09:00, ~2.5 %) is **identical** between
groups — a Loop-design phenomenon independent of autobolus.

## Mechanism interpretation

| Observation | Interpretation |
|-------------|----------------|
| OFF dawn-hyper 2× worse than ON | Autobolus pre-empts EGP rise; brake-only Loop cannot |
| OFF and ON have same 09:00 hypo | Morning bolus stacking is upstream of autobolus path |
| OFF has 9 min basal-cut latency (EXP-2919) vs 31 min ON | OFF responds *faster* to drops but doesn't pre-empt rises |
| Both signatures persist | Loop's effective design is two distinct policies |

This is the **complementary mechanism story** to EXP-2919:
autobolus-ON Loop trades faster basal-cut latency for better
dawn-hyper protection. autobolus-OFF Loop has the opposite trade.
Same patients in EXP-2916/2918 — different design fingerprints.

## Caveats

- **n=2 vs n=5** — bootstrap CIs are wide; OFF cell often
  degenerate (per Toolkit §2.8 small-n caveat).
- The 30.65 % at 04:00 OFF peak is driven by both patients
  (consistent direction); not a single-patient artefact.
- Hour-of-day not TZ-normalised (per EXP-2920 caveat).
- Autobolus mapping is empirical (derived from observed SMB
  delivery), not configuration-confirmed. Some "ON" patients
  may have autobolus-enabled-but-rarely-fired.

## Implication for AID authors

- **Autobolus is the dawn-hyper intervention** in Loop's design
  space, not a basal-cut accelerator.
- Loop **without autobolus is fundamentally a brake-only design**
  for hyperglycemia handling — the dawn fingerprint then
  approaches what one might expect from a no-SMB controller.
- A Loop variant that adds autobolus for dawn but keeps fast
  basal-cut latency from the OFF configuration would dominate
  both presets here.
- For comparison: oref1's 4.29 % peak (EXP-2920) is **3.3× lower**
  than Loop autobolus-ON's 14.30 % — dynamic-ISF and SMB-as-
  correction together still dominate autobolus alone.

## Linked artefacts

- `externals/experiments/exp-2921_summary.json`
- `docs/visualizations/exp-2921-loop-autobolus-tod.png`

## Next

- EXP-2922: post-prandial vs basal-fasted decomposition of the
  03–04:00 signature (was the patient eating after 21:00?).
- Document the "Loop is two designs" finding explicitly in any
  cross-design comparison table going forward.
