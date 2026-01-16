# AAPS Nightscout SDK Models

This document describes how AAPS represents Nightscout data structures internally via the `core/nssdk/` module. This SDK defines local model classes that map to Nightscout API v3 structures.

## Overview

AAPS maintains a dedicated Nightscout SDK (`core/nssdk/`) with ~59 Kotlin files that define:
- Local data models mirroring Nightscout structures
- API client implementations (sync, callback, Rx variants)
- Exception types for NS API errors

## Base Treatment Interface

All treatment types implement `NSTreatment`:

```kotlin
// aaps:core/nssdk/src/main/kotlin/app/aaps/core/nssdk/localmodel/treatment/NSTreatment.kt
interface NSTreatment {
    var date: Long?                    // Unix timestamp (ms)
    val device: String?                // Device identifier
    val identifier: String?            // Client-side UUID for sync
    val units: NsUnits?                // mg/dL or mmol/L
    val eventType: EventType           // Treatment type enum
    val srvModified: Long?             // Server last modified timestamp
    val srvCreated: Long?              // Server creation timestamp
    var utcOffset: Long?               // UTC offset in ms
    val subject: String?               // Subject identifier
    var isReadOnly: Boolean            // Read-only flag
    val isValid: Boolean               // Valid/deleted flag
    val notes: String?                 // Free-text notes
    val pumpId: Long?                  // Pump event ID
    val endId: Long?                   // End event ID (for ranges)
    val pumpType: String?              // Pump type identifier
    val pumpSerial: String?            // Pump serial number
    var app: String?                   // Application identifier
}
```

### Key Identity Fields

| Field | Purpose | Nightscout Equivalent |
|-------|---------|----------------------|
| `identifier` | Client-generated UUID | Used for updates/deletes |
| `srvCreated` | Server creation timestamp | `_id` creation time |
| `srvModified` | Server modification timestamp | `modifiedAt` |
| `pumpId` + `pumpType` + `pumpSerial` | Pump event composite key | Deduplication |

## Treatment Models

### NSBolus

Represents bolus insulin delivery:

```kotlin
// aaps:core/nssdk/src/main/kotlin/app/aaps/core/nssdk/localmodel/treatment/NSBolus.kt
data class NSBolus(
    // ... NSTreatment fields ...
    val insulin: Double,              // Insulin amount (units)
    val type: BolusType,              // NORMAL, SMB, PRIMING
    val isBasalInsulin: Boolean       // True if basal insulin
) : NSTreatment

enum class BolusType {
    NORMAL,     // Regular bolus
    SMB,        // Super Micro Bolus (automatic)
    PRIMING     // Pump priming (not therapy)
}
```

**Nightscout Mapping:**

| AAPS Field | Nightscout Field | Notes |
|------------|------------------|-------|
| `insulin` | `insulin` | Units of insulin |
| `type=NORMAL` | eventType: `Meal Bolus` or `Correction Bolus` | Based on context |
| `type=SMB` | eventType: `SMB` | Automatic micro-bolus |
| `isBasalInsulin` | N/A | AAPS-specific (Fiasp/Lyumjev basal) |

### NSCarbs

Represents carbohydrate intake:

```kotlin
// aaps:core/nssdk/src/main/kotlin/app/aaps/core/nssdk/localmodel/treatment/NSCarbs.kt
data class NSCarbs(
    // ... NSTreatment fields ...
    val carbs: Double,                // Carbohydrate amount (grams)
    val duration: Long?               // Duration in milliseconds (eCarbs)
) : NSTreatment
```

**Nightscout Mapping:**

| AAPS Field | Nightscout Field | Notes |
|------------|------------------|-------|
| `carbs` | `carbs` | Grams of carbs |
| `duration` | `duration` | For extended carbs (eCarbs) |
| eventType | `Carb Correction` | Default event type |

### NSTemporaryBasal

Represents temporary basal rate changes:

```kotlin
// aaps:core/nssdk/src/main/kotlin/app/aaps/core/nssdk/localmodel/treatment/NSTemporaryBasal.kt
data class NSTemporaryBasal(
    // ... NSTreatment fields ...
    val duration: Long,               // Duration in milliseconds
    val rate: Double,                 // Absolute rate (U/hr) when sending
    val isAbsolute: Boolean,          // True if absolute rate
    val type: Type,                   // Temp basal type
    val percent: Double? = null,      // Percentage (rate - 100)
    val absolute: Double? = null,     // Absolute rate (redundant)
    var extendedEmulated: NSExtendedBolus? = null  // For pumps that emulate
) : NSTreatment

enum class Type {
    NORMAL,                           // Standard temp basal
    EMULATED_PUMP_SUSPEND,            // Emulated via 0% basal
    PUMP_SUSPEND,                     // Pump suspend
    SUPERBOLUS,                       // Superbolus temp
    FAKE_EXTENDED                     // Memory only (extended bolus emulation)
}
```

