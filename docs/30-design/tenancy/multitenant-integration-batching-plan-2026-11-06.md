# Multitenant integration batching plan

*Contributor-facing living coordination plan, refreshed 2026-11-08. This page owns
capability boundaries, integration order and verification depth. The
[queue](../../../queue/work-queue.yaml) owns claimed item state; the
[dashboard](multitenant-delivery-dashboard.md) owns recorded milestone claims;
[release contents](../../../releases/cgm-remote-monitor-16.0.0/contents.md) and the
[integration record](../remedial/rc-16.0.0-integration-record.md) own actual source,
acceptance and publication. The [retained batching journal](../../archive/tenancy/multitenant-integration-batching-journal-2026-11-06.md)
preserves the original dispatch and all captured evidence.*

## Completion-focused coordination

**Maintainer direction, 2026-11-06:** organize lanes around complete capabilities
and adopted milestone criteria. A helper, fixture repair or individual control
belongs to its capability lane; an independently deliverable capability or
material architectural unknown may have a separate owner.

- Give each lane one observable deliverable, owner, exit criterion, focused
  positive/negative checks, unresolved decisions and next integration boundary.
  Confirm the head commit and that the task remains open before starting. Stop and
  report a mismatch rather than reaching for the nearest thing that works.
- Run changed-code lint and affected/focused checks during implementation. Keep
  meaningful controls for isolation, authorization, clinical behavior and
  compatibility, followed by restoration. A setup failure is not a semantic red.
- Resolve architectural unknowns with bounded early proofs whose question and
  stop condition are explicit. Incorporate their result into the capability;
  a proof does not become a separate comprehensive campaign.
- Freeze the coherent joined candidate for one full nonbrowser, default-browser,
  enabled-corpus and applicable native/client campaign, then final prcheck.
  Preserve failed campaigns, diagnose narrowly, join planned repairs and repeat
  final acceptance when material inputs changed. A leaf commit, resumption or
  documentation update does not trigger a new comprehensive campaign.
- Reuse evidence only with exact source/instrument attribution and an explicit
  affected-input analysis. Ancestry establishes incorporation, not execution.
  Source-identical evidence retains its original executed head and limits.
- Maintain one evolving lane handoff and one programme acceptance update per
  coherent batch. Record substantive failures, decisions and ownership transfers
  promptly. Report capability/criterion closure, remaining blockers and the next
  integration owner with the evidence link; counts are supporting observations.

<a id="1-historical-measured-basis"></a>
## 1. Evidence and ownership

Use the [current acceptance bundle](../../../reports/tenancy/operation-window-acceptance-2026-11-07/README.md)
for the published restore/Compose candidate, and the
[M5/M6 decision index](m5-m6-decision-list.md) for adopted policy and open
implementation/measurement work. A dated journal or local handoff does not assign
new work. Confirm active ownership with the programme coordinator before claiming
an existing lane; the release record links the evolving local handoffs.

