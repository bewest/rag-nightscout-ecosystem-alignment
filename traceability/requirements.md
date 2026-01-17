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
