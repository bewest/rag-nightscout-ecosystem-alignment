# Tenancy: what to read and maintain

The multitenant candidate uses writer-driven notifications, resident evaluator windows and tenant-routed realtime. The single-site server keeps its MongoDB path. Start with the [runtime topology](runtime-topology.md), then follow a [clinical write through evaluation and browser delivery](evaluator-realtime-communication.md). The [decisions in force](decisions-in-force.md) index links to the maintainer's adopted contracts.

For **candidate 5**, the [dated execution record](execution-log.md#candidate-5-qualification-and-nominal-discovery) identifies the qualified core and deploy revisions, the local connector measurements, the paid experiment and their admission limits. The [production guide](production-critical-path.md) explains how these results are used. The [milestone dashboard](multitenant-delivery-dashboard.md) preserves the recorded promotion decisions. The [queue](../../../queue/work-queue.yaml) owns individual work items. The [16.0.0 release record](../../../releases/cgm-remote-monitor-16.0.0/contents.md) covers a release with no multitenant role.

For storage, read the [SQL guide](sql-and-migration-architecture.md) for tenant isolation, history and restore. The [database diagrams](../../../site/pages/multitenant-database-design.html) render its component and storage contracts. The [layout study](storage-layout-proposal-2026-11-23.md) compares measured alternatives. The [diagram collection](diagrams/README.md) and [tenancy archive](../../archive/tenancy/README.md) identify the source and date of earlier designs.

## State, sequencing and decisions

| Document | Owns |
|---|---|
| [Delivery dashboard](multitenant-delivery-dashboard.md) | Generated milestone claims and the acceptance ledger. Edit the queue and `multitenant-delivery-status.json`, then `make queue`. |
| [Delivery roadmap](multitenant-delivery-roadmap.md#milestones-and-continuous-integration) | Delivery boundaries and the M0–M5, M6a–M6d and M7 promotion criteria. |
| [Completion schedule](multitenant-integration-batching-plan-2026-11-06.md#5-current-completion-schedule-adopted-2026-11-06) | November batch sequence and [completion-focused coordination](multitenant-integration-batching-plan-2026-11-06.md#completion-focused-coordination). |
| [M5/M6 decision index](m5-m6-decision-list.md) | Settled M5/M6 policy questions from the November 10 review. |
| [Production critical path](production-critical-path.md) | Production closure criteria, diagnostic/acceptance sequencing and conditional topology/HA decisions; current measurements are in the execution log. |

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
| [Single and multitenant architecture](single-and-multitenant-architecture.md) | Mode comparison, compatibility and the [source-pinned service and restore reference](single-and-multitenant-architecture.md#current-service-composition-and-restore-integration-2026-11-07). |
| [Runtime topology](runtime-topology.md) | Reusable roles, scale envelopes, private APIs and the [logical REST/worker map](runtime-topology.md#logical-rest-cohesion-and-worker-placement). |
| [Private API composition and scaling plan](selectable-endpoints-and-api-scaling-plan.md) | Private listener and graceful shutdown decisions, with the November 10 transport and fixed-roster acceptance plan. |
| [Realtime sharding plan](realtime-sharding-plan.md) | Static hash ownership, reconnect behavior and the retained fixed-roster move evidence. |
| [Evaluator/realtime communication](evaluator-realtime-communication.md) | Writer-owned pending work, evaluator completion, raw storage events, browser frames and notification handoff. |
| [Evaluator scaling options](evaluator-scaling-options-2026-11-19.md) | November scaling experiments and the decisions that selected more slices and cheaper cycles. |
| [Storage layout proposal](storage-layout-proposal-2026-11-23.md) | Typed entries and treatments remain on an experiment branch. The tenant-hour device-status layout is parked. Candidate 5 uses JSONB. |
| [Writer-driven refactor ledger](writer-driven-refactor-ledger-2026-11-20.md) | S4 join contents, pgstream retirement inventory and deferred refactors. |
| [SQL and migration architecture](sql-and-migration-architecture.md) | Table families, RLS and grants, tenant clock/order, migrations and restore inclusion. |
| [Counter and restore options](counter-and-restore-options.md) | Clinical time, public history, implemented insertion order and evaluator pending work; current recovery obligations and retained alternatives. |
| [Retained legacy history proof plan](../../archive/tenancy/postgres-tenant-clock-proof-2026-11-06.md) | Original public-history no-missed-write controls and source-scoped experiment design; not current internal CDC sequencing or dispatch. |

## Deployment

| Document | Owns |
|---|---|
| `nightscout-deploy` (sibling repository; local `/home/bewest/src/nightscout-deploy`) | The Compose tree, edge, identity-provider profiles and Vault Agent overlay, [from the next #8898 batch on](multitenancy-decisions.md#deploy-tree-home-now); see the [scope split](claimed-public-names-and-deploy-companion-2026-11-09.md#2-scope-split-core-sibling-repository-hoster-private). |
| [Deployment and rig testing](deployment-and-rig-testing.md) | Fault domains, the ed2 Compose runbook, client and rig setup, restore/restart scenarios. |
| [Deployment bindings and public names](deployment-bindings-and-public-names.md) | Kubernetes/Jsonnet resource translation, public-name lifetimes, transports and load-herd experiments. |

## Dispatch-era plans still cited by release records

These keep their route/domain design, seam plans and dated checkpoints; their
heads and "next" statements describe the original dispatch. Current runs and lane ownership are in the [execution log](execution-log.md).

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
[execution log](execution-log.md) and the applicable status source. Do not append execution journals to the
roadmap or the decision reference. When a document here is superseded, follow
[document control](../../00-overview/DOCUMENT-CONTROL.md#35-changing-a-document):
move it to the archive with a retention note and an index row, and repoint every
inbound link. Correspondence drafts belong to their owning session and are
outside this index.
