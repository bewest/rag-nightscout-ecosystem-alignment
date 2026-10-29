**Re: client-supplied identifiers for Nightscout**

Thank you for writing this up. We agree with the core of the ask, and most of what Loop needs
already works. The one gap we found, v1 entries and device status ignoring `identifier` on a
re-send, is closed for 16.0.0. Much of the earlier confusion came from our API documentation, not
the design: API v3's swagger said "The client should not create the identifier", but the server
keeps one a client sends. That sentence is removed for 16.0.0 (BF-169).

Code references are to cgm-remote-monitor `15.0.9` (`c6a0d8ed`, released 2026-10-21) and `dev` at
`7abe1cf6`, which becomes 16.0.0 (in development, not released). Behaviour marked *measured* is from
our [record identity lab of 2026-10-27](https://bewest.github.io/rag-nightscout-ecosystem-alignment/tools/lab/record-identity/results/record-identity-2026-10-27.html),
which runs both versions side by side.

## The contract, in three rules

1. **`_id` is a MongoDB ObjectId (24 hex characters) or absent.** A client that keeps a local
   cache may create its own ObjectId and send it over API v1. (Over API v3, send `identifier` instead:
   from 16.0.0 API v3 refuses a body `_id` with HTTP 400, and 15.0.9 and earlier store it as sent, so
   a 24-hex value becomes a string there; measured.) ObjectIds are designed to be made by clients
   without coordination (a timestamp, a random part and a counter). Other values in `_id` are not
   valid. For compatibility, `UUID_HANDLING` (on by default) moves any string `_id` that is not 24
   hex characters to `identifier` on treatments and entries, and the server assigns the ObjectId.
2. **If `_id` is absent, send `identifier`**: an opaque string, compared exactly as sent. It does
   not have to be a UUID. The server assigns `_id`. One identifier names one record in each
   collection.
3. **If neither is sent**, the server falls back to the collection's time key: entries
   `sysTime` + `type`, treatments `created_at` + `eventType`. This fallback stays. Sending
   `identifier` is recommended for every app. It will be required for controllers that register with
   Nightscout, a registration interface we are building, which apps opt into.

**Tie-break:** if a write carries both and they point at different records, `identifier`
decides. That is what v1 treatments do today (they drop `_id` when `identifier` is present), what
rule 5 of our design decision D20 says, and what your proposal implies, since `identifier` is the
key clients own. Rule 5 also says what every write reply should carry:

> **Two ids, one rule.** … Every write reply returns both.
> ([D20 rule 5](https://bewest.github.io/rag-nightscout-ecosystem-alignment/docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.html#263-d20--version-scoped-quirks-and-the-two-id-rule-maintainer-2026-10-16))

Returning both means a client never needs a cache of server ids to edit or delete what it sent.

**What an `identifier` is.** It names the real thing a record describes: this CGM reading, this
pump event, this carb entry. Two uploads of the same thing should carry the same value, whichever
app sends it. The server treats it as opaque and keeps one record per identifier in each
collection; clients compute the values from a published
[conventions table](https://bewest.github.io/rag-nightscout-ecosystem-alignment/docs/30-design/platform/identifier-conventions.html),
one row per record kind. Values are written in URL syntax. Readings and pump events take the
manufacturer as the scheme and the model as the first segment, so every app that reads one sensor
produces the same value: for a G7 reading, `dexcom://g7/<serial>/<sensor offset>`. Records made in
the app take the app's scheme, with the kind as the first segment: `loop://carbs/<uuid>`,
`loop://tempbasal/<syncIdentifier>`, `loop://override/<uuid>`. The kind segment also keeps values
unique across collections, which the server does not check. Would that work for Loop?

**What an `identifier` may contain (proposed).** 1 to 256 characters from `A-Z a-z 0-9 . _ ~ : / -`,
and under MongoDB's index key limit. In API v3 paths (`/api/v3/{collection}/{identifier}`), send
it percent-encoded as one path segment (`/` as `%2F`, `:` as `%3A`): that works for GET, PATCH,
PUT and DELETE, while a raw `/` is 404 (measured 2026-10-18 on 15.0.8 and the 15.0.9 candidate,
[identifier format §3.4](https://bewest.github.io/rag-nightscout-ecosystem-alignment/docs/60-research/tenancy/identifier-format-2026-10-17.html#34-url-form-identifiers-end-to-end-2026-10-18-m)).
No `%`, `?`, `#` or space. Not exactly 24 hex
characters, which both APIs read as an `_id`. Never a placeholder such as `invalid`, `undefined`,
`null` or `NaN`: once identifiers are matched, every reading sharing one would overwrite the last.
A UUID (v4 for a record made on one device, or v5 of a source-derived key) is needed only for
today's v1 by-`_id` routes (`find[_id]=`, `DELETE /api/v1/treatments/:id`), which recognise
UUID-shaped values only. API v3 and `find[identifier]=` take any string
([identifier format](https://bewest.github.io/rag-nightscout-ecosystem-alignment/docs/60-research/tenancy/identifier-format-2026-10-17.html)).

## What works, by version

| path | 15.0.9 | 16.0.0 (`dev`) |
|---|---|---|
| v1 treatments, `identifier` | matched first, the reply carries the stored `_id` (since 15.0.7, #8421) | the same; a treatment matched by time (no ids) is now also answered with its `_id` (BF-165), measured |
| API v3, every collection, `identifier` | a client value is kept and re-sends match on it | the same |
| v1 entries, `identifier` | stored, not matched: a re-send at another time is a second record, measured | **matched**: one record, updated (#8859), measured |
| v1 device status, `identifier` | stored, not matched: two records, measured | **matched**: a re-send writes nothing and is answered with the stored `_id` (#8859), measured |
| client ObjectId `_id`, v1 | treatments, entries and device status: a re-send is matched, measured | the same; a re-sent profile `_id` is answered 200 instead of 500, measured |

A merge on a match follows RFC 7386 from 16.0.0: a field sent as `null` is removed from the stored
record, and a field left out is kept. A `PUT` replaces the record.

## Your watch-and-phone case

Neither id alone solves two devices uploading one reading: both must arrive at the same key.

| option | server change |
|---|---|
| 1. one uploader at a time (today's workaround) | none |
| 2. both devices agree on the timestamp: the phone adopts the watch's activation estimate for the loaned period | none: v1 entries already merge on `sysTime` + `type`. The match is exact, so the times must be identical to the millisecond. `device` need not match: it is not part of the v1 key (over API v3 it would, because the server computes `identifier` from `device` + `date`). The later upload's fields overwrite the stored ones, so `device` becomes the phone's |
| 3. a source-derived identifier, `dexcom://g7/<serial>/<seconds>` | none from 16.0.0: v1 entries match on `identifier`. The inputs must come from the sensor: the real serial and the sensor's own seconds counter |
| 4. server-side fuzzy time matching | avoid: it can merge readings from two real sensors |

We recommend (3), with (2) as an interim that works on any version. Today's G7 `syncIdentifier`
would not serve (3) as it stands. It embeds each device's own activation estimate, as fractional
hours, and the BLE name `DXCMxx` rather than the serial, and it falls back to `"invalid"`
(G7SensorKit `dd91f46`, `G7CGMManager.swift:511-517`). Hashing it into a UUIDv5 would not help,
because the input already differs between devices.

For a G7, an identifier both devices can compute is `dexcom://g7/<serial>/<seconds>`. `<serial>` is the
sensor serial from the transmitter-version (`0x4A`) reply, which G7SensorKit `next-dev` reads.
`<seconds>` is the sensor's seconds-since-activation counter for the reading: `messageTimestamp −
age` for a live reading, the record's `timestamp` for backfill. Every G7 implementation we read
(G7SensorKit, xDrip+, xDrip4iOS, Juggluco, DiaBLE) treats that counter as the sensor's own
session clock, and backfill uses the same clock. We have not yet seen a capture with two
displays on one sensor, so we would confirm with one before relying on it
([identifier format §7](https://bewest.github.io/rag-nightscout-ecosystem-alignment/docs/60-research/tenancy/identifier-format-2026-10-17.html#7-is-the-g7-seconds-counter-shared-across-devices)).
G6 (`<transmitterID> <timestamp>`, as `dexcom://g6/<transmitterID>/<timestamp>`) and Libre 3
(`<serial>-<lifeCount>`, as `abbott://libre3/<serial>/<lifeCount>`) already key on a sensor-side
counter; Loop's Libre 2 key uses the phone's clock.

Precedents: FHIR keeps
the server id apart from the business `identifier`, and its conditional create answers 200 with
the existing record when the identifier already matches
([Aidbox](https://www.health-samurai.io/docs/aidbox/api/rest-api/crud/create)). HealthKit pairs
a [sync identifier](https://developer.apple.com/documentation/healthkit/hkmetadatakeysyncidentifier)
with a sync version, so a newer version of a sample replaces the stored one (Apple's pages word
the comparison slightly differently).

## Cautions for Loop starting today

- **Each identifier must name exactly one record.** In our corpus, 13 of 255,811 Loop
  `syncIdentifier` values are on 2 to 4 treatments, for example a Suspend Pump and a Temp Basal
  pair ([identifier duplicates §2.2](https://bewest.github.io/rag-nightscout-ecosystem-alignment/docs/60-research/tenancy/identifier-duplicates-2026-10-17.html#22-syncidentifier-on-treatments-as-a-proxy-m)).
  Sent as `identifier` to 15.0.7 or later, the second would replace the first. A kind segment
  (`loop://suspend/…`, `loop://tempbasal/…`) keeps such a pair apart.
- **On 15.0.9 and earlier, entries and device status do not match on `identifier`.** A re-send
  with the same identifier is stored twice there; from 16.0.0 it is matched
  ([lab](https://bewest.github.io/rag-nightscout-ecosystem-alignment/tools/lab/v3-identifier-immutable/results/v3-identifier-immutable-2026-10-27.html)).
- **Older servers store the field and ignore it.**
- **A carb edit can be lost.** Loop 3.14.9 sends a carb edit as a v1 `PUT` by the record's `_id`, which
  it caches for 24 hours. If the `_id` is no longer cached, the edit is not sent at all, and nothing tells
  the user. The server can take the edit by `identifier` instead: API v3 `PATCH` or `PUT`
  `/api/v3/treatments/{identifier}` today, and a v1 re-send with the same `identifier` (merged on match).
  Would Loop send edits that way?

## Six cases: what should Nightscout do?

To make the contract unambiguous, we would like your answer for each case. "Our default" is what
our decisions so far give, chosen to keep today's clients working.

| # | case | 15.0.9 / 16.0.0 today (measured) | our default | your answer |
|---|---|---|---|---|
| 1 | The watch uploads a G7 reading. Later the phone uploads the same reading: same `identifier`, other `device`, time 1.5 s later | v1 entries: two records on 15.0.9, one (updated) on 16.0.0. API v3: 400 on both | one record, updated with the later upload's fields (merge on match) | |
| 2 | Loop re-sends a record that changed after its first upload, same identity: a dose whose final amount differs, or an override ended early (Loop 3.14.9 does both by `POST`; a carb edit is a `PUT`, below) | v1 treatments: updated. API v3: 400 if the date, device or event type changed | updated (merge), kept as the default; an explicit `PUT` replaces. A switch, a site setting or a per-client rule, may later select keep-first or refuse for clients that opt in | |
| 3 | Loop re-sends an identical record after a timeout | 16.0.0: matched, and the reply carries the stored `_id`, on v1 entries, treatments and device status and on API v3. 15.0.9: device status stored again, and a treatment matched by time is answered without `_id` | success, and the reply carries the stored `_id` and `identifier` | |
| 4 | A record is deleted, then the same `identifier` arrives again | v1 (hard delete): stored again as a new record. API v3 (soft delete): a `POST` brings it back, a `PUT` is 410; on 16.0.0 an API v3 device status stays deleted | the re-send is acknowledged (a success reply naming the stored record, so the app stops retrying) and the record **stays deleted** (decided 2026-10-27; not built yet) | |
| 5 | An app sends no `identifier` | each collection's time key | the time key stays; `identifier` is recommended for every app and required for registered controller instances | |
| 6 | One write carries an `_id` and an `identifier` that name different stored records | v1 treatments: `identifier` wins, `_id` is dropped | `identifier` wins, as today (the tie-break above) | |

For case 1, if you would rather Nightscout keep the first upload unchanged, or refuse the second,
please say so and what the phone should do next. An error reply makes NightscoutKit treat the
batch as failed. For case 4, would Loop treat a success reply for a deleted record as final?

## What we have done, and what is next

Done for 16.0.0, on `dev` now: v1 entries and device status match on `identifier` (#8859), the
swagger correction (BF-169) and API v3's refusal of a body `_id` (#8845). Next: case 4's re-send
after delete, results per record in a batch, and a unique index on `identifier` per collection,
each after your answers. Later, and only if needed: identifier length and character checks (a
warning first).

Details and evidence are in our
[notes on your proposal](https://bewest.github.io/rag-nightscout-ecosystem-alignment/docs/30-design/platform/upstream-asks-loop-identifier/index.html).

Where would you like to continue?
