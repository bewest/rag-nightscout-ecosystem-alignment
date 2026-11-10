# MT-OWNERSHIP-OPS: ownership operations composed into the multitenant `admin` role

*Contributor-facing measurement record, captured 2026-11-10. Not edited after capture. Lane
`codex/ownership-role-20261110`; local, unpushed.*

## Anchors

| tree | ref | commit |
|---|---|---|
| cgm-remote-monitor lane head | `codex/ownership-role-20261110` | `1376c2946ce71078b477d4e0f2e4d428f29778ed` |
| lane base = draft #8898 head (fetched at start) | `official/workspace/multitenant-20261102` | `b70ad83fa4cdaeb7e6023137a05bd811d7db606a` |
| `official/dev` (fetched at start) | | `4a482627bfdafb1fef8dcbe0ac6c484811cae563` |
| alignment `main` at writing | | `d38055bc9ed2bc4e7969ee31e4d39ac2698cfc1e` |

`make queue-status` at start: `MT-OWNERSHIP-OPS ... in-flight-upstream 1/1 PASS`.

Lane commits (15 files, +732/−25 against `b70ad83f`):

| commit | what |
|---|---|
| `e6f6e248` | deployment plan: `<prefix>_ownership_operator` identity and its six grants (`deploy/multitenant/config.js` only; the nightscout-deploy overlay port) |
| `b726b6a0` | core: `admin` role runtime (`lib/server/serve/admin-config.js`, `admin-preview.js`), role table, serve and CLI wiring; unit and native tests; tier and corpus registration; ownership README |
| `1376c294` | native suite: CREATEROLE refusal case (see control C4) |

## What the composition is

- `roles.js` `admin`: `multitenant: true`, `start` → `admin-preview.js`. Plane, prefix, default
  host/port, `listener: true`, `storage: 'write'` unchanged.
- The admin listener (`ADMIN_HOSTNAME`/`ADMIN_PORT`, existing plane rule) serves exactly the
  `ownership-operations` v1 routes through `transport.handler` (the shared internal transport's
  route table, header/schema/bound checks), one owned token per module. No credential of its
  own (D7, decision `internal-service-contracts`: HTTP access policy belongs to the deployment).
- `MULTITENANT_ADMIN_CONFIG` (`admin-config.js`): `version`, `maxBytes`, `timeoutMs`,
  `ownership: {connectionEnv, namespace, operator: {principal, consumer}, tenants}`; nothing else
  accepted. Operator authority is the shipped `tenantSetAuthority` over the listed tenants.
- Startup: shared application connection refuses SUPERUSER/BYPASSRLS
  (`lib/storage/postgres-connection.js:72`); the admin readiness check refuses
  SUPERUSER/BYPASSRLS/CREATEROLE/CREATEDB/REPLICATION; the ownership store's exact privilege
  screen refuses any other table-privilege shape.
- serve refuses `admin` without its configuration, and together with
  `MULTITENANT_OPERATION_CONFIG` (admin is not a lifecycle cohort participant).
- UDS for the admin listener is not offered: the ADMIN listener is HTTP. `service.open` (UDS or
  internal HTTP on its own endpoint) is unchanged for other composers.

## Grants: derived from the code

Statements read in `lib/tenant-ownership/postgres.js` (read-derived) and measured by the native
identity test (reproduced):

| table | statements | grant |
|---|---|---|
| `tenant_authorization_config` | `SELECT ... FOR SHARE` (row lock needs an UPDATE column privilege) | SELECT, UPDATE(owner_fence) |
| `tenant_owner_policy` | `SELECT ceiling ... FOR UPDATE` | SELECT, UPDATE(owner_fence) |
| `tenant_owner_actors` | `SELECT ... FOR UPDATE`; `UPDATE SET active=false`; `INSERT ... ON CONFLICT DO UPDATE SET active, can_update, delegable` | SELECT, INSERT, UPDATE(active, can_update, delegable) |
| `tenant_authorization_subjects` | `SELECT subject_id` | SELECT |
| `tenant_subject_admin_audit` | `INSERT` (no RETURNING) | INSERT |

