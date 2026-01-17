# Entries Collection Deep Dive

This document provides comprehensive field-by-field mapping of glucose data across AID systems (Loop, AAPS, Trio) and data uploaders (xDrip+) to the Nightscout `entries` collection.

---

## Overview

The Nightscout `entries` collection stores all glucose observations:
- **SGV (Sensor Glucose Values)**: CGM readings
- **MBG (Meter Blood Glucose)**: Fingerstick calibrations
- **CAL**: Calibration records

Each system has its own internal glucose data model that must be translated to/from Nightscout's format.

### Data Flow Patterns

| System | Primary Role | Upload | Download |
|--------|--------------|--------|----------|
| **xDrip+** | Producer (CGM data source) | Yes (primary) | Rare |
| **Loop** | Consumer (uses for predictions) | No (consumer only) | Yes (via Share/NS/CGMManager) |
| **AAPS** | Consumer (uses for predictions) | Yes (rebroadcast) | Yes |
| **Trio** | Consumer (uses for predictions) | No (consumer only) | Yes (via Share/NS/CGMManager) |

**Key Insight**: xDrip+ is often the authoritative glucose producer, while Loop/AAPS/Trio are primarily consumers. Loop and Trio do not upload CGM entries to Nightscout—they receive glucose data from CGM apps (via CGMManager plugins) or download from Nightscout/Share. AAPS may rebroadcast readings it receives. This creates potential for duplicate records when multiple uploaders (xDrip+, AAPS, Spike) upload the same readings.

---

## Nightscout Entries Schema

### Core Fields

| Field | Type | Description | Required |
|-------|------|-------------|----------|
| `_id` | ObjectId/String | MongoDB document ID | Yes |
| `type` | String | Entry type: `sgv`, `mbg`, `cal` | Yes |
| `sgv` | Number | Sensor glucose value (mg/dL) | For sgv type |
| `mbg` | Number | Meter blood glucose (mg/dL) | For mbg type |
| `direction` | String | Trend arrow name | No |
| `date` | Number | Epoch milliseconds | Yes |
| `dateString` | String | ISO 8601 timestamp | Yes |
| `device` | String | Source device identifier | No |
| `noise` | Number | Signal quality (1-4) | No |
| `filtered` | Number | Filtered raw value | No |
| `unfiltered` | Number | Unfiltered raw value | No |
| `rssi` | Number | Signal strength | No |

### Entry Types

| Type | Purpose | Primary Fields |
|------|---------|----------------|
| `sgv` | CGM sensor reading | `sgv`, `direction`, `noise`, `filtered`, `unfiltered` |
| `mbg` | Fingerstick meter reading | `mbg` |
| `cal` | Calibration record | `slope`, `intercept`, `scale` |

---

## SGV Field Mapping

### Core Fields

| Field | Nightscout | Loop | AAPS | Trio | xDrip+ |
|-------|------------|------|------|------|--------|
| **Glucose value** | `sgv` | `quantity` (HKQuantity) | `value` | `sgv` | `calculated_value` |
| **Timestamp** | `date` | `startDate` | `timestamp` | `date` | `timestamp` |
| **Timestamp string** | `dateString` | ISO from `startDate` | ISO conversion | `dateString` | N/A (computed) |
| **Trend arrow** | `direction` | `trendType` (GlucoseTrend) | `trendArrow` | `direction` | `dg_slope` → direction |
| **Signal quality** | `noise` | N/A | `noise` | `noise` | `noise` |
| **Device** | `device` | `provenanceIdentifier` | `sourceSensor` | N/A | `sensor_uuid` |
| **Entry type** | `type` | Inferred | Inferred | `type` | Inferred |
| **Sync identity** | `_id` | N/A | `interfaceIDs.nightscoutId` | `_id` | `uuid` |

### Filtered/Unfiltered Raw Values

| Field | Nightscout | AAPS | xDrip+ | Purpose |
|-------|------------|------|--------|---------|
| **Unfiltered raw** | `unfiltered` | N/A | `raw_data` | Unprocessed sensor signal |
| **Filtered raw** | `filtered` | N/A | `filtered_data` | Noise-reduced sensor signal |
| **Calibrated value** | `sgv` | `value` | `calculated_value` | Final glucose estimate |
| **Raw** | N/A | `raw` | `raw_calculated` | Intermediate calculation |

**Note**: Loop and Trio (iOS) do not typically expose or upload raw sensor values—they rely on the CGM transmitter's calibrated readings.

