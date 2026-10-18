# Plan conformance case format

Cases for the [plans specification](../../../../docs/30-design/platform/spec/plans.md), rules
PN1–PN16, checked by `tools/nsschema/test_plans.py` against the reference in
`tools/nsschema/plans.py`. Every case is synthetic and its expectations are written by hand from
the specification, not from the reference. A plan case uses everything in the
[command case format](../commands/FORMAT.md) (instances, declares, subjects, the command,
fetch, enact, report, evaluate, withdraw and reject calls), and adds:

```yaml
# Synthetic. SPEC-PLANS; plans §N. Times are seconds; expectations authored by hand.
maxProposalSeconds: 1209600            # optional, default 14 days: PN1
maxPlanSeconds: 2592000                # optional, default 30 days: PN4
maxAdvanceApprovalSeconds: 43200       # optional, default 12 hours: PN13
riskClasses:                           # per product, element kind: R0-R6; undeclared is R4 (PN3)
  ControllerA: {eatingSoon: R1, mealBolus: R4, schoolOverride: R2, basalProfile: R5, maxBolus: R6}
channelVersions:                       # per tenant, product, channel: [[from, version], ...] (PN7)
  A: {ControllerA: {override: [[0, v1], [500, v2]]}}
instances:
  i-ctl-a:
    definitionId: sha256:d-a
    definitionChanges: [[400, sha256:d-a2]]   # optional: the instance renews under another definition
    sinks: {example/plans: [0, null]}         # the product's plan channel
calls:
  - {at: 10, kind: proposePlan, tenant: A, subject: s-agent, instance: i-agent,
     channel: example/plans, product: ControllerA, expiresAt: 5000,
     basedOn: {override: v1},          # channel -> that channel's state version
     plan:
       elements:
         - {id: soon, kind: eatingSoon, channel: override, path: standing, content: {...}}
         - {id: meal, kind: mealBolus, channel: example/bolus, path: standing, content: {...},
            standingConditions: {mitigation: reduced-portion,
                                 withdrawal: [{signal: location, evaluatedBy: controller}]}}
       trigger: {...}                  # stored unread
       startsAt: 100
       endsAt: 100000
       requiredReviews: [risk-check]}
  - {at: 20, kind: evaluate, tenant: A, subject: s-risk, proposal: p1, review: risk-check, note: text}
  - {at: 30, kind: approvePlan, tenant: A, subject: s-person, proposal: p1,
     accepts: [{element: soon, hash: <sha256 of the element's canonical JSON>}]}
  - {at: 40, kind: report, tenant: A, subject: s-ctl-a, command: c1, state: succeeded}   # PN9
  - {at: 50, kind: confirm, tenant: A, subject: s-agent, instance: i-agent, plan: p1,
     occurrence: d1, occursAt: 3600}
  - {at: 60, kind: approveOccurrence, tenant: A, subject: s-person, plan: p1, occurrence: d1,
     occursAt: 3600, element: meal, hash: <...>}
  - {at: 70, kind: skip, tenant: A, subject: s-person, plan: p1, occurrence: d2}
  - {at: 80, kind: planReport, tenant: A, subject: s-ctl-a, plan: p1,
     occurrence: d1, occurrenceState: ran}            # or planState: ended
  - {at: 90, kind: endPlan, tenant: A, subject: s-person, plan: p1}
  - {at: 95, kind: readPlan, tenant: A, subject: s-follower, plan: p1}
expected:
  calls:
    - {status: 201, proposalId: p1}                                   # proposePlan
    - {status: 201, commandId: c1, state: pending}                    # approvePlan, confirm,
                                                                      # approveOccurrence, skip, endPlan
    - {status: 200}                                                   # planReport
    - {status: 200, state: active, accepted: [soon], declined: [meal],
       occurrences: {d1: ran}}                                        # readPlan
    - {status: 422, code: standing-conditions-required}               # a refusal
  commands: {c1: {state: fetched, destination: i-ctl-a}}              # at `end`
  proposals: {p1: {state: approved}}
  plans: {p1: {state: active, accepted: [soon], declined: [meal], occurrences: {d1: ran}}}
```

The plan id is the proposal id. Element hashes: write `hash: element:<id>` to mean "the hash of
element `<id>` of the plan as proposed", and `hash: wrong` for any other value; the test resolves
`element:<id>` before replaying the calls, so expectations never carry computed hashes. Command ids
are assigned in order across every call that creates one, as in the command format. The mirror
(`plans:`) is listed for every approved plan at `end`. `declined` lists the plan's element ids
that the approval did not name, in the plan's order.
