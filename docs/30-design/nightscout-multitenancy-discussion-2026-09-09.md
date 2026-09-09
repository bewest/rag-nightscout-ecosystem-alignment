# Nightscout multitenancy: approaches, tradeoffs and a benchmark plan

Date: 2026-09-09. Status: draft for maintainer discussion. Companion to
[Nightscout modernization review and proposed next steps](../60-research/nightscout-modernization-next-steps-2026-09-09.md);
this document is deliberately *tangential* to that work and does not depend on its outcome.

Sources inspected: `externals/cgm-remote-monitor-official` (v15.0.9, `dev` @ `a8888f0d`,
node `>=20.x`, express 4.22.2, socket.io ~4.8.3, mongodb driver ^5.9.2, no mongoose) and
`externals/nocturne` (.NET 10 + PostgreSQL + Rust crates, host-based multitenancy).
Note that `externals/cgm-remote-monitor` in this workspace is a 0.5.0 historical checkout;
all Nightscout citations below use `cgm-remote-monitor-official`.

---

## 1. Why this question is worth asking

Nightscout's single-tenant design is a real feature: one process, one `env`, one
`API_SECRET`, one Mongo database, one in-memory data universe. It makes the codebase
legible, makes plugins trivial to write, and makes a site's blast radius exactly one
person. It also means the *unit of deployment is a person*: one Heroku/Azure/Fly/Atlas
bill, one upgrade, one TLS cert, one set of environment variables, per person with
diabetes. That per-capita cost and per-capita operational burden is the ceiling on
who can use Nightscout, and it is the main reason distributed care teams,
clinics, research cohorts and "family runs five sites" cases are painful.

The maintainers' long-standing intuition is that the shape of the fix lives at `ddata`:
if the runtime data universe were keyed by tenant rather than implicit, the rest of the
server might follow. This document tests that intuition against the code, sets out the
candidate architectures, and — most importantly — proposes how to *measure* rather than
argue about the tradeoffs.

**Nothing here is a proposal to merge.** The deliverable being requested is evidence.

---

## 2. What is actually single-tenant today

### 2.1 The runtime data object

`ddata` is a plain object created once at boot, holding the whole site's recent world:

```js
var ddata = {
  sgvs: [] , treatments: [] , mbgs: [] , cals: []
  , profiles: [] , devicestatus: [] , food: [] , activity: []
  , dbstats: {} , lastUpdated: 0
};
```
`externals/cgm-remote-monitor-official/lib/data/ddata.js:11-22`

Processing attaches derived arrays (`sitechangeTreatments`, `insulinchangeTreatments`,
`batteryTreatments`, `sensorTreatments`, `profileTreatments`, `combobolusTreatments`,
`tempbasalTreatments`, `tempTargetTreatments`) — `lib/data/ddata.js:249-337`.

Three cost centres matter for any multitenant plan:

| Cost | Location | Shape |
|---|---|---|
| JSON deep clone of every loaded document | `lib/data/ddata.js:29-79` (`processRawDataForRuntime`) | stringify+parse per load |
| Old/new merge | `lib/data/ddata.js:82-106` (`idMergePreferNew`) | ~O(old × new), not hash-indexed |
| Client delta | `lib/data/calcdelta.js:15-76` (`nsArrayTreatments`) | ~O(old × new) with deep compares |

`clone()` (`lib/data/ddata.js:108-123`) and `dataWithRecentStatuses()`
(`lib/data/ddata.js:126-145`) produce the client-facing projection.

### 2.2 The cache and retention windows

```js
const retentionPeriods = {
  treatments: constants.ONE_HOUR * 60
  , devicestatus: ...days == 2 ? constants.TWO_DAYS : constants.ONE_DAY
  , entries: constants.TWO_DAYS
};
```
`externals/cgm-remote-monitor-official/lib/server/cache.js:26-31`

So the steady-state per-site working set is roughly **48 h of entries, 60 h of
treatments, 24–48 h of devicestatus**, plus long-tail queries merged into
`ddata.treatments` (profile switches up to ~12 months, sensor/site/insulin/battery
changes up to ~62 days) — `lib/data/dataloader.js:341-430`.

The cache also keeps *removal generations* per datatype so the loader can detect a delete
that landed mid-query and retry rather than resurrect the document
(`lib/server/cache.js:29-34`, `lib/data/dataloader.js:159-196`, `:301-332`, `:456-489`).
Any tenant-aware cache must preserve this property per tenant.

### 2.3 The load cycle

Nine loaders run in parallel per update (`lib/data/dataloader.js:128-146`), expanding to
roughly **14 database operations per load**: entries, treatments, profile switches, six
"latest special treatment" queries, profile, food, devicestatus, activity, dbstats.
Incremental loads shrink the *rows* (15-minute windows —
`lib/data/dataloader.js:159`, `:301`, `:456`) but not the *query count*.

Loads are triggered by a debounced handler on the event bus:

```js
var updateData = debounce(runDataLoad, UPDATE_DEBOUNCE_WAIT, { leading: true, trailing: true, maxWait: UPDATE_MAX_WAIT });
ctx.bus.on('tick', ...); ctx.bus.on('data-received', ...);
```
`externals/cgm-remote-monitor-official/lib/server/bootevent.js:301-330`
(`UPDATE_DEBOUNCE_WAIT = 1000`, `UPDATE_MAX_WAIT = 5000`, heartbeat default 60 s —
`lib/server/bootevent.js:3-4`, `lib/settings.js:37`, `lib/bus.js:7`).

