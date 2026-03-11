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

## Test Cases Needed

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

## Implementation Plan

### Phase 1: Add Tests (Document Current Behavior)

1. Create `tests/api.entries.uuid.test.js`
2. Add test cases above
3. Run to document current (failing) behavior

### Phase 2: Implement Fix in entries.js

Apply same pattern as treatments.js:

```javascript
// lib/server/entries.js

var OBJECT_ID_HEX_RE = /^[0-9a-fA-F]{24}$/;

function normalizeEntryId (obj) {
  var clientIdentifier = obj.identifier 
    || (typeof obj._id === 'string' && !OBJECT_ID_HEX_RE.test(obj._id) ? obj._id : null);
  
  if (clientIdentifier && !obj.identifier) {
    obj.identifier = clientIdentifier;
  }
  
  if (obj._id && typeof obj._id === 'string' && OBJECT_ID_HEX_RE.test(obj._id)) {
    obj._id = new ObjectID(obj._id);
  }
}

function upsertQueryFor (obj) {
  if (obj.identifier) {
    delete obj._id;
    return { identifier: obj.identifier };
  }
  if (obj._id) {
    return { _id: obj._id };
  }
  return { date: obj.date, type: obj.type };
}
```

### Phase 3: Validate

1. Run all entry tests
2. Verify Trio upload simulation works
3. Update GAP-SYNC-045 status to "Fixed"

---

## Trio Upload Simulation

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
