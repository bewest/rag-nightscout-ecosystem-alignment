# Dexcom BLE Protocol Documentation

This document describes the Bluetooth Low Energy (BLE) protocol used by xdrip-js to communicate with Dexcom G5 and G6 transmitters. The protocol was reverse-engineered from iOS Dexcom app communications.

## BLE Services and Characteristics

### Service UUIDs

From `lib/bluetooth-services.js`:

| Service | UUID | Purpose |
|---------|------|---------|
| DeviceInfo | `180A` | Standard BLE device information |
| Advertisement | `FEBC` | Transmitter advertisement/discovery |
| CGMService | `F8083532-849E-531C-C594-30F1F86A4EA5` | Main CGM communication |
| ServiceB | `F8084532-849E-531C-C594-30F1F86A4EA5` | Secondary service (unused) |

### CGM Service Characteristics

| Characteristic | UUID | Purpose |
|----------------|------|---------|
| Communication | `F8083533-849E-531C-C594-30F1F86A4EA5` | General communication |
| Control | `F8083534-849E-531C-C594-30F1F86A4EA5` | Command/response messages |
| Authentication | `F8083535-849E-531C-C594-30F1F86A4EA5` | Auth handshake |
| Backfill | `F8083536-849E-531C-C594-30F1F86A4EA5` | Historical data retrieval |

## Message Opcode Summary

### Authentication Messages (via Authentication Characteristic)

| Opcode | Direction | Message | File |
|--------|-----------|---------|------|
| `0x01` | Tx | AuthRequestTxMessage | `auth-request-tx-message.js` |
| `0x03` | Rx | AuthChallengeRxMessage | `auth-challenge-rx-message.js` |
| `0x04` | Tx | AuthChallengeTxMessage | `auth-challenge-tx-message.js` |
| `0x05` | Rx | AuthStatusRxMessage | `auth-status-rx-message.js` |
| `0x06` | Tx | KeepAliveTxMessage | `keep-alive-tx-message.js` |
| `0x07` | Tx | BondRequestTxMessage | `bond-request-tx-message.js` |
| `0x08` | Rx | BondRequestRxMessage | `bond-request-rx-message.js` |

### Control Messages (via Control Characteristic)

| Opcode | Direction | Message | File |
|--------|-----------|---------|------|
| `0x09` | Tx | DisconnectTxMessage | `disconnect-tx-message.js` |
| `0x20` | Tx | VersionRequestTxMessage (v0) | `version-request-tx-message.js` |
| `0x21` | Rx | VersionRequestRx0Message | `version-request-rx-0-message.js` |
| `0x22` | Tx | BatteryStatusTxMessage | `battery-status-tx-message.js` |
| `0x23` | Rx | BatteryStatusRxMessage | `g5/` or `g6/battery-status-rx-message.js` |
| `0x24` | Tx | TransmitterTimeTxMessage | `transmitter-time-tx-message.js` |
| `0x25` | Rx | TransmitterTimeRxMessage | `transmitter-time-rx-message.js` |
| `0x26` | Tx | SessionStartTxMessage | `g5/` or `g6/session-start-tx-message.js` |
| `0x27` | Rx | SessionStartRxMessage | `session-start-rx-message.js` |
| `0x28` | Tx | SessionStopTxMessage | `session-stop-tx-message.js` |
| `0x29` | Rx | SessionStopRxMessage | `session-stop-rx-message.js` |
| `0x2e` | Tx | SensorTxMessage | `sensor-tx-message.js` |
| `0x2f` | Rx | SensorRxMessage | `sensor-rx-message.js` |
| `0x30` | Tx | GlucoseTxMessage (G5) | `glucose-tx-message.js` |
| `0x31` | Rx | GlucoseRxMessage (G5) | `glucose-rx-message.js` |
| `0x32` | Tx | CalibrationDataTxMessage | `calibration-data-tx-message.js` |
| `0x33` | Rx | CalibrationDataRxMessage | `g5/` or `g6/calibration-data-rx-message.js` |
| `0x34` | Tx | CalibrateGlucoseTxMessage | `calibrate-glucose-tx-message.js` |
| `0x35` | Rx | CalibrateGlucoseRxMessage | `calibrate-glucose-rx-message.js` |
| `0x42` | Tx | ResetTxMessage | `transmitter-reset-tx-message.js` |
| `0x43` | Rx | ResetRxMessage | `transmitter-reset-rx-message.js` |
| `0x4a` | Tx | VersionRequestTxMessage (v1) | `version-request-tx-message.js` |
| `0x4b` | Rx | VersionRequestRx1Message | `version-request-rx-1-message.js` |
| `0x4e` | Tx | GlucoseTxMessage (G6) | `glucose-tx-message.js` |
| `0x4f` | Rx | GlucoseRxMessage (G6) | `glucose-rx-message.js` |
| `0x50` | Tx | BackfillTxMessage | `backfill-tx-message.js` |
| `0x51` | Rx | BackfillRxMessage | `backfill-rx-message.js` |
| `0x52` | Tx | VersionRequestTxMessage (v2) | `version-request-tx-message.js` |
| `0x53` | Rx | VersionRequestRx2Message | `version-request-rx-2-message.js` |

