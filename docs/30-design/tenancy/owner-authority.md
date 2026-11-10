# Tenant owner authority and token verification

*Contributor-facing living contract. Adopted by the maintainer in the owner-authority
chat, 2026-11-05. Supplement to execution-plan D17/D22; this is the home of the owner
authority and local-verification amendment. Implementation acceptance is separate.
Queue homes: MT-OIDC-NATIVE and MT-M6A-JOIN (M6a), MT-OWNERSHIP-OPS (M6b), MT-OIDC-SINGLE-PROVISION;
the earlier MT-CONFIG-MIN, MT-SECRETS-CONTRACT, T30-WIRING and MT-IDENTITY-PLAN are closed as superseded.*

## Authority and storage boundaries

PostgreSQL is authoritative for tenant status, identities/access grants, subject and
role assignments, sessions, credential status/generations, operator ceilings and
accepted signing-key generations. It already carries current data permissions;
local signature verification removes a cryptographic service dependency, rather
than moving an existing permission database out of Vault.

The secrets component protects recoverable credentials and private signing keys.
For a new asymmetric token, its private key creates the signature; a public key
checks the signature without permitting token creation. A JWT is the signed
credential presented by a client, not its signing key. Existing NS-style HS256
uses a shared secret for signing and verification, rather than this key pair.
MongoDB single-tenant subject/role/credential records are distinct from signing keys.

| Value | Storage and use |
|---|---|
| New first-party API/machine credential | PostgreSQL credential metadata plus one-way verifier for sufficiently random credentials where compatibility permits; plaintext issued once. Existing legacy hash/header forms can themselves be bearer credentials and must not be exposed as harmless hashes. |
| Access JWT | Presented by client; current session/credential state in PostgreSQL. Do not store a recoverable copy merely to authorize it. New claims use stable subject/session IDs, not the legacy raw `accessToken`. |
| Refresh/session credential | PostgreSQL session record and one-way verifier; rotation/reuse detection or provider-supported session equivalent. |
| Existing tenant root/legacy derivation material | Preserve encrypted recoverable form while legacy derivation or reissuance requires it; migrate only after measuring client compatibility. PostgreSQL ciphertext/reference, protected by secrets component. |
| Private token-signing key | Non-exportable inside Vault/production secrets provider; never in serving-worker memory or plaintext application tables. Public verification key and trusted tenant/purpose/version binding may be cached. |
| Vendor-cloud credentials, nightscout-connect credentials, APNs private keys, push/webhook credentials | Recoverable by explicitly authorized consumers. Existing Transit design stores tenant-bound ciphertext/references in PostgreSQL and encryption keys in Vault. Vault Transit is not a KV store for the submitted application values. A separate Vault KV choice is not implied. |

Single-tenant MongoDB and legacy token behavior remain supported. New multitenant
token semantics do not silently change legacy issuance or refuse existing clients.
Management credentials are a distinct audience/purpose from data credentials.

## Owner permissions and ceilings

