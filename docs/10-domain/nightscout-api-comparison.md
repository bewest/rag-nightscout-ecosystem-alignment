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

| Aspect | API v1 | API v3 REST | v3 alarmSocket | v3 storageSocket |
|--------|--------|-------------|----------------|------------------|
| **Base Path** | `/api/v1/` | `/api/v3/` | `/alarm` namespace | `/storage` namespace |
| **Primary Client** | Loop, Trio, xDrip+, OpenAPS | AAPS (exclusive) | Web clients | AAPS, web clients |
| **API_SECRET Auth** | ✅ Yes | ❌ Entry-point blocks | ✅ Yes | ❌ No |
| **JWT Token Auth** | ✅ Yes | ✅ Required (Bearer) | ✅ Yes | ❌ No |
| **Access Token Auth** | ✅ Yes | ❌ No (Bearer JWT only) | ✅ Yes | ✅ Yes (only method) |
| **Document ID** | `_id` (MongoDB ObjectId) | `identifier` (server-assigned) | N/A | N/A |
| **Sync Method** | Poll with date filters | Incremental history | Push (alarms) | Push (storage changes) |
| **Deletion** | Hard delete | Soft delete (`isValid=false`) | N/A | N/A |

**Key Findings (Updated 2026-01-17):**
1. AAPS is the *only* major AID controller using API v3. All iOS systems (Loop, Trio) and xDrip+ continue to use v1.
2. **Both API v1 and v3 use a shared authorization module** (`lib/authorization/index.js`) that handles both API_SECRET and token authentication uniformly.
3. The v3 REST "token-only" behavior is an **entry-point restriction** in `lib/api3/security.js`, not an architectural limitation.
4. v3 WebSocket endpoints differ: **alarmSocket** accepts API_SECRET, JWT, and access tokens; **storageSocket** only accepts access tokens (calls `resolveAccessToken` directly).

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

### 3.1 Shared Authorization Infrastructure

**Key Finding (Verified 2026-01-17):** Both API v1 and v3 use a **shared authorization module** (`lib/authorization/index.js`) that can handle both API_SECRET and token-based authentication uniformly. The apparent differences in authentication between v1 and v3 stem from how each API's entry-point security layer calls this shared module, not from fundamental architectural differences.

**Shared Authorization Module (`lib/authorization/index.js`):**

The core `authorization.resolve()` function (lines 144-220) accepts both mechanisms:

```javascript
authorization.resolve = async function resolve (data, callback) {
  // data = { api_secret, token, ip }
  
  // 1. Check for API_SECRET first (grants full * permissions)
  if (data.api_secret && authorizeAdminSecret(data.api_secret)) {
    var admin = shiroTrie.new();
    admin.add(['*']);
    return { shiros: [admin] };
  }
  
  // 2. Then check for JWT/token
  try {
    const verified = env.enclave.verifyJWT(data.token);
    token = verified.accessToken;
  } catch (err) {}
  
  // 3. Also check if api_secret field contains a valid access token
  if (!token && data.api_secret) {
    if (storage.doesAccessTokenExist(data.api_secret)) {
      token = data.api_secret;
    }
  }
  
  // ... resolve token to permissions via shiros
};
```

**Source:** `lib/authorization/index.js` lines 144-220

### 3.2 API v1: Dual Authentication Support

**Method:** API v1 accepts BOTH SHA1-hashed API_SECRET AND opaque access tokens

**API_SECRET Authentication:**
```javascript
// Client-side (Trio example)
request.addValue(secret.sha1(), forHTTPHeaderField: "api-secret")
```

**Transmission options for API_SECRET:**
1. Header: `api-secret: <sha1-hash>`
2. Query: `?secret=<sha1-hash>` (legacy)

**Token Authentication:**
- Query: `?token=<access-token>`
- Body: `{ "token": "<access-token>" }`

**Permissions:** 
- API_SECRET grants full `*` permissions (all-or-nothing)
- Access tokens grant role-based Shiro permissions

**Server-side Resolution (`lib/authorization/index.js` lines 112-119):**
```javascript
authorization.resolveWithRequest = function resolveWithRequest (req, callback) {
  const resolveData = {
    api_secret: apiSecretFromRequest(req),  // Extracts from header/query/body
    token: extractJWTfromRequest(req),       // Extracts from Authorization header/query/body
    ip: getRemoteIP(req)
  };
  authorization.resolve(resolveData, callback);  // Passes BOTH to shared resolver
};
```

**Source:** `lib/api/verifyauth.js`, `lib/authorization/index.js`, `externals/Trio/Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift`

