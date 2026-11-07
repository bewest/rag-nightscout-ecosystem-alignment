# M5/M6: current decisions and next review

*Living contributor-facing decision index, 2026-11-06. Read this before older
question packets. Release decisions own adopted policy; the roadmap owns
acceptance; the queue/dashboard own claimed work/milestone state. This index
records no new application measurement or promotion.*

## Execute now

M5's existing implementation lane owns bounded current-state reconciliation,
actual evaluator consumption and failure recovery. Continue focused source checks,
then reviewed native positives and mechanism-specific red/restored controls.
Integrate live reference roles/forwarding and durable alarm state in coherent
capability batches; freeze one assembled candidate for comprehensive acceptance.
The [completion schedule](multitenant-integration-batching-plan-2026-11-06.md#5-current-completion-schedule-adopted-2026-11-06)
owns assignments; the [roadmap acceptance families](multitenant-delivery-roadmap.md#m5m6-acceptance-families)
own observable completion. Component recovery does not close all of M5.

Prepare M6 synthetic lifecycle/operations and bounded owner contracts in parallel.
Prefer a minimal working base with explicit incremental enhancements. Do not infer
production permission or waive an existing criterion from that preference.

## Settled: do not ask again

| Topic | Canonical home / implementation boundary |
|---|---|
| Current-state recovery | [Bounded full snapshot reconciliation first](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#m5-bounded-snapshot-reconciliation); preserve producer deletes/timestamps/replies. Cadence/capacity is measurement work. No every-transition promise. |
| First-preview ownership changes | [Operator-assisted](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#preview-operator-assisted-ownership); self-service co-owner/transfer follows separately. Last-owner, current authority, audit and secret boundaries remain required. |
| Restore versus cloning | [Restore original tenant ID; clone establishes new secrets/credentials](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#restore-identity-and-cloning). Clinical sync does not transfer credential authority. |
| Deleted-tenant keys/artifact | [Retain 30 days, then operator destroys keys](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#tenant-deletion-key-retention). Destroy/after-window refusal still needs evidence; this does not set a deletion cancellation period. |
| Legacy authority and management split | [Reader clamp withdrawn; preserve own-tenant credentials](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#multitenant-promotion-bars-2026-11-06); [owner authority](owner-authority.md) governs separate management audience, current authority and adopted lifetimes. |
| Socket writer and recovery direction | [D23](multitenancy-decisions.md#d23): realtime forwards to API with existing protocol/source; failure gives no acknowledgement. First runtime proof uses separate roles on one machine. No multi-node lease claim. |

## Human policy review

These are bounded topics for a concrete proposal, not blanket implementation stops.
A recommendation remains a proposal until recorded in release decisions.
The next human discussion is the minimal session-renewal base; M5 alarm-state
proposals and current recovery implementation can proceed in parallel.

| Topic | Decision needed | Work that need not wait |
|---|---|---|
| M5 durable ack/snooze | Define suppression scope/effect, original expiry, duplicate/retry behavior and retained evidence. Start from actual legacy client behavior; flag any observable change. Storage layout is an engineering choice once effects are agreed. | Reconciliation, evaluator acquisition, D23 forwarding/current authority and isolated reference scheduling. |
| M5 notification handoff | Define durable request identity and crash/retry responsibility before enabling handoff; separate request persistence from delivery to a device. Select a provider only when its enabled capability needs it. | Current-state recovery; synthetic handoff experiments. Do not promise exactly-once external effects. |
| M6 human session renewal | Choose provider-supported re-exchange versus Nightscout-held rotating refresh credentials. Specify upstream logout propagation, provider outage, qualifying activity and concurrent renewal. Existing adopted lifetimes and next-operation current-authority checks remain. | Adapter/session prototypes with synthetic identities and refusal controls; no custom password/recovery system. |
| M6 bounded owner surface | Approve the exact first-preview settings, credentials and enabled integrations; identify unsupported names/operations. Operator-assisted ownership is settled. | Census and proposed catalogue with consuming-runtime tests; do not silently declare the full catalogue implemented. |
| M6 deletion ceremony | Set request confirmation/cancellation and operator recovery procedure. Distinguish pre-deletion cancellation from adopted post-deletion key retention. | Synthetic export/delete/recovery tooling and artifact-fidelity controls. |
| M6 deployment/trust | Review concrete trusted-ingress and secrets/identity adapter contracts for the reference deployment before production use. | Synthetic spoof/conflict/outage probes and provider-neutral interfaces. |

The [owner lifecycle packet](owner-lifecycle-decision-packet-2026-11-06.md)
retains source surveys and alternatives; its recommended grace periods, invitation
lifetimes and self-service operations are not approved defaults. The [earlier
open-decision note](multitenant-open-decisions-2026-11-06.md) preserves already
answered A questions, not the current backlog.

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
