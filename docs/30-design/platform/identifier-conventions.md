# Identifier conventions: one `identifier` per real thing

*Contributor-facing. **Living draft**, as of 2026-10-30. Decisions recorded here are the
maintainer's of 2026-10-18, with the scope and absent-identifier decisions of 2026-10-27 and the
format decisions of 2026-10-29 (D-LOOP-ID rule 1 and ID-Q6, in the
[16.0.0 decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md)) marked where they
apply; the templates in §4 are proposals unless a cell says otherwise. Read
after the [identity specification](spec/identity.md) (L0), whose format section this page fills in.
Evidence: [identifier format research](../../60-research/tenancy/identifier-format-2026-10-17.md)
(§1 per-app identity, §3.4 URL-form identifiers measured, §7 the G7 counter) and
[identifier duplicates](../../60-research/tenancy/identifier-duplicates-2026-10-17.md). Queue:
`ID-CONVENTIONS`, `ID-FORMAT-DECISION`, `ID-ABSENT-DECISION`, `ID-SCOPE-DECISION`.*

`identifier` names the real thing a record describes (this CGM reading, this pump event, this carb
entry), written in URL syntax whose scheme says where the thing comes from: the manufacturer for
things that exist outside any app (`dexcom://g7/<serial>/<offset>`), the app for things made inside
it (`loop://carbs/<uuid>`). The server treats the value as opaque, enforces one record per
identifier in each collection and publishes the limits; clients compute the values, and this table
is how two apps that see the same sensor or pump arrive at the same value. Measured 2026-10-18 at
15.0.8 and dev: URL-form identifiers work on API v3 when percent-encoded as one path segment, and
on API v1 `find[identifier]=`; a raw `/` in a v3 path is 404.

Marks: **[R]** read from code at the commit given; **[M]** measured (the cited page says how);
**[proposed]** a template or rule for the maintainer and client developers to confirm;
**[decided]** the maintainer's decision of 2026-10-18, or of the date given.

## 1. Decisions

