"""GENERATED FILE — do not edit.

Wire-shape PyArrow schema for the Nightscout ``devicestatus`` collection.

Source:   aid-devicestatus-2025.yaml
Evidence: reports/schema-census/devicestatus.census.json
Emitter:  tools/nsschema/emit/pyarrow_emit.py

Regenerate with: make schema-emit

This is the shape documents have on the wire, not the analysis projection.
For the flattened, unit-normalized analysis schema see
``tools/ns2parquet/schemas.py``; ``tools/nsschema/emit/ns2parquet_drift.py``
checks that the two do not contradict each other.
"""

import pyarrow as pa

DEVICESTATUS_WIRE_SCHEMA = pa.schema([
    pa.field("_id", pa.large_string(), metadata={"sensitivity": "identifying", "category": "identity"}),  # 100% docs, 11 sites; universal
    pa.field("configuration", pa.large_string(), metadata={"sensitivity": "identifying", "category": "therapy-setting"}),  # object with no observed fields; stored as JSON text
    pa.field("created_at", pa.large_string(), metadata={"sensitivity": "quasi-identifying", "category": "temporal"}),  # 100% docs, 11 sites; universal
    pa.field("device", pa.large_string(), metadata={"sensitivity": "descriptive", "category": "device"}),  # 100% docs, 11 sites; universal
    pa.field("identifier", pa.large_string(), metadata={"sensitivity": "identifying", "category": "identity"}),
    pa.field("isCharging", pa.bool_(), metadata={"sensitivity": "identifying", "category": "vocabulary"}),
    pa.field("isValid", pa.bool_(), metadata={"sensitivity": "identifying", "category": "vocabulary"}),
    pa.field("loop", pa.struct([
        pa.field("automaticDoseRecommendation", pa.struct([
            pa.field("bolusVolume", pa.float64()),
            pa.field("tempBasalAdjustment", pa.struct([
                pa.field("duration", pa.float64()),
                pa.field("rate", pa.float64()),
            ])),
            pa.field("timestamp", pa.large_string()),
        ])),
        pa.field("cob", pa.struct([
            pa.field("cob", pa.float64()),
            pa.field("timestamp", pa.large_string()),
        ])),
        pa.field("enacted", pa.struct([
            pa.field("bolusVolume", pa.float64()),
            pa.field("duration", pa.float64()),
            pa.field("rate", pa.float64()),
            pa.field("received", pa.bool_()),
            pa.field("timestamp", pa.large_string()),
        ])),
        pa.field("failureReason", pa.large_string()),
        pa.field("iob", pa.struct([
            pa.field("iob", pa.float64()),
            pa.field("timestamp", pa.large_string()),
        ])),
        pa.field("name", pa.large_string()),
        pa.field("predicted", pa.struct([
            pa.field("startDate", pa.large_string()),
            pa.field("values", pa.list_(pa.float64())),
        ])),
        pa.field("recommendedBolus", pa.float64()),
        pa.field("timestamp", pa.large_string()),
        pa.field("version", pa.large_string()),
    ]), metadata={"sensitivity": "descriptive", "category": "vocabulary"}),  # 85% docs, 10 sites; core
    pa.field("mills", pa.int64(), metadata={"sensitivity": "identifying", "category": "temporal"}),
    pa.field("openaps", pa.struct([
        pa.field("enacted", pa.struct([
            pa.field("COB", pa.int64()),
            pa.field("CR", pa.float64()),
            pa.field("IOB", pa.float64()),
            pa.field("ISF", pa.int64()),
            pa.field("TDD", pa.float64()),
            pa.field("bg", pa.int64()),
            pa.field("carbsReq", pa.int64()),
            pa.field("current_target", pa.int64()),
            pa.field("deliverAt", pa.large_string()),
            pa.field("duration", pa.int64()),
            pa.field("eventualBG", pa.int64()),
            pa.field("expectedDelta", pa.float64()),
            pa.field("id", pa.large_string()),
            pa.field("insulinForManualBolus", pa.float64()),
            pa.field("insulinReq", pa.float64()),
            pa.field("manualBolusErrorString", pa.int64()),
            pa.field("minDelta", pa.float64()),
            pa.field("predBGs", pa.struct([
                pa.field("COB", pa.list_(pa.int64())),
                pa.field("IOB", pa.list_(pa.int64())),
                pa.field("UAM", pa.list_(pa.int64())),
                pa.field("ZT", pa.list_(pa.int64())),
            ])),
            pa.field("rate", pa.float64()),
            pa.field("reason", pa.large_string()),
            pa.field("received", pa.bool_()),
            pa.field("reservoir", pa.float64()),
            pa.field("sensitivityRatio", pa.float64()),
            pa.field("temp", pa.large_string()),
            pa.field("threshold", pa.int64()),
            pa.field("timestamp", pa.large_string()),
            pa.field("units", pa.float64()),
        ])),
        pa.field("iob", pa.struct([
            pa.field("activity", pa.float64()),
            pa.field("basaliob", pa.float64()),
            pa.field("bolusinsulin", pa.float64()),
            pa.field("bolusiob", pa.float64()),
            pa.field("bolussnooze", pa.float64()),
            pa.field("iob", pa.float64()),
            pa.field("iobWithZeroTemp", pa.struct([
                pa.field("activity", pa.float64()),
                pa.field("basaliob", pa.float64()),
                pa.field("bolusinsulin", pa.float64()),
                pa.field("bolusiob", pa.float64()),
                pa.field("iob", pa.float64()),
                pa.field("netbasalinsulin", pa.float64()),
                pa.field("time", pa.large_string()),
            ])),
            pa.field("lastBolusTime", pa.int64()),
            pa.field("lastTemp", pa.struct([
                pa.field("date", pa.int64()),
                pa.field("duration", pa.float64()),
                pa.field("rate", pa.float64()),
                pa.field("started_at", pa.large_string()),
                pa.field("timestamp", pa.large_string()),
            ])),
            pa.field("netbasalinsulin", pa.float64()),
            pa.field("time", pa.large_string()),
        ])),
        pa.field("recommendedBolus", pa.float64()),
        pa.field("suggested", pa.struct([
            pa.field("COB", pa.int64()),
            pa.field("CR", pa.float64()),
            pa.field("IOB", pa.float64()),
            pa.field("ISF", pa.int64()),
            pa.field("TDD", pa.float64()),
            pa.field("bg", pa.int64()),
            pa.field("carbsReq", pa.int64()),
            pa.field("current_target", pa.int64()),
            pa.field("deliverAt", pa.large_string()),
            pa.field("duration", pa.int64()),
            pa.field("eventualBG", pa.int64()),
            pa.field("expectedDelta", pa.float64()),
            pa.field("id", pa.large_string()),
            pa.field("insulinForManualBolus", pa.float64()),
            pa.field("insulinReq", pa.float64()),
            pa.field("manualBolusErrorString", pa.int64()),
            pa.field("minDelta", pa.float64()),
            pa.field("predBGs", pa.struct([
                pa.field("COB", pa.list_(pa.int64())),
                pa.field("IOB", pa.list_(pa.int64())),
                pa.field("UAM", pa.list_(pa.int64())),
                pa.field("ZT", pa.list_(pa.int64())),
            ])),
            pa.field("rate", pa.float64()),
            pa.field("reason", pa.large_string()),
            pa.field("received", pa.bool_()),
            pa.field("reservoir", pa.float64()),
            pa.field("sensitivityRatio", pa.float64()),
            pa.field("targetBG", pa.int64()),
            pa.field("temp", pa.large_string()),
            pa.field("threshold", pa.int64()),
            pa.field("tick", pa.large_string()),
            pa.field("timestamp", pa.large_string()),
            pa.field("units", pa.float64()),
            pa.field("variable_sens", pa.float64()),
        ])),
        pa.field("version", pa.large_string()),
    ]), metadata={"sensitivity": "descriptive", "category": "vocabulary"}),  # 11% docs, 1 sites; vendor
    pa.field("override", pa.struct([
        pa.field("active", pa.bool_()),
        pa.field("currentCorrectionRange", pa.struct([
            pa.field("maxValue", pa.float64()),
            pa.field("minValue", pa.float64()),
        ])),
        pa.field("duration", pa.float64()),
        pa.field("multiplier", pa.float64()),
        pa.field("name", pa.large_string()),
        pa.field("timestamp", pa.large_string()),
    ]), metadata={"sensitivity": "descriptive", "category": "therapy-setting"}),  # 85% docs, 10 sites; core
    pa.field("pump", pa.struct([
        pa.field("battery", pa.struct([
            pa.field("display", pa.bool_()),
            pa.field("percent", pa.int64()),
            pa.field("status", pa.large_string()),
            pa.field("string", pa.large_string()),
            pa.field("voltage", pa.float64()),
        ])),
        pa.field("bolusIncrement", pa.float64()),
        pa.field("bolusing", pa.bool_()),
        pa.field("clock", pa.large_string()),
        pa.field("extended", pa.large_string()),  # object with no observed fields; stored as JSON text
        pa.field("manufacturer", pa.large_string()),
        pa.field("model", pa.large_string()),
        pa.field("pumpID", pa.large_string()),
        pa.field("reservoir", pa.float64()),
        pa.field("reservoir_display_override", pa.large_string()),
        pa.field("reservoir_level_override", pa.int64()),
        pa.field("secondsFromGMT", pa.int64()),
        pa.field("status", pa.struct([
            pa.field("bolusing", pa.bool_()),
            pa.field("status", pa.large_string()),
            pa.field("suspended", pa.bool_()),
            pa.field("timestamp", pa.large_string()),
        ])),
        pa.field("suspended", pa.bool_()),
    ]), metadata={"sensitivity": "descriptive", "category": "device"}),  # 96% docs, 10 sites; core
    pa.field("srvCreated", pa.int64(), metadata={"sensitivity": "identifying", "category": "temporal"}),
    pa.field("srvModified", pa.int64(), metadata={"sensitivity": "identifying", "category": "temporal"}),
    pa.field("uploader", pa.struct([
        pa.field("battery", pa.int64()),
        pa.field("batteryVoltage", pa.float64()),
        pa.field("isCharging", pa.bool_()),
        pa.field("name", pa.large_string()),
        pa.field("timestamp", pa.large_string()),
        pa.field("type", pa.large_string()),
    ]), metadata={"sensitivity": "descriptive", "category": "device"}),  # 100% docs, 11 sites; universal
    pa.field("uploaderBattery", pa.int64(), metadata={"sensitivity": "identifying", "category": "device"}),
    pa.field("utcOffset", pa.int64(), metadata={"sensitivity": "quasi-identifying", "category": "location"}),  # 100% docs, 11 sites; universal
])
