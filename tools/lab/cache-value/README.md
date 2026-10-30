# cache-value lab

What cgm-remote-monitor's in-memory cache still saves on a single-tenant site,
and a reproduction of an over-broad cache flush. Synthetic data only; never a
real site or real health data. Approved by the maintainer 2026-10-29.

Marks: [M] measured in this lab, [R] read from code, [A] an assumption of the
lab's traffic model.

## Anchors

| | |
|---|---|
| cgm-remote-monitor | official/dev e1f7ac4169256581bda70fef4fea1846ecf56d86 (fetched 2026-10-29), worktrees `externals/work/crm-cache-value` (unpatched) and `externals/work/crm-cache-value-bypass` (cache-bypass.patch applied), each with its own `npm ci` |
| 15.0.9 read for comparison | tag v15.0.9 = c6a0d8ed (read only, not run) |
| MongoDB | mongo:8.0 image, server version read from the server: 8.0.34 [M] |
| Node | v22.23.4 [M] |
| Part 1 container | cv-p1-mongo, id d73fbff4f743…, port 27801, restartCount 0 at start and end of each run (results/p1-*-docker.jsonl) |
| Part 2 containers | cv-p2-rt3h-<arm>, ports 27810-27814; ids and restart counts in results/rt3h/docker-<arm>.jsonl |

Containers run with `--ulimit nofile=64000:64000`, no `--rm` (mongo.sh). The
API secret is generated per run into a state directory outside git and is never
written into results.

## Code read first [R]

- `lib/server/cache.js`: retention 60 h treatments, 48 h entries, 24 h
  devicestatus (48 h with `devicestatus.days == 2`). `isEmpty` is "fewer than
  20 records". `dataChanged`: a `remove` with no `changes` empties all three
  caches and bumps all three removal generations (Part 1). `invalidate(type)`
  exists for a per-type flush.
- `lib/data/dataloader.js`: with a warm cache the entries, treatments and
  devicestatus loaders query a 15-minute window; with `isEmpty` they query
  48 h / 60 h / 24 h. Each reload also runs the other loaders (profile, food,
  activity, profile switches, latest sensor/insulin change treatments), which
  do not depend on the cache: a warm reload is 13 queries (8 of them on treatments) and 1 command [M].
- `lib/api3/storage/mongoCachedCollection/index.js`: per-record cache updates
  for insertOne/replaceOne/updateOne/deleteOne; `deleteInCache(undefined)` (a
  no-changes remove, so all three caches) after the filter-AST writes and after
  `deleteManyOr` of more than one document. The comment there says it drops
  "this collection".
- `lib/server/storage-writes.js`: v1 writes go through the plain
  MongoCollection (`lib/server/storage-reads.js` `collection()`), not the cached
  wrapper; the v1 modules emit their own `data-update`.
- `lib/storage/mongo-storage.js`: `DEFAULT_POOL_SIZE = 5`,
  `LEGACY_POOL_SIZE = 100`; `maxPoolSize` from `env.mongo_pool_size`, else 5;
  `minPoolSize` from `env.mongo_min_pool_size`, else 0; `maxIdleTimeMS` 30000.
  `lib/server/env.js` reads `MONGO_POOL_SIZE` / `MONGO_MIN_POOL_SIZE` via
  `readENV`, which also accepts the lowercase name and the `CUSTOMCONNSTR_`
  prefix [R]; `MONGO_POOL_SIZE=100` and `mongo_pool_size=9` both reach
  `env.mongo_pool_size` [M].
- v1 GETs from memory: entries (`lib/api/entries/index.js` `query_models`)
  when the only `find` key is `type` and `count` ≤ cached length; treatments
  (`lib/api/treatments/index.js`) only when `count` is the only query key and
  the cache holds at least `count` records (default count 100, so a site with
  fewer than 100 treatments in 60 h never serves `/treatments.json` from
  memory); devicestatus (`lib/api/devicestatus/index.js`) when the only key is
  `count` and the cache holds at least `count`.
- `lib/server/bootevent.js`: `tick` (every `HEARTBEAT` s, default 60) and
  `data-received` call a debounced reload (1 s wait, 5 s max wait, leading and
  trailing).

## Part 1: the over-flush

`overflush.js` boots the server in-process (as `lib/server/server.js` does,
without the websocket, `HEARTBEAT=3600` so only the actions trigger reloads)
against a seeded synthetic database (entries every 5 min for 50 h,
devicestatus every 5 min for 26 h, a treatment every 2 h for 62 h, plus three
Notes), then profiles (MongoDB profiler level 2, the probe's own connection
excluded by appName) each action and the reload it triggers.

