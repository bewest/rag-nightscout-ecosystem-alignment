# MT-BENCH-BASELINE: the one-host multitenant Compose reference on a workstation, 2026-11-11 (UTC)

*Contributor-facing measurement record. Captured 2026-11-11 03:12–04:10 UTC; not edited after capture.
The numbers are the deliverable; no limit is claimed or implied. Every figure was taken **under
concurrent load** (see "Host"). Synthetic tenants and data only.*

## Anchors

| what | value |
|---|---|
| core under test | #8898 head `16a1fc2d45e59602eb6ec3e3bf6f506f35bcc5b1`, `deploy/multitenant` tree `6529d40282ea4589ea75c71712839d4db6e9940b`; own worktree `externals/work/crm-bench-20261110` (detached, own `npm ci`) |
| why core's tree and not the deploy home | it is exactly the head named for M7. nightscout-deploy `main` (`cda38265`) still carries the `ed2ced00` import; its `16a1fc2d` sync is branch `deploy/compose-sync-20261110` (`085d88a`), whose `config.js` leaves out `ownership_operator` |
| Compose fixes | nightscout-deploy `bench/compose-baseline-20261110` = `4e5a1051ecd67744171af66332789b80d2b5795e` (on `085d88a`): fix 1 `54af5f2e`, fix 2 `4e5a1051`. `tools/compose-identity-check.sh` passes on both commits. Not pushed |
| how the fixes reach the run | `make-overlay.sh` = core's `config.js`/`bootstrap.js` at `16a1fc2d` + `git diff 085d88a 4e5a1051` of those two files, mounted into the one-shot bootstrap container only (`compose.bench.yaml`). Serving images are unmodified. Overlay sha256: `config.js` `c0ef0e6f…4583`, `bootstrap.js` `06bb1832…6761` |
| application image | `sha256:964ed43b5475be94426a3353a5a979b42d6743432ef5d1dd67c0abdd932c5a7e`, built by `deploy/multitenant/build.js` from `16a1fc2d` (label `org.opencontainers.image.revision` checked by `bench.sh deploy`); removed afterwards |
| other images (pinned in core `compose.yaml`) | postgres `@sha256:721873c3…` (local id `81bd698b`), vault `@sha256:962a9287…` (`8794a735`), nginx `@sha256:65645c7b…` (`6769dc3a`) |
| tools | k6 `grafana/k6:1.3.0` `@sha256:3ddc8b1a33a2c3d8edc6e99b6a762ae36cba08788463458f5e6a7703e14eb77d` (k6 v1.3.0); socket.io-client 4.8.3 from the core lockfile; host Node v22.23.4; PostgreSQL `pg_stat_statements` in the `postgres` database |
| harness | `tools/mt-bench/compose-baseline/` (this commit) |
| per-run summaries | [`runs/`](runs/) (`summarize.js` output), [`summary.json`](summary.json) (combined, keyed by workload) |

## Host

11th Gen Intel Core i7-11800H @ 2.30GHz, 16 logical cores, 64 GB RAM (65683804 kB), Docker root on
`/dev/nvme1n1p2` (453G, 193G free, 56% used), Docker 29.1.3, Compose 2.40.3, kernel 6.18.7. The brief's
"92% / 42 GB free" is `/dev/sda1` (`/opt/external_home`), not the Docker disk.

Concurrent load: 44–46 containers of other projects ran throughout (52–53 running in all). Load average
over the published runs ranged from 2.0 to 25.4 (1-minute, sampled every 2 s); most of it above 8 was this
bench's own PostgreSQL. The samplers add load too: `docker stats --no-stream` every 2 s kept `dockerd` at
about 1 core (114% in one `top` sample). The figures are therefore labelled **under concurrent load**.

## What was run

Per tenant count: `bench.sh deploy N` (fresh project, volumes and private state), then two workloads on
the same deployment, then teardown:

- **real**: real cadence (`BENCH_ACCEL=1`), 300 s steady state;
- **x10**: cycle compressed 10× (one 5-minute cycle per 30 s), 120 s.

