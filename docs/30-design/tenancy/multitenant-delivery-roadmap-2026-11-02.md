# Multitenant delivery roadmap: current-dev integration

**Adopted direction, 2026-11-02.** One local upstream integration branch,
`workspace/multitenant-20261102`, starts at official dev `61eb3733`.
No upstream push is authorized in this session. Keep merging later dev changes
into the integration branch, not rebasing shared work. PRs may later split into
reviewable slices. Alignment records may be published separately.

Celld is **out of scope**. This supersedes its proposed feasibility workstream
in the [priorities assessment](../../10-domain/nightscout-multitenancy-priorities-deep-dive.md).
The assessment's current-dev findings still apply. No multitenant work reopens
v16's release merge list.

## 1. Owner journeys and supported boundary

The supported deliverable is a **headless, documented, versioned tenant-owner
API**, with conformance tests independent of vendor UI. A first-party hosted
owner UI is deferred, not prohibited. Vendors may build UI; they must not bypass
Nightscout's validation/floors or put an all-tenant service credential on the
owner's request path. Existing single-site behavior stays unchanged.

The initial tenant lifecycle is operator-only: provision, suspend, export and
delete through the private operator plane, never public signup. Export and
deletion have different audiences: an owner may export or request deletion;
the operator authorizes and executes lifecycle deletion. A deletion request
is not permission to bypass confirmation, retention or recovery policy.

Before a hosted preview, the selected owner use cases are:

| Journey | Contract needed | Delivery boundary |
|---|---|---|
| Understand configuration | Effective value, source/default/pin/constraint, stored owner value and explicit ignored/rejected reasons | First config slice; no raw secrets in reads |
| Change display, units and timezone | Reviewed typed catalogue, validation, version/precondition, audit attribution, live invalidation and rollback | Small catalogue first, not all historical environment settings |
| Manage uploaders/followers | Tenant-local subjects, roles, root and subject-token rotation/revocation | Preserve legacy credential forms; explain root versus least-privilege tokens |
| Configure connectors/push targets | Typed integration kinds, bounded egress and tenant-owned secret references, split operator/owner credential parts, health status | Enable a kind only when its consuming runtime passes its gate |
| Export and request deletion | Tenant-local export, request/confirmation status and operator execution | No cross-tenant rows or secret plaintext in exports |
| Change alarm settings | Preview/confirmation, complete ordered thresholds, correct units, evaluator version and invalidation | Hidden/unavailable until multitenant alarm acceptance |

Controller registration, command/intent execution and delegated access have
separate later journeys. Choosing these owner capabilities does not imply
their runtime is already implemented.

## 2. Configuration and authentication decisions

Retain D22: code floors > operator default/bounds/pins > permitted owner values.
Initially offer only a reviewed catalogue; refuse unsupported names explicitly.
Start with units, timezone, display preferences and authorization policy.
Deployment/runtime values remain in each role's environment; credentials are
never settings. Re-census current dev before claiming full catalogue coverage.
Detailed names, API paths and optimistic-concurrency/error shapes are design
outputs of MT-CONFIG-MIN, not silently chosen here.

**Continuation decisions (November 2):** include owner-editable authorization
policy in the first slice: tenant-local subject grants and bounded token
lifetimes, under the code/operator floors. Mandatory authentication, tenant
isolation and operator access cannot be weakened by an owner. Exact permission
names, lifetime limits, revocation/invalidation and API cases remain contract
outputs, not implemented settings.

**Revocation decision (November 2 continuation):** grant removal or token
revocation takes effect on the **next protected operation across workers**.
That operation checks current authorization and refuses if it cannot establish
current state; an unexpired JWT or cached earlier grant is not sufficient.
Socket writes, subscription changes and protected stream delivery must obey the
same boundary, removing/closing revoked access rather than waiting for token
expiry. An operation already authorized/in flight is not retroactively undone.
The implementation must define its authorization linearization point and test
revocation races, worker-local cache invalidation, reconnect and authorization
store outages. No bounded stale-permission window is adopted. This is a contract
decision, not a claim that current sockets or auth code implement it.

Preserve hashed `api-secret` headers, subject tokens and socket secret forms
using **each tenant's** root credential. Resolve and authorize the tenant before
credential verification; per-tenant JWT signing keys remain per-tenant. There
is no process-wide hosted `API_SECRET`. The owner's root is not a claim that
every uploader should receive owner permissions.