The source owner integrates original committed lane histories by fast-forward or
ordinary merge. Check ancestry and patch equivalence first; resolve overlap
explicitly. Do not cherry-pick/rebase patches and later merge their original
history solely to make evidence commits reachable. Continue the existing draft
[#8898](https://github.com/nightscout/cgm-remote-monitor/pull/8898); the adopted
integration direction does not authorize a cleanup rewrite or replacement PR.

<a id="1-measured-basis"></a>
The [original measured basis](../../archive/tenancy/multitenant-integration-batching-journal-2026-11-06.md#1-historical-measured-basis)
retains the older PR/CI snapshots. They are historical observations, not the
current publication state.

<a id="2-acceptance-ladder-and-what-runs-at-each-stage"></a>
## 2. Acceptance ladder

| Stage | Required evidence | Record owner |
|---|---|---|
| Locally accepted | Focused capability checks and meaningful red/restored controls on the lane's actual head | Capability owner, in the lane handoff |
| Incorporated | Original lane history is an ancestor of the joined candidate; overlap and affected checks resolved | Source integration owner |
| Integrated acceptance recorded | Coherent frozen candidate passes its applicable regression/native/client campaign and final prcheck | Acceptance coordinator, with exact source and instrument attribution |
| Milestone promoted | Every adopted milestone criterion has an explicit verdict; deferrals have an adopted basis | Maintainer decision, reflected in dashboard/status sources |

Implementation, functional preview acceptance, publication, merge to `dev`,
operator release and production/default enablement are separate claims. A
promoted component or milestone supplies evidence for decisions within its tested
scope; it does not establish capacity, high availability or a new deployment.

## 3. Batch rules

1. Keep default single/Mongo regression and explicit multitenant corpus coverage.
   Reconcile the enabled-suite inventory with source before each freeze; publish
   named pending/unsupported cases. A pending benchmark is not a functional pass.
2. Changes to existing shipping paths, migrations, dependencies, tier registry or
   shared fixtures are assessed on the coherent joined candidate. Material
   changes invalidate the affected final acceptance; they do not require a full
   campaign for every intermediate commit.
3. Run focused jobs only with positive ownership of schemas, ports, processes and
   containers. Local comprehensive campaigns share the coordinator's serialized
   runtime slot. Parallel native jobs need measured capacity and isolation;
   unknown resources remain untouched. Quiet performance work gets a separate
   controlled window.
4. Use the complete opt-in corpus command for corpus acceptance; an archived gate
   or a filtered focused suite cannot establish whole-corpus acceptance. CI and
   local campaigns keep their actual source/environment attribution.
5. Gates read; they never mutate another session's checkout. Update queue refs
   only after the applicable measured acceptance, retaining native evidence pins.
   Without a required database/runtime, report UNMEASURED, not green.
6. Every capability brief includes source head, outcome, integration boundary,
   focused tests, meaningful controls and remaining decision boundaries, plus the
   standing confirm-head/open-task and stop-on-mismatch instructions above.
7. Publication remains a separately authorized action. This plan supplies no
   authority to publish application source, enable defaults or admit real data.

<a id="4-critical-path-batches"></a>
<a id="4-historical-b1b7-dispatch"></a>
## 4. Retained dispatch

The [B1–B7 dispatch](../../archive/tenancy/multitenant-integration-batching-journal-2026-11-06.md#4-historical-b1b7-dispatch)
preserves original branch identities, commands, predictions, failures, controls
and ownership. Those completed/older lanes are evidence inputs, not today's task
list. The schedule below governs further work.

## 5. Current completion schedule (adopted 2026-11-06)

| Completion stage | Accepted capability and evidence | Remaining integration boundary |
|---|---|---|
| **A — data, control and clients (M0–M4)** | [R72](../remedial/rc-16.0.0-integration-record.md#r72---admitted-entries-and-owner-configuration-completion-batch-2026-11-06) retains M0 and promotes M1/M2, then M3/M4, at the adopted bounded scope. The later [pinned-client campaign](../../../reports/tenancy/operation-window-acceptance-2026-11-07/ed2-clients-accepted.json) belongs to its own source/instrument. | Preserve legacy root/subject behavior and supported PG differences. Android emulator and measured operating limits remain C; no all-client claim. A's closed criteria are not new prerequisites to re-run for the documentation refresh. |
| **B — durable runtime (M5)** | [R73](../remedial/rc-16.0.0-integration-record.md#r73-durable-runtime-operations-batch) accepts the functional separate-role reference on one host: current-state/evaluator recovery, current socket authority, durable suppression/request handoff and reference consumers. | Keep the accepted reference distinct from live external delivery, retained every-transition history, multi-node ownership and capacity. Changes to a consumed runtime contract need affected checks and coherent joined acceptance. |
| **C — synthetic operational preview (M6)** | [Operation-window acceptance](../../../reports/tenancy/operation-window-acceptance-2026-11-07/README.md) records separate-process tenant-local restore, ordinary forward history/client convergence and B continuity, plus cold Compose/UI/restore acceptance. Earlier SQL backup/upgrade/deletion evidence retains its captured scope. | **M6 remains blocked.** Join the complete chosen owner/human-session capability, lifecycle/key destruction/recovery, trusted deployment and approved workload/resource/egress evidence; retain Android and final criterion review. Accepted one-host recovery is not multi-host/HA admission. |
| **Next owner/OIDC capability** | [Shared OIDC source evidence](../../../reports/tenancy/shared-oidc-sessions-2026-11-07/README.md) establishes focused source behavior on its actual branch. | Signed native database/Vault/HTTPS/browser acceptance on the coherent owner/OIDC candidate remains **UNMEASURED**. The combined source owner and next-capability acceptance lead are identified in the latest release update/local handoff. Do not infer this capability from the published Compose candidate or redispatch archived chats. |

### Criterion matrix for the next frozen candidate

The coordinator records actual source, instrument, command/selector, artifact,
control and verdict for each applicable
[roadmap acceptance family](multitenant-delivery-roadmap.md#m5m6-acceptance-families).
Name the carried evidence, changed input and why reuse is valid for each retained
criterion. Record explicit deferrals before milestone promotion. A count, a
waiver inferred from a prototype, or an incorporated source change cannot replace
that matrix.

For production-quality deployment, keep four questions separate: whether the
component behaves correctly under tested faults; whether its chosen deployment
preserves those assumptions; whether its measured workload meets approved bounds;
and whether it is admitted for release/operation. The
[deployment guide](deployment-and-rig-testing.md) explains topologies and fault
domains. Remaining measurement work continues under adopted policy; a deferred
policy question retains its prototypes and benches.

<a id="5-lane-ownership-and-coordination"></a>
The [production dependency map](production-critical-path.md#dependency-map)
continues beyond C through actual deployment qualification and release/admission.
It proposes sequencing and closing evidence, without assigning new lanes or
changing the adopted milestone bars.

## 6. Lane ownership and coordination

The programme coordinator owns criterion closure, source freeze, queue/status
integration and the acceptance reservation. Each capability has one source owner
and one next integration boundary. Native acceptance has a named lead, finite
reservation and independent resource/physical-closure checks. Source-only
implementation is distinct from a runtime grant.

Local evolving handoffs remain under `externals/work/HANDOFF-<lane>-<date>.md`.
The latest release update points to current combined ownership; the
[archived lane roster](../../archive/tenancy/multitenant-integration-batching-journal-2026-11-06.md#6-lane-ownership-and-coordination)
retains earlier responsibilities and traps. Never take an old “active” label as
a present assignment. Preserve peer drafts and existing worktrees; inspect the
shared index and commit only owned paths.

<a id="6-what-this-plan-does-not-do"></a>
<a id="7-what-this-plan-does-not-do"></a>
## 7. Scope and retention

This plan changes no adopted milestone bar, release placement, backend default,
provider selection or operator admission. The full captured predecessor at
alignment `8792fc7a3d62f59629ed94bac168dcad5d9aa3c7` is retained in the
[batching journal](../../archive/tenancy/multitenant-integration-batching-journal-2026-11-06.md),
including its unique measurements, failed predictions and historical assignments.
Git retains intermediate revisions. Correct coordination here, decisions in their
canonical home and new acceptance in release/integration records; do not append
execution journals to the current schedule.
