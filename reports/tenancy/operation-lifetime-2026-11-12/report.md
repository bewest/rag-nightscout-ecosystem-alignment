# Bounded worker lifetime-session evidence

Captured 2026-11-12. Product and native/focused instruments:
`e896245ead0454bc6e649b8873f7c9498a814850`; parent
`fae4a925abf4acf025e4ee3e3c53f028d2e7b3db`. Immutable focused measurement;
no capacity envelope, comprehensive acceptance, push or release claim.

Captured outputs (terminal blank lines normalized): [native](native.txt),
[focused](focused.txt), [tiers](tiers.txt), [lint](lint.txt).

## Capability and boundary

The optional `leaseSessions` operation configuration integer selects bounded
worker-owned lifetime sessions, no greater than the existing operation physical
pool maximum. Unset preserves the original path. Tenant assignment is stable
SHA-256 modulo the explicit count; lanes open lazily. The existing connection
wait budget bounds queue waiting. Only short registration/admission/completion
sections serialize; response/provider bodies and clinical SQL use their existing
independent lifetimes and transactions. No new clinical write-concurrency cap
or per-write index is introduced.

The existing marker INSERT/finished UPDATE, full admission, transaction tenant
binding, generation checks and session shared advisory lease remain intact.
PostgreSQL marker RLS still requires the same backend PID and birth. Owner loss
or ambiguous completion invalidates associated active scopes, poisons that lane,
and does not silently reconnect or finish orphan markers. Restore cannot infer
completion from lock absence. No schema/RLS/census exception was introduced.

## Reproduced focused results

| command | result |
|---|---|
| `NS_OPERATION_LIFETIME_DOCKER_TEST=1 ./node_modules/.bin/mocha tests/operation-lifetime-discriminator.integration.test.js --reporter spec` | 15 passing |
| `./node_modules/.bin/mocha tests/lifetime-sessions.test.js tests/tenant-operation-window.test.js tests/tenant-operation-window-readiness.test.js tests/operation-cohort.test.js tests/pool-config.test.js tests/fixed-roster-config.test.js tests/multitenant-config-bound.test.js tests/registry-config.test.js tests/operation-cohort-peers.test.js --reporter dot` | 118 passing |
| `node scripts/test-tiers.js check` | 689 test files, 8 tiers, okay |
| ESLint affected source and test files | zero errors, three existing fixture filesystem warnings |
| `git diff --check` before source commit | exit 0 |

Native resources are uniquely owned disposable PostgreSQL/Vault containers and
volumes; cleanup output accompanies the capture. Actual API CLI processes use
the real parsed `leaseSessions` configuration, real SQL and private HTTP
transport. Non-API peers are synthetic lifecycle status/invalidation
participants, as in the previously accepted API fixture. This is not full
all-role deployment acceptance.

## Safety and meaningful controls

- At each selected count 1, 2 and 4, actual API writes exceed that lane count
  while all postcommit wire responses stay held. Actual A restore suspends but
  cannot enter its data callback until every response releases. B continues on
  the same worker and the other worker.
- Current permission revocation takes effect on the next request on both
  replicas; wrong-tenant credentials refuse and B remains available.
- A deliberate early lifetime-completion control leaves the actual response
  held but lets restore enter. The exact held-response exclusion assertion goes
  red; the test explicitly observes that assertion failure. This proves the
  safety oracle detects the missing lifetime rather than merely waiting for SQL.
- Killing the actual lease backend closes the outstanding postcommit wire
  response. The unfinished marker survives worker replacement with the same
  participant ID and prevents restore data entry. A remains suspended after the
  drain timeout; B serves on the replacement and other worker. Replacement
  readiness explicitly selects B while A's suspended refusal stays required.
- Lost registration COMMIT reply is simulated only after the real database
  commit. The body never enters, the durable orphan remains, and a replacement
  backend cannot finish it: the native UPDATE affects zero rows under existing
  PID/birth RLS. Actual maintenance refuses the orphan.
- Lost finish COMMIT reply reports failure and poisons the owner session without
  rewriting the database's committed finished result. A fresh owner can perform
  new work when no unfinished marker remains.
- A queued registration expires while another short transaction is held. It
  never later executes SQL or enters its body, creates no marker, and does not
  poison the healthy owner. A deliberate fresh retry succeeds.
- The lifetime identity remains metadata-only for census. Adding clock UPDATE
  authority makes actual restore refuse `RESTORE_COHORT_UNKNOWN_BACKEND` before
  data entry; removing that grant restores the supported capability boundary.
- Unit controls check physical bounds, stable assignment, deadline cancellation,
  owner-loss fanout, no silent replacement, and the strict configuration range.

## Mechanism timing, not capacity

Identical full admission and marker paths ran 128 operations at concurrency 16,
with 25 percent of bodies held 20 milliseconds. The host was not isolated.

| selected lanes | observed physical backends | operations/second | entry p95 ms | completion p95 ms |
|---|---|---|---|---|
| 1 | 1 | 151.97 | 65.06 | 113.90 |
| 2 | 2 | 241.69 | 47.71 | 83.19 |
| 4 | 4 | 343.91 | 42.90 | 63.07 |

This discriminates a material serialized bottleneck and supports exposing a
bounded explicit count rather than silently adopting one backend. It is not a
speedup against an equivalent old deployment or a throughput guarantee. The
first two native timing cases deliberately retain an original empty-body path
and a raw marker-only path; their unequal work makes them unsuitable for such
a claim. The coordinator may select four provisionally and must measure the
coherent deployment, including hot-tenant distribution, before capacity claims.

## Failed observations preserved

The first actual API capture was three mechanism passes and three actual
failures: authored POST payloads omitted the existing required `app` field and
all returned 400. The independent stored-write oracle stayed red. Adding the
required synthetic field repaired the instrument; endpoint, count and oracle
were preserved. No lower request count or fake storage expectation was used.

The next capture was eight passes and one replacement-helper failure: readiness
hardcoded anonymous A403 while A was correctly suspended503 after owner death.
The helper now accepts an explicit fixture readiness tenant B; the actual
A-suspension, orphan and restore-no-entry assertions remain mandatory.

An initial shared-client prototype emitted MaxListeners warnings from one raw
error listener per operation. It now uses one backend listener and explicit
active-scope subscribers; warnings were not suppressed. An early focused
sandbox run hit listener EPERM; the elevated focused run above passed. Local
failed captures and resource attribution remain in the evolving lane handoff.

## Next integration boundary

The coordinator merges this original source history with the rest of M7,
selects the explicit deployment count, and freezes a coherent candidate for
full/browser/enabled-corpus and capacity acceptance. Those campaigns are
UNMEASURED here. Pure Ed25519 signature-proof reuse with fresh current
key/claims/authority/expiry is a separate remaining authorization reduction.
The isolated alignment evidence checkout still lacks the external worktrees
named by programme gates; its previously measured queue-validation prerequisite
failure was not masked or rerun as a new product acceptance claim.
