# MongoDB 5.x Upgrade Compatibility Report

**Status**: 📋 Research Phase  
**Priority**: P1  
**Scope**: cgm-remote-monitor v15.0.x  
**Worktree**: `/home/bewest/src/worktrees/nightscout/cgm-pr-8447`

## Overview

This report documents behavioral changes and compatibility considerations for the MongoDB 5.x driver upgrade in Nightscout cgm-remote-monitor. The goal is to prove accuracy of changes against previous releases and client expectations.

**Suggested Workflow**: `sdqctl iterate ./workflows/mongodb-upgrade-research.conv -n 5`

---

## Track A: _id Handling and Sync Behavior

### Research Questions

1. How does each client (AAPS, Loop/NightscoutKit, Trio, xDrip+) use `_id` vs `identifier` vs `syncIdentifier`?
2. What is the impact of `UUID_HANDLING` quirk on each client?
3. Are `ObjectId()` validation changes breaking for any client?

### Matrix: Client _id Behavior

| Client | Collection | Field Sent to `_id` | Uses `identifier`? | Uses `syncIdentifier`? | UUID_HANDLING Impact |
|--------|------------|---------------------|-------------------|----------------------|---------------------|
| **Loop (NightscoutKit)** | treatments | String `id` field or `nil` | ❌ No | ✅ Yes (stored separate) | ⚠️ **CRITICAL**: Reads `_id` from server response |
| **Loop overrides** | treatments | Same as treatments | ❌ No | ✅ Yes (stored separate) | ⚠️ **CRITICAL**: Same pattern |
| **Trio** | entries | String `id` field or `nil` | ❌ No | ❌ No | 🟢 **LOW**: Uses own `id` field |
| **Trio** | treatments | String `id` field or `nil` | ❌ No | ❌ No | 🟢 **LOW**: Uses own `id` field |
| **AAPS** | treatments | Derived from `nightscoutId` | ❌ No | ❌ No (uses `nightscoutId`) | 🟡 **MEDIUM**: Uses `interfaceIDs.nightscoutId` |
| **AAPS** | devicestatus | Derived from `nightscoutId` | ❌ No | ❌ No (uses `nightscoutId`) | 🟡 **MEDIUM**: Same pattern |
| **xDrip+** | treatments | *(Not analyzed this iteration)* | | | |
| **xDrip+** | entries | *(Not analyzed this iteration)* | | | |

### Work Items

| ID | Title | Description | Status |
|----|-------|-------------|--------|
| `report-a1` | Document Loop/NightscoutKit _id patterns | Analyze `externals/NightscoutKit/` for _id usage | ✅ Complete 2026-03-18 |
| `report-a2` | Document AAPS _id patterns | Analyze `externals/AndroidAPS/` NSClient code | ✅ Complete 2026-03-18 |
| `report-a3` | Document Trio _id patterns | Analyze `externals/Trio-dev/` Nightscout sync | ✅ Complete 2026-03-18 |
| `report-a4` | Document xDrip+ _id patterns | Analyze `externals/xDrip/` NSClient code | 📋 Ready |
| `report-a5` | Compile _id behavior matrix | Fill in matrix above with evidence | ✅ Complete 2026-03-18 (Loop, AAPS, Trio) |

### Source Locations

| Client | Key Files |
|--------|-----------|
| NightscoutKit | `externals/NightscoutKit/Sources/NightscoutKit/NightscoutClient.swift` |
| AAPS | `externals/AndroidAPS/plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/` |
| Trio | `externals/Trio-dev/FreeAPS/Sources/Services/Network/NightscoutAPI.swift` |
| xDrip+ | `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/cloud/` |

---

## Track B: MongoDB Driver Migration

### Research Questions

1. Which `insert()` calls changed to `insertOne()` / `insertMany()`?
2. Which operations now use `bulkWrite()` for batch operations?
3. Are there `ObjectID()` vs `new ObjectId()` compatibility issues?

### Matrix: Storage Method Changes

