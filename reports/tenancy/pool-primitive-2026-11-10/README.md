# Pool-membership primitive (MT-POOL-PRIMITIVE), 2026-11-10

*Contributor-facing evidence record for lane P. Captured 2026-11-10; not edited after capture.
Decisions implemented: [evaluator-static-partition](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#evaluator-static-partition)
and [pool-primitive-shared](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#pool-primitive-shared).*

## Anchors

| tree | commit |
|---|---|
| base: #8898 head, `official/workspace/multitenant-20261102` | `16a1fc2d45e59602eb6ec3e3bf6f506f35bcc5b1` |
| lane branch `codex/pool-primitive-20261110` (worktree `externals/work/crm-pool-primitive-20261110`, local, unpushed) | `5a789903d5696ea70549ce5b57a8c23edc3967e9` |
| alignment `main` at capture | `76ceddb8579d85d98579e2bb16191766ea2edaae` |

The diff against the base is 14 files, 742 insertions and 8 deletions. Queue state at start: `MT-POOL-PRIMITIVE`
was `not-started` (read from `queue/work-queue.yaml`). This record does not change the queue, `decisions.md`
or `contents.md`.

## Design

| element | where | what |
|---|---|---|
| slice function | `lib/pool-membership/slice.js:9,22,29` | rule `sha256-modulo-v1`: the first 8 bytes of sha256(canonical lower-case tenant UUID), as an unsigned 64-bit integer, modulo the member count. A tenant belongs to the member whose ordinal equals the result. A non-canonical id is refused rather than hashed under a second spelling. Members: 1..1024. |
| table | `lib/pool-membership/postgres-candidate.json` (`0001_pool_membership`) | `pool_membership(pool_kind, ordinal, member_id, expected_members, slice_rule, registered_at, heartbeat_at, lease_expires_at)`, primary key `(pool_kind, ordinal, member_id)`. The key includes the member incarnation, so two processes that claim one ordinal produce two visible rows (a conflict) rather than one overwritten row. The slice is (rule, ordinal, expected count); the rule is a column so that a rule change is itself a disagreement. |
| agreement rule | `lib/pool-membership/assess.js:8` | A member is eligible only while its own row is live, every live row of its kind has the same `expected_members` and `slice_rule`, and no two live rows share an ordinal. Otherwise it refuses with `POOL_SELF_NOT_LIVE`, `POOL_COUNT_DISAGREEMENT`, `POOL_RULE_DISAGREEMENT` or `POOL_DUPLICATE_ORDINAL`. Missing ordinals are reported but do not refuse: whether a member may take over a stale peer's slice is still an open question inside `MT-EVALUATOR-PARTITION`. |
| kind separation | `lib/pool-membership/postgres.js:48-51` | Every read and delete is filtered by `pool_kind = $1`, and `assess` only ever receives its own kind's rows. A kind is `^[a-z][a-z0-9]{0,31}$`, which keeps the environment-variable mapping injective. |
| leases | `postgres.js:99-103,115` | Lease times use the database clock (`now() + leaseMs`), never the process clock. `register` deletes only expired rows of its own (kind, ordinal) before it upserts its row. A live predecessor is left in place, and the result is reported as a duplicate. |
| alerting | `postgres.js` `signal` | A refusal calls `onAlert({kind, ordinal, members, state:'refused', reason, conflicts})` once per change of reason. Recovery calls it once with `state:'recovered'`. A database error fails closed as `POOL_UNAVAILABLE`. The default sink is `console.error`. |
| least privilege | `postgres.js:30` `grants`, `:53-77` boot check | The **member** identity has SELECT and INSERT, plus UPDATE on `heartbeat_at` and `lease_expires_at` only, plus DELETE. The **inspector** identity has SELECT only. Both also get USAGE on the schema and SELECT on `schema_migrations`. At boot the store runs `migrate check` and then refuses (`POOL_STORE_UNSAFE`) any identity that owns the table, holds TRUNCATE, TRIGGER or REFERENCES, or whose INSERT, DELETE or column-UPDATE set differs from its capability. The table is not tenant data and carries no tenant RLS. |
| flag off | `lib/pool-membership/index.js:23-38` | `standalone(kind)` uses the same interface. Its slice is every tenant. Nothing is read or written, and `inspect()` reports `{mode:'standalone'}` with `observed: null` instead of a fabricated lease. |
| configuration | `lib/pool-membership/config.js:36` | `MULTITENANT_POOL_<KIND>_PARTITION` (`on`/`off`/unset), `_MEMBERS`, `_ORDINAL`, `_LEASE_MS` (default 30000, range 100..600000), `_DATABASE_URL`, `_NAMESPACE`. When the flag is off and any partitioned value is set, the config is refused (`POOL_CONFIG_INVALID`) rather than silently ignored. One kind never reads another kind's variables. |
| evaluator adoption | `lib/server/serve/evaluator-config.js:131-139`, `lib/server/serve/evaluator-preview.js:31-38` | `load()` parses the `evaluator` kind. Boot builds the member, registers it, reads its slice and filters `config.tenants` through `slice.includes`. Every later consumer (startup, consumers, runtime) sees the same filtered map. With the flag off the map is unchanged. `parse()` and `loadMetadata()` are untouched, so realtime, which reuses `parse`, is not affected. |
| census | `lib/tenant-operations/catalogues.js:22,130-136,157` | The deployment census discovers every catalogue under `lib/` and requires each table to be tenant-bound. The pool catalogue is admitted as `operational, no tenant data`, pinned by digest (`a3c0a49f…c02d`), and kept out of tenant artifacts. A changed catalogue refuses with `OPERATIONS_CENSUS_OPERATIONAL_CHANGED`. |

## Interface for the vcpool lane

```js
const membership = require('lib/pool-membership');
const member = await membership.member(membership.config.fromEnvironment('vcpool', process.env), { onAlert });
await member.register();                  // once, before the first cycle -> { registered, memberId }
await member.heartbeat();                 // on a timer well inside the lease -> { renewed } | { renewed:false, reason }
const slice = await member.slice();       // before each cycle
//   eligible: { eligible:true, includes(tenantId) -> boolean, members, ordinal, rule, missingOrdinals }
//   refused:  { eligible:false, reason, conflicts }   (alert already raised; stop this cycle)
await member.inspect();                   // read-only: { kind, configured:{mode,members,ordinal,rule,leaseMs,memberId}, observed:{rows,liveOrdinals,missingOrdinals,conflicts,eligible,reason} }
await member.close();                     // removes this member's row
membership.grants({ namespace, member: role, inspector: role });  // the grant plan
membership.catalogue;                     // the reviewed migration catalogue for `migrate up`
```

Connector tenants are hashed by tenant ID ([pool-primitive-shared](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#pool-primitive-shared)),
so the vcpool lane calls `slice.includes(tenantId)` and never passes a source ID. The caller owns the heartbeat
schedule.

## Measurements (reproduced)

Every run used the lane worktree with its own `npm ci` and a dedicated `postgres:16` container
(server `16.15`) with a private name and a random password held in a mode-0700 scratch directory. The
container, its volume and the credentials were removed afterwards. The local mongod on 27017 was not used.

| check | result |
|---|---|
| `tests/pool-membership.test.js` (unit: slice, config, agreement, standalone, evaluator config) | 13 passing |
| `tests/pool-membership.integration.test.js` (PostgreSQL 16) | 8 passing |
| existing evaluator integration suites, flag off: `evaluator-consumers`, `evaluator-consumer-load`, `evaluator-consumer-timer-churn`, `tenant-activity`, `tenant-current-state-recovery-proof`, `tenant-durable-replay` (with `NS_EVALUATOR_CONSUMERS_TEST`, `NS_M5_CURRENT_STATE_PROOF_TEST`, `NS_TENANT_DURABLE_REPLAY_TEST`), plus the pool suite | 43 passing, exit 0 |
| `tests/tenant-deployment-operations.test.js` (census now 25 candidates, one `operational`) | 28 passing |
| `npm run test:unit` | 3189 passing, exit 0 |
| `npm run test:tiers` | `628 test files, 8 tiers: ok` |
| `npm run test:write-boundary` | all 9 adapter entry points checked |
| eslint on changed files | 0 errors. The 2 warnings, both `security/detect-non-literal-fs-filename` in `evaluator-config.js` `loadInternal`, are also present at the base. |

The integration suites check that the admin URI names a database containing `test`. The first run against a
database named otherwise was refused by that check (`A disposable test database must be explicitly
selected`) and was repeated on a `*_test` database.

Not run: the full suite, the browser and dom tiers, `prcheck`. These belong to the coordinator's frozen-head
acceptance.

## Break-it controls

Each control was applied to the working tree and run, and then the files were restored. Restoration was
checked by `sha256sum -c` against copies taken before the first control (all six module files `OK`).

| control | break | result |
|---|---|---|
| key without pool kind | Primary key `(ordinal, member_id)`. Reads, deletes and `ON CONFLICT` drop `pool_kind`. | **red**, 2 of 8 integration tests. Cross-kind test: `evaluator 0 POOL_COUNT_DISAGREEMENT`, `false !== true` (the vcpool rows with count 3 were counted against evaluator count 2). Count-disagreement test: `another kind is unaffected`. |
| skip the agreement check | `assess` always returns eligible | **red**, 8 tests (4 unit, 4 integration). For example, the count-disagreement unit test gave `true !== false`. The cross-kind integration test expected `'POOL_DUPLICATE_ORDINAL'` and got `undefined`. |
| off-by-one slice | `prefix % (members + 1)` | **red**, 3 tests. The partition test found a synthetic tenant with `owners []` at N=1 (`0 !== 1`). The pinned-rule test gave `1 !== 0`. The integration partition test covered `219 !== 300` tenants. |
| standalone drops a tenant (adoption is on the evaluator path) | the standalone predicate excludes tenants whose id starts with `2` | **red**, `tenant-activity.integration`: 4 failing, 3 passing, `Error: Evaluator consumer tenant is not configured`. This shows that the actual evaluator role, booted through `evaluator-config.load`, selects tenants through the primitive. |
| census pin (in-test) | the pool catalogue loses a statement (checksum recomputed) | refused with `OPERATIONS_CENSUS_OPERATIONAL_CHANGED`. This is asserted inside `tenant-deployment-operations.test.js`. |

## Points for the maintainer

1. **The partitioned evaluator is refused in this build.** `MULTITENANT_POOL_EVALUATOR_PARTITION=on` fails
   config load with `evaluator pool partitioning is not enabled in this build`. The primitive is complete for
   the evaluator, but the per-cycle gate inside `evaluator-runtime`, an empty-slice member, and the
   operational endpoint are `MT-EVALUATOR-PARTITION` work. Enabling the flag without that work would admit
   the static slice without the per-cycle agreement check.
2. **The census gains a category.** The census requires every discovered catalogue table to carry
   `tenant_id`. The pool table is the first deployment-operational catalogue, so `catalogues.js` gains an
   explicit, digest-pinned `OPERATIONAL` list. Any change to the pool catalogue therefore moves that pin, in the
   same way as the profile alternative pin. Needs review: whether operational catalogues should live in this
   census or in a separate one.
3. **Row key.** The decision says "keyed by pool kind as well as ordinal". The key is `(pool_kind, ordinal,
   member_id)` so that a duplicate ordinal is observable as two rows. A key of `(pool_kind, ordinal)` alone
   would let a second process overwrite the first process's row, and "no two live rows share an ordinal"
   could then never be observed.
4. **Coverage gaps are reported, not refused.** When a member is missing, its tenants go unworked until its
   lease returns or an operator acts. Takeover of a stale slice remains the open design choice recorded in
   `MT-EVALUATOR-PARTITION`.
5. UNMEASURED: behaviour under a database failover, clock behaviour across PostgreSQL replicas, and the
   lease and heartbeat values to use at scale.