---

## Direction (Trend Arrow) Mapping

### Nightscout Direction Strings

| Direction | Rate (mg/dL/min) | Unicode Arrow |
|-----------|------------------|---------------|
| `DoubleUp` | > 3 | ⇈ |
| `SingleUp` | 2 to 3 | ↑ |
| `FortyFiveUp` | 1 to 2 | ↗ |
| `Flat` | -1 to 1 | → |
| `FortyFiveDown` | -1 to -2 | ↘ |
| `SingleDown` | -2 to -3 | ↓ |
| `DoubleDown` | < -3 | ⇊ |
| `NOT COMPUTABLE` | N/A | - |
| `RATE OUT OF RANGE` | N/A | - |

### Cross-System Direction Mapping

| Nightscout | Loop (GlucoseTrend) | AAPS (TrendArrow) | Trio (Direction) | xDrip+ (enum) |
|------------|---------------------|-------------------|------------------|---------------|
| `DoubleUp` | `.upUpUp` | `DOUBLE_UP` | `DoubleUp` | `DOUBLE_UP (1)` |
| `SingleUp` | `.upUp` | `SINGLE_UP` | `SingleUp` | `SINGLE_UP (2)` |
| `FortyFiveUp` | `.up` | `FORTY_FIVE_UP` | `FortyFiveUp` | `FORTY_FIVE_UP (3)` |
| `Flat` | `.flat` | `FLAT` | `Flat` | `FLAT (4)` |
| `FortyFiveDown` | `.down` | `FORTY_FIVE_DOWN` | `FortyFiveDown` | `FORTY_FIVE_DOWN (5)` |
| `SingleDown` | `.downDown` | `SINGLE_DOWN` | `SingleDown` | `SINGLE_DOWN (6)` |
| `DoubleDown` | `.downDownDown` | `DOUBLE_DOWN` | `DoubleDown` | `DOUBLE_DOWN (7)` |
| `NOT COMPUTABLE` | N/A | `NONE` | `notComputable` | `NOT_COMPUTABLE (8)` |
| `RATE OUT OF RANGE` | N/A | N/A | `rateOutOfRange` | `OUT_OF_RANGE (9)` |
| N/A | N/A | `TRIPLE_UP` | `TripleUp` | N/A |
| N/A | N/A | `TRIPLE_DOWN` | `TripleDown` | N/A |

**GAP-ENTRY-001**: Triple arrows (`TRIPLE_UP`, `TRIPLE_DOWN`) exist in AAPS and Trio but have no Nightscout equivalent. These are typically mapped to `DoubleUp`/`DoubleDown` on upload, losing granularity.

### Loop GlucoseTrend Implementation

```swift
// loop:LoopKit/LoopKit/GlucoseKit/GlucoseTrend.swift
public enum GlucoseTrend: Int, CaseIterable {
    case upUpUp       = 1   // > 3 mg/dL/min
    case upUp         = 2   // 2-3 mg/dL/min
    case up           = 3   // 1-2 mg/dL/min
    case flat         = 4   // -1 to 1 mg/dL/min
    case down         = 5   // -1 to -2 mg/dL/min
    case downDown     = 6   // -2 to -3 mg/dL/min
    case downDownDown = 7   // < -3 mg/dL/min
}
```

