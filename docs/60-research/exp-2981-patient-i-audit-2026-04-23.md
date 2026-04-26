# EXP-2981 — Patient `i` representativeness audit (Loop_AB_ON)

**Date**: 2026-04-23
**Audience**: Open-source AID code authors
**Scope**: Audit baseline metrics and rising-stratum SMB
emission counts for the 5 Loop_AB_ON patients (c, d, e, g, i).
Test whether patient `i` — who supplies 361/363 of the events
in EXP-2979's pooled Loop arm — is representative of the
cohort or an outlier on cohort-defining metrics.
**What this is NOT**: a per-patient therapy critique; not a
TIR comparison across designs.

## Result — STRONG OUTLIER on the EXP-2979 stratum

Patient `i` differs from c/d/e/g on **9 of 17 baseline / event-count
metrics** by Tukey-IQR (1.5 × IQR) test:

| Metric | i | others median | others IQR | outlier |
|---|---:|---:|---:|---|
| frac_in_70_100 | **0.194** | 0.131 | 0.023 | **YES** |
| frac_below_70  | **0.107** | 0.025 | 0.021 | **YES** |
| smb_count      | **13,724** | 10,766 | 1,306 | **YES** |
| smb_dose_mean_U | **0.45** | 0.25 | 0.09 | **YES** |
| n_5min_in_70_100 | **9,014** | 5,774 | 974 | **YES** |
| n_5min_in_70_100_rising | **1,222** | 498 | 268 | **YES** |
| n_smb_in_70_100 | **1,115** | 1.5 | 5.25 | **YES** |
| n_smb_in_70_100_rising | **370** | 1 | 0.25 | **YES** |
| n_smb_in_70_100_rising_nocarb | **362** | 0.5 | 1 | **YES** |
| TIR 70-180 | 0.599 | 0.703 | 0.118 | no (just below) |
| frac_above_250 | 0.115 | 0.073 | 0.035 | no (just above) |

## Why c/d/e/g fire ~0 SMB at 70-100 — it is not "they don't go there"

Patient `g` spends 7,798 5-min readings in 70-100; patient `c`
spends 5,879. They **descend into this band frequently**. They
just **never fire SMB there**:

| Patient | n_5min_in_70_100 | of which rising | SMBs fired | SMBs fired (rising) |
|---|---:|---:|---:|---:|
| c | 5,879 | 617 | 0 | 0 |
| d | 5,669 | 294 | 2 | 1 |
| e | 4,534 | 379 | 1 | 1 |
| g | 7,798 | 652 | 18 | 1 |
| **i** | **9,014** | **1,222** | **1,115** | **370** |

The other four patients evidently have some setting or behavior
(temp target, override, glucoseBasedApplicationFactor curve,
maxBolus floor) that **suppresses SMB at low BG**. Patient `i`
does not have this suppression. This is a **policy difference,
not a use-pattern difference**.

## Patient `i`'s broader profile

- Mean BG 150 mg/dL (cohort median 154; not unusual)
- TIR 70-180 = 60.0% (cohort median 70.3%) — lowest in the cohort
- Hypo (<70) = **10.7%** (cohort median 2.5%) — **4× cohort**
- Time >250 = 11.5% (cohort median 7.3%) — high
- SMB dose mean 0.45 U (cohort median 0.25 U) — **fires larger SMBs**
- 76 SMBs/day (cohort median 60) — fires more often

Profile picture: `i` runs **wide** — more low time, more very-high
time, more total SMB activity, larger per-SMB dose. This is
consistent with either an aggressive override / lower BG target,
disabled `glucoseBasedApplicationFactor`, or higher
`maxPartialApplicationFactor`. The dataset does not contain the
settings to confirm which.

## Verdict — `i` is an OUTLIER on the EXP-2979 metric

Patient `i` is the **only Loop_AB_ON patient who fires SMBs in
the 70-100 rising no-carb stratum**. The pooled "Loop_AB_ON
overshoot 10.7% in the rising sweet spot" claim is therefore a
**single-patient claim** about an aggressive Loop configuration,
not a cohort-level Loop-vs-oref1 mechanism comparison.

The mechanism prediction (magnitude lever ⇒ overshoot risk) is
**still consistent** with what `i` shows — but the cohort cannot
test it. To test this prediction at cohort level, we would need
either (a) more Loop patients with `i`'s configuration, or
(b) a stratum where c/d/e/g actually fire SMB
(see EXP-2985: at 100-140 they all fire and overshoot rates are
**broadly similar**).

## Source / data
- `tools/cgmencode/exp_patient_i_audit_2981.py`
- `externals/experiments/exp-2981_summary.json`
- Cohort: 5 Loop_AB_ON patients × ~45,000 5-min rows each
