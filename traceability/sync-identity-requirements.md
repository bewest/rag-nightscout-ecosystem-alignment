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

## Sync Deduplication Requirements (REQ-SYNC-036 to REQ-SYNC-043)

---

### REQ-SYNC-036: syncIdentifier Field Preservation

**Statement**: The server MUST preserve the `syncIdentifier` field exactly as provided by the client through upload and download cycles.

**Rationale**: Loop uses syncIdentifier to correlate local DoseEntry records with Nightscout. Modification breaks sync state.

**Scenarios**:
- Loop uploads bolus with syncIdentifier
- Download same treatment, verify syncIdentifier unchanged
- Network retry with same syncIdentifier

**Verification**:
- Upload treatment with `syncIdentifier: "test-uuid-123"`
- GET treatment by _id
- Verify `syncIdentifier == "test-uuid-123"`

**Assertion**: `syncidentifier-preserved`

---

### REQ-SYNC-037: identifier Field Preservation

**Statement**: The server MUST preserve the `identifier` field exactly as provided by AAPS clients through upload and download cycles.

**Rationale**: AAPS uses identifier for deduplication and sync. Modification causes duplicate records.

**Scenarios**:
- AAPS uploads treatment with identifier
- Download same treatment, verify identifier unchanged
- V3 API upsert by identifier

**Verification**:
- Upload treatment with `identifier: "AAPS-bolus-12345"`
- GET treatment by identifier
- Verify `identifier == "AAPS-bolus-12345"`

**Assertion**: `identifier-preserved`

---

### REQ-SYNC-038: enteredBy Field Preservation

**Statement**: The server MUST preserve the `enteredBy` field exactly as provided by clients.

**Rationale**: Controllers use enteredBy for self-exclusion filtering. Modification breaks cross-controller coexistence.

**Scenarios**:
- Loop uploads with enteredBy="Loop"
- AAPS queries with enteredBy[$ne]=AAPS
- Trio filters by enteredBy

**Verification**:
- Upload treatment with `enteredBy: "Loop"`
- GET treatment
- Verify `enteredBy == "Loop"`

**Assertion**: `enteredby-preserved`

---

### REQ-SYNC-039: utcOffset Field Preservation

**Statement**: The server MUST preserve the `utcOffset` field when provided by clients for timezone handling.

**Rationale**: utcOffset enables correct local time display without dateString parsing. Required for timezone-aware reporting.

**Scenarios**:
- Upload treatment with explicit utcOffset
- Download in different timezone
- Historical analysis with original timezone

**Verification**:
- Upload treatment with `utcOffset: -300`
- GET treatment
- Verify `utcOffset == -300`

**Assertion**: `utcoffset-preserved`

---

### REQ-SYNC-040: Soft Delete Sets isValid=false

**Statement**: When soft-deleting a document, the server MUST set `isValid=false` rather than physically deleting.

**Rationale**: Soft deletes enable sync clients to detect deletions via history endpoint.

**Scenarios**:
- Delete treatment via v3 API
- Query history endpoint for deleted records
- Client sync detects deletion

**Verification**:
- Create treatment
- DELETE treatment via v3 API
- GET with deleted=true, verify isValid=false

**Assertion**: `softdelete-isvalid-false`

---

### REQ-SYNC-041: Pump Composite Key Immutability

**Statement**: The pump composite key fields (pumpId, pumpType, pumpSerial) MUST NOT be modifiable after document creation.

**Rationale**: Pump composite key is used for deduplication. Modification could create duplicates or orphans.

**Scenarios**:
- Upload treatment with pump composite key
- Attempt to modify pumpId
- Verify modification rejected or ignored

**Verification**:
- Create treatment with pumpId, pumpType, pumpSerial
- PATCH with different pumpId
- GET and verify original pumpId preserved

**Assertion**: `pump-composite-key-immutable`

---

### REQ-SYNC-042: Core Treatment Fields Immutability

