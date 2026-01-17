# Nightscout API v1 vs v3 Comparison

**Last Updated:** 2026-01-17  
**Authoritative Sources:**
- v1: `externals/cgm-remote-monitor/lib/api/` (entries, treatments, devicestatus, profile)
- v3: `externals/cgm-remote-monitor/lib/api3/` (generic operations, security, history)
- v3 OpenAPI: `externals/cgm-remote-monitor/lib/api3/swagger.yaml`
- AAPS v3 SDK: `externals/AndroidAPS/core/nssdk/`

---

## 1. Executive Summary

Nightscout maintains two parallel API versions:

| Aspect | API v1 | API v3 |
|--------|--------|--------|
| **Base Path** | `/api/v1/` | `/api/v3/` |
| **Primary Client** | Loop, Trio, xDrip+, OpenAPS | AAPS (exclusive) |
| **Authentication** | SHA1-hashed API_SECRET | Bearer token (opaque access token) |
| **Document ID** | `_id` (MongoDB ObjectId) | `identifier` (server-assigned) |
| **Sync Method** | Poll with date filters | Incremental history endpoint |
| **Deletion** | Hard delete | Soft delete (`isValid=false`) |
| **Specification** | Implicit (code-defined) | OpenAPI 3.0 |

**Key Finding:** AAPS is the *only* major AID controller using API v3. All iOS systems (Loop, Trio) and xDrip+ continue to use v1, creating a bifurcated ecosystem where sync behaviors differ significantly.

---

## 2. Endpoint Structure Comparison

### 2.1 Base Paths

```
v1: https://yoursite.herokuapp.com/api/v1/{collection}.json
v3: https://yoursite.herokuapp.com/api/v3/{collection}
```

### 2.2 Endpoint Mapping

| Operation | API v1 | API v3 |
|-----------|--------|--------|
| **List/Search** | `GET /api/v1/entries.json?count=10` | `GET /api/v3/entries?limit=10` |
| **Create** | `POST /api/v1/entries.json` | `POST /api/v3/entries` |
| **Read One** | `GET /api/v1/entries/{_id}` | `GET /api/v3/entries/{identifier}` |
| **Update** | `PUT /api/v1/treatments/{_id}` | `PUT /api/v3/treatments/{identifier}` |
| **Patch** | N/A (full replace only) | `PATCH /api/v3/treatments/{identifier}` |
| **Delete** | `DELETE /api/v1/treatments/{_id}` | `DELETE /api/v3/treatments/{identifier}` |
| **History** | N/A | `GET /api/v3/{collection}/history/{timestamp}` |
| **Last Modified** | N/A | `GET /api/v3/lastModified` |

### 2.3 Query Parameter Syntax

**API v1** uses MongoDB-style query syntax:
```
GET /api/v1/entries.json?find[type]=sgv&find[date][$gte]=1705000000000&count=100
GET /api/v1/treatments.json?find[eventType]=Correction+Bolus&find[created_at][$gt]=2026-01-15T00:00:00Z
```

**API v3** uses flat parameter syntax:
```
GET /api/v3/entries?type$eq=sgv&date$gte=1705000000000&limit=100
GET /api/v3/treatments?eventType$eq=Correction%20Bolus&date$gte=1705000000000&limit=100
```

**Source:** `lib/api/entries/index.js` (v1), `lib/api3/generic/search/input.js` (v3)

---

## 3. Authentication Mechanisms

### 3.1 API v1: SHA1 Secret

**Method:** SHA1 hash of `API_SECRET` environment variable

**Implementation:**
```javascript
// Client-side (Trio example)
request.addValue(secret.sha1(), forHTTPHeaderField: "api-secret")
```

**Transmission options:**
1. Header: `api-secret: <sha1-hash>`
2. Query: `?token=<sha1-hash>` (legacy)
3. Query: `?secret=<sha1-hash>` (legacy)

**Permissions:** All-or-nothing. Valid secret grants full `*` permissions.

**Source:** `lib/api/verifyauth.js`, `externals/Trio/Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift`

### 3.2 API v3: Bearer Access Tokens

**Method:** Opaque access tokens created in Nightscout admin panel, transmitted via Bearer header

**Implementation:**
```kotlin
// AAPS SDK
@Headers("Authorization: Bearer $token")
suspend fun getSgvs(): Response<NSResponse<List<RemoteEntry>>>
```

