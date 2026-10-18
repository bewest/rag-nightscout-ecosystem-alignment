# Platform contracts: where each piece is specified

*Contributor-facing. Living index, current at `main` `5a9a49cc` (2026-10-18). Terms are defined in
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
| **Spec today** | `specs/sync/primitives.yaml` (the observation catalogue, graded `measured`, `declared` or `proposed`); [D11](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#26-d11--devicestatus-is-a-decomposition-problem-not-a-column-selection-problem) (devicestatus is decomposed, not given columns); [hub-sync §3.3](nightscout-hub-sync-architecture-2026-09-11.md#33-composite-on-the-wire-primitive-in-storage) |
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
| **Spec today** | `stateSpans` in [hub-sync §3.1](nightscout-hub-sync-architecture-2026-09-11.md#31-registration) (slot, states, end reasons, wire carrier, requested and applied, initiators, composition, `acceptsFromHub`); channels, the shared slot list and `sameAs` in [registration §9](spec/registration.md#9-channels-roles-and-provenance) |
| **Evidence** | [intent and workflow landscape](nightscout-intent-workflow-landscape-2026-10-09.md) (per-controller matrix, end encodings, how each hub decides what is active, command lifecycles); [effects and versioning](nightscout-effects-and-versioning-2026-09-11.md) (effect separated from motivation); [authority model](../../10-domain/authority-model.md) |
| **Schemas** | `specs/sync/controller-state-model.schema.json` (`stateSpans`, `composition`, `commands`); `specs/sync/shared-slots.yaml`; `specs/sync/therapy-effect.schema.json`; `specs/sync/effect-remapping.yaml` |
| **Open** | iAPS has no registration; end-reason vocabularies for Trio override and temporary target and for AndroidAPS profile switch, AndroidAPS initiator values and every command vocabulary are undeclared (landscape §10); `LAB-TRIO-INTENT` |
| **Audit** | requested and applied are recorded separately; each span records its end reason and initiator in the controller's own vocabulary; composition is recorded as the controller reports it, never computed by the hub |
| **Status** | evidenced and declared in the generated registrations; `LAB-HUB-ACTIVE-STATE` measured cgm-remote-monitor and Nocturne disagreeing on what is active for the same records (landscape §5) |

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
| **Open** | `SPEC-REG-COMMANDS` (the command API itself is not specified); delegation of a principal's authority to a caregiver, app or agent, and proposals awaiting approval, are not specified |
| **Audit** | the owner's listing shows every product's binding, credential kind and binding event, every instance's roles and liveness, and every overlap |
| **Status** | specified for registration and routing; not specified for commands and delegation |

## Reading order

For someone new to the series: this page, then the [glossary](spec/glossary.md), then
[intent and workflow landscape](nightscout-intent-workflow-landscape-2026-10-09.md) §2 and §9 for
why the contract exists, then the [identity](spec/identity.md) and [registration](spec/registration.md)
specifications for the contract itself.

## Planned layout

Each layer's living specification has, or will have, its own undated file under `spec/`:
[identity](spec/identity.md) and [registration](spec/registration.md) are written; `state-intent`,
`sync-transport` and `authority` are queued as `SPEC-STATE-INTENT`, `SPEC-SYNC-TRANSPORT` and
`SPEC-AUTHORITY`. `SPEC-AUTHORITY` moves registration §15 into the authority specification. The dated documents
above stay where they are as snapshots, and each moved section leaves a pointer to its new home.
