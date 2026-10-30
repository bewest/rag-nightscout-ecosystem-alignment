# ID-BATCH reply lab: results, 2026-10-30

*Contributor-facing. Synthetic data only. Evidence for the open questions (ii)-(vii) of the
[ID-BATCH design note](../../../docs/30-design/platform/id-batch-design-note-2026-10-30.md); the
maintainer decides them.* Run file: [results/run-2026-10-30.json](results/run-2026-10-30.json); how to
run it: [README.md](README.md).

- **Server:** cgm-remote-monitor `proto/id-batch-replies` at `7d81e1c1` (base `feat/id-first-s5`
  `545f941e`), MongoDB 8.3.9, Node 22.23.4, booted three times: `WRITE_VALIDATION` off, `=reject`, and
  `WRITE_IDENTIFIER=strict`.
- **Clients:** Loop = NightscoutKit `4ec9fd12a1` (the pin LoopWorkspace `548b332451` resolves,
  `Package.resolved:104-109`), NightscoutService `2cef4896f0`, Loop `c30b5c89`; Trio `0b29cd5341`;
  xDrip+ `1ed760048a`; xDrip4iOS `c268542e64`; AndroidAPS `7e1d537d49`; nightscout-connect `04102f9d26`.
- **Method.** Every reply below came from the real server. Loop, Trio, xDrip+ and xDrip4iOS are harnesses
  that reproduce each client's reply handling rule by rule, each rule cited `file:line` in
  [clients.js](clients.js); the client binaries were not run. **nightscout-connect was run**: its own
  Nightscout output module, cycle by cycle ([connect-run.js](connect-run.js)). Each client re-sends what
  its code re-sends, for up to 3 cycles; then MongoDB is read for how many records each item left. Two
  full runs gave identical tables.
- **"Forever"** means: the reply to the re-send is the same every time, and the client's code has no
  attempt counter or age limit on that path.

## Scenarios

| id | server | collection | batch |
|---|---|---|---|
| T-mixed | reject | treatments | `WRITE_VALIDATION=reject`; [carbs, Temporary Target with bottom > top, carbs] |
| T-allrefused | reject | treatments | `WRITE_VALIDATION=reject`; every item refused: [bad TT, bad TT] |
| T-prebolus | off | treatments | [carbs with `preBolus` 15, carbs]; for nightscout-connect, a record 5 min after the first becomes available at cycle 2 |
| T-strict | strict | treatments | `WRITE_IDENTIFIER=strict`; [carbs with a valid identifier, carbs with identifier `"undefined"`, carbs] |
| E-dupid | off | entries | a stored entry holds `_id` X; [sgv, sgv sent with `_id` X at another time, sgv] |
| E-sametime | off | entries | a stored entry at time t holds `_id` X; [sgv, sgv at t sent with another `_id`, sgv] |
| E-strict | strict | entries | `WRITE_IDENTIFIER=strict`; [sgv, sgv with identifier `"null"`, sgv] |
| D-resend | off | devicestatus | a stored devicestatus re-sent with its `_id`, beside a new one (the step answers the re-send `refused` "already stored") |
| D-badid | off | devicestatus | [devicestatus, devicestatus with a non-hex `_id`, devicestatus]: today a whole-batch 400 |

## Reply variants

| variant | opt-in value sent (prototype) | what the client gets |
|---|---|---|
| today | none | today's reply, unchanged |
| slots | `slots` | one slot per submitted item; a refused slot is the item as sent, no `_id`, with `refused`; every item refused: 400 |
| items | `items` | `{ items: [...], documents: [...] }` (a control: what if the object reply were the default) |
| 207 | `slots; status=207` | the slots under 207 (a control known to break clients) |
| prebolus-keep / -omit | `slots; prebolus=keep` / `omit` | the derived record after its item / left out |
| dup-5xx / dup-409 | `slots; duplicate-id=5xx` / `409` | today's 500 / a refused slot with 409 and the other items written |
| ack-refused / -word / -unchanged | `slots; acknowledged=...` | the step's re-send `refused` as a refusal / outcome `acknowledged` / `unchanged` with the reason |

## Per client and variant