### AAPS TrendArrow Implementation

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/GlucoseValue.kt
enum class TrendArrow {
    NONE,
    TRIPLE_UP,
    DOUBLE_UP,
    SINGLE_UP,
    FORTY_FIVE_UP,
    FLAT,
    FORTY_FIVE_DOWN,
    SINGLE_DOWN,
    DOUBLE_DOWN,
    TRIPLE_DOWN
}
```

### Trio Direction Implementation

```swift
// trio:BloodGlucose.swift
enum Direction: String {
    case tripleUp = "TripleUp"
    case doubleUp = "DoubleUp"
    case singleUp = "SingleUp"
    case fortyFiveUp = "FortyFiveUp"
    case flat = "Flat"
    case fortyFiveDown = "FortyFiveDown"
    case singleDown = "SingleDown"
    case doubleDown = "DoubleDown"
    case tripleDown = "TripleDown"
    case none = "NONE"
    case notComputable = "NOT COMPUTABLE"
    case rateOutOfRange = "RATE OUT OF RANGE"
}
```

### xDrip+ Direction Calculation

```java
// xdrip:models/BgReading.java → Dex_Constants.TREND_ARROW_VALUES
NONE(0),
DOUBLE_UP(1),       // Rising rapidly (>3 mg/dL/min)
SINGLE_UP(2),       // Rising
FORTY_FIVE_UP(3),   // Rising slowly
FLAT(4),            // Stable
FORTY_FIVE_DOWN(5), // Falling slowly
SINGLE_DOWN(6),     // Falling
DOUBLE_DOWN(7),     // Falling rapidly (<-3 mg/dL/min)
NOT_COMPUTABLE(8),  // Cannot compute
OUT_OF_RANGE(9)     // Sensor error
```

xDrip+ calculates direction from `dg_slope` (Dexcom native slope) or `calculated_value_slope` (local calculation).

---

## Noise Level Mapping

### Nightscout Noise Values

| Value | Meaning | Description |
|-------|---------|-------------|
| 1 | Clean | Reliable reading |
| 2 | Light | Minor noise |
| 3 | Medium | Some interference |
| 4 | Heavy | Significant noise, reading may be unreliable |

### Cross-System Noise Handling

| System | Noise Field | Values | Usage |
|--------|-------------|--------|-------|
| **Nightscout** | `noise` | 1-4 | Stored and displayed |
| **Loop** | N/A | N/A | Does not track noise level |
| **AAPS** | `noise` | Double | Algorithm may filter high-noise readings |
| **Trio** | `noise` | Int | Passes through from NS |
| **xDrip+** | `noise` | String | Calculated locally; displayed as indicator |

**GAP-ENTRY-002**: Loop does not consume or expose noise data, potentially using readings that other systems would filter.

---

## Glucose Source Attribution

### Nightscout `device` Field

The `device` field identifies the glucose data source but has no standardized format:

| Source | Example `device` Value |
|--------|------------------------|
| xDrip+ | `xDrip-DexcomG6` |
| Dexcom Share | `share2` |
| Loop CGMManager | `loop://iPhone` |
| AAPS | `AAPS` |
| Spike | `Spike` |
| Libre | `nightguard` or `bubble` |

### Source Sensor (AAPS)

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/GlucoseValue.kt
enum class SourceSensor {
    DEXCOM_NATIVE_UNKNOWN,
    DEXCOM_G6_NATIVE,
    DEXCOM_G5_NATIVE,
    DEXCOM_G7_NATIVE,
    LIBRE_1_NATIVE,
    LIBRE_2_NATIVE,
    LIBRE_3_NATIVE,
    POCTECH_NATIVE,
    GLUNOVO_NATIVE,
    MM_600_SERIES,
    EVERSENSE,
    AIDEX,
    RANDOM,
    UNKNOWN
}
```

**GAP-ENTRY-003**: No standardized source taxonomy across systems. The `device` field is free-form text, making programmatic source identification unreliable.

---

## CGM vs Meter Reading Distinction

### Type Field Usage

| Entry Type | Nightscout Field | Source | Purpose |
|------------|------------------|--------|---------|
| `sgv` | `sgv` | CGM sensor | Continuous readings |
| `mbg` | `mbg` | Fingerstick meter | Manual calibration/verification |
| `cal` | `slope`, `intercept`, `scale` | Calibration calculation | Sensor calibration parameters |

### AAPS Glucose vs TherapyEvent

AAPS distinguishes CGM from meter readings via entity type:

| Data Type | AAPS Entity | Nightscout Type | Notes |
|-----------|-------------|-----------------|-------|
| CGM reading | `GlucoseValue` | `entries` (type: `sgv`) | Continuous sensor data |
| Meter reading | `TherapyEvent` (FINGER_STICK_BG_VALUE) | `treatments` (BG Check) | Manual fingerstick |

**Key Difference**: Meter readings are **treatments** in Nightscout (eventType: `BG Check`), not entries.

### xDrip+ BloodTest Entity

```java
// xdrip:models/BloodTest.java
@Table(name = "BloodTest", id = BaseColumns._ID)
public class BloodTest extends Model {
    @Column(name = "timestamp", index = true)
    public long timestamp;
    
    @Column(name = "mgdl")
    public double mgdl;
    