**Statement**: Core identity fields (identifier, date, eventType, app, device) SHOULD NOT be modifiable after document creation.

**Rationale**: These fields define document identity. Modification breaks referential integrity.

**Scenarios**:
- Upload treatment with identifier
- Attempt to modify eventType
- Verify modification rejected

**Verification**:
- Create treatment with identifier and eventType
- PATCH with different eventType
- Verify original preserved or update rejected

**Assertion**: `core-treatment-fields-immutable`

---

### REQ-SYNC-043: Server Timestamps Immutability

**Statement**: Server-managed timestamps (srvCreated, _id) MUST NOT be client-modifiable.

**Rationale**: These are server-authoritative fields. Client modification would break data integrity.

**Scenarios**:
- Upload treatment with custom _id
- Attempt to modify srvCreated
- Verify server ignores client values

**Verification**:
- Create treatment with custom _id value
- Verify server-assigned _id used
- PATCH with different srvCreated, verify ignored

**Assertion**: `server-timestamps-immutable`

---

## Query Behavior Requirements (REQ-SYNC-044 to REQ-SYNC-048)

---

### REQ-SYNC-044: enteredBy Self-Exclusion Filter

**Statement**: The API MUST support `enteredBy[$ne]=<value>` filter to exclude a controller's own entries.

**Rationale**: Controllers must not re-process their own uploads. Self-exclusion prevents dosing loops.

**Scenarios**:
- Trio queries with enteredBy[$ne]=Trio
- Loop downloads excluding own entries
- Cross-controller data sharing

**Verification**:
- Create treatments from Trio, AAPS, xDrip+
- Query with `enteredBy[$ne]=Trio`
- Verify only AAPS and xDrip+ returned

**Assertion**: `enteredby-filter-excludes-self`

---

### REQ-SYNC-045: History Endpoint Modified-After Filter

**Statement**: The history endpoint MUST return documents modified after a given timestamp.

**Rationale**: Enables incremental sync by fetching only changed records.

**Scenarios**:
- Initial sync, store srvModified
- Wait, modify some records
- Fetch history with last srvModified

**Verification**:
- Create 3 treatments at T1, T2, T3
- Query history with timestamp between T1 and T3
- Verify only T2 and T3 treatments returned

**Assertion**: `history-returns-modified-after`

---

### REQ-SYNC-046: History Endpoint Includes Deleted

**Statement**: The history endpoint MUST include soft-deleted documents when requested.

**Rationale**: Sync clients need to detect server-side deletions to update local state.

**Scenarios**:
- Create treatment, sync client downloads
- Delete treatment on server
- Sync client queries history, detects deletion

**Verification**:
- Create treatment at T1
- Delete treatment
- Query history with deleted=true
- Verify deleted document returned with isValid=false

**Assertion**: `history-includes-soft-deleted`

---

### REQ-SYNC-047: Query by Client Identifier

**Statement**: The API MUST support querying treatments by client-generated identifier field.

**Rationale**: Enables direct lookup without timestamp-based search. Required for idempotent operations.

**Scenarios**:
- AAPS checks if treatment already uploaded
- Loop verifies sync success
- Retry with same identifier

**Verification**:
- Create treatment with identifier="client-uuid-123"
- Query `treatments?identifier=client-uuid-123`
- Verify single matching document returned

**Assertion**: `query-by-identifier`

---

### REQ-SYNC-048: Cross-Controller Coexistence

**Statement**: The server MUST support multiple AID controllers writing treatments simultaneously without data loss.

**Rationale**: Users may run multiple controllers. Data from all sources must be preserved.

**Scenarios**:
- Loop and AAPS both active
- Each uploads treatments
- Query returns all treatments

**Verification**:
- Upload treatment from Loop, AAPS, Trio
- Query all treatments
- Verify 3 distinct treatments exist

**Assertion**: `cross-controller-coexistence`

