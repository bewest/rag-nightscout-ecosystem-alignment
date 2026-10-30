# ID-BATCH: per-item results in API v1 batch replies

*Contributor-facing design note for ID-BATCH (queue `ID-BATCH-RESULTS`, plan §4.2 row ID-BATCH), written
2026-10-30. Design only: no `cgm-remote-monitor` code was changed or run for it.* Every claim carries a
mark: **[M]** measured, with the cell id of the write-contract matrix pin
[`dev-e1f7ac41-idfirst.json`](../../../tools/qc/results/write-contract-matrix/dev-e1f7ac41-idfirst.json)
(1,929 cells) or of its [`-uuidoff`](../../../tools/qc/results/write-contract-matrix/dev-e1f7ac41-idfirst-uuidoff.json)
companion (504 cells); **[R]** read from source. Server `file:line` is at crm `9919f8ef` (the #8874 head,
`write(intent)` release 1) unless another revision is named. Client `file:line` is at the revision named in
§2. Read-derived claims about clients are often wrong in this project; each one is a candidate for a
replay cell before it is relied on.

`wi` is `lib/storage/write-intent.js`, `ws` is `lib/server/websocket.js`, `wv` is
`lib/server/write-validation.js`, `wp` is `lib/api/shared/write-payload.js`.

**Headline.** The step already answers one result per item (`WriteResult.items[]`, wi:1594-1599), but no
API v1 route builds its reply from it: each route answers with the submitted objects as the step mutated
them [R]. One route, v1 treatments under `WRITE_VALIDATION=reject`, already keeps one slot per submitted
item with a `refused` member and a `Warning: 299` header (crm `6e842c07`, on `dev` since 2026-10-25) [R].
ID-BATCH generalises that shape to every v1 collection and every per-item outcome. It keeps HTTP 200 and an
array with exactly one slot per submitted item, because Loop's NightscoutKit fails any other status or
length (§2). Full outcomes are opt-in. No matrix cell sends a batch of more than one item [M], so every
batch behaviour below is read, and the first deliverable is the batch cells of §4.

---

## 0. Inputs and decisions this note builds on

- Plan §4.2 row ID-BATCH: "per-item results in v1 batch replies", needs WC-STEP-PATCH, "one bad item no
  longer refuses the batch". Plan §1a row 9 orders it last: "ID-FIRST-MATCH slices …, then ID-UNIQUE-INDEX
  (`WRITE_IDENTIFIER_INDEX`), then ID-BATCH". ROADMAP rows `ID-BATCH-RESULTS` (:188) and `ID-UNIQUE-INDEX`
  (:206, "retry-as-update on duplicate key", depends on `ID-BATCH-RESULTS`) state the opposite dependency;
  open question (i).
- Release allocation :213: WC-STEP-PATCH and ID-BATCH are ladder question 10 (reply shape), minor-class.
- Write-contract spec §2.2: `WriteResult.items: [{ index, outcome, _id, identifier, reason }]`, outcomes
  `inserted | merged | replaced | unchanged | deleted | not-found | refused`; §2.3 applies the rules per item.
  D20 rule 5: every write reply names both `_id` and `identifier`.
- ID-FIRST-MATCH §6a: ID-Q6 (a placeholder or over-length identifier is treated as absent, with a warning;
  strict refusal behind `WRITE_IDENTIFIER=strict`); ID-Q3 (`WRITE_DELETED_EDIT=ignore`: an edit of a deleted
  record is answered 2xx and not applied); ID-Q5 and the unique-index decision (`WRITE_IDENTIFIER_INDEX=try`
  default); `WRITE_RESEND=merge|acknowledge|refuse`. Its §4 item 8 names this note's unit tests.

## 1. Today, per collection

Every v1 array POST first passes `wp.normalize`: more than 10,000 items, or any item that is not an object,
refuses the whole request with 400 (wp:6, wp:24-40) [R]. Treatments do not call it (below).

