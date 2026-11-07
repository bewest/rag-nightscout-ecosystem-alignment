# Multitenant delivery roadmap

*Contributor-facing living plan. Consolidated 2026-11-06 from the delivery journal
and the adopted release decisions, without a new application measurement or
milestone promotion. This page owns delivery boundaries and promotion criteria.
The [dashboard](multitenant-delivery-dashboard.md) owns recorded milestone claims;
the [queue](../../../queue/work-queue.yaml) owns item states, gates and blockers.*

## Reading and execution order

Use the [reading guide](README.md) to select a contract. Use the
[completion schedule](multitenant-integration-batching-plan-2026-11-06.md#5-current-completion-schedule-adopted-2026-11-06)
for current batch ownership, implementation order and verification depth. The
[integration record](../remedial/rc-16.0.0-integration-record.md) owns executed heads,
failures, controls and campaign limits; [release contents](../../../releases/cgm-remote-monitor-16.0.0/contents.md)
owns publication and cycle updates. A source branch, an incorporated change, an
accepted batch and a promoted milestone are distinct claims.

Delivery uses three completion stages: **A**, data/control/clients through M4;
**B**, durable runtime for M5; **C**, synthetic operations for M6. Independent
implementation and early uncertainty proofs may proceed in parallel. Freeze one
coherent candidate for comprehensive acceptance; do not rerun accepted campaigns
merely because a new session resumes. Promotion requires the complete criterion
list below, with actual commands, source/instrument revisions, artifacts and
verdicts on the applicable final tree.

Use the [current M5/M6 decision list](m5-m6-decision-list.md) for remaining human
questions and measurement prerequisites. Prefer a minimal working reference with
explicitly deferred enhancements; do not substitute a component pass for a milestone.

## Supported boundary and owner journeys

The supported owner deliverable is a **headless, documented, versioned API**, with
conformance independent of vendor UI. A first-party owner UI is deferred; vendor
UI must use the same validation and floors and must not put an all-tenant service
credential on the owner's request path. Existing single/Mongo behavior remains
first-class. The multitenant target uses PostgreSQL/RLS; single PostgreSQL,
multitenant MongoDB and SQLite/Celld are outside this delivery series.
Multitenant completion is not a 16.0.0 tag prerequisite; placement of a reviewed
dormant slice remains separate from enabling its roles.

Initial lifecycle operations are private-operator actions: provision, suspend,
export and delete, without public signup. An owner may export or request deletion;
the operator authorizes and executes deletion. A request never bypasses
confirmation, retention or recovery policy. [Ownership changes are operator-assisted](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#preview-operator-assisted-ownership)
for the first preview; self-service co-owner addition and transfer follow separately.
Operator execution still preserves last-owner protection and owner-secret boundaries.

| Owner journey | Required contract | Capability boundary |
|---|---|---|
| Understand configuration | Effective value, source/default/pin/constraint, stored owner value and explicit ignored/rejected reasons | No raw secrets in config reads |
| Change units, timezone and display | Reviewed typed catalogue, validation, version/precondition, audit attribution, live invalidation and rollback | Small reviewed catalogue first |
| Manage uploaders/followers | Tenant-local subjects/roles, root and subject-token rotation/revocation | Preserve legacy credentials; distinguish root from least privilege |
| Configure connectors/push targets | Typed integration kinds, bounded egress, tenant-owned secret references, split owner/operator credential parts and health | Admit each kind only after its consuming runtime gate |
| Export/request deletion | Tenant-local export, request/confirmation status and private operator execution | No foreign rows or secret plaintext in the artifact |
| Change alarm settings | Preview/confirmation, ordered thresholds, units, evaluator version and invalidation | Unavailable until multitenant alarm acceptance |

Controller registration, commands/intents and delegated-access journeys have their
own contracts. Their later runtime is not implied by a configuration API.

## Configuration, authority and secrets

[Owner authority](owner-authority.md), including its [shared OIDC integration](owner-authority.md#shared-oidc-integration), owns management authority, delegation,
session/reauthentication and local-verification amendments. Preserve D22's order:
code floors, then operator defaults/bounds/pins, then permitted owner values.
Refuse unsupported names explicitly; role deployment values stay in the
environment and credentials are not settings. Full catalogue claims need a fresh
census. Names, API paths, preconditions and refusal shapes belong to the reviewed
configuration contract, rather than being selected ad hoc by a lane.

Grant removal or token revocation takes effect on the **next protected operation
across workers**, at a defined authoritative-read linearization point. If current
state cannot be established, refuse. An unexpired token or stale cached grant is
insufficient; an operation already authorized/in flight is not retroactively
undone. Socket writes, subscription changes and protected delivery share this
boundary, including reconnect, cache invalidation and authority-outage controls.

Preserve each tenant's legacy hashed `api-secret` header, subject tokens and socket
secret forms. Resolve and authorize the tenant before credential verification;
there is no process-wide multitenant root secret. Data credentials do not imply
owner management or delegation authority. Audit records name the verified
subject/root principal rather than inventing a human identity. Human login uses
an interchangeable reviewed identity provider, not a new password/recovery system.

The [promotion decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#multitenant-promotion-bars-2026-11-06)
drop the incompatible optional subject-reader clamping mode. Any replacement must
preserve existing tenant-root credentials. Proposed-grant management enforcement
and full lifecycle authority are separate contracts.

The secrets component owns recoverable secrets and private signing keys. New
asymmetric tokens may verify locally with trusted public keys and current
PostgreSQL authority; private keys remain protected. Vault Transit does not store
submitted application data: tenant-bound ciphertext/references, scoped consumers,
key versions, redacted audit, renewal and recovery remain necessary. Owner reveal
is an explicitly authorized audited action, not a data-API decrypt. The built-in
encrypted development/small-operator option remains adopted; production adapters
must meet the same contract. A disposable Vault lab does not establish TLS,
unseal/recovery, production identity, HA or operational suitability. Failures
never fall back to plaintext, another tenant's key or an unapproved signer.

## Tenant identity, migrations and import

Keep disposable public aliases, durable DNS-friendly internal names and stable
tenant IDs distinct. Deployment-owned mapping binds internal name to ID; alias
rotation does not recreate a tenant or transfer credentials/data. DNS discovery
is not authority. Preserve direct-alias mode and make canonical ingress explicit:
only trusted transport may supply the configured internal selector; forwarded
public aliases cannot override it. Conflicting/spoofed selectors and trust loss
refuse. Durable allocation, collision, rename/reassignment/deletion and mapping
consistency require explicit contracts before operator-writer admission. Consul,
Kubernetes and vendor discovery are optional adapters, not dependencies adopted
by this roadmap. Public domains, certificates and private edge implementation
remain deployment concerns.

Multitenant schema migration is **explicit operator execution**. Serving checks
compatibility read-only and refuses stale/unsafe schema; it never migrates at
boot. Keep committed catalogue bytes/checksums immutable. Two-store runner
acceptance covers locks/leases, fencing, ledger/drift, crash/restart and supported
steps; standalone/index/quiescence and chunking guarantees need their own gates.
This does not alter the separately decided single-site boot behavior.

The source-Nightscout API importer is one-time database population, not schema
migration over HTTP or ongoing synchronization. Bounded pagination and duplicate-safe
reruns start from the beginning; a durable checkpoint is not required. Offset
pagination plus `srvModified` history is best-effort, not a point-in-time snapshot.
Hard deletes can leave stale or missing target rows, legacy rows may lack history,
and API projections may omit stored fields. Preserve ObjectId/string distinction
and refuse ambiguous repeated textual IDs; accept JSONB logical equality without
claiming BSON field-order fidelity. This importer is not a raw backup.
`nightscout-connect` remains the separate ongoing synchronization path.

Apply the [restore identity and cloning decision](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#restore-identity-and-cloning).
Operational restore labs retain original-tenant bindings. Clinical API population
and synchronization do not migrate credential authority. Cloning implementation
and native acceptance remain UNMEASURED.

## Milestones and continuous integration

[R72](../remedial/rc-16.0.0-integration-record.md#r72---admitted-entries-and-owner-configuration-completion-batch-2026-11-06)
records the latest criterion verdicts; the [dashboard](multitenant-delivery-dashboard.md)
displays milestone claims. The criteria below retain their adopted scope.

The [release promotion decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#multitenant-promotion-bars-2026-11-06)
fix the scope of these bars. In particular, M2 is its table cell; human
issuer/refresh, existing-grant clamping, full lifecycle and production-resolution
trust belong to M6. Numeric resource/performance budgets are deferred to C;
M1 may promote with that deferral stated. The PostgreSQL sort-key cap remains 5,
an intentional PG-only difference. No threshold is invented by a passing lab.

| Milestone | Build / dependencies | Acceptance before promotion |
|---|---|---|
| M0: foundations | Current-dev integration; PG transaction binding and RLS; migration/secrets contracts may proceed independently | Non-bypass application role, overlapping IDs, unbound reader, read/write isolation, rollback/error cleanup, demonstrated pool reuse and paired breaks. No default or production role enabled; explicit D21 lab preview permitted. |
| M1: entries adapter | ST-PG on M0; current filter/read/write/identity contracts; reviewed DDL through MIG-RUNNER | Applicable backend tests execute against both stores; no pending-as-pass. Explicit unsupported collections/operations. Null, ordering/pagination, resend/delete and batch outcomes; preserve source labels/events. Reviewed import contract and populated identity/order fidelity. Resource bounds may be explicitly deferred to C by the adopted decision. |
| M2: tenant control plane | MT-CONFIG-MIN, MT-SECRETS-CONTRACT, MIG-RUNNER, TEN-RESOLVE, T30-WIRING | Tenant-local effective config and versioned writes; unknown tenant refuses; A token works on A and fails on B by signature; no environment/root/key leakage; separate owner/data/operator routes. |
| M3: two-tenant HTTP lab | Complete M1 + M2; TEN-LAB | Actual authorized entries-v3 requests and independent stored outcomes for both tenants, positive/negative controls; startup refuses stale/unsafe schema. A bounded lab alone is not the complete multitenant preview. |
| M4: existing-client surface | M3; further collections and v1/storage wiring, v2 exchange, tenant-local history/indexes | Executed headless clients plus source-pattern replay for the rest, pinned uploader/follower shapes, no coordinated client upgrade, tenant-local identity and correct batch/retry/refusal semantics. State explicitly that this is not an all-client claim. Android emulator acceptance is in C; iOS execution is outside the automated lab. |
| M5: realtime and evaluator | MT-RUNTIME-PLAN; computed views; durable interprocess delivery/recovery; settings/secrets consumers | Socket authorization/reconnect/write compatibility, tenant-local rooms/caches, replay-equivalent views, durable ack/snooze and restart/double-delivery checks. Live notification acceptance is separate. |
| M6: multitenant preview | M4 + M5 + chosen owner capabilities and operations | Human issuer/refresh, compatible current-authority/lifecycle completion and production-resolution trust; export/deletion/import fidelity, recoverable keys/ciphertext, backup/restore, upgrade/rollback, approved resource/egress bounds and final-tree review. Real-data/identity acceptance and role enablement require explicit approval. |

CI is cumulative: keep default single/Mongo tests green and run explicit PG suites
as they become applicable. Publish pending/unsupported inventory. Each isolation
property needs positive own-tenant behavior and a meaningful red control against
the actual implementation. A component pass is not a parent milestone pass.

Use the adopted [durable event contract](durable-event-delivery-contract-2026-11-06.md)
for D6/D-EVENT reconciliation. A process-local event is not a durable bus. Before
consumer admission, prove commit coupling, durable checkpoints, ordering, complete
cohorts, duplication/deletion/config invalidation and crash/replay boundaries.
The event carries the transaction's **final floor**, as decided in the
[B7 record](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#b7-durable-multitenant-delivery-2026-11-06).
Time-only ticks drive time-based alarms. The separately scheduled bounded snapshot
reconciliation recovers current rows and absence after missed wakes; neither
mechanism promises recovery of every intermediate transition.
D23 forwards socket writes/acks unchanged from the reader `realtime` role to the
internal `api` write endpoint with the `socket` source label; client behavior and
current authority must be measured at that boundary. Failed forwarding yields
no acknowledgement so the existing client no-ack retry applies.

For deletion, the adopted retention decision keeps Transit keys and the export
artifact for a 30-day window, then an operator destroys the keys. The artifact
must contain every ciphertext/key reference before secret/audit rows are removed.
The decision is in the [promotion record](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#multitenant-promotion-bars-2026-11-06);
implementation and destroy/after-window refusal evidence remain separate.

## M5/M6 acceptance families

These refine the milestone cells above into observable results. They are required
coverage, not new passing measurements. The coordinator records actual source,
command, control, artifact and verdict per family on the assembled candidate.
A deferred enhancement is named explicitly; it does not silently lower another bar.

| Family | Required observable result |
|---|---|
| M5 current-state recovery | Bounded full typed identity/absence reconciliation in one consistent tenant snapshot recovers hard deletes and unstamped activity after missed wakes/restart and at an unchanged floor. Preserve producer timestamps and replies. Concurrent paging cannot combine snapshots; foreign tenant state is unchanged. Row/byte/transaction failure refuses without partial projection/checkpoint replacement. |
| M5 evaluator recovery | The actual evaluator consumes recovered inputs. Acquisition or commit failure preserves last good state; downstream clinical failure may leave newer committed inputs while retaining the prior clinical result/time. A later cycle retries computation even at an unchanged floor. Settings/plugin-version changes cannot reuse an incompatible result. Do not claim atomic input-plus-clinical-output persistence. |
| M5 live reference | Separate roles on one machine exercise subscription startup races, missed/duplicate wakes, process death/restart and explicit scheduling. Time-only alarm ticks and current-state reconciliation are distinct work. A transport wake is not delivery evidence; a checkpoint lock is not a multi-node lease. |
| M5 socket compatibility and authority | Actual D23 API forwarding preserves namespace, source, replies and ack/no-ack retry behavior; realtime has no storage-write authority. Current authorization covers operations, reconnect and protected delivery. Tenant rooms/caches and settings invalidation remain isolated. |
| M5 durable alarm state | Apply the [adopted tenant-wide group/level suppression contract](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#tenant-wide-alarm-suppression): API-persisted state and original expiry survive restart, active-window repeats do not extend suppression, and existing default/level effects remain. No indefinite post-expiry deduplication is inferred from the unchanged client protocol. Exercise persistence failure and restart boundaries against actual client behavior. Live external notification delivery remains a separate gate; enabled durable request handoff needs its own crash/retry oracle. |
| M5 durable notification handoff | Apply the [durable request/retry decision](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#durable-notification-requests-and-retries): tenant-bound intent persisted before dispatch, stable identity across restart/ambiguous retry, no new request from a failed cycle. Verify joined notification consumers for ordinary alarm, snooze/repeat window, restart, ambiguous acceptance, foreign authority/configuration and shutdown. Preserve normal dedup/suppression and single behavior. Distinguish possible duplicate external effects from duplicate clinical records; uploader compatibility is not notification acceptance. Live provider/device delivery remains separate. |
| M6 bounded owner API | Declare the exact reviewed configuration/credential/integration catalogue and refusals. Shared optional OIDC/provider-backed renewal provides equivalent single/multitenant human authentication with separate authority adapters; single opt-in prefers `ENABLE=oidc`. Human issuer/renewal implements adopted lifetimes, current authority, reauthentication and cross-worker revocation through synthetic identities. Enabled/disabled parity and legacy-client controls are required. Provider logout, idle activity and outage behavior require explicit contracts; operator-provisioned credentials alone do not close human identity. |
| M6 operator-assisted ownership | Private-operator addition/transfer/recovery is tenant-bound, explicit and audited. Concurrent changes cannot orphan a tenant or silently replace an owner; unauthorized operations have no effect. Recovery grants no automatic secret reveal. Self-service co-owner/transfer is not a preview gate. |
| M6 lifecycle and trust | Provision/suspend/export/delete and restore respect current authority and trusted tenant resolution. Artifact fidelity is independently checked; capture required ciphertext/key references before deletion. Exercise retained-key recovery, operator destruction and after-window refusal. Same-ID restore and new-secret cloning remain distinct. Deletion request/confirmation/cancellation policy needs an explicit answer. |
| M6 operations and clients | Populated backup/restore and upgrade/rollback cover interruption, supported schema/catalogue and failure recovery on the assembled tree. Retain the Android emulator acceptance and the explicit iOS/all-client exclusions. A representative entries/clock lab does not cover the whole catalogue. |
| M6 operating envelope and final review | Declare synthetic workload and freshness/recovery expectations, then measure shared-pool/hot-tenant interference, row/byte limits, scan cadence, latency and egress refusal before approving bounds. Complete the final criterion matrix and review. Functional passes do not establish capacity. |

M5 reconciliation implementation may proceed now; it does not depend on selecting
an external notification provider or retained history. Multi-node failover,
every-transition history and self-service ownership are separate enhancements.
Real identities/data, production/default role enablement and release admission keep
their existing explicit approval boundaries.

## Compatibility and parallel contracts

| Direct comparison | Purpose |
|---|---|
| Released single/Mongo vs current dev | Explain intentional RC corrections, defined edge cases and preserved client quirks through release decisions/register |
| Current dev vs PR single/Mongo | Detect shared seam/composition regressions independently of PG differences |
| PR single/Mongo vs PR multitenant/PG | Exercise admitted routes, stored outcomes, identity, isolation and current authority directly |
| Pinned client workflow vs each applicable endpoint | Exercise ordinary handshake/read/write/retry/refusal, defaults, ordering, batch and delete/history behavior |

Every case identifies its client/source pin, endpoint/settings, expected observable
behavior, allowed incidental normalization and intended-change basis. Compare
logical contents, status/headers, identity, per-item replies and history; retain
omitted/null/zero/false and failure-category distinctions. Classify unchanged,
intended RC correction, preserved quirk, explicit unsupported capability,
unexpected regression or unmeasured. An unclassified difference fails. A broad
allowlist or a transitive old-release-to-PG inference is not acceptance. Index-off
duplicate fixtures and index-on/race campaigns retain separate scope.

Registration/instance identity, typed commands and delegation contracts may advance
independently. Their runtime admission still needs tenant storage, authorized
owner/action routing, registered destinations where required, durable state,
idempotency/reconciliation and reviewed human/delegated authority. Device tokens
do not implicitly grant command authority. These tracks and optional OIDC research
are not blanket prerequisites to the initial storage/HTTP lab or v1/v3 compatibility.
The hub observes/routes; the AID controller owns dosing decisions/reconciliation.

## Retained execution evidence

The [archived delivery journal](../../archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md)
retains the original dispatches, acceptance commands, failed experiments, controls,
capacity holds and source-scoped checkpoints. It describes its captured period,
not today's assignment or acceptance. Its unique evidence remains retrievable;
future measurements belong in the integration/release records, and current
coordination belongs in the dashboard and completion schedule.
