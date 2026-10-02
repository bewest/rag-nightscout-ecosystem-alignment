<!-- Draft body for branch bf/socket-dedup-zero at 7dff9f38 (one commit on dev ca6fcfaf), 2026-10-02. This comment is hidden on GitHub. Not opened. -->
A zero temp basal, a 100 % temp, a cancel, a zero bolus or a zero carb entry sent over the websocket within 2 seconds of another record is now kept, instead of being dropped as a copy of that record (BF-09). One commit (`7dff9f38`) on `dev` `ca6fcfaf`. It changes only the websocket `dbAdd` "similar" match; the exact match, API v1 and API v3 are unchanged. This is the handling the maintainer chose on 2026-10-02: a zero is a real value where it carries meaning (temp basals, cancels, a bolus or carb amount of zero), and a zero sent only as filler (`insulin: 0` on a carb entry) does not stop a re-send from being recognised.

## What changes for you

*A plain-language summary for people who run their own Nightscout site, for themselves or for a family member. Nothing here tells you how to dose. If a temp basal, bolus or carb entry looks wrong in Nightscout, check it against the app or pump that recorded it, and talk to your care team before relying on it.*

A few words used below:

- **Treatment**: a saved entry such as carbs, an insulin dose, a temporary basal rate or a temporary target.
- **Temp basal**: a temporary change to the background insulin rate that an automated insulin delivery (AID) app sets on the pump. A **zero temp** sets the rate to 0 for a while. It is how an AID app pauses basal insulin, for example when glucose is falling.
- **Cancel**: an entry that ends a temp basal or a temporary target early.
- **Uploader**: an app that sends treatments to your site. This change is about uploaders that use Nightscout's live connection (the websocket): AndroidAPS with the older NSClient connection (v1), the older standalone NSClient app that xDrip+ can send treatments to, and Nightscout's own chart when you drag a treatment to a new time. Loop, Trio, xDrip4iOS and AndroidAPS with the NSClient v3 connection use a different route and are not affected.

**What was wrong.** When an entry arrives over the live connection, Nightscout checks whether it already has the same entry from the last 2 seconds, so that an entry sent twice is not stored twice. That check ignored any value of zero. So a zero temp sent a second after a different temp of the same length looked like the same entry, and Nightscout threw the zero temp away. The chart then showed the earlier rate for the whole half hour, when the pump was actually delivering no basal. The same could happen to a cancel (the temp was drawn as still running), a 100 % temp, and an entry with 0 units or 0 g after one with an amount.

The AID app and the pump kept their own correct records. What was wrong was what Nightscout stored and showed, and what anything reading temp basals from Nightscout received.

**What this change does.** A zero now counts:

- For temp basal rates and lengths (including cancels), zero is a real value. A zero temp is no longer taken for a different temp.
- For insulin and carbs, zero means "none". An entry with 0 units is not taken for an entry with 1 unit. But when an app fills in `insulin: 0` on a carb entry only because the form has an insulin box, that entry is still recognised as the same as a stored carb entry, so re-sends are not stored twice.

**What does not change.** Entries sent more than 2 seconds apart, entries with their own uploader id, and entries sent through any route other than the live connection are handled as before. Entries that were already dropped before this update are not brought back.

**Do you need to do anything?** No.

## Technical detail

### The defect

