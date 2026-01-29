# CGM Sensor Session Handling Cross-Project Comparison

> **Systems Compared**: xDrip+, DiaBLE, Loop (LoopKit), AAPS  
> **Last Updated**: 2026-01-29

## Overview

CGM sensor sessions involve several lifecycle events:
- **Session Start** - When a new sensor is inserted and activated
- **Warm-up Period** - Initial period where sensor readings are unreliable
- **Calibration Events** - Finger-stick BG values for sensor calibration
- **Session End** - When sensor expires, is stopped, or fails

This document compares how each system handles these events.

---

## Comparison Matrix

### Session States

| State | xDrip+ | DiaBLE | Loop | AAPS |
|-------|--------|--------|------|------|
| Not Started | ✅ | `.notActivated` | `notYetStarted` | Via missing `SENSOR_CHANGE` |
| Warming Up | `CalibrationState.WarmingUp (0x02)` | `.warmingUp` | `warmup` | Calculated from start time |
| Active | Implied | `.active` | `ready` | Implied |
| Expired | ✅ | `.expired` | `sessionExpired` | Via automation trigger age |
| Failed | ✅ | `.failure` | `sessionFailedDuetoUnrecoverableError` | Via missing data |
| Stopped | ✅ | `.shutdown` | `stopped`, `sessionEnded` | `SENSOR_STOPPED` event |

### Warm-up Duration Tracking

| System | Default | Libre | Dexcom G6 | Dexcom G7 | Custom |
|--------|---------|-------|-----------|-----------|--------|
| **xDrip+** | 2 hours | 1 hour | 2 hours | From firmware | Via `SensorDays.java` |
| **DiaBLE** | N/A | From frame data | From transmitter | `warmupLength` field | N/A |
| **Loop** | `warmupPeriod` property | From `SensorState` | `CalibrationState` | `AlgorithmState` | Via `CgmEvent` |
| **AAPS** | N/A | Via source plugin | Via source plugin | Via source plugin | Calculated from events |

### Calibration Support

| System | Factory Cal | Manual Cal | BLE Cal Commands | Cal State Tracking |
|--------|-------------|------------|------------------|-------------------|
| **xDrip+** | ✅ | ✅ | `CalibrateRxMessage.java` | 25+ states in `CalibrationState.java` |
| **DiaBLE** | ✅ (6-factor) | ❌ | `calibrationDataRx (0x33)` | `calibrationsPermitted` flag |
| **Loop** | ✅ | ✅ | `CalibrationDataTx/RxMessage.swift` | `CalibrationState.swift` states |
| **AAPS** | ✅ | ✅ | Via xDrip+ | `FINGER_STICK_BG_VALUE` event |

---

## xDrip+ Implementation

**Source**: `externals/xDrip/`

### Session Management

| File | Purpose |
|------|---------|
| `app/.../models/Sensor.java` | Core sensor model with `started_at`, `stopped_at` |
| `app/.../StartNewSensor.java` | UI to initiate sensor sessions |
| `app/.../StopSensor.java` | UI to stop sensor sessions |
| `app/.../DexSessionKeeper.java` | Active session state persistence |
| `app/.../Ob1G5StateMachine.java` | State machine for G5/G6 lifecycle |

### BLE Protocol Messages

| Message | Opcode | Direction | Purpose |
|---------|--------|-----------|---------|
| `SessionStartTxMessage` | 0x26 | Tx | Request sensor start |
| `SessionStartRxMessage` | 0x27 | Rx | Confirm sensor started |
| `SessionStopRxMessage` | N/A | Rx | Confirm sensor stopped |

### Warm-up Handling

```java
// SensorDays.java - Device-specific warm-up
public static long warmupMs = 2 * HOUR_IN_MS;  // Default Dexcom
// Medtrum: 30 minutes
// Libre: 1 hour
// G7: From VersionRequest2RxMessage.warmupSeconds
```

**Key Methods**:
- `DexSessionKeeper.getWarmupPeriod()` - Returns warm-up duration
- `DexSessionKeeper.warmUpTimeValid()` - Checks if in warm-up window
- `DexSessionKeeper.prettyTime()` - Warm-up countdown display

### Calibration States

```java
// CalibrationState.java - Comprehensive state tracking
public enum CalibrationState {
    WarmingUp(0x02),
    NeedsFirstCalibration(0x04),
    NeedsSecondCalibration(0x05),
    CalibrationConfused1(0x08),
    InsufficientCalibration(0x0e),
    CalibrationSent(0xC3),
    // ... 25+ states total
}
```

---

## DiaBLE Implementation

**Source**: `externals/DiaBLE/`

### Session States

```swift
// Sensor.swift
enum SensorState: String {
    case notActivated = "Not Activated"
    case warmingUp = "Warming Up"
    case active = "Active"
    case expired = "Expired"
    case shutdown = "Shut Down"
    case failure = "Failure"
}
```

### Sensor-Specific Handling

