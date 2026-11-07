# Tenant owner authority and token verification

*Contributor-facing living contract. Adopted by the maintainer in the owner-authority
chat, 2026-11-05. Supplement to execution-plan D17/D22; this is the home of the owner
authority and local-verification amendment. Implementation acceptance is separate.
Queue homes: MT-CONFIG-MIN, MT-SECRETS-CONTRACT, T30-WIRING, MT-IDENTITY-PLAN.*

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
operator plane. Controller commands require their own reviewed authority.

Secret reveal is a separate permission with recent reauthentication. Ownership
transfer and adding co-owners are sensitive explicit operations; last-owner removal
must not orphan the tenant. Transactional transfer/recovery details require a
bounded implementation contract, not automatic operator access to owner secrets.
For the first preview, [ownership changes are operator-assisted](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#preview-operator-assisted-ownership).
Self-service co-owner addition and transfer are later enhancements; last-owner
protection, current authority and audit remain required for the operator path.

A grant must fit all three: project delegable catalogue, operator tenant ceiling,
and actor's explicit delegation authority. Possessing a permission does not grant
the right to delegate it. Start with reviewed roles and bounded assignment;
arbitrary role editing follows separately. Unknown permissions/roles refuse.
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
and writes even when the token signature verifies. Provider/identity outages and
session renewal behavior need their own explicit acceptance; no indefinite renewal
or new authority is granted by this outage policy.

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
