# Platform contracts: where each piece is specified

*Contributor-facing. Living index, current at `main` `010e1661` (2026-10-18). Terms are defined in
the [platform glossary](spec/glossary.md).*

This page maps the work on how controllers (Loop, Trio, AndroidAPS and others) and hubs
(cgm-remote-monitor, Nocturne) agree on what records are, who wrote them, and how they move. The
aim has three parts:

- **Full audit fidelity.** Every stored record says what it is, which copy of which controller
  wrote it, under which definition, and whether it was requested, applied, mapped or projected.
- **Controller-owned definitions, secured.** A controller declares its own typed definitions. The
  hub accepts them per element, binds them to the credential that wrote them, and never lets one
  controller redefine another's data.
- **Cost-effective sync.** Fewer requests per cycle with typed records, REST for writes and
  catch-up, a socket for live delivery, and versioned definitions so a new release does not need
  a full re-sync.

The material is organised in six layers. A lower layer never depends on a higher one.

| layer | question it answers | depends on |
|---|---|---|
| **L0 Identity** | Which record, definition, instance or subject is this? | — |
| **L1 Records** | What typed observations exist, and how are today's documents decomposed into them? | L0 |
| **L2 Definitions and instances** | Who declared what a record means, and which running copy wrote it? | L0, L1 |
| **L3 State and intent** | What was requested, what was applied, what is active now, and why did it end? | L1, L2 |
| **L4 Change and sync** | How are writes matched, re-sent, ordered and delivered over REST and the socket? | L0–L3 |
| **L5 Authority** | Who may register, write, route a command or act for someone else? | L0, L2 |

Audit fidelity is not a separate layer. Each layer's section below lists what it records for
audit.

**Status words used here.** *Evidenced*: measured or read from source in the corpus or controller
code. *Specified*: a contract with synthetic conformance cases and a reference decision function
in `tools/nsschema/`, which checks the cases but is not a hub. *Implemented*: a hub serves it. On
2026-10-18, no hub implements any L2, L3 or L5 contract on this page.

## The specification set

Seven specifications and a glossary, one file each under `spec/`. Each answers one question a
reader brings, and each has its own rules, conformance cases and gate.

| file | question | layer | rules | status | queue |
|---|---|---|---|---|---|
| [glossary](spec/glossary.md) | what does this term mean, and where is it specified? | all | — | written | — |
| [identity](spec/identity.md) | which record, definition, instance or subject is this, and when is a write a re-send? | L0 | I1–I9 | written | `SPEC-ID` |
| `records` | what typed observations and settings snapshots exist, and how do today's documents decompose into them? | L1 | R | queued | `SPEC-RECORDS` |
| [registration](spec/registration.md) | how does a controller declare what its data means, and how does a hub accept it and attribute what is written? | L2 | G1–G5, Q1–Q4 | written | `SPEC-REGISTRATION` |
| [state and intent](spec/state-intent.md) | what was requested, applied and active, who started it, and why did it end? | L3 | S1–S12 | written | `SPEC-STATE-INTENT` |
| `commands` | how does a request or a proposal reach a controller, and how does its outcome come back? | L3, L5 | C | queued | `SPEC-REG-COMMANDS` |
| `sync-transport` | how are writes matched, ordered and delivered over REST and the socket, and at what cost? | L4 | T | queued | `SPEC-SYNC-TRANSPORT` |
| `authority` | who may register, write, own, route or act for someone else? | L5 | A | queued | `SPEC-AUTHORITY` |

**Why these boundaries.** Each boundary falls where the reader, the rate of change or the review
differs:

- *identity* changes rarely and every other specification uses it;
- *records* change with the observation catalogue and the corpus;
- *registration* changes with hub releases, and is read by both controller and hub authors;
- *state and intent* changes with controller releases and their vocabularies;
- *commands* carry the safety review of anything that reaches a controller;
- *sync-transport* changes with performance work;
- *authority* changes with the tenancy and authentication decisions.

**Why not more.** The grammar stays in *registration*: declaring an element and accepting it are
read together, and the meaning table is what decides `version-conflict`. Version-scoped quirks
stay there because they are declarations and recorded mappings. The effect and motivation model
stays in *state and intent* while it is a proposal.