Device/token/root credentials come first. Human login needs a separate plan:
interchangeable identity provider, verified provider/subject, access grants,
tenant-bound token exchange, session/re-authentication/revocation and edge
acceptance. No custom username/password/recovery system. A token-authenticated
config audit names its verified subject or root-credential principal; it must
not invent a verified human identity.

## 3. Secrets: preserve the prior compromise, measure Vault first

The [execution plan](nightscout-multitenancy-execution-plan-2026-09-14.md)
at lines 973-1040 already adopts:

- one secrets component, including sign/verify and logged reveal;
- signing keys never exported from it;
- a built-in encrypted signer for development/small operators;
- Vault Transit and cloud-key-service production adapters behind the same
  contract; the built-in master key stays outside the application database.

The maintainer asks to try Vault integration early if feasible, rather than
assuming a built-in signer is the faster path. Execute a bounded Vault Transit
lab before deciding implementation order. Do not equate cryptographic API
availability with a production-reviewed integration.

Transit encrypts/signs but **does not store submitted application data**.
The design still needs tenant-bound ciphertext/reference storage, authenticated
consumer authorization, scoped provider credentials, rotation/version handling,
outage policy and audit redaction. Scope storage and data keys to tenants;
ordinary consumers cannot choose another tenant's key path. An owner reveal is
an explicit audited operation, never a generic decrypt on the data API.

The first lab uses only disposable synthetic keys/payloads. A Vault development
server can establish API/ACL/key-lifecycle feasibility, not persistence, TLS,
unseal/recovery, HA, production auth or operational suitability. Record the
image digest and the checks that remain. Failure is explicit; never fall back
to plaintext, another tenant's key or an unapproved local signer.

## 4. Milestones and continuous integration

| Milestone | Build / dependencies | Acceptance before promotion |
|---|---|---|
| M0: foundations | Current-dev integration worktree; PG connection/transaction binding and real RLS proof; migration and secrets contracts can proceed independently | Non-bypass application role, overlapping IDs, unbound reader, read/write isolation, rollback/error cleanup, demonstrated pool reuse and paired breaks. No hosted role enabled. |
| M1: entries adapter | ST-PG, on the M0 binding; current filter/read/write/identity contracts; reviewed DDL managed through MIG-RUNNER before deployment | Applicable backend tests execute against both stores; no pending-as-pass. Explicit unsupported collections/operations. Include null, ordering/pagination, resend/delete and batch outcomes; preserve source labels/events. |
| M2: tenant control plane | MT-CONFIG-MIN, MT-SECRETS-CONTRACT, MIG-RUNNER, TEN-RESOLVE, T30-WIRING | Tenant-local effective config and versioned writes; unknown tenant refuses; A token works on A and fails on B by signature; no environment/root/key leakage; separate owner/data/operator routes. |
| M3: two-tenant HTTP lab | M1 + M2, TEN-LAB | Real authorized entries v3 requests and stored outcomes for both tenants, positive and negative controls; startup refuses stale/unsafe schema. Not yet a complete hosted preview. |
| M4: existing-client surface | M3; further collections and v1/storage wiring; v2 exchange; tenant-local history and indexes | v1 and v3 uploader/follower shapes exercised on pinned versions; no coordinated app upgrade requirement; tenant-local identity and correct batch/retry/refusal semantics. |
| M5: realtime and evaluator | MT-RUNTIME-PLAN; computed views; durable interprocess event delivery/recovery; settings/secrets consumer integration | Socket authorization/reconnect/write compatibility, tenant-local rooms and caches, replay-equivalent views, durable ack/snooze, restart/double-delivery checks; live notification gate remains separate. |
| M6: hosted preview | M4 + M5 + chosen owner capabilities and hosted operations | Export/deletion, import fidelity, backup/restore, upgrade/rollback, bounded resource/egress policies and final-tree review. Real-data/identity acceptance is explicit, never inferred from lab success. |

CI is cumulative, not a calendar: keep default MongoDB/single tests green,
add explicit PG jobs only as their applicable suites execute, and preserve a
visible unsupported/pending inventory. Each isolation property has a red
control, with positive own-tenant behavior, against the actual implementation.
M0 does not certify M1, and M3 does not certify M6.

