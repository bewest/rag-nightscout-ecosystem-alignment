# cgm-remote-monitor API Layer Deep Dive

> **Purpose**: Comprehensive analysis of Nightscout's REST API architecture  
> **Scope**: v1, v3 APIs, authorization, Socket.IO, deduplication  
> **Last Updated**: 2026-01-29

## Executive Summary

This document analyzes the API layer of cgm-remote-monitor, the core Nightscout server. The analysis covers both legacy v1 API and modern v3 API, with focus on patterns critical for AID controller compatibility (Loop, AAPS, Trio).

### Key Findings

| Finding | Impact |
|---------|--------|
| v3 uses UPSERT on duplicate | Safe for retry/resync scenarios |
| Dedup keys per collection | Prevents duplicate treatments on re-upload |
| Socket.IO for real-time | Enables instant UI updates |
| Shiro-style permissions | Granular access control |

---

## API Architecture Overview

### Directory Structure

```
lib/
├── api/                    # v1 API (legacy, MongoDB-query style)
│   ├── index.js           # Main router
│   ├── entries/           # SGV, MBG, calibration
│   ├── treatments/        # Bolus, carbs, temp basal
│   ├── devicestatus/      # Loop/AAPS state
│   └── profile/           # Therapy settings
├── api3/                   # v3 API (RESTful, modern)
│   ├── index.js           # Main entry point
│   ├── security.js        # Auth middleware
│   └── generic/           # CRUD operation handlers
│       ├── collection.js  # Collection abstraction
│       ├── create/        # POST handlers + dedup
│       ├── read/          # GET single
│       ├── search/        # GET collection
│       ├── update/        # PUT replacement
│       ├── patch/         # PATCH partial
│       ├── delete/        # DELETE handlers
│       └── history/       # Changelog endpoint
├── authorization/          # Token resolution, permissions
└── server/                 # Socket.IO, HTTP server
```

---

## v1 API (Legacy)

### Entry Point
**File**: `lib/api/index.js`

The v1 API uses MongoDB-style query parameters and supports multiple response formats.

### Endpoints

| Collection | GET | POST | PUT | DELETE |
|------------|-----|------|-----|--------|
| `/entries` | ✓ Query + formats | ✓ Create | - | ✓ By ID/type |
| `/treatments` | ✓ Query | ✓ Create | ✓ Update | ✓ By ID |
| `/devicestatus` | ✓ Query | ✓ Create | - | ✓ By ID |
| `/profile` | ✓ Query | ✓ Create | - | ✓ By ID |

### Special v1 Features

#### Time-Range Queries
```
GET /api/v1/times/2015-04/T{13..18}:00:00
```
Bash-style brace expansion for time ranges.

#### MongoDB Find Syntax
```
GET /api/v1/entries?find[sgv][$gte]=120&find[type]=sgv
```

#### Multi-Format Response
```
GET /api/v1/entries.json
GET /api/v1/entries.csv
GET /api/v1/entries.tsv
```

### In-Memory Caching

```javascript
// lib/api/entries/index.js:477
if (count <= ctx.cache.entries.length) {
  // Serve from memory cache
}
```

Entries served from memory when count ≤ cached entries.

---

## v3 API (Modern)

### Entry Point
**File**: `lib/api3/index.js`

```javascript
// Enabled collections
app.set('enabledCollections', [
  'devicestatus', 'entries', 'food', 
  'profile', 'settings', 'treatments'
]);
```

### Generic Collection Pattern

All v3 collections follow the same RESTful pattern:

| Method | Path | Operation | Handler |
|--------|------|-----------|---------|
| GET | `/{collection}` | Search/List | `search/operation.js` |
| POST | `/{collection}` | Create (upsert) | `create/operation.js` |
| GET | `/{collection}/{id}` | Read single | `read/operation.js` |
| PUT | `/{collection}/{id}` | Replace | `update/operation.js` |
| PATCH | `/{collection}/{id}` | Partial update | `patch/operation.js` |
| DELETE | `/{collection}/{id}` | Delete | `delete/operation.js` |
| GET | `/{collection}/history` | Changelog | `history/operation.js` |
| GET | `/{collection}/history/{lastModified}` | Since timestamp | `history/operation.js` |