USAGE on the authorization schema only. No DELETE, table-level UPDATE, other namespace, or
lifecycle control-namespace grant (the plan's per-role control loop now excludes the identity).
This equals the shape the store screens and the earlier lane's test granted.

## Commands and results (lane head `1376c294`, from tool output)

```bash
cd externals/work/crm-ownership-role-20261110   # npm ci --ignore-scripts; npm run bundle (exit 0)
NODE_ENV=test NS_ADMIN_ROLE_DOCKER_TEST=1 NS_TENANT_OWNERSHIP_DOCKER_TEST=1 node_modules/.bin/mocha \
  --fail-zero --timeout 90000 --exit --require ./tests/hooks.js \
  tests/admin-role-ownership.integration.test.js tests/tenant-ownership-postgres.integration.test.js \
  tests/admin-role.test.js tests/tenant-ownership.test.js tests/internal-api-contracts.test.js \
  tests/internal-api-composition.test.js tests/serve-listeners.test.js tests/serve-roles.test.js \
  tests/nightscout-cli.test.js tests/multitenant-inventory.test.js
```

| check | result |
|---|---|
| native admin-role suite alone (`NS_ADMIN_ROLE_DOCKER_TEST=1`) | **11 passing, 0 failing**; no `nightscout.test=admin-role-ownership` container left |
| focused family above (both native suites + unit/contract/serve/CLI/inventory) | **124 passing, 0 failing, 0 pending**; no `ns-adm-*`/`ns-own-*` container left |
| `node scripts/test-tiers.js check` | `616 test files, 8 tiers: ok` |
| `node --test deploy/multitenant/bootstrap.test.js deploy/multitenant/restore.test.js` | 10 pass, 0 fail |
| `npm run lint` | 0 errors, 51 warnings; the two in new files are `security/detect-non-literal-fs-filename` on the config file read (same pattern as `owner-preview-config.js`) |
| `npm run test:unit:ci` (production bundle present) | **3116 passing, 0 failing**, exit 0 |

PostgreSQL: `postgres@sha256:9e2cf6287f25c3151f4c9421ccce2b17f3e60061c111a29165e0d2cdd9ff0a97`
(`PG_VERSION=16.15-1.pgdg13+2`), the suite's own container `ns-adm-<random>`, label
`nightscout.test=admin-role-ownership`, random loopback port, generated passwords in the child
environment only. Reaper: a detached `sh` loop removes the container if the mocha process dies
before `after`. No MongoDB used.

The native suite (`tests/admin-role-ownership.integration.test.js`) applies the authorization
catalogue the way `deploy/multitenant/bootstrap.js` does (NOLOGIN catalogue owner, tables and
schema owned by it) and then exactly `plan.grants(layout)` statements naming the identity. It
spawns `node bin/nightscout.js multitenant admin` (`ADMIN_HOSTNAME=127.0.0.2`) and reaches it
only with `clients.ownershipOperations({url, trust: 'network'})`:

- identity: exact privilege matrix over every authorization table; nine out-of-set statements
  (DELETE actors, UPDATE ceiling, UPDATE consumer, INSERT roles, INSERT subjects, DELETE
  subject_roles, SELECT audit, SELECT schema_migrations, CREATE TABLE) each refuse `42501`;
- listener: list works; an unknown route, a request without the contract headers and a body with
  a `credential` field each `503`, no audit row;
- add (applied), stale-set add (`OWNERSHIP_CONFLICT`, audited), transfer (applied), audit rows name
  the operator; recovery of a tenant with deleted owner subjects (keys exactly
  `code, event, outcome, owners`);
- tenant B (not in the configured list): all four operations `denied`/`OWNERSHIP_FORBIDDEN`, rows
  of A and B identical before and after;
- race: holder locks A's actor rows; two transfers through the role wait (2 backends
  `application_name='nightscout-ownership-ops'`, `wait_event_type='Lock'`); after release one
  `applied`, one `OWNERSHIP_CONFLICT`, one owner;
- INSERT on audit revoked under the running role: client `SOCKET_IPC_UNAVAILABLE`, rows unchanged,
  PostgreSQL log `permission denied for table tenant_subject_admin_audit`; grant restored, the same
  add applies;
- startup refusals (exit 1, `could not start: preview startup failed`, never listening): DELETE on
  actors, SELECT on subjects revoked, BYPASSRLS, CREATEROLE. SIGTERM exits 0.

## Break-it controls

Runner `controls-run.py` (here; results `controls.json`): mutate one file in the lane worktree,
run the named tests, restore with `git checkout --`, rerun, check the tree is clean and no
container is left. Every row: restored run all passing, tree clean, no container left.

