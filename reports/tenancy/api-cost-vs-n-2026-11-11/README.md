# api role: per-request cost against tenant count N, from reading the code (2026-11-11)

*Dated read-only record (contributor-facing). Never edited after capture. Every claim here is
**read-derived**: nothing was run, because a capacity campaign was using the machine. Each
finding is a hypothesis for the capacity lane to measure. Line numbers are at the anchors below.*

## Anchors (read from `git log` at the time of writing)

| tree | commit |
|---|---|
| cgm-remote-monitor `workspace/capacity-fixes-20261111` (worktree `externals/work/crm-capacity-fixes-20261111`) | `5c60aec669362b032a10d6dd7ac368e9c61e8003` |
| nightscout-deploy `deploy/capacity-fixes-20261111` (worktree `/home/bewest/src/nightscout-deploy-capacity-fixes-wt`) | `d1c7aca4f95998ae68d0fc42e3f236d68991b740` |
| alignment `main` | `958fd2e18202c38bc53fe6631fb77712f4d7f648` |

Paths below are relative to the cgm-remote-monitor worktree unless they start with `deploy:`,
which means `bindings/compose/multitenant/` in the nightscout-deploy worktree.

## Mismatches between the brief and the tree

1. `lib/server/serve/private-api.js` does not exist. The socket-authority contract that realtime
   calls (`authorizeSocket`, `executeSocketMutation`) is `lib/server/realtime/private-api.js`. The
   api process loads it from `lib/server/serve/preview-api.js:359-361`.
2. `deploy/multitenant/config.js` does not exist in the deploy tree. The plan is
   `deploy:config.js`, and the image build places it at `deploy/multitenant/` (`deploy:compose.yaml:87`).
3. The api has **no tenant runtime cache, LRU or warm-cell limit**. `TENANT_COLD_BEYOND_BOUND` is a
   **time** alert, not a size bound (finding 7). Every tenant's services stay resident and none are
   evicted (finding 5), so a cache-thrash mechanism does not exist.
4. The tenant-activity admission reader (`tenant_activity` per request) is not active in the
   fixture. The api config in `deploy:config.js:165-174` has no `activity` block, so
   `preview-api.js:329-338` is skipped and `prepareTenant` is `startup.admit` alone.
5. `tenant_change_stamps(uuid[])` is not on the api's path. Only realtime (`lib/server/realtime/change-detector.js:25`)
   and the evaluator (`lib/server/serve/evaluator-preview.js:73`) call it.

## What the fixture runs

- **One Node process for the api.** The api container runs `node deploy/multitenant/entrypoint.js api`
  (`deploy:compose.yaml:87`) under `init: true` (tini). That calls `lib/cli` `main(['multitenant','api'])`
  (`deploy:entrypoint.js:9`), which loads the command in-process (`lib/cli/index.js:26-29`; `passthrough`
  spawning is for other programs). There is no `cluster` or `worker_threads` in `lib/server/serve`. So
  the measured 4.46 cores means that about 3.5 cores were spent outside the JavaScript main thread:
  V8 GC helper threads (parallel scavenge, concurrent mark and sweep), background compilation, and the
  libuv threadpool. On the pool side, pg's SCRAM uses WebCrypto `deriveBits` PBKDF2
  (`node_modules/pg/lib/crypto/utils.js:86-88`), which runs on the threadpool for every new PostgreSQL
  connection. Per-thread CPU from `/proc/<pid>/task/*/stat` would show how the time divides; the
  split is unmeasured.
- **The operation window is on for every request.** `deploy:config.js:191` sets
  `MULTITENANT_OPERATION_CONFIG` for the api. `lib/server/serve/index.js:134-145` therefore builds an
  operation pool and window, `operation-cohort.js:46` installs it into every PostgreSQL connection the
  role opens, and every HTTP request and every socket-authority call runs inside `operationWindow.run`.
- **The k6 workload uses legacy credentials.** v1 calls carry `?token=<subject token>`
  (`tools/mt-bench/capacity/k6/workload.js:7-13,77,108,114`); v3 treatments carry a Bearer HS256 JWT
  that was exchanged once. Stock browser sockets send the exchanged JWT as `token` in the `/` namespace
  (`tools/mt-bench/capacity/probe.js:75`).

