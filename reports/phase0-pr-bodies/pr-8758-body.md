<!-- Body for nightscout/cgm-remote-monitor#8758 at head 6c3ccce6 (2026-09-25; ab7b22d6 plus part 4, local until pushed). This comment is hidden on GitHub. -->
Records keep their own `_id`, and create, read, update and delete by that `_id` work the same way in every collection, through API v1, API v3 and the websocket. Seventeen commits on `dev` `1f9a9d10`: the first five fix the defects, the next eight close the gaps a new create/read/update/delete matrix test found, and the last four fix what a review of this PR found (part 3). Then `dev` is merged in (`572bfc32`), with one follow-up for a change `dev` made to access entries (`ab7b22d6`), and three fixes from the 15.0.9 freeze review (part 4).

## Part 1: a record's own `_id` finds, edits and deletes it

### What changes for you

*Plain-language summary for people running their own Nightscout site. Nightscout is not a medical
device and none of this is medical advice. If your settings or history look wrong, check them
with your care team before relying on them.*

A few words used below:

- **Record**: one saved item, such as a treatment, a glucose reading (an "entry"), a device status
  report from a phone or pump, a food, or a profile.
- **Profile**: the saved settings Nightscout shows and uses for its reports and calculations,
  such as basal rates, insulin sensitivity and carb ratios.
- **Connector**: the part of Nightscout that copies data in from another service, including from
  another Nightscout site.
- **ID**: the label Nightscout gives each saved record so it can find it again.
- **API v3**: a newer way for apps to read and write Nightscout data.

#### What was wrong

Some records were saved with their ID written in a different form from the one Nightscout uses
to look records up. This happened to:

- profiles, device status reports, foods and activity records that arrived with their own ID,
  for example **copied from another Nightscout site by the connector** or **restored from an
  export**;
- treatments and glucose readings that arrived with their own ID on **Nightscout 15.0.6 or
  earlier**, if your site has been running since then.

Nightscout could show those records, but could not find them again by their ID. So **editing**
one saved a **second copy** with your changes and **kept the old one**, and **deleting** it by its
ID did not remove it. Apps that use API v3 could not see those records by their ID either, and
sending one again through API v3 stored a second copy.

#### What this change does

- Records that arrive with their own ID are saved in the normal form from now on.
- Records **already saved** the old way are found, and are fixed the first time they are edited:
  the edit replaces the old copy and you are left with **one** record. Nothing in your database
  changes until a record is edited or deleted.
- Deleting such a record now removes it, including a copy left by an earlier edit.

**What you should do:** nothing, for most sites. If your site receives data from another
Nightscout site through the connector, or you have restored data from an export, or your site
has been running since 15.0.6 or earlier, and you have edited a profile or treatment there, look
at it after upgrading. If you see an old copy beside the one you edited, open it in the profile
editor, or in the treatment list on the Reports page, and save it: the two become one record with
that edit. An edit made by dragging a treatment on the main chart, or from an app that uses API v3,
changes the record but leaves both copies. Deleting either copy deletes both, on a Nightscout page
or through API v3 (part 4).
If you are unsure which settings or entries are correct, check with your care team.

---

### Technical detail

#### The defect

A 24-hex string `_id` sent by a client was stored as the string itself by profile, devicestatus,
food and activity on every release to dev, and by treatments and entries up to 15.0.6 (measured
on 15.0.6; the REQ-SYNC-072 conversion first appears in 15.0.7). Every lookup by `_id` asks for
the ObjectId: `lib/server/query.js` converts `find[_id]`, and `save()`/`remove()`/`getEntry()`
build `new ObjectId(id)`. API v3's `filterForOne` and `identifyingFilter` match a v1 record's
`_id` as ObjectId only. So, measured on `origin/dev` `1f9a9d10` against records stored with a
string `_id`:

| | find[_id] | GET by id | edit | DELETE by id | re-send |
|---|---|---|---|---|---|
| devicestatus | [] | — | — | nothing | 500 |
| food | — | — | ObjectId copy added | nothing | replaced |
| activity | [] | — | ObjectId copy added | nothing | replaced |
| treatments | [] | — | ObjectId copy added | nothing | ObjectId copy added |
| entries | [] | 500 "No such id" | — | nothing | 500 (unchanged, see below) |
| API v3 | — | 404 | 201, second record | 404 | 201, second record |

Profiles behave the same way.

#### What the commits do