Items, one letter each, in batch order: **S** stored once and counted uploaded; **r** stored once, but the
client keeps re-sending it (each re-send is matched, not stored again); **R** not stored, and re-sent;
**L** not stored, and counted uploaded (dropped, no trace on the client); **D** stored twice;
**-** never sent by that client. "1st reply" is status [array length] or {} for a non-array body.

| scenario | reply variant | client | 1st reply | items | marks uploaded | retries | reads `_id` |
|---|---|---|---|---|---|---|---|
| T-mixed | today | loop | 200 [3] | SLS | 3/3 | no | yes: 2 right, 1 "NA" |
| T-mixed | today | trio | 200 [3] | SLS | 3/3 | no | no |
| T-mixed | today | xdripswift | 200 [3] | SRS | 2/3 | yes: every sync while among the latest 50 treatments | yes: 2 right |
| T-mixed | slots | loop | 200 [3] | SLS | 3/3 | no | yes: 2 right, 1 "NA" |
| T-mixed | slots | trio | 200 [3] | SLS | 3/3 | no | no |
| T-mixed | slots | xdripswift | 200 [3] | SRS | 2/3 | yes: every sync while among the latest 50 treatments | yes: 2 right |
| T-mixed | items | loop | 200 {} | rRr | 0/3 | yes: whole batch on every upload trigger, no bound; later records wait behind it | no |
| T-mixed | items | trio | 200 {} | SLS | 3/3 | no | no |
| T-mixed | items | xdripswift | 200 {} | rRr | 0/3 | yes: every sync while among the latest 50 treatments | no |
| T-mixed | 207 | loop | 207 [3] | rRr | 0/3 | yes: whole batch on every upload trigger, no bound; later records wait behind it | no |
| T-mixed | 207 | trio | 207 [3] | SLS | 3/3 | no | no |
| T-mixed | 207 | xdripswift | 207 [3] | SRS | 2/3 | yes: unmatched items on every sync while among the latest 50 | yes: 2 right |
| T-allrefused | today | loop | 400 {} | RR | 0/2 | yes: whole batch on every upload trigger, no bound; later records wait behind it | no |
| T-allrefused | today | trio | 400 {} | RR | 0/2 | yes: whole chunk on every upload pass while within 1 day (carbs), no attempt counter | no |
| T-allrefused | today | xdripswift | 400 {} | RR | 0/2 | yes: every sync while among the latest 50 treatments | no |
| T-allrefused | slots | loop | 400 [2] | RR | 0/2 | yes: whole batch on every upload trigger, no bound; later records wait behind it | no |
| T-allrefused | slots | trio | 400 [2] | RR | 0/2 | yes: whole chunk on every upload pass while within 1 day (carbs), no attempt counter | no |
| T-allrefused | slots | xdripswift | 400 [2] | RR | 0/2 | yes: every sync while among the latest 50 treatments | no |
| T-prebolus | today | loop | 200 [3] | rr | 0/2 | yes: whole batch on every upload trigger, no bound; later records wait behind it | no |
| T-prebolus | today | trio | 200 [3] | SS | 2/2 | no | no |
| T-prebolus | today | xdripswift | 200 [3] | rS | 1/2 | yes: unmatched items on every sync while among the latest 50 | yes: 1 right |
| T-prebolus | prebolus-keep | loop | 200 [3] | rr | 0/2 | yes: whole batch on every upload trigger, no bound; later records wait behind it | no |
| T-prebolus | prebolus-keep | trio | 200 [3] | SS | 2/2 | no | no |
| T-prebolus | prebolus-keep | xdripswift | 200 [3] | rS | 1/2 | yes: unmatched items on every sync while among the latest 50 | yes: 1 right |
| T-prebolus | prebolus-omit | loop | 200 [2] | SS | 2/2 | no | yes: 2 right |
| T-prebolus | prebolus-omit | trio | 200 [2] | SS | 2/2 | no | no |
| T-prebolus | prebolus-omit | xdripswift | 200 [2] | rS | 1/2 | yes: unmatched items on every sync while among the latest 50 | yes: 1 right |
| T-strict | today | loop | 200 [3] | SSS | 3/3 | no | yes: 3 right |
| T-strict | today | trio | 200 [3] | SSS | 3/3 | no | no |
| T-strict | today | xdripswift | 200 [3] | SSS | 3/3 | no | yes: 3 right |
| T-strict | slots | loop | 200 [3] | SLS | 3/3 | no | yes: 2 right, 1 "NA" |
| T-strict | slots | trio | 200 [3] | SLS | 3/3 | no | no |
| T-strict | slots | xdripswift | 200 [3] | SRS | 2/3 | yes: every sync while among the latest 50 treatments | yes: 2 right |
| E-dupid | today | loop | 500 {} code 11000 | rRR | 0/3 | yes: whole batch on every upload trigger, no bound; later records wait behind it | no |
| E-dupid | today | trio | 500 {} code 11000 | rRR | 0/3 | yes: whole chunk on every upload pass while within 1 day (carbs), no attempt counter | no |
| E-dupid | today | xdripplus | 500 {} code 11000 | rRR | 0/3 | yes: whole batch on every upload run until the queue entry is 7 days old | no |
| E-dupid | today | xdripswift | 500 {} code 11000 | rRR | 0/3 | yes: from the bookmark on every sync | no |
| E-dupid | dup-5xx | loop | 500 {} code 11000 | rRR | 0/3 | yes: whole batch on every upload trigger, no bound; later records wait behind it | no |
| E-dupid | dup-5xx | trio | 500 {} code 11000 | rRR | 0/3 | yes: whole chunk on every upload pass while within 1 day (carbs), no attempt counter | no |
| E-dupid | dup-5xx | xdripplus | 500 {} code 11000 | rRR | 0/3 | yes: whole batch on every upload run until the queue entry is 7 days old | no |
| E-dupid | dup-5xx | xdripswift | 500 {} code 11000 | rRR | 0/3 | yes: from the bookmark on every sync | no |
| E-dupid | dup-409 | loop | 200 [3] | SLS | 3/3 | no | yes: 2 right, 1 "NA" |
| E-dupid | dup-409 | trio | 200 [3] | SLS | 3/3 | no | no |
| E-dupid | dup-409 | xdripplus | 200 [3] | SLS | 3/3 | no | no |
| E-dupid | dup-409 | xdripswift | 200 [3] | SLS | 3/3 | no | no |
| E-sametime | today | loop | 200 [3] | SSS | 3/3 | no | yes: 3 right |
| E-sametime | today | trio | 200 [3] | SSS | 3/3 | no | no |
| E-sametime | today | xdripplus | 200 [3] | SSS | 3/3 | no | no |
| E-sametime | today | xdripswift | 200 [3] | SSS | 3/3 | no | no |
| E-sametime | dup-5xx | loop | 200 [3] | SSS | 3/3 | no | yes: 3 right |
| E-sametime | dup-5xx | trio | 200 [3] | SSS | 3/3 | no | no |
| E-sametime | dup-5xx | xdripplus | 200 [3] | SSS | 3/3 | no | no |
| E-sametime | dup-5xx | xdripswift | 200 [3] | SSS | 3/3 | no | no |
| E-sametime | dup-409 | loop | 200 [3] | SSS | 3/3 | no | yes: 3 right |
| E-sametime | dup-409 | trio | 200 [3] | SSS | 3/3 | no | no |
| E-sametime | dup-409 | xdripplus | 200 [3] | SSS | 3/3 | no | no |
| E-sametime | dup-409 | xdripswift | 200 [3] | SSS | 3/3 | no | no |
| E-strict | today | loop | 200 [3] | SSS | 3/3 | no | yes: 3 right |
| E-strict | today | trio | 200 [3] | SSS | 3/3 | no | no |
| E-strict | today | xdripplus | 200 [3] | SSS | 3/3 | no | no |
| E-strict | today | xdripswift | 200 [3] | SSS | 3/3 | no | no |
| E-strict | slots | loop | 200 [3] | SLS | 3/3 | no | yes: 2 right, 1 "NA" |
| E-strict | slots | trio | 200 [3] | SLS | 3/3 | no | no |
| E-strict | slots | xdripplus | 200 [3] | SLS | 3/3 | no | no |
| E-strict | slots | xdripswift | 200 [3] | SLS | 3/3 | no | no |
| D-resend | today | loop | 200 [2] | SS | 2/2 | no | yes: 2 right |
| D-resend | ack-refused | loop | 200 [2] | SS | 2/2 | no | yes: 1 right, 1 "NA" |
| D-resend | ack-word | loop | 200 [2] | SS | 2/2 | no | yes: 2 right |
| D-resend | ack-unchanged | loop | 200 [2] | SS | 2/2 | no | yes: 2 right |
| D-badid | today | loop | 400 {} | RRR | 0/3 | yes: whole batch on every upload trigger, no bound; later records wait behind it | no |
| D-badid | slots | loop | 200 [3] | SLS | 3/3 | no | yes: 2 right, 1 "NA" |

