# ST-VIEWS groundwork: the alarm slice re-measured, the ddata consumer census, and an equality harness

> **Snapshot, 2026-10-27, measured against `cgm-remote-monitor` `dev` `db3b9e4e` (merge of PR #8872).** Plan item ST-VIEWS (milestone M4) in [next-gen-platform-plan.json](../../30-design/platform/next-gen-platform-plan.json). The equality harness is on a local, unpushed `cgm-remote-monitor` branch, `feat/views-equality` `d69ff824` (one commit on `db3b9e4e`). MongoDB 7.0.43 in a dedicated container; Node 22.23.4 and 24.22.1.

*Audience: contributors.*

ST-VIEWS asks that what the page, the socket's `dataUpdate`, the plugins and the alarms compute come from bounded queries (newest *n* of a type within a time bound), materialised, used and discarded, with each view's output equal to today's `ddata`-based output on the fixtures, and, for alarms, the execution plan §7b measurement. This note covers three things. §1 re-runs the two September harnesses against `dev`. §2 lists every server-side reader of the resident data. §3 describes the harness that checks equality, and its controls. §4 lists the defects and mismatches found on the way.

---

## 1. The September harnesses on `dev`

### 1.1 `tools/qc/alarm-critical-slice.js` (EXP-MT-060): the bytes hold exactly, and the timing holds once the machine is accounted for

It loads and runs against `db3b9e4e` unchanged. 14 of its 15 checks pass. The one that fails is V7, and it fails because BF-28 is fixed on `dev`.

| quantity | September (`29749d92`, Node 24.15.0) | `29749d92` today, Node 24.22.1, 3 runs | `db3b9e4e` today, Node 24.22.1, 3 runs interleaved | `db3b9e4e` today, Node 22.23.4, 3 runs |
|---|---:|---:|---:|---:|
| whole `ddata` | 852.1 KB | 852.1 KB | 852.1 KB | 852.1 KB |
| conservative alarm window | 33,475 B (32.7 KB) | 33,475 B | 33,475 B | 33,475 B |
| full evaluation, p50 | 27.5 ms | 30.68 / 31.03 / 30.72 ms | 34.31 / 33.41 / 31.24 ms | 28.72 / 30.42 / 27.82 ms |
| windowed evaluation, p50 | 1.94 ms | 2.41 / 2.27 / 2.42 ms | 2.42 / 2.47 / 2.19 ms | 2.10 / 2.18 / 2.04 ms |
| emitted alarm at the window | `2\|default\|ar2\|low` | same | same | same |

The second column is the September commit, run today on the same machine as the `dev` runs, with its own `npm ci` (worktree `crm-views-sept`). Today's machine is about 10 % slower than September's on the September code, at load average 1.5 to 2.4. Run in the same conditions, `dev` and `29749d92` are within run-to-run spread on both arms. The ratio is unchanged: the window costs about 7 % of a full evaluation and emits the same alarm. The 1.94 ms figure is September's machine. The figure to plan against is "about 2 ms on this machine, about 7 % of a full evaluation", re-measured whenever the number is quoted.

With timings excluded, the text output of the two commits differs only where BF-28 (merged to `dev` in PR #8739) changes it:

- In scenario `deviceAged`, `iage` now emits URGENT ("Insulin reservoir age 72 hours") beside `cage`, `sage` and `bage`.
- `insulinchangeTreatments` is now alarm-critical in `deviceAged` as well as in `insulinAgedWarn`.
- The knockout counts are 18 critical, 138 inert and 100 read-but-inert pairs, where September had 17, 139 and 101.
- V7 ("the insulinage URGENT branch is unreachable") fails, because that branch is now reachable.

**Adaptation (minimal, in a copy on `lab/views-census`):** `tools/qc/alarm-critical-slice.js` takes `--bf28 live|fixed`. The default, `live`, keeps the September assertion. `fixed` asserts the reverse: `iage` URGENT at its urgent hour, and WARN at 48 h. The control matrix:

| checkout | `--bf28 live` | `--bf28 fixed` |
|---|---|---|
| `29749d92` (September) | V7 PASS, exit 0 | V7 FAIL, exit 1 |
| `db3b9e4e` (`dev`) | V7 FAIL, exit 1 | V7 PASS, exit 0 |

### 1.2 `tools/qc/ns-evaluator-arm.js` (T4.4, 46 checks): it does not load on `dev`

```
No cgm-remote-monitor checkout with T3.3 at …/externals/work/crm-views-census.
```

Exit 2, from the harness's own guard. It needs `lib/server/tenant-context.js` (T3.3), `lib/storage/tenant-scope.js` and `lib/server/socket-tenancy.js` (T3.5). None of the three is on `dev` `db3b9e4e`. They exist only on the `seam/*` branches (`seam/t3-k`, `seam/t1-2-storage-interface`, `seam/t30-schema-cred`, `seam/compose-*`). The September checkout `c8b456a7` (`crm-seam-n`) is not an ancestor of `db3b9e4e`. Every one of the eight sections builds its contexts through `tenantContext.createContextCache` or `tenantScope.withTenant`, so there is no tenancy-free subset to run. It was **not adapted**, because adapting it would mean writing substitutes for the three seam modules. The 46 checks still stand as results on `c8b456a7`. They were not re-run on `dev`.

---

## 2. Census: the server-side readers of the resident data on `db3b9e4e`

**Method.** The table lists every server-side match for `ctx.ddata`, `ctx.sbx`, `data-loaded`, `data-processed` and `dataloader.update` (client code excluded), plus the plugins' reads of `sbx.data` and the derived fields in `lib/data/ddata.js`. "Window" is what the code reads, by reading it. The last column says whether a bounded query through the storage interface (`ctx.entries.list`, `ctx.treatments.list`, `ctx.devicestatus.list`, `ctx.profile.last`, all on `lib/server/storage-reads.js` since ST-READS) supplies it today. **Measured** means the equality harness (§3) reproduced the output from bounded queries. The other rows are read-derived.

### 2.1 How the resident data is filled

| what | where | window |
|---|---|---|
| `ctx.ddata`, one per process | `lib/server/bootevent.js:294` | n/a |
| reload trigger | `bootevent.js:357-395`: on `tick` and `data-received`, with a leading-edge debounce and a concurrency guard | n/a |
| `sgvs`, `mbgs`, `cals` | `lib/data/dataloader.js:167-259` | the `entries` cache. First load (fewer than 20 cached) reads 48 h, later loads 15 min. Retention is 48 h from `Date.now()` (`lib/server/cache.js:30`) |
| `treatments` | `dataloader.js:306-355` | cache. First load 60 h, later 15 min. Retention is 60 h |
| newest Profile Switch with `duration: 0` | `dataloader.js:357-399` | `count: 1` within 372 days. Sets `lastProfileFromSwitch` |
| newest Sensor Start, Sensor Change, Sensor Stop, Site Change, Insulin Change, Pump Battery Change | `dataloader.js:401-441` | `count: 1` each, within 62 days, no upper time bound unless framed |
| `profiles` | `dataloader.js:443-455` → `lib/server/profile.js:279` | newest profile document (`limit: 1`) |
| `food` | `dataloader.js:458` | all |
| `devicestatus` | `dataloader.js:467-526` | cache, 24 h (48 h with `DEVICESTATUS_DAYS=2`) |
| `activity` | `dataloader.js:261` | 48 h |
| `dbstats` | `dataloader.js:528` | `db.stats()` |
| derived `*Treatments` arrays: site, insulin, battery, sensor, profile, combo bolus, temp basal, temp target | `ddata.processTreatments`, `lib/data/ddata.js:402-502`, called with `true` at `dataloader.js:127` | filters of `treatments`. Temp basal, profile and temp target arrays go through `processDurations` |
| treatment glucose (`mgdl`) | `lib/data/treatmenttocurve.js`, called at `dataloader.js:123` | the readings either side of each treatment, with no limit on the gap |

### 2.2 Readers, by view

| view | consumer (file:line) | `ddata` fields read | window or count it needs | bounded query today? |
|---|---|---|---|---|
| **alarms / notifications** | `bootevent.js:397-406` `updatePlugins`: `sandbox.serverInit`, `setProperties`, `initRequests`, `checkNotifications`, `process` | through `sbx.data` (a shallow clone, `lib/sandbox.js:55`): `sgvs`, `cals`, `mbgs`, `treatments`, `devicestatus`, the derived change-event arrays, `dbstats`. Off the live `ctx.ddata`: `profiles`, `profileTreatments`, `tempbasalTreatments`, `combobolusTreatments` (`sandbox.js:63-64`) | per §7b / EXP-MT-060 §4 item 3: 12 newest readings, a DIA of treatments, the 10 newest device statuses, the newest of each change event, the active profile | **measured: yes** for the emitted and requested alarms, on all 14 fixtures (§3.3). Not equal for every property computed along the way (§4 item 4) |
|  | `lib/notifications.js:61-66` `emitNotification` | `ctx.ddata.lastUpdated`, the ack and snooze clock | scalar | yes. It is the evaluation instant, not a stored record |
|  | `lib/plugins/treatmentnotify.js:64-75`, `:175` | `treatments` (newest), `mbgs` (newest) | 10 min | yes (inside the alarm window) |
|  | `lib/plugins/timeago.js:98` | newest reading, any age | newest 1 | yes |
|  | `lib/plugins/ar2.js:62`, `bgnow.js:57-75` | readings in four 5-min buckets | about 20 min | yes |
|  | `lib/plugins/boluswizardpreview.js:188` | `treatments` with carbs in the last 60 min, `profile` | 60 min plus IOB | yes |
|  | `cannulaage.js`, `sensorage.js`, `insulinage.js`, `batteryage.js` | `*Treatments` | newest of each type | yes (count 1 per type). See §4 item 4 for `sage` |
|  | `lib/plugins/upbat.js:37-41` | `devicestatus` with `uploader` | 30 min | yes |
|  | `lib/plugins/pump.js:67-70` | `devicestatus` with `pump` | `2 × urgentClock` min | yes |
|  | `lib/plugins/openaps.js:78-82`, `loop.js:47-51` | `devicestatus` | 6 h | yes |
|  | `lib/plugins/xdripjs.js:59-60` | `devicestatus` with `xdripjs` | 24 h | yes |
| **plugins / properties** | `lib/api2/properties.js:52-80` (`GET /api/v2/properties`) | `ctx.sbx.properties`, the last cycle's result | the union of the plugin windows above, plus: IOB from treatments over a DIA (`iob.js:46-55`); COB from treatments over the carb decay chain, which re-enters IOB at `lastDecayedBy` (`cob.js:127-170`); readings either side of each treatment in the window (`treatmenttocurve.js`) | **measured: yes**, with treatments over 3 DIA and readings over the same window plus the one reading before it. 1 or 2 DIA fail (§3.3). The 24 h device-status window is the default resident window, so for device status this view reads no less than `ddata` does |
| **v2 summary** | `lib/api2/summary/index.js:114-131` | `ctx.ddata.sgvs`, `ctx.ddata.treatments`, `ctx.sbx.data.profile`, `ctx.sbx.properties` | readings and insulin or carb treatments over `hours` (default 6, capped in practice at the 48 h reading retention); temp basals ending inside `hours` (`basaldataprocessor.js:125`); **every** temp target in `ddata`, with no time filter (`index.js:69-77`), so 60 h; `state` from properties | **measured: yes**, with temp targets over 60 h |
| **virtual assistants** | `lib/api/alexa/index.js:103`, `lib/api/googlehome/index.js:33` pass `ctx.sbx` to the plugin handlers | handlers read `sbx.properties` (bgnow, iob, cob, openaps, loop, pump, upbat, rawbg, xdripjs, dbsize, basal, ar2) and `sbx.data.profile` (`basalprofile.js:153`) | as properties | as properties (not run separately). `virtAsstBase.js:20,47` already reads the current reading through `entries.list({count: 1})` |
| **loop / pebble** | `lib/server/loop.js:29-35` | `ctx.ddata.profiles[0].loopSettings` | newest profile | yes (`profile.last`) |
|  | `lib/server/pebble.js:171-182` builds its own sandbox from `ctx.ddata` | `sgvs` (newest `count`, a request parameter, default 1), `cals`, newest `devicestatus` with uploader battery, IOB and COB as properties, bgnow | `count` readings and the properties windows | read-derived: yes, with `count` as a query parameter (not run) |
| **page / socket** | `lib/server/websocket.js:1115-1126` `update` on `data-processed`: `calcData(lastData, ctx.ddata)`, then `lastData = ctx.ddata.clone()` | the whole of `ddata` (a delta against the previous clone) | the display window: 48 h of readings, 60 h of treatments, 24 h of device status, all food | a delta needs the previous state. A bounded rewrite would compute it from changes (the `data-update` events) rather than from two snapshots. Not measured |
|  | `websocket.js:1099-1105`, first `dataUpdate` on authorize: `lastData.dataWithRecentStatuses()` (`ddata.js:128-153`) | `sgvs`, `cals`, `mbgs`, `food`, `treatments`, `dbstats`, `profiles` (with `@@@@@` keys removed), `devicestatus` (`recentDeviceStatus`: the newest 10 per device and type) | the display window | **measured: yes**, with time bounds equal to the retention windows (100 % of `ddata`'s bytes, §3.4), after the plugin pass (§4 item 3) and with same-`mills` ties put in `_id` order (§4 item 2) |
|  | `websocket.js:91, 170-173` `status()` and the profile-switch check | `lastProfileFromSwitch`, `profiles` | the newest Profile Switch, count 1 | yes |
| **v1 entries current** | `lib/api/entries/index.js:72-98` `ifModifiedSinceCTX` (`Last-Modified`, `304`) | the newest of `ctx.ddata.sgvs` | newest 1 | **measured: yes** |
|  | `entries/index.js:401-448` `query_models`, `lib/api/treatments/index.js:94`, `lib/api/devicestatus/index.js:100`, served from memory | `ctx.cache` (not `ddata`) | newest `count` | read-derived: a `find().sort().limit(count)` gives the same documents, unless a late upload is in the cache and not yet in a query window, or the reverse |
| **ddata/at** | `lib/data/endpoints.js:10-19` `/api/v2/ddata/at/:at` | `ctx.ddata.clone()`, refilled by `dataloader.update(…, {frame: true})`. Returns the live `ctx.ddata` when `at` is within 5 min of `lastUpdated` | intended: a window framed at `at` | **does not frame today** (§4 item 1) |
| **API v3 cache** | `lib/api3/storage/mongoCachedCollection/index.js:165-219` | writes into `ctx.cache` through `data-update`, with `ddata.processRawDataForRuntime` (`:187`). Reads no `ddata` fields | n/a | not a reader. Under ST-VIEWS it is a writer to whatever replaces the cache |
| **writers into the resident path** | `data-update` and `data-received` emitters in `lib/server/{entries,treatments,devicestatus,profile}.js`, `websocket.js`, `api3/generic/*`, `api/food` | `processRawDataForRuntime` and `idMergePreferNew` only (helpers) | n/a | n/a |

**Headline counts.** Ten consumers read `ctx.ddata` directly: `sandbox.serverInit`, notifications, v2 summary, v1 entries current, `server/loop.js`, `pebble.js` through `serverInit`, the websocket `update`, `status` and authorize paths, and `ddata/at`. Four read `ctx.sbx`: v2 properties, v2 summary, Alexa, Google Home. Two listen for `data-loaded` or `data-processed` (`bootevent.js` and `websocket.js`). Two call `dataloader.update` (`bootevent.js:375` and `endpoints.js:15`). 24 plugin files read `sbx.data` or the `sbx` reading helpers. Three v1 read routes serve from `ctx.cache` rather than `ddata`.

---

## 3. The equality harness

### 3.1 Design

The harness is in `tests/views-equality.test.js`, `tests/lib/views-equality/views.js` and `tests/lib/views-equality/fixtures.js`, on `feat/views-equality` `d69ff824`. It is registered in the `integration` tier, and `scripts/test-tiers.js check` reports `ok`.

- **Two arms, one loader.** Both arms run the shipping `lib/data/dataloader.js`, each with a fresh `lib/server/cache.js` and a private bus. The *resident* arm runs every query as the loader writes it, which is the server's first load. The *bounded* arm replaces each loader query, by kind (entries, treatments, profileSwitch, latest, devicestatus, profile, food, activity, dbstats), with the view's bounded queries through `ctx.entries.list` and the other storage-interface reads. It takes the union by `_id` and hands the result to the same loader code. Field mapping, `processTreatments`, the treatment-to-curve fit and the cache merge are therefore identical in both arms. Only what is read differs.
- **Views and how they are computed.**
  - `alarms`: the `data-loaded` cycle with a fresh `lib/notifications.js`. Compared: the emitted notifications, and the requested notifies and snoozes before highest-wins.
  - `properties`: `sbx.properties` after `setProperties`.
  - `summary`: the shipping `lib/api2/summary` router, called over HTTP with a context holding the arm's `ddata` and `sbx`.
  - `current`: the `Last-Modified` value of `ifModifiedSinceCTX`.
  - `page`: `dataWithRecentStatuses()`, after the plugin pass.
- **Evaluation instant.** `sbx.time` and the wall clock (`Date.now`) are both pinned to the instant the fixture was generated for (§4 item 5).
- **Fixtures.**
  - Seven synthetic scenarios, generated relative to the evaluation instant, with no records from people: `steady`, `urgentLow`, `recentTreatment` (a treatment 4 min old snoozes the low), `warnHigh`, `stale` (newest reading 45 min old), `noDeviceStatus` (IOB and COB from treatments), `deviceAged` (each change event past its urgent age). Each has 50 h of readings, 62 h of treatments and 26 h of device status, so every resident window has records just outside it.
  - The corpus: `VIEWS_CORPUS_DIR` pointed at the alignment repo's `tools/ns2parquet/fixtures` (seven sets). They are read in place, shifted in time so the newest reading is 2 min before the instant, and never copied into `cgm-remote-monitor`. Reports name them by position only (corpus #1 to #7).
- **Bounds used** (`views.js`):

| view | entries | treatments | device status | other |
|---|---|---|---|---|
| alarms (§7b) | 12 newest sgv, newest mbg, newest cal | 1 DIA (the profile's largest `dia`) | 10 newest | the loader's own count-1 lookups, profile, dbstats |
| properties | as alarms, plus readings over 3 DIA and the one before | 3 DIA | 24 h | as alarms |
| summary | as properties, plus readings over 6 h | max(3 DIA, 7 h), plus temp targets over 60 h | 24 h | as alarms |
| current | newest sgv | none | none | none |
| page | 48 h | 60 h | 24 h | food, activity, profile, dbstats as written |

### 3.2 Controls

- **Positive control (untampered).** Every fixture compares two independent resident loads, view by view. A difference there is the server's own nondeterminism and is reported as such, not as a bound.
- **Non-vacuity (`VIEWS_TAMPER=<view>`).** The named view's bound is made one record short at the edge the view depends on. Only that view may fail.

| tampered view | the record removed | result (synthetic + corpus, 98 tests) | failing tests, all of the tampered view |
|---|---|---|---|
| none | n/a | 98 passing, 0 failing | none |
| alarms | the newest treatment | 4 failing | `recentTreatment`, corpus #2, #4, #7 |
| properties | the newest device status | 11 failing | 6 scenarios (all but `noDeviceStatus`, which has none) and corpus #2, #3, #4, #5, #7 |
| summary | the oldest reading inside the 6 h the route returns | 13 failing | 6 scenarios and all 7 corpus sets |
| current | the newest reading | 14 failing | all 14 fixtures |
| page | the oldest reading in the 48 h window | 13 failing | 6 scenarios and all 7 corpus sets |

Where a tampered view stays green on a fixture, the dropped record did not matter there, and each case was checked:

- `alarms` stays green on 10 fixtures, because there the newest treatment neither snoozes nor changes an alarm.
- `summary` and `page` stay green on `stale`, because its oldest reading in the window sits exactly on the boundary (45 + 5k min = 6 h, and = 48 h). The route's cut-off (summary) or the cache's retention cut (page) is taken from `Date.now()` a moment after the query bound, so both arms drop that reading anyway.

Two earlier versions of the summary control **stayed green on every fixture**:

1. It dropped the union's oldest record, which was a calibration and then a reading older than 6 h.
2. It dropped the oldest reading from the summary's own query, but another query in the union still returned that reading.

Both broke nothing. The control now drops the oldest reading inside the 6 h from the union.

### 3.3 Results, and what the first runs found

The final state on synthetic and corpus fixtures is 98 passing and 0 failing, three runs in a row on Node 22.23.4. On synthetic fixtures alone it is 49 passing and 0 failing on Node 24.22.1. The bounds in §3.1 are not the first ones tried. Each change below was made after a failing run, and the failing output is recorded here:

| run | failure | cause | change |
|---|---|---|---|
| 1 | `page`: `$.devicestatus.0.openaps.iob.moment` present in one arm only. `$.sgvs.572.scaled` likewise | the plugin pass writes onto the shared documents (§4 item 3), and one resident `ddata` had been reused across views | a fresh resident load per view. The page view runs the plugin pass first, as the server does |
| 1 | `properties` `warnHigh`: `$.dbsize.totalDataSize` | `db.stats()` sampled at two moments | both arms get the same `db.stats()` sample |
| 1 to 4 | `page`: `$.treatments.24._id` order. **The resident-vs-resident control failed the same way** | same-`mills` records are ordered by which parallel loader query completes first (§4 item 2) | the page view puts each run of equal `mills` in `_id` order. Nothing else is reordered |
| 4 | `properties` `noDeviceStatus`: `$.iob.lastBolus.mgdl` 177 vs 161 | the treatment-to-curve fit needs the readings around each treatment | readings over the treatment window, plus the one before it |
| 5 | `properties`: `$.bgnow.sgvs.length` 1 vs 2 | the union of two queries returned the newest reading twice. The cache merge removes a duplicate only between batch and cache, not within a batch | the bounded arm takes the union by `_id` |
| 6 | `properties` `noDeviceStatus`: `$.cob.decayedBy` one minute apart | COB from treatments evaluates IOB at the previous carbs' decay time | treatments over 2 DIA |
| corpus | corpus #6: `$.cob.decayedBy` at 2 DIA, `$.cob.lastCarbs.mgdl` at 3+ DIA until readings covered the same window | as above, on real history | treatments and readings over 3 DIA. Sweep: 1 DIA fails 4 fixtures, 2 DIA fails 1, 3, 4, 6 and 15 DIA fail none |
| corpus | corpus #2: `$.iob.mills` differs by 2 ms. **The resident-vs-resident control failed the same way** | a device IOB without a timestamp is dated by the wall clock (§4 item 5) | the wall clock is pinned to the evaluation instant |

**On the alarm path, the §7b window gave the identical emitted and requested alarms on all 14 fixtures from the first run on.** No bound or comparison on the alarm path was changed. The run-1 fixes were to resident-arm reuse and to the `dbstats` sample, and the alarm view passed before and after them.

### 3.4 Size of what each view reads (`VIEWS_MEASURE=1`, serialised bytes of the `ddata` data fields, including the derived arrays)

| fixture | resident | alarms | properties | summary | current | page |
|---|---:|---:|---:|---:|---:|---:|
| synthetic (6 with device status) | 397,792 to 399,635 | 17,266 to 17,447 (4.3 to 4.4 %) | 66.7 to 66.9 % | 66.9 to 67.0 % | 567 to 570 B | 100 % |
| synthetic `noDeviceStatus` | 175,154 | 9,490 (5.4 %) | 24.4 % | 24.7 % | 570 B | 100 % |
| corpus #1 to #7 | 100,508 to 1,577,591 | 5.8 to 30.0 % | 62.3 to 100 % | 62.4 to 100 % | 503 to 570 B | 100 % |

These bytes include the derived `*Treatments` arrays, so they are not comparable field for field with EXP-MT-060's 852.1 KB fixture. Corpus #6 (30.0 %) has treatments dated up to 365 h after its last reading once shifted. Corpus #7 (15.5 %) is a short history.

---

## 4. Defects and mismatches found

Reported to the lane owner. No register id was allocated.

1. **`/api/v2/ddata/at/:at` does not return data framed at `at`.** Reproduced on `dev` `db3b9e4e`, MongoDB 7.0.43, synthetic fixture, clean cache: for `at` = now − 6 h, − 24 h and − 72 h, the response held the same 576 readings, newest 2 min old, with 72, 288 and 576 of them dated after `at`. Mechanism, from reading: the framed reload goes through `ctx.cache`. `insertDataRef` merges the framed query's results into the live cache and returns the whole cache, whose retention is measured from `Date.now()`, so the snapshot gets the live 48 h. Older framed results are filtered out by that retention. `lib/data/endpoints.js` and the cache merge in `dataloader.js` have the same shape on `v15.0.9` `c6a0d8ed` (read, not run). This is a correctness defect in a read endpoint, not a security exposure. It is described here at mechanism level only.
2. **Same-`mills` records are ordered nondeterministically in `ddata.treatments`.** Reproduced by resident-vs-resident: a Sensor Start and a Meal Bolus with equal `mills` swap order between loads. `dataloader.js:116-121` sorts by `mills` with a stable sort, and the arrival order comes from `callback-tasks.parallel` completion. Read-derived consequence, not reproduced: `processDurations`' `firstPerMills` (`ddata.js:237-241`) keeps the first record per `mills`, so which of two same-`mills` profile switches, temp basals or temp targets survives can vary between loads when they come from different loader queries.
3. **The plugin pass writes onto the resident documents.** Reproduced: `sandbox.scaleEntry` stores `scaled` on readings (`sandbox.js:263-267`), and the openaps plugin's state selector stores `moment` on `openaps.iob`, `openaps.enacted`, `openaps.suggested` and `mmtune` (`lib/client-core/devicestatus/openaps.js:179-220`). Because `serverInit`'s clone is shallow, the next first `dataUpdate` payload carries these fields. `pebble.js:160-170` already works around the `scaled` half. A bounded page view must run the plugin pass before serialising, or the payload loses these fields.
4. **`sage` reports the earliest of several same-hour sensor events, and the alarm window shows only the newest.** Observed on corpus #7: four Sensor Starts within 9 s. The resident `sage.Sensor Start.treatmentDate` is the earliest, and the bounded value (count 1, newest) is the latest. `sensorage.js:84-100` replaces a found event only when its whole-hour `age` is strictly smaller. The emitted alarms were identical on all fixtures. Read-derived and not reproduced: when such a burst straddles a whole-hour boundary, the two windows would report ages one hour apart, which moves the `sage` WARN and URGENT by up to the burst's spread. This is on the alarm path and is reported, not adjusted. Of the alarm window's outputs, only the notifications were compared. **Decided (maintainer, 2026-10-27): the newest Sensor Start is correct.** Today's earliest-in-burst value is a defect in `sensorage.js`, and the bounded view is meant to report the newest, so on this point it differs from `ddata` on purpose.
5. **A device-reported IOB with no timestamp is dated by the wall clock.** Reproduced as nondeterminism on corpus #2 (`$.iob.mills` 2 ms apart between two resident loads). Mechanism, read: `iob.fromDeviceStatus` uses `moment(iobOpenAPS.timestamp)` and `moment(iobLoop.timestamp)` (`iob.js:124,131`), which is "now" when the field is absent. `lastIOBDeviceStatus` then treats every such record as within its 30-min recency window, whatever the device status's own `created_at`. Read-derived and not reproduced: an old untimestamped device IOB can be taken as current IOB, which feeds `bwp` and its high-alarm snooze.
6. **Smaller observations, read-derived.**
   - `GET /api/v2/summary?hours=N` silently returns at most the 48 h reading retention, and returns every temp target in `ddata`, regardless of `hours`.
   - `processTreatments` sorts its derived arrays with `(a, b) => a.mills > b.mills`, a boolean comparator, so their order is the input order (`ddata.js:409-447`).
   - `loadLatestSingle` has no upper time bound unless framed, so a future-dated change event is returned as the newest and is then ignored by plugins that require `<= sbx.time`.

---

## 5. Limits

- **First load only.** The resident arm is the loader's first load (fresh cache, long windows). A long-running server's `ddata` comes from 15-min incremental loads merged into a cache, which can also hold late uploads and documents written through `data-update` that no query window revisits. The harness does not model that difference.
- **Views not run.** The socket's delta (`calcData`), pebble, the Alexa and Google Home handlers, and `loop.js` were not run as separate views. Read-derived, they reduce to the properties, current and profile bounds.
- **Alarm scenarios not driven.** Announcement treatments, `errorcodes`, `xdripjs`, `pump`, `loop` and `openaps` alarm states, and `dbsize` alarms were not driven into an alarming state, as in EXP-MT-060 §7.8.
- **Units and settings.** All fixtures use mg/dL (the corpus profiles carry their own units, unchecked), and `DEVICESTATUS_DAYS` is the default.
- **Bounds are measured, not derived.** The 3-DIA properties bound is what these 14 fixtures need. It is not a derived maximum.
- **Bytes, not costs.** §3.4 measures serialised bytes. Query cost against MongoDB was not measured.

## 6. Reproducing

```
# alarm slice (alignment repo, lab/views-census)
node tools/qc/alarm-critical-slice.js --root <cgm-remote-monitor checkout> [--bf28 fixed]

# equality harness (cgm-remote-monitor feat/views-equality), MongoDB on a test database
CUSTOMCONNSTR_mongo=mongodb://127.0.0.1:<port>/views_equality_test API_SECRET=<12+ chars> \
HOSTNAME=localhost INSECURE_USE_HTTP=true NODE_ENV=test \
node node_modules/mocha/bin/mocha.js --timeout 60000 --require ./tests/hooks.js --exit \
  tests/views-equality.test.js
# add VIEWS_CORPUS_DIR=<dir>, VIEWS_TAMPER=<view>, VIEWS_ONLY=<views>, VIEWS_MEASURE=1, VIEWS_COB_DIAS=<n>
```
