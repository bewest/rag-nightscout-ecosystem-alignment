# ns2parquet

Convert Nightscout diabetes data (JSON) into columnar Parquet files
optimized for research, ML pipelines, and analytics.

Handles data from **any AID system** — Loop, AAPS, Trio, OpenAPS, or
CGM-only setups — and produces a uniform 5-minute research grid with
49 features aligned across patients.

## Install

ns2parquet requires Python 3.10+ and three packages:

```bash
pip install pandas numpy pyarrow
```

Then run from the repository root:

```bash
python3 -m tools.ns2parquet --help
```

## Quick Start

### Convert local Nightscout JSON

```bash
# Single patient
python3 -m tools.ns2parquet convert \
  --input path/to/patient/data \
  --patient-id alice \
  --output output/

# All patients in a directory
python3 -m tools.ns2parquet convert-all \
  --patients-dir path/to/patients \
  --output output/
```

### Ingest from a live Nightscout site

```bash
python3 -m tools.ns2parquet ingest \
  --url https://your-nightscout.example.com \
  --days 90 \
  --output output/
```

### Load in Python

```python
import pandas as pd

# Load the research grid (all patients, 5-min intervals)
grid = pd.read_parquet("output/grid.parquet")

# Filter to one patient
pat = grid[grid["patient_id"] == "alice"]

# Core features
print(pat[["glucose", "iob", "cob", "bolus", "carbs"]].describe())
```

## Input Formats

ns2parquet accepts three input formats:

### 1. Nightscout JSON (default)

A directory containing the four standard Nightscout collections:

```
patient_data/
  entries.json        # CGM glucose readings
  treatments.json     # Bolus, carbs, temp basals, events
  devicestatus.json   # AID controller state (Loop/oref0)
  profile.json        # Therapy settings (basal, ISF, CR, targets)
  settings.json       # (optional) Site config from /api/v1/status.json
```

These are the JSON arrays returned by the Nightscout REST API
(`/api/v1/entries.json`, etc.) or exported via Nightscout data tools.

### 2. OpenAPS Data Commons (ODC)

