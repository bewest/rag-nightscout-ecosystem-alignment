<!-- Draft body for branch bf/same-time-treatments at fc821024 (one commit on dev e3adc91d), 2026-09-26. Not opened. This comment is hidden on GitHub. -->
Two treatments recorded at the same time are no longer stored as one (BF-121, issue #8185). One commit on `dev` `e3adc91d`. This is the design the maintainer chose on 2026-09-26 ("option 3"): identity-aware matching for API v1 and the websocket, and carbs and insulin in the match key for API v1 writes that carry no client identity. API v3 and the websocket's exact match keep their current key, so AndroidAPS behaves as before.

## What changes for you

*A plain-language summary for people who run their own Nightscout site, for themselves or for a family member. Nightscout is not a medical device, and nothing here is medical advice. Nothing here tells you how to dose. If your carb or insulin numbers look wrong, check them against the app that entered them and talk to your care team before you rely on them.*

A few words used below:

- **Treatment**: a saved carb entry, insulin dose, temporary target, note and similar.
- **Back-dated entry**: an entry where you pick the time it happened instead of "now", for example "16 g at 7:40".
- **Careportal**: the form on your Nightscout site for entering treatments.
- **Uploader**: an app that sends treatments to your site, such as Loop, Trio, AndroidAPS, xDrip+ or a pump sync tool.
- **Re-send**: when an uploader sends the same treatment again because it did not hear back the first time. Nightscout must recognise it and not store it twice.

**What was wrong.** When two treatments of the same kind had exactly the same time, Nightscout kept only one of them, with no error. In the report behind this fix, a caregiver sent 16 g and then 4 g of carbs through Loop, both back-dated to 7:40. Nightscout kept only the 4 g. The 16 g disappeared from the chart, the reports and the daily totals, and from what followers saw. The same happened with two careportal entries in the same minute with different amounts, and with a bolus and an extended bolus that a pump sync tool sends in the same second.

The app that entered the carbs (Loop in the report) kept both entries and dosed from its own records. What was lower was what Nightscout stored, showed and totalled, and what anything reading carbs or insulin from Nightscout received.

**What this change does.** Two entries at the same time are now kept apart when anything tells them apart:

- the uploader's own id for each entry (Loop, Trio, xDrip+ and NSClient each send one), or
- for entries that arrive without such an id (the careportal, several pump sync tools), a different carb or insulin amount.

Re-sends still work as before. An uploader that sends the same entry again, or sends an updated version of an entry with the same id (for example Loop or Trio updating a dose while it is still being delivered), still updates the one record. Entries saved before you update are matched the same way.

**What does not change.**

- Two careportal entries in the same minute with the **same** amount are still stored as one. Nothing tells them apart from pressing Save twice.
- Entries uploaded by **AndroidAPS** are matched as before. Two AndroidAPS entries of the same kind in the same millisecond can still be stored as one. This was left alone on purpose, so that an AndroidAPS edit that is re-sent after a lost reply still updates its entry instead of becoming a second copy.

**Do you need to do anything?** No. Entries that were already lost before this update are not brought back. If a past day's carbs or insulin looked too low in Nightscout, the app that entered them still has the full record.

## Technical detail

### The defect

`POST /api/v1/treatments` is an upsert. For a record with no `identifier` and no `_id`, `upsertQueryFor` (`lib/server/treatments.js`) matched on `{created_at, eventType}` alone, so a second entry at the same time replaced the first with `replaceOne` (keeping the first's `_id`). The array form does the same per item in one `bulkWrite`. The websocket `dbAdd` (`lib/server/websocket.js` `processSingleDbAdd`) looked up the same pair (or `NSCLIENT_ID` when sent) and, on a match, returned the stored record and dropped the new one. Its ±2 s "similar" match added `eventType` only when no amount had been matched, so a `Meal Bolus` 1 s after a `Carb Correction` with the same carbs was dropped too. A v1 write could also replace a record created through API v3 at the same time and type, removing its `identifier` and `srvModified`. Identical on `v15.0.8` `92d08342` and `dev` `e3adc91d`.

### What the commit does

New `lib/server/treatment-fallback-key.js` builds the fallback selector, used where the old `{created_at, eventType}` was:

1. **Client identity.** For each of `syncIdentifier` (Loop), `id` (Trio), `uuid` (xDrip+) and `NSCLIENT_ID` the write carries, the stored value must be equal (`$eq`). A write that carries none matches only a record where all four and `identifier` are null or missing. Used by API v1 (`create` single and array, `upsert`, `save`/PUT; the in-process writers call the same storage) and by the websocket `dbAdd` exact match (after its existing `NSCLIENT_ID` branch).
2. **Amounts, API v1 only.** For a v1 write with no client identity, `carbs` and `insulin` must also be equal (`$eq` value, or `$eq null` when absent). `prepareData` runs first, so both are numbers or absent (zero and NaN are dropped), on the stored and the incoming side alike.
3. **Similar match.** The websocket's ±2 s similar match now always includes `eventType`. The now-unused `selected` flag is removed.

Not changed: API v3 (`lib/api3/generic/create/operation.js`, computed identifier from `device + date + eventType`, `dedupFallbackFields`), the websocket exact match's key for a write without identity (no amounts), the preBolus companion record's key, and any path that matches by `identifier` or `_id`.

Every value goes into the selector as `{$eq: value}`, like the fields before it.

### Why amounts are not added on v3 and the socket

Measured with the lab prototype and again here (harness below): adding the amounts on those paths turns an AndroidAPS edit re-sent without its identifier (v3, R16) or after a lost socket ack (R18) into a duplicate. Option 3 keeps today's result for both: R16 updates in place, R18 keeps the first version (stale, as today).

## Tests

`tests/api.same-time-treatments.test.js` (new, 18 tests, real MongoDB, v1 routes through supertest and a real socket):

- **Fail on `dev` `e3adc91d` with the original symptom** (one record stored where two were sent; each failure message read): Loop 16 g + 4 g at one time with different `syncIdentifier`s (`expected [4] to equal [16, 4]`); the same in one array POST; two careportal entries in one minute with 20 g and 15 g (`[15]` vs `[20, 15]`); a 2 U bolus and a 1 U extended bolus in one second, no id (`[1]` vs `[2, 1]`); a v1 write does not replace an API v3 record (`expected 1 to be 2`); a careportal entry and a Loop entry in the same second; socket: same carbs, other `eventType`, 1 s later; socket: two different client `id`s at one time; socket: a write without identity does not land on a v3 record.
- **Pass on both** (the re-sends clients depend on): Loop dose re-POSTed with the same `syncIdentifier` and a new amount updates; Trio pump event re-POSTed with the same `id` and a new amount updates; identical Loop batch and careportal double-submit dedupe; an oref0-shape re-send that differs only in `notes` updates; records stored before the change (careportal without identity, Loop with `syncIdentifier`) match when re-sent; PUT without `_id` and equal amounts updates; two careportal entries with the same amount in one minute stay one record (documented limit); socket re-send with the same `NSCLIENT_ID` and a similar same-type entry dedupe; two socket entries without identity at one time keep the first (documented limit).

`tests/storage.selector-hardening.test.js`: one new test, a client identity in the fallback is wrapped in `$eq` (including `__proto__` and `$where` as values) and adds no null placeholders or amounts.

**Changed expectations** (each marked in the file):

- `tests/storage.selector-hardening.test.js` "wraps treatment identifiers and fallback fields in literal equality": the fallback selector now also carries `syncIdentifier`, `id`, `uuid`, `NSCLIENT_ID`, `identifier` as `{$eq: null}` and `carbs`, `insulin` as `{$eq: null}`.
- `tests/websocket.input-validation.test.js` "literalizes similar-match fields and acknowledges only after its update": the exact-match selector carries the five `{$eq: null}` identity fields, and the similar selector now includes `eventType`.

The v3 contract test "should deduplicate document by created_at+eventType" is unchanged and passes. `tests/api.deduplication.test.js` is unchanged and passes.

### Break-its (each hunk or rule reverted alone, 2026-09-26)

| reverted | turns red |
|---|---|
| `treatments.js` fallback back to `{created_at, eventType}` | 8: the six v1 tests above that fail on dev, both selector-hardening fallback tests |
| websocket exact match back to `{created_at, eventType}` | 3: socket different client ids, socket v3 record, websocket.input-validation similar-match |
| websocket similar match: `eventType` only when no amount matched | 2: socket other `eventType` 1 s later, websocket.input-validation similar-match |
| identity rule removed (client ids not in the key) | 10, including the Loop and Trio in-place updates, stored-before-the-change re-send, and four existing `api.deduplication` tests (syncIdentifier, dose, Trio id, temp target with id) |
| no-identity rule removed (no null placeholders) | 4: v1 and socket do-not-replace-v3, both selector-shape tests |
| amounts removed from the v1 key | 3: careportal 20 g + 15 g, bolus + extended bolus, selector-hardening fallback |

### Full suite

`npm test` on `fc821024`, fresh database: **3189 passing, 0 failing, 3 pending** (Node 22.23.2, MongoDB 7.0.43 read from the server). `dev` `e3adc91d` is 3170/0/3 on the same form; the difference is the 19 new tests.

### Harness (alignment repo, `tools/lab/triage-2026-09/`)

`same-time-carbs.js <tree> <port> <mongo uri>`: `dev` `e3adc91d` exit 1 (v1-single, v1-array, v1-careportal, v3-then-v1, ws-similar collapsed); `fc821024` exit 0, those five store 2, and v3-noid and ws-dbAdd are reported as "known issue (option 3 leaves AAPS paths unchanged)", still 1 record each; `--strict` counts them (exit 1). All four controls store 2 on both.

`same-time-resend-shapes.js <port> <mongo uri> off=<tree> fix=<tree>`, booting each tree's real server (`API_SECRET` set, `AUTH_DEFAULT_ROLES=denied`), every write answered 2xx and the server stayed live:

| shape | client and sequence | dev e3adc91d | this PR |
|---|---|---|---|
| I8185 | Loop: 16 g then 4 g, same time, own `syncIdentifier`s | MERGED (1) | kept 2 |
| R01 | Loop: batch re-POSTed identically after a failure | deduped | deduped |
| R02 | Loop: in-progress dose re-POSTed, same `syncIdentifier`, new amount | updated | updated |
| R03 | Trio: carbs with `id`, identical retry | deduped | deduped |
| R04 | Trio: pump event re-POSTed, same `id`, changed amount | updated | updated |
| R05 | Trio: fat/protein entries sharing one `id` at other times, re-sent | deduped | deduped |
| R06 | Trio: temp target without id, re-sent | deduped | deduped |
| R07 | Trio: temp target without id, re-sent with a changed duration | updated | updated |
| R08 | Trio: suspend / sensor start without id, re-sent | deduped | deduped |
| R09 | xDrip+: PUT with `_id`, re-sent with a new amount | updated | updated |
| R10 | xdripswift: POST `eventTime` in ms, no id, retry | deduped | deduped |
| R11 | careportal: double-submit, minute precision | deduped | deduped |
| R12 | oref0: no identity, re-send differs only in `notes` | updated | updated |
| R13 | tconnectsync: `pump_event_id` only, identical retry | deduped | deduped |
| R14 | nightscout-connect REST output: no identity, identical retry | deduped | deduped |
| R15 | AAPS v3: no identifier or device, identical retry | deduped | deduped |
| R16 | AAPS v3: edit after a lost id (20 g, then 30 g without identifier) | updated | updated |
| R17 | socket `dbAdd`: re-send with the same `NSCLIENT_ID` | deduped | deduped |
| R18 | socket `dbAdd`: edit re-sent after a lost ack, no identity | STALE | STALE (unchanged, known) |
| R19 | Loop: carb edit by PUT with `_id` | updated | updated |
| R20 | record stored before the upgrade (no identity), re-sent after it | deduped | deduped |
| R21 | v1 record edited by v3 PATCH (as AAPS edits), then re-sent through v1 | deduped | deduped |
| D01 | tconnectsync: bolus 2 U + extended 1 U, same second, both `Combo Bolus` | MERGED (1) | kept 2 |
| D02 | AAPS v3: bolus + carbs in the same ms, both `Meal Bolus` | MERGED (1) | MERGED (1) (unchanged, known) |
| D03 | careportal: two entries, same minute, same amount | MERGED (1) | MERGED (1) (indistinguishable) |
| D04 | careportal then Loop entry, same second, same `eventType` | MERGED (1) | kept 2 |
| D05 | careportal: same minute, 20 g and 15 g | MERGED (1) | kept 2 |

The shapes are synthetic records in each client's upload shape, read from the client sources; no client app was run. The same harness against the lab prototype (`BF121_LAB_MODE=safe|full`) reproduces the 2026-09-25 design measurement: `full` makes R16 and R18 duplicates and keeps D01 and D02 apart; `safe` merges D01 and D05.

## Interactions

- **BF-122 (`bf/v1-writes-v3-history` `718efddc`).** A trial merge conflicts in `lib/server/websocket.js` (the `require` lines) and in `tests/websocket.input-validation.test.js` (the exact-match selector: both branches changed it; the resolved expectation carries the identity nulls and `isValid: {$ne: false}`). Resolved, the full suite is 3215/0/3 and the harness table is identical to this PR's column. BF-122's `srvDates.carryForReplace` reads the record the same filter matches, so it carries `identifier` only from a record the new key matches.
- **BF-09 (socket dedup truthiness, awaiting the maintainer).** This commit makes the similar match always key on `eventType`, which is the second half of BF-09's option 3, and removes the `selected` flag BF-09's option 2 lines sit next to. Measured with `tools/remedial/bf3/bf09-dedup-zero.js`: on this commit X1 and X2 (zero temp and a temporary target of the same duration, either order) are kept (both dropped on `dev`); Z2, Z5, P2, B2 and C2 are still dropped by the truthiness tests; with BF-09's `zero-real` patch on top, every case is kept and every control is unchanged. BF-09's choice is left to the maintainer; a BF-09 branch will conflict textually with the similar-match hunk here.
- **BF-136 (`bf/api3-app-field-v1-records` `df6c04bc`).** Merges cleanly. With both, an AndroidAPS v3 POST at the same time and type as a v1 record now succeeds and takes that record over (giving it an `identifier`), and a later identical v1 re-send of the original record no longer matches it: two records (harness rows O1, O2). With a different amount that keeps both entries (BF-136 alone leaves only the v1 amount). With the same amount it is a duplicate. See "Open question".

## Open question

Whether a v1 re-send without identity should still match a v1 record that an API v3 deduplication has taken over. It needs both this PR and BF-136, the same `created_at` and `eventType` from a v1 uploader and AndroidAPS, and a v1 uploader that re-sends old records. No corpus client was found doing all three. It is left to the maintainer.

## Client impact (read from the corpus unless marked run)

- **Loop** (`LoopWorkspace` `f841285`, NightscoutKit `4ec9fd1`): POSTs arrays with `syncIdentifier`, re-POSTs the same batch on failure (`RemoteDataServicesManager.swift:263-343`), re-POSTs an in-progress dose with the same `syncIdentifier` and `created_at` and a new amount (`InsulinDeliveryStore.swift:454-458`), edits by PUT with `_id` (`NightscoutClient.swift:83-88`). All unchanged (R01, R02, R19, run with synthetic records). Two entries in the same second are now two records, which is the fix for #8185. LoopCaregiver's and LoopFollow's workaround of adding seconds to a picked minute keeps working.
- **Trio** (`e41c9db37`): POSTs with `id`; pump events re-POSTed with the same `id` and changed values rely on the upsert (`PumpEvent+helper.swift:130-131`, `NightscoutManager.swift:1082-1093`) and still update in place (R04). Fat/protein entries sharing one `id` at different times are unaffected (R05). Temp targets, suspends and sensor starts carry no id and have no carbs or insulin, so their re-sends match as before (R06-R08).
- **AndroidAPS** (`7e1d537d49`): API v3, unchanged (R15, R16, D02). Its edits are v3 PATCH by identifier, not affected (R21). No websocket `dbAdd` in its current source.
- **xDrip+** (`1ed760048`): PUT with `_id`, unchanged (R09). Its `NSClientChat` hands records to an NSClient app, which writes over the socket with `NSCLIENT_ID` (R17).
- **xdripswift** (`c268542e`): POST without id on create, PUT with `_id` for updates (`NightscoutSyncManager.swift:1918`, `TreatmentEntry+CoreDataClass.swift:185`). Retries dedupe (R10).
- **oref0** (`d219baf9`): POST without identity; re-sends with the same amounts still match (R12).
- **tconnectsync**: POST without an identity Nightscout uses (`pump_event_id` is stored, not matched; `tconnectsync/parser/nightscout.py:50-58`). A bolus and an extended bolus in the same second are now two records (D01); identical retries dedupe (R13).
- **Careportal and bolus wizard**: two entries in the same minute with different amounts are now two records (D05); a double submit is still one (R11, D03). Edits are PUT with `_id`.
- **nightscout-connect**: the in-process output calls the same v1 storage; identical re-fetches dedupe (R14, REST shape run).
- **Nightscout chart drag ("Move carbs/insulin")**: the split record keeps the original's client fields and gets a new time, so it matches nothing at the new time, as before (read).
- **Worse for anyone?** A v1 uploader that sends no client identity and re-sends an entry after a lost reply **with a changed carb or insulin amount** would now get a second record instead of an update. None was found in the corpus: the uploaders that change amounts on re-send (Loop, Trio) send an identity, and the ones without identity re-send the same amounts. Uploaders outside the corpus were not checked.
