# AAPS labeling fix — pipeline note (2026-04-23)

**Date**: 2026-04-23
**Linked experiment**: EXP-2986
**Audience**: AID-data pipeline maintainers (this repo)

## Problem

Two ingestion-pipeline bugs caused AAPS-platform patients
imported via the OpenAPS Data Commons (ODC) adapter to be
mis-classified as `controller='OpenAPS'` and propagated downstream
as `lineage='oref0 (legacy)'`.

## Two-line fix

### `tools/ns2parquet/normalize.py` (`_detect_controller`)

Reorder branches: test `'aaps'`/`'androidaps'` BEFORE `'openaps'`.
AAPS exports stamp `device='openaps://AndroidAPS'`, which would
otherwise be caught by the OpenAPS substring branch first.

### `tools/cgmencode/exp_state_clustering_2810.py` (`classify_controller`)

Map `pid.startswith('odc-') → 'AAPS'` (was `'OpenAPS'`). ODC =
OpenAPS Data Commons ≠ historical OpenAPS-on-Edison data; ODC
contains AAPS-native JSON (see `tools/ns2parquet/odc_loader.py`).

## Algorithm vs platform — important nuance

AAPS supports running EITHER oref0-algorithm OR oref1-algorithm.
Per-patient inspection of `algorithm_isf`, `algorithm_cr`,
`algorithm_tdd`, `insulin_activity`, `bolus_iob`, and `bolus_smb`
is required to determine which algorithm a particular AAPS patient
ran. The 3 ODC patients in the current cohort show ZERO non-null
in all five oref1-only columns AND zero SMB cells — they ran
**AAPS-platform with oref0-algorithm**.

`tools/cgmencode/exp_phenotype_synthesis_2886.py:lineage()`
defaults `controller='AAPS'` to `lineage='oref0 (legacy)'` for
the current cohort. Per-patient override is required when
oref1-mode AAPS patients are added.

## Idempotent in-place relabel script

`tools/ns2parquet/exp_2986_relabel_aaps.py`

Re-applies the controller fix to derived parquets (does NOT touch
lineage). Avoids running the expensive
2810 → 2812 → 2873 → 2886 → 2891 chain.

Targets:

- `externals/experiments/exp-2891_simpson_dose_response.parquet`
- `externals/experiments/exp-2886_phenotype.parquet`
- `externals/experiments/exp-2889_counterfactual_replay.parquet`
- `externals/experiments/exp-2895_tod_lineage.parquet` (no-op)

## Future work

- Re-ingest ODC source JSON with the fixed normalize.py to
  produce an authoritative new `grid.parquet` (not yet done; the
  existing grid uses pre-fix labels but downstream consumers
  read controller from the cohort parquet, not the grid).
- Add AAPS-NS oref1-mode patients to the cohort to enable the
  Trio-vs-AAPS within-oref1 platform-isolation experiments
  (EXP-2989 deferred).
- Add an `algorithm_mode` column to the cohort parquet
  alongside `controller` so platform and algorithm are tracked
  independently end-to-end.

## Verification

Post-fix tally:

```
controller  lineage         n_patients
AAPS        oref0 (legacy)  3
Loop        Loop (iOS)      7
Trio        oref1 (modern)  9
```
