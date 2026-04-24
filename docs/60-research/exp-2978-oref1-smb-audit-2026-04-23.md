# EXP-2978 — Per-patient oref1 sustained-high SMB audit (`enableSMB_always`)

**Date**: 2026-04-23
**Audience**: Open-source AID code authors
**Scope**: Per-patient em_rate of SMB at sustained-high BG (≥180
mg/dL for 60 min preceding) in no-carb context, looking for an
outlier patient consistent with `enableSMB_always=false`.
**What this is NOT**: a profile-config audit (we infer from
behavior, not from settings JSON).

## Hypothesis

EXP-2972 noted oref1 cohort had a wide em_rate spread; we
hypothesized one patient with em_rate ≪ median would indicate
`enableSMB_always` off (SMB only fires on rising/PP, not at
sustained-high alone).

## Result — NEGATIVE

All 9 oref1 (= Trio) patients fire SMB at sustained-high BG. Range
**0.11 – 0.34**, median 0.255, MAD 0.084. Lowest patient
(`ns-1ccae8a375b9`, em_rate 0.110) is **3× above** the outlier
threshold (0.064). No patient behaves like SMB-disabled at
sustained-high.

| patient_id      | n_cells | em_rate | smb:bolus ratio |
|-----------------|--------:|--------:|----------------:|
| ns-1ccae8a375b9 |     228 |  0.110  | 0.74 |
| ns-8b3c1b50793c |     765 |  0.129  | 0.48 |
| ns-dde9e7c2e752 |    2996 |  0.160  | 0.53 |
| ns-9b9a6a874e51 |    1222 |  0.242  | 0.86 |
| ns-8f3527d1ee40 |     255 |  0.255  | 0.79 |
| ns-6bef17b4c1ec |    1127 |  0.259  | 0.86 |
| ns-adde5f4af7ca |    1884 |  0.287  | 0.68 |
| ns-a9ce2317bead |    1748 |  0.339  | 0.97 |
| ns-d444c120c23a |    2694 |  0.341  | 0.93 |

The 3× spread is **patient-level dosing intensity**, not gating.
The smb:bolus ratio (48% – 97%) confirms heavy SMB use across the
whole cohort; even the lowest-em_rate patient sources 74% of bolus
from SMB.

## Interpretation for AID authors

- The previously suspected EXP-2972 anomaly (em_rate 0.008) was
  in the **70-100 sweet spot**, not at sustained-high — re-checking
  per-band em_rate per patient is the proper follow-up
  (deferred to a later experiment).
- `enableSMB_always` does NOT appear off in any cohort patient.
- Per-patient sustained-high em_rate spread (3×) is best
  attributed to ISF/CR/profile heterogeneity — Lever 4 (per-patient
  insulin-aggressiveness presets) territory, not a gating switch.

## Code refs

- `externals/AndroidAPS/plugins/aps/src/main/kotlin/.../DetermineBasalSMB.kt:66-103`
  (enable_smb gate with `enableSMB_always`, `enableSMB_with_COB`,
  `enableSMB_with_temptarget`, `enableSMB_after_carbs`)
- `externals/AndroidAPS/core/data/.../SMBDefaults.kt`
  (default settings; `SMBInterval=3 min`, `maxSMBBasalMinutes=30`)

## Source / data

- Script: `tools/cgmencode/exp_oref1_smb_audit_2978.py`
- Output: `externals/experiments/exp-2978_summary.json`
