# L3 State and intent: what was requested, applied and active, who started it, and why it ended

*Contributor-facing. Living specification, current at `main` `92a7d31b` (2026-10-18). Layer L3 of
the [platform index](../README.md); terms are in the [glossary](glossary.md). The grammar members
named here are part of the [registration specification](registration.md) §3; how a hub accepts
them is there too. Decisions: [D18](../../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#261-d18--two-tier-controller-registration)
(the hub observes, the controller composes) and the maintainer's 2026-10-18 decision on agent
initiators ([execution plan §2.6.3](../../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#263-d20--version-scoped-quirks-and-the-two-id-rule-maintainer-2026-10-16)
row 17). Queue: `SPEC-STATE-INTENT`.*

*Specification 4 of 7 in the [reading order](../README.md#reading-order); after registration, whose grammar it uses, and before commands. Expect rules S1–S12 and A1–A13, the declared kinds per controller, composition, what is active at a time, and the conformance cases.*

A controller manages *intent*: a preset is activated, several intents run at once and combine, the
controller applies something that may differ from what was asked, and the intent ends for a
reason. Nightscout's collections manage *entities*. This page says how a controller declares its
intent model, so that a reader can tell what was requested, what was applied, who started it and
why it ended, and what the hub may and may not conclude from the records. Status: rules S1–S12 are specified;
the active-state rules A1–A13 are proposed and specified with cases; §3, §4 and §7 are evidenced;
§5 is proposed; none is implemented.

The evidence is the [intent and workflow landscape](../nightscout-intent-workflow-landscape-2026-10-09.md),
read from Loop, Trio, iAPS and AndroidAPS source and measured where it says so.

## 1. What entity records lose

| # | property | what it means | how today's documents lose it |
|---|---|---|---|
| P1 | definition identity | an activation refers to a preset by a stable id | presets are copied into the instance, or referenced by name only |
| P2 | concurrent slots and composition | several intents active at once, combined by a controller rule | one collection, one "latest wins" reading per `eventType` |
| P3 | requested versus applied | what was asked, what the device or algorithm accepted, what it computed | one document is both request and effect, or the effect is elsewhere and unlinked |
| P4 | end reason | expired, cancelled, superseded, deleted before start, ended by a trigger | "ended" is a shortened `duration`, a delete, or a zero-duration record |
| P5 | initiator | phone, watch, shortcut, automation, caregiver, remote | kept locally or in debug logs; on the wire only free-text `enteredBy` |
| P6 | command lifecycle | request, validate, apply, acknowledge, with a correlation id | no request record; success visible only as the resulting entity; failure as free text |

Every rule below exists so that one of P1–P6 survives into the record.

## 2. Rules

| # | rule |
|---|---|
| S1 | **The hub observes; the controller composes.** Overlapping intents are combined by a controller-specific rule that depends on algorithm settings. The hub records the result the controller reports and never computes it: `composition` is declared with `reportedBy: controller` and `hubComputes: false`, with where the result is published (`result`, or null) and whether it names the intents it came from (`linkedToIntents`). `rule` is the controller's rule as read from its source, informational only. |
| S2 | **One declaration per intent kind.** A `stateSpans` entry declares one kind: `category` (open, and the only required member; what the hub renders and queries it under) and `kind` (the controller's own name). Its horizon is `span` unless it declares another. An entry may also carry `dualWriteLink` ([registration §6](registration.md#6-the-controllers-side-fallback-and-refused-writes)) and `wellKnownRef` ([registration §7](registration.md#7-definitions)). |
| S3 | **Slots.** `slot` names the exclusivity group. `exclusiveWithinSlot`: at most one instance is active in the slot at a time. `coexistsWith`: the slots that can be active at the same time; how they combine is S1. `overlay`: a timed instance applies over an open-ended one, which applies again when the timed one ends. `supersedes`: a later instance of this kind from this controller ends an overlapping earlier one, as the controller does it. The hub reads these to render and query the controller's own records; it never reconciles between controllers. `sameAs` names the shared slot a slot means; how a slot becomes a channel for roles, and the `sameAs` checks, are [registration §9](registration.md#9-channels-roles-and-provenance). |
| S4 | **States.** The vocabulary is `scheduled` (exists, not yet started), `active` and `ended`, written as a list of strings; registrations generated before 2026-10-12 used `active` and `inactive`. |
| S5 | **End reasons.** Shared values `expired`, `cancelled`, `superseded`, `deletedBeforeStart`, `endedByTrigger`, or `other`, which requires `controllerTerm` and is rendered "other: *term*". Any reason may also carry the controller's own `controllerTerm` (Loop declares `expired` as "natural"). `endedByTrigger` lists its `triggers`, a list of strings whose vocabulary is `carbs`, `glucoseAbove`, `glucoseBelow`, `loopOff`, `chain`. |
| S6 | **The wire carrier.** `wire` says how today's documents carry instances of the kind: the collection; `eventType`, or `documentIdentifier` for a single named document (such as one in the v3 `settings` collection); a `discriminator` (`path` and `test`: `exists`, `is-object`, `equals` with a `value`, or `{value: other, controllerTerm}`); `paths`, each a dotted path string or a typed path `{path, unit, type or typeRef}` that carries the typing members of a field declaration ([registration G2](registration.md#3-the-grammar)), so a carrier field can declare its unit (AndroidAPS declares `timeshift` in milliseconds); a typed path with no typing member names the same field, with the same meaning, as the bare string; `vocabularies` (closed value sets by path), `unpublishedFields` and `writtenWhen`; `durationField`, the path that carries the duration, and `durationUnit` (`seconds`, `minutes`, `milliseconds`); `identity`, the fields that identify one instance across amendments; `indefinite`, how an open-ended instance is written; `endedEncoding`, how an early end is written (`amend-duration`, `delete-and-repost`, `repost-same-created_at`, `zero-duration-record`, `sampled-state`, or `{value: other, controllerTerm}`); `cancelBeforeStartEncoding` (`delete`, `soft-delete`, `zero-duration-record`); and `endReasonPath`, or null when the reason is not sent and can only be inferred from the encoding. `wire: null` means the controller keeps the intent and publishes no instance record. |
| S7 | **Requested and applied are separate.** `requested` says where the request is recorded when it is a different record from the applied effect; `applied` says where the controller reports what it applied; either is null when not published. Both are carriers with the members S6 lists, except the ones only `wire` has (`identity`, `indefinite` and the end encodings), so each declares its own `durationField` and `durationUnit`: Loop's applied override reports `override.duration` in seconds remaining while its wire override's `duration` is in minutes. A carrier's `linkToRequest` names the field that links an applied record to its request, or null. A request record alone does not show that anything was applied: AndroidAPS writes an effective profile switch only after the pump accepts the profile switch, and a profile switch with none following is one that failed or is pending. |
| S8 | **Initiators.** `initiators` gives the controller's vocabulary name, its `values`, the `wirePath` that carries it (or null), and a `wireProxy` where one wire value stands in for one initiator. Each value is a string in the controller's own vocabulary, which is not a shared list, so any string is valid; a value outside that vocabulary is written `{value: other, controllerTerm}` and rendered "other: *term*". Decided 2026-10-18: no `agent` value is added to any initiator vocabulary, and an agent initiator takes that `other` form; a shared value is named once the corpus or a lab shows one in use. No controller records an agent as initiator today. |
| S9 | **Definitions.** `definitions` says where presets are `published` (or null), the `idField` that carries a stable id on the wire (or null), whether an instance refers to its definition by `id`, `name` or `copy` (`referencedBy`), and the `fields`, `unpublishedFields` and `controllerUniqueFields`. |
| S10 | **Acceptance policy.** `acceptsFromHub` says which hub-originated intent of the kind the controller acts on: `channels` (`command`, a remote command delivered to it; `treatment-download`, treatments other clients wrote that it reads and applies), the gating `preference` and its `default`, and whether acceptance or rejection is `acknowledged` where the hub can see it. Only a kind accepting `command` can carry a `command-sink` role. |
| S11 | **The controller's command contract.** `commands[]` declares each path by which commands reach the controller: `transport` (`apns`, `sms`, `nightscout-settings`, `nightscout-treatment`, or `{value: other, controllerTerm}`), `availability` (the AndroidAPS `nightscout-settings` path is `dev-only`: in the 4.0.0 prereleases and absent from the latest release, 3.4.2.6), `hubInPath` (`no`, `optional`, `yes`), `authorisation`, `expiry`, `acknowledgement` (`states`, `replyChannel`, `correlationId`, `failureRecord`) and `evidence`. The hub's own command API and the proposal record in front of a command are the [commands specification](commands.md). |
| S12 | **A kind's meaning is versioned.** Every member above except `description`, `evidence`, `availability` and the version members is meaning: a different meaning at the same version is rejected `version-conflict` ([registration §7](registration.md#7-definitions)). A controller that changes how it encodes an end, a unit or a vocabulary declares a new version of the kind. |

## 3. What the well-known registrations declare

Generated from `specs/sync/registrations/` (`make schema-sync-model`). Read-derived from each
controller's source except the counts the landscape marks measured.

<!-- BEGIN GENERATED: state-intent-kinds (tools/nsschema/spec_cases.py) -->
| controller | kind | category | slot | coexists with | ended on the wire | requested | applied | initiators | accepts from hub |
|---|---|---|---|---|---|---|---|---|---|
| Loop | TemporaryScheduleOverride | Override | override | preMeal | `Temporary Override`, amend-duration | undeclared | yes | EnactTrigger | command |
| Loop | TemporaryScheduleOverride (context preMeal) | PreMealTarget | preMeal | override | not published | undeclared | undeclared | — | — |
| Loop | dosingEnabled | LoopMode | loopMode | — | profile, sampled-state | yes | not published | — | — |
| Trio | OverrideStored | Override | override | temporaryTarget | `Exercise`, delete-and-repost | undeclared | yes | AdjustmentSource | command |
| Trio | — | TemporaryTarget | temporaryTarget | override | `Temporary Target`, repost-same-created_at | undeclared | yes | AdjustmentSource | treatment-download |
| Trio | DosingMode | LoopMode | loopMode | — | devicestatus, sampled-state | undeclared | undeclared | — | — |
| AndroidAPS | ProfileSwitch | ProfileState | profileSwitch | temporaryTarget, runningMode, scene | `Profile Switch`, amend-duration | yes | yes | Sources | treatment-download |
| AndroidAPS | — | TemporaryTarget | temporaryTarget | profileSwitch, runningMode, scene | `Temporary Target`, amend-duration | undeclared | undeclared | Sources | treatment-download |
| AndroidAPS | RunningMode | LoopMode | runningMode | profileSwitch, temporaryTarget, scene | `OpenAPS Offline`, amend-duration | yes | yes | Sources | treatment-download |
| AndroidAPS | Scene (dev-only) | Scene | scene | profileSwitch, temporaryTarget, runningMode | settings | undeclared | undeclared | — | — |
<!-- END GENERATED: state-intent-kinds -->

Undeclared because no source read establishes them: iAPS (no registration exists); end-reason
vocabularies for Trio's override and temporary target and AndroidAPS's profile switch; AndroidAPS
`Sources` values; command vocabularies; where AndroidAPS reports the composed target; a
`scheduled` state for any kind except Loop's override. Loop's pre-meal target is declared with
`wire: null`: it is an intent Loop holds and does not publish.

## 4. Composition, as read from each controller's source

| controller | rule (S1, informational) | where the result is published |
|---|---|---|
| Loop | target = pre-meal if active, else override, else schedule; basal ×f, ISF ×1/f, carb ratio ×1/f from the override only, applied over the history window | devicestatus `override.currentCorrectionRange` and `override.multiplier`, only while an override is active |
| Trio, iAPS | target = temporary target if set, else override target (unless 0 or 6), else profile; override percentage and ISF/CR scope apply regardless; a high or low temporary target also sets `sensitivityRatio` through `halfBasalTarget` | devicestatus `openaps.suggested` ISF, CR, `current_target` and `sensitivityRatio` per loop cycle, not attributed to the intents that produced them (Trio's registration; iAPS has none) |
| AndroidAPS | a temporary target replaces the targets; a profile switch's percentage has already scaled basal, ISF and carb ratio in the effective profile switch; one profile switch, one temporary target, one running mode and one scene at a time | the effective profile switch's `profileJson` (a `Note` with `originalProfileName`) |

No published result names the intents it was computed from (`linkedToIntents: false` in all three
registrations). No two controllers share a rule.

## 5. Effect and motivation (proposed)

`specs/sync/therapy-effect.schema.json` is a draft that separates a temporary effect from why it
was asked for, so that a projection which withholds the motivation is a field selection rather
than a redaction. It is not adopted as a decision; the
[effects and versioning analysis](../nightscout-effects-and-versioning-2026-09-11.md) is its
evidence. A `TherapyEffect` is a span (`startTimestamp`, `endTimestamp` or null while running, an
`id`, a `correlationId` linking the decisions taken under it, a structural `source`, and
`supersededById` when a later effect replaces it) with:

- `effect`: `insulinNeedsScaleFactor`, `basalScaleFactor`, `sensitivityScaleFactor`,
  `carbRatioScaleFactor`, `targetRange`, `timeShiftSeconds`, `smbAllowed`, `maxSmbMinutes`,
  `suspendDelivery`. Absent means unchanged; a factor of 1.0 is not the same as absent.
- `motivation`: an optional closed `classification`, an optional `label` in the person's own words,
  and `decidedBy`.
- `disclosure`: `effect-only`, `effect+classification` or `full`, chosen by the person whose data it
  is.
- `provenance`: the remapping rule from `specs/sync/effect-remapping.yaml` and whether it was lossy.

`disclosure` controls what a record states, not what an observer could infer from it: a recurring
effect is itself a signal. The remapping is lossy for Trio's override, whose wire document carries a
preset name and no effect.

## 6. What is active at a time

How a hub answers "what was active at time t" from the records a controller wrote and the kinds it
declared. Proposed, for the maintainer to confirm (§6.3, ten choices): specified with synthetic cases and a
reference function (`tools/nsschema/active_state.py`), not implemented by any hub. The hub reports
instances and which are active; it never combines them (S1).

### 6.1 Rules

| # | rule |
|---|---|
| A1 | **Per product and kind.** Instances are derived per `(vendor, product)` and kind, from that product's records only. Instances of two products are both reported, even on one shared slot; neither ends the other. |
| A2 | **Identity makes an instance.** A record belongs to a kind's requested layer by its `wire` carrier (collection, `eventType`, discriminator) and, when the kind declares a `requested` carrier, by that carrier too. Records whose `wire.identity` fields are equal are one instance; its content is the last live write the hub received for that identity. Two records with equal identity at the same instant are one instance, never two. |
| A3 | **Start is the record's own time.** An instance starts at its record's `timeField` (`created_at` when none is declared), never at the time in its `_id` or the time the hub received it ([identity I3](identity.md#1-rules)). |
| A4 | **End from the declared duration.** An instance ends at its start plus `durationField` in `durationUnit`. A record carrying the `indefinite` sentinel, or no duration, is open-ended. |
| A5 | **End encodings.** An amendment that shortens an instance (`amend-duration`, `repost-same-created_at`, or `delete-and-repost` under one identity) ends it early, with end reason `cancelled`; one that runs its duration ends `expired`. Under `zero-duration-record`, a zero-duration record ends the latest-starting instance of the kind and product that started strictly before it and is active at its time, with `cancelled`, and is not an instance itself; an instance starting at the marker's own time is not ended. The end reason describes an instance once it has ended; an amendment that shortens an instance is read as an early end, and an edit that only shortens it reads the same. |
| A6 | **Deletion.** A delete removes the write it names: by `_id`, as a delete by id carries no other field, or by identity. A soft delete (a write with `isValid: false`) removes its identity. An instance with no live write left is listed as ended `deletedBeforeStart`, and is never active and ends nothing, when the delete was received before its start; otherwise it is not reported, as a deleted document is not today. A re-post received before the delete of the record it replaces still amends the instance. |
| A7 | **Supersession by start.** Under `supersedes`, an instance ends at the start of the next instance of the same kind and product that starts after it and before its end, with `superseded`. Order is by start, never by arrival, so a backfilled earlier instance is ended by the later one whichever arrived first. Two instances that start at the same instant: the one whose last write was received later supersedes. |
| A8 | **Overlay.** Under `overlay`, a timed instance applies over an open-ended one without ending it; the open-ended one is not active while the timed one is, and is active again when it ends. |
| A9 | **Overlap is reported, not resolved.** For a kind that is `exclusiveWithinSlot` and declares neither `supersedes` nor `overlay`, overlapping instances are all reported active, each marked `overlap`. |
| A10 | **Requested and applied are separate layers.** Wire records matching the requested carrier give the requested layer (A2); `applied` records give the applied layer. Each applied record is in effect from its `timeField` until its own end or the next applied record of the same carrier and product, whichever is first; a record whose `activeField` is false ends what the earlier one put in effect. An applied carrier sampled per cycle (`devicestatus`) gives an applied layer only when it declares `activeField`; without one its values are the controller's composed result (S1) and name no intent, so no instance is reported from them. A request with no applied record is reported as requested only. |
| A11 | **Units are declared, never assumed.** A duration is read only in its declared `durationUnit`. A kind whose carrier has a duration and no unit yields no instances and is reported unreadable; the other kinds still answer. A field's unit is reported from its typed path, and a path with no unit carries none. |
| A12 | **A state version.** A product's state version at a time is `sha256:` over the RFC 8785 canonical JSON of its active rows with each instance's content. It changes when an instance starts, ends or is amended, including an amendment that changes only what the instance says. It versions the hub's record of what the controller reported, not the controller's own state: an approval bound to it is checked by the hub ([commands CM15](commands.md#6-proposals-and-approvals-proposed)), and only the controller's own validation checks its own state (D18). |
| A13 | **Sampled state.** A kind whose `endedEncoding` is `sampled-state` has no instance records: each record carries the current value, which holds from the record's time until the next record of the kind and product. The value reported is the first declared path's. |

### 6.2 What decides each measured disagreement

`LAB-HUB-ACTIVE-STATE` measured cgm-remote-monitor and Nocturne disagreeing on one synthetic record
set ([landscape §5](../nightscout-intent-workflow-landscape-2026-10-09.md#5-how-the-hubs-decide-what-is-active)).
The lab ran each hub's storage and active-state code directly, Nocturne on SQLite, not either hub's
HTTP write path. The rules give one answer for each; it is not always either hub's.

| disagreement (measured) | rule and declaration | case | against the hubs |
|---|---|---|---|
| a temporary target followed by a cancel: cgm-remote-monitor truncates the target; Nocturne records the cancel as an open span of its own | A5, for a kind declaring `zero-duration-record` | `active-state/zero-duration-ends-instance` | cgm-remote-monitor's answer |
| Loop's devicestatus override `duration`: seconds in cgm-remote-monitor, minutes in Nocturne | A3, A10, A11; Loop's applied carrier declares `override.timestamp`, `override.active` and seconds (NightscoutService `StoredDosingDecision.swift:118-136`) | `active-state/applied-duration-in-declared-unit` | cgm-remote-monitor's answer |
| a timed profile switch after a permanent one: cgm-remote-monitor falls back to the permanent profile; Nocturne has none after expiry | A4, A7, A8; AndroidAPS's profile switch declares duration 0 as permanent, `overlay` and `supersedes` (AndroidAPS `AppRepository.kt:408-415`, `ProfileSwitchDao.kt:37`) | `active-state/permanent-profile-switch-returns` | cgm-remote-monitor's answer |
| AndroidAPS `timeshift`: milliseconds in cgm-remote-monitor, hours in Nocturne | A11; the profile switch declares `{path: timeshift, unit: milliseconds}` | `active-state/field-unit-from-declaration` | cgm-remote-monitor's answer |
| two temporary targets at the same millisecond: cgm-remote-monitor keeps the first; Nocturne stores both | A2 for equal identity (the last received write); A7 for different identities | `active-state/equal-identity-same-instant` | neither: cgm-remote-monitor keeps the first write, the rules the last (§6.3 choice 1) |
| an earlier open override backfilled after a later one: Nocturne leaves two open spans | A7 | `active-state/backfill-supersedes-by-start` | cgm-remote-monitor's list answer |

Both hubs ignore a stored `Temporary Override Cancel` (measured), so they agree; that careportal
does not store one is read-derived. The writers that end with a zero-duration record (careportal,
nightguard, iAPS) have no registration, so A5 applies to them once one declares
`zero-duration-record`. AndroidAPS's running mode reads its duration from `originalDuration` in
milliseconds, 0 when permanent, because its wire `duration` is 0 for loop modes and a 10-year
placeholder for an open-ended loop-disabled mode (`RunningModeExtension.kt:25-97`), and it is
resolved like the profile switch (`AppRepository.kt:451-458`).

### 6.3 Choices for the maintainer to confirm

1. The last received write is an instance's content (A2), so a late, stale re-send of an older
   version would win. The alternative, the latest by the record's own time, needs a time that
   changes on amendment, which no carrier declares.
2. A record deleted after its start is not reported (A6), rather than listed as `cancelled`.
3. Two instances starting at the same instant: the later received supersedes (A7).
4. Overlay is checked before supersession, so a timed instance never ends an open-ended one of an
   overlay kind (A8).
5. An applied record holds until the next one or its own end, with no staleness limit (A10): a
   controller that stops uploading leaves its last applied record in effect until that record ends,
   or indefinitely if it is open-ended.
6. A carrier with a duration and no unit is not read (A11), rather than read in a default unit.
7. The state version covers content (A12), so any amendment of an active instance changes it.
8. A zero-duration record ends only an instance already running (A5). A zero-duration record
   written to cancel a target scheduled for later (careportal, nightguard and iAPS cancel before
   start this way) does not cancel it, because nothing on the record says which future instance
   it names.
9. An amendment that shortens an instance is read as an early end (`cancelled`, A5), so an edit
   from 60 to 45 minutes made before the 45th minute reads the same as a cancel.
10. Per-cycle values that name no intent give no applied instance (A10), so Trio's and iAPS's
    applied state is reported as composed values only.

## 7. Commands, as controllers handle them today

| path | request recorded at the hub | acceptance visible | success visible | failure visible |
|---|---|---|---|---|
| careportal or Nocturne → Loop (hub → APNs) | no | no | as the resulting entity | `Note` with free text |
| LoopFollow → Loop or Trio (direct APNs) | no | no | reply to the sender only | `Note` |
| any client → iAPS (`Announcement` treatment) | the request is the treatment | no | no | no |
| careportal or nightguard temporary target → Trio, AndroidAPS | the request is the treatment | no | indistinguishable from enacted | no |
| AAPSClient → AndroidAPS (4.0.0 prereleases, Nightscout `settings`) | yes, signed | `Executing` | `Done/Ok` | `Done/Failed`, `Expired`, `Delivery/Failed` |
| LoopCaregiver "Remote Commands 2" | expects a hub collection neither hub has | — | — | — |

Neither hub forwards a reply channel in the APNs payload it builds, so a hub-routed command cannot
receive a reply. Two hub writes reach no controller: Nocturne's `POST /api/v4/state-spans`, and a
careportal or nightguard temporary target for a controller that does not download treatments.

## 8. Open

- **The active-state choices** (§6.3), for the maintainer to confirm.
- **Undeclared vocabularies** (§3): for `PROPOSAL-REG-CONTROLLERS` to confirm with each controller's
  authors.
- **Effect and motivation** (§5): proposed, not adopted.
- **Treatments a controller downloads and acts on** (S10 `treatment-download`), found by the
  [control-loop analysis](control-loops.md): unlike a command, such an entry has no expiry, no
  destination, no outcome and no record that a controller acted on it (UCA-SYNC-DL-001); an edit
  or delete after the controller acted changes the record and not what was enacted
  (UCA-SYNC-DL-003).
- Not measured: anything about AndroidAPS from data (no AndroidAPS closed-loop site in the
  corpus); whether shipping AndroidAPS sites turn on the `NsClientAccept*` preferences; Trio's
  preset name join; the order in which a Trio override factor and a temporary target's
  `sensitivityRatio` multiply; either hub's HTTP write path and Nocturne on PostgreSQL; xDrip+
  remote and follower paths; the NightscoutKit fork LoopCaregiver uses; behaviour that depends
  on app lifecycle.

## 9. Conformance cases

59 cases: 15 exercise how a kind's declaration is accepted (its meaning and version, a well-known
reference, its acceptance policy, `sameAs` and catalogue mappings), and 44 under
`active-state/` exercise what is active at a time (§6), checked by
`tools/nsschema/test_active_state.py`, whose expectations are written by hand. The registrations' validity is checked by
`tools/nsschema/test_registration_grammar.py` and `make schema-sync-model` (`--check` fails on
drift).

<!-- BEGIN GENERATED: state-intent-cases (tools/nsschema/spec_cases.py) -->
| case | shows | expected | control |
|---|---|---|---|
| `instances/definition-version-conflict` | A kind typed differently at the same version is rejected | 201 partial; version-conflict | `definition-put` |
| `instances/definition-same-meaning` | Non-meaning members may differ at the same version | 201 accepted |  |
| `instances/product-update-version-conflict` | A product update retyping a kind at the same version is rejected for that kind | 200 partial; version-conflict | `product-update-new-version` |
| `instances/product-update-new-version` | A product update with the retyped kind at a new version | 200 accepted |  |
| `instances/definition-wellknown-ref` | A definition references a well-known kind instead of copying it | 201 accepted |  |
| `instances/definition-wellknown-copy-conflicts` | A copy that differs from a referenced catalogue kind conflicts | 201 partial; version-conflict | `definition-wellknown-copy-agrees` |
| `instances/instance-not-a-command-channel` | command-sink only where the kind accepts commands | 201 partial; not-a-command-channel | `instance-create` |
| `quirks/same-as-definition-accepted` | A slot declares the shared slot it means | 201 accepted |  |
| `quirks/same-as-without-slot` | sameAs needs a slot | 201 partial; invalid-element | `same-as-definition-accepted` |
| `quirks/names-alike-do-not-contend` | Slots are never one because their names look alike | 201 accepted |  |
| `quirks/equal-names-unlisted-do-not-contend` | Equal slot names that the shared list does not hold do not contend | 201 accepted |  |
| `quirks/catalogue-mapping-applied` | An older version gets its slot mapping from the catalogue | 200 written |  |
| `quirks/catalogue-mapping-version-outside` | A catalogue mapping applies only to the versions it affects | 200 written |  |
| `quirks/catalogue-mapping-version-unknown` | No mapping when the hub does not know the version | 200 written |  |
| `quirks/same-as-typed-write-declared` | A typed write on a sameAs channel says the channel was declared | 200 written |  |
| `active-state/applied-duration-in-declared-unit` | An applied sample is in effect from its own time, for its duration in the declared unit | rules A3, A10, A11 | `applied-duration-unit-minutes` |
| `active-state/applied-duration-unit-minutes` | The same samples declared in minutes stay in effect for twenty hours | rules A11 |  |
| `active-state/applied-inactive-sample-ends` | A sample saying the intent is not in effect ends the earlier sample | rules A10 | `applied-duration-in-declared-unit` |
| `active-state/backfill-supersedes-by-start` | An earlier instance received later is still ended by the later-starting one | rules A7 | `in-order-same-result` |
| `active-state/delete-after-start-withdraws` | A record deleted after its start and not re-posted is not reported | rules A6 |  |
| `active-state/delete-and-repost-amends` | A delete followed by a re-post of the same identity amends the instance | rules A2, A6 | `delete-after-start-withdraws` |
| `active-state/delete-by-id-withdraws` | A delete that names only the record's _id removes it, as a DELETE by id does | rules A6 | `delete-and-repost-amends` |
| `active-state/deleted-before-start-does-not-supersede` | A record deleted before its start ends nothing | rules A6, A7 | `deleted-before-start` |
| `active-state/deleted-before-start` | A record deleted before its start is listed as ended, deleted before start, and is never active | rules A6 | `scheduled-not-deleted` |
| `active-state/different-identity-same-instant` | Different identities at one instant are two instances; the later received supersedes | rules A2, A7 |  |
| `active-state/different-identity-supersedes` | A different identity is a new instance, which supersedes the earlier one at its start | rules A2, A7 |  |
| `active-state/equal-identity-same-instant` | Two records with equal identity at one instant are one instance, as last received | rules A2 | `different-identity-same-instant` |
| `active-state/equal-start-last-write-wins` | At an equal start, the instance whose last write was received later supersedes | rules A7 | `different-identity-same-instant` |
| `active-state/exclusive-overlap-reported` | Overlapping instances of an exclusive kind that does not supersede are both reported, as an overlap | rules A9 | `exclusive-supersedes` |
| `active-state/exclusive-supersedes` | The same records under a superseding kind: one instance | rules A7 |  |
| `active-state/field-unit-from-declaration` | A field's unit is reported from its typed path | rules A11 | `field-unit-undeclared` |
| `active-state/field-unit-undeclared` | A path with no declared unit carries none | rules A11 |  |
| `active-state/forced-mode-is-applied-not-requested` | A constraint-forced mode is in the applied layer only, when the kind declares a requested carrier | rules A10 | `forced-mode-without-requested-carrier` |
| `active-state/forced-mode-without-requested-carrier` | Without a requested carrier, the forced record is also taken as a request | rules A10 |  |
| `active-state/in-order-same-result` | Received in time order, the same instances | rules A7 |  |
| `active-state/marker-at-next-start` | An end marker at the instant the next target starts ends only the earlier one | rules A5 | `zero-duration-ends-instance` |
| `active-state/no-end-marker` | Without an end marker the instance runs its duration | rules A5 |  |
| `active-state/overlay-returns-to-open-ended` | A timed instance applies over an open-ended one, which applies again when it ends | rules A8 | `supersedes-without-overlay` |
| `active-state/permanent-after-temporary-supersedes` | A permanent switch that starts during a temporary one supersedes it | rules A7, A8 |  |
| `active-state/permanent-profile-switch-returns` | A permanent profile switch (duration 0) stays active and applies again after a temporary one | rules A4, A8 | `permanent-after-temporary-supersedes` |
| `active-state/products-never-supersede-each-other` | Instances of two products on one slot are both reported; neither ends the other | rules A1 | `same-product-supersedes` |
| `active-state/repost-before-delete` | A re-post received before the delete of the old record, and a delete that names only _id | rules A2, A6 | `delete-and-repost-amends` |
| `active-state/repost-same-identity-amends` | A re-post with the same identity amends the instance it names | rules A2, A5 | `different-identity-supersedes` |
| `active-state/requested-and-applied` | With the applied record, both layers are reported | rules A10 |  |
| `active-state/requested-without-applied` | A request with no applied record is reported as requested only | rules A10 | `requested-and-applied` |
| `active-state/running-mode-open-ended` | The same mode, not shortened, stays active | rules A4 |  |
| `active-state/running-mode-original-duration` | A loop-disabled mode shortened in originalDuration ends, whatever its placeholder wire duration | rules A4, A5 | `running-mode-open-ended` |
| `active-state/same-product-supersedes` | The same records from one product: the later supersedes | rules A7 |  |
| `active-state/sampled-state-latest-value` | A sampled-state kind is the latest sample's value, each sample holding until the next | rules A13 |  |
| `active-state/scheduled-not-deleted` | The same scheduled record, not deleted, is active from its start | rules A2 |  |
| `active-state/soft-delete-before-start` | A soft delete before the start is a deletion before start | rules A6 | `soft-delete-not-applied` |
| `active-state/soft-delete-not-applied` | The same scheduled target, not deleted, is active | rules A6 |  |
| `active-state/state-version-amended` | An amendment to an active instance changes the state version | rules A12 |  |
| `active-state/state-version-content-changed` | An amendment that changes only what an active instance says changes the state version | rules A12 | `state-version-tracks-active-set` |
| `active-state/state-version-tracks-active-set` | The state version is stable while the active set is, and changes when it changes | rules A12 | `state-version-amended` |
| `active-state/supersedes-without-overlay` | Without overlay, a superseding kind ends the open-ended instance for good | rules A7, A8 |  |
| `active-state/unattributed-applied-is-not-an-instance` | Per-cycle values that name no intent are not an applied instance | rules A10 | `applied-duration-in-declared-unit` |
| `active-state/undeclared-unit-kind-unreadable` | A kind whose duration has no declared unit yields nothing and is reported unreadable; other kinds still answer | rules A11 | `no-end-marker` |
| `active-state/zero-duration-ends-instance` | A zero-duration record ends the instance active at its time and is not an instance | rules A5 | `no-end-marker` |
<!-- END GENERATED: state-intent-cases -->
