# Tenant clock HTTP: fixed connection recovery — 2026-11-06

**Reproduced focused prototype result:** the transactional PostgreSQL tenant clock passes all seven functional HTTP cases at the pinned source below. An operator-terminated database connection produces a sanitized HTTP503, rolls back its write and clock allocation, and leaves the same API worker able to read and write. Removing the checked-out Client error listener reproduces worker loss and makes the stronger check fail; restoring the source passes again.

This immutable synthetic local record covers the corrected clock HTTP cohort and connection-failure recovery. The earlier availability failure has its own [canonical diagnostic](tenant-clock-http-backend-abort-diagnostic-2026-11-06.md). The [machine capture](tenant-clock-http-fixed-recovery-2026-11-06.json) contains pins, source and log hashes, outcomes and cleanup classifications. No programme gate or milestone state changes here.

## Anchors and scope

| Anchor | Exact source |
|---|---|
| Alignment base | `60776e0859527c248ff24d041d65c56805f0a7bc` |
| Tested application and restored archive | `3532c1a46d6fc3fb2100ed7704544d278f29357b` |
| Checked-out Client failure repair, cherry-picked into tested head | `11770146b420a2aa1ccad587030bfee50a8ea0b3` |
| Original transaction clock implementation | `3e76b2701538873e77c4bd461fbff3842fa9b443` |
| Corrected startup floor calculation, already included | `c52887d7eea054b0570c8ba8ce1dbce373856f19` |

The harness starts two actual REST CLI processes against operator-provisioned PostgreSQL and Vault fixtures. The clock is explicitly enabled in this synthetic multitenant preview. Node `v22.23.4`, npm `10.9.9` and installed `pg` driver `8.23.1` were measured. The declared database image is `postgres:16`; the exact server patch version was not captured in these runs.

**Read-derived mechanism:** `lib/storage/postgres-write-clock.js:52` locks the tenant clock row inside the data transaction. The connection repair observes errors on checked-out Clients, refuses further use of a failed transaction and evicts failed connections through the pool release path. This record tests that behavior through HTTP; it does not establish every disconnect schedule. Existing numeric history cursors and opt-in configuration remain the implementation contract. Complete single/Mongo regression acceptance on the assembled candidate remains unmeasured here.

## Functional cohort

`fixed-functional-3532.log`: **7 passing, 1 pending, 0 failing (11s)**. The pending case is the explicitly opt-in performance workload; it supplies no performance result.

| Actual case | Reproduced observation |
|---|---|
| Equal wall clocks in separate API workers, then worker restart | Stamps advance `1793991706986 → 1793991706987 → 1793991706988`; an exclusive history cursor includes the later committed record. |
| Same-tenant concurrent writers blocked behind actual data-row update | Observed wait chain reaches the clock row; commits advance `1793991708168 → 1793991708169`. Another tenant progresses while that chain is blocked. |
| Node SIGKILL characterization | Backend remains active waiting on a transaction lock and W2 remains pending until the independent original data-row blocker is explicitly released. The aborted row stays unchanged; survivor advances the prior floor by one. This is not a rapid recovery bound. |
| Operator termination of the observed W1 database backend | W2 commits while the original data-row blocker remains held. W1 receives HTTP503 with exact body `{error: 'STORAGE_UNAVAILABLE'}`; aborted row and allocation roll back. The same W1 then returns GET200 and POST201, and W2 history sees that later write. |
| Real data insertion CHECK failure | HTTP500; clock floor unchanged. |
| Individual committed writes with limit-one history paging | No skipped scalar committed record in the exercised equal-clock sequence. |
| Unsafe operator-provisioned clock state | Missing/stale floors, unsafe grants and missing FORCE RLS refuse startup before binding. |

In the operator-abort case the prior floor is `1793991709497`, W2 commits `1793991709498`, and recovered W1 commits `1793991709499`. The passive W1 monitor reports no fatal event; bounded stderr reports no unhandled error. Both workers remain subject to normal strict exit0 and socket-closure cleanup checks. The monitor uses only `uncaughtExceptionMonitor`; it does not suppress exceptions or install a Client listener.

## Break-it control and restored positive

The control runs in a private archive of the exact tested application, with its own dependency copy. The single source change removes only `client.on('error', connectionFailed)` from `lib/storage/postgres-connection.js`. The healthy-worker, sanitized-response and strict shutdown assertions are unchanged.

| Capture | Actual result |
|---|---|
| `fixed-listener-removal-control-3532.log` | **0 passing, 2 failing (4s)**. Primary assertion: required HTTP failure is replaced by socket hang up / ECONNRESET. Secondary afterEach failure: strict cleanup detects worker exit1, signal null. The bounded stack identifies an unhandled Client error; the passive monitor records uncaughtException. Both failures follow the reproduced worker loss; this is not a setup failure. |
| `fixed-restored-survival-3532.log` | **1 passing, 0 failing (4s)** selected operator-abort case. Actual HTTP503, same worker GET200 and POST201, no fatal monitor or unhandled error, normal strict shutdown passes. Prior floor `1793991945644`, survivor `1793991945645`, recovered-worker write `1793991945646`. |

The restored archive and clean tested worktree match the committed bytes for the clock, readiness implementation, HTTP test, PostgreSQL connection implementation and clock HTTP fixture. The machine capture records their hashes. Serialization, readiness and rollback source ablations were not run in this focused slot; no acceptance of those controls is inferred.

## Capture integrity and cleanup

| Preserved local raw log | SHA-256 |
|---|---|
| `fixed-functional-3532.log` | `918abd46f3148ca1e930cb04fc6d7dc1c90fe552c32ba08861f711abfe534b3f` |
| `fixed-listener-removal-control-3532.log` | `a16e47de42fdf92f9b4f6053b7d2626485cb83722772e655d0e7ee70210a0be1` |
| `fixed-restored-survival-3532.log` | `2ac63e7a4cd0fbdb6237b67346f05ab8bb840ba687756f4de2bc68dcc59423ae` |

The parent independently inspected each exact container and volume recorded by each run. All **6 containers and 9 volumes** were absent; per-run private audit JSONs retain the resource-specific results. No global cleanup or peer resource operation was used. Raw logs and audits remain local; the public capture omits resource identities, host paths, credentials and request recipes. The exclusive verification slot was explicitly released after the audits.

## Remaining work

Contention and ingestion latency are **UNMEASURED**. The functional lock-wait observation proves serialization and progress in that schedule, not throughput, tail latency, fairness or an operating limit. The optional benchmark must run in the coordinated slot against the frozen assembled candidate, with its clock-off comparison explicitly identified.

Full nonbrowser/browser tests, single/Mongo regressions on the assembled candidate, broader failure schedules and final prcheck remain outside this capture. Rapid cleanup of a PostgreSQL backend after a Node process dies is not established. Multi-machine deployment, realtime/derived-view recovery, event delivery and notification replay are separate work. This record authorizes no default enablement, deployment, release or milestone promotion.

## Record validation

`make docs-links` passes with this report staged. `make queue-check` fails in this isolated alignment worktree at queue validation: the inherited P0-F gate cwd `externals/work/nc-jitter` is absent for two gate entries. No substitute directory was created. This is a record-check limitation, separate from the runtime outcomes above. No queue manifest or generated view was edited.
