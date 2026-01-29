# CGM Sensor Session Handling Comparison

> **Sources**: xDrip+, Loop/CGMBLEKit, AndroidAPS  
> **Generated**: 2026-01-29  
> **Focus**: Session start, stop, calibration patterns

---

## Executive Summary

| Aspect | xDrip+ | Loop | AndroidAPS |
|--------|--------|------|------------|
| **Session Model** | Database entity (Sensor.java) | BLE message protocol | Delegates to CGM source |
| **Start Trigger** | Activity UI (StartNewSensor) | TransmitterManager | Via xDrip/BYODA/DexcomApp |
| **Stop Trigger** | Activity UI (StopSensor) | TransmitterManager | Via source app |
| **Calibration Storage** | Calibration entity + algorithms | CalibrationState enum | UserEntry + broadcast |
| **State Machine** | Implicit in Sensor model | Explicit CalibrationState | None (delegates) |

---

## 1. xDrip+ (Android)

### Session Management

**Source**: `app/src/main/java/com/eveningoutpost/dexdrip/models/Sensor.java`

```java
@Table(name = "Sensors")
public class Sensor extends Model {
    @Column(name = "started_at", index = true)
    public long started_at;

    @Column(name = "stopped_at")
    public long stopped_at;

    @Column(name = "latest_battery_level")
    public int latest_battery_level;

    @Column(name = "uuid", index = true)
    public String uuid;

    @Column(name = "sensor_location")
    public String sensor_location;
}
```

**Key Operations**:

| Operation | Method | Description |
|-----------|--------|-------------|
| Start | `Sensor.create(long timestamp)` | Creates new sensor with started_at |
| Stop | `Sensor.stopSensor()` | Sets stopped_at, marks as inactive |
| Current | `Sensor.currentSensor()` | Returns active sensor (stopped_at=0) |
| IsActive | `Sensor.isActive()` | Checks if sensor is running |

### Session Start Flow

**Source**: `app/src/main/java/com/eveningoutpost/dexdrip/StartNewSensor.java`

1. User selects sensor type (Dexcom G5/G6/G7, Libre, etc.)
2. Optional: Enter sensor code for factory calibration
3. Creates Sensor entity with `started_at = now`
4. Coordinates with Ob1G5StateMachine for BLE
5. Broadcasts sensor start event

### Session Stop Flow

**Source**: `app/src/main/java/com/eveningoutpost/dexdrip/StopSensor.java`

1. User confirms stop action
2. Sets `stopped_at = now` on Sensor entity
3. Resets Ob1G5StateMachine state
4. Broadcasts sensor stop event

### Calibration System

**Source**: `app/src/main/java/com/eveningoutpost/dexdrip/models/Calibration.java`

```java
@Table(name = "Calibrations")
public class Calibration extends Model {
    @Column(name = "timestamp", index = true)
    public long timestamp;

    @Column(name = "sensor_age_at_time_of_estimation")
    public double sensor_age_at_time_of_estimation;

    @Column(name = "bg")
    public double bg;  // User-entered blood glucose

    @Column(name = "raw_value")
    public double raw_value;

    @Column(name = "slope")
    public double slope;

    @Column(name = "intercept")
    public double intercept;
}
```

**Pluggable Algorithms**:
- XDripOriginal - Classic dual-point
- Native - Sensor's built-in
- Datricsae - Multi-point alternative
- FixedSlope - Testing
- LastSevenUnweighted - Averaging

---

## 2. Loop/CGMBLEKit (iOS)

### Session Management

Loop uses a BLE message-based protocol for Dexcom transmitters.

**Session Start Messages**:

| File | Purpose |
|------|---------|
| `SessionStartTxMessage.swift` | Transmit start command |
| `SessionStartRxMessage.swift` | Receive start confirmation |

**SessionStartRxMessage Structure**:

```swift
struct SessionStartRxMessage {
    let status: UInt8
    let received: UInt8
    let requestedStartTime: Date
    let sessionStartTime: Date?
    let transmitterTime: UInt32
}
```

**Session Stop Messages**:

| File | Purpose |
|------|---------|
| `SessionStopTxMessage.swift` | Transmit stop command |
| `SessionStopRxMessage.swift` | Receive stop confirmation |

### Calibration State Machine

**Source**: `CGMBLEKit/CalibrationState.swift`

```swift
enum CalibrationState: UInt8 {
    case stopped = 1
    case warmup = 2
    case needFirstInitialCalibration = 4
    case needSecondInitialCalibration = 5
    case ok = 6
    case needCalibration = 7
    
    // Error states
    case calibrationError1 = 9
    case calibrationError2 = 10
    
    // Sensor states
    case sensorFailedDueToCountsAberration = 18
    case sensorFailed = 19
    
    // Session states
    case sessionFailedDueToUnrecoverableError = 21
    case sessionStopped = 22
    case sensorFailedDueToResistanceBaseline = 23
    case sensorFailedDueToPoorSignal = 24
}
```

**State Transitions**:

```
stopped → warmup → needFirstInitialCalibration → needSecondInitialCalibration → ok
                                                                                  ↓
                                                                          needCalibration
```

### Calibration Data

**Source**: `CGMBLEKit/Calibration.swift`

```swift
struct Calibration {
    let glucose: Int  // mg/dL
    let date: Date
}
```

---

## 3. AndroidAPS

### Session Management

AndroidAPS **delegates** session management to the CGM source app (xDrip+, BYODA, Dexcom app).