Not a v1 batch client on these paths:
- xdripplus: treatments are PUT one object at a time (NightscoutUploader.java:803-806, :880-889) (T-mixed, T-allrefused, T-prebolus, T-strict, D-resend, D-badid)
- aaps: API v3, one document per request (NightscoutApi.kt:127-130, :160-163) (T-mixed, T-allrefused, T-prebolus, T-strict, E-dupid, E-sametime, E-strict, D-resend, D-badid)
- trio: does not post devicestatus as a v1 array (D-resend, D-badid)
- xdripswift: does not post devicestatus as a v1 array (D-resend, D-badid)

### nightscout-connect, run for real

| scenario | reply variant | posts per cycle (status [length]) | items (sent x times) | items |
|---|---|---|---|---|
| T-mixed | today | 200 [3] / - / - | x1 stored; x1 not stored; x1 stored | SLS |
| T-mixed | slots | 200 [3] / - / - | x1 stored; x1 not stored; x1 stored | SLS |
| T-mixed | 207 | 207 [3] / - / - | x1 stored; x1 not stored; x1 stored | SLS |
| T-allrefused | today | 400 / 400 / 400 | x3 not stored; x3 not stored | RR |
| T-allrefused | slots | 400 / 400 / 400 | x3 not stored; x3 not stored | RR |
| T-prebolus | today | 200 [3] / - / - | x1 stored; x1 stored; late:x0 not stored | SSL |
| T-prebolus | prebolus-keep | 200 [3] / - / - | x1 stored; x1 stored; late:x0 not stored | SSL |
| T-prebolus | prebolus-omit | 200 [2] / 200 [1] / - | x1 stored; x1 stored; late:x1 stored | SSS |
| T-strict | today | 200 [3] / - / - | x1 stored; x1 stored; x1 stored | SSS |
| T-strict | slots | 200 [3] / - / - | x1 stored; x1 not stored; x1 stored | SLS |
| E-dupid | today | 500 / 500 / 500 | x3 stored; x3 not stored; x3 not stored | rRR |
| E-dupid | dup-5xx | 500 / 500 / 500 | x3 stored; x3 not stored; x3 not stored | rRR |
| E-dupid | dup-409 | 200 [3] / - / - | x1 stored; x1 not stored; x1 stored | SLS |
| E-sametime | today | 200 [2] / - / - | x1 stored; x0 not stored; x1 stored | S-S |
| E-sametime | dup-5xx | 200 [2] / - / - | x1 stored; x0 not stored; x1 stored | S-S |
| E-sametime | dup-409 | 200 [2] / - / - | x1 stored; x0 not stored; x1 stored | S-S |
| E-strict | today | 200 [3] / - / - | x1 stored; x1 stored; x1 stored | SSS |
| E-strict | slots | 200 [3] / - / - | x1 stored; x1 not stored; x1 stored | SLS |
| D-resend | today | 200 [1] / - / - | x0 stored; x1 stored | -S |
| D-resend | ack-refused | 200 [1] / - / - | x0 stored; x1 stored | -S |
| D-resend | ack-word | 200 [1] / - / - | x0 stored; x1 stored | -S |
| D-resend | ack-unchanged | 200 [1] / - / - | x0 stored; x1 stored | -S |
| D-badid | today | 400 / 400 / 400 | x3 not stored; x3 not stored; x3 not stored | RRR |
| D-badid | slots | 200 [3] / - / - | x1 stored; x1 not stored; x1 stored | SLS |

