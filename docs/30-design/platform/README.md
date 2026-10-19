# Platform contracts: the index to six layers and eight specifications

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

**Status words used here and in every specification's header.** *Evidenced*: measured or read
from source in the corpus or controller code. *Decided*: the maintainer decided it, recorded in the
execution plan. *Proposed*: written as a rule for the maintainer to decide. *Specified*: a contract
with synthetic conformance cases and a reference decision function in `tools/nsschema/`, which
checks the cases but is not a hub. *Implemented*: a hub serves it. On 2026-10-18 the L2, L3 and L5
contracts are specified and not implemented; the first hub implementation is `HUB-REG-CRM`.

## The specification set

Eight specifications and a glossary, one file each under `spec/`. Each answers one question a
reader brings, and each has its own rules, conformance cases and gate.

| file | question | layer | rules | status | queue |
|---|---|---|---|---|---|
| [glossary](spec/glossary.md) | what does this term mean, and where is it specified? | all | — | written | — |
| [identity](spec/identity.md) | which record, definition, instance or subject is this, and when is a write a re-send? | L0 | I1–I9 | written | `SPEC-ID` |
| [records](spec/records.md) | what typed observations and settings snapshots exist, and how do today's documents decompose into them? | L1 | R1–R9 | written | `SPEC-RECORDS` |
| [registration](spec/registration.md) | how does a controller declare what its data means, and how does a hub accept it and attribute what is written? | L2 | G1–G5, Q1–Q4 | written | `SPEC-REGISTRATION` |
| [state and intent](spec/state-intent.md) | what was requested, applied and active, who started it, and why did it end? | L3 | S1–S12 | written | `SPEC-STATE-INTENT` |
| [commands](spec/commands.md) | how does a request or a proposal reach a controller, and how does its outcome come back? | L3, L5 | CM1–CM32 | written | `SPEC-REG-COMMANDS` |
| [plans](spec/plans.md) | how is a plan proposed, approved in parts, held by the controller and mirrored by the hub? | L3, L5 | PN1–PN18 | written | `SPEC-PLANS` |
| [sync-transport](spec/sync-transport.md) | how are writes matched, ordered and delivered over REST and the socket, and at what cost? | L4 | T1–T15 | written | `SPEC-SYNC-TRANSPORT` |
| [authority](spec/authority.md) | who may register, write, own, route or act for someone else? | L5 | AU1–AU5, DR1–DR7 | written | `SPEC-AUTHORITY` |

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

Each file should stay readable in a sitting. *Registration* is the largest; command routing has
moved from its §9 to *commands* §2.

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

### Who owns each layer

Each layer changes with a different group's work, so each has a natural owner. Status at `main`
`0b0d150f`, 2026-10-18:

| layer | changes with | natural owner | engaged today |
|---|---|---|---|
| L0 identity | rarely; every layer uses it | hub and controller maintainers together | the Loop developers shared an `identifier` proposal on 2026-10-17, close to D20 rule 5; the [reply](upstream-asks-loop-identifier/README.md) is drafted, not sent |
| L1 records | the observation catalogue and the site corpus | hub maintainers, with research users | specified in this repository |
| L2 definitions and instances | controller releases | each controller team, for its own data | proposals to the controllers not started ([queue](../../../queue/work-queue.yaml)) |
| L3 state and intent, commands, plans | controller releases; carries the safety review | controller teams, with caregiver-app teams | specified in this repository; implemented in no hub or controller |
| L4 change and sync | performance work | hub implementers (cgm-remote-monitor, Nocturne) | proposal to Nocturne not started |
| L5 authority | tenancy and authentication decisions | hub operators, with the foundation's oversight role | decided in part (D7, D13–D19; D17 row 2 open) in the [execution plan](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md) |

