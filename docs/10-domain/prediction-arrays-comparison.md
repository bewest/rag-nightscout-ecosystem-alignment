# Prediction Array Formats Comparison

> **Sources**: Loop, AAPS, Trio, Nightscout  
> **Last Updated**: 2026-01-28

## Overview

This document compares how glucose prediction arrays are generated, structured, and uploaded across AID systems. Predictions are critical for algorithm transparency and debugging.

## Prediction Types

| Type | Full Name | Description |
|------|-----------|-------------|
| **IOB** | Insulin on Board | Glucose impact from active insulin only |
| **COB** | Carbs on Board | Glucose impact including carb absorption |
| **UAM** | Unannounced Meal | Glucose impact detecting unannounced carbs |
| **ZT** | Zero Temp | Glucose trajectory if zero temp basal set |
| **aCOB** | AMA COB | Advanced Meal Assist COB variant |

---

## System Comparison

### Loop: Single Combined Prediction

**Source**: `LoopKit/LoopAlgorithm/LoopAlgorithm.swift`

Loop generates a **single combined prediction curve**, not separate IOB/COB/UAM/ZT arrays:

```swift
struct LoopPrediction: GlucosePrediction {
    var glucose: [PredictedGlucoseValue]  // Single combined curve
    var effects: LoopAlgorithmEffects     // Component effects available
}

struct LoopAlgorithmEffects {
    var insulin: [GlucoseEffect]
    var carbs: [GlucoseEffect]
    var retrospectiveCorrection: [GlucoseEffect]
    var momentum: [GlucoseEffect]
    var insulinCounteraction: [GlucoseEffectVelocity]
}
```

**Key Difference**: Loop combines all effects into one prediction; individual effect curves available internally but not as separate prediction arrays.

### AAPS: Four Prediction Curves (oref)

**Source**: `core/interfaces/src/main/kotlin/app/aaps/core/interfaces/aps/Predictions.kt`

```kotlin
@Serializable
data class Predictions(
    var IOB: List<Int>? = null,   // IOB-only prediction
    var ZT: List<Int>? = null,    // Zero-temp prediction
    var COB: List<Int>? = null,   // COB prediction
    var aCOB: List<Int>? = null,  // AMA COB variant
    var UAM: List<Int>? = null    // UAM prediction
)
```

**Array Format**:
- Values: Integer mg/dL
- Interval: 5 minutes per element
- Start: Current time
- Length: Variable (typically 36-72 elements = 3-6 hours)

**Source Sensor Types** (for graphing):
```kotlin
enum class SourceSensor {
    IOB_PREDICTION,
    COB_PREDICTION,
    UAM_PREDICTION,
    ZT_PREDICTION,
    A_COB_PREDICTION
}
```

### Trio: Four Prediction Curves (oref)

**Source**: `Trio/Sources/Models/Determination.swift`

```swift
struct Predictions: JSON, Equatable {
    let iob: [Int]?   // IOB prediction array
    let zt: [Int]?    // Zero-temp prediction
    let cob: [Int]?   // COB prediction
    let uam: [Int]?   // UAM prediction
}
```

**CoreData Storage**:
```swift
// Forecast entity
type: String?  // "iob", "zt", "cob", "uam"
forecastValues: Set<ForecastValue>?

// ForecastValue entity
index: Int32   // Position in array
value: Int32   // mg/dL value
```

---

## Nightscout devicestatus Format

### OpenAPS/AAPS Format

**Source**: `cgm-remote-monitor/lib/plugins/openaps.js`

```json
{
  "openaps": {
    "suggested": {
      "predBGs": {
        "IOB": [173, 178, 183, 187, 190, ...],
        "COB": [173, 180, 188, 195, ...],
        "UAM": [173, 182, 191, 198, ...],
        "ZT": [173, 170, 165, 160, ...]
      },
      "timestamp": "2026-01-28T12:00:00Z"
    },
    "enacted": {
      "predBGs": { ... }
    }
  }
}
```

### Loop Format

**Source**: `NightscoutServiceKit/Extensions/StoredDosingDecision.swift`

```json
{
  "loop": {
    "predicted": {
      "startDate": "2026-01-28T12:00:00Z",
      "values": [173, 178, 183, 187, 190, ...]
    },
    "iob": { ... },
    "cob": { ... }
  }
}
```

**Key Difference**: Loop uploads single `values` array; AAPS/Trio upload `predBGs` object with named arrays.

---

## Array Specifications

### Resolution and Interval

| System | Interval | Resolution | Units |
|--------|----------|------------|-------|
| Loop | Variable | Decimal | mg/dL or mmol/L |
| AAPS | 5 min | Integer | mg/dL |
| Trio | 5 min | Integer | mg/dL |

### Time Horizon

| System | Default | Maximum |
|--------|---------|---------|
| Loop | ~6 hours | DIA-based |
| AAPS | ~6 hours | Configurable |
| Trio | ~6 hours | Configurable |

### Array Length