1. **`1f9db1fe` helper.** `lib/server/object-id-forms.js`: `isHexId`, `toStoredId` (24-hex string
   → ObjectId), `idForms` (`[ObjectId, lower-case hex, as given]`), `matchEitherForm` (widens
   `query.js`'s ObjectId equality to `$in` of those), `staleStringForms` /
   `withStaleStringsRemoved` (after an upsert by the ObjectId, delete the string form of the same
   id). The header documents that the non-hex rule differs by collection and is not unified.
   Unit tests without a database.
2. **`09566345` profile.** The profile fix, on the shared helper: conversion on create, with the create guard
   that keeps a re-sent id already stored as a string colliding as before; PUT deletes the string
   form after the upsert; DELETE and `find[_id]` match both. `tests/api.profiles.object-id.test.js`
   is unchanged from the earlier profile-only fix.
3. **`80993afc` devicestatus, food, activity.** Conversion on create. `find[_id]` (devicestatus,
   activity; devicestatus DELETE uses the same query) matches both forms; food and activity
   DELETE match both; food and activity PUT, **and POST** (their create is an upsert by `_id`),
   delete the string form after the upsert in the same `bulkWrite`, so a re-POST still ends with
   one record, as on dev. devicestatus has **no create guard**: it would add a read to every
   connector batch. A devicestatus re-sent with the `_id` of a string copy is stored beside it
   (dev: 500); the connector's in-process output does not re-send (measured: it drops rows whose
   `created_at` is not strictly after the newest stored).
4. **`5581c5e4` treatments, entries.** `find[_id]` (and the DELETEs) and `GET /entries/<hex>`
   match both forms; a treatment write that matches by `_id` (PUT; POST of a record without
   `identifier`, on the batch path and on the one-at-a-time path a `preBolus` takes) deletes the
   string form after the upsert. The two REQ-SYNC-072 hex branches and `query.js`'s pattern use
   the helper; the UUID path is untouched and its tests pass unmodified.
5. **`597e2899` API v3.** `filterForOne` and `identifyingFilter` add one literal-`$eq` `$or`
   branch per form of the `_id`, keeping the existing selector-hardening tests' `$eq` shape.
   `explain()` on `mongo:7` over 5,001 documents: OR of IXSCAN on `_id_` and `identifier_1` for
   profile, food, treatments, entries and devicestatus; one or two documents examined; no
   COLLSCAN.

No migration and no bulk write at boot.

#### Tests

New: `tests/object-id-forms.test.js` (15), `tests/api.profiles.object-id.test.js` (13, from
this defect), `tests/api.object-id.other-collections.test.js` (31),
`tests/api.object-id.treatments-entries.test.js` (15), `tests/api3.string-id.test.js` (10).
Red on dev: 11/13, 27/31, 13/15, 9/10; the passing ones are controls (POST without `_id`, a
re-POST that dev already replaces in place, a record with an ObjectId `_id`).

Full suite, `mongo:7`, passing / failing / pending, each commit on its own:

| tree | Node 20.20.0 | Node 22.23.2 | new tests |
|---|---|---|---:|
| `origin/dev` `1f9a9d10` | 2386 / 0 / 3 | 2386 / 0 / 3 | — |
| a `1f9db1fe` helper | 2401 / 0 / 3 | 2401 / 0 / 3 | +15 |
| b `09566345` profile | 2414 / 0 / 3 | 2414 / 0 / 3 | +13 |
| c `80993afc` devicestatus, food, activity | 2445 / 0 / 3 | 2445 / 0 / 3 | +31 |
| d `5581c5e4` treatments, entries | 2460 / 0 / 3 | 2460 / 0 / 3 | +15 |
| e `597e2899` API v3 (tip) | 2470 / 0 / 3 | 2470 / 0 / 3 | +10 |
| `bf/object-id-other-collections` `2fac53f5` | 2432 / 0 / 3 | 2432 / 0 / 3 | +46 |
| `bf/api3-string-id` `7295bc8c` | 2411 / 0 / 3 | 2411 / 0 / 3 | +25 |

Every step is exactly the new test file(s); no existing test changed. (d and e were also run
before d gained its `preBolus` test, as `e10f9e48` 2459 and `30b130da` 2469, both green.)

No existing test expectation changed.

