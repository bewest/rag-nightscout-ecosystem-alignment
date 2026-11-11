# Capacity fixes: configuration bound and warm retry (2026-11-11)

*Contributor-facing evidence record for the multitenant preview (draft PR #8898). Snapshot; not edited after capture. Synthetic data only.*

## Anchors

| tree | commit |
|---|---|
| batch head (source) | `0392acf97c720a7e121eea47a9d42a0c8dbe9e73` (worktree `externals/work/crm-batch-join-20261111`, not edited) |
| this lane | branch `workspace/capacity-fixes-20261111`, head `5517cb6c74f2906383a436d034b86be86a0f743a` (one commit on 0392acf9), worktree `externals/work/crm-capacity-fixes-20261111` |
| nightscout-deploy (read only, not touched) | `9de244df8db294df807663a664633487894f0ea0` |
| alignment `main` at writing | `a59e5bd45a288339e198e657bb8abeb29c122511` |

Not pushed. No branch named `capacity-fixes` existed before this lane.

## Finding 1: one configuration bound, named refusals

**Mechanism (read from 0392acf9).** Eight loaders each carried a fixed 1,048,576-byte check: `preview-config.js` (api), `evaluator-config.js`, `owner-preview-config.js` (tenant-admin), `admin-config.js`, `realtime/contract.js` (realtime configuration, the realtime admission list, the operation cohort), and `tenant-connector/config.js` (vcpool). The vcpool loader checked only the size from `stat`, then read the file unbounded. Each loader caught every failure and replaced it with one generic message, so an oversize file could not be told apart from bad JSON.

**Change.** `lib/server/serve/config-file.js` holds the bound and the one reader. Every loader above now reads through it.

| setting | value |
|---|---|
| variable | `MULTITENANT_CONFIG_MAX_BYTES` (the name the deploy lane's bootstrap writes) |
| default | 1,048,576 bytes (1 MiB), unchanged |
| range | 65,536 to 67,108,864 bytes (64 KiB to 64 MiB), a whole number; anything else refuses the boot with `CONFIG_FILE_LIMIT_INVALID` |

The bound is checked twice: on the size from `stat`, and on the bytes actually read. The read takes 64 KiB chunks and stops one byte past the bound. The reader refuses a non-regular path before opening it, so a FIFO cannot block. After opening, it re-checks with `fstat` that the file is still the same regular file.

| code | cause | message (the variable name is the label; the path and contents are never shown) |
|---|---|---|
| `CONFIG_FILE_TOO_LARGE` | over the bound | `MULTITENANT_PREVIEW_CONFIG is too large: 1971372 bytes, over the limit of 1048576 bytes (MULTITENANT_CONFIG_MAX_BYTES)`; the error also carries `size` and `limit` |
| `CONFIG_FILE_NOT_REGULAR` | directory, FIFO, device, or the file was replaced mid-read | `… is not a regular file` |
| `CONFIG_FILE_UNREADABLE` | stat, open or read failed | `… cannot be read (ENOENT)`; only the errno is named |
| `CONFIG_FILE_INVALID_JSON` | parse failure | `… is not valid JSON` (the parser's message quotes the text, so it is dropped) |

Each module keeps its own error class (`PreviewConfigError`, `ConnectorConfigError`, and coded errors in realtime), with the stable code set on it. In realtime, `REALTIME_CONFIG_REFUSED` and `SOCKET_ADMISSION_REFUSED` still cover every content refusal. Only the read refusals listed above pass through with their own codes.

**Synthetic roster, measured (shipping loader, `preview-config.load`).** The generator writes 657 bytes per tenant (aliases, Vault key names, `tokenFile`, a settings block):

| roster | size | `MULTITENANT_CONFIG_MAX_BYTES` | result |
|---|---|---|---|
| 3,000 | 1,971,372 B | unset | refused `CONFIG_FILE_TOO_LARGE` (1971372 over 1048576) |
| 3,000 | 1,971,372 B | 4194304 | loaded, 3,000 bindings, 122 ms |
| 10,000 | 6,570,372 B | 4194304 | refused `CONFIG_FILE_TOO_LARGE` (6570372 over 4194304) |
| 10,000 | 6,570,372 B | 8388608 | loaded, 10,000 bindings, 304 ms |

Run through the CLI (`bin/nightscout.js multitenant api`) with the 3,000-tenant file: unset, it exits 78 with `nightscout multitenant: MULTITENANT_PREVIEW_CONFIG is too large: 1971372 bytes, over the limit of 1048576 bytes (MULTITENANT_CONFIG_MAX_BYTES)`. With 4194304, configuration loads and boot reaches storage, which refuses because no PostgreSQL was given (exit 78, `preview readiness or storage initialization refused …`).

## Finding 2: realtime warm retries an api that is not ready

**Mechanism (read from 0392acf9).** Realtime's startup warm (`lib/server/serve/preview-realtime.js`, the `tenant-startup.create` initializer) calls the api's `authorizeSocket` over the internal transport. The transport made every failure look the same. The server answered any handler error with 503 `{"error":"SOCKET_IPC_UNAVAILABLE"}`. The client turned any non-200 answer or connection error into `Error('SOCKET_IPC_UNAVAILABLE')`, with no code. A missing socket file threw a raw `ENOENT`. So realtime could not tell an api that is restarting from one that refuses, and it failed the tenant on the first answer. Credential denials do not come back as 401, 403 or 423 on this path: they are 200 `{denied:true}`. A tenant the api does not know comes back as the same opaque 503.

**Change.**
- **Server** (`transport.js` handler). Three conditions now answer 503 `{"error":"SOCKET_IPC_NOT_READY"}`: the listener is closing, the route's role has not bound yet (`internal-listener.js` now throws `SOCKET_IPC_NOT_READY` there), or the handler threw `TENANT_WARMING`. Everything else stays the opaque `SOCKET_IPC_UNAVAILABLE`.
- **Client.** It still rejects with `SOCKET_IPC_UNAVAILABLE`, and adds `notReady: true` for:
  - the not-ready body;
  - a missing socket file;
  - a connection error before any answer (`ECONNREFUSED`, `ECONNRESET`, `ENOENT`, `EPIPE`, `ENOTFOUND`, `EAI_AGAIN`, `ETIMEDOUT`).

  Any other status, 401, 403 and 423 included, is unmarked.
- **Retry** (`tenant-startup.notReadyRetry`, wired around the warm's `authorizeSocket` in `preview-realtime.js`).
  - Only `notReady` errors and `TENANT_WARMING` codes are retried.
  - Backoff is exponential with equal jitter: 100 ms base, 2 s cap.
  - The deadline is shared by the whole outage. It runs from the first not-ready answer and resets on any success. Past the deadline, every caller fails on its first not-ready answer and the tenant is marked failed, as before. So an api that is down longer than the deadline costs each tenant one fast failure, not one full deadline.
  - A caller backs off inside its own warm slot, so retries never exceed `NS_TENANT_STARTUP_CONCURRENCY`.
  - New setting `NS_TENANT_WARM_RETRY_MS`: default 60000, range 0 to 600000, where 0 means no retry.
- **Docs.** `docs/internal-service-api.md` documents the not-ready answer and the retry.

## Tests

| run | result |
|---|---|
| new `tests/multitenant-config-bound.test.js` (unit tier) | 5 passing |
| new `tests/realtime-warm-retry.test.js` (unit tier) | 11 passing; both new files 5 consecutive runs, 16 passing each |
| focused: 29 existing suites that require the changed modules, plus the two new ones | 339 passing, 0 failing |
| multitenant corpus (`scripts/test-multitenant.js`): owner-preview.integration, tenant-socket-data-forwarding, operation-window-epoch, multitenant-preview-replicas, admin-role-ownership, admin-lifecycle-fit, multitenant-preview-process (disposable PostgreSQL 16 + MongoDB 8.0, verified removed) | 98 passing, 0 pending, 0 failing |
| `test:affected --depth 4` (281 files), first run | UNMEASURED for integration and stress: the disposable MongoDB container disappeared mid-run, and 9,572 `ECONNREFUSED` lines to its port account for the 79 integration and 3 stress failures. Unit 922 passing, dependency 66, harness 33 |
| `test:affected --depth 4` integration and stress files (192), rerun on a fresh MongoDB 8.0.34 container with `--ulimit nofile=64000:64000`; the first container and a second one with default limits aborted with `Too many open files` (mongod fassert, exit 139), an environment limit of the container, not this change | integration 2,915 passing, 567 pending (opt-in), 0 failing; stress 18 passing; 0 `ECONNREFUSED` |
| `node scripts/test-tiers.js check` | 656 test files, 8 tiers: ok |
| eslint on changed files | 0 errors |

Two existing tests changed. In `admin-role.test.js`, a truncated file is now refused as `CONFIG_FILE_INVALID_JSON`; a valid-JSON but wrong file is still `invalid explicit admin operator configuration`. In `evaluator-preview-runtime.test.js`, the parse-count instrument counts `fs.openSync` instead of `fs.readFileSync`, because the reader no longer calls `readFileSync`.

## Break-it controls (each red, then restored and confirmed byte-identical)

| control | break | symptom |
|---|---|---|
| C1 | `maxBytes` ignores `MULTITENANT_CONFIG_MAX_BYTES` | 3 of 5 config-bound tests red. The 3,000-tenant roster test fails on load with the bound raised: `MULTITENANT_PREVIEW_CONFIG is too large: 1971358 bytes, over the limit of 1048576 bytes`. The range test gets 1048576 for `'65536'`. The every-loader test fails at `MULTITENANT_EVALUATOR_CONFIG read within a raised bound` |
| C2 | stat size check removed | The bound is still enforced on read. The roster test and the named-cause test go red only on their exact-size assertion: the message is now `too large: more than 1048576 bytes`. The read-bound test and the every-loader test (both assert refusal and limit) stay green |
| C2b | stat and read checks both removed | 4 of 5 red. `Missing expected exception: READ_BOUND_ENFORCED`; the roster and loader tests get `is not valid JSON` instead of too large, because the chunked read still stops at limit+1 bytes and so is never unbounded |
| C3 | retry disabled (every not-ready error thrown at once) | 4 of 11 red. `RESTART_OVERLAP_NO_TENANT_FAILED` expected 0, got 40 failed of 40, over uds and http. The unknown-tenant test got 8 failed instead of 1. The backoff unit test got `SOCKET_IPC_UNAVAILABLE` |
| C4 | client marks every failure not ready (refusals would be retried) | 5 of 11 red. `REFUSAL_NOT_RETRIED` expected 6 requests, got 543 / 552 / 543 for 401 / 403 / 423. The classification test fails at `refused` over uds and http. The unknown-tenant arm alone: `UNKNOWN_TENANT_NOT_RETRIED` expected 1, got 132 |
| C5 | server answers `TENANT_WARMING` as the opaque refusal | 5 of 11 red. Restart overlap got 35 (uds) and 37 (http) of 40 failed; the classification test fails at `warming` |

With the break removed, the 401/403/423 tests pass with retry on: one request per tenant, `retries 0`.

**Restart-overlap test design.** The api side runs a real serve-then-warm `tenant-startup` behind the real handler. Its warm starts when its listener opens, so it answers `TENANT_WARMING` and moves the requested tenant to the front of its queue. Realtime starts 300 ms before the listener, so its first answers are a missing listener. The test asserts:
- that `TENANT_WARMING` answers were seen and retried;
- at most 4 requests in flight at the api (the realtime warm concurrency);
- 40 of 40 warm;
- with `deadlineMs: 0` (no retry), at least one tenant failed.

An earlier version started the api's warm before its listener. Under C5 it stayed green, because the api had warmed every tenant before realtime's first request. That version was fixed before the controls above were recorded.

## Open points

1. **`deploy/multitenant/load-env.js` is not covered.** It does not exist in core at 0392acf9; it left core in f3dc10c8 and lives in nightscout-deploy at `bindings/compose/multitenant/load-env.js:9`. It has its own fixed 1 MiB check on `env.json` (`NS_ENV_FILE`), alongside lstat, symlink and mode checks.
   - The bound for `env.json` cannot come from `env.json` itself: `load-env` reads that file to set the environment. `MULTITENANT_CONFIG_MAX_BYTES` has to be in the container's own environment (Compose `environment:`) for `load-env` to see it.
   - The deploy copy can call core's `lib/server/serve/config-file.js` `maxBytes(process.env)` (`health.js` already requires `../../lib/...`) and keep its own lstat and mode checks, or implement the same name and range.
   - That change belongs to the deploy lane.
2. **`Tenant warm drained: ready 0 failed 1` after restarting 4 roles together (deploy lane).** That log line is printed by every role's `tenant-startup`, so it does not say which role failed or why. This lane retries only realtime's `authorizeSocket` check against the api. It does not retry:
   - database-side failures: realtime's `provisionTenant`, the evaluator's and api's own warm (a PostgreSQL that is not yet accepting connections);
   - the api's `TENANT_UNAVAILABLE`, which means the api itself marked the tenant failed in the last 30 s.

   C3 shows the realtime/api case is covered. The deploy lane's event is not confirmed covered. The role's `/health` alerts carry the cause code (`cause`), which would show whether it is the api path.
3. **Realtime reads its configuration file on every `readCurrent` (read-derived, not measured here).** `contract.parsedFile` reads and string-compares the whole file each call. Parsing only happens on change. At 3,000 tenants that is a 1.9 MB read per call. This change adds an `open` and `fstat` per read but does not alter the pattern. The capacity lane may want to measure it, as was done for the evaluator (inode/mtime cache).
4. The same-pattern limits that were left alone:
   - `lib/human-session/private-setting.js`: private secret files, own bound;
   - `deploy/multitenant/ui.js`: public UI configuration, no roster;
   - message-size limits (`maxMessageBytes`).

## Follow-up: Compose fixture limits (2026-11-11, branch head `12fa221d9c1ff1eb7f8d3b5844b17e70adc477b3`)

Started from `5517cb6c`. One commit added (`12fa221d`). Items 1 and 3 are stopped on a mismatch, reported below.

### Mismatch: core's fixture `config.js` is not the deploy copy

The brief says `deploy/multitenant/config.js` has a `tenantCount` that accepts 1..10000, and that nightscout-deploy keeps the fixture byte-identical. At `5517cb6c` neither holds for `config.js`:

| tree | `deploy/multitenant/config.js` / `bindings/compose/multitenant/config.js` |
|---|---|
| core `5517cb6c` (this branch) | no `tenantCount`, no `NS_DEMO_TENANTS`; fixed tenants `[A,B]`, `maxTenants:2`, realtime `maxSockets:100`. It was shrunk in f3dc10c8 to the fixture core's tests load, and has the newer grants (ownership_operator, change_stamps) |
| nightscout-deploy `main` `9de244df` | `tenantCount` from `NS_DEMO_TENANTS`, 1..1000 |
| nightscout-deploy `deploy/capacity-fixes-20261111` `ab950a23`, and `deploy/sync-0392acf9-20261111` | `tenantCount` 1..10000 |
| capacity overlays `crm-overlay-0392acf9-capacity`, `crm-overlay-5517cb6c-capacity` | the deploy copy with 1..10000, overlaid on core |

The deploy `config.js` differs from core's in 41 lines. `ui.js`, `health.js`, `restore.js` and `demo.js` are identical. So `tenantCount` and the ceiling live in the deploy copy, not in core. Two of the items depend on which direction the copy goes:
- The shared constant (item 1) and a tenant-derived `maxSockets` (item 3) need a tenant count in core's `config.js`, and there is none to share.
- Adding one would mean porting the deploy `tenantCount` into core.
- If the deploy lane then copied core over its own copy byte for byte, it would replace its own copy rather than receive a fix.

Decision for the coordinator: either port `tenantCount` (1..10000) into core's fixture, so that core becomes the source of the whole `config.js`, or keep the ceiling in the deploy copy and make the ui read it from there.

### Item 2, done: the ui refusal names its cause

`deploy/multitenant/ui.js` `main` now reads `UI_PUBLIC_CONFIG` through `lib/server/serve/config-file.js`. Before this, the read had no size limit and a fixed 1 MiB check followed it. The size limit is now `MULTITENANT_CONFIG_MAX_BYTES`. The entrypoint prints `UI_STARTUP_REFUSED: <code>`, plus the reader's message for a read refusal. The configuration's contents and path are never printed. Measured with the real entrypoint (`spawnSync`, exit 78):
- `UI_STARTUP_REFUSED: CONFIG_FILE_TOO_LARGE: UI_PUBLIC_CONFIG is too large: <n> bytes, over the limit of 1048576 bytes (MULTITENANT_CONFIG_MAX_BYTES)`
- `UI_STARTUP_REFUSED: CONFIG_FILE_INVALID_JSON: UI_PUBLIC_CONFIG is not valid JSON` (the planted marker is absent)
- `UI_STARTUP_REFUSED: UI_PUBLIC_CONFIG_INVALID` for version 2, and for 1,001 tenants (the 1,000-tenant limit is unchanged)

Tests:
- `tests/compose-ui.test.js`: 7 passing (2 new).
- `compose-ui`, `compose-deployment-protocol` and `admin-role` together: 31 passing.
- eslint: 0 errors.

Control: with the swallowed form restored (`catch { 'UI_STARTUP_REFUSED' }`), 2 of 7 go red. The first is `UI_CAUSE_CODE_PRINTED`. The second expected `UI_STARTUP_REFUSED: UI_PUBLIC_CONFIG_INVALID` and got `UI_STARTUP_REFUSED`. Restored byte-identical.

### Item 3, read only: what realtime `maxSockets` bounds

`lib/server/realtime/protocol.js:352` refuses a connection when `states.size >= maxSockets`. `states` holds every connected socket of the realtime process across all tenants and namespaces (`/`, `/storage`, `/alarm`). So the limit is one ceiling for the whole process, with no limit per tenant.
- It is validated in `lib/server/realtime/config.js:16` as a positive integer with no upper bound.
- It is part of the configuration identity (`config.js:28`), so changing it needs a restart.

The capacity runs' 25000 means two sockets per tenant at about 12,500 tenants. Choice pending the mismatch above. Recommendation: derive it in the fixture as `tenantCount × sockets per tenant`, with sockets per tenant an operator setting (default 2). Of the options the brief offered, this one keeps a real per-process limit that scales with the roster. A fixed operator total would drift when the tenant count changes.

### Item 4, read only: limits that scale with tenant count

| where | limit | blocks 3,000–10,000 in Compose? |
|---|---|---|
| `deploy/multitenant/ui.js:30` | tenants ≤ 1000 | yes; the fix is held on the mismatch |
| `deploy/multitenant/ui.js:36` | aliases ≤ 100 per tenant | no |
| `deploy/multitenant/config.js:129,149` (core) | `maxTenants:2` for evaluator, realtime and api socket forwarding | yes in core's copy; the deploy copy uses `n` |
| `deploy/multitenant/config.js:139` (core) | realtime `maxSockets:100`, for the whole process | yes, at 2 sockets per tenant above 50 tenants |
| `lib/server/serve/evaluator-config.js:49`, `lib/server/realtime/config.js` + `admission.js:9`, `lib/server/realtime/private-config.js:9` | tenants ≤ the configuration's `maxTenants` (positive integer, no upper bound) | no, when the fixture sets it from the count |
| `lib/server/serve/admin-config.js:30` | `MAX_TENANTS = 10000` | no up to 10,000; refuses 10,001 |
| `lib/tenant-connector/config.js:40,87` | vcpool `maxTenants` default 1000, settable 1..100000 | only if vcpool runs with the default |
| `lib/server/serve/preview-config.js:186`, `owner-preview-config.js:67` | trust keys ≤ 10000 | no (a key list, not per tenant) |
| every role configuration file | `MULTITENANT_CONFIG_MAX_BYTES` (first part of this record) | settable |

Bootstrap's `validateFiles` (core `config.js:179`) is in the same file as the mismatch, so making it validate the ui configuration is held too.

### Decision applied: one preview tenant ceiling (branch head `5c60aec669362b032a10d6dd7ac368e9c61e8003`)

Coordinator decision: nightscout-deploy is the source of the deployable `config.js`, and core's copy stays the shrunk test fixture. `tenantCount` is not ported into core.

- **The constant.** `lib/server/serve/tenant-ceiling.js` exports `PREVIEW_MAX_TENANTS = 10000`, the value `admin-config.js` held as `MAX_TENANTS`. `admin-config.js` and `deploy/multitenant/ui.js` both read it, so the ui's own 1,000 is gone. The ui file's size stays bounded by `MULTITENANT_CONFIG_MAX_BYTES`.
- **Left to the deploy lane:** take `tenantCount`'s range from this constant, derive `maxSockets` = tenantCount × sockets per tenant (default 2), and have bootstrap validate the ui configuration.
- **New tests** (`tests/compose-ui.test.js`):
  - `parseConfig` accepts 3,000 and 10,000 tenants and refuses 10,001.
  - The actual entrypoint, started on a synthetic 3,000-tenant file (157,915 bytes), serves `t2999.example.test` (200) and refuses an unconfigured host (421).
  - The entrypoint refuses 10,001 tenants, inside a raised byte bound, with `UI_STARTUP_REFUSED: UI_PUBLIC_CONFIG_INVALID`.
- **Control.** With the 1,000 limit restored in `ui.js`, 2 tests go red. `parseConfig` throws `TypeError: UI_PUBLIC_CONFIG_INVALID` for 3,000. The entrypoint test fails `UI_3000_TENANTS_SERVED` with stderr `UI_STARTUP_REFUSED: UI_PUBLIC_CONFIG_INVALID`. Restored byte-identical.
- **Test runs:**

| run | result |
|---|---|
| `compose-ui` + `admin-role` | 19 passing |
| affected since `5517cb6c` at depth 4 (14 files; disposable MongoDB 8.0 with `nofile=64000`, removed after) | unit 85 passing; integration 24 passing, 63 pending (opt-in suites, run in the corpus below) |
| corpus: admin-role-ownership, admin-lifecycle-fit, multitenant-preview-process, multitenant-preview-replicas, owner-preview.integration, owner-configuration.integration (disposable PostgreSQL 16, verified removed) | 61 passing, 0 pending, 0 failing |
| tier map; eslint | ok; 0 errors |

No corpus suite runs the Compose ui; `compose-ui.test.js` is its suite.
