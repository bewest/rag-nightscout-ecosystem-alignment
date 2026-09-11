# Extending the Nightscout document model: four designs, measured

Date: 2026-09-10. Status: draft for maintainer discussion. Companion to
[Typed schemas for Nightscout](./nightscout-typed-schema-evidence-2026-09-10.md)
and to the
[`x-aid-extensions` convention proposal](../sdqctl-proposals/x-aid-extensions-convention-proposal.md);
extends §6.5.1 of the
[multitenancy discussion](./nightscout-multitenancy-discussion-2026-09-09.md).

**Nothing here is a proposal to merge. The deliverable is evidence.**

---

## TL;DR

Every client already extends the document model. The question is not
whether to allow it but which shape to give it. Three designs are on the
table, and they are not equally knowable: two can be measured against
1.97 million real documents, and one cannot be measured at all because
nothing implements it.

**Scope is the axis that matters, and the first version of this document
missed it.** "Extensibility" at *tenant* scope and at *controller-product*
scope are different problems with different evidence, and lumping them
together made this document read as a rejection of extensibility when it is
only a rejection of one scope of it. Four designs, not three:

| | Extension bag | Granular primitives | Controller descriptions | Tenant-registered resources |
|---|---|---|---|---|
| **Scope** | per field | per record type | **per controller product** | per tenant |
| **Implemented?** | Proposed here; `devicestatus.extended` is a partial precedent | **Yes — Nocturne V4, in production shape** | Generated in `specs/sync/registrations/`; not yet consumed | Nowhere in the ecosystem |
| **Migration cost** | **6.4% / 15.2% / 10.5% / 0.0%** of live documents per collection | **0.01%** of treatments unroutable | **Zero** — describes documents already being written | Unknown |
| **Coverage of the corpus** | Total, by construction | **99.99%** of treatments reach a typed primitive | 3 controllers described from measurement | Unknown |
| **Fields with no typed home** | n/a — the bag is the home | **5 field names**, one of them common | n/a — names the absences too (`status: absent`) | Whatever a tenant declares |
| **Validation cost** | Measured: 85k–330k docs/s | Same class | None; it describes, it does not gate | Per-tenant compiled schemas; unmeasured |
| **Who has to change** | Every client that flattens today | Server only; clients keep writing legacy documents | **Nobody, by default**; a controller may publish its own | Server, plus a registration flow |
| **Number of schema stores** | one | one | one per *product* — a handful, reviewed in a PR | one per *site* — unbounded |

**The finding that should move the discussion:** the granular-primitive
model is not hypothetical and not expensive. Replaying Nocturne's own V4
treatment routing over the corpus, **368,905 of 369,419 treatments (99.86%)
reach a typed primitive from `eventType` alone**, a further 492 (0.13%)
from the insulin and carb values present, and **22 documents (0.01%) are
unroutable** — all of them one event type, and for a reason that is a bug
rather than a design limit (§3.2).

**These are not competing designs.** The extension bag is a *document*
convention; the primitive model is a *storage* decomposition. Nocturne runs
both: it decomposes into V4 primitives *and* keeps `[JsonExtensionData]` on
its legacy models for keys it does not recognise. The real question is which
one absorbs the long tail, and the measurements say: primitives absorb
essentially all of the structure, and a bag is still needed for a handful of
leaf fields (§3.3).

---

## 1. What each design is

### 1.1 Extension bag — `x-aid-extensions`

Keep `entries`, `treatments`, `devicestatus` and `profile` as they are. Add
one named optional object per collection; clients write non-standard fields
there rather than at the top level. Readers tolerate unknown keys in both
places.

Precedent exists in two directions. `aid-devicestatus-2025.yaml` already
declares `extended` with `additionalProperties: true` — an unnamed bag. And
Nocturne's `DeviceStatus.ExtensionData` (`[JsonExtensionData]`) is the same
idea implemented: unknown top-level keys are captured rather than dropped.

### 1.2 Granular primitives

Replace the fat documents, at the storage layer, with small typed records:
a `Bolus`, a `CarbIntake`, a `TempBasal`, a `BGCheck`, a `DeviceEvent`, a
`Note`, a `SensorGlucose`. A legacy document that mixes concerns decomposes
into several, linked by a correlation id — a `Meal Bolus` carrying both
insulin and carbs becomes a `Bolus` **and** a `CarbIntake` sharing a
`CorrelationId`.

**This is Nocturne's V4 model**, 65 types in
`src/Core/Nocturne.Core.Models/V4/`, with the decomposition implemented in
`TreatmentDecomposer` and partners for profile, activity and devicestatus.
It is the only one of the four designs with a working implementation to
measure.