### Opt-in forms, open question (ii)

| form | status | content type | reply | Warning | first item stored | query string in the server log |
|---|---|---|---|---|---|---|
| none | 200 | `application/json; charset=utf-8` | array[2] | `299 - "1 of 2 treatments refused by WRITE_VALIDATION; see the refused member of each"` | 1 | no |
| header | 200 | `application/json; charset=utf-8` | object{items[2],documents} | `299 - "1 of 2 items refused"` | 1 | no |
| query | 200 | `application/json; charset=utf-8` | object{items[2],documents} | `299 - "1 of 2 items refused"` | 1 | no |
| accept | 200 | `application/json; charset=utf-8` | array[2] | `299 - "1 of 2 treatments refused by WRITE_VALIDATION; see the refused member of each"` | 1 | no |
| accept-no-suffix-path | 200 | `application/vnd.nightscout.write-results+json; charset=utf-8` | object{items[2],documents} | `299 - "1 of 2 items refused"` | 1 | no |
| accept-with-json-too | 200 | `application/json; charset=utf-8` | array[2] | `299 - "1 of 2 treatments refused by WRITE_VALIDATION; see the refused member of each"` | 1 | no |
| header-no-suffix-path | 200 | `application/json; charset=utf-8` | object{items[2],documents} | `299 - "1 of 2 items refused"` | 1 | no |
| header-malformed | 400 | `application/json; charset=utf-8` | object | - | 0 | no |

