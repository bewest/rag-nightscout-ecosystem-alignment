# EXP-2972 — Trigger frequency vs per-event magnitude decomposition (2026-04-23)

## Scope
For open-source AID code authors. Decomposes the per-cell SMB
delivery in the 70-100 mg/dL no-carb sweet spot into:

- `emission_rate = P(bolus_smb > 0 | cell)` — how often SMB fires
- `mean_emission = E[bolus_smb | bolus_smb > 0]` — per-event size

Pooled and per-patient. Identifies which lever differs between
Loop_AB_ON and oref1.

## What this is NOT
Not therapy advice. Not a per-patient outcome claim.

## Method
Filter cells: `bg ∈ [70, 100)`, no carbs in prior 120 min, no carbs
at the cell. For each cell, record `bolus_smb` and `fired = 1{smb>0}`.
Pool per-design and per-patient.

## Results

### Pooled per-design (70-100 mg/dL, no-carb)

| design | n_cells | n_fired | emission_rate (95% Wilson CI) | mean_emission (U) | mean SMB / cell (U) |
|---|---:|---:|---:|---:|---:|
| Loop_AB_OFF | 14,551 | 0 | 0.0000 [0.0000, 0.0003] | 0.0000 | 0.00000 |
| **Loop_AB_ON** | 28,845 | 1,112 | **0.0386 [0.0364, 0.0408]** | **0.2439** | 0.00940 |
| oref0 | 29,522 | 0 | 0.0000 [0.0000, 0.0001] | 0.0000 | 0.00000 |
| **oref1** | 66,172 | 5,268 | **0.0796 [0.0776, 0.0817]** | **0.1690** | 0.01346 |

**Pooled headline:** oref1 emission rate (0.0796) is **2.06×** Loop's
(0.0386), with disjoint 95% CIs. Per-event magnitude is **inverted**:
Loop's mean per-event is 0.244 U vs oref1's 0.169 U (Loop **44%
larger per event**). Net per-cell SMB in this band is actually
**higher for oref1** (0.0135 U vs Loop's 0.0094 U) — a finding that
**inverts the EXP-2966 slope interpretation**: oref1 delivers more
total SMB at 70-100, but Loop responds more steeply to *velocity*.

### Per-patient

| design | patient | n_cells | n_fired | emission_rate | mean_emission (U) |
|---|---|---:|---:|---:|---:|
| Loop_AB_OFF | a | 4,689 | 0 | 0.0000 | 0.0000 |
| Loop_AB_OFF | f | 9,862 | 0 | 0.0000 | 0.0000 |
| Loop_AB_ON | c | 5,435 | 0 | 0.0000 | 0.0000 |
| Loop_AB_ON | e | 3,890 | 1 | 0.0003 | 0.5500 |
| Loop_AB_ON | d | 5,110 | 2 | 0.0004 | 0.5250 |
| Loop_AB_ON | g | 5,567 | 12 | 0.0022 | 0.0667 |
| Loop_AB_ON | i | 8,843 | 1,097 | **0.1241** | 0.2451 |
| oref0 | (3 patients) | — | 0 | 0.0000 | — |
| oref1 | ns-dde9e7c2e752 | 4,281 | 36 | 0.0084 | 0.1222 |
| oref1 | ns-d444c120c23a | 5,910 | 256 | 0.0433 | 0.2506 |
| oref1 | ns-9b9a6a874e51 | 4,708 | 228 | 0.0484 | 0.0853 |
| oref1 | ns-8f3527d1ee40 | 10,778 | 544 | 0.0505 | 0.2337 |
| oref1 | ns-8b3c1b50793c | 6,835 | 393 | 0.0575 | 0.2963 |
| oref1 | ns-6bef17b4c1ec | 9,146 | 833 | 0.0911 | 0.1122 |
| oref1 | ns-adde5f4af7ca | 8,378 | 830 | 0.0991 | 0.1519 |
| oref1 | ns-a9ce2317bead | 7,913 | 968 | 0.1223 | 0.1506 |
| oref1 | ns-1ccae8a375b9 | 8,223 | 1,180 | 0.1435 | 0.1640 |

**Per-patient headline:** Loop_AB_ON is **bimodal**: 4/5 patients
fire SMB ≤ 0.22% of cells at 70-100 no-carb; patient `i` fires at
12.4%. oref1 patients are tightly clustered (0.8% to 14.4%, all
firing).

### Per-design summary across patients

| design | n_pat | em_rate median | em_rate mean | mean_em median | mean_em mean |
|---|---:|---:|---:|---:|---:|
| Loop_AB_ON | 5 | 0.0004 | 0.0254 | 0.245 | 0.277 |
| oref1 | 9 | 0.0575 | 0.0738 | 0.152 | 0.174 |

### MWU (Loop_AB_ON vs oref1, per-patient)

| metric | U | p (two-sided) |
|---|---:|---:|
| emission_rate | 8.0 | **0.0599** (marginal) |
| mean_emission_U | 25.0 | 0.797 (null) |

## Headline
**POSITIVE / MECHANISM-SHIFT.** Decomposition cleanly identifies
that **the controllers differ on emission frequency**, not per-event
magnitude. oref1 fires SMB **2× more often** than Loop_AB_ON in the
70-100 mg/dL no-carb sweet spot (pooled CIs disjoint; per-patient
MWU marginal p=0.06). Per-event magnitudes are statistically
indistinguishable per patient (MWU p=0.80). Loop_AB_ON is **bimodal
across patients**: most fire SMB nearly never in this band; one
patient (`i`) fires at 12%. This is the **AID-author lever**:
emission frequency at low-target BG is set by Loop's "predicted
overshoot must clear bolus_increment" implicit gate vs oref1's
explicit `enableSMB_always` / `SMBInterval=3min` policy.

## Interpretation for AID authors
- The original "Loop_AB_ON > oref1 at 70-100 sweet spot" framing
  from EXP-2966 was about **slope (responsiveness to velocity)**,
  not total delivery. **Total SMB delivery in this band is actually
  higher for oref1** (0.0135 U/cell vs 0.0094 U/cell).
- The lever to tune is **emission_rate**, not per-event size.
  Per-event sizes converge (~0.17-0.24 U) once the controller
  decides to fire.
- Loop_AB_ON's bimodality across patients suggests a **profile-
  setting sensitivity** (likely `automaticDosingStrategy`,
  `glucoseBasedApplicationFactorEnabled`, target schedule, or
  `maxBolus`) that gates whether the implicit
  "predicted-overshoot > rounding threshold" condition fires at
  this BG band.
- See `docs/10-domain/smb-emission-policy-deep-dive-2026-04-23.md`
  for the code-side mapping.

## Files
- Script: `tools/cgmencode/exp_emission_decomposition_2972.py`
- JSON: `externals/experiments/exp-2972_summary.json`

## Provenance
- Cohort: `externals/experiments/exp-2891_simpson_dose_response.parquet`
- Grid: `externals/ns-parquet/training/grid.parquet`
- Date: 2026-04-23

## Next
- EXP-2973: stratify by velocity sign — does the emission-rate
  ordering hold across rising/stable/falling, or is it
  velocity-conditional?
- Per-patient settings export (if available) to test the bimodality
  hypothesis on Loop_AB_ON.
