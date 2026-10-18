# Command queue and planning: outstanding commands, enacting once, and plans confirmed in advance

*What this is: a design note (contributor-facing). Read after [commands](spec/commands.md) and the
[control-loop analysis](spec/control-loops.md); it prepares the maintainer's choices for commands
§9 item 7 and the use cases that drive them.* **Snapshot — describes 2026-10-18. Status: proposed;
the maintainer's answers of 2026-10-18 are in §5; nothing here is in a specification yet.** Every claim about a controller is **read-derived** from
source at the release named; nothing was run.

**The question.** The control-loop analysis found that the command contract has no list of
outstanding commands, no cancel, no rule that a controller enacts a command once, and no check
for doses since a proposal was made. The maintainer framed the answer as a queue with transparency
and operations for managing workflows and intents, asked what controllers do today, and asked for
use cases. The use cases that matter most are planned ones: an agent with access to calendar,
location and activity confirms a repeated meal at a repeated time hours or days ahead, so the
person manages a policy instead of pressing buttons in the moment.

## 1. What controllers do today about duplicate commands

Read at Loop v3.14.9 (NightscoutService `2cef4896`), Trio v1.0.2 (`0b29cd53`), AndroidAPS
4.0.0-rc1 (`d5e7f5bd`) and the unreleased Remote Commands 2 controller on a fork
(`gestrich/NightscoutService` `5bc54fac`).

| controller and command | how a duplicate is stopped | survives a restart |
|---|---|---|
| Loop bolus, carbs | the one-time password is single use, stored in the Keychain, valid about 60 s | yes; a refused duplicate still writes an error Note |
| Loop override, cancel | a list of seen `sent-at` values, in memory, never pruned; none without `sent-at` | no; a replay after a restart starts the override again from now |
| Loop Remote Commands 2 (fork) | a stored set of handled record `_id`s, marked before enacting, on push and fetch | yes; never pruned, and a duplicate is written back as `Error` |
| Trio bolus | refused when boluses since the command's own timestamp reach 20 % of the request | yes (stored pump events) |
| Trio meal | refused when newer carbs exist | yes; misses a back-dated or future-scheduled meal |
| Trio temp target, override, cancels | nothing; `dev` adds a `command_id` that is echoed, not checked | — |
| AndroidAPS client control (4.0 prereleases) | a per-client counter that must strictly increase, stored, advanced before dispatch; a dose is prepared, then committed once | yes |

