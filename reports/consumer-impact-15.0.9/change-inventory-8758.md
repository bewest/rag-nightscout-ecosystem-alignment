# #8758 at `ab7b22d6`: consumer-visible `_id` changes (C68–C81)

**Contributor-facing working document (DRAFT).** Extends [change-inventory.md](change-inventory.md)
(C1–C67, 2026-09-23). Not operator-facing and not medical advice.

- **Server repo:** `externals/cgm-remote-monitor-official` (remote `origin` = nightscout/cgm-remote-monitor).
- **Refs (measured 2026-09-25):** 15.0.8 = `origin/master` `92d08342`; `origin/dev` = `4f705217`;
  PR #8758 head = `ab7b22d6` (`bf/object-id-crud`), merge-base with dev `4f705217`, tree `25ab7afc`.
  Delta: `git diff origin/dev...ab7b22d6` (28 files, +3328/−80).
- **Relation to C49–C59.** The 2026-09-23 inventory covered #8758 at `6d120fa2`. Five commits
  since then change consumer-visible `_id` behaviour: `a2c7eb39` (API v3 writes on a v1/v3 pair,
  BF-109), `1c2d1afd` (`find[_id][$in]`/`$nin`, BF-111), `d2fd9ff6` + `ab7b22d6` (auth subjects,
  BF-112), `dd2cf8f1` (12-character ids, BF-113). `572bfc32` merges dev into the branch. C68–C81
  restate the whole #8758 contract at `ab7b22d6` and name the older C-id each one supersedes.