| File | Old Method (v14.2.5) | New Method (Current) | Batch Support | Code Citations | Verified |
|------|----------------------|---------------------|---------------|----------------|----------|
| `lib/server/treatments.js` | `api().update(query, obj, {upsert: true})` | `api().bulkWrite([{replaceOne}])` | ✅ Array batch via bulkWrite | **Old:** `externals/cgm-remote-monitor-official@1ad48672:lib/server/treatments.js:49,73`<br>**New:** `cgm-pr-8447/lib/server/treatments.js:64` | ✅ 2026-03-18 |
| `lib/server/entries.js` | `api().update(query, doc, {upsert: true})` | `api().bulkWrite([{replaceOne}])` | ✅ Array batch via bulkWrite | **Old:** `externals/cgm-remote-monitor-official@1ad48672:lib/server/entries.js:110`<br>**New:** `cgm-pr-8447/lib/server/entries.js:130` | ✅ 2026-03-18 |
| `lib/server/profile.js` | `api().insert(obj)` (single only) | `api().insertMany([docs])` + `insertOne(obj)` | ✅ Array→insertMany, Single→insertOne | **Old:** `externals/cgm-remote-monitor-official@1ad48672:lib/server/profile.js:11`<br>**New:** `cgm-pr-8447/lib/server/profile.js:26,43` | ✅ 2026-03-18 |
| `lib/server/devicestatus.js` | `api().insertOne(obj)` (already v5 compatible) | `api().insertMany([docs])` (enhanced) | ✅ Array batch via insertMany | **Old:** `externals/cgm-remote-monitor-official@1ad48672:lib/server/devicestatus.js:26`<br>**New:** `cgm-pr-8447/lib/server/devicestatus.js:56` | ✅ 2026-03-18 |
| `lib/server/activity.js` | `api().insert(obj)` (single only) | `api().bulkWrite([{replaceOne}])` | ✅ Array batch via bulkWrite | **Old:** `externals/cgm-remote-monitor-official@1ad48672:lib/server/activity.js:11`<br>**New:** `cgm-pr-8447/lib/server/activity.js:29` | ✅ 2026-03-18 |
| `lib/server/food.js` | `api().insert(obj)` + `api().save(obj)` (single only) | `api().bulkWrite([{replaceOne}])` | ✅ Array batch via bulkWrite | **Old:** `externals/cgm-remote-monitor-official@1ad48672:lib/server/food.js:8,26`<br>**New:** `cgm-pr-8447/lib/server/food.js:29,78` | ✅ 2026-03-18 |

### Work Items

| ID | Title | Description | Status |
|----|-------|-------------|--------|
| `report-b1` | Audit treatments.js storage changes | Compare worktree vs v14.2.5 | ✅ Complete 2026-03-18 |
| `report-b2` | Audit entries.js storage changes | Compare worktree vs v14.2.5 | ✅ Complete 2026-03-18 |
| `report-b3` | Audit profile.js storage changes | Compare worktree vs v14.2.5 | ✅ Complete 2026-03-18 |
| `report-b4` | Audit devicestatus.js storage changes | Compare worktree vs v14.2.5 | ✅ Complete 2026-03-18 |
| `report-b5` | Audit activity.js storage changes | Compare worktree vs v14.2.5 | ✅ Complete 2026-03-18 |
| `report-b6` | Audit food.js storage changes | Compare worktree vs v14.2.5 | ✅ Complete 2026-03-18 |
| `report-b7` | Compile storage method matrix | Fill in matrix above | ✅ Complete 2026-03-18 |

### Comparison Commands

```bash
# Compare current vs v14.2.5
cd externals/cgm-remote-monitor-official
git show 1ad48672:lib/server/treatments.js > /tmp/old.js
diff /tmp/old.js /home/bewest/src/worktrees/nightscout/cgm-pr-8447/lib/server/treatments.js
```

---

## Track C: Data Shape Consistency

### Research Questions

1. Does each endpoint handle single object AND array input?
2. Does each endpoint return consistent response format (array)?
3. How does API v3 envelope differ from API v1?

### Matrix: Input Shape Handling

