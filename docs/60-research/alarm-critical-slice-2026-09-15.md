# The alarm-critical slice, measured: 32.7 KB and 1.94 ms, not 852 KB and 27.5 ms

**Experiment**: EXP-MT-060 (alarm-critical vs display slice of `ddata`, measured by
knockout rather than by reading the source)
**Date**: 2026-09-15
**Harness**: `tools/qc/alarm-critical-slice.js` (alignment repo; `require()`s the shipping
modules by path, per D12 — nothing was written into cgm-remote-monitor)
**Under test**: `cgm-remote-monitor` @ **`29749d92`** (`seam/t3-k`, T3.5 landed), real
`lib/sandbox.js`, `lib/plugins/index.js`, `lib/notifications.js` and the 18-plugin shipped
alarm set
**Environment**: Node v24.15.0, Linux, shared development machine, **no database in the
loop** — event-loop CPU and serialised-byte measurements, not capacity results
**Confidence**: **measured**, with 15 non-vacuity checks that all pass and two of which
caught defects in the harness itself before the numbers were believed
**Feeds**: the plan's T3.5 ("the consequence to read twice") and phase 4 / D5 `ns-evaluator`
**Reproduce**: `node tools/qc/alarm-critical-slice.js --root <cgm-remote-monitor checkout>`
(~30 s; add `--json` for the raw record)

---

## Verdict

**A per-tenant alarm evaluator is cheap, and the number is 32.7 KB and 1.94 ms per tenant per
evaluation.** Against a realistic single-tenant dataset (576 SGVs, 600 treatments, 576
devicestatus, one profile) the whole of `ddata` serialises to **852.1 KB** and one full
evaluation of `bootevent.js:327-333` costs **27.5 ms p50**. Reduce `ddata` to a window
derived from the alarm code's own constants — 60 minutes of SGVs, a DIA of treatments, the
newest ten devicestatus, the newest of each of the four device-change event types, the active
profile, and `lastUpdated` — and the same evaluation costs **1.94 ms p50 / 2.14 ms p95** over
**33,475 bytes**, and emits **the identical alarm**. That is **26× less memory and 14× less
CPU** than evaluating against a resident `ddata`. At the empirical minimum for this fixture
it is smaller still — 5,567 bytes and 0.44 ms, a 62× speedup — but that figure is
fixture-specific and should not be planned against; §6 says why.

Set against {R} §12.5's proposal, the split is real but **the axis was wrong**. §12.5
proposes partitioning `ddata` **by field** into an alarm slice and a display slice. Measured
by knockout, **9 of 19 fields are alarm-critical and they carry 92.4 % of the bytes** — a
field partition buys nothing. What buys everything is partitioning **by depth**: every
alarm-critical field is needed only at its newest few documents. §12.5's *size* estimate of
50.6 KB nevertheless survives well; the conservative measurement here is 32.7 KB, within
1.5× of a figure that was arrived at by reading eighteen plugins rather than running them.

For the phase-4 cost model: the alarm slice is **transient**, so at 10,000 tenants alarm
coverage is a working set of ~327 MB *if every tenant were evaluated at once*, and in
practice it is 32.7 KB × concurrency, materialise-evaluate-discard. The evaluator does not
need a resident `ddata` and should not be built around one.

Two findings arrived that were not what was being measured, which plan §8 says to expect:

1. **`lib/plugins/insulinage.js:92` compares against `insulinInfo.urgent`, which is never
   assigned**, where `cannulaage.js:87`, `sensorage.js:141` and `batteryage.js:87` all
   compare against `prefs.urgent`. `age >= undefined` is always false, so **the URGENT
   "Insulin reservoir change overdue!" alarm can never fire**; the plugin degrades silently
   to WARN at 48 h. This is an upstream safety defect, unrelated to multitenancy, and it is
   **not fixed here** (D12). §5.1.
2. **{R} §2's "the plugin tier is small and flat — 0.61 ms p50" does not survive** with the
   full alarm plugin set enabled and a realistic treatment history. Measured here at
   **27.5 ms p50**, of which **about three quarters is `cob.setProperties` alone** and a further 12 % is
   `openaps.setProperties`. `checkNotifications` itself — the thing this brief named — is
   **0.37 ms, about 1 % of the block**. The alarm path's cost is not in the alarm plugins; it is in the property
   plugins the alarm plugins depend on. §4.2.