## Findings, ranked by likely cost at 3,000 tenants

The ranking is a judgement from reading. "O(1) in N" means that the cost of one request does not
depend on N, though the total rate of such requests grows with N.

### 1. A PostgreSQL client held for each request's lifetime, from a pool of 8. O(1) in N; caps concurrency

- `lib/server/tenant-app/index.js:157-171`: each HTTP request runs inside `operationWindow.run(tenant, …)`,
  and the body waits for `res` `finish` or `close`. `lib/server/internal-api/transport.js:182` does
  the same for each socket-authority call (`lib/server/serve/internal-listener.js:87-90`).
- `lib/tenant-lifecycle/operation-window.js:133-187` (`execute`): `pool.connect()` on the operation
  pool, then `pg_try_advisory_lock_shared`, `BEGIN`, `set_config`, the lifetime epoch statement,
  `INSERT tenant_lifecycle_operations`, `COMMIT`. The client stays checked out for the whole request.
  Afterwards it runs `BEGIN`, `set_config`, `UPDATE … finished=true`, `COMMIT` and an advisory unlock.
  That is about 12 round trips and two writes per request, and the client is held the whole time.
- The lifetime epoch (`operation-window-epoch.js:49-55`, used with `lifetime=true` at
  `operation-window.js:152-155`) aggregates every user `pg_class` row (`oid >= 16384`), every
  `pg_namespace`, `pg_roles` and `pg_auth_members` row, and the user `pg_attribute` rows that have
  ACLs, once per request. It is fixed in N, because tables are shared and tenants are rows, but it is
  PostgreSQL CPU on every request.
- Pool size: `NS_POOL_OPERATION_MAX`, default **8** (`lib/server/serve/pool-config.js:249`), with a
  5,000 ms connect timeout. The fixture does not set it. So **at most 8 requests are in progress in
  the api at once**, across HTTP and socket authorization together. During warm, each tenant
  initialization also runs inside the window (`tenant-startup.js:15-21,148`) and holds a client,
  4 at a time (`NS_TENANT_STARTUP_CONCURRENCY`), which leaves 4 for traffic.
- Refusals cost the full envelope too. `prepareTenant` (`TENANT_WARMING`) runs **inside** the window
  (`tenant-app/index.js:160-161`; `realtime/private-api.js:71` runs after `transport.js:182`).
- Fit with the measurement (read-derived): with 430–600 authorize calls in flight against 8 clients,
  the rest wait in `pool.connect()` and fail at 5 s. Throughput becomes 8 divided by per-call latency.
  About 200/s implies about 40 ms per call, which is plausible for finding 2's work. This would explain
  the 10.2 s p50 (5 s of queueing plus retries) and the 99.8% failures, because HTTP shares the same 8
  clients.
- Rows grow with time, not with N. Each request inserts a `tenant_lifecycle_operations` row (PK
  `operation_id`, FK to windows), and no code in `lib/` deletes them.
- **Fix direction.** Do not hold a pooled client for the lifetime of a request. The inner
  transactions already take the shared advisory lock and check admission on their own clients
  (`lib/storage/postgres-connection.js:131-141`). Register lifecycle operations in batches or in
  memory with a durable summary, and run the cheap in-process refusals (warm state, unknown tenant)
  before the window. Until then, size `NS_POOL_OPERATION_MAX` above the expected in-flight count plus
  startup concurrency, and refuse at boot when startup concurrency is 8 or more.

### 2. Credential verification repeated on every call, with no caching. O(1) in N; heavy constant

Per v1 request with `?token=` (`lib/server/tenant-app/data-access.js:117-125`):
- `secrets.exchangeLegacyCredential` (`lib/secrets/component.js:221-230`) runs `verifyLegacyCredential`,
  then `subjectSnapshot`, then `signJWT`, then `verifyJWT`. `data-access.js:123` then calls
  `verifyLegacyCredential` **again** with the JWT it just issued.
