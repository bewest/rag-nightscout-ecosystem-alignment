# Nightscout API v3 Specification Summary

**Authoritative Source:** `externals/cgm-remote-monitor/lib/api3/swagger.yaml`  
**Validation Code:** `externals/cgm-remote-monitor/lib/api3/generic/*/validate.js`  
**Version:** 3.0.4  
**License:** AGPL 3  
**Base Path:** `/api/v3`

> **Note:** This is a summary document. For authoritative schema definitions, consult the OpenAPI spec directly.

---

## Overview

Nightscout API v3 is a lightweight, secured, HTTP REST compliant interface for T1D treatment data exchange. It supersedes API v1/v2 with modern features including OpenAPI 3.0 specification, JWT authentication, and soft-delete support.

---

## Environment Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `API3_SECURITY_ENABLE` | `true` | Master security switch (never disable in production) |
| `API3_MAX_LIMIT` | `1000` | Maximum documents per query |
| `API3_AUTOPRUNE_DEVICESTATUS` | `60` | Days to retain devicestatus |
| `API3_AUTOPRUNE_ENTRIES` | - | Days to retain entries (if set) |
| `API3_AUTOPRUNE_TREATMENTS` | - | Days to retain treatments (if set) |
| `API3_DEDUP_FALLBACK_ENABLED` | `true` | Enable fallback deduplication |
| `API3_CREATED_AT_FALLBACK_ENABLED` | `true` | Auto-fill `created_at` from `date` |

---

## Collections

| Collection | Purpose |
|------------|---------|
| `entries` | CGM glucose readings (SGV, MBG, calibrations) |
| `treatments` | Insulin, carbs, overrides, notes |
| `devicestatus` | Controller/pump/uploader state |
| `profile` | Therapy settings (basal, ISF, ICR) |
| `food` | Food database entries |
| `settings` | Application-specific settings (admin only) |

---

## Generic Operations

All collections support CRUD operations via generic endpoints:

### Search: `GET /{collection}`
Query documents with filtering, sorting, and paging.

**Parameters:**
- Filter parameters (collection-specific fields)
- `sort` / `sort$desc` - Ordering
- `limit` / `skip` - Pagination
- `fields` - Field projection

**Permission:** `api:*:read` or `api:{collection}:read`

### Create: `POST /{collection}`
Insert new document. Returns 201 on success, 200 if deduplicated.

**Deduplication Rules (fallback):**
| Collection | Duplicate Criteria |
|------------|-------------------|
| `devicestatus` | `created_at` + `device` |
| `entries` | `date` + `type` |
| `food` | `created_at` |
| `profile` | `created_at` |
| `treatments` | `created_at` + `eventType` |

**Permission:** `api:{collection}:create` (+ `update` for dedup)

### Read: `GET /{collection}/{identifier}`
Retrieve single document by identifier.

**Conditional Headers:**
- `If-Modified-Since` → 304 if unchanged

**Permission:** `api:{collection}:read`

### Update: `PUT /{collection}/{identifier}`
Replace entire document.

**Conditional Headers:**
- `If-Unmodified-Since` → 412 if modified by another

**Permission:** `api:{collection}:update` (+ `create` for upsert)

### Patch: `PATCH /{collection}/{identifier}`
Partial update. Sets `modifiedBy` automatically.

**Permission:** `api:{collection}:update`

### Delete: `DELETE /{collection}/{identifier}`
Soft delete (marks `isValid=false`). Use `permanent=true` for hard delete.

**Permission:** `api:{collection}:delete`

---

## History Operation

### `GET /{collection}/history`
Incremental sync since timestamp. Returns all insertions, updates, and deletions.

**Headers:**
- `Last-Modified` (required) - Starting timestamp

**Response includes:**
- Documents modified after timestamp
- Deleted documents with `isValid=false`
- `Last-Modified` response header for next sync

