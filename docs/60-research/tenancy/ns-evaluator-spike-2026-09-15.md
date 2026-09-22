# `ns-evaluator`: what a per-tenant evaluation loop actually needs

> **Snapshot — research as of 2026-09-15, measured against `crm-seam-n` `c8b456a7`. Status: current — tenancy research, not on a shipping path; the three shipping defects it touched (register BF-31 `levels`, BF-28 `insulinage`, BF-29 `ENABLE`) are merged to dev in PR #8739 (2026-09-20, unreleased). Current facts: [execution plan](../../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md) T4.4, [backfix register](../../30-design/remedial/nightscout-backfix-register.md).**

*Audience: contributors.*

**Task** T4.4 (D5). **Date** 2026-09-15. **Harness** `tools/qc/ns-evaluator-arm.js`
(46 checks, 0 failed). **Checkout** `externals/work/crm-seam-n` @ `c8b456a7`.
**Status** spike — a requirements list backed by running code, not an implementation.

Run it with:

```
node --expose-gc tools/qc/ns-evaluator-arm.js [substrate|isolation|nonvacuity|cold|blast|ack|slice|cost]
```

## 0. The headline

**A per-tenant evaluator can be built on what landed today**, and the spike does build
one: two tenants in one process, each with its own thresholds from `ctxFor`, each
emitting into its own T3.5 room, tenant A's urgent high reaching `Tenant:A` and nothing
reaching `Tenant:B`. It needed **no change to shipping code**. It needed seven additions
to a T3.3 context, of which **three are process-wide singletons that the spike had to
work around rather than use**.

The blocker to turning alarms on is **not** the evaluator. It is that
`lib/notifications.js`'s ack/snooze map is in memory, and under D5 the four places a
person can acknowledge an alarm are all on processes that are **not** the evaluator.

## 1. Requirements

Each item carries the evidence that produced it. `arm:<section>` names the check.

### The context

**REQ-1 · The evaluator needs a `ddata` per tenant, and nothing owns one.**
`bootevent.js:244` builds exactly one per process. T3.3 deliberately excludes it.
*Evidence*: `arm:substrate` — the spike's context has 8 keys beyond
`DERIVED_CONTEXT_KEYS`. `arm:nonvacuity` BREAK 3 — with one shared `ddata`, tenant A
emits `Urgent HIGH` into `Tenant:A` **having loaded nothing of its own**, on tenant B's
glucose.

**REQ-2 · `lib/bus.js` cannot be instantiated per tenant.** `bus(settings, ctx)` calls
`setInterval` at construction. One bus per tenant is one heartbeat timer per tenant — at
{R}'s 1,580 resident tenants, 1,580 timers whose only job is to fire the process-wide
tick an evaluator replaces. **The spike substituted a bare `EventEmitter`.** This is a
named mismatch, not a fix: splitting the tick out of `lib/bus.js` is a change to shipping
code that was not in scope.

**REQ-3 · The plugin *registry* is per tenant, not just the settings it reads.**
`plugins.register` computes `enabledPlugins` from `ctx.settings.enable` **once**, at
construction (`lib/plugins/index.js:136`). A shared registry means every tenant runs the
first tenant's enabled plugin list. *Evidence*: `arm:substrate`.

**REQ-4 · `notifications` is per tenant and may not be cached.** *Evidence*: `arm:ack` —
A snoozes for 30 minutes; **one LRU eviction later the same reading alarms again**, with
nothing a person sees saying why. This measures T3.3's `DERIVED_CONTEXT_KEYS` reasoning
rather than restating it.