MIG-RUNNER can begin now; MIG-VV is already done. Build the runner against
both stores with lock/ledger/drift/restart semantics from the measured lab.
Hosted roles refuse stale schemas. Do not add a new default single-site boot
migration behavior to the v16 candidate without its own placement/review.

The maintainer selects **explicit operator-run hosted migrations**; serving
roles check schema compatibility but do not migrate it. This does not revise
the separately planned single-site boot behavior or change today's boot.

Interprocess event delivery is a named design task: D-EVENT's in-process
`storage-intent-committed` is not a durable bus. Reconcile D6's PG feed design
with it, with a durable checkpoint/replay story and explicit ordering,
duplication, deletion and configuration invalidation semantics before wiring
distributed evaluators. A timer may drive time-based alarms, not silently
repair lost write events.

## 5. Next-generation contracts proceed in parallel

| Track | Can progress independently | Hosted/runtime prerequisites |
|---|---|---|
| Registration and instance identity | Definition/catalogue/conformance and single-mode slices | Tenant-scoped storage, owner-action routing, lease/source-of-record conflicts and compatibility projections |
| Intent/command queue | Typed envelopes, lifecycle/status, expiry/cancellation, audit and replay tests | Authorized destination, registered instance where required, durable queue state, idempotency/reconciliation and tenant-local delivery |
| Delegation | Use-case/permission/consent model, bounded grants, revocation/audit design | Human identity/access-grant plan, owner authorization and independently reviewed command authority; no implicit grant from a device token |

None is a blanket prerequisite to the first storage/HTTP lab or a reason to
delay v1/v3 compatibility. The hub observes and routes; the AID controller
remains responsible for its dosing decisions and reconciliation.

## 6. Queue and execution record

New queue items ST-PG, TEN-RESOLVE and TEN-LAB give the existing platform cards
an executable-work index. MT-CONFIG-MIN scopes the initial subset without
claiming the full T30-SCHEMA-CONFIG catalogue complete. T30-WIRING's current-dev
slice follows TEN-RESOLVE and the secrets contract; old seam evidence is retained.
MT-RUNTIME-PLAN and MT-NEXTGEN-PLAN cover the explicit design outputs above.
Do not delete or bulk-refresh shared old worktrees.

Implementation results and commands are appended after measurement. No complete
adapter, production secret backend, client compatibility or hosted acceptance
is claimed by adopting this roadmap.

### Execution evidence (2026-11-02)

**Upstream local commits `27f085c93ad3f1eaef2bfcecc5cfa8544f2036d5`
and `ce14d637` (explicit connection-URI guard)** on
`workspace/multitenant-20261102` adds `pg` 8.23.1 and a dormant
`lib/storage/postgres-connection.js` foundation. It opens a tenant-bound
transaction, binds with `set_config(..., true)`, joins same-tenant nesting,
rolls back errors, refuses use after release and discards a connection if
rollback fails. A caught SQL error cannot turn PostgreSQL's aborted-transaction
`COMMIT` response into success. The store rejects superuser/BYPASSRLS application
connections. No backend registry or `serve` availability flag is changed.

Measured on PostgreSQL **16.15** and disposable MongoDB 8.0: **43 focused checks
pass**, including **9 PG foundation checks**, across:
`tests/postgres-connection.test.js`, `tests/storage.tenant-scope.test.js`,
`tests/storage-backend-selection.test.js` and `tests/test-backends.test.js`.
ESLint passes for the new module and test. Changing the actual binding call
from transaction-local to session-local made the cleanup check fail; restoring
it passes. The test probes the same pooled backend after commit/rollback,
not merely a new unbound connection. RLS-disable and session-binding controls
also demonstrate the exposure.

**Limits:** this is M0 progress, not the complete M1 adapter or even full M0
promotion. The test uses a synthetic entries-shaped table, not a newly reviewed
generated production migration. PgBouncer revalidation, entries methods/filter
translation, write-contract/backend suite integration and the migration runner
remain. The original PG backend availability remains false; no hosted role
starts. The first regression attempt lacked the project's test environment and
failed; the corrected run used `NODE_ENV=test` and an owned synthetic MongoDB.

