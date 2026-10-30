# ID-FIRST-MATCH: the re-send rule on every path, cell by cell

*Contributor-facing design note for ID-FIRST-MATCH (plan §4.2), written 2026-10-29. Design only: no
`cgm-remote-monitor` code was changed or run for it.* Every claim carries a mark: **[M]** measured, with the
cell ids of the write-contract matrix pin
[`dev-e1f7ac41-idfirst.json`](../../../tools/qc/results/write-contract-matrix/dev-e1f7ac41-idfirst.json)
(`dev` `e1f7ac41`, 1,929 cells: 456 earlier and 1,473 new; companion
[`-uuidoff`](../../../tools/qc/results/write-contract-matrix/dev-e1f7ac41-idfirst-uuidoff.json), 504 cells);
**[R]** read from source, `file:line` at crm `e8224807` (the #8874 head, `write(intent)` release 1 with slices
4 and 6) unless another revision is named; **[R, prediction]** a value the rule is expected to give, read and
not run. Read-derived predictions are often wrong in this project; the implementation slices measure every
one of them.

`wi` is `lib/storage/write-intent.js`, `ws` is `lib/server/websocket.js`, `tfk` is
`lib/server/treatment-fallback-key.js`, all at `e8224807`. The full cell list is the appendix
[`id-first-match-design-note-2026-10-29-cells.md`](id-first-match-design-note-2026-10-29-cells.md).

**Headline.** The four decisions can be expressed without moving any of the 456 earlier cells [R, prediction;
§2 (e)]. Under them, 417 of the 1,473 new cells change (option M below). One ordering constraint is not
optional. If identifier-first lands on the socket before the chart-drag split stops copying `identifier`
onto the new half (BF-212), moving the insulin or carbs of a treatment that carries an `identifier` loses
data. Under the merge outcome, the moved half is merged back into the original at the new time. Under the
keep outcome, it is dropped after the original has already lost that field
(`treatments ws idf-split-written`: today 2 records [M], predicted 1 [R, prediction]). Merge on match does
not fix BF-212 on API v1 and in-process, and identifier-first extends it to the socket and to API v1 profile,
food and activity (§5).

---

## 0. The decisions, as the plan records them

