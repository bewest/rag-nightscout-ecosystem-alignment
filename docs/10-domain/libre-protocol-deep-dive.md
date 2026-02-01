# Libre Sensor Protocol Deep Dive

This document provides a comprehensive specification of Abbott Libre sensor protocols (Libre 1, 2, 2+, 3, 3+), reverse-engineered from open-source implementations.

## Executive Summary

Abbott Libre continuous glucose monitors use NFC and/or Bluetooth Low Energy (BLE) to communicate with mobile devices. The protocol complexity varies significantly by sensor generation:

- **Libre 1/Pro**: NFC-only, unencrypted FRAM, requires transmitter bridges for continuous monitoring
- **Libre 2**: NFC + BLE, encrypted FRAM and BLE data, proprietary crypto
- **Libre 2 Gen2 (US)**: Enhanced security with session-based authentication
- **Libre 3/3+**: BLE-only, fully encrypted with ECDH key exchange, cloud-dependent decryption

**Key Protocol Differences:**

| Aspect | Libre 1/Pro | Libre 2 | Libre 2 Gen2 | Libre 3/3+ |
|--------|------------|---------|--------------|------------|
| NFC Access | Unencrypted | Encrypted FRAM | Session-based | Pairing only |
| BLE Streaming | No (via bridges) | Yes (encrypted) | Yes (session keys) | Yes (AES-CCM) |
| Encryption | None | XOR cipher | Session crypto | ECDH + AES |
| Warmup | 60 min | 60 min | 60 min | 60 min |
| Max Life | 14 days | 14 days | 14/15 days | 14 days |
| IC Manufacturer | TI (0x07) | TI (0x07) | TI (0x07) | Abbott (0x7a) |

---

## Source Code References

This specification is derived from the following open-source implementations:

| Project | Language | Location | Primary Focus |
|---------|----------|----------|---------------|
| DiaBLE | Swift | `externals/DiaBLE/` | Comprehensive Libre 1/2/3 support |
| LibreTransmitter | Swift | `externals/LoopWorkspace/LibreTransmitter/` | Libre 2 Loop integration |
| xDrip4iOS | Swift | `externals/xdripswift/` | Multi-transmitter bridge support |
| Trio LibreTransmitter | Swift | `externals/Trio/LibreTransmitter/` | Trio integration |

**Conformance Assertions**: [`conformance/assertions/libre-protocol.yaml`](../../conformance/assertions/libre-protocol.yaml) — 16 assertions covering REQ-LIBRE-001 through REQ-LIBRE-006

---

## Sensor Type Detection

Sensor type is determined from the `patchInfo` returned by NFC command `0xA1`:

### PatchInfo First Byte Mapping

```swift
case 0xDF, 0xA2: .libre1
case 0xE5, 0xE6: .libreUS14day
case 0x70:       .libreProH
case 0x9D, 0xC5: .libre2
case 0x76, 0x2B: .libre2Gen2
case 0xC6:       .libre2       // Libre 2+ EU (non-Gen2)
case 0x2C:       .libre2Gen2   // Libre 2+ US (Gen2)
case 0x7F:       .libre2       // Newer EU Libre 2(+) Mid 2025
```

### PatchInfo Structure (6+ bytes for Libre 1/2, 24 bytes for Libre 3)

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| 0 | 1 | Type ID | Sensor type identifier (see mapping above) |
| 2 | 4 bits | Family | SensorFamily raw value (upper 4 bits) |
| 2 | 4 bits | Generation | Security generation (lower 4 bits) |
| 3 | 1 | Region | SensorRegion raw value |
| 4-5 | 2 | Info | Type-specific, used in crypto |

### Libre 3 Extended PatchInfo (24 bytes)

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| 0-1 | 2 | Security Version | Security protocol version |
| 2-3 | 2 | Localization | Region (1=EU, 2=US) + subregion |
| 4-5 | 2 | Generation | 0=Libre 3, 1=Libre 3+ |
| 6-7 | 2 | Wear Duration | Max lifetime in minutes |
| 8-11 | 4 | Firmware Version | 4 bytes: major.minor.patch.build |
| 12 | 1 | Product Type | 4=Libre 3 sensor, 9=Lingo |
| 13 | 1 | Warmup Time | Warmup time / 5 minutes |
| 14 | 1 | Sensor State | Libre 3-specific state enum |
| 15-23 | 9 | Serial Number | Compressed serial number string |