### Collection Setup
**File**: `lib/api3/generic/setup.js`

```javascript
// Each collection configured with:
new Collection({
  name: 'treatments',
  dedupFallbackFields: ['created_at', 'eventType']
});
```

---

## Authorization System

### Credential Sources (Priority Order)

| Source | Header/Param | Format |
|--------|--------------|--------|
| API Secret | `api-secret` header, `?secret=` | Plain text hash |
| JWT Token | `Authorization: Bearer {token}` | JWT string |
| Query Token | `?token=` | JWT string |

### Permission Model

Uses Apache Shiro-style permission strings:

```
namespace:resource:action
```

**Examples**:
- `api:entries:read` - Read entries
- `api:treatments:create` - Create treatments
- `api:*:admin` - Full admin access
- `*:*:*` - Superuser

### v3 Security Middleware
**File**: `lib/api3/security.js`

```javascript
// authenticate(opCtx) - Lines 17-51
// - Checks Authorization header for "Bearer {token}"
// - Returns 401 if missing/invalid

// demandPermission(opCtx, permission) - Lines 74-85
// - Checks shiro-trie permissions
// - Returns 403 if missing permission
```

### Permission Resolution
**File**: `lib/authorization/index.js`

```javascript
authorization.resolveWithRequest(req, callback) {
  // 1. Extract API_SECRET + JWT token + IP
  // 2. Verify API key or resolve JWT to subject/roles
  // 3. Return shiros (permissions) array
}
```

---

## Deduplication Logic

### Overview

API v3 uses UPSERT semantics - duplicates are **updated**, not rejected.

**File**: `lib/api3/generic/create/operation.js`

```javascript
// Line 26-35
const result = await col.storage.identifyingFilter(
  doc.identifier, doc, col.dedupFallbackFields
);

if (result.length > 0) {
  await replace(opCtx, doc, storageDoc, { isDeduplication: true });
} else {
  await insert(opCtx, doc);
}
```

### Dedup Keys by Collection

| Collection | Primary Key | Fallback Keys |
|------------|-------------|---------------|
| entries | `identifier` | `date`, `type` |
| treatments | `identifier` | `created_at`, `eventType` |
| devicestatus | `identifier` | `created_at`, `device` |
| profile | `identifier` | `created_at` |
| food | `identifier` | `created_at` |
| settings | `identifier` | (none) |

### Fallback Dedup Rules
**File**: `lib/api3/generic/utils.js:145-163`

1. ALL fallback fields must be present in document
2. ALL fallback fields must match exactly
3. Existing document must NOT have an `identifier` field
4. Controlled by `API3_DEDUP_FALLBACK_ENABLED` env flag

### Impact on AID Controllers

| Controller | Sync Behavior | Dedup Compatibility |
|------------|---------------|---------------------|
| Loop | Uses `identifier` (UUID) | ✓ Native support |
| AAPS | Uses `identifier` or `_id` | ✓ With fallback |
| Trio | Uses `identifier` (UUID) | ✓ Native support |
| xDrip+ | Uses `uuid` → `identifier` | ✓ Mapped |

---

## Socket.IO Real-Time Updates

### Architecture
**File**: `lib/server/websocket.js`

```javascript
// Client joins DataReceivers room after auth
socket.join('DataReceivers');

// Updates pushed to all receivers
io.to('DataReceivers').compress(true).emit('dataUpdate', delta);
```

### Event Types

| Event | Direction | Purpose |
|-------|-----------|---------|
| `authorize` | Client → Server | Authenticate connection |
| `connected` | Server → Client | Auth acknowledgment |
| `dataUpdate` | Server → Client | Real-time glucose/status |
| `retroUpdate` | Server → Client | Historical data batch |
| `clients` | Server → Client | Connected client count |
| `dbAdd` | Client → Server | Create record |
| `dbUpdate` | Client → Server | Modify record |
| `dbRemove` | Client → Server | Delete record |
| `loadRetro` | Client → Server | Request history |

