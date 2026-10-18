# Command journeys: plans, confirmations and moment commands for one pump with many orchestrators

*What this is: a journey map (contributor-facing). Read after the
[command queue and planning note](command-queue-and-planning-2026-10-18.md), whose use cases and §5
decisions it walks step by step; it leads to the [commands specification](spec/commands.md), where
the needs it finds would be written.* **Snapshot — describes 2026-10-18. Status: proposed.**

Each journey follows the format of the [15.0.9 journey map](../../60-research/remedial/journey-map-15.0.9.md):
who is involved, then numbered steps. Each step names its level (policy, confirmation, moment or
algorithm, as in the note's §3), then **Do** (what happens), **Working** (what correct looks like),
**Watch for** (the failure a tester or reviewer looks for) and **Contributor** (the rules that apply,
the existing conformance case under `specs/sync/conformance/`, the unsafe control actions from the
[control-loop analysis](spec/control-loops.md#4-the-loops), and what is **not specified**, with the
open item or decision it needs). Claims about a named controller are read-derived, as in the note.

The journeys follow the maintainer's decisions of 2026-10-18 (note §5): a controller enacts each
`commandId` at most once; plans run on the controller and the hub keeps a read-only mirror; a plan or
proposal may require named reviews before approval; the person may withdraw or cancel any item on
their own therapy; followers read the queue; an adjustment is a new proposal, and an approval may
accept a plan in parts, naming the elements it accepts. The dose check stays open: each journey
shows which choice serves it.

## Words used here

| word | meaning |
|---|---|
| **queue item** | a proposal, a plan or a command on one tenant's channel, with its state |
| **plan** | a recurring intent with its trigger, conditions, bounds and end date, approved once and held and run by the controller (note §3) |
| **element** | one separately acceptable part of a plan, such as an eating-soon target or a meal entry |
| **occurrence** | one run of a plan, such as Tuesday's lunch |
| **confirmation** | a small command against one occurrence, sent hours ahead and bounded by the plan |
| **mirror** | the hub's read-only copy of a plan and its occurrences, written from the controller's reports |
| **since check** | comparing what changed (doses, carbs, intents, the definition) since an item was made |
| **hub refuses** | the open dose-check choice in which the hub refuses an approval when doses or carbs arrived after the proposal's `basedOn` |
| **controller decides** | the other choice: the hub shows doses and carbs since in the outstanding list, and only the controller refuses |

## The people

| role | does | who, in these journeys |
|---|---|---|
| proposer | drafts an item (CM11, CM12) | an agent with calendar, location or activity access; a clinician; a caregiver; the person |
| evaluator or reviewer | attaches evidence (CM16); a *required* reviewer must do so before approval (not specified) | a risk-check agent, a second agent, a caregiver, a clinician |
| approver | turns an item into a command or an active plan (CM13, CM14) | the person, or a delegate under a grant ([authority §7](spec/authority.md#7-delegation-not-decided)) |
| the person | may approve, adjust (by a new proposal), withdraw or cancel any item on their own therapy | the person with diabetes, or a parent for a young child |
| enactor | the singleton controller holding the channel's `command-sink`; validates, enacts once, reports | the AID app on the person's phone ([authority §6](spec/authority.md#6-who-may-receive-a-command)) |
| follower | reads the queue, the mirror and outcomes; never acts | a partner, a school nurse with read access, a watch app |

---

# Part 1: planning journeys

## PL1. A weekday lunch, planned from the calendar and location

| proposer | reviewer | approver | the person | enactor |
|---|---|---|---|---|
| a planning agent | a risk-check agent; a caregiver | the person | approves in parts; may skip any day | the controller |

**PL1.1 · policy · The agent drafts the plan.**
- **Do:** the agent sees the usual lunch at the usual time and place over past weeks and proposes a
  plan with two elements: an eating-soon target before lunch, and the usual lunch carbs with their
  meal bolus; weekdays only, each occurrence needing a confirmation that morning, with an end date.
- **Working:** the queue shows one open plan proposal: its elements, trigger, bounds, end date, the
  proposing agent and its expiry, and an evaluation saying in words why (no calendar entries).
- **Watch for:** calendar titles or places in the proposal or evaluation; a plan with no end date.
- **Contributor:** CM11, CM12 (`propose-with-permission-and-role`, `propose-without-role`), CM16,
  [authority DR7](spec/authority.md#7-delegation-not-decided); UCA-PROP-001, UCA-PROP-004. Not
  specified: the plan object and its element grammar (commands §9 item 3); a plan's lifetime
  versus CM11's `expiresAt`, which CM3's `commands.maxExpirySeconds` bounds (§9 item 1).

**PL1.2 · policy · Required reviews.**
- **Do:** the plan names two required reviews: a risk-check agent and a caregiver. Each attaches an
  evaluation.
- **Working:** approval is unavailable until both are attached; each review shows who made it.
- **Watch for:** an approval accepted with a required review missing; a review that changes the
  proposal's state.
- **Contributor:** CM16 (`evaluation-does-not-change-proposal`, `evaluate-without-read`);
  UCA-PROP-011. Not specified: required reviews (decision 3), a refusal for approving without them,
  and who may name them.

**PL1.3 · policy · The person accepts part of it.**
- **Do:** the person accepts the eating-soon element and declines the meal element, preferring to
  bolus at the table.
- **Working:** the approval names the element accepted and the hash it binds to; the declined
  element is recorded as declined; one plan, with one element, reaches the controller.
- **Watch for:** the declined element reaching the controller; an approval refused because the
  person's intents changed between drafting and approval (an unrelated override).
- **Contributor:** CM13 (`approve-hash-mismatch`), CM14 (`self-approval-refused`), CM15
  (`approve-state-changed`); UCA-PROP-003, UCA-PROP-006. Not specified: partial acceptance
  (decision 4); CM13 makes one command whose payload is the proposal's byte for byte, so the
  accepted subset needs its own hash rule. CM15 compares the whole intent state version, which a
  plan drafted days earlier rarely matches: whether `basedOn` applies to a plan at all is open.

**PL1.4 · policy · The controller takes the plan; the hub mirrors it.**
- **Do:** the approval becomes a command; the controller validates the plan against its own
  limits, stores it, reports `succeeded`, and reports the plan for the mirror.
- **Working:** the command reads `succeeded`; the mirror shows the active plan, its accepted
  element and the next occurrence; a redelivered copy of the command is not stored twice.
- **Watch for:** the mirror showing the proposal's content rather than what the controller holds;
  the plan stored again after a push and a fetch.
- **Contributor:** CM1, CM7–CM10, CM18, CM21 (`enact-identical-payload-succeeds`,
  `enact-hash-mismatch-refused`, `enact-push-then-fetch-once`); UCA-CMD-006, UCA-PROP-008. Not
  specified: the mirror's carrier, which needs a controller-owned plan kind declared under S2 and
  S9 and written by the instance's `source` role ([registration §9](spec/registration.md#9-channels-roles-and-provenance)).

**PL1.5 · confirmation · The morning confirmation.**
- **Do:** at a set hour the agent reads today's calendar and location and confirms today's
  occurrence, with an evaluation of one line ("lunch on the calendar, at the usual place").
- **Working:** a confirmation command for this occurrence, expiring before the occurrence, appears
  in the queue; the mirror shows the occurrence as confirmed.
- **Watch for:** a confirmation carrying anything outside the plan's bounds; a confirmation for a
  plan that was cancelled; an agent able to send commands outside plans.
- **Contributor:** CM3, CM4, CM12; UCA-AUTH-002, UCA-AUTH-003. Not specified: the confirmation as
  an object, and whether an approved plan authorises its proposer to confirm without a further
  approval (a grant: [authority §7](spec/authority.md#7-delegation-not-decided), commands §9 item 5).

**PL1.6 · moment · The lunch is cancelled.**
- **Do:** the meeting runs over; the person skips today's occurrence from the phone or the hub.
- **Working:** the confirmation is `cancelled` if not handed over, or the controller drops the
  occurrence and reports it; tomorrow's occurrence is untouched.
- **Watch for:** a skip that ends the whole plan; a skip read as done before the controller reports.
- **Contributor:** CM2, CM3; UCA-CMD-015, FB-CMD-001. Not specified: cancel (§9 item 7) and skipping
  one occurrence of a held plan.

**PL1.7 · algorithm · The occurrence runs.**
- **Do:** at the planned time the controller starts the eating-soon target, after its own checks
  of what was dosed and eaten since the confirmation.
- **Working:** the hub shows the target active, with initiator `{value: other, controllerTerm}`
  naming the plan, and the mirror links the occurrence to its intent.
- **Watch for:** the target shown as applied when only requested; the target started twice.
- **Contributor:** S8, S10, A2, A3, A10, A12 (`active-state/requested-and-applied`); FB-STATE-004,
  UCA-CMD-010. Not specified: the field linking an intent to its plan occurrence.

## PL2. Exercise from the calendar

| proposer | reviewer | approver | the person | enactor |
|---|---|---|---|---|
| a planning agent | none required | the person | may cancel any session | the controller |

**PL2.1 · policy · Plan proposed and approved whole.** The agent proposes a temporary target
before calendar entries marked as exercise, confirmed by location or activity; the person approves.
**Working:** one active plan in the mirror; the week's occurrences `scheduled`, not `active` (S4).
**Contributor:** CM11–CM15, S4. Precedent: AndroidAPS automation triggers on time, location and
activity and can start a temporary target (note §3). Not specified: the plan object.

**PL2.2 · confirmation · Confirmed by activity.**
- **Do:** the agent sees the person arrive at the gym and confirms the occurrence.
- **Working:** the confirmation is within the plan's bounds and expires soon after the session's
  start; the evaluation says "at the usual place", not where.
- **Watch for:** location data in the queue; a confirmation arriving after the session ended.
- **Contributor:** CM3, CM16, DR7; UCA-CMD-003. Not specified: as PL1.5.

**PL2.3 · confirmation · The session does not happen.** The entry stays on the calendar; the
person stays home; no confirmation is sent. **Working:** the occurrence ends unconfirmed and nothing
is enacted. **Watch for:** an occurrence run without a required confirmation. **Contributor:** HAZ-1.
Not specified: an unconfirmed occurrence's end reason (S5 has `expired` and `other`).

**PL2.4 · algorithm · Two intents at once.**
- **Do:** the target starts while an override the person set is active.
- **Working:** the hub reports both, with their initiators; the controller's combined result, if
  it publishes one, is the only composed value shown.
- **Watch for:** the hub computing a combined target, or ending one intent with the other.
- **Contributor:** S1, S3, A1, A9 (`active-state/exclusive-overlap-reported`); FB-STATE-003.

## PL3. A caregiver's week of school overrides

| proposer | reviewer | approver | the person | enactor |
|---|---|---|---|---|
| a parent | a school nurse (follower, may evaluate) | the second parent | a teenager, may cancel | the controller |

**PL3.1 · policy · A week planned on Sunday.**
- **Do:** a parent proposes five occurrences of a preset override around the timetable's sports
  lessons, referring to the preset by its controller id.
- **Working:** the proposal records the destination's `definitionId`; the nurse can read it.
- **Watch for:** a preset referred to by a name the controller can rename.
- **Contributor:** CM11, S9 (`idField`, `referencedBy`); UCA-PROP-008. Not specified: follower read
  of plans (decision 3; CM11 reads need `api:proposals:read` or `api:commands:create`).

**PL3.2 · policy · The other parent approves.**
- **Do:** the second parent approves; the proposing parent could not.
- **Working:** one approval, one command, the plan held by the controller and mirrored.
- **Watch for:** two approvals at once creating two plans.
- **Contributor:** CM13, CM14 (`self-approval-refused`, `approve-approved-proposal`);
  UCA-PROP-009, UCA-PROP-013. Not specified: a caregiver approving a plan they made alone, which
  CM14 refuses and a grant could allow (§9 item 5); atomic approval (§9 item 7).

**PL3.3 · policy · Wednesday changes.** A school trip moves Wednesday's lesson; the parent
proposes an adjusted plan, a new proposal. **Working:** once approved it replaces the held plan, and
the mirror shows which plan is current. **Watch for:** both plans running on Wednesday.
**Contributor:** decision 4; S3 `supersedes`, A7. Not specified: how a new plan ends the one it
adjusts (plan supersession, or cancel then approve).

**PL3.4 · algorithm · The controller was updated midweek.**
- **Do:** the app updates and renews under a new definition in which the preset changed.
- **Working:** the controller refuses Thursday's occurrence with a reason the hub records, and the
  parents see it.
- **Watch for:** the occurrence enacted under the changed preset with no notice.
- **Contributor:** CM8, S12, [registration §8](spec/registration.md#8-instances); UCA-PROP-008.
  Not specified: whether the hub checks `definitionId` at approval (§9 item 7) and how a held plan
  reports an occurrence it refused.

## PL4. A sensitivity plan for illness or a cycle phase, with an end date

| proposer | reviewer | approver | the person | enactor |
|---|---|---|---|---|
| a planning agent | a named human reviewer (a clinician or caregiver) | the person | may end it early | the controller |

**PL4.1 · policy · Proposed with an end date and a disclosure.**
- **Do:** the agent proposes a sensitivity change for the coming days, ending on a date, labelled
  for display with the effect only.
- **Working:** the queue shows the effect and the end date; the reason is visible only as the
  person's disclosure allows.
- **Watch for:** the motivation (illness, cycle phase) shown to followers.
- **Contributor:** CM11; [state and intent §5](spec/state-intent.md#5-effect-and-motivation-proposed)
  (`disclosure`, proposed, not adopted). Not specified: disclosure on queue items and the mirror.

**PL4.2 · policy · A required human review, then approval.** The reviewer attaches a review and
the person approves; **Working** and **Contributor** as PL1.2–PL1.4.

**PL4.3 · algorithm · Runs and ends.** The controller applies the change each day and reports it.
**Working:** active each day, ended `expired` after the end date. **Contributor:** S5, A4, A12.

**PL4.4 · moment · The person ends it early.**
- **Do:** feeling better, the person cancels the plan.
- **Working:** the controller ends the active change with `cancelled` and stops future occurrences;
  the mirror shows the plan ended by the person.
- **Watch for:** future occurrences still listed; the change still active on the pump.
- **Contributor:** S5, A5. Not specified: the person's standing to cancel an item someone else
  proposed (decision 3), and cancelling a held plan, which is a request to the controller.

## PL5. A clinician's settings proposal for the next visit

| proposer | reviewer | approver | the person | enactor |
|---|---|---|---|---|
| a clinician | a risk-check agent; the person's caregiver | the person, at the visit | approves in parts | the controller |

**PL5.1 · policy · Proposed weeks ahead.**
- **Do:** the clinician proposes changes to several settings, to be discussed at a visit weeks away.
- **Working:** the proposal is readable to the person and the reviewers until the visit.
- **Watch for:** the proposal expiring before the visit, or a hub limit raised so far that every
  command could live that long.
- **Contributor:** CM11, CM3 (`proposal-expiry-too-long`); UCA-AUTH-006. Not specified: a proposal
  expiry separate from the command's (§9 item 1), and a clinician's propose role (§9 item 1).

**PL5.2 · policy · Reviews before the visit.** A risk-check agent compares the proposal with
recent history; a caregiver adds notes. **Working:** evaluations attached, none changing the
proposal. **Contributor:** CM16; as PL1.2.

**PL5.3 · policy · Accepted in part at the visit.**
- **Do:** the person accepts one setting change and declines the others.
- **Working:** the approval names the accepted element; the declined ones stay on record.
- **Watch for:** a `state-changed` refusal because an override started that morning.
- **Contributor:** CM13, CM15; as PL1.3.

**PL5.4 · algorithm · The controller applies it** under its own limits. **Working:** its next
settings upload shows the change; the command reads `succeeded`. **Watch for:** the hub's stored
settings changed before the controller reports. **Contributor:** CM7, S10, D18. Not specified: a
settings change is not a span intent, and no controller declares accepting one as a command.

---

# Part 2: moment journeys

## C1. A correction bolus for a child at school

| proposer | reviewer | approver | the person | enactor |
|---|---|---|---|---|
| — | — | a parent (sends directly) | the child | the controller |

**C1.1 · moment · The parent looks before sending.**
- **Do:** the parent reads glucose, insulin on board and the outstanding list.
- **Working:** the list shows any command on the channel not yet final, and doses since the last
  upload are marked as possibly missing.
- **Watch for:** insulin on board from before a dose the controller already gave.
- **Contributor:** UCA-SYNC-SERVE-004, UCA-CMD-001. Not specified: list outstanding (§9 item 7).

**C1.2 · moment · Sends a correction bolus** with a `requestId` and a short expiry. **Working:**
one command, `pending` then `sent` or `fetched`; a retried send returns the first.
**Contributor:** CM1–CM5 (`request-id-same-payload-returns-first`, `expiry-required`).

**C1.3 · algorithm · Enacted once, after the controller's checks.**
- **Do:** the controller receives the command by push and again by fetch, checks hash, expiry and
  its own limits and recent doses, and enacts it once. Today Trio refuses a remote bolus when
  boluses since the command's timestamp reach a fifth of the request; Loop's remote bolus checks the
  amount and the one-time password and no doses since.
- **Working:** one bolus; the second delivery is recognised by `commandId`.
- **Contributor:** CM10, CM18, CM21 (`enact-push-then-fetch-once`, `enact-after-restart-once`);
  UCA-CMD-006, UCA-CMD-010.

**C1.4 · moment · The outcome.** The controller reports `succeeded`; later the pump fails the
delivery. **Working:** the parent sees the failure. **Watch for:** `succeeded` standing after it.
**Contributor:** CM9 (`report-after-final-refused`); UCA-CMD-013. Not specified: §9 item 4.

## C2. A meal sent, then not eaten

| proposer | reviewer | approver | the person | enactor |
|---|---|---|---|---|
| — | — | a caregiver | the child | the controller |

**C2.1 · moment · Carbs and bolus sent.** The caregiver sends the meal's carbs and bolus.
**Working:** one command per item, or one command whose parts are reported separately.
**Contributor:** CM1; UCA-CMD-011.

**C2.2 · moment · The meal is refused at the table.**
- **Do:** the caregiver cancels before the phone has fetched it.
- **Working:** the command reads `cancelled`, final, never handed over.
- **Watch for:** a cancel reported as done after the command was `sent`; there it is only a request.
- **Contributor:** CM2, CM3; UCA-CMD-015. Not specified: cancel and its state (§9 item 7).

**C2.3 · algorithm · Already handed over.**
- **Do:** the controller had stored the carbs and refused the bolus, as Trio's meal command can.
- **Working:** the outcome shows carbs entered and bolus refused, and the caregiver removes the
  carbs as a separate action.
- **Contributor:** CM9; UCA-CMD-011. Not specified: an outcome per part (§9 item 4).

## C3. Two caregivers act for one meal

| proposer | reviewer | approver | the person | enactor |
|---|---|---|---|---|
| — | — | a parent; a school nurse | the child | the controller |

**C3.1 · moment · Both send.** A parent and a nurse each send a meal bolus minutes apart.
**Working:** the second sender sees the first command in the outstanding list, with who sent it.
**Watch for:** two commands accepted with neither sender told. **Contributor:** CM4 matches within
one subject only (`request-id-scoped-to-subject`); UCA-CMD-001. Not specified: list outstanding.

**C3.2 · algorithm · The controller's check.** Enact once does not catch this: the commands have
different ids. Only the controller's doses-since check does, after the first bolus is stored.
**Contributor:** CM10; UCA-CMD-010; HAZ-1.

## P1. The person doses while a proposal is outstanding

| proposer | reviewer | approver | the person | enactor |
|---|---|---|---|---|
| an agent | — | a caregiver | doses on the phone | the controller |

**P1.1 · moment · Proposal made.** An agent proposes a correction bolus with `basedOn`.
**Contributor:** CM11.

**P1.2 · moment · The person boluses locally.** The dose reaches the hub one upload later.
**Contributor:** A12 covers intents, not doses; FB-STATE-006.

**P1.3 · moment · The caregiver approves.**
- **Working:** the approver sees the dose since `basedOn`, or the approval is refused.
- **Watch for:** an approval passing CM15 after the dose (UCA-PROP-012).
- **Contributor:** CM15 (`approve-state-unchanged`). Not specified: the dose check (§5, still open).
  *Hub refuses* catches a dose already uploaded; *controller decides* catches it at enactment on a
  controller with a since check.

## P2. The person sees and withdraws or cancels

| proposer | reviewer | approver | the person | enactor |
|---|---|---|---|---|
| an agent; a caregiver | — | — | withdraws and cancels | the controller |

**P2.1 · any · Opens the queue.** The person sees proposals, plans and commands on their channels.
**Contributor:** CM6, CM11. Not specified: the list (§9 item 7).

**P2.2 · any · Withdraws an agent's proposal.** **Working:** the proposal reads `withdrawn`.
**Contributor:** CM14 (`withdraw-by-other-subject`) allows only the proposer to withdraw, which
decision 3 overrides for the person; not specified: who counts as the person (a subject bound to the
therapy's owner).

**P2.3 · any · Cancels a caregiver's command.** As C2.2.

## A1. Carbs proposed from a photo of the meal

| proposer | reviewer | approver | the person | enactor |
|---|---|---|---|---|
| an agent | a risk-check agent | the person | adjusts | the controller |

**A1.1 · moment · Proposed.** The agent proposes carbs with an evaluation of its estimate.
**Watch for:** units or product misread on the approval screen. **Contributor:** CM11, CM16;
UCA-PROP-004. Not specified: payload grammar (§9 item 3).

**A1.2 · moment · The person adjusts.** The adjusted amount is a new proposal (decision 4). Because
the person made it, CM14's `self-approval` refuses their own approval; the person sends it as a
command instead and withdraws the agent's. **Contributor:** CM14.

**A1.3 · algorithm · Enacted.** The controller checks carbs since; Trio refuses when newer carbs
exist and misses a back-dated meal. **Contributor:** CM10; UCA-CMD-010.

## A2. A correction bolus proposed by an agent

| proposer | reviewer | approver | the person | enactor |
|---|---|---|---|---|
| an agent | a required risk check | the person or a delegate | may withdraw | the controller |

**A2.1 · moment · Proposed and reviewed.** The required risk check is attached.
**Contributor:** CM11, CM16; UCA-AUTH-002. Not specified: required reviews.

**A2.2 · moment · A controller preview.** **Working:** the approver sees the dose the controller
would give now. Only AndroidAPS's client-control prepare and commit offers this today.
**Contributor:** not specified (§9 item 2).

**A2.3 · moment · Approved.** **Contributor:** CM13–CM15; UCA-PROP-007, UCA-PROP-012; the dose
check is open.

**A2.4 · algorithm · Enacted once.** As C1.3–C1.4.

## Further cases, briefly

- **C4, an override or temporary target now:** CM1–CM5; the since check is intents (A12, CM15 for
  a proposal). **C5, closed loop or automatic bolus off:** a running-mode channel; LoopCaregiver
  sends these to `/api/v2/remotecommands`, which no hub implements (commands §3).
- **A3, too many proposals:** UCA-PROP-002; not specified: a limit per proposing instance and
  channel (§9 item 7).
- **U1, the controller's own automation:** outside the hub; Trio's Shortcuts use a six-minute
  window. The mirror would show such plans only if the controller reports them.
- **U2, a downloaded careportal entry:** no expiry, destination or outcome (UCA-SYNC-DL-001,
  [state and intent §8](spec/state-intent.md#8-open)).
- **F1, a follower:** reads proposals, plans, the mirror and outcomes; any write is 403. Not
  specified: a read permission covering commands and plans (CM11 names proposals only).

---

# Part 3: what the journeys show

## The since check and the dose-check choice

| journey | since check | which choice serves it |
|---|---|---|
| PL1 | intents at approval; doses and carbs at each occurrence | controller decides: the occurrence runs hours after any hub check |
| PL2 | intents; confirmation freshness | controller decides |
| PL3 | definition unchanged | neither; needs a `definitionId` check |
| PL4 | intents; definition | controller decides |
| PL5 | definition; long expiry | neither; doses are not what changes over weeks |
| C1 | doses since; outstanding | controller decides; a command is not a proposal, and CM5 keeps the hub from judging it |
| C2 | carbs and doses since; cancel | controller decides, with cancel |
| C3 | doses since; outstanding, who sent | controller decides, with the list showing the other sender |
| P1 | doses and carbs since `basedOn` | hub refuses catches an uploaded dose; controller decides catches it only on a controller with a since check |
| A1 | carbs since | hub refuses or controller decides; Trio's check misses back-dated meals |
| A2 | doses and carbs since; preview | hub refuses before approval; controller decides at enactment, best with a preview |
| C4, C5 | intents | neither; CM15 already applies to proposals |
| U1, U2, F1 | none at the hub | neither |

Hub refuses serves only P1, A1 and A2, and only when the local dose has been uploaded before the
approval. Controller decides serves every journey in which a controller checks doses since, which
Loop's remote bolus path does not today.

## Specification needs

| need | journeys |
|---|---|
| list outstanding, with sender and doses since | C1, C3, P1, P2, F1 |
| cancel (before hand-over final; after, a request) | PL1.6, PL4.4, C2, P2 |
| enact once per `commandId`, kept until expiry (specified: CM21) | PL1.4, C1, A2 |
| the plan object: elements, trigger, conditions, bounds, end date, confirmation rule | PL1–PL5 |
| a confirmation bound to one occurrence, and whether the plan authorises its proposer | PL1.5, PL2.2 |
| partial acceptance: the approval names elements; a hash rule for the accepted subset | PL1.3, PL5.3 |
| required reviews: who names them, refusal when missing | PL1.2, PL4.2, A2.1 |
| the mirror: plan kind, carrier, occurrence link to its intent | PL1.4, PL1.7, PL3.3 |
| follower read of proposals, plans and commands | PL3.1, F1 |
| the person's withdraw and cancel on any item (amends CM14) | P2, PL4.4 |
| proposal expiry separate from command expiry | PL5 |
| `basedOn` for plans, and a `definitionId` check at approval | PL1.3, PL3.4, PL5.3 |
| plan supersession by an adjusted plan | PL3.3 |
| proposal limit | A3 |

## What the journeys cannot show without a controller implementation

- whether a controller holds, runs and reports a plan, and the end reason of an unconfirmed or
  refused occurrence;
- whether enact once survives a restart on each controller;
- what a cancel after hand-over achieves;
- the since checks a controller makes at enactment, and how often they refuse;
- a preview before approval, outside AndroidAPS's client control;
- whether the mirror stays in step with what the controller holds.
