# Realtime publishes on change (perf lane RT), 2026-11-10

*Contributor-facing evidence record for perf lane RT (multitenant only). Captured 2026-11-10/11 (UTC); not
edited after capture. Decisions read: [cost-proportional-to-activity](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#cost-proportional-to-activity),
[activity-is-pause-suspend](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#activity-is-pause-suspend),
[suspended-refusal-423](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#suspended-refusal-423),
[tenant-devicestatus-status-parity](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#tenant-devicestatus-status-parity),
D6 and the [durable event delivery contract](../../../docs/30-design/tenancy/durable-event-delivery-contract-2026-11-06.md);
[m7-capacity-gate](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#m7-capacity-gate) for the marginal-cost section.
Synthetic data only. Every figure is labelled **reproduced** (read from a run file here) or **derived**
(arithmetic on reproduced figures, stated).*

## Outcome

Realtime sends a frame only when a tenant's view changes, authorizes a socket when it connects and
then only on events, primes concurrent connects late instead of disconnecting them, and comes back
after a restart at 50 and 100 tenants. No client change: `lib/client` is untouched, frames stay full
(`delta:false`). Measured on the one-host Compose reference against the base head:

| | base `cb1b751d` | this lane `6f31c94b` |
|---|---|---|
| frames per idle connected socket per minute (1 tenant × 20) | 20.0 | **0** |
| subject authorizations per connected socket per minute (1 × 20) | 20.1 | **0.099** |
| realtime DB-ms per minute, 50 tenants × 20 sockets idle | 44,989 | **83** |
| sockets primed when 1000 open (50 × 20) | 14 / 1000 at 50 ms stagger (986 server-disconnected) | **1000 / 1000 opened at once**, none disconnected |
| realtime after `docker compose restart realtime`, 50 tenants | exit 78, never back | **running**; reconnecting clients 1000/1000 in 32.8 s |
| realtime start at 100 tenants | exit 78 at deploy | **running**; restart survived, 200/200 back in 35.1 s |

**Restart root cause (reproduced):** at boot realtime warms and refreshes every configured tenant at
once, each inside an operation window that takes a client from the lifetime pool (max 8, 5 s connect
timeout, `operation-cohort-config.js:49`). On a loaded PostgreSQL one window waits longer than 5 s,
pg-pool rejects with `timeout exceeded when trying to connect` at `operation-window.js:103`, the
startup `Promise.allSettled` treats any rejection as fatal (`runtime.js:43-45` and `tenant-startup.js`
warm, both at `cb1b751d`), and `preview-realtime.js` turns it into `PreviewConfigError` → exit 78. Shown with a diagnostic
copy of `preview-realtime.js` that prints the swallowed error ([`runs/base-n50-restart-diagnostic.txt`](runs/base-n50-restart-diagnostic.txt)).
It is not caused by the previous process: a fresh `up` of the stopped container failed the same way.
The perf-db lane reproduced the same mechanism independently with unbounded warm at 200
([perf-db record](../perf-db-2026-11-10/README.md)).

**Not fixed here, measured in both heads:** graceful shutdown with sockets attached overruns the
10 s bound (`still open 10000 ms after SIGTERM: PipeWrap, PipeWrap, Timeout, …`, then the watchdog
exits 1; [`runs/base-n50-realtime-lifecycle.txt`](runs/base-n50-realtime-lifecycle.txt),
[`runs/after-n50-realtime-lifecycle.txt`](runs/after-n50-realtime-lifecycle.txt)). Without sockets the
base restarted in 5 s with no overrun. The mechanism was not examined.

## Anchors

| tree | commit |
|---|---|
| base: `codex/evaluator-partition-20261110` (clone `externals/cgm-remote-monitor-official`) | `cb1b751d4e3875b9b9c250b1a3b6236f7c926aa4` |
| lane branch `codex/perf-realtime-20261110`, worktree `externals/work/crm-perf-realtime-20261110`, local, unpushed | `6f31c94b0d8574c9796113fbd01765f5b5566a2b` (`6a64b75e` change, `6f31c94b` test strengthening) |
| base measurement worktree (detached) | `externals/work/crm-perf-realtime-base-20261110` at `cb1b751d` |
| images (built by `deploy/multitenant/build.js`, revision label checked, removed afterwards) | `ns-prt-realtime:cb1b751d`, `ns-prt-realtime:6f31c94b` |
| bench overlay | `tools/mt-bench/compose-baseline/make-overlay.sh` (core config at the commit + nightscout-deploy `085d88a..4e5a1051`), `maxSockets` raised to 25000 for 20 sockets per tenant |
| harness | [`tools/mt-bench/realtime-perf/`](../../../tools/mt-bench/realtime-perf/) (`run.sh`, `measure.js`); projects `ns-prt-<label>-n<N>` |
| alignment `main` when written | `23b8ada56` |

## Design (file:line at `6f31c94b`)

| piece | where | what |
|---|---|---|
| change hints in one round trip | `lib/storage/postgres-connection.js:232` `scanTenants` | One READ ONLY transaction per 500 tenants: for each tenant `set_config('app.current_tenant_id', …)` then one fixed parameterless SELECT, so forced RLS scopes each statement to its tenant. No operation-window lease; nothing read is served. Refuses `;`, `$`, `\`, non-SELECT, duplicate or non-UUID tenants. |
| detector | `lib/server/realtime/change-detector.js:19` `stampReader`, `:25` `create`, `:47` `invalidateIneligible` | Per interval: every tenant's `tenant_write_clock.last_stamp` (one scan), activity (`tenant-activity/postgres.js:94` `readMany`, one scan), configuration identities (`realtime/config.js:43` `readAll`, one file read). A tenant removed from admission or not eligible to be read (paused, suspended, unprovisioned, unreadable) has its sockets disconnected. |
| runtime | `lib/server/realtime/runtime.js:54` `due`, `:63` `tick`, `:93` `wake` | Refreshes a tenant only if its stamp differs from the checkpoint of its last published refresh (the clock floor read in the refresh's own snapshot), its configuration identity changed, its last refresh failed, or it was woken. At most two refreshes at a time (`preview-realtime.js:11`); startup bounded the same way (`:88`, `preview-realtime.js:80`). `wake(tenant)` is the seam for a later NOTIFY / slot reader. |
| publish on change | `lib/server/realtime/protocol.js:52` `sameView`, `:359` `fanout` | A main socket gets a frame only when its view (frame minus `lastUpdated`, plus configuration identity) differs from what it last received. `/storage` gets only row changes. Frames stay `delta:false`. Fanout uses each socket's remembered rights: no per-frame api call. |
| authorization by event | `protocol.js:130` `remember`, `:60` `expiryOf`, `:268` `recheck`, `:295` `sweep`, `:413` `recheckTenant` | At connect/re-authorize: one api call. Afterwards: at the credential's JWT `exp` (a recheck the api answers; all stock carriers are JWTs with `exp`), every `authorizationRecheckMs` (optional config, default 30000, set explicitly in `deploy/multitenant/config.js`), on `recheckTenant` (revocation-event seam), and on pause/suspend/admission removal (detector) or lifecycle invalidation. One api call per distinct (namespace, host, credential) per tenant per recheck (`:111` `authorities`). A refusal disconnects; an api that cannot answer holds that socket's frames until it can. Alarm delivery and `loadRetro` still authorize per request. |
| late, not dropped | `protocol.js:160` `queue`, `:171` `later`, `:204` `prime` | Connects are queued per tenant and primed in batches: authorization outside the window (one call per distinct credential), then one operation window for the refresh and every send. Pool pressure or an unanswering api retries the batch with jittered backoff (250 ms → 5 s); only refusals (`:21` `REFUSALS`, window suspension) disconnect. |
| shutdown | `protocol.js:429` `close` | Unchanged: every socket is disconnected server-side. |

**D6 mismatch, stated:** the decision asks for "one aggregate query per member per interval". Every
clinical and clock table is `FORCE ROW LEVEL SECURITY` and the realtime identity is NOBYPASSRLS
(`evaluator-readiness.js:15-19` refuses otherwise), so a single cross-tenant SELECT is not possible
without a schema change (a security-definer function or a summary table outside RLS). `scanTenants`
is one round trip and one transaction per member per interval, with one statement per tenant. A true
aggregate statement is a schema decision for the batch join.

**Shared with the evaluator lane:** `stampReader` is the evaluator's per-member change query too
(`stamps(tenants) → Map<tenant, last_stamp>`; the evaluator compares with its own checkpoint), and
`readMany` is its activity work list in one round trip. The peer branch `codex/perf-evaluator-20261110`
had no commits when this lane started, so nothing was reconciled yet.

**Overlap with perf-db (`codex/perf-db-20261110`, `d53f12d6`, `a52bc33b`):** both lanes bound startup
warm (`tenant-startup.js` warm). perf-db reads `NS_TENANT_STARTUP_CONCURRENCY` (default 4) for warm and
realtime's first refresh and makes pool sizes configurable; this lane hard-codes 2 for warm, startup
and change ticks. At the join take perf-db's setting for startup and derive the tick concurrency from
`NS_POOL_REALTIME_MAX`. The new [readiness-serve-then-warm](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#readiness-serve-then-warm)
decision (recorded after this lane started) is not implemented for realtime here: realtime still
refuses the boot if any tenant's startup fails, and `/health` stays 503 until all are ready.

## Checks

| check | result |
|---|---|
| `npm run test:unit` | 3229 passing, 0 failing (`6f31c94b`) |
| `tests/realtime-publish-on-change.test.js` (new, unit tier) | 10 passing |
| `tests/realtime-preview.test.js`, `tests/realtime-storage-proof.test.js`, `tests/tenant-activity.test.js` | 24, 5, 16 passing |
| `tests/postgres-tenant-scan.integration.test.js` (new) and `tests/tenant-activity.integration.test.js` (+1 case: `readMany`), PostgreSQL 16.15 container `ns-prt-pg` | 3 and 8 passing |
| `tests/tenant-socket-data-forwarding.integration.test.js` (PostgreSQL + MongoDB 8.0.34 container `ns-prt-mongo`) | 4 passing |
| `tests/evaluator-consumers.integration.test.js`, `tests/tenant-alarm-state.integration.test.js` | 20 passing together with the two above, 4 pending (opt-in not selected) |
| browser tier `socket-client.test.js`, `server-alarms.test.js` (no multitenant realtime case exists in the browser tier) | 7 passing |
| headless socket tests | none target multitenant realtime; the unit tier's socket suites pass |
| tier check, `test:write-boundary`, `eslint lib` | ok; all 9 entry points; 0 errors, 54 warnings (base: 54) |

Four existing assertions encoded the replaced model (fanout re-authorizing every socket every
second, or a frame every second). Each now drives the same security property through the recheck:
`realtime-preview` "fanout stops after revocation" and the `/` epoch fence call `recheckTenant`;
`realtime-storage-proof` narrows collections by `recheckTenant` before fanout; `tenant-activity` gives
B a write so its frame is a changed view.

### Break-it controls (each red with the symptom shown, then restored green)

| control | break | symptom |
|---|---|---|
| no change → no frame | `due()` returns true | `RT_IDLE_NO_ACQUISITION no projection read while the stamp is unchanged` |
| unchanged view sends nothing | `sameView` returns false | `RT_SAME_VIEW a stamp move with an unchanged view sends nothing` |
| a write → frame within the bound | `due()` ignores the stamp | `every A socket receives the new frame` (false after 1 s) |
| revocation → disconnect within the bound | recheck skips invalidation | `RT_REVOCATION_NO_DATA no frame after one recheck interval` — `2 !== 1`: the revoked socket kept receiving |
| expiry | expiry timer not scheduled | `disconnected at expiry` (false after 2.5 s) |
| pause and suspend | detector invalidation removed | both cases: socket not disconnected within 1 s |
| one api call per credential | dedupe off | `one call per sweep for 20 sockets sharing a credential: 60` |
| 50 simultaneous connects all prime | disconnect-on-exhaustion restored | `RT_PRESSURE_ALL_PRIMED 0/50` |
| scan binds each tenant | `set_config` replaced by `SELECT 1` | `returns each tenant its own rows only` deep-equal failure (RLS returned no rows) |

The first pressure version was vacuous (the control stayed green: batching meant the fake pool
never saw two windows at once); the fake pool is now exhausted by other holders for 150 ms
(`6f31c94b`), and the control goes red as above.

### Bounds (stated, then measured)

| event | stated bound | measured |
|---|---|---|
| a write → frame | one detection interval (`recoveryIntervalMs`, 1000 in the reference) + one refresh | unit: ≤ 90 ms at a 50 ms interval; Compose: p50 1,248 ms (1 tenant), 1,674 ms (10), 1,539 ms (50, host load ≈ 18; p95 6,178, p99 14,713) — **reproduced** |
| revocation | `authorizationRecheckMs` (30 s) + one api call; `recheckTenant` now | unit: ≤ 160 ms at a 100 ms interval — **reproduced** (Compose: not measured) |
| token expiry | `exp` + one api call | unit: < 200 ms after `exp` — **reproduced** |
| pause, suspend, admission removal | one detection interval | unit: ≤ 90 ms at a 50 ms interval; activity is not configured for realtime in the Compose reference, so no Compose figure — **reproduced (unit only)** |
| single-site reference | — | legacy sockets in `DataReceivers` are never rechecked after `authorize` (`lib/server/websocket.js:122,207-232`); human sockets are rechecked per emit (`:123-126`) — read-derived |

## Measurements (Compose reference, host 16 cores / 64 GB, other lanes running; load average in each run file)

All windows: sockets opened, primed, 5 s settle, `pg_stat_statements` reset, then 120 s idle (or
300 s with one write per tenant spread evenly); CPU from the container's cgroup `cpu.stat`, memory
from cgroup `memory.stat` `anon`. "Subject authorizations" count the api's subject-snapshot statement,
one per socket authorization of the exchanged JWT. Per-socket figures divide by sockets that were
connected and primed.

### Before and after

| N × sockets | head | primed | frames / socket / min | subject auth / socket / min | realtime DB-ms / min | api DB-ms / min | realtime window leases / min | file |
|---|---|---|---|---|---|---|---|---|
| 1 × 20 | base | 20/20 (250 ms stagger) | 20.0 | 20.1 | 1,307 | 9,433 | 20.3 | `base-n1-idle-s20` |
| 1 × 20 | lane | 20/20 (flood) | 0 | 0.099 | 8 | 200 | 0 | `after-n1-idle-s20` |
| 10 × 20 | base | 41/200 (250 ms stagger) | 16.6 | 16.8 | 38,409 | 27,429 | 413 | `base-n10-idle-s20` |
| 10 × 20 | lane | 200/200 (flood) | 0 | 0.099 | 21 | 2,737 | 0 | `after-n10-idle-s20` |
| 50 × 20 | base | 14/1000 (50 ms stagger) | 6.2 | 6.2 | 44,989 | 4,435 | 415 | `base-n50-idle-s20` |
| 50 × 20 | lane | 1000/1000 (flood) | 0 | 0.074 | 83 | 6,770 | 0 | `after-n50-idle-s20` |
| 100 × 2 | lane | 200/200 (flood) | 0 | 0.99 | 425 | 9,430 | 0 | `after-n100-idle-s2` |

Base per-socket rates are over the primed sockets (base 10 and 50 per-socket values derived:
reported per opened socket × opened / primed). Lane authorization rate is two rechecks per minute per
distinct credential divided by the sockets sharing it (0.1 at 20 per credential, 1.0 at 2).

With one write per tenant every 5 minutes (lane): frames per socket per minute 0.199 (1 and 10
tenants), 0.222 (50; frame count includes 116 more frames than writes × sockets: resends after held
rechecks or reconnects, not separated); all frames delivered at 1 and 10 tenants (20/20, 200/200),
960/1000 by window close at 50 (the last writes were sent within seconds of the close).

### Restart recovery

| N | head | after `docker compose restart realtime` | stock clients (no reconnect after server disconnect) | reconnecting clients |
|---|---|---|---|---|
| 50 | base | **exit 78** | 0/1000 | 0/1000 (nothing to connect to) |
| 50 | lane | running | 0/1000 | 1000/1000 in 32.8 s (flood) |
| 100 | base | **exit 78 at deploy** | — | — |
| 100 | lane | running | 0/200 | 200/200 in 35.1 s |

What the client does on restart (reproduced, both heads): shutdown disconnects every socket
server-side, socket.io-client reports `io server disconnect` and does not reconnect, so the stock
browser stays dark until reloaded. Unchanged by this lane, as required.

## Per-tenant marginal costs for realtime (capacity gate)

| figure | value | basis |
|---|---|---|
| CPU-ms per tenant-minute, idle, no sockets | not resolved above the process floor: 2,995 (1 tenant), 3,671 (10), 2,931 (100) ms/min for the whole process. Largest slope seen 75 ms/tenant-min (1→10), none 10→100 | reproduced points; slope derived |
| CPU-ms per socket-minute, idle | 3.6 (10 × 20: (4,396 − 3,671)/200), 10 (50 × 20: (13,102 − ≈3,000)/1000), 18.5 (100 × 2: (6,624 − 2,931)/200; one recheck call per 2 sockets) | derived from reproduced windows |
| CPU-ms per tenant-minute, one write / 5 min | not separable at 1 and 10 tenants (4,436 vs 4,396 ms/min at 10 × 20) | reproduced |
| resident MB per tenant, no sockets | ≈ 1.4 (anon 66 / 99 / 202 MB at 1 / 10 / 100 tenants) | points reproduced; slope derived; includes uncollected garbage |
| resident MB per connected socket | 0.36 (50 × 20), 0.44 (10 × 20), 0.79 (100 × 2) | derived from reproduced before/after-open anon |
| realtime DB-ms per tenant-minute, idle | ≈ 1.8 (8 / 19 / 178 ms/min at 1 / 10 / 100 tenants, no sockets) | points reproduced; slope derived |
| realtime DB-ms per tenant-minute, one write / 5 min | 30 (1), 37 (10), 45 (50) | derived: (write-window − idle) / N; ≈ 185 ms per write-triggered refresh |
| frames per socket per minute | 0 idle; 0.2 at one write / 5 min | reproduced |
| authorization calls per socket per minute | 2 / (sockets per credential): 0.074–0.099 at 20 per credential, 0.99 at 2 | reproduced |
| 1,000 tenants idle with a few sockets | **UNMEASURED**: the api exits 78 at boot before realtime starts (operation-window pool connect timeout at `operation-window.js:103`, [`runs/after-n1000-api-diagnostic.txt`](runs/after-n1000-api-diagnostic.txt)). Bounding the api warm to 2 did not change it (tried in a commit since removed from the branch); the remaining all-tenant step was not found. perf-db reports 1,000 tenants starting with its serve-then-warm api change. | reproduced symptom |

**What runs out first (derived, for one realtime process):**

1. **Refresh throughput.** Change ticks refresh at most two tenants at once and a refresh takes
   roughly 0.7–1.2 s of wall time (write-to-frame p50 1.2–1.7 s minus about half a detection
   interval), so about 100–170 refreshes per minute: **about 500–850 tenants at one write per
   5 minutes**, fewer with several uploaders per tenant. Each refresh is a full current-state
   reconcile (`postgres-durable-replay.js` reconcile scans every row), so it grows with each tenant's
   stored data; the synthetic tenants here hold little. Raising the concurrency (pool 4, configurable
   in perf-db) or an incremental catch-up refresh moves this.
2. **The single Node thread.** Idle sockets cost 3.6–18.5 CPU-ms per socket-minute, and one thread
   gives 60,000 ms per minute: roughly **3,000–4,500 idle sockets** per process (1,000 to 1,500
   tenants at 3 sockets each), less with writes (50 × 20 with writes: 17,957 ms/min).
3. **Memory.** About 1.4 MB per tenant and 0.4–0.8 MB per socket: 3,000 tenants with 3 sockets each
   ≈ 4 GB + 4–7 GB per process.
4. Realtime's own database time is not a limit at these sizes: about 1.8 ms per tenant-minute idle,
   about 40 ms with one write per 5 minutes (≈ 2 cores of PostgreSQL at 3,000 tenants).

Sharding realtime across processes (`MT-REALTIME-SHARDING`) addresses 2 and 3; 1 is per process too.

## UNMEASURED

- Everything at 1,000 tenants (api boot refusal above).
- Revocation, expiry, pause and suspend bounds on the Compose reference (unit only; the reference does
  not configure activity for realtime, and no revocation driver was run).
- Write-to-frame on a quiet host at 50 tenants (load average ≈ 18 from other lanes).
- Cost per write with realistic stored data (synthetic tenants hold few rows).
- The shutdown overrun's mechanism.
- Lane head on a joined batch with perf-db and the evaluator lane.

## What is local and unpushed

Branch `codex/perf-realtime-20261110` (`6f31c94b`) in worktree `externals/work/crm-perf-realtime-20261110`;
detached base worktree `externals/work/crm-perf-realtime-base-20261110`. Containers `ns-prt-*` and both
`ns-prt-realtime:*` images removed after the runs. Private run state (tenant tokens, logs) stayed in
the session scratch directory.