A concurrency guard prevents overlapping loads *on the shared ddata*
(`lib/server/bootevent.js:301-318`) — a guard that must become per tenant.

After each load, plugins run against a freshly built sandbox:

```js
var sbx = require('../sandbox')().serverInit(env, ctx);
ctx.plugins.setProperties(sbx);
ctx.notifications.initRequests();
ctx.plugins.checkNotifications(sbx);
ctx.notifications.process(sbx);
```
`externals/cgm-remote-monitor-official/lib/server/bootevent.js:332-341`

**This is the most encouraging fact in the codebase.** `sandbox.serverInit(env, ctx)`
(`lib/sandbox.js:45-84`) is already a per-invocation object parameterised over
*(settings, data, time)*. The plugin contract is therefore already tenant-shaped; what is
not tenant-shaped is `ctx` itself.

### 2.4 Realtime

Socket.IO uses exactly one room:

```js
io.to('DataReceivers').compress(true).emit('dataUpdate', delta);
```
`externals/cgm-remote-monitor-official/lib/server/websocket.js:150`, join at `:792`

Per-connection authorization exists and is resolved from secret/token into shiro
permissions (`lib/server/websocket.js:123-140`), but the resolved subject does not select
a data context. Tenant rooms (`DataReceivers:<tenantId>`) plus tenant-bound authorization
are mandatory, and are a *correctness/safety* requirement, not an optimisation: a leak
here is another person's glucose and alarms.

### 2.5 The storage seam

`lib/storage/mongo-storage.js` is a connection/collection factory
(`:105-205` connect, `:207-209` raw collection, `:211-223` indexes). Domain modules
(`lib/server/entries.js`, `treatments.js`, `devicestatus.js`, `profile.js`, `food.js`,
`activity.js`) receive **raw Mongo collections** and use driver semantics directly:
`find/findOne/sort/limit/toArray`, `insertOne/insertMany`, update with upsert, `ObjectId`,
Mongo query operators, `$`-aggregation in reporting paths. API v3 adds its own query
translation (`lib/server/query.js`, `lib/api3/`).

There is therefore **no adapter seam capable of accepting a different query model today**.
(API v3 does add a thin caching/collection layer — `lib/api3/storage/mongoCachedCollection/`
and `lib/api3/storage/mongoCollection/` — but it is Mongo-shaped too.)
This is the single most important finding for the keyv/SQLite question (§5).

### 2.6 Everything else that is process-global

`env` and `env.settings` (`lib/server/env.js:106-208`, `lib/settings.js:7-31`,
`:261-280`, `:328-340`), `API_SECRET`, authorization storage/roles/subjects
(`lib/server/bootevent.js:198-203`), the Mongo pool, the cache, the dataloader, the
websocket namespace, the plugin registry and its per-plugin closure state (e.g.
`lib/plugins/openaps.js:8-18`, `lib/plugins/speech.js:1-7`), external clients and timers
(`lib/plugins/mmconnect.js:15-30`, `lib/plugins/pushover.js:7-13`), the event bus,
language, and enclave key material (`lib/server/enclave.js:1-22`).

**Per-tenant settings surface** (the real work item): units, timezone/language, alarm
thresholds and snooze intervals, alarm type selection, enabled/shown plugins, raw-BG
visibility, device provenance obscuring, devicestatus retention, bridge/connect
credentials, notification credentials and recipients, auth defaults.

### 2.7 Sizing anchor

A synthetic measurement (`node --expose-gc`, 200 tenants, one `ddata`-shaped object each:
576 SGVs, 600 treatments, 576 Loop-style devicestatus with 72-point prediction arrays,
no derived arrays, no clones, no `lastData`):

```
tenants 200   heap delta 241.2 MB   per tenant 1.21 MB   JSON 795 KB/tenant
```

That is the **floor**, not the estimate. Steady state additionally holds cache arrays,
derived treatment arrays, the previous `lastData` for delta computation, and transient
JSON clones during load. A working assumption of **4–8 MB resident per active tenant**
should be treated as a hypothesis to be measured (§8, EXP-MT-001), not a number to quote.
At 6 MB, 1 000 tenants ≈ 6 GB of live JS objects before headroom — which is precisely why
the residency/tiering question (§4) matters more than the storage question.

---

## 3. What Nocturne already did

Nocturne is the strongest available evidence because it solved this problem in production
shape, and its choices are worth copying or consciously rejecting.

