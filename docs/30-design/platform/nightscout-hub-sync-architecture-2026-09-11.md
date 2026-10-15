# A hub-and-spoke sync model for AID controllers

*Contributor-facing.* **Snapshot — describes 2026-09-11. Status: current as analysis; the design it sketches is carried forward by [PROPOSAL-controller-descriptions](PROPOSAL-controller-descriptions-2026-09-11.md) and [PROPOSAL-replay-fidelity-changes](PROPOSAL-replay-fidelity-changes-2026-09-11.md).** Current decisions: [execution plan §1](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#1-decisions). **Corrected in place 2026-10-12:** §3.1's description of `stateSpans` and the schema field list in §5.2 now match the schema as extended for D18 from [intent and workflow across the landscape](./nightscout-intent-workflow-landscape-2026-10-09.md) §9. **Also 2026-10-12:** §3.1 lists `extensions` and the D18 addendum grammar rules 1–5 (`SCHEMA-REG-EXT`). **Also 2026-10-12:** §3.5 specifies negotiation, D18 addendum rule 6 (`SPEC-REG-NEGOTIATE`): the capability document, the submit, update and retire contract, the fallback rule, authorisation with open questions, and the conformance cases. **Also 2026-10-14:** §3.5's ten open questions are decided ("Decisions"), with the contract changes they imply listed for `SPEC-REG-DECISIONS`; §5.2's kind/instance split is adopted as D19. **Also 2026-10-15:** §3.5 is amended for those decisions (`SPEC-REG-DECISIONS`): first-to-claim namespaces, binding to the creating subject, the owner's actions on `ns-tenant-admin` and the `blocked` state, the credential kind, carrier views and dual-write links, and refused typed writes; 53 conformance cases.

Date: 2026-09-11. Fifth in a series
with
[Typed schemas](./nightscout-typed-schema-evidence-2026-09-10.md),
[Extending the document model](./nightscout-extensibility-models-2026-09-10.md),
[devicestatus and profile fidelity](./nightscout-devicestatus-profile-fidelity-2026-09-10.md)
and
[Settings, extensibility and delegation](../tenancy/nightscout-configuration-and-delegation-2026-09-10.md).

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
| 4 | **A real replay consumer already works around this.** `oref-digital-twin` reads settings from *screenshots* with a vision model, or from AAPS's encrypted preference export, because Nightscout does not carry them. `max_iob` is in its `REQUIRED_SETTINGS` and is recorded by no controller anywhere | §4.1 |
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
* **stateSpans** — the intent kinds it exposes, one entry per kind: the slot
  it occupies and which slots coexist, its states and end reasons, the wire
  carrier today's documents use (eventType, identity, duration unit,
  indefinite sentinel, how "ended" is encoded), where the request and the
  applied effect are each recorded, the initiator vocabulary, the definitions
  it is made from, and which hub-originated intent the controller accepts.
  Each entry carries evidence marked `read` (from source) or `measured`. The
  2026-09-11 form was categories with states and a supersession rule; that
  form still validates. *(Corrected 2026-10-12.)*
* **composition** — how overlapping intents combine, declared as reported by
  the controller (`reportedBy: controller`, `hubComputes: false`), with where
  the result is published or `null`. Under D18 the hub records the result and
  does not compute it. *(Added 2026-10-12.)*
* **commands** — how remote commands reach the controller: transport, whether
  the hub is in the path, authorisation, expiry and acknowledgement.
  *(Added 2026-10-12.)*
* **replayInputs** — every dosing input it could supply, with `status` and a
  path; **an input it has but does not publish is declared with a null
  path**, which is what makes completeness measurable rather than guessed.
  An input may also carry a type (below). *(Typing added 2026-10-12.)*
* **settings** — the configuration snapshot it will publish, effective-dated.
  `fields` takes a name, as before, or a typed field declaration (below).
  *(Typing added 2026-10-12.)*
* **extensions** — controller-specific data, keyed by a reverse-DNS namespace
  the controller owns, each with its own version and typed fields. An extension
  or field without a type declaration is rejected. *(Added 2026-10-12.)*
* **cadence** and **queryProfile**

*Grammar rules (added 2026-10-12, `SCHEMA-REG-EXT`; D18 addendum, execution plan
§2.6.1).* Within `nightscout.dev/sync/v1` a reader ignores members it does not know:
it keeps them as written and does not interpret or serve them, so no object in the
schema is closed (`tools/nsschema/sync_model.py` `unknown_grammar_fields` lists them).
A field declaration carries `type` — a restricted JSON Schema fragment (`type`,
`enum`, `minimum`, `maximum`, `format`, `items`, `properties`, `required`; closed;
an object must list its properties) — or `typeRef` to a Nightscout-published
definition such as a ControllerSettings field, plus `unit`, `range`, `horizon`,
`sensitivity` (the two-axis label of `specs/sync/sensitivity.yaml`) and `evidence`.
A field with no label falls under `sensitivity.unlabelledPolicy`, `withhold` when
absent. `endedEncoding`, command `transport`, `replayInputs[].status` and the
discriminator `test` take a shared value or `{value: other, controllerTerm}`, and
`endReasons` gains `other`. Each `stateSpans` kind and each extension may declare
`version` or `versions` (`served`, one `stored`, optional lossless `mappings`);
without a mapping nothing is converted. Documents, kinds, fields, settings and
extensions may declare a `horizon` (`cycle`, `span`, `effective-dated`,
`definition`, `aggregate`) with its own cadence and retention, and `availability`
gains `experimental`. The generated registrations gained `typeRef` only where the
ControllerSettings definition was read from the controller's own algorithm family,
and horizons only for the `devicestatus` document (`cycle`) and `settings`
(`effective-dated`); `specs/sync/registrations/fixtures/example-testcontroller.yaml`
is a synthetic registration that uses every rule.

