# BLE CGM Library Consolidation Analysis

> **Cycle**: 68  
> **Date**: 2026-01-31  
> **Status**: Complete  
> **Backlog Item**: ios-mobile-platform.md #9

## Executive Summary

This analysis evaluates the feasibility of a unified BLE CGM library by comparing implementations across CGMBLEKit (Loop), DiaBLE, xDrip4iOS, and LibreTransmitter. The conclusion is that **full consolidation is not practical** due to deep architectural differences, but **shared protocol layers** and **data model standards** can significantly improve interoperability.

## Libraries Analyzed

| Library | App | Protocols | Architecture |
|---------|-----|-----------|--------------|
| CGMBLEKit | Loop | Dexcom G5/G6 | LoopKit plugin |
| LibreTransmitter | Loop | Libre 2/3, MiaoMiao, Bubble | LoopKit plugin |
| DiaBLE | DiaBLE | Dexcom G6/G7, Libre 1/2/3 | Observable pattern |
| xDrip4iOS | xDrip4iOS | Dexcom G4-G7, 10+ Libre bridges | Protocol-based |

---

## Architecture Comparison

### CGMBLEKit (Loop - Dexcom Only)

**Location**: `externals/LoopWorkspace/CGMBLEKit/`

**Design Pattern**: LoopKit CGMManager plugin with delegate callbacks

**Key Components**:
```
BluetoothManager.swift     → Core BLE discovery/connection
PeripheralManager.swift    → Peripheral operations, timeouts
Transmitter.swift          → High-level abstraction
TransmitterManager.swift   → G5CGMManager, G6CGMManager
Messages/                  → 27 message types (Rx/Tx)
```

**Protocol Support**:
- ✅ Dexcom G5 (authentication, calibration)
- ✅ Dexcom G6 (no calibration required)
- ❌ Dexcom G7 (not supported - no J-PAKE)
- ❌ Libre sensors (separate LibreTransmitter)

**Key Protocols**:
```swift
protocol CGMManager: DeviceManager
protocol TransmitterDelegate: AnyObject
protocol TransmitterManagerObserver: AnyObject
protocol TransmitterTxMessage / TransmitterRxMessage
```

**Strengths**:
- Clean LoopKit integration
- Well-tested G5/G6 support
- HKDevice metadata for HealthKit

**Weaknesses**:
- No G7 support (missing J-PAKE crypto)
- Tightly coupled to LoopKit
- No Libre support (separate package)

---

### LibreTransmitter (Loop - Libre Only)

**Location**: `externals/LoopWorkspace/LibreTransmitter/`

**Design Pattern**: LoopKit CGMManager plugin, similar to CGMBLEKit

**Key Components**:
```
Bluetooth/Transmitter/
  LibreTransmitterProxyManager.swift   → Base manager
  Libre2DirectTransmitter.swift        → Direct Libre 2 EU
  BubbleTransmitter.swift              → Bubble bridge
  MiaomiaoTransmitter.swift            → MiaoMiao bridge
LibreTransmitterManagerV3.swift        → LoopKit CGMManager
```

**Protocol Support**:
- ✅ Libre 2 EU (direct BLE)
- ✅ MiaoMiao bridge
- ✅ Bubble bridge
- ❌ Libre 3 (not fully supported)

**Key Protocol**:
```swift
protocol LibreTransmitterProxyProtocol: AnyObject
protocol LibreTransmitterDelegate: AnyObject
```

---

### DiaBLE

**Location**: `externals/DiaBLE/DiaBLE/`

**Design Pattern**: SwiftUI Observable pattern with device hierarchy

**Key Components**:
```
Device.swift           → @Observable class Device (base)
Transmitter.swift      → @Observable class Transmitter: Device
Sensor.swift           → @Observable class Sensor
Dexcom.swift           → @Observable class Dexcom: Transmitter
DexcomG7.swift         → @Observable class DexcomG7: Sensor
Libre.swift            → @Observable class Libre: Sensor
Libre2.swift           → @Observable class Libre2: Libre
Libre3.swift           → @Observable class Libre3: Libre
Abbott.swift           → @Observable class Abbott: Transmitter
Bluetooth.swift        → BLE enum/constants
BluetoothDelegate.swift → CBCentralManagerDelegate
```

**Protocol Support**:
- ✅ Dexcom G6 (authentication)
- ✅ Dexcom G7 (J-PAKE documented)
- ✅ Libre 1/2/2Gen2/3
- ✅ Abbott Freestyle

**Strengths**:
- Most comprehensive protocol coverage
- Detailed protocol documentation
- SwiftUI-native Observable pattern
- Active G7/Libre 3 research

