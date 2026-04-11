# Parquet Data Path Validation Report

**Date**: 2026-04-10  
**Scope**: Validate that the new parquet data terrarium reproduces all experiment results, and assess impact of the oref0 IOB/COB inclusion fix.

## Background

### Problem Statement

The `tools/cgmencode` experiment suite loaded patient data via `build_nightscout_grid()` in `real_data_adapter.py`, which re-parsed ~1GB of JSON on every run. This path had a silent bug: **it only read Loop devicestatus IOB** (lines 349-354), dropping all oref0 records. Patient b (98% oref0, 2% Loop) got near-zero IOB/COB in the grid.

### Fix Applied

The `tools/ns2parquet` grid builder (`grid.py:143-177`) correctly reads both:
- `loop.iob` / `loop.cob` (Loop controller)
- `openaps.iob` / `openaps.suggested.IOB` and `openaps.enacted.COB` (oref0 controller)

A new **parquet bridge** (`load_parquet_patients()` in `real_data_adapter.py`) loads the pre-built grid from the data terrarium at `externals/ns-parquet/`.

### Two Different IOBs

The experiments use two independent IOB representations:
1. **DS IOB** (`df['iob']`): The controller's self-reported IOB from devicestatus — what Loop or oref0 *thinks* IOB is. Used as a feature in the 8-column grid array and for hepatic production modeling.
2. **PK IOB** (`insulin_total`, `insulin_net`): Independently computed by `build_continuous_pk_features()` from bolus+basal convolution with exponential action curves. This is the physics model used for ISF estimation.

Most experiments detect correction events from **bolus events + glucose deltas** — they do not use the grid IOB column for ISF/PK estimation.

## Methodology

- Built data terrarium: 11 patients × 2 subsets → `externals/ns-parquet/`
- Created `rerun_parquet.py` harness that monkey-patches `load_patients` with parquet version
- Ran 12 experiments (EXP-2051–2057, EXP-2071–2073, EXP-2091–2097)
- Compared all per-patient results against stored originals in `externals/experiments/`

## Results

### Reproduction: 12/12 Experiments Identical

| Experiment | Name | Patient b Match | All Patients Match |
|------------|------|----------------|-------------------|
| EXP-2051 | Circadian ISF | ✅ 36 corrections | ✅ |
| EXP-2052 | Circadian Basal | ✅ | ✅ |
| EXP-2053 | Dawn Phenomenon | ✅ | ✅ |
| EXP-2056 | IOB Sensitivity | ✅ n=37, r=0.042 | ✅ |
| EXP-2057 | Counter-Regulatory | ✅ n=115, rebound=114 | ✅ |
| EXP-2071 | Optimal ISF | ✅ | ✅ |
| EXP-2072 | Optimal CR | ✅ | ✅ |
| EXP-2073 | Optimal Basal | ✅ | ✅ |
| EXP-2091 | Insulin PK | ✅ n=1 (insufficient) | ✅ |
| EXP-2092 | Dose-Response | ✅ n=15, r=-0.53 | ✅ |
| EXP-2096 | Stacking | ✅ 1445 events | ✅ |
| EXP-2097 | IOB Accuracy | ✅ halflife=65min | ✅ |

### Why Results Are Identical Despite the Fix

The oref0 IOB/COB fix populates the `iob` and `cob` columns in the 8-column grid for patient b (from ~98% zeros to ~89% non-zero). However, the experiment algorithms detect correction events by searching for:

1. **Isolated bolus events** followed by glucose drops (ISF estimation)
2. **Bolus+carb events** followed by glucose response (CR estimation)
3. **Glucose threshold crossings** (hypo detection, stacking)

None of these use the grid IOB column as input. The IOB column flows into:
- The hepatic production estimate in `build_continuous_pk_features()`
- The 8-column grid feature array passed to downstream models

Since the current experiments operate on correction events (not the grid array directly), the fix has **no numerical impact on existing results**.

### Patient b: Grid Column Comparison

| Column | Old (Loop-only) | New (Loop+oref0) | Change |
|--------|-----------------|-------------------|--------|
| `iob` | ~98% zero (mean ~0.04U) | ~11% zero (mean ~1.8U) | **+4400%** |
| `cob` | ~99% zero | ~60% zero | Significant fill |
| `glucose` | Identical | Identical | None |
| `net_basal` | Identical | Identical | None |
| `bolus` | Identical | Identical | None |
| `carbs` | Identical | Identical | None |

### Performance Impact

| Metric | JSON Path | Parquet Path | Speedup |
|--------|-----------|--------------|---------|
| Load 11 patients | ~180s | 16.4s | **11×** |
| Single patient grid | ~18s | 0.08s | **225×** |
| Full experiment suite (12 exp) | ~hours | 24.7s | **~100×** |

## Implications

### Current Experiments: No Change
All existing experiment findings remain valid. The stored results in `externals/experiments/` are numerically identical to the parquet-path results.

### Future Experiments: Patient b Now Usable for IOB-Dependent Analysis
The corrected IOB/COB data for patient b enables future experiments that:
- Use DS IOB as a feature (e.g., predicting glucose from grid features)
- Analyze oref0 controller behavior (suspend patterns, SMB patterns)
- Compare Loop vs oref0 IOB estimation accuracy

### Patient b Controller Profile
- **1,018 Loop records** (2%): Full IOB/COB from `loop.iob`/`loop.cob`
- **54,842 oref0 records** (98%): IOB from `openaps.iob` or `openaps.suggested.IOB`, COB from `openaps.enacted.COB`
- This is the only mixed-controller patient in the dataset

## Files Changed

| File | Change | Status |
|------|--------|--------|
| `tools/ns2parquet/normalize.py` | Fixed timezone bug | Committed `ecb5ee4` |
| `tools/ns2parquet/grid.py` | Warning logging, tz fix | Committed `f9ee523` |
| `tools/ns2parquet/writer.py` | Warning logging | Committed `f9ee523` |
| `tools/ns2parquet/cli.py` | Batch features | Committed `cc1e183` |
| `Makefile` | Terrarium targets | Committed `dd5e30e` |
| `tools/cgmencode/real_data_adapter.py` | Parquet bridge + attrs reconstruction | **Uncommitted** |
| `tools/cgmencode/rerun_parquet.py` | Experiment rerun harness | **Uncommitted** |
| This report | Validation findings | **Uncommitted** |

## Conclusion

The parquet data path is a **drop-in replacement** for the JSON path. It reproduces all experiment results identically while providing 11-225× performance improvement. The oref0 IOB/COB fix is structurally correct and prepares patient b for future IOB-dependent analysis, but has zero impact on current experiment findings because they use bolus-event-based correction detection rather than grid IOB features.
