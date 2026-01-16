# AAPS Data Models

This document describes AAPS's core database entities and their mapping to Nightscout fields.

## Overview

AAPS uses Room (SQLite) for local persistence. Key entities are stored with:
- `InterfaceIDs` for external sync identifiers
- Version tracking for conflict resolution
- Soft deletes (`isValid` flag)

## Common Interfaces

### TraceableDBEntry

All main entities implement:

```kotlin
interface TraceableDBEntry {
    var id: Long
    var version: Int
    var dateCreated: Long
    var isValid: Boolean
    var referenceId: Long?
    var interfaceIDs_backing: InterfaceIDs?
}
```

### DBEntryWithTime

```kotlin
interface DBEntryWithTime {
    var timestamp: Long
    var utcOffset: Long
}
```

### DBEntryWithTimeAndDuration

```kotlin
interface DBEntryWithTimeAndDuration : DBEntryWithTime {
    var duration: Long
}
```

## InterfaceIDs

Stores external sync identifiers:

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/embedments/InterfaceIDs.kt
data class InterfaceIDs(
    var nightscoutSystemId: String? = null,  // NS system ID
    var nightscoutId: String? = null,        // NS _id
    var pumpType: String? = null,            // Pump type identifier
    var pumpSerial: String? = null,          // Pump serial number
    var temporaryId: Long? = null,           // Temporary local ID
    var pumpId: Long? = null,                // Pump event ID
    var startId: Long? = null,               // Start event ID
    var endId: Long? = null                  // End event ID
)
```

## Core Entities

### Bolus

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/Bolus.kt
@Entity(tableName = TABLE_BOLUSES)
data class Bolus(
    @PrimaryKey(autoGenerate = true)
    override var id: Long = 0,
    override var version: Int = 0,
    override var dateCreated: Long = -1,
    override var isValid: Boolean = true,
    override var referenceId: Long? = null,
    @Embedded override var interfaceIDs_backing: InterfaceIDs? = null,
    
    override var timestamp: Long,
    override var utcOffset: Long,
    
    var amount: Double,                      // Insulin units
    var type: Type,                          // NORMAL, SMB, PRIMING
    var notes: String? = null,
    var isBasalInsulin: Boolean = false,
    @Embedded var insulinConfiguration: InsulinConfiguration? = null
) : TraceableDBEntry, DBEntryWithTime

enum class Type { NORMAL, SMB, PRIMING }
```

**Nightscout Mapping:**

| AAPS Field | NS Field | Notes |
|------------|----------|-------|
| `amount` | `insulin` | Units |
| `type=NORMAL` | eventType `Meal Bolus` or `Correction Bolus` | Context-dependent |
| `type=SMB` | eventType `SMB` | Automatic micro-bolus |
| `timestamp` | `date` / `created_at` | Unix ms |
| `interfaceIDs.nightscoutId` | `_id` | MongoDB ID |

### TemporaryBasal

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/TemporaryBasal.kt
@Entity(tableName = TABLE_TEMPORARY_BASALS)
data class TemporaryBasal(
    @PrimaryKey(autoGenerate = true)
    override var id: Long = 0,
    override var version: Int = 0,
    override var dateCreated: Long = -1,
    override var isValid: Boolean = true,
    override var referenceId: Long? = null,
    @Embedded override var interfaceIDs_backing: InterfaceIDs? = null,
    
    override var timestamp: Long,
    override var utcOffset: Long,
    
    var type: Type,
    var isAbsolute: Boolean,
    var rate: Double,                        // Rate (U/hr or %)
    override var duration: Long              // Duration in ms
) : TraceableDBEntry, DBEntryWithTimeAndDuration

enum class Type {
    NORMAL,
    EMULATED_PUMP_SUSPEND,
    PUMP_SUSPEND,
    SUPERBOLUS,
    FAKE_EXTENDED
}
```

**Nightscout Mapping:**

| AAPS Field | NS Field | Notes |
|------------|----------|-------|
| `rate` | `absolute` | Always converted to absolute |
| `duration` | `duration` | MS in AAPS, minutes in NS |
| `isAbsolute=false` | `percent` | Rate as percentage |
| `type=PUMP_SUSPEND` | `absolute=0` | Zero basal |

### Carbs

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/Carbs.kt
@Entity(tableName = TABLE_CARBS)
data class Carbs(
    @PrimaryKey(autoGenerate = true)
    override var id: Long = 0,
    override var version: Int = 0,
    override var dateCreated: Long = -1,
    override var isValid: Boolean = true,
    override var referenceId: Long? = null,
    @Embedded override var interfaceIDs_backing: InterfaceIDs? = null,
    
    override var timestamp: Long,
    override var utcOffset: Long,
    
    var amount: Double,                      // Grams
    var duration: Long = 0,                  // Extended duration (ms)
    var notes: String? = null
) : TraceableDBEntry, DBEntryWithTime
```

**Nightscout Mapping:**

| AAPS Field | NS Field | Notes |
|------------|----------|-------|
| `amount` | `carbs` | Grams |
| `duration` | `duration` | For eCarbs |
| eventType | `Carb Correction` | Default |

