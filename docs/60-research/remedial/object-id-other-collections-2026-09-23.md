# A 24-hex `_id` stored as a string: devicestatus, food, activity, treatments, entries and API v3

*Contributor-facing. Snapshot, 2026-09-23. Superseded for the fix: BF-99 to BF-102 are fixed together
by PR #8758 (`bf/object-id-crud`, open); the continuation is
[crud-by-id-matrix](crud-by-id-matrix-2026-09-23.md), and item state is in `queue/work-queue.yaml`
(`BFQ-102`). The measurements stand. Measured 2026-09-23 against `origin/dev` `1f9a9d10` (15.0.9), the release
tag `15.0.6` `9cd304f7`, and `chore/nightscout-modernization` `b1bdaca0`. Storage: `mongo:7` in
Docker. Node 20.20.0 and 22.23.2 via `n exec` (15.0.6 on Node 16.20.2; modernization on 22.23.2
and 24.20.0). Synthetic records only. Every row marked "reproduced" or "measured" was run; rows
marked "read" were not.*

Continues [`profile-object-id-2026-09-23.md`](profile-object-id-2026-09-23.md) (BF-99), §4 of
which found BF-100 and BF-101. Register:
[`nightscout-backfix-register.md`](../../30-design/remedial/nightscout-backfix-register.md)
BF-99, BF-100, BF-101.

## Branches

All local, not pushed, each on `origin/dev` `1f9a9d10`.

