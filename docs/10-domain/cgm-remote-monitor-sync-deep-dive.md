# cgm-remote-monitor Sync/Upload Deep Dive

This document analyzes the synchronization and upload mechanisms of cgm-remote-monitor, focusing on real-time data flow, Socket.IO architecture, and sync identity handling. The sync layer bridges client uploads to database persistence and broadcasts updates to connected viewers.

## Overview

### Key Components

| Component | File | Lines | Purpose |
|-----------|------|-------|---------|
| WebSocket Server | `lib/server/websocket.js` | 649 | Socket.IO initialization, broadcasts |
| Event Bus | `lib/bus.js` | ~50 | Internal pub/sub for data events |
| Boot Orchestration | `lib/server/bootevent.js` | 382 | Startup, listener setup |
| Entries Handler | `lib/server/entries.js` | 194 | CGM entry storage |
| Treatments Handler | `lib/server/treatments.js` | 291 | Treatment record storage |
| DeviceStatus Handler | `lib/server/devicestatus.js` | 144 | Device status tracking |
| Delta Calculator | `lib/calcdelta.js` | ~200 | Compute data differences |
| Identifier Resolver | `lib/api3/shared/operationTools.js` | ~50 | UUID v5 sync identity |

### Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Client Upload                                │
│  (Loop, xDrip+, AAPS, Trio, browsers)                               │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      REST API Layer                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │
│  │ /api/v1/    │  │ /api/v3/    │  │ /api/v3/    │                  │
│  │ entries     │  │ treatments  │  │ devicestatus│                  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                  │
└─────────┼────────────────┼────────────────┼─────────────────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Storage Layer                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  resolveIdentifier() → UUID v5 from device+date+eventType   │    │
│  │  identifyingFilter() → 3-tier dedup query                   │    │
│  │  UPSERT semantics (replace if exists)                       │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      MongoDB                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │
│  │  entries    │  │ treatments  │  │ devicestatus│                  │
│  └─────────────┘  └─────────────┘  └─────────────┘                  │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Event Bus (ctx.bus)                              │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │  data-received → data-loaded → data-processed → broadcast  │     │
│  └────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   WebSocket Broadcast                                │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │  calcDelta() → compress() → io.to('DataReceivers').emit()  │     │
│  └────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Connected Clients                               │
│  (browsers, LoopFollow, Nightguard, etc.)                           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Socket.IO Architecture

### Initialization

**File**: `lib/server/websocket.js:74-90`

```javascript
io = require('socket.io')({log level: 0}).listen(server, {
  allowEIO3: true,              // Engine.IO v3 compatibility
  transports: ["polling", "websocket"],
  perMessageDeflate: {
    threshold: 512              // Compress messages > 512 bytes
  },
  httpCompression: {
    threshold: 512              // Compress HTTP responses > 512 bytes
  }
});
```

### Namespaces and Rooms

| Namespace | Room | Purpose |
|-----------|------|---------|
| `/` (default) | `DataReceivers` | Main data broadcast channel |
| `/alarm` | - | Alarm notifications |
| `/storage` | Per-collection | CRUD change notifications |

### Event Types

#### Server → Client Events

| Event | Source | Payload | Description |
|-------|--------|---------|-------------|
| `dataUpdate` | websocket.js:136 | Delta object | Incremental data updates |
| `retroUpdate` | websocket.js:193 | `{devicestatus: [...]}` | Historical devicestatus |
| `connected` | websocket.js:594 | - | Authorization success |
| `clients` | websocket.js:150 | Number | Connected client count |
| `alarm` | alarmSocket.js:183 | Alarm details | Warning alarms |
| `urgent_alarm` | alarmSocket.js:186 | Alarm details | Urgent alarms |
| `clear_alarm` | alarmSocket.js:180 | - | Alarm cleared |
| `announcement` | alarmSocket.js:189 | Message | General announcements |

#### Client → Server Events

| Event | Handler | Purpose |
|-------|---------|---------|
| `authorize` | websocket.js:584 | Client authentication |
| `loadRetro` | websocket.js:188 | Request historical data |
| `ack` | alarmSocket.js:83 | Acknowledge alarm |
| `dbAdd` | websocket.js:307 | Insert document |
| `dbUpdate` | websocket.js:400 | Update document |
| `dbUpdateUnset` | websocket.js:480 | Remove field from document |
| `dbRemove` | websocket.js:537 | Delete document |

### Authorization Flow

**File**: `lib/server/websocket.js:584-601`

```
Client connects → emits 'authorize' with secret/token
                           ↓
Server verifies → api_secret hash OR JWT token OR accessToken
                           ↓
Success → socket.join('DataReceivers') + emit 'connected'
Failure → connection remains limited (no data broadcast)
```

---

## Event Bus Architecture

### Bus Creation

**File**: `lib/bus.js`

The event bus is a Node.js EventEmitter that coordinates data flow:

```javascript
ctx.bus = require('../bus')(env.settings, ctx);
```

### Core Events

