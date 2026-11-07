# Durable event delivery contract for multitenant consumers

*Contributor-facing design contract, 2026-11-06, design direction adopted by the maintainer.
Batch B7 of the [integration batching plan](multitenant-integration-batching-plan-2026-11-06.md);
queue home `MT-RUNTIME-PLAN` (in-progress, no runnable gate yet). It reconciles
D-EVENT's in-process commit event with D6's change-feed design and the
transactional tenant clock, and names the entry bar before any distributed
evaluator or realtime wiring. It promotes no milestone, selects no provider,
admits nothing to a release candidate, and infers no consistency stronger than
what the cited records reproduced.*

| Anchor | Read from tool output at the time of writing |
|---|---|
| Alignment `main` | `18a9a5420c062aeb6cfe195d0fc0d5fd096509e2` |
| CRM cumulative head (`codex/serial-integration-20261106`) | `35903069b46974cfbaddd8dce00c994fb2562bc3`; every `file:line` below is read at this commit unless it names another |
| Tenant clock lane heads cited through their reports | product `3e76b270`, lower-port fixture `887c4aad`, HTTP fixed-recovery head `3532c1a4` with repair `11770146` |

Every claim is labelled **reproduced** (with the record that ran it) or
**read-derived** (from source or a design page). Designs borrowed by name: the
D6 slot-plus-NOTIFY-plus-poll pattern (execution plan, measured in T4.1), the
transactional tenant commit clock (clock proof plan and its two reports), and
the independent evaluator's retained-cycle policy (R50, R55, seams plan).

## 0. Premise, as read

- D-EVENT (maintainer, 2026-10-31; [decisions.md](../../../releases/cgm-remote-monitor-16.0.0/decisions.md)
  D-EVENT question 1 row) names one in-process event per `write(intent)`,
  carrying the step's `items[]`; delivery between processes is deferred to the
  multitenant roles; a timer serves time-driven alarms only, never catch-up on
  writes; writers that bypass Nightscout are unsupported. **Read-derived.**
- The event as built at `35903069` is `storage-intent-committed`
  (`lib/storage/write-intent.js:4635`), documented at `:4622-4634` as
  "INTERNAL: nothing in lib/ listens". **Read-derived.**
- D6 ([execution plan](multitenancy-decisions.md) §1,
  row D6): change feed = replication slot (spine) + `NOTIFY` (latency) + bounded
  aggregate poll (backstop), `NOTIFY` emitted by the slot reader, never by a
  trigger. T4.1 (same plan, Phase 4) **reproduced** 200/200 rows delivered after
  a stopped reader returned, 0 on re-consume, and a 0.000000% notification-queue
  gauge with reader-emitted `NOTIFY` against 0.019073% from a trigger.
- The [roadmap](multitenant-delivery-roadmap.md) §4 names this
  reconciliation as a design task, and its MT-RUNTIME-PLAN packet asks for
  durable checkpoint ownership, commit coupling, ordering, duplicates, hard and
  soft deletes, configuration invalidation and restart boundaries, with
  executable controls, before one producer/consumer recovery slice.
- The [seams plan](architecture-seams-execution-plan-2026-11-05.md) "Shared
  frame join and multitenant recovery" says a local `EventEmitter` and a cell
  lease cannot establish these guarantees, and that provider selection stays open.

The event payload at the anchored source carries no tenant or stamp. B2 has
since joined the clock locally; the [R56 report](../../../reports/tenancy/tenant-clock-join-2026-11-06.md)
owns that measured baseline. The original source references below remain anchored
to the table above; they are not line references into the joined source.

## 1. Terms