**REQ-5 · `lib/levels.js` is a module singleton and the evaluator mutates it.**
`bootevent.js:212` does `ctx.levels.translate = ctx.language.translate`. Two tenants get
the same object, so **the last context built owns alarm-level text for every tenant in
the process** — and that text reaches push notifications. `language` itself is correctly
per-instance. *Evidence*: `arm:substrate` (`ctx.levels === b.levels` while
`ctx.language !== b.language`). This is **BF-22** seen from the evaluator; the spike
reproduces the shipping assignment rather than papering over it.
[Correction 2026-09-22: the register files this defect as **BF-31** (merged to dev via PR #8739, unreleased); register BF-22 is an unrelated seam defect.]

**REQ-6 · The store stays shared, by reference, on purpose.** D3: isolation is a
per-transaction `set_config` on a pooled connection. A per-tenant store would be a
per-tenant connection pool. *Evidence*: `arm:substrate` asserts it, so a future
per-tenant store shows up as a failed check rather than as a thousand pools.

### The loop

**REQ-7 · Every tenant's evaluation needs its own error boundary, and it is not there
today.** `plugins.setProperties`/`checkNotifications` try/catch **per plugin**, but
`sandbox.serverInit`, `notifications.initRequests` and `notifications.process` are
unguarded. *Evidence*: `arm:blast` — in a plain `for (tenant of tenants) evaluate(tenant)`,
one tenant with a half-failed load throws out of `serverInit` and **every later tenant is
never evaluated**; the spike measures tenant C silently not being alarmed. A per-tenant
`try/catch` contains it and C is evaluated again.

**REQ-8 · A swallowed plugin error is a silent per-tenant alarm outage.** The per-plugin
try/catch means bad data produces **no alarm and no signal above `console.error`**.
*Evidence*: `arm:blast` — `ddata.sgvs = null` yields 0 alarms, 0 throws. Under one process
per tenant this is a crash somebody notices; under a shared evaluator it is invisible.
**The evaluator needs a per-tenant health signal that a swallowed plugin error trips.**

**REQ-9 · The loop can stay synchronous, and today it must.** Evaluation itself is
`0.046 ms` per tenant (`arm:cost`, 1 sgv, 10 plugins, no I/O). Nothing in the four calls
awaits. The two things that would make it async are **loading `ddata`** and **reading
ack/snooze from storage** — see REQ-12.

**REQ-10 · `process()` emits at most one alarm per group.** `notifications.process`
emits the **highest** alarm per group plus anything at or below INFO. *Evidence*:
`arm:slice` — 6 plugins requested an alarm, 5 emissions, all in group `default`. An
evaluator that fans out per tenant inherits this ceiling per **(tenant, group)**, and any
measurement taken on emissions rather than requests is nearly blind to it. (This is why
the `slice` ablation measures `requestNotify`.)

### Cold start and clocks — the three the brief did not anticipate

**REQ-11 · A cold tenant's first alarm is silently suppressed, and the hazard is one
integer wide.** `lib/notifications.js:196` gates on
`ctx.ddata.lastUpdated > alarm.lastAckTime + alarm.silenceTime`. A fresh `ddata` has
`lastUpdated: 0` (`ddata.js:21`) and a fresh `Alarm` has `lastAckTime: 0`,
`silenceTime: 30 min` — so the guard reads *"is this data timestamped after
1970-01-01T00:30Z"*. *Evidence*: `arm:cold` — same reading, same thresholds, **only
`lastUpdated` differs (0 vs now): warm emits `Urgent HIGH`, cold emits nothing**, and the
log line says *"silenced for 30 minutes more"* for an alarm nobody ever snoozed.

Under single tenancy this is unreachable: `data-loaded` fires only after a load, so
`dataloader.js:68` has always set `lastUpdated = Date.now()`. **A change-feed-driven
evaluator has no such guarantee**, which is exactly the cold-tenant case.

A merely *stale* `ddata` does **not** suppress — both operands are absolute epoch ms, so
staleness is harmless. Pinned as its own check.

**REQ-12 · Snooze is measured in *data* time; ack is written in *wall* time.**
`ack` writes `Date.now()` (`notifications.js:198`); the silence window is compared
against `ddata.lastUpdated`. *Evidence*: `arm:cold` — identical 30-minute ack at the same
wall instant, a tenant whose feed has advanced 35 min re-alarms, a tenant whose feed sits
10 min behind the ack stays silent. **A tenant whose feed is L behind the wall holds a
30-minute snooze for 30 + L minutes of real time, and L is per tenant.** Any storage
schema has to choose one clock and say which.

**REQ-13 · `sbx.time` is a third clock, hardcoded to `Date.now()`.**
`sandbox.js:51`, and `lastEntry` (`:141`) silently drops any entry newer than it.
*Evidence*: `arm:cold` — an sgv 60 s in the future evaluates to **nothing at all, with no
error and no log**. **An evaluator that batches, replays or catches up a tenant must own
`sbx.time`, and `serverInit` does not let it.** A harness that seeds entries 60 s ahead passes checks vacuously for
this reason; `arm:cold` guards against it.

### Ack/snooze — the actual blocker

**REQ-14 · The key is `(level, group)` with no tenant in it.**
`notifications.js:42`: `var key = level + '-' + group`. With per-tenant instances the
tenant is implicit in the *instance*. A storage-backed table must therefore key on
**`(tenant_id, level, group)`**. *Evidence*: `arm:nonvacuity` BREAK 4 — with one shared
instance, A acks and **B (a different person, same level 2, same group `default`, same
reading) emits 0**.

**REQ-15 · Under D5, no acknowledgement a person makes can ever reach the code that
decides whether to alarm.** This is the sharp form of T3.4's finding and it is the
verdict's load-bearing item. The four **person-initiated** ack writers:

| site | route | D5 entrypoint |
|---|---|---|
| `lib/api/notifications-api.js:28` | HTTP `GET /notifications/ack` | `ns-api` |
| `lib/api3/alarmSocket.js:111` | socket `ack` | `ns-realtime` |
| `lib/api3/alarmSocket.js:167` | socket `ack`, v3 auth path | `ns-realtime` |
| `lib/server/pushnotify.js:85` | Pushover receipt callback | `ns-api` |

and the only **reader** of `alarm.lastAckTime` is `notifications.js:196`, inside
`process()`, on `ns-evaluator`. T3.4 measured this as *"a sibling process emits 1"*.
Under D5 it is not a sibling accident — **the ack and the decision are on different
processes by design**. *Evidence*: `arm:ack`.

**REQ-16 · T3.4's conditional-upsert recommendation holds, and REQ-12 sharpens it.**
`ack`'s "already snoozed" guard is a read-modify-write and the seam does not promise
cross-operation atomicity ({S} §9). A single
`INSERT … ON CONFLICT (tenant_id, level, group) DO UPDATE … WHERE` expresses the guard as
the conflict predicate. The schema must also record **which clock** `last_ack_time` is in
(REQ-12) and must not let a cold read produce `lastUpdated = 0` (REQ-11).

### What a per-tenant `ddata` has to contain

**REQ-17 · Five fields are alarm-critical; twelve are display-only on this corpus.**
Measured **top-down by ablation**: populate everything, take a baseline of what the
plugins *requested*, blank one field at a time, record what is lost. 25 plugins enabled,
6 alarm producers armed.

| | fields |
|---|---|
| **alarm-critical** | `sgvs` (loses `simplealarms`, `ar2`), `devicestatus` (loses `upbat`), `sitechangeTreatments` (loses `cage`), `sensorTreatments` (loses `sage`), `batteryTreatments` (loses `bage`) |
| **display-only** | `mbgs`, `cals`, `treatments`, `profiles`, `food`, `activity`, `dbstats`, `insulinchangeTreatments`, `profileTreatments`, `tempbasalTreatments`, `combobolusTreatments`, `tempTargetTreatments` |
| **fatal if absent** | none |

Two consequences worth stating separately:

- **Raw `treatments` is display-only; the *derived* arrays are what the alarm path
  reads.** So an alarm-critical slice cannot just retain `treatments` — it must retain
  `processTreatments`'s output, or run `processTreatments` on wake.
- `insulinchangeTreatments` appears display-only **because of a bug, not because it is**
  — see §2.

This is my route's answer to {R} §12.5's proposed split. A sibling agent measured the
same question bottom-up from `checkNotifications`; the two were run without contact,
deliberately.

**REQ-18 · Residency, from this route.** `110.4 KB` per resident evaluator context with
an **empty** `ddata` (300 tenants, `--expose-gc`); `0.248 ms` to build one on a cache
miss. That is the floor — it excludes the `ddata` and `ctx.cache` payload that {R}
measures at 2,652 KB fully resident. The two figures are consistent and measure different
things: {R} measures a *loaded* tenant, this measures the *machinery* around it.

**REQ-19 · Loading is unowned and is the next thing to measure.** `dataloader.update`
needs `ctx.cache`, `ctx.entries/treatments/devicestatus/profile/food/activity` and
`ctx.store.db.stats`, and issues **9 parallel queries per tenant per cycle**.
`ctx.cache.isEmpty('entries')` is what selects a 15-minute incremental load over a 2-day
cold load, so **the per-tenant cache is load-bearing for the incremental path**, not an
optimisation. This spike does not run it (§4).

## 2. Found incidentally, not looked for

**`lib/plugins/insulinage.js:92` compares against `insulinInfo.urgent`, which is never
assigned anywhere in the file.** Its three sibling age plugins use `prefs.urgent` on the
identical line (`cannulaage.js:87`, `sensorage.js:141`, `batteryage.js:87`).
`age >= undefined` is false, so the URGENT branch is unreachable and the plugin falls
through to WARN.

**What this costs a person: the "Insulin reservoir change overdue!" urgent alarm never
fires.** *Evidence*: `arm:slice` — at the urgent age (72 h) `iage` requests nothing; at
the warn age (48 h) it requests level 1.

Pre-existing, single-tenant, unrelated to tenancy. **Not fixed** — D12 keeps
cgm-remote-monitor pristine and it is outside T4.4. Recommend a **backfix-register
entry**.
[Status 2026-09-22: filed as register **BF-28**, merged to dev via PR #8739 (2026-09-20), not released — 15.0.8 still has it.]

## 3. Verdict — and the shortest path to multitenant alarms being ON

**Can a per-tenant evaluator be built on what landed today? Yes.** T3.3 gives the
settings and T3.5 gives the room, and they compose: the spike runs two tenants with
different thresholds in one process against one identical reading, and A's alarm reaches
A's room while B's decision correctly differs, with no change to shipping code. The
substrate is sound and the missing piece named in the brief — `ddata` — is the easy one:
nothing *owns* it, but nothing *obstructs* it either.

**The shortest path to alarms being ON is not the evaluator.** It is REQ-15. Today
`TENANCY_MODE=multi` withholds alarms because producers run outside a tenant scope; the
spike shows that wrapping evaluation in `withTenant` fixes that in one line of loop
structure. But turning alarms on with the ack map still in memory ships something worse
than withholding: under D5 a person's acknowledgement lands on `ns-api` or `ns-realtime`
and the deciding process never sees it, so **every snooze fails open and the alarm
re-fires on the next cycle, forever**. That is an alarm-fatigue defect that would train
people to ignore the one path where not firing is the worst outcome.

So, in order:

1. **`(tenant_id, level, group)` ack/snooze in storage**, written as a single conditional
   upsert (REQ-14, REQ-16), with the clock question settled (REQ-12) and cold reads unable
   to produce `lastUpdated = 0` (REQ-11). This is T3.4's deferred work and it is the gate.
2. **A per-tenant error boundary and a per-tenant health signal** (REQ-7, REQ-8) — cheap,
   and without them one tenant's bad row silences a different tenant.
3. **A per-tenant `ddata` owner** with the alarm-critical slice of REQ-17, plus whatever
   §4 turns up when the loader is actually run per tenant.
4. **BF-22 (`levels`)** before alarm *text* is trusted per tenant (REQ-5).

Steps 2 and 3 are inside T4.4. Step 1 is the one with a schema and an async reordering in
it, and it is the one that should be measured next.

## 4. Honest limits

What this spike did **not** exercise. Read these before quoting anything above.

- **No database, no `dataloader`, no `ctx.cache`.** `ddata` is seeded by hand. Everything
  in REQ-19 is read from the source, not run. **The single largest unknown is what happens
  when nine queries per tenant per cycle meet a real pool**, and none of it is measured
  here.
- **No storage-backed ack.** REQ-16 specifies a write that was never executed. The claim
  that the loop "can stay synchronous" (REQ-9) is true *of today's code* and is exactly
  what step 1 changes; the reordering risk T3.4 names is untested.
- **The `slice` ablation is corpus-limited and the corpus is mine.** 6 alarm producers
  armed out of 17 plugins with a `checkNotifications`. `openaps`, `loop`, `xdripjs`,
  `pump`, `errorcodes`, `bwp`, `treatmentnotify` and `timeago` never fired, so fields only
  they read could be misfiled as display-only. **`insulinchangeTreatments` is a known
  false "display-only" caused by §2's bug** — treat the display-only column as *not yet
  shown to be critical*, not as *shown to be safe to drop*.
- **A near-miss worth recording**: four alarm producers were silently disabled in an
  earlier corpus because `ENABLE` listed file names (`cannulaage`) rather than registered
  names (`cage`), and **nothing warns about an unknown name in `ENABLE`**. That draft
  reported `treatments` as display-only. Any ablation on this codebase should assert its
  producers armed before trusting its negatives — `arm:slice` now does. [Status 2026-09-22:
  the silent `ENABLE` defect is register **BF-29**, merged to dev via PR #8739, unreleased.]
- **Two tenants, not 1,580.** No scheduling, partitioning, fairness, backpressure or
  wake/clone behaviour. {R}'s O(n²) merge/delta up to 81.2 ms is untouched here, and the
  `0.046 ms` evaluation figure is on a 1-sgv `ddata` — it is a floor, not a forecast.
- **`lib/bus.js` was replaced, not used** (REQ-2), so nothing here exercises the real
  tick/debounce/concurrency-guard path at `bootevent.js:293-311`.
- **No socket handshake.** `arm` uses T3.5's `currentRoom` with a stub resolver and
  registry; T3.1/T3.5 own the handshake half and it is tested there, not here.
- **Alarm *delivery* is not tested** — only which room an emission is addressed to. Push
  notification, Pushover and the `/alarm` namespace fan-out are out of scope.
- **Single process.** Nothing here says anything about two evaluator processes, which is
  where T4.4's hash partitioning lives.

## 5. Two mismatches in the brief, reported rather than worked around

- The brief gave the worktree head as `29749d92`; `crm-seam-n` is at **`c8b456a7`**
  (`29749d92` is its grandparent — T4.2 has since landed on `seam/t4-n`). The spike ran
  against `c8b456a7`. Nothing in T4.2 touches the evaluation path.
- All work is in `crm-seam-n`; the sibling worktree `crm-seam-m` was neither read nor written.

---

*Draft for review. This is quality-control research on an open-source project's
architecture, not clinical or regulatory advice. The alarm-behaviour findings (REQ-11,
REQ-15, §2) describe how software behaves under configurations that do not yet ship;
nobody's therapy decisions should be changed on the basis of this document, and anyone
with questions about their own alarm settings should raise them with their care team.*
