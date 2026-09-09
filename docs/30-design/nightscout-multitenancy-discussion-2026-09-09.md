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
should be treated as a hypothesis to be measured (§10, EXP-MT-001), not a number to quote.
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
*correctness* of an approach, not *capacity*. Capacity is what §10 is for.

> **Correction — Nocturne's Rust footprint is small, optional, and off by default.**
> A prior draft's phrasing ("Rust `nocturne-alerts-core`...") reads as if the alert path
> *is* Rust. Verified counts: `crates/nocturne-alerts-core` + `crates/nocturne-alerts-ffi`
> total **6 618 lines of Rust**, against **89 430 lines of C#** in `src/` — Rust is ~7% of
> the codebase, confined to one bounded, swappable boundary. More importantly, the engine
> selector defaults to the **managed C# evaluator**; Rust only runs at all in `shadow` mode
> (side-effect-free, comparing against managed) or explicit `rust` mode
> (`src/API/Nocturne.API/Services/Alerts/Engines/AlertEngineSelector.cs:6-9,28-69`,
> `ServiceRegistrationExtensions.cs:976-982`). **Nocturne's production default ships zero
> Rust in the request path.** Do not index the "should we rewrite in Rust" question on
> Nocturne's example — Nocturne itself doesn't run that way by default. Its actual
> multitenancy lever is the shared-process + RLS-shared-Postgres combination (this table),
> which is a *representation and isolation-primitive* choice, not a language choice — and
> §8.9 shows that lever reproduces in plain Node at 5 MB/tenant.

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
  path. This is a genuine architecture change, not a refactor. The wake cost itself now
  looks affordable — ~3–4 ms from a local store, or near-zero from a columnar hot cache
  (§7.1, §7.4) — so the hard part is eviction policy and cold alarms, not latency.
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
| **SQLite file per tenant** (`better-sqlite3` or `node:sqlite`) | Filesystem | Isolation is a *file*; backup = copy; delete = unlink; near-zero idle cost; per-tenant snapshot/restore/export makes data portability trivial. Measured: 1 000 open handles cost 66 MB RSS, cold open p99 0.06 ms (§7.1) | Replication/HA story; cloud filesystems; WAL write contention under heavy multi-writer load |
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

### 5.2.1 Postgres RLS, demonstrated against a live database (not just described)

The claim in §3 was that Nocturne's RLS is "fail closed at the storage layer." Rather than
take that on faith, the same primitive was reimplemented against a real Postgres 16
container with `knex` (`/tmp/rls-poc/` — a throwaway PoC, not committed, reproducible from
the SQL and script below), because Node's ecosystem tool for this is knex/Kysely/Prisma,
not EF Core, and the actual runnable mechanics matter more than the language they were
proven in first.

**Schema** (mirrors `externals/nocturne/.../Migrations/20260227034745_EnforceMultitenancy.cs:66-76`):

```sql
CREATE TABLE entries (
  id bigserial PRIMARY KEY, tenant_id uuid NOT NULL, sgv integer NOT NULL, date timestamptz NOT NULL DEFAULT now()
);
-- The application connects as this role: not the owner, no BYPASSRLS. Table owners and
-- BYPASSRLS roles see every row regardless of policy — this is the easiest way to
-- accidentally make RLS a no-op, and it is exactly what "FORCE" (next line) prevents
-- even for the owner.
CREATE ROLE app_user LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
GRANT SELECT, INSERT, UPDATE, DELETE ON entries TO app_user;
ALTER TABLE entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE entries FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON entries
  USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
-- second arg `true` = missing GUC returns NULL rather than raising; NULL = anything is
-- NULL in SQL (never true) → an unbound connection sees zero rows, not an error and not
-- everything. That NULL-comparison behaviour, not the policy syntax, is the actual
-- fail-closed mechanism, and it is worth stating explicitly because it is easy to get
-- backwards (a naive `current_setting(...)::uuid` with no second arg would instead
-- *throw* on an unbound connection — fail-closed in a different, noisier way).
```

**Per-request binding**, the Node equivalent of `TenantConnectionInterceptor.cs`:

```js
async function withTenant(tenantId, fn) {
  const trx = await knex.transaction();
  try {
    await trx.raw('select set_config(?, ?, true)', ['app.current_tenant_id', tenantId]);
    return await fn(trx); // is_local=true: scoped to this transaction, safe under pooling
  } finally { await trx.commit(); }
}
```

**Results, against a live container, 300 000 rows across 500 tenants (600 rows/tenant, matching
`gen.js`'s treatment count):**

| Scenario | Rows returned | p50 |
|---|---|---|
| No tenant context bound at all | **0** (not an error, not all rows) | 0.19 ms |
| Tenant-scoped query, **with no `tenant_id` predicate in the SQL at all** | only that tenant's 600 | 0.95 ms |
| Same "forgot the filter" query, plain table + explicit `WHERE tenant_id=` (no RLS) | correct 600, but only because the developer remembered | 0.63 ms |
| Same table, query with **no filter at all** (the actual bug, simulated) | **all 300 000 rows leaked** | 16.9 ms |
| Simulated Mongo-shaped app-layer-only filter, same forgotten-filter bug | **all 3 rows across tenants leaked** | — |

Two results matter more than the numbers:

1. **The forgotten-filter query against the RLS table returns the correct 600 rows with
   zero tenant predicate written in the SQL.** This is the actual value proposition: RLS
   converts "every query must remember to filter" into "every *connection* must remember
   to bind," which is one call site (middleware) instead of every call site (every query
   in `lib/data/dataloader.js`, `lib/api3/generic/*`, every plugin). It is fail-closed in
   the specific sense that *forgetting* fails safe, not merely that malicious input is
   rejected.
2. **RLS's overhead is real but small: ~0.32 ms (0.95 vs 0.63 ms) at this scale**, and it
   buys the property in (1). At Nightscout's actual query rate (~14 ops per tenant load
   cycle, once per 1–5 s per tenant, §2.3) this is noise, not a capacity concern.
3. **This has no equivalent in MongoDB as Nightscout uses it today.** MongoDB (self-hosted
   or Atlas, without Queryable Encryption/Data Federation, which are different features
   for different problems) has no server-enforced per-document ACL comparable to RLS.
   `ctx.store.collection(env.entries_collection)` (`lib/server/entries.js:203-205`) hands
   back a raw collection handle; isolation would be **whatever filter the 30-odd call
   sites across `lib/data/`, `lib/api3/generic/`, and every plugin remember to add** —
   exactly the failure mode column 4 of the table demonstrates. The honest options on
   Mongo are: (a) accept application-only isolation and invest heavily in a single
   enforced query-builder seam that *all* call sites must go through (closable, but a
   discipline problem, not a database property), (b) database-per-tenant (real isolation,
   no RLS needed, but N Mongo connections/index-sets — see the storage table above), or
   (c) migrate the tenant-scoped tables to Postgres and keep the rest on Mongo (a
   two-database architecture, real but non-trivial complexity).

### 5.2.2 Migrating off MongoDB without a flag day

The obvious objection to (c) above is "how would that actually work" — a full relational
redesign of a schema this heterogeneous sounds like a multi-quarter rewrite. Checked
directly against the source rather than assumed:

**The documents are far less regular than they look, and that argues *for* JSONB, not
against Postgres.** `specs/openapi/aid-treatments-2025.yaml:130-132` requires only
`eventType` and `created_at` — every other field is optional and varies by one of **28** enumerated
`eventType` values (`aid-treatments-2025.yaml:77-111`, counted directly from the `enum:`
list, spanning insulin/carb/basal/device/AAPS-specific/legacy categories). A
`Temporary Override` has
`reason.minValue`/`maxValue`; a `Temp Basal` has `rate`/`duration`/`absolute`; an SMB needs
`type`, not `eventType`, to identify at all (`aid-treatments-2025.yaml:207,391-428`). A
straight relational redesign (one typed column per field, one table per eventType or a
giant nullable table) would fight this heterogeneity for no benefit — clinical event
shapes evolve per-controller (Loop vs AAPS vs Trio) faster than a migration could track.

