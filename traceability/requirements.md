# Requirements

This document captures requirements derived from scenarios. Each requirement is testable and linked to the scenarios that depend on it.

## Format

Requirements follow the pattern:
- **ID**: REQ-XXX
- **Statement**: The system MUST/SHOULD/MAY...
- **Rationale**: Why this matters
- **Scenarios**: Which scenarios depend on this
- **Verification**: How to test this

---

## Override Requirements

### REQ-001: Override Identity

**Statement**: Every override MUST have a unique, stable identifier that persists across system restarts and data synchronization.

**Rationale**: Required for supersession tracking and cross-system data correlation.

**Scenarios**: 
- [Override Supersede](../conformance/scenarios/override-supersede/)

**Verification**: 
- Create override, restart system, query override by ID
- Sync override to another system, verify ID preserved

---

### REQ-002: Override Supersession Tracking

**Statement**: When an override is superseded, the system MUST record:
1. The ID of the superseding override
2. The timestamp of supersession
3. Update the status to "superseded"

**Rationale**: Enables accurate historical queries and audit trails.

**Scenarios**:
- [Override Supersede](../conformance/scenarios/override-supersede/)

**Verification**:
- Create override A
- Create override B while A is active
- Query A and verify supersession fields

---

### REQ-003: Override Status Transitions

**Statement**: Override status MUST follow valid transitions:
- `active` → `completed` (duration elapsed)
- `active` → `cancelled` (user cancellation)
- `active` → `superseded` (new override activated)

**Rationale**: Prevents invalid states and ensures consistent behavior.

**Scenarios**:
- [Override Supersede](../conformance/scenarios/override-supersede/)

**Verification**:
- Attempt invalid transitions and verify rejection
- Verify valid transitions succeed

---

## Timestamp Requirements

### REQ-010: UTC Timestamps

**Statement**: All timestamps MUST be in ISO 8601 format with UTC timezone (Z suffix or +00:00).

**Rationale**: Eliminates timezone ambiguity in multi-device, multi-region scenarios.

**Scenarios**: All

**Verification**:
- Parse timestamps from all event types
- Verify timezone handling across DST boundaries

---

## Data Integrity Requirements

### REQ-020: Event Immutability

**Statement**: Once created, the core identity and timestamp of an event MUST NOT be modified. Only status and relationship fields may be updated.

**Rationale**: Ensures audit trail integrity and reproducible queries.

**Scenarios**: All

**Verification**:
- Attempt to modify event timestamp
- Verify rejection or versioning

---

## Sync and Deduplication Requirements

### REQ-030: Sync Identity Preservation

**Statement**: When uploading data to Nightscout, the system MUST include a client-generated identifier that survives the upload/download round-trip.

**Rationale**: Required for deduplication, updates, and correlation across sync cycles.

**Scenarios**: 
- [Sync Deduplication](../conformance/assertions/sync-deduplication.yaml)

**Verification**: 
- Upload treatment with `syncIdentifier` or `identifier`
- Download treatment by server `_id`
- Verify client identifier is preserved

---

### REQ-031: Self-Entry Exclusion

**Statement**: When downloading treatments, the system SHOULD exclude entries it previously uploaded to avoid duplicate processing.

**Rationale**: Prevents feedback loops where a controller re-processes its own data.

**Scenarios**:
- [Sync Deduplication](../conformance/assertions/sync-deduplication.yaml)

**Verification**:
- Upload carbs with `enteredBy=ControllerX`
- Download carbs with filter `enteredBy[$ne]=ControllerX`
- Verify uploaded entry is excluded

---

### REQ-032: Incremental Sync Support

**Statement**: The system SHOULD support incremental synchronization using server-provided modification timestamps (`srvModified`).

**Rationale**: Reduces bandwidth and processing overhead for frequent sync operations.

**Scenarios**:
- [Sync Deduplication](../conformance/assertions/sync-deduplication.yaml)

**Verification**:
- Fetch `/lastModified` endpoint
- Request `/history/{timestamp}` endpoint
- Verify only newer records returned

---

### REQ-033: Server Deduplication

**Statement**: When receiving a POST for a document that matches existing deduplication criteria, the server MUST return the existing document with HTTP 200 (not create a duplicate with 201).

**Rationale**: Prevents data duplication from retries or multi-device scenarios.

**Scenarios**:
- [Sync Deduplication](../conformance/assertions/sync-deduplication.yaml)

**Verification**:
- POST treatment with `created_at=T1, eventType=Bolus`
- POST identical treatment again
- Verify HTTP 200, document count = 1

---

### REQ-034: Cross-Controller Coexistence

**Statement**: Multiple controllers MUST be able to upload data to the same Nightscout instance without interfering with each other's records.

**Rationale**: Common scenario where user has Loop on phone and AAPS on backup device.

**Scenarios**:
- [Sync Deduplication](../conformance/assertions/sync-deduplication.yaml)

**Verification**:
- Upload treatment with `enteredBy=Loop`
- Upload treatment with `enteredBy=AAPS`
- Verify both exist independently

---

### REQ-035: Conflict Detection

**Statement**: When updating a document, the system SHOULD support optimistic concurrency via `If-Unmodified-Since` header, returning HTTP 412 if document was modified by another client.

**Rationale**: Prevents lost updates in multi-client scenarios.

**Scenarios**:
- [Sync Deduplication](../conformance/assertions/sync-deduplication.yaml)

**Verification**:
- Client A reads document, captures `srvModified`
- Client B updates document
- Client A attempts update with `If-Unmodified-Since` header
- Verify HTTP 412 Precondition Failed

---

### REQ-036: Batch Response Order Preservation

**Statement**: When processing a batch POST request (array of documents), the server MUST return response items in the same order as the request items.

**Rationale**: Loop and other clients use positional matching (`zip()`) to map response `_id` values back to local `syncIdentifier` values. Out-of-order responses cause incorrect ID mappings, leading to updates/deletes targeting wrong records.

**Scenarios**:
- [Batch Upload](../conformance/assertions/batch-upload.yaml)

**Verification**:
- POST array of 5 treatments with distinct `created_at` values
- Verify response array has same length and order as request
- Verify each response item's `created_at` matches corresponding request item

**Code References**:
- Loop: `NightscoutService.swift:209-214` - uses `zip(syncIdentifiers, createdObjectIds)`
- Nightscout: `lib/server/treatments.js:21` - uses `async.eachSeries()` (sequential processing preserves order)

**Status**: Verified - Nightscout API v1 uses sequential processing which preserves order.

**Gap Reference**: GAP-BATCH-002

---

## Treatment Sync Requirements

### REQ-040: Bolus Amount Preservation

**Statement**: When syncing a bolus treatment, the `insulin` amount MUST be preserved exactly (to 0.01U precision) during upload and download.

**Rationale**: Insulin amounts directly affect IOB calculations; any loss of precision impacts dosing safety.

**Scenarios**:
- [Treatment Sync](../conformance/assertions/treatment-sync.yaml)

**Verification**:
- Create bolus with `insulin: 2.35`
- Upload to Nightscout
- Download from Nightscout
- Verify `insulin == 2.35`

---

### REQ-041: Carb Amount Preservation

**Statement**: When syncing a carb treatment, the `carbs` amount MUST be preserved exactly (to 0.1g precision) during upload and download.

**Rationale**: Carb amounts directly affect COB calculations and dosing recommendations.

**Scenarios**:
- [Treatment Sync](../conformance/assertions/treatment-sync.yaml)

**Verification**:
- Create carbs with `carbs: 45.5`
- Upload to Nightscout
- Download from Nightscout
- Verify `carbs == 45.5`

---

### REQ-042: Treatment Timestamp Accuracy

**Statement**: Treatment timestamps MUST be preserved with millisecond precision during sync.

**Rationale**: Timestamp precision is critical for:
- Deduplication (same event from multiple sources)
- IOB decay calculation timing
- Event ordering in timeline displays

**Scenarios**:
- [Treatment Sync](../conformance/assertions/treatment-sync.yaml)

**Verification**:
- Create treatment with timestamp `2026-01-17T12:34:56.789Z`
- Upload and download
- Verify timestamp matches exactly

---

### REQ-043: Automatic Bolus Flag

**Statement**: When uploading an automatic bolus (SMB or auto-bolus), the system MUST set `automatic: true` to distinguish from manual boluses.

**Rationale**: Distinguishing automatic from manual boluses is essential for:
- User review of algorithm behavior
- Analytics and reporting
- Troubleshooting dosing decisions

