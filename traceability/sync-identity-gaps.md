# Sync Identity Gaps

Domain-specific gaps extracted from gaps.md.
See [gaps.md](gaps.md) for the index.

---

### GAP-SYNC-001: Loop Uses POST-only, No Idempotent Upsert

**Scenario**: Network retry during treatment upload

**Description**: Loop uses POST-only uploads without PUT/upsert semantics. When a network timeout occurs after the server receives the treatment but before Loop receives the response, a retry creates a duplicate document. AAPS uses upsert with identifier, xDrip+ uses PUT with uuid.

**Source**: STPA analysis (`traceability/stpa/cross-project-patterns.md`)

**Impact**:
- Network retries may create duplicate bolus/carb records
- Duplicate boluses could affect IOB calculations
- Users may see duplicated treatments in Nightscout

**Possible Solutions**:
1. Loop adopts PUT/upsert with syncIdentifier
2. Nightscout server-side deduplication on syncIdentifier
3. Post-upload deduplication scan

**Status**: Documented

**Assertion References**: `syncidentifier-preserved`, `identifier-preserved`

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


## Cross-Controller Gaps

---

### GAP-SYNC-029: No Cross-Controller Deduplication

**Description**: Nightscout does not detect when the same treatment is entered in multiple controllers (e.g., Loop and Trio) and uploaded to the same instance.

**Affected Systems**: Nightscout, Loop, Trio, AAPS

**Impact**:
- Duplicate treatment records stored
- Incorrect IOB/COB calculations (doubled carbs, doubled boluses)
- Misleading historical data

**Source**: Deep dive analysis of `cgm-remote-monitor/lib/server/websocket.js:364` and `api3/storage/mongoCollection/utils.js:130`

**Current Behavior**: Deduplication based on `identifier` or `NSCLIENT_ID` only. No cross-controller awareness.

**Remediation**:
1. Add fuzzy deduplication: same amount ± tolerance, same eventType, within 2-minute window
2. Add `sourceController` field to all treatments
3. Warn user when identical treatment from different controllers detected

**Status**: Open

---

### GAP-SYNC-030: No Controller Conflict Warning

**Description**: Nightscout does not warn when multiple AID controllers (Loop, Trio, AAPS) are uploading deviceStatus to the same instance simultaneously.

**Affected Systems**: Nightscout UI, Loop, Trio, AAPS

**Impact**:
- User may not realize both controllers are active
- Conflicting therapy decisions possible
- Caregiver confusion about which controller is in charge

**Source**: Analysis of `loop.js:135` and `openaps.js:87` - both plugins can be active simultaneously

**Current Behavior**: Most recent deviceStatus displayed. No collision warning.

**Remediation**:
1. Add detection: if deviceStatus from different controllers within 5 minutes, show warning
2. Add `x-controller-id` header to API requests
3. Display active controller prominently in UI pill

**Status**: Open

---

### GAP-SYNC-031: Profile Sync Ambiguity

**Description**: When multiple controllers upload profiles to the same Nightscout instance, there is no indication which profile is authoritative.

**Affected Systems**: Nightscout, Loop, Trio

**Impact**:
- Caregiver may see wrong profile
- Uncertainty about which settings are active
- Potential for therapy errors if wrong profile assumed

**Source**: Cross-controller conflict analysis

**Current Behavior**: Most recent profile displayed. No source attribution.

**Remediation**:
1. Add `sourceController` field to profile records
2. Display profile source in UI
3. Warn if profiles from different controllers conflict

**Status**: Open

---

### GAP-SYNC-032: Loop/Trio Missing identifier Field

**Description:** Loop and Trio cache Nightscout `_id` locally but don't send `identifier` on uploads. Server calculates identifier from device+date+eventType.

**Source:** `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/ObjectIdCache.swift:56-58`

**Impact:** Cross-device sync may create duplicates; server's identifier won't match client's syncIdentifier.

**Remediation:** Send `syncIdentifier` as `identifier` field in upload payload.

### GAP-SYNC-033: xDrip+ UUID Not Sent as identifier

**Description:** xDrip+ generates local UUIDs but doesn't send them to Nightscout, relying on Last-Modified header for sync instead.

**Source:** `externals/xDrip/.../models/Treatments.java:95-96`

**Impact:** No server-side deduplication based on client identity.

**Remediation:** Send `uuid` as `identifier` in Nightscout API v3 calls.

