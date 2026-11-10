# Realtime sharding, composition and recovery

*Contributor-facing living proposal, 2026-11-10. **Read-derived** from joined
application `dc795bd1515f11808a8d0732f2be9925cb2ffcd1`; no sharding implementation,
capacity or failover acceptance is claimed. Queue home: `MT-REALTIME-SHARDING`.
The [runtime topology](runtime-topology.md) owns current composition; this page
owns the proposed realtime scaling/recovery contract. Existing captured
[joined acceptance](../../../reports/tenancy/m6a-join-2026-11-09/dc795bd1-acceptance/)
retains its original single-realtime scope.*

## Recommendation and boundary

Start with **tenant-sharded realtime**: every tenant has one admitted realtime
owner for connections, projection refresh and notification handoff. A stable
logical shard contains tenants; worker placement is a separate versioned mapping.
The evaluator's assignment is independent. Do not equate adding Socket.IO
processes behind a load balancer with complete notification delivery.

| Review dimension | Proposed direction |
|---|---|
| Long-term direction | Stable logical shards with controlled ownership changes; retain a separately scoped connection-fanout option for tenants larger than one worker. |
| Architecture | Separate evaluation and realtime responsibilities; allow co-location. Edge routes consumer connections; a direct application adapter routes alarm handoff using the same admitted placement generation. |
| Backward/forward compatibility | Preserve polling/WebSocket clients, namespaces, credential/write/ACK behavior and full current-state recovery. Specify coordinated changes to internal contracts; no silent new frame/epoch requirement on old clients. |
| Maintenance | One placement contract, explicit owner/incarnation and route generation, existing platform/config inputs and per-instance maintenance census. No new discovery/consensus product or mandatory gateway. |
| Reliability | Warm before owner admission, drain/terminate or effectively fence the old owner before replacement, and refuse unknown ownership rather than claiming transparent failover. Separate current-state recovery from alarm replay. |
| Performance | Bound assigned tenant refresh work, viewer count, frames/bytes and authority fanout. Measure hot-tenant and reconnect load; CPU/memory capacity is not established by this plan. |

This is a proposal to evaluate, not an adopted shard count, hash algorithm,
automatic failover policy, schema or new product dependency.

## Evaluator and realtime: logical components versus deployment

Evaluator schedules acquisition/time-based computation and owns evaluated output
and notification intent. Realtime owns consumer protocol, subscriptions, current
state frames and per-recipient delivery. Computation should continue without
viewers; a connection flood should not consume the clinical scheduler's budget.
Those are useful logical boundaries, not proof that every role needs a separate
deployment or network hop.

The current role launcher accepts composed roles (`evaluator,realtime`) and keeps
their contexts distinct. It requires different owned checkpoint namespaces.
That source capability does not qualify combined-process CPU/event-loop isolation
or a colocated sharding/failover profile.

| Deployment profile | Benefit | Required qualification |
|---|---|---|
| Same host/Pod, separate processes | Local UDS/TCP calls and shared placement can reduce operational overhead while keeping event loops separate. | Resource budgets and shared host/Pod failure remain explicit; scaling the Pod must not accidentally duplicate evaluator ownership. |
| Same process, separate modules | Can use an explicit in-process contract adapter and share selected immutable inputs. | Measure computation stalls, connection load, shutdown/drain and failure coupling. Preserve separate lifecycle and output ownership; source composition alone is not acceptance. |
| Independently placed pools | Scale scheduled work and viewer delivery for different demand. | Independent assignment maps, direct service contracts and complete maintenance coverage. |

Recommendation: preserve the logical boundary and permit co-location. Do not
require a distributed deployment for a small installation, or force both pools
to have identical counts merely to remove an inexpensive local call.

There is shared machinery to inspect before creating another service:
`tenant-projection-evaluator.js` materializes/evaluates clinical views; realtime
`projection.js` separately reconciles a durable input projection and builds a
snapshot/frame using shared read-context code. Realtime does not currently
consume a durable evaluator-produced frame contract. Combining processes will
not automatically remove those separate acquisitions/checkpoints. Measure the
duplicate input/view work and define any reusable immutable output boundary
before claiming a merger or new materialized-output API improves it.

## Placement and routing contract

The first prototype uses an explicit fixed worker roster and controlled map
revisions. It consumes configuration/platform placement, not a new membership
service. Freeze these source-owned facts together:

| Fact | Rule |
|---|---|
| Tenant key | Stable tenant UUID; never public alias, session ID or user-supplied destination. Alias-to-tenant resolution retains existing trust rules. |
| Logical assignment | Versioned deterministic hash/encoding and deployment-selected logical shard count. Keep that count fixed when merely adding/removing workers; changing it is an explicit repartition operation. |
| Owner placement | Each shard maps to a declared worker identity plus actual boot incarnation and placement generation. One worker may own multiple shards; a reusable ordinal/hostname is not a process incarnation. |
| Consumer route | Trusted edge resolves tenant to the admitted owner. Polling session IDs, upgrades and all namespaces remain on the same actual process for a connection lifetime. |
| Alarm route | The direct notification adapter resolves the same tenant/shard/owner mapping. Preserve logical consumer, request and attempt identity when an endpoint moves. |
| Route publication | Owner readiness and mapping generation are explicit. Stale edge or sender views must not make a wrong owner accept work; no arbitrary healthy-backend fallback or generic HTTP redirect. |

The edge can consume a rendered map or an existing application's routing decision
projected into response headers, as in the roles gateway. It need not ask an
authentication service for every frame, and internal application calls need not
traverse that edge. Deployment chooses UDS or private TCP/HTTP. No authentication
redesign, new bearer protocol or custom proxy belongs to this capability.

A backend verifies current tenant assignment before admitting new connections,
refresh work and alarm handoff. The routing map does not grant client authority:
current permissions, tenant bindings, exact writes/ACKs and operation lifetimes
remain enforced. If placement generation/owner admission becomes a wire field,
change the exact schemas/versioning deliberately; current alarm messages do not
already carry an ownership epoch.

The prototype must specify freshness/admission of its fixed map. A local cache or
Kubernetes readiness observation alone is not an exclusive owner fence. Unknown
or inconsistent placement refuses new admission until resolved.

## Projection and checkpoint ownership

Warm only assigned active tenants before routing them to a worker; report genuine
suspended tenants separately so healthy B remains routable. Process liveness,
owner readiness and tenant readiness are distinct. Operational inspection stays
available when application work is blocked.

Preserve a stable durable realtime consumer/checkpoint identity across worker
incarnation changes. Current code has one process-wide consumer, freezes tenant
configuration at boot and rejects another consumer in a tenant's checkpoint
namespace. Sharding therefore needs explicit parser/admission/assignment-update
changes; it cannot be implemented by starting the same configuration twice.
Do not derive durable identity from a Pod UID or reset checkpoints to hide a
collision. If a shard-specific identity is selected, specify legacy migration
and multi-shard ownership explicitly.

Owner admission protects checkpoint/projection work as well as socket delivery.
The new owner reconstructs current state, validates its source/tenant binding and
only then becomes routable. Independent physical-row/checkpoint inspection must
prove continuity; a plausible first browser frame is insufficient evidence.

Logical shards may be empty and a worker may initially own no active tenants.
Define an inspection-only idle state with no consumer route or synthetic jobs;
do not invent a tenant to satisfy the current nonempty runtime constructor.
Control-plane liveness, readiness to accept an assignment and readiness to serve
an assigned tenant are different signals. All-suspended assignments remain
inspectable without fabricating healthy clinical progress or blocking unrelated
owners. Empty-to-active and tenant-roster changes need explicit admitted startup
and coverage transitions; the current frozen boot configuration is not dynamic
tenant admission.

## Controlled moves and failure behavior

Initial scope is controlled fixed-roster moves and restart recovery, not automatic
takeover under an ambiguous partition. Planned sequence per affected shard:

1. Serialize the move against tenant maintenance and freeze the source/target
   assignment generation. Do not change a pinned restore cohort underneath it.
2. Stop new admission to the old owner, including new alarm attempts; retain
   accounting for existing connections, requests and responses.
3. Quiesce assigned work, finish or record uncertain in-flight handoffs, close
   connections and stop/terminate or effectively fence the old owner. Merely
   removing its route or observing lease expiry does not prove it stopped emitting.
4. Confirm old-owner exclusion, transfer the admitted generation, warm the target
   from durable state, then publish its route/readiness.
