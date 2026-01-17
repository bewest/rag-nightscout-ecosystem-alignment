# CGM Remote Monitor Source Code Synthesis

**Purpose:** Deep interrogation of Nightscout cgm-remote-monitor source code, synthesizing findings with external analysis and identifying key implementation details for alignment work.

**Source:** `externals/cgm-remote-monitor/` (wip/replit/with-mongodb-update branch)  
**Date:** 2026-01-16

---

## Executive Summary

This document synthesizes findings from source code analysis of Nightscout's cgm-remote-monitor repository, cross-referencing with documentation inventories and external project analyses. The goal is to identify:

1. Implementation details not fully captured in documentation
2. Critical code paths for data handling
3. Deduplication and sync patterns
4. Authorization model implementation
5. WebSocket real-time protocol details
6. Gaps requiring attention for alignment work

---

## 1. Data Layer Implementation

### 1.1 Treatment Processing Pipeline

**Source:** `lib/server/treatments.js`

The treatments module implements a upsert-by-default pattern:

```javascript
var query = {
  created_at: results.created_at,
  eventType: obj.eventType
};
api().replaceOne(query, obj, {upsert: true}, ...)
```

**Key Findings:**

| Behavior | Implementation |
|----------|----------------|
| Upsert key | `created_at` + `eventType` combination |
| Timestamp normalization | All dates converted to UTC ISO 8601 |
| UTC offset tracking | Automatically extracted and stored as `utcOffset` |
| Field coercion | Numeric fields force-cast via `Number()` |
| Empty field cleanup | Falsy/NaN fields deleted before storage |

**Pre-Bolus Handling (undocumented):**
When `preBolus` field is set, the system creates a *second* treatment record offset by `preBolus` minutes, splitting carbs to the delayed record:

```javascript
var pbTreat = {
  created_at: (new Date(new Date(results.created_at).getTime() + (obj.preBolus * 60000))).toISOString(),
  eventType: obj.eventType,
  carbs: results.preBolusCarbs
};
```

### 1.2 Field Transformation Rules

**Source:** `lib/server/treatments.js:198-277` (`prepareData` function)

| Input Field | Transformation |
|-------------|----------------|
| `created_at` | Parsed via moment.js, converted to ISO 8601 |
| `eventTime` | Overwrites `created_at`, then deleted |
| `glucose`, `targetTop`, `targetBottom` | `Number()` cast |
| `carbs`, `insulin`, `duration`, `percent`, `absolute`, `relative`, `preBolus` | `Number()` cast |
| Fields with value 0 or NaN | Deleted (except `duration`, `absolute`) |
| `eventType: "Announcement"` | Sets `isAnnouncement: true` flag |

**Indexed Fields:**
```javascript
indexedFields: [
  'created_at', 'eventType', 'insulin', 'carbs',
  'glucose', 'enteredBy', 'boluscalc.foods._id',
  'notes', 'NSCLIENT_ID', 'percent', 'absolute', 'duration',
  { 'eventType': 1, 'duration': 1, 'created_at': 1 }
]
```

---

## 2. WebSocket Real-Time Protocol

**Source:** `lib/server/websocket.js`

### 2.1 Supported Collections

```javascript
var supportedCollections = {
  'treatments': env.treatments_collection,
  'entries': env.entries_collection,
  'devicestatus': env.devicestatus_collection,
  'profile': env.profile_collection,
  'food': env.food_collection,
  'activity': env.activity_collection
};
```

### 2.2 Socket Events

| Event | Direction | Purpose | Payload |
|-------|-----------|---------|---------|
| `authorize` | Client→Server | Authenticate connection | `{ client, secret, token, history, status }` |
| `connected` | Server→Client | Confirm auth success | - |
| `dataUpdate` | Server→Client | Push delta updates | `{ delta, status? }` |
| `retroUpdate` | Server→Client | Historical devicestatus | `{ devicestatus }` |
| `loadRetro` | Client→Server | Request historical data | `{ opts }` |
| `dbAdd` | Client→Server | Insert document(s) | `{ collection, data }` |
| `dbUpdate` | Client→Server | Update document | `{ collection, _id, data }` |
| `dbUpdateUnset` | Client→Server | Remove fields | `{ collection, _id, data }` |
| `dbRemove` | Client→Server | Delete document | `{ collection, _id }` |
| `clients` | Server→All | Broadcast watcher count | `number` |

