# Dexcom G6/G7 BLE Protocol Deep Dive

This document provides a comprehensive specification of the Dexcom G6 and G7 Bluetooth Low Energy (BLE) protocols, reverse-engineered from open-source implementations.

## Executive Summary

The Dexcom G6 and G7 continuous glucose monitors use Bluetooth Low Energy (BLE) to communicate with mobile devices. The protocol consists of:

- **BLE Service Discovery**: Standardized Dexcom service UUIDs
- **Authentication**: Challenge-response using AES-128-ECB (G6) or J-PAKE (G7)
- **Message Exchange**: Opcode-based command/response pairs
- **Data Integrity**: CRC-16 CCITT (XModem) checksums

**Key Differences G6 vs G7:**
| Aspect | G6 | G7 |
|--------|----|----|
| Authentication | AES-128-ECB challenge-response | J-PAKE (Password Authenticated Key Exchange) |
| Connection Slots | 2 (allows xDrip + Dexcom app) | 1 (exclusive connection) |
| Glucose Opcode | 0x30/0x31 or 0x4E/0x4F | 0x4E/0x4F only |
| Calibration | Factory + user calibration | Factory calibration only |
| Warmup Period | 2 hours | 27 minutes |

---

## Source Code References

This specification is derived from the following open-source implementations:

| Project | Language | Location | Primary Author |
|---------|----------|----------|----------------|
| CGMBLEKit | Swift | `externals/LoopWorkspace/CGMBLEKit/` | Nathan Racklyeft / LoopKit |
| G7SensorKit | Swift | `externals/LoopWorkspace/G7SensorKit/` | Pete Schwamb / LoopKit |
| xdrip-js | Node.js | `externals/xdrip-js/` | xDrip+ community |
| DiaBLE | Swift | `externals/DiaBLE/` | gui-dos |
| xDrip+ | Java | (external) | NightscoutFoundation |

---

## BLE Service Architecture

### Service UUIDs

```
Advertisement Service:  FEBC
CGM Data Service:       F8083532-849E-531C-C594-30F1F86A4EA5
Service B (Unknown):    F8084532-849E-531C-C594-30F1F86A4EA5
```

### CGM Service Characteristics

| Characteristic | UUID | Properties | Purpose |
|----------------|------|------------|---------|
| Communication | F8083533-849E-531C-C594-30F1F86A4EA5 | Read/Notify | Status updates |
| Control | F8083534-849E-531C-C594-30F1F86A4EA5 | Write/Indicate | Command exchange |
| Authentication | F8083535-849E-531C-C594-30F1F86A4EA5 | Write/Indicate | Auth handshake |
| Backfill | F8083536-849E-531C-C594-30F1F86A4EA5 | Read/Write/Notify | Historical data |
| Unknown1 | F8083537-849E-531C-C594-30F1F86A4EA5 | - | Older G6 only |
| J-PAKE | F8083538-849E-531C-C594-30F1F86A4EA5 | - | G7 J-PAKE exchange |

### Service B Characteristics (Less Documented)

| Characteristic | UUID | Properties |
|----------------|------|------------|
| Characteristic E | F8084533-849E-531C-C594-30F1F86A4EA5 | Write/Indicate |
| Characteristic F | F8084534-849E-531C-C594-30F1F86A4EA5 | Read/Write/Notify |

---

## Message Protocol

### Opcode Reference Table

#### Authentication Opcodes (0x01-0x08)

| Opcode | Hex | Name | Direction | Description |
|--------|-----|------|-----------|-------------|
| 0x01 | `01` | AuthRequestTx | Client→Transmitter | Initiate auth with 8-byte single-use token |
| 0x02 | `02` | AuthRequest2Tx | Client→Transmitter | G7: App key challenge |
| 0x03 | `03` | AuthRequestRx | Transmitter→Client | Returns tokenHash + 8-byte challenge |
| 0x04 | `04` | AuthChallengeTx | Client→Transmitter | Client's computed challenge hash |
| 0x05 | `05` | AuthChallengeRx | Transmitter→Client | Authentication result (authenticated, bonded) |
| 0x06 | `06` | KeepAlive | Client→Transmitter | Keep connection alive, set ad params |
| 0x07 | `07` | BondRequest | Client→Transmitter | Request Bluetooth bonding |
| 0x08 | `08` | PairRequestRx | Transmitter→Client | Bond request response |

