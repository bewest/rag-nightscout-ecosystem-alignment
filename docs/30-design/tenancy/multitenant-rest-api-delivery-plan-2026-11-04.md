# Multitenant REST v1–v3: design and parallel implementation plan

*Current-use guide, 2026-11-06: Use the [dashboard](multitenant-delivery-dashboard.md) for acceptance and the [batching plan §5](multitenant-integration-batching-plan-2026-11-06.md#5-current-completion-schedule-adopted-2026-11-06) for current sequencing. This page retains the route/domain design and original implementation packets; its original heads and next steps describe that dispatch.*

**2026-11-04 · Contributor-facing proposal · implementation delivery, not REST readiness.**

Deliver one runnable API listener with tenant-safe versions of the actual v1, v2 and v3
surfaces below. Implement by **collection/domain across versions**, reusing shipping handlers,
query construction and write rules. Do not build three new APIs or wait for a universal
framework, production registry, owner lifecycle or a chain of administrative packets.

Current delivery status lives in the [dashboard](multitenant-delivery-dashboard.md)
and [release acceptance record](../remedial/rc-16.0.0-integration-record.md).
The [November 5 priority packets and compatibility matrix](../../archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#prioritized-rest-and-compatibility-execution-2026-11-05)
sequence current administration, wider REST and parallel historical/current
compatibility execution. Their expected-change rules preserve intended RC fixes
and measured client quirks; the historical source inventory is not current admission.
The source inventory and initial package assignments below retain their captured
baseline; already accepted domain implementations must not be rebuilt from those
historical missing/pending labels. The [continuation lanes](../../archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#rest-continuation-and-qms-reconciliation-2026-11-04)
carry derived reads, pinned-pattern replay and independent authority review.

## 1. Basis and boundaries

All source findings in this document are **read-derived** from
[cgm-remote-monitor `c527fb7e0d309b7fc567861a41e8f3862e0922df`](https://github.com/nightscout/cgm-remote-monitor/tree/c527fb7e0d309b7fc567861a41e8f3862e0922df).
Every `lib/`, `tests/`, `scripts/` and `migrations/` citation below refers to that CRM
tree, not the alignment repository. Line numbers are pinned to it; inspect with
`git show c527fb7e:<path> | nl -ba`. Swagger is not the route inventory.
No application tests were executed for this design; proposed parity, throughput,
client compatibility and completeness are **UNMEASURED**.

Anchors verified before writing:

| tree/reference | observed anchor |
|---|---|
| accepted cumulative CRM / PR #8898 | `c527fb7e0d309b7fc567861a41e8f3862e0922df`; PR OPEN, draft |
| CRM `official/dev` | `4a482627bfdafb1fef8dcbe0ac6c484811cae563` |
| alignment `main` | `4714b1a7409403c91ec2c0f812cd0a21611491f6` |
| this plan's alignment base | `3982d589a2d28da4bf831f1182e93858e7eb4c59` |

The [release decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#runnable-preview-and-parallel-crud-delivery-2026-11-04)
authorize a bounded runnable preview and entries CRUD in parallel. They do not authorize
an all-REST capability claim. Candidate 16.0.0 release acceptance is a separate process.
The [delivery roadmap](multitenant-delivery-roadmap.md),
[execution plan](multitenancy-decisions.md),
[storage seam](nightscout-storage-seam-interface-2026-09-14.md) and
[write contract](write-contract-spec-2026-10-07.md) supply prior art. Historical census
figures in those documents are not a current count or a reason to redo work already in source.

**Accepted bounded composition:** actual API3 entries GET/search and POST through injected
storage/current authority, compatible v2 credential exchange, and the canonical resolver seam.
This statement identifies the accepted lane boundary, not a new verification run.
`lib/server/tenant-app/data-access.js:26–38` admits only entries GET/list/address and POST/list;
history is deliberately reserved. Its v3 bridge rejects legacy query/body credential carriers.
`lib/server/tenant-app/index.js:137–168` mounts exchange and a protected v3 data router,
not the complete single application. An API3 `Collection` constructor or a storage primitive
does not establish admission for its other routes.

**Active implementation, delivery pending:** the entries CRUD lane owns API3 mutation/history
handler intent seams, entries tenant bridge/admission, required storage primitives and tests;
the runnable CLI lane owns `nightscout multitenant api`, strict operator preview configuration,
PG/Vault/current-authority boot, read-only readiness, owned shutdown and child-process tests.
Do not duplicate these changes or infer their acceptance from their briefs. Subsequent code
starts from their clean, integrated, accepted head when it needs their seams. Neither lane
waits for this plan.

## 2. Source route inventory

### Reading the matrix

Paths are relative to `/api/v1` or `/api/v2` in the legacy table and `/api/v3` in the v3
table. **Every v1 row is also mounted in v2**, because `lib/api2/index.js:14` mounts the
entire v1 application before its extras. A regex `app.all` dispatch is not an implemented
business method: only the child registrations below count. Express supplies implicit HEAD
for GET and automatic OPTIONS; include these in HTTP regression checks rather than inventing
PUT/PATCH routes. Trailing-slash and case behavior follow the shipping Express configuration.
The common legacy suffix set is json/svg/csv/txt/png/html/tsv; status additionally recognizes
js through its own middleware. A recognized suffix does not guarantee every handler renders
that format: retain its negotiated refusal/redirect as well as export successes. API3 has a
different suffix-to-MIME parser and JSON/CSV/XML renderer
(`lib/api3/shared/renderer.js:65–107`).

Readiness: **A** accepted bounded seam; **P** active implementation pending; **M** missing
tenant implementation; **X** deliberately excluded from the initial runnable preview, still
accounted for in the full-surface goal. X is not completion. Owners are future packages in §5.

Dependency shorthand: **S** tenant-scoped collection storage; **Q** existing query/filter/
projection/sort/count dialect; **W** existing write-intent and per-route validation/replies;
**E** tenant-scoped history, bus and cache invalidation; **R** derived runtime snapshot;
**C** tenant-safe settings/environment view; **I** current identity/authority;
**N** notification/connector side effects. These are requirements, not available capabilities.

### Legacy data and helpers — mounted in both v1 and v2

`lib/api/index.js:147–177` mounts entries, echo, times, slice, count, treatments, profile,
devicestatus, notifications, activity, verifyauth, adminnotifies, food, status and conditional
assistant routers. Formats are URL suffix aliases, not separate data stores:
`lib/api/index.js:46–48` and `lib/middleware/express-extension-to-accept.js:21–39`.

| domain | actual methods and paths | shipping handler anchor | tenant readiness; dependencies | next owner; synthetic instrument |
|---|---|---|---|---|
| entries read | GET `/entries`, `/entries/current`, `/entries/:spec` | `lib/api/entries/index.js:351–409` | M; S/Q/R/C/I; `:spec` is ID **or model**, absent ID returns `[]`, not API3's addressed reply | E; legacy HTTP/query/cache differential |
| entries writes | POST `/entries/`, DELETE `/entries/`, `/entries/:spec` | same file `839–879`; enabled API only | M; S/Q/W/E/I; no PUT/PATCH here | E; object/array/retry/delete differential |
| entries dry run | POST `/entries/preview` | same file `832–836`; outside API-enabled registration block, still permission checked | M; W/I/C, no persistence | E; prove zero rows/events |
| echo | GET `/echo/:echo{/:model}{/:spec}` | same file `417–435,594` | M; Q/I/C; dynamic `ctx[storage].query_for`, not an arbitrary SQL table selector | E + owning collection; synthetic selector/refusal cases |
| time helpers | GET `/times/echo{/:prefix}{/:regex}`, `/times{/:prefix}{/:regex}` | same file `612–700,788–809` | M; Q/S/I; dateString/brace/regex behavior, echo need not read rows | E; bounded pattern and refusal tests |
| slice/count | GET `/slice/:storage/:field{/:type}{/:prefix}{/:regex}`, `/count/:storage/where` | same file `769–824`; `lib/server/aggregate.js:29–48` | M; S/Q/I; storage selection entries/treatments/devicestatus, unknown selection currently defaults entries; count is filtered count, not a general aggregation API | E + T/D; count/list agreement and cross-collection permissions |
| treatments | GET `/treatments`, POST `/treatments/`, PUT `/treatments/`, DELETE `/treatments/`, `/treatments/:id` | `lib/api/treatments/index.js:89,186,214–234` | M; S/Q/W/E/R/I, API-enabled mutations | T; same-time, resends, validation, batches |
| devicestatus | GET `/devicestatus/`, POST `/devicestatus/`, DELETE `/devicestatus/`, `/devicestatus/:id` | `lib/api/devicestatus/index.js:82,197,241–266` | M; S/Q/W/E/R/I; mutations API-enabled, no legacy PUT/PATCH | D; prediction/identity/resend and delete differential |
| profile | GET `/profiles/`, `/profile/`, `/profile/current`; POST `/profile/`, PUT `/profile/`, DELETE `/profile/`, `/profile/:_id` | `lib/api/profile/index.js:63–101,191–240` | M; S/Q/W/E/R/I; mutation registration API-enabled; plural alias is actually mounted by profile regex | F; current-profile/order/prune and restart cases |
| food | GET `/food/`, `/food/quickpicks`, `/food/regular`; POST `/food/`, PUT `/food/`, DELETE `/food/:_id` | `lib/api/food/index.js:27–48,97,135` | M; S/W/E/I; mutation registration API-enabled | F; quickpick order, edit and replay |
| activity | GET `/activity`, POST `/activity/`, PUT `/activity/`, DELETE `/activity/:_id` | `lib/api/activity/index.js:33,128–142` | M; S/Q/W/E/I; mutation registration API-enabled; **not** an API3 collection | D; coercion/order/CRUD differential |

### Legacy status, identity and side effects — mounted in both v1 and v2

| domain | actual methods and paths | shipping handler anchor | tenant readiness; dependencies | next owner; synthetic instrument |
|---|---|---|---|---|
| status | GET `/status` and negotiated suffix formats | `lib/api/status.js:9–73` | M; C/I; filtered settings, extended settings, runtime state/index summary and optional token issuance, not just a health check | H; public/authenticated response and secret/tenant non-disclosure |
| authorization probe | GET `/verifyauth` | `lib/api/verifyauth.js:9–30` | M; I; shipping boolean/message response uses HTTP200 even for unauthorized probe result | H; carriers and current permission transitions |
| admin notices | GET `/adminnotifies` | `lib/api/adminnotifiesapi.js:9–27` | X; I/R; tenant-specific notice count and admin contents, never process-wide notices | H/N; two-tenant counts and admin filtering |
| notification receipt | POST `/notifications/pushovercallback` | `lib/api/notifications-api.js:15–17` | X; N; receipt ownership and callback validation are needed; unknown receipt is shipping no-op success | N; fake provider, unknown/restarted receipt, zero foreign acknowledgments |
| acknowledge | GET `/notifications/ack` | same file `20–28`; API-enabled | X; N/I; **GET has side effects** | N; tenant receipt/group/time and duplicate ack |
| debug experiment | GET `/experiments/test` | `lib/api/index.js:40–43`; `lib/api/experiments/index.js:11` | X; I; API-enabled and explicit debug permission, mounted before suffix middleware | H; default absent/refused, permission control |
| assistant integrations | POST `/alexa`, `/googlehome` | `lib/api/index.js:171–176`; `lib/api/alexa/index.js:19`; `lib/api/googlehome/index.js:18` | X; R/C/I/N; only when corresponding context exists; locale, plugin handlers and sandbox dependencies | N; fake requests, tenant locale/runtime isolation |

### v2-only extras

These are not the API3 owner/operator APIs. Their legacy administration permissions and
response shapes need an explicit tenant bridge, not an automatic mount of process authority.

| domain | actual methods and paths under `/api/v2` | shipping handler anchor | tenant readiness; dependencies | next owner; synthetic instrument |
|---|---|---|---|---|
| exchange | GET `/authorization/request/:accessToken` | `lib/authorization/endpoints.js:31`; tenant route `lib/server/tenant-app/index.js:138–147` | A, bounded tenant exchange only; I/current metadata/provider | H; `tests/tenant-credential-http.integration.test.js`, real provider/restart/revocation |
| permission discovery | GET `/authorization/permissions`, `/authorization/permissions/trie` | `lib/authorization/endpoints.js:41–46` | M; I; seen/expanded permissions must be tenant-local | H; two-tenant authority differential |
| subjects | GET, POST, PUT `/authorization/subjects`; DELETE `/authorization/subjects/:_id` | same file `48–79` | X; I; persistent identity, token/name changes, grants and invalidation side effects | H; admin/data/owner plane separation and revoke/rename |
| roles | GET, POST, PUT `/authorization/roles`; DELETE `/authorization/roles/:_id` | same file `88–113` | X; I; Shiro role interpretation/current grants, not operator policy | H; stale JWT after role change and cross-tenant denial |
| debug permission check | GET `/authorization/debug/check/:permission` | same file `122–123` | X; I; no process-global permission telemetry | H; allowed/refused permissions |
| properties | GET `/properties/{*path}` | `lib/api2/index.js:15`; `lib/api2/properties.js:44–90` | M; R/I; selected sandbox properties, pretty formatting; entries **and** treatments read permission | H; nested selection and snapshot isolation |
| derived data | GET `/ddata/at{/:at}` | `lib/api2/index.js:17`; `lib/data/endpoints.js:10–16,70–77` | M; R/S/Q/I; current/historical clone and dataloader; entries **and** treatments permission | H; as-of frame and interleaved-tenant reads |
| summary | GET `/summary/` | `lib/api2/index.js:19`; `lib/api2/summary/index.js:113–129` | M; R/I; entries, treatments, current profile and computed state; `hours` default | H with T/F; derived-value differential |
| Loop notification | POST `/notifications/loop` | `lib/api2/notifications-v2.js:14–38` | X; N/I/C; remote egress/override side effects, client-address provenance | N; fake egress, retries, permission/tenant/peer controls |

### v3 generic collections and special routes

**G3** means exactly this registration set, expanded for each collection below:
GET `/{collection}`, POST `/{collection}`, GET `/{collection}/history`,
GET `/{collection}/history/:lastModified`, GET `/{collection}/:identifier`,
PUT `/{collection}/:identifier`, PATCH `/{collection}/:identifier`,
DELETE `/{collection}/:identifier`.
History is registered before the identifier route. No generic root PUT, collection DELETE,
batch endpoint, count endpoint, legacy `/current` or activity collection is registered.
The POST body contract is a document, not the legacy array contract.
Source: `lib/api3/generic/collection.js:49–78`;
`lib/api3/generic/create/operation.js:18–25`.

| domain | mounted family | shipping setup anchor | tenant readiness; dependencies | next owner; synthetic instrument |
|---|---|---|---|---|
| entries | G3 with `entries` | `lib/api3/generic/setup.js:67–79` | A for GET/search/address + POST; P for PUT/PATCH/DELETE/history; S/Q/W/E/I | existing CRUD lane; E follows with legacy routes; real-provider entries HTTP |
| treatments | G3 with `treatments` | same file `107–115` | M; S/Q/W/E/I; created_at/eventType fallback | T; cross-version history and dedup |
| devicestatus | G3 with `devicestatus` | same file `56–64` | M; S/Q/W/E/I; created_at/device fallback | D; JSON extension/prediction and duplicate races |
| profile | G3 with `profile` | same file `90–98` | M; S/Q/W/E/I; created_at fallback distinct from legacy startDate semantics | F; legacy create → v3 read/edit/history |
| food | G3 with `food` | same file `80–88` | M; S/Q/W/E/I; created_at fallback | F; cross-version retention and tombstones |
| settings documents | G3 with `settings` | same file `100–105` | M; S/Q/W/E/I; no collection fallback date; strict-read policy | H; dedicated document-collection tests; **not owner configuration storage** |
| version | GET `/version` | `lib/api3/index.js:68`; `lib/api3/specific/version.js` | M; C; safe build/API information, admission must not pretend it is entries | H; actual public/authenticated HTTP |
| status | GET `/status` | `lib/api3/index.js:86`; `lib/api3/specific/status.js:12–65` | M; I/C; permissions of actually admitted collections only | H; branch-sensitive current permission checks |
| modification discovery | GET `/lastModified` | `lib/api3/index.js:84`; `lib/api3/specific/lastModified.js:11–95` | M; S/E/I; per-authorized-collection clocks and fallback dates | H + collection owners; no foreign clock/count leakage |
| conditional debug | GET `/test` | `lib/api3/index.js:70–81`; development/test/CI only | X; I; entries read permission | H; production absent, explicit test mode behavior |
| documentation redirect | all methods at `/swagger-ui-dist` prefix | `lib/api3/index.js:94–96` uses `app.use` | M; safe static redirect, no data privilege implied | H; 307/location, suffix/subpath/method checks |

`lib/api3/index.js:56` enables six collections in the shipping v3 app; that is not the
preview allowlist. Its terminal middleware returns API3 operation-not-found
(`98–100`). `lib/server/app.js:313–316` mounts the versions in the single application.
`GET /api/versions` is an additional discovery neighbor from `lib/api/root.js:10–18`,
not `/api/v1/versions`; H should supply an honest tenant capability-aware discovery view.
Root swagger documents, `/api-docs`, `/api3-docs`, `/pebble`, static pages and clocks are
outside the requested version prefixes and are not gained by REST completion.

Socket.IO storage/alarm channels (`lib/api3/index.js:102–103`, `lib/server/websocket.js`)
are separate realtime work. Do not construct them as an accidental side effect of mounting
the tenant REST router. No GraphQL endpoint is registered by the v1/v2/v3 mount graph above;
do not infer a new surface from unrelated documentation. Remote connectors and notification
egress remain explicit N work, not an invisible consequence of CRUD.

## 3. Architecture to implement

### 3.1 One tenant service graph, thin version adapters

**Recommendation:** retain version-specific HTTP handlers over shared, tenant-bound collection
ports and shared write-intent rules. Bind a request to stable tenant identity, then obtain a
trusted collection/service bundle. Never switch a global `ctx`, environment, Mongo collection
name or "current tenant" between requests.

The source already supplies the hard seams:

* `lib/api3/generic/collection.js:26–44` accepts trusted `storage`/`intentFactory` options,
  while the default still constructs Mongo plus cache. `lib/api3/shared/collectionWriteIntent.js:5–8`
  selects that intent factory. Extend those existing seams where the CRUD lane proves the need.
* Legacy domain wrappers already share `lib/storage/write-intent.js`; for example
  `lib/server/entries.js:34–35`, treatments `28–29`, devicestatus `57–58`, profile `34–35`,
  food `20–21`, activity `22–23`. Their parsers, domain transformations, callbacks and
  event shaping stay in the wrappers. `lib/server/storage-reads.js:34–36` still hardcodes
  Mongo construction; that, not a new REST framework, is the remaining legacy injection seam.
* `lib/storage/postgres-entries-intent.js:48–89` combines reader/writer with
  `forCollectionResolved`, commits through an owned transaction, and emits the intent
  event after commit. It currently refuses source other than `v3`; it is not already a
  legacy adapter. `postgres-entries-read.js:85–99` refuses v1 dialect/readOptions and
  unsorted bounded reads. Do not erase those refusals to make v1 tests green.

Proposed narrow additions, owned by S (§5), defaulting to current behavior:

1. A trusted logical-collection resolver used by legacy `storage-reads.collection`, and
   an injected intent factory in legacy wrapper construction, so each wrapper can use
   `source: 'v1/internal'` rules without constructing a raw Mongo handle. Keep callable
   driver accessors on the single/Mongo path; tenant routers must not receive those accessors.
2. A small explicit domain registration object per collection: legacy wrapper/router factory,
   v3 `Collection` options, schema/readiness requirements, admitted method set. These are
   trusted code, not user registration or request-supplied SQL identifiers.
3. An integrator-owned composition point that mounts completed domain routers under all
   their real prefixes with version-aware admission. An unsupported route is refused before
   backend lookup, never forwarded to the single application or a catch-all Mongo adapter.

Concretely, the proposed resolver accepts trusted `{ logical, source }` constants and returns
the existing storage interface plus an intent factory; tenant identity comes from the bound
request scope, not those arguments. Legacy `store()`/`step()` closures consume this bundle;
API3 consumes the same domain's `storage`/`intentFactory` constructor options with source `v3`.
Missing domain capabilities fail closed in tenant mode; absence of the optional injection in
single mode preserves today's Mongo construction. S owns the shared resolver contract; each
domain owner makes its own wrapper-constructor change against that contract. Test both
injected and uninjected construction before expanding mounts.

Share pools and immutable code, not credentials or mutable domain state. Construct tenant
settings/authorization views from persisted services; capture tenant-bound bundle references
for each handler execution. A bounded cache of router/service bundles may be keyed by stable
tenant ID plus configuration generation, with eviction/shutdown; it must not cache permission
decisions across protected operations. Request-bound transaction context remains authoritative
even if a router bundle is reused.

**Why not just mount `lib/api` with a renamed database?** Its handlers capture `ctx` at
construction. Entries uses `ctx.ddata` for conditional responses and `ctx.cache` for fast reads
(`lib/api/entries/index.js:73–98,447–477`); writes use `ctx.ddata.processRawDataForRuntime`
and `ctx.bus` (`lib/server/entries.js:167–179`). Properties, summary, assistants and notifications
capture sandbox/runtime/plugin/egress state. `lib/server/bootevent.js:313–335,514–551`
constructs this process graph and event subscriptions. A global context clone or
`Object.assign` is not isolation.

For initial legacy data routes, inject **tenant-local read snapshots, cache and bus**, with
the existing normalization functions. Where cache-backed behavior has not been implemented,
admit only paths proven storage-only; do not silently return empty ddata or suppress conditional
headers. H owns the reusable snapshot/data-loader binding; collection teams can implement and
test their storage and version handlers in parallel using an actual tenant snapshot fixture,
then join the runtime seam. Expensive sandbox evaluation can later be externalized without
changing the REST contract; that is not a prerequisite for collection writes.

### 3.2 Storage: reuse JSON document machinery, not entries policy

Keep PostgreSQL/RLS as the multitenant target and Mongo as the single compatibility baseline.
`lib/server/storage-backends.js:21–27` registers only Mongo; `tests/support/backends.js:39–63`
also marks global PG fixtures unavailable. **Do not flip either registry globally** to claim
every collection works. Add capability-scoped tenant composition and focused real-PG fixtures;
promote the global backend only when its advertised fixture/storage contract is genuinely built.

Reuse tenant connection/transaction/scope, typed `_id` codec, JSON representability checks,
filter compiler and common row operations. Proposed storage layout: one RLS-protected table
per logical collection, using the existing tenant_id + id_kind + JSON document pattern,
with collection-specific generated time/index columns. No per-version tables and no
one-off copy of every generic operation. A new collection may use the common row adapter
only after its query columns, ordering, identity and write rules are tested.

The entries candidate `migrations/candidates/postgres-entries-v1.json` is **entries-only**:
typed primary identity, tenant-prefixed indexes, identifier uniqueness and FORCE RLS.
Do not rename its table and call the other schemas done. Domain-owned migration candidates
must preserve:

| collection | required semantics to specify and test before admission |
|---|---|
| entries | date/sysTime/type, model-specific coercion, fallback identifier and current/history order; existing schema and accepted intent seam are the starting point |
| treatments | created_at/eventType/timezone handling, identifier and fallback-key matching, treatment duration/target units, same-time distinct records, array resend and validation outcomes |
| devicestatus | created_at/device matching, prediction JSON shape/size rules, stable retry identity and latest read order |
| profile | legacy startDate/current profile/list order and pruning; v3 created_at fallback; nested profile JSON, exact identifier/_id rules |
| food | quickpick ordering/regular filtering, server-created timestamps versus submitted dates, edit semantics and unknown nested fields |
| activity | its own date coercion and v1/internal rules, including absence of automatic server dates where shipping rules omit them; no invented v3 route |
| settings documents | generic v3 document/history/strict-read semantics; physically and semantically distinct from versioned tenant-owner settings and secrets |

Source detail: `lib/storage/write-intent.js:160–171` names collection-specific identity time
keys; `lib/api3/generic/setup.js:56–115` names v3 fallback dates/dedup fields;
`lib/server/profile.js:131–177` uses startDate queries/current ordering;
`lib/server/food.js:136–170` implements quickpick/regular selection. Domain packages inspect
their full rules, not just this summary. Missing migration/index/normalization decisions block
**that collection or path**, not every REST team.

Retain unknown representable extension fields without registration. The existing PG codec
keeps ObjectId and same-spelling string identity distinct
(`lib/storage/postgres-identity.js:13–38`). JSONB validation and unsupported operations
(`lib/storage/postgres-entries-write.js:22–79`) are deliberate boundaries, not reasons to coerce
or discard client fields. A generic JSON schema need not enumerate future controller fields.
Use explicit operator migrations/read-only startup checks; never create schema in a gate,
route constructor or readiness probe.

### 3.3 Version-aware parsing, current authority and error contracts

Use the existing permission vocabulary for each collection/action and consult persisted current
authority on every protected operation. Host selects a stable tenant ID, not a principal.
Keep root explicit; subject mutations require exact current name alongside stable identity.
No anonymous writes; invalid presented credentials never degrade to anonymous/default grants.
Keep data, service, tenant-owner and private operator authority separate.

Do **not** reuse v3's credential reader for v1/v2 unchanged:
`lib/authorization/index.js:30–91` reads bearer, query token, object/first-array-item body token,
query secret/header secret and body secret, with its own precedence and removal from the body.
API3 security uses its own header flow (`lib/api3/security.js:11–39`), and the accepted
tenant data bridge explicitly refuses legacy carriers. H implements a version-aware extraction
bridge that reuses shipping extraction behavior without invoking the process enclave or
process subject store. Differentially test valid carrier precedence, empty/duplicate/malformed
credentials and body-field consumption. If shipping fallback behavior contradicts the approved
tenant invalid-credential rule, preserve single behavior and expose a specific tenant refusal;
do not quietly change legacy single semantics or silently accept the fallback.

Preserve middleware order and body limits, not just happy-path documents:

* `lib/api/index.js:40–48,120–145` places experiments before format rewriting and validates
  counts before data routes. Entries has send-status, raw parser, JSON up to 50 MB,
  URL encoding, extension rewriting and read permission before action permission
  (`lib/api/entries/index.js:44–59`). Other routers have their own ordering/limits.
* `lib/middleware/index.js:23–32` supplies 1 MB JSON/raw/URL-encoded defaults. Treatments
  and activity override JSON limits. `lib/api/notifications-api.js:10–11` also registers
  parent parsers during router construction; v2 inherits v1 middleware before its extras.
  Avoid replacing this with one process-wide parser that changes credential consumption.
* API3 uses its 50 MB JSON parser, parser-error response and extension negotiation
  (`lib/api3/shared/jsonParser.js:6–12`, `lib/api3/index.js:39–41`).
  Malformed JSON is not automatically the same status in every stack. The accepted
  tenant v3 mount parses before protection (`lib/server/tenant-app/index.js:168`);
  changing order or format admission needs explicit HTTP characterization.

Version responses stay version responses. For example, legacy missing entries ID yields
HTTP200 with an empty list; verifyauth returns a boolean/message probe, and API3 addressed
mutation/history has distinct statuses, envelopes and headers. Preserve v1 count tolerances,
default count/type/sort, deprecation headers, deletion response, batch partial results and
optional `Nightscout-Write-Results` / `results=items`
(`lib/api/index.js:76–145`, `lib/api/shared/batch-reply.js:38–66`).
Legacy queries carry nested `find[...]`/sort structures and path models, whereas API3 search
parses field/operator parameters, repeated `filter_parameters`, `sort`/`sort$desc`, `limit`,
`skip` and `fields` (`lib/api3/generic/search/input.js:109–213`). Keep those parsers in their
version layer and compile their resulting predicates only where representable. Defaults are
not uniform: treatments chooses count100 or count1000 when a find is present
(`lib/api/treatments/index.js:89–103`), devicestatus defaults to count10 and may read cache
(`lib/api/devicestatus/index.js:82–105`), while API3 uses its configured maximum/limit and
identifier/created_at/date/_id order chain. The PG compiler currently refuses regex, v1 AST,
dotted paths and several operand types (`lib/storage/postgres-filter.js:11–20,82–96`);
time/slice pattern support and legacy coercion therefore need real translation work, not
an admission-only switch.

The approved tenant mutation policy is narrow: missing current subject name401,
actual authority outage503; demonstrably nonrepresentable **submitted** document400,
recognized storage outage503, internal/unclassified error500. It is not a global conversion
of legacy exceptions, stored-data faults or TypeError. Preserve shipping API3 read-then-write
preconditions, seconds flooring and invalid-date behavior
(`lib/api3/generic/update/operation.js:67–75`, patch `50–58`), without claiming atomic CAS.
Unsupported PG query/update semantics refuse explicitly, not approximate Mongo behavior.
Where a new legacy refusal has no established public mapping, the domain owner brings the
exact mechanism and proposed version-specific status to the maintainer; unrelated routes proceed.

### 3.4 Cross-version writes, histories and notifications

Keep one canonical tenant/collection document store visible to every version. Continue using
`write-intent`'s `v1/internal` versus `v3` source rules; they intentionally differ. Reuse its
single/array, identifier matching, resend, duplicate-recovery and per-item outcome machinery,
plus the legacy batch reply helpers. Do not implement a PG-specific duplicate policy or
translate every successful write into an API3 reply.

Preserve srvCreated/srvModified, modifiedBy, validity/tombstones, fallback visibility and
lastModified/history after legacy writes, including restart behavior. A v1 create followed
by v3 search/history/read is a required test, not an assumption. History is the shipping
modified-document synchronization contract, not a newly invented append-only audit log.
Physical deletes and configured pruning retain their actual visibility semantics.

`lib/storage/write-intent.js:4598,4681–4706` separates resolved write execution from intent
event emission. The PG entries wrapper emits after its transaction; legacy wrappers also
produce data-update/data-received, and v3 handlers emit storage-socket updates. Keep these
layers distinct, tenant-tagged, and non-duplicated. Refused/rolled-back writes must not publish
committed changes. A tenant-local in-process invalidation bus suffices for the runnable preview;
it must not enable realtime/evaluator roles or imply durable multi-process notification delivery.
Durable change-feed/outbox delivery, if needed for later scale, is separately measured.

### 3.5 Status, discovery and management boundaries

Build an explicit safe env/settings view for each tenant. Never pass process.env, Vault
configuration, database configuration, all-tenant maps or process-wide admin notices into a
legacy status handler. Preserve legitimate client settings and token exchange behavior, not
secret values. v1 status may issue authorization material; mark responses no-store as shipping
does (`lib/api/status.js:14–18,24–44`). v3 status/lastModified must describe only that tenant's
admitted, authorized collections, not a configured-but-unimplemented six-collection list.

Keep API3 `settings` documents separate from owner configuration CAS/rollback APIs. For v2
subject/role administration, the proposed target is a tenant-scoped legacy compatibility facade
with its existing admin permissions backed by persisted authority/identity services; data
tokens never become owner or platform-operator credentials. Token/name/role changes must
invalidate current authorization across workers. That capability needs a concrete authority
mutation/import contract; read-only subject fixtures cannot substitute for it.

**Runtime target:** one consumer API listener for the v1/v2/v3 REST compatibility facade,
plus separately authorized owner and private operator listeners. The current headless
single `api` role (`lib/server/serve/api.js:3–13,36–40`) supplies only v3 and authorization,
and is not multitenant merely because of its name; `serve/roles.js:14–25` says so.
The active CLI lane enables only its explicit API preview; keep that scope and use environment
credential references, direct-alias defaults, and per-request immediate-peer checks in opt-in
canonical mode. Static operator maps remain configuration, not a durable registry.

## 4. Policy recommendations, without blocking collection delivery

These are proposed defaults, not new maintainer approvals.

| topic | recommendation and operator-visible effect | trade-off and bounded blocker |
|---|---|---|
| shared storage vs version forks | common collection ports, version-specific frontends; existing client bodies/replies retained | a small injection seam is maintained once; rejects unsupported semantics rather than claiming universal Mongo emulation |
| cache/runtime-dependent reads | tenant-local snapshots using existing normalizers/loaders; admit storage-only paths earlier | preserves conditional/derived behavior; cache-backed legacy paths wait for H's real snapshot seam, not CLI or CRUD |
| unknown helper collection selectors | code-owned allowlist; never lookup arbitrary tenant/process services; preserve shipping fallback only when it selects a safe admitted entries port | some previously meaningful dynamic contexts may need an explicit new refusal; E must characterize and present any observable change rather than guess |
| v2 subject/role management | eventually implement tenant-scoped compatibility facade; keep initial preview excluded | avoids breaking existing admin clients long-term; H can deliver status/exchange/discovery now while persisted mutation semantics are resolved |
| notification/assistant endpoints | retain explicit exclusion until tenant runtime, receipt ownership and fake-provider egress tests exist | preview breadth comes from data clients first; X rows stay incomplete, not "all REST complete" |
| unsupported inputs | exact translation where representable, explicit refusal otherwise | protects reliability/data fidelity; migration/client footprint and performance are unmeasured, so no parity claim outside tested shapes |

Long-term direction and architecture favor one shared domain graph rather than three adapters
that duplicate business rules. Backward compatibility is enforced against single/Mongo;
forward compatibility retains representable extension fields. Maintenance favors small injected
ports over a universal framework. Reliability requires current authority, RLS and honest refusal;
performance needs later representative query/index/snapshot measurements, not inferred wins.
Only a newly observed policy mismatch blocks the affected path. No new global maintainer
decision is required merely to begin domain storage, HTTP and synthetic tests.

## 5. Executable parallel work packages

**Start rule for every implementation brief:** confirm the exact clean base commit and that
the task is still open; stop and report a mismatch rather than reaching for the nearest working
substitute. Do not read another lane's uncommitted changes. Every package owns implementation,
its focused tests and red controls together; there is no separate packet prerequisite.

All proposed filenames below are implementation outputs, not assertions that files exist.
Default ownership is by domain, across versions. S owns shared-file edits and integrates small
exports from domain teams; do not have every agent edit the router, write-intent and census.

| package | deliverable and owned surfaces | real prerequisites / what can start now | exclusions and stop condition |
|---|---|---|---|
| **S — shared seams/integration** | trusted collection/intent injection in `lib/server/storage-reads.js` and legacy constructors; reusable PG row helper extracted only from proven common code; tenant domain mount/admission in `lib/server/tenant-app/index.js` and `data-access.js`; changes to generic `Collection`, `collectionWriteIntent`, shared `write-intent`, filter compiler, migration catalogue, test tiers/census centrally owned | planning/test characterization now; edits touching active entries CRUD/CLI files wait for their accepted join or explicit owner coordination; independent legacy seam tests can start immediately in a clean worktree | no new policy/rules, no global backend enablement, no duplicate CRUD/CLI implementation; stop on semantic mismatch or disputed shared-file ownership |
| **E — legacy entries + shared query helpers** | `lib/api/entries/index.js`, `lib/server/entries.js`, `lib/server/aggregate.js`; proposed tenant legacy-entries adapter and `tests/tenant-rest-entries.integration.test.js`; all legacy entries/helper matrix rows under both versions, formats and conditional reads | existing entries schema and accepted POST seam allow query/handler characterization now; production injection uses S; actual CRUD/history consumption uses accepted CRUD join; cache-backed reads use H snapshot seam | active API3 CRUD files excluded; no PUT entries invented; count/echo other domains call their exported ports; stop on unsupported dialect/order semantics, not change silently |
| **T — treatments across versions** | `lib/api/treatments/index.js`, `lib/server/treatments.js`; proposed tenant treatments adapter, collection migration and `tests/tenant-rest-treatments.integration.test.js`; all legacy methods + G3 | begin migration, normalized fixtures, rule/HTTP differential and adapter implementation now; import S's stable ports at integration; no dependency on profile/food completion | no shared write-intent edits without S; preserve duration/target-unit/validation/batch/retry behavior; stop for a new clinical/domain interpretation, duplicate policy or unrepresentable stored semantics |
| **D — devicestatus + activity** | corresponding legacy route/wrapper files; proposed tenant domain adapters/migrations and `tests/tenant-rest-device-activity.integration.test.js`; G3 devicestatus, legacy devicestatus/activity | start independently now with typed JSON and collection rules; depends only on S mount/seam at join | no v3 activity or legacy devicestatus PUT; do not couple prediction field registration to admission; stop if normalization loses extension data or requires a new write policy |
| **F — profile + food** | corresponding route/wrapper files; proposed adapters/migrations and `tests/tenant-rest-profile-food.integration.test.js`; current/plural/quickpick legacy reads, edits and G3 | start schemas, nested JSON, order/pruning and cross-version tests now; S injects completed ports | no owner-config editing, profile meaning rewrite or universal timestamp policy; stop on ambiguous current-profile ordering/pruning representation |
| **H — identity/status/settings/derived reads** | `lib/authorization/endpoints.js`/extraction seam with S coordination; `lib/api/status.js`, `verifyauth.js`, `adminnotifiesapi.js`; v2 properties/summary/data endpoints; API3 specific routes; proposed settings document adapter, tenant snapshot service and `tests/tenant-rest-context.integration.test.js` | safe status/exchange/discovery, credential characterization and settings schema begin now; snapshot bridge can be developed against existing normalizers and synthetic collection ports; derived HTTP joins require E/T/F reads; authority mutations wait only for their own persisted mutation contract | no active CLI/exchange rewrite, service authority elevation, process env exposure, enabling owner/operator roles; management X rows are separate subdeliverable, not prerequisite for H reads |
| **N — notifications/assistant compatibility** | notifications v1/v2, assistant router adapters, tenant receipt/sandbox/egress ports; proposed `tests/tenant-rest-side-effects.integration.test.js` | fake-provider and tenant runtime characterization can start now; actual admission requires H snapshots and persisted receipt/authority services as applicable | no remote production sends or connector role enablement; stop when durable receipts, callback trust or egress provenance lack an approved contract; keep only those rows excluded |

The first implementation wave should be **S + E/T/D/F**, alongside uninterrupted existing
CRUD and runnable CLI work, with H's safe status/identity and snapshot work in parallel.
N may begin fake-provider characterization but is not on the data-preview critical path.
These are bounded packages, not an instruction to launch a workflow or dozens of agents.
At each delivery join integrate whichever collection is complete and advertise only its
tested routes. A useful preview does not wait for admin/assistant egress.

### Per-package acceptance: behavior, not document production

Each package must drive its listed **actual HTTP methods**, both successful and refused,
through the composed tenant application with real PG/RLS and persisted current authority.
Use single/Mongo shipping handlers as a differential oracle with normalized synthetic time/IDs;
normalize only transport nondeterminism, not bodies, ordering, outcome count or status differences.
Use two tenants sharing external identifier spellings; inspect stored rows, headers, history,
attribution and committed events. Test legacy v2 inheritance, suffixes, HEAD/OPTIONS and
unknown routes as well as v1/v3. For every write domain cover:

* valid create/read/edit/delete routes actually present; single and arrays only where shipping
  accepts them; default and opted-in item replies; a successful extension-field round trip;
* same request resent, identifier/_id collision, duplicate race and rollback; mixed failures
  where legacy batches permit them, without upgrading all batches to atomic transactions;
* current grant/role/revocation/rename changes after JWT issuance; anonymous reads only when
  tenant policy permits; denied anonymous writes, invalid credential and exact subject attribution;
* cross-version read/history/lastModified after legacy writes, tombstones/permanent delete,
  tenant-local pruning, cache invalidation and restart; data in tenant B remains unchanged;
* known service outage versus invalid submitted data versus internal fault, using that route's
  approved status contract; no credential/error payloads in logs or response bodies.

**Red controls are part of coding:** remove/bypass the newly added admission or intent seam
and require an actual HTTP success test to fail; cross-wire the tenant binding in a synthetic
owned fixture and require row/cache/event isolation to fail; freeze current authority or
drop attribution and require revoke/rename tests to fail. For query support, change the
translation of one exercised operator/order and require differential results to fail.
For N, wrong-tenant receipt routing must fail a fake-provider assertion; for H, inserting a
synthetic sentinel into process-only configuration must fail a non-disclosure assertion.
Record exact failure symptoms, restore the source and rerun. A suite that passes because its
routes remain refused, fixtures fall back to Mongo, or opt-in suites are skipped proves nothing.

Reuse existing focused instruments rather than rewriting the oracle:

| package | existing CRM tests to extend/reuse |
|---|---|
| S/E | `tests/tenant-credential-http.integration.test.js`, `tests/tenant-entries-http.integration.test.js`, `tests/api.entries.test.js`, `tests/api.count-parameter.test.js`, `tests/api.count-where.test.js`, `tests/api.v1-read-refusal.test.js`, `tests/api3.v1-writes-history.test.js` |
| T | `tests/api.treatments.test.js`, `tests/api.same-time-treatments.test.js`, `tests/api.treatments.resend-reply.test.js`, `tests/api.treatments-write-validation.test.js`, `tests/api.treatments-tt-units.test.js` |
| D | `tests/api.devicestatus.test.js`, `tests/api.devicestatus.resend-guard.test.js`, `tests/api.devicestatus.identifier-match.test.js`, `tests/api.activity.test.js`, `tests/api.activity-date-coercion.test.js` |
| F | `tests/api.profiles.test.js`, `tests/api.profiles.resend.test.js`, `tests/api.food.test.js`, `tests/api.food.quickpicks.test.js`, `tests/api3.history-restart.test.js` |
| H/N | `tests/api.status.test.js`, `tests/api.verifyauth.test.js`, `tests/api.security.test.js`, `tests/api3.settings-read-scope.test.js`, `tests/tenant-jwt-http.integration.test.js`, `tests/tenant-runtime-vault.integration.test.js`, `tests/api.alexa.test.js`, `tests/api.googlehome.test.js` |

For actual client compatibility, prioritize synthetic uploader/retry/read workflows for entries,
treatments, device status and profile. `tests/api.aaps-client.test.js` and
`tests/api3.aaps-patterns.test.js` are existing client-pattern instruments. Pin the relevant
client source revision before extracting another workflow; a source-derived client pattern is a
hypothesis until replayed through HTTP. Do not claim real-client acceptance from parser unit
tests or assume API3 conventions satisfy a v1 uploader. Replay retained extension fields and
retry responses, not private client data/configuration.

### Execution and integration order

1. Start clean domain worktrees from the accepted cumulative base; pin source and characterize
   the owned legacy/G3 family against Mongo. Implement domain schemas/adapters and tests while
   S makes the narrow legacy injection exports. Domain tests may inject completed exported
   ports, but must later pass through the real integration mount before admission is claimed.
2. Join existing CRUD and CLI deliveries when accepted. S reconciles their shared surfaces
   once, preserving their tests; teams rebase/merge only clean accepted commits. Land E/T/D/F
   independently with scoped capability admission and real-provider HTTP tests. No blanket
   `enabledCollections` switch, `NS_TEST_BACKEND=postgres` availability switch or broad
   permission wildcard as a shortcut.
3. Join H's snapshot/credential/status work; expand cache-backed/derived reads only after their
   cross-tenant tests pass. Implement authority administration and N side effects as their own
   bounded capabilities. Excluded endpoints remain visibly excluded until delivered.
4. At coherent delivery joins, run the full established suite and browser/client workflows,
   then the existing PR check last. Parent records acceptance once; do not manufacture a
   packet dependency before each collection can code or test.

Representative existing commands, run in the implementation worktree with its owned test
environment (not executed for this design):

```bash
# Example targeted legacy baseline; substitute the package's existing/new focused files.
node bin/with-env.js ./my.test.env node_modules/mocha/bin/mocha.js \
  --fail-zero --timeout 10000 --require ./tests/hooks.js --exit \
  tests/api.entries.test.js tests/api.count-where.test.js \
  tests/api3.v1-writes-history.test.js

# Existing real-provider HTTP instrument: opt in, never count a skipped suite as a pass.
NS_TENANT_CREDENTIAL_HTTP_DOCKER_TEST=1 node bin/with-env.js ./my.test.env \
  node_modules/mocha/bin/mocha.js --fail-zero --timeout 120000 \
  --require ./tests/hooks.js --exit tests/tenant-credential-http.integration.test.js

# At the coherent integrated join, not after every documentation or isolated adapter change.
npm run test:tiers
npm run test:all
npm run test:browser
# After fetching/merging official/dev and rerunning affected/full tests:
tools/review/prcheck/prcheck.sh
```

New tenant integration tests must expose explicit opt-ins as the existing instruments do,
be assigned in the tier/census registries by S, and report missing providers as skipped/
UNMEASURED, never silently use the dormant lab in place of actual admission. Preserve
single/Mongo tests and source controls at every join. Do not install dependencies or run broad
tests merely to validate this document.

## 6. Completion gate for the full REST goal

S adds a focused executable route-matrix regression test in CRM as the implementation evolves:
enumerate the **actual mounted router graph** with its configuration predicates and compare
against the families in §2. Exercise each expanded family/method over HTTP for one authorized
success and its relevant refusal; distinguish native methods, implicit HEAD/OPTIONS, prefix
redirects, inherited v2 and disabled conditional integrations. An unknown collection/method
must not acquire permission or storage merely because the generic code exists.

Do not write a constants-only inventory test. Its negative control adds a synthetic mounted
route with no matrix case and must fail; remove a mapped mount and require an exercised HTTP
case to fail. Turning off provider opt-ins or skipping backend fixtures must make the
completeness report incomplete. Existing source fixtures with dormant PATCH routes are not
evidence that the real credential bridge admits PATCH.

The full v1–v3 target is complete only when:

* every unconditional matrix row is tenant-implemented and verified, and every shipping
  conditional family either has its tenant capability implemented/tested or an explicit
  approved product disposition; "preview excluded" alone does not close it;
* Mongo-compatible semantics and explicit tenant differences have actual HTTP evidence for
  parsing, credentials, response/status/headers, queries, retries, batches, writes and history;
* persisted authority, PG/RLS, shared identity collisions, tenant snapshots/events and restart
  controls pass without tenant/process secret leakage or fallback to single/Mongo;
* the runnable API process advertises and serves that measured breadth, with read-only
  readiness and owned shutdown; owner/private-operator roles remain separately authorized;
* the integrated full suite, relevant client/browser workflows and last-step PR check pass,
  with pending/unmeasured exclusions disclosed rather than counted green.

Production identity/transport provenance, HA, durable registry, activation/owner lifecycle,
realtime and connector/evaluator operation retain their own completion criteria. Completing
REST does not silently complete those programmes, and a useful partial preview does not
require waiting for them.
