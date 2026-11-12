# Multitenant capacity campaign, one-host Compose reference (2026-11-11/12)

*Dated measurement record (contributor-facing). Captured 2026-11-11 18:00Z to 2026-11-12 02:50Z;
not edited after capture. Synthetic tenants only. Every figure is labelled **measured** (read from
this campaign's tool output, files under [`runs/`](runs/)), **derived** (computed from measured
figures, method stated) or **read-derived** (from reading code, not run).*

## Verdicts

| question | answer |
|---|---|
| **1,000-tenant milestone** ([`m7-capacity-gate`](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#m7-capacity-gate)) | **Met on both heads.** Every 1,000-tenant run (8) finished with every role healthy, the stored-count oracle GREEN with zero uncertain writes, all probe writes delivered, and all tenants evaluated after the full restart. Socket caps differ by run (table below). |
| **3,000-tenant gate** | **Not met** on core `5c60aec6` + deploy `d1c7aca` on this host. Deploy and the idle window succeed at 3,000; under the real cadence with 2 sockets per tenant, 99.8% of HTTP requests fail (p50 10.2 s) and 134 of 6,000 sockets prime in 300 s (r1, measured). |
| **What runs out first at 3,000** | The **api's single JavaScript main thread**, driven by realtime's socket-authorize path, with heavy allocation. With sockets present (x2, x3) the api's event-loop utilisation is 0.993–0.995 and its process uses 4.4–4.5 cores, of which 0.94–0.96 is the main thread and 3.4–3.5 V8 worker (GC/compiler) threads; authorize throughput stays at about 140–215/s whatever the pool size (measured). With HTTP only (x1) the api's 8-client operation pool binds first: requests wait their 5 s pool timeout while the main thread runs at 0.74 (measured). PostgreSQL is not the limit (1.8–4.5 cores, 3–5 active backends on average; measured). |
| **Where the api main thread saturates** | About **1,350–1,400 tenants** under this workload (real cadence + 2 sockets per tenant). **Derived, an extrapolation:** b4's api main-thread utilisation of 0.73 at 1,000 tenants, scaled linearly to 1.0. No run was made at that N. |
| 5,000 and 10,000 | Not run (the 3,000 gate failed first). |

Reference to beat (from the decision): about 100 tenants per node for tenant-per-pod.

## Anchors

| tree | commit |
|---|---|
| alignment `main` at the time of writing | `10b509c48c3b6b034b4c062a7eea3312ca4124b9` |
| core #8898 batch join (runs r1–r3, ctl at 1,000) | `0392acf97c720a7e121eea47a9d42a0c8dbe9e73`, deploy `deploy/sync-0392acf9-20261111` `fe36212f64e856efddfc0339725e215ad037b698`, image `nscap:0392acf9-fe36212` |
| core capacity fixes 1 (run b1) | `workspace/capacity-fixes-20261111` `5517cb6c74f2906383a436d034b86be86a0f743a`, deploy `deploy/capacity-fixes-20261111` `ab950a2384ba825dff14ebab0dd84778ac0c6a39`, image `nscap:5517cb6c-ab950a2` |
| core capacity fixes 2 (runs b2–b4, r1 at 3,000, x1–x3) | `5c60aec669362b032a10d6dd7ac368e9c61e8003`, deploy `d1c7aca4f95998ae68d0fc42e3f236d68991b740`, image `nscap:5c60aec6-d1c7aca` |

Images 2 and 3 were built through the deploy repository's overlay path (core worktree at the core
commit, `deploy/multitenant` replaced by the deploy commit's `bindings/compose/multitenant`, marker
`.overlay.json` written by hand because `SOURCE.md` names 0392acf9), `prepare.js` + `build.js`;
both labels (`org.opencontainers.image.revision`, `org.nightscout.deploy.revision`) checked by
`build.js --check-image` and by `cap.sh` at every deploy. Image 1 was built by
[`build.sh`](../../../tools/mt-bench/capacity/build.sh) (git archive of both commits).

Host: 16 threads, 62 GiB, shared with peer sessions' containers (listed per run in
`host-deploy.txt` counts). PostgreSQL `max_connections` 100, `superuser_reserved_connections` 3
(measured from the running stack).