---

## 1. What was measured, and where the boundary was drawn

The target is the five lines that are the entire alarm producer, `lib/server/bootevent.js:327-333`:

```js
var sbx = require('../sandbox')().serverInit(env, ctx);
ctx.plugins.setProperties(sbx);
ctx.notifications.initRequests();
ctx.plugins.checkNotifications(sbx);
ctx.notifications.process(sbx);
```

`setProperties` is inside the boundary although the brief named only the last two calls.
It has to be: `bwp.checkNotifications` reads `sbx.properties.bwp`, `ar2` reads the buckets
`bgnow` sets, `cage`/`sage`/`iage`/`bage` each read a property computed in the earlier pass.
Timing or slicing `checkNotifications` alone would have produced a number with no decision
behind it — and, as §4.2 shows, would have missed 99 % of the cost.

The harness reproduces that block exactly, against a `ctx` assembled from the real
`lib/language.js`, `lib/levels.js`, `lib/server/env.js`, `lib/data/ddata.js`,
`lib/notifications.js` and `lib/plugins/index.js`, with a real `EventEmitter` bus and no
database. `ddata.processTreatments(false)` is called before the cycle because that is what
`lib/data/dataloader.js` does. Every trial gets a **fresh** `ctx` and therefore a fresh
`lib/notifications.js` instance — its ack/snooze map is per-instance, and reusing it would
have let trial *n* silence trial *n+1* and manufacture a dependency that is not there.

### 1.1 Three signatures, because "a read" and "an alarm" are three different things

| signature | contents | what a change means |
|---|---|---|
| `alarmSig` | emitted WARN/URGENT only: level, group, plugin, event | **somebody is or is not woken up** |
| `requestedAlarmSig` | WARN/URGENT *requested*, before highest-wins and before snoozes | an alarm changed that is currently masked |
| `fullSig` | every emission including INFO and All-Clear, plus title and message | display text changed |

`notifications.process` emits **at most one alarm per group** — the highest. A field that
changes only a masked alarm therefore leaves `alarmSig` untouched. Classifying on `alarmSig`
alone would call such a field inert, and an evaluator built on that classification would emit
the *wrong* alarm the moment the masking one cleared. Hence the `MASKED` class, which is in
the slice.

Field verdicts, in precedence order: **CRITICAL** (emitted alarms change) > **MASKED**
(requested alarms change) > **NOTIFY** (INFO/All-Clear emissions change) > **DISPLAY** (only
title/message change) > **INERT** (nothing changes).

---

## 2. The inventory, and why the Proxy alone answers nothing

`ctx.ddata` is wrapped in a `Proxy`, and so is the object `ddata.clone()` returns — which is
what `sbx.data` actually is (`sandbox.js:52`). Two logs, because they are two objects with
two lifetimes.

Reads off the **live** `ctx.ddata`, identical in all nine scenarios:

```
clone  profiles  profileTreatments  tempbasalTreatments  combobolusTreatments  lastUpdated
```

`profiles`, `profileTreatments`, `tempbasalTreatments` and `combobolusTreatments` are read
unconditionally by `serverInit` (`sandbox.js:60-61`) to build `sbx.data.profile`, on every
cycle, alarm or no alarm. `lastUpdated` is read by `notifications.js:79` and gates every
emission.

Reads off the **clone** (`sbx.data`), also identical in all nine scenarios:

```
sgvs  cals  inRetroMode  devicestatus  treatments  profile
sitechangeTreatments  sensorTreatments  insulinchangeTreatments  batteryTreatments
dbstats  mbgs
```

**The read set does not vary with the scenario at all.** Check V2b reports *1 distinct read
set* across nine scenarios that produce *7 distinct alarm signatures*. The plugins read the
same fields whether they are about to wake somebody at 48 mg/dl or about to do nothing. **The
Proxy inventory, on its own, cannot produce a slice** — it produces "everything the plugins
touch", which is most of `ddata`. This is precisely the second vacuity mode the brief names:
*the code never distinguishes the branches*. Only the knockout separates them.

---

## 3. The knockout: read versus dependency

Nine scenarios. For each, every field of `ddata` — read or not — is neutralised to the empty
value of its own type and the cycle re-run.