Worked registrations for Loop, Trio and AndroidAPS are in
`specs/sync/registrations/`, **generated from the census, the vendor
surfaces and the dosing-input map** rather than hand-written, so they cannot
claim more than was measured. `make schema-sync-model` regenerates them and
`--check` fails on drift.

The discriminator is structural on purpose. The free-text `device` string is
the field this work spent the most effort de-identifying, and it is not
reliable: one site's device strings read like a controller while its
treatments showed no automated dosing at all.

**Read the registration as an affordance, not a constraint.** §3.2 says a
controller never negotiates a query shape *at request time*; that is about
timing, not about who decides. What a controller may sync, how often, and
which filters it uses are **declared by the controller in its own
registration** — `cadence` and `queryProfile` are per-controller fields, not
hub policy. A controller with an idiomatic channel says so there. The hub's
job is to honour a declaration it can bound, not to impose a uniform shape.

**The catalogue is the default, and it is served.** The hub ships
registrations for controllers that have not declared one
(`specs/sync/registrations/`) and serves them at a well-known path, so the
common case needs no controller action at all — see the
[controller-descriptions proposal](./PROPOSAL-controller-descriptions-2026-09-11.md)
§2.1. Precedence is controller-published, then operator-declared, then
structurally inferred.

**What the registration describes is a controller *kind*, not a running
instance.** That distinction is the subject of §5.2 and is where this design
is least complete.

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

**And it does not need a registration to start.** A collection-agnostic
`GET /api/v3/history/{lastModified}` plus a single batch write gets the same
two-requests-per-cycle result on v3 today, with no registration, no new
version, and no controller-side model — `lastModified.js` already loops every
collection with a per-collection permission check and
`history/operation.js` is already generic in `opCtx.col`. That is the
cheapest first step and it is specified in the
[replay-fidelity proposal](./PROPOSAL-replay-fidelity-changes-2026-09-11.md)
§1, including the merged-cursor rule that makes it correct under per-collection
page limits.

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

### 3.5 Negotiation

*Added 2026-10-12 (`SPEC-REG-NEGOTIATE`; D18 addendum rule 6, execution plan §2.6.1).
Amended 2026-10-15 for the decisions of 2026-10-14 below (`SPEC-REG-DECISIONS`).
Specified, not implemented: no hub serves any of this.* The hub publishes what it supports;
the controller submits its controller-owned registration and reads back, per element, what
was accepted; for anything not accepted it writes the element's well-known carrier.

| file | what it is |
|---|---|
| `specs/sync/hub-capabilities.schema.json` | the capability document |
| `specs/sync/registration-submit.schema.json` | request, response, stored registration, fallback, refused-typed-write and conformance-case shapes |
| `specs/sync/conformance/*.yaml` | 53 synthetic conformance cases; both hubs implement against them |
| `tools/nsschema/negotiate.py` | a reference decision function that computes each case's expected response, stored registration, fallback and handling of a refused typed write. It checks that the cases are self-consistent; it is not a hub |
| `tools/nsschema/test_registration_negotiation.py` | the queue gate |

**The capability document: `GET /.well-known/nightscout/sync`.** One well-known suffix,
`nightscout` (RFC 8615), with one path per concern beside the catalogue at
`/.well-known/nightscout/controllers` ([controller descriptions](./PROPOSAL-controller-descriptions-2026-09-11.md)
§2.1). It has the catalogue's properties: unauthenticated, cacheable, and about the hub
software rather than a person. It is served on every host the hub answers; in
`TENANCY_MODE=multi` that is each tenant's host (Host → slug, D10), with the same
deployment-level content. **It lists no tenant's submitted registrations**, because which
controller a person uses is not public; a tenant's registrations are read with a credential
(below). Members:

| member | states |
|---|---|
| `grammar.versions[]` | each grammar major the hub reads (`apiVersion`, `major`) and the `minor` it implements. A registration carries no minor: within a major the hub ignores what it does not know (rule 1) |
| `grammar.interprets[]` | the grammar members the hub interprets, as dotted paths with `*` for an array item or map key (`spec.stateSpans.*.wire`); an entry covers its subtree. It must cover the members the contract reads (`apiVersion`, `kind`, `metadata.vendor`, `metadata.product`, `metadata.tier`, `spec.cadence`, `spec.documents.*.collection`, `spec.documents.*.decomposesTo`) |
| `horizons.classes[]`, `horizons.availability[]` | the horizon classes and availability values the hub stores (rule 5) |
| `typeFragment.keywords[]`, `typeFragment.formats[]` | the subset of the grammar's type-fragment keywords the hub can store, validate and index; must include `type` (rule 2) |
| `limits` | `maxRegistrationBytes` (RFC 8785 canonical JSON), `maxExtensions`, `maxFieldsPerExtension`, `maxTypeDepth` |
| `wellKnown.catalogue`, `wellKnown.kinds[]` | the well-known tier: each shipped registration's vendor, product, version range and `href` |
| `submit.href`, `submit.tiers`, `submit.permissions` | where a controller-owned registration is submitted, and the permissions a credential needs. Absent: the hub takes no submissions (for example, a feature flag is off) |

