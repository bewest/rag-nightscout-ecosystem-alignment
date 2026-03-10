# Device Capability Architecture Deep Dive

**Created**: 2026-02-03  
**Trace**: GAP-ARCH-001, GAP-ARCH-002, GAP-ARCH-003, REQ-ARCH-001, REQ-ARCH-002, REQ-ARCH-003  
**Related**: [Pump Communication Deep Dive](pump-communication-deep-dive.md), [CGM Data Sources Deep Dive](cgm-data-sources-deep-dive.md)

---

## Executive Summary

CGMs and insulin pumps are fundamentally different device categories that should never share a single state model. This document establishes the architectural taxonomy for device capabilities across the AID ecosystem, addressing the "ConnectionPreviewState Overloaded" anti-pattern where implementations conflate CGM pairing and pump pairing into a single generic connection state.

---

## 1. Device Category Taxonomy

### 1.1 CGM (Continuous Glucose Monitor)

**Primary Function**: Read-only sensor data acquisition

**Data Flow**: Device → Controller (unidirectional for data, occasional commands for auth)

**Safety Criticality**: LOW - Display-only, incorrect data causes user inconvenience

**Connection Model**: Periodic reads or streaming with reconnection tolerance

| Capability | Description | Example |
|------------|-------------|---------|
| **Glucose Reading** | Current glucose value (mg/dL or mmol/L) | 120 mg/dL |
| **Trend Rate** | Rate of change (mg/dL/min) | +2.3 mg/dL/min |
| **Trend Arrow** | Categorical direction indicator | ↗ RISING |
| **Sensor State** | Lifecycle status | WARMING_UP, OK, EXPIRED |
| **Signal Quality** | RSSI or quality metric | -65 dBm |
| **Transmitter Battery** | Power remaining | 85% |
| **Calibration State** | Calibration requirements | NEEDS_CALIBRATION |
| **Backfill Data** | Historical readings | Last 3 hours |

### 1.2 Pump (Insulin Delivery Device)

**Primary Function**: Bidirectional command/response for insulin delivery

**Data Flow**: Controller ↔ Device (bidirectional with acknowledgment)

**Safety Criticality**: HIGH - Incorrect commands can cause hypo/hyperglycemia

**Connection Model**: Command/response with strict acknowledgment requirements

| Capability | Description | Example |
|------------|-------------|---------|
| **Basal Delivery** | Continuous insulin rate | 0.8 U/hr |
| **Temp Basal** | Time-limited rate adjustment | 1.2 U/hr for 30 min |
| **Bolus Delivery** | Discrete insulin doses | 2.5 U bolus |
| **Extended Bolus** | Square/dual wave boluses | 3U over 2 hours |
| **Suspend/Resume** | Delivery interruption | Suspended |
| **Reservoir Level** | Insulin remaining | 142 U |
| **Pod/Device State** | Activation lifecycle | PRIMING, ACTIVE, EXPIRED |
| **Delivery Uncertainty** | Command verification status | UNCERTAIN |
| **Alarm State** | Active alarms | OCCLUSION, LOW_RESERVOIR |

---

## 2. CGM Device Variations

### 2.1 Dexcom G6

| Property | Value |
|----------|-------|
| **Communication** | BLE direct |
| **Authentication** | AES-128 ECB with transmitter-derived key |
| **Reading Interval** | 5 minutes |
| **Form Factor** | Separate transmitter + sensor |
| **Warmup** | 2 hours |
| **Max Duration** | 10 days (sensor), 90 days (transmitter) |
| **Calibration** | Factory calibrated (optional user cal) |
| **Transmitter ID Format** | 6 alphanumeric (e.g., "8G1234") |

**State Model**:
```
IDLE → SCANNING → FOUND → AUTHENTICATING → BONDING → STREAMING → DISCONNECTED
```

**Pairing State Properties**:
- `transmitterId: String` (6 chars, alphanumeric)
- `authState: AuthState` (pending, challenged, authenticated, failed)
- `signalStrength: Int` (-100 to 0 dBm)
- `sensorState: SensorState` (unknown, warming, ok, expired, failed)
- `sensorAge: TimeInterval` (seconds since start)

### 2.2 Dexcom G7

| Property | Value |
|----------|-------|
| **Communication** | BLE direct |
| **Authentication** | J-PAKE (Password Authenticated Key Exchange) |
| **Reading Interval** | 5 minutes |
| **Form Factor** | Integrated transmitter + sensor |
| **Warmup** | 30 minutes |
| **Max Duration** | 10.5 days |
| **Calibration** | Factory calibrated only |
| **Sensor Code** | 4-digit pairing code |

**State Model**:
```
IDLE → SCANNING → FOUND → JPAKE_ROUND1 → JPAKE_ROUND2 → CERT_EXCHANGE → STREAMING → DISCONNECTED
```

