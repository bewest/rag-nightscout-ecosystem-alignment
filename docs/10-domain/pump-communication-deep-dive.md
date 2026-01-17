# Pump Communication Protocols Deep Dive

This document provides a comprehensive analysis of how AID (Automated Insulin Delivery) controllers communicate with insulin pumps across Loop, Trio, and AAPS ecosystems.

## Executive Summary

AID controllers must reliably communicate with insulin pumps to deliver insulin safely. This involves:
- **Transport layer**: Bluetooth Low Energy (BLE) or Radio Frequency (RF) via hardware bridges
- **Protocol layer**: Proprietary command/response protocols per pump manufacturer
- **Abstraction layer**: Platform-specific interfaces (PumpManager for iOS, Pump for Android)
- **Safety layer**: Constraints, acknowledgments, and state reconciliation

---

## 1. Protocol Taxonomy: BLE vs RF

### Communication Technologies by Pump

| Pump | Transport | Frequency | Bridge Required | Protocol |
|------|-----------|-----------|-----------------|----------|
| **Omnipod DASH** | BLE Direct | 2.4 GHz | No | AES-CCM encrypted |
| **Omnipod Eros** | RF | 433.91 MHz | RileyLink | Unencrypted RF |
| **Medtronic 500/700 series** | RF | 916.5 MHz (US) | RileyLink | Unencrypted RF |
| **Dana RS/i** | BLE Direct | 2.4 GHz | No | Custom encrypted |
| **Dana R/Rv2** | BLE Direct | 2.4 GHz | No | Custom encrypted |
| **Accu-Chek Combo** | RF | 869 MHz | ruffy (Bluetooth proxy) | Custom |
| **Accu-Chek Insight** | BLE Direct | 2.4 GHz | No | SightParser |
| **Diaconn G8** | BLE Direct | 2.4 GHz | No | Custom |
| **Medtrum Nano/Touch** | BLE Direct | 2.4 GHz | No | Custom |
| **EOPatch** | BLE Direct | 2.4 GHz | No | Custom |
| **Equil** | BLE Direct | 2.4 GHz | No | Custom |

### RileyLink Hardware Bridge

RileyLink is a Bluetooth-to-RF bridge device required for:
- **Omnipod Eros**: 433.91 MHz OOK modulation
- **Medtronic pumps**: 916.5 MHz (US) or 868 MHz (EU) FSK modulation

**Source**: `LoopWorkspace/MinimedKit/MinimedKit/PumpManager/RileyLinkDevice.swift`

The RileyLink:
1. Connects to phone via Bluetooth LE
2. Translates commands to RF packets
3. Handles RF timing and retries
4. Reports firmware version and battery status

---

## 2. Controller Abstraction Layers

### Loop/Trio: PumpManager Protocol (Swift)

**Source**: `LoopWorkspace/LoopKit/LoopKit/DeviceManager/PumpManager.swift`

The `PumpManager` protocol defines ~25+ methods and properties for pump communication:

```swift
public protocol PumpManager: DeviceManager {
    // Precision constraints
    var supportedBasalRates: [Double] { get }
    var supportedBolusVolumes: [Double] { get }
    var maximumBasalScheduleEntryCount: Int { get }
    func roundToSupportedBasalRate(unitsPerHour: Double) -> Double
    func roundToSupportedBolusVolume(units: Double) -> Double
    
    // Status
    var status: PumpManagerStatus { get }
    var lastSync: Date? { get }
    var pumpReservoirCapacity: Double { get }
    
    // Commands
    func enactBolus(units: Double, activationType: BolusActivationType, 
                    completion: @escaping (_ error: PumpManagerError?) -> Void)
    func cancelBolus(completion: @escaping (_ result: PumpManagerResult<DoseEntry?>) -> Void)
    func enactTempBasal(unitsPerHour: Double, for duration: TimeInterval, 
                        completion: @escaping (_ error: PumpManagerError?) -> Void)
    func suspendDelivery(completion: @escaping (_ error: Error?) -> Void)
    func resumeDelivery(completion: @escaping (_ error: Error?) -> Void)
    
    // Profile sync
    func syncBasalRateSchedule(items: [RepeatingScheduleValue<Double>], 
                               completion: @escaping (_ result: Result<BasalRateSchedule, Error>) -> Void)
    func syncDeliveryLimits(limits: DeliveryLimits, 
                            completion: @escaping (_ result: Result<DeliveryLimits, Error>) -> Void)
    
    // State management
    func ensureCurrentPumpData(completion: ((_ lastSync: Date?) -> Void)?)
    func setMustProvideBLEHeartbeat(_ mustProvideBLEHeartbeat: Bool)
}
```

