# Acceptance of the 2026-11-10 batch join: full campaign on `3cd1c487`, delta campaign on `16a1fc2d`

*Contributor-facing measurement record, captured 2026-11-11 (UTC). Not edited after capture.*

Candidate: `externals/work/crm-batch-join-20261110`, branch `codex/batch-join-20261110`.

- **Frozen head (full campaign):** `3cd1c4878f3ffdf5fe68156040fe6d30805c3de6`.
- **Final head (delta campaign):** `16a1fc2d45e59602eb6ec3e3bf6f506f35bcc5b1`, which is the frozen head
  plus the BF-232 lane `2f1ae027` merged by the coordinator's instruction after the freeze.
- **Base:** #8898 head `official/workspace/multitenant-20261102` = `b70ad83fa4cdaeb7e6023137a05bd811d7db606a`
  (`git ls-remote official refs/pull/8898/head`, read at the start and again before the freeze).
  `official/dev` = `4a482627`. The final head is a fast-forward of #8898: 37 commits (29 not counting merges).
- **Baseline record:** `../../m6b-join-2026-11-10/b70ad83f-acceptance/`.

The tree was clean (`porcelain=0`) before and after the campaign and at prcheck. The git-ignored
`my.test.env` was removed afterwards.

## Environment

- **Repository tiers:** `my.test.env` = `tests/ci.test.env` with
  `CUSTOMCONNSTR_mongo=mongodb://127.0.0.1:27817/testdb`. That address is the dedicated container
  `ns-batchjoin-mongo`:
  - image `mongo@sha256:9854f7139445d766a9523571d6f047530c45547460ffcf8259eb2bf4264632ca`;
  - server 7.0.43;
  - `--ulimit nofile=1048576:1048576`, no tmpfs;
  - removed afterwards.
- **Bundle:** `npm run bundle` (production), exit 0, on both heads.
- **Corpus images:** postgres `@sha256:9e2cf628…` (16), mongo `@sha256:1f995ad6…` (7.0.43); Vault is the
  digest the suites pin.
- **Containers:** the corpus, the OIDC matrix and the Compose instrument start and remove their own. The
  final count from the campaign script was `containers=0`.

## Lanes joined (each head confirmed with `git log -1` before merging)

| merge commit | lane | lane head | contains |
|---|---|---|---|
| `85b8f045` | root-admin-parity | `165c13bf` | m6b-followups `65657a62` (BF-229) |
| `95dfe1f2` | admin-lifecycle | `66655756` | ownership-role `1376c294`; BF-230 |
| `89188a4b` | internal-listener | `78ecba76` | |
| `e711f285` | activity-eligibility | `07981b55` | |
| `7dbbd334` | export-expiry | `701eba6f` | |
| `22f069e5` | consumer-refusal, first pass | `1adb17f8` | |
| `c00dabe2` | consumer-refusal, final | `956d0940` | `1d39c924`, `956d0940` (BF-231 option c) |
| `16a1fc2d` | tenant-extended-settings (after the freeze) | `2f1ae027` | BF-232 |

**Textual conflicts, each resolved as a union:**
- `deploy/multitenant/config.js`: the `root_writer` and `ownership_operator` identities and grants, and
  the serve.internal environments plus `NS_API_ROOT_WRITER_PG`.
- `lib/cli/commands/multitenant.js` and `lib/server/serve/index.js`: `adminPreview` and `internal`.
- `operation-cohort.js`: keeps the clinical-catalogue import. The `lifecycleParticipant` import went with
  `openControl`.
- `realtime/config.js`: the serve.internal `api` peer plus `activity`.
- `preview-config.js`: `subjectAdmin` plus `activity`.
- `preview-api.js`: the activity `prepareTenant` plus `rootAdmin`.
- `preview-realtime.js`.
- The lifecycle catalogue and `tests/tenant-lifecycle.test.js` columns.
- `tests/tiers.json`.
- `evaluator-runtime.js`, `evaluator-consumers.js`, `evaluator-preview.js`: the activity eligibility fence
  first, then the content-change publication. A pause clears `state.last`, so the first output after
  unpause is always a new revision.