| Endpoint | Single Object | Array `[1]` | Batch `[n]` | Empty `[]` | Response Format |
|----------|---------------|-------------|-------------|------------|-----------------|
| **API v1** | | | | | |
| `/api/v1/treatments` | | | | | |
| `/api/v1/entries` | | | | | |
| `/api/profile` | | | | | |
| `/api/devicestatus` | | | | | |
| `/api/activity` | | | | | |
| `/api/food` | | | | | |
| **API v3** | | | | | |
| `/api/v3/treatments` | | | | | |
| `/api/v3/entries` | | | | | |
| `/api/v3/devicestatus` | | | | | |
| `/api/v3/profile` | | | | | |

### API v3 Envelope Structure

API v3 uses a consistent message envelope:

```javascript
// Request: single document (not array)
POST /api/v3/treatments
{
  "eventType": "Carbs",
  "carbs": 30,
  "device": "Loop",
  "date": 1234567890000
}

// Response: single object with metadata
{
  "status": 201,
  "identifier": "abc123...",
  "lastModified": 1234567890000
}
```

### Work Items

| ID | Title | Description | Status |
|----|-------|-------------|--------|
| `report-c1` | Test API v1 treatments shape handling | Single, array, batch, empty | 📋 Ready |
| `report-c2` | Test API v1 entries shape handling | Single, array, batch, empty | 📋 Ready |
| `report-c3` | Test API v1 profile shape handling | Single, array, batch, empty | 📋 Ready |
| `report-c4` | Test API v1 devicestatus shape handling | Single, array, batch, empty | 📋 Ready |
| `report-c5` | Test API v1 activity shape handling | Single, array, batch, empty | 📋 Ready |
| `report-c6` | Test API v1 food shape handling | Single, array, batch, empty | 📋 Ready |
| `report-c7` | Document API v3 envelope behavior | Compare to v1, verify consistency | 📋 Ready |
| `report-c8` | Compile shape handling matrix | Fill in matrix above | 📋 Ready |

---

## Key Findings (2026-03-18)

### **NEW**: Client _id Usage Patterns Analysis (2026-03-18)

**Critical Discovery**: Loop/NightscoutKit has the **highest UUID_HANDLING dependency** risk.

#### Loop/NightscoutKit Evidence (`externals/NightscoutKit/`)

**Pattern**: Sends `id` field to `_id`, stores `syncIdentifier` separately, **reads `_id` from server responses**

| File | Line | Code Evidence | Impact |
|------|------|---------------|--------|
| `NightscoutClient.swift` | 418 | `rep["_id"] = id` (profile uploads) | ⚠️ Sends string to `_id` |
| `NightscoutClient.swift` | 494-495 | `if let id = entry["_id"] as? String { return id }` | 🔴 **CRITICAL**: Expects string from server |
| `NightscoutTreatment.swift` | 85 | `let identifier = entry["_id"] as? String` (server response parsing) | 🔴 **CRITICAL**: Expects string from server |
| `NightscoutTreatment.swift` | 111 | `rval["_id"] = id` (upload serialization) | ⚠️ Sends `String?` to `_id` |
| `NightscoutTreatment.swift` | 117 | `rval["syncIdentifier"] = syncIdentifier` | ✅ Uses separate sync field |

**UUID_HANDLING Impact**: 🔴 **CRITICAL** - Loop **expects** `_id` values returned from Nightscout to be strings, not ObjectIds. If UUID_HANDLING is disabled, Loop will fail to parse responses containing ObjectId values.

#### AAPS Evidence (`externals/AndroidAPS/plugins/sync/`)

**Pattern**: Uses `interfaceIDs.nightscoutId` system, likely sends ObjectId-compatible values

| File | Line | Code Evidence | Impact |
|------|------|---------------|--------|
| `NSClientPlugin.kt` | 219-230 | `dataPair.value.ids.nightscoutId` (all data types) | 🟡 Uses dedicated nightscout ID tracking |

**UUID_HANDLING Impact**: 🟡 **MEDIUM** - AAPS uses `interfaceIDs.nightscoutId` system suggesting it handles ObjectId format correctly.

#### Trio Evidence (`externals/Trio-dev/Trio/Sources/`)

**Pattern**: Uses simple `id` field, no dedicated sync identifier system

