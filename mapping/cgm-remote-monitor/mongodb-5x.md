# cgm-remote-monitor: MongoDB 5.x Migration

**Source**: `externals/cgm-remote-monitor` (wip/bewest/mongodb-5x)  
**Verified**: 2026-01-20

## Overview

This branch (`wip/bewest/mongodb-5x`) contains changes for MongoDB 5.x compatibility, addressing deprecated APIs and modernizing bulk operations.

## Key Changes

### 1. Bulk Write Operations

**Entries** (`lib/server/entries.js:99-145`):
- Migrated from sequential inserts to `bulkWrite`
- Uses `updateOne` with `$set` and `upsert: true`
- `{ ordered: true }` preserves response ordering

**Treatments** (`lib/server/treatments.js:49-82`):
- Uses `replaceOne` with `upsert: true`
- Handles preBolus separately with sequential fallback
- Returns `upsertedIds` from bulk result

### 2. findOneAndUpdate Migration

No deprecated `findAndModify` calls found. Modern patterns:
- `lib/api3/storage/mongoCollection/modify.js:62-76` - Uses `updateOne()`
- `lib/server/websocket.js:225, 273` - Uses `updateOne()`

### 3. Array Handling in WebSocket

Per `lib/server/websocket.js:306` comment:
> "Array support added for MongoDB 5.x migration (insertOne -> handles arrays via iteration)"

Lines 321-354: Sequential processing for arrays, preserving backward compatibility.

## Test Coverage

### New Test Files

| File | Lines | Purpose |
|------|-------|---------|
| `tests/concurrent-writes.test.js` | - | Simultaneous POST requests |
| `tests/api.partial-failures.test.js` | 496 | Batch operation edge cases |
| `tests/api.deduplication.test.js` | 388 | AAPS, Loop, Trio patterns |
| `tests/api.aaps-client.test.js` | 331 | AAPS-specific formats |
| `tests/websocket.shape-handling.test.js` | - | Array input behavior |

### Test Results

Per `docs/proposals/mongodb-modernization-implementation-plan.md`:
- **29/30 tests passing** (96.7%)
- Phase 1 (Test Infrastructure) complete

## Critical Behaviors Preserved

### Response Ordering

Per `lib/server/entries.js:123` and `lib/server/treatments.js:62`:

```javascript
api().bulkWrite(bulkOps, { ordered: true }, ...)
```

**Guarantee**: `response[i]` corresponds to `request[i]` - critical for Loop.

### Result Mapping

Per `lib/server/treatments.js:69-73`:

```javascript
Object.keys(bulkResult.upsertedIds).forEach(function(index) {
  objOrArray[index]._id = bulkResult.upsertedIds[index];
});
```

Original array returned with `_id` fields assigned by position.

## Client Impact

| Client | Impact | Notes |
|--------|--------|-------|
| **Loop** | ✅ Safe | Response ordering preserved |
| **AAPS** | ✅ Safe | Deduplication logic unchanged |
| **Trio** | ✅ Safe | Uses same patterns as Loop |
| **xDrip+** | ✅ Safe | PUT upsert still works |
| **xDrip4iOS** | ✅ Safe | POST/PUT patterns unchanged |

## Documentation

| File | Purpose |
|------|---------|
| `docs/proposals/mongodb-modernization-implementation-plan.md` | Comprehensive plan |
| `docs/proposals/TEST-IMPLEMENTATION-SUMMARY.md` | Test results |
| `docs/proposals/test-development-findings.md` | Critical behaviors |
| `docs/proposals/websocket-array-deduplication-issue.md` | Known issue analysis |

## Migration Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 1. Test Infrastructure | ✅ Complete | 29/30 tests passing |
| 2. Storage Layer Analysis | 🔄 Next | Analyze remaining patterns |
| 3. Core Implementation | ⏳ Planned | Apply remaining fixes |
| 4. Testing & Validation | ⏳ Planned | Full regression testing |

## Requirements Derived

| ID | Requirement | Source |
|----|-------------|--------|
| REQ-NS-MDB-001 | Must use `ordered: true` for bulk writes | Loop compat |
| REQ-NS-MDB-002 | Must return `upsertedIds` mapped by index | Loop compat |
| REQ-NS-MDB-003 | Must process arrays sequentially in WebSocket | Dedup compat |
| REQ-NS-MDB-004 | Must preserve all existing dedup behaviors | Client compat |
