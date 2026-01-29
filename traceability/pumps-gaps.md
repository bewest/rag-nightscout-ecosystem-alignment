# Pumps Gaps

Domain-specific gaps extracted from gaps.md.
See [gaps.md](gaps.md) for the index.

---

### GAP-PUMP-001: No Standardized Pump Capability Exchange Format

**Scenario**: Cross-system pump compatibility, pump switching

**Description**: There is no standardized format for exchanging pump capabilities between systems. Each system defines its own `PumpDescription`, `PumpType`, or protocol-specific structures.

**Impact**:
- Cannot programmatically compare pump capabilities across systems
- No standard way to communicate pump limits to Nightscout
- Pump compatibility matrix must be maintained manually
- New pump support requires updates in each system

**Possible Solutions**:
1. Define standard JSON schema for pump capabilities
2. Add pump capabilities to Nightscout `devicestatus`
3. Create pump registry with standardized attributes

**Status**: Under discussion

**Related**:
- [Pump Communication Deep Dive](../docs/10-domain/pump-communication-deep-dive.md)
- REQ-PUMP-001

---

---

### GAP-PUMP-002: Extended Bolus Not Supported in Loop Ecosystem

**Scenario**: Extended/combo bolus interoperability

**Description**: Loop and Trio do not support extended (square wave) or dual wave (combo) boluses. AAPS supports extended boluses natively via `setExtendedBolus()` and can emulate via `FAKE_EXTENDED` temp basals.

**Evidence**:
- Loop `PumpManager` has no extended bolus methods
- AAPS `Pump` interface has `setExtendedBolus()` and `cancelExtendedBolus()`
- AAPS uploads extended boluses as temp basals with special type

**Impact**:
- Users switching from AAPS to Loop lose extended bolus capability
- Extended boluses from AAPS appear as temp basals in Loop/Trio
- COB calculations may differ between systems during extended bolus
- No interoperability for extended bolus commands

**Possible Solutions**:
1. Loop adds extended bolus support to PumpManager protocol
2. Define standard Nightscout representation for extended boluses
3. Document limitation for users considering system switch