5. Clients establish new sessions, reauthorize and obtain current state. A live
   TCP/Socket.IO session is not migrated between processes. Stagger reconnects
   within measured bounds; prove healthy-tenant progress.

Resynchronization is namespace-specific. The main namespace can provide a current
full frame; a storage subscription acknowledgement is not a collection/history
reload, and an alarm subscription is not replay of earlier alarms. Qualify actual
API3 client reload/subscription ordering, concurrent changes and deletions rather
than assuming every namespace has the main browser's snapshot behavior.

If the target fails to warm, do not publish it as ready. With partial/stale route
publication, keep backend owner admission authoritative and expose routing
generation disagreement; affected requests may refuse rather than silently
falling back. Recovery or rollback is a fresh admitted generation/move with
old-owner exclusion re-established. Never republish an old incarnation/map or
restore old checkpoint data to make rollback appear successful. Preserve accepted
and uncertain outbox outcomes. Until a valid target is ready, the affected shard
can remain unavailable while unrelated shards continue.

If old-owner exclusion cannot be established, keep the affected shard unavailable.
Automatic partition failover is a later option requiring an effective platform
fence/defined bounded-overlap contract and its own adversarial proof. A database
epoch check or private network address alone cannot retract an already buffered
socket emission. Do not promise instantaneous exclusive delivery from a lease.

| Failure | Required outcome |
|---|---|
| Worker crash with confirmed termination | Route affected tenants through admitted replacement; reconnect, current authorization and full snapshot. Other owners continue. |
| Old owner unreachable but possibly alive | No speculative active replacement in this first scope; report unavailable/uncertain ownership. |
| Wrong/stale consumer or alarm route | Refuse before protected effects when assignment can be established; otherwise retain uncertainty. Never forward to an arbitrary URL. |
| PostgreSQL/API dependency failure | Preserve existing current-state/authority refusal; do not mark old frames fresh or invent write/notification success. |
| Worker or hot tenant overload | Bound connections/work/queues and expose pressure; do not silently route to a non-owner or allow one tenant to starve unrelated owners. |

## Alarm acceptance and reconnect semantics