**Vault:** [the persisted lab result](../../../tools/lab/vault-transit/results.json)
records **9/9 checks** on Vault **2.2.1**, image
`hashicorp/vault@sha256:962a92876e168d68eaaa24b0b8b49bbce1cb63024060a67bba95cd158a366fc2`.
Scoped encrypt/decrypt, HMAC verification (including wrong-tenant key),
non-exportability, denied key mutation, rotation/rewrap, token revocation and
the overbroad-policy control pass. The first run exposed an incorrect harness
assumption: this server's HMAC encoding is versioned base64, not hex.
The corrected check verifies a 32-byte result.

Vault's cryptographic feasibility supports proceeding with a Vault-facing
adapter contract instead of presuming the built-in signer must come first.
It does **not** establish comparative implementation efficiency, Nightscout
JWT compatibility, least-privilege tenant/consumer integration, ciphertext
storage or production operational acceptance. The built-in option remains
available; it was not implemented or removed.

### Reproduction and maintainer push command

Worktree: `externals/work/crm-multitenant-20261102`.
Install its locked dependencies with `npm ci --include=dev --ignore-scripts`.
For the focused suite, set `NODE_ENV=test`, `MONGODB_URI` to a disposable
test database whose name contains `test`, and `NS_TEST_POSTGRES_ADMIN_URI`
to a disposable PostgreSQL admin connection. Do not use a production database.

```sh
cd externals/work/crm-multitenant-20261102
npx eslint lib/storage/postgres-connection.js tests/postgres-connection.test.js
node_modules/.bin/mocha --fail-zero --timeout 15000 --exit --require ./tests/hooks.js \
  tests/postgres-connection.test.js tests/storage.tenant-scope.test.js \
  tests/storage-backend-selection.test.js tests/test-backends.test.js

# Only the maintainer runs this after review; no upstream push was made here:
git push bewest workspace/multitenant-20261102
```

MT-IDENTITY-PLAN names the separate human-identity design work. The initial
configuration slice still owes its exact setting names, paths, preconditions
and executable API cases; documenting the journey is not claiming that API
already exists.

### Continuation: pooler proof and typed identity primitive (2026-11-02)

The reproducible [pooler/DDL lab](../../../tools/lab/postgres-foundation/README.md)
and [sanitized results](../../../tools/lab/postgres-foundation/results.json)
exercise the actual connection module, not the September adapter. PostgreSQL
**16.15**, PgBouncer **1.25.2**, transaction pooling with one backend and no
per-transaction reset: **9 foundation checks pass**. Two independent clients
execute 24 interleaved tenant transactions on a measured single server PID.
Reads/writes, rollback, binding cleanup, unbound readers and dirty/null/missing
generated-column values pass. Disabling RLS, granting BYPASSRLS and mutating the
actual connection module to session-local binding demonstrate the failures.
The historical emitted entries DDL applies unchanged.

**A discovered M1 blocker, not a passing adapter test:** the current
`externals/work/crm-multitenant-20261102/lib/server/object-id-forms.js:82-106`
returns both an ObjectId and the same-spelling string. Ordinary JSON
serialization collapses them, so the historical `(tenant_id, _id)` DDL rejects
the second stored form with `23505`; raw Extended JSON instead fails its
generated string key with `23502`. The maintainer explicitly requires preserving
the distinction from the first adapter slice, not deferring it to import.

**Local upstream commit `6b1bf889a275b52bd119d122553bceb717e06ca9`**
adds the dormant identity codec:
`externals/work/crm-multitenant-20261102/lib/storage/postgres-identity.js:13-38`.
It keeps kind metadata outside the JSON document and reconstructs the original
ObjectId/string; unsupported/corrupt identities refuse rather than coerce.
The existing emitter now offers **opt-in** `--identity-kinds`
(`tools/nsschema/emit/postgres_emit.py:284-318`), producing the lab candidate
key `(tenant_id, id_kind, _id)` and kind/encoding constraints. The normal
generated production-shaped files are unchanged. This is a migration candidate,
not a boot-time schema modification.

**4 real-PG identity checks pass** using that generated candidate and actual
codec: both forms in both tenants, case/custom-string preservation, kind-scoped
deletion and constraint refusals. Flattening the actual codec's kind recreates
the collision; the restored codec stores both. **65 focused upstream checks**
pass across six files with disposable PG/MongoDB, plus ESLint and test-tier
classification. Both new PG files are now in their appropriate test tiers.
The schema pipeline has **291 passing tests**, including unchanged default DDL.
One attempted regression run omitted the required MongoDB environment; the
corrected isolated PG/MongoDB run is the reported green result.