**Scenarios**:
- [Treatment Sync](../conformance/assertions/treatment-sync.yaml)

**Verification**:
- Algorithm delivers SMB
- Verify uploaded treatment has `automatic: true`
- Manual bolus should have `automatic: false` or undefined

---

### REQ-044: Duration Unit Normalization

**Statement**: When uploading temp basal or eCarbs with duration, the system MUST convert to Nightscout's expected unit (minutes) before upload.

**Rationale**: Duration unit mismatch causes order-of-magnitude errors in temp basal and carb absorption timing.

**Scenarios**:
- [Treatment Sync](../conformance/assertions/treatment-sync.yaml)

**Automated Tests**: `tools/test_conversions.py` - `aaps-temp-basal-duration-*`, `aaps-ecarbs-duration-4hr`

**Verification**:
- Create temp basal with 30-minute duration (internal units)
- Upload to Nightscout
- Verify `duration == 30` (minutes)

---

### REQ-045: Treatment Sync Identity Round-Trip

**Statement**: A client-generated sync identifier MUST survive the upload/download round-trip unchanged.

**Rationale**: Required for:
- Deduplication on retry
- Correlating local and remote records
- Updating existing treatments

**Scenarios**:
- [Treatment Sync](../conformance/assertions/treatment-sync.yaml)

**Verification**:
- Upload treatment with `syncIdentifier: "abc-123"`
- Download treatment
- Verify sync identifier preserved

---

### REQ-046: Absorption Time Unit Conversion

**Statement**: When uploading carb entries with absorption time, the system MUST convert from internal units (typically seconds) to Nightscout's expected unit (minutes).

**Rationale**: Absorption time directly affects carb effect predictions and COB calculations.

**Scenarios**:
- [Treatment Sync](../conformance/assertions/treatment-sync.yaml)

**Automated Tests**: `tools/test_conversions.py` - `loop-absorption-time-3hr`, `loop-absorption-time-2hr`

**Verification**:
- Create carb with internal `absorptionTime: 10800` (seconds = 3 hours)
- Convert to Nightscout format: `absorptionTime: 180` (minutes)
- Upload to Nightscout
- Verify `absorptionTime == 180` (minutes)

---

## CGM Data Source Requirements

### REQ-050: Source Device Attribution

**Statement**: Every CGM entry uploaded to Nightscout MUST include a `device` field identifying the uploader application and hardware.

**Rationale**: Source attribution is essential for debugging data quality issues, identifying duplicate uploaders, and tracking data provenance.

**Scenarios**:
- [CGM Entry Upload](../conformance/assertions/cgm-upload.yaml)

**Verification**:
- Upload CGM entry
- Verify `device` field is present
- Verify `device` identifies app (e.g., "xDrip-DexcomG6")

---

### REQ-051: UTC Timestamp for CGM Entries

**Statement**: CGM entry timestamps MUST be epoch milliseconds in UTC, stored in the `date` field.

**Rationale**: Timezone-agnostic storage enables consistent cross-timezone queries and prevents DST-related issues.

**Scenarios**:
- All CGM scenarios

**Verification**:
- Upload entry with `date` field
- Verify timestamp is epoch milliseconds
- Verify `dateString` is UTC (Z suffix)

---

### REQ-052: Follower Source Indication

**Statement**: CGM entries sourced from follower mode (Nightscout, Dexcom Share, LibreLinkUp) SHOULD indicate follower mode in the `device` field.

**Rationale**: Distinguishing direct sensor data from cloud-sourced data is critical for latency analysis and duplicate detection.

**Scenarios**:
- [CGM Follower Mode](../conformance/assertions/cgm-follower.yaml)

**Verification**:
- Configure app in follower mode
- Upload entry
- Verify `device` includes "follower" or source indication

---

### REQ-053: Calibration Provenance (Proposed)

**Statement**: CGM entries SHOULD include metadata indicating which calibration algorithm produced the glucose value.

**Rationale**: Different calibration algorithms (xDrip Original, Native, WebOOP) can produce significantly different glucose values from the same raw sensor data. Tracking calibration source enables quality assessment.

**Scenarios**:
- [CGM Calibration Validation](../conformance/assertions/cgm-calibration.yaml)

**Verification**:
- Upload entry with calibration metadata
- Verify calibration algorithm is identifiable

**Note**: This is a proposed extension. Current Nightscout schema does not support calibration metadata.

---

### REQ-054: Duplicate Prevention via UUID

**Statement**: CGM data producers SHOULD generate a client-side UUID for each reading and use upsert semantics to prevent duplicates.

**Rationale**: Network retries, multiple uploaders, and cloud-to-cloud sync can create duplicate entries. UUID-based deduplication ensures data integrity.

**Scenarios**:
- [CGM Deduplication](../conformance/assertions/cgm-dedup.yaml)

**Verification**:
- Upload entry with `uuid` field
- Re-upload same entry
- Verify only one entry exists in Nightscout

---

### REQ-055: Raw Sensor Value Preservation

**Statement**: When raw sensor values are available, CGM entries SHOULD include `filtered` and `unfiltered` fields.

**Rationale**: Raw values enable recalibration, algorithm comparison, and retrospective analysis. iOS systems typically do not expose raw values.

**Scenarios**:
- [CGM Raw Data](../conformance/assertions/cgm-raw.yaml)

**Verification**:
- Upload entry from xDrip+
- Verify `filtered` and `unfiltered` fields present
- Verify values are numeric sensor readings

---

### REQ-056: Sensor Age Tracking

**Statement**: CGM entries SHOULD include sensor age at reading time when available from the transmitter.

**Rationale**: Sensor accuracy varies with age. Tracking sensor age enables quality assessment and sensor change detection.

**Scenarios**:
- [CGM Sensor Lifecycle](../conformance/assertions/cgm-sensor.yaml)

**Verification**:
- xDrip+ local web server includes `sensor.age` and `sensor.start`
- Verify sensor age is trackable

**Note**: This is a proposed extension. Current Nightscout entries schema does not include sensor age.

---

### REQ-057: Bridge Device Identification

**Statement**: When CGM data is received via a bridge device (MiaoMiao, Bubble, etc.), the bridge type SHOULD be distinguishable from the transmitter type.

**Rationale**: Hardware troubleshooting requires knowing both the bridge device and the underlying sensor/transmitter.

**Scenarios**:
- [CGM Bridge Device](../conformance/assertions/cgm-bridge.yaml)

**Verification**:
- Configure MiaoMiao with Libre sensor
- Upload entry
- Verify `device` indicates bridge type

**Note**: This is a proposed extension. Current `device` field format is not standardized.

---

## Remote Command Requirements

### REQ-REMOTE-001: Remote Command Authentication

**Statement**: All remote commands that can affect insulin delivery MUST require cryptographic authentication before execution.

**Rationale**: Remote commands can cause dangerous hypo/hyperglycemia. Authentication prevents unauthorized command execution.

**Scenarios** (proposed):
- Remote Bolus (to be created)
- Remote Override (to be created)

**Verification**:
- Send bolus command without valid OTP/encryption → Verify rejection
- Send bolus command with valid authentication → Verify execution
- Verify authentication failure is logged

**Cross-System Status**:
- Trio: ✅ All commands AES-256-GCM encrypted
- Loop: ⚠️ OTP required for bolus/carbs, **not for overrides** (GAP-REMOTE-001)
- AAPS: ✅ Phone whitelist + OTP+PIN for all commands

---

### REQ-REMOTE-002: Remote Command Replay Protection

**Statement**: Remote command systems MUST prevent replay attacks where captured commands are re-transmitted.

**Rationale**: Replayed bolus commands could cause dangerous insulin stacking.

**Scenarios** (proposed):
- Remote Bolus Replay (to be created)

**Verification**:
- Capture valid remote command
- Replay command after delay → Verify rejection
- Verify replay attempt is logged

**Mechanisms**:
- Trio: Timestamp within ±10 minutes
- Loop: Expiration date + duplicate tracking + OTP tracking (recent passwords stored)
- AAPS: Command timeout + min bolus distance

---

### REQ-REMOTE-003: Remote Bolus Safety Limits

**Statement**: Remote bolus commands MUST be rejected if they would exceed configured safety limits (max bolus, max IOB).

**Rationale**: Remote commands should never bypass local safety guards.

**Scenarios** (proposed):
- Remote Bolus Limits (to be created)