#### Control Opcodes (0x09-0x0C)

| Opcode | Hex | Name | Direction | Description |
|--------|-----|------|-----------|-------------|
| 0x09 | `09` | DisconnectTx | Client→Transmitter | Graceful disconnect |
| 0x0A | `0A` | ExchangePakePayload | Bidirectional | G7: J-PAKE phases (0x0A00, 0x0A01, 0x0A02) |
| 0x0B | `0B` | CertificateExchange | Bidirectional | G7: Certificate exchange |
| 0x0C | `0C` | ProofOfPossession | Bidirectional | G7: Signature challenge |

#### Transmitter Info Opcodes (0x20-0x29)

| Opcode | Hex | Name | Direction | Description |
|--------|-----|------|-----------|-------------|
| 0x20 | `20` | FirmwareVersionTx | Client→Transmitter | Request firmware version |
| 0x21 | `21` | FirmwareVersionRx | Transmitter→Client | Firmware version response |
| 0x22 | `22` | BatteryStatusTx | Client→Transmitter | Request battery status |
| 0x23 | `23` | BatteryStatusRx | Transmitter→Client | Battery voltage, runtime, temperature |
| 0x24 | `24` | TransmitterTimeTx | Client→Transmitter | Request transmitter time |
| 0x25 | `25` | TransmitterTimeRx | Transmitter→Client | Current time, session start time |
| 0x26 | `26` | SessionStartTx | Client→Transmitter | Start sensor session |
| 0x27 | `27` | SessionStartRx | Transmitter→Client | Session start confirmation |
| 0x28 | `28` | SessionStopTx | Client→Transmitter | Stop sensor session |
| 0x29 | `29` | SessionStopRx | Transmitter→Client | Session stop confirmation |

#### Glucose Data Opcodes (0x30-0x3E)

| Opcode | Hex | Name | Direction | Description |
|--------|-----|------|-----------|-------------|
| 0x30 | `30` | GlucoseTx | Client→Transmitter | Request glucose (G5/G6) |
| 0x31 | `31` | GlucoseRx | Transmitter→Client | Glucose response (G5/G6) |
| 0x32 | `32` | CalibrationDataTx | Client→Transmitter | Request calibration data |
| 0x33 | `33` | CalibrationDataRx | Transmitter→Client | Calibration data response |
| 0x34 | `34` | CalibrateGlucoseTx | Client→Transmitter | Submit calibration value |
| 0x35 | `35` | CalibrateGlucoseRx | Transmitter→Client | Calibration result |
| 0x3E | `3E` | GlucoseHistoryTx | Client→Transmitter | Request glucose history |

#### Extended Opcodes (0x42-0x59)

| Opcode | Hex | Name | Direction | Description |
|--------|-----|------|-----------|-------------|
| 0x42 | `42` | ResetTx | Client→Transmitter | Reset transmitter |
| 0x43 | `43` | ResetRx | Transmitter→Client | Reset confirmation |
| 0x4A | `4A` | TransmitterVersionTx | Client→Transmitter | Request version (extended) |
| 0x4B | `4B` | TransmitterVersionRx | Transmitter→Client | Version response (extended) |
| 0x4E | `4E` | GlucoseG6Tx | Client→Transmitter | Request glucose (G6/G7) |
| 0x4F | `4F` | GlucoseG6Rx | Transmitter→Client | Glucose response (G6/G7) |
| 0x50 | `50` | GlucoseBackfillTx | Client→Transmitter | Request backfill data |
| 0x51 | `51` | GlucoseBackfillRx | Transmitter→Client | Backfill metadata |
| 0x52 | `52` | TransmitterVersionExtendedTx | Client→Transmitter | G7: Extended version request |
| 0x53 | `53` | TransmitterVersionExtendedRx | Transmitter→Client | G7: Extended version response |
| 0x59 | `59` | BackfillFinished | Transmitter→Client | G7: Backfill complete |

---

## Message Structures

### Authentication Messages

#### AuthRequestTxMessage (0x01)

```
Offset  Length  Type     Field
0       1       UInt8    Opcode (0x01)
1       8       Data     Single-use token (UUID bytes 0-7)
9       1       UInt8    End byte (0x02)
```