**Key Design Patterns**:
- **Async completion handlers**: All commands are async with completion closures
- **Result types**: `PumpManagerResult<T>` for success/failure
- **Observer pattern**: `PumpManagerStatusObserver` for status updates
- **Delegate pattern**: `PumpManagerDelegate` for event callbacks

### PumpManagerStatus States

**Source**: `LoopWorkspace/LoopKit/LoopKit/DeviceManager/PumpManagerStatus.swift`

```swift
public struct PumpManagerStatus {
    public enum BasalDeliveryState {
        case active(_ at: Date)
        case initiatingTempBasal
        case tempBasal(_ dose: DoseEntry)
        case cancelingTempBasal
        case suspending
        case suspended(_ at: Date)
        case resuming
    }
    
    public enum BolusState {
        case noBolus
        case initiating
        case inProgress(_ dose: DoseEntry)
        case canceling
    }
    
    public var deliveryIsUncertain: Bool  // Critical for safety
}
```

The `deliveryIsUncertain` flag is critical for safety - when true, the controller cannot trust delivery state and must verify with pump.

### AAPS: Pump Interface (Kotlin)

**Source**: `AndroidAPS/core/interfaces/src/main/kotlin/app/aaps/core/interfaces/pump/Pump.kt`

The `Pump` interface defines ~50+ methods for pump communication:

```kotlin
interface Pump {
    // Connection state
    fun isInitialized(): Boolean
    fun isSuspended(): Boolean
    fun isBusy(): Boolean
    fun isConnected(): Boolean
    fun isConnecting(): Boolean
    fun isHandshakeInProgress(): Boolean
    
    // Connection management
    fun connect(reason: String)
    fun disconnect(reason: String)
    fun stopConnecting()
    fun waitForDisconnectionInSeconds(): Int = 5
    
    // Status
    val lastDataTime: Long
    val lastBolusTime: Long?
    val lastBolusAmount: Double?
    val baseBasalRate: Double
    val reservoirLevel: Double
    val batteryLevel: Int?
    
    // Commands
    fun deliverTreatment(detailedBolusInfo: DetailedBolusInfo): PumpEnactResult
    fun stopBolusDelivering()
    fun setTempBasalAbsolute(absoluteRate: Double, durationInMinutes: Int, 
                             profile: Profile, enforceNew: Boolean, 
                             tbrType: PumpSync.TemporaryBasalType): PumpEnactResult
    fun setTempBasalPercent(percent: Int, durationInMinutes: Int, 
                            profile: Profile, enforceNew: Boolean,
                            tbrType: PumpSync.TemporaryBasalType): PumpEnactResult
    fun cancelTempBasal(enforceNew: Boolean): PumpEnactResult
    fun setExtendedBolus(insulin: Double, durationInMinutes: Int): PumpEnactResult
    fun cancelExtendedBolus(): PumpEnactResult
    
    // Profile
    fun setNewBasalProfile(profile: Profile): PumpEnactResult
    fun isThisProfileSet(profile: Profile): Boolean
    
    // Pump metadata
    fun manufacturer(): ManufacturerType
    fun model(): PumpType
    fun serialNumber(): String
    val pumpDescription: PumpDescription
    
    // Special capabilities
    val isFakingTempsByExtendedBoluses: Boolean
    fun canHandleDST(): Boolean
    fun loadTDDs(): PumpEnactResult
}
```

**Key Design Patterns**:
- **Synchronous interface, async execution**: Commands return `PumpEnactResult` but internally use async pump command queues
- **Explicit connection management**: `connect()`, `disconnect()`, `stopConnecting()`
- **Handshake state**: `isHandshakeInProgress()` for connection establishment
- **Extended bolus support**: Native in AAPS, not in Loop

### PumpSync: Data Synchronization (AAPS)

**Source**: `AndroidAPS/core/interfaces/src/main/kotlin/app/aaps/core/interfaces/pump/PumpSync.kt`

AAPS uses a separate `PumpSync` interface for pump → database synchronization:

```kotlin
interface PumpSync {
    fun connectNewPump(endRunning: Boolean = true)
    fun verifyPumpIdentification(type: PumpType, serialNumber: String): Boolean
    fun expectedPumpState(): PumpState
    
    // Bolus sync with temporary ID (for pumps without immediate ID)
    fun addBolusWithTempId(timestamp: Long, amount: Double, temporaryId: Long, 
                           type: BS.Type, pumpType: PumpType, pumpSerial: String): Boolean
    fun syncBolusWithTempId(timestamp: Long, amount: Double, temporaryId: Long, 
                            type: BS.Type?, pumpId: Long?, pumpType: PumpType, 
                            pumpSerial: String): Boolean
    
    // Bolus sync with pump ID (for pumps with reliable history)
    fun syncBolusWithPumpId(timestamp: Long, amount: Double, type: BS.Type?, 
                            pumpId: Long, pumpType: PumpType, pumpSerial: String): Boolean
}
```

This two-phase sync pattern handles:
- Pumps with immediate IDs (Dana RS history)
- Pumps without immediate IDs (start bolus → wait → read ID from history)

---

## 3. Interface Comparison: Loop vs AAPS

| Aspect | Loop PumpManager | AAPS Pump |
|--------|------------------|-----------|
| **Language** | Swift | Kotlin |
| **Return type** | Async completion handler | Sync PumpEnactResult |
| **Connection mgmt** | Implicit (delegate callbacks) | Explicit `connect()`/`disconnect()` |
| **Bolus API** | `enactBolus(units, activationType)` | `deliverTreatment(DetailedBolusInfo)` |
| **TBR unit** | Duration as `TimeInterval` (seconds) | Duration in minutes |
| **Extended bolus** | Not supported | Native `setExtendedBolus()` |
| **TBR types** | Absolute U/hr only | Absolute or Percent |
| **Uncertainty flag** | `deliveryIsUncertain` | Implicit in result |
| **History sync** | `hasNewPumpEvents` delegate | `PumpSync` interface |
| **DST handling** | `didAdjustPumpClockBy` delegate | `canHandleDST()` + `timezoneOrDSTChanged()` |

---

## 4. Pump Precision Constraints

### Bolus Step Sizes

| Pump | Bolus Step (U) | Min Bolus | Max Bolus |
|------|----------------|-----------|-----------|
| Omnipod DASH/Eros | 0.05 | 0.05 | 30.0 |
| Dana RS/i | 0.05 | 0.05 | Configurable |
| Medtronic 523/723 | 0.05 | 0.05 | 25.0 |
| Accu-Chek Insight | 0.01-0.05 (variable) | 0.02 | 25.0 |
| Diaconn G8 | 0.01 | 0.05 | 15.0 |

### Basal Rate Constraints

| Pump | Basal Step (U/hr) | Min Basal | Max Basal | Max Segments/Day |
|------|-------------------|-----------|-----------|------------------|
| Omnipod DASH/Eros | 0.05 | 0.05 | 30.0 | 24 |
| Dana RS | 0.01 | 0.04 | Configurable | 24 or 48 |
| Medtronic 523/723 | 0.025 | 0.025 | 35.0 | 48 |
| Accu-Chek Insight | 0.01 (variable) | 0.02 | 25.0 | 24 |

### Temp Basal Constraints

| Pump | TBR Type | Duration Step | Max Duration | Max Rate |
|------|----------|---------------|--------------|----------|
| Omnipod DASH/Eros | Absolute | 30 min | 12 hrs | 30 U/hr |
| Dana RS | Percent | 15/30/60 min | 24 hrs | 200% |
| Medtronic | Absolute | 30 min | 24 hrs | 35 U/hr |

---

## 5. BLE Protocol Details

### Omnipod DASH BLE Protocol

**Source**: `LoopWorkspace/OmniBLE/OmniBLE/Bluetooth/`

#### BLE Service UUIDs
```swift
enum OmnipodServiceUUID: String {
    case advertisement = "00004024-0000-1000-8000-00805f9b34fb"
    case service = "1A7E4024-E3ED-4464-8B7E-751E03D0DC5F"
}

enum OmnipodCharacteristicUUID: String {
    case command = "1A7E2441-E3ED-4464-8B7E-751E03D0DC5F"
    case data = "1A7E2442-E3ED-4464-8B7E-751E03D0DC5F"
}
```

