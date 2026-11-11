# Acceptance of the 2026-11-11 batch join: frozen `2f1acc71`, final `0392acf9`

*Contributor-facing measurement record, captured 2026-11-11 (UTC). Not edited after capture.*

Candidate: `externals/work/crm-batch-join-20261111`, branch `codex/batch-join-20261111`.

- **Frozen head:** `2f1acc71b00fe7d53e5d3fbabf594910d77c20a8`. The full campaign ran here.
- **Final head:** `0392acf97c720a7e121eea47a9d42a0c8dbe9e73`. This is the frozen head plus two acceptance fixes,
  both changes to test files only (below).
- **Base:** #8898 head `16a1fc2d45e59602eb6ec3e3bf6f506f35bcc5b1`, from `git ls-remote official refs/pull/8898/head`
  at the start. `official/dev` is `4a482627`.
- **Size:** the final head is 66 commits on the base, 51 without merges.
- **Baseline record:** `../../batch-join-2026-11-10/16a1fc2d-acceptance/`.

The tree was clean (`porcelain=0`) at the freeze, at the end of the campaign and at prcheck. The git-ignored
`my.test.env` stays in the worktree.

## Environment

- **Repository tiers:** `my.test.env` is `tests/ci.test.env` with `CUSTOMCONNSTR_mongo` pointed at a dedicated
  container, `ns-batchjoin1111-mongo`:
  - mongo `@sha256:9854f713…`, server 7.0.43;
  - `--ulimit nofile=64000:64000`;
  - loopback port 27827.
- **Corpus images:** postgres `@sha256:9e2cf628…` (16) and mongo `@sha256:1f995ad6…` (7.0.43), through
  `NS_MULTITENANT_POSTGRES_IMAGE` and `NS_MULTITENANT_MONGO_IMAGE`. Vault is the digest the suites pin.
- **Lab and bench database:** a dedicated PostgreSQL 16.15 container, `ns-batchjoin1111-benchpg`:
  - `@sha256:9e2cf628…`, with `pg_stat_statements`;
  - `--ulimit nofile=64000:64000`;
  - database `nightscout_bench_test`.
- **Not used:** the local mongod on 27017.
- **Run order:** the tiers ran one at a time.
- **Containers:** both dedicated containers were removed afterwards. The corpus, the OIDC matrix and the
  Compose instrument start and remove their own: the campaign ended with `containers=0 nslc=0`.

## Lanes joined

Each head was confirmed with `git rev-parse` before merging, and every head matched the brief.

| merge commit | lane | lane head | conflicts |
|---|---|---|---|
| `4ad9882f` | deploy-fixture | `f3dc10c8` | none |
| `b34d5c36` | devicestatus-advanced | `0df0e66f` | none |
| `4bb4b4e5` | perf-db (contains evaluator-partition `d6560468`, pool `5a789903`, connector `1792063a`, partition `cb1b751d`) | `471e51a9` | `deploy/multitenant/compose.yaml` modify/delete |
| `e47fd708` | perf-realtime | `eacd6a3b` | `deploy/multitenant/bootstrap.js` modify/delete |
| `25b905b8` | perf-evaluator through its join scratch | `3b858586` (lane `9c46b95e`) | `lib/storage/postgres-durable-replay.js` |
| `d48a9c2c` | eval-cost | `745c7f4e` | `lib/storage/postgres-durable-replay.js` (3 hunks) |

The side branch `codex/eval-cost-pgsort-port-20261111` is not included.

**Conflict resolutions:**

- **`compose.yaml`:** resolved as deleted. Deploy-fixture moved the Compose tree to nightscout-deploy. Perf-db's
  change was the api, realtime and evaluator healthchecks, `start_period: 900s` and `start_interval: 2s`. It is
  listed for nightscout-deploy below.
- **`bootstrap.js`:** resolved as deleted, for the same reason. RT's change was a reviewed signature list
  (`tenant_change_stamps(uuid[])`) in the function-ownership loop. It is listed for nightscout-deploy below.
- **`postgres-durable-replay.js`, EV merge:** a union. The reconcile result carries RT's `physical` and
  `invalidKeys` (incremental view) and EV's `signature`.
- **`postgres-durable-replay.js`, eval-cost merge:** a union. Each hunk keeps RT's part and eval-cost's part.
  - `:183` keeps `invalidKeys` beside eval-cost's `ordinals` and `pageSource`.
  - `:212` keeps the E reuse (`unchanged ? row : clone(row)`) and adds `else invalidKeys.push`.
  - `:233-236` builds one `snapshot` object, and eval-cost's `.then` memo of verified signatures wraps it.