**What's actually indexed today is a small, stable, and separately discoverable set.**
Grepping the three storage modules' own `api.indexedFields` declarations:

| Collection | Indexed fields today | Count |
|---|---|---|
| entries | `date, type, sgv, mbg, sysTime, dateString, identifier` + 2 compounds | 7 scalar |
| treatments | `created_at, eventType, insulin, carbs, glucose, enteredBy, boluscalc.foods._id, notes, NSCLIENT_ID, percent, absolute, duration, identifier` + 2 compounds | 13 scalar |
| devicestatus | `created_at, NSCLIENT_ID` + 1 compound | 2 scalar |

(`lib/server/entries.js:217-227`, `lib/server/treatments.js:417-432`,
`lib/server/devicestatus.js:161-169`). Everything Mongo indexes *today* is already a short,
named list — the schema work in §5.3 doesn't need to invent a taxonomy, it needs to
formalize one that already exists as `indexedFields` arrays.

**Proposed migration shape — JSONB-first, generated columns for the hot set, nothing
else typed yet:**

```sql
CREATE TABLE treatments (
  id            bigserial PRIMARY KEY,
  tenant_id     uuid NOT NULL,
  doc           jsonb NOT NULL,                                   -- the whole document, as-is
  eventType     text GENERATED ALWAYS AS (doc->>'eventType') STORED,
  created_at    timestamptz GENERATED ALWAYS AS ((doc->>'created_at')::timestamptz) STORED,
  duration      numeric GENERATED ALWAYS AS ((doc->>'duration')::numeric) STORED,
  identifier    text GENERATED ALWAYS AS (doc->>'identifier') STORED
  -- ...remaining ~9 fields from the table above, same pattern
);
CREATE INDEX ON treatments (tenant_id, eventType, duration, created_at); -- mirrors the compound above
ALTER TABLE treatments ENABLE ROW LEVEL SECURITY;
ALTER TABLE treatments FORCE ROW LEVEL SECURITY;         -- §5.2.1's demonstrated primitive
CREATE POLICY tenant_isolation ON treatments USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
```

This is a **direct, mechanical translation of the existing `indexedFields` list**, not a
new schema design — every generated column already has a one-line justification in
today's Mongo index declaration. The 33 other possible treatment fields stay in `doc`,
queryable via `doc->>'field'` when needed (rare, uncommon-eventType queries), indexed via
GIN on `doc` if a specific plugin needs it. **Full normalization is deferred indefinitely,
by design** — the query-model seam (§5.2) means call sites speak the API v3 query model,
and the query-model layer is what translates `{find:{sgv:{$gte:120}}}`-shaped filters into
either a Mongo query or a generated-column/JSONB Postgres query, so most call sites never
notice which store answered.

**Migration mechanism — the workspace already has the pattern.** Because multitenancy is
being introduced at the same time, the storage migration and the tenancy migration are
the *same* migration, done incrementally, one tenant at a time — a strangler fig, not a
flag day:

1. New tenants (and any site owner who opts in) are created directly on Postgres/RLS.
2. Existing single-tenant Mongo-backed sites keep running completely unchanged — there is
   no forced cutover date.
3. For a site that opts to migrate: a one-time backfill (`mongoexport`-shaped bulk copy
   into the JSONB tables above) followed by a bounded dual-write window (both stores
   accept writes, a background job diffs them) before cutting reads over.
4. Because isolation is per-tenant (§5.2.1), a bug in the migration tooling for one tenant
   cannot corrupt another tenant's data on either side — the RLS boundary is also a
   migration blast-radius boundary.

**Correction — the CDC piece is not "already prototyped," it's unvalidated generated
config.** An earlier pass through this document overstated `~/src/node-multienv`'s Kafka
CDC work as directly reusable. Direct inspection corrects that:

- `cmd/webhook/handlers/resources.js:717-860` (`renderKafkaTopics`,
  `renderKafkaConnector`) does contain real, specific config — a `KafkaConnector` CRD
  wired to `com.mongodb.kafka.connect.MongoSourceConnector`, with a per-tenant topic map
  (`ns.<coll>` → `ns.<tenantId>.<coll>`), a DLQ topic, and `errors.tolerance: all`. This is
  genuine, non-trivial Mongo-change-stream-to-Kafka wiring, not vaporware.
- But it is **manifest-generation code only** — it emits the Kubernetes object a
  Metacontroller decorator would create, and there is no test file exercising it
  (no `*resources*test*` in the tree). node-multienv's own `STATUS.md` lists "Strimzi
  Kafka + KafkaConnect (for CDC)" as an **unchecked** prerequisite (line 136) and "Validate
  CDC: End-to-end Kafka connector testing" as a **pending** next step (line 217) — i.e. by
  the project's own accounting, this has never been run against a live cluster with real
  data flowing through it.
- More importantly for reuse: it only generates the *source* side (Mongo → Kafka topic).
  There is no sink connector anywhere in that codebase writing Kafka topics into Postgres
  — that half (JDBC sink connector config, or a custom consumer that upserts into the
  JSONB+generated-column tables above) does not exist and would need to be built and
  tested from scratch.

**Revised claim:** the *shape* (per-tenant CDC topic, DLQ, tolerant error handling) is a
reasonable one to borrow, and the source-side `MongoSourceConnector` config in
`resources.js` is a legitimate starting point to adapt rather than write blind. But
"reusable" should read as "a design sketch and one unvalidated half of the pipeline,"
not "an existing working mechanism." The bounded dual-write job in step 3 above (bulk
backfill + diff + cutover) does **not** require Kafka/Strimzi at all — it can be built as
a plain change-stream-tailing Node script reading Mongo's own oplog-backed change streams
and writing into Postgres directly, which is less infrastructure and more directly
testable than standing up Strimzi + Kafka Connect for a one-time-per-tenant migration.
Kafka/CDC only earns its keep if dual-write needs to run continuously at scale across many
concurrent migrating tenants; for a bounded, per-tenant, one-time migration, it is very
likely over-engineering and the plain change-stream script should be the default until
proven otherwise.

This bounds the actual engineering unknown to something measurable rather than "migrate
Mongo to Postgres" as a monolithic fear: port ~3 collections' `indexedFields` lists
(22 scalar fields total, per the table above) to generated columns, and build (not reuse)
a per-tenant backfill+dual-write+cutover script, most simply as a direct Mongo
change-stream consumer rather than a Kafka/Strimzi deployment. EXP-MT-037 (§10) is a
time-boxed spike to put a real number on this rather than an estimate, and should include
building and timing the plain change-stream-tailing approach before considering Kafka.

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

**Directly on "should Nightscout adopt mongoose":** no, independent of multitenancy.
Mongoose is a Mongo-specific ODM; adopting it would deepen the MongoDB coupling the
storage-abstraction seam (§5.2) is trying to loosen, and it does nothing that a compiled
Ajv/zod validator generated from `specs/openapi/` doesn't already do better — it validates
documents, not tenant boundaries, and (§5.2.1) tenant boundaries are the actual hard
problem. If the project migrates any collection to Postgres, the equivalent tool is
`knex` (query builder, used in §5.2.1) or `Kysely`/`Prisma` (typed query builder/ORM with
migration tooling) — not mongoose, which doesn't apply to a relational store at all.

### 5.4 Answering directly: is Postgres+RLS+knex better than Nocturne, better than Rust, or neither?