**Verification**:
- Configure max bolus = 5U
- Send remote bolus of 6U → Verify rejection with reason
- Send remote bolus that would exceed max IOB → Verify rejection

**Cross-System Status**:
- Trio: ✅ Enforced in remote handler (max bolus, max IOB, 20% recent rule)
- Loop: ✅ Enforced downstream in dosing logic
- AAPS: ✅ ConstraintChecker applied to all commands

---

### REQ-REMOTE-004: Remote Command Audit Trail

**Statement**: All remote command attempts (successful and failed) MUST be logged with timestamp, source identifier, command type, and outcome.

**Rationale**: Audit trails enable incident investigation and security monitoring.

**Scenarios** (proposed):
- Remote Command Audit (to be created)

**Verification**:
- Send remote bolus command
- Verify log entry includes: timestamp, remote address/phone, amount, success/failure, reason if failed

---

### REQ-REMOTE-005: Remote Command Source Tracking

**Statement**: Treatments created via remote command SHOULD indicate the remote origin in the `enteredBy` or equivalent field.

**Rationale**: Distinguishing remote vs local entries enables caregiver activity analysis.

**Scenarios** (proposed):
- Remote Treatment Provenance (to be created)

**Verification**:
- Send remote bolus command
- Query resulting treatment
- Verify `enteredBy` indicates remote origin (e.g., "Loop (via remote command)")

**Cross-System Status**:
- Trio: ✅ `CarbsEntry.manual` or explicit "Remote Command" note
- Loop: ✅ `enteredBy = "Loop (via remote command)"`
- AAPS: ✅ `Sources.SMS` enum value

---

### REQ-REMOTE-006: Remote Command Toggle

**Statement**: Remote command functionality MUST be disabled by default and require explicit user action to enable.

**Rationale**: Security-sensitive features should require opt-in.

**Scenarios** (proposed):
- Remote Command Enable (to be created)

**Verification**:
- Fresh installation → Verify remote commands disabled
- Enable remote commands → Verify commands are processed
- Disable remote commands → Verify commands are rejected

**Cross-System Status**:
- Trio: ✅ `isTrioRemoteControlEnabled` setting
- Loop: ✅ Requires OTP setup (implicit enable)
- AAPS: ✅ `BooleanKey.SmsAllowRemoteCommands` setting

---

## Pump Communication Requirements

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

### REQ-INS-001: Consistent Exponential Model Across Systems

**Statement**: AID systems using the exponential insulin model MUST use the same mathematical formula to ensure IOB calculations are comparable.

**Rationale**: Different formulas produce different IOB decay curves, leading to inconsistent dosing decisions when comparing systems or switching between them.

**Scenarios**:
- IOB Comparison (to be created)

**Verification**:
- Given identical bolus history and DIA settings
- Calculate IOB using Loop, oref0, AAPS, and Trio
- Verify IOB values match within 0.01U precision

**Cross-System Status**:
- Loop: ✅ Original exponential formula
- oref0: ✅ Copied from Loop (explicitly credited)
- AAPS: ✅ Port of oref0
- Trio: ✅ Uses oref0 JavaScript

**Source Reference**: `oref0:lib/iob/calculate.js#L125` cites Loop as formula source.

---

### REQ-INS-002: DIA Minimum Enforcement

**Statement**: AID systems MUST enforce a minimum DIA of 5 hours for exponential insulin models to prevent dangerously fast IOB decay.

**Rationale**: DIA values below 5 hours cause insulin to "disappear" from IOB calculations before it finishes acting, leading to insulin stacking and hypoglycemia.

**Scenarios**:
- DIA Validation (to be created)

**Verification**:
- Attempt to set DIA = 3 hours with exponential model → Verify rejection or auto-correction to 5 hours
- Verify user notification when DIA is adjusted

**Cross-System Status**:
- Loop: ✅ Fixed DIA per model preset (5-6 hours)
- oref0: ✅ `requireLongDia` flag enforces 5h minimum
- AAPS: ✅ `hardLimits.minDia()` returns 5.0
- Trio: ✅ Via oref0 enforcement

---

### REQ-INS-003: Peak Time Configuration Bounds

**Statement**: When custom peak time is enabled, AID systems MUST clamp the value to valid ranges to prevent unrealistic insulin curves.

**Rationale**: Peak times outside physiological ranges produce unrealistic insulin activity curves that lead to dangerous predictions.

**Scenarios**:
- Peak Time Validation (to be created)

**Verification**:
- Rapid-acting: Verify peak clamped to 50-120 min range
- Ultra-rapid: Verify peak clamped to 35-100 min range
- Verify user notification when peak is adjusted

**Cross-System Status**:
- oref0: ✅ Explicit min/max checks in `iobCalcExponential()`
- AAPS: ✅ Free Peak plugin with hard limits
- Trio: ✅ Via oref0 enforcement
- Loop: ✅ Fixed peaks per preset (no custom)

---

### REQ-INS-004: Activity Calculation for BGI

**Statement**: AID systems MUST calculate insulin activity (rate of action) alongside IOB to enable Blood Glucose Impact (BGI) predictions.

**Rationale**: BGI = -activity × ISF × 5 is used to predict how much glucose will drop in the next 5 minutes. Without activity, predictions are incomplete.

**Scenarios**:
- BGI Calculation (to be created)

**Verification**:
- Calculate activity from insulin curve formula
- Compute BGI = -activity × ISF × 5
- Verify BGI matches observed glucose change (within noise)

**Cross-System Status**:
- Loop: ✅ Via `percentEffectRemaining` derivative
- oref0: ✅ `activityContrib` calculated alongside `iobContrib`
- AAPS: ✅ `result.activityContrib` in `iobCalcForTreatment()`
- Trio: ✅ Via oref0

---

### REQ-INS-005: Insulin Model Metadata in Treatments (Proposed)

**Statement**: Treatments uploaded to Nightscout SHOULD include insulin model metadata (curve type, peak time, DIA) to enable historical IOB reconstruction.

**Rationale**: Without model metadata, historical IOB values cannot be reproduced, limiting retrospective analysis and debugging.

**Scenarios**:
- Treatment Upload Validation (to be created)

**Verification**:
- Upload bolus treatment
- Verify presence of `insulinModel`, `insulinPeak`, `insulinDIA` fields
- Download treatment and verify metadata preserved

**Cross-System Status**:
- Loop: ❌ Not implemented (gap)
- oref0: ❌ Not implemented (gap)
- AAPS: ⚠️ Partial via `insulinConfiguration` in database
- Trio: ❌ Not implemented (gap)

**Gap Reference**: GAP-INS-001

---

## BLE Protocol Requirements

### REQ-BLE-001: Message CRC Validation

**Statement**: All BLE messages with CRC-16 suffix MUST be validated before processing. Messages with invalid CRC MUST be rejected.

**Rationale**: Ensures data integrity over wireless transmission. CRC-16 CCITT (XModem) is the standard used by Dexcom transmitters.

**Scenarios**:
- CGM Data Reception
- Backfill Data Parsing

**Verification**:
- Compute CRC-16 of payload (excluding last 2 bytes)
- Compare with CRC in message (little-endian)
- Verify invalid CRC causes message rejection

**Cross-System Status**:
- CGMBLEKit: ✅ `Data.isCRCValid`
- xdrip-js: ✅ CRC validation in message parsing
- DiaBLE: ✅ CRC validation implemented

---

### REQ-BLE-002: Authentication Before Data Access

**Statement**: BLE clients MUST complete authentication handshake before requesting glucose data. Unauthenticated requests MUST be rejected by the transmitter.

**Rationale**: Ensures only authorized devices can read sensitive health data.

**Scenarios**:
- Initial Pairing
- Reconnection

**Verification**:
- Attempt glucose request before auth: verify failure
- Complete auth handshake: verify glucose request succeeds

---

### REQ-BLE-003: Glucose Value Extraction

**Statement**: Glucose values MUST be extracted from the lower 12 bits of the glucose field. The upper 4 bits (G6) or specific flag byte (G7) contain display-only flag.

**Rationale**: Ensures consistent glucose interpretation across implementations.

**Scenarios**:
- Real-time Glucose Reading
- Backfill Data Parsing

**Verification**:
- Parse glucose message
- Extract `glucose = glucoseBytes & 0x0FFF`
- Verify display-only flag extraction

---

### REQ-BLE-004: Trend Rate Conversion