| scenario | emitted | alarm-critical fields | display-only |
|---|---|---|---|
| `quiet` — steady 110 mg/dl, fresh | *(nothing)* | — | — |
| `urgentLow` — last SGV 48 | `ar2` URGENT low | `sgvs` `lastUpdated` | `cals` `profiles` `devicestatus` |
| `warnHigh` — last SGV 205 | `ar2` WARN high | `sgvs` `devicestatus` `lastUpdated` | `cals` (+`profiles` MASKED) |
| `stale` — last SGV 45 min old | `timeago` URGENT | `sgvs` `lastUpdated` | `treatments` `cals` `profiles` `devicestatus` |
| `predictedLow` — falling fast | `ar2` WARN low predicted | `sgvs` `lastUpdated` | `cals` `profiles` `devicestatus` |
| `highCoveredByIob` — 205 with 3.0 U IOB | *(nothing — snoozed)* | `profiles` | — (+`sgvs` MASKED) |
| `deviceAged` — each change at its urgent hour | `cage` `sage` `bage` URGENT | `lastUpdated` `sitechangeTreatments` `sensorTreatments` `batteryTreatments` | — |
| `insulinAgedWarn` — reservoir 48 h | `iage` WARN | `lastUpdated` `insulinchangeTreatments` | — |
| `recentTreatment` — 48 mg/dl, treatment 4 min ago | *(nothing — snoozed)* + INFO | `treatments` | — (+`sgvs` MASKED) |

Union over all nine, with JSON-serialised UTF-8 bytes on this fixture:

| field | read | bytes | verdict | alarm-critical in |
|---|---|---:|---|---|
| `devicestatus` | yes | 478,619 | **CRITICAL** | `warnHigh` |
| `treatments` | yes | 151,511 | **CRITICAL** | `recentTreatment` |
| `sgvs` | yes | 119,861 | **CRITICAL** | `urgentLow` `warnHigh` `stale` `predictedLow` |
| `batteryTreatments` | yes | 14,210 | **CRITICAL** | `deviceAged` |
| `insulinchangeTreatments` | yes | 13,910 | **CRITICAL** | `insulinAgedWarn` |
| `sensorTreatments` | yes | 13,790 | **CRITICAL** | `deviceAged` |
| `sitechangeTreatments` | yes | 13,730 | **CRITICAL** | `deviceAged` |
| `profiles` | yes | 630 | **CRITICAL** | `highCoveredByIob` |
| `lastUpdated` | yes | 13 | **CRITICAL** | 6 of 9 |
| `cals` | yes | 98 | DISPLAY | — |
| `tempbasalTreatments` | yes | 16,910 | INERT | — |
| `tempTargetTreatments` | no | 16,970 | INERT | — |
| `combobolusTreatments` | yes | 16,070 | INERT | — |
| `profileTreatments` | yes | 15,890 | INERT | — |
| `mbgs` | yes | 86 | INERT | — |
| `dbstats` | yes | 41 | INERT | — |
| `activity` | no | 85 | INERT | — |
| `food` | no | 85 | INERT | — |
| `lastProfileFromSwitch` | no | 4 | INERT | — |

| class | fields | bytes |
|---|---:|---:|
| **ALARM-CRITICAL** | **9** | **787.4 KB** |
| MASKED (union; each is CRITICAL elsewhere) | 0 | 0 |
| NOTIFY-ONLY | 0 | 0 |
| DISPLAY-ONLY | 1 | 0.1 KB |
| INERT | 9 | 64.6 KB |
| **whole `ddata`** | **19** | **852.1 KB** |

**92.4 % of `ddata`'s bytes are alarm-critical at field granularity.** If the question is
"which collections can the evaluator skip", the answer is *almost none*, and §12.5's field
partition does not exist.

### 3.1 Three dependencies the source does not make obvious

- **`treatments` can withhold an alarm.** `treatmentnotify.js:64-75` requests a URGENT-level
  *snooze* whenever the newest treatment is under 10 minutes old, and
  `notifications.process` honours it. `urgentLow` and `recentTreatment` differ **only** in
  whether the newest treatment is 25 or 4 minutes old: the first emits `ar2` URGENT low, the
  second emits nothing. An evaluator that got the treatment window wrong would wake people
  who should not be woken, or not wake people who should.