| Term | Meaning in this contract |
|---|---|
| **logical intent event** | the record of one resolved `write(intent)`: collection, source, op, per-record `_id`, `identifier`, `outcome` and problems, counts, `collapsed` flag (`write-intent.js:4656-4678`). It names records; it carries no document contents and no filter (D-EVENT question 3) |
| **commit stamp** | the per-tenant monotone value the transactional tenant clock allocates inside the data transaction and holds through `COMMIT`; persisted on the committed rows as the server-owned modification field. The ordering fence of the clock proof plan |
| **checkpoint** | one consumer's durable position for one tenant: the highest stamp whose complete equal-stamp cohort that consumer has processed. A database row owned by the consumer, never process memory |
| **consumer** | a process that derives state from committed writes: the `evaluator` role (plugins, notifications), the `realtime` role (socket fan-out), a cache, a view materializer. Each has its own checkpoint per tenant |
| **tenant-local evaluator** | the consumer that runs the plugin and notification cycle for one tenant from that tenant's rows under its own tenant binding, retaining one cycle per tenant (R50's policy) |
| **backstop** | the bounded aggregate poll of D6: a periodic per-tenant read of rows with stamp above the checkpoint, which finds what a lost `NOTIFY` did not announce |
| **timer** | the time-driven trigger (`bootevent.js:526` `tick` today) that evaluates alarms whose condition is elapsed time, not a new row |

## 2. The spine: what is durable and what is not

| Thing | Durable | Basis |
|---|---|---|
| the committed rows of a tenant, with their server-owned dates and (under the clock) their commit stamp | **yes**: this is the spine | lower-port proof: rollback leaves "data and durable floor unchanged" and "no queued logical event escapes" (**reproduced**, `tenant-commit-clock-lower-proof`) |
| the tenant clock floor row | **yes**: readiness refuses a missing or stale floor before binding (**reproduced**, lower-port and HTTP fixed-recovery reports) | |
| the in-process `storage-intent-committed` event | **no**: built and emitted only while a listener is attached (`write-intent.js:4682`); an observer failure is logged and the write stays committed (`:4686`); nothing in `lib/` listens | **read-derived** |
| the PostgreSQL ports' post-commit emission | **no**: `withCommitEvents` emits after `connection.transaction()` resolves (`postgres-intent-common.js:42-48`), which has verified `COMMIT` (`postgres-connection.js:59-62`); a crash between those two lines loses the emission and keeps the rows | **read-derived**; "a failed mutating transaction publishes nothing" is **reproduced** by the port corpus (`lib/storage/PORT-CONTRACT.md:141-146`) |
| the `settle` emission for a resolved no-op | **no**, and it is not a spine event at all: it opens no transaction and proves no physical write (`PORT-CONTRACT.md:120-124`, `postgres-intent-common.js:49-53`) | **read-derived** |
| `NOTIFY` | **no**: latency only (D6); a wedged consumer does not fill the queue when the reader emits it (T4.1, **reproduced** 2026-09-15) | |
| a replication slot's unacknowledged WAL | durable while the slot exists; retention horizon is deferred (§9) | T4.1 pinned 234.5 KB for 200 rows across a stop (**reproduced**) |

**Rules.**

1. The spine is the committed rows plus their stamp. A consumer that has the
   rows and its checkpoint needs no event to be correct; events only make it
   faster. This is the D6 shape and the D-EVENT scope decision read together.
2. A consumer's position is a **per-tenant checkpoint stamp owned by the
   consumer and stored in the database**, under that tenant's binding, never in
   process memory. Two consumers never share a checkpoint row; the `evaluator`
   and `realtime` roles advance independently.
3. The logical intent event must carry the **tenant** and the **commit stamp**
   of the write it describes before it is an interprocess message. At
   `35903069` it carries neither (`write-intent.js:4676-4677`); D-EVENT question
   3 already reserved "later the tenant". A consumer that receives an event
   without a stamp treats it as a wake-up only and reads from its checkpoint.
   **Built** on lane `codex/event-payload-20261106` (head `4b5edf02`, three commits
   over `65bb8456`, unpushed): `withCommitEvents.write` captures the tenant from the
   bound scope and the stamp from a new `connection.currentStamp()` on the clock
   decorator when the nested write resolves; settle, Mongo and clock-off carry null.
   Unit 9 passing, controls red for a null stamp (7 / 2) and a remembered tenant (6 / 3),
   focused `clock` run 28 / 1 / 0; the Mongo-gated case is UNMEASURED. The figures are
   the lane's own (`HANDOFF-event-payload-20261106.md`), not re-run here.
