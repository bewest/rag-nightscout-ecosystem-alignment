# ns-parquet Data Terrarium

Pre-built Parquet store derived from `externals/ns-data/patients/`.

## Contents

```
training/           # ~180 days per patient
  entries.parquet     SGV readings (patient_id, date, sgv, direction, ...)
  treatments.parquet  Bolus, carbs, temp basal (patient_id, eventType, ...)
  devicestatus.parquet  Loop/oref0 IOB, COB, predictions (patient_id, ...)
  profiles.parquet    Therapy settings (patient_id, ISF, CR, basal, ...)
  grid.parquet        5-min research grid (patient_id, glucose, iob, cob, ...)
verification/       # Held-out window, same structure
manifest.json       # Build provenance (git sha, timestamp, patient list)
```

## Quick Start

```python
import pandas as pd

# Load pre-built research grid (all patients, 5-min intervals)
grid = pd.read_parquet('externals/ns-parquet/training/grid.parquet')

# Filter to one patient
pat_a = grid[grid['patient_id'] == 'a']

# Columns: glucose, iob, cob, bolus, carbs, net_basal, time_sin, time_cos, ...
print(pat_a[['glucose', 'iob', 'cob']].describe())
```

## Rebuild

```bash
make terrarium                # full rebuild (all patients, both subsets)
make terrarium-info           # show contents summary
```

Or manually:
```bash
python3 -m tools.ns2parquet convert-all \
  -d externals/ns-data/patients \
  --subset both \
  -o externals/ns-parquet
```

## For cgmencode

Use the bridge function instead of re-parsing JSON:

```python
from tools.cgmencode.real_data_adapter import load_parquet_patients

# Replaces load_patients() — reads grid.parquet instead of re-parsing JSON
patients = load_parquet_patients('externals/ns-parquet/training')
```

## Notes

- All glucose values in mg/dL (mmol/L sites pre-converted)
- Grid uses 5-minute intervals aligned to UTC
- `patient_id` column present in all files for filtering
- This directory is gitignored (derived data) — rebuild with `make terrarium`
