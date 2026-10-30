# cache-catchup lab

Some writes don't name the records they change: a v1 delete by query, or an update by filter.
After one of these, can the server's in-memory cache (`lib/server/cache.js`) be brought back in
line without dropping and reloading the whole cache? And what does each way of doing it cost?
This lab measures three answers against dev `991b0654`:

| arm | how the cache catches up | tree |
|---|---|---|
| `dev` | as dev does today: drop the type's cache; the data loader reloads it | dev `991b0654`, unmodified (control) |
| `flush` | the prototype in flush mode, which should behave exactly like `dev` | `proto/cache-catchup` `5f8e95bf`, `CACHE_CATCHUP=flush` |
| `ids` | a v1 delete by query reads the `_id`s it is about to delete, and the cache removal names them; an update by filter still flushes | `CACHE_CATCHUP=ids` |
| `wm5` | as `ids` for deletes; an update by filter is caught up by reading `srvModified > watermark − 5 ms`, where the watermark is the largest `srvModified` the cache has merged for that type | `CACHE_CATCHUP=watermark,CACHE_CATCHUP_OVERLAP_MS=5` |
| `wm1000` | as `wm5` with a 1,000 ms overlap | `CACHE_CATCHUP_OVERLAP_MS=1000` |
| `idsbreak` | break-it control: `ids` with the last deleted id left unnamed | `CACHE_CATCHUP=ids,CACHE_CATCHUP_BREAK=drop-last` |

> Contributor-facing. Synthetic data only: the lab writes its own records into its own databases
> and must never be pointed at a real site.

## Status

This is research for **Q9** of the next-gen plan: is "the cache needs it" a reason to name records
in the write event (**D-EVENT**)? D-EVENT was deferred on 2026-10-27; research continues. This lab
reports findings; it does not choose an option.

**Scope: one server process.** In single-tenant Nightscout, clients such as xDrip+, uploaders and
AID controllers all write through the one server's REST and socket APIs. Several writers in
*separate server processes* sharing one database don't arise there, so they are not measured. All
writes through one process take their `srvModified` from one `srv-dates` clock. Check this
precondition again before `serve` roles share a database.