---

## Server Timestamp Requirements (REQ-SYNC-049 to REQ-SYNC-050)

---

### REQ-SYNC-049: srvModified Updated on Change

**Statement**: The server MUST update the `srvModified` timestamp whenever a document is modified.

**Rationale**: srvModified enables incremental sync. Must reflect actual modification time.

**Scenarios**:
- Create treatment, note srvModified
- Update treatment
- Verify srvModified increased

**Verification**:
- Create treatment, capture srvModified as T1
- PATCH treatment with new notes
- GET treatment, verify srvModified > T1

**Assertion**: `srvmodified-updated-on-change`

---

### REQ-SYNC-050: srvCreated Set on Creation

**Statement**: The server MUST set `srvCreated` timestamp when a document is first created.

**Rationale**: srvCreated indicates when server received the document. Required for audit and sync ordering.

**Scenarios**:
- Create treatment
- Verify srvCreated is set
- srvCreated never changes on update

**Verification**:
- Create treatment
- GET treatment, verify srvCreated > 0
- Update treatment, verify srvCreated unchanged

**Assertion**: `srvcreated-set-on-create`

---

## Profile Switch Requirements (REQ-SYNC-051 to REQ-SYNC-053)

### REQ-SYNC-051: Profile Change Visibility

**Statement**: Controllers SHOULD create `Profile Switch` treatment events when the active profile changes.

**Rationale**: Enables retrospective analysis of profile changes in Nightscout timeline.

**Scenarios**:
- User changes profile in AAPS
- Check treatments collection for Profile Switch event

**Verification**:
- Change profile
- GET treatments with eventType=Profile Switch
- Verify new event exists

**Gap**: GAP-SYNC-035

**Source**: `docs/10-domain/profile-switch-sync-comparison.md`

---

### REQ-SYNC-052: Percentage Handling

**Statement**: Controllers fetching Profile Switch treatments with `percentage != 100` SHOULD apply scaling or warn user.

**Rationale**: AAPS percentage adjustments affect actual insulin delivery; other controllers may not understand.

**Scenarios**:
- AAPS uploads Profile Switch with percentage=150
- Loop/Trio fetch from NS
- Verify warning or scaling applied

**Verification**:
- Create Profile Switch with percentage=150
- Fetch in non-AAPS controller
- Verify warning displayed or scaling applied

**Gap**: GAP-SYNC-037

**Source**: `docs/10-domain/profile-switch-sync-comparison.md`

---

### REQ-SYNC-053: Profile Deduplication

**Statement**: Controllers uploading profiles SHOULD use consistent identity to prevent duplicates.

**Rationale**: Avoid multiple profile documents for same logical profile.

**Scenarios**:
- Upload profile twice with same name
- Verify single document in collection

**Verification**:
- Upload profile "Default"
- Upload profile "Default" again
- GET profile collection, count documents with name "Default"

**Gap**: GAP-SYNC-036

**Source**: `docs/10-domain/profile-switch-sync-comparison.md`

---

## Override Requirements (REQ-OVERRIDE-001 to REQ-OVERRIDE-005)

---

### REQ-OVERRIDE-001: Superseded Status Change

**Statement**: When a new override is activated, the previous override's status MUST change to 'superseded'.

**Rationale**: Only one override can be active. Previous override must be marked as replaced.

**Scenarios**:
- Create override A (active)
- Create override B
- Verify A status = superseded

**Verification**:
- Create override with status=active
- Create new override
- GET original override, verify status=superseded

**Assertion**: `superseded-status-change`

---

### REQ-OVERRIDE-002: Superseded-By Reference

**Statement**: When an override is superseded, it MUST have a `superseded_by` field pointing to the new override.

**Rationale**: Enables audit trail and override history navigation.

**Scenarios**:
- Override A superseded by B
- A.superseded_by = B.id
- Query override chain