### Profile update permission, open question (iii)

| variant | status | slots | changed re-send applied | new profile stored |
|---|---|---|---|---|
| today | 401 | `Missing permission api:profile:update` | no | 0 |
| whole | 401 | `Missing permission api:profile:update` | no | 0 |
| per-item | 200 | refused 403, _id | no | 1 |

Notes on rows that are not live cases: Loop, Trio and xDrip4iOS do not send `preBolus` (the T-prebolus
rows show what a count-checking or content-matching client would do); xDrip4iOS sends no Temporary
Targets. In E-sametime, nightscout-connect's own bookmark is past the seeded time, so it never sends item 1.

## Findings, by open question

### (ii) How a client asks: header, query parameter or Accept

- Header and query parameter gave the same reply on every path measured, with and without the `.json`
  suffix. cgm-remote-monitor writes no access log, so neither shows in the server's own output; a query
  parameter would show in a proxy's or host's request log, which the lab does not have.
- **An Accept opt-in never reaches the route on a `.json` path.**
  `lib/middleware/express-extension-to-accept.js:30-36` replaces `Accept` with the extension's type before
  routing. On `/api/v1/treatments.json` the vendor type is dropped silently and the client gets today's
  array; on `/api/v1/treatments/` it works and the reply carries the vendor content type. Trio
  (`NightscoutAPI.swift:15-16`) and nightscout-connect (`lib/outputs/nightscout.js:63, :109, :161, :222`)
  post to `.json` paths; Loop (`NightscoutClient.swift:13-17`), xDrip4iOS
  (`NightscoutSyncManager.swift:54, :58`) and xDrip+ (`NightscoutUploader.java:130, :145`) do not. An Accept
  form would need the route to read the original header (`req.extToAccept.accept`).
- NightscoutKit already sets `Accept: application/json` on every call (`NightscoutClient.swift:523`), so
  Accept is the one form that shares a field with a header a client already sends.
- The prototype answers a malformed opt-in with 400 before writing. A client that sets the opt-in once
  and gets it wrong would fail every upload in either form.

### (iii) Profile's update permission per item

Server side only (not run through the client harnesses):

- Today and `profile=whole`: 401, nothing written; the new profile in the same batch is not stored.
- `profile=per-item`: 200; the changing re-send has a refused slot (403), the new profile is stored.
- For Loop, the one surveyed client posting profile arrays (`NightscoutClient.swift:398-408`), the 401 is a
  failure re-tried on every trigger, forever; the per-item 200 is a success, and the refused change is
  recorded as `"NA"` and not re-tried.