**Why not fewer.** *Commands* are kept apart from *state and intent*, because the request,
proposal and acknowledgement lifecycle has its own cases and review, and from *authority*, which
says who may rather than what happens. *Authority* is kept apart from *registration* so that
binding, the owner's actions and delegation are read in one place.

**What moves when the queued files are written:**
- registration §15 (binding, credentials, the owner) moves to *authority*;
- command routing in registration §9 moves to *commands*;
- the observation catalogue and settings snapshots, specified today only in `specs/sync/primitives.yaml`,
  `controller-settings.schema.json` and the dated evidence documents, go to *records*.

Each file should stay readable in a sitting. *Registration* is the largest, at about 820 lines, and
shrinks when §15 and routing move out.

**How they are kept.**

1. **One home per rule.** Other specifications link to it by section and never restate it.
   Decisions stay in the execution plan; defects stay in the backfix register.
2. **Stable rule ids.** A changed rule keeps its id; a removed id is not reused.
3. **One skeleton.** Each file has the same parts, in order:
   - a header: audience, the commit it is current at, its layer, its decisions and its queue item;
   - files, rules, the sections, compatibility and open items;
   - its conformance cases.
4. **Current rules only.** History is in git. A section moved out of a dated document leaves its
   heading, a pointer, and a link to its text at the commit it was taken from.
5. **Generated, gated, one commit.** Case and declaration tables are generated
   (`python3 -m tools.nsschema.spec_cases <layer>`). `node tools/queue/gates/platform-spec.js
   <layer>` checks a specification's cases, links and wording. A rule change lands with its schema
   and case changes in one commit.

## L0 Identity

