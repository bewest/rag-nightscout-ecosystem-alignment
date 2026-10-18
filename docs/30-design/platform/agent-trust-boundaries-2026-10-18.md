# Agents in the ecosystem: develop, interpret, act

*Contributor-facing.* **Snapshot — describes 2026-10-18. Status: current; a map of what exists and
what does not, not a design. The proposal lifecycle in §4.3 is proposed, not specified.** Repository
facts are read at this repository's `5a9a49cc`; facts about other repositories and publications were
checked 2026-10-18 through the GitHub API or the publisher's page, and each names its commit or
date. Every claim is **read-derived** (from source or documents) unless marked **measured**. Current
decisions: [execution plan §1](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#1-decisions).

**The question.** Software agents built on language models now touch this ecosystem in three
different ways: they write and change the code of apps and servers, they read a person's data and
explain it, and they could propose or start a therapy change. Each needs a different assurance, and
most of what each needs is already written down here or upstream, in separate places. This page
puts them side by side and names what is missing.

---

## TL;DR

| Domain | What the agent does | What exists | What does not exist |
|---|---|---|---|
| **Develop** | writes or changes code | each controller project's own contribution rules; review and test work measured in the [evidence](../../00-overview/observations/ECOSYSTEM-EVIDENCE.md#4-where-the-maintenance-time-goes-today); simulator asks drafted (§2) | signed builds, an SBOM or a build-provenance record in any project surveyed |
| **Interpret** | reads data and explains it | one read role; seven requirements for delegated reads; at least seven MCP servers and two agent tools that read a Nightscout site (§3) | scoped, purpose-bound or audited reads; a hub whose "what is active now" both hubs agree on |
| **Act** | proposes or starts a therapy change | the upstream RFC's `agent` issuer, `suggest` scope and `DelegationGrant`; D19 instances, roles and command routing, specified (§4) | any path of its own for an agent; a proposal record, an approval bound to the exact change, a command API |

---

## 1. Three domains

| | Develop | Interpret | Act |
|---|---|---|---|
| **What the agent touches** | source code of a controller, hub, uploader or follower app | a person's glucose, treatment, device and settings records | a controller's inputs: an override, temporary target, carbs, a bolus, a mode, a setting |
| **What goes wrong** | a defect ships to people who dose from or display the software | a wrong state read as right, a stale value read as current, a summary that misstates the data, data sent where the person did not expect | a change enacted that nobody approved, on stale state, or by an actor nobody can identify afterwards |
| **Assurance it needs** | review by people who own the code, tests and simulators, release control | minimal and scoped read access, deterministic computation, a hub state that is right, a record of what was read | an authority grant, approval bound to the exact change, the controller's own validation and enactment, an outcome record |
| **Who decides** | each project's maintainers | the person whose data it is, and whoever operates the site | the person, and the controller that owns the pump (D18) |

One tool can sit on two rows. An interpretation that ends in a recommended settings change is at
the edge between Interpret and Act, and its regulatory status is a question for counsel (§6).

## 2. Develop

The controller projects own their contribution rules; this repository points at them. Checked
2026-10-18 through the GitHub API at each repository's default or development branch.

| Project | What its contribution rules say about AI-generated code | Where |
|---|---|---|
| LoopWorkspace | "We do not accept pull requests that are largely AI-generated or submitted without careful engineering judgment, testing, and alignment with Loop's existing patterns." No pull-request template | `CONTRIBUTING.md`, last changed `ae75603c` (2026-07-06) |
| Trio | the same sentence, naming Trio. No pull-request template | `CONTRIBUTING.md`, last changed `74b94426` (2026-04-15) |
| AndroidAPS | "AI-generated pull requests are **not welcome**"; AI analysis goes into an issue and the maintainers write the fix | `CONTRIBUTING.md` on `dev`, last changed `1b583b8f8d` (2026-10-04); not on `master` (`85b5e89c29`, 2024-11-24) |
| cgm-remote-monitor | no rule on AI-generated contributions | `CONTRIBUTING.md` on `dev`, last changed `20e5ad2a` (2026-09-06) |
| Nocturne | no `CONTRIBUTING.md`; `AGENTS.md` and `CLAUDE.md` at the root give instructions to coding agents | `AGENTS.md` last changed `49d61d177` (2026-09-27) |

**What the rules are about, and how the projects use agents themselves.** The rules govern who
verifies and owns a change, not whether a tool was used. AndroidAPS gives its reason: "Verifying and
reviewing AI-generated code reliably takes maintainers more time than the AI took to produce it, and
unverified code is a risk we cannot accept". LoopWorkspace's and Trio's rules say "Do not submit
AI-heavy or 'vibe-coded' pull requests; we welcome thoughtful use of tooling, but contributions need
to be intentionally designed." Each project's own development uses coding agents (measured
2026-10-18 over each branch's latest 300 commits through the GitHub commits API, counting commits
whose message names a coding agent, nearly all as a `Co-Authored-By` trailer; a lower bound, since
attribution is optional):