### (iv) The preBolus derived record in the reply

- Today (the same as `prebolus=keep`) the reply has one element more than the request. A count-checking
  client (Loop, `NightscoutClient.swift:488-491`) fails it and re-sends the whole batch forever, with later
  records waiting; each re-send is matched on the server, so nothing is stored twice (`rr`).
- **nightscout-connect, run: the derived record's later `created_at` moves the treatments bookmark past
  records not yet sent.** A record 5 minutes after the preBolus item, available at the next cycle, is never
  sent (`SSL` today and with `keep`; `SSS` with `omit`). nightscout-connect takes the bookmark from the
  newest `created_at` in the reply (`lib/outputs/nightscout.js:247-253`, `:282`). Its Glooko source sets
  `preBolus` (`lib/sources/glooko/convert.js:58`), so this is a live path.
- `prebolus=omit` removes both effects. No surveyed client reads the derived record's `_id`.

### (v) E11000 on a sent `_id`: 409 or 5xx

- Today and `duplicate-id=5xx`: 500 (`description.code` 11000). The ordered write keeps item 0 and stops
  there. Every client re-sends the whole batch: Loop forever, later records waiting; Trio while within a
  day; xDrip+ until the queue entry is 7 days old; xDrip4iOS from its bookmark on every sync;
  nightscout-connect on every cycle. **Item 2, a valid record, is never stored by any of them** (`rRR`).
- `duplicate-id=409`: 200; item 1 refused with 409, items 0 and 2 stored. Every client counts item 1
  uploaded (`SLS`): Loop as `"NA"`, the others by status.
- The 409 variant writes the batch's other items in a further call from the route. Landing it means R5's
  continuation in the step.
- Senders: xDrip4iOS sends `_id` on calibration entries (`Calibration+Nightscout.swift:17, :36`). An entry
  at a stored entry's time under another `_id` (E-sametime) does not fail on this base: the step matches
  it by time and type and answers the stored `_id`, so xDrip4iOS's "500 with code 66 is success" path
  (`NightscoutSyncManager.swift:1692-1708`) is not reached.

### (vi) `acknowledged`, or `unchanged` with a reason

- On this base the case is a devicestatus re-sent with its stored `_id`, which the step answers `refused`
  "already stored" (`lib/storage/write-intent.js:1121-1125`).
- Kept as a refusal (`ack-refused`): the slot loses `_id` and Loop records `"NA"` for a record that is
  stored. Nothing is lost (Loop caches no devicestatus ids), but the reply misstates the outcome.
- **A re-send on its own is then an all-refused batch: 400.** The red control below measured it: with the
  slots shape on by default, 17 devicestatus re-send cells go from `200 [1 _id]` to `400 [1 no _id]`
  (for example `devicestatus v1 resend-hex`). Loop would re-send that devicestatus forever. So keeping the step's `refused` word
  for a re-send makes R3's "every item refused: 400" fire on a record that is stored.
- `word` and `unchanged`: the slot keeps the stored `_id`, byte-identical for every client; they differ
  only in `items[].outcome`. No surveyed client reads `items[]`, so the choice has no client-visible effect
  today; it decides what a future reader of `items[]` can tell apart (a change not applied, against
  nothing to change).
- nightscout-connect never re-sends a stored devicestatus: its own bookmark filter drops it first
  (`lib/outputs/nightscout.js:117-160`).

### (vii) Refusals that status-only clients never see

Under `WRITE_VALIDATION=reject` (T-mixed) and under strict-on-v1 (T-strict, E-strict), a refused item in a
200:

| client | refused item counted uploaded? | trace on the client |
|---|---|---|
| Loop | yes, as `"NA"` (`NightscoutClient.swift:493-503`) | none; later edits and deletes of that record are skipped too, because `"NA"` is never sent (`:83`, `:112`, `:140`) |
| Trio | yes: 2xx marks the chunk (`NightscoutManager.swift:1096-1110`; Temporary Targets `:1258-1275`) | none. Trio sends Temporary Targets, so this is the live case for `reject` |
| xDrip+ | entries: yes, by status. Treatments are not batched | none |
| xDrip4iOS | **no**: the slot has no `_id`, matches nothing, and the item is re-sent on every sync while among the latest 50 treatments. Re-sent alone it is an all-refused batch and gets 400 | the item never completes |
| nightscout-connect (run) | yes: the refused slot echoes `created_at`, and the bookmark passes it | none |

