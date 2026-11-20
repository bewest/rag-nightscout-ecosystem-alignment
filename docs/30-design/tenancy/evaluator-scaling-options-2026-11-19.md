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

*Pending. Session 2 of the concurrent Kubernetes campaign (2026-11-19, until midnight) runs the
thread split, one CPU profile with receiver trace at 83.33 req/s, pgstream log capture at
90 req/s, and evaluator K=2 at 90 req/s if the binding change is ready.*
