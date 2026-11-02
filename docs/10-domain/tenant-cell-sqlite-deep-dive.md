# Tenant cell + SQLite: local feasibility experiments

**2026-11-02. Experimental, synthetic data only.** Worktree
`externals/work/celld-sqlite-20261102`, branch `lab/celld-sqlite-20261102`,
based on alignment commit `28671cb4a`. No production backend registry, release
gate, hosted delivery roadmap or external NS checkout was changed.

## Outcome

**A tenant cell can own its SQLite records without a second database.** Real
celld v0.6.3 passed twelve local experiment checks and a discriminating broken
routing control. This supports continuing a SQLite backend feasibility track;
it does not establish a supported third backend or production cost advantage.

Each fixture tenant uses the same class and schema but a different cell name.
A shared ingress validates the fixture principal for the tenant before resolving
the cell. Inside the cell, document changes and operation receipts share a
SQLite transaction. There is no PostgreSQL authority, MongoDB mirror or
PG-to-actor delivery gap in this arm.

## Reproducible evidence

| Item | Anchor |
|------|--------|
| Runner | `tools/lab/tenant-cell-sqlite/run.mjs:1-331` |
| Worker and SQL | `tools/lab/tenant-cell-sqlite/worker.mjs:1-166` |
| Configuration and instructions | `tools/lab/tenant-cell-sqlite/wrangler.json:1-10`, [lab README](../../tools/lab/tenant-cell-sqlite/README.md) |
| Measured output | [local.json](../../tools/lab/tenant-cell-sqlite/results/local.json), timestamp `2026-11-02T20:33:09.545Z` |
| Runtime | celld 0.6.3, Node v22.23.4, Linux x64; executable/worker/runner SHA-256 in output |
| Binary provenance | `denoland/celld` v0.6.3 release asset; `gh attestation verify` succeeded |
| NS reference | `official/dev` at `61eb37335954ae42c91345a0823bd67331025165`, read from the local official repository; not executed by this lab |

The local developer object store persists on the same host's filesystem.
No cloud bucket, ensemble, second node, remote network or disk-loss recovery
was involved. No paid resources were provisioned and no real health records or
provider credentials were used.

## What passed

| Experiment | Observation |
|------------|-------------|
| Separate record identities | Two tenants store the same `_id` and `identifier` with different contents; reads and cell IDs remain distinct. |
| Trusted routing boundary | Wrong-tenant, absent and unknown-tenant fixture principals refuse GET, PUT and DELETE; stored positive fixtures remain intact. This is not a production authentication integration. |
| Retry receipts | Sixteen simultaneous copies produce one non-replay response. A new operation can resend the same record without duplication; another tenant can reuse the receipt ID independently. Changed content under the original ID conflicts. |
| Transaction rollback | A second-row unique-identifier conflict leaves neither the preceding new row nor a receipt; a corrected operation can retry. |
| JSON predicates | Numeric comparisons exclude numeric-looking strings. The null predicate matches null and missing, while stored JSON preserves the distinction. Only these bounded predicates were implemented, not the full NS filter language. |
| Paging and index | Date/id ordering, offset and limit match the fixture; invalid limits refuse. EXPLAIN uses `entries_date`. |
| Tombstones | Deleted rows disappear from normal reads, remain visible to the explicit tombstone read, refuse an ordinary resurrecting write and do not delete the other tenant's record. |
| Concurrent distinct writes | Twenty-four parallel operations all remain stored. |
| Batched ingest | 32 tenants each ingest 288 readings, then independently read them back: 9,216 CGM rows, in addition to the correctness fixtures. One batch per tenant, **not a day-long paced workload**. |
| Warm microbenchmark | 120 sequential write/read pairs on loopback; timings below. |
| SIGTERM restart | All 32 tenants' captured documents, including tombstones, match after restart; cell identity and original receipt replay survive. |
| SIGKILL restart | The same assertions pass after killing the owned dev process tree, with local state retained. |
| Broken shared-cell routing | The isolation check fails specifically because tenant A reads tenant B's `200` rather than its own `100`. This proves that the check can discriminate the deliberate fault. |

### Measurements, not capacity estimates

| Metric | Result |
|--------|--------|
| Warm write p50 / p95 | 12.53 / 24.67 ms |
| Warm read p50 / p95 | 2.02 / 3.34 ms |
| 32-tenant batched ingest and readback | 1.27 seconds; not steady-state throughput |
| Dev process-tree RSS before tenant creation | 69.11 MiB |
| Dev process-tree RSS after workload | 132.80 MiB |
| Local `.celld` files after workload | 10,922,626 bytes, including local-store/replication overhead |
| Database size for each initial one-row tenant | 73,728 bytes, as reported by `sql.databaseSize` |
| Final database size for tenant 0 | 204,800 bytes; 439 rows and 151 receipts |

RSS sums the developer supervisor and server and can double-count shared pages.
These observations include the small lab implementation, runtime, records and
receipts; they are not per-tenant memory reservations. No eviction/hibernation,
plugin working set, noisy-neighbor contention or sustained-load capacity was
measured. Latency uses the local object store, not remote bucket durability.
Do not extrapolate cells per 8 GB node or dollars per tenant from this run.

