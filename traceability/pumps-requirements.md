# Pumps Requirements

Domain-specific requirements extracted from requirements.md.
See [requirements.md](requirements.md) for the index.

---

### REQ-PUMP-001: Pump Precision Constraints

**Statement**: AID controllers MUST round all insulin amounts (bolus and basal) to the pump's supported step size BEFORE sending commands.

**Rationale**: Pumps reject or truncate commands that don't match their precision constraints. Rounding rules should err on the side of safety.

**Scenarios**:
- Pump Command Precision (to be created)

**Verification**:
- Request 1.03U bolus on pump with 0.05U step → Verify command uses nearest supported value (1.00U or 1.05U per system rules)
- Request 0.07U/hr basal on pump with 0.05U step → Verify command uses nearest supported value
- Verify rounding follows pump-specific rules (Loop rounds to nearest; AAPS applies constraints per pump driver)

**Cross-System Status**:
- Loop: ✅ `roundToSupportedBolusVolume()`, `roundToSupportedBasalRate()`
- AAPS: ✅ `constraintChecker.applyBolusConstraints()`
- Trio: ✅ Inherits Loop's LoopKit implementation

---

---

### REQ-PUMP-002: Command Acknowledgment Verification

**Statement**: AID controllers MUST verify pump command acknowledgment before recording the dose as delivered.

**Rationale**: Network failures, BLE disconnections, and RF interference can cause commands to fail. Recording unverified doses corrupts IOB calculations.

**Scenarios**:
- Pump Command Verification (to be created)

**Verification**:
- Send bolus command → Verify pump acknowledges start (system-specific mechanism)
- Verify delivery amount matches request (within step precision)
- On timeout or error → Verify dose NOT recorded as delivered
- Verify uncertainty is signaled via platform-appropriate mechanism

**Cross-System Status**:
- Loop: ✅ `PumpManagerStatus.deliveryIsUncertain` flag indicates command uncertainty
- AAPS: ✅ `PumpEnactResult.success=false` and pump history reconciliation detect failures
- Trio: ✅ Inherits Loop's `deliveryIsUncertain` pattern

---

---

### REQ-PUMP-003: Bolus Progress Reporting

**Statement**: AID controllers SHOULD provide real-time bolus delivery progress to the user.

**Rationale**: Large boluses take minutes to deliver. Users need feedback during delivery and ability to cancel.

**Scenarios**:
- Bolus Progress UI (to be created)

**Verification**:
- Start 5U bolus → Verify progress updates during delivery
- Verify "Cancel" option available during delivery
- Verify final delivered amount reported

**Cross-System Status**:
- Loop: ✅ `createBolusProgressReporter()`
- AAPS: ✅ `EventOverviewBolusProgress` events
- Trio: ✅ Inherits Loop's pattern

---

---

### REQ-PUMP-004: History Reconciliation

**Statement**: AID controllers MUST periodically reconcile local dose records with pump history to detect manual doses and missed events.

**Rationale**: Users may deliver manual boluses via pump UI. Untracked doses corrupt IOB calculations and lead to incorrect dosing decisions.

**Scenarios**:
- Pump History Sync (to be created)

**Verification**:
- Deliver manual bolus via pump UI
- Verify controller detects dose within next loop cycle
- Verify IOB calculation includes manual dose

**Cross-System Status**:
- Loop: ✅ `PumpManagerDelegate.hasNewPumpEvents()` callback
- AAPS: ✅ `PumpSync.syncBolusWithPumpId()` for history-capable pumps
- Trio: ✅ Inherits Loop's pattern

---

---

### REQ-PUMP-005: Clock Drift Handling

**Statement**: AID controllers MUST detect and handle clock drift between controller and pump to maintain accurate dose timing.

**Rationale**: Pump clocks drift over time. Inaccurate timestamps affect IOB decay calculations and event ordering.

**Scenarios**:
- Pump Clock Sync (to be created)

**Verification**:
- Pump clock 5 minutes ahead → Verify controller compensates
- Verify IOB calculations use corrected timestamps
- Verify user notified of significant drift (>5 minutes)

**Cross-System Status**:
- Loop: ✅ `pumpManager.didAdjustPumpClockBy()` delegate
- AAPS: ✅ `canHandleDST()` and `timezoneOrDSTChanged()` methods

---

---

### REQ-PUMP-006: Connection Timeout Handling