The same command does arrive twice today: a force-killed Loop received one bolus twice (Loop
#2174, refused by the password check), and Trio fixed doubled carbs from push redelivery or a
resend in v1.0.2 (#1346, #1348). AndroidAPS already receives each client-control command by
socket and by polling, the situation CM18 creates.

**What follows.** No released controller keys de-duplication on an id the hub assigns. A rule that
a controller enacts each `commandId` once, remembered until the command expires, matches the
newest designs (AndroidAPS client control, Remote Commands 2) and is small work for the rest:
Loop stores the override list it already keeps; Trio keeps a seen set on the `command_id` its
`dev` branch already parses; AndroidAPS needs nothing when its signed envelope rides through the
hub unread (CM10). A caregiver's manual resend is a new command and is not caught by this rule;
on the hub side that is CM4's `requestId`, and it is why the outstanding list (§2) matters.

## 2. The queue the specifications already imply

[Commands §4–§7](spec/commands.md#4-the-command-record-proposed) already define most of a queue,
per tenant and per channel:

- **Objects.** Proposals (`open`, then `approved`, `rejected`, `withdrawn` or `expired`),
  evaluations attached to them, commands (from `pending` to an outcome) and outcome reports.
- **Operations specified.** Send (with `requestId` re-send), propose, evaluate, approve (bound to a
  payload hash and a state version), reject, withdraw, fetch, push, report, expire.
- **Who sees what.** The sender and approver see a command's state; proposals are read with
  `api:proposals:read` or `api:commands:create`; the destination fetches only its own.

**Operations to add**, each named as a gap in [commands §9](spec/commands.md#9-open):

| operation | what it does | why |
|---|---|---|
| list outstanding | every proposal and command on a channel that is not final, returned with each send and approval and on its own | a second command or approval in the upload lag (UCA-CMD-001, UCA-PROP-007) |
| cancel | `pending` → `cancelled`, final, nothing handed over; after hand-over, a request the controller may refuse | a meal not eaten (UCA-CMD-015) |
| enact once | the controller rule in §1 | delivery is at least once (UCA-CMD-006) |
| limit open proposals | per proposing instance and channel | flooding (UCA-PROP-002) |

**Not added:** reordering (no precedent; a pump's command queue is the controller's own) and
superseding one command by another (supersession is a property of intents, S3 and A7, and a
superseding override is a new command).

## 3. Planning: a level above the moment

The person, the algorithm, caregivers and agents all act on one pump; STPA calls this several
controllers of one process, and the control-loop analysis gives the controller the only arbiter's
seat ([§3](spec/control-loops.md#3-the-control-structure)). The planned use cases add a level
above the moment, as hierarchical control structures in STPA do:

| level | horizon | who | acts by |
|---|---|---|---|
| policy | days to weeks | the person, a caregiver, a clinician, an agent that proposes | a plan: a recurring intent with its conditions and bounds, approved once |
| confirmation | hours | an agent reading calendar, location and history; the person | confirming, adjusting or skipping one occurrence of a plan |
| moment | minutes | the person, a caregiver | a command, as today |
| algorithm | five minutes | the controller | its own loop, within the active intents |

**One enactor, many orchestrators.** At every level the one instance holding the channel's
command sink (Loop or Trio on the person's phone) is the only thing that acts on the pump. Around
one plan or one proposal, several parties may work: agents that draft it or check it against
other data, human reviewers, a delegate who may approve it, and the person, who may approve,
adjust or withdraw it. The queue item is the shared record they work on, and each party's part is
a role on it:

| role | does | specified as |
|---|---|---|
| proposer | drafts the item | CM11, CM12 |
| evaluator | attaches evidence: a risk check, a second agent's view, a reviewer's note | CM16 |
| approver | turns it into a command or an active plan; the person, or a delegate under a grant | CM13, CM14; the grant is open ([authority §7](spec/authority.md#7-delegation-not-decided)) |
| the person | may also adjust, withdraw or cancel it, whoever proposed it | not specified |
| enactor | the singleton controller: validates and enacts, reports the outcome | CM7–CM10, D18 |

The specifications have the proposer, evaluator, approver and enactor. What they do not have yet:
an item that changes as parties work on it (an adjustment is today a new proposal), a review that
must happen before approval (an evaluation is optional evidence), and the person's standing to
withdraw or cancel any item on their own therapy.

**A precedent already on a controller.** AndroidAPS's automation plugin (`dev` `7e1d537d49`)
triggers on recurring time, location, Wi-Fi network, steps and heart rate, and its actions include
starting a temporary target, a profile percentage and scenes; it has no bolus or carb action. The
plan lives and runs on the controller, which is where D18 puts enactment.

**Where a plan runs.** Two shapes fit the specifications differently:

- **On the controller (recommended).** A plan is a controller-owned definition: a recurring intent
  kind with its trigger and bounds, declared in the controller's registration. A plan made off the
  phone reaches the controller as a proposal (CM11) whose payload is the plan; once approved, the
  controller holds it, runs it, and reports each occurrence as an intent with its initiator. A
  confirmation an agent sends hours ahead is a command against that plan's occurrence, small and
  bounded by the plan. The hub records and routes; it schedules nothing, as the
  [platform index](README.md#ideas-borrowed-from-kubernetes) says.
- **On the hub.** The hub stores the plan and issues commands when its conditions hold. Simpler for
  controllers, but the hub would decide when therapy changes, which D18 rules out, and it would
  need the calendar and location data, which then sits on a server.

**Out-of-band data stays with the agent.** Calendar, location and activity are identifying data.
An agent that reads them sends the hub its proposal or confirmation and, as an evaluation (CM16),
only what the approver needs to see ("lunch on the calendar, at the usual place"), not the data.
That is the minimisation delegation requires
([authority DR7](spec/authority.md#7-delegation-not-decided)).

**Checks move with the level.** A plan is checked when it is approved: its definition, its bounds,
who may approve it. An occurrence is checked when it is confirmed and when it is enacted: what is
active, and what was dosed and eaten since; the controller does the last check, because only it
knows its state at that moment.

## 4. Use cases and the check each needs

Grouped by who starts them. *Since* means what has to be compared with the moment the item was
made: doses, carbs, intents, or nothing.

| id | who | use case | since | level |
|---|---|---|---|---|
| PL1 | agent, person approves | a weekday lunch at a usual time and place: eating soon an hour before, confirmed that morning from the calendar and location | intents at plan approval; doses and carbs at the controller when it runs | policy, confirmation |
| PL2 | agent, person approves | exercise on the calendar: a temporary target before, confirmed by location or activity | intents | policy, confirmation |
| PL3 | caregiver | a week of planned overrides for a child's school schedule | intents; definition unchanged | policy |
| PL4 | agent | illness or cycle-phase sensitivity as a plan with an end date | intents; definition | policy |
| PL5 | clinician | a settings change proposed for review at the next visit | intents; definition; long expiry | policy |
| C1 | caregiver | a correction bolus for a child at school | doses since; outstanding bolus | moment |
| C2 | caregiver | a meal: carbs and bolus, then the meal is not eaten | carbs and doses since; cancel; partial outcome | moment |
| C3 | two caregivers | a parent and a school nurse act for one meal | doses and carbs since; outstanding list; who sent it | moment |
| C4 | caregiver | an exercise override or temporary target, now | intents | moment |
| C5 | caregiver | the phone is offline or being replaced | nothing at the hub beyond expiry and the lease | moment |
| P1 | person | doses on the phone while a caregiver's command or an agent's proposal is outstanding | doses and carbs since | moment |
| P2 | person | sees and cancels or withdraws an outstanding item | outstanding list | any |
| A1 | agent | proposes carbs from a photo of the meal | carbs since; outstanding | moment |
| A2 | agent | proposes a correction bolus | doses and carbs since; a controller preview (prepare, then commit) | moment |
| A3 | agent | proposes too often | proposal limit | any |
| U1 | the controller's own automation | a scheduled override, a shortcut | the controller's own window | algorithm |
| U2 | another client's treatment | a careportal temporary target a controller downloads | nothing today (UCA-SYNC-DL-001) | moment |
| F1 | follower | watches commands, proposals and plans without acting | nothing; read access to the queue | any |

What the table says about the dose check: the moment-level cases need *doses and carbs since*,
and two controllers already do it themselves (Trio's 20 % rule, AndroidAPS's prepare and commit);
the policy cases need *intents and definition* at approval and leave doses to the controller when
the plan runs. A hub-side "refuse if dosed since" check helps only the moment-level proposals
(A1, A2, P1), and is limited there by the upload lag.

## 5. Decided and open

**The maintainer's answers, 2026-10-18:**

1. **Enact once:** adopt the controller rule of §1, with the hub's `commandId` carried to the
   controller; specified as [CM21](spec/commands.md#7-delivery-in-each-mode-proposed).
2. **Plans run on the controller, and the hub mirrors them.** The controller holds and runs an
   approved plan; the hub keeps a read-only copy of the plan and of each occurrence, so followers
   and reviewers see the policy as well as the moments.
3. **Several orchestrators on one item:** a plan or proposal can require named evaluations (a risk
   check, a human reviewer) before it can be approved; the person can always withdraw or cancel
   any item on their own therapy, whoever proposed it; followers can read the queue (proposals,
   plans and commands) without acting on it.
4. **Revision:** an adjustment is a new proposal. A plan may be accepted in parts: the approver
   accepts some of its elements and not others, and the approval names what it accepted.
5. **Next:** write PL1–PL5 and the moment cases as journeys, now in
   [command journeys](command-journeys-2026-10-18.md), in the format of the
   [15.0.9 journey map](../../60-research/remedial/journey-map-15.0.9.md), with the rules and
   cases each step needs.

**Answered later the same day:** the self-approval refusal applies to agents only, and the
person may withdraw any proposal (CM14); the hub refuses an approval when doses or carbs arrived
since the proposal (CM22), and the controller checks doses since before it enacts (CM23). How a
plan accepted in parts binds to its approval is prototyped in
[partial acceptance](partial-acceptance-prototype-2026-10-18.md); what approval a plan needs, by
risk and by evidence, is drafted in [evidence-weighted approval](evidence-weighted-approval-2026-10-18.md).

**Still open:**

- **Out-of-band data:** agents keep it; the hub receives proposals, confirmations and minimised
  evaluations only.
