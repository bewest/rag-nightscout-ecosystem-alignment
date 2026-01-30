# Nightscout Api Gaps

Domain-specific gaps extracted from gaps.md.
See [gaps.md](gaps.md) for the index.

---

### GAP-API-001: API v1 Cannot Detect Deletions

**Scenario**: Cross-client data synchronization

**Description**: API v1 clients (Loop, Trio, xDrip+, OpenAPS) cannot detect when documents are deleted by other clients or by API v3 soft-delete. The v1 API has no mechanism to return deleted documents.

**Impact**:
- Stale data may persist in client caches indefinitely
- Deleted treatments may continue to affect IOB calculations
- No way to sync deletion events across clients
- "Zombie" data accumulates over time

**Possible Solutions**:
1. v1 clients implement periodic full-sync to detect missing documents
2. Nightscout adds deletion tombstones to v1 responses
3. v1 clients migrate to v3 history endpoint

**Status**: Under discussion

**Related**:
- [Nightscout API Comparison](../docs/10-domain/nightscout-api-comparison.md)
- [API v1 Compatibility Spec](../externals/cgm-remote-monitor/docs/requirements/api-v1-compatibility-spec.md)

---

## Insulin Curve Gaps

---

### GAP-API-002: Identifier vs _id Addressing Inconsistency

**Scenario**: Cross-API document identity

**Description**: API v1 uses `_id` (MongoDB ObjectId), API v3 uses `identifier` (server-assigned). Documents may have both fields with different values, causing confusion when tracking document identity across API versions.

**Impact**:
- Clients using different APIs cannot reliably reference the same document
- Deduplication may change `identifier` for v1-created documents
- No canonical identity field across both APIs

**Possible Solutions**:
1. Use `_id` as canonical identity for v1 clients, `identifier` for v3 clients
2. Ensure `identifier` equals `_id` for new documents
3. Document clear mapping rules

**Status**: Under discussion

**Related**:
- [Nightscout API Comparison](../docs/10-domain/nightscout-api-comparison.md)

---

---

### GAP-API-003: No API v3 Adoption Path for iOS Clients

**Scenario**: Ecosystem fragmentation

**Description**: Loop and Trio continue to use API v1 with no apparent migration plans. AAPS is the only major v3 client. This creates ecosystem fragmentation where sync behaviors differ significantly.

**Impact**:
- iOS clients lack efficient incremental sync capabilities
- iOS clients cannot detect deletions
- Different authentication and permission models
- Bifurcated documentation and tooling

**Possible Solutions**:
1. Document v3 benefits to encourage iOS client adoption
2. Create Swift SDK for v3 API
3. Accept ecosystem bifurcation and document interoperability patterns

**Status**: Under discussion

**Related**:
- [Nightscout API Comparison](../docs/10-domain/nightscout-api-comparison.md)
- [Loop Nightscout Sync](../mapping/loop/nightscout-sync.md)
- [Trio Nightscout Sync](../mapping/trio/nightscout-sync.md)

---

---

### GAP-API-004: Authentication Granularity Gap Between v1 and v3

**Scenario**: Access control, follower apps

**Description**: API v1 authentication is all-or-nothing (valid secret grants full `*` permissions). Cannot grant read-only access to specific collections without making the entire site public-readable.

**Impact**:
- Follower apps receive full write access unnecessarily
- No way to create collection-specific tokens
- Cannot audit who performed which operations
- Must choose between full access or public-readable

**Possible Solutions**:
1. Migrate to v3 JWT tokens for fine-grained access control
2. Add role-based tokens to v1 API
3. Use gateway-level access control

**Status**: Under discussion

**Related**:
- [Nightscout API Comparison](../docs/10-domain/nightscout-api-comparison.md)

---

---

### GAP-API-005: Deduplication Behavior Differs Between API Versions

**Scenario**: Data integrity, duplicate prevention

**Description**: API v3 returns `isDeduplication: true` when a document matches existing data and provides the existing document's `identifier`. API v1 silently accepts potential duplicates without indication.

**Impact**:
- v1 clients may create duplicate documents unknowingly
- v3 clients see duplicates created by v1 clients
- Inconsistent behavior when same document uploaded via both APIs
- No way for v1 clients to know if upload was deduplicated

**Possible Solutions**:
1. Use client-side deduplication with unique `syncIdentifier`
2. Add deduplication indicator to v1 responses
3. Use PUT upsert semantics consistently

**Status**: Under discussion

**Related**:
- [Nightscout API Comparison](../docs/10-domain/nightscout-api-comparison.md)
- GAP-003 (sync identity)

---

---

### GAP-API-006: No Machine-Readable OpenAPI Specification

**Scenario**: Client SDK generation and API validation

**Description**: Neither v1 nor v3 API has a machine-readable OpenAPI/Swagger specification. API structure must be reverse-engineered from source code.

**Evidence**:
```
lib/api3/  - No openapi.yaml or swagger.json
lib/api/   - No openapi.yaml or swagger.json
```

**Impact**:
- Cannot auto-generate client SDKs for Loop, AAPS, Trio
- No automated request/response validation
- Documentation drift from implementation
- Harder for new client developers to integrate

**Possible Solutions**:
1. Generate OpenAPI 3.0 spec from code analysis (this workspace)
2. Add swagger-jsdoc annotations to endpoints
3. Create manual OpenAPI spec and validate against implementation

**Status**: Documented

**Related**:
- [API Deep Dive](../docs/10-domain/cgm-remote-monitor-api-deep-dive.md)
- [specs/openapi/](../specs/openapi/) - Alignment workspace specs

---

---

### GAP-API-007: v1/v3 Response Structure Divergence

**Scenario**: Multi-version client compatibility

**Description**: v1 and v3 APIs return different response structures for the same data, requiring clients to handle both formats.

**Evidence**:
```javascript
// v1 response: Raw array
GET /api/v1/entries
[{sgv: 120, date: 1234567890000}, ...]

// v3 response: Wrapped with metadata
GET /api/v3/entries
{
  status: 200,
  result: [{sgv: 120, date: 1234567890000}, ...],
  ...
}
```

