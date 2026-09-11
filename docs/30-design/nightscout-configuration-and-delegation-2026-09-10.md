# Settings, extensibility, new data, and delegated access: four open questions

Date: 2026-09-10. Status: draft for maintainer discussion. Fourth in a
series with
[Typed schemas](./nightscout-typed-schema-evidence-2026-09-10.md),
[Extending the document model](./nightscout-extensibility-models-2026-09-10.md)
and
[devicestatus and profile fidelity](./nightscout-devicestatus-profile-fidelity-2026-09-10.md).

**Nothing here is a proposal to merge, and §5 in particular is a technical
sketch, not legal or regulatory advice. Anything acted on from §5 needs
review by someone qualified in health-data privacy for the jurisdictions
involved.**

---

## TL;DR — the four questions, answered directly

| Question | Answer |
|---|---|
| Have we documented all the settings and dosing inputs? | **Now, mostly.** 60 inputs across both algorithm families, each checked against the corpus. What is *not* documented is the settings surface that never becomes an algorithm input — every user-facing preference in AAPS, Loop and Trio |
| Are they recorded with high fidelity? | **No, and the gap is symmetric.** Loop records its safety limits and none of its algorithm-behaviour switches. oref0 derivatives record their algorithm state and none of their safety limits. Neither family records a complete configuration |
| Is there a roadmap for uniting field names or providing extensibility? | **There was not. §4 is one**, sequenced by measured cost, with the cheapest and least disruptive steps first |
| Does new out-of-band data change anything? | **Structurally, no — the pattern already exists** (`activity`, `type`-discriminated). **For privacy, yes, categorically**, and that is §5's problem more than the schema's |
| Privacy-preserving delegation between agents? | **Nothing in the ecosystem does this today.** Nightscout's read permission is `*:*:read` — one bit. §5 sets out what would have to exist |

**The finding worth leading with.** Two AID families, two complementary
halves of a configuration record, and no site has both:

| | Safety limits | Algorithm behaviour |
|---|---|---|
| **Loop** | recorded (`loopSettings.maximumBolus`, `maximumBasalRatePerHour`, `minimumBGGuard`) | **absent** — 8 switches, including one that scales every automatic dose |
| **AAPS** | **absent** — `maxIob`, `maxBasal` are preferences, uploaded nowhere | partly recorded (`sensitivityConfiguration`, `apsConfiguration`, `smoothing`) |
| **Trio** | **absent** — its uploader writes no limits | recorded (the `openaps.*` determination) |

`automaticBolusApplicationFactor` is the sharpest single example. It is the
fraction of a recommended bolus Loop actually delivers, it defaults to 0.4,
and it is recorded nowhere. Two sites with identical therapy settings and
identical glucose will dose differently, and nothing in Nightscout says why.

---

## 1. What is now documented

`specs/nsschema/dosing-input-sources.yaml` covers **60 dosing inputs across
two algorithms**, each mapped to the Nightscout paths that could carry it
and each claim checked against the census by `make schema-dosing`. All 60
currently hold.

| | Inputs | recorded | derivable | partial | **absent** |
|---|---|---|---|---|---|
| oref0 (AAPS, Trio, OpenAPS) | 40 | 20 | 9 | 3 | **8** |
| Loop | 20 | 4 | 7 | 1 | **8** |

The two sets come from different kinds of evidence, and the difference
matters:

* **oref0's** is capture-derived — the union of `input.*` paths across the
  385 replay vectors in `conformance/`, from real AAPS and Loop phone runs.
* **Loop's** is source-derived, from `AlgorithmInput` in
  `externals/LoopAlgorithm/Sources/LoopAlgorithm/AlgorithmInput.swift`. No
  vector set in this repo carries Loop's native inputs: the files under
  `conformance/loop/vectors/` are Loop *data* replayed through the oref0
  harness for cross-validation, so they describe oref0's input shape. An
  earlier reading of this document's series treated them as Loop's, which
  would have missed every finding in §2.

### 1.1 What is still not documented

* **The settings surface that is not an algorithm input.** Alarm
  thresholds, display preferences, connection settings, pump-specific
  configuration. AAPS's `overviewConfiguration` alone carries ~25 of these.
  A dosing replay does not need them; a support conversation, a bug report
  or an incident review often does.