**Verification**:
- Create override A
- Create override B
- GET A, verify superseded_by = B.id

**Assertion**: `superseded-by-reference`

---

### REQ-OVERRIDE-003: Superseded-At Timestamp

**Statement**: When an override is superseded, it MUST have a `superseded_at` timestamp matching the new override's start time.

**Rationale**: Enables precise duration calculation for superseded override.

**Scenarios**:
- Override A superseded at T
- B started at T
- A.superseded_at = B.started_at

**Verification**:
- Create override A
- Create override B with started_at = T
- GET A, verify superseded_at = T

**Assertion**: `superseded-at-timestamp`

---

### REQ-OVERRIDE-004: Original Override Data Preserved

**Statement**: When an override is superseded, its original data (name, duration, target_range) MUST NOT be modified.

**Rationale**: Historical data must be preserved for analysis and audit.

**Scenarios**:
- Override A with name="Exercise"
- A superseded by B
- A.name still = "Exercise"

**Verification**:
- Create override A with name, duration, target_range
- Supersede with override B
- GET A, verify original fields unchanged

**Assertion**: `original-preserved`

---

### REQ-OVERRIDE-005: Query Active Returns Single

**Statement**: Query for active overrides MUST return at most one override.

**Rationale**: Only one override can be active at a time. Query must reflect this invariant.

**Scenarios**:
- Multiple overrides exist
- Query status=active
- Only newest active returned

**Verification**:
- Create overrides A, B (B supersedes A)
- Query `overrides?status=active`
- Verify exactly 1 result (B)

**Assertion**: `query-active-single`

---

## Override/Temp Target Sync Requirements

### REQ-OVRD-001: eventType Documentation

**Statement**: Systems MUST document which eventType(s) they use for target overrides.

**Rationale**: Loop `Override` vs AAPS `Temporary Target` causes interoperability confusion.

**Verification**: Documentation review for eventType usage.

### REQ-OVRD-002: Insulin Adjustment Sync

**Statement**: Systems that support insulin sensitivity adjustment SHOULD sync this to Nightscout.

**Rationale**: Loop's `insulinNeedsScaleFactor` is important for understanding override behavior.

**Verification**: Field presence in synced treatments.

### REQ-OVRD-003: Duration Unit Normalization

**Statement**: Systems MUST normalize duration to consistent units when syncing.

**Rationale**: Loop (seconds) vs AAPS (milliseconds) requires conversion for interoperability.

**Verification**: Duration value validation in synced treatments.

### REQ-OVRD-004: Cross-Type Override Query

**Statement**: The API MAY provide a unified query for all target-modifying treatments (Override and Temporary Target).

**Rationale**: Simplifies client code that needs to understand "what's affecting targets right now."

**Scenarios**:
- Query returns both Loop Override and AAPS Temporary Target
- Results normalized to common schema

**Verification**: Query `eventType=Temporary Override,Temporary Target` returns both types.

**Gap Reference**: GAP-OVRD-005

**Source**: [Nocturne Override Analysis](../docs/10-domain/nocturne-override-temptarget-analysis.md)

### REQ-OVRD-005: Duration Unit Documentation

**Statement**: Systems MUST document duration units (seconds vs minutes) for all override-related fields.

**Rationale**: Prevents off-by-60x conversion errors between LoopOverridePreset (seconds) and Treatment (minutes).

**Scenarios**:
- LoopOverridePreset.Duration documented as seconds
- Treatment.Duration documented as minutes
- Conversion explicitly noted

**Verification**: Documentation review for duration units.

**Gap Reference**: GAP-OVRD-007

**Source**: [Nocturne Override Analysis](../docs/10-domain/nocturne-override-temptarget-analysis.md)

---

## ProfileSwitch Sync Requirements

### REQ-SYNC-054: ProfileSwitch Percentage Application

**Statement**: Servers ingesting ProfileSwitch treatments with `percentage != 100` SHOULD apply scaling to returned profile values.