**Readiness:** `tenant-startup.js` comes from the join scratch: perf-db's module plus `isReady` and `limited`.
`preview-api`, `preview-realtime` and `evaluator-preview` all use this one module. The evaluator passes
`isWarm: startup.isReady` (`evaluator-preview.js`).

## Integration work required by decisions (separate commits)

| commit | what | before (reproduced) | after |
|---|---|---|---|
| `465c1ea7` | 11 lane opt-in suites had no INVENTORY row (list below) | `test-multitenant.js` refused: `opt-in test file missing … INVENTORY` (11 files) | 65 suites: 40 on the script's admin URI, 29 with their own containers |
| `c82afdb9` | **`#write-clock-complete`**, evaluator side (details below) | 3 controls red on `d48a9c2c`; see below | evaluator-wake 11 passing, evaluator-cost 11, durable-replay unit 22, gap-alert 5 |
| `2f1acc71` | **`#root-writer-fenced`** and the evaluator's change-stamp grants (details below) | read-derived (nightscout-deploy `54af5f2e`) | first exercised by the corpus suites that apply `plan.grants()` (below) |

The 11 suites added to the inventory in `465c1ea7`:
- change-stamps, postgres-tenant-scan, pool-membership;
- incremental-view, tenant-write-clock-complete;
- evaluator-wake, evaluator-cost, views-keep, projection-total-order, evaluator-consumer-wake;
- operation-window-epoch.

**`c82afdb9` in detail:**
- The signature is the write clock pair `{stamp, deleted}`:
  - `postgres-durable-replay.js:97` reads `last_stamp` and `last_delete_stamp` from the tenant's clock row;
  - `changeSignature` and `sameSignature` are at `:32-36`, and the evaluator component uses the same
    `sameSignature`;
  - the row-count and `xmin` digest scan is removed.
- The runtime takes `readStamps`:
  - one read per backstop pass for every admitted tenant (`evaluator-runtime.js:366-378`);
  - a refused read checks no tenant that pass (`stampReadsRefused`);
  - a tenant missing from the read acquires.
- `evaluator-preview.js:73` wires `readStamps` to `lib/change-stamps` `clock` when the configuration names
  `changeStamps`.

**`2f1acc71` in detail** (`deploy/multitenant/config.js`):
- `:99`: `root_writer` joins the control-schema window reads, as nightscout-deploy `54af5f2e` does.
- `:121`: change-stamp grants with realtime and evaluator both as checkers. That gives SELECT on the function's
  `schema_migrations`, which evaluator readiness now checks.
- `:131`: the evaluator configuration names `changeStamps`.
- The api's `UPDATE(last_stamp,last_delete_stamp)` came with perf-db (`:53`).

**Grants, per role:**
- realtime and evaluator: USAGE plus EXECUTE on `tenant_change_stamps(uuid[])`, and SELECT on its ledger.
- api: `UPDATE(last_stamp,last_delete_stamp)` on the clock.
- root_writer: USAGE on control, plus SELECT on `schema_migrations`, `tenant_lifecycle_windows` and
  `tenant_lifecycle_operations`.

These are measured only as far as the plan suites apply them: operation-window-epoch and admin-lifecycle-fit
both apply `plan.grants()` and run window admission and the admin role. No test starts the api, realtime and
evaluator role processes against the full plan grants (see UNMEASURED).

### Evaluator controls under write-clock-complete (`evaluator-wake.integration`, actual PostgreSQL)

On the joined head `d48a9c2c`, before the switch, three tests went red:
- `EV_HARD_DELETE_REEVALUATED`;
- `EV_UNSTAMPED_UPDATE_REEVALUATED`;
- `the delete moved the signature`.

They were red because the tests write with raw SQL (`DELETE`, and `UPDATE` of activity). Raw SQL bypasses the
clock, and by the decision's contract it is not a supported write.

The rewritten controls write through the supported path, the storage port inside the clock transaction
(fixture `hardDelete` and `updateInPlace`). Each one asserts its premise first:
- a hard delete moves `last_stamp` and makes `last_delete_stamp = last_stamp`;
- an activity in-place update moves `last_stamp` only.

Every control runs twice: per component (one clock-row read), and in batch mode (one `readStamps` per pass).

