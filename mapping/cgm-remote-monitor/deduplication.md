# cgm-remote-monitor: Deduplication Strategies

**Source**: `externals/cgm-remote-monitor` (wip/bewest/mongodb-5x)  
**Verified**: 2026-01-20

## Overview

The server implements multi-client deduplication to handle different identity field patterns from various AID controllers.

## Client Identity Fields

| Client | Primary Field | Secondary Fields | API |
|--------|---------------|------------------|-----|
| **Loop** | `syncIdentifier` | - | v1 |
| **Trio** | `id` | `syncIdentifier` (via LoopKit) | v1 |
| **AAPS v3** | `identifier` | calculated from device+date+eventType | v3 |
| **AAPS v1** | composite | `pumpId`+`pumpType`+`pumpSerial` | v1 |
| **xDrip+** | `uuid` | - | v1 |
| **xDrip4iOS** | `uuid` | - | v1 |

## v3 Identifier Calculation

Per `lib/api3/shared/operationTools.js:97-107`:

```javascript
function calculateIdentifier(doc) {
  let key = doc.device + '_' + doc.date;
  if (doc.eventType) {
    key += '_' + doc.eventType;
  }
  return uuid.v5(key, uuidNamespace);
}
```

**Important**: `pumpId`/`pumpType`/`pumpSerial` are NOT included in identifier - they're preserved as metadata only.

## v3 Fallback Deduplication

Per `lib/api3/storage/mongoCollection/utils.js:130-169`:

```javascript
function identifyingFilter(identifier, doc, dedupFallbackFields) {
  // Priority 1: Exact identifier match
  if (identifier) {
    filterItems.push({ identifier: identifier });
  }
  
  // Priority 2: Fallback to _id if identifier looks like ObjectID
  if (checkForHexRegExp.test(identifier)) {
    filterItems.push({ identifier: { $exists: false }, _id: new ObjectID(identifier) });
  }
  
  // Priority 3: Fallback dedup fields (all must match)
  if (dedupFallbackFields.length > 0) {
    dedupFilterItems.push({ identifier: { $exists: false } });
    filterItems.push({ $and: dedupFilterItems });
  }
  
  return { $or: filterItems };
}
```

## v1 Deduplication

### Entries

Per `lib/server/entries.js:111-120`:

```javascript
var query = (doc.sysTime && doc.type) 
  ? { sysTime: doc.sysTime, type: doc.type } 
  : doc;

return {
  updateOne: {
    filter: query,
    update: { $set: doc },
    upsert: true
  }
};
```

### Treatments

Per `lib/server/treatments.js:54-58`:

```javascript
replaceOne: {
  filter: { created_at: results.created_at, eventType: obj.eventType },
  replacement: obj,
  upsert: true
}
```

## Response Ordering (Critical for Loop)

Loop caches `syncIdentifier[i] → response[i]._id` mapping by array position.

### Guarantee Mechanism

Per `lib/server/entries.js:123` and `lib/server/treatments.js:62`:

```javascript
api().bulkWrite(bulkOps, { ordered: true }, ...)
```

**`ordered: true`** ensures:
1. Operations processed sequentially
2. Results returned in same order as input
3. `response[i]` corresponds to `request[i]`

### Result Mapping

Per `lib/server/treatments.js:69-73`:

```javascript
if (bulkResult && bulkResult.upsertedIds) {
  Object.keys(bulkResult.upsertedIds).forEach(function(index) {
    objOrArray[index]._id = bulkResult.upsertedIds[index];
  });
}
fn(null, objOrArray);  // Original array with _ids assigned by position
```

## WebSocket Deduplication

Per `lib/server/websocket.js:364-467`:

### Treatments

Two-level deduplication with 2-second window (`maxtimediff = 2000ms`):

1. **Exact match**: `created_at` + `eventType`
2. **Similar match**: Time window (±2 secs) + eventType + optional fields (insulin, carbs, NSCLIENT_ID)

### DeviceStatus

Per `lib/server/websocket.js:469-515`:

- Match on `NSCLIENT_ID` or `created_at`

## Cross-Client Isolation

Different identity field schemes naturally isolate duplicates:

| Controller A | Controller B | Conflict Risk |
|--------------|--------------|---------------|
| Loop (syncIdentifier) | Trio (id) | LOW |
| AAPS (identifier) | Loop (syncIdentifier) | LOW |
| xDrip+ (uuid) | AAPS (identifier) | LOW |

## Test Coverage

| Test File | Lines | Purpose |
|-----------|-------|---------|
| `tests/api.deduplication.test.js` | 388 | AAPS, Loop, Trio patterns |
| `tests/api.partial-failures.test.js` | 496 | Response ordering for Loop |
| `tests/api.aaps-client.test.js` | 331 | AAPS-specific formats |

## Requirements Derived

| ID | Requirement | Source |
|----|-------------|--------|
| REQ-NS-DEDUP-001 | Must recognize `syncIdentifier` for Loop dedup | Tests |
| REQ-NS-DEDUP-002 | Must recognize `identifier` for AAPS v3 dedup | Tests |
| REQ-NS-DEDUP-003 | Must preserve response ordering for batch POSTs | Loop requires |
| REQ-NS-DEDUP-004 | Must support 2-second window for WebSocket dedup | `websocket.js:310` |
| REQ-NS-DEDUP-005 | Must fallback to created_at+eventType for v1 | `treatments.js` |
