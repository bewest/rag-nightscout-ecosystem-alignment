# Full acceptance of the M6b joined candidate `b70ad83f`

*Contributor-facing measurement record, captured 2026-11-10. Not edited after capture.*

Candidate: `externals/work/crm-m6b-join-20261110`, branch `codex/m6b-join-20261110`, head
`b70ad83fa4cdaeb7e6023137a05bd811d7db606a`. This is `3545236d` plus the repair for the stopped run
(`../3545236d-acceptance/`). The tree was clean before the run, after it, and at prcheck
(`porcelain=0`; the git-ignored `my.test.env` was removed afterwards). There are 16 commits from
`dc795bd1` (12 not counting merges). Baseline: `dc795bd1` (`reports/tenancy/m6a-join-2026-11-09/dc795bd1-acceptance/`).

Environment for the repository tiers and the corpus: `my.test.env` = `tests/ci.test.env` with
`CUSTOMCONNSTR_mongo=mongodb://127.0.0.1:27717/testdb`. That address is a dedicated container,
`ns-acc-mongo`: image `mongo:7` (`mongo@sha256:9854f7139445d766a9523571d6f047530c45547460ffcf8259eb2bf4264632ca`),
server 7.0.43, `--ulimit nofile=1048576:1048576`, no tmpfs. The container was removed afterwards.
Bundle: `npm run bundle` (production), exit 0. The corpus, the OIDC matrix and the native
instruments start and remove their own PostgreSQL 16.15, MongoDB 7.0.43 and Vault 2.2.1
containers. No container from this campaign remains.

## Per-suite results

| suite | command | start (UTC) | passing | pending | failing | baseline `dc795bd1` |
|---|---|---|---|---|---|---|
| unit (234 files) | `npm run test:all` | 20:16:31 | 3106 | 0 | 0 | 3072 |
| dom (19) | ″ | | 205 | 0 | 0 | 205 |
| dependency (32) | ″ | | 368 | 2 | 0 | 368 / 2 |
| core (26) | ″ | | 319 | 0 | 0 | 319 |
| harness (10) | ″ | | 99 | 0 | 0 | 99 |
| integration (250) | ″ | | 3643 | 547 | 0 | 3618 / 534 |
| stress (1) | ″ (`test:all` exit 0) | | 18 | 0 | 0 | 18 |
| browser (42 files) | `npm run test:browser` | 20:20:04–20:23:54 | 686 | 0 | 0 | 686 |
| multitenant opt-in corpus (49 suites) | `node scripts/test-multitenant.js --record test-multitenant.json` | 20:24:07–20:29:10 | 550 | 1 | 0 | 537 / 1 (47 suites) |
| OIDC nine-stage matrix | `tests/native/oidc-matrix/run.sh --out oidc-matrix` | 20:29:1x | 9/9 PASS, complete, 14987 ms, zero leftovers | | | 9/9 |
| matrix controls | `run.sh --out oidc-matrix/controls --control single:single-shipping-eight-hour-exchange,browser:csrf,consumer:consumer-current-data-authority-bypass` | –20:29:46 | 3/3 red then green, 14142 ms | | | 3/3 |
| gate `oidc-native-recorded` | `node tools/queue/gates/oidc-native-recorded.js …/oidc-matrix/summary.json` | | 13 checked, 0 failing, exit 0 (before merging controls: 1 failing, `mutant controls red-then-green: 0 of 0`, exit 1) | | | 13 / 0 |
| `test:tiers` check | `npm run test:tiers` | | `614 test files, 8 tiers: ok` | | | 609 files, ok |
| write intent | `node scripts/check-write-intent.js` | | 13 enrolled modules, 3 identifier-match reads, exit 0 | | | same |
| write boundary | `node scripts/check-write-boundary.js` | | 9 adapter entry points + canonical socket delegation, exit 0 | | | same |
| lint | `npm run lint` (`eslint lib`) | | 0 errors, 49 warnings, exit 0 | | | 0 errors |
| eslint, changed JS/CJS/MJS since `dc795bd1` (47 files) | `npx eslint <files>`; `git diff --check dc795bd1 HEAD` | | 0 errors, 39 warnings; diff-check exit 0 | | | |
| key retention native | `NS_KEY_RETENTION_DOCKER_TEST=1 … mocha tests/tenant-key-retention.integration.test.js` | 20:29:51 | 6 | 0 | 0 | lane: 6 |
| ownership PostgreSQL/HTTP family | `NS_TENANT_OWNERSHIP_DOCKER_TEST=1 mocha` (3 files, per the lane README) | 20:29:53 | 20 | 0 | 0 | lane: 20; 0 `ns-own-*` left |
| internal API compose | `tests/native/internal-api-compose/run.sh --out compose-final` | 20:29:56 | SCENARIO_PASS + drain PASS, exit 0; 0 containers, 0 networks left | | | lane: exit 0 |
| compose control | `run.sh --out compose-control --control blanket-window` | –20:30:05 | exit 1 (expected), `DRIVER_FAILED lifecycle invalidation of suspended A on api: SOCKET_IPC_UNAVAILABLE` (same symptom as the lane) | | | lane: exit 1 |
| prcheck | `bash tools/review/prcheck/prcheck.sh externals/work/crm-m6b-join-20261110` | 20:30:05 | `OK`, exit 0; already contains official/dev `4a482627`; the push would send 534 commits on it (baseline 518) | | | OK |

Every lint warning is `security/detect-non-literal-fs-filename` or similar (`eslint.log` has them
in full; `eslint.txt` lists the files and the totals).

Deltas against the baseline: unit +34, integration +25 passing and +13 pending, corpus +13 passing
with 2 more suites (`NS_KEY_RETENTION_DOCKER_TEST`, `NS_TENANT_OWNERSHIP_DOCKER_TEST` now in the
flag list), tiers +5 files. These are the new tests of the joined lanes and the provisioning test
registered in the integration tier.

Matrix images, recorded by digest in `oidc-matrix/summary.json`: postgres
`@sha256:721873c3…`, mongo `@sha256:1f995ad6…`, vault as recorded. Chrome 154.0.8037.57, oref0
`d219baf9`. Controls: single red `shipping single subject JWT lifetime is eight hours`; browser csrf
red `owner transport status oracle`; consumer red `next DATA operation must read current role
authority`; each restored PASS. The controls array was copied into `summary.json` (`controlsRun`)
by a scratch merge helper, which refuses on a `sourceCommit` mismatch.

## Files

`.txt` are the kept summaries; `*.log` are gitignored raw output. `test-all-and-browser.{txt,log}`,
`test-multitenant.{txt,log,json}`, `oidc-matrix/` (+ `controls/`), `oidc-matrix-run.{txt,log}`,
`oidc-matrix-gate*.txt`, `tiers-and-write-checks.txt`, `eslint.{txt,log}`,
`native-key-retention-and-ownership.txt` (raw `native-key-retention.log`, `native-ownership.log`),
`native-compose.{txt,log}`, `compose-final/`, `compose-control/`, `prcheck.{txt,log}`.

## UNMEASURED

- CI on the pushed head.
- The lanes' own UNMEASURED lists stand. Among them:
  - real role processes over Compose (the compose instrument uses stand-ins);
  - ownership composition into a serving role and its deployment grants;
  - key-retention production custodian, Vault policy and artifact expiry;
  - concurrency beyond the raced cases.
- The lanes' unit break-it controls (key-retention ablations, ownership C1–C7, oidc-single-provision
  C1–C7) were not repeated on the joined head. Only the matrix and compose controls were.
- prcheck runs no tests. `official/dev` was `4a482627` when it fetched.
