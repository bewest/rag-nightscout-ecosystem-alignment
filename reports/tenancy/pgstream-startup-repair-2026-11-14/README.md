# Pgstream startup repair: 1,000-tenant discovery and source acceptance

*Captured 2026-11-14 UTC. Contributor-facing record. Measurements are reproduced;
source mechanisms are read-derived except where a failing control is recorded.*

The repaired startup candidate passes the unchanged 1,000-tenant discovery's
readiness, idle and load checks. Every accepted ordinary write matches storage,
and both sampled tenants deliver their expected completed-output frames. This
closes the reproduced startup/progress failure for this discovery envelope.
Capacity acceptance remains **NOT_GRANTED**. The original run's functional
acceptance remains **UNACCEPTED**; this record does not relabel that capture.
The complete actual-role recovery and effect-fencing criteria remain open in the
[communication plan](../../../docs/30-design/tenancy/evaluator-realtime-communication.md#actual-role-integration-objective-and-completion-criteria).

## Source and measurement boundaries

| Boundary | Exact attribution |
|---|---|
| Measured application | `5fe05066c174b675dcd601374af512bc7573a52b` |
| Deployment | `883c516bc2b60a66ef5ae8e211cff4955449fea6` |
| Measured application image | `sha256:83d6bcdc608a3e496990f9ad5f649647da0833528e25847da997748953650955` |
| Final source acceptance | `b537141979dc79c528c2497e5bc59d69423be84c` |
| Final qualified image | `sha256:2aceffd91b1bb1f32ddce07e1f66c66647e7cec440d7c96bbcef35e4d3bd2baf` |
| Incorporated `official/dev` | `4a482627bfdafb1fef8dcbe0ac6c484811cae563` |

Later source acceptance repairs retain their own attribution. The discovery is
never represented as a performance measurement of the later source. The
[closed REST A/B comparison](../rest-api-performance-2026-11-13/final-joined-local-ab.md)
uses its earlier candidate and was not repeated.

## What changed

Normal operational verification now drains owned clinical work before invalidating
its admitted backend. Tickets remain queued, and a changed admission epoch causes
a current full acquisition rather than discarding a newer model. Cold TIME work
acquires retained state before evaluation; warm TIME retains the no-input-reload
path. Background API initialization runs in its boot scope rather than inheriting
a request's expiring operation lifetime. Sequential borrowed runtime and delivery
requests continue only in their same still-active parent; foreign, expired and
independent parents remain refused. These mechanisms were reproduced with
original-source RED and repaired GREEN controls.

The coherent delivery retains the earlier checkpoint, realtime and REST transfer
reductions. Observed progress commits before ACK; completed output, versions and
due state remain atomic. No clinical timer, authorization, restore or old-process
effect fence was replaced with a counter or a longer deadline.

## Unchanged discovery

The envelope retains one API replica, diagnostics off, 1,000 tenants, warmup
10 seconds, idle 30 seconds and load 310 seconds; acceleration and hot factor are
one, with two sockets per tenant and a 300,000 ms probe cadence. No tuning or
restart campaign follows this capture.

| Measurement | Result and limit |
|---|---|
| Fresh readiness, idle, load | **PASS**; driver and probe exit zero; no hard failures. |
| Ordinary writes | 3,102 accepted and stored: 1,034 each entries, device status and treatments. Zero uncertainty and zero per-tenant mismatches across 1,000 tenants. |
| HTTP | 12,371 requests include 1,000 setup exchanges and 11,371 ordinary iterations. Failure rate zero; absent refusal/drop series remain UNMEASURED. Global p95 86.2616415 ms and p99 110.9733165 ms include setup and are not isolated read latency. |
| Sockets | 2,000 primed and connected at end; zero dark sockets or observed disconnects. |
| Sampled output | Two separate probe writes deliver four of four frames. Write-to-frame n=4, maximum/p95 97 ms. Completed-output/BG-now agreement covers two sampled tenants, not all-roster clinical equivalence. |
| Sampled evaluation observation | n=2, maximum 1,119 ms; polling confirmation latency, not executor duration. |
| Evaluator progress | Load completed-work delta 2,274, minimum two per tenant. Zero failed-completion delta and zero model-generation changes. |
| Clinical time | All 1,000 tenants FUTURE_DUE / TIME_NOT_EXERCISED; no idle time witness. No clinical-time-only workload claim. |
| Storage oracle | GREEN; meaningful broken control RED, restored GREEN. Separate probe accounting closes without pending writes. |
| Later read-only observation | All 1,000 clock, observed, completed and input-checkpoint values match; zero pending. All nine role restart counts zero; no API warm-failure or cold-bound alerts. |

Available SQL keys increase from 18 to 162 across the load bookends, with no
missing keys or decreasing counters. Captured keys include role, database,
query identifier and SQL text. User identity, top-level classification and
reset/deallocation history were not retained; complete reset/eviction proof is
**UNMEASURED**. SQL execution time is not PostgreSQL CPU.

The cgroup bookends span 346.94655752182007 seconds, including setup and tail:

| Role | CPU seconds | Average cores | Anonymous MiB, start → end |
|---|---:|---:|---:|
| Evaluator | 59.910132 | 0.172678272 | 348.960938 → 477.207031 |
| Realtime | 59.265293 | 0.170819660 | 319.167969 → 310.265625 |
| API | 161.347347 | 0.465049569 | 973.628906 → 1126.878906 |
| PostgreSQL | 443.245405 | 1.277561040 | 190.949219 → 182.292969 |

These are unmatched shared-host observations. No memory saving or performance
ceiling is claimed. Host I/O and pressure measurements use a separate window and
are not attributed to PostgreSQL.

## Source acceptance and controls

The frozen source passed all eight unfiltered tiers and the enabled corpus:

| Tier | Passing | Pending | Failing |
|---|---:|---:|---:|
| Unit | 4,450 | 1 | 0 |
| DOM | 205 | 0 | 0 |
| Dependency | 368 | 2 | 0 |
| Core | 319 | 0 | 0 |
| Harness | 100 | 0 | 0 |
| Integration | 3,643 | 896 | 0 |
| Stress | 18 | 0 | 0 |
| Browser | 686 | 0 | 0 |
| Enabled native corpus | 899 | 1 | 0 |

Commands are `node scripts/test-tiers.js check`, then
`node scripts/test-tiers.js run <tier>` for each named tier, followed by
`node scripts/test-multitenant.js --record <private-run-record>` with no selection
or opt-in exclusions. The corpus's pending case is the request-latency/throughput
benchmark, not a credited functional pass. Corpus runner exit zero, remaining
owned fixtures empty and cleanup verified. Source stays clean. Its final result
record SHA-256 is `a3424ed87ced7f4aabb2d7ea75f6c31bab1b196697e55bcedcf8ace93bfd9cda`.
All raw outputs, exact environment keys, image pins and deadlines remain retained.

The first enabled corpus on `119bf4cbbb0818613643b321e5e8c829b7e8e456`
executed 873 passing checks, one pending benchmark and 26 failures. Original
outputs remain unchanged. Repairs address the reproduced sequential-parent race
and stale config, concurrent provisioning, pending migration, close-then-drain,
cohort-roster and outage injection expectations. The new provisioning check
measures exact pre-key BUSY refusal, no duplicate key work and idempotent retries:
34 GREEN, fence ablation 33 GREEN/one RED, restored 34 GREEN. The RED symptom is
`TENANT_PROVISION_FAILED` instead of required `TENANT_PROVISION_BUSY`; it does
not establish that duplicate key work occurred. REST focused native checks pass
69 cases, including existing response-lifetime, orphan and uncertain-reply controls.
These focused counts overlap acceptance and are not added to it.

Changed runtime/delivery modules pass ESLint with zero errors. The earlier full
lint run had two independently reproduced baseline errors and is not relabelled
as green. Final source acceptance establishes the listed suites, not complete
actual-role fault coverage. The next integration boundary is a shared two-tenant
actual-role campaign for current-image process loss, bootstrap coverage, hung
transport/backlog, schema routing and external effect/restore fencing. Lost-slot
terminal refusal is distinct from complete populated operator rebootstrap.

The canonical final source image passes independent network-disabled inspection:
all 674 tracked library and package files, including JSON schemas, match the
frozen Git source. Labels, source binding and Node v24.22.1 agree. Root image
qualification SHA-256 is `037605a06c3a2daef10bbdeb20a3c8afe438f77bb635ca55c21729c4a6278985`;
builder source manifest SHA-256 is `ed7ab5c94db069e9f1e344fe1a528b355c70d16962dbce9b416599887b6d9c52`.
This is filesystem qualification, not a role-startup or fault-campaign result.
Final prcheck exits zero, includes current `official/dev` and leaves the frozen
head unchanged. Nothing is pushed. The next actual-role work retains a separate
source, image, instrument and execution boundary.

## Retained evidence and custody

Raw outputs remain outside Git under `/mnt/data/nightscout-workspace/artifacts/`.

| Retained identifier | Evidence |
|---|---|
| `pgstream-n1000-startup-repair-20261114/runtime-5fe-01/attachment-01` | Original passing discovery, uploader/probe, storage oracle, SQL and cgroups. |
| `pgstream-n1000-startup-repair-20261114/runtime-5fe-01/root-final-run-audit.json` | Root raw-input audit, SHA-256 `4afcc833a67b4138cccb0f4f39a7b41f01ebadda7fdb52f7c75a568954caf3fe`. |
| Same runtime, `independent-rest-audit/audit.json` | Independent REST audit, SHA-256 `f1abc8c3375ca93236303b807f56fed12e3acb0057cfcfee6ca1a2251c7286fe`. |
| Same runtime, `root-post-capture-audit.json` | Separate later observation, SHA-256 `2865a2e978d2018b57d075a0e11eb56bb1c2cc56f25f0836bc2dd73050f6dfe1`. |
| Same runtime, `stop-preserve-fb2f56579f6d4caa961501de38e8e0b9/receipt.json` | All nine roles STOPPED_PRESERVED/PID zero; 65 process incarnations gone. SHA-256 `56d24fabff5917f33dfb2a81421026d9b7bb9e7cdcfcd14b8dc3f85e89690ff9`. |
| `joined-startup-enabled-corpus-20261114` | Original 26-failure corpus and verified fixture cleanup. |
| `evaluator-corpus-coordination-20261114` | Original sequential-parent RED controls and repaired focused checks. |
| `provisioning-corpus-contracts-20261114` | Focused GREEN/RED/restored GREEN and verified disposable fixture cleanup. |
| `rest-corpus-repair-20261114` | Focused native REST repair checks and cleanup. |
| `joined-corpus-repair-acceptance-20261114` and `pgstream-accepted-build-b537-20261114` | Final source acceptance, canonical image and final prcheck. |

Original failed startup, progress-reset and partial captures remain retained and
are not overwritten by this result. The single evolving local handoff is
`externals/work/HANDOFF-pgstream-flow-2026-11-13.md`. All paid resources were
removed and independently verified absent. No new cloud resource, push,
application-dev merge or release occurred.