| branch | tip | commits | what it is |
|---|---|---:|---|
| `bf/object-id-consistency` | `597e2899` | 5 | the whole through-line: helper, profile (BF-99), devicestatus/food/activity (BF-100), treatments/entries, API v3 (BF-101) |
| `bf/object-id-other-collections` | `2fac53f5` | 2 | helper + BF-100 only (the same two commits as consistency's a and c) |
| `bf/api3-string-id` | `7295bc8c` | 2 | helper + BF-101 only (the same two commits as consistency's a and e) |

The two narrow branches exist so BF-100 or BF-101 can land without the rest. Their commits
have the same content as the matching commits on `bf/object-id-consistency`.

`bf/object-id-consistency`, in order:

| | commit | subject (abridged) |
|---|---|---|
| a | `1f9db1fe` | one helper, `lib/server/object-id-forms.js`, plus `tests/object-id-forms.test.js` |
| b | `09566345` | profile: BF-99's fix (`9b8cc2f9`) expressed on the helper; BF-99's test file unchanged |
| c | `80993afc` | devicestatus, food, activity (BF-100) |
| d | `5581c5e4` | treatments and entries stored by 15.0.6 or earlier |
| e | `597e2899` | API v3 `filterForOne` / `identifyingFilter` (BF-101) |

PR body drafts:
[`bf-object-id-consistency.md`](../../../reports/phase0-pr-bodies/bf-object-id-consistency.md),
[`bf-object-id-other-collections.md`](../../../reports/phase0-pr-bodies/bf-object-id-other-collections.md),
[`bf-api3-string-id.md`](../../../reports/phase0-pr-bodies/bf-api3-string-id.md).

## 1. Which sites hold string-`_id` records

| collection | stores a POSTed 24-hex `_id` as | source |
|---|---|---|
| profile | string, every release to dev | BF-99, reproduced |
| devicestatus, food, activity | string, every release to dev | reproduced on dev (§2); 15.0.8 in the BF-99 evidence |
| treatments, entries | **string up to 15.0.6**, ObjectId from 15.0.7 | reproduced on 15.0.6 (below); the conversion (`normalizeTreatmentId` / `normalizeEntryId`, REQ-SYNC-072) first appears in 15.0.7 (read, `git log -S`) |

15.0.6, POST through v1 with a 24-hex `_id`, then the stored type read from MongoDB:

| POST | status | stored `_id` |
|---|---:|---|
| `/api/treatments/` | 200 | string |
| `/api/entries/` | 200 | string |

The same probe on dev stores ObjectId for both. So a site that ran 15.0.6 or earlier and
received treatments or entries with their own hex `_id` may hold string-`_id` records in those
collections today. Which clients sent a hex `_id` to those routes before 15.0.7 was not
established.

## 2. What dev does with a string-`_id` record

Records inserted directly into MongoDB with a string `_id`, as an upgraded site holds them, then
driven through the API on `origin/dev` `1f9a9d10`. All reproduced.

| collection | find[_id]=hex | GET by id | PUT / edit | DELETE by id | POST re-sending the id |
|---|---|---|---|---|---|
| devicestatus | [] | — | (no route) | nothing deleted | 500 (duplicate key); with the fix 200 and an ObjectId copy, see §4 |
| food | (no find) | — | ObjectId copy added | nothing deleted | replaced in place |
| activity | [] | — | ObjectId copy added | nothing deleted | replaced in place |
| treatments | [] | — | ObjectId copy added | `deletedCount: 0` | ObjectId copy added |
| entries | [] | 500 "No such id" | (no route) | `deletedCount: 0` | 500, see below |
| API v3 (profile, food) | — | 404 | 201, second record | 404, nothing deleted | 201, second record |

A record POSTed to devicestatus, food or activity with a hex `_id` on dev is stored as a string
and then shows the same row (reproduced: stored type string; find 0; DELETE leaves it; food and
activity PUT leave two).

**Entries re-POST, not changed by these branches:** an entry POSTed with the hex `_id` of an entry
stored as a string at the same `sysTime` and `type` answers 500 on dev and on
`bf/object-id-consistency` alike, because the upsert matches that entry by time and type and
cannot change its `_id`. The same POST without `_id` answers 200 and updates the entry
(measured on both trees). A CGM uploader re-sending a reading with its own hex `_id` to a site
upgraded from 15.0.6 would see this; which uploaders do was not established.

## 3. The rule and where it lives

`lib/server/object-id-forms.js` (commit a) holds the rule for a 24-hex `_id`:

| function | used for |
|---|---|
| `isHexId`, `OBJECT_ID_HEX_RE` | the 24-hex test (also now used by `lib/server/query.js`, treatments, entries, profile, API v3 utils) |
| `toStoredId` | create: a 24-hex string is stored as the ObjectId it names |
| `idForms` | `[ObjectId, lower-case hex, the string as given]`, for matching either stored form |
| `matchEitherForm` | widens `find[_id]`'s ObjectId equality from `query.js` to `$in` of those forms |
| `staleStringForms`, `withStaleStringsRemoved` | after an upsert by the ObjectId, delete the string form of the same id |

**The non-hex rule is not unified, on purpose.** What happens to a string `_id` that is not 24-hex
stays with each collection and is documented in the helper's header:

| collection | non-hex string `_id` (for example a UUID) |
|---|---|
| treatments, entries (REQ-SYNC-072) | dropped from `_id` so the server makes one; moved to `identifier` when `UUID_HANDLING` is on |
| profile, devicestatus, food, activity | refused with 400 by the v1 route (`lib/api/shared/objectid-validation.js`); an in-process storage call keeps it as given |
| API v3 | records are addressed by `identifier`; a 24-hex identifier also matches `_id` |

Copies of the 24-hex pattern not moved to the helper (read): `lib/api/shared/objectid-validation.js`
(route validation), `lib/server/websocket.js` `safeObjectID`, and `lib/api/entries/index.js`
`ID_PATTERN`, which is **lower-case only**, so `GET /api/v1/entries/<UPPER-CASE HEX>` is treated
as a model name, not an id. Left as they are to keep the change to storage.

## 4. Per-collection decisions

**profile (commit b).** BF-99's fix, re-expressed: the create guard (a POST re-sending an id already
stored as a string keeps the string so the insert collides, as before) is kept exactly.
`tests/api.profiles.object-id.test.js` is byte-identical to `9b8cc2f9`'s and passes 13/13.

**devicestatus (commit c): conversion on create, no create guard.** A create guard would add an
indexed read to every create carrying its own `_id`, which is every batch a Nightscout-to-Nightscout
connector writes. Without it, a twin can arise in one way: a devicestatus whose first copy was
stored with the string `_id` (before this change) is POSTed again with the same `_id`. On dev
that re-send is refused with a duplicate-key error; with the change it is stored as an ObjectId
beside the string copy. Measured through `POST /api/v1/devicestatus/`: dev answers 500 and keeps
one string copy; `bf/object-id-consistency` answers 200 and stores `["string","ObjectId"]`. The
same by calling `ctx.devicestatus.create` directly. Both copies are then returned by `find[_id]` and removed by
DELETE by id.

Does the connector re-send? Measured with the connector's in-process output
(`externals/work/nc-profile-dup` `f924de2`, `lib/outputs/internal.js`; its devicestatus code is
the same as `0.1.0-dev.2`, which dev installs) against a sink on `bf/object-id-consistency`
holding two string-`_id` devicestatus rows, the newer at the watermark. The batch re-sent both
(the boundary row with its `created_at` written with a `+00:00` offset) plus one new row:

| row | stored after the batch |
|---|---|
| older, re-sent | string only |
| at the watermark, re-sent | string only |
| new | ObjectId |

No error. The output drops every devicestatus whose `created_at` is not strictly after
(`Date.parse(r.created_at) > latest`) the newest stored devicestatus, so a row at the boundary
is not re-sent. A twin through the connector would need that comparison to be `>=`, or the
sink's newest stored `created_at` to move backwards (for example the newest rows deleted while
older string-`_id` rows remain, read). If a re-send is ever found, the guard to add is BF-99's:
before `insertMany`, one `find({_id: {$in: <hex ids>}}, {_id: 1})` and keep the string form for
ids already stored as strings, run only for batches that carry hex `_id`s. The released
connector `v0.0.13` (on 15.0.8) has no such filter (read); 15.0.9 installs `0.1.0-dev.2`.

