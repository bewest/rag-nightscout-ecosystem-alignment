# L0 Identity: how records, definitions, instances and subjects are named

*Contributor-facing. Living specification, current at 2026-10-29 (cgm-remote-monitor `dev`
`47723cda`, and `e1f7ac41` where named). Layer L0 of the [platform index](../README.md); terms are in the
[glossary](glossary.md). Status: specified, not implemented; §6, today's behaviour, is evidenced.
Decisions:
[D20](../../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#263-d20--version-scoped-quirks-and-the-two-id-rule-maintainer-2026-10-16),
the [write contract's §6.1](../../tenancy/write-contract-spec-2026-10-07.md#61-decided-2026-10-12)
and the [16.0.0 decisions](../../../../releases/cgm-remote-monitor-16.0.0/decisions.md) (I2 on API
v3, BF-170; the null rule of §3, Q1b), and D-LOOP-ID
([next-gen plan §4.2](../next-gen-platform-plan.md#42-identity), maintainer, 2026-10-29: the
`identifier` format, `_id` over API v1, re-sends with changed fields, re-send after delete).
Queue: `SPEC-ID`.*

*Specification 1 of 8 in the [reading order](../README.md#reading-order); every other specification uses these ids. Expect rules I1–I9, the contract ids, the match order per collection, the `identifier` format, today's behaviour in cgm-remote-monitor, and the conformance cases.*

This page defines how records, definitions, instances and subjects are identified, and how a hub
decides that a write is a re-send of something it already stores. Every other layer uses these
ids; none of them redefines one.

## 1. Rules

| # | rule |
|---|---|
| I1 | **Two ids, two jobs.** `identifier` is the sync identity the client assigns: stable across retries and across the devices that write the same record. `_id` is the storage key the hub assigns. In the typed API, `identifier` is the controller's record id. |
| I2 | **`_id` is 24 hex on every legacy surface.** The hub assigns a 24-hex `_id`, on MongoDB and PostgreSQL alike; API v1 serves it, and API v3 reads do not return it (§6). **On API v1**, a client `_id` that is 24 hex, in either case, or `{"$oid": …}`, is kept as that ObjectId in lower case, and a client `_id` that is any other string is never stored as `_id`; it is handled by the quirks registry (I9). **On API v3**, a client-supplied `_id` in the body of a create, `PUT` or `PATCH` is refused with HTTP 400, whatever its form, and no quirk applies: a v3 client names its records by `identifier` (maintainer, 2026-10-25; BF-170). A hub's own newer APIs may use other ids. |
| I3 | **An assigned `_id`'s time is the receipt time.** The first four bytes of an ObjectId the hub assigns are when the hub received the write, not the record's own time. Readers take a record's time from `created_at` or `date`. |
| I4 | **Every write reply returns both ids.** Per item: `identifier` (null when the client sent none and the path assigns none), `_id`, and `matchedBy`: `identifier`, `_id`, or null for a new record. On v1 and v3 this is the write step's `WriteResult.items[]`; on a typed write it is `write.ids`. A duplicate is never answered with a 5xx, an error to the callback or an empty acknowledgement. |
| I5 | **A re-send matches on `identifier` first**, then on `_id`, then on the collection's natural key (§3). A matched re-send stores no second copy and is answered with the stored ids, so a client needs no cache of server ids. |
| I6 | **One identifier names one record** per collection, for as long as the record is stored, and is compared exactly: case-sensitive, with no trimming or normalisation. For devicestatus, a re-send whose `identifier` is already stored writes nothing (no merge, no new record, no `srvModified` change) and is answered with the stored `_id`, on API v1 and v3 alike (maintainer, 2026-10-26; §3). |
| I7 | **A typed re-send matches across instances of one product.** A typed write matches a stored typed record of the same `(vendor, product)` with the same `identifier`, whichever instance sent it. The dual-write link (§2) is the exception: it is scoped by instance. |
| I8 | **Projected documents have both ids.** When a hub serves a typed record to older readers as a projected document, it assigns an ObjectId at the typed write and stores it with the record, so every read of that projection carries the same `_id`. The projection's `identifier` is the typed record's id. A write aimed at either id of a projected document is refused `projected-read-only`. |
| I9 | **Today's `_id` handling is a recorded quirk.** A non-ObjectId string `_id` on a treatment or entry is moved to `identifier` when `UUID_HANDLING` is on (the default) and the client sent no `identifier`, and dropped otherwise (QUIRK-TREATMENTS-006, QUIRK-ENTRIES-004). The hub records the move on the reply and the stored record as `quirksApplied` (`moved-to-identifier` or `dropped`). |

`identifier` is the record's semantic identity in the data model (this CGM reading, this pump
event, this carb entry), so two uploads of the same real thing carry the same value whichever app
sends it; `_id` identifies the stored record (maintainer, 2026-10-18).

Rules I1–I9 are D20 rules 5–8 with the walk-through rows 1–3, specified in the
[hub-sync design §3.7](../nightscout-hub-sync-architecture-2026-09-11.md#37-version-scoped-quirks-and-the-two-ids),
and the write contract's U1 and U6.

## 2. Contract ids

| id | form | assigned by | identifies |
|---|---|---|---|
| definition id | `sha256:` + the lowercase hex SHA-256 of the RFC 8785 canonical JSON of the definition as submitted | the hub computes it; the controller may compute it to check | one immutable definition; equal content gives an equal id |
| registration etag | `sha256:` over the canonical JSON of `{registration, state, boundTo}` | the hub | one state of a product resource |
| instance id | a random lowercase UUID v4, generated once per running copy; any other form is refused `invalid-instance-id` | the controller | one running copy of a controller |
| instance etag | `sha256:` over the canonical JSON of `{instance, boundTo, granted}`; the lease is outside it | the hub | one state of an instance |
| subject | an opaque id of the principal a credential belongs to | the credential issuer | a principal; tokens rotate, the subject does not |
| dual-write link | (instance id, the controller's record id) | the controller | one typed record and its carrier copy |

An instance id is never derived from a device name, model, serial number or the free-text
`devicestatus.device`. A hub cannot check that an id is random; the contract states it. Bindings
are to a subject, never to a token. These are specified in the
[registration specification §7–§8](registration.md#7-definitions).

## 3. Match order per collection

The write step (write contract §2.2) resolves a re-send's target by trying keys in order; the
first that resolves wins.

| collection | keys, in order | on a match |
|---|---|---|
| treatments | `identifier`, `_id`, client identity, `created_at` + `eventType` | merge |
| entries | `identifier`, `_id`, `date` + `type` | merge |
| devicestatus | `identifier`, `_id`, `NSCLIENT_ID`, `created_at` + `device` for an identical body only | an `identifier` match is unchanged whatever the body: nothing is written, no `srvModified` changes, and the reply carries the stored `_id`; on the other keys an identical body is unchanged and a differing body is a new record |
| profile | `identifier`, `_id`, `NSCLIENT_ID`, `created_at` | merge |
| food | `identifier`, `_id` | merge |
| activity | `_id` | merge |

- *Merge* follows JSON Merge Patch (RFC 7386): a field sent as `null` is removed from the stored
  record. The rule is recursive (a `null` inside a nested object removes that nested field) and
  an array is replaced whole, never merged element by element. It applies to a merge on match (a
  re-send that matches a stored record, in the collections above whose outcome is merge), to an
  API v3 `PATCH`, and to the socket's `dbUpdate`, which follows `PATCH`. It never applies to a
  replace (v1 `PUT`, v3 `PUT`), which stores the document as sent, or to any create, which stores
  a `null` as sent. On API v1 it runs after `prepareData`, so a field that `prepareData` removes or
  rewrites never reaches it. The socket's `dbUpdateUnset` stays as the explicit removal of named
  fields (maintainer, 2026-10-26; write contract Q1b; ships in 16.0.0).
- Because the merge is recursive, a profile re-send whose `store` leaves out a named profile keeps
  that stored profile; removing it takes `store: {"<name>": null}` or a replace (`PUT`, which the
  profile editor uses). The same nested merge applies to an API v3 `PATCH` and a socket
  `dbUpdate` (maintainer, 2026-10-26, accepted with this consequence).
- *Client identity* is `treatment-fallback-key`'s client ids, with its rule that a write without
  identity matches only a stored record without identity.
- The devicestatus natural key matches identical retries only, because Loop writes distinct
  statuses that share `created_at` and `device` (3,078 groups, 14,757 documents, at 11 of 12
  corpus sites, measured 2026-10-12).
- An `_id` matches every stored form of that id.
- *Re-send after delete.* A re-send that matches a deleted record is acknowledged with a 2xx naming
  the stored, deleted record, and the record stays deleted, on every path (maintainer, 2026-10-27;
  every path, 2026-10-29). Each cell this changes is documented, so the change can be reverted or
  adjusted. Today's code differs per path (§6); `ID-FIRST-MATCH` builds the rule.
- *Re-send with changed fields.* Where the table says merge, merge on match is the default. API v3
  refuses a re-send whose `date`, `device` or `eventType` differs from the stored record (HTTP
  400), and `PUT` replaces. A site setting plus per-client quirks (I9's registry) may opt a client
  into keep-first or refuse (`ID-RESEND-SWITCH`). A default changes only in a major version
  (maintainer, 2026-10-29).
- *Fields left out of a re-send* are kept on a merge on match (RFC 7386). The census reads replace on
  several paths today, which is not yet measured; the extended write-contract matrix measures each
  path before it changes, and every changed cell is listed.
- *Socket edits and removes, and activity.* The socket's `dbUpdate`, `dbUpdateUnset` and `dbRemove`
  accept an `identifier` when no `_id` is given, and an activity create matches on `identifier`.
  Both apply only where the extended matrix shows every existing form unchanged (maintainer,
  2026-10-29).
- *A re-send without `identifier`* is matched only by the natural keys in the table. New natural
  keys (device status, profile) are a separate item, `ID-NATURAL-KEY`, with its own corpus check of
  what would merge; food and activity have none.

## 4. The `identifier` format

`identifier` is an opaque string, with one rule for every collection. Values follow the
[identifier conventions](../identifier-conventions.md) table, one row per record kind, in URL
syntax: a source scheme for things that exist outside the app, the manufacturer as the scheme and
the model as the first segment (`dexcom://g7/<serial>/<offset>`), and an app scheme for records
made in an app (`loop://carbs/<uuid>`) (maintainer, 2026-10-18). What makes two devices agree is
that they derive the id from the same inputs, not its format. A UUID is recommended and not
required.

The format (maintainer, 2026-10-29, D-LOOP-ID) is 1 to 256 URL-safe characters (C1–C3), a UUID
recommended, with placeholders refused (C5). C4 and C5's reserved path words (`history`, `.`,
`..`) are proposed. Nothing enforces the format yet. Identifier-first matching would merge two
clients' writes that carry the same placeholder, so `ID-VALIDATE` ships with or before
`ID-FIRST-MATCH`. Each constraint is grounded in the
[identifier format research §0](../../../60-research/tenancy/identifier-format-2026-10-17.md#0-answer):

| # | constraint |
|---|---|
| C1 | a JSON string with at least one non-whitespace character |
| C2 | at most 256 characters |
| C3 | characters from `A-Z a-z 0-9 - . _ ~ : /`; in an API v3 path the identifier is percent-encoded as one segment (an encoded `/` works on every v3 by-identifier route at 15.0.8 and `fade2299`, a raw `/` is 404: [format research §3.4](../../../60-research/tenancy/identifier-format-2026-10-17.md#34-url-form-identifiers-end-to-end-2026-10-18-m)) |
| C4 | not exactly 24 hex characters, unless it equals the record's own `_id` |
| C5 | not `history`, `.` or `..`, and not a client placeholder such as `invalid`, `undefined`, `null` or `NaN` |
| C6 | one identifier, one record (I6) |
| C7 | compared exactly (I6) |

A client that sends no usable identifier sends none, and the natural key applies. A client that
uses today's v1 by-`_id` routes needs a UUID (§6).

## 5. Open decisions

| item | question | where the rules above stand |
|---|---|---|
| `ID-FORMAT-DECISION` | adopt C1–C7? | decided (maintainer, 2026-10-29): 1 to 256 URL-safe characters, a UUID recommended, placeholders refused (C1–C3, C5); opaque values, URL syntax and the source and app schemes decided 2026-10-18; C4 and the reserved path words proposed; not enforced yet (`ID-VALIDATE`) |
| `ID-CLIENT-OID-DECISION` | may a client create its own ObjectId as `_id` over API v1? | decided (maintainer, 2026-10-29): a client may still send an ObjectId `_id` over API v1 (legacy); going forward the hub sets `_id` and the client sets `identifier`. I2 refuses a client `_id` on API v3 (maintainer, 2026-10-25, BF-170). When `identifier` and `_id` match different records, `identifier` decides (maintainer, 2026-10-18), as I5 orders it |
| `ID-V3-IMMUTABLE-DECISION` | on an `identifier` match, may `date`, `device` or `eventType` change? | decided (maintainer, 2026-10-29, §3): merge on match stays the default; API v3 keeps refusing the change (400, reproduced by `LOOP-ID-V3-IMMUTABLE`); `PUT` replaces; `ID-RESEND-SWITCH` may opt a client into keep-first or refuse. Loop and Trio re-send changed doses, overrides and temp targets by `POST` over v1 and rely on the update ([client survey](../../../60-research/tenancy/identity-resend-survey-2026-10-29.md)) |
| `ID-ABSENT-DECISION` | a write with no `identifier`: keep the time-key fallback, deprecate it, or require `identifier`? | decided (maintainer, 2026-10-27): `identifier` is SHOULD for legacy writers, and the time-key fallback stays; it is MUST for registered controller instances; revisited as adoption grows. Open: how a hub recognises a registered instance's write on a legacy path. New natural keys are `ID-NATURAL-KEY`. Today v1 entries and treatments fall back to a time key, API v3 to its fallback fields; v1 device status has no key; two distinct doses with one `created_at` and `eventType` and no identifier are merged by §3 (UCA-SYNC-STORE-007) |
| `ID-DELETE-REUSE-DECISION` | after a delete, does a re-send of the same `identifier` resurrect, get refused, or create new? A resurrected dose is UCA-SYNC-STORE-003 in the [control-loop analysis](control-loops.md) | decided (maintainer, 2026-10-27; every path, 2026-10-29): acknowledged, and the record stays deleted (§3). Not built: today API v1 stores the re-send again after its hard delete and API v3 `POST` resurrects a soft-deleted record (measured 2026-10-18, [record identity reference](../../../10-domain/record-identity-reference.md)) |
| `ID-SCOPE-DECISION` | is `identifier` unique per collection, across collections, and per tenant? | decided (maintainer, 2026-10-27): unique per collection, with the tenant in the key under multi; values stay globally unique by convention (the URL kind segment). Not enforced: no index on `identifier` is unique today (`ID-UNIQUE-INDEX`) |
| D20 choice 6 ([text](../nightscout-hub-sync-architecture-2026-09-11.md#37-version-scoped-quirks-and-the-two-ids)) | is `identifier` null in the reply when the client sent none and the path assigns none? | I4 states null, pending confirmation |
| D20 choice 7 | does a typed re-send match across instances of one product? | I7 states yes, pending confirmation |

## 6. Today, in cgm-remote-monitor

Read-derived unless marked, at `official/dev` `fade2299` except where another revision is named. Measured per collection and path at 15.0.8 and `fade2299` in the [record identity reference](../../../10-domain/record-identity-reference.md) (2026-10-18).

- **API v1 treatments** match a re-send on `identifier`, and drop a client `_id` when `identifier`
  is present (`lib/server/treatments.js:356-362` at 15.0.8).
- **API v1 entries and devicestatus** (`dev` since #8859, `ID-SIMPLE-MATCH`): a v1 entries re-send
  matches on `identifier` and updates, and a v1 device status re-send matches on it and keeps the
  stored record (measured, [record identity reference §2.7](../../../10-domain/record-identity-reference.md#27-what-a-re-send-does-by-collection-and-path-added-2026-10-29)).
  15.0.9 matches neither on `identifier`.
- **API v1 by-id routes** treat only UUID-shaped values as identifiers (`UUID_RE`,
  `lib/server/query.js:12`). Stored identifiers are compared exactly, so an upper-case UUID matches
  only itself.
- **API v3** keeps a client `identifier`. When none is sent it computes a UUID v5 over the device,
  date and, for treatments, `eventType` (`lib/api3/shared/operationTools.js:6`, `:106`). It
  refuses a re-send whose `date`, `device` or `eventType` differs (400, reproduced).
- **API v3 and a body `_id`** (`dev` `47723cda`, since #8845): create, `PUT` and `PATCH` refuse a
  client-supplied `_id` with 400 (`lib/api3/shared/operationTools.js:197-203`, read), as I2 states.
  On `v15.0.9` a 24-hex body `_id` is stored as a string (BF-170, reproduced). v3 reads do not
  return `_id` (`lib/api3/storage/mongoCollection/utils.js:10-16`, read).
- **A devicestatus re-send with a stored `identifier`** (`dev` `47723cda`): API v1 stores a second
  record (no identifier match) and API v3 replaces the stored record and moves its `srvModified`
  (reproduced, the devicestatus study of 2026-10-26). I6's rule is on `dev` since #8859
  (`ID-SIMPLE-MATCH`).
- **A `null` in an update** (`dev` `47723cda`): a merge on match stores a field sent as `null` as
  `null` (`$set`), on every path, and `tests/api.profiles.resend.test.js:218` pins that. §3's
  removal is on `dev` since #8859, with BF-195's fix, for 16.0.0.
- **A re-send after delete** (measured 2026-10-18 at 15.0.8 and `fade2299`): API v1 deletes hard, so
  a re-send is stored again (with the same `_id` when the client sent one); API v3 `POST` brings a
  soft-deleted record back under the same `_id`, and `PUT` answers 410. §3's rule differs from all
  three and is not built.
- **Two records with one client identity** (`dev` `e1f7ac41`, reproduced): the chart's "Move
  insulin" and "Move carbs" store the split-off half with the original's `syncIdentifier`, `id`,
  `uuid` and `identifier`, which breaks I6 (BF-212).
- **`UUID_HANDLING`** (default on) moves a non-24-hex string `_id` to `identifier` on treatments and
  entries, as I9 describes (`lib/server/treatments.js:394-411`, `lib/server/entries.js:267-284` at
  official `a8888f0d`).
- **The write paths disagree.** A record created through one path and re-sent without `_id` through
  another is stored twice in 38 of 66 ordered path pairs (measured on `dev` `43289dde`;
  [write contract §0](../../tenancy/write-contract-spec-2026-10-07.md#0-summary)). The write step
  (`WRITE-CONTRACT`) is what makes §3 hold on every path.

What controllers send is in the [client id analyses](../../../10-domain/client-id-analysis/TRIO_ID_ANALYSIS.md),
the identifier format research §1, and the quirks registry: QUIRK-TREATMENTS-006 (Loop override
`_id`), QUIRK-ENTRIES-004 and QUIRK-TREATMENTS-007 (Trio's `id` member).

## 7. Conformance cases

20 cases, under `specs/sync/conformance/`. Checked by `tools/nsschema/test_registration_quirks.py`
and `tools/nsschema/test_registration_instances.py`; the reference functions check the cases, they
are not a hub.

| case | rule |
|---|---|
| `quirks/carrier-write-both-ids` | I4 |
| `quirks/carrier-hex-id-kept` | I2 |
| `quirks/carrier-resend-matches-objectid` | I2, I5 |
| `quirks/carrier-resend-identifier-first` | I5 |
| `quirks/carrier-resend-matches-identifier` | I5 |
| `quirks/carrier-uuid-id-moved` | I9 |
| `quirks/carrier-uuid-id-dropped` | I9 |
| `quirks/carrier-uuid-entries-moved` | I9 |
| `quirks/carrier-uuid-resend-matches` | I5, I9 |
| `quirks/typed-write-assigns-objectid` | I2, I3 |
| `quirks/typed-write-resend-same-ids` | I5 |
| `quirks/write-projected-read-only-by-objectid` | I8 |
| `quirks/write-stored-carrier-by-objectid` | I8 (control) |
| `instances/project-served` | I8 |
| `instances/write-projected-read-only` | I8 |
| `instances/write-stored-carrier` | I8 (control) |
| `instances/instance-invalid-id` | §2 instance id |
| `instances/definition-id-mismatch` | §2 definition id |
| `instances/dual-write-linked` | §2 dual-write link |
| `instances/dual-write-not-linked-across-instances` | §2 dual-write link |

Not covered by a case: I2's API v3 refusal (the carrier cases do not name an API version); I7 across two instances (`typed-write-resend-same-ids` re-sends from one
instance); §3's per-collection keys, which the write contract's gates measure against
cgm-remote-monitor rather than a reference function; and §4's format, which nothing enforces yet.