| collection | write and order | reply body | one invalid item | repeat in the batch | re-send of a stored record | storage error mid-batch |
|---|---|---|---|---|---|---|
| treatments | one ordered `bulkUpsert` replace per item (wi:1736-1755); items with `preBolus` go one by one (`lib/server/treatments.js:107-120`) | the submitted objects with `_id` set (treatments.js:146); `refused` slots spliced in at their index (:76-82) | `WRITE_VALIDATION=reject`: slot = item without `_id`, plus `refused: { status: 400, message, rules }` (wv:200-210), and `Warning: 299 - "k of n treatments refused…"` (`lib/api/treatments/index.js:152-156`); every item refused: 400 (treatments.js:60-64). A non-string `identifier`/`eventType`: whole 500 via `TypeError` (:31-37, :65-67; route :145-147) | the second item's target is the same filter; the ordered bulk lets it match the first's upsert [R] | slot gets the stored `_id` (wi:1829-1858, BF-165); item outcome is `replaced` for every match (wi:1768-1770) | whole 500 `Mongo Error` (api :145-147); items before it stay stored (ordered) [R] |
| entries | one ordered `bulkUpsert` merge (wi:672) | submitted objects with `_id` (`lib/server/entries.js:157`), through `obscure_device` (`lib/api/entries/index.js:805`) | a non-string `type`: whole error (entries.js:117-121) → 500 (api :206-211) | the second takes the first's `_id` (tests `api.entries.repost-with-id.test.js:207`) [R] | stored `_id` (wi:608-654) | whole 500; earlier stored [R]; identity ref §2.1 "a batch whose 2nd item collides: 500; item 1 stored, items 2 and 3 not" [M, its own pin] |
| devicestatus | identifier rule, `_id` rule, then one **unordered** `insertMany` (wi:802-833) | submitted objects with `_id` (`lib/server/devicestatus.js:97-109`) | a non-hex `_id`: whole 400 (`lib/api/devicestatus/index.js:164-169`) | stored once; the repeat gets the first's `_id`, item outcome `refused` "repeated in the batch" (wi:732-751, :842-851) | stored `_id`, not written, item `refused` "already stored" (wi:741-744, :849) | an E11000 on a sent `_id` is the race and is absorbed per item (wi:823-831); any other: whole 500 (api :172-173) |
| profile | classify, ordered `insertMany` of the new, then a merge per re-send (wi:924-976) | submitted objects (`lib/server/profile.js:67`) | a non-hex `_id`: whole 400 (`lib/api/profile/index.js:110-113`) | merged into the first (wi:938-940) | merged / `unchanged`; **one** changing re-send without `api:profile:update` refuses the whole batch with 401, nothing written (wi:950-955; api :130-131) | whole 500 (api :133-134) |
| food | one ordered `bulkUpsert` replace by `_id` (wi:1606-1626) | submitted objects, `_id` from `items[]` (`lib/server/food.js:25-30, :73`) — the only route that reads `items[]` | a non-hex `_id`: whole 400 (`lib/api/food/index.js:59-62`) | same `_id`: second replaces first | `replaced` | whole 500 (api :65-68) |
| activity | as food without dates (wi:1545) | submitted objects (`lib/api/activity/index.js:98-104`) | a non-hex `_id`: whole 400 (:92-95) | as food | as food | whole 500 |

Socket `dbAdd` with an array, for comparison: items run one at a time (ws:610-647). Treatments under
`reject` keep one slot per item (refused, or `failed: { status: 500 }` when the write is unconfirmed,
ws:556-562); every other case concatenates the per-item replies, so a duplicate that answers `[]` removes
its slot and shifts the rest (ws:644-646) [R]. API v3 is one document per request.

Two more facts. A `preBolus` item adds the derived record to the reply (treatments.js:202, `[obj,
pbTreat]`), so the reply is longer than the request [R]. The existing partial-failure tests log rather
than assert (`tests/api.partial-failures.test.js:111-135`, `:550-579`) [R].

