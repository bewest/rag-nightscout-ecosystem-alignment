# Record identity in cgm-remote-monitor: `_id`, `identifier` and time keys

*Contributor-facing. Living reference, **as of 2026-10-18**. Pinned to cgm-remote-monitor
**15.0.8** (`92d08342`, the shipping release) and **dev** (`fade2299`, the 15.0.9 candidate).
Queue item `DOCS-RECORD-IDENTITY`. It describes what the code does today; it proposes nothing.*

Every claim is marked **[M]** measured or **[R]** read. Measured claims come from
[`tools/lab/record-identity`](../../tools/lab/record-identity/README.md)
([results 2026-10-18](../../tools/lab/record-identity/results/record-identity-2026-10-18.md):
both refs, MongoDB 7.0.43, `UUID_HANDLING` at its default) and, where cited, from
[`tools/lab/v3-identifier-immutable`](../../tools/lab/v3-identifier-immutable/results/v3-identifier-immutable-2026-10-17.md).
Read claims cite `lib/` paths at the ref named. When this page and the code disagree, the code
wins; re-run the lab before quoting a cell for a newer ref.

## Summary

A Nightscout record has two ids. **`_id`** is MongoDB's storage key; the server serves it as 24
hex characters and, on v1, a client may send its own 24-hex value. **`identifier`** is the
client's sync identity: API v3 matches on it everywhere, v1 matches on it **only for
treatments**, and the socket does not match on it at all. When neither is sent, each path falls
back to a time key (entries `sysTime` + `type`, treatments `created_at` + `eventType`), and
devicestatus has none, so every POST adds a record. The paths disagree in the details that
matter to an uploader: whether a 24-hex `_id` is stored as an ObjectId or as a string (15.0.8:
ObjectId on v1 entries and treatments, string on v1 devicestatus, profile and food, on the
socket and on API v3; dev: ObjectId everywhere except API v3), whether `_id` or `identifier` wins
when both are sent (v1 treatments: `identifier`, and the sent `_id` is dropped), and whether the
reply names the stored `_id` (not after a v1 treatments time-key match, on either ref). dev
removes most of 15.0.8's `_id` failures (#8758): a re-sent devicestatus no longer fails its
batch, an entry re-sent under another `_id` no longer fails, and string-stored ids are found by
every v1 and socket lookup.

