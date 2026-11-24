# Multitenant operations runbook, warm-up plan and migration-rule transition

*Contributor-facing, draft, 2026-11-23. Procedures here are **read-derived** from the decisions and
source named in each section unless a row says **measured**. The one drill reported below ran on a
workstation with synthetic data; it is not a production figure. Decisions are linked, not restated:
start at [decisions in force](decisions-in-force.md). Alert rules that point at these sections live in
the deployment repository at `2d1fa41`, in `observability/alerts/multitenant.rules.yml`.*

Operator-facing safety note: Nightscout is a secondary display. Operators must tell people who rely on
alarms that during any restart, failover or restore on this page alarms and displayed values can be late
or missing, and that their own device alarms remain the primary protection. This page gives no advice on
an individual's treatment.

## Reading the signals

| Question | Metric (core `lib/metrics/index.js`, `NS_METRICS=true`) |
|---|---|
| How long from an accepted write to a durable evaluator completion? | `nightscout_evaluator_completion_lag_seconds` (histogram, per slice) |
| Is work waiting? | `nightscout_evaluator_pending_oldest_age_seconds`, `nightscout_evaluator_pending_tenants`, `nightscout_evaluator_queued_cycles` |
| Is the evaluator warm? | `nightscout_evaluator_resident_tenants` against `nightscout_evaluator_tenants` (warm when resident reaches the owned count, or `NS_EVALUATOR_RESIDENT_MAX` when that bounds it) |
| Is realtime keeping up? | `nightscout_realtime_frame_lag_seconds`, `nightscout_realtime_pending_oldest_age_seconds` |
| Is the api refusing? | `nightscout_storage_refusals_total` by `code` (`STORAGE_BUSY`, `STORAGE_TIMEOUT`, `STORAGE_UNAVAILABLE`) |
| Is a process saturated? | `nodejs_eventloop_utilization_histogram` |
| Are process clocks trustworthy? | `nightscout_db_clock_offset_seconds`, `nightscout_stage_lag_negative_total` |

