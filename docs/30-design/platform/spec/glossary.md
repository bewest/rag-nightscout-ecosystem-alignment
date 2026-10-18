# Platform glossary

*Contributor-facing. Living, current at `main` `5a9a49cc` (2026-10-18). Each term links to where
it is specified; the definition here is a summary, and the linked section is the authority. Therapy
terms (profile, override, temporary target) are in the [domain glossary](../../../10-domain/glossary.md).
The [platform index](../README.md) explains the layers.*

`HS` below is [the hub-sync design](../nightscout-hub-sync-architecture-2026-09-11.md), `REG` the
[registration specification](registration.md) and `ID` the [identity specification](identity.md); `WC` is
[the write contract](../../tenancy/write-contract-spec-2026-10-07.md).

## "Primitive" has three meanings

The word appears across the series for three different things. Use the qualified term.

| say | meaning | where |
|---|---|---|
| **observation primitive** | a typed record kind such as `SensorGlucose`, `Bolus` or `ApsSnapshot` that a composite document decomposes into | `specs/sync/primitives.yaml`; [HS §3.3](../nightscout-hub-sync-architecture-2026-09-11.md#33-composite-on-the-wire-primitive-in-storage) |
| **grammar member** | a member of the registration grammar (`stateSpans`, `extensions`, `settings`, a type fragment) | [REG §3](registration.md#3-the-grammar); `specs/sync/controller-state-model.schema.json` |
| **contract primitive** | a building block of the hub contract: an id, a definition, an instance, a role, an etag, a write result | this glossary, L0, L2 and L5 |

## L0 Identity

**`_id`.** The storage key the hub assigns. On every hub's legacy surface (API v1 and v3) it is a
24-hex value, on MongoDB and PostgreSQL alike. Its first four bytes are the hub's receipt time,
not the record's time. [ID I2, I3](identity.md#1-rules).

**`identifier`.** The sync identity the client assigns, stable across retries and devices. In the
typed API it is the controller's record id. A UUID is recommended, not required. The proposed
constraints are in [identifier format §0](../../../60-research/tenancy/identifier-format-2026-10-17.md#0-answer),
and the format decision is open (`ID-FORMAT-DECISION`).

**Two-id rule.** Every write reply returns both `identifier` and `_id` and says which one matched
(`matchedBy`). A re-send matches on `identifier` first, then on `_id`, so a client needs no cache
of server ids. [ID I4, I5](identity.md#1-rules).

**`syncIdentifier`.** A controller's own per-record sync key (Loop and LoopKit; Nocturne's V4
update key is `(dataSource, syncIdentifier)`). It is not unique per record in stored data:
13 Loop values each appear on 2 to 4 treatments ([identifier duplicates](../../../60-research/tenancy/identifier-duplicates-2026-10-17.md)).
A controller may send it as `identifier`.

**Natural key.** The fields a re-send without an id is matched on, one key per collection on every
write path: entries `date`+`type`, profile `created_at`, treatments `created_at`+`eventType`;
devicestatus `created_at`+`device` for an identical body only; food and activity by id only. Today
the key differs by path. [Identity §3](identity.md#3-match-order-per-collection).

**Definition id.** `sha256:` and the hex SHA-256 of the RFC 8785 canonical JSON of a definition as
submitted. Equal content gives an equal id. [ID §2](identity.md#2-contract-ids).

**Instance id.** A random lowercase UUID v4 the controller generates once per running copy. It is
never derived from a device name, model or serial. [ID §2](identity.md#2-contract-ids).

**Subject.** The opaque id of the principal a credential belongs to. Tokens rotate; the subject
does not. Registrations and instances bind to the subject, never to a token.

## L1 Records

Specified in the [records specification](records.md).

**Composite document, carrier.** Today's wire documents (a treatment, a devicestatus, a profile).
A *carrier* is the composite shape an element is written in when it is not written typed: its
`wire` declaration (collection, `eventType`, duration unit, indefinite sentinel, how "ended" is
encoded).

**Decomposition.** Turning a composite document into observation primitives on write, keeping the
composite as well. [D11](../../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#26-d11--devicestatus-is-a-decomposition-problem-not-a-column-selection-problem).

**Evidence grade.** `measured` (a wire path in the corpus populates it), `declared` (a typed model
has it and the corpus does not show it), `proposed` (asked for). In registrations, evidence is
`read` (from source) or `measured`.

**Quirk.** A recorded way stored documents deviate from the documented shape, scoped by
`affects: {vendor, product, versions}`, with a lifecycle `proposed` → `active` → `historical` →
`retired`. [quirks registry](../../../../specs/quirks/README.md); [REG §16](registration.md#16-version-scoped-quirks).

**Sensitivity label.** A field's two-axis label (`specs/sync/sensitivity.yaml`). A field with no
label is withheld by default (`unlabelledPolicy: withhold`).

**Horizon.** How long a value stays meaningful: `cycle`, `span`, `effective-dated`, `definition`
or `aggregate`, each with its own cadence and retention.

## L2 Definitions and instances

**Registration, product.** A controller's declaration of what its data means, one per
`(vendor, product)` per tenant. The product resource holds the binding, the state (`active`,
`retired`, `blocked`), the etag and the per-element results. [REG §5](registration.md#5-the-product-resource).

**Tier.** *Well-known*: registrations the hub ships for controllers that declare nothing, so
legacy writers need no change. *Controller-owned*: registrations a controller submits. [D18](../../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#261-d18--two-tier-controller-registration).

**Capability document.** `GET /.well-known/nightscout/sync`: unauthenticated and cacheable. It says
which grammar majors, members, type keywords, horizons, limits, roles and shared slots the hub
supports. It never lists a tenant's registrations.

**Element, element result.** The unit the hub accepts or rejects: a `stateSpans` kind, an
extension namespace, a typed settings field or a typed replay input. The result is `accepted`,
`accepted-with-ignored-members` or `rejected` with reasons. A registration is `accepted` or
`partial` overall.

**Fallback.** What a controller writes when an element is not accepted: the element's carrier.
Decided per element, from the response to this registration only.

**Definition.** An immutable, content-addressed statement of what a controller's data means. Many
coexist under one product; ten simulators on one build share one. [D19](../../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#262-d19--definitions-and-instances-maintainer-2026-10-14).

**Meaning members, `version-conflict`.** The members of a kind, extension or field that define
what it means ([REG §7](registration.md#7-definitions)'s table). Within one product, one element at one version has one meaning. A
different meaning at the same version is rejected `version-conflict`; a new meaning needs a new
version.

**Instance.** One running copy of a controller (a phone that doses, a development build, a
simulator, the old and new phone during a migration). It names its definition, holds roles on
channels and renews a lease. [REG §8](registration.md#8-instances).

**Lease.** An instance's liveness. Each create or renewal extends it by the hub's
`instances.leaseSeconds`; an instance that stops renewing lapses and holds no roles.

**Label.** A string key and value on an instance, `<reverse-DNS namespace>/<name>`, for selecting
and filtering. `dev.nightscout/` is reserved (`purpose`, `build`, `migration-group`). Labels never
decide what is therapy data; provenance does.

**Namespace, extension.** An *extension* is controller-specific typed data under a reverse-DNS
*namespace*. Namespaces are first to claim per tenant and belong to the product across all its
definitions. A namespace string proves nothing about authorship.

**`wellKnownRef`.** A definition's reference to a kind in the hub's well-known catalogue, instead
of a copy of it.

**Read selection, pin.** Which version of an element a view shows: the operator's capabilities,
then the owner's pin, then the version the live `device` source runs, then the newest stored.

**Projected view, `carrierView`.** A read-only document in the carrier's shape that the hub serves
to older readers from a typed record, labelled `projectedFrom`. `carrierView: served` says the hub
serves one for an element. A write to a projected document is refused `projected-read-only`.

**`dualWriteLink`.** For an element whose view is not served: the controller writes typed and
carrier, linked by (instance id, the controller's record id), so counting and de-duplication follow
the link.

**Retention.** A definition is kept while any stored record references it, any live instance runs
it, or it is the product's current registration.

## L3 State and intent

Specified in the [state and intent specification](state-intent.md).

**Intent kind, `stateSpans` entry.** One kind of state a controller exposes (an override, a
temporary target, a loop mode). It declares its slot, states, end reasons, carrier, where the
request and the applied effect are recorded, initiators, definitions and what it accepts from the
hub. [State and intent S2](state-intent.md#2-rules).

**Slot.** The exclusivity group a kind occupies. Kinds in one slot exclude each other; a kind may
declare which other slots coexist with it.

**Channel.** What roles are held on. For a kind with a slot, the channel is that slot. A slot is
shared across products only through the hub's shared slot list or a declared `sameAs`; otherwise it
is the product's own channel, `<vendor>/<product>/<slot>`. Other elements' channels are
`<vendor>/<product>/<element id>`. [REG §9](registration.md#9-channels-roles-and-provenance).

**Shared slot list, `sameAs`.** `specs/sync/shared-slots.yaml` (`override`, `loopMode`,
`temporaryTarget`). A kind declares `sameAs: <shared slot>` to join that channel. Two slots are
never joined because their names look alike. [REG §9](registration.md#9-channels-roles-and-provenance).

**Requested, applied.** What was asked for, and what the controller reports it put into effect.
They are recorded separately; a request is not evidence that anything happened.

**End reason.** Why a span ended: expired, cancelled, superseded, deleted before start, ended by
trigger, or `other` with the controller's term.

**Initiator.** Who or what started an intent, in the controller's own vocabulary (Loop
`EnactTrigger`, Trio `AdjustmentSource`, AndroidAPS `Sources`). A value outside the shared list is
`{value: other, controllerTerm}`.

**Composition.** How overlapping intents combine. Recorded as the controller reports it
(`reportedBy: controller`, `hubComputes: false`); the hub never computes it.

**StateSpan.** Nocturne's span record (category, state, start, end, source, supersession), the
container the series uses for observed state over time.

## L4 Change and sync

**Write step.** The single function every write path (v1, v3, socket, in-process) would call,
deciding `_id` form, target, outcome (insert, merge, replace, unchanged, refused), server dates and
one change event. [WC §2](../../tenancy/write-contract-spec-2026-10-07.md#2-the-proposed-write-step).

**Re-send rule.** A re-send that matches a stored record stores no second copy and is answered with
the stored ids. A differing re-send merges into the match (JSON Merge Patch: a `null` removes the
field); an explicit update replaces. An identical re-send is rewritten on API v1, v3 and in-process
and answered unchanged on the socket and for devicestatus (decided 2026-10-12, [WC §6.1](../../tenancy/write-contract-spec-2026-10-07.md#61-decided-2026-10-12)). Match order: [identity §3](identity.md#3-match-order-per-collection).

**Etag, precondition.** `sha256:` over the canonical JSON of a resource's content, state and
binding. Creates send `If-None-Match: *`; updates send `If-Match`. A missing precondition is 428 and
a stale one is 412.

**Load refusal, definite refusal.** A typed write answered 429 or any 5xx is retried with backoff
and never re-sent as its carrier. Any other refusal sends that record as its carrier at once.
[REG §6](registration.md#6-the-controllers-side-fallback-and-refused-writes).

**Cursor, watermark.** An opaque server position from which changes are read. API v3 has
`lastModified` and per-collection `history/{from}`; the proposed sync envelope reads every
registered collection from one cursor. [HS §3.2](../nightscout-hub-sync-architecture-2026-09-11.md#32-the-contract-the-hub-returns).

**Storage socket.** The API v3 socket that pushes stored changes to subscribed clients. Measured on `dev`
`43289dde`, only API v3 writes reach it ([WC §3](../../tenancy/write-contract-spec-2026-10-07.md#3-the-unified-re-send-rule) U7).

**`quirksApplied`, `slotMapping`.** What the hub records on a reply and on the stored record when
it applied a quirk mapping or decided a channel by `sameAs`, so a mapped value is never silent.

## L5 Authority

Specified in the [authority specification](authority.md).

**Binding (`boundTo`), credential kind.** The subject (or, in single mode, the shared secret) a
product or instance is bound to; only it may update or retire it. `credentialKind` records whether
a subject token or `API_SECRET` last wrote it. [authority §3](authority.md#3-binding-and-credential-kind).

**Owner, owner actions.** The tenant owner, acting on `ns-tenant-admin` (or with `API_SECRET` in
single mode). The owner may retire, block, unblock, release, transfer, free namespaces, transfer a
role and pin a version, and never edits a registration's content.

**Role.** `{channel, role, provenance}` on an instance. `source` writes the channel's typed records
as their source of record; `command-sink` accepts hub-originated commands for it; other roles are
`{value: other, controllerTerm}`. Among live `device` instances each (channel, role) has one
holder.

**Provenance.** `device` or `simulated`, per role. Only `device`-provenance data is therapy data in
default views and exports, and a `simulated` command sink never receives a routed command.

**Command destination.** The live `device` instance holding `command-sink` on a channel. With no
holder the command is refused `no-command-destination`; the hub never guesses
([commands §2](commands.md#2-where-a-command-goes)).

**Command record, outcome.** Proposed. The hub stores a command before it sends it, with the hash
of its payload; only the destination reports the outcome, and `sent` or `fetched` is never success
([commands §4–§5](commands.md#4-the-command-record-proposed)).

**Delegation, proposal.** A *delegation* would let a principal grant a caregiver, app or agent a
scoped, expiring, revocable authority; it is not specified. A *proposal* records an intended
change for approval without authority to execute it; an approval names the hash of one payload
(proposed, [commands §6](commands.md#6-proposals-and-approvals-proposed)). What a delegation design must provide is in
[configuration and delegation §5.4](../../tenancy/nightscout-configuration-and-delegation-2026-09-10.md#54-what-a-delegation-design-would-have-to-provide).