### 2.3 Deduplication Logic (WebSocket)

**Treatment Deduplication (2-tier):**

1. **Exact Match:** `{ NSCLIENT_ID }` or `{ created_at, eventType }`
2. **Similar Match (±2 seconds):**
   ```javascript
   var query_similiar = {
     created_at: { 
       $gte: new Date(timestamp - 2000).toISOString(), 
       $lte: new Date(timestamp + 2000).toISOString() 
     }
   };
   // Plus matching: insulin, carbs, percent, absolute, duration, NSCLIENT_ID
   ```

**DeviceStatus Deduplication:**
- Exact: `{ NSCLIENT_ID }` or `{ created_at }`
- No similarity matching

**EventType Default:**
```javascript
if (data.collection === 'treatments' && !('eventType' in data.data)) {
  data.data.eventType = '<none>';
}
```

### 2.4 Authorization Resolution

```javascript
verifyAuthorization(message, ip, function verified(err, authorization) {
  // authorization = {
  //   read: boolean,
  //   write: boolean,
  //   write_treatment: boolean
  // }
});
```

**Permission Checks:**
- `api:*:read` → `read`
- `api:*:create,update,delete` → `write`
- `api:treatments:create,update,delete` → `write_treatment`

---

## 3. Authorization System

**Source:** `lib/authorization/index.js`

### 3.1 Token Resolution Flow

```
Request
   ↓
Extract JWT (Bearer header) or API_SECRET
   ↓
Check delay list (brute-force protection)
   ↓
No auth? → Return default roles
   ↓
Valid API_SECRET? → Return full * permissions
   ↓
Valid JWT? → Decode accessToken claim
   ↓
Resolve accessToken → Subject + Roles → Shiro permissions
```

### 3.2 Authentication Methods

| Method | Source | Permissions |
|--------|--------|-------------|
| API_SECRET | `api-secret` header or `secret` param | Full `*` |
| JWT | `Authorization: Bearer` or `token` param | Role-based |
| Access Token | Direct token string | Mapped to subject roles |
| None | - | Default roles |

### 3.3 Shiro Permission Model

**Format:** `area:collection:operation`

```javascript
authorization.checkMultiple('api:*:read', shiros)
authorization.checkMultiple('api:treatments:create,update,delete', shiros)
```

**Key Functions:**
- `resolve(data, callback)` → Returns `{ shiros: [ShiroTrie] }`
- `checkMultiple(permission, shiros)` → Boolean
- `isPermitted(permission)` → Express middleware

### 3.4 Brute-Force Protection

**Source:** `lib/authorization/delaylist.js`

Failed authentication attempts trigger progressive delays per IP address.

---

## 4. API v3 Implementation Details

**Source:** `lib/api3/swagger.yaml`, `lib/api3/index.js`

### 4.1 Identifier Generation

The `identifier` field is server-assigned. For documents without `identifier`:
- Fallback to internal `_id` for addressing
- Deduplication uses collection-specific rules

### 4.2 Immutable Fields

**Source:** `lib/api3/generic/update/validate.js:21-22`

The following fields are enforced as immutable via server-side validation. Attempts to modify return HTTP 400:

```javascript
const immutable = ['identifier', 'date', 'utcOffset', 'eventType', 'device', 'app',
  'srvCreated', 'subject', 'srvModified', 'modifiedBy', 'isValid'];
```

| Field | Set By | Enforcement |
|-------|--------|-------------|
| `identifier` | Server (auto) | Reject* |
| `date` | Client (on create only) | Reject |
| `utcOffset` | Parsed from date | Reject |
| `eventType` (treatments) | Client (on create only) | Reject |
| `device` | Client (on create only) | Reject |
| `app` | Client (on create only) | Reject |
| `srvCreated` | Server | Reject |
| `srvModified` | Server | Server overwrites |
| `subject` | Server (from JWT) | Reject |
| `modifiedBy` | Server | Server overwrites |
| `isValid` | Server (delete operations) | Reject |

*Exception: identifier changes allowed during deduplication for API v1 docs.

