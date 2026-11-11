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
