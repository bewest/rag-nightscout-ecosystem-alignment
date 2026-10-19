# L5 Authority: who may register, write, own a site, receive a command, and act for someone else

*Contributor-facing. Living specification, current at `main` `1b69c295` (2026-10-18). Layer L5 of
the [platform index](../README.md); terms are in the [glossary](glossary.md). Decisions:
[D7 and D13–D17](../../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#1-decisions)
(the admin plane, the credential root, the three listeners, the auth plane by audience),
[D18 and D19](../../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#261-d18--two-tier-controller-registration)
and the maintainer's decisions of 2026-10-14 to 2026-10-18 recorded with them. Queue:
`SPEC-AUTHORITY`.*

*Specification 8 of 8 in the [reading order](../README.md#reading-order); last, because it authorises what the others define. Expect rules AU1–AU5, binding and credential kinds, the owner's actions, namespaces, command destinations, delegation requirements DR1–DR7, what is recorded for audit, and the conformance cases.*

Who may register a controller's definitions, write under them, act as a site's owner, receive a
command, and act for someone else. The hub routes and records; it never decides whether a change
to therapy is safe, and it never doses (D18). Status: §2–§6 are decided or
specified; §7 states delegation's requirements, and its design is open.

## 1. Files

| file | what it is |
|---|---|
| [registration specification](registration.md) | the resources these rules authorise: products, definitions, instances, roles |
| `specs/sync/registration-submit.schema.json` | the binding, credential kind, owner actions and their reason codes |
| [configuration and delegation §5](../../tenancy/nightscout-configuration-and-delegation-2026-09-10.md#5-new-data-and-delegation-between-agents) | what delegation would have to provide |
| [agents in the ecosystem](../agent-trust-boundaries-2026-10-18.md) | read access today, the earlier draft's grant, a proposal lifecycle |
| [authority model](../../../10-domain/authority-model.md) | prior art for grants with scopes, constraints and expiry; designed, not implemented |

## 2. Principals and credentials

| # | rule | status |
|---|---|---|
| AU1 | **By audience.** Devices and uploaders hold a native per-tenant credential permanently and never authenticate through Ory, because an uploader cannot run an OAuth flow. Tenant owners and caregivers are to authenticate through one cohort-wide Ory Kratos pool on hosted sites, with Nightscout minting a per-tenant token from the session. Third-party apps get no delegated-access server (Hydra deferred). The platform operator's plane needs no credential: it is unreachable from tenants (D7). | D17; the Kratos row is adopted in principle and gated: no real identities until four production conditions hold at the edge and the compliance question has an owner |
| AU2 | **Three listeners.** `ns-api` and `ns-realtime` (and `single`) serve devices, clients and viewers; `ns-tenant-admin` serves the tenant owner, as a second bound socket inside `ns-api`; `ns-admin` serves the operator. Under `single` there is one listener, and the owner's actions are taken there with `API_SECRET`. An owner action on the data listener with any other credential is refused 403 `not-authorised`. | D16; the socket decided 2026-10-16; `API_SECRET` as owner on `single` decided 2026-10-14 |
| AU3 | **The credential root is per tenant.** Under `TENANCY_MODE=multi` there is no deployment-wide secret: each tenant holds its own root credential, tokens are signed with the tenant's own key, and tenant resolution runs before any credential is checked, so a signed token for one tenant fails the signature on another. That alone does not close an opaque token sent in a request body, which carries no signature; the subject store is also scoped under RLS (BF-25). Subject tokens are re-rooted on the tenant's credential. Credentials are per tenant, identity is per cohort, and authorization is per tenant, so isolation rests on the authorization layer and RLS, not on authentication. Under `single`, `API_SECRET` remains the bootstrap credential. | D13 and its amendment, D14, D15; decided, not on `dev` |
| AU4 | **Subjects, not tokens.** A registration or an instance is bound to the subject that created it, never to a token, so a token rotated on the same subject changes nothing that is bound to it. Whether a delegation grant names subjects the same way is part of §7. | decided 2026-10-14 (registration question 4; hub-sync §3.5 at `b3536bbf`) |
| AU5 | **Permissions today.** Writes are per collection (`api:<collection>:<action>`); reading is one bit: `readable` is `*:*:read`, every collection, every field, all time. | shipping (cgm-remote-monitor `lib/authorization/storage.js:235` at `dev` `fade2299`, read) |

Under `multi`, who reaches the hub through which listener, with which credential (dashed: adopted
in principle and gated, D17 row 2). The drawing's source is
`tools/structure-diagrams/inputs/3-listeners.yaml`.

![3·listeners: controllers and uploaders reach ns-api and ns-realtime with a native per-tenant credential; caregivers, viewers and the tenant owner sign in through the cohort's Kratos pool, which is gated, and get a per-tenant token for the data listener or an owner's session for ns-tenant-admin; the operator reaches ns-admin, which tenants cannot reach; both tenant listeners act on one tenant's records under RLS](../../../00-overview/perspective/diagrams/3-listeners.svg)

## 3. Binding and credential kind

A create or update binds the registration to the credential that wrote it: `boundTo: {kind:
subject, subject}`, never the token, so a token rotated on the same subject changes nothing; or
`{kind: api-secret}` for the shared secret on `single`, which any holder of the secret presents. The
stored registration records `credentialKind` (`subject`, `api-secret`, or `other` with the hub's
term), the kind that last created or updated it; both are returned with it. `API_SECRET` against a
subject-bound registration is `not-registration-owner` on the data path. A released registration
(`boundTo: null`) is bound by the next credential with the permission that updates it, even with
identical content (200, not a no-op); it records `bindingEvent: next-writer`, kept by later updates
under the same binding and cleared by a release or transfer, and not in the etag. When a
single-tenant site moves into a tenant, a registration bound to `api-secret` is bound to the
tenant's root credential, a further credential kind; the etag changes with `boundTo` (decided;
the mechanics are `SPEC-REG-MODES` and `SPEC-REG-MIGRATE`).

An instance is bound the same way, to the subject that created it, not to its product's binding,
so a development build with its own subject may run a copy of a registered product
([registration §8](registration.md#8-instances)).

## 4. The owner's actions

On the owner's listener: `ns-tenant-admin`, or the one listener with `API_SECRET` on `single`. The owner never edits a registration's content (an owner `PUT` is 403
`not-authorised`) and never submits one. An action other than retire answers outcome `applied`
with the resource after it; a request for what is already the case is a no-op.

| action | effect |
|---|---|
| retire | [registration §5.5](registration.md#55-retire) |
| block | state `blocked`, recording the interrupted state as `blockedFrom`; etag changes; declaration, binding and stored data kept frozen; the controller's writes and typed writes are refused 403 `blocked-by-owner`. With `If-None-Match: *` it blocks an identity with nothing stored (stored with no registration), and a create for it is 403 |
| unblock | restores the interrupted state (`active`, or `retired`); removes a pre-emptive block; never reactivates a retired registration. A blocked registration is unblocked before it is retired (409 `blocked-by-owner` otherwise) |
| release | `boundTo: null`; §3; drops non-matching `device` command-sinks (§6) |
| transfer | binds to a named subject; drops non-matching `device` command-sinks (§6) |
| free-namespaces | a retired registration's namespaces are no longer held by it (409 `not-retired` otherwise); its declaration and stored data stay readable |
| transfer-role | moves one role from its holder to a live instance that claims it with `device` provenance (409 `role-not-granted`, `role-not-claimed` or `not-live` otherwise); `If-Match` the etag of the instance it is moved from; both instances' etags change; the moved role records `grantedBy: transfer-role` |
| pin-version, unpin-version | [registration §12](registration.md#12-read-selection) |
| listing | every instance with its roles, labels and liveness; the overlaps; `registrations` (every stored product with its `boundTo`, `credentialKind` and `bindingEvent`); `slotNameObservations`; observed aliases only when asked |

An owner action on the data listener is 403 `not-authorised`, except with `API_SECRET` on `single`.

## 5. Authorisation of registrations

- **The submitter is the controller, a device.** It holds the native per-tenant credential (AU1).
  Submit, update, read and retire are on the data listener with that credential. Under
  `TENANCY_MODE=multi` the credential's token is signed with the tenant's key (AU3), so a
  registration is per tenant and a controller on two tenants registers twice. On `single`,
  `API_SECRET` may also register and is recorded as `api-secret`.
- **Permissions.** Submitting needs `api:registrations:create` and retiring
  `api:registrations:delete`, granted by the tenant owner on `ns-tenant-admin`. Updating and
  retiring also need the binding. The names are proposals.
- **Storage.** Registrations, definitions and instances are tenant data: per tenant, under RLS
  under `multi` (D3), never in the public capability document.

**Namespaces** are first to claim, per tenant. A credential with no stated namespace roots may
claim any namespace no other registration on the tenant holds. A hub may restrict a credential to
owner-granted roots; a registration may then declare a namespace equal to or below one of them
(`com.example` covers `com.example.negotiation.targets`; `com.examplefoo` does not), else
`namespace-not-owned`. Either way a namespace another registration holds is `namespace-claimed`. A
retired registration holds its namespaces until the owner frees them. Readers spanning tenants
interpret a field by the declaration carried with it, never by its namespace. A published list of
namespace conventions may record use; it is never a check.

## 6. Who may receive a command

A `device` command-sink role goes only to an instance whose binding equals the product's
`boundTo`, or to one the owner moved it to with `transfer-role` (stored with `grantedBy:
transfer-role`); any other `device` claim is refused `not-registration-owner` for that role, after
the channel checks and before exclusivity. A `simulated` command-sink claim is open to any
permitted subject and never receives a routed command. Source roles are open to any permitted
subject. When a product's `boundTo` changes (the owner's `transfer` or `release`, or a released
registration bound by its next writer), every `device` command-sink role held by an instance whose
binding no longer matches is dropped at once and stored refused `not-registration-owner`, and that
instance's etag changes; roles with `grantedBy: transfer-role` are kept. A held `device`
command-sink survives renewal only when the instance matches the binding or the role carries
`grantedBy`.

Where a command goes once a holder exists, and that the hub never routes to a guess, is
[commands §2](commands.md#2-where-a-command-goes). The command record and the proposal in front of
a command are proposed in [commands §4–§7](commands.md#4-the-command-record-proposed).

## 7. Delegation (not decided)

Delegation lets a principal give a caregiver, an app or an agent a part of their authority.
Status: requirements stated (DR1–DR7); design open; not implemented.

**What is decided around it:**

- Validation and enactment stay the controller's; the hub routes and records and does not judge
  whether a change is safe (D18).
- An agent that starts an intent is recorded as an initiator in the open form `{value: other,
  controllerTerm}`; no `agent` value is added to any vocabulary (maintainer, 2026-10-18;
  [state and intent S8](state-intent.md#2-rules)).
- A role for an agent, such as proposing or acting, is an `other` role a hub lists
  ([registration §9](registration.md#9-channels-roles-and-provenance)).
- The proposal record in front of a command belongs to the [commands specification](commands.md)
  (maintainer, 2026-10-18).
- Third-party delegated access through an authorization server is deferred (AU1).

**What a delegation design would have to provide**, stated 2026-09-10 as requirements for
qualified review
([configuration and delegation §5.4](../../tenancy/nightscout-configuration-and-delegation-2026-09-10.md#54-what-a-delegation-design-would-have-to-provide)):

| # | requirement | today |
|---|---|---|
| DR1 | scoped reads, enforced in storage, so a forgotten filter returns nothing | reading is one bit (AU5) |
| DR2 | bounded queries, because a read grant is otherwise a denial-of-service grant | unbounded on 15.0.8: API v1 passes query operators through; an operator allowlist is merged on `dev`, not released; an unbounded pattern-matching cost defect (BF-72) is open on 15.0.8 and `dev`. D8 sets API v3's closed operator set as the query contract, which bounds the operators, not their cost |
| DR3 | purpose and expiry as fields of the grant, not documentation | modelled for writes in the authority model; not implemented |
| DR4 | answers rather than data where they suffice, a smaller disclosure than raw reads | nothing |
| DR5 | an audit of what was read | writes are timed (`srvModified`); reads are not recorded |
| DR6 | revocation that is real, which argues for narrow, short-lived grants, since a read cannot be un-read | nothing |
| DR7 | minimization at the boundary, as this repository's de-identification tools do | the tools exist for research exports only |

**Proposed constraints**, carried from
[agents in the ecosystem §4.3](../agent-trust-boundaries-2026-10-18.md#43-what-a-proposal-lifecycle-would-add--proposed-not-specified)
and specified as proposed rules in [commands §6](commands.md#6-proposals-and-approvals-proposed):
read access never confers a propose or act role, so a `readable` credential, or a tool holding one,
cannot be promoted to either (CM12); an approval binds to the exact change, by the SHA-256 of its
canonical payload (CM13); and the state a proposal was based on is the hub's state version
([state and intent A12](state-intent.md#61-rules)), checked by the hub at approval (CM15). That
version is the hub's record of what the controller reported, so it can tell an approver that the
record changed, never that the controller's own state is unchanged.

**What this supersedes.** This specification, with [commands §6](commands.md#6-proposals-and-approvals-proposed),
is proposed to supersede the earlier draft of this work in cgm-remote-monitor's
`docs/proposals/agent-control-plane-rfc.md`, which started in this repository. It keeps that
draft's `agent` issuer type, its `suggest` scope ("can propose, human must approve") and its
`DelegationGrant` (who granted, to whom, scopes, constraints, expiry, revocation), and replaces
its rule that composes conflicting intents inside the hub, which D18 puts in the controller. The
[authority model](../../../10-domain/authority-model.md) and `nightscout-roles-gateway`'s
time-bounded policies are prior art for grants.

## 8. What is recorded for audit

- **Current state, not history, on the owner's listing (§4):** each product's binding, the kind of
  credential that last wrote it and how a released product was last bound; each live instance's
  roles, provenance and overlaps. A release or transfer clears the binding event, and a deleted
  instance leaves the listing.
- **Attribution of typed records:** each carries its instance, definition and the role's
  provenance ([registration §11](registration.md#11-typed-writes-and-attribution)). The stable link
  to who wrote it is the instance's own binding to the subject that created it (§3); the product's
  binding is today's, and can change after the write. A namespace string proves nothing about
  authorship.
- **Who started an intent**, in the controller's vocabulary (state and intent S8).
- **Not recorded:** who took an owner action and when; reads (DR5); and, on today's collections,
  who wrote a record beyond the free-text `enteredBy`, an identifying field that is not an
  identity.

## 9. Open

1. **Choices for the maintainer to confirm:** unblock restores the interrupted state; a blocked
   registration is unblocked before it is retired; `credentialKind` is the kind that last created
   or updated a registration; reactivation reclaims a freed namespace only if no other
   registration holds it.
2. **D17 row 2:** caregivers and owners on Ory Kratos, adopted in principle and gated.
3. **The contract per tenancy mode** (`SPEC-REG-MODES`) and across a site's move into a tenant
   (`SPEC-REG-MIGRATE`).
4. **Owner actions with no case:** an owner `PUT` (403, UCA-DEF-004), retiring a blocked
   registration before unblocking it (409), and `transfer-role` refused `role-not-granted` or
   `not-live`. AU3's per-tenant credential root has no case here either (UCA-AUTH-001). What a
   block or retire does to command sinks the product holds on a shared channel, which another
   product's claimant can then take, is not stated (UCA-AUTH-005).
5. **A record of owner actions** (who and when), which §8 says is not kept (UCA-ROUTE-007).
6. **Delegation (§7):** the grant's shape, where a grant is stored and checked, read scopes, read
   audit, purpose limitation and revocation, and whether an agent instance is scoped by label,
   by role or by its own subject. In the [control-loop analysis](control-loops.md), an agent
   holding `api:commands:create` sends commands with no proposal (UCA-AUTH-002); grants carry no
   expiry (UCA-AUTH-003); reads are neither scoped nor recorded (UCA-AUTH-004); and revoking a
   credential does not say what happens to its open socket subscriptions (UCA-SYNC-SERVE-005).

## 10. Conformance cases

The cases that check binding, credentials, the owner's actions, namespaces and who may receive a
command are listed here; they are part of the registration suites
(`tools/nsschema/test_registration_negotiation.py`, `test_registration_instances.py`). Delegation
has no case.

65 cases.

<!-- BEGIN GENERATED: authority-cases (tools/nsschema/spec_cases.py) -->
| case | shows | expected | control |
|---|---|---|---|
| `owner-action-on-data-listener` | An owner action sent on the data listener is refused | 403 rejected; not-authorised | `owner-retire` |
| `owner-block-api-secret-single` | In single mode API_SECRET performs the owner's block | 200 applied |  |
| `owner-block-pre-emptive` | The owner blocks an identity with nothing stored | 201 applied |  |
| `owner-block` | The tenant owner blocks a controller's registration | 200 applied |  |
| `owner-free-namespaces-not-retired` | An active registration's namespaces cannot be freed | 409 rejected; not-retired | `owner-free-namespaces` |
| `owner-free-namespaces` | The owner frees a retired registration's namespaces | 200 applied |  |
| `owner-release` | The owner releases a registration from its subject | 200 applied |  |
| `owner-retire` | The tenant owner retires a registration bound to a controller | 200 retired |  |
| `owner-transfer` | The owner transfers a registration to a named subject | 200 applied |  |
| `owner-unblock-retired` | Unblocking a registration that was retired before the block leaves it retired | 200 applied |  |
| `owner-unblock` | The owner unblocks a registration that was active | 200 applied |  |
| `blocked-by-owner` | A controller update with the current etag of a blocked registration is refused | 403 rejected; blocked-by-owner | `update-accepted` |
| `blocked-pre-emptive-create` | A create for an identity the owner blocked pre-emptively is refused | 403 rejected; blocked-by-owner | `accepted` |
| `blocked-update-stale-etag` | A controller holding the etag from before a block gets 412 and reads that it is blocked | 412 precondition-failed; stale-etag | `update-accepted` |
| `released-update-binds` | After a release, the next subject that updates the registration is bound to it | 200 accepted |  |
| `retire` | The owning controller retires its registration; stored data is kept | 200 retired |  |
| `retire-not-authorised` | A credential without api:registrations:delete cannot retire, even when bound | 403 rejected; not-authorised | `retire` |
| `retire-not-registration-owner` | Another subject cannot retire a registration bound to the subject that created it | 403 rejected; not-registration-owner | `retire` |
| `retire-roots-not-required` | The bound subject retires its registration without namespace roots covering it | 200 retired |  |
| `update-accepted` | The owning controller updates its registration with the current etag | 200 accepted |  |
| `update-not-registration-owner` | Another subject cannot update a registration bound to the subject that created it | 403 rejected; not-registration-owner | `update-token-rotated` |
| `update-api-secret-bound` | A registration bound to API_SECRET is updated by a holder of the secret | 200 accepted |  |
| `update-api-secret-not-owner` | API_SECRET cannot update a registration bound to a subject | 403 rejected; not-registration-owner | `update-api-secret-bound` |
| `update-token-rotated` | The bound subject updates its registration with a rotated token | 200 accepted |  |
| `typed-write-blocked-by-owner` | A typed write refused blocked-by-owner sends that record as its carrier | 201 accepted | `typed-write-load-503` |
| `accepted-api-secret-single` | In single mode a controller holding API_SECRET registers; the credential kind is recorded | 201 accepted |  |
| `not-authorised` | A credential without the registration permission cannot submit | 403 rejected; not-authorised | `accepted` |
| `accepted-first-to-claim` | A submitter with no stated namespace roots claims a namespace no registration on the tenant holds | 201 accepted |  |
| `rejected-namespace-claimed-first-to-claim` | Without stated roots, a namespace another registration on the tenant holds is still refused | 201 partial; namespace-claimed | `accepted-first-to-claim` |
| `rejected-namespace-claimed-retired` | A retired registration still holds its namespaces until the owner frees them | 201 partial; namespace-claimed | `namespace-claimed-after-free` |
| `rejected-namespace-claimed` | An extension namespace already claimed by another registration on the tenant is rejected | 201 partial; namespace-claimed | `accepted` |
| `rejected-namespace-not-owned` | An extension in a namespace the credential does not hold is rejected | 201 partial; namespace-not-owned | `accepted` |
| `namespace-claimed-after-free` | A namespace the owner freed is claimed by another registration | 201 accepted |  |
| `instances/definition-not-registration-owner` | Another subject cannot add a definition | 403 rejected; not-registration-owner | `definition-put` |
| `instances/instance-command-sink-not-registration-owner` | A command-sink role goes only to an instance of the product's bound subject | 201 partial; not-registration-owner | `instance-create` |
| `instances/instance-not-registration-owner` | Another subject cannot renew an instance | 403 rejected; not-registration-owner | `instance-renew` |
| `instances/definition-blocked-by-owner` | No definition is added to a blocked product | 403 rejected; blocked-by-owner | `definition-put` |
| `instances/instance-blocked-product` | No instance for a blocked product | 403 rejected; blocked-by-owner | `instance-create` |
| `instances/definition-namespace-claimed` | A namespace another product's definition declares is held | 201 partial; namespace-claimed | `definition-namespace-own` |
| `instances/definition-namespace-own` | A product's own definitions share its namespaces | 201 accepted |  |
| `instances/owner-transfer-role-data-listener` | A transfer on the data listener is refused | 403 rejected; not-authorised | `owner-transfer-role` |
| `instances/owner-transfer-role-not-claimed` | A role is transferred only to an instance that claims it | 409 rejected; role-not-claimed | `owner-transfer-role` |
| `instances/owner-transfer-role-other-subject` | The owner transfers a command-sink role to another subject's instance | 200 applied |  |
| `instances/owner-transfer-role-stale` | A transfer with a stale etag fails its precondition | 412 precondition-failed; stale-etag | `owner-transfer-role` |
| `instances/owner-transfer-role` | The owner transfers a role from its holder to a claimant | 200 applied |  |
| `instances/owner-pin-version` | The owner pins a version for the site's default views | 201 applied |  |
| `instances/owner-unpin-version` | The owner removes a pin | 200 applied |  |
| `instances/rebind-keeps-transferred-role` | A command-sink role the owner granted by transfer-role survives a rebind | 200 applied |  |
| `instances/rebind-new-holder-claims` | After a rebind an instance of the new binding claims the dropped command-sink | 201 accepted |  |
| `instances/rebind-release-drops-command-sink` | A product release drops the device command-sink roles of its instances | 200 applied |  |
| `instances/rebind-transfer-drops-command-sink` | A product transfer drops the device command-sink of an instance that no longer matches | 200 applied |  |
| `instances/rebind-transfer-keeps-matching-instance` | A product transfer keeps the device command-sink of an instance that matches the new binding | 200 applied |  |
| `instances/listing-includes-withheld` | The owner may ask for withheld members | 200 listed |  |
| `instances/listing-shows-binding-event` | The owner's listing shows how a released registration was bound, and with what credential kind | 200 listed |  |
| `instances/listing-shows-rebind-drop` | The owner's listing shows a command-sink role dropped by a rebind | 200 listed; not-registration-owner |  |
| `instances/listing-withholds-alias` | The owner's default listing withholds observed aliases | 200 listed |  |
| `instances/instance-create-other-subject` | A second credential runs another copy of a registered product | 201 accepted |  |
| `instances/instance-renew-transferred-command-sink` | A command-sink role the owner transferred is kept on renewal | 200 accepted |  |
| `instances/instance-renew-after-transfer-stale` | After a transfer the former holder's renewal meets 412 | 412 precondition-failed; stale-etag | `instance-renew-after-transfer` |
| `instances/instance-renew-after-transfer` | The former holder renews with its current etag | 200 partial; role-held | `owner-transfer-role` |
| `instances/command-after-rebind-no-destination` | A command between the drop and the new holder's claim has no destination | 409 rejected; no-command-destination | `command-after-rebind-routed` |
| `instances/command-after-rebind-routed` | After the new holder's claim, a command is routed to it | 200 routed |  |
| `instances/command-no-destination-simulated` | A simulated command sink is never a command destination | 409 rejected; no-command-destination | `command-routed` |
| `instances/command-not-routed-to-other-subject-simulator` | Another subject's simulated command sink is granted and never a command destination | 200 routed |  |
| `instances/typed-write-attributed` | A typed write by the source holder is accepted and attributed | 200 written |  |
<!-- END GENERATED: authority-cases -->