### Data Flow

```
API POST /treatments
    ↓
ctx.bus.emit('data-received')
    ↓
Data pipeline processes
    ↓
ctx.bus.emit('data-processed')
    ↓
Socket.IO emitData()
    ↓
io.to('DataReceivers').emit('dataUpdate', delta)
```

### Authorization

Socket connections require:
- `api:*:read` for read access
- `api:*:create,update,delete` for write
- Verified via `verifyAuthorization()` on connect

---

## v1 vs v3 Comparison

| Aspect | v1 API | v3 API |
|--------|--------|--------|
| **Query Style** | MongoDB find syntax | RESTful query params |
| **Routing** | Regex/brace patterns | Standard REST paths |
| **Response Format** | JSON, CSV, TSV, SVG | JSON only |
| **Deduplication** | Manual/implicit | Explicit UPSERT |
| **Auth Tokens** | API_SECRET + JWT | JWT emphasis |
| **Permissions** | Shiro trie | Shiro trie |
| **Caching** | In-memory check | CachedCollectionStorage |
| **History** | None | `/history` endpoint |

---

## Gaps Identified

### GAP-API-001: No OpenAPI Specification

**Description**: Neither v1 nor v3 API has machine-readable OpenAPI specification.

**Impact**: 
- Clients must reverse-engineer API structure
- No automated validation of requests/responses
- Difficult to generate client SDKs

**Remediation**: Generate OpenAPI 3.0 spec from code analysis.

### GAP-API-002: v1/v3 Response Format Divergence

**Description**: v1 and v3 return different response structures for same data.

**Evidence**:
```javascript
// v1: Raw array
[{sgv: 120, date: ...}, ...]

// v3: Wrapped with metadata
{result: [{sgv: 120, date: ...}], ...}
```

**Impact**: Clients must handle both formats or target specific version.

**Remediation**: Document differences, provide migration guide.

### GAP-API-003: Inconsistent Timestamp Fields

**Description**: Different collections use different timestamp field names.

**Evidence**:
| Collection | Primary Timestamp |
|------------|------------------|
| entries | `date` (epoch ms) |
| treatments | `created_at` (ISO) |
| devicestatus | `created_at` (ISO) |

**Impact**: Client code must handle multiple timestamp formats.

**Remediation**: Document canonical field names per collection.

---

## Source Files Analyzed

### Core API
- `lib/api/index.js` - v1 router
- `lib/api/entries/index.js` - Entries endpoints
- `lib/api/treatments/index.js` - Treatments endpoints
- `lib/api/devicestatus/index.js` - DeviceStatus endpoints

### v3 API
- `lib/api3/index.js` - Main entry point
- `lib/api3/security.js` - Auth middleware
- `lib/api3/generic/collection.js` - Collection abstraction
- `lib/api3/generic/setup.js` - Collection initialization
- `lib/api3/generic/create/operation.js` - Create/dedup logic
- `lib/api3/generic/utils.js` - Dedup utilities

### Authorization
- `lib/authorization/index.js` - Token resolution

### Real-Time
- `lib/server/websocket.js` - Socket.IO integration

---

## Recommendations

| Priority | Action | Impact |
|----------|--------|--------|
| P1 | Document dedup keys per collection | Prevents duplicate treatment bugs |
| P1 | Add OpenAPI spec for v3 | Enables SDK generation |
| P2 | Document v1→v3 migration | Helps client developers |
| P2 | Standardize timestamp format | Reduces client complexity |
| P3 | Add v3 support for CSV export | Feature parity with v1 |

---

## Related Documents

- [Database Layer Deep Dive](cgm-remote-monitor-database-deep-dive.md)
- [Nightscout v3 Treatments Schema](../../mapping/nightscout/v3-treatments-schema.md)
- [Batch Ordering Deep Dive](batch-ordering-deep-dive.md)