- Each `verifyLegacyCredential` (`component.js:62-120`) does `legacy.read`, then `read()`. `read()`
  calls `authorize`, which for `decrypt` calls `legacy.read` **again**
  (`lib/server/serve/preview-api.js:289-291`), then an audit INSERT, `store.get` and a Vault Transit
  decrypt.
- Each `access()` (`component.js:27-38`), whether for sign, verify or decrypt, writes an audit row
  with `synchronous_commit = on` (`lib/secrets/postgres.js:51-55,129-147`). `verifyJWT` calls
  `access()` **before** the format check (`component.js:285-288`), so the failed JWT attempt on a raw
  subject token still writes an audit row and costs a transaction.
- Approximate total per v1 request, counted from the code: 5 Vault HTTP calls (decrypt, hmac, verify,
  decrypt, verify), 6 synchronous-commit audit INSERTs, 4 `legacy.read`, 2 `store.get`, 1
  `subjectSnapshot` and 1 or more `authorize`. That is about 14 PostgreSQL transactions. Under the
  window each one adds a `pg_try_advisory_lock_shared`, `BEGIN`, `set_config`, the lower epoch
  statement, `COMMIT` and an unlock (`postgres-connection.js:120-160`, `operation-window.js:95-131`).
- Per `authorizeSocket` with the stock client's JWT (`lib/server/realtime/authority.js:26-61`): 2
  `legacy.read`, 2 audits, `store.get`, a Vault decrypt, a Vault verify and `subjectSnapshot`, which
  is 6 transactions and 2 Vault calls.