| collection | path | a client's `_id` | match key on write, in order | the reply's `_id` | 15.0.8 vs dev |
|---|---|---|---|---|---|
| entries | v1 POST (one object or an array; one ordered `bulkWrite`) | 24-hex → ObjectId [M]; any other string → `identifier` (if none) and dropped, server assigns [M] | `sysTime` + `type` only; `_id` and `identifier` are not match keys [M] | inserted: the new `_id`; matched: 15.0.8 none [M], dev the stored `_id` [M] | another `_id` at a stored time: 15.0.8 **500** "immutable field `_id`", dev 200 and keeps the stored `_id` [M] |
| entries | v1 GET `/entries/<hex>`, `find[_id]`, `find[identifier]`; DELETE `/entries/<hex>` | hex → ObjectId; UUID → `identifier` or `_id` under `UUID_HANDLING` [R] | — | — | dev also matches a hex stored as a string [R]; DELETE is a hard delete on both [M] |
| entries | v3 POST / PUT / PATCH / GET / DELETE `{identifier}` | a body `_id` is stored as sent: 24-hex as a **string** [M treatments, R entries] | `identifier`; then `date` + `type` against a record with no `identifier` [R] | `identifier`, never `_id` [M] | same on both [R], except that dev accepts a v1 record's first `device` at the same time [M treatments] |
| entries | socket `dbAdd` / `dbUpdate` / `dbRemove` | stored as sent on 15.0.8 (24-hex as a string) [M]; dev stores 24-hex as ObjectId [M] | none: every `dbAdd` inserts [M] | the inserted document; `[]` on a duplicate `_id` [M] | update/remove by `_id` only |
| treatments | v1 POST (always an array; `preBolus` items one by one) | 24-hex → ObjectId [M]; other string → `identifier` (if none), dropped [M]; **dropped when `identifier` is also sent** [M] | `identifier` (or a UUID-shaped legacy `_id` equal to it); else `_id`; else `created_at` + `eventType` [M]; dev adds client ids and amounts to the last (BF-121) [M] | inserted: new `_id`; `identifier` match: stored `_id` [M]; time-key match: **none** on both [M] | same carbs at one time + `eventType`, other amount: 15.0.8 overwrites, dev keeps both [M] |
| treatments | v1 PUT | as POST [R] | as POST [M] | stored `_id` [M] | dev removes a string twin of the matched hex `_id` [R] |
| treatments | v1 GET `find[_id]`, `find[identifier]` | hex → ObjectId; UUID → `identifier` or `_id`, compared exactly (case kept) [M] | — | — | dev also matches a hex stored as a string [R] |
| treatments | v1 DELETE `/treatments/<id>` | hex or UUID as above; any other string matches only a stored `_id` [M] | — | — | hard delete on both [M] |
| treatments | v3 POST / PUT / PATCH / GET / DELETE `{identifier}` | body `_id` stored as sent, 24-hex as a **string** [M] | `identifier` (or a hex `_id` with no `identifier`); then `created_at` + `eventType` against a record with no `identifier` [R] | `identifier`, never `_id` [M] | v1 record re-sent through v3 at the same time: 15.0.8 400, dev 200 [M] |
| treatments | socket `dbAdd` / `dbUpdate` / `dbRemove` | 15.0.8 stored as sent (24-hex as a string, UUID as a string) [M]; dev 24-hex → ObjectId, other strings as sent [M] | `NSCLIENT_ID`, else `created_at` + `eventType` (exact, then ±2 s by amount); never `identifier` [M] | the stored or inserted document | 15.0.8 `dbUpdate`/`dbRemove` by a hex `_id` stored as a string answer `success` and change nothing; dev finds it [M] |
| devicestatus | v1 POST (array; `insertMany`) | 24-hex: 15.0.8 stored as a **string**, dev ObjectId [M]; any other `_id` → **400** [M] | none on 15.0.8 [M]; dev: a re-sent 24-hex `_id` is answered with the stored record and not written [M] | the `_id` stored [M] | re-sent `_id`: 15.0.8 **500**, earlier items kept, later items lost; dev 200, all stored [M] |
| devicestatus | v1 GET `find[_id]`; DELETE `/devicestatus/<hex>` | hex → ObjectId [R] | — | — | a hex stored as a string by 15.0.8's POST: 15.0.8 finds 0, deletes 0; dev finds and deletes it [M] |
| devicestatus | v3 POST / PUT / PATCH / GET / DELETE `{identifier}` | body `_id` stored as sent [R] | `identifier`; then `created_at` + `device` against a record with no `identifier` [R] | `identifier` [M] | same on both [M] |
| devicestatus | socket `dbAdd` | as sent (15.0.8), 24-hex → ObjectId (dev, every collection: `storeIdAsObjectId`, `lib/server/websocket.js:575-588` @fade2299) [R] | `NSCLIENT_ID`, else `created_at` (exact) [M] | the stored or inserted document [M] | — |
| profile | v1 POST / PUT / GET / DELETE `/profile/<hex>` | 24-hex: 15.0.8 POST stores a **string**, PUT looks up the ObjectId [M]; dev ObjectId [M]; any other `_id` → **400** [M] | POST: none (`insertMany`); PUT: `_id` [R] | the document [R] | 15.0.8 PUT after POST adds an ObjectId copy beside the string one (BF-99); dev one record [M] |
| profile | v3 `{identifier}` | body `_id` stored as sent [R] | `identifier`; then `created_at` [R] | `identifier` [R] | — |
| profile | socket `dbAdd` | as sent (15.0.8) [R] | `NSCLIENT_ID`, else `startDate`, then **replaces** the match [R] | the document [R] | — |
| food | v1 POST / PUT / DELETE `/food/<hex>` | 24-hex: 15.0.8 POST stores a **string**, PUT looks up the ObjectId [M]; dev ObjectId [M]; any other `_id` → **400** [M] | `_id` only (server-assigned when absent) [R] | the document [R] | 15.0.8 PUT after POST adds an ObjectId copy (BF-100); dev one record [M] |
| food | v3 `{identifier}` | body `_id` stored as sent [R] | `identifier`; then `created_at` [R] | `identifier` [R] | — |
| food | socket `dbAdd` | as sent (15.0.8) [R] | none: inserts [R] | the inserted document [R] | — |

API v3 GET of any collection answers `identifier`, and a record stored without one shows its
`_id` hex as its `identifier`; `_id` itself is never in a v3 reply [M for treatments; R for the rest]
(`normalizeDoc`, `lib/api3/storage/mongoCollection/utils.js:12-18` @15.0.8).

