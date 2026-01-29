# Nightscout API v3 Deep Dive

> **Date**: 2026-01-29  
> **Source**: `externals/cgm-remote-monitor/lib/api3/`  
> **Version**: 3.0.3-alpha (per const.json)

## Overview

Nightscout API v3 is a REST API providing CRUD operations on diabetes-related data collections. It features:
- Bearer token authentication with shiro-trie permission system
- Generic collection operations (SEARCH, CREATE, READ, UPDATE, PATCH, DELETE, HISTORY)
- Document deduplication via `identifier` field
- Incremental sync via `srvModified` timestamps

---

## Collections

| Collection | Storage Name | Dedup Fallback Fields | Date Field |
|------------|-------------|----------------------|------------|
| `devicestatus` | devicestatus | `created_at`, `device` | `created_at` |
| `entries` | entries | `date`, `type` | `date` |
| `food` | food | `created_at` | `created_at` |
| `profile` | profile | `created_at` | `created_at` |
| `settings` | settings | *(none)* | *(none)* |
| `treatments` | treatments | `created_at`, `eventType` | `created_at` |

**Source**: `lib/api3/generic/setup.js:25-93`

---

## Operations

### Routes per Collection

| Method | Route | Operation | Permission |
|--------|-------|-----------|------------|
| GET | `/{collection}` | SEARCH | `api:{collection}:read` |
| POST | `/{collection}` | CREATE | `api:{collection}:create` |
| GET | `/{collection}/history` | HISTORY | `api:{collection}:read` |
| GET | `/{collection}/history/{lastModified}` | HISTORY | `api:{collection}:read` |
| GET | `/{collection}/{identifier}` | READ | `api:{collection}:read` |
| PUT | `/{collection}/{identifier}` | UPDATE | `api:{collection}:update` |
| PATCH | `/{collection}/{identifier}` | PATCH | `api:{collection}:update` |
| DELETE | `/{collection}/{identifier}` | DELETE | `api:{collection}:delete` |

**Note**: `settings` collection requires `api:settings:admin` for all read operations.

**Source**: `lib/api3/generic/collection.js:42-72`

---

## Document Model

### System Fields

| Field | Type | Description |
|-------|------|-------------|
| `identifier` | string | Unique document ID (primary dedup key) |
| `srvCreated` | timestamp | Server-side creation time (ms since epoch) |
| `srvModified` | timestamp | Server-side modification time (ms since epoch) |
| `isValid` | boolean | Soft-delete flag (false = deleted) |
| `isReadOnly` | boolean | Prevents client modification |

### Date Fields

| Collection | Primary Date Field |
|------------|-------------------|
| entries | `date` (ms since epoch) |
| devicestatus | `created_at` (ISO string) |
| treatments | `created_at` (ISO string) |
| profile | `created_at` (ISO string) |
| food | `created_at` (ISO string) |

---

## Query Parameters

### Filtering

Operators supported (append to field name with `$`):

| Operator | Meaning | Example |
|----------|---------|---------|
| `eq` | equals (default) | `type=sgv` |
| `ne` | not equals | `type$ne=mbg` |
| `gt` | greater than | `date$gt=1609459200000` |
| `gte` | greater or equal | `date$gte=1609459200000` |
| `lt` | less than | `date$lt=1609545600000` |
| `lte` | less or equal | `date$lte=1609545600000` |
| `in` | in set | `type$in=sgv,mbg` |
| `nin` | not in set | `type$nin=cal` |
| `re` | regex match | `device$re=loop` |

**Source**: `lib/api3/generic/search/input.js:52-83`

### Pagination & Sorting

| Parameter | Description | Default |
|-----------|-------------|---------|
| `limit` | Max documents returned | 1000 (API3_MAX_LIMIT) |
| `skip` | Offset for paging | 0 |
| `sort` | Sort field (ascending) | *(none)* |
| `sort$desc` | Sort field (descending) | *(none)* |
| `fields` | Field projection | *(all fields)* |

### Reserved Parameters

`token`, `sort`, `sort$desc`, `limit`, `skip`, `fields`, `now`

---

## Authentication

### Bearer Token

```http
Authorization: Bearer <token>
```

Tokens are resolved via `ctx.authorization.resolve()` which checks against configured subjects.

### Permission Format

```
<scope>:<collection>:<operation>
```

Examples:
- `api:entries:read` - Read entries
- `api:treatments:create` - Create treatments
- `*:*:read` - Read all collections
- `api:settings:admin` - Admin access to settings

**Source**: `lib/api3/security.js`

### Security Switch

```env
API3_SECURITY_ENABLE=true  # default
```

When disabled, all requests get admin permissions (development only).

---

## History/Sync Pattern

### Request

```http
GET /api/v3/{collection}/history/{lastModified}
```

Or with header:
```http
GET /api/v3/{collection}/history
Last-Modified: Tue, 01 Jan 2026 00:00:00 GMT
```

### Response

Returns documents where `srvModified > lastModified` (or `>=` for header variant).

