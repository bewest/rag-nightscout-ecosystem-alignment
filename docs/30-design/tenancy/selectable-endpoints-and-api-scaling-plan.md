# Private API composition, deployment bindings and fixed-roster scaling

*Living contributor-facing implementation plan, refreshed 2026-11-10. Current
mechanisms are **read-derived** from joined application `dc795bd1`; carried
measurements retain their original source/instrument in the linked evidence.
Remaining criteria are **UNMEASURED** until their instruments run. Queue homes:
`MT-ENDPOINT-TRANSPORT`, `MT-API-FIXED-ROSTER`; scaling and partitioning retain
`MT-SCALE-UNBOUND` and `MT-EVALUATOR-PARTITION`. Read with the
[runtime topology](runtime-topology.md). No production/default enablement follows
from implementation or a diagram.*

## Implemented foundation and remaining boundary

The [internal API implementation](../../../reports/tenancy/internal-service-api-2026-11-09/README.md)
and [joined dc795bd1 acceptance](../../../reports/tenancy/m6a-join-2026-11-09/dc795bd1-acceptance/)
carry the shared transport, three service registries, executable request/response
schemas, named clients, strict public/private separation and consuming-role
configuration. UDS and actual loopback HTTP tests exist; the joined regression,
browser, enabled-corpus and OIDC records have their own executed scope.

| Surface | Current implementation | Remaining adjustment or proof |
|---|---|---|
| Private contracts | Socket authority/mutations, alarm delivery and lifecycle participant operations have named clients and schemas. | Compose explicit contract modules on a component-private listener without weakening ownership or lifetime checks. |
| Binding | UDS or explicit `http:` origin; optional independent bind address. Existing UDS configuration is retained. | Qualify a selected private network deployment, not merely a helper's loopback behavior. Direct `https:` is not implemented. |
| Trust | UDS permissions/UID/inode protections or explicit deployment-owned network reachability. Service/version headers identify the contract, not a caller identity. | Exercise the selected deployment's reachability/access boundary. TLS/mesh/proxy integration, if selected, belongs to the deployment; no new bearer protocol is required. |
| Listener allocation | One service contract per listener. Public/management interfaces are separate. | Proposed one private listener per component, with server-owned module registration. More listeners remain possible where an actual policy/resource boundary requires them. |
| Worker operations | Evaluator has lifecycle control and in-process `health()`; realtime has a consumer-app health route. | Define and integrate an operational health/readiness/metrics contract. A GET metrics endpoint and its response format do not already exist. |
| API replicas | API work is request scoped; fixed participant identity/drain mechanisms exist. | Run two real equivalent APIs behind a service destination and prove all-instance maintenance, replacement and compatibility. |
| Runtime cost | Realtime obtains current authority during recipient fanout. | Measure latency, request amplification, dependency failure and aggregate resource limits under `MT-SCALE-UNBOUND`. |

Private application calls and private lifecycle control are different purposes
inside the same private API surface. They need not create separate transports,
services or deployment processes. Data/authorization/owner REST modules may
co-locate under existing audience and credential rules. REST v1/v2/v3 remain
version adapters inside one logical request-serving component.

## Endpoint and compatibility contract

The current source of truth is application `lib/server/internal-api/endpoint-config.js`
and `transport.js`, with service descriptions under `contracts/` and usage in
`docs/internal-service-api.md`. Deployment configuration uses environment references:

```json
{ "socketPathEnv": "NS_INTERNAL_SOCKET" }
```

```json
{ "urlEnv": "NS_INTERNAL_URL", "trust": "network", "bindHostEnv": "NS_INTERNAL_BIND" }
```

`bindHostEnv` is optional. A Kubernetes Service DNS name can be the dial origin
while a listener binds its own interface. A configured link-local/private address
is supported; loopback is not an architectural restriction. The current parser
accepts a legacy socket reference OR its endpoint-descriptor alternative, never
both. Public request content cannot choose private destinations. Credentials in
URLs, unexpected paths/query/fragment components, unsupported schemes and
implicit trust/fallback refuse.

Private operation payloads retain current tenant, credential, RLS, ACK and
lifecycle semantics. Current service/version headers require a coordinated
internal-peer upgrade; preserving the public client protocol does not establish
mixed-version peer compatibility. Listener consolidation must specify any header,
operation-path or schema migration explicitly. Existing UDS settings must remain
supported or have an explicit measured transition; a URL must not be inferred
from a malformed socket field.

UDS-specific filesystem checks remain inside its adapter. HTTP reachability is
supplied by the selected deployment policy. If established TLS termination or a
service mesh is chosen, document its trust boundary and test the selected binding;
do not infer process identity from a DNS name, port, header or successful probe.
No new application cryptographic login, discovery service or orchestrator is
needed to keep these contracts well defined.

## Remaining work and acceptance