Owner is an explicit tenant relationship, separate from legacy data wildcards.
Initial capabilities cover reading effective configuration/provenance, changing
permitted settings, managing uploader/follower credentials and grants, configuring
enabled integrations, export and deletion requests. Operator provisioning,
suspension, policy changes and execution of lifecycle deletion remain on the private
operator plane. The [preview deletion ceremony](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#preview-deletion-confirmation)
requires an explicit request/operator confirmation, permits cancellation before
execution starts and imposes no mandatory waiting period. Current authority and
verified artifact/recovery prerequisites still apply. Controller commands require their own reviewed authority.

Secret reveal is a separate permission with recent reauthentication. Ownership
transfer and adding co-owners are sensitive explicit operations; last-owner removal
must not orphan the tenant. Transactional transfer/recovery details require a
bounded implementation contract, not automatic operator access to owner secrets.
For the first preview, [ownership changes are operator-assisted](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#preview-operator-assisted-ownership).
Self-service co-owner addition and transfer are later enhancements; last-owner
protection, current authority and audit remain required for the operator path.

A grant must fit all three: project delegable catalogue, operator tenant ceiling,
and actor's explicit delegation authority. Possessing a permission does not grant
the right to delegate it. For the first preview the owner defines roles from any
permission string single tenant accepts, wildcards included, under the ceiling
([decision](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#owner-credentials-single-tenant-equivalent));
a stricter permission model is a [separate proposal for both modes](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#permission-tightening-applies-to-both).
Unknown roles refuse.
An upgrade must not silently add new capabilities to an existing delegated role.
Role edits have the same ceiling checks as direct assignments. Tightening current
policy bounds effective authority even when an old stored assignment remains.

Management authorization must inspect proposed roles/grants, the actor's current
delegation authority and current policy together inside the mutation transaction.
The existing operation/target-only callback is insufficient for this ceiling.
Permission spellings and complete role catalogue remain design outputs; the adopted
capability groups do not pretend those implementation details are complete.

## Selected current proposed-grant wiring (R53)

Accepted native17f9a457 explicitly selects ownerPolicy on the existing subject
store transaction. Proposed grants must fit reviewed catalogue ∩ locked operator
ceiling ∩ current matching management actor delegation, with current actor and
authority row fencing before subject/credential mutation and audit commit.
This implements only the selected REST37 operation subset. DELETE refuses and
managementAuth remains injected; human issuer/refresh, full wildcard/default
catalogue, existing-grant clamping and production owner listener remain
unimplemented. R48 data-token readers are unchanged.

Bounded native acceptance and parent semantic controls are recorded in
[R53](../remedial/rc-16.0.0-integration-record.md#r53---selected-owner-proposed-grant-policy-on-17f9a457-2026-11-06).
This selected transaction does not make an operation/target-only management
callback sufficient for general proposed-grant enforcement.

## Shared OIDC integration

The [shared OIDC decision](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#shared-oidc-provider-renewal)
adopts one optional integration for single-tenant and multitenant Nightscout,
provider-backed renewal first, and separate authorization adapters. Human login,
renewal and logout support should be equivalent for comparable capabilities in
both modes; storage and tenant-resolution differences remain explicit. The intended
single-tenant opt-in is `ENABLE=oidc`, or an equivalent explicit flag if integration
measurement refutes that spelling. Default-off behavior preserves current startup,
web/data authentication and unattended clients. No OIDC feature is implemented or
enabled merely by setting that value today.
The [identity provider decision](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#deployment-identity-generic-adapter-authentik-reference)
adopts a generic adapter with Authentik as the intended reference, subject to the
Kratos proof, and Kratos as the measured fallback.

Share the provider-facing protocol and session integration. Single-tenant maps
verified provider/subject to local current authority; multitenant resolves the
selected tenant and maps it to current membership, session and grants under RLS.
A provider identity or ID token is not automatically an accepted Nightscout data
credential, root grant or management credential. Human data access and management
access can share login plumbing while retaining explicit permissions/audiences.
Keep native API_SECRET, subject/device tokens and machine renewal compatible.

The existing `single` application supplies the single-tenant HTTP boundary.
Multitenant owner operations use `tenant-admin` on its own listener, initially
co-locatable with `api`; DATA `api`, `realtime` and the private operator `admin`
retain their existing responsibilities. Login/callback/exchange/renewal routes
are not yet implemented or placed by this direction. Prefer composing the common
adapter into the applicable existing boundary over requiring a new process.
No first-party browser UI is required by this integration decision.

Provider-backed renewal obtains new short-lived Nightscout management access from
valid provider authentication and current Nightscout authority. It does not require
Nightscout-owned rotating refresh credentials initially. The provider's login
cookie/session, any Nightscout browser-session cookie, the current server-side
Nightscout session and access bearer token are distinct. The [adopted session
contracts](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#m6-human-session-effects-2026-11-07)
scope idle/absolute lifetimes to management sessions, order logout local-first with
an optional provider call, fence concurrent renewal and default browsers to an
HttpOnly cookie with direct-token mode retained. The [adopted provider-outage policy](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#oidc-provider-outage-existing-access)
allows existing valid access only until existing expiry under current local
checks, with no new login/renewal or relaxed freshness. Adopted lifetimes below
remain; provider activity alone cannot bypass current Nightscout authority.

Acceptance must exercise the same synthetic provider/login/renewal contract on
both supported modes, enabled and disabled. Cover missing/wrong issuer/audience,
invalid signatures, identity-to-permission mapping, revocation/expiry, logout,
provider outage and ordinary legacy data-client compatibility. Multitenant adds
foreign-tenant/selector refusal and isolated current authority; single-tenant must
not require multitenant PostgreSQL, a cohort identity service or extra role listeners.
Record unsupported provider capabilities rather than silently weakening guarantees.
Both browser transports are adopted, cookie default; each needs its own acceptance.

## Management authentication and lifetime policy

The owner listener stays separate from data/private-operator listeners. Human
authentication uses an interchangeable identity provider; Nightscout maps verified
provider/subject to current tenant access and exchanges it for a tenant-bound
management token. No custom password/recovery system. Provider sessions alone do
not certify current Nightscout grants; provider logout/revocation propagation must
be part of the eventual session integration contract.

Initial headless management uses explicitly provisioned management credentials
from the private operator plane. Legacy root/data credentials never acquire
management authority implicitly. Root-based bootstrap, if added, needs a separate
explicit exchange ceremony. Unattended uploaders use revocable machine credentials
whose renewal does not require a human login.

Adopted initial limits, subject to measured implementation acceptance:

| Policy | Initial value |
|---|---|
| Human management access token | 10 minutes |
| Human management session idle / absolute lifetime | 30 minutes / 12 hours |
| Authentication freshness for reveal, ownership changes, privileged credential issuance | Within 5 minutes |
| Existing device/client exchange JWT | Preserve 8 hours initially |

Owners may narrow permitted lifetimes; they cannot exceed operator/project bounds.
Idle/absolute expiry requires current server-side session enforcement. Token expiry
is not revocation. Removing a grant or revoking a credential/session takes effect
on the next protected operation across workers, including protected stream delivery.
Already-authorized in-flight work may finish. No stale permission window is adopted.

## Vault verification amendment

For new-format tokens, private signing keys remain in the secrets component;
serving workers verify asymmetrically signed tokens locally with provisioned public
keys. This supersedes D22's requirement to send every verification to the secrets
component. It does not export private/HMAC keys or weaken current authorization.
Prototype algorithm: Ed25519; production JOSE/library/provider interoperability is
an acceptance requirement before selecting/enabling the production format.

Verification pins algorithm, issuer, audience, tenant, purpose and key binding;
validates issued/not-before/expiry/lifetime; and rejects unknown keys. Key discovery
never follows a request-supplied URL/JWK. Cache public keys, not stale grants.
Current accepted-key state prevents cached public keys bypassing retirement.

Each protected operation obtains one current authority snapshot covering tenant,
principal/session/credential status, key acceptance, grants and applicable policy.
Evaluate required permissions from that operation's snapshot. Use primary or
equivalently consistent reads; asynchronous replicas/worker-local TTL grants cannot
satisfy next-operation revocation. Management writes additionally fence policy and
grant changes transactionally. RLS and trusted tenant binding remain mandatory.

Bound pools across workers, batch required checks into the snapshot, and apply
pre-verification throttling. A logical snapshot may still require transaction and
tenant-binding round trips; one snapshot is not a claim of one wire request.

## Dependency failures and acceptance

With a trusted cached public key and available current PostgreSQL authority, existing
new-format tokens continue ordinary data operations during a Vault outage. New
issuance, reveal and secret consumption that requires Vault refuse. Unknown keys
refuse rather than fall back. PostgreSQL authority outages refuse protected reads
and writes even when the token signature verifies. The [OIDC provider-outage decision](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#oidc-provider-outage-existing-access)
allows existing human access only within its adopted lifetime and current
Nightscout authority during an identity-provider outage. Provider-dependent
renewal refuses. Local logout/revocation takes effect on the next protected
operation across workers; unavailable current authority refuses even with an
unexpired token. No grace extension or Nightscout-owned refresh system is added.
Provider logout propagation, qualifying idle activity, concurrent renewal and
browser transport have adopted contracts. Upstream logout cannot take immediate
local effect until it is known locally. Human login/session implementation is on
draft #8898 with joined acceptance records
([M6a](../../../reports/tenancy/m6a-join-2026-11-09/README.md),
[M6b](../../../reports/tenancy/m6b-join-2026-11-10/b70ad83f-acceptance/README.md));
real identity-provider interoperability is synthetic only.

The [lab](../../../tools/lab/owner-authority/README.md) compares the actual current
credential component/authority adapter with local verification and a bounded combined
snapshot. Required controls cover signatures/audience/tenant, committed revocation
across pools, expired sessions, key retirement and stopped dependencies. Performance
results are synthetic authorization-pipeline measurements, not API-handler throughput,
production capacity, full owner-ceiling acceptance or milestone promotion.

The [November 5 measurement](../../60-research/tenancy/owner-authority-local-verification-2026-11-05.md)
records the reproduced prototype results and their controls. The [R48 application
acceptance](../remedial/rc-16.0.0-integration-record.md#r48---local-public-token-verification-through-actual-api-on-3d5eac19-2026-11-05)
tracks the local branch that wires new-format verification through the actual
API preview. Legacy issuance migration, complete management/session flows and
production deployment acceptance remain separately scoped; local wiring is not
a claim that published operators or all existing clients use the new format.
