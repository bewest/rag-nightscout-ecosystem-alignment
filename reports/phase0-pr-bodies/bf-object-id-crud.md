# `bf/object-id-crud`: create, read, update and delete by `_id` work the same way through API v1, API v3 and the websocket, with a matrix test over every collection

**DRAFT. Local branch, not pushed.** Branch `bf/object-id-crud` on `bf/object-id-consistency`
`597e2899` (itself on `origin/dev` `1f9a9d10`), tip `6d120fa2`, eight commits. No `CHANGELOG.md`
edit. Lands after, or together with, `bf/object-id-consistency`, and replaces the narrow
`bf/object-id-other-collections` and `bf/api3-string-id` (which now conflict with it). Evidence:
[`docs/60-research/remedial/crud-by-id-matrix-2026-09-23.md`](../../docs/60-research/remedial/crud-by-id-matrix-2026-09-23.md).
Continues the "Not in this branch" list of
[`bf-object-id-consistency.md`](bf-object-id-consistency.md). Commits 5 to 8 apply the
maintainer's decisions D1 to D4 of 2026-09-23.

| what changes | who can see it |
|---|---|
| a glucose reading re-sent with its own `_id` updates the stored reading instead of answering 500 when the stored reading has another `_id` (for example one saved by 15.0.6 or earlier) | uploaders that send their own hex `_id`, on sites that hold such readings |
| a glucose reading that updates a stored one is answered with the stored reading's `_id`, instead of the `_id` it was sent with or `null` | API clients that read the `_id` back from an entries POST |
| `GET` and `DELETE /api/v1/entries/<id>` accept the id in upper case, as every other v1 path does | API clients that write ids in upper case |
| a record added over the websocket with its own 24-hex `_id` is stored with an ObjectId `_id`, and websocket edits and deletes find a record whichever form its `_id` is stored in | clients that use the websocket `dbAdd` / `dbUpdate` / `dbRemove` messages |
| API v3 reads, replaces and deletes a record whose `_id` is a text id that is not 24-hex (a UUID treatment or entry from 15.0.6 or earlier, or a custom websocket id), and a v3 write for it no longer adds a second record | API v3 clients on those sites |
| a device status report re-sent with the `_id` of a copy stored as a string is refused again, as on dev, instead of being stored twice | sites fed by the Nightscout connector's Nightscout source, and clients that send their own `_id` |
| a new test, `tests/api.crud-by-id.matrix.test.js`, records the outcome of 336 create/read/update/delete cells | reviewers |
| a custom non-hex `_id` over the websocket, the UUID handling of treatments and entries, the 400 for a non-hex `_id` on the other v1 routes, and a re-sent profile (still refused) are unchanged | nobody; stated so a reviewer does not have to infer it |

---

## What changes for you

*Plain-language summary for people running their own Nightscout site. Nightscout is not a medical
device and none of this is medical advice. If your readings, treatments or settings look wrong,
check them with your care team before relying on them.*

A few words used below:

- **Record**: one saved item, such as a glucose reading (an "entry"), a treatment, a device status
  report from a phone or pump, a food, or a profile (your saved settings).
- **ID**: the label Nightscout gives each saved record so it can find it again.
- **Websocket**: a live connection some apps keep open to Nightscout to send and change records.
- **API v3**: a newer way for apps to read and write Nightscout data.
- **Uploader**: the app or device that sends your readings to Nightscout.

### What was wrong

- If your site holds glucose readings saved by **Nightscout 15.0.6 or earlier**, and an uploader
  sent a reading again **with its own ID**, Nightscout answered with an error instead of updating
  the reading. When a reading did update an earlier one, Nightscout told the app the wrong ID, or
  none, for it.
- An app asking for, or deleting, a glucose reading by an ID written in **capital letters** got
  nothing back, and nothing was deleted.
- A record an app added over the **websocket** with its own ID was saved in a form the websocket
  could not find again. Editing or deleting it over the websocket did nothing, although
  Nightscout reported success, and sending it again could save a second copy.
- Apps using **API v3** could not open, change or delete some older records whose ID is not in
  Nightscout's usual form, though they could see them in lists; changing one saved a second copy.
- A **device status report** sent again could be saved twice.

### What this change does

- A reading sent again with its own ID updates the reading already saved at that time, and the app
  is told that reading's ID.
- An ID in capital letters finds and deletes the same reading as the same ID in small letters.
- Records added over the websocket with their own ID are saved in the normal form, and websocket
  edits and deletes find records whichever way their ID was saved.
- API v3 finds, changes and deletes those older records by the ID it lists them under.
- A device status report sent again is refused, as before, instead of being saved twice.

