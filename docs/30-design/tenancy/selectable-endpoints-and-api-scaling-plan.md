# Selectable private endpoints and fixed-roster API scaling

*Contributor-facing implementation plan, 2026-11-08. **PLANNED, not executed.**
The maintainer requested selectable Unix-socket/HTTP(S) endpoints and independently
scaled API instances. This plan defines two bounded capabilities and their
acceptance; it selects no new production trust profile, endpoint environment
variable, wire schema, operating budget or milestone promotion. Queue homes:
`MT-ENDPOINT-TRANSPORT` and `MT-API-FIXED-ROSTER`. Read after
[deployment bindings and public names](deployment-bindings-and-public-names.md#configurable-transports-and-independently-scaled-api).
The source assessment is **read-derived** from application
`ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364`; actual prior acceptance retains the
heads in the [operation-window acceptance family](../../../reports/tenancy/operation-window-acceptance-2026-11-07/README.md).
No application, native transport, load balancer or replica campaign ran for this plan.*

## Outcome and boundaries

An operator can select a private transport without changing its operation
payloads or client-visible behavior. The same admitted operations work over a
filesystem Unix socket or an explicitly configured HTTP(S) endpoint. HTTPS needs
verified service and caller identity; cleartext HTTP requires an explicitly
admitted private deployment trust profile. An address alone grants no capability.

After that capability is accepted, a fixed deployment can declare more than one
API participant. Ordinary HTTP requests and realtime-to-API authorization/mutation
may use an admitted service destination. Restore addresses every actual API
instance separately, pins its incarnation and awaits the existing drain and
invalidation protocol. The minimal acceptance fixture moves from one API to two
declared APIs with the same synthetic tenants; other role counts stay unchanged.

These are capability boundaries within the existing preview. The accepted
baseline is usable despite broader parent items remaining in progress. Neither
capability claims whole M6, production/default enablement, operator release,
capacity, arbitrary raw-SQL fencing or all-client compatibility.

The evaluator remains one active owner of the current configured tenant set.
An evaluator replica count of one or a StatefulSet ordinal is placement, not
execution fencing. Future evaluator partitioning needs explicit disjoint tenant
assignment and its own overlap/recovery proof. Realtime replication, fanout,
polling affinity, dynamic membership, autoscaling, transaction-pooling proxies
and automatic orphan clearance are outside this plan. Platform membership and
scheduling primitives remain the source of placement and inventory. This work adds no custom API membership registry, discovery
service, evaluator scheduler, replica manager or consensus product. A platform
inventory/config adapter may supply the restore roster; native acceptance supplies
explicit endpoints. Kubernetes is a conceptual architecture frame here. Jsonnet,
resource manifests, cluster installation and platform rollout acceptance are
deferred and are not either capability's gate.

## Boundary audit: keep responsibilities separate

| Boundary | Stable application responsibility | Adapter/platform responsibility | Current implementation scope |
|---|---|---|---|
| Operation protocol | Fixed payload/result shapes, tenant/current-credential checks, lifetime, nonce/incarnation/schema identity and uncertainty refusal | Carry the same messages to the intended peer | Preserve the existing admitted operations and observable client behavior. |
| Private transport | Admit an authenticated service capability before invoking source-owned handlers; retain limits, cancellation and actual completion | UDS ownership or explicit HTTP(S) listen/dial and trust implementation | Add selectable transport; no generic proxy or public destination selection. |
| Service discovery | Request-scoped calls need an equivalently configured admitted API | Platform DNS/service or a configured native test dispatcher supplies the service destination | Consume destination configuration; do not create a discovery registry. |
| Restore inventory | Require a complete relevant roster, direct per-instance reachability and pinned actual incarnations; refuse change/missing peer during an attempt | Platform inventory/config adapter supplies identities/endpoints and communicates inventory changes | Consume a fixed roster in native proof; platform integration remains deferred. |
| API placement | Each real API participates in tenant admission, response drain and invalidation | Platform schedules/replaces API instances and may balance ordinary service requests | Prove two explicitly declared APIs with native processes, including replacement/overlap controls. |
| Evaluator ownership | One active owner for the current tenant set; future partitions consume explicit disjoint tenant assignments | Platform may supply stable partition identities, for example StatefulSet ordinals | Keep the singleton. No evaluator scheduler, partitions or replicated same-work execution is built here. An ordinal alone is not exclusion/fencing. |

These interfaces expose coupling before deployment-specific work hardens it.
A complete roster is an input to restore coordination, not permission to build a
parallel membership service. Platform churn observed during a pinned attempt
must retain refusal/suspension semantics; native fixtures simulate that runtime
condition without proving the platform itself.

Predictable bounded work can justify a singleton deployment when headroom and
restart availability are adequate. That sizing choice is distinct from the
logical single-owner rule for evaluator effects. Neither adds a watcher,
replicated evaluator, custom membership service or scheduler to these lanes.

## Source baseline and invariants to preserve

| Source at ed2 | Read-derived mechanism | Implementation constraint |
|---|---|---|
| [Private IPC](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/realtime/ipc.js#L10) | Bounded HTTP POST/JSON already runs over a Unix `socketPath`. Directory/socket ownership and the service UID establish local admission; the trusted factory receives a process-local symbol. | Preserve operation allowlists, byte bounds, deadlines, cancellation and actual response completion. A local symbol is not a network credential. Retain Unix ownership/publication/cleanup protections. |
| [Private API configuration](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/realtime/private-config.js#L5) | The exact parser accepts `socketPathEnv`, resolves it through private environment and calls IPC options. | Add an explicit endpoint contract; a TCP URL placed in the old field is unsupported. Preserve existing UDS configuration compatibility through an explicit parser rule. |
| [Private API operations](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/realtime/private-api.js#L69) | `/authorize` and `/mutate` each resolve the host/tenant and prepare current tenant state. Mutation rechecks the actual credential through the existing receiver. | A service destination may distribute request-scoped calls; do not substitute service authority for tenant/client authority or introduce an authorization ticket that silently requires replica affinity. |
| [API runtime](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/serve/preview-api.js#L129) | Request frames are fresh; retained startup and floor state have explicit tenant invalidators. Pools, responses and initialization are still local state. | Stateless request handling does not remove instance drain/invalidation obligations. Every admitted API instance must join the cohort. |
| [Cohort manifest](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/docs/tenant-operation-cohort.md#L3) | Fixed API replicas are already permitted as distinct participants. Participant IDs, roles, namespaces, endpoints and actual boot/datastore identities are compared. | Retain fixed membership, distinct instance destinations and actual incarnation checks. A load-balanced destination cannot represent the participant list. |
| [Outer operation lifetime](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/docs/tenant-operation-cohort.md#L24) | Operations remain unfinished until callback, HTTP/private response or socket acknowledgement completes; restore requires complete drain. | HTTP cancellation, connection loss or a drained SQL pool alone cannot declare a pending callback finished. Preserve uncertainty and suspension. |
| [Forwarding behavior](https://github.com/nightscout/cgm-remote-monitor/blob/ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364/lib/server/tenant-socket-forwarding.js#L33) | Each forward uses current socket credentials; an ambiguous result yields no acknowledgement and no automatic retry. | Transport and load-balancer policies must preserve that behavior, including when a mutation may already have committed. |

The application cohort document contains its original source-check/pending-native
wording. The alignment acceptance family records later native/cold executions on
their actual heads; this plan does not turn either source prose or old green
captures into new transport/replica acceptance.

## Endpoint contract to settle before implementation

The endpoint owner proposes the normalized configuration and both listener and
client interfaces together. Settle the contract in one review before parallel
consumer changes; do not invent incompatible env names in individual role lanes.
The illustrative names/syntax in the deployment guide remain proposals.

| Contract element | Required behavior |
|---|---|
| Listen versus dial | A listener binds an owned UDS path or explicit interface/port. A dial endpoint names an approved UDS path or HTTP(S) origin. Service destinations and direct instance destinations are separate configuration entries. A wildcard listen address is never copied into a client destination. |
| Operator selection | Environment/config references select endpoint kind, address and trust material at boot. Reject ambiguous mixed legacy/new fields, unsupported schemes, embedded credentials, fragments and unexpected URL components. Public requests, Host headers and socket message bodies cannot select private destinations. |
| UDS trust | Preserve private directory/socket permissions, correct numeric UID, symlink/path/inode protections, refusal to replace an existing endpoint and removal of only the owned endpoint. |
| Network service identity | Specify the authorized server identity and authorized caller role/purpose. HTTPS validates chain, server name and configured identity; caller admission may use an explicitly reviewed mutual-TLS or other bounded service-credential contract. TLS encryption or a private DNS name alone does not authenticate the caller. Credentials live in private references, not URLs or public configuration. |
| Private HTTP | Refuse unless its selected deployment profile explicitly supplies and measures the private reachability/caller-authentication boundary. No automatic HTTPS-to-HTTP downgrade. Network encryption requirements remain deployment admission work. |
| Capability admission | Only an admitted transport creates the internal trusted operation context. Tenant resolution, current client/session/key/grants, RLS and operator authority still run at their existing boundaries. The transport grants no arbitrary handler invocation. |
| Framing and limits | Preserve fixed operation routes, method/content type, bounded request and response bytes, complete JSON-object validation, non-success refusal, total deadlines and cancellation. Define connection establishment and response-completion handling; do not rely solely on idle timeouts. |
| Proxy behavior | No redirects, ambient proxy discovery, public forwarding headers, destination rewriting or silent transport fallback. Explicit service load balancing is permitted only under its declared no-replay/admission contract. |
| Failure/cleanup | Trust or identity failure refuses before an authorized operation. Transport loss/timeout preserves unknown mutation outcome and pending operation state. Shutdown drains actual work and closes only owned listeners/connections; an unresolved drain cannot select an unwindowed fallback. |
| Compatibility | Existing UDS config retains its documented semantics. Additive fields, versioning or explicit legacy normalization must be stated and tested; malformed legacy config cannot become a valid network endpoint by inference. No change to public API, websocket or mutation reply contracts. |

The transport contract must inventory all actual callers: private API authorization
and mutation, evaluator notification destination, cohort status/invalidation and
any shared configuration parser. Supporting an endpoint kind in a helper is not
consumer integration. Evaluator-to-realtime stays a single-destination handoff
within this scope; it does not acquire replicated realtime fanout semantics.

## Implementation sequence and integration ownership

These roles are proposed responsibilities, not active assignments. Confirm the
current coordinator and source ownership before dispatch. Each implementation
brief carries: **confirm the head commit and that the task is still open before
starting; stop and report a mismatch rather than reaching for the nearest thing
that works.** No runtime reservation or publication follows from this plan.

| Step | Owner role | Deliverable and integration boundary | Required focused evidence |
|---|---|---|---|
| 1. Freeze contracts | Transport owner with restore coordinator and security reviewer | One normalized endpoint/trust contract, explicit legacy compatibility and source inventory. `MT-ENDPOINT-TRANSPORT` owns parser, adapter and its helper/fixture/control changes. | Source inspection links identify every caller; config/trust alternatives are resolved without changing operation authority or wire payloads. Unsettled credential/trust policy stops dependent implementation. |
| 2. Implement adapter and consuming roles | Transport owner | UDS plus admitted HTTP(S) listener/client composition at all declared private consumers. Keep source-owned operation handlers and actual lifetime hooks. | Focused config, transport and consumer tests plus intended semantic reds/restorations. Native parity uses real owned sockets/listeners and test identities; source doubles are reported separately. |
| 3. Consume fixed API inventory | API scaling owner with restore coordinator | `MT-API-FIXED-ROSTER` consumes the accepted endpoint capability. Consume one API baseline and then two explicit API participants, service destination, direct instance endpoints, same role/namespace/tenant bindings and aggregate pool inventory. The roster is configuration/platform-adapter input, not a new registry. | Actual requests identify which API accepted them. Duplicate/missing/mismatched participants refuse; service routing never replaces cohort enumeration. No dynamic membership is implemented. |
| 4. Prove API equivalence and maintenance | API scaling owner owns API/config/client fixtures; restore coordinator owns joined maintenance composition | Concurrent direct/service requests, cross-API current authority, full response drain and all-instance invalidation; explicit death/replacement cases. Join original lane history normally. | Native stored-outcome and process-incarnation oracles, response/callback barriers, lost-ack uncertainty and positive B continuity. Focused diagnosis repairs failures before a new coherent freeze. |
| 5. Accept coherent joined candidate | Programme integration coordinator | Freeze exact joined application/config/instrument heads and complete the selected endpoint/replica matrix, then the required full suite, default browser, entire enabled corpus and final unchanged-source prcheck. | One comprehensive campaign for the coherent batch, not one per leaf. Prior campaigns retain their own heads and are not added together. Publish readiness remains separate from accepted capability. |

The second queue capability depends on `MT-ENDPOINT-TRANSPORT`. Existing broad
storage/runtime/tenancy parent cards remain context and retain their own gates;
their incomplete wider scope is not a fabricated prerequisite for using the
accepted bounded ed2 foundation. The coordinator may join implementation before
final acceptance, but incorporation alone does not close either capability.

## Fixed-roster topology and replacement rules

Native acceptance supplies explicit endpoints and an instrumented service
dispatcher; a platform binding is deferred. For ordinary traffic, the service
destination can select either equivalently configured API. A caller need not retain affinity merely because realtime keeps
its own socket connection. Each API still resolves the tenant, rechecks current
authority and enters the tenant operation window for its actual work. The service
must not transparently replay a mutation after connection loss or select an
undeclared API instance.

For maintenance, the fixed input manifest enumerates each actual API participant alongside
realtime, evaluator and tenant-admin. Each has a directly addressable endpoint,
expected authenticated service identity and actual boot incarnation. The
controller obtains status, validates datastore/namespace/role binding, pins the
whole selected cohort, drains and invalidates every participant. Sending the same
request repeatedly to a service URL cannot prove every API was reached.

A replacement process may reuse its logical participant ID only with a new actual
incarnation. An existing restore pin cannot accept the replacement's reply as the
old process. A lost participant, partial invalidation or uncertain DATA commit
retains the affected tenant's suspension. A fresh operator-controlled attempt can
register the actual complete cohort after prior-attempt cleanup under the existing
contract; this is not automatic restore resume or orphan clearance. Any
replacement/overlap must obey the admitted fixed-roster procedure with no
unaccounted overlap; a
StatefulSet name or desired replica count cannot prove the old process stopped.

Readiness keeps shared-process liveness distinct from tenant readiness. A remains
unavailable while its durable suspension/uncertainty persists; B must start and
make actual HTTP/realtime/evaluator progress. Shared schema, effective privilege,
binding, datastore identity or transport-trust failure still refuses readiness.
A TCP health probe or successful service request cannot substitute for full cohort
admission or authorize activation.

## Planned acceptance matrix

Every row below is **PLANNED / UNMEASURED**. The expected red names the intended
semantic failure, not a generic crash, connection/setup error or failing unrelated
assertion. Run mutations only in owned isolated copies/fixtures, confirm the break
landed, restore exact source/config and rerun the focused positive case. Preserve
failed predictions and correct this plan if the observed mechanism disagrees.

| Criterion | Positive experiment and independent oracle | Intended negative control and predicted symptom |
|---|---|---|
| Endpoint parsing and legacy UDS | Load existing private UDS config unchanged; separately admit proposed endpoint forms through actual role parsers. Compare normalized effective endpoints/consumer inventory without secret values. | Remove exact-kind/field validation: a malformed or mixed endpoint is accepted, causing the explicit refusal assertion to fail. Restore validation and refusal. |
| UDS ownership remains enforced | Real private directory/socket; refuse unowned/unsafe paths and clean only the owned published inode. | Bypass ownership/inode check in an isolated copy: unsafe path admission or wrong-endpoint cleanup is detected by the ownership assertion. A permission-denied setup failure is not this control. |
| HTTPS service and caller identity | Actual TLS listener/client with synthetic trusted and foreign identities. Verify correct intended peer and caller purpose before the operation; inspect independent handler/store counters. | Bypass server identity or caller-role check separately: a wrong peer or unadmitted caller reaches the handler, so the expected refusal/counter assertion fails. Restored case must leave no protected effect. |
| Private HTTP is explicit | Config without the admitted private trust profile refuses; the selected bounded fixture admits only intended private peers/callers. | Remove profile admission: unauthenticated/unqualified HTTP becomes usable and the explicit refusal assertion fails. No public deployment is opened for this test. |
| Framing, limits and deadlines | Real endpoints reject wrong method/type/route, malformed/oversized/truncated bodies and oversized responses. Held-open request/response hits the declared total deadline and closes owned work correctly. | Remove one byte or deadline check at a time: the deliberately oversized/held exchange is accepted or remains open beyond its bound; the matching assertion detects it. Avoid treating a process kill as deadline compliance. |
| Cancellation, redirect and fallback | Abort held requests; refuse redirects and trust failures without contacting alternate endpoints. Instrument actual destination/handler calls. | Enable redirect/downgrade/fallback in the isolated adapter: forbidden destination is reached, violating the independent zero-contact assertion. |
| Public inputs cannot choose private endpoint | Send permitted public requests with varying untrusted selector/message fields and verify only configured destinations are contacted; existing tenant-selector refusals remain. | Inject request-derived destination selection into an isolated copy: destination oracle sees a forbidden target or unknown-input request stops refusing. Synthetic targets only. |
| UDS/network operation parity | Run equivalent authorized/refused `/authorize`, `/mutate`, alarm and cohort status/invalidation fixtures through real selected transports. Compare public replies and independent stored effects, including absence. | Bypass current tenant/client authorization or change one reply field: foreign/refused effect or wire difference is caught. A successful TLS handshake alone cannot count as parity. |
| Two APIs really serve work | One-API baseline then fixed two-API fixture. Force direct and service requests through both instances; independent instance observations and stored outcomes confirm actual distribution/concurrency. | Omit or silently route away the second API: forced-instance coverage fails even if aggregate service responses stay green. |
| Current authority/config across APIs | Authorize through one API, revoke/change current state through its existing authority path, then use both direct APIs and the service. Compare replies, stored absence and consumed settings. | Retain stale permission/settings in one API: a revoked operation succeeds or an old setting is observed; current-state assertions fail. Merely refreshing a test-side cache is insufficient. |
| Complete cohort membership | Both APIs have unique manifest identities/endpoints and correct roles/namespaces/datastore tuple; restore pins actual distinct incarnations. | Point two manifest entries to the same actual process or omit one selected API: membership/coverage refuses rather than treating repeated service replies as a complete cohort. |
| Actual response/callback drain | Hold an A callback/HTTP response open on the second API after its SQL work completes. Restore cannot advance until that outer lifetime finishes; verify durable pending state and B progress independently. | Release lifetime at SQL commit or timeout alone: restore advances while the response/callback remains open, violating the barrier assertion. |
| All-instance invalidation | Warm both APIs' startup/floor state, restore A, and require fresh invalidation acknowledgement from each; follow-up reads reacquire correct state. B retains current state. | Skip one API invalidator or accept a synthetic reply: stale local state or missing actual acknowledgement is detected; activation must refuse. |
| Replacement and old pins | Replace a declared API with the same logical ID/new actual incarnation during a pinned attempt. Old pin refuses; a separately authorized fresh attempt pins the complete current cohort. | Ignore incarnation/schema/nonce identity: replacement/stale response enables activation, violating refusal. DNS/StatefulSet identity alone cannot satisfy the oracle. |
| Ambiguous mutation/no replay | Lose the mutation response after an independently observed commit. Client/socket receives no invented acknowledgement; adapter and service produce no automatic second attempt. | Enable transparent retry or success synthesis: independent stored/request count or reply oracle detects replay/false acknowledgement. Restore pending/uncertain state is retained where required. |
| Restore faults and tenant isolation | Exercise missing peer, DATA acknowledgement loss, invalidation acknowledgement loss and unresolved orphan. A remains protected/unavailable; fresh processes serve B via actual HTTP/realtime/evaluator paths. | Ignore uncertainty/missing peer or broadly defer shared errors: unsafe activation/startup is caught. Conversely disable tenant-local startup deferral: B replacement startup fails with A suspended. Preserve exact symptoms and restorations. |
| Aggregate resource behavior | Inventory all API pools/connections and exercise bounded concurrent work, shutdown and dependency outage/recovery. Verify stored effects, absence of leaked owned resources and healthy-tenant progress. | Remove a selected bound or omit an instance's pool from cleanup: retained resource/unbounded-admission oracle fails. This is mechanism acceptance, not an approved capacity/SLO claim. |
| Client and public behavior | Compare existing legacy/API3 credential forms, mutation replies/history, main/alarm socket acknowledgements and reconnect behavior against the single-API baseline, using actual pinned clients where required. | Change an observable reply/history/ack or substitute service identity for client authority: exact compatibility/independent storage oracle fails. A source-pattern replay stays labelled as such. |

Select supported workload sizes and finite deadlines before native dispatch.
Measure aggregate API pools against PostgreSQL/Vault/authority limits. Record
latency, connection wait and healthy-tenant interference where useful, but do not
invent a production threshold from passing functional fixtures. A numeric budget
requires its separate workload and maintainer acceptance.

## Evidence, dispatch and closure

Before dispatch, the coordinator records source and instrument commits, clean
worktree state, current queue openness and the exact capability criteria selected.
Each lane brief includes the relevant mechanism above, focused checks, semantic
controls, remaining policy boundaries and the two standing instructions. Runtime
execution needs the current owner's finite reservation and declared resource/
process cleanup; this document supplies no reservation.

Each capture names the actual application/config/endpoint trust/instrument
identity, transport kind, direct/service topology, complete participant roster,
actual incarnation coverage and datastore contract. Use synthetic tenant/client
fixtures only. Red controls name the changed property, exact intended symptom,
confirmed break and byte-exact restoration. Preserve native versus doubles,
source-pattern versus client binary, failed versus successful run and inherited
versus newly executed evidence. Counts from different attempts/heads are not added.

During implementation, use focused source/native/consumer checks appropriate to
the changed capability. Once joined, freeze one coherent candidate for complete
full/default-browser/entire-enabled-corpus acceptance and final prcheck after a
fresh upstream merge/check as required by the repository contract. A failed
campaign requires focused diagnosis and joined repairs before final acceptance
is repeated; a leaf commit does not trigger another comprehensive campaign.

The queue owns claimed state and runnable gates; the integration record owns
executed acceptance; release contents own capability closure, remaining blockers
and next integration owner. Documentation and generated diagrams may describe the
plan before either capability passes. A documentation/link gate establishes
structure, never transport trust, replica correctness, production admission or
milestone promotion. Close each capability only after its consuming paths and
native semantic controls pass on the attributed joined candidate. Future deployment
bindings consume the accepted interfaces separately. No Jsonnet, Kubernetes
manifest, cluster execution or platform rollout proof is required to close these
two native capabilities.