### ProfileSwitch

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/ProfileSwitch.kt
@Entity(tableName = TABLE_PROFILE_SWITCHES)
data class ProfileSwitch(
    @PrimaryKey(autoGenerate = true)
    override var id: Long = 0,
    override var version: Int = 0,
    override var dateCreated: Long = -1,
    override var isValid: Boolean = true,
    override var referenceId: Long? = null,
    @Embedded override var interfaceIDs_backing: InterfaceIDs? = null,
    
    override var timestamp: Long,
    override var utcOffset: Long,
    
    var basalBlocks: List<Block>,
    var isfBlocks: List<Block>,
    var icBlocks: List<Block>,
    var targetBlocks: List<TargetBlock>,
    var glucoseUnit: GlucoseUnit,
    var profileName: String,
    var timeshift: Long,                     // Milliseconds
    var percentage: Int,                     // 1-XXX %
    override var duration: Long,             // Milliseconds
    @Embedded var insulinConfiguration: InsulinConfiguration
)
```

**Nightscout Mapping:**

| AAPS Field | NS Field | Notes |
|------------|----------|-------|
| `profileName` | `profile` | Effective name |
| `percentage` | `percentage` | Insulin adjustment |
| `timeshift` | `timeShift` | Schedule shift |
| `duration` | `duration` | MS in AAPS |
| Profile blocks | `profileJson` | Full profile JSON |

### TemporaryTarget

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/TemporaryTarget.kt
@Entity(tableName = TABLE_TEMPORARY_TARGETS)
data class TemporaryTarget(
    @PrimaryKey(autoGenerate = true)
    override var id: Long = 0,
    override var version: Int = 0,
    override var dateCreated: Long = -1,
    override var isValid: Boolean = true,
    override var referenceId: Long? = null,
    @Embedded override var interfaceIDs_backing: InterfaceIDs? = null,
    
    override var timestamp: Long,
    override var utcOffset: Long,
    
    var reason: Reason,
    var highTarget: Double,                  // mg/dL
    var lowTarget: Double,                   // mg/dL
    override var duration: Long              // Milliseconds
) : TraceableDBEntry, DBEntryWithTimeAndDuration

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

| AAPS Field | NS Field | Notes |
|------------|----------|-------|
| `highTarget` | `targetTop` | mg/dL |
| `lowTarget` | `targetBottom` | mg/dL |
| `reason` | `reason` | Free text in NS |
| eventType | `Temporary Target` | Default |

### GlucoseValue

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/GlucoseValue.kt
@Entity(tableName = TABLE_GLUCOSE_VALUES)
data class GlucoseValue(
    @PrimaryKey(autoGenerate = true)
    override var id: Long = 0,
    override var version: Int = 0,
    override var dateCreated: Long = -1,
    override var isValid: Boolean = true,
    override var referenceId: Long? = null,
    @Embedded override var interfaceIDs_backing: InterfaceIDs? = null,
    
    override var timestamp: Long,
    override var utcOffset: Long,
    
    var raw: Double?,
    var value: Double,                       // mg/dL
    var trendArrow: TrendArrow,
    var noise: Double?,
    var sourceSensor: SourceSensor
)

enum class TrendArrow {
    NONE, TRIPLE_UP, DOUBLE_UP, SINGLE_UP,
    FORTY_FIVE_UP, FLAT, FORTY_FIVE_DOWN,
    SINGLE_DOWN, DOUBLE_DOWN, TRIPLE_DOWN
}
```

**Nightscout Mapping:**

| AAPS Field | NS Field | Notes |
|------------|----------|-------|
| `value` | `sgv` | mg/dL |
| `trendArrow` | `direction` | Trend string |
| `noise` | `noise` | Signal quality |
| Collection | `entries` | Not treatments |

### TherapyEvent

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/TherapyEvent.kt
@Entity(tableName = TABLE_THERAPY_EVENTS)
data class TherapyEvent(
    @PrimaryKey(autoGenerate = true)
    override var id: Long = 0,
    override var version: Int = 0,
    override var dateCreated: Long = -1,
    override var isValid: Boolean = true,
    override var referenceId: Long? = null,
    @Embedded override var interfaceIDs_backing: InterfaceIDs? = null,
    
    override var timestamp: Long,
    override var utcOffset: Long,
    
    override var duration: Long = 0,
    var type: Type,
    var note: String? = null,
    var enteredBy: String? = null,
    var glucose: Double? = null,
    var glucoseType: MeterType? = null,
    var glucoseUnit: GlucoseUnit = GlucoseUnit.MGDL
)