Nothing in your database changes until a record is written, edited or deleted.

**What you should do:** nothing, for most sites. If an app told you it had edited or deleted a
record but the record did not change, try the change again after upgrading. If you see two copies
of one record, you can now delete the extra one. If you are unsure which readings, treatments or
settings are correct, check with your care team.

---

## Technical detail

### What the matrix found

`tests/api.crud-by-id.matrix.test.js` (commit 4) seeds one record per cell with its `_id` stored as
an ObjectId (asked in lower or upper case), a lower- or upper-case hex string, or a UUID string,
and runs one operation through v1, API v3 or the websocket. The expected outcome of every cell is
in the test with its reason, including the deliberate differences (UUID → `identifier` for
treatments and entries; 400 for a non-hex `_id` elsewhere on v1; a custom `_id` kept as given by
the websocket; v3 identifiers immutable, so a PUT naming an ObjectId record by its upper-case hex is
refused).

| tree | `mongo:7` passing / failing | MongoDB 4.4 |
|---|---|---|
| `origin/dev` `1f9a9d10` | 176 / 160 | 176 / 160 |
| `bf/object-id-consistency` `597e2899` | 266 / 70 | 266 / 70 |
| `bf/object-id-crud` `6d120fa2` | 336 / 0 | 336 / 0 |

On `597e2899` the 70 are:
- entries re-POST of a string-stored hex `_id` answers 500 (2 cells);
- `GET` / `DELETE /entries/<UPPER>` find nothing (4);
- a devicestatus re-sent with the `_id` of a string copy is stored twice (2);
- API v3 on a record with a UUID `_id`: 404, second records, 500 (20);
- the websocket (42): `dbAdd` stores a hex `_id` as the string; `dbUpdate` and `dbRemove` miss a
  string-stored hex `_id` while replying success; a re-sent ObjectId record gets a string copy in
  the generic collections.

### What the commits do

1. **`4b41bcf8` entries re-POST.** `lib/server/entries.js` `create()`: the sent `_id` goes in
   `$setOnInsert`, not `$set`, so it is written only when the upsert inserts. A reading matched by
   `sysTime` + `type` keeps its own `_id`, as a POST without `_id` does; before, MongoDB refused the
   change of `_id` and the POST answered 500 (also for a hex `_id` that differs from the stored
   ObjectId, which is how the existing dedup treats a different UUID, `TEST-ENTRY-UUID-003`).
2. **`a612a26f` upper-case ids.** `lib/api/entries/index.js` `isId` is the helper's `isHexId`
   (either case) instead of a lower-case-only pattern. `lib/api/shared/objectid-validation.js`
   uses the same helper instead of its own copy (it already accepted either case). Why accept upper
   case: an ObjectId's hex names the same id in either case, and `find[_id]`, the other v1 routes,
   the websocket and API v3 all accepted it; the entries route was the one path that did not.
3. **`12c01268` websocket.** Through `lib/server/object-id-forms.js`: `dbAdd` stores a 24-hex
   `_id` as the ObjectId it names unless the same id is already stored as a string (one indexed
   read, only for a record carrying a 24-hex `_id`), in which case the insert collides with it as
   before. `dbUpdate`, `dbUpdateUnset` and `dbRemove` match a 24-hex `_id` in either form and reach
   an ObjectId copy and a string copy alike; a custom string `_id` keeps the exact match and
   `updateOne`/`deleteOne`. The similar-treatment dedup updates by the stored `_id` as it is.
4. **`c721e202` matrix test.**
5. **`44ac9047` API v3 and a non-hex `_id` (D2).** `filterForOne` and `identifyingFilter` also
   match a non-hex **string** identifier against `_id`, with the same literal `$eq`; a non-string
   (operator-shaped) identifier gets no `_id` branch and is still compared literally.
   `lib/api3/swagger.yaml` line 1112 documents this addressing. `tests/api3.storage.modify.test.js`
   asserted the old exact filter for a non-hex identifier; its three assertions are updated to the
   new shape. `explain()` on `mongo:7`, all five v3 collections: OR of IXSCAN on `_id_` and
   `identifier_1` (plus the dedup-field index where used), one to three documents examined, no
   COLLSCAN.
6. **`18b09df7` stored `_id` in the entries POST response (D3).** After the write, the stored `_id`
   of every reading that matched a stored one is read back in one `find` for the whole batch (an
   `$or` of the same `sysTime` + `type` filters), only when some reading matched, and set on the
   response, for a POST that carried another `_id` and for one that carried none (which answered
   `null`). Every item in a v1 POST response is expected to carry an `_id`
   (`docs/proposals/TEST-IMPLEMENTATION-SUMMARY.md` §6.1.2), and no existing test expected `null`.
   If the read-back fails, the POST still answers 200 with the readings stored.