**Statement**: Pump commands MUST timeout within a reasonable period (30-60 seconds) and report failure rather than hanging indefinitely.

**Rationale**: Stuck commands prevent loop iterations and leave delivery state uncertain.

**Scenarios**:
- Pump Timeout Handling (to be created)

**Verification**:
- Move pump out of range during command → Verify timeout within 60 sec
- Verify clear error message to user
- Verify loop can continue after timeout

**Cross-System Status**:
- Loop: ✅ Per-driver timeouts (typically 30 sec)
- AAPS: ✅ `waitForDisconnectionInSeconds()` and command timeouts
- Trio: ✅ Inherits Loop's pattern

---

## Insulin Curve Requirements

---

### REQ-PUMP-007: Nonce Management for Pod Commands

**Statement**: Controllers communicating with nonce-protected pumps (Omnipod DASH) MUST track and increment nonces correctly to prevent replay rejection.

**Rationale**: Omnipod DASH pods track the last received nonce and reject commands with stale or duplicate nonces. Incorrect nonce management causes command failures.

**Scenarios**:
- Pod Nonce Synchronization (to be created)

**Verification**:
- Send command with valid nonce → Verify acceptance
- Resend same nonce → Verify rejection
- After pod rejects nonce → Verify controller resynchronizes

**Cross-System Status**:
- Loop/Trio: ✅ `NonceResyncableMessageBlock` protocol handles nonce-bearing commands
- Source: `OmniBLE/OmnipodCommon/MessageBlocks/MessageBlock.swift`

---

---

### REQ-PUMP-008: BLE Session Establishment Security

**Statement**: BLE-connected pumps with session-based authentication MUST complete mutual authentication before accepting insulin delivery commands.

**Rationale**: Omnipod DASH uses EAP-AKA (Milenage) for session establishment; Dana RS uses passkey + time-based encryption. Commands sent without session establishment are rejected.

**Scenarios**:
- BLE Session Security (to be created)

**Verification**:
- Attempt command before session → Verify rejection
- Complete session establishment → Verify command acceptance
- Session timeout → Verify re-authentication required

**Cross-System Status**:
- Omnipod DASH: ✅ EAP-AKA with Milenage algorithm (3GPP standard)
- Dana RS: ✅ Three encryption modes (DEFAULT, RSv3, BLE5)
- Source: `OmniBLE/Bluetooth/Session/SessionEstablisher.swift`, `danars/encryption/BleEncryption.kt`

---

---

### REQ-PUMP-009: CRC Validation for Pump Messages

**Statement**: Controllers MUST validate CRC checksums on all pump response messages and reject messages with invalid checksums.

**Rationale**: RF/BLE transmission errors can corrupt message payloads. CRC validation prevents acting on corrupted commands or status.

**Scenarios**:
- Message Integrity Validation (to be created)

**Verification**:
- Receive valid message → Verify CRC passes
- Inject bit error → Verify CRC fails and message rejected
- Verify all pump drivers implement CRC validation

**Cross-System Status**:
- Omnipod DASH: ✅ Checksum in SetInsulinScheduleCommand
- Dana RS: ✅ CRC-16 with encryption-specific polynomials
- Medtronic: ✅ CRC validation in history page decoding
- Source: `SetInsulinScheduleCommand.swift`, `BleEncryption.kt:generateCrc()`

---

---

### REQ-PUMP-010: Bolus Delivery Rate Configuration

**Statement**: Controllers SHOULD respect pump-specific bolus delivery rates when calculating delivery times and progress updates.

**Rationale**: Different pumps deliver boluses at different rates (Omnipod: 0.025 U/s, Dana RS: configurable). Accurate delivery time estimation requires knowing the actual rate.

**Scenarios**:
- Bolus Progress Timing (to be created)

**Verification**:
- 5U bolus on Omnipod → Expect ~400 seconds (0.025 U/s × 200 pulses)
- 5U bolus on Dana RS Fast → Expect ~60 seconds
- Verify progress bar timing matches actual delivery

**Cross-System Status**:
- Omnipod DASH: 0.05U per 2 seconds (0.025 U/s)
- Dana RS: Configurable (12/30/60 sec per unit)
- Source: `Pod.swift:bolusDeliveryRate`, Dana RS packet handlers
- Trio: ✅ Inherits Loop's pattern

---

---