**food, activity (commit c): conversion on create, and no BF-99-style guard; a string-copy delete
instead.** Their `create` is already an upsert by `_id` (`replaceOne(..., {upsert: true})`), so a
re-POST replaces the record on dev rather than being refused. BF-99's guard exists to keep
profile's refusal; here it would keep the string form forever. Instead create, like PUT, upserts
the ObjectId and then deletes the string form of the same id in the same `bulkWrite`, so a re-POST
ends with one ObjectId record holding the new content, as dev ends with one record. No extra
read.

**treatments (commit d).** Writes that match their record by `_id` (PUT, and POST of a record
without `identifier`, both the batch path and the one-record-at-a-time path taken when a batch
has a `preBolus`) delete the string form after the upsert. The UUID path is untouched: the
REQ-SYNC-072, GAP-SYNC-045 and GAP-TREAT-012 test files pass unmodified.

**entries (commit d).** `find[_id]`, DELETE and `GET /entries/<hex>` match both forms. Create is
unchanged apart from using the helper (the 500 in §2 remains).

**API v3 (commit e).** The hex fallback in both filters adds one `$or` branch per form, each a
literal `$eq`, rather than one `$in`: the existing selector-hardening tests
(`tests/api3.storage.utils.test.js`) assert the `$eq` shape of the ObjectId branch and pass
unmodified.

## 5. API v3 query plans

`explain('executionStats')` on `mongo:7`, 5,001 documents per collection (one with a string
`_id`), with the indexes Nightscout creates at boot plus API v3's `identifier` index. Winning
plan, flattened:

| filter | dev | `bf/object-id-consistency` |
|---|---|---|
| `filterForOne(hex)` | `SUBPLAN > FETCH > OR > IXSCAN(_id_), IXSCAN(identifier_1)`; 0 returned | same plan; 1 returned, 1 document and 2 keys examined |
| `identifyingFilter(hex)` | `SUBPLAN > FETCH > OR > FETCH > IXSCAN(_id_), IXSCAN(identifier_1)`; 0 returned | `SUBPLAN > FETCH > OR > FETCH > IXSCAN(_id_), FETCH > IXSCAN(_id_), IXSCAN(identifier_1)`; 1 returned, 2 documents examined |
| v1 `{_id: {$in: [ObjectId, hex]}}` | `FETCH > IXSCAN(_id_)`, 1 document, 2 keys | same |

