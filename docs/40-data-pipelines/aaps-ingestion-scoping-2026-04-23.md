# AAPS-Android Ingestion Scoping (2026-04-23)

**Audience**: Open-source AID code authors, data-pipeline maintainers.
**Scope**: Document why the active Simpson/dose-response cohort
(`externals/experiments/exp-2891_simpson_dose_response.parquet`)
contains **zero `controller='aaps'` patients**, what feeds it,
and concrete steps to validate or add AAPS-Android data.
**What this is NOT**: an experiment. No statistical claims.
This is a pipeline / labeling diagnosis to enable future
Trio-vs-AAPS comparison (the gap surfaced in EXP-2980).

---

## Summary diagnosis — the gap is **data-LABELING**, not data-collection

AAPS-native uploads **are present** in the underlying ODC
(OpenAPS Data Commons) corpus, ingested via
`tools/ns2parquet/odc_loader.py`, but they are stamped with the
device string `'openaps://AndroidAPS'` and consequently
mis-classified as `controller='openaps'` (and downstream as
`lineage='oref0 (legacy)'`) by `_detect_controller()` in
`tools/ns2parquet/normalize.py:87-100`.

The detection function tests `'openaps' in dl` **before**
`'aaps' in dl`; since the synthesized device prefix is
`'openaps://...'`, every AAPS upload short-circuits at the
openaps branch and never reaches the AAPS branch.

---

## Where the cohort comes from

### The Simpson cohort parquet

`externals/experiments/exp-2891_simpson_dose_response.parquet`
is a **24-row per-patient summary** (one row per patient,
columns: `n_events, mean_duration, controller, lineage,
archetype, ...`). It is itself derived from upstream training
data, then enriched with `controller` and `lineage` labels and
the dose-response/Simpson decomposition computed on top.

Patient roster in this cohort:

| controller | lineage | n |
|---|---|---:|
| Loop | Loop (iOS) | 7 |
| Trio | oref1 (modern) | 9 |
| OpenAPS | oref0 (legacy) | 3 |
| (NaN) | unknown | 5 |
| **AAPS** | (any) | **0** |

### The training grid

`externals/ns-parquet/training/grid.parquet` is the 5-min
research grid covering **31 patients** (11 letter codes
`a..k` + 13 `ns-...` Trio uploads + 7 `odc-...` AAPS-format
uploads). The cohort parquet is a strict subset of these 31.

### Build provenance

`externals/ns-parquet/manifest.json` shows the parquet was
built 2026-04-11 from `externals/ns-data/patients/` (patients
a-k only). The `ns-...` and `odc-...` patient roots are added
elsewhere in the build flow:

- `tools/ns2parquet/cli.py:564` discovers ODC patient
  directories (numeric IDs) and routes them through the
  AAPS-native loader.
- `tools/ns2parquet/odc_loader.py:606 _load_aaps_format()`
  parses AAPS upload trees (`BgReadings.json`,
  `Treatments.json`, `APSData.json`, `TempBasals.json`, etc.).

### Where the AAPS label gets lost

`tools/ns2parquet/odc_loader.py` synthesizes Nightscout-shaped
records from the AAPS-native JSON. Every synthesized record
sets:

```python
'device': 'openaps://AndroidAPS',
'enteredBy': 'openaps://AndroidAPS',
```

at lines 105, 145, 175, 208, 224, 252, 295. (Multiple call
sites, all identical convention.)

Then `tools/ns2parquet/normalize.py:87-100`:

```python
def _detect_controller(device: str) -> str:
    dl = device.lower()
    if dl.startswith('loop://') or 'loop' in dl:
        return 'loop'
    if dl.startswith('openaps://') or 'openaps' in dl:
        return 'openaps'                                    # ← matched first
    if 'trio' in dl:
        return 'trio'
    if 'aaps' in dl or 'androidaps' in dl:                  # ← never reached
        return 'aaps'
```

Since `'openaps://AndroidAPS'.lower()` matches the
`'openaps' in dl` test on line 7 of the function, the function
returns `'openaps'` and never checks the AAPS branch.

### Confirmation in the data

`externals/ns-parquet/training/devicestatus.parquet` controller
distribution (verified 2026-04-23):

| patient cluster | controller |
|---|---|
| `a-k` (Loop iOS), `ns-...` (Trio NS) | `loop` or `trio` (correct) |
| `odc-39819048..96254963` (AAPS-native) | `openaps` (mis-labeled) |

**Zero rows have `controller='aaps'`.** Every odc-* patient
is AAPS-native upload, but every one is stamped `openaps`.

---

## Why this matters

EXP-2980 reported "no AAPS in cohort" and recommended adding
AAPS data. The diagnosis is more nuanced:

- The 3 patients labeled `lineage='oref0 (legacy)'` and
  `controller='OpenAPS'` (odc-74077367, odc-86025410,
  odc-96254963) are AAPS-Android uploads being **misread as
  legacy OpenAPS**.
- The 4 other odc-* patients (odc-39819048, -49141524,
  -58680324, -61403732, -84181797) had insufficient events for
  the Simpson cohort threshold and were excluded entirely.
- The "Trio vs AAPS" gap in EXP-2980 is therefore **not** a
  data-collection failure. It is a **labeling failure** that
  may have already silently mixed AAPS records into the
  "oref0" arm of EXP-2891.

---

## Concrete remediation steps

### Step 1 — Fix `_detect_controller` ordering (quick)

Reorder so `'aaps' / 'androidaps'` is checked **before**
`'openaps'`, since `'androidaps'` is a substring-superset:

```python
if 'aaps' in dl or 'androidaps' in dl:
    return 'aaps'
if dl.startswith('openaps://') or 'openaps' in dl:
    return 'openaps'
```

Risk: any *true* OpenAPS upload that put `aaps` in the device
string would now be mis-routed. Mitigation: tighten the AAPS
test to require `androidaps` (the AAPS-canonical token) and
keep `aaps` only as a careful fallback.

### Step 2 — Stop synthesizing the misleading device string

In `tools/ns2parquet/odc_loader.py`, change all 7 synthesized
device stamps from `'openaps://AndroidAPS'` to a token that
self-identifies cleanly, e.g. `'androidaps://odc'`. This is the
**root-cause** fix.

### Step 3 — Re-tag historic data without rebuild

The parquet store is large. A non-destructive option is to add
a `tools/relabel_aaps.py` post-processor that reads the
existing parquet, renames `controller='openaps'` → `'aaps'`
where the patient_id matches `^odc-\d+$` AND the underlying
device string contains `androidaps`, and writes a new column
or overwrites in place.

### Step 4 — Re-classify lineage

`oref0 (legacy)` vs `oref1 (modern)` is currently inferred by
the lineage labeler (likely in EXP-2891 or upstream). After
Steps 1-2, AAPS uploads need a lineage decision: modern AAPS
ships oref1-derived algorithms with SMB, so AAPS uploads should
generally be tagged `oref1 (modern)` unless the upload's
APSData reveals an explicitly older algorithm. This requires
inspecting `APSData.json.openaps.suggested` for SMB markers.

### Step 5 — Re-run cohort experiments

Once relabeled:

- Re-run EXP-2891 to regenerate the Simpson cohort with
  AAPS as a separate stratum.
- Re-run EXP-2972 / 2973 / 2978 / 2979 stratified by
  `controller in {Trio, AAPS}` within `lineage='oref1 (modern)'`
  to perform the platform-isolation test originally proposed in
  EXP-2980.
- If estimates overlap → algorithmic generalization confirmed.
- If estimates diverge → iOS/Android implementation difference
  isolated.

---

## What we cannot fix from the parquet alone

- AAPS users who don't upload to ODC are absent. Adding them
  requires reaching into the AAPS-NS uploader streams (different
  consent / data path).
- Some odc-* patients have very low event counts (≤3 rows in
  devicestatus); those are likely incomplete uploads, not
  representative AAPS users.

---

## Audit checklist for AID-author reviewers

- [ ] Confirm step 1 fix and re-run `tools/ns2parquet`
      end-to-end on a fresh tree (currently 31 patients).
- [ ] Verify expected outcome: `odc-*` patients re-tagged
      `controller='aaps'`.
- [ ] Re-run EXP-2891; expect new lineage rows
      `lineage='oref1 (modern)' AND controller='AAPS'`.
- [ ] Update progress.md to reflect AAPS arm now testable.
- [ ] Re-run EXP-2980 with the new stratification.

## References

- `tools/ns2parquet/normalize.py:87-100` — `_detect_controller`
- `tools/ns2parquet/odc_loader.py:105,145,175,208,224,252,295`
  — synthesized `'openaps://AndroidAPS'` device strings
- `tools/ns2parquet/cli.py:564,733-744,759` — controller
  detection at the cohort level
- `tools/ns2parquet/grid.py:236,357,485` — AAPS-aware temp-basal
  handling
- `externals/ns-parquet/manifest.json` — build provenance
- `externals/experiments/exp-2891_simpson_dose_response.parquet`
  — Simpson cohort
- EXP-2980: `docs/60-research/exp-2980-trio-vs-aaps-2026-04-23.md`
- EXP-2984 marker: `docs/60-research/exp-2984-aaps-scoping-2026-04-23.md`