- **`profiles` can withhold an alarm.** `boluswizardpreview.highSnoozedByIOB` snoozes a high
  when IOB covers it. In `highCoveredByIob` (205 mg/dl, 3.0 U IOB) the high is correctly
  suppressed; knock out `profiles` and `bwp` errors out, the snooze disappears, and the high
  alarm fires. The profile is not display state.
- **`devicestatus` can change an alarm**, because `lib/plugins/iob.js` prefers a
  device-reported IOB over one calculated from treatments, and that IOB feeds `bwp`. In
  `warnHigh`, knocking out the 478 KB `devicestatus` array changes the emitted alarm set.
  But the depth probe shows only its **newest document** is needed (§4.1).

---

## 4. Depth, which is where the slice actually lives

### 4.1 The probe

For each slice field, shrink it to its newest *n* elements and find the smallest *n* at which
every scenario still produces the same requested-alarm set **and** the same emitted-alarm set.
`treatments` is re-derived with `processTreatments` after truncation, because its seven
derived arrays are a function of it.

| field | minimal tail / length | bytes @ tail | bytes whole |
|---|---:|---:|---:|
| `sgvs` | 2 / 576 | 437 | 119,847 |
| `treatments` | 8 / 600 | 2,027 | 151,511 |
| `devicestatus` | 1 / 576 | 1,528 | 478,619 |
| `sitechangeTreatments` | 1 / 60 | 230 | 13,730 |
| `sensorTreatments` | 1 / 60 | 231 | 13,790 |
| `insulinchangeTreatments` | 1 / 60 | 233 | 13,910 |
| `batteryTreatments` | 1 / 60 | 238 | 14,210 |
| `profiles` | 1 / 1 | 630 | 630 |
| `lastUpdated` | scalar | 13 | 13 |
| **total** | | **5,567 B (5.4 KB)** | **803 KB** |

**0.64 % of `ddata`.** The split is real; it is a depth split, not a field split.

### 4.2 The cost, and a correction to {R} §2

Timing the five lines only — seeding, `processTreatments` and `ctx` construction are outside
the timer, because an evaluator would not repeat those per wake. Instrumentation Proxies off.

| arm | p50 | p95 | emits |
|---|---:|---:|---|
| full `ddata` (852.1 KB) | **27.502 ms** | 30.344 ms | `2\|default\|ar2\|low` |
| conservative window (32.7 KB, §4.3) | **1.941 ms** | 2.137 ms | `2\|default\|ar2\|low` |
| empirical minimum (5.4 KB) | **0.440 ms** | 0.647 ms | `2\|default\|ar2\|low` |

Where it goes, attributed per phase and per plugin over 10 runs. Per-plugin instrumentation
adds overhead of its own — the instrumented block totals 33.3 ms against the clean arm's
27.5 ms — so read the **proportions**, not the absolutes:

| phase | ms (instrumented) | share |
|---|---:|---:|
| `serverInit` (clone + profile deep clone) | 0.213 | 0.6 % |
| **`setProperties`** | **33.345** | **98.7 %** |
| `checkNotifications` | 0.369 | 1.1 % |
| `notifications.process` | 0.087 | 0.3 % |

| plugin | ms (instrumented) | share of cycle |
|---|---:|---:|
| **`cob.setProperties`** | **25.055** | **74 %** |
| `openaps.setProperties` | 3.904 | 12 % |
| `iob.setProperties` | 0.875 | 2.6 % |
| `bage.setProperties` | 0.673 | 2.0 % |
| `iage.setProperties` | 0.558 | 1.7 % |
| `cage.setProperties` | 0.483 | 1.4 % |

{R} §2 point 8 reports the plugin tier at **0.61 ms p50, "flat from 300 to 2,400
treatments"**. With the full shipped alarm set enabled — including `cob`, which §2's plugin
arm did not exercise — it is **27.5 ms**, and it is not flat: it is dominated by one
plugin's pass over the treatment history. Anyone quoting §2's 0.61 ms for the alarm tier
should stop. Whether `cob.setProperties` is quadratic was not measured here and is named in
§7 as the next thing to look at.

### 4.3 The conservative window — what to plan against

