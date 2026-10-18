# ID-FORMAT: should Nightscout require a client `identifier` to be a UUID?

*Contributor-facing.* **Snapshot, 2026-10-17.** Input to queue item `ID-FORMAT-DECISION` and to the
reply in [upstream-asks-loop-identifier](../../30-design/platform/upstream-asks-loop-identifier/reply.body.md).
Companion to [identifier duplicates](identifier-duplicates-2026-10-17.md), whose corpus, site labels
and client classes this note reuses. The proposed constraints are carried in the
[identity specification §4](../../30-design/platform/spec/identity.md#4-the-identifier-format).

Marks: **[R]** read from code at the commit given; **[M]** measured, by
[`identifier-format-2026-10-17/idshape.py`](identifier-format-2026-10-17/idshape.py) (corpus shapes,
output [`results-2026-10-17.txt`](identifier-format-2026-10-17/results-2026-10-17.txt), control
[`control-results-2026-10-17.txt`](identifier-format-2026-10-17/control-results-2026-10-17.txt)) or by
the two small harnesses in §3.3. Corpus output is aggregate counts and value **shapes**
(regex classes, lengths, token signatures); no identifier value, serial or record content is printed
or committed.

---

## 0. Answer

**No. Do not require a UUID. Define `identifier` as an opaque, case-sensitive string with a small set
of constraints, and recommend (not require) a UUID: v4 for a record made once on one device, v5 of a
source-derived key when several devices must agree.**

Why not require it:

- Non-UUID values are already in the wild and the server already accepts them on every write path
  [R][M]: 489 stored treatment `identifier`s at one site are 32-hex strings (§2); 15,117 entries at
  another site carry a 24-character non-hex alphanumeric `_id`, which 15.0.7 and later move into
  `identifier` (§3.1); and API v3 checks only "non-empty string" (§3.2). A UUID rule would reject
  writes that work today.
- The ecosystem's own sync keys are not UUIDs. Loop's CGM `syncIdentifier`s are derived strings, and
  Loop's dose `syncIdentifier`s are pump-event hex of 14 to 72 characters (§1, §2). HealthKit and FHIR
  both define their sync or business identifier as a plain string (§5).
- A UUID rule does not solve the watch-and-phone problem. What makes two devices agree is the
  *derivation* (the inputs must be the same on both), not the format. A UUIDv5 of a device-dependent
  key is still device-dependent (§4, §6.4).

The constraints a format rule does need (each grounded below):

| # | constraint | why |
|---|---|---|
| C1 | a JSON string, at least one non-whitespace character | already enforced on API v3 create (`create/validate.js:19`) [R]; v1 treatments reject a non-string (`treatments.js:18-25`) [R] |
| C2 | **at most 256 characters** (proposal) | an indexed `identifier` near 1 KB fails the insert on MongoDB before 4.2 (measured on 3.6.8: 1,000 characters fails, the compound `{date, identifier, created_at}` key is 1,026 bytes) [M]; the URL path of an API v3 read is capped by Node's 16 KB header limit (20,000 characters gave 431) [M] |
| C3 | **printable ASCII, no `/`, `%`, `?`, `#`, space or control characters** (proposal; or "URL-unreserved characters `A-Z a-z 0-9 - . _ ~` plus `:`") | API v3 addresses a record as `/api/v3/{collection}/{identifier}`. A raw `/` gives 404, a malformed `%` gives 400, and `?`/`#`/space must be percent-encoded by every client [M]; `%2F` works in Express but is commonly rewritten or refused by reverse proxies [R, not run] |
| C4 | **not exactly 24 hex characters** unless it equals the record's own `_id` | both API v3 (`filterForOne`, `identifyingFilter`) and v1 (`normalizeIdValue`) treat a 24-hex value as an ObjectId `_id` as well, so it can address a different record [R] |
| C5 | **not a reserved word**: `history` (shadowed by `GET /api/v3/{col}/history`), `.` and `..` (normalized away by URL libraries), and client sentinels such as `invalid`, `undefined`, `null`, `NaN` | `GET /api/v3/entries/history` reaches the history route, not the record [M]; G7SensorKit returns the literal `invalid` when its inputs are missing (§1) [R] |
| C6 | **one identifier, one record**, per collection, forever (no reuse after a long interval) | already in the reply; the companion note found 13 Loop `syncIdentifier` values on 2 to 4 treatments [M] |
| C7 | compared **exactly** (case-sensitive, no trimming or normalization) | v1 and v3 match with `$eq` [R]; Loop sends upper-case UUIDs and the server's own v5 is lower-case (§2, §4), so a client must send one spelling consistently |

Use the UUID recommendation where it buys something concrete: **v1 by-id routes understand only UUID-
and ObjectId-shaped values** (`query.js` `UUID_RE`, §3.1). A client that wants `find[_id]=<identifier>`
or `DELETE /api/v1/treatments/<identifier>` to work must use a UUID; a client that uses
`find[identifier]=`, API v3, or the reply's two-id rule does not need one.

---

## 1. Per-app identity for CGM readings (and the treatment identity each app sends) [R]

Two independent devices "agree" only if every input of the derivation comes from the sensor or
pump, not from the receiving device's clock or a random generator.

| app / source | per-reading identity | form | derived from | two devices reading the same sensor agree? | hazards | sent to Nightscout today |
|---|---|---|---|---|---|---|
| Loop, **G7** (G7SensorKit) | `syncIdentifier` = `"<activatedAt in hours> <sensorID> <glucoseTimestamp>"` (`G7CGMManager.swift:511-517`) | space-separated derived string; first token a `Double` printed with full fractional precision (`.hours` is `Double`, `Common/TimeInterval.swift:57`) | `activatedAt` = **local `Date()` at receipt minus the sensor's message counter** (`G7Sensor.swift:134`), stored once at discovery (`G7CGMManager.swift:313-322`); `sensorID` = BLE peripheral name (`DXCMxx`, `G7Sensor.swift:254-256`); timestamp = sensor seconds counter (`G7GlucoseMessage.swift:18,29-30`) | **No.** The first token embeds each device's own receive time and clock, to sub-second precision | literal `"invalid"` when `activatedAt` or `sensorID` is nil (shared by every reading in that state); `sensorID` is a 2-character suffix, so it repeats across sensors and is unique only together with the activation token | **No.** Entries carry no id (`StoredGlucoseSample.swift:34-42`, NightscoutKit `GlucoseEntry.swift:108` sends `_id` only when set; it is not) |
| Loop, **G6** (CGMBLEKit) | `"<transmitterID> <glucoseMessage.timestamp>"` (`Glucose.swift:110-113`) | space-separated derived string | transmitter ID + transmitter-relative seconds | **Yes**, both come from the transmitter ("consistent between backfill/live") | a simulated-sample path uses `Date()` (`TransmitterManager.swift:106-108`), not used for real readings | No (as above) |
| Loop, **Libre** (LibreTransmitter) | `syncId` = `"<Int(epoch s)><unsmoothedGlucose>"` (`LibreGlucose.swift:33-35`) | digits concatenated with a decimal, no separator | reading time = **local `Date()` at read minus minute offsets** (`SensorData.swift:303`) + value | **No** (local clock) | two readings in one second with one value collide | No |
| Loop, **Eversense** (EversenseKit) | `"<epoch Double><value>"` (`Common/NewGlucoseSample.swift:14`) | concatenation, no separator | transmitter-reported time + value | not checked | concatenation without a separator is ambiguous in principle | No |
| Loop, **Nightscout remote CGM** | `glucose.id ?? "<Int(epoch)>"` (`NightscoutRemoteCGM.swift:169`) | server `_id`, else epoch digits | the server's record | yes (both read the server) | fallback collides for two readings in one second | n/a (it reads Nightscout) |
| Loop, **Dexcom Share** | `"<Int(epoch)>"` (`ShareClientManager.swift:110`) | epoch digits | Share's reading time | yes (both read Share) | one-second collisions; not unique across sensors or sites | No |
| Loop, **Minimed CGM** | `"Y-M-D H-M-S"` of the pump clock, else `UUID()` (`MySentryPumpStatusMessageBody+CGMManager.swift:59-71`, `SensorValueGlucoseEvent+CGMManager.swift:10-24`, `MinimedPumpManager.swift:437,1610`) | derived string with a space; fallback random UUID | pump clock | yes when derived; no for the fallback | repeats after a pump clock change; not unique across pumps | No |
| Loop, simulators / mocks | `UUID()` (`MockGlucoseProvider.swift:83`) | UUID v4 | random | no | — | No |
| Loop, **watch** | the watch **receives** the phone's sample and forwards its `syncIdentifier` (`WatchContext.swift:162-170`, `WatchHistoricalGlucose.swift:55,72`) | as the phone's | — | n/a: no watch-side CGM reader in Loop `main` or `next-dev` | — | — |
| **Trio** (any CGM, incl. the same LoopKit managers) | discards the manager's `syncIdentifier`; `id: UUID().uuidString` (`PluginSource.swift:328,343`), re-assigned `UUID()` when stored (`GlucoseStorage.swift:255`) | UUID v4 | random, per device | **No** | — | **Yes**, as entry field **`id`** (`BloodGlucose.swift:61-62`; `_id` no longer sent since Trio commit `149e3bb71`, 2026-03-24) |
| **AndroidAPS** | local key `timestamp` + `sourceSensor` (`GlucoseValueDao.kt:32-33`); Nightscout identity = the **server-assigned** API v3 `identifier`, kept as `nightscoutId` (`GlucoseValueExtension.kt:38`) | server's UUIDv5 | server computes v5 of `device + "_" + date` (`operationTools.js:95-107`) | yes **if** both send the same `device` string and the same `date` to the millisecond | — | creates without an identifier; updates by the server's identifier |
| **xDrip+** | `BgReading.uuid = UUID.randomUUID()` (`BgReading.java:359` and others) | UUID v4 | random | No | — | entries: no id; treatments: `uuid`, and `_id` = `uuid_to_id(uuid)`: the UUID's first 24 hex, or **MD5 of a non-standard value** (one containing `:` or shorter than 24) truncated to 24 hex (`NightscoutUploader.java:245-256,884`) |
| **xDrip4iOS** | `BgReading.id = UniqueId.createEventId()` (`BgReading+CoreDataClass.swift:32`) | **24 random characters from `[A-Za-z0-9]`** (`UniqueId.swift:18-25`) | random | No | looks ObjectId-sized but is not hex | entries: as `_id` (`BgReading+Nightscout.swift:9`) |

Commits read: LoopWorkspace `548b332` (= `main` per `gh api`, 2026-10-05) with G7SensorKit `dd91f46`,
CGMBLEKit `ea224e7`, LibreTransmitter `4110512`, EversenseKit `e1bb6fa`, NightscoutRemoteCGM
`45b4efd`, MinimedKit `a7b2685`, dexcom-share-client-swift `ff0d714`, Loop `c30b5c8`,
NightscoutService `2cef489`, LoopKit `d9f1437`; NightscoutKit `4ec9fd1` (the revision LoopWorkspace's
`Package.resolved` pins). Loop **next-dev**: the local clone (`584bdaf`, 2026-07-15) is stale, so
`gh api` was read instead: LoopWorkspace `next-dev` `1561bff` (2026-10-15) pins G7SensorKit `e17129d`
and Loop `859b61d`. G7SensorKit `e17129d` has the same `generateSyncIdentifier` (line 1171) and the
same `activationDate` derivation (`G7Sensor.swift:392`); it adds `G7DisplayType` (`phone` = 2,
`watch` = 3; "a phone and a watch can both hold a session with it, while two phones cannot") and
reads the sensor's real serial number (`transmitterVersion?.serialNumberString`, lines 561, 579,
594). Loop `859b61d`'s tree has no watch-side CGM code. Trio `0b29cd534` (= `main`). AndroidAPS local
`7e1d537d49` (`dev` at 2026-09-23); current `dev` `b9bb9ef302` changes only the `device` resolver in
`GlucoseValueExtension.kt`, not the identity lines (diffed via `gh api`). xDrip+ `1ed760048` (tag
2026.09.18); `NightscoutUploader.java` is identical at current `master` `8532095b9`, and
`BgReading.java` still assigns random UUIDs there. xDrip4iOS `c268542e` (= `master`).

