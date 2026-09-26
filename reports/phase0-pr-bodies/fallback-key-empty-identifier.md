<!-- Draft body for branch bf/fallback-key-empty-identifier at aaf67785 (one commit on dev ff93fa94), 2026-09-26. This comment is hidden on GitHub. Not opened; not pushed. -->
A treatment re-sent with an empty identity is no longer stored twice (BF-141). One commit (`aaf67785`, on `dev` `ff93fa94`). This is a regression from #8780 (BF-121) that was never released: on `v15.0.8` and on `dev` before #8780 the same record is stored once. Found while reviewing #8778. The maintainer decided on 2026-09-26 to fix it for 15.0.9. API v3 is not changed.

## What changes for you

*A plain-language summary for people who run their own Nightscout site, for themselves or for a family member. Nightscout is not a medical device, and nothing here is medical advice. Nothing here tells you how to dose. If your carb or insulin numbers look wrong, check them against the app that entered them and talk to your care team before you rely on them.*

A few words used below:

- **Treatment**: a saved carb entry, insulin dose, temporary target, note and similar.
- **Uploader**: an app that sends treatments to your site, such as Loop, Trio, AndroidAPS, xDrip+ or a pump sync tool.
- **Identity**: a label an uploader puts on each treatment so that it can be recognised later, for example Loop's `syncIdentifier`. An **empty identity** is that label sent with nothing in it.
- **Re-send**: when an uploader sends the same treatment again because it did not hear back the first time. Nightscout must recognise it and not store it twice.

**What was wrong.** Only in the development version of Nightscout, after the fix for same-time treatments (#8780): if an uploader sent a treatment with an empty identity and then sent the same treatment again, Nightscout stored it twice. Its carbs or insulin could then be counted twice on the site, in reports and in what followers see. Treatments sent with no identity at all were not affected.

No released version has this problem, and no uploader we checked sends an empty identity.

**What this change does.** An empty identity now counts as no identity, exactly as a missing one does, so a re-send is recognised again and the treatment is stored once. Treatments with a real identity still have to match exactly, so two different treatments are still kept apart.

**Do you need to do anything?** No.

## Technical detail

### The defect

#8780 added `lib/server/treatment-fallback-key.js`, the selector API v1 (`upsertQueryFor`) and the websocket `dbAdd` exact match use for a write with no `identifier` and no `_id`. A write that carries none of `syncIdentifier`, `id`, `uuid`, `NSCLIENT_ID` (`present()` treats absent, `null` and `""` alike as none) matches only a record without identity. The stored side of that rule was `{field: {$eq: null}}` for those four fields and `identifier`, which matches `null` or absent, not `""`. `upsertQueryFor` sends a write with `identifier: ""` to the fallback (`if (obj.identifier)`), and v1 stores `""` as sent, so the second POST did not match the first and was inserted: 2 records on `ff93fa94`, 1 on `v15.0.8` `92d08342`, on `dev` `750801a9` and on `aa1111b2`. The same holds for a record stored with any of the four client fields as `""`. The socket's similar match (same amounts within 2 s) hid the gap for an identical socket re-send, but not for one with another amount, which the no-identity exact match otherwise answers with the stored record.

### What the commit does

The no-identity clause matches each of the five fields with `{$in: [null, ""]}` instead of `{$eq: null}` (a new object per query; the list is the server's own, not client input). A write without identity therefore matches a stored record whose field is absent, `null` or `""`, as a `null` write already matched `null` or absent. The rule for a write with a non-empty identity is unchanged: that value must be `$eq` the stored one, so a real identity and `""` are two records. The amounts clause, the paths that match by `identifier` or `_id`, and API v3 are not changed.

## Tests

`tests/api.same-time-treatments.test.js`, new describe "an empty identity is no identity (BF-141)", 71 tests on a real MongoDB (v1 through supertest, a real socket):

- **Fail on `dev` `ff93fa94` with the original symptom** (29; each failure message read, 2 records where 1 was expected, or 3 where 2): the same v1 treatment POSTed twice with `identifier: ""`; for each of `identifier`, `syncIdentifier`, `id`, `uuid` and `NSCLIENT_ID`, a re-send with `""`, `null` or absent against a record stored with `""`, and a re-send against a record inserted with `""` before the change; a real `syncIdentifier`, `id`, `uuid` or `NSCLIENT_ID` between two `""` writes; the socket exact match with `""` against a record stored with `""`, for four fields.
- **Pass on both** (the controls): every re-send against a record stored with `null` or absent; a real identity is kept apart from `""` both ways; an entry with `identifier: ""` does not replace an API v3 record (v1 and socket); two same-time entries with `""` and different carbs stay two; a socket write with a real `id` is not answered by a record with `id: ""`.

**Changed expectations** (each marked in the file): `tests/storage.selector-hardening.test.js` "wraps treatment identifiers and fallback fields in literal equality" and `tests/websocket.input-validation.test.js` "literalizes similar-match fields and acknowledges only after its update" now expect `{$in: [null, '']}` for the five identity fields.

### Break-it

Reverting only the query line (`noIdentity()` back to `literal(null)`) turns the same 29 tests red (60 passing, 29 failing); restored, 89 passing.

### Full suite

`npm test` on `aaf67785`, fresh database: **3467 passing, 0 failing, 3 pending** (Node 22.23.2, MongoDB 7.0.43 read from the server). `dev` `ff93fa94` is 3396/0/3; the difference is the 71 new tests.

### Harness (alignment repo, `tools/lab/triage-2026-09/`)

- `api3-empty-identifier-delete.js`: the only line that differs between `ff93fa94` and `aaf67785` is the re-send of the same v1 treatment with `identifier: ""` (stored 2, then 1); absent and `null` store 1 on both, and every v3 delete arm is unchanged.
- `same-time-resend-shapes.js` (`ff93fa94` against `aaf67785`): every row is the same. I8185, D01, D04 and D05 are kept 2; R01 to R21 dedupe or update as before (R18 stale, as before); D02 and D03 merge as before. Every write answered 2xx and both servers stayed live.
- `same-time-carbs.js`: the same output on both trees, exit 0 (v3-noid and ws-dbAdd reported as the known issues left by #8780).

## Client impact

No client in the corpus is known to send an empty `identifier`, `syncIdentifier`, `id`, `uuid` or `NSCLIENT_ID` (read). Clients that omit these fields or send `null`, and clients that send a real identity, are matched exactly as on `ff93fa94`.