**Weaknesses**:
- Not LoopKit compatible
- Observable pattern incompatible with delegate pattern
- No AID integration

---

### xDrip4iOS

**Location**: `externals/xdripswift/xdrip/BluetoothTransmitter/CGM/`

**Design Pattern**: Protocol-oriented with transmitter delegates

**Key Components**:
```
Generic/
  CGMTransmitter.swift           → Base protocol
  CGMTransmitterDelegate.swift   → Callback protocol
  GlucoseData.swift              → Data model
  TransmitterBatteryInfo.swift   → Battery enum

Dexcom/
  G4/, G5/, G6Firefly/, G7/      → Per-generation implementations
  Generic/                       → Shared Dexcom messages

Libre/
  MiaoMiao/, Bubble/, Blucon/    → Bridge implementations
  Libre2/, Atom/, etc.           → Direct implementations
  Utilities/                     → LibreDataParser, smoothing
```

**Protocol Support**:
- ✅ Dexcom G4/G5/G6/G6Firefly/G7
- ✅ 10+ Libre bridges (MiaoMiao, Bubble, Blucon, etc.)
- ✅ Libre 2 direct
- ⚠️ Libre 3 (limited)

**Key Protocols**:
```swift
protocol CGMTransmitter {
    func cgmTransmitterType() -> CGMTransmitterType
    func getCBUUID_Service() -> String
    func getCBUUID_Receive() -> String
    func requestNewReading()
    func startSensor()
    func calibrate(calibrationToSendToTransmitter: Calibration)
}

protocol CGMTransmitterDelegate {
    func cgmTransmitterInfoReceived(
        glucoseData: inout [GlucoseData],
        transmitterBatteryInfo: TransmitterBatteryInfo?,
        sensorAge: TimeInterval?
    )
}
```

**Strengths**:
- Widest device support
- Clean protocol abstraction
- Easy to add new transmitters

**Weaknesses**:
- Not LoopKit compatible
- No HealthKit integration built-in
- Complex class hierarchy

---

## Protocol Comparison Matrix

### Dexcom Protocols

| Feature | CGMBLEKit | DiaBLE | xDrip4iOS |
|---------|-----------|--------|-----------|
| G5 Auth | ✅ AuthRequest/Challenge | ✅ Opcode-based | ✅ AuthTxMessage |
| G6 Auth | ✅ Same as G5 | ✅ Same as G5 | ✅ Same as G5 |
| G7 J-PAKE | ❌ Missing | ✅ Documented | ✅ Implemented |
| Backfill | ✅ BackfillMessage | ✅ Backfill UUID | ✅ BackfillRxMessage |
| Calibration | ✅ CalibrateGlucose | ✅ Opcode | ✅ CalibrationTxMessage |
| Session Start | ✅ SessionStart | ✅ Opcode | ✅ SessionStartTx |

### Libre Protocols

| Feature | LibreTransmitter | DiaBLE | xDrip4iOS |
|---------|-----------------|--------|-----------|
| Libre 2 Direct | ✅ EU only | ✅ All regions | ✅ With bridges |
| Libre 2 Gen2 | ⚠️ Partial | ✅ Documented | ⚠️ Partial |
| Libre 3 | ❌ No | ✅ Documented | ⚠️ Limited |
| FRAM Parse | ✅ OOPParser | ✅ parseFRAM() | ✅ LibreDataParser |
| Bridge Support | ✅ Bubble, MiaoMiao | ❌ No | ✅ 10+ bridges |

---

## Data Model Comparison

### Glucose Reading

**CGMBLEKit**:
```swift
struct Glucose {
    let glucoseMessage: GlucoseSubMessage
    let timeMessage: TransmitterTimeRxMessage
    let transmitterID: String
    let status: TransmitterStatus
    var glucose: HKQuantity?  // mg/dL
    var trend: Int
    var trendRate: HKQuantity?
    var syncIdentifier: String
}
```

**DiaBLE**:
```swift
struct Glucose: Identifiable, Codable {
    var id: Int  // sequence number
    var date: Date
    var value: Int  // mg/dL
    var rawValue: Double
    var rawTemperature: Int
    var temperatureAdjustment: Double
    var hasError: Bool
    var dataQuality: DataQuality
    var dataQualityFlags: Int
}
```

**xDrip4iOS**:
```swift
struct GlucoseData {
    var timeStamp: Date
    var glucoseLevelRaw: Double
    var glucoseLevelFiltered: Double?
    var slope: Double?
    var offset: Double?
}
```

### Battery Info

