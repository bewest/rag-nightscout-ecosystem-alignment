# Treatments Requirements

Domain-specific requirements extracted from requirements.md.
See [requirements.md](requirements.md) for the index.

---

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

---

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

---

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

---

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

## Unit Handling Requirements

---

### REQ-UNIT-001: Duration Unit Documentation

**Statement**: API specifications MUST clearly document the unit for all duration fields.

**Rationale**: Prevents off-by-60x (seconds vs minutes) or off-by-60000x (milliseconds vs minutes) errors during data sync.

**Scenarios**:
- Treatment Sync Validation
- Temp Basal Upload
- eCarbs Duration Upload

**Verification**:
- OpenAPI spec includes unit in field description
- All duration fields have explicit unit annotations

**Source**: [Duration/utcOffset Analysis](../docs/10-domain/duration-utcoffset-unit-analysis.md), GAP-TREAT-002

---

### REQ-UNIT-002: Duration Validation

**Statement**: The server SHOULD validate duration fields are within reasonable ranges (0 < duration ≤ 1440 minutes).

**Rationale**: Catches unit confusion early—30000 minutes (20+ days) indicates milliseconds passed as minutes.

**Scenarios**:
- Treatment Upload Validation
- Duration Range Check

**Verification**:
- Reject `duration > 1440` with warning or error
- Reject `duration <= 0`
- Accept valid duration values (e.g., 30, 60, 120)

**Source**: [Duration/utcOffset Analysis](../docs/10-domain/duration-utcoffset-unit-analysis.md), GAP-TREAT-002

---

### REQ-UNIT-003: utcOffset Validation

**Statement**: The server SHOULD validate utcOffset is within ±840 minutes (±14 hours).

**Rationale**: Catches millisecond values being passed as minutes—a common unit confusion error.

**Scenarios**:
- Treatment Sync Validation
- Timezone Offset Check

**Verification**:
- Reject `|utcOffset| > 840` with error
- Log warning for unusual offsets (e.g., > 720)
- Accept valid offsets (e.g., -480, 330, 0)

**Source**: [Duration/utcOffset Analysis](../docs/10-domain/duration-utcoffset-unit-analysis.md), GAP-TZ-004

---

### REQ-UNIT-004: Preserve High-Precision Fields

**Statement**: The server SHOULD preserve AAPS-specific high-precision fields (e.g., `durationInMilliseconds`) for round-trip accuracy.

**Rationale**: Allows AAPS to recover original precision when syncing back from Nightscout.

**Scenarios**:
- AAPS Treatment Sync
- Round-Trip Precision

**Verification**:
- Upload treatment with `durationInMilliseconds` field
- Retrieve treatment and verify field preserved unchanged
- Sync back to AAPS and confirm precision maintained

**Source**: [Duration/utcOffset Analysis](../docs/10-domain/duration-utcoffset-unit-analysis.md)

---

## Caregiver Alarm Requirements

---
