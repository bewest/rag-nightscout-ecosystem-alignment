# Derived output ownership: evaluator, realtime and HTTP

*Contributor-facing decision preparation, 2026-11-07. Read-derived source review,
not a reproduced defect or an adopted serving change. Homes: `ARCH-DERIVED-FRAME`
for calculation/output contracts; `MT-RUNTIME-PLAN` for ownership and delivery.
The [seams plan](architecture-seams-execution-plan-2026-11-05.md#shared-frame-join-and-multitenant-recovery)
owns the existing shared-code direction. This note defines its output-publication
follow-up, without changing single-tenant behavior or enabling a service.*

## Source anchors and observed boundaries

Inspected application `9298d79305e941fcfd36effa594e0e0bccf79994`; alignment base
`6114cfecf5a6bc4bdcefb161a04a7ded45d3af0d`. References below are application
paths at that source, not a claim about a later integrated head.

| Consumer | Source and operation | Output and effects |
|---|---|---|
| Evaluator | `lib/data/tenant-projection-evaluator.js` acquires a durable projection, materializes properties and calls `views.evaluateCycle`; `lib/data/views/index.js:282` returns one calculation pass | Properties plus requested/emitted notification results. Latest evaluated output is process-local; notification consumer state/outbox are separate durable boundaries. |
| Realtime | `lib/server/realtime/projection.js:17` reconciles its own projection, `:26` loads a tenant snapshot, `:29` builds `dataWithRecentStatuses()` | Browser data frame and recovered rows/checkpoint. It does not call `evaluateCycle` or `derived-frame`; independent input acquisition is not a duplicate full alarm cycle. |
| Derived HTTP | `lib/server/tenant-app/snapshot.js` loads request inputs; `derived-frame.js` runs selected plugin property setters | Properties computed for a request, without notification/connector phases. Property-setter errors propagate; the code explicitly distinguishes this from evaluator error policy. |

`lib/data/ddata.js:128` shows that the realtime data frame contains admitted
records/statuses, not the evaluator's entire property result. Replacing it with
properties alone would change the client contract. Independently recovered
projections can also have different checkpoints and evaluation instants. No
same-revision guarantee follows from using common calculation code.

## Assessment and recommended direction

There is overlapping acquisition/transformation and property computation between
some paths, but source inspection does not reproduce a performance defect or a
clinical disagreement. The architecture risk is unclear result identity and
freshness/failure policy, or accidental re-execution of effects when sharing a
calculation. Retain consumer-specific wire shaping and authorization.

Recommended next boundary: define an immutable, versioned evaluated-result
contract and compare it with request-local calculation before selecting a shared
materialization service. Keep calculation code shared where semantics agree.
Publishing reusable results is a separate architecture change from sharing code:
it adds producer availability, result freshness, restart and ownership dependencies.
Transport may be a database-backed materialization, authenticated request API or
durable publication; none is selected here. Wake-ups alone are not stored results.

Candidate identity must include tenant, input checkpoint/projection identity,
settings and plugin/calculation versions, input-bound/frame policy, evaluation
instant, producer generation and output revision. A checkpoint alone does not
identify time-derived results or establish an atomic all-domain revision.
Publication must describe completeness, freshness/expiry and calculation errors.
Normal notification effects remain separate from reusable read data. Consumers
still apply current authority and endpoint-specific field/secret filtering.

## Ordered work and ownership

The [bounded characterization](../../../reports/tenancy/derived-output-2026-11-07/README.md)
now records actual f0 evaluator/realtime/API comparisons, instrumented costs,
semantic controls and physical closure. It supports scoped reuse, not a
publication-service decision or distributed admission.

1. **ARCH-DERIVED-FRAME owner: characterize overlap.** Compare actual evaluator,
   realtime data frame and HTTP properties with identical synthetic inputs,
   settings and explicit instants. Inventory which calculations execute, and
   measure CPU, query volume, retained memory, result size and observable values.
   Do not infer duplicate cost from a shared function name.
2. **Same owner: prepare publication decision.** State per-endpoint freshness,
   completeness/error and evaluation-time requirements; identify reusable results
   versus raw rows/consumer wire shaping. Compare request-local calculation with
   a versioned materialized result, including producer outage behavior. Keep
   historical/on-demand views and current time-driven alarm work explicit.
3. **MT-RUNTIME-PLAN owner: define publication ownership if selected.** Specify
   tenant/partition assignments, fencing, handoff, durable output recovery,
   settings invalidation and retry boundaries. Existing local runtime generation
   checks do not fence another process. Deployment versus StatefulSet does not
   implement this contract.
4. **Integration owner: join only the selected bounded implementation.** Verify
   journey-map equivalence over API reads, socket frames, writes, reconnect,
   alarm acknowledgement and restart. Preserve single-tenant behavior, current
   authority, no-egress reads and existing protocol limitations. Run broader
   acceptance on the coherent joined candidate, not after each preparation step.

Required semantic controls: cross-tenant result substitution; stale settings or
plugin version; incorrect calculation; a time tick incorrectly reusing a result
identified only by data checkpoint; partial-input success; obsolete-owner
publication; producer failure after input commit but before output publication;
hard deletion missing from a reused frame; accidental notification/connector
egress from a read; and restored ordinary journeys after each break. Explicitly
test refused versus stale-labeled versus synchronous-refresh behavior once chosen.
Duplicate external delivery must not be described as exactly-once.

Publication implementation, transport selection, operating budgets and policy
adoption remain UNMEASURED. Existing recorded functional runtime evidence is not invalidated by
this follow-up; it does not establish these additional publication guarantees.
