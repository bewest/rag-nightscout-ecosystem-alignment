# State and intent (L3)

*Contributor-facing. Living specification, current at `main` `92a7d31b` (2026-10-18). Layer L3 of
the [platform index](../README.md); terms are in the [glossary](glossary.md). The grammar members
named here are part of the [registration specification](registration.md) §3; how a hub accepts
them is there too. Decisions: [D18](../../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#261-d18--two-tier-controller-registration)
(the hub observes, the controller composes) and the maintainer's 2026-10-18 decision on agent
initiators ([execution plan §2.6.3](../../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#263-d20--version-scoped-quirks-and-the-two-id-rule-maintainer-2026-10-16)
row 17). Queue: `SPEC-STATE-INTENT`.*

A controller manages *intent*: a preset is activated, several intents run at once and combine, the
controller applies something that may differ from what was asked, and the intent ends for a
reason. Nightscout's collections manage *entities*. This page says how a controller declares its
intent model, so that a reader can tell what was requested, what was applied, who started it and
why it ended, and what the hub may and may not conclude from the records.

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
| S11 | **The controller's command contract.** `commands[]` declares each path by which commands reach the controller: `transport` (`apns`, `sms`, `nightscout-settings`, `nightscout-treatment`, or `{value: other, controllerTerm}`), `availability` (the AndroidAPS `nightscout-settings` path is dev-only), `hubInPath` (`no`, `optional`, `yes`), `authorisation`, `expiry`, `acknowledgement` (`states`, `replyChannel`, `correlationId`, `failureRecord`) and `evidence`. The hub's own command API and the proposal record in front of a command are `SPEC-REG-COMMANDS`. |
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

## 6. What is active at a time (not yet specified)

No rule says how a hub answers "what was active at time t" from the records. The two hubs
disagree, measured by `LAB-HUB-ACTIVE-STATE` on one synthetic record set
([landscape §5](../nightscout-intent-workflow-landscape-2026-10-09.md#5-how-the-hubs-decide-what-is-active)).
For each disagreement, the declaration that already carries the answer, and what is missing:

| disagreement (measured) | declaration that settles it | missing |
|---|---|---|
| a temporary target followed by a cancel: cgm-remote-monitor truncates the target; Nocturne records the cancel as a separate open span | `wire.endedEncoding`: `repost-same-created_at` for Trio, `amend-duration` for AndroidAPS | the rule that an end encoding ends the instance it names and is not an instance; and a declaration for the writers that end with a zero-duration record (careportal, nightguard, iAPS), none of which has a registration (landscape §4) |
| Loop's devicestatus override `duration`: seconds in cgm-remote-monitor, minutes in Nocturne | Loop's `applied` carrier: `durationField: override.duration`, `durationUnit: seconds` (seconds remaining, read from NightscoutService and NightscoutKit) | the rule that a reader takes a duration's unit from the carrier's declaration |
| a timed profile switch after a permanent one: cgm-remote-monitor falls back to the permanent profile, Nocturne has no profile after expiry | `overlay` | AndroidAPS's `profileSwitch` declares no `overlay` (its `runningMode` does); whether AndroidAPS returns to the earlier profile is not established here |
| AndroidAPS `timeshift`: milliseconds in cgm-remote-monitor, hours in Nocturne | the profile switch `wire` path `{path: timeshift, unit: milliseconds}`, and `originalTimeshift` in milliseconds on the effective profile switch (read from AndroidAPS) | the rule that a reader takes a field's unit from the typed path |
| two temporary targets at the same millisecond: cgm-remote-monitor keeps the first; Nocturne stores both, so list reads agree and latest-span reads disagree once the first ends | `wire.identity`: `created_at` + `eventType` for Trio, `identifier` for AndroidAPS | the rule that equal identity is one instance amended, not two |
| an earlier open override backfilled after a later one: Nocturne leaves two open spans | `supersedes` | the rule that supersession orders by instance start, not by arrival |

Both hubs ignore a stored `Temporary Override Cancel` (measured), so they agree; that careportal does not store one is read-derived.

The lab ran each hub's storage and active-state code directly on SQLite for Nocturne, not either
hub's HTTP write path; on PostgreSQL the same-millisecond tie may break differently.

The rule is `SPEC-ACTIVE-STATE`. It also has to give the therapy state a version an approval can
be bound to: D19's etags version the registration, not the controller's active intents, so nothing
yet tells an approver that the state an agent read is still the state the controller holds
(`SPEC-REG-COMMANDS`).

## 7. Commands, as controllers handle them today

| path | request recorded at the hub | acceptance visible | success visible | failure visible |
|---|---|---|---|---|
| careportal or Nocturne → Loop (hub → APNs) | no | no | as the resulting entity | `Note` with free text |
| LoopFollow → Loop or Trio (direct APNs) | no | no | reply to the sender only | `Note` |
| any client → iAPS (`Announcement` treatment) | the request is the treatment | no | no | no |
| careportal or nightguard temporary target → Trio, AndroidAPS | the request is the treatment | no | indistinguishable from enacted | no |
| AAPSClient → AndroidAPS (dev only, Nightscout `settings`) | yes, signed | `Executing` | `Done/Ok` | `Done/Failed`, `Expired`, `Delivery/Failed` |
| LoopCaregiver "Remote Commands 2" | expects a hub collection neither hub has | — | — | — |

Neither hub forwards a reply channel in the APNs payload it builds, so a hub-routed command cannot
receive a reply. Two hub writes reach no controller: Nocturne's `POST /api/v4/state-spans`, and a
careportal or nightguard temporary target for a controller that does not download treatments.

## 8. Open

- **The active-state rule** and a therapy-state version (§6): `SPEC-ACTIVE-STATE`.
- **Undeclared vocabularies** (§3): for `PROPOSAL-REG-CONTROLLERS` to confirm with each controller's
  authors.
- **Effect and motivation** (§5): proposed, not adopted.
- Not measured: anything about AndroidAPS from data (no AndroidAPS closed-loop site in the
  corpus); whether shipping AndroidAPS sites turn on the `NsClientAccept*` preferences; Trio's
  preset name join; the order in which a Trio override factor and a temporary target's
  `sensitivityRatio` multiply; either hub's HTTP write path and Nocturne on PostgreSQL; xDrip+
  remote and follower paths; the NightscoutKit fork LoopCaregiver uses; behaviour that depends
  on app lifecycle.

## 9. Conformance cases

15 cases exercise how a kind's declaration is accepted: its meaning and version, a well-known
reference, its acceptance policy, `sameAs` and catalogue mappings. The meaning of the declarations
themselves (§6) has no case yet. The registrations' validity is checked by
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
<!-- END GENERATED: state-intent-cases -->
