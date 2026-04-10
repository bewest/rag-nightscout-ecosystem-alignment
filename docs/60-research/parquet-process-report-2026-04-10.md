# Parquet Infrastructure: Process Report & IOB Validation

**Date**: 2026-04-10  
**Scope**: End-to-end documentation of the ns2parquet quality review, bug fixes, batch aggregation, data terrarium, experiment reproduction, and IOB-dependent validation.

## 1. Executive Summary

We reviewed `tools/ns2parquet` for quality and accuracy, found and fixed 2 bugs, added batch aggregation features, built a persistent "data terrarium" for experiments, validated that all 12 existing experiments reproduce identically via the parquet path, and confirmed the oref0/Trio IOB fix is material for IOB-dependent analysis with a purpose-built validation experiment.

**Key finding**: Patient b (98% Trio/oref0 controller) was silently getting near-zero IOB/COB through the old JSON data path. The parquet path corrects this, restoring 39,000+ IOB readings. This changes no existing experiment results (they use bolus events, not grid IOB) but enables a new class of IOB-dependent analysis.

## 2. Process Timeline

### Phase 1: Code Quality Review

Launched three parallel review agents to assess `tools/ns2parquet` against:
- **(a) cgmencode adoption** — 8/10 readiness (grid schema matches, bridge needed)
- **(b) outside researchers** — 2/10 (no documentation, no pip install, hardcoded paths)
- **(c) batch aggregation** — 8/10 (convert-all exists, merge/filter missing)

### Phase 2: Bug Discovery and Fixes

| Bug | Severity | Fix |
|-----|----------|-----|
| `normalize.py:554` stored `timeFormat` (12/24 clock display) in `timezone` column | **Real bug** | Created `_resolve_timezone()` helper. Committed `ecb5ee4` |
| `settings.js` threshold mmol→mg/dL conversion | **NOT a bug** — Nightscout converts server-side with `bgHigh < 50` heuristic | No fix needed |
| `grid.py` treatment timestamps: naive/mixed tz handling | **Silent risk** | Added tz→UTC normalization + warnings. Committed `f9ee523` |
| `writer.py` schema fallback on column mismatch | **Silent risk** | Added warning logging. Committed `f9ee523` |

### Phase 3: Batch Aggregation Features

Added to `cli.py` (committed `cc1e183`):
- `--patients a,b,c` filter for convert-all
- `--subset both` to process training+verification in one pass
- `merge` subcommand to combine parquet files from multiple directories
- `info --detail` with per-patient row counts and date ranges

### Phase 4: Data Terrarium

Built `externals/ns-parquet/` as a persistent, reproducible parquet store (committed `dd5e30e`):

```
externals/ns-parquet/
  training/          # 11 patients, 529K grid rows, ~44MB
    grid.parquet     # 5-min research grid (44 columns)
    entries.parquet, treatments.parquet, devicestatus.parquet, profiles.parquet
  verification/      # same structure
  manifest.json      # git sha, timestamp, patient list
  README.md          # quick-start guide
```

Makefile targets: `make terrarium`, `make terrarium-info`

### Phase 5: Parquet Bridge for cgmencode

Added to `real_data_adapter.py` (committed `af77f49`):
- `load_parquet_grid()` — loads pre-built 5-min grid
- `load_parquet_patients()` — loads grid + builds PK features
- `_reconstruct_attrs()` — recovers therapy schedules from profiles.parquet
- `_PARQUET_COL_MAP` — translates `actual_basal_rate` → `temp_rate`

Key challenge: Parquet doesn't store DataFrame `.attrs`. Without therapy schedules (ISF, CR, basal rate, DIA, timezone), the PK feature builder falls back to wrong defaults. Solved by reconstructing attrs from the latest profile snapshot in profiles.parquet.

### Phase 6: Experiment Reproduction

Ran 12 experiments via `rerun_parquet.py`:

| Experiment | Name | Status | Time |
|------------|------|--------|------|
| EXP-2051 | Circadian ISF | ✅ Identical | 0.2s |
| EXP-2052 | Circadian Basal | ✅ Identical | 2.4s |
| EXP-2053 | Dawn Phenomenon | ✅ Identical | 0.1s |
| EXP-2056 | IOB Sensitivity | ✅ Identical | 0.2s |
| EXP-2057 | Counter-Regulatory | ✅ Identical | 0.5s |
| EXP-2071 | Optimal ISF | ✅ Identical | 0.2s |
| EXP-2072 | Optimal CR | ✅ Identical | 0.4s |
| EXP-2073 | Optimal Basal | ✅ Identical | 2.4s |
| EXP-2091 | Insulin PK | ✅ Identical | 0.4s |
| EXP-2092 | Dose-Response | ✅ Identical | 0.5s |
| EXP-2096 | Stacking | ✅ Identical | 0.5s |
| EXP-2097 | IOB Accuracy | ✅ Identical | 0.6s |

**Total: 12/12 identical, 25s** (vs estimated hours on JSON)

### Phase 7: IOB-Dependent Validation

Purpose-built experiment (`exp_iob_validation.py`) that contrasts "full IOB" (Loop+Trio/oref0) vs "simulated loop-only IOB" (the old bug).

## 3. IOB Validation Results

### The Bug's Impact on Patient b

| Metric | With Fix (Full IOB) | Without Fix (Loop-only) | Change |
|--------|--------------------|-----------------------|--------|
| IOB > 0 | **75.9%** of steps | 1.6% of steps | **+4600%** |
| Mean IOB | 1.82 U | ~0.04 U | **+4400%** |
| COB > 0 | 60.2% | ~1% | Massive |
| IOB data points | 39,069 | 792 | **49× more** |

All other patients (a, c–k): **zero difference** — they are 100% Loop controller.

### Analysis 1: IOB Predictive Power (1h glucose Δ)

| Patient | Full IOB R² | Loop-only R² | Δ R² | n (full) | n (loop-only) |
|---------|------------|-------------|------|----------|--------------|
| a | 0.1072 | 0.1072 | 0.0000 | 40,384 | 40,384 |
| **b** | **0.0309** | **0.0032** | **+0.0277** | **39,069** | **792** |
| c | 0.1273 | 0.1273 | 0.0000 | 28,878 | 28,878 |
| k | 0.1238 | 0.1238 | 0.0000 | 28,850 | 28,850 |

Patient b's IOB predictive power increases **~10×** (R² 0.003 → 0.031) with the fix. While R²=0.031 is modest, the sample grows from 792 to 39,069 — making patient b usable for IOB analysis.

### Analysis 2: IOB-Stratified Glucose Outcomes

Higher IOB should predict greater glucose drops over 1 hour (the insulin is working). The "spread" measures the difference in mean 1h Δglucose between the highest and lowest IOB tertiles:

| Patient | Full Spread | Loop-only Spread | Interpretation |
|---------|------------|------------------|---------------|
| a | -49.9 mg/dL | -49.9 | Unchanged |
| **b** | **-19.9 mg/dL** | **-0.2 mg/dL** | **100× stronger signal** |
| c | -65.5 | -65.5 | Unchanged |

With loop-only IOB, patient b shows essentially **no stratification** — all IOB bins look the same because they're all ~zero. With the fix, the expected dose-response relationship emerges: high IOB → -19.9 mg/dL more glucose drop than low IOB.

### Analysis 3: Controller Suspend Patterns

"Suspend %" measures the fraction of time IOB < 0.05 U (controller is suspending delivery).

| Patient | Full Suspend | Loop-only Suspend | Δ |
|---------|-------------|-------------------|---|
| a | 22% | 22% | 0% |
| **b** | **25%** | **98%** | **-73%** |
| c | 45% | 45% | 0% |

With loop-only IOB, patient b appeared to be in "suspend" 98% of the time — an absurd result that should have been a red flag. With the fix, b shows 25% suspend rate, consistent with the population range (22-47%, excluding patient j).

### Analysis 4: Circadian IOB Pattern

| Patient | Full Peak Hour | Full Trough | Full Ratio | Loop-only Ratio |
|---------|---------------|-------------|------------|-----------------|
| a | 5:00 | 14:00 | 3.9× | 3.9× |
| **b** | **0:00** | **10:00** | **11.4×** | **8.5×** |
| c | 17:00 | 12:00 | 4.7× | 4.7× |