### 1.3 Controller descriptions — per product, not per site

One file per *controller product* declares how to recognise its documents,
what it writes, which dosing inputs it publishes, which it has but does not,
and the state categories it exposes. The hub ships a generated set and may
serve them; a controller may publish its own to correct or extend one.

This is the design in
[the controller-descriptions proposal](./PROPOSAL-controller-descriptions-2026-09-11.md),
and §3.4 argues it is the answer to controller-scoped extensibility — the
ability to ship a feature nobody else has without negotiating for it. Three
descriptions are generated in `specs/sync/registrations/`; **none has been
consumed by a reader yet**, so it sits between §1.2's measured model and
§1.4's unmeasured one.

### 1.4 Tenant-registered custom resources

A tenant registers a schema for a named resource; the server stores and
validates documents of that kind against the registered schema — the
Kubernetes CRD pattern, raised in §6.5.1 of the multitenancy discussion.

Nothing in the ecosystem implements this. It is included because it is the
design the others are often argued against, and because being explicit about
*what is unknown* is more useful than leaving it implied.

**The difference from §1.3 is the number of schema stores, and it decides
everything.** Per product there are four or five, each reviewed in a pull
request. Per site there are as many as there are deployments, reviewed by
nobody. §4's three costs all follow from the second, and none from the
first.

## 2. What the extension bag costs — measured

From `reports/schema-census/impact.json`: the share of live documents an
`x-aid-extensions` layout would reject, because the fields it wants in the
bag are at the top level today.

| Collection | Documents | Rejected | The fields responsible |
|---|---|---|---|
| `entries` | 896,589 | **6.44%** | `glucose` (one site, 86% of its documents) |
| `treatments` | 369,419 | **15.21%** | `id` (one site, 90% of its documents), `units`, `remoteAddress`, `mills`, `endmills`, `durationType` |
| `devicestatus` | 702,254 | **10.52%** | the whole `openaps.*` subtree, one site |
| `profile` | 202 | **0.00%** | nothing |

That rejection rate **is** the migration: it is the share of traffic whose
producer would have to move a field before a strict bag-enforcing validator
could be switched on. It is not a cost of the convention as documentation —
adopting `x-aid-extensions` as a *forward-looking* convention costs nothing,
because it asks nothing of existing writers.

Two things the number hides. First, it is dominated by single-site vendor
subtrees, so it measures "how much of this corpus is one client's private
structure", not "how messy the ecosystem is".

Second, the numbers move when the spec does. Against the 2025.1.0 specs the
same measurement was 6.44% / 15.19% / **14.94%** / **0.99%**; documenting
fields in the 2025.2.0 revision took `devicestatus` from 14.94% to 10.52%
and `profile` from 0.99% to 0.00%, without any client changing anything.
**Describing a subtree and relocating it are alternatives, and describing it
is free** — `loopSettings` was 26 paths that went from undeclared to
documented, and the profile collection's migration cost went to zero as a
result.

## 3. What the primitive model covers — measured

`make schema-decompose` replays Nocturne's routing over every treatment in
the corpus. The routing is transcribed from `TreatmentDecomposer.cs` and
`TreatmentTypes.cs`; it reproduces which branch a document takes, not the
records that branch writes.

### 3.1 Coverage

| Branch | Share | Documents | Produces |
|---|---|---|---|
| temp-basal | 54.86% | 202,677 | `TempBasal` |
| correction-bolus | 38.46% | 142,094 | `Bolus` |
| carb-correction | 4.11% | 15,194 | `CarbIntake` |
| plain-bolus | 0.83% | 3,057 | `Bolus` |
| override | 0.78% | 2,892 | `TherapySettings` |
| device-event | 0.57% | 2,112 | `DeviceEvent` |
| note | 0.18% | 676 | `Note` |
| **data-fallback** | 0.13% | 492 | `Bolus`, `CarbIntake` |
| bg-check | 0.04% | 161 | `BGCheck` |
| temporary-target | 0.01% | 42 | `TherapySettings` |
| **unroutable** | **0.01%** | **22** | — |

**99.86% route from `eventType` alone.** The data fallback — "I do not
recognise this event type, but there is insulin or carbs here, so produce
records from the data" — catches a further 0.13%. Under 25 documents in two
million have nowhere to go.