The empirical minimum is a lower bound over *this* fixture. The clearest way it misleads:
the probe says `treatments` needs 8 documents, but only because this fixture's IOB comes from
`devicestatus.openaps.iob`, which `lib/plugins/iob.js` prefers. A site with no
device-reported IOB computes IOB and COB from treatments over the profile's DIA. So the
report also carries a window derived from the **code's own constants**:

| field | n | bytes | constant it comes from |
|---|---:|---:|---|
| `sgvs` | 12 | 2,535 | `bgnow` 15-min buckets; `timeago` 30-min urgent — 60 min at 5-min spacing |
| `treatments` | 75 | 18,975 | profile DIA 5 h, for `iob`/`cob` when devicestatus has none |
| `devicestatus` | 10 | 10,390 | newest per device/type — `dataloader.js:360,:416` already fetches some as `count: 1` |
| `sitechangeTreatments` | 1 | 230 | `cannulaage` reads the newest only |
| `sensorTreatments` | 1 | 231 | `sensorage` reads the newest only |
| `insulinchangeTreatments` | 1 | 233 | `insulinage` reads the newest only |
| `batteryTreatments` | 1 | 238 | `batteryage` reads the newest only |
| `profiles` | 1 | 630 | the active profile document |
| `lastUpdated` | scalar | 13 | `notifications.js:79` gates every emission on it |
| **total** | | **33,475 B = 32.7 KB** | |

**32.7 KB and 1.94 ms p50 is the number to plan against.** It is 3.9 % of `ddata`'s bytes and
7.1 % of a full evaluation's CPU, and it emits the same alarm.

---

## 5. Non-vacuity

15 checks, all passing, run as part of every invocation. The instrument was broken
deliberately for V1 and V6b, and both times the break was caught.

| id | claim | evidence |
|---|---|---|
| V1 | the reads come from the instrument, not from anywhere else | with both Proxies removed, both logs are empty (`cloneLog=0 liveLog=0`) while the cycle still emits |
| V1b | instrumentation does not change the outcome | uninstrumented decision signature equals the instrumented one |
| V2a | the corpus exercises the property | 7 distinct alarm signatures across 9 scenarios |
| V2b | the scenarios differ in what matters | 1 distinct read set, **7 distinct critical sets** — the read set is useless, the knockout is not |
| V3a | some field's removal silences or changes an alarm | 17 critical (field, scenario) pairs |
| V3b | it is not "everything" | 139 inert (field, scenario) pairs |
| V3c | **a read is not a dependency** | 101 pairs that are read and inert — e.g. `quiet`/`sgvs` is read and knocking it out changes nothing |
| V4 | `treatments` can withhold an alarm | same BG: treatment 25 min ago ⇒ `2\|default\|ar2\|low`; treatment 4 min ago ⇒ *nothing* |
| V5a | **remove a field claimed critical, the alarm stops** | knock out `sgvs` in `urgentLow` ⇒ alarm signature becomes `""` |
| V5b | **remove a field claimed display-only, the alarm is unchanged** | knock out the 477 KB `devicestatus` in `stale` ⇒ `alarmChanged=false`, `textChanged=true` |
| V6a | the depth probe bites | every slice field's tail is shorter than its array (`sgvs` 2/576, `devicestatus` 1/576) |
| V6b | probe and knockout agree | no slice field has a minimal tail of 0 |
| V6c | the probe terminated | every slice field found a sufficient tail within the candidate depths |
| V7 | the `insulinage` defect (§5.1) | at each plugin's urgent hour: `bage`/`cage`/`sage` URGENT, **no `iage`**; at `iage`'s warn hour: `1\|IAGE\|iage\|` |

### 5.1 Two defects the checks found in the harness itself, before any number was believed

Both would have kept the run green and produced a wrong answer, which is why they are
recorded rather than quietly fixed.

1. **The fixture snoozed every alarm.** The first run emitted no threshold alarm in any
   scenario. The cause was not the harness's alarm logic but its *fixture*: the newest
   treatment sat 4 minutes before the evaluation instant, and `treatmentnotify` snoozes all
   URGENT alarms for 10 minutes after any treatment. The alarms were firing and being
   withheld. The condition is now `recentTreatment`, a deliberate scenario, and it is the
   evidence for V4.
