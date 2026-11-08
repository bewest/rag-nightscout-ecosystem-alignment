# M5/M6: current decisions and next review

*Living contributor-facing decision index, 2026-11-07. Read this before older
question packets. Release decisions own adopted policy; the roadmap owns
acceptance; the queue/dashboard own claimed work/milestone state. This index
records no new application measurement or promotion.*

## Execute now

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

M6 has bounded SQL operations evidence. Continue shared human identity/session
contracts, operator-assisted ownership, full suspension and identity-bearing
same-ID restore, key destruction and workload-based operating limits. The
[completion schedule](multitenant-integration-batching-plan-2026-11-06.md#5-current-completion-schedule-adopted-2026-11-06)
owns assignments; the [roadmap acceptance families](multitenant-delivery-roadmap.md#m5m6-acceptance-families)
own observable completion. Prefer a minimal working base with explicit later
enhancements; that preference grants no production permission or criterion waiver.

## Settled: do not ask again

| Topic | Canonical home / implementation boundary |
|---|---|
| Current-state recovery | [Bounded full snapshot reconciliation first](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#m5-bounded-snapshot-reconciliation); preserve producer deletes/timestamps/replies. Cadence/capacity is measurement work. No every-transition promise. |
| Shared human authentication | [Shared optional OIDC, provider-backed renewal first](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#shared-oidc-provider-renewal), equivalent single/multitenant support; preferred single opt-in `ENABLE=oidc`. Separate authorization adapters; no implicit root/management grant. |
| OIDC provider outage | [Existing valid access until existing expiry](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#oidc-provider-outage-existing-access), with current local authority/session checks, no new login or renewal and unchanged sensitive-action freshness. Equivalent optional single/multitenant behavior; provider-only revocation may remain unknown until expiry/recovery. Implementation and outage acceptance remain open. |
| Alarm suppression scope and restart | [Tenant-wide group/level suppression](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#tenant-wide-alarm-suppression), original expiry retained across restart, active-window repeats do not extend it. Per-user/device scope follows separately. |
| Notification retry responsibility | [Persist request intent before dispatch; retry same identity](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#durable-notification-requests-and-retries). Preserve suppression/dedup/single behavior; joined notification-consumer verification required. No exactly-once external delivery claim. |
| Deletion ceremony | [Explicit request + operator confirmation; cancellable before execution; no mandatory wait](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#preview-deletion-confirmation). Post-deletion 30-day key/artifact retention remains separate. |
| First-preview ownership changes | [Operator-assisted](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#preview-operator-assisted-ownership); self-service co-owner/transfer follows separately. Last-owner, current authority, audit and secret boundaries remain required. |
| Same-ID restore history | [Publish ordinary forward updates and deletions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#restore-history-forward-correction), preserving issued history floors and client convergence. Exact physical backup fidelity remains separate. Initial reconciliation covers identities retained live or in the artifact; prior hard purges absent both retain the existing history limitation. Actual commit publication and client acceptance remain open. |
| Restore versus cloning | [Restore original tenant ID; clone establishes new secrets/credentials](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#restore-identity-and-cloning). Clinical sync does not transfer credential authority. |
| Deleted-tenant keys/artifact | [Retain 30 days, then operator destroys keys](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#tenant-deletion-key-retention). Destroy/after-window refusal still needs evidence; this does not set a deletion cancellation period. |
| Tenant-local restore and ordering | [Per-tenant/collection ordering only; pursue tenant-local insertion state](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#tenant-local-insertion-semantics). Preserve other tenants' current state and supported client ordering. [Standalone native proof](../../../reports/tenancy/tenant-local-insertion-2026-11-07/README.md) passes its bounded SQL bar; migration-runner/readiness/lifecycle admission remains open. No global restore pause selected. |
| First-preview owner surface | [Projected display catalogue](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#owner-settings-projected-catalogue), [bounded owner thresholds and alarm enables](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#owner-alarm-thresholds), [single-tenant-equivalent credentials, wildcards accepted as single tenant accepts them, under the operator ceiling](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#owner-credentials-single-tenant-equivalent), [tightening applies to both and is a separate proposal](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#permission-tightening-applies-to-both), [no owner integrations yet](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#owner-integrations-none-first-preview). D22 floors stand. Implementation and consuming-runtime tests remain open. |
| First-preview external delivery | [No live push provider; Nightscout-to-Nightscout sync via nightscout-connect in both directions, outbound first](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#first-preview-no-push-provider); [per-kind operator/owner credential parts](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#integration-credential-parts); [single-tenant constants as first bounds](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#notification-bounds-single-tenant-constants); [admission by probes and lab sync](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#external-delivery-admission-by-probe). Pushover/Maker deferred. Connector actor and lab sync remain open. |
| M6 human session effects | [Idle/absolute lifetimes scoped to management sessions only; always-on displays unchanged](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#human-session-idle-scope-management-only); [local-first logout, provider optional, signal-less providers admitted with disclosure](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#human-session-logout-local-first); [fenced idempotent renewal](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#human-session-renewal-fenced); [both browser transports, HttpOnly cookie default, headless bearer unchanged](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#human-session-transport-cookie-default). Login/session implementation and acceptance remain open. |
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
M6 human session effects (idle scope, logout, renewal, transport) are settled; deployment/trust remains.

| Topic | Decision needed | Work that need not wait |
|---|---|---|
| M6 deployment/trust | Review concrete trusted-ingress and secrets/identity adapter contracts for the reference deployment before production use. | Synthetic spoof/conflict/outage probes and provider-neutral interfaces. |

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

## Measure before setting limits

Operations owners first propose representative active/idle tenant counts, stored
rows/bytes, ingestion bursts, reconnect backlog and a hot tenant sharing the pool.
Agree freshness and recovery expectations, then measure scan/lock/pool costs,
p50/p95/p99 latency, retained bytes, failure behavior and bounded egress. Use the
[experiment contract](durable-event-delivery-contract-2026-11-06.md#11-maintainer-acceptance-and-experiments).
Do not invent numeric capacity, polling cadence or a replay horizon from functional
passes. The coordinator assigns one controlled benchmark window after the workload
and candidate are stable; it is not a prerequisite to current correctness work.

## Reviewing and closing a topic

Bring one topic with current code anchors, user/operator effect, compatibility,
recommendation, alternatives, reproduced evidence and named unknowns. Record the
answer once in release decisions, link it here, and update the acceptance family.
Do not add per-commit journals. The coordinator maps each required family to an
actual source/command/artifact/verdict and records any explicit deferral before
milestone promotion. M5/M6, real-data/identity admission and production/default
role enablement remain separate claims.