The fallback deserves attention beyond its size. It is what makes the
primitive model robust to an ecosystem that keeps inventing event types:
the census found `Bolus` and `Carbs` in live data and in no declared enum
(QUIRK-TREATMENTS-005), and a model that discriminated purely on a closed
`eventType` enum would have dropped them. **An open-world discriminator with
a data-shaped fallback is what makes decomposition survive contact with
this ecosystem** — which is the same lesson as "never reject an unknown
`eventType`" from the quirks registry, reached from the other direction.

### 3.2 The 22 unroutable documents are a bug, not a limit

All 22 carry `eventType: "Suspend Pump"`.

`Suspend Pump` is the spelling in `aid-treatments-2025.yaml`, the spelling
in Nightscout's own documented event types, and the only spelling in the
corpus. Nocturne's V4 decomposition routes device events through
`TreatmentTypes.DeviceEventTypeMap`, keyed on
`TreatmentTypes.PumpSuspend = "Pump Suspend"` — the words reversed.

Nocturne is internally inconsistent here rather than simply wrong: its
legacy `TreatmentEventType` enum declares
`[EnumMember(Value = "Suspend Pump")]`, and `EventTypeConfiguration` uses
`"Suspend Pump"` too. Only the V4 decomposition path uses the reversed
constant, so a treatment the rest of that codebase recognises is silently
skipped on the way into V4.

This is worth reporting upstream on its own account, and it makes the
measured 0.01% an *upper* bound: fix the constant and the corpus decomposes
completely.

### 3.3 Five fields have no typed home

Counting keys on legacy treatments that no V4 primitive declares:

| Field | Occurrences | What it is |
|---|---|---|
| `userEnteredAt` | 6,491 | when the user entered the treatment, distinct from when it was recorded |
| `userLastModifiedAt` | 131 | when the user last edited it |
| `remoteAddress` | 98 | origin of a remote-command write |
| `endmills` | 2 | one client's end-of-interval timestamp |
| `durationType` | 1 | `indefinite` |

This is the honest limit of the primitive model, and it is small — but
`userEnteredAt` appears on **10 of 11 sites**, so it is a cross-client field
with no home rather than a single vendor's artefact. Nocturne would catch it
in `ExtensionData` on the legacy model and lose it on the way into V4.

**This is the argument for running both designs, and it is now quantified:**
primitives absorb all of the structure and 99.99% of the documents; a named
extension location is still needed, for roughly five leaf fields rather than
for the long tail people assume.

### 3.4 Controller-scoped extensibility, which is a different question

The design that lets a controller ship something unique is not in §1's
original three. It is the **controller description**
([proposal](./PROPOSAL-controller-descriptions-2026-09-11.md)), and the
distinction from §4's tenant-registered resources is the count of schema
stores: **one per controller *product*, of which there are four or five and
each is reviewed in a pull request** — against one per *site*, of which there
are thousands and none is reviewed by anyone.

That single difference removes all three of §4's costs:

| §4's objection to tenant registration | Why controller descriptions avoid it |
|---|---|
| Query cost becomes unbounded per tenant | `queryProfile` is declared per product and reviewed. The filterable set is finite and known before deployment |
| Validation stops being one compiled validator | Descriptions do not validate anything. They describe; nothing is rejected that is not rejected today |
| A registered schema is a migration surface | True, and it stays true — but versioning four product descriptions in a repo is a pull request, not a per-tenant migration story |

**So (b) in the motivation triad is answered by descriptions, not by CRDs.**
A controller that wants to ship an effect type, a state category, or a
dosing input nobody else has declares it in its own description and starts
writing it. Readers that do not understand it still store it; readers that
want to can look it up. What it does *not* require is agreement from the
ecosystem before the feature ships — which is the actual complaint.

The evidence for this is thinner than for §3's primitive coverage, and should
be labelled that way: three descriptions exist, generated from one corpus,
and **none has been consumed by a reader in production.** The claim that this
shape supports per-controller innovation is a design argument, not a
measurement.

## 4. Tenant-registered resources (§1.4) — what can and cannot be said

No implementation exists, so nothing here is measured. What the other two
measurements *do* constrain:

**This section is about *tenant*-scoped registration specifically.** For
controller-product-scoped extensibility, which is the thing this series
actually proposes, see §3.4 — the conclusion below does not apply to it.

**The case for it is weaker than it looks, on this evidence.** The argument
for CRD-style registration is that the long tail is large and diverse enough
that no fixed schema can anticipate it. The corpus says the opposite: the
tail is 5 field names and one mis-spelled event type. A registration
mechanism, a per-tenant schema store, per-tenant compiled validators and a
migration story for registered schemas is a large amount of machinery for
that.