**Status**: Under discussion (likely won't fix - Loop philosophy differs)

**Related**:
- [Pump Communication Deep Dive](../docs/10-domain/pump-communication-deep-dive.md)

---

---

### GAP-PUMP-003: TBR Duration Unit Inconsistency

**Scenario**: Temp basal interoperability, cross-system sync

**Description**: Temp basal duration units differ across systems:
- Loop: `TimeInterval` (seconds)
- AAPS: `durationInMinutes` (integer minutes)
- Nightscout: `duration` (minutes)

**Evidence**:
- Loop: `enactTempBasal(unitsPerHour: Double, for duration: TimeInterval, ...)`
- AAPS: `setTempBasalAbsolute(... durationInMinutes: Int, ...)`

**Impact**:
- Unit conversion errors possible during sync
- Off-by-one-minute errors in TBR end time
- Rounding differences may cause TBR overlap or gap

**Possible Solutions**:
1. All systems normalize to minutes for Nightscout interchange
2. Use ISO 8601 duration format (`PT30M`)
3. Explicit unit field in temp basal records

**Status**: Under discussion

**Related**:
- [Pump Communication Deep Dive](../docs/10-domain/pump-communication-deep-dive.md)
- GAP-TREAT-002 (duration unit inconsistency)

---

---

### GAP-PUMP-004: Pump Error Codes Not Normalized

**Scenario**: Error handling, debugging, alerting

**Description**: Each pump driver returns different error codes and messages. There is no cross-system error code taxonomy.

**Evidence**:
- Dana RS: `0x10` (max bolus), `0x20` (command error), `0x40` (speed error), `0x80` (insulin limit)
- Omnipod: `PodAlarmType` enum with pod-specific codes
- Medtronic: Hardware-specific alarm codes
- Loop: `PumpManagerError` with generic cases

**Impact**:
- Cannot create unified error handling or alerting
- Error messages vary widely across systems
- Debugging requires pump-specific knowledge
- No standard error taxonomy for Nightscout

**Possible Solutions**:
1. Define standard error categories (connectivity, delivery, reservoir, battery, etc.)
2. Map pump-specific codes to standard categories
3. Add structured error field to Nightscout treatments

**Status**: Under discussion

**Related**:
- [Pump Communication Deep Dive](../docs/10-domain/pump-communication-deep-dive.md)

---

---

### GAP-PUMP-005: No Standard for Delivery Uncertainty Reporting

**Scenario**: Safety, IOB accuracy, command verification

**Description**: When pump commands fail or timeout, the delivery state may be uncertain. Loop has `deliveryIsUncertain` flag, but there's no cross-system standard for reporting this state.

**Evidence**:
- Loop: `PumpManagerStatus.deliveryIsUncertain: Bool`
- AAPS: Implicit in `PumpEnactResult.success` and retry logic
- Nightscout: No field for delivery uncertainty

**Impact**:
- Uncertain deliveries may be double-counted or missed in IOB
- No way to communicate uncertainty to other clients
- Users may not understand why bolus "failed" but insulin was delivered
- Cannot audit delivery uncertainty events

**Possible Solutions**:
1. Add `deliveryUncertain` field to Nightscout treatments
2. Create `uncertainDelivery` event type
3. Standardize uncertainty resolution flow (verify with pump status)

**Status**: Under discussion

**Related**:
- [Pump Communication Deep Dive](../docs/10-domain/pump-communication-deep-dive.md)
- REQ-PUMP-002

---

---

### GAP-PUMP-006: Medtronic RF Protocol Lacks Encryption

**Scenario**: Pump communication security audit

**Description**: Medtronic pumps using RF communication (via RileyLink) have no encryption on the RF layer. Commands and responses are transmitted in plaintext.

**Source**: Analysis of MinimedKit and AAPS Medtronic driver

**Impact**:
- Replay attacks possible if attacker captures RF traffic
- Message tampering theoretically possible (though pump has safety limits)
- Unlike BLE pumps (DASH, Dana RS), no cryptographic protection

**Possible Solutions**:
1. Accept as known limitation (Medtronic discontinued Loop-compatible models)
2. Document security posture difference for users
3. Use as baseline for security comparison with newer protocols

**Status**: Documentation complete (inherent hardware limitation)

**Related**:
- [Pump Protocols Spec](../specs/pump-protocols-spec.md#4-cross-protocol-comparison)

---

---

### GAP-PUMP-007: Omnipod EAP-AKA Uses Non-Standard Milenage

**Scenario**: Cryptographic protocol analysis

**Description**: Omnipod DASH uses 3GPP Milenage algorithm for session establishment, but with non-standard operator keys (MILENAGE_OP constant) that are specific to Insulet.

**Source**: `OmniBLE/Bluetooth/Session/Milenage.swift`

**Impact**:
- Implementation requires knowledge of Insulet-specific constants
- Cannot use standard Milenage libraries without modification
- Reverse-engineering dependency for interoperability

**Possible Solutions**:
1. Document constants in protocol specification (done)
2. Accept as implementation detail

**Status**: Documented

**Related**:
- [Pump Protocols Spec - EAP-AKA](../specs/pump-protocols-spec.md#15-security-session-establishment-eap-aka)

---

---

### GAP-PUMP-008: Dana RS Encryption Type Detection

**Scenario**: Multi-model Dana pump support

**Description**: Dana pumps use three different encryption modes (DEFAULT, RSv3, BLE5) depending on pump model and firmware. Controllers must detect which mode to use during connection.

**Source**: `pump/danars/encryption/BleEncryption.kt`

**Impact**:
- Connection logic must handle all three modes
- CRC calculation differs by mode
- Upgrade path may require encryption mode transitions

**Possible Solutions**:
1. Document detection heuristics from AAPS implementation
2. Create mode-specific initialization sequences

**Status**: Under discussion

**Related**:
- [Pump Protocols Spec - Dana RS](../specs/pump-protocols-spec.md#2-dana-rsi-ble-protocol)

---

---

### GAP-PUMP-009: History Entry Size Varies by Medtronic Model

**Scenario**: Medtronic history reconciliation

**Description**: Medtronic history entry sizes vary by pump model (512, 522, 523+). A single history decoder must handle all variants using device-type-specific rules.

**Source**: `pump/medtronic/comm/history/pump/PumpHistoryEntryType.kt`

**Impact**:
- History parsing must be model-aware
- New pump models may introduce new entry formats
- Testing requires access to multiple pump models

**Possible Solutions**:
1. Document model-specific sizes in spec (done)
2. Create model detection and routing logic

**Status**: Documented

**Related**:
- [Pump Protocols Spec - Medtronic History](../specs/pump-protocols-spec.md#34-history-entry-types)

---

## Positive Findings

### FINDING-001: Shared exponential IOB formula across projects

**Discovery**: oref0 analysis revealed that the exponential insulin activity curve was directly sourced from Loop.

**Source**: `oref0:lib/iob/calculate.js#L125`
```javascript
// Formula source: https://github.com/LoopKit/Loop/issues/388#issuecomment-317938473
```

**Impact**:
- **oref0, AAPS, Trio, and Loop all use the same exponential insulin model**
- Direct IOB comparison is possible across all major AID systems
- This is a strong foundation for interoperability

**Related**:
- [oref0 Insulin Math](../mapping/oref0/insulin-math.md)
- [Loop Insulin Math](../mapping/loop/insulin-math.md)

---

### FINDING-002: oref0 outputs separate prediction curves (supports GAP-SYNC-002 resolution)

**Discovery**: oref0 (and AAPS/Trio) outputs four separate prediction curves in the algorithm output.

**Source**: `oref0:lib/determine-basal/determine-basal.js#L442-L449`
```javascript
rT.predBGs = {
    IOB: IOBpredBGs,   // Insulin-only prediction
    ZT: ZTpredBGs,     // Zero temp "what-if"
    COB: COBpredBGs,   // With carb absorption
    UAM: UAMpredBGs    // Unannounced meal
};
```

**Impact**:
- Provides reference implementation for what Loop could upload (GAP-SYNC-002)
- Enables detailed algorithm comparison across projects
- AAPS and Trio already upload these arrays to Nightscout `devicestatus.openaps`

**Related**:
- [GAP-SYNC-002](#gap-sync-002-effect-timelines-not-uploaded-to-nightscout)
- [oref0 Algorithm](../mapping/oref0/algorithm.md)

---

## Treatment Sync Gaps

---
