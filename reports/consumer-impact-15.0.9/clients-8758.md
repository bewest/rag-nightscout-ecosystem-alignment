# Clients × #8758 (`ab7b22d6`): how each client uses `_id` / `identifier`

**Contributor-facing working document (DRAFT).** Extends the 2026-09-23 consumer-impact survey
([clients/](clients/), [change-inventory.md](change-inventory.md)) with the `_id` changes of PR #8758
at `ab7b22d6`, listed as C68–C81 in [change-inventory-8758.md](change-inventory-8758.md). Synthetic
data only. Not medical advice.

- **Server refs (2026-09-25):** 15.0.8 `92d08342`; `origin/dev` `4f705217`; #8758 head `ab7b22d6`.
- **Client refs:** each repo's local HEAD as found on 2026-09-25, read with `git show` / `git grep`
  (no checkout, fetch or pull). `git diff --cached` and `git status --porcelain` were empty in every
  client repo. Where the HEAD differs from the ref the 2026-09-23 survey read, the section says so.
- **Evidence:** every client claim is **read-derived** unless it cites a replay cell. Replay cells
  (`Q…`, `P-ID-…`) are **measured**, §Replays.
- **Classes:** unaffected; better (the behaviour changes and is better); could be worse; cannot tell.

## Answers to the four questions

1. **Can #8758 refuse or de-duplicate a new devicestatus or a new CGM entry from an uploader in the
   corpus?** No, read-derived for every uploader and measured for the shapes they send. The only
   devicestatus shape #8758 turns from stored into refused is a re-post carrying a
   **server-assigned** `_id` (C69, C78); no uploader in the corpus sends one (AndroidAPS, Loop,
   Trio, xDrip, xDrip4iOS, oref0, the connector and the bridges send devicestatus without `_id`;
   the connector drops devicestatus not newer than the newest stored). For entries the change runs
   the other way: the connector's copy shape that answered 500 and lost the readings after it on
   15.0.8 is stored in full on `ab7b22d6` (Q8). AndroidAPS 3.x socket uploads are identical on both
   builds (Q9).
2. **Can a delete now remove more than before?** Only copies of the ids the client names: both
   halves of a twin (C74; Loop, xDrip, xDrip4iOS, tconnectsync, measured Q4/Q12/P-ID-7), and the
   string copies inside a `find[_id][$in]` list (C73; no client in the corpus sends one over HTTP).
   No delete reaches a record with a different id (Q4: the unlisted record is kept on both builds).
3. **AndroidAPS v3 identifiers and NSClient sync with `_id` now an ObjectId.** Unaffected, and
   better for v1 records stored with a string `_id`: AAPS sends no `_id` or `identifier` on create,
   keeps ids as the strings the server serialises (an ObjectId serialises as the same lower-case
   hex), and PATCH/DELETE by identifier of a string-`_id` record answers 200 where 15.0.8 answered
   404 (P-ID-2). A twin deleted through v3 keeps one valid copy on both builds (Q10b, CANDIDATE-3).
4. **Classes found:** no client is "could be worse" for a shape it sends. CANDIDATE-2 and
   CANDIDATE-3 below are server behaviours reached by no corpus client, or equally on both builds.

## Mismatches against this programme's inputs

- The 2026-09-23 survey's candidate already included #8758 (at `6d120fa2`, C42 and C49–C59). This
  document covers the five commits since then (`a2c7eb39`, `1c2d1afd`, `d2fd9ff6`, `dd2cf8f1`,
  `ab7b22d6`) and restates the whole contract at `ab7b22d6`.
- `tools/lab/object-id/README.md` P-ID-1 describes Loop re-POSTing a dose with its cached ObjectId.
  At NightscoutService `fe075ef0` the dose `_id` argument is commented out
  (`NightscoutServiceKit/Extensions/DoseEntry.swift:30,61`); Loop uses the cached id only for a
  carb PUT and for DELETE by id. The server shape P-ID-1 tests is still valid.
- AndroidAPS local HEAD is `7e1d537d49` (`origin/dev`); the 2026-09-23 map recorded local HEAD =
  `origin/master`. xdrip-js HEAD is `e30127358f` (was `0cd1c55`). xdripswift HEAD is `c268542e64`,
  now equal to `origin/master`. nightscout-connect HEAD is `04102f9d26` (`dev`, 0.1.1 development);
  `lib/` is identical to `v0.1.0` (`4dde1ecd`) and to `977da8a` read by the survey.
- The uploader pass graded oref0's `ns-dedupe-treatments` as "could be worse" on twins from lab
  cell P-ID-7 (the DELETE step alone). Run through the tool's own request sequence, its listing
  step does not complete on either build, so it deletes nothing on either (details with the parent,
  disclosure rule). The C74 effect applies to the DELETE step if the listing is fixed.

## Matrix

`–` unaffected or not reached; **B** better; **W** could be worse; **?** cannot tell. All read-derived;
a cell marked with a replay id was measured.

| client (HEAD) | C68 | C69 | C70 | C71 | C72 | C73 | C74 | C75 | C76 | C77 | C78 | C79 | C80 | C81 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AndroidAPS master `598e2eb39c` (v1 socket + v3) | – | – | – | – | – | – | – | B (P-ID-2) | B (P-ID-4) | – (Q9) | – | – | – | – |
| AndroidAPS dev `7e1d537d49` (v3) | – | – | – | – | – | – | – | B (P-ID-2) | n/a | n/a | – | – | – | – |
| xDrip `1ed760048a` | – | B | – | B | B | – | B | – | – | – | – | – | – | – |
| xdrip-js `e30127358f` | – | – | – | – | – | – | – | – | – | – | – | – | – | – |
| Loop (LoopWorkspace `f8412858c5`, NightscoutService `fe075ef0`, NightscoutKit `4ec9fd12a1`) | – | – | – | – | B (Q12) | – | B (Q12) | – | – | – | – | – | – | – |
| Trio `e41c9db37f` | – | – | – | – | – | – | – | – | – | – | – | – | – | – |
| xDrip4iOS `c268542e64` | – | – (P-ID-1) | – | – | B (Q14) | – | B | – | – | – | – | – | – | – |
| LoopFollow `4a74b781ad` | – | – | – | – | – | – | – | – | – | – | – | – | – | – |
| LoopCaregiver `230571838c` | – | – | – | – | – | – | – | – | – | – | – | – | – | – |
| nightguard `75404bd204` | – | – | – | – | – | – | – | – | – | – | – | – | – | – |
| DiaBLE `e6a909c88f` | – | – | – | – | – | – | – | – | – | – | – | – | – | – |
| GlookoServiceKit `8e2cad1cdf` | – | – | – | – | – | – | – | – | – | – | – | – | – | – |
| nightscout-connect `04102f9d26` | B (P-ID-5/6) | – | – | – | B (P-ID-5) | – | B | – | – | – | – | – | – | B (Q8) |
| oref0 `d219baf955` | – | – | – | – | B | – | see mismatches | – | – | – | – | – | – | – |
| tconnectsync `7c4b2f4ddb` | – | – | – | – | B | – | B | – | – | – | – | – | – | – |
| share2nightscout-bridge `518c85c4e5`, nightscout-librelink-up `bff2317f5c`, minimed-connect-to-nightscout `57bb042c43`, glooko-nightscout-eu `2b7fbc45b8`, cgmsim-lib `c09f9c0390` | – | – | – | – | – | – | – | – | – | – | – | – | – | – |
| glooko2nightscout `9ab8c6080b`, openaps `bd9a831887` (no Nightscout requests of their own) | – | – | – | – | – | – | – | – | – | – | – | – | – | – |
| GlycemicGPT `d1a9adb73e` | – | – | – | – | – (Q6) | – | B | – | – | – | – | – | – | – |
| nightscout-reporter `518d61fb1d` | – | – | – | – | – | – | B | – | – | – | – | – | – | – |
| oref-digital-twin `a2e8610d5f`, nightscout-cgm-skill `91a53ea167`, GluPredKit `e5bd6357a6`, nightscout-roles-gateway `90840acee1` | – | – | – | – | – | – | – (Q7) | – | – | – | – | – | – | – |
| babelbetes `07a7f07278`, osaid-keymanager `e9c3b738aa`, trio-telemetry `681ea86752` (no Nightscout requests) | – | – | – | – | – | – | – | – | – | – | – | – | – | – |
| nocturne `42275c812d` (server reimplementation) | n/a | n/a | n/a | ? | parity differs | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

## Candidate defects

