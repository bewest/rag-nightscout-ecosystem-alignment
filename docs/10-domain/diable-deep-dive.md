# DiaBLE Deep Dive

This document provides a comprehensive analysis of DiaBLE, an iOS/watchOS CGM reader application that supports Abbott Libre and Dexcom sensors with Nightscout integration.

## Executive Summary

DiaBLE is a Swift-based iOS/watchOS application developed by gui-dos that provides direct BLE communication with CGM sensors. Unlike most CGM apps that focus on a single sensor family, DiaBLE supports both Abbott Libre (1/2/3) and Dexcom (G6/G7) sensors, making it a valuable research platform for protocol analysis.

**Key Differentiators:**

| Feature | DiaBLE | xDrip4iOS | Loop/Trio |
|---------|--------|-----------|-----------|
| **Libre 1/2 Direct** | ✅ NFC + BLE | ✅ Via bridges | ❌ Bridge only |
| **Libre 3 Support** | ⚠️ Partial | ⚠️ Cloud only | ⚠️ Cloud only |
| **Dexcom G7** | ⚠️ App-dependent | ⚠️ App-dependent | ⚠️ App-dependent |
| **Apple Watch** | ✅ Native | ❌ | ❌ |
| **Nightscout Upload** | ✅ SGV only | ✅ Full | ✅ Full |
| **Treatment Logging** | ❌ | ✅ | ✅ |
| **AID Integration** | ❌ | ✅ (Trio) | ✅ |

**Nightscout Integration Pattern:**

- **Producer Only**: DiaBLE uploads SGV entries to Nightscout but does not consume or create treatments
- **API Version**: v1 only (`api/v1/entries`)
- **Auth Method**: SHA1-hashed API secret in header
- **Data Source**: Uses sensor type name as device identifier (e.g., "Libre 3", "Dexcom G7")

---

## Repository Structure

```
externals/DiaBLE/
├── DiaBLE/                    # Main iOS app source
│   ├── App.swift              # SwiftUI app entry point
│   ├── MainDelegate.swift     # Central coordinator (BLE, NFC, services)
│   ├── Sensor.swift           # Base sensor class
│   ├── Libre.swift            # Libre 1/2 base class
│   ├── Libre2.swift           # Libre 2 encryption
│   ├── Libre2Gen2.swift       # Libre 2+ Gen2 (US) 
│   ├── Libre3.swift           # Libre 3 BLE protocol
│   ├── Dexcom.swift           # Dexcom base transmitter
│   ├── DexcomG7.swift         # G7 protocol and J-PAKE stubs
│   ├── Nightscout.swift       # Nightscout API client
│   ├── LibreLink.swift        # LibreLinkUp cloud API
│   ├── NFC.swift              # NFC commands and FRAM reading
│   ├── Bluetooth.swift        # BLE UUIDs and utilities
│   ├── BluetoothDelegate.swift# CBCentralManager delegate
│   ├── Glucose.swift          # Glucose data structures
│   └── Health.swift           # HealthKit integration
├── DiaBLE Watch/              # watchOS companion app
├── DiaBLE Playground.swiftpm/ # Swift Playground version
└── README.md                  # Changelog and build instructions
```

> **Source**: `externals/DiaBLE/`

---

## Architecture

### Application Model

DiaBLE uses a shared-reference architecture with two primary coordinating objects:

```swift
class MainDelegate: UIApplicationDelegate {
    var app: AppState           // Observable UI state
    var settings: Settings      // UserDefaults wrapper
    var centralManager: CBCentralManager
    var bluetoothDelegate: BluetoothDelegate
    var nfc: NFC
    var healthKit: HealthKit?
    var libreLinkUp: LibreLinkUp?
    var nightscout: Nightscout?
}
```

> **Source**: `externals/DiaBLE/DiaBLE/MainDelegate.swift:29-44`

**Key Design Pattern**: All components reference `main: MainDelegate` for cross-component communication. This allows simple global expressions like `main.log()` and `app.sensor`.

### Service Architecture

DiaBLE supports three online services, selectable in settings:

```swift
enum OnlineService: String, CaseIterable {
    case nightscout  = "Nightscout"
    case libreLinkUp = "LibreLinkUp"
    case dexcomShare = "DexcomShare"
}
```

> **Source**: `externals/DiaBLE/DiaBLE/App.swift:49-53`

---

## Nightscout Integration

### API Endpoints Used

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `api/v1/entries.json` | Read historical SGV values |
| POST | `api/v1/entries` | Upload new SGV readings |
| DELETE | `api/v1/entries` | Delete entries (test mode) |

### Authentication

DiaBLE uses SHA1-hashed API secret in the `api-secret` header:

```swift
func post(_ endpoint: String, _ jsonObject: Any) async throws -> (Any, URLResponse) {
    let token = settings.nightscoutToken.SHA1  // SHA1 hash of API secret
    var request = URLRequest(url: URL(string: "\(url)/\(endpoint)")!)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.setValue(token, forHTTPHeaderField: "api-secret")
    request.httpBody = jsonData
    // ...
}
```

> **Source**: `externals/DiaBLE/DiaBLE/Nightscout.swift:116-152`

### Entry Upload Format

DiaBLE uploads SGV entries with this field mapping:

```swift
let dictionaryArray = entries.map { [
    "type": "sgv",
    "dateString": ISO8601DateFormatter().string(from: $0.date),
    "date": Int64(($0.date.timeIntervalSince1970 * 1000.0).rounded()),
    "sgv": $0.value,
    "device": $0.source
    // "direction": "NOT COMPUTABLE",  // TODO comment in source
] }
```

> **Source**: `externals/DiaBLE/DiaBLE/Nightscout.swift:155-167`

### Field Mapping: DiaBLE → Nightscout

| DiaBLE Field | Nightscout Field | Notes |
|--------------|------------------|-------|
| `date` | `dateString` | ISO 8601 format |
| `date` | `date` | Unix epoch milliseconds |
| `value` | `sgv` | Integer mg/dL |
| `source` | `device` | Sensor type name (e.g., "Libre 3") |
| N/A | `direction` | Not computed (TODO in source) |
| N/A | `type` | Always "sgv" |

### Missing Features

DiaBLE's Nightscout integration is deliberately minimal:

1. **No trend arrow upload**: `direction` is commented out with TODO
2. **No treatment support**: No bolus, carbs, or temp basal API calls
3. **No devicestatus upload**: No pump or loop status
4. **No v3 API support**: Only v1 endpoints used
5. **Read-only consumption**: Downloads values but doesn't use for AID

---

## Sensor Support Matrix

### Abbott Libre

| Sensor | NFC Read | BLE Stream | Encryption | Status |
|--------|----------|------------|------------|--------|
| Libre 1 | ✅ Full | ❌ None | None | Complete |
| Libre Pro | ✅ Full | ❌ None | None | Complete |
| Libre 2 EU | ✅ Encrypted | ✅ Encrypted | XOR cipher | Complete |
| Libre 2 US | ✅ Encrypted | ✅ Session | Session keys | Complete |
| Libre 2+ EU | ✅ Encrypted | ✅ Encrypted | XOR cipher | Complete |
| Libre 2+ US | ✅ Encrypted | ✅ Session | Gen2 crypto | Complete |
| Libre 3/3+ | ⚠️ Pairing | ⚠️ Eavesdrop | AES-CCM | Partial |
| Lingo | ⚠️ patchInfo | ⚠️ Eavesdrop | AES-CCM | Minimal |

### Dexcom

| Sensor | BLE Connect | Auth | Data Read | Status |
|--------|-------------|------|-----------|--------|
| Dexcom G6 | ✅ | Opcode auth | ✅ | Complete |
| Dexcom ONE | ✅ | Opcode auth | ✅ | Complete |
| Dexcom G7 | ⚠️ | J-PAKE needed | ⚠️ | App-dependent |
| Dexcom ONE+ | ⚠️ | J-PAKE needed | ⚠️ | App-dependent |
| Stelo | 🔍 Detected | J-PAKE needed | ❌ | Detection only |