| Concern | Nocturne's answer | Citation |
|---|---|---|
| Tenant identity | `tenants` row; `Guid Id` stable, mutable `Slug` for routing | `externals/nocturne/src/Infrastructure/Nocturne.Infrastructure.Data/Entities/TenantEntity.cs:8-91` |
| Request resolution | **Host header subdomain**, not path prefix or token claim | `src/API/Nocturne.API/Multitenancy/TenantResolutionMiddleware.cs:244-248` |
| Special modes | apex/single-tenant fallback, tenantless setup routes, `{token}.share.{domain}` | `TenantResolutionMiddleware.cs:249-279` |
| Isolation | Shared tables + `tenant_id` discriminator, EF Core global query filter **and** PostgreSQL RLS | `NocturneDbContext.cs:14-64`; `Migrations/20260227034745_EnforceMultitenancy.cs:66-76` |
| Fail-closed | `FORCE ROW LEVEL SECURITY`; unpinned context ⇒ `current_setting('app.current_tenant_id')` empty ⇒ zero rows; roles are `NOSUPERUSER NOBYPASSRLS` | `Interceptors/TenantConnectionInterceptor.cs`; `externals/nocturne/CLAUDE.md` |
| Credential binding | Token tenant claim must match host-resolved tenant, else reject; explicit `TenantId` predicates as defence in depth | `Middleware/Handlers/LegacyJwtHandler.cs:73-97`; `Handlers/DirectGrantTokenHandler.cs:127-152` |
| Cache | Many small tenant-GUID-keyed caches with TTL + explicit invalidation; **no monolithic per-tenant aggregate** | `Services/Entries/EntryCacheAdapter.cs:24-120` |
| Realtime | SignalR groups always prefixed `"{tenantId}:{group}"`; hub rejects connections without an active tenant | `Hubs/TenantAwareHub.cs:29-74`; `Services/Realtime/SignalRBroadcastService.cs:148` |
| Native hot path | Rust `nocturne-alerts-core` behind a JSON-in/JSON-out C ABI (`nocturne-alerts-ffi`); **stateless**, state threaded through the call | `crates/nocturne-alerts-ffi/README.md` |
| Benchmarks | BenchmarkDotNet micro/query benchmarks + RLS isolation integration tests | `tests/Performance/**`, `tests/Integration/**/Rls/*` |

Four transferable lessons:

1. **Isolation must fail closed at the storage layer**, not only in application code. RLS
   is the difference between "we filter correctly" and "we cannot fail to filter".
2. **Host-based routing keeps existing clients working.** Every uploader, follower app and
   `API_SECRET` in the ecosystem already points at a hostname; subdomain-per-site means
   xDrip+, AAPS, Loop, Trio and nightscout-connect need no changes.
3. **Nocturne deliberately did *not* build a per-tenant `ddata`.** It uses bounded,
   individually keyed, TTL'd caches. That is the opposite of Nightscout's design and is a
   direct challenge to the "just make ddata multitenant" instinct.
4. **The native (Rust) boundary is stateless and coarse-grained** — one JSON envelope per
   evaluation. That is exactly the shape that survives an FFI/WASM boundary (§6).

Two caveats Nocturne itself records: the browser bridge fans some notifications to the
whole tenant room rather than per-subject rooms (`Services/Realtime/RealtimeGroups.cs:32-57`),
and there is **no published tenants-per-instance target or tenant-count scaling
benchmark** in the repo, and no k6/NBomber/Socket.IO load harness. So Nocturne proves
*correctness* of an approach, not *capacity*. Capacity is what §8 is for.

### 3.1 Should cgm-remote-monitor *depend on* Nocturne?

Options, honestly stated:

| Option | What it means | Pros | Cons |
|---|---|---|---|
| **D1. Independent implementation** | Nightscout builds its own tenancy | No new runtime/toolchain; community can maintain it in JS | Duplicates solved work; two divergent tenancy semantics in the ecosystem |
| **D2. Shared contracts only** | Adopt Nocturne's tenant model, slug/GUID semantics, RLS pattern, group naming as a **spec**; independent code | Interop and mental-model alignment; cheap; migration paths between servers | Requires someone to write the spec down and keep it in sync |
| **D3. Nocturne as data plane** | cgm-remote-monitor becomes a UI/plugin tier over Nocturne's tenant-aware API | Least new backend code; inherits RLS + benchmarks | Node deployment now requires .NET+Postgres; hard dependency on another project's roadmap; hosting story gets *harder*, not cheaper, for small operators |
| **D4. Nocturne as reference, share the Rust crates** | Independent tenancy in JS; reuse `nocturne-alerts-core` style stateless native cores via WASM | Shared algorithm truth across servers; testable parity | Only pays off where the hot path is genuinely CPU-bound (§6, and see EXP-MT-020) |

The workspace already has grounds for D2 + D4: shared OpenAPI specs in `specs/openapi/`
and cross-project terminology in `mapping/cross-project/terminology-matrix.md`.
D3 is the option that should be argued *for* explicitly if anyone wants it, because it
inverts the project's independence.

---

## 4. Candidate architectures for cgm-remote-monitor

The choice is really *where tenant state lives*, and it decomposes into two independent
axes: **isolation unit** (process vs. context) and **residency** (always-resident vs.
computed on demand).

### A. Process per site (today, at scale)

One `cgm-remote-monitor` per person, N containers. Zero code change; isolation by OS.
Cost is the node baseline (~60–90 MB RSS before data) plus a Mongo connection pool plus a
container per person — the status quo we are trying to escape. Worth benchmarking anyway
as the **control arm**: everything else must beat it on $/tenant while matching it on
isolation.

### B. Context per tenant, one process ("multi-ctx")

Turn `ctx` into `ctxFor(tenantId)`: per-tenant `settings`, `ddata`, `cache`, `dataloader`,
`plugins`, `bus`, authorization, socket room. Requests resolve tenant → context.

- **Pro**: smallest conceptual change; the sandbox contract already fits
  (`lib/sandbox.js:45-84`); plugin API unchanged.
