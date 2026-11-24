# Multitenant preview integration runs, November 3–7, 2026

*Retained contributor evidence from the #8898 preview and its local branches.
Each run names its source and environment. The original run numbers also
appear in contemporaneous reviews. For later candidates, see the
[multitenant execution log](../../30-design/tenancy/execution-log.md).
The [16.0.0 integration record](../../30-design/remedial/rc-16.0.0-integration-record.md)
holds the single-tenant release runs.*

<a id="run-23"></a>

### R23 - #8898 opt-in CI accounting on `0afdb87f` (2026-11-03)

**Reproduced**, separate dormant foundations branch, not the release candidate:
`0afdb87f83c3b66a5206fa8bd9e5046696bcc2d1`, containing CI fix
`04321de0e3b3a7ea8d624fc5b8d3673aab218c56` and current `official/dev`
`4a482627bfdafb1fef8dcbe0ac6c484811cae563`. The isolated worktree is
`externals/work/crm-pr8898-ci-20261103`; its committed tree excludes the
pre-existing dependency-resolution edit in the shared integration worktree.

Node 22.23.4 / disposable MongoDB 8.0.34, UTC, CI shuffle seed `41574423920`.
Full non-browser tiers: **6,711 passing / 100 pending / 0 failing**, exit 0.
Unit 2,125; DOM 205; dependency 368 plus 2 pending; core 319; harness 93;
integration 3,583 plus 98 pending; stress 18. Disabled labs remain pending,
not exercised or counted as passes. Focused selection/backend regressions:
39 passing. Two explicit enabled-lab runs: 17 and 19 passing respectively,
including real PostgreSQL 16.15, Vault, importer and tenant HTTP checks.

Commands ran from the isolated worktree. `TEST_ENV_FILE` named an ignored
synthetic test environment; database URI variables name disposable resources.
The named scratch directories and owned containers were removed after capture;
recreate synthetic fixtures before replaying, without committing credentials.

```bash
TZ=UTC TMPDIR="$(realpath ../pr8898-ci-scratch-20261103)" TEST_ENV_FILE="$PWD/.ci-scratch/test.env" TEST_SHUFFLE_SEED=41574423920 node scripts/test-tiers.js run unit,dom,dependency,core,harness,integration,stress
NODE_ENV=test TMPDIR="$PWD/.ci-scratch" node node_modules/mocha/bin/mocha.js --no-config --no-package --reporter ./scripts/execution-reporter.js --timeout 20000 --exit tests/test-select.test.js tests/test-backends.test.js
NODE_ENV=test NS_TEST_POSTGRES_ADMIN_URI="$DISPOSABLE_POSTGRES_URI" NS_VAULT_DOCKER_TEST=1 TMPDIR="$(realpath ../pr8898-ci-scratch-20261103)" node node_modules/mocha/bin/mocha.js --no-config --no-package --fail-zero --reporter ./scripts/execution-reporter.js --timeout 30000 --exit tests/postgres-connection.test.js tests/entries-importer-postgres.integration.test.js tests/vault-secrets.integration.test.js
NODE_ENV=test NS_TEST_POSTGRES_ADMIN_URI="$DISPOSABLE_POSTGRES_URI" CUSTOMCONNSTR_mongo="$DISPOSABLE_COMPARISON_MONGO_URI" NS_TENANT_HTTP_DOCKER_TEST=1 NS_MIGRATION_DOCKER_TEST=1 NS_SECRETS_POSTGRES_DOCKER_TEST=1 TMPDIR="$(realpath ../pr8898-ci-scratch-20261103)" node node_modules/mocha/bin/mocha.js --no-config --no-package --fail-zero --reporter ./scripts/execution-reporter.js --timeout 60000 --exit tests/postgres-entries-read.test.js tests/tenant-entries-http.integration.test.js tests/postgres-migrations.integration.test.js tests/postgres-secrets.integration.test.js --grep 'PostgreSQL entries read matches|M3 tenant entries HTTP lab|status/check are read-only|runs the actual operator CLI|stores immutable tenant-local ciphertext'
```

**Control:** removing reporter recognition of opt-in pending events makes the
focused regression fail with `TEST_EXECUTION: no test body completed in
tests/fixtures/opt-in.fixture.js`. Restored behavior passes. Existing ordinary
skipped/empty file enforcement remains tested, serially and in parallel.
The original eight disabled labs reproduced 77 pending and exit 8;
with the fix they retain 77 pending and exit 0.