- **CANDIDATE-2 (C78, #8758 only, reached by no corpus client).** A devicestatus POST whose first
  item re-posts a record under its server-assigned `_id` answers 500 and the new statuses after it
  in the same POST are not stored; 15.0.8, and `ab7b22d6` with dev's `lib/server/devicestatus.js`, answer 200, store a string
  duplicate and store the new statuses. Measured Q2b; the ablation (dev's `lib/server/devicestatus.js` on `ab7b22d6`)
  restores the 15.0.8 cells exactly. Reproduction: create a devicestatus without `_id`, take the
  `_id` from the reply, POST `[{that _id, same fields}, {a new status}]`, count the new status. A
  restore-from-export tool or a client that echoes read-back records would lose loop status this
  way. Read with C55's "200 + duplicate → 500", which the 2026-09-23 inventory already names.
- **CANDIDATE-3 (C75, same on 15.0.8 and `ab7b22d6`).** An API v3 DELETE by identifier on a twin
  marks one half `isValid:false` and leaves the other valid; the valid half is returned by v1
  time-window reads and v3 search on both builds (Q10b), so a treatment AndroidAPS deleted through
  v3 remains visible. On `ab7b22d6` v1 DELETE and websocket `dbRemove` remove both halves (C74,
  BF-110) while v3 does not, and a v3 GET answers 410 while v1 `find[_id]` returns the valid half
  (Q10). Twins exist only where a ≤15.0.8 edit met a record stored by ≤15.0.6.
- One further pre-existing defect on 15.0.8, found by an `_id` replay and unchanged by #8758, is
  reported to the parent separately under the disclosure rule.

## Replays (2026-09-25)

Measured 2026-09-25. Builds: 15.0.8 `92d08342` (worktree `externals/work/crm-6a-corpus-1508`) and
`ab7b22d6` (`crm-6a-corpus-cand`), each `npm ci` under Node 22.23.2, one MongoDB 7.0.43 container
(`serverInfo().version` read into every run), one database per build (`corpustest_*`),
`AUTH_DEFAULT_ROLES=readable`. Ablation build `abl` = `ab7b22d6` with only `lib/server/devicestatus.js`
from dev `4f705217`. Every run checked `GET /api/v1/status.json` = 200 before and after. Records that
stand for data older releases left behind (string `_id`s, twins) are written straight to mongo;
everything else goes through each build's own API. Stored forms and counts are read from mongo.
The probe script is kept outside version control because one replay exercises a defect live on
15.0.8.

### Client-shape probes

| cell | 15.0.8 `92d08342` | `ab7b22d6` | ablation `abl` |
|---|---|---|---|
| Q1 new, no _id | 200 / reply has _id | 200 / reply has _id | 200 / reply has _id |
| Q1 new, lower hex _id | 200 / string | 200 / OID | 200 / string |
| Q1 new, UPPER hex _id | 200 / string / reply _id as sent | 200 / OID / reply _id lower | 200 / string / reply _id as sent |
| Q2 read back by find[_id] | n=1 | n=1 |  |
| Q2 re-send alone | 200 / stored string,OID | 500 / stored OID |  |
| Q2 batch [re-sent string-stored, NEW] | 500 / stored string / NEW stored n=0 | 500 / stored string / NEW stored n=0 |  |
| Q2 own hex id POST then retry | 200 / 500 / stored string | 200 / 500 / stored OID |  |
| Q2b fresh OID record: batch [re-sent, NEW] | 200 / stored string,OID / NEW n=1 | 500 / stored OID / NEW n=0 | 200 / stored string,OID / NEW n=1 |
| Q2b fresh OID record: batch [NEW, re-sent] | 200 / stored string,OID / NEW n=1 | 500 / stored OID / NEW n=1 | 200 / stored string,OID / NEW n=1 |
| Q2b fresh OID record: re-sent in UPPER | 200 / stored string,OID | 500 / stored OID | 200 / stored string,OID |
| Q3 new with hex _id | 200 / OID:101 | 200 / OID:101 |  |
| Q3 batch [re-sent same id, NEW] | 200 / OID:102 / NEW OID:103 | 200 / OID:102 / NEW OID:103 |  |
| Q3 batch [NEW time reusing stored _id, NEW] | 500 / at t3 n=0 / at t4 n=0 | 500 / at t3 n=0 / at t4 n=0 |  |
| Q4 GET $in [twin, string-only] | n=1 | n=3 |  |
| Q4 GET $nin [twin] over the 4 | keep,string-only,twin-string | keep,string-only |  |
| Q4 DELETE $in [twin, string-only] | 200 / twin n=1 / other n=1 / keep n=1 | 200 / twin n=0 / other n=0 / keep n=1 |  |
| Q4 GET $gt 0 hex (cursor) | keep | keep |  |
| Q4 entries DELETE /entries/<hex> twin | 200 / n=1 | 200 / n=0 |  |
| Q5 ws dbAdd devicestatus id of OID record, new time | ack=sent / n=2 | [] / n=1 |  |
| Q5 ws dbAdd devicestatus fresh hex | ack=sent / string | ack=sent / OID |  |
| Q5 ws dbAdd devicestatus AAPS v1 shape (no _id) | ack has _id / n=1 | ack has _id / n=1 |  |
| Q5 ws dbAdd treatment fresh hex | ack=sent / string | ack=sent / OID |  |
| Q6 cursor $gt over [OID A, string C, OID B] | 111,113 | 111,113 |  |
| Q6 find[_id]=string C (control) | n=0 | n=1 |  |
| Q7 twin: GET, PUT, GET | n=2 / 200 / n=2 | n=2 / 200 / n=1 |  |
| Q8 connector copy [T other _id, T+5 new] | 500 / at T n=1 OID=first / T+5 n=0 | 200 / at T n=1 OID=first / T+5 n=1 |  |
| Q9 AAPS v1 dbAdd devicestatus x2 | n=1 / n=1 / same _id / stored n=1 | n=1 / n=1 / same _id / stored n=1 |  |
| Q9 AAPS v1 dbAdd sgv entry | n=1 / stored n=1 | n=1 / stored n=1 |  |
| Q10 v3 soft DELETE twin | 200 / OID:invalid,string:valid / v3 GET 410 / v1 find none-valid | 200 / OID:valid,string:invalid / v3 GET 410 / v1 find tw-o |  |
| Q10b v3 soft DELETE twin, then window reads | 200 / v1 window tw-o(invalid),tw-s / v3 search tw-s | 200 / v1 window tw-o,tw-s(invalid) / v3 search tw-o |  |
| Q11 UPPER string: PUT, stored, v3 history | 200 / string(UPPER):upper,OID:upper-edit / history  n=0 | 200 / OID:upper-edit / history  n=0 |  |
| Q12 Loop carbs POST/PUT/find/DELETE | 200 / 200 / n=1 / 200 / left n=0 | 200 / 200 / n=1 / 200 / left n=0 |  |
| Q12 Loop DELETE by hex on twin | 200 / left n=1 | 200 / left n=0 |  |
| Q14 find[_id] string / OID / absent | n=0 / n=1 / n=0 | n=1 / n=1 / n=0 |  |

Cell notes: Q4 twin = a string copy and an ObjectId copy of one hex; "string-only" = a record stored
only as the string; "keep" = an unlisted ObjectId record. Q10 "OID:valid,string:invalid" = which half
carries `isValid:false`. Q8 "OID=first" = the reading at T kept the `_id` it was first stored with.

### The object-id lab (`tools/lab/object-id/probes.js`) at `ab7b22d6`

Same builds and mongod, databases `oidlab_test1508` / `oidlab_testcand`, run with
`OID_STATE=<scratch> OID_MONGO_PORT=27521 node tools/lab/object-id/probes.js <name> <worktree> <port>`.
Only the cells that differ are listed; every other cell is equal on both builds.

| cell | 15.0.8 `92d08342` | `ab7b22d6` |
|---|---|---|
| P-ID-1 loop cached id onto string record | 200 / string:0.5,OID:0.8 | 200 / OID:0.8 |
| P-ID-2 GET string record | 404 | 200 |
| P-ID-2 PATCH string record | 404 / string:legacy | 200 / string:v3-patch |
| P-ID-2 DELETE string record | 404 / string:undefined | 200 / string:false |
| P-ID-2 PATCH UUID-string record | 404 / docs at that time n=1 | 200 / docs at that time n=1 |
| P-ID-3 re-send without _id | 200 / reply no _id | 200 / reply = stored |
| P-ID-3 re-send with a different hex _id | 500 / no reply body / stored:sgv111 | 200 / reply = stored / stored:sgv113 |
| P-ID-3 re-send onto a string record | 500 / string:120 | 200 / string:121 |
| P-ID-3 GET /entries/<UPPER> | n=0 | n=1 |
| P-ID-4 dbUpdate string record | {"result":"success"} / string:orig | {"result":"success"} / string:ws-edit |
| P-ID-4 dbRemove string record | {"result":"success"} / n=1 | {"result":"success"} / n=0 |
| P-ID-4 dbAdd with hex _id | ack = sent / string | ack = sent / OID |
| P-ID-4 dbUpdate after dbAdd | string:add | OID:add-edit |
| P-ID-4 dbAdd food with hex _id | string | OID |
| P-ID-5 profile copied with its _id | 200 / string | 200 / OID |
| P-ID-5 connector guard find[_id] | n=0 | n=1 |
| P-ID-5 connector update PUT | skipped (connector logs NOT_REPLACED) | 200 / n=1 |
| P-ID-6 profile re-POST | 500 / string | 500 / OID |
| P-ID-6 devicestatus POST, re-POST, find, DELETE | 200:string / 500:string / find n=0 / DELETE 200 n=1 | 200:OID / 500:OID / find n=1 / DELETE 200 n=0 |
| P-ID-6 food POST, re-POST, find, DELETE | 200:string / 200:string / find n/a / DELETE 200 n=1 | 200:OID / 200:OID / find n/a / DELETE 200 n=0 |
| P-ID-6 activity POST, re-POST, find, DELETE | 200:string / 200:string / find n=0 / DELETE 200 n=1 | 200:OID / 200:OID / find n=1 / DELETE 200 n=0 |
| P-ID-7 find[_id] on a twin | n=1 | n=2 |
| P-ID-7 v1 DELETE /treatments/<hex> (careportal, oref0 dedupe) | 200 / n=1 | 200 / n=0 |
| P-ID-7 websocket dbRemove (web UI Remove) | {"result":"success"} / n=1 | {"result":"success"} / n=0 |
| P-ID-11 GET find[_id][$in] [string, OID] | n=1 | n=2 |
| P-ID-11 DELETE find[_id][$in] [string, OID] | 200 / string n=1 / OID n=0 | 200 / string n=0 / OID n=0 |
| P-ID-12 subject POST with hex _id | 200 / string | 200 / none |
| P-ID-12 subject DELETE by that hex | 200 / n=1 | 200 / n=0 |

Equal on both builds: `P-ID-0 liveness before`, `P-ID-1 loop cached id onto OID record (control)`, `P-ID-1 xdripswift sensor start retried`, `P-ID-2 GET OID record (control)`, `P-ID-3 POST without _id`, `P-ID-3 GET /entries/<lower> (control)`, `P-ID-4 AAPS 3.x add then update (control)`, `P-ID-7 v3 permanent DELETE`, `P-ID-10 hex GET returns`, `P-ID-10 hex DELETE, then GET`, `P-ID-10 hex PUT`, `P-ID-10 non-hex GET returns`, `P-ID-10 non-hex DELETE, then GET`, `P-ID-10 non-hex PUT`, `P-ID-0 liveness after`.


# Per-client sections

## Android

### AndroidAPS

| | |
|---|---|
| repo | `externals/AndroidAPS` |
| local HEAD | `7e1d537d49` (= `origin/dev`, 2026-09-23, `4.0.0-dev-c`), detached |
| also read | `origin/master` `598e2eb39c` (2026-08-02, 3.4.2.6), via `git show`/`git grep` on the ref |
| staged index / dirty | `git diff --cached` empty; `git status --porcelain` empty |
| clients | master: NSClient v1 (socket.io main namespace, `dbAdd`/`dbUpdate`) and NSClient v3 (REST `/api/v3`). dev: v3 only (`git grep '"dbAdd"\|"dbUpdate"\|"dbRemove"\|api/v1' HEAD -- '*.kt'` finds only test comments) |

| use | what the client does | anchor |
|---|---|---|
| (a) id on create | **v1 (master):** `nsAdd` runs only when `ids.nightscoutId == null`; every `toJson(isAdd=true)` adds `_id` only if `nightscoutId != null`, so `dbAdd` never carries `_id`. Devicestatus JSON has no `_id` and no `NSCLIENT_ID` (`created_at`, `device`, `pump`, `openaps`, `uploaderBattery`, `isCharging`, `configuration`). Profile store JSON is built fresh (`defaultProfile`, `startDate`, `store`, `date`), no `_id`. **v3 (both):** create bodies have `identifier: String? = null`, and the serializer omits nulls (dev `explicitNulls = false`), so no `identifier` and no `_id` is sent; the server computes the v5 UUID identifier. | master `nsclient/DataSyncSelectorV1.kt:184-202` (same pattern per type), `:507-529` (devicestatus), `:786-805` (profile); `nsclient/extensions/BolusExtension.kt:26`; `DeviceStatusExtension.kt:8-22`; `plugins/main/.../ProfilePlugin.kt:398-422`; dev `core/nssdk/.../NsSdkJson.kt:58-61`, `remotemodel/RemoteTreatment.kt:24-25`, `NSAndroidClientImpl.kt:183-219,353,374` |
| (b) `find[_id]` / operators | **None** on either ref (no v1 REST). v3 reads use `date$gt`, `created_at$gt`, `/history/{srvModified}`. | prior map S2; dev `networking/NightscoutApi.kt:107-155` |
| (c) PUT/DELETE by id | **v3 (both):** edit = `PATCH /api/v3/treatments/{identifier}` (and entries); `isValid=false` = `DELETE /api/v3/treatments/{identifier}` without `permanent` (soft). 404 is treated as done; dev retries a 404 on a real UPDATE up to 5 times per id, then advances. The identifier is whatever the server listed: a v3 UUID, or for a v1 record without one, its `_id` string. | master `networking/NightscoutRemoteService.kt:68,71`, `NSAndroidClientImpl.kt:330`; dev `NightscoutApi.kt:134,139,167,172`, `NSAndroidClientImpl.kt:411-437`, `nsclientV3/NSClientV3Plugin.kt:701-720` |
| (d) websocket | **master v1:** `dbAdd {collection, data}` and `dbUpdate {collection, _id: nightscoutId, data}`; no `dbRemove`, no `dbUpdateUnset` (deletes are `dbUpdate` `isValid:false`). `nightscoutId` = the `_id` from the `dbAdd` ack (`responseArray[0].getString("_id")`), or on import `identifier ?: _id`. **An empty `[]` ack leaves `id = null` but still runs `processAddAck`; the worker sets `nightscoutId = null` and `confirmed = true`**, so the record is counted uploaded. dev: `/storage` and `/alarm` only (no db events). | master `nsclient/services/NSClientService.kt:595-625`; `acks/NSAddAck.kt:31-38`; `workers/NSClientAddAckWorker.kt:55-90`; `NSClientPlugin.kt:194-251`; `BolusExtension.kt:38-40` |
| (e) re-send same record | v1: an unacked `dbAdd` (60 s) stops the queue and is re-sent on the next resend, still without `_id`; the server's dedup (treatments `NSCLIENT_ID` or `created_at`+`eventType`; devicestatus `created_at`; profile `startDate`) answers the stored record. v3: devicestatus is created once per record; re-creates dedup on the server's identifier / fallback fields. No re-send carries `_id`. | master `DataSyncSelectorV1.kt:192-196,522-525`; prior map S15 |

| C-id | AndroidAPS master (v1 + v3) | AndroidAPS dev (v3) |
|---|---|---|
| C68 hex `_id` stored as ObjectId | unaffected (never sends `_id`) | unaffected |
| C69 re-POST same `_id` | unaffected | unaffected |
| C70 entries reply `_id` | unaffected (no v1 REST) | unaffected |
| C71 upper-case hex | unaffected in what it sends; see probe A3 for records other clients stored as an upper-case string | same |
| C72 `find[_id]` either form | unaffected | unaffected |
| C73 `$in`/`$nin` both forms | unaffected | unaffected |
| C74 delete removes every form | unaffected (no v1 DELETE, no `dbRemove`) | unaffected |
| C75 v3 identifier reaches string `_id` | **better**: PATCH/DELETE of a v1 record stored with a string `_id` answers 200 and applies, where 15.0.8 answered 404 and the client dropped (master) or retried 5 times then dropped (dev) the change. Twin case: see probe A2 | **better**, same |
| C76 ws `dbUpdate` either form, many | **better**: a `dbUpdate` (edit or soft delete) by a 24-hex `nightscoutId` now reaches a string-stored record and both halves of a twin; a UUID `nightscoutId` (from a v3-created record) is matched exactly, as before | n/a |
| C77 ws `dbAdd` conversion / `[]` on collision | unaffected: the new pre-insert lookup runs only for a 24-hex `data._id`, which AAPS never sends; its devicestatus/treatment/profile dedup queries are unchanged | n/a |
| C78 devicestatus resend guard | unaffected (v1 socket path, no `_id`) | unaffected (v3 path, no `_id`) |
| C79 auth subject remove | unaffected (no subject writes) | unaffected |
| C80 profile PUT 12-char id | unaffected | unaffected |
| C81 entries `$setOnInsert` `_id` | unaffected | unaffected |

Safety questions (read-derived): no AAPS devicestatus, glucose value or treatment upload carries a
24-hex `_id` or a client `identifier`, so #8758's create, re-send and collision paths are not
reached and none of them can refuse or deduplicate a new loop status or CGM value. No AAPS path
deletes by `_id`. AAPS stores ids as the strings the server serialises; an ObjectId serialises as
lower-case hex on every build, so a record whose storage form changes from lower-case string to
ObjectId keeps the same `nightscoutId` / `identifier`.

Pre-existing, not changed by #8758, worth knowing for C77: on master v1 an empty `dbAdd` ack marks
the record uploaded with `nightscoutId = null` (`NSAddAck.kt:31-38`, `NSClientAddAckWorker.kt:55-90`).
Any server path that answers `[]` therefore loses that record from Nightscout silently. #8758 adds
`[]` answers only for a `dbAdd` carrying a 24-hex `_id`, which AAPS does not send.

#### Candidate probes (AndroidAPS), with results

- **A1 (control, should be identical on all builds)** — v1 socket, master shapes. Connect `/`,
  `authorize {client:"Android_AAPS", history:48, status:true, from:0, secret:<sha1(API_SECRET)>}`;
  `dbAdd {collection:"devicestatus", data:{created_at:"2026-09-25T10:00:00.000Z", device:"openaps://synthetic", openaps:{suggested:{bg:120,COB:0,IOB:0.5,timestamp:"2026-09-25T10:00:00.000Z"}}, uploaderBattery:80}}`
  → expect `[doc]` with a 24-hex `_id`; repeat the same `dbAdd` → expect the same `_id` (created_at
  dedup); then `dbAdd {collection:"entries", data:{type:"sgv", sgv:120, date:1790330400000, dateString:"2026-09-25T10:00:00.000Z", device:"AndroidAPS-synthetic"}}` → `[doc]`. Record stored count and `_id` BSON type from mongo. Purpose: prove no `[]` for AAPS shapes.
  **Measured Q9:** identical on both builds: `[doc]` twice, the same `_id`, one stored status; the sgv `dbAdd` `[doc]`, one stored.
- **A2 (cannot tell)** — v3 soft DELETE on a twin. Seed in mongo: treatment `{_id:"<H>" (string), created_at:"2026-09-25T09:00:00.000Z", eventType:"Correction Bolus", insulin:1.0}` plus `{_id:ObjectId("<H>"), same fields}`. `DELETE /api/v3/treatments/<H>` (no `permanent`), then `GET /api/v3/treatments/<H>` and `GET /api/v1/treatments.json?find[_id]=<H>`. Record which half got `isValid:false` and whether v1 still lists a valid copy. Compare 15.0.8 and candidate.
  **Measured Q10, Q10b:** both builds mark one half invalid and leave the other valid (15.0.8 the string half valid, `ab7b22d6` the ObjectId half valid); the valid half is returned by v1 time-window reads and v3 search on both. Same effect on both builds; CANDIDATE-3.
- **A3 (cannot tell, edge)** — upper-case string `_id` changing spelling. Seed a treatment with `_id:"<H-UPPER>"` (string). Another client `PUT /api/v1/treatments {_id:"<H-UPPER>", created_at:…, eventType:"Note", notes:"edit"}`. Then `GET /api/v3/treatments/history/0` and `GET /api/v1/treatments.json?find[created_at][$gte]=…`: record the identifiers listed before and after. On the candidate the record is expected to reappear under the lower-case hex with the upper-case string removed (no deletion marker in v3 history), which an AAPS follower would see as a new record beside its old one.
  **Measured Q11:** 15.0.8 keeps the upper-case string and adds an ObjectId copy; `ab7b22d6` leaves one ObjectId record. `/api/v3/treatments/history` lists neither change on either build (a v1 PUT sets no `srvModified`). Not worse than 15.0.8: on both builds a v3 follower misses the edit.

### xDrip+ (Android)

| | |
|---|---|
| repo | `externals/xDrip` |
| local HEAD | `1ed760048a` (2026-09-18), detached; the prior map read `origin/master` = this sha |
| staged index / dirty | `git diff --cached` empty; `git status --porcelain` empty |
| API | v1 REST only (Retrofit); no socket, no v3 |

| use | what the client does | anchor (`xDrip@1ed760048a`, `app/src/main/java/com/eveningoutpost/dexdrip/utilitymodels/NightscoutUploader.java` unless named) |
|---|---|---|
| (a) id on create | **Treatments:** inserts and updates both go out as `PUT /api/v1/treatments`, one per request, with `_id = uuid_to_id(uuid)` and `uuid` in the body. `uuid_to_id`: contains `:` or shorter than 24 → first 24 hex of MD5 (lower case); exactly 24 → used as is; otherwise dashes removed and the first 24 characters kept (lower-case hex for a Java `UUID`). **Entries** (sgv, mbg, cal), **devicestatus** and **activity** are POSTed with no `_id`. | `:245-256`, `:880-900`; POST routes `:130-140,161` |
| (b) `find[_id]` / operators | None. Lookup is `GET treatments.json?find[uuid]=<uuid>` and reads `[0]._id`. | `:155-156`, `:816-834` |
| (c) PUT/DELETE by id | `PUT /api/v1/treatments` (above). `DELETE /api/v1/treatments/<id>` where `<id>` is the queue's 24-char `reference_uuid` or the `_id` from the uuid lookup; a lookup that finds nothing marks the delete done. | `:158-159`, `:810-848` |
| (d) websocket | None. | prior map S6 |
| (e) re-send same record | Treatments: a failed PUT stays queued and is re-sent with the same derived `_id` (upsert by `_id`). Entries: the whole batch is re-POSTed without `_id` on any non-2xx; the response body is not read. Devicestatus is posted after entries succeed, without `_id`, errors ignored. Downloaded treatments without `uuid` take the Nightscout `_id` as their uuid, so a later local edit PUTs back with that same `_id`. | `:576-586`, `:887-900`; `NightscoutTreatments.java:39-47` |

| C-id | xDrip |
|---|---|
| C68 | unaffected (treatments already converted since 15.0.7; entries/devicestatus/activity carry no `_id`) |
| C69 | **better**: a PUT re-send over a treatment stored with the string `_id` (15.0.6 or earlier, or a downloaded record keyed by it) leaves one record instead of adding an ObjectId copy |
| C70 | unaffected (entries response not read) |
| C71 | **better** in one edge: a downloaded treatment whose Nightscout `_id` is an upper-case string is PUT back with that spelling; the candidate converts it and removes the string form |
| C72 | **better**: `DELETE /treatments/<id>` reaches a string-stored treatment |
| C73 | unaffected |
| C74 | **better** (intended, BF-110): a delete by id removes both halves of a twin; 15.0.8 left the string half, which re-downloads as a live treatment |
| C75 | unaffected |
| C76, C77 | unaffected (no socket) |
| C78 | unaffected (devicestatus has no `_id`) |
| C79, C80 | unaffected |
| C81 | unaffected (entries carry no `_id`) |

Safety questions (read-derived): no xDrip entries or devicestatus upload carries `_id`, so none
reaches the resend guard or the entries `$setOnInsert` path; glucose uploads are unaffected. Deletes
can remove more than on 15.0.8 only where a twin exists for that id, and then only the copy of the
same record. The optional direct-MongoDB uploader bypasses the API and is not covered.

#### Candidate probes (xDrip)

- **X1 (control, should improve)** — covered by lab P-ID-7 and P-ID-1 shapes; the xDrip-specific
  body: seed a string-`_id` treatment `{_id:"0123456789abcdef01234567", uuid:"01234567-89ab-cdef-0123-456789abcdef", created_at:"2026-09-25T09:00:00.000Z", eventType:"Carb Correction", carbs:10}`; `PUT /api/v1/treatments` with the same `_id` and `uuid`, `carbs:12`, `timestamp:1790326800000`, `sysTime:"2026-09-25T09:00:00.000Z"`; count documents with that hex in either form (expect 2 on 15.0.8, 1 on the candidate); then `GET /api/v1/treatments.json?find[uuid]=01234567-89ab-cdef-0123-456789abcdef` → `DELETE /api/v1/treatments/<[0]._id>` → count (expect 0 on the candidate, 1 on 15.0.8).
  **Measured (same server shapes):** P-ID-1 (PUT/POST by `_id` onto a string record: 15.0.8 string + ObjectId copy, `ab7b22d6` one ObjectId record) and Q12/P-ID-7 (DELETE by hex on a twin: 1 left → 0 left). The xDrip `find[uuid]` step itself was not replayed.

### xdrip-js

| | |
|---|---|
| repo | `externals/xdrip-js` |
| local HEAD | `e30127358f` (= the `origin/dev` the prior map grepped), detached; the prior map's local HEAD was `0cd1c55` |
| staged index / dirty | `git diff --cached` empty; `git status --porcelain` empty |

No Nightscout requests: `git grep -n -i -E 'api/v[123]|nightscout|_id|axios|request\(|fetch\(|socket.io' HEAD -- . ':!*.md' ':!package-lock.json'`
hits only BLE constants (`lib/bluetooth-manager.js:114-115`, `lib/keks_plugin/ble-packet.js:73-76`),
which is also the positive control that the grep reaches the code. Every C-id: unaffected.

## iOS

### Loop (LoopWorkspace + NightscoutService + NightscoutKit)

| | |
|---|---|
| repos | `externals/LoopWorkspace`, submodules `NightscoutService`, `NightscoutRemoteCGM`, `Loop`, `LoopKit`; `externals/NightscoutKit` (SPM, pinned `branch: main` in LoopWorkspace's `Package.resolved`) |
| HEAD | LoopWorkspace `f8412858c5`; NightscoutService `fe075ef0`; NightscoutRemoteCGM `e2230e33`; Loop `c2fddb76`; LoopKit `325bd820`; NightscoutKit `4ec9fd12a1` (branch `main`) |
| staged index | empty in LoopWorkspace, NightscoutService, NightscoutRemoteCGM, Loop, LoopKit, NightscoutKit; working trees clean |
| Nightscout code | NightscoutKit `Sources/NightscoutKit/NightscoutClient.swift` (all HTTP); NightscoutService `NightscoutServiceKit/NightscoutService.swift`, `Extensions/*.swift`, `ObjectIdCache.swift`. Loop, LoopKit: no Nightscout HTTP (`git grep '"_id"\|api/v1/\|api/v3\|dbAdd\|socket\.io'` → 0 hits; control: `Loop/Managers/DeviceDataManager.swift:408` builds `RemoteDataServicesManager`). NightscoutRemoteCGM reads through `NightscoutClient.fetchGlucose` (`NightscoutRemoteCGM/NightscoutFetcher.swift:25,30`) |

| item | what the client does | anchor |
|---|---|---|
| (a) `_id` on create | **Overrides:** `POST /api/v1/treatments` with `_id` = `override.syncIdentifier.uuidString` (upper-case UUID, non-hex). **Carbs, doses (bolus, temp basal, suspend), pump/CGM events, remote-command treatments:** no `_id`. **Entries:** no `_id` (`GlucoseEntry.id` is nil for Loop's samples; `representation["_id"] = nil` sets no key). **Devicestatus:** no `_id`, optional `identifier` field only if set, and Loop does not set it. **Profile:** no `_id` (`ProfileSet.dictionaryRepresentation` has none). | NightscoutService `Extensions/OverrideTreament.swift:59`; `Extensions/DoseEntry.swift:30,61` (commented out); `Extensions/SyncCarbObject.swift:16-21` (`objectId` nil on create, `NightscoutUploader.swift:20`); `Extensions/StoredGlucoseSample.swift:34-42`; `Extensions/StoredDosingDecision.swift:148-160`; NightscoutKit `Models/GlucoseEntry.swift:108`, `Models/DeviceStatus.swift:60-62`, `Models/ProfileSet.swift:143-164`, `Models/Treatments/NightscoutTreatment.swift:111` |
| (b) `_id` queries | None. No `find[_id]`, no `$in`. Reads filter only `dateString`, `created_at`, `startDate`. | NightscoutKit `NightscoutClient.swift:188-189,226-227,264-265,302-303` |
| (c) PUT/DELETE by id | **Carbs edit:** `PUT /api/v1/treatments` with `_id` = the 24-hex id cached from the POST reply (`ObjectIdCache`, 24 h). **Carbs and dose delete:** `DELETE /api/v1/treatments/<24-hex from cache>`. **Override delete:** `DELETE /api/v1/treatments/<UPPER-CASE UUID>`, then re-POST under the same UUID. `updateProfile` (PUT profile with a caller `_id`) exists in NightscoutKit but Loop has no call site. No v3. | NightscoutService `NightscoutUploader.swift:30-43,52-66,149-163`; `NightscoutService.swift:160-185,207-227,246-265`; NightscoutKit `NightscoutClient.swift:74-100,130-155,410-419,430-455` |
| (d) websocket | None (no socket library in `Package.resolved`). | LoopWorkspace `LoopWorkspace.xcworkspace/xcshareddata/swiftpm/Package.resolved` |
| (e) re-send | A failed batch is re-sent whole on the next trigger. Entries and devicestatus are re-sent **without** `_id`: entries upsert on `sysTime`+`type`; devicestatus inserts again (a second copy, same on every build). NightscoutKit's `flushEntries` requeues on failure. The carbs id cache is filled from the treatments POST reply (`postToNS` requires one reply item per request item). | NightscoutKit `NightscoutClient.swift:481-510,650-667`; NightscoutService `NightscoutService.swift:207-213,250-256,304` |

| C-id | class | why |
|---|---|---|
| C68 hex `_id` stored as ObjectId | n/a | no hex `_id` sent on create in any collection |
| C69 re-POST same `_id` | n/a | devicestatus/profile re-sends carry no `_id`; override re-POST carries a UUID (non-hex path, unchanged) |
| C70 entries reply `_id` = stored | U | `uploadEntries` maps the reply to `Bool`; entry ids are not kept |
| C71 upper-case hex | n/a | the only upper-case id is a UUID (non-hex); cached hex ids are the server's lower-case |
| C72 `find[_id]` / DELETE by id either form | B | `DELETE /treatments/<hex>` for carbs and doses now also reaches a string-stored copy |
| C73 `$in`/`$nin` both forms | n/a | not sent |
| C74 delete removes every form | B | a carb whose edit left an ObjectId copy beside a ≤15.0.6 string record is removed completely (both halves are the same carb) |
| C75 v3 | n/a | no v3 |
| C76, C77 websocket | n/a | no socket |
| C78 devicestatus resend guard | n/a | devicestatus has no `_id` |
| C79 subjects | n/a | no subject calls |
| C80 profile PUT 12-char id | n/a | no profile PUT call site |
| C81 entries `_id` on insert only | n/a | entries carry no `_id` |
| treatments PUT by hex over string record (C72 family, treatments `staleFormsFor`) | B | a carb edit leaves one record instead of adding a copy |

Safety questions: no Loop devicestatus or CGM entry carries a hex `_id`, so no #8758 path can refuse or
dedupe one. Deletes reach more only where two copies of the same carb/dose exist.


### Trio

| | |
|---|---|
| repo | `externals/Trio` |
| HEAD | `e41c9db37f` (detached; = `origin/dev` as recorded by the 2026-09-23 survey) |
| staged index | empty; working tree clean |
| Nightscout code | `Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift`, `NightscoutManager.swift`; models in `Trio/Sources/Models/` |

| item | what the client does | anchor |
|---|---|---|
| (a) `_id` on create | **Never sends `_id`.** Uploads are `[NightscoutTreatment]`, `[BloodGlucose]`, `NightscoutStatus`, `NightscoutProfileStore`, `[NightscoutExercise]`. `NightscoutTreatment` codes a plain `id`; `BloodGlucose` encodes `_id` only from `legacyId`, which is nil for every locally built reading (`id` = upper-case `UUID().uuidString` in a plain `id` field). No `_id` in `NightscoutStatus.swift`, `NightscoutTreatment.swift`, `NightscoutExercise.swift`. (`CarbsEntry` and `TempTarget` map `id`↔`_id`, but they are decode models for reads; uploads use `NightscoutTreatment`.) | `NightscoutAPI.swift:298,338,477` (upload signatures); `Models/NightscoutTreatment.swift:62`; `Models/BloodGlucose.swift:61,81-85,157`; `APS/Storage/GlucoseStorage.swift:531-532,565-575` (`id: glucose.id?.uuidString ?? UUID().uuidString`, no `legacyId`) |
| (b) `_id` queries | None. Deletes filter the plain `id` field: `DELETE /api/v1/treatments.json?find[id][$eq]=<UUID>` (carbs, insulin), `DELETE /api/v1/entries.json?find[$or][0][id][$eq]=<UUID>&find[$or][1][dateString][$eq]=<ISO>` (glucose). | `NightscoutAPI.swift:160-186,188-222,224-250` |
| (c) PUT/DELETE by id | No PUT. No `/…/<_id>` path. Override edit = `DELETE …treatments.json?find[created_at][$eq]=<ISO>&find[eventType][$eq]=Exercise`, then POST. No v3. | `NightscoutAPI.swift:445-475` |
| (d) websocket | None. | `Trio.xcworkspace/xcshareddata/swiftpm/Package.resolved` (no socket entry) |
| (e) re-send | Failed chunks (100) are re-POSTed without `_id`; devicestatus re-sends insert again (unchanged on every build). | `NightscoutManager.swift:692`; survey `clients/ios/Trio.md` S15 |

| C-id | class | why |
|---|---|---|
| C68, C69, C71, C78, C81 | n/a | no `_id` on any write |
| C70 entries reply `_id` | U | the POST reply body is discarded |
| C72, C73, C74 | n/a | `_id` never queried or deleted by; `find[id]` is a different field, untouched by #8758 |
| C75, C76, C77, C79, C80 | n/a | no v3, no socket, no subjects, no profile PUT |

Safety questions: nothing Trio sends reaches any #8758 code path.


### xDrip4iOS (xdripswift)

| | |
|---|---|
| repo | `externals/xdripswift` |
| HEAD | `c268542e64` (detached), **equal to `origin/master` and `origin/develop`** (`git rev-parse`), 2026-09-22 "version 7.1.1 - build 4233". The 2026-09-23 survey read the same commit through `git show` while the checkout was elsewhere; HEAD is now that commit. |
| staged index | empty; working tree clean (`git status --porcelain` = 0 lines) |
| Nightscout code | `xDrip/Managers/Nightscout/NightscoutSyncManager.swift`, `BgReading+Nightscout.swift`, `Calibration+Nightscout.swift`, `NightscoutImportService.swift`; `xDrip/Core Data/classes/TreatmentEntry+CoreDataClass.swift`; `xDrip/Utilities/UniqueId.swift` |

| item | what the client does | anchor |
|---|---|---|
| (a) `_id` on create | **Entries (sgv), calibrations (`cal`, `mbg`):** `_id` = `UniqueId.createEventId()`, 24 random characters from `[a-zA-Z0-9]`, so almost never 24-hex (chance a random id is all hex ≈ (22/62)^24 ≈ 2×10⁻¹¹). The server treats it as a non-hex string (stripped, or moved to `identifier` with `UUID_HANDLING`), with the same regex on every build. **Master-mode Sensor Start** treatment: `_id` = `sensor.id` (same generator, non-hex). **LibreLinkUp follower Sensor Start:** `_id` = `"6c6c75000000" + 12 hex digits of the start ms` — **24-hex lower-case**, deterministic so a retry is idempotent. **Treatments created locally:** no `_id` until uploaded (`EmptyId`). **Devicestatus:** no `_id` (uploader battery only). | `Utilities/UniqueId.swift:18-26`; `Nightscout/BgReading+Nightscout.swift:9`; `Nightscout/Calibration+Nightscout.swift:17,36`; `NightscoutSyncManager.swift:1427-1432,1448-1468,1476-1482,1393-1411`; `TreatmentEntry+CoreDataClass.swift:183-186` |
| (b) `_id` queries | **Remote-deletion reconciliation:** for each local treatment missing from the bulk download, `GET /api/v1/treatments?find[_id]=<remoteID>&count=1`; an empty answer marks the local treatment deleted. `remoteID` is the server's lower-case hex. No `find[_id][$in]`. The only list is `find[date][$in][]` (timestamps, entries delete, ≤50 per request), not `_id`. | `NightscoutSyncManager.swift:1214-1226,795-806` |
| (c) PUT/DELETE by id | **Edit:** `PUT /api/v1/treatments` with `_id` = the id before the first `-` (server hex) and all parts of a multi-part treatment. **Delete last part:** `DELETE /api/v1/treatments/<hex>`. **Entries replace:** re-POST with `_id` removed (server `sysTime`+`type` upsert). No v3. | `NightscoutSyncManager.swift:1882-1920,1935-1996` (DELETE at `:1990`); `:419-425` |
| (d) websocket | None. | `xdrip.xcodeproj/project.pbxproj` (no package references) |
| (e) re-send | Entries: the batch is re-sent until 2xx, same random `_id`; a 500 whose body has `description.code == 66` counts as success. LibreLinkUp Sensor Start retried with the same hex `_id` until 2xx. | survey `clients/ios/xdripswift.md` S15; `NightscoutSyncManager.swift:1452-1468` |

| C-id | class | why |
|---|---|---|
| C68 | U | the one hex `_id` on create is a treatment; treatments already stored hex as ObjectId since 15.0.7 |
| C69 re-POST same `_id` | U | Sensor Start retry: treatments upsert by `_id` replaces on every build (the 2026-09-24 lab cell P-ID-1 "xdripswift sensor start retried": 200 / 200 / OID on 15.0.8, dev and `6d120fa2`) |
| C70 entries reply `_id` | U | entries POST reply is not used for ids |
| C71 upper-case hex | n/a | all hex ids it sends are server-issued lower case or its own lower-case Sensor Start id |
| C72 `find[_id]` either form | B | reconciliation now finds a treatment stored with a string `_id`, so fewer local treatments are wrongly marked deleted; no new matches for other ids (the widening is limited to forms of the same id) |
| C73 `$in`/`$nin` | n/a | its `$in` is on `date`, not `_id` |
| C74 delete removes every form | B | `DELETE /treatments/<hex>` removes both halves of a twin of the same treatment |
| treatments PUT over string record | B | an edit leaves one record, not a copy |
| C75–C80 | n/a | no v3, socket, subjects or profile writes |
| C81 entries `_id` on insert only | U | entries `_id` is non-hex and stripped before this code; the `code 66` workaround is for the 500 that C81 removes, and remains harmless |

Safety questions: its CGM entries carry a non-hex `_id`, so C68/C81 do not act on them; no devicestatus
`_id`. Deletes reach more only for twins of one treatment.


### LoopFollow

| | |
|---|---|
| repo | `externals/LoopFollow` |
| HEAD | `4a74b781ad` (detached; = the `origin/main` the survey read) |
| staged index | empty; working tree clean |

| item | what the client does | anchor |
|---|---|---|
| (a) `_id` on create | Writes no data records. Creates one auth subject: `POST /api/v2/authorization/subjects` `{name, roles:["readable"]}`, **no `_id`**, then derives the access token locally from the returned `_id` (decodes array or bare object). Reuses an existing subject by name first. | `LoopFollow/Helpers/NightscoutUtils.swift:443-461,503-532` |
| (b) `_id` queries | None. Reads `_id` from treatments only as a display key. | `Treatments/TreatmentsView.swift:1163` |
| (c) PUT/DELETE by id | None. `executePostRequest` (two overloads) has **no call sites**. No subject delete. | `NightscoutUtils.swift:348,378` (`git grep executePostRequest` → only the definitions) |
| (d) websocket | socket.io `authorize` + `dataUpdate` only; no `dbAdd`/`dbUpdate`/`dbRemove`. | survey `clients/ios/LoopFollow.md` S6 |
| (e) re-send | n/a (no writes besides the subject). | — |

| C-id | class | why |
|---|---|---|
| C79 subject remove either form | n/a | never deletes a subject; create sends no `_id`, and #8758 at `ab7b22d6` leaves subject create as dev has it |
| all others | n/a | no data writes, no `_id` queries, no data socket writes |


### LoopCaregiver

| | |
|---|---|
| repo | `externals/LoopCaregiver` |
| HEAD | `230571838c` (detached; = the `origin/dev` the survey read) |
| staged index | empty; working tree clean |
| dependency | `gestrich/NightscoutKit` branch `feature/2023-07/bg/remote-commands` revision `d63fb737…` (`LoopCaregiver.xcworkspace/xcshareddata/swiftpm/Package.resolved:31-36`). **That revision is not in the corpus** (`git -C externals/NightscoutKit cat-file -t d63fb737…` → no such object), so the fork's anchors in the 2026-09-23 file could not be re-verified here. |

| item | what the client does | anchor |
|---|---|---|
| (a)–(c) | LoopCaregiver itself calls no treatment upload, update or delete, and no profile update (`git grep uploadTreatments\|deleteTreatment\|updateProfile\|postToNS\|upload(` → none). Remote commands are Loop push notifications. The only delete is `deleteRemoteCommands()` → `/api/v2/remotecommands` (not a Nightscout endpoint; pre-existing). | `LoopCaregiverKit/Sources/LoopCaregiverKit/Nightscout/NightscoutDataSource.swift:214`; `Models/RemoteDataServiceManager.swift:79,167` |
| (d) websocket | None. | survey file S6 |
| (e) re-send | n/a. | — |

| C-id | class | why |
|---|---|---|
| all | n/a | no `_id` sent, queried, or deleted by at the recorded HEAD. The fork's unused `updateProfile`/`postToNS` would matter only if a call site is added |


### nightguard

| | |
|---|---|
| repo | `externals/nightguard` |
| HEAD | `75404bd204` (detached; = the `origin/master` the survey read) |
| staged index | empty; working tree clean |

| item | what the client does | anchor |
|---|---|---|
| (a) `_id` on create | Treatments (Temporary Target, cancel = new target with `duration: 0`, Carb Correction, site/sensor/battery change) are POSTed to `/api/v3/treatments`, with `/api/v1/treatments` as fallback, **without `_id` or `identifier`**. The server computes the v3 identifier. | `nightguard/external/NightscoutService.swift:1868-1955` (v3 path `:1950`, v1 fallback `:1953`) |
| (b) `_id` queries | None. Reads `identifier` and `_id` as local keys, `identifier` first. | `nightguard/domain/treatment/TreatmentsStream.swift:107`; `NightscoutService.swift:929-930` |
| (c) PUT/DELETE by id | None (no PUT, PATCH, DELETE). | survey file S7/S8 |
| (d) websocket | None. | survey file S6 |
| (e) re-send | No retry loop. | survey file S15 |

| C-id | class | why |
|---|---|---|
| C75 v3 identifier | U | v3 create's dedup filter gains a branch for a v1 record whose `_id` equals the (server-computed, non-hex) identifier; no such v1 record exists for a nightguard treatment. No v3 read/PATCH/DELETE by identifier |
| all others | n/a | — |


### DiaBLE

| | |
|---|---|
| repo | `externals/DiaBLE` |
| HEAD | `e6a909c88f` (detached; = the `origin/main` the survey read) |
| staged index | empty; working tree clean |

| item | what the client does | anchor |
|---|---|---|
| (a) `_id` on create | `POST /api/v1/entries` items `{type:"sgv", dateString, date, sgv, device}`, **no `_id`**. | `DiaBLE/Nightscout.swift:155-167` |
| (b)–(d) | None. The `delete()` helper (`DELETE`, free-form query) has no caller (`git grep '\.delete('` in `DiaBLE/*.swift` → none). No socket. | `DiaBLE/Nightscout.swift:170-199` |
| (e) re-send | Each cycle re-POSTs readings newer than the newest `date` it read; the server upserts on `sysTime`+`type`. | `DiaBLE/MainDelegate.swift:432-439` |

| C-id | class | why |
|---|---|---|
| C70 entries reply `_id` | U | reply not read for ids |
| all others | n/a | — |


### GlookoServiceKit

| | |
|---|---|
| repo | `externals/GlookoServiceKit` |
| HEAD | `8e2cad1cdf` (branch `main`) |
| staged index | empty; working tree clean |

Uploads Loop/Trio data **to Glooko**; makes no Nightscout request. Its `/api/v3/…` paths and `put`
calls are Glooko's (`GlookoServiceKit/Data/Classic/GlookoClassicAPI.swift:110,125,168`;
`GlookoClassicBackend.swift:37,83,99-100`). Every C-id: n/a.


### Candidate replay probes (iOS), with results

No client in this group has a **W** or **?** cell. The probes below are regression controls for the
three shapes these clients do send into #8758 code, cheap enough to run beside any other probe.
Synthetic values; `S` = the API secret's SHA-1 in the `api-secret` header.

1. **Loop carbs edit/delete by cached id (C72/C74, treatments PUT).**
   `POST /api/v1/treatments` `[{"eventType":"Carb Correction","carbs":20,"created_at":"2026-09-25T10:00:00Z","timestamp":"2026-09-25T10:00:00Z","enteredBy":"loop://probe"}]` → keep reply `[0]._id` as `H`;
   `PUT /api/v1/treatments` `{"_id":"H","eventType":"Carb Correction","carbs":25,"created_at":"2026-09-25T10:00:00Z","timestamp":"2026-09-25T10:00:00Z","enteredBy":"loop://probe"}`;
   `GET /api/v1/treatments.json?find[_id]=H` → expect 1 record, carbs 25, on all builds;
   `DELETE /api/v1/treatments/H` → expect 0 left. Variant with a string twin seeded in mongo
   (`{_id:"H"}` string plus ObjectId `H`): 15.0.8 leaves the string copy; `ab7b22d6` leaves none.
   **Measured Q12:** POST 200, PUT 200, find n=1, DELETE 200, 0 left, on both builds; twin variant 1 left → 0 left.
2. **Loop override delete-then-repost (non-hex path, unchanged).**
   `POST /api/v1/treatments` `[{"_id":"0F1E2D3C-4B5A-6978-8796-A5B4C3D2E1F0","eventType":"Temporary Override","created_at":"2026-09-25T11:00:00Z","timestamp":"2026-09-25T11:00:00Z","duration":60,"reason":"probe","enteredBy":"loop://probe"}]`;
   `DELETE /api/v1/treatments/0F1E2D3C-4B5A-6978-8796-A5B4C3D2E1F0` → expect deleted (with `UUID_HANDLING` unset/true);
   re-POST the same body → expect exactly 1 record. Expect identical results on 15.0.8 and `ab7b22d6`.
   Not replayed in this pass; the 2026-09-23 lab (survey §4) measured this delete as 200 and deleted on every build with `UUID_HANDLING` unset or true.
3. **xDrip4iOS reconciliation (C72).** Seed one treatment stored with string `_id` `"5f0c0ffee0ddba11c0ffee01"` and one with ObjectId `5f0c0ffee0ddba11c0ffee02`;
   `GET /api/v1/treatments?find[_id]=5f0c0ffee0ddba11c0ffee01&count=1` and `…02…` → 15.0.8: `[]`, 1; `ab7b22d6`: 1, 1.
   Negative control: `find[_id]=5f0c0ffee0ddba11c0ffee03` (absent) → `[]` on both.
   **Measured Q14:** string record n=0 → n=1; ObjectId record n=1 on both; absent n=0 on both.
4. **xDrip4iOS LibreLinkUp Sensor Start retry (C69 treatments).**
   `POST /api/v1/treatments` `{"_id":"6c6c7500000001925a3b4c00","eventType":"Sensor Start","created_at":"2026-09-25T09:00:00.000Z","enteredBy":"xDrip4iOS"}` twice → 200, 200, one record stored as ObjectId, on both builds.
   **Measured P-ID-1 "xdripswift sensor start retried":** 200 / 200 / OID on both builds.

## Uploaders

Sink paths and the in-process connector are described in the nightscout-connect section.

### nightscout-connect

| | |
|---|---|
| repo | `externals/nightscout-connect` |
| HEAD | `04102f9d26` (branch `dev`, "start 0.1.1 development"), `git describe` = `v0.1.0-1-g04102f9`, `package.json` version `0.1.1` |
| release | tag `v0.1.0` = `4dde1ecd`; `git diff --stat v0.1.0 HEAD` changes only `package.json` and `package-lock.json` |
| prior survey ref | `977da8a` (`0.1.0-dev.3`); `git diff --stat 977da8a HEAD -- lib` is empty, so every `lib/` anchor below holds for `0.1.0-dev.3`, `v0.1.0` and HEAD |
| staged / dirty | 0 / 0 |
| server wiring | `ab7b22d6:lib/server/bootevent.js:384` `ctx.nightscoutConnect = require('nightscout-connect')(env, ctx)`; `ab7b22d6:package.json:140` pins `"nightscout-connect": "0.1.0"` |

Sink paths. In-process (built into Nightscout) the output is `lib/outputs/internal.js`, which
calls the server's storage modules directly, bypassing the v1 routes and their `_id` validation:
`ctx.entries.create`, `ctx.treatments.create`, `ctx.devicestatus.create`, `ctx.profile.create`
(`internal.js:37-42`, `:158-163`), `ctx.profile.list_query` + `ctx.profile.save` for profile
replace (`:73-91`), `ctx.treatments.remove` and `ctx.devicestatus.remove` for Glooko bookkeeping
(`:164-170`). Standalone, `lib/outputs/nightscout.js` sends the same records over HTTP:
`POST /api/v1/entries.json` (`:63`), `POST /api/v1/treatments.json` (`:109`),
`POST /api/v1/devicestatus.json` (`:161`, `:298`), `POST`/`PUT /api/v1/profile.json` (`:222`, `:194`),
`GET /api/v1/profiles.json?find[_id]=` (`:187`), `DELETE /api/v1/treatments.json` and
`DELETE /api/v1/devicestatus.json` by filter (`:294`, `:299`).

| surface | what it does | anchor (nightscout-connect@04102f9d26) |
|---|---|---|
| (a) `_id` on create | The Nightscout source hands records to the sink unchanged, so entries, treatments, devicestatus and profiles carry the **source site's `_id`**, a 24-hex lower-case string after JSON (the source's ObjectId), or whatever non-hex string the source stored. Source reads: `find[<field>][$gt]=<since>` with `count: sourceMaxCount` (default 1000), one GET per collection. Profiles are deduplicated by `String(_id)` within a poll. Glooko and LibreLinkUp sources create records without `_id` (Glooko treatments carry `identifier: 'glooko:…'`). Glooko checkpoints are devicestatus rows without `_id`. | `lib/sources/nightscout.js:54-60`, `:104-112`; `lib/outputs/glooko-checkpoint.js:40-46` |
| (b) `_id` operators | Profile replace guard: `find[_id]=String(id)` with `count: 10` (in-process `list_query`; HTTP `/api/v1/profiles.json` via `qs.stringify`). Glooko checkpoint cleanup: `find[_id][$in]=<obsolete ids>` plus `device`, `created_at $gte epoch`, `glookoSyncState.owner` (in-process the ids are the stored `_id` values, ObjectId instances; over HTTP they are hex strings, indices form). | `internal.js:73-79`; `nightscout.js:186-188`; `glooko-checkpoint.js:48-51`; `nightscout.js:39-40`, `:299` |
| (c) PUT/DELETE by id | Profile replace: `ctx.profile.save(p)` / `PUT /api/v1/profile.json` with the source `_id`, only when the `find[_id]` guard returns the profile. No v1 DELETE by path id. No v3. | `internal.js:80-91`; `nightscout.js:190-201` |
| (d) websocket | None. | (absence: `git grep -n "dbAdd\|socket.io" HEAD -- lib` has no hit) |
| (e) re-send, same `_id` | **Entries**: every cycle re-reads from the sink bookmark (`known.entries` from the newest stored `dateString`), so the newest source reading is normally re-sent with the same `_id`; the sink upserts on `sysTime`+`type`. **Treatments**: re-sent likewise; the sink upserts by `identifier`, else `_id`, else `created_at`+`eventType`. **Devicestatus**: before writing, the sink drops every row whose `created_at` is not strictly newer than the newest stored devicestatus of any device (Nightscout source) or of its own device (Glooko, LibreLinkUp), so a stored devicestatus is not re-sent in steady state. **Profiles**: `sync.plan` creates only profiles whose `_id`/`identifier` is not among the stored profiles read (`ctx.profile.list(…, 1000)`); a known `_id` with changed content goes to replace. A failed write fails the whole persist and the bookmark does not move, so the same window is re-sent next cycle. | `internal.js:133-157`, `:158-163`, `:171-181`, `:92-112`, `:207-217`; `lib/outputs/profile-sync.js:53-66`; `nightscout.js:117-169`, `:205-234` |

| C-id | class | why (read-derived unless a lab cell is named) |
|---|---|---|
| C68 | B | A copied devicestatus or profile with its source hex `_id` is stored as the ObjectId (15.0.8: the string). Lab P-ID-5 (profile) and P-ID-6 (devicestatus) show the stored form flip to OID. Entries/treatments already converted on 15.0.8. |
| C69 / C78 | U | Re-sent devicestatus collides on every build (string- or OID-stored), and the connector's `created_at` filter keeps stored devicestatus out of the batch. The one case #8758 turns from 200 into a refusal (hex `_id` equal to an **ObjectId-stored** devicestatus) needs a devicestatus already stored under that `_id` with a `created_at` newer than the sink's newest, which cannot exist. A copied profile already stored is routed to replace, not create, while it is among the 1000 profiles read; beyond 1000 stored profiles a re-create collides on every build. |
| C70 / C81 | B | A copied entry whose `sysTime`+`type` matches a reading the sink already holds under another `_id` (the same reading uploaded directly to the sink by xDrip, Loop or a bridge, or a string-`_id` reading from ≤15.0.6): on 15.0.8 the `_id` in `$set` makes MongoDB refuse the ordered bulk write, the entries write fails, the whole persist fails, and every cycle re-sends and fails again; readings after the refused one in that batch are not stored by the connector. On #8758 the write answers 200, the stored reading keeps its `_id`. Lab P-ID-3 "re-send with a different hex _id": 500 → 200. The connector uses `dateString`, not the reply `_id`, for its bookmark (`internal.js:171-181`; `nightscout.js:63-66`), so C70's reply change is invisible to it. Tail-of-batch effect measured: Q8. |
| C72 | B | Profile replace guard `find[_id]` finds a string-stored copy, so a changed source profile is replaced instead of skipped with `NOT_REPLACED`. Lab P-ID-5: guard n=0 → n=1, PUT 200 / n=1. |
| C73 | U | Checkpoint cleanup `_id $in`: rows are created without `_id`, so all are ObjectId-stored and match on every build. |
| C74 | B | Profile save over a string-stored copy leaves one profile (`ab7b22d6:lib/server/profile.js` `save` deletes the string forms). |
| C80 | U | The source `_id` is always 24-hex (or absent). |

### oref0

| | |
|---|---|
| repo | `externals/oref0` (openaps/oref0) |
| HEAD | `d219baf955` (detached; the prior survey's `dev` ref) |
| staged / dirty | 0 / 0 |

| surface | what it does | anchor (oref0@d219baf955) |
|---|---|---|
| (a) `_id` on create | None. Devicestatus (`ns-status.js`), treatments and entries are built without `_id`. `oref0-upload-profile.js` deletes `_id` before `POST /api/v1/profile`. | `bin/oref0-upload-profile.js:267`; `git grep -n "_id" HEAD -- lib bin/*.js` has only that line |
| (b) `_id` operators | None. | (absence, same grep) |
| (c) PUT/DELETE by id | `ns-dedupe-treatments delete <host>` (operator-run by hand, not part of the loop): lists treatments, counts rows per `created_at`, then `DELETE /api/v1/treatments/<_id>` for each. Its listing request does not complete on either build (reported to the parent; disclosure rule), so the tool deletes nothing on either. | `bin/ns-dedupe-treatments.sh:64-71`, `:76-96`; `package.json:32` |
| (d) websocket | None (`oref0-shared-node.js` is a local Unix socket). | `bin/oref0-shared-node.js:36-46` |
| (e) re-send | Treatments re-sent as a 24 h batch when the latest-treatment lookup fails (survey §2.1); no `_id`, upsert on `created_at`+`eventType`. Devicestatus is POSTed once and the queued file is removed whatever the HTTP status. | prior survey `clients/uploaders/oref0.md` S15 |

| C-id | class | why |
|---|---|---|
| C72 | B | `DELETE /api/v1/treatments/<hex>` now reaches a treatment stored with the string `_id`. |
| C74 | – through the tool; B/W for the DELETE step alone | Through the tool's own sequence nothing is deleted on either build (listing step, above). The DELETE step alone on a twin (a string copy plus an ObjectId copy of one hex) leaves 1 on 15.0.8 and 0 on `ab7b22d6` (P-ID-7); both halves are the same treatment, so the tool's intent (remove a duplicate) would then remove the treatment. BF-110 behaviour, kept by decision. |

### tconnectsync

| | |
|---|---|
| repo | `externals/tconnectsync` |
| HEAD | `7c4b2f4ddb` (detached) |
| staged / dirty | 0 / 0 |

| surface | what it does | anchor (tconnectsync@7c4b2f4ddb) |
|---|---|---|
| (a) `_id` on create | None on POST. Records carry `pump_event_id`; add-mode profile upload deletes `_id`. | `tconnectsync/sync/tandemsource/update_profiles.py:209-217`; `tconnectsync/nightscout.py:47-54` |
| (b) `_id` operators | None. | (absence) |
| (c) PUT/DELETE by id | **Profile replace** (`NIGHTSCOUT_PROFILE_UPLOAD_MODE=replace`): `GET /api/v1/profile/current`, merge pump settings, `PUT /api/v1/profile` with the same document, **including its `_id`**. **Sleep/Exercise update**: `last_uploaded_entry` (`GET /api/v1/treatments?count=1&find[enteredBy]=…&find[eventType]=…`), then `DELETE /api/v1/treatments/<_id>`, then POST a replacement with the original `created_at`. Non-200 raises. | `update_profiles.py:56-83`; `nightscout.py:65-72`, `:169-177`; `process_user_mode.py:223-260`; `nightscout.py:56-63`, `:74-87` |
| (d) websocket | None. | (absence) |
| (e) re-send | No `_id`; server upsert and client watermarks. | prior survey S15 |

| C-id | class | why |
|---|---|---|
| C72 / C74 | B | The profile PUT over a string-stored current profile leaves one profile (15.0.8: a second profile beside it). Lab P-ID-5 "connector update PUT" is the same request shape: 200 / n=1. `DELETE /treatments/<_id>` reaches a string-stored or twin Sleep/Exercise record; the client POSTs the replacement right after, so removing both halves of a twin loses nothing. |
| C80 | U | The PUT `_id` comes from the server's own reply (24-hex). |

### share2nightscout-bridge

| | |
|---|---|
| repo / HEAD | `externals/share2nightscout-bridge` `518c85c4e5`, staged 0 / dirty 0 |

(a)–(e): none. `POST /api/v1/entries.json` and `/api/v1/devicestatus.json` without `_id`
(`index.js:51-52`); `git grep` for `_id`, `identifier`, `dbAdd`, `api/v3`, PUT/DELETE finds nothing.
All C-ids U. C70 (reply names the stored `_id` for a matched reading) is not read by the bridge.

### nightscout-librelink-up

| | |
|---|---|
| repo / HEAD | `externals/nightscout-librelink-up` `bff2317f5c`, staged 0 / dirty 0 |

(a) none: v1 `POST /api/v1/entries` and v3 `POST /api/v3/entries` bodies carry `type, sgv,
direction, device, date` only (`src/nightscout/apiv1.ts:38`; `src/nightscout/apiv3.ts:83-110`).
v3 then computes a UUID `identifier` (`ab7b22d6:lib/api3/generic/create/operation.js:36`
`resolveIdentifier`), which is non-hex, so the new `identifyingFilter` branch matches only a v1
record whose `_id` is that exact UUID string (`ab7b22d6:lib/api3/storage/mongoCollection/utils.js:149-152`).
(b)–(e) none. All C-ids U (C75 U: the added branch cannot match its own records).

### minimed-connect-to-nightscout

| | |
|---|---|
| repo / HEAD | `externals/minimed-connect-to-nightscout` `57bb042c43`, staged 0 / dirty 0 |

(a)–(e): none. `POST` entries and devicestatus without `_id` (`run.js:50-51`). All C-ids U.

### glooko2nightscout

| | |
|---|---|
| repo / HEAD | `externals/glooko2nightscout` `9ab8c6080b` (`main`), staged 0 / dirty 0 |

No Nightscout requests: its HTTP calls go to Glooko (`glooko-cgm-reader.js:240`, `:389`); it only
shapes Nightscout-style objects (`:648-663`). All C-ids U.

### glooko-nightscout-eu

| | |
|---|---|
| repo / HEAD | `externals/glooko-nightscout-eu` `2b7fbc45b8` (`main`), staged 0 / dirty 0 |

(a)–(e): none. `POST /api/v1/treatments` of `[t]` without `_id`, dedup by `glookoGuid` on the
client (`glooko_uploader.py:75`). All C-ids U.

### cgmsim-lib

| | |
|---|---|
| repo / HEAD | `externals/cgmsim-lib` `c09f9c0390`, staged 0 / dirty 0 |

(a) none (prior survey S7). (c) the only DELETE is by date:
`DELETE /api/v1/devicestatus/?find[created_at][$lte]=<YYYY-MM-DD>` (`src/delete.ts:24-37`,
`src/utils.ts:198-213`), no `_id`. (b), (d), (e) none. All C-ids U.

### openaps

| | |
|---|---|
| repo / HEAD | `externals/openaps` `bd9a831887`, staged 0 / dirty 0 |

No Nightscout HTTP of its own: `git grep -nE "api/v1/[a-z]+"` finds nothing; Nightscout uploads in
an openaps rig go through oref0's `ns-upload` (`bin/openaps-import:33` names the `ns-upload`
device). `openaps/vendors/dexcom.py:446-541` only formats dates. All C-ids U.

### Candidate probes

**U-1 (nightscout-connect, entries collision, tail of batch).** Improvement expected; confirms the
safety-visible part (readings after a refused one).
1. `POST /api/v1/entries.json` `[{"type":"sgv","sgv":120,"date":T,"dateString":"<ISO T>","device":"xDrip-synthetic"}]` (T = now − 10 min, ms).
2. `POST /api/v1/entries.json` `[{"_id":"64b0c0ffee0000000000a001","type":"sgv","sgv":120,"date":T,"dateString":"<ISO T>","device":"nightscout-connect"},{"_id":"64b0c0ffee0000000000a002","type":"sgv","sgv":125,"date":T+300000,"dateString":"<ISO T+5m>","device":"nightscout-connect"}]`.
3. Read mongo: count of entries at T and at T+5m, `_id` BSON type of each.
Expected read-derived: 15.0.8 step 2 → 500, reading at T+5m **absent**; #8758 → 200, both present,
the T reading keeps its step-1 `_id`. **Measured Q8 (HTTP):** 15.0.8 500, the T+5 min reading absent; `ab7b22d6` 200, both stored, the T reading keeps its first `_id`. The in-process call was not replayed. In-process equivalent: `ctx.entries.create(<step-2 array>, cb)`
→ 15.0.8 `cb(err)`, #8758 `cb(null, docs)`.

**U-2 (oref0 `ns-dedupe-treatments delete`, twin).** Replayed through the tool's own request sequence: the listing step fails on both builds before any DELETE (details with the parent). The DELETE step alone is P-ID-7: 1 left → 0 left.

**U-3 (nightscout-connect, devicestatus re-send over an ObjectId-stored copy).** Control for the
C69/C78 "U" verdict: shows what would happen if the connector's `created_at` filter ever let a
stored devicestatus through.
1. `POST /api/v1/devicestatus.json` `[{"_id":"64b0c0ffee0000000000b001","device":"loop://synthetic","created_at":"<ISO T>","loop":{"iob":{"iob":0.5}}}]`.
2. Repeat step 1.
3. `POST /api/v1/devicestatus.json` `[{"_id":"64b0c0ffee0000000000b001",…same…},{"_id":"64b0c0ffee0000000000b002","device":"loop://synthetic","created_at":"<ISO T+5m>","loop":{"iob":{"iob":0.6}}}]`.
4. Count stored `b001` (either form) and `b002`.
Expected read-derived: 15.0.8 step 1 stores a string, step 2 → 500, step 3 → 500 and `b002`
absent; #8758 step 1 stores OID, step 2 → 500, step 3 → 500 and `b002` absent. Same outcome on
both; lab P-ID-6 has steps 1-2. The ObjectId-stored 200 → 500 case needs a devicestatus first
stored **without** `_id` and re-posted with its returned `_id`, which the connector does not do.
**Measured Q2:** own hex id POST then retry: 200 / 500 on both (15.0.8 string, `ab7b22d6` OID); a batch starting with a re-sent string-stored status: 500 and the new status not stored, on both. The ObjectId-stored case is Q2b (CANDIDATE-2).

### Notes outside this pass

- The in-process `_id $in` cleanup passes ObjectId instances; on #8758 `updateIdQuery` keeps
  them as given and stops `traverse` from walking into them (`ab7b22d6:lib/server/query.js:129-143`).
  What 15.0.8's `traverse` does to an ObjectId instance inside `$in` was not checked; the rows are
  the connector's own checkpoints.

## Readers

Server fact used throughout (read at `ab7b22d6:lib/server/query.js:111-158` against
`92d08342:lib/server/query.js:95-123`): `updateIdQuery` widens only `$in` and `$nin` lists (C73).
A `find[_id][$gt|$gte|$lt|$lte]=<hex>` bound is converted to an ObjectId by the same traverse walk
on both refs, and `matchEitherForm` does not touch it (it acts only when `query._id` is itself an
ObjectId, `ab7b22d6:lib/server/object-id-forms.js:83-88`). MongoDB compares across BSON types by
type order, so a range bound on an ObjectId never matches a string `_id`, on any build.

### GlycemicGPT

| | |
|---|---|
| repo | `externals/GlycemicGPT` |
| HEAD | `d1a9adb73e` (detached), staged 0, dirty 0 |

| | what it does | anchor (GlycemicGPT@d1a9adb73e) |
|---|---|---|
| (a) | none: read-only sync into its own database | no POST/PUT/DELETE in `apps/api/src/services/integrations/nightscout/client.py` |
| (b) | Entries cursor `GET <entries> ?count=<n>&find[_id][$gt]=<24-hex>`; the cursor is validated as 24 hex characters, either case | `client.py:707-747` (params `:734-737`), `_is_valid_object_id` `:756-769` |
| (b) | The cursor advances to `entries[0]._id` of the reply when it is a 24-character string | `sync.py:246-248` |
| (b) | Local rows keyed `(source, ns_id)`, `ns_id` = the record's `_id` as JSON text | `_glucose_mapper.py:137,180`; `_pump_events_mapper.py:164,199-200`; `_devicestatus_mapper.py:10-11,70` |
| (c) (d) (e) | none | — |

| C-id | class | reason |
|---|---|---|
| C72, C73 | unaffected | it sends neither plain `find[_id]` nor a list |
| `$gt` cursor | unaffected | the bound is an ObjectId on 15.0.8 and on `ab7b22d6`; string-stored entries (≤15.0.6) are outside the cursor on both. #8758 does not change that |
| C70, C81 | unaffected | a re-sent entry now updates the stored entry in place (200) where 15.0.8 answered 500; either way no new `_id` is inserted, so the cursor sees nothing new, and the `(source, ns_id)` row already held stays as first imported |
| C74 (twins removed) | better | a twin left by a ≤15.0.8 edit is collapsed by the next edit; the reader then holds one `ns_id` for it instead of two rows with the same text |
| others | unaffected | no writes, no socket, no v3 by identifier |

Probe (control, confirms "unchanged"): see R-1.

### oref-digital-twin

| | |
|---|---|
| repo | `externals/oref-digital-twin` |
| HEAD | `a2e8610d5f` (`main`), staged 0, dirty 0 |

| | what it does | anchor (oref-digital-twin@a2e8610d5f) |
|---|---|---|
| (a) (c) (d) (e) | none (read-only; Python ingestion and a browser page) | `ingestion/client.py:48` is the only request call |
| (b) | No `_id` filter. Windowed reads `find[<time>][$gte]`/`[$lte]`; results de-duplicated across windows by `_id`, falling back to `(time, device, sgv)` | `ingestion/client.py:107-133` (key `:128`); browser `web/app.js:47-48` |

| C-id | class | reason |
|---|---|---|
| all | unaffected | no id filter or write. A twin whose string copy is lower-case hex serialises to the same `_id` text as its ObjectId copy, so the `_id` key already folds it to one; an upper-case string twin gives two keys on every build. #8758 creates no twins |

### nightscout-cgm-skill

| | |
|---|---|
| repo | `externals/nightscout-cgm-skill` |
| HEAD | `91a53ea167` (`master`), staged 0, dirty 0 |

| | what it does | anchor (nightscout-cgm-skill@91a53ea167) |
|---|---|---|
| (a) (c) (d) (e) | none (read-only) | — |
| (b) | No `_id` filter. Pages entries back with `count=10000` and `find[date][$lte]`; stores each sgv under SQLite `id TEXT PRIMARY KEY` = the entry `_id`, skipping ids already held | `scripts/cgm.py:399`, `:488-516` |

| C-id | class | reason |
|---|---|---|
| all | unaffected | as oref-digital-twin. A re-sent entry updated in place (C81) keeps its `_id`, so the skill keeps its first copy of the value, as on 15.0.8 for any in-place update |

### GluPredKit

| | |
|---|---|
| repo | `externals/GluPredKit` |
| HEAD | `e5bd6357a6` (detached), staged 0, dirty 0 |

| | what it does | anchor (GluPredKit@e5bd6357a6) |
|---|---|---|
| (a) (c) (d) (e) | none (read-only) | — |
| (b) | No `_id` filter: `find[created_at]` / `find[dateString]` windows; profile GET through `requests` | `glupredkit/parsers/nightscout.py:69-70,74,80-81,88-89` |

| C-id | class | reason |
|---|---|---|
| all | unaffected | no `_id` surface. Entries and treatments go through `python-nightscout`, which is not in the corpus |

### nightscout-reporter (AngularDart, retired)

| | |
|---|---|
| repo | `externals/nightscout-reporter` |
| HEAD | `518d61fb1d` (detached), staged 0, dirty 0 |

| | what it does | anchor (nightscout-reporter@518d61fb1d) |
|---|---|---|
| (a) (c) (d) (e) | none to Nightscout. The one POST helper is used for Google sign-in | `lib/src/globals.dart:1324-1331`; `lib/src/controls/signin/signin_component.dart:95` |
| (b) | No `_id` filter, no `$in`. Reads `_id` as an opaque id | `lib/src/json_data.dart:1121,1317,1572`; `lib/src/start_component.dart:1125` |

| C-id | class | reason |
|---|---|---|
| C74 | better | fewer duplicate treatments on sites whose twins are collapsed by later edits (it sums treatments) |
| others | unaffected | read-only; the maintained Angular successor is not in the corpus (cannot tell for it) |

### nocturne (server reimplementation: parity note)

| | |
|---|---|
| repo | `externals/nocturne` |
| HEAD | `42275c812d` (detached), staged 0, dirty 0 |

nocturne keeps a Nightscout id as one text column, `LegacyId`, beside its own GUID. There is no
second BSON form, so the string-versus-ObjectId twins #8758 handles cannot arise there.

| #8758 rule | candidate `ab7b22d6` | nocturne | anchor (nocturne@42275c812d) |
|---|---|---|---|
| id forms accepted on v1 | 24-hex, either case | 24-hex and 32-hex (UUID v7 without dashes), case-insensitive regex | `EntriesController.cs:171-175,963-966,1036-1039`; `ProfileController.cs:333-336` |
| lookup by id (C71, C72) | ObjectId in any case; string in lower case or the spelling asked | GUID parse, then exact `LegacyId == id`, no lower-casing found | `Services/Entries/EntryReadService.cs:163-175,419-431`; `Repositories/V4/V4RepositoryBase.cs:219-222` |
| delete by id (C74) | every stored form | one `LegacyId` match | `V4RepositoryBase.cs:476` |
| websocket `dbAdd`/`dbUpdate`/`dbRemove` (C76, C77) | either form | not implemented | (prior map, S6) |
| `find[_id][$in]` (C73) | both forms per id | generic `$in` over the stored value | `FindQuery.cs` (prior map, S2) |

Differences a nocturne user could see after the parity suite moves to 15.0.9: an upper-case
24-hex id asked of an ObjectId-stored record is found by the candidate; in nocturne it depends on
whether `LegacyId` was stored in that case (cannot tell from reading). Probe R-3.

### nightscout-roles-gateway

| | |
|---|---|
| repo | `externals/nightscout-roles-gateway` |
| HEAD | `90840acee1` (detached), staged 0, dirty 0 |

| | what it does | anchor (nightscout-roles-gateway@90840acee1) |
|---|---|---|
| (a)–(e) | none for data. Auth subjects are **read** only: `GET /api/v2/authorization/subjects` with `API-SECRET`; roles listed | `lib/tokens/index.js:17-22,40`; `lib/criteria/core.js:45-47` |
| subject create/delete | not implemented. The docs describe a proposed `POST /api/v2/authorization/subjects` | `docs/token-management.md:280-282` ("PROPOSED") |

| C-id | class | reason |
|---|---|---|
| C79 | unaffected | it never deletes a subject; if the proposed create lands, a subject posted without `_id` gets an ObjectId on every build |
| others | unaffected | — |

### babelbetes, osaid-keymanager, trio-telemetry

| repo | HEAD | finding | anchor |
|---|---|---|---|
| babelbetes | `07a7f07278` (`develop`), staged 0, dirty 0 | no Nightscout requests; one notebook reads archived exports from files | `notebooks/understand-dana-dataset/2024-05-15 - LoadingLoopDataFromNightScout.ipynb` (loader cells) |
| osaid-keymanager | `e9c3b738aa` (`main`), staged 0, dirty 0 | no Nightscout requests, no subjects or roles (its ids are App Attest key ids) | `app/attest/verify.py:82-187` (positive control: the search reaches its code) |
| trio-telemetry | `681ea86752` (`master`), staged 0, dirty 0 | no Nightscout requests; `nightscoutPaired` is a boolean the Trio app reports | prior map `trio-telemetry.md:18` |

All C-ids: unaffected.

### Readers matrix (read-derived)

| client | C68 | C69 | C70 | C71 | C72 | C73 | C74 | C75 | C76 | C77 | C78 | C79 | C80 | C81 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GlycemicGPT | – | – | – | – | – | – | better | – | – | – | – | – | – | – |
| oref-digital-twin | – | – | – | – | – | – | – | – | – | – | – | – | – | – |
| nightscout-cgm-skill | – | – | – | – | – | – | – | – | – | – | – | – | – | – |
| GluPredKit | – | – | – | – | – | – | – | – | – | – | – | – | – | – |
| nightscout-reporter | – | – | – | – | – | – | better | – | – | – | – | – | – | – |
| nocturne (parity) | n/a | n/a | n/a | cannot tell | parity differs by design | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| nightscout-roles-gateway | – | – | – | – | – | – | – | – | – | – | – | – | – | – |
| babelbetes, osaid-keymanager, trio-telemetry | – | – | – | – | – | – | – | – | – | – | – | – | – | – |

`–` = unaffected. No reader is in "could be worse".

### Candidate probes

- **R-1 (GlycemicGPT cursor, control for "unchanged").** Seed three sgv entries in one test
  database through mongo: A with ObjectId `_id` `650000000000000000000001`, B with ObjectId
  `650000000000000000000003`, C with the **string** `_id` `"650000000000000000000002"`, all dated
  within the last hour. Then
  `GET /api/v1/entries.json?count=100&find[_id][$gt]=650000000000000000000000` with the api-secret
  header. Expected on 15.0.8 and `ab7b22d6` alike: A and B, not C. Positive control:
  `find[_id]=650000000000000000000002` returns C on `ab7b22d6` only (C72).
  **Measured Q6:** cursor returns A and B on both builds; `find[_id]=<C>` n=0 → n=1.
- **R-2 (dedupe-by-`_id` readers, twin).** Seed a treatment twin: string `_id`
  `"650000000000000000000010"` and ObjectId `650000000000000000000010`, same `created_at`. Then
  `GET /api/v1/treatments.json?find[created_at][$gte]=<1h ago ISO>&count=100` on both builds.
  Expected: two records with identical `_id` text on both builds (readers fold them). Then
  `PUT /api/v1/treatments` with `_id: "650000000000000000000010"` and re-run the GET: 15.0.8 still
  two, `ab7b22d6` one.
  **Measured Q7:** GET 2 / PUT 200 / GET 2 on 15.0.8; GET 2 / PUT 200 / GET 1 on `ab7b22d6`.
- **R-3 (nocturne parity, upper-case id).** Only if a nocturne instance is available:
  `POST /api/v1/entries` `[{type:'sgv', sgv:100, date:<now>, _id:'650000000000000000000abc'}]`, then
  `GET /api/v1/entries/650000000000000000000ABC` on nocturne and on `ab7b22d6`. Expected on the
  candidate: 1 entry. nocturne: cannot tell from reading. Not replayed (no nocturne instance in this pass).
