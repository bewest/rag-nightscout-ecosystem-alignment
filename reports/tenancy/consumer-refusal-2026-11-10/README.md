# Realtime consumer refusal under evaluator timer churn

*Contributor-facing measurement record, captured 2026-11-10. Not edited after capture. Lane
`codex/consumer-refusal-20261110`; local, unpushed. Settles the suspected pre-existing defect reported by the
[activity-eligibility lane](../activity-eligibility-2026-11-10/README.md) ("evaluator timers at 150 ms make the realtime
consumer refuse changed output on unmodified `b70ad83f`").*

## Verdict

**Reproduced**, mechanism diagnosed. The refusal is a product behaviour, and it also occurs at the deployed
timer intervals. The reported outcome "nothing delivered within 10 s" depends on the native fixture's consumer
timers (poll/retry 1,000,000 ms), which never re-drive a refused consumer. With the deployed consumer timers
(1,000 ms), every delivery completed (14/14). Fixed on the lane branch; a second, non-throwing path under the
same churn is left open as a decision (below).

## Anchors

| tree | ref | commit |
|---|---|---|
| lane head | `codex/consumer-refusal-20261110` | `1adb17f8533d0d9529042d57e3b4be07275f94a8` |
| lane base = #8898 head | `official/workspace/multitenant-20261102`, `refs/pull/8898/head` | `b70ad83fa4cdaeb7e6023137a05bd811d7db606a` |
| `official/dev` | | `4a482627bfdafb1fef8dcbe0ac6c484811cae563` |
| alignment `main` at writing | | `3efd647a492c84763eae09cf8fe8b1f44f62e1f8` |

Worktree `externals/work/crm-consumer-refusal-20261110`. Node v22.23.4. PostgreSQL 16.15 in a disposable container,
`postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea`, bound to 127.0.0.1, removed
afterwards. No MongoDB. Synthetic tenants A and B, synthetic readings only.

## Mechanism (at `b70ad83f`)

1. Every evaluator cycle, time-only included, publishes a new `last` with `outputRevision: ++state.revision`
   (`lib/server/serve/evaluator-runtime.js:82`). The recovery and time timers call `all()` directly
   (`evaluator-runtime.js:169-170`) and **do not wake the consumer**. Only the explicit `acquire`/`tick` wrapper
   wakes it (`lib/server/serve/evaluator-preview.js:49-52`).
2. `producer.select` captures `observed = current(tenant)`, then checks `unchanged()`, which requires the same
   `runtimeId`/`outputRevision`/`inputCheckpoint` (`lib/tenant-notifications/producer.js:21-28`). It checks
   inside the store transaction after the suppression read (`producer.js:32`) and again after commit
   (`producer.js:46`). A publication in that window throws `NOTIFICATION_PRODUCER_STALE`. Measured selection
   time is 18-55 ms. The two timers fire together, and each burst publishes two cycles per tenant within about 40 ms.
3. Two paths reach it:
   - **drain**: `lib/server/serve/evaluator-consumers.js:37` `producer.select` throws. The catch at
     `evaluator-consumers.js:49-53` records `refused` / `EVALUATOR_CONSUMER_REFUSED` and does not re-enqueue.
   - **attempt**: `notifier.retry` → `attempt` commits the request as `attempting` with
     `attempt_until = at + attemptTimeoutMs` (`lib/tenant-notifications/component.js:79`). `eligible()` then calls
     `selectCycle` (`component.js:31`, `:38`), which throws, and the error escapes `attempt` with the row still
     `attempting`. `due()` returns an attempting row only after `attempt_until`
     (`lib/tenant-notifications/postgres.js:125`).
4. Nothing re-drives the consumer until its own poll/retry timer fires (`evaluator-consumers.js:74-75`). In the native
   fixture those are 1,000,000 ms (`tests/fixtures/evaluator-consumers-native.js:83`), hence "stuck `attempting`,
   nothing delivered".

Diagnosed with temporary probes (since removed) that wrote to a scratch file: the swallowed error in the drain catch,
`producer.select` start/duration, and evaluator cycle start/end, publication and timer fire. Two refusals per failing
run, both `NOTIFICATION_PRODUCER_STALE`: one at `producer.js:46` via `component.js:38` ← `:83`, one at `producer.js:32`
via the drain.

**Why the reported failure looked interval-bound:** the failure is phase-locked to the test's own sequence. The
timers start at boot readiness. The test's `acquire`+`wake` consumer work runs from about +180 ms to +330 ms
after that. Any interval up to about 330 ms puts the first timer burst inside it, and 600 ms or 1000 ms at the
same phase never does. The phase-0 passes at 600/1000 ms therefore do not show that production intervals are
safe. Random-phase runs at 1000 ms do reach the refusal (below).

## Measurements

Test: `tests/evaluator-consumer-timer-churn.integration.test.js` on the lane (actual selected evaluator role as a
child, actual realtime consumer, restricted PostgreSQL, controlled UDS sink). Steps: A at 50 and B at 111, boot
with the evaluator timers at the stated interval, upload A at 40, then `acquire` (which also wakes the consumer),
`wake` and `flush`.

### Before the fix (`b70ad83f` code), delivery of the changed reading within the deadline

Runs marked † carried the temporary diagnostic probes (synchronous file writes on the consumer path, which shift timing).

| evaluator timers | consumer timers (poll/retry, attempt) | phase | delivered | runs logging a refusal |
|---|---|---|---|---|
| 150 ms | fixture 1e6 / 1e6, 5000 | 0 | **0/5** (4†) | 4/4 probed (2 each) |
| 300 ms | fixture | 0 | **0/4** (4†) | 4/4 probed (2 each) |
| 600 ms | fixture | 0 | 3/3† | 0/3 |
| 1000 ms | fixture | 0 | 3/3† | 0/3 |
| 1000 ms | fixture | random 0-1000 | 10/10† | **3/10** (masked by the second drain) |
| 1000 ms | deployed 1000 / 1000, 10000 | random | 10/10†, latency 185-305 ms | **5/10** (2-3 each) |
| 150 ms | deployed | random | 4/4†, latency 242-2931 ms | 4/4 (1-9 each) |

Deployed consumer and evaluator intervals are from `deploy/multitenant/config.js:96-103` (`recoveryIntervalMs`/`timeIntervalMs`
1000, `pollIntervalMs`/`retryIntervalMs` 1000, `attemptTimeoutMs` 10000), the only deployment configuration in the tree.
`docs/m5-evaluator-preview.md:23` describes the intervals as explicit configuration with no default.

### The committed regression case (no probes): consumer health right after `flush`

| code under test | 150 ms, phase 0 | 300 ms, phase 0 |
|---|---|---|
| `b70ad83f` producer | **3/3 `EVALUATOR_CONSUMER_REFUSED`** | 0/2 refused |
| fix (`1adb17f8`) | 0/6 refused | 0/3 refused |
| control: fix with `STALE_RESELECTS = 0` | 1/2 refused | not run |

Without the probes, 300 ms at phase 0 no longer collides. The native case is phase-sensitive, so the
deterministic proof is the unit pair below.

### Controlled interleaving (deterministic, no timers): `tests/notification-producer.test.js`

The suppression reader publishes exactly one newer evaluator output (same reading, next `outputRevision`) during a
selection or during an attempt.

| case | `b70ad83f` | fix | control `STALE_RESELECTS = 0` |
|---|---|---|---|
| `selects again against the newer evaluator output published during a selection instead of refusing` | red: `NOTIFICATION_PRODUCER_STALE` at `producer.js:32` | green: state output `['config','runtime-one',2,0]` | red, same symptom |
| `hands off a committed request when a newer evaluator output is published during its attempt` | red: `NOTIFICATION_PRODUCER_STALE` via `component.js:31` ← `:83` | green: original request `accepted`, one effect | red, same symptom |

Each control was reverted by copying the saved fixed file back (`cmp` identical); the green rerun gave 7 passing.

## Fix (`1adb17f8`, 4 files)

`lib/tenant-notifications/producer.js`: `select` runs the selection again on `NOTIFICATION_PRODUCER_STALE`, up to
`STALE_RESELECTS = 3` more passes, then refuses as before. Any other error, or a closed producer, still throws
immediately. A stale pass either rolled back (`producer.js:32`, inside the transaction) or committed the older output,
which the next pass supersedes (`:46`). The freshness checks themselves are unchanged. The fix covers both the
drain path and the attempt path, because `selectCycle` is `producer.select`.

| check at `1adb17f8` | result |
|---|---|
| unit/protocol: evaluator-consumer-native-observation, evaluator-control-readiness, evaluator-consumers, evaluator-consumer-open-order, multitenant-inventory, notification-producer-state, notification-producer, tenant-operation-window, tenant-notifications, tenant-startup-admission | 97 passing |
| native `NS_EVALUATOR_CONSUMERS_TEST=1`: `evaluator-consumers.integration` | 5 passing |
| native `NS_TENANT_NOTIFICATIONS_TEST=1`: `tenant-notifications.integration` | 7 passing |
| native `tenant-notification-native-restoration` | 1 passing |
| native `evaluator-consumer-timer-churn.integration` (new) | 1 passing |
| `node scripts/test-tiers.js check` | `615 test files, 8 tiers: ok` |
| `npm run lint` | 0 errors, 49 warnings (the activity lane recorded 49 at base) |

The full suite, browser and corpus acceptance were not run here; they belong to the coordinator's frozen candidate.

## Not fixed: the freshness gate under churn (decision)

With the fix, refusals were 0 in every run, but delivery of the changed reading under 150 ms churn with the fixture's
manual consumer timers was not guaranteed:

| fix, fixture consumer timers | delivered |
|---|---|
| 150 ms phase 0, deadline 10 s (†) | 5/6 |
| 300 ms phase 0, deadline 10 s (†) | 3/3 |
| 150 ms random phase, deadline 10 s (†) | 3/4 |
| 150 ms phase 0 / 300 ms phase 0, at the moment of `flush` (no probe) | 3/5, 3/3 |

Mechanism of the remainder (read from the traces): `eligible()` compares two selections taken either side of the
suppression check and requires an equal `outputRevision` (`component.js:38-43`). A time-only publication between them
returns `false`, so `attempt` cancels the request (`component.js:83`) or defers it with the row left `attempting`
until its deadline (`component.js:92`). This is a gate, not an error, and it is intentional ("a config/allowlist
change while the suppression read was pending cannot admit old work"). The consumer's own timer re-drives it. The
evaluator's timer publications do not.

Options for the maintainer (multitenant only; single tenant does not run this code):

- **(a) Timer publications wake the consumer.** `evaluator-runtime.js` timers notify the consumer as the explicit
  `acquire`/`tick` wrapper already does (`evaluator-preview.js:49-52`). Every published output then gets a consumer
  pass, which matches the `realtime-cycle` policy. The gate stays strict. Cost: one coalesced drain per publication
  per tenant (unmeasured).
- **(b) Relax the gate.** Compare emitted effects instead of `outputRevision` for time-only republishes. This
  changes a freshness rule that guards against admitting old work.

Recommendation, if asked: (a). It keeps the safety gate unchanged and the clinical/delivery semantics as
designed, and it removes the dependence on the consumer's poll interval for timer-driven output. Its throughput
cost is unmeasured.

## Operator-visible effect (multitenant preview, not in any release)

- Measured at the deployed intervals: consumer health intermittently reports `EVALUATOR_CONSUMER_REFUSED` (5/10 runs),
  and delivery is delayed by up to one consumer poll (all deliveries within 305 ms at 1000 ms timers; up to
  2.9 s under 150 ms churn).
- Read-derived, not observed in 14 deployed-interval runs: a request left `attempting` by the attempt path
  waits for `attemptTimeoutMs` (10 s deployed) before `due()` returns it.
- With consumer poll/retry intervals much longer than the evaluator's, a refused or deferred handoff waits for
  the consumer's next poll; the fixture's 1,000,000 ms is the extreme case.

## Proposed register entry (no id allocated)

> **Realtime consumer refuses when the evaluator's own timers publish during a selection.** *Multitenant evaluator
> preview (#8898 workspace); not released.* `producer.select` treats a newer evaluator output published between
> observing and committing as `NOTIFICATION_PRODUCER_STALE` (`lib/tenant-notifications/producer.js:32,46` at
> `b70ad83f`). The coordinator records `EVALUATOR_CONSUMER_REFUSED` without re-driving
> (`lib/server/serve/evaluator-consumers.js:49-53`). Inside an attempt, the error escapes after the request is
> committed `attempting` (`lib/tenant-notifications/component.js:79,83`). The evaluator's timers publish without
> waking the consumer (`lib/server/serve/evaluator-runtime.js:169-170`), so the handoff waits for the consumer's
> next poll, or for `attemptTimeoutMs` for an attempting row. **Basis:** reproduced (native, 150 ms timers 3/3
> refused; deployed 1000 ms intervals, refusal in 5/10 random-phase runs, delivery delayed by at most one poll;
> deterministic controlled-interleaving unit pair red/green). **Status:** fixed on `codex/consumer-refusal-20261110`
> `1adb17f8` (bounded reselect); not merged. **Related, open:** freshness gate in `eligible()` defers or cancels
> under churn with no wake from timer publications; decision (a)/(b) above.

Evidence: this record; lane handoff `externals/work/HANDOFF-consumer-refusal-20261110.md` (local).

## Addendum 2026-11-10: revision-on-content-change stopped at the reader inventory

Decision [`evaluator-revision-on-content-change`](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#evaluator-revision-on-content-change)
(alignment `main` `b9e78338`). Lane head unchanged at `1adb17f8`, tree clean. No code was changed: one reader relies on
the per-cycle bump, so the lane stopped and reported, as instructed.

**What changes between cycles over unchanged data** (reproduced natively; actual evaluator role, one synthetic reading,
`tick`/`acquire` over IPC, including one tick 61 s later): only `outputRevision`, `result.evaluationRevision`, `trigger`
and `result.now`. `checkpoint`, `progress`, `emitted`, `requested` and `properties` (`bgnow`, `buckets`, `direction`)
were identical. A content digest over those five fields would therefore hold the revision on every timer cycle.

**Readers of the evaluator's `last` / `outputRevision`** (at `1adb17f8`):

| reader | use | per-cycle bump |
|---|---|---|
| `lib/tenant-notifications/producer-state.js:57-68` | each new `[identity, runtimeId, outputRevision, inputCheckpoint]` is a fresh cycle: re-runs legacy `notifications.process`, which re-emits the active unsnoozed alarm | **relies on it** |
| `tests/evaluator-consumers.integration.test.js:44-45` `M5_CONSUMER_NEW_RT_CYCLE` | a `tick` over identical data must deliver a second realtime event | **relies on it** |
| activity lane `tests/tenant-activity.integration.test.js:128` (`07981b55`) `ACTIVITY_B_UNAFFECTED` | B's health `outputRevision` must advance by more than 2 over the timer window | relies on it (test oracle) |
| `lib/tenant-notifications/producer.js:36-39` `unchanged()` | runtimeId/outputRevision/inputCheckpoint equality and `result` object identity | no; benefits only if an unchanged cycle keeps the same frozen `last` object |
| `lib/tenant-notifications/producer.js:60-61`, `component.js:22-24,39-40,125` | the producer's own store revision, not the evaluator's | no (indirect: it moves when the producer state moves) |
| `lib/tenant-alarms/cycle.js:11-13,24` | shape validation; the revision must not change within one cycle | no |
| `lib/server/serve/evaluator-runtime.js:146,149-150` | health report, `last()` | no (reporting) |

`lib/server/realtime/runtime.js` keeps its own `cell.last` and does not read the evaluator's revision.

**Why the reliance is behavioural.** Legacy single-tenant Nightscout re-emits the highest unsnoozed alarm on every
processing cycle (`lib/notifications.js:131-165`, `emitNotification` at `:156`), gated only by the ack silence
window (`:63`). Processing runs on every heartbeat tick (`lib/server/bootevent.js:537-540`; `heartbeat` default 60 s,
`lib/settings.js:38`) and on each data-received event. The multitenant producer reproduces that repeat by treating
each evaluator cycle as fresh. Under the decision as worded, a time-only cycle with identical output keeps its
revision, so `fresh` is false and an unacknowledged alarm is delivered once per content change, not once per cycle. That
is a change from single-tenant behaviour. Read-derived: the client-side effect of fewer repeats (e.g. a client that
connects after the first delivery) was not measured.

Related measured fact: at the deployed `timeIntervalMs` 1000, the multitenant consumer re-delivers an active alarm about
once per second per tenant, against legacy's once per heartbeat (60 s default).

**Questions for the maintainer before implementation:**

1. Should alarm repetition stay per cycle (as in single tenant), become per content change, or follow a separate
   repeat clock (e.g. the legacy heartbeat interval)?
2. If repetition is kept, should the producer's `fresh` key be decoupled from the evaluator revision (for example, a
   repeat tick counter driven by a heartbeat), so the revision can still move only on content change?

## Addendum 2026-11-10 (second): revision on content change and the alarm repeat clock

Decisions [`evaluator-revision-on-content-change`](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#evaluator-revision-on-content-change)
and [`alarm-repeat-clock`](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#alarm-repeat-clock) (alignment `main`
`fee6e40e`). Lane `codex/consumer-refusal-20261110`: `1adb17f8` → `1d39c924` (telemetry) → **`956d0940`** (behaviour).
PostgreSQL 16.15 disposable container (same digest), removed afterwards.

### What changed (`956d0940`)

- **Evaluator** (`lib/server/serve/evaluator-runtime.js`): content is a canonical SHA-256 digest of `checkpoint`,
  `progress`, `emitted`, `requested` and `properties` (exported `CONTENT`, `contentDigest`). `now`,
  `evaluationRevision` and `trigger` are per-cycle metadata. Identical content keeps `outputRevision` and the same
  frozen `last` object. A new revision calls `onRevision(tenant)`. Health adds `cycles` (from `1d39c924`).
- **Producer** (`lib/tenant-notifications/producer-state.js`, `producer.js`): when the current output requests any
  notification (`armed`), the legacy processing of that output runs again once `at >= repeatAt`, at time `at`.
  `repeatAt = at + heartbeat` after each processing. `heartbeat` is the tenant's single-site setting in seconds
  (`environment.js:13` CLIENT_KEYS; the owner catalogue carries it too). If it is unset or not a positive number, the
  default is `lib/settings.js:38` (60). Silence is decided by `notifications.js:63` as before, and the
  suppression check (`component.js:35`) still applies at handoff.
- **Consumer** (`lib/server/serve/evaluator-consumers.js`, `evaluator-preview.js`): `revised(tenant)` wakes a tenant
  with a pending request, an armed repeat clock or a current output that requests a notification. A one-shot wake
  fires at the producer's `repeatAt`, with a 1 s floor for an overdue time. Health adds `passes`, `selections`
  and `repeatAt` (the first two from `1d39c924`). The stale-selection retry from `1adb17f8` is kept.

### Content between cycles over unchanged data (reproduced, before this change)

Only `outputRevision`, `result.evaluationRevision`, `trigger` and `result.now` differed across ticks and
acquisitions, including one 61 s later. With the stale-data plugin (single-site env shape, below), only time passing
(20 min) adds a level-1 "Stale data, check rig?" request and drops `direction` from `properties`.

### Measurements, deployed intervals (`deploy/multitenant/config.js:96-103`), two tenants each with an active low, random phase

Test `tests/evaluator-consumer-load.integration.test.js`, `NS_CONSUMER_LOAD_HEARTBEAT_S=60 NS_CONSUMER_LOAD_WINDOW_MS=60000`,
3 runs each. Values are per tenant per minute and were identical for both tenants.

| | evaluator cycles | output revisions | consumer passes | selections | alarm deliveries per active alarm | changed-reading latency | refused | stuck attempting |
|---|---|---|---|---|---|---|---|---|
| before (`1d39c924` = `1adb17f8` + counters) | 118-120 | 118-120 | 119-120 | 359-360 | **60** | 224, 1095, 1115 ms | 0 | 0 |
| after (`956d0940` code) | 120 | **0** | 121 | **125** | **1** | 467, 1032, 1043 ms | 0 | 0 |

At the CI setting (heartbeat 5 s, window 21 s), before: 120 revisions, 360 selections, 60 deliveries/min, latency 256 ms.
After: 0 revisions, 177 selections, 11.4 deliveries/min (expected 12), latency 595 ms, refused 0, stuck 0.
Passes stay at about 120/min after the change because the deployed consumer poll and retry timers (1000 ms each)
dominate. The change removes the per-cycle writes and handoffs, not the polls. The changed reading is picked up by the
evaluator's own recovery timer (no explicit trigger exists in production: no caller of `acquire` outside the IPC
driver). At the deployed 1 s poll, its latency is bounded by the poll before and after.

**150 ms churn** (`tests/evaluator-consumer-timer-churn.integration.test.js`, delivery now required): changed reading
delivered **8/8** (3 at phase 0, 5 random), 197-253 ms. Case "picked up only by the evaluator timers", with the
fixture's 1,000,000 ms consumer timers and no trigger, so only the targeted wake can deliver: **8/8**, 290-373 ms.

### Controls (each red, then restored by copying the saved file back; `cmp` identical)

| control | edit | red, exact symptom |
|---|---|---|
| bump the revision every cycle | runtime `const changed = true` | unit `EVALUATOR_IDENTICAL_CONTENT_KEEPS_REVISION`; load `ALARM_REPEAT_ON_HEARTBEAT 1 delivered 21, expected about 4.2` (selections 451/min); native M5 case 1 red |
| digest ignores a time-driven change | digest over `checkpoint`,`progress` only | unit `only time passed and the stale-data alarm appeared` (the held output hides the stale-data alarm from consumers) and `emitted is content` |
| remove the repeat clock | producer-state `const repeat = false && …` | unit `PRODUCER_REPEAT_ON_HEARTBEAT`, `EVALUATOR_CONSUMER_RT_POLICY alarm repeats on the heartbeat clock`, `EVALUATOR_CONSUMER_OUTPUT_POLL …`; load `ALARM_REPEAT_ON_HEARTBEAT 1 delivered 0` and `ALARM_REPEAT_OTHER_TENANT` |
| ack silence ignored | `notifications.js:63` → `if (true)` | unit `PRODUCER_ACK_SILENCE_HOLDS`. **Native stayed green** (0 acknowledged repeats): the outbox suppression check `allows` → `reader.allows` (`component.js:35`, `tenant-alarms/postgres.js:95`) is a second, independent gate. With both broken (`allows: async () => true` as well): `ALARM_ACK_SILENCE_HOLDS` with 3 acknowledged repeats |
| remove the targeted wake | preview `onRevision: undefined` | native `CONSUMER_TARGETED_WAKE_LATENCY` (latency null). The load test's latency assertion stays green at the deployed 1 s poll, as expected: the poll alone delivers within a second |

The repeat-clock control also showed a hot loop: with `repeatAt` left in the past, the one-shot re-armed at 0 ms
(2368 passes/min). The real code always advances an overdue `repeatAt`; the 1 s floor added in `956d0940` bounds any
regression. With the floor, the same broken state gives 120 passes/min.

### Oracles changed (the per-cycle reliance), with what replaces them

| oracle | was | now |
|---|---|---|
| `tests/evaluator-consumers.integration.test.js` case 1 `M5_CONSUMER_NEW_RT_CYCLE` | `tick` over identical data delivers a second event | tenant `heartbeat` 3 s; `tick` before the heartbeat delivers nothing (`M5_CONSUMER_IDENTICAL_CYCLE_NO_REPEAT`); the coordinator's repeat-clock wake delivers the second event with a new UUID |
| same file, case 4 (`:87`), B independent | `tick` B over identical data delivers for B | a new B reading plus `acquire` B delivers for B |
| `tests/evaluator-consumers.test.js` `EVALUATOR_CONSUMER_RT_POLICY`, `EVALUATOR_CONSUMER_OUTPUT_POLL`, B `requests + 1` | a `tick` repeats | advance the fixture clock 60 s (default heartbeat), then the tick or poll repeats; adds `EVALUATOR_CONSUMER_NO_REPEAT_BEFORE_HEARTBEAT` |
| same file, "clinical cycle does not wait for delivery" | `outputRevision` increases | evaluator `cycles` increases |
| `tests/evaluator-preview-runtime.test.js` "retries unchanged input" | revision increases | `cycles` increases and the revision is unchanged |

**Activity lane (not edited; for the join coordinator):** `tests/tenant-activity.integration.test.js:128` on
`codex/activity-eligibility-20261110` (`07981b55`). Replace
`const bBefore = tenantHealth(await worker.call('health'), lab.B).outputRevision;` with
`const bBefore = tenantHealth(await worker.call('health'), lab.B).cycles;`, and replace
`assert.ok(tenantHealth(health, lab.B).outputRevision > bBefore + 2, 'ACTIVITY_B_UNAFFECTED B kept cycling on the actual timers');`
with `assert.ok(tenantHealth(health, lab.B).cycles > bBefore + 2, 'ACTIVITY_B_UNAFFECTED B kept cycling on the actual timers');`.
(`cycles` is reported by `evaluator-runtime.js` health from `1d39c924`. B's data does not change in that window, so
its `outputRevision` now stays put by design.)

### Checks at `956d0940`

| check | result |
|---|---|
| unit/protocol: 16 files (evaluator-consumer*, evaluator-control-readiness, evaluator-preview-runtime, evaluator-runtime-content, multitenant-inventory, notification-producer*, tenant-operation-window, tenant-notifications, tenant-startup-admission, tenant-deployment-operations, realtime-evaluator-observer, tenant-projection-evaluator, tenant-maintenance-window) | 178 passing |
| native: evaluator-consumers.integration, tenant-notifications.integration, tenant-notification-native-restoration, evaluator-consumer-timer-churn, evaluator-consumer-load | 17 passing |
| `node scripts/test-tiers.js check` | `617 test files, 8 tiers: ok` |
| eslint on changed files | 0 errors; `npm run lint` 0 errors, 49 warnings |

### Found on the way (not changed)

- **The stale-data alarm cannot be enabled for a multitenant tenant.** `timeago` alerts need
  `extendedSettings.timeago.enableAlerts` (`lib/plugins/timeago.js:20`). The tenant environment copies only
  `extendedSettings.devicestatus` (`lib/server/tenant-app/environment.js:54-57`). The runtime test builds the
  single-site env shape directly for that reason. Read-derived, not run against a tenant config.
- A tenant with no pending request, no armed repeat and a current output that requests no notification is not woken
  on a content change; it waits for the consumer poll, as the decisions specify. A newly appearing alarm is covered
  (its output requests a notification), and so is the clear when an alarm ends (the repeat clock was armed).