## Harness

[`tools/mt-bench/capacity/`](../../../tools/mt-bench/capacity/): `campaign.sh` (quiet-host wait,
then per run: deploy, idle, real cadence + sockets + probe writes, full four-role restart, oracle,
summary, teardown), `cap.sh` (the steps), `probe.js` (sockets, probe writes, restart measurements),
`startup.js`, `summarize.js` (one `summary.json` per run), `aggregate.js` (tables), `k6/workload.js`.
Workload: k6 real cadence (sgv every 5 min per tenant, devicestatus, reads), 2 stock-browser
Socket.IO clients per tenant (polling, no reconnect after a server-initiated disconnect), one probe
sgv every 3 s; idle 600 s, load 900 s (x runs: 300 s / 600 s).

Instruments (mounted over core files in the realtime and api containers; files listed in the run
directories' compose extras, not committed): a 1 s realtime `DIAG` line (startup state, protocol
counters, event-loop utilisation/delay), a counter around realtime's whole-file config read, and a
2 s api `DIAGAPI` line (startup state and alert causes, event-loop utilisation and delay, CPU by
thread from `/proc/self/task`). The `ctl` run additionally mounts the unbounded per-socket warm
(realtime design control).

Socket cap per run: the 0392acf9 runs and b1 used a bench patch raising realtime `maxSockets` from
100 to 25,000. From d1c7aca the deploy tree sets `maxSockets = max(100, N × NS_DEMO_SOCKETS_PER_TENANT)`;
b2, b3 and r1 ran at the default 2 (cap 2N), b4 and x1–x3 at 4 (cap 4N). The 3,000-tenant runs used
`MULTITENANT_CONFIG_MAX_BYTES` = 4,194,304.

## Runs

All measured. "eval ready" is the probe's reading after the restart; "re-derived" is the
evaluator log's `Evaluator preview started` time, one basis for every run (see Corrections).

| head | run | N | socket cap | load1 mean idle / load | oracle | stock sockets back unaided | retry flood | eval ready s (probe / re-derived) | evaluated ≤60 s | realtime warm failed peak | realtime all ready s | POST entries p50 ms / failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0392acf9 | ctl (unbounded warm) | 1,000 | 25,000 patch | 2.5 / 6.7 | GREEN 6001 = 6001 | 2000/2000, 110.3 s | – | 12.8 / 11.1 | 925 | 255 | 110.8 | 242 / 0% |
| 0392acf9 | r1 | 1,000 | 25,000 patch | 1.7 / 7.9 | GREEN 6001 = 6001 | 2000/2000, 171.8 s | – | 14.7 / 11.5 | 865 | 384 | 172.3 | 252 / 0% |
| 0392acf9 | r2 | 1,000 | 25,000 patch | 1.9 / 6.9 | GREEN 6001 = 6001 | 2000/2000, 149.6 s | – | 14.7 / 11.8 | 880 | 405 | 149.7 | 237 / 0% |
| 0392acf9 | r3 | 1,000 | 25,000 patch | 2.1 / 6.7 | GREEN 6002 = 6002 | 2000/2000, 129.1 s | – | 12.0 / 10.8 | 948 | 546 | 127.8 | 244 / 0% |
| 5517cb6c | b1 | 1,000 | 25,000 patch | 2.1 / 6.7 | GREEN 6002 = 6002 | 2000/2000, 96.3 s | – | 25.2 / 11.5 | 471 | 3 | 96.7 | 246 / 0% |
| 5c60aec6 | b2 | 1,000 | 2N (2,000) | 1.9 / 7.2 | GREEN 6002 = 6002 | 2000/2000, 95.0 s | – | 26.1 / 11.7 | 444 | 1 | 83.8 | 251 / 0% |
| 5c60aec6 | b3 | 1,000 | 2N (2,000) | 2.3 / 6.6 | GREEN 6002 = 6002 | **1501/2000** (499 server disconnects) | 2000/2000 in 6.3 s | 13.4 / 11.4 | 926 | 0 | 120.6 | 246 / 0% |
| 5c60aec6 | b4 | 1,000 | 4N (4,000) | 2.2 / 8.0 | GREEN 6002 = 6002 | 2000/2000, 209.5 s, 0 server disconnects | not needed | 14.7 / 11.8 | 890 | 7 | 193.0 | 268 / 0% |
| 5c60aec6 | r1 | 3,000 | 2N (6,000) | 4.2 / 16.1 | not informative (33 accepted, 17,768 uncertain) | 0/6000 (134 primed before restart) | 0/6000 | 34.2 / 31.9 | 1028 | 14 | not reached | 10,239 / 99.8% |
| 5c60aec6 | x1: k6 only | 3,000 | 4N | 3.6 / 8.0 | GREEN 3035 = 3035, 8,902 uncertain | no sockets | – | 26.2 / 25.5 | 1816 | 0 | – | 5,004 / 71% |
| 5c60aec6 | x2: sockets only | 3,000 | 4N | 4.1 / 15.8 | not applicable (no k6 writes) | 0/6000 (128 primed) | 0/6000 | 33.6 / 32.3 | 1077 | 15 | not reached | – |
| 5c60aec6 | x3: r1 shape, api pool 32 | 3,000 | 4N | 4.7 / 19.0 | not informative (16 accepted, 11,795 uncertain) | 0/6000 (138 primed) | 0/6000 | 40.2 / 39.2 | 556 | 4 | not reached | 10,235 / 99.8% |

