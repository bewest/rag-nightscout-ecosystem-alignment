"""GENERATED FILE — do not edit.

Wire-shape PyArrow schema for the Nightscout ``profile`` collection.

Source:   aid-profile-2025.yaml
Evidence: reports/schema-census/profile.census.json
Emitter:  tools/nsschema/emit/pyarrow_emit.py

Regenerate with: make schema-emit

This is the shape documents have on the wire, not the analysis projection.
For the flattened, unit-normalized analysis schema see
``tools/ns2parquet/schemas.py``; ``tools/nsschema/emit/ns2parquet_drift.py``
checks that the two do not contradict each other.
"""

import pyarrow as pa

PROFILE_WIRE_SCHEMA = pa.schema([
    pa.field("_id", pa.large_string()),  # 100% docs, 11 sites; universal
    pa.field("created_at", pa.large_string()),  # 11% docs, 2 sites; vendor
    pa.field("defaultProfile", pa.large_string()),  # 100% docs, 11 sites; universal
    pa.field("enteredBy", pa.large_string()),  # 99% docs, 10 sites; core
    pa.field("identifier", pa.large_string()),
    pa.field("isValid", pa.bool_()),
    pa.field("loopSettings", pa.struct([
        pa.field("bundleIdentifier", pa.large_string()),
        pa.field("deviceToken", pa.large_string()),
        pa.field("dosingEnabled", pa.bool_()),
        pa.field("dosingStrategy", pa.large_string()),
        pa.field("maximumBasalRatePerHour", pa.float64()),
        pa.field("maximumBolus", pa.int64()),
        pa.field("minimumBGGuard", pa.float64()),
        pa.field("overridePresets", pa.list_(pa.struct([
                pa.field("duration", pa.int64()),
                pa.field("insulinNeedsScaleFactor", pa.float64()),
                pa.field("name", pa.large_string()),
                pa.field("symbol", pa.large_string()),
                pa.field("targetRange", pa.list_(pa.float64())),
            ]))),
        pa.field("preMealTargetRange", pa.list_(pa.float64())),
        pa.field("scheduleOverride", pa.struct([
            pa.field("duration", pa.int64()),
            pa.field("insulinNeedsScaleFactor", pa.float64()),
            pa.field("name", pa.large_string()),
            pa.field("symbol", pa.large_string()),
            pa.field("targetRange", pa.list_(pa.float64())),
        ])),
    ])),  # 99% docs, 10 sites; core
    pa.field("mills", pa.large_string()),  # 100% docs, 11 sites; universal; union of integer, string widened to string
    pa.field("srvCreated", pa.int64()),
    pa.field("srvModified", pa.int64()),  # 1% docs, 1 sites; rare
    pa.field("startDate", pa.large_string()),  # 100% docs, 11 sites; universal
    pa.field("store", pa.map_(pa.large_string(), pa.struct([
            pa.field("basal", pa.list_(pa.struct([
                    pa.field("time", pa.large_string()),
                    pa.field("timeAsSeconds", pa.int64()),
                    pa.field("value", pa.float64()),
                ]))),
            pa.field("carbratio", pa.list_(pa.struct([
                    pa.field("time", pa.large_string()),
                    pa.field("timeAsSeconds", pa.int64()),
                    pa.field("value", pa.float64()),
                ]))),
            pa.field("carbs_hr", pa.large_string()),  # union of number, string widened to string
            pa.field("delay", pa.large_string()),  # union of integer, string widened to string
            pa.field("dia", pa.float64()),
            pa.field("insulinCurve", pa.large_string()),
            pa.field("insulinPeakTime", pa.int64()),
            pa.field("sens", pa.list_(pa.struct([
                    pa.field("time", pa.large_string()),
                    pa.field("timeAsSeconds", pa.int64()),
                    pa.field("value", pa.float64()),
                ]))),
            pa.field("startDate", pa.large_string()),
            pa.field("target_high", pa.list_(pa.struct([
                    pa.field("time", pa.large_string()),
                    pa.field("timeAsSeconds", pa.int64()),
                    pa.field("value", pa.float64()),
                ]))),
            pa.field("target_low", pa.list_(pa.struct([
                    pa.field("time", pa.large_string()),
                    pa.field("timeAsSeconds", pa.int64()),
                    pa.field("value", pa.float64()),
                ]))),
            pa.field("timezone", pa.large_string()),
            pa.field("units", pa.large_string()),
        ]))),  # 100% docs, 11 sites; universal
    pa.field("units", pa.large_string()),  # 100% docs, 11 sites; universal
    pa.field("utcOffset", pa.int64()),
])
