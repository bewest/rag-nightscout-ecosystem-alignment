# MT-PERF-DB: cheap restore-fence admission, bounded startup warm, configurable pools (2026-11-10)

*Contributor-facing measurement record for perf lane DB, decision
[cost-proportional-to-activity](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#cost-proportional-to-activity)
item 3. Captured 2026-11-10 20:48–21:45 PST; not edited after capture. Multitenant only. Synthetic
tenants and data only. Every figure is labelled **reproduced** (read from tool output of a run listed
here) or **derived** (arithmetic on reproduced figures, or read from source).*

## Anchors

| what | value |
|---|---|
| base | `codex/evaluator-partition-20261110` at `cb1b751d4e3875b9b9c250b1a3b6236f7c926aa4` (its head when the lane started). It has since moved to `d6560468` (stale serve.internal sockets; four files, none of them this lane's except `tests/tiers.json`); `git merge-tree d6560468 d53f12d6` merges cleanly. Not rebased |
| branch | `codex/perf-db-20261110`, worktree `externals/work/crm-perf-db-20261110` (own `npm ci`) |
| commits | `cbda5f680ef1dfa9a87cd8a7df1dfaf3c3f7497d` epoch admission; `d53f12d6b9f18651c5ae9225deababaab88a5a51` bounded warm + pool configuration. Not pushed |
| image (Compose runs) | `ns-pdb-perf:d53f12d6` = `sha256:83b6a6b4abf2…`, built by `deploy/multitenant/build.js`, label revision `d53f12d6b9f1…`; removed afterwards |
| Compose bootstrap overlay | the MT-BENCH-BASELINE overlay `overlay-4e5a1051` (core `16a1fc2d` + nightscout-deploy `085d88a..4e5a1051`); `deploy/multitenant` is identical between `16a1fc2d` and `cb1b751d` (`git diff --stat` empty) |
| lab PostgreSQL | postgres 16.15 `@sha256:721873c3…` (the Compose reference image), container `ns-pdb-pg`, deployment plan catalogue and grants (`deploy/multitenant/config.js`) as `admin-lifecycle-fit` applies them, 20 tenants; `pg_stat_statements` in the `postgres` database only |
| harness | [`harness/`](harness/): `setup.js` (lab), `measure.js` (per-transaction cost), `start.sh` (Compose startup + idle window, projects `ns-pdb-<label>`) |
| host | 16 logical cores, 64 GB; other projects' containers ran throughout. Load average per run is in each `runs/<n>/host.txt` (1-minute 6–22) |

## 1. The guarantee (read from source at `cb1b751d`)

A tenant's restore must never overlap a tenant write, and the census must refuse unknown writers.
Four mechanisms carry it; only the fourth was expensive.

| | invariant | where |
|---|---|---|
| I1 lock | a serving backend holds `pg_try_advisory_lock_shared(key_t)` for every tenant transaction, taken before `BEGIN`; restore takes `pg_try_advisory_lock(key_t)` exclusively, which cannot be granted while any shared holder remains | `operation-window.js:63` (now `acquire`), `maintenance-window.js:158` |
| I2 phase | inside the transaction, after binding `app.current_tenant_id`, the window row must read `phase='active'` with the configured `lock_key`; restore commits `phase='suspended'` (new generation, claim) before draining | `operation-window.js:87-91` (now in `assertClient`), `maintenance-window.js:141-151` |
| I3 operations | a serving operation commits an unfinished `tenant_lifecycle_operations` row (owner pid/birth by RLS) before its callback and finishes it after; restore waits for no unfinished rows before the exclusive lock, and re-checks under it | `operation-window.js:116,130`, `maintenance-window.js:155-159,106` |
| I4 admission | the serving identity cannot alter or bypass I1–I3: not elevated or member of an elevated role; no CREATE on the database or any schema; does not own the namespace; the five control tables, their columns, defaults, constraints, forced RLS and exact policies, no triggers/rules/inheritance/foreign indexes, a NOLOGIN safe owner, exact column privileges; the birth helper exact; the migration ledger exact; for the lifetime identity, no write on any other relation and no EXECUTE on any other non-system function; object oids unchanged since `ready()`; datastore identity unchanged; not superuser/BYPASSRLS | `operation-window-readiness.js:232-293`, called per transaction at `operation-window.js:57-60` |
| census | restore refuses a connected backend that is neither a registered participant nor an identity without clinical privileges and counter writes | `operation-cohort.js:79-133` (unchanged) |

I1–I3 were already the cheap, database-enforced per-tenant epoch and lock the brief lists as
candidates (generation/phase row + shared/exclusive advisory lock). What cost 5–9 ms per call was I4:
the full catalogue admission, re-run on every data transaction (lower) and every operation (lifetime).

## 2. Design chosen: a catalogue epoch read inside the transaction

**Candidate taken: "a cache keyed on an epoch", with the epoch computed by the database inside the
transaction from the live catalogue.** `lib/tenant-lifecycle/operation-window-epoch.js` builds one
expression: a SHA-256 over the oid/key and row version (`xmin`) of every catalogue row the admission
reads (`pg_class`, `pg_attribute`, `pg_attrdef`, `pg_constraint`, `pg_policy`, `pg_trigger`,
`pg_rewrite`, `pg_index` with its validity flags, `pg_inherits` for the five tables; the helper's
`pg_proc` and `pg_language` rows; every `pg_namespace` row; the current `pg_database` row; every
`pg_auth_members` row), the live attributes of every role, the current role's oid, the names
re-resolved to oids, and the ledger rows. For the lifetime identity it also covers every user
`pg_class` and `pg_proc` row (`oid >= 16384`, a superset of the swept namespaces) and every user
`pg_attribute` row with a column ACL. PostgreSQL gives every committed catalogue change a new row
version, so any grant, policy, owner, membership, object or ledger change changes the epoch.

Per transaction (`operation-window.js` `acquire` / `assertClient`): shared lock (I1) → `BEGIN` →
bind tenant → **one prepared statement** returning the epoch, `rolsuper`/`rolbypassrls`, the
datastore identity and the window row (I2). An epoch the window has not admitted runs the full
admission (I4) on that backend and is cached only if the epoch read after it is unchanged (two
attempts, then `LIFECYCLE_WINDOW_SCHEMA_UNSAFE`). I3 and the census are unchanged.

Rejected:

- **shared/exclusive lock taken by DDL**: GRANT/ALTER ROLE do not take a lock a reader would see;
  it would rely on every DDL actor cooperating, so it is not database-enforced.
- **event-trigger epoch row** (DDL bumps a counter): needs a superuser-created event trigger and a new
  control migration (deployment and managed-PostgreSQL impact), and still misses global objects
  (role attributes, memberships, database ACL), which would need the same direct reads anyway.
- **process cache with a time-to-live**: not validated by the database; refused by the brief.

Why this one, measured: the epoch statement costs 0.75 DB-ms (lower) and 1.5 DB-ms (lifetime) per
transaction against at least 2.6 and 9.4 for the admission it replaces (table below), needs no
migration, privilege or deployment change, and keeps every I4 check reachable on any change.

Coverage limits (read-derived): changes only a superuser can make to built-in objects (renaming a
type or language) are not in the epoch; in-place catalogue updates (`relpages`, `relfrozenxid`, …)
do not change `xmin` but are not admission inputs. In a `REPEATABLE READ` snapshot transaction the
epoch reads the transaction snapshot while privilege functions read the current catalogue; the
re-check after admission is then trivially equal. A superuser can defeat any of this, as before.

## 3. Results

### 3.1 Per idle tenant transaction, lab, before (`cb1b751d`) and after (`d53f12d6`), reproduced

`measure.js`, 300 iterations each, run back to back twice (load 1-minute 6.4–9.6);
`pg_stat_statements` for the two identities in the app database; [`lab/final-*.json`](lab/).

| path | statements before → after | DB-ms before → after | admission/epoch DB-ms before → after | wall ms before → after |
|---|---|---|---|---|
| data transaction (api identity) | 18 → 8 | 2.789 → 0.849 | ≥ 2.616 → 0.747 | 16.69 → 3.68 |
| operation, empty body (lifetime identity) | 26 → 16 | 11.676 → 3.718 | ≥ 9.358 → 1.505 | 29.04 → 8.86 |
| operation wrapping one data transaction | 44 → 24 | 14.619 → 4.548 | | 45.95 → 12.30 |

Run 1 agrees within 4% (`final-*-1.json`). Earlier quieter pair (load 1.4–1.6): 2.098 → 0.627 and
6.872 → 2.712 DB-ms ([`before-cb1b751d.json`](lab/before-cb1b751d.json), [`after-v1.json`](lab/after-v1.json)).
"≥": the before column sums only the statements in the top six; the remaining DB time of the
lifetime operation is the I3 `INSERT`/`UPDATE` (about 0.7 ms each), kept.

In the Compose deployment under load (§3.3), the lower epoch statement averaged 1.41 ms (evaluator)
and 1.35 ms (realtime) per call at 10 tenants (derived from `runs/n10/pg-idle-top.tsv`).
The baseline's `operation-window-table`/`-role` statements no longer appear for serving identities.

### 3.2 Fence and catalogue controls, disposable PostgreSQL, reproduced

`tests/operation-window-epoch.integration.test.js` (`NS_OPERATION_WINDOW_DOCKER_TEST=1`, containers
`ns-pdb-epoch-*`): **23 passing** at `d53f12d6`, and **23 passing on the base code** (`cb1b751d`
`operation-window.js`), so the suite observes the same guarantee before and after.

| control | break | symptom |
|---|---|---|
| skip the fence check | `if (row.phase !== 'active') throw …SUSPENDED` removed | red, 1 failing: "refuses a tenant whose window was closed after its admission was cached" → `AssertionError: Missing expected rejection.` (the write body ran during a closed window) |
| stale epoch | epoch replaced by a constant `sha256('stale')` | red, 19 failing: every catalogue-change case → `Missing expected rejection.`; 4 passing are the three fence cases and BYPASSRLS, which is read live, not through the epoch |
| restored | source restored | 23 passing |
| unbounded warm | Compose, 200 tenants, `NS_TENANT_STARTUP_CONCURRENCY=1000` | red: realtime `exit:78`, log "realtime preview readiness or initialization refused" ([`runs/n200-unbounded`](runs/n200-unbounded/)); default concurrency at 200: all roles ready |

The 19 catalogue cases, each refused on the next transaction after a cached admission and admitted
after the revert: table UPDATE and column UPDATE(phase) on windows; RLS no longer forced; an added
policy; an added trigger; an added index; a changed column default; a loginable owner; CREATE on a
schema; CREATE on the database; membership of an elevated role; CREATEDB and BYPASSRLS on the
serving role; a changed ledger; helper EXECUTE for a lower role; a changed helper configuration; a
foreign table write, a foreign column write and a foreign function for the lifetime identity; a
replaced windows table. (An added-then-dropped column is permanent: the admission refuses dropped
attributes, so it is not a revertible case.)

### 3.3 Startup and idle at 10–1,000 tenants, Compose reference, reproduced

`start.sh`, image `ns-pdb-perf:d53f12d6`, default concurrency 4 unless stated. Healthchecks were given
a 1,200 s start period so the real time to ready is measured. 60 s idle window after ready. Each
row is one run; [`runs/<label>/`](runs/).

| tenants | api ready s | realtime ready s | evaluator ready s | startup DB-ms (all roles) | load avg at ready |
|---|---|---|---|---|---|
| 10 | 8.1 | 8.3 | 11.6 | 5,967 | 14.9 |
| 100 | 26.2 | 26.4 | 42.8 | 30,109 | 19.9 |
| 200 | 39.7 | 39.9 | 61.9 | 37,072 | 17.9 |
| 200, concurrency 1000 (control) | 26.7 | **exit 78** | not started | | 15.5 |
| 500 | 112.0 | 112.2 | 154.4 | 72,652 | 17.4 |
| 1,000 | 341.2 | 341.4 | 420.7 | 130,816 | 16.3 |

Baseline at `16a1fc2d` (MT-BENCH-BASELINE): 100 fails (realtime exit 78), 200 fails (api exit 78 on
pool connect timeouts). Bounded warm is slower to api-ready than unbounded at 200 (39.7 vs 26.7 s)
because four tenants initialize at a time; the unbounded realtime does not start.

### 3.4 Marginal cost per tenant (coordinator's units)

| measure | 10 | 100 | 200 | 500 | 1,000 | label |
|---|---|---|---|---|---|---|
| idle DB-ms per minute, all roles | 92,775 | 64,150 | 47,772 | 27,239 | 16,128 | reproduced |
| idle DB-ms per tenant-minute | 9,278 | 641 | 239 | 54 | 16 | derived |
| PostgreSQL CPU % (one sample) | 384 | 300 | 181 | 112 | 82 | reproduced |
| evaluator operations per minute (lifetime INSERTs) | 2,268 | 994 | 675 | 316 | 200 | reproduced |
| evaluator period per tenant, s | 0.26 | 6.0 | 17.8 | 95 | 300 | derived |
| realtime operations per minute | 602 | 1,148 | 912 | 520 | 392 | reproduced |
| realtime refresh period per tenant, s | 1.0 | 5.2 | 13.2 | 58 | 153 | derived |
| PostgreSQL connections (all roles) | 29 | 29 | 29 | 29 | 29 | reproduced |
| api RSS MiB (one sample) | 92.7 | 236.3 | 312.0 | 397.6 | 736.7 | reproduced |
| evaluator / realtime RSS MiB | 258 / 217 | 292 / 273 | 380 / 317 | 380 / 364 | 459 / 423 | reproduced |
| startup DB-ms per tenant | 597 | 301 | 185 | 145 | 131 | derived |

- **DB-ms per tenant-minute is not a per-tenant cost at idle.** It falls as N rises because the
  idle DB work is the evaluator's and realtime's per-tenant one-second polls, and those loops are
  throughput-bound: total operations per minute fall while N grows. The window's own share is now
  the epoch statement (§3.1).
- **Connections** are fixed by the pool caps (evaluator 4, lifetime evaluator 8, lifetime realtime 8,
  realtime 4, outbox 2, suppression 2, maintenance 1; api's idle clients had been released): zero
  marginal connections per tenant. **Pool waits** were not instrumented (UNMEASURED); the collapse of
  operations per tenant is the observed effect.
- **api resident memory**: about 0.65 MiB per tenant from 10 to 1,000 (derived from single samples);
  3,000 tenants ≈ 2 GiB, 10,000 ≈ 6.5 GiB (derived, extrapolated).
- **Real cadence**: not run in this lane (UNMEASURED); the k6 workload of MT-BENCH-BASELINE was not
  repeated at these tenant counts.

**What runs out first, and at about what N (derived from the table):** the evaluator's per-tenant
cycle. At 100 tenants each tenant is evaluated about every 6 s, at 1,000 about every 5 minutes, so
time-driven alarms lag by minutes long before PostgreSQL CPU (82% at 1,000), connections (fixed) or
memory (≈0.65 MiB per tenant) limit anything. Realtime refresh is second (2.5 minutes per tenant at
1,000). Both are the per-tenant poll model that the decision's items 1–2 replace (other lanes).
Next after those: **startup time** at concurrency 4 grows about 0.34 s per tenant (≈17 minutes at
3,000, ≈57 minutes at 10,000, derived), and the stock Compose healthcheck budget (30 × 2 s, no start
period) is shorter than the measured api start from 500 tenants (112 s).

## 4. Configuration (as committed in `d53f12d6`)

| variable | default (previous built-in) | bounds |
|---|---|---|
| `NS_POOL_API_MAX`, `NS_POOL_API_CONNECT_TIMEOUT_MS` | 4, 5000 | 1–1000, 1–600000 |
| `NS_POOL_REALTIME_MAX`, `NS_POOL_REALTIME_CONNECT_TIMEOUT_MS` | 4, the role's `operationTimeoutMs` | same |
| `NS_POOL_EVALUATOR_MAX`, `NS_POOL_EVALUATOR_CONNECT_TIMEOUT_MS` | 4, 5000 | same |
| `NS_POOL_OPERATION_MAX`, `NS_POOL_OPERATION_CONNECT_TIMEOUT_MS` | 8, 5000 (lifetime pool, `operation-cohort-config.js`) | same |
| `NS_TENANT_STARTUP_CONCURRENCY` | 4 (startup warm in api, api domain floors, realtime, evaluator, and realtime's first refresh) | 1–1000 |

Read from the role process's environment; a set value that is not a whole number in range refuses
the boot with a `PreviewConfigError` naming the variable (`tests/pool-config.test.js`). Bounded,
not lazy, warm was chosen so a misconfigured tenant still fails the boot as before (the existing
"hard refuses wrong binding…" startup tests stay green) and readiness still means every tenant is
initialized.

## 5. Checks run at `d53f12d6`

| check | result |
|---|---|
| `npm run test:unit` | 3238 passing |
| window/cohort/startup protocol suites (`grep -l operation-window tests/*.test.js`, 8 files without the new native suite) | 133 passing after the fixture update |
| `tests/pool-config.test.js` | 16 passing (one bound control: concurrency = N reproduces the unbounded peak) |
| disposable-PostgreSQL suites: admin-lifecycle-fit 6, key-retention 6, admin-role-ownership 11, tenant-ownership-postgres 9, owner-subject-policy 38, tenant-activity 7, operation-window-epoch 23 | all passing |
| `npm run test:tiers` (check) | 632 files, 8 tiers: ok |
| `npm run test:write-boundary` | all 9 adapter entry points checked |
| eslint on changed files | 0 errors (4 existing-pattern warnings in tests) |
| affected selection (`scripts/test-select.js affected --since cb1b751d --depth 4`, 106 files, unit and integration) | exit 0: 572 + 27 + 53 passing, 566 pending (opt-in labs), against a dedicated `mongo:7.0.43` with `nofile=64000`. Two earlier attempts are void: the first full integration-tier run reached the local MongoDB 3.6 (stopped); the second and the first affected run lost their dedicated MongoDB to a WiredTiger fatal assertion on `EMFILE` (error 24) at its default file limit. The full integration tier was not re-run (UNMEASURED) |

## 6. For the maintainer

1. **Second per-read admission, outside this lane's fence:** the alarm-suppression reader re-runs the
   full window admission plus its own catalogue sweep on every reader snapshot
   (`lib/server/serve/evaluator-consumers.js:186-188` → `postgres-operation-control.js:9`,
   `evaluator-consumer-readiness.js:26-40`): 10.9 s of 92.8 s idle DB time per minute at 10 tenants.
   The same epoch could carry it; that is a change to the suppression guard's contract.
2. **Per-transaction backend observation** (`postgres-connection.js:127`, a `pg_stat_activity`
   lookup per transaction for the census) is the next largest per-transaction statement (3.8 s per
   minute for realtime at 100 tenants). It could be cached per pooled client; unchanged here.
3. **Startup budget:** probes and Compose healthchecks need a start period proportional to N (or a
   higher `NS_TENANT_STARTUP_CONCURRENCY` with larger pools, unmeasured).
4. `root_writer` stays fenced (decision root-writer-fenced). Connections opened in a cohort process
   go through `postgres-connection.js`, whose selected window now checks the epoch, so its
   admission becomes the epoch check too (read-derived; not run as `root_writer` here). Core
   `config.js` `grants()` still lacks its control reads (next batch, as recorded there).

## Resumed, 2026-11-10 (late): serve-then-warm readiness and the epoch everywhere

Decisions [readiness-serve-then-warm](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#readiness-serve-then-warm)
and [admission-epoch-everywhere](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#admission-epoch-everywhere).
Captured 22:00–23:30 PST; appended, the sections above are unchanged.

### Anchors

| what | value |
|---|---|
| base merged | `d6560468` (evaluator-partition head) **merged** into the branch: `7c415f28` (no rebase, so `cbda5f68`/`d53f12d6` keep their hashes) |
| new commits | `a52bc33babb582b45506a0da3f7be37b458e0e6d` serve-then-warm readiness (api) + Compose start period; `540d3998ec1edbd961c950d5caa6cdb3e061c82c` suppression reader on the epoch + backend identity cache. Head measured: `540d3998`. Not pushed |
| images | `ns-pdb-perf:d53f12d6` (`sha256:60c6d609…`, before) and `ns-pdb-perf:540d3998` (`sha256:cb32fc7b…`, after), each label-checked against its commit; removed afterwards |
| harness | [`harness/restart.sh`](harness/restart.sh) (api restart probe, first evaluator pass), [`harness/restart-all.sh`](harness/restart-all.sh) (recreate the api with the readiness flag), [`harness/eval-gap.js`](harness/eval-gap.js) (per-tenant evaluation gap) |

### Corrections to the sections above (measured this session)

- **"api ready" in §3.3 is not the api's own time.** `start.sh` polls health only after `docker compose up -d` returns, and Compose starts realtime only once the api is healthy and returns only once realtime has started (`depends_on: service_healthy`, `deploy/multitenant/compose.yaml`), so the api, realtime and tenant-admin columns are bounded below by realtime's readiness. The evaluator column is its own. The api's own time at 1,000 tenants is below (container logs and the restart probe).
- **The catalogue suite had 20 cases, not 19**: 3 fence cases + 20 catalogue cases = 23 tests, as §3.2's count says. The decision row quotes 19.

### 1. Readiness: serve, then warm (`a52bc33b`)

`lib/server/serve/tenant-startup.js` gains a readiness mode; the api adopts it.

- **`serve` (default for the api):** the role opens once its own dependencies are up. Tenants warm in the **background, bounded** (`NS_TENANT_STARTUP_CONCURRENCY`, default 4), and **a request for a cold tenant moves it to the front of the queue**: both. A cold tenant's request is refused `TENANT_WARMING`, **503 with `Retry-After: 5`**, for that tenant only. A tenant whose initialization fails is marked failed with an alert (`TENANT_WARM_FAILED`, log line and `health().alerts`) and refused `TENANT_UNAVAILABLE` (503, `Retry-After` until its retry after 30 s); the other tenants serve and the boot succeeds.
- **`all` (`NS_TENANT_READINESS=all`):** today's behaviour, ready only once every tenant is initialized; a tenant failure fails the boot.
- **Cold bound:** in both modes a tenant still cold after `NS_TENANT_COLD_ALERT_MS` (default 120,000) raises `TENANT_COLD_BEYOND_BOUND`, cleared when it warms.
- `health()` on the api role: `{readiness, configured, ready, warming, cold, deferred, failed, alerts, ready}`. Global failures (wrong window, configuration) still fail the boot.
- Compose fixture: the api, realtime and evaluator healthchecks get `start_period: 900s` (`deploy/multitenant/compose.yaml`). nightscout-deploy's Compose binding needs the same change; its Kubernetes probes need a matching startup probe.

**Controls (reproduced, `tests/tenant-readiness.test.js`, 8 passing):**

| control | result |
|---|---|
| one broken tenant among 100 (missing root credential metadata), actual api boot, readiness `serve` | boot succeeds; 99 tenants initialized and served; the broken tenant alerts `TENANT_WARM_FAILED` and is refused `TENANT_UNAVAILABLE` with `Retry-After` |
| break-it: `serve` reverted to boot-fails (background warm replaced by the `all` path) | red, 4 failing; the 100-tenant test fails with `Error: preview readiness or storage initialization refused; check operator preparation and credential privileges`; restored: 8 passing |
| the flag | `NS_TENANT_READINESS=all`: the same broken tenant fails the boot (same error); with no broken tenant, ready only after all 100 initialized |
| cold tenant over HTTP | `503`, `Retry-After: 5`, `{"error":"TENANT_WARMING"}`; a warm tenant on the same app is served |
| queue promotion | with concurrency 1, a request for the tenth tenant makes it the next to warm |
| cold bound | alert at exactly the bound (999 ms none, 1,000 ms alert), cleared once warm |

The existing api-boot protocol test runs under `NS_TENANT_READINESS=all` (today's semantics).

**Time to first served request after an api restart, 1,000 tenants (reproduced; three tenants: first, middle, last in configuration order; probe every 250 ms through nginx, so 502 while the api is down):**

| readiness | first served (all three) | statuses seen | load avg (1 min) |
|---|---|---|---|
| serve | 35.2 s | 137 × 502, then one 503 `Retry-After: 5`, then 200 | 6.8 |
| serve (repeat) | 53.0 s | 204 × 502, one 503 `Retry-After: 5`, then 200 | 18.7 |
| all (control) | 90.8 s | 355 × 502, then 200 | 18.6 |

Each tenant was served 250 ms after its first 503: the request moved it to the front of the warm queue. In `serve` mode the remaining 35–53 s is the api's own boot before its listener opens: SIGTERM to "Listening" was 33–35 s in the container log, and that boot builds every tenant's settings and plugin set once ("enabling feature" × 2 per tenant, 2,000 lines) in `previewDomains` before the tenant warm starts. That per-tenant construction is the api's next O(N) startup cost (not changed here). No readiness alerts in the api log (the background warm finished inside the 120 s bound).

### 2. The epoch everywhere (`540d3998`)

- **Suppression reader** (`evaluator-consumers.js` → `evaluator-consumer-readiness.js` `suppressionGuard`): each reader snapshot reads one epoch statement (the window epoch with the whole-catalogue sweep its `unrelated` check needs, joined by `tenant_alarm_suppression` and its ledger, `operation-window-epoch.js` `extra`); the full guard runs only for an epoch it has not admitted, and the epoch is cached only if unchanged after the full guard.
- **Backend identity** (`postgres-connection.js`): read once per pooled client and again when the client's backend pid differs; a reconnect is a new client.

**Controls (reproduced, `tests/operation-window-epoch.integration.test.js`, 47 passing):**

| control | result |
|---|---|
| suppression reader, 22 catalogue cases (the 19 window cases that apply to it, targeted at the suppression identity where role-specific, plus a foreign table read, a changed suppression policy, a changed suppression ledger) | each refused on the next snapshot after a cached admission; admitted after the revert. The lifetime "foreign function" case is not an input of this guard and is not run against it |
| unchanged epoch | three snapshots, no further full checks |
| break-it: suppression epoch held constant | red, 5 failing, each `Missing expected rejection.`: foreign table write, foreign column write, foreign table read, changed suppression policy, changed suppression ledger. The other 17 stay refused because the reader's own transaction passes the window epoch, which covers the control-table and role cases; these five are covered only by the suppression epoch |
| reconnect with a different backend (native: superuser `pg_terminate_backend` on the api identity's backends) | the new backend's pid is in the cohort census |
| break-it (protocol, `tests/tenant-operation-window.test.js`): cache keyed on the client only | red: `a different backend is read again` |

**Idle DB time, Compose, 60 s idle after start, before `d53f12d6` → after `540d3998` (reproduced):**

| tenants | total DB-ms per min | statements per min | suppression identity DB-ms | lifetime operations (eval + rt) | DB-ms per lifetime operation (derived) | load avg |
|---|---|---|---|---|---|---|
| 10 | 41,705 → 36,452 | 337,183 → 291,945 | 5,494 → 2,174 | 3,019 → 3,028 | 13.8 → 12.0 | 5.1 / 6.3 |
| 100 | 72,164 → 74,098 | 536,916 → 508,705 | 5,948 → 2,731 | 4,086 → 4,386 | 17.7 → 16.9 | 6.5 / 6.6 |

The per-transaction identity statement (`SELECT pg_backend_pid() AS pid,current_user …`) left the top statements: before, 17,564 calls / 1,642 ms (evaluator) and 12,000 / 1,063 ms (realtime) at 10 tenants, and 43,352 / 4,545 ms (realtime) at 100. The suppression full guard (`operation-window-table` 6,050 calls, `suppression-role` 1,210 calls at 10 tenants) is replaced by one epoch statement per snapshot (about 1.2 ms each, the whole-catalogue sweep). The idle total is still the evaluator's and realtime's per-tenant polls; at 100 tenants the after run also did 7% more operations.

### 3. Evaluator after a restart, 1,000 tenants (clinical note)

The evaluator keeps readiness `all` (its scheduling is the evaluator perf lane's), so after a restart **no tenant is evaluated until every tenant has warmed**; the evaluator was healthy 44 s after SIGTERM (container log). The cold-tenant alert covers warm only: it did not fire (warm finished inside 120 s) while tenants went unevaluated for much longer, so an alert on *time since the last evaluation* belongs in the evaluator's scheduler (seam below).

**Per-tenant evaluation gap after an evaluator restart, 1,000 tenants (reproduced, [`runs/r-n1000/evaluator-gap.txt`](runs/r-n1000/evaluator-gap.txt), `harness/eval-gap.js`, load average 15.8 → 9.3):**
the evaluator was healthy 54.5 s after the restart; a tenant's first evaluation is its first window operation by an evaluator backend after that point.

| evaluated within (of 1,000) | 60 s | 5 min | 15 min | 25 min (end) | not evaluated within 25 min |
|---|---|---|---|---|---|
| tenants | 16 | 143 | 424 | 700 | **300** |

Since the restart: p25 5.7 min, p50 10.8 min, p90 22.5 min. This is the clinical gap the note asks for: with the per-tenant polling evaluator at 1,000 tenants, most tenants' alarms are not evaluated for minutes after a restart and 30% not within 25 minutes. It is set by the evaluator's cycle throughput (the evaluator perf lane), not by warm: warm took under a minute and raised no cold alerts. A first pass with `restart.sh` part (2) is superseded (it dropped operations of pooled backends that had since closed; [`runs/r-n1000/restart-serve.txt`](runs/r-n1000/restart-serve.txt) keeps its line for the record).

### 4. Seams for the peer lanes

| lane | what it needs at the join | where |
|---|---|---|
| realtime (`codex/perf-realtime-20261110`) | pass `{ readiness: require('./pool-config').tenantReadiness() }` to `tenant-startup.create` and stop awaiting every tenant before the role opens; the runtime's first refresh loop over all tenants (`runtime.js:45`, bounded by this lane) and `health().ready` requiring every cell healthy (`runtime.js:57`) must become per-tenant; a socket for a cold tenant needs a refusal clients retry (the HTTP side has `TENANT_WARMING` + `Retry-After`) | `lib/server/serve/preview-realtime.js:57,63`, `lib/server/realtime/runtime.js:45,57` |
| evaluator (`codex/perf-evaluator-20261110`) | the same option at `evaluator-preview.js:50`; `create()` already calls `startup.ensure` per tenant (`:66`), so a cold tenant can initialize on its first cycle; the scheduler must skip or prioritise tenants not yet warm (`startup.health()`), alert when a tenant has not been evaluated within a bound after restart (the measured gap above), and expose `startup.health()` in `health()`/inspection; `evaluator-consumers.js` `prepare` still visits every tenant sequentially before the runtime starts | `lib/server/serve/evaluator-preview.js:50,66,104`, `lib/server/serve/evaluator-consumers.js` tenant loop |
| api (this lane, next) | the per-tenant settings/plugin construction in `previewDomains` runs for every tenant before the listener opens (≈35–53 s at 1,000) | `lib/server/serve/preview-api.js` `previewDomains(...)` |

### 5. Checks at `540d3998`

| check | result |
|---|---|
| `npm run test:unit` | 3250 passing |
| protocol suites touching the window, startup or suppression guard (17 files) + pool-config + readiness | 201 passing, 16 pending (opt-in) |
| native epoch suite | 47 passing |
| disposable-PostgreSQL suites: admin-lifecycle-fit 6, key-retention 6, admin-role-ownership 11, tenant-ownership-postgres 9, owner-subject-policy 38 | passing |
| tier check, write-boundary | ok (634 files); all 9 entry points |
| eslint on changed files | 0 errors |
| Compose file | `docker compose config` valid |
| affected selection (`test-select.js affected --since cb1b751d --depth 4`, 212 files) | exit 0: 754 + 66 + 27 + 1368 + 18 passing, 593 pending (opt-in labs); dedicated `mongo:7.0.43` with `nofile=64000` |
| full integration tier (`npm run test:integration`) | exit 0: 3643 passing, 650 pending, against the dedicated `mongo:7.0.43` (`nofile=64000`); this replaces the UNMEASURED row in §5 |
