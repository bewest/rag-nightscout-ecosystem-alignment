"""GENERATED FILE — do not edit.

Wire-shape PyArrow schema for the Nightscout ``treatments`` collection.

Source:   aid-treatments-2025.yaml
Evidence: reports/schema-census/treatments.census.json
Emitter:  tools/nsschema/emit/pyarrow_emit.py

Regenerate with: make schema-emit

This is the shape documents have on the wire, not the analysis projection.
For the flattened, unit-normalized analysis schema see
``tools/ns2parquet/schemas.py``; ``tools/nsschema/emit/ns2parquet_drift.py``
checks that the two do not contradict each other.
"""

import pyarrow as pa

TREATMENTS_WIRE_SCHEMA = pa.schema([
    pa.field("_id", pa.large_string(), metadata={"sensitivity": "identifying", "category": "identity"}),  # 100% docs, 11 sites; universal
    pa.field("absolute", pa.float64(), metadata={"sensitivity": "descriptive", "category": "vocabulary"}),  # 55% docs, 10 sites; core
    pa.field("absorptionTime", pa.int64(), metadata={"sensitivity": "descriptive", "category": "therapy-setting"}),  # 2% docs, 10 sites; common
    pa.field("amount", pa.float64(), metadata={"sensitivity": "descriptive", "category": "vocabulary"}),  # 46% docs, 10 sites; core
    pa.field("app", pa.large_string(), metadata={"sensitivity": "identifying", "category": "vocabulary"}),
    pa.field("automatic", pa.bool_(), metadata={"sensitivity": "descriptive", "category": "vocabulary"}),  # 81% docs, 10 sites; core
    pa.field("bolusType", pa.large_string(), metadata={"sensitivity": "identifying", "category": "vocabulary"}),
    pa.field("carbs", pa.float64(), metadata={"sensitivity": "descriptive", "category": "health-measurement"}),  # 100% docs, 11 sites; universal; null observed
    pa.field("correctionRange", pa.list_(pa.float64()), metadata={"sensitivity": "descriptive", "category": "vocabulary"}),  # 0% docs, 7 sites; common
    pa.field("created_at", pa.large_string(), metadata={"sensitivity": "quasi-identifying", "category": "temporal"}),  # 100% docs, 11 sites; universal
    pa.field("device", pa.large_string(), metadata={"sensitivity": "identifying", "category": "device"}),
    pa.field("duration", pa.float64(), metadata={"sensitivity": "descriptive", "category": "therapy-setting"}),  # 91% docs, 10 sites; core
    pa.field("durationType", pa.large_string(), metadata={"sensitivity": "quasi-identifying", "category": "therapy-setting"}),  # 0% docs, 1 sites; rare
    pa.field("endmills", pa.int64(), metadata={"sensitivity": "quasi-identifying", "category": "temporal"}),  # 0% docs, 1 sites; rare
    pa.field("enteredBy", pa.large_string(), metadata={"sensitivity": "identifying", "category": "identity"}),  # 100% docs, 11 sites; universal
    pa.field("eventType", pa.large_string(), metadata={"sensitivity": "descriptive", "category": "vocabulary"}),  # 100% docs, 11 sites; universal
    pa.field("fat", pa.float64(), metadata={"sensitivity": "descriptive", "category": "vocabulary"}),  # 2% docs, 1 sites; sparse
    pa.field("foodType", pa.large_string(), metadata={"sensitivity": "quasi-identifying", "category": "vocabulary"}),  # 2% docs, 10 sites; common
    pa.field("glucose", pa.float64(), metadata={"sensitivity": "descriptive", "category": "health-measurement"}),  # 0% docs, 1 sites; sparse
    pa.field("glucoseType", pa.large_string(), metadata={"sensitivity": "quasi-identifying", "category": "health-measurement"}),  # 0% docs, 1 sites; sparse
    pa.field("id", pa.large_string(), metadata={"sensitivity": "identifying", "category": "identity"}),  # 15% docs, 1 sites; vendor
    pa.field("identifier", pa.large_string(), metadata={"sensitivity": "identifying", "category": "identity"}),  # 0% docs, 1 sites; sparse
    pa.field("insulin", pa.float64(), metadata={"sensitivity": "descriptive", "category": "health-measurement"}),  # 100% docs, 11 sites; universal; null observed
    pa.field("insulinNeedsScaleFactor", pa.float64(), metadata={"sensitivity": "descriptive", "category": "therapy-setting"}),  # 1% docs, 9 sites; common
    pa.field("insulinType", pa.large_string(), metadata={"sensitivity": "descriptive", "category": "therapy-setting"}),  # 80% docs, 10 sites; core
    pa.field("isBasalInsulin", pa.bool_(), metadata={"sensitivity": "identifying", "category": "therapy-setting"}),
    pa.field("isReadOnly", pa.bool_(), metadata={"sensitivity": "identifying", "category": "vocabulary"}),
    pa.field("isValid", pa.bool_(), metadata={"sensitivity": "identifying", "category": "vocabulary"}),
    pa.field("mills", pa.int64(), metadata={"sensitivity": "quasi-identifying", "category": "temporal"}),  # 0% docs, 1 sites; rare
    pa.field("modifiedBy", pa.large_string(), metadata={"sensitivity": "identifying", "category": "identity"}),
    pa.field("notes", pa.large_string(), metadata={"sensitivity": "identifying", "category": "free-text"}),  # 1% docs, 10 sites; common
    pa.field("percent", pa.float64(), metadata={"sensitivity": "identifying", "category": "therapy-setting"}),
    pa.field("percentage", pa.int64(), metadata={"sensitivity": "identifying", "category": "therapy-setting"}),
    pa.field("profile", pa.large_string(), metadata={"sensitivity": "identifying", "category": "therapy-setting"}),
    pa.field("profileJson", pa.large_string(), metadata={"sensitivity": "identifying", "category": "therapy-setting"}),
    pa.field("programmed", pa.float64(), metadata={"sensitivity": "descriptive", "category": "vocabulary"}),  # 35% docs, 10 sites; core
    pa.field("protein", pa.float64(), metadata={"sensitivity": "descriptive", "category": "vocabulary"}),  # 2% docs, 1 sites; sparse
    pa.field("pumpId", pa.int64(), metadata={"sensitivity": "identifying", "category": "device"}),
    pa.field("pumpSerial", pa.large_string(), metadata={"sensitivity": "identifying", "category": "device"}),
    pa.field("pumpType", pa.large_string(), metadata={"sensitivity": "identifying", "category": "device"}),
    pa.field("rate", pa.float64(), metadata={"sensitivity": "descriptive", "category": "therapy-setting"}),  # 55% docs, 10 sites; core
    pa.field("reason", pa.large_string(), metadata={"sensitivity": "identifying", "category": "free-text"}),  # 1% docs, 10 sites; common
    pa.field("remoteAddress", pa.large_string(), metadata={"sensitivity": "identifying", "category": "vocabulary"}),  # 0% docs, 3 sites; common
    pa.field("srvCreated", pa.int64(), metadata={"sensitivity": "identifying", "category": "temporal"}),
    pa.field("srvModified", pa.int64(), metadata={"sensitivity": "identifying", "category": "temporal"}),
    pa.field("subject", pa.large_string(), metadata={"sensitivity": "identifying", "category": "identity"}),
    pa.field("syncIdentifier", pa.large_string(), metadata={"sensitivity": "identifying", "category": "identity"}),  # 83% docs, 10 sites; core
    pa.field("targetBottom", pa.float64(), metadata={"sensitivity": "descriptive", "category": "therapy-setting"}),  # 0% docs, 1 sites; sparse
    pa.field("targetTop", pa.float64(), metadata={"sensitivity": "descriptive", "category": "therapy-setting"}),  # 0% docs, 1 sites; sparse
    pa.field("temp", pa.large_string(), metadata={"sensitivity": "descriptive", "category": "vocabulary"}),  # 46% docs, 10 sites; core
    pa.field("timeshift", pa.int64(), metadata={"sensitivity": "identifying", "category": "temporal"}),
    pa.field("timestamp", pa.large_string(), metadata={"sensitivity": "quasi-identifying", "category": "temporal"}),  # 84% docs, 10 sites; core; union of number, string widened to string
    pa.field("type", pa.large_string(), metadata={"sensitivity": "descriptive", "category": "vocabulary"}),  # 35% docs, 10 sites; core
    pa.field("unabsorbed", pa.float64(), metadata={"sensitivity": "descriptive", "category": "vocabulary"}),  # 35% docs, 10 sites; core
    pa.field("units", pa.large_string(), metadata={"sensitivity": "quasi-identifying", "category": "vocabulary"}),  # 0% docs, 1 sites; sparse
    pa.field("userEnteredAt", pa.large_string(), metadata={"sensitivity": "quasi-identifying", "category": "vocabulary"}),  # 2% docs, 10 sites; common
    pa.field("userLastModifiedAt", pa.large_string(), metadata={"sensitivity": "quasi-identifying", "category": "temporal"}),  # 0% docs, 5 sites; common
    pa.field("utcOffset", pa.int64(), metadata={"sensitivity": "quasi-identifying", "category": "location"}),  # 100% docs, 11 sites; universal
])
