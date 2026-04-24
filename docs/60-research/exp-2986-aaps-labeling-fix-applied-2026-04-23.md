# EXP-2986: AAPS labeling fix — applied & verified

**Date**: 2026-04-23
**Audience**: open-source AID code authors (Loop, AAPS, Trio,
oref0, Nightscout)
**Scope**: Fix the structural mis-classification of AAPS-platform
patients as "OpenAPS / oref0 (legacy)" lineage discovered in
EXP-2984. Apply minimum-viable code fixes across the ingestion
and cohort-classification pipeline. Re-verify cohort lineage
tally. Identify which downstream experiments must be revisited.
**What this is NOT**: not a re-ingest of raw NS / ODC data
(the existing grid.parquet and devicestatus.parquet remain
canonical); not a claim that AAPS = oref1 universally — see the
"algorithm vs platform" distinction below.

---

## 1. Bug summary

Pre-fix cohort lineage (3 ODC patients):

| patient_id | controller (pre-fix) | lineage (pre-fix) |
|---|---|---|
| odc-74077367 | OpenAPS | oref0 (legacy) |
| odc-86025410 | OpenAPS | oref0 (legacy) |
| odc-96254963 | OpenAPS | oref0 (legacy) |

Two underlying causes:

1. **`tools/ns2parquet/normalize.py:87-102` (`_detect_controller`)**:
   tested `'openaps'` substring before `'aaps'`. AAPS exports stamp
   `device='openaps://AndroidAPS'`, so the substring match caught
   them in the OpenAPS branch first.
2. **`tools/cgmencode/exp_state_clustering_2810.py:73-79`
   (`classify_controller`)**: hard-coded
   `pid.startswith('odc-') → 'OpenAPS'`. ODC = OpenAPS Data Commons
   contains AAPS-native JSON (`tools/ns2parquet/odc_loader.py:1-17`),
   not historical OpenAPS-on-Edison data.

The 2810 → 2812 → 2873 → 2886 → 2891 chain propagated the
mis-classification into the canonical cohort lineage parquet.

---

## 2. Fixes applied

### Code (committed)

```
tools/ns2parquet/normalize.py
  - Reorder _detect_controller branches: AAPS / AndroidAPS tested
    BEFORE 'openaps' substring.
  - Comment cites EXP-2986 and explains AAPS device-string format.

tools/cgmencode/exp_state_clustering_2810.py
  - classify_controller(): odc- → 'AAPS' (was 'OpenAPS').
  - Note that lineage assignment is delegated to phenotype-
    synthesis step.

tools/cgmencode/exp_phenotype_synthesis_2886.py
  - lineage(): add explicit AAPS branch defaulting to
    'oref0 (legacy)' for the current cohort. Documents
    that AAPS may run EITHER algorithm and per-patient
    override is required when oref1 markers are present.

tools/ns2parquet/exp_2986_relabel_aaps.py  (NEW)
  - Idempotent in-place relabel of derived parquets:
    exp-2891_simpson_dose_response.parquet
    exp-2886_phenotype.parquet
    exp-2889_counterfactual_replay.parquet
    exp-2895_tod_lineage.parquet (no-op; no odc rows)
  - Updates ONLY controller column (= 'AAPS'); preserves lineage.
  - Avoids the expensive 2810 → 2812 → 2873 → 2886 → 2891 re-run.
```

### Data (relabel script ran cleanly)

```
RELABELED exp-2891_simpson_dose_response.parquet: 3 rows -> controller=AAPS
RELABELED exp-2886_phenotype.parquet: 3 rows -> controller=AAPS
RELABELED exp-2889_counterfactual_replay.parquet: 8 rows -> controller=AAPS
NOOP      exp-2895_tod_lineage.parquet: no odc- rows touched
```

---

## 3. Critical nuance: platform ≠ algorithm

After applying the controller fix, inspection of devicestatus
columns for the 3 ODC patients revealed:

| Patient | rows | eventual_bg non-null | algorithm_isf nn | algorithm_cr nn | algorithm_tdd nn | insulin_activity nn | bolus_iob nn | bolus_smb cells > 0 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| odc-74077367 | 97225 | 95843 | 0 | 0 | 0 | 0 | 0 | 0 |
| odc-86025410 | 155742 | 140823 | 0 | 0 | 0 | 0 | 0 | 0 |
| odc-96254963 | 65757 | 46772 | 0 | 0 | 0 | 0 | 0 | 0 |