Current alarm acceptance means handoff to realtime fanout, not durable storage of
an event for every device. Default Socket.IO delivery does not replay events a
disconnected client missed. A reconnected current-state snapshot is not proof of
alarm-event replay. See [Socket.IO delivery guarantees](https://socket.io/docs/v4/delivery-guarantees/).

Preserve existing durable pending/uncertain attempt recovery. A changed owner
address alone must not change clinical config identity, retire/mint an equivalent
notification, or make an already accepted request pending again. A late old-owner
success response still belongs to its original attempt; do not reinterpret it as
a fresh new-owner attempt. A lost response remains ambiguous. Current generic
transport errors do not prove pre-effect refusal, so routing changes cannot
justify an immediate transparent retry. Re-resolution for the next permitted
durable attempt retains its logical request/attempt semantics.

Explicitly choose and test the product's future delivery guarantee before claiming
no missed alarms across moves. Durable per-client offsets/event replay would be
additional protocol/state work, not a property supplied by sharding or successful
handoff. Do not fabricate device receipts, replay historical alerts blindly or
replay uncertain clinical mutations. Existing supported-client behavior and
operator-visible gaps must be evaluated in acceptance.

## Maintenance coverage must change with sharding

Current cohort code assumes each role/participant covers the same tenant set.
API can continue covering every tenant while realtime workers cover subsets;
this requires a real cohort/manifest contract change, not merely a route table.

For tenant maintenance, enumerate every actual actor that may hold work/state for
that tenant, including old/draining owners during a move. Validate complete
assignment/role coverage against the admitted generation, retain actual datastore
and backend census, pin incarnations and await all required invalidations.
Self-reported subset membership is not proof of completeness. Shared processes
may host different role coverages; account for each actual role and backend.

A pinned attempt freezes the relevant placement revision or refuses observed
change. New owner admission cannot bypass invalidation, and old actors cannot
vanish because they are unready or absent from service routing. A fresh attempt
follows the existing uncertainty/suspension and cleanup rules.

## Capacity and the hot-tenant limit

Tenant sharding spreads tenants, not every tenant's viewers. Measure connection
count, serialization/bytes, refresh/checkpoint costs, per-recipient authority
calls, event-loop lag, dependency pools, reconnect bursts and per-tenant interference.
A busy shard can move to a larger/dedicated worker; that still leaves a single
tenant's delivery bounded by one worker. More CPU cores alone do not parallelize
one JavaScript event loop.

If one tenant exceeds a suitably sized worker, qualify connection-sharded fanout
as a second capability: multiple connection owners for that tenant, maintained
Socket.IO adapter/distribution, per-recipient current authority and defined
projection ownership. Do not introduce a mandatory broker before that workload
requires it, or assume an adapter replaces the current local-client delivery loop.
Polling affinity remains required for the supported fallback transports; see
[multiple-node guidance](https://socket.io/docs/v4/using-multiple-nodes/).

The private operational API reports intended versus observed assignments,
incarnation/generation, active/draining/ready state, connection and tenant counts,
checkpoint/refresh progress, handoff outcomes, pressure and dependency health.
Bounded inspection must work during refusal and must not acquire ownership.

## Implementation and acceptance

One `MT-REALTIME-SHARDING` owner keeps assignment, routing adapters, parser/runtime,
checkpoint migration, cohort coverage, fixtures and controls together. Prototype
with the incorporated private API foundation; consume shared listener/operational
composition when it is integrated. Deployment-companion changes render routing
and worker placement. No Kubernetes installation or new scheduler is required for
the native fixed-roster proof.

| Criterion | Positive experiment | Intended semantic red control |
|---|---|---|
| Single-worker compatibility | Same clients, frames, polling/upgrades, namespaces, credentials and ACK/write behavior with one worker owning all shards. | Change a reply or skip current authorization; independent client/store assertions fail. |
| Multi-owner coverage | Two real owners, synthetic tenants across both and a trusted edge; verify every connection and notification reaches the assigned owner. | Independent edge/alarm map mismatch or non-owner admission causes missing/foreign delivery assertion failure. |
| Stable logical assignment | Add a worker without changing logical shard count; only explicitly moved shards change owner. | Derive bucket count from process count and observe unexpected tenant/session churn. |
| Checkpoint continuity | Kill/move an owner, inspect physical checkpoint/digest and reconstruct current state on the target. | Reset consumer/checkpoint or admit overlapping checkpoint writers; continuity/ownership assertions fail. |
| Polling and namespace affinity | Repeated polling, upgrades and main/storage/alarm sessions stay on the admitted incarnation; move requires fresh sessions. | Route an existing session ID to another incarnation; compatibility assertion fails. |
| Controlled drain and partition refusal | Hold a response during a move; establish old-owner termination/fence before target admission. Exercise an unknown-alive partition. | Activate solely on a route/lease change; observe old/new protected output or premature activation. |
| Partial cutover and rollback | Fail target warmup or route publication between stages; recover through a fresh admitted generation without rolling back durable outcomes. | Reactivate an old incarnation/map, reset checkpoints or fabricate readiness; ownership/continuity assertions fail. |
| Empty and suspended assignments | Start an idle worker, activate an admitted assignment, and suspend its only tenant while another owner progresses. | Fabricate a tenant/job, route to an unready owner or globally block unrelated work; readiness/progress assertions fail. |
| Notification ambiguity | Hold/drop and deliver late old-owner responses; inspect original durable request/attempt and independent delivered outcomes. | Reset accepted state, change logical identity on move or synthesize success; duplicate/false-outcome assertion fails. |
| Cohort coverage | API full coverage plus realtime subsets and a draining owner; restore A while B continues. | Omit a former owner or accept only a sampled service endpoint/self-report; complete census/invalidation assertion fails. |
| Isolation and progress | Suspension, dependency outage, reconnect pressure and hot shard do not expose another tenant or starve unrelated owner progress. | Broad readiness deferral or unbounded scheduling makes B's progress/freshness oracle fail. |
| Composition choice | Run the selected colocated/separate-role profile with independent clinical and viewer load. | Block delivery/event loop or duplicate assignment; scheduler-lag/ownership bounds fail. |

All experiments and limits are **UNMEASURED**. Choose finite workload/budget inputs,
retain failed predictions and inspect independent durable/output outcomes. Join a
coherent candidate before applicable full/browser/enabled-corpus/native/client
acceptance and final prcheck. `MT-SCALE-UNBOUND` consumes this capability for
horizontal realtime measurements; it does not substitute for its correctness gates.