**Still open:** this is not the entries collection adapter, arbitrary BSON
import fidelity, filter/sort parity, durable events or migration-runner
acceptance. The historical DDL also lacks current v3 `srvModified`/`isValid`
indexes and the tenant-scoped partial unique identifier index. Those unsatisfied
properties stay visible in the report's `adapterBlockers`; the separate
`identityChecks` prove only the typed candidate. No backend availability flag,
hosted role or single-site behavior changes. No upstream push was made.

**Next implementation, without another architecture vote:** integrate the
typed identity into entries reads/writes and emitted migration plans. Preserve
the current choice among identifier matches and ObjectId/string copies, not
only their stored keys. Translate identifier-constraint collisions specifically
and preserve retry outcomes without continuing an aborted PG transaction.
Exercise the current filter/null/array/order/pagination, resend/delete/batch and
source/event contracts before marking M1 accepted. Do not copy the old SQL
compiler or registry availability flag as a shortcut.

**Parallel:** build MIG-RUNNER with explicit hosted operator execution; complete
the minimum settings/subject-policy API and provider-neutral secrets contract.
The recommendation is the Vault-facing adapter next, retaining the built-in
option—not a claim that Vault is cheaper, more efficient or production-ready.
Human identity, evaluator/events and next-generation execution remain separate.

### Continuation: explicit PostgreSQL operator migrations (2026-11-02)

**Local upstream commit `68828b8d`** adds the PostgreSQL-only MIG-RUNNER
foundation using Umzug **3.8.3**. An explicit `nightscout migrate
<up|status|check>` command takes a reviewed, checksummed JSON catalogue, a
non-system namespace and an explicitly named connection environment variable.
No production catalogue is supplied. `--direct` is the operator's assertion
that the endpoint is not a transaction pooler; it is not automatic detection.

`externals/work/crm-multitenant-20261102/lib/migrations/postgres.js:105-164`
uses one pinned direct client and a namespace-specific session advisory lock.
Each migration's SQL and ledger row commit in the same transaction. Read-only
status/check operations neither create schema nor acquire the migration lock;
stale checks, unknown history, checksum drift and non-prefix history refuse.
The catalogue validation is at
`externals/work/crm-multitenant-20261102/lib/migrations/catalogue.js:19-38`;
checksums detect drift, not catalogue authenticity or review.

**39 checks pass**: 5 migration unit checks, 12 disposable-PostgreSQL acceptance
checks and 22 existing CLI checks. These include four overlapping runners,
bounded lock wait, rollback, SIGKILL/restart, explicit connection configuration,
read-only/restricted-role inspection, drift/history refusals and a split-commit
control that demonstrates committed-but-unrecorded DDL. ESLint reports zero
errors and two filesystem-path warnings. Reproduce in the upstream worktree:

```sh
NS_MIGRATION_DOCKER_TEST=1 node_modules/.bin/mocha --timeout 30000 \
  tests/migrations.test.js tests/postgres-migrations.integration.test.js \
  tests/nightscout-cli.test.js
```

**MIG-RUNNER remains in progress:** MongoDB's fencing-safe renewable lease and
resumable steps, real reviewed catalogues/baselines, rollback/export policy,
catalogue distribution/authenticity and serving-role compatibility wiring are
not implemented. Default single-site MongoDB boot is unchanged; no hosted role
or storage backend is enabled and no upstream push was made.

### Continuation: entries read/filter subset (2026-11-02)

**Local upstream commit `7d4f3872`** adds dormant `findFiltered`, `count` and
`findOne` methods. They use the actual tenant-bound connection and typed
identity codec, not the old adapter. The strict filter AST compiles top-level
scalar comparisons, `in`/`nin`, existence and a bounded type subset into
parameterized SQL. ObjectId/string `_id` comparisons retain their kinds;
scalar fields retain MongoDB type brackets, null/missing and array-element
matching. Text comparison uses byte ordering rather than the database locale.

