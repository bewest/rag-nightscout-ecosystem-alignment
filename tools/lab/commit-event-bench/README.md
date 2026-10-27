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

## Verdict

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

## Not measured

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
| `run.sh` | up / all / down |
| `results/` | `*.log` (tables, `docker inspect` state) and `*.json` (raw) for every axis above |

An earlier payload run attached the listener twice in some repetitions (a harness bug: modes
were added without removing the previous listener). It was discarded and rerun after the fix.
Only the rerun is reported.