| File | Line | Code Evidence | Impact |
|------|------|---------------|--------|
| `NightscoutAPI.swift` | 299-320 | `JSONCoding.encoder.encode(treatments)` (direct encoding) | 🟢 Simple JSON encoding |
| `NightscoutTreatment.swift` | 24 | `var id: String?` (model field) | 🟢 String field, flexible |

**UUID_HANDLING Impact**: 🟢 **LOW** - Trio uses optional string `id` field, likely compatible with ObjectId format.

### Compatibility Risk Assessment

| Client | Risk Level | Rationale | Required Testing |
|--------|------------|-----------|------------------|
| **Loop** | 🔴 **HIGH** | Expects `_id` as string in server responses | Test Loop parsing ObjectId responses |
| **AAPS** | 🟡 **MEDIUM** | Uses `nightscoutId` system (ObjectId-aware?) | Test AAPS with UUID_HANDLING disabled |
| **Trio** | 🟢 **LOW** | Uses optional string `id` field | Basic compatibility testing |

### New Findings: activity.js and food.js Migration (2026-03-18)

**Activity.js Changes:**
- `create()` function completely rewritten from single `insert()` to array-based `bulkWrite()`
- Function signature changed: `create(obj, fn)` → `create(docs, fn)` expecting array input
- Single objects still supported through array normalization
- `save()` method migrated from `save()` to `insertOne()` 
- `remove()` migrated from `remove()` to `deleteOne()`

**Food.js Changes:**
- Both `create()` and `save()` functions rewritten to support array inputs via `bulkWrite()`
- Function signatures changed to accept single objects OR arrays
- Array normalization: `if (!Array.isArray(docs)) docs = [docs]`
- Consistent error handling with batch operations
- `remove()` migrated from `remove()` to `deleteOne()`

**Common Pattern Observed:**
All storage files now follow the pattern:
1. Accept single object OR array input
2. Normalize to array: `if (!Array.isArray(docs)) docs = [docs]`
3. Use `bulkWrite([{replaceOne: {filter, replacement, upsert: true}}])` for batch upserts
4. Handle empty arrays gracefully: `if (docs.length === 0) return fn(null, [])`
5. Assign `_id` from `bulkResult.upsertedIds` for new documents

### ObjectID → ObjectId Migration

**Breaking Change**: `require('mongodb').ObjectID` → `require('mongodb-legacy').ObjectId`

| File | v14.2.5 | Current | Code Citations | Impact |
|------|---------|---------|----------------|--------|
| treatments.js | `ObjectID = require('mongodb').ObjectID` | `ObjectID = require('mongodb-legacy').ObjectId` | **Old:** `@1ad48672:treatments.js:9`<br>**New:** `cgm-pr-8447/treatments.js:9` | ⚠️ Legacy wrapper needed |
| entries.js | `ObjectID = require('mongodb').ObjectID` | `ObjectId = require('mongodb-legacy').ObjectId` | **Old:** `@1ad48672:entries.js:5`<br>**New:** `cgm-pr-8447/entries.js:5` | ⚠️ Legacy wrapper needed |
| profile.js | `ObjectID = require('mongodb').ObjectID` | `ObjectID = require('mongodb-legacy').ObjectId` | **Old:** `@1ad48672:profile.js:7`<br>**New:** `cgm-pr-8447/profile.js:7` | ⚠️ Legacy wrapper needed |
| `lib/server/activity.js` | `ObjectID = require('mongodb').ObjectID` | `ObjectID = require('mongodb-legacy').ObjectId` | **Old:** `@1ad48672:activity.js:7`<br>**New:** `cgm-pr-8447/activity.js:7` | ⚠️ Legacy wrapper needed |
| `lib/server/food.js` | `ObjectID = require('mongodb').ObjectID` | `ObjectID = require('mongodb-legacy').ObjectId` | **Old:** `@1ad48672:food.js:4`<br>**New:** `cgm-pr-8447/food.js:4` | ⚠️ Legacy wrapper needed |

### Storage Method Migration

**Pattern**: Individual `update(upsert:true)` → `bulkWrite([{replaceOne}])` for batch operations