- Per **anonymous** `authorizeSocket` (realtime's warm probe, `lib/server/serve/preview-realtime.js:82`):
  `current = permission => authority.authorize(…)` (`authority.js:55`) is awaited 3 times for
  permissions and 6 times for collections (`authority.js:57-60`). That is 9 sequential transactions,
  each re-reading the same config and roles join (`lib/tenant-authorization/postgres.js:166-225`).
- Pools are hard-coded at 4: legacy (`lib/secrets/legacy-postgres.js:181`), secrets
  (`lib/secrets/postgres.js:42-44`), authority (`lib/tenant-authorization/postgres.js:86`), access
  (`access-postgres.js:17`, 1 s timeout) and alarm (`realtime/private-api.js:99`). Only
  `NS_POOL_API_MAX` and `NS_POOL_OPERATION_MAX` are configurable.
- Vault per call: `getToken` runs `reference(tokenEnv, source)` (`preview-config.js:151`), which reads
  `source[name]` three times (`preview-config.js:26-31`).
- **Fix direction.** Keep, per tenant, the derived root hashes and subject-token digests for a short
  TTL, invalidated on rotation, so that the decrypt does not run on every request. Cache a verified
  HS256 JWT by digest until its `exp` or the recheck interval. Fetch the anonymous or root permission
  set in one query, as `subjectSnapshot` already does, and check it in memory. Drop the second
  `legacy.read` inside `authorize`. Write audit rows in batches, or once per credential per interval.

### 3. A full data frame and a fresh legacy graph per v1/v2 request. O(1) in N; grows with each tenant's data

- `lib/server/serve/preview-domains.js:174-177` builds a new `createLegacy` graph (Express v1/v2
  apps, `ddata` and a cache) for **every** legacy request. Lines 183-193 attach `prepareTenantFrame`,
  and `lib/server/tenant-app/legacy-authorization.js:13` runs it for every authenticated non-metadata
  route, including `GET /api/v1/entries/sgv.json?count=1` and POSTs.
- `lib/server/tenant-app/snapshot.js:27-70` runs the shipping dataloader (`lib/data/dataloader.js`,
  9 loaders: 2 days of entries, 2.5 days of treatments, 12 months of profile switches, latest-single
  reads over 62 days, profile, food, devicestatus, activity, dbstats). Each port read is a
  window-wrapped transaction.
- dbstats (`lib/storage/postgres-tenant-stats.js:15-26`) runs `SELECT sum(pg_column_size(doc))` over
  each of the 7 domain tables, covering all of the tenant's rows under RLS, on every frame.
- About 20 or more transactions per v1 request, on top of finding 2. The work grows with how long each
  tenant has been uploading, not with N.
- **Fix direction.** Load a frame only for the routes that read derived state. Keep one frame per
  tenant, invalidated by the write clock or change stamp. Compute dbstats only for status routes, and
  from an incremental counter.

### 4. Realtime admission file read, compared and scanned 3 or 4 times per internal call. **O(N) per call**

- `lib/server/realtime/admission.js:21-29`: `read()` calls `c.parsedFile`
  (`lib/server/realtime/contract.js:30-37`). That does a synchronous `statSync`, `openSync`,
  `fstatSync` and chunked `readSync` of the **whole** file, a UTF-8 decode, and a full string
  comparison with the previous text, on every call. It then runs
  `[...current.tenants.keys()].some(id => !initialIds.has(id))`, an N-element array and scan, on every
  call.
- Calls per `authorizeSocket`: the transport lifetime `resolveTenant` (`realtime/private-api.js:110`),
  then `tenantFor` (`private-api.js:39,70`), then `verify`'s `admission.allows` (`authority.js:27`),
  which makes **3**. `executeSocketMutation` adds the receiver's `resolveTenant`
  (`tenant-socket-forwarding.js:80`), which makes **4**.
- Size at 3,000: the file is written compact (`deploy:bootstrap.js:33-38,174`) at about 94 bytes per
  tenant (`{"id":…,"enabled":true,"aliases":["tNNNN.example.test"]}`), so about 280 KB (computed, not
  measured). That is about 0.85 MB of synchronous reading and comparing per `authorizeSocket` on the
  event loop, plus the 3,000-element scans. This is the api's counterpart of the realtime `readCurrent`
  re-read that the peer lane found.
- `configFile.read` also reads `process.env.MULTITENANT_CONFIG_MAX_BYTES` on each call (`config-file.js:264-266`).
- **Fix direction.** Key the cache on `stat` identity (inode, size, mtime, ctime), as
  `lib/server/serve/evaluator-config.js:122-128` already does. Do the expansion check once per changed
  parse instead of once per call. Resolve the tenant once per internal call and pass it down.

### 5. Every tenant's service graph stays resident, with no eviction. O(N) heap, which raises GC cost per request

- `preview-domains.js:33,44-114`: `services` and `building` keep, for every warmed tenant, an Express
  app with 6 v3 `Collection`s and their routes, a legacy graph (v1/v2 apps, `ddata`, cache), a
  snapshot service, a REST context and its routers, and the socket ports. `tenant-startup.js:107` keeps
  a cell per tenant. Nothing evicts them.
- Major-GC marking scales with live heap. With N graphs resident, each request's garbage (finding 3
  allocates a whole graph and frame per request) costs more GC time as N grows. This is the only
  mechanism found for "per-request CPU rises with N" on the HTTP path, and it fits the extra cores
  beyond the main thread. Heap per tenant and GC share are unmeasured. `--trace-gc` or a heap snapshot
  at 1,000 and 3,000 would settle it.
- **Fix direction.** Measure retained heap per tenant first. Then share one route table per process,
  with tenant-parameterised ports, instead of per-tenant Express apps. Add an operator-bounded LRU for
  idle tenants' graphs, so that cold reconstruction is the cost of rarely-used tenants.

### 6. Vault tokens as N environment variables. Possibly O(N) per lookup (hypothesis)

- `deploy:config.js:184` puts `NS_VAULT_0 … NS_VAULT_{N-1}` into the api's environment, and
  `deploy:load-env.js:36` assigns them to `process.env`. Each Vault call reads its reference 3 times
  (finding 2), and each admission read reads the config bound once (finding 4).
- In Node, a `process.env` read goes to the C library's `getenv`, which scans `environ` linearly. That
  comes from Node's implementation; **it was not read in this tree**. If it holds, each lookup is
  O(N), at a few microseconds per call at 3,000. It is small, but it is a true per-request O(N) term.
- `config.providers` and `config.bindings` lookups are Maps, so O(1) (`preview-config.js:164-165,282,287`).
- **Fix direction.** Read the token references into a Map once at load (`preview-config.js:148-151`),
  or use the shared `tokenFile` sink that already exists. Read `MULTITENANT_CONFIG_MAX_BYTES` once.

