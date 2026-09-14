# What sets K: residency, the load cycle, and two quadratics

**Experiments**: EXP-MT-035 (resident cost against real `ddata`), EXP-MT-003 (residency
tiering), EXP-MT-004 (stateless rebuild), EXP-MT-005 (tenants per process),
EXP-MT-028 (adaptive merge/delta, extended)
**Date**: 2026-09-14
**Harness**: `tools/mt-bench/residency.js`, `tools/mt-bench/cycle-fix.js`; raw results in
`tools/mt-bench/results/exp-mt-035.json`
**Under test**: `cgm-remote-monitor` `origin/dev` @ `a8888f0d`, real `lib/data/ddata.js`
and `lib/data/calcdelta.js`
**Environment**: Node v24.15.0, Linux, shared development machine, **no database in the
loop** — these are event-loop CPU and heap measurements, not capacity results
**Confidence**: **measured** (committed scripts, re-run on a second pass, headline numbers
reproduced within 4 %)

Answers the question put to
[the multitenancy discussion](../30-design/nightscout-multitenancy-discussion-2026-09-09.md)
§5: of candidate architectures **B** (context per tenant, resident), **C** (B plus residency
tiering), **D** (stateless, storage-resident) and **E** (K tenants per process, M
processes) — which to commit to, and what order K and M take.

---

## Executive summary

**The architecture question is nearly decided by the measurements, and not in the way the
axis was framed.**

1. **Memory is not the constraint, and was never close.** A fully-processed real `ddata`
   tenant costs **1,204 KB resident** — *less* than §7.4's synthetic 2.2 MB, and stable from
   N=50 to N=300. At a 4 GB heap that is ~3,470 resident tenants per process.
2. **The load cycle is the constraint, and it is ~8× worse than anything recorded so far.**
   One incremental cycle for a typical 600-treatment tenant costs **9.5 ms p50 / 12.6 ms
   p99** of event-loop time. Prior harness numbers said 0.03 ms.
3. **The 0.03 ms was a fixture defect, not a result.** `tools/mt-bench/gen.js` gives every
   document the same `_id` (`'a'.repeat(24)`). Both hot loops break on first match, so the
   quadratics collapse to linear and were never exercised. **Every number derived from that
   fixture understates the merge and delta paths**, §7.5's "typical sizes are fine" row
   included.
4. **Two quadratics set K, and one of them was never identified.** `processDurations`
   (`ddata.js:198-247`) is quadratic *twice over* and accounts for **63 %** of the cycle;
   `calcDelta`'s treatment scan accounts for **34 %**. §2.1 lists three cost centres and
   `processDurations` is not among them.
5. **Fixing both is worth 6.3× at typical size and 27× at heavy size**, verified
   output-equivalent. That moves K by an order of magnitude — **K is set by code quality,
   not by architecture.**
6. **So: C, on top of B, with E as deployment shape — and E's M is small.** With the fixes,
   a realistic 10 000-tenant hoster needs ~2 application shards for capacity. Sharding is
   therefore justified by blast radius, rolling upgrades and noisy-tenant relocation — **not
   by capacity**, which is what §5 suspected and this measures.
7. **D is not competitive, for a reason that also indicts B.** A full stateless rebuild
   costs **10.8 ms** — statistically the same as one *incremental* cycle at 9.5 ms. Today's
   incremental path buys almost nothing over recomputing from scratch, because the quadratics
   run in full regardless of how little changed. After the fixes the incremental path is
   7× cheaper than rebuild, and D loses properly.

---

## 1. The harness defect, first

`gen.js` builds every document with `_id: 'a'.repeat(24)`. Both hot loops are written as
"scan until the ids match, then break":

```js
// calcdelta.js nsArrayTreatments
for (j = 0; j < m; j++) { oo = oldArray[j]; if (no._id === oo._id) { found = true; ... break; } }
```

With identical ids the inner loop exits at `j = 0` every time. The O(n²) scan becomes O(n),
and a benchmark built on that fixture measures a code path that does not exist in
production. Re-measuring the delta amplifier both ways, at three sizes:

| n treatments | ids | nested scan | Map-indexed | verdict |
|---:|---|---:|---:|---|
| 600 | identical | 0.568 ms | 0.545 ms | a wash — **the published result** |
| 600 | **distinct** | **1.369 ms** | **0.507 ms** | indexed wins **2.7×** |
| 2 000 | identical | 1.880 ms | 1.802 ms | a wash |
| 2 000 | **distinct** | **11.717 ms** | **1.751 ms** | indexed wins **6.7×** |
| 5 000 | identical | 5.005 ms | 4.611 ms | a wash |
| 5 000 | **distinct** | **66.391 ms** | **4.389 ms** | indexed wins **15×** |

**§7.5's conclusion needs splitting in two, because it blended two different functions:**

- **The delta (`nsArrayTreatments`) should just be indexed.** There is no crossover at any
  size measured. §7.5's "the fix is over 3× slower at typical sizes, so make it adaptive" is
  an artifact of the fixture.
- **The merge (`idMergePreferNew`) should be left alone**, and §7.5 is right about it — but
  for a reason it did not state. Its second argument is the *incremental batch* (~3
  documents), so the scan is O(n×3), never quadratic. Re-measured with distinct ids at 600
  old / 3 new: nested 0.031 ms vs indexed 0.053 ms; at 5 000 / 3: 0.144 ms vs 0.404 ms.
  Building a Set costs more than scanning three items. **Nested wins under both id regimes.**

A first attempt at a "distinct id" generator in `residency.js` was itself degenerate — an
LCG whose low bits cycled, yielding 16 distinct values from 5 000 calls. It is now a
monotonic counter in hex, asserted distinct. **Recorded because the failure mode is the
same one that produced the original defect, and it is invisible in the output.**

## 2. Memory — EXP-MT-035

Marginal cost per tenant, measured as `heapUsed + external` delta with forced GC, sweeping
to N=300, distinct ids throughout.