**Nightscout Mapping:**

| AAPS Field | Nightscout Field | Notes |
|------------|------------------|-------|
| `rate` | `absolute` | Always converted to absolute |
| `duration` | `duration` | Milliseconds in AAPS, minutes in NS |
| `percent` | `percent` | Optional, (rate - 100) |
| eventType | `Temp Basal` | Default |

### NSProfileSwitch

Represents profile changes with optional modifiers:

```kotlin
// aaps:core/nssdk/src/main/kotlin/app/aaps/core/nssdk/localmodel/treatment/NSProfileSwitch.kt
data class NSProfileSwitch(
    // ... NSTreatment fields ...
    val profileJson: JSONObject?,     // Full profile data
    val profile: String,              // Profile name
    val originalProfileName: String?, // Original name before modification
    val timeShift: Long?,             // Time shift in ms
    val percentage: Int?,             // Insulin percentage (100 = normal)
    val duration: Long?,              // Duration in ms (0 = permanent)
    val originalDuration: Long?       // Original duration before modification
) : NSTreatment
```

**Critical Semantic Gap (GAP-002):**

AAPS `ProfileSwitch` can represent three different concepts:

| Scenario | percentage | timeShift | Nightscout Interpretation |
|----------|------------|-----------|--------------------------|
| Complete switch | 100 | 0 | Profile Switch ✓ |
| Insulin adjustment | 110 | 0 | Profile Switch (lost semantics) |
| Schedule shift | 100 | 3600000 | Profile Switch (lost semantics) |

Nightscout treats all as "Profile Switch" events, losing the distinction between a true profile change and an adjustment.

### NSTemporaryTarget

Represents temporary target glucose modifications:

```kotlin
// aaps:core/nssdk/src/main/kotlin/app/aaps/core/nssdk/localmodel/treatment/NSTemporaryTarget.kt
data class NSTemporaryTarget(
    // ... NSTreatment fields ...
    val duration: Long,               // Duration in ms
    val targetBottom: Double,         // Low target (mg/dL)
    val targetTop: Double,            // High target (mg/dL)
    val reason: Reason                // Reason enum
) : NSTreatment

enum class Reason {
    CUSTOM,
    HYPOGLYCEMIA,
    ACTIVITY,
    EATING_SOON,
    AUTOMATION,
    WEAR
}
```

**Nightscout Mapping:**

| AAPS Field | Nightscout Field | Notes |
|------------|------------------|-------|
| `targetBottom` | `targetBottom` | Low target |
| `targetTop` | `targetTop` | High target |
| `reason` | `reason` | Free text in NS |
| eventType | `Temporary Target` | Default |

## Device Status

Represents loop status, pump state, and IOB:

```kotlin
// aaps:core/nssdk/src/main/kotlin/app/aaps/core/nssdk/localmodel/devicestatus/NSDeviceStatus.kt
data class NSDeviceStatus(
    val app: String?,                 // Application identifier
    val identifier: String?,          // Document ID
    val srvCreated: Long?,            // Server creation timestamp
    val srvModified: Long?,           // Server modification timestamp
    val createdAt: String?,           // ISO timestamp
    val date: Long?,                  // Unix timestamp (ms)
    val uploaderBattery: Int?,        // Uploader battery %
    val isCharging: Boolean?,         // Charging status
    val device: String?,              // Device identifier

    val uploader: Uploader?,          // Uploader info
    val pump: Pump?,                  // Pump status
    val openaps: OpenAps?,            // OpenAPS algorithm status
    val configuration: Configuration? // Configuration snapshot
)
```

### OpenAps Substructure

```kotlin
data class OpenAps(
    val suggested: JSONObject?,       // Algorithm suggestion
    val enacted: JSONObject?,         // Enacted changes
    val iob: JSONObject?              // IOB data
)
```

**Nightscout Mapping:**

