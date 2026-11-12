# Opt-in M7 diagnostics focused evidence

Captured 2026-11-12. Product and all diagnostic/control instruments:
`e30871ec27dcb43f6184bd89aa8f8a4267020f94`, parent
`623181b7c07586f72cffcaaec716983863cdf28c`. Control instrument
`scripts/test-m7-diagnostics-controls.js` SHA-256:
`6dc1b7e6076acfadb9a555b73e4098420a65b8bd3d12781f59265430b061a17a`.
No push, release, comprehensive acceptance or capacity claim.

Captures normalize trailing/terminal whitespace and the local product checkout
prefix only: [native](native.txt), [focused](focused.txt),
[native controls](native-controls.txt), [unit controls](controls.txt),
[tiers](tiers.txt), [lint](lint.txt).

## Completed capability

`NS_M7_DIAGNOSTICS=1` selects process/role aggregate JSON log snapshots, default
five seconds; `NS_M7_DIAGNOSTICS_INTERVAL_MS` accepts 1000..60000. Default OFF
creates no worker, timer, clock reads or pool/client/async function wrappers.
There is no new HTTP endpoint, schema, SQL, authority cache or credential policy.

The normal PostgreSQL connection foundation, raw lifetime pool, raw membership
pool and raw registry provisioning pool have constructor-only observation hooks.
Public total/idle/waiting counts are read directly; checkedout is total minus
idle. Observed outstanding client.query calls are separate from held clients.
They include client-side query queueing and are not pg_stat_activity state.
Query instances/custom submitters and config-owned callbacks are untouched and
mark SQL coverage UNMEASURED. Direct pg.Client use, including the feed reader,
is explicitly outside pool coverage and UNMEASURED.

Fixed gauges distinguish shared worker lease handles, queued critical-section
cells, active critical sections and outer body/response lifetimes. Admission,
registration, API authorization, realtime RPC/private authorization and marker
completion have separate fixed histograms. Body-response and completion timers
are inclusive; admission is a registration subspan. Independent overlapping
histograms have no request-level pairing: do not subtract percentiles or sum
nested spans to infer exclusive cost or causal order.

Resource bounds are 64 tracked pools, 13 buckets per fixed stage, and one
transferred output buffer no larger than 8 KiB. Only selected source role names
and process PID are labels. No tenant, token, request/socket ID, URL, SQL or error
text is retained in snapshots. Overflow, unsupported forms and missing/zero
observations are UNMEASURED. Closed pools leave the registry.

The selected sink uses one unref'd worker, empty environment and no inherited
application preloads. Busy/backpressured stdout drops snapshots instead of
queuing JSON. Raw output failures/partial writes/EPIPE mark missing telemetry;
the sink never wraps or closes application stdout. Shutdown does not await
logging or promise a final flush. Enabled diagnostics add fixed per-process
work/thread overhead; no zero-overhead or performance claim is made.

## Reproduced acceptance and controls

| command | result |
|---|---|
| `NS_M7_DIAGNOSTICS_DOCKER_TEST=1 ./node_modules/.bin/mocha tests/m7-diagnostics.integration.test.js --reporter spec` | 3 passing |
| `./node_modules/.bin/mocha tests/m7-diagnostics.test.js tests/m7-diagnostics-output.test.js tests/postgres-connection.test.js tests/postgres-connection-failure.test.js tests/pool-membership.test.js tests/provisioning-private.test.js tests/lifetime-sessions.test.js tests/tenant-operation-window.test.js tests/tenant-operation-window-readiness.test.js tests/operation-cohort.test.js tests/realtime-api-client.test.js --reporter dot` | 121 passing, 10 pending |
| `node scripts/test-m7-diagnostics-controls.js --native` | both actual-pool/actual-response ablations go red |
| `node scripts/test-m7-diagnostics-controls.js` | both unit gauge ablations go red |
| `node scripts/test-tiers.js check` | 693 test files, 8 tiers, okay |
| ESLint affected source, fixtures and instruments | zero errors, three existing private-transport/regex warnings |
| `git diff --check` before source commit | exit 0 |