The document is must-ignore like the grammar: no object is closed, and its vocabularies
(horizon classes, availability, keywords, formats) are closed lists that match the grammar's,
which the gate checks.

**Elements.** The response reports per element, and the fallback is decided per element:

| element id | from | well-known carrier when not accepted |
|---|---|---|
| `stateSpans/<kind, else category>` | `spec.stateSpans[]` | its `wire` (`write: carrier`); `none` when `wire` is null |
| `extensions/<namespace>` | `spec.extensions` | its `carrier`; `none` when it declares none |
| `settings.fields/<name>` | a `settings.fields[]` entry with `type` or `typeRef` | written as today, name-only (`write: untyped`) |
| `replayInputs/<input>` | a `replayInputs[]` entry with `type` or `typeRef` | written as today, name-only (`write: untyped`) |

Everything else in the registration (documents, cadence, composition, commands, query
profile, sensitivity, untyped settings and inputs) belongs to the registration as a whole.

**Identity and resource.** A registration's identity within a tenant is `metadata.vendor`
and `metadata.product`. `versionRange` is an attribute, not identity: a new release updates
the same registration, and older model versions stay served under rule 4. One registration
is the resource `<submit.href>/<vendor>/<product>` (each segment percent-encoded):

| method | who, where | meaning | precondition (required) |
|---|---|---|---|
| `PUT` | controller, data listener | submit: create, or update | `If-None-Match: *` to create; `If-Match: <etag>` to update |
| `GET` | controller, data listener | read the stored registration with its current element results, binding and credential kind | none |
| `DELETE` | controller, data listener | retire | `If-Match: <etag>` |
| `DELETE` | owner, `ns-tenant-admin` | retire | `If-Match: <etag>` |
| `POST …/block` | owner, `ns-tenant-admin` | block | `If-Match: <etag>`; `If-None-Match: *` when nothing is stored |
| `POST …/unblock`, `…/release`, `…/transfer`, `…/free-namespaces` | owner, `ns-tenant-admin` | see "The owner's actions" | `If-Match: <etag>` |

The owner's paths are proposals: the admin listener's registrations path and the action
segments are not settled. In `single` mode there is one listener, and `API_SECRET` there may
perform every owner action (decision 3).

**Order of checks.** (1) authorisation (403) — the permission, then the binding: a registration
is bound to the credential that created it, and any other credential that updates or retires it
is refused `not-registration-owner` before any precondition is evaluated; an owner action is
authorised by its listener (`ns-tenant-admin`, or `single` with `API_SECRET`) and refused
`not-authorised` elsewhere; (2) preconditions — none sent is 428, a failed
one is 412 with the current etag and state, and retiring an identity with nothing stored is 404 (RFC 9110 §13.2.1 evaluates preconditions after
authorisation and before the content); then the owner's block: a write to a blocked identity is
403 `blocked-by-owner`. The block is checked after the preconditions so a controller holding the
etag from before the block gets 412, whose `current.state` says `blocked`. A pre-emptive block
stores no registration, so a create's `If-None-Match: *` passes and the block answers 403;
(3) the registration as a whole — `apiVersion` not
among `grammar.versions` (`unsupported-grammar-major`), wrong `kind` or a grammar-invalid
registration outside `spec.extensions` (`invalid-registration`), identity differing from the
resource (`identity-mismatch`), a tier other than `controller-owned` (`wrong-tier`), over
`maxRegistrationBytes` (413) or `maxExtensions` (`limit-exceeded`) — each rejects the whole
registration (422 unless stated) and stores nothing; (4) each element.

