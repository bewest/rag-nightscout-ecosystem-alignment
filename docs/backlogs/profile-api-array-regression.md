# Profile API Array Handling Regression

**Status**: ✅ Complete  
**Priority**: High  
**Affected Version**: v15.0.0+ (after MongoDB driver migration)  
**Worktree**: `/home/bewest/src/worktrees/nightscout/cgm-pr-8447`

## Summary

The Profile API POST endpoint broke array handling when migrated from legacy MongoDB driver's `insert()` to `insertOne()`. This affects Loop iOS users via NightscoutKit.

**Fixed in commits:**
- `cbb6d061` - Profile array handling
- `2e81ce07` - DeviceStatus purifier fix  
- `32b1d700`, `8d44a043`, `808b923e` - _id validation across all endpoints
- `9fd53e32`, `269170b9`, `83248e7f` - NightscoutKit fixtures
- `5f5bf224` - Test matrix

## API Comparison: Array Handling Patterns

| API | API Layer | Storage Layer | Client Sends | Status |
|-----|-----------|---------------|--------------|--------|
| **Treatments** | ✅ Normalizes to array | ✅ `insertMany` | Array | ✅ Works |
| **Entries** | ✅ Handles both | ✅ Stream-based | Array | ✅ Works |
| **DeviceStatus** | ✅ Purifies each item | ✅ `insertMany` | Array | ✅ Fixed (`2e81ce07`) |
| **Profile** | ✅ Normalizes to array | ✅ `insertMany` | Array | ✅ Fixed (`cbb6d061`) |
| **Activity** | ✅ Normalizes to array | ✅ `replaceOne` loop | Single/Array | ✅ Works |
| **Food** | ✅ Normalizes to array | ✅ `replaceOne` loop | Single/Array | ✅ Fixed (`ef7bff3d`) |

### Activity API Analysis

- **API Layer**: ✅ Already normalizes `if (!_isArray(activity)) { activity = [activity]; }`
- **API Layer**: ✅ Has _id validation with `findInvalidId()`
- **Storage `create()`**: ✅ Uses `replaceOne` loop with upsert (works, handles arrays)
- **Status**: ✅ **Works for both single and array input**

### Food API Analysis

- **API Layer**: ✅ Normalizes to array (fixed in `ef7bff3d`)
- **API Layer**: ✅ Has _id validation for POST/PUT/DELETE
- **Storage `create()`**: ✅ Uses `replaceOne` loop with upsert (same as activity)
- **Status**: ✅ **Fixed - supports both single and array input**

### Array Support Priority

| API | Array Support | Crash Risk | Priority |
|-----|---------------|------------|----------|
| **Food** | ✅ Fixed | ❌ No crash | ✅ Done (`ef7bff3d`) |
| **Activity** | ✅ Works | ❌ No crash | ✅ Done |

**All APIs now support array input.**

### Correct Pattern (from Treatments)

```javascript
// lib/api/treatments/index.js:104-144
function post_response (req, res) {
  var treatments = req.body;

  // 1. Normalize to array
  if (!_isArray(treatments)) {
    treatments = [treatments];
  }

  // 2. Process each item
  for (let i = 0; i < treatments.length; i++) {
    const t = treatments[i];
    if (!t.created_at) {
      t.created_at = new Date().toISOString();
    }
    ctx.purifier.purifyObject(t);
  }

  // 3. Batch insert
  ctx.treatments.create(treatments, function(err, created) {
    if (err) {
      res.sendJSONStatus(res, constants.HTTP_INTERNAL_ERROR, 'Mongo Error', err);
    } else {
      res.json(created);  // Return array
    }
  });
}
```

### DeviceStatus Note

DeviceStatus has a **partial fix** - the storage layer handles arrays, but the API layer only purifies a single object. This should also be fixed for consistency:

```javascript
// CURRENT (lib/api/devicestatus/index.js:70-72) - BUGGY
var obj = req.body;
ctx.purifier.purifyObject(obj);  // Only purifies if single object!

// SHOULD BE:
var statuses = req.body;
if (!Array.isArray(statuses)) { statuses = [statuses]; }
for (let i = 0; i < statuses.length; i++) {
  ctx.purifier.purifyObject(statuses[i]);
}
```

## Root Cause

| Commit | Change | Impact |
|--------|--------|--------|
| `d46c5b41` | Changed `api().insert(obj)` → `api().insertOne(obj)` | Broke array support |

**Before (worked):**
```javascript
// lib/server/profile.js - OLD
api().insert(obj, function (err, doc) {  // insert() accepts arrays
  fn(null, doc);
});
```

**After (broken):**
```javascript
// lib/server/profile.js - CURRENT
api().insertOne(obj, function (err, doc) {  // insertOne() rejects arrays
  ...
});
```

## Evidence

### NightscoutKit Sends Arrays

From `NightscoutKit/Sources/NightscoutKit/NightscoutClient.swift:405`:

```swift
public func uploadProfile(profileSet: ProfileSet, completion: ...) {
    postToNS([profileSet.dictionaryRepresentation], url: url, completion: completion)
    //       ^--- Array wrapper
}
```

### MongoDB Error

```
MongoServerError: BSON field 'insert.documents.0' is the wrong type 'array', expected type 'object'
```

### Comparison with Other APIs

| API | Array Handling | Code |
|-----|----------------|------|
| **Treatments** | ✅ Normalizes | `if (!_isArray(treatments)) { treatments = [treatments]; }` |
| **Entries** | ✅ Handles both | `if (req.body.length) { incoming = incoming.concat(req.body); }` |
| **Profile** | ❌ Broken | Passes `req.body` directly to `insertOne()` |

## Proposed Fix

### Restore Full Array Support (Recommended)

Since this is a **regression**, restore the behavior that worked before:

```javascript
// lib/api/profile/index.js
api.post('/profile/', ..., function(req, res) {
    var data = req.body;
    
    // Normalize to array (match treatments pattern)
    if (!Array.isArray(data)) {
        data = [data];
    }
    
    // Purify each profile
    for (let i = 0; i < data.length; i++) {
        ctx.purifier.purifyObject(data[i]);
    }
    
    ctx.profile.createMany(data, function(err, created) {
        if (err) {
            res.sendJSONStatus(res, consts.HTTP_INTERNAL_ERROR, 'Mongo Error', err);
            console.log('Error creating profile');
            console.log(err);
        } else {
            // Return array of inserted docs (NightscoutKit expects this)
            res.json(created);
            console.log('Profile(s) created', created.length);
        }
    });
});

// lib/server/profile.js
function createMany(docs, fn) {
    docs.forEach(d => {
        if (!d.created_at) {
            d.created_at = (new Date()).toISOString();
        }
    });
    
    api().insertMany(docs, function(err, result) {
        if (err) {
            console.log("Error saving profile data", docs, err);
            fn(err);
            return;
        }
        // Return the inserted documents with _id
        fn(null, result.ops || docs);
    });
    ctx.bus.emit('data-received');
}
```

## Research Findings

### Multi-Profile Upload Use Cases

**Yes, Loop batches profile uploads!**

From `LoopWorkspace/NightscoutService/NightscoutServiceKit/NightscoutService.swift`:
```swift
public var settingsDataLimit: Int? { return 400 }  // Up to 400 items per batch!

public func uploadSettingsData(_ stored: [StoredSettings], completion: ...) {
    ...
    uploader.uploadProfiles(stored.compactMap { $0.profileSet }, completion: completion)
}
```

Loop uses `settingsStore.executeSettingsQuery()` to fetch historical settings changes,
then uploads them in batches to Nightscout. This allows syncing therapy setting history.

### Response Format Requirements

