# A hub-and-spoke sync model for AID controllers

*Contributor-facing.* **Snapshot — describes 2026-09-11. Status: current as analysis; the design it sketches is carried forward by [PROPOSAL-controller-descriptions](PROPOSAL-controller-descriptions-2026-09-11.md) and [PROPOSAL-replay-fidelity-changes](PROPOSAL-replay-fidelity-changes-2026-09-11.md).** Current decisions: [execution plan §1](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#1-decisions). **Corrected in place 2026-10-12:** §3.1's description of `stateSpans` and the schema field list in §5.2 now match the schema as extended for D18 from [intent and workflow across the landscape](./nightscout-intent-workflow-landscape-2026-10-09.md) §9. **Also 2026-10-12:** §3.1 lists `extensions` and the D18 addendum grammar rules 1–5 (`SCHEMA-REG-EXT`). **Also 2026-10-12:** §3.5 specifies negotiation, D18 addendum rule 6 (`SPEC-REG-NEGOTIATE`): the capability document, the submit, update and retire contract, the fallback rule, authorisation with open questions, and the conformance cases. **Also 2026-10-14:** §3.5's ten open questions are decided ("Decisions"), with the contract changes they imply listed for `SPEC-REG-DECISIONS`; §5.2's kind/instance split is adopted as D19. **Also 2026-10-15:** §3.5 is amended for those decisions (`SPEC-REG-DECISIONS`): first-to-claim namespaces, binding to the creating subject, the owner's actions on `ns-tenant-admin` and the `blocked` state, the credential kind, carrier views and dual-write links, and refused typed writes; 53 conformance cases. **Also 2026-10-15:** §3.6 specifies D19 (`SPEC-REG-INSTANCE`): content-addressed definitions, leased instances, channel roles with provenance and one source of record, labels under `dev.nightscout/` (corrected from D19's `nightscout.dev/`), read selection, the projected view for older readers and retention; 86 instance cases, and the 26 accepted or partial §3.5 cases gained `definitionId`. §3.5's file table said 53 cases after the amendment that made them 55; corrected in place.

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
| `specs/sync/conformance/*.yaml` | 55 synthetic conformance cases (53 until the 2026-10-15 amendment; corrected 2026-10-15); both hubs implement against them. D19's are under `instances/` (§3.6) |
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
7; how a hub decides, and the view's mapping, are `SPEC-REG-INSTANCE`'s — specified in §3.6 on 2026-10-15). `carrierView` is an
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
authorship. `SPEC-REG-INSTANCE` binds instances; this binding leaves room for that (§3.6: an instance is bound to the subject that created it).

**Concurrency and idempotency.** The etag is `sha256:` and the hex SHA-256 of the RFC 8785
canonical JSON of `{"registration": <as submitted>, "state": <active|retired|blocked>,
"boundTo": <binding or null>}` (`registration` and `boundTo` are null for a pre-emptive block),
so it changes on every change of content, state or binding, including a block, an unblock, a
release and a transfer; two owner actions racing on one registration therefore meet a 412
(maintainer, 2026-10-15). The credential kind and freed namespaces are stored beside the
registration and are not in the etag: freeing namespaces leaves it unchanged. A request whose content and state are already stored
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
answered 429 or any 5xx is no response), no capability document, no
`submit`, or a grammar major the hub does not list — falls back per the elements table. An
accepted element whose `carrierView` is `served` is written typed only; one whose view is not
served is written typed only, or typed and as its carrier when the element declares
`dualWriteLink` (decision 7): the dotted paths of the controller's record id in the typed record
(`typedIdPath`) and in the carrier (`carrierIdPath`), so counting and de-duplication follow the
link. `SPEC-REG-INSTANCE` scopes the link by instance and specifies the view's mapping (§3.6, 2026-10-15). A
controller that depends on an ignored member may treat that element as not accepted; the
conformance cases assume it does not. The capability document carries everything the
response depends on except the tenant's stored registrations (with their bindings and blocks),
the credential's grants and whether the hub serves a carrier view of an element, so
a controller can predict most of the result before it submits; the response is authoritative.