**Measured.** Every create cell in both pins sends one item: the harness wraps the body as `[b]` on v1 and
in-process (`tools/qc/write-contract-matrix.js:417`, `:441`) and sends one object on the socket (:434); every
recorded reply array has length 0 or 1 (2,451 recorded `st` and `seed` reply descriptors in the pin, 742 in `-uuidoff`) [M]. **No cell
exercises a batch.** The `dev-991b0654-idfirst.json` pin is not on `main`, so it is not used here.

## 2. What clients do with a v1 batch reply

| client (revision) | arrays to v1 | success status | reply use |
|---|---|---|---|
| Loop: NightscoutKit `4ec9fd1`, NightscoutService (LoopWorkspace `548b332`) | treatments, entries, devicestatus, profile (`NightscoutClient.swift:67, :404, :408, :647, :670`) | **200 only** (:545) | requires an array of exactly the sent count (:488); reads `_id` per slot, and a slot without `_id` becomes `"NA"` and counts as uploaded (:493-503); NightscoutService zips sent `syncIdentifier`s with the ids **by position** (`NightscoutService.swift:207-211`, doses :251-255). Untyped JSON, extra keys ignored. No headers read |
| Trio `0b29cd534` | treatments, entries, overrides (`NightscoutAPI.swift:318, :353, :492`); devicestatus and profile one object | 2xx (:331, :366, :505); profile **200 only** (:438) | body ignored (`let (_, response)`, :328) |
| xDrip+ `1ed760048` | entries, treatments, activity (`NightscoutUploader.java:577, :860, :949`) | 2xx (`isSuccessful`, :579, :864) | body ignored; on 2xx **every queued insert is marked done** (:866-871); reads `Accept-Encoding`/`X-Powered-By` headers only (:1069-1090) |
| xdripswift `c268542e` | entries, treatments (`NightscoutSyncManager.swift:1541, :1789`) | 2xx (:1692), plus a 500 with code 66 as success (:1696-1708) | treatments: reply must be an array (`TreatmentNSResponse.swift:157`); slots matched to local records **by content** (`created_at`, `eventType`, value, notes; ~:170), then `_id` stored (SyncManager :2119); an unmatched record is re-sent later. Entries: ignored |
| nightscout-connect `04102f9` | entries, treatments, devicestatus, profile (`lib/outputs/nightscout.js:63, :109, :161, :222`) | 2xx (axios default) | entries, treatments, profile: the sync bookmark is the newest `dateString`/`created_at` **in the reply** (:236-253, :282-284); a non-array reply leaves it unmoved. Devicestatus uses the sent data (:165-170) |
| AndroidAPS `7e1d537d49` | none found: API v3 single documents (`core/nssdk/.../NightscoutApi.kt:128-129, :161, :178, :195, :238`); no `api/v1` writer or `dbAdd` outside tests | — | not a v1-batch client |
| tconnectsync `7c4b2f4` | none: one object per request (`tconnectsync/nightscout.py:47-54`) | **200 only** (:53) | ignored |

Other entries-array uploaders, read only for status: share2nightscout-bridge `518c85c` (no check,
`index.js:353-355`), minimed-connect-to-nightscout `57bb042` (200 only, `nightscout.js:23`),
nightscout-librelink-up `bff2317` (200 only, `src/nightscout/apiv1.ts:50`). Not examined: LoopFollow,
LoopCaregiver, DiaBLE, xdrip-js, cgmsim-lib callers.

Uncertainty notes. The NightscoutKit pin inside LoopWorkspace was not checked against the standalone
checkout. Loop builds the zipped list from `created` while the upload passes through `compactMap`
(`Extensions/NightscoutUploader.swift:20, :128`); if an item is dropped there, positions shift. That is
inferred, not run. nightscout-connect's Glooko source sets `preBolus` (`lib/sources/glooko/convert.js:58`),
so its treatment reply can contain a derived record at a later `created_at`; whether that moves the
bookmark past unsent data was not traced. No corpus client sends `preBolus` otherwise.

What follows from this [R]:
- **Status.** 207 or 201 fails Loop, Trio profile, tconnectsync, minimed-connect and librelink-up; a 4xx
  fails everyone and Loop's queue retries the whole batch. Only 200 is safe for every client.