| control | per component | one read per pass |
|---|---|---|
| idle: 5 passes, 5 checks, 5 unchanged, 0 cycles | pass | pass (`stampReads` 5) |
| lost wake (`EV_LOST_WAKE_BACKSTOP`) | pass | pass |
| hard delete re-evaluated (`EV_HARD_DELETE_REEVALUATED`), stamp-only | pass | pass |
| unstamped-domain update re-evaluated (`EV_UNSTAMPED_UPDATE_REEVALUATED`), now stamped | pass | pass |
| eval-cost E after a hard delete (`EV_COST_E_HARD_DELETE`): checkpoint and delete stamp moved, delete seen | pass | n/a |

Unit cases:
- `EV_STAMPS_ONE_READ`;
- `EV_STAMPS_CHANGED_ACQUIRES` (one write and one hard delete among three tenants);
- `EV_STAMPS_REFUSED_NOT_A_CHANGE`;
- `EV_STAMPS_MISSING_ACQUIRES`.

**Break-it controls**, each restored with `git checkout`. Files: `integration/control-*.txt`.

| break | symptom |
|---|---|
| runtime `same` ignores the pair | evaluator-wake 5 passing / **6 failing**: `EV_LOST_WAKE_BACKSTOP` ×2, `EV_HARD_DELETE_REEVALUATED` ×2, `EV_UNSTAMPED_UPDATE_REEVALUATED` ×2. Unit: 2 failing (`EV_STAMPS_CHANGED_ACQUIRES`, "the next pass finds the change") |
| the batch pass ignores its read (`seen = state.processed`) | 8 passing / **3 failing**, exactly the three batch-mode cases. The per-component cases stay green, which shows the batch path is the one consulted |

### Idle DB cost per tenant, before and after the switch

The bench is `tools/tenancy/perf-evaluator/bench.cjs`. My scratch variant adds `BATCH=1`, which provisions the
change-stamp function and passes `readStamps`.

- **Setup:** N=100, 24 h seeded per tenant, deployed plugins, backstop 1 s, slow timer 1 s.
- **Phases:** 60 s idle, then 30 s at real cadence.
- **Host load:** 1.0–1.5.
- **Files:** `integration/bench-*.txt`.

| code | idle queries / tenant-min | idle DB-ms / tenant-min | PostgreSQL CPU | per check | real-cadence latency p50 / p95 ms |
|---|---|---|---|---|---|
| `d48a9c2c`, row-version digest | 240 | **24.4** | 14.3% | 4 statements, 0.265 DB-ms | 774 / 801 |
| `2f1acc71`, clock pair per component | 240 | **1.51** | 5.0% | 4 statements, 0.009 DB-ms | 731 / 748 |
| `2f1acc71`, one change-stamp read per pass | **1.8** | **1.24** | 1.5% | one statement per pass for all 100 | 730 / 756 |

- **How the batch row counts:** `pg_stat_statements` counts only top-level statements, so the function's
  per-tenant inner reads do not appear among the queries. Their time is inside the top-level DB-ms.
- **A misprovisioned run:** the first batch run (`bench-…-batch-misprovisioned.txt`) refused every read, 62/62.
  My bench provisioning gave the function owner no USAGE on the clock schema; the error was `42P01 relation
  "tenant_write_clock" does not exist`, read in a debug script. Meanwhile real-cadence writes were only evaluated
  by due timers (latency `null`). That shows the runtime's refused-read behaviour (no checks, no false
  "unchanged"). It also shows that a misprovisioned function stops change detection until the evaluation-gap
  alert fires.

## Join repairs: none beyond the table above

The perf-db `preview-domains-equivalence` golden is checkout-independent at `471e51a9`. It passed in the unit tier
here.

## Full campaign on the frozen head `2f1acc71` (16:50:56–17:10 UTC, `campaign.txt`)

| suite | command | passing | pending | failing | baseline `3cd1c487` / `16a1fc2d` |
|---|---|---|---|---|---|
| bundle | `npm run bundle` | exit 0 | | | |
| unit (258 files) | `npm run test:all` (exit 0) | 3315 | 1 | 0 | 3176 / 0 |
| dom (19) | ″ | 205 | 0 | 0 | 205 |
| dependency (32) | ″ | 368 | 2 | 0 | 368 / 2 |
| core (26) | ″ | 319 | 0 | 0 | 319 |
| harness (10) | ″ | 99 | 0 | 0 | 99 |
| integration (266) | ″ | 3643 | 703 | 0 | 3643 / 593 |
| stress (1) | ″ | 18 | 0 | 0 | 18 |
| browser (42) | `npm run test:browser` (exit 0) | 686 | 0 | 0 | 686 |
| multitenant corpus (65 suites) | `node scripts/test-multitenant.js --record …` | 653 | 1 | **2** (exit 1) | 596 / 1 (54 suites) |