**Pairing State Properties**:
- `sensorCode: String` (4-digit)
- `jpakeState: JPAKEState` (idle, round1, round2, complete, failed)
- `certState: CertState` (none, exchanged, verified)
- `signalStrength: Int`
- `sensorInfo: G7SensorInfo` (serialNumber, insertionTime, expirationTime)

### 2.3 Freestyle Libre 1

| Property | Value |
|----------|-------|
| **Communication** | NFC-only (ISO 15693) |
| **Authentication** | None |
| **Reading Interval** | 1 minute (stored), on-demand via NFC |
| **Form Factor** | Sensor with integrated NFC tag |
| **Warmup** | 1 hour |
| **Max Duration** | 14 days |
| **Calibration** | Factory calibrated |
| **Serial Number** | Encoded from 8-byte UID |

**State Model**:
```
NOT_STARTED → STARTING (warmup) → READY → EXPIRED → SHUTDOWN
```

**Pairing State Properties**:
- `sensorUID: Data` (8 bytes)
- `serialNumber: String` (derived from UID)
- `sensorState: LibreSensorState`
- `minutesSinceStart: Int`
- `minutesRemaining: Int`

### 2.4 Freestyle Libre 2

| Property | Value |
|----------|-------|
| **Communication** | NFC (pairing) + BLE (streaming) |
| **Authentication** | XOR cipher with sensor UID-derived key |
| **Reading Interval** | 1 minute (BLE streaming) |
| **Form Factor** | Sensor with NFC + BLE |
| **Warmup** | 1 hour |
| **Max Duration** | 14 days |
| **Regional Variants** | EU, US (14-day), different encryption |

**State Model**:
```
NOT_STARTED → NFC_PAIRING → BLE_CONNECTING → STREAMING → EXPIRED
```

**Pairing State Properties**:
- `sensorUID: Data`
- `patchInfo: Data` (identifies variant)
- `bleMAC: Data` (6 bytes, from NFC unlock)
- `encryptionKey: Data` (derived from UID + patchInfo)
- `sensorFamily: LibreSensorFamily` (.libre2EU, .libre2US, etc.)

### 2.5 Freestyle Libre 3

| Property | Value |
|----------|-------|
| **Communication** | BLE direct (encrypted) |
| **Authentication** | ECDH key exchange + challenge-response |
| **Reading Interval** | 1 minute |
| **Form Factor** | Sensor with integrated BLE |
| **Warmup** | 1 hour |
| **Max Duration** | 14 days |
| **Encryption** | Full end-to-end |

**State Model**:
```
IDLE → SCANNING → CONNECTING → SECURITY_HANDSHAKE → CHALLENGE_EXCHANGE → STREAMING → DISCONNECTED
```

**Pairing State Properties**:
- `sensorSerial: String`
- `securityState: Libre3SecurityState` (idle, challenged, authenticated)
- `publicKey: Data` (ECDH)
- `sessionKey: Data` (derived)
- `expirationDate: Date`

### 2.6 Third-Party Transmitters (MiaoMiao, Bubble)

| Property | Value |
|----------|-------|
| **Communication** | BLE (Nordic UART Service) |
| **Authentication** | None (open BLE) |
| **Transmitter Role** | NFC proxy for Libre sensors |
| **Reading Interval** | Configurable (1-5 minutes) |

**State Model**:
```
IDLE → SCANNING → CONNECTING → CONNECTED → READING_FRAM → DATA_AVAILABLE
```

**Pairing State Properties**:
- `transmitterMAC: String`
- `firmwareVersion: String`
- `batteryLevel: Int`
- `attachedSensor: LibreSensorInfo?`
- `rawFRAM: Data` (344 bytes)

---

## 3. Pump Device Variations

### 3.1 Omnipod DASH

| Property | Value |
|----------|-------|
| **Communication** | BLE direct |
| **Authentication** | EAP-AKA with Milenage (3GPP) |
| **Encryption** | AES-CCM with LTK |
| **Form Factor** | Disposable pod |
| **Max Duration** | 80 hours activation window, 72 hours active |
| **Reservoir** | 200 units |
| **Basal Precision** | 0.05 U/hr |
| **Bolus Precision** | 0.05 U |

**Lifecycle State Model**:
```
UNINITIALIZED → ADDRESS_ASSIGNED → POD_PAIRED → PRIMING → BASAL_SCHEDULED → CANNULA_INSERTING → RUNNING → FAULT/EXPIRED
```

**Pairing State Properties**:
- `podAddress: UInt32`
- `lotNo: UInt32`
- `lotSeq: UInt32`
- `ltk: Data` (long-term key, 16 bytes)
- `bleIdentifier: String` (CoreBluetooth UUID)
- `setupProgress: SetupProgress` (8 steps)
- `primeProgress: Double` (0.0-1.0)