| Event | Emitter | Listener | Description |
|-------|---------|----------|-------------|
| `tick` | bus.js (timer) | bootevent.js | Heartbeat for data refresh |
| `data-received` | storage handlers | bootevent.js | New data uploaded |
| `data-loaded` | dataloader | bootevent.js | Data fetched from DB |
| `data-processed` | bootevent.js | websocket.js | Ready for broadcast |
| `data-update` | storage handlers | websocket.js | Direct update notification |

### Event Propagation Sequence

**File**: `lib/server/bootevent.js:275-304`

```
1. tick event (every HEARTBEAT seconds)
      ↓
2. updateData() → ctx.dataloader.update()
      ↓
3. data-loaded event (DB fetch complete)
      ↓
4. ctx.plugins.setProperties() → process plugins
      ↓
5. data-processed event
      ↓
6. websocket.update() → calcDelta() → broadcast
```

---

## Sync Identity System

### UUID v5 Generation

**File**: `lib/api3/shared/operationTools.js:114`

```javascript
function resolveIdentifier(doc, dedupFallbackFields) {
  const input = [doc.device, doc.date, doc.eventType].join('|');
  return uuidv5(input, NIGHTSCOUT_NAMESPACE);
}
```

### Three-Tier Deduplication

**File**: `lib/api3/storage/mongoCollection/utils.js:130`

```javascript
function identifyingFilter(identifier, doc, dedupFallbackFields) {
  return {
    $or: [
      // Tier 1: Exact identifier match
      { identifier: identifier },
      
      // Tier 2: APIv1 _id compatibility
      { _id: identifier },
      
      // Tier 3: Fallback field matching
      {
        ...buildFieldMatch(doc, dedupFallbackFields),
        identifier: { $exists: false }
      }
    ]
  };
}
```

### Collection Dedup Fields

**File**: `lib/api3/generic/setup.js`

| Collection | Dedup Fields | Identifier Components |
|------------|--------------|----------------------|
| entries | `['date', 'type']` | device + date + type |
| treatments | `['created_at', 'eventType']` | device + created_at + eventType |
| devicestatus | `['created_at', 'device']` | created_at + device |
| food | `['created_at']` | created_at |
| profile | `['created_at']` | created_at |

---

## Upload Handlers

### Entries Upload (v1 API)

**File**: `lib/api/entries/index.js:263`

```javascript
function insert_entries(req, res) {
  var entries = req.body;
  if (!Array.isArray(entries)) entries = [entries];
  
  entries = entries.map(purifier.purifyObject);
  
  ctx.entries.create(entries, function(err, result) {
    ctx.bus.emit('data-received');
    // ... response
  });
}
```

**Characteristics**:
- Accepts single entry or array
- Purifies input for sanitization
- No explicit sync identity (relies on DB index)
- Emits `data-received` to trigger reload

### Treatments Upload (v1 API)

**File**: `lib/api/treatments/index.js:104`

```javascript
function post_response(req, res) {
  var treatments = req.body;
  if (!Array.isArray(treatments)) treatments = [treatments];
  
  treatments.forEach(t => {
    if (!t.created_at) t.created_at = new Date().toISOString();
    purifier.purifyObject(t);
  });
  
  ctx.treatments.create(treatments, function(err, result) {
    ctx.bus.emit('data-received');
    // ... response
  });
}
```

**Characteristics**:
- Auto-generates `created_at` if missing
- No deduplication at API level
- Storage layer handles UPSERT

### v3 API Create Operation

**File**: `lib/api3/generic/create/operation.js:15`

```javascript
async function create(doc, options) {
  const identifier = resolveIdentifier(doc, dedupFallbackFields);
  const filter = identifyingFilter(identifier, doc, dedupFallbackFields);
  
  const existing = await collection.findOne(filter);
  
  if (existing) {
    // UPSERT: Replace existing document
    doc._id = existing._id;
    await collection.replaceOne({ _id: existing._id }, doc);
  } else {
    // INSERT: New document
    doc.identifier = identifier;
    doc.srvCreated = Date.now();
    await collection.insertOne(doc);
  }
  
  doc.srvModified = Date.now();
}
```

---

## Delta Compression

### Delta Calculation

**File**: `lib/calcdelta.js`

The delta system minimizes bandwidth by only sending changes:

```javascript
function calcDelta(oldData, newData) {
  const delta = {};
  
  // Compare 5 compressible arrays
  ['sgvs', 'treatments', 'mbgs', 'cals', 'devicestatus'].forEach(key => {
    const added = findNewItems(oldData[key], newData[key]);
    if (added.length > 0) {
      delta[key] = added;
    }
  });
  
  return { delta: Object.keys(delta).length > 0, ...delta };
}
```

### Comparison Keys

| Collection | Comparison Key | Matching Logic |
|------------|---------------|----------------|
| sgvs | `mills + sgv/mgdl` | Timestamp + value |
| treatments | Object hash | Deep comparison on key fields |
| mbgs | `mills + mgdl` | Timestamp + value |
| cals | `mills` | Timestamp only |
| devicestatus | `mills + device` | Timestamp + device name |

### Three-Level Compression

1. **Data Diffing**: Only changed records sent (delta)
2. **Socket Deflate**: Messages > 512 bytes compressed
3. **HTTP Gzip**: HTTP responses > 512 bytes compressed

