# compose-baseline: MT-BENCH-BASELINE harness

*Contributor-facing. Measures the one-host multitenant Compose reference (core `deploy/multitenant`)
at 1, 10, 50 and 200 synthetic tenants with one hot tenant, and records the numbers. It claims no
limits. Results: [`reports/tenancy/bench-baseline-2026-11-10/`](../../../reports/tenancy/bench-baseline-2026-11-10/README.md).*

## What it measures

| measurement | instrument | file in the run directory |
|---|---|---|
| p50/p95/p99 latency per client shape, failure rate, dropped iterations | k6 (`k6/workload.js`, `grafana/k6:1.3.0`) | `k6-summary.json`, `k6.log` |
| socket fanout: write sent to `dataUpdate` received, hot tenant and cold tenants | `probes/fanout.js` (socket.io-client from the core lockfile) | `fanout.json` |
| reconnect recovery after a realtime restart: stock client, then a retrying client | `probes/fanout.js` | `fanout.json` `recovery` |
| CPU and RSS per role, idle window and load window | `docker stats` every 2 s (`probes/sample.sh`) | `docker-stats.tsv` |
| PostgreSQL backend states, wait events, ungranted locks | `pg_stat_activity`, `pg_locks` every 2 s | `pg-activity.tsv`, `pg-locks.tsv` |
| statements and DB time per role; per-tenant window leases per second (evaluator and realtime cycle rate) | `pg_stat_statements`, reset per phase | `pg-by-role-<phase>.tsv`, `pg-ops-<phase>.tsv`, `pg-statements-<phase>.tsv` |
| disk per tenant-day | table growth over the run's rows (`oracle/disk.sh`) | `disk-before.txt`, `disk.txt` |
| stored-count oracle | superuser `psql` in the postgres container, no API (`oracle/oracle.sh`) | `oracle-stored.tsv`, `oracle.txt` |
| host label: CPU, cores, RAM, disk, Docker, load average, other containers | `bench.sh` | `host-before.txt`, `host-after.txt` |

`summarize.js` folds a run directory into `summary.json`.

### Client shapes (per tenant, per 5-minute CGM cycle)

| shape | request | per cycle |
|---|---|---|
| xDrip+/cgmsim uploader | `POST /api/v1/entries?token=` (1 sgv) | 1 |
| Loop/oref0 uploader | `POST /api/v1/devicestatus?token=` (Loop-shaped, 72 predictions) | 1 |
| AAPS-style uploader | `POST /api/v3/treatments`, Bearer JWT exchanged once | 1 |
| follower apps | `GET /api/v1/entries/sgv.json?count=1` | 5 |
| | `GET /api/v1/devicestatus.json?count=1`, `GET /api/v1/treatments.json?count=10`, `GET /api/v1/status.json` | 1 each |
| browser socket | Socket.IO polling, `authorize` with the exchanged JWT, as `lib/client/index.js:1165,1218` | probe |

`BENCH_ACCEL` compresses the cycle (1 = real cadence, 10 = one cycle per 30 s). The hot tenant
(index 0) carries `BENCH_HOT_FACTOR` (10) times every shape. The probe holds `SOCKETS_HOT` (20) sockets
on the hot tenant and one on each of up to `SOCKETS_COLD` (40) other tenants, opened 250 ms apart, and
posts one sgv every `PROBE_INTERVAL_MS`.

v1 `POST /api/v1/treatments` is not driven: the reference tenants do not enable `careportal`, so it
answers 401, as a single-tenant site without careportal does (`lib/api/treatments/index.js:287`).

## Requirements

- Docker Engine with Compose v2; `bc`, `node`, `openssl` on the host.
- A core checkout detached at the commit under test with its own `npm ci` (the probe loads
  `socket.io-client` from it), and an image built from it by `deploy/multitenant/build.js` with
  `NS_DEMO_IMAGE` set to the bench tag.
- The bootstrap overlay: `make-overlay.sh` takes core's `config.js`/`bootstrap.js` at that commit and
  applies the nightscout-deploy bench fixes (branch `bench/compose-baseline-20261110`). No serving image
  changes; only the one-shot bootstrap container reads the overlay.