**Rationale**: AAPS percentage adjustments are meant to affect actual insulin delivery, not just display. Without application, the profile percentage field is meaningless for algorithm calculations.

**Scenarios**:
- AAPS uploads ProfileSwitch with percentage=150
- Server applies 1.5x scaling to basal, 0.667x to ISF/CR
- Algorithm uses scaled values

**Verification**:
- Create ProfileSwitch with `percentage=150`
- Query current basal via API
- Verify basal is 1.5x the base profile value

**Source**: [Nocturne ProfileSwitch Analysis](../docs/10-domain/nocturne-profileswitch-analysis.md)

**Gap Reference**: GAP-NOCTURNE-004

---

### REQ-SYNC-055: ProfileSwitch Timeshift Application

**Statement**: Servers ingesting ProfileSwitch treatments with `timeshift != 0` SHOULD rotate schedule lookup time accordingly.

**Rationale**: AAPS timeshift is meant to shift the basal/ISF/CR schedule for travel or circadian rhythm adjustments. Without application, the timeshift field is display-only.

**Scenarios**:
- AAPS uploads ProfileSwitch with timeshift=6 (hours)
- Server rotates schedule lookup by 6 hours
- 6am values returned when querying midnight

**Verification**:
- Create ProfileSwitch with `timeshift=6`
- Query profile value at midnight (local)
- Verify returned value matches 6am schedule entry

**Source**: [Nocturne ProfileSwitch Analysis](../docs/10-domain/nocturne-profileswitch-analysis.md)

---

### REQ-SYNC-056: ProfileJson Embedding Storage

**Statement**: Servers receiving ProfileSwitch treatments with `profileJson` SHOULD store the embedded profile data for historical retrieval.

**Rationale**: AAPS embeds complete profile data in ProfileSwitch events. This enables reconstruction of exact profile used at any historical time.

**Scenarios**:
- AAPS uploads ProfileSwitch with embedded profileJson
- Historical query retrieves ProfileSwitch
- Embedded profileJson available in response

**Verification**:
- Upload ProfileSwitch with `profileJson` containing complete profile
- Query treatments for Profile Switch eventType
- Verify `profileJson` field is present and complete

**Source**: [Nocturne ProfileSwitch Analysis](../docs/10-domain/nocturne-profileswitch-analysis.md)

**Gap Reference**: GAP-SYNC-036

### REQ-SYNC-057: Profile Effective Values API

**Statement**: Servers MAY provide an API endpoint returning effective profile values at a given time, with active ProfileSwitch percentage/timeshift applied.

**Rationale**: Allows cross-controller clients to receive computed values without implementing ProfileSwitch interpretation logic themselves.

**Verification**: Request effective profile with active 150% ProfileSwitch; verify basal×1.5, ISF÷1.5, CR÷1.5 in response.

**Gap**: GAP-NOCTURNE-005

### REQ-SYNC-058: ProfileSwitch Metadata in Profile Response

**Statement**: Servers MAY include active ProfileSwitch metadata (percentage, timeshift, CircadianPercentageProfile) in profile API responses.

**Rationale**: Even if raw values returned, clients can detect and apply ProfileSwitch adjustments themselves if metadata included.

**Verification**: Fetch profile with active ProfileSwitch; verify response includes percentage/timeshift fields.

**Gap**: GAP-NOCTURNE-005

---

## Profile Sync Requirements

### REQ-SYNC-059: Profile Deduplication Consistency

**Statement**: Servers SHOULD implement consistent profile deduplication using both `identifier` and `created_at` fallback fields.

**Rationale**: Ensures V1 and V3 API uploads are deduplicated consistently across implementations.

**Scenarios**:
- Upload profile without identifier
- Upload same profile again with same created_at
- Verify only one profile exists

**Verification**:
- Upload profile without identifier twice with same `created_at`
- Verify single profile exists