**Server-side token resolution:**
```javascript
// lib/api3/security.js
ctx.authorization.resolve({ token, ip: getRemoteIP(req) }, function resolveFinish (err, result) {
  // result contains shiros array with permissions
});
```

**Transmission:**
- Header: `Authorization: Bearer <access-token>`

**Permissions:** Apache Shiro-style granular permissions:
```
api:*:read          // Read all collections
api:treatments:create,update  // Create and update treatments only
api:entries:read    // Read entries only
```

**Token Creation:** Access tokens are created in the Nightscout admin panel (`/admin/`) and associated with roles. They are opaque strings, not JWTs - the server resolves them to permissions via the authorization subsystem.

**Source:** `lib/api3/security.js`, Nightscout admin panel

### 3.3 Authentication Comparison

| Aspect | v1 | v3 |
|--------|----|----|
| **Token Type** | SHA1 hash | Opaque access token |
| **Granularity** | All or nothing | Per-collection, per-operation |
| **Token Expiry** | Never | Depends on role configuration |
| **Transmission** | Header or query | Header only (best practice) |
| **Subject Tracking** | No | Yes (`subject` field on documents) |
| **Permission Format** | N/A | Apache Shiro (`api:collection:operation`) |

**Gap Identified:** v1 clients cannot use granular permissions. A "readable" site allows unauthenticated reads, but writes require full API_SECRET.

---

## 4. Document Identity: `_id` vs `identifier`

### 4.1 API v1: MongoDB `_id`

- **Format:** 24-character hex string (MongoDB ObjectId)
- **Assignment:** Server-assigned on insert
- **Immutability:** Permanent after creation
- **Usage:** Used for GET/PUT/DELETE operations

**Example:**
```json
{
  "_id": "65a5c1234567890abcdef12",
  "sgv": 120,
  "date": 1705000000000,
  "type": "sgv"
}
```

### 4.2 API v3: `identifier`

- **Format:** String (typically UUID-like or hash-based)
- **Assignment:** Server-assigned on insert
- **Immutability:** Yes, except during v1→v3 deduplication migration
- **Usage:** Primary addressing key for all operations

**Example:**
```json
{
  "identifier": "abc123def456",
  "_id": "65a5c1234567890abcdef12",
  "sgv": 120,
  "date": 1705000000000,
  "type": "sgv"
}
```

### 4.3 The Deduplication Migration Exception

When a document created via v1 is deduplicated by v3:
1. The `identifier` may be assigned or changed
2. Original `_id` is preserved
3. Response indicates `isDeduplication: true`

**Source:** `lib/api3/generic/create/validate.js`

```javascript
// From v3 create/validate.js - identifier mutation allowed for v1 docs
// "Exception: identifier changes allowed during deduplication for API v1 documents"
```

**AAPS Tracking:**
```kotlin
// AAPS creates documents and stores returned identifier
return CreateUpdateResponse(
    response = response.code(),
    identifier = responseBody?.identifier,
    isDeduplication = responseBody?.isDeduplication == true,
    ...
)
```

---

## 5. Sync Patterns

### 5.1 API v1: Polling with Date Filters

**Pattern:** Clients poll periodically with timestamp filters

```swift
// Trio - fetch entries since date
let dateItem = URLQueryItem(
    name: "find[dateString][$gte]",
    value: Formatter.iso8601withFractionalSeconds.string(from: date)
)
```

**Limitations:**
- No way to detect deletions
- No way to detect updates to existing documents
- Must re-fetch all documents in time range
- Inefficient for large datasets

### 5.2 API v3: Incremental History Endpoint

**Pattern:** Request all changes since `srvModified` timestamp

```kotlin
// AAPS SDK
@GET("v3/entries/history/{from}")
suspend fun getSgvsModifiedSince(@Path("from") from: Long, @Query("limit") limit: Int): Response<NSResponse<List<RemoteEntry>>>
```

**Server Implementation:**
```javascript
// lib/api3/generic/history/operation.js
return [
  { field: 'srvModified', operator: operator, value: lastModified.getTime() }
];
```

**Features:**
- Returns insertions, updates, AND deletions
- Deleted documents have `isValid: false`
- Response includes `Last-Modified` header for next sync
- ETag support for efficient caching

**Response Example:**
```json
[
  {"identifier": "abc", "sgv": 120, "srvModified": 1705000100000, "isValid": true},
  {"identifier": "def", "sgv": 115, "srvModified": 1705000200000, "isValid": true},
  {"identifier": "ghi", "srvModified": 1705000300000, "isValid": false}  // deleted
]
```