| Sensor | Session Start | Warm-up | Calibration |
|--------|---------------|---------|-------------|
| Dexcom G6 | `sessionStartTx (0x26)` | From transmitter | `calibrateGlucoseTx (0x34)` |
| Dexcom G7 | Via BLE | `warmupLength` from `data[6...7]` | `calibrationBounds (0x32)` |
| Libre 1/2 | Implicit | From frame `[316-317]` | 6-factor `CalibrationInfo` |
| Libre 3 | `activationTime` command | `warmupTime × 5 minutes` | From patch info |

### Calibration Info Structure

```swift
// Glucose.swift - 6-factor calibration for Libre
struct CalibrationInfo {
    var i1: Double  // Factory calibration factor 1
    var i2: Double
    var i3: Double
    var i4: Double
    var i5: Double
    var i6: Double
}
```

### Key Files

| File | Purpose |
|------|---------|
| `Sensor.swift` | Core sensor model with `activationTime`, `age`, `maxLife` |
| `Dexcom.swift` | G6 session handling, calibration |
| `DexcomG7.swift` | G7 warm-up and session length |
| `Libre.swift` | Libre 1/2 age calculation |
| `Libre3.swift` | Libre 3 activation and warm-up |

---

## Loop (LoopKit) Implementation

**Source**: `externals/LoopWorkspace/`

### Session States

**G7** (`G7SensorKit/AlgorithmState.swift`):
```swift
enum AlgorithmState {
    case stopped
    case warmup
    case sessionExpired
    case sessionFailedDuetoUnrecoverableError
    case sessionEnded
}
```

**Libre** (`LibreTransmitter/SensorState.swift`):
```swift
enum SensorState {
    case notYetStarted
    case starting
    case ready
    case expired
    case shutdown
    case failure
}
```

### CgmEvent Model

```swift
// LoopKit/CgmEvent.swift
struct CgmEvent {
    let date: Date
    let deviceIdentifier: String
    let eventType: CgmEventType
    let warmupPeriod: TimeInterval?  // Explicit warm-up tracking
    let expectedLifetime: TimeInterval?
}
```

### Calibration States

```swift
// CGMBLEKit/CalibrationState.swift
enum CalibrationState {
    case warmup
    case needFirstInitialCalibration
    case needSecondInitialCalibration
    case ok
    case calibrationError1
    case calibrationError2
    case needCalibration14
}
```

### Key Files

| File | Purpose |
|------|---------|
| `LoopKit/CgmEventStore.swift` | Session persistence |
| `LoopKit/CgmEvent.swift` | Event model with warm-up |
| `CGMBLEKit/CalibrationState.swift` | Calibration state tracking |
| `G7SensorKit/AlgorithmState.swift` | G7 session states |
| `LibreTransmitter/SensorState.swift` | Libre session states |
| `LibreTransmitter/SensorPairingService.swift` | Session initialization |

---

## AAPS Implementation

**Source**: `externals/AndroidAPS/`

### TherapyEvent Types

```kotlin
// TherapyEvent.kt
enum class Type {
    SENSOR_STARTED,
    SENSOR_STOPPED,
    SENSOR_CHANGE,   // Primary session tracking event
    FINGER_STICK_BG_VALUE,  // Calibration
    // ...
}
```

### Session Tracking

AAPS uses `SENSOR_CHANGE` events to track session starts:

```kotlin
// CgmSourceTransaction.kt
if (sensorInsertionTime != null) {
    val existing = repository.findByTimestamp(
        TherapyEvent.Type.SENSOR_CHANGE, 
        sensorInsertionTime
    )
    // Create new event if not duplicate
}
```

### xDrip+ Integration

```kotlin
// XdripSourcePlugin.kt
fun getSensorStartTime(bundle: Bundle): Long? {
    val sensorStart = bundle.getLong(Intents.EXTRA_SENSOR_STARTED_AT, 0)
    // Validate: not > 1 month old, not in future
    // Prevent duplicates within 5-minute tolerance
}
```

### Sensor Age Automation

```kotlin
// TriggerSensorAge.kt
override fun shouldRun(): Boolean {
    val sensorChangeEvent = repository.getLastTherapyRecordUpToNow(
        TherapyEvent.Type.SENSOR_CHANGE
    )
    val currentAgeHours = (now - sensorChangeEvent.timestamp) / 3600000.0
    return compare.check(currentAgeHours, value)
}
```

### Key Files

| File | Purpose |
|------|---------|
| `database/.../TherapyEvent.kt` | Event types including sensor events |
| `database/.../CgmSourceTransaction.kt` | Session insertion logic |
| `plugins/source/.../XdripSourcePlugin.kt` | xDrip+ session integration |
| `plugins/source/.../DexcomPlugin.kt` | Dexcom calibration |
| `plugins/automation/.../TriggerSensorAge.kt` | Age-based automation |

---

## Cross-System Synchronization

### Nightscout Treatment Events

