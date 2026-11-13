# 500-tenant idle sweep observations — 2026-11-13

**PARTIAL discovery capture; owned cleanup verified.** Both OFF and ON completed
two scheduled 120-second idle windows and one exact-write observation. SQL
collection failed in both arms. The controller returned 0 after collection and
cleanup; that does not promote the worker's PARTIAL verdict or grant capacity
acceptance. Results below are reproduced remote observations.

[Selected summary and evidence hashes](summary.json) retain bounded aggregates.
Raw captures, per-tenant rows, configuration/environment contents and provider,
container and tenant identities stay in ignored private evidence custody.

## Exact boundary

| Source | Exact identity |
|---|---|
| Core | `4f09765b767dd02da6791a0f77356383ddcea9a7` |
| Deployment overlay | `fd7ee57f231eb1a390f1f8397c30507fae66ccb2` |
| Actual overlay tree | `c3c4947156872e8d24243b30682607638d0c8ff7` |
| Transport | `d806f108828275cea64eca256ca7a84f4969c8c6` |
| Actual Node / npm / PostgreSQL | `v24.22.1` / `11.19.1` / `16.15` |

One colocated 16-vCPU/32-GiB VM and one byte-qualified built image were reused.
Both arms used the same 500-tenant roster. Recorded full API/evaluator/realtime
configuration custody matched after removing only evaluator/realtime `sweepMs`.
OFF omitted that field; ON selected 30000 through the shipping bootstrap generator.
Both arms explicitly selected a 120000 ms heartbeat horizon; the shipping 5000 ms
default was unchanged. The optional selected connection-budget profile and later
settings optimization were excluded.

Inspection sent one genuinely unselected full-roster request, with no selected-128
batching. Ordinary windows scheduled no HTTP/socket load and had SQL logging off.
The shipping primer commissioned authorization/ownership/session state and one
synthetic reading per tenant. History/HOT metadata do not establish a 24-hour
clinical workload, equal clinical ages or equal demanded work across arms.

## Observed CPU and work

CPU is whole-container logical cores, weighted across each arm's two counter
intervals. Bounds reflect request bracketing and include sparse observer overhead;
they are not confidence intervals or SQL-family CPU attribution.

| Service | OFF cores | ON cores | Descriptive change |
|---|---:|---:|---:|
| PostgreSQL | 4.3840–4.3940 | 3.8984–3.9076 | about 11% lower |
| Realtime | 0.26616–0.26676 | 0.10459–0.10480 | about 61% lower |
| Evaluator | 0.79665–0.79834 | 0.78253–0.78419 | about 2% lower |
| API | 0.07554–0.07570 | 0.07654–0.07670 | roughly flat |

Observed database session-counter births remained roughly 110–115/second in both
arms, including health/control/observer activity. These are database-wide session
counters with unmeasured statistics propagation lag, **not SQL QPS or per-service
connection attribution**. The sweep setting did not visibly remove this churn.

Actual completed TIME cycles were **167 OFF / 171 ON**; completed acquisitions and
failed completions were zero in all ordinary windows. All eight bookends reported
500 ready/admitted tenants and no evaluation alerts; the largest observed
confirmation age was 31149 ms. Confirmation age is not request or evaluation latency.

Complete TIME-demand/deadline proof remains absent. In the final ON window, 172
before-snapshot targets were due by the after-read request start, while 171
completions were observed. One target was 157 ms overdue at that bookend without
an observed completion or alert. Sparse snapshots do not establish continuous
freshness, every due opportunity or clinical acceptance.

## Writes, hints and SQL gap

Each arm accepted one unique synthetic write, read the exact stored record through
the normal API, and observed its server stamp covered by a stable unselected
evaluator checkpoint/revision with successful-acquisition evidence and an exact
re-read. POST-to-exact-GET was 301.9 ms OFF / 290.9 ms ON; published-input milestone
upper observations were 10.395 s / 4.193 s, including harness/poll/recheck work.
These single observations establish no p50/p95/p99, causal latency improvement,
cached clinical payload or delivery result.

Natural feed heartbeat/hint observations are retained in the summary. No healthy
lost-hint or listener-reconnect fault was injected, and the long heartbeat horizon
bounds what this experiment exercised. The recorded evaluator check/rotation
counts did not fall materially with ON. Read-derived hypothesis: elapsed-credit
accumulation and the one-page cap can keep a slow evaluator tick selecting near
its existing page amount. This is not measured SQL-family or CPU causation.

Both SQL slices stopped with `IDLE_DIAGNOSTIC_LOGGER_NOT_READY`. Captured stderr
identifies the inherited `reader_idle_log.py:25` output-path assertion, which only
allowed the old reader experiment layout. It refused the new OFF/ON directory
before opening the bounded log stream. SQL statement rates, family timings and
service attribution therefore remain **UNMEASURED**, not zero. A later separate
source repair cannot retroactively qualify this capture; no live patch or retry
was made.

## Custody, cleanup and limits

The unchanged private archive is **13,103,539 bytes / 1321 members**, SHA256
`e78cf931602675ce07f43a345d8bb07ad8acc726c60264270c1bc4fac09ec154`.
The summary hashes the archive, original bookends/observations, worker ledger,
source-pack proof, direct controller receipt/log, cleanup and assessment records.

Both fixture finalizations recorded no failures. Controller and watchdog cleanup
were verified; independent full-page inventory found zero owned droplets,
firewalls or tags and removed both exact original temporary SSH keys. All twelve
account inventory categories had unchanged pre/post resource identity sets.
Existing services/storage were preserved. The watchdog process exit code remains
UNMEASURED; verified cleanup is not an exit receipt.

The controller-through-watchdog interval was about 30.5 minutes. At the captured
$0.50/hour planning price, estimated compute is about **$0.25**; this is not an
invoice or billing cap. No paid test resources remain from this run.

This is fixed **OFF then ON**, two windows per arm, with order, age and demand
limits. The lower observed CPU is useful diagnostic evidence; capacity and causal
efficiency acceptance remain ungranted. No selected count, clinical/production,
isolation/restore acceptance, queue promotion or release claim follows. The
programme coordinator owns the single linked contents update; this leaf changes
no shared contents or queue state.
