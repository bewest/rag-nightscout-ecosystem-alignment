# WRITE-CONTRACT: explicit nulls, natural keys and identical re-sends, measured

*Contributor-facing.* **Snapshot, 2026-10-12.** Input to the maintainer decisions in
[write-contract spec §6](../../30-design/tenancy/write-contract-spec-2026-10-07.md#6-decisions-for-the-maintainer)
after the 2026-10-12 choices: Q1 = (a) merge on match; Q1b = (ii) under merge a JSON `null` deletes
the field (RFC 7386); Q2 = (b) an identical re-send keeps today's rewrite. Three questions:

1. Does any client send `"field": null` on a create or re-send, so that Q1b(ii) would remove a stored
   field on retry? (§1)
2. For Q3: do distinct devicestatus records share (`created_at`, `device`), and do entries' `date`
   and `sysTime` name different instants? (§2)
3. Under Q2(b), who re-sends unchanged records, and what does a consumer do with a record whose
   content is unchanged but whose `srvModified` is new? (§3)

Marks: **[M]** measured, by the script and output named, in
[`write-contract-null-and-keys-2026-10-12/`](write-contract-null-and-keys-2026-10-12/).
**[R]** read, from source at `path:line@commit`, not run. Paths for client sources are relative to
`externals/<repo>/`. Most client reads were made by two read-only sub-agents; the citations marked
*(checked)* were re-read for this document, the rest were not.

---

## 0. Verdicts

| question | verdict |
|---|---|
| **1. explicit nulls** | **Yes, four uploaders send them on create, all through API v1 POST: tconnectsync, oref0, nightscout-connect and cgmsim-lib.** Loop, Trio, xDrip4iOS, xDrip+, AndroidAPS (dev and master) and nightscout-librelink-up do not [R]. The stored corpus cannot confirm or refute this: it has no uploader from that list, and its only nulls are `carbs`/`insulin`, which the v1 treatments **read** adds [M]. **Which fields matter:** the treatment nulls (tconnectsync and cgmsim-lib `carbs`/`insulin`/`duration`) are normalised away by v1 `prepareData` before storage [M]. The devicestatus nulls are stored verbatim [M]: tconnectsync `pump.battery.percent`, oref0 `openaps.iob`, nightscout-connect `librelinkup.sensor.*` and `librelinkup.patientDevice.*`. All of these clients re-send the identical body after a failure [R]. Under Q1b(ii) such a retry deletes keys that the first write stored as `null`: the stored shape changes, but no non-null value is lost. A stored **value** is lost only if a second writer filled the field in between. |
| **2a. devicestatus (`created_at`, `device`)** | **3,078 groups (14,757 documents) are distinct records sharing the key. All are Loop, at all 11 sites with Loop devicestatus.** A further 4,001 groups (22,635 documents) are byte-identical retry copies, also all Loop. Trio and the phone-model uploader have 0 of either [M]. In every distinct group the members share `loop.timestamp` and differ in `loop.enacted.*` (1,457 groups differ only there), `uploader.battery`, `loop.predicted` and the dose recommendations [M]. Keying devicestatus on (`created_at`, `device`) with merge would fold these into one record. |
| **2b. entries `date` vs `sysTime`** | **0 entries name instants 1 s or more apart.** 427,003 of 719,559 differ by less than 1 s, because `date` carries sub-second milliseconds and `sysTime` is second-resolution. 292,556 are exactly equal [M]. Per client: §2.2. |
| **3. identical re-sends (Q2(b))** | **Every uploader re-sends records it already uploaded,** mostly as whole-batch retries after a lost reply [R]. The only deliberate re-send of unchanged records is xDrip+'s user-triggered backfill; no client has a periodic "touch" [R]. **AndroidAPS NSClientV3 is the only client that syncs by `srvModified`.** For a record whose content is unchanged it writes nothing to its database and uploads nothing, with one exception: an Announcement less than 60 min old raises its alarm notification again [R]. A re-delivered copy can also revert a pending local edit of a few fields, but only when the server copy differs from the local one, which an identical re-send by definition does not cause. The corpus cannot measure how often this happens: 1 of 1,589,356 stored documents carries `srvModified` and none carries `srvCreated` [M]. |

---

## 1. Explicit nulls (Task 1)

### 1.1 The stored corpus

**What it is.** The corpus is `externals/ns-data`, which holds 12 sites:

- `patients/{a..k}/raw`: 180-day exports captured 2026-04-01 to 04.
- `live-recent-180-json/live-recent`, labelled site L.

All were fetched through API **v1** GET (`tools/cgmencode/ns_fetch.py:75,111,146,233`). The software version of the hosting servers is not recorded. There is no `food` collection.

Document counts [M] (`corpus-results.txt`, `## docs`):

| collection | documents | clients, identified by app-level fields only |
|---|---:|---|
| treatments | 307,996 | `enteredBy` `loop://…`: 257,326 · `Loop`: 2,052 · `Loop (via remote command)`: 50 · `Trio`: 48,130 · `xDrip4iOS`: 436 · free text: 2 |
| devicestatus | 561,690 | `device` `loop://…`: 485,141 · `Trio`: 61,368 · a phone model with an `uploader` object only: 15,181 |
| entries | 719,559 | `device` family: Dexcom transmitter name (`Dexcom G6/G7 …`, written by the Loop/Trio CGM managers): 220,675 · Dexcom app bundle id: 128,294 · Trio bundle id: 18,856 · `share2`: 28,773 · LibreLinkUp: 13,096 · `xDrip-WebFollower`: 16,177 · pre-redacted: 244,429 · none: 48,864 · other: 395 |
| profile | 111 | — |

The corpus contains **no** AndroidAPS, openaps/oref0, xDrip+ uploader, tconnectsync, cgmsim-lib or nightscout-connect writes. The clients that §1.2 finds sending nulls are therefore not in it.

**Null counts** [M] (`corpus-results.txt`, `## nulls`). These count top-level and one-level-nested fields; `deepdocs` covers nulls at any depth.

| collection | client | field | documents with `null` |
|---|---|---|---:|
| treatments | Loop (`loop://`) | `carbs` | 252,545 |
| treatments | Loop (`loop://`) | `insulin` | 162,054 |
| treatments | Loop (`Loop`, remote command) | `carbs`, `insulin` | 2,102 each |
| treatments | Trio | `carbs` / `insulin` | 40,707 / 35,794 |
| treatments | xDrip4iOS | `carbs` / `insulin` | 221 / 264 |
| treatments | free text | `carbs`, `insulin` | 2 each |
| entries, devicestatus, profile | every client | any field, at any depth | **0** |

**The treatment nulls are made by the read, not by the clients.** Every treatment without a number in `carbs` or `insulin` shows `null` there, whichever client wrote it.

- The v1 GET handler sets `t.carbs = Number(t.carbs)` and `t.insulin = Number(t.insulin)` for every result [R]:
  - `lib/api/treatments/index.js:41-42@fade2299`
  - `:36-37@v15.0.8` *(checked)*
- `Number(undefined)` is `NaN`, which JSON serialises as `null`.
- Control [M] (`repro-results.txt`, "control"): a v1 POST of a treatment without `carbs` stores no `carbs` key, yet the v1 GET of that record returns `"carbs": null`. Same on dev `fade2299` and on 15.0.8.

**Why the corpus cannot show treatment nulls on v1.** `prepareData` normalises these fields before storage:

- It deletes `targetTop`, `targetBottom`, `carbs`, `insulin`, `percent`, `relative`, `notes` and `preBolus` when falsy, which includes `null`.
- It turns a `null` `duration` or `absolute` into `0`, because `Number(null)` is `0`.

Sources: `lib/server/treatments.js:516,554-566@fade2299` [R] *(checked)*. Control [M] (`repro-results.txt`, `v3-results.txt`): a v1 POST with these fields set to `null` stores none of them as `null`, and stores `duration` and `absolute` as `0`.

**Non-vacuity of the corpus query** [M] (`analyze.py --control`, `control-results.txt`). Planted copies in site a were each found exactly once:

- a Loop treatment with an extra `null` field;
- a devicestatus with a nested `pump.plantedNested: null`.

### 1.2 Client sources

| client | path | can it send `null`? | fields | evidence |
|---|---|---|---|---|
| Loop (NightscoutKit `4ec9fd1`, NightscoutService `fe075ef`) | v1 POST/PUT treatments, entries, devicestatus, profile | **no**: every body is a `[String: Any]` filled through optional subscripts (a nil assignment removes the key) and sent with `JSONSerialization` | — | `NightscoutClient.swift:530`; `Models/Treatments/NightscoutTreatment.swift:105-120`; `Models/DeviceStatus.swift:34-65`; `Models/GlucoseEntry.swift:101-132`; `Models/ProfileSet.swift:81-95,143-165` @`4ec9fd1` [R] |
| Trio `e41c9db37` | v1 POST (Trio has no PUT) | **no**: a plain `JSONEncoder` over synthesized Codable, which skips nil optionals; no upload model has a custom `encode(to:)` | — | `Trio/Sources/Helpers/JSON.swift:83-89`; `Models/NightscoutTreatment.swift:3-60`; `Models/NightscoutStatus.swift:3-70` @`e41c9db37` [R] |
| xDrip4iOS `c268542e` | v1 POST/PUT | **no**: `[String: Any]` built with `??` defaults or optional subscripts | — | `xDrip/Core Data/classes/TreatmentEntry+CoreDataClass.swift:172-238`; `Managers/Nightscout/BgReading+Nightscout.swift:6-22` @`c268542e` [R] |
| AndroidAPS dev `7e1d537d49` | v3 POST/PATCH (NSClient v1 removed) | **no top-level null**: kotlinx `explicitNulls = false`. Nested `JsonObject` values in devicestatus would pass a `JsonNull` through, but their producers omit nulls | — | `core/nssdk/src/commonMain/kotlin/app/aaps/core/nssdk/NsSdkJson.kt:15,59` *(checked)*; `remotemodel/RemoteDeviceStatus.kt:39,57-59` @`7e1d537d49` [R] |
| AndroidAPS master `598e2eb39c` | v3 via Retrofit with Gson; v1 socket `dbAdd`/`dbUpdate` with org.json | **no**: Gson without `serializeNulls`; the org.json builders guard optionals, and `JSONObject.NULL` appears only in tests | — | `core/nssdk/.../networking/NetworkStackBuilder.kt:50,62,102-104`; `plugins/sync/.../nsclient/extensions/BolusExtension.kt:20-26`; `TherapyEventExtension.kt:66-74` @`598e2eb39c` [R] |
| xDrip+ `1ed760048` | v1 POST entries/devicestatus, PUT treatments | **no**: org.json with no `JSONObject.NULL`; `put(k, null)` removes the key | — | `app/src/main/java/com/eveningoutpost/dexdrip/utilitymodels/NightscoutUploader.java:557-580,776-793,1119-1172` @`1ed760048` [R] |
| nightscout-librelink-up `bff2317` | v1 POST or v3 POST entries | **no**: an absent `direction` is `undefined` | — | `src/nightscout/apiv1.ts:37-48`; `apiv3.ts:81-108` @`bff2317` [R] |
| **tconnectsync** `7c4b2f4` | v1 POST, one record per request (`requests.post(json=)`) | **yes, on create** | treatments Temp Basal: `carbs: None`, `insulin: None` always; `duration: None` when 0. devicestatus: `pump.battery.percent: None` when 0 | `tconnectsync/parser/nightscout.py:30-41,205` *(checked)*; `tconnectsync/nightscout.py:47-72` @`7c4b2f4` [R] |
| **oref0** `d219baf9` | v1 POST by curl from a file queue | **yes, on create** | devicestatus `openaps.iob = null` when `iob.json` is missing or empty; nulls inside the suggested/enacted files pass through | `bin/ns-status.js:124-130,157` *(checked)* @`d219baf9` [R] |
| **nightscout-connect** `04102f9` | v1 POST via axios (keeps `null`, drops `undefined`) | **yes, on create** | devicestatus `librelinkup.sensor.{startedAt, startedAtEpoch, ageSeconds, warmupMinutes, state, lastJoin, patchType}` and `librelinkup.patientDevice.{deviceTypeId, appVersion, alarms, lowAlarm, highAlarm, lowAlarmThresholdMgDl, highAlarmThresholdMgDl, lastUpload, fixedLowAlarmValues(.mgdl/.mmoll), fixedLowThreshold}`; Glooko values copied across as they come; the Nightscout-to-Nightscout source re-POSTs stored documents verbatim, nulls included | `lib/sources/librelinkup.js:324-355` *(checked)*; `lib/sources/glooko/convert.js:164-170`; `lib/sources/nightscout.js:58-63,107` @`04102f9` [R] |
| **cgmsim-lib** `c09f9c0` | v1 POST treatments | **yes, on create** | `carbs: null`, `insulin: null` on temp basals and when absent | `src/upload.ts:237,250-258` *(checked)* @`c09f9c0` [R] |

### 1.3 What a null does today, and what it would do under Q1b(ii)

Today [M], on dev `fade2299` and 15.0.8 `92d08342`, MongoDB 7.0.43 in a dedicated container (`repro.py`, `v3.py`; outputs `repro-results.txt` and `v3-results.txt`):

- **v1 POST stores `null` verbatim for any field `prepareData` does not handle.** This was shown for:
  - treatments: a top-level field, a nested field, and `reason`;
  - entries: `direction`, `noise`, and a nested field;
  - devicestatus: top-level, `pump.battery` and `uploader.battery`;
  - profile: a top-level field, and `mills`.
- **v3 POST stores `null` verbatim, `carbs` and `insulin` included,** because v3 does not run `prepareData`.
- **A v1 re-send of a treatment matched by `syncIdentifier`, with `reason` changed from `"x"` to `null`, stores `reason: null`** (today's replace).

Under Q1b(ii), applied to the per-client facts above:

- **The treatment nulls from tconnectsync and cgmsim-lib never reach the merge on v1,** provided the null rule runs after `prepareData`, as the write step in spec §2.3 would. `duration` arrives as `0`.
- **On v3 they would reach it,** but neither client uses v3 [R].
- **The devicestatus nulls (tconnectsync, oref0, nightscout-connect) are stored by the first write.** An identical retry would then **delete** those keys, assuming RFC 7386's recursive merge reaches nested objects. The record changes shape (the key goes from `null` to absent). No value is lost unless something else wrote that field in between.
- **nightscout-connect's Nightscout-to-Nightscout source re-POSTs stored documents.** Any `null` stored on the source site deletes the matching field on the target on every re-send.

---

## 2. Natural keys (Task 2)

### 2.1 devicestatus sharing (`created_at`, `device`)

[M] `analyze.py` (`corpus-results.txt`, `## devicestatus … groups`) and `dsdiff.py`/`dsdiff2.py`
(`dsdiff-results.txt`, `dsdiff2-results.txt`). Bodies were compared with `_id`, `srvModified`,
`srvCreated`, `identifier`, `mills` and `utcOffset` removed. The groups are the same whether
`created_at` is compared as a string or as an instant.

| client | groups with distinct bodies (documents) | groups with identical bodies (documents) |
|---|---:|---:|
| Loop | **3,078 (14,757)** | 4,001 (22,635) |
| Trio | 0 | 0 |
| phone-model uploader | 0 | 0 |

- Distinct groups appear at 11 of the 12 sites, which is every site with Loop devicestatus.
- Most distinct groups have 2 members (2,509). 178 have 10 or more members with 2 distinct bodies.
- Loop `created_at` has millisecond resolution, and every distinct group shares `loop.timestamp`.

What differs, counted in groups:

| fields that differ | groups |
|---|---:|
| only `loop.enacted.{bolusVolume, duration, rate, received, timestamp}` | 1,457 |
| only `uploader.battery` | 329 |
| only `loop.cob.cob` and `loop.predicted.values` | 148 |
| `loop.automaticDoseRecommendation.*` together with `loop.predicted.values` | the next five combinations |
| only `loop.failureReason` | 69 |

**Reading.** These are different status reports from one Loop cycle carrying one `created_at`, not retries. Under Q3(a) with merge they would become one record, and the last report's `enacted` or recommendation would overwrite the earlier one.

**Non-vacuity** [M] (`control-results.txt`). A planted identical copy moved the identical-bodies count up by one group (2 documents). Two planted copies, each with one leaf changed (one with a nested `null`, one with an extra `loop` field), moved the distinct-bodies count up by two groups (4 documents).

### 2.2 entries: `date` versus `sysTime`

[M] `analyze.py` (`## entries date vs sysTime`) and `entdiff.py` (`entdiff-results.txt`).

| entry `device` family | exactly equal | differ by less than 1 s | differ by 1 s or more |
|---|---:|---:|---:|
| Dexcom transmitter name (Loop/Trio CGM managers) | 0 | 220,675 | 0 |
| Dexcom app bundle id | 86,891 | 41,403 | 0 |
| Trio bundle id | 0 | 18,856 | 0 |
| `loop://` | 0 | 75 | 0 |
| `share2` | 28,773 | 0 | 0 |
| LibreLinkUp | 13,096 | 0 | 0 |
| `xDrip-WebFollower` | 16,177 | 0 | 0 |
| pre-redacted | 147,371 | 97,058 | 0 |
| none | 23 | 48,841 | 0 |
| other | 225 | 95 | 0 |
| **total** | **292,556** | **427,003** | **0** |

Every entry in the corpus has a `sysTime` [M].

- Of the sub-second differences, 377,953 are exactly `sysTime` = `date` truncated to the second.
- Almost all of the rest (48,818 with no `device`, 140 Dexcom transmitter, 60 pre-redacted, 25 Dexcom app, 7 Trio) have a fractional-millisecond `date` that is within 1 s of `sysTime` without being its truncation.

**Reading.** `sysTime` names the same second as `date` in every case, but not the same millisecond for 59% of entries. Moving the key from `sysTime`+`type` to `date`+`type` therefore matches a re-send only when the client repeats `date` to the millisecond, including its fraction.

**Key collisions** [M] (`entkey.py`, `entkey-results.txt`). Groups that share a key but have distinct bodies:

| key | distinct groups | where |
|---|---:|---|
| `date`+`type` | 79 | 74 from `loop://` entries, 5 elsewhere |
| `sysTime`+`type` | 100 | 74 Dexcom transmitter, 25 Trio, 1 pre-redacted |

**Non-vacuity** [M]. A planted entry with `sysTime` moved 5 min away from its `date` showed up once in "differ by 1 s or more" (`control-results.txt`).

---

## 3. Identical re-sends under Q2(b) (Task 3)

### 3.1 Who re-sends records already uploaded

All [R]. See §1.2 for the commits.

| client | after a failure or a lost reply | other re-sends | how edits are sent |
|---|---|---|---|
| Loop | The per-type anchor advances only on success, so the whole batch (up to 1,000 records) is re-queried and re-sent. Carbs and doses are POSTed without `_id`, so a lost reply means a second POST (`Loop/Managers/RemoteDataServicesManager.swift:53-71,164-185,320-331@c2fddb76`; `NightscoutKit/Sources/NightscoutKit/NightscoutClient.swift:627-690@4ec9fd1`) | Removing and re-adding the service uploads everything again. A change to a stored record re-sends it (`LoopKit/InsulinKit/InsulinDeliveryStore.swift:901-911@325bd820`) | carbs: PUT; doses: re-POST; overrides: DELETE then POST (`NightscoutServiceKit/NightscoutService.swift:157-187@fe075ef`) |
| Trio | Chunks of 100. `isUploadedToNS` is set only after every chunk succeeds, so a lost reply re-POSTs all chunks (`NightscoutManager.swift:973,1032,1099,1160,1218,1261@e41c9db37`). The retry queue covers 24 h (`:120-127`) | A bolus or temp basal is re-POSTed when its amount, rate or duration changes (`APS/Storage/PumpHistoryStorage.swift:246,260-262,283-285`). The full profile is POSTed after each settings edit (`NightscoutManager.swift:741-875`) | DELETE then POST; no PUT |
| xDrip4iOS | Unconfirmed new treatments are re-POSTed on the next sync, at most every 10 s. Glucose uses a cursor that advances on success. Calibration `mbg` records get a new random `_id` on every attempt (`Managers/Nightscout/Calibration+Nightscout.swift:33`; `NightscoutSyncManager.swift:1499-1548@c268542e`) | — | PUT |
| xDrip+ | A failed entries batch re-POSTs the whole array (`.../UploaderTask.java:184-197@1ed760048`) | **The user-triggered backfill re-queues every reading and treatment since a chosen date: the only deliberate re-send of unchanged records found** (`NightscoutBackfillActivity.java:105-125`) | PUT upsert |
| AndroidAPS dev | One record per request. The cursor holds on an exception, so the same record is sent again as a create (`NSClientV3Plugin.kt:1093-1097@7e1d537d49`) | A full sync re-adds only records that have no nsId (`DataSyncSelectorV3.kt:126-145,175-185`). When a sync transaction applies a server change, the change is echoed back once as a PATCH | PATCH |
| nightscout-connect | A failed frame re-POSTs that collection's whole batch (`lib/machines/fetch.js:306-357@04102f9`) | Treatments carrying a `glooko:` identifier may be re-POSTed on every poll (`lib/outputs/nightscout.js:78`; not traced end to end) | profile: PUT; Glooko rows: POST new, then DELETE old |
| nightscout-librelink-up | The next cron tick re-derives what to send (`src/index.ts:300-339@bff2317`) | `ALL_DATA=true` re-POSTs the whole graph window every cycle (`src/config.ts:65`) | — |
| tconnectsync | Resumes from the last record uploaded per type; every run re-processes a window (`tconnectsync/autoupdate.py:59,71@7c4b2f4`) | Profile: GET, modify, PUT back the whole document | PUT |
| oref0 | Devicestatus files are deleted only after a successful upload, so a curl timeout after the server has inserted re-POSTs the identical body. The last 10 treatments are re-sent if the latest one is in the future (`bin/oref0-ns-loop.sh:202-260@d219baf9`) | — | — |

### 3.2 What a consumer does with "unchanged content, new `srvModified`"

**AndroidAPS NSClientV3 is the only client found that syncs by `srvModified`.** Loop, Trio and xDrip4iOS re-read a time window on `created_at`/`date`/`dateString`. xDrip+ does a full v1 GET gated by an ETag. nightscout-connect, librelink-up, tconnectsync and oref0 read by `created_at`/`date` [R].

How AndroidAPS dev `7e1d537d49` reads (master `598e2eb39c` is the same where noted) [R]:

- It reads `GET v3/treatments/history/{from}?limit=500`, with `from = max(cursor, now − 100 d)`.
- The cursor is the response ETag, persisted before the batch is processed (`LoadTreatmentsRunner.kt:39-42,56-67`; `NSAndroidClientImpl.kt:327-334`).
- Each record goes through a `SyncNs*Transaction` (`StoreDataForDbImpl.kt:201-261`).

What happens when the record's content is unchanged:

- **No database write, no upload back.**
  - Bolus: `SyncNsBolusTransaction.kt:19-31` *(checked)*. Writes only on invalidation or when `amount` differs.
  - Carbs, temporary target, temp basal, extended bolus, profile switch, running mode: write only on invalidation or a shorter duration.
  - Effective profile switch, bolus calculator result: invalidation only.
  - Therapy event: invalidation, a shorter duration, or a different `location`/`arrow`/`note`.
  - Food, calibration: write only if `contentEqualsTo` fails.
- **Exception: Announcement.** An Announcement whose timestamp is less than 60 min old raises its alarm notification each time it is processed, whether or not the database changed (`NsIncomingDataProcessor.kt:208-221@7e1d537d49`; `:204-211@598e2eb39c`). Under Q2(b), an identical re-send of a recent Announcement by any client alarms AndroidAPS users again. No client in §3.1 was found to retry Announcements in particular; careportal posts once.
- **Cost.** Every rewrite re-enters the 500-record history pages.

**Can it override a local edit?** Only if the server copy **differs** from the local one. The transactions accept the server's bolus `amount`, a therapy event's `note`/`location`/`arrow`, a whole food or calibration record, and a shortened duration. A local edit that has not been uploaded yet can therefore be reverted by a re-delivered stale server copy, and the reverted value is then PATCHed back [R; not run].

An identical re-send by a third client re-delivers the server's current copy. That copy can differ from an AndroidAPS local edit only while the edit is still pending. So Q2(b) does not create this hazard, but each rewrite is one more re-delivery that can trigger it. This was not reproduced.

Not traced: AndroidAPS's devicestatus, profile and entries runners, and its WebSocket `onDataCreateUpdate` path.

### 3.3 The corpus

[M] Across the 12 sites' 1,589,356 stored documents:

- `srvModified` appears on 1 (a profile);
- `srvCreated` appears on 0;
- `identifier` appears on 505 treatments.

The corpus was written by v1 clients, and 15.0.8 does not stamp v1 writes. dev `fade2299` does stamp them: in `repro-results.txt`, the dev rows carry `srvCreated`/`srvModified` and the 15.0.8 rows do not. **How often a record's `srvModified` advances without a content change cannot be recovered from this corpus.** Measuring it would need a dev or 15.0.9 site's v3 history, or MongoDB change history.

---

## 4. Reproduction

- **Corpus.** `python3 -I analyze.py` (and `--control`), `dsdiff.py`, `dsdiff2.py`, `entdiff.py`, `entkey.py`, run against `externals/ns-data`. Output is aggregate only; client labels come from fixed patterns over `enteredBy`/`device`, and free text is bucketed as "other".
- **Server.**
  1. Start a dedicated `docker run -d -p 127.0.0.1:27099:27017 mongo:7.0` and read `db.version()` → `7.0.43`.
  2. Create worktrees of `cgm-remote-monitor-official` at `fade2299` and at `v15.0.8` (`92d08342`), then run `npm ci --ignore-scripts && npm run postinstall` in each.
  3. Start each with `runserver.sh.txt`, which takes a random `API_SECRET` from a local file and sets `AUTH_DEFAULT_ROLES=denied`.
  4. Run `python3 -I repro.py <port> <db> <label> <secretfile>`, then `python3 -I v3.py <port> <db> <secretfile>`.
- **Server control.** The first run, made with an empty `API_SECRET`, answered every API write with 404, and the stored-document reads showed "NOT STORED". This confirms that the reads look at the server's own database.
- **Node.** Node 24.15.0.
