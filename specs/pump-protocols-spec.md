# Pump Communication Protocols Specification

This specification documents the low-level communication protocols used by AID systems to communicate with insulin pumps. Based on analysis of OmniBLE (Loop), AAPS pump drivers, and MinimedKit sources.

## Document Status

| Version | Date | Status |
|---------|------|--------|
| 1.0 | 2026-01-17 | Draft - Analysis Complete |

---

## 1. Omnipod DASH BLE Protocol

### 1.1 BLE Service Architecture

#### Service and Characteristic UUIDs

| Component | UUID | Purpose |
|-----------|------|---------|
| Advertisement Service | `00004024-0000-1000-8000-00805f9b34fb` | Pod discovery |
| Primary Service | `1A7E4024-E3ED-4464-8B7E-751E03D0DC5F` | Main communication |
| Command Characteristic | `1A7E2441-E3ED-4464-8B7E-751E03D0DC5F` | Control flow commands |
| Data Characteristic | `1A7E2442-E3ED-4464-8B7E-751E03D0DC5F` | Payload transfer |

**Source**: `OmniBLE/OmniBLE/Bluetooth/BluetoothServices.swift`

### 1.2 BLE Command Types

Flow control commands sent via Command Characteristic:

| Command | Value | Purpose |
|---------|-------|---------|
| RTS | `0x00` | Ready To Send |
| CTS | `0x01` | Clear To Send |
| NACK | `0x02` | Negative Acknowledgment |
| ABORT | `0x03` | Abort transaction |
| SUCCESS | `0x04` | Command succeeded |
| FAIL | `0x05` | Command failed |
| HELLO | `0x06` | Initial handshake |
| INCORRECT | `0x09` | Invalid command |

**Source**: `OmniBLE/OmniBLE/Bluetooth/BluetoothServices.swift:18-27`

### 1.3 Message Packet Structure

All messages start with "TW" magic pattern and have 16-byte header:

```
Offset  Size  Field
0       2     Magic Pattern ("TW")
2       1     Flags1 (version[0:2], sas[3], tfs[4], eqos[5:7])
3       1     Flags2 (ack[0], priority[1], lastMessage[2], gateway[3], type[4:7])
4       1     Sequence Number
5       1     Ack Number
6       2     Payload Size (11 bits, shifted)
8       4     Source ID
12      4     Destination ID
16      N     Payload (+ 8-byte MAC for encrypted messages)
```

#### Message Types (Flags2 bits 4-7)

| Type | Value | Description |
|------|-------|-------------|
| CLEAR | `0x00` | Unencrypted message |
| ENCRYPTED | `0x01` | AES-CCM encrypted |
| SESSION_ESTABLISHMENT | `0x02` | EAP-AKA handshake |
| PAIRING | `0x03` | LTK exchange |

**Source**: `OmniBLE/OmniBLE/Bluetooth/MessagePacket.swift`

### 1.4 Security: LTK Exchange (Pairing)

Uses X25519 key exchange with CMAC confirmation:

```
Step 1: Controller → Pod: SP1=<pod_id>, SP2=<GetPodStatus>
Step 2: Controller → Pod: SPS1=<pdm_public_key(32)> + <pdm_nonce(16)>
Step 3: Pod → Controller: SPS1=<pod_public_key(32)> + <pod_nonce(16)>
Step 4: Controller → Pod: SPS2=<pdm_conf(16)>  (CMAC confirmation)
Step 5: Pod → Controller: SPS2=<pod_conf(16)>  (CMAC confirmation)
Step 6: Controller → Pod: SP0GP0
Step 7: Pod → Controller: P0=0xA5

Result: LTK (16 bytes) derived from X25519 shared secret
```

**Source**: `OmniBLE/OmniBLE/Bluetooth/Pair/LTKExchanger.swift`

### 1.5 Security: Session Establishment (EAP-AKA)

Uses 3GPP Milenage algorithm for mutual authentication:

#### Milenage Constants