Source:
`externals/work/crm-multitenant-20261102/lib/storage/postgres-filter.js:82-229`
and
`externals/work/crm-multitenant-20261102/lib/storage/postgres-entries-read.js:49-98`.
**6 real PG/MongoDB differential checks** compare results and counts across a
filter matrix, seven sort specifications with skip/limit, nine `findOne`
identifiers with normalized/raw output and empty projections, and overlapping
tenant fixtures. A SELECT-only non-bypass role reads the typed generated
entries table; tenant B's different values expose accidental leakage.
An unbound read refuses. **4 unit checks** exercise unsupported-input refusals
and bound field names/values. The test DDL fixture is byte-identical to
`tools/lab/postgres-foundation/generated/entries.sql` (SHA-256
`0460c76bed932b35472595745491fb61ae918cc6ff4b403b51ba0cc9cffa6a69`);
it is still an experimental typed-key schema, not a production catalogue.

**Combined integration acceptance: 145 passing, no pending**, across 12 files:
the new read/filter and migration checks, existing PG connection/identity,
MongoDB filter semantics, tenant scope, backend selection/harness and CLI
tests. This run used owned disposable PostgreSQL 16 and MongoDB 8.0 with
`NODE_ENV=test`, the project hooks and both database URIs. ESLint has no errors;
the migration slice retains its two filesystem-path warnings. All 461 test
files are classified. Owned containers and private credentials were removed.

Reproduce the read/filter portion from the upstream worktree with
`NS_TEST_POSTGRES_ADMIN_URI` and `CUSTOMCONNSTR_mongo` pointing only to
disposable databases (the MongoDB database name must contain `test`):

```sh
NODE_ENV=test node_modules/.bin/mocha --fail-zero --timeout 30000 --exit \
  --require ./tests/hooks.js tests/postgres-connection.test.js \
  tests/postgres-identity.test.js tests/postgres-filter.test.js \
  tests/postgres-entries-read.test.js tests/storage.filter.test.js \
  tests/api3.storage.filter-semantics.test.js
```

Missing database URIs leave the differential checks pending; that is not
acceptance. Keep the fixture synchronized with the opt-in emitter candidate
until an actual reviewed migration catalogue replaces it.

**Still not M1:** regex (different dialects), dotted paths, v1, nonempty
projections, driver read options, non-JSON scalar operands, unsupported types,
array/object sort semantics, unsorted pagination and negative bounds explicitly
refuse rather than approximate. Shape refusals occur before SQL; sort-value
refusal is data-dependent after querying. Read results are materialized without
a cursor/batch cap and equal-key tie order is unspecified. `findMany`,
`findOneFilter`, `findEveryForm`, writes/events, identifier collision/retry,
current indexes and backend-suite wiring remain. No PG backend registration
or hosted role was enabled.

**Next bounded work:** entries writes/current write-intent outcomes and
identifier constraints; reviewed entries schema/migration catalogue; MongoDB
runner lease/fencing/resume; then trusted tenant resolution/config/auth wiring
for the two-tenant HTTP lab. Regex/projection/array-sort parity belongs in the
remaining compatibility inventory, not an implicit change to supported API
behavior. The owner authorization/revocation contract can proceed independently.
The maintainer push command above now includes both local continuation commits;
no upstream push was made.

### Continuation: dormant entries writes (2026-11-02)

**Local upstream commit `7bcfc8b0e42cacda67ca0bfd62a9374099a26759`** adds
`insertOne`, `updateOne`, `deleteOne`, `updateMany` and `deleteMany` in
`externals/work/crm-multitenant-20261102/lib/storage/postgres-entries-write.js:1-156`.
This is a persistence subset, not a registered backend or integrated write-intent
implementation. It uses the existing experimental typed-key entries fixture;
no migration catalogue or index policy is added here.

Updates/deletes lock their matching rows and write in the same SQL statement.
By-identifier writes follow the existing storage preference (identifier first,
then ObjectId over its string twin), unless an explicit stored `_id` chooses
the exact typed record. Scalar sets/unsets preserve unrelated fields, including
already-stored nested data. Replies distinguish matched from modified rows;
repeating an unchanged patch reports zero modifications. Inserts preserve the
stored identity kind and the requested input normalization behavior.

**Measured: 1 input-refusal check and 8 real PG/MongoDB checks** compare
supported replies and stored documents through the actual MongoCollection
interface and the tenant-bound PostgreSQL connection. Fixtures overlap across
tenants, test the ObjectId/string twins and include unrelated nested data.
Tenant B is unchanged by A's writes and can independently update/delete/insert
its own overlapping identities. Unbound writes refuse; duplicate-key and
explicit callback failures roll back the surrounding transaction.

