# Sync Identity Gaps

Domain-specific gaps extracted from gaps.md.
See [gaps.md](gaps.md) for the index.

---

### GAP-BATCH-001: Batch Deduplication Not Enforced at Database Level

**Scenario**: High-throughput batch uploads

**Description**: The `id` field used by Trio and other clients for deduplication is NOT enforced as unique by MongoDB. Nightscout relies on application-level deduplication queries (checking if id exists before insert), not database-level unique constraints. This means duplicate `id` values CAN be inserted if sent in a batch, because batch inserts don't perform per-document deduplication checks.

**Source**: `cgm-remote-monitor:tests/api.partial-failures.test.js:62-107`
```javascript
// QUIRK/BEHAVIOR: The 'id' field is used by clients (Trio, etc.) for deduplication
// but is NOT enforced as unique by MongoDB unless explicitly indexed.
// This means duplicate 'id' values CAN be inserted if sent in a batch,
// because the batch insert doesn't perform per-document deduplication checks.
```

**Impact**:
- Batch operations can create duplicate documents with same `id`
- Network retries during batch uploads may create duplicates
- Trio throttled pipelines may insert duplicates under high load
- Data integrity depends on client-side dedup, not server enforcement

**Possible Solutions**:
1. Add unique index on `id` field (breaking change for existing data)
2. Implement per-document deduplication in batch insert handler
3. Document behavior and recommend client-side deduplication
4. Use `identifier` field with v3 API for server-enforced uniqueness

**Status**: Under discussion

---

---

### GAP-BATCH-002: Response Order Critical for Loop syncIdentifier Mapping

**Scenario**: Loop batch treatment uploads

**Description**: Loop caches syncIdentifier→objectId mappings based on response array order. If the response order doesn't match the request order, Loop maps wrong IDs which breaks update and delete operations.

**Source**: `cgm-remote-monitor:tests/api.partial-failures.test.js:138-182`
```javascript
// SPEC: Loop caches syncIdentifier→objectId mapping based on response array order
// CRITICAL: If order doesn't match, Loop maps wrong IDs and breaks update/delete
```

**Impact**:
- Wrong ID mappings cause silent data corruption
- Updates may modify wrong documents
- Deletes may remove wrong documents
- Hard to debug because no immediate error

**Possible Solutions**:
1. Server guarantees response order matches request order (current behavior, needs testing)
2. Loop should match by syncIdentifier in response, not by position
3. Server includes syncIdentifier in response for verification
4. Add test coverage to prevent regression

**Status**: Under discussion

**Related**:
- GAP-TREAT-005 (Loop POST duplicates)
- REQ-045 (Sync identity round-trip)

---

---

### GAP-BATCH-003: Deduplicated Items Must Return All Positions

**Scenario**: Batch upload with some duplicates

**Description**: Loop expects N responses for N requests, even if some items are deduplicated. Missing positions in the response array break the syncIdentifier cache, causing subsequent operations to fail.

**Source**: `cgm-remote-monitor:tests/api.partial-failures.test.js:186-212`
```javascript
// SPEC: Loop expects N responses for N requests, even if some are deduplicated
// CRITICAL: Missing positions in response breaks syncIdentifier cache
```

**Impact**:
- If server returns fewer items than submitted, Loop cache is corrupted
- Subsequent updates/deletes fail silently or target wrong documents
- Deduplicated items must still appear in response with their existing `_id`

**Possible Solutions**:
1. Server always returns N items for N-item batch (current expected behavior)
2. Deduplicated items return existing document's `_id`
3. Document expected response format in API specification
4. Add conformance tests

**Status**: Under discussion

---

## Prediction Data Gaps

---

### GAP-DELEGATE-001: No Standardized Authorization Scoping

**Scenario**: Remote Control Delegation (L8)

**Description**: Current remote control implementations provide all-or-nothing authorization. A caregiver either has full remote control access or none. There is no mechanism to scope permissions to specific command types (e.g., "can send temp targets but not boluses").

**Affected Systems**: Loop, AAPS, Trio, LoopCaregiver, LoopFollow

**Source**: 
- Loop: Single OTP secret grants all command permissions
- AAPS: Phone whitelist is binary (all or nothing)
- Trio: Single shared secret for all commands

**Impact**:
- Cannot implement "observer" role (view-only)
- Cannot implement "coach" role (suggestions only)
- Cannot implement "nurse" role (limited commands)
- Inappropriate for clinical care team integration

**Possible Solutions**:
1. Implement permission bitmask in authorization
2. Create role-based access control (RBAC) layer
3. Use JWT claims for scoped permissions
4. Define standard permission vocabulary

