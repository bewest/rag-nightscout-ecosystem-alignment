# MT-OWNERSHIP-OPS (M6b): operator-assisted ownership add, transfer and recovery

*Contributor-facing measurement record, captured 2026-11-10. Not edited after capture. Lane
`codex/ownership-ops-20261110`; local, unpushed.*

## Anchors

| tree | ref | commit |
|---|---|---|
| cgm-remote-monitor lane head | `codex/ownership-ops-20261110` | `6ee8fb04882139b5e5dea068150d61d08519ca58` (tree `2d4b29654c479785259f8d9cba04c78e978d28df`) |
| lane base = draft #8898 head | `official/workspace/multitenant-20261102` | `dc795bd1515f11808a8d0732f2be9925cb2ffcd1` |
| `official/dev` (ancestor of the lane head) | local ref, not freshly fetched | `4a482627bfdafb1fef8dcbe0ac6c484811cae563` |
| alignment `main` at writing | | `3259787103b8a8d5a6ed4b193422dc868b127602` |

The queue item names `base: workspace/multitenant-20261102@ed2ced00`; the lane was cut from
the current #8898 head `dc795bd1` per the brief.

## What the capability is

Owner = an active `tenant_owner_actors` row with `can_update` whose principal is an existing
subject. The lane adds, in one commit (16 files, +1620/−9):

