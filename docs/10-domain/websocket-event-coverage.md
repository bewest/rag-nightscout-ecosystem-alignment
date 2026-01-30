# WebSocket Event Coverage: Nightscout Socket.IO vs REST API

> **Date**: 2026-01-30  
> **Status**: Complete  
> **Domain**: Nightscout API / Real-time Sync

---

## Executive Summary

Nightscout provides **two WebSocket channels** alongside the REST APIs for real-time data exchange. The legacy socket.io channel (v1) handles bidirectional CRUD operations, while the API v3 storage channel provides read-only event subscriptions.

| Channel | Namespace | Purpose | Auth Method |
|---------|-----------|---------|-------------|
| Legacy (v1) | `/` (root) | Bidirectional CRUD | `api-secret` hash |
| APIv3 Storage | `/storage` | Read-only events | `accessToken` |

---

## 1. Legacy WebSocket Channel (V1)

### Connection

```javascript
// Client connects to root namespace
const socket = io('https://nightscout.example.com');
```

### Authentication

```javascript
// websocket.js:584
socket.on('authorize', function authorize (message, callback) {
  // message format:
  // {
  //   client: 'web' | 'phone' | 'pump',
  //   secret: 'sha1_hash_of_api_secret',
  //   history: 48,  // hours of history to receive
  //   status: true  // include server status
  // }
});
```

### Inbound Events (Client → Server)

| Event | Description | Required Auth |
|-------|-------------|---------------|
| `authorize` | Authenticate and join data channel | None (provides auth) |
| `loadRetro` | Request historical devicestatus | `read` |
| `dbAdd` | Insert new document | `write_treatment` or `write` |
| `dbUpdate` | Update existing document by `_id` | `write_treatment` or `write` |
| `dbUpdateUnset` | Unset fields from document | `write_treatment` or `write` |
| `dbRemove` | Delete document by `_id` | `write_treatment` or `write` |

### Outbound Events (Server → Client)

| Event | Description | Trigger |
|-------|-------------|---------|
| `connected` | Auth successful | After `authorize` |
| `dataUpdate` | Full or delta data | Initial + on changes |
| `retroUpdate` | Historical devicestatus | On `loadRetro` |
| `clients` | Connected client count | On connect/disconnect |

### Supported Collections

```javascript
// websocket.js:32-39
var supportedCollections = {
  'treatments': env.treatments_collection,
  'entries': env.entries_collection,
  'devicestatus': env.devicestatus_collection,
  'profile': env.profile_collection,
  'food': env.food_collection,
  'activity': env.activity_collection
};
```

### Deduplication Logic

```javascript
// websocket.js:364-374
// Treatments deduplication
if (data.data.NSCLIENT_ID) {
  query = { NSCLIENT_ID: data.data.NSCLIENT_ID };
} else {
  query = {
    created_at: data.data.created_at,
    eventType: data.data.eventType
  };
}
```

---

## 2. APIv3 Storage Channel

### Connection

```javascript
// Connect to /storage namespace
const socket = io('https://nightscout.example.com/storage');
```

### Authentication

```javascript
// Subscribe with accessToken
socket.emit('subscribe', { 
  accessToken: 'testadmin-ad3b1f9d7b3f59d5',
  collections: ['entries', 'treatments']
}, function (data) {
  if (data.success) {
    console.log('subscribed for collections', data.collections);
  }
});
```

### Inbound Events (Client → Server)

| Event | Description |
|-------|-------------|
| `subscribe` | Authenticate and subscribe to collections |

### Outbound Events (Server → Client)

| Event | Description | Payload |
|-------|-------------|---------|
| `create` | Document created | `{ colName, doc }` |
| `update` | Document updated | `{ colName, doc }` |
| `delete` | Document deleted | `{ colName, identifier }` |

### Key Limitation

> **Important**: Only changes made via APIv3 are being broadcasted. All direct database or APIv1 modifications are not included by this channel.

---

## 3. REST API Comparison

### API v1 Endpoints

| Method | Endpoint | WebSocket Equivalent |
|--------|----------|---------------------|
| GET | `/api/v1/treatments` | `dataUpdate` (initial) |
| POST | `/api/v1/treatments` | `dbAdd` |
| PUT | `/api/v1/treatments` | `dbUpdate` |
| DELETE | `/api/v1/treatments/:id` | `dbRemove` |

### API v3 Endpoints

| Method | Endpoint | WebSocket Event |
|--------|----------|-----------------|
| GET | `/api/v3/{collection}` | (no equivalent) |
| POST | `/api/v3/{collection}` | Triggers `create` |
| PUT | `/api/v3/{collection}/{id}` | Triggers `update` |
| PATCH | `/api/v3/{collection}/{id}` | Triggers `update` |
| DELETE | `/api/v3/{collection}/{id}` | Triggers `delete` |

---

## 4. Controller Usage Patterns

### Loop

| Channel | Usage |
|---------|-------|
| REST API v1 | Primary upload method (POST) |
| WebSocket | Not used for upload |

**Source**: Loop uses NightscoutKit library which calls REST endpoints.

### AAPS

| Channel | Usage |
|---------|-------|
| REST API v3 | Primary (NSClientV3) |
| REST API v1 | Fallback (NSClient) |
| WebSocket | Optional for real-time updates |

**Source**: `NSAndroidClientImpl.kt` uses REST calls.

