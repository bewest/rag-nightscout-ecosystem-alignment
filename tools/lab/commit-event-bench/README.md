# commit-event-bench lab

Measures what decision **D-EVENT** would cost and buy. Today (dev `9668b179`),
`lib/storage/write-step.js` `publish()` emits the internal event `storage-write-committed` once
per driver call (`insertOne` … `bulkWrite`). Its frozen payload is
`{collection, source, operation, partial, counts:{inserted, upserted, modified, deleted}}` and
names no record. **Option 1** keeps one event per call and adds
`records: [{change, _id, identifier?}]` for every record the call inserted, upserted, modified or
deleted. **Option 2** keeps the payload as it is.

> Contributor-facing. Synthetic data only: the lab writes its own records into its own databases
> and must never be pointed at a real site.

## Status

**D-EVENT was deferred on 2026-10-27.** No event shape is adopted. This lab is research to inform
that decision, and it continued after the deferral.

- **Round 1** compares base with the uncapped pre-read variant.
- **Round 2** ([below](#round-2-2026-10-27-post-write-capped-and-counts-only-deletes)) adds
  three arms:
  - the post-write variant
  - the same variant with counts-only deletes
  - a pre-read capped at 500 records (the pattern Nocturne uses)
- **Round 3** ([below](#round-3-2026-10-29-since-watermark)) adds Ben's since-watermark arm. Each
  table reports misses (which matter for a cache catch-up) and cross-attribution (which matters for
  a per-write event) separately.
- **Prior art.** Comparable systems name records from the database's own log (change streams,
  an oplog or write-ahead log) or by a read before the write. A read after the write cannot see
  deleted records. It also misses records whose filter fields the update itself changed. Round 2
  measures both of these.

## What it measures

| axis | script | question |
|---|---|---|
| (a) | `bench.js` | Write latency and throughput of 16 write shapes and two 1,000-record backfills, base vs prototype, with arms interleaved |
| (b) | `payload.js` | Event bytes at 1, 100, 1,000 and 10,000 records per call, the cost of naming them (in-process, through each tree's `write-step.js`), and what a listener pays to act on the event |
| (c) | `changefeed.js` | Can a consumer rebuild which records were created, modified or deleted from the events alone, or does it need a follow-up read? Ground truth is MongoDB's change stream |
| (d) | `concurrent.js` | With 3k uploaders at once (k = 1, 2, 4), plus an optional pruner racing the CGM bridges: latency, throughput, and whether any event names another writer's record |
| — | `inventory.js` | Which driver calls (and events) each shape makes on a tree |

The 16 shapes come from the forms of `tools/qc/write-contract-matrix.js` (create, resend,
update, update-put, softdelete, harddelete) over the v1, v3 and socket paths. The two v1
writes that are not in that matrix are the query delete (`DELETE /api/v1/entries/?find[...]`, a
`deleteMany` of 10 records) and a devicestatus upload. Driver calls, from `results/inventory-base.log`:

| shape | driver call | shape | driver call |
|---|---|---|---|
| v1-entries-create | bulkWrite (upsert) | v3-treatments-create | insertOne |
| v1-entries-resend | bulkWrite (matched) | v3-treatments-resend | replaceOne |
| v1-entries-query-delete-10 | deleteMany (10) | v3-treatments-patch | updateOne |
| v1-devicestatus-create | insertMany | v3-treatments-put | replaceOne |
| v1-treatments-create | bulkWrite (upsert) | v3-treatments-delete-permanent | deleteMany |
| v1-treatments-put | replaceOne | ws-treatments-dbAdd | insertOne |
| v1-treatments-softdelete | replaceOne | ws-treatments-dbUpdate | updateMany |
| v1-treatments-delete-id | deleteMany | ws-treatments-dbRemove | deleteMany |
| v1-entries-backfill-1000 | bulkWrite (1,000 upserts) | v1-treatments-backfill-1000 | bulkWrite (1,000 upserts) |

No shape reaches `deleteOne`.

## The prototype (option 1)

Branch `proto/d-event-per-call` in `externals/cgm-remote-monitor-official`, head `8a396715`
(parent `9668b179`). It changes only `lib/storage/write-step.js` and `tests/write-step.test.js`.

- **Inserted and upserted records** come from the driver result (`insertedId(s)`,
  `upsertedId(s)`, keyed by operation index), with the `identifier` of the document that was sent.
  This needs no extra I/O. In a partial batch, the records the driver did not commit (its
  `writeErrors`, and everything after the first error in an ordered batch) are left out.
- **Matched records** (update, replace and delete) are named by one read before the write. The
  read is `find` of the call's filters (an `$or` when there are several), projected to
  `{_id, identifier}`, with `limit(1)` for single-document calls. There is one read for
  updates/replacements and one for deletes. **This read is the cost of option 1.**
- The read runs **only when a listener is attached** (`bus.listenerCount(...) > 0`). Nothing
  subscribes in production today, so as of `9668b179` production would pay nothing (arm `proto0` below).
- A failed identity read does not fail the write. The event then names only what the result
  names.
- The read is **not atomic** with the write. A concurrent writer can insert or delete a matching
  record between the read and the write. `counts` still come from the driver, so a listener can
  see when a change kind has more or fewer records than its count, and treat that event as inexact.
- The event stays internal, frozen (records and each record frozen) and off public channels. It
  still carries no document contents and no selectors.

Tests changed: in `tests/write-step.test.js`, the first test used to assert that the stored `_id`
is **absent** from the event (`!includes('stored')`). That pins option 2, so it now pins the
named record. Three tests are new: identity for insert, delete and a mixed upsert batch (including
the projected read); the committed records of a partial batch (unordered and ordered); and no
identity read without a listener. The other five tests that listen for the event
(`storage.v1-writes`, `api.crud-by-id.matrix`, `api3.storage.filter-semantics`,
`websocket.partial-reconciliation`, `api3.configured-write-boundary`) check only
collection, source and counts. They pass unchanged.

Controls for the new tests:
- **Red on base.** The proto test file on the base tree has 3 failing tests (21 passing), and
  each fails because `records` is undefined.
- **Break-it.** Removing the listener gate (`return true || ...`) makes "reads nothing for record
  identity when no listener is attached" fail. That test passes vacuously on base, because base
  never reads.

`npm test` (MongoDB 8.0.29 on 127.0.0.1:27602, Node v22.23.4):
- proto `8a396715`: **4703 passing, 0 failing, 3 pending**
- base `9668b179` (control, port 27603): **4700 passing, 0 failing, 3 pending**

## Run it

```sh
tools/lab/commit-event-bench/run.sh up     # mongo:8.0.29 single-node replica set on 127.0.0.1:27601
tools/lab/commit-event-bench/run.sh all    # every axis and control -> results/*.log, results/*.json
tools/lab/commit-event-bench/run.sh down
```

The trees are set by `CEB_BASE`, `CEB_NOOP` and `CEB_PROTO`, and default to
`externals/work/crm-devent-{base,noop,proto}`. Each tree needs its own `npm ci`. The API secret is
generated per run and is never written to disk. Each arm is its own `server.js` child: the tree
booted as `lib/server/server.js` boots it, with its own database. Every log starts and ends with
the container's `docker inspect` state and restart count.

## Results (2026-10-27)

Anchors:

| item | value |
|---|---|
| base | `9668b179` (dev) |
| no-op control | `1d4a8753` (base plus one comment line in `write-step.js`) |
| proto | `8a396715` |
| Node | v22.23.4 |
| MongoDB | 8.0.29 (`mongo:8.0.29`), single-node replica set, `--ulimit nofile=64000:64000`, `directConnection=true` |
| host | one Linux host, everything on localhost |
| containers | `restarts=0`, and the same `StartedAt` (2026-10-27T21:33:00Z) at the start and end of every axis log |

### (a) Latency, n = 200 per shape and per arm, interleaved

Five arms, each with its own process and database on one mongod. Each iteration shuffles the
shape order, seeds every arm (untimed), then times one call per arm in shuffled arm order. The arms:

- `base`: base with one counting listener
- `base2`: the same tree in a second process, which gives the **noise floor**
- `noop`: the **no-op commit** control
- `proto`: proto with one listener
- `proto0`: proto with no listener, as production runs today

Wall time was 821 s. There were 0 errors, and 5,801 events reached each listening arm.

Ratios are arm/base. Columns are median (med) and p95.

| shape | base med / p95 ms | base2/base | noop/base | **proto/base** | proto − base med ms | proto0/base |
|---|---|---|---|---|---|---|
| v1-entries-create | 5.07 / 9.68 | 1.020, 1.109 | 0.980, 1.135 | **1.194, 1.232** | +0.98 | 1.008, 1.031 |
| v1-entries-resend | 5.72 / 11.60 | 0.995, 0.908 | 0.947, 0.995 | 1.065, 1.300 | +0.37 | 0.962, 0.925 |
| v1-entries-query-delete-10 | 5.23 / 10.20 | 1.059, 1.078 | 1.036, 0.912 | **1.334, 1.201** | +1.75 | 1.001, 1.003 |
| v1-devicestatus-create | 5.14 / 9.57 | 0.998, 1.035 | 0.938, 1.004 | 0.962, 1.060 | −0.20 | 0.946, 1.130 |
| v1-treatments-create | 6.23 / 12.19 | 1.048, 1.046 | 1.056, 0.988 | **1.175**, 1.099 | +1.09 | 0.997, 1.003 |
| v1-treatments-put | 6.68 / 11.66 | 0.961, 1.051 | 0.983, 0.998 | **1.171, 1.397** | +1.14 | 1.071, 1.109 |
| v1-treatments-softdelete | 6.81 / 12.19 | 0.984, 1.132 | 0.962, 1.033 | **1.159, 1.233** | +1.09 | 1.002, 1.019 |
| v1-treatments-delete-id | 4.00 / 8.02 | 1.062, 1.067 | 1.072, 1.052 | **1.254, 1.160** | +1.02 | 1.027, 1.003 |
| v3-treatments-create | 6.66 / 12.17 | 1.003, 1.038 | 0.968, 1.037 | 1.006, 0.970 | +0.04 | 1.027, 0.982 |
| v3-treatments-resend | 8.54 / 15.01 | 1.055, 1.074 | 0.965, 1.019 | 1.076, 1.104 | +0.65 | 1.020, 1.053 |
| v3-treatments-patch | 7.53 / 14.52 | 1.011, 0.946 | 1.036, 0.968 | 1.075, 1.087 | +0.57 | 1.012, 0.962 |
| v3-treatments-put | 7.48 / 14.23 | 1.113, 0.967 | 1.092, 1.014 | 1.091, 1.106 | +0.68 | 1.076, 1.037 |
| v3-treatments-delete-permanent | 6.71 / 13.30 | 0.967, 0.890 | 1.005, 1.030 | 1.099, 1.119 | +0.67 | 0.935, 0.937 |
| ws-treatments-dbAdd | 6.31 / 13.80 | 0.986, 0.981 | 1.044, 0.931 | 1.008, 0.858 | +0.05 | 1.014, 0.987 |
| ws-treatments-dbUpdate | 5.04 / 9.79 | 1.125, 1.093 | 1.019, 1.068 | **1.231, 1.172** | +1.16 | 1.038, 1.046 |
| ws-treatments-dbRemove | 3.97 / 8.20 | 0.998, 0.925 | 1.004, 1.094 | **1.272, 1.244** | +1.08 | 1.020, 1.015 |
| v1-entries-backfill-1000 | 179.56 / 232.76 | 0.988, 0.997 | 1.004, 0.957 | **1.134**, 1.100 | +23.98 | 0.990, 1.013 |
| v1-treatments-backfill-1000 | 396.09 / 470.81 | 1.016, 1.047 | 1.000, 0.992 | **1.267, 1.257** | +105.61 | 1.009, 1.059 |

Reading the table:
- **Noise floor:** base2/base runs 0.961–1.125 (median) and 0.890–1.132 (p95).
- **No-op control:** noop/base runs 0.938–1.092 and 0.912–1.135, which is inside the floor, as
  it must be.
- **proto0** (prototype, no listener) runs 0.935–1.076 and 0.925–1.130, also inside the floor.
  With no subscriber, option 1 costs nothing measurable.
- **proto with a listener:**
  - The insert-only calls (`insertOne`/`insertMany`: v3 create, socket `dbAdd`, devicestatus) are
    inside the floor.
  - Every call that needs the identity read is about **+0.4 to +1.8 ms** at the median, one more
    localhost round trip. That is outside the floor (in **bold**) for 10 of the 13 such calls.
  - The v1 backfills are upserting `bulkWrite`s, so their read is a 1,000-way `$or`. They cost
    **+24 ms (+13%)** for entries and **+106 ms (+27%)** for treatments.
- Throughput is 1000 / mean per shape (`perSecond` in `results/latency.json`). It moves inversely
  with the latency above.

Caveat: a full `npm test` of the prototype (another mongod) ran during the first few minutes of
this run. Arms were interleaved, so all arms shared that load, and the noise floor includes it.

### (b) Payload bytes and the cost of naming records, in-process

The `write-step.js` boundary of each tree runs over a raw driver collection on the same mongod.
There are 20 repetitions per size (5 at 10,000), with arms and listen/quiet modes alternated.
`listen − quiet` on **base** is the control: the code is the same in both modes, so that column
is noise.

| N | driver call | base bytes | proto bytes | proto records | base listen−quiet ms | **proto listen−quiet ms** (quiet median) |
|---|---|---|---|---|---|---|
| 1 | insertMany | 150 | 262 | 1 | +0.06 | +0.48 (2.87) |
| 1 | bulkWrite upsert, fresh | 149 | 216 | 1 | +0.57 | +1.80 (3.07) |
| 1 | updateMany | 150 | 262 | 1 | +0.68 | +2.56 (2.04) |
| 1 | deleteMany | 150 | 261 | 1 | −0.03 | +2.15 (2.29) |
| 100 | insertMany | 152 | 10,454 | 100 | +0.20 | +0.22 (5.48) |
| 100 | bulkWrite upsert, fresh / re-sent | 151 | 5,663 | 100 | +1.56 / +0.03 | +3.28 / +3.75 (18.2 / 14.7) |
| 100 | updateMany | 152 | 10,454 | 100 | +0.45 | +1.75 (6.47) |
| 100 | deleteMany | 152 | 10,354 | 100 | +0.21 | +1.48 (6.24) |
| 1,000 | insertMany | 153 | 105,055 | 1,000 | +0.10 | −1.08 (15.67) |
| 1,000 | bulkWrite upsert, fresh / re-sent | 152 | 55,164 | 1,000 | −2.39 / −1.87 | **+38.8 / +39.5** (98.8 / 99.8) |
| 1,000 | updateMany | 153 | 105,055 | 1,000 | +0.30 | +2.42 (21.95) |
| 1,000 | deleteMany | 153 | 104,055 | 1,000 | −0.19 | +4.60 (14.94) |
| 10,000 | insertMany | 154 | 1,059,056 | 10,000 | −17.18 | +2.89 (97.79) |
| 10,000 | bulkWrite upsert, fresh / re-sent | 153 | 550,165 | 10,000 | +9.48 / +7.74 | **+370 / +401** (961 / 964) |
| 10,000 | updateMany | 154 | 1,059,056 | 10,000 | **+70.74** | +78.30 (151.97) — inside this row's noise |
| 10,000 | deleteMany | 154 | 1,049,056 | 10,000 | −6.51 | +37.61 (104.29) |

- **Bytes.** A counts-only event is about 150 B whatever the size of the call. Option 1 adds about
  **105 B per record with an `identifier`** and about **55 B per record without one**, so a
  1,000-record call is about 105 KB and a 10,000-record call about 1.06 MB, held in memory for
  every listener. The event is not serialized unless a listener does that.
- **Naming cost.**
  - Inserts: none.
  - Updates and deletes: a few ms up to 1,000 records, and +38 ms (+36%) for a deleteMany of
    10,000.
  - **Upserting bulkWrites: +39 ms on about 99 ms (+39%) at 1,000, and +370–400 ms on about
    960 ms (+40%) at 10,000.** That is the `$or` of every operation's filter.

Listener cost per event, measured on the events above (medians):

| N | JSON.stringify proto | apply to an `_id` index (Map) | cache.js removal by id (576 cached entries + N) |
|---|---|---|---|
| 1 | 0.001 ms | 0.0002 ms | 0.007 ms |
| 100 | 0.015 ms | 0.001–0.005 ms | 0.025 ms |
| 1,000 | 0.10–0.15 ms | 0.009–0.024 ms | 0.137 ms |
| 10,000 | 1.2–2.0 ms | 0.11–0.43 ms | 5.5 ms (O(ids × cache)) |

- **Counts-only events.** A counts-only event cannot be applied to an index. The base cache
  given a removal with no ids **flushes** (0 entries left), so the only option is a re-read.
  Re-reading the cache's 2-day window (576 entries) takes **median 2.29 ms (p95 3.80 ms)** on
  this mongod.
- **Option 1 with contents.** A consumer that needs the documents reads them by id
  (`_id $in`): 0.85 ms at 1, 1.00 ms at 100, 4.18 ms at 1,000, 38 ms at 10,000.
- **No production listener exists.** Nothing in `lib/` subscribes to `storage-write-committed`
  (`git grep` at `9668b179`); only tests do. The cache and ddata reload (`lib/server/cache.js`
  on `data-update`, `lib/server/bootevent.js` debounced `dataloader.update` on `data-received`)
  and the socket `dataUpdate` (`lib/server/websocket.js` on `data-processed`, delta from
  `calcdelta`) are all driven by the separate `data-update`/`data-received` events that each
  route emits. The listener figures above are therefore what those listeners **would** pay if
  driven from this event. They are not a change to them today.

### (c) Change-feed reconstruction, 5 calls per shape and arm

Ground truth is the MongoDB change stream of the arm's database. The window is bounded by start
and end sentinel writes: `startAtOperationTime` is inclusive of the seed write, so the stream
skips to the start sentinel first.

| shape (all 20, including query deletes of 100 and 1,000) | base: names exact | base: events needing a follow-up read | **proto: names exact** | proto: events needing a follow-up read |
|---|---|---|---|---|
| every shape | 0 / 5 (no records) | 5 / 5 | **5 / 5** | **0 / 5** |

Every shape is exact on proto (100 / 100 calls, 10,000 + 5,550 change-stream operations in the
bulk and query-delete shapes). On base every changing event needs a follow-up read, because
counts say how many records changed, never which.

Controls (`results/changefeed.log`):
- **BROKEN-drop-last** (option 1, but drops each event's last record) is reported wrong in
  **100 / 100** proto calls.
- **BROKEN-guess** (counts only, guesses that the newest `count` documents are the created ones)
  is reported wrong for every update, delete and resend shape. It is **right for the
  single-writer create shapes** (5 / 5 on most of them; 1 / 5 on socket `dbAdd`). A serial
  test of creates alone cannot tell a counts-and-guess consumer from a correct one.

### (d) Concurrent writers, 20 s per run, rounds in ABBA order

Writers:
- **Loop-like:** devicestatus + Temp Basal; re-sends every 5th treatment.
- **CGM bridge:** one entry per POST; every 3rd POST re-sends the last 3 entries.
- **Careportal:** v3 create, PATCH, then DELETE permanent.

There are k of each. Totals are summed over the two rounds:

| k | arm | requests | req/s (r0, r1) | median / p95 ms (r0) | change-stream ops | cross-attributed | records ≠ counts | missed | extra |
|---|---|---|---|---|---|---|---|---|---|
| 1 | base | 5,705 | 140.9, 143.6 | 6.51 / 12.16 | 6,159 | n/a (no records) | n/a | 6,159 unnamed | — |
| 1 | proto | 5,578 | 138.3, 139.7 | 6.97 / 12.82 | 6,026 | **0** | **0** | **0** | **0** |
| 2 | base | 11,648 | 289.4, 288.5 | 6.04 / 10.79 | 12,560 | n/a | n/a | 12,560 unnamed | — |
| 2 | proto | 11,412 | 283.9, 283.0 | 6.38 / 11.67 | 12,306 | **0** | **0** | **0** | **0** |
| 4 | base | 21,918 | 535.8, 545.6 | 6.68 / 13.21 | 23,690 | n/a | n/a | 23,690 unnamed | — |
| 4 | proto | 21,078 | 515.2, 517.4 | 7.37 / 15.24 | 22,786 | **0** | **0** | **0** | **0** |

- With interleaved writers whose filters do not overlap, option 1 named all **41,118** operations
  exactly, with no record attributed to another writer's request.
- Throughput was 2–5% lower than base (−4.5% on average at k = 4), and the median was +0.3–0.7 ms.
- Base vs base under concurrency was not run separately. The two base rounds differ by up to 1.8%.

**Pruner race** (`--pruner`, `results/concurrent-pruner.log`). One writer deletes every bridge
entry (`find[device]=bench-cgm`) every 200 ms while the bridges insert. This is the identity
read's read-then-write race, triggered on purpose.

| k | round | proto events with records ≠ counts | missed | extra | cross-attributed |
|---|---|---|---|---|---|
| 1 | 0 / 1 | 3 / 5 (of ~2,800) | 2 / 4 | 1 / 1 | 0 / 0 |
| 4 | 0 / 1 | 7 / 8 (of ~11,000) | 7 / 13 | 0 / 0 | 0 / 0 |

- Option 1 is **not exact under overlapping concurrent writes**. A record inserted between the
  read and the delete is deleted but not named ("missed"). A bridge re-send can also be named
  "modified" after the pruner deleted the record and the upsert created a new one ("extra").
- In every round the inexact events showed up as records ≠ counts. The lab did not check
  event by event that every inexact event is one of those flagged.

**Break-it control** (`--break swap-writer`, `results/concurrent-break.log`). One record is moved
from every 10th event onto the event before it. The check reports **277 cross-attributed events
and 560 records ≠ counts**, so the zero results above come from a check that can see a difference.

## Verdict (round 1: base vs uncapped pre-read)

- **With no subscriber, option 1 is free.** proto0 is inside the base-vs-base noise floor on all
  18 shapes, because the identity read is gated on a listener and nothing subscribes today.
- **With a subscriber:**
  - It is free for inserts (driver result).
  - It costs one extra round trip per update, replace, delete or upserting call: about
    +0.4–1.8 ms median on 4–8 ms requests (+7–33%) on localhost, and 2–5% of concurrent
    throughput.
  - **The expensive case is the v1 upload path.** v1 entries and treatments POSTs are upserting
    `bulkWrite`s, so a 1,000-record backfill pays a 1,000-way `$or` read: +24 ms (+13%) for
    entries, +106 ms (+27%) for treatments over HTTP; +39% in-process at 1,000 and 10,000.
- **What it buys:**
  - Single-writer reconstruction goes from 0 / 100 calls to 100 / 100 exact with no follow-up read.
  - The payload is about 55–105 B per record (about 1 MB at 10,000).
  - Acting on the event costs ≤ 0.5 ms at 10,000 records.
- **Not atomic.** Exactness is not guaranteed under overlapping concurrent filters, but `counts`
  exposes every inexact event the lab saw.
- **Recommendation for review.** The 27–40% bulk-upsert cost is the number to decide on. A
  cheaper variant was **not built**, per the lab's stop rule: name upserts from `upsertedIds` and
  read only the operations that did not upsert, after the write and only when `matchedCount > 0`.
  That would make a fresh backfill free. Its own exactness cost (a post-read misses records whose
  filter fields the update changed) is unmeasured.

## Not measured (round 1; see round 2 for what it added)

- Network latency. Everything ran on localhost. On a hosted MongoDB every identity read adds a
  network round trip, so the absolute +0.4–1.8 ms will grow with the RTT.
- MongoDB versions other than 8.0.29. A standalone `mongod` (only a replica set was used).
- Node versions other than 22.23.4.
- `deleteOne`, `updateOne` upserts and real-driver partial batch failures. Partial batches are
  covered only by the mock unit test.
- The reject-mode validated update path (`WRITE_VALIDATION=reject`).
- Client-visible socket `dataUpdate` latency, server memory, and event retention by listeners.
- A base-vs-base noise floor for the concurrent axis.
- The post-read variant above.
- An event-by-event proof that every inexact event under the race shows records ≠ counts.

## Round 2 (2026-10-27): post-write, capped and counts-only deletes

### Arms and anchors

All variants keep the listener gate and take `counts` from the driver.

| arm | tree | head | what it does |
|---|---|---|---|
| base | dev | `9668b179` | counts only |
| base2 | dev, second process | `9668b179` | noise floor |
| noop | base plus one comment line | `1d4a8753` | no-op control |
| pre | `proto/d-event-per-call` | `8a396715` | uncapped pre-read (round 1) |
| post | `proto/d-event-post-write` | `408c7d03` | inserts and upserts named from the result; updates and replacements read **after** the write, only when `matchedCount > 0` and `modifiedCount > 0`, and only for the operations that did not upsert; deletes keep a pre-read limited to the delete filters |
| postnodel | `proto/d-event-post-nodelete` | `70e2d218` | post, but deletes are counts only (no read and no deleted records) |
| capped | `proto/d-event-capped` | `8432ea66` | pre-read limited to 501; above 500 records the event has `collapsed: true` and no records; a call with more than 500 insert or upsert operations collapses without reading |

Environment:
- Node v22.23.4.
- `mongo:8.0.29` single-node replica set on 127.0.0.1:27601, `--ulimit nofile=64000:64000`.
- Every round-2 log starts and ends with `docker inspect`. They show `restarts=0` and the same
  `StartedAt` (2026-10-27T23:24:35Z) throughout. `results/round2/containers-final.log` holds the
  state at removal. All containers are removed.

**A failed run, not reported.** The first round-2 latency run used five arms and n = 200/100/10.
It crashed at about iteration 55 with `fetch failed: ECONNRESET` and wrote no results. The
likely cause is a reused keep-alive socket that the server had closed. The container stayed up
(`restarts=0`). The harness now counts a reset request as an error (status 599, never retried).
The runs below have 0 errors.

### Tests and controls for the new arms

| tree | `npm test` | new or changed tests | red control | break-it |
|---|---|---|---|---|
| post `408c7d03` | **4706 passing, 0 failing, 3 pending** | first identity test now expects the post-read filter; new: "reads updated records after the write, deleted records before it"; "reads nothing after a write that matched nothing, such as a fresh upsert batch" (includes matched-but-unmodified); "leaves a post-write mis-name visible: records disagree with counts" | on pre `8a396715`: 3 fail (the read happens before the write, the fresh batch reads); on base: 6 fail (`records` undefined) | counts rebuilt from records: the mis-name test fails |
| capped `8432ea66` | **4704 passing, 0 failing, 3 pending** | new: "collapses an event above 500 records to counts and collapsed: true" | on pre: fails at "more than 500 upserts collapse without a read" | — |
| postnodel `70e2d218` | **4706 passing, 0 failing, 3 pending** | delete expectations changed to counts only | — (comparison arm only) | — |

### (a) Latency, interleaved

**Single writes**, n = 200 per shape and per arm, 7 arms. The noise floor (base2/base) is
0.903–1.035 at the median and 0.872–1.252 at p95. The no-op control is 0.899–1.016 / 0.823–1.175,
inside it.

Ranges of arm/base median ratios, grouped by write kind (Δ = arm − base median):

| kind (shapes) | pre | post | postnodel | capped |
|---|---|---|---|---|
| insert (devicestatus, v3 create, socket dbAdd) | 0.913–1.007 | 0.914–1.003 | 0.929–1.022 | 0.953–1.003 |
| single upsert (v1 entries/treatments create) | **1.049–1.150** (+0.4–0.9 ms) | 0.949–0.992 (free) | 0.964–1.017 | **1.091–1.111** (+0.6–0.8 ms) |
| update/replace (v1 put, softdelete, resend; v3 resend, patch, put; socket dbUpdate; internal moves-out) | 0.978–**1.206** (up to +1.6 ms) | 0.959–**1.199** (up to +1.6 ms) | 1.011–**1.277** (up to +2.2 ms) | 0.983–**1.245** (up to +1.9 ms) |
| delete (v1 query delete 10, v1 delete id, v3 delete permanent, socket dbRemove) | **1.078–1.341** (+0.6–2.7 ms) | **1.119–1.426** (+0.7–3.3 ms) | 0.924–1.036 (free) | **1.079–1.414** (+0.6–3.2 ms) |

Per-shape numbers are in `results/round2/latency-singles.log`.

**Backfills**, one v1 POST each. n = 50 at 1,000 records and n = 8 at 10,000, 5 arms. A re-send
posts the same records again; every operation matches and is modified (the server stamps them).

| backfill | base median | base2 | pre | **post** | capped (collapsed) |
|---|---|---|---|---|---|
| entries fresh 1,000 | 180 ms | ×1.009 | ×1.121 (+22 ms) | **×1.054 (+10)** | ×1.026 (+5) |
| entries re-send 1,000 | 193 ms | ×1.000 | ×1.154 (+30) | **×1.147 (+28)** | ×0.987 |
| treatments fresh 1,000 | 394 ms | ×1.026 | ×1.283 (+112) | **×1.009 (+4)** | ×1.022 |
| treatments re-send 1,000 | 1,187 ms | ×1.000 | ×1.098 (+116) | **×1.093 (+111)** | ×0.980 |
| entries fresh 10,000 | 1,653 ms | ×0.971 | ×1.150 (+249) | **×0.958** | ×1.003 |
| entries re-send 10,000 | 1,914 ms | ×1.022 | ×1.165 (+316) | **×1.185 (+354)** | ×0.971 |
| treatments fresh 10,000 | 3,772 ms | ×1.019 | ×1.269 (+1,016) | **×0.995** | ×0.970 |
| treatments re-send 10,000 | 11,385 ms | ×1.029 (+325) | ×1.140 (+1,591) | **×1.119 (+1,350)** | ×1.000 |

- Noise floor: base2 is 0.971–1.029 at the median. At 10,000 it moved up to ±325 ms, with n = 8.
- **post** is free on fresh backfills. On a full re-send it costs as much as the pre-read:
  +9–19%, +111 ms at 1,000 treatments and +1.35 s at 10,000.
- **capped** is free on every backfill over 500 records, because it collapses without reading.
  Those events name no records.

### (b) Naming cost and payload, in-process

20 repetitions (5 at 10,000). The column is listen − quiet at the median. Base's own
listen − quiet is the control: it reached −59 to +25 ms at 10,000, so smaller differences at
that size are noise.

| N | call | pre | post | postnodel | capped |
|---|---|---|---|---|---|
| 1,000 | bulkWrite upsert, fresh | +37.9 ms | −0.4 | −3.7 | −0.3 (collapsed, no read) |
| 1,000 | bulkWrite upsert, re-send | +33.2 | +48.0 | +47.9 | −1.5 (collapsed) |
| 1,000 | deleteMany | +4.1 | +4.8 | −1.1 (counts only) | +3.9 (reads 501, then collapses) |
| 10,000 | bulkWrite upsert, fresh | +464 | −35 | −116 | −48 (collapsed) |
| 10,000 | bulkWrite upsert, re-send | +467 | +499 | +457 | +5 (collapsed) |
| 10,000 | deleteMany | +26.6 | +36.4 | −1.8 | −0.6 (collapsed) |
| 10,000 | updateMany | +39.8 | −14.5 | −11.7 | −32.5 — inside this row's base noise (−57.5) |

- **Bytes.** Unchanged from round 1: about 105 B per record with an `identifier`, about 55 B
  without. A collapsed event is 166–171 B, and a counts-only delete event 163–167 B.
- Details are in `results/round2/payload.log`.

### Deletes: named by a pre-read limited to deletes (post) vs counts only (postnodel)

| | post | postnodel |
|---|---|---|
| latency, 4 single delete shapes | ×1.119–1.426 (+0.7–3.3 ms) | ×0.924–1.036 (inside the floor) |
| naming cost, deleteMany of 1,000 / 10,000 | +4.8 ms / +36.4 ms | none |
| change-feed exactness, 6 delete shapes (10 to 1,000 records) | **30 / 30 exact**, no follow-up | **0 / 30**: every delete event needs a follow-up read, and every one is flagged (records ≠ counts) |
| pruner race (d), records ≠ counts per round | 7, 7 (k = 1); 37, 28 (k = 4) | 464, 455; 1,129, 1,098 (every pruner delete) |

### (c) Change-feed exactness against the change stream

5 calls per shape (2 at 10,000). The shapes are all 17 singles, including the new
`internal-update-moves-out-10`, plus the query deletes of 100 and 1,000 and the 8 backfills.

- **`internal-update-moves-out-10`** is an `updateMany` whose `$set` changes its own filter
  field (`bench`). It goes through the write-step boundary in the server process. No HTTP route
  was found that sends such an update.

| arm | calls exact | where it is not exact | wrong and unflagged |
|---|---|---|---|
| pre | **all** | — | **0** |
| post | all but 5 | `internal-update-moves-out-10`: 0 / 5, all 10 records missed; flagged on every call | **0** |
| postnodel | all but 35 | moves-out (5) and every delete shape (30); all flagged | **0** |
| capped | all but 33 | every event over 500 records (1,000 and 10,000 backfills, query delete 1,000) is `collapsed`; all need a follow-up | **0** |

Controls:
- **BROKEN-drop-last** is wrong and unflagged on every call of every arm.
- **BROKEN-ignore-counts** reads names and ignores counts. It is wrong and unflagged exactly
  where the post variants mis-name (moves-out, and deletes on postnodel). The check sees that
  difference.
- **BROKEN-guess** is again right only on single-writer creates.

### Mis-naming test (`misname.js`, in-process, change stream as truth, 5 per case)

A concurrent writer is simulated deterministically by wrapping the driver call.

| case | pre | post | postnodel | capped |
|---|---|---|---|---|
| plain update / plain delete (controls) | exact / exact | exact / exact | exact / **missed 25** (counts only) | exact / exact |
| update moves records out of its filter | exact | **missed 25** | **missed 25** | exact |
| matched but unmodified (2 of 5 already hold the value) | extra 10 | extra 10 | extra 10 | extra 10 |
| concurrent insert just after the update | exact | **extra 5** | **extra 5** | exact |
| concurrent delete of an updated record just after the update | exact | **missed 5** | **missed 5** | exact |
| concurrent insert just before the delete | missed 5 | missed 5 | missed 30 | missed 5 |
| validated (reject-mode) Temporary Target update | exact | exact | exact | exact |
| **inexact and unflagged** (all cases) | **0** | **0** | **0** | **0** |

- Every inexact event in every arm had records ≠ counts.
- **Break-it.** `--break counts-from-records` rebuilds counts from the records. The check then
  reports **75** inexact-and-unflagged events (`results/round2/misname-break.log`).
- **Exactly which records a post-read mis-names:**
  - records the update moved out of its own filter (missed)
  - records a concurrent writer inserted or changed into the filter before the read (extra)
  - updated records a concurrent writer deleted before the read (missed)
  - matched records the update left unchanged (extra, as with the pre-read)
- **What it does not mis-name.** The reject-mode conditional update re-reads the original
  filter, not its snapshot filter, so it stays exact.

### (d) Concurrent writers: 3k uploaders, k = 1, 2, 4, 20 s, two rounds, arm order reversed per round

**Noise floor for (d) (new).** It comes from base, base2 and noop, which all emit the same
counts-only payload. Across rounds they span:
- 131.6–143.7 req/s at k = 1
- 239.0–288.1 req/s at k = 2
- 472.6–527.3 req/s at k = 4

That is up to 17% between identical arms. The naming arms fall inside it: pre 501.8–505.5,
post 500.0–505.6 and capped 503.2–512.1 req/s at k = 4.

**Attribution.** With no overlapping filters, every naming arm named every change-stream
operation, with **0** cross-attributed, **0** records ≠ counts, **0** missed and **0** extra:
- pre: 40,681
- post: 40,847
- capped: 40,608

No capped event collapsed, because these calls are small.

**Pruner race** (k = 1, 4; base, base2, pre, post, postnodel, capped):

| arm | records ≠ counts (k = 1 r0, r1; k = 4 r0, r1) | missed | extra | cross-attributed |
|---|---|---|---|---|
| pre | 2, 1; 14, 7 | 1, 1; 20, 10 | 1, 0; 1, 0 | 0 |
| **post** | **7, 7; 37, 28** | **11, 14; 70, 61** | 0 | 0 |
| postnodel | 464, 455; 1,129, 1,098 | 815, 799; 2,633, 2,572 | 0 | 0 |
| capped | 1, 0; 10, 13 | 1, 0; 12, 17 | 0 | 0 |

The post-read has a wider race window than the pre-read. After a bridge re-send matches its
records, the pruner can delete them before the read.

**Break-it** (`--break swap-writer`):
- post: 266 cross-attributed, 532 records ≠ counts
- capped: 253 cross-attributed, 512 records ≠ counts

### Comparison of all arms

| axis | pre (uncapped) | post-write | post, counts-only deletes | capped at 500 |
|---|---|---|---|---|
| single inserts | free | free | free | free |
| single upsert | +0.4–0.9 ms | **free** | free | +0.6–0.8 ms |
| single update/replace | up to +1.6 ms | up to +1.6 ms | up to +2.2 ms | up to +1.9 ms |
| single delete | +0.6–2.7 ms | +0.7–3.3 ms | **free** | +0.6–3.2 ms |
| fresh backfill 1,000 / 10,000 | +12–28% / +15–27% | **free** | free | free, collapsed |
| re-send backfill 1,000 / 10,000 | +10–15% / +14–17% | +9–15% / +12–19% | same as post | free, collapsed |
| payload per record | 55–105 B | 55–105 B | 55–105 B (deletes 0) | 55–105 B up to 500; then 170 B |
| change-feed exact (single writer) | all shapes | all except filter-changing update | all except filter-changing update and deletes | all except calls over 500 |
| concurrent throughput | inside the (d) floor | inside the floor | not run without the pruner | inside the floor |
| pruner race, inexact events per round | 1–14 | 7–37 | 455–1,129 | 0–13 |
| inexact and unflagged | 0 | 0 | 0 | 0 |

### Round 2 verdict

- **The post-write variant is not cheap overall.**
  - It is free where the pre-read was most expensive: fresh uploads, single (×0.949–0.992) and
    bulk (treatments 1,000 +112 ms → +4 ms).
  - A full re-send pays the same read: +9–19%, up to +1.35 s on a 10,000-treatment re-send.
  - Deletes still need their pre-read: ×1.12–1.43 on single deletes.
  - It mis-names updates that move records out of their own filter, which the pre-read names
    correctly.
  - Under the pruner race it was inexact two to four times as often as the pre-read.
  - Every mis-name was flagged by records ≠ counts.
- **Counts-only deletes** remove the delete cost entirely. But every delete event then needs a
  follow-up read, so a change feed cannot rebuild deletions from the event alone.
- **The capped pre-read is the cheapest arm on bulk writes.** It is free on every backfill over
  500 records. Below the cap it costs the same as the pre-read, and it keeps the pre-read's
  exactness. Its price: events over 500 records (the 1,000- and 10,000-record backfills) name
  nothing and say so with `collapsed: true`. That is the case where a listener's follow-up read
  is most expensive.
- **No arm adds a measurable throughput cost** to the concurrent uploaders. Base-vs-base varies
  by up to 17% there.
- **PR-readiness.** The post-write head was **not** made PR-ready (not squashed onto
  `9668b179` and not merged with `official/dev` `7abe1cf6`), because by these numbers it is not
  cheap.

### Not measured in round 2

- Network latency: localhost only, so every extra read is one localhost round trip.
- MongoDB versions other than 8.0.29.
- Caps other than 500.
- A post-read issued asynchronously after the reply.
- An HTTP route that sends a filter-changing update (none was found; the shape is internal).
- postnodel under the concurrent run without the pruner.
- An event-by-event proof under the pruner race that every inexact event is flagged. The
  in-process mis-naming test does prove it for its cases.
- Memory and client-visible socket latency.

## Round 3 (2026-10-29): since-watermark

### The arm and its two uses

Ben proposed this arm. After a write, the arm reads the collection back for every document with
`srvModified` after a **watermark**: the last `srvModified` the process issued before the write,
less a small overlap. The records are deduplicated by `_id`. Two uses judge the result differently:

- **(a) Cache catch-up.** A cache refreshes after a query-based write instead of flushing. Only
  **misses** count: records this write changed that the read did not return. Records from other
  writers do no harm there. Load counts too: queries, bytes and latency.
- **(b) Per-write event.** The event names "this write's records". Records from other writers
  are then errors, counted as **cross-attribution** (extra).

Every table below gives both, as "missed" (both uses) and "extra" (event only).

| arm | tree | head | what it does |
|---|---|---|---|
| since | `proto/d-event-since-watermark` | `978aa282` (on post `408c7d03`) | inserts and upserts are named from the result. Updates and replacements: one read after the write, only when `matchedCount > 0` and `modifiedCount > 0`, of `{srvModified: {$gt: watermark − 5}}` projected to `_id` and `identifier`, deduplicated by `_id` against the result's records. Deletes keep post's pre-read limited to the delete filters |
| since0 | same tree | `978aa282` | overlap 0 (`CEB_SINCE_since0=overlap=0`) |
| late0, late5 | same tree | `978aa282` | **break-it control**: the watermark one write late (the call's last stamp instead of its first stamp minus one), overlap 0 and 5 |

- **The watermark.** It is the smallest `srvModified` the call's operations carry, minus one. That
  is the last value `lib/server/srv-dates.js` issued before the call's first stamp. `write-step.js`
  runs after the route has stamped, so it reads the watermark from the stamps. A call with no stamp
  falls back to `srvDates.last()` (a new export) at the boundary.
- **No upper bound and no filter.** The read returns everything any writer stamped after the
  watermark. The table in (d) shows what that costs the event use.
- **`npm test`** on `978aa282`: **4709 passing, 0 failing, 3 pending** (MongoDB 8.0.29, Node v22.23.4).
  - New unit tests: names records an update moved out of its own filter, by `srvModified`; names each record once when the read also returns an upserted record; leaves a since-read mis-name visible (records ≠ counts); reads from the call's last stamp when the watermark is late.
  - The post-write test that pinned the moves-out miss was replaced, and the post-read filter expectations now expect the `srvModified` filter.
  - **Red control:** the since test file on post `408c7d03` has 5 failing tests.
  - **Break-it:** removing the `_id` dedupe makes 1 test fail.

### Facts behind the arm (checked at base `9668b179`)

| claim | how checked | result |
|---|---|---|
| every server write path stamps `srvModified` (since `718efddc`, 15.0.9) | `718efddc` is an ancestor of base; every driver write call in `lib/` read by hand | v1 bulk/replace, socket update/merge/add/profile, v3 insert/replace/patch/soft delete all stamp. Activity and authorization storage do not, and neither is served by v3. **Read-derived, not reproduced** |
| `srv-dates.js` issues increasing values | read `next()` | strictly increasing in one process; it runs ahead of the clock by 1 ms per document in a large batch |
| `srvModified` is indexed | `MongoCollection.indexedFields` at `lib/api3/storage/mongoCollection/index.js` | yes. The in-process harnesses create the same index |
| single-tenant Nightscout has no unstamped writers | from Ben; not tested | — |

- **Harness change for every arm.** All in-process writers now stamp through the arm tree's own
  `srv-dates`: the `internal-update-moves-out-10` shape in `server.js`, every write in `misname.js`
  and `payload.js`, and the concurrent writer that `misname.js` simulates. Without the stamps the
  since-read would see nothing those writers wrote.
- **Side effect.** "Matched but unmodified" no longer happens: every matched record gets a new
  `srvModified`. All arms are exact on that case now (round 2: extra 10).
- **An edge, read-derived and not measured.** A socket `dbUpdate` that is a merge patch writes once per
  target with one shared stamp. The since-read for target k then also returns targets 1 … k−1:
  harmless to a cache, extra for an event.

Environment:
- Node v22.23.4; `mongo:8.0.29` single-node replica set on 127.0.0.1:27601, `--ulimit nofile=64000:64000`, no `--rm`.
- Every log starts and ends with `docker inspect`. They show `restarts=0` and the same `StartedAt` (2026-10-29T20:11:32Z) throughout.

**Two failed steps, not reported:**
- **Reads from the profiler.** The first reads run counted identity reads with the database
  profiler. It reported **0** identity reads on every 1,000- and 10,000-record re-send, for every
  arm. The likely cause is that the profiler's 1 MB capped collection drops the read's entry behind
  the backfill's per-operation entries. The table below comes from `readtap.js`, which counts in
  the arm's process. A run on a separate mongod confirmed it: 1 query and 1,000 documents where the
  profiler showed 0. Kept as `results/round3/reads-profiler-only.*`.
- **Latency run.** The first latency run interleaved singles with the backfills at about 80 s per
  iteration. A v3 seed POST returned no JSON and crashed it after iteration 25. Its six arm servers
  were orphaned and held the log pipe open for about four hours. Kept as
  `results/round3/latency-crashed.log`. Singles and backfills then ran separately, as in round 2.
  `bench.js` now counts a failed seed as an error of that arm instead of crashing; there were none.

### Reads per write (`reads.js` + `readtap.js`, 10 calls per shape, 2 at 10,000)

Identity reads per write: queries / documents / BSON bytes returned. Base makes none.

| shape group | pre | post | capped | since |
|---|---|---|---|---|
| inserts (devicestatus, v3 create) | 0 | 0 | 0 | 0 |
| single upsert (v1 create) | 1 / 0 / 0 | 0 | 1 / 0 / 0 | 0 |
| single update/replace/delete (v1, v3, socket) | 1 / 1 / 22–75 B (v1 PUT and soft delete: 2 queries) | same | same | same |
| moves-out, 10 | 1 / 10 / 220 B | 1 / **0** / 0 | 1 / 10 / 220 B | 1 / 10 / 220 B |
| query delete 100 / 1,000 | 1 / 100 / 2.2 KB; 1 / 1,000 / 22 KB | same | 1 / 100; 1 / **501** / 11 KB | same as pre |
| backfill fresh 1,000 / 10,000 | 1 / 0 / 0 | 0 | 0 (collapsed) | 0 |
| backfill re-send 1,000 / 10,000 | 1 / 1,000 / 22 KB; 1 / 10,000 / 220 KB | same | 0 (collapsed) | same |

- **v1 PUT and soft delete make 2 identity queries in every naming arm.** The route also deletes the
  record's string-`_id` twin, and that delete pays its pre-read even when it matches nothing.
- **Single writer, same reads.** Since reads the same documents and bytes as post on every shape;
  the difference is the query shape.
- **More documents under concurrency.** With concurrent writers the since-read also returns other
  writers' records (the extras in (d)). Those reads were not counted per write.
- Other reads (the route's own, the loader's) came to 1–294 per write. They varied by up to about 1.5 per write between arms and calls, with no pattern by arm (`results/round3/reads.log`).

### (a) Latency

**Singles**, n = 200, 6 arms, 0 errors, 5,801 events at every arm. Noise floor: base2/base
0.965–1.026 (median); no-op 0.957–1.011.

| kind (shapes) | pre | post | since |
|---|---|---|---|
| insert (devicestatus, v3 create, socket dbAdd) | 0.967–0.979 | 0.957–0.999 | 0.974–1.004 |
| single upsert (v1 entries/treatments create) | **1.155–1.185** | 0.991–1.002 | 1.003–1.006 |
| update/replace (v1 put, softdelete, resend; v3 resend, patch, put; socket dbUpdate) | **1.079–1.248** | **1.065–1.234** | **1.088–1.229** (+1–2 ms) |
| filter-changing update (internal moves-out, 10) | **1.273** | **1.312** | **1.187** |
| delete (v1 query delete 10, delete id; v3 delete permanent; socket dbRemove) | **1.173–1.407** | **1.154–1.392** | **1.156–1.437** |

**Backfills**, one v1 POST each, n = 50 at 1,000 and n = 8 at 10,000, 5 arms, 0 errors.

| backfill | base median | base2 | pre | post | **since** |
|---|---|---|---|---|---|
| entries fresh 1,000 | 160 ms | ×1.002 | ×1.162 | ×1.008 | **×1.018** |
| entries re-send 1,000 | 175 ms | ×1.011 | ×1.181 | ×1.164 | **×1.027** |
| treatments fresh 1,000 | 353 ms | ×1.009 | ×1.280 | ×1.008 | **×1.014** |
| treatments re-send 1,000 | 1,176 ms | ×0.990 | ×1.118 | ×1.095 | **×1.011** |
| entries fresh 10,000 | 1,531 ms | ×1.017 | ×1.181 | ×1.024 | **×1.054** |
| entries re-send 10,000 | 1,806 ms | ×0.960 | ×1.217 | ×1.162 | **×0.985** |
| treatments fresh 10,000 | 3,575 ms | ×0.980 | ×1.270 | ×1.009 | **×0.986** |
| treatments re-send 10,000 | 12,118 ms | ×0.982 | ×1.057 | ×1.125 | **×0.973** |

Since is inside the floor (0.960–1.017) or close to it on every backfill, **re-sends included**.
Pre and post pay for their 1,000-way `$or` there.

### (b) Naming cost, in-process (listen − quiet, median ms)

| N | call | pre | post | since |
|---|---|---|---|---|
| 1,000 | bulkWrite upsert, fresh | +36.5 | +0.2 | +2.2 |
| 1,000 | bulkWrite upsert, re-send | +34.8 | +39.8 | **+3.7** |
| 1,000 | updateMany | +3.2 | +3.8 | +5.0 |
| 1,000 | deleteMany | +3.3 | +3.5 | +4.0 |
| 10,000 | bulkWrite upsert, fresh | +352 | −47 | −12 |
| 10,000 | bulkWrite upsert, re-send | +413 | +372 | **+8** |
| 10,000 | deleteMany | +33.1 | +32.9 | +35.6 |

- Base's own listen − quiet is the control. It reached −39 to +24 ms at 10,000 records.
- **Bytes:** unchanged from rounds 1–2, about 55–105 B per record.
- The one large difference is the re-sent upsert batch. There, the since-read is one indexed
  range read, and pre and post read an `$or` of 1,000 or 10,000 filters. The mechanism is
  inferred from the query shapes; the bench does not isolate it.

### (c) Change-feed exactness against the change stream (27 shapes × 5 calls)

| arm | calls exact | missed (both uses) | extra (event use) | inexact and unflagged |
|---|---|---|---|---|
| pre | 135 / 135 | 0 | 0 | 0 |
| post | 130 / 135 | 50 (moves-out, every call) | 0 | 0 |
| **since** | **135 / 135** | **0** | **0** | **0** |
| since0 | 135 / 135 | 0 | 0 | 0 |
| late0 (break-it) | **71 / 135**: 13 shapes inexact | 110,089 | 0 | 0 (all 64 flagged) |
| late5 | 115 / 135: only the four re-send backfills | 109,900 (the overlap recovers 5 per call) | 0 | 0 (all 20 flagged) |

- **Break-it works.** A watermark one write late misses records, and the check sees it.
- **The overlap hides a late watermark only for small calls.** That includes an `updateMany`,
  whose records share one stamp. Calls that span more stamps than the overlap still fail.
- BROKEN-drop-last is wrong and unflagged on every call of every arm (135 / 135), as in round 2.

**Mis-naming test** (`misname.js`, 5 per case; truth excludes the simulated concurrent writer):

| case | pre | post | since | since0 | late0 |
|---|---|---|---|---|---|
| plain update / plain delete | exact / exact | exact / exact | exact / exact | exact / exact | **missed 25** / exact |
| update moves records out of its filter | exact | missed 25 | **exact** | exact | missed 25 |
| matched but unmodified | exact | exact | exact | exact | missed 25 |
| concurrent insert just after the update | exact | extra 5 | **extra 5** | extra 5 | missed 25, extra 5 |
| concurrent delete of an updated record just after the update | exact | missed 5 | missed 5 | missed 5 | missed 25 |
| concurrent insert just before the delete | missed 5 | missed 5 | missed 5 | missed 5 | missed 5 |
| validated (reject-mode) Temporary Target update | exact | exact | exact | exact | missed 5 |
| **inexact and unflagged** | **0** | **0** | **0** | **0** | **0** |

**Break-it** (`--break counts-from-records`, since): the check reports **15** inexact-and-unflagged events (the three race cases × 5), so the 0 above comes from a check that can see a difference.

### (d) Concurrent writers, 3k uploaders, 20 s, two rounds, arm order reversed per round

**Without the pruner:**

| k | arm | req/s (r0, r1) | missed (both uses) | never named | cross-attributed events (event use) | extra records (event use) |
|---|---|---|---|---|---|---|
| 1 | base / base2 | 133.3, 123.4 / 134.1, 123.5 | all (counts only) | all | n/a | n/a |
| 1 | pre / post | 130.1, 116.7 / 132.1, 115.5 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 1 | **since** | 130.8, 120.9 | **0** | **0** | **138, 136** | **140, 136** |
| 2 | base / base2 | 251.0, 249.5 / 237.4, 277.8 | all | all | n/a | n/a |
| 2 | pre / post | 233.4, 282.1 / 251.8, 294.9 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 2 | **since** | 283.9, 302.8 | **0** | **0** | **874, 905** | **1,353, 1,473** |
| 4 | base / base2 | 420.8, 536.4 / 423.2, 527.5 | all | all | n/a | n/a |
| 4 | pre / post | 402.7, 504.2 / 490.2, 510.0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 4 | **since** | 512.3, 497.2 | **0** | **0** | **1,946, 1,844** | **5,845, 5,082** |

- Every cross-attributed event also had records ≠ counts.
- Base-vs-base throughput differs by up to 27% between rounds (k = 4: 420.8 vs 536.4). Every
  naming arm is inside that spread.

**Pruner race** (one writer deletes every bridge entry every 200 ms), k = 1 (r0, r1); k = 4 (r0, r1):

| arm | missed (both uses) | records ≠ counts | cross-attributed events | extra records |
|---|---|---|---|---|
| pre | 2, 3; 14, 10 | 2, 4; 10, 6 | 0 | 0, 2; 0, 0 |
| post | 9, 13; 86, 68 | 5, 5; 39, 32 | 0 | 0 |
| **since** | **3, 9; 54, 45** | 154, 170; 1,647, 1,556 | **151, 166; 1,618, 1,532** | **152, 168; 4,709, 4,597** |
| base / base2 | 2,926–11,218 (counts only) | — | — | — |

The since misses come from the delete pre-read's race and from updated records the pruner deleted
before the read. They fall between pre and post.

**Break-it** (`--break swap-writer`, since, k = 2, 10 s): 539 cross-attributed, 744 records ≠ counts.
**This control is not informative for since.** The arm already cross-attributes on its own, so
the break cannot be told apart from its baseline. The evidence that the check sees
cross-attribution is the comparison inside one harness and run: pre and post report 0, since
reports 136–1,946.

### Comparison (round 3 measurements; pre and post re-measured alongside)

| axis | pre (uncapped) | post-write | **since-watermark** |
|---|---|---|---|
| single inserts / upserts | free / +16–19% | free / free | free / free |
| single update/replace | +8–25% | +7–23% | +9–23% (+1–2 ms) |
| single delete | +17–41% | +15–39% | +16–44% |
| backfill fresh 1,000 / 10,000 | +16–28% | free | free |
| backfill re-send 1,000 / 10,000 | +6–22% | +9–16% | **free** |
| filter-changing update | exact | misses all | **exact** |
| (a) cache: missed, single writer / concurrent / pruner race | 0 / 0 / 2–14 | 50 (moves-out) / 0 / 9–86 | **0 / 0 / 3–54** |
| (b) event: cross-attributed events, concurrent / pruner race | 0 / 0 | 0 / 0 | **136–1,946 / 151–1,618 per round** |
| inexact and unflagged (single writer, mis-naming test) | 0 | 0 | 0 |

### Findings (D-EVENT deferred; research continuing)

- **As a cache catch-up (use a):**
  - Since-watermark missed nothing a single writer changed. That includes the filter-changing
    update, which the post-write read misses.
  - With concurrent writers and no pruner it missed nothing either.
  - Under the pruner race it missed 3–54 records per round, between pre (2–14) and post (9–86).
  - Its read is one indexed range read, so it costs nothing measurable on backfills of 1,000 and
    10,000 records, re-sends included. The two `$or` arms pay +6–28% there.
  - It cannot see hard deletes. Deletes keep a pre-read, and that read sets the delete latency
    (+16–44% on single deletes, as for pre and post).
- **As a per-write event (use b):**
  - With one writer it is exact.
  - With concurrent writers it attributes other writers' records to an event: 136–1,946
    cross-attributed events per 20 s round, up to 5,845 extra records at k = 4. Pre and post
    attribute none.
  - Every such event was flagged by records ≠ counts.
- **The watermark is the safety-critical part.** One write late with overlap 0, it misses every
  record of 13 shapes; every one of those events is flagged. The 5 ms overlap hides a late
  watermark only for calls that span fewer stamps than the overlap.
- **Unmeasured:**
  - a read with an upper bound (`srvModified ≤` the last value issued after the write), which
    would cut cross-attribution from later writes;
  - multi-process writers (one `srv-dates` clock per process);
  - network latency;
  - MongoDB versions other than 8.0.29;
  - the socket merge-patch edge above.

## Files

| file | role |
|---|---|
| `server.js` | one tree booted as the server, with `none`/`count`/`capture` listeners and IPC |
| `lib.js` | arm spawning, HTTP and socket helpers, the 16 shapes, the bulk and query-delete shapes |
| `inventory.js` | driver calls per shape |
| `bench.js` | axis (a) |
| `payload.js` | axis (b) |
| `changefeed.js` | axis (c) |
| `concurrent.js` | axis (d), with `--pruner` and `--break swap-writer` |
| `misname.js` | round 2: which records each variant mis-names, with `--break counts-from-records` |
| `reads.js`, `readtap.js` | round 3: identity reads per write (queries, documents, bytes), counted in each arm's process; the database profiler for context |
| `run.sh` | up / all / round2 / down (the round-2 runs were driven by the same commands, with the arms listed in the round-2 section) |
| `results/` | round 1: `*.log` (tables, `docker inspect` state) and `*.json` (raw); round 2: `results/round2/`; round 3: `results/round3/` |

An earlier payload run attached the listener twice in some repetitions (a harness bug: modes
were added without removing the previous listener). It was discarded and rerun after the fix.
Only the rerun is reported.
