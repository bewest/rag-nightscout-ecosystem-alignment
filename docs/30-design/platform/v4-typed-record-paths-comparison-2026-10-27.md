# API v4 typed record paths: Nocturne's routes with our rules, or paths of our own

*Contributor-facing. Snapshot, 2026-10-27: alignment `main` `ef5bfb426` (specifications), Nocturne
`main` `89dcaf1dd` (read in a detached worktree of `externals/nocturne`, fetched for this page),
xDrip+ `1ed760048` (`externals/xDrip`). Every Nocturne and xDrip+ statement was read from source and
nothing was run (read-derived); the API v3 measurements quoted from
[`tools/lab/nocturne-parity`](../../../tools/lab/nocturne-parity/README.md) are that lab's. Nocturne
paths are relative to `src/API/Nocturne.API/` unless they begin with `Core.` (under
`src/Core/Nocturne.`) or `Infrastructure.` (under `src/Infrastructure/Nocturne.Infrastructure.Data/`).
Operation counts were made by parsing `[Http*]` attributes and are read-derived. Nothing here has
been sent to either project. Supports decision 12 of
[v4 surface §7](v4-surface-and-nocturne-2026-10-26.md#7-open-decisions-for-the-maintainer).*

## 1. What is being decided

Decision 12 asks whether typed record writes and reads on API v4 start from Nocturne's v4 routes or
from paths we define. Records §3 already shares Nocturne's model: its sixteen primitives are
Nocturne's V4 classes ([records §3](spec/records.md#3-the-catalogue)). What is not shared is how a
typed write is addressed, matched, attributed and re-sent. The maintainer deferred the decision on
2026-10-26 because the identity decisions in the hub-implementer guide's backlog
(`ID-FORMAT-DECISION`, `ID-ABSENT-DECISION`, `ID-SCOPE-DECISION`, `ID-DELETE-REUSE-DECISION`,
[guide §5](guides/hub-implementer.md#5-identity-for-registered-instances)) decide how a typed write
is matched, and asked for a comparison of two options that can be benchmarked later:

- **Option 1, Nocturne's routes, our rules.** Start from Nocturne's typed-record route names and
  resource shapes, and require our identity rules as behaviour: identifier-first matching, upsert
  on re-send, an instance id on every typed write.
- **Option 2, paths of our own.** Paths built around registration's instance header
  ([registration §11](spec/registration.md#11-typed-writes-and-attribution),
  [§12](spec/registration.md#12-read-selection)) and records R1–R9, mapped onto Nocturne
  afterwards.

Option 2 has no paths yet. Where this page needs one to compare, it uses two sketches, labelled
**2a** (one path per primitive, our names) and **2b** (one path addressed by the registered element,
`<vendor>/<product>/<element>`, the channel form of [registration §9](spec/registration.md#9-channels-roles-and-provenance)).
They are illustrations for comparison, not proposals.

## 2. Nocturne's typed-record surface at `89dcaf1dd`

### 2.1 Controllers and routes

The v4 surface page's group G3 counts 24 controllers and 182 operations, including health series,
`Sleep`, `Battery`, `DeviceAge`, `Reservoir*`, `Foods` and `MealMatching`. The fourteen controllers
that carry the record primitives of records §3 declare or inherit 110 operations (parsed: own
`[Http*]` attributes, plus nine inherited per `V4CrudControllerBase` subclass and two per
`V4ReadOnlyControllerBase` subclass):

| controller | route | base | ops |
|---|---|---|---:|
| `SensorGlucoseController` | `api/v4/glucose/sensor` (`Controllers/V4/Glucose/SensorGlucoseController.cs:34`) | CRUD | 9 |
| `BGCheckController` | `api/v4/observations/bg-checks` (`Glucose/BGCheckController.cs:29`) | CRUD | 9 |
| `MeterGlucoseController` | `api/v4/glucose/meter` (`Glucose/MeterGlucoseController.cs:31`) | CRUD | 9 |
| `CalibrationController` | `api/v4/glucose/calibrations` (`Glucose/CalibrationController.cs:27`) | CRUD | 9 |
| `BolusController` | `api/v4/insulin/boluses` (`Treatments/BolusController.cs:33`) | CRUD, plus `DELETE by-sync-id` (`:159`) | 10 |
| `BasalInjectionController` | `api/v4/insulin/basal-injections` (`Treatments/BasalInjectionController.cs:39`) | CRUD, plus `DELETE by-sync-id` (`:142`) | 10 |
| `BolusCalculationController` | `api/v4/insulin/calculations` (`Treatments/BolusCalculationController.cs:27`) | CRUD | 9 |
| `NoteController` | `api/v4/observations/notes` (`Treatments/NoteController.cs:28`) | CRUD, plus `DELETE by-sync-id` (`:76`) | 10 |
| `DeviceEventController` | `api/v4/observations/device-events` (`Devices/DeviceEventController.cs:39`) | CRUD, plus `DELETE by-sync-id` (`:181`) | 10 |
| `NutritionController` | `api/v4/nutrition` (`Treatments/NutritionController.cs:49`): `carbs`, `carbs/{id}`, `carbs/bulk` (`:154`), `carbs/by-sync-id` (`:261`), `carbs/{id}/foods`, `meals` (`:398`, `:518`) | hand-written | 13 |
| `TempBasalController` | `api/v4/insulin/temp-basals` (`Treatments/TempBasalController.cs:31`): list, get, `POST` an array (`:103`) | hand-written | 3 |
| `ApsSnapshotController` | `api/v4/device-status/aps` (`Devices/ApsSnapshotController.cs:28`), `POST` an array (`:47`) | read-only, plus `POST` | 3 |
| `PumpSnapshotController` | `api/v4/device-status/pump` (`Devices/PumpSnapshotController.cs:27`), `POST` an array (`:46`) | read-only, plus `POST` | 3 |
| `UploaderSnapshotController` | `api/v4/device-status/uploader` (`Devices/UploaderSnapshotController.cs:27`), `POST` an array (`:46`) | read-only, plus `POST` | 3 |

The route pattern is `api/v4/<category>/<kebab-case plural>`, with three categories in use for
primitives (`glucose`, `insulin`, `observations`) and two more for nutrition and device status. The
four settings primitives and `TherapySettings` are under the profile controllers (G5), and
`StateSpan` under `api/v4/state-spans` (G4); neither is compared here. `CarbIntake` is
`nutrition/carbs`.

### 2.2 What the base controllers give

`V4ReadOnlyControllerBase` (`Controllers/V4/Base/V4ReadOnlyControllerBase.cs`):

| op | route | notes |
|---|---|---|
| `GetAll` | `GET /` (`:43`, `:47`) | `from`, `to`, `limit` (default 100), `offset` (default 0), `sort` (`timestamp_desc` or `timestamp_asc`, else 400, `:76-77`), `device`, `source` (`:48-51`) |
| `GetById` | `GET /{id:guid}` (`:92`, `:96`) | 404 when absent |

`V4CrudControllerBase` (`Controllers/V4/Base/V4CrudControllerBase.cs`) adds seven:

| op | route | notes |
|---|---|---|
| `Create` | `POST /` (`:85`, `:92`) | one record; 201 with `Location`; a `(dataSource, syncIdentifier)` held by a record the owner deleted is 409 (`:81-83`; `Filters/RecreationBlockedFilter.cs:36`) |
| `CreateBulk` | `POST /bulk` (`:127`, `:132`) | at most 1000 (`V4BulkValidation.cs:27`); "per-item, not all-or-nothing" (`:114`); 201 with the written records |
| `Update` | `PUT /{id:guid}` (`:162`, `:169`) | by hub id; 404 when absent |
| `Delete` | `DELETE /{id:guid}` (`:199`, `:205`) | soft delete; 204 or 404 |
| `ListDeleted` | `GET /deleted` (`:228`, `:233`) | the recycle bin, gated on the write scope "although it reads" (`:223-226`) |
| `Restore` | `POST /{id:guid}/restore` (`:255`, `:262`) | 409 when a live record now holds the key |
| `BulkRestore` | `POST /restore` (`:287`, `:293`) | restored and conflicting ids listed separately |

Every write is gated on the controller's declared write scope (`:50`, `WriteScope`), and every read
on the class-level category scope: `glucose.read` / `glucose.readwrite`, `treatments.read` /
`treatments.readwrite`, `devices.read` / `devices.readwrite` (`Core.Core.Models/Authorization/Scope.cs:31-39`).

### 2.3 Paging and envelope

A list answers `PaginatedResponse<T>`: `{data, pagination: {limit, offset, total}}`
(`Core.Core.Models/V4/PaginatedResponse.cs:8-27`). `limit` is clamped to 100,000 rather than refused
(`V4ReadLimits.cs:16-18`, `:33`); a `from`–`to` span over 366 days is 400 (`:65`). Paging is by
offset over a timestamp sort. `total` is counted over `from` and `to` only
(`V4ReadOnlyControllerBase.cs:58`), while the page also filters by `device` and `source` (`:57`).
Errors are RFC 7807 problem details (`Problem(...)` throughout, e.g. `V4BulkValidation.cs:45`).

There is no modified-since read on the typed routes: the list parameters are the seven above, and
no v4 typed controller takes a cursor (searched for `since`, `modified`, `cursor` on `[FromQuery]`
under `Controllers/V4`). Records carry `ModifiedAt` (`Core.Core.Models/V4/IV4Record.cs:97`). Change
delivery for v4 records is a SignalR broadcast of `create`, `update` and `delete` events per
category (`Core.Core.Contracts/Events/IV4RecordBroadcaster.cs:15-25`). A modified-since read exists
for the legacy projection that serves API v3 history
(`Services/V4/V4ToLegacyProjectionService.cs:113`).

### 2.4 How a write is matched and re-sent

- **Hub id.** Every record's `Id` is a hub-assigned UUID v7 (`IV4Record.cs:36-39`); every by-id
  route constrains it as `{id:guid}`.
- **Sync key.** The upsert key is `(DataSource, SyncIdentifier)` within the tenant
  (`Models/Requests/V4/IBulkUpsertRequest.cs:14-18`), backed by a partial unique index on
  `(tenant_id, data_source, sync_identifier)` (`Infrastructure.Repositories/V4/SyncUpsertRepositoryBase.cs:189-191`).
  A bulk item with `SyncIdentifier` and no `DataSource` is 400 (`V4BulkValidation.cs:89-90`).
  `IV4Record` itself has no `SyncIdentifier` member; it is on the types that have one.
- **Which types upsert.** Twelve repositories derive from `SyncUpsertRepositoryBase`: bolus, basal
  injection, sensor glucose, BG check, note, device event, carb intake, temp basal, the three
  snapshots and profile activation (parsed from `Infrastructure.Repositories/V4/`). Calibrations,
  meter readings and bolus calculations always insert (`V4CrudControllerBase.cs:114-119`).
- **Single create is an upsert too.** `CreateAsync` is sealed to `UpsertAsync`
  (`SyncUpsertRepositoryBase.cs:68`, `:72-101`): a matched live row is updated in place. The
  repository reports whether it inserted (`SyncUpsert<T>(Record, Created)`,
  `Core.Core.Contracts/V4/Repositories/ISyncKeyedRepository.cs:49`); the controller answers 201
  either way (`V4CrudControllerBase.cs:107`).
- **Bulk.** Items without both halves of the key are never collapsed; within a batch the last item
  per key wins (`SyncUpsertRepositoryBase.cs:168-175`). An item whose key is held by a deleted
  record is skipped and absent from the response; for a one-item array the answer is 201 with an
  empty array (`TempBasalController.cs:91-96` states it for every v4 bulk endpoint). The response is
  the array of written records; no per-item outcome or match key is returned.
- **A matched upsert moves the record's timestamp** to the new one (`ISyncKeyedRepository.cs:34-36`).
- **Without a key** a create inserts. Sensor glucose then runs post-commit deduplication that links
  rows to canonical groups (`Infrastructure.Repositories/V4/SensorGlucoseRepository.cs:473-478`).
- **Update by id** maps the whole record. `BolusController` takes `SyncIdentifier` from the request
  (`Treatments/BolusController.cs:129`); `SensorGlucoseController` keeps the stored one
  (`Glucose/SensorGlucoseController.cs:144`).

### 2.5 Deletes and tombstones

Deletes are soft. A deleted record holds its sync key: a re-create is 409 on the single path and
skipped on the bulk path, and the owner brings it back with `Restore` (`V4CrudControllerBase.cs:81-83`,
`:255`). Five types also delete by sync key with `dataSource` and `syncIdentifier` as query
parameters (§2.1). `TempBasal` and the three snapshots have no v4 delete or update. On the v3
history projection a deleted treatment is served with `isValid: false`
(`Services/V4/LegacyTreatmentTables.cs:953-954`).

### 2.6 How a record names its writer

The record carries three client-supplied strings: `Device`, `App` and `DataSource`
(`IV4Record.cs:60-73`); the request maps them from the body (`BolusController.cs:91-93`). The
authenticated subject, token id and auth type go to the mutation audit log, not to the record
(`Core.Core.Contracts/Audit/IAuditContext.cs:9-13`). Device attribution (`PatientDeviceAttribution`,
`BolusController.cs:149-151`) links a record to a patient device; the snapshots are not attributed
(`ApsSnapshotController.cs:43-45`).

### 2.7 Decomposition and projection

API v1–v3 treatment writes reach the typed tables through the decomposers. A treatment's identity is
its `_id`, else its `syncIdentifier`, else a hash of its defining fields
(`Services/V4/TreatmentDecomposer.cs:130-159`). Reads of v1–v3 treatments are projected from typed
records: "every treatment read projects records of both provenances, since treatments have no legacy
table left" (`V4ToLegacyProjectionService.cs:29`). A projected treatment's id is the typed record's
UUID as a string (`LegacyTreatmentTables.cs:961`) and it carries `syncIdentifier` (`:978`). Whether a
v1–v3 write aimed at a projected treatment is refused or edits the typed record was not checked.

### 2.8 A client written against these routes

xDrip+ `1ed760048` has a Nocturne uploader (`app/src/main/java/com/eveningoutpost/dexdrip/nocturne/NocturneUploader.java`,
717 lines; `NocturneOAuthService.java`, 454) built on a generated SDK,
`org.nightscoutfoundation:nocturne-java:0.2.4` (`app/build.gradle:281`). Read from it:

- `DATA_SOURCE = "xdrip"` for treatments (`:76`); sensor glucose sends the collection method
  preference as `dataSource` (`:484`) and no `syncIdentifier` (`:476-492`), so its readings carry no
  sync key.
- A treatment with several doses uploads under suffixed sync identifiers, `uuid`, `uuid-2`, …
  (`:686-687`).
- A delete tries four resources by sync key in turn, because "a treatment's uuid may exist in any of
  these resources" (`:324-341`); its comment says basal injections have no delete by sync key "yet
  (pending upstream)" (`:329-330`), which `89dcaf1dd` now has (`BasalInjectionController.cs:142`).

## 3. What our specifications require of a typed write and read

| concern | requirement | anchor |
|---|---|---|
| instance id | a hub that advertises `instances` requires an instance id on every typed write, proposed as a request header; without one, 422 `instance-required`, a definite refusal; the instance must be live (409 `not-live`) and hold `source` on the element's channel (409 `role-held` / `role-not-granted`) | [registration §11](spec/registration.md#11-typed-writes-and-attribution) |
| attribution | an accepted typed record carries its instance, definition and the role's provenance; writes with no instance go to an implicit unregistered instance of the product; a namespace string proves nothing | registration §11; [§9](spec/registration.md#9-channels-roles-and-provenance) |
| two ids | `identifier` is the controller's record id in the typed API; `_id` is the hub's | [identity I1](spec/identity.md#1-rules) |
| reply | every write answers per item `identifier`, `_id` and `matchedBy`; on a typed write this is `write.ids`; a duplicate is never a 5xx or an empty acknowledgement | identity I4 |
| re-send | matches on `identifier` first; a matched re-send stores no second copy and answers with the stored ids, so a client keeps no cache of server ids | identity I5, I6 |
| match scope | a typed write matches a stored typed record of the same `(vendor, product)` with the same `identifier`, whichever instance sent it | identity I7; the typed index on `(vendor, product, identifier)`, [guide §5](guides/hub-implementer.md#5-identity-for-registered-instances) |
| identifier form | opaque, URL syntax, source and app schemes; C1–C7 proposed (256 characters, `A-Z a-z 0-9 - . _ ~ : /`) | [identity §4](spec/identity.md#4-the-identifier-format); [identifier conventions §2](identifier-conventions.md#2-the-rule-the-server-states) |
| identifier mandatory | for registered instances and at a future version boundary | [identifier conventions §1](identifier-conventions.md#1-decisions) decision 1 |
| one write step | every path writes through one step with outcomes `inserted`, `merged`, `replaced`, `unchanged`, `deleted`, `not-found`, `refused` | [sync-transport T1–T2](spec/sync-transport.md#2-the-write-path) |
| batch | `POST /api/v3/batch` takes `[{collection, doc}]`, answered per item, idempotent per record (proposed; typed batch not specified) | [sync-transport T7](spec/sync-transport.md#4-the-sync-read-and-write-proposed) |
| sync read | one history read across collections with an opaque cursor and a low watermark; a page carries the definitions its records need | sync-transport T5, T6, T8, T9, T14 |
| socket | subscribe by product and channel; each event carries the record, both ids, definition, instance, provenance and the cursor | [sync-transport T11](spec/sync-transport.md#5-typed-records-on-the-socket-proposed) |
| versions | a stored record keeps its `definitionId`; a re-send under a new definition with the same `identifier` replaces it | [sync-transport T13, T15](spec/sync-transport.md#6-definitions-and-versions-proposed) |
| read selection | per versioned element: capability limit, owner's pin, newest version run by a live `device` source, newest stored; a label selector narrows to matching instances | [registration §12](spec/registration.md#12-read-selection) |
| projected views | a served element is projected to v1 and v3 as a carrier-shaped document labelled `projectedFrom`, read-only (409 `projected-read-only`), with an ObjectId `_id` assigned at the typed write | [registration §13](spec/registration.md#13-projected-views-for-older-readers); identity I8 |
| composite on the wire | the hub keeps the composite and decomposes it into primitives; decomposition is declared by the registration | [records R1–R3](spec/records.md#2-rules) |
| permissions | our specifications name `api:registrations:*` and `api:commands:create`; no permission name for a typed write | [authority](spec/authority.md) (searched) |

The proposed OpenAPI file lists no typed record operation
([`specs/openapi/proposed/nightscout-v4.yaml`](../../../specs/openapi/proposed/nightscout-v4.yaml),
`info.description`). The conformance cases model a typed write without a path: `identity`
(vendor, product), `write.element` (`stateSpans/ExampleOverride`), `write.instanceId` and
`recordId` (`specs/sync/conformance/instances/typed-write-attributed.yaml`;
`specs/sync/conformance/quirks/typed-write-resend-same-ids.yaml`). Either option can be bound to them.

## 4. Side by side

"Cost" is the work the option leaves for our specifications, cgm-remote-monitor, or a shared
contract; "compatibility" is what a client of the other hub sees.

| concern | Option 1: Nocturne's routes, our rules | Option 2: paths of our own | compatibility consequence |
|---|---|---|---|
| **path shape** | fixed: `api/v4/<category>/<plural>`, fourteen roots for the primitives (§2.1), two write forms (`POST /` + `POST /bulk`, or `POST /` taking an array) | free: 2a one root per primitive; 2b one root per registered element; either can be advertised in the capability document as commands' `fetch` is (a URI template, [registration §4](spec/registration.md#4-the-capability-document)) | Option 1: a client written for Nocturne (xDrip+ §2.8) reaches both hubs on the same paths; Option 2: needs an alias table or a discovered template on one side |
| **resource naming** | Nocturne's names (`bg-checks`, `meter`, `calculations`, `device-status/aps`); `CarbIntake` is `nutrition/carbs` | records §3's primitive names, or element ids | records §3 already uses Nocturne's class names, so 2a can match names without matching categories |
| **coverage beyond primitives** | none for controller-owned extensions or versioned kinds: Nocturne's types are a closed set | 2b addresses any accepted element, including extensions ([registration §3](spec/registration.md#3-the-grammar), G2, G4) | Option 1 needs a second path family for extensions; 2b has one family for both |
| **create and upsert** | Nocturne already upserts on a key for twelve types (§2.4); the rule to change is the key (identifier-first, I5) and the three types that always insert | specify once: every typed create is an upsert on `identifier` (I5, I7) | under Option 1 the same route has two match rules on two hubs until both agree; a test fixture that passes on one can fail on the other |
| **per-item reply** | Nocturne answers records, 201 always, skipped items absent (§2.4); our I4 needs `identifier`, `_id`, `matchedBy` per item | `write.ids` per item from the start (I4) | Option 1 changes the response body of existing Nocturne routes, or adds a header/field next to it; xDrip+ ignores the body of its bulk call (`NocturneUploader.java:195`) |
| **batch** | per type, `POST …/bulk`, 1000 items; a mixed cycle is one request per type | can be per type or one typed batch across types (as T7 does for v3) | round trips per cycle differ (benchmark B3) |
| **identity match** | key becomes `identifier` within `(vendor, product)`; `DataSource` is a body string today and half of Nocturne's key | key is `(vendor, product, identifier)` (guide §5) | Option 1 must say which wins when the body's `dataSource` and the instance's product disagree (§7, Q3) |
| **writer attribution** | add the instance header to routes whose bodies already carry `device`, `app`, `dataSource` | the instance header is the attribution; body strings are data | under both, a client that sends no header is the product's unregistered instance (registration §11); Option 1 keeps three body strings that registration says prove nothing |
| **hub id** | `{id:guid}`, UUID v7 | the hub's `_id`; identity I2–I3 fix 24-hex only on legacy surfaces, so v4 may use another form | a by-id route works only with the id that hub assigned; I5 makes that rare for a sync client |
| **read by identifier** | Nocturne reads by sync key only through delete; a by-identifier read needs a new route or a query parameter (`identifier` is not a GUID) | define it; identifiers with `/` and `:` go percent-encoded as one segment (C3), or as a query parameter as Nocturne's `by-sync-id` does | a query parameter avoids proxies that refuse `%2F`, which were not measured ([conventions §2](identifier-conventions.md#2-the-rule-the-server-states)) |
| **read, query, paging** | `from`, `to`, `limit`, `offset`, `sort`, `device`, `source`; `{data, pagination}`; offset paging, `total` | open; T6's cursor rules exist for history | a shared list contract has to settle the envelope either way; v3 already differs between the two hubs (lab question 2) |
| **read selection** | no slot for a definition or version; §12's choice would be a query parameter or header | built in: element and version are part of the address (2b) or the query (2a) | without it, a reader of a versioned element on Option 1 sees whatever was stored last |
| **deletes and tombstones** | Nocturne: soft delete, deleted key refused on re-create, recycle bin and restore (§2.5); five types also delete by key | `ID-DELETE-REUSE-DECISION` is open; cgm-remote-monitor v3 resurrects a soft-deleted record on `POST` (identity §5) | adopting the routes brings Nocturne's answer (refuse) with them, which is one of the three options the decision lists |
| **sync** | no modified-since or cursor on typed routes; SignalR events; history only through the v3 projection (§2.3) | T5–T10 and T14 apply to typed records by design | under Option 1 a typed-record cursor is new on both hubs; under Option 2 it is new on Nocturne |
| **projection to v1–v3** | both hubs project typed records to v1–v3; Nocturne's projected id is the record's UUID (`LegacyTreatmentTables.cs:961`), ours is an ObjectId assigned at the typed write (I8) with `projectedFrom` and 409 `projected-read-only` | the same rules; path choice does not change them | a legacy client sees a 36-character `_id` on one hub and a 24-hex one on the other under either option (v1 by-id routes understand UUID and ObjectId shapes, [conventions §2](identifier-conventions.md#2-the-rule-the-server-states)) |
| **auth scopes** | three category scopes per direction (`glucose`, `treatments`, `devices`) | unnamed today; cgm-remote-monitor's permissions are `api:<collection>:<action>` | a shared contract needs a mapping table under either option; Option 1 makes Nocturne's categories the grouping |

## 5. What each party would do

### 5.1 A client

| client today | Option 1 | Option 2 |
|---|---|---|
| Loop (NightscoutKit `4ec9fd12a1`, v1, 7 endpoints) and Trio (`0b29cd5341`, v1, 5 endpoints), per [sync-transport §3](spec/sync-transport.md#3-what-each-clients-sync-code-can-call) | adopt Nocturne's per-type routes, send `identifier` (the conventions table gives `loop://…` templates) and the instance header; one request per type per cycle, or the bulk route per type | adopt our paths; the same identifier and header; one request per type (2a) or per element (2b), or one batch if a typed batch is specified |
| AndroidAPS (`7e1d537d49`, v3, 26 endpoints, delta read per collection) | as above; its delta reads have no typed equivalent on either hub yet (§2.3) | as above, with T5/T6 for reads once served |
| xDrip+ (`1ed760048`): a Nightscout uploader and a separate Nocturne v4 uploader (§2.8) | its Nocturne uploader works on both hubs once cgm-remote-monitor serves the routes; it adds `syncIdentifier` → `identifier`, the instance header, and a sync key for readings, which it does not send today | it keeps one uploader per hub until Nocturne serves our paths or an alias |

Under both options a client registers its product and instance first (registration §5, §8) and
reads the capability document at launch. Under both, the identifier convention it follows is the
same table; neither option changes what the identifier is.

### 5.2 A hub implementer

- **cgm-remote-monitor, Option 1.** Serve Nocturne's route set for the primitives (110 operations
  on fourteen controllers by the parse in §2.1, or a declared subset), with its envelope and paging,
  behind S3's checks ([guide §4.4](guides/hub-implementer.md#44-s3-typed-writes-attribution-and-read-selection)).
  The extension path family and read selection are designed separately.
- **cgm-remote-monitor, Option 2.** Serve our paths behind the same S3 checks. Nocturne compatibility,
  if wanted, is an alias layer from Nocturne's routes onto ours.
- **Nocturne, Option 1.** Its routes stay. Behaviour changes: identifier-first matching with
  `(vendor, product)` scope, a per-item reply, an instance header, a typed-record cursor; the three
  always-insert types upsert. Issue [#1932](https://github.com/nightscout/nocturne/issues/1932)
  (open since 2026-09-30) records the same identifier and upsert question for its API v3 `POST`.
- **Nocturne, Option 2.** Serve our paths beside its own, mapped onto the same repositories; the
  behaviour changes above apply to the new paths.

## 6. Benchmark plan

A plan, not built. Each criterion names a measurement, a control that must fail when the property
is broken, and the existing tool that could host it. Every run records both hubs' commits.

| # | criterion | measured as | control (must fail) | host |
|---|---|---|---|---|
| B1 | conformance | the path-free typed-write and quirk cases (13 typed and carrier cases under `specs/sync/conformance/instances/`, `typed-write-resend-same-ids`, `typed-write-assigns-objectid`) run through a path binding per option, against a cgm-remote-monitor branch and Nocturne; cases passed, by name | a hub with the identifier match removed fails `typed-write-resend-same-ids` | `tools/nsschema/test_registration_instances.py` (cases), a new binding; `tools/lab/nocturne-parity/run.sh` (boots Nocturne at a pinned commit) |
| B2 | re-send correctness | scripted sequences: retry after a lost response, edit then re-send, intra-batch duplicate, two instances of one product, two products with one identifier, delete then re-send; stored count, reply ids and `matchedBy` | send the second write with a new identifier: two stored records expected | `tools/lab/nocturne-parity/probe.js` extended to v4 (it probes v1 and v3 today) |
| B3 | round trips per sync cycle | requests per 5-minute cycle for three synthetic workloads (CGM-only uploader; Loop-like: reading, decomposed device status, occasional bolus and carbs; AndroidAPS-like with delta reads) | none needed; the count is the result, checked against a hand count for one cycle | `tools/nsschema/sync_cost.py` (declared endpoints) plus a request counter in the probe |
| B4 | payload size | request and response bytes per cycle, same workloads | a response that omits per-item ids must come out smaller than one that carries them | same probe |
| B5 | client cost to target both hubs | endpoints a client must declare, and lines in a reference client, to sync one workload to both hubs; baseline: xDrip+'s Nocturne uploader (717 lines, §2.8) | — | `tools/nsschema/sync_cost.py` |
| B6 | query latency | p50/p95 of typed list reads by time range and by identifier over the replay corpus loaded into each hub, after warm-up | the same read against an empty store must not be reported as a pass (record the row count of every answer) | `tools/seam` differential harness pattern (`v1-http-differential.js`); corpus loaders in `tools/nsschema/corpus.py` |
| B7 | projection fidelity | write typed on v4, read on v1 and v3, compare with the carrier document a legacy client wrote for the same event | a projection with `eventType` dropped fails | `tools/lab/nocturne-parity/compare.js`; `tools/nsschema/replay.js` for schema acceptance |
| B8 | sync completeness | a typed-record client under concurrent writes misses no record and keeps one copy per version | the 13 sync-transport cases' timelines, run against a hub with the low watermark removed | `tools/nsschema/sync_cursor.py` cases as scripts against live hubs |
| B9 | refusal vocabulary | each reason code a typed write can get (`instance-required`, `not-live`, `role-held`, `role-not-granted`, `projected-read-only`, the deleted-key refusal) mapped to the status and body each option gives | a hub that answers 200 to an instance-less typed write fails | B1's binding |

Non-vacuity, per run: read the status mix and stored counts before reading "0 mismatches", as
[`tools/seam/DIFFERENTIALS.md`](../../../tools/seam/DIFFERENTIALS.md) records for its two vacuous
first runs. Not measurable until a hub serves typed writes with our rules: B1, B2 and B9 on
cgm-remote-monitor (S3 is blocked on `WC-STEP-PATCH`, guide §5). Measurable against Nocturne alone
today: B2, B3, B4, B6 and B7 for its current behaviour, as a baseline.

## 7. Open questions the identity decisions settle

| # | question | settled by | Option 1 | Option 2 |
|---|---|---|---|---|
| Q1 | may a typed record id contain `/` and `:` (C3), and is it read in a path segment or a query parameter? | `ID-FORMAT-DECISION` | Nocturne's by-key routes use query parameters | either |
| Q2 | is `identifier` required on every typed write by a registered instance, and is a keyless typed write refused or inserted? | `ID-ABSENT-DECISION` | Nocturne inserts without a key today (§2.4) | specify the refusal |
| Q3 | what is the match scope: `(vendor, product)` (I7), the writer's `DataSource`, the tenant, or across products? Identifier conventions decision 2 says two apps reading one sensor send the same identifier; I7 and Nocturne's key both scope the match to the writer, so two products' copies of one reading are not matched under either | `ID-SCOPE-DECISION`; D20 choice 7 | decide what `dataSource` becomes: derived from the instance's product, kept as body data, or dropped from the key | the typed index on `(vendor, product, identifier)` |
| Q4 | after a delete, does a re-send resurrect, get refused, or create new? | `ID-DELETE-REUSE-DECISION` | Nocturne refuses and offers restore (§2.5) | open |
| Q5 | on an identifier match, may the record's time change? | `ID-V3-IMMUTABLE-DECISION` | Nocturne's upsert moves the timestamp (`ISyncKeyedRepository.cs:34-36`) | open |
| Q6 | is `identifier` null in the reply when none was sent? | D20 choice 6 | Nocturne returns its own UUID and no identifier | I4 states null |
| Q7 | what is the header's name, and does it also mark a registered instance's carrier writes? | registration §11; `ID-ABSENT-DECISION` (how a hub recognises a registered instance on a legacy path) | same question | same question |
| Q8 | are typed paths discovered from the capability document, as commands' `fetch` is? | not an identity decision; registration §4 | discovery would let Nocturne keep its names and still be found | discovery would let clients follow either hub's names |

## 8. How this was produced

- Nocturne: `git -C externals/nocturne fetch`, then a detached worktree at `89dcaf1dd` in the
  session's scratch directory (`externals/nocturne` itself is at `42275c812`). Controllers read by
  hand; the operation count in §2.1 parsed `[HttpGet|Post|Put|Delete|Patch]` lines in the fourteen
  controller files and added nine per `V4CrudControllerBase` subclass and two per
  `V4ReadOnlyControllerBase` subclass. The repository list in §2.4 is `grep -l SyncUpsertRepositoryBase<`.
- Nocturne issue #1932 read with `gh issue view 1932 -R nightscout/nocturne` (open, no comments).
- xDrip+ read at `1ed760048` in `externals/xDrip`; line counts by `wc -l`.
- Our side read at `ef5bfb426`: the specifications under [`spec/`](spec/), the identifier
  conventions, the hub-implementer guide, the proposed OpenAPI file, the conformance cases and the
  nocturne-parity lab's README.