The admin operator-plane listener stays as composed.

## Migration allocation

No renumbering was needed. Checksums hash `up` only (`lib/migrations/catalogue.js:15`).

- **Lifecycle catalogue:** `0001`–`0005` unchanged, then `0006_tenant_lifecycle_artifact_removal`
  (export-expiry) and `0007_tenant_activity` (activity).
  - All 7 checksums validate.
  - The diff against base is insertions only, so `0001`–`0005` are byte-identical.
- **Authorization catalogue:** `0006_owner_ownership_operations` (already in base), then
  `0007_root_role_administration` (root-admin-parity).

## Join repairs (separate commits)

| commit | reconciles | before (reproduced) | after |
|---|---|---|---|
| `1eee9e46` | internal-listener × admin-lifecycle: serve.internal is resolved only for api/evaluator/realtime/tenant-admin; the admin role keeps its own `ADMIN_HOSTNAME`/`ADMIN_PORT` plane | `nightscout multitenant admin` exit 78 `serve.internal: requires the explicit role list of this process`; `nightscout-cli.test.js` 1 failing | exit 78 `admin requires MULTITENANT_ADMIN_CONFIG`; CLI, serve, internal-api, cohort tests 162 passing |
| `f99e529f` | the lifecycle README `importArtifact` example omitted `ledgerNamespace` | (doc) | example passes it |
| `10558a61` | activity and consumer-refusal opt-in suites missing from the corpus INVENTORY | `test-multitenant.js` refused: `opt-in test file missing … INVENTORY` (2 files) | rows added; doc recounted |
| `beefaad2` | admin-lifecycle made `lifecycleNamespace` mandatory; BF-229/root-admin race cases in `owner-subject-policy.integration` built the store without it | 2 failing: `Ownership operations require … a separate lifecycle control namespace` | 38 passing (lane: 38) |
| `57d59c77` | consumer-refusal final adds `evaluator-consumer-load` without an INVENTORY row | refused as above | 54 suites / 30 admin URI / 28 own containers / 53 pending + 1 `describe.skip` |
| `99dfe627` | content-change revisions × activity suite: B measured by `cycles` (the coordinator's oracle) | control on the joined head: old oracle red, `ACTIVITY_B_UNAFFECTED B kept cycling on the actual timers` (6 passing, 1 failing) | 7 passing |
| `3cd1c487` | content-change revisions × M5 recovery proof (two cases assumed one revision per cycle) | reproduced on the lane head `956d0940` alone (10 passing, 2 failing: `Evaluator native condition watchdog`; trigger `acquisition` ≠ `time-only`) and on the join | recovery proof 12 passing |

A grep for `outputRevision`/`evaluationRevision` across `lib/` and `tests/` found no other test that runs
the real runtime and expects a bump on every cycle. `tenant-projection-evaluator`'s `evaluationRevision`
is a separate per-component counter.

## Full campaign on the frozen head `3cd1c487` (01:38:38–01:53:23 UTC)

| suite | command | passing | pending | failing | baseline `b70ad83f` |
|---|---|---|---|---|---|
| unit (240 files) | `npm run test:all` (exit 0) | 3167 | 0 | 0 | 3106 |
| dom (19) | ″ | 205 | 0 | 0 | 205 |
| dependency (32) | ″ | 368 | 2 | 0 | 368 / 2 |
| core (26) | ″ | 319 | 0 | 0 | 319 |
| harness (10) | ″ | 99 | 0 | 0 | 99 |
| integration (255) | ″ | 3643 | 593 | 0 | 3643 / 547 |
| stress (1) | ″ | 18 | 0 | 0 | 18 |
| browser (42) | `npm run test:browser` (exit 0) | 686 | 0 | 0 | 686 |
| multitenant corpus (54 suites) | `node scripts/test-multitenant.js --record …` (exit 0) | 596 | 1 | 0 | 550 / 1 (49 suites) |

- **OIDC nine-stage matrix:** `tests/native/oidc-matrix/run.sh --out oidc-matrix`, exit 0.
  - 9/9 PASS, complete, 15293 ms, porcelain `[]`, `sourceCommit` `3cd1c487…`.
  - postgres 16.15 (`@sha256:721873c3…`), mongo 7.0.43, Vault 2.2.1, Chrome 154.0.8037.57, oref0 `d219baf9`.
- **Matrix controls:** `--control single:single-shipping-eight-hour-exchange,browser:csrf,consumer:consumer-current-data-authority-bypass`,
  exit 0. Each control went red, then PASS when restored:
  - single: `shipping single subject JWT lifetime`;
  - browser csrf: `owner transport status oracle`;
  - consumer: `next DATA operation must read current role authority`.
- **Compose (internal API):**
  - `final` exit 0 and `--api-shutdown-ms 500` exit 0, each with `SCENARIO_PASS`.
  - Control `early-drop`: exit 1, as expected. The held call got `SOCKET_IPC_UNAVAILABLE` at 213 ms where a
    response was expected.
  - Control `blanket-window`: exit 1, as expected: `DRIVER_FAILED lifecycle invalidation of suspended A on
    api: SOCKET_IPC_UNAVAILABLE`, the same symptom as the lane.
  - 0 containers and 0 networks remained after each run.
- **Static checks:**
  - `npm run test:tiers`: `625 test files, 8 tiers: ok`;
  - write intent: 13 modules / 3 identifier reads, exit 0;
  - write boundary: 9 entry points, exit 0;
  - `npm run lint`: 0 errors, 52 warnings. The baseline had 49; the 3 new ones are in lane files
    `lib/server/serve/admin-config.js` (2) and `lib/server/serve/internal-listener.js` (1).

**Deltas against the baseline:**
- unit +61;
- integration +46 pending: the lanes' new opt-in suites register as pending in the default tier;
- corpus +46 passing, with 5 more suites (admin-role-ownership, admin-lifecycle-fit, tenant-activity,
  timer-churn, load).

## Delta campaign on the final head `16a1fc2d`

**What changed:** `git diff --stat 3cd1c487..16a1fc2d` lists 7 files (+226/−15):
- two docs;
- `lib/server/tenant-app/environment.js`;
- `lib/server/tenant-app/rest-context.md`;
- the new `tests/tenant-extended-settings.test.js`, registered as a unit-tier entry in `tests/tiers.json`;
- `tests/tenant-rest-context.integration.test.js`.

**Who reaches `environment.js`:**
- Its requirers are `tenant-projection-evaluator`, `evaluator-config`, `preview-config` and
  `tenant-settings/catalogue`, all multitenant.
- `preview-config` is also required at module level by `runRoles`, which the single-tenant headless api
  shares; its `load` is called only in multitenant mode.
- The change adds constant tables and functions; nothing executes at load except constant construction.

**Browser bundle:** the production bundle built on `16a1fc2d` is byte-identical to the frozen head's. All
6 `.js`/`.css` outputs have equal sha256 (`final-16a1fc2d/bundle-sha256.txt`).

**Carried over from `3cd1c487`, with the reason:**
- browser: the bundle is identical, and the only change on the single-site load path is module-level
  constants;
- OIDC matrix and controls, Compose and its controls: the changed module is outside their roles' paths
  beyond settings projection, and the delta below re-runs every corpus suite that reaches it.

**Re-run on `16a1fc2d` anyway**, because the cost is low: `npm run test:all` covers unit, dom,
dependency, core, harness, integration and stress.

| suite | command | passing | pending | failing |
|---|---|---|---|---|
| unit (241 files) | `npm run test:all` (exit 0, finished 01:57:57) | 3176 | 0 | 0 |
| dom / dependency / core / harness | ″ | 205 / 368 / 319 / 99 | – / 2 / – / – | 0 |
| integration (255) / stress (1) | ″ | 3643 / 18 | 593 / 0 | 0 |
| `tests/tenant-extended-settings.test.js` | mocha | 9 | 0 | 0 |
| `tenant-rest-context.integration` | `test-multitenant.js --only tenant-rest-context` (exit 0) | 10 | 0 | 0 |
| `tenant-projection-evaluator.integration`, `tenant-rest-derived`, `tenant-current-state-recovery-proof` | `--only` ×3 (exit 0) | 25 | 0 | 0 |
| corpus suites reaching `environment.js` (18, see below) plus `tenant-notifications` | `--only` ×19 `--record corpus-delta.json` (exit 0) | 160 | 1 | 0 |
| `tenant-notification-native-restoration` | mocha | 1 | 0 | 0 |

**The 18 corpus suites** within 4 require hops of `environment.js`, from
`node scripts/test-select.js affected --files lib/server/tenant-app/environment.js --depth 4` intersected
with the corpus inventory:
- admin-lifecycle-fit, admin-role-ownership;
- evaluator-consumer-load, evaluator-consumers, evaluator-consumer-timer-churn;
- multitenant-preview-process, multitenant-preview-replicas;
- owner-configuration, owner-preview;
- postgres-secrets;
- tenant-activity;
- tenant-commit-clock-http;
- tenant-current-state-recovery-proof;
- tenant-frame-acquisition, tenant-frame-concurrency;
- tenant-projection-evaluator, tenant-rest-context, tenant-rest-derived.

These include the consumer-refusal native set and the activity native suite.

**Consumer native set before the freeze** (join with `956d0940` and repairs): evaluator-consumers,
timer-churn, load, tenant-notifications, activity and recovery proof together gave 35 passing, 0 failing.
Leaving out activity (7) and the recovery proof (12), and adding restoration (1), the consumer set is 17,
which matches the lane. The consumer focused unit set is 183 passing (lane: 178; the join adds the
activity cases in maintenance-window and deployment-operations).

**Static checks:**
- `npm run test:tiers`: `626 test files, 8 tiers: ok`;
- write intent and write boundary: exit 0;
- `npm run lint`: 0 errors, 52 warnings.

**prcheck** (`bash tools/review/prcheck/prcheck.sh externals/work/crm-batch-join-20261110`, 02:02:31):
- `OK`, exit 0;
- already contains `official/dev` `4a482627`;
- the push would send 571 commits on it (baseline 534).

## Files

- `frozen-3cd1c487/`:
  - `campaign.txt` (the step log);
  - `test-all.txt`, `test-browser.txt`;
  - `test-multitenant.json`;
  - `oidc-matrix-summary.json`, `oidc-matrix-controls.json`;
  - `compose-*.txt`;
  - `tiers-and-write-checks.txt`.
- `final-16a1fc2d/`:
  - `test-all.txt`;
  - `extended-settings.txt`, `restoration.txt`;
  - `corpus-only.txt` (the `--only` list), `corpus-delta.json`;
  - `tiers-write-lint.txt`;
  - `bundle-sha256.txt`;
  - `prcheck.txt`.

Raw logs stay in the session scratch directory.

## UNMEASURED

- CI on the pushed head.
- The OIDC matrix, the Compose instrument and the browser tier on `16a1fc2d`. They were carried over from
  `3cd1c487` for the reasons above.
- The queue gate `oidc-native-recorded` was not run. It needs the controls array merged into
  `summary.json`, and no scratch merge helper was run this time.
- Activity selections and grants are not wired into `deploy/multitenant/config.js`, and the
  export-expiry `removeArtifact` is not composed in production. Neither the corpus nor Compose needs them;
  both stay open follow-ups.
- API ingest refusal and socket disconnect under suspend were not wired; this is the activity lane's open
  item.
- The lanes' own unit break-it controls were not repeated on the joined head. The exceptions are the
  matrix and Compose controls, the activity-oracle control, and the reproduced before-states of each repair
  listed above.
- The restore census with the api role holding a `root_writer` backend (root-admin-parity next step 3).
- Real role processes over Compose: the instrument uses stand-ins.
- prcheck runs no tests.