| action | caches right after (tx/ds/entries) | reload windows (tx/ds/entries) | ops | docs returned | bytes returned |
|---|---|---|---|---|---|
| warm reload, nothing changed | 32/287/575 | 15 min each | 14 | 4 | 6,226 |
| DELETE /api/v1/treatments/<id> | 31/287/575 | 15 min each | 15 | 4 | 6,226 |
| DELETE /api/v1/treatments/?find[eventType]=Note (3 records), dev | **0/0/0** | 60 h / 24 h / 48 h | 15 | 890 | 716,202 |
| same, matching 0 records, dev | **0/0/0** | 60 h / 24 h / 48 h | 15 | 890 | 716,202 |
| delete by query, with overflush-fix.patch | 0/287/575 | 60 h / 15 min / 15 min | 15 | 32 | 10,247 |

All rows [M] (results/p1-unpatched.json, results/p1-unpatched-run2.json:
identical figures; results/p1-patched.json). Of the 716,202 bytes, devicestatus
is 613,602 and entries 97,166.

Control: `overflush.js --control` exits 1 on unpatched dev with
"entries cache emptied by a treatments delete-by-query: before 575, after 0",
the devicestatus equivalent, the two generation bumps and "entries reloaded
with a long load … window 48 h" / "devicestatus … 24 h"; it exits 0 with
`patches/overflush-fix.patch`. Draft register entry: BF-DRAFT.md.

## Part 2: what the cache saves

### Method

- Five arms run in parallel, in real time, each with its own MongoDB
  container, its own server process and its own replay process started at the
  same moment with the same schedule (`run.sh`). Real time, not compressed:
  compressing would shrink the heartbeat and follower intervals but not the
  dataloader's 15-minute window or the debounce, so a warm reload would return
  many more records than on a real site (the compressed smoke run in
  results/smoke shows this; its figures are not used).
- Arms: `base-a` and `base-b` (dev, cache, pool default 5: the noise floor),
  `cache-pool100` (dev, `MONGO_POOL_SIZE=100`), `bypass-pool5` and
  `bypass-pool100` (dev + `patches/cache-bypass.patch`). The bypass makes
  `cache.isEmpty` always true (every reload is a long load) and makes the three
  v1 GETs never serve from memory. The cache still exists and is still filled.
- Seed: the Part 1 history. Traffic [A], per arm (`replay.js`):
  - uploader: a v1 entry and a devicestatus every 5 min, devicestatus
    alternating v1 and v3 (JWT from an admin subject); a treatment every
    40 min alternating v1 and v3;
  - follower 1: `GET /api/v1/entries/sgv.json?count=1` every minute;
  - follower 2, every 5 min: `entries/sgv.json?count=288`,
    `devicestatus.json?count=1`, `treatments.json?count=10`;
  - follower 3, every 5 min: `entries.json?count=300&find[date][$gte]=<24 h>`,
    `treatments.json?find[created_at][$gte]=<24 h>`, `devicestatus.json?count=2`
    (the first two are never served from memory, in either arm);
  - the website: one socket.io connection, `authorize` with the secret.
  Followers authenticate with the API secret header [A].