### GAP-SYNC-034: No Cross-Controller Identity Standard

**Description:** Each system uses different ID naming conventions (syncIdentifier, nightscoutId, uuid). No shared standard for portable identity.

**Impact:** Records uploaded from different controllers may duplicate when syncing to same Nightscout.

**Remediation:** Define standard identifier format; all clients adopt UUID v5 calculation or prefix with controller name.

---

## Profile Switch Sync Gaps

### GAP-SYNC-035: No Profile Switch Events from Loop/Trio

**Description:** Loop and Trio upload profiles to the `profile` collection but do not create `Profile Switch` treatment events. Profile change history is not tracked in the treatments timeline.

**Affected Systems:** Loop, Trio, Nightscout

**Source:**
- `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/NightscoutService.swift:367` - uploads to profile collection only
- `externals/Trio/Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift:411` - uploads to profile collection only

**Impact:** Cannot retrospectively analyze when profiles changed; different timeline visibility vs AAPS users.

**Remediation:** Controllers could optionally create `Profile Switch` treatment events when uploading new profiles.

### GAP-SYNC-036: ProfileSwitch Embedded JSON Size

**Description:** AAPS embeds complete profile JSON in `profileJson` field of Profile Switch treatments, duplicating data and increasing document size.

**Affected Systems:** AAPS, Nightscout

**Source:**
- `externals/AndroidAPS/core/nssdk/src/main/kotlin/app/aaps/core/nssdk/localmodel/treatment/NSProfileSwitch.kt:24` - `profileJson: JSONObject?`

**Impact:** Large treatment documents; data duplication between `profile` and `treatments` collections.

**Remediation:** Consider storing profile reference ID instead of embedded JSON.

### GAP-SYNC-037: Percentage/Timeshift Not Portable

**Description:** AAPS Profile Switch supports `percentage` (insulin scaling) and `timeshift` (schedule rotation) features that are not understood by Loop or Trio.

**Affected Systems:** AAPS, Loop, Trio

**Source:**
- `externals/AndroidAPS/database/impl/src/main/kotlin/app/aaps/database/entities/ProfileSwitch.kt:49-50` - `timeshift: Long`, `percentage: Int`

**Impact:** Multi-controller households may see confusing profile data; percentage adjustments not applied by Loop/Trio.

**Remediation:** Document as AAPS-specific feature; Loop/Trio should ignore or warn on percentage!=100.

---

## Override/Temp Target Sync Gaps

### GAP-OVRD-001: Different eventTypes for Target Overrides

**Description**: Loop uses eventType `Override`, AAPS uses `Temporary Target` - they don't map to each other.

**Affected Systems**: Loop vs AAPS

**Evidence**:
- Loop: `OverrideTreament.swift` creates eventType `Override`
- AAPS: `NSTemporaryTarget.kt:29` uses `EventType.TEMPORARY_TARGET`

**Impact**: A Loop override is not recognized as a temp target by AAPS and vice versa.

**Remediation**: Nightscout could map between them, or each app could recognize both types.

### GAP-OVRD-002: insulinNeedsScaleFactor Not in AAPS

**Description**: Loop overrides can adjust insulin sensitivity; AAPS temp targets cannot.

**Affected Systems**: Loop vs AAPS

**Evidence**:
- Loop: `OverrideTreament.swift:59` includes `insulinNeedsScaleFactor`
- AAPS: `NSTemporaryTarget.kt` has no equivalent field

**Impact**: Loop overrides with insulin adjustment don't translate to AAPS.

**Remediation**: Document as design difference; AAPS uses profile switching for insulin adjustment.

### GAP-OVRD-003: Reason Enum vs Free Text

**Description**: AAPS uses enum with 6 values; Loop uses free text from preset names.

**Affected Systems**: Loop vs AAPS

**Evidence**:
- AAPS: `NSTemporaryTarget.Reason` enum with CUSTOM, HYPOGLYCEMIA, ACTIVITY, etc.
- Loop: `OverrideTreament.swift:30-39` maps context to string

**Impact**: Loop preset names like "🏃 Running" don't map to AAPS reasons.

**Remediation**: Nightscout could normalize reasons; apps could recognize common patterns.

### GAP-OVRD-004: Duration Units Differ

**Description**: Loop uses seconds; AAPS uses milliseconds for temp target duration.

**Affected Systems**: Loop vs AAPS

