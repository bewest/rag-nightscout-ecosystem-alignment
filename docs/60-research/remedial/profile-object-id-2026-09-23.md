# A profile posted with its own `_id` is stored with a string `_id`

*Contributor-facing. Snapshot, 2026-09-23. Superseded for the fix: `bf/profile-object-id` will not be
opened; BF-99 is fixed by PR #8758 (`bf/object-id-crud`, open), see
[crud-by-id-matrix](crud-by-id-matrix-2026-09-23.md); item state is in `queue/work-queue.yaml` (`BFQ-99`,
`BFQ-102`). The measurements stand. Measured 2026-09-23 against `origin/dev` `1f9a9d10` (15.0.9; dev moved from
`74fc6619` to `1f9a9d10` on 2026-09-23 when #8752 and #8750 merged, neither touches profiles) and
the shipping release `15.0.8` `92d08342`. Storage: `mongo:7` in Docker. Node 20.20.0 and 22.23.2
via `n exec`. Synthetic profiles only. Every "reproduced" row below was run; rows marked
"read" were not.*

Branch: `bf/profile-object-id` `9b8cc2f9`, one commit on `origin/dev` `1f9a9d10`, local only
(worktree `externals/work/crm-bf-profile-id`). PR body draft:
[`reports/phase0-pr-bodies/bf-profile-object-id.md`](../../../reports/phase0-pr-bodies/bf-profile-object-id.md).

## 1. Mechanism

`lib/server/profile.js` `create()` purifies each document, validates `startDate` and calls
`insertMany(docs)` with `_id` as given. The v1 route (`lib/api/profile/index.js`) accepts a 24-hex
string `_id` and refuses any other string with 400 before storage. So a hex `_id` is stored as a
**string**.

Every other profile path looks the id up as an ObjectId:

| path | code | effect on a string-`_id` profile |
|---|---|---|
| `PUT /api/v1/profile` (profile editor) | `save()`: `new ObjectID(obj._id)`, `replaceOne({_id}, obj, {upsert: true})` | upserts a **second** document with the ObjectId `_id` and the new content; the string original stays |
| `DELETE /api/v1/profile/:_id` | `remove()`: `deleteOne({_id: new ObjectID(_id)})` | removes only an ObjectId twin, if there is one; the string original cannot be deleted through v1 |
| `GET /api/v1/profiles?find[_id]=<hex>` | `lib/server/query.js` `updateIdQuery` converts hex to ObjectId | answers `[]` |
| APIv3 `GET /api/v3/profile/<hex>`, and v3 dedup | `lib/api3/storage/mongoCollection/utils.js` `filterForOne`, `identifyingFilter` | match `identifier` or ObjectId `_id` only; miss the string doc (§4.3) |

Treatments differ: `lib/server/treatments.js` `normalizeTreatmentId` converts a 24-hex string to
ObjectId and drops any other string `_id` (moving it to `identifier` when `UUID_HANDLING` is on).
Profiles had no equivalent.

## 2. Reproduction

`tests/api.profiles.object-id.test.js` (13 tests), run unchanged on each tree.

| tree | passing | failing |
|---|---:|---:|
| `origin/dev` `1f9a9d10` (no fix) | 2 | 11 |
| `15.0.8` `92d08342` (no fix) | 2 | 11 |
| `bf/profile-object-id` `9b8cc2f9` | 13 | 0 |
| `15.0.8` + the commit's `lib/server/profile.js` diff (applies cleanly; not a branch) | 13 | 0 |

Symptoms on both unfixed trees, identical:

- POST with a hex `_id`: stored `_id` is a `string`.
- `find[_id]=<hex>`: 0 results (expected 1).
- PUT of the same `_id` with new content: **2** documents hold that id afterwards.
- DELETE `/profile/:_id` after that: **1** document is left (the string original).
- Array POST: each element stored with a string `_id`.
- A profile seeded directly with a string `_id` (the state operators already have): the same three
  failures; an ObjectId twin plus a string original survives a PUT as two documents and a DELETE
  as one.

The two tests that pass on the unfixed trees pass by design: a POST without `_id` still gets a new
ObjectId, and a POST that re-sends an id already stored as a string is refused on the duplicate
key and adds nothing (the fix must keep that; §3).

## 3. The change

All in `lib/server/profile.js`:

1. **create**: a 24-hex string `_id` is stored as the ObjectId it names (same regex and conversion
   as treatments), unless that exact string is already stored as a profile `_id`; then it is left
   as a string so the insert collides with the stored profile exactly as before. One indexed
   `find` on `_id` per create that carries hex ids.
2. **save**: after the existing ObjectId upsert, `deleteMany({_id: {$in: [<hex string forms>]}})`
   removes the string form of the same id. Upsert first, so the profile is never absent between
   the two writes. A PUT against a string-`_id` profile ends with one ObjectId document holding
   the new content; a string original plus an ObjectId twin collapses to one.
3. **remove**: `deleteMany({_id: {$in: [ObjectId, hex, as-given]}})`, so both forms go.
4. **find[_id]** (`query_for`, behind `/api/v1/profiles`): an ObjectId equality becomes
   `$in: [ObjectId, hex, as-given]`.

No boot-time migration, no bulk write. A string-`_id` profile is converted the first time it is
edited, and deleted by `_id` whichever form it has.

### Non-hex string `_id` (for example a UUID)

**Unchanged: refused with 400 at the v1 route, as on dev and 15.0.8** (existing test
`tests/api.profiles.test.js` "should return 400 for POST with invalid UUID _id"). At the storage
layer a non-hex string is kept as given. Treatments drop it; profiles do not, for two reasons:

- The only v1 route that reaches `create()` already refuses it, so there is no HTTP client to
  accommodate (treatments' UUID path exists because Loop sends override UUIDs to the treatments
  route).
- `ctx.profile.create` is also called in-process by the connector (`lib/outputs/internal.js`),
  which skips profiles it has already stored by comparing `_id` (connector
  `fix/profile-duplicate-stall` `f6359b4`). Dropping the id would make every re-read of a source
  profile a new copy.

### Why create keeps a string that is already stored

Without that guard (measured, break D below), a connector that re-sends a source profile whose
sink copy was stored with a string `_id` by 15.0.8 gets **200 and a second, ObjectId copy** on the
first poll after the upgrade. The unfixed behaviour is a duplicate-key error and one document;
the guard keeps that.

## 4. Other collections and paths (reported, not fixed here)

### 4.1 devicestatus, food, activity: reproduced on dev and 15.0.8

Probe: POST with a 24-hex `_id`, then find / PUT / DELETE by that id, counted in MongoDB.
Identical on `1f9a9d10` and `92d08342`:

| collection | stored `_id` after POST | `find[_id]` | after PUT | after DELETE `/:id` |
|---|---|---:|---|---|
| devicestatus | string | 0 | (no PUT route) | string kept; `deletedCount: 0` |
| food | string | (not probed) | string + ObjectId (duplicate) | string kept |
| activity | string | 0 | string + ObjectId (duplicate) | string kept |

`food.create` and `activity.create` use `replaceOne({_id: doc._id}, …, {upsert: true})` with the
id as given; `devicestatus.create` uses `insertMany` as given. Each needs its own register entry.
devicestatus has a likely writer (read, not probed): the connector's Nightscout source
(`v0.0.13` `lib/sources/nightscout.js:168`) copies devicestatus rows as the source's
`/api/v1/devicestatus.json` returns them, `_id` included, into `ctx.devicestatus.create`.

### 4.2 Websocket `dbAdd` (read)

`lib/server/websocket.js` `processSingleDbAdd` inserts `data.data` with its `_id` as given, for
every supported collection including `profile`; `hasSafeDedupFields` accepts a string `_id`. So the
socket path can still store a string `_id` for any collection. Not probed. AAPS's v1 socket upload
of profiles sends no `_id` (below), so no known client hits it.

### 4.3 APIv3 single-document lookup: reproduced at the storage layer

With a profile stored with a string `_id`, `filterForOne(hex)` and `identifyingFilter(hex)` each
match 0 documents; with the same id as ObjectId, `filterForOne` matches 1. Same on both trees. The
v3 route itself was not booted (it needs v3 auth); the filters are what it queries with. After this
fix a string-`_id` profile becomes reachable through v3 once it is edited through v1. The filters
are shared by every v3 collection, so a fix there is its own change.

## 5. Who sends a profile with `_id`

Read from source, with each repository's HEAD:

| client | sends `_id` in a profile upload | where |
|---|---|---|
| nightscout-connect, Nightscout source (every version: `v0.0.13` on 15.0.8, `234d47c` on dev, `v0.1.0-dev.2`) | **yes**, the source's `_id` | `lib/sources/nightscout.js` reads `/api/v1/profile.json`; `lib/outputs/internal.js` calls `ctx.profile.create(rows)` in-process |
| anyone restoring an export through v1 POST | yes, if the export kept `_id` | — |
| AndroidAPS `598e2eb39c` | no | `plugins/main/.../profile/ProfilePlugin.kt:398-431` (`createProfileStore`); v3 and v1-socket paths add no `_id` |
| Loop (NightscoutKit `4ec9fd1`) | no on POST | `Sources/NightscoutKit/Models/ProfileSet.swift:143-165`; `updateProfile` sets `_id` for a PUT but nothing in LoopWorkspace, LoopCaregiver or Trio calls it |
| Trio `40f097fdd` | no | `Trio/Sources/Models/NightscoutStatus.swift:51-64`, `NightscoutManager.swift:843-856` |
| xDrip, xdripswift, LoopCaregiver, nightscout-reporter | do not upload profiles | reads only |

This agrees with `docs/backlogs/profile-api-array-regression.md:400-411`.

The connector's `fix/profile-duplicate-stall` skip check compares `'id:' + String(p._id)`;
`String()` of an ObjectId is its lower-case hex, so it matches profiles stored by this change and
profiles stored as strings before it.

## 6. Why it matters (read, not measured)

The reports load every profile in their date range from `/api/v1/profiles`
(`lib/report/reportclient.js` `loadProfilesRange*`): Day to day (basal, and `iob.calcTotal`'s
profile fallback), Loopalyzer, and the Profiles report. A stale string copy beside an edited
ObjectId copy is one more profile those reports can read for the same period. The report output
with duplicates was not measured. On a connector sink, the profile editor edits a copy it then
cannot replace or delete.

## 7. Suite and break-its

Full suite (`mocha --timeout 5000 --require ./tests/hooks.js --exit ./tests/*.test.js`, `mongo:7`):

| tree | Node 20.20.0 | Node 22.23.2 |
|---|---|---|
| `origin/dev` `1f9a9d10` | 2386 / 0 / 3 | 2386 / 0 / 3 |
| `bf/profile-object-id` `9b8cc2f9` | 2399 / 0 / 3 | 2399 / 0 / 3 |

+13, exactly the new file. No existing test changed.

Break-its (new test file, Node 20.20.0), each with one part of the fix removed:

| removed | red | symptom |
|---|---:|---|
| A: create conversion | 2 | stored `_id` is a string (single and array POST) |
| B1: save's delete of the string form | 3 | 2 documents after PUT (legacy, upper-case legacy, twins) |
| B2: find[_id] dual match | 2 | 0 results, expected 1 |
| B3: remove's dual match (back to `deleteOne` ObjectId) | 2 | 1 document left after DELETE |
| B1+B2+B3: all dual-type matching | 6 | [] on find, duplicate after PUT, delete not removing |
| D: create's "already stored as string" guard | 1 | re-sent POST answers 200 (expected 500) and adds an ObjectId copy |

A first B2 attempt broke the file's syntax and failed for that reason; it was discarded and rerun
with the branch disabled by a condition.

## 8. Interplay with open 15.0.9 work

`git merge-tree --write-tree` of `9b8cc2f9` against each head: no conflict with #8748
`d19043b2`, #8749 `46b20b38`, #8751 `b5038500`, #8753 `e6a50e9a`, #8754 `0a74ef4e`, #8755
`92544d8f`, #8756 `83cfff14`, #8752 `adf5120c` (already in dev), or `rc/15.0.9-additions-e`
`1b1977e0`. #8748 and `1b1977e0` also touch `lib/server/profile.js` (`list()`'s zero count);
both merge cleanly. The merged tree with `1b1977e0` passes the profile and count-parameter test
files (112/0).

`chore/nightscout-modernization` `b1bdaca0` has the same defect: its `lib/server/profile.js`
`create()` inserts `_id` as given, and `save()`/`remove()` are dev's. The merge-tree against it
auto-merges `lib/server/profile.js`; its conflicts (`README.md`, `lib/server/bootevent.js`,
`package.json`, `package-lock.json`) are the same four that `origin/dev` alone has against it.