The concurrency check uses **two distinct backend PIDs** and observes the second
statement waiting on a real PostgreSQL lock before allowing the first commit.
It covers both disjoint patches and restoring a field's pre-wait value.
No-op comparison must use the locked target document: the update relation's
earlier statement snapshot can otherwise skip that second patch. Three actual
implementation mutations fail as intended: removing the identity-kind join,
counting unchanged updates as modifications, and using the stale snapshot
for no-op detection. The restored implementation passes.

**Combined regression: 158 passing, no pending, across 11 files**, on
PostgreSQL 16.15 and MongoDB 8.0.34. This includes the read/filter/identity/
connection tests and existing MongoDB filter, tenant-scope, backend-selection
and v3 write-intent regression tests; those existing tests are not a claim that
the PG subset now executes complete write intents. ESLint, all 462 test-file
classifications and the existing write-boundary check pass. The latter still
covers the existing nine adapter entry points, not promotion of the dormant
PG module. Only this session's two disposable containers were removed.

Reproduce the write slice from the upstream worktree using disposable database
URIs (`CUSTOMCONNSTR_mongo` must name a database containing `test`):

```sh
test -n "$NS_TEST_POSTGRES_ADMIN_URI" && test -n "$CUSTOMCONNSTR_mongo" &&
NODE_ENV=test node_modules/.bin/mocha --fail-zero --timeout 30000 --exit \
  --require ./tests/hooks.js tests/postgres-entries-write.test.js
```

Missing either URI leaves the eight database checks pending, not accepted.
The persistence slice refuses nested/array/BSON set or inserted values,
non-finite numbers and negative zero, dotted/operator/identity update fields,
conflicting set/unset fields, v1 and unsorted `one` filter options. Complex
identifier sort values refuse without modifying any matching row; an explicit
stored id needs no sort. Existing filter-compiler refusals still apply.

**Still not M1:** there is no replacement/upsert/batch/every-form write API,
identifier-index retry or duplicate-error translation, source-label/validation/
commit-event integration, complete read/query parity, cursor cap or backend
registration. Native PostgreSQL constraint errors propagate; no retry is
attempted inside an aborted transaction. Matching sets are locked/materialized
without a size cap; lock ordering/resource bounds still need acceptance.
The typed DDL remains experimental. No serving role or default MongoDB behavior
changes, and no upstream push was made.

**Workstream boundary:** the other session owns MIG-RUNNER, minimum settings/
subject-policy APIs and the provider-neutral secrets contract/Vault-facing
adapter, retaining the built-in option. This slice does not modify those files
or claim Vault cost/efficiency/production readiness. Human identity,
evaluator/events and next-generation execution remain separate. The next
storage slice is entries upsert/resend/batch outcomes with constraint-specific
retry, coordinated with the reviewed schema/catalogue owner.

### Integration: entries and Vault-facing secrets (2026-11-02)

**Local merge `6943dccb25e680d063a00e69ee0434d8bcb3eedb`** joins entries
`7bcfc8b0` and the parallel secrets branch at
`fec19ba5b0526e9c94c751dc24ea4505eb5d92ae`. Its three imported commits are
`a3888080` (provider-neutral component/Vault adapter), `cbbe9179` (PG ciphertext
and audit persistence) and `fec19ba5` (audited rewrap/CAS). The integration branch
remains `workspace/multitenant-20261102`; nothing was pushed upstream.

The dormant component authorizes each operation against injected current
authority, awaits a redacted audit receipt, and binds encrypted plaintext and
JWT audience to the tenant. Vault keys are not exported. The optional PG adapter
persists immutable references and independently committed append-only audit
attempts. A separate maintenance identity can rewrap ciphertext using CAS;
it has neither record INSERT nor plaintext-decrypt authority. Concurrent
rewraps have one winner; retries reload after a conflict or uncertain reply.
The experimental secrets catalogue upgrades through the existing explicit
operator runner; no migration is performed at serving boot.

**Integrated acceptance: 230 passing, no pending, across 17 files.** This runs
entries writes/reads/filter/identity/transactions, existing MongoDB filter,
scope/backend/v3-write-intent regression checks, migrations/CLI, and the full
33-test secrets/Vault/PG acceptance together. All three Docker opt-ins were
enabled, as were disposable entries PG/MongoDB URIs. Real scoped Vault calls,
PG restart, migration SIGKILL/restart, audit-before-provider visibility, tenant
RLS, maintenance-only privileges, rewrap races and simulated lost replies
execute rather than skip. Lab-owned containers were removed.