Each run: 30 s idle window (no clients) → k6 workload with the socket probe alongside → realtime restart
(reconnect recovery) → oracle, disk, summaries. Client shapes, the hot tenant (×10) and the probe (20
sockets on the hot tenant, one on each of up to 40 others, polling transport like the stock browser,
one sgv every 5 s) are in the [harness README](../../../tools/mt-bench/compose-baseline/README.md).

Tenant counts: **1, 10, 50 measured. 100 and 200 do not start** (below). N=50 x10 ran with realtime
down: the realtime restart at the end of N=50 real did not come back (below), so its socket and
realtime columns are empty by measurement, not omission.

## Results (quoted from `table.js` output)
### Latency, ms p50 / p95 / p99 (real)

| N | offered req | w_sgv | w_devicestatus | w_treatments_v3 | r_sgv | r_devicestatus | r_treatments | r_status | failed | dropped |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 117 | 698 / 869.1 / 959.6 | 685.6 / 868.1 / 939.8 | 279.7 / 437.8 / 444.8 | 315.1 / 696.2 / 834.2 | 681.4 / 858.3 / 941.6 | 686.8 / 873.4 / 959.3 | 1016.3 / 1179.7 / 1225.3 | 0% | 0 |
| 10 | 223 | 1257.6 / 1370 / 1489.3 | 1259.6 / 1377.3 / 1509.1 | 401.5 / 481.8 / 563.9 | 607.9 / 1243.1 / 1302.4 | 1231.4 / 1352.3 / 1479.7 | 1226.9 / 1329.4 / 1451 | 1731.1 / 1858 / 2127.6 | 0% | 0 |
| 50 | 703 | 1470.6 / 2155.4 / 2441.9 | 1460.5 / 2133 / 2418.8 | 496.1 / 688.4 / 1220.6 | 718.9 / 1541.6 / 2042.5 | 1450.5 / 2142.1 / 2318 | 1441.8 / 2091.3 / 2275.7 | 2029 / 2736.4 / 2992.2 | 0% | 0 |

### Sockets, recovery, oracle, disk (real)

| N | sockets | fanout hot p50/p95/p99 ms | fanout cold p50/p95/p99 ms | delivered/expected | realtime restart: stock recovered | retrying client: recovered, all after ms | oracle | bytes per tenant-day |
|---|---|---|---|---|---|---|---|---|
| 1 | 20 (primed 20) | 2958 / 4670 / 5142 (n 1120) | – | 1120/1120 | 1/20 | 20/20, 11832 | GREEN | 5678784 |
| 10 | 29 (primed 29) | 5724 / 7715 / 8008 (n 120) | 2324 / 3447 / 3820 (n 47) | 167/167 | 1/29 | 29/29, 45799 | GREEN | 4366944 |
| 50 | 60 (primed 21) | – | 4913 / 8173 / 13015 (n 28) | 28/89 | 0/60 | 0/60, – | GREEN | 2198016 |

### CPU % mean (max) and RSS MiB max per role, idle → load (real)

| N | api | realtime | evaluator | tenant-admin | postgres | vault | nginx | ui |
|---|---|---|---|---|---|---|---|---|
| 1 | 18.8 → 18.3 (64.9); 237.8 | 12.9 → 6.6 (18.2); 176.3 | 9.4 → 11.8 (20.1); 172.2 | 0 → 4 (8.6); 53 | 125.2 → 139.7 (506.8); 223.2 | 6 → 5.8 (11.2); 47.6 | 0.1 → 0.3 (0.8); 16.4 | 3.3 → 5.8 (13.5); 41.4 |
| 10 | 3.5 → 35.2 (67.2); 328.2 | 49.9 → 38.3 (53.8); 272.8 | 69.6 → 69.8 (86.9); 267.7 | 1.5 → 7 (13.9); 58 | 898.5 → 996.2 (1196.2); 286.1 | 11.7 → 4.8 (18.8); 67 | 0 → 0.6 (1.1); 15.9 | 10.9 → 7.9 (19.6); 41.6 |
| 50 | 19.8 → 40.1 (75.8); 442 | 61.7 → 51.7 (65.1); 278.5 | 63.5 → 71.2 (91.1); 305 | 8.9 → 7.5 (14.7); 54.3 | 715.4 → 917.9 (1109.4); 285.6 | 1.4 → 8.7 (18.6); 82.3 | 0 → 0.3 (0.9); 19.6 | 10.3 → 8.9 (21.7); 39.5 |