**Gap Reference**: GAP-SYNC-038

**Source**: [Profile Sync Comparison](../docs/10-domain/nocturne-cgm-remote-monitor-profile-sync.md)

---

### REQ-SYNC-060: Profile srvModified Support

**Statement**: Servers SHOULD track `srvModified` timestamp on Profile documents for sync polling.

**Rationale**: Enables efficient incremental sync by clients using `srvModified$gt` filter.

**Scenarios**:
- Update profile
- Query with srvModified$gt filter
- Only updated profiles returned

**Verification**:
- Update profile; verify `srvModified` changes
- Query with `srvModified$gt` filter

**Gap Reference**: GAP-SYNC-039

**Source**: [Profile Sync Comparison](../docs/10-domain/nocturne-cgm-remote-monitor-profile-sync.md)

---

### REQ-SYNC-061: Profile Soft Delete

**Statement**: Servers SHOULD implement soft delete for profiles (set `isValid: false`) rather than hard delete.

**Rationale**: Allows sync clients to detect deletions and remove local copies.

**Scenarios**:
- Delete profile
- Query with isValid=false
- Deleted profile returned with deletion marker

**Verification**:
- Delete profile
- Verify `isValid: false` and `srvModified` updated
- Verify still queryable

**Gap Reference**: GAP-SYNC-040

**Source**: [Profile Sync Comparison](../docs/10-domain/nocturne-cgm-remote-monitor-profile-sync.md)

---

## V4 API Requirements

### REQ-V4-001: StateSpan Portability

**Statement**: Future Nightscout API versions SHOULD include StateSpan-like time-range tracking for profiles and overrides.

**Rationale**: Enables profile change history and override tracking across implementations. Currently only available in Nocturne V4 API.

**Scenarios**:
- Query profile activation history over time range
- Determine which profile was active at a specific point
- Build profile timeline for retrospective analysis

**Verification**:
- API spec includes time-ranged state tracking endpoints
- Profile spans queryable by time range

**Gap Reference**: GAP-V4-001

**Source**: [Nocturne V4 ProfileSwitch Extensions](../docs/10-domain/nocturne-v4-profile-extensions.md)

---

### REQ-V4-002: Profile Activation Events

**Statement**: Servers SHOULD track profile activation events with timestamps.

**Rationale**: Enables retrospective analysis of which profile was active at any point. Currently V3 only stores profile documents, not activation history.

**Scenarios**:
- User activates profile "Exercise" at 10:00
- Query profile state at 10:30
- Verify "Exercise" returned as active profile

**Verification**:
- Query profile history returns activation timestamps
- Active profile determinable for any historical time

**Gap Reference**: GAP-V4-002

**Source**: [Nocturne V4 ProfileSwitch Extensions](../docs/10-domain/nocturne-v4-profile-extensions.md)

---

## Rust oref Integration Requirements

### REQ-OREF-001: Percentage Application for Predictions

**Statement**: Prediction calculations SHOULD apply active ProfileSwitch percentage to basal/ISF/CR values.

**Rationale**: Ensures predictions match actual insulin delivery when percentage adjustment is active.

**Scenarios**:
- User activates ProfileSwitch with percentage=150
- Query predictions for next 6 hours
- Verify predictions use scaled basal (150% of base)

**Verification**:
- Create ProfileSwitch with percentage=150
- Verify predictions use scaled basal
- Compare with ProfileService.GetBasalRate() output

**Gap Reference**: GAP-OREF-001

**Source**: [Nocturne Rust oref Profile Analysis](../docs/10-domain/nocturne-rust-oref-profile-analysis.md)

---

### REQ-OREF-002: Full Schedule Propagation

**Statement**: Algorithm implementations SHOULD receive full time-varying schedules, not just current values.

**Rationale**: Enables accurate multi-hour predictions that account for scheduled rate changes throughout the day.

