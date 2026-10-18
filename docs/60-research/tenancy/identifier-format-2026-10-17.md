# ID-FORMAT: should Nightscout require a client `identifier` to be a UUID?

*Contributor-facing.* **Snapshot, 2026-10-17.** Input to queue item `ID-FORMAT-DECISION` and to the
reply in [upstream-asks-loop-identifier](../../30-design/platform/upstream-asks-loop-identifier/reply.body.md).
Companion to [identifier duplicates](identifier-duplicates-2026-10-17.md), whose corpus, site labels
and client classes this note reuses.

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

To verify before relying on it (not checked here): that `messageTimestamp` ("seconds since pairing of
the *message*", `G7GlucoseMessage.swift:18`) counts from the sensor session and not from each
display's pairing slot. If it is per slot, a phone and a watch holding separate slots would see
different counters and no sensor-relative key would agree.

## 7. Reproduce

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