- **Con**: N × timers, N × event buses, N × plugin instances, N × resident ddata. Memory
  and GC pressure scale linearly with *registered* tenants, not *active* ones. Plugin
  module-level state (`lib/plugins/speech.js:1-7`) becomes a cross-tenant bug class.
  A single tenant's O(n²) treatment merge stalls the shared event loop for everyone.
- **Verdict**: probably the honest first prototype, but it is the option most likely to
  hit a wall around low hundreds of tenants. Measure it (EXP-MT-002).

### C. Context per tenant + residency tiering ("hot/warm/cold")

Same as B, but a tenant's ddata is materialised on demand and evicted on inactivity:

- *hot*: active follower/websocket connection ⇒ resident ddata, delta broadcast, plugins
  and alarms running.
- *warm*: recent writes but no viewers ⇒ cache only; ddata rebuilt lazily on read.
- *cold*: uploads land straight in storage; **alarms are the hard part** — a person with
  no browser open still needs hypo alerts, so a cheap always-on evaluator (a small
  bounded per-tenant alarm state machine over the last few readings, à la
  `nocturne-alerts-core`) must run for cold tenants without materialising a full ddata.
- **Pro**: cost tracks *concurrency*, not *registrations*. Most sites have one viewer and
  long idle periods, so this is where the order-of-magnitude lives.
- **Con**: needs a real eviction policy, cold-start latency budget, and a separated alarm
  path. This is a genuine architecture change, not a refactor.
- **Verdict**: the most promising direction, and the one the benchmark plan should be
  designed to prove or kill (EXP-MT-003, EXP-MT-010).

### D. Stateless server, storage-resident derived data

No resident ddata at all: every read recomputes/pages from the store, with the store doing
the range queries and the aggregation. This is where SQLite/Postgres/columnar formats
become interesting (§5) — a 48-hour SGV window is a trivial indexed range scan.

- **Pro**: memory becomes ~O(concurrent requests); horizontal scaling is trivial; restart
  is free.
- **Con**: Nightscout's client protocol is delta-oriented (`calcdelta.js`), and plugin
  chains assume a whole-world object. Recomputation per request could easily be *more*
  total CPU than one resident copy. Needs measurement, not assertion (EXP-MT-004).

### E. Sharded/partitioned: one process, K tenants

Orthogonal and pragmatic: whatever B/C/D wins, run K tenants per process across M
processes, with a tenant→shard router. Bounds blast radius, bounds GC pause impact, allows
rolling upgrades, and lets a noisy tenant be moved. Any serious deployment ends up here.

### Cross-cutting requirements for B–E