### PostgreSQL per phase (real): DB ms/s total; window leases per tenant per second (evaluator, realtime); top waits during load

| N | idle DB ms/s | load DB ms/s | idle leases/tenant/s eval, rt | load leases/tenant/s eval, rt | ungranted locks max | top active waits (mean backends) |
|---|---|---|---|---|---|---|
| 1 | 174 | 365.7 | 4, 1 | 3.99, 0.47 | 0 | CPU:- 1.3; Client:ClientRead 0.1; IO:WALSync 0 |
| 10 | 2140.8 | 2475.5 | 3.34, 0.98 | 2.85, 0.6 | 0 | CPU:- 8.1; Client:ClientRead 0.7; IO:WALSync 0.1 |
| 50 | 1686.8 | 2401.1 | 0.38, 0.2 | 0.34, 0.14 | 0 | CPU:- 8.4; Client:ClientRead 0.7; IO:WALSync 0.1 |

### Host during each run (real)

| N | load avg before | load avg after | containers running (other projects) | deploy: bootstrap s, start s |
|---|---|---|---|---|
| 1 | 3.23 5.19 4.08 | 2.01 3.16 3.50 | 52 (44) | 6.8, 8.7 |
| 10 | 4.47 4.30 3.91 | 10.87 10.66 7.28 | 52 (44) | 6.9, 10.7 |
| 50 | 13.86 13.97 9.83 | 12.36 13.92 12.28 | 53 (45) | 7.1, 29.4 |
### Latency, ms p50 / p95 / p99 (x10)

| N | offered req | w_sgv | w_devicestatus | w_treatments_v3 | r_sgv | r_devicestatus | r_treatments | r_status | failed | dropped |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 445 | 727.3 / 803.4 / 867.6 | 733.3 / 810.3 / 862.1 | 227.1 / 254.5 / 256.8 | 337.5 / 714.4 / 774.4 | 722.4 / 784.1 / 856.9 | 723.2 / 800.8 / 851.2 | 1014.1 / 1060.2 / 1112.7 | 0% | 0 |
| 10 | 840 | 5749.9 / 6581.7 / 6670.9 | 5591.5 / 6591.4 / 6840.2 | 4935.6 / 5511.7 / 5645.4 | 5675.9 / 6470.5 / 6704.3 | 5769.1 / 6522.3 / 6696.3 | 5619 / 6503.2 / 6579.6 | 6472.5 / 7059.6 / 7328.1 | 16.5% | 9 |
| 50 | 2603 | 5004.3 / 6569.9 / 6763.3 | 5004.4 / 6533.4 / 6720.3 | 5004.1 / 5390.7 / 5622.7 | 5003.2 / 6561.9 / 6765.4 | 5004.1 / 6514.1 / 6668.1 | 5004.3 / 6524.2 / 6742.1 | 5004.1 / 7045.6 / 7316.3 | 73.1% | 47 |

### Sockets, recovery, oracle, disk (x10)

| N | sockets | fanout hot p50/p95/p99 ms | fanout cold p50/p95/p99 ms | delivered/expected | realtime restart: stock recovered | retrying client: recovered, all after ms | oracle | bytes per tenant-day |
|---|---|---|---|---|---|---|---|---|
| 1 | 20 (primed 20) | 2988 / 4755 / 5339 (n 460) | – | 460/460 | 0/20 | 20/20, 13229 | GREEN | 1489248 |
| 10 | 29 (primed 12) | 47737 / 65937 / 65937 (n 9) | – | 9/52 | 0/29 | 29/29, 18360 | GREEN | 1751328 |
| 50 | 60 (primed 0) | – | – | 0/34 | 0/60 | 0/60, – | GREEN | 1721088 |

### CPU % mean (max) and RSS MiB max per role, idle → load (x10)