AAPS-native format from [OpenAPS Data Commons](https://openaps.org/data-commons/):

```bash
python3 -m tools.ns2parquet convert-odc \
  --odc-dir path/to/odc-dataset \
  --output output/
```

ODC directories contain numeric patient IDs with nested upload folders.
ns2parquet discovers patients automatically, converts AAPS-native JSON
(BgReadings.json, Treatments.json, APSData.json, etc.) into
Nightscout-shaped records, then runs the standard pipeline.

### 3. Live Nightscout API

```bash
python3 -m tools.ns2parquet ingest \
  --url https://your-ns.example.com \
  --days 90 --output output/

# Or use an env file
python3 -m tools.ns2parquet ingest \
  --env .env --days 90 --output output/
```

Fetches data in 7-day windows with automatic deduplication.

## Output Structure

ns2parquet produces six Parquet files. Every file includes a `patient_id`
column for efficient multi-patient queries.

```
output/
  entries.parquet        # CGM readings (sgv, direction, noise, ...)
  treatments.parquet     # Insulin/carb events (bolus, carbs, temp basal, ...)
  devicestatus.parquet   # AID controller state (IOB, COB, predictions, ...)
  profiles.parquet       # Therapy schedules (basal, ISF, CR, targets — expanded)
  settings.parquet       # Site configuration (units, plugins, thresholds)
  grid.parquet           # 5-min research grid (49 features, ready for analysis)
  manifest.json          # (optional) Build provenance + per-patient metadata
```

`grid.parquet` is the primary research artifact — a pre-computed 5-minute
grid joining glucose, IOB, COB, treatments, predictions, circadian
features, and sensor lifecycle into a single table. All glucose values
are in **mg/dL** (mmol/L sites are converted at ingestion).

See [DATA_DICTIONARY.md](DATA_DICTIONARY.md) for complete column
documentation.

## Directory Layouts for Common Use Cases

### Single-patient research

```
my-project/
  data/
    grid.parquet          # convert output
  notebooks/
    analysis.ipynb
```

```python
grid = pd.read_parquet("data/grid.parquet")
```

### Multi-patient cohort study

```
study/
  data/
    grid.parquet          # all patients merged into one file
    manifest.json         # patient metadata
  scripts/
    analyze.py
```

```python
grid = pd.read_parquet("data/grid.parquet")
for pid, pat in grid.groupby("patient_id"):
    print(f"{pid}: {len(pat)} rows, TIR={tir(pat):.1f}%")
```

### ML pipeline with train/validation splits

```
ml-project/
  data/
    training/
      grid.parquet        # ~180 days per patient
      manifest.json
    verification/
      grid.parquet        # held-out window
      manifest.json
  models/
    ...
```

Build this layout with `--subset both`:

```bash
python3 -m tools.ns2parquet convert-all \
  --patients-dir path/to/patients \
  --subset both \
  --output data/
```

Load train/test:

```python
train = pd.read_parquet("data/training/grid.parquet")
test  = pd.read_parquet("data/verification/grid.parquet")
```

### Merging multiple data sources

Combine Nightscout patients, ODC patients, and live sites into one
dataset:

```bash
# Convert each source
python3 -m tools.ns2parquet convert-all -d ns-patients/ -o tmp/ns/
python3 -m tools.ns2parquet convert-odc -d odc-dataset/ -o tmp/odc/
python3 -m tools.ns2parquet ingest --url https://site.example.com -o tmp/live/

# Merge into one output with deduplication
python3 -m tools.ns2parquet merge tmp/ns/ tmp/odc/ tmp/live/ \
  --output data/combined/

# Generate manifest
python3 -m tools.ns2parquet manifest --input data/combined/
```

### Privacy-safe sharing (opaque IDs)

```bash
python3 -m tools.ns2parquet convert-all \
  --patients-dir path/to/patients \
  --opaque-ids \
  --output data/

# Patient IDs become deterministic hashes: ns-a1b2c3d4e5f6
# Same input always produces the same ID, but not reversible
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `convert` | Convert a single patient JSON directory |
| `convert-all` | Convert all patients in a directory tree |
| `convert-odc` | Convert OpenAPS Data Commons patients |
| `ingest` | Fetch from live Nightscout API and convert |
| `merge` | Merge + deduplicate parquet from multiple dirs |
| `info` | Show summary of existing parquet files |
| `manifest` | Generate patient manifest JSON |

Common flags: `--output/-o` (output dir), `--quiet/-q` (suppress output),
`--skip-grid` (omit grid.parquet), `--opaque-ids` (hash patient names).

Run `python3 -m tools.ns2parquet <command> --help` for full options.

## Python API

```python
import tools.ns2parquet as ns

# Normalize raw JSON records
entries_df    = ns.normalize_entries(entries_list, patient_id="a")
treatments_df = ns.normalize_treatments(treatments_list, patient_id="a")
ds_df         = ns.normalize_devicestatus(ds_list, patient_id="a")
profiles_df   = ns.normalize_profiles(profile_doc, patient_id="a")
settings_df   = ns.normalize_settings(settings_dict, patient_id="a")

# Build research grid from a JSON directory
grid_df = ns.build_grid("path/to/patient/data", patient_id="a")

# Write to parquet (with append + dedup)
ns.write_parquet(grid_df, "output/", "grid", schema=ns.GRID_SCHEMA)

# Read back (with optional patient filter)
df = ns.read_parquet("output/", "grid", patient_id="a")

# Fetch from live Nightscout
entries = ns.fetch_entries(base_url, start_ms, end_ms)
```

## For cgmencode Users

The parquet bridge is a drop-in replacement for JSON loading:

```python
from tools.cgmencode.real_data_adapter import load_parquet_patients

# Replaces load_patients() — reads grid.parquet instead of re-parsing JSON
# ~16ms vs ~3s per patient
patients = load_parquet_patients("externals/ns-parquet/training")
```

Build the terrarium first:

```bash
make terrarium          # full build (all patients, training + verification)
make terrarium-tiny     # smoke-test build (2 patients, 7 days, ~800KB)
```

## Data Conventions

| Measurement | Unit | Notes |
|-------------|------|-------|
| Glucose (sgv, mbg) | mg/dL | mmol/L sites converted at ingestion |
| ISF | mg/dL per U | Converted from mmol/L if needed |
| CR | g per U | |
| Basal rate | U/hr | |
| Insulin | U | |
| Carbs | g | |
| Duration | minutes | Converted from seconds (Loop) or ms (AAPS) |
| Absorption time | minutes | Converted from seconds if Loop |
| Timestamps | UTC, ms precision | ISO 8601 or epoch ms accepted |
| Conversion factor | 18.01559 | mmol/L × 18.01559 = mg/dL |

## Key Design Decisions

- **Grid stores raw values** (mg/dL, units, grams), not normalized.
  Normalization happens at consumption time.
- **`loop_*` column prefix is historical.** These columns store
  predictions/actions from *any* AID controller (Loop, oref0, AAPS, Trio).
- **Deduplication** uses composite keys per collection (e.g., `patient_id +
  time` for grid, `patient_id + created_at + event_type` for treatments).
- **Overwrite mode** is the default for `convert`. Use `--append` to
  merge with existing output (deduplicates automatically).
- **zstd compression** for 20-25× size reduction vs JSON.

## Running Tests

```bash
# Fast tests (unit + fixture-based, ~4s)
make ns2parquet-tests

# Or directly
python3 -m pytest tools/ns2parquet/test_ns2parquet.py -v
```

233 tests covering all input formats, controller types, unit conversions,
corrupt data handling, and cross-pipeline parity with cgmencode.
