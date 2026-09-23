# `bf/object-id-crud`: create, read, update and delete by `_id` work the same way through API v1 and the websocket, with a matrix test over every collection

**DRAFT. Local branch, not pushed.** Branch `bf/object-id-crud` on `bf/object-id-consistency`
`597e2899` (itself on `origin/dev` `1f9a9d10`), tip `c721e202`, four commits. No `CHANGELOG.md`
edit. Lands after, or together with, `bf/object-id-consistency`. Evidence:
[`docs/60-research/remedial/crud-by-id-matrix-2026-09-23.md`](../../docs/60-research/remedial/crud-by-id-matrix-2026-09-23.md).
Continues the "Not in this branch" list of
[`bf-object-id-consistency.md`](bf-object-id-consistency.md).

| what changes | who can see it |
|---|---|
| a glucose reading re-sent with its own `_id` updates the stored reading instead of answering 500 when the stored reading has another `_id` (for example one saved by 15.0.6 or earlier) | uploaders that send their own hex `_id`, on sites that hold such readings |
| `GET` and `DELETE /api/v1/entries/<id>` accept the id in upper case, as every other v1 path does | API clients that write ids in upper case |
| a record added over the websocket with its own 24-hex `_id` is stored with an ObjectId `_id`, and websocket edits and deletes find a record whichever form its `_id` is stored in | clients that use the websocket `dbAdd` / `dbUpdate` / `dbRemove` messages |
| a new test, `tests/api.crud-by-id.matrix.test.js`, records the outcome of 336 create/read/update/delete cells | reviewers |
| a custom non-hex `_id` over the websocket, the UUID handling of treatments and entries, the 400 for a non-hex `_id` on the other v1 routes, and API v3 are unchanged | nobody; stated so a reviewer does not have to infer it |

---

## What changes for you

*Plain-language summary for people running their own Nightscout site. Nightscout is not a medical
device and none of this is medical advice. If your readings, treatments or settings look wrong,
check them with your care team before relying on them.*

A few words used below:

- **Record**: one saved item, such as a glucose reading (an "entry"), a treatment, a device status
  report, a food, or a profile (your saved settings).
- **ID**: the label Nightscout gives each saved record so it can find it again.
- **Websocket**: a live connection some apps keep open to Nightscout to send and change records.
- **Uploader**: the app or device that sends your readings to Nightscout.

### What was wrong

- If your site holds glucose readings saved by **Nightscout 15.0.6 or earlier**, and an uploader
  sent a reading again **with its own ID**, Nightscout answered with an error instead of updating
  the reading. The same reading sent without an ID was accepted.
- An app asking for, or deleting, a glucose reading by an ID written in **capital letters** got
  nothing back, and nothing was deleted.
- A record an app added over the **websocket** with its own ID was saved in a form the websocket
  could not find again. Editing or deleting it over the websocket did nothing, although
  Nightscout reported success, and sending it again could save a second copy.

### What this change does

- A reading sent again with its own ID updates the reading already saved at that time.
- An ID in capital letters finds and deletes the same reading as the same ID in small letters.
- Records added over the websocket with their own ID are saved in the normal form, and websocket
  edits and deletes find records whichever way their ID was saved, including records saved the
  old way. Nothing in your database changes until a record is written, edited or deleted.

**What you should do:** nothing, for most sites. If an app told you it had edited or deleted a
record but the record did not change, try the change again after upgrading. If you are unsure
which readings or treatments are correct, check with your care team.

---

## Technical detail

### What the matrix found

`tests/api.crud-by-id.matrix.test.js` (commit 4) seeds one record per cell with its `_id` stored as
an ObjectId (asked in lower or upper case), a lower- or upper-case hex string, or a UUID string,
and runs one operation through v1, API v3 or the websocket. The expected outcome of every cell is
in the test with its reason, including the deliberate differences (UUID → `identifier` for
treatments and entries; 400 for a non-hex `_id` elsewhere on v1; a custom `_id` kept as given by
the websocket; v3 identifiers immutable).

| tree | passing / failing, `mongo:7` | MongoDB 4.4 |
|---|---|---|
| `origin/dev` `1f9a9d10` | 194 / 142 | not run |
| `bf/object-id-consistency` `597e2899` | 288 / 48 | 288 / 48 |
| `bf/object-id-crud` `c721e202` | 336 / 0 | 336 / 0 |

On `597e2899` the 48 are: entries re-POST of a string-stored hex `_id` (2 cells, 500), `GET`/`DELETE
/entries/<UPPER>` (4), and 42 websocket cells (dbAdd stores a hex `_id` as the string; dbUpdate
and dbRemove miss a string-stored hex `_id`, replying success; a re-sent ObjectId record gets a
string copy in the generic collections). 22 cells are kept as they are pending a decision (below).

### What the commits do

1. **`4b41bcf8` entries re-POST.** `lib/server/entries.js` `create()`: the sent `_id` goes in
   `$setOnInsert`, not `$set`, so it is written only when the upsert inserts. A reading matched by
   `sysTime` + `type` keeps its own `_id`, as a POST without `_id` does; before, MongoDB refused the
   change of `_id` and the POST answered 500. This also covers a hex `_id` that differs from the
   stored entry's ObjectId (500 on dev), which is how the existing dedup treats a different UUID at
   the same time (`TEST-ENTRY-UUID-003`).