### 3.3 API v3: Entry-Point Restrictions

**Critical Distinction:** API v3 has different authentication behavior depending on interface type (REST vs WebSocket).

#### 3.3.1 API v3 REST: Token-Only Entry Point

The v3 REST security layer (`lib/api3/security.js`) only extracts Bearer tokens and does **not** pass API_SECRET to the shared authorization module:

```javascript
// lib/api3/security.js - authenticate() function
function authenticate (opCtx) {
  let token;
  if (req.header('Authorization')) {
    const parts = req.header('Authorization').split(' ');
    if (parts.length === 2 && parts[0].toLowerCase() === 'bearer') {
      token = parts[1];
    }
  }
  
  if (!token) {
    return reject(HTTP.UNAUTHORIZED);  // Rejects if no Bearer token
  }
  
  // NOTE: Only passes { token, ip } - no api_secret parameter
  ctx.authorization.resolve({ token, ip: getRemoteIP(req) }, function resolveFinish (err, result) {
    // ...
  });
}
```

**v3 REST Documentation Claim (`lib/api3/doc/security.md`):**
> "In APIv3, API_SECRET can no longer be used for authentication or authorization."

**Reality:** This is an **entry-point restriction**, not an architectural limitation. The shared authorization module can handle API_SECRET; the v3 REST security layer simply chooses not to pass it through.

**Token Flow Clarification:**
The v3 REST workflow is:
1. Client obtains JWT by calling `/api/v2/authorization/request/{accessToken}` with an opaque access token
2. Server returns a signed JWT containing the access token
3. Client sends JWT in `Authorization: Bearer {jwt}` header
4. Server verifies JWT signature and extracts the access token from the JWT payload
5. Server resolves access token to permissions via `authorization.resolve()`

**Transmission (v3 REST):**
- Header: `Authorization: Bearer <jwt>` (required — the Bearer value is a JWT, not an opaque access token)

#### 3.3.2 API v3 WebSocket: Varied Authentication Support

The v3 WebSocket endpoints have **different authentication behaviors**:

##### alarmSocket (`/alarm` namespace) — Full Dual-Auth Support

The alarmSocket supports API_SECRET, JWT tokens, AND access tokens, passing them to the shared authorization module:

```javascript
// lib/api3/alarmSocket.js - subscribe() function (line 120)
// Comment at line 61: "Support webclient authorization with api_secret is added"
return ctx.authorization.resolve({ 
  api_secret: message.secret,     // Accepts API_SECRET (SHA1 hash)
  token: message.jwtToken,         // Also accepts JWT token
  ip: getRemoteIP(socket.request) 
}, function resolveFinish (err, auth) {
  // ...
});
```

Also supports native client accessToken (line 71-72):
```javascript
if (message && message.accessToken) {
  return ctx.authorization.resolveAccessToken(message.accessToken, ...)
}
```

**Transmission (alarmSocket):**
- Message field: `secret` (SHA1-hashed API_SECRET)
- Message field: `jwtToken` (JWT token)
- Message field: `accessToken` (opaque access token)

##### storageSocket (`/storage` namespace) — Access Token Only

The storageSocket **only** accepts access tokens and calls `resolveAccessToken` directly (not the full `resolve` function):

```javascript
// lib/api3/storageSocket.js - subscribe() function (lines 64-78)
self.subscribe = function subscribe (socket, message, returnCallback) {
  if (message && message.accessToken) {
    return ctx.authorization.resolveAccessToken(message.accessToken, function resolveFinish (err, auth) {
      // ...
    });
  }
  // No API_SECRET or JWT support - returns error if no accessToken
  returnCallback({ success: false, message: apiConst.MSG.SOCKET_MISSING_OR_BAD_ACCESS_TOKEN });
};
```

**Transmission (storageSocket):**
- Message field: `accessToken` (opaque access token) — **only method**

**Source:** `lib/api3/alarmSocket.js`, `lib/api3/storageSocket.js`

### 3.4 Opaque Access Tokens

**Token Creation:** Access tokens are created in the Nightscout admin panel (`/admin/`) and associated with roles. They are opaque strings (not JWTs) - the server resolves them to permissions via the authorization subsystem.

**Permissions:** Apache Shiro-style granular permissions:
```
api:*:read                        // Read all collections
api:treatments:create,update      // Create and update treatments only
api:entries:read                  // Read entries only
notifications:*:ack               // Acknowledge notifications
```

**Token Resolution (`lib/authorization/storage.js`):**
- Tokens are matched against stored subjects in the database
- Each subject has associated roles with Shiro permission strings
- Permissions are resolved to a `shiros` array for authorization checks

