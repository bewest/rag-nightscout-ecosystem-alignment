# Dexcom G7 BLE Protocol Specification

This document provides a comprehensive specification of the Dexcom G7 Bluetooth Low Energy (BLE) communication protocol, compiled from analysis of DiaBLE, xDrip+, xDrip4iOS, and G7SensorKit implementations.

## Table of Contents

- [Overview](#overview)
- [BLE Service and Characteristics](#ble-service-and-characteristics)
- [Opcode Reference](#opcode-reference)
- [Authentication Protocol](#authentication-protocol)
- [Message Formats](#message-formats)
- [State Machine](#state-machine)
- [Glucose Data](#glucose-data)
- [Backfill Protocol](#backfill-protocol)
- [Implementation Status](#implementation-status)

---

## Overview

The Dexcom G7 CGM system uses Bluetooth Low Energy for communication between the sensor/transmitter and receiver applications. Unlike the G5/G6 which used simple challenge-response authentication, the G7 implements a more complex authentication scheme based on the J-PAKE (Password Authenticated Key Exchange by Juggling) protocol.

### Key Differences from G6

| Aspect | G6 | G7 |
|--------|----|----|
| Authentication | Simple challenge-response | J-PAKE + Certificate Exchange |
| Encryption | AES-CTR on calibration data | Shared key from J-PAKE |
| Glucose Data | Encrypted | **Unencrypted** (readable after auth) |
| Sensor Life | 10 days + 12h grace | 10 days (standard) or 15 days |
| Warmup | 2 hours | ~30 minutes |
| Transmitter | Separate, reusable | Integrated, disposable |

### Critical Insight

**The glucose data appears to be unencrypted in observed BLE traffic.** Based on analysis of DiaBLE BLE traces and the G7SensorKit/xDrip message parsers, the 5-minute realtime values and backfill stream are readable in cleartext after authentication completes. The primary complexity is in the initial J-PAKE authentication handshake required to establish a trusted connection. (Note: This observation is based on available trace data; Dexcom may implement encryption in specific modes or firmware versions.)

---

## BLE Service and Characteristics

### Primary Service UUID

```
F8083532-849E-531C-C594-30F1F86A4EA5
```

This is the same service family UUID used across Dexcom transmitters (G5/G6/G7/ONE).

### Characteristics

| Name | UUID Suffix | Properties | Purpose |
|------|-------------|------------|---------|
| Authentication | 3535 | Write, Notify/Indicate | Auth commands (J-PAKE, cert exchange) |
| Control | 3534 | Write, Notify | Data commands (EGV, backfill, battery) |
| Backfill | 3536 | Notify | Streaming backfill data packets |
| ExtraData | 3538 | Write, Notify | Large data transfer (certificates, J-PAKE payloads) |

### Full UUIDs

```
Authentication: F8083535-849E-531C-C594-30F1F86A4EA5
Control:        F8083534-849E-531C-C594-30F1F86A4EA5
Backfill:       F8083536-849E-531C-C594-30F1F86A4EA5
ExtraData:      F8083538-849E-531C-C594-30F1F86A4EA5
```

---

## Opcode Reference

### Authentication Opcodes (Characteristic 3535)

| Opcode | Hex | Name | Direction | Description |
|--------|-----|------|-----------|-------------|
| 0x01 | 01 | txIdChallenge | Tx | Transmitter ID challenge |
| 0x02 | 02 | appKeyChallenge | Tx | Application key challenge |
| 0x03 | 03 | challengeReply | Rx | Challenge response from sensor |
| 0x04 | 04 | hashFromDisplay | Tx | Hash derived from display code |
| 0x05 | 05 | statusReply | Rx | Authentication status response |
| 0x06 | 06 | keepConnectionAlive | Tx | Keep-alive with timeout byte |
| 0x07 | 07 | requestBond | Tx | Request Bluetooth bonding |
| 0x08 | 08 | requestBondResponse | Rx | Bond request response |
| 0x09 | 09 | disconnect | Tx | Request disconnect |
| 0x0A | 0A | exchangePakePayload | Tx/Rx | J-PAKE round data exchange |
| 0x0B | 0B | certificateExchange | Tx/Rx | Certificate info exchange |
| 0x0C | 0C | proofOfPossession | Tx/Rx | Sign challenge / verify |
| 0x0D | 0D | authStatus | Tx/Rx | Authentication status query |
| 0x0F | 0F | encryptionStatus | Tx/Rx | Encryption status |

### Control Opcodes (Characteristic 3534)

| Opcode | Hex | Name | Direction | Description |
|--------|-----|------|-----------|-------------|
| 0x22 | 22 | batteryStatus | Tx/Rx | Battery voltage and runtime |
| 0x28 | 28 | stopSession | Tx | Stop sensor session |
| 0x32 | 32 | calibrationBounds | Tx/Rx | Calibration parameters |
| 0x34 | 34 | calibrate | Tx | Send calibration value |
| 0x38 | 38 | encryptionInfo | Tx/Rx | Encryption info request |
| 0x4A | 4A | transmitterVersion | Tx/Rx | Firmware version info |
| 0x4E | 4E | egv | Tx/Rx | Estimated Glucose Value |
| 0x51 | 51 | diagnosticData | Tx/Rx | Diagnostic data stream |
| 0x52 | 52 | transmitterVersionExtended | Tx/Rx | Extended version info |
| 0x59 | 59 | backfill | Tx/Rx | Request historical glucose |
| 0xEA | EA | bleControl | Tx/Rx | BLE whitelist/stream settings |

---

## Authentication Protocol

### Overview

G7 authentication consists of five phases:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    G7 Authentication Flow                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Phase 1: J-PAKE Exchange (opcode 0x0A)                             │
│  ├── Round 0: Exchange initial key material                         │
│  ├── Round 1: Exchange second key material                          │
│  └── Round 2: Exchange final key material + derive shared key       │
│                                                                      │
│  Phase 2: Traditional Auth (opcodes 0x02-0x05)                      │
│  ├── Send app key challenge (0x02)                                  │
│  ├── Receive challenge reply (0x03)                                 │
│  ├── Send hash from display (0x04)                                  │
│  └── Receive status reply (0x05) - authenticated=1, bonded=1/2     │
│                                                                      │
│  Phase 3: Certificate Exchange (opcode 0x0B)                        │
│  ├── Request certificate part A (0x0B 00)                           │
│  ├── Request certificate part B (0x0B 01)                           │
│  └── Final certificate exchange (0x0B 02)                           │
│                                                                      │
│  Phase 4: Proof of Possession (opcode 0x0C)                         │
│  ├── Send 16-byte challenge                                         │
│  ├── Receive signed response                                        │
│  └── Send verification signature                                    │
│                                                                      │
│  Phase 5: Bonding Complete                                          │
│  ├── Send keepConnectionAlive (0x06 + timeout)                      │
│  ├── Send requestBond (0x07)                                        │
│  └── Receive bondResponse (0x08 01)                                 │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### J-PAKE Protocol Details

J-PAKE (Password Authenticated Key Exchange by Juggling) is a cryptographic protocol that allows two parties to establish a shared secret using a low-entropy password without exposing the password to offline dictionary attacks.

**References:**
- RFC 8236: J-PAKE: Password-Authenticated Key Exchange by Juggling
- IEEE P1363.2: Password-Based Cryptography
- https://ia.cr/2010/190

**Elliptic Curve Parameters:**
- Curve: secp256r1 (NIST P-256)
- Field size: 256 bits (32 bytes)
- Packet size: 160 bytes (5 × 32 bytes)

**Password Derivation:**
```
password = PREFIX_BYTES + sensor_code.getBytes("UTF-8")
```
Where `sensor_code` is the 6-character code printed on the sensor.

### Detailed Pairing Sequence (from BLE trace)

```
# Phase 1: J-PAKE Exchange
# Enable notifications for 3535 and 3538

write  3535  0A 00                    # Start J-PAKE round 0
notify 3538  [20 bytes] × 6           # Receive ~120 bytes sensor key material
notify 3535  0A 00 00                 # Round 0 status
notify 3538  [20 bytes] × 2           # Additional data (~40 bytes)
write  3538  [20 bytes] × 8           # Send our round 0 response (~160 bytes)

write  3535  0A 01                    # Start J-PAKE round 1
notify 3538  [20 bytes] × 6           # Receive sensor round 1 data
notify 3535  0A 00 01                 # Round 1 status
notify 3538  [20 bytes] × 2           # Additional data
write  3538  [20 bytes] × 8           # Send our round 1 response

write  3535  0A 02                    # Start J-PAKE round 2
notify 3538  [20 bytes] × 6           # Receive sensor round 2 data
notify 3535  0A 00 02                 # Round 2 status
notify 3538  [20 bytes] × 2           # Additional data
write  3538  [20 bytes] × 8           # Send our round 2 response

# Phase 2: Traditional Auth
write  3535  02 [8 bytes] 02          # App key challenge
notify 3535  03 [16 bytes]            # Challenge reply
write  3535  04 [8 bytes]             # Hash from display
notify 3535  05 01 02                 # Status: authenticated=1, bonded=2

# Phase 3: Certificate Exchange
write  3535  0B 00 [4 bytes]          # Request cert part A
notify 3538  [20 bytes] × 6           # Stream data
notify 3535  0B 00 00 [4 bytes]       # Cert A status
notify 3538  [20 bytes] × 18 + [12 bytes]  # Cert A data (~372 bytes)
write  3538  [20 bytes] × 24 + [14 bytes]  # Our cert A response

write  3535  0B 01 [4 bytes]          # Request cert part B
notify 3538  [20 bytes] × 6           # Stream data
notify 3535  0B 00 01 [4 bytes]       # Cert B status
notify 3538  [20 bytes] × 16 + [17 bytes]  # Cert B data
write  3538  [20 bytes] × 23 + [6 bytes]   # Our cert B response

write  3535  0B 02 00 00 00 00        # Final cert exchange
notify 3535  0B 00 02 00 00 00 00     # Confirmation

# Phase 4: Proof of Possession
write  3535  0C [16 bytes]            # Send challenge
notify 3538  [20 bytes] × 3 + [4 bytes]   # Receive signature
notify 3535  0C 00 [16 bytes]         # Challenge response
write  3538  [20 bytes] × 3 + [4 bytes]   # Send our signature

# Phase 5: Bonding
write  3535  06 19                    # Keep alive (25 seconds)
notify 3535  06 00                    # Acknowledged
write  3535  07                       # Request bond
notify 3535  07 00                    # Bond request accepted
notify 3535  08 01                    # Bond complete

# Now authenticated - can request data
enable notifications for 3534
write  3534  4A                       # Request transmitter version
notify 3534  4A 00 [18 bytes]         # Version response
write  3534  4E                       # Request EGV (glucose)
notify 3534  4E 00 [17 bytes]         # Glucose response
```

### Already-Bonded Connection Sequence

When reconnecting to an already-paired sensor:

```
# Abbreviated auth
write  3535  01 00                    # Tx ID challenge
write  3535  02 [8 bytes] 02          # App key challenge
notify 3535  03 [16 bytes]            # Challenge reply
write  3535  04 [8 bytes]             # Hash from display
notify 3535  05 01 01                 # Status: authenticated=1, bonded=1

# Proceed directly to data
enable notifications for 3534
write  3534  4E                       # Request EGV
notify 3534  4E 00 [17 bytes]         # Glucose data
```

---

## Message Formats

### EGV (Glucose) Message - Opcode 0x4E

**Request:** `4E`

**Response (19 bytes):**

```
Offset  Size  Field                Description
------  ----  -------------------  ----------------------------------
0       1     opcode               0x4E
1       1     status               TransmitterResponseCode
2       4     messageTimestamp     Seconds since sensor activation
6       2     sequence             Reading sequence number
8       2     reserved             Unknown/padding
10      2     age                  Seconds since this reading
12      2     glucose              Glucose value (bits 0-11) + flags
14      1     algorithmState       Calibration/algorithm state
15      1     trend                Trend rate (signed, ÷10 for mg/dL/min)
16      2     predicted            Predicted glucose (bits 0-11)
18      1     calibration          Calibration flags
```

**Example:**
```
4E 00 D5070000 0900 0001 0500 6100 06 01 FFFF 0E
│  │  │        │    │    │    │    │  │  │    └── calibration flags
│  │  │        │    │    │    │    │  │  └─────── predicted (0xFFFF = none)
│  │  │        │    │    │    │    │  └────────── trend: +0.1 mg/dL/min
│  │  │        │    │    │    │    └───────────── algo state: 6
│  │  │        │    │    │    └────────────────── glucose: 97 mg/dL
│  │  │        │    │    └─────────────────────── age: 5 seconds
│  │  │        │    └──────────────────────────── reserved
│  │  │        └───────────────────────────────── sequence: 9
│  │  └────────────────────────────────────────── timestamp: 2005 sec
│  └───────────────────────────────────────────── status: success
└──────────────────────────────────────────────── opcode: EGV
```

**Glucose Field Decoding:**
```
glucose_value = glucoseBytes & 0x0FFF
display_only = (data[18] & 0x10) != 0
```

**Trend Decoding:**
```
if (trend_byte == 0x7F):
    trend = None  # No trend available
else:
    trend = (signed int8)trend_byte / 10.0  # mg/dL per minute
```

### Backfill Message - Opcode 0x59

**Request (9 bytes):**
```
59 [startTime:4] [endTime:4]
```
Times are in seconds since sensor activation.

**Control Response (19 bytes):**
```
Offset  Size  Field               Description
------  ----  ------------------  ----------------------------------
0       1     opcode              0x59
1       1     status              0x00 = success, 0x01 = no record
2       1     result              BackfillResult enum
3       4     length              Total buffer length in bytes
7       2     crc                 CRC16 of backfill data
9       2     firstSequence       First sequence number
11      4     firstTimestamp      First reading timestamp
15      4     lastTimestamp       Last reading timestamp
```

**Backfill Data Packets (9 bytes each, on characteristic 3536):**
```
Offset  Size  Field               Description
------  ----  ------------------  ----------------------------------
0       3     timestamp           Seconds since activation (24-bit)
3       1     reserved            Padding
4       2     glucose             Glucose value (bits 0-11)
6       1     algorithmState      Calibration state
7       1     flags               Display-only flag in bit 4
8       1     trend               Trend rate (signed, ÷10)
```

**Example Backfill Packet:**
```
45A100 00 9600 06 0F FC
│      │  │    │  │  └── trend: -0.4 mg/dL/min (0xFC = -4 signed)
│      │  │    │  └───── flags
│      │  │    └──────── algo state: 6 (sessionRunning)
│      │  └───────────── glucose: 150 mg/dL (0x0096)
│      └──────────────── reserved
└─────────────────────── timestamp: 41285 seconds
```

### Transmitter Version - Opcode 0x4A

**Request:** `4A`

**Response (20 bytes):**
```
Offset  Size  Field               Description
------  ----  ------------------  ----------------------------------
0       1     opcode              0x4A
1       1     status              Response code
2       1     versionMajor        Firmware major version
3       1     versionMinor        Firmware minor version
4       1     versionRevision     Firmware revision
5       1     versionBuild        Firmware build number
6       4     softwareNumber      Software number
10      4     siliconVersion      Silicon/chip version
14      6     serialNumber        Device serial (little-endian)
```

### Extended Version - Opcode 0x52

**Request:** `52`

**Response (15 bytes):**
```
Offset  Size  Field               Description
------  ----  ------------------  ----------------------------------
0       1     opcode              0x52
1       1     status              Response code
2       4     sessionLength       Max session in seconds
6       2     warmupLength        Warmup period in seconds
8       4     algorithmVersion    Algorithm version
12      1     hardwareVersion     Hardware revision
13      2     maxLifetimeDays     Maximum sensor lifetime in days
```

**Session Length Examples:**
- 10-day G7: 907200 seconds (0x000DD7C0)
- 15-day G7: 1339200 seconds (0x00146F40)

### Battery Status - Opcode 0x22

**Request:** `22`

**Response (8 bytes):**
```
Offset  Size  Field               Description
------  ----  ------------------  ----------------------------------
0       1     opcode              0x22
1       1     status              Response code
2       2     voltageA            Static voltage (mV)
4       2     voltageB            Dynamic voltage (mV)
6       1     runtimeDays         Days of runtime
7       1     temperature         Temperature (signed, Celsius)
```

### Auth Status Response - Opcode 0x05

**Response (3 bytes):**
```
Offset  Size  Field               Description
------  ----  ------------------  ----------------------------------
0       1     opcode              0x05
1       1     authenticated       0=no, 1=yes
2       1     bonded              0=no, 1=yes, 2=needs pairing, 3=refresh
```

---

## State Machine

### Algorithm States

The `algorithmState` field indicates sensor calibration status:

| Value | State | Description | Glucose Usable |
|-------|-------|-------------|----------------|
| 0x01 | stopped | Session stopped | No |
| 0x02 | warmup | Sensor warming up | No |
| 0x03 | excessNoise | Too much noise | No |
| 0x04 | firstOfTwoBGsNeeded | Need calibration (legacy) | No |
| 0x05 | secondOfTwoBGsNeeded | Need calibration (legacy) | No |
| 0x06 | sessionRunning | Normal operation | **Yes** |
| 0x07 | calibrationNeeded | Calibration needed | No |
| 0x08 | calibrationError1 | Calibration error | No |
| 0x09 | calibrationError2 | Calibration error | No |
| 0x0A | calibrationLinearityFitFailure | Cal fit failed | No |
| 0x0B | sensorFailedDueToCountsAberration | Sensor failed | No |
| 0x0C | sensorFailedDueToResidualAberration | Sensor failed | No |
| 0x0D | outOfCalibrationDueToOutlier | Out of calibration | No |
| 0x0E | outlierCalibrationRequest | Need recalibration | No |
| 0x0F | sessionExpired | Session ended | No |
| 0x10 | sessionFailedDueToUnrecoverableError | Fatal error | No |
| 0x11 | sessionFailedDueToTransmitterError | Tx error | No |
| 0x12 | temporarySensorIssue | Temporary issue | No |
| 0x13 | sensorFailedDueToProgressiveSensorDecline | Sensor decline | No |
| 0x14 | sensorFailedDueToHighCountsAberration | Sensor failed | No |
| 0x15 | sensorFailedDueToLowCountsAberration | Sensor failed | No |
| 0x16 | sensorFailedDueToRestart | Restart failed | No |
| 0x50 | sensorOK | OK (alternate) | **Yes** |
| 0x51 | sensorOK2 | OK (alternate) | **Yes** |
| 0x52 | sensorOK3 | OK (alternate) | **Yes** |
| 0x53 | sensorOK4 | OK (alternate) | **Yes** |
| 0x54 | sensorOK5 | OK (alternate) | **Yes** |

### Transmitter Response Codes

| Value | Code | Description |
|-------|------|-------------|
| 0 | success | Operation completed successfully |
| 1 | notPermitted | Operation not permitted |
| 2 | notFound | Resource not found |
| 3 | ioError | I/O error |
| 4 | badHandle | Invalid handle |
| 5 | tryLater | Busy, try again later |
| 6 | outOfMemory | Out of memory |
| 7 | noAccess | Access denied |
| 8 | segfault | Memory access violation |
| 9 | busy | Device busy |
| 10 | badArgument | Invalid argument |
| 11 | noSpace | No space available |
| 12 | badRange | Value out of range |
| 13 | notImplemented | Feature not implemented |
| 14 | timeout | Operation timed out |
| 15 | protocolError | Protocol error |
| 16 | unexpectedError | Unexpected error |

---

## Implementation Status

### Cross-Project Feature Matrix

| Feature | xDrip Android | DiaBLE | G7SensorKit (Loop/Trio) | xDrip4iOS |
|---------|---------------|--------|-------------------------|-----------|
| J-PAKE Auth | ✅ Full (libkeks) | 🔄 Partial | ❌ None | ❌ None |
| Certificate Exchange | ✅ Full | 🔄 Trace only | ❌ None | ❌ None |
| Proof of Possession | ✅ Full | 🔄 Trace only | ❌ None | ❌ None |
| Bonding | ✅ Full | 🔄 Partial | ❌ None | ❌ None |
| Glucose (EGV) | ✅ Full | ✅ Full | ✅ Full | ✅ Full |
| Backfill | ✅ Full | ✅ Full | ✅ Full | ✅ Full |
| Battery Status | ✅ Full | ✅ Full | ❌ None | ✅ Full |
| Calibration | ✅ Full | 🔄 Read only | ❌ None | ❌ None |
| **Standalone Mode** | ✅ Yes | ❌ No | ❌ No | ❌ No |

**Legend:**
- ✅ Full: Complete implementation
- 🔄 Partial: Incomplete or read-only
- ❌ None: Not implemented

### Key Insight

**xDrip Android is the only open-source project with complete standalone G7 support** through its `libkeks` library. All iOS projects (DiaBLE, G7SensorKit, xDrip4iOS) currently require the official Dexcom app running in the background to complete authentication.

---

## References

### Source Files Analyzed

| Project | File | Purpose |
|---------|------|---------|
| DiaBLE | `DexcomG7.swift` | BLE trace documentation, opcode definitions |
| DiaBLE | `Dexcom.swift` | Base transmitter class, algorithm states |
| xDrip Android | `libkeks/Calc.java` | J-PAKE implementation |
| xDrip Android | `libkeks/Context.java` | Authentication context |
| xDrip Android | `libkeks/Curve.java` | Elliptic curve parameters |
| xDrip Android | `cgm/dex/g7/EGlucoseRxMessage.java` | Glucose message parsing |
| G7SensorKit | `G7GlucoseMessage.swift` | Glucose message format |
| G7SensorKit | `G7BackfillMessage.swift` | Backfill message format |
| G7SensorKit | `G7Opcode.swift` | Control opcodes |

### External References

- J-PAKE Protocol: https://ia.cr/2010/190
- IEEE P1363.2: Password-Based Cryptography
- mbedtls ecjpake.h: https://github.com/Mbed-TLS/TF-PSA-Crypto/blob/development/drivers/builtin/include/mbedtls/ecjpake.h
- Dexcom Developer: https://developer.dexcom.com/

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Initial specification from cross-project analysis |