**Evidence**:
- Loop: `TemporaryScheduleOverride.swift:26-31` uses TimeInterval (seconds)
- AAPS: `NSTemporaryTarget.kt:24` documents duration in milliseconds

**Impact**: Duration conversion required when syncing between systems.

**Remediation**: Nightscout normalizes to minutes; apps should convert accordingly.

### GAP-OVRD-005: No Unified Override Representation

**Description**: Loop `Temporary Override` and AAPS `Temporary Target` are stored separately with different field semantics. No mapping or unification exists in Nocturne or cgm-remote-monitor.

**Affected Systems**: Cross-controller queries, Nightscout UI, statistics

**Evidence**:
- Loop: `eventType: "Temporary Override"` with `insulinNeedsScaleFactor`
- AAPS: `eventType: "Temporary Target"` with `targetTop`/`targetBottom`
- Nocturne: Both stored as-is in treatments collection

**Impact**: Cannot query "all active target modifications" without checking both eventTypes with different field interpretations.

**Remediation**: Define normalized schema or query helper that abstracts both types.

**Source**: [Nocturne Override Analysis](../docs/10-domain/nocturne-override-temptarget-analysis.md)

### GAP-OVRD-006: Override Supersession Not Tracked

**Description**: Neither Nocturne nor cgm-remote-monitor tracks override supersession. When a new override activates, the old override treatment is not updated.

**Affected Systems**: All

**Evidence**:
- Nocturne: No `supersededBy` or `status` field update on old treatment
- cgm-remote-monitor: No supersession tracking
- V4 StateSpan: Provides time-range queries but no override linking

**Impact**: Cannot determine override history chain or why overrides ended (superseded vs cancelled vs expired).

**Remediation**: Implement REQ-OVERRIDE-001 through REQ-OVERRIDE-005.

**Source**: [Nocturne Override Analysis](../docs/10-domain/nocturne-override-temptarget-analysis.md)

### GAP-OVRD-007: Duration Unit Mismatch in Loop Presets

**Description**: LoopOverridePreset.Duration is in seconds; Treatment.Duration is in minutes. Conversion required.

**Affected Systems**: Loop, Nocturne

**Evidence**:
- `LoopModels.cs:182-183`: `Duration` in seconds
- `Treatment.cs:182`: `Duration` in minutes

**Impact**: Off-by-60x errors if units confused.

**Remediation**: Document unit expectations; add validation.

**Source**: [Nocturne Override Analysis](../docs/10-domain/nocturne-override-temptarget-analysis.md)

---

### GAP-NOCTURNE-004: ProfileSwitch Percentage/Timeshift Application Divergence

**Description**: Nocturne actively applies `percentage` and `timeshift` fields from ProfileSwitch treatments when computing profile values for algorithm calculations. cgm-remote-monitor only displays these values without applying them to calculations.

**Affected Systems**: Nocturne, cgm-remote-monitor

**Evidence**:
- Nocturne: `src/API/Nocturne.API/Services/ProfileService.cs:175-241` applies percentage scaling to basal, ISF, CR
- cgm-remote-monitor: Displays percentage/timeshift in treatments but does not apply them

**Impact**:
- Users migrating from cgm-remote-monitor to Nocturne may see different IOB/COB/predictions
- Algorithm recommendations differ based on server platform
- Same ProfileSwitch treatment produces different effective profiles on each platform

**Remediation**: Document as expected divergence. Nocturne behavior is more correct per AAPS semantics (percentage is meant to affect actual insulin delivery). Consider adding percentage application to cgm-remote-monitor for consistency.

**Source**: [Nocturne ProfileSwitch Analysis](../docs/10-domain/nocturne-profileswitch-analysis.md)

**Status**: Documented

### GAP-NOCTURNE-005: Profile API Returns Raw Values Despite Active ProfileSwitch

**Description**: Nocturne's Profile API endpoints (V1/V3) return raw profile data without applying percentage/timeshift from active ProfileSwitch treatments. Internal calculations (IOB, COB, bolus wizard) do apply scaling, creating a divergence between API consumers and Nocturne's own displays.

**Affected Systems**: Loop, Trio, any client fetching profiles via API while AAPS ProfileSwitch is active.

**Impact**: Controllers like Loop/Trio receive raw profiles and cannot detect that AAPS has activated a percentage-based profile adjustment. This means their algorithms operate on different effective values than AAPS intended.

