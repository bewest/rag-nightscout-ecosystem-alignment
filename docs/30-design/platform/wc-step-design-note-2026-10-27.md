# WC-STEP-PATCH: mapping the write step onto `dev` `db3b9e4e`

*Contributor-facing design note, milestone 1 of WC-STEP-PATCH (decision Q6 (a), first release:
the step with today's write matrix pinned, no behaviour change).* Written 2026-10-27 against
`cgm-remote-monitor` `official/dev` `db3b9e4e` (the merge of #8872). Every claim carries a mark:
**[M]** measured in this milestone (commands in §7), **[R]** read from source at `db3b9e4e`, not
run. `file:line` is at `db3b9e4e` unless it names the branch `feat/write-intent`.

The specification is `docs/30-design/tenancy/write-contract-spec-2026-10-07.md` (§2 the step, §5
gates, §6.1 decisions). It was written against `43289dde`, before the storage seam landed. This
note says where its pieces are now, and what the step has to do on the code as it is.

---

## 0. The rule, and the gate that holds it

**Decided 2026-10-27 (maintainer): a new write rule goes into `lib/storage/write-intent.js`, not into a
route.** This applies from now on, before every collection is enrolled. §3 below lists the copies that
already exist outside any step; the slices move them in.

Two gates hold it:

- **G2** (`scripts/check-write-intent.js` on the branch): an enrolled module writes only through
  `write(intent)`. Its coverage grows as each slice enrols a module.
- **Write-rule copies** (`tools/queue/gates/write-rule-copies.js`, control
  `write-rule-copies-control.sh`): for seven rule modules (merge-patch, the BF-194 units helper,
  write-validation, validated-update, srv-dates, object-id-forms, the treatment fallback key), it counts
  the lines in each other file under `lib/` and `bin/` that use the rule. It fails on a new (rule, file)
  pair or a grown count against `write-rule-copies.baseline.json`. The baseline was measured on `dev`
  `db3b9e4e`: 47 pairs. On `feat/write-intent` (slice 1) it reads 45: food's `srv-dates` and
  `object-id-forms` copies are gone. The count can only go down; the baseline is re-written after a
  slice moves a copy into the step, never to make a failure pass.

**Progress, 2026-10-27 late.** Slices 1-3 are built on local `feat/write-intent` (`2b9d3687`, `84e21a66`,
`f0d51ee7`, `a0e7fcac`), each with G1 at 0 of 360 cells. The slice list below is revised: slice 3 covers
the socket's generic `dbAdd` (entries, food, activity) and `dbRemove` (all six); a new slice 6 takes the
socket's `dbAdd` for treatments, devicestatus and profile (the `near` match, WRITE_VALIDATION, BF-194, the
`refused`/`failed` slots) plus `dbUpdate`/`dbUpdateUnset`, retiring `idMatch` (new question **Q-I**: until
then the step's `id-match` duplicates it). Matrix gaps found: no form PUTs over a stored string twin, reads
an `_id` that fails, or removes by a custom or numeric `_id`; those are covered by unit tests only.

## 1. Placement: two layers, not one

The spec (§2.1) puts `write(intent)` in `lib/storage/write-step.js`, "applied in `collectionFor`
above both adapters". On `db3b9e4e` that file name is taken by a different layer, and
`collectionFor` does not exist.

What exists [R]:

```
 lib/server/{entries,treatments,devicestatus,profile,food,activity}.js   (API v1 + in-process)
 lib/server/websocket.js  dbAdd / dbUpdate / dbUpdateUnset / dbRemove      (socket)
 lib/api3/generic/{create,update,patch,delete}                             (API v3)
          |                                   |
          |  lib/server/storage-writes.js     |  lib/api3/storage/mongoCachedCollection
          |  (v1 query doc -> filter AST)     |  (cache events, then delegates)
          v                                   v
 lib/api3/storage/mongoCollection  = THE STORAGE INTERFACE (one per collection and source label)
   writes: insertOne, insertMany, replaceOne(identifier), updateOne(identifier), deleteOne,
           updateEveryForm, deleteEveryForm, deleteManyOr, deleteMany(ast), updateMany(ast),
           replaceFiltered(ast), bulkUpsert(ops)
          |
          v
 lib/storage/write-step.js  = THE PERSISTENCE BOUNDARY: a Proxy over the driver collection;
   one driver call -> one `storage-write-committed` event; socket treatment validation;
   the conditional validated update (compare-and-set) for treatments in reject mode
          |
          v
 MongoDB driver collection
```

- The storage interface is `MongoCollection` (`lib/api3/storage/mongoCollection/index.js:20-101`).
  Its writes are listed at `index.js:68-100`; each is handed `col`, the write-step proxy
  (`index.js:43`). API v1 and the socket acquire it through `lib/server/storage-reads.js:34-37`
  with a source label (`MongoCollection.SOURCES`, `index.js:140-145`: `v1/internal`, `v3`,
  `socket`, `internal`). API v3 reaches it through `mongoCachedCollection`
  (`lib/api3/storage/mongoCachedCollection/index.js:10-159`), which adds cache `data-update`
  emissions around the same methods. [R]
- `lib/storage/write-step.js` is **below** the interface: `collection()` (`write-step.js:96-107`)
  wraps the driver collection; `write()` (`write-step.js:70-94`) makes one driver call and
  `publish()` (`write-step.js:57-68`) emits `storage-write-committed` once per call. [R]
- The next-gen plan already records the naming decision: "the intent layer gets its own name"
  (`next-gen-platform-plan.md:45`) [R].

**So the step is a second layer, above the interface.** In `feat/write-intent` it is
`lib/storage/write-intent.js`. It calls only storage-interface methods, never the driver, and it
emits nothing; the commit event stays exactly where #8854 put it. Nothing in this milestone
changes `write-step.js` or the event (D-EVENT is deferred, and session -2e's `crm-devent-*`
trees prototype that change).

**Adapter methods the step calls, against the spec's seam list (§2.1:
`findFiltered, insertMany, bulkUpsert, replaceFiltered, updateMany, deleteMany`)** [R]:

| path today | interface methods it writes with | in the seam list? |
|---|---|---|
| v1 / in-process (via `storage-writes.js:21-70`) | `bulkUpsert`, `replaceFiltered`, `updateMany`, `deleteMany`, `insertMany` (devicestatus `devicestatus.js:196`, profile `profile.js:153`) | yes |
| socket (`websocket.js`) | `insertOne` (`websocket.js:784-787`), `updateMany` and `replaceFiltered` and `deleteMany` via `storage-writes` | `insertOne` is **not** |
| API v3 (`api3/generic/*`) | `insertOne`, `replaceOne(identifier)`, `updateOne(identifier)`, `updateEveryForm`, `deleteEveryForm` (`create/insert.js:40`, `update/replace.js:46`, `patch/operation.js:116`, `delete/operation.js:60,87`), all through the cached wrapper | **none** of these |

Slice 1 (food, v1/in-process) calls `findFiltered` (through `srv-dates` `carryForReplace`),
`bulkUpsert` and `deleteMany`: all in the seam list. Bringing the socket and v3 paths in either
keeps two method families under the step, or re-expresses v3's identifier-addressed writes as
filter writes, which changes the driver calls and, for v3, the cache events of
`mongoCachedCollection` (its five filter methods reload the whole cache, `index.js:147-159`).
That is question Q-A (§5).

## 2. Where each rule of §2.3 lives today

Paths: **v1** (API v1 routes), **in** (in-process callers: the same `lib/server/<col>.js` module
as v1, under the same `v1/internal` label), **ws** (socket), **v3**. All [R].

**Rule 1, `_id` form.**
- v1/in: `object-id-forms.js` helpers per module: food create `toStoredId` (`food.js:59-64`), food
  save `new ObjectId(id)` falling back to a fresh one (`food.js:28-34,126`), activity the same pair
  (`activity.js:18-24,51,100`), treatments `normalizeTreatmentId` (`treatments.js:530-560`),
  entries `normalizeEntryId` (`entries.js:505-525`), devicestatus `toStoredId` (`devicestatus.js:89`),
  profile `toStoredId` (`profile.js:137`).
- ws: `storeIdAsObjectId` (`websocket.js:773-780`), keeps an existing string form.
- v3: refuses a client `_id` with 400 (`opTools.refuseClientId`, `create/operation.js:36`; BF-170).

**Rule 2, target resolution (natural key, twins).**
- v1/in: treatments `upsertQueryFor` identifier -> `_id` -> fallback key (`treatments.js:494-517`);
  entries `sysTime`+`type` (`entries.js:460-478`) plus identifier match (`entries.js:187-203`);
  devicestatus identifier rule (`devicestatus.js:105-148`) then stored `_id` (`devicestatus.js:62-96`);
  profile stored `_id` (`storedByKey`, `profile.js:54`, used at `profile.js:115-127`); food and activity
  by `_id` only, as an upsert filter (`food.js:65`, `activity.js:52`).
- ws: treatments `NSCLIENT_ID` or fallback key (`websocket.js:800-822`) then the +-2 s similar
  match (`websocket.js:824-873`); devicestatus `NSCLIENT_ID` or `created_at` (`websocket.js:910-930`);
  profile `NSCLIENT_ID` or `startDate` (`websocket.js:954-985`); entries, food, activity: none,
  a plain insert (`websocket.js:1008-1030`).
- v3: `identifyingFilter` + `findOneFilter` (`create/operation.js:47-49`), dedup fallback fields per
  collection.
- Twins: v1 food/activity/treatments-batch append one `deleteMany` of string forms after all
  replaces in one ordered bulk write (`object-id-forms.js:131-137`); treatments/profile/activity
  `save` make a separate `remove` call after the replace (`treatments.js:426`, `profile.js:211`,
  `activity.js:107`); v3 sorts the ObjectId copy first and writes only it (`modify.js:46-52`).

**Rule 3, outcome.** Not computed anywhere as a value. Each path infers it from what it did: v1
food/activity/treatments from `bulkUpsert`'s `upsertedIds` (`food.js:88-92`); devicestatus and
profile from their match step; ws from which branch ran; v3 from `result.length`
(`create/operation.js:54-64`) and `acknowledge.applies` for devicestatus (`acknowledge.js:31-49`).
v3's immutable-field check (`update/validate.js:28-100`) is the only `refused`-style outcome besides
WRITE_VALIDATION.

**Rule 4, server dates** (`srv-dates.js`). v1/in: `carryForReplace` (`food.js:21`,
`treatments.js:172,266,316,423`, `profile.js:208`), `stampCreated` (`devicestatus.js:190`,
`profile.js:152`), `stampModified` + `$setOnInsert srvCreated` (`entries.js:153-160`); activity
none. ws: `stampCreated` / `stampModified` / `carry` per handler (`websocket.js:477-481, 598-604,
868, 889, 933, 969, 988, 1010`). v3: `srvDates.next()` in `insert.js:32`, `replace.js:32`,
`patch/operation.js:90`, `delete/operation.js:81`.

**Rule 5, adapter write and twin removal.** Covered under rule 2; every write reaches the driver
through `write-step.js:70-94`.

**Rule 6, one change event.** There is no step-level change event. What exists: per-path
`data-update` emissions (15 write-side `processRawDataForRuntime` calls in `treatments.js`,
`entries.js`, `devicestatus.js`, `websocket.js`; the cached wrapper's `forCache`,
`mongoCachedCollection/index.js:184-200`); v3's `storage-socket-*` emissions
(`insert.js:55`, `replace.js:67`, `patch/operation.js:125`, `delete/operation.js:70,96`); per-path
`data-received`; and, below the interface, `storage-write-committed` once per driver call. v1
food and activity emit no `data-update` at all [M: the baseline matrix, food and activity v1/in
columns, ev `–`].

## 3. What of §2/§3/§6.1 is already on `dev`

| item | on `db3b9e4e`? | where [R] |
|---|---|---|
| Q1b null-removes (merge patch) | yes, outside any step | `lib/server/merge-patch.js` (`update` :59, `toMongo` :80, `differsFromSet` :97); used by v3 PATCH (`patch/operation.js:115-124`), socket `dbUpdate` (`websocket.js:483-520`), v1 entries merge (`entries.js:274-332`), v1 profile re-send merge (`profile.js:80-92`) |
| ID-SIMPLE-MATCH (identifier match on v1) | yes, per module | entries `entries.js:187-203` (identifier, `$or _id` under UUID_HANDLING `entries.js:488-493`); treatments `upsertQueryFor` `treatments.js:496-509` |
| devicestatus identifier rule (Q3, 2026-10-26) | yes, v1 and v3 | v1 `devicestatus.js:105-148`; v3 `acknowledge.js:31-49` |
| socket +-2 s `near` match (Q4 (a)) | yes, socket treatments only, inline | `websocket.js:824-873`; C5 (no `data-update` after it) still present [M: baseline `treatments ws resend-near` ev `none`] |
| BF-194 Temporary Target units at write | yes, four places | `lib/treatmentTargetUnits.js`; v1 `treatments.js:609`, socket `websocket.js:552-575,691`, v3 `insert.js:28`, `replace.js:44`, `patch/operation.js:109` |
| WRITE_VALIDATION | yes, five places on two layers | above the interface: v1 `treatments.js:43-58` + `api/treatments/index.js:151-155`, socket `websocket.js:685`, v3 `operationTools.js:100-112`; **below** it: `write-step.js:27-42` (socket inserts/updates) and the conditional update `write-step.js:79-86` + `validated-update.js` |
| compare-and-set behind an adapter method | partly: the conditional validated update is a compare-and-set, but it lives in the persistence boundary, not behind an interface method | `validated-update.js`, `write-step.js:79-86` |
| U7 (every path to the storage socket, BF-164) | no, held out | v3 only [M: baseline, `wire` non-`none` only in v3 cells] |

## 4. Proposed slicing

Every slice holds G1 (the matrix equals the pinned file, apart from the known racy `cache`
field) and `npm test` equal to baseline plus its own tests, and runs `node scripts/test-tiers.js
check`: a new test file is in no tier until `tests/tiers.json` names it, and `test:all` then
silently skips it (slice 1 hit this; fixed in `84e21a66`). Every slice that moves a rule
re-targets the matching ablation of `write-contract-ablate.sh` at the step and shows it red.

1. **Slice 1 (built, `feat/write-intent`): food, API v1 + in-process.** `write(intent)` and
   `WriteResult.items[]` in `lib/storage/write-intent.js`; `lib/server/food.js` writes only
   through it. Rules moved: `_id` form (both of today's spellings, create and save), target by
   `_id`, `carryForReplace` server dates, string-twin removal, the `bulkUpsert`/`deleteMany`
   call. `COLLECTION_RULES` is keyed by collection **and source label**, holding today's
   per-path rules (not the spec's §2.2 target table, which is release 2). G2 check
   `scripts/check-write-intent.js` with `ENROLLED = ['lib/server/food.js']`. Why not food on
   every path: the socket handlers (`websocket.js:449-1078`) and v3 operations
   (`api3/generic/*`) are collection-generic; enrolling one collection there means a
   per-collection branch inside shared code, which is a bigger and riskier diff than the shape
   needs to be proven. Those come as path slices.
2. **Slice 2: activity, v1 + in-process** (`activity.js` is food's twin minus server dates:
   create = food create, `save` = replaceFiltered + separate twin remove `activity.js:100-108`).
   Exercises a second source of twin-removal timing (separate call vs appended op) as data.
3. **Slice 3: socket `dbRemove` and generic `dbAdd` for entries/food/activity** (one path, the
   generic branch `websocket.js:1008-1030` and `1038-1076`): the step's first `refused` outcome
   (a duplicate `_id` insert answers `[]` today, C6) and its first non-seam method (`insertOne`).
4. **Slice 4: API v3 generic create/update/patch/delete**, every v3 collection at once (one code
   path), after Q-A is answered.
5. **Slices 5-8: treatments, entries, devicestatus, profile on v1/in**, one per PR, each with its
   own matching rules and `data-update` emissions; then the socket's per-collection branches.
6. **Last: rule 6, the one change event**, only after D-EVENT, since it is where the step would
   start to carry `WriteResult.items[]` into an event (ST-EVENT).

## 5. Contradictions and open questions for the maintainer

The step has to pick a side on each of these. **Picking would change a matrix cell or an
emission in every case marked (cell)**, so none is picked here; slice 1 keeps each path as it is.

- **Q-A, two method families.** The spec's step calls only filter methods (§2.1); v3 writes by
  identifier through the cached wrapper (table in §1). Re-expressing v3 as filter writes changes
  the driver calls and the cache behaviour (the wrapper reloads the whole cache after any filter
  write, `mongoCachedCollection/index.js:147-159`) (emission: `data-update` changes from
  `update` with docs to `remove` with no changes). Keep both families under the step for release
  1, or accept the cache change?
- **Q-B, twin removal timing.** Spec rule 5: "directly after the write it belongs to (BF-130)".
  Code: food, activity create and treatments batches append **one** `deleteMany` after all
  replaces in the same ordered bulk write; treatments/profile/activity `save` make a **separate**
  driver call. Unifying changes the number of `storage-write-committed` events per request (not a
  matrix cell, but an emission the brief forbids changing). Which form is the rule?
- **Q-C, v1 and in-process share one label.** The spec's `origin.path` distinguishes `v1` and
  `internal`; on `dev` both write as `v1/internal` (`index.js:140-145`) through the same module,
  and the module cannot tell them apart. Is that distinction needed before release 2? Adding it
  changes the commit event's `source` value (D-EVENT territory).
- **Q-D, `_id` rule on a PUT/save with a non-hex id** (cell, in-process only). v1/in-process food
  and activity `save` turn a non-hex `_id` into a **fresh** ObjectId (`food.js:28-34`), i.e. a
  "save" of a custom-id record inserts a new record; `create` keeps the custom id
  (`toStoredId`). The spec's rule 1 says a non-hex string keeps today's per-collection rule; the
  per-op difference inside one collection is not mentioned. The v1 route refuses non-hex ids with
  400 before this (`api/food/index.js:92-96`), so only in-process callers reach it. Slice 1
  keeps both spellings as named rules (`objectid-or-new`, `stored-or-new`).
- **Q-E, identical re-send outcome** (cell). Q2 decided (b1) "status quo per path". In the
  step's vocabulary, today's v1 food re-send is `replaced` (srvModified advances, [M] baseline
  `food v1 resend-hex` `C=M+`), the socket's is a refused insert (`empty`, `C=M=`), v3's is 400
  (BF-170). Slice 1 labels the v1 one `replaced`. Confirm that `unchanged` is reserved for
  release 2 and that labelling today's no-ops does not count as a behaviour change.
- **Q-F, WRITE_VALIDATION has two homes.** The plan row says validation moves into the step;
  part of it already sits below the interface (`write-step.js:27-42`, the conditional update at
  `write-step.js:79-86`), and moving it up would move code out of the file whose `publish()` the
  D-EVENT prototypes rewrite. Should validation's lower half stay in the persistence boundary
  (it is the compare-and-set), with only the above-interface checks (`treatments.js:43-58`,
  `websocket.js:685`, `operationTools.js:100-112`) moving into the step?
- **Q-G, the spec's §1.3 table is stale.** Against the spec's own result file
  (`tools/qc/results/write-contract-matrix/dev-43289dde.json`) the `db3b9e4e` baseline differs in
  65 cells [M] (BF-170's v3 400s, #8859's profile merge, devicestatus identifier rule, BF-194, and
  MongoDB 7 vs 8 under the harness). G1 for this work pins `db3b9e4e`, not the spec's file; the
  spec's tables should be re-generated before release 2 decisions cite them.
- **Q-H, the step's name for "create" on v1.** v1 `POST` for food and activity is an upserting
  replace by `_id`, not a create; treatments' is a replace by natural key. The intent says
  `create`; the rule table says `onMatch: replaced`. The spec's `create` + `near` vocabulary fits;
  noting only that `create` on v1 has always been allowed to replace.

## 6. What the matrix does not see

- `storage-write-committed`: the upstream harness taps only `data-update` and
  `storage-socket-*`. This milestone ran a scratch copy of the harness that also records every
  commit event per cell (field `commit`) [M], so the event's count, source, operation and counts
  are part of the G1 comparison for slice 1.
- The order of driver calls and their exact arguments: covered for slice 1 by a unit test that
  runs the pre-move `food.js` logic and the step over the same recording driver and compares the
  calls and the commit events (`tests/write-intent.test.js`).

## 7. Measurements behind the [M] marks

Environment: Node v22.23.4; MongoDB 8.0.34 in container `wcstep-mongo8` on 127.0.0.1:27711;
worktree `externals/work/crm-wc-step`, branch `feat/write-intent` from `official/dev` `db3b9e4e`.
Results in this scratch directory.

- `npm test` on untouched `db3b9e4e`: **4,750 passing, 0 failing, 3 pending** (`npmtest-base.log`);
  `--dry-run` counts 4,753 tests, consistent. A dry run at `ca1652d6` counts 4,707, so the brief's
  "4,750 at ca1652d6" figure must have been taken at a later tree; BF-194 added 46 tests in two
  new files (`api.treatments-tt-units` 34, `websocket.tt-units` 12).
- Write matrix, two runs on untouched `db3b9e4e` (the first is committed as [`tools/qc/results/write-contract-matrix/dev-db3b9e4e.json`](../../../tools/qc/results/write-contract-matrix/dev-db3b9e4e.json), the G1 pin): 360 cells
  (336 + 24 Temporary Target), 0 INVALID, 20 n/a, `write_validation` off. `--compare`: **0
  differing cells**, the known racy `cache` field included. Two more runs of a scratch copy of the
  harness that also records `storage-write-committed` per cell (`tools/wc-matrix-commit.js`,
  `matrixc-base-1/2.json`): 0 differing cells; with the `commit` field removed they equal the
  official run.
- Baseline vs the spec's own file `dev-43289dde.json`: 65 differing cells (Q-G).
- Upstream ablations (`tools/qc/write-contract-ablate.sh`, `ablate-base.txt`): all six patterns
  still match on `db3b9e4e` and all six breaks turn the matrix red; every revert matches its
  clean run. `oid`, `srv`, `soft`, `key` changed exactly their listed cells. `derive` and `wire`
  report MISMATCH because their expectation lists predate the Temporary Target cells
  (QC-MATRIX-TT, added after the script): the extra red cells are `treatments v3 tt-*` creates and
  updates, red for the same rule (no `mills` on the cache copy; no `ss:create`). Not vacuous;
  the script's lists need the TT cells, or `--no-tt`.
- Slice 1 (`2b9d3687`): G1 `--compare` against `dev-db3b9e4e.json`: **0 differing cells of
  360**; with the commit-event field: **0 differing**.
- Step-targeted ablations (`tools/wc-step-ablate.sh`, `ablate-step.txt`), each on
  `lib/storage/write-intent.js`, matrix limited to food on v1 and in-process:
  - `_id` form removed (create keeps a hex string): 8 cells red (`resend-hex`, `resend-upper`,
    `legacy-lower`, `legacy-upper` on both paths). The re-send answers 200 and **stores nothing**:
    the string-form upsert is followed by the twin removal of that same string. A silently lost
    record, which is exactly what rule order is for.
  - server dates removed: 19 cells red (every food write on both paths that reaches the step,
    including the seed writes): `CM`/`C=M+` -> `noCnoM`, v3 history `h` -> `–`.
  - twin removal removed: exactly the 4 `legacy-*` cells red: one record -> two (`str,OID`).
  Every revert matched its clean run; my predicted lists for the first two were too narrow,
  the cells that went red are listed above.