**Pending, reported separately:**
- **unit, 1:** `moment-memo` runs over `VIEWS_CORPUS_DIR` only when that is set. Run with it set (the alignment
  `tools/ns2parquet/fixtures`): `MOMENT_MEMO_CORPUS files=28 distinct date strings=14579 all equal`, 6 passing.
- **dependency, 2:** unchanged from the baseline.
- **integration, 703:** +110 against the baseline. These are the lanes' new opt-in suites registering as pending in
  the default tier, and they run in the corpus.
- **corpus, 1:** `NS_TENANT_COMMIT_CLOCK_BENCHMARK`, which is opt-in by design.

**Corpus failures on the frozen head:** operation-window-epoch and admin-lifecycle-fit both failed in their
before-all hook:

```
error: function <prefix>_change_stamps.tenant_change_stamps() does not exist
```

Both copy the old `bootstrap.js` ownership loop, which runs `ALTER FUNCTION ns.fn()` and assumes no arguments.
The plan's catalogues gained `change_stamps` (RT), whose function takes `uuid[]`. This is a real failure: RT
changed `bootstrap.js` but not the two suites, which were not in the corpus inventory until `465c1ea7`.

**OIDC nine-stage matrix:** `tests/native/oidc-matrix/run.sh --out …`, exit 0.
- 9/9 PASS, complete, 15677 ms, porcelain `[]`, `sourceCommit` `2f1acc71…`.
- postgres 16.15 (`@sha256:721873c3…`), mongo 7.0.43, Chrome 154.0.8037.57, oref0 `d219baf9`.

**OIDC matrix controls** (single eight-hour exchange, browser csrf, consumer authority bypass): exit 0. Each control
went red, then PASS when restored:
- `shipping single subject JWT lifetime is eight hours`;
- `owner transport status oracle`;
- `next DATA operation must read current role authority`.

**Compose instrument on the frozen head:** hung, then failed.
- Every component (api, evaluator, realtime, tenant-admin) exited 1 at start with `TypeError: Invalid fixed
  participant manifest` (`operation-cohort-manifest.js:14`, from `component.cjs:38`).
- The driver then waited with no bound. I removed the driver container (exit 137), and the instrument's trap
  removed the project.
- The second run, `deadline`, hung the same way and was stopped the same way.
- Cause: the connector lane (`fd882910`) added `vcpool` to `listener-config` `ROLES`. The instrument builds its
  fixed cohort manifest from that list, while the manifest admits four roles. The bug is in the lane, and the
  join surfaced it. File: `frozen-2f1acc71/compose-final-hung.txt`.

## Acceptance fixes (after the freeze, each with its diagnosis above)

| commit | fix | after |
|---|---|---|
| `ffc8c5aa` | the two suites' ownership loops read `pg_get_function_identity_arguments` | the two suites: 53 passing |
| `0392acf9` | `tests/native/internal-api-compose/component.cjs` builds its manifest from `manifest.ROLES` | Compose `final` `SCENARIO_PASS` |

Both changes touch only test files: two opt-in integration suites, which are pending in every repository tier, and
the Compose instrument, which no tier loads.

**Re-run on `0392acf9`:**
- the whole corpus;
- all four Compose runs;
- the static checks.

**Carried over from `2f1acc71`:**
- `test:all` and browser: the fixed files are pending or not loaded in those tiers;
- the OIDC matrix: its harness and stages do not load the changed files.

## On the final head `0392acf9` (17:11–17:19 UTC)

| check | result |
|---|---|
| multitenant corpus (65 suites), `--record` | **706 passing, 1 pending, 0 failing**, exit 0; every created container and volume verified absent |
| Compose `final` | exit 0, `SCENARIO_PASS`; drain: the held caller got its response at 1783 ms |
| Compose `--api-shutdown-ms 500` | exit 0, `SCENARIO_PASS`; caller `SOCKET_IPC_UNAVAILABLE` at 673 ms (expected) |
| Compose control `early-drop` | exit 1 as expected: `SOCKET_IPC_UNAVAILABLE` at 182 ms where a response was expected |
| Compose control `blanket-window` | exit 1 as expected: `DRIVER_FAILED lifecycle invalidation of suspended A on api: SOCKET_IPC_UNAVAILABLE` |
| `node scripts/test-tiers.js check` | `654 test files, 8 tiers: ok` |
| write intent / write boundary | exit 0; 13 modules / 3 identifier reads; 9 entry points, and `tenant write clock advanced by every mutating statement in lib/storage/postgres-entries-write.js` |
| `npm run lint` | 0 errors, 58 warnings (base `16a1fc2d`: 52) |

