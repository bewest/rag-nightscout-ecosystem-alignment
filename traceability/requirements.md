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