**Scenarios**:
- Profile has 4 different basal rates across day
- Generate 24-hour prediction
- Verify prediction uses correct rate per time block

**Verification**:
- Submit profile with multiple basal rates
- Verify oref receives full schedule array
- Verify predictions vary correctly across rate boundaries

**Gap Reference**: GAP-OREF-002

**Source**: [Nocturne Rust oref Profile Analysis](../docs/10-domain/nocturne-rust-oref-profile-analysis.md)

---

### REQ-OREF-003: Rust/JS Oref Equivalence Testing

**Statement**: Rust oref and JS oref0 SHOULD produce equivalent outputs for identical inputs.

**Rationale**: Ensures Nocturne users get same algorithm behavior as AAPS/Trio.

**Scenarios**:
- Feed identical profile/glucose/treatment data to both implementations
- Compare IOB, COB, and prediction outputs
- Document any numerical differences

**Verification**:
- Create test harness with identical inputs
- Compare outputs within tolerance (e.g., 0.001)
- Flag any significant divergence

**Gap Reference**: N/A (testing requirement)

**Source**: [Nocturne Rust oref Profile Analysis](../docs/10-domain/nocturne-rust-oref-profile-analysis.md)

---

## StateSpan Requirements

---

### REQ-STATESPAN-001: Time Range Query

**Statement**: StateSpan API MUST support time-range queries with `from` and `to` parameters.

**Rationale**: Core use case for state history visualization and analysis.

**Scenarios**:
- Query profile history for past 24 hours
- Query active overrides during a specific period
- Filter pump mode changes by date range

**Verification**:
- `GET /api/v3/state-spans?from=...&to=...` returns spans overlapping range
- Spans fully outside range are excluded
- Partially overlapping spans are included

**Gap Reference**: GAP-STATESPAN-001

---

### REQ-STATESPAN-002: Category Filtering

**Statement**: StateSpan API MUST support filtering by category enum.

**Rationale**: Enables focused queries for specific state types.

**Scenarios**:
- Query only Profile spans
- Query only Override spans
- Query only PumpMode spans

**Verification**:
- `?category=Profile` returns only Profile spans
- Invalid category returns 400 Bad Request

**Gap Reference**: GAP-STATESPAN-001

---

### REQ-STATESPAN-003: Active Span Query

**Statement**: StateSpan API MUST support querying currently active spans.

**Rationale**: Common need to know current profile/override/pump mode.

**Scenarios**:
- Get currently active profile
- Check if any override is active
- Determine current pump mode

**Verification**:
- `?active=true` returns spans where `endMills` is null
- `?active=false` returns spans with `endMills` set

**Gap Reference**: GAP-STATESPAN-001

---

### REQ-STATESPAN-004: Treatment Auto-Translation

**Statement**: Implementation SHOULD auto-generate StateSpans from treatment writes for backward compatibility.

**Rationale**: Enables gradual migration without breaking existing treatment-based workflows.

**Scenarios**:
- Write Profile Switch treatment → Profile StateSpan created
- Write Temporary Override treatment → Override StateSpan created
- Write Temp Basal treatment → TempBasal StateSpan created

**Verification**:
- POST treatment with eventType "Profile Switch"
- GET state-spans returns corresponding Profile span

**Gap Reference**: GAP-STATESPAN-001

---

### REQ-STATESPAN-005: Source Tracking

**Statement**: StateSpan MUST include `source` field identifying data origin.

**Rationale**: Enables deduplication and source attribution in multi-uploader scenarios.

**Scenarios**:
- StateSpan from Loop has `source: "Loop"`
- StateSpan from AAPS has `source: "AAPS"`
- StateSpan from manual entry has `source: "manual"`

**Verification**:
- Created StateSpan includes source field
- Source field is filterable in queries

**Gap Reference**: GAP-STATESPAN-001

**Source**: [StateSpan Standardization Proposal](../docs/sdqctl-proposals/statespan-standardization-proposal.md)