### Trio

| Channel | Usage |
|---------|-------|
| REST API v1 | Primary upload |
| WebSocket | Not used |

**Source**: `NightscoutAPI.swift` uses HTTP methods.

### xDrip+

| Channel | Usage |
|---------|-------|
| REST API v1 | Primary |
| WebSocket | Not used |

---

## 5. Event Flow Diagrams

### Write via Legacy WebSocket

```
Client                          Nightscout
  │                                │
  │──── authorize ────────────────>│
  │<─── connected ─────────────────│
  │                                │
  │──── dbAdd { treatments } ─────>│
  │                                │ (insert to MongoDB)
  │                                │ (emit data-update event)
  │<─── callback([doc]) ───────────│
  │                                │
  │<─── dataUpdate (to all) ───────│ (broadcast to DataReceivers)
```

### Write via REST, Subscribe via APIv3

```
Client A (REST)             Nightscout              Client B (WS)
    │                          │                         │
    │                          │<── subscribe ───────────│
    │                          │─── success ────────────>│
    │                          │                         │
    │── POST /api/v3/entries ─>│                         │
    │<── 201 Created ──────────│                         │
    │                          │─── create { doc } ─────>│
```

---

## 6. Gap Analysis

### GAP-API-013: Legacy WebSocket Not Used by Controllers

**Description**: All major controllers (Loop, AAPS, Trio) use REST APIs for upload. The legacy WebSocket `dbAdd`/`dbUpdate` events are primarily used by the web interface.

**Impact**: 
- Real-time sync benefits are underutilized
- Controllers poll REST endpoints instead of subscribing

**Remediation**: Document WebSocket as optional performance optimization.

---

### GAP-API-014: APIv3 WebSocket Doesn't Capture V1 Changes

**Description**: The APIv3 `/storage` channel only broadcasts changes made via APIv3 REST endpoints. Changes via APIv1 or WebSocket v1 are not included.

**Affected Systems**: Nightscout, any client using APIv3 WebSocket

**Source**: `lib/api3/doc/socket.md` - explicit limitation note

**Impact**: Clients subscribed to APIv3 storage miss updates from Loop (uses v1 API).

**Remediation**: Consolidate event bus to broadcast all changes regardless of entry point.

---

### GAP-API-015: No Alarm/Notification WebSocket Channel

**Description**: Alarm state changes (urgent high, stale data, etc.) are not exposed via WebSocket events.

**Impact**: Follower apps must poll for alarm state.

**Remediation**: Add `alarm` event to storage channel.

---

## 7. Source Files Analyzed

| File | Lines | Purpose |
|------|-------|---------|
| `lib/server/websocket.js` | 649 | Legacy WebSocket implementation |
| `lib/api3/doc/socket.md` | 100+ | APIv3 WebSocket documentation |
| `lib/api3/storage/mongoCollection/utils.js` | 170 | Deduplication logic |
| `lib/server/server.js` | 71 | WebSocket initialization |

---

## 8. Terminology Mapping

| Concept | WebSocket v1 | APIv3 WebSocket | REST |
|---------|--------------|-----------------|------|
| Create | `dbAdd` | `create` (outbound) | POST |
| Update | `dbUpdate` | `update` (outbound) | PUT/PATCH |
| Delete | `dbRemove` | `delete` (outbound) | DELETE |
| Read | `dataUpdate` | (subscribe) | GET |
| Auth | `authorize` | `subscribe` | Header/Query |

---

## 9. Requirements

### REQ-API-020: Document WebSocket Capabilities

**Statement**: Nightscout documentation SHOULD clearly describe both WebSocket channels and their limitations.

**Rationale**: Developers need to understand which channel suits their use case.

**Verification**: Documentation exists for both `/` and `/storage` namespaces.

**Gap**: GAP-API-013

---

### REQ-API-021: Cross-Channel Event Propagation

**Statement**: Changes via any entry point (v1 REST, v3 REST, WebSocket v1) SHOULD be broadcast on all WebSocket channels.

**Rationale**: Clients shouldn't need to know which API was used for the original write.

**Verification**: Create via v1 POST; verify `/storage` channel receives `create` event.

**Gap**: GAP-API-014

---

### REQ-API-022: WebSocket Rate Limiting

**Statement**: WebSocket write operations SHOULD be rate-limited to prevent abuse.

**Rationale**: Prevent DOS via rapid `dbAdd` events.

**Verification**: Send 100 `dbAdd` events in 1 second; verify rate limit response.

**Gap**: N/A (best practice)

---

## 10. Test Scenarios

### Scenario 1: WebSocket v1 CRUD

```yaml
given: Client authenticated via WebSocket authorize
when: Client sends dbAdd for treatment
then: 
  - Document inserted in MongoDB
  - Callback returns document with _id
  - dataUpdate broadcast to all DataReceivers
```

### Scenario 2: APIv3 REST + Storage Subscribe

```yaml
given: Client B subscribed to /storage for treatments
when: Client A POSTs treatment via /api/v3/treatments
then:
  - Client B receives create event with document
  - Event payload includes colName and doc
```

### Scenario 3: Cross-API Event Gap

```yaml
given: Client B subscribed to /storage for treatments
when: Client A POSTs treatment via /api/v1/treatments
then:
  - Client B does NOT receive create event (GAP-API-011)
```