`lib/server/websocket.js` `processSingleDbAdd`, treatments branch. When no exact match is found (by `NSCLIENT_ID`, or by `created_at` + `eventType` + client identity since #8780), the ±2 s similar match looks up a stored record of the same `eventType` (always, since #8780) with each of `insulin`, `carbs`, `percent`, `absolute` and `duration` that the incoming record carries. A field was added only when **truthy**, so `0` was treated as absent. On a match the incoming record is dropped and the stored one's `created_at` is moved to the incoming one's.

So, within 2 s and with the same `eventType`:

- a zero temp (`absolute: 0`) after a 1.2 U/h or a percent temp of the same `duration` was dropped;
- a 100 % temp (`percent: 0`, which AndroidAPS sends as `rate - 100`) after another temp of the same `duration` was dropped;
- a cancel (`duration: 0`) after a temp or a temporary target was dropped;
- a 0 U bolus after a 1 U bolus, a 0 g carb entry after a 20 g entry, and a `Meal Bolus` with 0 U + 20 g after one with 2 U + 20 g were dropped.

Identical on `15.0.8` and `dev` `74fc6619` (measured 2026-09-23) and on `dev` `ca6fcfaf` (measured 2026-10-02, table below). #8780 (BF-121) already fixed the two cases where a zero temp matched a temporary target, by always keying on `eventType`.

### What the commit does

The five `if (data.data.X)` tests become two rules (comment in the code names BF-09):

- **`percent`, `absolute`, `duration`**: `0` is a value and joins the key as `{$eq: 0}`.
- **`insulin`, `carbs`**: `0` joins the key as `{$in: [0, null]}`: it matches a stored record whose amount is 0 or absent, and never one with an amount.
- `''`, `false` and `null` are still left out, as before. A non-zero value is `{$eq: value}`, as before.

### Why the rule differs by field (evidence)

What clients send on this path:

- **AndroidAPS NSClient v1** (in release 3.4.2.6; removed from AndroidAPS `master` in `30fe4591a7`, 2026-05-05). Temp basal: `duration` in whole minutes (a temp under a minute is `duration: 0` beside `durationInMilliseconds`), and **either** `absolute: rate` **or** `percent: rate - 100` (`plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/extensions/TemporaryBasalExtension.kt:20-26`). A bolus carries `insulin` only (`BolusExtension.kt:12-16`), a carb entry `carbs` only, with `duration` left out when 0 (`CarbsExtension.kt:15-21`), a therapy event leaves out `duration` when 0 (`TherapyEventExtension.kt:66-67`). Sent as `dbAdd` with no `NSCLIENT_ID` (`NSClientPlugin.kt:196-212`, `services/NSClientService.kt:615-621`). So `absolute`, `percent` and `duration` are only present when they mean something, and a zero there is a value. Because a temp carries one of `absolute` or `percent`, "zero or absent" would be wrong for them: a zero temp would match a percent temp, and a 100 % temp an absolute one.
- **xDrip+ `NSClientChat`** sends `insulin` and `carbs` on **every** record, with the `eventType` chosen from which is non-zero (`app/src/main/java/com/eveningoutpost/dexdrip/models/NSClientChat.java:33-55`): a carb entry carries `insulin: 0`, a bolus `carbs: 0`. It sends only when xDrip+'s own Nightscout upload is off (`models/Treatments.java:475-479`), as an `info.nightscout.client.DBACCESS` broadcast to a standalone NSClient app; AndroidAPS 3.4.2.6 does not receive that broadcast. These zeros are filler.
- **API v1 storage removes a zero** `insulin`, `carbs` and `percent` (`lib/server/treatments.js` `prepareData`, `deleteIfEmpty`), so a copy stored through v1 has no field where the socket copy has `0`.
- **Nightscout's chart** (drag to move insulin or carbs) sends a copy of the stored record with the moved-away field deleted (`lib/client/treatmenttime.js` `splitRecord`); no zero is added.
- **Loop, Trio, xDrip4iOS** do not use `dbAdd` (no reference in their sources).

From the corpus (277,690 treatments, 11 sites, de-identified counts): `absolute` is 0 in 67,521 of 153,315 temp basals (Loop 50,326, Trio 17,195); `duration` is 0 on 11 Loop temp basals and 2,083 Loop correction boluses; `insulin` and `carbs` are never 0, and the "not applicable" filler that does appear is `null` (for example `insulin: null` on every Loop and Trio temp basal). The corpus has no AndroidAPS records and arrived through REST, where v1 removes zero `insulin` and `carbs`, so it does not show what socket clients send.

So an exact zero key for `insulin` and `carbs` (the "zero is real for all five" option measured on 2026-09-23) would make a filler zero stop a re-send from matching a copy stored without the field (R1 and R2 below). "Zero or absent" fixes the zero bolus and zero carbs cases and keeps those re-sends recognised. No per-`eventType` list is needed, because the similar match already requires the same `eventType`.

## Tests

`tests/websocket.dedup-zero.test.js` (new, 22 tests, real MongoDB, a real socket and the v1 route through supertest):

- **Fail on `ca6fcfaf`** (9; each fails with one record stored where two were sent, e.g. `expected Array [ 1.2 ] to equal Array [ 1.2, 0 ]`): zero temp after a 1.2 U/h temp; cancel after a zero temp; 100 % temp after a 150 % temp; 100 % temp after an absolute temp; zero temp after a percent temp; temporary target cancel after a target; zero bolus after 1 U; zero carbs after 20 g; `Meal Bolus` 0 U + 20 g after 2 U + 20 g.
- **Re-sends still recognised** (pass on both): zero temp re-sent 1 s later; zero bolus re-sent; xDrip+ carb entry (`insulin: 0`) 1 s after the same entry stored through API v1 (which removed the zero); xDrip+ bolus (`carbs: 0`) after the same bolus without carbs; xDrip+ note (0 and 0) re-sent.
- **Controls from the 2026-09-23 measurement** (pass on both): different `NSCLIENT_ID`s; 3 s apart; percent −100 then 1.2 U/h; zero temp then 1.2 U/h, and zero temps of different durations; `absolute` `''`, `false` and `null` then 1.2 U/h; 0 U then 1 U and 0 g then 20 g.

**Break-its** (2026-10-02):

| change | result |
|---|---|
| `lib/server/websocket.js` reverted to `ca6fcfaf` | 9 failing, the 9 above, each with the dropped record |
| `insulin`, `carbs` given an exact zero key (`x \|\| x === 0` for all five, the measured option) | 2 failing: the two xDrip+ filler re-sends, `expected 2 to be 1` |
| all five given "zero or absent" | 2 failing: 100 % temp after an absolute temp, zero temp after a percent temp, `expected 1 to be 2` |

No existing test changes.

### Full suite

`NODE_ENV=test npx env-cmd -f ./my.test.env mocha --timeout 5000 --require ./tests/hooks.js --exit ./tests/*.test.js`, fresh database, Node 22.23.2, MongoDB 7.0.43 read from the server: **3556 passing, 0 failing, 4 pending**. `ca6fcfaf` is 3534/0/4 on the same form; the difference is the 22 new tests.

### Harness (alignment repo, `tools/remedial/bf3/bf09-dedup-zero.js`; cases Q1, Q2, T1 and R1–R3 added on 2026-10-02)

Each case is sent over an authorized socket as `dbAdd` to the tree's real server, and the treatments are read back. Stored records and, separately, every sent record are rendered through the tree's `profilefunctions` (`getBasalRenderTimes` / `getTempBasal`, the path `renderer.js` takes) on a 1.0 U/h profile; "drawn Δs" counts the seconds where the drawn line differs from the line for every sent record.

| case | sent (1 s apart unless stated) | `ca6fcfaf` stored / drawn Δs | all-five exact zero (measured option) | this PR |
|---|---|---|---|---|
| Z1 | zero temp, re-sent | 1 / 1 | 1 / 1 | 1 / 1 |
| Z2 | 1.2 U/h, then zero temp | **1 / 1801** | 2 / 0 | 2 / 0 |
| Z3 | zero temp, then 1.2 U/h | 2 / 0 | 2 / 0 | 2 / 0 |
| Z4 | zero temps, different durations | 2 / 0 | 2 / 0 | 2 / 0 |
| Z5 | zero temp, then cancel | **1 / 1801** | 2 / 0 | 2 / 0 |
| Z6 | sub-minute zero temp, then 1.2 U/h | 2 / 0 | 2 / 0 | 2 / 0 |
| X1 | zero temp, then temporary target | 2 / 0 | 2 / 0 | 2 / 0 |
| X2 | temporary target, then zero temp | 2 / 0 | 2 / 0 | 2 / 0 |
| P1 | percent −100, then 1.2 U/h | 2 / 0 | 2 / 0 | 2 / 0 |
| P2 | 150 %, then 100 % (`percent: 0`) | **1 / 1801** | 2 / 0 | 2 / 0 |
| Q1 | 1.2 U/h, then 100 % (`percent: 0`) | **1 / 1801** | 2 / 0 | 2 / 0 |
| Q2 | 150 %, then zero temp | **1 / 1801** | 2 / 0 | 2 / 0 |
| T1 | temporary target, then cancel | **1** | 2 | 2 |
| N1 | different `NSCLIENT_ID`s | 2 / 0 | 2 / 0 | 2 / 0 |
| W1 | 1.2 U/h, then zero temp 3 s later | 2 / 0 | 2 / 0 | 2 / 0 |
| F1–F3 | `absolute` `''` / `false` / `null`, then 1.2 U/h | 2 / 0 | 2 / 0 | 2 / 0 |
| B1, C1 | 0 U then 1 U; 0 g then 20 g | 2 | 2 | 2 |
| B2, C2 | 1 U then 0 U; 20 g then 0 g | **1** | 2 | 2 |
| R3 | 2 U + 20 g, then 0 U + 20 g | **1** | 2 | 2 |
| R1 | 20 g, then xDrip+ shape 0 U + 20 g (a re-send) | 1 | **2 (duplicate)** | 1 |
| R2 | 1 U, then xDrip+ shape 1 U + 0 g (a re-send) | 1 | **2 (duplicate)** | 1 |

Drawn Δs equalled exact Δs in every row of every arm: the chart draws what is stored, exactly (the 1 s in Z1 is the merged record's `created_at` moving to the re-send's). So treating zero as a value does not bring back the AndroidAPS temp-basal display problem that `bec641ca` addressed and `846bb690` (sampling at every temp's start and end) now handles: every temp this change keeps is drawn exactly. For context, the bare 1-minute sampler that `bec641ca` replaced gets 58 to 117 s of each temp-basal case wrong on the sent records.

### Not changed, and not covered

- The exact match and its key, API v1 and API v3 matching.
- BF-94 (`prevBasalTreatment` at module scope in `lib/profilefunctions.js`) is not touched. This change stores more of the "temp followed by a zero temp" sequences that BF-94's browser case starts from; the harness renders with a fresh, cleared profile per render, so its figures are not affected by BF-94.
- No live AndroidAPS v1 burst was replayed; the cases are built from the upload shapes cited above.

Register: BF-09 (alignment repo `docs/30-design/remedial/nightscout-backfix-register.md`), queue `BFQ-09`. Evidence: `docs/60-research/remedial/bf09-dedup-zero-measurement-2026-09-23.md`.