**Where it would earn its place** is a case this corpus cannot see: a
controller that wants to store a *new kind of record* — not a field on an
existing one — with its own retention, query and authorization behaviour.
Nothing in `entries`, `treatments`, `devicestatus` or `profile` is that.
Whether such a need exists is a question for the controller maintainers, not
for the data.

**Three costs to name before anyone builds it**, each of which the other
designs avoid:

1. **Query cost becomes unbounded per tenant.** §6.5 of the multitenancy
   discussion found the `$regex` filter reaching MongoDB with no pattern
   guard, no index requirement and no `maxTimeMS`. A tenant-declared schema
   means tenant-declared *fields to query*, and the query-profile work that
   section proposes has to cover shapes nobody reviewed.
2. **Validation stops being one compiled validator.** §6 measured
   85k–330k docs/s for a fixed schema set. N tenants × their own schemas is
   a different cache-residency problem, and it lands on exactly the
   multitenant path where the memory numbers are tightest (§7.4).
3. **A registered schema is a migration surface.** A tenant's resource
   schema will need versioning, and nothing in Nightscout has a mechanism
   for that today.

## 5. What this supports

1. **Adopt `x-aid-extensions` as documentation now, not as a validator.**
   It costs nothing forward-looking, and §2 prices the enforcement decision
   for later. Where a subtree is big enough to describe — `loopSettings`
   was 26 paths — **describing it in the spec is strictly cheaper than
   relocating it**: documenting it took the profile collection's
   bag-migration cost from 0.99% to 0.00%, and documenting the flat pump
   status shape took `devicestatus` from 14.94% to 10.52%.
2. **Treat the primitive model as the storage-side answer, and say so with
   the number.** 99.99% of treatments reach a typed record. The design is
   built, in Nocturne, and the interesting work is reconciling it with this
   repo's specs field by field — not relitigating whether decomposition can
   work.
3. **Keep an extension location even with primitives.** Five fields, one of
   them on 10 of 11 sites, have no typed home. That is a small, concrete
   requirement rather than an open-ended one.
4. **Do not build *tenant*-registered resources on this evidence.** Revisit if
   a controller maintainer names a new *kind* of record, with its own
   lifecycle, that the primitives cannot express.
   **But do use controller-product-scoped descriptions as the extensibility
   mechanism** (§3.4). Same idea, at a scope where none of §4's three costs
   apply — a handful of schema stores, reviewed in pull requests, describing
   rather than validating. This is how a controller ships a feature unique to
   it without ecosystem negotiation. It is also the weakest-evidenced
   recommendation in this document: three descriptions exist, and **nothing
   has consumed one yet.**
5. **Report the `Suspend Pump` mismatch upstream.** It is a two-character
   fix with a measurable effect, found by replaying real data.

## 6. What is not measured

* **Only `treatments` decomposition is simulated.** Nocturne has profile,
  activity and devicestatus decomposers; their coverage is unmeasured, and
  `devicestatus` is where the vendor subtrees actually live, so it is the
  one most likely to behave differently.
* **The simulation reproduces branches, not records.** Whether the produced
  `Bolus` and `CarbIntake` carry every value faithfully is a separate
  question needing Nocturne running against the corpus.
* **Round-tripping is untested.** Whether a decomposed set recomposes into
  a document a legacy client accepts is the question that decides whether
  decomposition can happen behind the existing API.
* **No field-by-field diff of V4 against `specs/openapi/`.** The
  `x-aid-extensions` proposal named this as an open next step and it remains
  open; `reports/schema-census/attribution.json` now gives it a starting
  point, showing Nocturne serializes 179 of the 247 field names the census
  found — more than any other project.
* **Nothing about tenant-registered resources**, for want of an
  implementation.

## 7. References

* `make schema-decompose` → `reports/schema-census/decomposition.json`
* `make schema-impact` → `reports/schema-census/impact.json`
* `specs/quirks/` — the measured deviation registry, 17 entries
* Nocturne `cb43fae5`: `src/Core/Nocturne.Core.Models/V4/` (65 types),
  `src/API/Nocturne.API/Services/V4/TreatmentDecomposer.cs`,
  `src/Connectors/Nocturne.Connectors.Core/Constants/TreatmentTypes.cs`,
  `src/Core/Nocturne.Core.Models/TreatmentEventType.cs`
* [`x-aid-extensions` convention proposal](../sdqctl-proposals/x-aid-extensions-convention-proposal.md)
* [Multitenancy discussion](./nightscout-multitenancy-discussion-2026-09-09.md) §6.5, §6.5.1, §7.4
