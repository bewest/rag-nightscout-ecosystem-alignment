# EXP-MT-026: a real database in the loop

> **Snapshot — research as of 2026-09-14, measured against MongoDB 7.0.43 with driver 5.9.2 and queries transcribed from `lib/data/dataloader.js` (the doc names no `cgm-remote-monitor` commit). Status: superseded in part — tenancy research, not on a shipping path; §8's feed-poll sweep bound was revised by T4.2 (2026-09-15, in place below) and pgbouncer is now measured in [pgbouncer and the D3 binding](pgbouncer-tenant-binding-2026-09-15.md). Current facts: [execution plan](../../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md).**

*Audience: contributors.*

**Experiments**: EXP-MT-026 (query cost, load cycle, cold wake, event-loop behaviour under
RTT), **EXP-MT-040b** (where database-per-tenant breaks), **EXP-MT-011b** (one logical
database with a tenant discriminator), **EXP-MT-057** (RLS and the change feed, on Postgres),
**EXP-MT-058** (fan-out to one tenant's subscribers), **EXP-MT-059** (does `NOTIFY` scale;
Kafka comparison; pgbouncer conflict)
**Date**: 2026-09-14
**Harness**: `tools/mt-bench/{dbloop,nsfiles,shared-tenant,latency-proxy}.js` and
`pgfeed/{pgfeed,fanout,notify-scale}.js`; raw results in `results/exp-mt-026*.json`, `exp-mt-040b.json`,
`exp-mt-011b.json`, `exp-mt-057.json`, `exp-mt-058.json`, `exp-mt-059.json`
**Under test**: MongoDB **7.0.43**, single-node replica set in Docker, `mongodb` driver
5.9.2 (the version `cgm-remote-monitor` pins), real `indexedFields` index set, queries
transcribed from `lib/data/dataloader.js`. Shapes: **database-per-tenant** (§6.7's A′ rung,
§§1–6) and **one logical database with a tenant discriminator** (§6.6's B, §7).
**Environment**: Linux, 16 cores, 62 GB, Node v24.15.0. **A laptop.** See §L before quoting
anything.
**Confidence**: **measured**, with the scope limits in §L. RTT arms use `tc netem` inside the
database container — kernel-level delay, not a userspace shim.

Decisions taken on the strength of this report are recorded in
[the execution plan](../../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md).

Answers the question every other experiment in this programme deferred: **all of them ran
with no database.** That was tolerable while the question was how much CPU the resident path
burns. It became the largest open risk the moment the recommendation moved to a stateless
tier that trades resident memory for queries.

---

## Executive summary

**The recommendation survives, and the measured database numbers widen its margin rather than
narrowing it.** But two of the inputs it rested on were wrong, and one accident produced the
most operationally important finding here.

1. **The claim the cost model rests on is confirmed: RTT does not consume proportional
   event-loop CPU.** Going from loopback to 50 ms RTT multiplies wall time per operation by
   ~75× and CPU per operation by **2.5×**. Event-loop delay p50 stays pinned at **1.09–1.20 ms
   at every RTT and every concurrency level tested.** Process count is set by CPU and is
   therefore RTT-insensitive; what RTT actually costs is **connection-pool depth and
   latency**, not processes.
2. **`dbQueryCpu_ms = 0.15` was a good guess for the case that matters.** Measured at
   concurrency 256: **0.151 ms loopback, 0.207 ms at 10 ms RTT, 0.379 ms at 50 ms RTT.** The
   *sequential* figure is 0.517 ms, but that over-attributes idle-loop overhead and is not the
   number a loaded server experiences (§3.1).
3. **The load cycle's database work costs 1.82 ms of CPU**, 14 operations in parallel. Folded
   in, one cycle is **8.77 ms**, not 6.27, and K falls from 239 to **171**.
4. **Revised cost at 10,000 tenants** — the real numbers move A and B against C:

   | | processes | resident RAM | DB ops/s |
   |---|---:|---:|---:|
   | A · stateful, all resident | 13 → **17** | 26.7 GB | 6,183 |
   | B · stateful, tiered | 10 → **13** | 5.3 GB | 4,285 |
   | **C · stateless** | **5** (unchanged) | **0.5 GB** | **633** |

5. **The resident cache is 10× cheaper per read than a query**, measured: 0.02 ms CPU for a
   typed cache hit against 0.207 ms for the equivalent indexed query. That converts the
   shared response cache in the component design from a prudent suggestion into a measured
   requirement for the busiest endpoint.
6. **MongoDB took a fatal assertion at 50 tenant databases.** Not slow — a hard crash of the
   whole server, in the middle of an unrelated benchmark, on a file-descriptor limit. §4.
7. **And probing that deliberately found the more important number: `mongod` holds ~3.7 MB of
   non-evictable RSS per tenant database containing *zero documents*** — more than the 2.65 MB
   of app-side resident state that database-per-tenant is supposed to save, and unlike it,
   impossible to evict. **§6.7's A′ rung relocates per-tenant memory rather than deleting
   it.** §4.1.
8. **But A′ was never the destination, and the destination has none of this.** A maintainer
   asked the obvious question this report had failed to ask: wouldn't a multitenant version
   use one logical database with a tenant discriminator? Measured, §7: **104 WiredTiger files
   in total at 400 tenants — 0.26 per tenant, flat — against A′'s 47.0 per tenant**, with the
   planner examining **10 index keys to return 10 documents at every tenant count**. The
   namespace ceiling, the RSS slope and the `fassert()` cliff are all properties of
   database-per-tenant specifically. **They are arguments for consolidating storage, not
   against multitenancy**, and §4's findings should be read that way.

---

## 1. What was actually stood up

50 tenant databases, each carrying the real retention window — 576 entries (48 h), 600
treatments (60 h), 576 devicestatus with 72-point Loop prediction arrays — and the real index
set transcribed from `lib/server/{entries,treatments,devicestatus,profile,food,activity}.js`
`indexedFields`.

```
per-tenant db: 0.9 MB data, 0.9 MB indexes, 41 indexes across 6 collections
```

**§6.7 predicted "roughly 9 collections and 41+ indexes" per tenant database from counting
`indexedFields`. The server built 41 indexes across 6 collections.** The count is confirmed;
the collection estimate was high because `settings` and the `auth_*` collections were not
created here.

Note that **indexes cost as much as data** at this working-set size — 0.9 MB each. For a
tenant whose entire clinical history is under a megabyte, half the storage is index.

## 2. Per-query cost by shape

Sequential, round-robin across the 50 tenant databases, loopback. Wall is per call; CPU is
process CPU across the batch divided by iterations (§3.1 explains why that matters).

| Query, as `dataloader` issues it | wall p50 | wall p99 | CPU/op |
|---|---:|---:|---:|
| latest entry (`date` desc, limit 1) | 0.607 ms | 0.999 ms | 0.381 ms |
| **entries `?count=10` — the v1 REST read** | **0.664 ms** | 1.345 ms | **0.517 ms** |
| entries `?count=576` — full 48 h window | 0.414 ms | 4.552 ms | 0.925 ms |
| entries incremental, 15 min window | 0.440 ms | 1.036 ms | 0.272 ms |
| treatments 60 h window | 0.741 ms | 1.769 ms | 0.365 ms |
| `loadLatestSingle` (eventType, limit 1) | 0.769 ms | 1.398 ms | 0.438 ms |
| devicestatus latest (72-pt prediction) | 0.538 ms | 1.336 ms | 0.335 ms |
| **devicestatus 48 h window** | 0.405 ms | **8.158 ms** | **1.740 ms** |
| `profile.last()` | 0.311 ms | 0.626 ms | 0.203 ms |

**The devicestatus window is the expensive one**, by 4–8×, and for the reason
EXP-MT-055b found independently on the clone side: Loop's 72-float prediction array makes
each document an order of magnitude larger than an entry. Every measurement in this
programme that has touched devicestatus — the cache clone at 2.45 ms, the BSON decode at
1.74 ms — has found the same thing. **Devicestatus retention is the single most effective
per-tenant cost knob a hoster has, and it is already a configurable
(`DEVICESTATUS_DAYS`).**

## 3. The finding the cost model depends on: CPU versus wall under RTT

A query costs two different things and the cost model only cares about one. Wall time
determines latency and how many connections a pool needs. **Event-loop CPU is the term that
competes with the load cycle for the single thread, and therefore the only term that sets how
many processes an operator runs.**

Measured at three network conditions, `tc netem` applied to the database container's
interface. Concurrency is the number of operations in flight; each round is a `?count=10`
read against a different tenant database.

| concurrency | loopback | | 10 ms RTT | | 50 ms RTT | |
|---:|---:|---:|---:|---:|---:|---:|
| | ops/s | CPU/op | ops/s | CPU/op | ops/s | CPU/op |
| 1 | 2,552 | 0.330 | 144 | 1.485 | 37 | 2.377 |
| 16 | 7,387 | 0.166 | 1,502 | 0.390 | 428 | 0.585 |
| 64 | 6,901 | 0.183 | 2,694 | 0.248 | 637 | 0.583 |
| **256** | **7,866** | **0.151** | **5,435** | **0.207** | **1,457** | **0.379** |

**Event-loop delay, the same runs:**

| concurrency | loopback p50/p99 | 10 ms RTT p50/p99 | 50 ms RTT p50/p99 |
|---:|---|---|---|
| 1 | 1.01 / 1.50 ms | 1.11 / 2.19 ms | 1.11 / 1.84 ms |
| 16 | 1.23 / 2.32 ms | 1.13 / 4.56 ms | 1.10 / 5.37 ms |
| 64 | 2.71 / 4.56 ms | 1.10 / 7.37 ms | 1.11 / 9.02 ms |
| 256 | **4.74** / 11.55 ms | **1.20** / 10.39 ms | **1.09** / 9.96 ms |

Three things follow, and they are the load-bearing results of this experiment:

**a. CPU per operation is sub-linear in RTT.** Loopback → 50 ms RTT is an unbounded
multiplication of wall time and a **2.5× multiplication of CPU**. The residual growth is real
— more epoll wakeups, more partial reads, more timer activity per operation — but it is
nothing like proportional. **The stateless tier's process count survives a remote database.**

**b. Event-loop delay does not grow with RTT — it *falls*.** At concurrency 256, loop delay
p50 is 4.74 ms on loopback and 1.20 ms at 10 ms RTT. That is not a paradox: on loopback the
loop is genuinely saturated with work, and under RTT it spends most of its time idle waiting
for the network. **Waiting does not block the loop.** This is the async-I/O assumption the
whole cost model rests on, and it is now measured rather than asserted.

**c. What RTT actually costs is concurrency.** Throughput at concurrency 256 falls from 7,866
to 1,457 ops/s across the range. To sustain the 533 req/s an api tier needs at 10,000
tenants, a 50 ms-RTT deployment needs roughly 94 operations in flight. **A pool of 100 is
adequate and a default pool of 5–10 is not** — which is a concrete, actionable configuration
finding that no local benchmark could have produced.

### 3.1 A measurement trap worth recording

`process.cpuUsage()` attributes CPU for the whole process. In the **sequential** arms one
operation is in flight at a time, so under RTT the loop sits idle for milliseconds per
operation while driver heartbeats, timers and GC continue — and all of that lands in the
per-operation average. That is why the sequential figure rises from 0.517 ms to 1.549 ms at
10 ms RTT while the concurrent figure rises only from 0.151 to 0.207 ms.

**The concurrent figures are the ones that describe a loaded server, and they are the ones the
cost model uses.** The sequential number is not evidence that RTT triples CPU cost; that rise
is an artifact of the measurement method.

## 4. EXP-MT-040b — MongoDB fatal-asserts at 50 tenant databases

**This was an accident.** The first attempt at §2 crashed the server partway through:

```
"msg":"WiredTiger error message" ... "__posix_open_file:815:
  /data/db/index-3896-74235283549191764.wt: handle-open: open",
  "error_str":"Too many open files","error_code":24
"msg":"Failed to open WiredTiger cursor. This may be due to data corruption"
"msg":"Fatal assertion","attr":{"msgid":50882, ...}
"msg":"\n\n***aborting after fassert() failure\n\n"
```

At the moment of the crash:

| | |
|---|---:|
| tenant databases | 50 |
| WiredTiger files in the data directory | **2,404** |
| **files per tenant** | **48.1** |
| container file-descriptor soft limit (Docker default) | **1,024** |

48.1 files per tenant is exactly 41 indexes + 6 collections + overhead. **§6.7 stated the A′
ceiling as a namespace count rather than a data volume, said "where A′ actually breaks is an
experiment, not an opinion", guessed N\* in the low thousands, and left it unrun. This is
that experiment, run by accident, and the important result is not the number — it is the
failure mode.**

- **It is not graceful degradation. It is `fassert()` — an immediate abort of the whole
  `mongod` process.** In database-per-tenant that takes down *every* tenant on the cluster,
  not the one being added.
- **The trigger is a per-process resource limit, which an operator controls.** Raising the
  container to MongoDB's own recommended production value of `nofile 64000` let the same
  workload run without incident. At 48.1 files/tenant, **64,000 descriptors is ~1,330 tenant
  databases**, and 10,000 tenants would need ~481,000 — above most default hard limits and
  well into territory where WiredTiger's per-file cache metadata is the next wall.
- **The 0.9 MB of data per tenant is irrelevant to this.** The crash is driven entirely by
  namespace count. A hoster whose tenants are mostly idle hits it at exactly the same place as
  one whose tenants are all busy.

### 4.1 Probing it deliberately: 47 files and ~3.8 MB of RSS per *empty* tenant

Having found the cliff by accident, `nsfiles.js` walks up to it on purpose — creating tenant
databases with the full index set and **no documents at all**, which isolates namespace cost
from data cost.

| tenants | WT files | files/tenant | mongod RSS | open fds | read p50 | read p99 |
|---:|---:|---:|---:|---:|---:|---:|
| *(baseline, empty server)* | 51 | — | 168.8 MB | 121 | — | — |
| 50 | 2,401 | 47.0 | 339.7 MB | 2,471 | 0.923 ms | 5.081 ms |
| 100 | 4,751 | 47.0 | 547.0 MB | 4,818 | 1.112 ms | 2.090 ms |
| 150 | 7,101 | 47.0 | 714.8 MB | 7,168 | 1.218 ms | 1.507 ms |
| 200 | 9,451 | **47.0** | **909.7 MB** | 9,518 | 1.108 ms | 1.901 ms |

**Exactly 47 files per tenant at every step** — 6 collections plus 41 indexes, no rounding.
The count is not an estimate; it is what the index set arithmetically requires.

**The result worth the experiment is the memory slope: (909.7 − 168.8) MB ÷ 200 = ~3.7 MB of
`mongod` resident memory per tenant database containing zero documents.** This run capped WiredTiger's cache at 1 GB
specifically to test whether that growth was evictable cache; **it is not** — an uncapped run
on the same machine gave 4.0 MB/tenant and a 1 GB-capped run gave 3.8 MB/tenant. The cost is
per-namespace overhead outside the cache (dhandles, session cursor caches, index metadata),
and a cache limit does not reclaim it.

| | per tenant | at 10,000 tenants | evictable? |
|---|---:|---:|---|
| app-side resident `ddata` + `ctx.cache` (EXP-MT-035c) | 2.65 MB | 26.5 GB | **yes** — that is what residency tiering is for |
| **`mongod` RSS per empty tenant database** | **~3.8 MB** | **~37 GB** | **no** |

**This is a serious correction to §6.7's A′ rung, and it runs against the recommendation.**
A′ was presented as buying "the entire measured 10–20× density win with no engine migration
and no schema change". That is true *on the application side* — and it is now measured that
A′ reintroduces a **larger, non-evictable, per-tenant memory cost on the database side**,
paid whether the tenant is active, idle or dormant, and unreachable by any residency policy
the application could adopt. Moving from process-per-tenant to database-per-tenant does not
delete per-tenant memory; it relocates it from a tier that can evict to one that cannot.

**Read latency does not degrade** across this range — 0.92–1.22 ms p50 throughout, and the
p99 improves as the run settles. So A′'s
failure is not a gradual slowdown that monitoring would catch early. It is flat, flat, flat,
and then either an `fassert()` on file descriptors or memory exhaustion.

**The operational reading: A′ is real and cheap on the app tier, and it has two cliffs that
are invisible until you hit them** — a `ulimit` set outside the application, and a database
memory slope steeper than the application memory it saves. Any adoption needs `nofile` raised
deliberately and both file count and `mongod` RSS treated as capacity metrics. §6.7's
index-pruning recommendation (several of the 35 indexes read as speculative) now has a
measured slope to move along: **each index removed is one file and a share of 3.8 MB per
tenant**, on every tenant, forever.

## 5. Load cycle, cold wake, and the alarm slice

Loopback, so these are the CPU floors; scale by §3's ratios for a remote database.

| | wall p50 | wall p99 | CPU |
|---|---:|---:|---:|
| **incremental cycle, 14 ops in parallel** (§2.3) | 1.242 ms | 2.404 ms | **1.824 ms** |
| fetch whole window (4 queries) | 0.750 ms | 13.122 ms | 4.777 ms |
| **fetch + build ddata (full cold wake)** | 0.697 ms | 23.483 ms | **6.817 ms** |
| **alarm slice — what `ns-evaluator` fetches per change** | 0.898 ms | 1.968 ms | **1.189 ms** |

Wall is below CPU because the operations run in parallel across cores; the "% of wall" column
in the raw output is meaningless for these arms and should be ignored.

**The load cycle, complete at last.** Four passes have now each found a term the previous one
missed:

| Term | ms | share | found by |
|---|---:|---:|---|
| `ddata` derivation, post-#8733 | 2.19 | 25 % | K report §4 |
| `cache.insertData` defensive clone | 4.08 | 47 % | EXP-MT-055b |
| **database, 14 ops in parallel** | **2.50** | **29 %** | **EXP-MT-026** |
| **total** | **8.77** | | K = **171** active tenants/shard |

(Database term scaled to 10 ms RTT.) **The cycle is now 4× what the second pass reported and
the database is its smallest component.** The largest is still a defensive deep clone that
exists only to maintain a resident copy.

**Cold wake at 6.8 ms** confirms §7.1's ~3–4 ms estimate was the local-compute half and
missed the fetch. It remains cheap in absolute terms — a tenant can be materialised on demand
well inside a request budget.

## 6. The revised cost model

`node deployment-cost.js 10000`, with §3's measured CPU-per-operation and §5's measured cycle
and evaluator costs substituted for the guesses. 10 ms RTT (a managed database in the same
region) is the default; `RTT_MS=0` and `RTT_MS=50` reproduce the other two.

| At 10,000 tenants | processes | resident RAM | DB ops/s | routing |
|---|---:|---:|---:|---|
| A · stateful shards, all resident | **17** | 26.7 GB | 6,183 | tenant→shard map, sticky, rebalancing |
| B · stateful shards, tiered | **13** | 5.3 GB | 4,285 | + eviction policy + cold-alarm path |
| **C · stateless api + evaluator + realtime** | **5** | **0.5 GB** | **633** | none but socket stickiness |

Option C's internals, all now measured rather than assumed:

```
api         533 req/s    110 ms/s   1 process   (0.207 ms CPU/op)
evaluator    33 /s        80 ms/s   1 process   (2.4 ms each: 1.19 fetch + 0.61 plugins + materialise)
realtime   6000 sockets  1.8 ms/s   1 process   0.2 GB
```

**The measured database numbers moved A from 13 to 17 processes and B from 10 to 13, and left
C at 5.** The reason is structural: the resident options pay database cost *per tenant per
cycle on a timer*, so a more expensive query multiplies against tenant count; C pays it per
request, so it multiplies against demand, which is 10× smaller.

**The one number that moved against C**: a typed cache hit is **0.02 ms** of CPU against
**0.207 ms** for the equivalent query — **10×**. At 533 req/s that is 110 ms/s of a 300 ms/s
budget spent on reads that residency serves nearly free. It does not change the process
count, but it does mean the shared response cache keyed on `(tenant, lastUpdated)` in the
component design is **load-bearing, not optional**, for `/api/v1/entries` specifically.

## 7. EXP-MT-011b — one logical database with a tenant discriminator

**§4 measured a migration rung, not the destination shape.** A′
(database-per-tenant) is §6.7's stage 2 — a migration rung chosen because it requires no
schema change. The multitenant target is §6.6's B on Mongo or D on Postgres: **one logical
database, every document carrying a tenant discriminator, the index set tenant-prefixed.**
Then 6 collections and 41 indexes are *totals*, not per-tenant.

§6.7 asserts this outright — "35 total with `tenant_id` as the leading column, not 35 per
tenant; the curve is flat instead of linear" — and never measured it. Same corpus, same index
set mechanically tenant-prefixed, same queries, same server config, so the two are directly
comparable.

| tenants | documents | **WT files** | mongod RSS | data | index | read `?count=10` p50 | keys examined |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 175,300 | **104** | 544.8 MB | 94.5 MB | 55.1 MB | 0.702 ms | **10** |
| 200 | 350,600 | **104** | 765.1 MB | 189.2 MB | 113.9 MB | 0.745 ms | **10** |
| 300 | 525,900 | **104** | 973.8 MB | 284.0 MB | 172.6 MB | 0.554 ms | **10** |
| 400 | 701,200 | **104** | 1,075.6 MB | 378.7 MB | 233.6 MB | 1.011 ms | **10** |

**The ceiling does not exist in this shape.**

- **104 files in total at 400 tenants — 0.26 per tenant, and flat.** A′ needs 47.0 *per
  tenant*: 18,800 files for the same 400 tenants, and 470,000 at 10,000. The file-descriptor
  `fassert()` of §4 is unreachable here, because file count does not grow with tenant count at
  all.
- **Index locality holds, which is the result that actually had to be checked.** The planner
  examines **10 keys to return 10 documents at every tenant count**. This is the opposite of
  §6.1's measurement of MongoDB's *role-keyed view* mechanism, which gave the planner no
  constant and forced either a COLLSCAN or an IXSCAN over every tenant's keys. **An explicit
  discriminator in the query is a constant the planner can build index bounds from; a
  server-injected `$expr` over `$$USER_ROLES` is not.** That distinction, not the engine, is
  what decides index locality.
- **Indexes are cheaper in aggregate**: 233.6 MB for 400 tenants against A′'s ~0.9 MB/tenant,
  ~360 MB for the same corpus. One B-tree over 400 tenants packs better than 400 B-trees.
- **Memory is now data, not namespace.** The 2,321 KB/tenant slope here is *not* comparable to
  A′'s 3,793 KB/tenant: A′'s probe held **zero documents**, so that figure was pure namespace
  overhead, while this one is loaded with 701,200 real documents and is therefore
  data-and-index cache — evictable, proportional to stored data, and a cost both shapes pay.
  **The like-for-like comparison is A′'s ~3.7 MB/tenant of non-evictable namespace overhead
  against this shape's approximately zero.**

Read latency is roughly flat with noise (0.554–1.011 ms p50, non-monotonic) and the p50 at 400
tenants is the highest measured. Since keys examined never moved, that is working-set pressure
against the 1 GB WiredTiger cache — 612 MB of data and index at 400 tenants — not index
degradation. **It is the first sign of the constraint that replaces namespace count: ordinary
cache pressure, which is the constraint every database has and which sharding addresses
normally.**

### 7.1 What the shared shape costs instead: the forgotten filter

Shared collections trade a namespace ceiling for an isolation problem, and it is worth being
precise about which parts of that trade are real. Explain plans against the 400-tenant,
230,400-document `entries` collection:

| query | keys examined | **docs examined** | returned | time |
|---|---:|---:|---:|---:|
| tenant + indexed field (`sgv`) | 154 | 154 | 154 | 1 ms |
| tenant + **unindexed** field (`rssi`) | 576 | **576** | 576 | 2 ms |
| tenant + **regex** on unindexed field | 576 | **576** | 576 | 2 ms |
| **forgotten tenant filter**, unindexed | 0 | **230,400** | **230,400** | 92 ms |
| **forgotten tenant filter**, regex | 0 | **230,400** | **230,400** | 118 ms |

**The good news is real: a tenant-scoped query stays bounded to one tenant's 576 documents
even when the other predicate is unindexed, even for a regex.** The tenant-prefixed index
bounds the scan and the unindexed predicate is applied as a residual within those bounds. So
§6.5's unbounded-query exposure **does not get worse** in the shared shape — a noisy tenant's
regex costs one tenant's documents, exactly as it does under A′.

**The bad news is the whole argument for RLS, now demonstrated rather than asserted.** A query
that simply omits the discriminator does not fail, does not error, and does not return
nothing. It returns **every tenant's data** — 230,400 documents of other people's glucose
readings — and it does so in 92 ms, fast enough that nothing looks wrong. §6.6 calls B "the
only architecture where the enforcement component is developer discipline"; this is what that
sentence costs when the discipline lapses at one of ~30 call sites.

Against §6.1's measured Postgres result — *a query with zero `tenant_id` predicate in the SQL
returns only the bound tenant's rows, and an unbound connection returns zero rows* — the
comparison is stark, and it is not about performance:

| | forgotten filter on Mongo + discriminator | forgotten filter on Postgres + RLS |
|---|---|---|
| result | **every tenant's rows** | the bound tenant's rows |
| unbound connection | every tenant's rows | **zero rows** |
| failure mode | silent, fast, undetectable in tests that use one tenant | fail-closed |

**So the engine question is settled by this and not by the namespace curve.** Both engines
handle the shared shape's *performance* well. Only one of them makes the forgotten filter
safe, and for a system holding other people's clinical data that is the deciding property.

### 7.2 What this does to §6.7's ladder

The ladder's stages are unchanged; their justifications are not.

- **Stage 2 (A′) is a transitional rung, not a resting place.** Its case was "the entire
  measured density win with no schema change", and §4 shows it pays for that with a
  non-evictable ~3.7 MB/tenant on the database tier and a hard cliff at ~1,360 tenants. It
  remains a reasonable *migration* step for a hoster in the hundreds of tenants, and its
  per-tenant `mongodump` export is a genuine asset. It does not reach 10,000.
- **Stage 3's case is stronger and differently argued.** §6.7 justified Postgres+RLS on three
  axes: write coverage, index locality and connection multiplexing. **Index locality is no
  longer the discriminator between engines** — §7 shows an explicit discriminator gives the
  Mongo planner perfect bounds. What survives, and is now demonstrated, is **fail-closed
  isolation** (§7.1) and write coverage. Those are sufficient.
- **The namespace argument moves from "A′ versus Postgres" to "per-tenant versus shared."** It
  is an argument about consolidating storage, which both engines support, and it should not be
  cited as an argument for Postgres specifically.

## 8. EXP-MT-057 — how the evaluator learns, on Postgres

The component design calls `ns-evaluator` "change-driven" and never says by what mechanism.
Four candidates, and they are not interchangeable, because the consumer is an **alarm** path:
a delayed event is a nuisance, a dropped event is a missed hypo alert. **The question that
separates them is not throughput — it is what happens while the consumer is not there.** So
every arm below is a disconnect test.

PostgreSQL 16.14, `wal_level=logical`, 400 tenants × 576 entries = 230,400 rows, 53 MB.

### 8.1 A methodology correction first, because it nearly became a finding

The first run measured RLS as the `postgres` superuser. **Superusers bypass RLS
unconditionally** — `BYPASSRLS` is implicit, and `FORCE ROW LEVEL SECURITY` subjects the table
*owner*, not a superuser. So the policy was never enforced: an unbound connection returned all
230,400 rows and the planner, never seeing the predicate, chose the global date index. Both
results were about to be written up — the first as "RLS fails open", the second as "RLS does
not get index bounds". Both are artifacts of connecting as the wrong role.

**§6.1's parenthetical "app role `NOSUPERUSER NOBYPASSRLS`" is not a detail. It is the entire
mechanism**, and it is silently absent in any environment where the application connects as
the database owner — which is the default in most quick-start Postgres setups, including the
one this experiment started from.

### 8.2 RLS on Nightscout query shapes

As `ns_app` (`NOSUPERUSER NOBYPASSRLS`), bound per transaction with `set_config(..., true)`:

| | p50 | p99 |
|---|---:|---:|
| **RLS-bound, no tenant predicate in the SQL at all** | **0.383 ms** | 1.993 ms |
| explicit `WHERE tenant_id = $1` (RLS also active) | 0.585 ms | 2.535 ms |
| RLS-bound, full 48 h window (576 rows) | 1.452 ms | 3.770 ms |

```
Limit  (actual time=0.013..0.023 rows=10)
  ->  Index Scan using entries_tenant_date on entries  (actual rows=10)
        Index Cond: (tenant_id = (NULLIF(current_setting('app.current_tenant_id', true), ''))::uuid)
        Buffers: shared hit=9
```

**The policy predicate becomes an `Index Cond` on the tenant-leading index.** Index locality
is not merely comparable to the explicit filter — the RLS form is *faster* (0.383 vs 0.585 ms,
9 buffers either way), because the planner resolves `current_setting` once rather than
handling a bound parameter. This is the Postgres counterpart of EXP-MT-011b's "10 keys
examined for 10 returned", and it settles the question that §6.1 could only answer on a
generic corpus.

| | as `ns_app` | as superuser |
|---|---:|---:|
| unbound connection, no predicate | **0 rows** | 231,700 rows |
| bound connection, no predicate in SQL | 581 rows (that tenant's) | 231,700 rows |

**Fail-closed, confirmed on Nightscout's shapes**, and the contrast with EXP-MT-011b's Mongo
discriminator — where the same forgotten filter returned all 230,400 rows — is the reason the
recommendation lands where it does.

### 8.3 The four mechanisms, and the disconnect test

| | delivered while connected | latency | **written while consumer down** | **delivered after it returned** |
|---|---:|---:|---:|---:|
| **LISTEN/NOTIFY** | 500/500 | **1 ms p50** | 200 | **0 — all lost** |
| **logical replication slot** | — | — | 200 | **200/200 — nothing lost** |

- **`NOTIFY` is fast and lossy.** 1 ms delivery latency, and **every event written while the
  listener was disconnected is gone permanently** — there is no backlog, no cursor, nothing to
  resume from. Re-`LISTEN` starts from now. For a browser refresh that is fine. **For alarm
  delivery it is disqualifying on its own.**
- **A replication slot loses nothing and does not replay.** 200/200 INSERT changes delivered
  when the consumer finally arrived; re-consuming immediately after returned **0** changes,
  because `pg_logical_slot_get_changes` advances the slot. That is exactly the
  at-least-once-with-a-cursor semantic an alarm path needs.
- **The slot's cost is WAL retention, and it is affordable.** 574 bytes of pinned WAL per row.
  At 10,000 tenants writing once per five minutes (33 rows/s), **an abandoned slot pins
  ~0.06 GB/hour** — about 1.4 GB/day. That needs monitoring and an alert, but it is a slow
  leak, not a fast one: an operator has days, not minutes, to notice.

### 8.4 The poll is not what it used to be

Today's polling is per-tenant and O(tenants) — the 6,183 DB ops/s of option A. The poll a
change-driven design needs is **one aggregate query returning only the tenants whose newest
reading is later than their last evaluation**:

| | p50 | tenants returned |
|---|---:|---:|
| all tenants due (watermarks at zero — the cold-start case) | 20.89 ms | 400 |
| steady state, watermarks current | 13.69 ms | 0 |
| **bounded by the `date` index (last 10 minutes)** | **1.02 ms** | 0 |

**Bounded by a date index, the "who needs evaluating" sweep costs ~1 ms at 400 registered
tenants.** At one sweep every 30 seconds 1.02 ms is 0.03 ms/s of database work, four orders of
magnitude below the resident model's polling. (T4.2, 2026-09-15, which built the component,
measured how it scales with registered tenants — below.)

**The cost is not independent of how many tenants are registered; the run above varied neither
axis.** Reproducing this run's own query *and* its own index configuration across
corpora it never built (`tools/measure-feed-poll-bound.js` in `cgm-remote-monitor`):

| registered tenants | 100 | 400 | 1600 | 3200 |
|---|---:|---:|---:|---:|
| sweep p50, writing set held at 100 | 0.696 ms | **0.979 ms** | 2.909 ms | 5.236 ms |

The plan is a nested loop with one index descent per row of the watermark table, so **as
published the sweep is O(registered tenants)** — about 1.4 µs each. It lands on 1.02 ms at 400
tenants because 400 tenants is what was measured. At 10,000 it would be **~15 ms a sweep, not
1**.

**What makes it genuinely bounded is an index no emitted schema contains — and cannot contain
under its current rule.** Every index `tools/nsschema/emit/postgres_emit.py` produces is
**tenant-leading**, because every tenant-facing query runs under a policy predicate on
`tenant_id` (§8.2). This sweep has **no tenant predicate by construction** (§8.6), so it needs a
**global** index on `date`, and the emitter will never write one. With it, the same four corpora
cost 0.806 / 0.731 / 0.761 / **0.865 ms — flat across 32× the corpus**; and holding the corpus
at 1600 tenants while varying the writing set 25 → 1600 gives 0.579 / 0.790 / 1.209 / 3.001 ms.

**So the real bound is rows written since the last sweep** — ~0.57 ms fixed plus ~0.8 µs per row
inside the window — which is what this section's own sentence *claimed* without the index that
makes it true. Without it the same statement costs 6.6 ms at 57.6k rows and **108 ms at 1.84M**,
flat against the writing set, which is the signature of scanning everything.

So polling is not the alternative to CDC; **it is the affordable backstop underneath it** — on a
schema that carries one index the emitter does not currently know how to produce.

**Two things this lands on the emitter** (`{P}` T2.1), neither of which it can do today:

1. **A global, non-tenant-leading index** for the cross-tenant sweep. The emitter's rule —
   tenant first, always — is correct for every tenant-facing query and wrong for the two
   components §8.6 says can never be tenant-bound. The rule needs an exception it can express.
2. **An insertion-ordered column on `entries`.** The window predicate is over the **uploader's
   clock**, because the emitted schema has no server-assigned insertion column at all. A device
   running slow writes rows a bounded sweep cannot see — which makes the periodic full sweep a
   *detection latency* rather than a tidy-up — and a device running fast drags its tenant's
   watermark past real time, after which honest readings sit below it and **that tenant goes
   quiet until the clock catches up**. The second cannot be fixed at this layer: clamping
   re-reports the same row forever, and dropping a reading is not something an alarm path may
   do. T4.2 counts it instead.

### 8.5 The recommendation that follows: a spine, an accelerator, and a backstop

None of the four mechanisms is sufficient alone, and the right answer uses three of them for
different reasons:

1. **Logical replication slot as the spine.** The only mechanism measured here that survives a
   consumer restart without losing an alarm. Requires slot monitoring (§8.3).
2. **`LISTEN`/`NOTIFY` as a latency accelerator**, optional. It cuts the tail between a write
   and an evaluation to ~1 ms where a slot reader's poll interval would otherwise set it. It
   carries no correctness weight, so its lossiness does not matter.
3. **The bounded aggregate poll as a safety backstop**, non-optional. Slots get dropped,
   consumers get partitioned, replication breaks. At ~1 ms per sweep there is no reason not to
   run it, and **for an alarm path "the feed was broken and nobody noticed" is the failure
   that matters.** It is also the mechanism that closes the cold-start case, where every
   watermark is behind.
4. **Write-path publish is rejected** — it misses anything not written through the api
   (backfills, migrations, `nightscout-connect` writing directly) and couples two components
   that otherwise share only storage.

### 8.6 The consequence nobody had drawn: RLS cannot protect the feed

This follows directly from §8.1 and is a real constraint on the component design.

**The evaluator must see every tenant** — that is its job. So it cannot run under a policy that
binds it to one tenant. Likewise, reading a replication slot requires the `REPLICATION`
attribute, which is not tenant-scoped at all: **the WAL is one stream containing every
tenant's rows.**

So the isolation story is split, and honestly it should be stated that way:

| path | isolation enforced by |
|---|---|
| `ns-api` — arbitrary client queries | **the database** (RLS, per-transaction bind, fail-closed) |
| `ns-evaluator`, `ns-realtime` — feed consumers | **code review**. They hold cross-tenant privilege by construction |

**RLS protects the path that takes untrusted input, which is the one that needs it most.** But
the change-feed components are privileged, their blast radius is every tenant, and no storage
mechanism will fix that. The design consequence is that they must stay **small, single-purpose
and genuinely reviewed** — which is an argument for them being separate, narrow entrypoints
rather than modes of a large shared process, and it is a better argument for the decomposition
than the cost model is.

## 9. EXP-MT-058 — the last hop: reaching one tenant's subscribers

§8 settled how `ns-evaluator` *learns* about a change. It left the hop after that unexamined:
a change for tenant X must reach the sockets subscribed to tenant X, which are held by one of
N `ns-realtime` processes, and the process that learns about the change is not necessarily the
one holding the socket. Does that hop need its own stateful routing — tenant→process affinity,
a Redis adapter, per-tenant cursors — or are Postgres's primitives enough?

**The asymmetry that makes this tractable**, and which §8 established but did not apply here:

| | losing a change means | so it needs |
|---|---|---|
| `ns-evaluator` | a missed hypo alarm | the replication slot |
| `ns-realtime` | a browser is stale until the next reading, and re-syncs on reconnect | **it can tolerate loss** |

The cheap lossy mechanism is admissible precisely where correctness does not rest on it.

### 9.1 Fan-out: every listener gets everything, and no affinity is needed

32 concurrent `LISTEN` connections on one channel, 200 `NOTIFY`s:

```
200 NOTIFYs -> 6400 deliveries across 32 listeners (expected 6400, 32/32 complete)
notify cost 0.490 ms/event at the writer; delivery latency 0 ms p50 / 2 p99 / 4 max
```

**Every listener received every event.** So N `ns-realtime` processes can each subscribe, and
each emits to whichever of its own local socket rooms match — **no tenant→process affinity, no
Redis adapter, no coordination.** A process that holds no sockets for a tenant simply ignores
that tenant's event.

### 9.2 Postgres will do the per-tenant routing itself

Better than ignoring events is not receiving them. `LISTEN` takes a channel name, so a channel
per tenant means the server filters:

| channels on one connection | subscribe cost | targeted `NOTIFY` delivered |
|---:|---:|---:|
| 100 | 0.14 ms/channel | 1 (unsubscribed channel filtered out) |
| 1,000 | 0.10 ms/channel | 1 |
| 5,000 | 0.05 ms/channel | 1 |
| **10,000** | **0.08 ms/channel** | **1** |

**One connection held 10,000 tenant channels**, and a `NOTIFY` to a channel it had not
subscribed to was filtered server-side. `LISTEN`/`UNLISTEN` as sockets connect and disconnect
costs ~0.1 ms.

This narrows §8.6's privilege finding in a useful way. **`ns-realtime` does not need
cross-tenant privilege on the data path** — it receives only the tenants it currently holds
sockets for. Only the slot reader and `ns-evaluator` are unavoidably cross-tenant, which
shrinks the code that must be reviewed as privileged to one small component.

### 9.3 A real delta fits in the payload

| | |
|---|---:|
| realistic `dataUpdate` delta (1 SGV + 1 Loop devicestatus, 72-point prediction) | **1,039 bytes** |
| largest `NOTIFY` payload accepted | 7,900 bytes (8,000 rejected: *payload string too long*) |
| fallback: `NOTIFY` carries a row id, listener reads the row | **0.183 ms** per lookup |

**The common case carries the delta inline.** A batch upload — AAPS posting many treatments at
once — can exceed 7,900 bytes, and the fallback is an identifier plus one indexed lookup at
0.183 ms. Both paths are cheap; the design should implement the fallback rather than assume
the payload always fits.

### 9.4 The hazard, and the design change it argues for

A `LISTEN`ing session that stops consuming cannot be cleaned up by the server. Its
un-consumed notifications are retained in a shared **8 GB SLRU queue** until it reads them or
disconnects. So: can one wedged `ns-realtime` degrade or stop *ingest*?

With one listener holding its connection open and never reading its socket, 20,000 × 4 KB
notifications:

```
queue usage 0.0000% -> 0.7753%
write latency {"p50":0.09,"p99":0.86,"max":1.85} ms      <- flat, no degradation
ordinary INSERT with the queue in this state: 2.373 ms   <- ingest unaffected
~2,579,522 notifies to fill the queue
at 33 changes/s (10,000 tenants), a stuck listener has ~21.7 hours
```

**The hazard is real but slow, and it is monitorable.** ~21.7 hours of headroom at 4 KB
payloads; at the realistic 1,039-byte delta it is roughly four times that. Write latency does
not degrade on the way — there is no early warning in the timings, so
`pg_notification_queue_usage()` must be an actual alert rather than something noticed.

**What matters is what happens when it does fill: `NOTIFY` blocks.** If the `NOTIFY` is fired
by an `AFTER INSERT` trigger — which is how §8 implemented it, and how most examples do — then
it is *inside the ingest transaction*, and a wedged realtime process eventually stops uploads.
**A CGM uploader failing to POST because a display component is stuck is not an acceptable
coupling.**

> **Design consequence: do not `NOTIFY` from a trigger. `NOTIFY` from the slot reader.** The
> slot reader is already consuming every change for `ns-evaluator`; having it also emit the
> per-tenant `NOTIFY` costs nothing and removes the notification queue from the write path
> entirely. Ingest then depends only on the WAL, and the worst case of a wedged `ns-realtime`
> is that realtime is stale — which §9's opening asymmetry already says is tolerable.

This is the second time in this programme that the measured hazard was not the thing being
measured: §4's file-descriptor `fassert()` and this one both arrived as "the mechanism works
fine, and here is how it takes the system down anyway."

### 9.5 The assembled answer

**How a change reaches one tenant's subscribers, with no stateful tracking beyond the sockets
themselves:**

```
write ──> WAL ──> slot reader (privileged, cross-tenant)
                    ├──> queue partitioned by tenant hash ──> ns-evaluator workers
                    │                                            └──> alarm row ──> WAL ──┐
                    └──> pg_notify('tenant_<id>', delta)  ───────────────────────────────┤
                                                                                          │
                       ns-realtime ── LISTEN only on tenants it holds sockets for ◄────────┘
                            └──> io.to('DataReceivers:<id>').emit(...)
```

- **State held by `ns-realtime`**: the socket rooms (inherent to the protocol) and one
  `LISTEN` per tenant it currently serves. Both are *connection* state, discarded on
  disconnect. **No per-tenant cursor, no delivery tracking, no polling.**
- **Durability does not live in this path.** It lives in the alarm row: a reconnecting client
  queries what it missed, and the push channel (Pushover/APNS) is emitted by `ns-evaluator`
  directly, so the safety-critical delivery never traverses a socket at all.
- **Postgres's primitives are sufficient for this hop.** Fan-out, server-side per-tenant
  filtering, and a payload large enough for the common delta — with one indexed lookup as the
  documented fallback. No Redis, no broker, no affinity.

## 10. EXP-MT-059 — is `LISTEN`/`NOTIFY` built for this, or would Kafka be better?

§9 showed `NOTIFY` does the fan-out hop correctly at 32 listeners. That is not the same as
showing it *scales*, and the mechanism has three documented properties that should make anyone
nervous about leaning on it (`src/backend/commands/async.c`):

1. **`NOTIFY` serialises.** Appending to the notification queue takes an exclusive lock, so all
   notify traffic in the cluster passes through one lock.
2. **Delivery is signal-based and O(listeners).** At commit the notifying backend walks every
   listening backend and signals it.
3. **A listener is a whole Postgres backend.** `LISTEN` is session state, so every listening
   process costs a connection out of `max_connections` plus a backend's memory.

Each is a real ceiling. Whether any *binds* depends on how many listeners this design has.

### 10.1 The axis that degrades is listener count, not message rate

| listeners | NOTIFY/s | writer p50 | headroom vs the 33/s required |
|---:|---:|---:|---:|
| 1 | 7,873 | 0.072 ms | 239× |
| 8 | 5,202 | 0.154 ms | 158× |
| 32 | 3,016 | 0.307 ms | 91× |
| 128 | 1,016 | 0.980 ms | 31× |
| 256 | **495** | 1.967 ms | 15× |

**15.9× slower from 1 to 256 listeners.** Sub-linear — strict O(listeners) would be 256× — but
unmistakably not flat, and the writer's per-event cost grows ~27×. **The concern is
well-founded: `NOTIFY` is not built to scale in listener count.**

Message rate is a different story:

| | NOTIFY/s |
|---|---:|
| sequential, one per transaction | 9,434 |
| 8 concurrent writers | 32,787 |
| 32 concurrent writers | **35,398** |
| batched in one transaction | 12,666 |

**286× headroom on the slowest path** — enough for ~2.8 M tenants at one change per five
minutes. The queue lock does not bind anywhere near the rate this design generates.

### 10.2 Why the design survives: subscribers are not listeners

**This is the whole answer, and it is a property of the design rather than of `NOTIFY`.**

The subscribers are **websockets**, and they are held by `ns-realtime` processes. Only the
*processes* `LISTEN`. At ~31 KB/socket (EXP-MT-045a) one process holds ~10⁵ sockets, so 10,000
tenants at four followers each is **40,000 sockets — one or two processes, hence one or two
listeners**, sitting at the top of the table above with 239× headroom.

**Reaching 100 listeners would require ~10⁶ tenants.** `NOTIFY`'s listener ceiling is about two
orders of magnitude beyond the design target.

The failure mode to avoid is therefore architectural, not operational: **a design in which each
subscriber, or each tenant, holds its own `LISTEN` would collapse.** §9.2's 10,000 channels on
*one connection* is the shape that works; 10,000 connections holding one channel each is the
shape that does not. That distinction should be written into the design, because the two look
superficially similar.

### 10.3 The trap: `LISTEN` through a transaction-mode pooler fails silently

§6.7 recommends **pgbouncer in transaction mode** so one pool serves every tenant with
`set_config(..., is_local => true)`. §9 recommends `LISTEN`. `LISTEN` is *session* state and a
transaction-pooled connection is handed to a different client after each `COMMIT`. Measured
against `edoburu/pgbouncer` in `pool_mode = transaction`:

```
ordinary query through transaction-mode bouncer: ok
LISTEN through the bouncer: accepted (no error raised)
50 NOTIFYs sent direct to Postgres -> 0 received by the bouncer-side listener
verdict: LISTEN is accepted but delivers NOTHING — silent breakage
```

**No error is raised at any point.** A realtime component placed behind the pooler would simply
never update, and nothing would log a reason. This is a live trap in the recommendation as it
stood: two pieces of advice from two different sections, each correct alone, silently
incompatible when followed together.

> **`ns-realtime` and the slot reader must connect directly to Postgres, not through the
> transaction-mode pooler.** That is a handful of direct connections against a pool serving the
> api tier, so it costs nothing — but it has to be stated, because putting everything behind
> one pooler is the obvious thing to do and it fails without complaint.

### 10.4 Would Kafka be better?

**The framing to reject first: this is not a choice between `NOTIFY` and Kafka.** The design
already has a durable, ordered, replayable log — **the WAL, consumed through a replication
slot** (§8.3: 200/200 delivered after a consumer outage, no replay on re-consume). That is the
Kafka-shaped primitive, and it is already doing the job Kafka would be brought in to do.
`NOTIFY` is only the *last hop*, and the last hop is best-effort by design.

So the real question is whether to run a **second** log. What each side buys:

| | Kafka / Redpanda | WAL slot + `NOTIFY` |
|---|---|---|
| durable ordered log | yes | **yes, already — the WAL** |
| replay on the fan-out hop | yes | no — **and §9 establishes it is not needed** |
| consumer groups, partitions | yes | slot reader + hash-partitioned queue (§8.5) |
| survives the database being down | yes | no — but with the database down there is nothing to publish |
| independent of the storage engine | yes | no |
| **operational cost** | **a cluster: brokers, quorum, retention, upgrades, monitoring** | **none — it is the database already being run** |

**Kafka's central value is durability and replay, which is precisely the property this hop does
not want.** Paying a cluster's operational cost for a guarantee the design explicitly discards
is the wrong trade. §6.3 and EXP-MT-037 reached the same conclusion from the migration
direction ("keep the plain change-stream-tailing script; do not stand up Kafka"), and §7.4
notes that per-tenant Kafka topics were part of the 11–12 Kubernetes objects per tenant that
made the current hosting model expensive in the first place.

**And if `NOTIFY` ever does bind, Kafka is still not the next step.** The limit measured here is
*listener fan-out*, and the tools built for that are **Redis pub/sub or NATS** — fan-out buses
with no durability, which is exactly the requirement. Reaching for Kafka would be buying the
one property that is not needed while not directly addressing the one that bound.

**Concrete triggers for revisiting**, so this is falsifiable rather than a preference:

- more than ~100 listening processes — roughly 10⁶ tenants at measured socket density;
- a change rate approaching 10⁴/s — roughly 100× the current target;
- storage moving off Postgres, at which point the WAL-slot spine goes too and the whole
  mechanism has to be re-chosen;
- a requirement that the fan-out hop survive database unavailability, which would be a change
  to what the product promises rather than to how it is built.

**None of those is within an order of magnitude of the 10,000-tenant target**, which is the
honest reason to use the database's own primitives and not run a second distributed system.

## L. Limits — read before quoting any of this

This is a laptop. The numbers above rank hypotheses and settle mechanism questions; **none of
them is a capacity result**, and several would move on real infrastructure.

**What is not in the loop at all:**

- **No TLS.** A managed database connection is encrypted. Handshakes and per-message
  encryption add CPU that is entirely absent here, and it lands on exactly the term the
  recommendation depends on (CPU per operation). **This is the most likely direction for
  §3's figures to be wrong, and the gap is not small.**
- **No authentication.** SCRAM adds per-connection cost, which matters most for a pool that
  is being grown or recycled.
- **No replica-set write concern.** A single-node replica set acknowledges immediately;
  `w:majority` across three nodes does not.

**What is unrepresentative:**

- **The working set is 45 MB and entirely in page cache.** Every read here is a cache hit. A
  hoster's working set exceeds RAM by design, and the first thing that changes is read
  latency variance, not the mean.
- **`tc netem` delay is constant and symmetric.** Real networks have jitter, loss,
  reordering, congestion control and slow-start. Delay is the component that matters for RTT
  accounting, and it is the only one reproduced.
- **50 tenants, not 10,000.** The per-query figures are per-tenant-database and should carry;
  the *aggregate* behaviour of one cluster serving thousands of databases is precisely what
  §4 shows can fail discontinuously, and it was not measured.
- **No competing load.** One benchmark process, one mongod, on a machine also running a
  desktop session and unrelated containers — which adds noise but no contention of the kind a
  production cluster has.
- **16 cores.** The parallel arms (§5) benefit from that; a 2-vCPU container would not.

**What was not tested:**

- **PostgreSQL + RLS** has been run with a database in the loop: `rls-poc/` ran against a live
  `postgres:16-alpine` container (§6.1's figures), and §8 adds RLS and the change feed on
  Nightscout's own query shapes. What remains unmeasured on Postgres here is **writes at ingest
  rate** and the **shared-collection working set past cache size**. **`pgbouncer` in
  transaction mode** was not tested here; it is measured in
  [pgbouncer and the D3 binding](pgbouncer-tenant-binding-2026-09-15.md) (2026-09-15).
- **§7 tops out at 400 tenants and 701,200 documents**, where working-set pressure against a
  1 GB cache is only beginning to show. The shape of the curve past the point where the
  working set exceeds cache is the open question for the shared model, and it is the normal
  database capacity question rather than a Nightscout-specific one.
- **Change streams at tenant scale** — the mechanism `ns-evaluator` and `ns-realtime` both
  depend on. §4 of the component design flags the one-cursor-per-database tension with A′;
  nothing here tested it.
- **Write paths.** Every arm is a read. Ingest is what a hoster's uploaders actually generate.
- **Sustained running.** The longest arm here is minutes. Nothing about connection churn,
  memory growth, index fragmentation or oplog behaviour over days is visible.

**What does transfer, with reasonable confidence:** the CPU-versus-wall split under RTT (§3),
because it is a property of the driver and the event loop rather than of the hardware; the
relative cost of query shapes (§2), especially devicestatus; files-per-tenant and the shape
of the A′ failure (§4); and the ordering of the three deployment options (§6), which holds
across every RTT tested and would need CPU-per-operation to rise by roughly 4× before A or B
became competitive on process count.

## Reproduction

```bash
docker run -d --name nsbench-mongo --cap-add=NET_ADMIN --ulimit nofile=64000:64000 \
  -p 27099:27017 mongo:7 --replSet rs0 --bind_ip_all
docker exec nsbench-mongo mongosh --eval 'rs.initiate({_id:"rs0",members:[{_id:0,host:"127.0.0.1:27017"}]})'

cd tools/mt-bench
node dbloop.js load 50           # ~190 s
node dbloop.js all  50           # query shapes, cycle, cold wake, loop delay

docker exec nsbench-mongo tc qdisc add dev eth0 root netem delay 5ms    # 10 ms RTT
RTT_LABEL=rtt10ms node dbloop.js all 50
docker exec nsbench-mongo tc qdisc change dev eth0 root netem delay 25ms # 50 ms RTT
RTT_LABEL=rtt50ms node dbloop.js loopdelay 50
docker exec nsbench-mongo tc qdisc del dev eth0 root

node nsfiles.js 200 50           # EXP-MT-040b, namespace cost, database-per-tenant
node shared-tenant.js 400 100    # EXP-MT-011b, one database + tenant discriminator

docker run -d --name nspg -e POSTGRES_PASSWORD=poc -p 15433:5432 postgres:16-alpine \
  -c wal_level=logical -c max_replication_slots=10 -c max_connections=300
cd pgfeed && npm install pg
node pgfeed.js all 400           # EXP-MT-057, RLS + change feed
node fanout.js  all 32           # EXP-MT-058, fan-out to subscribers
node notify-scale.js scale       # EXP-MT-059, throughput vs listener count
node notify-scale.js ceiling     # EXP-MT-059, serialisation limit
# pgbouncer arm needs a transaction-mode bouncer on :16432 — see §10.3
node notify-scale.js bouncer
docker rm -f nspg
RTT_MS=10 node deployment-cost.js 10000
```

To reproduce §4's crash deliberately, omit `--ulimit` and load past ~21 tenants.
