# cgm-remote-monitor 16.0.0 — contents

**Status: in development. Nothing tagged or released.** 16.0.0 is the next release from `dev`
(maintainer, 2026-10-21; queue `RT-VERSION`). Contributor-facing; full technical depth intended.
Measured 2026-10-26 (to 19:10Z) against `official/dev` `47723cda` (the merge of #8605, cut 5) and
`official/master` `c6a0d8ed` (= `v15.0.9`, the shipping release), in
`externals/cgm-remote-monitor-official` after `git fetch official`, with `gh pr view`, `gh run view` and
`gh api` for PR, CI and branch-protection state.

> Complements the generated changelog. The changelog is authoritative for *what merged*; this file
> records what the release is made of so far, how each figure was measured, and what is unsettled.

BF-72, BF-161 and BF-191 appear by mechanism only: all three are live on 15.0.9, and this repository is public.
The decisions that shape the release are in [decisions.md](decisions.md); the test runs are in the
[16.0.0 integration record](../../docs/30-design/remedial/rc-16.0.0-integration-record.md); the call
for testers is [testing-notes.md](testing-notes.md) (not written yet).

## Identity

| | |
|---|---|
| Product | `cgm-remote-monitor` |
| Directory name | `cgm-remote-monitor-16.0.0`; the number is decided (maintainer, 2026-10-21) |
| Tag to be cut | `v16.0.0` and `16.0.0`, both forms, as for `15.0.7` to `15.0.9` |
| Merged part | `official/master..official/dev` |
| Base (shipping) | `c6a0d8ed` = `v15.0.9` (released 2026-10-21) |
| `dev` head | `47723cda` (merge of #8605, cut 5, 2026-10-26 17:32:44Z, by AndyLow91), tree `200a1c00` |
| Commits on `dev` | 857 — `git rev-list --count official/master..official/dev` (484 without merges, `--no-merges`) |
| First-parent commits on `dev` | 35 — `git rev-list --first-parent --count official/master..official/dev`: 34 PR merges and the cycle's version bump `04d435eb` |
| Diff on `dev` | 745 files, +123438/−15023 — `git diff --shortstat official/master official/dev` |
| Merged on 2026-10-26 | 15 PRs, from `b29f1bf7` to `47723cda`: 460 files, +79273/−3101 — `git diff --shortstat b29f1bf7 official/dev`; the eleven after `207a8352`: `git rev-list --first-parent --count 207a8352..official/dev` = 11 |
| `package.json` version | `16.0.0` — `git show official/dev:package.json \| grep '"version"'` |
| `engines.node` | `^22.23.4 \|\| ^24.22.1 \|\| >=26.12.1` (AndyLow91's `6a146a4c`, "require Node Brotli security patches"; supersedes the decided `^22.12 \|\| >=24`) |
| Docker base image | `node:24.22.1-alpine` for builder and runtime (`32489dc5`); the runtime stage deletes the image's global `npm` and `npx` (`Dockerfile` on `dev`) |
| Connector pin | `nightscout-connect` exactly `0.1.0`, as in 15.0.9 (`git show official/dev:package.json`) |
| MongoDB | driver `mongodb` `^7.6.0` (cut 3); the README states 5.0 through 8.0 as supported and 4.4 and earlier as unsupported (`README.md:157-158` on `dev`); driver 7 starts on 4.4 and refuses 3.6, 4.0 and 4.2, which get the boot error page (BF-182; decisions). Docker Compose starts `mongo:6.0.27` (`docker-compose.yml:12`; 15.0.9: `mongo:5.0.32`) |
| Web framework | `express` `^5.2.1`, `helmet` `^8.3.0` (cut 5; `package.json` on `dev`); 15.0.9 locks `express` 4.22.2 |
| Staging PR | #8824 (`dev` → `master`, "new dev branch post 15.0.9 release"): open, head `47723cda`, `mergeable` `MERGEABLE`, `mergeStateStatus` `BLOCKED`, `reviewDecision` `REVIEW_REQUIRED`; every check reported on the head passed except the jobs skipped by design (*Publish to Docker Hub* and *Build Docker image* on the `pull_request` run, *Validate Docker image* on the push run) — `gh pr view 8824`, `gh pr checks 8824`. `master`'s branch protection requires `Run Tests (22, 6)`, `Run Tests (22, 4.4)` and `Run Tests (24, 6)` (`gh api repos/nightscout/cgm-remote-monitor/branches/master/protection`, read 2026-10-26); no workflow on `dev` emits `Run Tests (22, 4.4)` since #8833, so #8824 cannot meet `master`'s required checks until that setting changes, and it also needs one approving review |
| CI on `47723cda` | `push` run 40369632641 (16 jobs: 15 passed, *Validate Docker image* skipped) published `dev`'s image at 17:42:36Z (`nightscout/cgm-remote-monitor:latest_dev` and `dev_47723cda…`; Docker Hub reports `latest_dev` updated 17:42:32Z); `pull_request` run 40369639616 passed; CodeQL passed on both events (40369632350, 40369639665) — `gh run view <id> --json jobs`; the 2026-10-26 merges' runs are R14 in the [integration record](../../docs/30-design/remedial/rc-16.0.0-integration-record.md) |
| CI on the 2026-10-25 merges | every `push` and `pull_request` run on `5de8505d`, `fd3792e5`, `eb44a9c2`, `78524be4` and `b29f1bf7` passed on attempt 1 and each push run published an image (integration record R13); `eb72a1d3` and `93f152bd` published, `a20469dc` failed Firefox and skipped publishing (R6, R9, R10) |

## Provenance

Every figure below is labelled. **reproduced**: something was executed and the output observed.
**read-derived**: read from source, a PR body or CI metadata. Commit counts, SHAs, PR states, CI
results and the conflict counts are reproduced with the commands shown. No test suite was run on
`dev` by this session; the runs reported are the PR authors' and peer sessions', read from the PR
bodies (see the integration record). No live site, vendor account or Docker image was run.

## What is merged so far

Merge SHAs: `git log --first-parent --format='%h %ad %an %s' --date=iso official/master..official/dev`;
merge times are `gh pr view <n> --json mergedAt`. The first nineteen merges below were made on
2026-10-25 (#8834, #8835 and #8838 by bewest, the others by AndyLow91), the last fifteen on 2026-10-26
(#8843, #8848 and #8850 by bewest, the others by AndyLow91). Register ids refer to the
[backfix register](../../docs/30-design/remedial/nightscout-backfix-register.md).

| PR | merged (UTC) | merge | head | author | register | queue | what |
|---|---|---|---|---|---|---|---|
| #8831 | 10:50:42 | `d7249f48` | `ecdd2af1` | AndyLow91 | — | — | opt-in `THEME=modern` responsive dashboard theme; existing themes unchanged (52 files, +3011/−224) |
| #8825 | 13:12:03 | `dfd659ba` | `b20a710b` | bewest | BF-173 | `BFQ-173` | the Careportal Bolus Wizard converts the profile's targets and sensitivity to the display units |
| #8826 | 13:21:08 | `e2857b89` | `9e3e1cc0` | bewest | BF-174 | `BFQ-174` | the bolus calculator uses the profile the caller names; merged after #8825, as required |
| #8827 | 13:29:41 | `1c70fc8c` | `8d2a3b8c` | bewest | BF-157 | `BFQ-157` | a treatment's glucose bubble reads units spelled `mmol/L` as mmol/L (display position only) |
| #8823 | 13:36:05 | `4c1a5f1a` | `d00576b9` | bewest | — | `RT-1` | `BRIDGE_SERVER=US`/`ous`/URL mapping in the bridge-to-connect compatibility layer (also folded into cut 1; see [Merge state](#merge-state)) |
| #8819 | 13:48:08 | `f09a9382` | `bbca2892` | javier-erro | BF-172 | `BFQ-172` | the Bolus Wizard Preview converts the profile's values to the display units |
| #8797 | 13:57:31 | `ecf32222` | `a4badcc6` | bewest | BF-09 | `BFQ-09` | the socket's 2 s duplicate check keeps a zero temp basal, 100 % temp, cancel, zero bolus or zero carbs |
| #8816 | 14:05:19 | `b1dce5e8` | `fb2c0da2` | awss1i | — | — | a snooze chosen on a page that is not signed in lasts as long as chosen |
| #8812 | 14:25:53 | `bb56989c` | `ba5f7f4b` | cpruijsen | — | — | off-by-one reading count in the glucose distribution report (issue 7659) |
| #8808 | 15:00:27 | `1cae31e1` | `dbd2a7be` | awss1i | — | — | the Loopalyzer keeps BG readings on or close to a 5-minute mark |
| #8828 | 16:29:06 | `eb72a1d3` | `12154df9` | bewest | BF-55, BF-58 | `RT-1` | cut 1: retire jsdom (option C), the enforced Node floor, removal of the legacy Dexcom Share and MiniMed CareLink bridges, version 16.0.0 |
| #8834 | 17:44:48 | `93f152bd` | `f3d73f43` | bewest | BF-176 | `BFQ-176` | `axios` `^0.34.0` and `lodash` `4.18.1` are runtime dependencies: a production install with `IMPORT_CONFIG` boots again |
| #8835 | 17:59:06 | `a20469dc` | `477d5200` | bewest | BF-163 | `BFQ-163` | `compression` 1.8.2, `follow-redirects` 1.16.1, `source-map-js` 1.2.2 (`feb3944c`, `ad458fa0`, `341b843a`) and `sanitize-html` 2.18.1 (`0293d640` the bump, `1eb986ad` `tests/purifier.corpus.test.js` pinning the stored text of 35 inputs), and a merge of `dev` `93f152bd` (`477d5200`) |
| #8838 | 19:42:01 | `2bc298b9` | `039be646` | bewest | BF-158, BF-177 | `RT-CONNECT-TEARDOWN`, `BFQ-158`, `BFQ-177`, `RT-D3-SUITE` | test and CI hygiene, 10 commits (below) |
| #8836 | 20:03:15 | `5de8505d` | `df2f37ab` | AndyLow91 | — | — | "Fix middleware DoS, harden credentials and streamline CI": `body-parser` 1.20.9, the status request's credentials move from the URL to headers, credential redaction in logs, `Referrer-Policy` and `Cache-Control` changes, dependency floors, CI action pins, no `npm` in the runtime image (24 files, +753/−99; below) |
| #8833 | 20:10:15 | `fd3792e5` | `9ac9d534` | AndyLow91 | — | — | "ci: remove temporary Node 22 / MongoDB 4.4 check": the `Run Tests (22, 4.4)` matrix entry and its docs (5 files, +14/−18) |
| #8837 | 21:28:47 | `eb44a9c2` | `af7ba73a` | bewest | — | `RT-2`, `RT-CONNECT-PIN-CUTS` | cut 2: page bundles and the build/runtime split (204 files, +22567/−3291; below) |
| #8839 | 21:57:16 | `78524be4` | `ad8a73e2` | bewest | — | `RT-TEST-TIERS` | the test tier map, its check and inner-loop selection (`test:affected`, `test:smoke`) (15 files, +1001/−11; below) |
| #8840 | 22:41:24 | `b29f1bf7` | `5be6f217` | mixa2010 | — | — | the Loopalyzer keeps 288 five-minute bins on 23- and 25-hour days (issue 8156) (4 files, +565/−69; below) |
| #8542 | 10-26 01:23:04 | `428b20b7` | `31f4bf21` | tim2000s | — | — | the Statistics Summary (AGP) report and modern report charts (33 files, +3125/−646) |
| #8843 | 10-26 05:20:27 | `720e60de` | `7fd2415e` | bewest | BF-185, BF-192 | `RT-CI-DIAGONAL`, `BFQ-185`, `BFQ-192` | CI: the Node × MongoDB diagonal, a no-database job, *Tests pass*, seeded test order; the browser tier runs in CI again (24 files, +437/−156) |
| #8848 | 10-26 06:03:54 | `1f10cd9d` | `952d0f49` | bewest | — | `RT-CI-DIAGONAL` | `dev` and `master` pushes build and publish Docker images again; two order-dependent tests (4 files, +27/−5) |
| #8850 | 10-26 06:22:23 | `207a8352` | `b6c11a93` | bewest | — | — | three more tests that passed only in alphabetical order (4 files, +23/−7) |
| #8841 | 10-26 10:23:14 | `e09bca3b` | `5901961c` | bewest | — | `MOD-WRITE-VALIDATION` | opt-in `WRITE_VALIDATION` (`off`, `log`, `reject`) for Temporary Target writes on API v1 and v3 (11 files, +918/−11; below) |
| #8842 | 10-26 10:33:08 | `85e5108a` | `148db86b` | bewest | BF-92, BF-93, BF-159 (token half), BF-160, BF-180, BF-190 | `BFQ-92`, `BFQ-93`, `BFQ-159`, `BFQ-160`, `BFQ-180`, `BFQ-190` | alarms and live updates reach the page (16 files, +455/−28; below) |
| #8844 | 10-26 10:59:10 | `ad05e140` | `0d54d072` | bewest | BF-179, BF-182 | `RT-REBASE`, `BFQ-179`, `BFQ-182` | cut 3: MongoDB driver 7, selected jQuery UI widgets, native help tooltips, Compose `mongo:6.0.27` (91 files, +10090/−194) |
| #8845 | 10-26 11:34:16 | `900abf7a` | `50219945` | bewest | BF-145, BF-152 (step 1), BF-165, BF-166, BF-167, BF-169, BF-170, BF-186 | the eight `BFQ-` items | record identity and the write contract (25 files, +1314/−107; below) |
| #8847 | 10-26 12:15:29 | `e34efdef` | `35fc8167` | bewest | BF-183 | `RT-5`, `BFQ-183` | cut 4: trusted proxies through one module, `mime-types`, moment-timezone 0.6, csv, semver 7, ESLint 10, webpack 5.110 (135 files, +5981/−1286) |
| #8849 | 10-26 12:43:22 | `3b2e1a68` | `0772cb47` | bewest | BF-46, BF-48, BF-49 (warning), BF-156 | `RT-BOOT-INDEX-AWAIT`, `BFQ-46`, `BFQ-ENV`, `BFQ-156` | boot waits for its indexes (at most 20 s), API v3 auto-prune handles its delete, API v3 and webhook settings read in `env.js` (17 files, +843/−60; below) |
| #8852 | 10-26 13:31:17 | `a911cdb2` | `b471074b` | AndyLow91 | — | — | API v1 profile POST payloads are validated before iteration: malformed entries and binary bodies answer 400, and batches are capped at 10,000 records; addresses CodeQL alerts 134 and 135 (3 files, +67/−10) |
| #8851 | 10-26 14:38:38 | `43050723` | `3bf675dd` | mixa2010 | — | — | `toRoundedStr` rounds on the decimal digits, so dose labels on midpoints round correctly (1.005 U shows as `1.01U`, not `1U`) (2 files, +74/−4) |
| #8730 | 10-26 15:31:40 | `89b7ebdd` | `2b32fe67` | sulkaharo | BF-132 | `RT-PR-8730` | Crowdin translations (33 files, +111/−12); it keeps `dev`'s corrected strings |
| #8555 | 10-26 16:12:41 | `09d0def8` | `371c4642` | samuelpert | — | — | opt-in `SHOW_SECONDS` dashboard clock seconds, a browser setting and an environment variable (13 files, +153/−7); closes issue 8048 |
| #8605 | 10-26 17:32:44 | `47723cda` | `a77cb146` | AndyLow91 | — | `RT-3` | cut 5: Express 5, Helmet 8, Axios 1, EJS 6, entities 8, `mime-types` 3, Swagger UI 5, APNs 8, a native Pushover client, a maintained notification cache, Flot 4 (204 files, +59400/−1515) |

Before merging, AndyLow91 merged `dev` into most branches and added commits of his own (read with
`git log` and `git show`):

- #8825: `b20a710b` "resolve profile units at calculation time": `getUnits(spec_profile, time)` takes
  a time, and the calculator reads the profile's units at the record's event time, the time its
  targets and sensitivity are read at; 2 more cases in `tests/careportal.test.js`.
- #8819: `bbca2892`, the same for the Bolus Wizard Preview (`getUnits(undefined, sbx.time)`), which
  answers the review point drafted on 2026-10-21 that `getUnits(sbx.time)` passed a time where it
  takes a profile name; `tests/boluswizardpreview.test.js` +57.
- #8828, after `806ff2f0`: `2c46e35b` (runtime-upgrade guide), `6a146a4c` (the floor above),
  `d49a81f7` (CI resolves the newest Node patch), `32489dc5` (the Docker base image above; `.nvmrc`
  `24.22.1`), the `dev` catch-up merge `43eb6066`, `36fa3121` (keeps a Node 22 × MongoDB 4.4 test
  cell), `76c73056` and `13507b38` (CI) and `12154df9` (a bounded Firefox month-report test).

#8838's ten commits, on `dev` `a20469dc`: `38049fe6` (the redundant connector teardown listener
removed, `RT-CONNECT-TEARDOWN`), `fb0e1217` (BF-158: the count=0 block isolated from records other
files leave, plus the runtime-cache flush found by peer session -b7), `89d19b5b` (BF-177: the test's
time-zone stand-in is a UTC profile; the report is verified correct by running it), `879ab51e` (the
duplicated `BRIDGE_SERVER mapping` block removed, 37 → 22 cases), `e45041c6` (stale Node floor text in
`docs/test-specs`), `f7856a44` (`RT-D3-SUITE`: two treatment-drag clamp browser tests), `29e8a36b` (the
CI edge matrix, 31 → 10 test and browser cells, about 81 runner-minutes less per run), `cab8896f` (the
API3 SEARCH hook's timeout: on an empty database the first insert waits on boot's unawaited index
creation; the product fix is `RT-BOOT-INDEX-AWAIT`), `aa7438ee` (Babel checked against the engines
floors) and `039be646` (MongoDB 5.0 and 8.0 as the CI edges, and the docs).

**#8836** (read from the PR body and `git show`; the runs are AndyLow91's). Six commits
(`git log 2bc298b9..df2f37ab`): `e0872924` (dependency and credential findings), two merges of `dev` (`f09cb431`, `15a84907`),
`be806a57` (privacy for GET authentication), `78aacc15` (CI) and the merge `df2f37ab` ("Merge dev CI
hygiene while preserving the 14-job matrix"). What it changes, by mechanism:

- `body-parser` `^1.20.6` → `^1.20.9` (lock 1.20.6 → 1.20.9): the PR body states that a malformed
  compressed request body can terminate the server, and adds child-process regression probes for it
  and for `compression` 1.8.2 (on `dev` since #8835). **15.0.9 locks `body-parser` 1.20.6 and
  `compression` 1.8.1** (`git show official/master:package-lock.json`), the versions these replace.
- The page's first status request no longer carries the API secret hash or token in its URL: it sends
  them as `api-secret` and `Authorization` headers (`lib/client/index.js`), and `lib/api/status.js`
  reads them there. Query-string credentials are still accepted for existing clients. **15.0.9's
  `lib/client/index.js:58` appends the credential to the status URL.**
- Logs and responses: credential-bearing request URLs and error details are redacted
  (`lib/server/log-privacy.js`, new), CSP reports are sanitised before logging, `Referrer-Policy:
  no-referrer` is set whether or not CSP is on, `Cache-Control: no-store` is set on status responses
  and before redirects and authorization (`lib/middleware/credential-cache.js`), and setup-mode errors
  use the production error handler.
- Dependency floors: `dompurify` 3.4.17, `moment` 2.31.0, `fast-uri` 3.1.9, `ip-address` 10.7.5,
  `serialize-javascript` 7.1.4, `csv-parse` 7.0.3 (development), nyc's nested `uuid` (lock versions on
  `dev`, reproduced). The PR body reports `npm audit` affected-package entries 23 (full) and 16
  (`--omit=dev`) before and two after, both in the one chain with no patched release:
  `@parse/node-apn` → `node-forge` 1.4.0, GHSA-86w9-cpqp-85rv; the body says no remotely reachable path
  was established and keeps APNs as it is (read-derived; not re-run).
- CI: the 20 mutable action references pinned to commit SHAs; superseded `pull_request` runs cancelled;
  publishing waits for every test job; a manual extended mode that never publishes. The runtime Docker
  stage deletes `npm` and `npx`.
- Tests on the PR head (read from the body): Node 24.22.1 against MongoDB 6.0.27, 3474 passing, 3
  skipped, 0 failing, with coverage; 51 focused privacy and header cases on Node 22.23.4 and 24.22.1.

**#8833** removes only the `Run Tests (22, 4.4)` matrix entry and updates `CONTRIBUTING.md`,
`README.md`, `docs/runtime-upgrade.md` and `docs/test-specs/browser-tests.md` (`daee0c9e`, merge
`9ac9d534`). Its body states that `dev` requires only `Run Tests (24, 6)`, and that `master` still
requires `Run Tests (22, 4.4)`, which an administrator must remove before the next release PR into
`master` (read; the protection read above agrees).

**#8837, cut 2, as merged.** After `ee94b148`: AndyLow91's merge of `dev` `fd3792e5` (`2efd78ac`,
"Merge dev security and CI updates into Cut 2"; conflicts in `.github/workflows/main.yml`,
`lib/server/app.js`, `package.json` and `package-lock.json` per the body), `62b1509d` (the env-runner nyc
fix: `--all=false` on the inner nyc and `docs/test-specs/env-runner.md`; author Ben West, the same
patch as the peer session's `bd941200` by `git patch-id`) and AndyLow91's `af7ba73a` ("fix: preserve
Maker delivery across recipient failures": Maker keys are sent in parallel and one key's error no
longer stops the other keys or the later events; each request has a 10 s deadline; the log line names
the event instead of the request URL, which carries the Maker key; 5 files). **15.0.9 logs that URL**
(`lib/plugins/maker.js:111` on `official/master`). Whether `af7ba73a` also closes BF-137 (several
Maker keys: out of order, a failed key not retried) was not checked; `BFQ-137` is unchanged. Tests on
the merged branch (read from the body): Node 24.22.1, MongoDB 8.0.29, 3730 passing, 4 skipped, 0
failing, with coverage; `test:core` 316; Chromium page-startup and credential-bootstrap selection 49
passing; the pruned runtime with `IMPORT_CONFIG` passes. CI on the PR head `af7ba73a`: run 40231697337,
attempt 1, passed. `lib/server/query.js` on `dev` now walks queries with `queryLeaves`
(`lib/utils/query-leaves.js`); `traverse` is no longer in `package.json` (reproduced with `git grep`).

**#8839** (read from the body): `tests/tiers.json` places 317 test files in eight tiers (unit 97,
dom 17, dependency 20, core 26, harness 7, integration 123, stress 1, browser 26). AndyLow91 merged
`dev` `eb44a9c2` into it (`90e2cfde`, "Merge dev and align test tiers with Cut 2") and added `ad8a73e2`
(invalid tier or file selections exit non-zero before any test starts). The tier check and the harness
tier run in the main backend CI jobs. `npm test` and `test-ci` are unchanged.

**#8840** (read from the body; issue 8156). On a 23- or 25-hour day the Loopalyzer built 276 or 300
five-minute bins instead of 288, so every series was rejected and the charts were blank; ranges that
included such a day dropped that day's series. The fix anchors the axis on a 24-hour local day and
bounds per-day slots to 288 (`lib/report_plugins/loopalyzer.js`, `docs/test-specs/loopalyzer-dst.md`,
two test files). Commits: HeartCoreDev's `63ad23be`, AndyLow91's merge of `dev` `a383f0f9` and his
`5be6f217` ("align DST curves with local clock markers"). The body reports 13 of 13 slot tests failing
before the change and 20 of 20 passing after (`TZ=Europe/Berlin`). The PR head's run 40240553524 needed
a maintainer approval on attempt 1 (`action_required`, a fork PR) and passed on attempt 2.

**The 2026-10-26 merges** (read from the PR bodies and `git log <merge>^1..<merge>^2`; the runs are the
authors'):

- **#8841**: `e8125d89`, `6e842c07`, `a2e5fe49` (bewest) and AndyLow91's `5901961c` ("validate effective
  Temporary Target updates"). Rules for every app, checked only when `WRITE_VALIDATION` is `log` or
  `reject`: targets above zero, bottom not above top, `units` `mg/dl` or `mmol` (client spellings
  accepted), each target plausible for its units (above 30 labelled `mmol` is a mg/dL number; below 20
  labelled `mg/dl` is a mmol/L number), durations zero or more. Under `reject` a v1 batch stores its valid
  items and answers 200 with one object per item, the refused ones without `_id` and with a `refused`
  member, plus `Warning: 299`. App-specific limits (AndroidAPS's 72–180 mg/dL) are not applied.
- **#8842**: BF-92 (`5fb199b3`, with BF-190), BF-93 (`91d9a4db`), BF-180 (`bb1ad38e`, the careportal temp
  target converted once and labelled `mg/dl`), BF-159's token half (`72f3cc09`) and BF-160 (`2556b35b`).
  On a page showing `---`, a non-glucose alarm (pump, loop, age, stale data, CGM error codes and the rest
  outside the default group) is now presented when either the page's high or low alarm for its level is
  on; glucose alarms with no reading stay unpresented. The PR body asks reviewers to confirm stale-data
  and CGM-error alarms on a page showing `---`.
- **#8844 (cut 3)**: merged from `0d54d072`, AndyLow91's commit over his own merge of `dev` into cut 3
  (`831c32fc`). Driver 7 with an explicit `batchSize: 1000` on bulk reads, BF-182's boot error page
  (`8f238fc5`), BF-179 (`200c1361`), jQuery UI 1.14.2 widgets and native help tooltips, Compose
  `mongo:6.0.27` (a database major upgrade for an existing Compose deployment).
- **#8845**: BF-145 (`d4566292`), BF-165 (`0d5edc66`), BF-166 (`c62a16c9`, a profile re-sent with its
  `_id` is merged with `$set`, the write contract's Q1 rule; a field sent as `null` is stored as `null`),
  BF-167 (`0edb1db9`, test only), BF-169 (`a1ab22b6`, `539856ef`), BF-170 (`304827fd`, `b899edc1`:
  API v3 create, PUT and PATCH refuse a body `_id` with 400), BF-186 (`b34f6703`), BF-152 step 1
  (`faffe875`, `API3_SETTINGS_STRICT_READ_ENABLED`, off by default), and AndyLow91's `50219945`
  ("Require update permission for profile POST merges").
- **#8847 (cut 4)**: one client-address module (`lib/server/client-ip.js`) for every consumer; with
  `TRUST_PROXY` unset, 15.0.9's resolution (BF-88); BF-183 (`54115e95`); the dependency majors above;
  `npm run lint` without errors and in CI.
- **#8849**: `488def62` (boot waits for collection and index creation, at most 20 s, then warns and
  continues; a first start on an empty database takes about 3 to 4 s longer on MongoDB 8.0), BF-156
  (`a5b569b9`), BF-46 (`1d63df57`), BF-48 (`8e4d30d3`) and BF-49's start-up warning (`8e3717e3`).
- **#8605 (cut 5)**: AndyLow91's head `a77cb146` over his merge of `dev` `09d0def8` (`246f2274`), which
  contains session -f8's catch-up chain (`98d2f9a0`, `574870f8`). Its last commits restore the CORS
  preflight's `200` text `OK` (`ad56423d`), give browser jobs 15 minutes (`f4abce3c`) and set `HOME`
  for the Firefox date probe (`a77cb146`). The body leaves live Pushover emergency delivery,
  acknowledgement and cancellation, alarm de-duplication over its real window, APNs delivery to a phone,
  production hosting, upgrade and rollback, and physical-device accessibility as maintainer-owned
  acceptance work.

None of these merged trees was re-run locally by this programme. The merged trees' CI is in
[Identity](#identity) and the integration record (R13, R14).

## Merge state

- **Every cut is on `dev`** (reproduced 2026-10-26 with `git merge-base --is-ancestor <head> official/dev`,
  exit 0 for each, and exit 1 against `official/master`): cut 1 `12154df9` (#8828), cut 2 `af7ba73a`
  (#8837), cut 3 `0d54d072` (#8844), cut 4 `35fc8167` (#8847), cut 5 `a77cb146` (#8605).
- **Session -f8's 2026-10-26 catch-up merges reached `dev` through cut 5, not through cuts 3 and 4.**
  `76b19fb0` (cut 3) and `8bf6c9b2` (cut 4) are not ancestors of #8844's and #8847's merged heads:
  AndyLow91 merged `dev` into cut 3 himself (`831c32fc`) and added `0d54d072`. Cut 5's head `a77cb146`
  contains `98d2f9a0`, which contains both, so all three are in `dev` (`git merge-base --is-ancestor`,
  reproduced).
- **#8823 merged twice, without duplicated code** (reproduced on `eb72a1d3`): one
  `bridgeServerToConnect`, in `lib/server/bridge-connect-compat.js`; the duplicated test block was
  removed by #8838 (`879ab51e`).

## Version: 16.0.0, major

Decided by the maintainer on 2026-10-21 (`RT-VERSION` answered). Surfaces touched (versioning policy
§6.2), read from the merged PRs. A ticked box is a surface the merged code touches; an unticked one
marked *owed* has a candidate change whose classification is not recorded yet:

- [x] S1 the HTTP API and the realtime socket contract: #8797 stores records the socket used to drop as
  copies; #8845 makes API v3 refuse a client body `_id` with 400 (BF-170), answers a v1 re-send with its
  stored `_id` (BF-165) and merges a profile re-sent with its `_id` instead of answering 500 (BF-166);
  #8852 answers malformed API v1 profile uploads with 400 and caps them at 10,000 records; #8841 adds
  `refused` slots to v1 batch replies under `WRITE_VALIDATION=reject`; cut 5 moves the routes to
  Express 5 (the query parser keeps `allowPrototypes: true` and sets `arrayLimit: 1000` and
  `parameterLimit: 1000`, `lib/middleware/configure-request.js:8-9`; read-derived: Express 4's extended
  parser used `qs`'s default `arrayLimit` of 20)
- [x] S2 plugin interface, boot sequence or client bundle: cut 2 (#8837) splits the client into page
  bundles and replaces the boot sequence and the client event bus with native code (a third-party
  plugin that hooks into the page is to be tested before upgrading; no plugin was run against it);
  #8849 makes boot wait for its indexes; #8831 adds an opt-in theme
- [x] S3 environment-variable surface: new `THEME=modern` (#8831), `WRITE_VALIDATION` (#8841),
  `API3_SETTINGS_STRICT_READ_ENABLED` (#8845) and `SHOW_SECONDS` (#8555); a start-up warning when
  `SECURE_HSTS_HEADER_INCLUDE_SUBDOMAINS` is set (BF-49); leftover legacy bridge settings stop the site
  with a page naming the replacements (cut 1); `DEBUG_MINIFY` no longer has an effect (cut 2)
- [ ] S4 stored document shape, *owed*: #8845's BF-166 changes what a profile re-sent with its `_id`
  stores (merged with `$set` where it failed before), and #8842's BF-180 changes how a careportal temp
  target on an mmol/L site is stored; neither is classified here
- [x] S5 Node or MongoDB runtime floor, **major**: `lib/server/runtime-policy.js` reads `engines.node`
  and exits at boot outside `^22.23.4 || ^24.22.1 || >=26.12.1`, which stops Node 20, 21, 23 and 25,
  and 22.0–22.23.3, 24.0–24.22.0 and 26.0–26.12.0. Driver 7 (cut 3) refuses MongoDB 3.6, 4.0 and 4.2
  (BF-182's boot error page); the README states 5.0 through 8.0. CI on `dev` (job names of push run
  40369632641): *Run Tests* (22.23.4, 8.0), (26, 5.0), (24, 6), (22, 6); *Tests without a database*
  (22.23.4), (26); *Maintained MongoDB* (26, 8.0.29); browsers on Node 26 × Chromium, Firefox and WebKit
- [x] S6 an ingestion path, **major**: the legacy Dexcom Share bridge and MiniMed CareLink
  (mmconnect) are removed; Dexcom Share data comes in through `nightscout-connect`
- [ ] S7 alarms or notifications, *owed*: #8842 (BF-92) presents device and other non-glucose alarms
  on a page with no reading where none was presented before, which is the policy's question 8
  (MINOR, never waivable, rule R2: at least a minor and a release note); #8816 changes how long a
  snooze lasts on a page that is not signed in; cut 2's `af7ba73a` changes how IFTTT Maker events are
  sent to several keys; cut 5 replaces the Pushover client and the notification cache and moves APNs
  to 8 (live delivery not checked, #8605's body)
- [x] S8 the version string: `16.0.0`
- [x] S9 what the client computes and shows a person: BF-172, BF-173 and BF-174 change the Bolus Wizard
  Preview and the Careportal Bolus Wizard where the profile and display units differ, or where a
  profile other than the active one is chosen; #8812, #8808 and #8840 change report figures; #8851
  changes how dose labels round; #8542 adds the AGP report

Not on the list, and recorded for the release notes: #8836 changes response headers
(`Referrer-Policy`, `Cache-Control`), where the page sends its credentials, and removes `npm` from the
runtime Docker image.

**Classification:** MAJOR, because of S5 and S6 (cut 1) and S5 again (cut 3's MongoDB floor).
**Directory name says:** 16.0.0. **Settled?** Yes, by the maintainer, 2026-10-21.

## In flight for this release

Read 2026-10-26, 19:10Z. Every cut is merged ([Merge state](#merge-state)).

| work | branch | head | state | queue |
|---|---|---|---|---|
| shared persistence and stored-data contracts | `wip/architecture-data-contracts`, **draft #8854** (AndyLow91, base `dev`) | `880b7369`, one commit on `dev` `47723cda` | open draft, mergeable; every check on its head passed. Decided 2026-10-26: in 16.0.0 after four alignment conditions (outcome B, [decisions](decisions.md)) | `ARCH-8854`, `WRITE-CONTRACT`, `MOD-WRITE-VALIDATION-READ` (related) |
| Crowdin translations | `crowdin_incoming`, **#8855** (sulkaharo) | — | opened 2026-10-26 18:52Z; not examined | — |
| BF-72: a caller-supplied regular expression can hold the database for minutes | `bf/regex-limits`, in the private fork of its draft advisory | `1833ab00` on `dev` `04d435eb` | in the fork; no fork PR opened yet; owes a merge of `dev` | `BFQ-72` |
| BF-161: a deeply nested pattern on three query endpoints makes that request fail | `bf/entries-pattern-limit`, in the private fork of its draft advisory | `d2c4df9f` on `dev` `04d435eb` | in the fork; no fork PR opened yet; owes a merge of `dev` | `BFQ-161` |
| BF-191: a stored treatment can stop the server process, and keeps doing so after a restart | private, through the maintainer's advisory process | — | open in the register | `BFQ-191` |
| BF-193: write paths log whole records | `bf/16.0.0-log-privacy`, **draft #8856** (the maintainer, base `dev`) | `8ae43eb4`, one commit on `dev` `47723cda` | draft PR opened 2026-10-26 | `BFQ-193` |
| the re-send and merge contract: `ID-SIMPLE-MATCH`, Q1b (a `null` in an update removes the field), BF-195 (a stale profile pushed over the socket after a re-send) and the devicestatus `identifier` rule, one PR | `bf/16.0.0-null-removes`, **draft #8859** (the maintainer, base `dev`) | `fc170a4c`, five commits on `dev` `47723cda`: `ID-SIMPLE-MATCH` `8d0f9a22`, Q1b `913d0895`, BF-195 `1bdce62c`, merge `cf2a2a67`, the devicestatus `identifier` rule `fc170a4c` (read from `git log`) | draft PR opened 2026-10-26; the devicestatus `identifier` rule is on it (v1 and v3: a re-send with a stored `identifier` writes nothing and the reply carries the stored `_id`); `npm test` 4374 / 3 / 1 and `test:all` 4702 / 3 / 1, the 3 environmental (`ENOSPC` file watchers); with #8854 one import-line conflict and a 3-line matrix expectation change for whichever merges second | `ID-SIMPLE-MATCH`, `WRITE-CONTRACT`, `BFQ-195` |

**#8854** (read from its body and `git diff --stat official/dev...refs/triage/pr-8854`, 31 files,
+934/−45; the runs are the author's). Its body targets the
[architecture review](../../docs/30-design/modernization/cgm-remote-monitor-architecture-review-2026-10-25.md)
and says it is a foundation, not the complete proposed write-intent service, and not merge-ready. By
mechanism: the six v1 and internal collection modules, the legacy socket and API v3 go through a
shared write step (`lib/storage/write-step.js`, new, a wrapper over the driver collection that keeps
existing replies and emits a data-free `storage-write-committed` event with no consumer yet); the
opt-in Temporary Target rules also apply to the socket's add, update and unset; a non-mutating stored
data inspection (`lib/storage/read-contract.js`, new) adds a `Nightscout-Data-Warnings` header to API v3
responses; a read-only diagnostic command (`scripts/diagnose-data.js`) and a write-boundary check
(`scripts/check-write-boundary.js`); guards for malformed cache values, authorization identities and
history timestamps; a future `srvModified` is reported, not rewound; Mocha runs that find zero tests
fail (`--fail-zero`). The body reports, against `dev` `47723cda`: the 336 original CRUD-matrix results
match a fresh baseline exactly, integration 2,233 passing / 1 pending, unit 1,441, Chromium 650; and five
sensor-age assertions failing in Europe/London around the October DST change on unchanged `dev`.

BF-72's fix, by mechanism: a length cap on every pattern and a time limit on every query whose filter
holds a regular expression, generated ones included; a refusal check for caller-written patterns
only behind `QUERY_REGEX_REFUSE_UNSAFE`, default off. BF-161's fix: a nesting-depth limit checked
before the pattern is parsed or expanded. Both keep the intended uses in the maintainer's public gist
`dbe590ab` working, and each is published with the release that carries it.

**Cut 2, #8837, before its last push** (read from the PR body and `git log`; the runs are the preparing
session's; kept as the record of `ee94b148`; the merged head is in [What is merged so far](#what-is-merged-so-far)). The
branch is a fast-forward of the published `b6e8c7cd`: 26 first-parent commits on top of it, 185
commits ahead of `dev` `a20469dc`. It merges `dev` three times: `04a7968d` (`eb72a1d3`, 9 conflicting
paths), `dd2e0cfd` (`93f152bd`, #8834) and `94242483` (`a20469dc`, #8835). The follow-ups are
`14ba4686` (the narrowed D3 surface gains `bisector`, `curveBasis` and `curveMonotoneX`, which #8831's
modern chart needs; without them the production main page with `THEME=modern` threw while drawing the
trend), `17a9d48a`, `4354fac3`, `1e9ea6f6`, `ba32eca4`, the CI edge commits `a7eb6942`, `bdb6c733` and
`b8ff91cb`, and `ee94b148`, the page-bundle budget (decided, option A). Tests on `ee94b148` (Node 24.22.1,
`TZ=UTC`): `npm test` 3691 / 4 / 0, Chromium 540 / 0, budget 9 / 9. Earlier, on `b8ff91cb` (host zone
America/Los_Angeles): Node 22.23.4, 24.22.1 and 26.12.1 each 3542 / 4 / 4 (the 4: the two budget
cases, the BF-177 test and the API3 hook timeout, both fixed by #8838 since); Firefox 540 / 0.
`queryLeaves` was verified against `traverse` on 50,000 generated and 20 edge queries: 0 differences.

**#8837's CI** (reproduced from GitHub run metadata): run 40225696687 on `ee94b148`, attempts 1 and 2,
failed the required check *Run Tests (24, 6)* and *Maintained MongoDB (26, 8.0.29)*, each 3690 passing,
1 failing: `tests/env-runner.test.js` "Native env runner process contract passes file values through
nyc into a Mocha child" exceeded its 10 s timeout. The case's inner nyc instruments all of `lib/`
(`.nycrc` `all: true`) under `test-ci`'s outer nyc; the local runs, without coverage, did not see it.
The fix reached the branch as `62b1509d` (the same patch as the peer
session's `bd941200`), after AndyLow91's merge of `dev` `fd3792e5` (`2efd78ac`); run 40231697337 on the
merged head `af7ba73a` passed.

**`sanitize-html` 2.18.1 (#8835)** (read from the PR body). The update was bundled into #8835 on the
maintainer's direction (themed PRs). Against 2.17.5, `npm audit` listed four `sanitize-html` advisories
and against 2.18.1 none: GHSA-x3q4-9hxx-gx8m, GHSA-cv27-6wvh-8x7j, GHSA-jxwj-j7wr-gfrw and
GHSA-g8qq-57p8-ggw5 (totals 23 → 22, and 16 → 15 with `--omit=dev`, npm 11.19.1, 17:27:34Z and
17:30:04Z). GHSA-374f-7chj-9948 never applied: its range is `>=2.17.7 <2.18.0`, and `dev` locked 2.17.5.
2.18.1 brings the htmlparser2 12, domhandler 6, domutils 4, domelementtype 3 and dom-serializer 3
majors, all reached only through `sanitize-html`; it declares `node >=22.12.0`, inside the 16.0.0
floor. Of the 35 inputs in `tests/purifier.corpus.test.js`, 34 are stored identically; the one change
is listed under [For the release notes](#for-the-release-notes). The combined head `477d5200` ran
3422 / 3 / 0 (Node 24.22.1, MongoDB 7.0.43, `TZ=UTC`).

## Modernization cuts: handoff

Written for AndyLow91 and the maintainer, who asked on 2026-10-25 for cuts 3–5 to be pushed so the
remaining work could be shared; kept as the record of the handoff. All five cuts are merged (cut 3
#8844, cut 4 #8847 and cut 5 #8605 on 2026-10-26). The "remaining work" lists below were written
against the handoff heads (`76b19fb0`, `8bf6c9b2`, `98d2f9a0`) and are not re-checked on the merged
heads, except where noted.

**Method** (decided 2026-10-12, `RT-PROPAGATION`): `dev` is merged up the stack, `dev` → cut 3 → cut 4
→ cut 5; nothing is rebased, so each push fast-forwards the published branch. Each cut is resolved
against the one below it, so `dev`'s fixes reach cut 4 and cut 5 through cut 3's resolutions. PRs are
stacked: cut 3 to `dev` (#8844), cut 4 as draft #8847 based on `chore/compose-mongodb6`, and #8605's base
is AndyLow91's call (suggested: `chore/mime-exposure-review`, so its diff shows only cut 5). When a
base branch is merged and deleted, GitHub retargets the PR above it.

**Rules every catch-up applied:** version `16.0.0`; `dev`'s `engines`, Node files and CI matrix;
`nightscout-connect` exactly `0.1.0`; `sanitize-html` 2.18.1; `lodash` exactly 4.18.1; lockfile
regenerated by npm, never hand-merged; every new test file given a tier (`tests/tiers.json`); `dev`'s
fixes kept on every security, storage and dosing path, each checked by reverting it and watching its
test fail; with `TRUST_PROXY` unset, 15.0.9's address resolution (BF-88).

| cut | head | fixes folded in | verified (reproduced, Node 24.22.1, `TZ=UTC` unless noted) |
|---|---|---|---|
| 3 | `12d1f645` (#8844) | BF-182 (boot error page when driver 7 refuses the server), BF-179 (production-only install explains itself) | `npm test` 3838 / 0 / 4 on MongoDB 5.0.33, 7.0.43 and 8.0.34 at `8f238fc5`; 3877 / 0 / 4 on 8.0.34 at `12d1f645`; Chromium 579 / 1 and Firefox 580 / 0 at `12d1f645` (the 1: BF-192, from `dev`); the budget moves to 6.8 MB with #8843; MongoDB 4.2.24 gets the boot error page, 4.4.24 connects |
| 4 | `99b6f68b` (#8847) | BF-183 (storage socket stops logging subscription credentials) | `npm test` 3887 / 0 / 4 on 5.0.33 and 8.0.34, and on 8.0.34 in America/Los_Angeles, at `32a3c0ac`; 3921 / 0 / 4 on 5.0.33 at `99b6f68b`; Chromium 591 / 1 (BF-192); `TRUST_PROXY` unset behind a TLS proxy answers 200, and 307-to-itself with cut 4's original default |
| 5 | `506cc41b` (#8605) | — | `npm test` 4045 / 0 / 3 on MongoDB 5.0.33 and 8.0.34, and on 8.0.34 in America/Los_Angeles; Chromium 638 / 1 (BF-192) and Firefox 639 / 0; reverting BF-70's refusal, the operator allowlist, Express 5 query preservation, a Pushover status check or the notification cache's expiry each fails its test; `TRUST_PROXY` unset behind a TLS proxy answers 200, 307-to-itself with the old default |

**2026-10-26: `dev` merged up again** after #8843 (CI diagonal), #8848 (Docker publish) and #8850
(test order isolation): cut 3 `76b19fb0`, cut 4 `8bf6c9b2`, cut 5 `98d2f9a0`, each a fast-forward of its
published head. Only `.github/workflows/main.yml` conflicted (cuts 4 and 5: `dev`'s split jobs, cut 4's
lint step in the no-database job, cut 5's connector step and database-upgrade rehearsal kept, the
replica-set job dropped) and `docs/runtime-upgrade.md` (cut 5). The new CI lanes reproduced locally on
each cut (Node 24.22.1): the no-database tiers in America/Los_Angeles and shuffled, integration and
stress on MongoDB 5.0.33 in America/Los_Angeles and on 8.0.34 shuffled (seed 40226791404), Chromium and
Firefox: cut 3 2014 + 18 integration, 580 browser; cut 4 2031 + 18, 592; cut 5 2038 + 18, 639; all
passing after #8850. The shuffled lane found four order-dependent tests already on `dev`, fixed there by
#8848 and #8850, not by the cuts.

Found by the merges and fixed on the branches: bson 7 `ObjectId`s carry own fields, so cut 2's query
walker walked into them (cut 3, `5aa1e749`); `git` merged `dev`'s alarm-socket body into cut 4's
handler signature, so every access-token alarm subscription would have thrown (cut 4, in the merge
commit; the September rehearsal hit the same); two API sub-apps called a `compileTrust` that `dev`'s
`client-ip.js` does not export, so the server would not boot (cut 4). In cut 5, the merge deleted dev tests
without a conflict where cut 5 had moved them (the profile editor defaults and empty-name tests, the
chart-container height race and six quick-pick tests), all restored; body-parser 2.3.0 failed dev's
HTTP middleware probe under Express 5 (lockfile 2.4.0, floor enforced by the dependency test); dev's
ajv 8 and `mocha.diff` overrides were below cut 5's majors; and the jsdom shim's `atob` recursed once
entities 8 loaded.

**Remaining work, cut 3:** the modern theme's tooltip palette does not style the native tooltip;
`views/index.html` and the service worker still load `css/jquery.tooltips.css`;
`tools/probe-legacy-bridge-transport.js` needs bridge packages `dev` removed; some cut 3 plans describe
September CI; a few small bulk reads added on `dev` have no batch bound.

**Remaining work, cut 4:** the lockfile holds minimizer-webpack-plugin 5.13.0, because 5.13.1 needs
schema-utils ^4.6.0 and npm kept 4.3.3 (postinstall failed); the `terser-webpack-plugin` override no
longer matches anything; the Firefox editor-time probe step lacks `HOME: /root`, and the lint step's
condition was fixed, both to be confirmed in CI; the spring-gap basal selection is an open discrepancy
in `tests/timezone-modernization.test.js`.

**Remaining work, cut 5:** live checks this programme cannot do without real credentials: a
Pushover emergency alarm's send, acknowledgement and cancel (the native client posts the cancel; whether
the old GET was ever accepted is unknown), notification de-duplication and receipts over a real
15-minute window, a Loop APNs remote command to a phone, and IFTTT Maker under Express 5; the CORS
preflight's `200` text `OK` was restored by AndyLow91's `ad56423d` before the merge (#8605's body);
`js-yaml` is declared as a devDependency so webpack-cli 7's optional peer resolves; the
`istanbul-lib-processinfo.uuid` override no longer applies; dev's `TRUST_PROXY` notes still compare
against cut 5's unadopted `395f3207`.

**Across the cuts:** WebKit and the Node 22.23.4 floor were not run locally (CI runs them, but see the
browser row in [Known defects](#known-defects-on-dev-now)); BF-07's `getDataRef` caller in
`lib/api/entries/index.js` has no pinning test (reverting it stays green; filed by session -f4); cut 5's
alarm transports (Pushover native client, notification caches, APNs 8) need a live delivery check,
which this programme cannot do without real credentials; #8843 (CI diagonal) and each cut change
`.github/workflows/main.yml`; #8843 landed first and each cut took its jobs.

## Known defects on `dev` now

| defect | what | exposure | queue |
|---|---|---|---|
| Firefox legacy-reports wait | `tests/browser/legacy-reports.test.js` "should produce some html" timed out at its fixed 30 s wait (`12154df9`) in one or two Firefox cells of the CI runs on `93f152bd` (`pull_request`) and `a20469dc` (both events), so the push run on `a20469dc` skipped the Docker publish; and once more on #8836's head `df2f37ab` (run 40228187718 attempt 1, *Browser tests (26, firefox)*, 463 passing, 1 failing; attempt 2 passed). Since cut 2 merged (`eb44a9c2`), `dev`'s test uses the progress-aware wait (fails after 15 s with no completed request, 60 s ceiling; `tests/browser/legacy-reports.test.js:136-144`), and *Browser tests (26, firefox)* passed in every push and `pull_request` run on `5de8505d`, `fd3792e5`, `eb44a9c2`, `78524be4` and `b29f1bf7` (one run each, so not yet evidence that the flake is gone) | test only; no register entry filed | `RT-2` (merged) |
| browser tests not running in CI | Since #8839 (`78524be4`), *Browser tests (26, chromium/firefox/webkit)* print no test output and pass: `scripts/test-tiers.js` lists files with `git ls-files`, ignores git's exit status, and inside the Playwright container (step `HOME=/root`) git refuses the checkout as dubious ownership, so the tier has zero files and the runner exits 0 (reproduced by session -5e in a root container over another uid's checkout; job logs read for push runs on `eb44a9c2`, 549 passing, then `78524be4` and `428b20b7`, none, and #8844's run 40253810477, none). Server jobs are unaffected (3820 passing per cell on `428b20b7`) | CI evidence only: no browser test gated `dev` or a PR from 2026-10-25 21:57Z until #8843 merged (2026-10-26 05:20:27Z, `720e60de`); the Chromium job of push run 40369632641 on `47723cda` runs 40 browser test files, 650 passing (job log). The fix (`listTestFiles` throws on git failure, a tier with zero files exits 2, `safe.directory` set system-wide in the browser job) on #8843 as `e767ce4e`, with a harness test that fails on the old runner | `RT-CI-DIAGONAL` (#8843, merged 2026-10-26) |
| dev pushes publish no Docker image | Since #8843 (`720e60de`), `docker-build` needs only `tests-pass`, and its implicit `success()` also sees `docker-build-pr`, which is skipped on pushes, so *Build Docker image* and *Publish to Docker Hub* are skipped: push run 40273692991 on `720e60de` passed every test lane and published nothing (job conclusions read with `gh run view`). The pushes before it (`78524be4`, `b29f1bf7`, `428b20b7`) published, so `dev`'s image stays `428b20b7`'s until the fix lands, and merges of the cuts publish nothing either | no `dev` image from `720e60de`; no release affected. **Fixed** by #8848 (merged 2026-10-26 06:03:54Z as `1f10cd9d`, head `952d0f49`; `864be741`: `!cancelled()` and an explicit `needs.<job>.result == 'success'`): `dev`'s push run 40277667345 built amd64 and arm64 and published to Docker Hub (session -5e, read-derived). #8848 also fixed two order-dependent tests (`c3a42776`, `952d0f49`) | `RT-CI-DIAGONAL` follow-up |
| reports page retained heap over budget | `tests/browser/page-populated.test.js` "initializes populated reports and bounds retained V8 heap" fails on Chromium on `428b20b7`: about 6.20 MB against 4.85 MB (`tools/page-resource-acceptance.js`), 3 of 3 runs (Node 24.22.1) and 2 of 2 (session -f4, Node 22.23.4); about 4.45 MB on `b29f1bf7`, so it arrived with #8542 (AGP reports). Hidden by the row above | a test budget, not an operator-visible failure. Resolved in #8843 (`0a33b7c7`, folded in by the maintainer): the test waits for the page's first report to finish, and the reports ceiling becomes 6,800,000 bytes, measured on `428b20b7`. Since #8542 the reports page draws a report on load; with a report showing, the new code retains about 2 MB less than the old (session -5e's measurement, read-derived) | BF-192, merged 2026-10-26 with #8843 |

Seen in `dev`'s CI on 2026-10-26 (read from the job logs, `gh run view <id> --log-failed`; neither
reproduced locally, no register entry):

| intermittent | run | what |
|---|---|---|
| development watch policy | push run 40350206994 on `89b7ebdd` (#8730) | *Tests without a database (22.23.4)*: 1339 passing, 1 failing, "Development watch policy preserves configured ignores and application watching through two restart cycles" (`tools/probe-development-watch.py`, `assert boots[-1]['value'] == cycle+1`; the test took 8.9 s). *Tests pass* failed, so no image was published from `89b7ebdd`; the `pull_request` run on the same commit passed |
| Firefox job time limit | push run 40356902994 on `09d0def8` (#8555) | *Browser tests (26, firefox)* was cancelled at the job's 10-minute limit, so *Tests pass* failed and no image was published from `09d0def8`. Cut 5's `f4abce3c` raised browser jobs to 15 minutes; Firefox took 8m12s and 10m40s on `47723cda` |
| page-startup reports recovery | `pull_request` run 40273696980 on `720e60de` (#8843) | *Browser tests (26, chromium)*: "Complete page template startup recovers the actual reports page after two failed bundle downloads" exceeded 30 s (172 passing, 2 failing with its `afterEach`); the push run on the same commit passed |
| repost-with-id find count | reported by peer session -b7 | `tests/api.entries.repost-with-id.test.js` failed once under `TEST_SHUFFLE_SEED=303`; not reproduced or verified here (`TEST-FLAKE-REPOST-FIND-COUNT`) |

**BF-176, the window.** `dev` carried the `IMPORT_CONFIG` boot crash from `eb72a1d3` (16:29:06Z, #8828)
to `93f152bd` (17:44:48Z, #8834). `dev`'s Docker image was published in between, by push run
40211895500 at 17:15:18Z, so a `dev` image pulled from then until the next publish (17:53:31Z, from
`93f152bd`) stops at boot when `IMPORT_CONFIG` is set. No release carried it.

#8831's PR body (read) also reports that `npm run test:dependencies` stops at an existing `npm ls`
error about the `axios` override on `master`, and that nine COB, IAGE and SAGE tests fail in the
Europe/London DST fall-back hour and pass in UTC; neither was measured here.

## Testing so far

The runs are in the
[16.0.0 integration record](../../docs/30-design/remedial/rc-16.0.0-integration-record.md), the same
place and form as the [15.0.9 integration record](../../docs/30-design/remedial/rc-15.0.9-integration-record.md).
No verification record is captured yet: `verification-record.{json,md}` is generated by
`tools/queue/verification-record.py` once, at release time, from the state being cut
([VERIFICATION-RECORDS.md](../VERIFICATION-RECORDS.md)), and is never hand-written, so this directory
has none until then.

## Open items a releaser must settle

As of `dev` `47723cda` (2026-10-26). The decisions already made are in [decisions.md](decisions.md).
Whether cuts 3–5 ship in 16.0.0 is answered: all three are merged into `dev`, so they ship in 16.0.0
unless reverted.

**Required before the tag** (maintainer, 2026-10-26, session -66; queue `RT-16-RELEASE`): (a) a live
Pushover and APNs delivery check (`RT-16-LIVE-ALARMS`); (b) a real-rig soak on `dev` (`RT-16-RIG-SOAK`);
(c) the BF-72 and BF-161 fork fixes merged and published with 16.0.0 (`BFQ-72`, `BFQ-161`). None is met.
BF-193 is not a pre-tag requirement; its fix shape is decided (debug-gated payload logging through
`DEBUG_LOGGING`, [decisions](decisions.md)) and is in draft PR #8856 (`bf/16.0.0-log-privacy` `8ae43eb4`).

**Decisions open, with their owner:**

1. **The scope of BF-161's draft advisory** (maintainer): publish it now for BF-151 (released in 15.0.9)
   with BF-161 as a follow-up, or extend it to include BF-161 and publish it with the release that
   carries the fix. Packet: [bfq-161](../../reports/reviewer-packets/bfq-161-bf-entries-pattern-limit.md).
2. **BF-72's test inputs** (the original author of the regex-limit commits): the tests' hostile inputs
   are to be rebuilt in code before anything is published. Packet:
   [bfq-72](../../reports/reviewer-packets/bfq-72-bf-regex-limits.md).
3. **BF-95** (maintainer): a notice for readings that arrive dated ahead of the server clock, or the
   status quo. Packet: [bfq-95](../../reports/reviewer-packets/bfq-95.md). 2026-10-25 (maintainer): verify
   `srvModified` first; on `dev` it is a server receipt time on every live path (caveat BF-181).
4. **Dependabot configuration** (maintainer): version updates targeting `dev`, dismissing alerts that
   are fixed on `dev` or not reachable, or releasing more often. Packet:
   [dependabot-config](../../reports/reviewer-packets/dependabot-config.md).
5. **BF-49's alias and dead settings keys** (maintainer; #8849's open items, `BFQ-ENV`): whether
   `SECURE_HSTS_HEADER_INCLUDE_SUBDOMAINS` becomes an alias, and what to do with the five settings keys
   nothing reads.
6. **#8842's open items** (maintainer): on a page with a reading, a non-glucose alarm is still gated by
   the high or low setting on the reading's side; and the reviewers' confirmation of stale-data and
   CGM-error alarms on a page showing `---`.
7. **#8841's open items** (maintainer): a refusal the person can see under `reject`, normalising `units`
   beyond temp targets, the plausibility thresholds (30 mmol/L, 20 mg/dL); and `WRITE_VALIDATION` set to
   any value other than `log` or `reject` reads as `off` with no message (`parseMode`,
   `lib/server/write-validation.js:42-46` on `dev`), so a misspelt `reject` turns checking off silently.
8. **The query-string array limit under Express 5** (maintainer): cut 5 sets `arrayLimit: 1000`
    (`lib/middleware/configure-request.js:8-9`), where 15.0.9's Express 4 parser used `qs`'s default of
    20 (read-derived); no decision on the value is recorded.
9. **A recorded waiver for the MongoDB 3.6–4.2 drop** (maintainer): the versioning policy §5.4 sets
    2 releases and 180 days for a runtime floor that can stop data arriving; MongoDB 4.4 was deprecated
    in 15.0.9, and 3.6, 4.0 and 4.2 stop serving with 16.0.0 (driver 7, decided 2026-10-25). The
    decision is recorded; a waiver of §5.4's window, with its reason for the release notes, is not.
10. **BF-194** (maintainer): API v1 removes `units` from a treatment with no glucose value before
    `WRITE_VALIDATION` runs, so a v1 temp target sent in mmol/L is stored with mmol/L numbers and no
    units and reads as mg/dL, in every mode, on 15.0.9 and `dev` (reproduced, integration record R15):
    keep the units, convert, or refuse. Queue `BFQ-194`.

**Found by R15 (reproduced; no register entry):**

- `npm test` and `test-ci` glob `./tests/*.test.js` (310 files) while `tests/tiers.json` maps all 377;
  the 67 outside the glob are the browser tier (40), `tests/client-core/` (26) and one harness fixture
  test. CI runs them through the tier runner; a contributor's local `npm test` skips the 27 non-browser
  files that `npm run test:all` runs.
- After driver 7 refuses MongoDB 4.2, the boot log still prints "Mongo Storage system ready"
  (`lib/server/bootevent.js:208`), though the site serves the boot error page.
- API v3 under `WRITE_VALIDATION=log` logs each bad record twice (`validate` in
  `lib/api3/generic/create/operation.js` and again in `create/insert.js`).
- API v3 refusals under `reject` write no log line; API v1 refusals do.

**Repository settings, for the maintainer** (branch protection read 2026-10-26 with `gh api
repos/nightscout/cgm-remote-monitor/branches/<branch>/protection`: `dev` requires `Run Tests (24, 6)`;
`master` requires `Run Tests (22, 6)`, `Run Tests (22, 4.4)` and `Run Tests (24, 6)` and one approving
review; `enforce_admins` is off on both). No workflow on `dev` emits `Run Tests (22, 4.4)`, so the
staging PR #8824 cannot meet `master`'s protection as it stands.

**Decided, settings change owed** (maintainer, 2026-10-26, relayed via session -66; applied by the
maintainer): `master` requires only the *Tests pass* check (job `tests-pass`, `.github/workflows/main.yml:317`
on `dev`, `if: always()`, needing every test job and the pull-request Docker validation) and one
approving review. The decision as relayed names `master`; `dev`'s required check is not part of it. Caveat: *Tests pass* accepts `skipped` as well as `success` from every job it needs
(`main.yml:327-337`), so a test job skipped in full would still let it pass.

**Follow-ups filed 2026-10-25:** `RT-BUNDLE-THEME-SPLIT` (page-bundle budget option B: load the modern
theme's code only when it is chosen; owner Andy Low or the maintainer; not started). `RT-BOOT-INDEX-AWAIT`
merged with #8849.

**Next merges** (a suggestion for the maintainers, not a decision):

1. The follow-ups, each in a themed PR: `RT-JSDOM-REST` (scope B), `ID-SIMPLE-MATCH` with BF-169's
   remaining client work, `RT-BUNDLE-THEME-SPLIT`.
2. BF-72 and BF-161 through their advisory forks, each after a merge of `dev`, published with the
   release that carries them.

**Before the tag:** the three requirements above (the live delivery check, the real-rig soak, BF-72 and BF-161), the other live acceptance checks #8605 leaves to the maintainer (Pushover emergency
delivery, acknowledgement and cancellation; alarm de-duplication over its real window; APNs delivery
to a phone; production hosting, upgrade and rollback; physical-device accessibility), the call for
testers ([testing-notes.md](testing-notes.md)), the tag message and the release notes (written last,
from the list below), a full run on the candidate in the integration record, the verification record
capture, the reconciliation in [releases/README.md](../README.md).

## For the release notes

A draft list of what the release notes must say; the notes themselves are written last, once the
candidate is named.

- The Node floor `^22.23.4 || ^24.22.1 || >=26.12.1`, and the message the server prints when it refuses
  to start.
- The legacy Dexcom Share and MiniMed CareLink bridges are removed; leftover bridge settings stop the
  site with a page naming the replacements; Dexcom Share data comes in through `nightscout-connect`.
- MongoDB 4.4 or newer is required to start (cut 3, driver 7): on 3.6, 4.0 or 4.2 the site does not
  serve data and shows a page naming the database server's version and the minimum it needs (BF-182); the
  fix is to upgrade MongoDB. 5.0 through 8.0 are the supported, tested range; 4.4 starts but is untested.
- Production-only installs (`npm ci --omit=dev` or `NODE_ENV=production`) that worked on 15.0.9 do not
  build the client bundle since cut 2 (webpack and Babel are devDependencies). BF-179 (planned for cut 3)
  turns the failure into a message naming the fix (`npm ci --include=dev`, then
  `npm prune --omit=dev --ignore-scripts`); it does not restore the old behaviour. The project's
  Dockerfile and `azure-deploy.sh` install dev dependencies and are not affected.
- Docker Compose starts `mongo:6.0.27` instead of `mongo:5.0.32` (cut 3): for an existing Compose
  deployment this is a database major-version upgrade (`docs/runtime-upgrade.md`).
- Express 5 and Helmet 8 (cut 5), and the query-string array limit (above, open item 8).
- The opt-in `THEME=modern` dashboard (#8831) and the opt-in `SHOW_SECONDS` clock (#8555).
- The opt-in `WRITE_VALIDATION` for Temporary Targets (#8841), what `log` and `reject` do, that most
  uploaders lose a refused record without showing an error, and that an unrecognised value means `off`.
- The opt-in `API3_SETTINGS_STRICT_READ_ENABLED` (#8845, BF-152 step 1), and that an AndroidAPS 4.0
  follower using a read-only token it was not given by AndroidAPS is refused when it is on.
- Record identity (#8845): API v3 refuses a client body `_id` with 400 (BF-170); API v3 PATCH, PUT and
  POST reach a record with an empty stored identifier (BF-145); a v1 re-send is answered with the stored
  `_id` (BF-165); a profile re-sent with its `_id` is merged instead of failing (BF-166).
- A `null` in an update removes the field (write contract Q1b, decided 2026-10-26; with BF-195's fix): what
  is stored changes for a re-send that matches a stored treatment, entry, profile, food or activity record, for
  an API v3 `PATCH` and for a socket `dbUpdate`, where 15.0.9 stores the `null`. A create and a replace (v1 or v3
  `PUT`) still store a `null` as sent. Arrays are replaced whole. The merge is nested: a profile re-sent with
  part of its `store` keeps the named profiles it leaves out; to remove one, send `store: {"<name>": null}` or
  replace the profile with `PUT` (as the profile editor does).
- A device status re-sent with an `identifier` that is already stored is not stored again and does not change
  the stored record (no new `srvModified`); the reply carries the stored `_id`, on API v1 and v3. API v1
  entries and device status match a re-send on `identifier`, as treatments do; an entry whose `identifier`
  matches nothing still matches on its time and type.
- Quieter server logs (BF-193): each write is logged as a summary, not the record. Set `DEBUG_LOGGING=true` to
  see the records clients send; debug logs then contain health data. Log lines change text.
- API v1 profile uploads (#8852): malformed entries and binary bodies answer 400, and a batch is capped at
  10,000 records, as on the other bounded v1 upload routes.
- BF-92 (#8842): a page showing `---` now presents device and other non-glucose alarms (a MINOR change
  under the policy's rule R2, with this note); BF-190, BF-93, BF-180, BF-159's token half and BF-160.
- The first start on an empty database waits for index creation (about 3 to 4 s on MongoDB 8.0), and a
  long index build logs a warning after 20 s and carries on (#8849).
- Dose labels round correctly on midpoints (#8851).
- The Bolus Wizard Preview and Careportal Bolus Wizard unit fixes (BF-172, BF-173) and the profile
  picker (BF-174); BF-09 (the socket's duplicate check keeps zero temps, cancels and zero amounts); #8816's snooze; #8812 and #8808's report figures.
- One stored-text change from `sanitize-html` 2.18.1 (#8835): a malformed empty
  `<textarea></textarea/>` followed by an image with an event handler is now stored as the image tag
  without its handler (`<img src="x" />`), where 2.17.5 stored nothing (the empty string). The other 34
  corpus inputs are stored identically.
- Cut 2 (merged): page bundles, build and runtime separated (`npm ci` with development
  dependencies, then prune), no late minification, `DEBUG_MINIFY` without effect, the load-failure
  panel, and a third-party plugin that hooks into the page to be tested before upgrading.
- #8836: the page sends its credentials in headers instead of the status URL (query credentials still
  work for other clients); `body-parser` 1.20.9; `Referrer-Policy: no-referrer` and `Cache-Control:
  no-store` where described above; the runtime Docker image has no `npm` or `npx`; the one remaining
  `npm audit` chain (`@parse/node-apn` → `node-forge`), with what it measures.
- #8833: MongoDB 4.4 is no longer tested at all.
- Cut 2's IFTTT Maker change (`af7ba73a`): every key and every event is attempted when one fails; the log
  names the event, not the key.
- #8840: the Loopalyzer on and across daylight-saving days.
- The known issues at the tag.

## What a reviewer must verify before this is relied on

1. That AndyLow91's `b20a710b` and `bbca2892` give the results of the 2026-10-21 reproductions for all
   four unit combinations (BF-172, BF-173); the merged trees were not re-run here.
2. Which advisory is the 1 critical in the 2026-10-25 `npm audit` on both `dev` and the refresh
   branch; this file does not name it.
3. That the PR-body figures recorded here for #8835 to #8840 and the 2026-10-26 merges match a re-run;
   none was re-run by this programme.
4. Whether #8836's `body-parser` and status-URL changes, and cut 2's Maker log line, need a notice for
   15.0.9 operators: 15.0.9 has the same code or versions (above). Recorded here by mechanism only.
5. The S4 and S7 classifications marked *owed* in [Version](#version-1600-major).

---

*Draft, 2026-10-26. Prepared locally; nothing pushed, tagged, merged or published by this programme.
Requires maintainer review before anything here is relied upon.*