### G6 Anubis-Specific Messages

| Opcode | Direction | Message | File |
|--------|-----------|---------|------|
| `0x3b` | Tx | AnubisTxStatusMessage | `g6/anubis-tx-status-message.js` |
| `0xf080` | Tx | AnubisTxResetDefaultMessage | `g6/anubis-tx-reset-default-message.js` |
| `0xf080` | Tx | AnubisTxResetExtendedMessage | `g6/anubis-tx-reset-extended-message.js` |

## Authentication Flow

The authentication handshake uses AES-128-ECB encryption with the transmitter ID.

```
┌──────────────────┐                           ┌──────────────────┐
│     Client       │                           │   Transmitter    │
└────────┬─────────┘                           └────────┬─────────┘
         │                                              │
         │  1. AuthRequestTxMessage (0x01)              │
         │  [opcode][singleUseToken(8)][endByte]        │
         │─────────────────────────────────────────────▶│
         │                                              │
         │  2. AuthChallengeRxMessage (0x03)            │
         │  [opcode][tokenHash(8)][challenge(8)]        │
         │◀─────────────────────────────────────────────│
         │                                              │
         │  Client verifies tokenHash matches           │
         │  Client computes challengeHash               │
         │                                              │
         │  3. AuthChallengeTxMessage (0x04)            │
         │  [opcode][challengeHash(8)]                  │
         │─────────────────────────────────────────────▶│
         │                                              │
         │  4. AuthStatusRxMessage (0x05)               │
         │  [opcode][authenticated][bonded]             │
         │◀─────────────────────────────────────────────│
         │                                              │
         │  If not bonded:                              │
         │                                              │
         │  5. KeepAliveTxMessage (0x06)                │
         │  [opcode][time(25 seconds)]                  │
         │─────────────────────────────────────────────▶│
         │                                              │
         │  6. BondRequestTxMessage (0x07)              │
         │  [opcode]                                    │
         │─────────────────────────────────────────────▶│
         │                                              │
         │  BLE pairing completes                       │
         │                                              │
```

### Encryption Details

From `lib/transmitter.js`:

```javascript
function encrypt(buffer, id) {
  const algorithm = 'aes-128-ecb';
  const cipher = crypto.createCipheriv(algorithm, `00${id}00${id}`, '');
  const encrypted = Buffer.concat([cipher.update(buffer), cipher.final()]);
  return encrypted;
}

function calculateHash(data, id) {
  // data must be 8 bytes
  const doubleData = Buffer.allocUnsafe(16);
  doubleData.fill(data, 0, 8);
  doubleData.fill(data, 8, 16);
  const encrypted = encrypt(doubleData, id);
  return Buffer.allocUnsafe(8).fill(encrypted);
}
```

The encryption key is constructed from the 6-character transmitter ID: `00${id}00${id}` (16 bytes total).