| Branch | Commits read (dates) | Naming a coding agent | Agent instructions in the tree |
|---|---|---|---|
| AndroidAPS `dev` | 300 (2026-10-07 to 2026-10-16) | 6 (Claude, Copilot) | `CLAUDE.md`, 28 KB, 28 commits since 2026-01-10 |
| Trio `dev` | 300 (2026-09-11 to 2026-10-18) | 28 (Claude) | none at the root |
| Loop `next-dev` | 300 (2025-10-07 to 2026-10-17) | 1 (Claude, 2026-04-23) | none at the root |
| LoopKit `next-dev` | 300 (2025-08-22 to 2026-10-18) | 1 (Claude, 2026-04-23) | none at the root |

**What exists in this repository.**

| Item | Where | Status |
|---|---|---|
| Which steps still need a person, where much of the 2026 cgm-remote-monitor engineering was done with AI coding agents under a maintainer's direction | [evidence §4](../../00-overview/observations/ECOSYSTEM-EVIDENCE.md#4-where-the-maintenance-time-goes-today); [sponsored-team proposal §3](../../00-overview/SPONSORED-TEAM-PROPOSAL.md#3-where-the-time-goes); [accountability thresholds §5](../../00-overview/perspective/ACCOUNTABILITY-THRESHOLDS.md#5-the-same-requirements-for-anyone) | observation and proposal |
| Asks to the simulator and test-rig projects, drafted to be sent in the sender's own words because of the rules above | [upstream asks: device simulators](upstream-asks-device-simulators/README.md) | drafted; nothing sent |
| Signed builds, recorded change review, an SBOM and release provenance, as evidence a manufacturer would expect | [partner readiness §3](../../00-overview/PARTNER-READINESS.md#3-what-a-manufacturer-will-need-to-see), [§8](../../00-overview/PARTNER-READINESS.md#8-order-of-work) item 3 | requirement in a draft; none found in this repository's survey |
| A record every test run leaves | [quality-system proposal §4.1](../../00-overview/QUALITY-SYSTEM.md#41-the-record-every-run-leaves) | proposed |

**What does not exist.** A rule shared across projects for agent-written changes; a way for a
reviewer to see, per change, which parts an agent wrote; signed builds, an SBOM or a build-provenance
record in any project surveyed.

## 3. Interpret

### 3.1 Read access today

| Item | Where | Status |
|---|---|---|
| The read role is one bit: `readable` is `*:*:read`, every collection, every field, all time | cgm-remote-monitor `lib/authorization/storage.js:235` at `dev` `fade2299`; [configuration and delegation §5.3](../tenancy/nightscout-configuration-and-delegation-2026-09-10.md#53-what-exists-today) | shipping |
| Seven requirements for a delegated reader: scoped reads enforced in storage, bounded queries, purpose and expiry, answers rather than data, read audit, revocation that is real, minimization at the boundary | [configuration and delegation §5.4](../tenancy/nightscout-configuration-and-delegation-2026-09-10.md#54-what-a-delegation-design-would-have-to-provide) | requirements, stated 2026-09-10; the read role above is still one bit |
| Delegation grants with scopes, constraints and expiry | [authority model](../../10-domain/authority-model.md) | designed, **not implemented** |
| Tools that read a site for an agent: MCP servers, an agent skill, an AI platform | [evidence §7.1](../../00-overview/observations/ECOSYSTEM-EVIDENCE.md#71-research-tools-elsewhere-in-the-ecosystem) | third-party; the list lives there |

Requirement 6 bears hardest on agents: once a model has read raw data, revoking the grant does not
un-read it, and the data has also gone to whoever runs the model. Where the model runs is a
property of the agent's host, not of the tool that fetched the data: a tool that keeps its database
local still returns its output into the conversation, which goes to the model provider when the
model is a hosted service. Lumose (repository `GlycemicGPT`) states this choice in its README; the
evidence table records which tools do.

### 3.2 MCP is an adapter

The Model Context Protocol, at its current revision `2026-07-28`, lets a server offer *resources*
(context and data), *prompts* (templated messages) and *tools* (functions the model may call), over
stdio or Streamable HTTP. The revision describes stateless, self-contained requests, and says the
protocol cannot enforce its security principles itself: hosts must obtain the user's consent before
invoking a tool. An MCP server for Nightscout is therefore an adapter over the API it calls, not a
new source of state or authority: a local copy it keeps is a copy, and it holds whatever credential
it is given and reads or writes what that credential allows. The servers surveyed differ on exactly that point — which credential they accept
and whether they expose write tools ([evidence §7.1](../../00-overview/observations/ECOSYSTEM-EVIDENCE.md#71-research-tools-elsewhere-in-the-ecosystem)).
The statistics API proposal specifies an MCP resource provider over a documented statistics API
(`REQ-STATS-005`, [proposal](../../sdqctl-proposals/statistics-api-proposal.md)).

### 3.3 Compute first, then explain

An explanation is only as right as the numbers under it. Two layers come before the model:

1. **The hub's state.** The two hubs do not always report the same thing as active.
   **Measured** by [`tools/lab/hub-active-state`](../../../tools/lab/hub-active-state/README.md)
   on synthetic records, running each hub's storage and active-state code directly rather than over
   HTTP (cgm-remote-monitor `fade2299`, Nocturne `42275c812`;
   [intent landscape §5](nightscout-intent-workflow-landscape-2026-10-09.md#5-how-the-hubs-decide-what-is-active)):
   - `Temporary Override Cancel`: the hubs **agree** — in both, the override runs its full duration.
   - A temporary target followed by a cancel: the latest span **agrees** (it is Nocturne's
     `Cancelled` span); `Active`-state and list reads **disagree** until the target's own end, and
     the open `Cancelled` span stays in Nocturne's list reads afterwards.
   - A Loop devicestatus override: cgm-remote-monitor reads `duration` as **seconds**, Nocturne as
     **minutes**, so a 30-minute override is active at +40 and +120 minutes in Nocturne only.
   - Also disagreeing: the profile after a timed switch ends, AAPS `timeshift` units, and
     out-of-order backfill of two open overrides.

   An agent that asks either hub "which override is active?" gets the hub's answer, not the
   controller's.
2. **Deterministic computation.** Time in range, GMI, variability and patterns are arithmetic; a
   tool that computes them in code and hands the model the result can be tested, and one that asks
   the model to compute them cannot. Several MCP servers in the evidence table compute aggregates
   server-side; one documents checking them against Nightscout's own report.

## 4. Act

### 4.1 What exists

| Item | Where | Status |
|---|---|---|
| Six things entity CRUD cannot carry, including the initiator (P5) and the command lifecycle (P6) | [intent landscape §2](nightscout-intent-workflow-landscape-2026-10-09.md#2-where-intent-differs-from-entity-management) | read-derived from Loop, Trio, iAPS, AAPS source |
| A hub sees acceptance on no command path except AAPS `dev`'s, whose signed requests and correlated acknowledgements go through NS `settings`; elsewhere success shows as the resulting entity and failure as free text, or not at all | [intent landscape §6](nightscout-intent-workflow-landscape-2026-10-09.md#6-the-remote-command-lifecycle); [remote commands](../../10-domain/remote-commands-comparison.md); [remote bolus](../../10-domain/remote-bolus-comparison.md) | read-derived |
| An automated agent has no path of its own: it holds a caregiver's credential and is indistinguishable from that caregiver (path H) | [technical loops §3](../../60-research/structures-2026-10-17/technical-loops.md#3-the-delegation-loop) | read-derived |
| `issuerType: human \| controller \| agent`; scopes `read`, `suggest` (`override.suggest # Can propose, human must approve`), `activate`, `deliver`, `admin`; `DelegationGrant {grantId, grantedBy, grantedTo, scopes, constraints {maxOverrideDuration, allowedOverrideTypes, requireConfirmation, expiresAt}, grantedAt, revokedAt}`; append-only audit | upstream `docs/proposals/agent-control-plane-rfc.md` (draft v1.0, January 2026; read at official `b5ddd662`) | proposal, not implemented |
| Authority levels (agent 50) and a grant with rate limits and time windows | [authority model](../../10-domain/authority-model.md) | designed, **not implemented** |
| D19 instances with leases, roles `source` / `command-sink` / `{value: other, controllerTerm}` "for roles such as an agent's propose and act", required provenance `device` or `simulated`, a `device` command-sink only for the product's bound subject or by the owner's transfer (`grantedBy`), and routing that refuses rather than guesses (`no-command-destination`, 409 `ambiguous-command-destination`) | [hub-sync §3.6](nightscout-hub-sync-architecture-2026-09-11.md#36-definitions-and-instances) | Specified, not implemented: no hub serves any of this |
| An earlier controller registration protocol | [controller registration protocol proposal](../../60-research/controller-registration-protocol-proposal.md) | draft v2, 2026-01-17 |

### 4.2 The upstream RFC under D18

D18 makes the hub responsible for observability and the controller responsible for sending,
syncing and reconciling; the hub records the controller's result and never composes intents
([execution plan §2.6.1](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#261-d18--two-tier-controller-registration)).
Read against that:

| RFC element | Under D18 and D19 |
|---|---|
| `agent` as an issuer type | prior art: the actor exists |
| `suggest` scope ("can propose, human must approve") | prior art: the distinction between proposing and acting |
| `DelegationGrant` shape: who granted, to whom, scopes, constraints, expiry, revocation | prior art: the grant a proposal would cite |
| append-only audit with issuer and authority | prior art |
| Conflict rules: override composition inside the hub, "Human > Agent > Controller" | **outside the hub's role.** Composition is controller-specific ([intent landscape §7](nightscout-intent-workflow-landscape-2026-10-09.md#7-composition-who-combines-overlapping-intents)); the [control-plane reconciliation](../tenancy/nightscout-control-plane-reconciliation-2026-09-11.md) records the same |

**An agent as initiator** (maintainer, 2026-10-18). No `agent` value is added to any initiator
vocabulary. An agent initiator is written in the open-vocabulary form `{value: other,
controllerTerm}`, as hub-sync §3.6 does for an agent's roles. No controller records an agent as initiator today. The registrations are built for needs that are latent but measured and demonstrated — in the corpus, in controller source and in the labs — not only for what apps send now; the open form lets a controller, simulator or lab record an agent initiator today, and a shared value can be named once the corpus or a lab shows one in use. Recorded in the [execution
plan](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#263-d20--version-scoped-quirks-and-the-two-id-rule-maintainer-2026-10-16)
(row 17). The registration grammar's `initiators.values` take strings in the controller's own
vocabulary or the `{value: other, controllerTerm}` form, with no shared list
([state and intent S8](spec/state-intent.md#2-rules); *corrected 2026-10-18 by `SCHEMA-INTENT-GAPS`*).

### 4.3 What a proposal lifecycle would add — proposed, not specified

Nothing in this subsection is specified or decided. It states what exists nowhere above, so that
the item that specifies commands can take it or leave it.

```
propose → validate → (evaluate) → approve | reject → command → outcome
```

| Step | Who | What it would carry |
|---|---|---|
| propose | an agent instance holding a propose role (`{value: other, controllerTerm}`) | the exact change; the controller instance it is for (D19 `instanceId` and `definitionId`); the state it was based on; an expiry; the SHA-256 of the payload's RFC 8785 canonical JSON, the rule D19 already uses for definition ids and etags |
| validate | the controller (D18) | its own checks, as today on every remote path ([technical loops §3.3](../../60-research/structures-2026-10-17/technical-loops.md#33-paths-compared)); a proposal the controller would refuse goes no further |
| evaluate | optional; any checker | a risk check may request human review; it never grants authority. A probabilistic check — a classifier or a second model — is evidence for the approver, not a decision |
| approve or reject | a person holding the grant | an approval names the payload hash, so it binds to that exact change and no other; an expired proposal cannot be approved |
| command | the hub routes to the live `device` command-sink, as specified in §3.6 | the approved payload and its hash; the controller checks the hash before enacting |
| outcome | the controller | accepted or refused, applied effect (P3), correlated to the proposal |

Three constraints carry over unchanged. Validation and enactment stay the controller's (D18). Read
access never confers a propose or act role: a `readable` credential, or an MCP server holding one,
cannot be promoted to either. And the hub routes and records; it does not decide whether a change
is safe. For comparison, OWASP's *LLM06:2025 Excessive Agency* recommends minimum extensions,
minimum permissions, and human approval of high-impact actions.

**"The state it was based on" has no home yet.** What D19 versions is the registration: the
product's etag and the instance's etag cover the declaration, the binding and the granted roles
([hub-sync §3.5–§3.6](nightscout-hub-sync-architecture-2026-09-11.md#36-definitions-and-instances)).
Neither covers the controller's therapy state — which override is active, which profile, what is
on board — so neither tells an approver that the state the agent read is still the state the
controller holds.

**Where it would be specified.** Command delivery is `SPEC-REG-COMMANDS` in the
[work queue](../../../queue/work-queue.yaml): not started, blocked on `SPEC-REG-MODES`; §3.6 says
"The command API itself is not specified here." The proposal record is folded into that item
(maintainer, 2026-10-18), with gate cases for an approval bound to one payload hash, an expired
proposal, and a proposal from a credential with no propose role; the open question above is its
first.

## 5. Evaluating an algorithm before it acts

An agent that proposes a change, and a developer who changes an algorithm, both need to know what
the algorithm does with the inputs it gets.

- **Cross-implementation equivalence.** [ADR-005](../../90-decisions/adr-005-adapter-protocol.md)
  fixes the adapter protocol for comparing oref0 in JavaScript, Swift and Kotlin, and Loop, on
  identical inputs; the vectors and assertions are under [`conformance/`](../../../conformance/README.md).
- **Shadow comparison.** The [cross-validation log](../../../traceability/cross-validation-log.md)
  (A10, 2025-03-30) records Trio's shadow mode, which logs JavaScript and Swift outputs for the same
  inputs; at Trio `e41c9db37` the Swift port is the running algorithm
  ([intent landscape §1](nightscout-intent-workflow-landscape-2026-10-09.md#1-sources)).
- **Replay is bounded by what was recorded.** Of the dosing inputs each algorithm declares, 20% are
  recorded for Loop and 50% for the oref0 family (55% and 72% counting inputs derivable from
  history), as of 2026-09-11 ([hub-sync §4.2](nightscout-hub-sync-architecture-2026-09-11.md#42-completeness-as-a-published-number)).
  Loop's input set is read from its source; oref0's is the union of inputs across 385 captured replay
  vectors (`specs/nsschema/dosing-input-sources.yaml`). A derived input is *a* value, not
  necessarily the one the controller used, so a replay on derived inputs tests the replayer as much
  as the algorithm. The change list that would raise the figures is
  [replay-fidelity changes](PROPOSAL-replay-fidelity-changes-2026-09-11.md).

## 6. Regulatory boundary

Facts, and questions for counsel; no conclusion is drawn here.

- FDA's guidance *Clinical Decision Support Software* was issued January 29, 2026, superseding the
  issue of January 6, 2026 (nonbinding recommendations). It states: "Software functions that support
  or provide recommendations to patients or caregivers – not HCPs – meet the definition of a
  device", and that FDA intends to be consistent with its existing digital-health policies for them.
- The programme's question for counsel is [§9 item 11](../../00-overview/ECOSYSTEM-PROGRAMME.md#9-the-foundations-role-and-points-to-decide):
  whether a report that proposes settings changes is clinical decision support under device
  regulation, and what clinical review it needs. The same question arises for an agent that explains
  data to a person with diabetes or a caregiver and ends with a suggestion.
- Regulatory roles, intended use and complaint handling in any agreement with a manufacturer are in
  [partner readiness §5](../../00-overview/PARTNER-READINESS.md#5-terms-of-the-agreement-itself) and
  [§6](../../00-overview/PARTNER-READINESS.md#6-complaint-incident-and-support-handling).

Questions for counsel: whether an MCP server or agent skill that only reads and summarises is in
scope of the guidance when its user is a patient or caregiver; whether a server that exposes a
treatment-write tool changes that; and who, among the server's author, the host's provider and the
person running it, would be the manufacturer of such a function.

## 7. Not measured, not decided

- No agent, MCP server or skill was run against a site for this page; the tool facts are from READMEs
  and source read.
- Whether any controller project would accept an agent as a command sender at all, under any grant.
- How an agent instance is scoped, limited and revoked: no decision covers it
  ([process models](../../00-overview/perspective/PROCESS-MODELS.md)).
- A shared initiator list (§4.2).
- A therapy-state version a proposal could bind to (§4.3).
- Whether the proposal lifecycle of §4.3 belongs in `SPEC-REG-COMMANDS` or in a separate item.
- Read audit, purpose limitation and real revocation for a delegated reader (§3.1).
- Which of the authority model and upstream `conflict-resolution.md` becomes the source for the
  grant shape ([hub-sync §5.2](nightscout-hub-sync-architecture-2026-09-11.md#52-liveness-and-channel-ownership--open-here-already-drafted-upstream)).