4. Commit coupling: the stamp is allocated inside the data transaction and held
   to `COMMIT` (clock proof plan "Proposed invariant"; `postgres-write-clock.js:52`
   per the HTTP report, **read-derived** at the clock head); publication
   happens strictly after the transaction resolves, never inside it, and never
   from a database trigger (D6).

## 3. Ordering and duplicates

Delivery is **at-least-once**. Every consumer is **idempotent on
`(tenant, stamp, collection, identity)`**, where identity is the stored `_id`
with its typed form kept distinct from a same-spelling string (`write-intent.js:4640-4642`
keys them apart; the port corpus preserves typed forms in delete records,
`PORT-CONTRACT.md:125`).

| Guarantee | Holds | Basis |
|---|---|---|
| Two writes for one tenant that both commit receive distinct, increasing stamps, and an exclusive cursor taken after the higher one commits includes the lower one | **yes, under the clock**, for the schedules run: lock wait observed while the lower write is held, no early visibility, ordered rows after release | **reproduced**, lower-port "transaction clock fence"; HTTP "same-tenant concurrent writers" (`1793991708168 → 1793991708169`) |
| The same, without the clock | **no**: an authored detached counter commits distinct stamps yet the lower, later-committing row becomes invisible behind an already-observed higher exclusive cursor | **reproduced** as the alternative-design control, lower-port report |
| Parallel REST reads of two collections share one database revision | **no** | **reproduced**, R49 "parallel reads do not provide a common database revision" |
| Every row has a unique stamp | **no**: two identifier-absent typed twins marked by one mutation share a stamp; a sorted `LIMIT 1` read followed by an exclusive cursor omits the tied second row | **reproduced**, lower-port "existing bulk tie characterization" (that cohort and schedule, not every interface) |
| Stamps across the two write paths (v3 identifier writes and legacy filter writes) are one sequence | **yes under the clock** for the exercised plan: after an intervening committed v3 cursor, two distinct preplanned legacy targets receive later authoritative stamps | **reproduced**, lower-port "earlier legacy plan"; raw import and mixed enabled/disabled writers are outside the captures |
| Equal wall clocks in separate API workers give distinct stamps | **yes** | **reproduced**, HTTP report (`1793991706986 → ...987 → ...988`) |

**Rules that follow.**

1. **Equal-stamp cohorts are the unit of progress.** A consumer records
   checkpoint `s` only after it has read every row with stamp `s`. A page cut by
   a limit inside a cohort records the previous stamp, not `s`. The cursor is
   `stamp > checkpoint`, ordered by stamp then identity, and the page size is
   larger than the largest bulk write the writer admits (the step's resolve cap,
   `RESOLVE_CAP`, bounds the named records in one event; the bulk soft-delete
   case is the reason this rule exists).
2. **Duplicates are expected, not errors.** A replayed row with
   `(tenant, stamp, collection, identity)` at or below the checkpoint is a
   no-op. A replayed row above it is processed once.
3. **Ordering is per tenant only.** No cross-tenant order is promised or needed;
   tenant B progresses while tenant A's writers wait on A's clock row
   (**reproduced**, lower-port "cross-tenant progress" on a shared pool of four;
   HTTP report, same observation).
4. **No cross-collection snapshot.** A consumer that reads entries and
   treatments in two statements may see a later treatment with an earlier
   entries cohort (R49). The evaluator's answer is the retained-cycle policy
   (§7), not a snapshot; a stronger policy needs its own implementation and
   test (seams plan).
5. **Without the clock the contract is not satisfiable by cursor replay.** On a
   backend or configuration without the commit-coupled stamp (single-tenant
   MongoDB under D4, which opens no transaction on a standalone server, seam
   interface §9.1; or PostgreSQL with the opt-in clock off), the in-process bus
   stays the mechanism and this contract does not apply. That is the D-EVENT
   scope decision, not a gap.

## 4. Deletes