## Message Formats

### CRC-16 XMODEM

All control messages include a 2-byte CRC-16 XMODEM checksum at the end.

### AuthRequestTxMessage (0x01)

```
+--------+-------------------+----------+
| [0]    | [1-8]             | [9]      |
+--------+-------------------+----------+
| opcode | singleUseToken    | endByte  |
+--------+-------------------+----------+
| 0x01   | random 8 bytes    | 0x02/01  |
+--------+-------------------+----------+
```

- `endByte`: `0x02` for standard channel, `0x01` for alternate (receiver) channel

### AuthChallengeRxMessage (0x03)

```
+--------+-------------------+-------------------+
| [0]    | [1-8]             | [9-16]            |
+--------+-------------------+-------------------+
| opcode | tokenHash         | challenge         |
+--------+-------------------+-------------------+
| 0x03   | 8 bytes           | 8 bytes           |
+--------+-------------------+-------------------+
```

### AuthStatusRxMessage (0x05)

```
+--------+--------------+--------+
| [0]    | [1]          | [2]    |
+--------+--------------+--------+
| opcode | authenticated| bonded |
+--------+--------------+--------+
| 0x05   | 0x01=yes     | 0x01   |
+--------+--------------+--------+
```

### TransmitterTimeRxMessage (0x25)

```
+--------+--------+-------------+-----------------+---------+-------+
| [0]    | [1]    | [2-5]       | [6-9]           | [10-13] | [14-15]|
+--------+--------+-------------+-----------------+---------+-------+
| opcode | status | currentTime | sessionStartTime| unknown | CRC   |
+--------+--------+-------------+-----------------+---------+-------+
| 0x25   | 0x00   | UInt32LE    | UInt32LE        | -       | -     |
+--------+--------+-------------+-----------------+---------+-------+
```

- `currentTime`: Seconds since transmitter activation
- `sessionStartTime`: Seconds since transmitter activation when session started (0xFFFFFFFF if no session)

### GlucoseRxMessage (0x31/0x4F)

```
+--------+--------+----------+-----------+---------+-------+-------+-------+
| [0]    | [1]    | [2-5]    | [6-9]     | [10-11] | [12]  | [13]  | [14-15]|
+--------+--------+----------+-----------+---------+-------+-------+-------+
| opcode | status | sequence | timestamp | glucose | state | trend | CRC   |
+--------+--------+----------+-----------+---------+-------+-------+-------+
| 0x31   | 0x00   | UInt32LE | UInt32LE  | UInt16LE| UInt8 | Int8  | -     |
+--------+--------+----------+-----------+---------+-------+-------+-------+
```

- `glucose`: Lower 12 bits = glucose value in mg/dL, bit 12+ = display only flag
- `state`: Session/calibration state (see data-models.md)
- `trend`: Rate of change in mg/dL per 10 minutes (signed)

Example:
```
31 00 0c3e0000 e41c6500 6c00 06 00 0320
│  │  │        │        │    │  │  └── CRC
│  │  │        │        │    │  └── trend: 0
│  │  │        │        │    └── state: 0x06 (OK)
│  │  │        │        └── glucose: 108 (0x6c)
│  │  │        └── timestamp: 6626532
│  │  └── sequence: 15884
│  └── status: 0x00 (OK)
└── opcode: 0x31
```

### SensorRxMessage (0x2F)

```
+--------+--------+-----------+------------+----------+-------+
| [0]    | [1]    | [2-5]     | [6-9]      | [10-13]  | [14-15]|
+--------+--------+-----------+------------+----------+-------+
| opcode | status | timestamp | unfiltered | filtered | CRC   |
+--------+--------+-----------+------------+----------+-------+
| 0x2f   | 0x00   | UInt32LE  | UInt32LE   | UInt32LE | -     |
+--------+--------+-----------+------------+----------+-------+
```

G6 transmitters apply a scaling factor:
- 16-byte message: `scale = 34`
- 18-byte message (float format): `scale = 35`