**The 6 new lint warnings**, all in lane files, none in the integration commits:
- `internal-api/transport.js` +2;
- `evaluator-config.js` +1;
- `projection-memory-read.js` +1;
- `tenant-connector/config.js` +2.

Per-file counts: `final-0392acf9/lint-warnings-*.txt`.

## Lane labs (on `2f1acc71`, or `0392acf9` where marked; files in `labs/`)

| lab | result |
|---|---|
| evaluator-partition (`tools/tenancy/evaluator-partition/run.cjs`) | **`SUMMARY 23 checks, 0 failing`**: 23/23, as the brief requires (the lanes without perf-db's fix were 20/23) |
| connector-reverse (`tools/tenancy/connector-reverse/run.cjs`) | `SUMMARY 25 checks, 0 failing`; `docker ps -a \| grep -c ns-cr` = 0 |
| realtime publish-on-change set (every `tests/realtime-*.test.js` except browser-diagnostics, plus `preview-domains-equivalence`) | 98 passing |
| realtime / write-clock integration (change-stamps, incremental-view, tenant-write-clock-complete) | in the corpus run, 0 failing |
| perf-evaluator clinical equivalence, cross-tree (below) | **IDENTICAL**, all 6 runs, against base `9c46b95e` |
| perf-evaluator `equivalence.cjs`, within the tree (deploy and 22 plugins, slow 1000 and 60000 ms) | verdict lines identical to the eval-cost lane's base run |
| eval-cost read lab (`read-lab.cjs`, `VIEWS_CORPUS_DIR`, `MONGO_URI` on the dedicated mongo 7.0.43) | `PASS A_READ_DIFFERENTIAL` (details below) |

The within-tree `equivalence.cjs` verdicts:
- deploy: PASS/PASS at both slow timers;
- 22 plugins: `PASS ALARM_SET_EQUIVALENT` (52 transitions, due at most 999 ms early), with base's pre-existing
  `DIFF CONTENT_EQUIVALENT` (245/245 at 1000 ms, three message refreshes 1 ms after the base tick; 156/245 at
  60000 ms).

The read lab in detail:
- 5976/5976 reads equal with the total order, 0 different;
- 402 order-only reads, all ties;
- `outputChangedWithoutTie: 0` in every part;
- single-site MongoDB 7 returns the total order on 400 and neither order on 2 (the limit-12 typed-twin reads),
  matching the lane's record.

### Clinical equivalence, cross-tree

Harness: `tools/tenancy/eval-cost/trace.cjs` + `compare.cjs`. One synthetic 13-hour timeline (one hour of lead-in
plus 12 h). Every cycle's full output is hashed: emitted, requested with message text, every property, the due
instant. Base traces were generated in this session from `9c46b95e`, not taken from the lane.

| run | verdict |
|---|---|
| deploy, base (1 s) | IDENTICAL, 46801 cycles, 17 alarm transitions |
| deploy, due 1000 | IDENTICAL, 6093 cycles |
| deploy, due 60000 | IDENTICAL, 288 cycles |
| 22 plugins, base | IDENTICAL, 46801 cycles, 52 alarm transitions |
| 22 plugins, due 1000 | IDENTICAL, 46917 cycles |
| 22 plugins, due 60000 | IDENTICAL, 1032 cycles |

No clinical-equivalence difference was found. The 13-hour timeline has no sort ties, as the lane recorded, and
the tie-order changes in the read lab are all on ties.

**Vacuous control, as the eval-cost lane recorded:** the trace lab cannot see candidate E, because its replay moves
the checkpoint with every write. E is covered instead by `EV_COST_E_HARD_DELETE` and the durable-replay unit cases.

## prcheck (`tools/review/prcheck/prcheck.sh externals/work/crm-batch-join-20261111`, 17:48:55 UTC)

- `OK`, exit 0;
- `already contains official/dev 4a482627`, so official/dev brings in nothing;
- the push would send 639 commits on it (baseline 571): 743 files changed, +99267/−1110;
- `official/codex/batch-join-20261111` does not exist yet.

## What nightscout-deploy needs to match this head (not edited)

1. **Grants** in `bindings/compose/multitenant/config.js`:
   - **Catalogues:** add `change_stamps` (`lib/change-stamps/postgres-candidate.json`) to `catalogues()`.
   - **Function grants:** append `require('…/lib/change-stamps/postgres').grants({namespace:ns.change_stamps,
     clockNamespace:ns.clock, roles:[r.realtime,r.evaluator]})` at the end of `grants()`. Both roles are checkers
     (default), so both get SELECT on the function's `schema_migrations`.
   - **api:** `SELECT,UPDATE(last_stamp,last_delete_stamp)` on `tenant_write_clock`. The deploy tree has
     `UPDATE(last_stamp)` only, so api writes that hard-delete would be refused.
   - **root_writer:** already in the window-reads loop (`54af5f2e`). The deploy delta for that line can be dropped
     once it imports core's plan.
   - **Namespaces:** realtime and evaluator name `changeStamps: ns.change_stamps`. Realtime also takes
     `authorizationRecheckMs: 30000`. `lifecycle()` excludes `change_stamps`, like `control`.
   - **Overlay:** keep the tenant-count overlay (`tenantIds`, `NS_DEMO_TENANTS`) as the deploy delta.
2. **Bootstrap** (`bindings/compose/multitenant/bootstrap.js:85`): the function-ownership loop must accept the
   reviewed signature `tenant_change_stamps(uuid[])` (RT's `eacd6a3b` change) instead of refusing any argument list.
   - Measured consequence of not doing this: core's own suites failed with the same old loop (above).
   - **The function owner needs USAGE on the clock schema** (schema ownership as the bootstrap does today is
     enough). Without it every read fails `42P01`, which the bench reproduced.
3. **Compose healthchecks:** api, realtime and evaluator get `start_period: 900s` and `start_interval: 2s` (perf-db's
   lost hunk; Compose 2.20+ for `start_interval`). With the default `NS_TENANT_READINESS=serve`, readiness no longer
   waits for every tenant. The period covers `all` mode and cold dependencies.
4. **Kubernetes:**
   - The golden render has `readinessProbe` on the app containers and a `startupProbe` only on the Vault Agent
     sidecar.
   - Add a `startupProbe` to the api, realtime and evaluator containers on the same health command, with
     `periodSeconds` × `failureThreshold` ≥ 900 s (for example 5 s × 180), so a long warm under `all` is not killed
     by the liveness or readiness budget.
   - Under `serve`, the probe passes as soon as the role's own dependencies are up.
5. **Re-pin** `bindings/compose/SOURCE.md` and the identity-check hashes to the final head after it is pushed.

## UNMEASURED

- CI on the pushed head.
- **Real role processes against the full plan grants:** no Compose deployment of nightscout-deploy, and no
  api/realtime/evaluator role started with `plan.grants()`. The grants above are read-derived beyond the two plan
  suites.
- The evaluator's batch change-stamp read through the evaluator role process: `evaluator-preview` wiring with a
  configured `changeStamps` namespace. It ran in the bench and in the runtime tests only, not in a
  role-process suite.
- Evaluator idle cost at 1,000 tenants after the switch. The bench ran at N=100.
- The queue gate `oidc-native-recorded`: no merged summary helper was run.
- The lanes' own unit break-it controls were not repeated on the joined head. The exceptions:
  - this record's two evaluator controls;
  - the OIDC and Compose controls;
  - the before-states of each repair.
- Pre-existing harness gap: the Compose driver has no bound when the components die at start.
- prcheck runs no tests.

## Files

- `campaign.txt`: the step log of both campaign scripts.
- `frozen-2f1acc71/`:
  - `test-all.txt`, `test-browser.txt` (counts);
  - `test-multitenant.json`, `corpus-failures.txt`;
  - `oidc-matrix-summary.json`, `oidc-matrix-controls.json`;
  - `compose-final-hung.txt`.
- `final-0392acf9/`:
  - `test-multitenant.json`;
  - `compose-{final,deadline,early-drop,blanket}.txt`;
  - `static.txt`, `lint-warnings-*.txt`;
  - `bootstrap-loop-fix.txt`;
  - `prcheck.txt`.
- `integration/`:
  - `bench-*.txt`;
  - `control-*.txt`;
  - `evaluator-wake-cost.txt`.
- `labs/`:
  - `partition.txt`, `connector-reverse.txt`;
  - `read-lab.txt`;
  - `trace-compare-vs-9c46b95e.txt`;
  - `equivalence-{deploy,full}.txt`.

Raw logs and traces stay in the session scratch directory.
