# Sync Identity Requirements

Domain-specific requirements extracted from requirements.md.
See [requirements.md](requirements.md) for the index.

---

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

---

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

---

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

---

---

## Sync Identity Requirements (REQ-030 to REQ-035)

---

### REQ-030: Sync Identity Preservation

**Statement**: The server MUST preserve client-provided sync identity fields (`identifier`, `syncIdentifier`) and return them unchanged in responses.

**Rationale**: Clients use these fields to correlate local records with server records. Modification breaks sync state.

**Scenarios**:
- Treatment upload with `identifier`
- Dose upload with `syncIdentifier`
- Round-trip verification

**Verification**:
- Upload document with explicit identifier
- Fetch document and verify identifier unchanged
- Test with Loop, AAPS, and Trio clients

**Source**: `mapping/cross-project/aid-controller-sync-patterns.md`

---

### REQ-031: Self-Entry Exclusion

**Statement**: When fetching records from Nightscout, AID controllers SHOULD exclude their own entries using `enteredBy` filter to avoid processing duplicates.

**Rationale**: Prevents controllers from re-processing their own uploaded treatments, which could cause dosing loops or duplicate COB/IOB calculations.

**Scenarios**:
- Trio fetches carbs with `enteredBy != "Trio"`
- Loop fetches treatments excluding own entries
- AAPS filters by `enteredBy`

**Verification**:
- Verify Trio uses `$ne` filter: `Trio/Sources/Services/Network/NightscoutAPI.swift:296-298`
- Verify Loop excludes own uploads
- Test cross-controller scenario where A's entries are visible to B

**Source**: `mapping/cross-project/aid-controller-sync-patterns.md:46`, `mapping/trio/carb-math.md:278`

---

### REQ-032: Incremental Sync Support

**Statement**: The API MUST support incremental sync using `srvModified` timestamp to fetch only records changed since last sync.

**Rationale**: Full-table fetches are inefficient. Clients need to sync only delta changes.

**Scenarios**:
- AAPS fetches treatments where `srvModified > lastLoadedSrvModified`
- nightscout-connect tracks sync bookmark
- Initial sync followed by incremental updates

**Verification**:
- Query `/api/v3/treatments?srvModified$gt=<timestamp>`
- Verify only modified records returned
- Test pagination with incremental sync

**Source**: `mapping/cross-project/aid-controller-sync-patterns.md:252`, `mapping/cgm-remote-monitor/api-versions.md:14`

**Gap Reference**: GAP-API-003 (v1 API lacks srvModified)

---

### REQ-033: Server Deduplication

**Statement**: The server MUST deduplicate uploads using a consistent algorithm: `identifier` field takes precedence, with fallback to `created_at + eventType`.

**Rationale**: Multiple clients may upload the same treatment. Server must prevent duplicates while allowing updates.

**Scenarios**:
- Loop uploads treatment, network retry sends again
- AAPS and Trio both upload same carb entry
- V1 upload followed by v3 update

**Verification**:
- Upload treatment with `identifier`
- Re-upload same treatment, verify no duplicate created
- Verify existing `_id` returned for duplicate

**Source**: `mapping/cross-project/aid-controller-sync-patterns.md:381-382`, `mapping/cgm-remote-monitor/deduplication.md`

**Gap Reference**: GAP-SYNC-009 (v1 lacks identifier field)

---

### REQ-034: Cross-Controller Coexistence

**Statement**: Multiple AID controllers SHOULD be able to write to the same Nightscout instance without data corruption or conflicts.

**Rationale**: Users may run Loop on phone and AAPS on tablet, or transition between systems. Data must not be lost.

**Scenarios**:
- Loop and AAPS both active
- Trio replaces Loop, historical data preserved
- Caregiver Loop + patient AAPS

**Verification**:
- Upload from Controller A, verify Controller B can read
- Both controllers write, verify no overwrites
- Verify `enteredBy` field distinguishes sources

**Source**: `mapping/cross-project/interoperability-matrix.md:100`, `docs/10-domain/authority-model.md:39`

**Gap Reference**: GAP-SYNC-008 (no conflict resolution)

---

### REQ-035: Conflict Detection

**Statement**: The server SHOULD detect and report conflicts when multiple clients update the same record concurrently.

**Rationale**: Last-write-wins without notification can silently lose data. Clients need to handle conflicts.

**Scenarios**:
- Loop and AAPS update same treatment
- Offline client syncs stale data
- Concurrent edits from multiple caregivers

**Verification**:
- Update treatment from two clients simultaneously
- Verify conflict detected (409 response or version mismatch)
- Verify client can resolve conflict

**Source**: `docs/10-domain/cgm-remote-monitor-sync-deep-dive.md:420`, `docs/10-domain/cgm-remote-monitor-design-review.md`

**Gap Reference**: GAP-SYNC-008, REQ-NS-028

---