Every run's final state: api, realtime, evaluator and tenant-admin `Up (healthy)`. Startup at 3,000:
bootstrap 58.6–60.5 s, api and realtime cold warm drained about 97 s after `compose up` (measured;
1,000: 23–24.5 s and 24–30 s). Full tables per head: [`runs/*/tables.md`](runs/).

**Failed deploys (measured):** 0392acf9 at 3,000 (r1, r2, r3, ctl): `COMPOSE_BOOTSTRAP_FAILED` with
no detail; reproduced by hand as core's 1 MiB role-config bound (api `config.json` 1,923,124 bytes).
5517cb6c at 3,000 (r1, r2): the ui refused more than 1,000 tenants (`UI_STARTUP_REFUSED`, `ui.js:29-31`);
directory `runs/core-5517cb6c-deploy-ab950a2/failed-3000-ui-limit/`. Both are closed (Findings).

## What runs out first at 3,000 tenants (x1–x3)

One variable per run against r1 (k6 + 2 sockets per tenant): x1 removes the sockets, x2 removes
k6, x3 restores both and raises the api's operation pool from 8 to 32 (`NS_POOL_OPERATION_MAX`,
api only; confirmed in the container). All figures measured over the load window.

| run | api cores (main / V8 workers) | api event-loop utilisation mean, delay p99 | realtime cores, utilisation | PostgreSQL cores, active backends mean (max) | authorize calls/s (peak) | requests |
|---|---|---|---|---|---|---|
| r1 (cap 2N) | 4.46 (not instrumented) | – | 2.36 | 1.59, 2.6 (12) | 145–215 (215) | p50 10.2 s, 99.8% failed |
| x1 k6 only | 0.87 (0.75 / 0.12) | 0.74, 177 ms | 0.41, 0.19 | 4.49, 4.9 (12) | none | p50 5.0 s (= pool timeout), 64–78% failed |
| x2 sockets only | 4.50 (0.96 / 3.54) | 0.993, 986 ms | 2.31, 0.98 | 1.81, 3.0 (13) | 138–208 (208) | – |
| x3 pool 32 | 4.39 (0.94 / 3.43) | 0.995, 1,366 ms | 2.27, 0.98 | 1.84, 4.0 (23) | 138–199 (199) | p50 10.2 s, 99.8% failed |