### 3.5 Authentication Comparison Matrix

| Aspect | v1 REST | v3 REST | v3 alarmSocket | v3 storageSocket |
|--------|---------|---------|----------------|------------------|
| **API_SECRET** | ✅ Yes | ❌ Entry-point blocks | ✅ Yes | ❌ No |
| **JWT Token (Bearer/jwtToken)** | ✅ Yes | ✅ Required | ✅ Yes | ❌ No |
| **Access Token (query/body/msg)** | ✅ Yes | ❌ No | ✅ Yes | ✅ Required |
| **Uses `authorization.resolve()`** | ✅ Yes | ✅ Yes (token only) | ✅ Yes | ❌ No |
| **Uses `resolveAccessToken()`** | ✅ (fallback) | ❌ No | ✅ (fallback) | ✅ Yes (only) |
| **Granular Permissions** | ✅ With tokens | ✅ Yes | ✅ Yes | ✅ Yes |
| **Subject Tracking** | ✅ With tokens | ✅ Yes | ✅ Yes | ✅ Yes |

### 3.6 Design Intent vs Implementation

**Design Intent:** The shared authorization module (`lib/authorization/index.js`) was designed to handle both API_SECRET and token-based authentication uniformly, using shared code for permission resolution.

**Implementation Reality:**
- **v1 REST:** Fully implements design intent (both mechanisms via shared `resolve()`)
- **v3 alarmSocket:** Fully implements design intent (API_SECRET, JWT, and accessToken)
- **v3 storageSocket:** Partial implementation (accessToken only via `resolveAccessToken()`)
- **v3 REST:** Artificially restricts to JWT Bearer token only at the security.js entry point

**Gap Identified (GAP-AUTH-001):** The v3 REST security layer's token-only restriction is inconsistent with:
1. The shared authorization module's dual-auth capability
2. The v3 alarmSocket interface which accepts both mechanisms
3. The design intent of unified authentication handling

**Possible Reasons for v3 REST Restriction:**
- Security preference to deprecate all-or-nothing API_SECRET for REST calls
- Encouragement of granular permission adoption
- Simplified OAuth/JWT integration for REST clients

**Gap Identified (GAP-AUTH-002):** v1 clients using API_SECRET cannot use granular permissions. A "readable" site allows unauthenticated reads, but writes require full API_SECRET or a properly configured access token.

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

### 8.3 Client Response Parsing Behavior (Verified 2026-01-19)

Understanding how clients actually parse v1 API responses is critical for MongoDB modernization. Source code verification reveals the requirements are **less strict than often assumed**.

#### Loop (NightscoutKit)

**Source:** [`LoopKit/NightscoutKit`](https://github.com/LoopKit/NightscoutKit) - `Sources/NightscoutKit/NightscoutClient.swift` - `postToNS` function

```swift
guard let insertedEntries = postResponse as? [[String: Any]], 
      insertedEntries.count == json.count else {
    completion(.failure(NightscoutError.invalidResponse(...)))
    return
}

let ids = insertedEntries.map({ (entry: [String: Any]) -> String in
    if let id = entry["_id"] as? String {
        return id
    } else {
        return "NA"  // Graceful fallback
    }
})
```

**Actual Requirements:**
| Requirement | Status | Notes |
|-------------|--------|-------|
| Response is array | **Required** | Validated with `as? [[String: Any]]` |
| Array length matches request | **Required** | Validated with `count == json.count` |
| Each object has `_id` field | **Preferred** | Falls back to "NA" if missing |
| Response order preserved | **Required** | Direct index mapping: `syncIdentifier[i]` → `response[i]._id` |
| `ok` field present | **Not required** | Not checked |
| `n` field present | **Not required** | Not checked |

**Minimum Viable Response:**
```json
[{ "_id": "id1" }, { "_id": "id2" }, { "_id": "id3" }]
```

#### AAPS (v3 API)

**Source:** `AndroidAPS/core/nssdk/` - `CreateUpdateResponse` data class

AAPS requires the full v3 response schema:
```kotlin
data class CreateUpdateResponse(
    val identifier: String,
    val isDeduplication: Boolean,
    val deduplicatedIdentifier: String?,
    val lastModified: Long
)
```

All four fields are used for sync logic. Changes to this schema will break AAPS.

#### Trio

Trio uses similar v1 parsing patterns to Loop. The `id` field (Trio's client-side UUID) is separate from the MongoDB `_id` returned in responses.

**Note:** Trio's response parsing was not directly verified in source code for this analysis; this assessment is based on its documented use of v1 API endpoints with similar batch patterns to Loop.

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