- Bypass control (in `replay.js`, before hour 0): 20 `entries/sgv.json?count=1`
  and 20 `devicestatus.json?count=1`, counting serverStatus `opcounters.query`.
  A cache arm must cause fewer than 10 queries, a bypass arm at least 40. Shown
  red for the right reason with the declarations swapped
  (results/bypass-check-red.txt: "caused 0 MongoDB queries: FAIL: expected every
  one to read MongoDB" and "caused 40 MongoDB queries: FAIL: expected them
  served from memory").
- Measures per hour: serverStatus deltas (`opcounters`,
  `metrics.document.returned`, `network.bytesOut` minus the sampler's own two
  serverStatus replies per sample), client-side request latency p50/p95, server
  RSS and `data-loaded` count from `preload.js`, `connections.current`.
- Atlas M0 column: MongoDB, "Atlas Free Cluster Limits",
  https://www.mongodb.com/docs/atlas/reference/free-shared-limitations/ , read
  2026-10-29 (the page shows no last-updated date): "Free clusters: 100
  operations per second"; "a maximum of 500 connections"; "10 GB in and 10 GB
  out per period" (rolling seven days); 0.5 GB storage; throttling when a limit
  is exceeded. The page does not say whether commands (as opposed to reads and
  writes) count toward the operations limit, so the ops/s column counts CRUD
  plus commands, which is the upper reading. Bytes out per 7 days is the hour's
  figure × 168. These figures are a local 8.0.34 server's counters, not
  Atlas's metering.

### Results

Run `rt3h`: 3 real hours, all arms in parallel, 2026-10-29 20:26-23:27 UTC.
Every figure in the table is [M] (results/rt3h/summary.json, table.md). 0 of
473 replay requests per arm failed; all five bypass controls PASS; every
container's restartCount was 0 at start and end.

| arm | hour | CRUD ops | command ops | ops/s | docs returned | bytes out | reloads | GET p50/p95 ms | POST p50/p95 ms | RSS max MB | conns | M0: ops/s % of 100 | M0: bytes out/7d % of 10 GB | M0: conns % of 500 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base-a | 1 | 1,264 | 1,847 | 0.86 | 4,140 | 1,940,192 | 86 | 2.2/7.7 | 14.1/23.9 | 112.9 | 5 | 0.86% | 3.26% | 1% |
| base-a | 2 | 1,248 | 1,913 | 0.88 | 4,142 | 2,196,119 | 85 | 2.3/7.0 | 11.1/31.8 | 112.1 | 5 | 0.88% | 3.69% | 1% |
| base-a | 3 | 1,261 | 1,850 | 0.86 | 4,168 | 1,986,018 | 86 | 3.3/7.0 | 11.4/29.6 | 112.7 | 5 | 0.86% | 3.34% | 1% |
| base-b | 1 | 1,264 | 1,850 | 0.86 | 4,140 | 1,941,179 | 86 | 2.2/7.6 | 12.3/33.0 | 112.9 | 10 | 0.86% | 3.26% | 2% |
| base-b | 2 | 1,246 | 1,851 | 0.86 | 4,142 | 1,956,886 | 85 | 2.3/7.6 | 8.9/33.9 | 113.8 | 10 | 0.86% | 3.29% | 2% |
| base-b | 3 | 1,261 | 1,851 | 0.86 | 4,168 | 1,986,379 | 86 | 3.3/7.4 | 15.3/31.3 | 114 | 10 | 0.86% | 3.34% | 2% |
| cache-pool100 | 1 | 1,318 | 1,983 | 0.92 | 4,142 | 1,989,304 | 86 | 2.3/7.5 | 10.1/21.7 | 111.9 | 11 | 0.92% | 3.34% | 2.2% |
| cache-pool100 | 2 | 1,291 | 2,035 | 0.92 | 4,142 | 2,236,257 | 85 | 2.2/7.1 | 10.3/39.6 | 112.9 | 12 | 0.92% | 3.76% | 2.4% |
| cache-pool100 | 3 | 1,302 | 1,972 | 0.91 | 4,172 | 2,034,924 | 86 | 3.3/6.8 | 8.4/32.0 | 113.1 | 11 | 0.91% | 3.42% | 2.2% |
| bypass-pool5 | 1 | 1,372 | 1,789 | 0.88 | 84,127 | 63,758,250 | 86 | 4.5/11.2 | 15.7/68.2 | 126.5 | 10 | 0.88% | 107.11% | 2% |
| bypass-pool5 | 2 | 1,356 | 1,853 | 0.89 | 83,374 | 63,554,681 | 85 | 4.4/8.6 | 16.8/88.2 | 124.5 | 10 | 0.89% | 106.77% | 2% |
| bypass-pool5 | 3 | 1,369 | 1,790 | 0.88 | 84,323 | 64,303,678 | 86 | 5.3/10.5 | 15.8/66.9 | 128.4 | 10 | 0.88% | 108.03% | 2% |
| bypass-pool100 | 1 | 1,429 | 1,980 | 0.95 | 84,127 | 63,821,105 | 86 | 4.6/10.4 | 13.0/73.1 | 123.1 | 11 | 0.95% | 107.22% | 2.2% |
| bypass-pool100 | 2 | 1,409 | 1,981 | 0.94 | 83,374 | 63,377,942 | 85 | 4.6/10.4 | 16.4/73.6 | 123.7 | 12 | 0.94% | 106.47% | 2.4% |
| bypass-pool100 | 3 | 1,425 | 1,987 | 0.95 | 84,323 | 64,368,507 | 86 | 5.9/11.4 | 16.2/70.3 | 122.9 | 11 | 0.95% | 108.14% | 2.2% |

- bypass check (base-a, expect cache): 40 simple v1 GETs caused 0 MongoDB queries: PASS; errors: 0 of 473 requests
- bypass check (base-b, expect cache): 40 simple v1 GETs caused 0 MongoDB queries: PASS; errors: 0 of 473 requests
- bypass check (cache-pool100, expect cache): 40 simple v1 GETs caused 0 MongoDB queries: PASS; errors: 0 of 473 requests
- bypass check (bypass-pool5, expect bypass): 40 simple v1 GETs caused 40 MongoDB queries: PASS; errors: 0 of 473 requests
- bypass check (bypass-pool100, expect bypass): 40 simple v1 GETs caused 40 MongoDB queries: PASS; errors: 0 of 473 requests

Per-hour means of hours 1-3 (pool 5 arms; base = mean of base-a and base-b) [M]:

| | cache (base) | bypass-pool5 | bypass / cache |
|---|---|---|---|
| CRUD ops/h | 1,257 | 1,366 | 1.09 |
| finds/5 min (spot check, results/rt3h-command-breakdown-5min.txt) | 95 | 104 | 1.09 |
| commands/h | 1,860 | 1,811 | 0.97 |
| documents returned/h | 4,150 | 83,941 | 20.2 |
| bytes out/h | 2.0 MB | 63.9 MB | 32 |
| GET p50 / p95 (ms, range over hours) | 2.2-3.3 / 7.0-7.7 | 4.4-5.3 / 8.6-11.2 | |
| POST p95 (ms, range) | 23.9-33.9 | 66.9-88.2 | |
| RSS max (MB) | 112-114 | 124.5-128.4 | |
| M0 bytes out, ×168 h vs 10 GB / 7 days | 3.3-3.7 % | 106.8-108.0 % | |
| M0 ops/s (CRUD + commands) vs 100 | 0.86-0.88 % | 0.88-0.89 % | |

Reading the measurements:

- [M] Noise floor (base-a vs base-b): CRUD ops and documents returned agree
  within 2 per hour; bytes out within 0.1 % in hours 1 and 3. Hour 2 of base-a
  (and of cache-pool100 and bypass-pool5) carries a 5-minute command-breakdown
  probe this lab ran by hand (three extra connections, ~250 KB of serverStatus
  replies, ~60 commands), which explains base-a hour 2's 2.20 MB against
  base-b's 1.96 MB.
- [M] Reloads: 85-86 per hour in every arm (60 heartbeat ticks plus the
  uploader's posts). The cache does not change how often the server reloads,
  nor the number of queries per reload; it changes the window, so what the
  cache saves is documents and bytes, not operations. The operations it saves
  are the follower GETs it serves from memory (≈9 finds per 5 min here).
- [M] Commands are more than half of all operations in every arm; in the
  5-minute breakdown they are mostly driver monitoring (`hello` 178,
  `isMaster` 21-35, `dbStats` 7). Whether Atlas counts these toward the M0
  operations limit is not published on the page read.
- [M] Pool 100 against pool 5 (same cache mode): about 40-57 more CRUD ops and
  120-200 more commands per hour (more `isMaster`, i.e. connection handshakes,
  and more `update` in opcounters), 1-2 more connections, no latency difference
  beyond the hour-to-hour spread. With this traffic the server never had more
  than 12 connections open (including the replay's own).
- [M] Against M0: at this traffic, average operation rate is under 1 % of
  100/s in all arms (per-second peaks were not measured). Bytes out is the
  limit the cache matters for: about 0.33 GB per 7 days with the cache, about
  10.7 GB without, which is above the published 10 GB out per rolling 7 days.
  These are a local server's counters, not Atlas metering, and the traffic is
  the model above [A]; a site with more followers or a larger devicestatus
  scales the bypass figure roughly with the long-load size.


## Files

- `mongo.sh` containers; `common.js` synthetic data and helpers; `seed.js`.
- `overflush.js` Part 1 probe and control; `patches/overflush-fix.patch`.
- `run.sh`, `replay.js`, `preload.js`, `analyze.js` Part 2;
  `patches/cache-bypass.patch`.
- `results/` raw outputs: `p1-*.json` and docker state, `rt3h/` (replay and
  metrics jsonl, anchors, docker state, summary.json), `smoke/` (compressed,
  harness check only), `bypass-check-red.txt`.
- `BF-DRAFT.md` draft register entry (no id).

Re-run: `CV_STATE=<dir outside git> ./run.sh <name> <hours>` then
`node analyze.js results/<name>`; Part 1:
`CRM_DIR=<tree> MONGODB_URI=mongodb://127.0.0.1:27801/cvp1 node overflush.js --control --out <file>`.
