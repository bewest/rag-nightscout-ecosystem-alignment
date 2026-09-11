# A hub-and-spoke sync model for AID controllers

Date: 2026-09-11. Status: draft for maintainer discussion. Fifth in a series
with
[Typed schemas](./nightscout-typed-schema-evidence-2026-09-10.md),
[Extending the document model](./nightscout-extensibility-models-2026-09-10.md),
[devicestatus and profile fidelity](./nightscout-devicestatus-profile-fidelity-2026-09-10.md)
and
[Settings, extensibility and delegation](./nightscout-configuration-and-delegation-2026-09-10.md).

**Nothing here is a proposal to merge. The deliverable is a design to argue
with, and the measurements that make it arguable.**

---

## TL;DR

The ask has four parts and they turn out to be one design: controllers
register a live state model, the hub derives a sync contract from it, the
wire stays composite so edge devices make few requests, and storage
decomposes into primitives so queries stay bounded and replay stays possible.

**Five measurements that shape it:**

| # | Finding | Evidence |
|---|---|---|
| 1 | **The three controllers have three different sync designs, and two have none.** AAPS uses v3's `lastModified` watermark and `history/{from}` deltas. Loop and Trio are on v1 with **no watermark and no delta endpoint at all** | §2 |
| 2 | **Cost is dominated by per-collection fan-out, whichever API version.** Up to 5,760 requests/day for AAPS, 2,016 for Loop, 1,440 for Trio, against 576 for a two-request-per-cycle batched design | §2.1 |
| 3 | **Replay completeness is 20% for Loop and 50% for oref0 derivatives** — the share of declared dosing inputs actually recorded. Including derivable inputs: 55% and 72% | §4.2 |
| 4 | **A real replay consumer already works around this.** `oref-digital-twin` reads settings from *screenshots* with a vision model, or from AAPS's encrypted preference export, because Nightscout does not carry them. Its replay code documents `currenttemp` and insulin `activity` as unrecoverable and approximates both | §4.1 |
| 5 | **The state machine primitive already exists.** Nocturne's `StateSpan` — category, state, start, end, source, supersession — is the shape needed to observe modes, overrides, exclusions and coordination between sources | §5 |

**The design in one sentence.** A controller registers its state model once;
the hub answers with a sync contract — one cursor endpoint in, one batch
endpoint out, filters fixed in advance — and decomposes what arrives into
primitives, so the edge device gets fewer round trips while the hub gets
queryable, replayable, inspectable state.

**What makes it tractable rather than a rewrite:** every piece exists
somewhere already. v3 has the cursor. Nocturne has the decomposer (99.99% of
treatments route) and `StateSpan`. `activity` is already a
`type`-discriminated composite collection. What is missing is the
*registration* that ties them together, and the settings resource that
nobody publishes.

---

## 1. What exists today, across four API generations

Documenting this was half the question, and the answer is less unified than
the version numbers suggest.

| | v1 | v3 | v4 (Nocturne) |
|---|---|---|---|
| Shape | four fat collections | the same collections, plus a metadata envelope | typed primitives |
| Identity | `_id` | `identifier`, server-assigned | typed keys plus `LegacyId` |
| Change tracking | none | `srvCreated`, `srvModified` | inherited |
| Delta read | none | `GET /{collection}/history/{from}` | per-resource |
| Watermark | none | `GET /lastModified`, all collections at once | — |
| Batch write | array POST per collection | array POST per collection | per-resource |
| Deletes | destructive | soft, `isValid: false` | soft |
| State over time | point events only | point events only | `StateSpan` |

**Who uses what.** AAPS is on v3 and uses it as intended. Loop
(`NightscoutKit/NightscoutClient.swift`) and Trio
(`Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift`) are on v1
only — seven and five endpoints respectively, no watermark, no delta. This
is the single most important fact about "unifying v1/v3/v4": **v3's sync
machinery is already there and two of the three major controllers do not use
it.** A new version that nobody adopts would be the third such layer.

The corpus agrees. Every document in it was fetched from `/api/v1/`, and the
v3 metadata envelope is absent from all 1.97 million of them — which is why
the census reports `identifier`, `srvCreated` and `srvModified` as
"v3-only metadata, not observable via the v1 endpoint", rather than as
missing.

## 2. What sync costs now

`make schema-sync-cost` counts the distinct endpoints each client's sync
path can call, from its own source, and prices them at the five-minute
cadence the corpus shows.

| Client | API | Endpoints | Watermark | Delta endpoint |
|---|---|---|---|---|
| AndroidAPS | v3 | 20 | yes | yes |
| Loop / NightscoutKit | v1 | 7 | no | no |
| Trio | v1 | 5 | no | no |

### 2.1 Against a batched design

| Client | Upper bound/day | Batched (2/cycle) | Factor |
|---|---|---|---|
| AndroidAPS | 5,760 | 576 | 10.0× |
| Loop | 2,016 | 576 | 3.5× |
| Trio | 1,440 | 576 | 2.5× |