`eventual_bg` is the oref-family prediction marker (any oref0/
oref1/AAPS implementation populates it). The five oref1-only
columns (`algorithm_isf`, `algorithm_cr`, `algorithm_tdd`,
`insulin_activity`, `bolus_iob`) are zero non-null across all 3
patients. `bolus_smb > 0` is also zero across the entire grid.

**Interpretation**: these patients are running **AAPS-platform with
oref0-algorithm** (SMB / UAM / dynamic-ISF disabled, or pre-oref1
AAPS version). The platform is AAPS (Android app). The algorithm
is oref0 (no SMB-class behaviour).

**Therefore**:

- `controller = 'AAPS'`  ← platform-correct, fixed
- `lineage   = 'oref0 (legacy)'`  ← algorithm-correct, preserved

---

## 4. Post-fix cohort tally

```
controller  lineage         n_patients
AAPS        oref0 (legacy)  3
Loop        Loop (iOS)      7
Trio        oref1 (modern)  9
```

`oref1 (modern) lineage` is now Trio-only (n=9). The cohort
contains **zero AAPS-oref1 patients**.

---

## 5. Implications for prior experiments

| Prior claim | Re-read |
|---|---|
| "oref0 (legacy)" arm shows X | Read as "AAPS-platform oref0-algorithm (n=3, ODC)". Behavioral conclusions remain valid because algorithm = oref0; cross-platform attributions to "OpenAPS reference design" must be retracted. |
| "oref1 (modern)" arm shows Y | Read as "Trio-iOS oref1 (n=9)". Trio-vs-AAPS platform isolation within oref1 is **NOT POSSIBLE in current cohort** — needs future AAPS-oref1 patients. |
| EXP-2980 Trio-vs-AAPS platform isolation | Re-ran with new labels; the AAPS arm shows `em_rate = 0` at sustained-high (180+) because the patients run oref0-mode AAPS without SMB. Result is **MERGED-LABEL_NO_AAPS_OREF1** still — algorithm gates dominate platform comparison. |

---

## 6. EXP-2989 (Trio-vs-AAPS within oref1) status

**SKIPPED — preconditions not met in cohort**. The platform-
isolation experiments (re-running EXP-2964 / 2972 / 2975 with
AAPS-vs-Trio split) require AAPS patients running oref1-algorithm
(SMB / dynamic-ISF / UAM enabled). The current cohort has zero
such patients. Documented predictions for future work:

- EXP-2964 (SMB-vs-basal velocity coupling at PP): expect AAPS-
  oref1 to match Trio-oref1 within ±10% on the controller-channel
  slope at PP, because both run identical oref1 source. Any
  deviation would isolate platform implementation differences
  (BLE timing, doze-mode wake delays on Android, profile-sync
  cadence).
- EXP-2972 (emission frequency vs magnitude in 70-100): expect
  similar `em_rate` and `mean_em_U` distributions; AAPS may show
  slightly higher `em_rate` due to tighter 5-min loop cadence
  (Loop 5-min vs AAPS configurable down to 1-min).
- EXP-2975 (U-shape): expect identical curve shape; if AAPS
  shifts left, that's evidence of Android-specific post-meal
  timing skew.

---

## 7. Cited code references

- `tools/ns2parquet/normalize.py:87-102` — `_detect_controller`
- `tools/ns2parquet/odc_loader.py:1-17, 105-148` — ODC adapter
  documents AAPS-native source format
- `tools/cgmencode/exp_state_clustering_2810.py:73-83` —
  upstream pid → controller heuristic
- `tools/cgmencode/exp_phenotype_synthesis_2886.py:41-55` —
  lineage assignment from controller
- `tools/ns2parquet/exp_2986_relabel_aaps.py` — relabel script

---

## 8. Verdict

**POSITIVE — STRUCTURAL FIX APPLIED**. Bug closed. Cohort labels
are now platform-correct. Algorithm lineage preserved per
empirical devicestatus inspection. Downstream synthesis updated
(see `synthesis-design-comparison-2026-04-23.md` thirteenth-batch
addendum). Evidence-line tally updated to **26**.