* **Loop's override presets as configuration.** `overridePresets` is
  recorded (10 sites, 100% of profile documents) but is a *list of things
  the user might do*, not a record of settings in force; the active
  override is elsewhere.
* **Pump-side limits.** Every pump enforces its own maxima independently of
  the controller. None of it reaches Nightscout.
* **Anything from AndroidAPS, from data.** The corpus has no AAPS
  closed-loop site; all AAPS statements here are read from its wire models.

## 2. The configuration gap is symmetric, and that is the interesting part

If this were one vendor being careless it would be a bug report. It is two
mature projects each recording the half the other omits, which means it is
a missing shared expectation rather than a missing feature.

**Loop's absent eight** are all algorithm-behaviour switches:
`automaticBolusApplicationFactor`, `carbAbsorptionModel`,
`recommendationInsulinModel`, `useIntegralRetrospectiveCorrection`,
`includePositiveVelocityAndRC`, `useMidAbsorptionISF`,
`maxActiveInsulinMultiplier`, `gradualTransitionsThreshold`. Several change
the delivered dose directly.

**oref0's absent eight** are run state and one limit: `microBolusAllowed`,
`flatBGsDetected`, the unannounced-meal detection slopes, bolus-snooze IOB,
and `maxIob`.

Neither is hard to fix in principle — both are small, stable, and already
serialized somewhere on the device. The obstacle is that nothing says they
should be recorded, which is what `OBS-PROF-004` in
`specs/conformance/observability-profile.yaml` now says, and what §4 phase 4
sequences.

## 3. Naming: what actually diverges

Before proposing unification it is worth being precise about how much
divergence there is, because the answer is "less than it feels like, but in
load-bearing places". From the quirks registry and the vendor surfaces:

| Kind | Example | Scope |
|---|---|---|
| Same concept, different name | Loop `bolusVolume` vs Nocturne's expected `bolus`; `tempBasalAdjustment` vs `tempBasal` | 4 paths, 10 sites, drops the dosing decision |
| Same concept, different word order | `Suspend Pump` (Nightscout, corpus) vs `Pump Suspend` (Nocturne's V4 map) | 22 documents unroutable |
| Same concept, different shape | flat `pump.bolusing` vs nested `pump.status.bolusing` | 85.1% vs 10.5% of device statuses |
| Same concept, different vocabulary | `mg/dl`, `mg/dL`, `mmol`, `mmol/L` across three of our own specs and the data | every profile document |
| Same name, different concept | `activity` = insulin activity (dU/min, a dosing input) **and** physical activity (a collection) | ecosystem-wide |
| Same concept, different case | `Normal` vs `normal` | 130,257 documents |

The last two are the dangerous ones. A case mismatch fails loudly. A name
collision between insulin activity and physical activity fails silently, in
a generated type, in a clinical context.

## 4. A roadmap, sequenced by measured cost

Each phase states what it costs, from the measurements rather than from
estimation, and phases are ordered so that nothing later depends on a
decision that has not been made.

### Phase 0 — done, and it was the precondition

Census, spec correction to `2025.2.0`, the quirks registry, the generated
artifacts. Strict validation went from rejecting 93.5%/63.4%/100%/100% of
live documents to 6.4%/15.2%/10.5%/0.0% without any client changing
anything. **Documenting a field is strictly cheaper than relocating it**,
and that is the measured basis for everything below.

### Phase 1 — alias, do not rename. Cost: zero for writers

Nothing in §3 needs a writer to change. Every divergence there can be
resolved by declaring both forms and naming one canonical:

* declare the alias pairs in the spec (`bolusVolume` ↔ `bolus`,
  `tempBasalAdjustment` ↔ `tempBasal`, flat ↔ nested pump status)
* extend enums to the union, as 2025.2.0 already did for `direction`,
  `eventType`, `type` and `units`
* add a reader-facing normalization table — the quirks registry's
  `reader_guidance` is already this, for 17 deviations

A rename breaks every existing reader. An alias breaks nobody, and a
generated normalizer makes the canonical form available to anyone who wants
it. **Renaming should be reserved for the one case where both names cannot
coexist** — and §3 contains no such case.

### Phase 2 — fix the two mismatches that lose data. Cost: two small patches

`Pump Suspend`/`Suspend Pump` in Nocturne's V4 event map, and
`bolus`/`tempBasal` in `LoopAutomaticDoseRecommendation`. Both are upstream
one-liners; both currently discard real dosing records. Neither needs a
convention to be agreed first.

### Phase 3 — extension points where the data actually is. Cost: measured at 6.4–15.2%

`x-aid-extensions` as *documentation* costs nothing and should be adopted
now. As an *enforced* layout it costs 6.4%/15.2%/10.5%/0.0% of live
documents per collection — that is the migration, and it is now a number
rather than a fear.

The structural finding is more important than the convention: an extension
bag at a document's root does not protect a tree. `devicestatus` loses 56 of
166 paths to a typed model because `[JsonExtensionData]` sits on
`DeviceStatus` and on none of its nested classes. **Either every level gets
an extension point, or `devicestatus` is composed from separately-typed
resources.** The second is what `activity` already does.

### Phase 4 — record the configuration. Cost: new fields, no migration

The §2 gap. Concretely:

1. Agree a vendor-neutral location. `profile.loopSettings` is the existing
   precedent and the wrong name for a shared one.
2. Loop adds its eight behaviour switches; AAPS adds `maxIob` and
   `maxBasal`; Trio adds both halves.
3. Declare it in the spec, so it is a contract rather than another
   flattened subtree.

This is additive: no existing reader breaks, and the fields already exist on
every device.

### Phase 5 — new collections follow the `activity` pattern

One collection, a `type` discriminator, per-type payload fields, an
extension bag on the model. Shipped and working (§5.1 of the fidelity
report). Our own `aid-heartrate-2025.yaml` proposes a conflicting separate
`/heartrate` collection and should be reconciled to the shipped pattern.

### What should *not* be on this roadmap

Tenant-registered custom resource definitions, on current evidence. The long
tail this corpus shows is five leaf fields and one misspelling — thin
justification for a per-tenant schema store, per-tenant validators, and a
schema-migration story. Revisit if a controller maintainer names a new
*kind* of record with its own lifecycle.

## 5. New data, and delegation between agents

### 5.1 Structurally, new data changes little

Adding heart rate, steps, sleep, menstrual cycle or geolocation needs no new
architecture. The `activity` collection is already a polymorphic,
`type`-discriminated resource with an extension bag, and cgm-remote-monitor
already has the collection and the `api:activity:create` permission.

Three practical consequences, none architectural:

* **Rate and retention differ by orders of magnitude.** CGM is one reading
  per five minutes. Heart rate from a watch can be per-second. The
  `dbsize` and retention machinery assumes the former.
* **The `activity` name collision (§3) must be resolved before generated
  types make it permanent.**
* **`aid-heartrate-2025.yaml` conflicts with the shipped pattern** and
  should be reconciled rather than implemented.

### 5.2 For privacy, new data changes the category

This is where the answer stops being "no". Glucose and insulin are
sensitive. Menstrual-cycle data, precise geolocation and calendar contents
are sensitive in *different* ways: they identify, they reveal things about
people who never consented (a calendar names other people), and several
carry specific legal regimes that vary sharply by jurisdiction.

Combining them is the point — predicting dinners from a calendar, or
correlating sensitivity with cycle phase, is real clinical value — and
combination is also exactly what makes a dataset re-identifying. This work's
own experience is the small version of that: field *names* were safe to
publish, and it took five successive rules before field *values* were, with
each rule added because the previous set demonstrably leaked.

### 5.3 What exists today

| Capability | Status |
|---|---|
| Read permission granularity | **One bit.** The `readable` role is `*:*:read`; there is no per-collection, per-field or per-time-range read scope |
| Write permission granularity | Per collection (`api:treatments:create`, `api:activity:create`) |
| Identity | `enteredBy`, a free-text nickname, unverified |
| Delegation grants | Designed in `docs/10-domain/authority-model.md` — scopes, constraints, expiry, time windows — and **not implemented** |
| Time-bounded access | Concept exists in `nightscout-roles-gateway` (`scheduled_policies`, `connection_policies`) |
| Purpose limitation | Nothing anywhere |
| Audit of reads | Nothing. `srvCreated`/`srvModified` track writes only |

ADR-003 is a real constraint on any design here, and a deliberate one:
Nightscout does not implement credentials, on liability grounds, and treats
access as consent-granted rather than credential-proven. So delegation has
to ride on an external identity provider — which is what the roles gateway's
Mode B does — and cannot become a bespoke auth system.

### 5.4 What a delegation design would have to provide

Stated as requirements rather than a solution, because this is the part that
needs qualified review:

1. **Scoped reads, enforced in storage.** Today a delegated reader gets
   everything. The multitenancy work measured Postgres RLS at 0.3–0.6 ms
   overhead and showed it is fail-closed — an unbound connection returns
   zero rows, not everything. A read scope that is a storage predicate
   rather than an application filter is the only kind that survives a
   forgotten `WHERE`.
2. **Bounded queries.** §6.5 of the multitenancy discussion found `$regex`
   reaching MongoDB with no pattern guard, no index requirement and no
   `maxTimeMS`. **A read grant is a denial-of-service grant today**, before
   any privacy question is reached. Query profiles are a prerequisite for
   delegation, not a parallel workstream.
3. **Purpose and expiry as first-class, not documentation.** A grant for
   "meal prediction" should not read cycle data, and should stop working on
   a date. `authority-model.md` already models constraints and expiry for
   writes; reads need the same shape.
4. **Answers rather than data, where it suffices.** An agent predicting
   dinner needs *carb patterns by time of day*, not the treatment log. A
   derived-value grant is a smaller disclosure than a raw-read grant, and
   for AI agents in particular the difference is the whole risk.
5. **Read audit.** Delegation without a record of what was read is
   indistinguishable from a copy.
6. **Revocation that is real.** Once an agent has read raw data, revocation
   cannot un-read it. This argues for narrow, short-lived, derived grants
   over broad standing ones — and it is the single strongest argument for
   (4).
7. **Minimization at the boundary.** The de-identification machinery built
   here (`tools/nsschema/redact.py`, `scan_pii.py`) is a working precedent:
   a name denylist, a cardinality cap, value-shape rejection, suffix rules
   and cross-site corroboration, each added because the previous set leaked.
   Anything exporting to an agent needs an equivalent, and should expect to
   need several iterations.

### 5.5 What this evidence base can and cannot say

It **can** say that the read-permission model is one bit, that query cost is
unbounded, and that combining collections is what makes data identifying —
all measured or read from code. It **cannot** say what a correct consent
model looks like for cycle data in any given jurisdiction; that is a
question for counsel and for the people whose data it is, and this document
should not be read as having answered it.

## 6. What is not measured

* **The full settings surface of any controller** — §1.1. Only inputs that
  reach the dosing algorithm are inventoried.
* **Whether the absent configuration fields are stable enough to record.**
  A switch that changes between builds may need a version alongside it.
* **Anything about delegation in practice.** No implementation exists to
  measure; §5 is requirements, not results.
* **Rate and volume for physiological data.** §5.1's claim that retention
  assumptions break is reasoning from the collection interval, not a
  measurement.
* **AndroidAPS from data**, still.

## 7. References

* `make schema-dosing` → `reports/schema-census/dosing-inputs.json`
* `specs/nsschema/dosing-input-sources.yaml` — 60 inputs, two algorithms
* `specs/conformance/observability-profile.yaml` — who must upload what
* `specs/quirks/` — 17 measured deviations, with reader guidance
* `externals/LoopAlgorithm/Sources/LoopAlgorithm/AlgorithmInput.swift`
* `docs/10-domain/authority-model.md`, `docs/90-decisions/adr-003-no-custom-credentials.md`
* `externals/cgm-remote-monitor-official/lib/authorization/storage.js` — the role table
* [Multitenancy discussion](./nightscout-multitenancy-discussion-2026-09-09.md) §6.1 (RLS, measured), §6.5 (unbounded query cost)
