# `bf/api3-string-id`: API v3 finds a v1 record stored with a string `_id`

**DRAFT. Local branch, not pushed.** Branch `bf/api3-string-id` on `origin/dev` `1f9a9d10`, tip
`7295bc8c`, two commits: the helper `lib/server/object-id-forms.js` and the BF-101 fix. The same
two commits, with the same content, are commits a and e of `bf/object-id-consistency`; land this
branch only if BF-101 is wanted without the rest. No `CHANGELOG.md` edit. Evidence:
[`docs/60-research/remedial/object-id-other-collections-2026-09-23.md`](../../docs/60-research/remedial/object-id-other-collections-2026-09-23.md).
Register: BF-101.

| what changes | who can see it |
|---|---|
| `GET`, `PUT`, `PATCH` and `DELETE /api/v3/<collection>/<24-hex id>` find a record stored through v1 with that id as a string `_id` | API v3 clients on sites holding such records (profiles, devicestatus, food, activity from any release; treatments and entries from 15.0.6 or earlier) |
| a v3 `POST` or `PUT` for that id updates the record instead of storing a second one | the same clients |
| records with an ObjectId `_id` or an `identifier` are found exactly as before | nobody |

---

## What changes for you

*Plain-language summary for people running their own Nightscout site. Nightscout is not a medical
device and none of this is medical advice.*

**API v3** is a newer way for apps to read and write Nightscout data. Some records saved through
the older API were stored with their **ID** (the label Nightscout uses to find a record) in a
different form. Apps using API v3 could not open, change or delete those records by their ID,
and sending one of them again through API v3 stored a **second copy**. With this change API v3
finds them in either form and updates them in place. Nothing in your database changes until an
app writes to one of those records.

**What you should do:** nothing.

---

## Technical detail

`lib/api3/storage/mongoCollection/utils.js`: the "identifier = `_id`" fallback in `filterForOne`
(GET, PUT's replace, PATCH, DELETE) and `identifyingFilter` (the existence check behind POST, PUT
and PATCH) matched `{_id: {$eq: ObjectId(identifier)}}` only. It now adds one `$or` branch per
form from `idForms` (ObjectId, lower-case hex, the identifier as given), each a literal `$eq`, so
the existing selector-hardening tests (`tests/api3.storage.utils.test.js`, which assert the `$eq`
shape) pass unmodified.

Measured on dev with a record inserted into MongoDB with a string `_id`: GET 404, DELETE 404,
PUT 201 and a second record, POST with that `identifier` 201 and a second record (profile and
food).

### Query plans

`explain('executionStats')` on `mongo:7`, 5,001 documents per collection, the boot indexes plus
v3's `identifier` index. On this branch, for profile, food, treatments, entries and devicestatus:

- `filterForOne(hex)`: `SUBPLAN > FETCH > OR > [IXSCAN _id_, IXSCAN identifier_1]`, 1 document
  and 2 keys examined, 1 returned.
- `identifyingFilter(hex)`: `SUBPLAN > FETCH > OR > [FETCH > IXSCAN _id_, FETCH > IXSCAN _id_,
  IXSCAN identifier_1]`, 2 documents examined, 1 returned.

No COLLSCAN; dev's plans are the same shape and return 0.

### Tests

`tests/object-id-forms.test.js` (15, no database) and `tests/api3.string-id.test.js` (10, through
the v3 routes, profile and food: GET, PUT, permanent DELETE, POST dedup, an upper-case string
`_id`, and an ObjectId control). Red on dev: 9 of 10.

Full suite, `mongo:7`, passing / failing / pending:

| tree | Node 20.20.0 | Node 22.23.2 |
|---|---|---|
| `origin/dev` `1f9a9d10` | 2386 / 0 / 3 | 2386 / 0 / 3 |
| this branch `7295bc8c` | 2411 / 0 / 3 | 2411 / 0 / 3 |

+25, exactly the two new files. No existing test changed.

Break-its (Node 20.20.0): `filterForOne` string branches removed 9 red; `identifyingFilter`
string branches removed 4 red (PUT and POST, both collections); the as-given branch removed 1
red (upper case).

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