#### Command Flow Protocol
```swift
enum PodCommand: UInt8 {
    case RTS = 0x00     // Ready To Send
    case CTS = 0x01     // Clear To Send
    case NACK = 0x02    // Negative Acknowledgment
    case ABORT = 0x03   // Abort transaction
    case SUCCESS = 0x04 // Command succeeded
    case FAIL = 0x05    // Command failed
    case HELLO = 0x06   // Initial handshake
    case INCORRECT = 0x09 // Invalid command
}
```

#### Encryption (AES-CCM)
**Source**: `OmniBLE/Bluetooth/EnDecrypt/EnDecrypt.swift`

```swift
class EnDecrypt {
    private let MAC_SIZE = 8  // 8-byte authentication tag
    
    func encrypt(_ msg: MessagePacket, _ nonceSeq: Int) throws -> MessagePacket {
        let n = nonce.toData(sqn: nonceSeq, podReceiving: true)
        let ccm = CCM(iv: n.bytes, tagLength: MAC_SIZE, 
                      messageLength: payload.count, 
                      additionalAuthenticatedData: header.bytes)
        let aes = try AES(key: ck.bytes, blockMode: ccm, padding: .noPadding)
        // ... encrypt payload
    }
}
```

**Key Exchange**: Uses LTK (Long Term Key) exchange during pairing (`LTKExchanger.swift`)

### Dana RS BLE Protocol

**Source**: `AndroidAPS/pump/danars/`

#### Packet Structure
```kotlin
open class DanaRSPacket {
    var type = BleEncryption.DANAR_PACKET__TYPE_RESPONSE
    var opCode = 0
    
    val command: Int
        get() = (type and 0xFF shl 8) + (opCode and 0xFF)
    
    companion object {
        private const val TYPE_START = 0
        private const val OPCODE_START = 1
        const val DATA_START = 2
    }
}
```

#### Encryption
Dana RS uses custom BLE encryption (`BleEncryption.kt`):
- Pairing PIN verification
- Encrypted command/response packets
- Hardware-tied encryption keys

---

## 6. Command Acknowledgment Patterns

### Loop/Trio Pattern (Async Completion)

**Source**: `LoopWorkspace/Loop/Loop/Managers/DoseEnactor.swift`

```swift
class DoseEnactor {
    func enact(recommendation: AutomaticDoseRecommendation, 
               with pumpManager: PumpManager, 
               completion: @escaping (PumpManagerError?) -> Void) {
        
        dosingQueue.async {
            let doseDispatchGroup = DispatchGroup()
            var tempBasalError: PumpManagerError? = nil
            var bolusError: PumpManagerError? = nil

            // 1. Set temp basal first (if needed)
            if let basalAdjustment = recommendation.basalAdjustment {
                doseDispatchGroup.enter()
                pumpManager.enactTempBasal(
                    unitsPerHour: basalAdjustment.unitsPerHour, 
                    for: basalAdjustment.duration
                ) { error in
                    tempBasalError = error
                    doseDispatchGroup.leave()
                }
            }
            doseDispatchGroup.wait()
            
            // 2. Only proceed to bolus if TBR succeeded
            guard tempBasalError == nil else {
                completion(tempBasalError)
                return
            }
            
            // 3. Enact bolus (SMB)
            if let bolusUnits = recommendation.bolusUnits, bolusUnits > 0 {
                doseDispatchGroup.enter()
                pumpManager.enactBolus(units: bolusUnits, activationType: .automatic) { error in
                    bolusError = error
                    doseDispatchGroup.leave()
                }
            }
            doseDispatchGroup.wait()
            completion(bolusError)
        }
    }
}
```

**Pattern**: Sequential TBR → Bolus with wait between, DispatchGroup for synchronization.

### AAPS Pattern (Sync with Retry)

**Source**: `AndroidAPS/pump/danars/src/main/kotlin/app/aaps/pump/danars/DanaRSPlugin.kt`

