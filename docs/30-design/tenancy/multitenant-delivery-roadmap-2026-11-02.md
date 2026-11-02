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
