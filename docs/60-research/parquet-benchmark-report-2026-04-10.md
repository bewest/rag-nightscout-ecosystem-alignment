# Parquet vs JSON Performance Benchmark Report

**Date**: 2026-04-10  
**Benchmark script**: `tools/cgmencode/benchmark_parquet_vs_json.py`  
**Raw data**: `externals/experiments/benchmark-parquet-vs-json.json`

## Test Environment

| Parameter | Value |
|-----------|-------|
| OS | Linux 6.18.7 (Ubuntu, glibc 2.39) |
| CPU | x86_64, 16 cores |
| RAM | 62.6 GB |
| Python | 3.12.3 |
| Storage | Local SSD |
| Dataset | 11 patients, ~6 months each |

## On-Disk Storage

| Format | Size | Ratio |
|--------|------|-------|
| JSON (11 patients × training) | **1,008 MB** | 1.0× |
| Parquet (terrarium) | **44 MB** | **23× smaller** |

Parquet file breakdown:

| File | Size | Contents |
|------|------|----------|
| `grid.parquet` | 17 MB | 529,288 rows × 44 columns (5-min research grid) |
| `devicestatus.parquet` | 15 MB | Controller IOB/COB records |
| `entries.parquet` | 7.8 MB | Raw CGM readings |
| `treatments.parquet` | 5.7 MB | Bolus, carbs, temp basal events |
| `profiles.parquet` | 16 KB | Therapy settings (ISF, CR, basal) |

## Benchmark Results

### 1. Single Patient Grid Load (3 trials, median)

Loading one patient's data into a 5-min research grid with 8 normalized features.

| Patient | JSON | Parquet | Speedup | Grid Rows |
|---------|------|---------|---------|-----------|
| a | 13.3s | 78ms | **169×** | 51,841 |
| b | 17.4s | 75ms | **232×** | 51,840 |
| c | 14.1s | 74ms | **190×** | 51,841 |

Patient b is slowest on JSON (224MB, largest dataset) but identical on parquet (pre-aggregated).

**Why the difference**: JSON path re-parses raw entries/treatments/devicestatus, resamples to 5-min grid, interpolates, normalizes — all on every load. Parquet reads the pre-built grid directly.

### 2. Raw Grid Read — All 11 Patients

Reading the entire `grid.parquet` into a single DataFrame (no feature construction):

| Operation | Time | Rows |
|-----------|------|------|
| `pd.read_parquet('grid.parquet')` | **51ms** | 529,288 |

This is the floor: 529K rows in 51ms from a 17MB file. Column-oriented storage and Snappy compression make this near-instantaneous.

### 3. Filtered/Columnar Read

Parquet supports predicate pushdown and column pruning — read only what you need:

| Query | Time | Rows |
|-------|------|------|
| Patient a, all 44 columns | 38ms | 51,841 |
| Patient a, 4 columns (glucose, iob, time, patient_id) | **11ms** | 51,841 |
| Patient b, all 44 columns | 36ms | 51,840 |
| Patient b, 4 columns | **10ms** | 51,840 |

Column pruning gives a further **3.5× speedup** over full-column reads. This is significant for exploratory analysis where you only need glucose + one feature at a time.

### 4. Full Pipeline — All Patients + PK Features

The complete data preparation path: load grid → reconstruct therapy attrs → build 8-channel pharmacokinetic features via bolus/basal convolution.

| Path | Time | Patients | Speedup |
|------|------|----------|---------|
| JSON (parse + grid + PK) | **2.4 min** | 11 | 1× |
| Parquet (load grid + PK) | **5.8s** | 11 | **25×** |

The PK feature build (exponential convolution over treatment events) is the same in both paths — only the grid loading differs. The 25× speedup (vs 170-230× for grid-only) reflects PK computation being the new bottleneck.

### 5. Incremental Scaling

How load time scales with patient count (parquet, including PK build):

| Patients | Time | Rows | Per-Patient |
|----------|------|------|-------------|
| 1 | 0.8s | 51,841 | 0.8s |
| 3 | 1.8s | 155,522 | 0.6s |
| 6 | 3.8s | 304,625 | 0.6s |
| 11 | 5.6s | 529,288 | 0.5s |

Scaling is **sublinear** — loading 11 patients takes only 7× the time of 1 patient, because the grid read is a single I/O operation (51ms) regardless of patient count. The per-patient PK build is the marginal cost.

## Experiment Iteration Speed

Using the rerun harness (`rerun_parquet.py`), 12 experiments across all 11 patients completed in **25 seconds** total. With the JSON path, a single experiment run would take ~2.4 minutes just for data loading, plus computation time.

| Workflow | JSON Path | Parquet Path | Impact |
|----------|-----------|--------------|--------|
| Load data + run 1 experiment | ~3 min | ~8s | Rapid iteration |
| Load data + run 12 experiments | ~30+ min | **25s** | Full suite in seconds |
| Exploratory query (1 patient, 4 cols) | ~14s | **11ms** | Interactive analysis |
| Rebuild after data update | N/A | ~5 min | One-time cost |

## Where Time Goes (Parquet Path)

For the full 11-patient pipeline (5.8s total):

| Phase | Time | % |
|-------|------|---|
| Read grid.parquet (51ms) + reconstruct attrs | ~0.2s | 3% |
| Build PK features (8-channel convolution × 11 patients) | ~5.6s | 97% |

The data loading is now negligible. **PK feature computation is the bottleneck.** Future optimization should target `build_continuous_pk_features()`, not I/O.

## Reproducibility

To rerun this benchmark:

```bash
cd tools/cgmencode
python3 benchmark_parquet_vs_json.py --trials 3 --patients a,b,c

# Skip the slow JSON full-pipeline benchmark:
python3 benchmark_parquet_vs_json.py --trials 5 --skip-json-all

# All patients for single-patient benchmarks:
python3 benchmark_parquet_vs_json.py --trials 3 --patients a,b,c,d,e,f,g,h,i,j,k
```

Results are saved to `externals/experiments/benchmark-parquet-vs-json.json` with full per-trial timing data for statistical analysis.

## Conclusions

1. **Grid loading: 170-230× faster** — the dominant speedup. Pre-aggregation eliminates redundant JSON parsing, resampling, and interpolation on every load.

2. **Full pipeline: 25× faster** — PK feature build (unchanged) is now the bottleneck, taking 97% of wall time.

3. **Storage: 23× smaller** — columnar encoding + Snappy compression. The entire 11-patient terrarium (44MB) fits in L3 cache on most modern CPUs.

4. **Column pruning: 3.5× additional** — reading only the columns you need gives 10ms single-patient access, enabling truly interactive exploratory analysis.

5. **Scaling is sublinear** — adding patients costs ~0.5s each (PK build), while the grid I/O is a fixed 51ms regardless of patient count.

6. **Experiment iteration cycles drop from minutes to seconds** — enabling rapid hypothesis testing and parameter sweeps that were impractical with the JSON path.