| Constant | Value | Size |
|----------|-------|------|
| MILENAGE_OP | `cdc202d5123e20f62b6d676ac72cb318` | 16 bytes |
| MILENAGE_AMF | `b9b9` | 2 bytes |
| RESYNC_AMF | `0000` | 2 bytes |
| KEY_SIZE | 16 | bytes |
| SQN_SIZE | 6 | bytes |
| AUTS_SIZE | 14 | bytes |

#### Session Establishment Flow

```
Step 1: Controller → Pod: EAP-AKA Challenge
        - AT_AUTN: Authentication token (16 bytes)
        - AT_RAND: Random challenge (16 bytes)
        - AT_CUSTOM_IV: Controller IV (4 bytes)

Step 2: Pod → Controller: EAP-AKA Response
        - AT_RES: Response (8 bytes) - must match expected
        - AT_CUSTOM_IV: Pod IV (4 bytes)
        
        OR Resynchronization:
        - AT_AUTS: Resync token (14 bytes)

Step 3: Controller → Pod: EAP-SUCCESS

Result: 
- CK: Cipher Key (16 bytes) from Milenage
- Nonce: Controller_IV (4 bytes) + Pod_IV (4 bytes)
```

**Source**: `OmniBLE/OmniBLE/Bluetooth/Session/SessionEstablisher.swift`, `Milenage.swift`

### 1.6 Encryption: AES-CCM

| Parameter | Value |
|-----------|-------|
| Algorithm | AES-128-CCM |
| Key | CK from Milenage (16 bytes) |
| Nonce | 13 bytes (prefix + sequence number) |
| MAC Size | 8 bytes |
| AAD | Message header (16 bytes) |

**Source**: `OmniBLE/OmniBLE/Bluetooth/EnDecrypt/EnDecrypt.swift`

### 1.7 Pod Command Message Blocks

#### Message Block Types (Opcodes)

| Opcode | Name | Direction | Description |
|--------|------|-----------|-------------|
| `0x01` | VersionResponse | Pod→Ctrl | Pod version info |
| `0x02` | PodInfoResponse | Pod→Ctrl | Pod status details |
| `0x03` | SetupPod | Ctrl→Pod | Initial pod setup |
| `0x06` | ErrorResponse | Pod→Ctrl | Error details |
| `0x07` | AssignAddress | Ctrl→Pod | Assign pod address |
| `0x08` | FaultConfig | Ctrl→Pod | Configure fault behavior |
| `0x0e` | GetStatus | Ctrl→Pod | Request status |
| `0x11` | AcknowledgeAlert | Ctrl→Pod | Clear alerts |
| `0x13` | BasalScheduleExtra | Ctrl→Pod | Extended basal params |
| `0x16` | TempBasalExtra | Ctrl→Pod | Extended TBR params |
| `0x17` | BolusExtra | Ctrl→Pod | Extended bolus params |
| `0x19` | ConfigureAlerts | Ctrl→Pod | Alert configuration |
| `0x1a` | SetInsulinSchedule | Ctrl→Pod | Main delivery command |
| `0x1c` | DeactivatePod | Ctrl→Pod | Deactivate pod |
| `0x1d` | StatusResponse | Pod→Ctrl | Current status |
| `0x1e` | BeepConfig | Ctrl→Pod | Configure beeps |
| `0x1f` | CancelDelivery | Ctrl→Pod | Stop delivery |

**Source**: `OmniBLE/OmniBLE/OmnipodCommon/MessageBlocks/MessageBlock.swift`

### 1.8 SetInsulinSchedule Command (0x1a)

Main insulin delivery command. Supports three schedule types:

#### Schedule Type Codes

| Code | Type | Description |
|------|------|-------------|
| `0x00` | BasalSchedule | Scheduled basal program |
| `0x01` | TempBasal | Temporary basal rate |
| `0x02` | Bolus | Immediate bolus |

#### Bolus Delivery Structure

