# One internal listener per role process, with graceful shutdown — 2026-11-10

Queue item `MT-INTERNAL-LISTENER`, lane branch `codex/internal-listener-20261110`
(local worktree `externals/work/crm-internal-listener-20261110`, not pushed).
It implements the decisions
[internal-listener-ory-pattern](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#internal-listener-ory-pattern)
and
[internal-listener-graceful-shutdown](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#internal-listener-graceful-shutdown).
Status: **fixed** on a local branch. Focused tests, a Compose run and break-it
controls are recorded below. Full, browser and corpus acceptance is left to the
joined candidate.

## Anchors

| Anchor | Value (from `git rev-parse` at writing) |
|---|---|
| Lane head | `78ecba7684aa94b0ce46a08a189217c1e4191605` |
| Lane commits | `efb58a0f` (implementation, tests, docs, instrument), `78ecba76` (instrument control-name fix) |
| Base = #8898 candidate head | `official/workspace/multitenant-20261102` = `b70ad83fa4cdaeb7e6023137a05bd811d7db606a` (unchanged at the 2026-11-10 re-fetch) |
| `official/dev` | `4a482627bfdafb1fef8dcbe0ac6c484811cae563` |
| Alignment `main` at writing | `638e5909181db06d38a86dff8242ab13742257ca` |
| Diff vs base | 47 files, +1046 / −359 |
| sha256 `lib/server/internal-api/transport.js` | `8938da7d79b59660c41d19718b7938841cb3bbc2bf88043bdbc0727925cb2751` |
| sha256 `lib/server/internal-api/listener-config.js` | `67d03a8552e5a61b5eb252c482a5b76d7580f839b704cd6daebf0bfe37b85cbf` |
| sha256 `lib/server/serve/internal-listener.js` | `c7a8358d1f7fd4dd4c945b342236c49a1a3a152993c91e050a044dd227333633` |

## The configuration as built (read-derived from the diff)

**This process's listener (`serve.internal`)**, `lib/server/internal-api/listener-config.js`:

| Key | Environment override | Default |
|---|---|---|
| `socket` | `NS_SERVE_INTERNAL_SOCKET` | `<runtime>/<roles>.sock`. `<runtime>` is `$XDG_RUNTIME_DIR/nightscout`, else `/run/nightscout`. `<roles>` is the process's role list, sorted and joined with `+` (`api.sock`, `api+realtime.sock`). |
| `host`, `port` | `NS_SERVE_INTERNAL_HOST`, `NS_SERVE_INTERNAL_PORT` | none. Both must be set explicitly; a partial pair is refused. |
| `shutdownTimeoutMs` | `NS_SERVE_INTERNAL_SHUTDOWN_TIMEOUT_MS` | 5000 (0..60000). `nightscout multitenant` also requires it to be below its 10000 ms shutdown bound (exit 78). |

- `socket` and `host`/`port` are exclusive. Unknown keys are refused. When the
  default socket is used, its runtime directory is created with mode 0700 if
  missing. The existing transport check still requires an owned 0700 directory.
- The resolver accepts a config object. `nightscout multitenant` passes `{}`, so
  today the settings come from the environment and the defaults only: no process
  config file carries a `serve` block (see open points).
- Trust is unchanged: `trust:'network'`, and the listener has no authentication.
  The public listeners (`listeners.js`) are untouched.

**Peer addresses**: another role is reached at `NS_<ROLE>_INTERNAL_URL`
(`http://host:port`) or `NS_<ROLE>_INTERNAL_SOCKET`. These are exclusive, and the
default is `<runtime>/<role>.sock`. `<ROLE>` is upper case with `_` for `-`, for
example `NS_TENANT_ADMIN_INTERNAL_URL`. A role this process serves is always
reached on the own listener; a wildcard bind is dialled on loopback. A peer
address for an own role is refused when it names another socket, another kind of
address or another port. A shared peer list may name the process by its service
name (`NS_API_INTERNAL_URL=http://api:7001` on the api process).

**Contracts are decided by role code**, `lib/server/serve/internal-listener.js`:

| Role | May serve |
|---|---|
| api | `socket-authority` (only with `socketForwarding`), `lifecycle-participant` |
| realtime | `alarm-delivery`, `lifecycle-participant` |
| evaluator | `lifecycle-participant` |
| tenant-admin | `lifecycle-participant` |

- The route table is fixed and the listener opens in `serve.start`, after the
  cohort and before any role boots. Each role binds its handlers after its boot;
  routes answer `SOCKET_IPC_UNAVAILABLE` until then. This keeps realtime's
  boot-time warm call to a co-resident api working.
- Start-up refuses a binding for a contract the role does not own
  (`INTERNAL_API_CONTRACT_UNOWNED`) and any contract left unbound
  (`INTERNAL_API_CONTRACT_UNBOUND`).
- A process with no contract opens no internal listener.
- Each contract keeps its own byte and time bounds on the shared listener (new
  per-module `bounds` in `transport.compose`). The listener-wide bound is the
  widest of them.

**Removed with no compatibility shim** (the preview is unreleased): `endpoint-config.js`;
`socketPathEnv`/`endpoint` in `socketForwarding`, in the evaluator `route` and in
cohort participant rows; `apiSocketPathEnv`/`alarmSocketPathEnv`/`apiEndpoint`/`alarmEndpoint`
in the realtime config; `operation-cohort.openControl()`. Each old key is now
refused by exact-key validation (tested).

- Participant rows are `{id, roles, namespaces, maxMessageBytes, timeoutMs}`.
  The address comes from the roles, and all roles of one row must resolve to one
  address.
- The Compose demo (`deploy/multitenant/config.js`, `health.js`) now uses
  `/run/ns-ipc/<role>.sock` for every role. The old `alarm.sock` and
  `cohort-<role>.sock` paths are gone.
- Updated documents: `docs/internal-service-api.md` (new section "The internal
  listener"), `docs/internal-service-topology.md`, `docs/tenant-operation-cohort.md`,
  `lib/server/realtime/README.md` and `evaluator-consumers-NATIVE-PLAN.md`.

**Shutdown**, `transport.compose(..., {shutdownTimeoutMs})`:

1. `close()` stops accepting and destroys the connections that carry no
   dispatched call.
2. A request that arrives while closing is refused with 503.
3. Dispatched calls finish and send their responses, until the deadline. The
   check after the call now only requires the connection to be alive; before,
   it refused once closing had started.
4. At the deadline, the remaining connections are destroyed. Their callers get
   `SOCKET_IPC_UNAVAILABLE`, which callers treat as uncertain with no retry, as
   before.
5. `close()` still awaits the handler promises afterwards, as before.

`serve.start().stop()` now closes the internal listener **first**, while the
role contexts are alive, then runs the earlier sequence.

## Focused checks (reproduced on clean `78ecba76`)

```bash
node_modules/.bin/mocha tests/internal-api-*.test.js tests/realtime*.test.js \
  tests/operation-cohort*.test.js tests/profile-wire-response.test.js \
  tests/human-session-stream.test.js tests/tenant-startup-admission.test.js \
  tests/evaluator-consumer*.test.js tests/evaluator-control-readiness.test.js \
  tests/compose-deployment-protocol.test.js tests/multitenant-inventory.test.js \
  tests/serve-listeners.test.js tests/serve-internal-listener.test.js \
  tests/preview-socket-port-composition.test.js tests/preview-serving-status.test.js \
  tests/profile-socket-order.test.js deploy/multitenant/*.test.js --timeout 10000 --reporter dot
```

- **Result: 270 passing, 5 pending, 0 failing** (mocha), plus a node:test sub-run
  of 10 pass and 0 fail.
- The same command on the base `b70ad83f` gave 257 passing, 5 pending, 0 failing.
  The difference: 5 tests were removed with `internal-api-endpoint-config.test.js`
  and 18 were added (listener-config 5, shutdown 8, serve-internal-listener 5).
- New test files are registered in the `unit` tier. `node scripts/test-tiers.js check`
  reports 616 test files, 8 tiers, ok.
- `npm run lint`: 0 errors, 50 warnings. The base warning count was not measured.
  The new files add `security/detect-non-literal-fs-filename` warnings only.
- Single-tenant path: a dedicated `mongo:7` container (`--ulimit nofile=1048576:1048576`,
  no tmpfs) was used through `bin/with-env.js` with a copy of `tests/ci.test.env`.
  Files run: `headless-test-server`, `serve-roles`, `owner-preview`,
  `realtime-api-startup-observer`, `evaluator-preview-runtime` and
  `multitenant-preview-process.integration`. Result: **48 passing, 16 pending,
  0 failing**. An earlier run without the env file failed with `MONGODB_URI
  setting is missing`; that is a setup failure, not counted.

| Criterion | Test |
|---|---|
| Socket default, never a network bind | `internal-api-listener-config`: default `/run/nightscout/api.sock`, `$XDG_RUNTIME_DIR/nightscout/api+realtime.sock`, no `url` key |
| Overrides, exclusivity and refusals | env beats config per key. Refused: partial host/port, socket together with host/port, port 0 or 70000, relative or non-normalised socket path, a socket path over 100 bytes, a deadline over 60000, the old `endpoint` key and a `contracts` key |
| Peers | URL, socket, default. Co-resident peers resolve to the own listener. A moved own role is refused; a service-name alias on the same port is accepted. A participant whose roles resolve to two addresses is refused |
| Role code decides contracts; one listener | `serve-internal-listener`: the actual `serve.start` composes `POST /authorize, /mutate, /alarm` for `api,realtime`. Realtime's boot calls the co-resident api over the listener. External alarm delivery works. Stop unlinks the socket. A process with no contract has no listener |
| Unowned or unbound contract refuses at start-up | evaluator binding `alarm-delivery` gives `INTERNAL_API_CONTRACT_UNOWNED`, and the listener is closed again. Binding a contract the process does not serve is refused. Leaving `alarm-delivery` unbound gives `INTERNAL_API_CONTRACT_UNBOUND` |
| Held-call shutdown (UDS and loopback HTTP) | `internal-api-shutdown`: a handler released 150 ms after `close()` starts, with a 3000 ms deadline: the caller receives the response. A new caller during the drain is refused. A 200 ms deadline with the handler still held: the caller gets `SOCKET_IPC_UNAVAILABLE` at ≥180 ms, and the handler still completes. An idle connection is closed at once |

## Separated processes over Docker Compose (reproduced, `78ecba76`, dirty=0)

```bash
cd externals/work/crm-internal-listener-20261110
tests/native/internal-api-compose/run.sh --out <dir>                            # exit 0
tests/native/internal-api-compose/run.sh --out <dir> --api-shutdown-ms 500      # exit 0
tests/native/internal-api-compose/run.sh --out <dir> --control early-drop       # exit 1 (expected)
tests/native/internal-api-compose/run.sh --out <dir> --control blanket-window   # exit 1 (expected)
```

**Instrument changes.**
- `component.cjs` now uses the production `listener-config.resolve`,
  `internal-listener.open`, `bind` and `assertBound`.
- Each process gets one `serve.internal`:
  - api: `NS_SERVE_INTERNAL_HOST=0.0.0.0`, `PORT=7001`
  - evaluator: port 7003
  - tenant-admin: port 7004
  - realtime: `NS_SERVE_INTERNAL_SOCKET=/shared/realtime.sock`
- Peers come from `NS_API_INTERNAL_URL`, `NS_EVALUATOR_INTERNAL_URL`,
  `NS_TENANT_ADMIN_INTERNAL_URL` and `NS_REALTIME_INTERNAL_SOCKET`. These are
  shared by all services, including each own role, which exercises the
  service-name alias rule.
- The drain step's assertion now depends on `--api-shutdown-ms` against the
  1500 ms hold.

**Service logs** (`compose-final/service-logs.log`): one listener per process.
- api: `POST /authorize, /mutate, /cohort/status, /cohort/invalidate` on `http://0.0.0.0:7001/`
- realtime: `POST /alarm, /cohort/status, /cohort/invalidate` on `/shared/realtime.sock`
- evaluator and tenant-admin: lifecycle routes only
- every process reports `shutdownTimeoutMs` 5000

**Drain step.** The evaluator is stopped, one A call is held at the api, the api
gets SIGTERM, and the call is released after 1.5 s.

| Run | Scenario | Drain result (from `results-drain.json`) |
|---|---|---|
| `compose-final` (deadline 5000) | `SCENARIO_PASS`: baseline A 3/0, B 3/0; revoked A 0/3, B 3/0; suspended A 0/3, B 3/0, direct A `SOCKET_IPC_UNAVAILABLE`, B admitted, lifecycle status + invalidation of A on all four, each log exactly `[A]`; resumed; route ownership 503/503/503/200 | **caller received the response**: `result: admitted`, `elapsedMs` 1746. Held call `start,finish`, 29/29 window operations finished, api drain 1544 ms (`LISTENER_CLOSED` then `WINDOW_DRAINED`), exit 0. The api was still running 1.5 s after SIGTERM |
| `compose-deadline` (deadline 500) | `SCENARIO_PASS` (same counts) | **caller got `SOCKET_IPC_UNAVAILABLE` at 668 ms**, which is after the deadline and not at shutdown start. The handler still ran `start,finish`, 29/29 finished, drain 1549 ms, exit 0 |
| `compose-control-early-drop` (scratch copy, `close()` destroys every connection at start) | `SCENARIO_PASS` | **red as intended**: the caller got `SOCKET_IPC_UNAVAILABLE` at **165 ms** although a response was expected; exit 1. This matches the pre-decision finding (176 ms on `d69b873a`) |
| `compose-control-blanket` (scratch copy, listener-wide window) | **red as intended**: `DRIVER_FAILED lifecycle invalidation of suspended A on api: SOCKET_IPC_UNAVAILABLE`, exit 1 | |

Every run left 0 containers and 0 networks. Image
`node@sha256:5ec23b7c622b00547753bc6ffd78085dd868a68aeb41c8e0a1418f033e13d96d`.
The stand-ins are as in the listener-composition lane:
- the window's PostgreSQL is the recording protocol fixture;
- authority and phase come from JSON files;
- role contexts record invalidation only.

An earlier blanket-window control run on `efb58a0f` exited 1 for the wrong reason
(`MODULE_NOT_FOUND`: `run.sh` looked for `blanket-window-control.cjs`). It is not
counted; `78ecba76` fixes the file selection, and the rerun above is red for the
intended reason.

## Break-it controls on the actual source (each edited, run, restored)

Logs: `ablation-<name>.log`. After each run the file was restored with `git
checkout`, and its sha256 matched the committed hash above. Afterwards, `git
status` in the worktree reported 0 changes.

| Ablation | Test | Red symptom (exact) |
|---|---|---|
| `early-drop`: `close()` destroys every connection at start (`transport.js`) | `internal-api-shutdown` | 3 passing, 5 failing. Held-call answered (UDS and HTTP) and deadline (UDS and HTTP) fail with `SOCKET_IPC_UNAVAILABLE`. The vm control fails with its marker missing, which is the expected setup red |
| `unowned-bind`: the bind ownership check reduced to "slot exists" (`internal-listener.js`) | `serve-internal-listener` | `Missing expected rejection: INTERNAL_UNOWNED_CONTRACT_REFUSED`, plus the vm control's marker red. The mocha process then hung on the listener the mutant left open (exit 124 by `timeout`) |
| `unowned-plan`: the plan ownership check removed | `serve-internal-listener` | `plans contracts from role code only…`: `Missing expected exception.` |
| `network-default`: default changed to a `0.0.0.0:7001` bind (`listener-config.js`) | `internal-api-listener-config` | `defaults to a unix socket…`: deep-equal failure; `own role dials own listener` |
| `moved-by-peer`: the co-resident contradiction check disabled | `internal-api-listener-config` | `Missing expected exception: INTERNAL_CONTRACT_NOT_MOVED_BY_CONFIG` |

Two of these are also permanent in-file vm controls:
- the early-drop mutant must lose the held response
  (`internal-api-shutdown.test.js`);
- the bind mutant must accept a foreign binding
  (`serve-internal-listener.test.js`).

## What stays UNMEASURED

- **Real role processes** (`nightscout multitenant api|realtime|evaluator|tenant-admin`
  with PostgreSQL, Vault, socket forwarding and consumers) on the new config.
  - The Compose run uses the production listener, config and transport with
    synthetic role contexts.
  - The joined native fixtures (`tests/fixtures/realtime-preview/*`,
    `tests/fixtures/evaluator-consumers-native.js`) were updated to
    `NS_SERVE_INTERNAL_SOCKET` / `NS_API_INTERNAL_SOCKET` /
    `NS_REALTIME_INTERNAL_SOCKET`, but **not run**: they need root-supplied provisioning.
  - The `deploy/multitenant` demo was not brought up. Its config generator and
    `health.js` were updated, and `compose-deployment-protocol` passes.
- The default `/run/nightscout` with a non-root user and no `XDG_RUNTIME_DIR`
  (`mkdir` would fail with EACCES, giving exit 1). Also unmeasured: a systemd
  `RuntimeDirectory` with its default 0755 mode, which the transport's
  0700 check refuses.
- SIGTERM through the CLI's watchdog, with the deadline near `SHUTDOWN_BOUND_MS`.
- Kubernetes, replicas and HTTPS.
- Full database tiers, browser, enabled corpus and CodeQL: these run on the
  joined candidate.
- Lint warnings compared with the base.
