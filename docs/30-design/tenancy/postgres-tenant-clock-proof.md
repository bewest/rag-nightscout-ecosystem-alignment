# Transactional PostgreSQL tenant clock: proof plan

*Current-use guide, 2026-11-06: R60 accepts the joined clock with bounded correctness evidence. [R65 descriptive HTTP workload](../remedial/rc-16.0.0-integration-record.md#r65---bounded-tenant-clock-http-descriptive-workload-2026-11-06) adds four small fresh cohorts; no performance budget or acceptance follows. Earlier corpus benchmark-pending captures remain unchanged. This page retains the original proof plan and invariants. Use the [current dashboard](multitenant-delivery-dashboard.md) and [R60 disposition](../../archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#accepted-coherent-ci-client-batch-and-m0-foundations-2026-11-06) for implementation acceptance.*

*Contributor-facing design/proof plan, 2026-11-06. The maintainer selects this
proof direction; implementation and performance acceptance remain UNMEASURED.
This is an additive lane proposal for central reconciliation, not a change to
queue state, release admission or the verification schedule.*

## Adopted direction

Prove a transactional PostgreSQL tenant clock first, preserving existing numeric
history cursors and single/Mongo behavior. Measure contention and fresh-ingestion
latency once the coordinator assigns a verification slot. Preserve the adopted
separate-role single-machine reference deployment and later multi-machine proof.

The motivating parent reproduction is the [REST replica history record](../../../reports/tenancy/rest-replica-history-characterization-2026-11-05.md).
Source for that reproduction is CRM `2a6eaf738382ef62b8b3bfd0c76dbd005abb8480`;
the later corrected-control/cleanup candidate is
`714f6c8b229fbea171db4e75cbf8179edd7d2d57`. No production clock change is contained
in either head. Preserve the reproduction independently of any remedy.

## Proposed invariant

Uniqueness alone is insufficient. For the same tenant, a reader must not observe
a later committed history watermark and then have an earlier watermark become
visible behind that cursor. Allocation, record mutation and ownership of the
ordering fence must therefore be coordinated through the actual commit boundary.
Transaction rollback must not leave an acknowledged write or prematurely release
an ordering guarantee. Existing HTTP history shape and server-owned date fields
remain compatible; do not silently reinterpret milliseconds as sequence IDs.

A candidate design uses a durable tenant clock row locked/advanced in the same
transaction as the relevant data write, retaining the lock until commit or
rollback. Different tenants should use independent clock rows. Exact schema,
privileges, initialization, timeout and batch behavior are engineering proposals
to test, not accepted implementation choices. Do not substitute a separate
sequence call, process mutex, leased timestamp range or wall-clock timestamp for
the commit-order proof.

## Scope to characterize before implementation

- Locate every relevant stamping call and its actual write transaction, including
  API3, legacy REST and independently admitted in-process writers. Unadmitted
  socket/connector paths remain explicit; no full-surface claim from one route.
- Preserve the default single/Mongo allocator and behavior. An adapter-specific
  capability must not make shared synchronous stamp helpers silently perform
  detached asynchronous allocation or fall back to a process clock on failure.
- Initialize above existing persisted numeric watermarks, including imported or
  future-dated values, without rewinding issued cursors. Restore/migration and
  concurrent startup must not allocate overlapping ranges.
- Keep tenant RLS, app-role grants, transaction ownership and nested/savepoint
  behavior explicit. Use an append-only candidate migration; no boot-time DDL.
- Define no-op, resend, multi-item write, partial batch failure, update, soft
  delete and hard-delete behavior against existing supported contracts.

## Required positive and semantic controls

| Proof | Expected positive | Break-it control / required symptom |
|---|---|---|
| Two actual API processes, equal allocator time | Later committed write appears after the earlier exclusive history cursor | Remove shared coordination; reproduce equal stamps and missed later row |
| Stalled first writer and competing second writer | No later visible cursor overtakes an earlier still-committable write | Release fence before commit; demonstrate a later cursor followed by a late lower-stamped commit |
| Rollback and crash before commit | No acknowledged/visible partial write; subsequent writer progresses correctly | Separate allocation/fence lifetime from transaction and detect broken visibility/recovery invariant |
| Same-tenant concurrent batch/write sources | Supported rows retain compatible dates and history visibility | Bypass coordination in one admitted write path; actual HTTP/persisted-state assertion must fail |
| Other tenant under contention | Its allowed writes remain isolated and progress within measured limits | Cross-bind clock state or use a global fence; detect isolation failure or serialized cross-tenant schedule |
| Restart, stored high watermark and migration | No rewind; current persisted state restored under safe schema | Omit initialization/readiness or corrupt ledger; detect lost history or unsafe listener bind |
| Compatibility | Existing single/Mongo results and cursor/date shapes remain unchanged | Deliberately route single through the new PG capability; existing behavior checks must detect it |

Controls must fail semantically. Setup errors, zero tests, timeout without a
confirmed scheduling barrier and a failed unrelated route are not evidence.
Restore the original source and rerun positives on the immutable candidate head.
A standalone ordering sequence cannot be accepted without data-commit proof.

## Performance and operational measurements

Record reproducible synthetic workloads and actual environment versions. Compare
a single writer, same-tenant competing writers, independent tenants, batches and
fresh ingestion during bounded import/rebuild contention. Measure end-to-end
ingestion latency distributions, completed throughput, clock-lock wait, database
load, errors/retries and any timestamp lead over wall time. Separate cold/restart
from steady-state measurements. No numeric threshold is selected before evidence.

Keep lock-held work short; characterize rather than assume how much work runs
between acquiring the fence and COMMIT. Never hold the ordering fence across
external provider calls without explicit justification and measurement. Preserve
explicit retryable refusal, bounded per-tenant work and fresh-ingestion priority.

## Ownership and next steps

Central coordinator owns source reservations, serial verification slots and
queue/release/dashboard/map reconciliation. This lane retains the reproduced
replica fixture and standalone evidence. A separate read-only investigation of
clock/fencing options must be reconciled before product implementation; do not
have two agents edit shared storage/date helpers independently.

Capacity has recovered following separately authorized cleanup, but other lanes
retain the current verification slots. Do not self-start DB/full/browser runs on
seeing free disk. Static planning may proceed. Once source ownership and slot are
assigned: implement a narrow candidate, reproduce concurrency/rollback controls,
measure performance, run affected/full/browser checks and final prcheck, then
return additive source/evidence commits. No agent push.