### 4.3 Soft Delete

DELETE operations set `isValid = false` rather than removing documents. Use `permanent=true` query param for hard delete.

### 4.4 History Sync

The `/history` endpoint returns all changes since a timestamp, including:
- Inserted documents
- Updated documents (full document returned)
- Deleted documents (`isValid: false`)

Response includes `Last-Modified` header for next sync.

---

## 5. Controller Sync Identity Patterns

### 5.1 Identity Field Usage (from source + schema analysis)

| Controller | Primary ID Field | Secondary Fields | Dedup Strategy |
|------------|-----------------|------------------|----------------|
| **AAPS** | `identifier` | - | API v3 native |
| **Loop** | `pumpId` | `pumpType`, `pumpSerial` | Pump-centric |
| **xDrip** | `uuid` | - | Client-assigned UUID |
| **NSClient** | `NSCLIENT_ID` | - | WebSocket-specific |
| **Generic** | - | `created_at` + `eventType` | Fallback |

### 5.2 Gap Analysis

| Gap ID | Description | Impact |
|--------|-------------|--------|
| GAP-001 | No `superseded` / `superseded_by` fields | Cannot track override chains |
| GAP-002 | Controller sync identity not standardized | Multiple dedup paths |
| GAP-003 | No formal schema validation layer | Client-dependent validation |
| GAP-004 | `eventType` is free-form string | No enumeration enforcement |
| GAP-005 | No authority field on documents | Cannot determine writer type |

---

## 6. Event Bus Architecture

**Source:** `lib/bus.js`, various modules

### 6.1 Key Events

| Event | Emitter | Purpose |
|-------|---------|---------|
| `data-received` | treatments, websocket | Trigger data reload |
| `data-update` | treatments, websocket | Notify of specific changes |
| `data-processed` | data processing | Trigger WebSocket broadcast |
| `admin-notify` | authorization | Admin notification |
| `teardown` | server | Shutdown signal |

### 6.2 Data Update Payload

```javascript
ctx.bus.emit('data-update', {
  type: 'treatments',    // collection name
  op: 'update' | 'remove',
  changes: [...],        // processed documents
  count: number          // for remove operations
});
```

---

## 7. Key Source File Registry

| File | Purpose | Alignment Relevance |
|------|---------|---------------------|
| `lib/server/treatments.js` | Treatment CRUD, validation | **Critical** - Field transformations |
| `lib/server/websocket.js` | Real-time sync protocol | **Critical** - Dedup logic |
| `lib/authorization/index.js` | Auth system | **High** - Permission model |
| `lib/api3/swagger.yaml` | OpenAPI spec | **Critical** - API contract |
| `lib/api3/generic/` | CRUD operations | High - API behavior |
| `lib/profilefunctions.js` | Profile loading | Medium - Profile handling |
| `lib/server/bootevent.js` | Server initialization | Medium - Boot sequence |
| `lib/bus.js` | Event bus | Medium - Integration points |

---

## 8. Recommendations for Alignment Work

### 8.1 Immediate Actions

1. **Document dedup rules formally** - Create `docs/20-specs/nightscout-dedup.md` with all deduplication pathways
2. **Extract event types** - Create `docs/10-domain/nightscout-event-types.md` with enumeration from source
3. **Map immutable fields** - Document which fields are locked after creation

### 8.2 Schema Proposals

1. **Authority tracking** - Add `issuedBy` field with writer type/ID
2. **Override chaining** - Add `supersedes` / `supersededBy` fields
3. **Sync identity standardization** - Define `syncIdentifier` convention

### 8.3 Integration Points

For alignment with Loop/AAPS/Trio:
- Map each controller's identity field to common `syncIdentifier`
- Document timestamp semantics (event time vs server time)
- Clarify authority hierarchy for conflict resolution

---

## Cross-References

- [cgm-remote-monitor Documentation Inventory](./external-inventories/cgm-remote-monitor-docs.md)
- [Nightscout Data Model](../10-domain/nightscout-data-model.md)
- [API v3 Summary](../../specs/openapi/nightscout-api3-summary.md)
- [Authority Model](../10-domain/authority-model.md)

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial synthesis from source code analysis |