Identical for profile, food, treatments, entries and devicestatus. No COLLSCAN on either tree.
Each `$or` branch needs an index for this plan; `identifier` has one on every v3 collection
because API v3 creates it.

## 6. `chore/nightscout-modernization` and BF-99

`tests/api.profiles.object-id.test.js` from `9b8cc2f9`, unchanged, on a detached worktree of
`b1bdaca0` after `npm ci`:

| Node | passing | failing |
|---|---:|---:|
| 22.23.2 | 2 | 11 |
| 24.20.0 | 2 | 11 |
| 20.20.0 | — | — (modernization refuses to start on Node 20: engines `^22.23.2 \|\| ^24.20.0`) |

The same 11 assertions as dev and 15.0.8. BF-99 is **reproduced** on modernization (the register
row said read-derived).

## 7. Tests, suites and break-its

New test files: `tests/object-id-forms.test.js` (15, no database),
`tests/api.object-id.other-collections.test.js` (31), `tests/api.object-id.treatments-entries.test.js`
(15), `tests/api3.string-id.test.js` (10), plus BF-99's `tests/api.profiles.object-id.test.js` (13).

Red on unmodified dev `1f9a9d10`:

| file | passing | failing | the passing ones |
|---|---:|---:|---|
| other-collections | 4 | 27 | POST without `_id` (×3); food and activity re-POST replaces in place |
| treatments-entries | 2 | 13 | a new treatment / entry with a hex `_id` is stored as ObjectId |
| api3.string-id | 1 | 9 | a record with an ObjectId `_id` is found |

Full suite (`mocha --timeout 5000 --require ./tests/hooks.js --exit ./tests/*.test.js`), passing /
failing / pending:

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

Break-its, each with one part of the fix removed (Node 20.20.0, the commit's own test file):

| commit | removed | red |
|---|---|---:|
| a | case-insensitive hex pattern | 3 |
| a | `toStoredId` conversion | 1 |
| a | the as-given string in `idForms` | 3 |
| a | caller's spelling in `matchEitherForm` | 1 |
| a | hex/ObjectId filter in `staleStringForms` | 2 (throws) |
| a | the empty check in `withStaleStringsRemoved` (`> 1`) | 1 |
| b | create conversion / save's string delete / find / remove / create guard | 2 / 3 / 2 / 2 / 1 (same as BF-99's own) |
| c | devicestatus create conversion / devicestatus find (also DELETE) | 2 / 4 |
| c | food create conversion / create string delete / PUT string delete / remove | 2 / 1 / 3 / 2 |
| c | activity create conversion / create string delete / PUT string delete / find / remove | 1 / 1 / 3 / 2 / 2 |
| d | treatments find (also DELETE) / batch-POST string delete / one-at-a-time POST string delete / PUT string delete / hex conversion | 5 / 2 / 1 / 3 / 6 |
| d | entries `getEntry` / find (also DELETE) / hex conversion | 1 / 3 / 1 |
| e | `filterForOne` string branches / `identifyingFilter` string branches / the as-given (upper-case) branch | 9 / 4 / 1 |

The first attempt at d's one-at-a-time break-it went **green**: no test reached `upsert()`,
because the v1 route always hands `create()` an array and only a batch containing a `preBolus`
takes that path. A test with a `preBolus` was added to d (on dev it is red too, 13 of 15 red);
the break then went red. Two food/activity create-conversion break-its first also removed the
stale-delete input and went red for that reason; they were rerun with only the conversion
removed.

## 8. Merges

`git merge-tree --write-tree`, each branch tip against each open 15.0.9 head:

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

## 9. Not changed

- Websocket `dbAdd` inserts `_id` as given for every collection (read, BF-99 §4.2).
- The entries re-POST 500 in §2.
- A devicestatus re-sent with the `_id` of a string copy is stored beside it (§4).
- Route-level copies of the hex pattern (§3).
- No boot migration: string-`_id` records stay strings until they are edited or deleted.