**Remediation**: Consider adding an `/api/v4/profile/effective` endpoint that returns computed values with active ProfileSwitch applied, or add metadata to profile responses indicating active ProfileSwitch details.

**Related**: GAP-NOCTURNE-004, GAP-SYNC-037

---

## Profile Sync Divergences

### GAP-SYNC-038: Profile Deduplication Fallback Missing in Nocturne

**Description**: Nocturne lacks `created_at` fallback deduplication for profiles. cgm-remote-monitor uses `identifier` OR `created_at` for deduplication; Nocturne only uses `Id`/`OriginalId`.

**Affected Systems**: Controllers uploading profiles via V1 API to Nocturne

**Evidence**:
- cgm-remote-monitor: `lib/api3/generic/setup.js:65-73` - `dedupFallbackFields: ['created_at']`
- Nocturne: `src/Infrastructure/Nocturne.Infrastructure.Data/Repositories/ProfileRepository.cs:159-167` - only checks `Id` or `OriginalId`

**Impact**: Duplicate profiles may accumulate when uploading without identifiers.

**Remediation**: Add `created_at` fallback matching to Nocturne's `CreateProfilesAsync`.

**Source**: [Profile Sync Comparison](../docs/10-domain/nocturne-cgm-remote-monitor-profile-sync.md)

**Status**: Open

---

### GAP-SYNC-039: Profile srvModified Field Missing in Nocturne

**Description**: Nocturne's Profile model lacks `srvModified` field. cgm-remote-monitor auto-updates `srvModified` on every profile modification for sync tracking.

**Affected Systems**: Clients using `srvModified$gt` filter for profile sync

**Evidence**:
- cgm-remote-monitor: `lib/api3/generic/update/replace.js:28-29` - sets `srvModified`
- Nocturne: `src/Core/Nocturne.Core.Models/Profile.cs` - no srvModified property

**Impact Analysis** (updated 2026-01-30):
- ✅ `/api/v3/lastModified` endpoint uses `UpdatedAtPg` for profiles (correct behavior)
- ✅ AAPS profile sync works (uses endpoint, not per-record field)
- ⚠️ Per-record srvModified inspection not available (low impact)

**Remediation**: No change required. The `/api/v3/lastModified` endpoint correctly uses `UpdatedAtPg` for profile modification tracking.

**Source**: [Profile Sync Comparison](../docs/10-domain/nocturne-cgm-remote-monitor-profile-sync.md), [srvModified Gap Analysis](../docs/10-domain/nocturne-srvmodified-gap-analysis.md)

**Status**: ✅ No Remediation Required (2026-01-30)

---

### GAP-SYNC-040: Profile Delete Semantics Differ

**Description**: cgm-remote-monitor uses soft delete (sets `isValid: false`); Nocturne uses hard delete (removes from database).

**Affected Systems**: Sync clients expecting deleted profiles to remain visible with isValid=false

**Evidence**:
- cgm-remote-monitor: Soft delete with `isValid: false`, `srvModified` updated
- Nocturne: Hard delete from database

**Impact**: Clients may not detect profile deletions when syncing with Nocturne.

**Remediation**: Implement soft delete in Nocturne with isValid field.

**Source**: [Profile Sync Comparison](../docs/10-domain/nocturne-cgm-remote-monitor-profile-sync.md)

**Status**: Open

---

## V4 API Extension Gaps

### GAP-V4-001: StateSpan API Not Standardized

**Description**: Nocturne's V4 StateSpan API (`/api/v4/state-spans`) provides time-ranged state tracking for profiles and overrides, but this is proprietary and not part of any Nightscout standard.

**Affected Systems**: Loop, Trio, AAPS, cgm-remote-monitor

**Evidence**:
- Nocturne: `src/API/Nocturne.API/Controllers/V4/StateSpansController.cs` - full CRUD for state spans
- cgm-remote-monitor: No equivalent endpoint or data model

**Impact**: V4 features for profile activation history and override tracking are not portable across ecosystem. Clients cannot consume or produce compatible data when switching between Nocturne and cgm-remote-monitor.

**Remediation**: Propose StateSpan as RFC for Nightscout v4 API standard.

**Source**: [Nocturne V4 ProfileSwitch Extensions](../docs/10-domain/nocturne-v4-profile-extensions.md)

**Status**: Open

---

### GAP-V4-002: Profile Activation History Not in V3