**Impact**:
- Clients must detect API version and parse accordingly
- Migration from v1 to v3 requires response handling changes
- Increased client code complexity

**Possible Solutions**:
1. Document response format differences in API spec
2. Provide v1-compatible wrapper for v3 responses
3. Add Accept header negotiation for format preference

**Status**: Documented

**Related**:
- [API Deep Dive](../docs/10-domain/cgm-remote-monitor-api-deep-dive.md)

---

---

### GAP-API-008: Inconsistent Timestamp Field Names

**Scenario**: Cross-collection data correlation

**Description**: Different collections use different field names for primary timestamps, complicating client-side data correlation.

**Evidence**:
| Collection | Primary Timestamp | Format |
|------------|------------------|--------|
| entries | `date` | Epoch milliseconds |
| treatments | `created_at` | ISO-8601 string |
| devicestatus | `created_at` | ISO-8601 string |
| profile | `created_at` | ISO-8601 string |

**Impact**:
- Client code must know per-collection timestamp fields
- Cannot use generic timestamp filtering across collections
- Confusion for developers new to API

**Possible Solutions**:
1. Document canonical timestamp field per collection
2. Add `timestamp` alias that maps to collection-specific field
3. Normalize all to epoch milliseconds in future API version

**Status**: Documented

**Related**:
- [API Deep Dive](../docs/10-domain/cgm-remote-monitor-api-deep-dive.md)
- GAP-TZ-001 (timezone handling)

---

## Plugin System Gaps (2026-01-29 Audit)

---

### GAP-AUTH-001: `enteredBy` field is unverified

**Scenario**: Authorization and audit scenarios

**Description**: The `enteredBy` field in treatments is a free-form nickname with no authentication verification. Anyone can claim to be anyone.

**Impact**:
- Cannot audit who actually made changes
- No accountability for data mutations
- Cannot implement authority-based conflict resolution

**Possible Solutions**:
1. OIDC Actor Identity - replace with verified claims
2. Add separate verified `actor` field alongside legacy `enteredBy`
3. Gateway-level identity injection

**Status**: Under discussion

**Related**:
- [OIDC Actor Identity Proposal](../externals/cgm-remote-monitor/docs/proposals/oidc-actor-identity-proposal.md)
- [Authorization Mapping](../mapping/nightscout/authorization.md)

---

---

### GAP-AUTH-002: No authority hierarchy in Nightscout

**Scenario**: Conflict resolution scenarios

**Description**: Nightscout treats all authenticated writes equally. There is no concept of authority levels (human > agent > controller).

**Impact**:
- Controllers can overwrite human-initiated overrides
- No protection for primary user decisions
- Cannot implement safe AI agent integration

**Possible Solutions**:
1. Implement authority levels in API layer
2. Add authority field to treatments
3. Handle in gateway layer (NRG)

**Status**: Proposed in conflict-resolution.md

**Related**:
- [Conflict Resolution Proposal](../externals/cgm-remote-monitor/docs/proposals/conflict-resolution.md)
- [Authority Model](../docs/10-domain/authority-model.md)

---

---

### GAP-AUTH-003: API_SECRET Grants Full Admin Access

**Scenario**: Any client with API_SECRET can perform admin operations.

**Description**: API_SECRET bypasses role-based access control entirely. A compromised secret exposes all administrative functions including subject/role management.

**Affected Systems**: All Nightscout instances, all uploading clients.

**Impact**: No granular access control for API_SECRET holders; single point of compromise.

**Remediation**: Deprecate API_SECRET for write operations; require subject tokens with explicit roles.

---

---

### GAP-AUTH-004: No Token Revocation Mechanism

**Scenario**: Compromised access token needs to be invalidated.

**Description**: Access tokens have no revocation endpoint. Deleting a subject is the only way to invalidate a token, which loses all subject metadata.

**Affected Systems**: All clients using access tokens (Loop, AAPS, xDrip+, Trio).

**Impact**: Compromised tokens remain valid until subject deletion or JWT expiry.

**Remediation**: Add token revocation API and token blacklist mechanism.

---

---

### GAP-AUTH-005: JWT Secret Stored in Node Modules

**Scenario**: JWT signing key persistence.

**Description**: JWT secret is stored in `node_modules/.cache/_ns_cache/randomString`, which may be cleared during npm updates or container rebuilds.

**Affected Systems**: All Nightscout instances using JWT.

**Impact**: JWT secret loss invalidates all issued tokens, forcing re-authentication.

**Remediation**: Store JWT secret in persistent location (environment variable or database).

---

## Frontend/UI Gaps

---

### GAP-DB-001: Entries batch ordering not guaranteed

**Scenario**: CGM data with same timestamp

**Description**: The `lib/server/entries.js` uses `forEach` for batch inserts, which does not guarantee order. If two entries have the same `sysTime`, insertion order may vary.

**Evidence**:
- `externals/cgm-remote-monitor-official/lib/server/entries.js:98` - uses `forEach`
- Compare with `lib/server/treatments.js:21` which uses `async.eachSeries`

**Impact**:
- CGM readings with same timestamp may appear in random order
- Affects historical data display when multiple readings arrive simultaneously

**Possible Solutions**:
1. Use `async.eachSeries` like treatments
2. Add sequence number for same-timestamp entries
3. Sort by `_id` as secondary key

**Status**: Under discussion

**Related**:
- [cgm-remote-monitor Database Deep Dive](../docs/10-domain/cgm-remote-monitor-database-deep-dive.md)

---

---

### GAP-DB-002: MongoDB driver deprecated patterns

**Scenario**: Node.js 18+ console warnings

**Description**: Uses deprecated `ObjectID` import and connection options (`useNewUrlParser`, `useUnifiedTopology`).

**Evidence**:
- `externals/cgm-remote-monitor-official/lib/storage/mongo-storage.js:28-30` - deprecated options
- `externals/cgm-remote-monitor-official/lib/api3/storage/mongoCollection/utils.js:6` - `ObjectID` import