1. Tenant resolution middleware (host, then path prefix as fallback, then token claim
   verified against the resolved tenant — Nocturne's ordering, and its rejection rule).
2. Tenant-scoped socket rooms and tenant-bound socket authorization.
3. Tenant-scoped settings object; every read of `env.settings` audited.
4. Per-tenant plugin instances; a lint rule or test banning module-level mutable plugin state.
5. Per-tenant concurrency guard, backpressure and a fairness policy (one tenant must not
   monopolise the loop).
6. Storage-layer fail-closed isolation (RLS, separate database, or separate file).
7. Per-tenant quotas/accounting: memory, docs, query rate — needed for both fairness and
   the cost model that justifies the whole exercise.
8. Alarm delivery for non-resident tenants (safety-critical).

---

## 5. Storage abstraction, keyv, SQLite and schemas

### 5.1 The keyv hypothesis, tested

The intuition — "keyv would decouple Nightscout from its storage engine" — is right about
the *goal* and, on the evidence, wrong about the *mechanism*.

Keyv is a **key→value** store with namespaces, TTLs and adapters (Redis, SQLite, Postgres,
Mongo, in-memory). Nightscout's data access is **range and predicate queries**:
`{date: {$gte: t}}` sorted descending with limits, `eventType` filters, "latest N of type
X", `find/sort/limit` in every domain module, plus API v3 query translation
(`lib/server/query.js`). Keyv has no query language; every such access would become
"load a namespace and filter in JS", which is exactly the resident-memory cost we are
trying to reduce. Storing per-tenant blobs under keyv keys ("tenant:X:entries:2026-09-09")
reinvents a worse index and breaks API v3 filtering.

Where keyv **is** a good fit, and worth adopting on its own merits:

- sessions, share tokens, rate-limit counters, tenant-resolution cache
  (slug→tenant), enclave-ish derived secrets, plugin scratch state, socket presence.
- Those are precisely the things that must become *tenant-namespaced* and that you want to
  move out of process memory when you shard (§4E). Keyv's namespace concept maps
  1:1 onto tenant prefixes, and its adapter set means small deployments use memory/SQLite
  while large ones use Redis with no code change.

**Proposed framing**: keyv for *ephemeral tenant-keyed state*; a real query abstraction for
*time-series and clinical records*. Conflating the two is the trap.

### 5.2 What a real storage abstraction would have to be

Given §2.5, an adapter must be introduced at the **domain module** level, not below it.
The plausible seam is a small repository interface per collection, e.g.

```
entries.list({find, sort, limit, skip})  →  Promise<Doc[]>
entries.upsertMany(docs)                 →  Promise<{inserted, updated}>
entries.remove(filter)                   →  Promise<count>
```

with the *existing* API v3 query model (`lib/api3/`, `lib/server/query.js`,
`specs/openapi/aid-entries-2025.yaml`) as the canonical query language rather than raw
Mongo filters. That reframes the work as: **make the internal call sites speak the
documented public API's query model**, which is defensible independently of multitenancy,
testable against the existing suites, and is the prerequisite for *any* alternative engine.

Candidate backends, once that seam exists:

| Backend | Isolation model | Strengths | Risks |
|---|---|---|---|
| MongoDB + `tenantId` discriminator | Compound index `{tenantId, date}` | Zero migration for existing sites; keeps all current queries | No RLS equivalent; isolation is application-enforced only; shared Atlas cluster noisy-neighbour |
| MongoDB, database-per-tenant | DB per site | Strong isolation; per-tenant backup/restore/export | Connection/namespace overhead; Atlas cost per DB; N × index sets |
| PostgreSQL + RLS | Nocturne's model, fail-closed | Proven in-ecosystem; real constraints; JSONB for the messy documents; time-series indexes | New engine for Nightscout; migration of every query; ops learning curve |
| **SQLite file per tenant** (`better-sqlite3` or `node:sqlite`) | Filesystem | Isolation is a *file*; backup = copy; delete = unlink; near-zero idle cost; per-tenant snapshot/restore/export makes data portability trivial | Node-level concurrency (WAL helps), thousands of open handles, replication/HA story, cloud filesystems |
| Columnar/Arrow/Parquet for history | File per tenant per period | Reports and long-window analytics get dramatically cheaper; workspace already has `externals/ns-parquet*` precedent | Not for the hot 48 h; adds a second storage tier |

On the Node SQLite choice specifically: `node:sqlite` is built in from Node 22.5 but as of
Node 25/26 is still a release candidate rather than marked stable, while `better-sqlite3`
remains the faster, mature option; either way this is a benchmark input, not a belief
(EXP-MT-012).

**SQLite-file-per-tenant is the most intriguing under-explored option** because it makes
isolation a filesystem property, makes per-tenant cost near-zero when idle (aligning
perfectly with residency tiering, §4C), and makes "export my data / move my site" a file
copy — which is a digital-rights win as much as a cost win (cf. `docs/DIGITAL-RIGHTS.md`).
Its risks (open file handles, WAL contention, HA) are exactly the kind of thing a
benchmark settles in a day.

### 5.3 Schemas: mongoose, zod and friends

Nightscout uses no ODM today (no mongoose). Introducing one now would couple the codebase
harder to Mongo — the opposite of the goal. The workspace already holds the real schema
assets: OpenAPI 3.0 in `specs/openapi/aid-*-2025.yaml` with `x-aid-*` annotations.

Suggested position for discussion:

- **Runtime validation at boundaries only** (HTTP ingest, connector output, storage
  read-back), with zod or an Ajv/JSON-Schema compilation of the existing OpenAPI specs.
  Vendor and uploader payloads are hostile; TypeScript types would not validate them.
- **Generate, don't duplicate**: derive validators from `specs/openapi/` so the spec, the
  conformance scenarios in `conformance/`, and the server cannot drift.
- **Validation is a hot path in multitenancy**: N tenants × ingest rate. Compiled
  validators (Ajv `standalone`, or zod with precompiled schemas) belong in the benchmark
  matrix (EXP-MT-013), because naive per-document validation can dominate CPU.
- Tenant identity should be a *storage-enforced* column/predicate, never a validated
  application field.

---

## 6. WASM and eBPF: where they help, and where they don't

Both are worth experimenting with, but they answer different questions, and it is worth
being blunt about which parts of the problem are actually CPU-bound.

### 6.1 WebAssembly

Realistic uses, best first:

1. **Shared algorithm cores across servers.** Nocturne already isolates alert evaluation
   into a stateless Rust crate with a JSON envelope
   (`crates/nocturne-alerts-ffi/README.md`). Compiling the same crate to WASM and calling
   it from Node gives cgm-remote-monitor *bit-identical* alarm/IOB/COB/oref semantics with
   Nocturne, AAPS and Trio parity testable in CI. The value here is **correctness and
   ecosystem convergence**, with performance as a bonus.
2. **Hot inner loops**: `idMergePreferNew`, `calcdelta`, treatment duration processing —
   the O(n²) sites in §2.1. But note: *the first fix for an O(n²) loop is an O(n) loop with
   a Map*, in plain JavaScript. WASM should be benchmarked **against an optimised JS
   baseline**, never against the current one, or the result is meaningless (EXP-MT-020
   insists on this).
3. **Columnar/compact representation.** The biggest per-tenant memory win is not faster
   code, it is not representing 576 SGVs as 576 heap objects with 15 properties each. A
   typed-array/struct-of-arrays representation (in JS or in WASM linear memory) could
   plausibly cut resident bytes by an order of magnitude, and WASM linear memory can be
   released wholesale on eviction — no GC negotiation. This is the strongest WASM argument
   and it is about *memory*, not speed.
4. **Sandboxing untrusted per-tenant logic** (custom alarm rules, user-defined plugins).
   Speculative, but it is the classic multitenant WASM use case, and it would let sites
   customise behaviour without operator-level trust.

What WASM will **not** fix: Mongo round-trips, JSON serialisation across the boundary
(which can cost more than the compute saved), socket.io fan-out, or event-loop fairness.
Node worker threads + `SharedArrayBuffer` may deliver more of the fairness benefit than
WASM does, and should be in the same experiment arm.

### 6.2 eBPF

eBPF cannot be a Nightscout runtime component (it is kernel-side, Linux-only, and requires
privilege). Its honest role is **observability of the benchmark**, and that role is genuinely
valuable:

- Off-CPU and scheduler analysis: where do 500 tenants actually block — Mongo I/O, GC,
  TLS, event loop?
- Per-tenant syscall/network accounting via `bpftrace`/`bcc`, giving a real cost-per-tenant
  attribution that userland profiling cannot produce cleanly.
- `tcp_retrans`, connection churn, and socket buffer pressure under N websocket clients.
- Optionally: enforcement at the edge (cgroup/tc rate limiting per tenant process in a
  sharded deployment, §4E).

**Recommendation**: treat eBPF as first-class *measurement* infrastructure for §8 and
explicitly out of scope as an application dependency. If the benchmark harness produces
per-tenant flamegraphs and off-CPU profiles, the architecture debate becomes short.

---

## 7. Runtime performance model to test

Capacity per process should be modelled and then *checked*:

```
resident_bytes  ≈ base_rss
                + Σ_hot ( ddata + cache + lastData + derived arrays )
                + Σ_warm ( cache only )
                + Σ_cold ( alarm state only )

cpu_per_minute  ≈ Σ_active ( loads_per_min × ( db_ops(≈14) + clone + merge + sort
                                              + plugins + delta + serialize ) )
```

Known amplifiers to attack before any exotic technology:

| Amplifier | Evidence | Cheap fix to test first |
|---|---|---|
| JSON deep clone per load | `lib/data/ddata.js:29-79` | structuredClone, or clone-free normalisation |
| O(old×new) merge | `lib/data/ddata.js:82-106` | Map-indexed merge by `_id`/`identifier` |
| O(old×new) treatment delta | `lib/data/calcdelta.js:15-76` | Map-indexed diff |
| 14 queries per load regardless of window | `lib/data/dataloader.js:128-146`, `:385-393` | Combine the six special-treatment queries; skip loaders whose window is empty |
| Repeated filter/sort of full treatment array | `lib/data/ddata.js:249-337` | Single pass bucketing |
| Per-object heap overhead | §2.7 | Compact/columnar representation |

A plausible and testable claim: **these six fixes alone move the tenants-per-process
number more than any storage or WASM change.** If true, that reorders the whole roadmap,
and it is a much easier sell to maintainers than a rewrite.

---

## 8. Benchmark plan

The purpose is to replace opinion with numbers, using everything available: real code,
synthetic tenants, ecosystem-realistic workloads, and both userland and kernel profiling.

### 8.1 Harness

Proposed location `tools/mt-bench/` (new, workspace-side; nothing lands in
cgm-remote-monitor until results justify it):

- **Workload generator**: replayable tenant traces derived from realistic uploader
  behaviour — xDrip+/Dexcom 5-minute entries, AAPS batch uploads (the case
  `UPDATE_DEBOUNCE_WAIT`/`UPDATE_MAX_WAIT` exist for), Loop devicestatus every 5 minutes
  with 72-point prediction arrays, careportal treatment bursts, nightscout-connect
  backfills. The workspace already has real-shape data under `externals/ns-data*` and
  `externals/ns-parquet*` to derive distributions from — use them rather than inventing
  rates.
- **Tenant mix profiles**: `idle` (uploads only, no viewers), `single-viewer`,
  `family` (3–5 followers), `clinic-view` (many read-only sessions), `heavy`
  (AAPS batch + Loop + xDrip + reports). Populations expressed as ratios, e.g.
  70/20/7/2/1 %.
- **Clients**: HTTP via `autocannon`/`k6`; websockets via a socket.io-client swarm that
  performs the real `authorize` handshake and consumes `dataUpdate` deltas
  (`lib/server/websocket.js:123-150`, `:776-801`).
- **Server under test**: pluggable arm (see 8.3), each behind an identical façade.
- **Instrumentation**: `process.memoryUsage()`/RSS sampling, `--cpu-prof` and
  `--heap-prof`, `clinic doctor|flame|bubbleprof`, `perf_hooks` event-loop delay
  histograms (`monitorEventLoopDelay`), GC traces, Mongo/Postgres server-side query stats,
  and eBPF (`bpftrace`) for off-CPU, syscall and TCP behaviour.
- **Existing assets to reuse**: `npm run test:stress` (`tests/concurrent*.test.js`), the
  socket flaky harness (`test:flaky:socket`), and `tests/hooks.js` fixtures for correctness
  gating; Nocturne's `tests/Performance/**` for cross-server comparison shape.

### 8.2 Metrics (fixed set, reported for every arm)

**Cost**: peak/steady RSS per tenant; total RSS at N; CPU-seconds per tenant-hour;
DB ops per tenant-minute; DB storage per tenant-month; **$ per tenant-month** on two
reference deployments (single VM; managed container + managed DB).
**Latency**: p50/p95/p99 for `POST /api/v1/entries` ack, entry→`dataUpdate` broadcast
propagation, `/api/v1/entries.json?count=N`, report generation, cold-tenant first paint.
**Safety**: alarm evaluation latency and miss rate for cold/warm tenants; delta
correctness vs. full-payload reference; **zero cross-tenant leakage** (hard gate).
**Stability**: event-loop delay p99 under a noisy tenant; GC pause distribution;
behaviour at 2× target N; recovery after restart.
**Fairness**: p99 latency of a quiet tenant while a heavy tenant runs a 12-month report.

### 8.3 Arms

| ID | Arm | Question |
|---|---|---|
| EXP-MT-001 | Control: N separate processes, current code | Baseline $/tenant, RSS/tenant, isolation reference |
| EXP-MT-002 | Multi-ctx in one process (§4B), Mongo + tenantId | Where does the wall sit? |
| EXP-MT-003 | Multi-ctx + residency tiering (§4C) | Does cost track concurrency instead of registrations? |
| EXP-MT-004 | Stateless/on-demand (§4D) | Is recompute-per-request cheaper than resident ddata? |
| EXP-MT-005 | Sharded K-tenants-per-process (§4E) | Best K for fairness vs. overhead |
| EXP-MT-010 | Cold-tenant alarm evaluator | Can alarms be safe without a resident ddata? |
| EXP-MT-011 | Storage: Mongo discriminator vs DB-per-tenant vs Postgres+RLS vs SQLite-per-tenant | Query cost, isolation, idle cost, backup/restore/export time |
| EXP-MT-012 | `better-sqlite3` vs `node:sqlite` at 100/1 000 open tenant DBs | Handle limits, WAL contention, cold open latency |
| EXP-MT-013 | Validation: none vs zod vs compiled Ajv-from-OpenAPI | CPU cost of boundary validation at N × ingest |
| EXP-MT-014 | keyv for ephemeral tenant state (memory vs SQLite vs Redis adapters) | Does it hold up as the shard-safe state layer? |
| EXP-MT-020 | Hot loops: current JS vs Map-optimised JS vs WASM vs worker-thread offload | Is WASM worth the boundary cost *after* the JS fix? |
| EXP-MT-021 | Representation: objects vs typed-array/columnar ddata | The memory-per-tenant order-of-magnitude question |
| EXP-MT-022 | eBPF-instrumented run of the winning arm | Where does time really go at scale? |
| EXP-MT-030 | Nocturne under the identical workload | Cross-server capacity comparison; validates the harness itself |

`EXP-MT-030` matters disproportionately: running the *same* generator against Nocturne
gives the ecosystem its first apples-to-apples server comparison, and it also fills the
gap that Nocturne's own repo has no tenant-count scaling benchmark.

### 8.4 Method notes

- **Sweep N**: 1, 10, 50, 100, 250, 500, 1 000, 2 500 tenants; stop each arm at its first
  gate failure and record where and why. The failure mode is the finding.
- **Fix the workload, vary one thing**: no arm may change two axes at once.
- **Warm-up + steady state**: ≥30 min steady state after warm-up; report distributions,
  not means; report the noisy-neighbour scenario separately.
- **Correctness gate before performance**: an arm that leaks data or drops an alarm is
  disqualified regardless of throughput. Cross-tenant isolation should be asserted by an
  automated test in the harness, modelled on
  `externals/nocturne/tests/Integration/Nocturne.Infrastructure.Data.Tests/Rls/RlsEnforcementTests.cs`.
- **Publish**: raw JSON results + a `docs/60-research/` report per arm, with the exact
  commit SHAs of every server under test, following existing workspace report conventions.
- **Pre-register the decision rule** before running (below), so the numbers decide.

### 8.5 Decision rule (proposed, to be argued now rather than later)

Adopt a multitenant direction only if the winning arm shows, at N ≥ 250 tenants:

1. **≥ 5× reduction** in $/tenant-month vs. EXP-MT-001; and
2. p99 entry→broadcast propagation **within 2×** of the control; and
3. **zero** cross-tenant leakage across the full correctness suite; and
4. cold/warm alarm latency **no worse** than the control; and
5. a credible operational story for backup, restore, per-tenant export and per-tenant
   deletion.

If no arm clears the bar, the finding is "keep the single-tenant deployment model and
spend the effort on the §7 amplifiers" — which would itself be a valuable, publishable
result.

---

## 9. Phasing (only if the numbers support it)

1. **Measure first.** Build `tools/mt-bench/`, run EXP-MT-001/002 and the §7 amplifier
   fixes. Cheap, independently useful, and non-invasive.
2. **Land the amplifier fixes upstream on their own merits** (Map-indexed merge/delta,
   fewer queries, clone reduction). They help every existing single-tenant site today.
3. **Introduce the query-model seam** (§5.2) as a refactor toward the *documented* API v3
   query model, validated by the existing test suites. Independently justifiable.
4. **Tenant-scope the request path**: resolution middleware, socket rooms, socket
   auth binding, per-tenant settings — behind a flag that defaults to single-tenant.
5. **Tenant-scope the data path**: `ctxFor(tenantId)`, per-tenant cache/loader/plugins,
   fail-closed storage isolation.
6. **Residency tiering + cold alarm path**, if EXP-MT-003/010 support it.
7. **Native/columnar work last**, only where EXP-MT-020/021 show a real win, and preferably
   by sharing Nocturne's stateless Rust cores rather than writing new ones.

---

## 10. Relationship to the parallel tooling evaluation

A companion evaluation produced alongside the modernization work —
`docs/reports/nightscout-release-planning-2026-09/tooling-evaluation-keyv-mongoose-zod-wasm.md`
— reaches compatible conclusions from the *single-tenant* side, and the two should be read
together. Agreements and one correction:

| Point | Tooling evaluation | This document |
|---|---|---|
| mongoose | Do not adopt; reaffirms prior rejection | Agree — an ODM deepens Mongo coupling, opposite of the needed seam |
| zod | Adopt only inside the broader schema-vocabulary item; API3 `validate.js` is hand-rolled and drifts from `specs/openapi/` | Agree; add that validation cost becomes a *hot path* at N tenants (EXP-MT-013), favouring compiled validators generated from the specs |
| keyv | Low-priority, behaviour-preserving swap inside `lib/api3/storage/mongoCachedCollection/` so a future Redis move is config-only | Agree, and multitenancy is the concrete motivation: keyv namespaces map onto tenant prefixes and shard-safe ephemeral state (EXP-MT-014). Still not a substitute for a query model (§5.1) |
| WASM | Reopen narrowly as a shared Rust oref core, without re-litigating ADR-005 | Agree; add that the first WASM benchmark must be against a *Map-optimised JS* baseline (EXP-MT-020), and that the strongest case is memory representation (EXP-MT-021) |

`docs/90-decisions/adr-005-adapter-protocol.md` rejected WASM as the common runtime for the
oref cross-validation harness. Nothing here reverses that: the proposal is Rust/WASM as an
*additional* shared implementation, not as the harness runtime.

**One correction to record**: the claim that Nocturne's `src/Core/oref/` is Rust with a
`wasm-bindgen` feature does not match this checkout. `src/Core/Nocturne.Core.Oref/` is C#
and P/Invokes a native `oref` Rust library (`OrefInterop.cs:1-40`, `LibraryName = "oref"`),
whose crate is **not vendored here** — `externals/nocturne/crates/` contains only
`nocturne-alerts-core` and `nocturne-alerts-ffi`, and neither `Cargo.toml` declares a wasm
feature. So the verified ecosystem precedent is *Rust behind a stateless C ABI*, and the
WASM target should be treated as unconfirmed until the oref crate is located and inspected.
That is a cheap follow-up and it materially affects the D4 option in §3.1.

---

## 11. Open questions for the maintainers

1. Is the target "many people on one operator's instance" (hosted service, needs billing,
   support, liability, and an explicit trust/threat model) or "one family/clinic runs a few
   sites cheaply"? These lead to different architectures, and the second is far easier.
2. What is the **isolation contract** we are willing to promise, and who is the adversary —
   another tenant, the operator, or a bug? Nocturne's RLS answer is "the storage engine
   refuses", which is the strongest available and should probably be the floor.
3. Host-based routing (Nocturne-compatible) vs path-prefix? Host preserves every existing
   uploader/follower config; paths are cheaper to host without wildcard TLS.
4. Do we accept a **hard dependency** on Nocturne (D3) or align on shared contracts and
   shared algorithm cores (D2 + D4)?
5. Who owns per-tenant **safety** — alarm delivery for idle tenants is the requirement most
   likely to be dropped by a cost-optimising design, and it is the one that hurts people.
6. Is data portability (per-tenant export/delete as a first-class operation) a requirement?
   If yes, it strongly favours file/DB-per-tenant isolation and is a
   `docs/DIGITAL-RIGHTS.md` matter, not only an engineering one.
7. Sequencing against the modernization gate: this work should stay measurement-only until
   #8605 is resolved, to avoid a second moving baseline.

---

## 12. References

**Nightscout** (`externals/cgm-remote-monitor-official`, `dev` @ `a8888f0d`):
`lib/data/ddata.js`, `lib/data/dataloader.js`, `lib/data/calcdelta.js`,
`lib/server/cache.js`, `lib/server/websocket.js`, `lib/server/bootevent.js`,
`lib/server/env.js`, `lib/settings.js`, `lib/sandbox.js`, `lib/storage/mongo-storage.js`,
`lib/server/query.js`, `lib/api3/`, `lib/plugins/`, `lib/bus.js`.

**Nocturne** (`externals/nocturne`): `src/API/Nocturne.API/Multitenancy/TenantResolutionMiddleware.cs`,
`src/API/Nocturne.API/Hubs/TenantAwareHub.cs`,
`src/API/Nocturne.API/Services/Realtime/{RealtimeGroups.cs,SignalRBroadcastService.cs}`,
`src/API/Nocturne.API/Services/Entries/EntryCacheAdapter.cs`,
`src/Infrastructure/Nocturne.Infrastructure.Data/{NocturneDbContext.cs,Interceptors/TenantConnectionInterceptor.cs,Migrations/20260227034745_EnforceMultitenancy.cs}`,
`crates/nocturne-alerts-core/`, `crates/nocturne-alerts-ffi/`, `tests/Performance/`,
`tests/Integration/**/Rls/`, `CLAUDE.md`.

**Workspace**: `docs/60-research/nightscout-modernization-next-steps-2026-09-09.md`,
`docs/reports/nightscout-release-planning-2026-09/tooling-evaluation-keyv-mongoose-zod-wasm.md`,
`docs/90-decisions/adr-005-adapter-protocol.md`,
`docs/sdqctl-proposals/nocturne-modernization-analysis.md`,
`docs/60-research/mongodb-modernization-impact-assessment.md`,
`specs/openapi/aid-*-2025.yaml`, `conformance/`, `docs/DIGITAL-RIGHTS.md`,
`externals/ns-data*`, `externals/ns-parquet*`.
