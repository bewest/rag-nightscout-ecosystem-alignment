# Add a setting in your controller's next release: declare it typed, submit it, fall back, write it and read it back

*Contributor-facing. Living guide, current at `main` `127f69e1` (2026-10-18). Uses the [platform specifications](../README.md); terms are in the [glossary](../spec/glossary.md). Status: the specifications are proposed and not implemented; until `HUB-REG-CRM` is, each step is checked against its conformance case, not run against a hub.*

*For a Loop, Trio or other controller developer who adds a setting or feature in a release and
wants a Nightscout hub to store and show it typed. Expect the decisions to make before writing
code, a walk-through in three tables (declare and submit, write and read back, the release after),
what older hubs and older readers see, a checklist, and the steps no case covers.*

## 1. What you will have at the end

Your release declares the setting in a controller-owned registration, submits it to any hub that
takes submissions, and learns element by element what the hub accepted. For each accepted element
it writes typed records, attributed to the running copy of your app and to the definition they
were written under. For everything else, and on every hub that predates the specifications, it
writes the same documents it writes today, so no site loses data and no older reader breaks. What
older readers see of an accepted element (a read-only projection, a linked carrier copy, or
nothing in the carrier's shape) is a choice your declaration makes (§4).

## 2. Before you start

### 2.1 The worked example

The example setting is fictional. Its declaration is taken from the synthetic fixture
`specs/sync/registrations/fixtures/example-testcontroller.yaml`, whose extension
`com.example.testcontroller.adaptiveTargets` holds a typed schedule and a typed on/off setting.
The conformance cases use two other synthetic products with an extension of the same shape:
`Example/NegotiationController` with `com.example.negotiation.targets`, and `Example/ControllerA`
with `com.example.controllera.targets`. Read "your extension" for any of the three. None of them
describes a real controller.

### 2.2 Choose the shape: a typed settings field or an extension

The hub accepts four kinds of element ([registration §5.3](../spec/registration.md#53-elements-and-their-results)).
Two of them carry a setting:

| your setting | declare it as | element id | when the hub does not accept it |
|---|---|---|---|
| one that `ControllerSettings` already defines ([records §5](../spec/records.md#5-settings-snapshot)) | a typed `settings.fields[]` entry with `typeRef` to its definition | `settings.fields/<name>` | written where it is today, name-only (`write: untyped`) |
| one unique to your app | a field of an extension under a reverse-DNS namespace your app holds | `extensions/<namespace>` | written as the extension's declared `carrier` |

The well-known Loop registration already names Loop's `ControllerSettings` fields this way:

<!-- BEGIN GENERATED: guide-example specs/sync/registrations/loop.yaml spec.settings.fields.0 -->
```yaml
name: automaticBolusApplicationFactor
typeRef: https://nightscout.dev/schemas/sync/controller-settings.json#/properties/settings/properties/automaticBolusApplicationFactor
```
<!-- END GENERATED: guide-example -->

The rest of this guide follows the extension path, because the conformance cases cover it. The
typed settings field path follows the same steps; §6 lists what its cases do not show.

### 2.3 Which hub answers what

Your app meets four kinds of hub. It finds out which from the capability document,
`GET /.well-known/nightscout/sync`, read at launch and after an app update, never on a timer, on a
lease renewal or because a request was refused ([registration §4](../spec/registration.md#4-the-capability-document)).

| the hub | what your app does |
|---|---|
| answers 404 for the capability document (every hub released before `HUB-REG-CRM`) | submits nothing; writes every element as its carrier |
| publishes the document with no `submit` member | submits nothing; writes every element as its carrier |
| publishes `submit` and no `instances` | submits; writes accepted elements typed, with no instance id |
| publishes `submit` and `instances` | submits; registers an instance; writes accepted elements typed, with its instance id |

The parts of a hub your app calls (C4 containers; under `TENANCY_MODE=single` one listener serves all three):

![3·guide-containers: your app reads the unauthenticated capability document at launch; it calls the data listener to put its product, definition and instance, write typed records, fetch commands and report outcomes, which the hub stores per element bound to your credential and attributed to your instance; the socket brings live commands inside bound requests; the site owner acts through the owner's listener on products, definitions and instances](../../../00-overview/perspective/diagrams/3-guide-containers.svg)

The members your app reads before it submits are `grammar.versions`, `typeFragment` and
`submit`:

<!-- BEGIN GENERATED: guide-example accepted.yaml capabilities.submit -->
```yaml
href: /api/v4/registrations
tiers:
- controller-owned
permissions:
  submit: api:registrations:create
  retire: api:registrations:delete
```
<!-- END GENERATED: guide-example -->

<!-- BEGIN GENERATED: guide-example accepted.yaml capabilities.typeFragment -->
```yaml
keywords:
- type
- enum
- minimum
- maximum
- format
- items
- properties
- required
- description
```
<!-- END GENERATED: guide-example -->

## 3. The walk-through

Each step names the rule it follows and the conformance case that shows it. Case paths are
relative to `specs/sync/conformance/` unless they start with `specs/`.

### 3.1 Declare and submit

| step | you do | the hub answers | rule | case |
|---|---|---|---|---|
| 1 | Read the capability document at launch. With no document, or no `submit`, skip to step 9 and write carriers. | the document, or 404 | registration §4, registration §6 | `accepted.yaml`, `older-hub-no-capabilities.yaml`, `hub-without-submit.yaml` |
| 2 | Check that your grammar major is in `grammar.versions` and that every type keyword and format your fields use is in `typeFragment`. Do not submit a major the hub does not list. | a keyword outside the subset rejects that element `unsupported-type-keyword`; an unlisted major rejects the whole registration | G2, registration §5.2 | `rejected-type-keyword-outside-subset.yaml`, `rejected-unsupported-grammar-major.yaml` |
| 3 | Declare the setting as a field of your extension: a `type` fragment (or `typeRef`), a `unit` where it has one, and a `sensitivity` label. A field with no label falls under `unlabelledPolicy`, which is `withhold` when absent. | an extension with an untyped field is rejected `untyped-extension` | G2, R9 | `specs/sync/registrations/fixtures/example-testcontroller.yaml`, `rejected-untyped-extension.yaml` |
| 4 | Put the extension under a reverse-DNS namespace that your credential's namespace roots cover and that no other product on the site holds. | `namespace-not-owned` or `namespace-claimed` for that element; first to claim holds it | registration §5.3, authority §5 | `rejected-namespace-not-owned.yaml`, `rejected-namespace-claimed.yaml`, `accepted-first-to-claim.yaml` |
| 5 | Give the extension a `version` and a `horizon`. A setting is configuration published on change, so its horizon is `effective-dated`, as the `settings` document's is (R5, registration §3); a value computed each cycle is not a setting and belongs to the cycle's record (R7). Leave `availability` out for a released setting; `experimental` is stored only by a hub that lists it. | the version is what `version-conflict` and read selection compare later | G4, G5, R5, R7 | `specs/sync/registrations/fixtures/example-testcontroller.yaml`, `accepted.yaml`, `rejected-unsupported-availability.yaml` |
| 6 | Declare the extension's `carrier`: the document you write today for this setting. It is your fallback and the mapping any projected view uses. | an element with no carrier falls back to `none`, and no view of it can be served | registration §5.3, registration §13 | `rejected-untyped-extension.yaml`, `instances/carrier-view-needs-mapping.yaml` |
| 7 | `PUT` the registration to `<submit.href>/<vendor>/<product>` with `If-None-Match: *` the first time. A retry after a lost response sends the same body again. | 201 with an outcome, the `definitionId` and an element result per element; a retry of stored content is a 200 no-op | registration §5.1, registration §5.2, D18 | `accepted.yaml`, `create-retry-noop.yaml` |
| 8 | Read each element's result and keep the write plan for this release. Treat `accepted` and `accepted-with-ignored-members` as accepted; anything else, or a value you do not know, as not accepted. | `accepted`, `accepted-with-ignored-members` (members kept as written), or `rejected` with reasons; outcome `accepted` or `partial` | registration §5.3, registration §6, G1 | `accepted.yaml`, `accepted-with-ignored-members.yaml`, `extensions-not-interpreted.yaml` |
| 9 | For each element not accepted, and for every element on a hub from step 1 that takes no submission, keep writing today's carrier document. | the hub stores the carrier as it does today | registration §6, registration §17 | `rejected-untyped-extension.yaml`, `older-hub-no-capabilities.yaml`, `hub-without-submit.yaml` |
| 10 | For an accepted element, read `carrierView`. `served`: write typed only. Not served and the element declares `dualWriteLink`: write typed and as its carrier, linked by your record id. Not served and no link: write typed only. | older readers get the projection, the linked carrier copy, or nothing in the carrier's shape | registration §6, registration §13, I7 | `accepted-dual-write-view-served.yaml`, `accepted-dual-write-view-not-served.yaml`, `instances/dual-write-linked.yaml` |

The declaration, from the fixture (steps 3 to 6). The fixture marks its extension `experimental` to exercise that rule; a released setting omits it:

<!-- BEGIN GENERATED: guide-example specs/sync/registrations/fixtures/example-testcontroller.yaml spec.extensions -->
```yaml
com.example.testcontroller.adaptiveTargets:
  version: '1'
  availability: experimental
  horizon:
    class: definition
  carrier:
    collection: settings
    documentIdentifier: example-targets
  fields:
  - name: targetSchedule
    type:
      type: array
      items:
        type: object
        properties:
          startMinute:
            type: integer
            minimum: 0
            maximum: 1439
          target:
            type: number
        required:
        - startMinute
        - target
    unit: mg/dL
    sensitivity:
      level: descriptive
      category: therapy-setting
  - name: adaptationEnabled
    type:
      type: boolean
    sensitivity:
      level: descriptive
      category: therapy-setting
```
<!-- END GENERATED: guide-example -->

The request (step 7), as the cases model it:

<!-- BEGIN GENERATED: guide-example accepted.yaml request -->
```yaml
action: submit
identity:
  vendor: Example
  product: NegotiationController
preconditions:
  ifNoneMatch: '*'
```
<!-- END GENERATED: guide-example -->

Every element accepted (step 8):

<!-- BEGIN GENERATED: guide-example accepted.yaml expected.response.elements -->
```yaml
- element: stateSpans/ExampleOverride
  result: accepted
- element: extensions/com.example.negotiation.targets
  result: accepted
```
<!-- END GENERATED: guide-example -->

The same extension with an untyped field: rejected, and the write plan sends it as its carrier
(steps 8 and 9):

<!-- BEGIN GENERATED: guide-example rejected-untyped-extension.yaml expected.response.elements.1 -->
```yaml
element: extensions/com.example.negotiation.targets
result: rejected
reasons:
- code: untyped-extension
  path: spec.extensions.com.example.negotiation.targets.fields.0
```
<!-- END GENERATED: guide-example -->

<!-- BEGIN GENERATED: guide-example rejected-untyped-extension.yaml expected.fallback -->
```yaml
stateSpans/ExampleOverride:
  write: typed
extensions/com.example.negotiation.targets:
  write: carrier
  carrier:
    collection: settings
    documentIdentifier: example-targets
```
<!-- END GENERATED: guide-example -->

### 3.2 Write the typed record and read it back

| step | you do | the hub answers | rule | case |
|---|---|---|---|---|
| 11 | On a hub that publishes `instances`, create an instance: a random UUID v4 generated once per running copy, the `definitionId` from step 7, and a `source` role with `device` provenance on your extension's channel, `<vendor>/<product>/extensions/<namespace>`. On a hub without `instances`, skip this step. | 201 with the lease and a result per role | registration §8, registration §9, D19 | `instances/instance-create.yaml`, `instances/typed-write-hub-without-instances.yaml` |
| 12 | Renew the lease with `If-Match` before it lapses. A renewal is not a reason to re-read the capability document. | 200, `noop: true` when only the lease moved | registration §8 | `instances/instance-renew.yaml` |
| 13 | Write the typed record with your instance id and your own record id, which the hub keeps as `identifier`. | 200 with the record attributed to your instance, its definition and provenance, and both ids; a write with no instance id on a hub with `instances` is refused 422 `instance-required` | registration §11, I1, I4 | `instances/typed-write-attributed.yaml`, `quirks/typed-write-assigns-objectid.yaml`, `instances/typed-write-instance-required.yaml` |
| 14 | Re-send with the same record id after a lost reply. No cache of server ids is needed. | the stored ids, `matchedBy: identifier`, no second record | I5, I7 | `quirks/typed-write-resend-same-ids.yaml` |
| 15 | Handle a refused typed write. 429 or any 5xx: retry with backoff, no sooner than `Retry-After`, never as a carrier. Any other refusal: send that record as its carrier at once and treat the element as not accepted until the next launch or app update. | load refusals change nothing; a definite refusal changes the plan for that element | registration §6 | `typed-write-load-503.yaml`, `typed-write-load-429-retry-after.yaml`, `typed-write-blocked-by-owner.yaml`, `typed-write-route-404.yaml`, `instances/typed-write-role-held.yaml` |
| 16 | Read which version of your extension the site's views show. | the owner's pin, else the version the live `device` source runs, else the newest stored, within what the hub's capabilities accept | registration §12 | `instances/select-live-device.yaml`, `instances/select-newest-stored.yaml`, `instances/select-owner-pin.yaml` |
| 17 | Read back what you wrote as a carrier through history, from the cursor your last read returned. A record received by event and by history is kept once. | pages of records above the cursor, `complete` when nothing was truncated | T5, T6, T10 | `sync-transport/single-page-complete.yaml`, `sync-transport/duplicate-delivery-is-one-record.yaml` |

A role on the extension's channel (step 11), and the hub's result for it:

<!-- BEGIN GENERATED: guide-example instances/instance-create.yaml body.roles.2 -->
```yaml
channel: Example/ControllerA/extensions/com.example.controllera.targets
role: source
provenance: device
```
<!-- END GENERATED: guide-example -->

<!-- BEGIN GENERATED: guide-example instances/instance-create.yaml expected.response.roles.2 -->
```yaml
channel: Example/ControllerA/extensions/com.example.controllera.targets
role: source
provenance: device
result: granted
```
<!-- END GENERATED: guide-example -->

The reply to a typed write (step 13). The case writes the override kind of the same product; the
reply has the same shape for any element:

<!-- BEGIN GENERATED: guide-example quirks/typed-write-assigns-objectid.yaml expected.response.write -->
```yaml
accepted: true
as: typed
attributedTo:
  vendor: Example
  product: ControllerA
  instanceId: 00000000-0000-4000-8000-00000000000a
definitionId: sha256:ee552930b207551ed46bbbe4e1065e3c67773415193f3a067ef46816201da2ab
provenance: device
ids:
  identifier: 00000000-0000-7000-8000-0000000000b2
  _id: 6ad0c04000000000000000a1
matchedBy: null
```
<!-- END GENERATED: guide-example -->

The versions a default view shows while the phone runs the first definition (step 16):

<!-- BEGIN GENERATED: guide-example instances/select-live-device.yaml expected.response.selection -->
```yaml
extensions/com.example.controllera.targets:
  version: '1'
  by: live-device
stateSpans/ExampleOverride:
  version: '1'
  by: live-device
```
<!-- END GENERATED: guide-example -->

A typed record keeps the `definitionId` it was written under, and the hub converts nothing between
versions without a lossless mapping your definition declares (T13, G4). A sync page carries the
definitions its records reference (T14). No case shows a typed record read back through the sync
read; §6 lists it.

### 3.3 The release after

| step | you do | the hub answers | rule | case |
|---|---|---|---|---|
| 18 | At the next release, `PUT` the same product resource with `If-Match` and the stored etag. Identity is vendor and product; `versionRange` is an attribute. | 200 and a new etag; a stale etag is 412 and changes nothing | registration §5.1, registration §5.4 | `update-accepted.yaml`, `update-stale-etag.yaml` |
| 19 | When a meaning member of the setting changes (type, unit, range, horizon, sensitivity, carrier), raise the extension's version. Description and evidence may change at the same version. | the same version with a different meaning is rejected `version-conflict` for that element, which then goes as its carrier | registration §7, G4, D19 | `instances/definition-extension-version-conflict.yaml`, `instances/product-update-new-version.yaml`, `instances/definition-same-meaning.yaml` |
| 20 | When builds of two releases run on one site, each instance names its own definition; a build that is not the current registration adds its definition with `PUT …/definitions/<definitionId>` and `If-None-Match: *`. | 201; the product's etag does not change; both definitions stay stored | registration §7, D19 | `instances/definition-put.yaml`, `instances/definition-retry-noop.yaml` |
| 21 | When an earlier release wrote the setting in a shape that deviates (a unit, a slot name, a vocabulary), the deviation belongs in the quirks registry (`specs/quirks/`) as an entry with an `affects` range over your version strings, stated only where the corpus or source shows it. A newer definition declares its own mapping instead (`sameAs` for a slot). | the hub applies a catalogue mapping only to writers whose version it knows and is in range, and records every mapping it applies | Q1, Q2, Q3, D20 | `quirks/catalogue-mapping-applied.yaml`, `quirks/catalogue-mapping-version-outside.yaml`, `quirks/same-as-definition-accepted.yaml` |

The extension retyped at the version a stored definition already uses (step 19):

<!-- BEGIN GENERATED: guide-example instances/definition-extension-version-conflict.yaml expected.response.elements.1 -->
```yaml
element: extensions/com.example.controllera.targets
result: rejected
reasons:
- code: version-conflict
  path: spec.extensions.com.example.controllera.targets
```
<!-- END GENERATED: guide-example -->

To move stored records to a new version, your app sends them again under the new definition with
the same `identifier`; the re-send matches and replaces their content and `definitionId` (T15).

## 4. What older apps see

The per-app answers are in [compatibility](../spec/compatibility.md): the
[L2 table](../spec/compatibility.md#43-l2-definitions-and-instances) for attribution and projected
views, the [L1 table](../spec/compatibility.md#42-l1-records) for records, and
[where an answer changes](../spec/compatibility.md#5-where-an-answer-changes). For the setting
your release adds:

| who | sees | rule | case |
|---|---|---|---|
| a hub that predates the specifications | your carrier documents, exactly as today | registration §17, registration §6 | `older-hub-no-capabilities.yaml`, `instances/carrier-write-older-hub.yaml` |
| an older reader (a follower app, a report, the hub's own web pages) when the element's view is `served` | a projected document in the carrier's shape, labelled `projectedFrom`, with the same `_id` on every read; it cannot write to it | registration §13, I8 | `instances/project-served.yaml`, `instances/write-projected-read-only.yaml` |
| an older reader when the view is not served and the element declares `dualWriteLink` | the carrier copy your app writes beside the typed record | registration §6, I7 | `accepted-dual-write-view-not-served.yaml`, `instances/dual-write-linked.yaml` |
| an older reader when the view is not served and the element declares no link | nothing in the carrier's shape: the record exists only typed | registration §6, registration §13 | `instances/carrier-view-needs-mapping.yaml` |
| an earlier release of your own app on the same site | nothing changes for it: its carrier writes are stored, attributed to the product's unregistered instance and never refused for exclusivity | registration §11, registration §17 | `instances/carrier-write-older-controller.yaml`, `instances/carrier-write-claimant.yaml` |

A projection, as the case for the override kind serves it (the mapping comes from the element's
declared carrier; for your extension that is the `settings` document it names):

<!-- BEGIN GENERATED: guide-example instances/project-served.yaml expected.response.projected -->
```yaml
collection: treatments
document:
  identifier: 00000000-0000-7000-8000-0000000000b1
  _id: 6ad0b23500000000000000b1
  created_at: '2026-10-15T11:00:00Z'
  eventType: Temporary Override
  duration: 60
  projectedFrom:
    definitionId: sha256:ee552930b207551ed46bbbe4e1065e3c67773415193f3a067ef46816201da2ab
    element: stateSpans/ExampleOverride
    entities:
    - 00000000-0000-7000-8000-0000000000b1
```
<!-- END GENERATED: guide-example -->

So the choice in step 10 decides what followers see. If followers must keep showing the setting
on hubs that serve no view of it, declare `dualWriteLink`.

## 5. Checklist

- [ ] The setting has one home: a typed `settings.fields[]` entry with `typeRef` when
      `ControllerSettings` defines it, else a field of your extension.
- [ ] Every field has a `type` or `typeRef` within the hub's `typeFragment`, a `unit` where it has
      one, and a `sensitivity` label.
- [ ] The namespace is reverse-DNS, covered by your credential's roots, and yours alone on the site.
- [ ] The extension has a `version`, a `horizon` and a `carrier` that is the document you write
      today.
- [ ] The app reads the capability document and its registration only at launch and after an app
      update.
- [ ] The write plan is per element, from this registration's response only; anything unknown is
      not accepted.
- [ ] Carrier writes continue for every element not accepted and on every hub without `submit`.
- [ ] On a hub with `instances`, every typed write carries a live instance id holding `source` on
      the element's channel.
- [ ] Typed records carry your own stable record id as `identifier`.
- [ ] Load refusals retry; definite refusals send that record as its carrier.
- [ ] A change of meaning raises the element's version.
- [ ] You have decided what followers see: a served view, a dual write, or typed only.

## 6. Gaps

Steps a developer needs that no conformance case shows. Each is a gap in the cases, not in
this guide's steps.

1. **Typed settings fields.** No case submits a typed `settings.fields[]` entry, so neither its
   element result nor its `write: untyped` fallback ([registration §5.3](../spec/registration.md#53-elements-and-their-results))
   is shown, and none writes a `ControllerSettings` snapshot ([records §5](../spec/records.md#5-settings-snapshot)).
2. **The typed record itself.** The typed write route is not specified ("the typed API the hub
   derived", registration §6), and the write cases model the request with no body, so no case shows
   the content of a typed extension record. Under `instances/`, every typed write case writes a
   `stateSpans` kind; none writes an extension element.
3. **Reading a typed record back.** The sync read (T5), typed records on the socket (T11), the
   definitions a page carries (T14) and moving stored records to a new version (T15) have no case
   with a typed record.
4. **Projecting an extension.** `instances/project-served.yaml` projects a `stateSpans` kind to a
   treatment; no case projects an extension to its `settings` carrier document.