### CalibrateGlucoseTxMessage (0x34)

```
+--------+---------+----------------------+-------+
| [0]    | [1-2]   | [3-6]                | [7-8] |
+--------+---------+----------------------+-------+
| opcode | glucose | dexcomTimeInSeconds  | CRC   |
+--------+---------+----------------------+-------+
| 0x34   | UInt16LE| UInt32LE             | -     |
+--------+---------+----------------------+-------+
```

Example:
```
34 cb00 35200000 b3f3
│  │    │        └── CRC
│  │    └── timestamp: 8245 seconds since transmitter start
│  └── glucose: 203 mg/dL
└── opcode: 0x34
```

### CalibrateGlucoseRxMessage (0x35)

```
+--------+---------+--------+-------+
| [0]    | [1]     | [2]    | [3-4] |
+--------+---------+--------+-------+
| opcode | unknown | status | CRC   |
+--------+---------+--------+-------+
| 0x35   | 0x00    | varies | -     |
+--------+---------+--------+-------+
```

Status values:
- `0x00`: Calibration successful
- `0x06`: Second calibration needed
- `0x08`: Calibration rejected, enter another
- `0x0b`: Sensor stopped, cannot calibrate

### SessionStartTxMessage (0x26)

**G5 Format (11 bytes):**
```
+--------+-----------+-------------+-------+
| [0]    | [1-4]     | [5-8]       | [9-10]|
+--------+-----------+-------------+-------+
| opcode | startTime | currentTime | CRC   |
+--------+-----------+-------------+-------+
| 0x26   | UInt32LE  | UInt32LE    | -     |
+--------+-----------+-------------+-------+
```

**G6 Format (17 bytes):**
```
+--------+-----------+-------------+---------+---------+--------+-------+
| [0]    | [1-4]     | [5-8]       | [9-10]  | [11-12] | [13-14]| [15-16]|
+--------+-----------+-------------+---------+---------+--------+-------+
| opcode | startTime | currentTime | paramA  | paramB  | null   | CRC   |
+--------+-----------+-------------+---------+---------+--------+-------+
| 0x26   | UInt32LE  | UInt32LE    | UInt16LE| UInt16LE| 0x0000 | -     |
+--------+-----------+-------------+---------+---------+--------+-------+
```

G6 includes calibration parameters derived from sensor serial code.

### SessionStartRxMessage (0x27)

```
+--------+--------+----------+-----------------+-----------------+-----------------+
| [0]    | [1]    | [2]      | [3-6]           | [7-10]          | [11-14]         |
+--------+--------+----------+-----------------+-----------------+-----------------+
| opcode | status | received | requestedStart  | sessionStart    | transmitterTime |
+--------+--------+----------+-----------------+-----------------+-----------------+
| 0x27   | UInt8  | UInt8    | UInt32LE        | UInt32LE        | UInt32LE        |
+--------+--------+----------+-----------------+-----------------+-----------------+
```

### SessionStopTxMessage (0x28)

```
+--------+-----------+-------+
| [0]    | [1-4]     | [5-6] |
+--------+-----------+-------+
| opcode | stopTime  | CRC   |
+--------+-----------+-------+
| 0x28   | UInt32LE  | -     |
+--------+-----------+-------+
```

### BatteryStatusRxMessage (0x23)

**G5 Format (12 bytes):**
```
+--------+--------+----------+----------+--------+---------+-------------+-------+
| [0]    | [1]    | [2-3]    | [4-5]    | [6-7]  | [8]     | [9]         | [10-11]|
+--------+--------+----------+----------+--------+---------+-------------+-------+
| opcode | status | voltagea | voltageb | resist | runtime | temperature | CRC   |
+--------+--------+----------+----------+--------+---------+-------------+-------+
| 0x23   | UInt8  | UInt16LE | UInt16LE | UInt16LE| UInt8  | UInt8       | -     |
+--------+--------+----------+----------+--------+---------+-------------+-------+
```