- **Body.** It must stay an array with one slot per submitted item, in order (Loop), whose slots echo
  `created_at`/`dateString` and the treatment fields (nightscout-connect, xdripswift). Extra members on a
  slot are ignored by every decoder surveyed.
- **A slot without `_id` is final for Loop** ("NA", treated as uploaded), and every status-only client
  (Trio arrays, xDrip+) treats a 200 as all items uploaded. So a per-item refusal inside a 200 is never
  retried by them. That is right for a refusal that a retry cannot fix, and wrong for a transient failure.

## 3. The proposed rule

**R1. One slot per submitted item, in order, on every v1 array write** (POST of treatments, entries,
devicestatus, profile, food, activity; PUT of food and profile, which take arrays). Each route builds its
reply from `WriteResult.items[]` by `index` instead of from the mutated input. The reply's length equals
the number of items submitted. A derived record (`preBolus`) is not given a slot of its own; open
question (iv).

**R2. Slot content, by outcome.**

| item outcome | slot | counted in `Warning` |
|---|---|---|
| `inserted`, `merged`, `replaced`, `unchanged` | the record as stored, with `_id` and `identifier` (D20 rule 5) | no |
| acknowledged, stays deleted (ID-FIRST-MATCH slice 3); deleted-record edit under `WRITE_DELETED_EDIT=ignore` (ID-Q3) | the stored record's `_id` and `identifier` and the item's own fields; nothing written | yes, "acknowledged, not applied" |
| ID-Q6 lenient: identifier treated as absent | the outcome of the remaining keys, as above, with `identifier: null` | yes, "identifier ignored" |
| `refused`, final (domain rule, `_id` form, `WRITE_IDENTIFIER=strict`, `WRITE_DELETED_EDIT=refuse` with `status: 410`, profile update permission) | the item as sent, no `_id`, and `refused: { status, message, rules? }` (today's `wv.refusal`, generalised beyond Temporary Targets) | yes |

The whole-batch refusals of §1 become per-item: one non-hex `_id` on devicestatus, profile, food or
activity, one non-string `identifier` or `type`, and profile's update permission (which today refuses the
whole batch "so a refused mixed batch cannot partially write", api profile :120-122; open question (iii)).
`wp.normalize`'s size limit stays whole-request.

**R3. Status.** 200 when at least one item is not `refused`. 400 when every item is refused (today's
treatments rule), with the per-item slots in the body. Not 207: it breaks Loop and three entries
uploaders (§2). Not 4xx for a partial result: Loop would re-send the whole batch without limit.

**R4. Transient failures stay whole-request.** A storage error the step cannot attribute and resolve, or a
write it cannot confirm, answers 5xx as today, never as a refused slot, because a refused slot is final
for Loop and status-only clients. The client's retry of the whole batch is safe where re-send matching
reaches the items (identifier, `_id`, entries `sysTime`+`type`); devicestatus, food and activity items with
no identity are stored twice (identity reference §2.7). The ordered writes keep items before the failure
stored, as today.

**R5. Duplicate key mid-batch (ID-UNIQUE-INDEX).** With the index built, an E11000 on `identifier` for
item *k* is a re-send that raced the lookup. The step re-reads the record by that identifier, re-plans
item *k* as a matched re-send under `WRITE_RESEND` (merge, acknowledge or refuse), writes it, and then
re-plans and writes items *k+1…n*, because an ordered bulk write stops at the first error. The slot shows
the matched outcome, as for any re-send. Retry once; a second E11000 on the same item is R4. Devicestatus
already absorbs an E11000 on a sent `_id` this way (wi:823-831). An E11000 on `_id` (an entry re-sent
under a used `_id` at another time) is a final refusal, `refused: { status: 409 }`; open question (v).
Under `WRITE_IDENTIFIER_INDEX=try` with no index built, the race stores a second record, as today.

**R6. Summary and full results.**
- A `Warning: 299 - "<counts>"` header whenever any slot is not applied as sent, extending
  `lib/api/treatments/index.js:152-156` (for example `"2 of 40 items refused, 1 identifier ignored"`). No
  surveyed client reads it, so it is for logs and operators.