**Treatments, briefly.** Loop sends `syncIdentifier` (NightscoutKit `NightscoutTreatment.swift:117`)
and an override's UUID as `_id`; Trio sends `id`; AndroidAPS uses API v3 `identifier`; xDrip+ sends
`uuid` and a derived `_id`.

## 2. Corpus: the shapes in the wild [M]

12 sites, 719,559 entries and 307,996 treatments (the companion note's corpus §1; fetched by API v1
GET; server versions not recorded). Counts by collection, client class, field and shape:

| collection | client class | field | shape | documents | sites |
|---|---|---|---|---:|---|
| entries | every class except below | `_id` | 24-hex (ObjectId form) | 655,578 | 12 |
| entries | no-device | `_id` | UUID, upper case, v4 | 48,864 | b |
| entries | LibreLinkUp / xDrip+ | `_id` | **24 alphanumeric, not hex** (xDrip4iOS's generator shape) | 13,096 / 2,021 | j |
| entries | any | `identifier`, `syncIdentifier`, `uuid`, `id`, `NSCLIENT_ID` | — | **0** | — |
| treatments | Loop | `identifier` | UUID, upper case, v4 | 16 | L, i |
| treatments | Loop | `identifier` | **32 hex** (equals its own `syncIdentifier`) | **489** | L |
| treatments | Loop | `syncIdentifier` | UUID, upper case, v4 | 6,862 | 11 |
| treatments | Loop | `syncIdentifier` | hex, length 14 / 18 / 20 / 32 | 103 / 16 / 49 / 29,982 | L |
| treatments | Loop | `syncIdentifier` | hex, length 60 / 62 / 64 / 68 / 70 / 72 | 41,695 / 51,245 / 976 / 75,421 / 17,409 / 31,537 | 10 |
| treatments | Loop | `syncIdentifier` | **`<hex 64-72> <3 characters containing "/">`** | 503 | i |
| treatments | Loop | `syncIdentifier` | digits | 13 | L |
| treatments | Loop | `_id` | UUID, upper case, v4 | 2,064 | 9 |
| treatments | Trio | `id` | UUID, upper case, v4 | 47,454 | b |
| treatments | every class | `uuid`, `NSCLIENT_ID` | — | 0 | — |

Readings:

- **Non-UUID identity values are the majority, not the exception.** 248,949 treatments at 11 sites
  carry a non-UUID, non-ObjectId value in a client identity field (`results`, last section), almost
  all Loop dose `syncIdentifier`s. As `identifier` itself, 489 are non-UUID.
- **A `/` appears in real client keys.** 503 Loop `syncIdentifier`s at site i end in a 3-character
  token containing `/`. Sent as `identifier`, each would need `%2F` in an API v3 path (C3).
- **Every UUID in the corpus is upper case and v4.** No v5 UUID was found, so no stored record shows a
  client using UUIDv5 today, and none shows the server's own v5 (this corpus has no API v3 writer).
- **No CGM entry carries a client identity field.** This agrees with the code read in §1: Loop and
  xDrip+ send none for entries; Trio's `id` (from 2026-03-24) postdates most of this corpus.
- The 24-alphanumeric `_id`s at site j were stored as string `_id`s by whatever server version
  received them; on 15.0.7 and later the same write moves the value into `identifier` (§3.1).

Not visible here: AndroidAPS, xDrip+ uploader and other API v3 writers are absent from the corpus, as
the companion note says. Shapes, not values, were read.

## 3. Server compatibility of non-UUID identifiers

### 3.1 API v1 [R] (15.0.8 `92d0834`, dev `fade2299`)

| path | behaviour with a non-UUID `identifier` |
|---|---|
| treatments write, `identifier` in body | matched first, by exact string (`{identifier: {$eq: v}}`), any characters; `_id` dropped from the replacement (`treatments.js:356-381` @92d0834). Non-string values throw (`treatments.js:18-25`). Same on fade2299 |
| treatments / entries write, string `_id` that is **not 24-hex** | moved to `identifier` when `UUID_HANDLING` is on (the default), deleted otherwise (`treatments.js:394-405`, `entries.js:267-277` @92d0834; `treatments.js:452-459`, `entries.js:334-341` @fade2299). The test is "not 24-hex", **not** "is a UUID", although the comments say UUID: an xDrip4iOS 24-alphanumeric `_id` or a Loop-style derived string becomes an `identifier` |
| entries write, `identifier` in body | stored, not matched; entries match on `sysTime` + `type` (the reply's "gap") |
| read/delete by `_id` (`find[_id]=`, `DELETE /api/v1/treatments/:id`) | `normalizeIdValue`: 24-hex becomes an ObjectId; **only a value matching `UUID_RE`** (`query.js:7` @92d0834, `query.js:12` @fade2299) is looked up by `identifier`; any other string is compared to `_id` and finds nothing (`query.js:131-143` @92d0834, `195-206` @fade2299) |
| query by `find[identifier]=` | generic exact match on the field, any string |
| index | `identifier` is indexed alone and in `{date, identifier, created_at}` on entries and `{eventType, created_at, identifier, date}` on treatments (`entries.js:224-226`, `treatments.js:430-432` @92d0834) |

### 3.2 API v3 [R]

- **Create:** `resolveIdentifier` computes the server key; a client value that differs only logs a
  warning and is kept (`operationTools.js:114-126`); `validate` requires a non-empty, non-whitespace
  string, nothing more (`create/validate.js:19`). No pattern, no length. Same at both commits.
- **Address:** `/{collection}/:identifier` for GET, PUT, PATCH, DELETE (`generic/collection.js:42`),
  registered **after** `GET /{collection}/history` (lines 54-57).
- **Lookup:** exact `identifier` match, plus `_id` when the value is 24-hex
  (`mongoCollection/utils.js:107-116` @92d0834). On fade2299 a non-hex string is also compared to a
  string `_id` (`utils.js:105-123`), so a v1 record stored with a non-hex string `_id` is reachable.
- **Swagger:** `paramIdentifier` and `identifierField` are `type: string` with a UUID-shaped
  **example** only, no `pattern` or `maxLength` (`swagger.yaml:1052-1060` @92d0834,
  `1011-1020` @fade2299).

### 3.3 What breaks: two small harnesses [M]

**URL path.** Express 4.22.2 (the version in the checkout's `node_modules`; dev pins 4.22.2, 15.0.8
4.22.1) with the four v3 routes and the history route registered in the server's order, driven over
HTTP ([`v3-path-routing.js`](identifier-format-2026-10-17/v3-path-routing.js); Express routing only, no proxy, no auth, no storage):

| identifier in path | GET result |
|---|---|
| UUID, `g7:SERIAL:12345` (colon), `a+b` | reaches the record route; colon and plus pass through unchanged |
| `a%20b%20c`, `a%2Fb`, `a%25b`, `a%23b`, `a%3Fb` | reaches the record route, decoded to space, `/`, `%`, `#`, `?` |
| `a/b` (raw slash) | **404** |
| `a%zzb` (malformed escape) | **400** "Failed to decode param" |
| `history` | **reaches the history route**, not the record (PUT and DELETE do reach the record) |
| `.` and `..` | reach the record route in this harness; client URL libraries normalize them away |
| 8,000 characters | reaches the route; **20,000 characters: 431** (Node's 16 KB header limit) |

**Index key size.** ([`index-key-size.js`](identifier-format-2026-10-17/index-key-size.js).) Local MongoDB 3.6.8 (FCV 3.6), a scratch database with the v1 entries indexes
`{identifier: 1}` and `{date: -1, identifier: -1, created_at: -1}`, dropped afterwards: a 256-character
`identifier` inserts; 1,000, 1,010, 1,020, 1,100 and 2,000 characters fail with code 17280 "key too
large to index" (the compound key is 1,026 bytes at 1,000 characters). MongoDB 4.2 removed this limit
at FCV 4.2 (not fetched from MongoDB's documentation; MongoDB's tracker
[DOCS-11942](https://jira.mongodb.org/browse/DOCS-11942) was listed by a search, not opened).

## 4. UUIDv5 as the bridge

If a client hashes its derived key into a UUIDv5 and sends that as `identifier`:

| gained | lost |
|---|---|
| works with today's v1 by-id routes (`UUID_RE`), every version since `UUID_HANDLING` | readability: the sensor, session and time are no longer visible in the record |
| fixed 36 characters: no index-size, header or URL-escaping concern (C2, C3) | debuggability: a support person cannot tell two ids apart or see why they differ, unless the client also stores the key (in `syncIdentifier` or a dedicated field) |
| never 24-hex, never a reserved word (C4, C5) | irreversibility: no parsing back; a wrong input (e.g. today's G7 activation token) is invisible |
| byte-for-byte determinism is explicit: the same namespace and the same canonical name give the same UUID ([RFC 9562 §6.5](https://www.rfc-editor.org/rfc/rfc9562.html#section-6.5)) | nothing about agreement: v5 is exactly as device-independent as its input, no more |

**Namespace.** The server's v3 namespace is the 16 ASCII bytes of `NightscoutRocks!`
(`operationTools.js:6,106`), i.e. `4e696768-7473-636f-7574-526f636b7321`; read as a UUID its variant
bits are the reserved NCS variant, so it is not an RFC-conformant UUID of any version (computed, not
a defect: v5 accepts any 16 bytes). The server's names are `<device>_<date>[_<eventType>]`
(`operationTools.js:95-107`). A client v5 in the same namespace collides with a server-computed
identifier only if its name string is byte-identical to such a name (SHA-1 makes accidental
collisions between different names negligible). A scheme-prefixed name such as `g7:<serial>:<seconds>`
cannot equal `<device>_<digits>` unless a client's `device` string were itself crafted to match.
The risk is semantic, not cryptographic, but it is avoidable: RFC 9562 recommends a v4 or v7 value for
a custom namespace ([§6.6](https://www.rfc-editor.org/rfc/rfc9562.html#section-6.6)). Proposal:
Nightscout publishes **one client namespace** (a fresh v4, documented next to the format rule) and
asks clients to put a scheme prefix in the name (`g7:`, `g6:`, `libre:` …). Two independent
apps that adopt the same scheme then agree with each other, and none can coincide with a server key.

## 5. Precedents (fetched)

FHIR R4's `Identifier.value` is a `string` "unique within the context of the system", with `system`
a URI that "establishes the namespace for the value"; FHIR strings are limited to 1 MB and should
contain non-whitespace content, while FHIR's resource `id` (the server id) is a separate type limited
to `[A-Za-z0-9\-\.]{1,64}`, case-sensitive ([FHIR R4 data types](https://hl7.org/fhir/R4/datatypes.html)).
HealthKit's `HKMetadataKeySyncIdentifier` is "a unique string that identifies a piece of data so it
can be updated and synced", must be accompanied by `HKMetadataKeySyncVersion`, and a save with a
greater sync version replaces the stored object
([Apple, documentation JSON for HKMetadataKeySyncIdentifier](https://developer.apple.com/tutorials/data/documentation/healthkit/hkmetadatakeysyncidentifier.json)).
Neither imposes a UUID. The FHIR split, a free-form business identifier beside a tightly-charactered,
length-capped server id, is the same split as Nightscout's `identifier` beside `_id`; FHIR's `id`
rule is a reasonable model for C2/C3 if the maintainers want a stricter character set. Open mHealth
and IEEE 11073 were not checked.

## 6. Implications

### 6.1 The reply (`reply.body.md`)

- **Nothing in it overstates a UUID requirement.** It says "a string. We recommend a UUID", which
  this note supports.
- **Rule 1 is narrower than the code.** "`UUID_HANDLING` … moves a UUID `_id` to `identifier`": the
  code moves **any non-24-hex string** `_id` (§3.1). Not wrong for Loop, but "a non-ObjectId string
  `_id` (a UUID, for example)" would be exact.
- **Option 3 needs two qualifiers** if it stays as written: the `<serial>` must be the sensor's
  serial number, not G7SensorKit's `sensorID` (a `DXCMxx` BLE name that repeats across sensors), and
  the string form works on v1 treatments, API v3 and `find[identifier]=` but **not** on v1 by-id
  routes; its UUIDv5 works on all of them.
- **Option 2's premise matches the code:** today each device computes its own activation estimate
  from its own receive time, so phone and watch timestamps differ unless one adopts the other's.
- "Later, only if needed: the identifier's length limit, character set and case comparison" can now
  carry a concrete proposal (§0, C1-C7) instead of an open question.

### 6.2 `ID-FORMAT-DECISION` (proposed answer)

`identifier` is an opaque, case-sensitive string, 1 to 256 characters, from
`[A-Za-z0-9._~:-]`, not exactly 24 hex characters, not `history`, `.`, `..`, `invalid`, `undefined`,
`null` or `NaN`; one identifier names one record per collection. Recommended: UUID v4 for a
one-device record; UUID v5 in the published Nightscout client namespace over a scheme-prefixed,
source-derived name when several devices must agree; required only by clients that use v1 by-id
routes. The 256 limit and the character set are proposals for the maintainers: the corpus's longest
client key is 72 hex characters plus a 4-character suffix, and the only character outside the set
seen in client keys is the `/` in §2 (and the space in Loop's CGM keys, §1).

### 6.3 `ID-VALIDATE` (server checks worth adding)

In order of value, each a 400 on API v3 and a per-record rejection on v1 once per-record results exist:

1. **Length** over the limit (protects pre-4.2 MongoDB from a failed insert that today surfaces as a
   storage error, §3.3).
2. **Exactly 24 hex** in `identifier` that is not the record's own `_id` (C4: ambiguous addressing).
3. **Reserved words** (`history`, `.`, `..`) and known client sentinels (`invalid` from G7SensorKit;
   `undefined`, `null`, `NaN` from string-formatting bugs). A sentinel shared by many readings is the
   worst case for C6: with identifier matching on entries, every "invalid" reading would overwrite
   the last.
4. **Characters** outside the set (C3), at least `/`, `%`, `?`, `#`, whitespace and control
   characters. This one would reject Loop's current G7/G6 `syncIdentifier`s (they contain spaces)
   if Loop sent them unchanged, so roll it out as a warning first, or define the set to allow a space
   and accept that such ids must be percent-encoded in v3 paths.

Do **not** add a UUID pattern check: it would reject the 489 stored values and every non-UUID key in §1.

### 6.4 Loop's G7 identifier

**Verified:** today's G7 `syncIdentifier` would **not** dedupe a watch and a phone reading the same
sensor. Its first token is `activatedAt.timeIntervalSince1970.hours`, a `Double` printed in full,
where `activatedAt` = (local time when the first glucose message was received) − (the message's
sensor seconds counter), computed independently on each device (`G7Sensor.swift:134`,
`G7CGMManager.swift:313-322,511-517` @dd91f46; unchanged in next-dev `e17129d`). Receive latency and
clock offset differ between devices, so the token differs; it would differ even between two
discoveries on one device. The reading's `date` is derived from the same per-device estimate
(`G7CGMManager.swift:469,476,547`), which is why the reply's option 2 needs one device to adopt the
other's estimate.

A device-independent G7 form needs only inputs both devices read from the sensor:

- **sensor identity:** the real serial number (`transmitterVersion.serialNumberString`, read in
  next-dev), not the `DXCMxx` peripheral name, which has a 2-character suffix and repeats across
  sensors. Without the serial, the session must be identified some other sensor-sourced way; rounding
  the activation estimate is not safe (two devices can fall either side of a rounding boundary).
- **reading position:** the sensor's own seconds counter (`glucoseTimestamp`), already used.
- **no fallback sentinel:** if either input is missing, send no `identifier` (let the time key apply)
  rather than `"invalid"`.
- **one spelling:** fixed scheme, separators and case (e.g. `g7:<serial>:<seconds>`), or its UUIDv5
  in the published namespace; both devices must produce the same bytes.

Whether `messageTimestamp` counts from the sensor session or from each display's pairing slot: see
§7. Very probably the sensor session (shared by every display, and equal between live and backfill),
not yet measured with two displays.

## 7. Is the G7 seconds counter shared across devices?

**Answer: very probably yes, but nobody has measured it with two displays.** The value Loop keys
on (`glucoseTimestamp` = the glucose message's counter minus its `age`, equal to a backfill record's
`timestamp`) is the sensor's own session clock. It counts seconds from sensor activation. It does
not start at each display's pairing. Every independent implementation read here, the official
app's own field name, a captured session, and the sensor's expiry behaviour all point that way [R][M].
Two caveats: no capture with two displays on one sensor exists in any repository or source opened
here, and one implementation (xDrip4iOS) reads the field's relation to `age` the other way round
(§7.3). So `g7:<serial>:<seconds since activation>` should be device-independent. Confirm it with
the two-display capture in §7.6 before a client relies on it.

Snapshot commits (all read 2026-10-17): G7SensorKit `main` `dd91f46` and `next-dev` `e17129d`
(the local next-dev clone at `468eefc` is stale; `e17129d` was read from a fresh clone of
LoopKit/G7SensorKit), xDrip+ `1ed760048`, xDrip4iOS (xdripswift) `c268542e`, DiaBLE `e6a909c`,
Juggluco `75399d7` (default branch `primary`, read via `gh api`, no local clone), g7sim `7c039de`
(matches GitHub `main`), AndroidAPS `7e1d537d49`, CGMBLEKit `ea224e7`, LibreTransmitter `4110512`,
LibreLoop `e0282d0` and LibreCRKit `66920c6` (next-dev workspace).

### 7.1 What each implementation says the counter counts from [R]

The G7 glucose reply (opcode `0x4E`) carries a 4-byte counter at bytes 2-5 and a 2-byte `age` at
bytes 10-11. A backfill record (9 bytes) carries a 3-byte counter at bytes 0-2. Every implementation
below reads these at the same offsets.

| implementation | `0x4E` bytes 2-5 called | what it counts from | reading's position | backfill record bytes 0-2 | same clock live and backfill? | builds an id from it? |
|---|---|---|---|---|---|---|
| G7SensorKit `main` | `messageTimestamp`, "Seconds since pairing of the *message*" (`G7GlucoseMessage.swift:18`) | activation: `activationDate = now − messageTimestamp` (`G7Sensor.swift:134`); lifetime, grace and warm-up are measured from it (`G7CGMManager.swift:121-152`) | `messageTimestamp − age` (`G7GlucoseMessage.swift:29-31`) | `timestamp`, "Seconds since pairing" (`G7BackfillMessage.swift:14,36`) | yes: both go through one `generateSyncIdentifier` and one activation date (`G7CGMManager.swift:505,547,554`) | yes, but prefixed with the per-device activation estimate (§6.4) |
| G7SensorKit `next-dev` | same (`G7GlucoseMessage.swift:23`) | same (`G7Sensor.swift:392`); calibrations are written "on the sensor's seconds-since-activation clock" (`G7CalibrationMessage.swift:13-14`) | same | same (`G7BackfillMessage.swift:15`); backfill now tagged `isBackfill` (`G7CGMManager.swift:1227-1229`) | yes | same form (`G7CGMManager.swift:1171-1177`) |
| xDrip+ (companion mode, listening to the Dexcom app's link) | `clock` (`cgm/dex/g7/EGlucoseRxMessage.java:49`) | activation: `activation_time = now − clock` (`g5model/DexTimeKeeper.java:48`, fed at `cgm/dex/ClassifierAction.java:56`) | live reading dated `now − age` by wall clock (`EGlucoseRxMessage.java:55`); it does not use the counter | 4-byte little-endian `dexTime` (`g5model/BackFillStream.java:94`) | yes: backfill is dated `activation + dexTime` (`ClassifierAction.java:131`) | no; dedupes by time window |
| xDrip4iOS (xdripswift), primary mode | `transmitterTime`, "reading time measured from sensor start" (`DexcomG7GlucoseDataRxMessage.swift:78-80`) | sensor start: `sensorAge = transmitterTime + age` (`:87`) | **`transmitterTime`** (age is *added* to get the sensor's age now, `:86-90`) | `timeStampSincePairing`, "Seconds since pairing, ie sensorage + age of the message" (`DexcomG7BackfillMessage.swift:9,23,25`) | yes, but offset by `age` relative to the others (§7.3) | no |
| xDrip4iOS, coexistence mode (listening to the Dexcom app) | the app's own link uses a `0x31` glucose frame with a counter at bytes 6-9, joined with a `0x25` clock reply giving transmitter start and sensor start (`DexcomG7GlucoseDataRxMessage.swift:132-157`; `CGMG7Transmitter.swift:1089-1100`; `DexcomTransmitterTimeRxMessage.swift:17,21`) | the transmitter's clock (`0x25` current time), with session start as a separate offset | `transmitterStart + counter` | — | — | no |
| Juggluco | `secsSinceStart` (`Common/src/main/cpp/dexcom/java.cpp:37,84`) | sensor start: `starttime = now − secsSinceStart` (`:133`); warm-up and maximum life checked against it (`:151,173`) | `secsSinceStart − age` (`:96-97`) | `secsSinceStart` (`:328-329`) | yes: both store at index `(seconds)/300` in one stream (`:101-104`, `:338-340`, `DEXSECONDS` `:76`) | yes, internally: slot index `(secsSinceStart − age)/300` per sensor |
| DiaBLE | `txTime` (`DiaBLE/DexcomG7.swift:269`), the field name it reports from the official app's `EGVResponse` class (`:256-266`) | activation: `activationDate = now − txTime` (`:270`) | `txTime − egvAge` (`:278`) | "seconds since pairing" (`:385`) | yes: backfill requests are sent as a `startTime-endTime` range on the same clock (`:292-294`) and records are dated from the same activation (`:386`) | yes, internally: `id = timestamp/60/5` (`:298,394`) |
| g7sim (sensor-side model) | `sensorNow` (`g7/messages.go:58-60`) | one `Activation` per sensor state (`g7/state.go:64`); "A reading every 300 s from activation" (README `:229`, from sniffer measurements of a real sensor that the README cites) | `Reading.Time`, `age = sensorNow − Time` (`messages.go:63`) | `Reading.Time` (`messages.go:75-76`) | yes, by construction | — |
| AndroidAPS | no G7 BLE driver; receives readings by broadcast or notification from another app (`plugins/source/.../DexcomPlugin.kt`, `notificationreader/PackageConfig.kt:40`) | — | — | — | — | — |

**Do they agree?** On the clock, yes. Every implementation treats the counter as seconds since
sensor activation (the "pairing" in G7SensorKit's comments is the sensor's start-up pairing; next-dev
says "seconds-since-activation" outright). Every one converts it to a date as `now − counter`, and
every one that reads backfill puts it on the same clock. The one disagreement is where a reading
sits on that clock (§7.3).

The alignment repo's own deep dives already say "seconds since sensor activation"
([g7-protocol-specification.md](../../10-domain/g7-protocol-specification.md) lines 269, 312, 358),
but they were read from the same code [R]. Its
[dexcom-ble-protocol-deep-dive.md](../../10-domain/dexcom-ble-protocol-deep-dive.md) line 18 gives the
G7 "1 (exclusive connection)" slot. That is contradicted by the slot model in G7SensorKit next-dev,
g7sim, xDrip4iOS and DiaBLE (§7.2).

### 7.2 A property of the sensor, or of the connection?

The G7 holds **one slot per display type**: phone 2, watch 3, receiver 4, pump 5, and others
(`G7DisplayType.swift:18-28` next-dev). A client says which type it is during authentication
(Juggluco sends `0d 00 02`, phone, `DexGattCallback.java:391`). Held slots set bits in the
advertisement's types-in-use byte (`G7DisplayType.swift:31-33`; g7sim `sensor.go:295-302`). G7SensorKit
next-dev: "a watch app takes its own [slot], alongside the phone's" (`G7CGMManager.swift:283-284`,
`G7Sensor.swift:190-192`). xDrip4iOS: each Bluetooth channel is "an independent authentication slot
inside the sensor" (`CGMG7Transmitter.swift:8-13`). So a phone and a watch reading one sensor
directly hold **separate connections with separate keys** [R].

Nothing read here shows the counter is per slot, and five things show it is the sensor's:

1. **The official app names it `txTime`** (transmitter time). It does so in DiaBLE's record of the
   app's `EGVResponse` class (`DexcomG7.swift:256-259`) and in an app log line kept in G7SensorKit's
   tests: `readEGV(txTime=40104,seq=136,session=1,age=4,...)` (`G7GlucoseMessageTests.swift:87`
   @dd91f46). That is a sensor clock, not a link clock [R].
2. **A captured session starts the counter at activation** [M]. In G7SensorKit's lifecycle vectors
   (`G7GlucoseMessageTests.swift:33-43`), the first message is state *stopped* at counter 182,
   sequence 1, session byte 0. The next messages are *warmup* at reading positions 200, 500, … and
   *ok* from 1700. A session that began when this display paired would also look like this. But see 3.
3. **The sensor's own expiry is on this clock** [M]. The same vector set's *expired* message has
   reading position 907,385 s. A 10-day sensor's own `0x52` reply gives a session length of 907,200 s
   (10 days + 12 h grace; g7sim `state.go:49-56`, from captured replies). The sensor marks itself
   expired just past its session length on this counter. A per-display counter that started late
   would put expiry late for that display. Loop's expiry display (`G7CGMManager.swift:134-144`),
   Juggluco's maximum-life check (`java.cpp:151,173`) and xDrip4iOS's lifetime checks all rest on
   the counter being session-relative. If the counter started at each display's pairing, all of
   them would misplace expiry for a display paired after activation. None of them guards against
   that case, and none of their issue trackers was searched for such a report.
4. **Commands that write to shared sensor state use it.** A calibration (`0x34`) is sent as a time on
   this clock (`G7CalibrationMessage.swift:13-14` next-dev; xDrip4iOS "converts its date into
   transmitter time", `CGMG7Transmitter.swift:98-104`). The sensor then reports it back in the
   calibration-bounds reply as `lastCalibrationTime`, beside a `sessionNumber` and `sessionSignature`
   (`DexcomG7.swift:319-330`). One calibration applies to the sensor for every display, so the clock it
   is expressed on must be one every display shares.
5. **Backfill is requested by range on this clock** (`0x59` + start + end, `DexcomG7.swift:292-294`;
   g7sim `handler_test.go:121-123`). The sensor serves records from one 24-hour store (g7sim models
   one store; the backfill reply carries a first sequence number and first and last timestamps,
   `DexcomG7.swift:362-369`).

g7sim models exactly this: one `Activation` and one reading list per sensor, with every slot served
the same `Reading` in a window (`state.go:11-18,64-71`; `sensor.go:421-431`). It is a model built on
the same assumption, so it does not prove the assumption.

An analogue on Dexcom's side: an EGV record in Dexcom's v3 API carries `transmitterId`,
`transmitterTicks` (int64) and `displayDevice` (iOS, android or receiver) side by side
([S] third-party schema mirror, apis.io "Dexcom API EGV record", opened 2026-10-17). Dexcom's own
endpoint overview says `systemTime` is "the UTC time according to the device" and "not 'true' UTC
time because of drift and/or user manipulation of the device's clock"
([S] developer.dexcom.com/docs/dexcomv3/endpoint-overview, opened 2026-10-17). The schema keeps a
transmitter tick count apart from the display's clock. It does not say whether two displays report
the same ticks, and the official schema page did not load, so this is context only.

### 7.3 Live and backfill: same value for the same reading?

**Yes, on G7SensorKit's reading, which the captured data supports.** G7SensorKit, DiaBLE, Juggluco
and g7sim put a live reading at `counter − age` and a backfill reading at the record's counter, and
treat the two as equal. xDrip4iOS puts a live reading at `counter` and adds `age` to get the
sensor's age. If xDrip4iOS were right, G7SensorKit's live key would sit `age` seconds before the
same reading's backfill key.

The lifecycle vectors settle it for one session [M]. Their `age` varies (5 or 7 s), and so does the raw
counter mod 300 (205, 207). `counter − age` is constant mod 300 (200) for all seven readings after
start-up. That holds only if `counter − age` is the reading's position on the sensor's 5-minute grid
and `counter` is the time the message was sent.

| vector (`G7GlucoseMessageTests.swift`) | counter | age | counter − age | (counter − age) mod 300 | counter mod 300 |
|---|---|---|---|---|---|
| lifecycle 1-5, 7 | 205 … 2005 | 5 | 200 … 2000 | 200 | 205 |
| lifecycle 6 | 1707 | 7 | 1700 | 200 | 207 |

Reproduce: decode the hex strings at `G7GlucoseMessageTests.swift:33-43` (bytes 2-5 and 10-11,
little-endian).

xDrip4iOS's offset matters only to xDrip4iOS. If it ever built a key from `transmitterTime`, its live
and backfill keys for one reading would differ by `age`. It does not build one today.

Two smaller points:

- The backfill counter is 24-bit (`data[0..<3]`), good to 194 days, well past a 15.5-day session.
  The live counter is 32-bit. A key should print the decimal value, not the bytes.
- `sequence` is also sensor-side and appears in the backfill reply, but it is not a clean reading
  index. In the lifecycle vectors it runs 1, 3, 4, … against positions 80, 200, 500, …, and a backfill
  record does not carry it. The seconds counter is the better key.

### 7.4 What identifies the sensor across devices

| candidate | carried by | same on every device? | unique? | read by |
|---|---|---|---|---|
| BLE name `DXCM` + 2 characters | advertisement | yes | **no**: 2-character suffix, repeats across sensors (`DX02`/`DX01` for ONE+ and Stelo, g7sim `state.go:33-35`) | everyone; today's Loop `sensorID` |
| **serial number** | `0x4A` transmitter-version reply, bytes 14-19, u48, "the number printed on the applicator and encoded in the package barcode, rendered in decimal" (`TransmitterVersionMessage.swift:10-23` next-dev) | yes: a sensor property | yes | G7SensorKit **next-dev only** (`serialNumberString`, `G7CGMManager.swift:579,594`); `main` has no `0x4A` parser (no `TransmitterVersionMessage` file at `dd91f46`); xDrip4iOS sends `0x4A` (`CGMG7Transmitter.swift:90-95`; whether it keeps the serial was not checked) |
| `sessionNumber` + `sessionSignature` | calibration-bounds reply `0x32` (`DexcomG7.swift:319-330`); session byte 9 of `0x4E` (0 when *stopped*, 1 after, in the vectors) | presumably | signature meaning unknown | DiaBLE logs it; no one keys on it |
| activation estimate `now − counter` | derived | **no**: receive latency and clock offset differ (§6.4) | — | today's Loop key |

**Restart and extension.** The 12-hour grace period and the 15-day model are on the same counter.
The `0x52` session length includes the grace period (907,200 s for 10-day, 1,339,200 s for 15-day,
g7sim `state.go:49-56`). The captured *expired* reading is at 907,385 s, so the counter did not
reset at the 10-day boundary [M]. No G7 implementation read here has a session-start command (the
G7 opcode lists have stop `0x28` but no `0x26`: `G7Opcode.swift` next-dev, `DexcomG7.swift:18-48`), so
none can restart a G7 session. Whether any unsupported restart method resets the counter or increments
the session byte is **not known**. If one existed, the session number would belong in the key.

### 7.5 Verdict

`g7:<serial>:<seconds>`, where `<seconds>` = `messageTimestamp − age` for a live reading and the
record's `timestamp` for backfill, printed in decimal, **is device-independent on everything read
here**:

- **Counter:** sensor-side, from activation, shared by live and backfill, measured on one captured
  session.
- **Serial:** sensor-side.
- **Clock drift:** irrelevant. Neither input touches a receiving device's clock.
- **5-minute slots:** no rounding is needed or wanted. The counter lands on the sensor's own grid
  (`activation + k·300 + phase`, with phase 185-200 s in the post-warm-up vectors), so the exact integer is the key.
  Rounding to a 300-s slot would only add a boundary risk.

Caveats:

- **Not measured with two displays.** Points 1-5 in §7.2 make a per-slot counter very unlikely, but
  nothing rules it out.
- **The serial needs `0x4A`.** G7SensorKit `main` does not send it. Until it does, Loop cannot form
  this key, and a `DXCMxx` name is not a substitute (§6.4).
- **Readings before the serial arrives.** The serial comes after the first glucose message
  (`recordPendingSensorStart` waits for it, `G7CGMManager.swift:585-596` next-dev). Readings in that
  gap should carry no `identifier` rather than a partial one.

### 7.6 The lab that would settle it

Use one real G7 sensor (g7sim cannot settle this, because it encodes the assumption) and two displays
holding **different** slots:

- A. A phone on Loop next-dev in direct mode (display type 2). G7SensorKit already logs every
  `G7GlucoseMessage` with `messageTimestamp` and `age` and every `G7BackfillMessage`.
- B. A watch-type or receiver-type client. Juggluco or xDrip4iOS primary mode on a second phone,
  set to another display type, or a Dexcom receiver if its log can be exported.

Steps:

1. Run both for at least 2 hours, with B paired **at least a day after** sensor start. A per-pairing
   counter would then differ by about 86,400 s, which is impossible to miss.
2. For every 5-minute window, compare A's and B's `messageTimestamp − age`.
3. Force a gap on B (out of range for 30 min), then compare B's backfill `timestamp`s with A's live
   values for the same windows.
4. Read `0x4A` on both and compare serials.

Pass criterion: every shared window matches exactly. Record only the differences and counts, never
the serial or raw frames, in anything committed. Once one real capture exists, g7sim can then
regression-test that each client forms the same `g7:` string from the same bytes.

### 7.7 Other CGMs: which have a shared counter?

| CGM | counter | sensor-side? | today's client key | device-independent today? |
|---|---|---|---|---|
| **Dexcom G6** | transmitter seconds since *transmitter* activation (`0x25` current time; `Transmitter.swift:89,200` CGMBLEKit) | yes, one clock per transmitter, across sessions | CGMBLEKit: `"<transmitterID> <timestamp>"`, "consistent between backfill/live data" (`Glucose.swift:110-112` @ea224e7) | **yes in form** [R]. The transmitter ID is user-entered on every display and the clock is the transmitter's. Caveat: some G6 transmitters can be hard-reset (xDrip+ offers it, `DexTimeKeeper.java:39-41`), which restarts the clock and can repeat keys. |
| **Dexcom G7 / ONE+ / Stelo** | seconds since activation (§7.1) | very probably (§7.2) | Loop: activation-estimate prefix (§6.4) | **no today**; yes with the serial and §7.5 form |
| **Libre 3** | `lifeCount`, the sensor's minute counter (`RealtimeGlucoseReading.swift:6,153` LibreCRKit); "lets us back-derive activatedAt" (`LibreLoopSensorMonitor.swift:50-55`) | yes | LibreLoop (next-dev): `"libreloop-<serial>-<lifeCount>"` (`LibreLoopCGMManager+Pairing.swift:575,647,750`) | **yes in form** [R], except the `unknown` fallback at `:575` when the serial is missing (the same sentinel problem as C5) |
| **Libre 2** (LibreTransmitter) | minutes since start, read from the sensor (`LibreTransmitterManagerV3.swift:381`) | yes | `"<startDate epoch><glucose>"` (`LibreGlucose.swift:33-35` @4110512): a date from the receiving device plus the value | **no**. The counter exists but is not used in the key. |

Not checked here: how Libre 2/3 multi-reader access works (NFC by a second phone versus one BLE
link at a time), and xDrip+/Juggluco/DiaBLE Libre keys.

### 7.8 Implications

**For the reply's option 3.** The source-derived identifier is sound for G7 if it uses only the
serial and the sensor counter. Suggested wording:

> For a G7, an identifier both devices can compute is `g7:<serial>:<seconds>`, where `<serial>` is the
> sensor serial number from the transmitter-version (`0x4A`) reply and `<seconds>` is the sensor's
> seconds-since-activation counter for the reading (`messageTimestamp − age` for a live reading, the
> record's `timestamp` for backfill). Every G7 implementation we read (G7SensorKit, xDrip+, xDrip4iOS,
> Juggluco, DiaBLE) treats that counter as the sensor's session clock, and a captured session lands on
> its 5-minute grid only that way. We have not yet seen a capture with two displays on one sensor, so
> we would confirm with one before relying on it. The activation date estimated from the receiving
> device's clock must not be part of it.

**For Loop.**

- **Change the key:**
  - drop the `activatedAt.hours` token;
  - key on `serialNumberString`, which next-dev already reads;
  - keep the counter it already uses (`glucoseTimestamp` / backfill `timestamp`, which agree);
  - send no identifier until the serial is known.
- **Leave `date` alone:** it can stay derived from the per-device activation estimate, since dates
  are not compared for identity under the two-id rule.
- **Before shipping:** the two-display capture in §7.6.

## 8. Reproduce

```sh
python3 -I docs/60-research/tenancy/identifier-format-2026-10-17/idshape.py
python3 -I docs/60-research/tenancy/identifier-format-2026-10-17/idshape.py --control
```

The §3.3 harnesses take the cgm-remote-monitor checkout (for its `node_modules`) as their argument:

```sh
node docs/60-research/tenancy/identifier-format-2026-10-17/v3-path-routing.js <cgm-remote-monitor checkout>
node docs/60-research/tenancy/identifier-format-2026-10-17/index-key-size.js <cgm-remote-monitor checkout>  # needs mongod on 127.0.0.1:27017; creates and drops idfmt_scratch_20261017
```

`idshape.py` needs `externals/ns-data` at the main checkout's path (as the companion script's `BASE` names) and the
companion script beside this folder (its classifiers are imported). Runs in about 5 s. The control
plants six documents in site a (a G7-form and an `invalid` Loop `syncIdentifier`, a colon and a G6-form
entry `identifier`, a 24-alphanumeric `_id`, a Trio upper-case UUID `id`); each moves exactly its own
counter (`control-results-2026-10-17.txt`).
