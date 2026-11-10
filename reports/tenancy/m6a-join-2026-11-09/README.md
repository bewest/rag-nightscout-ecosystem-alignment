# M6a join candidate for draft PR #8898: measurement record, 2026-11-09

*Queue item MT-M6A-JOIN. One machine, one day; every figure below is quoted from the logs in this
directory. Status words: `reproduced` = this run executed it; `read-derived` = from reading
code or logs, not executed.*

## 1. Anchors (from `git log` at the time of writing)

| tree | commit |
|---|---|
| PR #8898 head before this lane (`workspace/multitenant-20261102`, = `/tmp/crm-tenant-order-integration-20261107`) | `ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364` |
| OIDC harness branch `codex/oidc-native-harness-20261109` (merged first) | `3b09131e9c33bd765a58e6a25ce48c1fb8edd372` |
| tokenFile branch `codex/vault-token-file-20261109` (merged second) | `0c5479584a39f68edb6b1eb2e1228129eb9722ac` |
| join merge commit | `7ec700a584395a66f566530903a504f10b1a988e` |
| follow-up A (shared `tokenFile` reader) | `9b2c5e50` |
| follow-up B (IPC `Map` dispatch) | `80f00394e4b1612a8d1cf6613d34b8f89147911e` = **frozen head for every suite below** |
| alignment `main` at start | `b8de4e15cbbea6ca8e14e2f616cfda4eb95d5563` |
| worktree | `externals/work/crm-m6a-join-20261109`, branch `codex/m6a-join-20261109` |
| Node / npm install | v22.23.4; `npm ci` in this worktree (871 packages, exit 0; `crm-m6a-join-20261109-npm-ci.log` beside the worktree) |

## 2. Merges

Both merges with `git merge --no-edit`, no cherry-pick, squash or rebase.

| step | result | conflicted paths |
|---|---|---|
| `git merge codex/oidc-native-harness-20261109` | fast-forward to `3b09131e` (that branch already contains ed2 via its merge commit `124699bd`) | none |
| `git merge codex/vault-token-file-20261109` | `ort` merge `7ec700a5`; auto-merged `lib/server/serve/preview-config.js` and `tests/tiers.json` (the only two files both branches touch) | none |

## 3. Follow-up A: `tokenFile` for the two remaining Vault credential loaders (`9b2c5e50`)