### Sensor Families

```swift
enum SensorFamily: Int {
    case unknown    = -1
    case libre1     = 0
    case librePro   = 1
    case libre2     = 3
    case libre3     = 4
    case libreX     = 5  // Glucose/Ketone sensor
    case libreSense = 7
    case lingo      = 9  // Wellness device
}
```

### Sensor Regions

```swift
enum SensorRegion: Int {
    case unknown            = 0
    case european           = 1
    case usa                = 2
    case australianCanadian = 4
    case easternROW         = 8
}
```

---

## NFC Protocol

### ISO 15693 Standard Commands

All Libre sensors use ISO 15693 (vicinity) NFC. Standard commands:

| Code | Name | Description |
|------|------|-------------|
| 0x20 | Read Single Block | Read 8-byte block by address |
| 0x23 | Read Multiple Blocks | Read range of blocks |
| 0xA1 | Get Patch Info | Abbott custom: returns sensor info |

### Abbott Custom NFC Commands

| Code | Name | Parameters | Description |
|------|------|------------|-------------|
| 0xA0 | Activate | backdoor + readerSerial | Activate sensor |
| 0xA1 | Universal Prefix | subcommand + params | Execute subcommand |
| 0xA2 | Lock | backdoor | Lock sensor |
| 0xA3 | Read Raw | backdoor | Read raw FRAM (Libre 1) |
| 0xA4 | Unlock | backdoor | Unlock for writing |
| 0xB0 | Read Block | address, count | Read memory blocks |
| 0xB3 | Read Blocks | address, count | Read multiple blocks |

### Subcommands (via 0xA1 prefix)

| Code | Name | Description |
|------|------|-------------|
| 0x1A | Unlock | Read FRAM in clear, enable extended reads |
| 0x1B | Activate | Activate sensor |
| 0x1E | Enable Streaming | Enable BLE streaming (Libre 2) |
| 0x1F | Get Session Info | Get session info (Gen2) |
| 0x1C | Unknown | Unknown function |
| 0x1D | Disable BLE | Disables Bluetooth |
| 0x20 | Read Challenge | Gen2: returns 25-byte challenge |
| 0x21 | Read Blocks | Gen2: read FRAM blocks |
| 0x22 | Read Attribute | Gen2: returns 6 bytes (includes state) |

### Backdoor Codes

```swift
var backdoor: Data {
    switch type {
    case .libre1:    Data([0xc2, 0xad, 0x75, 0x21])
    case .libreProH: Data([0xc2, 0xad, 0x00, 0x90])
    default:         Data([0xde, 0xad, 0xbe, 0xef])
    }
}
```

---

## FRAM Memory Layout (Libre 1, 2, 2+, Gen2 Only)

> **Note**: This section applies only to NFC-based sensors (Libre 1, Pro, 2, 2+, Gen2). Libre 3 does **not** use the same FRAM structure and is BLE-only; its data is received via encrypted BLE characteristics (see Libre 3 BLE Protocol section).

The FRAM (Ferroelectric RAM) is 344 bytes organized into three sections:

### Memory Map

| Offset | Size | Section | CRC Location |
|--------|------|---------|--------------|
| 0-23 | 24 bytes | Header | bytes 0-1 |
| 24-319 | 296 bytes | Body | bytes 24-25 |
| 320-343 | 24 bytes | Footer | bytes 320-321 |

### Header (24 bytes)

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| 0-1 | 2 | CRC16 | CRC of bytes 2-23 |
| 2-3 | 2 | Reserved | Calibration i1, i2 packed |
| 4 | 1 | State | SensorState raw value |
| 5 | 1 | Reserved | |
| 6 | 1 | Error Code | Failure error code |
| 7-8 | 2 | Failure Age | Minutes since start when failed |
| 9-23 | 15 | Reserved | Zeros for Libre 1/2 |

