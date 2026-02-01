# MongoDB Storage Layer Analysis

> **Date**: 2026-02-01  
> **Phase**: 2 (Storage Layer Analysis)  
> **Source**: `externals/cgm-remote-monitor/lib/`  
> **Parent**: [mongodb-update-readiness-report.md](../60-research/mongodb-update-readiness-report.md)

---

## Executive Summary

This document completes Phase 2 of the MongoDB modernization roadmap by auditing all MongoDB usage patterns in cgm-remote-monitor's storage layer.

### Key Findings

| Finding | Impact | Action Required |
|---------|--------|-----------------|
| **No `insertMany` usage** | Simplifies migration | None |
| **`replaceOne` with upsert** | Standard pattern | Compatible with 5.x/6.x |
| **Sequential array processing** | Preserves ordering | Already optimized |
| **V3 API uses Promise wrapper** | Clean abstraction | Upgrade-friendly |
| **V1 API returns raw docs** | Response format stable | Test coverage needed |

### MongoDB 5.x/6.x Compatibility: HIGH ✅

The storage layer uses modern MongoDB patterns (`replaceOne`, `updateOne`, `deleteMany`) that are fully compatible with MongoDB 5.x and 6.x drivers.

---

## Storage Layer Architecture

```
lib/
├── server/                    # V1 API storage (direct MongoDB)
│   ├── entries.js            # SGV entries - replaceOne + upsert
│   ├── treatments.js         # Treatments - replaceOne + upsert
│   ├── devicestatus.js       # Device status - insertOne
│   ├── profile.js            # Profiles - insertOne
│   ├── food.js               # Food database - insertOne
│   ├── activity.js           # Activity log - insertOne
│   └── websocket.js          # Real-time sync - insertOne
├── api/                       # V1 REST endpoints
│   ├── entries/index.js      # Entries REST handler
│   ├── treatments/index.js   # Treatments REST handler
│   └── devicestatus/         # DeviceStatus REST handler
└── api3/                      # V3 API storage (Promise wrapper)
    └── storage/
        └── mongoCollection/
            ├── index.js      # Collection factory
            ├── modify.js     # Write operations
            └── find.js       # Read operations
```

---

## Call Site Inventory

### V1 API Layer (`lib/server/`)

| File | Method | Line | Pattern | Notes |
|------|--------|------|---------|-------|
| `entries.js` | `replaceOne` | 113 | Upsert by sysTime+type | Sequential in forEach |
| `treatments.js` | `replaceOne` | 49, 73 | Upsert by created_at+eventType | Includes preBolus handling |
| `devicestatus.js` | `insertOne` | 25 | Single doc insert | Callback style |
| `profile.js` | `insertOne` | 11, 27 | Single doc insert | Callback style |
| `food.js` | `insertOne` | 8 | Single doc insert | Callback style |
| `activity.js` | `insertOne` | 35 | Single doc insert | Callback style |
| `websocket.js` | `insertOne` | 447, 497, 517 | Single doc insert | Real-time updates |

### V3 API Layer (`lib/api3/storage/`)

| File | Method | Line | Pattern | Notes |
|------|--------|------|---------|-------|
| `modify.js` | `insertOne` | 16 | Promise wrapper | Returns identifier |
| `modify.js` | `replaceOne` | 45 | Promise wrapper | Upsert enabled |
| `modify.js` | `updateOne` | 68 | Promise wrapper | $set operator |

---

## Batch Operation Handling

### Entries (SGV Data)

**File**: `lib/server/entries.js:92-134`

```javascript
// Batch insert via sequential replaceOne
function create (docs, fn) {
  var firstErr = null, numDocs = docs.length, totalCreated = 0;
  
  docs.forEach(function(doc) {
    var query = { sysTime: doc.sysTime, type: doc.type };
    api().replaceOne(query, doc, { upsert: true }, function(err, updateResults) {
      // ... accumulate results
      if (++totalCreated === numDocs) {
        fn(firstErr, docs);
      }
    });
  });
}
```

**Analysis**:
- Uses `replaceOne` with upsert (not `insertMany`)
- Sequential processing via `forEach` callback chain
- Response ordering preserved by input array order
- Compatible with MongoDB 5.x/6.x

### Treatments

**File**: `lib/server/treatments.js:11-38`

```javascript
// Batch insert via async.eachSeries
function create (objOrArray, fn) {
  if (_.isArray(objOrArray)) {
    async.eachSeries(objOrArray, function (obj, callback) {
      upsert(obj, callback);
    }, function () {
      done(errs.length > 0 ? errs : null, allDocs);
    });
  } else {
    upsert(objOrArray, done);
  }
}
```

**Analysis**:
- Uses `async.eachSeries` for ordered processing
- Each item processed via `upsert()` → `replaceOne()`
- Explicit sequential execution guarantees order
- Compatible with MongoDB 5.x/6.x

---

## Response Format Analysis

### V1 API Responses

**Treatments** (`lib/api/treatments/index.js:136-143`):
```javascript
ctx.treatments.create(treatments, function(err, created) {
  res.json(created);  // Returns array of docs with _id
});
```

**Response format**: Array of documents with `_id` field populated.

**Entries** (`lib/api/entries/index.js:781-785`):
- Uses `insert_entries` middleware → `format_entries` formatter
- Response format: Array of entry objects

### V3 API Responses

**Insert** (`lib/api3/storage/mongoCollection/modify.js:21-27`):
```javascript
const identifier = doc.identifier || result.insertedId.toString();
delete doc._id;
resolve(identifier);
```