- Every item refused (T-allrefused; D-badid today): 400; every client re-sends forever or until its window
  closes. Nothing is lost and nothing is stored.
- A refused slot is final for every client except xDrip4iOS: right for a refusal a retry cannot fix, and a
  dropped record with no trace on the client.

### Strict on v1 (ID-STRICT-V1)

- Today strict on v1 treats the invalid identifier as absent: the record is stored without it (`SSS`).
- With per-item replies strict refuses the record: every client except xDrip4iOS drops it (`SLS`). The
  refusal is about an identifier the client chose, and what is lost is the record's data (carbs, a glucose
  value).

### The shapes as a default

- `items` (the object reply) as a default breaks Loop (not an array) and xDrip4iOS (counted failed): both
  re-send forever. Safe only as an opt-in.
- `207` breaks Loop (not 200): forever. Trio, xDrip4iOS and nightscout-connect accept it.
- `slots` as a default gives the same client outcomes as today's treatments-under-`reject` reply in every
  measured case, and turns devicestatus's whole-batch 400 for one bad `_id` (D-badid today: forever, for
  Loop and nightscout-connect) into one refused slot.

## Corrections to the design note's §2

- xDrip+ treatments are not a v1 batch: inserts go into the upsert list ("always use singular upserts",
  `NightscoutUploader.java:803-806`) and are PUT one object at a time (`:880-889`); the POST of
  `insert_array` (`:859-863`) is never reached.
- The NightscoutKit pin inside LoopWorkspace is the standalone checkout (`Package.resolved:104-109`
  names `4ec9fd12a1`).
- Loop's retry has no bound: the query anchor moves only on success
  (`RemoteDataServicesManager.swift:278-287`), and a failed type is re-tried on every later trigger
  (`:182-183`).
- nightscout-connect's preBolus uncertainty is resolved: the derived record does move the bookmark past
  unsent data (iv).

## Prototype checks

- **Default replies unchanged.** The write-contract matrix (`tools/qc/write-contract-matrix.js`, the frozen
  copy that made the pin) on the prototype, against the ID-FIRST-MATCH slice 5 pin
  `dev-7c7532f7-idf-s5.json`: 4,604 cells in each, **0 moved** apart from `cache`/`wire`; 88 differ only
  in `cache`/`wire`, which are racy by design.
- **Red control.** With the opt-in on by default (`DEFAULT_REQUEST = { shape: 'slots' }`), the matrix on
  the v1 paths moved **30 of 503** cells (23 devicestatus, 7 profile). In 17 devicestatus cells a lone
  re-send of a stored record went from `200 [1 _id]` to `400 [1 no _id]`; in the rest a whole-batch 400
  (a non-hex or placeholder `_id`) kept its status and its body became the slots array. 4 of the
  prototype's 22 tests failed: the four that pin today's reply where the prototype differs (the preBolus
  pin did not, because `prebolus=keep` is today's reply). Reverted.
- `npm test`, serially, on `7d81e1c1`: 5,412 passing, 3 pending, 0 failing.
  `node scripts/test-tiers.js check` (421 files, ok) and `node scripts/check-write-intent.js` (G2) pass.
  `lib/storage/write-intent.js` is unchanged from the base.

## Limits

- The Loop, Trio, xDrip+ and xDrip4iOS rows are reproductions of the cited code, not runs of the apps.
- Three cycles per run; "forever" is read from the code's retry rule together with a reply that does not
  change between cycles.
- The prototype covers v1 POST of treatments, entries, devicestatus and profile. Food, activity and the
  array PUTs are not in it; xDrip+'s activity upload (status only) is therefore not measured.
- Not examined: LoopFollow, LoopCaregiver, DiaBLE, xdrip-js, tconnectsync (one object per request), and
  the entries-only uploaders listed in the design note.
