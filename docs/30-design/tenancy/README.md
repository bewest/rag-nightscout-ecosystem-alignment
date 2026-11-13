# Tenancy: what to read and maintain

*Contributor-facing living reading guide, current with the release decisions of
2026-11-12. Each document below owns one kind of fact; it links to the others
rather than restating them. [Release decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md)
own adopted policy, the [queue](../../../queue/work-queue.yaml) owns claimed item
state and the [release contents](../../../releases/cgm-remote-monitor-16.0.0/contents.md)
own merges, acceptance and publication. Retired journals, answered packets and
superseded analyses are in the [tenancy archive](../../archive/tenancy/README.md);
a date in a filename does not establish currency.*

For an outsider's first reading, start with [runtime topology](runtime-topology.md)
for reusable roles and scale envelopes, [deployment bindings](deployment-bindings-and-public-names.md)
for configuration and trust, then [production sequencing](production-critical-path.md)
for evidence and admission. The release record is a journal of executed work, not
the architecture explanation.

For a diagram-first review, open the [multitenant database and component ownership
page](../../../site/pages/multitenant-database-design.html), rendered from the SQL
guide below.

## State, sequencing and decisions

| Document | Owns |
|---|---|
| [Delivery dashboard](multitenant-delivery-dashboard.md) | Generated milestone claims and the acceptance ledger. Edit the queue and `multitenant-delivery-status.json`, then `make queue`. |
| [Delivery roadmap](multitenant-delivery-roadmap.md#milestones-and-continuous-integration) | Delivery boundaries and the M0–M5, M6a–M6d and M7 promotion criteria. |
| [Completion schedule](multitenant-integration-batching-plan-2026-11-06.md#5-current-completion-schedule-adopted-2026-11-06) | Batch sequence, lane ownership and [completion-focused coordination](multitenant-integration-batching-plan-2026-11-06.md#completion-focused-coordination). |
| [M5/M6 decision index](m5-m6-decision-list.md) | Every settled policy topic with its decision row; no human-policy topic is open. |
| [Production critical path](production-critical-path.md) | Production closure criteria, diagnostic/acceptance sequencing and conditional topology/HA decisions; current blockers remain in the queue/release records. |

## Decisions and contracts

| Document | Owns |
|---|---|
| [Tenancy decisions](multitenancy-decisions.md#1-decisions) | D1–D23, hard qualifications, pause/suspend meanings and the operator listener rule. |
| [Owner authority](owner-authority.md) | Owner, root (`API_SECRET`) and admin-tool authority, token verification, shared optional OIDC and management lifetimes. |
| [Tenant admission and activity](tenant-admission-and-activity.md) | The REST component boundary, restore-aware APIs and the adopted pause/suspend activity policy with its acceptance criteria. |
| [Durable event contract](durable-event-delivery-contract-2026-11-06.md#11-maintainer-acceptance-and-experiments) | B7 consumer, checkpoint and recovery rules and the experiment contract. |
| [Write contract §9](write-contract-spec-2026-10-07.md#9-current-shared-intent-and-backend-capabilities-2026-11-05) | Current admitted write implementation; earlier sections keep their baseline. |
| [Storage seam §11](nightscout-storage-seam-interface-2026-09-14.md#11-current-admitted-ports-and-independent-scopes-2026-11-05) | Current admitted ports; earlier sections keep the old-seam census. |
| [Tenant config schema](tenant-config-schema-2026-10-27.md) | The bounded configuration schema candidate and its lab evidence. |

## Architecture guides

| Document | Owns |
|---|---|
| [Single and multitenant architecture](single-and-multitenant-architecture.md) | Mode comparison, compatibility and the [current service composition and restore integration](single-and-multitenant-architecture.md#current-service-composition-and-restore-integration-2026-11-07). |
| [Runtime topology](runtime-topology.md) | Reusable roles, scale envelopes, private APIs and the [logical REST/worker map](runtime-topology.md#logical-rest-cohesion-and-worker-placement). |
| [Private API composition and scaling plan](selectable-endpoints-and-api-scaling-plan.md) | The adopted `serve.internal` listener, graceful shutdown, fixed-roster API replicas and their acceptance matrix. |
| [Realtime sharding plan](realtime-sharding-plan.md) | Proposed realtime tenant placement, recovery and co-location comparison. |
| [Evaluator/realtime communication](evaluator-realtime-communication.md) | Clinical projections, notification handoff, private API forwarding, output revisions and alarm repeat. |
| [SQL and migration architecture](sql-and-migration-architecture.md) | Table families, RLS and grants, tenant clock/order, migrations and restore inclusion. |
| [Counter and restore options](counter-and-restore-options.md) | History clock versus insertion order, restore alternatives and the census counter-writer rule. |
| [Clock proof plan](postgres-tenant-clock-proof.md) | Tenant clock invariants and experiment design; acceptance records keep their own scope. |

## Deployment

| Document | Owns |
|---|---|
| `nightscout-deploy` (sibling repository; local `/home/bewest/src/nightscout-deploy`) | The Compose tree, edge, identity-provider profiles and Vault Agent overlay, [from the next #8898 batch on](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#deploy-tree-home-now); see the [scope split](claimed-public-names-and-deploy-companion-2026-11-09.md#2-scope-split-core-sibling-repository-hoster-private). |
| [Deployment and rig testing](deployment-and-rig-testing.md) | Fault domains, the ed2 Compose runbook, client and rig setup, restore/restart scenarios. |
| [Deployment bindings and public names](deployment-bindings-and-public-names.md) | Kubernetes/Jsonnet resource translation, public-name lifetimes, transports and load-herd experiments. |

## Dispatch-era plans still cited by release records

These keep their route/domain design, seam plans and dated checkpoints; their
heads and "next" statements describe the original dispatch. Current sequencing is
in the completion schedule above.

| Document | Retained for |
|---|---|
| [REST delivery plan](multitenant-rest-api-delivery-plan-2026-11-04.md) | Route/domain coverage and handler reuse. |
| [Architecture seams plan](architecture-seams-execution-plan-2026-11-05.md) | Port composition, consolidation and caller-policy distinctions (`ARCH-*` items). |
| [Derived output boundary](derived-output-boundary-2026-11-07.md) | Output-publication ownership for `ARCH-DERIVED-FRAME`. |
| [M4 client dispatch](m4-client-binary-lab-packet-2026-11-06.md) | Lab hypotheses for the pinned-client campaign; the campaign record owns results. |

## Earlier analyses cited by platform specifications and gates

| Document | Retained for |
|---|---|
| [Configuration and delegation](nightscout-configuration-and-delegation-2026-09-10.md) | Delegation requirements carried as DR1–DR7 in the [authority specification](../platform/spec/authority.md). |
| [Control-plane reconciliation](nightscout-control-plane-reconciliation-2026-09-11.md) | Supersession map from the earlier cgm-remote-monitor control-plane draft to the platform specifications. |
| [Ordering translation](nightscout-seam-ordering-translation.md) | How ordering crosses the storage seam; cited by the backfix register. |
| [Owner configuration census](tenant-owner-config-surface-2026-09-15.md) | The 2026-09-15 census and DDL that `T30-*` gates read; the [dev census](../../60-research/tenancy/t30-census-dev-2026-10-27.md) re-measured it. |

## Keeping this path useful

Correct a rule in its decision or contract home and record acceptance in the
release records and status sources. Do not append execution journals to the
roadmap or the decision reference. When a document here is superseded, follow
[document control](../../00-overview/DOCUMENT-CONTROL.md#35-changing-a-document):
move it to the archive with a retention note and an index row, and repoint every
inbound link. Correspondence drafts belong to their owning session and are
outside this index.