These owner roles name integration boundaries, not a new reservation ceremony.
Confirm actual HEAD, current item openness and ownership before starting; stop
and report a mismatch rather than substituting the nearest working mechanism.
Keep each capability's helper, fixtures and meaningful controls in its lane.

| Step / queue owner | Concrete change | Focused gate and intended semantic control |
|---|---|---|
| Private API composition — `MT-ENDPOINT-TRANSPORT` | Build one explicit registry of supported `(method,path)` routes and contract modules per selected private listener. Enforce duplicate/missing/extra registration, schema/content-type and service/version ownership. Bind independently from public/management HTTP. | Actual UDS and HTTP calls succeed only on their intended private routes; public routes return 404. Inject a duplicate route, foreign contract/header, extra handler, malformed request or response and show the corresponding assertion turns red before unauthorized effects. |
| Per-operation lifecycle policy — same owner, with restore integration | Preserve application tenant admission through response completion. Lifecycle status/invalidation and operational probes need their own explicit policy, rather than inheriting a blanket tenant-work window. | With A in maintenance/suspended, status and the admitted invalidation still execute under the controller's existing rules while A application work refuses and B progresses. Hold an application response after SQL completion: drain must still wait. A blanket-window mutant must fail the lifecycle assertion, not merely a setup check. |
| Operational module — same composition owner | Specify liveness, readiness and metrics semantics, supported methods/response formats, dependency/tenant readiness behavior and scrape access. Retain useful existing health behavior or migrate it explicitly. | Exercise actual GET/operational responses and any metrics content type. Wrong method/schema/format and false-ready dependency mutants go red. The JSON POST RPC client is not silently used as a metrics client. Naming endpoints is not implementing a collector or inventing new metric values. |
| Deployment binding — endpoint owner with deployment-companion owner | Select UDS or private HTTP independently for application and direct-instance calls. Render actual service/dial and listen addresses, access policy and upgrade configuration; keep existing reference UDS settings valid. | Run real separated processes on the selected network. Compare current authority, stored effects/absence, schema responses, byte/deadline/cancellation bounds, disconnect/no-retry behavior and shutdown. Remove the selected boundary/config check or synthesize an acknowledgement after commit/response loss: the intended refusal/uncertainty oracle must fail. |
| Fixed roster — `MT-API-FIXED-ROSTER` | Consume two equivalent real APIs, one ordinary service destination and a complete roster of exact participant endpoints, with pool inventory. Controller addresses each actual instance even when contracts share its private port. | Observe which API handles each direct/service call. Missing/duplicate/service-aliased participants, wrong datastore/birth/incarnation/nonce, replacement during an old pin and omitted instance invalidation must refuse. Sampling a load-balanced destination is a deliberate failing control. |
| Joined replica behavior — same API owner | Preserve concurrent current authority, response/callback drain, tenant-local invalidation, lost-ack/commit uncertainty, replacement and B continuity. No transparent mutation replay. | Revoke/change state through one API and exercise both direct APIs/service; hold the other API's response; lose a commit or invalidation reply; replace an incarnation. Stale authority, early lifetime release, ignored uncertainty or missing B progress must each fail its own independent outcome assertion. |
| Coherent integration — existing candidate coordinator | Join original lane histories, freeze the chosen code/config/instrument candidate, then run applicable full/default-browser/enabled-corpus/native/client acceptance and final prcheck. | Preserve exact source/instrument attribution and named pending cases. A source-identical carried result stays attributed to its original run; new inputs require affected acceptance. No comprehensive campaign per leaf commit. |

**Lifetime composition is a substantive code change.** Current API and alarm
listeners supply an operation window; lifecycle control deliberately does not.
Read-derived from `tenant-lifecycle/operation-window.js`, shared work admission
refuses during exclusive/suspended maintenance. Wrapping lifecycle operations in
that same policy would make control unavailable when it is needed. This is a
predicted failure to reproduce with the control above, not a reported deadlock.

## Optional gateway decision adapter

Direct application-to-application calls retain the existing authentication and
authorization semantics. Listener composition or using TCP instead of UDS does
not inherently require changing those semantics. A native client can consume
JSON; an edge integration can project selected decision fields into HTTP status
and headers without making every private application call traverse a gateway.