Patient b now reveals a real circadian IOB pattern: peak at midnight (overnight basal delivery), trough at 10am. The ratio changes from 8.5× (Loop-only, noisy small sample) to 11.4× (full data, robust estimate).

## 4. Architecture Decisions

### Why Two IOBs?

The system maintains two independent IOB representations:

| | DS IOB (grid `iob` column) | PK IOB (8-channel PK features) |
|---|---|---|
| **Source** | Controller self-report from devicestatus | Physics: bolus+basal convolution with exponential curves |
| **Meaning** | What the AID controller *thinks* IOB is | What IOB *actually is* based on delivery records |
| **Use** | Grid feature, hepatic production model | ISF estimation, dose-response analysis |
| **Affected by fix?** | **Yes** — patient b goes from 98% zeros to real data | No — computed from treatment events independently |

### Why Existing Experiments Were Unaffected

All 12 experiments detect **correction events** by searching for:
1. Isolated bolus events followed by glucose drops (ISF)
2. Bolus+carb events followed by glucose response (CR)
3. Glucose threshold crossings (hypo/stacking detection)

These algorithms iterate over the **treatment** parquet (which was always correct for all controllers), not the grid IOB column. The grid IOB column feeds into downstream feature arrays but was not used by the correction-event-based experiments.

### Why Parquet Bridge Needed Attrs Reconstruction

The `build_continuous_pk_features()` function reads therapy schedules from `df.attrs`:
- `isf_schedule` → insulin sensitivity by time of day
- `cr_schedule` → carb ratio by time of day
- `basal_schedule` → basal rates by time of day
- `dia_hours` → duration of insulin action
- `timezone` → for local time conversion

Parquet format does not persist DataFrame `.attrs`. Without these, PK features fall back to population defaults, producing wrong results. The bridge reconstructs attrs from the latest profile snapshot in `profiles.parquet`.

### Column Name Mapping

ns2parquet uses descriptive column names (`actual_basal_rate`), while the PK builder expects legacy names (`temp_rate`). The `_PARQUET_COL_MAP` translation layer handles this without modifying either side.

## 5. Performance

| Operation | JSON Path | Parquet Path | Speedup |
|-----------|-----------|--------------|---------|
| Load 1 patient grid | ~18s | 0.08s | **216×** |
| Load 11 patients + PK | ~180s | 16.4s | **11×** |
| Run 12 experiments | ~hours | 24.7s | **~100×** |
| Terrarium build (one-time) | — | ~5 min | — |

## 6. Commit History

| Commit | Description |
|--------|-------------|
| `ecb5ee4` | fix(normalize): timezone bug — stored timeFormat instead of timezone |
| `f9ee523` | feat(grid,writer): warning logging, treatment tz normalization |
| `cc1e183` | feat(cli): batch aggregation (--patients, --subset both, merge, info) |
| `dd5e30e` | feat: data terrarium (make terrarium, profiles, manifest) |
| `af77f49` | feat(cgmencode): parquet bridge + rerun validation |
| *next* | feat: IOB validation experiment + process report |

## 7. Recommendations

### Immediate
1. **Adopt parquet path as default** for all future experiments — 100× faster, identical results.
2. **Run `make terrarium`** after any ns-data update to rebuild the parquet store.
3. **Patient b is now usable** for controller-behavior analysis, IOB-dependent modeling, and Loop vs Trio/oref0 comparison.

### Future Work
1. **Fix the JSON path too**: `real_data_adapter.py:349-354` should read oref0 IOB if the JSON path is still needed. Currently it only reads `loop.iob`.
2. **Patient j (no controller IOB)**: Has 0% IOB data from any source. May need alternative IOB estimation (PK from treatments).
3. **Outside researcher readiness**: Add `pip install -e .`, documentation, and example notebooks to ns2parquet.
4. **Online sync**: Consider S3/GCS upload for terrarium sharing across machines.

## 8. Conclusion

The parquet infrastructure is validated as a **drop-in replacement** for the JSON data path. The oref0/Trio IOB inclusion fix is confirmed material: patient b's IOB predictive power increases 10×, stratified outcomes become meaningful, and the spurious 98% "suspend" artifact is eliminated. The fix has zero impact on existing experiment findings because they use bolus-event correction detection, but it opens patient b to a new class of IOB-dependent analysis previously impossible with the old data path.
