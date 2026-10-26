# cgm-remote-monitor 16.0.0 — contents

**Status: in development. Nothing tagged or released.** 16.0.0 is the next release from `dev`
(maintainer, 2026-10-21; queue `RT-VERSION`). Contributor-facing; full technical depth intended.
Measured 2026-10-25 (to 23:49Z) against `official/dev` `b29f1bf7` (the merge of #8840) and `official/master`
`c6a0d8ed` (= `v15.0.9`, the shipping release), in `externals/cgm-remote-monitor-official` after
`git fetch official`, with `gh pr view` and `gh run view` for PR and CI state.

> Complements the generated changelog. The changelog is authoritative for *what merged*; this file
> records what the release is made of so far, how each figure was measured, and what is unsettled.

BF-72 and BF-161 appear by mechanism only: both are live on 15.0.9, and this repository is public.
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
| `dev` head | `b29f1bf7` (merge of #8840, 2026-10-25 22:41:24Z, by AndyLow91), tree `b6486a8d` |
| Commits on `dev` | 415 — `git rev-list --count official/master..official/dev` |
| First-parent commits on `dev` | 20 — `git rev-list --first-parent --count official/master..official/dev`: 19 PR merges and the cycle's version bump `04d435eb` |
| Diff on `dev` | 369 files, +38473/−9028 — `git diff --shortstat official/master official/dev` |
| `package.json` version | `16.0.0` — `git show official/dev:package.json \| grep '"version"'` |
| `engines.node` | `^22.23.4 \|\| ^24.22.1 \|\| >=26.12.1` (AndyLow91's `6a146a4c`, "require Node Brotli security patches"; supersedes the decided `^22.12 \|\| >=24`) |
| Docker base image | `node:24.22.1-alpine` for builder and runtime (`32489dc5`); since #8836 the runtime stage deletes the image's global `npm` and `npx` (`Dockerfile` on `dev`) |
| Connector pin | `nightscout-connect` exactly `0.1.0`, as in 15.0.9 (`package.json` on `dev`; the `connector-pin-exposure` gate, run 2026-10-25 after the fetch, reads `official/dev` and `official/chore/build-runtime-separation` ok at v0.1.0) |
| Supported MongoDB | 5.0 through 8.0 (`README.md` on `dev`, from #8838's `039be646`); 4.4 and earlier unsupported |
| Staging PR | #8824 (`dev` → `master`, "new dev branch post 15.0.9 release"): open, head `b29f1bf7`, `mergeable` `MERGEABLE`, `mergeStateStatus` `BLOCKED`, `reviewDecision` `REVIEW_REQUIRED`; 40 checks passed, 3 skipped — `gh pr view 8824`, `gh pr checks 8824`. `master`'s branch protection still requires `Run Tests (22, 4.4)` (`gh api .../branches/master/protection/required_status_checks`), which no workflow on `dev` emits since #8833: no check of that name is on #8824's head |
| CI on `b29f1bf7` | `push` run 40241375688 (20 jobs: 19 passed, the unused *Validate Docker image* skipped) and `pull_request` run 40241381245 (18 passed, *Build Docker image* and *Publish* skipped, as on every `pull_request` run) passed every test, browser, maintained-MongoDB, replica-set and npm 12 job; the push run's *Publish to Docker Hub* passed at 22:47:04Z, so `dev`'s published image is `b29f1bf7`'s; CodeQL passed on both events (runs 40241375762, 40241381258) — `gh run view <id> --json jobs` |
| CI on the 2026-10-25 evening merges | every `push` and `pull_request` run on `5de8505d`, `fd3792e5`, `eb44a9c2` and `78524be4` passed on attempt 1, and each push run published an image: `5de8505d` run 40228940119 at 20:10:00Z, `fd3792e5` run 40229498194 at 20:17:31Z, `eb44a9c2` run 40235686217 at 21:37:57Z, `78524be4` run 40237888969 at 22:02:54Z — `gh run list --commit <sha>`, `gh run view <id> --json jobs` |
| CI on the earlier merges | `eb72a1d3` push run 40211895500 published an image at 17:15:18Z (it carries BF-176); `93f152bd` push run 40217943528 published one at 17:53:31Z (BF-176 fixed); `a20469dc` push run 40219064024 failed *Browser tests* (24.22.1, firefox) and (26, firefox) and skipped publishing; the `pull_request` runs of `93f152bd` and `a20469dc` each failed one Firefox cell. Each Firefox failure is `tests/browser/legacy-reports.test.js` "should produce some html", `page.waitForFunction: Timeout 30000ms exceeded` with the report still loading (454 passing, 1 failing) |

## Provenance

Every figure below is labelled. **reproduced**: something was executed and the output observed.
**read-derived**: read from source, a PR body or CI metadata. Commit counts, SHAs, PR states, CI
results and the conflict counts are reproduced with the commands shown. No test suite was run on
`dev` by this session; the runs reported are the PR authors' and peer sessions', read from the PR
bodies (see the integration record). No live site, vendor account or Docker image was run.

## What is merged so far

Merge SHAs: `git log --first-parent --format='%h %ad %an %s' --date=iso official/master..official/dev`.
Every merge below was made on 2026-10-25: the first eleven and the last five by AndyLow91, #8834,
#8835 and #8838 by bewest. Register ids refer to the
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

None of these merged trees was re-run locally by this programme. The merged trees' CI is in
[Identity](#identity).

## Merge state

- **#8823 merged twice, without duplicated code** (reproduced). It was folded into cut 1 as
  `42a2729e` and also merged on its own as `4c1a5f1a` before #8828. On `eb72a1d3`, `git grep
  bridgeServerToConnect official/dev` finds one definition, in `lib/server/bridge-connect-compat.js`,
  and that file is byte-identical to `806ff2f0`'s (compared by hash). The test block that ran twice
  was removed by #8838 (`879ab51e`); on `2bc298b9` `tests/bridge-connect-compat.test.js` has one
  `describe('BRIDGE_SERVER mapping')`.
- **Cut 2 is merged** (#8837, `eb44a9c2`): `git merge-base --is-ancestor af7ba73a official/dev` exits 0,
  and `official/chore/build-runtime-separation` `af7ba73a` is 13 behind / 0 ahead of `dev` `b29f1bf7`.
- **Cuts 3–5 against `b29f1bf7`** (reproduced 2026-10-25 after the fetch; `git rev-list --left-right
  --count official/dev...<cut>` and `git merge-tree --write-tree --name-only --no-messages official/dev
  <cut>`): cut 3 `official/chore/compose-mongodb6` `ebb690cf` 532 behind / 63 ahead, 10 conflicting
  paths; cut 4 `official/chore/mime-exposure-review` `b80aa147` 532 / 142, 35; cut 5
  `official/chore/nightscout-modernization` `b1bdaca0` (#8605, open) 408 / 240, 47. The "ahead" counts
  fell from 222, 301 and 399 against `2bc298b9` because cut 2's commits, which cuts 3–5 descend from,
  are now on `dev`.

## Version: 16.0.0, major

Decided by the maintainer on 2026-10-21 (`RT-VERSION` answered). Surfaces touched (versioning policy
§6.2), read from the merged PRs:

- [x] S1 the realtime socket contract: #8797 stores records the socket used to drop as copies (a
  correction)
- [x] S2 plugin interface, boot sequence or client bundle: cut 2 (#8837) splits the client into page
  bundles and replaces the boot sequence and the client event bus with native code (a third-party
  plugin that hooks into the page is to be tested before upgrading; no plugin was run against it);
  #8831 adds an opt-in theme
- [x] S3 environment-variable surface: `THEME=modern` (#8831, a new value); leftover legacy bridge
  settings stop the site with a page naming the replacements (cut 1); `DEBUG_MINIFY` no longer has an
  effect (cut 2)
- [ ] S4 stored document shape
- [x] S5 Node or MongoDB runtime floor, **major**: `lib/server/runtime-policy.js` reads `engines.node`
  and exits at boot outside `^22.23.4 || ^24.22.1 || >=26.12.1`, which stops Node 20, 21, 23 and 25,
  and 22.0–22.23.3, 24.0–24.22.0 and 26.0–26.12.0. The README states MongoDB 5.0 through 8.0 (#8838);
  4.4 and earlier are unsupported, and no server check that refuses them was found. The test matrix on
  `dev` `b29f1bf7` (read from the job names of push run 40241375688) is Node 22.23.4 and 26 × MongoDB
  5.0 and 8.0, plus (24, 6) and (22, 6); the (22, 4.4) cell was removed by #8833. Cut 2 adds
  maintained-MongoDB jobs (Node 22.23.4 and 26 × 8.0.29) and replica-set jobs (Node 22.23.4 and 26 ×
  5.0.32 and 8.0.29); browser tests run on Node 26 × Chromium, Firefox and WebKit
- [x] S6 an ingestion path, **major**: the legacy Dexcom Share bridge and MiniMed CareLink
  (mmconnect) are removed; Dexcom Share data comes in through `nightscout-connect`
- [ ] S7 alarms or notifications: #8816 changes how long a snooze lasts on a page that is not signed
  in, and cut 2's `af7ba73a` changes how IFTTT Maker events are sent to several keys (corrections)
- [x] S8 the version string: `16.0.0`
- [x] S9 what the client computes and shows a person: BF-172, BF-173 and BF-174 change the Bolus Wizard
  Preview and the Careportal Bolus Wizard where the profile and display units differ, or where a
  profile other than the active one is chosen; #8812, #8808 and #8840 change report figures

Not on the list, and recorded for the release notes: #8836 changes response headers
(`Referrer-Policy`, `Cache-Control`), where the page sends its credentials, and removes `npm` from the
runtime Docker image.

**Classification:** MAJOR, because of S5 and S6 (cut 1). **Directory name says:** 16.0.0.
**Settled?** Yes, by the maintainer, 2026-10-21.

## In flight for this release

Branch heads as of 2026-10-26, 05:00Z (cut rows); 2026-10-25, 23:49Z (others). Cut 2 (#8837) and the test tiers (#8839) merged on 2026-10-25
([What is merged so far](#what-is-merged-so-far)).

| work | branch | head | state | queue |
|---|---|---|---|---|
| cut 3: MongoDB driver 7, maintained jQuery UI widgets, native help tooltips, Compose `mongo:6.0.27`; BF-179 and BF-182 folded in | `chore/compose-mongodb6`, **#8844** to `dev` | `12d1f645` (dev `428b20b7` merged in) | open; pushed 2026-10-25/26; see [Modernization cuts: handoff](#modernization-cuts-handoff) | `RT-REBASE` |
| cut 4: trusted proxies through one module, `mime-types`, moment-timezone 0.6, csv, semver 7, ESLint 10, webpack 5.110; BF-183 folded in | `chore/mime-exposure-review`, **#8847** (draft, based on `chore/compose-mongodb6`) | `99b6f68b` | open draft; pushed 2026-10-26 | `RT-5` |
| cut 5: Express 5, Helmet 8, Pushover native client, notification caches, APNs 8, EJS 6, axios 1, Flot 4, Swagger UI 5 | `chore/nightscout-modernization`, **#8605** (AndyLow91, base `dev`; retarget to `chore/mime-exposure-review` suggested) | `506cc41b` (fast-forward of `b1bdaca0`) | open; updated 2026-10-26 | `RT-3` |
| BF-72: a caller-supplied regular expression can hold the database for minutes | `bf/regex-limits`, in the private fork of its draft advisory | `1833ab00` on `dev` `04d435eb` | in the fork; no fork PR opened yet; owes a merge of `dev` | `BFQ-72` |
| BF-161: a deeply nested pattern on three query endpoints makes that request fail | `bf/entries-pattern-limit`, in the private fork of its draft advisory | `d2c4df9f` on `dev` `04d435eb` | in the fork; no fork PR opened yet; owes a merge of `dev` | `BFQ-161` |

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

For AndyLow91 and the maintainer, who asked on 2026-10-25 for cuts 3–5 to be pushed so the remaining
work can be shared. Cut 1 (#8828) and cut 2 (#8837) are merged.

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
preflight now answers `200` as JSON instead of the text `OK` (`res.sendStatus(200)` would restore it);
`js-yaml` is declared as a devDependency so webpack-cli 7's optional peer resolves; the
`istanbul-lib-processinfo.uuid` override no longer applies; dev's `TRUST_PROXY` notes still compare
against cut 5's unadopted `395f3207`.

**Across the cuts:** WebKit and the Node 22.23.4 floor were not run locally (CI runs them, but see the
browser row in [Known defects](#known-defects-on-dev-now)); BF-07's `getDataRef` caller in
`lib/api/entries/index.js` has no pinning test (reverting it stays green; filed by session -f4); cut 5's
alarm transports (Pushover native client, notification caches, APNs 8) need a live delivery check,
which this programme cannot do without real credentials; #8843 (CI diagonal) and each cut change
`.github/workflows/main.yml`, and whichever lands second takes the other's jobs.

## Known defects on `dev` now

| defect | what | exposure | queue |
|---|---|---|---|
| Firefox legacy-reports wait | `tests/browser/legacy-reports.test.js` "should produce some html" timed out at its fixed 30 s wait (`12154df9`) in one or two Firefox cells of the CI runs on `93f152bd` (`pull_request`) and `a20469dc` (both events), so the push run on `a20469dc` skipped the Docker publish; and once more on #8836's head `df2f37ab` (run 40228187718 attempt 1, *Browser tests (26, firefox)*, 463 passing, 1 failing; attempt 2 passed). Since cut 2 merged (`eb44a9c2`), `dev`'s test uses the progress-aware wait (fails after 15 s with no completed request, 60 s ceiling; `tests/browser/legacy-reports.test.js:136-144`), and *Browser tests (26, firefox)* passed in every push and `pull_request` run on `5de8505d`, `fd3792e5`, `eb44a9c2`, `78524be4` and `b29f1bf7` (one run each, so not yet evidence that the flake is gone) | test only; no register entry filed | `RT-2` (merged) |
| browser tests not running in CI | Since #8839 (`78524be4`), *Browser tests (26, chromium/firefox/webkit)* print no test output and pass: `scripts/test-tiers.js` lists files with `git ls-files`, ignores git's exit status, and inside the Playwright container (step `HOME=/root`) git refuses the checkout as dubious ownership, so the tier has zero files and the runner exits 0 (reproduced by session -5e in a root container over another uid's checkout; job logs read for push runs on `eb44a9c2`, 549 passing, then `78524be4` and `428b20b7`, none, and #8844's run 40253810477, none). Server jobs are unaffected (3820 passing per cell on `428b20b7`) | CI evidence only: no browser test has gated `dev` or a PR since 2026-10-25 21:57Z; fix (`listTestFiles` throws on git failure, a tier with zero files exits 2, `safe.directory` set system-wide in the browser job) on #8843 as `e767ce4e`, with a harness test that fails on the old runner | `RT-CI-DIAGONAL` (#8843) |
| dev pushes publish no Docker image | Since #8843 (`720e60de`), `docker-build` needs only `tests-pass`, and its implicit `success()` also sees `docker-build-pr`, which is skipped on pushes, so *Build Docker image* and *Publish to Docker Hub* are skipped: push run 40273692991 on `720e60de` passed every test lane and published nothing (job conclusions read with `gh run view`). The pushes before it (`78524be4`, `b29f1bf7`, `428b20b7`) published, so `dev`'s image stays `428b20b7`'s until the fix lands, and merges of the cuts publish nothing either | no `dev` image from `720e60de`; no release affected. **Fixed** by #8848 (merged 2026-10-26 06:03:54Z as `1f10cd9d`, head `952d0f49`; `864be741`: `!cancelled()` and an explicit `needs.<job>.result == 'success'`): `dev`'s push run 40277667345 built amd64 and arm64 and published to Docker Hub (session -5e, read-derived). #8848 also fixed two order-dependent tests (`c3a42776`, `952d0f49`) | `RT-CI-DIAGONAL` follow-up |
| reports page retained heap over budget | `tests/browser/page-populated.test.js` "initializes populated reports and bounds retained V8 heap" fails on Chromium on `428b20b7`: about 6.20 MB against 4.85 MB (`tools/page-resource-acceptance.js`), 3 of 3 runs (Node 24.22.1) and 2 of 2 (session -f4, Node 22.23.4); about 4.45 MB on `b29f1bf7`, so it arrived with #8542 (AGP reports). Hidden by the row above | a test budget, not an operator-visible failure. Resolved in #8843 (`0a33b7c7`, folded in by the maintainer): the test waits for the page's first report to finish, and the reports ceiling becomes 6,800,000 bytes, measured on `428b20b7`. Since #8542 the reports page draws a report on load; with a report showing, the new code retains about 2 MB less than the old (session -5e's measurement, read-derived) | BF-192 (filed by session -f4, unlanded `records/f4-2510`) |

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

As of `dev` `b29f1bf7` (2026-10-25). The decisions already made are in [decisions.md](decisions.md).

**Decisions open, with their owner:**

1. **Whether cuts 3–5 ship in 16.0.0 or later** (maintainers). Cut 2 merged into `dev` (#8837), so it
   ships in 16.0.0 unless reverted; the versioning policy §8.3 leaves the later cuts' grouping open.
2. **The scope of BF-161's draft advisory** (maintainer): publish it now for BF-151 (released in 15.0.9)
   with BF-161 as a follow-up, or extend it to include BF-161 and publish it with the release that
   carries the fix. Packet: [bfq-161](../../reports/reviewer-packets/bfq-161-bf-entries-pattern-limit.md).
3. **BF-72's test inputs** (the original author of the regex-limit commits): the tests' hostile inputs
   are to be rebuilt in code before anything is published. Packet:
   [bfq-72](../../reports/reviewer-packets/bfq-72-bf-regex-limits.md).
4. **BF-95** (maintainer): a notice for readings that arrive dated ahead of the server clock, or the
   status quo. Packet: [bfq-95](../../reports/reviewer-packets/bfq-95.md). 2026-10-25 (maintainer): verify
   `srvModified` first; on `dev` it is now a server receipt time on every live path (caveat BF-181).
5. **BF-152** (maintainer, with the AndroidAPS developers): is API v3 `settings` meant to be readable
   with a follower's read token, or admin-only? **Decided 2026-10-25**: a staged ladder, an opt-in
   admin-only settings read in 16.x (`API3_SETTINGS_STRICT_READ_ENABLED`, default off; cherry-pick
   `faffe875` of `06ba6201` in PR #8845 to `dev`, pending push), a question to the AndroidAPS developers
   about a narrower scope, and a strict default later on the calendar. Queue `BFQ-152` (`in-flight-upstream`).
6. **Dependabot configuration** (maintainer): version updates targeting `dev`, dismissing alerts that
   are fixed on `dev` or not reachable, or releasing more often. Packet:
   [dependabot-config](../../reports/reviewer-packets/dependabot-config.md).

**Repository settings, for the maintainer** (from #8838's and #8833's bodies; branch protection read
2026-10-25, after the 22:41Z merge: `dev` requires `Run Tests (24, 6)`; `master` requires `Run Tests (22, 6)`,
`Run Tests (22, 4.4)` and `Run Tests (24, 6)`). Nothing in a PR changes these:

1. `master`: drop the required check `Run Tests (22, 4.4)`. #8833 deleted its `include` entry, so no
   run emits it, and the staging PR #8824 cannot meet `master`'s protection until it is dropped.
2. `dev` and `master`: move the `Run Tests (24, 6)` and `Run Tests (22, 6)` requirements to edge cells
   (for example `Run Tests (22.23.4, 8.0)` and `Run Tests (26, 8.0)`, and `(22.23.4, 5.0)` and
   `(26, 5.0)` if the MongoDB floor should also gate merges), then delete those `include` entries.
3. Optionally, require `Browser tests (26, chromium)`, `(26, firefox)` and `(26, webkit)`, whose names
   are now stable.

**Follow-ups filed 2026-10-25:** `RT-BUNDLE-THEME-SPLIT` (page-bundle budget option B: load the modern
theme's code only when it is chosen; owner Andy Low or the maintainer; not started) and
`RT-BOOT-INDEX-AWAIT` (boot awaits its collection and index creation, the cause of the API3 hook
timeout; a product change; not started).

**Merge order** (a suggestion for the maintainers, not a decision): #8838, #8837 (cut 2) and #8839 (the
test tiers) merged on 2026-10-25, in that order with #8836 and #8833 between them. Then:

1. Cuts 3–5 (`RT-REBASE`, `RT-3`, `RT-5`), after their catch-up merges of `dev`.
2. The other follow-ups, each in a themed PR: `RT-JSDOM-REST` (scope B), `ID-SIMPLE-MATCH` with BF-169
   (it touches `lib/server/entries.js`, which cut 2 also changes), `RT-BUNDLE-THEME-SPLIT` and
   `RT-BOOT-INDEX-AWAIT`.
4. BF-72 and BF-161 through their advisory forks, each after a merge of `dev`, published with the
   release that carries them.

**Before the tag:** the call for testers ([testing-notes.md](testing-notes.md)), the tag message and the
release notes (written last, from the list below), a full run on the candidate in the integration
record, the verification record capture, the reconciliation in [releases/README.md](../README.md).

## For the release notes

A draft list of what the release notes must say; the notes themselves are written last, once the
candidate is named.

- The Node floor `^22.23.4 || ^24.22.1 || >=26.12.1`, and the message the server prints when it refuses
  to start.
- The legacy Dexcom Share and MiniMed CareLink bridges are removed; leftover bridge settings stop the
  site with a page naming the replacements; Dexcom Share data comes in through `nightscout-connect`.
- MongoDB 4.4 or newer is required to start once cut 3 (driver 7) is in: on 3.6, 4.0 or 4.2 the site does not
  serve data and shows a page naming the database server's version and the minimum it needs (BF-182); the
  fix is to upgrade MongoDB. 5.0 through 8.0 are the supported, tested range; 4.4 starts but is untested.
- Production-only installs (`npm ci --omit=dev` or `NODE_ENV=production`) that worked on 15.0.9 do not
  build the client bundle since cut 2 (webpack and Babel are devDependencies). BF-179 (planned for cut 3)
  turns the failure into a message naming the fix (`npm ci --include=dev`, then
  `npm prune --omit=dev --ignore-scripts`); it does not restore the old behaviour. The project's
  Dockerfile and `azure-deploy.sh` install dev dependencies and are not affected.
- The opt-in `THEME=modern` dashboard (#8831).
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
3. That the PR-body figures recorded here for #8835, #8836, #8837, #8838, #8839 and #8840 match a
   re-run; none was re-run by this programme.
4. Whether #8836's `body-parser` and status-URL changes, and cut 2's Maker log line, need a notice for
   15.0.9 operators: 15.0.9 has the same code or versions (above). Recorded here by mechanism only.

---

*Draft, 2026-10-25. Prepared locally; nothing pushed, tagged, merged or published by this programme.
Requires maintainer review before anything here is relied upon.*
