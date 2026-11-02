# Nightscout multitenancy: next priorities, PostgreSQL RLS and Celld

**Assessment: 2026-11-02. Recommendations, not newly adopted decisions or
production acceptance.** Public `dev` was checked through GitHub and read from
the local `official/dev` ref at `61eb37335954ae42c91345a0823bd67331025165`.
No database, Celld fleet, client or failure experiment was run for this assessment.

**Maintainer follow-up:** Celld is now out of scope. The adopted
[delivery roadmap](../30-design/tenancy/multitenant-delivery-roadmap-2026-11-02.md)
supersedes the experimental recommendations below: storage first, one local
integration branch, headless owner API with UI deferred, operator-only lifecycle,
legacy per-tenant credentials, a reviewed settings subset and early Vault
feasibility work. Human identity and next-generation execution have separate
gates. The Celld section remains evidence of the evaluated alternative, not
scheduled work.

**Measured continuation:** the [roadmap's execution follow-up](../30-design/tenancy/multitenant-delivery-roadmap-2026-11-02.md#continuation-pooler-proof-and-typed-identity-primitive-2026-11-02)
now records 9 current-connection PgBouncer/DDL checks and 4 typed-identity
checks. The historical JSON key collapses ObjectId/string copies; the opt-in
typed-key candidate and dormant codec preserve both. This does not certify
the entries adapter, migration runner or hosted operation. Source identity
rules are at
`externals/work/crm-multitenant-20261102/lib/server/object-id-forms.js:82-106`;
the new codec is at
`externals/work/crm-multitenant-20261102/lib/storage/postgres-identity.js:13-38`.

**Migration continuation:** local upstream `68828b8d` adds the explicit
PostgreSQL-only operator runner, with atomic SQL/ledger commits, a pinned-client
advisory lock and read-only compatibility inspection. **39 migration/CLI checks
pass**, including 12 disposable-PG acceptance checks and failure controls.
See the [execution record](../30-design/tenancy/multitenant-delivery-roadmap-2026-11-02.md#continuation-explicit-postgresql-operator-migrations-2026-11-02).
MongoDB leases/resumability, production catalogues and serving-role wiring
remain open; the command does not change default server boot.

**Authorization decision, not implementation acceptance:** grant removal or
revocation applies at the next protected operation across workers, including
socket subscriptions/writes/protected delivery. Current authorization must be
available; unexpired JWTs and stale caches are insufficient. Already-authorized
operations are not retroactively undone. The control-plane/runtime slice still
owes an explicit authorization linearization point and race/outage tests.

**Entries continuation:** local upstream `7d4f3872` supplies a dormant
parameterized read/filter subset (`findFiltered`, `count`, `findOne`) using the
actual connection/identity modules. Six real PG/MongoDB differential checks and
four unit checks run in the **145-passing combined regression**; this is not
full M1. Regex/v1/dotted paths/projections, unsupported operands/types and
array/object sorting refuse, and results are materialized without cursor caps.
Writes/events/current indexes and backend registration remain absent. The
[bounded acceptance and reproduction record](../30-design/tenancy/multitenant-delivery-roadmap-2026-11-02.md#continuation-entries-readfilter-subset-2026-11-02)
distinguishes this measured slice from full client/API compatibility.

**Write continuation:** local upstream `7bcfc8b0` adds dormant inserts, scalar
patches and deletes through five persistence methods. Eight real PG/MongoDB
checks plus one refusal check cover stored results/counts, typed identities,
rollback, both tenants and actual two-connection lock contention. The combined
regression is **158 passing, no pending**; existing v3 write-intent tests in
that run remain regression evidence, not PG write-intent integration. A
stale-snapshot no-op comparison was corrected and three actual mutations fail.
Bulk/replace/every-form writes, constraint-specific retries and commit-event
integration remain; no backend is enabled. See the
[write acceptance record](../30-design/tenancy/multitenant-delivery-roadmap-2026-11-02.md#continuation-dormant-entries-writes-2026-11-02).
The other session owns migrations, settings/subject policy and provider-neutral
secrets/Vault-facing work; this slice leaves those files unchanged.

**Integrated continuation:** local merge `6943dccb` now joins the entries slice
with the parallel secrets branch (`a3888080`, `cbbe9179`, `fec19ba5`):
provider-neutral authorization/audit boundaries, Vault Transit, PG ciphertext/
audit persistence and maintenance-only rewrap/CAS. **230 focused tests pass
without pending**, including real Vault/PG, migration and entries checks
together; all **465 test files** classify. Unit/DOM/core/harness tiers pass
after building local bundles. The dependency tier remains non-green because
its unchanged `har-validator` assertion resolves old AJV outside the worktree.
See the [integration acceptance and parallel handoff](../30-design/tenancy/multitenant-delivery-roadmap-2026-11-02.md#integration-entries-and-vault-facing-secrets-2026-11-02).
The next isolated secrets objective is backup/restore and actual process-crash
acceptance; owner-policy APIs, MongoDB migrations and runtime consumers remain
unfinished. This is no backend promotion or production-Vault acceptance.

**Upsert/intent continuation:** local `14ae16db` adds measured merge-upsert,
replacement/batch/every-form subsets and a dormant shared v3 intent seam with
savepoint recovery and post-commit events. **878 integrated checks pass without
pending**; the changed 28 checks also pass against MongoDB 5.0.32 and 8.3.9.
V3 resend POST retains replacement behavior, not v1's merge behavior.
JSON-equal replacements owing exact modification counts refuse because JSONB
does not preserve BSON field order. Production DDL/import, full v1/socket and
route authorization/validation/current-grant wiring, bounds and backend suites
remain open. See the [bounded acceptance record](../30-design/tenancy/multitenant-delivery-roadmap-2026-11-02.md#continuation-entries-upserts-and-post-commit-v3-intents-2026-11-02).

**Latest recovery integration:** merge `0de90852` imports `78b915ab` without
runtime/migration/entries-source changes. The combined command passes **879
checks, zero pending**, including 34 secrets checks and actual PG dump/restore,
encrypted single-node Vault snapshot recovery and before-CAS/after-commit
worker SIGKILL/retry. Production recovery remains open. The next parallel
slice is the minimum policy/current-authority service, not more provider
features; see the [acceptance and handoff](../30-design/tenancy/multitenant-delivery-roadmap-2026-11-02.md#integration-secrets-recovery-acceptance-and-next-control-plane-slice-2026-11-02).

## 1. Bottom line

The next useful delivery is **an entries-first PostgreSQL RLS slice on current
dev**, alongside a **tenant configuration/authentication integration workstream**.
Neither needs to wait for the v16 tag to conduct synthetic, isolated experiments.
Do not reopen the v16 merge list just to land multitenancy.

Celld is worth a bounded **tenant actor/scheduling/realtime experiment**, not an
immediate replacement for PostgreSQL or the Nightscout Node server. PostgreSQL
addresses shared-record authorization; Celld addresses durable actor execution
and placement. They can complement each other, but a hybrid adds a cross-system
commit/delivery boundary that must be proved, not assumed.

Retain D1-D4: first-class single-tenant MongoDB, and shared PostgreSQL with RLS
for the hosted target. A Celld/SQLite record-store alternative would be an
explicit architecture experiment, not an already authorized change to D2/D3.

## 2. What is actually blocking progress?

| Boundary | Evidence on current dev or in existing records | Next move |
|---|---|---|
| PostgreSQL adapter | `lib/server/storage-backends.js:21-27` registers MongoDB only. `tests/support/backends.js:58-65` explicitly marks PostgreSQL unavailable. A green run with storage tests pending is not a PG pass. | ST-PG can start: ST-HARNESS is merged. Implement the adapter against today's interface and write contract, entries first. |
| Hosted bootstrap | `lib/server/serve/roles.js:14-17` says no role is multitenant yet. `lib/storage/tenant-scope.js:34-40` distinguishes the merged binding seam from tenant resolution still to build. | TEN-RESOLVE and T30-WIRING must provide trusted request scope, per-tenant config and credentials before enabling `serve`. Do not remove the refusal as a shortcut. |
| Configuration and credentials | The config lab records 59 green tests and 77 red controls, but it is not integrated into dev. T30-SCHEMA-CRED is done on the old seam, not on dev. | Port the bounded schema and secrets/access-grant contract; settle only decisions necessary for the chosen milestone. Reuse MIG-RUNNER's existing buildable work item. |
| Legacy consumer compatibility | The headless API mounts v3 and the authorization router only (`lib/server/serve/api.js:36-42`); v1, pages and sockets are not supplied by that profile. | An API v3 storage spike is not an ecosystem-compatible hosted preview. Preserve v1/root-header and socket consumers in later acceptance, without requiring AID upgrades. |
| Evaluator and realtime | ST-VIEWS is merged but unwired. `lib/server/serve/roles.js:27-41` declares evaluator/realtime/connector/owner roles without start functions. D-EVENT defines an in-process event, not durable delivery between processes. | Prove tenant-local settings, plugin state, scheduling, acknowledgment/snooze and socket routing; choose interprocess delivery with the role design. |
| Operational acceptance | Existing PG/pooler measurements are from September seam commits. The hosted import plan is not a production migration rehearsal. | Re-run the relevant controls against the new integrated tree; prove backup/restore, tenant deletion/export, upgrade and rollback before real onboarding. |

Source paths in the table are relative to
`externals/cgm-remote-monitor-official/` **at `61eb3733`**, not its detached working
directory. These are implementation gaps, not evidence that RLS itself remains
an untested idea.

### Prior work to preserve, not repeat blindly

- The [PG backend measurement](../60-research/tenancy/t25-postgres-backend-verification-2026-09-15.md)
  exercised the actual old adapter and emitted schema, including 3,000 filter
  comparisons. It also exposed limit/order/projection/materialization issues.
  Those results do not certify a port to the current write/identity contract.
- The [pooler experiment](../60-research/tenancy/pgbouncer-tenant-binding-2026-09-15.md)
  demonstrated transaction-local tenant binding through real transaction
  pooling, including a shared backend and a red session-binding control.
  Statement pooling could not run the adapter. Its unregistered defect labels
  collide with later BF IDs; do not treat them as current register identifiers.
- The [configuration lab](../../tools/lab/tenant-config-schema/README.md)
  measures policy/floor/RLS behavior on PostgreSQL 16.15. Its October 27 schema
  predates October 29 decisions, including `tenant_access_grants` replacing
  `tenant_members`; the next integration must reconcile them.

### A coordination blocker: two generations of planning

At the initial assessment, the
[platform map](../30-design/platform/next-gen-platform-plan.json) had ST-PG,
TEN-RESOLVE and TEN-LAB without corresponding executable-work items in
`queue/work-queue.yaml`. The adopted roadmap has since added those queue items
and bounded M0/Vault checks. Their complete acceptance is still open.
The queue also carries older
seam-era dependencies; SEAM-REFRESH is blocked on the old release train.
The [current platform plan](../30-design/platform/next-gen-platform-plan.md#41-storage)
explicitly keeps that chain as reference, not a bulk merge.

Keep each assigned slice in the queue with its current-dev base, owner and
discriminating gate. Do not make a blanket
September-chain refresh a new prerequisite for ST-PG. Preserve completed
measurements, but do not infer that a platform-map card has a runnable queue gate.

## 3. Recommended independent workstreams

| Priority / stream | Bounded deliverable | Acceptance / stop boundary |
|---|---|---|
| P0: PG storage slice | Current-dev topic branch, entries adapter, emitted DDL and backend harness integration; explicit list of unsupported collections/operations. | Both stores execute the applicable cases, not pending PG storage tests; request/reply/stored outcomes cover filtering, paging, identity, resend, delete, null and batch semantics. Stop short of claiming a complete hosted site. |
| P0: tenant control plane | Reconcile T30 decisions, then config/credential/schema integration, resolver and per-tenant key wiring. | A's token succeeds on A and fails on B by signature; unknown tenant refuses; no process-env secret leaks into hosted config; owner/operator/data boundaries hold. Synthetic device tokens do not need a production human IdP. |
| P1: evaluator/realtime | Wire the computed view behind an experimental execution profile; define durable wake/reconnect and state ownership. | Equality with resident outcomes on relevant replay fixtures; tenant-specific units/thresholds/language; durable ack/snooze; no cross-tenant rooms or notifications. No live alert promise until the alarm gate passes. |
| P1: Celld feasibility | Two synthetic tenants, tenant-addressed actors, fake delivery sink, restart/failover and event-retry probes. Compare with a simple Node worker baseline. | Measure useful runtime benefit and integration cost; no real records, provider secrets, push delivery or release dependency. Reject a design that needs unsafe routing or a hidden second source of truth. |
| P2: hosted operations | Extend covered collections, import/export fidelity and repeatable migration/restore/rollback. | Full supported-client surface and failure acceptance before onboarding. Entries-only synthetic data needs no Mongo-to-PG migration first. |

BF-72/BF-161 remain in the separate private release/security workstream. They
are not prerequisites to a synthetic PG or Celld experiment; any later deployed
hosted build must incorporate the applicable fixes and validate its final tree.
nightscout/cgm-remote-monitor#8829 remains explicitly nonblocking for v16; it is
not promoted into a blanket tenancy research blocker.

### PG experiment: the smallest useful proof

Use two tenants with overlapping `_id` and `identifier` values, plus an unbound
bystander, against the real adapter. Exercise reads **and** inserts/updates/deletes.
Bind the tenant inside each transaction with `set_config(..., true)`, use
non-owner `NOSUPERUSER NOBYPASSRLS` application roles and forced RLS, and keep
migration privileges separate. Test missing scope, rollback and error cleanup
through a transaction-pooling PgBouncer with demonstrably reused connections.
Pair isolation checks with deliberate breaks so that zero rows cannot mean
the fixture never stored anything.

[PostgreSQL's RLS documentation](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
also limits the promise: superusers/BYPASSRLS bypass it, owners normally bypass
unless forced, and operations such as TRUNCATE are outside row policies.
RLS protects against omitted row filters under the trusted application's binding;
it does not authenticate the chosen tenant or make arbitrary tenant-controlled
SQL safe. Grants, parameterization and trusted tenant resolution remain required.

## 4. Where Celld fits, and where it does not

The primary docs retrieved November 2 describe **v0.6.2 beta**. These are vendor
claims and documented limits, not measurements made by this workspace.

| Question | Assessment |
|---|---|
| What does it provide? | Single-threaded Durable Object actors, each with SQLite; bucket-backed replication/ownership, timers, hibernatable WebSockets, queues and workflows. A scheduling alarm is a runtime callback, not verified Nightscout clinical notification delivery. |
| Can today's server simply run unchanged? | Not established. It targets the Workers programming model with partial Node compatibility. Containers are experimental. Express/socket.io/plugins and their dependencies need actual compatibility work; raw WebSocket support does not prove socket.io protocol compatibility. |
| Does it supply tenancy? | No account service, multi-tenant scheduler or managed ingress. The application still owns identity, authorization, tenant routing, quotas, secrets and egress policy. A cell per tenant is not RLS and is not authorization. |
| Can it retain PostgreSQL? | A Node/PG service can remain authoritative while an actor handles scheduling/fan-out over a narrow interface. Celld has TCP support but no Hyperdrive; direct PG-driver compatibility is not demonstrated here. Keep direct SQL out of the first spike. |
| What changes operationally? | TLS terminates outside Celld; peer HTTP is plaintext, so use a private/encrypted network. Bucket semantics, fleet credentials and an appropriate restarting supervisor are part of correctness. No placement/jurisdiction guarantee is supplied. |
| What survives failure? | Docs claim acknowledged writes survive according to the durability mode and required bucket/follower conditions. Recovery can block for missing or uncertifiable tails. Socket transports do not move with cell ownership; clients must reconnect. This is not a no-outage or exactly-once-notification guarantee. |
| Why not replace PG with per-tenant SQLite now? | That is a different storage architecture, requiring query/write fidelity, migration, export, fleet isolation and cost evidence. September's per-tenant WiredTiger cost does not measure Celld SQLite, so it neither proves nor disproves this alternative. |

### Celld spike gates

1. Derive actor addressing from an **authenticated, authorized immutable tenant
   ID**, not a caller-selected cell name. Reject forged cross-tenant routing;
   verify each tenant's own positive case.
2. Use synthetic committed-event envelopes with stable operation IDs. Exercise
   duplicate and out-of-order delivery, suspension, restart and owner loss.
   Queues are documented as at-least-once and unordered; one queue has one writer.
3. Keep PG as the record authority for the hybrid arm. Demonstrate the
   commit-before-publish crash gap explicitly. An in-process commit event followed
   by a queue send is not atomic; durable replay/outbox/CDC semantics need a
   separate choice consistent with D6 and D-EVENT before promotion.
4. Persist scheduling/ack state and distinguish an unacknowledged client retry
   from a proven failed write. A timeout does not imply the original effect
   did not happen. Fake external effects must expose duplicate attempts.
5. Test a qualified bucket and the documented supervisor/fencing setup, socket
   reconnect and full stopped-fleet restore. Measure latency, recovery delay,
   resident/idle cost, object-store operations and noisy-neighbor impact.
   Published headline density/pricing is not a Nightscout capacity estimate.
6. Avoid renaming the Worker/script as an innocent deployment change:
   `idFromName()` incorporates script/class identity; docs say a script rename
   reaches new empty objects. Record identity and upgrade constraints.

**Recommendation:** PG integration is the primary progress track; Celld gets a
small parallel feasibility budget only if someone owns the runtime experiment.
Do not wait for production human-login/edge compliance to run synthetic storage
tests, or mistake those tests for permission to accept real identities/data.

## 5. Evidence and limits

- Current-dev source references above were read with `git show official/dev:...`;
  the GitHub commits API independently returned the same full SHA.
- State/dependencies: `queue/work-queue.yaml:5952-6055,6086-6123,6208-6280`;
  `docs/30-design/platform/next-gen-platform-plan.md:140-152,203-221`;
  `docs/30-design/platform/next-gen-platform-plan.json:592-605,662-711`.
- Configuration decisions:
  `docs/30-design/tenancy/tenant-config-schema-2026-10-27.md:454-494`.
  The October census's 264 settings are a dated measurement, not a fresh count
  against November 2 dev. Re-census before asserting complete settings coverage.
- Celld primary sources: [limitations](https://celld.dev/docs/limitations/),
  [runtime compatibility](https://celld.dev/docs/cloudflare-compat/),
  [Durable Objects](https://celld.dev/docs/services/durable-objects/),
  [guarantees](https://celld.dev/docs/guarantees/),
  [queues](https://celld.dev/docs/services/queues/).
  Retrieved web docs are unpinned; pin a binary/source revision for an experiment.

No experiment acceptance, ownership assignment, new release prerequisite or
architecture reversal is inferred from this assessment.