| Collection | v14.2.5 Method | Current Method | Code Citations | Batch Support |
|------------|-----------------|----------------|----------------|---------------|
| **treatments** | `api().update(query, obj, {upsert: true})` | `api().bulkWrite([{replaceOne: {filter, replacement, upsert}}])` | **Old:** `:49,73`<br>**New:** `:64` | ✅ preBolus fallback to sequential |
| **entries** | `api().update(query, doc, {upsert: true})` | `api().bulkWrite([{replaceOne: {filter, replacement, upsert}}])` | **Old:** `:110`<br>**New:** `:130` | ✅ Full batch support |
| **profile** | `api().insert(obj)` (single only) | `api().insertMany([docs])` + `insertOne(obj)` | **Old:** `:11`<br>**New:** `:26,43` | ✅ Array and single support |
| **activity** | `api().insert(obj)` (single only) | `api().bulkWrite([{replaceOne: {filter, replacement, upsert}}])` | **Old:** `:11`<br>**New:** `:29` | ✅ Array and single support |
| **food** | `api().insert(obj)` + `api().save(obj)` (single only) | `api().bulkWrite([{replaceOne: {filter, replacement, upsert}}])` | **Old:** `:8,26`<br>**New:** `:29,78` | ✅ Array and single support |

### Compatibility Assessment

| Risk Level | Finding | Mitigation |
|------------|---------|------------|
| **🔴 HIGH** | `mongodb-legacy` dependency required for ObjectId compatibility | Using legacy wrapper, monitor deprecation |
| **🟡 MEDIUM** | `bulkWrite()` error handling differs from `update()` | Enhanced error handling implemented |
| **🟢 LOW** | Batch operations now atomic via `bulkWrite` | Improvement over sequential operations |
| **🟢 LOW** | preBolus treatments fall back to sequential processing | Preserves complex business logic |

### Performance Improvements

- **treatments.js**: Array inputs now use single `bulkWrite()` vs multiple `update()` calls
- **entries.js**: Array inputs use single `bulkWrite()` vs multiple `update()` calls  
- **profile.js**: Array inputs use single `insertMany()` vs sequential `insert()` calls
- **devicestatus.js**: Array inputs use single `insertMany()` (enhancement from v14.2.5)
- **activity.js**: Array inputs use single `bulkWrite()` vs sequential `insert()` calls (NEW)
- **food.js**: Both `create()` and `save()` now support array inputs via `bulkWrite()` (NEW)

---

## Evidence Sources

### Current Worktree (changes under test)

```
/home/bewest/src/worktrees/nightscout/cgm-pr-8447/
├── lib/server/     # Storage layer
├── lib/api/        # API v1 handlers
├── lib/api3/       # API v3 handlers
└── tests/          # Test coverage
```

### Previous Release (baseline)

```bash
cd externals/cgm-remote-monitor-official
git show 1ad48672:lib/server/<file>.js   # v14.2.5
git show 03c01d03:lib/server/<file>.js   # v15.0.4
```

### Client Source Code

```
externals/NightscoutKit/     # Loop iOS
externals/AndroidAPS/        # AAPS Android
externals/Trio-dev/          # Trio iOS
externals/xDrip/             # xDrip+ Android
```

---

## Completion Checklist

- [x] Track A: 3 of 5 work items complete ✅ 2026-03-18 (Loop, AAPS, Trio)
- [x] Track A: Client _id matrix filled with evidence ✅ 2026-03-18 (3 clients)
- [x] Track B: All 7 work items complete ✅ 2026-03-18
- [x] Track B: Storage method matrix filled ✅ 2026-03-18
- [ ] Track C: All 8 work items complete
- [ ] Track C: Shape handling matrix filled
- [ ] Final report assembled with citations

---

## Related Documents

- [Profile API Array Regression](profile-api-array-regression.md) - Completed array handling fixes
- [UUID Identifier Lookup](uuid-identifier-lookup.md) - UUID_HANDLING implementation
- [Client ID Handling Deep Dive](../10-domain/client-id-handling-deep-dive.md) - Which apps send UUID to _id
