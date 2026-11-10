# Private listener composition and per-operation rules — 2026-11-10

`MT-ENDPOINT-TRANSPORT` (remaining scope), application lane
`codex/listener-composition-20261110`. Composition, per-operation bounds and
per-module lifetime are **fixed on a local branch** with reproduced focused
evidence. A separated-process run over a Docker Compose network was executed with
the production transport and lifecycle handlers. Real API/realtime/evaluator role
processes were **not** run over Compose (see [what blocked it](#what-stays-unmeasured)).
Nothing was pushed.

## Anchors

| Anchor | Value (from `git rev-parse` at writing) |
|---|---|
| Lane commit | `d69b873aa93044ed90c004ba79491eb49e25405a` |
| Lane base | `692bd5078f2fa26b6e0a31a2bf7429f2dd453aae` (docs on `3a534e89`, on `dc795bd1`) |
| #8898 candidate head | `official/workspace/multitenant-20261102` = `dc795bd1515f11808a8d0732f2be9925cb2ffcd1` |
| Fetched `official/dev` | `4a482627bfdafb1fef8dcbe0ac6c484811cae563` |
| Alignment main at writing | `3259787103b8a8d5a6ed4b193422dc868b127602` |
| Committed `transport.js` sha256 | `9fb0ea5588260170734536d8bb8c1083b56909f5aa95ccf9653d3970d4e28119` |

## What changed (read-derived from the diff)

- `transport.compose(endpoint, modules)`: one private listener for an explicit
  list of `{service, create, lifetime?}` modules. Routes are a fixed table keyed by
  `(method, path)`. A duplicate route (within or across services) refuses with
  `INTERNAL_API_ROUTE_DUPLICATE`, a duplicate service with
  `INTERNAL_API_SERVICE_DUPLICATE`, before any endpoint is published. Dispatch
  requires the service/version headers to name the route's owner; a co-resident or
  unregistered service is refused (`503 SOCKET_IPC_UNAVAILABLE`), no handler runs.
  Each module gets its own transport token.
- Lifetime is per module. Application modules carry `{operationWindow, resolveTenant}`;
  the lifecycle module carries none. No listener-wide window is offered.
- Operations may declare `method` (POST only), `contentType` (application/json
  only), `maxBytes`, `timeoutMs`. Per-operation bounds only tighten the endpoint
  bounds and apply at listener and client. Both ends check the operation media
  type (request accepts `; charset=utf-8`); the client no longer accepts any media
  type merely prefixed `application/json`.
- `transport.open` is the one-module form; role wiring is unchanged (one listener
  per contract). `operation-cohort` exports `controlOperations(cohort)`, the
  unchanged lifecycle handlers, so a composed listener can reuse them.

**Compatibility.** No internal path, header or schema changed; checked-in contracts
declare none of the optional fields. Peers on `dc795bd1` and on this lane
interoperate on the wire. One client-side tightening: a response whose media type
is `application/json`-prefixed but different (for example `application/json-seq`)
is now refused; current listeners send exactly `application/json`. No migration
note is required for deployments.

## Focused checks (reproduced on clean `d69b873a`)

```bash
node_modules/.bin/mocha tests/internal-api-*.test.js tests/realtime*.test.js \
  tests/operation-cohort*.test.js tests/profile-wire-response.test.js \
  tests/human-session-stream.test.js tests/tenant-startup-admission.test.js \
  tests/evaluator-consumer*.test.js tests/evaluator-control-readiness.test.js \
  tests/compose-deployment-protocol.test.js tests/multitenant-inventory.test.js \
  tests/serve-listeners.test.js --timeout 10000 --reporter dot
```

Result: **244 passing, 5 pending, 0 failing** (the prior lane's command without
`serve-listeners`: 204/5). `tests/internal-api-composition.test.js` alone: **19
passing**. `node scripts/test-tiers.js check`: 610 files, 8 tiers, ok. ESLint on
changed/new files: 0 errors; warnings on changed lib files equal the base
(`transport.js` 15/15, `operation-cohort.js` 0/0). `git diff --check` passes.

| Criterion | Focused test (actual UDS and loopback HTTP listeners) |
|---|---|
| 1 Composition | socket-authority + lifecycle-participant on one listener; `routes` equals the four exact routes; both named clients succeed; foreign co-resident service, unregistered service (`alarm-delivery`) and GET refused with no handler call; duplicate route / duplicate service refuse with no socket file or port bound. |
| 2 Per-operation | 64-byte / 80 ms operation under a 1024-byte / 600 ms listener: oversized request and response refused at both ends while a sibling operation accepts the same bytes; deadline fires before a 300 ms handler while the sibling completes; wrong request media types refused; client refuses `application/json-seq` from an independent peer. Public port: the existing production `preview-api` isolation test now derives its 404 path list from the contracts. |
| 3 Lifetime | Actual `operation-window` over the recording PG protocol fixture and actual `operation-cohort` control handlers, composed with an application module: with A's phase `suspended`, A application call refuses and its handler does not run, B is admitted, lifecycle status and invalidation of A succeed and only A is invalidated (UDS and HTTP). A held A response keeps `window.close()` waiting (registered, unfinished) while status stays callable; release completes it and marks the operation finished. |

### Controls (break the source, observe red, restore)

Each ablation edited the actual `lib/server/internal-api/transport.js`, ran the
composition file, and restored it; restored sha256 equals the committed hash above.
Logs: `ablation-<name>.log`. In-file vm mutant controls repeat the first, second,
third and fifth as permanent tests.

| Ablation | Red symptom (exact) |
|---|---|
| remove the duplicate-route check | UDS and HTTP duplicate tests: `Missing expected rejection.` |
| remove the route-owner service fence | `foreign co-resident service` (actual 200, expected 503), UDS and HTTP |
| replace operation bounds with listener bounds | `request above operation bound` (200 vs 503); deadline test `Missing expected rejection.` |
| skip the media-type check | `text/plain` (200 vs 503) |
| listener-wide (blanket) window for tenant-bearing requests | `lifecycle invalidation of suspended A must stay callable: SOCKET_IPC_UNAVAILABLE` (UDS and HTTP); lifecycle status assertion before it still passes |

The vm-control tests themselves go red under each source ablation with `Mutation
marker must match actual transport source` (the marker is already removed); that
is the expected setup red, not a semantic result.

## Separated processes over Docker Compose

```bash
cd externals/work/crm-listener-composition-20261110
tests/native/internal-api-compose/run.sh --out <dir>                          # exit 0
tests/native/internal-api-compose/run.sh --out <dir> --control blanket-window # exit 1 (expected)
```

Image `node@sha256:5ec23b7c622b00547753bc6ffd78085dd868a68aeb41c8e0a1418f033e13d96d`
(Node v22.23.4), worktree mounted read-only, host UID/GID, internal Compose network,
no published ports. Endpoints parsed by the production `endpoint-config` from env
references. Bound (from service logs): api `http://api:7001` bind `0.0.0.0` routes
`POST /authorize, /mutate, /cohort/status, /cohort/invalidate`; realtime
`/shared/realtime.sock` (shared 0700 bind mount) routes `POST /alarm,
/cohort/status, /cohort/invalidate`; evaluator `http://evaluator:7003` and
tenant-admin `http://tenant-admin:7004` lifecycle only. Evaluator delivers an alarm
for A and B every cycle over UDS; realtime asks the API over HTTP for current
authority on every delivery. Final run on clean `d69b873a` (`compose-final/`):

| Phase | A (ok/refused) | B (ok/refused) | Other observations |
|---|---|---|---|
| baseline | 3/0 | 3/0 | |
| A revoked at the API decision store | 0/3 | 3/0 | next delivery after the change refuses: no cached authority in realtime |
| A suspended (phase row) | 0/3 | 3/0 | driver→API direct: A `SOCKET_IPC_UNAVAILABLE`, B admitted; status + invalidation of A succeed on all four participants by their own endpoints; each participant's invalidation log is exactly `[A]` |
| resumed | 3/0 | 3/0 | |
| route ownership on the network | | | API `/cohort/status` named `socket-authority`: 503; API `/alarm`: 503; realtime `/cohort/status` named `alarm-delivery`: 503; realtime lifecycle: 200 |
| drain (evaluator stopped, one held A call, SIGTERM api) | | | api still running 1.5 s after SIGTERM, no `WINDOW_DRAINED`; after release: held call `start,finish`, all 29 window operations finished, drain 1535 ms, exit 0 |

**Finding (reproduced, current behaviour):** on SIGTERM the transport's `close()`
destroys in-flight connections at shutdown start. The held caller received
`SOCKET_IPC_UNAVAILABLE` after 176 ms, before its handler finished; the server
still drained the handler and window. The outcome is reported to the caller as
uncertain with no retry, consistent with the documented no-retry contract. A
graceful "deliver held responses before closing" mode does not exist; whether one
is wanted is a design question for the replica/drain owner, not changed here.

Control (`compose-control/`, scratch source copy with the blanket-window mutant):
exit 1, `DRIVER_FAILED lifecycle invalidation of suspended A on api:
SOCKET_IPC_UNAVAILABLE`. Both runs left 0 containers and 0 networks.

Instrument stand-ins, labelled in `component.cjs`: the window's PostgreSQL is the
recording protocol fixture whose tenant phase is read from a shared JSON file on
every query; the API's authority decision is a shared JSON file read per call;
role contexts record invalidation only.

## What stays UNMEASURED

- **Real role processes over Compose.** `nightscout multitenant api|realtime|evaluator`
  with PostgreSQL, Vault, socket forwarding, realtime alarm/checkpoint stores and
  evaluator consumers were not run on a Compose network. Blocker: no in-tree
  provisioning composes all three roles; the joined native phases in
  `tests/fixtures/realtime-preview/README.md` depend on root-supplied provisioning
  and configs, and the operation window has no in-tree native PostgreSQL
  provisioning (only protocol fixtures). Current authority, response drain and
  tenant-local invalidation over the network are therefore measured with the
  production transport and lifecycle handlers but synthetic authority, phase and
  role contexts.
- PostgreSQL advisory-lock suspension across processes; Vault; clinical data paths.
- Production role wiring onto a shared component listener (needs a config shape
  naming the shared endpoint and a boot order registering every module before
  binding — a decision boundary, not implemented).
- Direct HTTPS, a bearer protocol, GET metrics/readiness routes (out of scope;
  follow-ups for the operational module), Kubernetes manifests, fixed-roster replicas.
- Full database tiers, browser, enabled corpus and CodeQL for this commit: run on
  the coherent joined candidate, not on this leaf.

## Affected tier (reproduced, clean `d69b873a`, 2026-11-10)

```bash
npm run bundle   # production bundle for this tree
TEST_ENV_FILE=<copy of tests/ci.test.env with CUSTOMCONNSTR_mongo=mongodb://127.0.0.1:27627/testdb> npm run test:affected
```

MongoDB: lane-owned `ns-lc-mongo`, `mongo:8.0.34`, `--ulimit nofile=1048576:1048576`.
Selector: 270 of 610 tests implicated (depth 4); tiers unit 58, dom 3, dependency 6,
harness 1, integration 162, stress 1, browser 36 files. Result: **exit 0, 4240
passing, 164 pending, 0 failing** (`affected-tier.log`). Pending are named opt-in
suites (disposable PostgreSQL/Vault/Docker gates) that did not execute.

Earlier attempts were setup failures, not semantic results, and are not counted:
the default `127.0.0.1:27017` is MongoDB 3.6.8, refused by driver 7.7 (wire 6 < 9);
a `--tmpfs` container and then a container without a raised `nofile` limit both
aborted (`Too many open files`, WiredTiger panic, exit 139) mid integration tier;
one run used a development bundle, which turns the production bundle-budget and
D3 source-map checks red.