```bash
export NS_BENCH_CORE=/path/to/crm-bench-checkout          # detached at the commit under test
export NS_BENCH_WORK=/path/outside/the/checkout/runs      # private: state, credentials, raw output
export NS_BENCH_IMAGE=nsbench-baseline:<short-sha>
export NS_BENCH_OVERLAY=/path/to/overlay
tools/mt-bench/compose-baseline/make-overlay.sh "$NS_BENCH_CORE" <core-commit> \
  /path/to/nightscout-deploy 085d88a <bench-fix-head> "$NS_BENCH_OVERLAY"
(cd "$NS_BENCH_CORE/deploy/multitenant" && node prepare.js --state /tmp/x && \
  echo NS_DEMO_IMAGE=$NS_BENCH_IMAGE >> .env && node build.js && rm -rf .env /tmp/x)
tools/mt-bench/compose-baseline/campaign.sh 1 10 50 200     # or bench.sh deploy|run|control|teardown N
```

Each tenant count is its own Compose project (`nsbench-n<N>`, port `18400+N` on 127.0.0.1) with
its own volumes; `teardown` removes the volumes and the private state and keeps the raw output.
`NS_BENCH_WORK` must be outside the core checkout (`prepare.js` refuses state inside it).

### Another base URL (Kubernetes binding)

`k6/workload.js` and `probes/fanout.js` take the base URL and a tenants file
(`[{id, host, token}]`, data tokens, private) and nothing else; Host selects the tenant. Against a
deployment the harness did not create:

```bash
docker run --rm --network host -v $PWD/tools/mt-bench/compose-baseline/k6:/scripts:ro -v $OUT:/out \
  -e BASE_URL=https://bench.example.test -e TENANTS_FILE=/out/tenants.private.json -e RUN_ID=bench-$(date +%s) \
  -e RUN_START=$(( $(date +%s) * 1000 - 86400000 )) -e DURATION=300 -e ACCEL=1 -e HOT_FACTOR=10 \
  grafana/k6:1.3.0 run --summary-export /out/k6-summary.json /scripts/workload.js
NODE_PATH=$NS_BENCH_CORE/node_modules SKIP_RECONNECT=1 node tools/mt-bench/compose-baseline/probes/fanout.js \
  --base https://bench.example.test --tenants $OUT/tenants.private.json --runid <same RUN_ID> --duration 300 --out $OUT/fanout.json
```

The oracle, the samplers and the realtime restart are Compose-specific (they `docker exec` into the
postgres container and `docker compose restart` realtime); a Kubernetes run needs its own operator
connection for `oracle/oracle.sh`'s SQL and its own restart command.

## Controls

- **Oracle:** `bench.sh control N` alters one stored row of the last run so it no longer carries the
  run marker, expects `ORACLE RED`, restores the row, expects `ORACLE GREEN` (`CONTROL PASS`).
- **Timestamp collisions:** every write gets a timestamp unique within the run (`RUN_START` plus the
  scenario iteration). With a per-VU origin the server's dedup merged colliding writes and the oracle
  went red (stored 57, accepted 60), which is how this was found.

## Traps

- Do not `CREATE EXTENSION pg_stat_statements` in the application database. Its functions are
  executable by PUBLIC, and the lifetime operation-window admission
  (`lib/tenant-lifecycle/operation-window-readiness.js:67-85`, `foreign_functions`) then refuses every
  evaluator and realtime cycle. The harness creates it in the `postgres` maintenance database.
- A raw legacy data token sent as the socket `token` is refused; the stock browser sends the exchanged
  JWT there. The probe does the same.
- Opening many sockets at once on one realtime process exhausts its PostgreSQL pools and the server
  disconnects them; socket.io-client does not reconnect after a server-initiated disconnect. The probe
  staggers opens; the reconnect phase measures the flood on purpose.
- Synthetic data only. The tenants file and the private state hold credentials and stay in
  `NS_BENCH_WORK`; `bench.sh run` deletes the tenants file when the run ends.
