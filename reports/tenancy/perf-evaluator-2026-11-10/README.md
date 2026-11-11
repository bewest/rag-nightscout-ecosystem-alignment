# Perf lane EV: the evaluator works on change and due time, not a per-tenant one-second poll (2026-11-10)

*Contributor-facing measurement record for decision
[cost-proportional-to-activity](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#cost-proportional-to-activity),
stage 1. Captured 2026-11-10 20:48–23:20 local time; not edited after capture. Synthetic tenants and data only.
Figures are labelled **reproduced** (run here, output in [`runs/`](runs/)) or **derived** (arithmetic on
reproduced figures). Every run shared the host with other lanes; load averages are quoted per run.*

## Anchors

| what | value |
|---|---|
| base | `codex/evaluator-partition-20261110` at `cb1b751d` (no hygiene commit on top when the lane started) |
| change | branch `codex/perf-evaluator-20261110`, head `d0cf97d1` on `a335be89` (the change), worktree `externals/work/crm-perf-evaluator-20261110` (own `npm ci`). Not pushed. Labs, bench and controls ran on `a335be89`; `d0cf97d1` only makes the reconcile signature opt-in (realtime shares reconcile and no longer pays for it; the evaluator still requests it) and adapts two more tests |
| base for comparisons | detached worktree of `cb1b751d` sharing the change worktree's `node_modules` (same lockfile) |
| alignment `main` when written | `8af6d057b9ac5c40fc0ea28c5001fee55784e6f7` |
| PostgreSQL | dedicated container `ns-pev-pg`, `postgres:16` (16.15), `pg_stat_statements` in the `postgres` database only |
| Node | v22, host 16 logical cores (i7-11800H), 64 GB |
| harnesses | [`tools/tenancy/perf-evaluator/equivalence.cjs`](../../../tools/tenancy/perf-evaluator/equivalence.cjs), [`bench.cjs`](../../../tools/tenancy/perf-evaluator/bench.cjs) (this commit) |

## What changed (file:line at `a335be89`)

The two `setInterval`s that ran an acquisition and a time-only cycle for every tenant every second
(`lib/server/serve/evaluator-runtime.js:271-272` at the base; `:240-241` at the bench baseline's head) are
gone. One backstop interval remains (`evaluator-runtime.js:401`); everything else is per tenant and on demand.

| part | mechanism | where |
|---|---|---|
| backstop (D6 shape) | every `recoveryIntervalMs`: one pool read, then per admitted tenant its activity, configuration identity and change signature; acquire only if the signature differs from the one the last successful acquisition processed | `evaluator-runtime.js:288` `check`, `:316` `pass` |
| change signature | `(last_stamp, row count, digest of identity/xmin of every admitted row)`, one statement under the tenant's RLS binding; reconcile records the same signature inside its snapshot, so the processed signature is exactly what the evaluator read | `lib/storage/postgres-durable-replay.js:68` (`signatureSql`), `:162` (in reconcile), `:169` `signature()` |
| processed checkpoint | the signature of the last successful acquisition, held in the runtime (`state.processed`, `evaluator-runtime.js:187`). It is set only after the evaluation published, unlike the `tenant_consumer_checkpoint` row, which reconcile commits before evaluation (its own comment: "a snapshot floor, not evaluation/delivery completion"). `inputCheckpoint` (the published output's `checkpoint`) is its `stamp` half | |
| wake seam | `runtime.wake(tenant, { stamp })`: a stamp at or below the processed floor is a duplicate (no work); a higher stamp acquires; no stamp checks the signature. Exposed as `wake` on the role (`lib/server/serve/evaluator-preview.js`) for a later slot reader | `evaluator-runtime.js:338` |
| in-flight cycles | a check that meets a running cycle re-checks once when it finishes (shared promise), never skips and never adds a blind acquisition | `evaluator-runtime.js:297` |
| due-time timer | per tenant, one `setTimeout` at the earliest instant a plugin's time comparison can flip, or at `at + timeIntervalMs` (the bounded slow timer) while the output depends continuously on time | `evaluator-runtime.js:91` `arm`; rules `lib/data/evaluator-due.js:54` |
| eviction (optional `evictAfterMs`) | an unchanged tenant's component drops its retained input and plugin context; output, processed signature and timer stay; its next cycle is a full acquisition | `evaluator-runtime.js:113`, `lib/data/tenant-projection-evaluator.js:128` |

`recoveryIntervalMs` is now the backstop interval and `timeIntervalMs` the slow-timer bound. With the deployed
values (both 1000, `deploy/multitenant/config.js:123-126`) a tenant with an active alarm is still evaluated every
second; raising `timeIntervalMs` is an operator choice measured below, not made here.

### The change stamp: the clock floor is not enough (reproduced)

The tenant write clock floor (`tenant_write_clock.last_stamp`) advances only when a transaction allocates a
server date (`lib/storage/postgres-write-clock.js:74`). Two kinds of supported write do not:

- **hard deletes**: v3 permanent delete, prune/autoPrune and v1 delete reach `DELETE ... RETURNING` in
  `lib/storage/postgres-entries-write.js` (`remove`, used by `deleteMany` `:359` and `deleteManyOr`) with no
  `srvDates.next()`;
- **unstamped domains**: the `activity` collection carries no `srvModified`.

The existing proof `tests/tenant-current-state-recovery-proof.integration.test.js` ("finds quiet canonical
absence and unstamped activity through the explicit recovery backstop") deletes an entry and inserts an activity
row: floor unchanged **and** row count unchanged. A floor-plus-count signature failed it (reproduced during this
lane). Hence the per-row version digest. Decision
[m5-bounded-snapshot-reconciliation](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#m5-bounded-snapshot-reconciliation)
already requires recovery "independent of floor movement"; this is the same fact seen from the backstop.

Cost of that coverage: the signature scans the tenant's admitted rows (bounded by `maxRows`): 0.25–0.79 DB-ms
per check at 576 rows (reproduced, `runs/bench.txt` per-evaluation `signature`).

### Due-time rules (each from the plugin's own comparison)

`lib/data/evaluator-due.js`: timeago warn/urgent onset (`timeago.js` `isStale`, strict `>`) and the "Last received"
display boundaries while stale (`calcDisplay` resolvers); 10-minute reading recency for simplealarms/errorcodes
(`<`) and ar2 (`>`); `sbx.isCurrent` 15 minutes (bwp); cage/sage/iage/bage threshold hours and the end of their
20-minute notification window, read from the same `ddata` lists the plugins use; treatmentnotify 10 minutes (wall
clock); bwp recent carbs 60 minutes; openaps offline end; device-status look-back (24/48 h) and treatment window
(60 h) exits; upbat 30 minutes; loop/openaps recent selection (`warn/2`) and 6 h window; pump clock warn/urgent and
pump status window (`2 × urgentClock`); loop/openaps status warn/urgent from `lastOkMoment`/`lastLoopMoment`; any
record dated in the future reaching now.

**Not expressible as an instant → bounded slow timer** (say so per the brief): every alarm message carries IOB/COB
lines that decay continuously and humanized times (`buildDefaultMessage`, ar2/loop/openaps `from`/`formatAgo`);
bwp while the reading is current; xdripjs state notices on the wall clock; pump quiet-night hours in the profile's
time zone. These keep a tenant on `timeIntervalMs` only while the condition holds; they do not undermine the
model, because they hold only for tenants with an active alarm or fresh data.

## Checks (reproduced)

| check | result |
|---|---|
| affected suites (evaluator-\*, tenant-activity, tenant-durable-replay, pool-membership, notification-producer, tenant-projection-evaluator, current-state-recovery with `NS_M5_CURRENT_STATE_PROOF_TEST=1`, all opt-ins on) | base `cb1b751d`: 181 passing, 0 failing; `a335be89` + the two new suites: 193 / 0; `d0cf97d1` + new suites + tenant-maintenance-window: **213 passing, 0 failing** |
| unit tier (`scripts/test-tiers.js run unit`) | `a335be89`: 3222 / 2 failing (realtime's reconcile fake and `tenant-maintenance-window` driving the removed interval), fixed in `d0cf97d1`: **3224 passing, 0 failing** |
| tests adapted to the model (no assertion weakened) | `evaluator-preview-runtime` (one backstop schedule, per-tenant slow timer), `tenant-activity` (time trigger is per tenant), `tenant-durable-replay` fake (answers the signature query), current-state recovery proof (waits for convergence and publication instead of "3 more cycles", since an unchanged tenant now runs none) |
| new | `tests/evaluator-wake.integration.test.js` (7, actual PostgreSQL), `tests/evaluator-due.test.js` (5, actual plugins) |
| eslint `lib` | 0 errors (54 warnings, none new in changed lines) |
| `test:tiers` | ok (632 files, 8 tiers) at `d0cf97d1` |
| `test:write-boundary` | all 9 adapter entry points checked |
| evaluator-partition lab (`tools/tenancy/evaluator-partition/run.cjs`) | change 20/23, base 20/23 on this host, **the same three failing** (2→3 duplicate logical effect, SIGKILL restart over a stale socket `SOCKET_IPC_PATH_EXISTS`, kill-restart measure). Lane EP recorded 22 green; these three are not introduced here (`runs/partition-*.txt`) |

Two defects found and fixed during the lane, each by an existing or new test going red:
1. the backstop skipped a tenant whose time-only cycle was in flight; with a 1 s slow timer and 1 s backstop they
   phase-locked and a new reading was never acquired (`evaluator-consumer-load` `CHANGED_READING_LATENCY`: latency
   `null` and 5081 ms; after the re-check: 132–487 ms over three runs);
2. a wake arriving just after a cycle resolved added a second acquisition (`EV_DUPLICATE_ONE_EVALUATION` 3 ≠ 2).

### Durable-event contract controls (actual runtime, component and PostgreSQL)

| control | green | break-it (red, exact symptom) → restored |
|---|---|---|
| lost wake: backstop finds the change within one pass | `EV_LOST_WAKE_BACKSTOP` | backstop `pass()` returns at once: `111 !== 222` (stale reading kept); hard-delete and unstamped tests also red → restored 7/7 |
| duplicate delivery: same stamp twice, then a stampless wake and a pass | one evaluation, one revision, `duplicateWakes: 1` | (found defect 2 above) |
| restart replays from the checkpoint | new runtime sees a write made while down | |
| hard delete re-evaluated (floor unchanged, asserted) | `EV_HARD_DELETE_REEVALUATED` | signature = floor only: `222 !== 111` (deleted reading still shown); unstamped update `1 !== 2` → restored 7/7 |
| unstamped in-place update re-evaluated | `EV_UNSTAMPED_UPDATE_REEVALUATED` | same break |
| idle tenant: no cycle | 5 passes → 5 checks, 5 unchanged, 0 cycles | |
| eviction: same output after reacquisition | same content digest | |

## Clinical equivalence (reproduced, `runs/equivalence-*.txt`)

The actual component (real views, server plugins, projection reads on PostgreSQL) over one recorded synthetic
13-hour timeline (CGM and loop/pump device status every 5 min with lows, highs, a 1 h gap and a 4 h gap; site,
sensor, insulin and battery changes; boluses, carbs, a meter reading), the wall clock pinned to the evaluation
instant (`tests/lib/views-replay/clock`). Base: a time-only cycle every 1000 ms (46,801 cycles). Due: cycles only at
due instants or on the slow timer. Writes are acquired at the same whole second in both (write latency is measured
on the runtime, below). Compared from the evaluator's own `requested` rows.

| plugin set | slow timer | alarm set (`plugin, level, group, title`) | full content (messages) | cycles |
|---|---|---|---|---|
| 22 plugins incl. bwp, timeago, simplealarms, ar2, cage/sage/iage/bage, pump, loop, upbat, treatmentnotify | 1000 ms | **PASS**: 52 transitions identical; due never later than base, at most 999 ms earlier | 245 = 245 in order; 3 transitions 1 ms after the base tick (slow-timer phase) | 46,917 (bwp keeps an alarm active almost throughout) |
| same | 60000 ms | **PASS** (52, ≤ 999 ms earlier) | 156 of 245 (message text refreshes within 60 s) | 1,032 (45× fewer) |
| without bwp | 1000 ms | **PASS** (52) | 245 = 245; 3 at +1 ms | 29,344 (1.6×) |
| without bwp | 60000 ms | **PASS** (52) | 156 of 245 | 792 (59× fewer) |

Gates from the brief: stale-data alarm fires at the same time (timeago transitions within the base's 1 s
quantum); age alarms at their thresholds and window ends (cage 2/3/4 h, sage 5/6/7 h, iage 6/7/8 h, bage 9/10/11 h
in this timeline); repeat cadence, ack and snooze unchanged (the producer's repeat clock and ack/snooze are not
touched; `evaluator-consumer-load` repeat-on-heartbeat and ack-silence, the partition lab's repeat gates and
`notification-producer*` pass).

**Control C3, timeago due dropped** (`runs/control-timeago-dropped.txt`, 5 h, slow 60 s): `FAIL
ALARM_SET_EQUIVALENT` — stale-data warn `29001 ms late` (base 03:10:01.000, due 03:10:30.001), urgent `29000 ms
late`; restored.

A first lab run without the pinned wall clock showed a content difference in loop/pump messages: those plugins
format "Last Loop: 31m ago" with `moment()` (wall clock), so a lab in virtual time diverges. Not a defect of the
change; the lab now pins the clock.

## Cost (reproduced, `runs/bench.txt`)

In-process bench: actual runtime and component, change replay through a tenant-RLS reader role (`max: 4`, as
deployed), deployed plugin set (`bgnow delta direction simplealarms treatmentnotify`), each tenant seeded with 24 h
of entries and device status (288 + 288 rows). **No operation window** (its admission queries are lane (3) of the
decision) and no notification consumers, so these are the evaluator's own marginal costs, not a deployment's.
Backstop 1000 ms, slow timer 1000 ms. Load averages 1.5–11.

### Per tenant, idle (no writes, 60 s)

| N | code | evaluations / tenant-min | queries / tenant-min | DB-ms / tenant-min | evaluator CPU-ms / tenant-min | PostgreSQL CPU | evaluator CPU |
|---|---|---|---|---|---|---|---|
| 1 | base | 120 | 6,107 | 1,529 | 6,666 | 6.5% | 11.1% |
| 1 | change | **0** | **240** | **51** | 238 (fixed overhead at N=1) | 0.4% | 0.4% |
| 10 | base | 120 | 6,065 | 1,213 | 3,968 | 49.9% | 66.1% |
| 10 | change | 0.9 | 280 | 32 | 76 | 2.0% | 1.3% |
| 100 | base | 32 (saturated; wanted 120) | 1,622 | 224 | 684 | 98.2% | 113.9% |
| 100 | change | 0.77 | 275 | 25 | 42 | 14.3% | 7.0% |
| 1000 | base | 2 (saturated) | 109 | 23 | 70 | 92.7% | 116.9% |
| 1000 | change | 0.41 | 263 | 40 | 40 | 170.7% | 66.0% |

Queries per idle tenant per minute: **~6,100 → ~260** (23×) where the base keeps up (N ≤ 10). The remaining
~260 are the backstop: one signature check per tenant per second, 4 statements each (BEGIN, `set_config`, the
signature, COMMIT), because RLS allows no cross-tenant statement for this role. The idle evaluations (0.4–0.9 per
tenant-minute) are due times from the 24 h windows: one entry and one device status leave the window every 5 min.

DB-ms at idle, whole database: change 0.9 / 5.3 / 42 / 664 DB-ms per second at N = 1 / 10 / 100 / 1000;
base 25.5 / 202 / 373 / 390 (the base stops scaling because the evaluator saturates).

### Real cadence (one entry + one device status per tenant every 5 min)

| N | code | writes | evaluations / tenant-min | write → evaluation latency p50 / p95 / max ms |
|---|---|---|---|---|
| 1 | base / change | 1 / 1 | 121 / 0.49 | 855 / 864 |
| 10 | base / change | 4 / 4 | 120 / 0.20 | 877, 885 / 910, 912 |
| 100 | base | 40 | 31 | 3,630 / 6,429 / 6,894 |
| 100 | change | 40 | 0.44 | **867 / 908 / 909** |
| 1000 | base (60 s) | 200 | 2.3 | 36,885 / 53,838 / 55,598 (133 of 200 seen) |
| 1000 | change (300 s) | 1000 | 0.44 | **767 / 1,283 / 1,773** |

Latency is bounded by the backstop interval (no wake source yet): the brief's "NOTIFY gives latency" is the next
stage.

### The capacity figures asked for (M7 capacity gate)

| figure | value | basis |
|---|---|---|
| **CPU-ms per evaluation**, acquisition, 24 h window, deployed plugins | **33.7 p50 / 38.7 mean** (N=10, load 1.5); 46–56 p50 at load 5–6 | reproduced, sequential, no concurrent work |
| CPU-ms per evaluation, time-only | **16.2 p50 / 18.3 mean** (N=10); 23–31 at load 5–11 | reproduced |
| CPU-ms per evaluation, 22-plugin set, ≤ 12 h window | 6–9 p50 (equivalence lab, smaller window) | reproduced |
| statements / DB-ms per evaluation | acquisition 60 / 8.9; time-only 44 / 3.0 | reproduced: a time-only cycle still runs every view's projection read on PostgreSQL (`lib/storage/postgres-projection-read.js:44`, `jsonb_to_recordset` over the retained input) |
| per-tenant change check | 4 statements, 0.25–0.79 DB-ms | reproduced |
| CPU-ms per tenant-minute, idle / real cadence | 40 / 35 (N=1000), 42 / 36 (N=100) | reproduced; at N ≤ 10 dominated by fixed process overhead |
| DB-ms per tenant-minute, idle / real | 25–40 / 27–34 | reproduced |
| MB resident per tenant (24 h window) | **1.9–2.3** (N=100, 1000: RSS after boot minus RSS before, after GC) | reproduced |
| eviction | 1000 of 1000 evicted after 30 s unchanged; RSS 2,421 MB at boot → 2,150 MB after (−11%); V8 heap not measured, so the memory released is **UNMEASURED**. Evicted tenants' due times still fire (they reacquire: 144 CPU-ms per evaluation in the evicted phase vs 79 resident) | reproduced; eviction output equality reproduced in `EV_EVICTION_SAME_OUTPUT` |
| 1,000 idle tenants | held: boot 28.5 s, evaluator 66% of one core, PostgreSQL 171%, 664 DB-ms/s | reproduced |

**What runs out first, and at about what N (derived):**
1. **One evaluator process, around 1,500 tenants**: CPU at ~40 ms per tenant-minute is one core at ~1,500, and
   resident memory at ~2.3 MB per tenant reaches the default V8 heap (~4 GB) near 1,700. Partitioned members
   (MT-EVALUATOR-PARTITION) divide both; eviction would cut memory only if the heap actually shrinks (unmeasured).
2. **PostgreSQL across all members, around 9,000 tenants**: the per-tenant signature check costs ~0.17% of a core
   per tenant at a 1 s backstop (171% at 1,000); 16 cores at ~9,000. It scales with tenants × backstop rate × rows
   per tenant, not with activity, and is the reason the decision's aggregate query matters.
3. Not reached and not measured here: the operation-window admission per transaction (bench baseline's largest
   idle cost) would multiply both 1 and 2 until lane (3) lands.

## Conflicts with decisions recorded after this lane started (stop-and-report)

The coordinator relayed
[change-stamp-definer-function](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#change-stamp-definer-function)
and [incremental-refresh](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#incremental-refresh) while this
lane ran. Neither is built here; both conflict with what was reproduced:

1. **A definer function returning `(tenant_id, last_stamp)` does not see hard deletes or unstamped (activity)
   writes.** Reproduced: control C2 (signature = floor only) leaves a hard-deleted reading on display
   (`222 !== 111`) and misses an unstamped update; the shipped M5 proof (delete + activity insert) fails the same
   way. Options for the maintainer: (a) make every supported write that changes evaluated input advance the clock
   floor (hard delete paths in `postgres-entries-write.js` `remove`, and the activity domain), so `last_stamp` is a
   complete signature and the shared function suffices; (b) the function also returns a per-tenant row-version
   digest (the scan this lane does per tenant, now in one statement); (c) keep `last_stamp` for latency and a slower
   per-tenant digest pass for absence. (a) is the cheapest at runtime and touches the API write path and the event
   payload's stamp (null today for hard deletes).
   Swap point for the join: the runtime compares opaque signatures (`evaluator-runtime.js:54` `validSignature`,
   `same`), obtained from `component.signature()` → `postgres-durable-replay.js:169`. A shared aggregate would
   replace the per-tenant read inside `pass()` (`evaluator-runtime.js:316`) with one call that returns signatures
   for the slice; `check()` already accepts any signature object.
2. **Incremental read saves little per evaluation, because the evaluation recomputes the whole window anyway.**
   Reproduced at N=10: acquisition 33.7 CPU-ms / 8.9 DB-ms; time-only (no change rows read at all) 16.2 CPU-ms /
   3.0 DB-ms and still 44 statements, because the views re-query the retained input through PostgreSQL every cycle
   and every plugin recomputes from the full window. An incremental read can remove at most the difference
   (~17 CPU-ms, ~6 DB-ms per acquisition, which at real cadence is one per tenant per 5 min). Hard deletes and
   unstamped writes also defeat `stamp > checkpoint` (point 1). The larger, per-evaluation cost is the
   projection-read path and the full plugin pass; that is where CPU-ms per evaluation can fall.

## UNMEASURED

- The role process under Compose/Kubernetes with the operation window and consumers (in-process bench only).
- V8 heap per tenant and the memory eviction actually returns.
- Backstop intervals other than 1000 ms (per-check cost is reproduced; the rate scales linearly, derived).
- 3,000 and 10,000 tenants.
- A quiet host: load averages 1.5–15 during runs.

## Resumed, 2026-11-11 (00:00–02:00 local): evaluation-gap gate, alert and readiness seam

*Appended after the coordinator relayed perf-db's restart-gap measurement (`codex/perf-db-20261110` `540d3998`,
[perf-db record, "Resumed"](../perf-db-2026-11-10/README.md)) and the readiness seam for
[readiness-serve-then-warm](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#readiness-serve-then-warm). The
sections above are unchanged.*

### Anchors

| what | value |
|---|---|
| lane branch `codex/perf-evaluator-20261110` | `3ac621a2` alert + serve boot; `374e7191` partition test; `8da2804a` bounded checks; head **`5ab35cad`** config parse cache. Not pushed |
| join scratch branch `codex/perf-evaluator-join-db-20261110` (worktree `externals/work/crm-perf-evaluator-join-20261110`) | lane merged with perf-db `540d3998` (`c812c5f0`), readiness wiring `91c5c2b4`, boot-protocol test `2ec72c4d`, check bound `6ce791fc`, head **`41f9179a`** (lane `5ab35cad` merged). Not pushed; for measurement and the join |
| gate harness | perf-db's `harness/start.sh` (1,000 tenants, `KEEP=1`) and `harness/eval-gap.js` unchanged; overlay `overlay-4e5a1051`; images `ns-pev-perf:<join head>` built by `deploy/multitenant/build.js`, label-checked, removed afterwards |

### What changed

**Lane (`5ab35cad`)**
- **Evaluation-gap alert**: `EVALUATOR_NOT_EVALUATED_WITHIN_BOUND` (`evaluationAlertMs`, default 60,000; evaluator
  config field of the same name). A tenant's evaluation is "confirmed current" by an acquisition, a time-only cycle, or
  a backstop check that found nothing changed; the alert fires once when the age since the runtime started or since the
  last confirmation exceeds the bound, and clears on confirmation. Paused, suspended and withdrawn tenants are exempt.
  It has its own watchdog schedule, so a stuck backstop still alerts. Exposed in `health()` (`tenants[].evaluatedAgeMs`,
  `tenants[].alert`, `alerts`) and in the evaluator inspection (`tenants[].evaluation: { ageMs, alert }`, an additive
  optional property of the `evaluator-inspection` contract).
- **Serve boot**: `boot: 'serve'` returns at once and acquires in the background, `bootConcurrency` at a time, warm
  tenants first (`isWarm`); the backstop leaves queued tenants to that queue. `'all'` is unchanged.
- **Bounded backstop**: checks and the acquisitions they start share `checkConcurrency` slots (default 4); the in-flight
  guard is per tenant (one stuck check holds only itself); a refused check waits for the next pass instead of
  acquiring.
- **Config parse cache**: `readCurrent` reuses the parsed evaluator config while the file's inode, size, mtime and ctime
  are unchanged.

**Join (`41f9179a`)**: the evaluator passes `NS_TENANT_READINESS` (default `serve`) and `NS_TENANT_STARTUP_CONCURRENCY`
to `tenant-startup.create` and to the runtime boot, with `isWarm` from a new `tenant-startup` `isReady(tenant)`;
`checkConcurrency` is the evaluator pool size (`NS_POOL_EVALUATOR_MAX`); `startup.health()` is in `health()` and the
inspection (`startup`, additive); the consumers' `prepare` tenant loop runs through perf-db's `settleLimited` at the
startup concurrency instead of one tenant after another (the first failure still refuses the boot). The role-booting
labs and the evaluator boot-protocol test run under `NS_TENANT_READINESS=all`, as perf-db did for the api's.

### Gate: per-tenant evaluation gap after an evaluator restart, 1,000 tenants (reproduced)

Same definition as perf-db: a tenant's first evaluation after the restart is its first window operation by an evaluator
backend after the container is healthy. Under the change, an unchanged tenant's backstop check is such an operation
and is exactly "confirmed current"; an acquisition is too.

| run | code | evaluator healthy after | within 60 s | 5 min | 15 min | 25 min | not within 25 min | p50 since restart | load avg |
|---|---|---|---|---|---|---|---|---|---|
| perf-db (reference) | polling evaluator, `540d3998` | 54.5 s | 16 | 143 | 424 | 700 | 300 | 10.8 min | 15.8 → 9.3 |
| 1 | join `ca50a4b5` (unbounded backstop) | 20.6 s | 22 | 129 | 286 | 506 | 494 | 12.8 min | 16.9 → 6.1 |
| 2 | join `6ce791fc` (bounded checks) | 12.5 s | 41 | 180 | 365 | 554 | 446 | 8.9 min | 3.9 → 4.4 |
| **3** | **join `41f9179a` (+ config parse cache), deployed settings** | 12.2 s | **511** | **668** | **928** | **999** | **1** | **46 s** | 4.8 → 5.8 |
| 3, diagnostic | same, consumers' per-tenant poll at 60 s instead of 1 s | 14.2 s | **996** | 1,000 | 1,000 | 1,000 | 0 | 26.6 s (max 73 s) | 5.8 → 6.0 |

Steady state after the diagnostic run (evaluator inspection, `runs/eval-gap-run3/inspect-steady-poll60.json`): all
1,000 tenants confirmed within the last 957 ms (p50 592, p90 891), no alert, no refusal code; evaluator 52% CPU,
511 MiB; PostgreSQL 310% (the per-tenant signature checks under the window, one per tenant per second).

**What each run found** (from the evaluator's own inspection on the live deployment):
- run 1: 817 tenants `EVALUATOR_WINDOW_REFUSED`. The backstop started every tenant's check at once: 1,000 window leases
  on a pool with a 5 s connect timeout; each refused check started an acquisition, feeding the herd. Fixed by bounded
  checks (`8da2804a`).
- run 2: 854 tenants `EVALUATOR_WINDOW_REFUSED`, all 1,000 alerting, evaluator ~125% CPU. Two causes: (a) every check's
  `readCurrent` re-parsed the whole configuration, all tenants included (O(N²) per pass), fixed by the parse cache
  (`5ab35cad`); (b) the notification consumers poll **every tenant every second** for `run` and for `retry`
  (`lib/server/serve/evaluator-consumers.js` `start`, `pollIntervalMs`/`retryIntervalMs` = 1000 in
  `deploy/multitenant/config.js`), each under an operation-window lease: about 2,000 leases a second at 1,000 tenants
  in the same role. The diagnostic (b) alone, polls at 60 s, gave 1,000 within 15 min before the cache.
- run 3: with both evaluator fixes, the remaining tail (p90 13.6 min, one tenant past 25 min) is (b): with the consumer
  polls at 60 s the gap closes to 73 s for the last tenant. **The consumers' per-tenant one-second poll is the remaining
  blocker to the gate**; it is the delivery path, not the evaluator runtime this lane changed, so it is reported, not
  changed here. The consumers already have per-tenant repeat timers (`arm`) and wakes on revision (`revised`/`wake`);
  turning the poll into a slow backstop is the analogous change.

The evaluation-gap alert fired in the field: run 1's evaluator logged 2,229 `EVALUATOR_NOT_EVALUATED_WITHIN_BOUND`
lines and run 2's inspection showed all 1,000 alerting; in the diagnostic steady state none.

### Controls (reproduced)

| control | green | break-it → restored |
|---|---|---|
| one tenant's evaluation suppressed (its change check never completes) | `EV_GAP_ALERT`: only that tenant alerts, once, age > 30,000 ms; the other is confirmed ≤ 1 s; clears after evaluation (`tests/evaluator-gap-alert.test.js`) | watchdog raise disabled: red, no alert for the suppressed tenant (`EV_GAP_ALERT only the suppressed tenant, once`) → restored 3/3 |
| paused/withdrawn tenant | no alert | |
| serve boot | returns before any acquisition; warm tenants first; one at a time at concurrency 1; the backstop does not start queued tenants | |
| config parse cache | 21 reads of an unchanged file parse once; a same-size edit is seen (`EV_CONFIG_PARSED_ONCE_WHILE_UNCHANGED`, `EV_CONFIG_EDIT_SEEN`) | cache disabled: red, `EV_CONFIG_PARSED_ONCE_WHILE_UNCHANGED` → restored 17/17 |
| stuck tenant does not hold the others | found by the alert test itself: the first version's single-flight pass let one hung check stop every tenant's confirmation; fixed by the per-tenant guard (`3ac621a2`) | |

Checks: see the table appended below this section.

### Still open

- The consumers' per-tenant one-second poll (above): owner is the delivery/realtime perf lane or the join coordinator.
- The gate's healthy point under serve readiness is earlier (12 s) than perf-db's measurement under `all` (54.5 s), so
  the windows are not identical; the column "p50 since restart" is comparable.
- The two decisions reported above (definer function, incremental read) are unchanged by this work.

### Checks at the resumed heads (reproduced)

| check | lane `5ab35cad` | join `41f9179a` |
|---|---|---|
| affected suites (as above, all opt-ins, + new suites; join also tenant-readiness, pool-config, tenant-startup-admission) | 222 passing, 0 failing | 256 passing, 0 failing |
| unit tier | 3228 passing, 0 failing (a first run had 1 failure in `tenant-legacy-credentials`, a JWT lifetime of 28801 vs 28800 s at a second boundary; untouched by this lane, it passed 3/3 alone and in the rerun) | 3259 passing, 0 failing |
| `test:tiers` | ok (633 files) | ok (637 files) |
| `test:write-boundary` | — | all 9 entry points |
| eslint `lib` | 0 errors (55 warnings; +1 `detect-non-literal-fs-filename` on the config `statSync`) | 0 errors |

## Round 3, 2026-11-11 (06:00–07:00 local): consumers on change, gate at deployed settings, CPU profile

*Decisions [write-clock-complete](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#write-clock-complete) (the
digest scan retires once perf-db's complete clock lands; the signature stays opaque: `evaluator-runtime.js`
`validSignature`/`same`, read through `component.signature()` → `postgres-durable-replay.js` `signature()`) and
[incremental-refresh-realtime-only](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#incremental-refresh-realtime-only)
(no incremental read for the evaluator) are noted; nothing in this round depends on them.*

| what | value |
|---|---|
| lane head | `9c46b95e` (on `5ab35cad`): evaluator consumers on change |
| join scratch head | `3b858586` (lane `9c46b95e` merged); image `ns-pev-perf:3b858586` label-checked, removed afterwards |

### Consumers on change (`lib/server/serve/evaluator-consumers.js`)

- The `pollIntervalMs`/`retryIntervalMs` loops visit only **active** tenants: a pending or refused request, or an armed
  repeat clock (an alarm already delivered). Acks, snoozes and retries are seen as promptly as before where they can
  matter; an ack reaches the consumer through its next selection, and only a tenant with a delivered alarm can be acked.
- A newly alarming tenant is found by the evaluator's revision wake (`revised`); a repeat by its `arm` timer.
- Every tenant is visited by the slow backstop, `backstopIntervalMs` (default 60,000). Every pass, including the start
  pass, works at most `maxConcurrentTenants` (default 4) tenants at once. Both are optional consumer config fields;
  `deploy/multitenant/config.js` is unchanged (its 1,000 ms intervals now apply to active tenants only).

Gates (reproduced):

| gate | result |
|---|---|
| affected suites incl. `evaluator-consumer-load` (repeat on the heartbeat, ack silence, changed-reading latency), `evaluator-consumers.integration` (retry with the same UUID after process death), timer churn | 223 passing, 0 failing (lane, before the retry test was added) |
| idle tenant | 0 consumer passes in 3 s (`EV_CONSUMER_IDLE_NOT_POLLED`) |
| new alarm on a tenant with none, 600 s backstop | delivered by the revision wake in 721 / 642 / 688 ms (`EV_CONSUMER_REVISION_WAKE`) |
| delivery failure (sink loses the response), live process | the same request accepted 355 ms after the sink recovered, ≥ 2 attempts of one request id (`EV_CONSUMER_RETRY_PROMPT`) |
| partition lab, join `3b858586` | **23/23** (repeat gates: standalone one alarm per tenant per 3 s repeat, two overlapping evaluators no duplicate, 2 members no duplicate, 2→3 no duplicate and delivery continuity within repeat + lease). The SIGKILL stale-socket case passes with perf-db's fix merged (`runs/partition-join-3b858586.txt`) |

Controls (each red, then restored):

| break | symptom |
|---|---|
| revision wake dropped (`revised` never enqueues) | `EV_CONSUMER_REVISION_WAKE delivered in null ms with a 600 s backstop`: the alarm waits for the backstop |
| no tenant on the fast loop | `EV_CONSUMER_RETRY_PROMPT same request accepted null ms after the sink recovered`, one attempt only |
| only "pending" removed from the active set | **green: vacuous**. The alarming tenant also has an armed repeat clock, which keeps it on the fast loop; the break broke nothing in that test |

### Gate: per-tenant evaluation gap after an evaluator restart, 1,000 tenants, deployed settings (reproduced, `runs/eval-gap-run4/`)

| run | code | healthy after | within 60 s | 5 min | 15 min | 25 min | not within 25 min | p50 | max | load avg |
|---|---|---|---|---|---|---|---|---|---|---|
| perf-db reference | polling evaluator | 54.5 s | 16 | 143 | 424 | 700 | 300 | 10.8 min | – | 15.8 → 9.3 |
| 3 | join `41f9179a` | 12.2 s | 511 | 668 | 928 | 999 | 1 | 46 s | 23.4 min | 4.8 → 5.8 |
| **4** | **join `3b858586`** | 9.9 s | **935** | **1,000** | 1,000 | 1,000 | **0** | **18.8 s** | **70.7 s** | 7.9 → 8.1 |

Every tenant within 70.7 s: inside the 60–90 s target. Steady state after the gate (inspection): every tenant confirmed
within 1,116 ms (p50 579, p90 1,019), no alert, no refusal; consumer passes 1–2 per tenant over the gate (not ~300);
evaluator 81% CPU, 509 MiB; PostgreSQL 558% CPU, which is the per-tenant digest signature check once a second (the
scan [write-clock-complete](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#write-clock-complete) retires).

### Where an evaluation's CPU goes (reproduced, `runs/profile-{deploy,full}.txt`; measurement only)

`tools/tenancy/perf-evaluator/profile.cjs`: one tenant with 24 h of entries and device status (576 rows), the actual
component on actual PostgreSQL, 200 sequential cycles of each kind under the V8 sampling profiler (100 µs), self time
grouped by source file. Load average 6.7–9.3, so absolute milliseconds run high; the shares are the finding.

| per evaluation | time-only, deployed plugins | time-only, 22 plugins | acquisition, deployed | acquisition, 22 plugins |
|---|---|---|---|---|
| CPU-ms | 22.3 | 30.4 | 40.4 | 45.4 |
| wall ms | 20.7 | 27.4 | 50.2 | 53.0 |
| projection-read transactions (statements) | 11 (44) | 11 (44) | 22 (58) | 22 (58) |
| DB exec ms | 3.9 | 4.4 | 12.6 | 12.3 |

Share of the busy (non-idle) samples, time-only:

| where | deployed | 22 plugins | what it is |
|---|---|---|---|
| views: materialise and data loader (`ddata.processRawDataForRuntime`, `idMergePreferNew`, `dataloader`) | 25% | 22% | rebuilding the working set from the retained input every cycle |
| projection reads: pg driver row parsing + SQL build/translate/decode | 23% | 21% | `postgres-projection-read.js:44`: each view read sends the whole retained input as a `jsonb_to_recordset` parameter and parses the rows back, 11 transactions per cycle |
| evaluator component closure (`tenant-projection-evaluator.js:60`) | 13% | 12% | `JSON.parse(retained)` and `JSON.stringify(input)` of the whole input every cycle, decode loop |
| other app code (`cache.getData` JSON deep clone, 6–8%) | 12% | 11% | |
| moment / moment-timezone | 3% | 13% | date parsing of created_at in the loader and plugins |
| GC | 8% | 7% | |
| **plugins** (`lib/plugins`) | **0.4%** | **1.3%** | the plugin pass itself is not the cost |
| sandbox, notifications | 0.4% | 0.6% | |

Acquisition adds the reconcile: pg row parsing (10%), `clone` of every row and the deep comparison of the saved
projection (`postgres-durable-replay.js`, ~8%), and 12.6 DB-ms (six 100-row page scans 3.8 ms, the checkpoint row
read 1.7 ms).

Candidate changes (not built), with their clinical-equivalence risk:

| candidate | removes (time-only) | equivalence risk | how to prove |
|---|---|---|---|
| A. serve the views' reads from the retained projection in process (an in-memory query over the same documents) instead of 11 `jsonb_to_recordset` round trips | ~23% of CPU, all 44 statements and ~4 DB-ms per time-only cycle; time-only cycles then touch no database at all | **medium–high**: the projection read deliberately reuses the SQL storage path so filter, typed identity, sort, limits and legacy translation stay identical; an in-process engine must match them (D8 names `mingo` as the differential oracle) | differential lab over the views-equality and views-replay corpora (every view query, typed twins, sort ties), plus this lane's equivalence lab |
| B. keep the materialised working set between time-only cycles of the same input; re-cut only the time windows (60 h treatments, device-status look-back) at the new instant | ~25% (materialise, ddata processing) + much of the 13% closure | **medium**: plugins and ddata processing mutate the working set (the source comment says so), so it must be copied or frozen per cycle; window cuts must equal a fresh load at every instant | the equivalence lab (alarm set and full content at 1 s), views-equality harness, a mutation guard test |
| C. drop the per-cycle `JSON.parse`/`stringify` of the retained input and `cache.getData`'s JSON deep clone (structured copy or immutable input) | ~10–20% | **low** if copies stay independent; the clone exists to stop plugin mutation leaking between cycles | the existing retained-input and mutation tests, equivalence lab |
| D. parse document dates once (cache mills on the retained documents) | up to ~13% with the full plugin set | **low–medium**: must equal moment's ISO parsing, time zones included | equivalence lab, date-format corpus |
| E. acquisition: avoid cloning and deep-comparing the whole projection in reconcile when the signature is unchanged; with the complete clock, skip storing the full projection | ~8–10% of an acquisition and part of 12.6 DB-ms | **low** for the evaluator (acquisitions now happen on change only); the checkpoint row's projection is part of the replay contract | durable-replay suites, current-state recovery proof |

At the measured rates, A + B together would take a time-only cycle from about 16–22 CPU-ms to a few CPU-ms and to zero
statements (derived, unmeasured). With work on change, time-only cycles run only at due times and for alarming tenants
on the slow timer, so the remaining per-tenant cost at idle is the backstop check, not evaluation.

### Checks at round 3 heads

See the table appended below.

| check (round 3) | lane `9c46b95e` | join `3b858586` |
|---|---|---|
| affected suites (all opt-ins, + this lane's new suites; join also tenant-readiness, pool-config, tenant-startup-admission) | 223 passing, 0 failing (before the retry test; the new file then 2/2) | **258 passing, 0 failing** |
| unit tier | **3228 passing, 0 failing** | **3259 passing, 0 failing** |
| `test:tiers` | ok (634 files) | ok (638 files) |
| `test:write-boundary` | — | all 9 entry points |
| eslint `lib` | 0 errors | 0 errors |
| partition lab | — | 23/23 |