2. **`slice(-0)` returns the whole array.** The depth probe's candidate list starts at 0, and
   `arr.slice(-0)` is `arr.slice(0)` — a full copy. Depth 0 was a no-op that compared equal
   every time, so the first probe reported a minimal tail of **0 for every field**, i.e. "the
   alarm needs nothing", and the headline would have been 13 bytes. V6b was written precisely
   to disbelieve a tail of 0 and it failed on the first run. Depth 0 is now spelled `[]`.
3. **Five of the eighteen alarm plugins were never enabled.** `settings.enable` matches
   `plugin.name`, not the file name: `boluswizardpreview.js` registers as `bwp`, and
   `cannulaage`/`sensorage`/`insulinage`/`batteryage` register as `cage`/`sage`/`iage`/`bage`.
   An enable list written from file names silently ran 13 of 18 plugins — including omitting
   the only plugin that reads the profile to decide an alarm. Before the fix, `profiles` and
   all four derived change arrays measured as INERT. This is the *corpus* vacuity mode, and
   nothing in the run looked wrong.

### 5.2 `lib/plugins/insulinage.js:92` — an upstream defect, reported not fixed

```js
// insulinage.js:92
if (insulinInfo.age >= insulinInfo.urgent) {      // insulinInfo.urgent is never assigned
```

against its three siblings:

```js
// cannulaage.js:87 · sensorage.js:141 · batteryage.js:87
if (cannulaInfo.age >= prefs.urgent) {
```

`insulinInfo.urgent` is `undefined`, and `number >= undefined` is always `false`. The URGENT
branch — `'Insulin reservoir change overdue!'`, `pushoverSound: 'persistent'` — is
unreachable. The plugin falls through to the WARN branch and notifies once, at WARN, at
exactly `prefs.warn` (48 h); past 72 h it does nothing further.

Measured: at 72 h + 10 min, which fires `cage` at URGENT, `iage` computes `age: 72`,
`level: 1` (WARN) and produces no notification at all, because `sendNotification` is set from
the WARN branch's `age === prefs.warn` test and 72 ≠ 48. At 48 h + 10 min it emits
`1|IAGE|iage|`.

This is a **safety-relevant defect in shipped single-tenant Nightscout**, independent of
multitenancy, and it belongs upstream on its own. It is **not** patched in the worktree,
per D12. Carried by check V7 so it cannot decay into prose. A maintainer should confirm the
intended behaviour before any fix: changing `insulinInfo.urgent` to `prefs.urgent` would
start emitting an URGENT alarm that no existing deployment has ever received, which is a
behaviour change users will notice.

---

## 6. What this means for `ns-evaluator` (D5, phase 4)

The brief lists four things a per-tenant evaluator needs. Three were already settled; this
sizes the fourth.

- **The tenant a change belongs to** — free, via `tenant_id` on every row.
- **That tenant's thresholds and alarm settings** — landed, T3.3 `deriveEnv`.
- **A socket room to emit into** — landed, T3.5.
- **That tenant's `ddata`** — **32.7 KB, materialised per evaluation, not held resident.**

Consequences:

1. **The evaluator should be stateless and query-driven, not resident.** 32.7 KB is a
   transient working set: materialise, evaluate, discard. The only alarm state that must be
   durable is ack/snooze, which is a few hundred bytes per tenant and is T3.4's problem, not
   a residency problem. This strengthens {R} §12.6's option C rather than qualifying it.
2. **The window is expressible as a query.** Every field in §4.3 is "the newest *n* of a type
   within a time bound" — `dataloader.js:360` and `:416` already issue two of them as `count: 1`
   queries. An evaluator woken by the phase-4 replication-slot reader can fetch its slice
   with a handful of indexed lookups rather than by maintaining a resident copy.
3. **1.94 ms of synchronous work per evaluation** sets the per-process ceiling. At a 30 %
   event-loop budget that is ~155 evaluations per second per process; whether that binds
   depends on how often tenants are woken, which this does not measure.
4. **`cob.setProperties` is roughly three quarters of the cost of the resident path and ~0 of the windowed
   one.** Anyone who fixes `cob` improves single-tenant Nightscout today and changes nothing
   about the evaluator's number, because the window already avoids it. That is an argument
   for doing the window rather than the optimisation.

---

## 7. Honest limits — what was not measured, and why