**CGMBLEKit**: Internal to transmitter state
**DiaBLE**: In Device class properties
**xDrip4iOS**:
```swift
enum TransmitterBatteryInfo {
    case percentage(Int)
    case DexcomG5(voltageA: Int, voltageB: Int, resist: Int, runtime: Int, temperature: Int)
    case DexcomG4(level: Int)
}
```

---

## Consolidation Assessment

### Why Full Consolidation Is Not Practical

1. **Incompatible Design Patterns**
   - CGMBLEKit/LibreTransmitter: Delegate-based, LoopKit plugins
   - DiaBLE: Observable-based, SwiftUI native
   - xDrip4iOS: Protocol-based, UIKit native

2. **Different Target Architectures**
   - Loop/Trio: AID controllers requiring CGMManager protocol
   - DiaBLE: Research/exploration tool
   - xDrip4iOS: Standalone CGM display

3. **Protocol Implementation Depth**
   - DiaBLE has deepest G7/Libre 3 research
   - CGMBLEKit is most stable for G5/G6
   - xDrip4iOS has widest device support

4. **Licensing Considerations**
   - Different open source licenses
   - Attribution requirements vary

### What CAN Be Shared

#### 1. Protocol Specifications (Documentation)

Create shared protocol documentation:
```
specs/cgm-protocols/
  dexcom-g5-g6.md       # Auth, calibration, backfill
  dexcom-g7.md          # J-PAKE, pairing
  libre-2.md            # BLE streaming, NFC auth
  libre-3.md            # Pairing, encryption
```

#### 2. BLE Constants Package

**Proposed: `CGMBLEConstants` Swift Package**
```swift
public enum DexcomService {
    public static let advertisement = "FEBC"
    public static let data = "F8083532-849E-531C-C594-30F1F86A4EA5"
}

public enum DexcomCharacteristic {
    public static let communication = "F8083533-..."
    public static let control = "F8083534-..."
    public static let authentication = "F8083535-..."
    public static let backfill = "F8083536-..."
}

public enum DexcomOpcode: UInt8 {
    case authRequestTx = 0x01
    case authChallengeRx = 0x03
    // ...
}
```

#### 3. Glucose Data Model Protocol

**Proposed: `GlucoseReading` Protocol**
```swift
public protocol GlucoseReading {
    var timestamp: Date { get }
    var glucoseValue: Double { get }  // mg/dL
    var trend: GlucoseTrend? { get }
    var trendRate: Double? { get }    // mg/dL/min
    var sensorSerialNumber: String? { get }
    var isCalibrated: Bool { get }
}

public enum GlucoseTrend: Int {
    case doubleDown = 1
    case singleDown = 2
    case fortyFiveDown = 3
    case flat = 4
    case fortyFiveUp = 5
    case singleUp = 6
    case doubleUp = 7
}
```

#### 4. Crypto Utilities

**Shared cryptographic implementations**:
- Dexcom CRC calculation
- Libre 2 decryption keys
- G7 J-PAKE (if abstractable)

---

## Proposed Architecture

### Option A: Shared Protocol Package

```
┌─────────────────────────────────────────────────────┐
│                  CGMBLEConstants                     │
│  (UUIDs, Opcodes, Enums - no implementation)        │
└──────────────────────┬──────────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         │             │             │
         ▼             ▼             ▼
   ┌──────────┐  ┌──────────┐  ┌──────────┐
   │CGMBLEKit │  │ DiaBLE   │  │xDrip4iOS │
   │(Loop)    │  │          │  │          │
   └──────────┘  └──────────┘  └──────────┘
```

### Option B: Shared Data Model Package

```
┌─────────────────────────────────────────────────────┐
│                  GlucoseDataKit                      │
│  (GlucoseReading, Trend, Calibration protocols)     │
└──────────────────────┬──────────────────────────────┘
                       │
    ┌──────────────────┼──────────────────┐
    │                  │                  │
    ▼                  ▼                  ▼
┌────────┐       ┌──────────┐       ┌───────────┐
│LoopKit │       │ DiaBLE   │       │ xDrip4iOS │
│CGM     │       │ Glucose  │       │GlucoseData│
└────────┘       └──────────┘       └───────────┘
```

### Option C: Unified BLE Layer (Most Ambitious)

```
┌─────────────────────────────────────────────────────┐
│                  CGMBLEUnified                       │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐       │
│  │DexcomDriver│ │LibreDriver │ │ BridgeSDK  │       │
│  └────────────┘ └────────────┘ └────────────┘       │
│                                                      │
│  protocol CGMDriver {                                │
│    func connect()                                    │
│    func readGlucose() -> AsyncStream<GlucoseReading>│
│    func calibrate(value: Double)                     │
│  }                                                   │
└──────────────────────┬──────────────────────────────┘
                       │
         Adapters for each app
```