| # | decision | status |
|---|---|---|
| 1 | **`identifier` becomes mandatory** at a future version boundary, and for registered instances of controllers ([registration §8](spec/registration.md#8-instances)). Until then the legacy paths keep the time-key fallback for a write that carries none (entries `sysTime` + `type`, treatments `created_at` + `eventType`). The version boundary and how a hub tells a registered instance's writes apart are open (`ID-ABSENT-DECISION`). Until the boundary, `identifier` is SHOULD for legacy writers and MUST for registered controller instances (2026-10-27); what a hub answers a registered instance's write without one is open ([identity §5](spec/identity.md#5-open-decisions), `ID-REGISTERED-NO-IDENTIFIER`). | [decided] |
| 2 | **Meaning.** `_id` identifies the stored record (uniqueness in the database). `identifier` is the record's semantic identity in the data model: two uploads of the same real thing carry the same identifier, whichever device or app sends it. The server enforces uniqueness and states the format; clients compute the values. This refines the wording of D20 rule 5 ("the sync identity the client assigns") without changing its mechanics. | [decided] |
| 3 | **Format.** Opaque to the server, one rule for every collection, plus this published table per record kind so different apps converge on one value. URL syntax: `<scheme>://<segment>/<segment>/…`. | [decided] |
| 4 | **Scheme.** Things that exist outside the app (sensor readings, pump events) use a **source scheme**: the manufacturer is the scheme and the model is the first segment (`dexcom://g7/…`, `dexcom://g6/…`, `abbott://libre3/…`). Things created inside an app (manual carbs, boluses, overrides, temporary targets, device status) use an **app scheme** (`loop://carbs/…`). | [decided] |
| 5 | **A controller's own format.** A controller may use one format of its own across collections for the records it creates, for example `loop://carbs/<uuid>`, `loop://tempbasal/<syncId>`, `loop://override/<uuid>`, `loop://devicestatus/<uuid>`. Constraints: unique per collection, within the limits of §2, stable across re-sends. A registered instance declares the format it uses (§5). | [decided] |

**Why a source scheme.** The maintainer's first example, `loop://g7/<serial>/<sensor offset>`,
names the uploading app. Loop and xDrip+ reading one G7 would then produce two identifiers for one
reading, which is the opposite of what decision 2 asks. With the manufacturer as the scheme, every
app that reads the sensor's own serial and counter produces the same bytes. One scheme per vendor
covers all its models, serial numbers are a manufacturer's namespace, and the shape matches
`loop://g7/…`.

**Scope, decided (maintainer, 2026-10-27; `ID-SCOPE-DECISION`).** Uniqueness is per collection,
with the tenant in the key under multi, while values are globally unique by convention: the kind
segment (`carbs`, `tempbasal`, `devicestatus`, or the model for a source scheme) keeps two
collections from ever holding the same value. Each collection's partial unique index on
`identifier` is in 16.0.0 under `WRITE_IDENTIFIER_INDEX=try|require|off` (maintainer, 2026-10-30;
[identity §3](spec/identity.md#3-match-order-per-collection)).

**The kind segment fixes a measured hazard.** 13 Loop `syncIdentifier` values are each on 2 to 4
treatments in the corpus; 9 of them are a Suspend Pump and a Temp Basal at the same `created_at`
([identifier duplicates §2.2](../../60-research/tenancy/identifier-duplicates-2026-10-17.md#22-syncidentifier-on-treatments-as-a-proxy-m)) [M].
Sent as `identifier` today, the second would replace the first. `loop://suspend/<id>` and
`loop://tempbasal/<id>` differ. The other 4 values are Temp Basals only (groups spread over more
than a day, and one pair 1 s apart); a kind segment does not separate those, and the cause on
Loop's side is not known.

## 2. The rule the server states

| # | constraint | status |
|---|---|---|
| C1 | a JSON string with at least one non-whitespace character | enforced on API v3 create today [R] |
| C2 | at most 256 characters; a longer value is treated as absent, with a warning | [decided] 2026-10-29 (D-LOOP-ID rule 1, ID-Q6); an indexed value near 1 KB fails the insert on MongoDB before 4.2 [M] |
| C3 | characters from `A-Z a-z 0-9 - . _ ~ : /`; no `%`, `?`, `#`, space or control characters | [proposed] as the set clients build values from; the server applies no character restriction and an identifier in a URL path is percent-encoded ([decided] 2026-10-29, ID-Q6). `/` and `:` are in the set because the URL form needs them and the measurement below holds |
| C4 | not exactly 24 hex characters, unless it equals the record's own `_id` | [proposed]; both APIs read a 24-hex value as an `_id` too [R] |
| C5 | not `history`, `.` or `..`, and no client placeholder (`invalid`, `undefined`, `null`, `NaN`, `unknown`) | placeholders: [decided] 2026-10-29 (ID-Q6) for `undefined`, `null`, `invalid` and an empty string, which the server treats as absent with a warning (refused under `WRITE_IDENTIFIER=strict`); `NaN` and `unknown` are open ([identity §5](spec/identity.md#5-open-decisions), `ID-PLACEHOLDER-LIST`); the path words are [proposed] |
| C6 | one identifier, one record, per collection, for as long as the record is stored | identity rule I6 |
| C7 | compared exactly: case-sensitive, never trimmed or normalised | identity rule I6 |
| C8 | URL syntax `<scheme>://<segments>`: scheme lower case, `[a-z][a-z0-9+.-]*`; segments separated by `/`; no empty segment | [proposed]; the server does not parse it, so this is a convention for clients, not a check |

**Writing one in an API v3 path.** Percent-encode the whole identifier as **one path segment**
(`encodeURIComponent` in JavaScript: `:` becomes `%3A`, `/` becomes `%2F`). At 15.0.8 `92d08342`
and dev `fade2299`, an encoded URL-form identifier works on v3 GET, PATCH, PUT (update and create)
and DELETE, `?identifier$eq=` search finds it, and v1 `find[identifier]=` finds it encoded or raw;
a raw `/` in the path is 404 [M, [§3.4](../../60-research/tenancy/identifier-format-2026-10-17.md#34-url-form-identifiers-end-to-end-2026-10-18-m)].
A path helper that leaves `/` unescaped (Foundation's `urlPathAllowed` set allows `/`) builds the
wrong route. v1 by-id routes (`DELETE /api/v1/treatments/:id`, `find[_id]=`) understand UUID- and
ObjectId-shaped values only, so a client deletes over v1 with the `_id` the write reply returns.
Reverse proxies that decode or refuse `%2F` were not measured; behind one, reads work through
search and `find[identifier]=`.

**Build the string, do not normalise it.** In RFC 3986 terms the first segment after `//` is the
authority; some URL libraries lower-case or re-encode it. Clients should build the value by
concatenation from the convention's parts and send those exact bytes, since the server compares
them exactly (C7).

## 3. How two apps converge

They converge only when **every input of the template comes from the device itself** (the sensor's
serial and counter, the pump's own event record), not from the receiving phone's clock or a random
generator ([format research §1](../../60-research/tenancy/identifier-format-2026-10-17.md#1-per-app-identity-for-cgm-readings-and-the-treatment-identity-each-app-sends-r)).
A record created inside one app (a carb entry typed on the phone) has one origin, so there is
nothing to converge: an app that reads it back from Nightscout keeps the identifier it received and
never mints a new one. If an input is missing (no serial yet, no counter), send **no** identifier
and let the time key apply; never a partial value or a placeholder.

## 4. The conventions table

Column "identity source today" is what the app already has, read at the commit given; "converge"
is whether two devices or apps would produce the same value with the template. Commits: LoopKit
`d9f14373`, Loop `c30b5c89b`, G7SensorKit `dd91f46` (`main`) and `e17129d` (`next-dev`), CGMBLEKit
`ea224e7`, LibreTransmitter `4110512`, LibreLoop `e0282d0` and LibreCRKit `66920c6` (Loop
`next-dev` workspace), MinimedKit `a7b2685`, OmnipodKit `043b91d`, NightscoutService `2cef489`,
NightscoutKit `4ec9fd1`, Trio `0b29cd534`, AndroidAPS `7e1d537d49`, xDrip+ `1ed760048`.

### 4.1 Things that exist outside the app: source schemes

| record kind | source | template | identity source today | converge? | status |
|---|---|---|---|---|---|
| CGM reading (entries) | Dexcom G7 | `dexcom://g7/<serial>/<seconds>` [decided shape] | serial: the `0x4A` transmitter-version reply, bytes 14-19, decimal (`TransmitterVersionMessage.swift:10-23` @G7SensorKit `e17129d`; not parsed on `main`) [R]. Seconds: the sensor's seconds since activation, `messageTimestamp − age` for a live reading (`G7GlucoseMessage.swift:29-31` @`dd91f46`), the record's `timestamp` for backfill (`G7BackfillMessage.swift:14,36` @`dd91f46`) [R] | **yes in form** [R][M on one captured session]; a two-display capture is still owed (format research §7.6). Today's Loop key does not converge: it embeds each device's activation estimate (`G7CGMManager.swift:511-517` @`dd91f46`) [R] | template [proposed]; inputs [R] |
| CGM reading | Dexcom ONE+, Stelo | `dexcom://<model>/<serial>/<seconds>` [proposed] | same protocol family as G7 (format research §7.4; g7sim models `DX01`/`DX02` names) [R] | as G7 | model segment spelling (`oneplus`, `stelo`, or `g7`) **unknown** |
| CGM reading | Dexcom G6 | `dexcom://g6/<transmitterId>/<seconds>` [decided shape] | transmitter ID + transmitter seconds since transmitter activation: `"<transmitterID> <glucoseMessage.timestamp>"` (`Glucose.swift:110-113` @CGMBLEKit `ea224e7`) [R] | **yes in form** [R]; a transmitter hard reset restarts the clock and can repeat values | template [proposed] |
| CGM reading | Libre 3 | `abbott://libre3/<serial>/<lifeCount>` [decided shape] | serial + `lifeCount`, the sensor's minute counter (`RealtimeGlucoseReading.swift:6,153` @LibreCRKit `66920c6`); LibreLoop keys `"libreloop-<serial>-<lifeCount>"` (`LibreLoopCGMManager+Pairing.swift:575,647,750` @`e0282d0`) [R] | **yes in form** [R]; LibreLoop's `unknown` fallback when the serial is missing must become "no identifier" (C5) | template [proposed] |
| CGM reading | Libre 2 | `abbott://libre2/<serial>/<minutes>` [proposed] | minutes since sensor start, read from the sensor (`LibreTransmitterManagerV3.swift:381` @`4110512`) [R]; today's key is `"<startDate epoch><glucose>"` from the phone's clock (`LibreGlucose.swift:33-35`) [R]; where the serial is read was not checked | **no today**; yes in form with the counter | template [proposed]; serial source **unknown** |
| CGM reading | Medtronic CGM through the pump | `medtronic://<pumpModel>/<pumpSerial>/cgm/<pumpClock>` [proposed] | pump clock `"Y-M-D H-M-S"`, else a random UUID (`MinimedPumpManager.swift:437,1610` @MinimedKit `a7b2685`) [R] | yes when derived; repeats after a pump clock change | [proposed] |
| CGM reading | cloud relay (Dexcom Share, LibreLinkUp) | none [proposed]: the time key applies | Loop's Share key is `"<Int(epoch)>"` (`ShareClientManager.swift:110`) [R]; a relay exposes no sensor serial or counter | no sensor-side inputs | [proposed]; if a relay publishes its own record id, `dexcom-share://…` is a possible app-style form, **unknown** |
| pump event (treatments) | Medtronic, read by Loop | `medtronic://<pumpModel>/<pumpSerial>/<kind>/<eventHex>` [proposed] | Loop's dose `syncIdentifier` is the hex of the pump history record's raw bytes (`NewPumpEvent.swift:33` @LoopKit `d9f14373`; raw from the pump history, `MinimedPumpManager.swift:646,764` @`a7b2685`) [R] | **yes in form**: the bytes come from the pump's own history [R]; the serial makes it unique across pumps; `<kind>` (`bolus`, `tempbasal`, `suspend`, `resume`) separates the events that share one history record (§1) | [proposed] |
| pump event | pumps driven by AndroidAPS | `<manufacturer>://<pumpType>/<pumpSerial>/<kind>/<pumpId>` [proposed] | `pumpId`, `pumpType`, `pumpSerial` on every pump record, the server's `identifier` kept as `nightscoutId` (`nsclientV3/extensions/BolusExtension.kt:26,44-47` @`7e1d537d49`) [R] | where `pumpId` is the pump's own history id, yes; which drivers generate it on the phone was not checked | [proposed]; per driver **unknown** |
| pump event | Omnipod (DASH, Eros) | app scheme, §4.2 | the controller makes the event record itself, e.g. raw = `"Pod Change <date>"` (`OmniPumpManager.swift:276,1251` @OmnipodKit `043b91d`) [R]; one controller drives a pod | not applicable: one origin | [proposed] |

### 4.2 Things created inside an app: app schemes

One origin per record, so the question is only uniqueness and stability (§3). The scheme spelling
for each app is [proposed] and is the app developers' to confirm.

| record kind | app | template | identity source today | status |
|---|---|---|---|---|
| carb entry | Loop | `loop://carbs/<uuid>` | `syncIdentifier = UUID().uuidString`, checked unique locally (`CarbStore.swift:1524` @LoopKit `d9f14373`), sent as `syncIdentifier` (`NightscoutTreatment.swift:117` @NightscoutKit `4ec9fd1`) [R] | [proposed] |
| carb entry | Trio | `trio://carbs/<id>` | `id` sent as `_id` (`CarbsEntry.swift:29` @`0b29cd534`) [R] | [proposed] |
| carb entry, bolus, other treatments | xDrip+ | `xdrip://<kind>/<uuid>` | `uuid`, a random v4, sent on treatments (`NightscoutUploader.java:784` @`1ed760048`) [R] | [proposed] |
| manual bolus | Loop | `loop://bolus/<syncId>` | `Data(UUID().uuidString.utf8).hexadecimalString`, 72 hex characters (`LoopDataManager.swift:770` @Loop `c30b5c89b`) [R], the 72-hex shape in the corpus (format research §2) [M] | [proposed] |
| temp basal, suspend, resume | Loop (Omnipod and other controller-made events) | `loop://<kind>/<syncId>` (`tempbasal`, `suspend`, `resume`) | the pump event's raw bytes as hex (`NewPumpEvent.swift:33`) [R] | [proposed]; the kind segment fixes the measured Suspend + Temp Basal pairs (§1) |
| override | Loop | `loop://override/<uuid>` | `TemporaryScheduleOverride.syncIdentifier`, a UUID (`TemporaryScheduleOverride.swift:56,157` @`d9f14373`), sent today as `_id` (QUIRK-TREATMENTS-006) [R] | [proposed] |
| override | Trio | `trio://override/<id>` | not read here | identity source **unknown** |
| temporary target | Trio | `trio://temptarget/<id>` | `id` sent as `_id` (`TempTarget.swift:50` @`0b29cd534`) [R] | [proposed] |
| temporary target, carbs, boluses | AndroidAPS | `androidaps://<kind>/<id>` | creates over API v3 without an identifier; keeps the server's as `nightscoutId` (`BolusExtension.kt:44`) [R] | [proposed]; what local id it would send is **unknown** |
| device status | Loop | `loop://devicestatus/<uuid>` | `StoredDosingDecision.syncIdentifier`, a UUID per dosing decision (`DosingDecisionStore.swift:263` @`d9f14373`) [R]; NightscoutKit's `DeviceStatus` has an `identifier` member that Loop does not set (`DeviceStatus.swift:60-61` @`4ec9fd1`; `StoredDosingDecision.swift:149-163` @NightscoutService `2cef489`) [R] | [proposed]; one status per loop cycle, re-sent unchanged |
| device status | Trio, AndroidAPS, oref0 | `<app>://devicestatus/<id>` | per-cycle stable id not read here | **unknown** |

## 5. How a registered controller declares its convention

Decision 5 says a registered instance declares the format it uses. Where it goes is a
**proposal**: the registration grammar v1 has no member for it.

- An instance carries no meaning of its own; it names a stored definition by `definitionId`
  ([registration §8](spec/registration.md#8-instances)), and a definition is where a product says
  what its data means ([registration §7](spec/registration.md#7-definitions)). So the declaration
  belongs in the definition, as a meaning member, for example
  `identifiers: [{collection: treatments, kind: carbs, template: "loop://carbs/{uuid}"}, …]`. Being
  meaning, a changed template would need a new definition version (§7's "one element at one
  version has one meaning").
- A hub can then check a registered instance's writes against its own declaration (scheme and kind
  segment) and, under decision 1, refuse one with no identifier. It cannot check that a value names
  the right real thing; that stays the client's contract.
- Source schemes (§4.1) are not a product's to declare: they belong to this table, and a
  definition that uses one names it rather than restating it, as a well-known kind is named by
  `wellKnownRef` today.

## 6. Earlier tables and what still holds

| where | what it has | date | accurate? |
|---|---|---|---|
| [interoperability matrix](../../../mapping/cross-project/interoperability-matrix.md) "Identity Fields by Data Type" and "Device Identifier Formats" | per-client identity field and `device` string | created 2026-01-20, moved 2026-09-16 | **partly.** Wrong against format research §1-§2: Loop's treatment `syncIdentifier` is listed as a UUID, but most are pump-event hex of 14 to 72 characters [M]; Trio is listed with `syncIdentifier`, but Trio sends `id` (as `_id` on carbs and temporary targets) [R]; entries are keyed `dateString` + `device`, but v1 matches `sysTime` + `type` [R]. Right: xDrip+ `uuid` on treatments; AndroidAPS keeping `identifier` plus the pump composite. Its `device` formats (`loop://iPhone`, `openaps://…`) describe the free-text `device` field, not an identifier |
| [controller registration protocol proposal](../../60-research/controller-registration-protocol-proposal.md) GAP-003 and its controller table | "no unified sync identity field"; `device` prefixes per controller | 2026-10-18 | the gap stands; this page is the convention that answers it |
| [identifier format research §1, §7](../../60-research/tenancy/identifier-format-2026-10-17.md) | per-app identity for CGM readings and the treatment identity each app sends | 2026-10-17 | current; the source for §4 |
| `specs/quirks/treatments.yaml`, `entries.yaml` | version-scoped quirks: Loop override `_id`, Trio `id`, `UUID_HANDLING` mapping | 2026-10-16 onward | current; they record what clients send today, not a convention |
| [consumer-impact survey](../../../reports/consumer-impact-15.0.9/clients-8758.md) | which clients send which `_id` or identity field, per client, against #8758 | 2026-09-25, updated 2026-10-17 | current for the field each client sends; it has no templates |

No earlier table of identifier templates or URL schemes for `identifier` was found in `docs/`,
`mapping/`, `specs/`, `traceability/` or `conformance/`; the `loop://` and `openaps://` strings in
those files are `device` and `enteredBy` values.

## 7. Open

- **The version boundary** at which `identifier` becomes mandatory on legacy paths, how a hub
  recognises a registered instance's write on a legacy path (`ID-ABSENT-DECISION`), and what it
  answers one without `identifier` (`ID-REGISTERED-NO-IDENTIFIER`).
- **Placeholders** beyond ID-Q6's four (`NaN`, `unknown`, a whitespace-only value), and the form
  of the warning a write gets when its value is treated as absent (`ID-PLACEHOLDER-LIST`,
  `ID-WARNING-FORM`).
- **The client developers' answers**: whether the source-scheme templates work for them, and each
  app's scheme spelling (Loop is asked first, [reply](upstream-asks-loop-identifier/reply.body.md)).
- **Unknown cells** in §4: Dexcom ONE+ and Stelo model segments, the Libre 2 serial source,
  AndroidAPS per-driver `pumpId` origin, Trio override ids, a per-cycle device status id for Trio,
  AndroidAPS and oref0.
- **The G7 two-display capture** (format research §7.6) before any client relies on
  `dexcom://g7/…` converging.
- **Proxies**: whether common reverse-proxy setups pass `%2F` through to v3 paths.
- **The UUIDv5 bridge**: format research §4 proposed hashing a source-derived name into a UUIDv5 for
  today's v1 by-id routes. With URL-form identifiers the readable form is the identifier; whether a
  v5 form is still offered for v1-only clients is open.
