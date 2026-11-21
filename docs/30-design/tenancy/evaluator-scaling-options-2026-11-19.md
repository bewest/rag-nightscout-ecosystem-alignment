# Evaluator scaling options

*Contributor-facing collection of proposals, 2026-11-19. Status: **proposed**, not a decision.
Options can be added here as they come up. Measurements will be added to the results section as
they arrive. It relates to
[evaluator-scale-direction](multitenancy-decisions.md#evaluator-scale-direction) (profile first,
then K processes), [private-stream-router](multitenancy-decisions.md#private-stream-router)
(deferred routing for K>1) and
[ack-path-tenant-independent](multitenancy-decisions.md#ack-path-tenant-independent).*

## Question

At 1,000 tenants the evaluator is the first role to bind. How should its ceiling be raised? The
options are cheaper work in the same process, more cores in the same process, more evaluator
processes, or separating the roles the evaluator combines today. Several options combine: A is
worth doing under any of the others.

## Evidence so far

- **Measured, 2026-11-19.** See the [execution log](execution-log.md#update--concurrent-k1-kubernetes-points-and-first-bend-at-1000-tenants-2026-11-19)
  for the setup and denominators.
  - On Kubernetes at 1,000 tenants, every point up to 86.81 req/s passed. At 90 req/s both runs
    failed the 120 s clinical deadline, while HTTP p95 stayed below 83 ms.
  - The evaluator's CPU stayed at 1.06–1.11 cores from 76 req/s to 240 req/s. A 6-core allocation
    did not raise it. That is consistent with one saturated Node.js main thread, but read-derived.
  - Neither PostgreSQL nor the node was saturated.
- **Read-derived** from core `6da24edbb7`. The evidence is the local evaluator map
  `artifacts/evaluator-map-20261119/EVALUATOR-MAP.md`.
  - **One thread.** Stream receipt and clinical evaluation run on one Node.js main thread. pgstream
    delivers one source transaction at a time and waits for the acknowledgement. Receipt latency
    therefore caps stream throughput, and evaluation CPU delays receipts.
  - **What the acknowledgement covers.** It waits for a durable receipt transaction of about 10–12
    statements (`lib/server/serve/clinical-stream-sql.js:20-122`), not for evaluation. Under
    backlog, receipts keep succeeding while pending work ages. That matches the measured bend.
  - **Most per-write CPU is in memory.** The receipt applies rows to the tenant's **in-memory**
    working set (`clinical-stream-state.js:93-125`). It appends to a per-tenant storage-event
    journal of up to 10,000 events or 8 MiB that realtime replays. It fills an in-memory replay
    cache that evaluation reads on its warm path (`postgres-durable-replay.js:111-122, 207-228`).
    The database receives only working-set metadata and the journal; the rows themselves are not
    stored there. A cache miss forces a snapshot rebuild from the domain tables
    (`postgres-durable-replay.js:230, 368`).
  - **Completions are serialised.** Completions for all tenants run on one owner connection
    (`postgres-connection.js:582-591, 675-677`).
  - **Core can already run K evaluators.** The sliced path exists:
    `NS_PGSTREAM_EVALUATOR_SLICE`, an owner key per slice, and `sha256-modulo-v1` filters. The
    patched pgstream's `slice_receivers` supports it, and so does the Compose binding. The cost is
    head-of-line coupling: the slot advances only when every slice has acknowledged, so one slow
    evaluator pauses intake for all of them.

## Options collected

| option | what changes | removes the slot coupling? | new moving parts | status |
|---|---|---|---|---|
| **A. In-process efficiency** | Cut per-write main-thread work found by the profile: append-only or bounded journal instead of a whole-journal rewrite per append; skip re-hashing unchanged output (already listed in [evaluator-scale-direction](multitenancy-decisions.md#evaluator-scale-direction)); one serialisation of the working set instead of 4–5; no full-history `dbstats()` per acquisition; one `validateTransaction` instead of two. | n/a (K=1) | none | Read-derived candidates; the profile ranks them |
| **B. Evaluation on worker threads** | Keep receipt, scheduling and completion on the main thread. Run acquisition (dataloader and plugin pass) on a `worker_threads` pool inside the same process, with tenants pinned to workers by hash. | n/a (one receiver) | thread hand-off and per-worker resident state; one Pod uses several cores | Idea; no routing or binding change |
| **C. Evaluator K>1, patched slicing** | Kubernetes binding renders K evaluator Pods and pgstream `slice_receivers` (core and Compose already support this). | **No.** One slow slice pauses all. | per-Pod slice config | Maintainer accepted for measurement 2026-11-19; binding lane in progress |
| **D. Intake split** | A singleton `stream-intake` receives and acknowledges; K evaluators read pending work for their slice from the database (detailed below). | **Yes.** Evaluators are off the replication path. | one role; durable wake-up; evaluator working-set rebuild | Proposed here |
| **E. Private stream router** | Stock pgstream → body-reading router (nginx njs or Node) → owning evaluator; standalone or colocated per Pod ([private-stream-router](multitenancy-decisions.md#private-stream-router)). | **No**, without a buffer: the producer still waits on each owner. | router; a commit marker for transaction completeness | Deferred decision, preferred shape |
| **F. Debezium plus broker** | Debezium (per-row events, optional transaction markers) into Kafka/Redpanda partitions or NATS JetStream partitioned subjects keyed by tenant; evaluators consume their partitions. A thin router (nginx with the tenant in a header) is an alternative to a broker but keeps the coupling. | **Yes**, with a broker. | JVM connector plus a stateful broker for every operator; transaction reassembly | Idea |
| **G. Per-evaluator publications** | PostgreSQL publications with row filters on a tenant bucket column, one logical consumer per evaluator ([private-stream-router](multitenancy-decisions.md#private-stream-router) item 7). | **Yes.** One slot per slice. | bucket column; a pgoutput consumer; K slots and WAL senders | Research candidate |
| **H. Full filter** | Every evaluator receives every row and drops what it does not own. | No | none | Comparison arm |
| **I. Batched completion** | Completions for several tenants in one statement (`UPDATE … FROM unnest(…)`) instead of one transaction per tenant on the serialised owner connection. Under backlog, PostgreSQL cost per write then falls as load rises. | n/a | none | Proposed 2026-11-20 |
| **J. Time-only cycles without a full pass** | Time-derived display fields (timeago and similar) are computed at read or render time. Server timers remain only for time-driven alarms, and they run the alarm predicate, not the full plugin pass. A cycle whose output is unchanged writes nothing. Today a tenant with a "slow" reason gets a full pass every 60 s (`evaluator-due.js:85-149`, read-derived), so this cost grows with tenant count, not write rate. | n/a | none | Proposed 2026-11-20 |
| **K. Writer-driven notification, no CDC** | The writing role marks the tenant pending in the write transaction. After commit it sends a hint to the owning evaluator and realtime (`slice.js` over ordinal DNS). A sweep over pending rows only, through a partial index, covers lost hints and restarts. The evaluator reads changed rows since its checkpoint into a resident working set. The write's own result may serve as the payload when it is contiguous with the resident state. It rests on [no direct writers](multitenancy-decisions.md); it reopens [event-driven-reset](multitenancy-decisions.md#event-driven-reset). | **Yes.** There is no slot. | pending marker (exists), hint client, sweep; retires pgstream, the patch, the slot, the receipt transaction and the journal in the checkpoint row (to be confirmed) | **Adopted 2026-11-21** ([writer-driven-transport-direction](multitenancy-decisions.md#writer-driven-transport-direction)); C/E/F/G retired |

**Open question for D, E and F.** "Inbox" is a good name for the durable pending state that
receipt and evaluation share. Whether that state stays in PostgreSQL (D) or moves into a broker (F)
is the main fork between them.

## Option D in detail: intake split

| role | workload | owns | scales by |
|---|---|---|---|
| **`stream-intake`** | One replica: a Deployment with `Recreate`, or a StatefulSet of 1, fenced by the existing owner advisory lock | Receives the pgstream transaction, validates it, appends the durable receipt (the inbox: input checkpoint, journal, `work_pending_at`) and acknowledges. Owns the storage-event journal that realtime replays. | Not at first. One ordered stream, one cursor. |
| **`evaluator`** | StatefulSet, ordinal = slice ([statefulset-ordinal-scaling](multitenancy-decisions.md#statefulset-ordinal-scaling)) | Picks pending work for its slice from the durable inbox. Rebuilds or extends each tenant's working set, evaluates and completes. Sends realtime hints and notifications. | K slices, `sha256-modulo-v1` |

**Names.** "Inbox" is a good name for the durable pending state the two roles share, but not for a
process. `stream-intake` follows the existing `stream-intake` port and intake Service names. The
`evaluator` role keeps its name, so the K=1 deployment and the decisions that reference it do not
change. A single-tenant or small deployment runs both roles in one process through the one
entrypoint (`serve <roles>`, D21), which is what happens today.

**Is intake stateless?** Its correctness state lives in PostgreSQL, so the process can be
replaced. It is not cache-free, though: computing the working-set metadata needs the tenant's rows,
which the receipt currently holds in memory. Its rebuild path would be the same snapshot path the
evaluator uses today.

## What would have to change

1. **Hand-off becomes durable.** Evaluators are woken by a notification (`LISTEN/NOTIFY` on
   pending work, or the existing realtime-hint style RPC) or by a short poll of `work_pending_at`
   for their slice. The scheduler already reads `store.work()` pages and `nextDue()` from SQL.
2. **The warm path cannot rely on the receiver's cache.** Choose one:
   - (a) intake persists the windowed rows, not just metadata, so evaluators read them in one
     query;
   - (b) evaluators read only the changed rows since their last checkpoint, which the journal
     already carries, and keep their own resident working set;
   - (c) accept a snapshot rebuild per acquisition. This is likely too expensive.

   Option (b) keeps evaluators stateful per slice, which a StatefulSet gives.
3. **Per-slice completion connections.** The single owner connection becomes one per slice, which
   core's per-slice owner key already implies.
4. **Journal work stays with intake and should get cheaper.** Today each append re-reads and
   re-serialises the whole journal of up to 8 MiB per tenant (`storage-event-journal.js:43-74`). An
   append-only table or a bounded tail would cut intake CPU whichever transport is chosen.

## How D relates to transport and routing

- **The slot-coupling problem goes away.** Intake is the only receiver, so no slow slice holds the
  slot. Evaluators scale behind the database, which needs no router, no broker and no patched
  slicing for evaluator K>1.
- **Intake capacity becomes the transport question.**
  [private-stream-router](multitenancy-decisions.md#private-stream-router) (stock pgstream through
  a body-reading router), Debezium, or patched slicing would then decide only whether one intake
  process can keep up and how to run more than one.
- **nginx `auth_request` cannot route on the body.** The subrequest receives no body, as the
  decision already notes.
- **Debezium is an option for intake, not for evaluators.** It would require the receiver to
  reassemble transactions from per-row events. Decoupling more than one intake from each other
  still needs a durable per-partition buffer, such as Kafka/Redpanda partitions or NATS JetStream
  partitioned subjects. Any of these adds a stateful service for every operator.

## Trade-offs of D

- **Costs.**
  - One more role to deploy and monitor.
  - Evaluation latency gains a wake-up hop.
  - Intake becomes a singleton with a ceiling of its own.
  - Working-set rebuild cost moves to the evaluators.
- **Gains.**
  - Receipt latency no longer competes with plugin CPU.
  - Adding evaluators adds clinical throughput without touching replication.
  - A slow or restarting evaluator delays only its own tenants.
- **Single-tenant behaviour is unchanged.** Both roles run in one process
  ([multitenant = same behaviour as single tenant](multitenancy-decisions.md)).

## Measurements that decide

1. **Thread split.** Per-thread CPU of the evaluator at 83 req/s, to confirm the main thread is
   saturated.
2. **Receipt share.** What fraction of main-thread time goes to receipt (parse, validate, apply,
   journal, serialise) compared with acquisition and completion. Measured with one CPU profile
   plus the receiver trace (`NS_PGSTREAM_RECEIVER_TRACE=1`). If receipt is a small share, D
   buys little, and A, B or C is the cheaper step. If plugin evaluation dominates, B is the cheapest
   way to use more cores.
3. **Stall reality.** At 90 req/s, do pgstream logs show 2 s client timeouts, retries or replays
   from the slot? Does evaluator K=2 under patched slicing raise the bend, and by how much?
4. **Steady journal size per tenant** in the 1,000-tenant fixture, which sets intake cost.

## Results

**2026-11-19, Kubernetes, 1,000 tenants, core `6da24edbb7`** (detail in the
[execution log](execution-log.md#update--k1-kubernetes-repeats-cpu-model-dependence-and-the-first-evaluator-profile-2026-11-19)):

1. **Thread split — measured.** The evaluator's main thread ran at 96–97% on Xeon 8168 nodes and
   85–88% on Xeon 8358 nodes at 83–90 req/s; GC threads about 2% each. The ceiling is single-core
   speed of one thread: on 8358 nodes 90 req/s stays healthy and 120 req/s is constrained.
2. **Receipt share — open.** A 120 s CPU profile at 83.33 req/s (main thread 93.4% busy) is flat.
   Socket writes take 15–22% of busy time, then `pg` row handling, the completion hash
   `canonical` and receiver parsing. The reducer left about 69% of samples unattributed. Reading
   suggests per-SQL-statement cost is material. That favours **A** (fewer statements per receipt
   and completion, skip unchanged re-hash) before any topology change, and it does not yet show
   whether **D** pays.
3. **Stall reality — partly measured.** No pgstream timeouts, retries, replays or restarts at
   83–90 req/s; receipt-to-response p99 41 ms. The coupling **C** would add is not yet exercised.
   Evaluator K=2 renders offline but the harness cannot yet run a multi-Pod evaluator.
4. **Journal size — not measured.**

**Profile attribution and SQL per write (2026-11-19, from retained evidence; local evidence
identifier `evaluator-profile-20261119`).**

- **Profile split — measured.** An inclusive call-stack reducer assigns every busy sample to a
  phase, and an empty-rules negative control removes every named phase. At 83.33 req/s:

  | phase | % of busy |
  |---|---:|
  | receive | 10.7 |
  | acquisition | 20.9 |
  | completion | 5.1 |
  | consumers | 4.2 |
  | settings | 4.5 |
  | wrapper and fence SQL, phase hidden by async boundaries | 21.0 |
  | inbound row parsing, no caller | 12.2 |

  PostgreSQL client frames take **35–42% of busy time**, about 4 ms per write at both rates. The
  plugin pass is under 3% and the dataloader 2.3–2.5% on this fixture, whose tenants hold very
  little history.
- **Statements per write — measured, Compose.** The evaluator's four database roles issue 164–173
  statements per accepted write from 1,000 to 5,000 tenants. That count does not grow with tenant
  count; it falls only when cycles merge under backlog. About 20 statements do domain work.
  - The rest are transaction control (41.5) and fences (30.2) on the evaluator role, observe
    transactions (14.7), trusted scans (8.9) and outbox/suppression bookkeeping (about 55).
  - A one-tenant receipt is 13 statements.
  - Kubernetes cases kept no statement statistics.
- **What this means for the options (read-derived arithmetic on measured shares).**
  - **A first.** Fewer `BEGIN`/`COMMIT` wrappers around single reads, folded fences (restore
    fencing keeps its semantics and needs a control that can fail), deduplicated trusted scans,
    merged outbox transactions, settings cached per revision, no re-hash of unchanged output, and
    keep-alive for realtime hints. Together these are estimated at about 25% of busy, roughly 1.3×
    headroom.
  - **B** can move at most 25–28% of busy time (acquisition JS, settings, the hash). It needs a
    profile on a fixture with realistic history before it is judged.
  - **D** removes only receipt work, about 11% (19% at most), from each evaluator. It pays only by
    enabling K evaluators without slot coupling. A singleton intake would reach roughly 500–800
    writes/s on today's code, extrapolated linearly.

**K=2 against K=1 (2026-11-19, Kubernetes, Xeon 8168, option C as patched; detail in the
[execution log](execution-log.md#update--evaluator-k2-against-k1-at-1000-tenants-on-kubernetes-2026-11-19)).**

- **Stall reality — measured.** At 90 req/s K=2 brings durable p95 from 51.84 s to 12.65 s (one
  pair). At 120 req/s it reduces late outputs from 103 to 25 and 32 but still fails the clinical
  deadline. No pgstream timeouts, retries or restarts appeared; the coupling shows instead as the
  walsender waiting on pgstream in 15 of 16 samples with slot lag at 113–123 MB, while each
  evaluator main thread had 24–31% to spare.
- **What this means for the options (read-derived).** C buys roughly one notch of rate on slow
  cores and then hands the bottleneck to the single stop-and-wait delivery path. Further K will not
  help until delivery is parallel or pipelined: per-slice delivery (D, E, F or G), or more pgstream
  workers with ordering kept per tenant. A remains worthwhile because it lowers the per-write
  PostgreSQL cost that K=2 raised (2.1 → 3.0 cores at 90 req/s).

**2026-11-20, direction for the next round (read-derived, from the measurements above).**
- **What binds after K=2 is delivery, not PostgreSQL.** At 120 req/s PostgreSQL used 3.2–3.3 of 16
  cores. The statement count does not create a serial queue. It lengthens each turn through the
  three serial points: the main thread, stop-and-wait delivery and the owner connection.
- **A, I and J pay off under any topology** and come first. A is in progress against a statement
  budget of ≤ 40 per accepted write, with a smoke that reports statements per write by phase.
- **K decides whether the transport question exists at all.** It depends on two things:
  - whether every writer of stream-relevant tables can notify after commit;
  - what realtime needs instead of the storage-event journal.

  Both are being read. The cheapest deciding spike compares the evaluator's PostgreSQL statements
  per write under pull-on-hint with today's receipt plus acquisition.

**Next measurements:** per-batch pgstream delivery latency at 120 req/s with K=2; a progress
instrument that reads K>1 on Kubernetes; the steady journal size per tenant; a profile on a
fixture with realistic history.