From [plan §4.2](next-gen-platform-plan.md#42-identity) (main, 2026-10-29):

- "**Merge on match (2026-10-29).** When a re-send matching a stored record is applied, fields it leaves out
  are kept (RFC 7386), and `PUT` replaces. The census reads replace on several paths today. The extended
  matrix measures each path first, and each path that changes is listed cell by cell."
- "**Re-send after delete, every path (2026-10-29).** 'Acknowledged, stays deleted' applies on every path,
  and the spec text is corrected. Every changed cell is documented, so the change can be reverted or adjusted
  as cohort feedback arrives."
- "**Records without an identifier.** Natural keys for device status and profile are a separate item,
  ID-NATURAL-KEY, with its own corpus check of what would merge. Food and activity have no natural key."
- "**Socket edits and removes, and activity.** Identifier addressing is added where it changes nothing for
  writes that carry no `identifier`: socket `dbUpdate`, `dbUpdateUnset` and `dbRemove` accept an
  `identifier` when there is no `_id`, and activity creates match on `identifier`. This is conditional on the
  extended matrix showing every existing form unchanged."
- Rules in force from earlier: "**Fallback.** A v1 entries re-send whose identifier matches nothing still
  matches on `sysTime`+`type`; treatments never fall back. A devicestatus re-send whose identifier is stored
  writes nothing and is answered with the stored `_id`." "**Format (2026-10-29).** 1 to 256 URL-safe
  characters; a UUID is recommended; placeholders (`invalid`, `undefined`, `null`, `NaN`) are refused."
- Plan §1a row 9: "ID-FIRST-MATCH where it changes no outcome, and ID-BATCH", 16.2.0, or 16.0.0 through the
  entry bar.

## 1. The rule, as entries in the step's rule table

### 1.1 Three shared rules (new)

1. **`identifier-format`** (rule 1, in `plan()`, after the `_id` form). It checks the `identifier` the write
   will be matched by. That covers a sent one, one that `UUID_HANDLING` moved from a non-hex `_id`
   (`DOC_ID_FORMS['treatment-uuid']`, wi:271-287), and on API v3 a sent one before `resolveIdentifier`
   computes one for a write that has none (`lib/api3/shared/operationTools.js:182-189`). What a bad value
   gets, refused or treated as absent, is open question (vi). No pin cell sends a bad value [M: every
   `idf-` identifier is `crypto.randomUUID()`, harness `tools/qc/write-contract-matrix.js:723-731`].
2. **`identifier-match`** (rule 2, first). Filter: `identifier = X`. Under `UUID_HANDLING`, on entries and
   treatments, also `_id = X`, as today (wi:297-307, wi:434-438). On API v3, also the shown-`_id` clauses
   for records with no identifier, as today (`lib/api3/storage/mongoCollection/utils.js:155-165,193-206`).
   **Soft-deleted records are included.** When more than one record matches, the pick is open question (v).
   The predictions use P1: each path keeps today's pick, and a path that newly matches on identifier picks
   the first stored record.
3. **`on-deleted: acknowledged`**. A soft-deleted record (`isValid: false`) reached by any match key of a
   create is not written. The reply names the stored record with a 2xx. There is no `data-update`, no
   storage-socket event and no `storage-write-committed`, and `srvModified` stays, so API v3 history does
   not show it. On API v3 the reply takes the shape `acknowledge.js` gives devicestatus today (200,
   `identifier`, `isDeduplication`, `lastModified`; `lib/api3/generic/create/acknowledge.js:38-61`).

When `identifier-match` finds nothing, each path's remaining order runs as it does today (decision 3), and any
of its keys that reaches a soft-deleted record gives `acknowledged` (decision 2; open question (iv) is about
the keys that hide deleted records today).

### 1.2 Per collection, path and operation

Outcome words are the step's (`OUTCOMES`, wi:54). "Changed" names the rule-table entry that changes. Reply and
emissions are today's for that outcome on that path unless the row says otherwise.

| collection | path · op | rule-table entry today [R] | match order after | on a live match | soft-deleted | change |
|---|---|---|---|---|---|---|
| treatments | v1 / in-process create (`batch`, `one`) | `TREATMENTS_V1.create.forms` wi:388-405, `TREATMENT_ONE` wi:384, target `treatment-key` wi:297-317 | `identifier-match` → `_id` → fallback key (tfk:36-61) **only when the write has no identifier** (unchanged: "treatments never fall back") | `merged` (was `replaced`); reply the stored `_id` | `acknowledged` (today replaced, so revived [M: `treatments v1 idf-softdel-plain` `n=1 OID:v2 · replace`]) | changed: `onMatch`, `write` (`replace-one`/`bulk` replace → update), deleted |
| treatments | v1 / in-process create (`prebolus`) | wi:406-407 | `created_at`+`eventType` | `replaced`, unchanged: a record the server derives, not a client re-send (Q-H) | unchanged | none |
| treatments | v1 PUT / in-process save | `TREATMENTS_V1.update` wi:412 | as create | `replaced` (PUT replaces) | unchanged (an edit, not a re-send; open question (iii)) | none |
| treatments | socket `dbAdd` | `SOCKET_ADD.treatments` wi:1354; `writeSocketAdd` wi:1275-1345; `SOCKET_EXACT.treatment` wi:1166-1171; similar match wi:1199-1238 (with #8877's identity rule) | **`identifier-match`** (new) → `NSCLIENT_ID` → fallback key → ±2 s similar match | identifier match: `merged` (option M) or `unchanged` (option K), open question (i). Other keys: as today (`unchanged`; similar: `created_at`, `srvModified` set) | `deleted: 'hidden'` → `acknowledged` on every key, the similar match included | changed: new first key, deleted |
| treatments | socket `dbUpdate`, `dbUpdateUnset` | `socketUpdate()` wi:1485-1491, `planSocketUpdate` wi:1364-1370; request check `hasSafeIdentifier` ws:273-277, ws:365-369 | `_id` (`socketIdMatch`, wi:99-106), or **`identifier-match` when `_id` is absent or null and `identifier` passes `identifier-format`** (new, decision 4) | `merged` / unset, as today | unchanged (a dbUpdate reaches a deleted record today) | new target |
| treatments | socket `dbRemove` | `SOCKET_DELETE` wi:132, ws:376-378 | as `dbUpdate` (new) | `deleted` | n/a | new target |
| treatments | API v3 `POST` | identifying read inline (`create/operation.js:41-64`); write `v3Rules.update` `v3-replace` wi:1092-1097 | unchanged (`identifier`, shown `_id`, fallback against a record with no identifier, `utils.js:193-234`; first by `identifier: -1, _id: -1`, `find.js:82`); the read moves into the step | `merged` through `updateOne` (was `replaceOne`); the immutable-field 400 stays (`update/validate.js:71-92`) | `acknowledged` (today `validate` skips every check on a deleted record, `update/validate.js:85-87`, and the replace revives it) | changed: new `v3Rules.create.match`, write `v3-replace` → `v3-merge`, deleted |
| treatments | API v3 `PUT`, `PATCH`, `DELETE` | `v3Rules` wi:1129-1145 | unchanged | unchanged (`PUT` replaces) | unchanged (410) | none |
| entries | v1 / in-process create | `ENTRIES_V1` wi:693-699, `planEntries` wi:468-505 | unchanged (identifier when stored → `sysTime`+`type`) | `merged`, unchanged | `acknowledged` (today `$unset isValid` revives on purpose, wi:497-500) | changed: deleted |
| entries, food | socket `dbAdd` | `socketInsert('stamp-created')` wi:141-146 | **`identifier-match`** (new) → insert | `merged` | `acknowledged` | changed: `insert-one` → a matching `socket-add` with no natural key |
| entries, devicestatus, profile, food, activity | socket `dbUpdate`, `dbUpdateUnset`, `dbRemove` | as treatments | as treatments (new) | as today | as today | new target |
| entries, devicestatus, profile, food, settings | API v3 `POST` / `PUT` / `PATCH` / `DELETE` | as treatments | as treatments | as treatments, except devicestatus below | as treatments | as treatments |
| devicestatus | v1 / in-process create | `DEVICESTATUS_V1` wi:856-862, `withoutStoredStatusIdentifiers` wi:718-755 | unchanged (identifier → 24-hex `_id`) | `refused` 'already stored', HTTP 200 with the stored `_id` (I6; Q-J) | already acknowledged (the read has no `isValid` term) | none (the lookup moves to `identifier-match`) |
| devicestatus | socket `dbAdd` | `SOCKET_ADD.devicestatus` wi:1355 | **`identifier-match`** → `NSCLIENT_ID` → `created_at` | `unchanged`, as today | `hidden` → `acknowledged` | changed: first key, deleted |
| devicestatus | API v3 `POST` | as treatments; `acknowledge.applies` `acknowledge.js:31-33` | unchanged | identifier match: acknowledged, unchanged. Fallback match (`created_at`+`device`, no stored identifier): `replaced`, unchanged as read, open question (ii) | already acknowledged | none |
| profile | v1 / in-process create | `PROFILE_V1.create` wi:979-983, `writeProfiles` wi:924-976 | **`identifier-match`** (new) → `_id` (every stored form) | `merged` (as an `_id` re-send today); `canUpdate` refusal unchanged | `acknowledged` | changed: new first key, deleted |
| profile | v1 PUT / in-process save | `PROFILE_V1.update` wi:988-989 | unchanged | `replaced` | unchanged | none |
| profile | socket `dbAdd` | `SOCKET_ADD.profile` wi:1357 | **`identifier-match`** → `NSCLIENT_ID` → `startDate` | `merged` (was `replaced`) | `matched` (revives, Q-R) → `acknowledged` | changed: first key, `onExact`, deleted |
| food | v1 / in-process create | `food['v1/internal'].create` wi:1513-1525 | **`identifier-match`** (new) → `_id` (`id-eq`) | `merged` (was `replaced`) | `acknowledged` | changed |
| food | v1 PUT / in-process save | wi:1525 | unchanged | `replaced` | unchanged | none |
| activity | v1 / in-process create; socket `dbAdd` | wi:1539 and wi:1534 (`socketInsert('none')`) | as food (decision 4) | `merged` | `acknowledged` | changed |
| settings | API v3 only | `settings: { v3: V3_OTHER }` wi:1532 | as API v3 (no fallback fields) | `merged` | `acknowledged` | as API v3 |

**#8877** (BF-209 and BF-211, merged to `dev` as `cf3d4b8f`, head `ac5d77fb`) adds the client-identity rule to
the socket's similar match, with an `identifier` the write carries deciding on its own (`identityQuery(…,
{ identifier: true })`, tfk at `ac5d77fb`). After `identifier-match` runs first on the socket, that branch
only ever sees a write whose identifier matched nothing. It then rejects every stored record in the window,
which is the same outcome. The client-identity part stays. Read against the pin, #8877 alone moves **no new
cell**. It moves one earlier cell, `treatments x v3 x ws` (plan §1a), because the API v3 seed carries a
computed identifier and the socket write carries none [R, prediction for the new cells: every
`idf-identifier-*` socket cell either matched in the window with the same identifier or is outside it].

## 2. Impact, cell by cell, computed from the pin

The classification reads each new cell's measured `store` and `shape` (the harness labels: `merge`,
`replace`, `not-written`, `new`; seeds carry `wck: 1`, re-sends `wcv: 2`; harness:86-93). It applies §1:

- A re-send carries an identifier for the `idf-identifier-*`, `idf-*-identifier`, `idf-split-*` forms; for
  `idf-uuidid-*` on v1 and in-process entries and treatments (moved under `UUID_HANDLING`); and on API v3
  always, computed when none is sent. A computed identifier reaches only an API v3 seed.
- A path new to identifier matching (socket; v1 / in-process profile, food, activity) turns a second record
  into one.
- Today's `replace` becomes `merge` (not on devicestatus).
- A soft-deleted seed that a key reaches is acknowledged.
- Split cells use pick P1.

The earlier cells that re-send and replace today are listed in group (a). The `cache` field is set aside, as
for every pin. The full list, with today's value and the prediction per cell, is the appendix.

| group | cells | where |
|---|---:|---|
| (a) the write changes, no recorded value is predicted to change | 62 | 56 earlier cells whose re-send replaces an identical body today; `settings v3 resend-identity`; 5 devicestatus socket cells now matched by identifier instead of `created_at` |
| (b) identifier now matches where a second record was stored | 88 | socket (entries, food, activity, profile `-time`, treatments `-amt`/`-time`, devicestatus `-time`); v1 / in-process profile, food, activity; same path and across paths |
| (c1) replace becomes merge, same record | 216 | v1 / in-process treatments; API v3 every collection; socket profile; in-process food / activity by a string `_id` |
| (c2) kept becomes merge, socket treatments (option M only) | 4 | `treatments ws idf-identifier-same` and its three cross cells |
| (d1) revived becomes "acknowledged, stays deleted" | 36 | v1 / in-process treatments and entries; API v3; socket profile |
| (d2) a new record beside a deleted one becomes "acknowledged, stays deleted" | 23 | socket treatments and devicestatus (plain and identifier); socket entries and food, v1 / in-process profile, food, activity (identifier forms only) |
| (g) two records share one identifier (split family, BF-212), pick P1 | 50 + 1 not visible | §5 |
| (h) unchanged as read, in question | 12 | `devicestatus x {v1,inproc,ws} x v3 idf-{syncIdentifier,id,uuid,NSCLIENT_ID}-same`, the API v3 fallback replace; open question (ii) |

**417 new cells change** under option M (b 88 + c 220 + d 59 + g 50). Under option K, 415 do: c2's four cells
keep their store but `srv` goes from `C=M+` to `C=M=` and `hist` from `valid` to `absent`, and two split cells
keep their values. The appendix lists the 12 cells whose prediction differs between M and K.

**(a) No outcome change: 62 cells.** The 56 earlier cells are `resend-*`, `legacy-*` and the cross cells
(`<c> x A x B`) that re-send an identical body through a path that replaces today: v1 / in-process treatments,
food and activity, API v3 and the socket's profile. Merge and replace of an identical body store the same
document. API v3's cached `updateOne` emits the same cache update as `replaceOne` for a valid record
(`mongoCachedCollection/index.js:41-68` at `e8224807`), so `ev` is predicted equal. Examples:
`treatments v1 resend-identity`, `food v1 resend-hex`, `profile ws resend-identity`,
`entries x v1 x v3` [M today: one record; R, prediction: equal].

**(b) to (d)** examples (today [M] → predicted [R, prediction]):
- `profile v1 idf-identifier-same`: `n=2 OID,OID:v2 · not-written,new` → `n=1 OID:v2 · merge`.
- `treatments ws idf-identifier-amt`: `n=2 · not-written,new` → `n=1 OID:v2 · merge` (K: `n=1 OID ·
  not-written`, the other amount is dropped).
- `devicestatus ws idf-identifier-time`: `n=2` → `n=1 OID · not-written`.
- `treatments v1 idf-identifier-amt`: `n=1 OID:v2 · replace` → `n=1 OID:v2 · merge` (c1).
- `treatments v1 idf-softdel-plain`: `n=1 OID:v2 · replace`, `srv C=M+` → `n=1 OID:inv · not-written`,
  `srv C=M=` (d1).
- `treatments ws idf-softdel-plain`: `n=2 OID:inv,OID:v2 · not-written,new` → `n=1 OID:inv · not-written` (d2).

Per collection (same path and cross cells together; the appendix splits by path):

| collection | a | b | c1 | c2 | d1 | d2 | g |
|---|---:|---:|---:|---:|---:|---:|---:|
| treatments | 20 | 5 | 97 | 4 | 12 | 4 | 11 |
| entries | 4 | 9 | 25 | 0 | 8 | 2 | 5 |
| devicestatus | 5 | 4 | 0 | 0 | 0 | 4 | 1 (+1) |
| profile | 12 | 22 | 57 | 0 | 8 | 4 | 11 |
| food | 11 | 27 | 22 | 0 | 4 | 6 | 11 |
| activity | 9 | 21 | 5 | 0 | 0 | 3 | 9 |
| settings | 1 | 0 | 10 | 0 | 4 | 0 | 2 |

**(e) The additive items (decision 4). Earlier cells that move: none** [R, prediction]. Every earlier socket
`dbUpdate`, `dbUpdateUnset` and `dbRemove` form sends an `_id` (harness:435-437, 651, 658, and
`update-twin`, `harddelete-custom` with a string `_id`, `harddelete-num` with a number). Today a request
without an `_id` is refused with `{ result: 'Missing or invalid _id' }` (ws:365-369, ws:376-378), and no form sends
one. No earlier activity form carries an `identifier`: `body()` has none (harness:292-300), and activity has no
API v3 path to compute one. Decision 4 therefore holds against the pin. It still changes outcomes for writes
that carry an `identifier`. Activity identifier matching moves 24 new cells: 21 in (b) and 3 in (d2):
`activity {v1,inproc,ws} idf-identifier-*`, their cross cells, and `activity {v1,inproc,ws}
idf-softdel-identifier`. Identifier addressing on the socket moves no cell, because no form exercises it
(§4). The same holds for everything else in §1: of the 456 earlier cells, none is predicted to move, and 56
change only how they are written (group a).

**(f) Dedupe-gate fixtures that change** (`tests/websocket.dedupe-gate.test.js` at `e8224807`, 58 tests; titles
are the same at `ac5d77fb`, where #8877 flipped three others). No fixture sends `identifier`, so identifier
matching changes none. Six fixtures change [R, prediction]:
- `treatments: 6. a soft-deleted record (isValid: false) is never a match` › `on NSCLIENT_ID`,
  `on the fallback key`, `in the similar match`: stored → acknowledged, stays deleted (decision 2).
- `devicestatus: exact match on NSCLIENT_ID or created_at` › `never matches a soft-deleted record`: the same.
- `profile: replaced on NSCLIENT_ID or startDate` › `replaces a soft-deleted profile with the same
  NSCLIENT_ID` (Q-R): replaced → acknowledged, stays deleted.
- `profile: replaced on NSCLIENT_ID or startDate` › `replaces the stored profile with the same startDate when
  no NSCLIENT_ID is sent`. The stored profile carries `NSCLIENT_ID` and the write does not, so a merge keeps
  it. The fixture's `plain(after[0]).should.eql(expected)` then fails (decision 1). Its sibling
  `replaces the stored profile with the same NSCLIENT_ID` sends every stored field and is predicted to pass
  unchanged.

**`UUID_HANDLING` off** (the `-uuidoff` pin, entries and treatments only): b 14, c1 114, c2 4, d1 20, d2 6,
g 16. The 16 cells that differ between the two pins [M] are `idf-uuidid-*` cells, where the flag decides
whether the UUID becomes the identifier. With the flag off they are re-sends with no identity, so
identifier matching cannot reach them.

## 3. Release slicing

Each slice is one rule-table change with its own pin, red control, ablation and revert. **Red control:** put
the slice's old rule back in the step (one rule-table value). The matrix against the slice's pin then shows
exactly the slice's cells red. **Ablation:** remove the slice's new rule. Its cells, and the named unit test,
go red. **Revert:** revert the slice commit. The previous pin then holds at 0 cells (G1), `cache` aside.
Counts are option M with P1.

| # | slice | cells that move | gate fixtures | pin it writes | red control | ablation |
|---|---|---:|---|---|---|---|
| 1 | **No outcome change.** `identifier-match` used by the paths that already match on identifier: v1 / in-process treatments, entries and devicestatus, and API v3's identifying read moved from `create/operation.js:47-49` into the step. Each path keeps its order, pick and outcome as data. Socket `dbUpdate`, `dbUpdateUnset`, `dbRemove` by `identifier` when there is no `_id` (decision 4) | 0 of 1,929 and 0 of 504 | none | none (holds `dev-e1f7ac41-idfirst.json` and `-uuidoff`) | not applicable: nothing moves | `identifier-match` answers "no match": predicted red are the identifier-matched cells of those paths (for example `treatments v1 idf-identifier-time`, `entries v1 idf-identifier-time`, `devicestatus v1 idf-identifier-same`, `treatments v1 idf-uuidid-amt`, `* v3 idf-identifier-same`), listed as measured. Socket addressing: a new unit test (§4) |
| 2 | **`identifier-format`** (ID-VALIDATE), with the outcome open question (vi) settles | 0 in the pin | none | first a harness extension with placeholder, over-length and bad-character forms, pinned on the slice's base; then the slice moves only those cells | the check off | the check off; the new cells and the unit test red |
| 3 | **Stays deleted** on the keys that reach a deleted record today, and on the socket keys that hide one: d1 36 and the d2 plain cells (`{treatments,devicestatus} ws idf-{softdel,v3del}-plain`) | 40 | the five deleted-record fixtures | `dev-<rev>-idf-s3.json` | `on-deleted` back to each path's today (revive, `hidden`, `matched`) | `on-deleted` removed from `identifier-match` only: the identifier-carrying cells among the 40 go red |
| 4 | **Merge on match:** c1 216, plus the 16 split cells where the same record is merged instead of replaced (v1 / in-process treatments, API v3), plus group (a)'s 62 with no value change | 232 | `replaces the stored profile with the same startDate…` | `dev-<rev>-idf-s4.json` | `onMatch: 'replaced'` per path: v1 / in-process treatments (72 cells in c1 with the re-send through v1 or in-process), API v3 (`v3-merge` → `v3-replace`), socket profile | per path, the merge write swapped for the replace write |
| 5 | **Shared identifiers (BF-212)**: the pick rule of open question (v), and the chart split not copying identity fields onto the new half | P1: 0; P4: §5 | none | P4 only: `dev-<rev>-idf-s5.json` | the pick back to P1 | the split's copy keeps identity (the probe `probe/split-ident-2026-10-29` goes red) |
| 6 | **Identifier first where it is new:** socket entries, treatments, devicestatus, profile, food; v1 / in-process profile and food. Needs slices 2 and 5 first | 112 (+1 not visible): b 67, c2 4, d2 16, g 25 | none | `dev-<rev>-idf-s6.json` | `identifier-match` removed from those entries | the same, per path |
| 6a | **Activity** (decision 4), on v1, in-process and socket | 33: b 21, d2 3, g 9 | none | `dev-<rev>-idf-s6a.json` | as 6, activity only | as 6, activity only |

Slices 3 to 6a each change outcomes. Plan §1a lets each clear the entry bar on its own (matrix result as
stated, red controls, a rehearsed revert, time on `dev` with its cohort check). Slice 1 is the "where it changes
no outcome" part of plan row 9. The slice order puts protection first: a deleted dose stays deleted (3), then
the write shape (4). Each of 3 to 6a reverts on its own, and the appendix's group for each slice is the list
the soak reverts against.

## 4. What the matrix still cannot see, and the unit tests needed

1. **Which record a reply names.** The harness records `[1 _id]`, not which one (harness:403-416).
   `devicestatus ws idf-split-second` keeps its values under P1 while the reply names A instead of B.
   Unit test: under each pick rule, every outcome replies with the matched record's `_id` and `identifier`
   (I4).
2. **Field-level merge.** The `wck`/`wcv` probe shows only whether a left-out field survived. Unit tests per
   path: a nested object (profile `store`; RFC 7386 merges objects member by member), an explicit `null` in
   a create re-send (removes on merge on match, plan "Null removes"), a field left out on purpose.
3. **Identifier format.** No form sends a placeholder, an over-length value, a character outside the set or a
   24-hex identifier that is not the record's own `_id`. Harness forms first (slice 2), then unit tests of
   `identifier-format` per path, including a placeholder `_id` that `UUID_HANDLING` moves.
4. **Races.** Two creates with one new identifier at once: both miss the lookup and both insert. Only a unique
   index stops this (open question (v)). Integration test with concurrent writes, before and after the index.
5. **A live and a deleted record sharing one identifier.** The pick between them. Unit test.
6. **PUT or save with an `_id` and an `identifier` that name different records** (identity: "identifier
   decides"), and **PUT or save on a soft-deleted record** (v1 save replaces and so revives; v3 `PUT` answers
   410). Unit tests.
7. **Socket addressing by identifier** (decision 4): `dbUpdate`, `dbUpdateUnset`, `dbRemove` with only
   `identifier`, with both (`_id` decides), with a placeholder, with two records sharing it, with a deleted
   record. Today's refusal of a request without `_id` (ws:365-369) is the baseline. New gate fixtures, one
   ablation each.
8. **A v1 batch with a repeated identifier, or one deleted** (ID-BATCH): per-item outcomes. Unit tests.
9. **`storage-write-committed`.** The official harness does not record it. Unit test: an acknowledgement
   commits nothing.
10. **`WRITE_VALIDATION=reject`.** The pin runs with it off. A merge whose result fails the domain rules, and
    the conditional validated update (`lib/storage/validated-update.js`). Unit tests.
11. **Cross-path deletes and `-amt` across paths.** The delete forms and `-amt` run on the same path only
    (harness:845-866). Unit tests for a v1 seed deleted through the socket and re-sent through API v3, and so
    on.
12. **An API v3 delete of a shared identifier.** `filterForEveryForm` matches every record with that
    identifier (`utils.js:179-182`), so one `DELETE` reaches both halves of a split [R]. Unit test.
13. **The chart split end to end.** The client sends `dbUpdateUnset`, maybe `dbUpdate`, then `dbAdd`
    (`lib/client/renderer.js:1014-1040,1046-1072`, `lib/client/treatmenttime.js:60-73`). The matrix's
    `idf-split-written` is two `dbAdd`s. Use the BF-212 probe with and without identifier-first on the socket.

## 5. BF-212: the shared-identifier data loss, and a rule for it

**Today [M].** Two stored treatments A and B share one `identifier`, B two minutes later with another amount.
On API v1 and in-process, a re-send of B lands on A: `treatments v1 idf-split-second` is `n=2 OID:v2,OID ·
replace,not-written`, the first record (A) replaced. `treatments v1 idf-split-first` is the same.
`treatments v1 idf-split-written` is `n=1`: B's own write already replaced A. Entries do the same with merge
(`entries v1 idf-split-second` `merge,not-written`). On API v3, the lookup picks B
(`treatments v3 idf-split-second` `not-written,replace`), and a re-send of A is refused 400 because B's date
is immutable (`treatments v3 idf-split-first`). The socket picks by time: `treatments ws idf-split-second`
stores nothing new and the similar match finds B. Socket entries, food and activity and v1 profile, food and
activity store a third record (`n=3`).

**Under identifier-first plus merge, pick P1 [R, prediction; appendix group g].**
- **Kept** on v1 / in-process treatments and entries: 4 `-second` cells. Merge keeps only the fields the
  re-send leaves out. A and B carry the same fields, so A still takes B's amount and time
  (`treatments v1 idf-split-second` → `merge,not-written`).
- **Worsened** on 11 `-second` cells, where a re-send of B now overwrites A:
  `treatments ws`, `profile ws`, `{entries,food,activity} ws`, `{profile,food,activity} {v1,inproc}`. Today
  these either land on B (socket treatments and profile) or store a duplicate.
- **Collapsed** on 12 `-written` cells, where B's own write is matched to A: today 2 or 3 records, predicted
  1. On the socket this is the chart split's `dbAdd`.
- **Unchanged** on API v3: B is picked, and A is refused 400.

**So the rule as decided keeps BF-212 and widens it.** It is fixed only by a pick that tells the two records
apart, by stopping the split from creating them (slice 5), or by both.

**A rule for two records that share one identifier** (proposed for open question (v)):
1. The server does not create a second record with an identifier that is stored, on any path. Under
   `identifier-match` everywhere, a create carrying a stored identifier is a re-send by definition. The
   remaining ways in are a race, a `PUT`/save or `dbUpdate` that sets another record's identifier, and the
   records that already exist.
2. When an identifier names more than one stored record, the pick is **P4**: the record whose time key
   equals the re-send's (`created_at` for treatments, devicestatus, food, activity; `date`/`sysTime` for
   entries; `startDate` for profile), else the newest by `_id` (API v3's order today), and every such match is
   logged. Under P4 [R, prediction]: `-first` and `-second` land on their own record on every path where the
   time survives to the lookup. API v1 food overwrites `created_at` with the server time (`lib/server/food.js`
   create, census F1), so food falls back to the newest. `* v3 idf-split-first` changes from 400 to a merge
   into A. `-written` still collapses (rule 1).
3. The chart split stops copying `identifier`, `syncIdentifier`, `id` and `uuid` onto the new half
   (`treatmenttime.js:60-73` deletes only `_id` and `NSCLIENT_ID`). This is the register's control: with the
   copy stripped, the shared-identity effects go [M, BF-212 entry]. It must land before slice 6. With the
   copy unchanged and identifier-first on the socket, option M merges the moved half back into the original at
   the new time, so both halves move. Option K drops it after `dbUpdateUnset` has removed it from the
   original, so the insulin or carbs is lost. Both apply only to records that carry `identifier`: API
   v3-written records, and the 505 Loop treatments with an `identifier` in the 12-site corpus
   (`docs/60-research/tenancy/identifier-format-2026-10-17.md` §2).

**Unique index consequences** (ID-UNIQUE-INDEX, plan §4.2; read, with the pin where it applies):
- **Existing duplicates.** ID-DUP-MEASURE found 0 across the 12-site corpus (plan §4.2). That corpus has no
  API v3 writer (format research §2), and every chart split of an identifier-carrying treatment makes one.
  A unique `createIndex` fails on the first duplicate. The server needs a defined path: report and run
  without the index, or a migration. A migration cannot choose between two split halves, which are both real
  doses.
- **Soft-deleted records.** Decision 2 means they count. A deleted identifier is acknowledged, never
  re-created, so the index covers deleted records too. A partial filter can then be `identifier: { $type:
  'string', $gt: '' }`, which also leaves out the empty values that tfk:32-34 and API v3's
  `emptyIdentifier` treat as absent. Excluding deleted records would need `isValid` stored as a positive
  value, because partial filters do not take `$ne` (the supported operators per MongoDB version are to be
  verified against the floor version, node-version policy).
- **Twins.** A string and an ObjectId copy of one record (BF-130) carry the same identifier, so a stored twin
  fails the index. Twins are removed on write by the step today (rule 5). Stored twins from earlier versions
  need the same migration.
- **Scope.** Per collection, with the tenant in the key under multi (plan "Scope"). API v3's computed
  identifiers (UUID v5 of `device`, `date`, `eventType`, `operationTools.js:141-158`) already make records
  that share those one record. That is consistent with the index.
- **A duplicate-key error** from a race must become a re-read and match, never a 5xx (I4).

## 6. Open questions

Mechanism and trade-off for each. IDs are allocated by session -a5.

(i) **Socket treatments: merge or keep on an identifier match.** Decision 1 says merge. The socket's exact
match keeps the stored record today and drops an edited re-send (identity reference §2.7, gate
`treatments: 1.`). Mechanism: `SOCKET_ADD.treatments.onExact` is `unchanged`; the new `identifier-match` needs
its own outcome. Trade-off: merge (M) applies an edited dose re-sent over the socket, and with the chart split
unfixed it moves both halves. Keep (K) never lets a socket re-send change a stored dose, and with the split
unfixed it loses the moved half. The 12 cells that differ are listed in the appendix.

(ii) **Devicestatus: acknowledge, merge, or replace.** Identifier matches acknowledge (I6, "devicestatus never
merges"), which agrees with decision 1 only if devicestatus is an exception. The API v3 fallback match
(`created_at`+`device` against a status with no identifier) replaces today
(`create/operation.js:56-60`). The 12 group (h) cells keep that, as read. Mechanism: three outcomes on one
collection, chosen by which key matched. Trade-off: merging a status into another folds Loop's distinct
statuses that share `created_at`+`device` (identity §3 counts 3,078 groups). Acknowledging there also changes
those 12 cells. Spec Q3 (i) (a differing body is a new record) is ID-NATURAL-KEY's, by decision 3.

(iii) **"Stays deleted" against API v3's revive and history.** API v3 `POST` brings a soft-deleted record back
today. `PUT` and `PATCH` answer 410. v1 entries revive on purpose (wi:497-500). Under decision 2 nothing is
written, so the re-send leaves no history entry and a client cannot undo a delete by re-sending. It needs a
new identifier. Mechanism: `on-deleted` in `identifier-match` and in each remaining key. Trade-off: a deleted
dose cannot come back through a retry or a full re-upload (UCA-SYNC-STORE-003). A record deleted by mistake
cannot be restored through the API it was written with. v1 `PUT`/save on a deleted record still replaces, and
so revives. Should "every path" cover edits, or only re-sends?

(iv) **Stays deleted on keys other than the identifier.** The socket's fallback key (no amounts), its ±2 s
similar match, devicestatus `created_at` and profile `startDate` hide or revive deleted records today. Applying
decision 2 to them moves the d2 plain cells and five fixtures. Mechanism: those keys are not identities, so a
new record can share one with a deleted record. Trade-off: applying it means a new carb entry at the same
`created_at` and `eventType` as a deleted one is acknowledged and not stored. Not applying it keeps today's
second record beside the deleted one (4 cells and 4 fixtures stay as today), and for the socket profile
today's revive.

(v) **Two records with one identifier: the pick, and a unique index** (§5). Options:
- **P1:** each path keeps its pick (A on v1, B on v3). Changes nothing today and keeps BF-212.
- **One order everywhere:** oldest or newest. One path changes and the loss moves to the other half.
- **P4:** time key, then newest. Fixes `-first`/`-second` where the time survives; changes 400 to a merge on
  `* v3 idf-split-first`.
- **Refuse when ambiguous:** a refusal per item. Safest for the data, but a retrying client loops (D-LOOP-ID
  rule 3).

Plus whether to add the partial unique index, and when: after the split fix and a duplicate report. Mechanism:
`identifier-match` assumes I6, and the split and earlier writes break it. Trade-off: as listed, with the index
making ambiguity impossible going forward at the cost of a migration for sites that already have duplicates.

(vi) **Identifier format: where, and what a bad value gets.** Where: `identifier-format` in `plan()` after
the `_id` form (§1.1). Without that placement, a placeholder `_id` such as `"undefined"` that `UUID_HANDLING`
moves on v1 treatments and entries is not checked. Today it becomes `identifier` and is matched first, so two
clients sending that `_id` already share one record on v1 treatments [R: wi:276-280, wi:298-307]. The two
options:
- **Refuse:** HTTP 400 on API v3, as for an empty one (`create/validate.js:19`); a refused item on v1 (needs
  ID-BATCH, else the whole batch); `{ result: … }` on the socket.
- **Treat as absent:** match by the remaining order, and do not store the value. Storing it would put many
  records under one identifier and fail the unique index. On API v3 a computed identifier replaces it.

Cell impact from the pin: **0 cells under either option**, because no form sends such a value (§4 item 3).
Clients: none in the corpus is known to send a placeholder as `identifier`. The 12-site corpus's identifiers
are 16 UUIDs and 489 32-hex values (format research §2). G7SensorKit's literal `"invalid"` is a Loop CGM
`syncIdentifier`, and Loop sends no identity on entries (format research §1). The definition of "URL-safe" is
open too. nightscout-connect sends `glooko:<kind>:<sha256>` and `librelinkup:sensor-start:<sha256>`
(`lib/sources/glooko/map.js:35-40`, `lib/sources/librelinkup.js:317` at `04102f9`). Loop dose keys can hold
`/` and spaces. Identifier conventions C3 allows `:` and `/`; RFC 3986's unreserved set does not. Trade-off:
refusing makes a client that retries a refusal loop, and treating as absent silently changes what the client
named.

(vii) **Merge of nested objects.** RFC 7386 merges object members, so a profile re-send that drops a named
profile from `store` keeps it. v1 profile `POST` already merges (Q1b). The socket's profile and API v3's
dedup replace today (c1). Mechanism: decision 1 applies RFC 7386 to the whole document. Trade-off: keeping
fields another writer added, against a client that removes a profile by leaving it out and finds it still
there.

(viii) **`_id` re-sends on v1 food and activity create.** These are upserting replaces by `_id` today. Decision
1 makes them merges: 18 of group (a), no value change in the pin. Mechanism: Q-H, "create on v1 has always
been allowed to replace". Trade-off: one rule for every create, against keeping v1 `POST` by `_id` as a replace
like `PUT`.

(ix) **How additive decision 4 is.** It holds for every earlier form (§2 (e)). Two consequences go beyond
"unchanged". A socket request with no `_id` and an `identifier` is refused today and would be applied. No
client is known to send one: AndroidAPS 3.4.2.x's v1 sync addresses by `_id` and sends no `identifier` (BF-209
register line). Activity identifier matching changes 24 new cells. Mechanism: "additive" is measured against
existing forms, not against every input. Trade-off: shipping 6a with slice 1 (both "no existing form changes")
or after slice 6, where the plan's "lands first where it changes no outcome" puts it.

(x) **Addressing by an identifier two records share.** A socket `dbUpdate` or `dbRemove` by identifier reaches
one record or all of them. API v3 `DELETE` reaches all (§4 item 12). `_id` addressing reaches every stored form
of one record (`socketIdMatch`, `many: true`). Mechanism: the pick of (v) or the every-form filter. Trade-off:
deleting both halves of a split by one request, against an update that lands on the half the pick names.

(xi) **When outcome slices ship.** Plan row 9 puts "where it changes no outcome" in 16.2.0. D-LOOP-ID: "a
default changes only in a major (16.0.0 if it clears the entry bar, otherwise 17.0.0)". Slices 3 to 6a each
change a default. Mechanism: each slice is its own revert, so each can clear the bar or roll separately.
Trade-off: 16.0.0 gets protections (slice 3) while the major is open, and 17.0.0 gives cohorts a release of
notice.

## 6a. Question ids and answers (session -a5, 2026-10-29)

The questions in §6, numbered in order: (i) is ID-Q1, (ii) ID-Q2, (iii) ID-Q3, (iv) ID-Q4, (v) ID-Q5,
(vi) ID-Q6, (vii) ID-Q7, (viii) ID-Q8, (ix) ID-Q9, (x) ID-Q10 and (xi) ID-Q11.

- **ID-Q5, decided by the maintainer:**
  - the chart split stops copying identity fields, as a 16.0.0 backfix under BF-212;
  - identifier-first picks between existing duplicates by P4 (the time key, then the newest);
  - identifier-first never creates a second record with an identifier already stored;
  - a unique index comes later, after a per-site duplicate report and a cleanup step.
- **ID-Q4, decided:** "stays deleted" applies only when the match is on an identity (`identifier`,
  `syncIdentifier`, `id`, `uuid`, `NSCLIENT_ID`, `_id`). A match on a time key against a deleted record stores
  the new record. The socket profile's revive is a separate small question.
- **ID-Q1, decided:** socket treatments merge on an identifier match, after the split fix.
- **ID-Q3:** the maintainer leans to refusing edits of a deleted record on every path, with a separate
  restore action. He asked first which clients that would affect and what the AndroidAPS authors intend.
  A client survey is under way.
- **ID-Q2, decided:** device status follows the same default as the other collections (merge on an identifier
  match). The re-send switch (ID-RESEND-SWITCH) can select acknowledge, and the maintainer noted that the
  switch is the place for that choice. This changes only `dev`'s unreleased behaviour since #8859 (acknowledge);
  15.0.9 stored a duplicate. Loop sends no device-status identifier, and AndroidAPS creates each status once.
  API v3's `created_at`+`device` fallback is left to ID-NATURAL-KEY.
- **ID-Q6, decided:**
  - no character restriction. Any string up to 256 characters (MongoDB's index key limit) is accepted, and the
    docs say an identifier used in a URL path must be percent-encoded;
  - a placeholder (`undefined`, `null`, `invalid`, an empty string) or an over-length value is treated as
    absent: it is ignored for matching, not stored, and answered with a warning;
  - strict refusal is available behind a setting, off by default;
  - the check runs right after the `_id` step, so a placeholder `_id` moved into `identifier` by
    `UUID_HANDLING` is caught as well.
- **ID-Q7, decided:** a matched profile re-send replaces `store` as a whole, and its other fields merge. No
  released client depends on a merge of `store`: 15.0.9 refused that re-send (BF-166), and API v3 and the socket
  replace. This adjusts the `dev`-only Q1b rule for `store`.
- **ID-Q3, decided** after a [client survey](../../60-research/tenancy/deleted-record-edit-survey-2026-10-29.md):
  - an edit of a soft-deleted record over API v1 (PUT, the socket's `dbUpdate`, in-process `save`) is answered
    2xx and **not applied**, so the record stays deleted. Today it revives;
  - API v3 keeps its documented 410;
  - a setting, off by default, makes v1 refuse instead (410);
  - the spec documents both, and client authors are asked to handle a 410, starting with AndroidAPS, whose upload
    queue stalls on a 410 PATCH;
  - a deliberate restore is a separate item.

  Why 2xx on v1: every surveyed v1 editor retries a 4xx without limit, and Loop and xDrip+ then block other
  uploads. The server also cannot tell an xDrip+ edit from its retry, because both are a PUT.
- **ID-Q8, decided:** merge, one rule. A matched v1 food or activity create merges, and only PUT replaces.
- **ID-Q9, decided:** both additive items ship with slice 1 (a socket edit or remove by `identifier` without
  `_id`; activity creates matching `identifier`). No existing request changes.
- **ID-Q11, decided:** data protection first. The slices go to the 16.0.0 entry bar in the order 1 (with the
  additive items), 2, 5, 3, 4, 6, 6a. Whatever has not cleared the bar at the tag rolls to 17.0.0 if it changes a default, otherwise to 16.1.0 (rule of 2026-10-30).
- **ID-Q10, decided:** an edit addressed by an `identifier` that two stored records share lands on the record
  the P4 pick names. A delete addressed that way reaches every record sharing it, as API v3 DELETE does today.
- **Unique index, decided 2026-10-30:** in 16.0.0 behind `WRITE_IDENTIFIER_INDEX=try|require|off` (default `try`).
  - `try`: build a partial unique index per collection (records with an `identifier`, soft-deleted included,
    built online). On existing duplicates, log counts and show them on the status page, then run without the
    index; the ID-Q5 write rule still blocks new duplicates.
  - `require`: refuse to start without the index.
  - `off`: skip it.
  - An operator-run tool reports duplicate groups and resolves them by the P4 pick.
- **Settings, proposed by session -4f and confirmed by the maintainer (2026-10-29). They follow `WRITE_VALIDATION`:
  a `WRITE_` prefix, and modes rather than booleans, with the default first:
  - `WRITE_RESEND=merge|acknowledge|refuse`;
  - `WRITE_IDENTIFIER=lenient|strict`;
  - `WRITE_DELETED_EDIT=ignore|refuse`.

  All four, `WRITE_VALIDATION` included, are parsed by one module and read once, and an unknown value refuses to
  start. Per-client D20 quirks select a `WRITE_RESEND` mode for one registered client. Under multitenancy they
  are policy rows (D22), a question for the tenant-config schema.

## 7. How this was produced

- Inputs: the pin and `-uuidoff` pin (alignment `2258c458c`, branch `qc/matrix-idfirst`), the harness at the
  same commit, session -4f's fact tables, the ID-FIRST-MATCH census (read-derived; where it disagrees with the
  pin, the pin is used: v1 profile after a soft delete stores a second record, `profile v1 idf-softdel-plain`
  `n=2`; API v3 create after a soft delete revives except on devicestatus, `devicestatus v3 idf-softdel-plain`
  `n=1 OID:inv`; the split target is deterministic, A on v1 and B on v3). Code: crm `e8224807` for the step,
  the socket, API v3 and the gate. #8877 at `ac5d77fb` for the similar match's identity rule.
- The classification is `tools/qc/idfirst/classify.py <pin.json> [M|K]` (option M or K for socket treatments),
  and the appendix is `tools/qc/idfirst/render.py <out-M> <out-K> <out-uuidoff-M> <appendix.md>` over its outputs
  for the pin, option K and the `-uuidoff` pin. Nothing was run against a server, and no prediction here is measured.
