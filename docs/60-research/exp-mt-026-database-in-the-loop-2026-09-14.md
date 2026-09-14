# EXP-MT-026: a real database in the loop

**Experiments**: EXP-MT-026 (query cost, load cycle, cold wake, event-loop behaviour under
RTT), **EXP-MT-040b** (where database-per-tenant breaks)
**Date**: 2026-09-14
**Harness**: `tools/mt-bench/{dbloop,nsfiles,latency-proxy}.js`; raw results in
`results/exp-mt-026*.json` and `exp-mt-040b.json`
**Under test**: MongoDB **7.0.43**, single-node replica set in Docker, `mongodb` driver
5.9.2 (the version `cgm-remote-monitor` pins), real `indexedFields` index set, queries
transcribed from `lib/data/dataloader.js`. Shape: **database-per-tenant on one cluster** —
§6.7's A′ rung.
**Environment**: Linux, 16 cores, 62 GB, Node v24.15.0. **A laptop.** See §L before quoting
anything.
**Confidence**: **measured**, with the scope limits in §L. RTT arms use `tc netem` inside the
database container — kernel-level delay, not a userspace shim.

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
7. **And probing that deliberately found the more important number: `mongod` holds ~3.8 MB of
   non-evictable RSS per tenant database containing *zero documents*** — more than the 2.65 MB
   of app-side resident state that database-per-tenant is supposed to save, and unlike it,
   impossible to evict. **§6.7's A′ rung relocates per-tenant memory rather than deleting
   it.** §4.1.

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
cost model uses.** An earlier pass of this report nearly published the sequential number as
evidence that RTT triples CPU cost. It does not; the measurement method did.

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

- **PostgreSQL + RLS.** The whole engine half of §6.7's ladder is unmeasured with a database
  in the loop. The `rls-poc` figures remain the only evidence there.
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

node nsfiles.js 200 50           # EXP-MT-040b, namespace cost
RTT_MS=10 node deployment-cost.js 10000
```

To reproduce §4's crash deliberately, omit `--ulimit` and load past ~21 tenants.
