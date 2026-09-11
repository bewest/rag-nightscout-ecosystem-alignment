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
    pa.field("_id", pa.large_string(), metadata={"sensitivity": "identifying", "category": "identity"}),  # 100% docs, 11 sites; universal
    pa.field("app", pa.large_string(), metadata={"sensitivity": "identifying", "category": "vocabulary"}),
    pa.field("date", pa.float64(), metadata={"sensitivity": "quasi-identifying", "category": "temporal"}),  # 100% docs, 11 sites; universal
    pa.field("dateString", pa.large_string(), metadata={"sensitivity": "quasi-identifying", "category": "temporal"}),  # 100% docs, 11 sites; universal
    pa.field("delta", pa.float64(), metadata={"sensitivity": "descriptive", "category": "health-derived"}),  # 4% docs, 1 sites; sparse
    pa.field("device", pa.large_string(), metadata={"sensitivity": "quasi-identifying", "category": "device"}),  # 94% docs, 11 sites; core
    pa.field("direction", pa.large_string(), metadata={"sensitivity": "descriptive", "category": "vocabulary"}),  # 85% docs, 11 sites; core
    pa.field("filtered", pa.float64(), metadata={"sensitivity": "descriptive", "category": "health-measurement"}),  # 13% docs, 2 sites; vendor
    pa.field("glucose", pa.int64(), metadata={"sensitivity": "descriptive", "category": "health-measurement"}),  # 6% docs, 1 sites; vendor
    pa.field("identifier", pa.large_string(), metadata={"sensitivity": "identifying", "category": "identity"}),
    pa.field("intercept", pa.float64(), metadata={"sensitivity": "identifying", "category": "vocabulary"}),
    pa.field("isCalibration", pa.bool_(), metadata={"sensitivity": "descriptive", "category": "therapy-setting"}),  # 62% docs, 10 sites; core
    pa.field("isReadOnly", pa.bool_(), metadata={"sensitivity": "identifying", "category": "vocabulary"}),
    pa.field("isValid", pa.bool_(), metadata={"sensitivity": "identifying", "category": "vocabulary"}),
    pa.field("mbg", pa.float64(), metadata={"sensitivity": "descriptive", "category": "health-measurement"}),  # 0% docs, 10 sites; common
    pa.field("modifiedBy", pa.large_string(), metadata={"sensitivity": "identifying", "category": "identity"}),
    pa.field("noise", pa.int64(), metadata={"sensitivity": "descriptive", "category": "health-measurement"}),  # 7% docs, 1 sites; vendor
    pa.field("rssi", pa.int64(), metadata={"sensitivity": "descriptive", "category": "vocabulary"}),  # 4% docs, 1 sites; sparse
    pa.field("scale", pa.float64(), metadata={"sensitivity": "identifying", "category": "therapy-setting"}),
    pa.field("sgv", pa.float64(), metadata={"sensitivity": "descriptive", "category": "health-measurement"}),  # 100% docs, 11 sites; universal
    pa.field("slope", pa.float64(), metadata={"sensitivity": "identifying", "category": "vocabulary"}),
    pa.field("srvCreated", pa.int64(), metadata={"sensitivity": "identifying", "category": "temporal"}),
    pa.field("srvModified", pa.int64(), metadata={"sensitivity": "identifying", "category": "temporal"}),
    pa.field("subject", pa.large_string(), metadata={"sensitivity": "identifying", "category": "identity"}),
    pa.field("sysTime", pa.large_string(), metadata={"sensitivity": "quasi-identifying", "category": "temporal"}),  # 100% docs, 11 sites; universal
    pa.field("trend", pa.int64(), metadata={"sensitivity": "descriptive", "category": "health-derived"}),  # 72% docs, 10 sites; core
    pa.field("trendRate", pa.float64(), metadata={"sensitivity": "descriptive", "category": "health-derived"}),  # 46% docs, 10 sites; core
    pa.field("type", pa.large_string(), metadata={"sensitivity": "descriptive", "category": "vocabulary"}),  # 100% docs, 11 sites; universal
    pa.field("unfiltered", pa.float64(), metadata={"sensitivity": "descriptive", "category": "health-measurement"}),  # 13% docs, 2 sites; vendor
    pa.field("units", pa.large_string(), metadata={"sensitivity": "identifying", "category": "vocabulary"}),
    pa.field("utcOffset", pa.int64(), metadata={"sensitivity": "quasi-identifying", "category": "location"}),  # 100% docs, 11 sites; universal
])