**Status**: Under discussion

---

---

### GAP-DELEGATE-002: No Role-Based Permission Model

**Scenario**: Care Team Coordination (L8)

**Description**: No AID system implements role-based permissions for remote control. All authorized parties have equivalent access regardless of their relationship (parent, partner, clinician, coach).

**Affected Systems**: All

**Source**: 
- No role field in command authentication
- No permission differentiation by user identity
- No concept of permission hierarchy

**Impact**:
- Cannot distinguish parent vs babysitter permissions
- Cannot limit clinician access to view-only
- Cannot implement "least privilege" security principle
- Risk of unauthorized actions by over-privileged users

**Possible Solutions**:
1. Define standard role vocabulary (primary, caregiver, clinician, observer, agent)
2. Map roles to permission sets
3. Store role in Nightscout token or authorization
4. Implement in gateway layer (NRG)

**Status**: Under discussion

**Related**:
- [GAP-AUTH-002](#gap-auth-002-no-authority-hierarchy-in-nightscout)
- [Controller Registration Protocol Proposal](../docs/60-research/controller-registration-protocol-proposal.md)

---

---

### GAP-DELEGATE-003: No Structured Out-of-Band Signal API

**Scenario**: Agent Context Integration (L9)

**Description**: There is no standardized API for integrating out-of-band signals (exercise, menstrual cycle, sleep, stress) into AID decision-making. Each potential signal source would require custom integration.

**Affected Systems**: All

**Source**: 
- No exercise detection integration in any open-source AID
- No hormone cycle awareness
- No wearable data integration (HR, HRV, steps) beyond CGM
- Manual overrides are the only mechanism

**Impact**:
- Agents cannot propose contextually-aware recommendations
- Users must manually detect and respond to patterns
- No path to reduced burden through automation
- Cannot leverage growing wearable ecosystem

**Possible Solutions**:
1. Define standard "context event" format for Nightscout
2. Create observer APIs for external signal sources
3. Implement signal-to-recommendation mapping framework
4. Start with exercise detection pilot (highest impact)

**Status**: Under discussion

---

---

### GAP-DELEGATE-004: No Agent Authorization Framework

**Scenario**: Autonomous Agent Operation (L9)

**Description**: There is no framework for authorizing software agents to act on behalf of users. Current systems assume human operators for all commands.

**Affected Systems**: All

**Source**: 
- `enteredBy` field is unverified string
- No concept of "agent" vs "human" command source
- No scoping for agent autonomy bounds
- No revocation mechanism for agent permissions

**Impact**:
- Cannot safely deploy autonomous agents
- Cannot audit human vs machine decisions
- Cannot implement "human in the loop" for agent actions
- Cannot limit agent actions to safe bounds

**Possible Solutions**:
1. Define `actorType` field (human, agent, controller)
2. Implement agent registration and authorization
3. Create audit trail for agent actions
4. Define bounded autonomy specifications

**Status**: Under discussion

**Related**:
- [GAP-AUTH-001](#gap-auth-001-enteredby-field-is-unverified)
- [GAP-AUTH-002](#gap-auth-002-no-authority-hierarchy-in-nightscout)

---

---

### GAP-DELEGATE-005: No Propose-Authorize-Enact Pattern

**Scenario**: Safe Agent Interaction (L9)

**Description**: Current remote command patterns assume immediate execution. There is no standardized workflow for agents to propose actions, await human authorization, and then enact approved actions.

**Affected Systems**: All

**Source**: 
- Remote commands execute immediately upon receipt
- No "pending authorization" state for commands
- No mechanism for human approval of proposed actions
- No timeout/expiry for unapproved proposals

**Impact**:
- Agents cannot operate in "propose-only" mode
- No gradual trust-building path for automation
- Users must fully trust or fully block agents
- Cannot implement "confirm to enact" safety pattern

**Possible Solutions**:
1. Add `status` field to remote commands (proposed, authorized, enacted, expired)
2. Implement proposal notification to authorized humans
3. Create authorization workflow with timeout
4. Define escalation for unacknowledged proposals

**Status**: Under discussion


---

---

### GAP-SYNC-002: Effect timelines not uploaded to Nightscout

**Scenario**: Cross-project algorithm comparison, debugging

**Description**: Loop computes individual effect timelines but only uploads the final combined prediction. The component effects are lost.

**Loop-Specific Evidence**: `LoopAlgorithmEffects` contains:
- `insulin[]` - Expected glucose change from insulin
- `carbs[]` - Expected glucose change from carbs  
- `momentum[]` - Short-term trajectory
- `retrospectiveCorrection[]` - Unexplained discrepancy correction
- `insulinCounteraction[]` - Observed vs expected glucose change

Only `predicted.values[]` (the combined prediction) is uploaded to `devicestatus.loop`.

**Source**: [Loop Nightscout Sync](../mapping/loop/nightscout-sync.md#gap-sync-002-effect-timelines-not-uploaded)

**Impact**:
- Cannot debug algorithm behavior from Nightscout data
- Cannot compare Loop effects to oref0's separate `predBGs.IOB[]`, `predBGs.COB[]`, etc.
- Critical for cross-project interoperability analysis

**Possible Solutions**:
1. Loop uploads `effects` object alongside `predicted`
2. Nightscout defines schema for effect timelines
3. Optional upload flag for debugging/research mode

**Status**: Under discussion

**Related**:
- [Loop Algorithm Documentation](../mapping/loop/algorithm.md)

---

---

### GAP-SYNC-004: Override supersession not tracked in sync

**Scenario**: [Override Supersede](../conformance/scenarios/override-supersede/), [Sync Deduplication](../conformance/assertions/sync-deduplication.yaml)

**Description**: When an override is superseded by a new override, the lifecycle change is not synced to Nightscout. Loop and Trio only upload the initial override creation, not subsequent status changes.

**Source**: [AID Controller Sync Patterns - Gaps and Recommendations](../mapping/cross-project/aid-controller-sync-patterns.md)

**Impact**:
- Historical override queries unreliable
- Cannot determine why an override ended (superseded vs cancelled vs natural end)
- Related to GAP-001 (override supersession tracking)

**Possible Solutions**:
1. Upload override UPDATE when superseded
2. Add `supersededBy`, `actualEndType`, `actualEndDate` fields
3. Server-side inference from timestamps

**Status**: Under discussion

**Related**:
- [GAP-001](#gap-001-nightscout-lacks-override-supersession-tracking)
- [AID Controller Sync Patterns](../mapping/cross-project/aid-controller-sync-patterns.md)

---

---

### GAP-SYNC-005: Loop ObjectIdCache not persistent

**Scenario**: Treatment deduplication across app restarts

**Description**: Loop uses an in-memory `ObjectIdCache` to map `syncIdentifier` → Nightscout `_id`. This cache is purged on app restart or expiration (24 hours), causing Loop to lose knowledge of previously uploaded treatments.

**Evidence**:
- `externals/LoopWorkspace/LoopKit/NightscoutKit/NightscoutUploader.swift` - ObjectIdCache implementation
- Cache lifetime: 24 hours, memory-only

**Impact**:
- After app restart, Loop may re-upload treatments if it cannot find existing records
- Duplicate treatments in Nightscout if server doesn't deduplicate
- AAPS and xDrip+ persist sync IDs to database, avoiding this issue

**Possible Solutions**:
1. Persist ObjectIdCache to UserDefaults or CoreData
2. Use Nightscout v3 PUT with `identifier` for server-side dedup
3. Query Nightscout for existing treatments on startup

**Status**: Under discussion

**Related**:
- [Loop Sync Identity Fields](../mapping/loop/sync-identity-fields.md)
- GAP-SYNC-006

---

---

### GAP-SYNC-006: Loop uses Nightscout v1 API only

**Scenario**: Treatment deduplication and update semantics

**Description**: Loop uploads treatments via `POST /api/v1/treatments` which creates new records. The v3 API's `PUT /api/v3/treatments/{identifier}` would enable server-side upsert semantics, eliminating client-side dedup logic.

**Evidence**:
- `externals/LoopWorkspace/LoopKit/NightscoutKit/NightscoutClient.swift` - only v1 endpoints
- No `identifier` field usage for upsert

**Impact**:
- Requires client-side ObjectIdCache for deduplication
- No atomic upsert - must query then decide POST vs PUT
- AAPS uses v3 with interfaceIDs for reliable dedup

**Possible Solutions**:
1. Migrate Loop uploads to v3 PUT with `identifier = syncIdentifier`
2. Use v1 POST but include `identifier` for server dedup (if supported)
3. Accept as design limitation, rely on ObjectIdCache

**Status**: Under discussion

**Related**:
- [Loop Sync Identity Fields](../mapping/loop/sync-identity-fields.md)
- GAP-SYNC-005

---

---

### GAP-SYNC-007: syncIdentifier format not standardized

**Scenario**: Cross-system treatment correlation

**Description**: Loop's `syncIdentifier` format varies by source:
- Pump events: Hex string of raw pump data (variable length)
- Carb entries: UUID string
- HealthKit: Composite with source device

No standard format or prefix convention exists.

**Evidence**:
- `externals/LoopWorkspace/LoopKit/LoopKit/DoseEntry.swift` - pumpEventDose creates hex
- `externals/LoopWorkspace/LoopKit/LoopKit/CarbKit/StoredCarbEntry.swift` - uses UUID

**Impact**:
- Cannot reliably parse syncIdentifier to determine source type
- Collision risk between hex pump data and UUID formats unlikely but possible
- AAPS uses structured `interfaceIDs` object with typed fields

**Possible Solutions**:
1. Add type prefix: `pump:HEXDATA`, `carb:UUID`, `healthkit:UUID`
2. Document current formats for consumers
3. Accept variability, rely on eventType for disambiguation

**Status**: Documented

**Related**:
- [Loop Sync Identity Fields](../mapping/loop/sync-identity-fields.md)

---

## Database Layer Gaps

---

### GAP-SYNC-008: No Cross-Client Sync Conflict Resolution

**Scenario**: Multiple clients uploading conflicting data simultaneously.

**Description**: The UPSERT system replaces documents based on sync identity, but provides no conflict resolution or merge strategy. Last-write-wins may cause data loss.

**Affected Systems**: Loop + xDrip+, AAPS + Trio, any multi-uploader scenario.

**Impact**: Potential data loss when multiple AID systems upload overlapping data.

**Remediation**: Implement versioning or conflict detection with client notification.

---

---

### GAP-SYNC-009: V1 API Lacks Identifier Field

**Scenario**: Legacy clients using v1 API endpoints.

**Description**: V1 API does not generate or require the `identifier` field. Deduplication relies on legacy field matching only, which may fail for edge cases.

**Affected Systems**: Older Loop versions, legacy uploaders, direct API integrations.

**Impact**: Duplicate records may be created if dedup fields don't match exactly.

**Remediation**: Backfill `identifier` field during v1 uploads, document migration path.

---

---

### GAP-SYNC-010: No Sync Status Feedback

**Scenario**: Client needs confirmation of successful sync.

**Description**: Upload endpoints return HTTP 200 but provide no sync status, conflict detection, or guidance on retries. Clients cannot distinguish between insert and update.

**Affected Systems**: All uploading clients (Loop, AAPS, xDrip+, Trio).

**Impact**: Clients may retry unnecessarily or fail to detect sync failures.

**Remediation**: Return sync metadata: `{inserted: N, updated: M, conflicts: [...]}`.

---

## Authentication Gaps

---

### GAP-TZ-001: Timezone Handling Inconsistent

**Description**: Multiple PRs address timezone display issues (#8405, #8307). Device timezone vs browser timezone causes confusion for cross-timezone caregivers.

**Affected Systems**: Nightscout web UI, caregivers

**Impact**:
- Caregivers see wrong times when in different timezone than looper
- Careportal entries may use wrong timezone
- Historical data queries may be offset

**Remediation**: Merge PR#8405 timezone utility, ensure consistent use of profile timezone.

---

---

### GAP-TZ-002: Medtrum Timezone GMT+12 Bug

**Scenario**: Users in Pacific timezones (Fiji, New Zealand)

**Description**: Medtrum pump driver has a workaround for a bug where timezone settings fail for GMT > +12. This affects users in Pacific timezones.

**Source**: `AndroidAPS/pump/medtrum/...SetTimeZonePacket.kt:29`
```kotlin
// Workaround for bug where it fails to set timezone > GMT + 12
```

**Impact**:
- Users in affected timezones may have incorrect pump time
- Basal schedules may be misaligned with local time
- Workaround behavior is undocumented

**Possible Solutions**:
1. Document affected timezones
2. Implement proper timezone mapping for high-offset zones
3. Add user notification for affected timezones

**Status**: Under discussion

---

---

### GAP-TZ-003: utcOffset Recalculation on Upload

**Scenario**: Cross-timezone sync

**Description**: Nightscout recalculates `utcOffset` from the `dateString`'s timezone, rather than preserving the client-provided value. This can lead to unexpected behavior when uploading data from a device in a different timezone than the dateString indicates.

**Source**: `cgm-remote-monitor:tests/api.aaps-client.test.js:337`
```javascript
// QUIRK/FEATURE: Nightscout recalculates utcOffset from the dateString's timezone
```

**Impact**:
- Client-provided utcOffset may be overwritten
- Timezone handling differs between API v1 and v3
- Historical data analysis may be affected

**Possible Solutions**:
1. Document utcOffset handling behavior
2. Preserve client-provided utcOffset when valid
3. Add configuration option for behavior

**Status**: Under discussion

---

---

### GAP-TZ-004: utcOffset Unit Mismatch Between Nightscout and AAPS

**Scenario**: Cross-system sync between AAPS and Nightscout

**Description**: Nightscout stores and expects `utcOffset` in **minutes** (e.g., `-480` for UTC-8), while AAPS stores `utcOffset` internally in **milliseconds** (e.g., `-28800000` for UTC-8). This unit mismatch requires careful conversion during sync.

**Source**:
- Nightscout: `cgm-remote-monitor:lib/api3/generic/collection.js:182` - `doc.utcOffset = m.utcOffset()` (moment returns minutes)
- AAPS SDK: `core/nssdk/remotemodel/RemoteTreatment.kt:23` - `utcOffset: Long?` (documented as "minutes" in comments)
- AAPS DB: `database/entities/interfaces/DBEntryWithTime.kt:6` - `var utcOffset: Long` (milliseconds internally)

**Impact**:
- Potential off-by-factor-of-60000 if units confused
- AAPS SDK correctly handles conversion, but custom clients may not
- Documentation unclear about which unit applies where

**Possible Solutions**:
1. Document unit expectations clearly in API specs
2. Add validation for reasonable offset ranges
3. Standardize on one unit (minutes) across all systems

**Status**: Analyzed - see [Duration/utcOffset Impact Analysis](../docs/10-domain/duration-utcoffset-unit-analysis.md)

**Requirements**: REQ-UNIT-001, REQ-UNIT-003

---

---

### GAP-TZ-005: AAPS Fixed Offset Storage Breaks Historical DST Analysis

**Scenario**: Analyzing historical data that spans DST transitions

**Description**: AAPS captures `utcOffset` at event creation time using `TimeZone.getDefault().getOffset(timestamp)`. This captures the offset **at that moment** including DST, but the offset is fixed and won't update when viewing historical data. This means reconstructing local time from historical events may be incorrect if DST status has changed.

**Source**: `AndroidAPS/database/entities/Bolus.kt:43`
```kotlin
override var utcOffset: Long = TimeZone.getDefault().getOffset(timestamp).toLong(),
```

**Impact**:
- Historical reports may show incorrect local times for events near DST transitions
- Cannot retroactively determine if DST was in effect for old events
- Schedule alignment analysis across DST boundaries is unreliable
- Exported data may have misleading timezone information

**Possible Solutions**:
1. Store IANA timezone identifier alongside offset
2. Use offset calculated for the event's timestamp, not current time (already done for most events)
3. Document limitation in data export documentation

**Status**: Documented (architectural limitation)

---

---

### GAP-TZ-006: Loop Uploads Non-Standard Timezone Format

**Scenario**: Loop profile sync to Nightscout

**Description**: Loop uploads timezone strings with non-standard casing (`ETC/GMT+8` instead of `Etc/GMT+8`). Nightscout has a workaround but it's incomplete (uses `replace` instead of case-insensitive matching).

**Source**: `cgm-remote-monitor:lib/profilefunctions.js:179-181`
```javascript
// Work around Loop uploading non-ISO compliant time zone string
if (rVal) rVal.replace('ETC','Etc');
```

**Note**: This code has a bug - it calls `replace` but doesn't assign the result.

**Impact**:
- Timezone lookup may fail with uppercase prefix
- Profile time calculations may use fallback behavior
- Inconsistent behavior between Loop and other clients

**Possible Solutions**:
1. Fix Loop to use standard IANA format (`Etc/GMT+8`)
2. Fix Nightscout to use `rVal = rVal.replace('ETC','Etc')` (assign result)
3. Use case-insensitive timezone lookup

**Status**: Bug identified

---

---

### GAP-TZ-007: Missing Timezone Fallback Uses Server Local Time

**Scenario**: Profile uploaded without timezone field

**Description**: When a profile is uploaded without a `timezone` field, Nightscout falls back to the server's local timezone. This can cause schedule misalignment when the server is in a different timezone than the user.

**Source**: `cgm-remote-monitor:lib/profilefunctions.js:107-110`
```javascript
// Use local time zone if profile doesn't contain a time zone
// This WILL break on the server; added warnings elsewhere that this is missing
// TODO: Better warnings to user for missing configuration
```

**Impact**:
- Basal rates may be applied at wrong times
- ISF/CR lookups return incorrect values for time of day
- User may not realize timezone is missing

**Possible Solutions**:
1. Require timezone in profile validation
2. Default to UTC instead of server local
3. Add prominent UI warning when timezone missing

**Status**: Under discussion

---

## Error Handling Gaps

---