Health endpoints on each role's private listener: `/healthz/live`, `/healthz/ready`, plus
`/healthz/datastore`, `/healthz/schema` and `/healthz/isolation`. A role is ready when its own
dependencies are up and tenants warm afterwards ([readiness-serve-then-warm](multitenancy-decisions.md#readiness-serve-then-warm),
narrowed for the api by [api-tenant-cache-bounded-lru](multitenancy-decisions.md#api-tenant-cache-bounded-lru)).
"Ready" therefore does not mean "every tenant is warm".

## Planned restart and K change

Governing decision: [evaluator-k-planned-restart](multitenancy-decisions.md#evaluator-k-planned-restart).
K (evaluator and realtime slice count) changes only by a planned restart of the role, with headroom
chosen so that this is rare. There is no live K change and no slice hash change.

1. Choose a quiet period. Tell affected people that alarms may be late for about the duration below.
2. Check the starting state: `NightscoutEvaluatorPendingOldest` is not firing, pending tenants are at baseline.
3. Restart or resize the role as a whole (all ordinals together for a K change, because ownership is a
   modulo of K; a mixed K would give two owners or none). A rolling restart one ordinal at a time is
   enough for a restart without a K change.
4. Wait for `/healthz/ready`, then for the warm-up in [Warm-up after restart](#warm-up-after-restart).
5. Confirm `nightscout_evaluator_resident_tenants` has reached its target on every ordinal and the
   completion-lag p95 is back under 30 s.

**Measured** (K=2 evaluator, 1,000 tenants under load, execution log 2026-11-22): both pods deleted at
once were Ready 9.2 s later, nothing completed over 120 s, the largest window lag was 80 s, and the
backlog returned to baseline about 228 s after the delete; about 1.3% of completions were lost against
an unrestarted control. That is one run at 1,000 tenants. At 10,000 tenants expect a longer tail
([warm-up plan](#warm-up-plan)).

## Node loss

Read-derived. A node hosting an api or realtime pod: Kubernetes reschedules; the api's cache is a
bounded optimization, so a replacement serves cold tenants inline. An evaluator ordinal (StatefulSet pod)
returns with the same ordinal and so the same tenants; its tenants have no evaluator until it is Ready
and then warm lazily. The alert is `NightscoutRoleDown`.

1. Identify the lost role from the alert (`workload`, `pod`). Check whether the node also hosted PostgreSQL;
   if so, go to [PostgreSQL restart and failover](#postgresql-restart-and-failover) first.
2. Do not delete the evaluator's PersistentVolume or force-delete the pod to "speed it up" unless the node
   is confirmed gone; two pods claiming one ordinal would give two evaluators for the same tenants.
3. Wait for Ready, then follow the warm-up steps. If the node will not return, cordon it, and let the
   StatefulSet reschedule.
4. Record the incident window: `increase(nightscout_evaluator_completion_unobserved_total[...])` should
   be 0 afterwards. A non-zero value means a completion's commit was uncertain and needs a look at that
   slice before it is called recovered.

Node loss of a role is a restart of that role from a clinical point of view; it has no recovery-time bound
today ([production-critical-path](production-critical-path.md), failure and recovery section).

## PostgreSQL restart and failover

[One large PostgreSQL primary on its own node](multitenancy-decisions.md#one-large-postgresql-primary) is the current shape; there is no
automatic failover in the supported shape. Alerts: `PostgresDown`, `PostgresExporterDown`,
`NightscoutStorageUnavailable`, `PostgresRestarted`.

**Planned restart (configuration change, minor upgrade).**
1. Confirm a recent backup exists and was test-restored (see [Restore](#restore)).
2. Restart PostgreSQL. Roles keep running; the api answers `STORAGE_UNAVAILABLE` / `STORAGE_TIMEOUT`
   (503) and writers retry. Evaluators lose their database connections and recover through their pools.
3. When `pg_up` returns, watch the refusal rate fall to zero, then the pending age. Expect the warm-up
   pattern in the next section even though no application pod restarted, because caches reload from a
   cold PostgreSQL buffer cache.

**Unplanned loss or failover to a restored copy.**
1. Treat any writes after the last backup or replicated position as possibly lost. Say so to the
   affected people: readings uploaded in that window may need to be uploaded again by the source app.
2. Bring PostgreSQL up from the backup ([Restore](#restore)) or promote a replica, then point the
   roles at it by the platform's usual mechanism.
3. Roles on a restored database follow the restore fencing rules: the restart census and incarnation
   pins in [deployment-and-rig-testing](deployment-and-rig-testing.md#restore-and-failure-scenarios) apply;
   do not substitute replacement processes for an unresolved operation.

Whether replication lag is bounded is not measured here; `PostgresReplicationLagHigh` exists in the
rules but no replica topology is part of the supported shape yet.

## Restore

Two different operations share the word. **Tenant-local restore** (one tenant's history, through the
lifecycle controller, with other tenants continuing) is specified by
[restore-history-forward-correction](multitenancy-decisions.md#restore-history-forward-correction) and rehearsed
in [deployment-and-rig-testing](deployment-and-rig-testing.md#restore-and-failure-scenarios); do not do it by hand in
SQL. **Whole-database restore** (the primary is lost or corrupt) is below.

Whole-installation rollback requires a PostgreSQL backup and the matching Vault state. The
read-derived procedure below follows the [platform backup decision](multitenancy-decisions.md#platform-backup-and-test-fixtures).

1. Close admission and stop all writers, including connectors and admin jobs, before restoring either store. Keep serving roles offline. Tell people alarms are unavailable during recovery.
2. Restore either a physical base backup (`pg_basebackup`, plus WAL if point-in-time recovery is
   wanted) or a logical dump (`pg_restore -j`). A physical backup restores identical bytes, including
   the tenant write clock rows; prefer it for the primary. A logical dump is for moves between
   versions, and requires running `ANALYZE` afterwards.
3. Restore the matching Vault state and verify access to tenant key material. Run the schema check (`/healthz/schema` on a role, or `node bin/nightscout.js migrate check`) before
   starting roles.
4. Start api, then realtime, then evaluators. Each ordinal reloads its tenants lazily.
5. Check isolation, the tenant census and client readback across the rollback point. History-forward correction applies to same-ID logical tenant restore. Physical rollback has no demonstrated guarantee for clients whose saved cursors are ahead of the backup.
6. Follow [Warm-up after restart](#warm-up-after-restart) and close the incident when completion-lag p95 is
   below 30 s for ten minutes.

Vault and platform secrets are backed up separately; a database restore without its key material cannot
serve tenants whose secrets are encrypted ([upgrade precondition](#migration-rule-transition) also requires a
Vault backup).

### Drill, 2026-11-23 (measured, local, synthetic)

PostgreSQL 16.15 in Docker (`lane6-pg`, host port 54160), NVMe workstation disk, nothing else measured
at the same time. **Not the Nightscout schema**: a synthetic table pair (`entries`, `treatments`) keyed by a
tenant id, 1,000 synthetic tenants, 2,000 entries and 200 treatments each (2,000,000 + 200,000 rows,
502 MB database). "Serving" means one range-scan read of each tenant's newest 288 entries returned 288 rows
for all 1,000 tenants; it does not start the application roles, so it excludes role start and warm-up.
Script and output are local: `/mnt/data/nightscout-workspace/artifacts/ops-readiness-20261123/drill/`.

| Step | Logical (`pg_dump -Fd -j4` / `pg_restore -j4`) | Physical (`pg_basebackup -X stream` / start on copy) |
|---|---|---|
| Backup | 1.8 s, 10.6 MB (synthetic filler compresses far better than clinical data) | 1.9 s, 540 MB |
| Restore | 4.6 s, plus `ANALYZE` 0.3 s, plus an empty server start of about 2.3 s | server ready 1.3 s after start (includes a 1 s fixed sleep in the script) |
| All 1,000 tenants answer a read | 0.2 s for the first full pass | 0.2 s for the first full pass |
| Content check | md5 of all entries equal to the source | md5 of all entries equal to the source |

Limits: one run each; sizes are about three orders of magnitude below a 10,000-tenant realistic-history
database; the disk was warm; the readiness poll can answer during the container's first-start
initialisation, so the logical start time is indicative only. These figures show the
procedure works end to end and that the database part is small at this size. They say nothing about
restore time at production size, which should be re-measured on the real node class with a realistic
database before an operator relies on a recovery-time figure.

## Warm-up after restart

After any restart of PostgreSQL or an evaluator, evaluators reload tenants lazily, tenants with a due
alarm first ([evaluator-k-planned-restart](multitenancy-decisions.md#evaluator-k-planned-restart)). Until
the cache is warm, completions take longer.

1. Watch `nightscout_evaluator_resident_tenants` per slice rise toward the owned count.
2. Watch `nightscout_evaluator_pending_oldest_age_seconds`; it peaks after the restart and falls.
   Alerts for the critical (120 s) level will fire during a large restart: that is the warm-up, not a
   second fault, so note the incident as a restart in the log rather than acting on each alert.
3. If the pending age keeps rising after resident tenants stop rising, it is not warm-up: go to the
   evaluator-lag alerts and check event-loop utilisation and storage refusals.
4. Do not restart a slice again to "clear" a warm-up; each restart repeats the cold start.

### Evaluator lag

When completion lag or the pending age is high with warm-up complete: check `nodejs_eventloop_utilization`
(above 0.9 means the evaluator is CPU-bound and K or the per-slice density is wrong; K changes by
planned restart only), then `nightscout_storage_refusals_total` and PostgreSQL connection use, since at
10,000 tenants PostgreSQL and the api pool limited throughput, not the evaluator
([execution log](execution-log.md), 10k K=20 row).

### Realtime lag

Frame lag high with evaluator lag normal: check the realtime pending age and event-loop utilisation of
the realtime pods; K for realtime follows evaluator K.

### Storage refusals

`STORAGE_BUSY` (checkout: no pooled client): the pool is exhausted; do not add api replicas without
first checking PostgreSQL connection headroom (`PostgresConnectionsNearLimit`). `STORAGE_TIMEOUT`
(statement or clock row lock): look for a long transaction. `STORAGE_UNAVAILABLE`: the database is
suspended or unreachable; go to [PostgreSQL restart and failover](#postgresql-restart-and-failover).

## Warm-up plan

Basis (**measured**, 10k K=20 run, execution log 2026-11-22): durable completions over 120 s were 6.2%
of the run, and 97% of those fell in the first 10 minutes after the restore. The run's case verdict was
UNMEASURED by a harness limit, and the 10,000-tenant figure comes from a reconstructed window, so treat the
97% as indicative. Everything below is **read-derived** option analysis; none of it is implemented or
measured, and a recommendation is for the maintainer to take.

Principle: warm-up cost is lazy cold-load work competing with live writes on one database. Scoring should
keep it apart from steady state (an open item in the execution log), and the operator-facing promise is
"alarms may be late for the first minutes after a restart", not a bound.

| Option | Idea | Expected effect | Cost and risk |
|---|---|---|---|
| A. Do nothing, report it | Keep lazy loading; score and alert warm-up separately | Known, bounded in practice to the first minutes at 10k | Late alarms after every restart are an operating fact |
| B. Priority warm | Warm tenants with a due alarm and recent writers first, then the rest | Concentrates the cold loads on those most likely to need an evaluation, shrinking the tail that exceeds 120 s | The decision already says due-alarm tenants go first; extending the priority to recently-written tenants is a core change in the evaluator's load order; verify it does not starve quiet tenants |
| C. Pre-warm before traffic | A restarted evaluator reads its owned tenants before reporting ready, or holds the pod out of the Service until resident count reaches a threshold | No live writes compete with the cold loads | Conflicts with [readiness-serve-then-warm](multitenancy-decisions.md#readiness-serve-then-warm); an operator flag for all-tenants readiness already exists for cautious operators; at 10,000 tenants the derived readiness wait is long (the decision derives about 57 min if readiness waits for every tenant, an older measurement) |
| D. Staggered restarts | Restart evaluator ordinals one at a time with a wait for a resident-count threshold between them | A restart of K ordinals does not cold-start every tenant at once | Longer maintenance window; does not apply to a K change, which restarts all, or to a PostgreSQL restart |
| E. Warm the database cache | After a PostgreSQL restart run `pg_prewarm` on the hot tables and indexes | Removes the cold buffer cache part of the first cycles | Only helps the PostgreSQL restart case; needs the extension and a privileged role |

Suggested order to try (maintainer to decide): measure A properly first (warm-up scored apart from steady
state in the next ladder), then B, which stays inside the lazy model, then D and E as operator
procedures that need no core change. C is only for operators who choose all-tenants readiness.

Success measure for any option: over-120 s completions in the 10 minutes after a restart, and time for
`nightscout_evaluator_resident_tenants` to reach its target, at the same tenant count and load as the
baseline run.

## Migration-rule transition

Today ([prerelease-schema-in-place](multitenancy-decisions.md#prerelease-schema-in-place)) the multitenant
schema and its migrations may change in place because no operator database exists. From the first release
that ships a multitenant role to operators, [multitenant-upgrade-shape](multitenancy-decisions.md#multitenant-upgrade-shape)
applies: two-step migrations (add first; remove only after no old version runs), a one-shot migration
job, and pre- and post-checks. Read-derived state of the source at core `2dee799c8`: a migration runner
(`node bin/nightscout.js migrate status|up|check`, `lib/migrations/`), an upgrade precheck/postcheck
module (`lib/tenant-operations/upgrade.js`), and a documented "no shipped migration catalogue, no
startup integration" status in `lib/migrations/README.md`. See also [sql-and-migration-architecture](sql-and-migration-architecture.md).

Plan:

1. **Baseline cut (before the release).** Freeze the in-place-edited schema as migration 0001 of a
   reviewed catalogue, the only time in-place edits are folded together. Record its checksum. Anything
   edited in place after this point is a defect.
2. **Gate.** Add a check (queue gate that can fail, with a negative control) that the catalogue is
   append-only: no existing migration's checksum changes between releases, and a destructive step
   (drop, rename, type change, narrowing constraint) is refused unless marked as a *remove* step.
3. **Compatibility pair.** For each release, run the previous release's api, realtime and evaluator
   against the new schema before the remove step. This is the existing "old and new code share one schema"
   requirement; the rolling-update behaviour needs one rehearsal: new schema, old pods Ready, new pods
   rolled, then the remove step in the release after.
4. **Operator procedure.** Pre-check: backup exists and was test-restored (this page's [Restore](#restore)),
   no tenant closed or mid-restore, `migrate check` against the old schema. Run the one-shot job; run
   `migrate check` for the new catalogue; roll roles; run post-checks (tenant census, per-tenant health).
5. **Interrupted migration and rollback.** Rehearse an interrupted `up` (the runner commits each migration
   and its ledger row in one transaction, so a kill leaves a whole prefix) and a rollback to the previous
   release before the remove step ([multitenant-upgrade-shape](multitenancy-decisions.md#multitenant-upgrade-shape)).
6. **Fixtures.** Prefer an exact fixture key. For a writer-driven Kubernetes fixture from an ancestor core commit, match the tenant count, seed, full history specification, PostgreSQL image and transport. Verify the bootstrap migration receipt for the source and target before starting roles. [Fixture reuse decision](multitenancy-decisions.md#one-call-usable-provisioning)
7. **Record.** On the first operator release, mark prerelease-schema-in-place superseded in the same edit
   that records the baseline cut ([decisions in force](decisions-in-force.md) conventions).

Open: who decides the baseline-cut commit, and whether the single-tenant MongoDB catalogue follows the
same append-only gate (the decision is multitenant PostgreSQL only).