| Kind | Status under the contract | Basis |
|---|---|---|
| **soft delete** (the v3 default and every path that marks a record invalid) | an ordinary write: the row stays, its stamp advances, and a consumer that replays it removes the record from its view. A bulk soft delete is one event with many records (or `collapsed` above the cap) and one cohort that may share a stamp (§3 rule 1) | **read-derived** from the step; the tie case **reproduced** in the lower-port report |
| **hard delete** through the intent path (v3 `prune`/autoPrune, `write-intent.js:4606-4613`; permanent delete) | **outside the spine.** The event names the removed ids, but no durable row carries a stamp afterwards, so replay cannot reconstruct it. A consumer learns of it only by re-reading a window and noticing absence. Whether a tombstone is added, and the window the backstop re-reads, are deferred (§9) | **read-derived**; the roadmap's "no timer substitutes for lost writes" applies with equal force here |
| **raw writers that bypass `write(intent)`** (a direct MongoDB upload, an independent SQL client) | **outside the contract**, by decision: writers that go straight to the database are unsupported and xDrip+'s MongoDB upload is deprecated (D-EVENT question 1 row, decisions.md). R50's fixture used exactly such raw writes to show they "emit no process event" (**reproduced**); under the clock they also carry no stamp allocated by the fence | |

A consumer never infers a hard delete from a missing event. It reports what it
replayed; reconciling absence is the backstop's bounded job and its horizon is
a deferred decision.

## 5. Configuration and grant invalidation

**Decision: re-read per cycle, not an event.** Current authority is checked per
operation from a tenant-bound snapshot taken for that operation, and the
evaluator binds each cycle to the settings version it read at the start of
the cycle.

Why this and not an invalidation event:

- R48 **reproduced** that the shipping data-access path consumes one tenant-bound
  SQL snapshot "for every permission and current-name attribution in the
  operation", with no retained cross-request permission cache; its controls
  show the failure mode of the alternative exactly: "reusing an earlier snapshot
  makes committed grant removal's next GET answer 200 instead of 403".
  Revocation-as-event would reintroduce that cache and make its correctness
  depend on at-least-once delivery, the property this contract exists to make
  tolerable rather than load-bearing.
- A grant revocation and a settings change are per-tenant configuration rows
  under D15 and D22; they are not writes to a data collection and do not pass
  through `write(intent)`, so they have no logical intent event to ride on
  today. Whether configuration rows also appear on the feed is deferred (§9);
  a consumer never relies on it.
