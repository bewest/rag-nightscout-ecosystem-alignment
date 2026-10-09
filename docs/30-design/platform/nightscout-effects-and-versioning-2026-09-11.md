# Temporary effects, privacy-preserving projection, and which version this is

*Contributor-facing.* **Snapshot — describes 2026-09-11. Status: current as analysis; not adopted as a decision.** Current decisions: [execution plan §1](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#1-decisions). **Corrected in place 2026-10-09** to distinct-document counts (§2.1), and against source ([intent and workflow across the landscape](./nightscout-intent-workflow-landscape-2026-10-09.md) §11): the AAPS `percentage` semantics (§2.2, §3.3, §6), the Trio document count and the meaning of its `notes` (TL;DR, §2.2, §3.3), and the Trio recoverability question (§6).

Date: 2026-09-11. Companion to
[the hub-and-spoke sync design](./nightscout-hub-sync-architecture-2026-09-11.md).

**Nothing here is a proposal to merge. The privacy argument in §3 is a
technical sketch; what may lawfully be shared, and on what consent, needs
review by someone qualified for the jurisdictions involved.**

---

## TL;DR — the six questions

| Question | Answer |
|---|---|
| Does the registration solve the MQTT+protobuf "which schemas do I publish" problem? | **Yes, and that is most of what a registration is for.** A registration *is* a schema announcement; a broker or a batch endpoint is then a transport choice, not a schema problem |
| Can legacy traffic keep working while newer controllers sync idiomatically? | **Yes**, because the split is by *contract*, not by document. v1 writers keep writing v1 documents into the same collections |
| Can effects be represented only as their impact on dosing, not their motivation? | **Yes, and the corpus is already 86% of the way there.** 86.1% of temporary-effect treatments carry both halves separably | §2 |
| Can AAPS, Trio and Loop concepts be remapped? | **Yes, with one documented lossy case** — and it is the finding: Trio publishes a preset name and no effect at all | §2.2 |
| Does Nocturne already implement this? | **It has the container, not the separation.** `StateSpan` is the right shape; `BuildOverrideMetadata` puts `name` and `multiplier` side by side in one untyped dictionary | §4 |
| Is this v4, v5, or an extension to v4? | **An extension to v4, and the sync contract is a profile over it, not a document generation.** A v5 would be the fourth layer nobody adopts | §5 |

**The sharpest finding.** Trio uploads an override as
`{eventType: "Exercise", duration, notes}` — 399 distinct documents in the
corpus, one site — and its `NightscoutExercise` model carries no percentage, no
target, no multiplier. `eventType: "Exercise"` is a fixed carrier for every
override whatever its purpose, and `notes` is the preset name the user chose.
The record keeps that name and discards what the loop actually did. **It can be neither replayed nor usefully anonymised**:
redacting it leaves nothing, and keeping it reveals only the sensitive half.

---

## 1. Why the registration answers the protobuf question

An MQTT-plus-protobuf transport is efficient and stalls on one thing: both
ends have to agree, in advance, which message types exist and what is in
them. Discovering that from traffic is impossible, and hard-coding it means
a schema change is a coordinated release.

A registration is that agreement, made explicit and versioned. A controller
declares the documents it writes, the primitives they decompose to, the
state machine it exposes and the inputs it can supply
(`specs/sync/controller-state-model.schema.json`). Once the hub holds that,
the transport becomes a choice rather than a constraint:

* **batched HTTP** — one cursor request in, one batch out (§2 of the sync
  design measured the saving at 2.5–10×)
* **MQTT with protobuf** — the registration is the `.proto` selection; the
  topic structure follows the registered documents; the hub can generate the
  descriptor set because it already generates JSON Schema, zod, mongoose and
  Arrow from one model
* **anything later** — the registration outlives the wire format

The same generation machinery that emits validators today would emit the
protobuf descriptors, from the same source, with the same drift check. That
is worth more than the wire saving: **the reason the earlier MQTT attempt
needed to know which schemas to publish is that nothing published them.**

## 2. Effects, separated from motivation

### 2.1 The corpus is already most of the way there

`make schema-effects` classifies every temporary-effect record by whether it
carries the **effect** (multiplier, target, duration — what a replay needs)
and the **motivation** (preset name, reason, note — why it was asked for):

| | Records | effect+motivation | motivation-only | effect-only |
|---|---|---|---|---|
| Temporary-effect treatments | 2,865 | **86.1%** | 13.9% | — |
| Active overrides in devicestatus | 55,938 | **76.5%** | 19.5% | 3.9% |

Counts are distinct documents across the corpus's two overlapping snapshots (`make schema-effects`, corrected 2026-10-09).

**86.1% are already separable**, because Loop writes
`insulinNeedsScaleFactor` and `correctionRange` alongside `reason`. A
privacy-preserving projection of those records is a field selection, not a
redaction pass — which matters, because a field selection can be enforced in
storage while a redaction pass has to be remembered.

The two requirements point the same way, which is the useful part: **replay
needs the effect, privacy needs the effect without the motivation**, and a
representation that separates them serves both.

### 2.2 The remapping, and where it is lossy

`specs/sync/effect-remapping.yaml` maps each controller's concept onto
`TherapyEffect`. Five rules, one lossy:

| Rule | Controller | Lossy | Note |
|---|---|---|---|
| `MAP-LOOP-OVERRIDE` | Loop | no | 2,428 documents, 9 sites, both halves present |
| `MAP-LOOP-DEVICESTATUS-OVERRIDE` | Loop | no | 55,938 active overrides |
| `MAP-AAPS-TEMPTARGET` | AAPS | no | the only **closed** motivation vocabulary in the ecosystem |
| `MAP-AAPS-PROFILESWITCH` | AAPS | no | `percentage` is an insulin-needs scale: basal × p/100, ISF and IC × 100/p (`ProfileSealed.convertToNonCustomizedProfile`, pinned by `ProfileSealedTest`); under Dynamic ISF it enters the ISF formula instead |
| `MAP-TRIO-EXERCISE` | Trio | **yes** | no effect on the wire at all; `notes` is the preset name |

**Why the factors stay per component.** An AAPS profile-switch `percentage`
and a Loop override multiplier are the same kind of quantity: both scale basal
by the factor and ISF and carb ratio by its inverse. Trio is the case that
needs separate components — its override applies the percentage to basal and,
by its `isfAndCr`, `isf` and `cr` flags, to ISF and CR together, to one of
them, or to neither. So `TherapyEffect` carries `basalScaleFactor` *and*
`insulinNeedsScaleFactor` rather than one normalised factor, and a mapping
states which components a controller scaled. Collapsing them would silently
misprice a replayed dose — the kind of error that validates cleanly and is
wrong.

**AAPS already does the right thing on motivation.** `NSTemporaryTarget.reason`
is a closed enum — `Custom`, `Hypo`, `Activity`, `Eating Soon`,
`Automation`, `Wear`. That maps straight onto a `classification` with no
free text, which is exactly the design the other two should copy: a closed
vocabulary can be *coarsened*, free text can only be *withheld*.

### 2.3 What the model looks like

`specs/sync/therapy-effect.schema.json`. A time-ranged span with three
parts:

* **`effect`** — scale factors, target range, time shift, SMB permission,
  suspension. Every member optional; absent means unchanged, and a factor of
  1.0 is deliberately *not* the same as absent.
* **`motivation`** — an optional object: a closed `classification`, an
  optional free-text `label`, and who decided. Never required.
* **`disclosure`** — `effect-only`, `effect+classification`, or `full`,
  chosen by the person whose data it is.

A cycle-aware controller, or a delegated agent combining a calendar, would
publish `{effect: {sensitivityScaleFactor: 1.15}, disclosure: "effect-only"}`
— "insulin needs were scaled for six hours" with no statement of why. The
dose is fully replayable; the reason is not disclosed. That is the
"sensitivity changed instead of menstrual cycle" projection, and it falls
out of the field layout rather than needing a scrubber.

**This does not make the effect non-identifying.** A recurring monthly
sensitivity change is itself a signal. `disclosure` controls what the record
*states*, not what a determined observer could *infer*, and no schema choice
changes that.

## 3. What each project would have to do

### 3.1 Nocturne — has the container, not the separation

| | Status |
|---|---|
| Time-ranged span with category, state, source | **`StateSpan`**, already there |
| Supersession between sources | **`SupersededById`, `CanonicalId`, `Sources`**, already there |
| Categories for the AID state machine | `PumpMode`, `Override`, `TemporaryTarget`, `ProfileState`, `DataExclusion`, `Activity` — already there |
| Typed effect | **missing** |
| Effect separated from motivation | **missing** |
| Derived state rather than a constant | **missing** |

`DeviceStatusDecomposer.BuildOverrideMetadata` puts `name`, `multiplier`,
`currentCorrectionRange.minValue` and `currentCorrectionRange.maxValue` into
**one untyped `Dictionary<string, object>`**, and `BuildOverrideSpan` sets
`State = OverrideState.Custom` unconditionally. So the effect and the
motivation arrive in the same bag, addressed by string key, with no way to
project one without the other and no schema to validate either.

The change is contained: type the metadata as a `TherapyEffect`, move the
name into `motivation`, derive `State` from the effect. `StateSpan` itself
does not change.

### 3.2 cgm-remote-monitor

Nothing is required for the *legacy* path — that is the point of §5. To
participate:

* accept and store `TherapyEffect` as a resource (or as a typed
  `devicestatus`/`treatments` extension under the registered contract)
* enforce `disclosure` as a storage predicate, not an application filter —
  the multitenancy work measured RLS at 0.3–0.6 ms and showed it is
  fail-closed, which is the property a disclosure level needs
* expose effect spans in the API the registration derives

### 3.3 The controllers

| | Change | Value |
|---|---|---|
| **Trio** | publish the effect, not only the preset name | **highest in this document.** 399 records in the corpus carry the name and nothing else |
| **Loop** | adopt a closed `classification` beside the free-text preset name | makes coarsening possible; the name alone cannot be published safely |
| **AAPS** | publish the effective scale per component with the profile switch | removes the need for a consumer to know the `percentage` and Dynamic ISF rules |
| **All three** | publish `smbAllowed` with the effect | closes a measured dosing input (`microBolusAllowed`) that no controller records |

## 4. Does this need new out-of-band collections?

Mostly not, and that is the argument for doing it this way. A menstrual-cycle
model, an exercise detector or a calendar agent does not need a new
collection to influence dosing — it needs to publish a `TherapyEffect`. The
raw signal can stay wherever it lives, under whatever consent applies to it,
and only the dosing-relevant projection enters the record.

Where a raw physiological stream genuinely should be stored, `activity` is
already the pattern: one collection, a `type` discriminator, per-type fields
(xDrip+ ships `{type: "hr-bpm", bpm}` and `{type: "steps-total", steps}`
today).

The separation is the point. **`activity` carries observations; a
`TherapyEffect` carries a decision's consequences.** Keeping a heart-rate
series and "insulin needs were scaled 1.15× for six hours" in different
resources is what lets the second be shared when the first cannot.

## 5. Which version is this

**An extension to v4, with the sync contract as a profile over it. Not v5.**

The reasoning, in the order it matters:

1. **A v5 would be the fourth layer nobody adopts.** Loop and Trio are still
   on v1 with no watermark and no delta endpoint; AAPS is the only client
   using v3's sync machinery. The ecosystem has not finished adopting v3.
   Adding a generation would create a fourth surface to document, test and
   support, with the same adoption problem plus one.
2. **`TherapyEffect` is a v4-shaped thing.** It is a typed primitive with an
   identity, a correlation id, a time span and supersession — the same
   family as `StateSpan`, `Bolus` and `TempBasal`. It belongs in the
   primitive catalogue, not in a new document generation.
3. **The sync contract is a transport concern, not a document generation.**
   Registration, cursor and batch endpoints do not change what a document
   *is*. Versioning them together is what produced three partly-adopted
   generations; keeping them separate means the contract can iterate while
   the model stays still, and a controller can adopt the contract without
   adopting new documents, or the reverse.
4. **cgm-remote-monitor adopting v4 typed schemas does not make it v5.** It
   makes v4 a shared model with two implementations, which is the outcome
   worth wanting. The typed-schema work in this repo generates JSON Schema,
   zod, mongoose and Arrow from one model precisely so that a second
   implementation is a generation target rather than a reimplementation.

So the naming that fits what exists:

* **v1** — the legacy documents. Frozen, supported, never retired.
* **v3** — the same documents plus the metadata envelope and cursor sync.
  Already built; the work is adoption, not extension.
* **v4** — typed primitives, of which `TherapyEffect` becomes one and
  `StateSpan` already is one. Shared between Nocturne and
  cgm-remote-monitor rather than owned by either.
* **the sync profile** — registration, cursor, batch, query bounds.
  Versioned on its own (`nightscout.dev/sync/v1`), and deliberately not
  called v5.

## 6. What is not measured

* **The scale-factor semantics under Dynamic ISF and AutoISF.** The plain
  AAPS `percentage` maths is pinned by an AAPS unit test; how it combines with
  Dynamic ISF and AutoISF is read from source only.
* **Trio's override effect is partly recoverable, by join only.** Trio does not
  express an override through a profile switch or temp target. The applied
  ISF, CR, target and `sensitivityRatio` are in
  `devicestatus.openaps.suggested/enacted` on every cycle, after every
  adjustment and unattributed; preset percentage and target are in the
  `profile` document's `overridePresets`, joinable by name, with no Trio
  `profile` document in the corpus to test the join.
* **`disclosure` enforcement.** Nothing implements it. RLS was measured for
  tenant isolation, not for field-level projection, and the two are not the
  same query.
* **AAPS from data**, still — no closed-loop AAPS site in the corpus, so
  `MAP-AAPS-TEMPTARGET` and `MAP-AAPS-PROFILESWITCH` are source-derived.
* **Re-identification risk of effect-only records.** §2.3 asserts that a
  recurring effect is itself a signal. Quantifying that is a research
  question this repo has not attempted.

## 7. References

* `make schema-effects` → `reports/schema-census/effects.json`
* `specs/sync/therapy-effect.schema.json`, `specs/sync/effect-remapping.yaml`
* `specs/sync/controller-state-model.schema.json`, `specs/sync/registrations/`
* Nocturne `Core.Models/StateSpan.cs`, `API/Services/V4/DeviceStatusDecomposer.cs` (`BuildOverrideSpan`, `BuildOverrideMetadata`)
* Trio `Sources/Models/NightscoutExercise.swift`, `Model/Helper/OverrideStored+helper.swift`
* AAPS `core/nssdk/.../localmodel/treatment/NSTemporaryTarget.kt`
* [Hub-and-spoke sync design](./nightscout-hub-sync-architecture-2026-09-11.md) §2 (wire cost), §5 (StateSpan)
* [Settings, extensibility and delegation](../tenancy/nightscout-configuration-and-delegation-2026-09-10.md) §5 (delegation requirements)