| Event Type | xDrip+ | Loop | AAPS |
|------------|--------|------|------|
| `Sensor Start` | ✅ | ✅ | ✅ (`sensorInsertionTime`) |
| `Sensor Change` | ✅ | ❓ | ✅ (`SENSOR_CHANGE`) |
| `Sensor Stop` | Limited | ❓ | ✅ (`SENSOR_STOPPED`) |
| `BG Check` (calibration) | ✅ | ✅ | ✅ (`FINGER_STICK_BG_VALUE`) |

### Data Flow

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   xDrip+    │─────▶│  Nightscout │◀─────│    Loop     │
│  (Android)  │      │  treatments │      │    (iOS)    │
└─────────────┘      └──────┬──────┘      └─────────────┘
                            │
                     ┌──────▼──────┐
                     │    AAPS     │
                     │  (Android)  │
                     └─────────────┘
```

### Sync Identity Fields

| System | Session Identity | Calibration Identity |
|--------|------------------|----------------------|
| xDrip+ | `sensor.uuid` | `calibration.uuid` |
| DiaBLE | N/A (no upload) | N/A |
| Loop | `syncIdentifier` | `syncIdentifier` |
| AAPS | `interfaceIDs.nightscoutId` | `interfaceIDs.nightscoutId` |

---

## Gaps Identified

### GAP-SESSION-001: No Standard Sensor Session Event Schema

**Description**: Each system tracks sensor sessions differently. No common Nightscout API schema for session events.

**Impact**: Session start/stop times don't sync reliably between systems.

**Remediation**: Define `Sensor Session Start/Stop` treatment types with standard fields.

### GAP-SESSION-002: Warm-up Period Not Uploaded to Nightscout

**Description**: Warm-up duration varies by sensor but isn't included in Nightscout data.

**Impact**: Downstream consumers can't determine if readings are during warm-up.

**Remediation**: Add `warmupDuration` field to CGM entries or devicestatus.

### GAP-SESSION-003: DiaBLE Has No Session Upload Capability

**Description**: DiaBLE tracks session states internally but doesn't upload session events to Nightscout.

**Impact**: Sensor changes in DiaBLE aren't visible in Nightscout.

**Remediation**: Add session event upload to DiaBLE Nightscout integration.

### GAP-SESSION-004: Calibration State Not Synchronized

**Description**: xDrip+ and Loop track detailed calibration states (25+ states), but this isn't shared via Nightscout.

**Impact**: Other systems can't warn users about calibration issues.

**Remediation**: Consider adding calibration state to devicestatus or entries.

---

## Summary Table

| Aspect | xDrip+ | DiaBLE | Loop | AAPS |
|--------|--------|--------|------|------|
| **Session Tracking** | `Sensor.java` model | `SensorState` enum | `CgmEvent` + state enums | `TherapyEvent` records |
| **Warm-up Source** | `SensorDays.java` | Sensor-specific | `CgmEvent.warmupPeriod` | Calculated from events |
| **Calibration Model** | 25+ state enum | 6-factor struct | State enum + messages | `FINGER_STICK_BG_VALUE` |
| **BLE Protocol** | Full opcode support | Full opcode support | Via CGMBLEKit | Via xDrip+ |
| **NS Sync** | ✅ (treatments) | ❌ (CGM only) | ✅ (treatments) | ✅ (treatments) |
| **Language** | Java | Swift | Swift | Kotlin |

---

## Source File Reference

### xDrip+
- `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/models/Sensor.java`
- `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/services/DexSessionKeeper.java`
- `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/utils/SensorDays.java`
- `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/g5model/CalibrationState.java`

### DiaBLE
- `externals/DiaBLE/DiaBLE/Sensor.swift`
- `externals/DiaBLE/DiaBLE/Dexcom.swift`
- `externals/DiaBLE/DiaBLE/DexcomG7.swift`
- `externals/DiaBLE/DiaBLE/Libre.swift`
- `externals/DiaBLE/DiaBLE/Libre3.swift`

### Loop (LoopKit)
- `externals/LoopWorkspace/LoopKit/LoopKit/GlucoseKit/CgmEvent.swift`
- `externals/LoopWorkspace/LoopKit/LoopKit/GlucoseKit/CgmEventStore.swift`
- `externals/LoopWorkspace/CGMBLEKit/CGMBLEKit/CalibrationState.swift`
- `externals/LoopWorkspace/G7SensorKit/G7SensorKit/AlgorithmState.swift`
- `externals/LoopWorkspace/LibreTransmitter/LibreSensor/SensorContents/SensorState.swift`

### AAPS
- `externals/AndroidAPS/database/impl/src/main/kotlin/app/aaps/database/entities/TherapyEvent.kt`
- `externals/AndroidAPS/database/impl/src/main/kotlin/app/aaps/database/transactions/CgmSourceTransaction.kt`
- `externals/AndroidAPS/plugins/source/src/main/kotlin/app/aaps/plugins/source/XdripSourcePlugin.kt`
- `externals/AndroidAPS/plugins/automation/src/main/kotlin/app/aaps/plugins/automation/triggers/TriggerSensorAge.kt`