---

## Gaps Identified

| ID | Gap | Impact |
|----|-----|--------|
| GAP-BLE-001 | No shared BLE constants package | Duplicate UUID definitions across 4 codebases |
| GAP-BLE-002 | No standard glucose data model | Each app uses different structures, complicating data exchange |
| GAP-BLE-003 | G7 J-PAKE missing from Loop/CGMBLEKit | Loop cannot support G7 without major update |
| GAP-BLE-004 | Libre 3 support incomplete everywhere | No fully working Libre 3 implementation |
| GAP-BLE-005 | Bridge support not in LoopKit pattern | MiaoMiao/Bubble users can't use standard Loop plugins |

---

## Requirements

| ID | Requirement |
|----|-------------|
| REQ-BLE-001 | Shared packages MUST be license-compatible (MIT preferred) |
| REQ-BLE-002 | Protocol constants MUST match manufacturer specifications |
| REQ-BLE-003 | Glucose data model MUST support mg/dL and mmol/L |
| REQ-BLE-004 | Any shared package MUST NOT break existing app functionality |

---

## Recommendations

### Short-term (Feasible Now)

1. **Create `CGMBLEConstants` Swift Package**
   - UUIDs, opcodes, enums only
   - No implementation code
   - MIT license
   - All apps can adopt incrementally

2. **Document Protocol Specifications**
   - Add to `specs/cgm-protocols/`
   - Reference DiaBLE research
   - Cross-reference existing implementations

### Medium-term (Community Effort)

3. **Create `GlucoseDataKit` Protocol Package**
   - Define `GlucoseReading` protocol
   - Each app provides conforming types
   - Enables data exchange between apps

4. **Add G7 Support to CGMBLEKit**
   - Port J-PAKE from DiaBLE/xDrip4iOS
   - Critical for Loop users

### Long-term (Major Project)

5. **Unified CGM Driver Architecture**
   - Would require buy-in from all projects
   - Significant refactoring effort
   - Benefits: reduced duplication, shared testing

---

## Source Files Analyzed

### CGMBLEKit
- `externals/LoopWorkspace/CGMBLEKit/CGMBLEKit/BluetoothManager.swift`
- `externals/LoopWorkspace/CGMBLEKit/CGMBLEKit/Transmitter.swift`
- `externals/LoopWorkspace/CGMBLEKit/CGMBLEKit/TransmitterManager.swift`
- `externals/LoopWorkspace/CGMBLEKit/CGMBLEKit/Messages/*.swift`

### LibreTransmitter
- `externals/LoopWorkspace/LibreTransmitter/Bluetooth/Transmitter/*.swift`
- `externals/LoopWorkspace/LibreTransmitter/LibreTransmitterManagerV3.swift`

### DiaBLE
- `externals/DiaBLE/DiaBLE/Bluetooth.swift`
- `externals/DiaBLE/DiaBLE/Device.swift`
- `externals/DiaBLE/DiaBLE/Dexcom.swift`
- `externals/DiaBLE/DiaBLE/DexcomG7.swift`
- `externals/DiaBLE/DiaBLE/Libre.swift`
- `externals/DiaBLE/DiaBLE/Libre2.swift`
- `externals/DiaBLE/DiaBLE/Libre3.swift`

### xDrip4iOS
- `externals/xdripswift/xdrip/BluetoothTransmitter/CGM/Generic/CGMTransmitter.swift`
- `externals/xdripswift/xdrip/BluetoothTransmitter/CGM/Generic/CGMTransmitterDelegate.swift`
- `externals/xdripswift/xdrip/BluetoothTransmitter/CGM/Dexcom/Generic/*.swift`
- `externals/xdripswift/xdrip/BluetoothTransmitter/CGM/Libre/Utilities/*.swift`

### LoopKit
- `externals/LoopWorkspace/LoopKit/LoopKit/DeviceManager/CGMManager.swift`
- `externals/LoopWorkspace/LoopKit/LoopKitUI/CGMManagerUI.swift`

---

## Conclusion

**Full BLE CGM library consolidation is not practical** due to fundamental architectural differences between LoopKit's plugin model, DiaBLE's Observable pattern, and xDrip4iOS's protocol-based design.

**Recommended path forward**:
1. Shared constants package (immediate, low risk)
2. Shared data model protocol (medium effort, high value)
3. Protocol documentation (ongoing)
4. G7 support for Loop (community priority)

This approach enables **interoperability without requiring architectural changes** to existing apps.