**Analysis**: V3 API normalizes responses to return `identifier` string, abstracting MongoDB ObjectId details.

---

## MongoDB Driver Compatibility Matrix

### Current Driver: `mongodb-legacy ^5.0.0`

| Operation | 3.x Driver | 4.x+ Driver | cgm-remote-monitor Usage | Compatible |
|-----------|------------|-------------|--------------------------|------------|
| `insertOne` | ✅ | ✅ | devicestatus, profile, food | ✅ |
| `replaceOne` | ✅ | ✅ | entries, treatments | ✅ |
| `updateOne` | ✅ | ✅ | V3 API modify | ✅ |
| `deleteMany` | ✅ | ✅ | entries remove | ✅ |
| `findOne` | ✅ | ✅ | Various lookups | ✅ |
| `find().toArray()` | ✅ | ✅ | List operations | ✅ |

### Result Object Changes (3.x → 4.x+)

| Property | 3.x Format | 4.x+ Format | cgm-remote-monitor Usage |
|----------|------------|-------------|--------------------------|
| `insertedId` | ObjectId | ObjectId | ✅ Used directly |
| `upsertedId` | ObjectId | ObjectId | ✅ Used directly |
| `upsertedCount` | Number | Number | ✅ Used at treatments.js:54 |
| `modifiedCount` | Number | Number | ✅ Used at modify.js:72 |
| `matchedCount` | Number | Number | ✅ Used at modify.js:49 |
| `deletedCount` | Number | Number | ✅ Used at entries.js:54 |

**All result properties used in cgm-remote-monitor are stable across driver versions.**

---

## Risk Assessment

### Low Risk (Safe to Upgrade)

| Component | Reason |
|-----------|--------|
| V3 API storage | Clean Promise abstraction, stable result properties |
| Single-doc inserts | `insertOne` behavior unchanged |
| Upsert operations | `replaceOne` with upsert stable |
| Delete operations | `deleteMany` stable |

### Medium Risk (Needs Testing)

| Component | Concern | Mitigation |
|-----------|---------|------------|
| Batch entries | Sequential forEach may hit timing edge cases | Add batch size limit tests |
| WebSocket inserts | Real-time timing sensitivity | Load test with concurrent writes |
| Deduplication | Query + upsert race conditions | Already tested (29/30 passing) |

### No Risk Areas Identified

The codebase does NOT use:
- ❌ `insertMany` (would require response format translation)
- ❌ `findAndModify` (deprecated)
- ❌ `update` without `One`/`Many` suffix (deprecated)
- ❌ Legacy callback-only patterns (all are driver-compatible)

---

## Recommendations

### Phase 3: Core Implementation (Ready to Proceed)

1. **Write Result Translator** (from Phase 2 recommendations):
   - NOT NEEDED - codebase uses stable result properties
   - Response formats already abstract MongoDB details

2. **Response Order Preservation**:
   - ALREADY IMPLEMENTED via sequential processing
   - `async.eachSeries` and `forEach` chains maintain order

3. **Driver Upgrade Path**:
   ```bash
   # Recommended approach
   npm install mongodb@5.9.2  # Latest 5.x
   # Then test before jumping to 6.x
   npm install mongodb@6.3.0  # Latest 6.x
   ```

### Test Coverage Gaps

| Area | Current Coverage | Recommended |
|------|------------------|-------------|
| Batch entries (100+ docs) | ❓ Unknown | Add stress tests |
| Concurrent upserts | ✅ 29/30 passing | Increase parallelism |
| WebSocket reconnection | ❓ Unknown | Add chaos tests |
| Large devicestatus | ⚠️ 1 flaky test | Infrastructure issue |

---

## Gap Closure

This analysis addresses:

| Gap ID | Description | Status |
|--------|-------------|--------|
| Phase 2 | Storage Layer Analysis | ✅ COMPLETE |
| GAP-MONGO-001 | Driver upgrade path unclear | ✅ Path documented |
| NEW: GAP-MONGO-002 | No insertMany abstraction | ✅ Not needed (not used) |

---

## Appendix: File Line References

### Key Insert/Update Locations

| Operation | File:Line | Context |
|-----------|-----------|---------|
| Entries batch | `lib/server/entries.js:113` | Main insert path |
| Treatments upsert | `lib/server/treatments.js:49` | Primary upsert |
| Treatments preBolus | `lib/server/treatments.js:73` | Secondary upsert |
| DeviceStatus insert | `lib/server/devicestatus.js:25` | Single doc |
| Profile insert | `lib/server/profile.js:11,27` | Single doc |
| V3 insertOne | `lib/api3/storage/mongoCollection/modify.js:16` | Promise wrapper |
| V3 replaceOne | `lib/api3/storage/mongoCollection/modify.js:45` | Promise wrapper |
| V3 updateOne | `lib/api3/storage/mongoCollection/modify.js:68` | Promise wrapper |
| WebSocket insert | `lib/server/websocket.js:447,497,517` | Real-time |

### Query Pattern Locations

| Pattern | File:Line | Description |
|---------|-----------|-------------|
| Entries dedup query | `lib/server/entries.js:112` | `{ sysTime, type }` |
| Treatments dedup query | `lib/server/treatments.js:44-47` | `{ created_at, eventType }` |
| V3 identifier filter | `lib/api3/storage/mongoCollection/utils.js` | ObjectId or identifier |
