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