Restated precisely, because "better" needs an axis: **on the specific axis of per-tenant
capacity and cost**, measured here, adopting **RLS as an isolation primitive inside
cgm-remote-monitor** (via knex or an equivalent query builder, keeping Node) dominates
both alternatives the user named — but "dominates" needs three separate comparisons, not
one verdict, because each alternative fails on a different axis:

| vs. | What it would cost | What it would buy over Postgres+RLS+knex-in-Node | Verdict |
|---|---|---|---|
| **Migrating to Nocturne (D3, §3.1)** | Adopt .NET+EF Core+Postgres as the whole stack; lose the JS plugin/connector ecosystem; hard dependency on another project's roadmap | Nothing measured here — its Rust is optional and off by default (§3 correction), and nothing shown suggests EF Core+RLS beats knex+RLS at this workload | **Postgres+RLS+knex-in-Node is better**: same isolation primitive, none of the migration cost, keeps community-maintainable JS |
| **A Rust (or other native) rewrite of the host** | Full rewrite; lose the plugin ecosystem; §8.1/§8.2 show it *loses* to V8 on the untyped document shape Nightscout uses today, and its only unambiguous win (§8.2, 41 MB/process) is exactly what §8.9's `shared` architecture already reclaims in Node | A stateless typed core for the genuinely CPU-bound spots (§6.1, §8.5) — narrow and separable, not a host swap | **Non-inferior to strictly better**: Postgres+RLS+knex solves *isolation*; a native core (if ever justified) solves a *different, CPU-bound* problem and can sit behind either storage choice. They are not substitutes for each other, so "better" doesn't fully apply — but nothing here argues for swapping the host to get RLS-equivalent isolation |
| **Staying on MongoDB with only an application-enforced filter** | Cheapest short-term; zero migration | Nothing — §5.2.1's leak demonstration shows this fails exactly the bug class RLS exists to catch, and is the current de facto state | Postgres+RLS+knex is **strictly better** on the isolation axis; the honest cost is the migration itself (§5.2 table), which is the real thing to weigh, not whether RLS is a good idea |

**So, plainly**: mongoose is not being proposed (§5.3) and would not help isolation if it
were. The comparison that matters is Postgres+RLS+knex (or an equivalent enforced
predicate on whichever store is kept) versus (a) Nocturne's *runtime*, which loses on
migration cost for no measured capacity gain, and (b) a native rewrite, which solves a
different problem than isolation and is not shown to win on the representation Nightscout
actually uses (§8.1). The open cost that this document has **not** measured and should
before recommending a migration is the one-time cost of moving Nightscout's ~14 queries
per load cycle (§2.3) and every plugin's ad hoc Mongo filter onto a relational schema —
that is a real, possibly large, engineering cost, and is tracked as EXP-MT-011
(storage-backend comparison) and a to-be-added EXP-MT-037 (migration LOC/time estimate
from a spike on 2–3 representative collections).

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

Two adjacent WASM proposals are measured and answered in §7 and should not be conflated
with the four above: **SQLite compiled to WASM is 2.5–7× slower than native on the server**
(§7.2), and **hosting Nightscout's JS inside a WASM runtime** optimises instantiation cost
that Nightscout does not have, while taxing the JS hot path it does (§7.3).

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

**Recommendation**: treat eBPF as first-class *measurement* infrastructure for §10 and
explicitly out of scope as an application dependency. If the benchmark harness produces
per-tenant flamegraphs and off-CPU profiles, the architecture debate becomes short.

---

## 7. Cold-tenant wake, hot cache and WASM: measured

This section answers a specific maintainer question — *could a WASM server/runtime wake a
cold tenant faster, make SQLite faster, or should we just keep a hot cache?* — with
measurements rather than intuition. Harness and raw scripts: `tools/mt-bench/`
(node v24.15.0, Linux, shared development machine; synthetic tenant = 576 SGVs +
600 treatments + 576 Loop-style devicestatus with 72-point prediction arrays,
i.e. one 48-hour window). **These are indicative single-machine numbers, not a
benchmark result** — they exist to rank hypotheses before building the full harness in §9.

### 7.1 How expensive is a cold wake, actually?

Rebuilding one tenant's runtime window from various sources
(`tools/mt-bench/coldwake.js`, `wasmvsnative.js`):

| Wake path | Time |
|---|---:|
| `JSON.parse` of an 795 KB snapshot (the "hot cache in Redis/keyv" path) | 2.47 ms |
| `v8.deserialize` of a 706 KB snapshot | 3.29 ms |
| `node:sqlite`, cold open + 3 range scans + `JSON.parse` rows | 3.96 ms |
| `node:sqlite`, warm handle + prepared statements + `JSON.parse` rows | 3.22 ms |
| `node:sqlite`, warm handle, **rows only, no `JSON.parse`** | 0.70 ms |
| `better-sqlite3`, warm handle + `JSON.parse` rows | 3.06 ms |
| `better-sqlite3`, warm handle, rows only | 0.53 ms |
| current `processRawDataForRuntime` clone (`JSON.parse(JSON.stringify(...))`) | 3.79 ms |
| `structuredClone` of live ddata | 4.18 ms |

**A cold wake from a local store is ~3–4 ms, and roughly 80 % of that is
`JSON.parse` materialising JavaScript objects** — not I/O, not query planning, not
code startup. Note also that `v8.deserialize` is *slower* than `JSON.parse` here, so the
obvious "snapshot the object graph" trick does not pay.

SQLite file-per-tenant scales fine at the handle level (`tools/mt-bench/handles.js`,
1 000 tenant databases, 207 MB total):

| Measure | Result |
|---|---:|
| cold open latency | p50 0.03 ms / p99 0.06 ms |
| first query after open | p50 0.30 ms / p99 0.69 ms |
| 1 000 handles held open simultaneously | no failure |
| RSS to hold 1 000 open handles | 66.1 MB (≈ 67.7 KB per open tenant) |

So the EXP-MT-012 worry about file handles and cold-open cost looks unfounded at this
scale, which strengthens the SQLite-per-tenant option in §5.2 considerably.

### 7.2 Does SQLite-in-WASM help? No — it is strictly slower here

Same workload, same queries, native vs WASM build (`tools/mt-bench/wasmvsnative.js`,
`@sqlite.org/sqlite-wasm` 3.53.4):

| | + `JSON.parse` | rows only |
|---|---:|---:|
| `better-sqlite3` (native) | 3.06 ms | 0.53 ms |
| SQLite-WASM | 7.68 ms | 3.79 ms |
| **WASM penalty** | **2.5×** | **7.2×** |

This is the expected result once stated plainly: SQLite-WASM exists so that *browsers*,
which have no native SQLite, can have one (via OPFS). On a server that can call native
SQLite directly, compiling it to WASM only adds a sandbox boundary and linear-memory
bounds checks. **The "WASM makes SQLite faster" intuition inverts on the server side.**

### 7.3 Would a WASM runtime wake a tenant faster? Wrong term of the equation

The appeal of WASM runtimes (Wasmtime/WasmEdge/Spin) for multitenancy is real but
specific: near-instant *instance* creation, cheap per-tenant sandboxes, and snapshot
pre-initialisation (Wizer) giving microsecond cold starts. That is a decisive advantage
when your cold start is dominated by **process/runtime startup** — the FaaS case.

Nightscout's cold start is not. §7.1 shows it is ~3–4 ms of **data materialisation**, and
in a real deployment the dominant term is the Mongo network round-trips (§2.3: ~14 queries
per load), which a WASM runtime does not touch at all. A WASM runtime would optimise a
term that is already close to zero.