```kotlin
@Synchronized
override fun deliverTreatment(detailedBolusInfo: DetailedBolusInfo): PumpEnactResult {
    // Apply constraints
    detailedBolusInfo.insulin = constraintChecker
        .applyBolusConstraints(ConstraintObject(detailedBolusInfo.insulin, aapsLogger))
        .value()
    
    // Calculate delivery time (12/30/60 sec per U based on settings)
    val speed = when (preferences.get(DanaIntKey.BolusSpeed)) {
        0 -> 12; 1 -> 30; 2 -> 60
        else -> 12
    }
    detailedBolusInfo.timestamp = dateUtil.now() + (speed * detailedBolusInfo.insulin * 1000).toLong()
    
    // Store for later reconciliation
    detailedBolusInfoStorage.add(detailedBolusInfo)
    
    // Execute bolus command
    val connectionOK = danaRSService?.bolus(detailedBolusInfo) == true
    
    // Verify delivery
    val result = pumpEnactResultProvider.get()
    result.success = connectionOK && 
        (abs(detailedBolusInfo.insulin - BolusProgressData.delivered) < pumpDescription.bolusStep 
         || danaPump.bolusStopped)
    result.bolusDelivered = BolusProgressData.delivered
    
    // Handle error codes
    if (!result.success) {
        val error = when (danaPump.bolusStartErrorCode) {
            0x10 -> "Max bolus violation"
            0x20 -> "Command error"
            0x40 -> "Speed error"
            0x80 -> "Insulin limit violation"
            else -> danaPump.bolusStartErrorCode.toString()
        }
        result.comment = "Bolus error: $error"
    }
    return result
}
```

### Omnipod DASH Retry Pattern

**Source**: `AndroidAPS/pump/omnipod/dash/.../OmnipodDashPumpPlugin.kt`

```kotlin
companion object {
    private const val BOLUS_RETRY_INTERVAL_MS = 2000.toLong()
    private const val BOLUS_RETRIES = 5
}

private fun waitForBolusDeliveryToComplete(requestedBolusAmount: Double): Single<Double> {
    // Wait for estimated delivery time
    val estimatedDeliveryTimeSeconds = estimateBolusDeliverySeconds(requestedBolusAmount)
    var waited = 0
    while (waited < estimatedDeliveryTimeSeconds && !bolusCanceled) {
        waited += 1
        Thread.sleep(1000)
        // Update progress dialog
    }
    
    // Retry status check up to 5 times
    (1..BOLUS_RETRIES).forEach { tryNumber ->
        val cmd = if (bolusCanceled) cancelBolus() else getPodStatus()
        try {
            cmd.blockingAwait()
            // Success - break out
        } catch (e: Exception) {
            Thread.sleep(BOLUS_RETRY_INTERVAL_MS)  // Retry every 2 sec
        }
    }
}
```

---

## 7. Timing Constraints

### Bolus Delivery Speed

| Pump | Delivery Rate | 1U Delivery Time | 5U Delivery Time |
|------|---------------|------------------|------------------|
| Omnipod DASH/Eros | 40 pulses/min | ~75 sec | ~6.25 min |
| Dana RS (Fast) | 1U/12sec | 12 sec | 60 sec |
| Dana RS (Normal) | 1U/30sec | 30 sec | 2.5 min |
| Dana RS (Slow) | 1U/60sec | 60 sec | 5 min |
| Medtronic | ~40 sec/U | 40 sec | ~3.3 min |

### Loop Cycle Timing

| System | Cycle Interval | TBR Duration | Max Recommended Bolus |
|--------|----------------|--------------|----------------------|
| Loop | 5 min | 30 min | Per user settings |
| Trio | 5 min | 30 min | Per user settings |
| AAPS (SMB) | ~3 min | 30 min | maxSMBBasalMinutes |

### Command Timeouts

| System | Connect Timeout | Command Timeout | Retry Interval |
|--------|-----------------|-----------------|----------------|
| OmniBLE | 30 sec | 30 sec | 2 sec |
| Dana RS | 10 sec | 30 sec | Immediate |
| Medtronic RF | 15 sec | 30 sec | 1 sec |

---

## 8. Pump State Synchronization

### History Reconciliation

#### Loop Pattern
```swift
// PumpManagerDelegate callback
func pumpManager(_ pumpManager: PumpManager, 
                 hasNewPumpEvents events: [NewPumpEvent], 
                 lastReconciliation: Date?, 
                 replacePendingEvents: Bool, 
                 completion: @escaping (_ error: Error?) -> Void)
```