**Re-checking and refused typed writes** (decision 8). A controller reads the capability
document and its registration at launch and after a controller release; never on a timer and
never because a request was refused, so an overloaded hub is not met with a surge of reads. A
typed write refused for load — 429 or any 5xx, with or without `Retry-After` (maintainer,
2026-10-15: a server or gateway error says nothing about whether the element is accepted) — is
retried with backoff (no sooner than `Retry-After` when sent); it is not written as its carrier,
the record is not dropped and the write plan does not change. A record still refused when its
delivery deadline passes is sent as its carrier, so a typed route failing persistently never
holds data back from older readers; the element stays accepted for the next record. The deadline
is the controller's. Any other refusal of a typed write is definite: `blocked-by-owner`, a
retired or missing registration, a typed route answering 404 after a hub rollback, or a 4xx
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
   authorised by subject binding, and namespace ownership no longer decides it. (done 2026-10-15, `SPEC-REG-DECISIONS`; the binding was put into the etag the same day, so a release or transfer changes it)
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
   met with a surge of reads: a 429 or 503 is retried with backoff and is not a fallback
   (2026-10-15: every 5xx counts as load, and a record past its delivery deadline goes as its
   carrier without changing the plan); a
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
| `owner-release` | newer/newer | `boundTo: null`; etag changes (it covers the binding) |
| `released-update-binds` | newer/newer | another subject updates a released registration and is bound to it |
| `owner-transfer` | newer/newer | bound to a named subject; etag changes, so a racing owner action meets 412 |
| `owner-free-namespaces` | newer/newer | retired registration's namespaces freed |
| `owner-free-namespaces-not-retired` | newer/newer | active registration; 409 `not-retired` |
| `accepted-dual-write-view-not-served` | newer/newer | no carrier view, `dualWriteLink` declared; typed and carrier (decision 7) |
| `accepted-dual-write-view-served` | newer/newer | `carrierView: served`; typed only |
| `typed-write-load-503` | newer/newer | typed write 503, no `Retry-After`; retry with backoff, no carrier, no re-check (decision 8) |
| `typed-write-load-429-retry-after` | newer/newer | typed write 429 with `Retry-After: 30`; retry after it |
| `typed-write-load-502` | newer/newer | typed write 502; load, like 503: retry with backoff |
| `typed-write-load-deadline-passed` | newer/newer | 503 past the record's delivery deadline; that record as its carrier, element stays typed |
| `typed-write-blocked-by-owner` | newer/newer | typed write 403 `blocked-by-owner`; that record as its carrier, no re-check |
| `typed-write-route-404` | newer/newer | typed route 404 after a rollback; that record as its carrier, no re-check |

The 21 cases that predate the decisions keep their outcomes; each now states the submitter's
subject and credential kind, and each stored registration its identity, binding and credential
kind (measured 2026-10-15: the reference reproduces every earlier expected outcome with only
those members added).

### 3.6 Definitions and instances