### Body (296 bytes)

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| 0-1 | 2 | CRC16 | CRC of bytes 2-295 (body offset 24-25) |
| 2 | 1 | Trend Index | Next trend block to write (0-15) |
| 3 | 1 | History Index | Next history block to write (0-31) |
| 4-99 | 96 | Trend Data | 16 blocks × 6 bytes (1-min readings) |
| 100-291 | 192 | History Data | 32 blocks × 6 bytes (15-min readings) |
| 292-293 | 2 | Sensor Age | Minutes since activation |
| 294 | 1 | Initializations | Sensor initialization count |

### Footer (24 bytes)

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| 0-1 | 2 | CRC16 | CRC of bytes 2-23 (footer offset 320-321) |
| 2-3 | 2 | Region Info | Matches patchInfo[2:3] |
| 6-7 | 2 | Max Life | Maximum sensor life in minutes |
| 8-23 | 16 | Calibration | Factory calibration parameters |

### Glucose Reading Structure (6 bytes per reading)

Each trend and history block contains a packed glucose reading:

| Bit Offset | Bit Count | Field | Description |
|------------|-----------|-------|-------------|
| 0 | 14 | Raw Value | Raw glucose value |
| 14 | 11 | Quality | Data quality (lower 9 bits = error code) |
| 25 | 1 | Has Error | Error flag |
| 26 | 12 | Raw Temperature | Raw temperature reading << 2 |
| 38 | 9 | Temp Adjustment | Temperature adjustment << 2 |
| 47 | 1 | Negative Adj | Sign bit for adjustment |

```swift
let rawValue = readBits(fram, offset, 0, 0xe)       // 14 bits
let quality = UInt16(readBits(fram, offset, 0xe, 0xb)) & 0x1FF  // 9 bits
let qualityFlags = (readBits(fram, offset, 0xe, 0xb) & 0x600) >> 9  // 2 bits
let hasError = readBits(fram, offset, 0x19, 0x1) != 0
let rawTemperature = readBits(fram, offset, 0x1a, 0xc) << 2
var temperatureAdjustment = readBits(fram, offset, 0x26, 0x9) << 2
let negativeAdjustment = readBits(fram, offset, 0x2f, 0x1)
if negativeAdjustment != 0 { temperatureAdjustment = -temperatureAdjustment }
```

### Calibration Parameters (from FRAM footer)

```swift
let i1 = readBits(fram, 2, 0, 3)
let i2 = readBits(fram, 2, 3, 0xa)
let i3 = readBits(fram, 0x150, 0, 8)      // footer[-8]
let i4 = readBits(fram, 0x150, 8, 0xe)
let negativei3 = readBits(fram, 0x150, 0x21, 1) != 0
let i5 = readBits(fram, 0x150, 0x28, 0xc) << 2
let i6 = readBits(fram, 0x150, 0x34, 0xc) << 2
```

---

## CRC-16 Validation

Libre sensors use CRC-16 with bit reversal:

```swift
func crc16(_ data: Data) -> UInt16 {
    let table: [UInt16] = [0, 4489, 8978, 12955, ...]  // 256 entries
    var crc = data.reduce(UInt16(0xFFFF)) { 
        ($0 >> 8) ^ table[Int(($0 ^ UInt16($1)) & 0xFF)] 
    }
    var reverseCrc = UInt16(0)
    for _ in 0 ..< 16 {
        reverseCrc = reverseCrc << 1 | crc & 1
        crc >>= 1
    }
    return reverseCrc
}
```

---

## Libre 2 Encryption

> **Note**: Libre 2 encryption is sensor-specific. The decryption process uses the sensor's 8-byte UID and 6-byte patchInfo as inputs to derive per-sensor keys. The constants below are used in the key derivation algorithm, not as direct encryption keys.

> **Source**: `externals/DiaBLE/DiaBLE/Libre2.swift` lines 1-150

### FRAM Decryption

Libre 2 and Libre US 14-day sensors encrypt FRAM data. The encryption uses a custom XOR cipher with per-sensor key derivation.

#### Key Derivation Constants

```swift
// These are derivation constants, NOT direct keys
// Actual keys are derived using sensor UID and patchInfo
static let key: [UInt16] = [0xA0C5, 0x6860, 0x0000, 0x14C6]
static let secret: UInt16 = 0x1b6a
```

#### Variable Preparation