**Element results.** `accepted`; `accepted-with-ignored-members`, with the ignored members
as dotted paths; or `rejected`, with reasons. Ignored members are those the grammar does not
define (`tools/nsschema/sync_model.py` `unknown_grammar_fields`) plus those `interprets` does
not cover; they are kept as written and not interpreted (rule 1). Ignored members outside
any element are listed at registration level. An element is not accepted when a member that
defines it is ignored (`not-interpreted`): a kind's `category`; an extension's `fields`,
`version`/`versions` and each field's `name`, `type`, `typeRef`; a typed setting's or input's
name and type. Otherwise an element is rejected for: `namespace-not-owned` (only when the
credential has stated namespace roots, an optional hub restriction; decision 1),
`namespace-claimed` (another registration on the tenant holds it: declares it and the owner
has not freed it, whatever that registration's state), `untyped-extension`,
`unsupported-type-keyword` (a keyword or format outside `typeFragment`, including in a
`typeRef` target), `limit-exceeded` (`maxFieldsPerExtension`, `maxTypeDepth`),
`invalid-element` (an extension that fails the grammar), `version-plan-invalid`,
`unsupported-availability`, `unsupported-horizon`. Declared availability and horizons are
checked only where the hub interprets them. Reason codes are an open vocabulary (`other` with
the hub's `term`); `detail` is for people and is not compared by the conformance cases.
Outcome: `accepted` when every element is accepted, `partial` when at least one is rejected —
both store the registration as written (201 on create, 200 on update). An accepted element may
also carry `carrierView`: `served` when the hub serves older readers a projected, read-only view
of its typed records in the carrier's shape, `not-served` or absent when it does not (decision
7; how a hub decides, and the view's mapping, are `SPEC-REG-INSTANCE`'s). `carrierView` is an
open vocabulary; a value the controller does not know is not accepted.

**Binding and credential kind** (decisions 3 and 4). A create or update binds the registration
to the credential that wrote it: `boundTo: {kind: subject, subject: <opaque id>}`, never the
token, so a token rotated on the same subject changes nothing; or `{kind: api-secret}` for the
shared secret in single mode, which any holder of the secret presents. The stored registration
also records `credentialKind` (`subject`, `api-secret`, or `other` with the hub's term), the
kind of credential that last created or updated it; both are returned with the registration.
`API_SECRET` against a subject-bound registration is `not-registration-owner` on the data path.
A released registration (`boundTo: null`) is bound by the next credential with the permission
that updates it, even with identical content (200, not a no-op). Readers attribute typed
records to the registration and its bound credential: a namespace string proves nothing about
authorship. `SPEC-REG-INSTANCE` binds instances; this binding leaves room for that.

**Concurrency and idempotency.** The etag is `sha256:` and the hex SHA-256 of the RFC 8785
canonical JSON of `{"registration": <as submitted>, "state": <active|retired|blocked>}`
(`registration` is null for a pre-emptive block), so it changes on every change of content or
state, including a block and an unblock. The binding, the credential kind and freed namespaces
are stored beside the registration and are not in the etag: a release, a transfer or freeing
namespaces leaves it unchanged, and the precondition on those owner actions guards against
acting on content or a state the owner has not read. A request whose content and state are already stored
succeeds as a no-op (`noop: true`, 200, the stored etag), so a create retried after a lost
response does not fail (RFC 9110 §13.1.1 allows a 2xx for `If-Match` when the change has already been
applied; the contract applies the same rule to a create's `If-None-Match`). A stale `If-Match` with different content is 412 `stale-etag`; `If-None-Match: *`
over different content is 412 `registration-exists`. A hub evaluates a stored registration
against its current capabilities on every read, so an element's result can change after a hub
upgrade; the stored registration and its etag do not.

**Retire.** The controller the registration is bound to retires it (D18), with
`api:registrations:delete`; namespace roots do not decide it (decision 4). The tenant owner may
also retire it (decision 5). Retiring sets the state to `retired`,
changes the etag and keeps the declaration and the binding, frozen: data already stored under it stays stored
and readable as declared, and no typed write is accepted for its kinds or extensions. Its
namespaces stay claimed while it is stored, until the owner frees them. A later `PUT` with the
retired etag reactivates it; a namespace the owner freed is claimed again on reactivation only
if no other registration holds it by then, and otherwise stays freed and that extension is
rejected `namespace-claimed`.
The controller writes its carriers from the moment it retires.

**The owner's actions** (decision 5; `ns-tenant-admin`, or `API_SECRET` in single mode). The
owner may retire, block, unblock, release, transfer and free namespaces, and never edits a
registration's content (an owner `PUT` is 403 `not-authorised`). An action other than retire
answers outcome `applied` with the registration after it; a request for what is already the case
is a no-op.

- **Block** sets the state to `blocked` and records the state it interrupted (`blockedFrom`); the
  etag changes, the declaration and binding are kept, and data already stored stays frozen as on
  retire. The controller's writes and typed writes are refused 403 `blocked-by-owner` and it
  writes its carriers. With `If-None-Match: *` the owner blocks an identity with nothing stored
  (a pre-emptive block, stored with no registration); a create for it is then 403
  `blocked-by-owner`.
- **Unblock** restores the state the block interrupted: `active`, or `retired` if the
  registration was retired before the block; unblocking a pre-emptive block removes it. Unblocking
  never reactivates a retired registration; the controller does that with a `PUT`, as above.
  The owner unblocks before retiring a blocked registration (409 `blocked-by-owner` otherwise).
- **Release** unbinds the registration (`boundTo: null`); the next credential with the permission
  that updates it is bound to it. **Transfer** binds it to a named subject. Neither changes the etag.
- **Free namespaces** applies to a retired registration only (409 `not-retired` otherwise): its
  namespaces are no longer held by it, so another registration may claim them. The declaration
  stays as written and data stored under it stays readable.

**Fallback (the controller's side).** An element is written through the typed API only when
the response to *this* registration has outcome `accepted` or `partial` and the element's
result is `accepted` or `accepted-with-ignored-members`. Everything else — a rejected
element, an element result, reason or `carrierView` the controller does not know, a rejected
registration, a failed precondition, a retired or blocked registration, no response (a submit
answered 429 or 503 is no response), no capability document, no
`submit`, or a grammar major the hub does not list — falls back per the elements table. An
accepted element whose `carrierView` is `served` is written typed only; one whose view is not
served is written typed only, or typed and as its carrier when the element declares
`dualWriteLink` (decision 7): the dotted paths of the controller's record id in the typed record
(`typedIdPath`) and in the carrier (`carrierIdPath`), so counting and de-duplication follow the
link. `SPEC-REG-INSTANCE` scopes the link by instance and specifies the view's mapping. A
controller that depends on an ignored member may treat that element as not accepted; the
conformance cases assume it does not. The capability document carries everything the
response depends on except the tenant's stored registrations (with their bindings and blocks),
the credential's grants and whether the hub serves a carrier view of an element, so
a controller can predict most of the result before it submits; the response is authoritative.

**Re-checking and refused typed writes** (decision 8). A controller reads the capability
document and its registration at launch and after a controller release; never on a timer and
never because a request was refused, so an overloaded hub is not met with a surge of reads. A
typed write refused for load — 429 or 503, with or without `Retry-After` — is retried with
backoff (no sooner than `Retry-After` when sent); it is not written as its carrier and the
record is not dropped. Any other refusal of a typed write is definite: `blocked-by-owner`, a
retired or missing registration, a typed route answering 404 after a hub rollback, or a status
the controller does not know. The controller sends that record as its carrier and treats the
element as not accepted until its next re-check. The cases model this as `typedWrite` (the
refusal) and `expected.typedWrite` (`retry-backoff` or `carrier-this-record`, `recheck: false`,
and the write plan afterwards).

| | older hub | newer hub |
|---|---|---|
| **older controller** | no capability document, no registration: today's documents (`older-hub-older-controller`) | the controller submits nothing; the hub's well-known registration describes its writes by structural discriminator and wire carrier (`newer-hub-older-controller`) |
| **newer controller** | no capability document, or no `submit`, or its grammar major not listed: it submits nothing and writes every element as its carrier (`older-hub-no-capabilities`, `hub-without-submit`, `rejected-unsupported-grammar-major`) | typed registration, extensions and versions; per-element fallback for what is not accepted (the remaining cases) |

**Authorisation.** What follows from D13–D17, and what does not:

- **The submitter is the controller, a device.** Under D17 row 1 a device holds the native
  per-tenant credential, never Ory; so submit, update, read and retire are on the data
  listener (`ns-api`, and `single`), with that credential. In `TENANCY_MODE=multi` there is
  no deployment secret (D13); the credential's token is signed with the tenant's key (D14),
  so a registration is per tenant and a token for tenant A cannot register on tenant B. A
  controller on two tenants registers twice. In single mode `API_SECRET` may also register
  (decision 3); the registration records `credentialKind: api-secret` and is bound to the
  shared secret.
- **Permission and binding.** Submitting needs `api:registrations:create` and retiring needs
  `api:registrations:delete`, shiro-style like the existing `api:<collection>:<action>`
  permissions, granted by the tenant owner to the controller's subject on `ns-tenant-admin`
  (D16). The names are proposals. Updating and retiring also need the binding: the subject the
  registration is bound to, or the shared secret for a registration bound to it (decision 4).
- **Namespaces: first to claim, per tenant** (decisions 1 and 2). A credential with no stated
  namespace roots may claim any namespace no other registration on the tenant holds. A hub may
  also restrict a credential to owner-granted roots: a registration may then declare an
  extension namespace equal to or below one of them
  (`com.example` covers `com.example.negotiation.targets`; `com.examplefoo` does not), else
  `namespace-not-owned`. Either way a namespace another registration on the tenant holds is
  `namespace-claimed`. Readers attribute typed records to the registration and its bound
  credential, never to the namespace string.
- **The owner.** On `ns-tenant-admin` (D16; the owner's authentication there is D17 row 2) the
  tenant owner retires, blocks, unblocks, releases, transfers and frees a retired
  registration's namespaces; in single mode `API_SECRET` may do the same on `single`. An owner
  action on the data listener is 403 `not-authorised`.
- **Storage.** Registrations are tenant data: per-tenant, under RLS (D3), never in the
  public capability document. Authorisation is per tenant, as the D13 amendment requires.

**Decisions (maintainer, 2026-10-14).** The ten questions D13–D18 left open. Where a decision
changes the contract above, the change is listed; each was applied to the contract above, the
schemas and the cases on 2026-10-15 (`SPEC-REG-DECISIONS`). Question 6 became D19 ([execution plan §2.6.2](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#262-d19--definitions-and-instances-maintainer-2026-10-14)), queued as `SPEC-REG-INSTANCE`.

1. **Where namespace roots come from: first to claim.** A credential with
   `api:registrations:create` may claim any namespace no registration on the tenant holds; a
   second claimant is rejected `namespace-claimed`, as now. Owner-granted roots remain an
   optional restriction a hub may support (`namespace-not-owned` stays); a verified client
   identity (`software_id`) may later restrict further. Basis: `(vendor, product)` is already
   self-asserted and first to claim (412 `registration-exists`), the owner already chose the
   credential, and losing a claim falls back to carriers. A namespace string proves nothing
   about authorship: readers attribute typed records to the writing registration and
   credential. *Change:* a submitter without stated roots may claim any unclaimed namespace. (done 2026-10-15, `SPEC-REG-DECISIONS`)
2. **Scope: per tenant**, as the cases assume. A deployment-wide claim would let one tenant
   block another and reveal another tenant's controller. Readers that span tenants interpret a
   field by the declaration carried with it, not by its namespace. The community may keep a
   published list of namespace conventions, as a record of use, never a check. DNS
   verification, if ever added, labels a claim as verified rather than gating it.
3. **`API_SECRET` in single mode may register.** The hub records the kind of credential that
   registered, and the owner's admin view shows registrations made with the shared secret;
   documentation steers controllers toward subject tokens. Multi mode has no deployment secret
   (D13). *Change:* the stored registration records its credential kind. (done 2026-10-15, `SPEC-REG-DECISIONS`)
4. **A registration is bound to the subject that created it**, not to a token, so token
   rotation needs nothing. Another subject is refused 403 `not-registration-owner`. The owner
   may release or transfer a registration to another subject. A registration made with
   `API_SECRET` is bound to the shared secret. *Change:* new reason and case; retire is
   authorised by subject binding, and namespace ownership no longer decides it. (done 2026-10-15, `SPEC-REG-DECISIONS`)
5. **The owner may retire, block and unblock, never edit.** A block makes the hub refuse that
   `(vendor, product)` on the tenant (`blocked-by-owner`); the controller writes its carriers,
   data already stored stays frozen as on retire, and unblocking restores it. The owner may
   also free a retired registration's namespaces. Accepting is already the hub's side of
   negotiation, so a block does not change what the controller declares (D18). *Change:* the
   owner as a second retirer, the block state and its reason, and namespace release. (done 2026-10-15, `SPEC-REG-DECISIONS`)
6. **Two live releases or copies on one tenant:** D19. The definition (what data means) and the
   instance (which copy is connected, in which roles) are separate resources.
7. **Typed and carrier for the same intent.** A registered instance writes typed records only
   for accepted elements, and the hub serves older readers a declared, read-only, labelled view
   in today's shapes (D19 rule 8). Writing both, linked by (instance, the controller's record
   id), is for elements with no declared carrier mapping and for migration; counting follows
   the link. *Change:* the fallback rule gains the view; a dual-write element declares it. (done 2026-10-15, `SPEC-REG-DECISIONS`, as `carrierView` and `dualWriteLink`; the view's mapping and the instance-scoped link are `SPEC-REG-INSTANCE`'s)
8. **Re-checking: at launch and after a controller release.** A lease renewal does not re-read
   the capability document. A refusal does not trigger a re-check, so an overloaded hub is not
   met with a surge of reads: a 429 or 503 is retried with backoff and is not a fallback; a
   definite refusal (`blocked-by-owner`, a retired or missing registration, a typed route
   answering 404 after a hub rollback) sends that record as its carrier, and the element is
   treated as not accepted until the next re-check. *Change:* the fallback rule distinguishes
   load refusals from definite ones. (done 2026-10-15, `SPEC-REG-DECISIONS`)
9. **Retired data stays readable while it is stored.** A definition is kept while any stored
   record references it; each record's declared horizon retention decides when the record
   goes (D19 rule 9).
10. **Which hub first: cgm-remote-monitor.** The specifications are then proposed to the
    community for adoption by Nocturne and the open-source AID controllers
    (`HUB-REG-NOCTURNE`, `PROPOSAL-REG-CONTROLLERS`).

**The cases.**

| case | cell | outcome |
|---|---|---|
| `accepted` | newer/newer | 201 accepted; both elements typed — the control for most rejections |
| `accepted-with-ignored-members` | newer/newer | hub v1.0 without document horizons; unknown members listed and kept |
| `rejected-untyped-extension` | newer/newer | extension rejected; kind typed, extension to its carrier |
| `rejected-type-keyword-outside-subset` | newer/newer | hub has no `minimum`/`maximum`; extension rejected |
| `rejected-namespace-not-owned` | newer/newer | credential's root does not cover the namespace |
| `rejected-namespace-claimed` | newer/newer | another registration on the tenant declares the namespace |
| `rejected-unsupported-availability` | newer/newer | experimental kind on a hub that stores no experimental kinds |
| `extensions-not-interpreted` | newer/newer | hub does not interpret `spec.extensions` |
| `rejected-limit-exceeded` | newer/newer | over `maxExtensions`; rejected whole |
| `not-authorised` | newer/newer | no `api:registrations:create`; 403 |
| `rejected-unsupported-grammar-major` | newer/older | v2 registration to a v1 hub; 422, every element to its carrier |
| `older-hub-no-capabilities` | newer/older | no capability document; nothing submitted |
| `hub-without-submit` | newer/older | capability document without `submit`; nothing submitted |
| `newer-hub-older-controller` | older/newer | no registration; well-known registration describes the writes |
| `older-hub-older-controller` | older/older | nothing negotiated |
| `update-accepted` | newer/newer | `If-Match` current etag; 200 |
| `update-stale-etag` | newer/newer | 412 `stale-etag` with the current etag; carriers until resubmitted |
| `create-retry-noop` | newer/newer | identical create retried; 200 `noop` |
| `create-exists` | newer/newer | create over different content; 412 `registration-exists` |
| `retire` | newer/newer | 200 retired; declaration kept; carriers from then on |
| `retire-not-authorised` | newer/newer | no `api:registrations:delete`; 403. *Changed 2026-10-15:* until then it asserted that retiring needs roots covering every namespace (decision 4 removed that rule) |
| `accepted-first-to-claim` | newer/newer | no stated roots; unclaimed namespace accepted (decision 1) |
| `rejected-namespace-claimed-first-to-claim` | newer/newer | no stated roots; namespace held by another registration; `namespace-claimed` |
| `rejected-namespace-claimed-retired` | newer/newer | the holder is retired but has not had its namespaces freed; `namespace-claimed` |
| `namespace-claimed-after-free` | newer/newer | the owner freed the retired holder's namespace; accepted |
| `accepted-api-secret-single` | newer/newer | `API_SECRET` on `single`; `credentialKind: api-secret`, bound to the secret (decision 3) |
| `update-token-rotated` | newer/newer | bound subject, new token; 200 (decision 4) |
| `update-not-registration-owner` | newer/newer | another subject; 403 `not-registration-owner` |
| `update-api-secret-bound` | newer/newer | secret-bound registration updated with the secret; 200 |
| `update-api-secret-not-owner` | newer/newer | `API_SECRET` against a subject-bound registration; 403 `not-registration-owner` |
| `retire-not-registration-owner` | newer/newer | another subject retires; 403 `not-registration-owner` |
| `retire-roots-not-required` | newer/newer | bound subject without covering roots retires; 200 |
| `owner-retire` | newer/newer | owner on `ns-tenant-admin`; 200 retired (decision 5) |
| `owner-action-on-data-listener` | newer/newer | the same on `ns-api`; 403 `not-authorised` |
| `owner-block` | newer/newer | `blocked`, `blockedFrom: active`, etag changes |
| `owner-block-api-secret-single` | newer/newer | `API_SECRET` on `single` blocks; applied |
| `blocked-update-stale-etag` | newer/newer | controller's pre-block etag; 412, `current.state: blocked` |
| `blocked-by-owner` | newer/newer | controller's current etag on a blocked registration; 403 `blocked-by-owner` |
| `owner-block-pre-emptive` | newer/newer | nothing stored, `If-None-Match: *`; 201, stored with no registration |
| `blocked-pre-emptive-create` | newer/newer | create after a pre-emptive block; 403 `blocked-by-owner` |
| `owner-unblock` | newer/newer | back to `active`, with the pre-block etag |
| `owner-unblock-retired` | newer/newer | retired before the block; stays `retired` |
| `owner-release` | newer/newer | `boundTo: null`; etag unchanged |
| `released-update-binds` | newer/newer | another subject updates a released registration and is bound to it |
| `owner-transfer` | newer/newer | bound to a named subject; etag unchanged |
| `owner-free-namespaces` | newer/newer | retired registration's namespaces freed |
| `owner-free-namespaces-not-retired` | newer/newer | active registration; 409 `not-retired` |
| `accepted-dual-write-view-not-served` | newer/newer | no carrier view, `dualWriteLink` declared; typed and carrier (decision 7) |
| `accepted-dual-write-view-served` | newer/newer | `carrierView: served`; typed only |
| `typed-write-load-503` | newer/newer | typed write 503, no `Retry-After`; retry with backoff, no carrier, no re-check (decision 8) |
| `typed-write-load-429-retry-after` | newer/newer | typed write 429 with `Retry-After: 30`; retry after it |
| `typed-write-blocked-by-owner` | newer/newer | typed write 403 `blocked-by-owner`; that record as its carrier, no re-check |
| `typed-write-route-404` | newer/newer | typed route 404 after a rollback; that record as its carrier, no re-check |

The 21 cases that predate the decisions keep their outcomes; each now states the submitter's
subject and credential kind, and each stored registration its identity, binding and credential
kind (measured 2026-10-15: the reference reproduces every earlier expected outcome with only
those members added).

## 4. Replay, and why physicians cannot see the settings

### 4.1 The workaround that proves the gap

`externals/oref-digital-twin` is an advisory tool that replays the real
`determine-basal` under altered settings. To do that it needs the settings.
It cannot get them from Nightscout, so it gets them from **a screenshot, via
a vision model**, or from AAPS's client-side-decrypted preference export.
Its own settings module says so plainly, and its replay code names the one
input it cannot proceed without:

> `REQUIRED_SETTINGS = ("max_iob",)`

`max_iob` is the input measured as recorded by no controller anywhere. A
serious replay tool, written independently, hits the gap this series
measured. That is the physician complaint in code form.

**One correction to an earlier reading of this file.** Its module docstring
also lists `currenttemp` and insulin `activity` as unrecoverable from
devicestatus and approximates both. Neither claim survives measurement:
`activity` is **already read** by its own `_iob_data_from_cycle` when
`openaps.iob.activity` is present, and `currenttemp` **is published** —
`openaps.iob.lastTemp` carries `rate`, `duration` and `started_at` on 73,891
documents, the dosing map classifies it as *recorded*, and `OBS-OREF-006`
checks for it. The tool still substitutes a zero temp basal. That is a
consumer fix, not a Nightscout gap, and it is the cheapest fidelity gain
identified anywhere in this series — see the
[replay-fidelity proposal](./PROPOSAL-replay-fidelity-changes-2026-09-11.md) §6.

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

### 5.1 Spans, not point events

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

### 5.2 Liveness and channel ownership — open here, already drafted upstream

*(2026-10-14: answered by D19 — [execution plan §2.6.2](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#262-d19--definitions-and-instances-maintainer-2026-10-14) — which adopts the RFC's kind/instance split with the reconciliation's identity correction and settles two writers on one site; what follows is the map as written on 2026-09-11.)*

**This section is an open question, not a design.** It is written as a
reconciliation target because the honest finding is that cgm-remote-monitor
has drafted most of it already, and this series had not noticed.

> **The reconciliation has since been done.** This section remains the map;
> the specific edits it implies — twelve of them, across four upstream files,
> plus five corrections the corpus supplies — are in
> [Reconciling the agentic control plane RFC](../tenancy/nightscout-control-plane-reconciliation-2026-09-11.md).

The question is real and this design does not answer it. A registration says
what a controller *kind* writes. It does not say which controller is
*running right now*, which one owns a given channel, or what to do when two
of them write. §7 records "cursor semantics under concurrent writers" as
unmeasured, and that is the whole of what this series has to say on the
subject.

**`cgm-remote-monitor/docs/proposals/` (added 2026-01-01) already carries the
missing half**, and it carves the problem at a joint this series did not:

| Their concept | What it is | Our nearest thing | Verdict |
|---|---|---|---|
| `ControllerKindDefinition` | Per *product*: supported features, pumps, CGMs, `eventCapabilities.minimalEventSet` | `ControllerStateModel` (`specs/sync/`) | **Complementary, not competing.** Theirs says what a controller *can do*; ours says what it *writes*. Neither contains the other's half |
| `ControllerInstanceRegistration` | Per *running instance*: `instanceId`, `pumpBinding.connectedSince`, `cgmBinding`, `registeredAt`, **`lastSeenAt`** | **nothing** | This *is* liveness, and we have no equivalent |
| `CapabilitySnapshot` | Liveness over time: `pumpConnected`, `closedLoopEnabled`, `suspended`, `lastLoopTime`, reservoir, battery | `StateSpan` categories `PumpConnectivity`, `PumpMode` | Same phenomenon, different container — theirs a point snapshot, ours a span. Reconcilable; a span is the stronger form for replay |
| `bridge-rules.md` detection | `if (devicestatus.loop) … if (devicestatus.openaps) …` | our structural discriminator | **Independently identical.** Two efforts reached the same answer, which is the strongest evidence in this document that it is the right one |
| Authority hierarchy, composition, delegation grants | `conflict-resolution.md` | `docs/10-domain/authority-model.md` | **Duplicated.** Near-identical authority levels, conflict scenarios and grant structures exist in both trees. This is the clearest single place to converge |
| Global monotonic event cursor | `assignEventCursor`, `/events?cursor=` | §3.2's opaque server watermark | Same role, different implementation. Whether they are one cursor is an open design question |

**The kind/instance split is the answer to the liveness question**, and it is
theirs, not ours. A catalogue entry describes the kind; liveness belongs to
the instance. Adopting that split costs this series one new field group in
`specs/sync/controller-state-model.schema.json` — which today has
`cadence`, `documents`, `stateSpans`, `composition`, `commands`,
`replayInputs`, `settings`, `queryProfile`, `sensitivity`, `extensions` and nothing about
instances at all. (`composition` and `commands` added 2026-10-12; `extensions` added
2026-10-12 by `SCHEMA-REG-EXT`, see §3.1.)

**Two corrections we can offer back, because we measured them.** Both are
small and both are the kind of thing only a corpus can catch:

1. `bridge-rules.md` detects Trio with `if (devicestatus.trio) return 'trio'`.
   **No document in the corpus carries a top-level `trio` key.** The observed
   top-level `devicestatus` objects are `loop`, `openaps`, `pump`, `uploader`
   and `override`. Trio is an oref derivative and writes under `openaps` —
   which our own generated `specs/sync/registrations/trio.yaml` and
   `androidaps.yaml` both confirm, since **both discriminate on `openaps` and
   are therefore not distinguishable from each other at the top level.** That
   is a limit in our work as much as a bug in theirs, and it should be stated
   in both.
2. `CapabilitySnapshot` sets `controllerInstanceId: devicestatus.device` —
   the free-text device string. That is the field this series found least
   reliable (§3.1), and using it as an instance identity makes liveness
   inherit the unreliability. If instances need identity, it should not come
   from that string.

**What should happen before anyone builds this.** Ask, rather than design:
the `integration-questionnaire.md` in that same directory is addressed to
Loop, AAPS and Trio implementers and asks a version of this question already.
Writing a competing liveness model before answering it would be the exact
duplication this work exists to prevent.

## 6. Sequencing

Ordered so nothing depends on an unmade decision, and each step is useful
alone.

1. **Publish settings.** Additive, no migration, no new API. Closes the
   physician complaint and the digital-twin workaround. The registrations
   name the fields, and for Loop it is **eight more keys in the
   `loopSettings` block it already writes on 200 of 202 profile documents** —
   see the [replay-fidelity proposal](./PROPOSAL-replay-fidelity-changes-2026-09-11.md) §3.
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
  ordering under that load is unexamined. `conflict-resolution.md` upstream
  proposes optimistic locking on `srvModified` plus a global monotonic
  cursor; neither is measured here, and whether that cursor and §3.2's
  watermark are the same object is undecided (§5.2).
* **Liveness and channel ownership entirely.** No measurement, no design —
  see §5.2. Nothing in the corpus can say which controller was running when,
  because nothing records it. The upstream `ControllerInstanceRegistration`
  is the nearest thing to an answer, and its instance identity is taken from
  the `device` string, which §3.1 found unreliable — see the
  [reconciliation](../tenancy/nightscout-control-plane-reconciliation-2026-09-11.md) §3.3.
* **Anything about AndroidAPS from data.** Still no AAPS closed-loop site in
  the corpus.
* **The registration's own lifecycle.** How a controller updates a
  registration when it ships a new build, and what the hub does with
  in-flight data under the old one. *(2026-10-12: specified in §3.5 — update
  by `If-Match`, retire keeps stored data and the frozen declaration. Not
  measured: no hub implements it.)*

## 8. References

* `make schema-sync-cost` → `reports/schema-census/sync-cost.json`
* `make schema-sync-model` → `specs/sync/registrations/{loop,trio,androidaps}.yaml`
* `specs/sync/controller-state-model.schema.json`
* `specs/sync/hub-capabilities.schema.json`, `specs/sync/registration-submit.schema.json`, `specs/sync/conformance/` — negotiation (§3.5)
* `specs/conformance/observability-profile.yaml` — the obligations a registration would formalise
* `externals/oref-digital-twin/` — `DESIGN.md` §2, `replay/inputs.py`, `settings/schema.py`
* Nocturne: `Core.Models/StateSpan.cs`, `API/Services/V4/TreatmentDecomposer.cs`
* AAPS `core/nssdk/.../NightscoutRemoteService.kt`; Loop `NightscoutKit/NightscoutClient.swift`; Trio `Sources/Services/Network/Nightscout/NightscoutAPI.swift`
* cgm-remote-monitor `lib/api3/` — `lastModified`, `{collection}/history/{lastModified}`