| N | api | realtime | evaluator | tenant-admin | postgres | vault | nginx | ui |
|---|---|---|---|---|---|---|---|---|
| 1 | 5.9 → 39.5 (69.1); 298.6 | 9.8 → 3.8 (10); 171 | 15 → 13.4 (20.3); 178.9 | 0 → 2.1 (9); 39.6 | 126.8 → 311.2 (537.2); 235.6 | 1.5 → 5.9 (14.3); 51.3 | 0.1 → 0.5 (0.9); 16.6 | 7.1 → 5.6 (15.7); 41.1 |
| 10 | 15.5 → 62.6 (81.5); 360.1 | 53.1 → 29.2 (51); 269.7 | 72.2 → 58.3 (73.6); 261.2 | 4 → 12.3 (14.5); 52.2 | 896.8 → 1086.2 (1208.4); 288.6 | 11.2 → 15.4 (19.5); 52.5 | 0 → 0.3 (0.7); 15.2 | 11.8 → 9.2 (21.1); 28 |
| 50 | 3.2 → 64.4 (81.5); 436.1 | – | 74.7 → 71.8 (91.4); 330.8 | 3.1 → 7 (15.4); 39.6 | 463.2 → 765.3 (940.7); 223.6 | 3.2 → 9.2 (20.8); 77.4 | 0 → 0.7 (1); 19.3 | 2.1 → 8.9 (20.7); 41.1 |

### PostgreSQL per phase (x10): DB ms/s total; window leases per tenant per second (evaluator, realtime); top waits during load

| N | idle DB ms/s | load DB ms/s | idle leases/tenant/s eval, rt | load leases/tenant/s eval, rt | ungranted locks max | top active waits (mean backends) |
|---|---|---|---|---|---|---|
| 1 | 185.8 | 736.5 | 4.03, 1 | 3.99, 0.65 | 0 | CPU:- 2.8; Client:ClientRead 0.3; IO:WALSync 0 |
| 10 | 2244.9 | 2939.6 | 3.02, 0.9 | 1.97, 0.46 | 0 | CPU:- 11.5; Client:ClientRead 0.6; IO:WALSync 0.3 |
| 50 | 1130.2 | 2017.5 | 0.51, – | 0.33, – | 0 | CPU:- 7.3; Client:ClientRead 0.7; IO:WALSync 0.2 |

### Host during each run (x10)

| N | load avg before | load avg after | containers running (other projects) | deploy: bootstrap s, start s |
|---|---|---|---|---|
| 1 | 2.01 3.16 3.50 | 5.88 4.53 3.97 | 52 (44) | 6.8, 8.7 |
| 10 | 10.87 10.66 7.28 | 16.47 14.59 9.80 | 52 (44) | 6.9, 10.7 |
| 50 | 12.36 13.92 12.28 | 11.56 13.68 13.05 | 53 (46) | 7.1, 29.4 |

Reading the tables:

- Latency columns are per client shape (`k6/workload.js`); "failed" is the request-weighted failure rate
  over all shapes; "dropped" counts k6 iterations not started because no VU was free.
- Fanout is from sending the probe's POST to the first `dataUpdate` carrying that sgv on each socket of
  that tenant. "primed" counts sockets that received any `dataUpdate` within 30 s of opening.
- Realtime restart: `docker compose restart realtime` with every probe socket connected. "Stock" waits
  30 s with socket.io-client's own behaviour (no reconnect after a server-initiated disconnect, as the
  stock browser); "retrying" then makes every dark socket reconnect, re-trying each server disconnect
  after 1–5 s jitter, for up to 180 s.
- Window leases per tenant per second: one `INSERT INTO tenant_lifecycle_operations` per tenant operation
  window (`pg_stat_statements`, reset per phase). For the evaluator this is its per-tenant cycle rate; at
  N=1 it is 4/s (two 1 s timers), at N=50 0.34–0.38/s, i.e. one cycle per tenant about every 3 s.
- Bytes per tenant-day = table growth (heap, TOAST, indexes) per stored row × 288 per shape. The runs
  stored 10–111 rows per table, so 8 KB page allocation dominates: per-row growth ranged 1,100–2,294 B
  (entries), 2,253–10,426 B (devicestatus) and 1,386–8,192 B (treatments); stored `doc` size was 446,
  1,602 and 446 B. The tenant-day figure is between 1.49 MB (n1 x10, the most rows per table) and
  5.7 MB; the jsonb payload alone is 0.72 MB. A run with thousands of rows per table is needed for a
  single number (UNMEASURED below).