**Description**: V3 API has no mechanism to query profile activation history. Only profile documents can be queried via `/api/v3/profile`, not when they were activated or which profile was active at a given time.

**Affected Systems**: All using V3 API

**Evidence**:
- V3 API: Only `/api/v3/profile` for document CRUD
- V4 API: `/api/v4/state-spans/profiles` provides activation history
- V4 ChartDataController returns `ProfileSpans` in response

**Impact**: Cannot build profile timeline or retrospectively analyze which profile was active at any point without using V4 StateSpan API (Nocturne-specific).

**Remediation**: Add profile activation events to V3 treatments collection or migrate to V4 with StateSpan.

**Source**: [Nocturne V4 ProfileSwitch Extensions](../docs/10-domain/nocturne-v4-profile-extensions.md)

**Status**: Open

---

## Rust oref Profile Integration Gaps

### GAP-OREF-001: PredictionService Bypasses ProfileService

**Description**: Nocturne's `PredictionService` reads profiles directly from the database via `_postgresService.GetProfilesAsync()`, bypassing `ProfileService` which applies percentage/timeshift from active ProfileSwitch treatments.

**Affected Systems**: Nocturne predictions when AAPS ProfileSwitch is active

**Evidence**:
- `PredictionService.cs:165-186` - reads from database directly
- `ProfileService.cs:228-241` - applies percentage/timeshift (not used by PredictionService)
- `OrefProfile` receives raw values: `CurrentBasal = activeStore.Basal?.FirstOrDefault()?.Value`

**Impact**: Algorithm predictions use raw profile values instead of scaled values. A 150% ProfileSwitch is ignored by predictions, leading to incorrect IOB/COB calculations.

**Remediation**: Inject `IProfileService` into `PredictionService`; use `GetBasalRate()`, `GetSensitivity()`, `GetCarbRatio()` methods instead of direct database access.

**Source**: [Nocturne Rust oref Profile Analysis](../docs/10-domain/nocturne-rust-oref-profile-analysis.md)

**Status**: Open

---

### GAP-OREF-002: OrefProfile Lacks Full Schedule Support

**Description**: The C# `OrefProfile` model only passes single current values (`CurrentBasal`, `Sens`, `CarbRatio`) to Rust oref, not the full time-varying schedules that Rust oref supports.

**Affected Systems**: Nocturne algorithm accuracy for multi-rate profiles

**Evidence**:
- Rust `Profile` has `basal_profile: Vec<BasalScheduleEntry>`
- C# `OrefProfile` has `CurrentBasal: double`
- `PredictionService.cs:176`: `CurrentBasal = activeStore.Basal?.FirstOrDefault()?.Value`

**Impact**: Multi-rate profile schedules are reduced to first/current value only. Time-of-day variations ignored in predictions.

**Remediation**: Extend `OrefProfile` to include schedule arrays; serialize full schedules to Rust.

**Source**: [Nocturne Rust oref Profile Analysis](../docs/10-domain/nocturne-rust-oref-profile-analysis.md)

**Status**: Open

---

### GAP-OREF-003: No Timeshift Propagation to Rust

**Description**: Even if percentage is applied, timeshift rotation is not propagated to Rust oref for schedule lookups.

**Affected Systems**: Users with timeshift-based ProfileSwitch (travel, circadian adjustments)

**Evidence**:
- `ProfileService.cs:189-190` applies timeshift via `adjustedTime`
- `PredictionService` does not use adjusted time for oref calls
- Rust oref uses raw UTC time for schedule lookups

**Impact**: Rust oref uses wrong time-of-day for schedule lookups when timeshift is active.

**Remediation**: Either apply timeshift in C# before calling Rust, or pass timeshift parameter to Rust.

**Source**: [Nocturne Rust oref Profile Analysis](../docs/10-domain/nocturne-rust-oref-profile-analysis.md)

**Status**: Open

---

## StateSpan Standardization Gaps

---

### GAP-STATESPAN-001: No Standard Time-Range State API

**Description**: cgm-remote-monitor stores time-ranged states (profile, override, temp basal) as treatments with implicit durations. No dedicated collection or API for querying state history by time range.

**Affected Systems**: cgm-remote-monitor, Loop, AAPS, Trio, xDrip+

**Impact**:
- Must calculate end times from duration or next event
- Cancel events disconnected from originals
- Time-range queries inefficient
- Pump mode not queryable

