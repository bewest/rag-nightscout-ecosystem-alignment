# `devicestatus` and `profile`: what survives, what is lost, and what was never written

Date: 2026-09-10. Status: draft for maintainer discussion. Third in a series
with
[Typed schemas for Nightscout](./nightscout-typed-schema-evidence-2026-09-10.md)
and
[Extending the document model](./nightscout-extensibility-models-2026-09-10.md).

**Nothing here is a proposal to merge. The deliverable is evidence.**

---

## TL;DR

`entries` and `treatments` are nearly solved problems — a typed model
retains 18 of 19 and 41 of 41 observed paths respectively. `devicestatus`
is not, and the reasons are structural rather than incidental.

| # | Finding | Evidence |
|---|---|---|
| 1 | **Nocturne's typed model silently drops 56 of 166 observed `devicestatus` paths.** Nine are on 10 of 11 sites. `entries` loses 1 of 19, `profile` 1 of 66, `treatments` 0 of 41 | §2 |
| 2 | **The reason is one line of design: `[JsonExtensionData]` is on `DeviceStatus` but on none of its nested classes.** An unknown key at the top level is captured; the same key one level down is gone. A document model nested three deep needs an extension point at every level, or at none | §2.1 |
| 3 | **Loop's automatic dose recommendation — the dosing decision itself — is dropped.** NightscoutKit writes `bolusVolume` and `tempBasalAdjustment`; Nocturne's model declares `bolus` and `tempBasal`. 26% of device statuses, 10 of 11 sites | §2.2 |
| 4 | **The majority pump-status shape is dropped too.** `pump.bolusing`, `pump.suspended`, `pump.pumpID`, `pump.secondsFromGMT` — 85.1% of device statuses, 10 sites — because the typed model reads only the nested `pump.status.*` form | §2.3 |
| 5 | **Of 40 real dosing inputs, 20 are recorded, 9 derivable, 3 partial and 8 absent.** The absent set includes `microBolusAllowed`, `flatBGsDetected` and oref0's unannounced-meal detection state | §3 |
| 6 | **Dosing *safety limits* are recorded by Loop and by nobody else.** `maxBasal`, `suspendThreshold` and `dosingStrategy` reach Nightscout only as `profile.loopSettings.*`. No oref0 derivative records `maxIob` anywhere at all | §3.2 |
| 7 | **The `activity` collection is already a polymorphic, `type`-discriminated resource in production** — xDrip+ posts `{type: "hr-bpm", bpm}` and `{type: "steps-total", steps}` to `/api/v1/activity`. Our own `aid-heartrate-2025.yaml` proposes a *separate* `/heartrate` collection, which conflicts with the shipped pattern | §4 |

**The through-line.** Every one of findings 1–4 is a *nested* field being
lost. `treatments` loses nothing because it is flat and carries an extension
bag; `devicestatus` loses a third of its surface because it is a tree whose
branches each need their own contract. That is the concrete argument for
composing `devicestatus` out of separately-typed resources rather than
treating it as one document with one escape hatch — and §4 shows the
ecosystem already does exactly that for `activity`, discriminated by `type`.

---

## 1. Method

`make schema-nocturne` parses `Nocturne.Core.Models` for its wire contract —
every class, its `[JsonPropertyName]` members and declared types, and whether
it carries `[JsonExtensionData]` — then resolves every census path through
the resulting type graph. A path whose segment is undeclared in a class with
no extension data is **dropped**: not rejected, not logged, gone.

Nocturne is used as the yardstick because it is the most complete typed model
of this corpus in existence (`attribution.json`: 179 of 247 field names, 162
of them with explicit serialization attributes — more than any other
project). A gap here is not a criticism of Nocturne; it is the best available
measurement of how hard this document is to type at all.

Two parser bugs were found and fixed before any of this was trusted, both
verified against hand-reads of the C#: properties with expression bodies
(`get => _x ?? Fallback()`) were reported as undeclared, which wrongly
condemned `Entry.date` and `Profile.srvModified` — the fallback-chain style
used for exactly the most interesting fields; and four duplicated class names
were overwriting rather than merging. Regression tests pin both.

