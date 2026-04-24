# EXP-2992: Add `algorithm_mode` column to cohort schema

**Date**: 2026-04-23
**Audience**: open-source AID code authors; future experiment authors.
**Scope**: add an `algorithm_mode` column to the per-patient summary
parquets so that future experiments can stratify on the
**(platform, algorithm, AB-state)** triple rather than the
ambiguous historical `controller` label.
**What this is NOT**: not a re-derivation of the underlying grid;
not a change to the raw NS export schema; not retroactive renaming
of the `controller` column (kept for back-compat).

---

## Background

EXP-2986 found that the three ODC patients
(`odc-74077367`, `odc-86025410`, `odc-96254963`) run the AAPS Android
app on the **oref0** algorithm (no SMB, no UAM, no dynamic ISF),
even though earlier code paths labeled their `controller` as
`OpenAPS`. EXP-2986 corrected the platform label to `AAPS` but kept
`lineage = "oref0 (legacy)"`.

That left a downstream gap: experiments stratifying by `controller`
alone now conflate AAPS-oref0 (3 patients) with the never-observed
AAPS-oref1, and Loop-AB-ON with Loop-AB-OFF.

This EXP adds `algorithm_mode` as the canonical join key.

---

## Derivation rule

```
controller=AAPS  + lineage contains "oref1"  -> "AAPS-oref1"
controller=AAPS  + lineage contains "oref0"  -> "AAPS-oref0"
controller=AAPS  + neither                   -> "AAPS-unknown"
controller=Trio                              -> "Trio-oref1"
controller=Loop  + ∃ bolus_smb > 0 in grid   -> "Loop-AB-ON"
controller=Loop  + no SMB ever               -> "Loop-AB-OFF"
otherwise                                    -> "unknown"
```

`autobolus_on` is inferred operationally: a Loop patient with any
non-zero `bolus_smb` cell anywhere in the grid is treated as AB-ON.
This matches the operational definition that has been used
throughout the EXP-29xx arc.

Implementation: `tools/ns2parquet/exp_2992_algorithm_mode.py`.
Idempotent.

---

## Cohort distribution after applying

```
exp-2891_simpson_dose_response.parquet (24 rows):
  Trio-oref1   : 9
  Loop-AB-ON   : 5  (c, d, e, g, i)
  unknown      : 5  (h, k, and 3 NS patients with insufficient_data)
  AAPS-oref0   : 3  (odc-74077367, odc-86025410, odc-96254963)
  Loop-AB-OFF  : 2  (a, f)

exp-2886_phenotype.parquet : same 5-class distribution.
exp-2889_counterfactual_replay.parquet (31 rows):
  Trio-oref1   : 9
  AAPS-oref0   : 8
  unknown      : 7
  Loop-AB-ON   : 5
  Loop-AB-OFF  : 2
```

Note: `exp-2895_tod_lineage.parquet` is patient-day-grain without
`controller` — skipped, will be revisited if future TOD experiments
need stratification.

---

## Cohort gaps now visible

* **AAPS-oref1**: zero patients. Any conclusion about "AAPS"
  in this cohort is exclusively about AAPS-oref0.
* **Loop-AB-OFF**: only 2 patients. Underpowered for AB-on-vs-off
  isolation (already noted in synthesis §6).
* **unknown**: 5 patients (h, k, ns-554b, ns-8ffa, ns-c422); these
  fail every algorithm-marker check and remain ambiguous.

---

## Forward usage convention

Going forward, all experiments stratifying by design SHOULD use
`algorithm_mode` directly. The legacy `controller` and `lineage`
columns remain for back-compat but should not be used as primary
join keys.

---

## Verdict

POSITIVE — `algorithm_mode` column added to three per-patient
summary parquets; cohort distribution computed and documented;
AAPS-oref1 confirmed as a structural gap (zero patients).
