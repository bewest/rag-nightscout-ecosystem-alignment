# Architecture seams and execution-profile integration

*Contributor-facing execution plan, 2026-11-05. Authorized priority work;
bounded R42 contract/management, R43 profile and R44 current-domain composition
evidence is recorded; broader consolidation/frame acceptance remains UNMEASURED.
Item states, gates and blockers
live in [the work queue](../../../queue/work-queue.yaml). This plan supplements
the [REST delivery roadmap](multitenant-delivery-roadmap-2026-11-02.md), without
changing release placement or promoting M0–M6. Batching and verification depth
per acceptance stage are set by the
[integration batching plan](multitenant-integration-batching-plan-2026-11-06.md).*

## Basis and priorities

Read-derived review inspected published draft #8898 at
`ded254b9acf5a94e3a4fd99c85b23e1413fa08b6` and draft #8891 at
`744d196861fbc1c9988669b8c7afdc9c7110c265`. Fresh GitHub metadata on November 5
reports both OPEN/draft. The local CRM `official/dev` reference is
`4a482627bfdafb1fef8dcbe0ac6c484811cae563`. Planning incorporates alignment main
`1551c3e019713901315238d2f67b075205247430` and the separately recorded local
CRM continuation `94c57f1f37370215ef25b69691ef63918c876db3`;
[R41](../remedial/rc-16.0.0-integration-record.md#r41---subject-administration-and-cross-compatibility-on-94c57f1f-2026-11-05)
owns its acceptance. These anchors are not new application test results.

Preserve shared shipping handlers/write rules, trusted storage injection,
current authority and independent tenancy/execution choices. The maintainer
prioritizes improvements to those boundaries and integration of #8891 into the
existing lanes. SQLite/celld experiments are deferred, low priority; no backend
or runtime is selected by this plan. Preserve existing lab artifacts.

| Priority / queue home | Deliverable | Lane / scheduling |
|---|---|---|
| First: `ARCH-SEAM-CONTRACT` | Executable contract inventory for storage, identity, queries, results, failures, tenant binding and transaction ownership | Architecture lane; begin alongside current REST/compatibility work |
| First, after contract: `ARCH-SEAM-COMPOSE` | Separate domain definitions from PG factories/schema/readiness; separate storage failure classification from HTTP rendering | Architecture/composition lane; reserve shared files with REST coordinator |
| Next: `ARCH-SEAM-CONSOLIDATE` | Consolidate proven common PG adapter mechanics and incrementally relocate Mongo compatibility helpers | Storage lane, after contract/composition and direct compatibility baseline |
| Parallel preparation, then next: `ST-VIEWS-PROFILE` | Refresh/replay #8891 and integrate the explicit single/nonresident execution profile after its entry bar | Execution-profile lane; independent of PG helper consolidation |
| Next join: `ARCH-DERIVED-FRAME` | Shared bounded materialization and calculation primitives, explicit REST/evaluator lifecycle policies | Derived/evaluator lane; join refreshed #8891 with current preview |
| Later M5: existing `MT-RUNTIME-PLAN` | Durable commit-coupled feed, recovery, tenant-local evaluation and notification state | Runtime lane; contract design continues while REST completes |
| Deferred: `ARCH-SQLITE-SPIKE` | Optional third-backend conformance probe | Unassigned; no dispatch and no dependency of preview or release readiness |

Queue dependencies describe prerequisites for implementation acceptance. They
do not stop independent characterization, contract review or bounded prototypes.
The REST coordinator retains cumulative integration ownership. Existing subject
administration, remaining side effects and direct/historical compatibility lanes
continue; no new implementation agent is dispatched by this planning commit.

## Active bounded dispatch checkpoint

This records the delivered R42/R43 dispatch. Current R46/R47 acceptance and
next ownership are recorded below.

Continuation authorized 2026-11-05 from accepted CRM R41 `94c57f1f` and
alignment `fc8c4010e`; fresh remote read-back retains draft #8898 `ded254b9`,
draft #8891 `744d1968` and dev `4a482627`. Selected current integration gates
MT-CONFIG-MIN and T30-WIRING pass; contract/profile/full-lab scope is UNMEASURED.

| Lane | Owned bounded work | Acceptance boundary |
|---|---|---|
| `codex/seam-contract-20261105` | Actual Mongo/PG parameterized port characterization and module-facing contract; parent reconciles existing interface/write-contract documents. | Identity/query/projection/result and independent binding/transaction cases plus semantic controls; no production extraction or backend adoption. |
| `codex/owner-subject-http-20261105` | Standalone management HTTP factory over R41 subject service, with trusted injected management authentication. | Real persisted effects/current authority and data-plane refusal; no CLI listener, identity provider or grant-ceiling default selected. |
| `codex/profile-refresh-20261105` | Refresh existing #8891 in its own worktree; actual-trigger/timer/freshness characterization and controls. | Preserve current subscriber until its logical/physical event behavior is measured; separate from #8898 cumulative acceptance and release placement. |

The coordinator reserves existing domain-catalogue, preview assembly, shared
error wrappers and migration/tier registration. No composition/consolidation
agent is dispatched yet. New lanes own new files or profile-specific source;
owned services and private dependencies remain separate. Stop and report source
or policy mismatches; partial instrumentation never promotes a milestone.

## Accepted checkpoint and next ownership

The dispatch slices above delivered local REST `d4570e58` (R42) and independent
profile `925c9527` (R43). The [integration record](../remedial/rc-16.0.0-integration-record.md#r42---storage-contracts-and-separate-management-http-on-d4570e58-2026-11-05)
owns measurements, corrections and limits. Three archived suite instruments
measure the bounded port, separate management and profile scopes; current
authority/subject gates also run against the new REST head. Five representative
controls are NON-VACUOUS. This does not complete their broader cards or M0–M6.

Next storage work consumes the R44 composition boundary for proven common
adapter consolidation, under coordinator ownership. Preserve the
measured lower/preview projection differences and independent transaction scope;
do not combine extraction with new query or write policy. #8891 keeps its current
physical subscriber while logical no-op/outcome and full-writer replay continue.
Its branch remains separate from REST and release placement. SQLite stays deferred.

## Current-domain composition acceptance and next ownership

[R44](../remedial/rc-16.0.0-integration-record.md#r44---explicit-backend-composition-and-imported-identity-on-bc4ee1a9-2026-11-05)
accepts local REST `bc4ee1a9`, joining the domain/backend and failure/HTTP split
with bounded direct imported-identity compatibility tests. Real startup/refusal,
HTTP and stored-outcome controls, full nonbrowser/default-browser campaigns and
independent source review establish this current-domain extraction. The public
preview is draft #8898 `bc4ee1a9`; both that head and independent #8891
`dff9a8d4` have successful head CI/CodeQL at read-back. New continuations stay local.

The REST coordinator owns cumulative acceptance. Next storage ownership is
`ARCH-SEAM-CONSOLIDATE`: extract only proven common adapter mechanics after
comparing the measured lower/preview contract differences. Compatibility owns
further settings/identity/index-race and actual-client evidence. R45 independently
accepts actual-HTTP profile replay and corrected live fixture ownership; profile remains
independent; complete writer/alarm coverage and logical no-op admission precede
subscriber or shared-frame policy changes. No new RC gate or milestone promotion.

## Bounded consolidation and evaluator continuation acceptance

[R46](../remedial/rc-16.0.0-integration-record.md#r46---bounded-pg-consolidation-and-identifier-races-on-44331668-2026-11-05)
accepts local REST `44331668`: shared PG projection/identifying-read/owned-commit
event mechanics with independent translators and source-specific behavior retained.
Expanded baseline/current port and direct index-on race checks, semantic controls,
full regression and independent source review pass. Broader helper relocation,
portable capabilities and remaining REST/client/import/resource gates stay open.

[R47](../remedial/rc-16.0.0-integration-record.md#r47---independent-shipping-v1-evaluator-replay-on-0c98ad06-2026-11-05)
independently accepts test-only v1 writer composition over the actual evaluator;
production routes and subscriber remain unchanged. The source-pinned frame
inventory below is read-derived preparation. Next shared-frame work must first
measure acquisition and concurrent-read boundaries before extracting lower private
working-set mechanics. Keep retention/notification and REST all-or-error policy
separate; no consistency strengthening, provider selection, RC admission or
M0-M6 promotion is inferred.

Published #8898 is OPEN/draft R44 `bc4ee1a9`; #8891 is OPEN/draft R45 `dff9a8d4`,
both with successful head CI/CodeQL at fresh read-back. New continuations stay
local until the maintainer publishes them. SQLite remains deferred.

## Contract packet: ARCH-SEAM-CONTRACT

Characterize the current implementation before prescribing extraction. At the
published review head, `lib/storage/write-intent.js:39–46` imports Mongo/server/API
helpers; `postgres-collection-intent.js` translates Mongo-shaped predicates;
`lib/server/storage-reads.js:34–56` and API3 Collection expose trusted injection.
These are portability hypotheses, not reproduced runtime defects.

Reconcile the existing [storage seam interface](nightscout-storage-seam-interface-2026-09-14.md)
and [write contract](write-contract-spec-2026-10-07.md) with current code; update
their applicable contract sections rather than create competing definitions.
Add concise module-facing documentation and parameterized tests against actual
Mongo and PG ports. Specify:

- Typed stored identity versus shown `_id`/`identifier`; missing/null/zero/false,
  ordering, natural-order/import requirements and supported document representation.
- Query AST, projections, sort/limits and explicit unsupported operations. No
  silent coercion, field dropping or Mongo-wide emulation requirement.
- Per-item outcomes, resend/edit/delete/history, partial batch success and
  version-specific compatibility. Do not strengthen legacy preconditions silently.
- Tenant binding independently from transaction ownership; isolation evidence
  appropriate to the backend, with no implication that every backend offers RLS.
- Invalid submitted representation, unsupported query, conflict, unavailable
  dependency and internal failure; preserve approved v1/v3 status/reply differences.
- Logical intent events versus backend-specific instrumentation, commit/rollback,
  no-op outcomes, collapsed record lists and retry ambiguity.

**Predicted acceptance:** existing admitted Mongo/PG workflows retain replies AND
stored outcomes. Tests must distinguish absent/null values, identity kinds and
approved refusals. **Controls:** alter a projection/missing-value rule, cross-bind
a tenant handle, and falsify a write outcome; each corresponding semantic
assertion must fail. Declare read-only queue instruments and controls when built;
the planning card's no-gate is not a passing contract check.

## Composition and consolidation packets

`ARCH-SEAM-COMPOSE` separates the domain metadata currently combined with PG
factories/migrations in `lib/server/tenant-app/domain-catalogue.js:5–13`. Keep
backend schema/readiness in explicit backend composition. Serving startup checks
remain read-only; absent injected capabilities refuse rather than select Mongo.
Move PG/network failure recognition out of HTTP renderers, retaining narrow
submitted-document classification and current version-specific responses.

**Predicted acceptance:** the real CLI still boots the admitted PG preview and
default single still selects Mongo; unsafe/missing schema or partial ports refuse.
**Controls:** remove an injected intent capability, bind the wrong backend
catalogue, and misclassify an unavailable dependency as bad input. Actual startup
or HTTP assertions must detect the intended symptom. Do not accept import-count
or source-text-only tests as proof of runtime behavior.

`ARCH-SEAM-CONSOLIDATE` compares `postgres-entries-intent.js` with
`postgres-collection-intent.js` and the repeated tenant domain error wrappers.
Extract only demonstrated common projection/filter/transaction/event behavior.
Keep entries-specific/source-specific validation, legacy patterns, natural order,
normalization and duplicate/race outcomes explicit. Relocate portable identity
and result helpers out of Mongo-named modules incrementally, preserving legacy
BSON compatibility where required. Do not combine a refactor with new write policy.

**Predicted acceptance:** existing direct single/PG corpus and historical RC
comparison retain their classifications, with no unexplained differences.
**Controls:** change a legacy ordering rule and emit a logical event before a
forced commit failure; tests must catch changed selection and false commit.
Compatibility lanes own corpus expansion; this lane consumes their accepted
baseline rather than forking another compatibility policy.

## Execution-profile packet: ST-VIEWS-PROFILE / PR #8891

Adopt the existing branch; do not reimplement its scheduler or calculations.
Confirm current PR head/task status, refresh against current dev in an owned
worktree, and inventory overlap with #8898 before choosing a join. No merge to the
shipping candidate or production enablement is authorized by scheduling this work.

Keep the explicit single/nonresident entrypoint separate from default resident
single and the multitenant API preview. Resolve the PR's open subscriber choice
against the existing D-EVENT contract: logical per-intent events are the target
to evaluate; a subscriber change requires measured no-op/resend/batch behavior.
Keep the timer for time-driven alarms. A timer does not replace reliable write
delivery. Retained properties represent the last evaluation cycle; request-time
recomputation must not silently substitute for that freshness contract.

**Predicted acceptance:** fresh replay through the profile's actual trigger
matches the resident baseline for alarms/properties except explicitly decided
differences. Run the execution plan's §7b alarm cohorts, WRITE_RESEND variants,
quiet/no-upload stale alarms, retained-properties freshness, teardown and revert.
Old prototype replay/cost figures are historical; new cost remains UNMEASURED
until a quiet-hardware run. Release placement remains a separate maintainer call.

**Controls:** suppress the timer and observe the missing time-driven alarm;
suppress the selected write trigger and observe a missed write-driven cycle;
shrink the device-status window and observe incorrect derived output; substitute
request-time properties and detect freshness divergence. Restore and rerun.
Actual notification delivery and durable multitenant recovery require their own
gates; local replay does not establish either.

## Shared frame join and multitenant recovery

`ARCH-DERIVED-FRAME` inventories `lib/data/views/index.js`, tenant
`snapshot.js`, `derived-frame.js`, `derived-reads.js` and #8891 `nonresident.js`.
Share bounded acquisition, data transformation and shipping calculation code.
Retain explicit policies for REST authorization, all-or-error responses, plugin
selection, retained evaluator properties and notification request handoff.
REST reads must not execute notifications or connector egress.

Distinguish the evaluation instant from a consistent database revision. Current
multi-read acquisition does not itself promise a cross-collection snapshot.
Characterize concurrent writes before selecting stronger consistency. Define
tenant/settings-version/plugin/frame identity and bounded lifetime for any
retained result; no process-global mutable clinical frame.

**Predicted acceptance:** identical admitted inputs produce the intended
properties/alarms through resident, nonresident and tenant REST paths, with
documented lifecycle differences. **Controls:** cross-bind a frame, inject a
partial read failure, change a clinical property setter and enable egress during
a read. Isolation, complete-response, derived-value and no-egress assertions must
each fail. Test concurrent updates and report the observed consistency boundary.

Existing `MT-RUNTIME-PLAN` remains the M5 home. Before multitenant evaluation or
realtime enablement, accept commit-coupled durable checkpoints, ordering,
duplicates, hard/soft deletes, config/grant invalidation and restart catch-up.
Own ack/snooze, scheduling and retained properties per tenant. Verify crash after
commit/before publish, duplicate replay, idle wake, ownership loss and current
authority after reconnect. A local EventEmitter and a cell lease cannot establish
these application guarantees. Provider selection remains open.

## Shared-frame inventory and next characterization

**Read-derived**, pinned to independent R47 `0c98ad06` and tenant REST R44
`bc4ee1a9`. This inventory prepares `ARCH-DERIVED-FRAME`; no shared implementation
or stronger consistency contract is accepted.

| Boundary | Observed source | Next characterization |
|---|---|---|
| Acquisition and materialization | `lib/data/views/index.js:121-219` reads bounded domain unions and creates private loader/ddata/cache with frame:false. `lib/server/tenant-app/snapshot.js:15-75` validates tenant-bound ports, accumulates read failures and creates private state with frame:true. | Compare identical admitted inputs under explicit bounds/frame/error policy before sharing the lower private working-set primitive. |
| Calculations and effects | `views/index.js:228-289` runs per-view properties and notification phases. `tenant-app/derived-frame.js:8-30` selects property setters and propagates errors, without notification phases. | Share only demonstrated property/sandbox mechanics; REST reads must remain free of evaluator/connector egress. |
| Lifecycle and identity | `lib/server/nonresident.js:138-219` retains the last cycle across write/timer triggers and hands requests to long-lived process-local notification state. `serve/preview-domains.js:124-143` prepares a request-local tenant frame. | Keep retained freshness, ack/snooze/scheduler state and HTTP all-or-error behavior explicit. Bind any future retained multitenant result to tenant/settings/plugin policy, evaluation instant and bounded lifetime. |
| Consistency, failure and statistics | Neither acquisition module declares a shared database revision. Failed evaluator cycles retain previous properties; failed REST reads refuse the response. Tenant statistics exclude shared index bytes; replay fixtures use fixed synthetic statistics. | Run concurrent-write characterization and partial-read controls. Do not infer snapshot consistency, shared stats equivalence or current cost/freshness. |

Predicted entry bar: admitted resident/nonresident/tenant REST inputs preserve
approved derived values with documented lifecycle differences. Cross-bound frame,
partial read, incorrect property setter and read-egress controls must each fail.
Keep logical no-op admission and durable commit-coupled recovery separate. Broader
socket status/read paths still assume resident data; test-only v1 writer replay
does not admit that transport or join the profile into REST.

## Reproduced frame acquisition and concurrent reads

The R49 REST frame lane exercises shipping views, tenant snapshots and resident
loader frame modes over actual MongoDB and PostgreSQL wrappers. Selected current
BG, direction, uploader battery and IOB values agree on the admitted corpus.
This establishes a bounded comparison, with these measured differences retained:

- Alarm acquisition keeps twelve SGVs plus MBG/calibration; property acquisition
  keeps fifteen SGVs within two days. Tenant frame mode excludes future records;
  the unframed loader includes them. Food/activity, old sensor/pump records and
  per-kind device-status bounds retain their existing path-specific policies.
- Raw ObjectId and same-spelling string identities are fetched separately. The
  computed-view union collapses that spelling while the framed loader retains
  both fetched rows. This characterization does not prescribe an identity fix.
- Views and tenant snapshots reject a statistics error; resident loading logs it
  and continues with empty statistics. Tenant-local statistics exclude shared
  index bytes. Private acquisition leaves the caller's cache/ddata untouched.

The actual tenant HTTP concurrency fixture pauses a treatment SELECT before
execution, completes an entries SELECT, then commits both updated domains in one
independent PostgreSQL transaction. The response contains old entries and new
treatments. Before/after responses and tenant B remain separately asserted.
**Reproduced:** parallel reads do not provide a common database revision. Real
permission and missing-relation failures refuse the entire response; read paths
make no additional network connection outside the owned loopback services.
Tenant binding, input bounds, clinical values, private cache, partial-read refusal
and read-egress controls each have explicit semantic break-it checks in R49.

Independent R50 exercises actual nonresident materialization over MongoDB with
read barriers and raw writes that emit no process event. The selected ordering
retains entries A/treatments B, then a real marker write refreshes B/B. A callback
fault injected after real rows arrive retains the complete previous result and
its timestamp; the next real trigger recovers. The teardown check proves no late
fake-provider delivery/listener remains. It does not prove database cancellation,
absence of an internal handoff, or immutable closed evaluator state.

No production frame extraction, stronger snapshot consistency, settings/plugin
version key, logical no-op subscriber policy, durable recovery or M5/M6 admission
is accepted by these fixtures. Next extract the measured private acquisition
primitive behind explicit bounds/frame/statistics/error policies, preserve the
REST all-or-error and evaluator retained-result boundaries, and rerun the same
controls. Any stronger consistency policy needs its own implementation and test.

## Integration and merge boundaries

For the bounded #8898 preview, prioritize contract review, capability/refusal
characterization and the composition split before declaring the seams stable.
Do not make the complete helper extraction, #8891 wiring, durable M5/M6 or a
third backend blanket prerequisites for merging that preview. No new 16.0.0 tag
gate is created here. Role-specific acceptance gates continue to govern enablement.

Every dispatch names current tree/task, predicted green assertions and exact
negative symptoms. Standing instructions: **confirm the head commit and that the
task is still open before starting**; **stop and report a mismatch rather than
reaching for the nearest thing that works**. Reserve shared files, use owned
databases/services and synthetic data, and join at one immutable cumulative head.
Run affected and full suites, meaningful controls and final prcheck for CRM fixes.
Only the maintainer pushes or sends upstream correspondence.

## Deferred SQLite/celld experiment

`ARCH-SQLITE-SPIKE` is low priority, unassigned and not dispatched. Revisit after
the seam work and evaluator/REST priorities, with an explicit scheduling choice.
An eventual probe would implement entries/treatments under the same conformance
corpus, first local SQLite and then a trusted cell boundary. Preserve existing
lab work; do not migrate the app runtime or select celld operational guarantees
through this hypothetical. No SQLite implementation or performance acceptance
is claimed.
