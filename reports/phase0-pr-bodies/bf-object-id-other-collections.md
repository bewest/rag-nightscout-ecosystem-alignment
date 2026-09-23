# `bf/object-id-other-collections`: devicestatus, food and activity records posted with their own `_id` can be found, edited and deleted by it

**DRAFT. Local branch, not pushed.** Branch `bf/object-id-other-collections` on `origin/dev`
`1f9a9d10`, tip `2fac53f5`, two commits: the helper `lib/server/object-id-forms.js` and the
BF-100 fix. The same two commits, with the same content, are commits a and c of
`bf/object-id-consistency`; land this branch only if BF-100 is wanted without the rest. No
`CHANGELOG.md` edit. Evidence:
[`docs/60-research/remedial/object-id-other-collections-2026-09-23.md`](../../docs/60-research/remedial/object-id-other-collections-2026-09-23.md).
Register: BF-100.

| what changes | who can see it |
|---|---|
| a devicestatus, food or activity record POSTed with a 24-hex `_id` is stored with an ObjectId `_id`, not a string | sites fed by the Nightscout connector's Nightscout source (devicestatus), anyone restoring an export, clients that send their own `_id` |
| a food or activity PUT, or POST, of a record stored with a string `_id` replaces it, leaving one record | the same sites |
| `find[_id]` (devicestatus, activity) and DELETE by id (all three) work whichever form the `_id` is stored in | the same sites |
| a devicestatus re-sent with the `_id` of a copy stored as a string is stored beside it (dev refuses it with 500) | clients that re-send devicestatus with the same `_id`; not the connector's in-process output, which does not re-send (measured) |
| a POST without `_id`, and a non-hex `_id` (still 400), are unchanged | nobody |

---

## What changes for you

*Plain-language summary for people running their own Nightscout site. Nightscout is not a medical
device and none of this is medical advice.*

- **Device status**: the reports your phone, pump or looping app sends, such as battery level
  and loop results. **Food**: entries in your food list. **Activity**: step and heart-rate
  records. **ID**: the label Nightscout gives each saved record so it can find it again.

**What was wrong.** When one of these records arrived with its own ID, for example copied from
another Nightscout site by the connector or restored from an export, Nightscout saved the ID in
a different form from the one it looks records up by. It could show the record but could not
find it again by that ID: deleting it by ID did nothing, and editing a food or activity record
saved a second copy and kept the old one.

**What this change does.** New records are saved in the normal form. Records already saved the
old way are found, are replaced (not copied) the next time they are edited, and can be deleted.
Nothing in your database changes until a record is edited or deleted.

**What you should do:** nothing, for most sites. If you edited a food on a site that received
foods from an export or another site, look at your food list after upgrading and delete any old
copy.

---

## Technical detail

See commit c of [`bf-object-id-consistency.md`](bf-object-id-consistency.md) and the evidence
file §2 and §4. In short: conversion on create through `toStoredId`; `matchEitherForm` in
devicestatus and activity `query_for`; `deleteMany` over `idForms` in food and activity
`remove`; food and activity `create` and `save` append a `deleteMany` of the string forms after
the upserts in the same `bulkWrite` (activity `save` issues it after its `replaceOne`).

**devicestatus has no create guard.** BF-99's guard (keep the string form if that string is
already stored, so the insert collides as before) would cost one indexed read per create that
carries its own `_id`, which is every connector batch. The connector's in-process output
(`0.1.0-dev.2`, which dev installs, and `nc-profile-dup` `f924de2`) drops every devicestatus
whose `created_at` is not strictly after the newest one stored, so it does not re-send: measured
with a sink holding two string-`_id` rows, the newer at the watermark, and a batch re-sending
both plus a new row, both stayed single string copies. If a re-send path is found, the guard to
add is BF-99's, limited to batches with hex `_id`s.

**food and activity have no BF-99-style guard.** Their `create` is an upsert by `_id`, so dev
replaces a re-POSTed record in place; keeping the string (BF-99's guard) would keep the old form
forever. The string-form delete after the upsert gives the same "one record, new content" with
no extra read.

### Tests

`tests/object-id-forms.test.js` (15, no database) and
`tests/api.object-id.other-collections.test.js` (31). The second is red on dev: 27 of 31; the
4 passing are three POST-without-`_id` controls and the food/activity re-POST that dev already
replaces in place (it guards the string-form delete, see break-its).

Full suite, `mongo:7`, passing / failing / pending:

| tree | Node 20.20.0 | Node 22.23.2 |
|---|---|---|
| `origin/dev` `1f9a9d10` | 2386 / 0 / 3 | 2386 / 0 / 3 |
| this branch `2fac53f5` | 2432 / 0 / 3 | 2432 / 0 / 3 |

+46, exactly the two new files. No existing test changed.

Break-its (one hunk removed, Node 20.20.0): devicestatus create conversion 2 red, devicestatus
find 4; food create conversion 2, create string delete 1, PUT string delete 3, remove 2;
activity create conversion 1, create string delete 1, PUT string delete 3, find 2, remove 2.

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