| control | mutation | mutated result | exact symptom |
|---|---|---|---|
| C1a | admin composition loses the ownership module (`modules = []`) | **red** 5/2 | role never listens: `stderr: nightscout multitenant: could not start: preview startup failed`, `exit: {"code":1}`; in-process boot of the mutated module: `INTERNAL_API_COMPOSITION_INVALID: at least one service module required` |
| C1b | admin listener app answers 404 instead of the ownership routes (role still listens) | **red** 5/6 | every through-role test: `Error: SOCKET_IPC_UNAVAILABLE` (route absence at request time) |
| C2a | plan drops `INSERT` on `tenant_subject_admin_audit` | **red** 12/4 | identity matrix: the audit table entry is absent (expected `inserts: true`); role startup refused (`preview startup failed`); unit plan-grant test red |
| C3 | plan also grants `DELETE` on `tenant_owner_actors` | **red** 12/4 | identity matrix `tenant_owner_actors.deletes: true` (expected false); role startup refused; unit plan-grant test red |
| C4 | admin identity readiness check removed | **red** 10/1 | `refuses a CREATEROLE identity`: `role exits instead of listening; stdout: Listening for role admin on 127.0.0.2:<port>` |
| C5 | composition adds tenant B to the operator's tenant list | **red** 10/1 | `listOwners` on B returns `outcome: 'listed', owners: [s_bowner]` instead of `denied` |
| C6 | serve's cohort refusal for admin disabled | **red** 8/1 | message absent; input was `TypeError: Cannot read properties of undefined (reading 'startsWith')` from the stub `{}` cohort config |
| C7 | the runtime-revoke test no longer revokes | **red** 10/1 | `Missing expected rejection.` |

Meanings: C1a's process symptom is masked by the CLI (`preview startup failed`); its cause is
identified by the in-process probe only. C2a/C3 role-startup refusals are by the store's privilege
screen (cause read-derived from the masked message; the screen's refusal itself is reproduced by
the earlier lane's C6 and this suite's startup-refusal tests). Before C4 was meaningful, the BYPASSRLS
case was a green ablation: the shared application connection (`postgres-connection.js:72`)
already refuses SUPERUSER/BYPASSRLS (reproduced with a scratch probe: `OWNERSHIP_STORE_UNAVAILABLE`),
so the CREATEROLE case was added (`1376c294`). C6 is red at the check, but a real cohort config
would instead fail in `operation-cohort` create with `RESTORE_COHORT_CONFIGURATION` (read-derived).

## Findings

- **read-derived**: by default `nightscout multitenant admin` exits 78: the admin default host
  `127.0.0.1` equals the CLI's consumer fallback `HOSTNAME`, which the plane rule computes even when
  `api` is not served (`listeners.js` `resolve`). An operator must set `ADMIN_HOSTNAME` (another
  loopback such as `127.0.0.2`, or an acknowledged internal address) or `HOSTNAME`. The unit test
  pins this behaviour; whether the default should change is a coordinator question.
- **read-derived**: the restore cohort census (`operation-cohort.js` `assertComplete`) refuses
  `RESTORE_COHORT_UNKNOWN_BACKEND` for any connected backend with privileges on a protected
  namespace that is not a participant's. The admin role's ownership backends are such backends
  while connected (pool idle connections included). Restore with the admin role running is
  expected to refuse; the admin role does not join the cohort (serve refuses the combination).
  Whether ownership changes must be held during lifecycle operations is a decision input.
- **read-derived**: the ownership_operator identity holds no control-namespace grant and the admin
  role composes no operation window, so the lifecycle operation window does not fence ownership
  changes for a tenant under export/restore/deletion.

## UNMEASURED

- Full suite, browser tier, the
  multitenant corpus, prcheck and CI on the lane head (coordinator's joined-candidate acceptance).
- Compose deployment: `deploy/multitenant/compose.yaml`/`bootstrap.js` do not run an `admin`
  service; bootstrap now creates the `ownership_operator` LOGIN role (role loop) but no service
  consumes its URL. Not run.
- Admin listener over TLS or a non-loopback acknowledged address; restore/deletion with the admin
  role connected; ownership change concurrent with an owner-plane mutation through a real
  tenant-admin role.