- **The pool is refuted as the limit once sockets are present.** In x3 the api's operation-pool
  identity reached 32 connections (per-role peaks summed to 84, 73 concurrent), and authorize
  throughput did not move from about 200/s (prediction was "well above 200/s, towards 800/s").
  Throughput topped out far below that with the pool full: the per-call cost is api CPU, not
  database contention (measured).
- **The api is one process with one JavaScript thread** (per-thread CPU from `/proc/self/task`):
  r1's 4.46 cores are one pinned main thread plus about 3.5 cores of V8 worker threads, generated by
  the socket/authorize path (x2), not by HTTP (x1: 0.87 cores). About 5 ms of main thread per
  authorize at about 200/s (derived: 0.96 core / 200 per s).
- **HTTP alone** at 3,000 waits on the 8-client operation pool: p50 equals the 5,000 ms pool connect
  timeout, and the api's database statement rate is flat across N (about 9.5 k/s at 3,000 in x1,
  10.1 k/s at 1,000 in r3, from `pg_stat_statements`; the most frequent statement's mean 0.77 vs
  0.70 ms). Demand is three times larger; throughput is not (measured; the pool mechanism is
  read-derived from [the api lane](../api-cost-vs-n-2026-11-11/README.md)).
- PostgreSQL `max_connections` 100 is a **deployment ceiling**: an api pool of 64 would have needed
  about 117 connections at peak (derived: r1 per-role peaks 61 − 8 + 64), above the 97 available;
  32 was the largest one-variable step.

## Marginal cost per tenant, 1,000 to 3,000 (idle)

Derived from the idle windows (no clients): mean of the eight 1,000-tenant runs against the mean of
the four 3,000-tenant runs, difference divided by 2,000. A load-window figure is not derivable,
because no 3,000-tenant load window served its load.

| role | 1,000: CPU ms/min, anon MiB | 3,000: CPU ms/min, anon MiB | marginal per tenant: CPU ms/min, anon KiB |
|---|---|---|---|
| api | 3,451, 717 | 7,144, 1,946 | 1.85, 629 |
| realtime | 5,388, 182 | 16,222, 238 | 5.42, 28 |
| evaluator | 7,904, 410 | 32,691, 790 | 12.39, 195 |
| tenant-admin | 2,896, 46 | 5,600, 49 | 1.35, 1 |
| postgres | 29,154, 19 | 84,747, 62 | 27.80, 22 |

The evaluator's and realtime's marginal CPU exceed their average at 1,000 (7.9 and 5.4 ms/min per
tenant): idle cost grows faster than N, consistent with the change-detector stamp scan below. At
3,000 the five roles idle at about 2.4 cores and 3.0 GiB anon (derived). Memory is not what runs out
first: 31.0–31.6 GiB was available before and after every 3,000-tenant load window (measured,
`host-before.txt` / `host-after.txt`).

Realtime's whole-file config read (instrument): at 1,000, 49–54 calls/s at 0.29 ms (3.5–3.7% of
realtime CPU); at 3,000 under sockets, 174–185 calls/s at 1.10–1.14 ms, about 0.2 core (8.7–9.2% of
realtime CPU) (measured).

## Bounded realtime against the unbounded control (1,000, 0392acf9, matched load)

| | r1 / r2 / r3 (bounded) | ctl (unbounded per-socket warm) |
|---|---|---|
| realtime warm failed peak after restart | 384 / 405 / 546 | 255 |
| `TENANT_WARM_FAILED` alerts (realtime) | 632 / 627 / 755 | 518 |
| restart command | 1.1 / 0.9 / 0.9 s | 0.9 s |
| realtime all ready after restart | 172.3 / 149.7 / 127.8 s | 110.8 s |
| stock sockets all back | 171.8 / 149.6 / 129.1 s | 110.3 s |