**G6/G6+ Format (10 bytes):**
```
+--------+--------+----------+----------+---------+-------------+-------+
| [0]    | [1]    | [2-3]    | [4-5]    | [6]     | [7]         | [8-9] |
+--------+--------+----------+----------+---------+-------------+-------+
| opcode | status | voltagea | voltageb | runtime | temperature | CRC   |
+--------+--------+----------+----------+---------+-------------+-------+
| 0x23   | UInt8  | UInt16LE | UInt16LE | UInt8   | UInt8       | -     |
+--------+--------+----------+----------+---------+-------------+-------+
```

Note: G6+ format does not include the `resist` field.

### Version Messages

**VersionRequestTxMessage (0x20/0x4A/0x52):**
```
+--------+-------+
| [0]    | [1-2] |
+--------+-------+
| opcode | CRC   |
+--------+-------+
```

Version opcodes: `0x20` (v0), `0x4A` (v1), `0x52` (v2)

**VersionRequestRx0Message (0x21):**
```
+--------+--------+-----------------+-------------------+--------+-----------------+-------+-------+
| [0]    | [1]    | [2-5]           | [6-9]             | [10]   | [11-14]         | [15-16]| [17] |
+--------+--------+-----------------+-------------------+--------+-----------------+-------+-------+
| opcode | status | firmwareVersion | btFirmwareVersion | hwRev  | otherFwVersion  | asic  | CRC  |
+--------+--------+-----------------+-------------------+--------+-----------------+-------+-------+
```

Example:
```
21 00 02120258 02120258 ff 003145 4141 2412
   │  │        │        │  │      │    └── CRC
   │  │        │        │  │      └── asic: 0x4141
   │  │        │        │  └── otherFwVersion: 0.49.69
   │  │        │        └── hwRev: 255
   │  │        └── btFirmwareVersion: 2.18.2.88
   │  └── firmwareVersion: 2.18.2.88
   └── status: 0x00
```

**VersionRequestRx1Message (0x4B):**
```
+--------+--------+-----------------+------------+-------------+----------+--------------+----------------+
| [0]    | [1]    | [2-5]           | [6-9]      | [10-11]     | [12]     | [13]         | [14-15]        |
+--------+--------+-----------------+------------+-------------+----------+--------------+----------------+
| opcode | status | firmwareVersion | buildVer   | inactiveDays| versionCode| maxRuntimeDays| maxInactiveDays|
+--------+--------+-----------------+------------+-------------+----------+--------------+----------------+
```

**VersionRequestRx2Message (0x53):**
```
+--------+--------+-----------------+-------------+--------------+-------+
| [0]    | [1]    | [2]             | [3-4]       | [5-16]       | [17-18]|
+--------+--------+-----------------+-------------+--------------+-------+
| opcode | status | typicalSensorDays| featureBits | unknown     | CRC   |
+--------+--------+-----------------+-------------+--------------+-------+
```

### BackfillTxMessage (0x50)

```
+--------+------+------+------+--------------+------------+-------+
| [0]    | [1]  | [2]  | [3]  | [4-7]        | [8-11]     | [12-13]|
+--------+------+------+------+--------------+------------+-------+
| opcode | 0x05 | 0x02 | 0x00 | timestampStart| timestampEnd| CRC  |
+--------+------+------+------+--------------+------------+-------+
| 0x50   | -    | -    | -    | UInt32LE     | UInt32LE   | -     |
+--------+------+------+------+--------------+------------+-------+
```

### BackfillRxMessage (0x51)

```
+--------+--------+--------------+------------+--------------+------------+-------+
| [0]    | [1]    | [2]          | [3]        | [4-7]        | [8-11]     | ...   |
+--------+--------+--------------+------------+--------------+------------+-------+
| opcode | status | backfillStatus| identifier | timestampStart| timestampEnd| CRC  |
+--------+--------+--------------+------------+--------------+------------+-------+
| 0x51   | UInt8  | UInt8        | UInt8      | UInt32LE     | UInt32LE   | -     |
+--------+--------+--------------+------------+--------------+------------+-------+
```