7. **`ad973110` devicestatus re-send guard (D1).** For a batch that carries 24-hex `_id`s, one
   `find({_id: {$in: <string forms>}}, {_id: 1})`; ids found keep their stored value, so a re-send
   collides and is refused as on dev and as a profile re-send is (BF-99). No read for a batch
   without 24-hex `_id`s. Measured cost (100-row batch, in-process create, `mongo:7`, 20,000 stored
   rows, 40 runs, two repeats): median 5.29 / 5.09 ms with hex `_id`s against 4.18 / 4.17 ms before
   the guard; without `_id`s 4.14 / 3.93 ms against 4.06 / 4.09 ms. About 1 ms per hex batch; the
   `find` alone is 0.67 ms median, a covered IXSCAN on `_id_`.
8. **`6d120fa2` helper header (D4).** Comment only: a string `_id` stored in upper case is found
   when asked for in that spelling, not in lower case; the header's non-hex rules now include the
   websocket and API v3.

### Tests

New: `tests/api.entries.repost-with-id.test.js` (18), `tests/api.entries.upper-case-id.test.js`
(5), `tests/websocket.object-id.test.js` (13), `tests/api.crud-by-id.matrix.test.js` (336),
`tests/api3.non-hex-id.test.js` (16), `tests/api.devicestatus.resend-guard.test.js` (8). Changed:
`tests/api3.storage.modify.test.js` (three filter-shape assertions, D2).

Red on `597e2899`: 11/18, 3/5, 10/13, 70/336, 11/16, 5/8. Each commit's own tests were red on its
parent (4/8, 3/5, 10/13, —, 11/16, 7/18, 5/8). The passing ones are controls: the stored `_id`
re-sent, a new record, a POST without `_id`, `/entries/sgv`, an ObjectId-stored record, an
operator-shaped identifier, a batch without `_id`s, a failed read-back.

Full suite (`npm test`, `mongo:7`), passing / failing / pending:

| tree | Node 20.20.0 | Node 22.23.2 | new tests |
|---|---|---|---:|
| `bf/object-id-consistency` `597e2899` | 2470 / 0 / 3 | 2470 / 0 / 3 | — |
| 1 `4b41bcf8` | 2478 / 0 / 3 | 2478 / 0 / 3 | +8 |
| 2 `a612a26f` | 2483 / 0 / 3 | 2483 / 0 / 3 | +5 |
| 3 `12c01268` | 2496 / 0 / 3 | 2496 / 0 / 3 | +13 |
| 4 `c721e202` | 2832 / 0 / 3 | 2832 / 0 / 3 | +336 |
| 5 `44ac9047` | 2848 / 0 / 3 | 2848 / 0 / 3 | +16 |
| 6 `18b09df7` | 2858 / 0 / 3 | 2858 / 0 / 3 | +10 |
| 7 `ad973110` | 2866 / 0 / 3 | 2866 / 0 / 3 | +8 |
| 8 `6d120fa2` | 2866 / 0 / 3 | 2866 / 0 / 3 | 0 |

Breaking the fix, each part removed singly, the commit's own test file: every part turned at least
one test red (table in the evidence file §4). Commit 8 is comment only.

### Merges

`git merge-tree --write-tree`, `6d120fa2` against each open 15.0.9 head:

| head | result |
|---|---|
| #8748 `d19043b2`, #8749 `46b20b38`, #8751 `b5038500`, #8753 `e6a50e9a`, #8754 `0a74ef4e`, #8755 `92544d8f`, #8756 `83cfff14`, #8757 `5d342ac1`, `rc/15.0.9-additions-e` `1b1977e0` | clean |
| `bf/profile-object-id` `9b8cc2f9` | conflict in `lib/server/profile.js`, inherited from `597e2899` (land one) |
| `bf/object-id-other-collections` `2fac53f5`, `bf/api3-string-id` `7295bc8c` | conflict in `lib/server/object-id-forms.js` (and, for the second, the v3 filters): the narrow alternatives this branch's base already carries; not landed beside it |

The merged tree with `rc/15.0.9-additions-e` passes the websocket, matrix, entries, devicestatus
and v3 storage test files (439 / 0). The full suite was not run on merged trees.

### Decisions taken

D1 add the devicestatus guard (commit 7); D2 take the v3 fix (commit 5); D3 answer the stored
`_id` (commit 6); D4 leave the upper-case string limit and state it (commit 8). Evidence file §5.