enum class Type {
    CANNULA_CHANGE,
    INSULIN_CHANGE,
    PUMP_BATTERY_CHANGE,
    SENSOR_CHANGE,
    SENSOR_STARTED,
    SENSOR_STOPPED,
    FINGER_STICK_BG_VALUE,
    EXERCISE,
    ANNOUNCEMENT,
    NOTE,
    APS_OFFLINE,
    // ...
}
```

**Nightscout Mapping:**

| AAPS Field | NS Field | Notes |
|------------|----------|-------|
| `type` | `eventType` | Therapy event type |
| `note` | `notes` | Free text |
| `glucose` | `glucose` | Optional BG |
| `enteredBy` | `enteredBy` | Actor identity |

### DeviceStatus

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/DeviceStatus.kt
@Entity(tableName = TABLE_DEVICE_STATUS)
data class DeviceStatus(
    @PrimaryKey(autoGenerate = true)
    var id: Long = 0,
    var timestamp: Long,
    var suggested: String? = null,           // JSON
    var enacted: String? = null,             // JSON
    var iobData: String? = null,             // JSON
    var device: String? = null,
    var pump: String? = null,                // JSON
    var uploaderBattery: Int? = null,
    var isCharging: Boolean? = null,
    var configuration: String? = null,       // JSON
    @Embedded var interfaceIDs_backing: InterfaceIDs? = InterfaceIDs()
)
```

**Nightscout Mapping:**

| AAPS Field | NS Field | Notes |
|------------|----------|-------|
| `suggested` | `openaps.suggested` | Algorithm suggestion |
| `enacted` | `openaps.enacted` | What was done |
| `iobData` | `openaps.iob` | IOB calculation |
| `pump` | `pump` | Pump status |
| Collection | `devicestatus` | Not treatments |

### APSResult

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/APSResult.kt
@Entity(tableName = TABLE_APS_RESULTS)
data class APSResult(
    @PrimaryKey(autoGenerate = true)
    var id: Long = 0,
    var algorithm: Algorithm,
    var date: Long,
    var duration: Int = 0,
    var rate: Double = 0.0,
    var smb: Double = 0.0,
    var tempBasalRequested: Boolean = false,
    var bolusRequested: Boolean = false,
    var carbsReq: Int = 0,
    var carbsReqWithin: Int = 0,
    var glucoseStatus: GlucoseStatus? = null,
    var variableSens: Double? = null,
    var json: String? = null,
    @Embedded var interfaceIDs_backing: InterfaceIDs? = InterfaceIDs()
)

enum class Algorithm { AMA, SMB, AUTO_ISF }
```

This is stored locally for debugging/history, not synced to NS directly.

## Supporting Data Classes

### Block (Profile Segments)

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/data/Block.kt
data class Block(
    val duration: Long,                      // Segment duration (ms)
    val amount: Double                       // Value (U/hr, mg/dL/U, or g/U)
)
```

### TargetBlock

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/data/TargetBlock.kt
data class TargetBlock(
    val duration: Long,
    val lowTarget: Double,
    val highTarget: Double
)
```

### InsulinConfiguration

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/embedments/InsulinConfiguration.kt
data class InsulinConfiguration(
    val insulinLabel: String,
    val insulinEndTime: Long,                // DIA in ms
    val insulinPeakTime: Long                // Peak time in ms
)
```

## Table Names

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/TableNames.kt
const val TABLE_BOLUSES = "boluses"
const val TABLE_CARBS = "carbs"
const val TABLE_GLUCOSE_VALUES = "glucoseValues"
const val TABLE_PROFILE_SWITCHES = "profileSwitches"
const val TABLE_EFFECTIVE_PROFILE_SWITCHES = "effectiveProfileSwitches"
const val TABLE_TEMPORARY_BASALS = "temporaryBasals"
const val TABLE_TEMPORARY_TARGETS = "temporaryTargets"
const val TABLE_THERAPY_EVENTS = "therapyEvents"
const val TABLE_DEVICE_STATUS = "deviceStatus"
const val TABLE_APS_RESULTS = "apsResults"
// ... and more
```

## Entity Relationships

```
┌───────────────────────────────────────────────────────────────────┐
│                    AAPS Database Schema                           │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│  TraceableDBEntry (common interface)                              │
│  ├── Bolus                                                        │
│  ├── Carbs                                                        │
│  ├── TemporaryBasal                                               │
│  ├── TemporaryTarget                                              │
│  ├── ProfileSwitch                                                │
│  ├── EffectiveProfileSwitch                                       │
│  ├── GlucoseValue                                                 │
│  ├── TherapyEvent                                                 │
│  ├── ExtendedBolus                                                │
│  ├── OfflineEvent                                                 │
│  └── Food                                                         │
│                                                                   │
│  InterfaceIDs (embedded in all above)                             │
│  ├── nightscoutId                                                 │
│  ├── pumpId + pumpType + pumpSerial                               │
│  └── temporaryId                                                  │
│                                                                   │
│  Standalone Entities                                              │
│  ├── DeviceStatus                                                 │
│  ├── APSResult                                                    │
│  ├── UserEntry (audit log)                                        │
│  └── PreferenceChange                                             │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

## Summary

AAPS's data model is well-structured with:
1. **Clear entity separation** - Each treatment type is a distinct entity
2. **Sync identity tracking** - InterfaceIDs embedded for external references
3. **Soft deletes** - `isValid` flag preserves history
4. **Version tracking** - Conflict resolution support
5. **Full profile embedding** - ProfileSwitch stores complete profile data