Measured; one control run. These restart figures carry the probe stall described under Corrections
(the 0392acf9 runs stalled at 7–31 s), and the warm-retry fix (5517cb6c) changed the bounded design's
failure count far more than the control comparison does: b1–b4 show a failed peak of 0–7.

## Corrections to figures reported during the campaign

1. **Evaluator recovery after the restart was a probe artifact, not slower evaluation.** `probe.js`
   restarted nginx with a synchronous `spawnSync`, freezing its own event loop for the command's
   duration (about 11 s when nginx waits out open connections). On the new head the edge samples
   before it included a 5 s hang, which moved the freeze into the evaluator's ready window:
   b1 freeze 13.9–25.1 s, ready read 25.2 s; b2 13.2–24.4 s, read 26.1 s. Evaluations during the
   freeze were absorbed into the warm baseline, so "evaluated within 60 s" fell to 471 and 444.
   Re-derived on one basis (evaluator log), the evaluator was ready at 10.8–11.8 s on every head
   (table above). Docker's own healthcheck in b2 first passed at 13.3 s (measured). Fixed in the
   harness (nginx restart asynchronous; role health polled in its own 250 ms loop, with Docker's
   healthcheck time kept as the reference); b3 then read 13.4 s and 926/1000. "Evaluated within 60 s"
   cannot be re-derived for the earlier runs: `tenant_lifecycle_operations` has no timestamp.
2. **"2000/2000 stock sockets back unaided" before b3 is affected by the same stall.** While the
   probe was frozen its clients did not reconnect, so the reconnect surge never met realtime's cap.
   With clients reconnecting immediately (b3), 499 of 2000 received `io server disconnect`.