The race scenario (inserts that match a delete's filter, sent while the delete runs) is a
stress test. It isn't typical use.

## Results (2026-10-29)

Node 22.23.4, MongoDB 8.0.29 standalone (container `cache-lab-27621`, `nofile=64000`). Ten reps per
scenario and arm, with arms interleaved. Two cache sizes:

- **realistic**: 576 entries, 75 treatments, 288 devicestatus (about 2 KB each), the size of a
  default cache.
- **heavy**: five times that.

Every arm's seed is checked by count before it runs. Full tables and per-record detail are in
`results/{realistic,heavy}.log`, and the summaries are in `results/*.json`.

Columns: **consistent after** is the time from the write's response until the cache equals the
database over the lab's records, as a median / p95. The number in brackets counts reps that weren't
consistent within the 8 s timeout. **missing**, **ghost** and **stale** are summed over the reps
that never became consistent:

- *missing*: in the database, not in the cache
- *ghost*: in the cache, gone from the database
- *stale*: in both, with a different `srvModified`

**Reads** counts every driver `find` in the arm's process, from the write until settle
(`readtap.js`, client-side; the profiler loses reads in bulk calls).

### Q1: name the ids read before a delete, instead of flushing?

v1 delete by query of 10 records (`DELETE /api/v1/<type>/?find[bench]=…`):

| size | type | arm | consistent after (never) | missing / ghost | reads: queries / docs / KB |
|---|---|---|---|---|---|
| realistic | entries | dev | 94 / 251 ms (0) | 0 / 0 | 13 / 886 / 216.7 |
| realistic | entries | ids | 33 / 42 ms (0) | 0 / 0 | 14 / 10 / 0.2 |
| realistic | treatments | dev | 93 / 126 ms (0) | 0 / 0 | 13 / 125 / 27.0 |
| realistic | treatments | ids | 27 / 39 ms (0) | 0 / 0 | 14 / 10 / 0.2 |
| realistic | devicestatus | dev | 2,027 ms in the one rep that settled (9) | 2,304 / 0 | 0 / 0 / 0.0 |
| realistic | devicestatus | ids | 24 / 36 ms (0) | 0 / 0 | 1 / 10 / 0.2 |
| heavy | entries | dev | 327 / 528 ms (0) | 0 / 0 | 13 / 3,210 / 764.1 |
| heavy | entries | ids | 92 / 169 ms (0) | 0 / 0 | 14 / 10 / 0.2 |
| heavy | devicestatus | dev | — (10) | 14,400 / 0 | 0 / 0 / 0.0 |
| heavy | devicestatus | ids | 56 / 94 ms (0) | 0 / 0 | 1 / 10 / 0.2 |

- **Cost.** Naming the ids costs one extra query of 10 `_id`s (0.2 KB) instead of reloading the
  type's whole cache. That reload is 217 KB for realistic entries and 764 KB for heavy. The wm5
  and wm1000 arms match `ids` on deletes, as expected, since deletes take the same path.
- **Latency.** The delete's own response is 5–10 ms slower with `ids`, from the pre-read: 25.7
  against 18.8 ms median for realistic entries.
- **flush = dev** on every row, so the prototype's flush mode is a faithful control.
- **Non-vacuity.** `idsbreak` leaves exactly one ghost per rep (10 of 10, every type, both sizes),
  so the check sees a removal that's one record short.
- **Race (stress).** Five inserts that match the filter are sent while the delete runs. Ghosts
  per 10 reps:

  | arm | realistic | heavy |
  |---|---|---|
  | `dev` / `flush` | 0 | 0 |
  | `ids` | 19 | 37 |
  | `wm5` | 16 | 31 |
  | `wm1000` | 18 | 33 |
  | `idsbreak` | 28 | 38 |

  A record inserted between the id read and the delete is deleted but not named, so the cache
  keeps it. The prototype's comment says the same: the read isn't atomic with the delete. A flush
  is immune because it reloads from the database afterwards. **Not measured:** a variant that
  deletes `{query} ∧ _id ∈ ids` would leave late inserts in the database rather than as ghosts in
  the cache. That changes what the delete deletes.

### Q2: catch up an update by filter from a watermark?

Update by filter of 10 records (`updateMany` stamped through `srv-dates`, then announced):

| size | type | arm | consistent after (never) | stale | reads: queries / docs / KB |
|---|---|---|---|---|---|
| realistic | entries | dev | 86 / 230 ms (0) | 0 | 13 / 861 / 210.2 |
| realistic | entries | wm5 | 32 / 44 ms (0) | 0 | 14 / 10 / 2.7 |
| realistic | treatments | dev | 102 / 135 ms (0) | 0 | 13 / 135 / 29.4 |
| realistic | treatments | wm5 | 30 / 42 ms (0) | 0 | 14 / 10 / 2.4 |
| heavy | entries | dev | 352 / 493 ms (0) | 0 | 13 / 3,165 / 752.4 |
| heavy | entries | wm5 | 79 / 183 ms (0) | 0 | 14 / 10 / 2.7 |

`ids` flushes here (an update can't be named by a pre-read in this prototype), so it matches `dev`.

**In-flight writes.** Two updates by filter are made. The first is stamped, then *gap* ms later the
second is stamped, written and announced, and only then is the first written and announced. This is
a write stamped before another that commits after it. Stale records per 10 reps (5 records per rep):

| gap | `dev` / `flush` / `ids` | `wm5` | `wm1000` |
|---|---|---|---|
| 0 ms | 0 | 0 | 0 |
| 10 ms | 0 | 50 | 0 |
| 100 ms | 0 | 50 | 0 |
| 1,000 ms | 0 | 50 | 50 |

Identical at both sizes. The watermark misses every in-flight write whose stamp is older than the
watermark by more than the overlap. The flushing arms re-read everything, so they never miss one.
The overlap needed is the longest time between stamping a write and announcing it. Within one
process, that is the longest time a `srv-dates` stamp can wait before its write commits.

### Devicestatus: a v1 delete by query leaves the cache empty

On dev (and the `flush` arm), a v1 devicestatus delete by query drops the devicestatus cache, which
then **stays empty**. At realistic size, 9 of 10 reps on dev had all 288 records missing at the 8 s
timeout. At heavy size, 10 of 10 had all 1,440 missing.

From the code (dev `991b0654`):

- `lib/server/devicestatus.js` `remove()` emits `data-update` with `op: 'remove'` and no
  `changes`. That makes the cache drop the type.
- It doesn't emit `data-received`, which is what triggers a reload. The entries and treatments
  `remove()`s both emit it (`entries.js:63`, `treatments.js:399`).
- The reload therefore waits for the next heartbeat `tick` (`bootevent.js:452`; `settings.heartbeat`
  defaults to 60 s) or the next write of any type.

**Measured gap** (`results/devicestatus-gap.{log,json}`): realistic size, 5 reps, `--settle-ms 90000`.

| arm | consistent after: median / p95 / mean | reads: queries / docs / KB |
|---|---|---|
| `dev` | 56.4 / 56.5 / 55.4 s | 13 / 288 / 347.1 |
| `flush` | 56.2 / 58.7 / 57.0 s | 13 / 288 / 347.1 |
| `ids` | 14 / 14 / 12 ms | 14 / 10 / 0.2 |

The cache comes back on the next heartbeat tick, and the arms re-read all 288 devicestatus records
then. The lab's reps ran about 120 s apart, twice the 60 s heartbeat, so every rep's delete landed
at the same point in the tick cycle, about 56 s before a tick. That's why the five figures agree.
On a site the gap is whatever is left of the current heartbeat, anywhere from 0 to 60 s (read from
the code, not measured), unless another write's `data-received` arrives sooner.

On a site, devicestatus feeds the loop/OpenAPS/pump pills, so they can go blank for up to a heartbeat
after such a delete. The `ids` and watermark arms don't have the gap, because their removal names
the deleted records and needs no reload.

### Read from the code (not run here)

API v3's delete paths (`mongoCachedCollection` `deleteManyOr` / `deleteEveryForm`) already pre-read up
to 1,000 `_id`s before deleting. They then flush anyway unless exactly one document was deleted.
The pre-read cost Q1 measures is already paid on v3 and autoPrune. Only the flush is extra.

## Round 2 (2026-10-30): the write scoped to the ids read

The maintainer decided Q9 on 2026-10-30: "the cache needs records named" is no longer a reason to reopen D-EVENT.
Release 2's direction for Q-A/Q-U is for the write step to resolve each write by filter to ids first. It then
writes `{filter AND _id in ids}` and names those ids. Over 1,000 ids it falls back to the plain filter and a
reload. There is no timestamp watermark. That direction depended on this arm confirming the scoped write.

The new arm is **`resolve`** (`CACHE_CATCHUP=resolve`, `proto/cache-resolve` `cd7a5b6c`, which is
`proto/cache-catchup` with dev `305a6533` merged in):

- A v1 delete by query reads its `_id`s (cap 1,000), deletes `{query AND _id in ids}` and names the ids.
- An update by filter (the lab server's IPC) reads its `_id`s, updates `{filter AND _id in ids}`, and the cache
  re-reads exactly those ids.

`resolvebreak` is the same arm with the last id left unnamed. `dev` is now `305a6533`, which includes the BF-214
fix. The new **left in db** column counts each call's records still in the database afterwards. For a delete,
those are the records it didn't delete: in the race, the inserts that arrived while it ran. Full tables are in
`results/round2/{realistic,heavy}.log`.

| scenario (10 reps) | size | `dev` consistent after | `resolve` consistent after | `resolve` missing / ghost / stale | `resolve` reads | `dev` reads |
|---|---|---|---|---|---|---|
| query delete, entries | realistic | 104 ms | 31 ms | 0 / 0 / 0 | 0.2 KB | 210 KB |
| query delete, entries | heavy | 468 ms | 104 ms | 0 / 0 / 0 | 0.2 KB | 762 KB |
| query delete, devicestatus | heavy | 679 ms | 112 ms | 0 / 0 / 0 | 0.2 KB | 1,735 KB |
| update by filter, entries | realistic | 124 ms | 28 ms | 0 / 0 / 0 | 2.9 KB | 222 KB |
| update by filter, entries | heavy | 389 ms | 116 ms | 0 / 0 / 0 | 2.9 KB | 762 KB |
| race (stress) | realistic | 54 ms | 29 ms | 0 / 0 / 0 | 0.2 KB | 216 KB |
| race (stress) | heavy | 439 ms | 121 ms | 0 / 0 / 0 | 0.2 KB | 754 KB |
| in-flight, gap 1,000 ms | heavy | 508 ms | 80 ms | 0 / 0 / 0 | 2.8 KB | 1,513 KB |

Findings:

- **`resolve` is exact in every scenario at both sizes.** No rep was left inconsistent at the timeout, and there
  were 0 missing, ghost or stale records.
  - **Race:** `ids` left 16 (realistic) and 36 (heavy) ghosts per 10 reps. `resolve` left 0.
  - **In-flight writes:** at every gap (0, 10, 100, 1,000 ms), `resolve` left 0 stale. The watermark arms of round 1
    missed every gap above their overlap.
- **The behaviour change is as designed.** In the race, every insert sent while the delete ran survives in the
  database: 50 of 50 per size, the same as `dev`, because they arrived after the delete's read. `ids` deleted them
  without naming them, leaving 34 (realistic) and 14 (heavy) in the database.
- **Non-vacuity.** `resolvebreak` was flagged in 10 of 10 reps in every scenario at both sizes. A deleted record
  that isn't named shows as a ghost; an updated record that isn't named shows as stale.
- **Cost.** One extra `_id` read per write by filter. With realistic data the write's own latency is about the same
  as `dev`. At heavy size it is slower: an update by filter takes 50 ms against 21 ms, and a delete 41 ms against
  26 ms. The lab's filter field (`bench`) has no index, so the `_id` read scans the collection, and the cost grows
  with its size. Real filters mostly use indexed fields (`created_at`, `date`, `srvModified`), but this was not
  measured with one.
- **BF-214 is fixed on dev `305a6533`.** dev's devicestatus delete by query is now consistent in 122 ms (realistic)
  and 679 ms (heavy). On `991b0654` it stayed empty until the next heartbeat.

## Prototype

`proto/cache-catchup` in `cgm-remote-monitor`, local and not pushed. The results above ran on
`5f8e95bf`. `02d974c2` only moves API v3's mode read into `cache-catchup-ids.mode()`, because
`tests/env.api3.test.js` forbids a direct `process.env` read in `lib/api3`. There's no change in
behaviour. `npm test` on `02d974c2`: 4917 passing, 0 failing, 3 pending (Node 22.23.4,
MongoDB 8.0.29). Round 2 ran on `proto/cache-resolve` `cd7a5b6c` (local, not pushed).

## Running it

```
tools/lab/cache-catchup/run.sh up     # mongo:8.0.29 standalone on 127.0.0.1:27621
tools/lab/cache-catchup/run.sh all    # results/{realistic,heavy}.{log,json}, ~50 min each
tools/lab/cache-catchup/run.sh round2 # results/round2/{realistic,heavy}.{log,json}, ~45 min each
tools/lab/cache-catchup/run.sh down
```

Each tree needs its own `npm ci`. `CC_DEV`, `CC_PROTO`, `CC_PORT` and `CC_CONTAINER` override the
defaults. `lab.js` also takes:

- `--only <scenario,…>`
- `--reps`
- `--size realistic|heavy`
- `--settle-ms` (the never-consistent timeout, default 8000)

The API secret is generated per run and never written. Each log starts and ends with the
container's state.

| file | what |
|---|---|
| `lab.js` | driver: starts each arm, seeds, runs scenarios interleaved, compares cache to database |
| `server.js` | one arm: a tree booted as `lib/server/server.js` boots it, with IPC for cache dumps and writes by filter |
| `readtap.js` | counts every driver `find` (queries, docs, BSON bytes), loaded with `--require` |
| `run.sh` | container up/down and the full run |