NightscoutKit expects response to match input count:
```swift
guard let insertedEntries = postResponse as? [[String: Any]], 
      insertedEntries.count == json.count else {
    completion(.failure(.invalidResponse(...)))
}
```

**Server MUST return array of inserted documents with `_id` fields.**

### NightscoutKit Response Expectations

From `NightscoutKit/NightscoutClient.swift:488`:
```swift
guard let insertedEntries = postResponse as? [[String: Any]], insertedEntries.count == json.count else {
    completion(.failure(.invalidResponse(...)))
}
```

NightscoutKit expects response to be an **array of objects** with `_id` fields.

## Test Fixtures Needed

### From NightscoutKit (externals/NightscoutKit/)

| Fixture | Source File | Format | Purpose |
|---------|-------------|--------|---------|
| `nightscoutkit-profile-single.js` | `Models/ProfileSet.swift` | `[profile]` | Single profile wrapped in array |
| `nightscoutkit-profile-batch.js` | `Models/ProfileSet.swift` | `[p1, p2, ...]` | Batch profile upload |
| `nightscoutkit-devicestatus.js` | `Models/DeviceStatus.swift` | `[status]` | LoopStatus, PumpStatus nested |
| `nightscoutkit-treatment-carb.js` | `Models/Treatments/*.swift` | `[treatment]` | CarbCorrection with syncIdentifier |
| `nightscoutkit-treatment-bolus.js` | `Models/Treatments/*.swift` | `[treatment]` | Bolus with syncIdentifier |

### Extraction Method

```bash
# View ProfileSet structure
cat externals/NightscoutKit/Sources/NightscoutKit/Models/ProfileSet.swift

# View dictionaryRepresentation (this is what gets JSON encoded)
grep -A50 "dictionaryRepresentation" externals/NightscoutKit/Sources/NightscoutKit/Models/ProfileSet.swift
```

## Test Matrix: API Array Handling

| Test Case | Input | Expected Response | Profile | DeviceStatus | Treatments | Entries |
|-----------|-------|-------------------|---------|--------------|------------|---------|
| Single object | `{...}` | `[{..., _id}]` | ❌ Fix | ✅ | ✅ | ✅ |
| Single-element array | `[{...}]` | `[{..., _id}]` | ❌ Fix | ✅ | ✅ | ✅ |
| Multi-element array | `[{...}, {...}]` | `[{..., _id}, {..., _id}]` | ❌ Fix | ✅ | ✅ | ✅ |
| Empty array | `[]` | `[]` or 400 | ❌ Fix | ? | ✅ | ? |
| Response count | - | `response.length === input.length` | ❌ Fix | ✅ | ✅ | ✅ |
| Response has _id | - | All items have `_id` field | ❌ Fix | ✅ | ✅ | ✅ |

## Test Matrix: Client Behaviors

| Client | Profile | DeviceStatus | Treatments | Entries |
|--------|---------|--------------|------------|---------|
| **NightscoutKit (Loop)** | Array (single or batch) | Array | Array | Array |
| **Trio** | Single object POST | Array | Array | Array |
| **AAPS** | TBD | TBD | TBD | TBD |
| **xDrip+** | TBD | TBD | TBD | TBD |
| **Portal Editor** | Single object PUT | N/A | Single object | N/A |

## Files to Modify

### c-r-m Worktree

- `lib/api/profile/index.js` - Add array handling
- `lib/server/profile.js` - Add `createMany()` function
- `tests/api.profiles.test.js` - Add array test cases
- `tests/fixtures/profiles/` - Add NightscoutKit fixtures

## Work Items

### Track 1: Fix Regressions (Priority)

| ID | Title | Description | Status |
|----|-------|-------------|--------|
| `profile-array-fix` | Fix profile API array handling | Add array normalization + `insertMany()` | ✅ Complete |
| `devicestatus-purifier-fix` | Fix devicestatus API purifier | Add array loop for purification | ✅ Complete |
| `profile-id-validation` | Add _id validation to profile API | Return 400 on invalid _id instead of 500 crash | ✅ Complete (`32b1d700`) |
| `devicestatus-id-validation` | Add _id validation to devicestatus API | Reject invalid _id with 400 instead of silent ignore | ✅ Complete (`2c15a323`) |