**CGM Sources** (`plugins/source/`):

| Source | Session Control |
|--------|-----------------|
| xDripPlugin | Via xDrip+ broadcasts |
| DexcomPlugin | Via Dexcom app |
| GlimpPlugin | Via Glimp app |
| PocTechPlugin | Via PocTech app |
| TomatoPlugin | Via Tomato app |

### Calibration Handling

**Source**: `ui/src/main/kotlin/app/aaps/ui/dialogs/CalibrationDialog.kt`

```kotlin
class CalibrationDialog : DialogFragmentWithDate() {
    
    override fun submit(): Boolean {
        val units = profileUtil.units
        val bg = binding.bg.value
        
        // Validate input
        if (bg > 0) {
            // Send calibration via xDrip broadcast
            xDripBroadcast.sendCalibration(bg, units)
            
            // Log to user entry
            uel.log(UserEntry.Action.CALIBRATION, ...)
        }
        return true
    }
}
```

**Broadcast Integration**:

```kotlin
// XDripBroadcast.kt
fun sendCalibration(bg: Double, units: GlucoseUnit) {
    val intent = Intent(Intents.ACTION_CALIBRATION)
    intent.putExtra("glucose", bg)
    intent.putExtra("units", units.asText)
    context.sendBroadcast(intent)
}
```

---

## 4. Session Lifecycle Comparison

### Start Session

| System | Trigger | Storage | Broadcast |
|--------|---------|---------|-----------|
| xDrip+ | UI Activity | Sensor entity | `ACTION_SENSOR_START` |
| Loop | TransmitterManager | In-memory | CGMManager delegate |
| AAPS | External app | N/A (delegates) | Receives from source |

### Stop Session

| System | Trigger | Cleanup | Broadcast |
|--------|---------|---------|-----------|
| xDrip+ | UI Activity | Sets stopped_at | `ACTION_SENSOR_STOP` |
| Loop | TransmitterManager | Clears state | CGMManager delegate |
| AAPS | External app | N/A | Receives from source |

### Calibration

| System | Entry Point | Storage | Algorithms |
|--------|-------------|---------|------------|
| xDrip+ | UI + Auto | Calibration entity | 5 pluggable |
| Loop | CGM Manager | In-memory | Native only |
| AAPS | CalibrationDialog | UserEntry log | Via xDrip+ |

---

## 5. Nightscout Integration

### Calibration Upload

| System | eventType | Fields |
|--------|-----------|--------|
| xDrip+ | `BG Check` or `Sensor Start` | `glucose`, `glucoseType`, `units` |
| Loop | `mbg` entry | `mbg` value (mg/dL) |
| AAPS | `BG Check` | Via xDrip+ broadcast |

### Sensor Events

| Event | xDrip+ | Loop | AAPS |
|-------|--------|------|------|
| Start | `Sensor Start` treatment | Not uploaded | N/A |
| Stop | `Sensor Stop` treatment | Not uploaded | N/A |
| Change | `Sensor Change` treatment | Not uploaded | `Sensor Change` |

---

## 6. Interoperability Gaps

### GAP-SESSION-001: Session Events Not Standardized

**Description**: Only xDrip+ consistently uploads sensor start/stop events to Nightscout. Loop and AAPS do not upload session lifecycle events.

**Impact**:
- Cannot track sensor history from Nightscout alone
- Analytics cannot correlate readings with sensor age
- No cross-system session awareness

**Remediation**: Define standard `Sensor Start`/`Sensor Stop` treatment types with required fields.

### GAP-SESSION-002: Calibration State Not Exposed

**Description**: Loop has a rich 17-state calibration state machine, but this state is not exposed to Nightscout or other systems.

**Impact**:
- Cannot diagnose calibration issues remotely
- No visibility into warmup progress
- Analytics cannot distinguish calibration errors from sensor failures

**Remediation**: Add `calibrationState` field to devicestatus.

### GAP-SESSION-003: Pluggable Calibration Algorithms Unique to xDrip+

**Description**: Only xDrip+ supports user-selectable calibration algorithms. Loop and AAPS use native sensor calibration only.

**Impact**:
- Users switching from xDrip+ may lose preferred algorithm
- No cross-system calibration comparison possible
- Algorithm choice not preserved in Nightscout

**Remediation**: Document as intentional difference; xDrip+'s flexibility is a feature.

---

## 7. Code References

| System | File | Purpose |
|--------|------|---------|
| xDrip+ | `models/Sensor.java` | Session entity |
| xDrip+ | `models/Calibration.java` | Calibration entity |
| xDrip+ | `StartNewSensor.java` | Session start UI |
| xDrip+ | `StopSensor.java` | Session stop UI |
| Loop | `CalibrationState.swift` | 17-state machine |
| Loop | `SessionStartRxMessage.swift` | BLE session protocol |
| Loop | `Calibration.swift` | Calibration data |
| AAPS | `CalibrationDialog.kt` | Calibration UI |
| AAPS | `XDripBroadcast.kt` | xDrip+ integration |

---

## Cross-References

- [xDrip+ Calibration Algorithms](../../mapping/xdrip-android/calibrations.md) - 431 lines
- [xDrip+ Nightscout Sync](../../mapping/xdrip-android/nightscout-sync.md) - 506 lines
- [CGM Data Sources Deep Dive](cgm-data-sources-deep-dive.md) - Multi-source analysis
- [Terminology Matrix - CGM Section](../../mapping/cross-project/terminology-matrix.md) - Term mappings
