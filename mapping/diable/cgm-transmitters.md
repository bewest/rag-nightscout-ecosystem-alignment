# DiaBLE CGM Transmitter Support

This document details the CGM sensors and transmitter devices supported by DiaBLE, including their communication protocols, encryption methods, and data formats.

## Table of Contents

- [Abbott Libre Family](#abbott-libre-family)
- [Dexcom Family](#dexcom-family)
- [Third-Party Bridge Devices](#third-party-bridge-devices)
- [NFC Communication](#nfc-communication)
- [Bluetooth Low Energy Communication](#bluetooth-low-energy-communication)

---

## Abbott Libre Family

### Sensor Type Detection

Abbott sensors are identified by their `patchInfo` bytes read via NFC.

**File**: `Abbott.swift` (207 lines)

```swift
extension SensorType {
    init(patchInfo: Data) {
        switch patchInfo[0] {
        case 0xDF: self = .libre1
        case 0xA2: self = .libre1        // Libre 1 A2
        case 0xE5: self = .libreUS14day
        case 0x70: self = .libreProH
        case 0x9D: self = .libre2
        case 0x76: self = patchInfo[3] == 0x02 ? .libre2US : 
                         patchInfo[3] == 0x04 ? .libre2CA : .libre2
        case 0x00, 0x01: self = .libre3
        default:   self = .none
        }
    }
}
```

### Libre 1 (Original)

**File**: `Libre.swift` (408 lines)

| Feature | Support |
|---------|---------|
| NFC Read | ✅ Full FRAM read |
| BLE | ❌ (requires bridge device) |
| Encryption | None |
| Sensor Life | 14 days |
| Warmup | 60 minutes |

**FRAM Parsing**:
```swift
class Libre: Sensor {
    func parseFRAM() {
        // Header at offset 0x00 (24 bytes)
        let sensorState = SensorState(rawValue: fram[4])
        let sensorAge = Int(fram[317]) << 8 + Int(fram[316])  // minutes
        
        // Trend buffer at 0x18 (96 bytes = 16 readings × 6 bytes)
        let trendIndex = Int(fram[26])
        for i in 0..<16 {
            let offset = 28 + ((trendIndex - 1 - i + 16) % 16) * 6
            let rawValue = readBits(fram, offset, 0, 0xe)
            trend.append(Glucose(rawValue: rawValue, ...))
        }
        
        // History buffer at 0x78 (192 bytes = 32 readings × 6 bytes)
        let historyIndex = Int(fram[27])
        for i in 0..<32 {
            let offset = 124 + ((historyIndex - 1 - i + 32) % 32) * 6
            // Each history point is 15 minutes apart
            history.append(Glucose(rawValue: rawValue, ...))
        }
    }
}
```

**NFC Commands**:
```swift
// Backdoor unlock code for Libre 1
var backdoor: Data { Data([0xc2, 0xad, 0x75, 0x21]) }

// Custom NFC commands
var activationCommand: NFCCommand { NFCCommand(code: 0xA0, parameters: backdoor) }
var lockCommand: NFCCommand { NFCCommand(code: 0xA2, parameters: backdoor) }
var readRawCommand: NFCCommand { NFCCommand(code: 0xA3, parameters: backdoor) }
var unlockCommand: NFCCommand { NFCCommand(code: 0xA4, parameters: backdoor) }
```

### Libre 2

**File**: `Libre2.swift` (433 lines)

| Feature | Support |
|---------|---------|
| NFC Read | ✅ Encrypted FRAM |
| BLE Streaming | ✅ Encrypted data |
| Encryption | AES (custom "usefulFunction") |
| Sensor Life | 14 days |
| Warmup | 60 minutes |

**Encryption**:
```swift
class Libre2 {
    static let secret: UInt16 = 0xA5B6
    
    /// Generates 8-byte authentication token for NFC commands
    static func usefulFunction(id: Data, x: UInt16, y: UInt16) -> Data {
        // XOR-based key derivation using sensor UID
        let s1 = UInt16(truncatingIfNeeded: UInt(id[5]) << 8 + UInt(id[4])) ^ x
        let s2 = UInt16(truncatingIfNeeded: UInt(id[3]) << 8 + UInt(id[2])) ^ y
        let s3 = UInt16(truncatingIfNeeded: UInt(id[1]) << 8 + UInt(id[0]))
        let s4 = ...
        // Returns 8 bytes for command authentication
    }
    
    /// Decrypts FRAM data read from sensor
    static func decryptFRAM(uid: Data, patchInfo: Data, data: Data) -> Data {
        // AES-based decryption
    }
    
    /// Decrypts BLE streaming packets
    static func decryptBLE(uid: Data, data: Data) -> Data {
        // Per-packet decryption for streaming
    }
}
```

**BLE Streaming**:
```swift
// Enable BLE streaming via NFC
let enableStreamingCommand = nfcCommand(.enableStreaming)

// BLE streaming data format (after decryption)
struct Libre2BLEPacket {
    let glucose: Int          // Current glucose
    let glucoseTimestamp: Int // Minutes since sensor start
    let trend: TrendArrow
    let temperature: Int
}
```

### Libre 2 Gen2

**File**: `Libre2Gen2.swift` (258 lines)

Enhanced security version of Libre 2 with challenge-response authentication.

| Feature | Support |
|---------|---------|
| NFC Read | ✅ With challenge-response |
| BLE Streaming | ✅ Enhanced encryption |
| Encryption | Enhanced AES |
| Sensor Life | 14 days |

**Challenge-Response Authentication**:
```swift
enum Subcommand: UInt8 {
    case readChallenge = 0x20   // Returns 25 bytes challenge
    case readBlocks = 0x21      // Read FRAM with auth
    case readAttribute = 0x22   // Returns sensor state
}

func authenticate() {
    // 1. Read challenge from sensor
    let challenge = nfcCommand(.readChallenge)
    // 2. Generate response using device keys
    let response = generateResponse(challenge: challenge)
    // 3. Read FRAM blocks with response
    let data = nfcCommand(.readBlocks, parameters: response)
}
```

### Libre 3

**File**: `Libre3.swift` (1212 lines)

| Feature | Support |
|---------|---------|
| NFC Read | ✅ Activation only |
| BLE Streaming | ✅ AES-CCM encrypted |
| Encryption | AES-CCM |
| Sensor Life | 14 days |
| Warmup | 60 minutes |

**Key Characteristics**:
- NFC used only for activation (not data reading)
- All glucose data via BLE streaming
- Uses AES-CCM (Counter with CBC-MAC) for authenticated encryption
- Device pairing required for BLE connection

**Encryption Architecture**:
```swift
class Libre3: Sensor {
    // AES-CCM encryption parameters
    var pairingKey: Data           // Derived during activation
    var kAuth: Data                // Authentication key
    var kEnc: Data                 // Encryption key
    var nonce: Data                // Counter for CCM
    
    // BLE service UUIDs
    static let serviceUUID = "089810CC-EF89-11E9-81B4-2A2AE2DBCCE4"
    static let notifyCharacteristic = "08981338-EF89-11E9-81B4-2A2AE2DBCCE4"
    static let writeCharacteristic = "0898177A-EF89-11E9-81B4-2A2AE2DBCCE4"
    
    func decrypt(data: Data) -> Data {
        // AES-CCM decryption
        // 1. Verify authentication tag
        // 2. Decrypt payload
    }
    
    var activationNFCCommand: NFCCommand {
        // Complex activation sequence including:
        // - Reading sensor certificate
        // - Generating ephemeral keys
        // - Establishing secure channel
    }
}
```

**BLE Packet Structure**:
```swift
// Libre 3 BLE packet (after decryption)
struct Libre3Packet {
    let opcode: UInt8
    let glucose: UInt16          // Current glucose mg/dL
    let glucoseRaw: UInt16       // Raw sensor value
    let trend: Int8              // Trend direction
    let temperature: Int16
    let timestamp: UInt32        // Unix timestamp
    let quality: UInt8
}
```

### Libre Pro / Pro H

**File**: `LibrePro.swift` (374 lines)

| Feature | Support |
|---------|---------|
| NFC Read | ✅ Full FRAM |
| BLE | ❌ |
| Encryption | None |
| Sensor Life | 14 days (Pro H) |
| Data Access | Retrospective only |

Professional/hospital sensors with no real-time streaming.

```swift
class LibrePro: Sensor {
    // Backdoor for Pro H
    var backdoor: Data { Data([0xc2, 0xad, 0x00, 0x90]) }
    
    // Pro sensors store more history
    var historyCount: Int { 32 * 4 }  // 128 readings (32 hours at 15-min intervals)
}
```

### Lingo

**File**: `Lingo.swift` (835 lines)

Abbott's wellness-focused glucose monitor (non-medical).

| Feature | Support |
|---------|---------|
| NFC Activation | ✅ |
| BLE Streaming | ✅ AES-CCM |
| Encryption | AES-CCM (like Libre 3) |
| Sensor Life | 14 days |

---

## Dexcom Family

### Dexcom G5/G6/ONE

**File**: `Dexcom.swift` (693 lines)

| Feature | G5 | G6 | ONE |
|---------|----|----|-----|
| BLE | ✅ | ✅ | ✅ |
| Bonding | Required | Required | Required |
| Transmitter Life | 90 days | 90 days | 90 days |
| Calibrations | 2x/day | Optional | Optional |

**BLE Service UUIDs**:
```swift
class Dexcom: Transmitter {
    static let serviceUUID = "F8083532-849E-531C-C594-30F1F86A4EA5"
    static let authenticationUUID = "F8083533-849E-531C-C594-30F1F86A4EA5"
    static let controlUUID = "F8083534-849E-531C-C594-30F1F86A4EA5"
    static let backfillUUID = "F8083535-849E-531C-C594-30F1F86A4EA5"
}
```

**Authentication Flow**:
```swift
enum DexcomOpcode: UInt8 {
    case authRequestTx = 0x01      // Start auth
    case authRequestRx = 0x03      // Auth challenge
    case authChallengeTx = 0x04    // Auth response
    case authChallengeRx = 0x05    // Auth result
    case keepAlive = 0x06
    case bondRequest = 0x07
    case bondRequestRx = 0x08
    
    case glucoseTx = 0x30          // Request glucose
    case glucoseRx = 0x31          // Glucose response
    case calibrationTx = 0x32      // Submit calibration
    case backfillTx = 0x50         // Request history
    case backfillRx = 0x51         // History data
}

func authenticate() {
    // 1. Request authentication
    write(Data([DexcomOpcode.authRequestTx.rawValue, 0x02, ...]))
    
    // 2. Receive challenge
    // Response contains 8-byte challenge
    
    // 3. Compute response using transmitter ID and token
    let response = computeAuthResponse(challenge: challenge, id: transmitterID)
    
    // 4. Send response
    write(Data([DexcomOpcode.authChallengeTx.rawValue]) + response)
    
    // 5. Wait for success
    // Then request bonding if needed
}
```

**Glucose Reading Format**:
```swift
struct DexcomGlucose {
    let status: UInt8
    let sequence: UInt32
    let timestamp: UInt32          // Transmitter time
    let glucose: UInt16            // mg/dL
    let glucoseIsDisplayOnly: Bool
    let state: UInt8
    let trend: Int8
}

func parseGlucoseRx(_ data: Data) -> DexcomGlucose {
    // Byte 0: opcode (0x31)
    // Bytes 1-4: status
    // Bytes 5-8: sequence number
    // Bytes 9-12: timestamp
    // Bytes 13-14: glucose value
    // Byte 15: state
    // Byte 16: trend
}
```

### Dexcom G7 / ONE+ / Stelo

**File**: `DexcomG7.swift` (827 lines)

| Feature | G7 | ONE+ | Stelo |
|---------|----|----|-------|
| BLE | ✅ | ✅ | ✅ |
| Sensor Life | 10 days | 10 days | 15 days |
| Warmup | 30 min | 30 min | 30 min |
| Transmitter | Integrated | Integrated | Integrated |

**Key Differences from G6**:
- Integrated transmitter (no separate component)
- Shorter warmup period (30 min vs 2 hours)
- Different BLE service UUIDs
- Enhanced encryption

```swift
class DexcomG7: Transmitter {
    static let serviceUUID = "F8083532-849E-531C-C594-30F1F86A4EA5"  // Same family
    
    // G7-specific characteristics
    static let g7ServiceUUID = "F8083663-..."
    static let g7NotifyUUID = "F8083664-..."
    static let g7WriteUUID = "F8083665-..."
    
    // Extended opcodes for G7
    enum G7Opcode: UInt8 {
        case egv = 0x4E               // Estimated glucose value
        case calibration = 0x4F
        case sensorSession = 0x50
        case glucoseBackfill = 0x52
    }
}
```

---

## Third-Party Bridge Devices

Bridge devices connect to Libre 1 sensors (which lack native BLE) and transmit data via Bluetooth.

### MiaoMiao

**File**: `MiaoMiao.swift` (153 lines)

| Feature | MiaoMiao 1 | MiaoMiao 2 | MiaoMiao 3 |
|---------|------------|------------|------------|
| Supported Sensors | Libre 1 | Libre 1/2 | Libre 1/2 |
| Battery | CR2032 | Built-in | Built-in |
| Connection | BLE | BLE | BLE |

```swift
class MiaoMiao: Device {
    static let dataServiceUUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
    static let dataReadCharacteristicUUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
    static let dataWriteCharacteristicUUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
    
    enum ResponseType: UInt8 {
        case dataPacket = 0x28
        case newSensor = 0x32
        case noSensor = 0x34
        case frequencyChange = 0xD1
    }
    
    /// Command to request sensor data
    static let startReadingCommand = Data([0xF0])
    
    func parsePacket(_ data: Data) {
        // Byte 0: Response type
        // Bytes 1-2: Data length
        // Bytes 3-10: Sensor UID
        // Bytes 11-17: Patch info
        // Bytes 18+: FRAM data (344 bytes)
    }
}
```

### Bubble

**File**: `Bubble.swift` (142 lines)

| Feature | Bubble |
|---------|--------|
| Supported Sensors | Libre 1/2 |
| Battery | Built-in |
| Connection | BLE |

```swift
class Bubble: Device {
    static let dataServiceUUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
    static let dataReadCharacteristicUUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
    static let dataWriteCharacteristicUUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
    
    enum ResponseType: UInt8 {
        case serialNumber = 0x80
        case patchInfo = 0x82
        case dataPacket = 0xDD
        case noSensor = 0xBF
    }
    
    /// Request full FRAM dump
    static let readDataCommand = Data([0x00, 0x00, 0x05])
}
```

### BluCon

**File**: `BluCon.swift` (209 lines)

| Feature | BluCon |
|---------|--------|
| Supported Sensors | Libre 1 |
| Battery | AAA |
| Connection | BLE |

```swift
class BluCon: Device {
    static let dataServiceUUID = "436A62C0-082E-4CE8-A08B-01D81F195B24"
    static let dataReadCharacteristicUUID = "436AA6E9-082E-4CE8-A08B-01D81F195B24"
    static let dataWriteCharacteristicUUID = "436A0C82-082E-4CE8-A08B-01D81F195B24"
    
    enum Command: String {
        case wakeUp = "cb010000"
        case initialState = "cb020000"
        case readSingleBlock = "cb03"     // + block number
        case sleep = "cb050000"
    }
    
    enum ResponseType: UInt8 {
        case wakeupResponse = 0x8B
        case singleBlockInfo = 0x8C
        case sensorData = 0x8E
    }
}
```

---

## NFC Communication

### Core NFC Integration

**File**: `NFC.swift` (933 lines)

DiaBLE uses Apple's CoreNFC framework to communicate with Libre sensors via ISO 15693 protocol.

```swift
#if !os(watchOS)
import CoreNFC

class NFC: NSObject, NFCTagReaderSessionDelegate {
    var session: NFCTagReaderSession?
    var sensor: Sensor?
    var isNFCAvailable: Bool { NFCTagReaderSession.readingAvailable }
    
    // Task types
    enum TaskRequest {
        case enableStreaming   // Enable BLE on Libre 2
        case readFRAM          // Read sensor memory
        case unlock            // Unlock for debug access
        case dump              // Full memory dump
        case reset             // Reset sensor
        case prolong           // Extend sensor life
        case activate          // Activate new sensor
    }
    
    func startSession() {
        session = NFCTagReaderSession(
            pollingOption: .iso15693,
            delegate: self
        )
        session?.alertMessage = "Hold iPhone near sensor"
        session?.begin()
    }
    
    func tagReaderSession(_ session: NFCTagReaderSession, 
                          didDetect tags: [NFCTag]) {
        guard case .iso15693(let tag) = tags.first else { return }
        
        // Connect to tag
        session.connect(to: tags.first!) { error in
            // Read system info
            tag.systemInfo { info in
                // Extract sensor UID (8 bytes)
                let uid = Data(info.uid.reversed())
            }
            
            // Read patch info (sensor type identification)
            tag.customCommand(requestFlags: .highDataRate, 
                              customCommandCode: 0xA1,
                              customRequestParameters: Data()) { patchInfo in
                // Determine sensor type from patch info
            }
        }
    }
}
```

### NFC Commands

```swift
struct NFCCommand {
    let code: Int
    var parameters: Data = Data()
    var description: String = ""
}

extension Sensor {
    // Universal prefix for custom commands
    var universalCommand: NFCCommand { 
        NFCCommand(code: 0xA1, description: "A1 universal prefix") 
    }
    
    // Libre 1 commands (use backdoor)
    var lockCommand: NFCCommand { 
        NFCCommand(code: 0xA2, parameters: backdoor, description: "lock") 
    }
    var readRawCommand: NFCCommand { 
        NFCCommand(code: 0xA3, parameters: backdoor, description: "read raw") 
    }
    var unlockCommand: NFCCommand { 
        NFCCommand(code: 0xA4, parameters: backdoor, description: "unlock") 
    }
    
    // Block read commands (Libre 2/Pro)
    var readBlockCommand: NFCCommand { 
        NFCCommand(code: 0xB0, description: "B0 read block") 
    }
    var readBlocksCommand: NFCCommand { 
        NFCCommand(code: 0xB3, description: "B3 read blocks") 
    }
}
```

### Libre 2 NFC Subcommands

```swift
enum Subcommand: UInt8 {
    case unlock = 0x1a          // Clear FRAM encryption
    case activate = 0x1b        // Start sensor
    case enableStreaming = 0x1e // Enable BLE streaming
    case getSessionInfo = 0x1f  // Get security session
    case unknown0x1d = 0x1d     // Disables Bluetooth
    
    // Gen2 additional commands
    case readChallenge = 0x20   // Get auth challenge
    case readBlocks = 0x21      // Read with auth
    case readAttribute = 0x22   // Get sensor state
}

func nfcCommand(_ code: Subcommand, parameters: Data = Data()) -> NFCCommand {
    var parameters = parameters
    if code.rawValue < 0x20 {
        // Add authentication using usefulFunction
        parameters += Libre2.usefulFunction(id: uid, x: UInt16(code.rawValue), y: secret)
    }
    return NFCCommand(code: 0xA1, parameters: Data([code.rawValue]) + parameters)
}
```

---

## Bluetooth Low Energy Communication

### Core Bluetooth Integration

**File**: `Bluetooth.swift` (121 lines), `BluetoothDelegate.swift` (869 lines)

```swift
class MainDelegate: CBCentralManagerDelegate, CBPeripheralDelegate {
    var centralManager: CBCentralManager!
    
    // Device discovery
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        if central.state == .poweredOn {
            scan()
        }
    }
    
    func scan() {
        centralManager.scanForPeripherals(
            withServices: nil,  // Scan all
            options: [CBCentralManagerScanOptionAllowDuplicatesKey: true]
        )
    }
    
    func centralManager(_ central: CBCentralManager,
                        didDiscover peripheral: CBPeripheral,
                        advertisementData: [String: Any],
                        rssi: NSNumber) {
        // Match known device types by name/service UUIDs
        let name = peripheral.name ?? ""
        
        if name.hasPrefix("MIAOMIAO") {
            device = MiaoMiao(peripheral: peripheral)
        } else if name.hasPrefix("Bubble") {
            device = Bubble(peripheral: peripheral)
        } else if name.hasPrefix("BluCon") {
            device = BluCon(peripheral: peripheral)
        } else if name.hasPrefix("DEXCOM") || name.hasPrefix("Dexcom") {
            device = Dexcom(peripheral: peripheral)
        } else if name.hasPrefix("ABBOTT") {
            device = Libre3(peripheral: peripheral)
        }
    }
}
```

### Standard BLE UUIDs

```swift
struct BLE {
    enum UUID: String {
        // Device Information Service (0x180A)
        case device = "180A"
        case model = "2A24"
        case serial = "2A25"
        case firmware = "2A26"
        case hardware = "2A27"
        case manufacturer = "2A29"
        
        // Battery Service (0x180F)
        case battery = "180F"
        case batteryLevel = "2A19"
        
        // Time Service (0x1805)
        case time = "1805"
        case currentTime = "2A2B"
        
        // CCCD (notifications/indications)
        case configuration = "2902"
    }
}
```

### Characteristic Handling

```swift
func peripheral(_ peripheral: CBPeripheral,
                didUpdateValueFor characteristic: CBCharacteristic,
                error: Error?) {
    guard let data = characteristic.value else { return }
    
    switch device {
    case let device as MiaoMiao:
        device.parsePacket(data)
        
    case let device as Bubble:
        device.parsePacket(data)
        
    case let device as Dexcom:
        device.parseResponse(data)
        
    case let device as Libre3:
        device.parseBLEPacket(data)
    }
}

func write(_ data: Data, for characteristic: CBCharacteristic) {
    device?.peripheral?.writeValue(
        data,
        for: characteristic,
        type: characteristic.properties.contains(.writeWithoutResponse) 
            ? .withoutResponse : .withResponse
    )
}
```

---

## Related Documentation

- [data-models.md](data-models.md) - Glucose and Sensor data structures
- [nightscout-sync.md](nightscout-sync.md) - Uploading CGM data to Nightscout
- [xDrip4iOS CGM Transmitters](../xdrip4ios/cgm-transmitters.md) - Similar documentation for xDrip4iOS