### Track 1b: _id Validation - All Endpoints ✅ COMPLETE

| ID | Title | Description | Status |
|----|-------|-------------|--------|
| `activity-id-validation` | Add _id validation to activity API | API validates before storage | ✅ Complete (`808b923e`) |
| `food-id-validation` | Add _id validation to food API | API validates before storage | ✅ Complete (`808b923e`) |
| `api3-id-validation` | API3 query validation | `checkForHexRegExp` validates before `new ObjectID()` | ✅ Already Safe |
| `websocket-id-validation` | Websocket validation | `safeObjectID()` validates and preserves strings | ✅ Already Safe |
| `id-validation-tests` | Create _id validation test suite | Tests for activity, food, profile, devicestatus | ✅ Complete (`808b923e`) |

### Track 1c: Array Handling - All Endpoints ✅ COMPLETE

| ID | Title | Description | Status |
|----|-------|-------------|--------|
| `food-array-fix` | Add array support to food API | ✅ Fixed - supports single and array input | ✅ Complete (`ef7bff3d`) |
| `activity-storage-fix` | Optimize activity storage | Works but uses `replaceOne` loop - optional | 📋 Optional |

**Food API Fix Applied (`ef7bff3d`):**
- API layer: Added array normalization with `findInvalidId()` validation
- Storage layer: Changed `insertOne()` to `replaceOne` loop with upsert
- Now matches activity pattern exactly

### Track 1d: Array Input Test Coverage

| ID | Title | Description | Status |
|----|-------|-------------|--------|
| `test-food-array-input` | Add array input tests for food API | Single, array, batch, empty array | 📋 Ready |
| `test-activity-single-input` | Add single object test for activity API | Current tests only cover array | 📋 Ready |
| `test-entries-single-input` | Add single object test for entries API | Current tests only cover array | 📋 Ready |

**Test Coverage Audit:**

| API | Single Object | Array [1] | Batch [n] | Empty [] | Gap |
|-----|---------------|-----------|-----------|----------|-----|
| Treatments | ✅ | ✅ | ✅ | ❌ | - |
| DeviceStatus | ✅ | ✅ | ✅ | ❌ | - |
| Entries | ❌ | ✅ | ✅ | ❌ | Single |
| Profile | ✅ | ✅ | ❌ | ✅ | Batch |
| Food | ✅ | ❌ | ❌ | ❌ | Array |
| Activity | ❌ | ✅ | ❌ | ❌ | Single |

### Track 2: Extract Fixtures from NightscoutKit ✅ COMPLETE

| ID | Title | Description | Status |
|----|-------|-------------|--------|
| `fixture-nightscoutkit-profile` | Extract profile fixtures | Single array, batch array, response format | ✅ Complete (`9fd53e32`) |
| `fixture-nightscoutkit-devicestatus` | Extract devicestatus fixtures | LoopStatus, PumpStatus nested structures | ✅ Complete (`269170b9`) |
| `fixture-nightscoutkit-treatments` | Extract treatment fixtures | Carb, Bolus, TempBasal with syncIdentifier | ✅ Complete (`83248e7f`) |

### Track 3: Test Matrices ✅ COMPLETE

| ID | Title | Description | Status |
|----|-------|-------------|--------|
| `test-matrix-api-array` | API array handling test matrix | Test single/array/batch/empty across all APIs | ✅ Complete (`5f5bf224`) |
| `test-matrix-client-behaviors` | Client behavior test matrix | Document Loop, Trio, AAPS, xDrip+ expectations | ✅ Complete (`73b901a`) |

### Track 4: Client Analysis (Optional)