**Impact**:
- Console warnings in Node.js 18+
- May cause issues with MongoDB 6.x+ driver

**Possible Solutions**:
1. Upgrade to `mongodb` 4.x or 5.x driver
2. Use `ObjectId` import (new naming)
3. Remove deprecated options (defaults in 4.x+)

**Status**: Documented

**Related**:
- [cgm-remote-monitor Database Deep Dive](../docs/10-domain/cgm-remote-monitor-database-deep-dive.md)

---

---

### GAP-DB-003: No bulk write optimization

**Scenario**: Large batch uploads

**Description**: All batch operations use sequential single-document operations rather than MongoDB's `bulkWrite()` API.

**Evidence**:
- `externals/cgm-remote-monitor-official/lib/server/entries.js:98` - `forEach` with individual updates
- No `bulkWrite` usage in codebase

**Impact**:
- Higher latency for large uploads (100+ documents)
- More round-trips to MongoDB
- Potential timeout issues on slow connections

**Possible Solutions**:
1. Implement `bulkWrite` for batch inserts
2. Use `{ ordered: true }` to preserve insertion order
3. Batch into chunks of 100-500 documents

**Status**: Under discussion

**Related**:
- [cgm-remote-monitor Database Deep Dive](../docs/10-domain/cgm-remote-monitor-database-deep-dive.md)

---

---

### GAP-ERR-001: Empty Array Creates Empty Treatment

**Scenario**: Edge case - empty batch upload

**Description**: Sending an empty array `[]` to the treatments API does not return an error. Instead, current behavior creates an empty treatment with auto-generated `created_at`. This is surprising behavior that may mask client-side bugs.

**Source**: `cgm-remote-monitor:tests/api.v1-batch-operations.test.js:163-164`
```javascript
// SPEC: Edge case - empty array should not error (Section 4.6)
// NOTE: Current behavior creates empty treatment with auto-generated created_at
```

**Impact**:
- May create phantom treatments
- Client bugs may go undetected
- Data pollution with empty records

**Possible Solutions**:
1. Return HTTP 400 for empty array
2. Return HTTP 200 with empty array response
3. Document current behavior
4. Add validation to reject truly empty items

**Status**: Under discussion

---

---

### GAP-ERR-002: CRC Mismatch Ignored in Medtronic History

**Scenario**: Medtronic pump history download

**Description**: Medtronic history pages with CRC mismatches are logged as warnings but the data is processed anyway. This could lead to corrupted data being used for IOB calculations.

**Source**: `AndroidAPS/pump/medtronic/...RawHistoryPage.kt:39`
```kotlin
Locale.ENGLISH, "Stored CRC (%d) is different than calculated (%d), but ignored for now.", crcStored,
```

**Impact**:
- Corrupted pump history may be used
- IOB calculations may be incorrect
- Silent data corruption possible

**Possible Solutions**:
1. Retry history download on CRC mismatch
2. Alert user to potential data corruption
3. Exclude entries with CRC mismatch from calculations
4. Log as error instead of warning

**Status**: Under discussion

---

---

### GAP-ERR-003: Unknown Pump History Entries Silently Ignored

**Scenario**: New pump firmware with new entry types

**Description**: Medtronic pump history decoder silently ignores unknown entry types. Several entry types are marked with `/* TODO */` and have unknown purposes. New firmware versions may introduce entry types that are completely ignored.

**Source**: `AndroidAPS/pump/medtronic/...PumpHistoryEntryType.kt:13-17`
```kotlin
/* TODO */ EventUnknown_MM512_0x2e(0x2e, "Unknown Event 0x2e", PumpHistoryEntryGroup.Unknown, 2, 5, 100),
/* TODO */ ConfirmInsulinChange(0x3a, "Confirm Insulin Change", PumpHistoryEntryGroup.Unknown),
/* TODO */ Sensor_0x51(0x51, "Unknown Event 0x51", PumpHistoryEntryGroup.Unknown),
/* TODO */ Sensor_0x52(0x52, "Unknown Event 0x52", PumpHistoryEntryGroup.Unknown),
```

**Impact**:
- Undiscovered boluses or temp basals may be missed
- IOB calculations may be incomplete
- No visibility into unknown events

**Possible Solutions**:
1. Log unknown entries with full data for analysis
2. Surface unknown entries to user for reporting
3. Community effort to document unknown entry types
4. Add mechanism to report unknown entries

**Status**: Under discussion

---

## Specification Gaps

---

### GAP-PLUGIN-001: No AAPS-Specific Plugin

**Scenario**: AAPS controller display in Nightscout

**Description**: AAPS uploads to Nightscout but uses the OpenAPS plugin for display. AAPS-specific fields (interfaceIDs, pumpType, SMB details) are not utilized.

**Evidence**:
```javascript
// openaps.js handles AAPS data via OpenAPS format
// AAPS unique fields not processed:
// - interfaceIDs.nightscoutId
// - pumpType, pumpSerial
// - SMB-specific visualization
```

**Impact**:
- AAPS users may see incomplete status information
- SMB activity not differentiated from regular temp basals
- AAPS-specific pump details not displayed

**Possible Solutions**:
1. Extend OpenAPS plugin with AAPS detection
2. Create dedicated AAPS plugin
3. Document AAPS→OpenAPS field mapping

**Status**: Documented

**Related**:
- [Plugin Deep Dive](../docs/10-domain/cgm-remote-monitor-plugin-deep-dive.md)

---

---

### GAP-PLUGIN-002: Prediction Curve Format Mismatch

**Scenario**: Cross-controller prediction visualization

**Description**: Loop uses single prediction array while OpenAPS/AAPS use 6 separate curves (IOB, ZT, COB, aCOB, UAM, Values). Visualization must handle both formats.