## 1. The two ids

**`_id`, the storage key.** MongoDB accepts any non-array value as `_id`; the lab stores UUID
strings and 24-hex strings as `_id` through the socket and API v3 [M]. Nightscout's convention
is an ObjectId: 12 bytes, served as 24 lower-case hex characters. ObjectIds are designed to be
made by any client without coordination (a timestamp, a random value and a counter), so a client
that creates one and sends it as `_id` is using the type as intended. On v1 entries and
treatments, a 24-hex `_id` has been converted to an ObjectId since 15.0.7 [R]
(`normalizeEntryId`, `lib/server/entries.js:267-284`; `normalizeTreatmentId`,
`lib/server/treatments.js:394-412` @15.0.8). Until #8758 (merged to dev 2026-09-25, not
released), v1 devicestatus, profile and food, and the socket, stored a sent 24-hex `_id` as the
string itself, while their lookups convert to an ObjectId, so the record could not be found,
edited or deleted by its id [M]; that is BF-99 to BF-102. On dev those paths store an ObjectId,
and every v1 and socket lookup also matches the string form (`lib/server/object-id-forms.js`
@fade2299) [M]. API v3 still stores a body `_id` as sent, a 24-hex value as a string, on both
refs [M]; see §2.6.

**`identifier`, the client's sync identity.** A string the client chooses, compared exactly as
stored (case kept) [M]. API v3 requires one on every record: when a POST has none, the server
computes `uuid.v5(device + "_" + date [+ "_" + eventType], "NightscoutRocks!")`
(`lib/api3/shared/operationTools.js:97-126` @15.0.8) [M: the stored value equals that
computation]. When a client sends one, the server keeps it and logs `APIv3: Identifier
mismatch` if it differs from the computed value [M, server log]. API v3's swagger says "The
client should not create the identifier"; the code does the opposite, which is BF-169. No index
on `identifier` is unique, on either ref [R] (`lib/server/entries.js:224,226`,
`treatments.js:430,432`, `devicestatus.js:168`, `api3/storage/mongoCollection/index.js:21`
@15.0.8).

## 2. Match keys per collection, and their pitfalls

### 2.1 Entries (v1)

The upsert filter is `sysTime` + `type`, always (`upsertQueryFor`, `lib/server/entries.js:238-256`
@15.0.8, `:301` @fade2299) [R]. Neither `_id` nor `identifier` selects the record.

| sent | 15.0.8 | dev |
|---|---|---|
| a new 24-hex `_id` | stored as that ObjectId; reply names it [M] | same [M] |
| the same `_id` and time again | 200, one record, fields updated [M] | same [M] |
| the same `_id` at **another** time | **500**, E11000 duplicate key: the filter finds no record at the new time, so the upsert inserts the `_id` already in use [M] | same [M] |
| **another** `_id` at a stored time | **500**, "Performing an update on the path '_id' would modify the immutable field '_id'": `$set` carries the sent `_id` (`:136`) [M] | 200; `_id` goes into `$setOnInsert` only (`:147`), so the stored record keeps its `_id` and the reply names it [M] |
| no `_id`, same time twice | 200 twice, one record; the second reply has **no `_id`** [M] | the second reply names the stored `_id` [M] |
| the same `identifier` at another time | **two records** [M] | same [M] |
| a new `identifier` at the time of a stored entry | **one record**; the stored `identifier` is overwritten [M] | same [M] |
| a batch whose 2nd item collides | 500; item 1 stored, items 2 and 3 not (ordered `bulkWrite`) [M] | same [M] |
| a UUID or any other non-24-hex string `_id` | moved to `identifier` (when none is sent), server assigns `_id` [M] | same [M] |

The socket's `dbAdd` on entries does no matching: an identical body sent twice is stored twice
[M] (generic `insertOne`, `lib/server/websocket.js:707` @15.0.8).

### 2.2 Treatments (v1)

`upsertQueryFor` (`lib/server/treatments.js:356-381` @15.0.8, `:411` @fade2299) tries, in order
[R, each step M]:

1. **`identifier`** when present. Under `UUID_HANDLING` the filter is `identifier = X or _id = X`,
   so a legacy record stored with the value in `_id` matches. **The sent `_id` is deleted**
   (`:362` @15.0.8, `:417` @fade2299): a write carrying `identifier` X and a new `_id` A is
   stored under a server-assigned ObjectId, not A, and the reply names the stored one [M].
   Re-sending X with yet another `_id` updates the same record [M]. Sending a stored record's
   `_id` with a **new** `identifier` creates a second record [M].