- Full `items[]` only on request: a request header (proposed `Nightscout-Write-Results: items`) returns
  `{ "items": [{ index, outcome, _id, identifier, reason, warnings }], "documents": [ …R2 slots… ] }`.
  No surveyed client sends it, so the default reply is unchanged for all of them. Header or query
  parameter: open question (ii).

Options weighed for where per-item outcomes go by default:

| option | breaks a surveyed client? | trade-off |
|---|---|---|
| fields on each slot (`outcome`, `warnings`) | no (every decoder ignores unknown keys) | visible to every client; a client that stores the reply element would store them (none found) |
| header only | no | counts, not positions; no client reads headers |
| opt-in object reply | no | the only full result; needs a client change to use |
| 207 multi-status | yes: Loop, Trio profile, tconnectsync, minimed-connect, librelink-up | the HTTP-standard form |

The rule takes the existing `refused` member, the header and the opt-in object, and adds nothing else to
default slots.

## 4. Cells and tests needed

**New matrix forms** (harness first, pinned on the base before any ID-BATCH change; v1 and in-process for
every collection, socket for comparison). Each records status, reply length, a per-slot descriptor in
order (today's `replyDesc` collapses slots to a set, harness:389-397; it needs an ordered form), the
`Warning` header, and the store.
- `batch-mixed-valid`: valid, invalid, valid. Invalid means a Temporary Target the domain rules refuse
  (run with `WRITE_VALIDATION=reject`), a non-hex `_id` (devicestatus, profile, food, activity), and a
  non-string `identifier`.
- `batch-repeat-identifier`: one new `identifier` twice in a batch; and a batch whose second item re-sends
  a stored one.
- `batch-deleted`: the second item re-sends a soft-deleted record by `identifier` (slice 3 baseline).
- `batch-placeholder-identifier`: `"undefined"` and a 257-character value in the middle (ID-Q6).
- `batch-dupkey-mid`: with the index, a conflicting record inserted between plan and write for item 2,
  extending the harness's read-failure injection (harness:330-333).
- `batch-storage-fail-mid`: an injected write failure on item 2 (R4), the store showing item 1 kept.
- `batch-profile-permission`: a create-only token re-sending a changed profile beside a new one.

**Unit tests.**
- The route builds slots from `items[]` by index, with length equal to the submitted count, for every
  outcome and every collection, including when the step mutates nothing.
- All refused → 400 with slots; one not refused → 200. `Warning` text per kind.
- Opt-in reply shape; absent header → today's array byte-for-byte (G1 for the default).
- R5: one retry, the slot's outcome under each `WRITE_RESEND` mode, the remainder re-planned, the second
  E11000 → 5xx. Ablation: remove the retry; `batch-dupkey-mid` goes red.
- Client-shaped contract tests: NightscoutKit (array, equal count, `_id` string on non-refused slots);
  xdripswift (array, `created_at`/`eventType` echoed); nightscout-connect (`dateString`/`created_at`
  echoed). Turn `tests/api.partial-failures.test.js:111` and `:550` into assertions.

## 5. Where it lands, and what the ID-FIRST-MATCH slices must leave ready

Plan §1a row 9 places ID-BATCH after ID-UNIQUE-INDEX. It needs WC-STEP-PATCH (#8874) for `items[]`, and
the batch cells of §4 pinned first. Changes to make in the ID-FIRST-MATCH slices so ID-BATCH is only a
reply change:
- **Slice 1 (no outcome change):** routes read `items[]` and keep today's bytes. Treatments, entries,
  devicestatus and profile ignore it now (treatments.js:146, entries.js:157, devicestatus.js:109,
  profile.js:67).
- **Slice 2 (`identifier-format`):** an item member for warnings. `item()` has only `reason`
  (wi:1594-1599), and an ignored identifier is not a refusal.
- **Slice 3 (stays deleted):** an outcome word for "acknowledged, not applied". `OUTCOMES` has none
  (wi:54), and devicestatus answers its re-send `refused` "already stored" (wi:849), which R2 would show as
  a refusal. Open question (vi).
- **Slice 4 (merge on match):** the batch forms report `inserted` or the rule's `onMatch` for every match
  (wi:1768-1770, wi:687-690); they need `unchanged` where nothing changed.
- **ID-UNIQUE-INDEX:** the retry of R5 belongs in the step, at the `items[]` level, so it works before
  ID-BATCH changes any reply.

## 6. Open questions

Mechanism and trade-off for each. IDs are allocated by session -49.

(i) **Which lands first: the unique index or ID-BATCH.** Plan row 9 puts the index first; ROADMAP :206
makes it depend on ID-BATCH-RESULTS. Mechanism: with the index and no per-item reporting, a duplicate key
mid-batch is a 500 with earlier items stored, unless the step's retry (R5) lands with the index.
Trade-off: index first with the retry in the step (the reply is unchanged and correct) against ID-BATCH
first (the retry's outcome is visible per item from the start).

(ii) **How a client asks for full results.** A request header, a query parameter (`?results=items`) or an
`Accept` media type. Mechanism: the default array is kept either way. Trade-off: a header survives proxies
and URL logging rules; a query parameter is easier for scripts and shows up in access logs.

(iii) **Profile's update permission per item.** Today one changing re-send without `api:profile:update`
refuses the whole batch, on purpose, so nothing is written (api profile :120-122). Mechanism: R2 makes it a
refused slot, so the new profiles in the batch are stored. Trade-off: a create-only uploader's new
profiles get through, against a partly applied profile set that the uploader may not expect.

(iv) **The `preBolus` derived record in the reply.** Today it is an extra element (treatments.js:202).
Mechanism: R1 gives one slot per submitted item. Trade-off: dropping it from the reply fixes count-checking
clients, but a client that reads the derived record's `_id` from the reply loses it (none found; the
Glooko path of nightscout-connect is the only corpus sender).

(v) **E11000 on `_id`.** A final refusal (409) or a 5xx. Mechanism: an `_id` in use at another time is not
a race, and a retry cannot succeed. Trade-off: a final refusal is silently treated as uploaded by Loop
("NA") and dropped; a 5xx makes Loop retry the whole batch without limit (identity reference §5 rule 4,
"500 and the rest of the batch is lost").

(vi) **The outcome word for "acknowledged".** A new `acknowledged` outcome, or `unchanged` with a reason.
Mechanism: R2 shows it as a stored record and counts it in `Warning`. Trade-off: a new word extends spec
§2.2 and every consumer of `items[]`; reusing `unchanged` hides that the client's change was not applied.
Devicestatus's `refused` "already stored" moves to whichever is chosen.

(vii) **Refusals that status-only clients never see.** Trio's array paths and xDrip+ mark every item
uploaded on 2xx (§2), so a refused treatment is dropped without a client-side trace; Loop does the same
through `"NA"`. Mechanism: R3 keeps 200 for a partial result, as treatments under `reject` do today.
Trade-off: no retry loops and no blocked queues, against a dropped record surfaced only in the server log,
the `Warning` header and the opt-in results. Whether a refused dose or carb entry should also be shown on
the site (an announcement or status-page count) is open.

**Decided elsewhere, carried here (maintainer, 2026-10-30, ID-STRICT-V1).** `WRITE_IDENTIFIER=strict`
refuses an invalid identifier on API v3 and the socket from slice 2 on. On API v1 and in-process it is
enforced with this item's per-item replies; until then those paths treat an invalid identifier as absent,
as under `lenient` (`IDENTIFIER_STRICT` in `lib/storage/write-intent.js`, `'v1/internal': 'absent'`). The
reply-format prototype includes strict on v1 as a case.

## 7. How this was produced

Server code read with `git show 9919f8ef:<path>` from the `crm-wc-step` work tree, nothing checked out.
Client code read at the revisions in §2, with the Loop, Trio, xDrip+, xdripswift and nightscout-connect
lines re-read for this note. Pin facts: the cell counts and reply lengths were computed from the two pin
files on `main` and the harness at `2258c458c`. Nothing was run against a server.
