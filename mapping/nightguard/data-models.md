# Nightguard Data Models

This document describes the data models used by Nightguard to represent Nightscout data locally.

## Overview

Nightguard uses four primary data models:

| Model | Nightscout Source | Purpose |
|-------|-------------------|---------|
| `NightscoutData` | `/api/v2/properties` | Current BG display |
| `BloodSugar` | `/api/v1/entries.json` | Historical readings |
| `DeviceStatusData` | `/api/v1/devicestatus.json` | Pump/Loop status |
| `TemporaryTargetData` | `/api/v1/treatments` | Temp targets |

All models implement `Codable` and `NSSecureCoding` for persistence in UserDefaults.

---

## NightscoutData

**Purpose**: Represents the current blood glucose value and associated metadata for display.

**Source**: `nightguard:nightguard/app/NightscoutData.swift`

### Fields

| Field | Type | Nightscout Source | Description |
|-------|------|-------------------|-------------|
| `sgv` | `String` | `bgnow.last` | Current BG value (mg/dL string) |
| `bgdeltaString` | `String` | `delta.display` | Delta for display (with units) |
| `bgdeltaArrow` | `String` | `direction` | Trend arrow character |
| `bgdelta` | `Float` | `delta.mgdl` | Delta value in mg/dL |
| `time` | `NSNumber` | `bgnow.mills` | Timestamp (epoch milliseconds) |
| `battery` | `String` | `upbat.display` | Uploader battery percentage |
| `iob` | `String` | `iob.display` | Insulin on board (e.g., "2.5U") |
| `cob` | `String` | `cob.display` | Carbs on board (e.g., "15g") |

### Computed Properties

```swift
var hourAndMinutes: String  // "HH:mm" formatted time
var timeString: String      // Minutes ago (e.g., "5min", ">1Hr")
```

### Time Staleness Methods

```swift
func isOlderThanYMinutes() -> Bool  // Uses configured check interval
func isOlderThan1Minute() -> Bool
func isOlderThan5Minutes() -> Bool
func isOlderThanXMinutes(_ minutes: Int) -> Bool
```

### Nightscout API Mapping

From `/api/v2/properties` response:

```json
{
  "bgnow": {
    "last": 120,
    "mills": 1705432800000
  },
  "delta": {
    "display": "+5",
    "mgdl": 5
  },
  "upbat": {
    "display": "85%"
  },
  "iob": {
    "display": "2.5"
  },
  "cob": {
    "display": 15.0
  }
}
```

**Note**: Nightguard appends "U" to IOB and "g" to COB for display.

---

## BloodSugar

**Purpose**: Represents a single historical blood glucose reading for charting.

**Source**: `nightguard:nightguard/domain/BloodSugar.swift`

### Fields

| Field | Type | Nightscout Source | Description |
|-------|------|-------------------|-------------|
| `value` | `Float` | `sgv` or `mbg` | BG value in mg/dL |
| `timestamp` | `Double` | `date` | Epoch milliseconds |
| `isMeteredBloodGlucoseValue` | `Bool` | presence of `mbg` | True for finger stick |
| `arrow` | `String` | `direction` | Trend arrow |

### Computed Properties

```swift
var date: Date  // Converted from timestamp
var isValid: Bool  // value > 10 (filters noise)
```

### Nightscout API Mapping

From `/api/v1/entries.json` response:

```json
[
  {
    "sgv": 120,
    "date": 1705432800000,
    "direction": "Flat"
  },
  {
    "mbg": 115,
    "date": 1705432500000
  }
]
```

### Direction Mapping

Nightguard converts Nightscout direction strings to arrow characters:

| Nightscout Direction | Nightguard Arrow |
|---------------------|------------------|
| `"DoubleUp"` | `"↑↑"` |
| `"SingleUp"` | `"↑"` |
| `"FortyFiveUp"` | `"↗"` |
| `"Flat"` | `"→"` |
| `"FortyFiveDown"` | `"↘"` |
| `"SingleDown"` | `"↓"` |
| `"DoubleDown"` | `"↓↓"` |
| (other) | `"-"` |

---

## DeviceStatusData

**Purpose**: Represents pump and Loop status for users with AID systems.

**Source**: `nightguard:nightguard/app/DeviceStatusData.swift`

### Fields

| Field | Type | Nightscout Source | Description |
|-------|------|-------------------|-------------|
| `activePumpProfile` | `String` | `pump.extended.ActiveProfile` | Active basal profile name |
| `pumpProfileActiveUntil` | `Date` | (not implemented) | Profile switch end time |
| `reservoirUnits` | `Int` | `pump.reservoir` | Insulin reservoir units |
| `temporaryBasalRate` | `String` | calculated | Temp basal as percentage |
| `temporaryBasalRateActiveUntil` | `Date` | calculated | Temp basal end time |