- `lib/tenant-ownership/component.js`: `list`, `add`, `transfer`, `recover`. The operator
  identity `{principal, consumer}` comes from composition; the request names the tenant and
  identifiers only. Every change carries `expectedOwners` (the owner set the operator observed),
  so a concurrent change refuses `OWNERSHIP_CONFLICT` instead of being replaced. Current operator
  authority is called in the store transaction and must return exactly `{allowed: true, current:
  true, tenant, plane: 'operator', principal, consumer}` for the requested tenant (the
  deletion ceremony's shape).
- `lib/tenant-ownership/postgres.js`: separate operator identity with an exact privilege screen
  (no DELETE, no table UPDATE, no credential/secret tables). Lock order config `FOR SHARE` →
  policy `FOR UPDATE` → actor rows `FOR UPDATE` (the subject-admin order; owner-plane mutations
  hold the policy row `FOR SHARE`, so they serialize with ownership changes). Conditional writes
  under a savepoint; a lost conditional write, a result without the named target or with zero
  owners rolls back and is audited as refused.
- Authorization migration `0006_owner_ownership_operations` (append-only; 0001–0005 bytes
  unchanged): owner verbs, `outcome` and `detail` columns on `tenant_subject_admin_audit`, with a
  constraint that owner verbs carry both and existing verbs neither.
- Internal service `ownership-operations` v1 (`lib/server/internal-api/contracts/ownership-operations.json`,
  named client `clients.ownershipOperations`, listener `lib/tenant-ownership/service.js`) on the
  existing shared transport: Unix socket or internal HTTP with `trust: 'network'`. No new
  authentication scheme. `service.tenantSetAuthority({principal, consumer, tenants})` is the
  shipped current-authority adapter.
- Self-service co-owner/transfer is not implemented (decision `preview-operator-assisted-ownership`).

## Commands and results (all from tool output on `6ee8fb04`)

```bash
cd externals/work/crm-ownership-ops-20261110
NODE_ENV=test NS_TENANT_OWNERSHIP_DOCKER_TEST=1 node_modules/.bin/mocha --fail-zero --timeout 60000 \
  --exit --require ./tests/hooks.js tests/tenant-ownership-postgres.integration.test.js \
  tests/tenant-ownership.test.js tests/internal-api-contracts.test.js
```

| check | result |
|---|---|
| focused family (7 PostgreSQL/HTTP + 5 source + 8 contract tests) | **20 passing, 0 failing**; no `ns-own-*` container left afterwards |
| `npm run test:unit:ci` (first run) | 3067 passing / 3 failing: `compose-ui`, `page-bundle-budget`, page benchmark gzip, all `ENOENT .../node_modules/.cache/_ns_cache/public/js/bundle.app.js` (no bundle after `npm ci --ignore-scripts`) |
| after `npm run bundle`, the 3 files | 16 passing |
| `npm run test:unit:ci` (rerun) | **3078 passing, 0 failing**, exit 0 |
| multitenant corpus, 26 suites that apply the authorization catalogue or admit lifecycle/deployment catalogues (`--only` list in `corpus-subset-record.json`) | **280 passing, 0 pending, 0 failing**; the script verified its PostgreSQL, Mongo and Vault containers and volumes absent |
| `node scripts/test-tiers.js check` | `611 test files, 8 tiers: ok` |
| ESLint on changed JS | 0 errors; 18 warnings, all `security/detect-non-literal-fs-filename` (17 in existing files, 1 in the new test's `chmodSync`) |

PostgreSQL image `postgres:16` (the suite's own disposable container `ns-own-<random>`, random
loopback port, generated password in the child environment only).

## Gate tests (in `tests/tenant-ownership-postgres.integration.test.js`)

- **Race control.** A separate connection holds tenant A's owner row `FOR UPDATE`; two transfers
  `s_owner1→s_new` and `s_owner1→s_new2` with the same `expectedOwners` start; the test waits
  until both `nightscout-ownership-ops` backends are in `wait_event_type='Lock'`, then releases.
  Asserted: exactly one `applied`, one `refused` (`OWNERSHIP_CONFLICT`); owners = the winner
  only; two `owner-transfer` audit rows, one applied and one refused, naming both targets.
- **Foreign-authority control.** Operator authorized for tenant B only (`tenantSetAuthority`)
  calls add/recover/transfer/list on tenant A: all `OWNERSHIP_FORBIDDEN`. An adapter that answers
  `allowed` for its own tenant B when asked about A, a `current: false` answer and a
  `plane: 'owner'` answer are each forbidden. Over the private service the same binding gets
  `{outcome: 'denied', code: 'OWNERSHIP_FORBIDDEN', event: null}`. Oracle: every actor and audit
  row of A and B identical before and after. Positive control: the same binding then adds an
  owner in B.
- Add (applied + four audited refusals), transfer (old owner loses and new owner gains the owner
  plane's own `owner-policy.js` authority), recovery of a tenant whose owner subjects were deleted
  out of band (`expectedOwners: []`; no console output during the call; response keys exactly
  `code, event, outcome, owners`; audit detail keys exactly `after, before, expected, owner`),
  privilege screen (DELETE on actors or UPDATE(ceiling) on policy refuses startup), UDS and
  internal HTTP round trips with a schema refusal for a `credential` field.

## Break-it controls

Runner `controls-run.py` (copied here; results `controls.json`): apply the mutation to the lane
file, run the named test, restore with `git checkout --`, rerun, check the tree is clean.
Every row: restored run 1 passing / 0 failing, tree clean.

| control | mutation | mutated result and exact symptom |
|---|---|---|
| C1 | remove the three row locks **and** both conditional-write predicates | **red**: `exactly one transfer applies: applied:,applied:` `2 !== 1` (both transfers applied) |
| C1b | remove the row locks only | green: the conditional write refuses the loser (`AND active=true` matches no row), audited |
| C1c | remove the conditional predicates only | green: the policy/actor locks serialize; the loser sees the new owner set |
| C2 | drop `result.tenant !== actor.tenant` from the authority check | **red**: `Missing expected rejection` at the misbound-adapter call (line 251): A changed |
| C2b | `tenantSetAuthority` ignores its tenant list | **red**: `Missing expected rejection` at the first foreign call (line 248) |
| C3 | remove the in-transaction `authorize()` from `change` | **red**: `Missing expected rejection` (line 248) |
| C4a | transfer plan forgets to activate the target, orphan guard kept | red against the test's expectation, but safe: `outcome: 'refused'`, owners still `[s_owner1]` |
| C4b | same plan bug and the zero-owner/target guard removed | **red**: `outcome: 'applied'`, `owners: []` (tenant orphaned) |
| C5 | service adds an `operator` field to the wire result | **red**: `SOCKET_IPC_UNAVAILABLE` (response schema refused) |
| C5b | store returns `delegable` beside the recovery result | **red**: response keys gain `'delegable'` |
| C6 | privilege screen ignores DELETE/TRUNCATE/REFERENCES | **red**: `Missing expected rejection` (store with DELETE on actors accepted) |
| C7 | `plan()` skips the `expectedOwners` compare (unit test) | **red**: `undefined` vs `'OWNERSHIP_CONFLICT'` |

C1b and C1c are green ablations with a known meaning: the locks and the conditional writes are
two independent layers, and only removing both lets two transfers apply. C4a is red for the
intended reason only in part: the orphan guard turned the plan bug into a refusal.

## Findings

- **read-derived**: `lib/subject-admin/postgres.js` `remove()` deletes any subject, including an
  owner's own subject, without consulting `tenant_owner_actors`. The actor row stays but no longer
  counts (human sessions join subjects; this lane counts only actors with a subject), so an owner
  can leave the tenant with zero usable owners. Recovery restores it (the recovery test reproduces
  the resulting state by deleting the subjects directly, not through `remove()`). Last-owner
  protection in the owner API is an M6a question for the coordinator.
- **read-derived**: legacy subject-admin writers composed without `ownerPolicy` do not take the
  policy row lock, so they do not serialize with ownership changes. Only the owner-policy path was
  exercised.

## UNMEASURED

- Composition into a serving role: `admin` in `lib/server/serve/roles.js` has no runtime; no CLI
  configuration, endpoint descriptor parsing or `nightscout multitenant admin` start exists for
  this service.
- Deployment grants: `deploy/multitenant/config.js` has no `ownership_operator` identity; the
  grants above exist only in the test.
- Concurrency other than transfer-vs-transfer (add-vs-recover, ownership change vs. an in-flight
  owner-plane mutation holding the policy row) is reasoned from the lock order, not raced.
- Human-session effect (`lib/human-session/postgres.js` reads `owner_active`) of a transfer:
  not exercised; the owner-policy effect is.
- Full suite, browser tier, the other 22 corpus suites, prcheck and CI on the lane head.
- Lifecycle export/import of the two new audit columns: exercised only as far as the corpus suites
  above apply the catalogue; no artifact round trip with owner audit rows was checked.