**Remediation**: Adopt StateSpan collection with V3 API endpoint (see proposal).

**Source**: [StateSpan Standardization Proposal](../docs/sdqctl-proposals/statespan-standardization-proposal.md)

**Status**: Proposal drafted

---

### GAP-STATESPAN-002: Treatment Cancel Events Disconnected

**Description**: `Temporary Override Cancel` treatment has no foreign key linking to the original override it cancels.

**Affected Systems**: cgm-remote-monitor, Loop

**Evidence**:
- `externals/cgm-remote-monitor/lib/server/loop.js:65`
- Cancel event matched by timestamp proximity, not ID

**Impact**: Ambiguous which override was cancelled when multiple active.

**Remediation**: StateSpan model with explicit `endMills` eliminates need for cancel events.

**Status**: Open

---

### GAP-STATESPAN-003: No User Activity Annotations

**Description**: cgm-remote-monitor has no standard way to record sleep, exercise, illness, or travel periods that affect insulin sensitivity.

**Affected Systems**: All AID consumers

**Impact**:
- Cannot contextualize glucose patterns with activities
- No retrospective analysis by activity type
- Algorithm adjustments require manual correlation

**Remediation**: StateSpan categories for Sleep, Exercise, Illness, Travel (Phase 2).

**Status**: Open

---

## PostgreSQL Migration Gaps

### GAP-MIGRATION-001: srvModified Not Distinct from Mills

**Description**: Nocturne computes `srvModified` from `mills` rather than storing it independently. This means per-record `srvModified` reflects event time, not server modification time.

**Affected Systems**: Nocturne, clients inspecting per-record `srvModified`

**Evidence**:
- `externals/nocturne/src/Core/Nocturne.Core.Models/Treatment.cs:30-31`
  ```csharp
  [JsonPropertyName("srvModified")]
  public long? SrvModified => Mills > 0 ? Mills : null;
  ```

**Impact Analysis** (updated 2026-01-30):
- ✅ `/api/v3/lastModified` endpoint uses `SysUpdatedAt` (correct behavior)
- ✅ AAPS incremental sync works (uses endpoint, not per-record field)
- ✅ Loop incremental sync works (uses endpoint, not per-record field)
- ⚠️ Per-record inspection shows event time, not modification time (low impact)

**Remediation**: No change required. The `/api/v3/lastModified` endpoint correctly uses `SysUpdatedAt` for modification tracking, which is what sync clients rely on.

**Related**: GAP-SYNC-039

**Analysis**: [srvModified Gap Analysis](../docs/10-domain/nocturne-srvmodified-gap-analysis.md)

**Status**: ✅ No Remediation Required (2026-01-30)

---

### GAP-MIGRATION-002: srvCreated Also Computed from Mills

**Description**: Like `srvModified`, Nocturne's `srvCreated` is computed from `mills` rather than representing actual server creation timestamp.

**Affected Systems**: Nocturne, audit trail consumers

**Evidence**:
- `externals/nocturne/src/Core/Nocturne.Core.Models/Extensions/EntryResponseExtensions.cs:195`
  ```csharp
  public long? SrvCreated => _entry.Mills > 0 ? _entry.Mills : null;
  ```

**Impact**:
- No server-side audit trail of when documents were created
- Backdated events appear to have been created in the past

**Remediation**: Use PostgreSQL `sys_created_at` column for `srvCreated` value.

**Status**: Open

---

### GAP-MIGRATION-003: Original MongoDB ID Truncation Risk

**Description**: `original_id` column is VARCHAR(24), matching MongoDB ObjectId hex length. However, some systems (xDrip+, custom) may use longer UUIDs as identifiers.

**Affected Systems**: Migration from non-MongoDB sources

**Evidence**:
- `externals/nocturne/src/Infrastructure/Nocturne.Infrastructure.Data/Entities/EntryEntity.cs:23-24`
  ```csharp
  [Column("original_id")]
  [MaxLength(24)]
  public string? OriginalId { get; set; }
  ```

**Impact**:
- UUID identifiers (36 chars) would be truncated
- May cause sync identity loss for xDrip+ entries

**Remediation**: Increase `MaxLength` to 36 or 64 for UUID compatibility.

**Status**: Open

---

**Source**: [Migration Field Fidelity Analysis](../mapping/nocturne/migration-field-fidelity.md)