```
Offset  Size  Field
0       1     Block Type (0x1a)
1       1     Length
2       4     Nonce (32-bit, big-endian)
6       1     Schedule Type (0x02 for bolus)
7       2     Checksum
9       1     Num Segments
10      2     FieldA (pulses × time multiplier)
12      2     First Segment Pulses
14      N     Delivery table entries (2 bytes each)
```

#### Temp Basal Delivery Structure

```
Offset  Size  Field
0       1     Block Type (0x1a)
1       1     Length
2       4     Nonce
6       1     Schedule Type (0x01 for TBR)
7       2     Checksum
9       1     Num Segments
10      2     Seconds Remaining (shifted left 3)
12      2     First Segment Pulses
14      N     Delivery table entries
```

**Source**: `OmniBLE/OmniBLE/OmnipodCommon/MessageBlocks/SetInsulinScheduleCommand.swift`

### 1.9 BolusExtra Command (0x17)

Extended bolus parameters (13 bytes total):

```
Offset  Size  Field
0       1     Block Type (0x17)
1       1     Length (0x0d)
2       1     Beep Options (ack[7], completion[6], reminder[0:5])
3       2     Pulse Count × 10 (big-endian)
5       4     Time Between Pulses (hundredths of ms, big-endian)
9       2     Extended Pulse Count × 10
11      4     Time Between Extended Pulses
```

**Source**: `OmniBLE/OmniBLE/OmnipodCommon/MessageBlocks/BolusExtraCommand.swift`

### 1.10 StatusResponse (0x1d)

Pod status (10 bytes):

```
Offset  Size  Field
0       1     Block Type (0x1d)
1       1     Delivery Status (high nibble), Progress Status (low nibble)
2-4     13b   Insulin Delivered (pulses)
4       4b    Last Programming Message Seq
4-5     10b   Bolus Not Delivered (pulses)
6-7     8b    Alerts (AlertSet bitmap)
7-8     13b   Time Active (minutes)
8-9     10b   Reservoir Level (pulses)
```

#### Delivery Status Values

| Value | Name | Description |
|-------|------|-------------|
| `0x00` | Suspended | Delivery suspended |
| `0x01` | ScheduledBasal | Normal basal running |
| `0x02` | TempBasalRunning | Temp basal active |
| `0x04` | Priming | Priming in progress |
| `0x05` | BolusInProgress | Bolus delivering |
| `0x06` | BolusAndTempBasal | Both active |
| `0x08` | ExtendedBolusWhileSuspended | Extended bolus, suspended |
| `0x09` | ExtendedBolusRunning | Extended bolus active |
| `0x0a` | ExtendedBolusAndTempBasal | Both extended + TBR |

**Source**: `OmniBLE/OmniBLE/OmnipodCommon/Pod.swift`, `StatusResponse.swift`

### 1.11 Pod Constants

| Constant | Value | Unit |
|----------|-------|------|
| Pulse Size | 0.05 | U |
| Pulses per Unit | 20 | pulses/U |
| Seconds per Bolus Pulse | 2 | seconds |
| Bolus Delivery Rate | 0.025 | U/s |
| Max Reservoir Reading | 50 | U |
| Reservoir Capacity | 200 | U |
| Max Basal Schedule Entries | 24 | entries |
| Min Basal Entry Duration | 30 | minutes |
| Service Duration | 80 | hours |
| Nominal Pod Life | 72 | hours |

**Source**: `OmniBLE/OmniBLE/OmnipodCommon/Pod.swift`

---

## 2. Dana RS/i BLE Protocol

### 2.1 Packet Structure

All Dana RS packets follow this format:

```
Offset  Size  Field
0       2     Start Bytes (0xA5, 0xA5)
2       1     Length (packet size - 7)
3       1     Type (command type)
4       1     OpCode (command code)
5       N     Data payload
-4      2     CRC-16 (big-endian)
-2      2     End Bytes (0x5A, 0x5A)
```

**Source**: `pump/danars/src/main/kotlin/app/aaps/pump/danars/comm/DanaRSPacket.kt`

### 2.2 Packet Types