### 5.3 Sync Pattern Comparison

| Aspect | v1 Polling | v3 History |
|--------|------------|------------|
| **Detects Insertions** | Yes | Yes |
| **Detects Updates** | Partial (if timestamp changes) | Yes |
| **Detects Deletions** | No | Yes (`isValid: false`) |
| **Bandwidth** | Higher (full documents) | Lower (delta only) |
| **Precision** | Second-level | Millisecond-level |
| **Stale Data Risk** | High | Low |

---

## 6. Soft Delete vs Hard Delete

### 6.1 API v1: Hard Delete

```
DELETE /api/v1/treatments/65a5c1234567890abcdef12
```

- Document is permanently removed from database
- Other clients have no way to know it was deleted
- Can cause "zombie" data in clients that cached the document

### 6.2 API v3: Soft Delete

```
DELETE /api/v3/treatments/abc123def456
```

- Document remains in database with `isValid: false`
- Appears in history responses so clients can sync deletion
- Optional `permanent=true` query param for hard delete

```json
// Soft-deleted document in history response
{
  "identifier": "abc123def456",
  "isValid": false,
  "srvModified": 1705000500000
}
```

**Source:** `lib/api3/generic/delete/operation.js`

---

## 7. Client Usage Matrix

### 7.1 Primary Clients by API Version

| Client | API Version | Platform | Notes |
|--------|-------------|----------|-------|
| **AAPS** | v3 | Android | Full v3 implementation via nssdk |
| **Loop** | v1 | iOS | REST only, no WebSocket |
| **Trio** | v1 | iOS | REST, SHA1 auth |
| **xDrip+** | v1 | Android | REST, batch uploads |
| **xDrip4iOS** | v1 | iOS | REST, SHA1 auth |
| **OpenAPS** | v1 | Linux/Pi | Bash scripts |
| **Nightguard** | v1 | iOS | Read-only |
| **Nightscout Reporter** | v1 | Web | Read-only |

### 7.2 AAPS v3 SDK Usage

**Source:** `externals/AndroidAPS/core/nssdk/`

AAPS uses a dedicated Kotlin SDK (`nssdk`) for Nightscout communication:

```kotlin
// Key operations in NSAndroidClientImpl.kt
suspend fun getSgvsModifiedSince(from: Long, limit: Int)  // History sync
suspend fun createSgv(nsSgvV3: NSSgvV3): CreateUpdateResponse
suspend fun updateEntry(nsSgvV3: NSSgvV3): CreateUpdateResponse
suspend fun deleteEntry(nsSgvV3: NSSgvV3)

// Treatments
suspend fun getTreatmentsModifiedSince(from: Long, limit: Int)
suspend fun createTreatment(nsTreatment: NSTreatment): CreateUpdateResponse
suspend fun updateTreatment(nsTreatment: NSTreatment): CreateUpdateResponse
suspend fun deleteTreatment(nsTreatment: NSTreatment)

// DeviceStatus
suspend fun getDeviceStatusModifiedSince(from: Long)
suspend fun createDeviceStatus(nsDeviceStatus: NSDeviceStatus): CreateUpdateResponse
```

### 7.3 Trio v1 Usage

**Source:** `externals/Trio/Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift`

```swift
private enum Config {
    static let entriesPath = "/api/v1/entries/sgv.json"
    static let uploadEntriesPath = "/api/v1/entries.json"
    static let treatmentsPath = "/api/v1/treatments.json"
    static let statusPath = "/api/v1/devicestatus.json"
    static let profilePath = "/api/v1/profile.json"
}
```

---

## 8. Response Format Differences

### 8.1 Create Response

**API v1:**
```json
[
  {
    "_id": "65a5c1234567890abcdef12",
    "sgv": 120,
    "date": 1705000000000,
    "type": "sgv"
  }
]
```
- Always returns array (even for single document)
- No deduplication indicator

**API v3:**
```json
{
  "status": 201,
  "identifier": "abc123def456",
  "isDeduplication": false,
  "lastModified": 1705000100000
}
```
- Returns object with metadata
- `isDeduplication` indicates if document already existed
- `lastModified` for sync tracking

### 8.2 Search Response

**API v1:**
```json
[
  {"_id": "abc", "sgv": 120, ...},
  {"_id": "def", "sgv": 115, ...}
]
```