```swift
static func prepareVariables(id: SensorUid, x: UInt16, y: UInt16) -> [UInt16] {
    let s1 = UInt16(truncatingIfNeeded: UInt(UInt16(id[5], id[4])) + UInt(x) + UInt(y))
    let s2 = UInt16(truncatingIfNeeded: UInt(UInt16(id[3], id[2])) + UInt(key[2]))
    let s3 = UInt16(truncatingIfNeeded: UInt(UInt16(id[1], id[0])) + UInt(x) * 2)
    let s4 = 0x241a ^ key[3]
    return [s1, s2, s3, s4]
}
```

#### Crypto Processing

```swift
static func processCrypto(input: [UInt16]) -> [UInt16] {
    func op(_ value: UInt16) -> UInt16 {
        var res = value >> 2
        if value & 1 != 0 { res = res ^ key[1] }  // 0x6860
        if value & 2 != 0 { res = res ^ key[0] }  // 0xA0C5
        return res
    }
    
    let r0 = op(input[0]) ^ input[3]
    let r1 = op(r0) ^ input[2]
    let r2 = op(r1) ^ input[1]
    let r3 = op(r2) ^ input[0]
    let r4 = op(r3)
    let r5 = op(r4 ^ r0)
    let r6 = op(r5 ^ r1)
    let r7 = op(r6 ^ r2)

    return [r0 ^ r4, r1 ^ r5, r2 ^ r6, r3 ^ r7]
}
```

#### FRAM Block Decryption

```swift
static func decryptFRAM(type: SensorType, id: SensorUid, info: PatchInfo, data: Data) -> Data {
    func getArg(block: Int) -> UInt16 {
        switch type {
        case .libreUS14day:
            if block < 3 || block >= 40 { return 0xcadc }  // Fixed for header/footer
            return UInt16(info[5], info[4])
        case .libre2:
            return UInt16(info[5], info[4]) ^ 0x44
        }
    }
    
    var result = [UInt8]()
    for i in 0 ..< 43 {  // 43 blocks × 8 bytes = 344 bytes
        let input = prepareVariables(id: id, x: UInt16(i), y: getArg(block: i))
        let blockKey = processCrypto(input: input)
        
        // XOR each byte with corresponding key byte
        result.append(data[i * 8 + 0] ^ UInt8(truncatingIfNeeded: blockKey[0]))
        result.append(data[i * 8 + 1] ^ UInt8(truncatingIfNeeded: blockKey[0] >> 8))
        result.append(data[i * 8 + 2] ^ UInt8(truncatingIfNeeded: blockKey[1]))
        // ... continue for all 8 bytes
    }
    return Data(result)
}
```

### BLE Data Decryption

Libre 2 BLE streaming sends 46-byte encrypted packets (20 + 18 + 8 bytes):

```swift
static func decryptBLE(id: SensorUid, data: Data) -> Data {
    let d = usefulFunction(id: id, x: UInt16(Subcommand.activate.rawValue), y: secret)
    let x = UInt16(d[1], d[0]) ^ UInt16(d[3], d[2]) | 0x63
    let y = UInt16(data[1], data[0]) ^ 0x63
    
    var key = [UInt8]()
    var initialKey = processCrypto(input: prepareVariables(id: id, x: x, y: y))
    
    for _ in 0 ..< 8 {  // Generate 64 bytes of key
        key.append(contentsOf: [
            UInt8(truncatingIfNeeded: initialKey[0]),
            UInt8(truncatingIfNeeded: initialKey[0] >> 8),
            // ... 8 bytes per iteration
        ])
        initialKey = processCrypto(input: initialKey)
    }
    
    let result = data[2...].enumerated().map { i, value in
        value ^ key[i]
    }
    
    // Verify CRC
    guard crc16(Data(result.prefix(42))) == UInt16(Data(result[42...43])) else {
        throw DecryptBLEError()
    }
    return Data(result)
}
```

### BLE Streaming Unlock Payload

The enable streaming NFC command requires a special payload:

```swift
static func streamingUnlockPayload(id: SensorUid, info: PatchInfo, 
                                    enableTime: UInt32, unlockCount: UInt16) -> Data {
    let time = enableTime + UInt32(unlockCount)
    let b: [UInt8] = [
        UInt8(time & 0xFF),
        UInt8((time >> 8) & 0xFF),
        UInt8((time >> 16) & 0xFF),
        UInt8((time >> 24) & 0xFF)
    ]
    
    let ad = usefulFunction(id: id, x: UInt16(Subcommand.activate.rawValue), y: secret)
    let ed = usefulFunction(id: id, x: UInt16(Subcommand.enableStreaming.rawValue), 
                            y: UInt16(enableTime & 0xFFFF) ^ UInt16(info[5], info[4]))
    
    // Complex key derivation using CRC16 and processCrypto
    // Returns 12-byte payload: 4 bytes timestamp + 8 bytes auth
}
```

---

## Libre 2 BLE Protocol

### BLE Service UUIDs

```swift
enum UUID: String {
    case abbottCustom     = "FDE3"
    case bleLogin         = "F001"  // Write characteristic
    case compositeRawData = "F002"  // Read/Notify characteristic
}
```

### BLE Data Format (44 bytes after decryption)

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| 0-39 | 40 | Glucose Data | 10 readings × 4 bytes |
| 40-41 | 2 | Wear Time | Sensor age in minutes |
| 42-43 | 2 | CRC16 | CRC of bytes 0-41 |

### BLE Glucose Reading Format (4 bytes per reading)

| Bit Offset | Bit Count | Field |
|------------|-----------|-------|
| 0 | 14 | Raw Value |
| 14 | 12 | Raw Temperature |
| 26 | 5 | Temp Adjustment |
| 31 | 1 | Negative Adjustment |

### Reading Distribution

- **Trend (0-6)**: Sparse current readings at minutes 0, 2, 4, 6, 7, 12, 15
- **History (7-9)**: Latest three 15-minute history values

---

## Libre 2 Gen2 Protocol (US)

Gen2 sensors require session-based authentication:

### Session Commands

| Command ID | Name | Description |
|------------|------|-------------|
| 0 | INIT_LIB | Initialize library |
| 773 | DECRYPT_BLE_DATA | Decrypt BLE streaming data |
| 6145 | GET_PVALUES | Get P-values |
| 6440 | GET_NFC_AUTHENTICATED_CMD | Get NFC authenticated command |
| 6505 | GET_BLE_AUTHENTICATED_CMD | Get BLE authenticated command |
| 6520 | DECRYPT_NFC_STREAM | Decrypt NFC stream |
| 12545 | DECRYPT_NFC_DATA | Decrypt NFC data |
| 18712 | PERFORM_SENSOR_CONTEXT_CRYPTO | Sensor context crypto |
| 22321 | VERIFY_RESPONSE | Verify response |
| 28960 | GET_AUTH_CONTEXT | Get authentication context |
| 29465 | GET_CREATE_SESSION | Create secure session |
| 37400 | END_SESSION | End session |

### Gen2 Errors

```swift
enum Gen2Error: Int {
    case GEN2_SEC_ERROR_INIT            = -1
    case GEN2_SEC_ERROR_CMD             = -2
    case GEN2_SEC_ERROR_KDF             = -9
    case GEN2_SEC_ERROR_RESPONSE_SIZE   = -10
    case GEN2_ERROR_AUTH_CONTEXT        = -11
    case GEN2_ERROR_PRNG_ERROR          = -12
    case GEN2_ERROR_KEY_NOT_FOUND       = -13
    case GEN2_ERROR_SKB_ERROR           = -14
    case GEN2_ERROR_INVALID_RESPONSE    = -15
    case GEN2_ERROR_INSUFFICIENT_BUFFER = -16
    case GEN2_ERROR_CRC_MISMATCH        = -17
}
```

---

## Libre 3 BLE Protocol

> **Note**: Libre 3 is BLE-only and does NOT use NFC FRAM like earlier generations. All data exchange happens via encrypted BLE. The protocol requires ECDH key exchange and AES-CCM encryption; full offline decryption is not completely documented in open-source implementations.

> **Source**: `externals/DiaBLE/DiaBLE/Libre3.swift`

Libre 3 uses a fully encrypted BLE-only protocol with ECDH key exchange.

### BLE Service and Characteristic UUIDs

All characteristics use the base UUID `0898xxxx-EF89-11E9-81B4-2A2AE2DBCCE4` where `xxxx` is the short ID:

| Short ID | Full UUID | Name | Purpose |
|----------|-----------|------|---------|
| 10CC | 089810CC-EF89-11E9-81B4-2A2AE2DBCCE4 | data | Data service |
| 1338 | 08981338-EF89-11E9-81B4-2A2AE2DBCCE4 | patchControl | Send control commands |
| 1482 | 08981482-EF89-11E9-81B4-2A2AE2DBCCE4 | patchStatus | Sensor status notifications |
| 177A | 0898177A-EF89-11E9-81B4-2A2AE2DBCCE4 | oneMinuteReading | Current glucose (1-min updates) |
| 195A | 0898195A-EF89-11E9-81B4-2A2AE2DBCCE4 | historicalData | Backfill historical readings |
| 1AB8 | 08981AB8-EF89-11E9-81B4-2A2AE2DBCCE4 | clinicalData | Clinical data backfill |
| 1BEE | 08981BEE-EF89-11E9-81B4-2A2AE2DBCCE4 | eventLog | Event logging |
| 1D24 | 08981D24-EF89-11E9-81B4-2A2AE2DBCCE4 | factoryData | Factory calibration data |
| 203A | 0898203A-EF89-11E9-81B4-2A2AE2DBCCE4 | security | Security service |
| 2198 | 08982198-EF89-11E9-81B4-2A2AE2DBCCE4 | securityCommands | Security command writes |
| 22CE | 089822CE-EF89-11E9-81B4-2A2AE2DBCCE4 | challengeData | Auth challenge exchange |
| 23FA | 089823FA-EF89-11E9-81B4-2A2AE2DBCCE4 | certificateData | Certificate exchange |
| 2400 | 08982400-EF89-11E9-81B4-2A2AE2DBCCE4 | debug | Debug interface |

Legacy login characteristic (short form): `F001`

### Libre 3 States

```swift
enum State: UInt8 {
    case manufacturing      = 0
    case storage            = 1  // Not activated
    case insertionDetection = 2
    case insertionFailed    = 3
    case paired             = 4  // Advertising 10-15 min after activation
    case expired            = 5  // Still advertising for 24h
    case terminated         = 6  // Shutdown command received
    case error              = 7  // Sensor fell off
    case errorTerminated    = 8
}
```

### Security Commands

```swift
enum SecurityCommand: UInt8 {
    case security_01         = 0x01  // ECDH start
    case security_02         = 0x02  // Load cert data
    case certificateLoadDone = 0x03
    case challengeLoadDone   = 0x08
    case sendCertificate     = 0x09
    case security_0D         = 0x0D  // Key agreement
    case ephemeralLoadDone   = 0x0E
    case readChallenge       = 0x11  // Authorize symmetric
}
```

### Security Events

```swift
enum SecurityEvent: UInt8 {
    case certificateAccepted = 0x04
    case challengeLoadDone   = 0x08
    case certificateReady    = 0x0A
    case ephemeralReady      = 0x0F
}
```

### Packet Types

```swift
enum PacketType: UInt8 {
    case controlCommand   = 0
    case controlResponse  = 1
    case patchStatus      = 2
    case currentGlucose   = 3
    case backfillHistoric = 4
    case backfillClinical = 5
    case eventLog         = 6
    case factoryData      = 7
}
```

### Security Handshake Sequence

The Libre 3 security handshake uses specific command opcodes on the securityCommands characteristic (2198):

| Step | Action | Command/Response | Description |
|------|--------|------------------|-------------|
| 1 | Setup | Enable notifications on 2198, 23FA, 22CE | Prepare for security exchange |
| 2 | Initiate | Write `0x11` (readChallenge) to 2198 | Request challenge |
| 3 | Response | Receive `0x08 0x17` on 2198 | challengeLoadDone + status |
| 4 | Challenge | Receive 23-byte challenge on 22CE | Sensor's challenge |
| 5 | Response | Write 40-byte response to 22CE | Client's challenge response |
| 6 | Confirm | Write `0x08` (challengeLoadDone) to 2198 | Confirm challenge complete |
| 7 | Response | Receive `0x08 0x43` on 2198 | challengeLoadDone + success |
| 8 | KAuth | Receive 67-byte encrypted KAuth on 22CE | Key authentication data |
| 9 | Data | Enable notifications on 1482, 177A, etc. | Ready for glucose data |
| 10 | Status | Receive patch status on 1482 | Sensor state |
| 11 | Glucose | Receive readings on 177A | 1-minute glucose updates |