Changed-file ESLint: zero errors, two existing filesystem-path warnings.
Tier map: 473 files/eight tiers. Whitespace and final PR check passed.
**Unmeasured:** browser replay, MongoDB migration opt-ins, remaining PG
migration/secrets campaigns and fresh remote CI on this unpushed head.
An earlier full attempt was aborted after an owned MongoDB descriptor-limit
failure and scratch-directory dependency leakage; it is not counted green.
The complete replay used an owned MongoDB descriptor limit of 64,000 and
scratch outside the package tree. No M1-M6 promotion or runtime enablement.
See [mechanism and integration record](multitenant-delivery-roadmap-2026-11-02.md#pr-8898-database-ci-accounting-fix-2026-11-03).

<a id="run-24"></a>

### R24 - combined P2 dormant slices on `8b193e18` (2026-11-03)

**Read-derived agent-run evidence**, not coordinator remeasurement or candidate
acceptance. Clean isolated `workspace/p2-integration-20261103` at
`8b193e187fecaa93b41b5f3ced786a80d3e219f0` joins entries `cabb5eec`
and authority `ad0cbdac`, includes refreshed `official/dev` `4a482627`,
and is unpushed. PR #8898 remains open/draft at published `0afdb87f`.
Eight changed paths relative to that PR head are the entries reader and two
focused tests, tenant-authorization README/adapter/candidate and integration
test, plus `tests/tiers.json`. No role is enabled.

Runtime: Node 22.23.4, MongoDB 8.0.34 with nofile 64000, PostgreSQL 16.15.
Owned synthetic loopback databases and scratch outside the package tree;
bundles built in the owned worktree. After sourcing `tests/ci.test.env`,
set the owned MongoDB connection environment, `TZ=UTC`, external `TMPDIR`,
`TEST_SHUFFLE_SEED=41574423920`, and `TEST_ENV_FILE=/dev/null` for nonbrowser
tiers so default configuration cannot override the owned database.

| Command / suite | Passing | Pending | Failing |
|---|---|---|---|
| `npm run test:all` unit | 2127 | 0 | 0 |
| DOM | 205 | 0 | 0 |
| dependency | 368 | 2 | 0 |
| core | 319 | 0 | 0 |
| harness | 93 | 0 | 0 |
| integration | 3583 | 106 | 0 |
| stress | 18 | 0 | 0 |
| Nonbrowser total | 6713 | 108 | 0 |
| `npm run test:browser` | 684 | 0 | 0 |
| `npm run test:affected` (overlapping replay, not additive) | 7293 | 108 | 0 |

Explicit campaigns use `node_modules/.bin/mocha --no-config --no-package
--fail-zero --reporter ./scripts/execution-reporter.js`, owned dependencies,
and 30000-120000ms timeouts:

| Selectors / environment | Passing / pending / failing |
|---|---|
| `postgres-entries-read`, `postgres-connection`, `entries-importer-postgres.integration` test files; both disposable database URI variables | 18 / 0 / 0 |
| `postgres-entries-write.test.js`; both disposable database URI variables | 22 / 0 / 0 |
| `tenant-authorization-postgres.integration.test.js`; `NS_TENANT_AUTHORITY_POSTGRES_DOCKER_TEST=1` | 7 / 0 / 0 |
| `tenant-entries-http.integration.test.js`; `NS_TENANT_HTTP_DOCKER_TEST=1` | 10 / 0 / 0 |
| `postgres-migrations.integration.test.js`; `NS_MIGRATION_DOCKER_TEST=1` | 13 / 0 / 0 |
| `postgres-secrets.integration.test.js`; `NS_SECRETS_POSTGRES_DOCKER_TEST=1 NS_VAULT_DOCKER_TEST=1` | 16 / 0 / 0 |
| `vault-secrets.integration.test.js`; `NS_VAULT_DOCKER_TEST=1` | 6 / 0 / 0 |

Campaign counts overlap full-suite cases; do not add them as a unique census.
Actual state controls demonstrate unbound/session binding leakage, foreign rows
when RLS is disabled and unsafe-authority startup refusal. Owned idle database
termination leaves the child alive; its next authorization refuses. Grant,
ledger/checksum, audit privilege and provider-key mutations exercise refusal
and recovery. No new source ablation was run on this combined tree; original
source controls retain their lane-head evidence. HTTP revocation/outage still
uses fixture authority, not production credential wiring.

Focused ESLint, whitespace and `npm run test:tiers` pass (474 files, eight
tiers). Final `tools/review/prcheck/prcheck.sh
externals/work/crm-p2-integration-20261103` passes after current-dev checks,
tests and owned resource cleanup. Only read-only checks followed.
The Mongo migration opt-in was **skipped** because its fixture writes literal
`/tmp/ns-repl-key` without a path override. Production credential-to-principal
verification, HTTP/listener wiring and owner/operator provisioning remain
UNMEASURED. This records tested dormant integration, not full multitenant
acceptance or release readiness.

<a id="run-25"></a>

### R25 - tenant credential/current-authority GET on `7eb76c71` (2026-11-03)

**Read-derived agent-run evidence**, not coordinator replay or production
acceptance. Clean isolated `workspace/tenant-auth-http-20261103` at
`7eb76c713ace783dc24f412f1242678f1fd23770` extends combined `8b193e18`
and includes refreshed `official/dev` `4a482627`. Unpushed; #8898 remains
open/draft at published `0afdb87f`.

The dormant slice adds tenant-bound legacy credential verification inside the
secrets boundary, separate operator-run credential-reference/subject metadata,
and an optional entries GET data-access bridge. The actual API3 handler gets
only the asynchronously established `api:entries:read` permission through an
internal synchronous binding. No wildcard, HTTP-supplied identity or Promise
serves as Shiro authority. Owner/operator authentication and default single
paths remain unchanged. Other data methods explicitly refuse; this is not
full REST compatibility.

Verification preserves shipping root/subject derivation in synthetic
differential tests, including presentation-prefix variants. Imported stable
IDs/root authority remain necessary for existing credentials. Trusted metadata
selects the current encrypted root reference; authorized/audited decryption
and digest calculation stay inside the secrets boundary. Real Vault decrypt
is tested separately; Transit HMAC is measured as different from legacy
digests and is not substituted. Signing keys remain nonexportable.

Authentication reads current credential metadata; authorization separately
reads current subject/default-role policy. These are sequential snapshots,
not an atomic transaction spanning stores. Previously verified/authorized
in-flight operations may finish. Invalid supplied credentials refuse rather
than become anonymous. Missing references, audit refusal and store failures
produce sanitized unavailable responses.

Enabled focused command, from the owned lane with Docker and owned scratch:

```sh
NS_TENANT_CREDENTIAL_HTTP_DOCKER_TEST=1 \
NS_TENANT_AUTHORITY_POSTGRES_DOCKER_TEST=1 \
NS_TENANT_HTTP_DOCKER_TEST=1 NS_VAULT_DOCKER_TEST=1 NODE_ENV=test \
  node_modules/.bin/mocha --no-config --no-package --fail-zero \
  --reporter ./scripts/execution-reporter.js --timeout 90000 \
  tests/tenant-legacy-credentials.test.js \
  tests/tenant-credential-http.integration.test.js \
  tests/tenant-authorization-postgres.integration.test.js \
  tests/tenant-entries-http.integration.test.js \
  tests/tenant-resolution.test.js tests/tenant-app.test.js \
  tests/tenant-jwt-http.integration.test.js tests/secrets.test.js \
  tests/vault-secrets.integration.test.js
```

| Campaign on committed tree | Passing | Pending | Failing |
|---|---|---|---|
| Enabled focused command | 72 | 0 | 0 |
| `npm run test:all` | 6718 | 118 | 0 |
| `npm run test:browser` | 684 | 0 | 0 |
| Enabled `npm run test:affected -- --since 8b193e187fecaa93b41b5f3ced786a80d3e219f0` | 2006 | 23 | 0 |

Counts overlap, never additive. Nonbrowser tier passes: unit 2132, DOM 205,
dependency 368 (2 pending), core 319, harness 93, integration 3583 (116
pending), stress 18. Full/affected setup sources `tests/ci.test.env` then
overrides the owned MongoDB environment, `TZ=UTC`,
`TEST_SHUFFLE_SEED=41574423920`, `TEST_ENV_FILE=/dev/null`, external owned
`TMPDIR`. Runtime Node 22.23.4, MongoDB 8.0.34/no-file limit 64000; PG fixtures
use `postgres:16`. Separate MongoDB instances prevent concurrent suite
interference.

Nine new persistent HTTP cases and five unit cases cover legacy credential
forms, real GET/304, tenant isolation, root/uploader distinctions,
invalid/expired JWT, anonymous modes, policy/grant changes, reference/subject
removal and metadata/audit/authority refusal. The HTTP provider is synthetic;
data authority and credential metadata are real PostgreSQL state. Independent
pools run in one process, not a two-OS-worker deployment.

Three actual source controls in owned scratch go red: bypassing current
authority returns 200 instead of 403 after revocation; caching root-reference
metadata returns 200 instead of 401 after replacement; clearing entries tenant
binding returns 404 instead of own-tenant 200. The latter proves binding
dependence, not foreign disclosure. Restored selectors pass 3/0/0. An earlier
mutation broke setup liveness and was not counted as the final control.

Focused lint, whitespace and 476-file/eight-tier classification pass.
After fetch/current-dev confirmation and repeated focused checks,
`tools/review/prcheck/prcheck.sh externals/work/crm-tenant-auth-http-20261103`
passes as the final readiness gate. Owned containers/scratch removed.

**Remaining:** tenant exchange endpoints and pinned client cohorts, full
v1/v2/v3 carriers/REST compatibility, production import/provisioning,
scoped provider runtime identity/recovery, cross-process races,
owner/operator lifecycle and listeners, resource limits and role enablement.
Other historical opt-ins, including Mongo migration, were not enabled.
No new JWT format or coordinated client upgrade is introduced, but broad
client compatibility and preexisting single-site JWT portability are not
established by these tests.

<a id="run-26"></a>

### R26 - dormant tenant exchange to GET on `81bc71e6` (2026-11-03)

**Read-derived agent-run evidence**, captured 2026-11-04T07:22:29Z, not
coordinator replay or production acceptance. Clean unpushed
`workspace/tenant-exchange-20261103` at
`81bc71e634c0c2e60ac4e86cfba2e063501c9192` extends characterization
`2bbdf312` and credential/GET `7eb76c71`, with refreshed `official/dev`
`4a482627` included. #8898 remains open at published `0afdb87f`.

The explicit dormant composition adds only the shipping v2 subject-token
exchange path and its join to actual entries GET. Response fields remain
`token,sub,permissionGroups,iat,exp`; exact current subject name and permission
arrays come from a fresh tenant-bound authority snapshot. An appended candidate
migration adds nullable subject display-name metadata without changing the
original migration. Missing imported names refuse exchange, not unrelated data
reads. Canonicalization/signing stays inside secrets; root exchange refuses.
Eight-hour issuance and maximum are explicit for this issuer/verifier.
Current grants still govern subsequent GET; JWT response groups are not
cached authority. No default single, client, JWT-envelope, OIDC, listener,
role enablement or wider REST change.

Node 22.23.4, MongoDB 8.0.34/nofile 64000; owned synthetic loopback services,
external project scratch and pinned PG/Vault fixtures. Full setup sources
`tests/ci.test.env`, then supplies the owned MongoDB environment, `TZ=UTC`,
`TEST_SHUFFLE_SEED=41574423920` and `TEST_ENV_FILE=/dev/null`.

```sh
NS_TENANT_CREDENTIAL_HTTP_DOCKER_TEST=1 \
NS_TENANT_AUTHORITY_POSTGRES_DOCKER_TEST=1 \
NS_TENANT_HTTP_DOCKER_TEST=1 NS_VAULT_DOCKER_TEST=1 NODE_ENV=test \
  node_modules/.bin/mocha --no-config --no-package --fail-zero \
  --reporter ./scripts/execution-reporter.js --timeout 90000 \
  tests/authorization-exchange-contract.test.js \
  tests/tenant-legacy-credentials.test.js \
  tests/tenant-credential-http.integration.test.js \
  tests/tenant-authorization-postgres.integration.test.js \
  tests/tenant-entries-http.integration.test.js \
  tests/tenant-resolution.test.js tests/tenant-app.test.js \
  tests/tenant-jwt-http.integration.test.js tests/secrets.test.js \
  tests/vault-secrets.integration.test.js
```

| Campaign | Passing | Pending | Failing |
|---|---|---|---|
| Enabled focused command | 85 | 0 | 0 |
| `npm run test:all` | 6725 | 124 | 0 |
| `npm run test:browser` | 684 | 0 | 0 |
| Enabled `npm run test:affected -- --since 2bbdf3121a6ea2b9c16742b77067c4dbc21cfb38` | 77 | 16 | 0 |

Counts overlap. Nonbrowser passes: unit 2133, DOM 205, dependency 368 (2
pending), core 319, harness 93, integration 3589 (122 pending), stress 18.
Focused cases prove accepted legacy credential canonicalization,
exchange-issued token to actual own-tenant GET, cross-tenant refusal,
empty-bearer handshake, exact-name updates, current grants, duration bounds,
schema upgrade and provider/audit/store refusals. HTTP crypto provider remains
synthetic with actual PostgreSQL metadata/authority; real Vault exchange is
measured separately, not as one production deployment.

Four actual source ablations in owned scratch fail: cached name/grants return
stale display metadata; signing caller input instead of canonical token changes
decoded accessToken; bypassed data authority permits revoked GET (200 vs 403);
removed duration verification permits an overlong token (200 vs 401).
Restored selectors pass 2/0/0. Preliminary migration/Vault expectations were
corrected against actual contracts: stale check throws `MIG_STALE`; mismatched
Vault signing versions may produce provider refusal before audience checking.
That provider case does not establish uniform cross-tenant HTTP status behavior.

Full production lint passes with 22 warnings in unchanged files, zero errors;
focused lint, whitespace and 477-file/eight-tier classification pass. Final
prcheck passes after current-dev sync and post-fetch focused checks. Owned
containers/scratch removed. Global queue measurement was not green:
PASS 204 / FAIL 36 / UNMEASURED 118; no unrelated states/gates changed.

Read-derived client source inventory: AndroidAPS pinned `7e1d537d`, Connect
workspace pin `b394411a` and NightscoutKit `4ec9fd12` retain existing exchange
or direct-credential call shapes; no client was edited or replayed. Broad
backward/forward client compatibility remains UNMEASURED. Production
provisioning/import, scoped provider runtime/recovery, cross-process races,
v1/v2 data routes, mutations, resource bounds, owner/operator lifecycle and
listeners remain outside acceptance. Mongo migration opt-in was not enabled.
No milestone promotion follows.

<a id="run-27"></a>

### R27 - dormant tenant entries search on `c10290d2` (2026-11-04)

**Read-derived agent-run evidence**, reviewed against local logs on
2026-11-04, not coordinator replay or production acceptance. Clean local
`workspace/tenant-entries-search-20261104` at
`c10290d2b804f86853ce3d92014baaf62d10a745` extends R26's `81bc71e6` and
contains `official/dev` `4a482627`.

The dormant reader adds `findMany` using the shipping filter-definition
parser and existing PostgreSQL AST compiler, projection and normalization.
Actual API3 collection/search handlers are exercised through the existing
tenant credential/current-authority bridge. Supported reads require explicit
sort, positive safe-integer limit and nonnegative safe-integer skip; unsupported
filter/sort shapes refuse rather than approximate MongoDB or read unboundedly.
The bridge binds only current `api:entries:read`; reserved history routes,
mutations and other collections remain unsupported. No single-site default,
client protocol, backend registration, listener or role is changed.

| Campaign on `c10290d2` | Passing | Pending | Failing |
|---|---:|---:|---:|
| Live MongoDB/PostgreSQL reader differential | 8 | 0 | 0 |
| New actual HTTP search selectors | 2 | 0 | 0 |
| `npm run test:affected -- --since 2bbdf3121a6ea2b9c16742b77067c4dbc21cfb38` | 115 | 16 | 0 |
| `npm run test:all`, seven nonbrowser tiers summed once | 6764 | 88 | 0 |
| `npm run test:browser` | 684 | 0 | 0 |

Campaigns overlap; do not add them. Nonbrowser tier passes are unit 2133,
DOM 205, dependency 368 (2 pending), core 319, harness 93, integration 3628
(86 pending), stress 18. The integration tier alone is not the full-suite
total. An initial run failed four existing test-database name guards; the
corrected owned database name includes `test`, without bypassing the guard.
The inherited R26 focused campaign was not rerun as one combined selector;
its 85 passes are not a post-change combined result.

Disposable MongoDB 8.0.34 uses loopback/random ports and nofile 64000;
PostgreSQL 16 is also disposable. Source `tests/ci.test.env` first, then
provide owned `CUSTOMCONNSTR_mongo` and `NS_TEST_POSTGRES_ADMIN_URI`, with
`TZ=UTC TEST_SHUFFLE_SEED=41574423920 TEST_ENV_FILE=/dev/null NODE_ENV=test`.
The full run leaves the four tenant-HTTP/authority/Vault Docker flags unset.
The affected run enables `NS_TENANT_CREDENTIAL_HTTP_DOCKER_TEST`,
`NS_TENANT_AUTHORITY_POSTGRES_DOCKER_TEST`, `NS_TENANT_HTTP_DOCKER_TEST` and
`NS_VAULT_DOCKER_TEST`. Reader differential uses
`tests/postgres-entries-read.test.js`; actual HTTP search cases are in
`tests/tenant-credential-http.integration.test.js`. The local ignored
`externals/work/HANDOFF-tenant-entries-search-20261104.md` carries the
environment recipe and log names.

Actual HTTP cases measure exchange-issued JWTs, overlapping tenant IDs,
pagination/projection, current grant revocation across independently pooled
workers, root/anonymous policies, invalid credentials, reserved history
refusal, unsupported filters, store failure and unchanged stored rows.
Source controls in owned scratch fail as intended: bypassing current
authority returns 200 instead of revoked-search 403; binding the other tenant
returns the wrong synthetic row; removing pagination offset breaks the
MongoDB/PostgreSQL differential. Sources are restored and scratch removed.

Agent-reported full lint has zero errors and 22 existing warnings; focused
lint, whitespace, 477-file/eight-tier classification and final prcheck pass.
Broader pinned-client replay, history/mutations, production import/provider
composition, resource acceptance, owner/operator lifecycle and listeners
remain unmeasured. Mongo migration opt-in remains skipped because of its
literal shared temporary path. No queue state or milestone is promoted;
there is no operator-visible default change.

<a id="run-28"></a>

### R28 - entries POST contract characterization on `c10290d2` (2026-11-04)

**Read-derived agent-run characterization**, not implemented PostgreSQL HTTP
POST acceptance. Owned `workspace/entries-mutations-20261104` starts at
`c10290d2b804f86853ce3d92014baaf62d10a745`; characterization tests are local
uncommitted packet artifacts. Production source and migrations were unchanged
for this capture. Current `official/dev` is `4a482627`; published foundations
PR remains at `81bc71e6`.

The actual MongoDB API3 application/purifier and existing live PostgreSQL/Mongo
write differentials pass 34 selected checks, zero pending/failing. A separate
credential/metadata campaign passes four checks with one intended acceptance
failure: accepted credential GET succeeds, but POST remains 405 rather than
the future 201. This red result is evidence of missing implementation, not a
completed gate. The original root GET mismatch was a fixture using plaintext
instead of the shipping accepted root digest; an explicit shipping/verifier/
actual-GET matrix now agrees. No shipping credential regression is inferred.

Measured contracts: current missing subject-name metadata leaves existing GET
valid but refuses exchange 401; metadata-query unavailability returns 503.
Shipping parser/purifier accepts a synthetic field above the unrelated owner
parser's size limit, scrubs disallowed inert markup, and retains its existing
malformed-JSON error behavior. The exact 50 MiB parser boundary is read-derived,
not load-tested. Actual configured pruning runs after create-only writes
without requiring caller delete permission, preserves its OR age predicate
and hourly collection throttle, and is absent when retention is disabled.

Commands from the alignment root after sourcing the owned lane's
`tests/ci.test.env`:

```sh
node externals/work/entries-mutations-run-owned.cjs
node externals/work/entries-mutations-run-owned.cjs gap
```

The ignored runner supplies disposable PostgreSQL 16 and MongoDB 8.0.34 on
random loopback ports, Mongo nofile 64000, owned test connections,
`TZ=UTC TEST_SHUFFLE_SEED=41574423920 TEST_ENV_FILE=/dev/null NODE_ENV=test`.
It uses the execution reporter; gap mode explicitly enables the credential
HTTP opt-in. The local ignored
`externals/work/HANDOFF-entries-mutations-packet-20261104.md` identifies
characterization selectors and logs
`entries-mutations-policy-characterization-final.log` (34 passes) and
`entries-mutations-root-metadata-followup.log` (4 passes, intended 1 failure).
An earlier fixture-only update overgrant made create-only resend incorrectly
succeed (200 instead of 403); restored checks pass. That is not an implemented
production source-ablation control.

The approved next slice is actual tenant entries POST/create/resend with
current branch-sensitive grants, exact attribution, explicit input/outage
classification and configured tenant-local pruning, using a trusted collection
intent factory while retaining Mongo defaults. Approved refusal semantics live
in release decisions. Actual PG HTTP compatibility, controlled races,
source-ablation controls, full suites and final prcheck remain pending for
that implementation. Other mutation methods/history, runtime enablement,
client replay and milestone promotion are outside this characterization.

<a id="run-29"></a>

### R29 - dormant tenant entries POST on `6cad7a42` (2026-11-04)

**Agent-reproduced; parent read-derived from retained logs and handoff.**
Local `workspace/entries-mutations-20261104` is clean at
`6cad7a42d804d6bb115c9d4eff55fe931b68a7cf`, based on `c10290d2`.
Parent fetched `official/dev` at `4a482627bfdafb1fef8dcbe0ac6c484811cae563`;
published foundations PR remains OPEN at `81bc71e6`. This slice is unpushed,
not merged or released, and is not the independent real-Vault composition lab.

Actual entries list POST now uses the shipping create/resend handler and a
trusted per-Collection PostgreSQL intent/storage factory; Mongo remains the
default. Fresh create/update grants follow the stored-identity branch; subject
attribution uses the current exact display name. Missing attribution refuses
401, metadata outages 503. Submitted representation failures alone become 400;
recognized storage unavailability becomes 503 and internal failures remain 500.
The shared parser/purifier and tenant-local configured autoprune are retained.
Adjacent mutation methods/history remain unsupported; no serving role,
listener, migration or default profile is enabled.

The measured Mongo201/PG400 extension-key gap is repaired by separating literal
document keys from mutation-map validation. Independent hyphenated, Unicode
and ordinary unknown-field cases agree across actual Mongo/PG HTTP insert,
replacement and configured merge, including omission/unset behavior. Existing
dot/dollar path refusals, immutable identity and losslessness checks remain.
This is bounded compatibility evidence, not proof for every Mongo input/client.

| `npm run test:all` tier | passing | pending | failing |
|---|---:|---:|---:|
| unit | 2133 | 0 | 0 |
| dom | 205 | 0 | 0 |
| dependency | 368 | 2 | 0 |
| core | 319 | 0 | 0 |
| harness | 93 | 0 | 0 |
| integration | 3671 | 71 | 0 |
| stress | 18 | 0 | 0 |
| **Nonbrowser, each tier counted once** | **6807** | **73** | **0** |

Separate browser: **684 passing**, zero pending/failing. Focused actual HTTP,
live read/write differential and create checks: **78 passing**, zero
pending/failing. Post-sync committed affected groups total **3475 passing /
13 pending / 0 failing**, not another full-suite result. Production lint:
zero errors, 22 warnings outside changed source; owned test lint and whitespace
checks pass. Tier registry: 478 files across eight tiers, valid. Final
`tools/review/prcheck/prcheck.sh` log ends `OK`.

Actual HTTP cases include two tenants/workers, current-name change after
exchange, next-operation revocation, branch-specific permissions, parser
behavior, configured retention without fabricated delete permission,
rollback/no-events and postcommit visibility before notifications. Synchronized
identifier races preserve measured Mongo outcomes: create-only `[201,500]`,
create+update `[200,201]`; no new race guarantee is claimed.

Six isolated source controls go red with assertion failures: restoring ASCII
validation returns400 instead of201 for hyphen/Unicode; overgranting update
returns200 instead of403; bypassing fresh authority accepts a revoked caller;
wrong entries tenant binding exposes the other synthetic row; removing the
owned transaction returns201 instead of rollback500; removing the retry
permission guard changes create-only race outcomes to `[200,201]`.
Clean focused/full checks were rerun after restoring controls.

Reproduce from alignment root, repeating the environment prefix in each shell:

```sh
set -a
. ./externals/work/crm-entries-mutations-20261104/tests/ci.test.env
set +a
node externals/work/entries-mutations-run-owned.cjs focused
node externals/work/entries-mutations-run-owned.cjs all
node externals/work/entries-mutations-run-owned.cjs browser
node externals/work/entries-mutations-run-owned.cjs affected
node externals/work/entries-mutations-controls.cjs
```

The ignored runner prints exact child invocations; uses owned random-loopback
PG16/Mongo8.0.34 (Mongo nofile64000), UTC, seed41574423920 and
`TEST_ENV_FILE=/dev/null`; overrides connections after sourcing CI settings;
and enables the credential HTTP opt-in. Helpers/control copies were removed.
The migration fixture requiring literal `/tmp/ns-repl-key` remains skipped;
pending opt-ins are not passes. Current-dev synchronization preceded final
checks. Exact selectors, lint/tier commands and local artifact names are in
`externals/work/HANDOFF-entries-mutations-implementation-20261104.md`.
Session logs: `entries-mutations-full-nonbrowser-final.log`,
`entries-mutations-browser.log`, `entries-mutations-final-focused.log`,
`entries-mutations-postsync-affected-enabled.log`,
`entries-mutations-lint-tier.log`, `entries-mutations-controls-summary.log`,
the six named control logs and `entries-mutations-prcheck.log`.

No pinned-client campaign, production TLS/provider operations, durable
cross-worker notification/recovery, combined runtime/POST acceptance or major
milestone completion is established here.

<a id="run-30"></a>

### R30 - real-provider runtime lab on e410b163 (2026-11-04)

Tree: `workspace/runtime-composition-20261104`
`e410b1637038c4a4e5f4675a340c4697398bbcba`, extending search `c10290d2`;
includes freshly fetched `official/dev`
`4a482627bfdafb1fef8dcbe0ac6c484811cae563`. The clean commit changes only
`tests/tenant-runtime-vault.integration.test.js` and `tests/tiers.json`.
No runtime, production configuration, listener or role is changed. The
separate POST slice `6cad7a42` is not included.

Evidence provenance: agent-reproduced; parent read the retained logs and
verified committed scope, clean worktree and upstream anchors, not a second
execution of the campaigns. Tests use synthetic data, real scoped Vault
Transit, PostgreSQL/RLS and actual HTTP exchange/read/search across two
workers. They measure tenant-local overlapping IDs, next-operation committed
grant revocation/recovery, wrong-tenant Vault ACL refusal, actual Vault
pause/unpause yielding sanitized 503 and recovery, unsafe serving-role refusal,
stale migration-catalogue refusal and clean worker/pool closure.

| Command / campaign | passing | pending | failing |
|---|---:|---:|---:|
| Enabled new lab | 5 | 0 | 0 |
| Enabled new lab, credential HTTP, real Transit and PG secrets suites | 44 | 0 | 0 |
| `npm run test:all`, seven nonbrowser tiers counted once | 6725 | 132 | 0 |
| `npm run test:browser`, separate | 684 | 0 | 0 |
| Post-fetch `npm run test:affected`, nonbrowser selection | 1755 | 46 | 0 |
| Post-fetch affected browser selection, separate | 6 | 0 | 0 |

The full nonbrowser breakdown is unit 2133, DOM 205, dependency 368/2 pending,
core 319, harness 93, integration 3589/130 pending, stress 18.
Focused/affected totals overlap the full suite and are not additions.
Pending opt-ins are not passes. `npm run lint` exits zero with zero errors and
22 existing warnings; `npm run test:tiers` validates 478 files/eight tiers.
`git diff --check` passes. After fresh fetch/merge (already up to date), the
affected campaigns pass and final `tools/review/prcheck/prcheck.sh` ends `OK`.
Its full branch range includes inherited work; it is not permission to push.

Source-ablation control removes request-local tenant binding in owned scratch:
the actual GET returns 500 instead of expected 200, with
`postgres transaction ran with no tenant bound` (0 passing/1 failing).
This establishes fail-closed binding coverage, not successful cross-tenant
data exposure. The wrong-key ACL refusal is a distinct expected provider case.
An earlier affected attempt reached ambient MongoDB 3.6 and failed the driver's
wire-version requirement; it was stopped and rerun successfully with owned
disposable MongoDB 8 on a random loopback port, not treated as a source defect.

Exact reproduction/environment and local helper ownership are in
`externals/work/HANDOFF-runtime-composition-implementation-20261104.md`.
Retained session logs: `runtime-composition-focused-final.log`,
`runtime-composition-enabled-focused-exact.log`,
`runtime-composition-test-all-exact.log`,
`runtime-composition-browser-exact.log`,
`runtime-composition-lint-exact.log`,
`runtime-composition-affected-postfetch.log`,
`runtime-composition-tenant-scope-ablation.log` and
`runtime-composition-prcheck-final.log`.

The pre-bind migration check is a test-owned read-only catalogue check, not a
production readiness protocol. Production Vault TLS/unseal/HA, service identity,
token renewal/recovery policy, production provider sourcing, owner/operator auth,
canonical ingress, real data, combined runtime/POST acceptance and role
enablement remain outside this result. No M1/M2/M3 promotion follows.

<a id="run-31"></a>

### R31 - canonical ingress packet on 6cad7a42 (2026-11-04)

Tree: accepted POST `6cad7a42d804d6bb115c9d4eff55fe931b68a7cf`, copied to
packet-only `workspace/canonical-ingress-20261104`. No production edits or
commit in the packet. Agent-reproduced, parent packet-read evidence:
`lib/tenant-resolution/index.js:73-79` gives trusted forwarded Host lookup
precedence over Host. A known internal Host resolves alone; adding an unknown
disposable public forwarded name refuses `TENANT_HOST_UNKNOWN`. A known
forwarded alias for another tenant selects that alias's ID under the existing
direct-alias contract. The proposed canonical acceptance probe is expected-red;
it does not indicate a direct-alias regression.

The unchanged resolver suite ran through a dependency-free `node:test` wrapper,
not the normal Mocha/full-tier campaign. Existing source-ablation controls
demonstrate coverage for direct-alias precedence, exact trust, duplicate wire
selectors and resolved-ID assertions. Packet commands, predictions, outcomes
and local logs are retained in
`externals/work/HANDOFF-canonical-ingress-packet-20261104.md` and the lane's
untracked `packet/`; these instruments are not shipping changes.

Maintainer approved rewritten Host as sole canonical selector with explicit
immediate-transport trust, preserving direct mode and assertion-only resolved
ID. Bounded resolver/tenant-app implementation/tests are delegated separately;
their proposed behavior and real transport integration remain UNMEASURED.
Registry allocation/lifecycle and vendor routing are not implemented by a
static resolver map. Selected `TEN-RESOLVE`/`T30-WIRING` queue gates remain
UNMEASURED (no runnable gate), not green. No role enablement or milestone
promotion follows.

<a id="run-32"></a>

### R32 - real-provider POST composition on 4621d5c4 (2026-11-04)

Tree: `workspace/preview-composition-20261104`
`4621d5c4c349f5b5798fa39873274b3dc02928ee`, joining accepted POST
`6cad7a42d804d6bb115c9d4eff55fe931b68a7cf` and runtime
`e410b1637038c4a4e5f4675a340c4697398bbcba` through merge
`acd46750d26728339582a0a91fa3057b0448b282`. Both histories are preserved.
The only merge conflict was adjacent tier registrations; both were retained.
The focused commit changes only the existing runtime integration test.
No production source, schema, dependency or public protocol changed.

Evidence provenance: agent-reproduced; parent verified clean committed scope,
fresh upstream anchors and retained outcome/control logs, not a second run.
The existing lab now injects the accepted trusted PG entries intent and shared
parser/purifier, with separate collections/buses per tenant/worker. It measures
real Vault exchange followed by actual POST201 and another worker's GET200 for
two tenants with identical identifiers; matched POST200 replacement removes an
omitted extension field without changing the other tenant's document.
Post-issuance grants remain current: create-only cannot replace, update-only
cannot insert, and revoked update cannot mutate rows (403).
Actual Vault pause refuses POST503 without a write; unpause permits POST201
and cross-worker GET200 using the previously issued credential.

| Campaign / command | passing | pending | failing |
|---|---:|---:|---:|
| Enabled runtime / credential HTTP / Vault / PG secrets suites | 62 | 0 | 0 |
| `npm run test:all`, seven nonbrowser tiers counted once | 6807 | 79 | 0 |
| `npm run test:browser`, separate | 684 | 0 | 0 |
| Focused permanent HTTP/create/PG read/write selection | 78 | 0 | 0 |
| Committed post-sync affected selection, including selected browser | 3475 | 19 | 0 |

Nonbrowser breakdown: unit2133, DOM205, dependency368/2 pending, core319,
harness93, integration3671/77 pending, stress18. The enabled campaign contains
runtime6, credential HTTP32, Vault8, PG secrets16. The full campaign enables
credential HTTP but not the runtime/Vault/PG-secrets opt-ins; those pending
cases are not passes and are measured separately in enabled62.
Focused/affected totals overlap other campaigns and are not additions.
Lint has zero errors/22 existing warnings; changed-test lint and whitespace
pass; tier registry validates 479 files/eight tiers. After fresh fetch/merge
of `official/dev` (already up to date at `4a482627`), committed enabled/affected
campaigns pass and final `tools/review/prcheck/prcheck.sh` ends `OK`.

Three isolated source controls each fail the new actual POST composite
(0 passing/1 failing): empty trusted intent returns500 instead of201 with
`step.identifiers is not a function`; forced update authority returns200
instead of expected403 for create-only replacement; removed tenant scope
returns500 instead of201 with `postgres transaction ran with no tenant bound`.
The last demonstrates fail-closed binding coverage, not a data leak.
An initial synthetic POST missing required `app` returned400 and was corrected
to the accepted fixture shape; it was not classified as a production defect.
An earlier removed-factory control stopped at constructor validation, so the
final empty-intent control was used to reach actual POST.

Reproduce from alignment root, repeating the environment prefix in each shell:

```sh
set -a
. ./externals/work/crm-preview-composition-20261104/tests/ci.test.env
set +a
node externals/work/preview-composition-run-owned.cjs enabled
node externals/work/preview-composition-run-owned.cjs focused
node externals/work/preview-composition-run-owned.cjs all
node externals/work/preview-composition-run-owned.cjs browser
node externals/work/preview-composition-run-owned.cjs affected
node externals/work/preview-composition-controls.cjs
```

Ignored helpers use disposable random-loopback PG16/Mongo8.0.34 and separate
suite-owned provider containers, UTC, seed41574423920 and
`TEST_ENV_FILE=/dev/null`, overriding connections after CI settings.
Runners report owned helpers removed; control scratch is removed.
The Mongo migration opt-in remains skipped. Exact selectors, opt-ins and
cleanup are in `externals/work/HANDOFF-preview-composition-20261104.md`.
Session logs have prefix `preview-composition-`: `enabled-postsync.log`,
`full.log`, `browser.log`, `focused.log`, `affected-postsync.log`, `lint.log`,
`controls.log`, the three `control-*.log` files and `prcheck.log`.

Fresh upstream read: candidate remains
`4a482627bfdafb1fef8dcbe0ac6c484811cae563`; foundations PR #8898 remains
OPEN/draft at `81bc71e634c0c2e60ac4e86cfba2e063501c9192`.
This local head does not include canonical ingress or establish production
provider/transport readiness, broad client/REST acceptance, durable events,
operational preview or any M1/M2/M3 completion. No push or role enablement.

<a id="run-33"></a>

### R33 - canonical ingress on 468c41dc (2026-11-04)

Tree: `workspace/canonical-ingress-20261104`
`468c41dcab391f827a5bd1d9a581af9de2f0e10b`, extending accepted POST
`6cad7a42d804d6bb115c9d4eff55fe931b68a7cf`, with current candidate
`official/dev` `4a482627bfdafb1fef8dcbe0ac6c484811cae563`.
The committed five-file surface is the resolver and its README, tenant-app
README, resolver tests and app tests. Tracked paths are clean; the packet's
untracked instruments remain excluded. No production listener/startup, provider,
registry, allocator, migration or role was changed.

Evidence provenance: agent-reproduced; parent verified commit/scope and read
retained validation/control logs, not a second run.
Constructor-only `canonical-internal` mode selects only normalized Host from a
copied internal-name map, with one portless canonical name per stable ID and
explicit exact synchronous trusted-peer approval on every request.
Default `direct-alias` behavior remains. Unknown well-formed forwarded public
names are metadata; known conflicting aliases and unequal resolved-ID
assertions refuse, and neither can rescue an unknown canonical name.
Original raw-header duplicate/list/name refusals remain. A thrown trust
decision reaches the app's sanitized unavailable response.

| Command / campaign | passing | pending | failing |
|---|---:|---:|---:|
| Focused resolver and tenant-app Mocha | 25 | 0 | 0 |
| `npm run test:all`, seven nonbrowser tiers counted once | 6815 | 73 | 0 |
| Separate complete browser tier | 684 | 0 | 0 |
| Post-sync affected selection, including selected browser | 3490 | 13 | 0 |

Full nonbrowser breakdown: unit2138, DOM205, dependency368/2 pending,
core319, harness93, integration3674/71 pending, stress18. Pending opt-ins
are not passes; this tree does not include the separate runtime provider lab.
Affected/focused totals overlap other campaigns, not additional full suites.
Focused ESLint passes; production lint has zero errors and 22 existing warnings
outside changed source; tier check validates 478 files/eight tiers; whitespace
passes. Fresh fetch/merge was already up to date; final prcheck ends `OK`.

Four in-memory source controls each produce 23 passing/2 failing:
restored forwarded precedence gives `TENANT_HOST_UNKNOWN` instead of canonical
success in resolver/app; public-alias/ID fallback admits an unknown canonical
name; checking trust only for extra selector fields admits untrusted Host-only
requests; skipped consistency admits a conflicting known public alias.
The clean focused campaign passes without ablation. These measure resolver/app
coverage, not a real production ingress transport.

Reproduction and exact environment are in
`externals/work/HANDOFF-canonical-ingress-implementation-20261104.md`.
The existing ignored `entries-mutations-run-owned.cjs` accepts
`NS_MUTATIONS_WORKTREE` for this tree's `all`, `browser` and `affected` modes;
it uses owned random-loopback PG16/Mongo8, UTC, seed41574423920 and
`TEST_ENV_FILE=/dev/null`, overriding connections after CI settings and
removing owned helpers afterward. Session logs:
`canonical-focused-mocha.log`, `canonical-full-nonbrowser.log`,
`canonical-full-browser.log`, `canonical-postsync-affected.log`,
`canonical-focused-eslint.log`, `canonical-full-eslint.log`,
`canonical-test-tiers-check.log`, four `canonical-control-*.log` files and
`canonical-prcheck-final.log`.

Production transport provenance, durable allocation/lifecycle, atomic
publication/invalidation, wider REST/clients, durable realtime and operational
preview remain outside acceptance. The clean-head join with real-provider POST
`4621d5c4` is dispatched separately; combined behavior is UNMEASURED.
Fresh upstream read keeps #8898 OPEN/draft at `81bc71e6` and the candidate
at `4a482627`. No push, role enablement or M1/M2/M3 promotion.

<a id="run-34"></a>

### R34 - cumulative canonical provider POST on c527fb7e (2026-11-04)

Tree: `workspace/canonical-preview-20261104`
`c527fb7e0d309b7fc567861a41e8f3862e0922df`. Merge
`b1c3437aa6617aa5ff5e6f3f008159f67ae3b25f` preserves accepted ingress
`468c41dcab391f827a5bd1d9a581af9de2f0e10b` and provider/POST
`4621d5c4c349f5b5798fa39873274b3dc02928ee`, including their runtime and POST
ancestors. The focused commit changes only the existing runtime integration
test. Source worktree is clean; no further production source, schema,
dependency, tier, listener or role change.

Evidence provenance: agent-reproduced; parent verified clean committed scope,
fresh upstream anchors and retained outcome/control logs, not a second run.
The new composed case temporarily restarts the lab workers with canonical
resolvers, then restores direct mode and trust state in `finally`.
The explicit synchronous test predicate checks immediate loopback socket peer
and mutable test-local trust on each request; no caller header grants trust.
This is not a production transport adapter.

Real Vault exchange succeeds with canonical A Host and an unknown disposable
public forwarded name, followed by PG/RLS POST201 and another worker's GET200.
Public-name rotation preserves the stable row and exchanged credential.
Known conflicting public aliases refuse400 without mutation; unknown canonical
Host cannot be rescued by a public alias/ID assertion (404).
An A credential on canonical B refuses401 for GET and POST without mutation,
while B's credential still reads its fixture. Host-only POST after trust loss
refuses400 without mutation; restoring trust permits update/read.
Existing direct-mode POST, fresh grants and actual provider pause/recovery
cases remain enabled. Fixtures/grants/workers are restored or cleaned.

| Campaign / command | passing | pending | failing |
|---|---:|---:|---:|
| Focused resolver/tenant-app | 25 | 0 | 0 |
| Runtime suite alone | 7 | 0 | 0 |
| Enabled runtime/credential HTTP/Vault/PG secrets suites after sync | 63 | 0 | 0 |
| `npm run test:all`, seven nonbrowser tiers counted once | 6815 | 80 | 0 |
| Separate complete browser tier | 684 | 0 | 0 |
| Post-sync affected selection including selected browser | 3490 | 20 | 0 |

Full nonbrowser breakdown: unit2138, DOM205, dependency368/2 pending,
core319, harness93, integration3674/78 pending, stress18.
Full/affected enable credential HTTP only; provider opt-ins are separately
measured in enabled63. Pending opt-ins are not passes; overlapping campaigns
must not be added together. Production lint has zero errors/22 existing
warnings outside changed test paths; focused lint and whitespace pass; tier
check validates 479 files/eight tiers. After fetch/merge (already current),
committed enabled/affected campaigns pass and final prcheck ends `OK`.

Three in-memory source controls run the composed actual request path, each
0 passing/1 failing: restored forwarded precedence yields exchange404 instead
of200; removed Host-only trust refusal yields POST200 instead of400; removed
known-alias conflict refusal yields POST200 instead of400.
These are request assertion failures, not constructor/setup-only refusals.
Prior intent/overgrant/tenant-scope POST controls are retained in R32, not
re-run or counted as new controls here.

Reproduce from alignment root, repeating the environment prefix in each shell:

```sh
set -a
. ./externals/work/crm-canonical-preview-20261104/tests/ci.test.env
set +a
NS_CANONICAL_PREVIEW_WORKTREE="$PWD/externals/work/crm-canonical-preview-20261104" \
  node ./externals/work/canonical-preview-run-owned.cjs enabled
```

The ignored runner also supports `runtime`, `all`, `browser`, `affected`;
the local handoff supplies exact source-control hook commands and opt-ins:
`externals/work/HANDOFF-canonical-preview-20261104.md`.
Helpers use owned random-loopback PG16/Mongo8, UTC, seed41574423920,
`TEST_ENV_FILE=/dev/null`, sourcing CI settings before connection overrides;
suite-owned provider containers and pools close, and runners report owned
helpers removed. Session logs have prefix `canonical-preview-`:
`enabled-postsync.log`, `full-nonbrowser.log`, `browser.log`,
`affected-postsync.log`, `resolver-app-focused.log`, `runtime-initial.log`,
`lint-tiers.log`, three `control-*.log` files and `prcheck-final.log`.

Fresh upstream read keeps candidate `official/dev`
`4a482627bfdafb1fef8dcbe0ac6c484811cae563` and foundations PR #8898
OPEN/draft at `81bc71e634c0c2e60ac4e86cfba2e063501c9192`.
No upstream CI, production transport/service identity, registry durability,
complete entries/history/import/resource coverage, wider REST/client,
durable realtime or operational preview acceptance is established by this
local bounded join. No push, role enablement or M1/M2/M3 promotion.

<a id="run-35"></a>

### R35 - provisioning runtime packet on c527fb7e (2026-11-04)

Packet tree: `workspace/provisioning-runtime-packet-20261104`, unchanged
accepted `c527fb7e0d309b7fc567861a41e8f3862e0922df`; no tracked edits.
Agent-reproduced, parent log-read: two existing PostgreSQL integration checks
pass, a paired readiness source control fails, then unchanged checks pass again.
`tenant-authorization-postgres.integration.test.js` verifies additive display
metadata leaves existing names NULL without rewriting the applied catalogue,
original stable ID or checksum. `postgres-migrations.integration.test.js`
verifies status/check are read-only even before namespace/ledger existence.
Removing only the `MIG_STALE` refusal in memory makes the latter test fail
with `Missing expected rejection` (0 passing/1 failing); restored selection
passes2. This is readiness-check sensitivity, not credential fidelity proof.

Reproduce the two checks from the packet worktree with CI settings sourced
first, UTC, seed41574423920, `TEST_ENV_FILE=/dev/null`, opt-ins
`NS_TENANT_AUTHORITY_POSTGRES_DOCKER_TEST=1` and
`NS_MIGRATION_DOCKER_TEST=1`, Mocha `--no-config --no-package --fail-zero`,
execution reporter and the selector
`appends current display metadata|status/check are read-only even before`.
Exact dependency path/command and in-memory preload are in
`externals/work/HANDOFF-provisioning-runtime-packet-20261104.md`.
Tests own and remove disposable random-loopback PG16 containers.
Retained session logs: `provisioning-runtime-packet-existing-positive.log`,
`provisioning-runtime-packet-readiness-control.log`,
`provisioning-runtime-packet-restored-positive.log`.

Read-derived inventory: explicit operator schema CLI, entries-only importer,
read-only legacy/current authority readers and encrypted root insertion exist;
no tenant/credential provisioning-import command joins them. Components commit
independently, so schema currency does not certify complete tenant preparation
or atomic activation. Duplicate root insertion refuses; it is not an
idempotent multi-store import. The existing runtime fixture hand-seeds metadata
and binds workers before encrypting roots; successful setup is not production
prebind readiness. A test-only source-credential/current-metadata fidelity
slice is the next bounded action, not an implementation of missing tooling.

No new authenticator, root recovery, registry lifecycle, numeric bound,
production transport/service identity or listener policy is selected.
Full suites/provider/production acceptance were not rerun by this packet.
No serving enablement, push or M2 promotion.

<a id="run-36"></a>

### R36 - entries PATCH characterization on c527fb7e (2026-11-04)

Packet tree: `workspace/entries-patch-packet-20261104`, unchanged accepted
`c527fb7e0d309b7fc567861a41e8f3862e0922df`; no production implementation.
Agent-reproduced, parent packet/log-read: corrected baseline23 passing,
permission source control0 passing/1 failing, restored baseline23 passing.
The original red baseline is retained: fixture assumptions expected allowed
inert markup to be removed and unaddressed subapplication PATCH400, while
shipping purifier retains allowed markup and actual route fallback is404.
Only those two characterization expectations were corrected after review;
no enforcement assertion was weakened or shipping behavior changed.

The actual shipping addressed PATCH performs merge/unset, omission retention,
nested merge, array replacement, immutable/identifier/read-only/deleted checks,
seconds-floored preconditions, current-name modifiedBy stamps and events.
The prepared source ablation removes only the update-permission demand:
the reference request returns200 instead of expected403, proving that check
is non-vacuous. These are actual shipping Mongo handler checks, not a pinned
client replay or real-provider PATCH campaign.

Actual tenant PG HTTP PATCH still returns405 before credential verification;
those refusals do not prove post-admission authentication/authorization.
Trusted PG merge primitives independently support ordinary JSON changes and
rollback with no committed event; the handler's two direct intent factories
still bypass the accepted injected PG intent seam. Read-derived minimal next
surface is addressed PATCH admission/current authority plus both trusted
factory call sites, not a new update language or schema.
Mongo top-level dotted updates succeed with path semantics while PG mutation
maps refuse; nested literal dotted members are distinct. Do not approximate
that difference or silently claim parity.

Exact-name attribution/missing-name/outage treatment for modifiedBy and marked
nonrepresentable submitted-input status require review before implementation.
Preserve existing shipping read-then-write/seconds-floor/invalid-date behavior;
no stronger atomic compare-and-swap or changed single/Mongo behavior is selected.

Reproduction commands, exact source anchors and synthetic fixture scope:
`externals/work/HANDOFF-entries-patch-packet-20261104.md`.
Session logs: `entries-patch-packet-baseline.log` (original red),
`entries-patch-packet-corrected-baseline.log`,
`entries-patch-packet-permission-control.log`,
`entries-patch-packet-final-baseline.log`. The ignored packet runner owns
random-loopback Mongo8/PG16 and removes helpers; source settings precede
connection overrides, UTC/seed41574423920/`TEST_ENV_FILE=/dev/null`.
Full suites/browser, production PATCH, remaining methods/history and
M1/M2/M3 promotion remain outside this packet. No push or serving enablement.

<a id="run-37"></a>

### R37 - runnable API and entries CRUD delivery lanes (2026-11-04)

Two independent implementation heads descend from accepted `c527fb7e`.
Both are committed locally, not pushed or merged to `dev`. Candidate
`official/dev` was fetched as `4a482627bfdafb1fef8dcbe0ac6c484811cae563`;
nightscout/cgm-remote-monitor#8898 remains OPEN/draft at
`c527fb7e0d309b7fc567861a41e8f3862e0922df`.

| Lane / tree | Reproduced on that lane | Boundary |
|---|---|---|
| `workspace/runnable-multitenant-20261104`, `93c90520124ff4912d49d37e933ebfe4a5708075` | Actual executable process suite 4 passing; targeted 45; full nonbrowser 6820 passing / 80 pending; browser 684; final affected 96; final prcheck OK. | `nightscout multitenant api` uses strict explicit environment-reference config, real PostgreSQL/Vault, read-only catalogue readiness, current authority and owned shutdown. Child-process tests run outside the checkout without Mongo/API_SECRET and cover two tenants, exchange, POST/read/search, restart, refusal/recovery and cleanup. Only the API preview role is enabled; this lane alone retains the older GET/search/POST admission. |
| `workspace/entries-crud-20261104`, `f57138f24d90eec0ff78e5bf2aba5edc46c7c165` | Actual CRUD HTTP 12 passing; focused 45; full nonbrowser 6795 passing / 112 pending; browser 684; final prcheck OK. Separately enabled inherited credential HTTP is **29 passing / 3 failing**. | Actual API3 addressed PUT/PATCH/DELETE and incremental history use the shared trusted intent seam with real PG/RLS and persisted authority. Single/Mongo behavior is retained. The inherited credential test, deliberately untouched to preserve the separate fidelity lane, has stale 405 expectations for newly admitted routes; it was pending, not green, in this full campaign. |

These are lane-agent reproduced measurements; parent inspected committed heads,
handoffs and persisted result logs, without independently rerunning the broad
campaigns. Passing counts overlap and must not be added across campaigns.
Runtime source controls are red when migration readiness is bypassed (a stale
catalogue child binds its listener) and when requests are cross-bound (tenant B
POST returns200/dedup instead of201). CRUD controls are red for stale authority,
direct PATCH factories, missing owned transaction, wrong tenant and an inclusive
URL-history boundary. Restored lane tests pass; no cumulative acceptance follows
from those independent results.

Parent integration is dispatched in a new owned
`workspace/runnable-crud-20261104` lane: preserve both histories, join test-only
credential fidelity `9e97d07338108f3b338f754c3a3466c7da8d29a8`, refresh the stale
route assertions without weakening permissions, then measure full CRUD/history
through the actual CLI with real Vault/PG and all three relevant opt-ins enabled.
That join and its full/browser campaign remain **UNMEASURED** here. No all-REST,
durable registry/importer, owner/operator role, HA or M1-M6 completion claim.

Commands and exact controls:
`externals/work/HANDOFF-runnable-multitenant-20261104.md` and
`externals/work/HANDOFF-entries-crud-20261104.md`. Session log prefixes are
`runnable-multitenant-` and `entries-crud-`; runners source `tests/ci.test.env`
before connection overrides, use UTC/seed41574423920/`TEST_ENV_FILE=/dev/null`,
owned random-loopback PG16/Mongo8 and pinned Vault, and clean their helpers.
No effect on the shipping single-tenant candidate or its operator release notes.

<a id="run-38"></a>

### R38 - executable entries CRUD cumulative acceptance on 21145d0d (2026-11-04)

Local `workspace/runnable-crud-20261104` is clean at
`21145d0d3b396b744618d2e8158bc1b969f8dd0a`, preserving runtime `93c90520`,
CRUD `f57138f2` and test-only credential fidelity `9e97d073` histories.
Fetched `official/dev` remains `4a482627bfdafb1fef8dcbe0ac6c484811cae563`;
nightscout/cgm-remote-monitor#8898 remains OPEN/draft at `c527fb7e`.
No push, candidate merge or release occurred.

The actual spawned `bin/nightscout.js multitenant api` now exercises shipping
API3 POST, replace, PATCH, logical delete, incremental history and permanent
delete with real Vault and operator-prepared PG/RLS. Two tenants share identifier
spellings; current grants and exact subject names govern mutations, foreign and
anonymous writes refuse, and persisted outcomes survive process restart.
History exposes logical deletion but not a permanently removed document.
Inherited credential tests now assert the admitted routes' actual outcomes;
unaddressed POST and unsupported status retain 405. No production source,
schema, dependency manifest or runtime default changed in this join.

| Reproduced campaign on this head | Passing | Pending | Failing |
|---|---:|---:|---:|
| Focused cumulative HTTP | 83 | 0 | 0 |
| Standalone actual executable/PG/Vault | 5 | 0 | 0 |
| Complete nonbrowser `npm run test:all` | 6834 | 80 | 0 |
| Separate complete browser tier | 684 | 0 | 0 |
| Affected tiers after official/dev sync | 3489 | 20 | 0 |
| Backend census | 4 | 0 | 0 |

Nonbrowser tiers: unit2139, DOM205, dependency368/2pending, core319,
harness93, integration3692/78pending, stress18. All three relevant opt-ins
(`NS_ENTRIES_CRUD_HTTP_TEST`, `NS_TENANT_CREDENTIAL_HTTP_DOCKER_TEST`,
`NS_MULTITENANT_PREVIEW_PROCESS_DOCKER_TEST`) were enabled. Other pending
provider labs are not passes; campaign figures overlap and are not additive.
Production lint reports0 errors/24 warnings; tier map481 files/8tiers passes;
final prcheck reports OK and contains official/dev.

Three in-memory request-path controls each yield0passing/1failing:
bypassed current authority makes denied PUT return200 instead of403;
cross-bound tenant B create returns200/dedup instead of201;
bypassed intent transaction plus post-write failure returns500 but leaves the
row changed, violating rollback. These are semantic assertion failures, not
fixture setup failures. Unmutated cumulative campaigns pass.

These are integration-agent reproduced measurements. Parent inspected the
committed test changes, clean head, handoff and persisted campaign/control logs;
it did not repeat the broad campaigns. Commands and owned-service cleanup are
in `externals/work/HANDOFF-runnable-crud-20261104.md`; session artifacts have
prefix `runnable-crud-`. Source CI defaults precede connection overrides;
UTC/seed41574423920/`TEST_ENV_FILE=/dev/null`, owned random-loopback PG/Mongo
and pinned Vault are used. No owned service remains.

**Accepted boundary: executable API3 entries CRUD preview.** This does not
complete v1/v2, other collections, pinned client replay, a provisioning/import
product, owner/operator roles, durable registry/events, HA, production readiness
or M1-M6. Follow-on domain work is scoped by the
[REST delivery plan](../../30-design/tenancy/multitenant-rest-api-delivery-plan-2026-11-04.md).
The shipping single-tenant candidate and operator release notes are unchanged.

<a id="run-39"></a>

### R39 - explicitly selected REST domains on ae471ac7 (2026-11-04)

Clean local `workspace/rest-shared-20261104` at
`ae471ac790455d6e81781f31b505e3c7b838831b` joins the bounded treatments,
devicestatus/activity, profile/food and context/settings deliveries atop R38.
Fetched `official/dev` remains `4a482627bfdafb1fef8dcbe0ac6c484811cae563`;
nightscout/cgm-remote-monitor#8898 remains OPEN/draft at `c527fb7e`.
No push, candidate merge or release occurred.

The explicit full-domain configuration serves actual shipping v1/inherited-v2
data handlers and API3 collection handlers with tenant-bound PG/RLS storage.
Seven selected domains comprise entries, treatments, devicestatus, profile,
food, activity and settings documents; activity has no invented v3 route.
Legacy credential extraction, current authority, tenant-local loader/cache
frames, safe status/discovery and status credential issuance are composed.
Default executable configuration remains entries-only. Additional domains
require explicit namespaces and operator preparation, checked read-only before
listening. No generic PG backend registry switch or single/Mongo fallback.

| Reproduced campaign on this head | Passing | Pending | Failing |
|---|---:|---:|---:|
| Coherent full nonbrowser | 6909 | 80 | 0 |
| Full browser | 684 | 0 | 0 |
| Cumulative real PG/Mongo/Vault focused | 121 | 0 | 0 |
| Existing migration/M3 actual HTTP | 23 | 0 | 0 |
| Actual executable PG/Vault process | 7 | 0 | 0 |

Nonbrowser tiers: unit2152, DOM205, dependency368/2pending, core319,
harness93, integration3754/78pending, stress18. Pending opt-in labs are not
passes; the migration/M3 selection was separately enabled above. Counts
overlap. Lint reports0 errors/24 warnings; tier map491 files/8tiers passes;
final prcheck reports OK and contains official/dev.

Four in-memory controls each produce0passing/1failing: bypassed read seam
returns an empty list rather than the Mongo reference record; cross-bound
tenant B returns A's synthetic value; bypassed current authority allows revoked
legacy POST; erased query predicate returns a record instead of an empty list.
Restored focused121 and subsequent full/browser runs pass without the hooks.
These are integration-agent reproduced measurements; parent inspected clean
commits, handoff and persisted logs, without repeating the broad campaigns.

Reproduction and exact logs: `externals/work/HANDOFF-rest-shared-20261104.md`;
`rest-shared-full-2.log`, `rest-shared-browser-2.log`,
`rest-shared-composed-restored.log`, `rest-shared-migration-affected.log`,
`rest-shared-process-3.log` and `rest-shared-prcheck-final.log` under
`externals/work/`. CI defaults precede connection overrides; owned random
loopback PG16/Mongo8 and pinned Vault use UTC/seed41574423920 and
`TEST_ENV_FILE=/dev/null`. Local runners, logs and dependency links are not
publication artifacts.

**Incomplete full-REST rows remain:** properties/ddata/summary HTTP admission,
subject/role administration, notices/debug management, notification receipts/
egress and assistant integrations, plus complete route/client replay acceptance.
Imported populated PG insertion-order backfill and physical shared-index
attribution are UNMEASURED. Realtime, evaluation, connector actors, provisioning,
owner/operator lifecycle, HA and production readiness remain separate.
No M1-M6 promotion or shipping operator release-note change follows.

<a id="run-40"></a>

### R40 - derived REST and pinned-pattern cumulative acceptance on ded254b9 (2026-11-04)

Parent-reproduced cumulative acceptance on clean local
`codex/rest-integration-20261104` at
`ded254b9acf5a94e3a4fd99c85b23e1413fa08b6`. Alignment base is
`969dbc74ed8a050f80590732be35801073b9a494`; fetched `official/dev` is
`4a482627bfdafb1fef8dcbe0ac6c484811cae563`. Live #8898 was checked OPEN/draft
at published `ae471ac790455d6e81781f31b505e3c7b838831b`; the continuation
is local and unpushed. No candidate merge, release or M0–M6 promotion.

**Implemented boundary:** actual API2 properties/current/as-of ddata/summary
handlers reuse tenant-local loader frames and shipping sandbox property setters.
Properties/ddata retain shipping entries-and-treatments read requirements,
including inherited secondary-domain snapshot arrays; summary requires wildcard
read. No request-global tenant switch, evaluator/notification lifecycle or new
permission policy is introduced. Current authorization and snapshots remain
request-bound; v1 derived paths and derived mutation methods refuse.

Committed synthetic replay pins NightscoutKit
`4ec9fd12a16b5d6c2de4f11870511361d42e1b7f` and LoopFollow
`4a74b781ad6836dd77eccc03bb08a42749dd59a6`. Real CLI/PG/Vault tests exercise
legacy uploader arrays/resends, follower query-token/window/format reads,
response-sourced caller IDs, cross-version history and restart. Successful
legacy resends may advance srvModified; they preserve logical rows, identity
and srvCreated. Profile upload has no invented retry key. This is extracted
client-pattern replay, not execution of Swift binaries; API3 history and derived
composition are additional server acceptance. The parent-added executable case
joins derived reads with real Vault authority, two tenants, revocation and restart.

| Parent-reproduced campaign on this head | Passing | Pending | Failing |
|---|---:|---:|---:|
| Complete nonbrowser `npm run test:all` | 6926 | 80 | 0 |
| Complete browser tier | 684 | 0 | 0 |
| Enabled cumulative REST/storage/authority/client focused | 138 | 0 | 0 |
| Separate migration and two-tenant HTTP | 30 | 0 | 0 |
| Archived authority queue instrument | 5 | 0 | 0 |

Nonbrowser tiers: unit 2152, DOM 205, dependency 368 / 2 pending, core 319,
harness 93, integration 3771 / 78 pending, stress 18. Counts overlap across campaigns
and must not be added. Remaining disabled labs are pending, not passes. The
runner prints immutable head, Node22.23.4, PostgreSQL16.15, MongoDB8.0.34,
Vault2.2.1, UTC and seed41574423920. Dependencies are installed privately from
the CRM lockfile and assets rebuilt in the owned integration tree. Changed-file
lint reports 0 errors / 9 warnings; tier map 494 files / 8 tiers passes. Final
`tools/review/prcheck/prcheck.sh` reports OK and already contains refreshed
`official/dev` `4a482627`; it runs after the restored focused campaign.

**Controls and correction:** parent-run memory controls on the final source
cross-wire derived frames, bypass current read authority, corrupt computed IOB,
change retry natural identity, route uploads to the other tenant, corrupt consumed
response IDs and freeze persisted grants. Each failed a semantic assertion,
not fixture setup. The executable boot-seam control at source-identical
`c9804060` returns405 where the derived-success test requires200. Archived final
head controls bypass current grant checks (revoked401/outage503 become200) or
remove JWT audience refusal (foreign401 becomes200). The queue control is
NON-VACUOUS. Restored unhooked focused acceptance passes; controls never modify a
shipping checkout or source commit.

The first joined full run on `c9804060` completed 6925 passing / 80 pending / 1 failing:
its inherited process fixture still expected summary405 after the route was
implemented. `ded254b9` verifies actual returned summary data while retaining
v1 and wrong-method refusals; the final full campaign above is coherent on that
commit. Original failure evidence remains under the local handoff. The independent
review also strengthened caller update/delete tests to consume IDs from upload
responses, with SQL only an independent stored-outcome oracle.

Reproduction is committed in
[the owned-service runner](../../../tools/lab/multitenant-rest-preview/README.md):
`CRM_REST_WORKTREE=<clean-tree> node tools/lab/multitenant-rest-preview/owned.js`
with modes `focused`, `all`, `browser` and `migration` after private dependency
installation/build. CI defaults precede private random-loopback overrides;
`TEST_ENV_FILE=/dev/null` is explicit. The
[archived authority instrument](../../../tools/lab/multitenant-rest-authority/README.md)
uses `git archive` into scratch and has registered source controls; it is a
bounded integration instrument, not full runtime or REST completeness.

Exact logs/commands and owned cleanup:
`externals/work/HANDOFF-codex-rest-integration-20261104.md`.
Final parent logs are `/tmp/codex-rest-{full,browser,focused,migration}-final.log`,
`/tmp/codex-rest-controls-final.log`, `/tmp/codex-rest-queue-integration.log` and
`/tmp/codex-rest-vacuity-final.log`; restored focused output is
`/tmp/codex-rest-focused-restored.log` and final publication check is
`/tmp/codex-rest-prcheck-final.log`. Lane details remain in the derived, client
and authority handoffs. Local service credentials, dependency trees, runners,
scratch and log files are not publication artifacts. Parent supplies all final
campaign figures above; earlier lane measurements retain their own provenance.

**Still incomplete:** subject/role administration, notices/debug, notifications/
receipts/egress and assistant routes; full route coverage and client binary execution; arbitrary
query/plugin/localization shapes; populated import ordering and resource bounds;
production identity/trust, provisioning/lifecycle, durable events/realtime/
evaluation, HA and operations. The
[next bounded administration packet](multitenant-delivery-roadmap-2026-11-02.md#next-administration-and-side-effect-implementation-boundary-2026-11-04)
keeps authority writes separate from data-serving privileges. No shipping operator
release-note change follows from this explicit preview continuation.

<a id="run-41"></a>

### R41 - subject administration and cross-compatibility on 94c57f1f (2026-11-05)

**Parent-reproduced cumulative acceptance** on clean local
`codex/rest-integration-20261105` at
`94c57f1f37370215ef25b69691ef63918c876db3`, containing fetched
`official/dev` `4a482627bfdafb1fef8dcbe0ac6c484811cae563`.
Alignment dispatch base was `2294a8944a0eac8e72da866cb70f0580fc7b0c18`;
published #8898 remains OPEN/draft at `ded254b9`. This continuation is local,
not published, merged to dev or released. No M0–M6 promotion or RC scope change.

**Implemented boundary:** dormant subject update/delete and known-stored-role
assignment, with a separately authorized management callback and PG writer.
Append-only `0003_subject_management_metadata` preserves earlier migration bytes,
adds nullable notes/created_at without fabricating old timestamps, and adds a
redacted audit. Stable subject ID, display name, credential presentation prefix
and role links update atomically; final audit failure rolls them all back.
Serving credentials cannot mutate authority; management credentials are refused
as the serving reader. Current persisted grants/deletion apply to the same
previously issued raw/JWT credential on the next operation across separate pools.
Concurrent replacements serialize; this is not a new optimistic version protocol.

The trusted callback authorizes this entire bounded management action; it does
not implement owner permission ceilings or an HTTP identity policy. Migrated
absent notes are SQL null, not proof of Mongo absent-property response parity.
No owner route/listener, full roles CRUD, provisioning or production policy is
enabled. Migration downgrade/rolling-version acceptance remains unmeasured.

**Compatibility additions:** actual Mongo/PG treatment HTTP/stored-result tests
cover legacy PUT, API3 merge PATCH/retry, whole replacement, stale conditionals,
soft-delete/retry and history. Strict comparisons retain nested identity/server-
named extension fields, null/false/zero and arrays, excluding only top-level
server clock stamps. Unrepresentable JSONB text is explicitly refused; observed
Mongo acceptance is recorded separately. Shipping legacy preparation removes
falsy notes and zero carbs; this is asserted rather than normalized away.
Shipping lookup/exchange and tenant verification agree that raw credentials and
JWTs containing the old raw token survive a display rename, while hashes of the
old full prefixed token do not. These are server contracts and synthetic client
patterns, not execution of client applications.

| Parent-reproduced campaign on this head | Passing | Pending | Failing |
|---|---:|---:|---:|
| Complete nonbrowser `npm run test:all` | 6944 | 80 | 0 |
| Complete browser tier | 684 | 0 | 0 |
| Enabled cumulative focused, including new subject and rename tests | 162 | 0 | 0 |
| Separate migration / two-tenant HTTP | 30 | 0 | 0 |
| Affected current-authority PG / upgrade suite, explicitly enabled | 8 | 0 | 0 |
| Archived subject-administration gate | 13 | 0 | 0 |

Nonbrowser tiers: unit2157, DOM205, dependency368/2pending, core319,
harness93, integration3784/78pending, stress18. Campaigns overlap; never add
them. Node22.23.4, PostgreSQL16.15, MongoDB8.0.34, Vault2.2.1, UTC and
seed41574423920 were printed by the owned-service runner. Private matching
dependencies and a fresh postinstall browser build were used. Changed-file
lint passes with no output; classification reports496files/8tiers. Refreshed
dev was already contained; final prcheck reports OK after restored focused
162/0/0. No application source changed during these campaigns.

**Parent controls:** archived current-grants bypass accepts the earlier JWT
after role removal; wrong tenant binding returns foreign metadata; removing the
transaction leaves partial rename/link changes after audit failure. Each is
0passing/1failing with the semantic symptom. The queue gate is PASS and its
registered control NON-VACUOUS. Separate in-memory cumulative controls corrupt
nested PG metadata, bypass shared PATCH conditionals or falsely acknowledge a
representation refusal. Each is 0passing/1failing: strict stored documents
differ, expected412/got200, or expected400/got200, respectively. Source matching
and control loading were checked; shipping worktrees remained unchanged.
Restored unhooked focused162 passes after all controls.

**Historical experiment, separate source scope:** the retained
[bounded refresh](../../../reports/compat-refresh-2026-11-05/README.md) runs
v15.0.9/current dev/published PR-single `ded254b9` twice each,768cells/run,
Node22.23.4/MongoDB7.0.43. It excludes identity/settings families and is not a
rerun on this new cumulative head. Parent independently reran its pin auditor:
dev versus published PR has0semantic differences; release versus each has227
changed cells. Repeats have0semantic differences after narrow random-test-DB
normalization. Persistence ablation and corrupted-repeat/wrong-head controls
are rejected; restored source is green. Historical full-corpus projection
residuals remain diagnostic, not approved differences or a new blanket
backwards-compatibility pass. No old-release-to-PG transitivity is claimed.

**Preserved trial failures:** the first treatment corpus expected notes:null
retention, refuted by equal Mongo/PG results and shipping preparation; it now
asserts omission plus extension-null semantics. A rename draft expected
undefined where shipping returns null. The first PG writer used a role lock
requiring UPDATE permission; the final implementation retains read-only role
privileges and relies on composite foreign-key integrity. An early lane
credential-HTTP invocation lacked its owned Mongo endpoint; the correctly
configured affected run passed. These are recorded hypothesis/setup failures,
not hidden changes to accepted behavior.

Reproduction uses the expanded [owned runner](../../../tools/lab/multitenant-rest-preview/README.md)
and [archived subject gate](../../../tools/lab/multitenant-subject-admin/README.md).
Local commands/logs/controls are indexed by
`externals/work/HANDOFF-codex-rest-integration-20261105.md` and the subject-admin,
cross-compat and historical-compat handoffs. No dependency tree, database endpoint,
service credential or raw local log is a publication artifact.

**Next:** a separately authenticated management HTTP facade and stable role-ID /
unresolved-role characterization; remaining REST side effects and client binary
acceptance; import/resources, production lifecycle and M5/M6 durability/operations.
CodeQL147/148 remain open. This closes the bounded persisted-subject packet,
not full administration, full REST or multitenant readiness.

<a id="run-42"></a>

### R42 - storage contracts and separate management HTTP on d4570e58 (2026-11-05)

**Parent-reproduced local cumulative acceptance**, not publication or milestone
promotion. Final REST head is `d4570e585d0e12e46386ed26772790b269b2b736`,
branch `codex/rest-integration-next-20261105`; fetched dev remains
`4a482627bfdafb1fef8dcbe0ac6c484811cae563`. Alignment dispatch base was
`fc8c4010ee786b7e3453624c6427709a766b7c02`. Published draft #8898 remains
`ded254b9`; R41 and this continuation remain local. No new role/listener or RC
merge-list admission is inferred.

**Implemented boundary:** a standalone subject-management Express factory over
the R41 persisted service. Resolver selection must match authenticated management
identity; body/query fields cannot grant identity. The service still separately
authorizes the entire bounded action. PUT/DELETE use shipping API2-style paths
and stable string IDs, but this is a JSON-only facade with explicit request/error
mapping, not full legacy UI/form/BSON coercion parity. Headers are no-store and
no-referrer; resolver outages, parser failures, unknown roles, incomplete metadata
and persistence failure have bounded sanitized replies. Malformed encoded paths
return400 while callback failures remain503. Subject validation is shared by
HTTP and service, preserving omitted-role revocation and note/date behavior.

Actual PG/HTTP tests observe committed metadata/grants, same earlier raw/JWT
credential refusal across independent serving pools, tenant twins, rollback and
concurrent replacements. Data applications do not mount these management routes;
no CLI binding, human identity provider, delegated grant ceilings or role CRUD is
enabled. This does not cancel an already-authorized operation or add atomic
policy/write fencing. Independent source review found no blocking issue in the
dormant boundary and prompted the encoded-path characterization/fix.

**Contract characterization:** real MongoCollection, lower PG reader/writer and
PG preview storage objects expose typed/raw/shown identity, missing/null/false/
zero comparisons, projection/sort/refusal, partial duplicate batches and actual
result counts. Mongo scope asserts binding without manufacturing row isolation
or rollback; PG binds current UUID through RLS/transactions and refuses to claim
an outer commit. Lower versus preview projections differ explicitly. Shared
logical events include settled no-ops, distinct from physical instrumentation;
mutating PG writes publish after commit and failed commits do not publish.
The [interface amendment](../../30-design/tenancy/nightscout-storage-seam-interface-2026-09-14.md#11-current-admitted-ports-and-independent-scopes-2026-11-05)
and [write-contract amendment](../../30-design/tenancy/write-contract-spec-2026-10-07.md#9-current-shared-intent-and-backend-capabilities-2026-11-05)
reconcile current capabilities without rewriting historical measurements.

| Parent-reproduced campaign | Passing | Pending | Failing |
|---|---:|---:|---:|
| Final complete nonbrowser on d4570e58 | 7015 | 80 | 0 |
| Browser on precursor d1d8c520, application source identical to final | 684 | 0 | 0 |
| Final restored enabled focused | 233 | 0 | 0 |
| Archived current port corpus | 58 | 0 | 0 |
| Archived current management HTTP | 13 | 0 | 0 |

Campaigns overlap; do not sum them. Final tiers: unit2157, DOM205,
dependency368/2pending, core319, harness93, integration3855/78pending, stress18.
Runner versions: Node22.23.4, PG16.15, Mongo8.0.34, Vault2.2.1, UTC,
seed41574423920. The separate port fixture measures PG16.15/Mongo7.0.43.
Private dependencies/build are owned; tier classification498files/8tiers and
changed-file lint pass. Full d1d8 precursor first gave7014/80pending/1failing:
the existing no-subscriber guard counted an event name in new Markdown as code.
The final test limits scanning to executable JS/CJS/MJS and fails closed on Git
errors. Its real-subscriber control fails with a source reference; unavailable
Git also fails rather than silently passing; restored guard passes. Only that
test and PORT-CONTRACT.md changed between precursor/final; runtime source identity
was independently checked. Browser was not repeated for that test/doc-only fix.

**Controls:** projection corruption, foreign PG binding and false changed-count
each fail a real-port assertion; credential bypass and actor/host mismatch each
turn required401 into200; deliberate management-before-data fixture composition
exposes a forbidden mutation. These are separate 0passing/1failing controls,
not setup failures. Representative controls on final source are NON-VACUOUS.
Updated MT-CONFIG-MIN/T30-WIRING gates also pass at final source. Five selected
gates, including the independent profile gate below, report PASS and five
NON-VACUOUS controls; broad catalogue failures/unmeasured cards are not green.
Final unhooked focused233 and final prcheckOK follow the controls; source remains
clean and contains current dev.

**Direct historical comparison:** [new bounded capture](../../../reports/compat-rest-next-2026-11-05/README.md)
uses actual final d457 candidate twice with this campaign's fresh repeated
release/dev endpoints,768cells/run,0semantic repeat differences,0dev/candidate
semantic differences; release comparisons retain227changed cells. Parent reran
the hardened auditor and reproduced the public aggregate byte-for-byte. Actual
no-write/restored source controls, wrong-head, corrupted-repeat and dependency-
change checks reject their breaks. Exact driver/lock/manifest provenance is
captured; the prior unverified7.6.0 driver statement is corrected without
rewriting old aggregate/pins. Omitted identity/settings families, index-on races
and old-full-corpus residuals remain outside this bounded pass scope. No
old-release-to-PG transitivity or universal client parity is claimed.

Local commands/logs/controls are indexed by
`externals/work/HANDOFF-rest-next-20261105.md` and the owner-http, seam-contract
and compat-rest-next handoffs. First fixture hypotheses (selector overreach and
Mongo-generated null ID) and the malformed-path red-before-fix are retained.
No third backend, production management identity, durable events, full REST or
M0–M6 completion is accepted. Next: backend/domain composition and failure
classification, wider roles/client/import/resource and lifecycle acceptance.

<a id="run-43"></a>

### R43 - independent nonresident profile refresh on 925c9527 (2026-11-05)

**Parent-reproduced independent branch acceptance** at
`925c95278ed04954d1181201da79ae5d6c48c095`,
`codex/profile-refresh-20261105`. This refreshes existing draft #8891
`744d1968` with dev `4a482627` and bounded replay tests; it is not joined into
#8898, merged to dev, released or selected for the RC. The boot-stage merge
retains dev's identifier-index prerequisite and the explicit views stages.
Default single remains resident; nonresident is an explicit prototype launcher.

| Parent-reproduced campaign on this head | Passing | Pending | Failing |
|---|---:|---:|---:|
| Complete nonbrowser | 6676 | 3 | 0 |
| Complete browser, default single | 684 | 0 | 0 |
| Archived actual-trigger profile replay | 24 | 0 | 0 |

These are separate branch results, not additional R42 coverage. Tiers:
unit2081, DOM205, dependency368/2pending, core319, harness92,
integration3593/1pending, stress18. Node22.23.4/Mongo8.0.34, private matching
dependencies and rebuilt assets; final prcheckOK contains current dev. Browser
results preserve default resident behavior, not a new nonresident UI claim.

Measured cohorts include treatment/BWP snooze, device IOB properties, crowded
device-kind acquisition, selected Loop/AAPS failure history, pump repost clocks,
quiet no-upload stale alarm, retained-properties freshness, four resend modes,
mixed batches, default/revert and teardown including delayed read completion.
Resident/nonresident derived-property comparison uses identical synthetic DB-size
input because independent live Mongo stats fluctuate. Live stats freshness,
every alarm producer/writer and cross-collection snapshot consistency are not
proved. Fake delivery and socket rejection measure notification requests/handoff;
actual provider delivery, multitenant evaluation/recovery and runtime cost remain
UNMEASURED. Pinned-clock reporter durations are not performance measurements.

Current production code still subscribes to physical write instrumentation plus
a timer. The test harness also drives the same evaluator from logical events:
replace/merge resends yield one cycle in both; acknowledge/refuse yield zero
physical/current cycles but one logical-candidate cycle. Mixed two-record entries
batch coalesces to one cycle. No-op/refusal outcome admission and complete writer
coverage remain an open subscriber decision; no policy switch was made.

Parent archived controls suppress the timer, suppress the write trigger, narrow
device acquisition, or substitute request-time properties. Each produces
0passing/1semantic failure, followed by restored24. The registered timer control
is NON-VACUOUS. Initial archived attempts omitted translations and failed setup
0passing/2failing; those are not semantic controls. Including required fixtures
restored the measured gate. The lane's earlier exploratory full run was
inconclusive after owned Mongo error24/WT_PANIC under an insufficient descriptor
limit; parent full/browser used fresh owned services with explicit limits and
passed. Original failures remain local, not relabeled as green.

Reproduction: [archived suites](../../../tools/lab/multitenant-next-slices/README.md)
and `externals/work/HANDOFF-profile-replay-next-20261105.md`; parent logs are
`/tmp/codex-next-profile-{all,browser,prcheck}.log` and final profile gate/control
logs. Full alarm/writer entry bar, logical subscriber decision, shared derived
frame join, release placement and durable tenant recovery remain open.

<a id="run-44"></a>

### R44 - explicit backend composition and imported identity on bc4ee1a9 (2026-11-05)

**Parent-reproduced local cumulative acceptance** on
`bc4ee1a91b84a657012dbb77ee835fdeb78ef707`,
`codex/rest-compose-integration-20261105`, from R42 `d4570e58`.
Fetched `official/dev` remains `4a482627bfdafb1fef8dcbe0ac6c484811cae563`.
Fresh GitHub read-back reports draft #8898 at R42 `d4570e58` and draft
#8891 at R43 `925c9527`, both OPEN with successful head CI and CodeQL.
This new continuation is local, not merged, released or a milestone promotion.

**Implemented boundary:** domain-catalogue now holds logical domain metadata;
explicit `serve/postgres-domains` owns PG factories/catalogues, read-only
readiness and serving-privilege checks. The preview keeps its current startup,
pool cleanup, forced-RLS and refusal rules. `storage/failures` recognizes the
same dependency codes, wrapped causes and cycles below the HTTP wrappers.
Submitted-validation provenance and version-specific response bodies/statuses
remain with the adapters. Default single/Mongo, query/write policies, projections
and tenant binding versus commit ownership retain their existing contracts.
This is current preview composition, not a universal backend API or helper
consolidation.

**Direct identity expansion:** actual API3 Mongo/PG HTTP compares imported
ObjectId, hex-string and custom-string raw identities with absent/null/empty/
false/zero stored identifiers. Each case observes GET, PATCH, replace, soft and
permanent deletion; raw typed identities, retained/removed fields, independently
allocated clocks against persisted outcomes, and unchanged foreign-tenant data
are asserted. Only allocated clock values are excluded from cross-backend
comparison. This fills a bounded current-backend gap; it does not rerun the
historical release corpus, settings families, index races or client binaries.

| Parent-reproduced campaign | Passing | Pending | Failing |
|---|---:|---:|---:|
| Complete nonbrowser on bc4ee1a9 | 7035 | 80 | 0 |
| Complete default browser on bc4ee1a9 | 684 | 0 | 0 |
| Archived composition: real process/startup and storage/HTTP boundaries | 15 | 0 | 0 |
| Archived direct imported-identity differential | 15 | 0 | 0 |

Scopes overlap; do not sum them. Full nonbrowser tiers: unit2157, DOM205,
dependency368/2pending, core319, harness93, integration3875/78pending,
stress18. Node22.23.4, PostgreSQL16.15, Mongo8.0.34, Vault2.2.1, UTC and
seed41574423920; owned services cleaned. Classification499files/8tiers and
changed-file ESLint pass with zero errors and five path/import warnings. Final
prcheck is OK, with the tested branch clean and current official/dev contained.

**Parent-reproduced controls:** removing the injected intent guard makes a
partially injected real child bind; bypassing the migration catalogue check
makes the wrong-catalogue child bind. Each fails the required no-bind assertion,
0passing/1failing. Removing dependency recognition makes actual HTTP503 become500,
0passing/1failing. Removing PG imported raw-ID fallback makes the actual PG GET
return404 after the Mongo oracle returned200, 0passing/1failing. These are semantic
failures, not setup errors. Restored archived positives pass; the two declared
queue instruments are PASS with NON-VACUOUS controls. Independent read-derived
source review found no blocking extraction issue; actual guard-bypass controls
resolve its concern that generic refusal alone could mask initialization errors.

Initial sandbox invocations of Git child processes failed with `spawnSync git
EPERM`; granted process access allowed measurement. A first archive attempt used
an unqualified HEAD and was refused by the dependency-lock check, without running
the corpus; final gates pin the explicit commit. Neither setup failure is a
product defect or a semantic control.

Commands/logs are indexed by local
`externals/work/HANDOFF-compose-integration-20261105.md` and the compose and
compat-compose lane handoffs. The [archived instruments](../../../tools/lab/multitenant-next-slices/README.md)
read committed sources into scratch with matching private dependencies and owned
services. Full portable capability review, consolidation, remaining REST/clients,
owner policy, import/resources and production lifecycle/recovery remain open.
The independent profile continuation is measured separately.

<a id="run-45"></a>

### R45 - independent actual HTTP profile writers on dff9a8d4 (2026-11-05)

**Independent test-only branch acceptance**, not a REST join, subscriber choice,
release admission or multitenant evaluator acceptance. Source is
`dff9a8d42860be09c7f187f5e3d0527d6eb31d80`,
`codex/profile-writers-20261105`, extending published draft #8891 R43
`925c9527`. Production `lib`, `scripts`, `bin` and `migrations` are unchanged;
current dev `4a482627` remains contained. Default single stays resident and the
prototype keeps its physical-write subscriber and heartbeat.

**Measured scope:** six new cases drive actual authenticated API3 entries and
treatments POST/PATCH/soft DELETE plus all four entries resend modes through the
prototype's real application. Stored values and tombstones, actual physical and
logical events, coalesced evaluator cycles and retained properties are observed.
Resident comparison deep-compares retained property JSON and alarm-request
signatures (kind/level/group/plugin/event/title/message); it does not compare all
notification fields. Selected high-alarm and treatment notifications must reach
actual live service emission. Provider delivery remains fake/guarded. No-op
acknowledge/refuse preserves zero physical events/evaluator cycles, one logical
intent and unchanged retained cycle; this characterizes existing behavior without
adopting a logical-event admission policy.

| Campaign / evidence owner | Passing | Pending | Failing |
|---|---:|---:|---:|
| Agent-reproduced complete nonbrowser, parent audited source anchor and tier aggregate | 6682 | 3 | 0 |
| Agent-reproduced complete default browser, parent audited source anchor and aggregate | 684 | 0 | 0 |
| Parent-reproduced archived whole profile file | 30 | 0 | 0 |

Full campaigns were not independently repeated by the parent. Their immutable
runner output anchors the same final head and records cleanup; parent reproduced
the bounded replay and controls. Nonbrowser tiers: unit2081, DOM205,
dependency368/2pending, core319, harness92, integration3599/1pending, stress18.
Node22.23.4/Mongo8.0.34, UTC, seed41574423920; the shared owned runner also
records unused PG16.15/Vault2.2.1 services, not evidence of tenant-PG evaluation.
Groups overlap. Selected new-only replay6 and changed-file lint pass. Final
independent prcheck is OK and the tested branch remains clean/current.

**Independent review found a fixture defect**, reproduced before correction:
the preceding alarm cohort closed its notification service; new request wrappers
still recorded signatures around that closed service. Live emission assertions
made whole-file execution28passing/2failing while new-only execution6passed.
The final test owns a fresh live notification service and scoped teardown
listeners per cohort, restores previous context and retains both live assertions.
Whole30/new-only6 then pass. No production defect or policy change is inferred.
Earlier aec5496f broad runs were stopped and are incomplete/superseded, not green
acceptance. Independent read-derived final review resolves the lifecycle finding.

**Parent-reproduced controls:** suppressing the actual write trigger fails the
required post-write coalesced cycle (0 versus1) after persistence/event checks;
closing only the new real notification service leaves request recording in place
but fails the required committed high-alarm emission. Each is0passing/1semantic
failure; restored whole30passes. The declared profile gate is PASS/NON-VACUOUS.
The first close-service mutation attempt matched two source sites and correctly
reported CONTROL-INVALID; the unique-boundary retry is the semantic control.
A missing generated JWT-key cache and incomplete synthetic API3 fixture first
failed setup; they are not product defects or negative-control evidence.

Commands, superseded logs, final logs and controls are indexed by local
`externals/work/HANDOFF-profile-writers-20261105.md` and the parent handoff.
Remaining scope includes every alarm/writer and emitted/provider path, complete
alarm-field equality, live DB-stat freshness, concurrent-read consistency,
quiet-hardware cost, logical subscriber policy, shared frames, release placement
and durable multitenant recovery. Reporter durations under pinned clocks are not
performance measurements.

<a id="run-46"></a>

### R46 - bounded PG consolidation and identifier races on 44331668 (2026-11-05)

**Parent-reproduced local cumulative acceptance** at
`44331668038dca5bc23af24c4125052b9c8e5612`,
`codex/pg-consolidation-integration-20261105`, from published R44 `bc4ee1a9`.
Fresh remote read-back reports #8898 OPEN/draft at R44 and independent #8891
OPEN/draft at R45 `dff9a8d4`; both published heads have successful CI and CodeQL.
Current fetched dev remains `4a482627bfdafb1fef8dcbe0ac6c484811cae563`.
New continuations remain local; no upstream merge, release or milestone promotion.

**Bounded production extraction:** `postgres-intent-common` shares only identical
projection/refusal mechanics, identifying-read order/options/normalization and
after-owned-transaction logical-event publication plus synchronous settle.
Entries and general-collection callers retain their independent translators,
natural-order and source-specific validation/write paths. Error labels, typed
identities, lower-versus-preview projection behavior, return shapes and swallowed
postcommit observer failures remain unchanged. This does not relocate every
Mongo compatibility helper or establish a universal portable backend interface.

The expanded real-port corpus tests entries-v3, general-v3 and general-legacy
selection/projection, actual mutation followed by rollback without publication,
independent postcommit visibility, source-specific IDs and synchronous no-transaction
settle. Identical corrected tests pass on the unchanged baseline and candidate in
UTC. Current legacy generated ObjectIds and v3 supplied raw identities remain
distinct rather than normalized into one policy.

**Direct compatibility expansion:** actual indexed Mongo/PG HTTP forces two
empty identifying reads and holds two real INSERTs; the winner commits before the
loser resumes. Actual duplicate errors11000/23505 must be observed. Four resend
modes assert replies, nested merge/null/removal behavior, raw winner identity and
independently allocated clocks against stored outcomes, one committed record,
foreign-tenant invariance and next-operation write-grant refusal. Only allocated
IDs/clocks are excluded across backends; stability/type are checked within each.
The hidden fixture Mongo environment is selected through the exact shipping
intent factory, not a new policy or deployment/config-parser acceptance. No
storage reply or duplicate error is manufactured.

| Parent-reproduced campaign | Passing | Pending | Failing |
|---|---:|---:|---:|
| Complete nonbrowser, final44331668 | 7051 | 80 | 0 |
| Complete default browser, e5796b32 with application source identical to final | 684 | 0 | 0 |
| Archived current common-adapter contract and existing unit checks | 75 | 0 | 0 |

Groups overlap. Full nonbrowser tiers: unit2157, DOM205, dependency368/2pending,
core319, harness93, integration3891/78pending, stress18. Node22.23.4,
PostgreSQL16.15, Mongo8.0.34, Vault2.2.1, UTC, seed41574423920; owned cleanup
finished. The nested port fixture separately measures Mongo7.0.43/PG16.15.
Classification500files/8tiers and changed-file lint pass. Browser was not repeated
for the final test-only timestamp correction; independent Git comparison confirms
unchanged lib/scripts/bin/migrations/static/package inputs. Final prcheck is OK
with the branch clean and current dev contained.

**Parent-reproduced semantic controls:** reverse shared identifying order and the
legacy selected-row sequence fails; omit shared included raw ID and the assertion
gets{}instead of the required identity; publish inside the transaction and a
verified mutating rollback exposes one false logical event instead of none.
Disable the duplicate retry and the indexed race loser returns500 instead of the
admitted resend200. Each selected control is0passing/1semantic failure; restored
positives pass. The selected consolidation, identity, race and independent profile
instruments report PASS/NON-VACUOUS. Independent read-derived source/fixture review
finds no blocking issue.

**Diagnostic failures retained:** the first added legacy commit fixtures assumed
the supplied raw ID survives creation; unchanged baseline and extraction both
failed68passing/2failing. Corrected assertions probe stable identifier and actual
source-specific raw kind. UTC then exposed missing-date fallback producing an
unsupported negative-zero utcOffset in the direct legacy fixture, also on the
unchanged baseline. The first cumulative all campaign ended7049passing/80pending/
2failing, not green. Explicit +01:00 synthetic timestamps with asserted legacy
offset60 isolate commit mechanics; production negative-zero refusal is unchanged.
Corrected baseline/candidate UTC ports pass70 repeatedly, and final full acceptance
above passes. These fixture findings are not runtime refactor defect claims.

Commands, controls, initial/final logs and source identity are indexed by local
`externals/work/HANDOFF-pg-consolidation-integration-20261105.md`,
`HANDOFF-pg-consolidate-20261105.md` and `HANDOFF-compat-consolidate-20261105.md`.
[Archived suite contract](../../../tools/lab/multitenant-next-slices/README.md)
requires committed sources, matching dependencies and owned synthetic services.
Historical release comparisons are not rerun or enlarged transitively by these
direct race tests. Remaining portable capabilities/helpers, settings/clients,
REST side effects, import/resources, owner identity/ceilings and production
lifecycle/durable recovery retain separate acceptance. R47 remains independent.

<a id="run-47"></a>

### R47 - independent shipping v1 evaluator replay on 0c98ad06 (2026-11-05)

**Independent test-only acceptance** at
`0c98ad06f8e01114639d58e1bc0724499af97f1f`,
`codex/evaluator-next-20261105`, over published #8891 R45 `dff9a8d4`.
Production `lib`, `scripts`, `bin` and `migrations` are unchanged. The executable
continues to expose its existing API3 prototype; shipping v1 entries/treatments
configurators are mounted only in an explicit test application over the actual
nonresident context. This is not production route/socket admission, a subscriber
switch, an RC join or a multitenant evaluator implementation.

Six new cases exercise real authorized v1 batch creation, identity resend,
treatment PUT and physical deletes plus all entries resend modes. They observe
actual persisted values/IDs, physical v1/internal and logical events, coalesced
retained cycles, full retained-property JSON and resident alarm-request signatures.
Selected BWP high alarms and treatment notifications must reach the live service.
V1 hard deletion and refusal409 inside a200 batch reply remain distinct from API3
soft deletion and HTTP409. V1 entries resend outcomes retain their existing merged
classification; tests do not normalize these differences or select logical-event
no-op admission. Acknowledged/refused resends keep zero physical cycles and the
previous retained cycle. Provider delivery and complete alarm-field equality are
outside this measurement.

| Campaign / evidence owner | Passing | Pending | Failing |
|---|---:|---:|---:|
| Agent-reproduced complete nonbrowser, parent-audited immutable anchor and tier totals | 6688 | 3 | 0 |
| Agent-reproduced complete default browser, parent-audited immutable anchor and totals | 684 | 0 | 0 |
| Parent-reproduced archived whole profile replay | 36 | 0 | 0 |

Groups overlap. Parent did not repeat the complete profile campaigns. Nonbrowser
tiers: unit2081, DOM205, dependency368/2pending, core319, harness92,
integration3605/1pending, stress18. Node22.23.4/Mongo8.0.34, UTC,
seed41574423920; shared runner PG16.15/Vault2.2.1 services are not evidence of PG
or multitenant evaluation. Agent whole/new-only replay36/6, lint/classification,
clean current-dev containment and final prcheck pass; owned services cleaned.

**Parent-reproduced controls:** suppressing actual write-trigger delivery leaves
persistence and the physical event visible but misses the required retained cycle
(0versus1); closing only the real notification service preserves request recording
but misses the required live BWP high emission. Each0passing/1semantic failure;
restored whole36passes. The declared expanded profile instrument is
PASS/NON-VACUOUS. Independent read-derived review found no blocking fixture,
handler/event or lifecycle issue.

The first new v1 case expected the prior single-reading fixture's AR2 alarm and
failed5passing/1failing. Actual resident/profile request signatures agreed: the
new earlier batch reading selects BWP's urgent high. The final assertion names
that observed producer and retains the prior API3 AR2 case; no production rule or
input normalization changed. Pinned-clock reporter durations are not costs.

[Source-pinned frame inventory](../../30-design/tenancy/architecture-seams-execution-plan-2026-11-05.md#shared-frame-inventory-and-next-characterization)
is read-derived: bounded acquisition, frame flags, error policy, tenant binding,
statistics and retained versus request-local lifecycle differ. No concurrency
experiment, database revision guarantee, shared-frame extraction or durable event
acceptance follows. Socket transport still has resident data/read assumptions.
Full writers/alarms, stats freshness, quiet cost, subscriber policy, shared frames,
release placement and M5/M6 recovery remain open. Commands, logs, controls and
inventory are in local `externals/work/HANDOFF-evaluator-next-20261105.md` and the
parent consolidation handoff.


<a id="run-48"></a>

### R48 - local public-token verification through actual API on 3d5eac19 (2026-11-05)

**Reproduced local application acceptance** on
`3d5eac196256e447859373beadf7abf2efbfb2ce`, branch
`codex/owner-local-auth-20261105`, a clean descendant of R46 `44331668`.
The [owner authority contract](../../30-design/tenancy/owner-authority.md) owns the adopted
policy; [application acceptance and log hashes](../../../tools/lab/owner-authority/results/2026-11-05-application-acceptance.json)
retain the campaign summary. This is locally fixed code, not merged/released or
published on #8898 by this lane. The coordinator has incorporated this clean
application commit into its separate frame-integration tree, pending its own
cumulative acceptance. No ancestry-based acceptance or milestone promotion.

**Actual application wiring:** explicit preview configuration admits trusted,
per-tenant Ed25519 public keys and a separately migrated access-state namespace.
The actual executable builds local authentication and the current read-only PG
snapshot adapter. The existing shared data-access permission/handler path consumes
that snapshot for every permission and current-name attribution in the operation.
No second REST stack or retained cross-request permission cache. The lab now
imports this application verifier; its original independent implementation is
retained only in the earlier pinned instrument history.

One tenant-bound SQL snapshot joins current tenant/session/credential-generation/
key acceptance with existing subject/default/role permissions. Serving identities
cannot mutate authority or own/bypass forced RLS. Public keys bind issuer, tenant,
key ID and data purpose; unknown keys/invalid new tokens refuse without legacy
fallback. Duplicate tenant key material, unsafe writer grants and disabled RLS
refuse before binding. Existing eight-hour legacy exchange and default single
behavior are unchanged. New-format data tokens remain capped at eight hours.

| Campaign on this application code | Reproduced result |
|---|---|
| `CRM_REST_WORKTREE=<owned CRM> node tools/lab/multitenant-rest-preview/owned.js all`, descriptor limit 64000 | 7058 passing / 80 pending / 0 failing; tiers 2157 unit, 205 DOM, 368 dependency (2 pending), 319 core, 93 harness, 3898 integration (78 pending), 18 stress |
| Same runner `browser`, own services | 684 passing / 0 pending / 0 failing |
| Complete executable process file, including existing compatibility/startup cases | 16 passing / 0 pending / 0 failing; this file also runs in the full integration campaign |
| Immutable `owner-local-token.js --ref 3d5eac19...` archive | 7 actual configured-executable new-format cases passing, no pending/failing |
| Actual-HTTP signature, audience, session and stale-snapshot mutations | Each 0 passing / 1 semantic assertion failure; scratch-only, restored source untouched |
| Tier/build/lint/final prcheck | 500 files / 8 tiers; own postinstall build passes; changed production lint has 0 errors and 4 inherited warnings; final prcheck OK after fetched official/dev merge reports already up to date |

Scopes overlap and are not summed. Node22.23.4, PG16.15, Mongo8.0.34,
Vault2.2.1, UTC seed41574423920. Services/databases are synthetic, individually
owned and cleaned. Full/browser runners verify unchanged source head and clean
tracked tree after the campaign. Published remote continuation is not inferred
from these local results.

**HTTP semantics reproduced:** own-tenant GET/POST/PATCH and v1 reads succeed;
POST keeps shipping `subject` and PATCH keeps `modifiedBy`. Permission discovery
still refuses an ordinary uploader without `admin:api:permissions:read`.
Tenant A's token on B fails with TOKEN_SIGNATURE, with successful own-key arms.
A new-token request leaves the real secrets audit count unchanged. The same
previous token observes committed grants/session/credential/key/tenant status
on the next read/write across independent API processes; refused writes produce
no stored record. Uncommitted removal remains invisible until commit.

With Vault paused, new-token reads/writes continue and current revocation still
refuses, while legacy verification answers503. With PostgreSQL paused, protected
new-token reads/writes answer503 before handler effects; after recovery the refused
write is absent. These are bounded blackhole/refusal tests, not crash/HA recovery.

**Break-it controls:** removing signature comparison or audience checking makes an
invalid token's actual POST answer201 instead of401. Removing session-active
checking makes a revoked session's GET answer200 instead of403. Reusing an earlier
snapshot makes committed grant removal's next GET answer200 instead of403. Every
mutant fails at the intended HTTP assertion; setup failure is not accepted as red.
See [raw control summary](../../../tools/lab/owner-authority/results/2026-11-05-http-controls.json).

**Repeated authorization-pipeline lab using the actual application verifier:**
16 semantic checks, 4 non-vacuous verifier/state controls, 24 timing cases/2880
operations. [Raw repeat](../../../tools/lab/owner-authority/results/2026-11-05-application-module.json)
pins instrument `f814f967c`, application `ab09297b` and application-module SHA256.
A direct git comparison confirms unchanged verifier bytes at final `3d5eac19`;
this carries the component measurement forward without relabeling its source head. At concurrency8, current
median reads18.904/18.572ms versus combined2.795/2.251ms; current writes18.764/16.396ms
versus combined2.152/2.153ms. Each pair is two repeats, not pooled percentiles.
Instrumented ordinary operations retain 2 versus0 Vault calls; current write uses
2 versus1 logical authority snapshots. The lab's combined candidate schema is
simpler than the application's new access-state join; these timings do not measure
that application's SQL adapter, end-to-end HTTP throughput or production capacity.
The [original prototype measurement](../../60-research/tenancy/owner-authority-local-verification-2026-11-05.md)
remains immutable and distinct.

**Acceptance boundary:** new-format keys/credential/session state are explicitly
operator-provisioned in this preview. Complete human/refresh-session issuance,
automatic migration of existing legacy exchange to the new format, complete owner
ceilings/ownership transfer and production key distribution/rotation/provider
acceptance remain open. Ordinary new-token verification is wired; this does not
mean all legacy clients now use that format or that M2/M6 is complete. No real
identities, production traffic, management listener or RC admission is enabled.
Protected stream/socket delivery and full multitenant producer/evaluator recovery
remain their separate M5 gates.

Initial new test expectations wrongly looked for `modifiedBy` on POST and allowed
uploader permission discovery. Source characterization confirmed POST `subject`,
PATCH `modifiedBy` and the separate admin permission; expectations were corrected
without changing those shipping behaviors. The original pilot's synchronous PG
shutdown race remains an unmeasured in-flight-recovery concern, as its record says.

Two additional same-persisted-state HTTP cases reproduced predecessor snapshot
compatibility gaps before correction: malformed duplicated defaults produced
legacy503/new200; a NULL display name produced legacy-read200/new503. Both new
cases failed on the predecessor application code (0 passing/2 failing). Final
`3d5eac19` validates unique defaults, preserves authorized incomplete-name reads,
and refuses unattributed PATCH401 before effects. The complete final file passes16,
and fresh full/browser acceptance above supersedes predecessor readiness. Independent
source review of the original integration and final delta found no additional
trust/isolation/privilege issue; its duplicate-default finding was addressed.


<a id="run-49"></a>

### R49 - cumulative frame acquisition and concurrent-read characterization on 1c55098a (2026-11-05)

**Tree:** `codex/frame-integration-20261105`
`1c55098a3d4bcf3d871bcd345f159ce444d6e458`, over R46, with R48 owner-authority
source and its compatibility corrections incorporated. Current `official/dev`
`4a482627bfdafb1fef8dcbe0ac6c484811cae563` fetched/merged before final campaigns;
merge already up to date. Frame changes add two registered integration fixtures;
no production shared-frame primitive or stronger consistency policy is introduced.
R50 remains an independent evaluator branch.

| Measurement | Reproduced result |
|---|---|
| `CRM_REST_WORKTREE=<owned frame worktree> node tools/lab/multitenant-rest-preview/owned.js all` | 7076 passing / 80 pending / 0 failing; tiers2157 unit,205 DOM,368 dependency (2 pending),319 core,93 harness,3916 integration (78 pending),18 stress |
| Same runner `browser` | 684 passing / 0 pending / 0 failing |
| Archived `multitenant-next-slices.js --suite frame-acquisition --ref 1c55098a3d4bcf3d871bcd345f159ce444d6e458` | 14 passing / 0 pending / 0 failing |
| Archived `multitenant-next-slices.js --suite frame-concurrency --ref 1c55098a3d4bcf3d871bcd345f159ce444d6e458` | 4 passing / 0 pending / 0 failing |
| Acquisition controls `tenant`, `bound`, `clinical`, `cache` | Each 0 passing / 1 semantic failure: foreign tenant200 instead of100; SGV alarm bound1 instead of12; clinical current-reading invariant; caller cache receives rows |
| Concurrency controls `partial`, `egress` | Each 0 passing / 1 semantic failure: real SQL42501 produces HTTP200 instead of503; blocked extra provider connection raises denied count2 instead of1 |
| Changed-file ESLint; `node scripts/test-tiers.js check`; whitespace | 0 errors / 6 warnings; 502 files across 8 tiers; PASS |
| Final `tools/review/prcheck/prcheck.sh` | PASS; clean exact final head still contains official/dev4a482627, no source merge needed |

Node22.23.4, PostgreSQL16.15, MongoDB8.0.34 and Vault2.2.1, UTC,
`TEST_SHUFFLE_SEED=41574423920`; each broad campaign owns separate disposable
services and verifies immutable clean source. Full commands and machine-local
artifacts are in `externals/work/HANDOFF-frame-integration-20261105.md`.

The six controls and restored14 acquisition/4 concurrency positives ran on
`3285ca4042ca00fc1b72e595eca8b6ad248952a3`; final1c55098a differs only in the
Mongo test-fixture cleanup described below. Control source boundaries and both
frame fixture files are unchanged. Final archived positives bind the exact final
head. No control is a setup error or a zero-test green.

**Acquisition:** actual shipping views, tenant snapshots and resident frame:false/
frame:true loaders read real Mongo/PG inputs. Selected BG/direction/uploader
battery/IOB agree on the admitted current cohort. Alarm/property SGV bounds,
future-entry/treatment/status behavior, food/activity, old sensor/pump records and
per-kind status bounds are explicitly compared. Real raw ObjectId and same-spelling
string identities both fetch, while computed-view union keys collapse the spelling;
framed loading retains both. This is a documented difference, not universal parity.
Views/snapshot reject a statistics failure; resident loading logs and continues
with empty statistics. Caller cache/ddata stay unchanged, tenant A/B row binding
is real, and tenant statistics exclude shared index bytes.

**Concurrent HTTP:** a barrier completes real entries SELECT before treatment
SELECT execution. An independent PostgreSQL client atomically commits new entries
and treatments; the actual response combines old entries with new treatments.
Before/after cohorts and foreign tenant B remain asserted. This reproduces the
absence of a common database revision; no new snapshot guarantee follows.
Actual permission revocation42501 returns503/TENANT_SNAPSHOT_UNAVAILABLE;
a temporarily renamed relation42P01 returns500/TENANT_SNAPSHOT_INTERNAL, each
as a complete error response with no partial data and restored200 afterward.
An exact owned-port socket guard admits only fixture PG/Mongo/HTTP endpoints;
its self-test and source control block provider connection attempts before any
external connection. Synthetic fixture provider is not real CLI/Vault acceptance.

**Diagnostic correction:** predecessor21fade full regression had two setup errors
in `storage.tenant-scope.test.js`: an earlier Mongo test left its deliberately
invalid URI in a shared configuration object, then teardown found no store.
The exact ordered pair reproduced24 passing/2 failing. A test-local environment
clone and explicit `assert.rejects` replace the earlier self-swallowing assertion;
corrected/restored pair25 passing/0 failing. A scratch success-return control
fails `Missing expected rejection`. These are test-only changes; product parsing
is unchanged. Other predecessor tiers/browser are historical scoped results,
not final cumulative acceptance. Final full results above supersede that failed run.

Fixture diagnostics also corrected a selector that accidentally intercepted stats
rows, parallel query trace ordering, shared stats-facade mutation and a vacuous
small-cache predicate. Final controls target actual document SELECTs, inspect all
callback traces, isolate the facade and assert exact untouched cache contents.
Owned-service cleanup runs on failure. Wider shared extraction, all clinical
cohorts, settings/plugin version keys, live stats/cost, logical no-op policy,
production human issuance/ceilings and M0-M6 completion remain open. No agent push.

<a id="run-50"></a>

### R50 - independent evaluator frame characterization on 5173864d (2026-11-05)

**Tree:** `codex/evaluator-frame-20261105`
`5173864da1835da7aecf1f73121b28463f6a6a70`, over R47. Test-only additions
in `tests/views-profile.test.js` and its owned read-barrier helper; application
source unchanged. Contains `official/dev` `4a482627`. Independent of R49 REST;
no executable v1/socket admission, subscriber switch or release placement.

| Measurement | Reproduced result |
|---|---|
| Agent `npm run test:all`, owned MongoDB, `/tmp/evaluator-frame-full.log` | 6690 passing / 3 pending / 0 failing; 2081 unit, 205 DOM, 368 dependency (2 pending), 319 core, 92 harness, 3607 integration (1 pending), 18 stress |
| Agent default `npm run test:browser`, `/tmp/evaluator-frame-browser.log` | 684 passing / 0 failing |
| Parent archived `node tools/queue/gates/multitenant-next-slices.js --suite profile --ref 5173864da1835da7aecf1f73121b28463f6a6a70` | 38 passing / 0 failing; restoration after both new controls also 38 |
| Same archived gate `--control frame-clinical` | 0 passing / 1 semantic failure: next real-trigger BG241 instead of240 |
| Same archived gate `--control frame-retention` | 0 passing / 1 semantic failure: null replaces exact prior kept properties/timestamp |
| Agent final `tools/review/prcheck/prcheck.sh` | PASS; current dev contained, clean tree; parent read-only barrier/lifecycle review found no bounded-claim blocker |

Actual evaluator acquisition is triggered by `ctx.entries.create`, not a
manufactured event. An after-read barrier holds actual Mongo entries A while a
before-read barrier delays treatments. Independent raw writes commit entries B,
then treatments B; these writes emit no process event. The retained cycle is A/B,
not the explicitly observed intermediate B/A; the next real marker write triggers
B/B. Selected retained BG/COB values are asserted at both cycles. This is one
deterministic schedule, not a universal consistency or cross-process-delivery
contract.

A selected callback fault injected **after real rows arrive** increments the error
counter, retains the entire successful prior result and timestamp and performs no
notification handoff; the next real trigger recovers. It is not a real database
outage. The late-read teardown case fetches a fresh synthetic row and proves no
late fake-provider delivery/listener, not database cancellation, prevention of
internal handoff, or immutability of closed evaluator state. Each new cohort owns
and closes its notification service and restores clock/statistics fixtures.
Live statistics freshness, runtime cost, logical no-op subscriber policy, complete
alarm/writer cohorts and multitenant durable recovery remain open.

Diagnostic correction: the existing late-read fixture used an aged fixed date
and returned no rows under the restored real clock; a fresh raw synthetic row
makes the intended late-row assertion meaningful. No production behavior changed.
Commands, ownership and local artifacts:
`externals/work/HANDOFF-evaluator-frame-20261105.md`.

<a id="run-51"></a>

### R51 - bounded settings differential on 33870764 (2026-11-06)

**Tree:** `codex/settings-differential-20261105`
`338707648c43dea190cf47f3d64d6f8d2bcde56c`, over accepted R49
`1c55098a3d4bcf3d871bcd345f159ce444d6e458`; contains official/dev
`4a482627bfdafb1fef8dcbe0ac6c484811cae563`. Root
`codex/serial-integration-20261106` fast-forwarded this exact application tree.
Independent R50 remains separate; A/C/D/clock are not joined. Five changed files,
seven additive commits; the only product edit raises global PG sort cap4→5.

| Reproduced measurement (logs independently read and manifest hashes verified) | Result |
|---|---|
| Owned final `npm run test:all`, `settings-evidence-20261106/full-fixed.log` | 7089 passing /80pending /0failing: tiers2158/205/368/319/93/3928/18 |
| Owned default `npm run test:browser`, `browser.log` | 684passing /0pending /0failing |
| `node scripts/test-tiers.js check`; final `tools/review/prcheck/prcheck.sh` | 503files/8tiers PASS; final prcheckOK, current dev contained, source clean |
| Actual settings focused repeats; settings+profile/food ordered pair | 12/0 twice; pair25/0 |
| Parent `node tools/queue/gates/multitenant-next-slices.js --suite settings --ref 338707648c43dea190cf47f3d64d6f8d2bcde56c` | 12passing /0failing; restored invocation12/0 |
| Same gate `--control sortcap` | 0passing /1semantic failure: actual HTTP500 instead of200 |
| Same gate `--control predicate` | 0/1semantic: selected exact-row result includes synthetic distractor |
| Same gate `--control projection` | 0/1semantic: raw storage projection leaks synthetic private fields |

Gate source was alignment `40d1dfb859e6d110c3267b9066b90ee95a666764`, archived
with matching candidate private dependencies and fresh owned Mongo/PG/Vault.
These are assertion failures, not setup/anchor failures. Source controls at
application-identical predecessor0a also cover predicate/projection, cross-binding
and restored cap4; cross-binding proves a forbidden operation completed, not which
rows changed. R48 existing stale-authority control remains its own entries proof,
not new settings token proof. Final candidate full new-token suite passes.

**Diagnostic correction:** earlier0a full failed profile/food setup with duplicate
Vault transit mount HTTP400; ordered pair reproduced12settings passing+1setup
failure. Fixture-only commits use unique mount names, successful-create ownership
and owned-only DELETEfinally. Pair25/0 and complete final full/browser were rerun
at338; application source after0a is unchanged. This failure was not ENOSPC.
Earlier ENOSPC/NUL/truncated campaigns remain unaccepted and individual numbered
failures are not all assigned to capacity without isolation.

Synthetic actual settings preserve supported scalar filtering/sorting/projection,
current authority and mutation contracts with six-key sort refusal. Regex and
dotted predicates retain sanitized PG500 capability refusals. No client binary,
all-query parity, sort-cost performance, cross-process history/revision or full
owner lifecycle acceptance. R49/R50 are retained historical captures. No M0–M6
promotion or final combined A/C/D/clock acceptance.

**Separate infrastructure reproduction:** actual source cleanup blocks from
ddd3334d cover4runner/gate success/controlled-failure cases, continued attempts,
private0700/0600 diagnostics and6owned anonymous volumes independently absent.
Five archived settings audit files verify15owned containers and25recorded volumes
absent. Authorized inventory cleanup3779/3779,0errors/no outside-inventory loss;
B75recorded new volumes absent and219preserved volumes present. Unknown40nested
volumes remain preserved; this does not prove complete cleanup. New canonical
all registration fromd0d60fa6 has not run a future combined campaign.

Private command/log homes: `externals/work/settings-evidence-20261106/` and
`externals/work/resource-cleanup-scratch/`. Acceptance manifest SHA256
`2802b42bd27d13e90b043ae1fc89bff5e91ea607ae6f55b412683a6279282f81`;
all listed artifact hashes independently verified. Lane handoffs:
`HANDOFF-settings-verification-20261106.md` and
`HANDOFF-cleanup-settings-runtime-20261106.md`. B slot released, A now active;
no service campaign or deletion performed by this records lane. No push.

<a id="run-52"></a>

### R52 - native private acquisition extraction on e5fe0b5e (2026-11-06)

**Native tree:** `codex/private-acquisition-extract-20261105`
`e5fe0b5ed2e5cdc1c7841320d898128673095e9f`, over historical accepted R49
`1c55098a3d4bcf3d871bcd345f159ce444d6e458`; contains official/dev
`4a482627bfdafb1fef8dcbe0ac6c484811cae563`. Production extractionee480a96,
independent tests9c39e819, unit registratione5fe0b5e. Native acceptance below is
separate from root B+A composition `c77784360076f9cd3e7a8b41700b0b9468378c7b`,
whose combined full verification is PENDING. R51 and preceding records are unchanged.

| Reproduced measurement, independently read from local captured logs | Result |
|---|---|
| Fresh owned `npm run test:all`, `full-recovery-20261106.log` | 7080passing /80pending /0failing, exit0; tiers2161/205/368/319/93/3916/18 |
| Prior same-native-head default `npm run test:browser` | 684passing /0failing, exit0; not rerun after capacity recovery |
| Final `tools/review/prcheck/prcheck.sh`, `final-prcheck-20261106.log` | OK; fetched current dev contained, source clean/frozen |
| Archived `node tools/queue/gates/multitenant-next-slices.js --suite frame-acquisition --ref e5fe0b5ed2e5cdc1c7841320d898128673095e9f` | 14passing; restored14 |
| Same instrument `--suite frame-concurrency` | 4passing; restored4 |
| Acquisition `--control tenant`, `bound`, `clinical`, `cache`; concurrency `--control partial`, `egress` | Each0passing/1semantic failing, exit1; restored14/4 |
| Actual loader caller ownership/error unit tests | 4passing; scratch reused-target mutant0passing/2ownership assertion failures; restored4 |
| Updated instrument on historical1c55098a cache control | 0passing/1semantic untouched resident-cache failure; restored14 |
| Root B338+A tier registration, not native full acceptance | 504files/8tiers PASS; combined full PENDING |

Native environment: Node22.23.4, PG16.15, Mongo8.0.34, Vault2.2.1, UTC,
seed41574423920. Groups overlap and are not additive. Updated cache instrument
alignment334dc571 selects historical cache reuse or extracted acquired-SGV leakage
with exact non-ambiguous anchors; neither silently skips missing anchors. No
accepted worktree is modified by its scratch controls.

The26-line helper owns fresh context/helper-data/bus, private cache and loader
target, preserving existing loader invocation. Views/snapshot retain queries,
bounds, frame/future/statistics policy, string-key typed union, authority and
complete-error/lifecycle differences. The actual loader unit proof is not database
consistency proof. No common revision, stronger snapshot or default single/Mongo/
evaluator behavioral admission is inferred.

Earlier ENOSPC/NUL/truncated exit7 full attempt remains unaccepted historical
evidence; the fresh completed recovery log contains all seven tier summaries and
cleanup marker. A supplemental no-NUL assertion found the intentional unsupported
nul-key fixture diagnostic; exact byte inspection distinguishes this from earlier
truncation. The campaign itself exited0 without source/expectation changes.
Outer audit independently verifies3owned containers/5recorded anonymous volumes
absent; nested old fixture ownership was not audited, unknown/orphan volumes were
not deleted and no zero-leak guarantee follows.

Independent evaluator helper preparation
`2ee8b493d76ddf92bf53d5e5c9cf0d9d0d2dbb35` descends from accepted
`5173864da1835da7aecf1f73121b28463f6a6a70`. Helper blob
`3a97307af1e749e98b99f2955182e6844c331441` matches native REST exactly;
views-only integration preserves evaluateCycle. All new-head runtime38/controls/
full/browser/prcheck are UNMEASURED, pending separate slot. No REST join,
subscriber/notification or production role admission.

Local evidence home: `externals/work/private-acquisition-evidence-20261105/`,
including recovery summary/log, final prcheck and owned cleanup audit. Exact
commands, scoped controls and ownership:
`externals/work/HANDOFF-private-acquisition-extraction-20261105.md`.
Native A step finished. D/clock lower proof active with HTTP/full/bench acceptance
pending, Cqueued; no new clock acceptance allocation. No M0–M6 promotion,
application push or combined full acceptance.

<a id="run-53"></a>

### R53 - selected owner proposed-grant policy on 17f9a457 (2026-11-06)

**Native tree:** `codex/owner-enforcement-20261105`
`17f9a4577e649208ada6b0aa8f83c51026459875`, over historical accepted R49
`1c55098a3d4bcf3d871bcd345f159ce444d6e458`; current official/dev
`4a482627bfdafb1fef8dcbe0ac6c484811cae563` contained. Native acceptance below
is not combined acceptance: root B+A+C `4a15802cc1fe5ecb60b5985cd0aff9b2d57eed37`
has tier506files/8tiers PASS but combined full PENDING. No clock/profile2ee join.
R51/R52 and earlier captured records are unchanged.

| Reproduced native result, independently read/hash-verified from local logs | Result |
|---|---|
| Owned `npm run test:all`, `full-17.log` | 7127passing/80pending/0failing, tiers2186/205/368/319/93/3938/18; all22owner bodies executed |
| Default `npm run test:browser`, `browser-17.log` | 684passing/0pending/0failing |
| Final `tools/review/prcheck/prcheck.sh`, `prcheck-17.log` | OK, current dev contained, native source unchanged/clean |
| Actual owner database/affected existing subject-PG-management corpus | 22/0 and26/0 at17f |
| Catalogue/Shiro plus existing subject unit | 29+3=32positive; four negative guards not added to positive count |
| Parent `node tools/queue/gates/multitenant-next-slices.js --suite owner-policy --ref 17f9a4577e649208ada6b0aa8f83c51026459875` | 22passing/0failing; restored22/0 |
| Same archived gate `--control catalogue`, `ceiling`, `delegation`, `actor` | Each0passing/1ERR_ASSERTION, actual HTTP200vs403 with persisted effects |

Parent instrument source was alignmenta08947484eebb1123f03f1c38a73099591399059.
Fresh private services per capture; all6recorded containers/6volumes independently
absent, modes0700/0600. Controls are semantic failures, not setup/zero-test errors.
Earlier product-identical3106 actualDB22 twice/restored22 and guards remain scoped.
Only17f fixture correction expects migration003+004, applies prior3 before004 and
compares all prior3 stored checksums. Initial affected25/1 retained; corrected26
passes, no production guard weakened. Native registered504files/8tiers; root506/8
is the combined registration result, not native full proof.

Explicit ownerPolicy uses existing subject mutation transaction with proposed
grants constrained by reviewed catalogue ∩ locked operator ceiling ∩ current
matching management actor delegation. Authority/current actor row fencing extends
through subject/credential mutation and audit. Selected REST37 only; DELETE
refuses and managementAuth is injected. Full wildcard/default catalogue, human
issuer/refresh, existing-grant clamping, DELETE policy and production listener
remain unimplemented. R48 data-token readers unchanged; full native new-token7
functional checks pass without becoming throughput/capacity proof.

Current narrowing before proposal locks refuses; a proposal holding authority
locks may complete before a waiting revoker commits, then the next proposal sees
narrowing. These orderings do not establish cancellation/total deadlines or
arbitrary lock-order guarantees. Native full records18containers/26volume
references, browser3/5, final database1/1 and affected2/2, all recorded absent.
Unknown unrelated resources remain untouched; no global cleanup guarantee.

Public [native acceptance](../../../reports/owner-subject-policy-acceptance-2026-11-06.md)
and [machine capture](../../../tools/lab/owner-subject-policy/results/17f9a457-acceptance.json)
record original output hashes/environment/controls. This records lane acceptance;
root combined full and clock/profile work remain pending. Clock lower report8+
controls/oldSQL42703/corrected9 is separate; no clock HTTP/full/bench acceptance
is allocated here. Canonical clock correctness flags source registered for future
combined run, benchmark off. No milestone/RC/production listener admission or push.
Local final evidence: `owner-enforcement-campaign-20261106/` and
`owner-archive-gate-runtime-20261106/summary.json` plus lane handoffs.

<a id="run-54"></a>

### R54 - cumulative settings acquisition and owner policy on 35903069 (2026-11-06)

**Cumulative tree:** `codex/serial-integration-20261106`
`35903069b46974cfbaddd8dce00c994fb2562bc3`, composing native R51 settings338,
R52 private acquisitione5 and R53 owner policy17f. Contains current official/dev
`4a482627bfdafb1fef8dcbe0ac6c484811cae563`; final native source unchanged/clean.
Final359 after4a158 only rewrites settings-test normalization to delete three
server-owned fields from cloned documents without unused bindings. No product
scope change. R51–R53 and all earlier captures are unchanged.

| Reproduced final-tree result, independently read and SHA256-verified | Result |
|---|---|
| Owned actual settings differential | 12passing/0pending/0failing |
| Owned `npm run test:all` | 7144passing/80pending/0failing; tiers2191/205/368/319/93/3950/18 |
| Owned default `npm run test:browser` | 684passing/0pending/0failing |
| Changed JavaScript lint | 0errors/0warnings |
| Fresh final `tools/review/prcheck/prcheck.sh` | OK, currentdev contained, final source unchanged/clean |

Pending totals are dependency2 plus integration78. Scope totals overlap and are
not additive. Canonical runner alignmente739c466; private bundle built before
campaigns. First sandboxprcheck attempt failed DNS beforefetch and is preserved;
the accepted freshretry completedOK. No failed/setup output counted as acceptance.

Native controls remain separately captured in R51–R53. This cumulative regression
does not relabel those mutations as fresh controls of359 or imply complete
ST-PG/client/owner/lifecycle acceptance from counts. Explicit ownerPolicy REST37
retains injectedmanagementAuth/refusedDELETE; fullwildcard/defaultcatalogue,
humanissuer/refresh, existing-grant clamping and productionlistener unimplemented.
R48 data-token readers unchanged. Private allocation retains caller policy/error/
lifecycle differences, adds no atomicrevision/common snapshot.

Successful captured settings3containers/5volumes, full18/26 and browser3/5 are
independently absent afterward; all219preserved volumes present, directories0700/
files0600. Bounded successful-campaign audit, not global leak freedom. Clock and
independent profile2ee not joined; clockHTTP/full/bench acceptance separately
pending. No new Dresult, M0–M6/RC promotion, defaultproduction enablement or push.

[Public record](../../../reports/tenancy/serial-cumulative-acceptance-2026-11-06.md)
and [machine capture](../../../reports/tenancy/serial-cumulative-acceptance-2026-11-06.json)
contain exact inputpins/counts/hash-only original-output index and sanitized
cleanup aggregates. Local source manifestSHA256
`348c35f65831664479e6b0b263453206091a0c783d6e0675cf17bed71056a9c2`;
all six listed artifacts independently verified. No services or cleanup run by
records lane.

<a id="run-55"></a>

### R55 - independent private acquisition profile on 2ee8b493 (2026-11-06)

**Independent tree:** `codex/private-acquisition-profile-prep-20261106`
`2ee8b493d76ddf92bf53d5e5c9cf0d9d0d2dbb35`, over accepted R50
`5173864da1835da7aecf1f73121b28463f6a6a70`. Current official/dev
`4a482627bfdafb1fef8dcbe0ac6c484811cae563` contained; fresh finalprcheckOK,
HEAD unchanged/clean. REST359 and PROFILE2ee remain separate accepted branches,
not merged. R50–R54 captures are unchanged.

| Reproduced result, independently read and original-output hash verified | Result |
|---|---|
| Owned fresh `npm run test:all` | 6690passing/3pending/0failing; tiers2081/205/368/319/92/3607/18 |
| Owned fresh default `npm run test:browser` | 684passing/0pending/0failing |
| Canonical `node tools/queue/gates/multitenant-next-slices.js --suite profile --ref 2ee8b493d76ddf92bf53d5e5c9cf0d9d0d2dbb35` | 38passing/0failing; restored38 |
| Same gate `--control http` | 0passing/1semantic: suppressed actual HTTP physical-write trigger does not refresh retained cycle |
| Same gate `--control frame-clinical` | 0/1semantic: actual next-trigger currentreading differs |
| Same gate `--control frame-retention` | 0/1semantic: failed materialization loses prior successful timestamp/properties |
| Final `tools/review/prcheck/prcheck.sh` | OK, currentdev contained/sourceclean; changed ESLint/tier/writeboundary checks pass |

Notification-close `v1-closed` is a distinct fourth declared current-ref control:
its2ee runtime is UNMEASURED, prior517 measurement is historicalR50. It was not
one of the three measured R55 reds. The38positive suite retains fresh notification
service/live-handoff assertions. Teardown proves no late fake-provider delivery,
not DB cancellation, absent internal handoff or immutable closed evaluator state.

Only helperlib/data/private-acquisition.js and views allocation/loader hunks change
from517; helperblob3a97307af1e749e98b99f2955182e6844c331441 matches REST exactly,
evaluateCycle retained. Caller policies for bounds/future/statistics/typedunion/
retainedcycle remain; selected mixedA/B then realtriggerB/B and selected callback
failure retain their bounded meaning. No commonrevision, stronger snapshot, full
writer/clinical/alarm/recovery/cost acceptance or defaultsubscriber/runtime-role
change. Outer PG/Vault services supplied by broad runner do not establish PG
evaluator behavior. Captured7serial campaigns/11containers/20volumes all recorded
absent; unknown/named/attached resources and failed creates without IDs outside audit.

[Canonical profile report](../../../reports/private-acquisition-profile-2026-11-06/README.md),
[acceptance capture](../../../reports/private-acquisition-profile-2026-11-06/acceptance.json)
and additive [artifact index](../../../reports/private-acquisition-profile-2026-11-06/artifact-index.json)
were adopted without altering original capture/README. All22indexed artifact
lengths/hash verified. AcceptanceSHA256
`9645a8d630f874877466e46186f55b75db97714a195cb2d726e89b0ca2eb73c4`;
indexSHA256`b30cddb2184d214b2ffa04b90063ea4674b14a6dc5cca19fe455e2dd7bbe2f75`.

Separate [focused clock recovery](../../../reports/tenancy/tenant-clock-http-fixed-recovery-2026-11-06.md)
is not numbered clock acceptance:3532/117 functional7/1benchmarkpending,
negative0/2(primarylostHTTP/ECONNRESET, secondarystrict workerexit1), restored1
with503/same-workerGET200/POST201/strict0. Originalfataldiagnostic retained;
clockcode notjoined/default-off, assembledsingle/Mongo/full/browser/prcheck,
broadercontrols/performance UNMEASURED. No M0–M6/RC promotion or application push.

<a id="run-56"></a>

### R56 - frozen clock join on 65bb8456 (2026-11-06)

**Frozen join:** `codex/clock-join-20261106` `65bb8456618df9816106692a32f0dd5c76e216d1`
= accepted R54 `35903069b46974cfbaddd8dce00c994fb2562bc3` + clock lane
`11770146b420a2aa1ccad587030bfee50a8ea0b3` + clock HTTP lane
`3532c1a46d6fc3fb2100ed7704544d278f29357b` (merge base `1c55098a`; conflicts in
`tests/tiers.json` only, union; no `lib/` difference between the two clock heads).
`official/dev` `4a482627bfdafb1fef8dcbe0ac6c484811cae563` contained; final prcheck OK,
HEAD unchanged and clean. Local and unpushed; not published to #8898. Batch B2 of the
[batching plan](../../30-design/tenancy/multitenant-integration-batching-plan-2026-11-06.md).

| Reproduced result, independently re-read from the logs with hashes | Result |
|---|---|
| Owned `owned.js clock` (unit, lower-port, HTTP) | 28 passing / 1 pending (benchmark opt-in) / 0 failing |
| Owned `owned.js all` | 7187 passing / 81 pending / 0 failing; tiers 2213 / 205 / 368+2 / 319 / 93 / 3971+79 / 18 |
| Owned `owned.js browser` | 684 passing / 0 pending / 0 failing |
| Serialization ablation (drop `FOR UPDATE`), `--grep holds` | 0 / 3: no clock-row lock wait observed (lower-port x2); HTTP clock-select completed before its lock wait; restored 3 / 0 |
| Readiness ablation (bypass stale-floor throw), `--grep provision` | 0 / 2: missing expected rejection; refused configuration bound; restored 2 / 0 |
| Rollback ablation (clock advanced after data rollback), `--grep rolls back` | 0 / 3: floor advanced by one; failed insert committed a clock allocation; restored 3 / 0 |
| Final `tools/review/prcheck/prcheck.sh` | OK, dev contained, source unchanged |

Passing rises by 43 over R54: 22 new unit cases, lower-port 9, HTTP 7 and five
test-only cases of the unaccepted replica candidate `714f6c8b`, which the HTTP fixture
requires and which rides along without any claim about its own controls. Changed-JS
lint: 0 errors in `lib/`; six pre-existing test-file errors on `3532c1a4` left for that
lane. Nine runner runs, 27 containers and 45 volumes audited absent by inspection.
Contention/latency benchmark, Mongo comparison, mixed writers, bulk ties, SIGKILL
cleanup bound and CI on this head remain UNMEASURED. Clock opt-in, default off. No
M0–M6 promotion, no application push.

[Canonical report](../../../reports/tenancy/tenant-clock-join-2026-11-06.md) and
[machine capture](../../../reports/tenancy/tenant-clock-join-2026-11-06.json).

<a id="run-57"></a>

### R57 - frozen-head controls stopped on invalid authority instrument (2026-11-06)

**INCOMPLETE, no B4a acceptance.** Frozen CRM `65bb8456618df9816106692a32f0dd5c76e216d1`, alignment base `88902eba2532c42bf83a91a8104f9ea64da2ca18`. Reproduced captured logs: 11/12 positive instruments, 27 semantic-red controls, 1 invalid control, 8/12 restored instruments. Owner-policy/settings originals were re-read without rerun. Profile excluded because absent on this head.

`rest-authority --control authority` exits 1 before Mocha: `CONTROL-INVALID: expected source boundary missing`. Read-derived cause: the gate searches `authority.authorize` while frozen data-access uses `currentAuthority.authorize`. This is not semantic evidence. No source repair, queue ref move, milestone promotion, default enablement or push. B5 acceptance prerequisite remains unsatisfied. Missing controls/restores and subject-admin remain UNMEASURED.

Earlier local classifier stop (Supertest Error rather than AssertionError) is preserved and manually classified by its intended HTTP500 versus503 assertion. The control was not rerun. Runtime released on mismatch; identified gate-owned cleanup audited, older fixture anonymous volumes preserved with ownership limits. [Partial report](../../../reports/tenancy/gate-controls-65bb8456-2026-11-06.md) and [machine capture](../../../reports/tenancy/gate-controls-65bb8456-2026-11-06.json) retain exact symptoms, per-suite counts, artifact hashes and limitations. Local handoff: `externals/work/HANDOFF-codex-b4a-20261106.md`.

<a id="run-58"></a>

### R58 - frozen-head B4a controls complete after instrument repair (2026-11-06)

**Bounded gate evidence complete:** unchanged application `65bb8456618df9816106692a32f0dd5c76e216d1`; authority instrument `3845b3a156e19fec77b9bb495117c12403a5a953`, other instruments unchanged. R57 remains an immutable incomplete capture. This continuation adds ten runs and combines them by instrument: **12 positive instruments, 32 semantic controls, 12 restored positives**. Profile excluded because absent on this head.

Reproduced: repaired authority3passing/2failing (expected401/503got200), audience4passing/1failing(expected401got200), restored5; subject-admin positive13, current/tenant/atomic each0passing/1failing, restored13; owner restored22/settings restored12. All positive/restored runs have0pending/0failing. Authority controls fail HTTP assertions before later effect checks; no separately quantified mutated-effects claim. Original invalid control and local classifier stop remain preserved.

Runtime released after complete measurements; recorded gate-owned cleanup audited, older fixture anonymous volumes preserved. No application change, queue ref move, milestone promotion, default enablement, full/browser/corpus run or push. B5 joined-head acceptance remains separate. [Continuation report](../../../reports/tenancy/gate-controls-65bb8456-continuation-2026-11-06.md) and [machine capture](../../../reports/tenancy/gate-controls-65bb8456-continuation-2026-11-06.json) retain exact symptoms, artifact/source hashes and cleanup limits. Local handoff: `externals/work/HANDOFF-codex-b4a-20261106.md`.

<a id="run-59"></a>

### R59 - completion-batch source incorporation and recovery model (2026-11-06)

**Source-stage evidence only:** Batch A application `863c8a2b3fa7ac3e13ecb5f7dca90de6766bb7e0`
incorporates the corpus inventory repair, typed role table and narrow M4
identity/literal-slash repairs. Reproduced selected CLI/role/filter/write-intent
checks: 201 passing, no failing or pending cases; tier registry 512 files / 8 tiers;
corpus source inventory 34 opt-in suites. No fixtures started by this selection.

Separately, coordinator independently ran the isolated recovery model at
`25c8441a861fb3d8f9aff3f559d833f2db8ab448`: 8 passing / 0 failing / 0 skipped.
Its crash case uses a synthetic file-backed commit and child SIGKILL, not PostgreSQL.
It evaluates recovering projection and checkpoint together; production bootstrap,
checkpoint bookkeeping authority and concurrent-current-row replay remain unresolved.

The [immutable source capture](../../../reports/tenancy/completion-batch-source-checks-2026-11-06.md)
owns commands and scope. Application full/browser/enabled corpus, actual-client
rerun, database recovery/RLS and final prcheck remain UNMEASURED on these heads.
No application-ready claim, queue-ref move, milestone promotion or default change.
The approved completion schedule spends comprehensive V&V at frozen batch
boundaries, with targeted evidence during implementation. Production decisions
are deferred, research continuing.

<a id="run-60"></a>

### R60 - coherent CI client batch and M0 foundations (2026-11-06)

**Accepted bounded batch:** `d89a44e182e771ef84aa99190ec166e6ff0d9772`, containing
`official/dev 4a482627bfdafb1fef8dcbe0ac6c484811cae563`. The batch repairs the
opt-in corpus inventory/provisioner, adds the typed role table, and preserves
legacy client identity, literal-slash lookup and refusal-envelope behavior.

| Reproduced measurement | Actual executed head | Passing / pending / failing |
|---|---|---|
| Full nonbrowser, seven tiers | `c0e8ad3c` | 7207 / 81 / 0 |
| Default browser | `c0e8ad3c` | 684 / 0 / 0 |
| Registered actual-client gate, cgmsim and oref0 | `c0e8ad3c` | 82 checks / 0 failing; 19 paired cells, 0 differences/missing cells |
| PgBouncer connection/RLS and typed-identity groups | `c0e8ad3c` | 9 and 4 passing; paired breaks observed and restored |
| Entire expanded corpus, 34 suites | `d89a44e1` | 441 / 1 / 0 |
| Final prcheck, last application gate | `d89a44e1` | exit 0, OK; clean unchanged head |

The single pending corpus case is an explicitly disabled performance benchmark,
not a functional pass. Full-suite pending cases remain named pending. Totals
overlap and are not added. Independent source comparisons prove **only**
`scripts/test-multitenant.js` and its documentation differ between the two heads;
all other paths, including serving code, tests, CLI and dependency manifests,
are identical. The ancestor runs are reused on that basis, not relabelled as
fresh executions on d89. No full/browser/client repeat was spent on a runner-only
change. [Final capsule and source identity](../../../reports/tenancy/batch-a-acceptance-d89a44e1-2026-11-06.md).

The [failed corpus attempt](../../../reports/tenancy/batch-a-acceptance-attempt-c0e8ad3c-2026-11-06.md)
is preserved: 432/1/1, clock-port before-hook refusal of the provisioner's
`/postgres` database name. The repair initializes, selects and probes the same
explicit test database; the safety assertion is unchanged. Focused corrected
clock-port execution produced 9/0/0 before the final whole-corpus run.

The [actual-client capture](../../../reports/m4-client-binaries/2026-11-06-revised-freeze/README.md)
retains pinned-source/build provenance, strict refusal/no-effect checks, six
wrong-oracle assertion failures, one planted unexplained reply and green
restoration. Connector observations remain scoped to their ancestor capture.
The [pooler proof](../../../reports/tenancy/batch-a-foundation-c0e8ad3c-2026-11-06.md)
uses two clients/one backend in transaction pooling and demonstrates RLS,
BYPASSRLS, session-binding and typed-kind controls. Its historical DDL is not
substituted for current migration/process acceptance in the expanded corpus.

**Criterion disposition:** M0 foundations promoted: restricted roles, overlapping
identities, unbound refusal, tenant isolation, rollback/cleanup, physical pool
reuse, paired breaks and current schema/startup refusal are measured. The explicit
lab preview remains consistent with D21; no default or production role is enabled.
The bounded M4 client-lab card is complete after canonical integration. M1–M6
are not promoted: populated import/order and broader resource behavior, control-plane
composition/lifecycle, wider client coverage, durable consumers and operations
retain their explicit criteria. Parent R57/R58 controls keep their original scope.

Root independently verified 26 raw B5 artifact hashes and the five final M4 run
hashes. Cleanup is limited to observed campaign resources; older unknown resources
remain preserved. B7 direction approval has also been reconciled from its separate
decision lane; the earlier draft wording was stale documentation, not a missing
maintainer authorization. Dormant owner and runtime/operations implementation
branches remain separate from this accepted compatibility batch. Remote publication
and CI are recorded separately after execution; no operator release is claimed.

<a id="run-61"></a>

### R61 - published batch remote CI and CodeQL verification (2026-11-06)

**Reproduced remote read-back:** draft PR #8898 points to the exact accepted
`d89a44e182e771ef84aa99190ec166e6ff0d9772`. Normal fast-forward publication is
verified; no merge to dev, release/tag or default enablement occurred.

[Application CI](https://github.com/nightscout/cgm-remote-monitor/actions/runs/42296422151)
completed successfully: 15 jobs succeeded, including the opt-in corpus, all
three browser engines, maintained MongoDB, ordinary database/no-database matrices
and runtime/build validation. Three release-image build/publication jobs were
skipped by the PR workflow conditions. The previous inventory/provisioner CI
failure is resolved on this head.
[CodeQL](https://github.com/nightscout/cgm-remote-monitor/actions/runs/42296422116)
also completed successfully. The PR remains draft and its description now cites
the accepted head, actual execution/reuse boundaries and successful remote runs.

Accepted alignment records at `ed18a7bceb096fc52e155fc5a005106f7e91263d` were
published and their [CI/site workflow](https://github.com/bewest/rag-nightscout-ecosystem-alignment/actions/runs/42296363495)
passed. The [immutable publication snapshot](../../../reports/tenancy/batch-a-publication-d89a44e1-2026-11-06.json)
records job names, conclusions and exact source scope. R60's benchmark pending
case and remaining M1–M6 criteria are unchanged by remote CI success. Later owner,
replay and populated-recovery branches remain outside this published batch.

<a id="run-62"></a>

### R62 - bounded owner reader replay and populated recovery batch (2026-11-06)

**Accepted local candidate:** `83582e876dd193f4448f44c28e379fb5464a26c7`, containing
`official/dev 4a482627bfdafb1fef8dcbe0ac6c484811cae563`. This joins optional
subject-reader catalogue/current-ceiling clamping, dormant durable current-row
projection/checkpoint replay, and a populated PostgreSQL dump/restore laboratory.
All options remain unselected; no listener or production role is enabled.

| Reproduced measurement | Actual executed head | Passing / pending / failing |
|---|---|---|
| Full nonbrowser, seven tiers | `87133959` | 7226 / 99 / 0 |
| Browser | `87133959` | 684 / 0 / 0 |
| Entire expanded corpus, 35 suites | `87133959` | 460 / 1 / 0 |
| Actual default cgmsim/oref0 gate | `87133959` | 82 checks, 19 paired cells, zero differences/missing cells |
| Affected PgBouncer connection/RLS and typed identity | `87133959` | 9 and 4 passing, semantic controls restored |
| Archived owner-reader gate | `87133959` | 12 / 0 / 0; intersection semantic red; restored 12 / 0 / 0 |
| Archived durable replay gate | `87133959` | 7 / 0 / 0; typed-key semantic red; restored 7 / 0 / 0 |
| Authored source replay controls | runner-only continuation | Five semantic breaks, each restored 22 passing |
| Final prcheck, last application gate | `83582e87` | exit 0, OK; clean unchanged head |

Totals overlap and are not added. Full pending cases remain pending; the corpus
pending case is the explicitly disabled performance benchmark. The
[comprehensive capsule](../../../reports/tenancy/control-recovery-acceptance-87133959-2026-11-06.md)
owns commands, per-tier totals, actual pooler controls and observed cleanup.
The [default actual-client capture](../../../reports/m4-client-binaries/2026-11-06-control-recovery/README.md)
measures unselected behavior, with all 94 pinned cgmsim runtime files verified.
Selected-mode actual-client certification is separate and remains unmeasured by
this accepted batch. In particular, cgmsim only supplies a root-style credential,
which selected subject-only readers deliberately exclude; universal enablement
with no client impact is not established.

The [archived native gates](../../../reports/control-recovery-gates/2026-11-06/README.md)
observe freshly tightened grants wrongly admitting three protected operations
when the reader intersection is removed, and two independently stored typed
identities collapsing into one projected row when identity kind is removed.
The original owner-control classifier rejected Mocha's formatted boolean-array
representation. That instrument mismatch is preserved; the same immutable native
failure report was revalidated offline with a narrowly corrected classifier,
without another database control run. Fresh restorations passed.

The [initial focused failure and repair](../../../reports/tenancy/control-recovery-focused-1df25fba-2026-11-06.md)
remain distinct: 56/0/5 on `1df25fba`; four fixture/test paths repaired restore
stdin loss and a raw-versus-decoded typed oracle; affected importer/replay then
passed 15/0/0. No product workaround or weaker archive/identity contract was used.
The later source-control runner omitted those required fixture files in scratch;
that failure was reproduced and only the runner was corrected.
[Complete source identity and final gate](../../../reports/tenancy/control-recovery-runner-continuation-83582e87-2026-11-06.md)
prove that **every path except that source-control script** is identical between
871 and 835, including application, tests/assertions, migrations, CLI, dependency
manifests and corpus runner. Completed campaigns keep their actual executed head;
source identity supports reuse, not relabelling as fresh 835 executions.

**Criterion disposition:** bounded current subject-grant enforcement and
persisted typed projection/checkpoint recovery now have executable semantic
controls. Current-grant changes apply on the next selected operation in the same
SQL snapshot; no delegator provenance is inferred. Replay measures current-row
convergence with atomic persisted state, repeatable-read bootstrap, process death,
rollback, bounds and tenant fencing, rather than every intermediate transition
or exactly-once external effects. Populated recovery is a stopped-write synthetic
PG reference with explicit ACL recreation, not production key/provider recovery
or general typed API import. M0's earlier promotion stands; M1–M6 are not promoted.
Management composition, broader client workflows, clinical/evaluator/socket
consumers, operational lifecycle and performance retain their concrete criteria.

The coordinator independently verified 22 broad-acceptance artifact hashes and
26 focused failure/repair artifact hashes. Exact observed resources were audited;
older unknown services and volumes were preserved. Selected-client activation and
D23 forwarding preparation remain separate lanes. Remote publication/CI follows
only after canonical records and gates are integrated; no operator release is claimed.

<a id="run-63"></a>

### R63 - selected subject actual-client compatibility boundary (2026-11-06)

**Reproduced targeted experiment**, separate from R62's comprehensive campaign:
archived application `8713395992e07b4dd2cde61ee972e9a15c8ada8c`, standalone
[lab instrument](../../../tools/lab/selected-owner-clients/README.md) at
`7aae38a7de56c0c0367c524b354d4169f4d3e107`. No application, canonical/default
instrument or production configuration changed.

| Actual pinned-client operation | Unselected reference | Selected subject reader |
|---|---|---|
| oref0 subject-token uploads, entries/treatments/devicestatus | Three admitted workflows | Response summaries, client exits and normalized stored values match |
| Next oref0 entries upload after ceiling emptied | 200, new stored values | 401, independent all-domain A/B state unchanged |
| cgmsim root-secret upload | 200 | 503, no-effect assertion passed |

The reader mode can preserve the measured oref0 subject-token workflows while
revoking their grants at the next operation. The comparison covers response
status/shape summaries and full normalized synthetic stored values; every raw
reply-body field and all other client workflows remain unmeasured. Root exclusion
is deliberate, but **503 is an observed mapping requiring compatibility
disposition**, not an adopted client contract or waiver. cgmsim cannot supply a
subject token without a client/credential-carrier change. Universal selected-mode
activation therefore does not meet the user's no-unintended-client-impact condition.
The existing default remains unchanged and separately accepted in R62.

The archived ceiling-intersection ablation made the actual tightened upload
return 200 and change independent SQL state: both refusal/no-effect predicates
failed, exit 1. Fresh restoration passed, exit 0, without an instrument repair.
The catalogue contains six explicit read/create permissions across those three
domains and uses the existing denied-anonymous policy. This is lab-only explicit
constructor selection with subject readiness; it does not bypass production
preview readiness or enable a management listener.

[Immutable capture](../../../reports/selected-owner-clients/2026-11-06/README.md)
owns pinned provenance, oracle snapshots, commands and cleanup. The root no-effect
snapshot comparison executed successfully but its snapshots were not separately
serialized. Exact owned containers/mounted volumes were independently verified
absent; runtime released 22:11:44Z. Counts are not added to R62. No full/browser
repeat, new application head, milestone promotion or activation follows.

<a id="run-64"></a>

### R64 - published control recovery batch remote verification (2026-11-06)

**Reproduced remote read-back:** draft PR #8898 points to the accepted exact
`83582e876dd193f4448f44c28e379fb5464a26c7`, published by normal fast-forward.
[Application CI](https://github.com/nightscout/cgm-remote-monitor/actions/runs/42303661682)
completed successfully: 15 jobs passed, including all three browser engines,
maintained MongoDB, database/no-database matrices, runtime/build validation and
the expanded PostgreSQL/MongoDB/Vault corpus. Three release-image build/publication
jobs were skipped by workflow conditions.
[CodeQL](https://github.com/nightscout/cgm-remote-monitor/actions/runs/42303661681)
also completed successfully. Its CodeQL check has zero annotations; the Analyze
job's annotation is a runner-image migration notice. All eight retrieved inline
review threads are resolved. No blocking new review finding was observed.

Alignment acceptance main `74d273225a4a9c50854c905c73a6dafb9347dc85` was published
with the peer's prior public main ancestry retained. Its
[CI/site workflow](https://github.com/bewest/rag-nightscout-ecosystem-alignment/actions/runs/42303565719)
passed, including build/check/gh-pages publication. The PR description now cites
R62/R63 scope, source-identity reuse and these successful current-head remote runs.
It remains open and draft. [Immutable publication snapshot](../../../reports/tenancy/control-recovery-publication-83582e87-2026-11-06.json).

R62's last application gate is scoped to the 835 publication worktree. Separate
archived-source controls retain their actual 871 source and lane attribution;
no later experiment is relabelled as a prerequisite execution on 835. The selected
mode stays dormant: R63's measured root-client incompatibility and its unresolved
503 mapping are not waived. M0's R60 promotion stands; M1–M6 remain open. No dev
merge, release/tag, production role or default enablement occurred. New socket/
evaluator source work remains outside this verified publication.

<a id="run-65"></a>

### R65 - bounded tenant clock HTTP descriptive workload (2026-11-06)

**Reproduced descriptive data:** the existing native workload executed once on
an unchanged archive of published application
`83582e876dd193f4448f44c28e379fb5464a26c7`. Four fresh clock-off/on × hot/balanced
cohorts each completed 40 HTTP 201 requests at concurrency four through two API
processes, with zero HTTP/transport errors or retries. Eight warmup writes per
cohort are outside the timed interval.

| Clock / cohort | p95 ms | Successful requests/s |
|---|---:|---:|
| Off / single hot tenant | 18.766 | 339.067 |
| Off / balanced two tenants | 20.633 | 339.003 |
| On / single hot tenant | 23.115 | 303.356 |
| On / balanced two tenants | 18.180 | 336.242 |

[Immutable workload capsule](../../../reports/tenancy/2026-11-06-clock-http-workload/README.md)
owns the exact command, emitted metrics, configuration, versions and raw hashes.
These are short single observations in fixed order. No numeric budget, steady
state, cache equivalence, repeated-run uncertainty or causal off/on difference
is established. The native case asserts accounted-for HTTP outcomes, not a final
independent stored-row count. Raw individual latency samples, database CPU/memory/
I/O and isolated clock-lock waiting remain unmeasured. No performance or M1/M5
acceptance follows, and earlier corpus benchmark-pending captures are unchanged.

The original cleared-PATH command exited 127 before loading Node and started no
fixtures; it is preserved as an invalid prelaunch experiment. The coordinator
approved one replacement using the existing absolute Node executable and its
PATH directory, without source/assertion/instrument changes. The corrected native
case passed. All 1,726 archived regular files were verified unchanged by the lane;
the coordinator independently verified ten indexed raw/source artifact hashes.
The exact ten owned containers and fifteen captured mounted volumes were absent,
with no deletion needed; older unknown fixtures were preserved. Runtime released
22:23:58Z. This experiment is independent of R64 publication/remote verification
and does not change the accepted application head or production selection.

<a id="run-66"></a>

### R66 - joined socket evaluator native attempt and ordering gap (2026-11-06)

**Reproduced failed prediction:** joined source
`1990f453e09303d9dcf3394f0f50a42c3ce4052b` passed 124 pure tests, then one targeted
native socket/evaluator invocation produced **9 passing / 0 pending / 2 failing**.
[Immutable attempt capsule](../../../reports/tenancy/socket-evaluator-native-attempt-1990f453-2026-11-06.md)
owns commands, exact source, native breakdown and six independently verified raw
artifact hashes. No full application acceptance or publication follows.

All seven evaluator PostgreSQL cases passed. Socket DATA reported 2/2, but its
rollback green is vacuous: an earlier unsorted bounded-read refusal prevented the
post-write abort. The same refusal invalidated add acknowledgement and prevented
the held-COMMIT barrier; its timeout is not semantic evidence. Current-authority
foreign-role refusal passed. Native controls remain separately scoped.

Code inspection refutes a flag-only repair: the existing natural-order capability
requires an insertion ordinal missing from treatments/device-status catalogues.
Optional successor-schema/ordering and old/new/populated rollout characterization
continue as a separate prototype, without arbitrary sorting or invented import
provenance. Evaluator semantic controls proceed independently. Exact owned
resources were absent at release22:38:45Z; older unknown services were preserved.
R64's accepted835 publication is unchanged, M1–M6 remain open, and no default,
provider, role, notification or alarm-ack semantics are enabled by this attempt.

<a id="run-67"></a>

### R67 - bounded recovered clinical projection native controls (2026-11-06)

**Reproduced bounded property acceptance**, not whole-batch acceptance: archived
application `1990f453e09303d9dcf3394f0f50a42c3ce4052b`, instrument
`2d7ea7a3c95ae924745b9e9d66d2af33371a21f3`. R66's original seven evaluator
positives remain attributed to its combined failed batch. This slot ran only:

| Native experiment | Passing / pending / failing | Semantic symptom |
|---|---|---|
| Remove identity kind from projection key | 0 / 0 / 1 | Physical two-row/two-kind oracle passes; current clinical reading111 instead222 |
| Skip full bootstrap at advanced empty projection | 0 / 0 / 1 | Stored reading123 exists; recovered clinical reading undefined instead123 |
| Fresh restored source | 7 / 0 / 0 | Complete evaluator cohort passes |

Both reds are named `ERR_ASSERTION` failures, not import/SQL/timeout/TypeError.
The [immutable native capsule](../../../reports/projection-evaluator-gates/2026-11-06/README.md)
owns exact commands, raw reports, identity/recovery boundaries and cleanup. The
gate applies one consistent scratch-only oracle hardening: `bgnow?.mean` still
requires123, making missing clinical state an assertion rather than a TypeError.
Physical input checks precede the clinical assertions. Product source is unchanged.
The coordinator independently verified13 public and15 private artifact hashes;
private paths resolve from the owning alignment gate worktree named in its handoff.

The dormant constructor now has native evidence for persisted typed projection
recovery, actual clinical loader/property parity with physical-table reads,
retained A/B state, downstream failure/retry, explicit later-time computation and
producer death after data COMMIT before publication. It does not implement live
role scheduling, current protected socket delivery, durable notification handoff,
ack/snooze, every-transition history or external exactly-once effects. R66's
separate socket failure remains open in this source; no whole1990 acceptance,
publication, production role or M5 promotion is inferred.

Exact three owned PostgreSQL containers and three captured mounted volumes were
absent on independent reinspection; older unknown resources were preserved.
Runtime released22:48:29Z. Headless-owner and corrected socket-order source work
continue separately toward one larger frozen completion candidate.

<a id="run-68"></a>

### R68 - fresh schema socket DATA prototype native controls (2026-11-06)

**Reproduced bounded prototype measurements**, no production ordering rollout:
[immutable prototype capsule](../../../reports/tenancy/socket-order-prototype-native-2026-11-06.md)
and [native semantic controls](../../../reports/tenancy/socket-data-controls-12919f55-2026-11-06/README.md).
The optional successor preserves applied migration bytes and adds stable insertion
order only on empty tables. Actual populated refusal is atomic; old catalogue
check after upgrade returns `MIG_UNKNOWN`. An old application binary was not run;
its startup consequence is inferred from unchanged checker/catalogue inputs.
No down migration or invented imported order is provided.

| Actual source / experiment | Passing / pending / failing | Disposition |
|---|---|---|
|0d628 optional matrix + socket |6 /0 /1 |Matrix3 passes; initial reference lookup refuses under wrong global mode |
|12919 affected socket family |4 /0 /0 |Only three fixture paths differ; product/schema/catalogue bytes identical |
|12919 early-ack control |0 /0 /1 |Post-write reached, external row/event absent, but callback observed |
|12919 role-authority control |0 /0 /1 |Committed A-row count1 instead0 plus callback/event; B unchanged |
|12919 fresh restoration |4 /0 /0 |Complete bounded DATA cohort passes |

The corrected canonical Mongo reference runs in its own single-mode child;
PostgreSQL parent remains multi. Initial/retry/update/unset/remove/device and
reverse-lexical multiple-match identity parity are measured on fresh schemas.
Scratch-only observation hardening is consistent across controls/restoration;
independent physical state precedes exact assertion classification, not timeout.
All indexed original/public/private artifacts verified; exact owned resources
were absent at release. These are source-pattern/socket-handler proofs, not an
Android binary/full single-app or populated-realm compatibility claim.

This joins the next implementation candidate as a dormant experimental capability,
not automatic catalogue selection, production transport/role, stream authority,
alarm-ack or M4/M5/M6 completion. R66 and the first prototype failure remain
preserved. Comprehensive exact-head acceptance and current owner controls remain
separate gates; published835 is unchanged.

<a id="run-69"></a>

### R69 - tenant export, import and two-phase deletion early proof on fd827e35 (2026-11-07)

**Reproduced focused early proof, Batch C**, not a frozen-head campaign. Dormant,
opt-in lane `codex/tenant-export-delete-20261106`
`fd827e350a185ad73c838b013b25fe889434b036` over accepted R62
`83582e876dd193f4448f44c28e379fb5464a26c7` (`official/dev` `4a482627` contained),
adding `lib/tenant-lifecycle/` (typed export artifact, typed import with an
independent oracle, two-phase deletion request/execute) and one unit file. Instrument
`tools/lab/tenant-export-delete/` on alignment `f036e4dfe`; captured results under
`results/2026-11-07/`. Local and unpushed; joins #8898 at the root coordinator's next
batch boundary. No queue ref, dashboard or milestone change.

| Reproduced result, re-read from the committed report and lane logs | Result |
|---|---|
| Unit `tests/tenant-lifecycle.test.js`; eslint on the three new files; tier registry | 7 / 0; 0 errors / 0 warnings; 515 files, 8 tiers ok |
| Lab run 1 on `7255414e` | fatal at the first migration (`syntax error at or near "^"`, the lane's own candidate SQL unquoted); no stage ran; 2 containers and 2 volumes verified absent; preserved as `report-run1-fatal.json` |
| Lab run 2 on `fd827e35`, PostgreSQL 16.15 (`postgres:16`), Vault 2.2.1 (pinned digest), 00:02:49–00:02:59 UTC | `result: pass`; positive 14 / 14; restored 14 / 14 |
| Positive stage | tenant A 39 rows across 29 admitted tables (16 candidate catalogues), tenant B 17 rows; export counts equal the oracle; ObjectId/string twins keep `[objectid, string]`; two ciphertexts with key references and no plaintext; interrupted import (backend terminated after row 5) leaves 0 target rows and the rerun restores 39 oracle-equal rows; stale artifact refused (`LIFECYCLE_ARTIFACT_STALE`) with 40 rows intact; deletion thrown after the second table rolls back to 39 with B unchanged; execute deletes 39, 29 tables at zero, B unchanged at 17; re-import restores 39 rows with byte-identical ciphertexts that decrypt through the secrets component; the Transit key is present and non-exportable |
| Control `empty-catalogue` | red: `oracle: treatments.treatments: expected 2 rows, got 0` |
| Control `drop-catalogue` | red: `LIFECYCLE_CATALOGUE_INCOMPLETE: treatments`, target 0 rows |
| Control `flatten-objectid` | red: typed identity expected kinds `[objectid, string]`, got `[string]` |
| Control `omit-ciphertext` | red: `LIFECYCLE_KEY_REFERENCE_WITHOUT_CIPHERTEXT: secrets.secret_records.vendor-cloud`, target 0 |
| Control `wrong-binding-delete` | red: foreign tenant B changed in 16 tables while A's rows remain |
| Control `no-rollback` | red: interrupted import left 5 rows in the target (`entries.entries=5`) |
| Cleanup | both lane containers "No such container"; Vault's two anonymous volumes "no such volume"; PostgreSQL data on tmpfs; no foreign resource touched |

Five decision lines are recorded in the lane README, the lab README and the handoff:
Vault key destruction and artifact/tombstone retention after deletion; re-homing under
a new tenant id (the secrets envelope binds the tenant, so the import target must equal
the artifact's tenant); `food.insertion_ordinal` preservation across tenants; artifact
size and transaction bounds (one transaction, no cap); and which plane calls
`requestDeletion` versus `executeDeletion` (the module enforces no authorization).
UNMEASURED: real data, backup tooling, M6 acceptance, capacity and numeric bounds,
MongoDB-backed catalogues, concurrent writers during export, Vault key destruction,
full/browser/prcheck on the lane head, CI. Decrypting through the secrets component
writes audit rows, so the lab compares every oracle before any decrypt.
[Lab README](../../../tools/lab/tenant-export-delete/README.md).

<a id="run-70"></a>

### R70 - headless owner native wire and authority controls (2026-11-06)

**Reproduced bounded owner evidence**: [wire failure/correction](../../../reports/tenancy/owner-preview-wire-native-2026-11-06.md) and [strict native controls](../../../reports/tenancy/owner-preview-native-controls-4cd95d06-2026-11-06/README.md).

| Executed source / phase | Passing / pending / failing | Meaning |
|---|---|---|
| f078 combined owner/evaluator |9 /0 /7 |Evaluator7 and owner startup/lifecycle2 pass; seven owner request cases stop at tenant refusal before intended checks |
|4cd affected owner followup |9 /0 /0 |Fixture preserves explicit tenant Host through node:http; product/schema/defaults/other tests identical to f078 |
|4cd snapshot mutation, gate71be |0 /0 /1 |Two valid worker warmups precede committed revocation; next request200 changes target/audit+1, foreign unchanged |
|4cd listener mutation, gate71be |0 /0 /1 |Actual combined CLI incorrectly serves owner app on DATA; management200 changes target/audit+1, foreign unchanged |
|4cd initial ordinary gate71be |9 /0 /0 |Native green but gateFAIL: incorrect no-bind exit78 assumption; actual expected no-bind exit1 preserved |
|4cd fresh ordinary gatec67e |9 /0 /0 |Strict gatePASS: two explicit no-bind/no-port children exit1; four bound workers exit0, all independently absent |

Strict observations precede status assertions. Fresh restoration observes fourteen
revocation requests across two warmed workers at401/no effects, DATA management405,
OWNER200/audit+1, actual201 DATA canary and both sockets closing. Exact-owned reader
SELECT privilege loss gives sanitized503/no mutation, restoration200/audit+1;
this is SQL permission refusal, not transport-outage certification. Lifecycle-only
instrument repair leaves both product mutations and physical verdict function
identical; semantic controls were not repeated. All original failures remain.

The final invocation's three owned containers, four mounts, six CLI workers and
eight observed Node identities were independently absent at23:56:46Z; baseline462
volumes preserved. Initial transient evaluator-producer PID observation remains
limited as recorded. Tokens/credential rows/raw identities are private; public
capsules contain aggregates and hashes. No human issuer/refresh/provider or M2
promotion follows. Later joins retain actual4cd attribution; joined V&V is separate.

<a id="run-71"></a>

### R71 - transaction final-floor PostgreSQL component control (2026-11-06)

**Reproduced actual PostgreSQL component**, [immutable capsule and exact instrument](../../../reports/tenancy/final-floor-native-1acb4eee-2026-11-06/README.md):
instrumentf0e53977 archives1acb4eee. Ordinary6/0/0, final-argument omission0/0/1,
fresh restoration6/0/0. Six unique cases cover nested/no-op/settle/later allocation,
fresh no-op, rollback, A/B/A on one actual backend, closed/postcommit context and
clock-off behavior. Physical markers isolate the core; every canonical intent's
allocation policy is not established.

Independent restricted storage sees row allocationss1/s2 and final durable floors3.
Ordinary events are s3/s3/null/s3. Omission changes only the callback argument and
produces s1/s1/null/s2, exact `EVENT_FINAL_FLOOR_MISMATCH` ERR_ASSERTION with storeds1
versus independents3. Precommit rows invisible; all deliveries follow driver COMMIT;
foreign rows empty. Setup/timeout/pending/wrong assertion is not accepted as red.
No premature-publication or stale-tenant native mutation was run here.

One owned PG container/volume and eight observed Node descendants independently
absent;159 baseline containers preserved, no new resources or observer errors.
An initial zero-service preflight stop and initial reporter-string aggregate
extraction are preserved; normalized scalar comparison changes no execution/source.
Actual execution belongs to1acb only. Root independently verifies26 protected
source groups/files unchanged on later readermode-removale2; scoped reuse is not
new-head execution. [Source failure/repair/removal evidence](../../../reports/tenancy/owner-event-reader-removal-source-2026-11-06.json)
records the two stale socket gate registrations, meaningful retained mutation
coverage, repaired unit2306 and removal unit2304. Full/default-client/pooler/browser/
whole39-corpus/prcheck acceptance on frozene2 remains separate. No M5/M6 promotion.

<a id="run-72"></a>

### R72 - admitted entries and owner configuration completion batch (2026-11-06)

**Reproduced comprehensive acceptance on `74d7b3fc25c7e3c496c438847c95e89ec7fe6061`, containing official/dev `4a482627bfdafb1fef8dcbe0ac6c484811cae563`.**
[Immutable aggregate and source attribution](../../../reports/tenancy/completion-batch-74d7-2026-11-06/README.md),
[summary](../../../reports/tenancy/completion-batch-74d7-2026-11-06/summary.json) and
[52-artifact index](../../../reports/tenancy/completion-batch-74d7-2026-11-06/artifact-index.json).
Root independently verifies every indexed artifact. Source remains clean and unchanged after final prcheck.

| Instrument / actual executed tree | Passing / pending / failing | Verdict |
|---|---:|---|
| Affected resend, event-payload and clock source files with real private Mongo /74d7 |46 /0 /0 |Exact settle contract, final-floor and no-write assertions retained |
| Full nonbrowser /74d7 |7320 /132 /0 |All seven tiers pass; pending is not pass |
| Browser,41 files /74d7 |684 /0 /0 |Actual default browser campaign |
| Entire enabled multitenant corpus,40 suites /74d7 |495 /1 /0 |Only end-to-end latency/throughput benchmark pending, explicitly deferred C |
| Source and final prcheck /74d7 |PASS |527 files/eight tiers;40 suites/23 own-container; G1/G2, whitespace and lint0errors/29warnings; current dev contained |
| Actual default cgmsim/oref0 /7015 |82 /0 /0 checks |19 paired cells per stack; zero differences/unexplained/missing;94 compiled cgmsim JS files verified |
| Fresh affected PgBouncer /7015 |9 +4 checks |Transaction binding/RLS and typed identity, including actual embedded mutation/restoration controls |
| New M1 paging/import vectors /7015 |2 /0 /0, fresh2 |[Native capsule](../../../reports/tenancy/m1-backend-native-7015-2026-11-06/README.md); comparator reversal and defective-target fidelity oracle each fail at its intended assertion |
| New M2 actual owner settings /7015 |14 /0 /0, restored subset4 |[Native capsule](../../../reports/tenancy/owner-settings-native-7015-2026-11-06/README.md); four actual authorization/fence/policy/presentation mutations produce intended physical effects and ERR_ASSERTIONs |

Counts overlap and are not added. The two dependency pending cases name optional
ajv6/har-validator and style-loader schema-utils paths. Ordinary full integration
opt-outs are classified separately from the required enabled-corpus execution;
all forty required suites are selected and the only corpus pending case is the
explicit benchmark. No capacity, latency or numerical budget is accepted.

**Source identity and preserved failures.** The7015 full run is retained at
7317pass/132pending/3fail: its three exact settle-event expectations omitted
adopted `tenant:null` and `stamp:null` (B7 rule3). The74d7 repair changes only that
existing test's expected object and comment, retaining every WriteResult, one-event,
immutable-event, no-write and stored-unchanged assertion. All other1777 tracked
blobs match7015. Product, migrations, dependencies, native fixtures and relevant
client/pooler inputs are identical, so their actual7015 results are retained with
that attribution, not relabelled74d7 execution. R70/R71 retain actual4cd/1acb source
and bounded relevant-input reuse. Earlier M2 scope-rebind/fixture failures and their
narrow repairs remain in its capsule; the [temporal fixture proof](../../../reports/tenancy/legacy-rest-temporal-fixtures-386dba33-2026-11-07/README.md)
retains its actual386dba33 calibration and red/restored controls.

The corpus audit initially omitted the helper's existing runner-manifest argument,
so its prefix guard refused generated Docker names. Exact created IDs, images and
mounted volumes match the runner manifest; the supported exact-ID allowlist then
completed independent absence/baseline checks. No name/timing inference, product
change or test replay followed this audit setup stop. Per-phase resources and
observed birth-identified children are absent; unknown baselines are preserved.

#### Criterion disposition

| Milestone | Actual criterion evidence | Disposition |
|---|---|---|
| M1 | Source applicability crosswalk plus dedicated enabled Mongo/PG port/CRUD/identity/filter/history/batch suites; reviewed DDL/migrations/import target, real interrupted-page rollback and rerun; tied paging against independent physical identities | **Promoted for the admitted preview contract.** JSONB logical equality and explicit unsupported operations remain; global generic PostgreSQL fixture availability is not claimed. Resource bounds: deferred, measured in C; sort cap5 retained. |
| M2 | Actual versioned owner configuration, CAS/history/rollback, explicit configure authority, current operator generation, cross-worker current reads, unknown-tenant/signature/refusal, secrets/context leakage checks, separate OWNER/DATA/operator route boundaries; enabled owner/credential/secrets/process suites | **Promoted under the adopted roadmap cell.** Two reviewed display names; operator-provisioned management credentials. Human issuer/refresh, broader catalogue, existing-grant lifecycle and production resolution trust remain M6. |
| M3 | M1/M2 criteria pass; actual executable A/B entries-v3 writes/readback/restart and independent stored outcomes, foreign credential refusal, unknown aliases and stale/unsafe startup refusal in enabled process/replica/migration suites | **Promoted.** Synthetic isolated two-tenant lab acceptance. |
| M4 | M3 passes; actual pinned cgmsim/oref0 gate and enabled source-pattern client/socket replay, identity/history/batch/retry/refusal/exchange contracts | **Promoted under the adopted headless/source-pattern bar. No all-client claim.** Android emulator C; iOS outside automated lab. |
| M5/M6 | Bounded constructors, prototypes and early operational evidence remain individually attributed | **Not promoted.** Live consumer roles, durable acknowledgement/handoff, production identity/lifecycle and operational/resource acceptance remain. |

The default queue-status measurement before promotion was1PASS/4UNMEASURED for the
five selected parent items, with integration gates skipped. Those skipped gates
are not green: this disposition uses the explicit reproduced runtime commands and
frozen captures above. Broader parent-card scope remains explicit in the queue.
M0's R60 promotion is retained. No dev merge, operator release, default enablement
or production-role admission follows from these preview milestones.

The separate [representative backup/upgrade proof](../../../reports/tenancy/backup-upgrade-native-f77-2026-11-06.md)
passes its original entries/clock boundary; its application source is not joined
to this candidate and full Batch C acceptance is not inferred. Restore/clone policy
is [adopted separately](../../30-design/tenancy/multitenancy-decisions.md#restore-identity-and-cloning).
Local coordination: `externals/work/HANDOFF-codex-completion-coordination-20261106.md`.

**Publication verified (2026-11-06):** draft [#8898](https://github.com/nightscout/cgm-remote-monitor/pull/8898)
is OPEN at accepted74d7; its title/body now match R72, compatible reader removal
and adopted milestone scope. [Application CI](https://github.com/nightscout/cgm-remote-monitor/actions/runs/42330725615)
and [CodeQL](https://github.com/nightscout/cgm-remote-monitor/actions/runs/42330725633)
complete SUCCESS on that exact head: all15 test/build jobs, including three browser
engines and enabled corpus, succeed; three release-image publication jobs skip.
The alignment promotion/map publication586f8c83 has [successful CI](https://github.com/bewest/rag-nightscout-ecosystem-alignment/actions/runs/42331010678).
These are remote measurements after the accepted local campaign; no application
source or test was changed/replayed after final prcheck.

<a id="r73-durable-runtime-operations-batch"></a>
<a id="run-73"></a>

### R73 - durable runtime and bounded operations batch (2026-11-07)

**Reproduced joined acceptance; M5 functional one-host reference promoted locally;
M6 remains open.** The
assembled application candidate is `f0fac99a2fccee259c9a76eba0123058bf288d96`,
tree `09dd7baf52d51f2725e7cac732fabd3f8280b482`. Fresh remote inspection retains
`official/dev` at `4a482627bfdafb1fef8dcbe0ac6c484811cae563`; the application
candidate is local, not merged to dev or released. R72's accepted M0–M4 scope is
retained. The joined criterion disposition below promotes M5, rather than any
component record alone. M6, default/production enablement and publication retain
their separate status.

| Recorded family | Actual executed source | Reproduced boundary and record |
|---|---|---|
| M5 PostgreSQL recovery, evaluator, alarm and durable requests | `f4e3f7e7b9eab6388cee1fb3470d380506917e05` and `353bb4445143bc85fe9f52e6ba3295247b23a96a` | Initial23,19 distinct physical semantic controls and fresh complete23 restoration. [The PostgreSQL record](../../../reports/tenancy/m5-runtime-2026-11-07/postgres/README.md) owns exact per-phase attribution, original stopped verdicts, precise regrades and the excluded timed-out control. |
| Joined API/realtime/evaluator and browser consumers | `b6bb39fd02a1cc1df8cd0c088edd8bafeb4ef952` | Six fresh ordinary phases, six intended physical semantic reds, six fresh ordinary restorations. [The roles record](../../../reports/tenancy/m5-runtime-2026-11-07/roles/README.md) retains every original process, physical predicate, controlled patch and source binding. Independent replay matched all18 verdicts;54 containers,90 volumes and87 observed process births were absent. The87 include20 Chromium births. |
| Bounded populated SQL operations | `9298d79305e941fcfd36effa594e0e0bccf79994`, with OLD `a7f5cbf71ab9016855976fae74730727d0a78024` | Initial C1–C5,11 physical semantic controls,11 targeted restorations and fresh final C1–C5. [The SQL operations record](../../../reports/tenancy/m6-ops-2026-11-07/postgres/README.md) compares all37 CURRENT and31 OLD tables, ledgers, rows, identities, ACL/RLS, relations and inheritance. Original parent false closure remains explicit; only nine exact terminal-Z/empty-command audit samples are reconciled against independent live identities and resource release. |

These are separate executed heads, not an invented aggregate native head. Against
the final candidate,118 of119 joined-role source references are byte-identical;
the exception is test registration. Sixty of61 SQL-core references are identical;
the exception is the independently checked process-audit collector correction.
Application SQL, runtime and protocol bytes covered by those comparisons are
unchanged. Source equivalence does not relabel an old execution as a new one.

The joined roles exercise current-state recovery and connected storage,
12 physical Mongo/PostgreSQL DATA comparisons across six domains, durable
same-identity notification retry, cold authorized control clear, actual private
plugin snooze/ACK, current authority/configuration epochs, and the unchanged
client's same-origin sockets and urgent UI. The browser event is supplied at the
actual realtime boundary; evaluator-to-realtime handoff is measured separately.
This is not a single evaluator-to-device journey or external-provider delivery
proof. Stable request identity prevents duplicate request creation; it does not
undo an external effect accepted before its response was lost. Original
suppression expiry, active-window behavior and single-tenant defaults retain
their separate default/consumer verification.

Clinical acquisition failure cannot create a new ordinary clinical notification
request. Independently authorized, committed ACK/snooze controls may still create
a durable control-clear request; the cold-clear control exercises that distinction.

**Retained combined-run failure and causal repair.** The first assembled run on
`e8827e1d77bfe0c58c4cfe4ff65e10304a4d9b31` completed7,620 passing,
165 pending and nine dependency failures. The private wrapper's injected
`NODE_PATH` made intentionally tool-absent scratch installations find the shared
webpack/parser dependencies. The same two actual test files reproduced5 pass /
9 fail with that variable,14 pass with the key removed, the same nine failures
when reintroduced, and14 pass after restoration. No application assertions were
weakened. The corrected wrapper removes both inherited and forced `NODE_PATH`.

That run also reproduced19 retained anonymous volumes: nested fixtures removed
their owned containers without requesting anonymous-volume removal. All22
containers and166 observed process births were absent. The original failed
cleanup verdict is immutable. Deletion of those exact old volumes awaits explicit
local authorization; later runs preserve them as known baseline residuals and
never adopt or delete them. The final fixture changes add volume removal only to
24 owned terminal calls in15 files. Four actual-source failed-creation probes
also exposed cleanup of uncreated names in two fixtures: old4 fail → fixed4 pass
→ old-behavior ablation4 fail → restored4 pass. Post-success ownership tracking
now protects those paths. These probes fake only Docker's external boundary;
they do not fabricate successful database operations or native cleanup evidence.

**Final candidate verification.** A fresh production build at `f0fac99a` completed
with zero webpack errors and three performance warnings; all16 asset hashes were
checked. The private verification checkout has its own cache and synthetic test
key and consumes that build. Default browser verification preserves the original
`playwright.chromium.launch()` call: actual installed option normalization selects
the headless-shell binary, separately from the named-reference fixture's explicit
full-Chromium binary. The observer must see the selected executable's birth.

| Final-tree check | Current disposition |
|---|---|
| Full nonbrowser suite through the actual owned runner | **Reproduced:7,633 passing,165 pending,0 failing.** Unit2,645; DOM205; dependency368 with2 pending; core319; harness99; integration3,979 with163 pending; stress18. Source head/tree stayed clean and unchanged. All22 new containers,32 new volumes and165 observed process births were absent; baseline preserved, including the old19 residual volumes. |
| Entire default browser tier | **Reproduced:684 passing,0 pending,0 failing**, actual Chromium153.0.8010.12. The unchanged launch selected the pinned headless shell;285 such births and7 Node births were absent. All3 new containers/5 new volumes were absent; old19 preserved. |
| Entire enabled multitenant corpus | **Reproduced:all45 suites,528 passing,1 pending,0 failing**, no filter, no signal, no remaining resources. The sole pending case is the disabled end-to-end clock latency/throughput benchmark. Independent raw-report, selected-inventory and pending-title checks pass. All41 new containers,58 new volumes and128 observed births were absent; old19 preserved. |
| Final `prcheck.sh` | **Reproduced:exit0**, after the accepted full/browser/corpus campaign. Exact head, tree, lock, empty index and clean publishing/verification trees retained; `official/dev` unchanged. The first sandbox invocation could not resolve GitHub; its unchanged-source setup failure is preserved separately. The same script with host network access passed. No application test or source change followed the successful final check. |

**M5 criterion disposition under the adopted reference bar:**

| Required family | Applicable reproduced evidence | Disposition |
|---|---|---|
| Typed consistent current-state/absence recovery and refusal without partial persistence | PG record plus actual corpus hard-delete restart, unstamped v1/internal and socket activity, row/byte/persistence rollback, and concurrent commit across snapshot pages | Accepted. |
| Actual evaluator consumption, retained/time-only cycles, config changes, failure and shutdown | PG lifecycle/notification record plus actual executable recovery and joined separate roles | Accepted. |
| Separate API/realtime/evaluator startup, scheduling, missed/duplicate wakes and restart | Actual joined-role recovery and fresh restoration; selected roles on one machine | Accepted; no multi-node ownership claim. |
| Existing socket namespace/source/replies/retry and current authority/configuration | Twelve ordinary DATA pairs, connected typed storage, current collections and socket/config epochs, with physical red/restored controls | Accepted at the declared wire/client scope. |
| Durable original suppression/default-level effects, private plugin ACK and restart | PG alarm record plus actual plugin/consumer socket effects and control-clear evidence | Accepted. |
| Persisted request intent, same-identity ambiguous retry, current consumer admission and shutdown | PG notification/consumer record plus actual realtime handoff, cold control clear and UUID/plugin/clear controls | Accepted; external effects can repeat. |
| Preserved default/single consumers and unchanged browser behavior | Full default suite, entire default browser, entire enabled corpus and separate actual recipient/browser observation | Accepted without an evaluator-to-device or all-client claim. |

The transport mapping is explicit: [B7 §9](../../30-design/tenancy/durable-event-delivery-contract-2026-11-06.md#9-what-this-contract-does-not-decide)
permits a slot, polling or both while provider selection remains deferred. This
reference uses initial and scheduled consistent snapshots. It does **not** execute
a PostgreSQL `LISTEN` catch-up/handshake or establish notification latency. The
startup/concurrency proof composes actual consistent paging/interleaving/rollback,
scheduled role recovery and downstream subscription/authority epochs. Conditional
direct-connection guidance still applies if a LISTEN/NOTIFY provider is selected.
No every-transition history or capacity guarantee is added.

The portable gates replay archived synthetic evidence without starting services:

```bash
node tools/queue/gates/m5-runtime-batch-recorded.js \
  --repo "$APP_OBJECT_REPOSITORY" --deps "$APP_NODE_MODULES"
NS_M6_OPS_RECORDED_REPO="$APP_OBJECT_REPOSITORY" \
  node tools/queue/gates/m6-ops-recorded.js
```

Root independently measured ordinary → deliberately rehashed corruption →
restored acceptance for the PostgreSQL record, all13 roles controls and all13
SQL operations controls. The aggregate M5 gate checks both separate record homes.
The three wired recorded gates pass, and each authored control is NON-VACUOUS.
The broader parent items retain their explicit no-gate boundaries. The selected
vacuity command also reports pre-existing duplicate registry entries:15 extra
entries remain, compared with17 at the baseline; none of the three new gate keys
is duplicated. This is not a claim of a clean global control registry.
Missing committed app objects or lock-matched BSON dependencies are not a green
result. The gates read objects into owned scratch; they never fetch or check out
a peer tree. Private environments, credentials, raw logs and global machine
inventories are excluded from the public projections.

**Remaining criterion boundaries.** M5's functional one-host reference is accepted
and promoted. The accepted application and alignment records are published;
[release contents](../../../releases/cgm-remote-monitor-16.0.0/contents.md) owns
publication, remote CI and the separately approved residual cleanup. Live provider/device delivery,
performance/capacity, production trust and human identity/session effects are not
established by these functional records. Same-ID identity-bearing tenant restore
remains `OPEN/UNSUPPORTED`; whole-deployment fresh-target restore and tenant-local
fixture quiescence do not establish a shared allocator fence. The optional
allocator/fence discriminator was source-only at this acceptance; the later R74
measurement below does not hold or promote this bounded SQL result. Current-cycle state and local coordination are linked
from release contents; no dev merge, operator release or real-data admission is
claimed here. The earlier blocked publication attempt changed no remote; later
direct maintainer approval authorized the recorded normal fast-forward publication.
Original failed acceptance and cleanup captures remain immutable.

<a id="run-74"></a>

### R74 - same-ID allocator discriminator and remote publication readback (2026-11-07)

**Reproduced:** the unchanged R73 application head's isolated
[allocator discriminator](../../../reports/tenancy/m6-allocator-discriminator-2026-11-07/README.md)
completed seven SQL groups with actual clock-bypass and shared-sequence-rewind
reds and fresh restorations. Exact source/instrument attribution, separate CACHE 8
counterexample, setup failure and immediate/later physical closure distinction
are retained there. Same-ID restore remains `OPEN/UNSUPPORTED`; no new policy,
production admission or M6 promotion follows.

**Read-derived remote metadata:** [publication snapshot](../../../reports/tenancy/r73-publication-2026-11-07.json)
retains application CI attempt1 failure and observed external attempt2 success,
CodeQL/alignment success and draft PR state. The actual second warning in attempt1
is unidentified. **Reproduced diagnostic:** source-identical boot-index test: 3 pass;
injecting an unrelated global warning reproduces exact `2 !== 1` at line 39;
removing injection restores 3 pass. No application patch or coordinator CI rerun
was made. Release contents owns publication and separately approved cleanup facts.

<a id="run-75"></a>

### R75 - operation lifetime early proof and cache-parameter mismatch (2026-11-07)

**Reproduced:** local unpublished prototype `6a245c09f652f020dc07f774aa0f2fe8e22e973f`
passes 95 focused source tests. The [bounded evidence](../../../reports/tenancy/m6-operation-window-2026-11-07/README.md)
retains an initial fixture 42501 refusal; a later overall-failed native run with
seven completed lower/HTTP/orphan groups, meaningful bypasses and fresh
restorations; and a separately successful narrow cache diagnostic. These captures
are not added into an accepted full cohort.

The actual retained backend returns 2 for CACHE 8/setval-only, but 109 after a CACHE 1
parameter change that preserves its PID and sequence OID while replacing the
relfilenode. The latter refutes the test's predicted 2; the original false result
remains immutable. Read-derived pinned PostgreSQL 16.15 source explains the
rewrite/cache distinction. No ALTER/global allocator/B-outage policy follows.

Exact owned resources/children were removed, immediate baselines matched and root
physical closure was independently read. Complete CLI/privilege/census/operator
control and allocator history/floor/import refusal/rollback acceptance remain
OPEN/UNSUPPORTED. No full/browser/corpus/prcheck or M6 promotion is claimed; the
coherent source integration is not frozen. External accepted effects are not
cancelled by a vanished SQL lease. Release contents owns current lane state.

<a id="run-76"></a>

### R76 - allocator-preserving entries restore feasibility (2026-11-07)

**Reproduced:** unchanged app `f0fac99a2fccee259c9a76eba0123058bf288d96`
(tree `09dd7baf52d51f2725e7cac732fabd3f8280b482`), PostgreSQL 16.15;
[bounded report/source/observations](../../../reports/tenancy/allocator-preserving-restore-2026-11-07/README.md).
R75 is allocated by the separate operation-window lane and retains its own scope.

Command: owned finite `python3 parent.py` in the local
`externals/work/m6-allocator-preserving-feasibility-20261107/` packet;
final instrument hash and private capability requirements are recorded in the
report. Restricted application entries writes use frozen source; operator restore
is research SQL and does not call/change the production refusal.

Original A ordinals restore with no shared allocator maintenance while B writes
before/during/after; all prior B raw rows remain exact. High-floor/wrong-binding
refusals precede effects; injected interruption rolls A back while B's commit
survives. Removed floor guard yields actual numeric natural-order regression;
B corruption fails the independent comparator; fresh ordinary restoration passes.
A separate logical proposal assigns fresh internal ordinals preserving synthetic
document values and relative order while B continues; exact raw ordinal fidelity
is deliberately not claimed for that proposal.

Initial mode-setup failure and subsequent text-alias oracle error remain failed
captures. Final child exits 0; owned container/volume absent and baseline inventory
unchanged; root independently checks final instrument/parent hashes and current
exact owned-resource absence. No application source changed.

**Boundary:** deliberate A fixture quiescence, entries-only SQL feasibility.
Complete serving/writer/authority/cache exclusion, public clients, populated
history/cursors, full catalogue/secrets, cached allocator configurations and
production recovery remain UNMEASURED. No shared pause was needed by this fixture;
no recovery duration or M6 promotion follows. Comprehensive application acceptance
is skipped because this is an isolated early proof with unchanged product source.

<a id="run-77"></a>

### R77 - tenant-local insertion direction and consumed native proof (2026-11-07)

**Reproduced, separate exact sources:**

| Capability | Source and evidence | Verdict / boundary |
|---|---|---|
| Actual relative-order consumers | f0fac99a; [native server consumer proof](../../../reports/tenancy/insertion-order-consumers-2026-11-07/README.md) | Renumber preserving order returns exact same profile; reversed duplicate-match order changes selected full profile and makes equivalence red; date-sorted entries unchanged; fresh restoration passes. Released AndroidAPS NSClient v1 connection is read-derived source tracing, not binary execution. |
| Existing-allocator advisory preflight | df7215ac; [retained planner proof](../../../reports/tenancy/allocator-plan-2026-11-07/README.md) | Root focused45 pass after initial missing NODE_ENV precheck refusal; actual PG SELECT-only role returns advisory/not-authorized, floor/setter/cache refusals and fresh restorations leave rows/ledger/sequence unchanged. Retained evidence, not selected target architecture. |
| Tenant-local insertion primitive | 07f8c27d1c2c2cab1b65cd17fa4995d0bdf7f816, tree a66c114ae0add5f47170de9d2cc5c682bb971cc5; [native proof](../../../reports/tenancy/tenant-local-insertion-2026-11-07/README.md) | All five actual ordered catalogues convert populated rows unchanged and remove sequences. Canonical insert/rollback, column ACL, foreign binding, immutability and exact A restore with concurrent B pass; entries lock witness shows B progress; real profile first match unchanged. Inherited grant refuses; own-counter corruption makes order oracle red, rollback/B exact and fresh ordinary pass. |

Commands: isolated finite `python3 parent.py` in each named local proof packet;
root `NODE_ENV=test TEST_ENV_FILE=/dev/null node node_modules/mocha/bin/mocha.js
--require ./tests/hooks.js --timeout 10000 tests/tenant-insertion-sql.test.js`
on07f8 passes4 source cases. Report instruments pin exact native source, arguments,
physical observations and cleanup; counts are not additive. PostgreSQL16.15.

The first tenant-local native attempt preserves the scope-rebinding fixture
failure after successful conversion/entries checks. Its correction uses an
independent root request context for B; product guard/source unchanged. Both
attempts remove exact own resources and restore inventory; final child exits0.
Root independently checks final instrument/parent hashes and exact owned absence.

Maintainer [selected per-tenant insertion semantics](../../30-design/tenancy/multitenancy-decisions.md#tenant-local-insertion-semantics),
with no global insertion identity requirement. Explicit standalone conversion SQL
is not yet MIG-RUNNER catalogue-compatible (LOCK/SET/DO), selected or deployed.
Counter-table lifecycle/readiness/role admission, target-A exclusion, cursor/cache/
identity recovery and coherent final application acceptance remain open. No M6
promotion or production/default enablement. Full/browser/enabled-corpus/prcheck,
site render and capacity checks skipped: standalone source/native feasibility;
coordinator freezes a coherently integrated candidate before comprehensive acceptance.
