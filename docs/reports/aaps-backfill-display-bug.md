# AAPS Backfill Display Bug — Root Cause Analysis

**Date:** 2026-07-23  
**Context:** PR [#8444](https://github.com/nightscout/cgm-remote-monitor/pull/8444) / dev branch  
**Reported by:** AAPS user (Discord)  
**Worktree:** `/home/bewest/src/worktrees/nightscout/cgm-pr-8447`  
**Test file:** `tests/cache-objectid-compat.test.js`

---

## 1. Symptom

An AAPS user who uploads only while charging reports:

1. Switching to `latest_dev` container creates gaps in the chart.
2. Each time AAPS upload starts, **past (backfilled) data does not appear**.
3. The data **IS in MongoDB** — reverting to v15.0.6 shows it immediately.
4. The gaps recur consistently; not a one-time switchover artifact.

## 2. Confirmed Bug: `_.isEmpty(ObjectId)` Behavioral Change

### Discovery

The MongoDB driver upgrade from v3.6 (`mongodb`) to v5.9 (`mongodb-legacy`)
changed the `ObjectId` class internals. The new `ObjectId` stores its value
in a private buffer with **no enumerable own properties**:

```js
// mongodb driver 3.x (v15.0.6)
Object.keys(new ObjectID())  // → ['_bsontype', 'id']
_.isEmpty(new ObjectID())    // → false ✓

// mongodb driver 5.x (dev, via mongodb-legacy)
Object.keys(new ObjectId())  // → []
_.isEmpty(new ObjectId())    // → true ✗ ← BUG
```

### Impact on `cache.js:filterForAge()`

`lib/server/cache.js` line 52–58 uses `!_.isEmpty(object._id)` as the `hasId`
validity check in `filterForAge()`:

```js
function filterForAge(data, ageLimit) {
  return _.filter(data, function hasId(object) {
    const hasId = !_.isEmpty(object._id);  // ← BROKEN for ObjectId instances
    const age = getObjectAge(object);
    const isFresh = age >= ageLimit;
    return isFresh && hasId;
  });
}
```

Any document whose `_id` is an `ObjectId` instance (rather than a string) is
**silently filtered out** of the cache.

### Existing Mitigation

`ddata.processRawDataForRuntime()` (lib/data/ddata.js:36) converts `_id`
to a string:

```js
if (Object.prototype.hasOwnProperty.call(obj[key], '_id')) {
  obj[key]._id = obj[key]._id.toString();  // ObjectId → "hex string"
}
```

All V1 code paths (WebSocket `dbAdd`, `entries.js:create()`, `treatments.js`)
call `processRawDataForRuntime()` before emitting `data-update`, so entries
enter the cache with string `_id` and pass `filterForAge()`.

### Unmitigated Code Path: API V3 `mongoCachedCollection`

`lib/api3/storage/mongoCachedCollection/index.js:30` emits `data-update`
with the **raw document** (ObjectId `_id`), without `processRawDataForRuntime`:

```js
self.insertOne = async (doc) => {
  const result = await baseStorage.insertOne(doc, { normalize: false });
  if (cacheSupported()) {
    updateInCache([doc]);  // ← raw ObjectId _id, NOT string
  }
  ...
};
```

For AAPS users on NSClientV3 (API V3), entries uploaded via
`POST /api/v3/entries` go through this path. The `data-update` event carries
a document with ObjectId `_id`, which `filterForAge` rejects. The entry is
**not cached** via the `data-update` path.

The entry IS still loaded by the dataloader (which uses
`processRawDataForRuntime` and queries MongoDB directly), so it eventually
appears — but timing-dependent issues can cause gaps.

### Recommended Fix

Replace `!_.isEmpty(object._id)` with a null/empty check:

```js
// Before (broken with ObjectId instances):
const hasId = !_.isEmpty(object._id);

// After (works with ObjectId, string, and undefined):
const hasId = object._id != null && object._id !== '';
```

### Test Coverage

`tests/cache-objectid-compat.test.js` — 7 tests confirming:
- `_.isEmpty(ObjectId)` returns `true` (regression confirmed)
- `filterForAge` rejects ObjectId `_id` documents
- `processRawDataForRuntime` mitigates by converting to string
- Proposed fix `_id != null && _id !== ''` works correctly

## 3. Contributing Factor: Debounce Removal

### Change

| Version | `updateData` behavior | Source |
|---------|----------------------|--------|
| v15.0.6 | `_.debounce(fn, 5000)` — coalesces rapid events into one call after 5s quiet | `bootevent.js:4`, `bootevent.js:289` |
| dev (intermediate) | `_.debounce(fn, 15000)` — 15s delay | commit `1107e84a` (#8026 re-applied) |
| dev (current) | No debounce — immediate call | commit `5a9ffb12` |

### Impact on AAPS Backfill

When AAPS starts uploading backfill (50+ entries, one at a time, oldest first):

**v15.0.6 (debounce):** All `data-received` events coalesce → ONE dataloader
run after 5s of quiet → queries MongoDB with `TWO_DAYS` window (cache
typically sparse after idle period) → gets ALL entries including old backfill.

**dev (no debounce):** EVERY entry triggers an immediate dataloader run →
first run populates cache → subsequent runs use `FIFTEEN_MINUTES` window →
old backfill entries (hours old) NOT in 15-minute MongoDB query → BUT should
be preserved in cache from `data-update` events.

### Race Condition with Concurrent Dataloaders

Without debounce, N concurrent `dataloader.update()` calls run on the
**same shared `ddata` object**:

1. Run A: `ddata.entries = []` → starts 9 parallel MongoDB queries
2. Run B: `ddata.entries = []` → starts 9 more queries (overwrites A's state)
3. Callbacks interleave, writing to the same `ddata.sgvs`, `ddata.treatments`
4. Each `loadComplete` emits `data-loaded` → WebSocket delta to clients

The race produces transient mixed states. While `nsArrayDiff` (used for sgvs)
only sends additions (not deletes), `nsArrayTreatments` DOES send `action:
'remove'` for missing items — so treatments could flicker.

## 4. `bulkWrite` Missing `_id` for Matched Entries

`lib/server/entries.js:create()` changed from individual `update()` (per
entry) to batch `bulkWrite()`. After bulkWrite, only **upserted** documents
get `_id` from `bulkResult.upsertedIds`. Matched/updated documents retain
whatever `_id` was set before (often `undefined` for AAPS entries that don't
send `_id`).

These `_id`-less entries are included in the `data-update` event. After
`processRawDataForRuntime`, entries without `_id` have `_id = undefined`.
`filterForAge` rejects them (`_.isEmpty(undefined) → true`).

On v15.0.6 (individual `update()`): each entry got its own `data-update`
event, and matched entries also lacked `_id`. Same issue existed but was
less impactful due to debounce batching.

## 5. Data Flow Comparison

### v15.0.6 Flow (working)

```
AAPS upload → [entries arrive in MongoDB] →
  data-update (cache each entry, string _id via processRawDataForRuntime) →
  data-received × N →
  DEBOUNCE (5s) →
  ONE dataloader run →
    cache sparse? → TWO_DAYS query → gets ALL entries ✓
    cache full? → 15 MIN query + cache merge → old entries preserved ✓
  → data-loaded → data-processed → WebSocket delta → chart ✓
```

### dev Flow (broken)

```
AAPS upload → [entries arrive in MongoDB] →
  data-update (cache each entry, string _id via processRawDataForRuntime) →
  data-received →
  IMMEDIATE dataloader run →
    [concurrent with next entry's data-received → ANOTHER dataloader] →
    race condition on shared ddata →
    cache merge OK for entries in cache →
    BUT treatments may flicker (nsArrayTreatments sends 'remove') →
  → data-loaded → data-processed → WebSocket delta → chart (possibly stale)
```

### API V3 Flow (AAPS NSClientV3)

```
AAPS upload → POST /api/v3/entries →
  mongoCachedCollection.insertOne →
  data-update with RAW ObjectId _id →
    filterForAge REJECTS entry (_.isEmpty bug) →
    entry NOT cached ✗
  data-received →
  dataloader run →
    processRawDataForRuntime → string _id → cache.insertData →
    entry NOW in cache ✓ (delayed)
```

## 6. Summary of Findings

| Finding | Severity | Status | Fix |
|---------|----------|--------|-----|
| `_.isEmpty(ObjectId)` returns `true` on driver 5.x | **High** | Confirmed, tested | Replace with `_id != null && _id !== ''` |
| mongoCachedCollection bypasses processRawDataForRuntime | Medium | Confirmed | Add processRawDataForRuntime call or fix filterForAge |
| Debounce removal causes concurrent dataloader runs | Medium | Confirmed | Re-add debounce or add concurrency guard |
| bulkWrite doesn't populate `_id` for matched entries | Low | Confirmed | Query MongoDB for matched entry _ids, or accept |
| Treatment delta sends 'remove' for transiently missing items | Low | Hypothesis | Needs investigation |

## 7. Actions Taken

### ✅ 7.1 Fix Applied: `filterForAge` hasId check

Commit `f4e686c1` in `wip/test-improvements` branch.

**One-line fix in `lib/server/cache.js:54`:**
```diff
- const hasId = !_.isEmpty(object._id);
+ const hasId = object._id != null && object._id !== '';
```

This resolves the ObjectId compatibility issue throughout the cache layer.
Both V1 (WebSocket) and V3 (REST API) paths now correctly accept ObjectId
`_id` values.

**Test coverage (16 tests, all pass):**
- 3 root-cause tests confirming `_.isEmpty(ObjectId)` regression
- 7 filterForAge logic tests (old broken vs fixed behavior)
- 6 integration tests exercising actual `cache.js` with `data-update` events

### Remaining Recommendations

1. **Re-add debounce to `updateData`** — A 2–5 second debounce prevents
   concurrent dataloader runs and reduces MongoDB query load during bulk
   uploads. The original 5s debounce in v15.0.6 was battle-tested.
   This is a **performance issue**, not a correctness bug.

2. **Add `processRawDataForRuntime` to `mongoCachedCollection`** — Ensure
   API V3 `data-update` events have string `_id` for cache compatibility.
   After the filterForAge fix, ObjectId `_id` works, but converting to
   string is still good practice for consistency.

3. **Ask the reporting user** which AAPS sync plugin they use (NSClient V1
   vs NSClientV3) to narrow down whether the API V3 cache path is involved.

## 8. Files Analyzed

| File | Role | Changed (dev vs v15.0.6) |
|------|------|--------------------------|
| `lib/server/cache.js` | Server-side data cache | **No** (unchanged — latent bug) |
| `lib/data/ddata.js` | Data processing, processRawDataForRuntime | Yes (endmills, identifier merge) |
| `lib/data/dataloader.js` | Periodic data loading from MongoDB | **No** (unchanged) |
| `lib/server/bootevent.js` | Event wiring, debounce | **Yes** (debounce removed) |
| `lib/server/entries.js` | Entries CRUD | **Yes** (bulkWrite, normalizeEntryId) |
| `lib/server/websocket.js` | WebSocket dbAdd handler | **Yes** (insertOne, safeObjectID) |
| `lib/api3/storage/mongoCachedCollection/` | API V3 cached storage | **No** (unchanged — latent bug) |
| `lib/data/calcdelta.js` | WebSocket delta calculation | **No** (unchanged) |
| `lib/storage/mongo-storage.js` | MongoDB connection | **Yes** (mongodb-legacy, pool config) |