2. **`a612a26f` upper-case ids.** `lib/api/entries/index.js` `isId` is the helper's `isHexId`
   (either case) instead of a lower-case-only pattern, so `GET`/`DELETE /entries/<UPPER>` address
   the entry. `lib/api/shared/objectid-validation.js` uses the same helper instead of its own copy
   of the pattern (it already accepted either case; unchanged). Why accept upper case: an ObjectId's
   hex names the same id in either case (`new ObjectId('5F…')` is valid), and `find[_id]`, the
   devicestatus/food/activity/profile `_id` checks, the websocket and API v3 all accepted it; the
   entries route was the one path that did not.
3. **`12c01268` websocket.** `lib/server/websocket.js`, through `lib/server/object-id-forms.js`:
   `dbAdd` stores a 24-hex `_id` as the ObjectId it names unless the same id is already stored as
   a string (one indexed read, only for a record carrying a 24-hex `_id`), in which case the stored
   value is kept so the insert collides with it as before. `dbUpdate`, `dbUpdateUnset` and
   `dbRemove` match a 24-hex `_id` in either form and write with `updateMany`/`deleteMany`, so an
   ObjectId copy and a string copy of one id are both reached; a custom string `_id` keeps the
   exact match and `updateOne`/`deleteOne`. The similar-treatment dedup updates by the stored
   `_id` as it is (it converted a stored hex string to an ObjectId and missed). `safeObjectID` and
   its copy of the pattern are gone.
4. **`c721e202` matrix test.**

### Tests

New: `tests/api.entries.repost-with-id.test.js` (8), `tests/api.entries.upper-case-id.test.js` (5),
`tests/websocket.object-id.test.js` (13), `tests/api.crud-by-id.matrix.test.js` (336).

Red on `597e2899`, and the same on `origin/dev` `1f9a9d10`: 4/8, 3/5, 10/13. The passing ones are
controls: a re-POST with the `_id` already stored, a new entry, an entry without `type`, a POST
without `_id`; `GET /entries/<lower>` and `/entries/sgv`; a re-send of a string-stored record, a
dbUpdate of an ObjectId-stored record, and a re-send of an upper-case string record in upper case.

Full suite (`npm test`, `mongo:7`), passing / failing / pending:

| tree | Node 20.20.0 | Node 22.23.2 | new tests |
|---|---|---|---:|
| `bf/object-id-consistency` `597e2899` | 2470 / 0 / 3 | 2470 / 0 / 3 | — |
| 1 `4b41bcf8` | 2478 / 0 / 3 | 2478 / 0 / 3 | +8 |
| 2 `a612a26f` | 2483 / 0 / 3 | 2483 / 0 / 3 | +5 |
| 3 `12c01268` | 2496 / 0 / 3 | 2496 / 0 / 3 | +13 |
| 4 `c721e202` | 2832 / 0 / 3 | 2832 / 0 / 3 | +336 |

Every step is exactly the new test file; no existing test changed.

Breaking the fix, each part removed singly, the commit's own test file (Node 20.20.0): every part
turned at least one test red (table in the evidence file §4).

### Merges

`git merge-tree --write-tree`, `c721e202` against each open 15.0.9 head:

| head | result |
|---|---|
| #8748 `d19043b2`, #8749 `46b20b38`, #8751 `b5038500`, #8753 `e6a50e9a`, #8755 `92544d8f`, #8756 `83cfff14` | clean |
| #8754 `0a74ef4e`, `rc/15.0.9-additions-e` `1b1977e0` | clean (the first build of commit 3, `f433dc16`, conflicted in `lib/server/websocket.js`; `12c01268` moves one `require` line) |
| #8757 `5d342ac1` | clean |
| `bf/profile-object-id` `9b8cc2f9` | conflict in `lib/server/profile.js`, inherited from `597e2899` (land one) |
| `bf/object-id-other-collections` `2fac53f5`, `bf/api3-string-id` `7295bc8c` | clean |

The merged tree with `rc/15.0.9-additions-e` passes the websocket, matrix and entries test files
(396 / 0). The full suite was not run on merged trees.

### Decisions for the maintainer (not in this branch)

Each is measured in the evidence file §5, with its tradeoff.

- **D1.** A devicestatus re-sent through v1 with the `_id` of a string-stored copy is stored beside
  it (dev refuses it with 500). Keep (no read added to devicestatus creates; the connector does not
  re-send), or add BF-99's guard (one indexed read per batch carrying hex `_id`s).
- **D2.** API v3 cannot address a v1 record whose `_id` is a non-hex string (a UUID stored by
  treatments or entries up to 15.0.6, or a custom id kept by the websocket): GET and DELETE 404,
  PUT adds a second record, POST answers 500 and adds a second record for treatments, entries and
  devicestatus. `lib/api3/swagger.yaml` says such an identifier addresses the record. A two-branch
  fix is written and measured (all 20 cells consistent) but changes the filter that
  `tests/api3.storage.modify.test.js` asserts for a non-hex identifier, so it is not in this branch.
- **D3.** An entry POST whose hex `_id` differs from the entry stored at that time and type now
  updates that entry, and the response echoes the sent `_id`, not the stored one. Leave, read the
  stored `_id` back, or omit it.
- **D4.** A string `_id` stored in upper case is found only when asked in upper case, on every
  path using the helper; adding the upper-case spelling to `idForms` changes
  `tests/object-id-forms.test.js`.