### 7. Warm: front-of-queue moves are O(N), and the slow per-tenant init produces `TENANT_COLD_BEYOND_BOUND`

- `lib/server/serve/tenant-startup.js:135-139`: a request for a cold tenant moves it to the front with
  `queue.indexOf` and `splice`, which is **O(N) per refused request** while the warm runs. It is small
  in absolute terms (thousands of element moves per call).
- **The bound.** `TENANT_COLD_BEYOND_BOUND` is raised by a timer (`tenant-startup.js:167-175`) when
  a tenant has been cold for longer than `NS_TENANT_COLD_ALERT_MS`, **default 120,000 ms**
  (`pool-config.js:287-289`). The fixture does not set it. It is an alert and nothing more: no
  eviction and no refusal. A cell raises it at most once until it completes (`tenant-startup.js:109-112,123`).
- **Per-tenant init** (`preview-api.js:316-325`):
  - `floors.ensure`: an insertion floor per ordered domain, then a `MAX(srvModified)` over all 6
    domain tables for the tenant (`postgres-domains.js:113-139`);
  - `legacy.read`, `store.get` and `authority.authorize`;
  - `domains.initializeTenant`, which `build`s the graph. That build opens **3 new PostgreSQL clients**
    (`lib/server/tenant-socket-order-port.js:18`, from `preview-domains.js:61-63`) to run the
    schema-wide socket-order migration `check` for treatments, devicestatus and profile. Each is a new
    TCP connection plus SCRAM, repeated identically for every tenant: 9,000 connections at 3,000
    tenants.
- Fit with the measurement (arithmetic from the figure in the `deploy:compose.yaml:96-97` comment,
  "1,000 tenants took 341-421 s"): about 2.4–2.9 tenants per second at concurrency 4. About 290–350
  tenants are warm by 120 s, so about 2,650–2,700 cells alert per api lifetime at 3,000. One lifetime
  can raise at most 3,000. **5,550 therefore needs two api lifetimes in the log, or lines from
  realtime or the evaluator**, which use the same module and message (`preview-realtime.js` warm,
  `evaluator-preview.js:103`). Check which container each line came from.
- **Fix direction.** Run the schema-wide checks once per process. Use a deque with a separate
  priority lane for request-driven warms. Raise startup concurrency only together with finding 1's pool.

### 8. Minor O(N) items off the hot path

- Healthcheck every 2 s (`deploy:compose.yaml:91-95`, `deploy:health.js:28`): `getStatus` sorts and
  returns all N tenant ids (`lib/server/serve/operation-cohort.js:172-177`), and the transport parses
  and validates the reply. O(N log N) at 0.5 Hz, which is negligible. At about 39 bytes per id, the
  health client's 1 MiB `maxBytes` would be exceeded only above about 26,000 tenants, which is beyond
  the ceiling of 10,000.
- Alarm ack only: `selectedState.readCurrent` runs twice per ack (`realtime/private-api.js:49,52`).
  Each run does a `statSync` plus an N-key scan (`evaluator-config.js:129-131`).
- Boot only: the access-token key set is built from every tenant with `createPublicKey`, up to 10,000
  keys (`preview-config.js:183-202`). Per-request lookup is a Map get, so O(1).
- Realtime side (for the peer lane): in realtime's warm,
  `config.admission.aliases.find(alias => alias.tenant === tenant)` (`preview-realtime.js:81`) is O(N)
  per tenant, so O(N²) per warm.

### Checked and found bounded (read-derived)

- Tenant resolution is a Map lookup (`lib/tenant-resolution/index.js:141,156`). The private API
  builds its second resolver once, at bind (`realtime/private-api.js:36,109`).
- The api parses its config file once at boot (`preview-config.js:47-50`) and never re-reads it per
  request.
- Domain tables have tenant-leading indexes (`migrations/candidates/postgres-entries-v1.json`), and
  RLS quals are `tenant_id = …`. `tenant_activity` has a PK on `tenant_id`
  (`lib/tenant-lifecycle/postgres-candidate.json`, migration `0007`). No all-tenant query was found on
  the request path. The plans have not been checked with `EXPLAIN`.