## Runtime discovery

The first diagnostic attempted `SELECT sqlite_version()` and received
`not authorized to use function: sqlite_version`. Document storage had worked;
the metadata request failed explicitly. The final diagnostic uses the cell SQL
API's `databaseSize` rather than assuming an unrestricted sqlite3 connection.
The embedded SQLite engine version was **not measured**.

The runner also needed more than ten seconds for developer-mode SIGTERM
shutdown. Its bound is now 45 seconds with explicit cleanup. Reported restart
check times include shutdown, startup and all readback assertions, and must not
be presented as failover latency.

## Three backend implications

The desired architecture can distinguish:

| Candidate | Tenant record authority | Status here |
|-----------|-------------------------|-------------|
| MongoDB | Existing NS MongoDB adapter | Unchanged; no comparative run |
| Shared PostgreSQL | Tenant-bound SQL/RLS adapter | Separate workstream; no comparative run |
| Tenant cell + SQLite | One cell database per tenant | Local lab only; no NS adapter registration |

Current inspected NS `official/dev` registers MongoDB only:
`externals/cgm-remote-monitor-official/lib/server/storage-backends.js:21-27`.
The harness lists PostgreSQL as unavailable:
`externals/cgm-remote-monitor-official/tests/support/backends.js:58-65`.
The filter contract explicitly pins MongoDB type/null/regex semantics:
`externals/cgm-remote-monitor-official/lib/storage/filter.js:35-45`;
the actual tests are at
`externals/cgm-remote-monitor-official/tests/api3.storage.filter-semantics.test.js:65-119`.
These references are **at `61eb3733`**, not a claim about the official worktree's
currently checked-out branch. A third entry must not be marked available merely
because this independent lab passed.

The next integration gate is an actual SQLite adapter exercising applicable
NS storage contract cases. Preserve legacy v1/v3/socket identity and mutation
behavior, BSON/JSON boundaries, projection/filter/paging semantics, validated
treatment updates, partial batches and committed-event behavior. The lab's
atomic batches and required identifier are not substitutes for those contracts.
Choose whether the existing Node server reaches celld through a narrow adapter
or the runtime itself is ported; neither integration is demonstrated here.

## Open experimental gates

These are experiment checks, not new release dependencies or duplicate protocol
GAP/REQ identifiers:

1. **Actual NS contract:** run the real backend harness on the SQLite adapter,
   with positive and deliberate-break controls. Keep unavailable backend tests
   visible rather than passing under another backend's name.
2. **Fleet durability:** use a dedicated qualified bucket and at least two
   supervised nodes; measure acknowledgments, owner loss, fencing, retained-tail
   recovery and reconnect. Repeat with reserve capacity and concurrent traffic.
   Local SIGKILL with the same disk does not prove RPO=0 or host-loss survival.
3. **Runtime behavior:** prove settings/plugin isolation, durable evaluator
   scheduling, notification acknowledgment and retry delivery, and actual
   Socket.IO compatibility. A storage receipt does not make an external push
   effect exactly once.
4. **Lifecycle:** test schema upgrades across many tenant databases, immutable
   cell addressing across deployments, full export/deletion, tenant restore,
   backup retention, tombstone/receipt GC and rollback.
5. **Economics:** compare the same paced workload and historical data on the
   three actual adapters; measure resident/idle memory, CPU, bucket requests,
   replication bytes, storage growth, recovery headroom and operational effort.
   Count retained receipt fingerprints as storage amplification. At five-minute
   CGM cadence there are 8,640 readings per 30 days per tenant, before other NS
   records; this batch test did not simulate that schedule.

The next fleet step needs dedicated object-store provisioning/credentials; none
were discovered or reused from this shared environment. The local experiment
is complete, while that fleet acceptance and the three-way comparison remain
unperformed.

## Validation

The final runner exits zero with all twelve positive checks and the precise
shared-cell negative control passing. Both `.mjs` files pass `node --check`,
and `git diff --check` passes. All experiment servers are stopped.

`make verify` ran with existing external checkouts linked into this worktree
for reference reads. It is **not globally green**: 102 broken corpus references,
63 requirements without coverage and 175 uncovered requirements in the assertion
report remain. Terminology reports zero issues and GAP definitions have zero
duplicates. The Make target ignores subcheck failures, so its zero exit status
does not establish success. None of the listed broken source references is in
the new deep dive.

`make traceability` completed, but its requirements matrix extracts zero
requirements from the index despite the coverage scanner finding 323 in the
modular corpus. The regenerated matrix was not retained over the older tracked
matrix. These corpus/tool limitations are outside this experiment.

Primary runtime documentation, retrieved November 2:
[cells](https://celld.dev/docs/services/durable-objects/),
[local development](https://celld.dev/docs/#develop-an-application-locally),
[guarantees](https://celld.dev/docs/guarantees/),
[compatibility](https://celld.dev/docs/cloudflare-compat/),
[limitations](https://celld.dev/docs/limitations/).
Web docs are unpinned and the limitations page described v0.6.2 beta;
**the executed release was v0.6.3**.
