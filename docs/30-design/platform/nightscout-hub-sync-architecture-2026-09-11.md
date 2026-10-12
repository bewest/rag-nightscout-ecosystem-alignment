# A hub-and-spoke sync model for AID controllers

*Contributor-facing.* **Snapshot — describes 2026-09-11. Status: current as analysis; the design it sketches is carried forward by [PROPOSAL-controller-descriptions](PROPOSAL-controller-descriptions-2026-09-11.md) and [PROPOSAL-replay-fidelity-changes](PROPOSAL-replay-fidelity-changes-2026-09-11.md).** Current decisions: [execution plan §1](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#1-decisions). **Corrected in place 2026-10-12:** §3.1's description of `stateSpans` and the schema field list in §5.2 now match the schema as extended for D18 from [intent and workflow across the landscape](./nightscout-intent-workflow-landscape-2026-10-09.md) §9. **Also 2026-10-12:** §3.1 lists `extensions` and the D18 addendum grammar rules 1–5 (`SCHEMA-REG-EXT`). **Also 2026-10-12:** §3.5 specifies negotiation, D18 addendum rule 6 (`SPEC-REG-NEGOTIATE`): the capability document, the submit, update and retire contract, the fallback rule, authorisation with open questions, and the conformance cases.

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
Specified, not implemented: no hub serves any of this.* The hub publishes what it supports;
the controller submits its controller-owned registration and reads back, per element, what
was accepted; for anything not accepted it writes the element's well-known carrier.

| file | what it is |
|---|---|
| `specs/sync/hub-capabilities.schema.json` | the capability document |
| `specs/sync/registration-submit.schema.json` | request, response, fallback and conformance-case shapes |
| `specs/sync/conformance/*.yaml` | 21 synthetic conformance cases; both hubs implement against them |
| `tools/nsschema/negotiate.py` | a reference decision function that computes each case's expected response and fallback. It checks that the cases are self-consistent; it is not a hub |
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

| method | meaning | precondition (required) |
|---|---|---|
| `PUT` | submit: create, or update | `If-None-Match: *` to create; `If-Match: <etag>` to update |
| `GET` | read the stored registration with its current element results | none |
| `DELETE` | retire | `If-Match: <etag>` |

**Order of checks.** (1) authorisation (403); (2) preconditions — none sent is 428, a failed
one is 412 with the current etag and state, and retiring an identity with nothing stored is 404 (RFC 9110 §13.2.1 evaluates preconditions after
authorisation and before the content); (3) the registration as a whole — `apiVersion` not
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
name and type. Otherwise an element is rejected for: `namespace-not-owned`,
`namespace-claimed` (another registration on the tenant declares it), `untyped-extension`,
`unsupported-type-keyword` (a keyword or format outside `typeFragment`, including in a
`typeRef` target), `limit-exceeded` (`maxFieldsPerExtension`, `maxTypeDepth`),
`invalid-element` (an extension that fails the grammar), `version-plan-invalid`,
`unsupported-availability`, `unsupported-horizon`. Declared availability and horizons are
checked only where the hub interprets them. Reason codes are an open vocabulary (`other` with
the hub's `term`); `detail` is for people and is not compared by the conformance cases.
Outcome: `accepted` when every element is accepted, `partial` when at least one is rejected —
both store the registration as written (201 on create, 200 on update).

**Concurrency and idempotency.** The etag is `sha256:` and the hex SHA-256 of the RFC 8785
canonical JSON of `{"registration": <as submitted>, "state": <active|retired>}`, so it changes
on every change of content or state. A request whose content and state are already stored
succeeds as a no-op (`noop: true`, 200, the stored etag), so a create retried after a lost
response does not fail (RFC 9110 §13.1.1 allows a 2xx for `If-Match` when the change has already been
applied; the contract applies the same rule to a create's `If-None-Match`). A stale `If-Match` with different content is 412 `stale-etag`; `If-None-Match: *`
over different content is 412 `registration-exists`. A hub evaluates a stored registration
against its current capabilities on every read, so an element's result can change after a hub
upgrade; the stored registration and its etag do not.

**Retire.** Only the owning controller retires (D18). Retiring sets the state to `retired`,
changes the etag and keeps the declaration, frozen: data already stored under it stays stored
and readable as declared, and no typed write is accepted for its kinds or extensions. Its
namespaces stay claimed while it is stored. A later `PUT` with the retired etag reactivates it.
The controller writes its carriers from the moment it retires.

**Fallback (the controller's side).** An element is written through the typed API only when
the response to *this* registration has outcome `accepted` or `partial` and the element's
result is `accepted` or `accepted-with-ignored-members`. Everything else — a rejected
element, an element result or reason the controller does not know, a rejected registration,
a failed precondition, a retired registration, no response, no capability document, no
`submit`, or a grammar major the hub does not list — falls back per the elements table. A
controller that depends on an ignored member may treat that element as not accepted; the
conformance cases assume it does not. The capability document carries everything the
response depends on except the tenant's stored registrations and the credential's grants, so
a controller can predict the result before it submits; the response is authoritative.

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
  controller on two tenants registers twice.
- **Permission.** Submitting needs `api:registrations:create` and retiring needs
  `api:registrations:delete`, shiro-style like the existing `api:<collection>:<action>`
  permissions, granted by the tenant owner to the controller's subject on `ns-tenant-admin`
  (D16). The names are proposals.
- **Namespace ownership.** A credential holds a set of namespace roots on its tenant. A
  registration may declare an extension namespace equal to or below one of them
  (`com.example` covers `com.example.negotiation.targets`; `com.examplefoo` does not), and
  not one another registration on the tenant already declares. Retiring needs roots covering
  every namespace the stored registration declares. The conformance cases state the outcome
  given the roots, independent of how the roots are granted.
- **Storage.** Registrations are tenant data: per-tenant, under RLS (D3), never in the
  public capability document. Authorisation is per tenant, as the D13 amendment requires.

**Open questions for the maintainer.** None of these is decided by D13–D18; the cases do not
depend on the answers.

1. **Where namespace roots come from.** Granted by the tenant owner per subject on
   `ns-tenant-admin`; derived from a client identity such as Nocturne's RFC 7591
   `software_id` (§2.2 of the controller-descriptions proposal), which would need third-party
   client registration that D17 defers with Hydra; or both.
2. **Scope of a namespace.** Per tenant (what the cases assume, consistent with "authorization
   is per-tenant"), or deployment-wide, or verified against DNS control of the reverse-DNS
   name. A per-tenant namespace can mean two things on two tenants, which matters to any
   reader that spans tenants.
3. **`API_SECRET` in single mode.** It grants `*`. Whether it also holds every namespace root,
   or a controller must register with a subject token, is open. D13 removes it only in multi
   mode.
4. **Binding a registration to a credential.** Whether any credential with the permission and
   the namespace roots may update or retire a registration (what the cases assume), or only
   the subject that created it — which matters when an app is reinstalled or its token rotated.
5. **The tenant owner and a controller-owned registration.** D18 gives the controller the
   lifecycle. Whether the owner may also retire or block one from `ns-tenant-admin` is open.
6. **Identity granularity.** `(vendor, product)` per tenant assumes one live release per
   controller per tenant. Two phones on two releases would share one registration; whether
   `versionRange` should join the identity is open.
7. **Writing both typed and carrier.** A controller may keep writing carriers for accepted
   elements so older readers still see them. The hub would then hold one intent twice; whether
   it should link or deduplicate them, and on what key, is open.
8. **Re-checking.** When a controller re-reads its registration or the capability document
   (each launch, each release, on a timer) after a hub upgrade or downgrade.
9. **Retired data.** How long a retired declaration keeps typed reads available, beyond each
   item's declared horizon retention.
10. **Which hub first** (already open on `HUB-REG-CRM`): single-tenant cgm-remote-monitor, or
    the multitenant target only.

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
| `retire-not-authorised` | newer/newer | credential does not own the namespaces; 403 |

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