**Delivery State Properties**:
- `reservoirLevel: Double` (units)
- `activeAlerts: [PodAlert]`
- `unfinalizedBolus: UnfinalizedDose?`
- `unfinalizedTempBasal: UnfinalizedDose?`
- `deliveryStatus: DeliveryStatus` (normal, tempBasal, suspended)

### 3.2 Omnipod Eros

| Property | Value |
|----------|-------|
| **Communication** | 433.91 MHz RF via RileyLink |
| **Authentication** | Nonce-based sequencing |
| **Encryption** | None (RF obfuscation only) |
| **Form Factor** | Disposable pod + PDM |
| **Gateway Required** | RileyLink, OrangeLink, EmaLink |

**Lifecycle State Model**:
```
Same as DASH: UNINITIALIZED → ... → RUNNING → FAULT/EXPIRED
```

**Pairing State Properties** (additional):
- `nonceState: NonceState` (lot/tid-derived)
- `rileyLinkState: RileyLinkState`
- `rileyLinkBattery: Int?`
- `lastValidFrequency: Double?`

### 3.3 Medtronic (5xx/7xx series)

| Property | Value |
|----------|-------|
| **Communication** | 916.5/868 MHz RF via RileyLink |
| **Authentication** | Pump ID addressing |
| **Encryption** | None |
| **Form Factor** | Durable pump |
| **Basal Precision** | Model-dependent (0.025-0.05 U/hr) |
| **History Reconciliation** | Required (no real-time delivery confirmation) |

**State Model**:
```
DISCONNECTED → TUNING → CONNECTED → IDLE → COMMANDING → CONFIRMING
```

**State Properties**:
- `pumpID: String` (6-digit)
- `pumpModel: MinimedPumpModel` (508, 512, 515, 522, 523, 554, 715, 722, 723, 754)
- `pumpRegion: PumpRegion` (NA, WW, CA - determines frequency)
- `batteryLevel: BatteryLevel`
- `reservoirLevel: Double`
- `lastHistoryPage: Int`
- `suspendState: SuspendState`
- `rileyLinkState: RileyLinkState`

### 3.4 Dana RS/i

| Property | Value |
|----------|-------|
| **Communication** | BLE direct |
| **Authentication** | Passkey + time-based encryption |
| **Encryption** | 3 modes: DEFAULT, RSv3, BLE5 |
| **Form Factor** | Durable pump |
| **Basal Precision** | 0.01 U/hr (Dana i) |
| **Bolus Rate** | Configurable (12/30/60 sec per unit) |

**State Model**:
```
DISCONNECTED → CONNECTING → AUTHENTICATING → ENCRYPTION_SETUP → READY → COMMANDING
```

**State Properties**:
- `pumpSerial: String`
- `pumpModel: DanaModel` (DanaR, DanaRS, DanaI)
- `encryptionMode: EncryptionMode`
- `firmwareVersion: String`
- `batteryLevel: Int`
- `reservoirLevel: Double`
- `basalProfile: [Double]` (24 rates)
- `tempBasalState: TempBasalState?`
- `bolusState: BolusState?`

---

## 4. Architectural Requirements

### 4.1 State Separation Requirement (REQ-ARCH-001)

**Statement**: AID implementations MUST use separate state types for CGM devices and pump devices. A single "connection state" type MUST NOT be used for both device categories.

**Rationale**: CGM and pump devices have fundamentally different:
- Capability sets (read-only vs bidirectional)
- Safety profiles (display vs delivery)
- Lifecycle models (sensor warmup vs pod activation)
- Error handling (retry vs uncertainty)

**Verification**:
- CGMPairingState and PumpPairingState are distinct types
- No inheritance relationship between them
- No casting between CGM and pump states

### 4.2 Capability Enumeration Requirement (REQ-ARCH-002)

**Statement**: Device state types MUST enumerate device-specific capabilities rather than using generic fields.

**Rationale**: Generic fields like "connectionStatus: String" lose type safety and don't capture device semantics.

**Example**:
```swift
// ❌ Anti-pattern
struct ConnectionPreviewState {
    var connectionStatus: String  // "connected", "pairing", etc.
    var deviceName: String
}

// ✅ Correct pattern
struct CGMPairingState {
    var sensorState: SensorState  // .warmingUp, .ready, .expired
    var authState: AuthState      // .pending, .authenticated
    var transmitterId: String
}

struct PumpPairingState {
    var setupProgress: SetupProgress  // 8-step enum
    var primeProgress: Double
    var podLot: UInt32
}
```

### 4.3 Vendor Extension Requirement (REQ-ARCH-003)

**Statement**: Device state types SHOULD support vendor-specific extensions without breaking the base interface.