| AAPS Field | Nightscout Field | Notes |
|------------|------------------|-------|
| `openaps.suggested` | `openaps.suggested` | Algorithm decision |
| `openaps.enacted` | `openaps.enacted` | What was actually done |
| `openaps.iob` | `openaps.iob` | IOB calculation |
| `pump.reservoir` | `pump.reservoir` | Reservoir level |
| `pump.battery` | `pump.battery` | Pump battery |

### Configuration Substructure

```kotlin
data class Configuration(
    val pump: String?,                // Pump driver name
    val version: String?,             // AAPS version
    val insulin: Int?,                // Insulin type resource ID
    val aps: String?,                 // APS algorithm name
    val sensitivity: Int?,            // Sensitivity plugin ID
    val smoothing: String?,           // BG smoothing algorithm
    val insulinConfiguration: JSONObject?,
    val apsConfiguration: JSONObject?,
    val sensitivityConfiguration: JSONObject?,
    val overviewConfiguration: JSONObject?,
    val safetyConfiguration: JSONObject?
)
```

## Event Types

AAPS defines event types matching Nightscout conventions:

```kotlin
// aaps:core/nssdk/src/main/kotlin/app/aaps/core/nssdk/localmodel/treatment/EventType.kt
enum class EventType(val text: String) {
    CANNULA_CHANGE("Site Change"),
    INSULIN_CHANGE("Insulin Change"),
    PUMP_BATTERY_CHANGE("Pump Battery Change"),
    SENSOR_CHANGE("Sensor Change"),
    SENSOR_STARTED("Sensor Start"),
    SENSOR_STOPPED("Sensor Stop"),
    FINGER_STICK_BG_VALUE("BG Check"),
    EXERCISE("Exercise"),
    ANNOUNCEMENT("Announcement"),
    NOTE("Note"),
    APS_OFFLINE("OpenAPS Offline"),
    
    // Treatment types
    CARBS_CORRECTION("Carb Correction"),
    BOLUS_WIZARD("Bolus Wizard"),
    CORRECTION_BOLUS("Correction Bolus"),
    MEAL_BOLUS("Meal Bolus"),
    COMBO_BOLUS("Combo Bolus"),
    TEMPORARY_TARGET("Temporary Target"),
    PROFILE_SWITCH("Profile Switch"),
    TEMPORARY_BASAL("Temp Basal"),
    // ...
}
```

## Glucose Entry

```kotlin
// aaps:core/nssdk/src/main/kotlin/app/aaps/core/nssdk/localmodel/entry/NSSgvV3.kt
data class NSSgvV3(
    val identifier: String?,
    val date: Long?,                  // Unix timestamp (ms)
    val sgv: Int?,                    // Sensor glucose value (mg/dL)
    val direction: Direction?,        // Trend direction
    val noise: Int?,                  // Signal noise level
    val filtered: Double?,            // Filtered value
    val unfiltered: Double?,          // Unfiltered value
    // ... additional fields
)

enum class Direction {
    TRIPLE_UP,                        // Rapidly rising
    DOUBLE_UP,                        // Rising quickly
    SINGLE_UP,                        // Rising
    FORTY_FIVE_UP,                    // Rising slowly
    FLAT,                             // Stable
    FORTY_FIVE_DOWN,                  // Falling slowly
    SINGLE_DOWN,                      // Falling
    DOUBLE_DOWN,                      // Falling quickly
    TRIPLE_DOWN,                      // Rapidly falling
    NONE,                             // No trend
    NOT_COMPUTABLE                    // Cannot compute
}
```

## Units Handling

```kotlin
// aaps:core/nssdk/src/main/kotlin/app/aaps/core/nssdk/localmodel/entry/NsUnits.kt
enum class NsUnits {
    MG_DL,                            // mg/dL
    MMOL_L                            // mmol/L
}
```

The `NSTreatment` interface includes a helper extension:

```kotlin
fun Double.asMgdl() = when (units) {
    NsUnits.MG_DL  -> this
    NsUnits.MMOL_L -> this * 18
    null           -> this
}
```

## Summary

The AAPS NSSDK provides a clean abstraction layer between AAPS internal data and Nightscout API:

1. **Strong Typing** - Enums for event types, directions, units
2. **Identity Management** - `identifier` for client-side, `srvModified` for server sync
3. **Composite Keys** - `pumpId`/`pumpType`/`pumpSerial` for deduplication
4. **Bidirectional Sync** - Models support both upload and download
5. **V3 API** - Designed for Nightscout API v3 with `srvModified` timestamps