> **Note**: G7 support requires official Dexcom app running in background because J-PAKE authentication is not fully implemented. DiaBLE can eavesdrop on BLE traffic when Dexcom app handles auth.

> **Source**: `externals/DiaBLE/README.md:39-40`

---

## Sensor Type Detection

DiaBLE determines sensor type from the NFC `patchInfo` first byte:

```swift
extension SensorType {
    init(patchInfo: PatchInfo) {
        self = switch patchInfo[0] {
        case 0xDF, 0xA2: .libre1
        case 0xE5, 0xE6: .libreUS14day
        case 0x70:       .libreProH
        case 0x9D, 0xC5: .libre2
        case 0x76, 0x2B: .libre2Gen2
        case 0xC6:       .libre2     // Libre 2+ EU
        case 0x2C:       .libre2Gen2 // Libre 2+ US
        case 0x7F:       .libre2     // Newer EU Libre 2(+)
        default:
            if patchInfo.count == 24 {
                patchInfo[12] == 4 ? .libre3 :
                patchInfo[12] == 9 ? .lingo :
                    .unknown
            } else { .unknown }
        }
    }
}
```

> **Source**: `externals/DiaBLE/DiaBLE/Libre.swift:8-30`

### Sensor Families and Regions

```swift
enum SensorFamily: Int {
    case unknown    = -1
    case libre1     = 0
    case librePro   = 1
    case libre2     = 3
    case libre3     = 4
    case libreX     = 5  // Glucose/Ketone
    case libreSense = 7
    case lingo      = 9
}

enum SensorRegion: Int {
    case unknown            = 0
    case european           = 1
    case usa                = 2
    case australianCanadian = 4
    case easternROW         = 8
}
```

> **Source**: `externals/DiaBLE/DiaBLE/Sensor.swift:30-71`

---

## Libre 2/2+ Encryption

DiaBLE implements full FRAM decryption for Libre 2 sensors:

```swift
class Libre2: Libre {
    static let key: [UInt16] = [0xA0C5, 0x6860, 0x0000, 0x14C6]
    static let secret: UInt16 = 0x1b6a

    static func prepareVariables(id: SensorUid, x: UInt16, y: UInt16) -> [UInt16] {
        let s1 = UInt16(truncatingIfNeeded: UInt(UInt16(id[5], id[4])) + UInt(x) + UInt(y))
        let s2 = UInt16(truncatingIfNeeded: UInt(UInt16(id[3], id[2])) + UInt(key[2]))
        let s3 = UInt16(truncatingIfNeeded: UInt(UInt16(id[1], id[0])) + UInt(x) * 2)
        let s4 = 0x241a ^ key[3]
        return [s1, s2, s3, s4]
    }

    static func processCrypto(input: [UInt16]) -> [UInt16] {
        func op(_ value: UInt16) -> UInt16 {
            var res = value >> 2
            if value & 1 != 0 { res = res ^ key[1] }
            if value & 2 != 0 { res = res ^ key[0] }
            return res
        }
        // XOR cipher processing...
    }
}
```

> **Source**: `externals/DiaBLE/DiaBLE/Libre2.swift:54-100`

### FRAM Structure

DiaBLE parses the 344-byte FRAM structure:

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| 0-1 | 2 | CRC | CRC16 of bytes 2-23 |
| 2-23 | 22 | Header | Sensor metadata |
| 24-25 | 2 | CRC | CRC16 of body |
| 26 | 1 | trendIndex | Current trend buffer position |
| 27 | 1 | historyIndex | Current history buffer position |
| 28-123 | 96 | trend[16] | 16 trend readings (6 bytes each) |
| 124-315 | 192 | history[32] | 32 history readings (6 bytes each) |
| 316-317 | 2 | age | Sensor age in minutes |
| 318 | 1 | initializations | Number of sensor activations |
| 320-343 | 24 | footer | Calibration and metadata |

> **Source**: `externals/DiaBLE/DiaBLE/Libre.swift:105-199`

---

## Libre 3 Support

DiaBLE documents extensive Libre 3 protocol details but with limited functionality:

### BLE UUIDs

```swift
enum UUID: String {
    case data             = "089810CC-EF89-11E9-81B4-2A2AE2DBCCE4"
    case patchControl     = "08981338-EF89-11E9-81B4-2A2AE2DBCCE4"
    case patchStatus      = "08981482-EF89-11E9-81B4-2A2AE2DBCCE4"
    case oneMinuteReading = "0898177A-EF89-11E9-81B4-2A2AE2DBCCE4"
    case historicalData   = "0898195A-EF89-11E9-81B4-2A2AE2DBCCE4"
    case clinicalData     = "08981AB8-EF89-11E9-81B4-2A2AE2DBCCE4"
    case eventLog         = "08981BEE-EF89-11E9-81B4-2A2AE2DBCCE4"
    case factoryData      = "08981D24-EF89-11E9-81B4-2A2AE2DBCCE4"
    case security         = "0898203A-EF89-11E9-81B4-2A2AE2DBCCE4"
    case securityCommands = "08982198-EF89-11E9-81B4-2A2AE2DBCCE4"
    case challengeData    = "089822CE-EF89-11E9-81B4-2A2AE2DBCCE4"
    case certificateData  = "089823FA-EF89-11E9-81B4-2A2AE2DBCCE4"
}
```

> **Source**: `externals/DiaBLE/DiaBLE/Libre3.swift:318-335`

### Libre 3 Glucose Data Structure

```swift
struct GlucoseData {
    let lifeCount: UInt16          // Sensor age in minutes
    let readingMgDl: UInt16        // Current glucose
    let dqError: UInt16            // Data quality error code
    let historicalLifeCount: UInt16
    let historicalReading: UInt16
    let projectedGlucose: UInt16   // Smoothed/projected value
    let rateOfChange: Int16        // mg/dL per minute
    let trend: TrendArrow
    let esaDuration: UInt16        // Early Signal Attenuation
    let temperatureStatus: Int
    let actionableStatus: Int
    let glycemicAlarmStatus: GlycemicAlarm
    let glucoseRangeStatus: ResultRange
    let sensorCondition: Condition
}
```

> **Source**: `externals/DiaBLE/DiaBLE/Libre3.swift:128-162`

### Libre 3 Encryption Challenge

DiaBLE README documents the encryption challenges:

> "tackle AES 128 CCM, ECDH key agreement, Zimperium zShield anti-tampering... (see Juggluco)"

DiaBLE can:
- ✅ Eavesdrop on encrypted BLE traffic when LibreLink running
- ✅ Parse decrypted realm files from backups
- ⚠️ Cannot independently decrypt live sensor data

> **Source**: `externals/DiaBLE/README.md:37-38`

---

## Dexcom G7 Support

DiaBLE documents G7 opcodes but relies on official app for authentication:

### BLE Opcodes

```swift
enum Opcode: UInt8 {
    case batteryStatus              = 0x22
    case stopSession                = 0x28
    case egv                        = 0x4e  // Current glucose
    case calibrationBounds          = 0x32
    case calibrate                  = 0x34
    case transmitterVersion         = 0x4a
    case transmitterVersionExtended = 0x52
    case encryptionInfo             = 0x38
    case backfill                   = 0x59
    case diagnosticData             = 0x51
    case bleControl                 = 0xea
    // J-PAKE authentication opcodes
    case exchangePakePayload        = 0x0a
    case certificateExchange        = 0x0b
    case proofOfPossession          = 0x0c
}
```

> **Source**: `externals/DiaBLE/DiaBLE/DexcomG7.swift:18-48`

### Connection Flow (Documented)

DiaBLE includes detailed BLE trace documentation:

```
// Connection:
// write  3535  01 00
// write  3535  02 + 8 bytes + 02
// notify 3535  03 + 16 bytes
// write  3535  04 + 8 bytes
// notify 3535  05 01 01           // statusReply
// enable notifications for 3534
// write  3534  4E                 // EGV request
// notify 3534  4E + 18 bytes      // EGV response
// write  3534  59 + 8 bytes       // backfill request
// notify 3536  9-byte packets     // backfill data
```