**Statement**: Trend rate values MUST be interpreted as signed Int8 divided by 10, yielding mg/dL per minute. Value 0x7F (127) indicates unavailable.

**Rationale**: Standardizes trend rate interpretation for consistent trend arrow display.

**Scenarios**:
- Trend Arrow Display
- Rate of Change Alerting

**Verification**:
- Parse trend byte as signed Int8
- Divide by 10 for mg/dL/min
- Handle 0x7F as nil/unavailable

---

### REQ-BLE-005: Timestamp Calculation

**Statement**: Glucose timestamps MUST be calculated as activation date plus transmitter time (seconds). Activation date is derived from `Date.now() - currentTime * 1000`.

**Rationale**: Enables accurate historical data reconstruction and correlation with other events.

**Scenarios**:
- Glucose History Display
- Data Export

**Verification**:
- Request TransmitterTime message
- Calculate activation date
- Verify glucose timestamps are consistent

---

### REQ-BLE-006: Algorithm State Interpretation

**Statement**: Algorithm/calibration state values MUST be interpreted according to the G6 or G7 state machine. Only specific states indicate reliable glucose readings.

**Rationale**: Prevents display of unreliable readings during warmup, calibration errors, or sensor failures.

**Scenarios**:
- Glucose Display Logic
- Alerting Decisions

**Verification**:
- Parse algorithm state byte
- Map to known state enum
- Verify `hasReliableGlucose` logic matches state

---

## Carb Absorption Requirements

### REQ-CARB-001: COB Time Granularity Documentation

**Statement**: Systems SHOULD document their COB calculation time granularity in devicestatus or algorithm metadata.

**Rationale**: Different systems use different time granularities (oref0 uses 5-minute intervals; Loop uses variable modeling). Without knowing the granularity, cross-system COB comparison is unreliable.

**Scenarios**:
- COB Display
- Cross-System Data Analysis

**Verification**:
- Check devicestatus or documentation for stated granularity
- Verify granularity matches documented behavior
- Note differences across systems

---

### REQ-CARB-002: Absorption Model Reporting

**Statement**: Systems SHOULD report the active absorption model (Parabolic, Linear, PiecewiseLinear) in devicestatus uploads.

**Rationale**: Without knowing which model was used, COB values cannot be correctly interpreted by downstream systems.

**Scenarios**:
- Cross-System Data Analysis
- Algorithm Comparison

**Verification**:
- Upload devicestatus with COB
- Verify `absorptionModel` field present
- Confirm model name matches active configuration

---

### REQ-CARB-003: Extended Carbs Distinction

**Statement**: Extended carbs (duration > 0) MUST be clearly distinguished from instant carbs in data representation and must specify the duration in a consistent unit.

**Rationale**: Systems that don't support eCarbs may misinterpret duration carbs as instant, leading to incorrect predictions.

**Scenarios**:
- eCarb Entry
- Cross-Platform Sync

**Verification**:
- Create eCarb entry with duration
- Sync to Nightscout
- Verify `duration` field preserved
- Import to iOS app and verify handling

---

### REQ-CARB-004: Carb Sensitivity Factor Calculation

**Statement**: CSF (Carb Sensitivity Factor) calculation MUST use the formula: `CSF = ISF / CR` (mg/dL per gram of carbs).

**Rationale**: Consistent CSF calculation ensures glucose effects from carbs are comparable across systems.

**Scenarios**:
- Glucose Prediction
- Bolus Calculation

**Verification**:
- Calculate CSF in multiple systems with same ISF/CR
- Verify results match
- Test with varying ISF and CR schedules

---

### REQ-CARB-005: Per-Entry Absorption Time (Where Supported)

**Statement**: Systems that support per-entry absorption time (Loop, Trio) SHOULD preserve this field during sync. Systems using profile-based absorption (oref0, AAPS) MAY ignore this field.

**Rationale**: Different foods absorb at different rates. Loop/Trio support per-entry `absorptionTime`; oref0/AAPS use profile-based defaults and do not accept per-entry overrides.

**Scenarios**:
- Mixed Meal Entry (Loop/Trio)
- Cross-Platform Sync

**Verification**:
- Create carb entry with custom absorption time in Loop/Trio
- Verify COB decay follows specified time
- Sync to Nightscout and verify `absorptionTime` field preserved
- Note that oref0/AAPS will use profile-based absorption regardless

---

### REQ-CARB-006: COB Maximum Limits

**Statement**: COB hard limits SHOULD be configurable and MUST be clearly documented per system.

**Rationale**: Different limits (e.g., oref0's 120g cap vs Loop's no cap) can cause confusion and unexpected behavior.

**Scenarios**:
- Large Meal Entry
- COB Display

**Verification**:
- Enter carbs exceeding maxCOB limit
- Verify COB is capped at documented maximum
- Confirm limit is surfaced in UI or logs

---

## Libre CGM Protocol Requirements

### REQ-LIBRE-001: Sensor Type Detection from PatchInfo

**Statement**: Systems reading Libre sensors MUST correctly identify sensor type from the `patchInfo` first byte using the documented mapping (0xDF/0xA2→Libre1, 0x9D/0xC5→Libre2, etc.).

**Rationale**: Correct sensor type determines encryption requirements, FRAM layout interpretation, and BLE protocol selection.

**Scenarios**:
- NFC Sensor Scan
- BLE Connection

**Verification**:
- Scan known sensor types and verify detection
- Test edge cases (Libre 2+ EU: 0xC6, Gen2 US: 0x2C)

---

### REQ-LIBRE-002: FRAM CRC Validation

**Statement**: Before parsing FRAM data, systems MUST validate CRC-16 checksums for header (bytes 0-1), body (bytes 24-25), and footer (bytes 320-321).

**Rationale**: Invalid CRC indicates corrupted or improperly decrypted data, which would produce incorrect glucose values.

**Scenarios**:
- NFC FRAM Read
- Transmitter Bridge Data

**Verification**:
- Read FRAM and verify CRC validation logic
- Test with intentionally corrupted data

---

### REQ-LIBRE-003: Libre 2 FRAM Decryption

**Statement**: Systems reading Libre 2/US14day sensors MUST decrypt FRAM using the documented XOR cipher with sensor UID and patchInfo as inputs.

**Rationale**: Libre 2 FRAM is encrypted; reading raw data produces invalid glucose values.

**Scenarios**:
- Libre 2 NFC Scan
- Transmitter Bridge Decryption

**Verification**:
- Decrypt known encrypted FRAM and verify glucose values
- Verify CRC passes after decryption

---

### REQ-LIBRE-004: BLE Streaming Authentication

**Statement**: For Libre 2 BLE streaming, systems MUST use the enable streaming NFC command (0xA1 0x1E) with correct unlock payload to obtain the sensor's MAC address.

**Rationale**: BLE streaming requires prior NFC pairing to establish cryptographic context.

**Scenarios**:
- Libre 2 BLE Pairing
- Streaming Reconnection

**Verification**:
- Execute enable streaming command
- Verify 6-byte MAC address response
- Verify BLE connection succeeds

---

### REQ-LIBRE-005: Libre 3 Security Protocol

**Statement**: Libre 3 connections MUST complete the security handshake (challenge-response with ECDH key exchange) before receiving glucose data.

**Rationale**: Libre 3 is fully encrypted; data is unreadable without completing security protocol.

**Scenarios**:
- Libre 3 BLE Connection
- Reconnection after disconnect