**Generation**: Token is 8 bytes from a random UUID.

#### AuthRequestRxMessage (0x03)

```
Offset  Length  Type     Field
0       1       UInt8    Opcode (0x03)
1       8       Data     Token hash
9       8       Data     Challenge
```

**Validation**: Client verifies `tokenHash == hash(singleUseToken, transmitterID)`

#### AuthChallengeTxMessage (0x04)

```
Offset  Length  Type     Field
0       1       UInt8    Opcode (0x04)
1       8       Data     Challenge hash
```

**Computation**: `challengeHash = hash(challenge, transmitterID)`

#### AuthChallengeRxMessage (0x05)

```
Offset  Length  Type     Field
0       1       UInt8    Opcode (0x05)
1       1       UInt8    Is authenticated (0x01 = yes)
2       1       UInt8    Is bonded (0x01 = yes)
```

### Authentication Hash Function

The hash function uses AES-128-ECB encryption:

```javascript
function calculateHash(data, transmitterID) {
  const doubleData = Buffer.concat([data, data]); // 8 bytes → 16 bytes
  const key = `00${transmitterID}00${transmitterID}`; // e.g., "00ABCD1200ABCD12"
  const encrypted = aes128ecb_encrypt(doubleData, key);
  return encrypted.slice(0, 8);
}
```

**Source**: `externals/xdrip-js/lib/transmitter.js:52-70`

---

### Glucose Messages

#### GlucoseTxMessage (0x30 or 0x4E)

```
Offset  Length  Type     Field
0       1       UInt8    Opcode (0x30 G5, 0x4E G6/G7)
1       2       UInt16   CRC-16
```

#### GlucoseRxMessage (0x31 or 0x4F)

**G5/G6 Format (16 bytes minimum):**

```
Offset  Length  Type     Field
0       1       UInt8    Opcode (0x31 or 0x4F)
1       1       UInt8    Status
2       4       UInt32   Sequence number
6       4       UInt32   Timestamp (seconds since activation)
10      2       UInt16   Glucose (low 12 bits) + display-only flag (high 4 bits)
12      1       UInt8    Algorithm/Calibration state
13      1       Int8     Trend (mg/dL per minute × 10)
14      2       UInt16   CRC-16
```

**G7 Format (19 bytes):**

```
Offset  Length  Type     Field
0       1       UInt8    Opcode (0x4E)
1       1       UInt8    Status (0x00 = success)
2       4       UInt32   Message timestamp (seconds since pairing)
6       2       UInt16   Sequence number
8       2       UInt8    Reserved
10      2       UInt16   Age (seconds since sensor reading)
12      2       UInt16   Glucose value (low 12 bits, 0xFFFF = no reading)
14      1       UInt8    Algorithm state
15      1       Int8     Trend rate (mg/dL per minute × 10, 0x7F = unavailable)
16      2       UInt16   Predicted glucose (low 12 bits, 0xFFFF = unavailable)
18      1       UInt8    Calibration/Display flags
```

**Glucose Calculation**:
- Raw value: `glucose = glucoseBytes & 0x0FFF`
- Display-only flag: G6 = `(glucoseBytes & 0xF000) > 0`, G7 = `(data[18] & 0x10) > 0`

**Trend Conversion**:
- `trend = Int8(data[offset]) / 10.0` → mg/dL per minute
- Value `0x7F` (127) indicates unavailable

**Source**: `externals/LoopWorkspace/CGMBLEKit/CGMBLEKit/Messages/GlucoseRxMessage.swift`, `externals/LoopWorkspace/G7SensorKit/G7SensorKit/Messages/G7GlucoseMessage.swift`

---

### Transmitter Time Messages

#### TransmitterTimeTxMessage (0x24)

```
Offset  Length  Type     Field
0       1       UInt8    Opcode (0x24)
1       2       UInt16   CRC-16
```

#### TransmitterTimeRxMessage (0x25)

```
Offset  Length  Type     Field
0       1       UInt8    Opcode (0x25)
1       1       UInt8    Status
2       4       UInt32   Current time (seconds since activation)
6       4       UInt32   Session start time (seconds since activation)
10      4       Reserved
14      2       UInt16   CRC-16
```