- R51 keyed its settings differential to actual settings rows and refused on
  stale state (**reproduced**, 12/0 with three semantic controls). Reading the
  settings version at cycle start costs one indexed read per cycle, the same
  order as the T4.1 payload decision ("a consumer told only 'tenant T changed'
  reads under its own tenant binding").

Consequences: a revoked grant stops delivery to the affected socket at the next
operation that checks authority, and the `realtime` role performs that check
per fan-out cycle, not per connection lifetime (the execution plan already
notes that a tenant suspended mid-session is not re-checked after the handshake
under the current socket; that is the behaviour this rule replaces for the
multitenant roles). A settings change takes effect at the next cycle; retained
state keyed to the old version is discarded (§7).

## 6. Restart and catch-up

| Situation | What happens | Covered by |
|---|---|---|
| consumer starts, or restarts after a crash | reads its checkpoint for each tenant it serves, replays `stamp > checkpoint` in cohort order, records the new checkpoint after each complete cohort, then subscribes to `NOTIFY` | replay from the spine |
| crash **after** `COMMIT`, **before** the emission (`postgres-intent-common.js:46-47`) | the rows and stamp are durable; the emission is lost; replay finds the rows | replay, never the publish |
| crash **inside** the transaction | nothing is visible, floor unchanged, no event escapes; the writer gets a sanitized 503 and the same worker continues | **reproduced**: lower-port "actual rollback"; HTTP fixed-recovery operator-abort case (`STORAGE_UNAVAILABLE`, then GET 200 and POST 201 from the same worker) |
| lost `NOTIFY` | the bounded aggregate poll reads `stamp > checkpoint` on its interval and finds the cohort | backstop (D6) |
| slot reader stopped and restarted | rows written meanwhile are delivered once on return; the slot is acknowledged only after the batch's notifications commit | **reproduced**, T4.1 (200/200, 0 on re-consume), on the 2026-09-15 reader |
| time passes with no writes (stale data, missed readings, pump age) | the timer evaluates time-driven alarms from the retained cycle | timer; it reads no new rows and advances no checkpoint |
| a writer's process is killed mid-transaction while holding the fence | the backend stays active until the lock holder is released; the survivor advances the floor by one; this is **not** a rapid-recovery bound | **reproduced** characterization, HTTP report "Node SIGKILL" row; the bound is UNMEASURED |

The rule the roadmap states is kept verbatim in effect: the timer may drive
time-based alarms; it never silently repairs lost write events. A consumer that
finds its checkpoint missing starts from the floor the operator provisioned, and
says so in its health report; it does not invent one.

## 7. Evaluator and notification state

Where that state lives **today** at `35903069`, **read-derived**:

| State | Home today | Scope today |
|---|---|---|
| alarm levels and `lastEmitTime` per group; the per-cycle `requests = { notifies, snoozes }` | `lib/notifications.js:23-74`, reset by `initRequests` each cycle | one process-global `ctx.notifications` |
| ack and snooze | `notifications.ack` at `lib/notifications.js:166-184` deletes `lastEmitTime`; `requestSnooze` at `:118-127` | same object; the web client's ack arrives over the socket. Under D23 (adopted and amended 2026-11-06) the socket protocol is unchanged: `realtime` forwards every socket write and the alarm ack, with the socket's own authorization, to an internal write endpoint on `api`, which runs the write step with the `socket` source label and writes the tenant-keyed ack row that the evaluator consumes from the feed; the result is relayed into the socket acknowledgement, and a failed forward is no acknowledgement |
| the data the cycle evaluates | `ctx.ddata` (`lib/data/ddata.js`), loaded by `lib/data/dataloader.js` from `ddata.lastUpdated`; the cycle runs on `data-loaded` → plugins → `data-processed` → socket `dataUpdate` (`lib/server/bootevent.js:514-551`, `lib/server/websocket.js:122,159`) | one process, one site |
| the write-driven trigger | `data-received` from the socket write paths (`websocket.js:285,538,598,...`) and the timer `tick` (`bootevent.js:526`) | in-process bus |
| private, bounded acquisition that leaves the caller's `ddata` untouched | `lib/data/views/index.js:121-219` and `lib/server/tenant-app/snapshot.js:15-75` (per the seams plan's inventory, R49 **reproduced** the caller-cache-untouched control) | per call |
| the retained cycle (last successful properties and timestamp, kept on a failed cycle, refreshed by the next real trigger) | `lib/server/nonresident.js` on the #8891 profile branch (`2ee8b493`), **not** at `35903069` | one process, one site; R50 and R55 **reproduced** the retention and recovery controls |
| the `evaluator` role | `lib/server/serve/roles.js:27-29`: a summary ("change feed, plugins and notifications; no listener") and no `start` | does not exist as code |

No "memory-ignore" marker exists in `lib/`, `docs/` or `tests/` of the CRM tree
or in this repository's documents; the term in the brief has no source behind
it and is not used here.

**Contract for the multitenant roles**, borrowing R50's retained-cycle policy
and the seams plan's identity rule:

1. Evaluator and notification state is **keyed by
   `(tenant, settings version, plugin set)`** with a bounded lifetime; a key
   change discards the retained cycle rather than carrying it across versions.
   There is no process-global mutable clinical frame.
2. A failed cycle retains the entire prior successful result and timestamp and
   performs no notification handoff; the next real trigger recovers (R50, R55
   `frame-retention` control: null replacing the kept properties is the red).
