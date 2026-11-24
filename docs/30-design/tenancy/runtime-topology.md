# Multitenant runtime topology

Candidate 5 uses a stateless API tier, tenant-partitioned evaluators and tenant-partitioned realtime processes. PostgreSQL holds the clinical data, pending work and completed output. The edge sends a tenant's sockets to its realtime owner. The [write-to-viewer diagram](evaluator-realtime-communication.md#from-a-write-to-a-viewer) shows where writes commit and where latency is measured.

## Component inventory and operator-topic readiness

| Component | Responsibility |
|---|---|
| API | Serves REST v1/v2/v3, checks current tenant authority and commits clinical writes. Equivalent replicas scale behind a service. |
| Evaluator | Owns its tenants' clinical windows and due work. Reads current state, evaluates shared plugins, commits completed output and wakes realtime. |
| Realtime | Owns live sockets for its assigned tenants. Sends authorized frames and storage events, and forwards mutations to API. |
| vcpool | Runs tenant connector actors with scoped credentials. Ingests through the clinical API. |
| Tenant-admin and admin | Tenant management has a separate owner audience. The private operator surface handles provisioning and lifecycle operations. |
| Edge and backing services | The deployment owns public routes, private reachability, the PostgreSQL primary, secrets delivery and identity-provider bindings. |

The registry binds public names to durable tenant identities. Data requests, management operations and operator calls retain their own listeners and authority. The platform applies migrations before serving. A serving process checks schema readiness. [Deployment bindings](deployment-bindings-and-public-names.md) · [Startup decision](multitenancy-decisions.md#platform-verification-removal)

## Logical REST cohesion and worker placement

REST versions are adapters within a logical API service. A request can go to any equivalent replica. Evaluator and realtime have different work to distribute, so each has its own replica count (K). On Kubernetes, API uses a Deployment and evaluator and realtime use StatefulSets. For each role the Pod ordinal selects its tenant hash slice. Realtime routing uses the same assignment at the edge. A change to K requires a planned restart. [Static hash ownership](multitenancy-decisions.md#static-hash-ownership) · [Ordinal binding](multitenancy-decisions.md#statefulset-ordinal-scaling) · [Deployment bounds](multitenancy-decisions.md#evaluator-k-bound)

## Evaluator inspection and workload ownership

An evaluator owns each assigned tenant's work even when that tenant has no socket. Readiness measures whether a role can serve. Pending work, completed output and the time since an accepted input measure tenant progress. Realtime loads a tenant when it has a connection. vcpool sizes outbound work against upstream quotas. [Resident windows](multitenancy-decisions.md#stateful-evaluator-resident-window) · [Connection-driven realtime](multitenancy-decisions.md#realtime-connection-driven) · [Connector capacity](multitenancy-decisions.md#vcpool-egress-capacity)

## Scale envelopes and fleet planning

The nominal deployment places one vertically sized PostgreSQL primary on its own node. Evaluators scale by adding slices and reducing the cost of a cycle. Size them from measured density, ordinary write-to-output latency and recovery after a planned restart. The local kind experiment and the paid cluster use different placements and workloads. Multiple independent databases and tenant moves between them remain deferred fleet options. [Primary placement](multitenancy-decisions.md#one-large-postgresql-primary) · [Evaluator headroom](multitenancy-decisions.md#evaluator-capacity-headroom) · [Measured candidate scope](execution-log.md#candidate-5-qualification-and-nominal-discovery)

<a id="work-needed-to-reach-the-target"></a>
## Qualification and delivery boundaries

A functional test qualifies the named source and binding. Admission also depends on the selected workload, current authority, storage and clinical outcomes, and recovery on that deployment. [Production criteria](production-critical-path.md) · [Milestone roadmap](multitenant-delivery-roadmap.md)

## Read the diagrams

The [tenancy topology plates](diagrams/README.md) preserve the accepted one-host Compose reference, private-listener composition and former pgstream topology. Their filenames and source pins identify the original measurements. The [archived topology guide](../../archive/tenancy/pgstream-topology-2026-11-16.md) explains each plate and the fleet proposals of that period.

Sections in the captured guide:

- <a id="runtime-topology-zones-components-and-private-apis"></a>[Runtime topology: zones, components and private APIs](../../archive/tenancy/pgstream-topology-2026-11-16.md#runtime-topology-zones-components-and-private-apis)
- <a id="reuse-the-components-across-profiles"></a>[Reuse the components across profiles](../../archive/tenancy/pgstream-topology-2026-11-16.md#reuse-the-components-across-profiles)
- <a id="current-stream-runtime"></a>[Current stream runtime](../../archive/tenancy/pgstream-topology-2026-11-16.md#current-stream-runtime)
- <a id="historical-accepted-one-host-reference"></a>[Historical accepted one-host reference](../../archive/tenancy/pgstream-topology-2026-11-16.md#historical-accepted-one-host-reference)
- <a id="private-api-composition-one-internal-listener-per-role"></a>[Private API composition: one internal listener per role](../../archive/tenancy/pgstream-topology-2026-11-16.md#private-api-composition-one-internal-listener-per-role)
- <a id="proposed-fixed-roster-api-scale-target"></a><a id="fixed-roster-api-scale-placement-example"></a>[Fixed-roster API-scale placement example](../../archive/tenancy/pgstream-topology-2026-11-16.md#fixed-roster-api-scale-placement-example)
- <a id="ownership-and-placement-constraints"></a>[Ownership and placement constraints](../../archive/tenancy/pgstream-topology-2026-11-16.md#ownership-and-placement-constraints)
- <a id="single-worker-priority-and-component-regrouping"></a>[Single-worker priority and component regrouping](../../archive/tenancy/pgstream-topology-2026-11-16.md#single-worker-priority-and-component-regrouping)