2. **`_id`** when present: a re-send with the same `_id` replaces the record, even at a new
   `created_at` [M].
3. **`created_at` + `eventType`**. On 15.0.8 that is the whole key, so a second carb entry at the
   same time with another amount replaces the first [M]. On dev (BF-121, #8780) the key adds the
   client's own id when it sends one (`syncIdentifier`, `id`, `uuid` or `NSCLIENT_ID`), and
   otherwise `carbs` and `insulin` and the absence of any id, so the two entries are kept [M]
   (`lib/server/treatment-fallback-key.js` @fade2299).

After a step-3 match the reply item has **no `_id`**, on both refs [M]: the server looks the
stored `_id` up only after an `identifier` match (`:104-129` @15.0.8). A v1 batch is one ordered
`bulkWrite`; a failure stops it and earlier items stay stored [R] (`:91`).

The socket's `dbAdd` on treatments matches `NSCLIENT_ID`, else `created_at` + `eventType`
exactly, then a ±2 s window on equal `insulin`, `carbs`, `percent`, `absolute` or `duration`
(`lib/server/websocket.js:515-580` @15.0.8; dev uses the BF-121 key without amounts) [R]; it
never reads `identifier`, so one `identifier` at two times is two records [M].

### 2.3 Devicestatus

v1 POST is `insertMany` with no key on 15.0.8 (`lib/server/devicestatus.js:70`) [R]: identical
bodies, or one `identifier`, sent twice are two records on both refs [M]. A re-sent 24-hex `_id`
fails the whole POST with 500 on 15.0.8; the items before it are stored and the items after it
are lost [M]. On dev, `withoutStoredIds` (`:57-90` @fade2299) answers a re-sent `_id` with the
stored record and stores the rest of the batch (unordered `insertMany`, `:135`) [M]. Any `_id`
that is not 24 hex is refused with 400 before storage (`lib/api/shared/objectid-validation.js`,
since 15.0.7) [M]. The socket's `dbAdd` matches `NSCLIENT_ID`, else `created_at`, and answers a
match with the stored record [M].

### 2.4 Profile and food

v1 POST and PUT accept only a 24-hex `_id` or none; anything else is 400 [M]. On 15.0.8 the POST
stores a sent 24-hex `_id` as a string while PUT and DELETE look up the ObjectId, so a PUT after a
POST leaves two records (BF-99, BF-100) [M]. On dev both store the ObjectId and PUT leaves one
[M]. Re-POSTing a stored profile `_id` is 500 (duplicate key) on both [M]. The socket's `dbAdd`
on profile matches `NSCLIENT_ID`, else `startDate`, and replaces the match (`:653-690` @15.0.8)
[R].

### 2.5 API v3 (every collection)

POST looks for `identifier`, or a 24-hex `identifier` equal to the `_id` of a record that has
none, or the collection's fallback fields against a record that has no `identifier`
(`identifyingFilter`, `lib/api3/storage/mongoCollection/utils.js:128-168` @15.0.8; fields in
`lib/api3/generic/setup.js`: entries `date` + `type`, treatments `created_at` + `eventType`,
devicestatus `created_at` + `device`, profile and food `created_at`) [R]. A match is answered 200
with `isDeduplication`; but `date`, `utcOffset`, `eventType`, `device` and `app` may not change,
so a re-send with another time or device is 400 and the record is unchanged [M, 2026-10-17 lab].
A record first written through v1 has no `date` or `device`: on 15.0.8 its v3 re-send is 400, on
dev it is accepted when `date` equals `created_at` [M]. GET by a v1 record's hex `_id` works on
both [M].

### 2.6 A body `_id` on API v3

API v3 does not read or convert `_id`; a POST that carries one is stored with it as sent, and a
24-hex value becomes a **string** `_id`, on both refs [M]. v3 replies and reads never show `_id`
[M], so the client cannot see this. On 15.0.8 a v1 `find[_id]` for that hex then misses the
record (`query.js` converts to an ObjectId); dev's v1 lookups match both forms [R]. Not filed as
a defect at the time of writing.

## 3. `UUID_HANDLING`

`UUID_HANDLING` is on unless set false (`env.uuidHandling = readENVTruthy("UUID_HANDLING", true)`,
`lib/server/env.js:93` @15.0.8, `:102` @fade2299) [R]. It was added in 15.0.7 (commit `bf6cfb77`,
reached `dev` in #8456) [R].

- **Writes, v1 entries and treatments only.** Any **string `_id` that is not 24 hex** is moved to
  `identifier` when the write has no `identifier`, and dropped either way; the server assigns an
  ObjectId [M]. The test is "not 24 hex", not "is a UUID": `ridlab-1a2b3c4d` is moved too [M]. With
  the flag off the value is dropped, not kept [R]. v1 devicestatus, profile and food refuse such an
  `_id` with 400 instead [M]; the socket and API v3 store it as `_id` [M].
- **Reads and deletes, v1 entries and treatments only.** A `find[_id]` (or `DELETE
  /treatments/<id>`) value that matches `UUID_RE` (`lib/server/query.js:7` @15.0.8, `:12`
  @fade2299, case-insensitive) becomes `identifier = value or _id = value`; the comparison is
  exact, so a record sent with a lower-case UUID is not found by the upper-case form, nor the
  reverse [M]. A value that is neither 24 hex nor UUID-shaped is passed as a literal `_id`, so
  `DELETE /api/v1/treatments/<non-UUID identifier>` deletes nothing [M]; `find[identifier]=`
  finds it [M]. `$in` lists are not rewritten [R]. Devicestatus lookups do not pass the flag [R].
- **Version-scoped quirks it serves** (D20 rule 7: today's handling becomes a registry entry
  scoped to the versions that send it, its behaviour unchanged).
  [QUIRK-TREATMENTS-006](../../specs/quirks/treatments.yaml): Loop sends a Temporary Override's
  `syncIdentifier` UUID as `_id` (read at LoopWorkspace `f8412858`, Loop 3.14.8; measured in the
  corpus: every stored document it fires on is an override with an upper-case UUID).
  [QUIRK-ENTRIES-004](../../specs/quirks/entries.yaml): upper-case UUIDs and 24-character
  non-hex strings stored as entries `_id` on two corpus sites, attributed to older Trio versions
  by a backlog, unmeasured. Trio 1.0.1 (`e41c9db3`) sends `_id` on carbs and temporary targets
  (`CarbsEntry.swift:29`, `TempTarget.swift:50`) and its other treatments' UUID as `id`, which
  Nightscout does not read (QUIRK-TREATMENTS-007). [R]

## 4. Driver history

| release | tagged commit's date | MongoDB driver | `_id` handling on write [R] |
|---|---|---|---|
| 15.0.0 | 2023-10-18 | `mongodb-legacy ^5.0.0` | passed to MongoDB as sent, on every path |
| 15.0.1 | 2023-10-20 | `mongodb ^3.6.0` (#8115 reverts #8026) | the same |
| 15.0.6 | 2026-03-03 | `mongodb ^3.6.0` | the same; a 24-hex `_id` is stored as a string (measured in BF-102) |
| 15.0.7 | 2026-04-29 | `mongodb ^5.9.2` (commit `69b620dd`, #8474) | v1 entries and treatments convert 24-hex to ObjectId and apply `UUID_HANDLING`; v1 devicestatus, profile and food refuse non-hex `_id` |
| 15.0.8 | 2026-09-04 | `mongodb ^5.9.2` | as 15.0.7 |
| dev `fade2299` | not released | as 15.0.8 | #8758: every v1 and socket path stores 24-hex as ObjectId and matches both forms |

**What 15.0.0 broke.** Not `_id` values, as far as the record shows. #8026 ("Mongo driver update
& less frequent database polls", merged 2023-10-12) moved to `mongodb-legacy` 5, which no longer
has the collection methods `insert`, `save` and `update`. 15.0.0 still called them on several
paths (`git show 15.0.0:lib/server/…`): `profile.js:11,22`, `food.js:8,26`, `activity.js:11,24`,
`treatments.js:163` (v1 PUT) and `websocket.js:406,454,472` (`dbAdd`). The issues filed in the
two days after the release report exactly those calls: #8114 (profile editor and v1 profile
saves fail), #8119 (iAPS profile upload), #8120 (`api(...).save is not a function` at
`treatments.js:163`, xDrip+ treatments), #8121 (`ctx.store.collection(...).insert is not a
function` at `websocket.js:406`, AndroidAPS `dbAdd`), #8146 (`api(...).insert is not a function`
at `profile.js:11`), and #8117 (deleting treatments from Reports answers 500, closed as the same
root cause without a stack trace). #8115 reverted #8026 "to allow further testing", which is
15.0.1; #8111 ("WIP: fix WS v1") was closed unmerged. The entries, treatments-create and
devicestatus write code of 15.0.0 differs from 15.0.1 only in the method names (`replaceOne` /
`insertOne` against `update` / `insert`), both replacing with the document as sent, so a
non-ObjectId `_id` was handled the same way on both. No issue in that window names `_id`. [R:
issues and PRs read with `gh` on 2026-10-18; `diff` of `lib/` between the tags]

## 5. For app developers: what holds today

Each rule says the version it holds from; "dev" means not yet released.

1. **To keep your own handle on a record, send either a 24-hex ObjectId you create as `_id`, or an
   `identifier`.** A 24-hex `_id` is stored as that ObjectId on v1 entries and treatments since
   15.0.7, and on v1 devicestatus, profile, food and the socket on dev; on 15.0.8 those paths
   store it as a string that their own id lookups miss [M]. API v3 stores a body `_id` as a
   string on both, and never returns it [M]; on v3, use `identifier`.
2. **Do not put any other value in `_id`.** On v1 entries and treatments it is moved to
   `identifier` or dropped (`UUID_HANDLING`, 15.0.7+); on v1 devicestatus, profile and food it is
   refused with 400 (15.0.7+); on the socket and v3 it is stored as the `_id` (all versions) [M].
3. **`identifier` is matched by v1 treatments (15.0.7+) and API v3 (all 15.x), not by v1 entries,
   v1 devicestatus, or the socket** [M]. On v1 treatments, sending `identifier` makes the server
   ignore the `_id` you send [M].
4. **Entries are matched on time, not on either id.** One reading per `sysTime` + `type`; a new
   `identifier` at a stored time overwrites the stored one's, and one `identifier` at two times is
   two readings (15.0.x) [M]. Do not re-send an entry's `_id` with a different time: 500 and the
   rest of the batch is lost (15.0.x) [M].
5. **Devicestatus has no match key.** Every POST adds a record (15.0.x); re-sending a 24-hex
   `_id` is 500 on 15.0.8 and answered with the stored record on dev [M].
6. **Read the reply for the `_id` that is stored.** It can differ from the one you sent (v1
   treatments with `identifier`; entries matched by time, on dev) or be absent (v1 treatments
   matched by time, 15.0.x; entries matched by time, 15.0.8) [M]. API v3 replies name only
   `identifier` [M].
7. **A delete is not final on API v3.** v1 DELETE removes the record and a re-send stores it
   again; v3 DELETE marks `isValid: false`, and a v3 POST with the same `identifier` restores
   it, even with another time and device (15.0.x) [M].

## 6. Open decisions

None of these is decided; each is a row in [the queue](../../queue/QUEUE.md).

| item | question |
|---|---|
| `ID-FORMAT-DECISION` | what an `identifier` may contain (opaque string, limits; UUID not required) |
| `ID-CLIENT-OID-DECISION` | may a client set `_id`, and which wins when `_id` and `identifier` name different records |
| `ID-V3-IMMUTABLE-DECISION` | on an `identifier` match, may `date`, `device` or `eventType` change |
| `ID-ABSENT-DECISION` | a write with no `identifier`: keep the time-key fallback, deprecate it, or require `identifier` |
| `ID-DELETE-REUSE-DECISION` | after a delete, a re-send of the same `identifier`: resurrect, refuse, or create new |
| `ID-SCOPE-DECISION` | is `identifier` unique per collection, across collections, per tenant |
| `ID-SIMPLE-MATCH` | the one server change proposed: v1 entries and devicestatus match on `identifier` |

Related: [identity specification](../30-design/platform/spec/identity.md) (the L0 rules this page measures today's behaviour against),
[Loop `identifier` proposal and reply](../30-design/platform/upstream-asks-loop-identifier/README.md),
[identifier format research](../60-research/tenancy/identifier-format-2026-10-17.md),
[identifier duplicates](../60-research/tenancy/identifier-duplicates-2026-10-17.md),
[write contract](../30-design/tenancy/write-contract-spec-2026-10-07.md) (its §1.4 measures
cross-path re-sends at dev `43289dde`),
[consumer-impact survey of #8758](../../reports/consumer-impact-15.0.9/clients-8758.md) (which
clients send which id), [D20](../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#263-d20--version-scoped-quirks-and-the-two-id-rule-maintainer-2026-10-16).