`make schema-dosing` checks a hand-authored map
(`specs/nsschema/dosing-input-sources.yaml`) against the census: a source
claimed to carry an input must exist in the corpus, and an input claimed
absent must not. All 40 claims currently hold.

## 2. What a typed model loses

| Collection | Paths | Retained | Captured by an extension bag | **Dropped** |
|---|---|---|---|---|
| `entries` | 19 | 18 | 0 | **1** |
| `treatments` | 41 | 32 | 9 | **0** |
| `profile` | 66 | 65 | 0 | **1** |
| `devicestatus` | 166 | 110 | 0 | **56** |

`entries` loses only single-site `glucose`; `profile` only a rare
`store.{}.startDate`. `treatments` loses nothing, because `Treatment` carries
`[JsonExtensionData]` and is flat enough for it to work.

### 2.1 Why `devicestatus` is different

`[JsonExtensionData]` appears on exactly three classes in the whole model:
`DeviceStatus`, `Treatment` and `Activity`. `PumpStatus`, `UploaderStatus`,
`LoopStatus`, `OpenApsStatus` and `PumpBattery` have none.

So `devicestatus.somethingNew` survives, and `devicestatus.pump.somethingNew`
does not. The escape hatch is at the root of a tree whose leaves are where
the vendors actually write.

Of the 56 dropped paths, **9 are cross-site** (3 or more sites) and 47 are
the single-site `openaps.*` subtree — which is not a reason to dismiss them
(§3 is about exactly those) but does say the loss is concentrated.

### 2.2 The dosing decision itself

| Path | Documents | Sites |
|---|---|---|
| `loop.automaticDoseRecommendation.bolusVolume` | 26.1% | 10 |
| `loop.automaticDoseRecommendation.tempBasalAdjustment` | 6.1% | 10 |
| `loop.automaticDoseRecommendation.tempBasalAdjustment.rate` | 6.1% | 10 |
| `loop.automaticDoseRecommendation.tempBasalAdjustment.duration` | 6.1% | 10 |

`NightscoutKit/Sources/NightscoutKit/Models/AutomaticDoseRecommendation.swift`
writes `rval["bolusVolume"]` and `rval["tempBasalAdjustment"]`. Nocturne's
`LoopAutomaticDoseRecommendation` declares `bolus` and `tempBasal`. The names
never matched, and because the class has no extension data, the recommendation
is dropped rather than preserved as an unknown key.

This is worth reporting upstream on its own: it is the automatic dose Loop
decided on, lost on ingest, on nearly every Loop site.

### 2.3 The majority pump shape

`pump.bolusing`, `pump.suspended`, `pump.pumpID` and `pump.secondsFromGMT`
each appear in **85.1% of device statuses on 10 of 11 sites** and are all
dropped, because `PumpSnapshot` reads `ds.Pump.Status?.Bolusing` — the nested
form, written by one site.

This is `QUIRK-DEVICESTATUS-001` (flat vs. nested pump status) with its
consequence measured: the fork is not merely a reader inconvenience, it
causes the majority shape to be discarded by the most complete typed model
available. `pump.battery.string` and `pump.battery.display` go the same way,
against a declared `battery.status` and `battery.voltage` that the corpus
never contains.

## 3. Can a dosing decision be replayed from Nightscout?

The input set is evidence-based: the union of `input.*` paths across the 385
replay vectors in `conformance/`, captured from real AAPS and Loop runs.

| | Count | Meaning |
|---|---|---|
| `recorded` | 20 | a Nightscout path holds the value |
| `derivable` | 9 | reconstructible from stored history, by recomputing what the controller already knew |
| `partial` | 3 | recorded by Loop only |
| `absent` | 8 | nothing carries it |

### 3.1 What is absent

| Input | What it is |
|---|---|
| `microBolusAllowed` | whether SMB was permitted on this run. Not inferable after the fact: a run that allowed SMB and chose not to dose is indistinguishable from one that forbade it |
| `flatBGsDetected` | oref0's flat-CGM guard |
| `mealData.slopeFromMaxDeviation` | unannounced-meal detection state |
| `mealData.slopeFromMinDeviation` | the same |
| `mealData.mealCOB` | meal-attributed COB, distinct from total COB |
| `iob.bolusSnooze`, `iob.iobWithZeroTemp.bolussnooze` | bolus-snooze IOB |
| `profile.maxIob` | the IOB safety ceiling |