**Read-derived prior art:** inspected `nightscout-roles-gateway`
`90840acee1ec641d881512e91f1728f7ed8f7817`. Its
[GET/HEAD Warden chain](https://github.com/t1pal/nightscout-roles-gateway/blob/90840acee1ec641d881512e91f1728f7ed8f7817/lib/routes.js#L327)
uses the existing policy decision and then
[sets upstream routing headers](https://github.com/t1pal/nightscout-roles-gateway/blob/90840acee1ec641d881512e91f1728f7ed8f7817/lib/policies/index.js#L107)
(`x-upstream-origin`, `x-forwarded-host`); its
[token header adapter](https://github.com/t1pal/nightscout-roles-gateway/blob/90840acee1ec641d881512e91f1728f7ed8f7817/lib/exchanged.js#L75)
sets `X-NSJWT`. Nginx can consume response headers through `auth_request_set`
without interpreting the JSON body. These code mechanisms are inspected, not a
newly executed gateway or interoperability campaign.

Nginx already handles public proxying and the Socket.IO upgrade. A selected
`auth_request`/Oathkeeper-style integration would add a private decision contract:
HTTP allow/deny/error semantics, original-request metadata, tenant resolution and
which injected identity headers the application trusts. Reuse the existing
authority component; do not duplicate its policy or use JSON `{denied:true}` as
an HTTP allow. Client-supplied identity headers must not become trusted inputs.

This adapter is a separately bounded optional deployment integration until its
contract is selected. It is not an extra prerequisite for selectable UDS/HTTP
transport. Connection admission does not replace subsequent message, subscription,
recipient, exact mutation/ACK or current credential authorization. Deployment
binding/trust work owns an adopted gateway profile; core owns its stable decision
hook if one is selected. No new mandatory gateway or authentication product is
selected by this plan.

## Evaluator workload and membership inspection

The operational listener supports a read-only evaluator module whose payload is
owned by `MT-EVALUATOR-PARTITION`. It reports configured mode/rule/version,
member count, ordinal/incarnation and intended slice separately from observed
membership/heartbeat agreement, freshness, conflicts and current eligibility.
Expose aggregate assignment/progress/lag and handoff health, with bounded private
drill-down where needed. Endpoint names and executable response schemas are still
to be implemented; existing cohort status is not relabelled as ring health.

Standalone mode reports all configured tenants without inventing a membership
lease. Partitioned mode reports the actual slice and observed membership basis;
ordinal configuration alone cannot make a stale/conflicting member healthy.
Introspection remains callable while evaluation is blocked, does not schedule
clinical work or acquire ownership, and does not clear lifecycle suspension.

Acceptance uses actual evaluator processes and independently enumerated tenant
assignments: member-count one covers the configured set; distinct members cover
it without stable-state gaps/overlap; stale/mismatched count or duplicate ordinal
is visible and blocks the affected computation. A mutant reporting only intended
configuration as observed health must go red. Exercise membership-change overlap,
recovery and duplicate durable/external effects under the existing M7 policy;
the inspection API must not claim exactly-once execution from a hash mapping.

The [ownership inventory](runtime-topology.md#evaluator-inspection-and-workload-ownership)
also covers notification attempts, future connector actors, realtime projections
and maintenance claims. The shared operational module does not impose one common
ring on these different work units or make them all stateless replicas.

## Service destinations, participants and workload owners

Ordinary request-scoped calls may use an equivalently configured API service
without pinning to the API that handled a prior request. A service must not retry
an uncertain mutation automatically or route to an undeclared participant.

Maintenance consumes a complete relevant roster, directly reaches each instance,
checks actual datastore/backend and role/namespace identity, pins incarnation,
drains actual operations and awaits every invalidation acknowledgement. Logical
participant IDs can survive replacement; an old pin cannot accept a new process.
A lost peer or uncertain commit/ack retains the affected tenant's suspension. A
fresh authorized attempt follows existing cleanup/registration rules; this is
not automatic restore resume or orphan clearance.

Use supplied configuration/platform inventory. A routing table may exclude
unready/terminating actors that still own operations, so it cannot automatically
serve as the maintenance census. The native proof uses explicit endpoints; a
Kubernetes/platform adapter is separate deployment work. No new membership or
consensus service is required for the API capability.

Evaluator and realtime replication remain separate semantics. `MT-EVALUATOR-PARTITION`
carries the adopted optional member-count/ordinal and pool-membership contract;
the default remains one workload owner. Realtime scale-out still needs delivery
ownership/fanout and polling-affinity proof. Neither is a reason to split REST
version adapters into separate services or to block the already accepted foundation.

## Measurement and documentation boundaries

`MT-SCALE-UNBOUND` owns synchronous authority fanout/dependency cost and aggregate
API pools, database/Vault pressure, failure/recovery and healthy-tenant progress.
Benchmarks retain synthetic workload, actual source/config, latency/queue/freshness
and independent durable outcome oracles. Functional success is not a capacity
or availability target. Metrics endpoint implementation does not itself supply
that measurement, and a proposed cache must retain current-authority guarantees.

Native runs use the adopted disposable harness and owned resource cleanup; there
is no grant, lead reservation or freshness-attestation ceremony. Capture exact
code/config/instrument identities, direct/service topology, complete participant
coverage, real listener/transport and each red/restored symptom. Preserve failed
predictions and distinguish actual clients/native processes from source doubles.

The [runtime topology](runtime-topology.md) owns figures and audience/purpose/binding
terminology. This page owns remaining work/acceptance; the queue owns claimed
state. Correct superseded living prose in place and link retained measurements;
do not create a second current plan or rewrite captured evidence.
