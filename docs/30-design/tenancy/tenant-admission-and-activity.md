# Tenant admission, activity and recovery

*Contributor-facing decision-preparation guide, 2026-11-08. **Activity policy proposed;
not adopted or implemented.** The REST component direction below is recorded
separately in the [release decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#rest-api-component-and-replica-placement-2026-11-08). The maintainer raised whether operator-controlled tenant inactivity should
prevent unnecessary background work and asks how business APIs,
connector workers, evaluator and restoration fit together. This guide separates
that proposal from the existing maintenance protocol. Mechanism assessment is
**read-derived** from application
`ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364`; later acceptance stays attributed to
its actual heads in the [operation-window acceptance family](../../../reports/tenancy/operation-window-acceptance-2026-11-07/README.md).
No new runtime, policy transition, deployment layout or production admission was
measured. Existing [tenancy decisions](multitenancy-decisions.md#suspension-and-lifecycle)
and [owner authority](owner-authority.md) retain their adopted meaning.*

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

## Maintenance safety is not a complete inactivity policy

Several existing mechanisms use an active/disabled concept, but their meanings
and consumers differ. Do not collapse them into one status flag.

| Existing mechanism | What source establishes | What it does not establish |
|---|---|---|
| Maintenance phase | The exact lifecycle schema admits `active` and `suspended`, with claim/digest consistency constraints: [operation-window-readiness.js:24](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/tenant-lifecycle/operation-window-readiness.js#L24). Restore owns the claim-bound transition and later clears its own maintenance claim. | A general operator activity enum, read-only mode, connector scheduling policy, account disablement or deletion policy. Reusing its columns would mix safety recovery with business intent. |
| Current access authority | The signed-token adapter reads tenant, credential, session and key activity and current grants: [access-postgres.js:39](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/tenant-authorization/access-postgres.js#L39), [:71](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/tenant-authorization/access-postgres.js#L71). | Proof that every legacy/anonymous/owner route and background worker consumes one tenant-wide activity/resource policy. A token-authority bit alone is not a complete workload-admission contract. |
| Evaluator current-config refusal | A missing current configuration discards its local component and output: [evaluator-runtime.js:43](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/serve/evaluator-runtime.js#L43). Maintenance-window refusal also discards state. | Proof of no scheduled work for an inactive tenant. The runtime retains configured tenant states, iterates all configured tenants at [line 101](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/serve/evaluator-runtime.js#L101), and installs acquisition/time timers at [line 152](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/serve/evaluator-runtime.js#L152). Refusing the attempted cycle is not the same as removing it from eligible background work. |
| Restore preserves live authority | Same-ID clinical restoration retains current authority, credentials, secrets, checkpoints and live clock: [logical-restore.js:3](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/tenant-lifecycle/logical-restore.js#L3). | A new general operator activity policy, or proof that future policy is preserved until it has its own persistence, transition and consumer contract. |

Thus recovery provides important exclusion, drain, invalidation and uncertainty
mechanisms to reuse. It does not already close the requirement that an inactive
tenant should not consume unnecessary background resources. In particular,
configured presence is not workload eligibility. A configured tenant may need to
remain discoverable to operators and recovery while it is ineligible for clinical
evaluation or connector polling.

## Proposed orthogonal admission model

Keep separately owned facts, with separately reported reasons:

| Fact | Owner and intended use | Boundary |
|---|---|---|
| Desired operator activity policy | Explicitly authorized operator action records which tenant activities are intended to run. Exact states, fields and transition API remain undecided. | Neither a successful restore nor a process restart writes an administrative enablement on the operator's behalf. |
| Maintenance/recovery state | The existing operation-window/controller owns exclusion, claims, uncertainty and safe maintenance completion. | Finishing restore clears only that maintenance restriction; it must not undo administrative inactivity. Unknown maintenance outcome cannot be treated as success. |
| Current authority | Existing tenant/client/session/key/grants and owner/operator policy determine whether the actor may perform the requested operation. | Administrative enablement does not grant a principal new permissions, revive a revoked key/session or override RLS. Clinical restoration does not rewind current authority. |
| Worker assignment | Platform assignment/config identifies which worker may own the tenant's eligible task; the current evaluator remains singleton. | Being assigned or configured does not make an inactive tenant eligible. Future partitions consume disjoint assignments; this proposal adds no scheduler or replicated same-work execution. |
| Observed health/readiness | Runtime reports dependencies, last successful acquisition, freshness and refusal/recovery reasons. | A green process probe cannot override desired inactivity or recovery refusal; an outage must not be presented as an intentional operator choice. |

For a normal operation, the proposed effective admission is the intersection of
**operator policy for that operation, maintenance safety and current authority**.
A background task additionally requires its valid assignment. Observed dependency
health may refuse work; it never expands permission. This is a responsibility
model, not an adopted persistence schema or a new universal status enum.

The existing [pause/suspend decision](multitenancy-decisions.md#suspension-and-lifecycle)
already distinguishes **pause** (UI/reads blocked, ingestion continues) from
**suspend** (total blackout including ingestion). Delete requires suspend.
Preserve those meanings and their socket/staleness obligations. Do not silently
rename an inactive resource policy to either term, or assume pause already means
"stop evaluators and connectors." Its exact background consequences need a
bounded decision consistent with those adopted semantics.

An inactivity transition should make prohibited work ineligible before expensive
clinical acquisition, provider polling or notification production. It should
drain or invalidate already-running work under an explicit race contract and
release retained tenant-specific resources when safe. A small amount of shared
control-plane/eligibility/recovery observation may remain necessary; "no
unnecessary background resources" is not a measured promise of zero shared
process or database overhead. Operators must still be able to inspect and recover
the tenant through separately authenticated controls.

## Policy choices still to settle

These are decision-preparation topics, not questions silently answered by the
implementation. Take one policy topic at a time with its source mechanism,
operator-visible behavior and actual acceptance evidence.

| Topic | Trade-off and user/operator effect | Current status |
|---|---|---|
| Meaning and names of desired activity states | A single enable/disable action is simple; operation-specific eligibility can preserve ingestion while stopping views or selected workers. A broad disable can interrupt device upload or hide fresh data. | **UNDECIDED:** exact names, allowed combinations, defaults and relationship to adopted pause/suspend. |
| Reads and ingestion while inactive | A read-only/stale display can aid inspection; complete refusal is simpler to reason about. Continuing canonical ingestion preserves device continuity but consumes resources. | **UNDECIDED:** operation matrix across browser, legacy/API3, sockets and direct device/headless credentials. Retain adopted pause/suspend semantics. |
| Evaluation, notifications and connectors | Stopping expensive work saves resources; stopping evaluation/delivery also removes freshness/notification production. Continuing ingest need not imply continuing external connector polling. | **UNDECIDED:** eligible tasks, retained output handling, pending notification/connector jobs, cancellation and reactivation catch-up. No live provider/device claim. |
| Transition authority and observability | Operator-only policy protects shared resource control; owner requests may support self-service within operator ceilings. Visible desired/effective/recovery reasons prevent a failed tenant being mistaken for intentionally inactive. | **UNDECIDED:** privilege/audience/UI/API/audit contract. Existing owner DATA and private operator boundaries remain. |
| Recovery and reactivation | Recovery may repair clinical state without changing desired activity. Explicit reactivation can reacquire current data/config and safely re-enable selected workers; blind restart risks reviving stale work. | **PROPOSED INVARIANT:** restore/restart must preserve administrative inactivity. Exact transition, reacquisition and race protocol still need implementation/acceptance. |
| Compatibility and placement | New multitenant policy can be explicit and additive. Applying it to the single-site server changes default behavior and alarm/connector lifetime. Moving a REST listener does not settle either policy. | **UNDECIDED:** single-tenant applicability and opt-in/release placement. Preserve current single/Mongo resident behavior and existing credentials until explicitly selected and verified. No process-layout change adopted. |

## Focused future acceptance

Every experiment below is **PLANNED / UNMEASURED**. It should join the applicable
owner/lifecycle/runtime capability with its fixtures and meaningful controls;
this document creates no native reservation or independent comprehensive campaign.
Use synthetic tenants A and B, actual serving/worker consumers and independent
stored-state/work/resource oracles. Source doubles and native runs retain their
actual scope.

| Criterion | Positive experiment and independent oracle | Planned semantic negative control |
|---|---|---|
| Administrative inactivity survives restore | Disable A through the future authorized activity transition while a restore is in progress. Complete permitted maintenance or retain refusal under the settled transition protocol. Desired policy stays disabled; prohibited requests/work remain blocked after maintenance activation. B continues actual operations. | Make restore activation overwrite desired policy: the post-restore policy/operation oracle detects unintended enablement. Confirm that exact control, then restore and rerun. |
| Restart and replacement preserve intent | Start fresh API/realtime/evaluator processes with A inactive and B eligible. A's desired state persists; B becomes ready; no component derives administrative enablement from boot or cleared maintenance. | Treat lifecycle `active`, process restart or absent local cache as desired enablement: A executes prohibited work and the effect/work counter assertion fails. |
| Eligibility differs from configuration | Keep A in configuration and recovery inventory but make its clinical evaluation/connector workload ineligible. Exercise actual timer/poll/notification triggers; observe no prohibited acquisition/provider work, bounded retained resources and continued B work. Measure any required eligibility-check overhead separately. | Schedule from configured tenant presence alone: the independent workload/egress oracle detects A's unnecessary work even if the request eventually refuses. |
| In-flight transition and invalidation | Hold an actual A callback/HTTP response or evaluator/connector cycle open during disable. Apply the settled drain/cancel policy; late generations cannot publish output, acknowledgements or newly disallowed effects. Current local contexts are invalidated. | Complete at SQL commit/transport abort only, skip an invalidator or accept a late generation: the callback barrier or stored/output oracle detects premature completion/stale publication. |
| Current authority remains independent | Change desired activity without reviving revoked session/key/grants; restore an older clinical snapshot and confirm current authority and desired policy survive. Exercise supported legacy/anonymous/owner paths explicitly. | Permit an administrative enablement or old artifact to replace current authority: revoked access/effect assertion fails. A signed-token-only check cannot count as all-path coverage. |
| Policy is operation-specific and visible | Execute the adopted matrix for reads, ingest, evaluation, notifications and connectors across each supported desired policy. UI/health exposes intent separately from maintenance, dependency failure and data freshness. | Substitute a generic active flag or UI-only gate: an operation outside its policy runs, or an outage is reported as intentional inactivity. Exact path/reason assertions must detect it. |
| Safe reactivation | After an explicit authorized reactivation, reacquire current settings, authority and clinical inputs before eligible publication/work. Preserve uncertainty and do not resume suspended restore/orphan work automatically. | Reuse stale output/credentials or clear uncertainty to become ready: source-attributed refusal/freshness/effect oracle fails. |
| Isolation and shared failure behavior | A's transition/inactivity does not block B's HTTP, realtime and evaluator progress. Shared schema/privilege/datastore/trust failures still refuse where required rather than being treated as A-only inactivity. | Broadly defer a shared failure or globally stop healthy tenants: unsafe startup or lost B progress triggers its intended assertion. |

Before implementation, confirm the current head, queue openness, source owner and
adopted operation matrix; stop and report mismatches rather than choosing the
nearest behavior that passes. Record actual source/instrument/role/topology,
confirmed semantic reds, exact restoration and physical cleanup. Run focused
checks during development; one coherent joined candidate owns the required full,
default-browser, enabled-corpus and final prcheck campaign. Existing acceptance
and recorded-evidence gates do not measure this proposed activity policy.