| Type | Value | Description |
|------|-------|-------------|
| COMMAND | Standard | Regular pump commands |
| ENCRYPTION_REQUEST | Request | Encryption handshake request |
| ENCRYPTION_RESPONSE | Response | Encryption handshake response |
| NOTIFY | Notify | Pump notifications |
| RESPONSE | Response | Command responses |

### 2.3 Encryption Types

| Type | Description | Security Level |
|------|-------------|----------------|
| ENCRYPTION_DEFAULT | Legacy encryption | Time + Password + SN encoding |
| ENCRYPTION_RSv3 | Dana RS v3 | Pairing key + random key + matrix |
| ENCRYPTION_BLE5 | BLE5 (Dana-i) | 6-digit PIN + matrix encryption |

**Source**: `pump/danars/src/main/kotlin/app/aaps/pump/danars/encryption/BleEncryption.kt`

### 2.4 Encryption Handshake Flow

#### RSv3 / BLE5 Connection States

| State | Value | Description |
|-------|-------|-------------|
| 0 | Pre-handshake | Initial connection |
| 1 | Time exchange | Awaiting pairing keys |
| 2 | Authenticated | Full encryption active |

#### Handshake Commands

| OpCode | Name | Purpose |
|--------|------|---------|
| `0x00` | PUMP_CHECK | Initial pump identification |
| `0x01` | PASSKEY_REQUEST | Request passkey |
| `0x02` | PASSKEY_RETURN | Passkey returned |
| `0x03` | CHECK_PASSKEY | Verify passkey |
| `0x04` | TIME_INFORMATION | Time sync + authentication |
| `0x05` | GET_PUMP_CHECK | Verify pump connection |
| `0x06` | GET_EASY_MENU_CHECK | Check easy menu status |

### 2.5 CRC-16 Calculation

```kotlin
fun generateCrc(buffer: UByteArray): UInt {
    var crc: UShort = 0u
    for (byte in buffer) {
        var result = crc.ushr(8) or crc.shl(8)
        result = result.xor(byte)
        result = result.xor(result.and(0xFFu).ushr(4))
        result = result.xor(result.shl(12))
        // Variant based on encryption type and connection state
        result = result xor (...)  // Different polynomial per mode
        crc = result
    }
    return crc
}
```

CRC polynomial varies by encryption type and connection state.

**Source**: `pump/danars/src/main/kotlin/app/aaps/pump/danars/encryption/BleEncryption.kt:453-480`

### 2.6 Multi-Layer Encryption (RSv3)

RSv3 encryption applies three layers:

1. **Serial Number Encoding**: XOR with device name bytes
2. **Time Encoding**: XOR with time info bytes
3. **Password Encoding**: XOR with password bytes
4. **CfPassKey Encoding**: XOR with confirmed passkey

For BLE5, simpler matrix-based encryption using 6-digit PIN.

### 2.7 Command Categories

#### Basal Commands

| OpCode | Name | Parameters |
|--------|------|------------|
| GetBasalRate | Read basal program | - |
| GetProfileNumber | Read active profile | - |
| SetProfileBasalRate | Write basal program | 24 rates |
| SetProfileNumber | Change profile | Profile number |
| SetTemporaryBasal | Start TBR | Duration, rate |
| CancelTemporaryBasal | Stop TBR | - |

#### Bolus Commands

| OpCode | Name | Parameters |
|--------|------|------------|
| SetStepBolusStart | Start bolus | Amount, speed |
| SetStepBolusStop | Cancel bolus | - |
| SetExtendedBolus | Start extended | Amount, duration |
| SetExtendedBolusCancel | Cancel extended | - |
| GetStepBolusInformation | Read bolus status | - |

#### History Commands

| OpCode | Name | Parameters |
|--------|------|------------|
| APSHistoryEvents | Read APS history | Since timestamp |
| APSSetEventHistory | Write APS event | Event data |

**Source**: `pump/danars/src/main/kotlin/app/aaps/pump/danars/comm/DanaRSMessageHashTable.kt`

### 2.8 Bolus Delivery Speeds