The `derivable` nine are a subtler problem than the absent eight. Recomputing
`shortAvgDelta` from the stored `sgv` series gives *a* value, not necessarily
*the* value the controller used — it saw a different window, with different
de-duplication and different noise handling. A replay built on derived inputs
tests the replayer as much as the algorithm.

### 3.2 Safety limits are a Loop-only record

| Input | Loop | Trio | AndroidAPS |
|---|---|---|---|
| `profile.maxBasal` | `loopSettings.maximumBasalRatePerHour` | — | — |
| `profile.suspendThreshold` | `loopSettings.minimumBGGuard` | — | — |
| `profile.dosingStrategy` | `loopSettings.dosingStrategy` | — | — |
| `profile.maxIob` | — | — | — |

Trio is separated from Loop here deliberately. Trio is LoopKit-derived and
holds `maximumBasalRatePerHour` in its vendored `SettingsStore.swift`, so it
is tempting to assume it uploads it. It does not: Trio's
`NightscoutProfileStore` declares `store`, `overridePresets`,
`bundleIdentifier`, `deviceToken`, `teamID` and `expirationDate`, and no
`loopSettings` and no limits.

The corpus cannot confirm this on its own and is worth showing as a trap.
`loopSettings.maximumBasalRatePerHour` appears on the Trio site in 100% of
its profile documents — but those documents carry `loopSettings` and *not*
Trio's own top-level `teamID`/`bundleIdentifier` markers, so they were
written by Loop before that site switched. Reading the corpus alone would
have credited Trio with recording limits it never writes. `openaps.suggested.threshold`
is present for oref0 derivatives but is the *computed* threshold, not the
configured one.

This reframes `loopSettings` considerably. In the schema work it looked like
a vendor subtree that had been flattened into a shared document — 26
undeclared paths, the attribute-flattening camp of the `x-aid-extensions`
proposal. It is also **the only place in the Nightscout data model where an
AID system's dosing safety limits are recorded at all.**

The implication cuts both ways. Loop's flattening is what makes those limits
recoverable, so relocating them into an unstructured extension bag would make
them *less* accessible, not more. And no oref0 derivative records its limits
anywhere, so for AAPS and Trio data the question "was this dose within the
configured ceiling?" cannot be answered from Nightscout at all.

## 4. Activity, steps and heart rate

The variability here is lower than expected, because one client already set a
de facto standard and the server already supports it.

**What ships today.** xDrip+ (`NightscoutUploader.java`) posts to
`/api/v1/activity`:

```json
{"type": "hr-bpm",       "timeStamp": 1743465600000, "created_at": "…", "bpm": 72, "accuracy": 2}
{"type": "steps-total",  "timeStamp": 1743465600000, "created_at": "…", "steps": 4213}
```

cgm-remote-monitor has the collection (`MONGO_ACTIVITY_COLLECTION`, an
`api:activity:create` permission) and its `dataloader` reads `element.steps`.
Nocturne models `Activity` with 18 typed fields **and** `[JsonExtensionData]`,
and writes back to `/api/v1/activity`.

**Who does not participate.** Loop, Trio and LoopFollow write nothing here.
AAPS has a full `HeartRate` database entity, a Wear listener, a Garmin
inbound plugin and automation triggers on heart rate — and **no Nightscout
upload path**. The data exists on the phone and stops there.

**Three things worth naming:**

1. **`activity` is already the composed-resource pattern.** One collection,
   a `type` discriminator, per-type payload fields, and an extension bag on
   the model. That is the design §2 argues `devicestatus` needs, shipped and
   working, by the one client that had a reason to build it.