### Backfill Data Packets

Backfill data arrives via notifications on the Backfill characteristic:

**First Packet:**
```
+----------+------------+------------------------+-------------------+
| [0]      | [1]        | [2-3]                  | [4-5]             |
+----------+------------+------------------------+-------------------+
| sequence | identifier | backfillRequestCounter | unknown           |
+----------+------------+------------------------+-------------------+
| 0x01     | varies     | UInt16LE               | UInt16LE          |
+----------+------------+------------------------+-------------------+
```

**Subsequent Packets:**
```
+----------+------------+-------------------------------+
| [0]      | [1]        | [2-...]                       |
+----------+------------+-------------------------------+
| sequence | identifier | backfill data (8 bytes each)  |
+----------+------------+-------------------------------+
```

**Backfill Data Entry (8 bytes each):**
```
+----------+---------+------+-------+
| [0-3]    | [4-5]   | [6]  | [7]   |
+----------+---------+------+-------+
| dextime  | glucose | type | trend |
+----------+---------+------+-------+
| UInt32LE | UInt16LE| UInt8| Int8  |
+----------+---------+------+-------+
```

## Communication Flow

### Standard Reading Cycle

```
┌──────────────────┐                           ┌──────────────────┐
│     Client       │                           │   Transmitter    │
└────────┬─────────┘                           └────────┬─────────┘
         │                                              │
         │  1. Connect via BLE                          │
         │─────────────────────────────────────────────▶│
         │                                              │
         │  2. Authentication (see auth flow above)     │
         │◀────────────────────────────────────────────▶│
         │                                              │
         │  3. Enable notifications on Control          │
         │─────────────────────────────────────────────▶│
         │                                              │
         │  4. TransmitterTimeTxMessage (0x24)          │
         │─────────────────────────────────────────────▶│
         │  5. TransmitterTimeRxMessage (0x25)          │
         │◀─────────────────────────────────────────────│
         │                                              │
         │  6. [Optional] Send pending commands         │
         │     (Calibrate, Start/Stop session, etc.)    │
         │◀────────────────────────────────────────────▶│
         │                                              │
         │  7. [Optional] BackfillTxMessage (0x50)      │
         │─────────────────────────────────────────────▶│
         │  8. BackfillRxMessage (0x51)                 │
         │◀─────────────────────────────────────────────│
         │  9. Backfill data via Backfill characteristic│
         │◀─────────────────────────────────────────────│
         │                                              │
         │  10. GlucoseTxMessage (0x30/0x4E)            │
         │─────────────────────────────────────────────▶│
         │  11. GlucoseRxMessage (0x31/0x4F)            │
         │◀─────────────────────────────────────────────│
         │                                              │
         │  12. SensorTxMessage (0x2E)                  │
         │─────────────────────────────────────────────▶│
         │  13. SensorRxMessage (0x2F)                  │
         │◀─────────────────────────────────────────────│
         │                                              │
         │  14. CalibrationDataTxMessage (0x32)         │
         │─────────────────────────────────────────────▶│
         │  15. CalibrationDataRxMessage (0x33)         │
         │◀─────────────────────────────────────────────│
         │                                              │
         │  16. DisconnectTxMessage (0x09)              │
         │─────────────────────────────────────────────▶│
         │                                              │
```

## G5 vs G6 Differences

| Feature | G5 | G6 |
|---------|----|----|
| Serial prefix | `4xxxxx` | `8xxxxx` |
| Glucose opcode (Tx) | `0x30` | `0x4E` |
| Glucose opcode (Rx) | `0x31` | `0x4F` |
| CalibrationDataRx length | 19 bytes | 20 bytes |
| BatteryStatusRx length | 12 bytes | 10 bytes |
| SessionStart format | No sensor code | Includes calibration params |
| Sensor scaling | None | 34x or 35x multiplier |
| Requires calibration | Yes | Optional (factory calibrated) |

## Related Documentation

- [data-models.md](data-models.md) - Data structures and status codes
- [README.md](README.md) - Library overview and architecture
