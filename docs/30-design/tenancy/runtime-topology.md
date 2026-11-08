# Runtime topology: zones, components and coordination

*Living contributor-facing architecture guide, 2026-11-08. **Read-derived**
structure with source-scoped acceptance links; target endpoints/API replication
are planned, not executed. These grid diagrams separate trust zones, logical
endpoints and physical placement. The [implementation plan](selectable-endpoints-and-api-scaling-plan.md)
owns the new capability boundaries and planned acceptance matrix; the
[queue](../../../queue/work-queue.yaml) owns implementation state. Kubernetes is
an architectural frame here, not a deployment to build or prove. Jsonnet,
cluster bindings and evaluator partitioning are deferred.*

## Read the diagrams

Read downward: public clients/DMZ, public address/load balancing, trusted HTTP
edge, service destinations, actual role processes, then database/secrets and other
backing resources. A trust zone is not a host, Pod or container. A service address
is not a process identity. Named connection terminals and communication-plane
tables replace long crossing lines; they reference the same components/resources,
not duplicate stores or new mandatory services.

### Accepted one-host reference

![Accepted one-host reference topology](diagrams/accepted-one-host-topology.svg)

[PNG preview](diagrams/accepted-one-host-topology.png) ·
[SVG source](diagrams/accepted-one-host-topology.svg)

The actual [ed2 cold Compose acceptance](../../../reports/tenancy/operation-window-acceptance-2026-11-07/ed2-cold-accepted.json)
measures the synthetic one-host UI/socket/ordinary-restore deployment. Public
publication is lab HTTP; Vault uses TLS. The actual
[c23 native matrix](../../../reports/tenancy/operation-window-acceptance-2026-11-07/c23-native-accepted/README.md)
retains separate-role restore and fresh shared-role restart attribution. Drawing
a topology does not transfer either campaign to another image/head or qualify
production ingress, capacity or identity integration.

### Proposed fixed-roster API/network target

![Proposed fixed-roster API and network topology](diagrams/proposed-fixed-roster-network-topology.svg)

[PNG preview](diagrams/proposed-fixed-roster-network-topology.png) ·
[SVG source](diagrams/proposed-fixed-roster-network-topology.svg)

This is the proposed architecture for the queued endpoint/API capability, not a
Kubernetes resource design, an accepted multihost deployment or a replicated
clinical workload. API1/API2 are the minimal explicit scale-out fixture. Realtime
retains its connected clients and evaluator remains one active workload owner.
Network locations, public TLS and optional human identity retain their own
implementation/admission boundaries. PostgreSQL grants, Vault use and private
operator reachability remain role-specific; being in one zone grants no authority.

## Cohesion and coupling contracts

| Responsibility | Contract to keep cohesive | Coupling to avoid |
|---|---|---|
| Public edge and load balancing | Resolve a trusted public name, preserve current route/audience policy and forward to the intended service. | Public alias, backend service address and stable tenant ID becoming the same identity or an implicit permission. |
| Request-serving API | Existing request/write/authority semantics over current tenant-scoped durable state; reconstructible local state, explicit operation completion and invalidation. | In-memory singleton authority, sticky dependence on the API that handled the previous ordinary call, or owning evaluator scheduling. |
| Private transport | Same operation payloads, trusted service/caller admission, bounded messages/deadlines/cancellation and real acknowledgement outcomes over UDS or HTTP(S). | Filesystem ownership tests leaking into domain handlers, a URL conferring authority, or remote retry silently repeating mutations. |
| Realtime | Own live connections/rooms and deliver current permitted state; call API through a service destination. | Assuming an API service address identifies a restore participant, or that one load-balanced alarm handoff broadcasts to all realtime instances. Realtime replication is outside the new scope. |
| Evaluator | One active owner of its configured workload, with durable effects and existing current-state/recovery semantics. | Replicating the same tenant's evaluation simply because additional processes can be scheduled. Future explicit partitions may use platform-provided stable identities. |
| Restore coordination | Consume a complete supplied participant set, pin actual incarnations, drain actual operations and await every required invalidation before activation. | Discovering participants by sampling a load-balanced endpoint, treating readiness as proof that no old actor exists, or coupling correctness to a particular scheduler API. |
| Platform/configuration adapter | Supply process lifecycle, endpoint inventory and stable instance/partition identities through existing primitives or explicit configuration. | Building a parallel membership service, custom workload scheduler or orchestrator in this capability. |

## What comes from the platform, and what the application consumes

Use the platform's workload lifecycle and discovery. Kubernetes Services and
[EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/)
provide endpoint-routing infrastructure; [StatefulSet identities and ordinals](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/#pod-identity)
can provide stable instance/partition identities. We do not need to implement
those primitives again or prove Kubernetes itself for this plan.

The application-facing contract is narrower: receive a versioned complete roster
of the instances allowed to participate, address their control endpoints and
check actual runtime identity during maintenance. The set relevant to draining
can include an unready or terminating process that still owns an operation;
it cannot be reduced blindly to currently routable service destinations. The
scoped native acceptance fixture supplies an explicit roster. A future platform
adapter may supply equivalent inventory; its integration is deferred.

Similarly, an evaluator can consume one platform/config-assigned partition.
Stable ordinals are useful partition identities; the mapping of tenant/workload
to that identity and the policy for reassignment still need an explicit contract
when partitioning is pursued. No new evaluator scheduler, replicated evaluator
or sharding implementation is requested now. A Deployment of one or stable
StatefulSet identity is a useful lifecycle primitive; application completion and
uncertain durable effects retain their existing operation/recovery rules.

## Sizing is separate from logical ownership

For a component whose workload is bounded/predictable, one instance is a sensible
initial deployment recommendation when measured headroom and restart downtime
meet its service needs. A scoped configuration watcher/reconciler can fit this
model; it need not gain replicas merely because the API scales. This is a sizing
and maintenance choice, not a request for a new watcher in this architecture.

Keep the two questions explicit:

| Question | Examples / architectural consequence |
|---|---|
| How many instances are needed for load and availability? | An API, edge or bounded watcher may initially need one, and may scale if demand or availability requires it. Predictable throughput alone does not decide outage tolerance. |
| How many owners may process the same logical workload? | The evaluator has one active owner for its assigned tenant set. Later disjoint partitions may each have one owner, using platform identities/assignment inputs. Replicating the same work is a separate semantic choice. |

This avoids making either automatic replication or a custom scheduling system a
condition of a sound component boundary. Platform lifecycle primitives remain
reusable; application operation completion and uncertain durable effects remain
explicit where the existing runtime requires them.

## Immediate implementation boundary

1. **MT-ENDPOINT-TRANSPORT:** selectable private transport and effective trust,
   preserving the same operation/authority/lifetime/client semantics.
2. **MT-API-FIXED-ROSTER:** independent API processes behind a service destination,
   with every declared instance separately addressable for restore and replacement.

Acceptance uses separate native processes and synthetic A/B tenants, with the
plan's ordinary and meaningful red/restored controls. It does not require a
cluster, Jsonnet, autoscaling, a new membership product or an evaluator scheduler.
No implementation completion follows from this architecture/documentation work.

Diagrams are maintained by
[`render_tenancy_topologies.py`](../../../tools/site/render_tenancy_topologies.py).
Render SVG with Python; use its PNG option for previews. Diagram rendering is
separate from application runtime acceptance.