**Evidence**:
```javascript
// Loop format:
status.loop.predicted.values = [120, 118, 115, ...]

// OpenAPS format:
status.openaps.predBGs = {
  IOB: [120, 115, 110, ...],
  ZT: [120, 118, 116, ...],
  COB: [120, 125, 130, ...],
  aCOB: [...],
  UAM: [...]
}
```

**Impact**:
- Unified prediction display requires format normalization
- Loop users see single curve, OpenAPS users see multiple
- Cross-system comparison difficult

**Possible Solutions**:
1. Document canonical prediction format in API spec
2. Normalize to common format in plugin layer
3. Support both formats in visualization

**Status**: Documented

**Related**:
- [Plugin Deep Dive](../docs/10-domain/cgm-remote-monitor-plugin-deep-dive.md)
- [Prediction Arrays Comparison](../docs/10-domain/prediction-arrays-comparison.md)

---

---

### GAP-PLUGIN-003: Enacted Confirmation Field Inconsistency

**Scenario**: OpenAPS/AAPS enacted status display

**Description**: OpenAPS plugin requires explicit `received: true` flag but also accepts typo `recieved`. AAPS may not consistently send this field.

**Evidence**:
```javascript
// openaps.js:44 - Typo tolerance
if (enacted.received || enacted.recieved) {
  // Show as enacted
}
// AAPS may omit this field entirely
```

**Impact**:
- False "not enacted" status for AAPS users
- Inconsistent status display between OpenAPS rigs and AAPS
- User confusion about algorithm state

**Possible Solutions**:
1. Document required `received` field in devicestatus spec
2. Add fallback logic (assume enacted if rate/duration present)
3. Align AAPS upload to include field

**Status**: Documented

**Related**:
- [Plugin Deep Dive](../docs/10-domain/cgm-remote-monitor-plugin-deep-dive.md)
- GAP-API-006 (no OpenAPI spec)

---

## Sync/Upload Gaps

---

### GAP-SPEC-001: Remote Command eventTypes Missing from OpenAPI Spec

**Scenario**: Remote command processing

**Description**: The Nightscout server recognizes special remote command eventTypes that are not listed in the OpenAPI spec's eventType enum:
- `Temporary Override Cancel` - cancels active override
- `Remote Carbs Entry` - adds carbs remotely
- `Remote Bolus Entry` - requests bolus remotely

These are used exclusively for Loop remote commands via APNS but are undocumented in the API specification.

**Source**: `cgm-remote-monitor:lib/server/loop.js:65-106`

**Impact**:
- Clients cannot discover valid remote command eventTypes from spec
- No validation rules documented for remote command fields
- Missing required fields documentation (remoteCarbs, remoteBolus, etc.)

**Possible Solutions**:
1. Add remote command eventTypes to treatments spec with required field documentation
2. Create separate remote commands API specification
3. Document as extension to base treatments schema

**Status**: Under discussion

**Related**:
- GAP-REMOTE-001, GAP-REMOTE-002
- [Remote Commands Comparison](../docs/10-domain/remote-commands-comparison.md)

---

---

### GAP-SPEC-002: AAPS Treatment Fields Not in AID Spec

**Scenario**: AAPS treatment sync round-trip

**Description**: The AAPS SDK `RemoteTreatment` model includes many fields not documented in the AID treatments OpenAPI spec:

**Missing fields**:
| Field | Type | Purpose |
|-------|------|---------|
| `durationInMilliseconds` | Long | Alternative duration representation |
| `endId` | Long | ID of record that ended this treatment |
| `autoForced` | Boolean | RunningMode auto-forced flag |
| `mode` | String | RunningMode type |
| `reasons` | String | RunningMode reasons |
| `location` | String | Site management location |
| `arrow` | String | Site management arrow indicator |
| `isSMB` | Boolean | Explicit SMB identifier |
| `relative` | Double | Relative rate for extended bolus |
| `isEmulatingTempBasal` | Boolean | Extended bolus emulation flag |
| `extendedEmulated` | Object | Nested treatment for emulated extended bolus |
| `bolusCalculatorResult` | String | Full bolus wizard calculation JSON |
| `originalProfileName` | String | Effective Profile Switch original |
| `originalCustomizedName` | String | Effective Profile Switch customization |
| `originalTimeshift` | Long | Original profile timeshift |
| `originalPercentage` | Int | Original profile percentage |
| `originalDuration` | Long | Original duration before modification |
| `originalEnd` | Long | Original end timestamp |
| `enteredinsulin` | Double | Alternative insulin field for combo bolus |

**Source**: `AndroidAPS:core/nssdk/src/main/kotlin/.../RemoteTreatment.kt:41-87`

**Impact**:
- Spec consumers miss fields needed for AAPS compatibility
- Round-trip data loss for AAPS-originated treatments
- Incomplete validation rules

**Possible Solutions**:
1. Add all AAPS fields to aid-treatments-2025.yaml with x-aid-controllers annotations
2. Create AAPS-specific extension schema
3. Document as "implementation-specific" extensions

**Status**: Under discussion

**Related**:
- GAP-TREAT-003, GAP-TREAT-004
- [Treatments Deep Dive](../docs/10-domain/treatments-deep-dive.md)

---

---

### GAP-SPEC-003: Effective Profile Switch vs Profile Switch Distinction

**Scenario**: Profile tracking across systems

**Description**: AAPS uploads both `Profile Switch` and `Effective Profile Switch` eventTypes. The latter includes `original*` prefixed fields tracking what changed from the base profile. This distinction is not captured in the spec.

**Source**: `AndroidAPS:core/nssdk/src/main/kotlin/.../RemoteTreatment.kt:69-74`

**Evidence**:
```kotlin
@SerializedName("originalProfileName") val originalProfileName: String? = null,
@SerializedName("originalCustomizedName") val originalCustomizedName: String? = null,
@SerializedName("originalTimeshift") val originalTimeshift: Long? = null,
@SerializedName("originalPercentage") val originalPercentage: Int? = null,
@SerializedName("originalDuration") val originalDuration: Long? = null,
@SerializedName("originalEnd") val originalEnd: Long? = null,
```

