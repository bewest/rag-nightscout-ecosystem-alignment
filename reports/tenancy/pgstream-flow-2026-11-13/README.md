# Local pgstream clinical-to-client proof

*Contributor-facing retained measurement, 2026-11-13. Reproduced on the frozen
prototype source below. This closes a bounded local capability, not M7 production
acceptance, autonomous recovery or capacity. The [release decision](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#event-driven-reset)
owns priority; the [communication guide](../../../docs/archive/tenancy/evaluator-realtime-reference-2026-11-16.md#event-driven-target-and-first-proof)
owns the proposed architecture.*

## Result

A committed synthetic clinical change passes through maintained pgstream, the
actual clinical evaluator, durable completed output and output CDC to an
already-connected Socket.IO client. A committed settings change changes the
clinical outcome. Due clinical work runs without another write and survives an
explicit loss of evaluator/config caches and timers. Realtime does not reacquire
raw clinical inputs in this proof.

The prototype uses a separate consumer entry in the existing
`tenant_consumer_checkpoint` table. Its envelope records completed clinical
result, browser frame, input signature, settings identity, content revision and
next due instant. Input acquisition retains its separate checkpoint. HTTP success
follows the completed-output transaction. Output routing selects the completed
consumer and cannot enqueue raw-input evaluation. Clinical writes do not call
webhooks or emit notifications.

This supports keeping evaluator/materializer and realtime as two logical modules,
initially co-located for the proof. It does not make clinical state disappear:
“stateless” means caches can be discarded and reconstructed from durable state.

## Executed source and instrument

| Input | Exact attribution |
|---|---|
| Core prototype | `codex/pgstream-flow-20261113`, commit `aba583199e9ab8a4bb907adc46dc9262a3dcedf5`, tree `76631811d17c748bd50ab5a6f5ee64996c5d4983`; based on coherent core `4b13bf8bbfe578416441d7322837ec5aabeba1ea` |
| Actual modules | `lib/data/tenant-projection-evaluator.js`, its working-set browser-frame builder, PostgreSQL durable replay and restricted reader; `lib/server/realtime/protocol.js`, `socket-server.js` and actual `socket.io-client` |
| Harness | `tools/pgstream-flow/proof.js` and README at the prototype commit; dormant synthetic fixture, fixed local ports, one serialized adapter, two tenants |
| Upstream transport | pgstream **v1.6.0**, source `97d7ab464f0accf6cf1373b3c3f7b328debae4b9`; published Linux amd64 binary SHA256 `f9da5d0c299139db5236b63bdbd5cc20f6e1267db989c51d6444f429150c158b`, verified against the release checksum |
| Local database | Image `sha256:581a51cbf85d3c922bdbf01e4f1610dec8dae15f2baa25f46a9a3c73ce5dcea1`; base `postgres@sha256:5db6dac2ef5dcff512f4f00a009c3c332b9f2f28f24277175bf3e4a3d02ef83a`; actual packages PostgreSQL `16.16-1.pgdg13+1`, wal2json `2.7-1.pgdg13+2`. Installation upgraded the base minor version; this records what ran. |
| Retained evidence | Ignored `data/acceptance/pgstream-flow-20261113/`; originals include payloads, logs and runtime configuration. Do not publish raw configuration or force-add captures. Local custody is `externals/work/HANDOFF-pgstream-flow-2026-11-13.md`. |

The retained `manifest.json` SHA256 is
`549c4dcec59552b6ba0e57f6797c9a50258c2779547104e9a1c4e11a18ef5003`.
The coordinator independently rehashed every file named by that manifest with no
mismatch. Owned container and anonymous volume were removed; the coordinator's
filtered container query returned no match. Local image, source worktree and
original captures remain preserved; process checks are retained in the manifest.

The optional evaluator frame is JSON-copied and byte-bounded; default output has
no new frame field. No deployment pin or shipping role is enabled. The fixture
provides admission and settings adapters: it does not execute production identity,
revocation or lifecycle integration.

## Focused measurements and controls

All final cases use the frozen prototype and v1.6.0. Each positive run checks
input, settings, connected-client output CDC, natural due work, a newer committed
input while an older result is held, tenant isolation, explicit manual transport
restart, quiet adapter work and persisted-due cache recovery.

| Capture | Exit / measured outcome |
|---|---|
| `final-before-durable` | **0**: SIGKILL before evaluation/HTTP acknowledgement; the committed input replays and durable output reaches the client. |
| `final-after-durable` | **0**: SIGKILL after completed-output commit and before HTTP acknowledgement; replay completes durably and retains content revision and input checkpoint. The assertion waits for SQL completion and the tenant queue, not merely evaluation starting. |
| `red-early-ack` | **1**, `TIMEOUT durable clinical`: returning success without durable work is detected. |
| `red-output-drop` | **1**, `TIMEOUT connected client output CDC update`: suppressing output delivery is detected. |
| `red-due-loss` | **1**, `TIMEOUT cache-loss recovered due without write`: omitting due reconstruction is detected. |
| `red-rls-disabled` | **1**, `A-bound actual reader cannot see B rows`, actual `1 !== 0`: disabling row-level security exposes the seeded foreign row and is detected. |

Positive isolation checks require the actual tenant-bound reader to hide the
other tenant's stored rows, reject a foreign evaluator binding and keep that
other tenant's reading out of the first tenant's output/client frames. This is
not full authority acceptance. The newer-generation check proves retention under
one adapter's serialization, not competing-owner fencing.

The quiet observation is **300 ms** with no increase in adapter evaluation,
output or Node PostgreSQL query counters. It does not instrument pgstream's own
SQL, establish a long idle baseline or measure scaling. Slot observations report
`wal2json`, `max_slot_wal_keep_size=64MB` and `wal_status=reserved`; exceeding that
bound, invalidation and rebootstrap were not tested.

Focused source tests: `./node_modules/.bin/mocha tests/tenant-projection-evaluator.test.js tests/evaluator-due.test.js`
reports **17 passing**, including default output compatibility and optional-frame
selection. Full application/browser/corpus acceptance and final prcheck were
**skipped**: this is a dormant prototype, not a release-ready application fix.

## Material findings and remaining boundary

1. **Use the repaired maintained artifact.** Exploratory v1.5.0 captures `h`, `i`
   and `j` retain replay failures, including a failed input with no completed
   output after restart. Their helper evolved uncommitted and has no captured
   exact source hash, so they are diagnostic observations, not frozen paired
   acceptance. Upstream [v1.6.0](https://github.com/xataio/pgstream/releases/tag/v1.6.0)
   explicitly repairs acknowledgement positions running ahead of WAL. Final
   v1.6.0 controls above establish their own scope; this is not a matched
   performance or exhaustive transport comparison.
2. **Notifier liveness remains open.** Both final positives observe strict-mode
   notifier failure while `processExited=false`. Recovery is explicitly triggered
   stop/restart. Read-derived mechanism: upstream `pkg/stream/stream.go` runs
   `Notify` in a goroutine that logs its error without immediately cancelling the
   parent. Process existence alone is insufficient health evidence. No automatic
   restart or bounded autonomous recovery is claimed.
3. **Schema events need an explicit boundary.** The deliberate RLS alteration
   also produced a `pgstream.ddl` action `M` despite DML subscriptions; the
   adapter refused it with `NO_TENANT`. The control's decisive failure is the
   independent foreign-row assertion. Normal flow has no post-start DDL. Schema
   and control-event routing remain integration work.
4. **Recovery scope is bounded.** Due reconstruction clears caches/timers within
   the harness, rather than killing the adapter OS process. Actual adapter
   restart, overlapping-owner/restore generations, pause/suspend/revocation,
   durable producer/suppression dispatch and WAL-cap recovery remain unmeasured.
   Persisted clinical requests are not provider delivery or exactly-once effects.

The next owner remains the same capability lane under the sole M7 coordinator.
Integrate the adapter with existing role/lifecycle and generation fences, establish
notifier health/recovery and schema-event routing, then prove actual process-loss
recovery. Keep the small proof as the discriminator. No paid host, old capacity
retry, broad acceptance campaign or benchmark is authorized by these results.

## Reproduce the focused cases

Use the prototype README to prepare an isolated disposable database with
wal2json, logical replication and bounded retention, plus the checksum-verified
binary. Credentials come from the environment. Each invocation provisions its
own synthetic schemas and cleans its slot; run serially.

```bash
export NS_TEST_POSTGRES_ADMIN_URI
export PGSTREAM_BINARY
export PGSTREAM_FLOW_EVIDENCE
node tools/pgstream-flow/proof.js
```

Use `PGSTREAM_FLOW_CRASH=before-durable` for the other positive. The four red
variants are `PGSTREAM_FLOW_ABLATE=early-ack`, `drop-output`, `drop-due-recovery`
and `disable-rls`; see the pinned README for their exact invocation contract.