Worse, the cost side is severe. Nightscout is JavaScript, so "run it in WASM" means
running JS *inside* a WASM-hosted engine — Javy/QuickJS or SpiderMonkey via
ComponentizeJS. That trades V8's tiered JIT for an interpreter or a boundary-crossing
engine; published comparisons commonly put QuickJS-in-WASM in the **5–20× slower**
range for steady-state JS. Nightscout's per-tenant CPU is exactly steady-state JS:
plugin chains (IOB/COB/AR2/loop/openaps), treatment processing, delta computation. Paying
a multiple on all of that to save microseconds of instantiation is a bad trade.

**Verdict**: a WASM *server runtime* hosting Nightscout's JS is not the answer, and should
be pre-registered as an expected-to-lose arm (EXP-MT-024) purely so the question is closed
with a number instead of being re-raised. WASM as a *library* boundary for shared Rust
compute (§6.1, and Nocturne's stateless crates) remains open and interesting; those are
different proposals that happen to share a word.

### 7.4 The hot cache instinct is right — but the format matters more than the store

The third suggestion is the strongest, with one refinement: **what the hot cache holds
matters far more than where it lives.** Comparing representations of the 48-hour SGV
window (`tools/mt-bench/columnar.js`, measuring `heapUsed + external`, 200 tenants):

| Representation | Memory | Wake time |
|---|---:|---:|
| JS objects (`JSON.parse`) | 202.5 KB/tenant | 0.559 ms |
| Columnar typed arrays (f64 mills, i32 sgv, f32 delta, u8 direction) | 9.9 KB/tenant | 0.001 ms |
| **Ratio** | **≈ 20×** | **≈ 500×** |

A hot cache holding *JSON* costs ~2.5 ms and a full object graph per wake. A hot cache
holding *columnar blobs* costs effectively nothing to wake — mapping typed-array views
over bytes is pointer arithmetic — and 20× less memory. Buffer-backed storage is also
**external to the V8 heap**, so it does not add GC pressure, which matters more than raw
bytes once hundreds of tenants share one event loop.

Two honest limits:

1. **This win requires no WASM.** Typed arrays are plain JavaScript. WASM linear memory
   would only add value if the *compute* over those buffers also moved to Rust (shared
   with Nocturne), or to release a tenant's memory wholesale on eviction without GC
   negotiation. That is a §6.1 argument, not a runtime argument.
2. **Not everything columnarises.** SGVs, MBGs, calibrations and Loop's
   `devicestatus.loop.predicted.values` (72 floats each — a large share of devicestatus
   bytes) are ideal. Treatments are heterogeneous documents with optional fields and free
   text (`lib/data/ddata.js:249-337`) and will not compact nearly as well. Expect the
   blended win to be well below 20×; EXP-MT-025 should measure per collection.

### 7.5 Revised recommendation for the wake path

Ordered by evidence, cheapest first:

1. **Local store beats remote store.** Most of a realistic cold wake is Mongo network
   RTT, not compute. SQLite-per-tenant (or any co-located store) removes it, and §7.1
   shows handle/open costs are negligible at 1 000 tenants.
2. **Stop materialising objects you do not need.** The parse is ~80 % of local wake cost.
   Keep the hot window in a compact binary form and decode lazily, per field, on demand.
3. **Hot cache holding columnar blobs**, tiered hot/warm/cold per §4C. Wake ≈ free;
   full rebuild from the store (~3–4 ms) is the fallback, not the common path.
4. **keyv is the right abstraction for *where* that blob lives** (memory → SQLite → Redis
   as deployments grow, config-only change), which is exactly the §5.1 role — and note it
   is storing an opaque value, so keyv's lack of a query language is irrelevant here.
   This is the one place the keyv intuition lands cleanly.
5. **WASM only for shared Rust compute over those buffers**, if EXP-MT-020/021 justify it.
6. **Not** a WASM host runtime for Nightscout's JS; **not** SQLite-in-WASM on the server.

### 7.6 Additional pre-registered arms

| ID | Arm | Question |
|---|---|---|
| EXP-MT-023 | Snapshot format: JSON vs `v8.serialize` vs FlatBuffers/Arrow vs hand-rolled columnar | Wake time, bytes, and encode cost per update |
| EXP-MT-024 | Nightscout JS under a WASM host (Javy/QuickJS, ComponentizeJS) vs Node/V8 | Close the question with a number; expected to lose on steady-state CPU |
| EXP-MT-025 | Columnar coverage per collection (entries vs devicestatus vs treatments) | Where the 20× holds and where it collapses |
| EXP-MT-026 | Cold wake with a real remote Mongo/Atlas in the loop | Confirm network RTT dominates local compute |

---

## 8. Is Node the right host at all? Measured

§7 asked whether WASM makes Nightscout's *existing* runtime faster. This section asks the
prior question: **should the server be JavaScript at all**, or would Rust, Grain, or a
WASM shell be structurally better? Harness: `tools/mt-bench/rust/` (rustc 1.68, serde_json,
release build) against the same fixtures as §7, same machine.

### 8.1 Parsing and memory, Node vs Rust, three representations

| Representation | Parse (SGV window) | Memory / tenant |
|---|---:|---:|
| Node — JS objects (`JSON.parse`) | 0.559 ms | 202.5 KB |
| Node — typed arrays (columnar) | 0.001 ms | 9.9 KB |
| Rust — `serde_json::Value` (untyped) | — | **1 552.3 KB** |
| Rust — typed structs (serde derive) | 0.26 ms | 53.7 KB |
| Rust — columnar struct-of-arrays | 0.25 ms | 10.2 KB |

Whole-tenant untyped parse: **Node `JSON.parse` 2.47 ms vs Rust `serde_json::Value`
4.60–4.82 ms.**

Three results here are worth sitting with:

1. **Rust loses to V8 on untyped JSON**, by roughly 1.9× on time and 7.7× on memory.
   V8's `JSON.parse` is heavily optimised C++ with hidden-class object layout;
   `serde_json::Value` is a tree of enums and `String`s and `BTreeMap`s. Choosing Rust
   while keeping a schemaless document model makes things **worse**, not better.
2. **Columnar JS ties columnar Rust**: 9.9 KB vs 10.2 KB per tenant, within 3 %. Once the
   data is in typed arrays, JavaScript is holding the same bytes Rust would hold.
3. **The lever is the schema, not the language.** Rust only wins after you commit to a
   typed representation (1 552 → 53.7 → 10.2 KB). But that same commitment is available in
   JavaScript, and delivers the same endpoint. This connects directly to §5.3: adopting
   real schemas is what unlocks the performance, in *either* language.

### 8.2 Language choice buys a constant; representation buys a slope

| | Node | Rust |
|---|---:|---:|
| Baseline RSS, HTTP server, no data | 44.0 MB | 3.0 MB |

That 41 MB gap is a **fixed cost per process**, and how much it matters depends entirely
on the deployment model:

| Tenants per process | Runtime baseline amortised |
|---:|---:|
| 1 (today's model) | 41 MB per tenant — **dominant** |
| 100 | 0.41 MB per tenant |
| 1 000 | 0.04 MB per tenant — negligible |

This produces the sharpest strategic finding in this document:

> **Multitenancy and a runtime rewrite are substitutes, not complements.** The single
> largest per-tenant saving a Rust rewrite offers is eliminating a ~41 MB per-process
> runtime baseline — which is exactly the cost that multitenancy amortises to nothing.
> Doing both buys the second one almost nothing.

In today's one-process-per-person deployment, the Node baseline genuinely *is* a
per-tenant cost, and "rewrite it in something smaller" is a rational response to it. That
is likely the intuition behind the question. But if the goal is many tenants per process,
that argument dissolves, and what remains is the per-tenant *slope* — which §8.1 shows is
set by data representation, and is achievable without leaving Node.

### 8.3 The amplifiers are a fairness problem, not a throughput problem

Re-measuring the O(n²) hot spots against a Map-indexed rewrite
(`tools/mt-bench/amplifiers.js`) corrects an over-claim made in §10 of the first draft:

| Workload | Nested scan (current shape) | Map-indexed |
|---|---:|---:|
| `idMergePreferNew`, 600 old / 3 new (typical incremental) | 0.022 ms | 0.077 ms |
| treatment delta, 600 × 600 | 0.888 ms | 0.878 ms |
| treatment delta, **5 000 × 5 000** (heavy/long-history tenant) | **80.9 ms** | **2.7 ms** |

At typical sizes the nested scan is **already fine, and the "fix" is 3.5× slower** —
building an index costs more than scanning three new documents. The quadratic only bites
the tail: at 5 000 treatments it is a **30× difference and an 81 ms event-loop stall**.

In single-tenant Nightscout, an 81 ms hiccup is invisible. In a multitenant process it is
a **fairness incident**: one person with a long treatment history stalls everyone else's
broadcasts. So the correct framing is tail latency and isolation, not throughput — and the
right fix may be adaptive (scan when small, index when large) rather than unconditional.
This also means §10's amplifier list should be justified by p99 and fairness metrics, not by
expected tenants-per-process.

### 8.4 Candidate hosts, assessed

| Host | Real advantage | Real cost | Verdict |
|---|---|---|---|
| **Node/V8 (today)** | Best-in-class untyped JSON; the entire ecosystem Nightscout depends on (socket.io, mongodb driver, 38 plugins, connectors); largest contributor pool | 44 MB baseline; single-threaded fairness; no memory isolation between tenants | Default. The baseline stops mattering once amortised |
| **Rust** | 3 MB baseline; real threads; predictable memory; Nocturne already ships Rust cores | Full rewrite; loses the plugin/connector ecosystem; **loses to V8 unless the data is typed** | Justified for *libraries* (§6.1), not as the host |
| **Grain** | WASM-native, small, functional, pleasant type system | Ecosystem is tiny — no Mongo driver, no socket.io, no plugin community. Its production maturity could not be verified from authoritative sources here | Not viable as a Nightscout host; interesting for isolated pure computations at most |
| **Go** | Small baseline, real concurrency, good ops story, large ecosystem | Full rewrite; same ecosystem loss as Rust; GC still present | Plausible if a rewrite were happening anyway; no measured advantage over Rust here |
| **WASM component shell** (Wasmtime/Spin, WASI 0.3) | Genuine **per-tenant sandboxing and fairness**; cheap instantiation; host-managed shared event loop with `stream<T>`/`future<T>` now native to the canonical ABI (WASI 0.3 ratified by the WASI Subgroup, Bytecode Alliance) | Nightscout's JS would run in QuickJS/SpiderMonkey rather than V8 — the 5–20× steady-state tax from §7.3; ecosystem/driver gaps | Interesting as an **isolation** mechanism, not a speed one. Track WASI 0.3; do not adopt for throughput |

The honest summary: **no candidate host is faster than Node at what Nightscout actually
spends its time on**, once representation is held constant. What the alternatives offer is
*isolation* and *baseline footprint* — and multitenancy addresses the second while §4's
sharding addresses the first.

### 8.5 Split by tier, not by language

Nightscout is not one workload, and "which runtime" has a different answer per tier. This
also matches what Nocturne actually did — .NET for orchestration, Rust for the stateless
alert core (§3).

| Tier | Character | Right host |
|---|---|---|
| HTTP ingest / API v1–v3 | I/O bound, untyped JSON in/out | **Node** — V8's parser is the best tool, and the ecosystem is here |
| Storage / query | I/O bound | Node + native driver; the seam matters (§5.2), the language does not |
| Realtime fan-out | I/O bound, connection-heavy | **Node** — socket.io is an ecosystem asset, hard to replace |
| Per-tenant compute (IOB/COB/AR2/loop, alarms, delta) | CPU bound, stateless, schema-stable | **Native/WASM library boundary** — the Nocturne pattern; shareable across servers |
| Reports / analytics | Batch, columnar, long windows | Columnar store + native compute (cf. `externals/ns-parquet*`) |
| Browser | No native option exists | **WASM** — see §8.6 |

The boundary belongs where data is **already typed and compute is already stateless**.
That is precisely `nocturne-alerts-core`'s shape, and precisely *not* the shape of
Nightscout's request handling.

### 8.6 The browser is the opposite case — and the conclusions invert

Every §7 conclusion reverses in the browser, and conflating the two is the main way this
discussion goes wrong:

| Question | Server | Browser |
|---|---|---|
| SQLite in WASM? | **No** — 2.5–7× slower than native (§7.2) | **Yes** — WASM+OPFS is the *only* way to have SQLite at all |
| JS in a WASM engine? | **No** — loses V8's JIT (§7.3) | Irrelevant — the browser *is* V8/SpiderMonkey/JSC |
| Rust/WASM compute? | Only where already typed and stateless | **Yes** — the only route to native-speed compute, and the only way to share one oref/alarm implementation with the server |
| Columnar payloads? | Memory and wake win (§7.4) | **Bandwidth, parse-time and battery win** — decode into typed arrays feeding charts directly |

The browser case is where WASM is unambiguously correct, and it is also where the
modernization discussion is already heading (Svelte reports UI, Nocturne's Svelte
components). A shared Rust core compiled **native for the server and WASM for the browser**
gives one implementation, two targets, with parity testable in CI — which is a
*correctness* argument first and a performance argument second.

The unifying idea: **one columnar format used as wire format, storage format and compute
format.** The server keeps it in Buffers, ships it to the browser without re-serialising,
and the browser maps typed arrays over it straight into charts. That deletes several
JSON encode/decode round-trips that currently exist purely because the format changes at
every hop.

### 8.7 Lessons

1. **Fix the representation before changing the language.** Columnar JS (9.9 KB/tenant)
   beats typed Rust structs (53.7 KB) and ties columnar Rust (10.2 KB). Language changes
   nothing that representation has not already decided.
2. **Rust is not automatically faster.** On untyped JSON it lost to V8 by ~1.9× on time and
   ~7.7× on memory. "Rewrite in Rust" without a schema is a regression.
3. **Schemas are the performance unlock**, not just a correctness nicety — which makes the
   zod/OpenAPI work in §5.3 load-bearing for this whole effort rather than adjacent to it.
4. **Runtime baseline is a constant; multitenancy already eliminates it.** Don't pay for a
   rewrite to solve a problem that the architecture change deletes anyway.
5. **The quadratics are a tail/fairness problem**, invisible at typical sizes and a 30×
   cliff at heavy ones. Multitenancy converts a private hiccup into everyone's outage.
6. **Server and browser have opposite answers.** Native wins on the server; WASM wins in the
   browser; the shared artefact between them is a typed, stateless compute core plus a
   common columnar format.
7. **The strongest non-Node argument is isolation, not speed** — per-tenant sandboxing and
   fairness. That is worth tracking (WASI 0.3, component model) and worth solving more
   cheaply first with process sharding (§4E) and worker threads.

### 8.8 Additional pre-registered arms

| ID | Arm | Question |
|---|---|---|
| EXP-MT-027 | Node vs Rust vs Go: full tenant tick (load → plugins → delta → serialise) | Does the language gap survive a realistic mixed workload, or is it all representation? |
| EXP-MT-028 | Adaptive merge/delta (scan when small, index when large) | Best crossover point; p99 under a heavy tenant |
| EXP-MT-029 | Worker threads + `SharedArrayBuffer` over columnar buffers | Can fairness be bought without leaving Node? |
| EXP-MT-031 | One columnar format server→wire→browser vs today's JSON hops | End-to-end bytes, parse time, battery on mobile followers |

### 8.9 Deployment models: where the cost of "one Nightscout per person" actually is

This section answers the operator-facing question directly: hosters (T1Pal, NSPro, and
this workspace's own `node-multienv` prototype) run **one Node process — and usually one
database — per tenant**, orchestrated by Kubernetes, and the claim is that this "pushes
the limits of Kubernetes... for large cohorts". Measured, in three parts: what a pod
actually costs at rest, what three Node architectures cost per tenant, and what actually
runs out first in the k8s control plane.

**Prior art in this workspace.** `/home/bewest/src/node-multienv` is exactly this
architecture, evolved over four generations: a REST-managed process supervisor
(`master.js`, one `node server.js` per `.env` file), then a Consul-backed dispatcher, then
a Kubernetes deployment-per-tenant controller, then (2025-10) a Metacontroller
CompositeController that declares **11–12 child resources per tenant** — MongoDB
StatefulSet + Service + Secret, Nightscout Deployment + Service, Kafka Topic + Connector,
PVCs, PodDisruptionBudgets — because "managing resources would need to handle an
arbitrarily large number of resources per tenant, not just a single Deployment"
(`COMPONENT-SEPARATION-SUMMARY.md:127-135`). Its operator-chosen defaults:
Nightscout request/limit `128Mi`/`256Mi`, MongoDB `256Mi`/`512Mi`
(`cmd/webhook/handlers/resources.js:1351-1362`) — i.e. **≥384 MiB requested per tenant**
before the process has loaded a single document. That number is the one worth checking
against reality.

**1. What does a bare Nightscout pod cost before any tenant data?**
Measured by requiring layers of the actual `-official` server one at a time in a fresh
process (`tools/mt-bench/footprint.js`):

| Layer added | RSS (MB) | PSS (MB) | Δ RSS |
|---|---|---|---|
| bare Node | 45.6 | 10.0 | — |
| + express | 63.7 | 19.9 | +18.1 |
| + socket.io | 66.6 | 21.7 | +2.9 |
| + mongodb driver | 78.0 | 32.1 | +11.4 |
| + Nightscout server modules (`env`, `plugins`, `sandbox`, `ddata`, `dataloader`,
  `client`, `websocket`, `api3`, `language`) | **98.9** | **52.0** | +20.9 |

That is **~99 MB RSS before one tenant's data is loaded** — against the §2.7 anchor of
**~1.2 MB for that tenant's actual `ddata`**. In the pod-per-tenant model, code and runtime
outweigh data roughly **80:1**. The `node-multienv` request of 128Mi is *below* this
measured RSS floor already (it relies on Linux overcommit and the limit, not the request,
being the operative ceiling) — a concrete, checkable discrepancy worth flagging to that
project independently of this document.

**2. Three ways to hold N tenants in Node — measured, not assumed**
(`tools/mt-bench/arch.js`; each tenant loads the identical `gen.js` fixture, so the only
variable is the architecture):

| Architecture | What it is | RSS/tenant | PSS/tenant | at 16 tenants w/ full NS require graph |
|---|---|---|---|---|
| **process** (today's model) | fork per tenant, one k8s pod each | 54.8 MB (32 tenants) | 12.4 MB | 101.9 MB RSS / 53.7 MB PSS |
| **worker** (`worker_threads`, one per tenant) | threads inside one process | 15.0 MB | 13.0 MB | 56.8 MB / 54.4 MB |
| **shared** (`Map<tenantId, ctx>`, one process) | the `ctxFor(tenantId)` proposal, §4B | 2.2 MB | 2.3 MB | 5.4 MB / 5.1 MB |

Three findings that should update the intuition:

1. **RSS and PSS diverge hugely for `process`, and barely for the others.** The kernel
   deduplicates the Node binary's text segment and shared libraries (libc, OpenSSL) across
   forked processes, so the *physical* memory cost of process-per-tenant (12–54 MB/tenant)
   is much less alarming than the *provisioned* cost (55–102 MB/tenant) that a Kubernetes
   `resources.requests` field has to declare. **The real waste is in what Kubernetes must
   book, not in what the kernel actually pays** — which is an argument for bin-packing
   (higher pod density, lower per-pod requests) before it is an argument for rewriting.
2. **Worker threads are not the free lunch they look like.** At the same 16-tenant,
   full-require-graph scale, `worker` (56.8 MB/tenant) is statistically indistinguishable
   from `process` (101.9 MB provisioned / 53.7 MB physical) — each V8 isolate re-compiles
   and re-holds its own copy of every required module. Threads only look cheap when you
   don't load real application code into them (bare fixture-only case: 15.0 MB vs 54.8 MB).
   **Isolate count, not OS process count, is the cost driver.**
3. **`shared` wins by 10–20× on both metrics**, and it is the same number the columnar
   work (§7.4) and Nocturne's bounded-cache design (§3) both point at independently: one
   process, one V8 isolate, one copy of the require graph, tenants as data. This is
   Architecture B in §4, and it is now measured, not just proposed.

**3. Cold start — does it matter for scale-to-zero?**
Spawn + require, no DB I/O yet, p50/p95 over 8 runs:

| Layer | p50 | p95 |
|---|---|---|
| bare Node | 22 ms | 23 ms |
| + mongodb driver | 129 ms | 354 ms |
| + full Nightscout server require graph | 266 ms | 503 ms |

A quarter-second p50 (half a second p95) to *start the process*, before any Mongo
round-trip, is the actual argument against per-tenant scale-to-zero (Knative/KEDA-style):
it is not disqualifying for a background sync, but it is a bad user experience for
"someone opens the app and the alarm engine has to cold-boot first". The `shared`
architecture doesn't have a cold-start problem for existing tenants at all — only the
process does, and only because it re-pays the require graph every time.

**4. What actually limits Kubernetes at "a few score" → "a thousand" tenants**
Not raw node memory first — the `node-multienv` history shows the tipping point was
**object count and control-plane reconcile load**: 11–12 Kubernetes objects per tenant
means 1 000 tenants is 11 000–12 000 objects, each independently watched, reconciled, and
diffed by Metacontroller/kube-controller-manager and stored in etcd. That is a real,
well-documented Kubernetes scaling axis (etcd request rate and watch fan-out, not disk
space), and it is **orthogonal to the runtime language** — a Rust or Go rewrite of
Nightscout would still need 11–12 objects per tenant under this deployment model, because
the object count comes from the *database-per-tenant* and *CDC-per-tenant* choices, not
from Node. Shrinking the object count (shared MongoDB with per-tenant collections/RLS-style
filters, shared Kafka topic with a tenant-keyed payload, one Nightscout Deployment scaled
horizontally instead of one-per-tenant) removes the k8s ceiling regardless of language,
and is a strict prerequisite for any of the "radically more tenants" options in this doc.

**So: Nocturne, extend cgm-remote-monitor, or new runtime?** The measurements point at a
specific, narrower answer than any of the three framed wholesale:

- **Don't adopt Nocturne's *runtime*.** Its Rust is small, optional, and off by default
  (see the correction in §3); its .NET+RLS combination is not shown here to beat a
  well-built shared-process Node server, and D3 (Nocturne as data plane) makes hosting
  *harder* for small operators, not cheaper.
- **Do adopt Nocturne's *isolation primitive*.** Fail-closed Postgres RLS (or an
  equivalent enforced-at-storage filter for whichever database Nightscout keeps) is a
  database property, not a .NET property — it is directly portable to Node+`pg` and is
  the actual lesson worth taking, independent of language.
- **Extend cgm-remote-monitor with the `shared` architecture (§4B).** It is the measured
  winner at 10–20× the density of both alternatives tested, requires no new language or
  toolchain, and directly attacks the two real ceilings found here: per-pod require-graph
  overhead (§8.9.1) and per-tenant Kubernetes object count (§8.9.4). A runtime rewrite
  would have to *also* solve those two problems to be worth its migration cost, and
  nothing measured here shows Rust/Go doing so for free.
- **A new runtime is worth revisiting only if** profiling of the *shared* architecture
  under real load surfaces a genuinely CPU-bound hot path (not a memory or footprint one —
  those are solved by sharing) — at which point §6/§8.4's answer (a typed, stateless
  native/WASM core called from Node, not a rewrite of the host) still applies.

EXP-MT-032/033/034 (footprint, architecture, cold start) are added to §10 below; the
highest-value next one is **EXP-MT-035: repeat `arch.js`'s `shared` mode against a real
tenant-count target (300, 1 000) with the real `ddata`/`dataloader` code path**, not the
synthetic fixture, to confirm the 5 MB/tenant figure survives contact with actual query
and cache logic.

---

## 9. Runtime performance model to test

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

| Amplifier | Evidence | Cheap fix to test first | Measured (§7–§8) |
|---|---|---|---|
| JSON deep clone per load | `lib/data/ddata.js:29-79` | clone-free normalisation | clone 3.79 ms; `structuredClone` is **worse** at 4.18 ms |
| O(old×new) merge | `lib/data/ddata.js:82-106` | Map-indexed merge by `_id`/`identifier` | index is **slower** at typical size; only wins in the tail (§8.3) |
| O(old×new) treatment delta | `lib/data/calcdelta.js:15-76` | Map-indexed diff | 0.89 ms @600 (no gain) vs 80.9→2.7 ms @5 000 (**30×**) |
| 14 queries per load regardless of window | `lib/data/dataloader.js:128-146`, `:385-393` | Combine the six special-treatment queries; skip loaders whose window is empty | not yet measured; expected to dominate once a real remote DB is in the loop (EXP-MT-026) |
| Repeated filter/sort of full treatment array | `lib/data/ddata.js:249-337` | Single pass bucketing | not yet measured |
| Per-object heap overhead | §2.7 | Compact/columnar representation | **202.5 → 9.9 KB/tenant (≈20×)**, wake ≈500× faster (§7.4) |

**Correction to the first draft.** This section originally claimed these six fixes would
"move the tenants-per-process number more than any storage or WASM change". The
measurements only partly support that, and the distinction matters:

- **Representation (row 6) does move the capacity number** — ~20× memory is a slope change.
- **The quadratics (rows 2–3) do not.** At typical sizes they cost microseconds and the
  "fix" can be slower; they are a **tail-latency and fairness** issue that multitenancy
  promotes from private hiccup to shared outage (§8.3). Justify them with p99 under a
  noisy tenant, not with tenants-per-process.
- **Clone reduction (row 1) needs a different fix than assumed** — `structuredClone` is
  slower than the current `JSON.parse(JSON.stringify(...))`, so the win has to come from
  not cloning at all.

Revised claim, still to be tested: **representation plus locality (columnar hot cache over
a local store) moves capacity more than any language or runtime change**, and the
quadratics must be fixed for fairness regardless of what capacity they buy.

---

## 10. Benchmark plan

The purpose is to replace opinion with numbers, using everything available: real code,
synthetic tenants, ecosystem-realistic workloads, and both userland and kernel profiling.

### 10.1 Harness

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

### 10.2 Metrics (fixed set, reported for every arm)

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

### 10.3 Arms

| ID | Arm | Question |
|---|---|---|
| EXP-MT-001 | Control: N separate processes, current code | Baseline $/tenant, RSS/tenant, isolation reference |
| EXP-MT-002 | Multi-ctx in one process (§4B), Mongo + tenantId | Where does the wall sit? |
| EXP-MT-003 | Multi-ctx + residency tiering (§4C) | Does cost track concurrency instead of registrations? |
| EXP-MT-004 | Stateless/on-demand (§4D) | Is recompute-per-request cheaper than resident ddata? |
| EXP-MT-005 | Sharded K-tenants-per-process (§4E) | Best K for fairness vs. overhead |
| EXP-MT-010 | Cold-tenant alarm evaluator | Can alarms be safe without a resident ddata? |
| EXP-MT-011 | Storage: Mongo discriminator vs DB-per-tenant vs Postgres+RLS vs SQLite-per-tenant | Query cost, isolation, idle cost, backup/restore/export time |
| EXP-MT-012 | `better-sqlite3` vs `node:sqlite` at 100/1 000 open tenant DBs | Handle limits, WAL contention, cold open latency — **preliminary result in §7.1: not a limiter** |
| EXP-MT-013 | Validation: none vs zod vs compiled Ajv-from-OpenAPI | CPU cost of boundary validation at N × ingest |
| EXP-MT-014 | keyv for ephemeral tenant state (memory vs SQLite vs Redis adapters) | Does it hold up as the shard-safe state layer? |
| EXP-MT-020 | Hot loops: current JS vs Map-optimised JS vs WASM vs worker-thread offload | Is WASM worth the boundary cost *after* the JS fix? |
| EXP-MT-021 | Representation: objects vs typed-array/columnar ddata | The memory-per-tenant order-of-magnitude question — **preliminary result in §7.4: ~20× memory, ~500× wake, on SGVs** |
| EXP-MT-022 | eBPF-instrumented run of the winning arm | Where does time really go at scale? |
| EXP-MT-030 | Nocturne under the identical workload | Cross-server capacity comparison; validates the harness itself |
| EXP-MT-032 | Per-process RSS/PSS by require-graph layer (`footprint.js`) | Preliminary result in §8.9.1: ~99 MB before any tenant data, ~80:1 code-to-data |
| EXP-MT-033 | `process` vs `worker_threads` vs `shared` at fixed N (`arch.js`) | Preliminary result in §8.9.2: `shared` wins 10–20×; worker ≈ process once real code is loaded |
| EXP-MT-034 | Cold spawn+require latency by layer (`MEASURE_START=1 footprint.js`) | Preliminary result in §8.9.3: 22 ms bare → 266 ms p50 full server; scale-to-zero viability |
| EXP-MT-035 | `shared` mode against real `ddata`/`dataloader`, 300/1 000 tenants | Does the 5 MB/tenant synthetic figure survive real query/cache code? |
| EXP-MT-036 | Postgres RLS overhead at N tenants × ingest rate, live container (`rls-poc/perf.js`) | Preliminary result in §5.2.1/§5.4: ~0.32 ms overhead vs hand-written filter at 500×600 rows — noise at Nightscout's actual query rate |
| EXP-MT-037 | Migration LOC/time spike: port 2–3 representative collections (entries, treatments) from Mongo filters to the §5.2 repository seam + Postgres/RLS, **and** build/time a plain Mongo change-stream-tailing backfill+dual-write script (no Kafka) per §5.2.2 | The one real, unmeasured cost in the "adopt RLS" recommendation of §5.4; also settles whether Kafka/Strimzi is ever necessary for this or is over-engineering for a bounded per-tenant migration |

`EXP-MT-030` matters disproportionately: running the *same* generator against Nocturne
gives the ecosystem its first apples-to-apples server comparison, and it also fills the
gap that Nocturne's own repo has no tenant-count scaling benchmark. `EXP-MT-032/033/034`
matter for a different reason: they are the numbers that actually decide the
"pod-per-tenant vs shared-process" argument raised by real hosters (T1Pal, NSPro), and
§8.9 shows preliminary results already favour `shared` by an order of magnitude,
independent of any language question.

### 10.4 Method notes

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

### 10.5 Decision rule (proposed, to be argued now rather than later)

Adopt a multitenant direction only if the winning arm shows, at N ≥ 250 tenants:

1. **≥ 5× reduction** in $/tenant-month vs. EXP-MT-001; and
2. p99 entry→broadcast propagation **within 2×** of the control; and
3. **zero** cross-tenant leakage across the full correctness suite; and
4. cold/warm alarm latency **no worse** than the control; and
5. a credible operational story for backup, restore, per-tenant export and per-tenant
   deletion.

If no arm clears the bar, the finding is "keep the single-tenant deployment model and
spend the effort on the §9 amplifiers" — which would itself be a valuable, publishable
result.

---

## 11. Phasing — a layered dependency model, not just an ordered list

This document has mixed a lot of tactics: typed schemas, RLS, JSONB, shared-process
architecture, columnar representation, adaptive fairness fixes, native/WASM cores. Not all
combinations matter, and some pairs are **substitutes** (doing both wastes effort) rather
than **complements** (doing both compounds). Restated as layers, each with what it
requires below it, what it's a substitute for, and what independently justifies it on its
own even if nothing above it ever ships:

| Layer | Move | Requires | Substitute for | Ships alone? |
|---|---|---|---|---|
| **0. Typed vocabulary** | Generate zod/Ajv validators from `specs/openapi/`, formalizing the *existing* `indexedFields` lists (§5.2.2) as the schema | Nothing — first move | Nothing; this is load-bearing infrastructure, not an alternative to anything | **Yes.** Correctness win today, single-tenant, zero risk. Also the *measured* precondition for every later win (§8.1: Rust without a schema loses to V8; columnar without a schema is undefined) |
| **1. Storage isolation primitive** | Either (1a) a single enforced query-builder seam on Mongo, or (1b) JSONB+generated-columns+RLS on Postgres, migrated per-tenant (§5.2.2) | Layer 0 (need `tenant_id` and the hot-field set typed to write the generated columns / enforce the seam) | Nothing on its own — but is a **prerequisite**, not optional, for Layer 2 | **Yes**, and *should* ship before Layer 2 — see the ordering note below |
| **2. Shared-process architecture** | `ctxFor(tenantId)`, one process holds N tenants (§4B) | Layer 1, non-negotiably (see below) | **A runtime rewrite** (§8.2: both attack the same 41 MB/process constant; measured, don't do both) | No — needs Layer 1 first |
| **3. Representation (columnar hot window)** | Typed schema (Layer 0) to know field shapes | Nothing directly | Nothing; independent axis | **Yes**, and helps single-tenant sites even without Layers 1–2 |
| **4. Fairness fixes for the O(n²) sites** | Nothing structurally, but low priority until Layer 2 ships | Nothing | Nothing | **Yes**, but priority should track Layer 2's schedule (see below) |
| **5. Native/WASM compute core** | Layer 0 (typed, stateless data — §8.1 shows this fails without it) and evidence of a genuine CPU-bound hot path *after* Layers 2–3 are in | Layers 0, 2, 3 | **Nothing** — not a substitute for Layer 2 (§8.2), and actively harmful to attempt before Layer 0 | No — conditional and last |

**The two orderings that are load-bearing, not just tidy:**

1. **Layer 1 before Layer 2 is a safety requirement, not a style preference.** Sharing one
   process across tenants (Layer 2) means a storage-isolation bug now has a *live*
   co-resident neighbour to leak into, not just a log line in an already-compromised
   single-tenant pod. §5.2.1 demonstrated RLS is fail-closed *by construction* — shipping
   Layer 2 on top of Mongo's application-only filter (§5.2.1's leak table, column 4) would
   turn a discipline problem into a live cross-tenant data breach surface. If Layer 1 must
   be deferred for cost reasons, Layer 2 should be deferred with it, or restricted to a
   small number of mutually-trusting tenants (e.g. one operator's own test sites) rather
   than the general multi-tenant case.
2. **Layer 4 (fairness) should be pulled forward to ship *with* Layer 2, not after it.**
   §8.3 already showed the O(n²) sites are invisible at single-tenant sizes and a 30× tail
   at heavy ones — Layer 2 is precisely the change that turns "one heavy tenant's private
   80 ms hiccup" into "every co-resident tenant's shared stall." Shipping Layer 2 without
   Layer 4 creates the exact failure Layer 4 exists to prevent, on a schedule dictated by
   whichever tenant happens to be busiest that day.

**What's genuinely independent (parallelizable, no ordering constraint between them):**
Layer 0 and Layer 3 have no dependency on tenancy work at all and can — and should — ship
on their own timeline, reviewed by whoever owns performance/correctness today, without
waiting for a tenancy decision. This is deliberate: if the multitenancy program stalled or
were rejected outright, Layers 0 and 3 would still have been worth doing.

**What this rules out, plainly:** "migrate to Nocturne" is not a layer in this model at
all — §3's correction and §5.4 showed it doesn't supply anything Layers 0–2 don't already
supply, at a much higher migration cost. "Rewrite in Rust/Go" is Layer 2's substitute, not
its complement — pick one. A native/WASM core (Layer 5) is real but strictly last,
conditional, and only pays off *after* Layer 0 removes the representation penalty that
made Rust lose to V8 in the first place (§8.1) — attempting Layer 5 before Layer 0 is the
single most measurably counterproductive sequencing mistake this document can name.

**Ordered execution, given the layers above and their constraints:**

1. **Measure first.** Extend `tools/mt-bench/` into the §10 harness; run EXP-MT-001/002 and
   EXP-MT-026 (real remote DB in the loop). Cheap, independently useful, non-invasive.
2. **Layer 0 — schema work (§5.3).** Generate validators from `specs/openapi/`; formalize
   the existing `indexedFields` lists as the schema (§5.2.2) rather than inventing a new one.
3. **Layer 3 — columnar hot window** for entries/MBGs/cals and Loop's `predicted.values`
   (EXP-MT-021/025). Ships independently of tenancy; helps single-tenant sites today.
4. **Layer 1 — storage isolation primitive.** Either harden the Mongo query-builder seam
   (1a, cheaper, weaker) or begin the incremental per-tenant Postgres/RLS migration (1b,
   §5.2.2 — JSONB-first, generated columns for the ~22 fields already indexed, per-tenant
   cutover via a change-stream-tailing backfill+dual-write script, no flag day, no Kafka
   dependency assumed). EXP-MT-037's migration spike belongs here, before committing to
   1b at scale.
5. **Layer 4 — fairness fixes for the quadratics** (§8.3), timed to land with or just
   before Layer 2, not after — see the ordering note above. Ideally adaptive (scan when
   small, index when large — EXP-MT-028).
6. **The query-model seam** (§5.2) as a refactor toward the *documented* API v3 query
   model, validated by the existing test suites — this is also what makes Layer 1's
   choice of backend (Mongo-hardened vs. Postgres/RLS) invisible to most call sites.
7. **Tenant-scope the request path**: resolution middleware, socket rooms, socket
   auth binding, per-tenant settings — behind a flag that defaults to single-tenant.
8. **Layer 2 — tenant-scope the data path**: `ctxFor(tenantId)`, per-tenant
   cache/loader/plugins. Only after step 4 (Layer 1) is in place for the tenants being
   shared.
9. **Residency tiering + cold alarm path**, if EXP-MT-003/010 support it.
10. **Layer 5 — shared native cores only where already typed and stateless** (§8.5),
    conditional on profiling *after* steps 2–8 still showing a CPU-bound hot path —
    preferably by reusing Nocturne's Rust crates, compiled native for the server and WASM
    for the browser. Not a host change (§8.4), and not a step to take early.

---

## 12. Relationship to the parallel tooling evaluation

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

## 13. Open questions for the maintainers

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
8. Given §8.2 — that multitenancy and a runtime rewrite are **substitutes** for the same
   ~41 MB per-process cost — is the project's preference to keep one-process-per-person and
   shrink the process, or to keep Node and share the process? Both are defensible; doing
   both buys little. This is arguably the actual fork in the road.
9. Is the project willing to treat **schemas as performance infrastructure** (§8.1, §11.3)
   rather than as documentation? That reframing is what makes the representation work
   possible, and it changes who needs to review it.

---

## 14. References

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