This is a **source-derived upper bound on distinct endpoint calls per
cycle**, not a packet capture: a cycle with nothing to upload makes fewer
calls, a catch-up after an outage makes more. It is a fair basis for
comparing sync *designs*, which is what it is for, and it should not be
quoted as a measured traffic figure.

The shape of the result matters more than the magnitude: **AAPS, the client
using v3 correctly, has the worst fan-out**, because v3 gives it a delta
*per collection* and it syncs more collections. Cursor-based sync solved the
"what changed" problem and left the "how many round trips" problem
untouched.

## 3. The design

### 3.1 Registration

A controller declares its live state model once, against
`specs/sync/controller-state-model.schema.json`:

* **documents** — the composite wire documents it writes, each with a
  *structural* discriminator (a devicestatus carrying a `loop` object rather
  than an `openaps` one) and the primitive types it decomposes to
* **stateSpans** — the state machine it exposes, as categories with states
  and a supersession rule
* **replayInputs** — every dosing input it could supply, with `status` and a
  path; **an input it has but does not publish is declared with a null
  path**, which is what makes completeness measurable rather than guessed
* **settings** — the configuration snapshot it will publish, effective-dated
* **cadence** and **queryProfile**

Worked registrations for Loop, Trio and AndroidAPS are in
`specs/sync/registrations/`, **generated from the census, the vendor
surfaces and the dosing-input map** rather than hand-written, so they cannot
claim more than was measured. `make schema-sync-model` regenerates them and
`--check` fails on drift.

The discriminator is structural on purpose. The free-text `device` string is
the field this work spent the most effort de-identifying, and it is not
reliable: one site's device strings read like a controller while its
treatments showed no automated dosing at all.

### 3.2 The contract the hub returns

Everything the hub offers is derived from the registration, so a controller
never negotiates a query shape at request time:

```
GET  /api/v4/sync?cursor=<opaque>     → one envelope, every registered
                                        collection, changes since cursor,
                                        plus the next cursor
POST /api/v4/sync                     → one batch, composite documents,
                                        mixed collections, idempotent on
                                        (dataSource, syncIdentifier)
```

Two requests per cycle, whatever the controller syncs. The cursor is a
server watermark and opaque, so the hub can change its implementation — a
`srvModified` scan today, a logical replication slot later — without a
client release.

**Why this is not just v3 with fewer paths.** The envelope is derived from a
registration, so the hub knows which collections this controller cares
about, what page size suits its cadence, and which filters it may use. v3's
`lastModified` tells a client what changed everywhere and leaves it to fan
out; a registered contract lets the hub answer the whole question once.

### 3.3 Composite on the wire, primitive in storage

The edge device sends what it has, in the shape it has it. The hub
decomposes on write:

* a treatment carrying insulin and carbs becomes a `Bolus` and a
  `CarbIntake` sharing a correlation id
* a devicestatus becomes an `ApsSnapshot`, a `PumpSnapshot` and an
  `UploaderSnapshot`
* a profile becomes `TherapySettings` plus four schedules

This is measured, not hypothetical: replaying Nocturne's routing over the
corpus places **99.86% of treatments by `eventType` alone, 0.13% by the
data present, and leaves 22 documents unroutable** — all of them one event
type, for a spelling bug rather than a design limit.

Keep the composite too. Round-tripping to a legacy client, and answering
"what did the device actually send", both need it, and the extensibility
evaluation found exactly five leaf field names with no typed home — a small,
known residue rather than an open-ended one.

### 3.4 Bounded queries are part of the contract, not a later hardening

The registration's `queryProfile` fixes the filterable fields, the operators
and the page size in advance. This is not tidiness: §6.5 of the multitenancy
discussion found the `re`/`$regex` operator reaching MongoDB with no pattern
guard, no index requirement and no `maxTimeMS` anywhere in the query path.
A sync API that accepts arbitrary filters inherits that. One that answers
only the shapes a registration declared does not.

## 4. Replay, and why physicians cannot see the settings

### 4.1 The workaround that proves the gap

`externals/oref-digital-twin` is an advisory tool that replays the real
`determine-basal` under altered settings. To do that it needs the settings.
It cannot get them from Nightscout, so it gets them from **a screenshot, via
a vision model**, or from AAPS's client-side-decrypted preference export.
Its own settings module says so plainly, and its replay code is equally
direct:

> Two inputs cannot be recovered faithfully from devicestatus alone and are
> approximated: `currenttemp` — the temp basal running at decision time
> (assumed none); insulin `activity` — the IOB curve's instantaneous
> activity (assumed 0), which degrades bgi/eventualBG.

and

> `REQUIRED_SETTINGS = ("max_iob",)`

`max_iob` is the input measured as recorded by no controller anywhere. A
serious replay tool, written independently, hits exactly the three gaps this
series measured. That is the physician complaint in code form.

### 4.2 Completeness as a published number

Because a registration declares every dosing input with a status, the hub
can report completeness per controller, per cycle:

| | Declared inputs | Recorded | Recorded or derivable |
|---|---|---|---|
| Loop | 20 | **20%** | 55% |
| Trio / AndroidAPS (oref0) | 40 | **50%** | 72% |

A "derivable" input is recomputed from stored history, which gives *a* value
and not necessarily *the* value the controller used — it saw a different
window, with different de-duplication and different noise handling. A replay
built on derived inputs tests the replayer as much as the algorithm, so the
two columns should never be collapsed.

### 4.3 Settings as a first-class, effective-dated resource

The missing piece is small and additive. A `ControllerSettings` snapshot,
versioned and effective-dated, published on change rather than per cycle:

* **effective-dated**, because a setting that changed mid-history
  invalidates a replay that assumed one value
* **versioned with the build**, because algorithm behaviour changes between
  releases — which is why `OBS-LOOP-006` and `OBS-OREF-007` ask for the
  version at all
* **declared in the registration**, so "this controller publishes nine
  settings and withholds none" is checkable

The generated registrations already list what each controller would have to
add: nine fields for Loop, four for the oref0 family.

## 5. Observing the state machine

Point events cannot answer "was the pump suspended when this dose was
skipped". Nocturne's `StateSpan` can: `Category`, `State`,
`StartTimestamp`, `EndTimestamp`, `Source`, `Metadata`, and — the part that
matters for coordination — `SupersededById`, `CanonicalId` and `Sources`.

Categories already modelled there cover the AID state machine: `PumpMode`
(automatic, limited, manual), `PumpConnectivity`, `Override`,
`TemporaryTarget`, `ProfileState`, `DataExclusion`, `Activity`.

Two properties worth keeping in any adoption:

* **Supersession, not last-write-wins.** When a human and a controller both
  set an override, or two controllers overlap, the resolution has to be
  recorded rather than implied. `authority-model.md` has already worked
  through those conflict scenarios.
* **`DataExclusion` as a first-class span.** A sensor warm-up or a known-bad
  stretch is not missing data, it is data known to be unusable, and a replay
  that cannot tell the difference will silently score itself against noise.

`specs/openapi/statespan-v3-extension.md` in this repo documents a
hypothetical v3 backport and records that Nocturne's author prefers
StateSpan stay v4-only. That preference is worth respecting: the span model
is the clearest thing to put behind a registered contract rather than to
retrofit into the collection API.

## 6. Sequencing

Ordered so nothing depends on an unmade decision, and each step is useful
alone.

1. **Publish settings.** Additive, no migration, no new API. Closes the
   physician complaint and the digital-twin workaround. The registrations
   name the fields.
2. **Registration and the derived contract, read-only first.** A controller
   registers; the hub offers the cursor envelope. No write path yet, so
   nothing can be corrupted by an early adopter.
3. **Batch write.** Idempotent on `(dataSource, syncIdentifier)`, which
   Nocturne's V4 already uses as its update key.
4. **Decomposition behind the contract.** Already measured at 99.99% for
   treatments; `devicestatus` and `profile` decomposition are unmeasured and
   should be before they are relied on.
5. **StateSpan behind the contract**, for the categories a registration
   declares.
6. **Retire nothing.** v1 stays. Every argument in this series for aliasing
   over renaming applies at the API layer too.

## 7. What is not measured

* **Whether two requests per cycle is achievable in practice.** §2.1 is an
  upper bound on endpoint calls, not a measurement of traffic, and payload
  size may trade against request count.
* **`devicestatus` and `profile` decomposition coverage.** Only treatments
  were replayed. `devicestatus` is where the vendor subtrees live, so it is
  the one most likely to behave differently.
* **Round-tripping.** Whether a decomposed set recomposes into a document a
  legacy client accepts is the question that decides whether decomposition
  can happen behind the existing API at all.
* **Cursor semantics under concurrent writers.** Two controllers plus a
  care-portal user writing to one site is the normal case, and `srvModified`
  ordering under that load is unexamined.
* **Anything about AndroidAPS from data.** Still no AAPS closed-loop site in
  the corpus.
* **The registration's own lifecycle.** How a controller updates a
  registration when it ships a new build, and what the hub does with
  in-flight data under the old one.

## 8. References

* `make schema-sync-cost` → `reports/schema-census/sync-cost.json`
* `make schema-sync-model` → `specs/sync/registrations/{loop,trio,androidaps}.yaml`
* `specs/sync/controller-state-model.schema.json`
* `specs/conformance/observability-profile.yaml` — the obligations a registration would formalise
* `externals/oref-digital-twin/` — `DESIGN.md` §2, `replay/inputs.py`, `settings/schema.py`
* Nocturne: `Core.Models/StateSpan.cs`, `API/Services/V4/TreatmentDecomposer.cs`
* AAPS `core/nssdk/.../NightscoutRemoteService.kt`; Loop `NightscoutKit/NightscoutClient.swift`; Trio `Sources/Services/Network/Nightscout/NightscoutAPI.swift`
* cgm-remote-monitor `lib/api3/` — `lastModified`, `{collection}/history/{lastModified}`
