# Profile API Array Handling Regression

**Status**: In Progress  
**Priority**: High  
**Affected Version**: v15.0.0+ (after MongoDB driver migration)  
**Worktree**: `/home/bewest/src/worktrees/nightscout/cgm-pr-8447`

## Summary

The Profile API POST endpoint broke array handling when migrated from legacy MongoDB driver's `insert()` to `insertOne()`. This affects Loop iOS users via NightscoutKit.

## API Comparison: Array Handling Patterns

| API | API Layer | Storage Layer | NightscoutKit Sends | Status |
|-----|-----------|---------------|---------------------|--------|
| **Treatments** | ✅ `if (!_isArray(treatments)) { treatments = [treatments]; }` | Uses array | Array | ✅ Works |
| **Entries** | ✅ `if (req.body.length) { incoming.concat(req.body); }` | Uses stream | Array | ✅ Works |
| **DeviceStatus** | ⚠️ Passes single `obj` to purifier | ✅ `if (!Array.isArray(statuses)) { statuses = [statuses]; }` | Array | ⚠️ Partial |
| **Profile** | ❌ Passes `req.body` directly | ❌ Uses `insertOne()` | Array | ❌ Broken |

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

| ID | Title | Description |
|----|-------|-------------|
| `profile-array-fix` | Fix profile API array handling | Add array normalization + `insertMany()` |
| `devicestatus-purifier-fix` | Fix devicestatus API purifier | Add array loop for purification |

### Track 2: Extract Fixtures from NightscoutKit

| ID | Title | Description |
|----|-------|-------------|
| `fixture-nightscoutkit-profile` | Extract profile fixtures | Single array, batch array, response format |
| `fixture-nightscoutkit-devicestatus` | Extract devicestatus fixtures | LoopStatus, PumpStatus nested structures |
| `fixture-nightscoutkit-treatments` | Extract treatment fixtures | Carb, Bolus, TempBasal with syncIdentifier |

### Track 3: Test Matrices

| ID | Title | Description |
|----|-------|-------------|
| `test-matrix-api-array` | API array handling test matrix | Test single/array/batch/empty across all APIs |
| `test-matrix-client-behaviors` | Client behavior test matrix | Document Loop, Trio, AAPS, xDrip+ expectations |

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
