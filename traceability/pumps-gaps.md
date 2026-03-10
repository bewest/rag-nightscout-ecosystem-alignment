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


### GAP-TANDEM-001: No Open-Source AID Control for Tandem Pumps

**Description**: Unlike Omnipod/Medtronic/Dana, Tandem t:slim X2 pumps cannot be controlled by open-source AID algorithms (AAPS, Loop, Trio).

**Affected Systems**: All open-source AID systems

**Evidence**:
- AAPS: Has `PumpType.TANDEM_T_SLIM_X2` enum but no pump driver plugin
- Loop: No TandemKit or similar driver
- Trio: No Tandem support
- Tandem uses proprietary, encrypted BLE protocol
- Control-IQ is FDA-cleared closed-source algorithm

**Impact**:
- Tandem users cannot use open-source AID
- Locked into Control-IQ algorithm settings
- Cannot customize dosing beyond Tandem's parameters
- Data access only via cloud (tconnectsync), not real-time

**Remediation**: 
Requires Tandem to open BLE protocol or provide control API. Unlikely due to:
- Proprietary IP in Control-IQ
- FDA regulatory concerns
- No community reverse-engineering effort

**Related**: 
- GAP-TCONNECT-001/002/003/004 (data sync gaps)
- `docs/10-domain/tandem-integration-inventory.md`

**Status**: Platform limitation (not remediable by community)

---

## Device Architecture Gaps (2026-02-03)

### GAP-ARCH-001: No Standardized Device Capability Taxonomy

**Scenario**: Cross-system device compatibility, feature development

**Description**: The AID ecosystem lacks a standardized taxonomy for device capabilities. Each project defines its own `PumpDescription`, `CGMType`, or protocol-specific structures with no interoperability format.

**Evidence**:
- Loop: `PumpManager.supportedMaximumBasalRatePerHour` property
- AAPS: `PumpDescription` class with 30+ properties
- Nightscout: No device capability schema in devicestatus

**Impact**:
- Cannot compare device capabilities programmatically across systems
- No standard way to communicate device limits to Nightscout
- Feature flags must be maintained manually per device
- New device support requires ad-hoc updates in each system

**Possible Solutions**:
1. Define JSON Schema for device capabilities (CGM and pump)
2. Add capability objects to Nightscout devicestatus
3. Create device registry with standardized attributes
4. OpenAPI specification for device capabilities

**Status**: Documentation complete, implementation pending

**Related**:
- [Device Capability Architecture Deep Dive](../docs/10-domain/device-capability-architecture-deep-dive.md)
- GAP-PUMP-001
- REQ-ARCH-001, REQ-ARCH-002

---

### GAP-ARCH-002: CGM/Pump State Models Conflated

**Scenario**: Device pairing UI, state management

**Description**: Some implementations use a single state type for both CGM and pump pairing despite fundamentally different requirements. This "ConnectionPreviewState Overloaded" anti-pattern loses type safety and device semantics.

**Evidence**:
- T1Pal `ConnectionPreviewState` used for both cgm-pairing and pump-pairing screens
- Generic fields like `connectionStatus: String` used instead of device-specific enums
- Same state editor configuration applied to different device types

**Impact**:
- Loss of type safety (compiler cannot enforce device-specific fields)
- Incorrect UI for device-specific states (no J-PAKE progress for G7, no prime progress for pods)
- Cannot validate state transitions properly
- Code maintainability issues as device support expands

**Possible Solutions**:
1. Create separate `CGMPairingState` and `PumpPairingState` protocols
2. Vendor-specific implementations (DexcomG7PairingState, OmnipodDashPairingState)
3. Protocol-oriented design with shared base for common fields
4. State machine validation per device type

**Status**: Documented in [STATE-ARCHITECTURE-AUDIT.md](../../t1pal-mobile-workspace/docs/architecture/STATE-ARCHITECTURE-AUDIT.md)

**Related**:
- [Device Capability Architecture Deep Dive](../docs/10-domain/device-capability-architecture-deep-dive.md)
- REQ-ARCH-001

---

### GAP-ARCH-003: Vendor Capability Variations Undocumented

**Scenario**: Feature planning, user documentation

**Description**: While protocol details are documented in deep dives, there's no unified capability matrix showing which features each vendor/model supports. Users and developers lack a quick reference for device-specific behavior.

**Evidence**:
- Dexcom G6 supports optional user calibration; G7 does not
- Omnipod supports temp basal but not extended bolus; Dana supports both
- Libre 2 requires NFC pairing; Libre 3 does not
- These differences scattered across multiple documents

**Impact**:
- Difficult to plan feature development across vendors
- Users don't know what features their device supports
- No programmatic way to enable/disable features by device
- QA testing matrix unclear

**Possible Solutions**:
1. Create capability matrix in terminology-matrix.md (done)
2. Add capability flags to device configuration types
3. Generate documentation from capability definitions
4. Add capability discovery to device pairing flows

**Status**: Documented

**Related**:
- [Device Capability Architecture Deep Dive](../docs/10-domain/device-capability-architecture-deep-dive.md)
- [Terminology Matrix - Device Capability Section](../mapping/cross-project/terminology-matrix.md#device-capability-architecture-2026-02-03)
- REQ-ARCH-003
