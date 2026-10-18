# The earlier control-plane draft and the specifications proposed to supersede it

*What this is: a supersession map (contributor-facing). Read after the [platform
specifications](../platform/README.md#reading-order); leads to [integration questionnaire
defaults](../platform/integration-questionnaire-defaults-2026-10-18.md).* **Snapshot — describes the
earlier draft at cgm-remote-monitor `a8888f0d` and this repository's specifications at `main`
`df93608c` (2026-10-18). Status: current; no decision rests on it.** Current decisions: [execution
plan §1](nightscout-multitenancy-execution-plan-2026-09-14.md#1-decisions). The 2026-09-11 analysis
of the same draft is in git: [full text at
`85c645c8`](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/85c645c8b003b61dc07ea31f8a7002711493b18a/docs/30-design/tenancy/nightscout-control-plane-reconciliation-2026-09-11.md).

The earlier draft in cgm-remote-monitor's `docs/proposals` came from earlier versions of this
repository and was added there in cgm-remote-monitor `12c90cfc` (2026-01-19). This repository's
[platform specifications](../platform/README.md) are proposed to supersede it. Each row below names
the rule that now carries an idea of the draft and what changes. The specifications share one
premise: the hub routes and records, never composes intents, never judges whether a change is safe
and never doses; validation and enactment stay the controller's (D18).

## 1. The earlier draft

Read at cgm-remote-monitor `a8888f0d`; none of the five files has changed since `db32bdc6`
(2026-01-18).

| file | what it proposes | proposed to be superseded by |
|---|---|---|
| `agent-control-plane-rfc.md` | an event envelope; configuration, runtime, computed, delivery and capability objects; ten collections and an event stream; bridge mode; authority, scopes, delegation and audit | [records](../platform/spec/records.md), [registration](../platform/spec/registration.md), [state and intent](../platform/spec/state-intent.md), [commands](../platform/spec/commands.md), [sync transport](../platform/spec/sync-transport.md), [authority](../platform/spec/authority.md) |
| `bridge-rules.md` | synthesising those objects from today's `devicestatus`, `treatments` and `profile` | [registration §2–§3](../platform/spec/registration.md#2-two-tiers) (well-known registrations), [records R1–R2](../platform/spec/records.md#2-rules), [state and intent S6–S7](../platform/spec/state-intent.md#2-rules) |
| `conflict-resolution.md` | an authority hierarchy, five conflict scenarios, optimistic locking, a global event cursor, delegation grants, safety invariants | [state and intent S1, A7–A9](../platform/spec/state-intent.md#2-rules), [sync transport T8–T9](../platform/spec/sync-transport.md#4-the-sync-read-and-write-proposed), [authority §7](../platform/spec/authority.md#7-delegation-not-decided) |
| `oidc-actor-identity-proposal.md` | verified actor identity through OpenID Connect, an `actors` collection, delegation claims, a migration away from `enteredBy` | [authority AU1–AU4](../platform/spec/authority.md#2-principals-and-credentials), [authority §8](../platform/spec/authority.md#8-what-is-recorded-for-audit) |
| `integration-questionnaire.md` | 16 questions to Loop, AAPS, Trio and OpenAPS implementers | [integration questionnaire defaults](../platform/integration-questionnaire-defaults-2026-10-18.md): a default answer per controller, read from source |

## 2. Supersession map

### 2.1 Objects

| earlier draft | replaced by | what changes |
|---|---|---|
| `EventEnvelope` (`eventId`, `cursor`, `issuer`, `issuerSeq`, `idempotencyKey`, `refs`) | [identity I1, I5](../platform/spec/identity.md#1-rules); [sync transport T4, T8](../platform/spec/sync-transport.md#2-the-write-path); [state and intent S8](../platform/spec/state-intent.md#2-rules); [registration §11](../platform/spec/registration.md#11-typed-writes-and-attribution) | No envelope. A record keeps its own `identifier` (the client's sync identity, which is the idempotency key) and `_id`; a write produces one change event; the cursor is opaque; who started an intent is its initiator, and which running copy wrote a record is its instance |
| `ProfileDefinition` (`profileId`, `contentHash`, schedules, insulin model) | [records R1](../platform/spec/records.md#2-rules) (`TherapySettings` and four schedules); [state and intent S9](../platform/spec/state-intent.md#2-rules) | A profile decomposes into typed primitives. A stable profile id is something a controller declares (`definitions.idField`); no controller sends one today ([questionnaire defaults A1](../platform/integration-questionnaire-defaults-2026-10-18.md#a1-profile-identification)) |
| `OverrideDefinition`, `OverrideInstance`, `ProfileSelection` | [state and intent S2–S9](../platform/spec/state-intent.md#2-rules) and [A1–A13](../platform/spec/state-intent.md#61-rules) | One declaration per intent kind (S2) with its slot (S3), states (S4), end reasons (S5), wire carrier (S6), requested and applied carriers (S7), initiators (S8) and definitions (S9). The hub derives what is active from the controller's own records; `status: superseded` and `supersededBy` become the declared `supersedes` (S3, A7) |
| `PolicyComposition` | [state and intent S1, §4](../platform/spec/state-intent.md#2-rules); [records §5](../platform/spec/records.md#5-settings-snapshot) | The hub never computes it. The controller reports its composed result where it publishes one (`composition.result`); effective limits are settings in an effective-dated `ControllerSettings` snapshot |
| `DeliveryRequest` (`basedOn.policyCompositionId`, `expiresAt`) | [commands CM1–CM6](../platform/spec/commands.md#4-the-command-record-proposed), [CM11](../platform/spec/commands.md#6-proposals-and-approvals-proposed) | A command record with the payload, its `payloadHash` and a required expiry (CM3); after an approval it carries `basedOn`, the hub's [state version](../platform/spec/state-intent.md#61-rules) (A12) |
| `DeliveryObservation` (`confidence`, `pumpResponse.acked`, `errorCode`) | [records §3](../platform/spec/records.md#3-the-catalogue) (`Bolus`, `TempBasal`, `ApsSnapshot`); [commands CM7–CM9](../platform/spec/commands.md#5-outcomes-proposed) | A delivery is a typed primitive with an evidence grade per field (R4). Whether a command was received or enacted is the destination's outcome report, `acknowledged`, `succeeded`, `failed` or `refused`, with a reason (CM8) |
| `Reconciliation` (`matched`, `partial`, `blocked`, `unknown`, `expired`) | [commands §4 states, CM9](../platform/spec/commands.md#4-the-command-record-proposed) | The hub sets only hand-over states (`sent`, `fetched`, `unconfirmed`, `undeliverable`, `expired`); outcomes are the controller's. A command enacted in part is open ([commands §9](../platform/spec/commands.md#9-open) item 4) |
| `ControllerKindDefinition` (`kindId`, `version`, `supportedFeatures`, `eventCapabilities`) | [registration §2–§3, §7](../platform/spec/registration.md#2-two-tiers) | A product registration in two tiers: well-known, generated by the hub from measurement, and controller-owned. Definitions are content-addressed (`sha256:` of RFC 8785 canonical JSON) and several coexist per product. What a controller can do is declared per element: intent kinds, commands, replay inputs, settings |
| `ControllerInstanceRegistration` (`instanceId`, `device`, `pumpBinding`, `cgmBinding`, `lastSeenAt`) | [registration §8](../platform/spec/registration.md#8-instances); [identity §2](../platform/spec/identity.md#2-contract-ids) | The instance id is a random UUID v4 the controller supplies; liveness is a lease; an instance carries no hardware identifiers. `devicestatus.device` is at most an observed alias, labelled identifying and withheld by default (§3.3) |
| `CapabilitySnapshot` (`connectivity`, `automationState`, `effectiveLimits`, `health`) | [records §3, §5](../platform/spec/records.md#3-the-catalogue); [registration §4](../platform/spec/registration.md#4-the-capability-document), [§8](../platform/spec/registration.md#8-instances) | Split by what each part is: pump, uploader and loop state are the `PumpSnapshot`, `UploaderSnapshot` and `ApsSnapshot` primitives; limits are `ControllerSettings`; liveness is the instance lease. The capability document at `/.well-known/nightscout/sync` describes the hub software, never a person |
| Ten collections, and `/api/v3/events` with WebSocket and SSE subscriptions | [sync transport T5–T11](../platform/spec/sync-transport.md#4-the-sync-read-and-write-proposed); [registration §13](../platform/spec/registration.md#13-projected-views-for-older-readers) | One read across collections, one batch write and one opaque cursor (an event cursor, if one is added, is the same cursor); socket subscription by product and channel. Typed records reach older readers as projected documents |
| Bridge mode and `bridge-rules.md` (detection, profile hashing, override and delivery extraction, idempotency) | [registration §2–§3](../platform/spec/registration.md#2-two-tiers), [§16](../platform/spec/registration.md#16-version-scoped-quirks); [records R1–R2](../platform/spec/records.md#2-rules); [state and intent S6–S7](../platform/spec/state-intent.md#2-rules); [identity I5–I7](../platform/spec/identity.md#1-rules) | Well-known registrations served at `/.well-known/nightscout/controllers` describe today's writers as they are; decomposition is declared with structural discriminators, never the `device` string; version-specific encodings are recorded quirks. A re-send matches on `identifier`, then `_id`, then the collection's natural key |

### 2.2 Rules

| earlier draft | replaced by | what changes |
|---|---|---|
| Authority hierarchy (human 100, caregiver 80, agent 50, controller 30) and conflict rules: composition by most restrictive target and lowest basal multiplier, supersession by authority, profile selection by recency | [state and intent S1, S3, A7–A9](../platform/spec/state-intent.md#2-rules); [authority §7](../platform/spec/authority.md#7-delegation-not-decided) | Composition is the controller's rule and differs per controller ([state and intent §4](../platform/spec/state-intent.md#4-composition-as-read-from-each-controllers-source)). The hub reports each product's instances, ends one by another only as the controller declares (`supersedes`, `overlay`), and marks overlap without resolving it (A9) |
| Flip-flop prevention: rate limits per issuer, a cooldown, confirmation after N activations | [commands §9](../platform/spec/commands.md#9-open) (proposal volume, UCA-PROP-002) | Open: nothing limits the open proposals one instance holds on a channel |
| Optimistic locking on `srvModified`; a global `eventCursors` counter | [registration §5.4](../platform/spec/registration.md#54-etag-and-idempotency); [sync transport T3, T8, T9](../platform/spec/sync-transport.md#2-the-write-path) | Registration resources use etags and `If-Match`. Records are ordered by the server's `srvModified` (unique and never decreasing within a process) under `single` and by the replication slot under `multi`, behind one opaque cursor with a low watermark, so a slow write is never skipped. No global counter document |
| Identity model: human and caregiver by OAuth, controller by a device-bound key, agent by OAuth with a delegation token | [authority AU1–AU4](../platform/spec/authority.md#2-principals-and-credentials) | By audience: devices and uploaders hold a native per-tenant credential; owners and caregivers are to sign in through one Ory Kratos pool on hosted sites (adopted in principle, gated); third-party delegated access is deferred. Everything binds to a subject, never a token |
| `issuerType: human \| controller \| agent` | [state and intent S8](../platform/spec/state-intent.md#2-rules); [registration §9](../platform/spec/registration.md#9-channels-roles-and-provenance) | The initiator is a value in the controller's own vocabulary. An agent initiator is `{value: other, controllerTerm}`; no `agent` value is added (maintainer, 2026-10-18). An agent's role is an `other` role a hub lists |
| Scopes `read`, `suggest` ("can propose, human must approve"), `activate`, `deliver`, `admin` | [authority AU5, §5](../platform/spec/authority.md#2-principals-and-credentials); [commands CM5, CM12, CM14](../platform/spec/commands.md#6-proposals-and-approvals-proposed) | Permissions per collection and action. Proposing needs `api:proposals:create` and a granted propose role; approving needs `api:commands:create`, because approving is sending; a proposer cannot approve its own proposal; reading confers neither (CM12). Registering needs `api:registrations:create` |
| `DelegationGrant` (`grantedBy`, `grantedTo`, `scopes`, `constraints`, `expiresAt`, `revokedAt`) and grant validation | [authority §7, DR1–DR7](../platform/spec/authority.md#7-delegation-not-decided) | Requirements stated; the grant's shape, storage and checks are open ([authority §9](../platform/spec/authority.md#9-open) item 6). The [authority model](../../10-domain/authority-model.md) keeps a worked example of a grant with constraints |
| Audit: append-only events with `issuer` and `authority`; optional signed events and a hash chain per issuer | [authority §8](../platform/spec/authority.md#8-what-is-recorded-for-audit); [commands CM1, CM10](../platform/spec/commands.md#4-the-command-record-proposed) | The owner's listing records current bindings, roles and overlaps; typed records carry instance, definition and provenance; a command is recorded before it is sent. Binding an approval end to end needs a signature by the sender or approver (CM10). Who took an owner action, and reads, are not recorded |
| OIDC actor identity: an `actors` collection, RFC 8693 delegation claims, `enteredBy` replaced by verified claims | [authority AU1, AU3, AU4, §8](../platform/spec/authority.md#2-principals-and-credentials); [records R9](../platform/spec/records.md#2-rules) | Identity is per cohort; credentials and authorization are per tenant. `enteredBy` stays a free-text field labelled identifying, never an identity |
| Safety invariants ("human always wins", composed effects within safety limits, conservative composition) | [state and intent S1](../platform/spec/state-intent.md#2-rules); [commands CM5, CM10](../platform/spec/commands.md#4-the-command-record-proposed) | They bind the controller, which composes and validates. The hub checks only routing, expiry, size and permission, and never changes a payload |
| Integration questionnaire | [integration questionnaire defaults](../platform/integration-questionnaire-defaults-2026-10-18.md); [state and intent S10–S11](../platform/spec/state-intent.md#2-rules); [records R8](../platform/spec/records.md#2-rules) | Every question has a default per controller, read from source, for its authors to correct. What the questions ask is what a registration declares: acceptance policy, command paths, replay inputs |

## 3. Measured findings the specifications carry

Measured over the corpus in `reports/schema-census/` (snapshots dated 2026-04-01 and 2026-04-26;
11 sites, 9 of them Loop; one site carries `openaps.*`, and it is Trio's; no AndroidAPS closed-loop
site and no oref0 rig). Counts are `docs_present` across both snapshots, which overlap, so they
bound distinct documents from above; §3.4 counts distinct documents.

### 3.1 Fields already on the wire

| what the draft proposes | on the wire today | where the specifications use it |
|---|---|---|
| an idempotency key | `treatments.syncIdentifier`, 306,741 (83%, 10 sites) | the client's `identifier` ([identity I1, I5](../platform/spec/identity.md#1-rules)) |
| a human or automation flag | `treatments.automatic`, boolean, 300,228 (81%, 10 sites) | `Bolus.Automatic` ([records §3](../platform/spec/records.md#3-the-catalogue)); a wire value can stand for an initiator through `wireProxy` ([state and intent S8](../platform/spec/state-intent.md#2-rules)) |
| controller version | `loop.version` 597,335 (85%, 10 sites); `openaps.version` 73,898 (1 site) | the product and version a settings snapshot carries ([records R5](../platform/spec/records.md#2-rules)) |
| override state | `override.active` 597,335 (85%, 10 sites) | Loop's applied override carrier ([state and intent S7](../platform/spec/state-intent.md#2-rules)) |

### 3.2 Trio and AndroidAPS both write `openaps`

No corpus document has a top-level `trio` key, and Trio's wire model declares `openaps`,
`suggested` and `enacted` (`Trio/Sources/Models/NightscoutStatus.swift`). The well-known Trio and
AndroidAPS registrations use the same structural discriminator, `{path: openaps, test: is-object}`
(`specs/sync/registrations/trio.yaml:18-20`), so the two cannot be told apart by a top-level key,
and cgm-remote-monitor's readers cannot either (`lib/plugins/openaps.js:82`). In the
specifications a registered controller's records are attributed to its instance and definition
([registration §11](../platform/spec/registration.md#11-typed-writes-and-attribution)), and a
controller-published registration takes precedence over a structurally inferred one
([registration §2](../platform/spec/registration.md#2-two-tiers)).

### 3.3 Instance identity and the `device` string

`devicestatus.device` is on every devicestatus document and is free text: one site's device
strings read like a controller while its treatments show no automated dosing. An instance id is a
random UUID v4 the controller supplies, never derived from a device name, model, serial number or
`devicestatus.device` ([identity §2](../platform/spec/identity.md#2-contract-ids)); the hub may
keep the string as an observed alias, labelled `{level: identifying, category: device}` and
withheld by default ([registration §8](../platform/spec/registration.md#8-instances)).

### 3.4 Overrides with a name and no effect

Of the 55,938 distinct devicestatus documents with an active override:

| | count | share |
|---|---:|---:|
| effect and name both present | 42,799 | 76.5% |
| effect only | 2,176 | 3.9% |
| **name only, no effect** | **10,892** | **19.5%** |
| neither | 71 | 0.1% |

Of 2,865 temporary effects in treatments, 399 carry a label and no effect. A reader that
synthesises an override's effect from these records gets none for one in five. In the
specifications the hub never computes a composed result from them ([state and intent
S1](../platform/spec/state-intent.md#2-rules)); a kind declares the fields it does not publish
(`unpublishedFields`, S6); and a setting a controller does not publish is recorded as not
published, never filled with a default ([records R6](../platform/spec/records.md#2-rules)). The
draft therapy-effect schema separates an effect from why it was asked for ([state and intent
§5](../platform/spec/state-intent.md#5-effect-and-motivation-proposed)).

### 3.5 Suggested, requested and confirmed

| state | Loop | oref0 family (Trio, AAPS) |
|---|---|---|
| suggested, manual bolus | `loop.recommendedBolus`, 597,143 (85%, 10 sites) | `openaps.recommendedBolus`, 41,474 (1 site) |
| suggested, automatic dose | `loop.automaticDoseRecommendation`, 183,049 (26%, 10 sites) | `openaps.suggested`, 73,898 (1 site) |
| requested | not published | not published |
| confirmed | `loop.enacted` with `received`, 405,228 (58%, 10 sites) | `openaps.enacted` with `received`, 73,834 (1 site) |

Loop's writer sets `loop.enacted.received` to `true` whenever there is a recommendation and no
error, so it is not a pump acknowledgement; Trio sets `received` from the pump call's result
([questionnaire defaults C7](../platform/integration-questionnaire-defaults-2026-10-18.md#c7-delivery-state-distinction)).
Loop's only failure text is `loop.failureReason`, a string on 16,550 documents (2.4%). The
suggestions decompose into `ApsSnapshot`'s `RecommendedBolus` and `Enacted`
([records §3](../platform/spec/records.md#3-the-catalogue)); a request recorded apart from its
effect is the requested carrier ([state and intent S7](../platform/spec/state-intent.md#2-rules));
for a command, handed over and not yet acknowledged is the `sent` or `fetched` state
([commands §4](../platform/spec/commands.md#4-the-command-record-proposed)).

### 3.6 Safety limits

Loop records its limits in `profile.loopSettings` (200 profile documents, 10 sites). The corpus
holds no `max_iob` from any oref0 derivative, so a replay of corpus data has to assume it. oref0's
own rig uploads its `preferences` file, `max_iob` included, as `devicestatus.preferences` (oref0
`d219baf9` `bin/ns-status.js:40-49,175-177`); Trio and AndroidAPS write a cap only into `reason`
text when it binds. Of the dosing inputs each family declares, Nightscout records 20% for Loop and
50% for the oref0 family (55% and 72% counting derivable inputs). The specifications carry this as
the settings snapshot and the declared replay inputs ([records R5, R6, R8,
§5](../platform/spec/records.md#5-settings-snapshot)).

### 3.7 Sync cost of typed collections

API v3 gives a client one delta read per collection, so a client that uses it as designed reads
each collection separately, and every typed collection added adds a read. One read and one write
across collections make the cost independent of the number of collections ([sync transport §3,
T5, T7](../platform/spec/sync-transport.md#3-what-each-clients-sync-code-can-call)). The change
list is the [replay-fidelity proposal](../platform/PROPOSAL-replay-fidelity-changes-2026-09-11.md) §1.

## 4. Examples

### 4.1 An override proposed, approved, requested and applied

An agent instance proposes an exercise override; a person approves it; Loop, as a registered
controller holding the `override` channel's `command-sink`, enacts it. Each step is a typed
record. Identifiers are shortened, and the payload is illustrative, because no definition yet
declares a command payload's shape ([commands §9](../platform/spec/commands.md#9-open) item 3).

```yaml
# 1. Proposal (commands CM11). The agent's own instance holds a propose role (CM12).
proposal:
  proposalId: p-41
  instanceId: 9b2f…            # the agent's instance (registration §8)
  channel: override
  payload: {preset: Exercise, durationMinutes: 60}
  payloadHash: sha256:7c1e…
  basedOn: sha256:a90d…        # Loop's state version the agent read (state and intent A12)
  expiresAt: 2026-10-18T15:10:00Z
  state: open

# 2. The approval names the hash (CM13, CM14). The hub creates one command (CM1).
approval: {proposalId: p-41, payloadHash: sha256:7c1e…}
command:
  commandId: c-118
  proposalId: p-41
  payloadHash: sha256:7c1e…
  initiator: {value: other, controllerTerm: agent}   # state and intent S8
  state: pending

# 3. Loop fetches it (CM18), checks the hash, the expiry and its own limits (CM10),
#    enacts it, and reports the record that shows the effect (CM7).
outcome: {commandId: c-118, state: succeeded, payloadHash: sha256:7c1e…, record: {identifier: 5d3a…}}

# 4. Loop's records give the two layers the hub reports (state and intent S7, A10):
#    treatments   `Temporary Override`, duration in minutes      -> the requested instance
#    devicestatus `override`, duration in seconds remaining      -> the applied layer
```

### 4.2 An approval bound to a payload hash

The proposal's payload hashes to `sha256:7c1e…`. An approval naming `sha256:7c1e…` creates a
command whose payload is the proposal's, byte for byte. An approval naming any other hash is
refused 409 `hash-mismatch`, and the proposal stays `open`. An approval after Loop's records have
changed the state version is refused 409 `state-changed` (CM15); one after the `override`
channel's `command-sink` has moved to another Loop instance is refused 409 `destination-changed`
(CM13). The state version is the hub's record of what Loop reported, so `state-changed` tells the
approver that the record changed, never that Loop's own state is unchanged.
