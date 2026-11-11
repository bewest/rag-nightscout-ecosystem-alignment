# MT-ACTIVITY-ELIGIBILITY: durable pause/suspend and the evaluator's work list

*Contributor-facing measurement record, captured 2026-11-10. Not edited after capture. Lane
`codex/activity-eligibility-20261110`; local, unpushed. Implements the 16.0.0 decisions
[`activity-is-pause-suspend`](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#activity-is-pause-suspend)
and [`owner-may-pause`](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#owner-may-pause), against the
adopted [suspension and lifecycle](../../../docs/30-design/tenancy/multitenancy-decisions.md#suspension-and-lifecycle)
semantics and the [admission and activity proposal](../../../docs/30-design/tenancy/tenant-admission-and-activity.md#focused-future-acceptance).*

## Anchors

| tree | ref | commit |
|---|---|---|
| lane head | `codex/activity-eligibility-20261110` | `8f3e3c6018cd7accad2d959a094ecd883da4ca00` |
| lane base = #8898 head | `official/workspace/multitenant-20261102`, `refs/pull/8898/head` | `b70ad83fa4cdaeb7e6023137a05bd811d7db606a` |
| `official/dev` | | `4a482627bfdafb1fef8dcbe0ac6c484811cae563` |
| alignment `main` at writing | | `638e5909181db06d38a86dff8242ab13742257ca` |

`make queue-status` at start (alignment `b76d3b47`): `MT-ACTIVITY-ELIGIBILITY workspace/multitenant- not-started 0/0 UNMEASURED (1 no-gate)`.
#8898 had not moved from `b70ad83f` at the start (`git ls-remote official refs/pull/8898/head`).

Worktree: `externals/work/crm-activity-eligibility-20261110`. One commit, `8f3e3c60`, 19 files.

## What existed before this lane (read-derived, from `b70ad83f`)

- **No administrative pause or suspend existed.** The only "suspended" in the multitenant tree is the restore
  maintenance hold: `tenant_lifecycle_windows.phase` = `suspended` while `maintenance-window.js` holds a tenant,
  set back to `active` on activation. Readers see it through the operation window (`LIFECYCLE_WINDOW_SUSPENDED`).
  It is not a desired-state flag and a restore clears it by design.
- `evaluator-runtime.js` built its state map from every configured tenant and both timers called `all()` over
  that map (`evaluator-runtime.js:15,112,169-170` at `b70ad83f`). A held or removed tenant was refused per cycle
  (`EVALUATOR_WINDOW_REFUSED`, `EVALUATOR_TENANT_DISABLED`) after the cycle had started, rather than skipped.
- The consumer coordinator's timers iterated every configured tenant (`evaluator-consumers.js:74-76` at `b70ad83f`).
- Connectors have no multitenant runtime (`roles.js:81` `vcpool` has no `start`).

## What was added

**Storage** (`lib/tenant-activity/postgres-candidate.json`, migration `0001_tenant_activity`, checksum
`ac9ed41b590d0bd4382d80e50da9763e509222925e0505ebe913d2341ca04159`):

- `tenant_activity(tenant_id PK, version bigint, paused boolean, suspended boolean)` under the tenant RLS policy
  used elsewhere. Two flags, three effective states: `suspended` wins over `paused`, else `active`.
- `tenant_activity_audit(tenant_id, version, verb, authority, principal, consumer, paused, suspended, event_time)`,
  append-only; a CHECK limits `authority='owner'` rows to `pause`/`unpause`.
- A separate table from `tenant_lifecycle_windows`, so a restore's activation has no statement that touches it,
  and the restore operator grants (`maintenance-window.js` `operatorGrants`) include nothing on it.
- `grants({namespace, reader, owner, operator})`: reader `SELECT`; owner `SELECT` + `UPDATE(version, paused)` +
  audit `INSERT`; operator adds `INSERT` and `UPDATE(suspended)`. The store refuses at boot an identity whose
  privileges do not match its capability (`ACTIVITY_STORE_UNSAFE`).
- A row is provisioned by the operator (`provision`, audited). An unprovisioned tenant is **not** eligible and
  reports `…_ACTIVITY_NOT_PROVISIONED`; an unreadable store reports `…_ACTIVITY_UNAVAILABLE`.

**Policy** (`lib/tenant-activity/policy.js`): operation matrix `evaluator: [active]`, `notification: [active]`,
`ingest: [active, paused]`, `connector: [active, paused]`. Owner verbs `pause`, `unpause`; operator verbs add
`suspend`, `unsuspend`. An owner cannot act on a suspended site, so an owner unpause cannot lift a suspension;
operator `unsuspend` keeps an owner's pause.

**Evaluator** (`evaluator-runtime.js`): with an `activity` selection every trigger, both timers and the
boot acquisition read the tenant's current state first. Ineligible: no cycle, `readCurrent`, component,
acquisition or output; the generation is bumped (an in-flight cycle cannot publish), queued tickets are
released, the component is closed after any running cycle, `last()` is `null`, `isCurrent()` is false, health
reports `EVALUATOR_TENANT_PAUSED|SUSPENDED` and `activity`. The cycle re-reads the state before publishing.
On the first eligible read after inactivity the component is discarded and the next work is forced to a full
acquisition, whatever triggered it. `invalidateTenant` (what restore activation's cohort invalidation calls)
keeps the inactive code. Without an `activity` selection the runtime behaves as before.

**Consumers** (`evaluator-consumers.js`): each drain iteration checks `notification` eligibility; a
paused/suspended tenant gets no `producer.select`, no `notifier.retry` (so no retried or clearing delivery);
health `state: inactive`, `code: EVALUATOR_CONSUMER_TENANT_PAUSED|SUSPENDED`.

**Connectors**: `eligibility.create({read}).connectorWorkList(tenants)` returns the tenants to poll (paused
keeps polling, suspended does not). No caller exists yet.

**Owner API** (`owner-settings.js`, wired in `owner-preview.js` when `ownerActivity` is configured, which
requires `ownerSettings`): `GET /api/v1/tenant/activity`, `POST /api/v1/tenant/activity/pause` and
`/unpause` with `{expectedVersion}`. The tenant is the request-resolved tenant, which the router already
requires to equal the credential's tenant. Authority is the owner-settings configuration authority (active and
`can_configure`). No suspend route. Errors: `ACTIVITY_FORBIDDEN` 403, `ACTIVITY_SUSPENDED` 409,
`ACTIVITY_VERSION_CONFLICT` 409, `ACTIVITY_NOT_PROVISIONED` 404.

**Configuration**: evaluator `activity: {connectionEnv, namespace}`; owner preview `ownerActivity: {connectionEnv,
namespace}`. Both optional, both run the catalogue `check` before use. `deploy/multitenant/config.js` is not
changed (internal-listener lane's area).

### Owner-facing text, as written (`policy.OWNER_NOTICE`)

> **pause:** While your site is paused, alarms are not computed or delivered. Uploads from your devices are
> still stored. Nightscout will not warn you about high or low glucose, stale data or anything else until you
> unpause. If you rely on Nightscout alarms, make sure you have another way to be alerted before you pause.
>
> **unpause:** When you unpause, Nightscout recalculates from your current data before it shows or sends any
> alarm.
>
> **suspended:** Your site is suspended by the operator. Nothing runs for your site, including uploads and
> alarms. Contact your operator.

`GET` returns the pause text while active, pause + unpause text while paused, the suspended text while suspended.

## Checks (reproduced)

Node v22.23.4. PostgreSQL 16.15 in a disposable container, `postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea`,
bound to 127.0.0.1, database `activity_disposable_test`, removed afterwards (`docker ps -a` count 0). No MongoDB.

| check | result at `8f3e3c60` |
|---|---|
| `tests/tenant-activity.test.js` (policy, actual runtime with synthetic component, actual router with synthetic authenticator/store) | 12 passing |
| non-native tests touching the changed modules (18 files: evaluator-*, owner-*, operation-cohort*, maintenance window, operation window, startup admission, realtime bootstrap, multitenant inventory, notification producer, tenant-activity) | 194 passing |
| native, `NS_EVALUATOR_CONSUMERS_TEST=1 NS_OWNER_PREVIEW_TEST=1 NS_M5_CURRENT_STATE_PROOF_TEST=1`: `tenant-activity.integration`, `evaluator-consumers.integration`, `owner-preview.integration`, `tenant-current-state-recovery-proof.integration` | 29 passing |
| `NS_OWNER_CONFIGURATION_DOCKER_TEST=1 owner-configuration.integration` (before commit, same tree) | 14 passing |
| `node scripts/test-tiers.js check` | `616 test files, 8 tiers: ok` |
| `npm run lint` | exit 0, 0 errors, 49 warnings; unmodified `b70ad83f` also 49 warnings |

### Acceptance with synthetic tenants A and B (`tests/tenant-activity.integration.test.js`)

The actual evaluator role runs as a child process (`serve.start(['evaluator'])`) with its realtime consumer,
restricted PostgreSQL identities, and a controlled UDS sink; triggers are the actual IPC `acquire`/`tick`/`wake`
and, in phase 1, the actual recovery/time timers at 150 ms. Oracles are independent of the runtime: A's replay
checkpoint row, outbox request rows, sink effects, stored entries and the audit table.

| criterion | observed |
|---|---|
| A paused: no acquisition, timers or output | checkpoint stays `'0'` from before the process existed through boot, a new A reading, `acquire`, `tick`, `wake` and ~700 ms of timers; 0 A requests, 0 A sink effects; health `EVALUATOR_TENANT_PAUSED`, outputRevision `null`; consumer `EVALUATOR_CONSUMER_TENANT_PAUSED`; `last(A)` null |
| B unaffected | B outputRevision advanced by more than 2 over the timer window; B checkpoint advanced; B low alarm delivered after restart |
| uploads for A still stored while paused | 3 A entries present after uploads at pause time (written through the storage port, not HTTP) |
| unpause recomputes before publishing | first `tick` after owner unpause returns output with `trigger: 'acquisition'`; A checkpoint advanced; every A outbox request carries `lastSGV: 45` (the reading uploaded while paused), none the pre-pause 50 |
| A suspended: nothing runs | checkpoint unchanged, 0 A effects, `EVALUATOR_TENANT_SUSPENDED`; owner `unpause` → `ACTIVITY_SUSPENDED` |
| restart with A paused | fresh evaluator process: `EVALUATOR_TENANT_PAUSED`, checkpoint unchanged |
| restore activation path | `invalidateTenant(A)` in the actual process, then `acquire`/`tick`: still paused, no work |
| owner of A pauses A | router + actual owner store: 200, `paused`, notice text; audit row `{A, pause, owner, owner, tenant-admin}` |
| owner of A cannot pause B | owner-A credential on B's host → 401; B stays `active`, no audit row |
| owner cannot suspend | no route (404); policy `ACTIVITY_FORBIDDEN`; the owner database identity's `UPDATE … SET suspended` fails `42501`; a store created as `reader` with the owner identity is refused `ACTIVITY_STORE_UNSAFE` |

Restore with the actual controller: `tests/tenant-maintenance-window.test.js` adds a case that runs the actual
`maintenance-window.js` `withRestore` (simulated backend protocol, as the rest of that file) whose cohort
invalidation calls the actual evaluator runtime with A paused. After activation the window is `active`, the
durable activity row is still `{paused: true}`, and timers plus `acquire` do no work for A. A native restore
was not run (see below).

## Break-it controls (each red, then restored by copying the saved file back; `cmp` identical; green rerun)

| control | edit | red, exact symptom |
|---|---|---|
| schedule from configured presence | `evaluator-runtime.js` `trigger`: drop the eligibility line, enqueue every configured tenant | unit 4 failing: `ACTIVITY_PAUSED_NO_WORK` actual `[create, acquisition, close, create, time-only, acquisition, time-only, acquisition]` expected `[]`. Native 2 failing: `ACTIVITY_PAUSED_NO_ACQUISITION` checkpoint `'0'` → `'1794354466697'`; `ACTIVITY_SUSPENDED_NOTHING_RUNS` checkpoint advanced. (The cycle's publication re-check still withheld output; the work oracle caught it.) |
| restore activation clears the pause | `maintenance-window.js` activation also runs `UPDATE "<ns>".tenant_activity SET paused=false,suspended=false` | target case red: `ACTIVITY_RESTORE_PRESERVES` `paused: true` expected, `false` actual. Four other cases in the file also go red because their simulated backend has no activity row and refuses the unknown statement ("Unexpected simulated query"); those reds are the fixture refusing SQL, not activity assertions. |
| owner pause verb skips the tenant check | `owner-settings.js` middleware: drop `actor.tenant !== tenant` | unit and native: `ACTIVITY_CROSS_TENANT` expected 401, actual 200 (owner-A credential paused B; both tenants have a principal named `owner`, as tenant-local names do) |
| extra: unpause resumes on the trigger's own kind | drop `if (state.reactivated) acquisition = true` | unit: `ACTIVITY_UNPAUSE_RECOMPUTES` first work `time-only`, expected `acquisition` |

An earlier version of the native paused case read A's checkpoint *after* boot; under the first control it
stayed green on the checkpoint (boot had already acquired) and went red later for an unrelated reason
(`last` was null). The case now reads the checkpoint before any evaluator process exists and writes a new A
reading during the pause; the control then goes red at `ACTIVITY_PAUSED_NO_ACQUISITION`.

## Observation outside this lane (reproduced, mechanism not diagnosed)

With the evaluator timers at 150 ms, the realtime consumer does not deliver a **changed** reading: after a new
A reading, `acquire`, `tick`, `wake`, `flush`, the consumer health is `refused` / `EVALUATOR_CONSUMER_REFUSED`
with an outbox request left `attempting`, and no sink effect within 10 s. Failed 4 of 4 runs on an unmodified
`b70ad83f` checkout (scratch test, no activity selection) and 3 of 4 on this lane with no activity selection. The lab
default is 1,000,000 ms timers, which is why the existing consumer suite does not see it. This lane's native
case therefore measures delivery only with the default timers. Proposed for triage as a possible defect
(consumer refusal under evaluator output churn); no BF id allocated. Whether production intervals reach this
is UNMEASURED.

## Not measured, not wired, open

- **API ingest/serving under suspend is not refused.** The decision says nothing runs while suspended; the
  API role has no activity check yet (`preview-api.js` `prepareTenant` is the natural hook). Uploads for a
  suspended tenant are still stored (the suspended case writes one through the storage port). UNMEASURED at
  HTTP. Wiring it touches `preview-config.js`, which may overlap the internal-listener lane's endpoint config.
- **Realtime role** (`preview-realtime.js`, `realtime/runtime.js`) does not read activity: sockets stay open and
  realtime fan-out continues for paused and suspended tenants. The adopted text says suspension disconnects
  sockets and shows last data visibly stale.
- **Evaluator boot warm-up** (`tenant-startup` `warm`, `provisionTenant`) still runs for paused/suspended tenants
  (checkpoint-row readiness, no evaluation).
- **Owner preview boot with `ownerActivity`** is not exercised by any test; the router and store are, separately.
- **Native restore** (actual `withRestore` on PostgreSQL with an activity row) not run; the restore guarantee is
  measured on the simulated-backend protocol plus the native `invalidateTenant` path, and by construction (no
  restore statement or grant touches `tenant_activity`, read-derived).
- **Operator CLI/deploy wiring** for `provision`/`suspend` and the `grants()` statements: not added
  (`deploy/multitenant/config.js` belongs to the internal-listener lane).
- `deploy`/`site` docs, OpenAPI for the new owner routes: not written.

## Addendum, 2026-11-10 (second capture): adopted semantics, always-provisioned rows, deletion auto-pause

Implements [`activity-adopted-semantics-wiring`](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#activity-adopted-semantics-wiring),
[`activity-row-always-provisioned`](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#activity-row-always-provisioned) and
[`deletion-request-auto-pauses`](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#deletion-request-auto-pauses)
(alignment `main` `c7370e961` when briefed). The consumer refusal at 150 ms timers is left to its own lane.

| tree | ref | commit |
|---|---|---|
| lane head | `codex/activity-eligibility-20261110` | `07981b55b76779ee25e023ebc0e0c9c2b9bce2f2` (one commit on `8f3e3c60`, 24 files) |
| previous lane head | | `8f3e3c6018cd7accad2d959a094ecd883da4ca00` (confirmed head, clean worktree, before starting) |
| `official/dev` | | `4a482627bfdafb1fef8dcbe0ac6c484811cae563` |
| alignment `main` at writing | | `3efd647a492c84763eae09cf8fe8b1f44f62e1f8` |

### Design change: the activity tables moved into the lifecycle (control) namespace

A backfill migration must read the tenant inventory, and catalogue SQL is static: a separate activity
namespace cannot name the control namespace. The tables are therefore migration `0007_tenant_activity` of
`lib/tenant-lifecycle/postgres-candidate.json` (checksum `04e34feac301aa516bfe1bbac7355e413db26a2a5ccf4c03be652176d718b84e`);
`lib/tenant-activity/postgres-candidate.json` is deleted. Consequences:

- `tenant_activity.tenant_id` references `tenant_lifecycle_windows`; a tenant is "provisioned" when it has a
  window row, the same definition the admin-lifecycle lane's `tenantPhase` uses.
- Backfill: `INSERT … SELECT FROM tenant_lifecycle_windows` plus an audit row
  (`provision/operator/migration/backfill-0007`). `tenant_lifecycle_windows` has FORCE ROW LEVEL SECURITY, so a
  non-superuser schema owner would see no rows; the migration runs `NO FORCE` → backfill → `FORCE` inside its
  own transaction. A runner that is not the windows' owner fails the migration (loud), it does not backfill nothing.
- `LEDGER_TABLES` (derived from the catalogue) now includes both tables, so the ceremony and key-retention
  relation inventories and the whole-deployment census include them automatically (census 47→49, 48→50 with
  the profile successor; seed rows added).
- **Numbering:** the export-expiry lane adds `0006_tenant_lifecycle_artifact_removal` to the same catalogue.
  This lane uses `0007` so either join order keeps names lexically ordered; neither is released.
- New columns `deletion_request_id`, `paused_before_deletion` (both null or both set). New grant set
  `grants({ceremony})`: `UPDATE(version, paused, suspended, deletion_request_id, paused_before_deletion)`, audit `INSERT`.

### What is wired now

| behaviour | where | measured |
|---|---|---|
| suspend refuses uploads and reads | API `prepareTenant(tenant, req)` → `lib/tenant-activity/serving.js`; `423 TENANT_SUSPENDED`; forwarded socket operations are admitted as uploads, so they refuse too | reproduced, tenant-app composition |
| pause refuses reads and UI, admits uploads | uploads = POST/PUT/PATCH/DELETE, OPTIONS, `GET /api/v2/authorization/request/:token`; everything else is a read → `423 TENANT_PAUSED` | reproduced, tenant-app composition |
| unreadable state on API | `503 TENANT_ACTIVITY_UNAVAILABLE` | reproduced, unit |
| sockets disconnected on pause and suspend | `serving.gateReadCurrent` wraps realtime `readCurrent`; ineligible → `protocol.invalidateTenant` + disabled | reproduced, actual realtime protocol/runtime with synthetic sockets |
| every tenant has a row | migration backfill; `provisionInTransaction` (Compose `bootstrap.js` calls it in the tenant transaction) | reproduced, native |
| unreadable row stops only that tenant | evaluator `EVALUATOR_ACTIVITY_UNAVAILABLE` / `…_NOT_PROVISIONED`, one `console.warn` per change | reproduced, native + unit |
| deletion request pauses; cancel restores; execution suspends | `lib/tenant-activity/deletion.js`, called inside `ceremony.js` request/cancel/claim/execute transactions | reproduced, native, actual ceremony on PostgreSQL |
| owner may pause/unpause while a request is pending | owner store unchanged; no phase check | reproduced, native |

Configuration: API `preview-config.js` and realtime `realtime/config.js` accept an optional
`activity: {connectionEnv, namespace}` (namespace = the control namespace). Without it behaviour is unchanged.
The internal-api endpoint config is not touched. `realtime/config.js` and `preview-api.js` are also edited by the
internal-listener and root-admin-parity lanes; expect one-line merges at the `c.exact(...)`/`fields(...)` lists
and the `createTenantApp` call.

### Owner-facing text, as now written (`policy.OWNER_NOTICE`)

> **pause:** While your site is paused, alarms are not computed or delivered, and your site and its data cannot be
> viewed. Uploads from your devices are still stored. Nightscout will not warn you about high or low glucose, stale
> data or anything else until you unpause. If you rely on Nightscout alarms, make sure you have another way to be
> alerted before you pause.
>
> **unpause:** (unchanged) When you unpause, Nightscout recalculates from your current data before it shows or sends any alarm.
>
> **suspended:** Your site is suspended by the operator. Nothing runs for your site: uploads are refused, your site
> and its data cannot be viewed, and alarms are not computed or delivered. Contact your operator.
>
> **deletion** (returned as `notice` by `requestDeletion`): You have asked to delete your site. Alarms stop now: from
> this moment alarms are not computed or delivered, and your site and its data cannot be viewed. Uploads from your
> devices are still stored until the operator carries out the deletion. If you cancel the request, your site goes
> back to how it was before you asked. If you rely on Nightscout alarms, make sure you have another way to be alerted now.

There is no owner HTTP route for deletion in this tree; any owner UI that requests deletion must show `notice`.

### Checks (reproduced, at `07981b55`)

PostgreSQL 16.15 `postgres@sha256:721873c3…80ea` (disposable, removed; `docker ps -a` count 0), Node v22.23.4.

| check | result |
|---|---|
| `tests/tenant-activity.test.js` | 16 passing |
| non-native tests touching the changed modules (47 files by name match) | 559 passing, 10 failing: `api.count-where`, `authdelay`, `api3.alarm-socket.*` need a MongoDB-backed single-site boot; the same 10 fail identically on `8f3e3c60` in this environment |
| `tenant-lifecycle`, `tenant-deployment-operations`, `tenant-operations`, `tenant-insertion-lifecycle` | 31, 28, 42 (with insertion) passing |
| native: tenant-activity (7), evaluator-consumers, owner-preview, current-state-recovery | 33 passing |
| `NS_KEY_RETENTION_DOCKER_TEST=1 tenant-key-retention.integration` (Vault `@sha256:962a9287…`) | 6 passing (fixture now provisions windows + activity and grants the ceremony role) |
| `NS_TENANT_OPERATIONS_PG_TEST=1 tenant-operations.integration` | 5 passing |
| `NS_MULTITENANT_PREVIEW_PROCESS_DOCKER_TEST=1 multitenant-preview-process.integration` | 16 passing |
| `deploy/multitenant/*.test.js` (node test runner) | 10 pass |
| `test-tiers.js check` / `npm run lint` | ok / 0 errors, 49 warnings (unchanged) |

Native acceptance observed (synthetic A/B):

- Backfill: A and B `version 1, active`, audit `provision/operator/migration/backfill-0007`, windows FORCE restored.
- Provisioning: tenant C committed with its window has an active row; tenant D whose transaction failed after
  the activity insert has neither row; an activity row without a window is refused `23503`.
- Unreadable A (a restrictive policy that raises division-by-zero on A's row only): A `EVALUATOR_ACTIVITY_UNAVAILABLE`,
  checkpoint unchanged, 0 A effects, exactly one stderr warning naming A; B outputRevision rose over three
  acquisitions, B ready, B low alarm delivered.
- Deletion: request → A paused (evaluator `EVALUATOR_TENANT_PAUSED`), B active, notice contains "Alarms stop now";
  owner unpause then pause during the pending request both succeed; cancel → active (the pre-request state);
  paused-before-request → cancel → still paused; request → confirm → claim → suspended, owner unpause refused
  `ACTIVITY_SUSPENDED`, evaluator `EVALUATOR_TENANT_SUSPENDED`. Audit sequence: `deletion-request:owner,
  unpause:owner, pause:owner, deletion-cancel:owner, pause:owner, deletion-request:owner, deletion-cancel:owner,
  unpause:owner, deletion-request:owner, deletion-execute:operator`.
- HTTP matrix (actual `createTenantApp` + actual reader store; data routes are a stub router):

  | | A read | A upload | A exchange | B (all) |
  |---|---|---|---|---|
  | active | 200 | 201 | 200 | 200/201/200 |
  | A paused | 423 TENANT_PAUSED | 201 | 200 | unchanged |
  | A suspended | 423 TENANT_SUSPENDED | 423 TENANT_SUSPENDED | 423 | unchanged |

### Break-it controls (each red, then restored from a saved copy, `cmp` identical, green rerun 23 passing)

| control | edit | red, exact symptom |
|---|---|---|
| pause does not gate reads | `serving.operationOf` returns `ingest` always | `ACTIVITY_HTTP_PAUSED`: `A read` `200` where `423 TENANT_PAUSED` expected |
| suspend admits uploads | policy `ingest` includes `suspended` | `ACTIVITY_HTTP_SUSPENDED`: `A upload` `201`, `A exchange` `200` where `423` expected |
| sockets not disconnected | `gateReadCurrent` returns null without `invalidate` | both realtime cases: `ACTIVITY_SOCKET_DISCONNECTED` |
| backfill blind to RLS | drop the `NO FORCE` statement from 0007 (checksums recomputed) | `ACTIVITY_BACKFILL`: actual `[]`, expected A and B rows |
| provisioning omits the row | `provisionInTransaction` writes nothing | `ACTIVITY_PROVISIONED_WITH_TENANT`: actual `[]`, expected C's row |
| unreadable row stops everyone | evaluator deactivates every tenant on `ACTIVITY_UNAVAILABLE` | unit `ACTIVITY_UNREADABLE_B_CONTINUES` (B thrashes `close/create` instead of cycling); native: B alarm never delivered (`Evaluator native condition watchdog` at the B-delivery wait) |
| request does not pause | ceremony skips `activity.requested` | `ACTIVITY_DELETION_REQUEST_PAUSES`: `'active' !== 'paused'` |
| cancel does not restore | ceremony skips `activity.cancelled` | `ACTIVITY_DELETION_CANCEL_RESTORES (active)`: `'paused' !== 'active'` |
| execution does not suspend | `deletion.executing` returns without writing | `ACTIVITY_DELETION_EXECUTION_SUSPENDS`: `'paused' !== 'suspended'` |

### Not measured or open after this addendum

- The API admission is measured in the actual tenant-app composition with stub data routes; the full API role
  (`preview-api` boot with `activity` selected) and the realtime role process are not run with activity
  selected. `multitenant-preview-process` (16 passing) runs without the selection.
- Per-request activity read on the API: one extra query per request; overhead UNMEASURED.
- 423 for refusals is a choice: uploaders that treat 4xx as final may drop data uploaded during suspension; 503
  would invite retries. The human-session (OIDC) routes are mounted before `createTenantApp` and are not gated.
- Cancel restores the state from before the *first* pending request, overriding owner pause/unpause made while
  pending (the decision's wording). Deletion execution leaves the row suspended; restoring a deleted tenant's
  data does not unsuspend it.
- Deploy wiring (activity selections, the four roles' grants) remains with the deploy/internal-listener owner.

**Shared password file (re-run).** Both rounds wrote the PostgreSQL password to the session scratchpad's shared
`pgpw`, and deleted it at the end of each round. That overwrote and removed another lane's file. The runs recorded
above authenticated against this lane's own container on port 55437, so the password they read was this lane's.
They were re-run anyway at `07981b55` with a private `scratchpad/activity-lane/pgpw` (mode 600) and a fresh container
(same digest, port 55447, removed afterwards). Unit `tenant-activity` plus native tenant-activity,
evaluator-consumers, owner-preview and current-state-recovery: **49 passing** (16 + 33), unchanged. The break-it
controls were not re-run. Their recorded symptoms are assertion failures, which need an authenticated connection.
