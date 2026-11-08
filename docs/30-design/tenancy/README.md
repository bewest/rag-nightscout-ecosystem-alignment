# Tenancy: what to read and maintain

*Contributor-facing living reading guide. The current documents below own rules,
coordination and recorded acceptance. The complete long execution journals are
retained in the [tenancy archive](../../archive/tenancy/README.md); dates in a
filename do not establish currency. Consolidated 2026-11-06.*

## Start with the task

| You need | Read | What stays current |
|---|---|---|
| What is accepted, blocked, or next | [Delivery dashboard](multitenant-delivery-dashboard.md) | Generated queue claims and dated acceptance metadata; not live branch monitoring. Edit the queue/status sources, then `make queue`. |
| What to implement and how to join it | [Completion schedule](multitenant-integration-batching-plan-2026-11-06.md#5-current-completion-schedule-adopted-2026-11-06) | A–C sequence, ownership and verification boundaries. Its sections 1 and 4 retain the original dispatch. |
| What a milestone must prove | [Delivery roadmap](multitenant-delivery-roadmap.md#milestones-and-continuous-integration) | Delivery boundaries and M0–M6 criteria, including later promotion-bar decisions. Claims remain in the dashboard. |
| Why the architecture is this way | [Tenancy decisions](multitenancy-decisions.md#1-decisions) | D1–D23, hard qualifications and links to detailed contracts. Old per-commit tasks belong to the archive. |
| Current promotion bars and compatibility direction | [Promotion decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#multitenant-promotion-bars-2026-11-06) | Reader mode withdrawn; writer policy retained. M2 cell/M6 lifecycle and deferred M1 budgets/Android lab retain their adopted scope. No new promotion. |
| Owner, delegation and token rules; shared optional OIDC | [Owner authority](owner-authority.md), [shared integration](owner-authority.md#shared-oidc-integration) | Equivalent single/multitenant human auth, provider-backed renewal and separate authority adapters; implementation acceptance is separate. |
| What needs a maintainer decision | [Current M5/M6 decision list](m5-m6-decision-list.md) | Settled choices, next policy questions and measurement prerequisites. Release decisions own answers; older packets supply background only. |
| Durable consumers and recovery | [Durable event contract](durable-event-delivery-contract-2026-11-06.md#11-maintainer-acceptance-and-experiments) | Adopted B7 direction; runtime evidence retains its actual tree and limits. |
| Separate service processes and restore coordination | [Current composition diagram](single-and-multitenant-architecture.md#current-service-composition-and-restore-integration-2026-11-07) | Fixed cross-process cohort and source-attributed restore evidence; newer independent-startup acceptance remains pending. |
| Deploy a synthetic prototype or connect a rig | [Deployment and rig testing](deployment-and-rig-testing.md) | Runnable Compose preparation, ingress/credential boundaries, client setup, restore/restart scenarios and evidence limits. |
| Follow evaluator and socket messages | [Evaluator/realtime communication](evaluator-realtime-communication.md) | Independent clinical projections, durable notification handoff, private API forwarding, current authority and operation lifetimes. |
| Understand SQL and recovery | [SQL/migration architecture](sql-and-migration-architecture.md) | Table families, RLS and grants, tenant clock/order, catalogue migration/readiness and restore inclusion/exclusion. |
| A picture of the system | [Platform map](../platform/next-gen-platform-plan.md#3-the-map), then [architecture comparison](single-and-multitenant-architecture.md) | Map summarizes bounded components. Architecture diagrams retain their named source scope. Neither promotes a milestone. |
| What ran and on which tree | [Integration record](../remedial/rc-16.0.0-integration-record.md), then the named capture | Executed heads, failed predictions, red/restored controls and reuse limits. A prior green campaign is not a new-head execution. |
| Release or publication status | [Release contents](../../../releases/cgm-remote-monitor-16.0.0/contents.md) | Dated programme updates. Local acceptance, merge and release are distinct. |

Follow [completion-focused coordination](multitenant-integration-batching-plan-2026-11-06.md#completion-focused-coordination):
one capability/criterion per lane, focused checks during implementation and one
comprehensive campaign on the coherent frozen batch. Report closure and blockers.

For a new lane, read the dashboard, the applicable completion batch and the
specific contract it touches, then inspect its evidence. Confirm current ownership
and task state before starting; a dated handoff's “next” is not a new assignment.

## Specialist references

Open only the section needed for the change; use the dashboard and completion
schedule for work state.

| Reference | Purpose and scope |
|---|---|
| [REST delivery plan](multitenant-rest-api-delivery-plan-2026-11-04.md) | Route/domain coverage and handler reuse; original lane packets are historical dispatch. |
| [Architecture seams plan](architecture-seams-execution-plan-2026-11-05.md) | Port composition, consolidation and caller-policy distinctions; dated checkpoints keep their captured scope. |
| [Storage seam §11](nightscout-storage-seam-interface-2026-09-14.md#11-current-admitted-ports-and-independent-scopes-2026-11-05) | Current admitted ports; earlier sections retain old-seam census and implementation evidence. |
| [Write contract §9](write-contract-spec-2026-10-07.md#9-current-shared-intent-and-backend-capabilities-2026-11-05) | Current admitted implementation; original matrices retain their baseline. |
| [Config schema candidate](tenant-config-schema-2026-10-27.md) | Bounded schema; owner authority owns later management/session/delegation rules. |
| [Clock proof plan](postgres-tenant-clock-proof.md) | Invariants and experiment design. Correctness, descriptive timing and capacity acceptance retain separate records. |
| [Deployable components](nightscout-deployable-components-2026-09-14.md) | Original decomposition/rationale; apply current tenancy decisions, CLI amendments and B7. |

## Source-backed architecture guides

The guides above provide the requested **MT-DOC-DEPLOY**, **MT-DOC-REALTIME** and
**MT-DOC-SQL** documentation. Their source inspection, diagrams and structural
checks are separate from runtime acceptance. Each links executed evidence at its
actual source; pending Compose, restart, rig and capacity experiments remain
explicit. The queue owns documentation status, and release records own accepted
application behavior.

## Historical evidence and earlier proposals

These retain distinct evidence or alternatives; they are not current work instructions.

| Read only for this purpose | Current successor / boundary |
|---|---|
| [Archived execution journals](../../archive/tenancy/README.md) | Original decision detail, seam tasks, dispatches, failures, controls and checkpoints. Current rules live above. |
| [September multitenancy discussion](nightscout-multitenancy-discussion-2026-09-09.md) | Original options/evidence; decisions superseded by the current decision reference. |
| [Owner configuration census](tenant-owner-config-surface-2026-09-15.md) | Historical census/DDL; later [dev census](../../60-research/tenancy/t30-census-dev-2026-10-27.md), config candidate and owner authority have separate scopes. |
| [Configuration/delegation questions](nightscout-configuration-and-delegation-2026-09-10.md), [control-plane reconciliation](nightscout-control-plane-reconciliation-2026-09-11.md) | Historical analysis and supersession map; not a replacement backlog. |
| [Ordering translation](nightscout-seam-ordering-translation.md) | Old-seam proposal; current ports, write contract and backend measurements govern admission. |
| [Earlier open-decision note](multitenant-open-decisions-2026-11-06.md), [owner lifecycle packet](owner-lifecycle-decision-packet-2026-11-06.md) | Historical questions, source surveys and alternatives. Start with the current decision list; draft recommendations are not adopted policy. |
| [M0–M3 promotion review](milestone-promotion-review-2026-11-06.md), [M4 client dispatch](m4-client-binary-lab-packet-2026-11-06.md) | Read-derived gap review and lab hypotheses. Later integration records own actual acceptance. |

## Keeping this path useful

Correct current rules in their decision/contract home. Record acceptance in the
integration/release records and status sources. Do not append execution journals
to the roadmap or decision reference, or copy their checkpoints into the platform
map. The archive preserves scope and successors; Git retains intermediate revisions.

Future consolidation follows [document control](../../00-overview/DOCUMENT-CONTROL.md#35-changing-a-document):
read a cluster in full, preserve unique content and evidence, rewrite links, then
remove superseded material from the active reading path. Correspondence drafts
belong to their owning session and are outside this controlled inventory.