The ten pending cases are the existing transaction-foundation opt-ins requiring
`NS_TEST_POSTGRES_ADMIN_URI`; no shared database was borrowed to enable them.
The coordinator owns their joined native/full-corpus acceptance. Real constructor
coverage is also exercised by the owned native API and pool checks above.

Native tests create owned disposable PostgreSQL/Vault and two actual API CLI
workers with real private lifecycle transports. Other required lifecycle peers
remain synthetic status/invalidation participants. Resource cleanup output is
captured. A real max-one pool holds a client while another acquisition waits:
checkedout=1, waiting=1, outstanding SQL=0. Releasing it populates acquisition-wait
histograms. Actual pg_sleep makes outstanding SQL=1, then completion restores
idle=1/checkedout=0/SQL=0. PostgreSQL error results retain their code.

Actual ON/OFF API runs persist the same synthetic SGV value, preserve write and
wrong-tenant status, keep B available and exclude restore data while A's actual
postcommit wire response is held. With diagnostics selected, the fresh controlled
snapshot shows an outer body and lease handle, checked-out lifetime client,
measured SQL coverage and zero outstanding SQL. After release, the inclusive body
and completion observations advance. The same source executes both selections.

Unit/owned-child tests additionally preserve result/error identity, callback
`this`, Promise semantics and unknown Query objects without double-counting SQL.
They prove no disabled clock/sink/wrapper, fixed pool/output bounds, actual EPIPE
and stdout backpressure drops, unchanged application stdout after sink shutdown,
and process exit without waiting for the unref worker/timer. No actual partial
kernel-write scenario is claimed; the worker's short-write refusal is source
handling, while failure callbacks and EPIPE are exercised.

The native ablation reports checkedout=0 despite a real held client; its exact
oracle fails `0 !== 1`. Omitting the outer-body gauge makes the actual held-response
snapshot oracle fail readiness. Unit counterparts independently fail as well.
Each source variant is compiled only in owned child preloads; the working tree
and remote harness are never mutated. Owned resources still clean up after the
intentional assertion failures.

## Substantive failed observation

The initial native run was two passes and one authored timing-oracle failure:
a periodic one-second snapshot was incorrectly treated as proof that a body had
been held at least 900 milliseconds. It need not be. The corrected instrument
holds the same explicit 1100 milliseconds ON/OFF, excludes startup snapshots,
and preserves the original SQL/body/restore/B/authority expectations. The final
capture above passes; no runtime authority, clinical result or latency threshold
was weakened. Failed local output remains in the evolving lane handoff.

## Credential-profile boundary (read-derived)

At source623 there is no supported non-OIDC ordinary Ed25519 DATA-session issuing
API found. `lib/server/serve/preview-api.js:60` composes verification only;
`owner-credential-runtime.js:32` permits issue-legacy;
`lib/management-sessions/component.js:13` fixes management purpose. Human DATA
issuance follows verified OIDC identity/session transactions in
`lib/human-session/engine.js:110`. Its signing primitive is not a non-OIDC
provisioning adapter. `access-tokens.md:35` documents operator-prepared state.

The actual API verifier fixture explicitly seeds access credentials/sessions
(`tests/fixtures/multitenant-preview-replicas.js:315`) and signs local DATA JWTs
through Vault (`:219`). That proves verifier/current-authority behavior, not a
supported provisioning API. The old performance baseline uses legacy/Vault and
cannot inherit the local Ed25519 proof result. Future profiles must record their
credential producer/mode explicitly; diagnostics aggregate process/role only.
No new DATA issuer was added by this lane.

## Integration boundary

The coordinator owns original-history integration with realtime sharding and
other prepared changes, then one frozen full/browser/enabled-corpus/capacity
campaign. Those are UNMEASURED here. Existing remote old-source profiles were not
modified mid-run; absent diagnostics mean UNMEASURED, not zero waits or zero SQL.
The isolated alignment evidence checkout retains its previously reported missing
external gate-worktree prerequisite; no queue state or gate was changed.