**API v3:**
```json
{
  "status": 200,
  "result": [
    {"identifier": "abc", "sgv": 120, ...},
    {"identifier": "def", "sgv": 115, ...}
  ]
}
```

---

## 9. Server-Side Timestamps

### 9.1 API v1 Timestamps

| Field | Type | Description |
|-------|------|-------------|
| `date` | Integer (ms) | Event timestamp |
| `created_at` | ISO 8601 string | Document creation time |
| `dateString` | ISO 8601 string | Human-readable date |

### 9.2 API v3 Additional Timestamps

| Field | Type | Mutable | Description |
|-------|------|---------|-------------|
| `srvCreated` | Integer (ms) | No | Server creation time |
| `srvModified` | Integer (ms) | No (server-set) | Last modification time |
| `subject` | String | No | Creating user/token |
| `modifiedBy` | String | No (server-set) | Last modifier |

**Key Insight:** `srvModified` enables the history endpoint to return precise deltas.

---

## 10. Migration Path

### 10.1 v1 → v3 Document Migration

When a v1 document is accessed via v3:
1. Server assigns `identifier` if not present
2. `srvCreated` and `srvModified` populated from `created_at` or `date`
3. `isValid` defaults to `true`

### 10.2 Hybrid Usage

The same Nightscout instance supports both APIs simultaneously:
- v1 and v3 access the same database
- Documents created by v1 clients are visible to v3 clients (and vice versa)
- Soft-deleted documents (v3) are invisible to v1 `find` queries but remain in database

### 10.3 Client Migration Recommendations

| From | To | Effort | Benefit |
|------|-----|--------|---------|
| v1 polling | v3 history | Medium | Deletion detection, lower bandwidth |
| SHA1 auth | JWT tokens | Low | Granular permissions, audit trail |
| Hard delete | Soft delete | Low | Cross-client sync consistency |

---

## 11. Identified Gaps

### GAP-API-001: v1 Cannot Detect Deletions
**Severity:** Medium  
**Description:** API v1 clients (Loop, Trio, xDrip+) cannot detect when documents are deleted by other clients or by API v3 soft-delete.  
**Impact:** Stale data may persist in client caches indefinitely.  
**Mitigation:** v1 clients would need to implement periodic full-sync to detect missing documents.

### GAP-API-002: Identifier vs _id Addressing Inconsistency
**Severity:** Low  
**Description:** API v1 uses `_id`, API v3 uses `identifier`. Documents may have both fields with different values.  
**Impact:** Cross-API client confusion when tracking document identity.  
**Mitigation:** Use `_id` as canonical identity for v1 clients, `identifier` for v3 clients.

### GAP-API-003: No v3 Adoption Path for iOS Clients
**Severity:** Medium  
**Description:** Loop and Trio continue to use v1 with no apparent migration plans. AAPS is the only v3 client.  
**Impact:** Ecosystem fragmentation; iOS clients lack efficient sync capabilities.  
**Mitigation:** Document v3 benefits to encourage iOS client adoption.

### GAP-API-004: Authentication Granularity Gap
**Severity:** Low  
**Description:** v1 authentication is all-or-nothing; cannot grant read-only access to specific collections.  
**Impact:** Follower apps receive full write access or are limited to public-readable sites.  
**Mitigation:** Use v3 JWT tokens for fine-grained access control.

### GAP-API-005: Deduplication Behavior Differences
**Severity:** Low  
**Description:** v3 returns `isDeduplication: true` when a document matches existing data; v1 silently accepts duplicates.  
**Impact:** v1 clients may create duplicate documents that v3 clients later see as deduplicated.  
**Mitigation:** Use client-side deduplication or unique `identifier` generation.

---

## 12. Cross-References

- **v1 Compatibility Spec:** `externals/cgm-remote-monitor/docs/requirements/api-v1-compatibility-spec.md`
- **v3 OpenAPI Spec:** `externals/cgm-remote-monitor/lib/api3/swagger.yaml`
- **v3 API Summary:** `specs/openapi/nightscout-api3-summary.md`
- **AAPS Sync Mapping:** `mapping/aaps/nightscout-sync.md`
- **Trio Sync Mapping:** `mapping/trio/nightscout-sync.md`
- **Loop Sync Mapping:** `mapping/loop/nightscout-sync.md`
- **Terminology Matrix:** `mapping/cross-project/terminology-matrix.md`