---

## Retroactive Data Loading

### Purpose

LoadRetro enables viewing historical device status when browsing past data.

### Client Request

**File**: `lib/client/index.js:1065-1088`

```javascript
function loadRetroIfNeeded() {
  if (retroAge > 3 * 60 * 1000) {  // Data older than 3 minutes
    if (timeSinceLastRequest > 30000) {  // Throttle: 30 seconds
      socket.emit('loadRetro');
    }
  }
}
```

### Server Response

**File**: `lib/server/websocket.js:188-195`

```javascript
socket.on('loadRetro', function(callback) {
  socket.compress(true).emit('retroUpdate', {
    devicestatus: lastData.devicestatus
  });
  callback && callback();
});
```

### Data Scope

| Parameter | Default | Max | Notes |
|-----------|---------|-----|-------|
| DEVICESTATUS_DAYS | 1 | 2 | Days of history |
| Stale threshold | 3 min | - | When to request refresh |
| Request throttle | 30 sec | - | Minimum between requests |
| Cache timeout | 5 min | - | Clear unused retro data |

**Only devicestatus is included** - entries and treatments come through standard `dataUpdate`.

---

## Gap Analysis

### GAP-SYNC-008: No Cross-Client Sync Conflict Resolution

**Scenario**: Multiple clients uploading conflicting data simultaneously.

**Issue**: The UPSERT system replaces documents based on sync identity, but provides no conflict resolution or merge strategy. Last-write-wins may cause data loss.

**Affected Systems**: Loop + xDrip+ uploading same treatments, AAPS + Trio dual upload.

**Impact**: Potential data loss when multiple AID systems are active.

**Remediation**: Implement versioning or conflict detection with client notification.

---

### GAP-SYNC-009: V1 API Lacks Identifier Field

**Scenario**: Legacy clients using v1 API endpoints.

**Issue**: V1 API does not generate or require the `identifier` field. Deduplication relies on legacy field matching only, which may fail for edge cases.

**Affected Systems**: Older Loop versions, legacy uploaders, direct API integrations.

**Impact**: Duplicate records may be created if dedup fields don't match exactly.

**Remediation**: Backfill `identifier` field during v1 uploads, document migration path.

---

### GAP-SYNC-010: No Sync Status Feedback

**Scenario**: Client needs confirmation of successful sync.

**Issue**: Upload endpoints return HTTP 200 but provide no sync status, conflict detection, or guidance on retries. Clients cannot distinguish between insert and update.

**Affected Systems**: All uploading clients (Loop, AAPS, xDrip+, Trio).

**Impact**: Clients may retry unnecessarily or fail to detect sync failures.

**Remediation**: Return sync metadata: `{inserted: N, updated: M, conflicts: [...]}`.

---

## Recommendations

### 1. Document WebSocket API

Create OpenAPI-style documentation for Socket.IO events, including:
- Event names and payloads
- Authentication requirements
- Error handling

**Priority**: High (enables third-party integration)

### 2. Standardize Sync Identity Across v1/v3

Ensure all API versions generate consistent `identifier` fields:
- V1: Add identifier generation to upload handlers
- Document identifier algorithm for client implementers

**Priority**: High (prevents duplicates)

### 3. Add Sync Status Response

Enhance upload responses to include:
```json
{
  "status": "ok",
  "inserted": 1,
  "updated": 0,
  "identifier": "uuid-v5-value"
}
```

**Priority**: Medium (improves client reliability)

### 4. Implement Conflict Detection

Add optional conflict detection for multi-source scenarios:
- Track source device per document
- Warn on conflicting updates from different sources
- Provide conflict resolution callback

**Priority**: Medium (prevents data loss)

---

## Source Files Analyzed

| File | Lines | Key Content |
|------|-------|-------------|
| `lib/server/websocket.js` | 649 | Socket.IO, broadcasts, auth |
| `lib/server/bootevent.js` | 382 | Boot sequence, event listeners |
| `lib/bus.js` | ~50 | Event emitter |
| `lib/calcdelta.js` | ~200 | Delta compression |
| `lib/api/entries/index.js` | ~300 | V1 entries API |
| `lib/api/treatments/index.js` | ~200 | V1 treatments API |
| `lib/api3/generic/create/operation.js` | ~100 | V3 create with UPSERT |
| `lib/api3/shared/operationTools.js` | ~150 | Identifier resolution |
| `lib/api3/storage/mongoCollection/utils.js` | ~200 | Dedup filter |
| `lib/client/index.js` | ~1200 | Client-side loadRetro |

---

## Cross-References

- **API Layer**: [cgm-remote-monitor-api-deep-dive.md](./cgm-remote-monitor-api-deep-dive.md)
- **Plugin System**: [cgm-remote-monitor-plugin-deep-dive.md](./cgm-remote-monitor-plugin-deep-dive.md)
- **Database Layer**: [cgm-remote-monitor-database-deep-dive.md](./cgm-remote-monitor-database-deep-dive.md)
- **Terminology**: [terminology-matrix.md](../../mapping/cross-project/terminology-matrix.md)