| Setting | Speed | Time per 1U |
|---------|-------|-------------|
| 0 (Fast) | 12 sec/U | 12 seconds |
| 1 (Normal) | 30 sec/U | 30 seconds |
| 2 (Slow) | 60 sec/U | 60 seconds |

### 2.9 Error Codes

| Code | Meaning |
|------|---------|
| `0x10` | Max bolus violation |
| `0x20` | Command error |
| `0x40` | Speed error |
| `0x80` | Insulin limit violation |

**Source**: `pump/danars/src/main/kotlin/app/aaps/pump/danars/DanaRSPlugin.kt`

---

## 3. Medtronic RF Protocol

### 3.1 Physical Layer

| Parameter | Value |
|-----------|-------|
| Frequency (US) | 916.5 MHz |
| Frequency (EU) | 868 MHz |
| Modulation | FSK |
| Bridge Device | RileyLink |

### 3.2 Message Structure

Medtronic uses Carelink message format:

| Format | Description |
|--------|-------------|
| Short Message | Head + Body (< 64 bytes) |
| Long Message | Multi-packet with paging |

### 3.3 History Entry Types

Based on `PumpHistoryEntryType.kt`, major opcodes:

#### Delivery Events

| Code | Name | Head | Date | Body |
|------|------|------|------|------|
| `0x01` | Bolus | 4 (8 on 523+) | 5 | 0 |
| `0x03` | Prime | 5 | 5 | 0 |
| `0x16` | TempBasalDuration | 2 | 5 | 0 |
| `0x33` | TempBasalRate | 2 | 5 | 1 |
| `0x1e` | SuspendPump | 2 | 5 | 0 |
| `0x1f` | ResumePump | 2 | 5 | 0 |
| `0x7b` | BasalProfileStart | 2 | 5 | 3 |

#### Configuration Events

| Code | Name | Description |
|------|------|-------------|
| `0x08` | ChangeBasalProfile_Old | Previous basal program |
| `0x09` | ChangeBasalProfile_New | New basal program |
| `0x14` | ChangeBasalPattern | Pattern selection |
| `0x24` | ChangeMaxBolus | Max bolus setting |
| `0x2c` | ChangeMaxBasal | Max basal setting |

#### Alarm/Status Events

| Code | Name | Description |
|------|------|-------------|
| `0x06` | NoDeliveryAlarm | Occlusion/empty |
| `0x0b` | SensorAlert | CGM alert |
| `0x0c` | ClearAlarm | Alarm acknowledged |
| `0x19` | LowBattery | Battery warning |
| `0x1a` | BatteryChange | Battery replaced |
| `0x34` | LowReservoir | Reservoir warning |

#### Statistics Events

| Code | Name | Description |
|------|------|-------------|
| `0x6c` | DailyTotals515 | Daily summary (515) |
| `0x6d` | DailyTotals522 | Daily summary (522) |
| `0x6e` | DailyTotals523 | Daily summary (523) |
| `0x07` | EndResultTotals | Period totals |

**Source**: `pump/medtronic/src/main/kotlin/app/aaps/pump/medtronic/comm/history/pump/PumpHistoryEntryType.kt`

### 3.4 Entry Structure

Each history entry has variable structure:

| Component | Size | Description |
|-----------|------|-------------|
| Head | 2-8 bytes | Opcode + parameters |
| Date | 0-5 bytes | Timestamp (5-byte packed) |
| Body | 0-145 bytes | Additional data |

### 3.5 Device-Specific Sizes

Different pump models have different entry sizes:

| Entry Type | 512/515 | 522/523 | 523+ |
|------------|---------|---------|------|
| Bolus Head | 4 | 4 | 8 |
| BolusWizard Body | 12 | 13 | 15 |
| BolusWizardSetup Body | 32 | 117 | 137 |

---

## 4. Cross-Protocol Comparison

### 4.1 Transport Layer

| Aspect | Omnipod DASH | Dana RS | Medtronic |
|--------|--------------|---------|-----------|
| Transport | BLE Direct | BLE Direct | RF (via RileyLink) |
| Frequency | 2.4 GHz | 2.4 GHz | 916.5/868 MHz |
| Bridge Required | No | No | Yes |
| MTU | 20 bytes | 20 bytes | 64 bytes |