| | |
|---|---|
| **Spec** | [spec/identity.md](spec/identity.md): rules I1–I9, contract ids, match order per collection, the proposed `identifier` format, open decisions, today's cgm-remote-monitor behaviour, 20 cases |
| **Drawn from** | [hub-sync §3.7](nightscout-hub-sync-architecture-2026-09-11.md#37-version-scoped-quirks-and-the-two-ids) rules 5–8; [write contract](../tenancy/write-contract-spec-2026-10-07.md) §2.2, §3 and §6.1; [hub-sync §3.6](nightscout-hub-sync-architecture-2026-09-11.md#36-definitions-and-instances) |
| **Evidence** | [identifier format](../../60-research/tenancy/identifier-format-2026-10-17.md) (UUID not required; constraints C1–C7); [identifier duplicates](../../60-research/tenancy/identifier-duplicates-2026-10-17.md); [Loop identifier ask](upstream-asks-loop-identifier/README.md) |
| **Schemas, cases** | `specs/sync/registration-submit.schema.json` (`write.ids`, `matchedBy`); `specs/quirks/`; 29 cases in `specs/sync/conformance/quirks/` |
| **Decisions** | [D20](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#263-d20--version-scoped-quirks-and-the-two-id-rule-maintainer-2026-10-16) |
| **Open** | `ID-FORMAT-DECISION`, `ID-CLIENT-OID-DECISION`, `ID-V3-IMMUTABLE-DECISION` (needs decision); `ID-SIMPLE-MATCH`, `ID-VALIDATE`, `ID-FIRST-MATCH`, `ID-V1-LOOKUP`, `ID-UNIQUE-INDEX` (blocked) |
| **Audit** | every write reply returns `identifier` and `_id` and says which one matched; an assigned ObjectId's time is the hub's receipt time, never the record's time |
| **Status** | specified (`SPEC-ID`); the v1 `identifier` match for entries and devicestatus is queued for cgm-remote-monitor after 15.0.9 |

## L1 Records

| | |
|---|---|
| **Spec today** | queued as `SPEC-RECORDS`; today `specs/sync/primitives.yaml` (the observation catalogue, graded `measured`, `declared` or `proposed`); [D11](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#26-d11--devicestatus-is-a-decomposition-problem-not-a-column-selection-problem) (devicestatus is decomposed, not given columns); [hub-sync §3.3](nightscout-hub-sync-architecture-2026-09-11.md#33-composite-on-the-wire-primitive-in-storage) |
| **Evidence** | [typed schema evidence](nightscout-typed-schema-evidence-2026-09-10.md); [primitive coverage](nightscout-primitive-coverage-2026-09-11.md); [devicestatus and profile fidelity](nightscout-devicestatus-profile-fidelity-2026-09-10.md); [extensibility models](nightscout-extensibility-models-2026-09-10.md); [quirks registry](../../../specs/quirks/README.md) |
| **Schemas** | `specs/nsschema/*.model.json` (today's collections); `specs/sync/controller-settings.schema.json`; `specs/sync/sensitivity.yaml` (the two-axis sensitivity label) |
| **Open** | devicestatus and profile decomposition coverage is unmeasured ([hub-sync §7](nightscout-hub-sync-architecture-2026-09-11.md#7-what-is-not-measured)) |
| **Audit** | the composite document is kept beside its decomposed records, so "what did the device send" stays answerable |
| **Status** | evidenced; treatment routing measured at 99.86% by `eventType` alone |

## L2 Definitions and instances

| | |
|---|---|
| **Spec** | [spec/registration.md](spec/registration.md): the grammar, the capability document, the product resource and fallback, definitions, instances, channels and roles, labels, typed writes, read selection, projected views, retention, binding and the owner, version-scoped quirks, open choices, 186 cases |
| **Evidence** | [controller descriptions](PROPOSAL-controller-descriptions-2026-09-11.md) (the well-known tier); [intent and workflow landscape](nightscout-intent-workflow-landscape-2026-10-09.md) §8–§9 (what a registration must declare); [control-plane reconciliation](../tenancy/nightscout-control-plane-reconciliation-2026-09-11.md) (the upstream RFC's kind/instance split) |
| **Schemas, cases** | `specs/sync/controller-state-model.schema.json`, `hub-capabilities.schema.json`, `registration-submit.schema.json`, `controller-instance.schema.json`; generated registrations in `specs/sync/registrations/`; 54 cases in `specs/sync/conformance/`, 103 in `conformance/instances/` |
| **Decisions** | [D18](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#261-d18--two-tier-controller-registration) and its [addendum](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#d18-addendum--an-extensible-grammar-maintainer-2026-10-12); [D19](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#262-d19--definitions-and-instances-maintainer-2026-10-14) |
| **Open** | `SPEC-REG-MODES`, `SPEC-REG-MIGRATE`; implementation `HUB-REG-CRM`, `HUB-REG-CRM-SEAM`, `HUB-REG-CRM-ADMIN`; adoption `HUB-REG-NOCTURNE`, `PROPOSAL-REG-CONTROLLERS`; §3.7's choices 2, 3, 4, 6, 7, 9, 10, 11 and 12 await the maintainer |
| **Audit** | every typed record carries its instance, its definition id and its role's provenance; projected documents carry `projectedFrom`; records are attributed to the registration and its bound credential, never to a namespace string |
| **Status** | specified (`SPEC-REGISTRATION`) |

## L3 State and intent

| | |
|---|---|
| **Spec** | [spec/state-intent.md](spec/state-intent.md): rules S1–S12 (composition reported by the controller, kinds, slots, states, end reasons, the wire carrier, requested and applied, initiators, definitions, acceptance, the controller's command contract), the declared kinds (generated), composition per controller, effect and motivation (proposed), the active-state gap, 15 cases; channels from slots are [registration §9](spec/registration.md#9-channels-roles-and-provenance) |
| **Evidence** | [intent and workflow landscape](nightscout-intent-workflow-landscape-2026-10-09.md) (per-controller matrix, end encodings, how each hub decides what is active, command lifecycles); [effects and versioning](nightscout-effects-and-versioning-2026-09-11.md) (effect separated from motivation); [authority model](../../10-domain/authority-model.md) |
| **Schemas** | `specs/sync/controller-state-model.schema.json` (`stateSpans`, `composition`, `commands`); `specs/sync/shared-slots.yaml`; `specs/sync/therapy-effect.schema.json`; `specs/sync/effect-remapping.yaml` |
| **Open** | `SPEC-ACTIVE-STATE` (what is active at a time, and a therapy-state version); `SCHEMA-INTENT-GAPS` (initiators' `other` form, units on requested and applied carriers, typed carrier fields); undeclared vocabularies for `PROPOSAL-REG-CONTROLLERS`; `LAB-TRIO-INTENT` |
| **Audit** | requested and applied are recorded separately; each span records its end reason and initiator in the controller's own vocabulary; composition is recorded as the controller reports it, never computed by the hub |
| **Status** | specified for declarations (`SPEC-STATE-INTENT`); not specified for what is active at a time, where `LAB-HUB-ACTIVE-STATE` measured cgm-remote-monitor and Nocturne disagreeing (state and intent §6) |

## L4 Change and sync

| | |
|---|---|
| **Spec today** | [write contract](../tenancy/write-contract-spec-2026-10-07.md) §2–§3 (one write step, the re-send rule, every path's writes reaching the storage socket); [hub-sync §3.2](nightscout-hub-sync-architecture-2026-09-11.md#32-the-contract-the-hub-returns) (cursor envelope and batch write); [replay-fidelity proposal §1](PROPOSAL-replay-fidelity-changes-2026-09-11.md#1-sync-cost-should-be-o1-in-the-number-of-resources) (one history read across collections on API v3); [registration §6](spec/registration.md#6-the-controllers-side-fallback-and-refused-writes) (fallback, load versus definite refusals); [D6](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#1-decisions) (the change feed under multi) |
| **Evidence** | [hub-sync §2](nightscout-hub-sync-architecture-2026-09-11.md#2-what-sync-costs-now) (`make schema-sync-cost`: up to 5,760, 2,016 and 1,440 requests a day for AndroidAPS, Loop and Trio against 576 for two requests a cycle; source-derived upper bounds, not traffic); the write contract's measured matrix |
| **Open** | `WRITE-CONTRACT`, `WC-STEP-PATCH`, `ID-BATCH-RESULTS` (blocked). Not specified anywhere: socket delivery of typed records, cursor semantics under concurrent writers, and migrating stored typed records when a definition changes version (rule 4 of the D18 addendum converts nothing without a declared mapping) |
| **Audit** | one change event per write call; a matched re-send stores no second copy and is answered with the stored ids; each mapping the hub applies is recorded as `quirksApplied` |
| **Status** | the write matrix is evidenced; the write step is specified; the typed sync transport is not |

## L5 Authority

| | |
|---|---|
| **Spec today** | binding, credential kind, owner actions and authorisation in [registration §15](spec/registration.md#15-binding-credentials-and-the-owner); roles, provenance, command-sink binding and command routing in [registration §9](spec/registration.md#9-channels-roles-and-provenance) |
| **Evidence** | [agent trust boundaries](agent-trust-boundaries-2026-10-18.md) (develop, interpret and act; a proposal lifecycle, proposed and not specified); [configuration and delegation §5](../tenancy/nightscout-configuration-and-delegation-2026-09-10.md#5-new-data-and-delegation-between-agents) (what a delegation design must provide); [control-plane reconciliation](../tenancy/nightscout-control-plane-reconciliation-2026-09-11.md); [authority model](../../10-domain/authority-model.md) |
| **Decisions** | [D13–D17](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#1-decisions) (credential root, listeners, auth plane; D17 row 2 open) |
| **Open** | `SPEC-REG-COMMANDS` (the command API and the proposal record in front of a command, to be the `commands` specification); `SPEC-AUTHORITY` (delegation of a principal's authority to a caregiver, app or agent) |
| **Audit** | the owner's listing shows every product's binding, credential kind and binding event, every instance's roles and liveness, and every overlap |
| **Status** | specified for registration and routing; not specified for commands and delegation |

## Reading order

For someone new to the series: this page, then the [glossary](spec/glossary.md), then
[intent and workflow landscape](nightscout-intent-workflow-landscape-2026-10-09.md) §2 and §9 for
why the contract exists, then the specifications in layer order: [identity](spec/identity.md),
[registration](spec/registration.md), [state and intent](spec/state-intent.md).
