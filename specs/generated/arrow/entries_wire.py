"""GENERATED FILE — do not edit.

Wire-shape PyArrow schema for the Nightscout ``entries`` collection.

Source:   aid-entries-2025.yaml
Evidence: reports/schema-census/entries.census.json
Emitter:  tools/nsschema/emit/pyarrow_emit.py

Regenerate with: make schema-emit

This is the shape documents have on the wire, not the analysis projection.
For the flattened, unit-normalized analysis schema see
``tools/ns2parquet/schemas.py``; ``tools/nsschema/emit/ns2parquet_drift.py``
checks that the two do not contradict each other.
"""

import pyarrow as pa

ENTRIES_WIRE_SCHEMA = pa.schema([
    pa.field("_id", pa.large_string()),  # 100% docs, 11 sites; universal
    pa.field("app", pa.large_string()),
    pa.field("date", pa.float64()),  # 100% docs, 11 sites; universal
    pa.field("dateString", pa.large_string()),  # 100% docs, 11 sites; universal
    pa.field("delta", pa.float64()),  # 4% docs, 1 sites; sparse
    pa.field("device", pa.large_string()),  # 94% docs, 11 sites; core
    pa.field("direction", pa.large_string()),  # 85% docs, 11 sites; core
    pa.field("filtered", pa.float64()),  # 13% docs, 2 sites; vendor
    pa.field("glucose", pa.int64()),  # 6% docs, 1 sites; vendor
    pa.field("identifier", pa.large_string()),
    pa.field("intercept", pa.float64()),
    pa.field("isCalibration", pa.bool_()),  # 62% docs, 10 sites; core
    pa.field("isReadOnly", pa.bool_()),
    pa.field("isValid", pa.bool_()),
    pa.field("mbg", pa.float64()),  # 0% docs, 10 sites; common
    pa.field("modifiedBy", pa.large_string()),
    pa.field("noise", pa.int64()),  # 7% docs, 1 sites; vendor
    pa.field("rssi", pa.int64()),  # 4% docs, 1 sites; sparse
    pa.field("scale", pa.float64()),
    pa.field("sgv", pa.float64()),  # 100% docs, 11 sites; universal
    pa.field("slope", pa.float64()),
    pa.field("srvCreated", pa.int64()),
    pa.field("srvModified", pa.int64()),
    pa.field("subject", pa.large_string()),
    pa.field("sysTime", pa.large_string()),  # 100% docs, 11 sites; universal
    pa.field("trend", pa.int64()),  # 72% docs, 10 sites; core
    pa.field("trendRate", pa.float64()),  # 46% docs, 10 sites; core
    pa.field("type", pa.large_string()),  # 100% docs, 11 sites; universal
    pa.field("unfiltered", pa.float64()),  # 13% docs, 2 sites; vendor
    pa.field("units", pa.large_string()),
    pa.field("utcOffset", pa.int64()),  # 100% docs, 11 sites; universal
])
