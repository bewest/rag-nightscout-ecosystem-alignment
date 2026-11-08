# Evaluator, realtime and API communication

*Contributor-facing living explanation, 2026-11-07. Mechanisms below are
**read-derived** from cgm-remote-monitor `151de0248a1e4301c85b5c638185eec3ca8c38e6`,
tree `3bb46431a19e604dc028768f0e72e6ad29616c26`. Source file/line anchors were
checked against that immutable tree. These are branch implementation mechanisms;
pinned source links identify the inspected revision, not a released feature.
Recorded reproductions retain their own source in the evidence section. The
later c23 native matrix measures bounded tenant-local restart behavior; it does
not relabel this inspected tree as the executed source.*

This guide explains which process owns each result and which messages cross a
boundary. Decisions remain in [tenancy decisions](multitenancy-decisions.md), the
[durable event contract](durable-event-delivery-contract-2026-11-06.md),
[owner authority](owner-authority.md) and the
[release decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md).
The [delivery dashboard](multitenant-delivery-dashboard.md) owns milestone status;
this guide does not promote M6.

## The two outputs have different owners

Realtime and evaluator each acquire clinical data from PostgreSQL. The evaluator
does not send its SQL projection to realtime. Realtime builds the browser's record
frames from its own bounded projection and checkpoint. Separately, evaluator
consumers can send a durable alarm/notification intent to realtime for browser
fanout. That handoff is not a glucose-data replication stream or proof of device
notification delivery.

| Component | Owns | Reads or sends |
|---|---|---|
| API process | Current client authority, REST and existing socket write handlers, canonical clinical mutation | Tenant-bound PostgreSQL writes; scoped secrets; private socket authorization/mutation receiver |
| Evaluator process | Clinical acquisition, plugin cycle and eligibility of its current in-memory output | Its own durable input checkpoint/projection; current configuration; independently scheduled durable notification producer/retries |
| Realtime process | Browser connections, socket namespace state, independent current-record projection | Its own SQL reads/checkpoint; current API authorization; private API mutation forwarding; private alarm receiver |
| Tenant-admin process | Current tenant management and owner authority | Separate listener and management credential audience; it does not execute clinical socket writes |
| Private restore controller | A's suspension, draining and exclusive maintenance claim, committed-data and activation outcome | Fixed participants' control endpoints and actual backend identities; per-tenant invalidation |