Response headers:
- `Last-Modified`: Latest srvModified in result set
- `ETag`: `W/"{maxSrvModified}"`

### Sync Algorithm

1. Client stores last `srvModified` timestamp
2. Request `/history/{lastModified}` 
3. Process returned documents (including `isValid=false` for deletes)
4. Update stored timestamp from response `Last-Modified` header
5. Repeat periodically

**Source**: `lib/api3/generic/history/operation.js`

---

## Deduplication

### Primary: `identifier` Field

Documents with matching `identifier` are deduplicated (CREATE becomes UPDATE).

### Fallback Deduplication

When `API3_DEDUP_FALLBACK_ENABLED=true` (default), documents without `identifier` are matched by:

| Collection | Match Fields |
|------------|-------------|
| devicestatus | `created_at` + `device` |
| entries | `date` + `type` |
| food | `created_at` |
| profile | `created_at` |
| treatments | `created_at` + `eventType` |

**Source**: `lib/api3/generic/setup.js:29-93`

---

## Auto-Pruning

Optional automatic deletion of old documents:

```env
API3_AUTOPRUNE_DEVICESTATUS=60   # days (default)
API3_AUTOPRUNE_ENTRIES=365       # days
API3_AUTOPRUNE_TREATMENTS=120    # days
```

Deletes documents where `srvCreated < (now - days)`.

---

## Specific Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/version` | GET | API version info |
| `/status` | GET | Server status |
| `/lastModified` | GET | Last modification times per collection |

---

## WebSocket Support

### Storage Socket

Real-time document updates via WebSocket at `/api/v3/socket`.

### Alarm Socket

Real-time alarm notifications.

**Source**: `lib/api3/storageSocket.js`, `lib/api3/alarmSocket.js`

---

## Configuration Summary

| Variable | Default | Description |
|----------|---------|-------------|
| `API3_SECURITY_ENABLE` | true | Enable authentication |
| `API3_MAX_LIMIT` | 1000 | Max documents per query |
| `API3_DEDUP_FALLBACK_ENABLED` | true | Fallback deduplication |
| `API3_CREATED_AT_FALLBACK_ENABLED` | true | Auto-fill created_at |
| `API3_AUTOPRUNE_{COLLECTION}` | varies | Auto-prune days |

---

## Gaps Identified

### GAP-API3-001: No Batch Operations

**Description**: API v3 lacks batch create/update/delete operations. Each document requires individual HTTP request.

**Impact**: Sync performance issues for bulk uploads (e.g., historical data import).

**Possible Solution**: Add `POST /{collection}/batch` endpoint accepting array.

### GAP-API3-002: No Cursor-Based Pagination

**Description**: Uses offset pagination (`skip`) which is inefficient for large datasets.

**Impact**: Performance degrades with high skip values.

**Possible Solution**: Add `cursor` parameter using `srvModified` + `identifier` for stable pagination.

### GAP-API3-003: Limited Field Projection Syntax

**Description**: `fields` parameter is basic comma-separated list.

**Impact**: Cannot exclude specific fields, only include.

**Possible Solution**: Support `fields=-largeField` exclusion syntax.

---

## Requirements Extracted

### REQ-API3-001: History Endpoint Completeness

**Statement**: The `/history` endpoint MUST return all modified documents including soft-deleted ones (`isValid=false`).

**Rationale**: Clients need delete notifications for full sync.

**Verification**: History response includes documents with `isValid: false`.

### REQ-API3-002: Deduplication Determinism

**Statement**: Deduplication MUST be deterministic based on `identifier` or fallback fields.

**Rationale**: Prevents duplicate documents from sync race conditions.

**Verification**: Identical POST requests don't create duplicates.

### REQ-API3-003: srvModified Monotonic

**Statement**: `srvModified` MUST be monotonically increasing within a collection.

**Rationale**: Ensures history sync doesn't miss documents.

**Verification**: Sequential updates produce increasing srvModified values.

---

## Source Files

| File | Lines | Purpose |
|------|-------|---------|
| `lib/api3/index.js` | 119 | API setup, route mounting |
| `lib/api3/const.json` | 51 | Constants, HTTP codes, messages |
| `lib/api3/security.js` | 93 | Authentication, authorization |
| `lib/api3/generic/setup.js` | 103 | Collection configuration |
| `lib/api3/generic/collection.js` | 230 | Collection class, routing |
| `lib/api3/generic/search/operation.js` | 79 | SEARCH implementation |
| `lib/api3/generic/search/input.js` | 140 | Query parsing |
| `lib/api3/generic/history/operation.js` | 151 | HISTORY implementation |
| `lib/api3/swagger.yaml` | 1500+ | OpenAPI specification |

---

## Related Documents

- [API Layer Audit](../sdqctl-proposals/cgm-remote-monitor-api-layer-audit.md)
- [Authentication Flows Deep Dive](./authentication-flows-deep-dive.md)
- [OpenAPI Spec](../../specs/openapi/)