**Rationale**: Different vendors have unique capabilities:
- Dexcom G7 has J-PAKE state, G6 has AES auth state
- Omnipod has pod lot/sequence, Medtronic has pump history
- Dana has encryption mode selection

**Pattern**:
```swift
protocol CGMPairingState {
    var transmitterId: String { get }
    var authState: AuthState { get }
    var signalStrength: Int { get }
}

struct DexcomG7PairingState: CGMPairingState {
    // Base properties
    var transmitterId: String
    var authState: AuthState
    var signalStrength: Int
    
    // G7-specific
    var jpakeRound: Int
    var sensorCode: String
    var certVerified: Bool
}
```

---

## 5. Gap Analysis

### GAP-ARCH-001: No Standardized Device Capability Taxonomy

**Description**: The AID ecosystem lacks a standardized taxonomy for device capabilities. Each project defines its own `PumpDescription`, `CGMType`, or protocol-specific structures with no interoperability.

**Impact**:
- Cannot compare device capabilities programmatically
- No standard way to communicate device limits to Nightscout
- New device support requires ad-hoc updates in each system

**Related**: GAP-PUMP-001

### GAP-ARCH-002: CGM/Pump State Models Conflated

**Description**: Some implementations (including T1Pal's `ConnectionPreviewState`) use a single state type for both CGM and pump pairing despite fundamentally different requirements.

**Impact**:
- Loss of type safety
- Incorrect UI for device-specific states
- Cannot validate state transitions properly
- Code maintainability issues

**Status**: Documented in [STATE-ARCHITECTURE-AUDIT.md](../../../t1pal-mobile-workspace/docs/architecture/STATE-ARCHITECTURE-AUDIT.md)

### GAP-ARCH-003: Vendor Capability Variations Undocumented

**Description**: While protocol details are documented (see pump/CGM deep dives), there's no unified capability matrix showing which features each vendor supports.

**Impact**:
- Difficult to plan feature development across vendors
- Users don't know what features their device supports
- No programmatic way to enable/disable features by device

---

## 6. Cross-Reference Matrix

| Device | Auth Type | Encryption | Gateway | Warmup | Max Duration |
|--------|-----------|------------|---------|--------|--------------|
| Dexcom G6 | AES-128 | Session | None | 2h | 10d sensor |
| Dexcom G7 | J-PAKE | Session | None | 30m | 10.5d |
| Libre 1 | None | None | NFC scan | 1h | 14d |
| Libre 2 | XOR cipher | FRAM + BLE | NFC pair | 1h | 14d |
| Libre 3 | ECDH | Full | None | 1h | 14d |
| MiaoMiao | None | None | BLE proxy | N/A | N/A |
| Omnipod DASH | EAP-AKA | AES-CCM | None | N/A | 80h |
| Omnipod Eros | Nonce | None | RileyLink | N/A | 80h |
| Medtronic | Pump ID | None | RileyLink | N/A | Durable |
| Dana RS | Passkey | AES | None | N/A | Durable |

---

## 7. Implementation Recommendations

### For T1Pal Screen Wizard

Per STATE-ARCHITECTURE-AUDIT.md, implement:

1. **CGMPairingState** with vendor-specific variants:
   - `DexcomG6PairingState`
   - `DexcomG7PairingState`
   - `LibrePairingState` (Libre 2/3)
   - `TransmitterProxyPairingState` (MiaoMiao/Bubble)

2. **PumpPairingState** with vendor-specific variants:
   - `OmnipodDashPairingState`
   - `OmnipodErosPairingState`
   - `MinimedPairingState`
   - `DanaPairingState`

3. **Separate StateEditor configurations** for each device category

### For Nightscout/AID Ecosystem

1. Add device capability fields to `devicestatus`:
   ```json
   {
     "pump": {
       "capabilities": {
         "tempBasal": true,
         "extendedBolus": false,
         "suspendResume": true,
         "basalPrecision": 0.05,
         "bolusPrecision": 0.05
       }
     },
     "cgm": {
       "capabilities": {
         "backfill": true,
         "calibration": false,
         "trendRate": true,
         "signalQuality": true
       }
     }
   }
   ```

2. Define JSON Schema for capability objects (new OpenAPI spec)

---

## References

- [Pump Communication Deep Dive](pump-communication-deep-dive.md)
- [CGM Data Sources Deep Dive](cgm-data-sources-deep-dive.md)
- [Dexcom BLE Protocol Deep Dive](dexcom-ble-protocol-deep-dive.md)
- [Libre Protocol Deep Dive](libre-protocol-deep-dive.md)
- [STATE-ARCHITECTURE-AUDIT.md](../../../t1pal-mobile-workspace/docs/architecture/STATE-ARCHITECTURE-AUDIT.md)
- [Pump Protocols Spec](../../specs/pump-protocols-spec.md)