**Security Command Opcodes** (for REQ-LIBRE-005 verification):
- `0x11`: readChallenge - Initiate authentication
- `0x08`: challengeLoadDone - Confirm challenge exchange complete
- `0x03`: certificateLoadDone
- `0x0E`: ephemeralLoadDone

### Glucose Data Structure (29 bytes)

```swift
struct GlucoseData {
    let lifeCount: UInt16           // Sensor age in minutes
    let readingMgDl: UInt16         // Current glucose
    let rateOfChange: Int16         // Trend rate
    let esaDuration: UInt16         // Early Signal Attenuation duration
    let projectedGlucose: UInt16    // Projected glucose value
    let historicalLifeCount: UInt16 // Historical reading age
    let historicalReading: UInt16   // Historical glucose
    let trend: TrendArrow           // Trend direction
    let uncappedCurrentMgDl: Int    // Uncapped current reading
    let uncappedHistoricMgDl: Int   // Uncapped historical reading
    let temperature: Int            // Sensor temperature
    let fastData: Data              // 8 bytes raw data
}
```

---

## Transmitter Bridge Protocols

For Libre 1 (NFC-only) and enhanced Libre 2 compatibility, third-party transmitters provide continuous BLE data.

### MiaoMiao Protocol

**Service UUIDs:**
```
Service:    6E400001-B5A3-F393-E0A9-E50E24DCCA9E (Nordic UART)
Receive:    6E400003-B5A3-F393-E0A9-E50E24DCCA9E
Write:      6E400002-B5A3-F393-E0A9-E50E24DCCA9E
```

**Commands:**
| Command | Description |
|---------|-------------|
| `0xF0` | Start reading |
| `0xD3` | Change frequency |
| `0x28` | Request new sensor |
| `0x32` | Request full data |

**Response Types:**
```swift
enum MiaoMiaoResponseType: UInt8 {
    case dataPacket   = 0x28  // Full data packet
    case newSensor    = 0x32  // New sensor detected
    case noSensor     = 0x34  // No sensor found
    case frequencySet = 0xD1  // Frequency change confirmed
}
```

**Data Packet Structure (363+ bytes):**
| Offset | Size | Field |
|--------|------|-------|
| 0 | 1 | Response type (0x28) |
| 1-4 | 4 | Packet number |
| 5-12 | 8 | Sensor UID |
| 13 | 1 | Battery percentage |
| 14-15 | 2 | Firmware version |
| 16-17 | 2 | Hardware version |
| 18-361 | 344 | Libre FRAM data |
| 362 | 1 | Footer |
| 363-368 | 6 | PatchInfo (if present) |

### Bubble Protocol

**Service UUIDs:** Same as MiaoMiao (Nordic UART)

**Commands:**
| Command | Description |
|---------|-------------|
| `[0x00, 0xA0, interval]` | Start reading with interval |
| `[0x08, 0xA0, ...]` | Request full data (Bubble Nano) |
| `[0x0C, 0xA0, ...]` | Request data (firmware >= 8.1) |

**Response Types:**
```swift
enum BubbleResponseType: UInt8 {
    case dataInfo       = 0x80  // Device info
    case serialNumber   = 0x8C  // Sensor serial
    case patchInfo      = 0x8D  // Patch info
    case dataPacket     = 0xDD  // FRAM data packet
    case decryptedData  = 0xDE  // Decrypted data (for Libre 2)
    case noSensor       = 0xBF  // No sensor detected
}
```

### Other Bridges

| Device | Service UUID | Protocol |
|--------|--------------|----------|
| Blucon | Specific Blucon UUID | Proprietary |
| Atom | Nordic UART | Similar to Bubble |
| Droplet | Nordic UART | Similar to MiaoMiao |
| GNSentry | Nordic UART | Custom protocol |

---

## Calibration

### Factory Calibration

All Libre sensors use factory calibration stored in FRAM footer:

```swift
func calibratedGlucose(raw: Int, rawTemperature: Int, calibrationInfo: CalibrationInfo) -> Int {
    let glucose = (raw - calibrationInfo.i1) * calibrationInfo.i6 / 
                  (rawTemperature - calibrationInfo.i2) / 
                  calibrationInfo.i5
    return glucose + calibrationInfo.i3
}
```

### OOP (Out Of Process) Calibration

Third-party web services provide enhanced calibration:

1. **LibreOOPWeb**: HTTP API for glucose calculation from FRAM
2. **Native Algorithm**: Replicated from reverse-engineering

### Calibration Info Fields

| Field | Description |
|-------|-------------|
| i1 | Raw value offset |
| i2 | Temperature offset |
| i3 | Glucose offset |
| i4 | Scale factor part 1 |
| i5 | Temperature scale |
| i6 | Raw scale |

---

## Cross-System Compatibility

### System Support Matrix

| Sensor | DiaBLE | LibreTransmitter | xDrip4iOS | xDrip+ Android |
|--------|--------|------------------|-----------|----------------|
| Libre 1 | ✅ | ✅ | ✅ | ✅ |
| Libre Pro | ✅ | ⚠️ | ⚠️ | ✅ |
| Libre 2 EU | ✅ | ✅ | ✅ | ✅ |
| Libre 2 US | ⚠️ | ⚠️ | ⚠️ | ✅ |
| Libre 2 Gen2 | ⚠️ | ❌ | ⚠️ | ✅ |
| Libre 3 | ⚠️ | ❌ | ❌ | ⚠️ |

Legend: ✅ Full support, ⚠️ Partial/experimental, ❌ Not supported

### Integration Notes

1. **Loop/Trio**: Use LibreTransmitter plugin for Libre 2 direct connection
2. **xDrip+**: Supports most sensors via native or OOP algorithms
3. **Nightscout**: Receives data from any compatible app via standard entries API
4. **AAPS**: Can receive CGM data from xDrip+ via broadcast

---

## Error Codes

### Sensor Failure Codes (from FRAM byte 6)

| Code | Description |
|------|-------------|
| 0x01 | ADC IRQ overflow |
| 0x05 | MMI interrupt |
| 0x09 | Error in patch table |
| 0x0A | Low voltage occurred |
| 0x0B | Low voltage occurred |
| 0x0C | FRAM header section CRC error |
| 0x0D | FRAM body section CRC error |
| 0x0E | FRAM footer section CRC error |
| 0x0F | FRAM code section CRC error |
| 0x10 | FRAM Lock Table error |
| 0x13 | Brownout |
| 0x28 | Battery low indication |
| 0x34 | From custom E1 and E2 command |

### Data Quality Flags

The lower 9 bits of the quality field indicate error conditions:

| Flag | Description |
|------|-------------|
| 0x000 | OK |
| 0x001 | SD (Signal Disturbance) |
| 0x002 | Invalid |
| ... | Various error conditions |

---

## Serial Number Encoding

### Algorithm

Libre sensor UIDs are converted to serial numbers using a 5-bit encoding:

```swift
func serialNumber(uid: SensorUid, family: SensorFamily = .libre1) -> String {
    let lookupTable = ["0","1","2","3","4","5","6","7","8","9",
                       "A","C","D","E","F","G","H","J","K","L",
                       "M","N","P","Q","R","T","U","V","W","X","Y","Z"]
    guard uid.count == 8 else { return "" }
    let bytes = Array(uid.reversed().suffix(6))
    var fiveBitsArray = [UInt8]()
    fiveBitsArray.append( bytes[0] >> 3 )
    fiveBitsArray.append( bytes[0] << 2 + bytes[1] >> 6 )
    // ... continue packing bits
    return fiveBitsArray.reduce("\(family.rawValue)") {
        $0 + lookupTable[Int(0x1F & $1)]
    }
}
```

---

## References

- DiaBLE source code: https://github.com/gui-dos/DiaBLE
- LibreTransmitter: https://github.com/dabear/LibreTransmitter
- xDrip4iOS: https://github.com/JohanDegraworked/xdripswift
- Libre Protocol Research: Various community contributions

---

## Document History

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-17 | 1.0 | Initial comprehensive specification |
