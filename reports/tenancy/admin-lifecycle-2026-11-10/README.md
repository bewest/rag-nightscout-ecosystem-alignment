# MT-ADMIN-LIFECYCLE-FIT: the admin role beside tenant lifecycle operations

*Contributor-facing measurement record, captured 2026-11-10. Not edited after capture. Lane
`codex/admin-lifecycle-20261110`; local, unpushed. Implements the 16.0.0 decisions
[`restore-census-and-ownership-phase`](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#restore-census-and-ownership-phase)
and [`admin-plane-same-address-different-port`](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#admin-plane-same-address-different-port).*

## Anchors

| tree | ref | commit |
|---|---|---|
| lane head | `codex/admin-lifecycle-20261110` | `26b5349d7e734a36f2caa67271d5673e30cab0fe` |
| lane base = ownership-role lane head | `codex/ownership-role-20261110` | `1376c2946ce71078b477d4e0f2e4d428f29778ed` |
| #8898 head under that | `official/workspace/multitenant-20261102` | `b70ad83fa4cdaeb7e6023137a05bd811d7db606a` |
| `official/dev` | | `4a482627bfdafb1fef8dcbe0ac6c484811cae563` |
| alignment `main` at writing | | `638e5909181db06d38a86dff8242ab13742257ca` |

`make queue-status` at start: `MT-ADMIN-LIFECYCLE-FIT codex/ownership-role-2 not-started 0/0 UNMEASURED (1 no-gate)`.

| commit | what |
|---|---|
| `bb5753b0` | plane rule: admin may share the consumer listener's address on another port |
| `26b5349d` | restore census by grants; ownership refuses on a non-active tenant; native suite |

21 files, +682/−72 against `1376c294`.

## What changed

**Plane rule** (`lib/server/serve/listeners.js` `checkPlane`). An internal-plane listener may bind the
consumer listener's address, loopback or non-loopback, when the ports differ. Refused: every interface
(acknowledged or not); the consumer listener's port on its address, checked against the consumer
listener even when `api` is not served (`overlaps(spec, consumer)`, so a consumer on every interface
also claims its port on 127.0.0.1); a non-loopback address without
`ADMIN_INSECURE_BIND_ACKNOWLEDGED=true`. New message: `... would share the consumer listener ...; give it
a port of its own with ADMIN_PORT`. The reproduced case from the decision row (`HOSTNAME=127.0.0.1`,
admin at its default `127.0.0.1:1338`) now resolves and the role listens (native suite case 1).

**Restore census** (`lib/server/serve/operation-cohort.js` `assertComplete`). The actor query now also
returns, per backend, `clinical`: whether the backend's database identity holds any privilege (direct,
through any role membership, or by owning the table) on a **clinical table** in the protected
namespaces, computed from `pg_class`/`has_table_privilege`/`has_any_column_privilege` in the same
statement, so at census time. A backend that is not a registered participant backend is accepted only
when `clinical === false` (counted in a new `exempt` field); `true`, `null` or a missing flag refuses
`RESTORE_COHORT_UNKNOWN_BACKEND`. Participants match by PID, birth and role exactly as before.

*Clinical table catalogue*: `lib/tenant-lifecycle/clinical-catalogue.js` `CLINICAL` = `entries,
treatments, devicestatus, profile, food, settings, activity`, matched by `relname` inside the protected
namespaces. It is the set `logical-restore.js` reconciles (moved there from its local `HISTORY`/`CLINICAL`
sets; logical-restore now reads it). Not in it: `tenant_insertion_ordinal`, `schema_migrations`,
`tenant_write_clock`, consumer checkpoints, outbox, alarm suppression, authorization, secrets, legacy,
access (see decision question 1).

**Ownership phase** (`lib/tenant-lifecycle/tenant-phase.js`, `lib/tenant-ownership/postgres.js`).
`tenantPhase(connection, {namespace, tenant, hold})` reads only existing control state:
`tenant_lifecycle_windows.phase` (`suspended` while a restore holds the tenant), and a deletion request
in `tenant_lifecycle_requests` that is executed or whose ceremony is not `cancelled`, or any ceremony row
not `cancelled`. No window row → `unprovisioned`. With `hold: true` it first takes the tenant's window
lock with `pg_try_advisory_xact_lock_shared(lock_key)`; a restore holding it exclusively reads as `held`.
The phase is read after the lock (READ COMMITTED), and the shared lock lasts to commit, so a restore
cannot take its exclusive lock and enter its data phase under an ownership change. Ownership `add`,
`transfer`, `recover` call it after operator authority and before row locks; not active → `refused`,
`OWNERSHIP_TENANT_INACTIVE`, audited with `detail.lifecycle` (`suspended|held|deletion|unprovisioned`),
no ownership row change, current owners returned. `list` does not check. The helper is exported for
other operator verbs (activity-eligibility lane's owner pause), with `phaseGrants({namespace, role})`.

Wiring: the store takes `lifecycleNamespace` (required, distinct from the authorization namespace);
`MULTITENANT_ADMIN_CONFIG` `ownership.lifecycleNamespace` (required); the store's privilege screen adds the
three control tables as SELECT-only; the contract `ownership-operations.json` adds
`OWNERSHIP_TENANT_INACTIVE` to the three `refused` enums; the deployment plan grants
`<prefix>_ownership_operator` `USAGE` on the control schema and `SELECT` on `tenant_lifecycle_windows`,
`tenant_lifecycle_requests`, `tenant_lifecycle_ceremony`. No clinical grant, no operation registration,
no window or ceremony write.

## Commands and results (lane head `26b5349d`, from tool output)

```bash
cd externals/work/crm-admin-lifecycle-20261110      # npm ci --ignore-scripts; npm run bundle (both exit 0)
NODE_ENV=test NS_ADMIN_ROLE_DOCKER_TEST=1 NS_TENANT_OWNERSHIP_DOCKER_TEST=1 NS_ADMIN_LIFECYCLE_DOCKER_TEST=1 \
  node_modules/.bin/mocha --fail-zero --timeout 120000 --exit --require ./tests/hooks.js \
  tests/admin-lifecycle-fit.integration.test.js tests/admin-role-ownership.integration.test.js \
  tests/tenant-ownership-postgres.integration.test.js tests/admin-role.test.js tests/tenant-ownership.test.js \
  tests/internal-api-contracts.test.js tests/internal-api-composition.test.js tests/serve-listeners.test.js \
  tests/serve-roles.test.js tests/nightscout-cli.test.js tests/multitenant-inventory.test.js \
  tests/operation-cohort.test.js tests/operation-cohort-peers.test.js tests/tenant-logical-restore.test.js \
  tests/tenant-maintenance-window.test.js
```

| check | result |
|---|---|
| focused family above (three native suites + unit/contract/serve/CLI/inventory/cohort/restore) | **185 passing, 0 failing**, exit 0; no `admin-lifecycle-fit`/`tenant-ownership`/`admin-role-ownership` container left |
| new native suite alone | 4 passing |
| `tests/tenant-ownership-postgres.integration.test.js` alone | 9 passing (was 7: two phase cases added) |
| `tests/admin-role-ownership.integration.test.js` alone | 11 passing |
| `node scripts/test-tiers.js check` | `617 test files, 8 tiers: ok` |
| `node scripts/test-multitenant.js --list` | `51 opt-in suites (51 in the inventory); 28 start their own containers` (doc counts updated to 51/27/28/50) |
| `node --test deploy/multitenant/bootstrap.test.js deploy/multitenant/restore.test.js` | pass 10, fail 0 |
| `npm run lint` | 0 errors, 51 warnings (unchanged count) |
| `npm run test:unit:ci` | **3119 passing**, exit 0 |
| commit `bb5753b0` alone (scratch export): `serve-listeners` + `admin-role` unit | 32 passing |

PostgreSQL: `postgres@sha256:9e2cf6287f25c3151f4c9421ccce2b17f3e60061c111a29165e0d2cdd9ff0a97` for all
three native suites (the ownership-store suite was moved from the `postgres:16` tag to this digest and
given the same label-and-reaper pattern). Each suite starts its own labelled container on a random
loopback port with generated passwords in the child environment; a detached reaper removes it if the
mocha process dies. No MongoDB.

### The new native suite (`tests/admin-lifecycle-fit.integration.test.js`, `NS_ADMIN_LIFECYCLE_DOCKER_TEST=1`)

Applies the deployment plan's PostgreSQL bootstrap without Vault: every role in `plan.layout('nsfit')`,
every catalogue owned by the NOLOGIN owner, exactly `plan.grants(l)`, window rows for A and B, restore
authority for the plan's `operator` on A. Then:

- a real `nightscout multitenant admin` process with `HOSTNAME=127.0.0.1 PORT=<p1>` and `ADMIN_PORT=<p2>`
  (admin address defaulted to 127.0.0.1), connected as `ownership_operator`;
- four lifecycle-participant peers on real Unix sockets (synthetic status handlers), each reporting one
  real backend opened as that role's database identity (`api`, `realtime`, `evaluator`, `owner_writer`);
- the real `operation-cohort.createRemote` coordinator and real `maintenance-window.create(...).withRestore`
  on a pool of the plan's `operator` identity.

Cases:
1. admin on the consumer address at another port listens; `ADMIN_PORT=<p1>` exits 78 `would share the
   consumer listener`; `ADMIN_HOSTNAME=0.0.0.0` (acknowledged) exits 78 `every interface`;
   `ADMIN_HOSTNAME=192.0.2.10` without acknowledgement exits 78 `ADMIN_INSECURE_BIND_ACKNOWLEDGED=true`.
2. with ≥1 `ownership_operator` backend in `pg_stat_activity`, tenant A's restore runs to `activated`;
   inside the claim, `addOwner` and `transferOwner` on A return `refused`/`OWNERSHIP_TENANT_INACTIVE`
   (audit `detail.lifecycle = 'held'`), A's actor rows unchanged; `addOwner` on B applies; after
   activation the same add on A applies.
3. `GRANT SELECT` on `entries.entries` to `ownership_operator` under the running role: the restore
   refuses `RESTORE_COHORT_UNKNOWN_BACKEND` before its body, A stays `active`; revoked, the next restore
   activates.
4. an unregistered backend as the `realtime` identity: refuses `RESTORE_COHORT_UNKNOWN_BACKEND`, A active.

The restore body is a read under the claim; the logical clinical reconciliation (`logical-restore.js`
`restore`) is not run here (see UNMEASURED). A superuser session would itself be an unregistered backend
with every privilege, so the suite opens its bootstrap session only between censuses.

### Ownership-store phase cases (`tests/tenant-ownership-postgres.integration.test.js`)

- add, transfer, recover on A each refuse `OWNERSHIP_TENANT_INACTIVE` with one audit row per attempt and
  no actor change, for each of: window `suspended` (as `maintenance-window.js` writes it), window lock held
  exclusively by another session (`held`), a pending deletion request with a `requested` ceremony
  (`deletion`), no window row (`unprovisioned`); after the ceremony is `cancelled` and the window restored,
  the same add applies; B untouched; `list` on a suspended tenant still lists.
- lock: an add blocked on the policy row lock holds A's window lock `ShareLock` in `pg_locks`; another
  session's `pg_try_advisory_lock` on A's key returns false; after the add commits (`applied`) it returns true.
- store screen: `UPDATE(phase)` on windows, or `SELECT` on the ceremony table revoked, each refuse
  `OWNERSHIP_STORE_UNSAFE`.

## Break-it controls

Runner `controls-run.py` (here; results `controls.json`): mutate, run the named files, `git checkout --`,
rerun. Every row: restored run all passing, tree clean, no container left.

| control | mutation | mutated (pass/fail) | exact symptom |
|---|---|---|---|
| C0 | census exemption line removed (pre-decision behaviour) | **red** 2/2 | restore with admin connected: `Error: RESTORE_COHORT_UNKNOWN_BACKEND`; case 3's final "revoked: census accepts the role again" also `RESTORE_COHORT_UNKNOWN_BACKEND` |
| C1 | plan grants `ownership_operator` `SELECT` on `entries` | **red** 11/2 | restore with admin connected: `Error: RESTORE_COHORT_UNKNOWN_BACKEND`; unit plan-grant test: grant list differs |
| C2 | exemption by role name (`/_ownership_operator$/`) instead of the grants flag | **red** 3/1 | case 3: `Missing expected rejection.` (census accepts the identity holding `entries`) |
| C1+C2 | both | 3/1: **restore acceptance green** with the clinical grant in the plan; case 3 `Missing expected rejection.` | a name-based exemption cannot see a widened grant; C1 alone is red, so the grant check is what refuses it |
| C3 | ownership phase check removed (`plan(...)` regardless) | **red** 11/2 | store suite deep-equal fails at `add while suspended` (expected `refused`/`OWNERSHIP_TENANT_INACTIVE`); fit case 2: refused-object deep-equal fails |
| C3b | phase read without the shared lock (`hold: false`) | **red** 10/3 | `add while held`; `ownership change holds the window lock shared`; fit case 2 deep-equal fails (the change applied during the restore claim) |
| C4a | `checkPlane` no longer compares with the consumer listener | **red** 29/3 | `refuses the consumer listener's port ...` and the admin-definition case: message did not match `/would share the consumer listener/` (pairwise check still refuses when both are served); admin-role serve case red |
| C4b | `overlaps` always false (same port allowed everywhere) | **red** 28/4 | `Missing expected exception.` on the same-port cases; admin-role serve case red |

Meanings: C2 alone is red only at case 3 because the plan grants carry no clinical table; C1+C2 is the
control the decision asked for (it goes green where it must not). C4a shows the overlap-with-consumer check
is the only guard when `api` is not served in the same process. An earlier vacuity was caught on the way:
`tests/operation-cohort.test.js`'s "broken census comparison" mutation targeted the old comparison text,
so after the census rewrite it no longer applied; it now asserts its mutation applies.

## Findings

- **reproduced**: with the deployment plan's grants, the admin role's backends are accepted by the census
  and a tenant restore completes while it is connected; widening its grant to one clinical table makes the
  same restore refuse before suspension.
- **reproduced**: during a restore's claim, ownership changes on that tenant refuse as `held`; on another
  tenant they apply.
- **read-derived**: export has no durable lifecycle state (`exportTenant` is one snapshot transaction;
  no window, request or ceremony row). "Not exporting" is not checked; nothing was invented for it
  (decision question 2).
- **read-derived**: a deletion request committed between the ownership transaction's phase read and its
  commit is not fenced (the ceremony path takes no window lock at request time).

## Decision questions

1. **Breadth of the census exemption.** Literal to the decision: any identity without a clinical-table
   privilege is exempt, so a non-participant with writes on outbox, alarm suppression, checkpoints,
   authorization, secrets, the write clock or `tenant_insertion_ordinal` is now accepted (the plan's
   `readiness` identity, holding `SELECT` on clinical `schema_migrations`, also becomes exempt). Restore
   itself writes the clinical tables, `tenant_insertion_ordinal` and `tenant_write_clock`.
   Recommendation (reliability, low cost): count every table the restore writes as clinical for the
   census (add `tenant_insertion_ordinal` and `tenant_write_clock`), keeping the admin identity exempt.
   Unmeasured: whether any deployed non-participant holds those.
2. **Export.** No existing state marks a tenant as exporting. Options: accept that an ownership change may
   land beside an export (the artifact is one consistent snapshot), or add export state (export-expiry
   lane's area). Recommendation: accept; the snapshot already gives a consistent artifact.

## UNMEASURED

- The logical clinical reconciliation (`logical-restore.js restore`) with the admin role connected; the
  compose demo (`deploy/multitenant/demo.sh demo`) runs no `admin` service.
- Real participant roles (the peers here are synthetic status handlers over real backends).
- Deletion ceremony execution with the admin role connected.
- Full suite, browser tier, multitenant corpus, prcheck, CI (coordinator's joined-candidate acceptance).
- nightscout-deploy overlay: needs the four control grants and `ownership.lifecycleNamespace`.