These are application modules wired by explicit preview role configuration.
Separate processes/containers can share a private directory containing Unix-domain
sockets (UDS): an endpoint is a transport address, not shared JavaScript memory.
The [adopted separate-process decision](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#restore-service-processes)
retains this deployment boundary. A local `EventEmitter` does not become a durable
cross-process event bus merely because the processes share a host.

## Clinical acquisition and browser records

The evaluator's acquisition first commits a bounded current-state projection and
input checkpoint, then computes the clinical/plugin cycle. Its checkpoint records
input acquisition, not completed evaluation or notification delivery. A later
failure can therefore leave committed input with no eligible evaluated output.
The runtime reports an output revision only from a successful cycle and requires
an admitted tenant operation for `last(tenant)` to expose it.
[Evaluator acquisition][evaluator-acquisition], [runtime output][evaluator-runtime]
and [durable snapshot/checkpoint][replay] implement these separate stages.

```mermaid
sequenceDiagram
    participant API as API process
    participant PG as PostgreSQL
    participant Eval as Evaluator process
    participant RT as Realtime process
    participant Browser as Browser
    API->>PG: Canonical tenant write + forward tenant clock
    PG-->>API: COMMIT acknowledged
    par Evaluator acquisition schedule
        Eval->>PG: Tenant-bound bounded current snapshot
        Eval->>PG: Persist evaluator input projection/checkpoint
        PG-->>Eval: Snapshot transaction COMMIT
        Eval->>Eval: Compute plugins; publish eligible output revision
    and Realtime recovery/refresh schedule
        RT->>PG: Tenant-bound bounded current snapshot
        RT->>PG: Persist realtime projection/checkpoint
        PG-->>RT: Snapshot transaction COMMIT
        RT->>RT: Build browser frame; recheck current configuration
        RT-->>Browser: dataUpdate, full replacement (delta:false)
    end
```

The namespaces for evaluator and realtime checkpoints must be distinct.
[Role composition][role-composition] enforces that ownership boundary.
[Realtime projection][realtime-projection] builds a full replacement frame,
including absence, so a hard-deleted record is not retained by a delta-only merge.
Its runtime rechecks the configuration identity before fanout and exposes no healthy
last value after refusal. [Realtime refresh][realtime-runtime] supplies these checks.

Public API3 `identifier` and the storage `_id` are different identities. A browser
SGV frame carries the stored record key in `_id` and its value in `mgdl`; an API3
POST acknowledgement names the public identifier. Bind them through the actual
stored record when comparing transports, rather than assuming the strings match.
The [shipping frame loader][frame-loader] preserves this distinction.

The current reference uses bounded snapshot reconciliation and polling schedules.
It does not implement the full replication-slot/reader-NOTIFY design as a transport
between these roles. The durable-event contract owns that longer-term direction;
R73's polling/snapshot acceptance does not imply a LISTEN latency guarantee.
Time-only evaluator ticks reuse retained successful input; they do not substitute
for fresh acquisition or establish recovery after missed writes.

## Notification intents, retries and alarm handoff

The evaluator's optional realtime consumer is separately scheduled from clinical
computation. It reads eligible current output and current configuration, reconciles
persisted producer state and suppression acknowledgements, and records durable
intents with stable origin/request identity. The producer must still be current
after pending reads. The coordinator then selects due requests for retry.
[Producer][producer] and [consumer coordinator][consumers] implement this path;
when no consumer is selected, it opens no extra consumer pool, timer or socket.

```mermaid
sequenceDiagram
    participant Eval as Evaluator runtime
    participant Consumer as Evaluator notification consumer
    participant PG as PostgreSQL outbox / suppression
    participant RT as Realtime private alarm receiver
    participant Browser as Authorized browser
    Eval-->>Consumer: Current eligible output + configuration identity
    Consumer->>PG: Reconcile producer state and enqueue stable intents
    PG-->>Consumer: Durable request state committed
    Consumer->>PG: Claim due attempt; commit dispatch token/deadline
    Consumer->>Consumer: Recheck current eligibility and suppression
    Consumer->>RT: POST JSON /alarm over private UDS
    RT->>RT: Current tenant/socket authority checks
    RT-->>Browser: Alarm / clear event for admitted tenant sockets
    RT-->>Consumer: accepted:true (handoff receipt, not device ACK)
    Consumer->>PG: Persist accepted or uncertain attempt outcome
    opt Lost response or restart
        Consumer->>PG: Read durable due/uncertain request
        Consumer->>RT: Retry same stable request identity
    end
```

The attempt and dispatch state commit before the adapter call; the network wait is
not held inside SQL. Deadline, abort or an ambiguous response preserves a durable
retryable outcome. Before dispatch, the notifier rechecks configuration eligibility
and the current suppression reader, so an old selected cycle is not standing
permission to deliver. [Notification attempts][notification-attempts] owns the
implementation. Clear requests have their own retirement/suppression handling;
this is not a blanket rule to discard every request when an output is unavailable.

The actual [alarm adapter][alarm-transport] sends tenant, request ID, attempt,
notification and receipts to `/alarm`. Acceptance means the realtime handoff
completed. It does not mean a browser displayed it, a person acknowledged it, or a
provider/device received it. A lost handoff response can repeat the unchanged
request: there is no exactly-once delivery promise.

A browser's `ack` follows the private API mutation route below. API checks current
credential/tenant permission and, for linked consumer state, current evaluator
configuration inside the acknowledgement admission. It persists original
suppression state; the evaluator subsequently reads that state.
[Private acknowledgement admission][private-api] is distinct from the transport
receipt acknowledging an evaluator-to-realtime handoff.

## Browser authorization and mutations

Socket.IO exposes `/`, `/storage` and `/alarm`. Tenant resolution uses the admitted
host/configuration mapping. The root namespace accepts the existing `authorize`
shape; `/storage` and `/alarm` use their own subscription/credential contracts.
Their credential forms and permissions are not interchangeable. The
[realtime protocol][realtime-protocol] rechecks current authority across asynchronous
acquisition and before fanout; a long-lived connection is not a permanent grant.

```mermaid
sequenceDiagram
    participant Browser as Browser / existing socket client
    participant RT as Realtime process
    participant API as API private UDS receiver
    participant PG as Tenant-bound PostgreSQL
    Browser->>RT: authorize / subscribe with client credential
    RT->>API: /authorize (host, tenant, namespace, credential)
    API->>PG: Current credential + tenant authority reads
    API-->>RT: Current permissions / selected collections
    RT-->>Browser: Namespace-specific acknowledgement and admitted data
    Browser->>RT: Existing mutation or ack event
    RT->>API: /mutate (host + original tenant/credential/event envelope)
    API->>API: Resolve tenant; authenticate transport AND client authority
    API->>PG: Existing socket write handler / suppression transaction
    PG-->>API: Canonical operation completes
    API-->>RT: Existing callback arguments
    RT-->>Browser: Unchanged callback acknowledgement
```

Realtime does not replace the user's credential with its database identity.
[Forwarding][forwarding] preserves the event namespace, arguments and callback
shape. Failure or ambiguity produces no synthetic success and no automatic socket
mutation retry. The [API executor][socket-executor] invokes the same socket write
handlers/purifier/write intents as the single-tenant socket listener. This is a
private HTTP/JSON call over UDS, not a replay of a public REST request. Public REST
requests use the real API handlers and shared storage/write-intent ports directly.

The private API independently resolves the host and compares the envelope's tenant,
authenticates the owned transport, verifies the current client credential and
checks the operation's permission. [Private API][private-api] and
[namespace credential normalization][socket-authority] define these boundaries.
A socket-path possession check is not permission to mutate a tenant's records.

## Wire format and operation lifetimes

The current [private transport][ipc] uses bounded JSON objects in HTTP POSTs over
fixed UDS endpoints, with explicit byte/time limits and restrictive same-UID
filesystem/socket ownership. It accepts a fixed operation list: `/authorize`,
`/mutate`, `/alarm`, `/cohort/status` and `/cohort/invalidate`. Application payloads
and cohort controls have different handlers; they are not a public administration
API. A private directory and fixed manifest are deployment trust inputs, not an
authentication substitute for each client's current authority.

A registered tenant operation surrounds actual HTTP response completion, not just
entry into a handler. [API lifetime middleware][api-lifetime] waits for response
finish/close; private IPC similarly retains its lifetime through response finish.
Socket authorization, forwarding, clinical/evaluator acquisition and notification
attempts also use the actual operation window. Tenant-scoped lower handles enforce
that window when used. These lifetimes let maintenance drain real unfinished work
rather than infer quiescence from a callback returning.

## Disconnect, restart and tenant-local restore

Ordinary process restart reacquires current records and persisted checkpoints.
An evaluator's in-memory output is recomputed; a committed input checkpoint is not
relabelled as a successful output. Realtime rebuilds its own projection and full
browser frame. Durable notification requests survive and retain their retry
identity. Current credentials/configuration are checked again; retained process
memory does not authorize a new connection.

The [logical restore policy](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#restore-history-forward-correction)
requires forward changes and deletion records for known captured/current clinical
identities, preserving public IDs and clinical fields. It retains current
nonclinical authority, consumer state and the authoritative live clock; physical
backup fidelity is a separate operation. Activity retains its existing full-read
behavior rather than acquiring a new v3 history contract. IDs purged from both
artifact and current retained history remain outside that bounded guarantee.
[Logical restore source][logical-restore] enforces captured/live floor checks.

The controller suspends A durably, drains A operations and holds an actual
backend-bound exclusive claim. After definite outer DATA commit, it runs registered
commit effects, invalidates the configured roles' tenant caches/sockets/output,
then activates A. A's sockets disconnect; fresh readers and evaluator acquisition
must obtain the restored current state. B has independent tenant operation keys
and counters. Lost COMMIT or invalidation acknowledgement does not authorize
blind replay, orphan clearance or expiry-based reopening.
[Controller contract][maintenance] and [participant protocol][cohort] supply this
ordering; participant incarnation changes invalidate an old pin.

### Independent startup on the inspected candidate

At `151de024`, shared schema/ACL checks remain unconditional. Genuine suspension
from the actual registered operation gate defers only that tenant's initialization;
a lookalike error code, metadata drift, bad binding, transport failure or other
application failure is not swallowed as suspension. The full configured tenant
roster remains present. A deferred tenant retries through the same gate when work
is admitted, with invalidation retiring its cached initialization.
[Tenant startup][tenant-startup] implements this provenance distinction;
[evaluator metadata admission][evaluator-readiness] runs READ ONLY, and
[consumer admission][consumers] retains unconditional metadata and actual
same-datastore checks before tenant-local initialization.

Consequently the source intends a restarted shared API/realtime/evaluator process
to serve active B while suspended A remains unavailable, with no stale A output.
[Realtime startup][realtime-runtime], [API startup][api-startup] and
[evaluator startup][evaluator-preview] use that mechanism. Aggregate health can
remain degraded while B is available: do not omit A from the roster or require A
to become active merely to make a process health summary green. The [c23 native matrix](../../../reports/tenancy/operation-window-acceptance-2026-11-07/c23-native-accepted/README.md)
reproduces this bounded restart criterion on its exact later source; the inspected
151de024 mechanisms above remain read-derived.

## What the evidence establishes

| Record | Actual accepted scope | Remaining boundary |
|---|---|---|
| [R73 durable runtime and bounded operations](../remedial/rc-16.0.0-integration-record.md#r73---durable-runtime-and-bounded-operations-batch-2026-11-07) | Reproduced functional M5 reference on its recorded source: durable bounded acquisition, current socket authority/compatibility, suppression and stable-request handoff; complete named broad acceptance on that tree | Current polling/snapshot reference does not establish provider/device delivery, capacity, multi-node ownership or all later source |
| [b029 native operation-window matrix](../../../reports/tenancy/operation-window-acceptance-2026-11-07/b029-native-accepted/README.md) | Reproduced all 17 criteria on `b029f5d8`: actual four CLI roles, forward logical history, B progress, rollback, changed-participant refusal, real COMMIT/invalidation acknowledgement loss and orphan refusal; independent physical closure | Not new-source restart-while-A-suspended acceptance, Compose/browser acceptance, released feature or whole M6 |
| [c23 native operation-window matrix](../../../reports/tenancy/operation-window-acceptance-2026-11-07/c23-native-accepted/README.md) | Reproduced actual fresh shared API/realtime/evaluator startup with B progress while A remained unavailable after the recorded failure cases; unsafe-clock API startup refused; independent physical closure | Fixed trusted cooperative participants, private serving credentials and database ingress. No raw-SQL fence, automatic orphan clearance, suspended-restore resume command or recovery-time guarantee |
| [ed2 cold Compose measurement](../../../reports/tenancy/operation-window-acceptance-2026-11-07/ed2-cold-accepted.json) | Reproduced actual UI, main/alarm sockets and ordinary A restore with B committing work; public identity, forward history and synthetic client convergence preserved; independent configuration/resource/process closure | Exact ed2 source and image, one-host synthetic scope. Actual pinned clients, final regression and wider M6 admission remain separate |
| [ed2 pinned-client measurement](../../../reports/tenancy/operation-window-acceptance-2026-11-07/ed2-clients-accepted.json) | Reproduced actual cgmsim/oref0 execution with matching stored outcomes and no unexplained or missing differences; independent baseline/resource/process closure within the original deadline | Synthetic pinned-client scope; connector polling, Android/device, provider delivery and wider milestone admission remain separate |
| Startup mechanism inspected here, `151de024` | Read-derived per-tenant deferred initialization and source-protocol controls owned by its implementation lane | Runtime measurements retain the c23 source attribution above; [current acceptance family](../../../reports/tenancy/operation-window-acceptance-2026-11-07/README.md) owns the separate cold Compose/client/full/corpus verdicts |

Application modules above are real code selected by explicit role configuration.
Recording connections, monkey-patched observers, COMMIT-loss proxies, privileged
same-PID/different-birth seeds and synthetic fixtures belong to the evidence
harnesses. They are not deployed communication services or credential providers.
The b029 record distinguishes real backend death from its separate privileged
counterfactual. Reproduced handoff or browser protocol equivalence does not imply
an Android binary, rig, external provider or device-delivery test ran.

## Pinned source map

All links below name `151de0248a1e4301c85b5c638185eec3ca8c38e6`; line anchors were
verified from that tree. Application API/format policy remains in the contracts
linked above rather than in this explanatory map.

[evaluator-acquisition]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/data/tenant-projection-evaluator.js#L49-L101
[evaluator-runtime]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/server/serve/evaluator-runtime.js#L125-L154
[replay]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/storage/postgres-durable-replay.js#L79-L144
[role-composition]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/server/serve/index.js#L42-L46
[realtime-projection]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/server/realtime/projection.js#L8-L32
[realtime-runtime]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/server/realtime/runtime.js#L11-L58
[producer]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/tenant-notifications/producer.js#L13-L51
[consumers]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/server/serve/evaluator-consumers.js#L109-L162
[notification-attempts]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/tenant-notifications/component.js#L28-L105
[alarm-transport]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/server/realtime/alarm-transport.js#L5-L20
[private-api]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/server/realtime/private-api.js#L35-L86
[realtime-protocol]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/server/realtime/protocol.js#L78-L162
[forwarding]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/server/tenant-socket-forwarding.js#L28-L51
[socket-executor]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/server/tenant-socket-write-executor.js#L12-L29
[socket-authority]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/server/realtime/authority.js#L7-L18
[ipc]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/server/realtime/ipc.js#L14-L49
[api-lifetime]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/server/tenant-app/index.js#L139-L162
[logical-restore]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/tenant-lifecycle/logical-restore.js#L58-L185
[maintenance]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/tenant-lifecycle/maintenance-window.md#L35-L70
[cohort]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/server/serve/operation-cohort.js#L129-L206
[tenant-startup]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/server/serve/tenant-startup.js#L5-L42
[evaluator-readiness]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/server/serve/evaluator-readiness.js#L80-L100
[api-startup]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/server/serve/preview-api.js#L92-L106
[evaluator-preview]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/server/serve/evaluator-preview.js#L25-L57

[frame-loader]: https://github.com/nightscout/cgm-remote-monitor/blob/151de0248a1e4301c85b5c638185eec3ca8c38e6/lib/data/dataloader.js#L244-L255