L2 and L3 describe what controllers send and do, and today they are written here, not by the
controller teams. They become the controllers' own when those teams review the parts that describe
their data and hold a route to change them. Why the cut follows the teams is read in
[the Conway's Law case study §6](../../00-overview/perspective/CONWAY.md#6-inverse-conway-specifications-shaped-to-their-owners).

## L0 Identity

| | |
|---|---|
| **Spec** | [spec/identity.md](spec/identity.md): rules I1–I9, contract ids, match order per collection, the proposed `identifier` format, open decisions, today's cgm-remote-monitor behaviour, 20 cases |
| **Drawn from** | [hub-sync §3.7](nightscout-hub-sync-architecture-2026-09-11.md#37-version-scoped-quirks-and-the-two-ids) rules 5–8; [write contract](../tenancy/write-contract-spec-2026-10-07.md) §2.2, §3 and §6.1; [hub-sync §3.6](nightscout-hub-sync-architecture-2026-09-11.md#36-definitions-and-instances) |
| **Evidence** | [identifier conventions](identifier-conventions.md) (living draft: decisions of 2026-10-18 and one URL-form template per record kind and source); [identifier format](../../60-research/tenancy/identifier-format-2026-10-17.md) (UUID not required; constraints C1–C7); [identifier duplicates](../../60-research/tenancy/identifier-duplicates-2026-10-17.md); [Loop identifier ask](upstream-asks-loop-identifier/README.md) |
| **Schemas, cases** | `specs/sync/registration-submit.schema.json` (`write.ids`, `matchedBy`); `specs/quirks/`; 29 cases in `specs/sync/conformance/quirks/` |
| **Decisions** | [D20](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#263-d20--version-scoped-quirks-and-the-two-id-rule-maintainer-2026-10-16) |
| **Open** | `ID-FORMAT-DECISION`, `ID-CLIENT-OID-DECISION`, `ID-V3-IMMUTABLE-DECISION` (needs decision); `ID-SIMPLE-MATCH`, `ID-VALIDATE`, `ID-FIRST-MATCH`, `ID-V1-LOOKUP`, `ID-UNIQUE-INDEX` (blocked) |
| **Audit** | every write reply returns `identifier` and `_id` and says which one matched; an assigned ObjectId's time is the hub's receipt time, never the record's time |
| **Status** | specified (`SPEC-ID`); the v1 `identifier` match for entries and devicestatus is queued for cgm-remote-monitor after 15.0.9 |

## L1 Records

| | |
|---|---|
| **Spec** | [spec/records.md](spec/records.md): rules R1–R9, the generated catalogue with evidence grades, decomposition measured, the settings snapshot and completeness, sensitivity labels, 10 checks. Drawn from `specs/sync/primitives.yaml` (the observation catalogue, graded `measured`, `declared` or `proposed`); [D11](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#26-d11--devicestatus-is-a-decomposition-problem-not-a-column-selection-problem) (devicestatus is decomposed, not given columns); [hub-sync §3.3](nightscout-hub-sync-architecture-2026-09-11.md#33-composite-on-the-wire-primitive-in-storage) |
| **Evidence** | [typed schema evidence](nightscout-typed-schema-evidence-2026-09-10.md); [primitive coverage](nightscout-primitive-coverage-2026-09-11.md); [devicestatus and profile fidelity](nightscout-devicestatus-profile-fidelity-2026-09-10.md); [extensibility models](nightscout-extensibility-models-2026-09-10.md); [quirks registry](../../../specs/quirks/README.md) |
| **Schemas** | `specs/nsschema/*.model.json` (today's collections); `specs/sync/controller-settings.schema.json`; `specs/sync/sensitivity.yaml` (the two-axis sensitivity label) |
| **Open** | devicestatus and profile decomposition coverage is unmeasured ([hub-sync §7](nightscout-hub-sync-architecture-2026-09-11.md#7-what-is-not-measured)) |
| **Audit** | the composite document is kept beside its decomposed records, so "what did the device send" stays answerable |
| **Status** | evidenced (`SPEC-RECORDS`); treatment routing measured at 99.86% by `eventType` alone; devicestatus and profile decomposition not measured |

## L2 Definitions and instances

| | |
|---|---|
| **Spec** | [spec/registration.md](spec/registration.md): the grammar, the capability document, the product resource and fallback, definitions, instances, channels and roles, labels, typed writes, read selection, projected views, retention, binding and the owner, version-scoped quirks, open choices, 186 cases |
| **Evidence** | [controller descriptions](PROPOSAL-controller-descriptions-2026-09-11.md) (the well-known tier); [intent and workflow landscape](nightscout-intent-workflow-landscape-2026-10-09.md) §8–§9 (what a registration must declare); [control-plane reconciliation](../tenancy/nightscout-control-plane-reconciliation-2026-09-11.md) (the kind/instance split of the earlier draft in cgm-remote-monitor `docs/proposals`, which these specifications are proposed to supersede) |
| **Schemas, cases** | `specs/sync/controller-state-model.schema.json`, `hub-capabilities.schema.json`, `registration-submit.schema.json`, `controller-instance.schema.json`; generated registrations in `specs/sync/registrations/`; 54 cases in `specs/sync/conformance/`, 103 in `conformance/instances/` |
| **Decisions** | [D18](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#261-d18--two-tier-controller-registration) and its [addendum](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#d18-addendum--an-extensible-grammar-maintainer-2026-10-12); [D19](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#262-d19--definitions-and-instances-maintainer-2026-10-14) |
| **Open** | `SPEC-REG-MODES`, `SPEC-REG-MIGRATE`; implementation `HUB-REG-CRM`, `HUB-REG-CRM-SEAM`, `HUB-REG-CRM-ADMIN`; adoption `HUB-REG-NOCTURNE`, `PROPOSAL-REG-CONTROLLERS`; §3.7's choices 2, 3, 4, 6, 7, 9, 10, 11 and 12 await the maintainer |
| **Audit** | every typed record carries its instance, its definition id and its role's provenance; projected documents carry `projectedFrom`; records are attributed to the registration and its bound credential, never to a namespace string |
| **Status** | specified (`SPEC-REGISTRATION`) |

## L3 State and intent

| | |
|---|---|
| **Spec** | [spec/state-intent.md](spec/state-intent.md): rules S1–S12 and A1–A12 (composition reported by the controller, kinds, slots, states, end reasons, the wire carrier, requested and applied, initiators, definitions, acceptance, the controller's command contract), the declared kinds (generated), composition per controller, effect and motivation (proposed), what is active at a time, 59 cases; channels from slots are [registration §9](spec/registration.md#9-channels-roles-and-provenance) |
| **Evidence** | [intent and workflow landscape](nightscout-intent-workflow-landscape-2026-10-09.md) (per-controller matrix, end encodings, how each hub decides what is active, command lifecycles); [effects and versioning](nightscout-effects-and-versioning-2026-09-11.md) (effect separated from motivation); [authority model](../../10-domain/authority-model.md) |
| **Schemas** | `specs/sync/controller-state-model.schema.json` (`stateSpans`, `composition`, `commands`); `specs/sync/shared-slots.yaml`; `specs/sync/therapy-effect.schema.json`; `specs/sync/effect-remapping.yaml` |
| **Open** | the active-state choices (state and intent §6.3); undeclared vocabularies for `PROPOSAL-REG-CONTROLLERS`; `LAB-TRIO-INTENT` |
| **Audit** | requested and applied are recorded separately; each span records its end reason and initiator in the controller's own vocabulary; composition is recorded as the controller reports it, never computed by the hub |
| **Status** | specified for declarations (`SPEC-STATE-INTENT`) and, as a proposal with ten choices to confirm, for what is active at a time (rules A1–A12, `SPEC-ACTIVE-STATE`), where `LAB-HUB-ACTIVE-STATE` measured cgm-remote-monitor and Nocturne disagreeing |

## L4 Change and sync

| | |
|---|---|
| **Spec** | [spec/sync-transport.md](spec/sync-transport.md): rules T1–T15 (the write step, re-send outcomes, server write times, the change event; the measured cost; the sync read and write, the merged cursor, one opaque cursor, the low watermark, the socket as fast path; typed records on the socket; definitions and versions), 13 cases. Drawn from the [write contract](../tenancy/write-contract-spec-2026-10-07.md) §2–§3 and §6.1, [hub-sync §3.2](nightscout-hub-sync-architecture-2026-09-11.md#32-the-contract-the-hub-returns) and the [replay-fidelity proposal §1](PROPOSAL-replay-fidelity-changes-2026-09-11.md#1-sync-cost-should-be-o1-in-the-number-of-resources) |
| **Evidence** | `make schema-sync-cost` on 2026-10-18: endpoints each client's code declares, read from source (AndroidAPS `7e1d537d49` 26, three never called; Loop 7; Trio 5), not calls per cycle (sync-transport §3); the write contract's measured matrix; `lib/server/srv-dates.js` on `dev` `fade2299` |
| **Open** | `WRITE-CONTRACT`, `WC-STEP-PATCH`, `ID-BATCH-RESULTS` (blocked); BF-164 (which writes reach the socket); the choices in sync-transport §8; the in-flight window under `single` |
| **Audit** | one change event per write call; a matched re-send stores no second copy and is answered with the stored ids; each mapping the hub applies is recorded as `quirksApplied` |
| **Status** | the write path is decided and specified (T1–T4; T3 merged on `dev`); the sync read, cursor and socket rules are proposed and specified with 13 cases (`SPEC-SYNC-TRANSPORT`); typed socket delivery and versions are proposed without cases |

## L5 Authority

| | |
|---|---|
| **Spec** | [spec/authority.md](spec/authority.md): principals and credentials (AU1–AU5), the binding and credential kind, the owner's actions, the authorisation of registrations and namespaces, who may receive a command, delegation as requirements DR1–DR7 with what is decided around it, what is recorded for audit, 70 cases |
| **Evidence** | [agent trust boundaries](agent-trust-boundaries-2026-10-18.md) (develop, interpret and act; a proposal lifecycle, proposed and not specified); [configuration and delegation §5](../tenancy/nightscout-configuration-and-delegation-2026-09-10.md#5-new-data-and-delegation-between-agents) (what a delegation design must provide); [control-plane reconciliation](../tenancy/nightscout-control-plane-reconciliation-2026-09-11.md); [authority model](../../10-domain/authority-model.md) |
| **Decisions** | [D13–D17](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#1-decisions) (credential root, listeners, auth plane; D17 row 2 open) |
| **Open** | the choices in [commands §9](spec/commands.md#9-open); delegation (authority §7); D17 row 2; the owner choices in authority §9 |
| **Audit** | the owner's listing shows every product's binding, credential kind and binding event, every instance's roles and liveness, and every overlap |
| **Status** | specified for registration, owners and command destinations (`SPEC-AUTHORITY`); the command record, outcomes and proposals are proposed in [commands](spec/commands.md) (`SPEC-REG-COMMANDS`); delegation is not specified |

## Ideas borrowed from Kubernetes

Several parts of this design take what Kubernetes does well for declared, typed resources, and
apply it to controllers that share a hub:

| idea | in Kubernetes | here |
|---|---|---|
| one object shape | `apiVersion`, `kind`, `metadata`, `spec` | every registration and definition has the same four members ([registration §3](spec/registration.md#3-the-grammar)) |
| declared spec, reported status | `spec` is what is wanted, `status` what is observed | a definition declares what a controller's data means; the owner's listing reports what the hub granted, refused and saw overlap ([registration §7–§9](spec/registration.md#7-definitions)); a command record separates the request from its state ([commands §4](spec/commands.md#4-the-command-record-proposed)) |
| reconciliation | a controller drives observed state toward its spec | the controller reconciles; each instance renewal re-evaluates every claim, and the hub records what it observes ([registration §8–§9](spec/registration.md#8-instances)) |
| leases | `coordination.k8s.io` Lease for liveness and leadership | instances hold leases; a lapsed holder loses its roles and is never a command destination ([registration §8](spec/registration.md#8-instances)) |
| labels and selectors | key-value labels, selected by queries | instance labels and read selection ([registration §10, §12](spec/registration.md#10-labels)) |
| typed extension resources | CustomResourceDefinitions, versioned, with conversion | controller-owned definitions with namespaced extensions, version-scoped quirks and projected views for older readers ([registration §7, §13, §16](spec/registration.md#7-definitions)) |
| admission | requests are checked and refused with a reason before they are stored | each element is accepted or refused with a reason code, and nothing is rewritten ([registration §5](spec/registration.md#5-the-product-resource)) |

What the hub does with these is narrower than a Kubernetes control plane: it schedules nothing and
acts on no therapy. It records, routes and refuses; the controller decides and enacts (D18).

## Reading order

For someone new to the series: this page, then the [glossary](spec/glossary.md), then
[intent and workflow landscape](nightscout-intent-workflow-landscape-2026-10-09.md) §2 and §9 for
why the contract exists, then the eight specifications in layer order:

1. [identity](spec/identity.md) (L0): every other specification uses its ids;
2. [records](spec/records.md) (L1): the typed observations a hub stores;
3. [registration](spec/registration.md) (L2): how a controller declares what those records mean,
   the largest file;
4. [state and intent](spec/state-intent.md) (L3): requested, applied and active state;
5. [commands](spec/commands.md) (L3, L5): requests and proposals that reach a controller;
6. [plans](spec/plans.md) (L3, L5): recurring intents approved once and held by the controller;
7. [sync-transport](spec/sync-transport.md) (L4): how all of the above moves;
8. [authority](spec/authority.md) (L5): who may do each of the above.

Across the eight, [control loops](spec/control-loops.md) is an STPA analysis: it draws the loops
the specifications set up, lists each unsafe control action with the rule that prevents it, and
names the gaps the specifications now carry as open. [Compatibility](spec/compatibility.md) says,
for every app the corpus holds and every layer, what the app does today and what it sees from a
hub that implements the specifications without the app changing.

Two guides walk a controller developer through the specifications step by step, each step naming
its rule and the conformance case that shows it: [add a setting in your next
release](guides/add-a-setting.md) and [bring a new controller onto a hub](guides/new-controller.md).
