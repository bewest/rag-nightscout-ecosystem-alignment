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

---

## Update 2026-11-11: BF-233, change-stamp function, incremental refresh, serve-then-warm

*Appended 2026-11-11 (UTC); the sections above are unchanged. Brief: BF-233 (filed from this lane's
finding), decisions [change-stamp-definer-function](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#change-stamp-definer-function),
[incremental-refresh](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#incremental-refresh) and
[readiness-serve-then-warm](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#readiness-serve-then-warm).
The coordinator then put the change-stamp function and incremental refresh **on hold** pending the
maintainer's answer on how the write clock should cover deletes; what was built before the hold is
committed and described below, and nothing further was added to those two after it, except where a
measured defect in already-committed code had to be fixed (marked).*

### Anchors

| tree | commit |
|---|---|
| lane `codex/perf-realtime-20261110`, worktree `externals/work/crm-perf-realtime-20261110`, unpushed | `20a49aabe7014726cc870e8fde76e1923add9d5a` |
| merged into the lane | `d6560468` (evaluator-partition head; **merge**, not rebase: `3390626a`), then `codex/perf-db-20261110` at `540d3998` (`cdbdf5ac`, for serve-then-warm) |
| scratch integration, measurement only, not for the join | `scratch/perf-realtime-int-20261111` (`12ff09e2` measured), worktree `externals/work/crm-perf-realtime-int-20261111` |
| images (removed afterwards) | `ns-prt-realtime:f62222cd`, `:650cfce3`, `:int-12ff09e2`, `:20a49aab` |
| alignment `main` when written | `25ca687fb` |

### Design (file:line at the lane head)

**BF-233.** `lib/server/realtime/socket-server.js` owns the Socket.IO server on the realtime listener. Shutdown is `io.close()` (namespaces, then `engine.close()`: every transport closes); `protocol.close` (`protocol.js`) no longer sends a server-side disconnect. socket.io-client then sees `transport close` and reconnects with its own backoff. No client change.

Mechanism of the 10 s overrun (reproduced, control A below): a server-side `disconnect(true)` on a polling socket leaves its engine connection and two timers waiting for a client that, having been told "io server disconnect", no longer polls. After `stop()` resolved (119 ms) the process still held 829 TCP sockets and 1,656 timers for 828 disconnected sockets, so it outlived the 10 s bound and the watchdog exited 1. `closeAllConnections` was tried and is not needed (control B).

**Change stamps (decision change-stamp-definer-function).**
- `lib/change-stamps/postgres-candidate.json`: operational catalogue (census `OPERATIONAL`, digest-pinned, `lib/tenant-operations/catalogues.js`), one migration creating `tenant_change_stamps(uuid[]) RETURNS TABLE (tenant_id uuid, last_stamp bigint)`, plpgsql, `SECURITY DEFINER`, `SET search_path = pg_catalog`, `SET app.current_tenant_id = ''`, `REVOKE ALL ... FROM PUBLIC`. The body binds each requested tenant through the same RLS setting the serving paths use and selects that tenant's clock row: RLS on the clock is unchanged and the owner needs no bypass. The function's own `SET app.current_tenant_id` keeps its binding from reaching the caller.
- Provisioning (`lib/change-stamps/postgres.js` `grants`, used by `deploy/multitenant/config.js`): `ALTER FUNCTION ... SET search_path = <clock schema>, pg_catalog`; `USAGE` and `EXECUTE` to the realtime and evaluator identities only; the catalogue ledger read to realtime only (its readiness checks the catalogue). `bootstrap.js` gives the function to the NOLOGIN catalogue owner, as every catalogue function (reviewed signature list).
- Reader (`lib/change-stamps/postgres.js` `create`): one statement per poll returns the stamps and the function's catalogue version (pg_proc row version plus the owner's login/superuser/bypass flags) — the same idea as perf-db's catalogue epoch, applied to the one object perf-db's epoch does not cover. An unadmitted version calls the function with no tenants, runs the attribute check (owner NOLOGIN, NOSUPERUSER, NOBYPASSRLS and owning the clock table; SECURITY DEFINER; plpgsql; exact body; exact result type; exact `proconfig`; no PUBLIC EXECUTE), then calls it with the tenants. A refused check raises `CHANGE_STAMPS_FUNCTION_UNSAFE`; detection then answers nothing and the runtime refreshes only failed cells.
- Realtime uses it when `postgres.namespaces.changeStamps` is set (the Compose plan sets it); a configuration without it keeps the per-tenant scan. The evaluator has EXECUTE and can adopt it; its configuration does not name the namespace yet.

**Incremental refresh (decision incremental-refresh).** `lib/storage/postgres-incremental-view.js`, shared read path:
- `create({ connection, domains, indexed, clockTable, reconcile, pageSize, maxRows })`; `refresh()` inside the tenant binding returns `{ mode: 'full' | 'incremental' | 'unchanged', changed, checkpoint, rows }`; `reset()` forces a full read.
- Cold start: the existing bounded `replay.reconcile` (checkpoint bookkeeping unchanged; it now also reports its physical row count and invalid keys from the same snapshot, `postgres-durable-replay.js`).
- Afterwards one REPEATABLE READ snapshot: clock floor; rows stamped in `(checkpoint, floor]` through the generated, indexed `"srvModified"` column (entries, treatments, devicestatus; an expression for profile, food, activity); a physical row count per tenant. Soft deletes (`isValid:false`) remove, everything else replaces.
- Full reconcile when the floor is below the checkpoint (rewind, restore), when more rows changed than the bound (gap), or when the count disagrees with the view (a hard delete — v1 entries remove, v3 prune or permanent delete — or a writer outside the clock leaves no stamp; durable event delivery contract §4).
- Hard deletes advance no clock, so nothing announces them: the runtime refreshes every tenant at least every `absenceCheckMs` (default 60000, set in the Compose plan; the single-site data reload cadence). With the floor unmoved that refresh is one count and returns the published frame unchanged (`projection.js`).
- The frame build's dbsize statistics (`sum(pg_column_size(doc))` over every row, `postgres-tenant-stats.js:19`) are read at most every 5 minutes per tenant.
- Frames stay full (`delta:false`).

**For the join with the evaluator lane (`a335be89`):** the evaluator's backstop reads, per tenant per pass, a signature of floor + row count + a digest over every row's identity and `xmin` (one statement per tenant, cost with stored rows). The shared shape is: `change-stamps` for the floor of every member tenant in one statement, then `postgres-incremental-view` per changed tenant (its count check covers hard deletes and unstamped writes), with an absence interval for tenants with no stamp movement.

**Serve, then warm (decision readiness-serve-then-warm, on perf-db's mechanism).** `NS_TENANT_READINESS`
(default `serve`) reaches realtime's startup cells (`preview-realtime.js`) and runtime (`runtime.js`).
In `serve` the role opens without awaiting tenants; each tick warms a bounded number of cold tenants
after the changed ones; a failed tenant is retried after 30 s while the others serve; `health().ready` is
the role's own, with `healthy` and `failed` counts. The stock client retries neither a handshake refusal
nor a server disconnect (`lib/client/index.js:1165` opens with default reconnection, which covers only
transport loss), so a socket for a cold tenant is **not refused**: it waits in the priming queue built
for pool pressure and gets its first frame when the tenant is warm. `all` restores the earlier
await-every-tenant boot.

**Two defects found by measurement in already-committed code, fixed:**
- *Absence checks stalled change detection at scale* (`addaa1ad`). At 1,000 tenants every tenant's 60 s
  absence check was due at once; one tick refreshed about three per second and the stamp poll ran only
  between ticks: 0.3 stamp calls per minute in the window (reproduced, `int-n1000-idle-s2`). Each tick now
  takes the changed, failed or woken tenants plus at most `ceil(N × interval / absenceCheckMs)` absence
  checks, oldest first.
- *Configuration re-parsed on every check* (`20a49aab`). One parse of the 1,000-tenant realtime
  configuration costs 85 ms (reproduced locally on the deployed file); it ran twice per refresh, once per
  fanout and once per tick, and the 143 KB admission file on every check. At 1,000 tenants realtime used
  70–73 s of CPU per minute with no sockets (more than its one thread) and primed 4 of 2,000 sockets
  (reproduced). Both files are still read on every call; they are parsed only when their text changes.
  This cost was in the base too (every refresh, every socket check).
- Also fixed on the way, each measured: the evaluator refused its boot because the grants gave it the
  change-stamp catalogue ledger outside its readiness screen (`f62222cd`); the 60 s absence check rebuilt
  every frame (`261f568e`); each frame build ran `sum(pg_column_size(doc))` over the tenant's rows for the
  dbsize display (`postgres-tenant-stats.js:19`), now at most every 5 minutes per tenant (`650cfce3`).

### The hard-delete gap (coordinator's question)

**Reproduced, and covered by the absence check, not by the stamp.** A hard delete (v1 entries `remove`,
`postgres-entries-write.js:177`) allocates no stamp, so `tenant_write_clock` does not move
(`postgres-write-clock.js` writes the floor only when a stamp was allocated).
- Stamp-only detection (this lane at `6f31c94b`, and the realtime runtime with no absence check) misses
  it: `RT_HARD_DELETE_STAMP_ONLY` (kept as a test) shows the deleted reading staying on display.
- With the absence check (count of physical rows against the view, `postgres-incremental-view.js`, at
  least every `absenceCheckMs` = 60 s): `RT_HARD_DELETE` passes (unit), `IV_HARD_DELETE` passes on
  PostgreSQL, and **end to end on the Compose reference** a v1 `DELETE` of a synthetic entry removed it
  from a stock-style socket's display after **79.8 s** at 100 tenants (stored count 0 after the delete;
  `rt2-n100-hard-delete.json`) and after **67.7 s** at 1,000 tenants (`rt2-n1000-hard-delete.json`; the write itself reached the display in 1.0 s).
- **Not covered:** an in-place edit of an unstamped activity row (no stamp, no count change). Only a full
  reconcile sees it; realtime runs one on cold start, a gap, a mismatch or a count difference.

### Checks

| check | result at `20a49aab` (unless stated) |
|---|---|
| `npm run test:unit` | 3267 passing, 0 failing (`044c08c2`; `20a49aab` adds one unit file, `realtime-config-cache`, 2 passing) |
| new: `realtime-socket-server` (actual Socket.IO, 50 stock clients), `realtime-readiness`, `realtime-config-cache`; `realtime-publish-on-change` now 13 | 1, 3, 2, 13 passing |
| PostgreSQL 16.15 (`ns-prt-pg`) and MongoDB 8.0.34 (`ns-prt-mongo`, `--ulimit nofile=64000`): `postgres-tenant-scan`, `change-stamps` (new, 9), `incremental-view` (new, 5), `tenant-activity`, `tenant-socket-data-forwarding`, `evaluator-consumers`, `tenant-alarm-state`, `tenant-durable-replay` | 45 passing, 0 failing (`044c08c2`) |
| tier check, `test:write-boundary`, `eslint lib` | ok (641 files); all 9 entry points; 0 errors, 56 warnings (54 at `cb1b751d`; the perf-db merge adds code) |

### Controls (each red with the symptom, then restored green)

| control | break | symptom |
|---|---|---|
| BF-233, unit (actual Socket.IO) | restore the server-side disconnect in `protocol.close` | `BF233_RECOVER 0/50 stock clients received a frame after the restart; reasons {"io server disconnect":50}` |
| BF-233, Compose (50 × 20, mounted variant) | restore the server-side disconnect | restart command 10.6 s, `still open 10000 ms after SIGTERM`; after `stop()` resolved (119 ms) 829 TCP sockets and 1,656 timers remained; stock clients **172/1000** back in 150 s, 828 told `io server disconnect` |
| BF-233, Compose | drop `closeAllConnections` (variant B) | none: restart 1.1 s, stock 1000/1000 in 62.7 s, so it was not needed and was removed (`a8ed874d`) |
| function: attribute check | check admits every version | 5 alteration cases `Missing expected rejection` (owner to a LOGIN role, search_path, EXECUTE to PUBLIC, SECURITY INVOKER, body replaced) |
| function: serving identity | (a property, no break) | api identity: `permission denied`; `has_function_privilege` api false, PUBLIC false |
| incremental view | ignore soft deletes | `IV_SOFT_DELETE reflected` |
| incremental view | skip the physical count | `IV_HARD_DELETE reflected without any write` |
| absence share | unbounded share (as before `addaa1ad`) | `RT_ABSENCE_SHARE write latency 596 ms with 200 tenants due for absence checks` |
| absence check | no absence checks | `RT_HARD_DELETE the deleted reading leaves every display` |
| readiness: one broken tenant | serve mode awaits every tenant | boot fails, `REPLAY_NOT_PROVISIONED` |
| readiness: cold socket | refuse a cold tenant's socket | `RD_COLD_SOCKET not refused or disconnected while cold` |
| readiness: flag | `all` ignored | `Missing expected rejection` |
| config parse | never re-parse / parse every call | `RT_PARSE_CHANGE …` / `RT_PARSE_ONCE one parse for fifty unchanged reads` |

A note on two controls during this round: two edits commented out the rest of a line and went red
for a syntax error, not for the property; each was redone (the table shows the redone symptom).

### Measurements (Compose reference; host load average in the run files, 9–20 during these runs)

**BF-233 gates (reproduced).**

| N × sockets | build | restart command | `still open` | stock clients back (no assistance) |
|---|---|---|---|---|
| 50 × 20 | base `cb1b751d` (first record) | 10.7 s | yes | 0/1000 (realtime exit 78) |
| 50 × 20 | `6f31c94b` (first record) | ~10.6 s | yes | 0/1000 in 30 s |
| 50 × 20 | `f62222cd` | 0.87 s; 0.74 s | no; `stop()` 124 ms, 49 ms | 1000/1000 within 180 s |
| 50 × 20 | `650cfce3` | 4.9 s | no | **1000/1000 in 42.8 s** |
| 100 × 2 | `650cfce3` | 4.9 s | no | **200/200 in 55.2 s** |
| 1000 × 2 | scratch `12ff09e2` (before the stall and parse fixes) | 10.8 s | — | 0/2000 in 300 s |
| 1000 × 2 | `20a49aab` | 0.89 s | no | **163/2000 in 300 s** (gate not met; 1,669 saw `transport close` and kept retrying) |

The stock client's recovery time is the realtime start plus priming; the restart command's 4.9 s at
`650cfce3` includes Docker's own stop and start.

**Change detection, statements and DB-ms per interval (reproduced).**

| N | build | stamp statements per minute | realtime DB-ms per minute (idle, with sockets) | of which window leases (absence checks) |
|---|---|---|---|---|
| 50 | `6f31c94b` (per-tenant scan, no absence check) | 2,761 scan statements (one round trip per second) | 83 | 0 |
| 50 | `650cfce3` (function) | 53.7 (one per second) | 1,815 | 1,421 |
| 100 | `650cfce3` | 58.8 | 2,294 | 1,783 |
| 1000 | scratch `12ff09e2` | 0.3 (stalled) | 1,115 | 896 |
| 1000 | `20a49aab` | 56.2 (one per second) | 10,451 | 6,979 (948 leases/min) |

The function itself: one statement per poll regardless of N; 26–39 ms wall for 1,000 tenants in the lab
(`CS_SCALE`). The absence check costs one operation-window lease per tenant per minute (about 29 ms of
lifetime-role time each on the lane before perf-db's epoch; about 7.4 ms at `20a49aab` with it).

**Refresh cost against stored data (lab, entries, reproduced).** Full reconcile 11 / 33 / 433 ms at 100 /
1,000 / 10,000 stored rows; incremental refresh with one changed row 3.1 / 3.2 / 10.6 ms (2.7 / 3.0 / 9.0
after VACUUM). The remaining growth is the physical count and the in-process copy of the view.

**At 1,000 tenants (reproduced).**

| figure | scratch `12ff09e2` | `20a49aab` |
|---|---|---|
| realtime start to ready | 257.8 s (await every tenant) | 92.4 s (serve; 1,000/1,000 warm by the first measurement) |
| realtime CPU per minute, no sockets | 72.6 s | 15.6 s |
| sockets primed (2 per tenant, opened at once) | 4 / 2000 | 2000 / 2000 in 42 s |
| realtime CPU per minute, 2000 idle sockets | 70.7 s | 30.7 s |
| resident MB, no sockets / with sockets | 1,295 / 1,297 | 231 / 384 |
| frames per idle socket per minute | — | 0.05 (300 frames in 3 min, no writes; authorization rechecks 0.38 per socket per minute against 1.0 expected: read-derived, rechecks the busy api could not answer hold a socket and resend one frame when they succeed) |
| stamp statements per minute | 0.3 | 56.2 |
| write to frame / hard delete to removal (end to end, one tenant) | — | 1.0 s / 67.7 s |

### Per-tenant marginal costs, updated (derived from the rows above)

| figure (`20a49aab`, 1,000 tenants unless stated) | value | basis |
|---|---|---|
| realtime CPU-ms per tenant-minute, idle, no sockets | about 13 (15.6 s/min at 1,000 minus the ≈3 s process floor) — almost all of it the 60 s absence check | derived from reproduced |
| CPU-ms per socket-minute, idle | about 7.6 ((30.7 − 15.6) s / 2000) | derived |
| resident MB per tenant, no sockets | about 0.2 (231 MB at 1,000; the earlier 1.4 MB/tenant estimate included configuration-parse garbage now gone) | derived |
| resident MB per connected socket | about 0.08 ((384 − 231) / 2000) | derived |
| realtime DB-ms per tenant-minute, idle | about 10.5 (10,451 / 1,000): 7.0 window lease + 3.5 count and floor, all from the absence check; the stamp function is one statement per second for all tenants | derived from reproduced |
| frames per socket-minute | 0 idle by design (0.05 measured, see above); 0.2 at one write per 5 minutes (50 × 20) | reproduced |
| authorization calls per socket-minute | 2 / sockets sharing a credential (0.074 at 20, 0.99 at 2; 0.38 at 1,000 × 2 where rechecks failed) | reproduced |

**What runs out first (derived, one realtime process).** The single Node thread: 15.6 s/min at 1,000
tenants with no sockets and 30.7 s/min with 2,000 idle sockets, so about **1,900 tenants at 2 sockets
each** (≈ 3,800 with none) before one core is spent. Most of the idle cost is the 60 s absence check
(one lease, one count, one refresh per tenant per minute); if the maintainer's answer makes hard deletes
advance the clock, the absence check can go and the idle per-tenant cost falls to the stamp function's
share. Memory (≈0.2 MB per tenant, 0.08 MB per socket) and realtime's own DB time (≈10 ms per
tenant-minute idle) are not the first limits at these sizes. Restart recovery at 1,000 is the open gate:
163/2000 stock clients back in 300 s.

### Decisions and questions for the join

- The change-stamp function and incremental refresh are on hold per the coordinator. If the maintainer
  makes deletes advance the clock, the absence check (and its per-tenant lease every minute) can go; the
  count check in the view stays as a guard.
- The evaluator lane's per-tenant signature (floor + row count + digest over every row's identity and
  `xmin`, `a335be89`) and this lane's function + view are two answers to one question; the shared shape
  proposed is: the function for every member tenant's floor in one statement, the view per changed
  tenant, an absence interval for unmoved tenants.
- `closeAllConnections` is not needed (control B); the shutdown fix is the removed server-side disconnect.
- perf-db overlap is merged in the lane (`cdbdf5ac`); the scratch branch is for measurement only.

### UNMEASURED (this round)

- **Restart recovery at 1,000 tenants: gate not met (163/2000 in 300 s).** Mechanism read-derived, not
  instrumented: after a restart every tenant is cold, and each reconnecting socket's priming batch
  warms its own tenant directly (no bound across tenants), competing with the bounded background warm;
  batches back off and retry. Candidate: a cold tenant's socket waits for the runtime's bounded warm
  (`wake` to the front) instead of warming itself.
- The run files of the `f62222cd` deployment (first stock-recovery runs, BF-233 controls A and B) were
  deleted by mistake before the next campaign; their figures above are quoted from tool output at
  capture time.

- Revocation, expiry, pause and suspend on the Compose reference (unit only, as before).
- Write-to-frame at 1,000 tenants with writes (idle and the hard delete only).
- Memory per socket at 1,000 tenants beyond the one idle run.
- The cost of the absence check with realistic stored data (synthetic tenants hold few rows).

## Update 2026-11-11 (round 3): restart recovery at 1,000 tenants, idle frames

Lane head `dc8d10bc` (`codex/perf-realtime-20261110`, not pushed). Commits this round: `721b5daf`
(protocol counters), `65b9fc7a` (cold-tenant sockets park for the runtime's bounded warm), `9b6ff088`
(bounded recheck, resend only a missed frame), `dc8d10bc` (parked drain outside the runtime's
operation; sockets wait for the runtime's next cycle). Compose reference as above, 1,000 tenants × 2
stock sockets, `--open flood`; a diagnostic mount (`preview-realtime.js` logging protocol and runtime
counters every 5 s) on every run. Host load averages are in each `*-campaign.txt`; a peer bench
campaign shared the host during the `dc8d10bc` runs (load 6.7 to 23).

### Idle frames at 1,000 tenants: recheck resends (reproduced), fixed

| image | idle window | frames | resends | authorizeInFlightMax | recheckFailures |
|---|---|---|---|---|---|
| `721b5daf` (before) | 180 s | 236 | 236 | 1000 | 420 → 1968 |
| `9b6ff088` | 180 s | 0 | 0 | | |
| `dc8d10bc` | 180 s | 0 | 0 | | |

Mechanism: the periodic recheck started every tenant at once, so 1,000 authorizations were in flight;
the failures held sockets, and the end of each hold resent the frame whether or not it had changed.
Fix (`9b6ff088`): the sweep rechecks 8 tenants at a time, and a hold ends with a frame only if fan-out
skipped a changed view during the hold, or display or permissions changed. Unit controls: resend
always, `RT_RESEND_NONE no frame for an unchanged view after the hold`; unbounded sweep,
`RT_RECHECK_BOUNDED 40 authorizations in flight for 40 tenants`. Runs:
`runs/rt3-n1000-721b5daf-idle-s2.json`, `runs/rt4-n1000-9b6ff088-idle-s2.json`,
`runs/rt4-n1000-dc8d10bc-idle-s2.json`; counters in the matching `*-diag.txt`.

### Restart recovery at 1,000 tenants (BF-233 at scale)

| image | what it does | restartCommandMs | stock clients recovered | all recovered |
|---|---|---|---|---|
| `721b5daf` | each socket warms its own tenant | 1769 | 2000/2000 | 94.2 s |
| `9b6ff088` | sockets park; drain started inside the runtime's operation | 682 | 76/2000 | not within 300 s |
| `dc8d10bc` | parked drain detached; sockets wait for the runtime's cycle | 1041 | 2000/2000 | 129.7 s |
| `dc8d10bc` + control mount | unbounded per-socket warm (no parking, socket refreshes) | 10553 | 2000/2000 | 103.1 s |

Gate: stock clients N/N at 1000 × 2 within 300 s. **Met on `dc8d10bc`** (129.7 s).

Cause on the old path (`721b5daf`, reproduced with counters): after the restart every reconnecting
socket ran its own tenant warm, outside the runtime's bound, and every retry re-authorized. At +30 s:
healthy 19, socket warms 851 (648 failed), retries 4139, authorizations 6059, runtime ticks 1. At
+60 s: healthy 496, socket warms 3635 (2847 failed), retries 6338, authorizations 8765, runtime
ticks 2. The 163/2000 of the previous round ran at host load 21 to 24; this run recovered on a quieter
host.

Cause of the `9b6ff088` failure (reproduced): the runtime calls `onReady` from inside its refresh
cycle, which runs inside the operation window's async scope. `tenantReady` started the parked drain
there, so the drain and every retry timer it scheduled inherited that scope; after the cycle ended,
every prime was refused with `LIFECYCLE_WINDOW_SCOPE_INVALID` (`operation-window.js:139`, via
`withOperation`). Counters 5 min after the restart: all 1,000
tenants healthy, socket refreshes 66611 with 66569 failures, primed 76. The unit gate passed on
`9b6ff088` because its lab had no operation window.

Fix (`dc8d10bc`):

- The drain runs in the protocol's own async context (`AsyncResource.bind` at create).
- A socket for a warm tenant never refreshes the tenant itself: `runtime.fresh(tenant)` wakes the
  tenant into the tick's bounded share, and the socket takes the first cycle that starts after it
  asked (freshness at connect, `RT_HARD_DELETE*`, kept). All sockets of a tenant share that cycle.
  Sockets released by the runtime's warm take the projection that warm published. A cycle published
  while sockets primed is sent to them afterwards.
- A failed tenant with sockets waiting backs off from the tick interval up to `failureRetryMs`;
  without this, a pool refusal of the runtime's own fan-out darkened the tenant for 30 s
  (`RT_PRESSURE_ALL_PRIMED 0/50`). A failed tenant nobody waits for keeps the full interval
  (`RD_ONE_BROKEN`).

Unit gate `RD_RESTART_BOUNDED` now runs under an operation window with the window's scope rule:
100 cold tenants × 2 sockets all prime, concurrent acquires ≤ 2 (runtime concurrency), parked ≥ 1.
Controls, each red then restored green: unbounded per-socket warm,
`RD_RESTART_BOUND concurrent warms 100 (runtime concurrency 2)`; drain not detached,
`RD_RESTART_ALL_PRIMED 0/200`.

**Compose control: an unbounded per-socket warm does not fail the gate at this size** (2000/2000 in
103.1 s, host load about 19). Its symptoms are those of the old path: socket refreshes 4836 with
4153 failures and runtime ticks 2 at about +60 s after the restart (`dc8d10bc`: socket refreshes
266, 0 failures, ticks 14), and a 10.6 s restart command. The bounded design recovers more slowly
here (129.7 s against 103.1 s, under different host loads) because warm-up proceeds at the runtime's
concurrency share per tick; the gate as stated does not discriminate between the two at 1,000
tenants on this host. The unit bound is the discriminating check. Counters:
`runs/rt4-n1000-dc8d10bc-diag.txt`, `runs/rt5-n1000-dc8d10bc-control-unbounded-diag.txt`.

### Checks on `dc8d10bc`

- `realtime-*`, `tenant-startup-admission`, `tenant-operation-window`, `human-session-stream`,
  `tenant-activity` at the project timeout (`--timeout 5000`): 157 passing, 0 failing.
  `realtime-browser-diagnostics` fails only at mocha's 2,000 ms default, identically on `cb1b751d`,
  `16a1fc2d` and `dc8d10bc`; it passes at 5,000 ms on all three.
- eslint: 0 errors (2 existing `detect-non-literal-fs-filename` warnings on the configuration file
  read).

### UNMEASURED (round 3)

- Restart recovery under a tighter bound or at 3,000 tenants; whether a larger warm share during a
  restart closes the gap to the unbounded control without its socket-path failures.
- The write clock (perf-db `03661f22`) is not yet merged in this lane; the absence check is still on.
- The realtime logs of the two `9b6ff088` restart runs (counters and the `LIFECYCLE_WINDOW_SCOPE_INVALID`
  lines) were overwritten when a later deploy reused their run directories; the figures above for
  those runs are quoted from tool output at capture time. Their run files (`*-restart-s2.json`,
  `*-campaign.txt`) are kept.