**Reference**: [Libre Protocol Deep Dive - Security Handshake Sequence](../docs/10-domain/libre-protocol-deep-dive.md#security-handshake-sequence)

**Verification**:
- Monitor security command sequence on characteristic 2198:
  - Write `0x11` (readChallenge) to initiate
  - Receive `0x08 0x17` (challengeLoadDone + status)
  - Exchange challenge data on 22CE
  - Write `0x08` (challengeLoadDone) to confirm
- Verify glucose data received on 177A after handshake completes

---

### REQ-LIBRE-006: Glucose Data Quality Flags

**Statement**: Systems SHOULD interpret the data quality flags in glucose readings and exclude readings with `hasError=true` or invalid quality codes.

**Rationale**: Sensor errors (signal disturbance, calibration issues) produce unreliable glucose values.

**Scenarios**:
- CGM Data Display
- Closed-Loop Input

**Verification**:
- Parse readings with various quality flags
- Verify error readings are filtered or flagged

---

## Template

```markdown
### REQ-XXX: [Title]

**Statement**: [The system MUST/SHOULD/MAY...]

**Rationale**: [Why this matters]

**Scenarios**: 
- [Link to scenarios]

**Verification**: 
- [Test steps]
```

---

## Remote Caregiver Requirements

### REQ-REMOTE-007: Command Status Display

**Statement**: Caregiver apps MUST display the current status of remote commands to users, including pending, in-progress, success, and error states.

**Rationale**: Caregivers need visibility into whether commands were received and executed successfully to avoid duplicate commands or missed treatments.

**Scenarios**:
- Remote Bolus Delivery
- Remote Carb Entry

**Verification**:
- Send remote command
- Verify status updates displayed in UI
- Test error case and confirm error message visible

---

### REQ-REMOTE-008: Recommended Bolus Expiry

**Statement**: Caregiver apps MUST expire recommended bolus values after the device status ages beyond a configurable threshold (default: 7 minutes).

**Rationale**: Stale recommendations based on outdated glucose data could lead to inappropriate dosing.

**Scenarios**:
- Remote Bolus from Recommendation
- Stale Data Handling

**Verification**:
- View recommended bolus
- Wait for expiry threshold
- Verify recommendation no longer displayed

---

### REQ-REMOTE-009: Command Creation Timestamp

**Statement**: Remote commands MUST include a creation timestamp for ordering and replay protection.

**Rationale**: Commands may arrive out of order; timestamp enables proper sequencing and detection of stale commands.

**Scenarios**:
- Command Ordering
- Replay Prevention

**Verification**:
- Create multiple commands in sequence
- Verify createdDate field present
- Confirm commands processed in timestamp order

---

### REQ-REMOTE-010: Credential Validation Before Storage

**Statement**: Caregiver apps SHOULD validate credentials against the Nightscout server before storing looper profiles.

**Rationale**: Invalid credentials would prevent all remote operations; early validation improves user experience and security.

**Scenarios**:
- Looper Setup
- QR Code Linking

**Verification**:
- Enter invalid credentials
- Verify validation fails before profile saved
- Enter valid credentials and confirm success

---

### REQ-REMOTE-011: Post-Bolus Recommendation Rejection

**Statement**: Caregiver apps SHOULD reject recommended bolus values if a bolus has been delivered since the device status timestamp.

**Rationale**: A bolus delivered after the recommendation invalidates it; using stale recommendations could cause stacking.

**Scenarios**:
- Concurrent Bolus Handling
- Recommendation Refresh

**Verification**:
- View recommended bolus
- Deliver bolus from another source
- Verify recommendation invalidated on refresh

---

## Caregiver Alarm Requirements

### REQ-ALARM-001: Configurable Glucose Thresholds

**Statement**: Caregiver alarm apps MUST allow configuration of glucose thresholds for low and high alarms.

**Rationale**: Different individuals have different target ranges; one-size-fits-all thresholds lead to alarm fatigue or missed alerts.

**Scenarios**:
- Low Glucose Alerting
- High Glucose Alerting
- Individual Threshold Customization

**Verification**:
- Configure custom low threshold (e.g., 65 mg/dL)
- Verify alarm fires at configured threshold
- Configure custom high threshold (e.g., 200 mg/dL)
- Verify alarm fires at configured threshold

---

### REQ-ALARM-002: Configurable Snooze Duration

**Statement**: Caregiver alarm apps MUST allow configuration of snooze duration per alarm type.

**Rationale**: Some alarms (e.g., low BG) require shorter snooze intervals than others (e.g., sensor change reminder).

**Scenarios**:
- Alarm Snooze
- Snooze Duration Management

**Verification**:
- Configure different snooze durations for different alarm types
- Snooze alarm and verify it re-fires after configured duration

---

### REQ-ALARM-003: Day/Night Schedule Support

**Statement**: Caregiver alarm apps SHOULD support different alarm behavior for day vs night hours.

**Rationale**: Nighttime alarms may need different thresholds (lower sensitivity for minor highs) or different sound/vibration patterns to avoid disrupting sleep for non-urgent issues.

**Scenarios**:
- Night Mode Alarms
- Time-Based Alarm Configuration

**Verification**:
- Configure day/night schedule times
- Verify alarm behavior changes between periods
- Test sound/activation options per time period

---

### REQ-ALARM-004: Predictive Low Glucose Alarms

**Statement**: Caregiver alarm apps SHOULD support predictive alarms that fire before glucose reaches threshold based on prediction data.

**Rationale**: Reacting to lows only when they occur may not provide enough time for intervention; predictive alarms enable proactive treatment.

**Scenarios**:
- Predictive Low Alerting
- Early Warning System

**Verification**:
- Enable predictive alarm with N-minute look-ahead
- Verify alarm fires when prediction shows low within window
- Confirm alarm does not fire for brief predicted dips

---

### REQ-ALARM-005: Persistent Threshold Requirement

**Statement**: Caregiver alarm apps SHOULD support requiring glucose to persist outside threshold for a configurable duration before alarming.

**Rationale**: Brief excursions (compression lows, signal noise) should not trigger alarms; persistence filtering reduces false positives.

**Scenarios**:
- Persistent High Detection
- Noise Filtering

**Verification**:
- Configure persistent duration (e.g., 15 minutes)
- Verify alarm does not fire for brief threshold crossing
- Verify alarm fires when threshold crossed for configured duration

---

### REQ-ALARM-006: Rate-of-Change Alarms

**Statement**: Caregiver alarm apps SHOULD support rate-of-change alarms for fast drops and fast rises.

**Rationale**: Rapid glucose changes may indicate emerging hypo/hyperglycemia before thresholds are crossed.

**Scenarios**:
- Fast Drop Detection
- Fast Rise Detection

**Verification**:
- Configure drop rate threshold (e.g., 3 mg/dL/min)
- Verify alarm fires when glucose drops rapidly
- Configure rise rate threshold
- Verify alarm fires when glucose rises rapidly

---

### REQ-ALARM-007: Missed Reading Detection

**Statement**: Caregiver alarm apps MUST alert when glucose readings have not been received for a configurable period.

**Rationale**: Missing data may indicate CGM failure, connectivity issues, or phone problems—all requiring attention.

**Scenarios**:
- Data Gap Alerting
- CGM Connectivity Monitoring

**Verification**:
- Configure missed reading threshold (e.g., 15 minutes)
- Simulate data gap
- Verify alarm fires after configured threshold

---

### REQ-ALARM-008: Loop Status Alerting

**Statement**: Caregiver alarm apps MUST alert when the AID loop has not run for a configurable period.

**Rationale**: A non-looping controller provides no automatic basal adjustment—equivalent to open-loop pump therapy with significant safety implications.

**Scenarios**:
- Loop Failure Detection
- AID Status Monitoring

**Verification**:
- Configure not-looping threshold (e.g., 30 minutes)
- Simulate loop stoppage
- Verify alarm fires after configured threshold

---

### REQ-ALARM-009: Alarm Priority Ordering

**Statement**: When multiple alarm conditions are met simultaneously, caregiver apps MUST present the highest-priority alarm first.

**Rationale**: Low glucose is more urgent than high glucose; critical alarms should not be obscured by less important ones.

**Scenarios**:
- Multiple Concurrent Alarms
- Priority-Based Alerting

**Verification**:
- Trigger low and high alarms simultaneously
- Verify low alarm displayed first
- Snooze low alarm, verify high alarm now displayed

---

### REQ-ALARM-010: Global Snooze/Mute Capability

**Statement**: Caregiver alarm apps SHOULD support a global snooze or mute function for all alarms.

**Rationale**: During meetings, movies, or known high-activity periods, caregivers may need to temporarily suppress all alerts.

**Scenarios**:
- Meeting Mode
- Temporary Silence All

**Verification**:
- Enable global snooze for N minutes
- Verify all alarms suppressed during period
- Verify alarms resume after period ends

---

## Graceful Degradation Requirements

> **See Also**: [Progressive Enhancement Framework](../docs/10-domain/progressive-enhancement-framework.md) for layer definitions.

### REQ-DEGRADE-001: Automation Disable on CGM Loss

**Statement**: AID controllers MUST automatically disable closed-loop automation when CGM data becomes stale or unreliable, falling back to scheduled basal delivery.

**Rationale**: Automation decisions require current glucose evidence. Without reliable CGM, the system should degrade to a known-safe state (scheduled basal) rather than continue making decisions on stale data.

**Scenarios**:
- CGM Signal Loss
- Sensor Warmup Period
- Compression Low Detection

**Verification**:
- Simulate CGM data gap exceeding staleness threshold
- Verify automation suspends and basal schedule resumes
- Verify clear notification to user about fallback state

---

### REQ-DEGRADE-002: Pump Communication Timeout Handling

**Statement**: AID controllers MUST enter a safe fallback state when pump communication fails, with clear indication to the user about current therapy status.

**Rationale**: Pump command failures create uncertainty about actual delivery. The system should inform the user and await confirmation rather than silently failing or retrying indefinitely.

**Scenarios**:
- Pump Out of Range
- Bluetooth Disconnection
- Pod/Pump Occlusion

**Verification**:
- Simulate pump communication timeout
- Verify system enters fallback state
- Verify user notification includes actionable guidance

---

### REQ-DEGRADE-003: Remote Control Fallback

**Statement**: When remote control channels are unavailable, caregiver apps SHOULD continue to provide remote visibility (following) and SHOULD offer out-of-band communication guidance.

**Rationale**: Network failures should not leave caregivers without any visibility. Read-only monitoring should remain available longer than write commands.

**Scenarios**:
- Nightscout Connectivity Loss
- Push Notification Failure
- API Token Expiration

**Verification**:
- Simulate command channel failure
- Verify following/monitoring continues
- Verify UI guidance for alternative communication

---

### REQ-DEGRADE-004: Layer Transition Logging

**Statement**: AID systems MUST log layer transitions (e.g., closed-loop to open-loop, automation to manual) with reason codes and timestamps.

**Rationale**: Understanding why the system changed modes is critical for retrospective analysis, debugging, and user trust.

**Scenarios**:
- Automation Pause
- Safety Limit Breach
- Component Failure

**Verification**:
- Trigger layer transition (e.g., pause automation)
- Verify log entry includes reason code
- Verify log entry includes precise timestamp

---

### REQ-DEGRADE-005: Safe State Documentation

**Statement**: Each AID system SHOULD document its safe states and the conditions that trigger transitions to those states.

**Rationale**: Users, caregivers, and developers need to understand what happens when components fail. This enables appropriate planning and reduces panic during degraded operation.

**Scenarios**:
- System Documentation
- User Onboarding
- Incident Response

**Verification**:
- Review system documentation for safe state definitions
- Verify safe states are discoverable in UI/settings
- Verify safe state behavior matches documentation

---

### REQ-DEGRADE-006: Delegate Agent Fallback

**Statement**: Delegate agents (L9) MUST fall back to human confirmation when confidence is low, context signals are unavailable, or out-of-band data is stale.

**Rationale**: Agents operating with incomplete information should not make autonomous decisions. Graceful degradation means reverting to "propose only" mode.

**Scenarios**:
- Context Signal Loss
- Low Confidence Decision
- Stale Wearable Data

**Verification**:
- Simulate loss of out-of-band signal
- Verify agent reverts to propose-only mode
- Verify agent requests human confirmation

---

## Batch Operation Requirements

### REQ-BATCH-001: Response Order Must Match Request Order

**Statement**: When processing batch uploads, the server MUST return responses in the same order as the input array.

**Rationale**: Loop caches syncIdentifier→objectId mappings based on response position. Mismatched order causes wrong ID assignments.

**Scenarios**:
- Batch Treatment Upload
- Batch Entry Upload

**Verification**:
- Submit batch of 5 treatments with distinct syncIdentifiers
- Verify response[i]._id corresponds to request[i].syncIdentifier
- Verify no position swaps occur

**Gap Reference**: GAP-BATCH-002

---

### REQ-BATCH-002: Deduplicated Items Return Existing ID

**Statement**: When a batch item is deduplicated, the server MUST return the existing document's `_id` at that position, not omit it.

**Rationale**: Clients expect N responses for N requests. Missing positions corrupt sync state.

**Scenarios**:
- Batch with Duplicates
- Network Retry Handling

**Verification**:
- Submit batch with one duplicate item
- Verify response array has same length as request
- Verify duplicate position returns existing _id

**Gap Reference**: GAP-BATCH-003

---

### REQ-BATCH-003: Partial Failure Response Format

**Statement**: When some items in a batch fail validation, the server SHOULD return a response array with success/failure indicators per item, preserving order.

**Rationale**: Clients need to know which items succeeded and which failed to update local state.

**Scenarios**:
- Mixed Validity Batch

**Verification**:
- Submit batch with valid and invalid items
- Verify response indicates status per item
- Verify response order matches request

---

## Timezone Requirements

### REQ-TZ-001: DST Transition Notification

**Statement**: AID systems with pumps that cannot handle DST SHOULD notify users before DST transitions.

**Rationale**: Most pump drivers cannot automatically adjust for DST. User intervention is required.

**Scenarios**:
- DST Transition Handling

**Verification**:
- Configure pump with `canHandleDST() = false`
- Approach DST boundary (±24 hours)
- Verify user notification generated

**Gap Reference**: GAP-TZ-001

---

### REQ-TZ-002: Preserve Client utcOffset

**Statement**: The server SHOULD preserve client-provided `utcOffset` values when they are valid, rather than recalculating from dateString.

**Rationale**: Client may have authoritative timezone information; server recalculation may lose precision.

**Scenarios**:
- Cross-Timezone Sync

**Verification**:
- Upload treatment with explicit utcOffset
- Download and verify utcOffset preserved
- Compare with dateString-derived offset

**Gap Reference**: GAP-TZ-003

---

## Error Handling Requirements

### REQ-ERR-001: Empty Array Handling

**Statement**: Batch endpoints SHOULD return an empty success response for empty arrays, NOT create phantom records.

**Rationale**: Creating records from empty input is surprising behavior that masks bugs.

**Scenarios**:
- Empty Batch Upload

**Verification**:
- Submit empty array `[]` to treatments endpoint
- Verify HTTP 200 with empty array response (or 400 error)
- Verify no phantom records created

**Gap Reference**: GAP-ERR-001

---

### REQ-ERR-002: CRC Validation Enforcement

**Statement**: Pump drivers SHOULD reject or retry data with invalid CRC, not silently use corrupted data.

**Rationale**: CRC failures indicate data corruption that could affect dosing calculations.

**Scenarios**:
- Pump History Corruption

**Verification**:
- Simulate CRC mismatch in pump history
- Verify retry or rejection behavior
- Verify corrupted data not used for IOB

**Gap Reference**: GAP-ERR-002

---

### REQ-ERR-003: Unknown Entry Type Logging

**Statement**: Pump history decoders SHOULD log unknown entry types with full data for community analysis.

**Rationale**: Unknown entries may contain critical dosing information that is being silently discarded.

**Scenarios**:
- New Firmware Entry Types

**Verification**:
- Inject unknown entry type in history
- Verify entry logged with full byte data
- Verify user can report unknown entries

**Gap Reference**: GAP-ERR-003

---

## Specification Requirements

### REQ-SPEC-001: Document All Valid eventTypes

**Statement**: The OpenAPI specification MUST enumerate all valid eventType values including remote command types.

**Rationale**: Clients cannot implement correct behavior without knowing valid eventTypes.

**Scenarios**:
- Remote Command Processing
- Treatment Type Validation

**Verification**:
- Compare spec enum to all eventTypes used in Nightscout server code
- Verify all Loop/AAPS/Trio eventTypes are represented
- Verify remote command types are documented

**Gap Reference**: GAP-SPEC-001

---

### REQ-SPEC-002: Document Controller-Specific Fields

**Statement**: The treatments schema SHOULD document all fields used by major AID controllers with x-aid-controllers annotations.

**Rationale**: Enables round-trip data preservation and cross-system compatibility.

**Scenarios**:
- AAPS Treatment Sync
- Loop Treatment Sync
- Cross-System Data Analysis

**Verification**:
- Compare AAPS RemoteTreatment model fields to spec
- Compare Loop treatment upload fields to spec
- Verify no data loss on upload/download cycle

**Gap Reference**: GAP-SPEC-002

---

### REQ-SPEC-003: Document Deduplication Algorithm

**Statement**: The API specification MUST document the deduplication key fields for each collection.

**Rationale**: Clients need to know which fields to include to prevent duplicates.

**Scenarios**:
- Batch Treatment Upload
- Network Retry Handling

**Verification**:
- Verify spec documents `created_at` + `eventType` key for treatments
- Verify spec documents `date` + `device` + `eventType` key for v3
- Verify behavior when dedup key fields are missing

**Gap Reference**: GAP-SPEC-007

---

### REQ-SPEC-004: Define isValid Semantics

**Statement**: The API specification MUST define the semantics of the `isValid` field including default value and deletion behavior.

**Rationale**: Consistent soft-delete handling across clients.

**Scenarios**:
- Treatment Deletion
- Sync History Query

**Verification**:
- Document when isValid should be set to false
- Document default value when field is missing
- Document query behavior for isValid filter

**Gap Reference**: GAP-SPEC-006

---

## Algorithm Conformance Requirements

### REQ-ALG-001: Cross-Project Test Vector Format

**Statement**: The ecosystem MUST define a unified JSON schema for algorithm test vectors that can be executed by any AID implementation.

**Rationale**: Enables automated detection of behavioral differences across oref0, AAPS, Loop, and Trio algorithm implementations.

**Scenarios**:
- Algorithm Conformance Testing
- Cross-Project Regression Detection
- New Implementation Validation

**Verification**:
- Schema validates all extracted test vectors
- At least 50 vectors covering all categories
- Runners exist for oref0, AAPS, and Loop

**Gap Reference**: GAP-ALG-001

---

### REQ-ALG-002: Semantic Equivalence Assertions

**Statement**: The conformance suite MUST support semantic assertions (e.g., "rate increased", "no SMB") rather than only exact value matching.

**Rationale**: Different algorithm architectures (Loop combined curve vs oref 4-curve) produce different numerical values for equivalent clinical decisions.

**Scenarios**:
- Loop vs oref Comparison
- Algorithm Migration Validation

**Verification**:
- Assertion types include: rate_increased, rate_decreased, no_smb, eventual_in_range
- Baseline field allows relative assertions
- Tests pass when clinical behavior matches, not just values

**Gap Reference**: GAP-ALG-003

---

### REQ-ALG-003: Safety Limit Validation

**Statement**: The conformance suite MUST include test vectors that verify safety limits (max IOB, max basal) are enforced.

**Rationale**: Safety-critical limits must be validated across all implementations to prevent overdosing.

**Scenarios**:
- Max IOB Enforcement
- Max Basal Rate Enforcement
- Low Glucose Suspend

**Verification**:
- Test vectors exist for each safety category
- All implementations pass safety limit tests
- Failures are treated as critical

**Gap Reference**: GAP-ALG-001

---

### REQ-ALG-004: Baseline Regression Detection

**Statement**: The conformance suite SHOULD detect when an implementation's behavior drifts from a known baseline.

**Rationale**: Algorithm updates should be intentional; accidental behavioral changes could affect patient safety.

**Scenarios**:
- oref0 Upstream Update
- AAPS Kotlin Migration
- Version Upgrade Validation

**Verification**:
- Baseline results stored per implementation
- CI detects changes from baseline
- Drift report generated with affected vectors

**Gap Reference**: GAP-ALG-002

---

## API Layer Requirements

### REQ-API-001: Document Deduplication Keys Per Collection

**Statement**: The API specification MUST document the deduplication key fields for each collection.

**Rationale**: AID controllers must know which fields trigger dedup to avoid duplicate treatments and ensure proper sync behavior.

**Scenarios**:
- Treatment batch upload from Loop
- Retry after network failure
- AAPS sync with existing data

**Verification**:
- Spec documents `identifier` as primary key
- Spec documents fallback keys per collection
- Spec documents `API3_DEDUP_FALLBACK_ENABLED` behavior

**Gap Reference**: GAP-API-006

---

### REQ-API-002: Provide Machine-Readable API Specification

**Statement**: The API SHOULD provide an OpenAPI 3.0 specification for automated client generation.

**Rationale**: Enables SDK generation, request validation, and reduces integration errors.

**Scenarios**:
- New client development
- API version migration
- Automated testing

**Verification**:
- OpenAPI spec exists and validates
- Spec covers all v3 endpoints
- Spec includes request/response schemas

**Gap Reference**: GAP-API-006

---

### REQ-API-003: Document Timestamp Field Per Collection

**Statement**: The API specification MUST document the canonical timestamp field name and format for each collection.

**Rationale**: Clients need consistent timestamp handling for cross-collection queries and data correlation.

**Scenarios**:
- Time-range queries across collections
- Data export/import
- Historical analysis

**Verification**:
- Spec documents timestamp field per collection
- Spec documents format (epoch vs ISO-8601)
- Examples show correct field usage

**Gap Reference**: GAP-API-008

---

## Plugin System Requirements

### REQ-PLUGIN-001: Document DeviceStatus Schema Per Controller

**Statement**: The API specification MUST document the expected devicestatus fields for each AID controller (Loop, OpenAPS, AAPS, Trio).

**Rationale**: Controllers upload different field structures; plugins must know what to expect.

**Scenarios**:
- Loop devicestatus upload
- AAPS devicestatus upload
- Plugin status display

**Verification**:
- Spec documents Loop `status.loop` structure
- Spec documents OpenAPS `status.openaps` structure
- Spec documents required vs optional fields

**Gap Reference**: GAP-PLUGIN-001, GAP-PLUGIN-003

---

### REQ-PLUGIN-002: Normalize Prediction Format

**Statement**: The visualization layer SHOULD normalize prediction data to a common format regardless of source controller.

**Rationale**: Enables consistent prediction display across Loop, OpenAPS, and AAPS.

**Scenarios**:
- Loop single-curve prediction display
- OpenAPS multi-curve prediction display
- Cross-controller comparison

**Verification**:
- Prediction visualization handles both formats
- Documentation describes normalization approach
- Unit tests cover both input formats

**Gap Reference**: GAP-PLUGIN-002

---

### REQ-PLUGIN-003: Document IOB/COB Calculation Models

**Statement**: The specification SHOULD document the IOB and COB calculation algorithms used by Nightscout plugins.

**Rationale**: Enables cross-project validation and ensures consistent insulin/carb tracking.

**Scenarios**:
- IOB calculation verification
- COB absorption validation
- Algorithm conformance testing

**Verification**:
- IOB exponential decay model documented
- COB absorption model documented
- Formulas match implementation

**Gap Reference**: GAP-ALG-001

---

## Sync/Upload Requirements

### REQ-SYNC-001: Document WebSocket API

**Statement**: The specification MUST document all Socket.IO events, payloads, and authentication requirements.

**Rationale**: Enables third-party clients to implement real-time sync correctly.

**Scenarios**:
- Client connecting to receive dataUpdate
- Custom dashboard implementation
- Mobile app Socket.IO integration

**Verification**:
- All events documented with payload schemas
- Authentication flow documented
- Error handling documented

**Gap Reference**: GAP-API-006

---

### REQ-SYNC-002: Consistent Sync Identity Across API Versions

**Statement**: All API versions MUST generate consistent `identifier` fields using the same algorithm.

**Rationale**: Prevents duplicates when clients switch between v1 and v3 APIs.

**Scenarios**:
- V1 upload followed by v3 update
- Migration from v1 to v3 client
- Mixed-version client ecosystem

**Verification**:
- V1 uploads include identifier field
- Same document matches across API versions
- Migration path documented

**Gap Reference**: GAP-SYNC-009

---

### REQ-SYNC-003: Sync Status Response

**Statement**: Upload endpoints SHOULD return sync metadata including insert/update counts and identifiers.

**Rationale**: Enables clients to verify sync success and handle retries appropriately.

**Scenarios**:
- Client retry after network failure
- Bulk upload status tracking
- Conflict detection

**Verification**:
- Response includes inserted/updated counts
- Response includes document identifiers
- Conflicts are reported

**Gap Reference**: GAP-SYNC-010

---

## Authentication Requirements

### REQ-AUTH-001: Document Permission Strings

**Statement**: The specification MUST document all permission strings used across API endpoints.

**Rationale**: Enables client developers to request appropriate permissions for their use case.

**Scenarios**:
- Client requesting minimal permissions
- Custom role creation
- Permission troubleshooting

**Verification**:
- All endpoints list required permission
- Permission format documented
- Wildcard behavior documented

**Gap Reference**: GAP-API-006

---

### REQ-AUTH-002: Token Revocation Capability

**Statement**: The authorization system SHOULD provide a mechanism to revoke access tokens without deleting subjects.

**Rationale**: Enables security response to compromised tokens while preserving audit history.

**Scenarios**:
- Token compromise response
- Device decommissioning
- Permission change enforcement

**Verification**:
- Revocation endpoint exists
- Revoked tokens rejected
- Revocation logged

**Gap Reference**: GAP-AUTH-002

---

### REQ-AUTH-003: Document Role Requirements Per Endpoint

**Statement**: The OpenAPI specification SHOULD include required permissions for each endpoint.

**Rationale**: Enables automated permission checking and client-side validation.

**Scenarios**:
- API client development
- Permission audit
- Automated testing

**Verification**:
- `x-required-permission` extension on endpoints
- Role-to-permission mapping documented
- Default roles documented

**Gap Reference**: GAP-AUTH-001

---

## Frontend/UI Requirements

### REQ-UI-001: Document Frontend Architecture

**Statement**: The specification SHOULD include a frontend developer guide covering bundle structure, plugin UI development, and chart customization.

**Rationale**: Enables contributors to extend Nightscout frontend without extensive codebase archaeology.

**Scenarios**:
- New plugin development
- Chart customization
- Translation contribution

**Verification**:
- Developer guide exists
- Build process documented
- Plugin UI API documented

**Gap Reference**: GAP-UI-001

---

### REQ-UI-002: Chart Accessibility

**Statement**: The glucose chart SHOULD provide accessible alternatives for visually impaired users.

**Rationale**: Ensures Nightscout is usable by all users regardless of visual ability.

**Scenarios**:
- Screen reader navigation
- Keyboard-only access
- Data table view

**Verification**:
- ARIA labels on chart elements
- Data table alternative available
- Keyboard navigation functional

**Gap Reference**: GAP-UI-002

---

### REQ-UI-003: Offline Data Access

**Statement**: The application SHOULD cache recent data for offline viewing.

**Rationale**: Enables glucose monitoring during connectivity interruptions.

**Scenarios**:
- Network disconnection
- Poor mobile signal
- Airplane mode with cached data

**Verification**:
- Recent SGVs cached locally
- Offline indicator displayed
- Data refreshes on reconnection

**Gap Reference**: GAP-UI-003

---

## Interoperability Requirements

### REQ-INTEROP-001: Standard Timestamp Format

**Statement**: All applications MUST use ISO 8601 format for string timestamps and Unix milliseconds for numeric timestamps.

**Rationale**: Inconsistent timestamp formats cause parsing failures and sync issues across the ecosystem.

**Scenarios**:
- Cross-controller data sync
- Third-party integration
- Data export/import

**Verification**:
- String dates match ISO 8601 pattern
- Numeric dates are Unix milliseconds
- Timezone handling documented

**Gap Reference**: GAP-SYNC-009

---

### REQ-INTEROP-002: Standard eventType Values

**Statement**: Applications SHOULD use standard eventType values as defined in the interoperability specification.

**Rationale**: Non-standard eventTypes cause display issues and break treatment categorization.

**Scenarios**:
- Treatment synchronization
- Report generation
- Plugin visualization

**Verification**:
- eventType matches specification catalog
- Unknown eventTypes handled gracefully
- Mapping documented for legacy values

**Gap Reference**: GAP-TREAT-001

---

### REQ-INTEROP-003: Device Identifier Inclusion

**Statement**: All uploads MUST include a device identifier field for source tracking.

**Rationale**: Enables deduplication, conflict detection, and audit trails.

**Scenarios**:
- Multi-device sync
- Duplicate detection
- Source attribution

**Verification**:
- `device` field present on entries
- `device` field present on devicestatus
- `enteredBy` field present on treatments

**Gap Reference**: GAP-SYNC-008

---

## nightscout-connect Requirements

### REQ-CONNECT-001: XState Machine Testability

**Statement**: Bridge applications SHOULD use state machine patterns for testable, deterministic data flow.

**Rationale**: XState enables injecting mock services, replaying event sequences, and verifying state transitions without network I/O.

**Scenarios**:
- Unit testing fetch cycles
- Simulating session expiry
- Verifying retry behavior

**Verification**:
- Machine definitions exportable
- Services injectable at runtime
- State snapshots capturable

**Implementation Reference**: `lib/machines/*.js`

---

### REQ-CONNECT-002: Source Transform Standardization

**Statement**: Data transform functions MUST produce Nightscout-compatible batches with entries, treatments, devicestatus, and profile arrays.

**Rationale**: Consistent output format enables unified output drivers and simplifies testing.

**Scenarios**:
- Multi-source aggregation
- Output driver switching
- Transform validation

**Verification**:
- Transform returns `{ entries: [], treatments: [], devicestatus: [], profile: [] }`
- Each item has required fields per collection spec
- Device field populated for source attribution

**Gap Reference**: GAP-CONNECT-002

---

### REQ-CONNECT-003: Exponential Backoff on Failure

**Statement**: Bridge applications MUST implement exponential backoff when fetch cycles fail.

**Rationale**: Prevents overwhelming vendor APIs during outages and respects rate limits.

**Scenarios**:
- Network timeout
- Authentication failure
- Rate limiting

**Verification**:
- Delay increases with consecutive failures
- Maximum retry count enforced
- Successful fetch resets backoff

**Implementation Reference**: `lib/backoff.js`, `lib/machines/fetch.js:61-67`

---

## Carb Absorption Requirements

### REQ-CARB-001: COB Model Type Annotation

**Statement**: Nightscout devicestatus uploads SHOULD include carb absorption model type annotation with COB values.

**Rationale**: COB values from different models (predictive vs reactive) are not comparable and should be labeled.

**Scenarios**:
- Multi-controller households
- User switching between systems
- Historical data analysis

**Verification**:
- devicestatus.cob includes model field
- UI displays model type when available
- Reports group by model type

**Gap Reference**: GAP-CARB-001

---

### REQ-CARB-002: Minimum Carb Impact Documentation

**Statement**: AID systems MUST document their minimum carb impact floor and its effect on COB decay.

**Rationale**: The min_5m_carbimpact parameter significantly affects how quickly COB decays and should be understood by users.

**Scenarios**:
- Configuring absorption settings
- Troubleshooting "stuck" COB
- Comparing system behavior

**Verification**:
- min_5m_carbimpact documented in user guide
- Effect on COB decay explained
- Comparison with other systems provided

**Gap Reference**: GAP-CARB-003

---

### REQ-CARB-003: Absorption Model Selection

**Statement**: AID systems supporting multiple absorption models SHOULD allow user selection with clear documentation of differences.

**Rationale**: Different absorption patterns (fast vs slow carbs) benefit from different models.

**Scenarios**:
- High-fat meals (slower absorption)
- Simple carbs (faster absorption)
- Mixed meals

**Verification**:
- Model selection available in settings
- Each model's characteristics documented
- Guidance on when to use each model

**Implementation Reference**: Loop CarbMath.swift supports Linear, Parabolic, PiecewiseLinear

---

## Vendor Interop Requirements

### REQ-BRIDGE-001: v3 API Support for Bridge Applications

**Statement**: Bridge applications uploading to Nightscout SHOULD support API v3 for UPSERT semantics.

**Rationale**: v3 API provides identifier-based deduplication, preventing duplicate records on re-runs.

**Scenarios**:
- Recovery from network failures
- Scheduled re-sync operations
- Multi-instance deployments

**Verification**:
- Bridge supports v3 endpoints
- Records include `identifier` field
- Re-runs don't create duplicates

**Gap Reference**: GAP-CONNECT-001

---

### REQ-BRIDGE-002: Client-Side Sync Identity Generation

**Statement**: Bridge applications SHOULD generate deterministic UUIDs for uploaded records.

**Rationale**: Enables idempotent uploads and cross-system deduplication matching Nightscout's sync identity spec.

**Scenarios**:
- Re-uploading historical data
- Multiple bridges for same source
- Disaster recovery

**Verification**:
- UUID v5 generated from source|date|type
- Consistent across re-runs
- Matches Nightscout identifier format

**Gap Reference**: GAP-CONNECT-003

---

### REQ-BRIDGE-003: Complete Collection Coverage

**Statement**: Bridge applications SHOULD upload all available data types (entries, treatments, devicestatus) from their source.

**Rationale**: Incomplete data limits Nightscout's value as a unified diabetes data platform.

**Scenarios**:
- Algorithm analysis requiring IOB/COB
- Report generation
- Caregiver monitoring

**Verification**:
- Transform outputs all 3 collection arrays
- Empty arrays for unavailable data (not omitted)
- Device field populated for attribution

**Gap Reference**: GAP-CONNECT-002
