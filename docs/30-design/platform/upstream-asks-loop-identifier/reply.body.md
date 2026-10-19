**Re: client-supplied identifiers for Nightscout**

Thank you for writing this up. We agree with the core of the ask, and most of what Loop needs
already works. Much of the confusion comes from our API documentation, not the design: API v3's
swagger says "The client should not create the identifier", but the server keeps one a client
sends. That sentence is wrong; we track it as BF-169.

Code references are to cgm-remote-monitor `15.0.8` (`92d08342`) and `dev` at `fade2299` (the
15.0.9 candidate).

## The contract, in three rules

1. **`_id` is a MongoDB ObjectId (24 hex characters) or absent.** A client that keeps a local
   cache may create its own ObjectId and send it over API v1. (API v3 stores a body `_id` as sent, so
   a 24-hex value becomes a string there; measured 2026-10-18, [record identity reference](https://bewest.github.io/rag-nightscout-ecosystem-alignment/docs/10-domain/record-identity-reference.html).) ObjectIds are designed to be made by clients
   without coordination (a timestamp, a random part and a counter). Other values in `_id` are not
   valid. For compatibility, `UUID_HANDLING` (on by default) moves any string `_id` that is not 24
   hex characters to `identifier` on treatments and entries, and the server assigns the ObjectId.
2. **If `_id` is absent, send `identifier`**: an opaque string, compared exactly as sent. It does
   not have to be a UUID. The server assigns `_id`. One identifier names one record.
3. **If neither is sent**, the server falls back to the collection's time key: entries
   `sysTime` + `type`, treatments `created_at` + `eventType`. This fallback may be deprecated
   later.

**Tie-break:** if a write carries both and they point at different records, `identifier`
decides. That is what v1 treatments do today (they drop `_id` when `identifier` is present), what
rule 5 of our design decision D20 says, and what your proposal implies, since `identifier` is the
key clients own. Rule 5 also says what every write reply should carry:

> **Two ids, one rule.** … Every write reply returns both.
> ([D20 rule 5](https://bewest.github.io/rag-nightscout-ecosystem-alignment/docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.html#263-d20--version-scoped-quirks-and-the-two-id-rule-maintainer-2026-10-16))

Returning both means a client never needs a cache of server ids to edit or delete what it sent.

**What an `identifier` is.** It names the real thing a record describes: this CGM reading, this
pump event, this carb entry. Two uploads of the same thing should carry the same value, whichever
app sends it. The server treats it as opaque and enforces one record per identifier in each
collection; clients compute the values from a published
[conventions table](https://bewest.github.io/rag-nightscout-ecosystem-alignment/docs/30-design/platform/identifier-conventions.html),
one row per record kind. Values are written in URL syntax. Readings and pump events take the
manufacturer as the scheme and the model as the first segment, so every app that reads one sensor
produces the same value: for a G7 reading, `dexcom://g7/<serial>/<sensor offset>`. Records made in
the app take the app's scheme, with the kind as the first segment: `loop://carbs/<uuid>`,
`loop://tempbasal/<syncIdentifier>`, `loop://override/<uuid>`. Would that work for Loop?

**What an `identifier` may contain (proposed).** 1 to 256 characters from `A-Z a-z 0-9 . _ ~ : / -`,
and under MongoDB's index key limit. In API v3 paths (`/api/v3/{collection}/{identifier}`), send
it percent-encoded as one path segment (`/` as `%2F`, `:` as `%3A`): that works for GET, PATCH,
PUT and DELETE on 15.0.8 and `dev`, while a raw `/` is 404 (measured 2026-10-18,
[identifier format §3.4](https://bewest.github.io/rag-nightscout-ecosystem-alignment/docs/60-research/tenancy/identifier-format-2026-10-17.html#34-url-form-identifiers-end-to-end-2026-10-18-m)).
No `%`, `?`, `#` or space. Not exactly 24 hex
characters, which both APIs read as an `_id`. Never a placeholder such as `invalid`, `undefined`,
`null` or `NaN`: once identifiers are matched, every reading sharing one would overwrite the last.
A UUID (v4 for a record made on one device, or v5 of a source-derived key) is needed only for
today's v1 by-`_id` routes (`find[_id]=`, `DELETE /api/v1/treatments/:id`), which recognise
UUID-shaped values only. API v3 and `find[identifier]=` take any string
([identifier format](https://bewest.github.io/rag-nightscout-ecosystem-alignment/docs/60-research/tenancy/identifier-format-2026-10-17.html)).

## What works today, and the one gap

| path | status |
|---|---|
| v1 treatments, `identifier` | works since 15.0.7 (#8421, `cdef1e7c`): matched first, and the reply carries the stored `_id` ([treatments.js:356-381](https://github.com/nightscout/cgm-remote-monitor/blob/92d0834219aa771b5837dbcbf1baeb839a200cf6/lib/server/treatments.js#L356-L381), [104-128](https://github.com/nightscout/cgm-remote-monitor/blob/92d0834219aa771b5837dbcbf1baeb839a200cf6/lib/server/treatments.js#L104-L128)) |
| API v3, every collection, `identifier` | works: a client value is kept and re-sends match on it ([operationTools.js:114-126](https://github.com/nightscout/cgm-remote-monitor/blob/92d0834219aa771b5837dbcbf1baeb839a200cf6/lib/api3/shared/operationTools.js#L114-L126)) |
| client ObjectId `_id` | v1 treatments: works on 15.0.8. v1 device status: works on `dev` (#8758; a re-send is answered with the stored record, [devicestatus.js:57-90](https://github.com/nightscout/cgm-remote-monitor/blob/fade229909e6f3a0b5459230bc7273fe85de4f32/lib/server/devicestatus.js#L57-L90)); on 15.0.8 a re-sent `_id` fails the POST with 500 and loses the rest of the batch |
| **v1 entries and device status, `identifier`** | **the gap**: stored, not matched. Entries match on `sysTime` + `type` only ([entries.js:238-255](https://github.com/nightscout/cgm-remote-monitor/blob/92d0834219aa771b5837dbcbf1baeb839a200cf6/lib/server/entries.js#L238-L255)); device status has no key |

## Your watch-and-phone case

Neither id alone solves two devices uploading one reading: both must arrive at the same key.

| option | server change |
|---|---|
| 1. one uploader at a time (today's workaround) | none |
| 2. both devices agree on the timestamp: the phone adopts the watch's activation estimate for the loaned period | none: v1 entries already merge on `sysTime` + `type`. The match is exact, so the times must be identical to the millisecond. `device` need not match: it is not part of the v1 key (over API v3 it would, because the server computes `identifier` from `device` + `date`). The later upload's fields overwrite the stored ones (`$set`), so `device` becomes the phone's ([entries.js:127-136](https://github.com/nightscout/cgm-remote-monitor/blob/92d0834219aa771b5837dbcbf1baeb839a200cf6/lib/server/entries.js#L127-L136)) |
| 3. a source-derived identifier, `dexcom://g7/<serial>/<seconds>` | entries match on `identifier` (the one change below). The inputs must come from the sensor: the real serial and the sensor's own seconds counter |
| 4. server-side fuzzy time matching | avoid: it can merge readings from two real sensors |

We recommend (3), with (2) as an interim that needs no server change. Today's G7 `syncIdentifier`
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
- **Entries do not match on `identifier` until the server change lands.** A re-send with the same
  identifier and a different time is stored twice
  ([lab](https://bewest.github.io/rag-nightscout-ecosystem-alignment/tools/lab/v3-identifier-immutable/results/v3-identifier-immutable-2026-10-17.html)).
- **Older servers store the field and ignore it.**

## Six cases: what should Nightscout do?

To make the contract unambiguous, we would like your answer for each case. "Our default" is what
our decisions so far would give (write contract, 2026-10-12), chosen to keep today's clients
working. Where it says *open*, we have no default yet.

| # | case | today | our default | your answer |
|---|---|---|---|---|
| 1 | The watch uploads a G7 reading. Later the phone uploads the same reading: same `identifier`, other `device`, time 1.5 s later | v1 entries: two records. API v3: 400 | one record, updated with the later upload's fields (merge on match) | |
| 2 | Loop re-sends a carb entry after the user edits its amount or time, same `identifier` | v1 treatments: updated. API v3: 400 if the time changed | updated (merge); an explicit `PUT` replaces | |
| 3 | Loop re-sends an identical record after a timeout | v1 entries and treatments: matched, but a treatment matched by time is answered without `_id` (BF-165). v1 device status: stored again. API v3: matched | success, and the reply carries the stored `_id` and `identifier` | |
| 4 | A record is deleted, then the same `identifier` arrives again | API v3 (soft delete): the record comes back. v1 (hard delete): a new record | *open* | |
| 5 | An older app sends no `identifier` | each collection's time key | keep the time key on legacy paths now; `identifier` becomes mandatory at a future version boundary and for registered controller instances | |
| 6 | One write carries an `_id` and an `identifier` that name different stored records | v1 treatments: `identifier` wins, `_id` is dropped | `identifier` wins, as today (the tie-break above) | |

For case 1, if you would rather Nightscout keep the first upload unchanged, or refuse the second,
please say so and what the phone should do next. An error reply makes NightscoutKit treat the
batch as failed.

## What we will do

One server change: v1 entries and device status match on `identifier` the way treatments do.
With it, the swagger fix (BF-169). Both land after 15.0.9, which is frozen as `dev` stands. Your
answers above decide the rest. Later, and only if needed: identifier length and character
checks (a warning first), results per record in a batch, and a unique index on `identifier`.

Details and evidence are in our
[notes on your proposal](https://bewest.github.io/rag-nightscout-ecosystem-alignment/docs/30-design/platform/upstream-asks-loop-identifier/index.html).

Where would you like to continue?