| Horizon | 5-min Interval |
|---------|----------------|
| 3 hours | 36 elements |
| 4 hours | 48 elements |
| 5 hours | 60 elements |
| 6 hours | 72 elements |

---

## Nightscout Truncation

**Environment Variable**: `PREDICTIONS_MAX_SIZE`

| Value | Behavior |
|-------|----------|
| Not set | Default truncation |
| `0` | Disable truncation |
| `N` | Truncate to N elements |

**Impact**: Clients cannot detect if truncation occurred.

---

## Cross-System Comparison

### Feature Matrix

| Feature | Loop | AAPS | Trio |
|---------|------|------|------|
| **Separate IOB curve** | ❌ (combined) | ✅ | ✅ |
| **Separate COB curve** | ❌ (combined) | ✅ | ✅ |
| **Separate UAM curve** | ❌ N/A | ✅ | ✅ |
| **Separate ZT curve** | ❌ N/A | ✅ | ✅ |
| **Integer values** | ❌ (decimal) | ✅ | ✅ |
| **5-min interval** | ⚠️ Variable | ✅ | ✅ |
| **Effect curves** | ✅ Internal | ❌ | ❌ |

### Algorithm Comparison

| Aspect | Loop | AAPS/Trio (oref) |
|--------|------|------------------|
| **Prediction Model** | Single combined | 4 separate scenarios |
| **Carb Absorption** | Dynamic (ML-based) | Linear + UAM fallback |
| **Insulin Curve** | Exponential models | Exponential models |
| **Retrospective** | Yes (RC) | Yes (autosens) |

---

## Gaps Identified

### GAP-PRED-002: Loop single prediction incompatible with oref multi-curve display

**Description**: Loop uploads a single combined prediction curve, while Nightscout's OpenAPS plugin expects `predBGs.IOB`, `predBGs.COB`, etc. Loop predictions display differently than AAPS/Trio.

**Impact**:
- Loop predictions don't show IOB/COB/UAM/ZT toggle in Nightscout
- Different visualization between Loop and AAPS/Trio users
- Harder to compare algorithm behavior

**Remediation**: Accept as design difference; document in UI.

### GAP-PRED-003: Prediction interval not standardized

**Description**: AAPS/Trio use fixed 5-minute intervals; Loop may use variable intervals based on algorithm timing.

**Impact**:
- Cannot directly compare prediction accuracy
- Interpolation needed for analysis

**Remediation**: Document interval in devicestatus metadata.

### GAP-PRED-004: No prediction confidence or uncertainty

**Description**: None of the systems upload prediction confidence intervals or uncertainty bounds.

**Impact**:
- Cannot assess prediction reliability
- Algorithm comparison limited to point estimates

**Remediation**: Add optional `confidenceBounds` field to prediction format.

---

## devicestatus Structure Comparison

### Loop
```json
{
  "loop": {
    "predicted": {
      "startDate": "ISO8601",
      "values": [int, ...]
    }
  }
}
```

### AAPS/Trio (oref)
```json
{
  "openaps": {
    "suggested": {
      "predBGs": {
        "IOB": [int, ...],
        "COB": [int, ...],
        "UAM": [int, ...],
        "ZT": [int, ...]
      }
    }
  }
}
```

---

## Source Files Reference

### Loop
- `externals/LoopWorkspace/LoopKit/LoopAlgorithm/LoopAlgorithm.swift`
- `externals/LoopWorkspace/LoopKit/LoopAlgorithm/GlucosePredictionAlgorithm.swift`
- `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/Extensions/StoredDosingDecision.swift`

### AAPS
- `externals/AndroidAPS/core/interfaces/src/main/kotlin/app/aaps/core/interfaces/aps/Predictions.kt`
- `externals/AndroidAPS/implementation/src/main/kotlin/app/aaps/implementation/aps/DetermineBasalResult.kt`
- `externals/AndroidAPS/core/nssdk/src/main/kotlin/app/aaps/core/nssdk/localmodel/devicestatus/NSDeviceStatus.kt`

### Trio
- `externals/Trio/Trio/Sources/Models/Determination.swift`
- `externals/Trio/Trio/Sources/APS/OpenAPS/OpenAPS.swift`
- `externals/Trio/Trio/Sources/Models/NightscoutStatus.swift`

### Nightscout
- `externals/cgm-remote-monitor/lib/plugins/openaps.js`
- `externals/cgm-remote-monitor/lib/report_plugins/loopalyzer.js`

---

## Summary

| Aspect | Loop | AAPS/Trio |
|--------|------|-----------|
| **Prediction Model** | Single combined | 4 separate curves |
| **NS Field** | `loop.predicted.values` | `openaps.suggested.predBGs.*` |
| **Interval** | Variable | 5 minutes |
| **Values** | Decimal | Integer mg/dL |
| **Visualization** | Single line | 4 toggleable lines |

**Key Recommendation**: Nightscout should document both prediction formats in OpenAPI spec with clear field descriptions.
