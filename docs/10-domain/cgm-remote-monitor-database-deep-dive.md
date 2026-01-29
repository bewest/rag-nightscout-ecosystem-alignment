# cgm-remote-monitor Database Layer Deep Dive

> **Source**: `externals/cgm-remote-monitor-official/` (dev branch)  
> **MongoDB Driver**: `mongodb ^3.6.0`  
> **Last Updated**: 2026-01-29

## Overview

This document audits the database layer of cgm-remote-monitor (Nightscout), analyzing MongoDB schema, indexes, batch operations, and compatibility with Loop's ordering requirements.

---

## Database Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     cgm-remote-monitor                          │
├─────────────────────────────────────────────────────────────────┤
│  lib/storage/mongo-storage.js    ← Core MongoDB connection      │
│  lib/server/*.js                 ← Collection wrappers (v1/v2)  │
│  lib/api3/storage/mongoCollection/*.js ← API v3 storage layer   │
├─────────────────────────────────────────────────────────────────┤
│                        MongoDB                                  │
│  ┌──────────┐ ┌───────────┐ ┌──────────────┐ ┌─────────┐       │
│  │ entries  │ │treatments │ │ devicestatus │ │ profile │       │
│  └──────────┘ └───────────┘ └──────────────┘ └─────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Collections and Indexes

### entries Collection

**File**: `lib/server/entries.js:167`

```javascript
api.indexedFields = [
    'date',
    'type',
    'sgv',
    'mbg',
    'sysTime',
    'dateString',
    { 'type': 1, 'date': -1, 'dateString': 1 }  // Compound index
];
```

**Purpose**: SGV readings, MBG calibrations, sensor data

**Key Fields**:
| Field | Type | Purpose |
|-------|------|---------|
| `_id` | ObjectId | MongoDB auto-generated |
| `date` | Number | Epoch milliseconds |
| `dateString` | String | ISO 8601 timestamp |
| `sysTime` | String | Normalized UTC time |
| `utcOffset` | Number | Timezone offset (minutes) |
| `type` | String | `sgv`, `mbg`, `cal`, etc. |
| `sgv` | Number | Sensor glucose value |

---

### treatments Collection

**File**: `lib/server/treatments.js:175`

```javascript
api.indexedFields = [
    'created_at',
    'eventType',
    'insulin',
    'carbs',
    'glucose',
    'enteredBy',
    'boluscalc.foods._id',
    'notes',
    'NSCLIENT_ID',
    'percent',
    'absolute',
    'duration',
    { 'eventType': 1, 'duration': 1, 'created_at': 1 }  // Compound index
];
```

**Purpose**: Bolus, carbs, temp basal, overrides, announcements

**Key Fields**:
| Field | Type | Purpose |
|-------|------|---------|
| `_id` | ObjectId | MongoDB auto-generated |
| `created_at` | String | ISO 8601 timestamp |
| `eventType` | String | Treatment type (21+ types) |
| `insulin` | Number | Insulin units |
| `carbs` | Number | Carbohydrates (grams) |
| `identifier` | String | API v3 sync identity |

---

### devicestatus Collection

**File**: `lib/server/devicestatus.js:127`

```javascript
api.indexedFields = [
    'created_at',
    'NSCLIENT_ID'
];
```

**Purpose**: Loop/AAPS/Trio status uploads, predictions, pump state

---

### profile Collection

**File**: `lib/server/profile.js:97`

```javascript
api.indexedFields = ['startDate'];
```

**Purpose**: Therapy settings (basal rates, ISF, CR, targets)

---

### Additional Collections

| Collection | Index Fields | Purpose |
|------------|--------------|---------|
| `activity` | `created_at` | User activity log |
| `food` | `type`, `position`, `hidden` | Food database |
| `auth.roles` | `name` | Authorization roles |
| `auth.subjects` | `name` | Authorization subjects |

---

## Index Creation

**File**: `lib/storage/mongo-storage.js:83`

```javascript
mongo.ensureIndexes = function ensureIndexes(collection, fields) {
    fields.forEach(function (field) {
        console.info('ensuring index for: ' + field);
        collection.createIndex(field, { 'background': true }, function (err) {
            if (err) {
                console.error('unable to ensureIndex for: ' + field + ' - ' + err);
            }
        });
    });
};
```

**Key Characteristics**:
- Uses `createIndex()` (MongoDB 3.x+ compatible)
- Background index creation (non-blocking)
- Called during boot (`lib/server/bootevent.js:267-272`)

---

## API v3 Storage Layer

### Collection Setup

**File**: `lib/api3/storage/mongoCollection/index.js:21`

```javascript
ctx.store.ensureIndexes(self.col, [
    'identifier',
    'srvModified',
    'isValid'
]);
```

### Identifier-Based Deduplication

**File**: `lib/api3/storage/mongoCollection/utils.js:130`

```javascript
function identifyingFilter (identifier, doc, dedupFallbackFields) {
    const filterItems = [];
    
    if (identifier) {
        // Standard identifier field (APIv3)
        filterItems.push({ identifier: identifier });
        
        // Fallback to "identifier = _id" (APIv1)
        if (checkForHexRegExp.test(identifier)) {
            filterItems.push({ identifier: { $exists: false }, _id: ObjectID(identifier) });
        }
    }
    
    // Fallback deduplication via field matching
    if (!_.isEmpty(doc) && _.isArray(dedupFallbackFields)) {
        // ... matches on dedupFallbackFields
    }
    
    return { $or: filterItems };
}
```

**Deduplication Strategy**:
1. Primary: Match by `identifier` field (v3)
2. Fallback 1: Match by `_id` if identifier looks like ObjectId
3. Fallback 2: Match by composite fields (e.g., `created_at` + `eventType`)

---

## Batch Operations and Ordering

### Entries: Sequential Upsert

**File**: `lib/server/entries.js:92`

```javascript
function create (docs, fn) {
    docs.forEach(function(doc) {
        // Normalize dates to UTC
        doc.utcOffset = _sysTime.utcOffset();
        doc.sysTime = _sysTime.toISOString();
        
        var query = (doc.sysTime && doc.type) 
            ? { sysTime: doc.sysTime, type: doc.type } 
            : doc;
        
        api().update(query, doc, { upsert: true }, function(err, updateResults) {
            // ... callback on each doc
        });
    });
}
```

**Behavior**: 
- Iterates with `forEach` (parallel, unordered)
- Deduplication by `sysTime + type`
- **No guaranteed insertion order**

### Treatments: Ordered Series

**File**: `lib/server/treatments.js:21`

```javascript
if (_.isArray(objOrArray)) {
    async.eachSeries(objOrArray, function (obj, callback) {
        upsert(obj, function upserted (err, docs) {
            // ... process each
            callback(err, docs);
        });
    }, function () {
        done(errs.length > 0 ? errs : null, allDocs);
    });
}
```

**Behavior**:
- Uses `async.eachSeries` for **ordered sequential processing**
- Each treatment upserted before next begins
- **Preserves client-specified order**

### DeviceStatus: Sequential Insertion

**File**: `lib/server/devicestatus.js:15`

```javascript
for (let i = 0; i < statuses.length; i++) {
    api().insertOne(obj, function(err, results) {
        // Sequential via callback chain
    });
}
```

**Behavior**:
- For loop with callbacks (sequential)
- Insert only, no upsert
- Order preserved within batch

---

## Loop Batch Ordering Verification

### The Requirement

Loop relies on batch ordering for treatments to ensure:
1. Parent bolus appears before child temp basal
2. Override start appears before settings changes
3. Timestamps with same second resolve correctly

### Evidence of Support

**Test**: `tests/api.entries.test.js:99`

```javascript
it('gets entries in right order', function (done) {
    request(self.app)
        .get('/entries/sgv.json')
        .expect(200)
        .end(function (err, res) {
            var firstEntry = res.body[0];
            var secondEntry = res.body[1];
            firstEntry.date.should.be.above(secondEntry.date);
            done();
        });
});
```

**Test**: `tests/api.entries.test.js:117`

```javascript
it('gets entries in right order without type specifier', function (done) {
    // Validates descending date order
});
```

### Finding: Treatments Are Ordered

The `async.eachSeries` in `lib/server/treatments.js:21` ensures treatments are processed sequentially, preserving client order. This satisfies Loop's requirement.

**Relevant Commit**: `d7f44324` (Feb 2023)
```
* Add a unit test to check the /entries endpoint returns values in correct order
* Fix a bug in CGM entry insertion, where entries that were inserted without 
  a dateString but with a numeric date were always using the current time
```

---

## MongoDB 5.x Compatibility Analysis

### Current Driver Version

```json
"mongodb": "^3.6.0"
```

The MongoDB Node.js driver 3.6.x is compatible with MongoDB 5.x server.

### Potential Issues

| Concern | Status | Notes |
|---------|--------|-------|
| `createIndex` | ✅ OK | Works in 5.x |
| `update` with upsert | ✅ OK | Works in 5.x |
| `insertOne` | ✅ OK | Works in 5.x |
| `ObjectID` import | ⚠️ Warning | Deprecated, use `ObjectId` |
| Connection options | ⚠️ Warning | `useNewUrlParser`, `useUnifiedTopology` deprecated |

### Recommended Upgrades

```javascript
// Current (3.6.x style)
const ObjectID = require('mongodb').ObjectID;
const options = {
    useNewUrlParser: true,
    useUnifiedTopology: true,
};

// Recommended (4.x/5.x style)
const { ObjectId } = require('mongodb');
// No options needed - unified topology is default
```

---

## API Version Comparison

| Aspect | API v1 | API v3 |
|--------|--------|--------|
| Storage | `lib/server/*.js` | `lib/api3/storage/mongoCollection/*.js` |
| Identity | `_id` (ObjectId) | `identifier` (String) |
| Deduplication | `sysTime + type` (entries) | `identifier` + fallback |
| Upsert | `update({}, {}, {upsert: true})` | `replaceOne({}, {}, {upsert: true})` |
| Batch Ordering | Mixed (`forEach` vs `eachSeries`) | Single document only |

---

## Gaps Identified

### GAP-DB-001: Entries batch ordering not guaranteed

**Description**: The `lib/server/entries.js` uses `forEach` for batch inserts, which does not guarantee order. If two entries have the same `sysTime`, insertion order may vary.

**Impact**:
- CGM readings with same timestamp may appear in random order
- Affects historical data display

**Remediation**: 
- Use `async.eachSeries` like treatments
- Or add sequence number for same-timestamp entries

### GAP-DB-002: MongoDB driver version deprecated patterns

**Description**: Uses `ObjectID` and deprecated connection options.

**Impact**:
- Console warnings in Node.js 18+
- May cause issues with MongoDB 6.x+

**Remediation**: 
- Upgrade to `mongodb` 4.x or 5.x driver
- Use `ObjectId` import
- Remove deprecated options

### GAP-DB-003: No bulk write optimization

**Description**: All batch operations use sequential single-document operations rather than `bulkWrite()`.

**Impact**:
- Higher latency for large uploads
- More round-trips to MongoDB

**Remediation**:
- Implement `bulkWrite` for batch inserts
- Preserve ordering with `{ ordered: true }`

---

## Source File Reference

### Core Storage
- `externals/cgm-remote-monitor-official/lib/storage/mongo-storage.js` - Connection, index creation
- `externals/cgm-remote-monitor-official/lib/server/bootevent.js:258-274` - Boot-time index setup

### Collection Wrappers (v1/v2)
- `externals/cgm-remote-monitor-official/lib/server/entries.js` - SGV storage
- `externals/cgm-remote-monitor-official/lib/server/treatments.js` - Treatment storage
- `externals/cgm-remote-monitor-official/lib/server/devicestatus.js` - DeviceStatus storage
- `externals/cgm-remote-monitor-official/lib/server/profile.js` - Profile storage

### API v3 Storage
- `externals/cgm-remote-monitor-official/lib/api3/storage/mongoCollection/index.js` - Collection wrapper
- `externals/cgm-remote-monitor-official/lib/api3/storage/mongoCollection/modify.js` - CRUD operations
- `externals/cgm-remote-monitor-official/lib/api3/storage/mongoCollection/utils.js` - Query helpers

### Tests
- `externals/cgm-remote-monitor-official/tests/api.entries.test.js:99` - Ordering test
- `externals/cgm-remote-monitor-official/tests/api.treatments.test.js` - Treatment tests
- `externals/cgm-remote-monitor-official/tests/mongo-storage.test.js` - Storage tests

---

## Summary

| Aspect | Finding |
|--------|---------|
| **MongoDB Driver** | 3.6.0 (compatible with MongoDB 5.x) |
| **Collections** | 6 main + 2 auth |
| **Indexes** | Background creation, compound indexes supported |
| **Treatments Ordering** | ✅ Preserved via `async.eachSeries` |
| **Entries Ordering** | ⚠️ Not guaranteed (uses `forEach`) |
| **Loop Compatibility** | ✅ Treatment batches ordered correctly |
| **v3 Deduplication** | Uses `identifier` with fallback strategy |

**Key Finding**: Loop's batch ordering requirement for treatments is satisfied by the `async.eachSeries` implementation in `lib/server/treatments.js`. Entries batch ordering is not guaranteed but typically not critical for Loop operation.