*Added 2026-10-15 (`SPEC-REG-INSTANCE`; D19, [execution plan §2.6.2](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#262-d19--definitions-and-instances-maintainer-2026-10-14)).
Specified, not implemented: no hub serves any of this.* §3.5 registers what a controller's data
means, one registration per `(vendor, product)` per tenant. D19 separates that from which copy of
a controller is connected — a phone that doses, a development build or simulator beside it, a lab
rig, a phone migration with both phones running, later agents — so those copies no longer
overwrite one another. The product resource of §3.5 keeps its whole contract; two resources are
added under it.

| file | what it is |
|---|---|
| `specs/sync/controller-instance.schema.json` | the instance document (new) |
| `specs/sync/hub-capabilities.schema.json` | gains `instances` (lease length, role and channel vocabularies, label bounds) |
| `specs/sync/registration-submit.schema.json` | gains the D19 reason codes, `definitionId` on product responses, and the stored-definition, stored-instance, request, response and case shapes (`instanceCase`) |
| `specs/sync/controller-state-model.schema.json` | gains `stateSpans[].wellKnownRef`; `dualWriteLink` and `slotName` descriptions updated |
| `specs/sync/conformance/instances/*.yaml` | 86 synthetic cases; the 55 of §3.5 are unchanged in meaning |
| `tools/nsschema/instances.py` | a reference for this section, extending `negotiate.py` (which gained the definition id, the meaning comparison, well-known references and namespace claims across a product's definitions); it checks the cases, it is not a hub |
| `tools/nsschema/test_registration_instances.py` | the queue gate |

**Three resources under one product.**

| resource | method | who, where | meaning | precondition |
|---|---|---|---|---|
| `<submit.href>/<vendor>/<product>` | as §3.5 | as §3.5 | the product: binding, state (`active`, `retired`, `blocked`), owner actions, namespaces, etag, element results. Its body is a definition; every definition it accepts is also stored content-addressed | as §3.5 |
| `<…>/<product>/definitions/<definitionId>` | `PUT` | the credential the product is bound to, data listener | add a definition, immutably | `If-None-Match: *` only |
| `<…>/<product>/instances/<instanceId>` | `PUT` | any credential with `api:registrations:create` on the tenant, data listener | create (`If-None-Match: *`), renew or change (`If-Match`) an instance | required, as §3.5 |
| `<…>/<product>/instances/<instanceId>` | `DELETE` | the credential the instance is bound to, with `api:registrations:delete` | release the instance and all its roles | `If-Match` |

A hub that advertises `instances` in its capability document serves the two new resources;
one that does not serves neither, and §3.5 applies unchanged. Paths are proposals.

**Definitions (rules 1 and 2).**

- *Identity.* A definition's id is `sha256:` and the lowercase hex SHA-256 of the RFC 8785
  canonical JSON of the definition document as submitted — the same canonical form as the §3.5
  etag. A product PUT's accepted or partial response now names the `definitionId` the hub
  computed, so a controller can check its own canonical form before naming it in an instance.
  Every definition the hub accepts is stored content-addressed: the product resource's current
  registration, every registration a product update replaced, and every definition added at
  `<…>/definitions/<id>`. Any number coexist under one `(vendor, product)`; ten simulators on one
  build share one definition.
- *Adding one.* `PUT <…>/definitions/<definitionId>`, body the definition. Order of checks: (1)
  authorisation — the owner never adds one (403 `not-authorised`), the permission
  `api:registrations:create`, a registered product (404 otherwise), and the product's binding (403
  `not-registration-owner`; a released product is not bound by a definition PUT, because binding
  changes the product's etag and a definition never does — the controller re-binds with a product
  PUT); (2) `If-None-Match: *` (428 otherwise), then the product's state: blocked 403
  `blocked-by-owner`, retired 409 `product-retired`; (3) the body's hash equals the path id (422
  `definition-id-mismatch`), then §3.5's registration-level checks; (4) element results as §3.5,
  plus the two rules below. An identical retry is a 200 no-op. Adding a definition never changes
  the product resource or its etag, so instances of one product never contend on it.
- *Namespaces belong to the product* across all its stored definitions: a definition of another
  product that declares a namespace any of this product's definitions declares is rejected
  `namespace-claimed`, as in §3.5, until the owner frees it on the holder's registration.
- *One kind at one version has one meaning* (`version-conflict`). Within one product, an element
  of a new definition — a stateSpans kind (id `stateSpans/<kind, else category>`) or an
  extension namespace — whose stored version equals that of the same element in a stored
  definition of the product, and whose meaning differs, is rejected `version-conflict`. This
  applies to definition PUTs and to product PUTs (an update is compared with the registration it
  replaces, which stays stored). A different meaning is a new version; definitions that agree, or
  that declare different versions, coexist. The version compared is the element's stored version
  (`version`, or `versions.stored`); an element that declares none is one unversioned version.
  Typed settings fields and replay inputs carry no version in grammar v1 and are not compared.

  | | members that are meaning | not meaning |
  |---|---|---|
  | stateSpans kind | `category`, `kind`, `slot`, `exclusiveWithinSlot`, `coexistsWith`, `overlay`, `supersedes`, `states`, `endReasons`, `wire`, `dualWriteLink`, `requested`, `applied`, `initiators`, `definitions`, `acceptsFromHub`, `horizon` | `description`, `evidence`, `availability`, `version`/`versions`, members the grammar does not define |
  | extension | `carrier`, `dualWriteLink`, `horizon`, `fields` (compared by `name`) | `description`, `evidence`, `availability`, `version`/`versions` |
  | extension field | `name`, `type`, `typeRef`, `unit`, `range`, `horizon`, `sensitivity` | `description`, `evidence` |

  Inside a meaning member, `description`, `evidence` and a carrier's `writtenWhen` are prose and
  not compared, and order is not meaning: an array of strings compares as a set in sorted order,
  an array of objects as the sorted list of their canonical forms. `availability` is a promise
  level, not a typing, so an experimental kind can be released at the same version.
  `sensitivity` is meaning so a later definition cannot relabel data stored under an earlier one.
- *Well-known references.* A stateSpans entry whose kind is exactly a kind of the hub's
  well-known catalogue names it instead of copying it: `wellKnownRef: {catalogue, kind,
  version}`, where `catalogue` is the `id` of an entry in the capability document's
  `wellKnown.kinds[]`, `kind` is the catalogue kind's `kind` (else its `category`) and `version`
  its stored version. The entry carries only `category` and `kind` (both the catalogue kind's),
  the reference, and `availability`, `description` and `evidence`; a restated member is rejected
  `invalid-element`. Its meaning, version, slot and carrier are the catalogue kind's, so a copy
  identical to the catalogue kind agrees with a reference to it, and a copy that differs at that
  version is `version-conflict`. A reference to a kind the hub's catalogue does not have at that
  version is rejected `unknown-well-known-kind`, and the controller writes the referenced kind's
  carrier, which it knows. `wellKnownRef` is additive under must-ignore, and the strict view
  (`sync_model.unknown_grammar_fields`) knows it. **A catalogue kind can be referenced only when
  it declares a version; the three generated registrations (`loop`, `trio`, `androidaps`) declare
  no kind versions** (measured 2026-10-15), so none of their kinds can be referenced until the
  generator gives them versions; the cases use a synthetic versioned catalogue kind.

**Instances (rule 4).**

- *Identity.* The instance id is the path segment: supplied by the controller, opaque, a random
  lowercase UUID version 4 (122 random bits), generated once per copy and never derived from a
  device name, model, serial or the free-text `devicestatus.device` (control-plane
  reconciliation §3.3). Another form is refused 422 `invalid-instance-id`. A hub cannot check
  that an id is random; the contract states it.
- *Body* (`controller-instance.schema.json`): `apiVersion`, `kind: ControllerInstance`,
  `definitionId` (a stored definition of this product, else 422 `unknown-definition`), `roles[]`
  and `labels{}`. An instance carries no hardware identifiers. The upstream RFC's
  `ControllerInstanceRegistration` (cgm-remote-monitor `docs/proposals/agent-control-plane-rfc.md`
  and `schemas/controller-instance-registration.schema.json`, read at official `b5ddd662`) carries
  `device.deviceId`, `device.model`, `pumpBinding.pumpSerial` and `cgmBinding.cgmId`, and its
  `CapabilitySnapshot` takes `controllerInstanceId` from `devicestatus.device` (read-derived).
  This contract has none of them: the instance distinguishes copies of a controller, which an
  opaque id does without identifying a person or a device. Anything identifying a controller
  reports is a typed, sensitivity-labelled field of its definition (D18 addendum rule 2).
- *Observed alias.* The hub may record the free-text `devicestatus.device` it sees in an
  instance's writes on that instance as an observed alias, labelled `{level: identifying,
  category: device}`. It is withheld by default in the `unlabelledPolicy: withhold` style: absent
  from the owner's default listing (shown only when the owner asks for withheld members), never
  in the capability document, never in a default export, and never the instance's identity.
- *Order of checks* for `PUT`. (1) authorisation: the owner never writes an instance (403
  `not-authorised`); the permission; a registered product (404); an existing instance's binding
  (403 `not-registration-owner`). An instance is bound to the subject that created it — or the
  shared secret in single mode — as products are (decision 4), not to the product's binding: a
  development build with its own subject may run a copy of a registered product. (2)
  preconditions: none 428; `If-None-Match: *` over a different stored body 412; `If-Match` that
  is not the instance's current etag 412 `stale-etag` with the current etag and lease; then the
  product's state: blocked 403 `blocked-by-owner`, retired 409 `product-retired`. (3) the instance
  as a whole: id form, labels (`invalid-label`), the schema (`invalid-instance`, including a role
  without provenance and a (channel, role) claimed twice), `unknown-definition` — each 422, nothing
  stored. (4) each role.
- *Lease.* Each create or renewal sets `leaseExpiresAt` to now plus the capability document's
  `instances.leaseSeconds`; the response carries it and per-role results (outcome `accepted`, or
  `partial` when a role is refused; 201 on create, 200 on renewal). An instance that stops
  renewing lapses: it holds no roles, with no housekeeping. Renewal is not a capability re-check:
  a controller reads the capability document at launch and after a controller release (decision
  8), never on a renewal.
- *Etag.* `sha256:` over the canonical JSON of `{instance: <body>, boundTo, granted: <granted
  roles>}`. The lease is outside it, so a renewal that changes nothing keeps it (`noop: true`)
  and a renewal retried after a lost response still matches; a role granted on renewal, or moved
  by the owner, changes it, so the instance learns of an owner's transfer through a 412 on its
  next renewal and two owner actions racing on one instance meet 412. A create retried with the
  same body by the same subject is a renewal.
- *DELETE* releases the instance and all its roles. Records it wrote keep its id.

**Roles, channels and provenance (rules 5 and 6).**

- *A role* is `{channel, role, provenance}`. `role` is an open vocabulary: `source` (the instance
  writes the channel's typed records as their source of record), `command-sink` (it accepts
  hub-originated commands for the channel; only on a channel whose kind declares
  `acceptsFromHub.channels` with `command`, else `not-a-command-channel`), or `{value: other,
  controllerTerm}` for roles such as an agent's propose and act. A hub grants only the roles its
  capability document lists (`unsupported-role` otherwise); a bare unknown string is invalid.
  `provenance` is required and closed: `device` or `simulated`. One instance may mix them (a
  development build with a real CGM and a simulated pump). An unknown provenance refuses that
  role (`unknown-provenance`), never the instance, and is never accepted.
- *Channels.* For a stateSpans kind that declares a `slot`, the channel is that slot name; for
  every other element it is `<vendor>/<product>/<element id>`. A slot channel is shared across
  products on the tenant, so two controllers that name the same slot contend for its roles. A
  slot name containing `/` derives no shared channel (its element form is used), so a slot cannot
  name another product's element channel. A role on a channel the instance's definition does not
  derive is refused `unknown-channel`. **The slot vocabulary**: the grammar's `slotName` is a free
  string "named by this registration" with no shared list; the generated registrations use
  `override` (Loop, Trio), `preMeal` (Loop), `loopMode` (Loop, Trio), `temporaryTarget` (Trio,
  AndroidAPS), `profileSwitch`, `runningMode` and `scene` (AndroidAPS), hand-written in
  `tools/nsschema/sync_model.py` (measured 2026-10-15). Equal names contend; AndroidAPS's
  `runningMode` and Loop's and Trio's `loopMode` do not, though they name a similar state.
- *Exclusivity.* Among live `device`-provenance instances of active products on the tenant, each
  (channel, role) has one holder. A second claimant is refused that role `role-held`; its other
  roles are still granted, and it writes the elements on that channel as their carriers. The hub
  records the overlap and shows it on the owner's instance listing (`overlaps`: channel, role,
  claimant, holder) until the claimant drops the claim or its lease lapses; when the holder has
  lapsed or dropped the role the overlap shows `holder: null`. `simulated` roles never contend
  with `device` roles or with each other.
- *Handoff.* A role passes when its holder drops it (a renewal without it, or DELETE), when the
  holder's lease lapses, or when the owner transfers it. A lapsed or dropped role is not
  auto-assigned: a claimant is granted it on its own next renewal, which re-evaluates every claim.
- *Commands.* A command for a channel goes to the live `device` instance holding `command-sink` on
  it. With no holder the hub refuses the command `no-command-destination` and never routes it to
  a guess: not to a lapsed former holder, not to a `simulated` command sink, not to the product's
  latest instance. The command API itself is not specified here.
- **The hub never decides dosing.** Role exclusivity decides only which instance is the typed
  source of record for a channel and where a command for that channel is routed; it never stops,
  directs or composes dosing. A claimant refused a role keeps running and keeps writing its
  carriers; the hub records what each instance reports (D18).

**Labels (rule 7).** String keys to string values, which distinguish, select and filter instances.
A key is `<namespace>/<name>`, the namespace in the reverse-DNS form extension namespaces use
(`com.example.testcontroller/rig`); labels are not subject to namespace claims. The prefix
`dev.nightscout/` is reserved; its keys are `dev.nightscout/purpose` (`therapy`, `development`,
`lab`, `research`), `dev.nightscout/build` (`release`, `dev`) and `dev.nightscout/migration-group`
(an opaque string shared by the old and new phone of one migration). A reader reads an unlisted
value of the first two as `other`; another key under the prefix is refused `invalid-label`, as are
a key not in the form, a value that is not a string, and labels over the capability document's
`instances.labels` bounds. *(Corrected 2026-10-15: D19 as written named the prefix
`nightscout.dev/`, which is not reverse-DNS form; a key under it is an ordinary key with no
well-known meaning.)* Labels carry no names, device names or serials. Provenance, never a label,
decides what is therapy data.

**Writes, and older controllers losing nothing.**

- A hub that advertises `instances` requires an instance id on every typed write (proposed as a
  request header; the cases model it as `write.instanceId`). An instance-less typed write is a
  definite refusal, 422 `instance-required`: that record goes as its carrier (§3.5 decision 8).
  A typed write also needs the writing instance to be live (409 `not-live`) and to hold `source`
  on the element's channel (409 `role-held` when another instance does, `role-not-granted`
  otherwise), so the claimant's typed write is refused and goes as its carrier. An accepted typed
  record carries its instance, its definition and the role's provenance; only `device`-provenance
  data is therapy data in default views and exports.
- Writes with no instance — older controllers, and anything the well-known tier describes — are
  attributed to an implicit unregistered instance of the product, which holds no roles and is
  never refused for exclusivity. Exclusivity never blocks a carrier write, from any instance.
- *Dual-write link key.* §3.5's `dualWriteLink` matches a carrier to its typed record by
  (instance id, the controller's record id): the instance id travels with each write, typed or
  carrier, so equal record ids from two instances are never linked to each other.

| | older hub | newer hub |
|---|---|---|
| **older controller** | no capability document: today's documents (`carrier-write-older-hub`; §3.5 `older-hub-older-controller`) | no instance id: carrier writes attributed to the product's unregistered instance, never refused for exclusivity (`carrier-write-older-controller`) |
| **newer controller** | no `instances` in the capability document: it registers no instance and its typed writes need none (`typed-write-hub-without-instances`); no capability document at all as §3.5 | definitions, instances, roles and labels (the remaining cases) |

**Read selection (rule 3).** Writes need no selection: each instance names its definition. A view
chooses, per versioned element of a product, the version it shows, in this order: (1) the
operator's capability document limits what is accepted at all — only versions of stored
definitions whose element the hub accepts today are candidates; (2) the owner's pin, for the
site's default views; (3) the newest version run by a live instance holding a `device` `source`
role on the element's channel; (4) the newest stored version. A view with a label selector (every
selector key must have that value) uses only the live instances that match, whatever their
provenance, and no pin. "Newest" compares dot-separated parts, numeric parts as numbers and before
text. Pins are the owner's actions `pin-version` and `unpin-version` on `ns-tenant-admin` (or
`API_SECRET` on single), a resource of their own per product with its own etag (`If-None-Match:
*` for the first pin, `If-Match` after), so an owner's pin never changes the product's etag or
stored data; a pin names a version some stored definition stores (422 `unknown-version`).

**The projected view for older readers (rule 8).** An accepted element's `carrierView: served`
requires a declared mapping: the catalogue's carrier for a referenced well-known kind, the kind's
`wire`, or an extension's `carrier`. A hub that would serve a view of an element without one
reports `not-served`, and the controller writes it per §3.5. For a served element, each typed
record is served to v1 and v3 readers as a projected document in the carrier's shape: the
collection, `eventType`, start time and duration in the wire's unit (or its indefinite sentinel)
from the mapping, and nothing the mapping does not declare. The projected document:

- is labelled by the member `projectedFrom: {definitionId, element, entities: [<typed ids>]}`;
- is never stored as a source and is read-only: a write to it (an update or delete aimed at its
  identifier) is refused 409 `projected-read-only`, and the typed record is changed through the
  typed API by its source;
- carries the decomposed typed entity's id as its identifier: v3 `identifier` and v1 `_id` are
  the typed id verbatim. Where one carrier document is projected from several entities, the id is
  the primary entity's and `entities` lists them all. Prior art, read-derived:
  Nocturne's `V4ToLegacyProjectionService` and `LegacyTreatmentTables` (read at `42275c812`) set a
  projected treatment's or entry's `Id` to the V4 record's `Id.ToString()` (a UUID v7; `Identifier`
  returns `Id`), project a meal bolus from a bolus and a carb intake under the bolus's id, and tell
  records that mirror a legacy write (`LegacyId` set) from V4-native ones with a `NativeOnly`
  filter; the projected `Treatment` carries no projection marker of its own.

A view for older readers is not a conversion between typed versions (D18 addendum rule 4).

**Retention (rule 9).** A definition is eligible for removal only when no stored record references
it, no live instance runs it, and it is not the product resource's current registration
(`definition-referenced`, `definition-in-use`, `definition-current` otherwise). A definition that
is no longer current is not removed while anything references it; each record's declared horizon
retention decides when the record goes.

**The owner's actions** (`ns-tenant-admin`, or `API_SECRET` on single; elsewhere 403
`not-authorised`): §3.5's, plus `transfer-role` (moves one role from the instance it was granted to
to a live instance that claims it with `device` provenance, else 409 `role-not-granted`,
`role-not-claimed` or `not-live`; precondition `If-Match` the etag of the instance it is moved
from; both instances' etags change), `pin-version`, `unpin-version`, and the instance listing
(every instance with its roles, labels and liveness, and the overlaps).

**Choices made here for the maintainer to confirm.** Creating an instance needs the permission,
not the product's binding (a second subject may run a copy); a definition PUT never binds a
released product; definitions and instances are refused for a retired product (409
`product-retired`); the instance etag covers granted roles, so a transfer reaches each instance as
a 412 on its next renewal; every listed role, including an `other` role a hub lists, is exclusive
among `device` instances; a typed write needs a granted `source` role on its channel; the owner
transfers only to a live instance that already claims the role with `device` provenance; pins are
their own resource; "newest" is numeric by part; a label selector ignores provenance and pins;
the product's current registration also keeps its definition from removal; typed settings fields
and replay inputs are outside `version-conflict`; `devicestatus` and other documents are not
channels (writes to them are attributed by instance, and their exclusivity is not specified);
`wellKnownRef` needs a versioned catalogue kind; the permission names reuse
`api:registrations:create`/`delete`. The label prefix correction above was set with this item.

**The cases.** 86, under `specs/sync/conformance/instances/`, each with its time `now`, the hub's
stored registrations, definitions, instances, pins and records, and the expected response and
stored state. A refusal names the passing case that differs from it in the aspect under test.
The 26 §3.5 cases whose response is `accepted` or `partial` gained only `definitionId` (measured
2026-10-15: the reference reproduces every other member unchanged); the other 29 are unchanged.

| case | what it shows | outcome | control |
|---|---|---|---|
| `carrier-view-needs-mapping` | A projected view is served only with a declared mapping | 200 accepted; carrierView not-served |  |
| `carrier-write-claimant` | Exclusivity never blocks a carrier write | 200 written; carrier, attributed to the instance |  |
| `carrier-write-older-controller` | An older controller's write goes to the unregistered instance | 200 written; carrier, attributed unregistered |  |
| `carrier-write-older-hub` | An older hub takes today's documents | 200 written; carrier |  |
| `command-no-destination-simulated` | A simulated command sink is never a command destination | 409 rejected; no-command-destination | `command-routed` |
| `command-routed` | A command for a channel goes to its command-sink holder | 200 routed |  |
| `definition-blocked-by-owner` | No definition is added to a blocked product | 403 rejected; blocked-by-owner | `definition-put` |
| `definition-extension-version-conflict` | An extension typed differently at the same version is rejected | 201 partial; `extensions/com.example.controllera.targets` version-conflict | `definition-put` |
| `definition-id-mismatch` | A definition whose hash is not the path id is refused | 422 rejected; definition-id-mismatch | `definition-put` |
| `definition-namespace-claimed` | A namespace another product's definition declares is held | 201 partial; `extensions/com.example.shared.feature` namespace-claimed | `definition-namespace-own` |
| `definition-namespace-own` | A product's own definitions share its namespaces | 201 accepted |  |
| `definition-not-registration-owner` | Another subject cannot add a definition | 403 rejected; not-registration-owner | `definition-put` |
| `definition-product-retired` | No definition is added to a retired product | 409 rejected; product-retired | `definition-put` |
| `definition-put` | A second definition is added to a product, content-addressed | 201 accepted |  |
| `definition-retry-noop` | An identical definition PUT is a no-op | 200 accepted |  |
| `definition-same-meaning` | Non-meaning members may differ at the same version | 201 accepted |  |
| `definition-version-conflict` | A kind typed differently at the same version is rejected | 201 partial; `stateSpans/ExampleOverride` version-conflict | `definition-put` |
| `definition-wellknown-copy-agrees` | A copy identical to a referenced catalogue kind agrees with the reference | 201 accepted |  |
| `definition-wellknown-copy-conflicts` | A copy that differs from a referenced catalogue kind conflicts | 201 partial; `stateSpans/LegacyOverride` version-conflict | `definition-wellknown-copy-agrees` |
| `definition-wellknown-ref-restated` | A reference restates nothing of the kind | 201 partial; `stateSpans/LegacyOverride` invalid-element | `definition-wellknown-ref` |
| `definition-wellknown-ref-unknown` | A reference to a kind the catalogue does not have | 201 partial; `stateSpans/LegacyOverride` unknown-well-known-kind | `definition-wellknown-ref` |
| `definition-wellknown-ref` | A definition references a well-known kind instead of copying it | 201 accepted |  |
| `dual-write-linked` | A dual-write carrier links to its typed record by (instance, record id) | 200 written; carrier, attributed to the instance, linkedTo the typed record |  |
| `dual-write-not-linked-across-instances` | Equal record ids from two instances never link | 200 written; carrier, attributed to the instance, linkedTo null | `dual-write-linked` |
| `instance-blocked-product` | No instance for a blocked product | 403 rejected; blocked-by-owner | `instance-create` |
| `instance-create-other-subject` | A second credential runs another copy of a registered product | 201 accepted |  |
| `instance-create-retry-noop` | An identical instance create retried is a renewal | 200 accepted |  |
| `instance-create` | An instance is created with a lease and its roles | 201 accepted |  |
| `instance-delete-stale` | DELETE needs the current etag | 412 precondition-failed; stale-etag | `instance-delete` |
| `instance-delete` | DELETE releases an instance and all its roles | 200 released |  |
| `instance-handoff-lapse` | A lapsed holder's role goes to the claimant on its renewal | 200 accepted |  |
| `instance-handoff-release` | A holder that drops a role hands it to the claimant's renewal | 200 accepted |  |
| `instance-invalid-id` | An instance id is a random UUID version 4 | 422 rejected; invalid-instance-id | `instance-create` |
| `instance-label-not-namespaced` | A label key is <reverse-DNS namespace>/<name> | 422 rejected; invalid-label | `instance-create` |
| `instance-label-not-string` | A label value is a string | 422 rejected; invalid-label | `instance-create` |
| `instance-label-old-prefix` | The reserved prefix is dev.nightscout/, not nightscout.dev/ | 201 accepted |  |
| `instance-label-other-value` | An unlisted well-known value is accepted and read as other | 201 accepted |  |
| `instance-label-reserved-unknown` | Only the specified keys live under dev.nightscout/ | 422 rejected; invalid-label | `instance-create` |
| `instance-missing-provenance` | A role without a provenance is invalid | 422 rejected; invalid-instance | `instance-create` |
| `instance-not-a-command-channel` | command-sink only where the kind accepts commands | 201 partial; com.example.controllera.targets command-sink: not-a-command-channel | `instance-create` |
| `instance-not-registration-owner` | Another subject cannot renew an instance | 403 rejected; not-registration-owner | `instance-renew` |
| `instance-overlap-holder-lapsed` | An overlap stays listed with no holder after the holder lapses | 200 listed; 2 overlaps, holder null |  |
| `instance-overlap-listed` | The owner's listing shows the overlap | 200 listed; 2 overlaps |  |
| `instance-renew-after-transfer-stale` | After a transfer the former holder's renewal meets 412 | 412 precondition-failed; stale-etag | `instance-renew-after-transfer` |
| `instance-renew-after-transfer` | The former holder renews with its current etag | 200 partial; override command-sink: role-held | `owner-transfer-role` |
| `instance-renew-holder-live` | A claimant's renewal stays refused while the holder is live | 200 partial; override source: role-held; override command-sink: role-held | `instance-handoff-lapse` |
| `instance-renew` | An instance renews its lease with If-Match | 200 accepted |  |
| `instance-retired-product` | No instance for a retired product | 409 rejected; product-retired | `instance-create` |
| `instance-role-held` | A second device source for a slot is refused role-held | 201 partial; override source: role-held; override command-sink: role-held | `instance-role-simulated` |
| `instance-role-simulated` | Simulated roles never contend with device roles | 201 accepted |  |
| `instance-unknown-channel` | A role on a channel the definition does not derive | 201 partial; temporaryTarget source: unknown-channel | `instance-create` |
| `instance-unknown-definition` | An instance must name a stored definition of its product | 422 rejected; unknown-definition | `instance-create` |
| `instance-unknown-provenance` | A role with an unknown provenance is refused | 201 partial; override source: unknown-provenance | `instance-create` |
| `instance-unsupported-role` | A role term the hub does not list is refused | 201 partial; override other: unsupported-role | `instance-create` |
| `lapsed-role-not-auto-assigned` | A lapsed holder's role is not given to anyone until asked | 409 rejected; no-command-destination | `command-routed` |
| `listing-includes-withheld` | The owner may ask for withheld members | 200 listed |  |
| `listing-withholds-alias` | The owner's default listing withholds observed aliases | 200 listed |  |
| `observed-alias-recorded` | The free-text devicestatus.device is an observed alias | 200 written; carrier, attributed to the instance |  |
| `owner-pin-stale` | A pin change needs the current pins etag | 412 precondition-failed; stale-etag | `owner-unpin-version` |
| `owner-pin-unknown-version` | A pin names a stored version | 422 rejected; unknown-version | `owner-pin-version` |
| `owner-pin-version` | The owner pins a version for the site's default views | 201 applied |  |
| `owner-transfer-role-data-listener` | A transfer on the data listener is refused | 403 rejected; not-authorised | `owner-transfer-role` |
| `owner-transfer-role-not-claimed` | A role is transferred only to an instance that claims it | 409 rejected; role-not-claimed | `owner-transfer-role` |
| `owner-transfer-role-stale` | A transfer with a stale etag fails its precondition | 412 precondition-failed; stale-etag | `owner-transfer-role` |
| `owner-transfer-role` | The owner transfers a role from its holder to a claimant | 200 applied |  |
| `owner-unpin-version` | The owner removes a pin | 200 applied |  |
| `product-update-new-version` | A product update with the retyped kind at a new version | 200 accepted |  |
| `product-update-version-conflict` | A product update retyping a kind at the same version is rejected for that kind | 200 partial; `stateSpans/ExampleOverride` version-conflict | `product-update-new-version` |
| `project-no-mapping` | No projection without a declared mapping | 409 rejected; no-carrier-mapping | `project-served` |
| `project-served` | An older reader is served a labelled, read-only projection | 200 projected |  |
| `retention-current` | The product's current registration is kept | 200 not-eligible; definition-current | `retention-eligible` |
| `retention-eligible` | A definition nothing references may be removed | 200 eligible |  |
| `retention-in-use` | A definition a live instance runs is kept | 200 not-eligible; definition-in-use | `retention-eligible` |
| `retention-referenced` | A definition stored records reference is kept | 200 not-eligible; definition-referenced | `retention-eligible` |
| `select-capability-limit` | The operator's capabilities limit what any view shows | 200 selected; com.example.controllera.targets 2 by newest-stored |  |
| `select-label-selector` | A lab view selects its own instances by label | 200 selected; com.example.controllera.targets 2 by label-selector |  |
| `select-live-device` | A default view shows the version the live device source runs | 200 selected; com.example.controllera.targets 1 by live-device |  |
| `select-newest-stored` | With no live device source, the newest stored version | 200 selected; com.example.controllera.targets 2 by newest-stored |  |
| `select-owner-pin` | The owner's pin wins over the live device's version | 200 selected; com.example.controllera.targets 2 by owner-pin |  |
| `typed-write-attributed` | A typed write by the source holder is accepted and attributed | 200 written; typed, device, attributed to the instance |  |
| `typed-write-hub-without-instances` | A hub without instances needs no instance id | 200 written; typed, attributed unregistered |  |
| `typed-write-instance-required` | A hub with instances refuses an instance-less typed write | 422 rejected; instance-required | `typed-write-attributed` |
| `typed-write-role-held` | A typed write by a refused claimant is refused role-held | 409 rejected; role-held | `typed-write-attributed` |
| `typed-write-simulated` | A simulated source's typed write carries simulated provenance | 200 written; typed, simulated, attributed to the instance |  |
| `write-projected-read-only` | A write to a projected document is refused | 409 rejected; projected-read-only | `write-stored-carrier` |
| `write-stored-carrier` | A write to a stored carrier document is accepted as today | 200 written; carrier, attributed unregistered |  |

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

*(2026-10-14: answered by D19 — [execution plan §2.6.2](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#262-d19--definitions-and-instances-maintainer-2026-10-14) — which adopts the RFC's kind/instance split with the reconciliation's identity correction and settles two writers on one site; what follows is the map as written on 2026-09-11.)* *(2026-10-15: specified in [§3.6](#36-definitions-and-instances) (`SPEC-REG-INSTANCE`): the instance carries an opaque controller-supplied id and no hardware identifiers, `devicestatus.device` is a withheld observed alias, liveness is a lease, and channel ownership is one `device`-provenance holder per (channel, role).)*

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
* `specs/sync/controller-instance.schema.json`, `specs/sync/conformance/instances/`, `tools/nsschema/instances.py` — definitions and instances (§3.6)
* `specs/conformance/observability-profile.yaml` — the obligations a registration would formalise
* `externals/oref-digital-twin/` — `DESIGN.md` §2, `replay/inputs.py`, `settings/schema.py`
* Nocturne: `Core.Models/StateSpan.cs`, `API/Services/V4/TreatmentDecomposer.cs`
* AAPS `core/nssdk/.../NightscoutRemoteService.kt`; Loop `NightscoutKit/NightscoutClient.swift`; Trio `Sources/Services/Network/Nightscout/NightscoutAPI.swift`
* cgm-remote-monitor `lib/api3/` — `lastModified`, `{collection}/history/{lastModified}`