| ID | Title | Description |
|----|-------|-------------|
| `profile-c1` | Analyze Loop profile upload | NightscoutKit patterns |
| `profile-c2` | Analyze AAPS profile upload | NSClient patterns |
| `profile-c3` | Analyze Trio profile upload | Fork of Loop - same? |
| `profile-c4` | Analyze xDrip+ profile upload | Does it upload profiles? |
| `profile-c5` | Create client comparison matrix | Unified documentation |

## Related

- Deep dive: `docs/10-domain/profile-client-patterns.md` (to be created)
- NightscoutKit source: `externals/NightscoutKit/`
- Breaking commit: `d46c5b41a81a8c0804444ebdfb2dddbb207eab47`

## _id Protocol and Client Behavior Matrix

### The Protocol Rule

**MongoDB `_id` must be a valid 24-character hex ObjectId.** Non-ObjectId values sent to `_id` are a **protocol error**.

However, this protocol error "silently worked" in various ways historically, creating mixed client expectations.

### Historical Behavior (Why It "Worked")

| Era | MongoDB `insert()` behavior | Result |
|-----|----------------------------|--------|
| **Pre-v15** | Legacy `insert()` accepted anything | Non-ObjectId stored directly, queries worked |
| **v15+** | `insertOne()` validates stricter | Non-ObjectId causes type mismatch errors |

### Client Expectations Matrix

| Client | Collection | What They Send to `_id` | Expected Behavior | Actual Pre-v15 | Planned v15+ |
|--------|------------|-------------------------|-------------------|----------------|--------------|
| **Loop overrides** | treatments | UUID (`syncIdentifier.uuidString`) | Insert + retrieve by same ID | ✅ Worked | ✅ `UUID_HANDLING` quirk |
| **Trio CGM** | entries | UUID | Insert + retrieve by same ID | ✅ Worked | ✅ `UUID_HANDLING` quirk |
| **Loop carbs/doses** | treatments | `syncIdentifier` field (not `_id`) | N/A - correct usage | ✅ Works | ✅ Works |
| **AAPS** | treatments | `identifier` field (not `_id`) | N/A - correct usage | ✅ Works | ✅ Works |
| **xDrip+** | treatments | `uuid` field (not `_id`) | N/A - correct usage | ✅ Works | ✅ Works |
| **Portal Editor** | profile | Omits `_id` (correct) | Server generates | ✅ Works | ✅ Works |
| **NightscoutKit** | profile | Omits `_id` (correct) | Server generates | ✅ Works | ✅ Works |

### Server-Side Strategy

| Endpoint | UUID_HANDLING Quirk? | Non-ObjectId Handling | Rationale |
|----------|---------------------|----------------------|-----------|
| **entries** | ✅ Yes | UUID → `identifier`, strip `_id` | Trio sends UUID to `_id` |
| **treatments** | ✅ Yes | UUID → `identifier`, strip `_id` | Loop overrides send UUID |
| **profile** | ❌ No | Return **400** | No client sends UUID to `_id` |
| **devicestatus** | ❌ No | Return **400** | No client sends UUID to `_id` |
| **activity** | ❌ No | Return **400** | No client sends UUID to `_id` |
| **food** | ❌ No | Return **400** | No client sends UUID to `_id` |

### Why Different Treatment?

| Collection | Has UUID_HANDLING | Reason |
|------------|-------------------|--------|
| **entries/treatments** | ✅ Yes | Historical client data exists with UUID in `_id` |
| **profile/devicestatus/etc** | ❌ No | No evidence of clients sending UUID to `_id` |

**Principle**: Apply the quirk **only where clients actually used it**, enforce 400 everywhere else.

### Evidence from NightscoutKit Source Code

