<!-- Draft body for branch bf/v1-writes-v3-history at dbc4c5fc (718efddc, the fix, plus two test commits, on dev e3adc91d), 2026-09-26. Not opened. This comment is hidden on GitHub. -->
Records written through API v1, the websocket or inside the server now appear in API v3 history (BF-122, issue #8244). A record deleted with `isValid: false` stops counting on the site (JL-1). Three commits on `dev` `e3adc91d`: the fix and two test commits. v1 DELETE is left unchanged by the maintainer's decision: it stays a hard delete (see "Decision: v1 DELETE stays a hard delete").

## What changes for you

*A plain-language summary for people who run their own Nightscout site, for themselves or for a family member. Nightscout is not a medical device, and nothing here is medical advice. If your numbers look wrong, check with your care team before you rely on them. Nothing here tells you how to dose.*

A few words used below:

- **Treatment**: a saved carb entry, insulin dose, temporary target, note and similar.
- **COB / IOB**: carbs on board and insulin on board. Nightscout estimates both from your treatments and shows them in pills on the main page.
- **AndroidAPS (AAPS)**: an automated insulin delivery app. Its Nightscout connection, **NSClient**, copies treatments and readings between the phone and your site.
- **API v1 / API v3**: the two ways apps talk to Nightscout. The Nightscout web pages (careportal, bolus wizard), Loop, Trio, xDrip+, xdripswift and OpenAPS use v1. AndroidAPS uses v3.
- **Deleted record (soft delete)**: when AndroidAPS deletes a record, Nightscout keeps it with a "deleted" mark (`isValid: false`) instead of removing it. That mark is how other copies of AndroidAPS learn about the delete.

### What was wrong

1. **AndroidAPS did not receive what other apps wrote.** After its first sync, AndroidAPS asks Nightscout only for "what changed since last time". Nightscout answered that question only for records written by AndroidAPS or other v3 apps. It left out carbs, insulin, temporary targets and notes entered in the careportal or bolus wizard, including ones a caregiver entered. It also left out glucose readings uploaded by xDrip+, xdripswift or nightscout-connect, and every edit made through v1. So AndroidAPS never got them, unless someone ran a full sync.
2. **A deleted entry kept counting on the site.** Carbs or insulin that AndroidAPS deleted stayed in Nightscout's COB and IOB, on the chart, in reports, and in what followers and other apps read. In our lab, 40 g of carbs showed COB 40 g, and after AndroidAPS deleted them COB still showed 40 g. That happens on 15.0.8 and on the 15.0.9 candidate. A deleted profile could also stay the "current" profile.

### What this change does

- AndroidAPS now receives careportal, bolus wizard and caregiver entries, readings from other uploaders, and edits made through v1, on its next regular check. It no longer needs a full sync for them.
- When a v1 app edits a record that AndroidAPS created, the record keeps the label AndroidAPS knows it by, so AndroidAPS updates its copy and does not add a second one.
- A record that AndroidAPS deletes, over either kind of connection, no longer counts. It disappears from COB and IOB, from the chart and reports, from what followers and v1 apps read, and from "current profile". COB and IOB then show exactly what they show when the record is deleted from the careportal.

### What to check after you update

- **Carbs and insulin you entered in the careportal will now reach AndroidAPS**, if AndroidAPS is set to accept them. On a phone that loops, AndroidAPS takes carbs and insulin from Nightscout only if **"accept carbs"** and **"accept insulin"** are switched on in its NSClient settings. Both are off unless you turned them on. The AAPSClient follower app always takes them, and does not show these two settings. If you have been entering the same meal both in the careportal and on the phone as a workaround, AndroidAPS may now see it **twice**. Check the phone's treatment list after the update.
- AndroidAPS applies what it receives according to its own settings. For carbs it already knows about, it accepts a deletion and a shorter duration, but not a changed amount (AAPS `SyncNsCarbsTransaction.kt:20-34`, read).
- Records written before the update are not changed. AndroidAPS gets only what is written or edited after the update.
- **Deleting in the careportal (or by Loop, Trio or xDrip+) still removes the record completely, and AndroidAPS still does not hear about it.** An entry deleted that way keeps counting on the phone. This stays as it is by decision. **Delete the entry in AndroidAPS as well.** An entry you delete in AndroidAPS stops counting on your site, and other phones running AndroidAPS hear about the delete, if they are set to accept carbs and insulin.

## Technical detail

### BF-122: v1 writes and v3 history

`GET /api/v3/<col>/history/<ms>` filters `srvModified > ms`, sorts by `srvModified` and returns the largest value as the `ETag`, which AAPS takes as its next cursor (`lib/api3/generic/history/operation.js:45-49`, `:102`, `:113`; AAPS `NSAndroidClientImpl.kt:327-335`). Before this change only the v3 handlers stored `srvModified`.

What the commit does:

- `lib/server/srv-dates.js` (new) provides `next()`, `stampCreated`, `stampModified`, `carry` and `carryForReplace`. Both fields are ms numbers, as v3 writes them. The server owns them, so any value a client sends is replaced.
- **Inserts** set `srvModified = srvCreated`. That covers devicestatus `insertMany`, profile `create`, websocket `dbAdd` for treatments, devicestatus, profile, entries and food, and the v1 treatment and food upserts when they insert.
- **Updates with operators**: entries upserts `$set srvModified` and `$setOnInsert srvCreated`. Websocket `dbUpdate`, `dbUpdateUnset` and the treatment "similar" dedup update add `$set srvModified` and never write `srvCreated`. A client cannot unset either field.
- **`replaceOne` upserts** (v1 PUT `treatments.save`, `treatments.create` single, batch and preBolus, food `create`/`save`, profile `save`, websocket profile dedup) first read the records the filters name, in one `$or` query per 500 items. They match each filter in memory (`$eq` and `$or` only; any other shape falls back to `findOne`). The replacement then keeps the stored `srvCreated`, or its absence, and the stored `identifier` when the body has none. A v1 PUT therefore no longer strips a v3 record's `identifier`. Without it, v3 would list the record under its `_id`, and AAPS would store it as a new record (read: AAPS matches by `nightscoutId` = `identifier`, `SyncNsCarbsTransaction.kt:15-18`, then falls back to timestamp only for records without an NS id, `:58-67`).
- **One clock.** `next()` returns `max(Date.now(), last + 1)`. It never repeats and never goes back in the process. The v3 handlers use it too (`create/insert.js`, `update/replace.js`, `patch/operation.js`, `delete/operation.js`). A batch stamped with one value would lose every record past the first page, because paging is `> cursor` and AAPS asks for 500 (`NSClientV3Plugin.kt:184`). A batch of N records runs the clock up to N ms ahead. The shared clock keeps a v3 write that follows the batch ordered after it (test: "a v3 write made right after a large v1 batch").
- Collections: every collection v3 serves that has a v1 or websocket writer: treatments, entries, devicestatus, profile, food. Settings has no v1 writer. Activity has no v3 endpoint and is not stamped.

### JL-1: `isValid: false` is deleted outside v3

`lib/server/soft-deleted.js` (new): `visible(query, opts)` adds `isValid: {$ne: false}` unless `opts.find` names `isValid`. With `find[isValid]=false` the caller gets the tombstones.

- v1 reads: `treatments`, `entries`, `devicestatus` `query_for` (used by list, `/count/.../where` through `aggregate`, the `/slice` and `/times` routes, and the `/echo` query), `entries.getEntry`, and profile `list`, `list_query` and `last` (so `/profile/current` and the dataloader skip a deleted profile). Food `list`, `listquickpicks` and `listregular` too.
- Deletes use a new `stored_query_for`, so a v1 DELETE (including the Admin Tools purges) still removes tombstones.
- Dataloader: its loads go through `list`, so tombstones are not merged back into the cache or `ddata`. COB, IOB, the chart, `/api/v2/properties`, the websocket `dataUpdate` deltas (treatments send `action: 'remove'`, `lib/data/calcdelta.js:64-68`) and the pushover and alarm plugins read from there.
- Cache (`lib/server/cache.js`): a `data-update` `op: 'update'` whose change has `isValid === false` removes that record and bumps the removal generation. This is the AAPS v1 `dbUpdate` path. v3 DELETE already evicted through `mongoCachedCollection.updateEveryForm`. Before, the dataloader's next 15-minute query put the tombstone back.
- Websocket `dbAdd` dedup lookups (treatment exact and similar match, devicestatus exact match) skip tombstones. A record re-entered at the same time as a deleted one is stored, instead of being answered with the deleted copy.
- An entry re-sent through v1 for a deleted reading gets `$unset isValid`, so it is stored again. Treatments already revived this way through `replaceOne`, and v3 POST dedup does the same (`create/operation.js:52` → `replace`).
- `lib/data/ddata.js:351` ('OpenAPS Offline' skips `isValid === false`) is unchanged. Such records no longer reach it.
- v3 search already excluded tombstones (`search/operation.js:32`, `onlyValid = true`). v3 history still returns them (`onlyValid = false`).

Which numbers and displays change (measured in the tests and the lab below): COB and IOB from treatments, the treatment glyphs on the chart, Reports (they read v1), `/api/v1/treatments|entries|devicestatus|food|profile*`, `/api/v1/count`, `/api/v2/properties` (cob, iob and the rest built from `ddata`), `/api/v2/ddata`, and the websocket data followers and the web page receive. COB and IOB that AndroidAPS uploads in its device status are unchanged, because they are the phone's own numbers.

### Decision: v1 DELETE stays a hard delete

**Decided 2026-09-26 by the maintainer: option (a), keep hard delete.** The reason given: people are likely to use AndroidAPS as the controller, not the careportal. AndroidAPS deletes are soft (`isValid: false`). With JL-1's fix below they stop counting on the site, and they reach other AndroidAPS instances through v3 history. Consequences:

- A careportal, Loop, Trio or xDrip+ delete still removes the record, never appears in v3 history, and does not reach AndroidAPS, which keeps counting its copy. The plain-language section tells people to delete in AndroidAPS as well.
- The Admin Tools and API purges keep freeing space, and no tombstones build up.
- The probe's v1 DELETE arm now measures the decision: the record is expected to be absent from history, and the probe exits 1 on that arm alone.
- What reaches AndroidAPS through history is applied according to its NSClient settings (AAPS `7e1d537d49`, read). With the looping app, carbs and insulin from Nightscout, and their deletions, are applied only when "accept carbs" and "accept insulin" (`ns_receive_carbs`, `ns_receive_insulin`) are on; both default to off (`core/keys/.../BooleanKey.kt:224-225`). The AAPSClient build always applies them and hides both settings (`showInNsClientMode = false`; the checks are `preferences.get(...) || config.AAPSCLIENT` in `NsIncomingDataProcessor.kt:163-167` and `StoreDataForDbImpl.kt:420-426`). A full sync applies them too.

The options considered, kept as the record:

v1 `DELETE /api/v1/<col>/<id>`, `DELETE /api/v1/<col>?find…` and websocket `dbRemove` still remove documents, so v3 history has no tombstone to report. AAPS then keeps its copy of the record. It is still counted on the phone after the careportal deletes it (read: `SyncNsCarbsTransaction.kt:20-26` invalidates only on `isValid: false`; a record missing from history changes nothing). The test "a v1 DELETE still removes the record…" pins this behaviour. Its name and comment record the decision (hard delete kept, 2026-09-26).

With JL-1 in place, a soft delete is possible without changing what the site shows. Soft deletes were not made the default because some things in the corpus would get worse:

| option | AAPS | what gets worse |
|---|---|---|
| (a) keep hard delete (this PR) | a careportal, Loop, Trio or xDrip+ delete never reaches AAPS | nothing changes |
| (b) every v1 and websocket delete soft | AAPS invalidates its copy | The Admin Tools purges (`lib/admin_plugins/cleanstatusdb.js:66,121`, `cleanentriesdb`, `cleantreatmentsdb`, `daterangedelete`) and API purges no longer free space, which matters on the 512 MB free database tiers (a full database stops accepting uploads). A re-insert with the same `_id` then collides with the tombstone: profile `insertMany` and websocket `insertOne` fail with E11000, and devicestatus answers "already stored". `delete-count.js` reads `deletedCount`. v3 `autoPrune` is off by default, so tombstones stay |
| (c) soft for single-record deletes (by `_id`, `find[_id]`, `find[id]`, `dbRemove`), hard for range and `*` deletes | AAPS hears about record deletes | Trio deletes with `find[id][$eq]` and with `find[created_at][$eq]&find[eventType][$eq]` (`Trio/.../NightscoutAPI.swift:160-173`, `:235-240`), so "single record" has to be judged from the query. A re-insert by the same `_id` needs a revive path in profile, devicestatus and websocket `dbAdd` |
| (d) hard delete plus a minimal tombstone (`_id`, `identifier`, `isValid: false`, `srvModified`, date field) for records modified in the last 100 days (AAPS `maxAge`, `NSClientV3Plugin.kt:228`) | AAPS hears about recent deletes | space is freed except for small tombstones. Tombstones need a purge path. A date-ranged v1 read hides them (JL-1), but an unranged tool reading MongoDB directly sees them |

(c) or (d) would have been the smallest change that gives AAPS careportal deletions. Neither was chosen.

### History paging: what the v3 design still allows

- **Commit order vs stamp order.** `srvModified` is taken in the app before the write reaches MongoDB. If write A takes T1, write B takes T2 > T1, B commits, a client reads (cursor T2), and then A commits, the client never sees A. That window is the time between stamping and committing: milliseconds, and it exists for v3 writes too. For `replaceOne` paths the pre-read happens before stamping, so this change does not widen the window. Closing it needs a value assigned at commit, or a client that re-reads an overlap window. That is a v3 design question and is not changed here.
- **Several server processes** each have their own clock. Nightscout runs one process.
- **`Last-Modified` header form** uses `>=` on whole seconds, so it re-delivers the same second rather than skipping it.

### Indexes and cost

- v3 creates single-field indexes on `identifier`, `srvModified` and `isValid` for each collection it serves (`lib/api3/storage/mongoCollection/index.js:21-24`). History uses `srvModified_1`.
- `isValid: {$ne: false}` did not change the winning plan in a measured check. Fifty thousand entries with the app's indexes on MongoDB 7.0.43 (2026-09-25): `{type:'sgv'}` sorted by date, limit 10 used `type_1_date_-1_dateString_1` with 10 docs examined, with or without the filter. A one-day range with limit 1000 used `date_1` with 1000 examined in both cases. The filter costs something only where a range is mostly tombstones: 5,000 tombstones examined, 14 ms.
- Each `replaceOne` write reads first: one indexed `$or` query per 500 items.

## Tests

New files: `tests/api3.v1-writes-history.test.js` (15 tests) and `tests/soft-deleted.jl1.test.js` (15 tests): 30 new tests.

- v1 POST of a treatment, entry, device status, profile and food, and in-process `ctx.entries.create` and `ctx.treatments.create`, each appear in `history/<t>`, with `srvModified` a number and `srvCreated === srvModified`.
- A v1 PUT of a v3 record by `_id` alone keeps `identifier` and `srvCreated`, and the change appears in history. A PUT that sends the record back with a stale `srvModified`/`srvCreated` gets them replaced or kept. A food and profile PUT keeps `srvCreated`. An entry re-sent for the same reading keeps `srvCreated`.
- Websocket `dbAdd`, `dbUpdate` (including `isValid: false`, reported as deleted) and `dbUpdateUnset` (which cannot unset the server fields) appear in history, with `srvCreated` kept.
- A 25-entry v1 batch is read in full by paging with limit 10 on the ETag cursor. A v3 write right after a 1,500-entry batch sorts after it. `next()` is strictly increasing.
- Pinned (the maintainer's decision): a v1 DELETE is not in history. Control: a v3 DELETE is in history with `isValid: false`.
- JL-1: AAPS v3 carbs 40 g give COB 40. After v3 DELETE, COB is 0, the record is absent from `ddata`, v1 list and v1 count, present with `find[isValid]=false`, present in v3 history and absent from v3 search. The same through the v1 socket (`dbAdd`, then `dbUpdate isValid:false`, which also takes it out of the cache). Control: v1 hard DELETE gives COB 0. Control: undeleted carbs keep counting. A 2 U bolus stops counting in IOB after v3 DELETE. A re-added treatment is stored. A deleted profile is not `/profile/current`. A deleted entry is absent from v1 and the cache, and re-sending it stores it again. A deleted device status and food are absent. A v1 DELETE by query removes tombstones. A cache unit test.
- `tests/soft-deleted.jl1.test.js` also checks that a v1 profile search by date (`/api/v1/profiles/?find[date]=…`) leaves out a deleted profile with the same date, and still returns it when `find[isValid]=false` is asked for. Without the profile read filter, the deleted profile comes back.
- Red on `e3adc91d`: 20 of the 25 then in the files fail there, and the 5 controls pass (run 2026-09-25 by copying the files into a clean `e3adc91d` worktree). Each fails with the original symptom, for example "expected 0 to be 1" (absent from history) and "expected 40 to be 0" (COB after delete). The shared-clock test was added afterwards and has its own break-it (B16).

Changed expectations, marked `// CHANGED EXPECTATION` in the files: `tests/api3.create.test.js` (two dedup tests: the v3 copy of a v1 record no longer carries the v1 record's server times), and `tests/websocket.input-validation.test.js` (the dedup selectors now carry `isValid: {$ne: false}`, and the fake collection understands `$ne`). The fake collection in `tests/storage.selector-hardening.test.js` gains `find`, because food now reads before it writes.

### Break-its (each hunk reverted alone, 2026-09-25)

Every one turned the named test red, and the others stayed green.

| tamper | red test |
|---|---|
| B1 `treatments.save` carries nothing | v1 PUT by `_id`; v1 PUT with identifier |
| B2 treatments batch create not stamped | v1 POST of a treatment… |
| B3 treatments single upsert not stamped | in-process write |
| B4 entries not stamped | v1 POST…, in-process, entry sent again, batch paging |
| B6 devicestatus not stamped | v1 POST… device status |
| B7 profile create not stamped | v1 POST of a profile; PUT of food and profile |
| B8 profile save carries nothing | PUT of a food and a profile |
| B9 food not stamped | v1 POST of a profile and a food; PUT of food and profile |
| B10 ws `dbUpdate` not stamped | dbAdd/dbUpdate/dbUpdateUnset; dbUpdate isValid false |
| B11 ws `dbUpdateUnset` not stamped | dbAdd/dbUpdate/dbUpdateUnset |
| B12 ws `dbAdd` generic insert not stamped | dbAdd of an entry, device status, profile |
| B13 clock is `Date.now()` | batch paging; `next()` increasing |
| B14 carry drops `identifier` | v1 PUT by `_id` |
| B15 carry drops `srvCreated` | both v1 PUT tests; food/profile PUT |
| B16 v3 insert on its own clock | v3 write after a large v1 batch |
| J1 treatment reads unfiltered | AAPS v3 COB; AAPS v1 COB; IOB; re-add |
| J2 cache keeps `isValid:false` updates | AAPS v1 COB; cache unit test |
| J3 entry reads unfiltered | deleted glucose reading |
| J4 profile `last` unfiltered | deleted profile |
| J5 devicestatus reads unfiltered | deleted device status and food |
| J6 food list unfiltered | deleted device status and food |
| J7 ws similar-match sees tombstones | re-add of a deleted treatment |
| J8 entry re-send does not revive | deleted glucose reading… stores it again |
| J9 DELETE uses the filtered query | DELETE by query removes deleted records |

### Probe

`node tools/lab/triage-2026-09/v1-writes-v3-history.js <tree> 17832 mongodb://127.0.0.1:27831/<db>` against MongoDB 7.0.43 on Node 22.23.2:

| arm | `e3adc91d` | this branch `718efddc` |
|---|---|---|
| treatments-v1, entries-v1, devicestatus-v1 | absent | **present** |
| treatments-v1put | absent (`srvModified` removed) | **present** (`identifier` kept) |
| treatments-v1del | absent | absent (kept by decision) |
| controls (v3 ×3, v3del, v1+srvModified) | present | present |
| exit | 1 | 1 (the delete arm only) |

### Journey lab (JL-1 end to end)

`tools/review/journey-lab/lab.sh`, copied with the site ports moved to this run's (17833/17834, MongoDB 27832, fake APNs/Share 17831/17832) and site names `f122-*`. Steps: `up`, `connect`, `editor-save` (a Nightscout profile with `carbs_hr`: the AAPS `onboard` and `wizard` profiles have no `carbs_hr`, so COB from treatments stays 0 on both trees), `carbs 40`, `carb-delete`. The read is `/api/v2/properties/cob`:

| site | tree | after carbs | after AAPS delete |
|---|---|---|---|
| cp-aaps (v3 DELETE) | `e3adc91d` | COB 40 | **COB 40** (v1 read returns it, `isValid:false`) |
| cp-aaps | this branch | COB 40 | **no COB** (`{}`), v1 read empty |
| aaps-v1 (`dbUpdate isValid:false`) | `e3adc91d` | COB 40 | **COB 40** |
| aaps-v1 | this branch | COB 40 | **no COB** (`{}`), v1 read empty |
| control: v1 DELETE by `_id` | this branch | COB 40 | no COB (`{}`), v1 read empty |

After the delete, the soft-deleted site answers exactly as the hard-deleted control does (`cob {}`, `iob {}`).

### Full suite

`npm test` on `d45987f7` (`dbc4c5fc` after it renames one test), Node 22.23.2, MongoDB 7.0.43 (read from the server): **3200 passing, 0 failing, 3 pending** (3170 on `e3adc91d` plus the 30 new tests), exit 0. On `718efddc` alone it was 3196/0/3.

Combined with the other five fix branches for 15.0.9 (local `lab/round1-combined` `bda225e4`, carrying `718efddc`), the full suite gave 3292 passing, 0 failing, 3 pending on 2026-09-26 (3170 plus 122 new tests), and this probe exited 1 on the v1 DELETE arm only.

## Client impact (read from the corpus unless marked run)

- **AndroidAPS NSClientV3** (`externals/AndroidAPS` `7e1d537d49`) is the client this change is for. After its first load it polls `v3/<col>/history/<cursor>` with limit 500 and takes the ETag as the next cursor (`LoadTreatmentsRunner.kt:50-58`, `NSAndroidClientImpl.kt:327-335`, `NSClientV3Plugin.kt:184`). It reads profile history too (`NightscoutApi.kt:225`). What it now receives:
  - treatments written by the careportal, the bolus wizard, a caregiver, Loop, Trio, xDrip+ and oref0;
  - entries from xDrip+, xdripswift and nightscout-connect, when it takes BG from Nightscout;
  - device statuses and profiles written through v1;
  - v1 and websocket edits of its own records, which keep their `identifier`.

  Records it already knows by NS id change only by invalidation, or a shorter duration for carbs (`SyncNsCarbsTransaction.kt:20-34`). Records it does not know are inserted, unless it matches them by pump ids or timestamp (`:37-67`). **Worse for anyone?** Someone who enters the same meal in both the careportal and AAPS, at different timestamps, now gets two carb records in AAPS. That is the NSClient receive path working as designed, and it is a behaviour change to put in the release notes. v1 deletes still do not reach AAPS (see the decision on v1 DELETE).
- **Uploaders using v1** (careportal `lib/client/careportal.js:398`, `boluscalc.js:544`, chart drag `renderer.js:904-918`; Loop/NightscoutKit `4ec9fd1` `NightscoutClient.swift:13-15`; Trio `e41c9db37` `NightscoutAPI.swift:14-17`; xDrip+ `1ed760048` `NightscoutUploader.java:130-149`; xdripswift `c268542e` `NightscoutSyncManager.swift:54,58,61`; oref0 `d219baf9` `ns-upload.sh:13`, `ns-upload-entries.sh:22`; nightscout-connect `04102f9` `lib/outputs/internal.js:40`, `nightscout.js:63,109,161`). Their requests are unchanged. Responses and v1 reads now also carry `srvModified` and `srvCreated`, as records written by AAPS already did. A client that sends those fields back has them replaced by the server. No corpus client reads them.
- **Readers of v1** (Loop, Trio, LoopFollow `4a74b781`, nightguard `75404bd`, xDrip+ followers, Nightscout Reporter, oref0): they no longer receive records deleted with `isValid: false`. No corpus client asks for `find[isValid]` or treats `isValid` from Nightscout specially (grep of the clients' sources: the only `isValid` hits are their own local model properties, read). For oref0 and Trio, which read Nightscout treatments, deleted carbs stop reaching them (read). That is the intended fix.
- **Older AndroidAPS on the v1 socket NSClient** (not in the corpus; released versions not checked): when another AAPS deletes a treatment, a v1-socket client now gets a websocket delta with `action: 'remove'` (`calcdelta.js:64-68`) instead of an update carrying `isValid: false`. Whether those versions act on `remove` was not checked. That is the open item for this change.

<!-- Register text proposed to the parent, not applied: see the agent report. -->