- Oracle: GREEN on every run. At N=10 x10 43 writes and at N=50 x10 564 writes ended in a client timeout
  or 5xx; none of them was stored (stored = accepted in both).

### Tenant counts that do not start

| N | result | mechanism (reproduced at the symptom; cause from a temporary diagnostic) |
|---|---|---|
| 100 | `deploy` fails: realtime exits 78 (`dependency failed to start: container nsbench-n100-realtime-1 exited (78)`); api started | realtime start refreshes every tenant at once and refuses unless all succeed (`lib/server/realtime/runtime.js:43-45`) |
| 200 | `deploy` fails twice: api exits 78 | diagnostic copy of `preview-api.js` printing the swallowed error: `timeout exceeded when trying to connect` (pg-pool) from `lib/tenant-lifecycle/operation-window.js:103`. `startup.warm()` (`lib/server/serve/preview-api.js:121`) warms every tenant at once (`lib/server/serve/tenant-startup.js:33`), each warm takes an operation-pool client (`max:8`, `connectionTimeoutMillis:5000`, `lib/server/serve/operation-cohort-config.js:49`) |
| 50, after a restart | realtime does not come back: SIGTERM, "still open 10000 ms after SIGTERM", then `realtime preview readiness or initialization refused`, `Exited (78)` | reproduced twice (campaign N=50 real; a second deployment, `runs/n50-restart-repro.json`, container log kept in the private run directory). Same startup path as N=100 under a loaded PostgreSQL |

Bootstrap itself completed at every N, including 200 (6.8–7.1 s up to N=50); start time rose from 8.7 s
(N=1) to 29.4 s (N=50).

## Bottlenecks observed

Mechanisms are read from the source at `16a1fc2d`; the costs are measured.

1. **Per-transaction catalogue admission.** Every tenant transaction acquires an operation-window lease
   (`lib/storage/postgres-connection.js:128`) and re-runs the window admission
   (`lib/tenant-lifecycle/operation-window.js:57` → `operation-window-readiness.js:64-87`): a role query
   plus one catalogue query per control table (5), every time. At idle these queries are most of the
   database work: N=1 idle, 174 DB-ms/s, of which `/* operation-window-table */` and
   `/* operation-window-role lifetime */` took 4,376 of 5,219 ms over 30 s; the lifetime role query
   costs 5–9 ms per call (`EXISTS` over `pg_proc`/`pg_class` with privilege functions). At N=1 under
   load the api role ran 93,795 `operation-window-table` statements (34.9 s DB) in 302 s.
2. **Per-tenant polling every second, independent of traffic.** The evaluator runs an acquisition and a
   time-only cycle for every tenant every second (`lib/server/serve/evaluator-runtime.js:240-241`) and
   realtime refreshes every tenant every second (`lib/server/realtime/runtime.js:46`), each through (1).
   Idle PostgreSQL CPU: 125% at N=1, 899% at N=10, 715% at N=50 (16-core host); at N=50 the evaluator
   no longer keeps up (0.38 cycles/tenant/s against 4 at N=1).
3. **Fixed pool sizes.** api data pool `max: 4`, 5 s connect timeout (`lib/server/serve/preview-api.js:57-58`);
   realtime `max: 4` (`lib/server/serve/preview-realtime.js:32`); evaluator `max: 4`
   (`lib/server/serve/evaluator-preview.js:31`); operation pool `max: 8` per role
   (`lib/server/serve/operation-cohort-config.js:49`). The latency floor of 5,004 ms with 16.5% (N=10 x10)
   and 73.1% (N=50 x10) failures is the 5 s pool connect timeout.
4. **Socket fanout is sequential per socket and re-authorizes every second.** `fanout()` walks every
   socket and awaits `current(state)` (an IPC `authorizeSocket` to the api, which opens its own tenant
   transaction) before sending, socket by socket (`lib/server/realtime/protocol.js:180-199`, `:55`), and
   sends a full `dataUpdate` to every primed socket on every 1 s refresh, changed or not. Hot-tenant
   fanout p50 with 20 sockets: 2,958 ms (N=1), 5,724 ms (N=10). The api's DB work at N=1 under load is
   18,759 tenant transactions in 302 s for 117 k6 requests and about 60 probe writes; the attribution of the rest to these socket authorizations is read-derived.