> **Source**: `externals/DiaBLE/DiaBLE/DexcomG7.swift:52-76`

### J-PAKE Reference

DiaBLE references xDrip+'s `libkeks` for J-PAKE implementation:

> "J-PAKE authentication protocol (see xDrip+'s keks)"

> **Source**: `externals/DiaBLE/README.md:40`

---

## LibreLinkUp Integration

DiaBLE includes a full LibreLinkUp cloud API client as an alternative data source:

### Regions Supported

```swift
let regions = ["ae", "ap", "au", "ca", "cn", "de", "eu", "eu2", "fr", "jp", "la", "ru", "us"]
```

> **Source**: `externals/DiaBLE/DiaBLE/LibreLink.swift:170`

### Data Structures

```swift
struct GlucoseMeasurement: Codable {
    let factoryTimestamp: String  // Sensor time
    let timestamp: String         // Phone time
    let type: Int                 // 0: graph, 1: logbook, 2: alarm, 3: hybrid
    let alarmType: Int?           // 0: fixedLow, 1: low, 2: high
    let valueInMgPerDl: Int
    let trendArrow: TrendArrow?
    let measurementColor: MeasurementColor
    let glucoseUnits: Int         // 0: mmol/L, 1: mg/dL
    let isHigh: Bool              // HI flag
    let isLow: Bool               // LO flag
}
```

> **Source**: `externals/DiaBLE/DiaBLE/LibreLink.swift:112-126`

---

## Data Quality Handling

DiaBLE tracks glucose data quality with detailed error flags:

```swift
struct DataQuality: OptionSet, Codable {
    static let OK = DataQuality([])
    static let SD14_FIFO_OVERFLOW  = DataQuality(rawValue: 0x0001)
    static let FILTER_DELTA        = DataQuality(rawValue: 0x0002)
    static let WORK_VOLTAGE        = DataQuality(rawValue: 0x0004)
    static let PEAK_DELTA_EXCEEDED = DataQuality(rawValue: 0x0008)
    static let AVG_DELTA_EXCEEDED  = DataQuality(rawValue: 0x0010)
    static let RF                  = DataQuality(rawValue: 0x0020)  // NFC interference
    static let REF_R               = DataQuality(rawValue: 0x0040)
    static let SIGNAL_SATURATED    = DataQuality(rawValue: 0x0080)
    static let SENSOR_SIGNAL_LOW   = DataQuality(rawValue: 0x0100)
    static let THERMISTOR_OUT_OF_RANGE = DataQuality(rawValue: 0x0800)
    static let TEMP_HIGH           = DataQuality(rawValue: 0x2000)
    static let TEMP_LOW            = DataQuality(rawValue: 0x4000)
    static let INVALID_DATA        = DataQuality(rawValue: 0x8000)
}
```

> **Source**: `externals/DiaBLE/DiaBLE/Glucose.swift:63-91`

---

## HealthKit Integration

DiaBLE writes glucose values to HealthKit:

```swift
class HealthKit {
    func write(_ glucoseValues: [Glucose]) async {
        // Writes to HKQuantityType(.bloodGlucose)
    }
    
    func read(handler: @escaping ([Glucose]) -> Void) {
        // Reads recent glucose from HealthKit
    }
}
```

> **Source**: `externals/DiaBLE/DiaBLE/Health.swift`

---

## Calibration

DiaBLE supports temperature-based calibration for Libre sensors:

```swift
struct CalibrationInfo: Codable, Equatable {
    var i1: Int = 0  // Calibration parameter 1
    var i2: Int = 0  // Calibration parameter 2
    var i3: Int = 0  // Temperature offset
    var i4: Int = 0  // Calibration parameter 4
    var i5: Int = 0  // Temperature coefficient 1
    var i6: Int = 0  // Temperature coefficient 2
}
```

> **Source**: `externals/DiaBLE/DiaBLE/Glucose.swift:32-41`

**Note from README**:

> "The temperature-based calibration algorithm has been derived from the old LibreLink 2.3: it is known that the Vendor improves its algorithms at every new release, smoothing the historical values and projecting the trend ones into the future to compensate the interstitial delay..."

> **Source**: `externals/DiaBLE/README.md:29`

---

## Apple Watch Support

DiaBLE includes a native watchOS app with direct BLE connectivity:

```swift
// Watch app entry
@main
struct DiaBLEApp: App {
    #if os(watchOS)
    @WKApplicationDelegateAdaptor(MainDelegate.self) var main
    #endif
}
```

> **Source**: `externals/DiaBLE/DiaBLE/App.swift:8-11`

**Note**: Direct Libre 2/3 and Dexcom G7 connection from Apple Watch is "a proof of concept that it is technically possible" - keeping the connection running in background requires additional work.

> **Source**: `externals/DiaBLE/README.md:31`

---

## Interoperability Gaps

### GAP-CGM-001: No Treatment Support (Existing)

**Description**: DiaBLE only uploads CGM entries and cannot create, edit, or sync treatments. Users must use another app for treatment logging.

**Source**: `externals/DiaBLE/DiaBLE/Nightscout.swift` (no treatment endpoints)

**Impact**:
- Cannot log insulin or carbs from DiaBLE
- No unified CGM + treatment workflow
- Cannot use as standalone diabetes management

**Remediation**: Accept as design choice (CGM-only producer) or add treatment API.

**Note**: This gap was previously documented in `traceability/cgm-sources-gaps.md`.

---

### GAP-DIABLE-002: No Trend Direction Upload

**Description**: DiaBLE does not upload trend direction to Nightscout. The source code has a TODO comment for direction calculation.

**Source**: `externals/DiaBLE/DiaBLE/Nightscout.swift:163`

**Impact**:
- Nightscout graphs lack trend arrows
- Follower apps cannot display direction
- Missing data for AID systems consuming from Nightscout

**Remediation**: Implement direction calculation from rate of change data.

---

### GAP-DIABLE-003: No v3 API Support

**Description**: DiaBLE uses only Nightscout v1 API endpoints. No support for v3 features like identifier-based sync or atomic operations.

**Source**: `externals/DiaBLE/DiaBLE/Nightscout.swift:40-45`

**Impact**:
- Relies on date-based deduplication
- No proper sync identity handling
- May create duplicates if timing varies

**Remediation**: Add v3 API support with proper identifiers.

---

## Source Files Analyzed

| File | Lines | Purpose |
|------|-------|---------|
| `DiaBLE/Nightscout.swift` | 273 | Nightscout API client |
| `DiaBLE/LibreLink.swift` | 550+ | LibreLinkUp cloud API |
| `DiaBLE/Sensor.swift` | 151 | Base sensor class |
| `DiaBLE/Libre.swift` | 200 | Libre 1/2 base class |
| `DiaBLE/Libre2.swift` | 200+ | Libre 2 encryption |
| `DiaBLE/Libre3.swift` | 500+ | Libre 3 protocol structures |
| `DiaBLE/DexcomG7.swift` | 500+ | G7 opcodes and traces |
| `DiaBLE/Glucose.swift` | 200+ | Glucose data structures |
| `DiaBLE/MainDelegate.swift` | 400+ | Central coordinator |
| `DiaBLE/App.swift` | 150 | SwiftUI app entry |

---

## Related Documentation

- [Libre Protocol Deep Dive](./libre-protocol-deep-dive.md) - Detailed Libre 1/2/3 protocol
- [Dexcom BLE Protocol Deep Dive](./dexcom-ble-protocol-deep-dive.md) - G6/G7 BLE protocol
- [G7 Protocol Specification](./g7-protocol-specification.md) - J-PAKE authentication

---

## References

- DiaBLE repository: https://github.com/gui-dos/DiaBLE
- DiaBLE TestFlight: https://testflight.apple.com/join/s4vTFYpC
- Juggluco (Libre 3 reference): https://github.com/j-kaltes/Juggluco
- xDrip+ libkeks (J-PAKE): https://github.com/NightscoutFoundation/xDrip/tree/master/libkeks