| Collection | `dictionaryRepresentation` sends `_id`? | Verified |
|------------|----------------------------------------|----------|
| **ProfileSet** | ❌ No - omits `_id`, only reads from response | `externals/NightscoutKit/.../ProfileSet.swift:141-159` |
| **DeviceStatus** | ❌ No - sends `identifier` field instead | `externals/NightscoutKit/.../DeviceStatus.swift:60-62` |
| **TreatmentEntry** | ⚠️ Some send `syncIdentifier` to `_id` | Loop overrides only |

### Summary: Is This Accurate?

| Statement | Accuracy | Evidence |
|-----------|----------|----------|
| "Non-ObjectId to `_id` is protocol error" | ✅ **True** | MongoDB spec requires ObjectId or server-generated |
| "It silently worked historically" | ✅ **True** | Legacy `insert()` accepted any value |
| "Mixed client expectations" | ⚠️ **Partially** | Only Loop overrides + Trio CGM actually used it |
| "UUID_HANDLING is a quirk for Loop/Trio" | ✅ **True** | Preserves compatibility for historical data |
| "Stricter behavior elsewhere" | ✅ **True** | 400 for profile/devicestatus/activity/food |
| "NightscoutKit omits _id for profile/devicestatus" | ✅ **Verified** | Source code inspection confirms |

---

## _id Validation Issue

### Full Endpoint Audit

| Endpoint | Storage File | ObjectID Handling | Invalid _id Behavior |
|----------|--------------|-------------------|---------------------|
| **profile** | `lib/server/profile.js:39` | `new ObjectID(obj._id)` | **500 crash** |
| **activity** | `lib/server/activity.js:31` | `new ObjectID(obj._id)` | **500 crash** |
| **food** | `lib/server/food.js:20` | try/catch → `new ObjectID()` | **Silent replace** (generates new _id) |
| **devicestatus** | `lib/server/devicestatus.js` | No conversion | **Silent ignore** (client _id lost) |
| **entries** | `lib/server/entries.js` | UUID_HANDLING extracts to `identifier` | ✅ **Correct** (400 or strips) |
| **treatments** | Via API3 | Via mongoCollection storage | Via API3 validation |
| **API3 queries** | `lib/api3/storage/mongoCollection/utils.js:115` | `new ObjectID(identifier)` | **500 crash** on lookup |
| **websocket** | `lib/server/websocket.js:455` | Direct `insertOne(data.data)` | Depends on collection |

### Current Behavior Summary

| Behavior | Endpoints | Problem |
|----------|-----------|---------|
| **500 crash** | profile, activity, API3 queries | Server error exposed to client |
| **Silent ignore** | devicestatus | Client's _id silently discarded |
| **Silent replace** | food | Generates new _id, may cause duplicates |
| **Correct (400/extract)** | entries | Only endpoint with proper handling |

### Desired Behavior

All should return **400 Bad Request** with clear error message:

```json
{
  "status": 400,
  "message": "Invalid _id format. Must be 24-character hex string or omit for auto-generation."
}
```

### Fix Pattern

```javascript
// Validate _id if provided
function validateObjectId(id) {
  if (id === undefined || id === null) return true;  // Will auto-generate
  if (typeof id !== 'string') return false;
  return /^[a-fA-F0-9]{24}$/.test(id);
}

// In API handler, before storage:
if (doc._id && !validateObjectId(doc._id)) {
  return res.status(400).json({
    status: 400,
    message: 'Invalid _id format. Must be 24-character hex string or omit for auto-generation.'
  });
}
```

### Test Cases for _id Validation

| Input _id | Expected | Test |
|-----------|----------|------|
| `undefined` | 200 + auto-gen | ✅ Allow |
| `null` | 200 + auto-gen | ✅ Allow |
| `"507f1f77bcf86cd799439011"` | 200 + use provided | ✅ Valid hex |
| `"my-uuid-12345"` | **400** | ❌ Not 24 hex chars |
| `"abc"` | **400** | ❌ Too short |
| `12345` | **400** | ❌ Not string |
| `{}` | **400** | ❌ Object |