**Activation Date Calculation**:
```javascript
activationDate = new Date(Date.now() - currentTime * 1000);
```

---

### Backfill Messages

#### GlucoseBackfillTxMessage (0x50)

```
Offset  Length  Type     Field
0       1       UInt8    Opcode (0x50)
1       1       UInt8    Byte1 (typically 0x05)
2       1       UInt8    Byte2 (typically 0x02)
3       1       UInt8    Identifier (request ID)
4       4       UInt32   Start time (seconds since activation)
8       4       UInt32   End time (seconds since activation)
12      4       UInt32   Length (0x00000000)
16      2       UInt16   Backfill CRC (0x0000)
18      2       UInt16   CRC-16
```

#### GlucoseBackfillRxMessage (0x51)

```
Offset  Length  Type     Field
0       1       UInt8    Opcode (0x51)
1       1       UInt8    Status
2       1       UInt8    Backfill status
3       1       UInt8    Identifier
4       4       UInt32   Start time
8       4       UInt32   End time
12      4       UInt32   Buffer length
16      2       UInt16   Buffer CRC
18      2       UInt16   CRC-16
```

#### Backfill Frame Buffer Format

Backfill data arrives on the Backfill characteristic in frames:

```
Frame Format:
Offset  Length  Type     Field
0       1       UInt8    Frame index (1-based)
1       1       UInt8    Identifier
2+      varies  Data     Glucose entries (8 bytes each)
```

**Glucose Entry Format (8 bytes per reading):**
```
Offset  Length  Type     Field
0       4       UInt32   Timestamp (seconds since activation)
4       2       UInt16   Glucose (low 12 bits) + display-only flag
6       1       UInt8    Algorithm state
7       1       Int8     Trend
```

**Source**: `externals/LoopWorkspace/CGMBLEKit/CGMBLEKit/Messages/GlucoseBackfillMessage.swift`

---

### G7 Backfill Format (9 bytes per entry)

```
Offset  Length  Type     Field
0       3       UInt24   Timestamp (seconds since pairing, 3 bytes)
3       1       Reserved
4       2       UInt16   Glucose (low 12 bits)
6       1       UInt8    Algorithm state
7       1       UInt8    Flags
8       1       Int8     Trend
```

**Source**: `externals/DiaBLE/DiaBLE Playground.swiftpm/DexcomG7.swift:377-394`

---

## Algorithm/Calibration States

### G6 Calibration States

| Value | Name | Has Reliable Glucose |
|-------|------|---------------------|
| 0x01 | Stopped | No |
| 0x02 | Warmup | No |
| 0x04 | NeedFirstInitialCalibration | No |
| 0x05 | NeedSecondInitialCalibration | No |
| 0x06 | OK | Yes |
| 0x07 | NeedCalibration7 | Yes |
| 0x08-0x0A | CalibrationError | No |
| 0x0B-0x0C | SensorFailure | No |
| 0x0D | CalibrationError13 | No |
| 0x0E | NeedCalibration14 | Yes |
| 0x0F-0x11 | SessionFailure | No |
| 0x12 | QuestionMarks | No |

### G7 Algorithm States

| Value | Name | Has Reliable Glucose | Sensor Failed |
|-------|------|---------------------|---------------|
| 0x01 | Stopped | No | No |
| 0x02 | Warmup | No | No |
| 0x03 | ExcessNoise | No | No |
| 0x04 | FirstOfTwoBGsNeeded | No | No |
| 0x05 | SecondOfTwoBGsNeeded | No | No |
| 0x06 | OK | Yes | No |
| 0x07 | NeedsCalibration | No | No |
| 0x08-0x0A | CalibrationError | No | No |
| 0x0B-0x0C | SensorFailed (Aberration) | No | Yes |
| 0x0D | OutOfCalibrationDueToOutlier | No | No |
| 0x0E | OutlierCalibrationRequest | No | No |
| 0x0F | SessionExpired | No | No |
| 0x10-0x11 | SessionFailed | No | Yes |
| 0x12 | TemporarySensorIssue | No | No |
| 0x13-0x15 | SensorFailed (Progressive) | No | Yes |
| 0x16 | SensorFailedDueToRestart | No | Yes |
| 0x18 | Expired | No | No |
| 0x19 | SensorFailed | No | Yes |
| 0x1A | SessionEnded | No | No |