    @Column(name = "source")
    public String source;  // "Manual Entry", "Contour Next", etc.
}
```

xDrip+ uploads meter readings as Nightscout treatments (`BG Check`), not entries.

---

## Timestamp Handling

### Epoch Milliseconds Convention

All systems use epoch milliseconds internally, but ISO 8601 strings are used for display.

| System | Internal Timestamp | Nightscout Upload |
|--------|-------------------|-------------------|
| **Loop** | `Date` object | ISO 8601 string |
| **AAPS** | `timestamp: Long` (epoch ms) | Both `date` (epoch) and `dateString` (ISO) |
| **Trio** | `date: Decimal` (epoch ms) | Both fields |
| **xDrip+** | `timestamp: long` (epoch ms) | `date` (epoch ms) |

### UTC Offset Handling

| System | Timezone Strategy | Field |
|--------|-------------------|-------|
| **AAPS** | Fixed UTC offset | `utcOffset: Long` |
| **Loop** | Device timezone | N/A (uses Date) |
| **xDrip+** | Device timezone | N/A |
| **Nightscout** | UTC preferred | `dateString` in UTC |

**Note**: AAPS stores a fixed `utcOffset` at creation time, which does not update for DST changes.

---

## Stale Data Handling

### Definition of Staleness

| System | Stale Threshold | Action |
|--------|-----------------|--------|
| **Loop** | ~15 minutes | Open loop (no automatic dosing) |
| **AAPS** | Configurable (~10-15 min) | Open loop mode |
| **Trio** | ~15 minutes | Open loop mode |
| **xDrip+** | Configurable alerts | Visual warning only |
| **Nightscout** | Client-side | Displays "stale" indicator |

### Loop Glucose Recency

```swift
// Loop uses glucose recency to determine closed-loop eligibility
let glucoseDate = latestGlucose.startDate
let staleness = Date().timeIntervalSince(glucoseDate)
let isStale = staleness > TimeInterval(minutes: 15)
```

### AAPS Stale Detection

```kotlin
// AAPS validates glucose recency before dosing
val lastBgTimestamp = glucoseValue.timestamp
val now = System.currentTimeMillis()
val ageMinutes = (now - lastBgTimestamp) / 60000
val isStale = ageMinutes > maxMinutesSinceLastBg
```

---

## xDrip+ Local Web Server (Port 17580)

xDrip+ provides an alternative data access path via its local web server, which emulates Nightscout API endpoints.

### Endpoint: `/sgv.json`

**URL**: `http://127.0.0.1:17580/sgv.json`

**Response Format**:
```json
[
    {
        "date": 1705421234567,
        "dateString": "2026-01-16T12:00:34.567Z",
        "sgv": 120,
        "delta": 2.5,
        "direction": "Flat",
        "noise": 1,
        "units_hint": "mgdl"
    }
]
```

### Additional Extensions (First Record Only)

| Field | Type | Description |
|-------|------|-------------|
| `units_hint` | String | `mgdl` or `mmol` |
| `delta` | Number | Change since last reading |
| `sensor.age` | Number | Sensor age in milliseconds |
| `sensor.start` | Number | Sensor start timestamp |
| `collector` | String | Alert message if any |

**Use Case**: Watchfaces, automation apps (Tasker), and other tools can query glucose data without cloud connectivity.

---

## Upload/Download Patterns

### Producer-Consumer Relationships

```
┌──────────────┐         ┌──────────────┐
│   CGM Tx     │────────▶│   xDrip+     │
│ (G6/G7/Libre)│         │  (Producer)  │
└──────────────┘         └──────┬───────┘
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
              ┌──────────┐ ┌──────────┐ ┌──────────┐
              │Nightscout│ │   AAPS   │ │  Garmin  │
              │ (Store)  │ │ (Consume)│ │  Watch   │
              └────┬─────┘ └──────────┘ └──────────┘
                   │
         ┌─────────┼─────────┐
         ▼         ▼         ▼
    ┌──────────┐ ┌──────────┐ ┌──────────┐
    │   Loop   │ │   Trio   │ │Followers │
    │(Consume) │ │(Consume) │ │(Display) │
    └──────────┘ └──────────┘ └──────────┘
```

### Duplicate Prevention Strategies

| System | Upload Identity | Dedup Strategy |
|--------|-----------------|----------------|
| **xDrip+** | `uuid` | Upsert by uuid |
| **AAPS** | `interfaceIDs.nightscoutId` | Check before insert |
| **Loop** | N/A | Typically doesn't upload CGM data |
| **Trio** | `_id` | Direct passthrough |

### Duplicate Risk Scenarios

