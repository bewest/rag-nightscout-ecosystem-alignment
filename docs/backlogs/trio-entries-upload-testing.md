# Trio → Nightscout Entries Upload Testing Backlog

> **Goal**: Develop comprehensive tests for cgm-remote-monitor `entries.js` that handle Trio's UUID `_id` pattern.
> **Gap**: [GAP-SYNC-045](../../traceability/sync-identity-gaps.md#gap-sync-045-trio-entries-upload-uses-uuid-as-_id)
> **Related Fix**: [PR #8447](https://github.com/nightscout/cgm-remote-monitor/pull/8447) (treatments only)
> **Test Location**: `/home/bewest/src/worktrees/nightscout/cgm-pr-8447/tests/`
> **Created**: 2026-03-11

---

## Problem Summary

Trio uploads CGM entries with UUID strings as `_id`. Nightscout's `lib/server/entries.js` does not have the same `identifier` promotion pattern that was added to `treatments.js` in PR #8447.

### Affected Code Paths in Trio

| File | Line | Pattern |
|------|------|---------|
| `Trio/Sources/APS/DeviceDataManager.swift` | 335 | `_id: sample.syncIdentifier` |
| `Trio/Sources/APS/Storage/GlucoseStorage.swift` | 415 | `_id: result.id?.uuidString ?? UUID().uuidString` |

### Upload Endpoint

```
POST /api/v1/entries.json
```

---

## ⚠️ CRITICAL DIFFERENCES FROM TREATMENTS FIX

Before implementing, understand these key differences between `entries.js` and `treatments.js`:

### 1. Different Upsert Key Strategy

| File | Upsert Key | Code |
|------|------------|------|
| `treatments.js` | `identifier` > `_id` > `created_at + eventType` | `upsertQueryFor()` |
| `entries.js` | `sysTime + type` only | Line 111: `{ sysTime: doc.sysTime, type: doc.type }` |

**Impact**: entries.js ignores client `_id` entirely for dedup - it uses timestamp + type. This means:
- ✅ Duplicate entries at same timestamp already prevented
- ❌ Client `_id` is silently discarded (server assigns new ObjectId)
- ❌ No way to update/delete by client `_id`

### 2. GET/DELETE Route Uses ObjectId Only

```javascript
// lib/api/entries/index.js - isId() only matches 24-hex
const ID_PATTERN = /^[a-f\d]{24}$/;
function isId (value) { return ID_PATTERN.test(value); }

// lib/server/entries.js:149 - getEntry() calls new ObjectId(id)
api().findOne({ "_id": new ObjectId(id) }, ...)
```

**Impact**: `GET /entries/UUID` and `DELETE /entries/UUID` will:
- `isId()` returns false (UUID doesn't match 24-hex pattern)
- Falls through to `req.params.model` path (treats as type filter)
- Returns wrong results or 404

### 3. No `identifier` Field in Entry Schema

Unlike treatments (which have `syncIdentifier`), entries have no standard identity field:

| Field | treatments.js | entries.js |
|-------|--------------|------------|
| `syncIdentifier` | ✅ Loop carbs/doses | ❌ Not used |
| `identifier` | ✅ Added by Option G | ❌ Doesn't exist |
| `uuid` | ✅ xDrip+ | ❌ Not used |

**Impact**: Need to add `identifier` to entries schema and indexes.

---

## ⚠️ EDGE CASES TO TEST

### Edge Case 1: UUID _id vs sysTime+type Collision

**Scenario**: Two entries with same timestamp but different `_id`

```javascript
// Entry 1
{ _id: "UUID-A", sysTime: "2026-03-11T20:00:00Z", type: "sgv", sgv: 120 }
// Entry 2 (5 seconds later, same sysTime due to rounding)
{ _id: "UUID-B", sysTime: "2026-03-11T20:00:00Z", type: "sgv", sgv: 125 }
```

**Current behavior**: Entry 2 overwrites Entry 1 (same sysTime+type)
**Expected behavior**: Both preserved, `identifier` used for dedup

### Edge Case 2: Re-upload After App Reinstall

**Scenario**: Trio reinstalled, uploads same glucose with new UUID

```javascript
// Original upload
{ _id: "UUID-OLD", sysTime: "2026-03-11T20:00:00Z", type: "sgv", sgv: 120 }
// Re-upload (same glucose, new UUID)  
{ _id: "UUID-NEW", sysTime: "2026-03-11T20:00:00Z", type: "sgv", sgv: 120 }
```

**Current behavior**: Upsert by sysTime+type = single entry (correct!)
**Question**: Should we store `identifier: UUID-NEW` or keep original?

### Edge Case 3: Mixed Batch Upload

**Scenario**: Batch contains ObjectId, UUID, and no `_id`

```javascript
[
  { _id: "507f1f77bcf86cd799439011", type: "sgv", sgv: 120, ... }, // ObjectId
  { _id: "A1B2C3D4-E5F6-7890-ABCD", type: "sgv", sgv: 125, ... }, // UUID
  { type: "sgv", sgv: 130, ... } // No _id
]
```

**Test**: All three should create successfully.

### Edge Case 4: GET by UUID When Entry Exists

**Scenario**: Entry created with UUID `_id`, then GET requested

```javascript
// Created via POST
{ _id: "A1B2C3D4-E5F6-7890-ABCD", type: "sgv", sgv: 120, ... }

// Server stores as
{ _id: ObjectId("..."), identifier: "A1B2C3D4-E5F6-7890-ABCD", ... }

// Client requests
GET /entries/A1B2C3D4-E5F6-7890-ABCD
```

**Current behavior**: `isId()` returns false, falls through to type filter, returns all SGV
**Required fix**: Check `identifier` field when `isId()` fails

### Edge Case 5: DELETE by UUID

**Scenario**: Delete entry using original UUID

```
DELETE /entries/A1B2C3D4-E5F6-7890-ABCD
```

**Current behavior**: `isId()` fails, may not delete anything
**Required fix**: Query by `identifier` when not ObjectId

### Edge Case 6: CalibrationDue vs SGV Type Collision

**Scenario**: Different entry types at same timestamp

```javascript
{ _id: "UUID-1", sysTime: "T", type: "sgv", sgv: 120 }
{ _id: "UUID-2", sysTime: "T", type: "mbg", mbg: 115 }
```

**Expected**: Both preserved (different types)
**Test**: Verify `type` is part of dedup key

---

## Implementation Plan (Detailed)

### Phase 1: Tests First (Iterations 1-3)

#### Iteration 1: Test Skeleton
- Create `tests/api.entries.uuid.test.js`
- Copy structure from `api.entries.test.js`
- Add 6 test skeletons with `it.skip()`

#### Iteration 2: Implement Tests 001-003
```javascript
describe('UUID _id handling', function() {
  it('TEST-ENTRY-UUID-001: accepts UUID _id on POST');
  it('TEST-ENTRY-UUID-002: deduplicates by sysTime+type');
  it('TEST-ENTRY-UUID-003: GET by UUID returns entry');
});
```

#### Iteration 3: Implement Tests 004-006
```javascript
describe('UUID _id handling', function() {
  it('TEST-ENTRY-UUID-004: DELETE by UUID removes entry');
  it('TEST-ENTRY-UUID-005: batch with mixed IDs');
  it('TEST-ENTRY-UUID-006: identifier field indexed');
});
```

### Phase 2: Implementation (Iterations 4-6)

#### Iteration 4: entries.js Core Changes

```javascript
// Add at top of file
var OBJECT_ID_HEX_RE = /^[0-9a-fA-F]{24}$/;

// Add new function
function normalizeEntryId(doc) {
  // Extract client identifier from _id if UUID
  var clientIdentifier = doc.identifier
    || (typeof doc._id === 'string' && !OBJECT_ID_HEX_RE.test(doc._id) ? doc._id : null);
  
  if (clientIdentifier && !doc.identifier) {
    doc.identifier = clientIdentifier;
  }
  
  // Convert valid ObjectId strings
  if (doc._id && typeof doc._id === 'string' && OBJECT_ID_HEX_RE.test(doc._id)) {
    doc._id = new ObjectId(doc._id);
  } else if (doc._id && typeof doc._id === 'string') {
    // UUID _id - remove it, let server assign
    delete doc._id;
  }
}

// Modify create() - add before line 99
var bulkOps = docs.map(function(doc) {
  normalizeEntryId(doc);  // ← ADD THIS
  // ... rest of function
```

#### Iteration 5: entries.js Query Changes

```javascript
// Modify upsert query (line 111)
var query;
if (doc.identifier) {
  query = { identifier: doc.identifier };
} else if (doc.sysTime && doc.type) {
  query = { sysTime: doc.sysTime, type: doc.type };
} else {
  query = doc;
}

// Modify getEntry() (line 148-156)
function getEntry(id, fn) {
  var query;
  if (OBJECT_ID_HEX_RE.test(id)) {
    query = { _id: new ObjectId(id) };
  } else {
    query = { identifier: id };
  }
  api().findOne(query, function(err, entry) {
    // ...
  });
}
```

#### Iteration 6: API Route Changes

```javascript
// lib/api/entries/index.js
// Modify isId() or add isIdentifier()
function isIdOrIdentifier(value) {
  return ID_PATTERN.test(value) || value.length === 36; // UUID length
}

// Update route handler to use new function
```

### Phase 3: Index & Validation (Iterations 7-8)

#### Iteration 7: Add identifier Index

```javascript
// entries.js line 178
api.indexedFields = [
  'date',
  'type',
  'sgv',
  'mbg',
  'sysTime',
  'dateString',
  'identifier',  // ← ADD THIS
  { 'type': 1, 'date': -1, 'dateString': 1 }
];
```

#### Iteration 8: Run Full Test Suite
```bash
cd /home/bewest/src/worktrees/nightscout/cgm-pr-8447
npm test  # All 722+ tests must pass
```

### Phase 4: Documentation (Iterations 9-10)

#### Iteration 9: Update Backlog Statuses
- Mark all TEST-ENTRY-UUID-* as ✅
- Update GAP-SYNC-045 status to "Fixed"

#### Iteration 10: Final Commit
- Commit with proper trace refs
- Update deep dive document

---

## ⚠️ RISK WARNINGS FOR IMPLEMENTATION

### Risk 1: Breaking sysTime+type Dedup (HIGH RISK)

**Current behavior protects against CGM duplicate data**. The `sysTime + type` upsert ensures only one SGV per timestamp regardless of upload source.

**Risk**: If we change upsert to use `identifier` instead, two different devices uploading the same glucose could create duplicates.

**Mitigation**: Make `identifier` upsert OPTIONAL. Keep `sysTime + type` as fallback:

```javascript
// Priority: identifier > sysTime+type > date+type
function upsertQueryFor(doc) {
  if (doc.identifier) {
    return { identifier: doc.identifier };
  }
  if (doc.sysTime && doc.type) {
    return { sysTime: doc.sysTime, type: doc.type };
  }
  return { date: doc.date, type: doc.type };
}
```

### Risk 2: Index Missing on Production (MEDIUM RISK)

Adding `identifier` to `indexedFields` doesn't automatically create the index on existing databases.

**Risk**: First Trio upload after fix will do collection scan on `identifier` field.

**Mitigation**: 
1. Document manual index creation step
2. OR add migration that checks/creates index on server startup

```javascript
// Startup check (suggested)
entries().createIndex({ identifier: 1 }, { sparse: true, background: true });
```

### Risk 3: v3 API Not Fixed (MEDIUM RISK)

This backlog focuses on v1 API (`/api/v1/entries`). Nightscout also has v3 API in `lib/api3/`.

**Risk**: Trio may also use v3 API, which has different code path.

**Mitigation**: Check Trio's `NightscoutAPI.swift` for v3 usage:
```swift
// Look for "/api/v3/" in upload paths
```

### Risk 4: Rollback Scenario (LOW RISK)

If fix is deployed then reverted, entries created with `identifier` may behave unexpectedly.

**Risk**: Entries with `identifier` field but no UUID `_id` handling code.

**Mitigation**: 
- `identifier` is purely additive (no schema change)
- Old code ignores `identifier` field
- ObjectId `_id` still present for normal ops

### Risk 5: CGM Calibration Entries (LOW RISK)

Trio may also upload `mbg` (calibration) entries with UUID `_id`.

**Risk**: Only testing `sgv` type, `mbg` might have different code path.

**Mitigation**: Add TEST-ENTRY-UUID-007 for `mbg` type entries:
```javascript
it('TEST-ENTRY-UUID-007: handles UUID _id for mbg entries', function() {
  // POST mbg with UUID _id
});
```

---

## Iteration Estimate

Based on complexity analysis:

| Phase | Iterations | Rationale |
|-------|-----------|-----------|
| Phase 1: Tests | 3 | Test structure + 6 test cases |
| Phase 2: Implementation | 3 | entries.js + API routes |
| Phase 3: Validation | 2 | Index + test suite |
| Phase 4: Documentation | 2 | Backlog + deep dive |
| **Total** | **10** | `-n 10` recommended |

### Potential Blockers Requiring Extra Iterations

| Blocker | Impact | Likelihood |
|---------|--------|------------|
| Existing tests fail after change | +2-3 iterations | Medium |
| v3 API also needs fix | +3-4 iterations | Low |
| Index performance issues | +1-2 iterations | Low |

**Recommendation**: Start with `-n 10`, be prepared to extend to `-n 15` if blockers occur.

---

## Test Cases (Original Specification)

### TEST-ENTRY-UUID-001: POST Entry with UUID _id

**Description**: Verify entries API accepts UUID string as `_id` on create.

**Input**:
```json
{
  "_id": "550e8400-e29b-41d4-a716-446655440000",
  "type": "sgv",
  "sgv": 120,
  "direction": "Flat",
  "date": 1710187200000,
  "dateString": "2026-03-11T20:00:00.000Z"
}
```

**Expected**: 
- Entry created successfully
- `_id` either stored as string OR promoted to `identifier` with server-assigned ObjectId

**Status**: ❌ Not implemented

---

### TEST-ENTRY-UUID-002: Re-POST Same UUID Deduplicates

**Description**: Verify re-uploading entry with same UUID `_id` doesn't create duplicate.

**Input**: Same as TEST-ENTRY-UUID-001, POSTed twice

**Expected**:
- Single entry in database
- Upsert behavior (update existing)

**Status**: ❌ Not implemented

---

### TEST-ENTRY-UUID-003: GET Entry by UUID _id

**Description**: Verify entry can be retrieved using original UUID.

**Input**: `GET /api/v1/entries/550e8400-e29b-41d4-a716-446655440000`

**Expected**:
- Entry returned
- No ObjectId coercion error

**Status**: ❌ Not implemented

---

### TEST-ENTRY-UUID-004: DELETE Entry by UUID _id  

**Description**: Verify entry can be deleted using original UUID.

**Input**: `DELETE /api/v1/entries/550e8400-e29b-41d4-a716-446655440000`

**Expected**:
- Entry deleted successfully
- No ObjectId coercion error

**Status**: ❌ Not implemented

---

### TEST-ENTRY-UUID-005: Batch Upload with Mixed IDs

**Description**: Verify batch upload handles mix of UUID and ObjectId `_id` values.

**Input**:
```json
[
  { "_id": "550e8400-e29b-41d4-a716-446655440000", "type": "sgv", "sgv": 120, ... },
  { "_id": "507f1f77bcf86cd799439011", "type": "sgv", "sgv": 125, ... },
  { "type": "sgv", "sgv": 130, ... }
]
```

**Expected**:
- All three entries created
- UUID → identifier promotion OR stored as-is
- ObjectId string → converted to ObjectId
- No `_id` → server generates ObjectId

**Status**: ❌ Not implemented

---

### TEST-ENTRY-UUID-006: Identifier Field Preserved

**Description**: If entry has `identifier` field, it should be preserved and used for dedup.

**Input**:
```json
{
  "identifier": "trio-sync-12345",
  "type": "sgv",
  "sgv": 120,
  ...
}
```

**Expected**:
- `identifier` preserved
- Used for upsert matching on re-upload

**Status**: ❌ Not implemented

---

## Trio Upload Simulation Helpers

### Simulate DeviceDataManager Path

```javascript
// Test helper
function createTrioSGVEntry(syncIdentifier, sgv, direction, timestamp) {
  return {
    _id: syncIdentifier,  // UUID from sample.syncIdentifier
    type: 'sgv',
    sgv: sgv,
    direction: direction,
    date: timestamp,
    dateString: new Date(timestamp).toISOString(),
    device: 'Trio'
  };
}

// Usage
const entry = createTrioSGVEntry(
  'A1B2C3D4-E5F6-7890-ABCD-EF1234567890',
  120,
  'Flat',
  Date.now()
);
```

### Simulate GlucoseStorage Path

```javascript
function createTrioStoredGlucoseEntry(coreDataId, glucose, direction, date) {
  return {
    _id: coreDataId?.toString() || crypto.randomUUID(),
    type: 'sgv',
    sgv: glucose,
    glucose: glucose,
    direction: direction,
    date: date.getTime(),
    dateString: date.toISOString(),
    filtered: glucose,
    unfiltered: glucose,
    device: 'Trio'
  };
}
```

---

## References

- **Gap**: [GAP-SYNC-045](../../traceability/sync-identity-gaps.md#gap-sync-045-trio-entries-upload-uses-uuid-as-_id)
- **Requirement**: [REQ-SYNC-072](../../traceability/sync-identity-requirements.md#req-sync-072)
- **Deep Dive**: [Client ID Handling](../10-domain/client-id-handling-deep-dive.md)
- **Treatments Fix**: [PR #8447](https://github.com/nightscout/cgm-remote-monitor/pull/8447)
- **Source Analysis**: 
  - `externals/Trio/Trio/Sources/APS/DeviceDataManager.swift:332-346`
  - `externals/Trio/Trio/Sources/APS/Storage/GlucoseStorage.swift:413-426`
  - `externals/Trio/Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift:340-374`