### `GET /{collection}/history/{lastModified}`
Same as above but with millisecond precision via path parameter.

---

## Other Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/version` | GET | No | API version info |
| `/status` | GET | Yes | Version + permissions |
| `/lastModified` | GET | Yes | Last modification per collection |

---

## Document Schema

### Base Fields (all collections)

**Immutability enforced in:** `lib/api3/generic/update/validate.js`

| Field | Type | Mutable | Enforcement | Description |
|-------|------|---------|-------------|-------------|
| `identifier` | String | No* | Server rejects | Primary addressing key (auto-assigned) |
| `date` | Integer (epoch ms) | No | Server rejects | Event timestamp |
| `utcOffset` | Integer (minutes) | No | Server rejects | Local timezone offset |
| `app` | String | No | Server rejects | Origin application |
| `device` | String | No | Server rejects | Origin device |
| `_id` | String | No | Internal | Internal MongoDB ID |
| `srvCreated` | Integer (epoch ms) | No | Server rejects | Server creation time |
| `srvModified` | Integer (epoch ms) | No | Server sets | Server modification time |
| `subject` | String | No | Server rejects | Creating user/token |
| `modifiedBy` | String | No | Server sets | Last modifier |
| `isValid` | Boolean | No | Server rejects | Soft-delete flag (false = deleted) |
| `isReadOnly` | Boolean | Client | N/A | Lock document forever (HTTP 422 on modify) |

*Exception: `identifier` changes allowed during deduplication for API v1 documents.

### Entry-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `type` | String | `sgv`, `mbg`, `cal` |
| `sgv` | Number | Sensor glucose value |
| `direction` | String | Trend arrow |
| `noise` | Number | Signal noise level (0-5) |
| `filtered` | Number | Raw filtered value |
| `unfiltered` | Number | Raw unfiltered value |
| `rssi` | Number | Signal strength |
| `units` | String | `mg` or `mmol` |

### Treatment-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `eventType` | String | Treatment classification (immutable) |
| `insulin` | Number | Units delivered |
| `carbs` | Number | Grams consumed |
| `duration` | Number | Duration in minutes |
| `percent` | Number | Basal rate percentage |
| `absolute` | Number | Absolute basal rate |
| `glucose` | Number | BG at time of treatment |
| `glucoseType` | String | `Sensor`, `Finger`, `Manual` |
| `notes` | String | Free text |
| `enteredBy` | String | User/device nickname |
| `profile` | String | Profile name (for switches) |
| `targetTop` / `targetBottom` | Number | Temporary target range |

---

## Authentication

### JWT Token
- Passed via `Authorization: Bearer {token}` header
- Or via `token` query/body parameter
- Contains `accessToken` claim mapped to subject

### API_SECRET
- Legacy auth via `api-secret` header or `secret` parameter
- Grants full `*` permissions when valid

### Permission Format
Apache Shiro-style: `{area}:{collection}:{operation}`

Examples:
- `*` - Full access
- `api:*:read` - Read all API collections
- `api:treatments:create,update` - Create/update treatments

---

## Error Responses

| Code | Meaning |
|------|---------|
| 400 | Bad request (invalid parameters) |
| 401 | Unauthorized (missing/invalid auth) |
| 403 | Forbidden (insufficient permissions) |
| 404 | Not found |
| 406 | Not acceptable (wrong Accept header) |
| 410 | Gone (document was deleted) |
| 412 | Precondition failed (If-Unmodified-Since) |
| 422 | Unprocessable entity (validation error) |

---

## Cross-References

- Full OpenAPI spec: `externals/cgm-remote-monitor/lib/api3/swagger.yaml`
- API tutorial: `externals/cgm-remote-monitor/lib/api3/doc/tutorial.md`
- Security docs: `externals/cgm-remote-monitor/lib/api3/doc/security.md`
- Socket API: `externals/cgm-remote-monitor/lib/api3/doc/socket.md`