- The data dispatcher is one middleware with a Map lookup (`preview-domains.js:131-137`).

## Deploy bounds: which scale with N and which are fixed

| setting | where | value in fixture | scales with N |
|---|---|---|---|
| tenant count | `NS_DEMO_TENANTS`, ≤ `PREVIEW_MAX_TENANTS` (`lib/server/serve/tenant-ceiling.js:7`) | 1..10,000 | is N |
| `socketForwarding.maxTenants` (admission bound) | `deploy:config.js:173` | `n` | yes |
| realtime `maxTenants` | `deploy:config.js:153` (`limits`) | `n` | yes |
| realtime `maxSockets` | `deploy:config.js:37,163` | max(100, n × `NS_DEMO_SOCKETS_PER_TENANT`, default 2) | yes |
| operation-window lock rows | `deploy:config.js:190` | `n` | yes |
| access-token public keys | `deploy:bootstrap.js:102-108`; cap 10,000 at `preview-config.js:186` | one per tenant | yes |
| Vault token env vars in the api | `deploy:config.js:184` | `n` | yes |
| `MULTITENANT_CONFIG_MAX_BYTES` | `deploy:compose.yaml:16` from `NS_BOOTSTRAP_CONFIG_MAX_BYTES` | operator-set; core default 1 MiB | must be raised by hand |
| `NS_POOL_OPERATION_MAX` | `pool-config.js:249` | 8 (unset) | fixed |
| `NS_POOL_API_MAX` | `pool-config.js:245` | 4 (unset) | fixed |
| legacy, secrets, authority, access, alarm, subject-admin pools | hard-coded (finding 2; `lib/subject-admin/postgres.js:34`) | 4 each (access: 1 s connect timeout) | fixed, not configurable |
| `NS_TENANT_STARTUP_CONCURRENCY` | `pool-config.js:251` | 4 (unset) | fixed |
| `NS_TENANT_COLD_ALERT_MS` | `pool-config.js:288` | 120,000 (unset) | fixed |
| `NS_TENANT_READINESS` | `pool-config.js:280-284` | `serve` (unset) | n/a |
| `NS_TENANT_WARM_RETRY_MS` (realtime against api) | `pool-config.js:292-296` | 60,000 (unset) | fixed |
| internal `operationTimeoutMs`, Vault `timeoutMs` | `deploy:config.js:171,173` | 5,000 ms | fixed |
| realtime `authorizationRecheckMs` | `deploy:config.js:163` | 30,000 ms | fixed (so recheck rate grows with N) |
| PostgreSQL `max_connections` | `deploy:compose.yaml:24-37` (not overridden) | image default (100 in stock PostgreSQL; not read from the pinned image) | fixed |
| api healthcheck `start_period` | `deploy:compose.yaml:98` | 900 s | fixed |

The settings that scale with N are rosters and admission bounds. Every concurrency and connection
setting is fixed. That is why the offered load grows with N while the api's in-flight capacity
(8 operation clients) does not.

## Suggested measurements (none run)

1. Count `pool.connect` waits and timeouts on the operation pool. Rerun 3,000 with
   `NS_POOL_OPERATION_MAX=64` as a one-variable control for finding 1. If failures and p50 do not
   move, finding 1 is not the limiter.
2. Get per-thread CPU of the api process (`/proc/<pid>/task/*/stat`), and `--trace-gc` at 1,000 and
   3,000 idle and loaded, for finding 5 and the 4.46-core question.
3. Count calls per request to Vault, to `secret_audit` and to `tenant_lifecycle_operations`, from
   `pg_stat_statements` and the Vault audit log, to confirm finding 2's counts.
4. Rerun 1,000 tenants with the 6,000 sockets' proportion of socket load (2 per tenant). The 1,000 and
   3,000 runs differ in socket load as well as N, so 50.5 against 89 CPU-ms per tenant-minute does not
   isolate N. The 3,000 figure also counts CPU spent on requests that failed.