2. **Our own spec proposes a conflicting design.**
   `specs/openapi/aid-heartrate-2025.yaml` defines a separate `/heartrate`
   collection (from PR #8083, flagged `GAP-API-HR: Heart Rate Collection Not
   Implemented`). It is not implemented because the ecosystem solved it a
   different way. Reconciling the two is a spec decision, and the shipped
   pattern should win unless there is a reason it cannot.
3. **`activity` is an overloaded word, dangerously so.** In oref0 and Loop,
   `activity` is *insulin activity* in dU/min — `openaps.iob.activity` and
   `openaps.iob.iobWithZeroTemp.activity` in this corpus are that, and they
   are dosing inputs. In Nightscout, `activity` is the physical-activity
   collection. Any schema, generated type or query that mixes them is a
   clinical-grade confusion, and the names give no warning.

**What is not measured.** The corpus contains no `activity` documents at all,
because `tools/ns2parquet/ns_fetch.py` requests only `entries`, `treatments`,
`devicestatus`, `profile` and `status`. Everything in this section is source
evidence; the prevalence and shape of real activity data is unmeasured, and
extending the fetcher is the obvious next step.

## 4a. Vendor variation: what each system *can* write

The census says what 11 sites did write. With one AAPS site and one Trio
site it under-represents both. `make schema-vendors` reads each project's
own wire model instead, so "nobody writes this" and "our corpus has one site
of that client" stop being the same observation.

| Project | Declared | Observed in corpus | Declared but never seen |
|---|---|---|---|
| AndroidAPS (`RemoteDeviceStatus.kt`) | 35 | 18 | **17** |
| Trio (`NightscoutStatus.swift`) | 19 | 16 | 3 |
| Trio determination (`Determination.swift`) | 29 | 27 | 2 |
| Trio IOB (`IOBEntry.swift`) | 17 | 16 | 1 |
| Loop (`LoopStatus.swift`) | 14 | 11 | 3 |
| Loop dose rec. (`AutomaticDoseRecommendation.swift`) | 3 | 3 | 0 |
| oref0 (`determine-basal.js`) | 18 | 14 | 4 |
| oref0 IOB (`iob/total.js`) | 10 | 7 | 3 |

Every surface is partial — a payload is assembled across several files and
only the named ones are read — so a gap means "not in the file we parsed",
never "the project cannot write it".

### 4a.1 AAPS uploads its running configuration; nobody else does

Of AAPS's 17 unobserved fields, ten are one feature:

```
configuration  apsConfiguration  sensitivityConfiguration  safetyConfiguration
overviewConfiguration  insulinConfiguration  smoothing  aps  insulin  sensitivity
```

`RunningConfigurationImpl.kt` populates these from the live plugin set, so an
AAPS device status can carry *which algorithm, which sensitivity model, which
insulin model and which smoothing* were running at the moment of the
decision. That is dosing provenance no other system records, and our corpus
contains none of it — the one AAPS site never emitted it.

What is in there is narrower than the names suggest, and the distinction
matters for §3.2. From AAPS's own test fixtures:

* `sensitivityConfiguration` — `autosens_max`, `autosens_min`,
  `openapsama_min_5m_carbimpact`, `absorption_cutoff`. Real algorithm
  parameters.
* `apsConfiguration` — for the SMB plugin, only `ApsUseDynamicSensitivity`
  and `ApsDynIsfAdjustmentFactor`.
* `safetyConfiguration` — `age`, `treatmentssafety_maxbolus`,
  `treatmentssafety_maxcarbs`: caps on *manual entry*, not the loop's dosing
  ceilings.

So §3.2 stands as written: `maxIob` and `maxBasal` are AAPS *preferences*
(`DoubleKey.ApsMaxBasal`, `DoubleKey.ApsAmaMaxIob`) and are in none of the
uploaded configuration blocks. AAPS records more of its configuration than
any other system and still does not record the two limits a replay needs.

### 4a.2 Trio declares two safety predictions the corpus never carried

`minGuardBG` and `minPredBG` — the minimum guarded and predicted glucose
behind a dosing decision. Declared in `Determination.swift`'s `CodingKeys`,
absent from 702,254 device statuses. Either conditional on a code path our
one Trio site did not take, or newer than the April snapshot.

### 4a.3 Two near-misses worth recording as method

Both were wrong in a first pass and corrected before anything was published,
and both are now regression tests:

* Trio's `tdd` ships as `TDD` — its `CodingKeys` renames it — and the corpus
  carries `TDD`. Reading Swift *property* names instead of `CodingKeys`
  reported it as never written.
* `reasonParts` and `reasonConclusion` look like a structured replacement for
  oref0's free-text `reason` field, which would be a notable finding. They
  are computed properties, deliberately excluded from `CodingKeys` — a
  comment in that file says so explicitly — and are never serialized. Trio
  structures the reason *for its own UI*, not on the wire.

The general lesson for any vendor-surface analysis: in Swift the wire
contract is `CodingKeys`, and a property is not a field.

## 5. What this supports

1. **Report two upstream defects, both found by measurement.** Nocturne's
   `LoopAutomaticDoseRecommendation` expecting `bolus`/`tempBasal` against
   NightscoutKit's `bolusVolume`/`tempBasalAdjustment` (§2.2), and the
   `Suspend Pump` / `Pump Suspend` word-order mismatch from the
   [extensibility evaluation](./nightscout-extensibility-models-2026-09-10.md)
   §3.2. Both are small fixes with measurable effect.
2. **Put an extension point at every level of `devicestatus`, or compose it.**
   One bag at the root does not protect a tree. The `activity` collection
   shows the composed alternative working in production.
3. **Describe the flat pump shape as the primary one.** The 2025.2.0 spec
   revision documented it; typed models still read the nested form. Until
   they agree, 85% of pump state is dropped on ingest by the most complete
   typed model available.
4. **Record dosing safety limits for oref0 derivatives.** `maxIob`,
   `maxBasal` and `suspendThreshold` are configured in AAPS and Trio and
   reach Nightscout nowhere. Loop's `loopSettings` is the existing precedent
   for how, even if the location should be better named.
5. **Adopt the shipped `activity` pattern for heart rate and steps** rather
   than the proposed `/heartrate` collection, and rename or namespace one of
   the two meanings of `activity` before generated types make the collision
   permanent.
5a. **Ask AAPS to keep uploading its configuration block, and declare it.**
   It is the only record in the ecosystem of which algorithm and which
   sensitivity model produced a decision (§4a.1). The spec declares it only
   as `configuration: {type: object}`; it deserves a real shape.
6. **Treat "replayable from Nightscout" as a stated non-goal, or close the
   8 absent inputs.** Today a stored decision cannot be reproduced: the run
   flags and the meal-detection state are simply not written.

## 6. What is not measured

* **Nocturne's V4 decomposition of `devicestatus` and `profile`.** §2 measures
  what its *legacy* deserializer retains. The `ApsSnapshot` mapping types 14
  scalars and keeps the rest as JSON blobs (`SuggestedJson`, `EnactedJson`,
  `LoopJson`), so "retained" there means "stored", not "queryable".
* **Whether dropped fields matter to any consumer.** Nothing downstream was
  checked for a dependency on them.
* **Whether AAPS's configuration block appears in the wild at all.** §4a.1
  reads the uploader, not data: our one AAPS site emitted none of it, and
  the conditions under which `RunningConfigurationImpl` runs were not traced.
* **AndroidAPS behaviour of any kind, from data.** The corpus contains no
  AAPS closed-loop site: the site previously described as AAPS runs no loop
  at all (xDrip4iOS and LibreLinkUp, manual treatments, `automatic` never
  true). Every AAPS statement in this document is read from its wire models.
* **Trio profile variation** — one site, and that site's profile documents
  were written by Loop.
* **Real `activity` documents**, per §4.
* **`heartrate` as a v3 collection.** Not implemented anywhere; the spec in
  this repo is a proposal, not a description.

## 7. References

* `make schema-nocturne` → `reports/schema-census/nocturne-coverage.json`
* `make schema-dosing` → `reports/schema-census/dosing-inputs.json`
* `specs/nsschema/dosing-input-sources.yaml` — the input→source map
* `conformance/t1pal/vectors/`, `conformance/loop/vectors/` — 385 replay vectors
* NightscoutKit `Models/AutomaticDoseRecommendation.swift`, `Models/LoopStatus.swift`
* xDrip+ `utilitymodels/NightscoutUploader.java` (`postStepsCount`, heart-rate upload)
* AAPS `database/entities` `HeartRate`, `plugins/sync/garmin/GarminPlugin.kt`
* Nocturne `Core.Models/DeviceStatus.cs`, `Core.Models/Activity.cs`,
  `API/Services/V4/DeviceStatusDecomposer.cs`, `Connectors/…/NightscoutActivityWriteBackSink.cs`
* cgm-remote-monitor `lib/server/env.js`, `lib/data/dataloader.js`