**Impact**:
- Cannot distinguish calculated effective profile from user-initiated switch
- Profile history reconstruction incomplete
- Algorithm comparison missing profile context

**Possible Solutions**:
1. Add `Effective Profile Switch` to eventType enum
2. Document `original*` fields in Profile Switch schema
3. Create ProfileSwitchTreatment discriminated union

**Status**: Needs ADR

---

---

### GAP-SPEC-004: BolusCalculatorResult JSON Not Parsed

**Scenario**: Bolus wizard audit trail

**Description**: AAPS uploads `bolusCalculatorResult` as a JSON string containing detailed bolus calculation parameters. This is documented as a string field but the internal structure is not specified.

**Source**: `AndroidAPS:core/nssdk/src/main/kotlin/.../RemoteTreatment.kt:76`

**Sample structure**:
```json
{
  "basalIOB": -0.247,
  "bolusIOB": -1.837,
  "carbs": 45.0,
  "carbsInsulin": 9.0,
  "glucoseValue": 134.0,
  "glucoseInsulin": 0.897,
  "glucoseDifference": 44.0,
  "ic": 5.0,
  "isf": 49.0,
  "targetBGLow": 90.0,
  "targetBGHigh": 90.0,
  "totalInsulin": 7.34,
  "percentageCorrection": 90,
  "profileName": "Tuned 13/01 90%Lyum",
  ...
}
```

**Impact**:
- Bolus audit trail requires parsing embedded JSON
- No schema validation for calculator parameters
- Cannot query by calculator inputs

**Possible Solutions**:
1. Define BolusCalculatorResult as object schema in spec
2. Recommend storing as structured object instead of string
3. Document required fields for bolus wizard auditing

**Status**: Under discussion

---

---

### GAP-SPEC-005: FAKE_EXTENDED Temp Basal Type Undocumented

**Scenario**: Extended bolus handling

**Description**: AAPS uses `type: "FAKE_EXTENDED"` for extended boluses implemented as temp basals. This is not documented in the treatments spec.

**Source**: `AndroidAPS:core/nssdk/src/main/kotlin/.../RemoteTreatment.kt:77`
```kotlin
@SerializedName("type") val type: String? = null,  // "NORMAL", "SMB", "FAKE_EXTENDED"
```

**Impact**:
- Extended bolus treatments not identified correctly
- IOB calculation may double-count if both bolus and temp basal components exist
- Related to GAP-TREAT-004 (extended bolus representation)

**Possible Solutions**:
1. Add FAKE_EXTENDED to BolusType enum with documentation
2. Add isExtendedBolus boolean flag
3. Document relationship between extended bolus and temp basal treatments

**Status**: Under discussion

**Related**:
- GAP-TREAT-004

---

---

### GAP-SPEC-006: isValid Soft Delete Semantics Not Specified

**Scenario**: Treatment deletion sync

**Description**: API v3 uses `isValid: false` for soft-deleted documents, but the spec doesn't define:
- When isValid should be set to false
- Whether clients should filter by isValid
- Behavior when isValid is missing (null vs true)

**Source**: `AndroidAPS:core/nssdk/src/main/kotlin/.../RemoteTreatment.kt:30`
```kotlin
@SerializedName("isValid") val isValid: Boolean? = null,
```

**Impact**:
- Clients may display deleted treatments
- Sync logic varies by implementation
- Related to GAP-TREAT-006 (retroactive edit handling)

**Possible Solutions**:
1. Document isValid semantics in spec
2. Add isValid query filter documentation
3. Specify default value when field is missing

**Status**: Under discussion

**Related**:
- GAP-TREAT-006, GAP-API-001

---

---

### GAP-SPEC-007: Deduplication Key Fields Undocumented

**Scenario**: Batch upload deduplication

**Description**: The Nightscout API uses `created_at` + `eventType` as the deduplication key for treatments, but this is not explicitly documented in the OpenAPI spec. Additionally, the spec doesn't document:
- `identifier` field behavior for API v3
- `date` + `device` + `eventType` alternative key
- Priority when multiple identity fields are present

**Source**: `cgm-remote-monitor:lib/api3/swagger.yaml:1103`
```yaml
The server calculates the identifier in such a way that duplicate records are automatically merged 
(deduplicating is made by `date`, `device` and `eventType` fields).
```

**Impact**:
- Clients may not include required deduplication fields
- Duplicate detection varies between v1 and v3 APIs
- Related to GAP-003, GAP-BATCH-001

**Possible Solutions**:
1. Document deduplication algorithm per API version
2. Add x-deduplication-key extension to spec
3. Specify which fields form the composite key

**Status**: Under discussion

**Related**:
- GAP-003, GAP-BATCH-001, GAP-BATCH-002

---

## Resolved Gaps

_None yet._

---

## Template

