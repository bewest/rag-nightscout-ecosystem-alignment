# Tenancy: what to read and maintain

*Contributor-facing living reading guide. Reconciled 2026-11-06 to recorded R60
acceptance. This guide owns document navigation; status, decisions and measurements
stay in their existing homes. Dates in filenames do not establish currency.*

## Start with the task

| You need | Read | Maintenance contract |
|---|---|---|
| What is accepted, blocked, or next | [Delivery dashboard](multitenant-delivery-dashboard.md) | Generated from the queue and `multitenant-delivery-status.json`; update those sources, then `make queue`. Recorded acceptance, not live branch monitoring. |
| What to implement and how to join it | [Batching plan §5](multitenant-integration-batching-plan-2026-11-06.md#5-current-completion-schedule-adopted-2026-11-06) | Current A–C completion schedule and acceptance boundaries. Sections 1 and 4 retain the original dispatch. |
| The milestone's actual criteria | [Delivery roadmap §4](multitenant-delivery-roadmap-2026-11-02.md#4-milestones-and-continuous-integration) | Maintained promotion criteria. The dashboard owns milestone claims; dated checkpoint sections own only their captured scope. |
| Why the architecture is this way | [Execution-plan decisions](nightscout-multitenancy-execution-plan-2026-09-14.md#1-decisions) | Maintainer decisions D1–D23. Read the relevant decision and task, rather than the entire plan. |
| Owner, delegation and token rules | [Owner authority](owner-authority.md) | Adopted amendment to the execution plan. Implementation acceptance remains separate. |
| Durable consumers and recovery | [Durable event contract](durable-event-delivery-contract-2026-11-06.md#11-maintainer-acceptance-and-experiments) | B7 direction adopted; experiments and implementation acceptance retain their own evidence. |
| A picture of the system | [Platform map](../platform/next-gen-platform-plan.md#3-the-map), then [architecture comparison](single-and-multitenant-architecture.md) | Map summarizes current bounded components. Architecture diagrams explain their explicitly pinned source scope, rather than current milestone completion. |
| What ran and on which tree | [R60](../remedial/rc-16.0.0-integration-record.md#r60---coherent-ci-client-batch-and-m0-foundations-2026-11-06) and its linked captures | Preserve executed heads, failures and controls. A prior green campaign is not a new-head execution. |
| Release or publication state | [Release contents](../../../releases/cgm-remote-monitor-16.0.0/contents.md#update--coherent-compatibility-batch-accepted-m0-promoted-2026-11-06) | Programme updates go here. PR acceptance, merge and release are separate facts. |

For a new lane, read the dashboard, the current completion batch, and the specific
contract it touches. Then inspect the named evidence. A dated handoff's “next”
instruction is not a new assignment.

## Specialist references

These retain unique design content. Open only the section needed for the change;
use the dashboard and batch plan for work state.

| Reference | Use and scope |
|---|---|
| [REST delivery plan](multitenant-rest-api-delivery-plan-2026-11-04.md) | Route/domain coverage and handler reuse. Original lane packets are historical dispatch instructions. |
| [Architecture seams plan](architecture-seams-execution-plan-2026-11-05.md) | Port composition, consolidation and caller-policy distinctions. Dated acceptance and pending statements keep their original scope. |
| [Storage seam](nightscout-storage-seam-interface-2026-09-14.md) | Current admitted ports in §11; §§1–10 retain old-seam census/implementation evidence. |
| [Write contract](write-contract-spec-2026-10-07.md) | Current admitted implementation in §9, decisions in §6; original matrices retain their captured baseline. |
| [Tenant config schema](tenant-config-schema-2026-10-27.md) | Bounded schema candidate. Owner authority owns later management/session/delegation amendments. |
| [Clock proof plan](postgres-tenant-clock-proof.md) | Invariants and experiment design. R60 owns joined correctness acceptance; benchmark remains pending. |
| [Deployable components](nightscout-deployable-components-2026-09-14.md) | Original decomposition/rationale. Apply later execution-plan decisions, CLI amendments and the durable event contract when implementing. |

## Retained evidence and earlier proposals

These are not maintained as current work instructions. Preserve their measurements
and proposed alternatives; resolve current policy through the decision owners above.

| File | Retention purpose / current successor |
|---|---|
| [September multitenancy discussion](nightscout-multitenancy-discussion-2026-09-09.md) | Original evidence/options; decisions superseded by the execution plan. |
| [Owner configuration census](tenant-owner-config-surface-2026-09-15.md) | Historical census and proposed DDL; later [dev census](../../60-research/tenancy/t30-census-dev-2026-10-27.md), config candidate and owner authority have distinct scopes. |
| [Configuration and delegation questions](nightscout-configuration-and-delegation-2026-09-10.md) | Historical analysis; execution-plan decisions and owner authority govern current policy. |
| [Control-plane reconciliation](nightscout-control-plane-reconciliation-2026-09-11.md) | Supersession map for the earlier external draft and platform specifications; not an implementation backlog. |
| [Ordering translation](nightscout-seam-ordering-translation.md) | Old-seam proposal and ordering evidence; current ports/write contract and backend measurements govern admitted behavior. |
| [M0–M3 promotion review](milestone-promotion-review-2026-11-06.md) | Read-derived R24–R55 gap review. R60 later promotes M0; this review is not the current milestone verdict. |
| [M4 client dispatch packet](m4-client-binary-lab-packet-2026-11-06.md) | Original client inventory and lab hypotheses. Later actual-client captures linked by R60 own measured results; wider M4 remains open. |

## Grooming boundaries

Keep current summaries short and link to their evidence. New acceptance belongs
in the integration/release records and dashboard sources, rather than another
checkpoint copied into the platform overview. That overview now retains its
superseded checkpoints through a pinned history link.

The next consolidation candidates are the delivery roadmap's dated execution
journal and the execution plan's old implementation/task narrative. Preserve
milestone criteria, decision anchors and unique designs as separate maintained
sections. Retire superseded prose through pinned history rows and rewrite inbound
links after a full scope/evidence review. The discussion and owner census are
historical evidence candidates for leaving the default reading path; their length
alone is not evidence that their contents can be deleted.

Follow [document control §3.5](../../00-overview/DOCUMENT-CONTROL.md#35-changing-a-document):
read a cluster in full, preserve unique content and evidence, rewrite inbound links,
then remove superseded files. Avoid moving dated records merely to make the
folder appear smaller. Untracked correspondence drafts belong to their owning
session and are outside this guide's controlled inventory.