1. **Multiple Uploaders**: If both xDrip+ and AAPS upload the same CGM reading, duplicates occur unless UUIDs match
2. **Cloud-to-Cloud**: Dexcom Share → xDrip+ → Nightscout and Dexcom Share → Sugarmate → Nightscout
3. **Follower Sync**: Follower mode in xDrip+ downloading and re-uploading

**GAP-ENTRY-004**: No universal deduplication mechanism for entries. Systems rely on timestamp matching or client-generated UUIDs, which may not align across producers.

---

## Gap Summary

| Gap ID | Description | Impact | Systems Affected |
|--------|-------------|--------|------------------|
| **GAP-ENTRY-001** | Triple arrows have no Nightscout equivalent | Granularity lost | AAPS, Trio |
| **GAP-ENTRY-002** | Loop ignores noise level | May use unreliable readings | Loop |
| **GAP-ENTRY-003** | No standardized source taxonomy | Unreliable source identification | All |
| **GAP-ENTRY-004** | No universal dedup for entries | Potential duplicates | All uploaders |
| **GAP-ENTRY-005** | Filtered/unfiltered values iOS-incompatible | iOS systems can't leverage raw data | Loop, Trio |

---

## Suggested Test Specifications

Where protocol is clear and unambiguous, these test specifications can validate conformance.

### SPEC-ENTRY-001: SGV Value Range

**Protocol**: Nightscout `sgv` values must be in mg/dL, range 39-400.

```yaml
test: sgv_value_range
given: An SGV entry is uploaded
then:
  - sgv >= 39
  - sgv <= 400
  - type == "sgv"
```

### SPEC-ENTRY-002: Direction String Values

**Protocol**: Nightscout `direction` must be one of the defined string values.

```yaml
test: direction_valid_values
given: An SGV entry with direction is uploaded
then:
  direction IN [
    "DoubleUp", "SingleUp", "FortyFiveUp", "Flat",
    "FortyFiveDown", "SingleDown", "DoubleDown",
    "NOT COMPUTABLE", "RATE OUT OF RANGE", "NONE"
  ]
```

### SPEC-ENTRY-003: Timestamp Consistency

**Protocol**: `date` (epoch ms) and `dateString` (ISO 8601) must represent the same instant.

```yaml
test: timestamp_consistency
given: An entry with both date and dateString
then:
  - abs(date - parse_iso8601(dateString)) < 1000  # Within 1 second
```

### SPEC-ENTRY-004: Noise Value Range

**Protocol**: When present, `noise` must be 1-4.

```yaml
test: noise_valid_range
given: An entry with noise field
then:
  - noise >= 1
  - noise <= 4
```

### SPEC-ENTRY-005: Entry Type Distinction

**Protocol**: CGM readings use `sgv` field; meter readings use `mbg` field.

```yaml
test: entry_type_fields
given: An entry is created
then:
  - if type == "sgv" then sgv is present
  - if type == "mbg" then mbg is present
  - sgv and mbg are mutually exclusive
```

---

## Requirements (Suggested)

Based on protocol clarity, these requirements are proposed for data preservation and accuracy.

| Req ID | Description | Rationale |
|--------|-------------|-----------|
| **REQ-ENTRY-001** | Glucose values must preserve original mg/dL precision | Round-trip accuracy |
| **REQ-ENTRY-002** | Direction must map to valid Nightscout string | Cross-system display consistency |
| **REQ-ENTRY-003** | Timestamps must be epoch milliseconds UTC | Timezone-agnostic storage |
| **REQ-ENTRY-004** | Source device should be preserved in `device` field | Provenance tracking |
| **REQ-ENTRY-005** | Duplicate entries should be prevented via UUID | Data integrity |

---

## Related Documentation

- [Nightscout Data Model](nightscout-data-model.md) - Overall schema reference
- [Treatments Deep Dive](treatments-deep-dive.md) - Treatment event mappings
- [DeviceStatus Deep Dive](devicestatus-deep-dive.md) - Controller status mappings
- [Terminology Matrix](../../mapping/cross-project/terminology-matrix.md) - Cross-project concept alignment
- [xDrip+ Local Web Server](../../mapping/xdrip-android/local-web-server.md) - Alternative data path

---

## Changelog

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Initial creation covering SGV field mapping, direction arrows, noise, source attribution, stale data, xDrip+ local server, gaps GAP-ENTRY-001 through GAP-ENTRY-005, suggested specs and requirements |