3. Ack and snooze are **per tenant** writes. D23 names their writer: the
   client acks on the `/alarm` socket as today, `realtime` forwards the ack,
   like every other socket write, unchanged to `api`'s internal write endpoint,
   and `api` persists a tenant-keyed ack row that the evaluator reads from the
   feed like any other committed row, so an ack survives a consumer restart by
   replay and `realtime` holds no storage write authority. A forward that fails
   yields no acknowledgement, so the client's existing no-ack retry applies. The roadmap keeps "owner
   ack/snooze and actual notification delivery" on their separate gates, so the
   row's shape and retention are not decided here, only its key and its writer.
4. The retained cycle's inputs are the tenant's rows at or below the
   consumer's checkpoint; the evaluation instant is recorded with the cycle and
   is not a database revision (R49).

## 8. Entry bar before any implementation

The roadmap asks for executable controls before one producer/consumer recovery
slice. Each row names the predicted green and the exact red symptom; a control
that goes red for a setup reason is not evidence (clock proof plan). All are
**UNMEASURED** today.

| Control | Predicted green assertion | Exact red symptom when the mechanism is broken |
|---|---|---|
| **kill after commit, before publish, then restart** (pause the consumer-facing emission after `connection.transaction()` resolves; kill the writer and the consumer; restart the consumer) | the restarted consumer's tenant view equals a fresh read of the tenant's rows; its checkpoint equals the highest committed stamp | break: checkpoint stored in process memory. Red: the view lacks the last committed cohort and the checkpoint reads the pre-kill value |
| **duplicate replay** (deliver the same cohort twice, once by `NOTIFY` and once by the backstop) | one evaluation, one notification request, same properties; checkpoint unchanged after the second delivery | break: idempotency key dropped to `(tenant, stamp)` or to identity alone. Red: two notification requests for one write, or a typed twin collapses onto its string spelling |
| **soft delete replayed after restart** | the row is absent from the restarted consumer's view and from the realtime delta | break: consumer skips records whose outcome is `deleted`. Red: the deleted record is still in the view |
| **equal-stamp cohort cut by a page** | with a page size smaller than one bulk soft delete, every record of the cohort is processed before the checkpoint advances | break: record the page's last stamp. Red: the tied second row (the lower-port characterization) is never processed |
| **revoked grant** (remove a grant while a socket is connected) | delivery to that socket stops within one fan-out cycle; the next operation answers 403 | break: authority cached at connect time. Red: the socket keeps receiving deltas after revocation (the R48 control's shape, 200 instead of 403) |
| **cross-tenant checkpoint read** (bind tenant A, read B's checkpoint row) | fails closed: zero rows under RLS, or a refused rebind (`postgres-connection.js:44-47`) | break: checkpoint table outside RLS or keyed without the tenant. Red: A reads B's stamp and replays B's rows into A's view |
| **suppressed timer** | with the timer stopped and writes continuing, every write-driven alarm still fires; only time-driven alarms (stale data, time-ago) are missed | break: the timer also reloads rows (today's `timedReloadData`). Red: a write-driven alarm is late by one timer interval, or, inversely, stopping the timer loses nothing because the timer was repairing the feed |
| **lost `NOTIFY`** (drop every notification for an interval) | the backstop delivers the cohort within its bound; the event-driven path delivers nothing | break: backstop disabled. Red: the cohort is never evaluated until the next write |
| **rollback inside the transaction** | no event, no stamp advance, no row | already **reproduced** at the clock head (lower-port "actual rollback", "publish immediately instead of queueing" control: 1 event rather than 0); rerun on the frozen head that joins the clock |

These rows are the gate `MT-RUNTIME-PLAN` lacks today; the queue item keeps
`no-gate` until a runnable instrument exists in `tools/queue/gates/`.

## 9. What this contract does not decide

| Question | Status |
|---|---|
| provider: logical replication slot with `wal2json`-style decoding versus poll-only versus change streams | **deferred, research continuing.** D6 selected the slot as spine on T4.1's 2026-09-15 measurement; the seams plan reopens provider selection; nothing here closes it. The contract is written so that the slot, a poll, or both satisfy it, because the spine is the rows and the stamp, not the transport |
| multi-node consumers: leasing a tenant to one evaluator, failover, split-brain | **deferred.** The seams plan says a cell lease cannot by itself establish these guarantees; the single-machine separate-role reference deployment is the adopted first proof (clock proof plan) |
| retention horizon: how far behind a checkpoint may fall before replay is refused; slot WAL retention; the backstop's re-read window for hard deletes | **UNMEASURED.** T4.1 measured one stop of 200 rows |
| performance budgets: contention, fresh-ingestion latency, lock-held work, evaluator cost per tenant | **UNMEASURED**; the clock reports say so in the same words, and the benchmark is opt-in and pending |
| whether configuration and grant rows appear on the feed | **deferred**; §5 makes consumers correct without it |
| tombstones for hard deletes | **deferred**; §4 keeps hard deletes outside the spine |
| the storage shape and retention of per-tenant ack/snooze rows | separate gate per the roadmap; the writer is settled by D23 (`api`, via the `realtime` forward) |
| which floor the event carries when an outer transaction allocates more stamps after a nested write resolved: the write's own floor (as built, at most the final floor) or the transaction's final floor (readable from the clock state in the after-commit callback) | **decided, maintainer, 2026-11-06: the transaction's final floor.** The event names the cohort that committed together, read from the clock state in the after-commit callback; built on `codex/event-payload-20261106` at `e7baff74a8da0035a2ff473ecadf09123abbdeb7`: the clock hands each after-commit publish the final floor, a nested-allocation test asserts it (unit 134 / 33 / 0; the stamp-null control 7 / 3 with "the event carries the final floor, not the floor at resolve", restored 10), and the Mongo-gated d-event suite ran on MongoDB 8.0.34 at 103 / 0 / 0. Either choice keeps §3 ordering; the final floor makes the event's stamp equal the cohort's stamp |
| anything about single-tenant MongoDB | out of scope; D4 and the D-EVENT scope decision keep the in-process bus there |
| M5/M6 promotion, RC admission, default enablement | **no**; this is a design acceptance input for batch B7, nothing more |

## 10. Decisions this contract makes

For the reviewer's convenience, the decisions above in one list, each one a
sentence the entry bar in §8 can falsify:

1. The spine is committed rows plus their commit stamp; events are latency.
2. A checkpoint is a per-tenant, per-consumer database row under the tenant's
   binding; never process memory.
3. The interprocess event carries tenant and stamp, or is treated as a wake-up.
4. Delivery is at-least-once; consumers are idempotent on
   `(tenant, stamp, collection, typed identity)`.
5. Progress is by complete equal-stamp cohort, never by page.
6. Soft deletes are events; hard deletes and raw writers are outside the spine.
7. Authority and settings are re-read per operation or per cycle, not
   invalidated by event.
8. Replay covers crash-after-commit; the publish covers nothing.
9. The timer drives time-based alarms only and never reloads rows.
10. Evaluator and notification state is keyed by tenant, settings version and
    plugin set, with R50's retention policy.
11. The contract applies only where the commit-coupled stamp exists; the clock
    (batch B2) is therefore a prerequisite of the first recovery slice, and the
    clock is absent from the original anchor `35903069`. B2 has since joined
    it locally; R56 owns the joined baseline and its measured limits.

## 11. Maintainer acceptance and experiments

The maintainer adopted B7's design direction on 2026-11-06 in the B7 approval
chat: proceed with tenant-local durable checkpoints, commit-coupled ordering,
at-least-once replay and idempotent consumers, and use experiments to inform
scalability and performance. The decision is recorded in the
[release decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#b7-durable-multitenant-delivery-2026-11-06).
This accepts the direction and the executable entry bar, not measured distributed
recovery, a performance budget, a provider, milestone promotion or release admission.
`MT-RUNTIME-PLAN` remains in-progress with `no-gate` until its instrument exists.

**What UNMEASURED means.** The named behavior has no applicable executed capture
on the stated assembled source and workload. It is neither a failure nor a pass.
A source reading is a hypothesis; a focused positive and mechanism-specific red
control support only the schedules and source actually exercised. Existing clock
proofs do not establish distributed consumer or notification recovery.

**Correctness experiments before runtime acceptance.** Implement the §8 positives
and paired breaks in an isolated synthetic producer/consumer slice. Also cut the
consumer at each boundary between processing, durable notification handoff and
checkpoint persistence: demonstrate neither a lost required handoff nor a duplicate
request after restart. Provider delivery to a device remains a separate acceptance.
Exercise subscription during concurrent commits so startup cannot depend on an
uncovered gap between catch-up and listening. Measure an update that overwrites a
row, then another update or hard delete before replay: state convergence from current
rows is not proof that every intermediate transition can be recovered. Specify which
transitions the evaluator must preserve and whether a retained log, outbox or
tombstone is required. These are questions for the prototype, not added guarantees.

**Performance experiments before capacity claims.** Pin the assembled head,
hardware, data size and consumer count; compare clock on/off at identical load.
Sweep active and idle tenants, write rate per tenant, burst size, bulk cohorts,
reconnect backlog and slow consumers. Include one hot tenant beside ordinary
tenants on a shared pool. Capture commit-to-view and commit-to-evaluation p50/p95/p99,
clock lock wait/hold time, throughput, pool occupancy, CPU/memory, database reads,
checkpoint writes, replay lag/catch-up duration and retained bytes. Evaluate idle
poll overhead separately: aggregate work depends on tenants and poll frequency,
not only incoming writes. Declare workload-specific freshness and recovery targets
before judging an operating envelope; do not invent a tenant capacity from a green
functional suite.

**How results change expectations.** Correctness positives with meaningful red
controls support bounded recovery claims. A load sweep establishes where freshness
and recovery targets hold, and where queues grow. Contention may require shorter
transactions or admission limits; aggregate polling cost may require batching or a
different provider; lost intermediate transitions may require retained history.
Per-tenant ordering avoids a global ordering requirement, but shared pools, CPU,
retention and database I/O can still couple tenants. Architecture and provider
choices remain revisitable when experiments refute their assumptions.

## Sources

- [decisions.md](../../../releases/cgm-remote-monitor-16.0.0/decisions.md), D-EVENT rows (2026-10-31) and Q9 release-2 row
- [write-intent guide](../platform/guides/write-intent.md) "What the step does not do"; [wc-step design note](../platform/wc-step-design-note-2026-10-27.md) Q-B, Q-C, Q-F and the D-EVENT bench reference
- [execution plan](multitenancy-decisions.md) D4, D6, D15, D22, §7b and Phase 4 T4.1; [storage seam interface](nightscout-storage-seam-interface-2026-09-14.md) §9 and §11
- [clock proof plan](postgres-tenant-clock-proof.md); [lower-port proof](../../../reports/tenancy/tenant-commit-clock-lower-proof-2026-11-06.md); [HTTP fixed recovery](../../../reports/tenancy/tenant-clock-http-fixed-recovery-2026-11-06.md); [backend-abort diagnostic](../../../reports/tenancy/tenant-clock-http-backend-abort-diagnostic-2026-11-06.md)
- [integration record](../remedial/rc-16.0.0-integration-record.md) R48, R49, R50, R51, R55
- [seams plan](architecture-seams-execution-plan-2026-11-05.md) "Shared frame join and multitenant recovery", "Shared-frame inventory", "Reproduced frame acquisition and concurrent reads"
- [roadmap](multitenant-delivery-roadmap.md) §4 and the MT-RUNTIME-PLAN packet; [batching plan](multitenant-integration-batching-plan-2026-11-06.md) B2 and B7
- CRM `35903069`: `lib/storage/write-intent.js`, `lib/storage/postgres-intent-common.js`, `lib/storage/postgres-connection.js`, `lib/storage/postgres-entries-intent.js:56`, `lib/storage/postgres-collection-intent.js:114`, `lib/storage/PORT-CONTRACT.md`, `lib/notifications.js`, `lib/server/bootevent.js`, `lib/server/websocket.js`, `lib/server/serve/roles.js`
