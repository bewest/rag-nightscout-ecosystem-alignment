# Consumer-replay lab: results

*Contributor-facing. Snapshot, 2026-09-23. Evidence for the [consumer-impact analysis](../../docs/60-research/remedial/consumer-impact-15.0.9-2026-09-23.md). Two passages about defects live on 15.0.8 are reduced to mechanism.*


Run on 2026-09-23 (server clock 2026-09-24T05:2x–05:4xZ). Every row below comes from running the request, not from reading code.
Raw per-request logs, server logs and the probe scripts stay outside version control.

## Builds and environment

| | build | SHA | express / qs | worktree |
|---|---|---|---|---|
| A | tag 15.0.8 = origin/master | 92d0834219aa | 4.22.1 / 6.15.1 | externals/work/crm-6a-replay-a |
| B | origin/dev | ddd9b600c9f2 | 4.22.2 / 6.16.0 | externals/work/crm-6a-replay-b |
| C | local `lab/consumer-replay-6a` = merge of ef3404fd (#8754) and 6d120fa2 (#8758); tree 2ce67b27ce; contains ddd9b600 | 1067e6681214 | 4.22.2 / 6.16.0 | externals/work/crm-6a-replay-c |

- Node v22.23.2 (`n exec 22.23.2`) for all three builds. Every build's `engines` is `node >=20.x`, 15.0.8 included.
- MongoDB 7.0.43 in docker container `s6a-replay-mongo` (`--ulimit nofile=64000:64000`, 127.0.0.1:27161). Each build and config had its own database: `s6a_<build>_<cfg>`.
- Servers ran on 127.0.0.1:3961/3962/3963 (A/B/C). They were started with `setsid nohup`, and each was stopped by the PID that start recorded.
- Configs:
  - `r`: AUTH_DEFAULT_ROLES=readable, UUID_HANDLING unset. The code default is true on all three builds (`env.js readENVTruthy("UUID_HANDLING", true)`).
  - `d` and `d2`: AUTH_DEFAULT_ROLES=denied.
  - `ut`: UUID_HANDLING=true.
  - `uf`: UUID_HANDLING=false.
- API_SECRET was freshly generated (20 characters, file `secret`, mode 600). Subjects `lab-readable` [readable], `lab-careportal` [careportal] and `lab-admin` [admin] were created through `POST /api/v2/authorization/subjects` on each build. Their tokens were read back from `GET /subjects`.
- Seed data, on every build and config:
  - 576 sgv entries, one every 5 min over 48 h.
  - 76 treatments via the API: Meal Bolus, Correction Bolus, Temp Basal with duration 30 and absolute 0.725, and Temporary Target by `careportal` and by `Trio`. `enteredBy` was `openaps://medtronic/522` or `loop://iPhone`.
  - 1 profile.
  - 12 devicestatus: 6 in the Loop shape (`loop.cob.cob`, `loop.iob.iob`) and 6 in the OpenAPS shape (`openaps.suggested.COB`).
  - 24 activity records with numeric `date`.
  - Direct mongo inserts into treatments, simulating records written by ≤15.0.6: `_id` as an ObjectId, as a 24-hex string, as an UPPER-case UUID string, and a second 24-hex string for the PUT test.

### Liveness evidence

Every probe group ran between two controls, each a `GET /api/v1/status.json` with the api-secret header. Result for every group on every build and config: **200 before / 200 after**, with one exception: **A, group P4, after = 000**. The 15.0.8 process exited during that group; see P4. Each group's `liveBefore`/`liveAfter` is stored in `out/*.json`. Because P4 took A down, it runs last in the suite. The A result was the same in 3 of 3 runs.

---

## P1: oref0 `latest-openaps-treatment` [every loop's treatment lookup gets 400]

**Request shape.** This is what `ns-get` builds from `nightscout.sh:164-165` (`curl --compressed -g -s`):
- hashed-secret mode: `GET /api/v1/treatments.json?find[enteredBy]=/openaps:\/\//&count=1?<sha1>`, with header `api-secret:<sha1>`
- token mode: `GET /api/v1/treatments.json?find[enteredBy]=/openaps:\/\//&count=1?token=<t>&token=<t>`

**Control:** the same URL with a plain `count=1`. In hashed mode that is the URL with the header. In token mode it is `…&count=1&token=<t>`.

| cfg | mode | A | B | C |
|---|---|---|---|---|
| readable | hashed, suspect | 200, 1 record (latest openaps) | **400** `Bad count` "count must be a whole number of documents, 0 or greater" | **400** `Bad count` |
| readable | hashed, control | 200, 1 record | 200, 1 record | 200, 1 record |
| readable | token, suspect | 200, 1 record | **400** `Bad count` | **400** `Bad count` |
| readable | token, control | 200, 1 record | 200, 1 record | 200, 1 record |
| denied | hashed / token, suspect | 200 / 200 | **400 / 400** | **400 / 400** |
| denied | hashed / token, control | 200 / 200 | 200 / 200 | 200 / 200 |

**What oref0 does next.** This was run with the real `jq` 1.7 and GNU `date`, using the rig's own pipeline: `ns-get … | jq . | jq .[0] | jq -r .created_at`, then `date -Is -d $x`.
- A: `latest_ns_treatment_time` = the newest openaps treatment (for example `2026-09-23T22:02:13-07:00`).
- B and C: `jq .[0]` fails with "Cannot index object with number", so `date -Is -d` gets no argument and exits 1. `latest_ns_treatment_time` is **empty**. The "in the future" guard at `oref0-ns-loop.sh:249` is false. `cull-latest-openaps-treatments` runs with LAST_TIME empty, and `select(.created_at > "")` keeps every record.

| 57-record 24 h pump-history batch (mm-format-ns-treatments shape, zoned `-07:00` `created_at`) | A | B | C |
|---|---|---|---|
| records the cull keeps with the LAST_TIME this build yields | 1 | **57** | **57** |
| same, with the control's LAST_TIME | 1 | 1 | 1 |

**Replay of that consequence.** The batch was POSTed three times to `/api/v1/treatments.json` with header `API-SECRET: <sha1>`, the way `ns-upload.sh` sends it.

| | A | B | C |
|---|---|---|---|
| POST 1 / 2 / 3 status | 200 / 200 / 200 | 200 / 200 / 200 | 200 / 200 / 200 |
| reply length (request length 57) | 57 / 57 | 57 / 57 | 57 / 57 |
| treatments total: before, after POST 1, 2, 3 | 80, 137, 137, 137 | 80, 137, 137, 137 | 80, 137, 137, 137 |
| a rig record edited in Nightscout between POST 1 and 2 (PUT adds `notes`; edit confirmed stored) | the re-POST replaced it: same `_id`, `notes` gone | same | same |

**Verdict: reproduced.**
- B and C answer 400 to both oref0 shapes, under readable and denied, and 15.0.8 answers 200. The change is already on dev (B), not introduced by #8754/#8758.
- The consequence is **no duplicates**: the upsert on `created_at`+`eventType` is idempotent.
- Instead, every loop re-POSTs about 24 h of pump history (57 writes here, not 1). Any edit made in Nightscout to a rig-uploaded treatment from the last 24 h is **overwritten on the next loop**. The replace-on-repost behaviour itself is the same on A. What is new is that B and C now make the rig re-send those records on every loop.

## P2: GluPredKit `count=0` [count=0 as "no limit" now returns nothing]

**Request shape.** From `glupredkit/parsers/nightscout.py:66-91`, urlencoded as `urllib.parse.urlencode`/requests do, with header `api-secret: <sha1>`:
- `GET /api/v1/profile?count=0&find%5Bcreated_at%5D%5B%24gte%5D=<ISO .000Z>&find%5Bcreated_at%5D%5B%24lte%5D=<ISO>`
- `GET /api/v1/treatments.json?count=0&find[created_at][$gte]=…&find[created_at][$lte]=…` (python-nightscout `get_treatments`)
- `GET /api/v1/entries/sgv.json?count=0&find[dateString][$gte]=…&find[dateString][$lte]=…` (python-nightscout `get_sgvs`)

The entries filter is `dateString`, as GluPredKit sends it, not `date`. The python-nightscout paths and header are recalled from the library; that package is not in `externals/`.

The window was 50 h. **Control:** the same requests with `count=100000`.

| | A | B | C |
|---|---|---|---|
| profile count=0 / control | 200 [1] / 200 [1] | 200 **[]** / 200 [1] | 200 **[]** / 200 [1] |
| treatments count=0 / control | 200 [137] / 200 [137] | 200 **[]** / 200 [137] | 200 **[]** / 200 [137] |
| entries count=0 / control | 200 [576] / 200 [576] | 200 **[]** / 200 [576] | 200 **[]** / 200 [576] |

**Verdict: reproduced.** On 15.0.8, `count=0` returned every record in the window. On B and C it returns an empty list, on all three endpoints. The change is already on dev.

## P3: activity numeric `date` filter [candidate-side regression]

**Request shape:** `GET /api/v1/activity.json?find[date][$gte]=<ms>&count=100`. **Control:** `find[created_at][$gte]=<ISO>&count=100`. Both use the same 6 h window. The stored `date` is a number.

| | A | B | C |
|---|---|---|---|
| numeric `date` filter | 200, 7 | 200, **0** | 200, **0** |
| `created_at` control | 200, 7 | 200, 7 | 200, 7 |
| mongo truth (`date >= since`) | 7 | 7 | 7 |

**Verdict: reproduced, but already on dev (B).** It is not candidate-only.

Mechanism, read after the run: B and C pass `collection: 'activity'` to the query builder. The collection coercion map has `activity: {}`, so no walker converts `date` to a number, and the string bound does not match numeric `date`. On 15.0.8 the default walker applied `parseInt` to `date`.

## P4: bulk `$in` deletes [Express 4.22.2: arrays over 20 now work, so bulk deletes take effect]

**(a) The brief's shape.** `DELETE /api/v1/treatments?find[_id][$in][]=<id>&…` with 5/20/21/50 ids, all ObjectIds created through the API, and header `api-secret`. Counts are of the 120 dedicated `p4` records.

| ids | A | B | C |
|---|---|---|---|
| 5 | 200, deleted 5 (120→115) | 200, 5 (120→115) | 200, 5 (120→115) |
| 20 | 200, deleted 20 (115→95) | 200, 20 (115→95) | 200, 20 (115→95) |
| 21 | **500** (HTML page "MongoServerError: $in needs an array"), 95→95 | 200, 21 (95→74) | 200, 21 (95→74) |
| 50 | **500** same, 95→95 | 200, 50 (74→24) | 200, 50 (74→24) |
| GET `$in` of 5 / 20 (control), count=100 | 200 [5] / 200 [20] | 200 [5] / 200 [20] | 200 [5] / 200 [20] |
| (one read in this group) | **ended the 15.0.8 process**: BF-107, fixed on `dev` by #8697. The request is withheld here because the defect is live on the shipping release. | 200 | 200 |

**(b) What xdripswift actually sends.** `NightscoutSyncManager.swift:794-806` (c268542e) sends `DELETE /api/v1/entries.json?find[type]=sgv&find[date][$in][]=<ms>&…`, chunked at 50. It does not send `find[_id][$in]` on treatments; ios/xdripswift.md S12 says the same. The same request was also replayed as a GET with `count=100`.

| values | A | B | C |
|---|---|---|---|
| 5 / 20 / 21 / 50: GET | **500** "Mongo Error" | **500** | **500** |
| 5 / 20 / 21 / 50: DELETE | **500** `dateString.replace is not a function` (the body includes a stack trace with server paths); entries 580→580, targets all left | **500**, same | **500**, same |
| control: one `$in` value | GET 200 [1], DELETE 200 deleted 1 | same | same |
| control: xdripswift's range delete `find[date][$gte]&find[date][$lte]` (5 readings) | 200, deleted 5 | same | same |

**Verdict: reproduced for (a), and (a) is already on dev.** A bulk `_id $in` over 20 values fails on 15.0.8 and succeeds on B and C.

**(b) is a separate finding, and it is not fixed on any build.** xdripswift's cadence-rebuild delete fails with 500 for two or more timestamps on all three builds, and nothing is deleted. The mechanism, confirmed by the error and read afterward: `enforceDateFilter` (`lib/server/query.js`) walks the keys of the `date` filter and calls `.replace` on each value that `isNaN`. The `$in` value is an array, which `isNaN`, and the array has no `.replace`. A one-element array passes `isNaN` as a number, which is why the single-value control works.

## P5: Loop override delete by UPPER-UUID [Loop override delete]

NightscoutKit sends no query string on this DELETE (ios/NightscoutKit.md S7(a), S15, and join question 1). **Request shape:**
1. `POST /api/v1/treatments` with `[{_id: <UPPER-UUID>, eventType: "Temporary Override", created_at, timestamp, duration: 60, reason, correctionRange, insulinNeedsScaleFactor, enteredBy: "Loop"}]`
2. `DELETE /api/v1/treatments/<UPPER-UUID>`

Both carry header `api-secret`. **Control** (where the record survived): DELETE by the stored `_id`.

| UUID_HANDLING | | A | B | C |
|---|---|---|---|---|
| unset (default true) | POST | 200; reply `_id` = new 24-hex; stored `_id` ObjectId, `identifier` = the UPPER-UUID | same | same |
| | DELETE | 200 `deletedCount:1`; record gone | same | same |
| true | POST / DELETE | same as unset: 200 / 200 `deletedCount:1`, gone | same | same |
| false | POST | 200; stored `_id` ObjectId, **no `identifier`** (the UUID is dropped) | same | same |
| | DELETE | **200 `deletedCount:0`; override still stored** | same | same |
| | control DELETE by stored `_id` | 200, `deletedCount:1` | same | same |

**Verdict: not reproduced as a regression.** DELETE answers 200 on every build and setting, so Loop's override queue does not block. With UUID_HANDLING=false, the override is never deleted on the server. That happens identically on A, B and C, so it is pre-existing.

## P6: Trio [count=1600 / `+` as space]

**Request shapes and controls:**
- `GET /api/v1/entries/sgv.json?count=1600&find[dateString][$gte]=<ISO .sssZ>`, window 24 h. Control: `count=10`.
- `GET /api/v1/treatments.json?find[eventType]=Temporary+Target&find[created_at][$gte]=<ISO>`. Control: `%20` in place of `+`.
- Trio's full temp-target shape (`NightscoutAPI.swift:255-274`, bracket-percent-encoded as URLComponents does): `find[eventType]=Temporary+Target&find[duration][$exists]=true&find[$and][0..4][enteredBy][$ne]=<Trio|AndroidAPS|openaps://AndroidAPS|iAPS|loop://iPhone>&find[created_at][$gt]=<ISO>`. Control: `%20`.

| | A | B | C | truth |
|---|---|---|---|---|
| sgv count=1600 / count=10 | 200 [288] / [10] | 200 [288] / [10] | 200 [288] / [10] | 288 |
| TT with `+` / with `%20` | 200 [12] / [12] | 200 [12] / [12] | 200 [12] / [12] | 12 |
| Trio full shape `+` / `%20` | 200 [6] / [6] | 200 [6] / [6] | 200 [6] / [6] | 6 (Trio's own excluded) |

**Verdict: no change (no regression).** `+` decodes to a space on all three builds, and count=1600 is accepted.

## P7: xdripswift `find[_id]=<X>&count=1` [an empty lookup deletes locally]

**Request shape:** `GET /api/v1/treatments?find[_id]=<X>&count=1` with header `api-secret`. The results were identical under UUID_HANDLING unset, true and false.

| stored as → asked with | A | B | C |
|---|---|---|---|
| API-written ObjectId → lower hex (control) | found | found | found |
| legacy ObjectId → lower hex | found | found | found |
| legacy 24-hex **string** → same | **[]** | **[]** | found |
| legacy UPPER-UUID string → same | found | found | found |
| legacy ObjectId → UPPER hex | found | found | found |
| legacy 24-hex string → UPPER hex | [] | [] | found |
| legacy UPPER-UUID string → lower-case | [] | [] | [] |

All answers were 200.

**Verdict: not reproduced as a regression.** C returns the record in every case where A did. For records that ≤15.0.6 stored with a 24-hex string `_id`, A and B return `[]`, which is the answer xdripswift reads as "deleted remotely". C fixes that. A UUID asked in a different case is `[]` on every build, so that is pre-existing.

## P8: Loop/xDrip `_id` round trip

**Request shapes:**
- `POST /api/v1/treatments` with `[Loop carb (syncIdentifier, no _id), xDrip bolus with its own lower-case 24-hex _id]`
- `PUT /api/v1/treatments` with the reply `_id`, which is the Loop carb edit
- PUT with xDrip's own `_id`
- a PUT of a new record with its own `_id`, twice (xDrip Android backfill)
- a PUT onto a record inserted directly with a 24-hex string `_id`, then DELETE by that id

| | A | B | C |
|---|---|---|---|
| POST status; reply length / request length | 200; 2/2 | 200; 2/2 | 200; 2/2 |
| reply `_id` forms | both 24-hex lower strings; xDrip's equals the one it sent | same | same |
| Loop carb PUT with reply `_id` | 200; 1 doc, carbs 20→25 (in place) | same | same |
| xDrip PUT with own `_id` | 200; 1 doc, updated | same | same |
| xDrip PUT-new ×2 | 200/200; 1 doc | same | same |
| PUT onto a legacy **string** `_id` | 200; **2 docs**: string original (0.8) + ObjectId copy (0.9) | 200; **2 docs** | 200; **1 doc** (ObjectId, 0.9); string copy removed |
| then DELETE by that id | 200; 1 left (string copy survives) | 200; 1 left | 200; 0 left |

**Verdict: reproduced** as described (a C improvement). Round trips of new records are clean on all builds. Legacy string-`_id` records get duplicated by a PUT, and are not removed by a DELETE, on A and B. C updates them in place and deletes them.

## P9: xDrip follower devicestatus

**Request shape:** `GET /api/v1/devicestatus.json?count=1`.

| cfg | credential | A | B | C |
|---|---|---|---|---|
| readable | api-secret header | 200 [1] | 200 [1] | 200 [1] |
| readable | none | 200 [1] | 200 [1] | 200 [1] |
| denied | api-secret header | 200 [1] | 200 [1] | 200 [1] |
| denied | none (negative control) | 401 | 401 | 401 |

**Verdict: no change.** The follower keeps polling on every build, and the denied control shows auth was enforced.

## P10: entries re-sent with a different `_id` (the connector's case)

**Request shape:** `POST /api/v1/entries` with `[{type:sgv, date:T, dateString, sgv, device}]`, then the same `date` and `type` with a different 24-hex `_id`.

| | A | B | C |
|---|---|---|---|
| first without `_id`, second with hex `_id` | 200, then **500** `Mongo Error`, `description.code 66` (immutable `_id`); 1 doc, sgv unchanged | 200, then **500** code 66 | 200, then **200**; 1 doc, sgv updated |
| first hex `_id` h1, second h2 | 200, then **500** code 66 | 200, then **500** | 200, then **200**; 1 doc |
| control: same `_id` both times | 200, 200; 1 doc | same | same |

**Verdict: reproduced** (A 500 → C 200; B still 500). No duplicate document on any build. xdripswift counts a 500 with code 66 as success, and C's 200 is also success for it.

## P11: devicestatus re-post with its own `_id` [inventory C55: 200 with duplicate → 500 on C]

**Request shape:** `POST /api/v1/devicestatus` with `[{_id: <24-hex>, device, created_at, uploader}]`, twice. A second case sends the `_id` of a copy inserted directly as a string (the ≤15.0.6 case the #8758 commit names). **Control:** the same document with no `_id`, twice.

| | A | B | C |
|---|---|---|---|
| POST 1 / POST 2 (same hex `_id`) | 200 / **500** E11000; docs 1 → 1 | 200 / **500**; 1 → 1 | 200 / **500**; 1 → 1 |
| stored `_id` form from the API | 24-hex **string** | 24-hex string | ObjectId |
| re-send of a legacy string-stored copy | **500** E11000; 1 doc | **500**; 1 doc | **500**; 1 doc |
| control, no `_id` twice | 200/200, **2 docs** | 200/200, 2 docs | 200/200, 2 docs |

**Verdict: not reproduced.** No build answered "200 with a duplicate". A and B already refuse the re-post with 500, because they store the `_id` as a string and the second insert collides. C refuses it too: it stores an ObjectId, and the legacy string copy is caught. The before-state the inventory describes did not occur on 15.0.8 or dev in this run. It could belong to an intermediate commit on the #8758 branch, which was not tested.

## P12: websocket `authorize`, LoopFollow style

**Shape:** a socket.io-client 4.8.3 connection to `/`, with the `token` connect parameter. It emits `authorize` `{client:"LoopFollow", history:1, secret:<access token>}`, once with an ack callback and once without, as LoopFollow does. It then emits `{client:"web", history:1, secret:<sha1>}`. Liveness: an unauthenticated socket connected before and after.

| cfg | case | A | B | C |
|---|---|---|---|---|
| readable & denied | unauthenticated (liveness) | `clients` ×1, no `connected`, no `dataUpdate` | same | same |
| readable & denied | readable token (ack) | `connected`, `dataUpdate` with sgvs; ack `{read:true, write:false, write_treatment:false}` | same | same |
| readable & denied | readable token (no ack, LoopFollow) | `connected`, `dataUpdate` with sgvs | same | same |
| readable & denied | hashed api secret | `connected`, `dataUpdate`; ack `{read:true, write:true, write_treatment:true}` | same | same |

**Verdict: no change.** LoopFollow's flow receives `dataUpdate` on A, B and C under both default roles. The liveness `clients` event arrived every time.

## P13: `/alarm` namespace, who receives and whose `ack` clears

Raising an alarm needed no special setup: an entry with `sgv: 45` posted now raises simplealarms "Urgent LOW" (level 2, group `default`). An earlier attempt with `sgv: 39` raised nothing, because values below 40 are CGM error codes.

**Shape:** one socket per role subscribes on `/alarm` with its access token, and one anonymous socket never subscribes. After the alarm is raised, each role in turn tries to silence it, 2.5 s apart, in two orders. The exact sequence is withheld because the 15.0.8 behaviour below is a published advisory that is still live on the shipping release.

| cfg | | A | B | C |
|---|---|---|---|---|
| readable | receive `urgent_alarm` | anonymous, readable, careportal, admin | all four | all four |
| readable | first ack that emits `clear_alarm` | **careportal's** | admin's only | admin's only |
| denied | receive | **anonymous (never subscribed)**, readable, careportal, admin | readable, admin | readable, admin |
| denied | first ack that clears (order 1) | **careportal's** | admin's | admin's |
| denied | first ack that clears (order 2) | **readable's** | admin's | admin's |

All subscribe acks answered `{success:true}`.

**Verdict: B and C behave identically, and A differs.**
- On B and C, only a subject with `notifications:*:ack` (admin here) can silence an alarm, and under denied only subjects that can read receive it.
- On 15.0.8, any socket can silence the alarm for every viewer, and under denied a socket that never authenticated receives alarms. This is consistent with the socket advisories that are still live on 15.0.8 (mechanism only).
- Consumer note: a follower that acks over `/alarm` with a readable-only token, or an anonymous web viewer on a readable site, can silence alarms on 15.0.8 and cannot on B/C. The ack is ignored silently; no error is sent back.

---

## Verdict table

| probe | finding tested | verdict | where the behaviour changes |
|---|---|---|---|
| P1 | oref0 lookup gets 400 | **reproduced**; consequence: whole-24 h re-POST each loop, no duplicates, Nightscout edits to rig treatments overwritten | A→B (dev) |
| P2 | GluPredKit count=0 → nothing | **reproduced** (profile, treatments, entries all `[]`) | A→B (dev) |
| P3 | activity numeric `date` filter | **reproduced** (0 vs 7), but **already on dev**, not candidate-only | A→B (dev) |
| P4a | `_id $in` > 20 now deletes | **reproduced**; plus a 15.0.8 process exit, BF-107 (request withheld) | A→B (dev) |
| P4b | xdripswift's real bulk delete (`find[date][$in][]` on entries) | **new: 500 on all builds, nothing deleted** | none (still broken on C) |
| P5 | Loop override DELETE by UPPER-UUID | not reproduced; 200 on all; with UUID_HANDLING=false the delete removes nothing on every build | none |
| P6 | Trio count=1600, `+` decoding | no change | none |
| P7 | xdripswift empty `find[_id]` lookup | not reproduced as a regression; C finds legacy string-hex ids that A/B miss | B→C (improvement) |
| P8 | `_id` round trip | reproduced as described; legacy string PUT duplicates on A/B, in place on C | B→C (improvement) |
| P9 | xDrip follower devicestatus | no change (200) | none |
| P10 | entry re-send with a different `_id` | **reproduced** (A 500/66 → C 200) | B→C |
| P11 | devicestatus re-post (C55) | **not reproduced**: 500 on A, B and C; no build gave 200 plus a duplicate | none observed |
| P12 | websocket authorize under denied | no change; `dataUpdate` arrives on all | none |
| P13 | `/alarm` receive and ack | B and C identical, only admin's ack clears; A lets any socket clear the alarm and, under denied, delivers it to unauthenticated sockets | A→B (dev) |

## Deviations from the brief

- **P4:** the brief's shape (`find[_id][$in][]` on treatments) is not what xdripswift sends. Both shapes were run; see (a) and (b).
- **P2:** GluPredKit filters entries on `dateString`, not `date`, and that shape was used. The python-nightscout endpoint paths are recalled, not verified in a checkout.
- **P5:** UUID_HANDLING "unset" means true on every build, so `false` was added as the only setting that changes behaviour.
- **P13:** the `sgv: 39` attempt raised nothing (error code). `sgv: 45` was used instead.
- **P1:** the replay ran on A and B as well as C.