Loop tracks `lastReconciliation` date:
- For **closed-loop only pumps** (Omnipod): Last telemetry received
- For **pumps with UI** (Medtronic): Last full history sync

#### AAPS Pattern (PumpSync)

Two sync methods based on pump capabilities:

1. **History-capable pumps** (Dana RS): 
   - Read pump history after command
   - Match via `pumpId` from history
   - `syncBolusWithPumpId()`

2. **Non-history pumps** (older Dana):
   - Generate temporary ID before command
   - `addBolusWithTempId()` → deliver → `syncBolusWithTempId()`

### Clock Drift Handling

Loop:
```swift
func pumpManager(_ pumpManager: PumpManager, didAdjustPumpClockBy adjustment: TimeInterval)
```

AAPS:
```kotlin
fun canHandleDST(): Boolean
fun timezoneOrDSTChanged(timeChangeType: TimeChangeType)
```

---

## 9. Safety Limits

### Constraint Checking

| System | Layer | Constraints Applied |
|--------|-------|---------------------|
| Loop | PumpManager | `roundToSupportedBolusVolume()` before command |
| AAPS | ConstraintChecker | `applyBolusConstraints()` system-wide |
| Both | Pump hardware | Max bolus, max basal, reservoir limits |

### AAPS Error Codes (Dana)

```kotlin
when (danaPump.bolusStartErrorCode) {
    0x10 -> "Max bolus violation"
    0x20 -> "Command error"
    0x40 -> "Speed error"
    0x80 -> "Insulin limit violation"
}
```

### Omnipod Safety States

```kotlin
if (podStateManager.deliveryStatus?.bolusDeliveringActive() == true) {
    return result.comment("Bolus already in progress")
}

if (requestedBolusAmount > reservoirLevel) {
    return result.comment("Not enough insulin")
}
```

---

## 10. Cross-System Comparison Summary

| Feature | Loop/Trio | AAPS |
|---------|-----------|------|
| **Pump interface** | PumpManager protocol | Pump interface |
| **Command model** | Async completion | Sync result |
| **Extended bolus** | Not supported | Native support |
| **TBR units** | Seconds | Minutes |
| **TBR type** | Absolute only | Absolute or Percent |
| **History sync** | Delegate callback | PumpSync interface |
| **Pump drivers** | OmniBLE, OmniKit, MinimedKit | 10+ drivers |
| **RF bridge** | RileyLink | RileyLink |
| **Encryption** | Per-pump | Per-pump |

---

## Source Files Analyzed

### Loop/Trio (Swift)
- `LoopKit/LoopKit/DeviceManager/PumpManager.swift` - Core protocol
- `LoopKit/LoopKit/DeviceManager/PumpManagerStatus.swift` - Status states
- `Loop/Loop/Managers/DoseEnactor.swift` - Command sequencing
- `OmniBLE/OmniBLE/Bluetooth/BluetoothServices.swift` - BLE UUIDs
- `OmniBLE/OmniBLE/Bluetooth/EnDecrypt/EnDecrypt.swift` - AES-CCM encryption
- `MinimedKit/MinimedKit/PumpManager/RileyLinkDevice.swift` - RF bridge

### AAPS (Kotlin)
- `core/interfaces/src/main/kotlin/app/aaps/core/interfaces/pump/Pump.kt` - Core interface
- `core/interfaces/src/main/kotlin/app/aaps/core/interfaces/pump/PumpSync.kt` - History sync
- `core/data/src/main/kotlin/app/aaps/core/data/pump/defs/PumpType.kt` - Pump definitions
- `pump/danars/src/main/kotlin/app/aaps/pump/danars/DanaRSPlugin.kt` - Dana RS driver
- `pump/danars/src/main/kotlin/app/aaps/pump/danars/comm/DanaRSPacket.kt` - BLE packets
- `pump/omnipod/dash/src/main/kotlin/.../OmnipodDashPumpPlugin.kt` - DASH driver

---

## Gap Summary

See `traceability/gaps.md` for detailed gap tracking:

- **GAP-PUMP-001**: No standardized pump capability exchange format
- **GAP-PUMP-002**: Extended bolus not supported in Loop ecosystem
- **GAP-PUMP-003**: TBR duration units differ (seconds vs minutes)
- **GAP-PUMP-004**: Pump error codes not normalized across systems
- **GAP-PUMP-005**: No standard for delivery uncertainty reporting