3. **The b3 drops were the socket cap, closed by b4.** Cap 2N counts every live engine.io session,
   and sessions from the first reconnect stay live for up to about 45 s (read-derived,
   [realtime disconnect record](../realtime-restart-disconnect-2026-11-11/README.md)). b3 (measured,
   realtime's 1 s counter): sessions at exactly 2,000 from +27.5 to +50.6 s, then 2,000 → 1,501 by
   +55.6 s; `invalidated` and `primeRefreshFailures` 0. b4 at cap 4N (measured): zero server
   disconnects, 2000/2000 back unaided, sessions peaked at 2,455, above 2N. Decision:
   [`realtime-no-socket-cap`](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#realtime-no-socket-cap)
   (no per-process cap, plus cause codes).

## Findings

| finding | status | evidence |
|---|---|---|
| (a) Deploy overlay build path refused every overlay (`BUILD_INPUTS_DIRTY`) | closed, deploy `9fd2a81` (in d1c7aca) | [deploy fixes record](../deploy-capacity-fixes-2026-11-11/README.md) §5; images 2 and 3 built through it |
| (b) nginx 502 after a full role restart (stale upstream addresses) | closed, deploy `d3306bf` (re-resolution through Docker DNS) | 0392acf9 runs: edge 502,502,502 (ctl) and first served at 37–42 s until nginx restarted (r1, r2); new head: the first tenant served at 2.3–5.6 s after the restart in b1–b4, without an edge restart |
| (c) Realtime warm fails when the api restarts with it (0392acf9: failed peak 384 / 405 / 546, ctl 255; all ready 127.8–172.3 s vs 24–25 s cold) | closed, core `5517cb6c` warm retry | b1–b4: failed peak 3 / 1 / 0 / 7, `TENANT_WARM_FAILED` cause recorded only as the generic fallback |
| Bootstrap failures carried no detail | closed, deploy `8f9a97e` | deploy fixes record §1 |
| Role config bound 1 MiB (api config 641 B per tenant indented) | closed, core `5517cb6c` (`MULTITENANT_CONFIG_MAX_BYTES`) + deploy compact JSON | 3,000 deploys at 4 MiB, bootstrap 58.6–60.5 s |
| ui refused more than 1,000 tenants | closed, core `5c60aec6` (`PREVIEW_MAX_TENANTS` 10,000) + deploy d1c7aca | 3,000 deploys with ui healthy |
| Socket cap 2N drops reconnecting clients after a restart | decided: [`realtime-no-socket-cap`](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#realtime-no-socket-cap); runs here used cap 4N as a bench setting | Correction 3 |
| api main thread saturates on the socket-authorize path (about 5 ms main thread and heavy GC per authorize) | **open** (core) | x2, x3 |
| api operation pool of 8 binds first under HTTP-only load at 3,000 | **open** (core default; pool size is operator-settable) | x1 |
| Change-detector stamp scan grows with N: 71–76 ms per call at 3,000 (evaluator and realtime, about once a second each); not among the top statements at 1,000 | **open** (core) | x1 `load-pg-top.tsv`; idle marginal cost table |
| Realtime re-reads its whole config file on every `readCurrent` (1.1 ms per call at 3,000, about 0.2 core under sockets); the api lane reports the same shape for the per-request admission read | **open** (core) | config-read figures above; [api lane](../api-cost-vs-n-2026-11-11/README.md) |
| nginx re-resolution leaves one request hanging about 5 s after an api address change | **open** (deploy) | edge samples with a 5 s timeout (`0`) in b1, b2, b4; deploy record §3 |
| After the restart, with clients reconnecting immediately, recovery is complete but slow: b4 all stock sockets back at 209.5 s, realtime all ready at 193.0 s (b3: 120.6 s); the second and third probed tenants were first served at 64.6 / 74.9 s (b3) and 88.1 / 153.8 s (b4) against 2.5–4.2 s in b1 and b2, whose probe was stalled | **open**, not investigated | b3, b4 `restart.firstServedMs` |
| The api logs up to two `TENANT_COLD_BEYOND_BOUND` alerts per tenant per lifetime (5,550 in one second at 3,000, all from the api container): it runs two tenant-startup instances (`preview-api.js:115`, `postgres-domains.js:114`) | open, cause read-derived | r1 at 3,000 api log |
| Stored-count oracle has nothing to count without k6 writes (x2: oracle silent, its break-it control reports `CONTROL FAIL`) | open (harness) | x2 |
| PostgreSQL `max_connections` 100 is a deployment ceiling for pool sizing | open (deploy) | x3 sizing |

## Limitations

- **Busy, shared host.** Peer sessions' containers ran throughout. The quiet-host rule (1-minute load
  below 3 before each deploy) held at deploy for every run (`quiet.txt`); load1 during the load
  windows was 6.6–8.0 at 1,000 and 8.0–19.0 at 3,000 (mean of 2 s samples, table above), on 16 threads.
- **Load generators share the host.** k6 used 0.21–0.32 cores on average (peaks 5.9–7.8 cores) and the
  probe process 0.80–0.90 cores with 6,000 sockets (x2, x3; `load/loadgen.tsv`); earlier runs did not
  record them.
- **One run per variant** for b1–b4, r1 at 3,000 and x1–x3; three plus a control at 1,000 on 0392acf9.
- Probe changes during the campaign (asynchronous nginx restart, own health loop, disconnect timeline)
  apply from b3 onward; the restart-phase figures of earlier runs are comparable only after
  Correction 1.
- `cap.sh` was edited while r1 at 3,000 was running; the running shell logged one parse error
  (`deploy.log` line 4) after the probe ended; every artifact of that step is present.
- The x runs used 300 s idle and 600 s load windows.

## Files

`runs/<head>/<run>/`: `summary.json` (everything above), `deploy.json`, `startup.json`, host
labels (other projects' container names removed), `idle/` and `load/` tsv files (2 s samplers:
docker stats, host load, PostgreSQL activity and locks; per-role statement tables), `probe.json`,
`restart-startup.json`, oracle output, and role logs trimmed to the restart window (10 s before to
300 s after, per-tenant boot lines removed). Per head: `campaign.log`, `tables.md` (from
`aggregate.js`), `means.json`. Not kept: environment files, private state, tenant tokens, bootstrap
logs, k6 raw summaries.