`tests/tiers.json` merged without conflicts and keeps all four new test files:
the entries-write file, secrets unit file and two secrets integration files.
**All 465 files classify**. ESLint and the existing write-boundary check pass.
No dependency-manifest, migration-runner, entries-source or serving-role file
changed in this merge.

The CI no-database runner was also exercised. Initially missing local frontend
artifacts caused bundle/map, DOM and gzip-accounting failures; building with
`npm run bundle` resolved them. On the built tree:

| Tier | Result |
|---|---|
| unit | 2,108 passing |
| DOM | 205 passing |
| core | 319 passing |
| harness | 92 passing |
| dependency | 368 passing, 1 pending, 1 failing |

The remaining unchanged dependency assertion finds `har-validator` and AJV
6.12.6 in ancestor `/home/bewest/node_modules`, outside the integration tree,
while requiring AJV >=6.14.0. No dependency manifest changed and no ancestor
installation was altered. **The full no-database command is not green**;
this is an explicit environment/dependency limitation, not a secrets/entries
acceptance pass or permission to waive the gate. The production bundle builds
with its three webpack performance warnings.

Reproduce the combined checks in the integration worktree:

```sh
# Both URI variables must name disposable databases; MongoDB name contains test.
test -n "$NS_TEST_POSTGRES_ADMIN_URI" && test -n "$CUSTOMCONNSTR_mongo" &&
NODE_ENV=test NS_MIGRATION_DOCKER_TEST=1 NS_VAULT_DOCKER_TEST=1 \
NS_SECRETS_POSTGRES_DOCKER_TEST=1 node_modules/.bin/mocha \
  --fail-zero --timeout 30000 --exit --require ./tests/hooks.js \
  tests/postgres-entries-write.test.js tests/postgres-entries-read.test.js \
  tests/postgres-filter.test.js tests/postgres-identity.test.js \
  tests/postgres-connection.test.js tests/storage.filter.test.js \
  tests/api3.storage.filter-semantics.test.js tests/storage.tenant-scope.test.js \
  tests/storage-backend-selection.test.js tests/test-backends.test.js \
  tests/write-intent.v3.test.js tests/migrations.test.js \
  tests/postgres-migrations.integration.test.js tests/nightscout-cli.test.js \
  tests/secrets.test.js tests/vault-secrets.integration.test.js \
  tests/postgres-secrets.integration.test.js
node scripts/test-tiers.js check
NODE_ENV=test node scripts/test-tiers.js run unit,dom,dependency,core,harness --ci
```

**Parallel continuation handoff:** the clean secrets worktree can first
fast-forward to this integrated baseline, preserving the original commits:

```sh
git -C externals/work/crm-secrets-20261102 merge --ff-only \
  workspace/multitenant-20261102
```

Its next bounded objective is **synthetic secrets backup/restore and process
crash/retry acceptance** in that isolated worktree. Restore ciphertext/audit
and necessary key versions; demonstrate unchanged references/values and
explicit missing-key/provider refusal, then exercise actual process termination
around rewrap/CAS. Do not equate an interrupted-call test or database restart
with that result. Keep `0001`/`0002` catalogue checksums immutable; any schema
change appends a reviewed candidate migration. Do not modify entries, enable
consumers or push. Reconcile any new tier entry during the next integration.

The entries lane retains upsert/resend/batch/constraint-retry work. MIG-RUNNER's
MongoDB fencing/resume, minimum settings/subject-policy API and current-grant
integration remain separate unfinished work; merging the secrets boundary
does not complete them. Built-in signing remains an adopted option, with no
Vault cost/efficiency/production claim. Human identity, evaluator/events and
next-generation execution remain separate. M1/M2 and backend availability
remain unpromoted.

Source:
`externals/work/crm-multitenant-20261102/lib/secrets/component.js:16-140`,
`externals/work/crm-multitenant-20261102/lib/secrets/postgres.js:34-153`,
`externals/work/crm-multitenant-20261102/lib/secrets/vault-transit.js:29-123`,
`externals/work/crm-multitenant-20261102/tests/postgres-secrets.integration.test.js:19-443`.