**Source**: `externals/LoopWorkspace/CGMBLEKit/CGMBLEKit/CalibrationState.swift`, `externals/LoopWorkspace/G7SensorKit/G7SensorKit/AlgorithmState.swift`

---

## CRC-16 Implementation

The protocol uses CRC-16 CCITT (XModem):

```swift
func crc16(_ data: [UInt8]) -> UInt16 {
    var crc: UInt16 = 0
    for byte in data {
        crc ^= UInt16(byte) << 8
        for _ in 0..<8 {
            if crc & 0x8000 != 0 {
                crc = (crc << 1) ^ 0x1021
            } else {
                crc = crc << 1
            }
        }
    }
    return crc
}
```

**Validation**: Messages include CRC in last 2 bytes (little-endian). Validate by computing CRC of payload (excluding CRC bytes) and comparing.

**Source**: `externals/LoopWorkspace/CGMBLEKit/CGMBLEKit/NSData+CRC.swift`

---

## Connection Flow

### G6 Connection Sequence

```
1. Scan for FEBC advertisement
2. Connect to peripheral
3. Discover services and characteristics
4. Write AuthRequestTx (0x01) to Authentication characteristic
5. Read AuthRequestRx (0x03) - validate token hash
6. Write AuthChallengeTx (0x04) with computed challenge hash
7. Read AuthChallengeRx (0x05) - check authenticated/bonded
8. If not bonded:
   a. Write KeepAlive (0x06) with timeout
   b. Write BondRequest (0x07)
   c. Wait for OS bonding prompt
9. Enable notifications on Control characteristic
10. Write TransmitterTimeTx (0x24) to Control
11. Read TransmitterTimeRx (0x25)
12. Write GlucoseTx (0x30 or 0x4E) to Control
13. Read GlucoseRx (0x31 or 0x4F)
14. Optionally request backfill (0x50)
15. Write DisconnectTx (0x09)
```

### G7 Connection Sequence (Initial Pairing)

```
1. Scan for FEBC advertisement (device name: DXCM + identifier)
2. Connect to peripheral
3. Enable notifications on Authentication (0x3535) and J-PAKE (0x3538)
4. J-PAKE Phase 0: Write 0x0A00 to Auth, receive data on J-PAKE
5. J-PAKE Phase 1: Write 0x0A01, exchange payloads
6. J-PAKE Phase 2: Write 0x0A02, exchange payloads
7. Write AppKeyChallenge (0x02 + token + 0x02)
8. Read ChallengeReply (0x03 + tokenHash + challenge)
9. Write HashFromDisplay (0x04 + computed hash)
10. Read StatusReply (0x05 01 02) - authenticated and needs pairing
11. Certificate Exchange Phase 0: Write 0x0B00
12. Certificate Exchange Phase 1: Write 0x0B01
13. Certificate Exchange Phase 2: Write 0x0B02
14. Write ProofOfPossession (0x0C + challenge)
15. Read ProofOfPossession response
16. Write KeepAlive (0x06 19) - 25 seconds
17. Write BondRequest (0x07)
18. Read PairRequestRx (0x08 01)
19. Normal session continues...
```

### G7 Connection Sequence (Already Paired)

```
1. Enable notifications on Authentication characteristic
2. Write AppKeyChallenge (0x02 + token + 0x02)
3. Read ChallengeReply (0x03 + tokenHash + challenge)
4. Write HashFromDisplay (0x04 + computed hash)
5. Read StatusReply (0x05 01 01) - authenticated and bonded
6. Enable notifications on Control characteristic
7. Read EGV (0x4E) - glucose data arrives automatically
8. Optionally request Backfill (0x59)
```

---

## Transmitter Identification

### G5 Transmitter IDs
- Format: 5 alphanumeric characters
- Example: `80XXX`, `40XXX`

### G6 Transmitter IDs
- Format: 6 alphanumeric characters
- Prefixes:
  - `80xxxx` - Standard G6
  - `8Gxxxx`, `8Hxxxx`, `8Jxxxx`, `8Lxxxx`, `8Rxxxx` - G6+ variants

### G7 Sensor IDs
- Format: `DX` + identifier
- Advertised name: `DXCM` + suffix