Breaking the fix (each part removed singly, the commit's own test file): every part turned at
least one test red; the table is in the evidence file §7. One break went green on the first
try (the one-at-a-time treatment POST path had no test); a `preBolus` test was added and it now
goes red.

#### Left to part 2

The first three items here are fixed by part 2 (commits `4b41bcf8`, `12c01268` and `a612a26f`); the last is
about a different branch.

- An entry POSTed with the hex `_id` of an entry stored as a string at the same time and type
  still answers 500, as on dev; the same POST without `_id` updates the entry.
- Websocket `dbAdd` still inserts `_id` as given (read).
- Route-level copies of the hex pattern (`lib/api/shared/objectid-validation.js`,
  `lib/server/websocket.js`, and the lower-case-only `ID_PATTERN` in `lib/api/entries/index.js`).
- `chore/nightscout-modernization` has this defect (reproduced, 11 of 13 red on Node 22.23.2 and
  24.20.0).

## Part 2: the same rules through API v1, API v3 and the websocket

### What changes for you

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

#### What was wrong

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

#### What this change does

- A reading sent again with its own ID updates the reading already saved at that time, and the app
  is told that reading's ID.
- An ID in capital letters finds and deletes the same reading as the same ID in small letters.
- Records added over the websocket with their own ID are saved in the normal form, and websocket
  edits and deletes find records whichever way their ID was saved.
- API v3 finds, changes and deletes those older records by the ID it lists them under.
- A device status report sent again is not saved twice. (Part 2 refused it with an error, which also lost the other reports sent with it; part 4 answers it as already saved and saves the rest.)

Nothing in your database changes until a record is written, edited or deleted.

**What you should do:** nothing, for most sites. If an app told you it had edited or deleted a
record but the record did not change, try the change again after upgrading. If you see two copies
of one record, see part 1: deleting either copy deletes both. If you are unsure which readings, treatments or
settings are correct, check with your care team.

---

### Technical detail

#### What the matrix found

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

#### What the commits do

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
5. **`44ac9047` API v3 and a non-hex `_id`.** `filterForOne` and `identifyingFilter` also
   match a non-hex **string** identifier against `_id`, with the same literal `$eq`; a non-string
   (operator-shaped) identifier gets no `_id` branch and is still compared literally.
   `lib/api3/swagger.yaml` line 1112 documents this addressing. `tests/api3.storage.modify.test.js`
   asserted the old exact filter for a non-hex identifier; its three assertions are updated to the
   new shape. `explain()` on `mongo:7`, all five v3 collections: OR of IXSCAN on `_id_` and
   `identifier_1` (plus the dedup-field index where used), one to three documents examined, no
   COLLSCAN.
6. **`18b09df7` stored `_id` in the entries POST response.** After the write, the stored `_id`
   of every reading that matched a stored one is read back in one `find` for the whole batch (an
   `$or` of the same `sysTime` + `type` filters), only when some reading matched, and set on the
   response, for a POST that carried another `_id` and for one that carried none (which answered
   `null`). Every item in a v1 POST response is expected to carry an `_id`
   (`docs/proposals/TEST-IMPLEMENTATION-SUMMARY.md` §6.1.2), and no existing test expected `null`.
   If the read-back fails, the POST still answers 200 with the readings stored.
7. **`ad973110` devicestatus re-send guard.** For a batch that carries 24-hex `_id`s, one
   `find({_id: {$in: <string forms>}}, {_id: 1})`; ids found keep their stored value, so a re-send
   collides and is refused as on dev and as a profile re-send is (part 4, `c3a34bac`, answers the
   re-send instead of refusing it). No read for a batch
   without 24-hex `_id`s. Measured cost (100-row batch, in-process create, `mongo:7`, 20,000 stored
   rows, 40 runs, two repeats): median 5.29 / 5.09 ms with hex `_id`s against 4.18 / 4.17 ms before
   the guard; without `_id`s 4.14 / 3.93 ms against 4.06 / 4.09 ms. About 1 ms per hex batch; the
   `find` alone is 0.67 ms median, a covered IXSCAN on `_id_`.
8. **`6d120fa2` helper header.** Comment only: a string `_id` stored in upper case is found
   when asked for in that spelling, not in lower case; the header's non-hex rules now include the
   websocket and API v3.

#### Tests

New: `tests/api.entries.repost-with-id.test.js` (18), `tests/api.entries.upper-case-id.test.js`
(5), `tests/websocket.object-id.test.js` (13), `tests/api.crud-by-id.matrix.test.js` (336),
`tests/api3.non-hex-id.test.js` (16), `tests/api.devicestatus.resend-guard.test.js` (8). Changed:
`tests/api3.storage.modify.test.js` (three filter-shape assertions, for the API v3 fix).

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

## Part 3: four fixes from review

### What changes for you

- An app that uses API v3, such as AndroidAPS, could delete or change a record that it had once saved a second copy of, and the delete would report success while the record stayed. It now deletes or changes the copy it shows.
- On the admin page, deleting an access entry (a "subject") that was restored from a backup, or created by a tool that set its own ID, reported success and left the entry, with its access, in place. It is now removed. This was also true on 15.0.8.

### Technical detail

| commit | what was wrong |
|---|---|
| `a2c7eb39` | Where a v1 record and the API v3 copy an earlier v3 PUT left beside it both exist, a v3 DELETE or PUT by that id wrote the v1 record while GET kept returning the v3 copy: the DELETE answered 200 and the record stayed, and a PUT left two records with the same `identifier`. v3 writes now find their target the way reads do (the document with `identifier` first, `findOne` sorted `{identifier: -1}`) and write that document by its `_id`. The v3 filter in `utils.js` is unchanged, so v3 still reaches string-`_id` records. |
| `1c2d1afd` | `find[_id][$in]` and `find[_id][$nin]` missed a record whose 24-hex `_id` is stored as a string, for reads and bulk deletes. Each hex in the list now names both forms. Also on 15.0.8. |
| `d2fd9ff6`, `ab7b22d6` | An auth subject or role created with its own 24-hex `_id` was stored with it as a string, and DELETE by that id answered 200 and removed nothing. Also on 15.0.8; admin only. Remove now matches either form, so entries already stored that way can be deleted. `d2fd9ff6` also made create store the ObjectId; since #8754 merged into `dev`, create keeps only a subject's owned fields and a client `_id` is not stored at all, so `ab7b22d6` drops that half and its test now checks that no string `_id` is stored. Tokens are unaffected: they are derived from `_id.toString()`, the same for either form. |
| `dd2cf8f1` | `idForms` read a 12-character string as an id, because the driver takes any 12 characters as raw bytes. It now throws for anything that is not an ObjectId or 24-hex; food, activity and profile remove match any other id exactly; `profile.save` gives such an id a new ObjectId. |

A delete by hex still removes both copies of a record an earlier edit left twice. That is intended (decided 2026-09-24), and the advice in part 1 now says so.

Each commit carries its own tests. At `dd2cf8f1`, with `lib/` reverted to `6d120fa2` and the new tests kept, 10 of them fail. At `ab7b22d6`, reverting remove to match the ObjectId form only fails the string-`_id` remove test.

## Part 4: fixes from the freeze review

### What changes for you

- A treatment or glucose reading sent without a usable ID is given one. One kind of badly formed
  record could stop a Nightscout site from running, and again after every restart; that can no
  longer happen, and a site that already holds such a record keeps running. This was also true on
  15.0.8.
- A device status report sent again is recognised as already saved, and the other reports sent
  with it are saved. Before this part, the whole upload answered with an error and the reports
  after the repeated one were lost.
- Deleting a record that is saved twice through an app that uses API v3, such as AndroidAPS,
  deletes both copies, so it no longer keeps showing. Where API v3 shows one copy, it is the one
  with the latest edit. The first half was also true on 15.0.8.

### Technical detail

| commit | what was wrong |
|---|---|
| `17add44b` | entries and treatments are written with upserts, which keep the `_id` they are given, so an `_id` that is empty or neither a string nor an ObjectId was stored as the record's `_id`; for one such value the next load of the in-memory data threw and the process ended, again after each restart. `object-id-forms.dropEmptyId` drops such an `_id` (an ObjectId from another copy of `bson` is kept, by `_bsontype`), called from `normalizeEntryId` and `normalizeTreatmentId`. `ddata`, `dataloader`, `calcdelta` and API v3 `normalizeDoc` accept a stored record without an id. Test: `tests/api.empty-id.test.js`. |
| `c3a34bac` | Part 2's re-send guard read the string forms only, so a re-send of a devicestatus stored with an ObjectId (every one this PR creates) collided, answered 500, and the ordered insert dropped every status after it in the POST. The read now asks for every form; a re-sent status is answered with the `_id` it is stored under and not written; the same new `_id` twice in a batch is stored once; the insert is unordered and accepts a duplicate key only for a status sent with its own `_id` (a retry that raced its first POST). **Changed expectations**: the resend-guard tests and the devicestatus re-send row of the matrix go from 500 to 200, marked in the files. This changes the 2026-09-23 decision below from "refused" to "acknowledged"; the guard still stores no second copy. Profile create still refuses a re-send (BF-99). |
| `63dd716c` | API v3 DELETE wrote one of the documents `filterForOne` matches, so of a record stored with a string `_id` and again with the ObjectId, one stayed valid; and reads and writes sorted by `identifier` only, which the two copies tie on, so which one they took depended on storage order (the string copy, in the review's trials; 15.0.8 took the ObjectId copy). DELETE now marks or removes every form (`updateMany`/`deleteMany`), and `findOne`, `findOneFilter` and `writeFilter` sort `{identifier: -1, _id: -1}`, which takes the ObjectId copy. **Changed expectations**: part 3's v1/v3 pair DELETE test now expects the v1 record marked deleted too, and two helper tests pin the new sort. Test: `tests/api3.delete-every-form.test.js`, which runs GET and PATCH with each copy stored first. |

| `cb7d4110` | From review of the three above. The every-form DELETE matched any document whose `_id` is the identifier, so it could also mark or remove a different record that has an identifier of its own; it now matches by `_id` only records without an identifier, as `identifyingFilter` does. And `dropEmptyId` dropped an Extended JSON `{"$oid": "<hex>"}` `_id`, as `mongoexport` writes it, so a restored record got a new id and a re-send stored a copy; it now becomes the ObjectId it names. Tests: two in `tests/api3.delete-every-form.test.js` (soft and permanent), and one unit and one HTTP test in `tests/api.empty-id.test.js`. |
| `6c3ccce6` | A treatments POST batch deleted the string forms of the ids it matched by `_id` once, after all its writes. An item without `_id` matched by `created_at` and `eventType` could land on such a string copy and was deleted with it, behind a 200. Each write matched by `_id` now removes its string forms right after it, so a later item finds the one record and replaces it, as it does when no string copy exists; upserted ids are mapped back to their items past the added deletes. Tests: three in `tests/api.object-id.treatments-entries.test.js`. |

Not changed here: API v3 PUT/PATCH edit one copy and websocket `dbUpdate` edits both, and each
leaves two records; websocket `dbAdd` and API v3 POST still store some unusable `_id` values
without a crash.

Each fix reverted singly fails a named test: either normalizer's call, the `ddata` or `calcdelta`
guard, the unordered insert, soft and permanent DELETE, the read sort (only with the ObjectId copy
stored first), the write sort, the Extended JSON read, the narrowed DELETE filter, and the
treatments batch's per-write delete and its index map.

## Merges

The eight 15.0.9 PRs this was first checked against (#8748, #8749, #8751, #8753, #8754, #8755, #8756, #8757) have all merged into `dev`, and `dev` `4f705217` is merged into this branch (`572bfc32`, no conflicts). CI on `572bfc32` failed one test, the part 3 subject-create test, which `dev`'s change to create made wrong; `ab7b22d6` fixes it.

The narrower profile-only fix that this replaces is not being opened.

## Tests, re-run for this description

At `63dd716c` the full suite (CI's `test-ci`, then `test:core`), Node 20.20.0, 22.23.2 and 24.20.0 × MongoDB 4.4.24 and 7.0.43, each version read from the server: 3090 passing, 0 failing, 3 pending, and 286 core, in all six. At `cb7d4110`, the same six cells: 3094 passing, 0 failing, 3 pending, and 286 core, in all six (four more than `63dd716c`, all from that commit). At `6c3ccce6` the full suite is being run.
At `ab7b22d6` (this branch with `dev` `4f705217` merged), Node 22.23.2, MongoDB 7: 3066 passing, 0 failing, 3 pending. At `dd2cf8f1`, before the merge: 2875 passing, 0 failing, 3 pending.
At `6d120fa2` (parts 1 and 2), Node 20.20.0: 2866 passing (`dev` `1f9a9d10` was 2386); of the 480 tests in the eleven new files, 259 fail with `dev`'s `lib/`, and the other 221 are invariants that pass on both.
MongoDB needs a raised open-file limit for this suite (peak 1130 open files in `mongod` at `6d120fa2`); a container at Docker's default 1024 stops partway through.

## Decisions taken (maintainer)

2026-09-25: fix the three freeze-review findings in this PR (part 4), including answering a device
status re-send instead of refusing it.

2026-09-23: add the device status re-send guard (commit 7 of part 2); take the API v3 fix (commit 5); answer with the stored
`_id` (commit 6); leave the upper-case string `_id` limit as it is, and state it in the helper (commit 8).