The path validator and per-call sink reader moved from `preview-config.js` into a shared
`lib/secrets/vault-token-source.js`; `preview-config.js` keeps its messages and behaviour.
`lib/human-session/access-config.js` (OIDC_ACCESS_CONFIG `vault` block) and
`lib/server/serve/owner-credential-config.js` (`ownerCredentials.tenants[]`) now take exactly one of
`tokenEnv` / `tokenFile`, read the sink on every call, fail closed (`SECRETS_PROVIDER_UNAVAILABLE`
from Transit, `HUMAN_SESSION_UNAVAILABLE` from the access signer) and never fall back to the
environment. `lib/secrets/vault-access-signing.js` already passes `{signal}` to `getToken` and
collapses any throw into `HUMAN_SESSION_UNAVAILABLE`, so it is unchanged. The brief's "three
getToken sites" are therefore two loader edits plus one consumer confirmed as already conforming.
The core preview guide (`multitenant-api-preview.md` in cgm-remote-monitor's architecture docs) still show `tokenEnv` only; the tokenFile
branch did not document `tokenFile` either; left for the coordinator.

New test `tests/vault-token-file-sources.test.js` (unit tier): 10 passing. Together with the
tokenFile branch's `tests/preview-vault-token-file.test.js` (5 passing): 15 passing.
`npm run test:tiers`: `# 605 test files, 8 tiers: ok`.

Controls (`followup-a-controls.log`), both red for the stated reason and restored to 15 passing with
a clean tree, head unchanged `80f00394`:

| ablation | mutant | symptom |
|---|---|---|
| 1. load-time cache | `tokenFileReader` reads the sink once with `readFileSync` at construction | `9 passing, 6 failing`: the "rewritten token" test and the "fails closed" test in each of the three suites (human, owner, preview); the fail-closed ones die at load with `ENOENT … absent-*-token` / `invalid preview tenant…` |
| 2. environment fallback | each of the three loader sites returns the env token when the sink read throws | `12 passing, 3 failing`: the "never falls back to an environment token" test in each suite, `AssertionError: Missing expected rejection` |

## 4. Follow-up B: IPC dispatch through a fixed `Map` (`80f00394`)

`lib/server/realtime/ipc.js` `handler()` builds `new Map(Object.entries(operations))` once (after the
existing all-functions check), looks the request path up with `table.get(req.url)` and refuses with
`SOCKET_IPC_REQUEST_REFUSED` when the entry is `undefined`; the call site uses the looked-up
function. Same entries, same refusal paths, same 503 body. `lib/authorization/storage.js` untouched.
Whether CodeQL stops flagging the pattern is **UNMEASURED** here (no CodeQL run; read-derived
expectation only).

The four IPC-consuming unit files (`realtime-preview`, `operation-cohort`, `operation-cohort-peers`,
`profile-wire-response`): 53 passing. Control (`followup-b-control.log`): lookup keyed off
`req.url + '/x'` → `49 passing, 4 failing` (private handler, IPC lifetime ×2, profile wire handler);
restored 53 passing, tree clean.

## 5. Lint

`npx eslint` on every JS file changed since ed2 (97 files, `eslint-changed-files.log`):
**2 errors, 54 warnings**. Both errors pre-exist on the OIDC branch (introduced by `eadf41f8`, not by
this lane): `tests/human-session-http.test.js:19:31` parsing error on `||=` (the eslint parser
config does not accept logical assignment; Node 22 runs it) and `tests/human-session-stream.test.js:6:17`
unused import `credential`. The files this lane touched: 0 errors, 27 warnings, all
`security/detect-non-literal-fs-filename` on the sink reader and the test's `writeFileSync` calls
(same class the tokenFile lane recorded).

## 6. Nine-stage OIDC matrix (`oidc-matrix/`, reproduced)

`tests/native/oidc-matrix/run.sh --out oidc-matrix` then `run.sh --out oidc-matrix/controls
--control single:single-shipping-eight-hour-exchange,browser:csrf,consumer:consumer-current-data-authority-bypass`
(the same three controls the MT-OIDC-NATIVE record executed). The controls array from
`controls/controls.json` was copied into `summary.json` (field `controlsRun` records the source), as
the gate reads one file.

| fact | value |
|---|---|
| sourceCommit | `80f00394e4b1612a8d1cf6613d34b8f89147911e`, branch `codex/m6a-join-20261109`, clean tree |
| stages | vault-single 193 ms, vault-multi 193 ms, mongo-sessions 410 ms, pg-sessions 551 ms, mongo-http 1724 ms, owner-consumer 2453 ms, owner-authority 2338 ms, owner-browser 3775 ms, owner-compatibility 2088 ms: all **PASS**, every family true |
| matrix wall clock | 15037 ms (21:21:58Z to 21:22:13Z); controls run 13888 ms |
| controls | 3 of 3 red-then-green: `lib/server/enclave.js`, `lib/human-session/http.js`, `lib/server/tenant-app/data-access.js` mutants |
| images | postgres `@sha256:721873c3…`, mongo `@sha256:1f995ad6…`, vault `@sha256:962a9287…` (full digests in `summary.json`) |
| oref0 / Chrome | `d219baf9559d62a8bb0bd42014192a2d7c0839ef` / Google Chrome 154.0.8037.57 |
| gate | `node tools/queue/gates/oidc-native-recorded.js reports/tenancy/m6a-join-2026-11-09/oidc-matrix/summary.json` → `13 checked, 0 failing`, exit 0 (`oidc-native-recorded-gate.log`). Before the controls were merged it was `1 failing` on `mutant controls red-then-green: 0 of 0` (so the gate does fail on an incomplete record). |

## 7. Repository suites on the frozen head `80f00394`

Environment: `my.test.env` = `tests/ci.test.env` with `CUSTOMCONNSTR_mongo` repointed to a `mongo:7`
container on 127.0.0.1:27517 (server version 7.0.43 read from `mongosh`, image
`mongo@sha256:9854f7139445d766a9523571d6f047530c45547460ffcf8259eb2bf4264632ca`).

### 7a. `npm run test:affected -- --since ed2ced00` (`test-affected.log`, exit 17)

129 changed files, 405 of 605 tests implicated. Unit 1714 passing / 17 failing; dom 22 / 3;
dependency 368 passing / 2 pending; core 4; harness 27; integration 2501 passing / 378 pending /
**72 failing**; stress 0 passing / 3 failing; browser 352 / 7. **The integration, stress and browser
figures of this run are invalid**: the Mongo container died at 21:24:43Z, between the unit and
integration tiers' completion, with WiredTiger error 24 (`EMFILE`, too many open files) in
`__posix_directory_sync` → fassert 50853 → SIGABRT (`mongo-container-crash-run1.log`; container
exit code 14, RestartCount 0, not OOM). Default `nofile` inside a `mongo:7` container is 1024.
Container recreated with `--ulimit nofile=1048576:1048576`. The unit tier had finished before the
crash and its 17 failures reproduce in isolation (section 8).

### 7b. Full tiers, repaired environment (`test-all-and-browser.log`; bundle = `npm run bundle-dev`)

| tier | files | passing | pending | failing |
|---|---|---|---|---|
| unit | 229 | 3010 | 0 | 24 |
| dom | 19 | 191 | 0 | 3 |
| dependency | 32 | 367 | 2 | 1 |
| core | 26 | 319 | 0 | 0 |
| harness | 10 | 99 | 0 | 0 |
| integration | 247 | 3617 | 534 | 0 |
| stress | 1 | 18 | 0 | 0 |
| browser | 41 | 672 | 0 | 12 |

`test:all` exit 24, `test:browser` exit 12; container still running afterwards.

### 7c. Re-run of the bundle-sensitive tiers after `npm run bundle` (production) (`rerun-production-bundle.log`)

The 7 unit "Production page bundle resource budgets", the 1 dependency "D3 browser surface
coverage" and the 5 browser "Populated application page budgets" failures were artefacts of the
development bundle: with the production bundle the unit budget file is 9 passing, dependency
368 passing / 2 pending / 0 failing, dom 191 / 3 (unchanged), browser **677 passing / 7 failing**.

**Final figures for the frozen head, production bundle:** unit 3017 passing / 17 failing (3010 + 7
budget tests recovered; 17 as in 7a and 7b), dom 191 / 3, dependency 368 / 2 pending / 0, core 319,
harness 99, integration 3617 / 534 pending / 0, stress 18, browser 677 / 7.

## 8. The failures that remain: what they are and where they came from

Baseline method: two detached scratch worktrees (`3b09131e` = OIDC head alone; `ed2ced00` = PR head
before this lane), the six failing unit files run in each.

| set | on `80f00394` (join) | on `3b09131e` (OIDC alone) | on `ed2ced00` | attribution |
|---|---|---|---|---|
| six unit files (`owner-configuration-persistence`, `preview-serving-status`, `tenant-deployment-operations`, `tenant-alarm-composition`, `write-step`, `write-intent`) | 170 passing / 17 failing | 170 / 17 (same titles) | 177 / 1 | **16 unit failures arrived with the accepted OIDC candidate `c0a67b69`**, not with the join or follow-ups A/B; 1 (`tenant-alarm-composition` "filters actual successful evaluator plugin output", `ALARM_ACTUAL_EVALUATOR … expected false, actual true` at line 120) pre-exists on ed2 in this environment, deterministic in 3 of 3 runs |

The 16 by mechanism (read-derived from the assertion text; the repair is not this lane's):

1. `tests/tenant-deployment-operations.test.js`, 9 tests: `OPERATIONS_CATALOGUE_UNADMITTED:
   lib/human-session/candidate.json` from `lib/tenant-operations/catalogues.js:123`. The OIDC branch
   (`b486f6f6`) added `lib/human-session/candidate.json` without admitting it to the deployment
   operations catalogue.
2. `tests/write-intent.test.js` ×2 and `tests/write-step.test.js` ×1 (gate G2 / write-boundary
   controls): `lib/server/websocket.js: canonical socket result delegation expected once, found 0`
   and `one deliberate mutation boundary: expected 1, actual 2`. `lib/server/websocket.js` changed
   only in `b486f6f6` (+33/−3) between ed2 and the OIDC head. `node scripts/check-write-boundary.js`
   on the join head prints the same finding. This touches D23 (every socket write forwarded to the
   api write step) and needs the owner's attention before the PR moves.
3. `tests/owner-configuration-persistence.test.js` ×3 ("projected owner catalogue and next-cycle
   source consumers"): `observe()` asserts at lines 277 and 285 fail (`expected 0, actual 1` on
   emitted count; strict-equal mismatches on the next-cycle result).
4. `tests/preview-serving-status.test.js` ×1 ("reproduces omitted-status client retry …").

dom (3, `client.alarm-no-reading`, `client.alarm-snooze`): `TypeError: Cannot read properties of
undefined (reading 'alarmHigh')`, `(reading 'forEach')`, `client.dataUpdate is not a function`.
These tests load the production bundle from `node_modules/.cache`; the OIDC branch changed
`lib/client/index.js` (+30), `lib/client/hashauth.js` (+86) and added `lib/client/human-session.js`.
browser (7): `tests/browser/legacy-reports.test.js` ×4 (expected console error
`Failed to load resource … 404`, got `[]`) and `tests/browser/startup-retries.test.js` ×3 ("The first
failure must not retry immediately", `expected 0, actual 1`). Attribution for dom and browser is in
section 8a (ed2 baseline with its own bundle); a first attempt to baseline them in the ed2 scratch
tree was invalid because that tree shared this worktree's `node_modules` and therefore this
worktree's bundle (the borrowed-bundle trap).

**Two corrections to section 8 (2026-11-10, repair lane):** (a) the legacy-reports symptom is the
other way round: the page's console *had* `Failed to load resource … 404` and the test expects `[]`
(the 404 is the OIDC session probe; see §9.3). (b) The three `owner-configuration-persistence`
failures and the `tenant-alarm-composition` failure are wall-clock time bombs in the tests, not OIDC
behaviour (§9.2, §9.5).

### 8a. ed2 dom/browser baseline (`ed2-baseline-dom-browser.log`)

The previous lane ran the same dom and browser files on `ed2ced00` with that tree's own `npm ci`
and production bundle: dom files **14 passing**, browser files **11 passing**, 0 failing. The
3 dom and 7 browser failures on the join were therefore introduced by the OIDC candidate (its
client changes), not by the environment. Reproduced.

## 9. Repairs (branch `codex/m6a-join-20261109`, after the frozen head `80f00394`)

Each repair: mechanism, commit, the control executed (break, see red with the named symptom,
restore). All reproduced on this machine unless marked read-derived.

| # | commit | what failed | mechanism | repair | control (red symptom) |
|---|---|---|---|---|---|
| 0 | `521c35e0` (coordinator) | write-intent ×2, write-step ×1; `check-write-boundary` | `b486f6f6` wrapped `socket.on` registration in `lib/server/websocket.js` to refresh human authority before each write, so the D23 gate counted 0 canonical delegations | refresh moved into an optional `beforeWrite` hook on `createHandlers` (`lib/server/socket-write-handlers.js`) | coordinator's: ignoring the hook fails the human write-after-logout recheck |
| 1 | `cc1789bd` | `tenant-deployment-operations` ×9 `OPERATIONS_CATALOGUE_UNADMITTED: lib/human-session/candidate.json` | the whole-deployment census discovers every candidate JSON; the OIDC tables were in no family | `human_session` family (human_identities, human_sessions, human_access_tokens, human_logout_events) in `DEFAULT_CATALOGUE` after `access`; fixture namespace, two-tenant synthetic seed, census counts 46/47 tables, 22 kinds, 24 candidates; table row in `lib/tenant-operations/README.md` | reverting the catalogue entry: 19 passing / 9 failing, the original `OPERATIONS_CATALOGUE_UNADMITTED` ×7 and `OPERATIONS_NAMESPACE_INVALID` expectation ×2; restored 28 passing |
| 2 | `463e2806` | `owner-configuration-persistence` ×3 (`undefined !== 190`; emitted `0 !== 1`) | arrived with `6a230b86` (owner settings, in the OIDC candidate lineage); the test fixed the evaluator instant and the reading at 2026-11-07T12:00Z, but the shipping entries query bounds unbounded reads from `Date.now()` (`lib/server/query.js` deltaAgo, read-derived line). Clock-shift measurement: green at +42 h, red at +48 h | instant and reading taken from the real clock at test start; green with the clock set to 2027-06-01 | reading aged 3 days behind the instant: 18 passing / 3 failing with the original two symptoms; restored 21 passing |
| 3 | `861a5d11` | dom ×3, browser ×7, `preview-serving-status` ×1 | `client.init` probed `GET /api/v2/oidc/session` before every startup on every deployment: an extra 404 (console error) on non-OIDC sites and an asynchronous init (dom: `client.dataUpdate is not a function`; browser: ajaxStop settled on the probe before status.json, `expected 0, actual 1`; status gate: `client.humanSession` undefined) | `app.js` sets `app.locals.humanSessions` when it mounted OIDC; `views/partials/page-scripts.ejs` renders `<meta name="nightscout-human-sessions" content="enabled">` before the bundle only then; the client probes only when the meta is present and tolerates a client without `humanSession`. New tests: two unit (`tests/human-session-client.test.js`), two browser (`tests/browser/human-session-advertised.test.js`) | (a) advertised check removed: new unit test red "unadvertised page requests status synchronously"; (b) hint never rendered: render test red; (c) a bundle built before the meta reader: browser advertised test red (no probe). All restored green |
| 4 | `f9702e56` | eslint errors ×2 | `||=` not accepted by the eslint parser config; unused `credential` import | one line each | n/a (lint) |
| 5 | `2c289a0c` | `tenant-alarm-composition` "filters actual successful evaluator plugin output" (`ALARM_ACTUAL_EVALUATOR`); also red on ed2 | same time bomb as #2, fixed date 2026-11-06T12:00Z; green with the clock set to 2026-11-01/05/07 | instant from the real clock | reading aged 3 days: original `ALARM_ACTUAL_EVALUATOR` assertion red; restored 10 passing |
| 6 | `887c7357` | eslint error (`no-useless-assignment`, `tests/native/oidc-matrix/run.cjs:203`), found by this lane's lint of `.cjs` files | initialiser never read | `let result;` | n/a (lint); matrix rerun on the final head (§10) |
| 7 | `74036ba6` | multitenant corpus: 5 failing (first full run on `2c289a0c`, `first-test-multitenant-2c289a0c.log`) | owner capability branches in the OIDC candidate (`9cdb77f5`, `68f35cd0`, `3ef957f2`) appended migrations `0003_secrets_legacy_issuance` and `0005_owner_subject_creation`, POST on subject/role collections, INSERT privileges required by the owner store startup check, and owner revocation (DELETE) fenced in the store. Attribution (`attribution-multitenant-five.log`): the five suites are 21 passing / 5 failing on `521c35e0` and on OIDC head `3b09131e`, 62 passing / 0 failing on `ed2ced00` | test expectations updated (migration lists, `Allow: POST, PUT`, roles collection 405 `Allow: POST`); owner writer gets INSERT on subjects, legacy credential metadata and roles in the owner-preview test and `tests/fixtures/owner-configuration.js` (matching `tests/native/oidc-matrix/prepare.cjs`); the owner-preview DELETE case now asserts a committed revocation of a dedicated synthetic subject (200, rows gone, one audit row) instead of 403; compose `owner_writer` gets the same INSERT grants | the original failures on `521c35e0`/`3b09131e` are the red; startup refusal surfaced as `SUBJECT_ADMIN_STORE_UNSAFE` by a temporary local diagnostic (not committed) |

Decision points the owner should confirm (not decided here):
- **#3 changes the OIDC browser design**: discovery becomes opt-in by the page server (server-rendered
  hint) instead of a universal probe. It restores ed2 startup exactly for every non-OIDC page and
  keeps the single-process OIDC site working. A multitenant page server that wants browser human
  sessions must render the hint; the compose UI (`deploy/multitenant/ui.js`) mounts no OIDC today
  and renders none. Alternative: keep the probe and accept a 404 console error and async init on
  every default-off site (that changes single-site behaviour, which the brief excludes).
- **#7 encodes owner revocation as permitted** in the owner-preview suite, following the candidate's
  own change of comment in `lib/server/serve/owner-preview.js` ("DELETE remains refused" →
  "including creation, revocation and issuance").
- **#1 restore semantics**: human sessions follow the `access` family exactly (exported, restored
  and deleted with the tenant; logical restore leaves current credentials authoritative; cloning
  is refused by `deployment.js`). No new policy was needed. Read-derived consequence: an archive
  taken before the OIDC candidate lacks `lib/human-session/candidate.json`, so whole-deployment
  admission of such an old source tree refuses `OPERATIONS_CENSUS_SOURCE_MISMATCH`, the same as any
  family added after an archive.

## 10. Final verification

Final head **`74036ba6e3572f6774fbc94ae2dc41b31922d2b7`** (`official/dev` `4a482627` already
contained; `git merge --no-edit official/dev` → "Already up to date"). Mongo `mongo:7` container
`ns-m6a-join-mongo` (nofile 1048576), running, 0 restarts.

| check | head | result | log |
|---|---|---|---|
| OIDC nine-stage matrix | `74036ba6` | 9 of 9 PASS (vault-single 193 ms … owner-browser 4074 ms), clean tree, Chrome 154.0.8037.57, oref0 `d219baf9` | `oidc-matrix-final/`, `oidc-matrix-final.run.log` |
| matrix controls | `74036ba6` | 3 of 3 red-then-green (enclave.js, human-session/http.js, tenant-app/data-access.js) | `oidc-matrix-final/controls/`, `oidc-matrix-final.controls-run.log` |
| `oidc-native-recorded` gate | `74036ba6` | before merging controls: exit 1, `mutant controls red-then-green: 0 of 0`; after: **13 checked, 0 failing, exit 0** | `oidc-matrix-final-gate*.log` |
| same matrix + gate on `2c289a0c` | `2c289a0c` | 9/9 PASS, 3/3 controls, gate 13/0 | `oidc-matrix-2c289a0c*` |
| `npm run bundle` then `npm run test:all` | `2c289a0c` | unit 3036 / 0 pending / 0 failing; dom 205 / 0 / 0; dependency 368 / 2 / 0; core 319 / 0 / 0; harness 99 / 0 / 0; integration 3617 / 534 / 0; stress 18 / 0 / 0; exit 0 | `final-test-all-and-browser.log` |
| `npm run test:browser` | `2c289a0c` | 686 passing / 0 failing (42 files); exit 0 | same |
| `node scripts/test-multitenant.js --record` | `74036ba6` | **537 passing, 1 pending, 0 failing**, exit 0, every container verified removed (ed2: 537/1/0) | `final-test-multitenant.log`, `.json` |
| first full multitenant run | `2c289a0c` | 496 / 1 / 5 failing (repaired by #7) | `first-test-multitenant-2c289a0c.*` |
| `npm run test:affected -- --since 2c289a0c` | `74036ba6` | 7 changed files, 5 implicated (integration, opt-in): 5 passing / 62 pending / 0 failing; real coverage is the multitenant row | `final-affected-since-2c289a0c.log` |
| `npm run test:tiers` | `74036ba6` | ok (606 files, 8 tiers) | same |
| `check-write-intent` / `check-write-boundary` | `2c289a0c` | 13 enrolled modules ok / 9 adapter entry points and canonical socket delegation ok; both exit 0 | `final-write-checks.log` |
| eslint, every JS/CJS file changed since ed2 | `74036ba6` | 126 files: **0 errors**, 88 warnings (`security/detect-non-literal-fs-filename` class) | `final-eslint-changed-files.log` |
| prcheck | `74036ba6` | already contains official/dev `4a482627`; exit 0 | `final-merge-and-prcheck.log` |

Between `2c289a0c` (test:all/browser) and `74036ba6` the changes are: opt-in integration test
files, one test fixture, `deploy/multitenant/config.js` and a lint-only change in the matrix
runner; covered by the multitenant corpus and matrix rows above.

## 11. UNMEASURED

- CodeQL on the IPC `Map` dispatch (§4).
- Compose deployment runtime with the new `owner_writer` grants (`deploy/multitenant/check-compose.js`
  passes and `node --test deploy/multitenant/*.test.js` is 10/10, both source-only); whether the
  compose `tenant-admin` started before this change is read-derived (it should have refused
  `SUBJECT_ADMIN_STORE_UNSAFE`).
- A single-process OIDC site rendering the meta hint end to end through `app.js` with a real
  provider: covered piecewise (template render test, bundle browser test, matrix single-mode
  stages that do not load the browser bundle).
- Whole-deployment backup/restore of the `human_session` family against PostgreSQL
  (`NS_TENANT_OPERATIONS_PG_TEST` suites ran inside the multitenant corpus; the lab
  `tools/lab/tenant-whole-c` was not run).
- `npm run test:all`/`test:browser` were not repeated on `74036ba6` (see the note under §10).

## 12. `deploy/` files changed (divergence from the nightscout-deploy mirror)

| file | commit | change |
|---|---|---|
| `deploy/multitenant/config.js` | `74036ba6` | `owner_writer`: `INSERT,UPDATE,DELETE` (was `UPDATE,DELETE`) on `tenant_authorization_subjects` and `legacy_credential_subjects`; new `INSERT` on `tenant_authorization_roles` |

No other `deploy/` file changed. The `human_session` family needed no deploy change: the compose
lifecycle selects its own catalogue list (`deploy/multitenant/restore.js` `expectedCandidates`) and
mounts no OIDC.