**Detection Logic**:
```javascript
const isG6 = transmitterID.startsWith('8');
const isG6Plus = ['8G', '8H', '8J', '8L', '8R'].includes(transmitterID.slice(0, 2));
```

**Source**: `externals/xdrip-js/lib/transmitter.js:394-396`

---

## G7 J-PAKE Authentication

The G7 uses J-PAKE (Password Authenticated Key Exchange by Juggling) for initial pairing:

### J-PAKE Overview

1. **Phase 0 (0x0A00)**: Exchange initial Schnorr ZKP commitments
2. **Phase 1 (0x0A01)**: Exchange additional commitments
3. **Phase 2 (0x0A02)**: Derive shared secret

### Implementation Notes

- Uses elliptic curve cryptography (mbedtls/TF-PSA-Crypto)
- Pairing code: 4-digit code from sensor packaging
- After J-PAKE, standard AES authentication follows
- Certificate exchange establishes long-term trust

### References

- [J-PAKE Wikipedia](https://en.wikipedia.org/wiki/Password_Authenticated_Key_Exchange_by_Juggling)
- [mbedTLS ecjpake.h](https://github.com/Mbed-TLS/TF-PSA-Crypto/blob/development/drivers/builtin/include/mbedtls/private/ecjpake.h)
- [xDrip+ keks library](https://github.com/NightscoutFoundation/xDrip/tree/master/libkeks)

**Source**: `externals/DiaBLE/DiaBLE Playground.swiftpm/DexcomG7.swift:213-230`

---

## Dual Slot Architecture (G6 Only)

G6 transmitters support two simultaneous Bluetooth connections:

| Slot | Default Use | Description |
|------|-------------|-------------|
| Slot 1 | Receiver/Pump | Primary slot for Dexcom receiver or pump |
| Slot 2 | xDrip | Secondary slot for third-party apps |

**Alternate Bluetooth Channel**: Controlled by `endByte` in AuthRequestTx:
- `0x02` = Default slot
- Different value = Alternate slot

**Source**: `externals/xdrip-js/lib/transmitter.js:73`

---

## Session Management

### Session Start (0x26/0x27)

**SessionStartTxMessage**:
```
Offset  Length  Type     Field
0       1       UInt8    Opcode (0x26)
1       4       UInt32   Start time (seconds since activation)
5       4       UInt32   Seconds since Unix epoch
9       4       G6: Sensor code (4 digits)
9       2       CRC-16
```

**SessionStartRxMessage**:
```
Offset  Length  Type     Field
0       1       UInt8    Opcode (0x27)
1       1       UInt8    Status
2       1       UInt8    Received
3       4       UInt32   Requested start time
7       4       UInt32   Session start time
11      4       UInt32   Transmitter time
15      2       UInt16   CRC-16
```

### Session Stop (0x28/0x29)

**SessionStopTxMessage**:
```
Offset  Length  Type     Field
0       1       UInt8    Opcode (0x28)
1       4       UInt32   Stop time
5       2       UInt16   CRC-16
```

---

## Known Gaps and Limitations

### GAP-BLE-001: G7 J-PAKE Full Specification
The J-PAKE exchange phases (0x0A00-0x0A02) are not fully documented. The mathematical operations for key derivation are implemented in native libraries (keks, mbedtls).

### GAP-BLE-002: G7 Certificate Chain
The certificate exchange (0x0B) and proof of possession (0x0C) protocols require further documentation.

### GAP-BLE-003: Service B Purpose
The secondary Bluetooth service (F8084532-...) and its characteristics are not well understood.

### GAP-BLE-004: Anubis Transmitters
Extended commands for "Anubis" G6 transmitters (maxRuntimeDays > 120) use opcodes 0x3B and 0xF0xx that are not fully documented.

### GAP-BLE-005: G7 Encryption
The encryption info (0x38) and encryption status (0x0F) commands for G7 are present but data format is unclear.

---

## Cross-References

- **Terminology Matrix**: See `mapping/cross-project/terminology-matrix.md` for BLE Protocol Models section
- **CGM Data Sources**: See `docs/10-domain/cgm-data-sources-deep-dive.md` for data flow context
- **Requirements**: See `traceability/requirements.md` for REQ-BLE-xxx

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | AID Alignment Workspace | Initial comprehensive specification |
