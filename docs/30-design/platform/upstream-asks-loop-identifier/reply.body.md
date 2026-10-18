**Re: client-supplied identifiers for Nightscout**

Thank you for writing this up. We agree with the core of the ask, and most of what Loop needs
already works. Much of the confusion comes from our API documentation, not the design: API v3's
swagger says "The client should not create the identifier", but the server keeps one a client
sends. That sentence is wrong; we track it as BF-169.

Code references are to cgm-remote-monitor `15.0.8` (`92d08342`) and `dev` at `fade2299` (the
15.0.9 candidate).

## The contract, in three rules

1. **`_id` is a MongoDB ObjectId (24 hex characters) or absent.** A client that keeps a local
   cache may create its own ObjectId and send it. ObjectIds are designed to be made by clients
   without coordination (a timestamp, a random part and a counter). Other values in `_id` are not
   valid. For compatibility, `UUID_HANDLING` (on by default) moves a UUID `_id` to `identifier` on
   treatments and entries, and the server assigns the ObjectId.
2. **If `_id` is absent, send `identifier`**: a string. We recommend a UUID: v5 of a
   source-derived key when several devices must agree, v4 created once for a manual entry. The
   server assigns `_id`. One identifier names one record.
3. **If neither is sent**, the server falls back to the collection's time key: entries
   `sysTime` + `type`, treatments `created_at` + `eventType`. This fallback may be deprecated
   later.

**Tie-break (proposed):** if a write carries both and they point at different records, `_id`
decides. This differs from rule 5 of our design decision D20, which tries `identifier` first, and
from v1 treatments today, which drop `_id` when `identifier` is present. We will record it as a
decision. Rule 5 also says what every write reply should carry:

> **Two ids, one rule.** … Every write reply returns both.
> ([D20 rule 5](https://bewest.github.io/rag-nightscout-ecosystem-alignment/docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.html#263-d20--version-scoped-quirks-and-the-two-id-rule-maintainer-2026-10-16))

Returning both means a client never needs a cache of server ids to edit or delete what it sent.

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
| 3. a source-derived identifier, `g7:<serial>:<seconds>` or its UUIDv5 | entries match on `identifier` (the one change below) |
| 4. server-side fuzzy time matching | avoid: it can merge readings from two real sensors |

We recommend (3), with (2) as an interim that needs no server change. Precedents: FHIR keeps
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
  Sent as `identifier` to 15.0.7 or later, the second would replace the first.
- **Entries do not match on `identifier` until the server change lands.** A re-send with the same
  identifier and a different time is stored twice
  ([lab](https://bewest.github.io/rag-nightscout-ecosystem-alignment/tools/lab/v3-identifier-immutable/results/v3-identifier-immutable-2026-10-17.html)).
- **Older servers store the field and ignore it.**

## What we will do

One server change: v1 entries and device status match on `identifier` the way treatments do.
With it, the swagger fix (BF-169). Both land after 15.0.9, which is frozen as `dev` stands. Could you confirm that the simple contract fits Loop?

## Later, only if needed

- Whether a re-send with changed fields is an edit or a duplicate, and versioning, HealthKit-style.
- The identifier's length limit, character set and case comparison.
- Per-record results in batch replies.
- A unique index on `identifier`.
- API v3's immutable `date` and `device` on an identifier match (400 today, measured in the lab above).
- Device status's identical-body retry rule, once `identifier` is matched.

Details and evidence are in our
[notes on your proposal](https://bewest.github.io/rag-nightscout-ecosystem-alignment/docs/30-design/platform/upstream-asks-loop-identifier/index.html).

Where would you like to continue?
