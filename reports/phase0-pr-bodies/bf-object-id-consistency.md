# `bf/object-id-consistency`: a record's own `_id` finds, edits and deletes it, in every collection and in API v3

**DRAFT. Local branch, not pushed.** Branch `bf/object-id-consistency` on `origin/dev` `1f9a9d10`,
tip `597e2899`, five commits. No `CHANGELOG.md` edit. Supersedes `bf/profile-object-id`
`9b8cc2f9` (its commit b carries that fix and its test file unchanged); the two conflict in
`lib/server/profile.js`, so land one. Evidence:
[`docs/60-research/remedial/object-id-other-collections-2026-09-23.md`](../../docs/60-research/remedial/object-id-other-collections-2026-09-23.md)
and [`profile-object-id-2026-09-23.md`](../../docs/60-research/remedial/profile-object-id-2026-09-23.md).
Register: BF-99, BF-100, BF-101.

| what changes | who can see it |
|---|---|
| a profile, devicestatus, food or activity record POSTed with a 24-hex `_id` is stored with an ObjectId `_id`, not a string | sites fed by the Nightscout connector's Nightscout source, anyone restoring an export, and clients that send their own `_id` |
| editing such a record, or one already stored with a string `_id`, replaces it, leaving one record, instead of adding a second one | the same sites, through the profile editor, food editor and API clients |
| `find[_id]`, `GET /entries/<id>` and DELETE by id work whichever form the `_id` is stored in, for profile, devicestatus, food, activity, treatments and entries | the same sites, and sites upgraded from 15.0.6 or earlier (treatments and entries) |
| API v3 reads, replaces and deletes a v1 record stored with a string `_id`, and a v3 write for the same id updates it instead of adding a second record | API v3 clients on those sites |
| a POST without `_id`, the non-hex `_id` handling of every collection (UUID → `identifier` for treatments and entries; 400 elsewhere), and a re-sent profile POST (still refused) are unchanged | nobody; stated so a reviewer does not have to infer it |

---

## What changes for you

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

### What was wrong

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

### What this change does

- Records that arrive with their own ID are saved in the normal form from now on.
- Records **already saved** the old way are found, and are fixed the first time they are edited:
  the edit replaces the old copy and you are left with **one** record. Nothing in your database
  changes until a record is edited or deleted.
- Deleting such a record now removes it, including a copy left by an earlier edit.

**What you should do:** nothing, for most sites. If your site receives data from another
Nightscout site through the connector, or you have restored data from an export, or your site
has been running since 15.0.6 or earlier, and you have edited a profile or treatment there, look
at it after upgrading. If you see an old copy beside the one you edited, you can now delete it.
If you are unsure which settings or entries are correct, check with your care team.

---

## Technical detail

### The defect

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

Profiles as in BF-99.

### What the commits do

1. **`1f9db1fe` helper.** `lib/server/object-id-forms.js`: `isHexId`, `toStoredId` (24-hex string
   → ObjectId), `idForms` (`[ObjectId, lower-case hex, as given]`), `matchEitherForm` (widens
   `query.js`'s ObjectId equality to `$in` of those), `staleStringForms` /
   `withStaleStringsRemoved` (after an upsert by the ObjectId, delete the string form of the same
   id). The header documents that the non-hex rule differs by collection and is not unified.
   Unit tests without a database.
2. **`09566345` profile.** BF-99's fix on the helper: conversion on create, with the create guard
   that keeps a re-sent id already stored as a string colliding as before; PUT deletes the string
   form after the upsert; DELETE and `find[_id]` match both. `tests/api.profiles.object-id.test.js`
   is `9b8cc2f9`'s, unchanged.
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

### Tests

New: `tests/object-id-forms.test.js` (15), `tests/api.profiles.object-id.test.js` (13, from
BF-99), `tests/api.object-id.other-collections.test.js` (31),
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

### Merges

| head | `bf/object-id-consistency` `597e2899` | `bf/object-id-other-collections` `2fac53f5` | `bf/api3-string-id` `7295bc8c` |
|---|---|---|---|
| #8748 `d19043b2` | clean | clean | clean |
| #8749 `46b20b38` | clean | clean | clean |
| #8751 `b5038500` | clean | clean | clean |
| #8753 `e6a50e9a` | clean | clean | clean |
| #8754 `0a74ef4e` | clean | clean | clean |
| #8755 `92544d8f` | clean | clean | clean |
| #8756 `83cfff14` | clean | clean | clean |
| `rc/15.0.9-additions-e` `1b1977e0` | clean | clean | clean |
| `bf/profile-object-id` `9b8cc2f9` | **conflict**, `lib/server/profile.js` (consistency carries the same fix on the helper; land one) | clean | clean |
| `bf/object-id-other-collections` `2fac53f5` | clean | — | clean |
| `bf/api3-string-id` `7295bc8c` | clean | clean | — |

The two narrow branches both add `lib/server/object-id-forms.js` with identical content, so they
merge with each other and with `bf/object-id-consistency`. An earlier build of
`bf/object-id-other-collections` (`386fd92e`) had its own copy of the helper and conflicted
add/add with `bf/api3-string-id`; it was rebuilt from commits a and c. The merged trees were not
run through the suite.

### Not in this branch

- An entry POSTed with the hex `_id` of an entry stored as a string at the same time and type
  still answers 500, as on dev; the same POST without `_id` updates the entry.
- Websocket `dbAdd` still inserts `_id` as given (read).
- Route-level copies of the hex pattern (`lib/api/shared/objectid-validation.js`,
  `lib/server/websocket.js`, and the lower-case-only `ID_PATTERN` in `lib/api/entries/index.js`).
- `chore/nightscout-modernization` has BF-99 (reproduced, 11 of 13 red on Node 22.23.2 and
  24.20.0).