### 4.2 Security

| Aspect | Omnipod DASH | Dana RS | Medtronic |
|--------|--------------|---------|-----------|
| Pairing | X25519 + CMAC | 6-digit PIN | None |
| Session Auth | EAP-AKA (Milenage) | Time + Password | Serial check |
| Encryption | AES-128-CCM | Matrix + XOR | None |
| Replay Protection | Sequence numbers | CRC | Sequence numbers |

### 4.3 Bolus Precision

| Aspect | Omnipod DASH | Dana RS | Medtronic |
|--------|--------------|---------|-----------|
| Step Size | 0.05 U | 0.01-0.05 U | 0.025-0.05 U |
| Min Bolus | 0.05 U | 0.05 U | 0.025-0.05 U |
| Max Bolus | 30 U | Configurable | 25 U |
| Delivery Rate | 0.025 U/s | Configurable | ~0.025 U/s |

### 4.4 Temp Basal

| Aspect | Omnipod DASH | Dana RS | Medtronic |
|--------|--------------|---------|-----------|
| Type | Absolute only | Percent | Absolute |
| Duration Step | 30 min | 15/30/60 min | 30 min |
| Max Duration | 12 hours | 24 hours | 24 hours |
| Max Rate | 30 U/hr | 200% | 35 U/hr |

---

## 5. Implementation Notes

### 5.1 Nonce Management

Omnipod DASH requires nonce for most commands:
- Nonce is 32-bit value
- Must be unique per command
- Pod tracks last nonce for replay protection
- `NonceResyncableMessageBlock` protocol for commands requiring nonce

### 5.2 Delivery Uncertainty

All protocols have mechanisms for detecting uncertain delivery:

| System | Mechanism |
|--------|-----------|
| Loop | `PumpManagerStatus.deliveryIsUncertain` flag |
| AAPS | `PumpEnactResult.success` + retry logic |
| Omnipod | StatusResponse verification after command |
| Dana | Bolus progress tracking |

### 5.3 History Reconciliation

| System | Pattern |
|--------|---------|
| Loop | `PumpManagerDelegate.hasNewPumpEvents()` callback |
| AAPS | `PumpSync.syncBolusWithPumpId()` |
| Omnipod | No persistent history, track via StatusResponse |
| Dana | Full history retrieval via APSHistoryEvents |
| Medtronic | Page-based history with CRC validation |

---

## Source Files Reference

### Omnipod DASH (OmniBLE - Swift)
- `OmniBLE/Bluetooth/BluetoothServices.swift` - BLE UUIDs, command types
- `OmniBLE/Bluetooth/MessagePacket.swift` - Packet structure
- `OmniBLE/Bluetooth/EnDecrypt/EnDecrypt.swift` - AES-CCM encryption
- `OmniBLE/Bluetooth/Session/SessionEstablisher.swift` - EAP-AKA
- `OmniBLE/Bluetooth/Session/Milenage.swift` - Milenage algorithm
- `OmniBLE/Bluetooth/Pair/LTKExchanger.swift` - Key exchange
- `OmniBLE/OmnipodCommon/MessageBlocks/*.swift` - Command definitions
- `OmniBLE/OmnipodCommon/Pod.swift` - Constants

### Dana RS (AAPS - Kotlin)
- `pump/danars/comm/DanaRSPacket.kt` - Packet structure
- `pump/danars/encryption/BleEncryption.kt` - Encryption layers
- `pump/danars/comm/DanaRSMessageHashTable.kt` - Command registry
- `pump/danars/DanaRSPlugin.kt` - Driver implementation

### Medtronic (AAPS - Kotlin)
- `pump/medtronic/comm/history/pump/PumpHistoryEntryType.kt` - Opcodes
- `pump/medtronic/comm/MedtronicCommunicationManager.kt` - Protocol
- `pump/medtronic/comm/message/*.kt` - Message formats