| Arm | What is held | Per tenant @N=300 | vs resident |
|---|---|---:|---:|
| `raw` | `gen.js`-shaped fixture in a `Map` (reproduces §7.4's method) | 1,278 KB | 1.06× |
| **`resident`** | **real `ddata`: processed clone, 8 derived arrays, retained client projection** | **1,204 KB** | 1× |
| `alarm` | last SGV, direction, delta, thresholds, ack/snooze state | **0.6 KB** | **1/2,007** |

Three results:

1. **EXP-MT-035 answers yes, favourably.** §7.4's 2.2 MB/tenant not only survives the real
   `ddata`/`processTreatments` path, it *improves* to 1.18 MB — matching §2.7's independent
   ~1.2 MB estimate. The synthetic arm was pessimistic because `JSON.parse` compacts the
   object graph that the raw fixture holds loosely.
2. **The per-tenant figure is flat.** 1,206 → 1,204 KB from N=25 to N=300; no super-linear
   term appears. Memory scales as expected.
3. **The hot/cold ratio is 2,000×**, which is what makes §5C tractable. §7.4.1 argued
   `ddata` must split into an alarm-critical slice that survives eviction and a display slice
   that does not; the alarm slice measures at **0.6 KB**. Ten thousand cold tenants cost
   ~6 MB — alarm coverage for an entire hoster fits in the noise of one process.

## 3. The load cycle — and where it goes

One incremental cycle, as `dataloader` performs it: process the new documents, merge them,
re-derive the treatment arrays, rebuild the client projection, diff it. 600-treatment
tenant, distinct ids, 400 iterations, first fifth discarded as warm-up.

```
per-cycle breakdown (mean of 200):
  process         0.029 ms    0.3%   processRawDataForRuntime on the new batch
  merge           0.057 ms    0.6%   idMergePreferNew x3
  treatments      5.983 ms   63.3%   processTreatments  <-- not in §2.1's cost centres
  projection      0.203 ms    2.1%   dataWithRecentStatuses
  delta           3.184 ms   33.7%   calcDelta
  TOTAL           9.457 ms
```

**`processDurations` (`ddata.js:198-247`) is quadratic twice over:**

```js
treatments = treatments.filter((t, index, self) =>            // O(n^2) dedup
  index === self.findIndex(x => x.mills === t.mills));
...
treatments.forEach(function (t) {                              // O(n^2) overlap cut
  if (t.duration) { treatments.forEach(function (e) { cutIfInInterval(t, e); }); }
});
```

It runs on every load, on each filtered treatment subset. Measured in isolation, with every
event carrying a duration (the Loop/AAPS temp-basal case):

| temp basals | `processDurations` | ms / n² × 10⁶ |
|---:|---:|---:|
| 100 | 0.379 ms | 37.9 |
| 300 | 1.523 ms | 16.9 |
| 600 | 4.614 ms | 12.8 |
| 1 200 | 19.322 ms | 13.4 |
| 2 400 | 88.902 ms | 15.4 |
| 5 000 | **343.481 ms** | 13.7 |

The constant `ms/n²` from 600 upward confirms the quadratic. **600 temp basals is not a
tail case**: §2.2's 60-hour treatment retention over a 5-minute temp-basal cadence is ~720.
The typical Loop or AAPS site sits in the middle of this table, and a long-history site at
the bottom of it — **a 343 ms event-loop stall per load cycle, on single-tenant Nightscout
today.**

## 4. The fix, and what it is worth — EXP-MT-028 extended

`processDurations` replaced by a sorted forward scan (dedup via `Set` on `mills`; sort by
`mills`; for each event with a duration, scan forward only while the next event starts
before the current end). Semantics-preserving by construction: `cutIfInInterval` only fires
when `base.mills < end.mills`, so only later events can act, and durations shrink
monotonically under cutting, so re-reading the bound each step visits exactly the pairs that
can matter. `calcDelta`'s treatment scan replaced by a `Map` lookup.

Output equivalence is asserted against the stock implementation on a mixed fixture including
zero-duration end events: **MATCH** at every size run.

| treatments | current p50 | +delta indexed | **+both** | speedup |
|---:|---:|---:|---:|---:|
| 300 | 2.734 ms | 2.618 ms | **1.033 ms** | 2.6× |
| 600 | 9.541 ms | 7.753 ms | **1.523 ms** | **6.3×** |
| 1 200 | 31.934 ms | 27.382 ms | **2.518 ms** | 12.7× |
| 2 400 | 121.178 ms | 101.689 ms | **4.477 ms** | **27×** |

Indexing the delta alone buys only ~19 %, because `processDurations` dominates. **The two
fixes are not independent and should not be scheduled separately.**

## 5. Solving for K

K is bounded by whichever binds first:

```
K_memory = heap_budget / resident_bytes_per_tenant
K_cpu    = (utilisation_target x 1000 ms/s) / (cycle_ms x loads_per_second)
```

Using a 30 % event-loop utilisation target (leaving headroom for GC, request handling and
socket fan-out), an *active* tenant loading once per 5 s (`UPDATE_MAX_WAIT` under a write
stream), and an *idle* tenant on the 60 s heartbeat:

| Tenant profile | code | K (active) | K (idle) | K_memory @4 GB |
|---|---|---:|---:|---:|
| typical, 600 treatments | current | **157** | 1 885 | 3 471 |
| typical, 600 treatments | **+both fixes** | **987** | 11 811 | 3 471 |
| heavy, 2 400 treatments | current | **12** | 148 | 3 471 |
| heavy, 2 400 treatments | **+both fixes** | **335** | 4 011 | 3 471 |

**K_cpu is below K_memory in every row**, by between 3× and 280×. §7.4.1's inferred claim —
that tiering moves the binding constraint from memory to the load cycle — is now measured,
and it holds with room to spare. With the fixes, K_cpu and K_memory come within the same
order of magnitude for the first time, which is when residency tiering starts to pay for
itself on memory as well as on cycles.

**And M.** A hoster with 10 000 tenants at a 15 % concurrent-active fraction, 5 % of active
tenants being heavy:

| | work per second | M (application shards) |
|---|---:|---:|
| current code | 4 537 ms/s | **~16** |
| +both fixes | 500 ms/s | **~2** |

**Two functions are worth a factor of eight in M.** That is the single most decision-relevant
number here: at M≈2 the sharding in §5E is justified by blast radius, rolling upgrades and
the ability to relocate a noisy tenant — **not by capacity**. A design that shards for
capacity reasons before fixing the quadratics would be buying hardware to run an O(n²) loop.

## 6. K is different per component, and that is the real argument for splitting

The user question was also *across which areas of the app*. K is not one number, and each
component binds on a different resource:

| Component | Binding resource | Order of K | Measured here? |
|---|---|---|---|
| **APP shard** (`ddata`, plugins, delta) | event-loop CPU | **10²–10³ active tenants** | **yes** |
| **REALTIME** fan-out | open socket count, not tenants | 10⁴ sockets | no — EXP-MT-045 |
| **ROUTER / AUTH** | stateless; request rate | effectively unbounded | no — EXP-MT-041 |
| **VCPOOL** (vendor connectivity) | **vendor rate limit per egress IP** | plausibly 10¹–10² accounts | no — EXP-MT-048/051 |
| **STORAGE** | connections, index locality | — | no — EXP-MT-040 |

**The components should be split where their K values differ by an order of magnitude, not
because a split is cloud-native.** On present evidence the APP shard and the vendor-
connectivity pool are the pair most likely to differ — vendor connectivity is bounded by
somebody else's rate limiter, which no amount of code quality moves — and that is the split
worth doing first. Everything else is speculation until EXP-MT-045/048/051 run.

## 7. What this says about B, C, D and E

- **B (resident context per tenant) is the right substrate** and is cheaper than believed:
  1.18 MB/tenant against real code.
- **C (B plus tiering) is what makes a hoster's numbers work**, and the alarm slice that
  §7.4.1 requires measures at 0.6 KB — a 2 000× ratio. The hard part was never the wake cost
  (§7.1: 2.5–4 ms); it is the policy and the alarm split, and the split is now sized.
- **D (stateless) loses, and the margin is the finding.** A full rebuild is 10.8 ms against
  9.5 ms for an incremental cycle — today, *that is not a margin at all*, which is itself an
  indictment of the incremental path. After the fixes the incremental cycle is 1.5 ms and D
  loses by 7×. **D only looks competitive while the resident path is broken.**
- **E is the deployment shape, not an alternative**, exactly as §5 says — and M is small
  once the quadratics are gone. Commit to E for operational reasons, size it from K, and do
  not let it become the answer to a performance problem that is really two functions.

**Recommended commitment: B + C as the runtime, E as the deployment shape, D rejected** —
with the explicit condition that the quadratics are fixed first, because they move K by
~6× and M by ~8× and nothing about the architecture choice does.

## 8. What is not measured, and matters

1. **Plugin execution is absent from the cycle.** §2.3 shows every load is followed by
   `plugins.setProperties(sbx)`, `checkNotifications(sbx)` and `notifications.process(sbx)`.
   None of it is in the 9.5 ms. **Real K will be lower — possibly much lower — and this is
   the most important next measurement.**
2. **No database in the loop.** Every figure is local CPU and heap. §2.3's ~14 DB operations
   per load are not included, and EXP-MT-026 should establish whether network RTT dominates
   before K is quoted as capacity.
3. **No socket fan-out, no HTTP request handling, no GC pressure at N.** The utilisation
   target of 30 % is a placeholder for exactly these, not a measurement of them.
4. **The load-rate assumption drives K linearly.** "Active = one load per 5 s" is taken from
   `UPDATE_MAX_WAIT`, not from observed uploader behaviour. §8.1's replayable traces would
   replace it.
5. **The treatment fixture is homogeneous** — 600 Temp Basals. Real sites mix 28 event types
   with different `duration` semantics, and `processDurations` cost depends on how many
   events carry durations.
6. **The proposed `processDurations` replacement is asserted equivalent on a fixture, not
   proved.** It needs the existing suites plus adversarial cases (nested overlaps, zero and
   negative durations, identical `mills`, profile-switch cutting) before it is a patch.

## 9. Reproduction

```bash
cd tools/mt-bench
node --expose-gc residency.js resident 300 --unique   # memory, real ddata
node --expose-gc residency.js alarm    300 --unique   # cold-tier slice
node --expose-gc residency.js cycle    400 --unique   # incremental cycle
node --expose-gc residency.js rebuild  200 --unique   # stateless (§5D)
node cycle-fix.js 300 600                             # current vs indexed vs both
```

Raw results: `tools/mt-bench/results/exp-mt-035.json`.
