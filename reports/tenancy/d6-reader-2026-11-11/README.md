# D6 metadata reader and consumer signalling — focused acceptance

*Contributor-facing measurement record, captured 2026-11-11 (America/Los_Angeles).
Synthetic fixtures only. This records focused local capability evidence; capacity,
joined programme acceptance and deployment qualification remain separate.*

The optional D6 source is implemented on core `419af9b1f6dd59d0000f113a886db51fa4fdc6d1`,
branch `codex/d6-reader-capability-20261112`. Original history contains implementation
`a24f741c`, merge `51e09ea1` of coordinator `f3a18445`, then the native/watchdog repair.
The merged source retains registry step A and authorization changes. Source contract:
core `docs/d6-change-feed.md`; deployment helper: `lib/change-feed/postgres.provision`.

## Implemented boundary

- Dedicated `multitenant feed-reader` role, outside serving processes and tenant
  operation cohorts. An EXECUTE-only non-replication login calls fixed-slot wrappers
  owned by an exact NOLOGIN/NOSUPERUSER/NOBYPASSRLS/REPLICATION identity.
- Reviewed operational function catalogue, pinned for restore census. Wrapper body,
  owner, result/security/config/grants, publication table/filter/DML shape, slot and
  finite resource settings are checked. NULL numeric arguments refuse.
- Metadata-only `pgoutput` decoder for the write clock and activity table. Complete
  committed transactions produce coalesced tenant hints. Notification commit precedes
  slot acknowledgement; unsafe/oversize/incomplete batches do not acknowledge.
- SQL-session loss reconnects with the same safety checks. LISTEN commits before
  reconciliation. Reader/listener loss and new generation enter visible degraded
  recovery. Healthy and degraded recovery both use fixed page budgets.
- Realtime detects the hinted tenants, with separate bounded cold/retry work.
  Evaluator recovery accepts a subset, retains clinical due timers and separate
  per-tenant evaluation-gap deadlines. Delivery recovery is paged in feed mode;
  active retry work uses tracked active tenants.
- Activity hints are independent of data writes. Existing pause/suspend control
  semantics remain: read/socket/evaluator work stops, pause permits uploads, suspend
  refuses uploads, resumption reacquires. `changeFeed` requires an activity reader.

## Reproduced checks

| Check | Command / artifact | Verdict and scope |
|---|---|---|
| Native source and real CLI | `NS_D6_FEED_TEST=1 MULTITENANT_STATIC_TENANTS=lab node node_modules/mocha/bin/mocha.js --timeout 30000 tests/change-feed.integration.test.js --reporter spec`; [output](d6-native-419af9b1.log) | **8 passing**, 0 failing on exact clean `419af9b1`. One owned PG16.15 container on random loopback port, removed afterward. Covers EXECUTE-only/RLS behavior, notify/ACK loss, reader outage, listener reconnect, actual backend termination during notification COMMIT, activity without data writes, B progress, pin tampering, oversized transaction refusal and real CLI boot/SIGTERM. |
| Focused runtime/composition | `node node_modules/mocha/bin/mocha.js --timeout 10000 tests/change-feed.test.js tests/realtime-publish-on-change.test.js tests/evaluator-preview-runtime.test.js tests/evaluator-runtime-content.test.js tests/realtime-config-cache.test.js tests/socket-admission-cache.test.js tests/evaluator-consumers.test.js tests/evaluator-consumer-open-order.test.js tests/registry-config.test.js tests/registry-realtime.test.js tests/serve-roles.test.js tests/serve-listeners.test.js tests/serve-internal-listener.test.js tests/tenant-operations.test.js --reporter dot`; [output](d6-focused-419af9b1.log) | **164 passing**, 0 failing on exact clean `419af9b1`. Synthetic projection/config/runtime fixtures; not whole clinical corpus or a real-role restore campaign. |
| Changed-source lint | [output](d6-final-lint.log) | 0 errors; two existing non-literal stat warnings in config readers. |
| Tier inventory | `node scripts/test-tiers.js check` | 679 test files, 8 tiers, OK. |
| No writer NOTIFY | `node scripts/check-no-trigger-notify.js` | 13 trigger bodies, 2 trigger functions, zero notifying functions, OK. Existing no-trigger control retained. |
| Enabled multitenant inventory | `node scripts/test-multitenant.js --list`; [output](d6-inventory-419af9b1.log) | 73 opt-in suites, 73 inventory entries. D6 plus missing joined API-roster and registry-human entries have their actual flags and resource ownership. This lists/selects; it does not execute the full corpus. |

## Meaningful red/restored controls

[Machine-readable verdicts](d6-controls.json) and individual logs preserve four
actual source mutations in the lane's own worktree, each restored byte-for-byte:

| Mutation | Observed semantic red |
|---|---|
| Advance before notification | `D6_NO_ACK_BEFORE_NOTIFY`: confirmed slot position moved despite a refused notification. [Output](d6-control-ack-before-notify.log). |
| Disable recovery pages | `D6_READER_OUTAGE_BACKSTOP`: persisted B update stayed absent from observed current state with reader stopped. [Output](d6-control-backstop-disabled.log). |
| Suppress activity hints | `D6_ACTIVITY_HINT_NOT_A_DATA_WRITE`: pause transition emitted no activity hint despite unchanged data clock. [Output](d6-control-activity-hints-disabled.log). |
| Detect every tenant after one hint | `D6_TARGETED_HINT_ONLY`: detection received A and B instead of A. [Output](d6-control-full-roster-on-hint.log). |

Controls executed on merge `51e09ea1` plus the working candidate later committed
as `419af9b1`. The four mutated implementation files match their final versions;
subsequent changes concerned watchdog deadlines, documentation and extra inventory.
The exact-head native and focused runs above establish the restored final state.
Controls are semantic failures, not setup or permission failures.

## Preserved failures and limits

Initial focused listener runs hit sandbox `EPERM`; the restored focused run above
had listener/subprocess access. Initial native instrumentation omitted the startup
statement timeout from its raw-client control, so the first test stopped before
seeding and later cases lacked rows. That setup was repaired. The CLI readiness
probe originally observed its backend before shutdown handlers were installed;
source now emits `feed-reader started` only after the handlers are present.

The [earlier native discriminator](../d6-native-discriminators-2026-11-11/README.md)
remains the source for transaction-sized SQL overshoot. Wrapper message/byte limits
are **post-decode**. Spill settings, finite retained WAL, server statement timeout
and reader RSS soft refusal are distinct limits; none establishes a hard total
shared-server RSS guarantee. An oversized transaction can hold the reader degraded
until explicit operator recovery. There is no silent skip/reset.

UNMEASURED: 1k/3k latency/cost on the joined deployment, capacity, real clinical
alarm equivalence under D6, full restore/epoch campaign with a live reader, sustained
WAL-loss/retention fault campaign, shared-server resource envelope and deployment
cgroup qualification. Existing focused clinical/authority tests passed within their
fixture scope. Root owns deployment binding and final frozen-candidate campaign.

The normal page sweep must be sized consistently with the existing evaluation-gap
alert deadline. Derived scheduling examples at 1-second intervals: 3k/64 requires
47 intervals; 10k/64 requires 157; 10k/256 requires 40. These are arithmetic queue
coverage bounds, not end-to-end latency measurements. Do not weaken the clinical
watchdog to hide slow recovery.