1. **No database, no network, no Mongo, no Postgres.** Every number is local CPU and
   serialised bytes. The evaluator's real cost is dominated by fetching its 32.7 KB, which
   this harness cannot see. This is the same gap {R} §12.7 item 1 names, and it remains the
   highest-value unrun experiment.
2. **Bytes are `JSON.stringify` UTF-8 length, not retained heap.** {R} §12.4's 2,652 KB is a
   heap measurement and is **not** comparable to this document's 852.1 KB — the same data
   costs roughly 2–3× more as live V8 objects than as JSON. Compare ratios here, not
   absolutes, against {R}.
3. **The Proxy cannot see a value already destructured into a local.** `var sgvs =
   sbx.data.sgvs` is recorded once and every subsequent element access is invisible, so the
   inventory is at top-level field granularity only. The knockout and the depth probe do not
   depend on the Proxy, which is why they carry the conclusion and the inventory does not.
4. **`ddata`'s own methods bypass the Proxy.** `clone`, `processTreatments`,
   `recentDeviceStatus` and the rest close over the `ddata` local inside `init()`, not over
   `this`. Their internal reads are invisible. That is why the clone is instrumented
   separately.
5. **Reads inside `sbx.data.profile` are invisible.** `sandbox.js:52,60-62` replaces the cloned
   `profiles` array with a `profilefunctions` object. What is visible — and measured — is
   that `serverInit` reads `profiles`, `profileTreatments`, `tempbasalTreatments` and
   `combobolusTreatments` off the live `ddata` on every cycle regardless of outcome.
6. **`webhook` was not enabled.** It ships in a real server boot and makes an outbound HTTP
   call per cycle. It reads the same last-SGV the others do, so it should not change the
   slice, but its cost is not in the 27.5 ms.
7. **One fixture shape.** 576 SGVs at 5 min, 600 treatments at 4 min, 576 devicestatus, one
   profile, mg/dL, distinct `_id`s. The empirical minimal tails in §4.1 are properties of
   *this* fixture — §4.3 exists because of it. Nothing was measured at mmol/L, and nothing at
   a site with no devicestatus, which is exactly the configuration in which `treatments`
   needs the full DIA window.
8. **Nine scenarios, not the full alarm space.** `errorcodes`, `xdripjs`, `pump`, `loop`,
   `openaps`, `upbat` and `dbsize` all have `checkNotifications` and none of them was driven
   into an alarming state. Each reads the newest devicestatus document or a scalar, so they
   should fall inside the §4.3 window, but **that is inference, not measurement**. A field
   that is alarm-critical only for one of those plugins would be reported INERT here.
9. **Announcement treatments were not exercised.** `treatmentnotify.requestAnnouncementNotify`
   can raise a WARN/URGENT from a treatment's own `mgdl`, and announcements bypass snoozing.
   That path would make `treatments` critical for a second, independent reason.
10. **Ack/snooze state is out of scope.** Every trial starts with a fresh
    `lib/notifications.js`, so nothing here measures how a per-process ack map behaves across
    tenants — that is T3.4, and its finding (per-process, non-durable, invisible to siblings)
    stands untouched.
11. **`cob.setProperties`'s ~74 % share was attributed, not characterised.** Whether it is
    quadratic in treatments, and whether it shares a shape with the two scans {R} §1 found,
    was not measured. It is the obvious next thing.
12. **The worktree named in the brief was deleted mid-run.** All figures were re-taken on a
    throwaway worktree restored at the same commit `29749d92` with `node_modules` symlinked
    from `externals/work/crm-seam`; the module set is therefore that checkout's, not one
    installed from `29749d92`'s own lockfile. Every number in this document comes from that
    single re-run, and the checks pass on it.

---

## 8. Reproducing

```
git -C <cgm-remote-monitor> worktree add --detach /tmp/crm-alarm 29749d92
ln -s <a checkout with node_modules>/node_modules /tmp/crm-alarm/node_modules
node tools/qc/alarm-critical-slice.js --root /tmp/crm-alarm          # human-readable
node tools/qc/alarm-critical-slice.js --root /tmp/crm-alarm --json   # the raw record
```

Exit code is 0 only if all 15 non-vacuity checks pass. The harness writes nothing, to either
repository.