```markdown

---

### GAP-STATS-001: No Aggregate Statistics Endpoints

**Description**: Nightscout API v3 provides CRUD operations for entries/treatments but no pre-computed statistical aggregations. Clients must fetch raw data and compute statistics locally.

**Affected Systems**: nightscout-reporter, cgm-remote-monitor reports, AI/LLM integrations

**Impact**:
- Heavy client-side computation for reports
- Excessive data transfer (thousands of entries for simple stats)
- No efficient path for AI/MCP integrations
- Redundant calculations across multiple clients

**Remediation**: Implement `/api/v3/stats/*` endpoints with MongoDB aggregation pipelines.

---

---

### GAP-STATS-002: Client-Side Report Computation

**Description**: Report plugins (dailystats, glucosedistribution, hourlystats) compute all statistics in browser JavaScript, causing slow report generation and high CPU usage.

**Affected Systems**: cgm-remote-monitor reports, nightscout-reporter

**Impact**:
- Slow report loading (seconds to minutes for long periods)
- Poor mobile performance
- Inconsistent calculations between clients
- No caching of computed results

**Remediation**: Move statistical calculations to server-side with caching layer.

---

---

### GAP-STATS-003: No MCP Integration for Statistics

**Description**: No Model Context Protocol (MCP) resources exist for glucose statistics, limiting AI assistant integration capabilities.

**Affected Systems**: AI assistants, LLM-based health tools

**Impact**:
- AI tools must fetch raw entries and compute statistics
- Inefficient token usage for simple health queries
- No standardized resource URIs for glucose data

**Remediation**: Expose Statistics API as MCP resources with standard URI patterns.

---

### GAP-UI-001: No Component Framework

**Scenario**: Frontend maintenance and extension.

**Description**: UI is built with vanilla JavaScript and jQuery. No modern component framework (React, Vue, etc.) makes maintenance difficult and prevents code reuse.

**Affected Systems**: All Nightscout frontend features.

**Impact**: High barrier to contribution, difficult testing, inconsistent patterns.

**Remediation**: Consider incremental migration to component-based architecture.

---

---

### GAP-UI-002: Chart Accessibility

**Scenario**: Screen reader and keyboard navigation.

**Description**: D3.js charts lack ARIA labels, keyboard navigation, and screen reader support. Glucose data is only accessible visually.

**Affected Systems**: Visually impaired users, accessibility compliance.

**Impact**: Nightscout not accessible to all users.

**Remediation**: Add ARIA labels, data tables as alternative, keyboard controls.

---

---

### GAP-UI-003: No Offline Support

**Scenario**: Intermittent connectivity.

**Description**: While service worker exists, meaningful offline support is limited. Data cannot be viewed when disconnected.

**Affected Systems**: Mobile users, poor connectivity areas.

**Impact**: Nightscout unusable without active connection.

**Remediation**: Implement IndexedDB caching, offline data display.

---

## nightscout-connect Gaps

---

### GAP-REMOTE-CMD: Remote Commands API Not Merged

**Status**: ✅ Addressed in specification

**Scenario**: Caregiver remote bolus/carb commands

**Description**: PR#7791 adds remote command queue for Loop caregiver features, but has been stalled since 2022. Prevents caregivers from sending remote bolus, carb entries, and overrides.

**Affected Systems**: Loop, Trio, caregivers

**Impact**:
- Caregivers cannot remotely manage children's diabetes
- Loop remote features incomplete without Nightscout integration
- 3+ years of waiting for critical caregiver functionality

**Remediation**: ✅ OpenAPI spec created: `specs/openapi/aid-commands-2025.yaml` (738 lines)

**Specification Coverage**:
- 7 endpoints: CRUD + list + delete all
- 4 action types: bolus, carbs, override, cancelOverride
- State machine: Pending → In-Progress → Complete/Error
- OTP security model documented
- Push notification flow documented
- 5 conformance scenarios

---

## Authentication Gaps

---

### GAP-AUTH-006: JWT Secret Storage Location

**Scenario**: JWT invalidation after npm update

**Description**: JWT secret is stored in `node_modules/.cache/.jwt-secret`, which can be deleted during npm install/update operations.

**Affected Systems**: All clients using JWT authentication

**Impact**:
- All JWTs become invalid after npm operations
- Users must re-authenticate
- No warning before invalidation

**Remediation**: Store JWT secret in environment variable or persistent config file outside node_modules.

**Source**: `crm:lib/server/enclave.js`

---

### GAP-AUTH-007: No Account Lockout

**Scenario**: Brute force attack on API

**Description**: Rate limiting only delays requests (5s per failure), never blocks them. No maximum attempt limit or account lockout.

**Affected Systems**: Nightscout server security

**Impact**:
- Brute force attacks possible with patience
- No alerting on repeated failures
- No automatic blocking

**Remediation**: Implement lockout after N failed attempts with admin unlock capability.

**Source**: `crm:lib/authorization/delaylist.js`

---

## API v3 Architecture Gaps

---

### GAP-API3-001: No Batch Operations

**Scenario**: Bulk data synchronization

**Description**: API v3 lacks batch create/update/delete operations. Each document requires an individual HTTP request.

**Affected Systems**: All clients performing bulk sync (historical import, large uploads)

**Impact**:
- Performance bottleneck for bulk uploads
- High HTTP overhead for large datasets
- Sync timeouts for historical data

**Remediation**: Add `POST /{collection}/batch` endpoint accepting array of documents.

**Source**: `lib/api3/generic/` (no batch operation exists)

---

### GAP-API3-002: No Cursor-Based Pagination

**Scenario**: Large dataset traversal

**Description**: API v3 uses offset pagination (`skip`) which is inefficient for large datasets. Skip values over ~10000 cause performance issues.

**Affected Systems**: Clients querying large collections

**Impact**:
- Performance degrades with high skip values
- Risk of missing documents during pagination
- MongoDB performance issues

**Remediation**: Add `cursor` parameter using `srvModified` + `identifier` for stable pagination.

**Source**: `lib/api3/generic/search/input.js:119-133`

---

### GAP-API3-003: Limited Field Projection Syntax

**Scenario**: Bandwidth optimization

**Description**: The `fields` parameter only supports comma-separated field inclusion. Cannot exclude specific large fields.

**Affected Systems**: Mobile clients, bandwidth-constrained connections

**Impact**:
- Cannot exclude just one large field (must list all others)
- Verbose requests for simple exclusions
- No nested field projection

**Remediation**: Support `fields=-largeField` exclusion syntax or MongoDB-style projection.

**Source**: `lib/api3/shared/fieldsProjector.js`

---

## DeviceStatus Structure Gaps

---

### GAP-DS-001: No Effect Timelines in Loop

**Description**: Loop computes individual effect timelines (insulin, carbs, momentum, retrospective correction) internally but does NOT upload them to devicestatus.

**Affected Systems**: Loop, cross-system analytics

**Impact**:
- Cannot debug Loop algorithm decisions
- Cannot compare Loop effects to oref0's detailed output
- Limited retrospective analysis

**Remediation**: Add optional effect timeline upload to Loop devicestatus.

**Source**: `docs/10-domain/devicestatus-deep-dive.md`

---

### GAP-DS-002: Prediction Array Incompatibility

**Description**: Loop uploads single combined prediction array; oref0 systems provide four separate curves (IOB, COB, UAM, ZT).

**Affected Systems**: Loop, Trio, AAPS, analytics tools

**Impact**:
- Cannot directly compare predictions between systems
- Different semantics for prediction interpretation
- Analytics must handle both formats

**Remediation**: Document clearly which prediction to use for comparison purposes.

**Source**: `docs/10-domain/devicestatus-deep-dive.md`

---

### GAP-DS-003: Duration Unit Inconsistency

**Description**: Loop uses seconds for duration; oref0 systems use minutes.

**Affected Systems**: Loop, Trio, AAPS, OpenAPS

**Impact**:
- Analytics code must convert between units
- Risk of off-by-60x errors
- Cross-system comparison requires normalization

**Remediation**: Document conversion requirements; consider standardizing in future specs.

**Source**: `docs/10-domain/devicestatus-deep-dive.md`

---

### GAP-DS-004: Missing Algorithm Transparency in Loop

**Description**: oref0 exposes extensive algorithm state (eventualBG, sensitivityRatio, ISF, CR, deviation, reason). Loop uploads minimal algorithm context.

**Affected Systems**: Loop, analytics tools

**Impact**:
- Cannot understand Loop algorithm decisions
- Limited debugging capability
- Cannot compute similar metrics retrospectively

**Remediation**: Consider adding optional algorithm context fields to Loop devicestatus.

**Source**: `docs/10-domain/devicestatus-deep-dive.md`

---

### GAP-PROFILE-001: Unit Representation Mismatch

**Description**: Loop uses HealthKit units (`HKQuantity`) with type safety; Nightscout uses string representations ("mg/dl", "mmol"). Unit precision may be lost during conversion.

**Affected Systems**: Loop, Nightscout

**Impact**:
- Potential precision loss during unit conversion
- HealthKit's type-safe units become loosely typed strings
- May affect edge cases in ISF/CR calculations

**Remediation**: Document acceptable precision loss; consider adding unit metadata to Nightscout profile schema.

**Source**: `docs/60-research/profile-therapy-settings-comparison.md`

---

### GAP-PROFILE-002: Time Block vs Start-Time Format

**Description**: AAPS uses duration-based blocks (`Block` with duration in ms); Nightscout uses start-time arrays (`time` + `timeAsSeconds`). Requires bidirectional conversion logic.

**Affected Systems**: AAPS, Nightscout

**Impact**:
- Conversion logic required in AAPS NSClient
- Edge cases possible around midnight wraparound
- Duration-based format more explicit about schedule coverage

**Remediation**: Document conversion algorithms; consider supporting both formats in future spec.

**Source**: `docs/60-research/profile-therapy-settings-comparison.md`

---

### GAP-PROFILE-003: Loop Has No Profile Naming

**Description**: Loop treats therapy settings as a single unnamed entity. Cannot reference profiles by name in cross-system scenarios where AAPS/Trio support multiple named profiles.

**Affected Systems**: Loop, AAPS, Trio

**Impact**:
- Cannot correlate Loop settings to named Nightscout profiles
- Profile switch events don't translate to Loop
- Multi-profile workflows (work vs home) not expressible in Loop

**Remediation**: Loop could adopt optional profile naming for Nightscout compatibility.

**Source**: `docs/60-research/profile-therapy-settings-comparison.md`

---

### GAP-PROFILE-004: Loop Download-Only

**Description**: Loop uploads profiles to Nightscout but does not download them. Settings cannot be remotely updated via Nightscout.

**Affected Systems**: Loop, Nightscout

**Impact**:
- Loop is source-of-truth for its own settings
- Remote configuration (caregiver scenario) not possible
- Differs from Trio which downloads profiles from Nightscout

**Remediation**: Consider adding optional profile download for caregiver mode.

**Source**: `docs/60-research/profile-therapy-settings-comparison.md`

### GAP-REPORT-001: No Server-Side Statistics API

**Description**: Both cgm-remote-monitor and nightscout-reporter compute statistics client-side, duplicating logic and preventing standardization.

**Affected Systems**: cgm-remote-monitor, nightscout-reporter, all report consumers

**Impact**:
- Inconsistent calculations between clients
- High client-side computation load
- No standard statistics endpoint

**Remediation**: Implement statistics-api-proposal.md server-side endpoints.

**Source**: `docs/10-domain/reporting-needs-analysis.md`

---

### GAP-REPORT-002: No PDF Export in cgm-remote-monitor

**Description**: Built-in reports render HTML only. Users wanting PDF must use nightscout-reporter or browser print-to-PDF.

**Affected Systems**: cgm-remote-monitor

**Impact**:
- Suboptimal for clinical sharing
- Requires separate tool for print

**Remediation**: Add PDF export capability or integrate with nightscout-reporter.

**Source**: `docs/10-domain/reporting-needs-analysis.md`

---

### GAP-REPORT-003: Loop Analysis Fragmented

**Description**: Loop/OpenAPS analysis exists in loopalyzer.js for cgm-remote-monitor, but nightscout-reporter uses uploader detection heuristics instead of dedicated analysis.

**Affected Systems**: cgm-remote-monitor, nightscout-reporter

**Impact**:
- Inconsistent loop analysis across tools
- Different metrics computed

**Remediation**: Standardize loop analysis metrics.

**Source**: `docs/10-domain/reporting-needs-analysis.md`

---

### GAP-RG-001: No Standard Nightscout Integration for Roles Gateway

**Description**: The nightscout-roles-gateway provides enterprise RBAC functionality but requires separate deployment and does not integrate into the core Nightscout installation.

**Affected Systems**: nightscout-roles-gateway, cgm-remote-monitor

**Impact**:
- Enterprise deployments require separate infrastructure
- No turnkey multi-user support in core Nightscout
- School/clinic use cases need custom setup

**Remediation**: Consider integration pathway or plugin architecture for roles-gateway.

**Source**: `mapping/nightscout-roles-gateway/authorization.md`

---

### GAP-API-010: Loop Missing API v3 Pagination

**Description:** Loop uses API v1 with no incremental sync. Re-fetches all data on each sync.

**Source:** `externals/LoopWorkspace/NightscoutService/`

**Impact:** Higher server load, slower sync, battery drain from redundant data transfer.

**Remediation:** Migrate NightscoutServiceKit to use API v3 `/history` endpoints with `srvModified` tracking.

### GAP-API-011: Trio Missing API v3 Pagination

**Description:** Trio uses API v1 with count-based fetching. Uses date filtering but not server-side modification tracking.

**Source:** `externals/Trio/Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift:14-18`

**Impact:** Same as Loop - no incremental sync capability.

**Remediation:** Add `srvModified` tracking and migrate to `/api/v3/{collection}/history` endpoints.

### GAP-API-012: xDrip+ Partial Pagination Compliance

**Description:** xDrip+ correctly uses `Last-Modified` header but with API v1 endpoints. Misses v3 per-document `srvModified` precision.

**Source:** `externals/xDrip/app/.../NightscoutUploader.java:410-437`

**Impact:** Moderate efficiency but misses per-document sync precision.

**Remediation:** Add API v3 support as alternative, track `srvModified` per document.

---

## WebSocket Gaps

### GAP-API-013: Legacy WebSocket Not Used by Controllers

**Description:** All major controllers (Loop, AAPS, Trio) use REST APIs for upload. The legacy WebSocket `dbAdd`/`dbUpdate` events are primarily used by the web interface.

**Source:** 
- Loop: `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/NightscoutService.swift` (REST only)
- AAPS: `externals/AndroidAPS/core/nssdk/src/main/kotlin/app/aaps/core/nssdk/NSAndroidClientImpl.kt` (REST only)
- Trio: `externals/Trio/Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift` (REST only)

**Impact:** Real-time sync benefits underutilized; controllers poll REST endpoints.

**Remediation:** Document WebSocket as optional performance optimization.

### GAP-API-014: APIv3 WebSocket Doesn't Capture V1 Changes

**Description:** The APIv3 `/storage` channel only broadcasts changes made via APIv3 REST endpoints. Changes via APIv1 or WebSocket v1 are not included.

**Source:** `externals/cgm-remote-monitor/lib/api3/doc/socket.md` - "Only changes made via APIv3 are being broadcasted"

**Impact:** Clients subscribed to APIv3 storage miss updates from Loop (uses v1 API).

**Remediation:** Consolidate event bus to broadcast all changes regardless of entry point.

### GAP-API-015: No Alarm/Notification WebSocket Channel

**Description:** Alarm state changes (urgent high, stale data, etc.) are not exposed via WebSocket events.

**Source:** `externals/cgm-remote-monitor/lib/server/websocket.js` - no alarm event handling

**Impact:** Follower apps must poll for alarm state.

**Remediation:** Add `alarm` event to storage channel.

---

## DeviceStatus Schema Gaps

### GAP-DS-005: Incompatible Prediction Formats

**Description:** Loop uses single `predicted.values` array while oref0 uses four separate `predBGs.*` curves (IOB, COB, UAM, ZT). Nightscout must implement dual parsers.

**Source:** 
- `externals/cgm-remote-monitor/lib/report_plugins/daytoday.js:347-357`
- `externals/LoopWorkspace/.../StoredDosingDecision.swift:155`

**Impact:** Reports must conditionally parse either format; no unified prediction visualization API.

**Remediation:** Define unified prediction schema with optional curve decomposition.

### GAP-DS-006: Missing Basal/Bolus IOB Split in Loop

**Description:** Loop reports only total IOB, while oref0 provides `basaliob` and `bolusiob` components.

**Source:** `externals/AndroidAPS/.../NSDeviceStatus.kt:57`

**Impact:** Nightscout displays can't show IOB breakdown for Loop users.

**Remediation:** Loop could add optional `basaliob`/`bolusiob` fields.

### GAP-DS-007: No Override Status in oref0

**Description:** Loop has `status.override` for temporary target overrides, but oref0 uses different mechanism (profile switches).

**Source:** `externals/LoopWorkspace/.../StoredDosingDecision.swift:160`

**Impact:** Override visualization only works for Loop users.

**Remediation:** AAPS could add equivalent override reporting to devicestatus.

### GAP-DS-008: Missing eventualBG in Loop

**Description:** oref0 explicitly reports `eventualBG` prediction endpoint, Loop does not include this field.

**Source:** `externals/cgm-remote-monitor/lib/plugins/openaps.js`

**Impact:** Loop users don't see eventual BG prediction in Nightscout displays.

**Remediation:** Loop could add `eventualBG` field to match oref0 format.

---

## V2 DData Endpoint Gaps

---

### GAP-API-016: Nocturne Missing lastProfileFromSwitch in DData

**Scenario:** Profile switch synchronization via DData endpoint

**Description:** The `/api/v2/ddata` endpoint in Nocturne does not populate the `lastProfileFromSwitch` field, which cgm-remote-monitor computes from the most recent Profile Switch treatment.

**Evidence:**
- cgm-remote-monitor: `lib/data/dataloader.js:364-374` - Computes lastProfileFromSwitch
- Nocturne: `Core/Models/DData.cs` - Field not present in model

**Affected Systems:** Loop, Nightguard, any client using lastProfileFromSwitch for active profile determination

**Impact:** Low - Clients can compute from `profileTreatments` list in same response

**Remediation:** 
1. Add `LastProfileFromSwitch` property to Nocturne `DData.cs`
2. In `DDataService.GetDData()`, find latest Profile Switch treatment before request time
3. Extract and assign the `profile` field

**Status:** Open - Low Priority

**Related:**
- [Nocturne DData Analysis](../docs/10-domain/nocturne-ddata-analysis.md)
- GAP-SYNC-040 (deletion semantics)
