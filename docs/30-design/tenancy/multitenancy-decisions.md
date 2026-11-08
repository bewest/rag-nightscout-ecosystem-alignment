# Multitenancy decisions and architectural contracts

*Contributor-facing living decision reference. Consolidated 2026-11-06 from the
maintainer's D1–D23 decisions and their later amendments. This is a read-derived
reorganization, not new implementation acceptance or a new decision. The
[retained execution journal](../../archive/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md)
preserves the original rationale, prototypes, task definitions and measurements.*

This document owns the D1–D23 architectural decisions. The [owner-authority
contract](owner-authority.md) owns the later D17/D22 management and verification
amendment; the [durable event contract](durable-event-delivery-contract-2026-11-06.md)
owns B7's consumer/recovery rules. Later [release decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md)
own promotion-bar, compatibility and lifecycle decisions. Their amendments take
precedence over earlier journal text. The [dashboard](multitenant-delivery-dashboard.md)
owns milestone claims, the [queue](../../../queue/work-queue.yaml) owns item state
and gates, and [release contents](../../../releases/cgm-remote-monitor-16.0.0/contents.md)
owns integration/publication status. Read the [tenancy guide](README.md) for the
current execution plan; archived “next” instructions are historical.

## 1. Decisions

| Decision | Adopted direction and qualifications |
|---|---|
| <a id="d1"></a>**D1** — targets | Multitenant service is the design target; families, clinics and communities are configurations of it. Self-hosted single-tenant remains first-class permanently. |
| <a id="d2"></a>**D2** — shared storage | Shared logical storage with a tenant discriminator, rather than a database per tenant. The retained database experiments own the comparative cost evidence. |
| <a id="d3"></a>**D3** — isolation | PostgreSQL with RLS for multitenancy. Serving connections must not own tables or bypass RLS; trusted tenant binding is transaction-local. A missing binding must not expose other tenants. |
| <a id="d4"></a>**D4** — MongoDB | MongoDB remains permanent for single-tenant sites. The storage seam carries two mature backends; an adapter change must preserve single-tenant behavior. |
| <a id="d5"></a>**D5** — workload roles | One core, with multitenant `api`, change-driven `evaluator`, fan-out `realtime` and connector `vcpool`; `single` keeps its server. D21 packages roles under one executable. |
| <a id="d6"></a>**D6** — feed | Replication slot as the durable spine, reader-emitted `NOTIFY` for latency, bounded aggregate polling as backstop. Never emit notifications from a write trigger. B7 supplies later replay/checkpoint semantics; no direct `api` → `realtime` data stream is adopted. |
| <a id="d7"></a>**D7** — operator plane | Platform administration has its own entrypoint/network interface and is secured by unreachability, without a deployment API credential. Tenant administration is authenticated and tenant-bound; D16 gives it a separate listener. |
| <a id="d8"></a>**D8** — query contract | API v3's closed operator set is the initial query contract; v1 is bounded by client/corpus evidence. Use `mingo` as a differential oracle, with live-backend checks where oracle semantics differ. |
| <a id="d9"></a>**D9** — original base | The September seam work was based on `chore/nightscout-modernization`. This is its historical base decision, not an instruction to start current work there: the adopted current-dev delivery plan supersedes the old branch sequence. |
| <a id="d10"></a>**D10** — tenant label | Slug is a globally unique host label within one deployment, not a full hostname. Configured trusted resolution maps host to label to stable tenant id; no hardcoded first-label assumption. |
| <a id="d11"></a>**D11** — devicestatus | Generate columns only for the collection's indexed fields; retain the body as JSONB. Decomposition into normalized series is controller-declared and sits above the seam, so single-tenant benefits too. |
| <a id="d12"></a>**D12** — repositories | Alignment holds tooling, evidence, documentation and QC. Shipping code/tests belong in `cgm-remote-monitor`; findings and experimental scaffolding do not. Harnesses exercise shipping modules by path. |
| <a id="d13"></a>**D13** — credentials | No deployment-wide secret on any multitenant interface. Each tenant retains its own root/legacy credential; root-derived subject tokens must also be tenant-scoped. The operator plane remains credential-free. |
| <a id="d14"></a>**D14** — token keys | Per-tenant signing authority; resolve the tenant before examining a credential. A token for A used on B must fail signature verification, while opaque credential lookup and subjects also remain tenant-bound. Current key/credential state and rotation require their own acceptance. |
| <a id="d15"></a>**D15** — configuration source | `single` reads the environment. Multitenant per-tenant values come from storage, administered by owners under policy. Deployment-only values remain in each role's environment; D22 clarifies that distinction. |
| <a id="d16"></a>**D16** — audience listeners | Separate data, tenant-owner and private-operator sockets for the deployment, multiplexed by tenant rather than duplicated per tenant. Extract shared tenant resolution/credential verification before adding the owner listener. The adopted initial owner listener is a second bound socket inside `api`, movable to its own process later. |
| <a id="d17"></a>**D17** — authentication audiences | Devices permanently keep native tenant credentials; Hydra is deferred and D7 is unchanged. External human identity uses the later [shared optional single/multitenant OIDC integration](owner-authority.md#shared-oidc-integration), provider-backed renewal first and separate authorization adapters behind Nightscout's own credential exchange. The cohort-wide Kratos pool remains adopted in principle and gated, with cookie scope E and the production conditions below. |
| <a id="d18"></a>**D18** — registration | Well-known declarations describe existing writers without client changes. Controller-owned, dynamic typed declarations support new kinds, states, transitions, initiators, effects and commands. The controller owns lifecycle, composition, synchronization and reconciliation; the hub records and observes, never derives dosing state. Its extensible grammar is specified below. |
| <a id="d19"></a>**D19** — instances | Immutable content-addressed definitions are separate from leased instances. Each channel role declares `device` or `simulated` provenance; one device source of record holds a role, with explicit handoff and visible overlap. Definitions survive while data references them. |
| <a id="d20"></a>**D20** — identities and quirks | `identifier` is client sync identity; `_id` is the hub storage key. Every legacy surface serves hub-assigned 24-hex `_id` values on either store; the opaque alternative is withdrawn. Quirks are version-scoped, recorded when applied, and retired only from measured evidence. |
| <a id="d21"></a>**D21** — executable/profiles | One Node executable, `bin/nightscout.js`: `single`, `multitenant <role>[,<role>…]`, and operator tools. The namespace is `multitenant`, not `serve`; the subcommand selects tenancy and retires `TENANCY_MODE` as an operator setting. Legacy single-site start paths stay equivalent. Roles/listeners are admitted only by their gates. |
| <a id="d22"></a>**D22** — policy/secrets | Effective settings combine code defaults, operator defaults, permitted owner values and operator pins, under code-enforced project floors. Secrets are a separate encrypted component. The owner-authority amendment governs delegation, sessions and local public-key verification. |
| <a id="d23"></a>**D23** — socket writes | Multitenant `realtime` is a reader without data-storage write authority. It forwards every socket mutation and alarm ack/snooze unchanged, with the socket's authorization, to an internal `api` endpoint using the same write step and `socket` source label. Relay the actual result to the acknowledgement; a failed forward yields no acknowledgement, preserving client no-ack retry. Never synthesize success. No client change; `single` stays unchanged. |

D1–D17 were adopted in September 2026; D18 and its grammar amendment in October,
D19/D20 and their walk-through amendments in October, D21 on October 26 with the
November 3 namespace amendment, D22 on October 27 with the November 5 owner
amendment, and D23 on November 6 with its same-day all-socket-write amendment.
The original dated basis for each remains in the [journal decision table](../../archive/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#1-decisions).
D17's human-identity gate is the exception to unconditional adoption.

## 2. Storage, resolution and profiles

The seam expresses backend-independent storage and write intent, rather than
exporting driver semantics. Both supported adapters stay in applicable CI;
unavailable backends register pending tests instead of silently disappearing.
Query coercion belongs above the seam, generated from the shared schema. MongoDB
write validation remains inside its adapter. The initial v3 operators are `eq`,
`ne`, `gt`, `gte`, `lt`, `lte`, `in`, `nin`, `re`; v1 admissions and explicit
refusals depend on measured client contracts. `mingo` agreement alone does not
establish MongoDB/PostgreSQL agreement for regex or BSON truthiness/order.

One shared write boundary owns identity forms, server dates, soft deletion,
resend identity and the logical per-write event. Runtime-derived fields are
computed on copies, not persisted as source data. Import uses the admitted write
contract and typed-identity rules. Preserve collection/path-specific behavior
until a change has its own compatibility decision and consumer replay; the
[write contract](write-contract-spec-2026-10-07.md#9-current-shared-intent-and-backend-capabilities-2026-11-05)
and [storage interface](nightscout-storage-seam-interface-2026-09-14.md#11-current-admitted-ports-and-independent-scopes-2026-11-05)
own their current admitted contracts.

Tenant resolution precedes authentication. Slug labels use lowercase
alphanumerics and `-`, without leading/trailing `-`, validated on write and read.
A resolver's configured pattern has exactly one capture and no stateful flags;
trusted host/header provenance is explicit. Stable ids bind RLS, not reassignable
slugs. Socket handshakes resolve by host, not the client-chosen engine path;
path-only socket tenancy must refuse unless a reviewed trusted edge supplies the
host assertion. Unknown tenants must not allocate an unbounded context cache.

The current target profiles are resident `single` on MongoDB and multitenant
roles on PostgreSQL/RLS. Backend portability does not automatically admit
single-tenant PostgreSQL or multitenant MongoDB. SQLite/Celld needs a separate
backend/profile decision and compatibility, isolation, migration and operations
acceptance. The API v3 headless test launcher is development tooling, outside
the operator CLI/image. Resident versus computed execution is a separate axis;
its prototype/placement decisions live in the [release decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md).

`single` is dispatched in-process so termination reaches the server directly.
Each HTTP role has its own bind; private admin cannot share the consumer address.
Unknown commands exit 64 and help names the available commands. Packaging into
separate repositories/packages and an all-roles invocation remain separate
questions. The original journal's automatic image-healthcheck instruction is
historical: the [platform plan](../platform/next-gen-platform-plan.md) records
no automatic image healthcheck, preserving visible boot-error behavior.

## 3. Administration, identity and configuration

### Operator, owner and data authority

The operator plane alone provisions, suspends and executes lifecycle deletion.
It is cross-tenant by construction, with an explicit reachability/bind contract;
code review bounds that authority. Default operator bind is loopback; non-loopback
requires explicit acknowledgement and may never share the consumer interface.
A name used for a loopback bind must resolve only to loopback addresses.
Authenticated owner operations remain RLS-scoped. The dashboard's path holds no
credential for every tenant, and the operator plane never reveals owner secrets.

Credentials are per-tenant, identity may be per-cohort, authorization is
per-tenant. Isolation rests on current authorization and RLS, not the identity
provider's tenancy model. D17's native device path remains permanent. Providers
handle human password/recovery/MFA/session functions; Nightscout's exchange maps
verified `(provider, subject_id)` to current tenant membership and mints its own
tenant-bound credential. Membership keys are text, unique within a tenant, with
no foreign key to a Nightscout identity table.

For the gated Kratos direction, scope E is the apex cookie behind a hardened
edge. Before real identities: strip Kratos and CSRF cookies before tenant
backends; refuse cross-origin writes including WebSocket upgrades; route every
API/socket path through that edge; measure the conditions over HTTPS; assign
an owner to the compliance question. A different provider still needs its own
issuer/audience/cookie and logout/revocation acceptance. External identity alone
does not establish current Nightscout grants.

The [owner-authority contract](owner-authority.md) is authoritative for explicit
ownership, management versus data audiences, permission use versus delegation,
proposed-grant transaction fencing, lifetimes and next-operation revocation.
Legacy data/root credentials gain no implicit management privilege. Initial
headless management credentials are explicitly provisioned; a root bootstrap
would need its own explicit exchange ceremony. Last-owner removal must not
orphan a tenant. The [later compatibility decision](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#multitenant-promotion-bars-2026-11-06)
drops the optional subject-reader clamping mode; it does not drop proposed-grant
writer ceilings or permit breaking existing root/data clients.

### D22 policy and project floors

Policy per setting has a default, `open`/`bounded`/`pinned` mode and constraint
(allowed values, range, floor or host allow-list). Effective order is code
default → operator default → permitted owner value → operator pin. Deployment
policy may have tenant-specific operator overrides; project floors apply to all.
A launch-environment migration sends values an owner can no longer set to a
review list rather than dropping them.

| Project floor | Required behavior in multitenant roles |
|---|---|
| Tenant credentials and API security | No `API_SECRET`/`API_SECRET_FILE` deployment root; API3 security cannot be disabled. |
| Anonymous authority | Default roles limited to `denied`, `readable`, `status-only`; no anonymous writes or `TREATMENTS_AUTH=off`. |
| Network safety | Explicit hop-count/CIDR trust for proxy inputs; public-address webhooks only; driver-defined connector hosts; tenant-derived `BASE_URL`. |
| App settings privacy | Identifier reads require `api:settings:admin`, as search/history do; strict settings reads always enabled. |
| Data/log safety | `WRITE_VALIDATION` at least `log`; debug payload logging off; ignore `IMPORT_CONFIG`; permanent autoprune requires confirmation and an export offered first. |

Deployment-only ports, storage URIs, proxy trust, logging and release-driven
compatibility switches belong in the consuming role's environment. A role refuses
startup when required deployment values are missing and names them. No per-tenant
value leaks in from process environment. Operator policy contains tenant-facing
defaults/modes/constraints, not deployment infrastructure values.

Changes are versioned with who/when/what, invalidate the tenant cache live, and
apply on the next request or background cycle. An owner rollback is refused
whole if current operator policy would block any setting, naming every conflict.
Alarm settings remain hidden with a plain-language explanation until actual
multitenant alarm acceptance; preview/confirmation precedes alarm-policy changes.

Integrations are typed kind-catalogue records with schema-validated settings,
credential references, status, and operator-enabled kinds/limits. Several of one
kind may coexist. A kind may split credential parts between operator and owner;
owners never see the operator part. Existing environment aliases stay in `single`.

Secrets stay encrypted at rest; only their named consumers decrypt. Reveal is a
separate logged permission with recent reauthentication, never an operator-plane
operation. The provider remains pluggable: built-in development/small-operator
signer, Vault Transit and a cloud key service behind the common interface.
Private signing keys stay inside the secrets component. New-format tokens are
verified locally with trusted public keys and current PostgreSQL authority;
legacy signing/derivation material is retained compatibly until migration is
measured. Cache keys, never stale grants; unknown keys and unavailable current
authority refuse. The owner-authority contract defines the exact outage/session
rules. `secrets` is a role of the one executable, not an owner-dashboard privilege.

Migration tooling is the adopted Umzug wrapper with explicit operator-run
multitenant migrations before serving. PostgreSQL ledger/lock and each migration
commit together. MongoDB migrations are safe to rerun with ledger/lease locking;
transactional steps use transactions where supported, index creation precedes
writes to new collections, `listCollections` stays outside the transaction, and
a repeated body is tolerated. Single-site boot changes retain their own release
placement; journal prototype behavior is not an instruction to change defaults.

### Suspension and lifecycle

Suspend is total blackout, including ingest; pause blocks UI/reads while ingest
continues. Delete requires suspend, not pause. On suspension, disconnect sockets
and show last data visibly stale using existing staleness vocabulary; silent
frozen charts are not sufficient. Destructive lifecycle preconditions, export
coverage and key retention now live in the [owner-lifecycle packet](owner-lifecycle-decision-packet-2026-11-06.md)
and [release decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#multitenant-promotion-bars-2026-11-06).
Do not infer current deletion behavior from the original seam's admin prototype.
Shared-role startup follows the adopted [tenant-local startup admission decision](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#tenant-local-startup-admission).
The release record owns its implementation and acceptance state.
Deployment support-contact metadata remains a recommendation, not an adopted
schema: its privacy/availability rationale is retained in the [journal](../../archive/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#211-deployment-metadata-a-recommendation-not-a-decision).

## 4. Typed controllers, provenance and compatibility

The living [registration](../platform/spec/registration.md),
[records](../platform/spec/records.md), [identity](../platform/spec/identity.md)
and [authority](../platform/spec/authority.md) specifications own the detailed
D18–D20 contracts. The following clauses remain architectural requirements.

- Unknown grammar fields are must-ignore within a major version: preserve them
  without interpreting or serving them as data. Controller extensions use owned
  reverse-DNS namespaces and declared restricted JSON-Schema types. Missing types
  refuse; missing sensitivity labels withhold. Declarations carry units, ranges,
  horizon and evidence. The hub derives storage/validation/query, never dosing.
- Vocabularies stay open through `other` plus the controller's term. Each kind and
  extension has its own versions, served/stored selection and optional declared
  lossless mappings; absent a mapping, never convert. Horizons are `cycle`,
  `span`, `effective-dated`, `definition`, `aggregate`, with cadence/retention;
  experimental values get no invented well-known mapping or long-term promise.
- Capability negotiation precedes typed writes; unsupported elements use their
  declared well-known carrier. Typed 5xx responses retry with backoff until they
  succeed, never fall back to a carrier after a possibly stored write. Definite
  4xx refusal may use the carrier; no arbitrary delivery deadline is adopted.
- A definition is `sha256:` of RFC 8785 canonical JSON; many coexist per product.
  Conflicting meanings for the same kind/version refuse. References to catalogue
  kinds get the catalogue's native storage/carrier mapping. Retain definitions
  while stored records depend on them.
- Instances name definitions and renew capability-defined leases; no hardware
  identifiers. Identifying fields must be typed and sensitivity-labelled. Labels
  use reverse-DNS keys, including `dev.nightscout/purpose`, `/build` and
  `/migration-group`; only device-provenance data enters default therapy views
  and exports. Labels never substitute for provenance.
- Source-of-record selection is per channel role among device instances. Refuse
  a second holder, flag overlap, and hand off by release, lease lapse or owner
  transfer. Simulated roles never compete with device roles or receive their
  commands. The hub does not stop, direct or compose dosing.
- Default read versions obey operator capabilities, owner pins/blocks, then the
  newest live device instance. Lab/development views select instances explicitly.
  Legacy readers get declared read-only projections, labelled projected and
  never stored as sources. Typed/carrier dual-write links by instance and record
  identity apply only during migration or without a declared carrier mapping.
- A channel is shared only by the shared-slot catalogue or `sameAs`. An unlisted
  slot is product-scoped; equal names across products only produce an observation.
  Infer a command's product only when exactly one candidate exists; ambiguity
  refuses. Device command sinks require the product's bound subject or explicit
  owner transfer. A changed binding drops mismatched sinks immediately except
  owner-transferred roles; until a new destination exists, commands refuse.
  Simulated sinks are exempt from that binding rule.
- A released registration binds its next permitted writer, with binding event
  and credential kind visible. Migrating an `api-secret` binding uses the tenant
  root credential and changes the etag. Loop-status exclusivity remains
  unspecified until its decomposition is a typed channel. An agent initiator
  uses the open `other`/`controllerTerm` form rather than a new shared `agent` value.
- `identifier` survives retries/devices; resend matches it first and replies
  return it with the server's `_id`. Projected legacy ids are assigned at typed
  write time and remain stable, using hub receipt time rather than record time.
  Version-scoped quirk mappings are observed, never silent, and move
  proposed → active → historical → retired only from evidence; “recent” is the
  declared 365-day measurement parameter. Trio's `id` observation adds no new
  mapping. Shared slot candidates remain for controller-author confirmation.

## 5. Runtime isolation and clinical acceptance

B7's [durable event contract](durable-event-delivery-contract-2026-11-06.md)
owns producer/consumer checkpoints, replay and crash recovery. The per-write
logical stamp is the transaction's final clock floor; equal-stamp cohorts commit
together. Bound tenant scope is carried in the event; `single`, settle, MongoDB
and clock-off cases retain the contract's null-tenant/null-stamp rules. Provider
choice, hard-delete recovery and multi-node failover retain separate decisions.

D23 forwarding must preserve pinned client requests, stored outcomes, retries and
acknowledgements. Authorize with the socket's credential, not a role credential;
recheck current tenant authority. A failed forward yields no acknowledgement, preserving the client's no-ack retry; never synthesize success.
Durable tenant-keyed alarm acknowledgement must survive process/restart changes.
Typed role metadata records listener, data-storage authority, feed consumer,
egress and forwarding; distinguish a reader's checkpoint bookkeeping from data
write authority. [B7 leaves provider selection deferred](durable-event-delivery-contract-2026-11-06.md#9-what-this-contract-does-not-decide):
a slot, polling or both may satisfy the durable contract. When a `LISTEN`/`NOTIFY`
provider is selected, hold one `LISTEN` per held/served tenant on a direct
connection rather than transaction pooling. The [R73 first reference](../remedial/rc-16.0.0-integration-record.md#r73-durable-runtime-operations-batch)
uses polling over consistent tenant snapshots; it establishes no `LISTEN`
handshake or notification-transport latency result.
Re-run the socket-writer inventory when client pins change. The retained
[D23 analysis](../../archive/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#214-d23--realtime-is-a-reader-socket-writes-and-acks-are-forwarded-to-api-maintainer-2026-11-06-amended-the-same-day)
contains original corpus/rationale and entry-control design.

The evaluator materializes a transient bounded slice rather than resident
`ddata`, while retaining the actual alarm dependencies on treatments, profiles
and device status. Device-status bounds must preserve relevant kinds and success
conditions, not merely the newest few documents: retained [clinical findings](../../archive/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#7b-the-per-tenant-evaluator-is-cheap-and-the-split-is-by-depth)
explain how crowding can hide alarms. Current acquisition contracts, costs and
runtime acceptance remain in their own records; old spike figures are not a
capacity guarantee. No single-tenant computed profile is enabled by this design.

Before multitenant alarms/live updates are enabled, require actual A-to-A and
not-A-to-B producer delivery, durable ack/snooze, per-tenant exception containment,
and health signals for silent evaluation failure. Snooze data-time versus
wall-time remains an explicit policy question. Shared mutable locale, levels,
plugins, caches and authorization state require tenant-safe lifecycle controls;
a source grep is insufficient. Changes to alarm rendering also require a
single-tenant regression in a non-English locale. Never hold the synchronous
alarm decision waiting for storage; the durability/freshness trade-off needs
explicit measured acceptance. The [retained alarm-gate analysis](../../archive/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#7a-what-stands-between-here-and-alarms-being-on-under-multi)
contains original failure mechanisms and controls.

## 6. Retained evidence and current work

The [archived execution journal](../../archive/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md)
retains all original sections: deployment/storage rationale; auth and delegation;
registration amendments; query/coercion and write-seam findings; branch-refresh
rehearsals; Phase 0–4 task definitions, measurements, controls and limitations;
clinical/runtime analysis. Measurements keep their original dates and source
heads. The archive is not an instruction to rerun old branch work or a status
monitor. Current work follows the dashboard, completion schedule and queue.