- **Evidence labels.** "read-derived" = from source at the anchors. "measured" = replayed
  2026-09-25 against 15.0.8 `92d08342` and `ab7b22d6` side by side, MongoDB 7.0.43
  (`db.admin().serverInfo().version`), Node 22.23.2, `AUTH_DEFAULT_ROLES=readable`; cell names
  (`Q…`, `P-ID-…`) refer to [clients-8758.md §Replays](clients-8758.md#replays-2026-09-25).
- **Status:** open PR #8758. Nothing here is on `origin/dev` `4f705217`.

## The rule (`ab7b22d6:lib/server/object-id-forms.js`)

- `isHexId` = string matching `/^[0-9a-fA-F]{24}$/` (`:40-44`).
- `toStoredId`: 24-hex string → the ObjectId it names; anything else kept (`:47-49`).
- `idForms(id)`: `[ObjectId, lower-case hex, the string as given if different]`; throws on anything
  that is not an ObjectId or 24-hex string, so a 12-character string is never read as raw bytes
  (`:56-67`, `dd2cf8f1`).
- `idFilter(id)`: `$in` of all forms for a hex/ObjectId id, `$eq` otherwise (`:75-77`).
- `matchEitherForm`: widens a query whose `_id` is a plain ObjectId equality (`:83-88`).
- `withStaleStringsRemoved` / `staleStringForms`: after an upsert by the ObjectId form, delete the
  string forms of the same id (`:95-112`).
- Stated limit (`:14-20`): an upper- or mixed-case **string** `_id` on disk is matched only when
  asked for in that spelling.

## Summary

| C-id | change | endpoint(s) | supersedes | evidence |
|---|---|---|---|---|
| C68 | a new record with a 24-hex `_id` is stored as ObjectId | v1 POST profile, devicestatus, food, activity; websocket `dbAdd` (every collection) | C54, C55, C56, C58 | measured Q1, Q5, P-ID-4/5/6 |
| C69 | a re-send with the same `_id`: result per collection | same, plus treatments | C53–C56, C58 | measured Q2, Q2b, P-ID-6 |
| C70 | entries POST reply names the stored reading's `_id` | v1 POST entries | C50 | measured P-ID-3 |
| C71 | upper-case hex ids | v1 `/entries/<id>`; replies | C51, C54 | measured Q1, P-ID-3 |
| C72 | `find[_id]=<hex>` and delete by id reach both stored forms | v1 entries, treatments, devicestatus, profile, activity, food | C52–C56 | measured Q6, Q14, P-ID-6 |
| C73 | `find[_id][$in]` / `[$nin]` name both forms | every v1 collection through `lib/server/query.js` | new (`1c2d1afd`, BF-111) | measured Q4, P-ID-11 |
| C74 | a delete by id removes every stored copy (twins) | v1 DELETE, websocket `dbRemove` | new statement (BF-110 decided) | measured Q4, Q12, P-ID-7 |
| C75 | API v3 by `identifier` reaches string `_id`s; writes target the document GET returns | `/api/v3/<coll>/<identifier>`, v3 create dedup | C59 + `a2c7eb39` (BF-109) | measured P-ID-2, P-ID-10, Q10, Q10b |
| C76 | websocket `dbUpdate` / `dbUpdateUnset` / `dbRemove` match both forms | main-namespace socket | C42, C58 | measured P-ID-4, P-ID-7 |
| C77 | websocket `dbAdd` collision answers `[]` | main-namespace socket | C58 | measured Q5, Q9 |
| C78 | devicestatus re-send guard, and the rest of the batch | v1 POST devicestatus | C55 | measured Q2, Q2b, ablation |
| C79 | auth subject / role delete matches both forms | `/api/v2/authorization/subjects/<id>`, `/roles/<id>` | new (`d2fd9ff6`, `ab7b22d6`) | measured P-ID-12 |
| C80 | profile PUT with a non-hex `_id` gets a new ObjectId | v1 PUT profile | new (`dd2cf8f1`, BF-113) | read-derived; unit test |
| C81 | entries POST writes `_id` only on insert | v1 POST entries (and in-process `ctx.entries.create`) | C49 | measured Q3, Q8, P-ID-3 |

## C68 — a new record posted with its own 24-hex `_id` is stored as an ObjectId

- **Before (15.0.8 and dev):** profile `insertMany` with `_id` as given (`92d08342:lib/server/profile.js:38`);
  devicestatus `insertMany(…, {ordered:true})` as given (`92d08342:lib/server/devicestatus.js:70`);
  food/activity `replaceOne({_id: <as given>})` upsert; websocket `insertOne(data.data)`
  (`92d08342:lib/server/websocket.js:590,633,686,707`). A 24-hex string stayed a **string**.
  Treatments and entries already converted since 15.0.7 (unchanged).
- **After (`ab7b22d6`):**
  - profile: converted unless that exact string is already stored (`lib/server/profile.js:23-37`, applied `:66-68`);
  - devicestatus: converted unless the lower-case or submitted string form is already stored (`lib/server/devicestatus.js:50-71`, called `:101`);
  - food, activity: converted, and any string copy of the same id deleted in the same bulk write (`lib/server/food.js:46,56`; `lib/server/activity.js:46,56`);
  - websocket `dbAdd`, every collection: converted unless a string copy exists (`lib/server/websocket.js:549-555`, called `:561`; a failed lookup answers `[]`).
- **Reply `_id`:** lower-case hex (ObjectId JSON). An upper-case id sent is answered lower case (Q1: 15.0.8 "as sent", candidate "lower").
- **Measured:** Q1 devicestatus new with lower/upper hex: string → OID; Q5 `dbAdd` devicestatus and treatment with a fresh hex: string → OID, ack `_id` equals the sent id; P-ID-4/5/6 profile, food, activity: string → OID.
- **Consumer effect:** `find[_id]` and DELETE by that id now find the record (C72).

## C69 — re-send of a record with the same `_id`

| collection | stored form of that id | 15.0.8 | `ab7b22d6` | anchor (`ab7b22d6`) |
|---|---|---|---|---|
| devicestatus | the client's own hex, first posted by the client | 200, then 500 (string collides) | 200, then 500 (OID collides) | `devicestatus.js:50-71,108` |
| devicestatus | server-assigned ObjectId (read back and re-posted) | **200, string copy added** | **500** | same |
| profile | client hex | 500 | 500 | `profile.js:66-68` |
| profile | server-assigned ObjectId | 200, string copy added | 500 | same |
| food, activity | any | 200, replaced (string) / string copy added (OID) | 200, replaced, one record | `food.js:46,56`; `activity.js:46,56` |
| treatments | any | upsert by `_id`; a string original gets an ObjectId copy beside it | upsert by `_id`, string original removed | `treatments.js:90,165-171,315-320` |
| entries | matched on `sysTime`+`type` | see C81 | see C81 | `entries.js:128-141` |
| websocket `dbAdd` | server-assigned ObjectId, dedup query misses | `[doc]`, string copy added | `[]`, nothing stored | `websocket.js:549-561` |

Measured: Q2 (re-send alone 200 → 500), Q2b, Q5 (`dbAdd` devicestatus with the id of an ObjectId
record and a new `created_at`: 15.0.8 `ack = sent`, n=2; candidate `[]`, n=1), P-ID-6.

## C70 — entries POST reply names the stored reading's `_id`

- **Before:** a reply item's `_id` came only from `upsertedIds`; a reading that matched a stored one was
  echoed with the id it was sent with, or none (`92d08342:lib/server/entries.js:154-157`).
- **After:** one extra read over the matched `{sysTime, type}` filters sets each matched item's `_id`
  to the stored one (`lib/server/entries.js:156-178`, called `:198`); a failed read still answers 200.
- **Measured:** P-ID-3 "re-send without _id": `reply no _id` → `reply = stored`.
- No client in the corpus reads ids from this reply (see clients-8758.md).

## C71 — upper-case hex ids

- `GET`/`DELETE /api/v1/entries/<UPPER-HEX>`: 15.0.8 read it as an entry **type** (`ID_PATTERN = /^[a-f\d]{24}$/`)
  and found nothing; `ab7b22d6` uses `isHexId` (`lib/api/entries/index.js:14`). Measured P-ID-3: n=0 → n=1.
- Replies for records created with an upper-case hex `_id` (C68) are lower case.
- Treatments PUT with an upper-case string `_id` over an upper-case string record: 15.0.8 leaves the string and
  adds an ObjectId copy; `ab7b22d6` leaves one ObjectId record (measured Q11). A v1 PUT sets no `srvModified`, so
  neither build shows the change in `/api/v3/treatments/history` (Q11: n=0 on both).

## C72 — `find[_id]=<hex>` and delete by id reach both stored forms

- **Before:** `find[_id]=<hex>` became an ObjectId equality (`92d08342:lib/server/query.js:95-123`); a record stored
  with the 24-hex **string** was not returned and not deleted.
- **After:** `query_for` → `matchEitherForm` in entries (`entries.js:240`), treatments (`treatments.js:280`),
  devicestatus, profile (`profile.js:167`), activity (`activity.js:112`); `getEntry` uses all forms
  (`entries.js:225`); profile/food/activity `remove` use `idFilter` + `deleteMany` (`profile.js:198`, `food.js:187`,
  `activity.js:143`). Food's GET routes ignore `find` on every build.
- **Measured:** Q14 `find[_id]=<hex>&count=1` on a string record: n=0 → n=1; ObjectId record n=1 both; absent id n=0 both.
  Q6 control: string-stored entry n=0 → n=1.
- Unchanged: range operators. `find[_id][$gt]=<hex>` is an ObjectId bound on both builds and never matches a
  string `_id` (Q6 cursor: `111,113` on both).

## C73 — `find[_id][$in]` and `find[_id][$nin]` name both forms (`1c2d1afd`)

- **Before:** each list value became an ObjectId (`92d08342:lib/server/query.js:114`); a string-stored record
  was outside `$in` and inside `$nin`.
- **After:** each 24-hex value is expanded to all its forms; other values normalised as before
  (`ab7b22d6:lib/server/query.js:132-143`). ObjectId instances passed in-process are kept as given and not expanded.
- **Measured (Q4, twin + string-only + ObjectId record):**
  - `GET …find[_id][$in][]=<twin>&…[]=<string-only>`: n=1 → n=3;
  - `GET …find[_id][$nin][]=<twin>` over the four: `keep, string-only, twin-string` → `keep, string-only`;
  - `DELETE …find[_id][$in][]=<twin>&…[]=<string-only>`: 15.0.8 leaves the twin's string half and the string-only
    record; `ab7b22d6` removes all three; the unlisted record is kept on both.
- **Consumer effect:** a bulk delete by an `_id` list can now remove records 15.0.8 left (only copies of the listed
  ids). No client in the corpus sends `find[_id][$in]` or `$nin` over HTTP (clients-8758.md).

## C74 — a delete by id removes every stored copy of that id

- v1 DELETE by id (entries, treatments, devicestatus via `deleteMany(query_for)`; profile, food, activity via
  `idFilter`) and websocket `dbRemove` (`websocket.js:804`, `deleteMany`) remove the string copy and the ObjectId
  copy of a twin. 15.0.8 removed the ObjectId half only.
- API v3 DELETE by identifier removes or marks **one** document on both builds (C75).
- **Measured:** Q4 entries DELETE `/entries/<hex>` on a twin n=1 → n=0; Q12 Loop's `DELETE /treatments/<hex>` on a
  twin n=1 → n=0; P-ID-7 v1 and websocket n=1 → n=0, v3 permanent DELETE n=1 on both.
- A twin is two stored copies of one record; they arise only where a ≤15.0.8 edit met a record stored by ≤15.0.6.
  Status: behaviour kept by decision (BF-110).

## C75 — API v3 by `identifier` reaches records with a string `_id`; writes take the document GET returns

- **Before:** `filterForOne` = `identifier == X` or (24-hex) `_id == ObjectId(X)` (`92d08342:lib/api3/storage/mongoCollection/utils.js:107`);
  a string-`_id` v1 record was listed under `identifier = _id` but GET/PATCH/DELETE answered 404, and a v3 write added a copy.
- **After:** a 24-hex identifier matches `_id` in every form; any other string matches `_id` literally
  (`utils.js:105-121`, `:135-152`); `replaceOne`/`updateOne`/`deleteOne` first pick the document a read returns
  (sorted `identifier: -1`) and write that one (`modify.js:35-41`, used `:52,67,81`, `a2c7eb39`).
- **Measured:** P-ID-2 GET/PATCH/DELETE of a string record: 404 → 200; P-ID-10 v1/v3 pair: DELETE and PUT take the
  v3 copy on both builds.
- **Twin under v3 soft DELETE (measured Q10, Q10b):** both builds mark one half `isValid:false` and leave the other
  valid. 15.0.8 marks the ObjectId half; `ab7b22d6` marks the string half. On both builds the remaining valid copy is
  returned by a v1 time-window read and by a v3 search, so a record AndroidAPS deleted through v3 stays visible.
  Same effect on both builds; see CANDIDATE-3 in clients-8758.md.

## C76 — websocket `dbUpdate`, `dbUpdateUnset`, `dbRemove` match both forms

- **Before:** `safeObjectID` + `updateOne`/`deleteOne({_id: ObjectId})` (`92d08342:lib/server/websocket.js:15,358,411,749`):
  a string record was missed and the reply still said `{result:'success'}`.
- **After:** `idMatch` (`websocket.js:15-20`): `$in` of all forms with `updateMany`/`deleteMany` for a 24-hex id
  (`:383,440,804`); any other id exact, one record. Reply shapes unchanged.
- **Measured:** P-ID-4 `dbUpdate` on a string record: unchanged → edited; `dbRemove` n=1 → n=0; AAPS 3.x add-then-update
  control identical.

## C77 — websocket `dbAdd` with a 24-hex `_id` that collides answers `[]`

- The treatments, devicestatus and profile dedup queries (`NSCLIENT_ID`, `created_at`, `startDate`) run after the new
  id lookup and are unchanged. When they miss and the converted id already exists as an ObjectId, the insert collides
  and the reply is `[]`; on 15.0.8 a string copy was inserted and the reply was `[doc]`.
- **Measured:** Q5 devicestatus with the id of an ObjectId record and a new `created_at`: `ack = sent`, n=2 → `[]`, n=1.
  Q9 AAPS 3.x `dbAdd` shapes (no `_id`): identical on both builds (`[doc]`, same `_id` on the re-send, n=1).
- AndroidAPS 3.4.x marks a record uploaded with no Nightscout id when the ack is `[]`
  (clients-8758.md, AndroidAPS); it sends no `_id` on `dbAdd`, so this path does not reach it.

## C78 — devicestatus re-send guard, and the records after it in the same POST

- The guard (`ad973110`, `devicestatus.js:50-71`) keeps an id already stored as a string so a re-send collides (500)
  instead of adding an ObjectId copy.
- Insert is `insertMany(…, {ordered:true})` (`devicestatus.js:108`) on both builds: records before a collision are
  stored, records after it are not, and the reply is `500 Mongo Error` (`lib/api/devicestatus/index.js:173`).
- **Measured (Q2b, a fresh server-assigned record re-posted with its own `_id`):**

| request | 15.0.8 | `ab7b22d6` | `ab7b22d6` with dev's `devicestatus.js` |
|---|---|---|---|
| `[re-sent, NEW]` | 200, string copy added, NEW stored | **500, NEW not stored** | 200, string copy added, NEW stored |
| `[NEW, re-sent]` | 200, string copy added, NEW stored | 500, NEW stored | 200, as 15.0.8 |
| re-sent alone, upper case | 200, string copy added | 500 | 200, as 15.0.8 |

  The ablation isolates the change to `lib/server/devicestatus.js`. A client's own hex id re-sent, or a string-stored
  record re-sent, gives 500 on both builds (Q2), and the records after it are not stored on either.
- No uploader in the corpus re-posts a devicestatus with a server-assigned `_id` (clients-8758.md). See CANDIDATE-2.

## C79 — auth subject and role delete matches both forms

- `remove` = `deleteMany({_id: idFilter(_id)})` (`ab7b22d6:lib/authorization/storage.js:160`); 15.0.8 `deleteOne({_id: ObjectId})`
  (`92d08342:lib/authorization/storage.js:100`).
- Create on dev (#8754) stores only owned fields, so a client `_id` is not stored at all (`ab7b22d6` drops the create
  half of `d2fd9ff6`).
- **Measured:** P-ID-12 subject POST with a hex `_id`: 15.0.8 stores it as that string; `ab7b22d6` stores the subject
  under a server id (no document with that hex). That a subject already stored as the string is removed by DELETE
  on `ab7b22d6` is covered by `tests/storage.shape-handling.test.js:809` and was not replayed.
- No client in the corpus creates a subject with an `_id` or deletes a subject (LoopFollow creates one without `_id`).

## C80 — profile PUT with a non-hex `_id`

- 15.0.8: `new ObjectID(obj._id)` accepted any 12-character string as 12 raw bytes (`92d08342:lib/server/profile.js:70`).
- `ab7b22d6`: only an ObjectId or 24-hex string names the profile to replace; anything else gets a new ObjectId
  (`profile.js:103-108`, `dd2cf8f1`). The v1 route still refuses a non-hex `_id` with 400 before storage, so over HTTP
  this is reached only by in-process callers. Read-derived; covered by `tests/storage.shape-handling.test.js:432`.

## C81 — entries POST writes `_id` only when it inserts

- **Before:** `{ $set: doc }` including `_id`; when the reading matched a stored one (same `sysTime`+`type`) under another
  `_id`, MongoDB refused the change to `_id` and the ordered bulk write stopped: **500**, and every later reading in
  that POST was not stored.
- **After:** `$set` without `_id`, `$setOnInsert: {_id}` (`entries.js:128-141`); the stored reading keeps its `_id`; 200.
- **Measured:** Q8 (the connector's copy shape: a reading at T already stored under another `_id`, then a new
  reading at T+5 min in the same POST): 15.0.8 **500, the T+5 min reading missing**; `ab7b22d6` 200, both stored,
  the T reading keeps its first `_id`. P-ID-3 500 → 200.
- Unchanged (Q3): a batch whose re-sent item carries the same `_id` it is stored under answers 200 on both; a new
  reading at a new time that reuses another stored reading's `_id` collides and answers 500 on both, and the readings
  after it are not stored on either.

## Not settled

- The #8758 test suite was not run in this pass.
- The `data-update` event for string copies removed by `withStaleStringsRemoved`: not verified by running (open pages
  may keep an old copy until reload).
- One pre-existing defect on 15.0.8 found during these replays is reported to the parent separately under the
  disclosure rule; it is not caused or changed by #8758.
