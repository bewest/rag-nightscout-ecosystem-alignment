# Tenant admission, activity and recovery

*Contributor-facing living guide, current with the release decisions of 2026-11-10.
**Activity policy adopted 2026-11-10:** pause and suspend are the operator
activity policy ([decision](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#activity-is-pause-suspend)), with the rows listed
under [adopted activity policy](#adopted-activity-policy). Implementation is
`MT-ACTIVITY-ELIGIBILITY` (fixed on its lane, not joined to #8898; the
[queue](../../../queue/work-queue.yaml) owns its state and the
[lane record](../../../reports/tenancy/activity-eligibility-2026-11-10/README.md)
its measurements). The REST component direction below is recorded in the
[release decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#rest-api-component-and-replica-placement-2026-11-08).
Mechanism assessment in the first three sections is **read-derived** from application
`ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364`; later acceptance stays attributed to
its actual heads in the [operation-window acceptance family](../../../reports/tenancy/operation-window-acceptance-2026-11-07/README.md).
The [tenancy decisions](multitenancy-decisions.md#suspension-and-lifecycle)
own the pause/suspend meanings and [owner authority](owner-authority.md) the
owner and root boundaries.*

## One logical API does not require one listener or process

**Architecture direction: REST APIs (v1/v2/v3) are one stateless request-serving
component.** Version-specific routers/adapters live inside that component; API
version numbers do not select separate processes, services or scaling groups.
Each replica serves the same configured, admitted route set. Compose service
instances and a Kubernetes Deployment are alternative placement/lifecycle
mechanisms for that component; neither is a new route-acceptance claim or a
requirement to demonstrate Kubernetes now.

“Stateless” means no replica owns authoritative tenant data or an exclusive
clinical evaluation workload. Durable authority, clinical state and operation
records remain in their backing stores. Each replica still owns connections,
in-flight responses, pools and reconstructible startup/cache state, so it must
participate in maintenance drain and invalidation. Do not require client affinity
or introduce per-version deployment boundaries as part of API scale-out.

The source already composes configured API3 and legacy routers in one API role:
[preview-api.js:110](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/serve/preview-api.js#L110),
[tenant-app/index.js:187](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/tenant-app/index.js#L187),
[:217](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/tenant-app/index.js#L217).
These read-derived mechanisms support the component boundary; the acceptance
family still owns exactly which routes/clients were exercised. Internal
v1/v2/v3 adapters retain their reply, authentication and compatibility rules.

The business REST surface groups data, authorization and owner-management
capabilities. Owner operations retain their separate audience/listener and
privileges, even when their module is colocated with request-serving API. A
logical component describes responsibility. A listener describes who can reach which interface and with which
audience. A process describes placement, resource custody and failure coupling.
Grouping REST business APIs does not merge their credentials, privileges or trust
boundaries, and it does not put every worker or maintenance engine inside HTTP
request handling.

The current CLI can compose selected roles in one process, with role-owned
contexts and separately resolved listeners:
[serve/index.js:42](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/serve/index.js#L42),
[:85](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/serve/index.js#L85).
That includes the available `api` and `tenant-admin` roles under their explicit
configurations; it does not authorize a public operator listener. The current
DATA API intentionally excludes owner/operator routes:
[preview-api.js:110](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/serve/preview-api.js#L110).
Whether the selected deployment combines those listeners or separates their
processes remains distinct from their logical grouping. This clarification adopts
no process-count, ingress or deployment-layout change.

| Responsibility | Current mechanism and placement boundary | What this means for the logical API |
|---|---|---|
| Data REST and credential authorization | `api` owns request-serving DATA behavior and canonical clinical writes. Current tenant/client authority and RLS still apply. | A business API responsibility; it may have explicitly declared replicas. It does not gain operator restoration credentials. |
| Owner REST | `tenant-admin` has its own configuration, listener and owner-management audience. [roles.js:88](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/serve/roles.js#L88) | Part of the logical business surface while preserving owner versus DATA authority. Logical grouping does not imply one permission set. |
| Restore orchestration | A private operator CLI/tool constructs the maintenance controller and invokes logical restoration: [deploy/multitenant/restore.js:97](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/deploy/multitenant/restore.js#L97). It is not an API replica's normal request handler. | The API participates in safe maintenance; it does not host the restore engine. A future control-plane request may initiate a separately authorized operator job, but that API/job contract is not selected here. |
| Evaluator | Headless runtime, with one active owner of the current tenant set; it computes clinical output and participates in durable notification/recovery contracts. [roles.js:59](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/serve/roles.js#L59) | A worker responsibility, not a REST route or API replica. Tenant eligibility and producer ownership remain separate checks. |
| Connector `vcpool` | Declared role metadata has no `start`/multitenant runtime: [roles.js:81](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/serve/roles.js#L81). CLI rejects unavailable roles: [serve/index.js:31](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/serve/index.js#L31). | Future connector workers perform external acquisition and send canonical writes through the admitted API/write boundary. The descriptor is not proof of an implemented worker or permission for a new direct-write path. Exact deployment and activity policy remain open. |
| Realtime | Owns connected sockets, projections and private API forwarding; it is a reader and forwards writes to `api`. [roles.js:68](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/serve/roles.js#L68) | Retained connection state makes it a different runtime responsibility from request-serving REST, even when composition shares a process. |

The [endpoint/API-scaling plan](selectable-endpoints-and-api-scaling-plan.md)
separates transport, service discovery, per-instance restore inventory and
producer ownership. It does not add evaluator replication or a custom scheduler.
Platform scheduling/inventory may supply placement and assignment; application
eligibility and actual operation lifetime still have to be enforced.

## Why every API instance is restore-aware

An API need not perform restoration to conflict with it. It can hold a request or
response open, prepare tenant-specific startup/floor state, read a frame, or
commit a write while another component replaces that tenant's clinical state.
Restoration must therefore exclude new conflicting operations, drain actual
in-flight work and invalidate each instance's retained state before reopening the
maintenance gate.

The [operation window:77](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/tenant-lifecycle/operation-window.js#L77)
checks the tenant's current lifecycle phase under its lease; a non-active phase
refuses. The [cohort contract:24](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/docs/tenant-operation-cohort.md#L24)
keeps an outer operation unfinished through callback, HTTP/private response or
socket acknowledgement completion, not merely SQL completion. The API's
[tenant invalidator:129](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/serve/preview-api.js#L129)
resets local startup/readiness floors; request frames are acquired fresh.

The controller pins every actual participant, suspends the maintenance window,
drains, restores, awaits actual invalidation and only then attempts maintenance
activation:
[maintenance-window.js:133](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/tenant-lifecycle/maintenance-window.js#L133),
[:177](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/tenant-lifecycle/maintenance-window.js#L177).
Missing/replaced peers or uncertain acknowledgement retain the affected tenant's
protected state. A load-balanced API service address does not establish that all
actual API instances drained or invalidated. None of this requires exposing a
restore endpoint on every API.

## Maintenance safety is not an activity policy

Several existing mechanisms use an active/disabled concept, but their meanings
and consumers differ. Do not collapse them into one status flag.

| Existing mechanism | What source establishes | What it does not establish |
|---|---|---|
| Maintenance phase | The exact lifecycle schema admits `active` and `suspended`, with claim/digest consistency constraints: [operation-window-readiness.js:24](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/tenant-lifecycle/operation-window-readiness.js#L24). Restore owns the claim-bound transition and later clears its own maintenance claim. | A general operator activity enum, read-only mode, connector scheduling policy, account disablement or deletion policy. Reusing its columns would mix safety recovery with business intent. |
| Current access authority | The signed-token adapter reads tenant, credential, session and key activity and current grants: [access-postgres.js:39](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/tenant-authorization/access-postgres.js#L39), [:71](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/tenant-authorization/access-postgres.js#L71). | Proof that every legacy/anonymous/owner route and background worker consumes one tenant-wide activity/resource policy. A token-authority bit alone is not a complete workload-admission contract. |
| Evaluator current-config refusal | A missing current configuration discards its local component and output: [evaluator-runtime.js:43](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/serve/evaluator-runtime.js#L43). Maintenance-window refusal also discards state. | Proof of no scheduled work for an inactive tenant. The runtime retains configured tenant states, iterates all configured tenants at [line 101](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/serve/evaluator-runtime.js#L101), and installs acquisition/time timers at [line 152](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/serve/evaluator-runtime.js#L152). Refusing the attempted cycle is not the same as removing it from eligible background work. `MT-ACTIVITY-ELIGIBILITY` replaces this with an eligible work list (lane record above). |
| Restore preserves live authority | Same-ID clinical restoration retains current authority, credentials, secrets, checkpoints and live clock: [logical-restore.js:3](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/tenant-lifecycle/logical-restore.js#L3). | A new general operator activity policy, or proof that future policy is preserved until it has its own persistence, transition and consumer contract. |

Recovery provides exclusion, drain, invalidation and uncertainty mechanisms to
reuse; it does not by itself stop a paused or suspended tenant consuming background
resources. Configured presence is not workload eligibility: a configured tenant
stays discoverable to operators and recovery while it is ineligible for clinical
evaluation or connector polling.

## Adopted activity policy

Pause and suspend are the operator activity policy; there is no third state and
no separate "inactive" flag. Each fact keeps its own owner and its own reported
reason:

| Fact | Owner and use | Boundary |
|---|---|---|
| Activity state (active, paused, suspended) | Durable per-tenant row, written by authorized owner (pause only) or operator action with audit. [Every tenant has one](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#activity-row-always-provisioned): a migration backfills existing tenants as active and provisioning writes the row in the same transaction. | Neither a successful restore nor a process restart changes it. An unreadable row stops the evaluator for that tenant only, with a per-tenant health code. |
| Maintenance/recovery state | The existing operation-window/controller owns exclusion, claims, uncertainty and safe maintenance completion. | Finishing restore clears only its own maintenance claim; it never clears pause or suspend. Unknown maintenance outcome is not success. |
| Current authority | Tenant/client/session/key/grants and owner/operator policy decide whether the actor may perform the operation. | Unpausing grants no permission, revives no revoked key or session and overrides no RLS. Clinical restoration does not rewind current authority. |
| Worker assignment | Configuration (and later [evaluator partitioning](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#evaluator-static-partition)) names which worker may own a tenant's task. | Assignment does not make a paused or suspended tenant eligible. |
| Observed health/readiness | Runtime reports dependencies, last acquisition, freshness and refusal reasons. | A green probe cannot override pause, suspend or recovery refusal; an outage is never reported as an intentional state. |

Effective admission for an operation is the intersection of **activity state,
maintenance safety and current authority**; a background task also needs its
assignment. Dependency health may refuse work and never expands permission.

| Decision (2026-11-10) | What it fixes |
|---|---|
| [Pause and suspend are the activity policy](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#activity-is-pause-suspend) | Workers build work lists from eligible tenants. Paused: uploads and connector polling continue, the evaluator stops, and on unpause it recomputes from current data before publishing. Suspended: nothing runs. Restore and restart preserve the state. |
| [Adopted semantics in full](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#activity-adopted-semantics-wiring) | Suspend refuses ingest and reads and disconnects sockets; pause blocks UI and reads while uploads continue. |
| [Owner may pause](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#owner-may-pause) | Owner-API pause/unpause with audit. Only the operator suspends and deletes (delete requires suspend). Single-site behaviour is unchanged. |
| [Deletion request pauses](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#deletion-request-auto-pauses) | Request pauses; cancel restores the earlier state; operator execution suspends. An owner may pause or unpause during a pending ceremony; ownership changes still refuse. |
| [Refusal status](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#suspended-refusal-423) | Suspended: every refused request, uploads included, returns 423 `TENANT_SUSPENDED`. Paused reads return 423 `TENANT_PAUSED`. Uploaders are not invited to retry. |
| [Activity row always provisioned](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#activity-row-always-provisioned) | A missing row is a provisioning defect, not an operating state. |

**What operators and owners notice.** No alarms are computed or delivered while a
site is paused, including the pause that starts with a deletion request. The pause
control and the deletion confirmation say so in plain language. Some uploaders
treat a 4xx as final and drop data sent during a suspension; that cost was
accepted with the 423 choice.

An activity transition makes prohibited work ineligible before clinical
acquisition, provider polling or notification production, drains or invalidates
running work under an explicit race contract, and releases retained
tenant-specific resources when safe. A small amount of shared eligibility and
recovery observation remains; "no unnecessary background work" is not a measured
promise of zero shared overhead. Operators keep separately authenticated
inspection and recovery controls. Connector workers do not yet exist as a
multitenant runtime (`roles.js:81`); they adopt the same eligibility when built.

## Focused future acceptance

The criteria below are the acceptance bar for the adopted policy. The
[activity-eligibility lane record](../../../reports/tenancy/activity-eligibility-2026-11-10/README.md)
holds what its two passes measured and with which controls; the queue item
`MT-ACTIVITY-ELIGIBILITY` lists what is still open (deploy wiring and grants,
full API/realtime role runs with activity selected, per-request read cost, and
isolation of one tenant's unreadable row). A criterion counts as met only on the
joined candidate that carries it. Use synthetic tenants A and B, actual
serving/worker consumers and independent stored-state/work/resource oracles.

| Criterion | Positive experiment and independent oracle | Planned semantic negative control |
|---|---|---|
| Pause/suspend survives restore | Pause or suspend A through the authorized activity transition while a restore is in progress. Complete permitted maintenance or retain refusal under the settled transition protocol. The state stays paused/suspended; prohibited requests/work remain blocked after maintenance activation. B continues actual operations. | Make restore activation overwrite the activity state: the post-restore state/operation oracle detects unintended reactivation. Confirm that exact control, then restore and rerun. |
| Restart and replacement preserve intent | Start fresh API/realtime/evaluator processes with A paused or suspended and B active. A's state persists; B becomes ready; no component derives reactivation from boot or cleared maintenance. | Treat lifecycle `active`, process restart or absent local cache as reactivation: A executes prohibited work and the effect/work counter assertion fails. |
| Eligibility differs from configuration | Keep A in configuration and recovery inventory but make its clinical evaluation/connector workload ineligible. Exercise actual timer/poll/notification triggers; observe no prohibited acquisition/provider work, bounded retained resources and continued B work. Measure any required eligibility-check overhead separately. | Schedule from configured tenant presence alone: the independent workload/egress oracle detects A's unnecessary work even if the request eventually refuses. |
| In-flight transition and invalidation | Hold an actual A callback/HTTP response or evaluator/connector cycle open during pause or suspend. Apply the drain/cancel contract; late generations cannot publish output, acknowledgements or newly disallowed effects. Current local contexts are invalidated. | Complete at SQL commit/transport abort only, skip an invalidator or accept a late generation: the callback barrier or stored/output oracle detects premature completion/stale publication. |
| Current authority remains independent | Change the activity state without reviving revoked session/key/grants; restore an older clinical snapshot and confirm current authority and the activity state survive. Exercise supported legacy/anonymous/owner paths explicitly. | Permit an unpause or old artifact to replace current authority: revoked access/effect assertion fails. A signed-token-only check cannot count as all-path coverage. |
| Policy is operation-specific and visible | Execute the adopted matrix for reads, ingest, evaluation, notifications and connectors in active, paused and suspended states, including the 423 codes. UI/health exposes the state separately from maintenance, dependency failure and data freshness. | Substitute a generic active flag or UI-only gate: an operation outside its policy runs, or an outage is reported as intentional inactivity. Exact path/reason assertions must detect it. |
| Safe reactivation | After an authorized unpause or unsuspend, reacquire current settings, authority and clinical inputs before eligible publication/work. Preserve uncertainty and do not resume suspended restore/orphan work automatically. | Reuse stale output/credentials or clear uncertainty to become ready: source-attributed refusal/freshness/effect oracle fails. |
| Isolation and shared failure behavior | A's pause/suspend, or an unreadable A activity row, does not block B's HTTP, realtime and evaluator progress. Shared schema/privilege/datastore/trust failures still refuse where required rather than being treated as an A-only state. | Broadly defer a shared failure or globally stop healthy tenants: unsafe startup or lost B progress triggers its intended assertion. |

Before implementation, confirm the current head and queue openness; stop and
report mismatches rather than choosing the nearest behavior that passes. Record
actual source/instrument/role/topology and confirmed semantic reds. Focused checks
run during development; the coherent joined candidate owns the full,
default-browser, enabled-corpus and final prcheck campaign.