### Nightscout API Mapping

From `/api/v1/devicestatus.json` response (AAPS format):

```json
[
  {
    "pump": {
      "reservoir": 150.5,
      "extended": {
        "ActiveProfile": "Default",
        "BaseBasalRate": 0.8,
        "TempBasalAbsoluteRate": 1.2,
        "TempBasalRemaining": 25
      }
    }
  }
]
```

### Temp Basal Calculation

```swift
temporaryBasalRate = (TempBasalAbsoluteRate / BaseBasalRate) * 100
// Result: "150" (percent string)

temporaryBasalRateActiveUntil = Date() + TempBasalRemaining minutes
```

---

## TemporaryTargetData

**Purpose**: Represents temporary glucose targets set by Loop/AAPS.

**Source**: `nightguard:nightguard/app/TemporaryTargetData.swift`

### Fields

| Field | Type | Nightscout Source | Description |
|-------|------|-------------------|-------------|
| `targetTop` | `Int` | `targetTop` | Upper target (mg/dL) |
| `targetBottom` | `Int` | `targetBottom` | Lower target (mg/dL) |
| `activeUntilDate` | `Date` | calculated from `duration` | When target expires |
| `lastUpdate` | `Date?` | local | Last refresh time |

### Staleness Check

```swift
func isUpToDate() -> Bool {
    guard let lastUpdate = lastUpdate else { return false }
    return Date().timeIntervalSince(lastUpdate) < 300  // 5 minutes
}
```

### Nightscout API Mapping

From `/api/v1/treatments` with `eventType: "Temporary Target"`:

```json
{
  "eventType": "Temporary Target",
  "targetTop": 120,
  "targetBottom": 100,
  "duration": 60,
  "created_at": "2026-01-16T10:00:00.000Z"
}
```

---

## Data Flow Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                    Nightscout Server                             │
├─────────────────────────────────────────────────────────────────┤
│  /api/v2/properties  │  /api/v1/entries  │  /api/v1/devicestatus│
│         │                    │                     │            │
└─────────┼────────────────────┼─────────────────────┼────────────┘
          ▼                    ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    NightscoutService                             │
├─────────────────────────────────────────────────────────────────┤
│  extractApiV2PropertiesData() │ readChartData()  │ readDevice() │
│         │                          │                   │        │
└─────────┼──────────────────────────┼───────────────────┼────────┘
          ▼                          ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌───────────────────────┐
│  NightscoutData │  │  [BloodSugar]   │  │  DeviceStatusData     │
│  - sgv          │  │  - value        │  │  - activePumpProfile  │
│  - bgdelta      │  │  - timestamp    │  │  - temporaryBasalRate │
│  - time         │  │  - arrow        │  │  - reservoirUnits     │
│  - iob/cob      │  │  - isMetered    │  │                       │
└─────────────────┘  └─────────────────┘  └───────────────────────┘
          │                   │                       │
          ▼                   ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                NightscoutDataRepository                          │
│                (UserDefaults Persistence)                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Terminology Mapping

| Alignment Term | Nightguard Term | Notes |
|----------------|-----------------|-------|
| SGV (sensor glucose value) | `sgv` (string in NightscoutData), `value` (float in BloodSugar) | Nightguard uses string for display, float for calculations |
| Delta | `bgdelta` / `bgdeltaString` | Separate numeric and display values |
| Direction | `arrow` / `bgdeltaArrow` | Stored as Unicode arrow character |
| Timestamp | `time` (NSNumber) / `timestamp` (Double) | Both are epoch milliseconds |
| IOB | `iob` | Stored with "U" suffix for display |
| COB | `cob` | Stored with "g" suffix for display |
| Metered BG | `isMeteredBloodGlucoseValue` | From `mbg` field vs `sgv` field |

---

## Code References

| Purpose | Location |
|---------|----------|
| NightscoutData model | `nightguard:nightguard/app/NightscoutData.swift` |
| BloodSugar model | `nightguard:nightguard/domain/BloodSugar.swift` |
| DeviceStatusData model | `nightguard:nightguard/app/DeviceStatusData.swift` |
| TemporaryTargetData model | `nightguard:nightguard/app/TemporaryTargetData.swift` |
| API V2 parsing | `nightguard:nightguard/external/NightscoutService.swift#L467-L538` |
| Direction mapping | `nightguard:nightguard/external/NightscoutService.swift#L145-L165` |
| DeviceStatus parsing | `nightguard:nightguard/external/NightscoutService.swift#L1147-L1268` |