5. **Socket admission under concurrency and restart.** A socket's priming holds an operation-window lease
   while it authorizes and refreshes; when the pools are exhausted the window fails, `initial()`
   disconnects the socket (`lib/server/realtime/protocol.js:81-84`), and socket.io-client does not
   reconnect after a server-initiated disconnect. Shutdown also disconnects every socket server-side
   (`protocol.js:240`). Measured on an idle N=2 deployment, sockets opened at once: 9/9 primed with 9 sockets; with 13–21,
   4 of 6 attempts refused most or all (0/13, 0/21, 3/17, 0/21 primed; 13/13 and 21/21 otherwise); opened
   250 ms apart, 21/21 primed. After a realtime restart 0–1 of 20–29
   stock sockets recovered; retrying clients recovered in 11.8–45.8 s (N=1, N=10).
6. **Configured ceiling.** realtime `maxSockets: 100` per process across all tenants
   (`deploy/multitenant/config.js:133`); not reached in these runs (at most 60 sockets).

## Compose fixes (nightscout-deploy `bench/compose-baseline-20261110`, not pushed)

1. `54af5f2e` **api refuses startup on the unmodified plan** (exit 78). The subject-admin store's
   `root_writer` connection runs under the operation window, whose admission needs the control-schema
   reads that `grants()` withheld from `root_writer` (`config.js:98` at `16a1fc2d`). Red on the
   unmodified plan, green with the fix. The decision whether `root_writer` should be fenced by the
   window (this fix) or its store should not use the window belongs to the root-admin parity owner.
2. `4e5a1051` **the plan is fixed at two tenants**; `NS_DEMO_TENANTS` (1..1000, default 2) on the
   bootstrap service. At the default `documents()` is byte-identical to core's and `bootstrap.test.js`
   passes 5/5. `restore.js` and `ownership-admin/ownership-grants.js` still assume two tenants.

N=100 and N=200 are not fixed: their causes are core pool sizes and startup concurrency, not
deployment configuration.

## Controls

- **Oracle break-it:** `bench.sh control 2` on a 30 s run: baseline `ORACLE GREEN … stored 36, accepted 36`;
  one entry re-marked → `ORACLE RED: tenants 2, mismatched 1, stored 35, accepted 36`; restored →
  `ORACLE GREEN … stored 36, accepted 36`; `CONTROL PASS` (`runs/n2-oracle-control.json`). Two earlier
  attempts did not exercise the oracle (the ordinal trigger refused an unbound UPDATE; the control then
  picked the state directory); the N=10 campaign entry `CONTROL FAIL` is that harness defect, not a red.
- **Oracle found a harness defect:** with a per-VU timestamp origin, colliding writes were merged by the
  server's dedup and the smoke oracle went red (stored 57, accepted 60); fixed with one run-wide origin.
- **Instrument perturbation found:** `pg_stat_statements` created in the application database made the
  lifetime window admission refuse every evaluator/realtime cycle (`foreign_functions`); the harness
  creates it in `postgres` only.
- **Compose fix 1:** red on the unmodified plan (api exit 78), green with the fix.

## UNMEASURED

- Every figure at 100 and 200 tenants (the reference does not start there).
- Evaluator cycle duration in-process (`runtime.health().cycles` is not exposed over the internal API);
  the lease rate above is the external proxy.
- Pool wait time inside the Node processes; only PostgreSQL-side waits (`pg_stat_activity`: no ungranted
  locks seen; waits were CPU and `ClientRead`) and client-side timeouts were measured.
- Disk per tenant-day as one number (needs thousands of rows per table) and WAL volume.
- Alarm delivery latency (`/alarm` namespace, evaluator → outbox → realtime).
- Socket fanout and restart at N=50 with a live realtime under x10 load, and any socket count above 60.
- A quiet host: no run had a load average below 2.
- Kubernetes binding: the workload and probe take a base URL; not run there.
- MT-BENCH-CONTRAST shapes (single-tenant Mongo, node-multienv).
