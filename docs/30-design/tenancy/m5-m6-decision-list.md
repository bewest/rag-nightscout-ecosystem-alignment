# M5/M6: current decisions and next review

*Living contributor-facing decision index, 2026-11-09. Read this before older
question packets. Release decisions own adopted policy; the roadmap owns
acceptance; the queue/dashboard own claimed work/milestone state. This index
records no new application measurement or promotion.*

## Execute now

**2026-11-09 restructure.** M6 is now M6a identity and owner API, M6b lifecycle and keys,
M6c deployment trust (in `nightscout-deploy`), M6d connector sync, and M7 production
readiness ([decision](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#m6-split-and-queue-collapse)).
The owner/OIDC native matrix runs through a disposable harness (`MT-OIDC-NATIVE`); the
grant/reservation ceremony is retired. Vault connectivity is a Vault Agent sidecar
(`DEPLOY-VAULT-AGENT`) plus a `tokenFile` read in core (`MT-VAULT-TOKEN-FILE`). The
umbrella queue items are closed as superseded; one capability item per remaining gap.


The functional M5 reference on one host is accepted in [R73](../remedial/rc-16.0.0-integration-record.md#r73-durable-runtime-operations-batch). It includes
bounded current-state/evaluator recovery, durable alarm/request state and actual
reference-role/browser consumers, with accepted final comprehensive verification.
Publication and remote CI retain their separate records; production/default
admission and live provider/device delivery are not implied.

Reuse the [recorded proof gates](multitenant-delivery-roadmap.md#current-bounded-proof-and-remaining-admission)
for source-identical evidence instead of repeating native cases for documentation
changes. New source behavior still needs affected checks and an appropriate joined
verification. Do not silently add later provider, capacity or multi-node work to
the satisfied M5 functional bar.

M6 now includes [accepted native tenant-local restore/restart and cold Compose
reference evidence](../../../reports/tenancy/operation-window-acceptance-2026-11-07/README.md).
The published ed2 candidate closes that bounded clinical restore capability;
restoring or cloning credentials/identity is a separate contract. Shared human
identity/session and owner source has progressed locally, while signed native
DB/Vault/HTTPS/browser acceptance remains **UNMEASURED** in the
[release update](../../../releases/cgm-remote-monitor-16.0.0/contents.md).
Continue that acceptance, operator-assisted ownership, retained-key destruction
and workload-based operating limits. The
[completion schedule](multitenant-integration-batching-plan-2026-11-06.md#5-current-completion-schedule-adopted-2026-11-06)
owns assignments; the [roadmap acceptance families](multitenant-delivery-roadmap.md#m5m6-acceptance-families)
own observable completion. Prefer a minimal working base with explicit later
enhancements; that preference grants no production permission or criterion waiver.

## Settled: do not ask again

| Topic | Canonical home / implementation boundary |
|---|---|
| Supported PostgreSQL writers | [Exclusive application ownership](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#exclusive-application-postgres-ownership): declared internal components and admitted maintenance tools cooperate on write/lifecycle contracts; external direct writers are unsupported with undefined behavior. The [database ownership map](sql-and-migration-architecture.md#component-ownership-and-internal-application-apis) defines command and persistence boundaries. Cooperating replicas remain possible; Kubernetes scale-out acceptance is separate. |
| Current-state recovery | [Bounded full snapshot reconciliation first](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#m5-bounded-snapshot-reconciliation); preserve producer deletes/timestamps/replies. Cadence/capacity is measurement work. No every-transition promise. |
| Shared human authentication | [Shared optional OIDC, provider-backed renewal first](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#shared-oidc-provider-renewal), equivalent single/multitenant support; preferred single opt-in `ENABLE=oidc`. Separate authorization adapters; no implicit root/management grant. |
| OIDC provider outage | [Existing valid access until existing expiry](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#oidc-provider-outage-existing-access), with current local authority/session checks, no new login or renewal and unchanged sensitive-action freshness. Equivalent optional single/multitenant behavior; provider-only revocation may remain unknown until expiry/recovery. Local implementation exists; signed native outage acceptance remains UNMEASURED. |
| Alarm suppression scope and restart | [Tenant-wide group/level suppression](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#tenant-wide-alarm-suppression), original expiry retained across restart, active-window repeats do not extend it. Per-user/device scope follows separately. |
| Notification retry responsibility | [Persist request intent before dispatch; retry same identity](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#durable-notification-requests-and-retries). Preserve suppression/dedup/single behavior; joined notification-consumer verification required. No exactly-once external delivery claim. |
| Deletion ceremony | [Explicit request + operator confirmation; cancellable before execution; no mandatory wait](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#preview-deletion-confirmation). Post-deletion 30-day key/artifact retention remains separate. |
| First-preview ownership changes | [Operator-assisted](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#preview-operator-assisted-ownership); self-service co-owner/transfer follows separately. Last-owner, current authority, audit and secret boundaries remain required. |
| Same-ID restore history | [Publish ordinary forward updates and deletions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#restore-history-forward-correction), preserving issued history floors and client convergence. Exact physical backup fidelity remains separate. Initial reconciliation covers identities retained live or in the artifact; prior hard purges absent both retain the existing history limitation. Published ed2 cold Compose and client acceptance now cover the bounded forward-history behavior; see the operation-window evidence above. |
| Restore versus cloning | [Restore original tenant ID; clone establishes new secrets/credentials](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#restore-identity-and-cloning). Clinical sync does not transfer credential authority. |
| Deleted-tenant keys/artifact | [Retain 30 days, then operator destroys keys](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#tenant-deletion-key-retention). Destroy/after-window refusal still needs evidence; this does not set a deletion cancellation period. |
| Tenant-local restore and ordering | [Per-tenant/collection ordering only; pursue tenant-local insertion state](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#tenant-local-insertion-semantics). Preserve other tenants' current state and supported client ordering. [Standalone native proof](../../../reports/tenancy/tenant-local-insertion-2026-11-07/README.md) retains its early SQL scope; later c23 native and ed2 packaged restore evidence covers the admitted fixed-cohort reference. No global restore pause selected. |
| First-preview owner surface | [Projected display catalogue](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#owner-settings-projected-catalogue), [bounded owner thresholds and alarm enables](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#owner-alarm-thresholds), [single-tenant-equivalent credentials, wildcards accepted as single tenant accepts them, under the operator ceiling](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#owner-credentials-single-tenant-equivalent), [tightening applies to both and is a separate proposal](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#permission-tightening-applies-to-both), [no owner integrations yet](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#owner-integrations-none-first-preview). D22 floors stand. Implementation and consuming-runtime tests remain open. |
| First-preview external delivery | [No live push provider; Nightscout-to-Nightscout sync via nightscout-connect in both directions, outbound first](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#first-preview-no-push-provider); [per-kind operator/owner credential parts](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#integration-credential-parts); [single-tenant constants as first bounds](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#notification-bounds-single-tenant-constants); [admission by probes and lab sync](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#external-delivery-admission-by-probe). Pushover/Maker deferred. Connector actor and lab sync remain open. |
| M6 human session effects | [Idle/absolute lifetimes scoped to management sessions only; always-on displays unchanged](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#human-session-idle-scope-management-only); [local-first logout, provider optional, signal-less providers admitted with disclosure](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#human-session-logout-local-first); [fenced idempotent renewal](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#human-session-renewal-fenced); [both browser transports, HttpOnly cookie default, headless bearer unchanged](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#human-session-transport-cookie-default). Local signed source exists; actual joined native/browser/provider acceptance remains UNMEASURED. |
| M6 deployment and trust | [Peer-list ingress trust, one list for tenant selection and client IP](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#deployment-ingress-peer-list-trust); [Vault Transit at every stage, service-login adapter before production](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#deployment-secrets-ladder-vault-all-stages); [generic OIDC adapter, Authentik intended reference subject to the Kratos proof](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#deployment-identity-generic-adapter-authentik-reference); [admission by trust record plus live probes](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#deployment-admission-probes-and-trust-record). Synthetic Compose edge/TLS Vault is measured at the reference scope; provider/service-login proof and production deployment remain UNMEASURED. |
| Legacy authority and management split | [Reader clamp withdrawn; preserve own-tenant credentials](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#multitenant-promotion-bars-2026-11-06); [owner authority](owner-authority.md) governs separate management audience, current authority and adopted lifetimes. |
| Socket writer and recovery direction | [D23](multitenancy-decisions.md#d23): realtime forwards to API with existing protocol/source; failure gives no acknowledgement. First runtime proof uses separate roles on one machine. No multi-node lease claim. |

## Human policy review

These are bounded topics for a concrete proposal, not blanket implementation stops.
A recommendation remains a proposal until recorded in release decisions.
Shared OIDC/provider-backed renewal, bounded existing access during provider outage
and tenant-wide alarm suppression are adopted.
Review remaining session effects and operational parameters while implementation continues.
Notification retry responsibility and deletion ceremony policy are settled. Their
bounded proofs do not resolve live-provider admission or wider M6 identity/trust.
The first-preview owner surface (settings, thresholds, credentials, integrations) is settled.
The first-preview external delivery channel (no push provider; Nightscout-to-Nightscout sync) is settled.
M6 human session effects (idle scope, logout, renewal, transport) are settled.
M6 deployment and trust (ingress peer-list trust, one-provider secrets ladder, generic OIDC adapter with Authentik as intended reference, probe-plus-record admission) are settled.
Vault Agent scope is settled: [one AppRole per deployment](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#vault-one-approle-per-deployment); tenant separation at Vault is not a goal.
Evaluator partitioning is settled in direction: [member count and ordinal flag with a pool-membership table](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#evaluator-static-partition).

The following topic is open; it does not reopen the settled choices above.

| Topic | Decision needed / source mechanism | Work that need not wait |
|---|---|---|
| Operator activity/resource policy vs recovery admission (multitenant) | [Tenant-admission review](tenant-admission-and-activity.md) records the proposed separation of desired activity, claim-bound maintenance state and observed health. Decide inactive behavior per serving/ingest/evaluator/connector capability, transition authority and how it composes with existing pause/suspend semantics. Source `operation-window.js:87–91` checks maintenance phase; `evaluator-runtime.js:101,152–154` iterates configured tenants. The proposal is read-derived; no new policy/schema or full inactive-resource behavior is accepted. | Endpoint transport and fixed-roster APIs preserve existing admission/drain/invalidation. Existing owner/OIDC and lifecycle work can proceed within adopted contracts. Policy-specific consumer/schema changes wait for a bounded decision. |

The [owner lifecycle packet](owner-lifecycle-decision-packet-2026-11-06.md)
retains source surveys and alternatives; its recommended grace periods, invitation
lifetimes and self-service operations are not approved defaults. The [earlier
open-decision note](multitenant-open-decisions-2026-11-06.md) preserves already
answered A questions, not the current backlog.

The [counter and restore options analysis](counter-and-restore-options.md)
separates the tenant-local history clock from internal insertion order. The
tenant-local insertion prototype removes cross-tenant allocation state while
preserving supported per-tenant order; exact physical and logical backup fidelity
retain their separate contracts.

## From preview to production

The [production critical path](production-critical-path.md) maps these adopted
requirements to closing evidence and conditional topology choices. It separates
M6 completion, a coherent released candidate and per-deployment production
admission. Its proposed one-cohort scope and HA deferrals are not adopted policy.

## Measure before setting limits

Decision 2026-11-09 ([row](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#m7-envelope-measured-not-declared)):
the envelope is measured first, not declared. `MT-BENCH-BASELINE` benchmarks the
one-host reference at stepped synthetic tenant counts with a hot tenant and
publishes p50/p95/p99 latency, socket fanout, evaluator cycle time, pool/lock
waits, CPU and memory per role, disk per tenant-day and reconnect recovery.
`MT-BENCH-CONTRAST` runs the same workload against the shapes operators run today
(N single-tenant Mongo processes; the per-site process model) and reports the
comparison side by side. `MT-SCALE-UNBOUND` proves each component scales
horizontally or vertically as intended and itemises any binding with `file:line`.
Limits, polling cadence and replay horizons are then set from those numbers.
Use the [experiment contract](durable-event-delivery-contract-2026-11-06.md#11-maintainer-acceptance-and-experiments)
for oracle and control design. Nothing here is a prerequisite to current
correctness work, and no number is invented from functional passes.

## Reviewing and closing a topic

Bring one topic with current code anchors, user/operator effect, compatibility,
recommendation, alternatives, reproduced evidence and named unknowns. Record the
answer once in release decisions, link it here, and update the acceptance family.
Do not add per-commit journals. The coordinator maps each required family to an
actual source/command/artifact/verdict and records any explicit deferral before
milestone promotion. M5/M6, real-data/identity admission and production/default
role enablement remain separate claims.
