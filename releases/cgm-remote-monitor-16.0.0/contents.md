# cgm-remote-monitor 16.0.0 — contents

**Status: in development. Nothing tagged or released.** 16.0.0 is the next release from `dev`
(maintainer, 2026-10-21; queue `RT-VERSION`). Contributor-facing; full technical depth intended.
Measured 2026-10-26 (to 19:10Z) against `official/dev` `47723cda` (the merge of #8605, cut 5) and
`official/master` `c6a0d8ed` (= `v15.0.9`, the shipping release), in
`externals/cgm-remote-monitor-official` after `git fetch official`, with `gh pr view`, `gh run view` and
`gh api` for PR, CI and branch-protection state. Updated at 22:13Z for `dev` `7ad3a67f` (#8854 `c08cbe03`,
then #8084), and on 2026-10-27 for `dev` `8dbb60c2` (#8860): the Identity rows for `dev`, the merge list,
#8854, #8860, the in-flight rows and the CI on `8dbb60c2`; the other figures are still those of `47723cda`.
Updated on 2026-10-28 for `dev` `e1f7ac41` (#8873), and on 2026-10-30 for `dev` `991b0654` (#8865, 02:04:14Z):
the Identity rows for `dev`, the merge list (#8877, #8878, #8865), the in-flight rows for the 16.0.0 scope
the maintainer set on 2026-10-30, Known defects (BF-209, BF-211, BF-212) and the open items; read with
`gh pr view`, `gh run list --commit` and `gh api` at about 02:30Z, and counted in
`externals/cgm-remote-monitor-official` after `git fetch official`. Updated on 2026-10-31 for `dev` `368e6c23`
(#8874, 02:02:52Z): the merge state, the in-flight update below the handoff table, Known defects (BF-215,
BF-216, BF-219 to BF-222) and the testing pointer to R18; read with `gh pr list`, `gh pr checks` and
`gh api .../compare` at about 05:45Z. The Version section and the other figures are still those of
`47723cda`.

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
| `dev` head | `368e6c23` (merge of #8874, 2026-10-31 02:02:52Z, by bewest); before it `305a6533` (merge of #8880, 2026-10-30 16:24:38Z, by bewest); before that `991b0654` (merge of #8865, 2026-10-30 02:04:14Z, by bewest), tree `a9ae9536`; the merges before that: #8878 `d51c7a60` (2026-10-30 01:48:51Z), #8877 `cf3d4b8f` (2026-10-30 00:50:49Z), #8873 `e1f7ac41` (2026-10-28 05:20:32Z), and on 2026-10-27 after #8856: #8872 `db3b9e4e`, #8871 `dcf20bfb`, #8858 `ca1652d6`, #8869 `b8baf24d`, #8870 `7abe1cf6`, #8863 `9668b179`, #8861 `84fac457` (`git log --first-parent eed31dca..official/dev`) |
| `dev` head on 2026-10-27 | `eed31dca` (merge of #8856, 2026-10-27 20:09:35Z, by bewest), tree `584623cf`; the merges before it that day: #8868 `88676086` (20:01:50Z), #8859 `94899828` (19:52:21Z), #8866 `b84871d7` (19:42:55Z), #8864 `2dc0c1bc` (16:55:01Z, AndyLow91) and #8860 `8dbb60c2` (00:07:13Z, AndyLow91) |
| Commits on `dev` | 999 at `991b0654` — `git rev-list --count official/master..official/dev` (576 without merges, `--no-merges`); 921 at `eed31dca` (529 without merges), 890 at `8dbb60c2`, 882 at `7ad3a67f` |
| First-parent commits on `dev` | 54 at `991b0654` — `git rev-list --first-parent --count official/master..official/dev`: 53 PR merges and the cycle's version bump `04d435eb`; 43 at `eed31dca` |
| Diff on `dev` | 947 files, +144414/−18833 at `991b0654` — `git diff --shortstat official/master official/dev`; 871 files, +131070/−15204 at `eed31dca`; 855 files, +127983/−15090 at `8dbb60c2`. Since `e1f7ac41`: 62 files, +3815/−213 |
| Merged on 2026-10-26 | 17 PRs, from `b29f1bf7` to `7ad3a67f`: 611 files, +86276/−3996 — `git diff --shortstat b29f1bf7 official/dev`; the thirteen after `207a8352`: `git rev-list --first-parent --count 207a8352..official/dev` = 13 |
| `package.json` version | `16.0.0` — `git show official/dev:package.json \| grep '"version"'` |
| `engines.node` | `^22.23.4 \|\| ^24.22.1 \|\| >=26.12.1` (AndyLow91's `6a146a4c`, "require Node Brotli security patches"; supersedes the decided `^22.12 \|\| >=24`) |
| Docker base image | `node:24.22.1-alpine` for builder and runtime (`32489dc5`); the runtime stage deletes the image's global `npm` and `npx` (`Dockerfile` on `dev`) |
| Connector pin | `nightscout-connect` exactly `0.1.0`, as in 15.0.9 (`git show official/dev:package.json`) |
| MongoDB | driver `mongodb` `^7.6.0` (cut 3); the README states 5.0 through 8.0 as supported and 4.4 and earlier as unsupported (`README.md:157-158` on `dev`); driver 7 starts on 4.4 and refuses 3.6, 4.0 and 4.2, which get the boot error page (BF-182; decisions). Docker Compose starts `mongo:6.0.27` (`docker-compose.yml:12`; 15.0.9: `mongo:5.0.32`) |
| Web framework | `express` `^5.2.1`, `helmet` `^8.3.0` (cut 5; `package.json` on `dev`); 15.0.9 locks `express` 4.22.2 |
| Staging PR, 2026-10-30 | #8824: open, head `991b0654` (`MERGEABLE`, `BLOCKED`, `REVIEW_REQUIRED`, read 2026-10-30 about 02:30Z). `master`'s protection is unchanged: required checks `Run Tests (22, 6)`, `Run Tests (22, 4.4)` and `Run Tests (24, 6)` and one approving review (`gh api repos/nightscout/cgm-remote-monitor/branches/master/protection`), so #8824 still cannot meet it; the decided change to require only *Tests pass* is still owed ([Open items](#open-items-a-releaser-must-settle)) |
| CI on the 2026-10-28 to 2026-10-30 merges | `e1f7ac41`, `cf3d4b8f`, `d51c7a60` and `991b0654`: the `push` and `pull_request` runs of *CI test and publish Docker image* and CodeQL passed on each (`991b0654`: push 40989520549, `pull_request` 40989526434; `d51c7a60`: 40988048798, 40988055182; `cf3d4b8f`: 40982235609, 40982243569; `e1f7ac41`: 40637431538, 40637440405) — `gh run list --commit <sha>`; job lists and image tags not read |
| Staging PR, 2026-10-27 | #8824 (`dev` → `master`, "new dev branch post 15.0.9 release"): open, head `eed31dca` (`MERGEABLE`, `BLOCKED`, `REVIEW_REQUIRED`, read 2026-10-27 20:25Z); `master`'s required checks are still `Run Tests (22, 6)`, `Run Tests (22, 4.4)` and `Run Tests (24, 6)`, and `dev`'s CI no longer runs `Run Tests (22, 4.4)`, so the maintainer's settings change is still owed |
| CI on the 2026-10-27 merges | `eed31dca`, `88676086` and `94899828`: `push` passed and published `dev_<sha>` and `latest_dev` with no per-architecture tags (#8866's by-digest publishing; Docker Hub 20:20Z, 20:14Z, 20:02Z); `88676086`'s `pull_request` run was cancelled by the next push. `b84871d7` (#8866): `push` run 40571593504 failed *Browser tests (26, webkit)* on the cached-bundle startup test again, so it published nothing (`RT-CI-WEBKIT-REPORTS`); its `pull_request` run passed. The MongoDB 8.0 jobs run on `ubuntu-22.04` since `f6884342` (BF-202) |
| CI on `8dbb60c2` | **red.** `push` run 40424319822: *Browser tests (26, webkit)* (658 passing, 1 failing: "Complete page template startup boots every page from cached bundles and retires the old cache on upgrade", `Uncaught browser errors`, fifteen report-page `entries.json`/`treatments.json` requests "due to access control checks") and *Run Tests (26, 5.0)* (`tests/concurrent-writes.test.js` "all documents have unique _id after concurrent inserts", expected 10, got 9) failed, so *Tests pass* failed and no image was published; `pull_request` run 40424329138: the same WebKit test failed, every other job passed (*Validate Docker image* amd64 and arm64 passed); CodeQL passed on both events (40424319787, 40424329177). #8860's own run 40422840113 on `ad593fce`, the identical tree, passed every job at 23:55Z, before UTC midnight; the merge runs started after 00:07Z. See [Known defects](#known-defects-on-dev-now) — `gh run view <id> --json jobs`, `--log-failed` |
| CI on `7ad3a67f` | `push` run 40410737772 passed every job and published (*Validate Docker image* skipped by design); `pull_request` run 40410745675 and CodeQL (40410737784, 40410745580) passed; on `c08cbe03`, push 40403541566 and `pull_request` 40403553936 passed — `gh run list --commit`, `gh run view <id> --json jobs` |
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
2026-10-25 (#8834, #8835 and #8838 by bewest, the others by AndyLow91), seventeen on 2026-10-26
(#8843, #8848 and #8850 by bewest, the others by AndyLow91) and on 2026-10-27 #8860 and #8864 by AndyLow91, then #8866, #8859, #8868, #8856, #8861, #8863, #8870, #8869 and #8858 by bewest; later #8871, #8872, #8873 (2026-10-28) and, on
2026-10-30, #8877, #8878 and #8865, all by bewest. Register ids refer to the
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
| #8854 | 10-26 21:20:34 | `c08cbe03` | `246313e4` | AndyLow91 | — | `ARCH-8854` | shared persistence and stored-data contracts: the persistence boundary `lib/storage/write-step.js`, socket Temporary Target validation under `reject`, the opt-in `Nightscout-Data-Warnings` header (46 files, +2340/−100; below) |
| #8084 | 10-26 22:13:18 | `7ad3a67f` | `27886bab` | gardenrobot | — | — | Google Fonts replaced by fonts served from the site; the Content-Security-Policy drops the Google font hosts (92 files, +1093/−23); not examined further |
| #8860 | 10-27 00:07:13 | `8dbb60c2` | `ad593fce` | AndyLow91 | — | — | the glucose pentagon (Comprehensive Glucose Pentagon) and its prognostic glycemic risk (PGR) in the Distribution report, for issue 8809 (20 files, +1178/−10; below) |
| #8864 | 10-27 16:55:01 | `2dc0c1bc` | `4ed92673` | AndyLow91 | — | — | the IOB pill keeps the device-reported value through a socket reconnect instead of switching to the treatment-based value |
| #8866 | 10-27 19:42:55 | `b84871d7` | `f6884342` | bewest | BF-201, BF-202 | `RT-CI-FLAKES-8DBB60C2`, `BFQ-201`, `BFQ-202` | CI: three intermittent test fixes, a MongoDB wait that names the runner's kernel, the MongoDB 8.0 jobs on `ubuntu-22.04`, release images published from the tag (a push to `master` publishes nothing), nodemon's watch list; #8867 was folded in and closed |
| #8859 | 10-27 19:52:21 | `94899828` | `87f1aeb8` | bewest | BF-195 | `BFQ-195`, `ID-SIMPLE-MATCH` | the re-send and merge contract: identifier matching, `null` in an update removes the field (Q1b), the profile socket push after its merge write (BF-195), devicestatus `identifier` |
| #8868 | 10-27 20:01:50 | `88676086` | `2ca7dfc8` | bewest | BF-200 | `BFQ-200` | API v2's data-snapshot route answers 400 for a time it cannot parse instead of stopping the server; callback tasks stop a run when a task throws, as `async` did |
| #8856 | 10-27 20:09:35 | `eed31dca` | `6c9af523` | bewest | BF-193 | `BFQ-193` | write paths log a summary of a write, not the record, unless `DEBUG_LOGGING` is on |
| #8861 | 10-27 20:57:07 | `84fac457` | `5310a447` | bewest | — | `ST-FILTER-READS` | the storage filter AST and interface methods; API v1 reads move onto the storage interface |
| #8863 | 10-27 21:00:16 | `9668b179` | `42128f3b` | bewest | — | `ST-WRITES` | API v1, authorization and socket writes go through the storage interface, labelled by source |
| #8870 | 10-27 21:33:44 | `7abe1cf6` | `0955f25b` | bewest | — | `ST-COUNT-ONEPATH` | API v1 count goes only through the storage interface (the pipeline path removed) |
| #8869 | 10-27 22:23:05 | `b8baf24d` | `d9fca2de` | bewest | — | `RT-CI-WEBKIT-REPORTS` | test: page-startup waits for `/report/` on its first controlled visit, and a failure names each browser error's page |
| #8858 | 10-27 22:29:46 | `ca1652d6` | `debf4a14` | bewest | — | — | the API v1 and v3 documents describe what 16.0.0 serves, and a contract test holds them to the routes (includes #8381 by arfaomar); the alignment site's API pages re-rendered from it as current |
| #8871 | 10-27 22:51:12 | `dcf20bfb` | `57f1d37c` | bewest | BF-203 | `BFQ-203` | tooling: a `jsconfig.json` scoped by `exclude`, so an editor stops watching sibling worktrees (1 file, +8) |
| #8872 | 10-27 23:45:05 | `db3b9e4e` | `355b4f14` | bewest | BF-194 | `BFQ-194` | a Temporary Target is stored in mg/dL labelled `mg/dl` on API v1, API v3 and the socket (11 files, +742/−43); owes a release-note line |
| #8873 | 10-28 05:20:32 | `e1f7ac41` | `1c50c29a` | bewest | BF-204, BF-205, BF-206, BF-207 | `BFQ-204`..`BFQ-207` | the data-snapshot route answers a past time from its own query; same-time records ordered by `_id`; an undated device IOB takes its status's time (the AAPS IOB pill golden regenerated); sensor age keeps the newest start within an hour (built by session -65) |
| #8877 | 10-30 00:50:49 | `cf3d4b8f` | `ac5d77fb` | bewest | BF-209, BF-211 | `BFQ-209`, `BFQ-211` | the socket's ±2 s similar treatment match follows client identity: when the write carries `identifier`, the same one is one record and a different one a second record; the exact match is unchanged (BF-209). A delete by query flushes only the cache of the collection it deleted from (BF-211). BF-210 was withdrawn from it before merge as not a defect (maintainer, 2026-10-29) (8 files, +1219/−20) |
| #8878 | 10-30 01:48:51 | `d51c7a60` | `57f333b4` | bewest | BF-212 (first part) | `BFQ-212` | the chart's "Move insulin" and "Move carbs" split no longer copies `syncIdentifier`, `id`, `uuid` or `identifier` onto the moved half (2 files, +21/−4); the rest of BF-212 is open ([Known defects](#known-defects-on-dev-now)) |
| #8865 | 10-30 02:04:14 | `991b0654` | `1b2801f7` | bewest | — | `PLAT-SERVE`, `PLAT-ENTRY` | one executable `nightscout`: the image's `CMD ["nightscout", "single"]`, SIGTERM and SIGINT shutdown on every start path, the healthcheck command, boot profiles, API v3 without API v1's modules, the socket and the cache (ST-V3-DECOUPLE), and `serve` reserved for a multitenant Nightscout (53 files, +2575/−189); supersedes #8862 |
| #8880 | 10-30 16:24:38 | `305a6533` | `0e5c25be` | bewest | BF-213, BF-214, BF-217 | — | the pump alarm follows the severity Loop sends in `reservoir_level_override`, with Loop's text; an override with no reservoir value no longer throws in the pump plugin; a v1 device-status delete by query asks for a reload (5 files, +327) |
| #8874 | 10-31 02:02:52 | `368e6c23` | `83f3d54a` | bewest | BF-218 (test) | `WC-STEP-PATCH` | `write(intent)` release 1: every v1, API v3 and socket write path through one write step, no behaviour change by the write-contract matrix (0 of 1,929 cells outside `cache`), merge revert rehearsed; journey lab (2026-10-30/31) found no difference from `dev` |

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
- **#8854**: eleven commits by AndyLow91 over `dev` `47723cda`, from `880b7369` to `246313e4`, merged
  after the four outcome-B points ([decisions](decisions.md)), which he agreed to on the PR at 20:32Z. By
  mechanism: the six v1 and internal collection modules, the legacy socket and API v3 go through the
  persistence boundary (`lib/storage/write-step.js`, a wrapper over the driver collection that keeps
  existing replies and validates the effective result of `$set` and `$unset`); it emits a data-free
  `storage-write-committed` event marked internal and unstable, with no consumer; the opt-in Temporary Target
  rules also apply to the socket's add, update and unset, and under `reject` the socket answers a refused
  item with a `refused` slot in input order, as API v1 does; a non-mutating stored-data inspection
  (`lib/storage/read-contract.js`) can add a `Nightscout-Data-Warnings` header to API v3 reads, off unless
  `API_V3_DATA_WARNINGS=true` and called experimental; a read-only diagnostic command
  (`scripts/diagnose-data.js`) and a write-boundary check (`scripts/check-write-boundary.js`); guards for
  malformed cache values, authorization identities and history timestamps; Mocha runs that find zero tests
  fail (`--fail-zero`). Not asked for: `246313e4` adds a `failed` slot on socket treatment arrays under
  `reject` for an item whose write cannot be confirmed (open item 11). The merged tree's client replay is
  R16 in the integration record: 0 differences from `47723cda` in 201 cells.

**#8860**, the glucose pentagon (read from the PR body and `git diff --stat 7ad3a67f 8dbb60c2`; not run by
this programme). The Distribution report gains the Comprehensive Glucose Pentagon's five component values,
a reference polygon, CGM coverage, the reading count and the prognostic glycemic risk (PGR), in both
glucose units, both report themes and print (`lib/report/pentagon.js`, `pentagon-view.js`, `agp-data.js`,
`lib/report_plugins/glucosedistribution.js`). Fixed 70–180 mg/dL thresholds; it reads the original CGM
observations before the report's one-minute filter, time-weights them, collapses exact same-source
duplicates and withholds the score for conflicting simultaneous readings or indistinguishable alternating
streams. The score is withheld below 70 % elapsed coverage, below 16 h 48 min of observed data, or when an
hourly filter excludes part of the day; the PR body calls these "implementation guards, not validated
clinical PGR thresholds", and says the numerical checks "do not constitute third-party clinical
validation" and that independent review of the incomplete-data method and clinical presentation remains
advisable. It adds the Nightscout Reporter licence notices (`docs/third-party/`) and the method in
`docs/test-specs/glucose-pentagon.md`. The PR's CI on `ad593fce` passed every job; the merge's did not
([Identity](#identity), CI on `8dbb60c2`).

**The 2026-10-30 merges** (read from the [register](../../docs/30-design/remedial/nightscout-backfix-register.md)
and the [next-gen plan](../../docs/30-design/platform/next-gen-platform-plan.md) §1a; the runs are the
preparing sessions'):

- **#8877**: BF-209's scope was decided 2026-10-29: in the similar match only, `identifier` decides when
  present, because applying the legacy client-id rule as it is would make an `identifier`-only re-send a
  duplicate; recognising `identifier` at any time waits for ID-FIRST-MATCH. `567f0612` restores the amount
  rule with pins (a carbs-only re-send next to a stored carbs-and-insulin record stays one record) and
  `ac5d77fb` is BF-211. `npm test` 4858 passing, 0 failing, 3 pending; the write-contract matrix against `dev`
  moves `treatments × v3 × ws` as intended, and session -4f's dedupe gate (58 tests, ablations red) measured
  it. Changes which socket treatment uploads are stored as separate records; the plan asks an AndroidAPS
  3.4.2.x v1 cohort to check carbs and boluses.
- **#8878**: `splitRecord` (`lib/client/treatmenttime.js`) drops the four client identity fields beside `_id`
  and `NSCLIENT_ID`; a unit test that is red on `dev` before it; `npm test` 4858 → 4859 passing, 0 failing,
  3 pending; the reproduction probe finds one record per identity. A 16.0.0 backfix by the maintainer's
  ID-Q5 decision (2026-10-29).
- **#8865**: the start forms were measured on images in `tools/lab/image-start-forms` (B8 in the
  [release allocation](../../docs/30-design/platform/release-allocation-2026-10-27.md)): every `docker run`
  form that started a server on `dev` starts the same one; `docker stop` takes 0.13 s and exits 0 instead
  of 10.1 s and 137. `serve` refuses every role until one is multitenant.

None of these merged trees was re-run locally by this programme, except the client replay on `7ad3a67f`
(R16). The merged trees' CI is in
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
- **The 2026-10-30 heads are on `dev`, not on `master`** (reproduced 2026-10-30 with
  `git merge-base --is-ancestor`: exit 0 against `official/dev`, 1 against `official/master`): #8877
  `ac5d77fb`, #8878 `57f333b4`, #8865 `1b2801f7`. #8874's head `4f9fc4cd` is 0 commits behind `dev`
  `991b0654` (`gh api repos/nightscout/cgm-remote-monitor/compare/dev...4f9fc4cd`: `behind_by` 0,
  `ahead_by` 20).
- **#8874 is on `dev`** (2026-10-31): `dev` `368e6c23` is its merge, with CI passing on the push run
  41158171888 and the `pull_request` run 41158177377. `dev` is 1027 commits and 56 first-parent commits
  ahead of `master` `c6a0d8ed` (968 files, +151453/−19743; the integration record's figures).

## Version: 16.0.0, major

Decided by the maintainer on 2026-10-21 (`RT-VERSION` answered). Surfaces touched (versioning policy
§6.2), read from the merged PRs. A ticked box is a surface the merged code touches; an unticked one
marked *owed* has a candidate change whose classification is not recorded yet:

- [x] S1 the HTTP API and the realtime socket contract: #8797 stores records the socket used to drop as
  copies; #8845 makes API v3 refuse a client body `_id` with 400 (BF-170), answers a v1 re-send with its
  stored `_id` (BF-165) and merges a profile re-sent with its `_id` instead of answering 500 (BF-166);
  #8852 answers malformed API v1 profile uploads with 400 and caps them at 10,000 records; #8841 adds
  `refused` slots to v1 batch replies under `WRITE_VALIDATION=reject`, and #8854 the same slots, and a
  `failed` slot, to socket replies under `reject`, and the opt-in `Nightscout-Data-Warnings` header on API v3
  reads; cut 5 moves the routes to
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

**The 16.0.0 scope, decided by the maintainer on 2026-10-30** ([decisions](decisions.md); next-gen plan §1):
16.0.0 targets every single-tenant item of the [next-gen plan](../../docs/30-design/platform/next-gen-platform-plan.md),
through the entry bar and in priority order. An item joins the merge list when its matrix result is as stated
(0 cells, or named cells), its red controls and ablations pass, a revert has been rehearsed, and it has had time
on `dev` with its cohort check (entry bar, 2026-10-29). An item that misses the bar at the tag rolls to 16.1.0,
or to 17.0.0 if it changes a default. The identity work is the core: it is the substance of the agreement with
the Loop maintainers. Multitenant items may ship dormant, labelled alpha behind `serve`, or not ship. The tag
is gated by the bar and the pre-tag items, not by a date.

**Handoff, 2026-10-31 (read with `git ls-remote` and `gh pr list` at about 03:00Z; plan owner session -49).**
`dev` is `368e6c23` (#8874 merged 2026-10-31 02:02Z). Merge order on `dev` from here: #8883, then #8879 once
slice 4 is rebuilt on it, then the unique-index PR. The cohort window (one window over #8874 and the identity work)
opens when slices 3 and 4 are on `dev`.

| PR / branch | head | state | next step, owner |
|---|---|---|---|
| #8883 v1 treatment writes (BF-219, BF-220, BF-221, BF-222) | `8ae46b72` on GitHub; `789d5d9d` local adds BF-222 (session -7d's fix, cherry-picked; the bundle's new test files 18 passing) | open, base `dev`; write-step port reviewed by session -4f | push `789d5d9d` and update the title and body, then merge **before** #8879's next `dev` merge (they conflict in four files); maintainer |
| #8879 identity (ID-FIRST-MATCH) | `5cdd9577` (slices 1, 2, 5, 5b, 3 + `dev` `368e6c23`) | draft, base `dev` | slice 4 rebuilt with treatments `replaced` on every path (decided 2026-10-30), then 6 and 6a (prepared: `prep/id-first-s6` `47377fa3`, tests red as expected, prediction script); session -4f |
| `feat/id-unique-index` (local) | `b4a4092c` on slice 3 | built and gated (342 predicted cells, MongoDB 5.0 and 8.0) | rebase onto 6a, re-run, open as a draft on #8879; held until then |
| `proto/id-batch-replies` (local) | `7d81e1c1` | prototype + client lab; (ii)–(vi) decided 2026-10-30 | build ID-BATCH on the identity branch after the index, with strict on v1 (ID-STRICT-V1) |
| #8881 ST-HARNESS | `ffa5e6b4` | draft, base `dev` | review; unblocks ST-PG and TEN-RESOLVE |
| #8882 hygiene (DEV-LINT-OVERLAY-REGEX, UI-DRAWER-RESIZE) | `cd42dfce` | open, base `dev` | review and merge (one `dev` merge behind) |
| #8875 ST-VIEWS | `24647c0a` | draft; both views equal to the resident path on 126,092 replayed minutes each | wiring under the multitenant `serve` roles (alpha); one `dev` merge behind |
| #8857 registration | `10fe6725` | draft; product-as-address built | D-REG-FLAG and the upload-role question are the maintainer's |
| BF-72, BF-161 advisory forks | local `0fdf0fd6`, `0873f314` | `dev` `305a6533` merged and re-tested; **not pushed** (forks still `a9da33ff`, `1dce7722`) | push, then merge `dev` `368e6c23` once more before the tag; maintainer |
| #8855 Crowdin | `6a2e84ab` | behind `dev` | update branch, merge; maintainer |
| `master` protection, #8824 | — | protection still requires `Run Tests (22, 4.4)` | the decided settings change (only *Tests pass* and one approval), then #8824; maintainer |
| Release 2 | `proto/v3-unify` `3b7f054a` (local) | Q-A adopted 2026-10-30; Q-U decided; Q9 recorded | write step resolves filter writes to ids; one write shape for v3; session -7d's labs |

**Update, 2026-10-31, about 17:50Z** (session -d1; `dev` still `37b2280f`):

- **#8879's `dev` merge is ready to push** (session -4e): local `feat/id-first-s4r` `5a251213` = merge `5bf94c8b` (`f5bd2642` + `dev` `37b2280f`) plus a test for the batch-index mapping (`tests/api.entries.batch-deleted-and-taken.test.js`); fast-forwards the PR head; 0 behind `dev`, 13 ahead. The four expected conflicts kept both sides; the matrix (4,604 cells, MongoDB 8.0) moved 0 cells outside `cache` and `wire`; every tier green on Node 22.23.4 and 24.22.1; the merge revert gives `f5bd2642`'s tree. The maintainer has the push commands. The matrix has no cells for BF-219..222 (coverage gap, no BF id).
- **Slice 6 decisions** (maintainer, 2026-10-31; [decisions](decisions.md)): socket treatments replace on an identifier match, as every other path does; the profile rule (a different `startDate` is a new profile without the copied identifier) extends to the socket. Both go in the [compatibility notes for affiliated projects](../../docs/30-design/platform/upstream-asks-controller-authors/socket-paths-compat-notes.md) (draft, unsent). Slice 6 and 6a are being built on `5a251213`.
- **BF-223** (a saved API secret the site refuses blocks a valid `?token=` link; also on `v15.0.9`): ready to push on local `bf/16.0.0-stale-secret-hash` `ecbc9c06` (main page and clock views); the clock bundle allowance moves by 43 gzip bytes, for the maintainer to accept.

**Update, 2026-10-31, about 16:40Z** (GitHub, session -d1): the maintainer merged **#8883** at 16:30Z as `2f50d944`
(head `789d5d9d`: BF-219, BF-220, BF-221, BF-222) and **#8882** at 16:33Z as `37b2280f` (head `32cd90e6`:
DEV-LINT-OVERLAY-REGEX, UI-DRAWER-RESIZE). `dev` is `37b2280f`. Not released. Next on the merge order: #8879, which
needs `dev` `37b2280f` merged in (the four-file conflict with #8883; session -4e), then slices 6 and 6a, then out of draft.

**Update, 2026-10-31, about 16:20Z** (read from GitHub with `gh pr list`, `gh pr checks` and
`gh api .../compare/dev...<head>` by session -d1). `dev` is still `368e6c23`; nothing merged since #8874. Every open
16.0.0 PR is green on every CI job:

| PR | head now | against `dev` `368e6c23` | CI | changed since the 05:45Z table |
|---|---|---|---|---|
| #8883 | `789d5d9d` | 0 behind, 7 ahead | green | none; ready for the maintainer's review, merge first |
| #8879 | `f5bd2642` (draft) | 0 behind, 11 ahead | green | the lint failure is fixed (`f5bd2642`); slices 6 and 6a not yet pushed (local `prep/id-first-s6` `47377fa3`) |
| #8882 | `7a6b0283` | 0 behind, 4 ahead | green | the drawer-resize handler registers at the first open (`2737756d`), so the browser-less test passes; `dev` merged in. Ready for review |
| #8881 | `ffa5e6b4` (draft) | 0 behind, 7 ahead | green | — |
| #8875, #8857 | `24647c0a`, `10fe6725` (drafts) | 25 behind each | green | — |
| #8855 | `6a2e84ab` | — | — | — |

Still owed before the tag, unchanged: BF-72 and BF-161 fork branches carry `dev` `305a6533` (local `0fdf0fd6`, `0873f314`) and need `dev` `368e6c23` merged and re-run; `master` protection; the cohort window (opens when slices 3 and 4 are on `dev`).

**Update, 2026-10-31, about 05:45Z** (read from GitHub with `gh pr list`, `gh pr checks` and
`gh api .../compare/dev...<head>` by session -7d; every local branch matches its PR head, and every worktree is clean):

| PR | head now | against `dev` `368e6c23` | CI | changed since the table |
|---|---|---|---|---|
| #8883 | `789d5d9d` (pushed; title names BF-222) | 0 behind, 7 ahead | 13 passed, 2 pending | the push is done; merge before #8879 |
| #8879 | `931e5e60` | 0 behind, 10 ahead | lint fails: `no-useless-assignment` at `lib/storage/write-intent.js:1450` | slice 4 (merge on match, treatments `replaced` on every path) pushed |
| #8882 | `cd42dfce` | 25 behind | 4 failing: the browser-less test of `browser-utils` stops with `window is not defined`, because the drawer-resize listener (`lib/client/browser-utils.js:138`) runs when the module loads | **not ready to merge** until that commit guards for a missing `window` |
| #8881 | `ffa5e6b4` | 0 behind | green | — |
| #8875, #8857 | `24647c0a`, `10fe6725` | 25 behind each | green | — |
| #8855 | `6a2e84ab` | 299 behind | — | — |

Queued, unowned: QC-MATRIX-WIRE-ATTRIBUTION, UI-STALE-SECRET-HASH. BF-222's fix is in #8883 (BFQ-222).
Upstream drafts, unsent: AndroidAPS 410 handling, tconnectsync profile copy
(`docs/30-design/platform/upstream-asks-controller-authors/`).

In flight on 2026-10-30 (read about 02:30Z with `gh pr view` and `gh api .../compare`, and again later on 2026-10-30 for the rows marked *later*; work not yet in a PR
is read from the plan, the [ID-FIRST-MATCH design note](../../docs/30-design/platform/id-first-match-design-note-2026-10-29.md)
and the queue):

| work | branch or PR | head | state | queue |
|---|---|---|---|---|
| `write(intent)` release 1: every v1, API v3 and socket write path through one write step, no behaviour change except BF-165's `_id` in the fallback-key re-send reply | `feat/write-intent`, **#8874** (base `dev`, opened by the maintainer 2026-10-28; *later* 2026-10-30: out of draft at `9919f8ef`) | `9919f8ef` (*later*): `4f9fc4cd` (2026-10-30 02:06Z, a merge of `dev` `991b0654`; 20 commits, 27 files, +7187/−1531 against `dev`) plus one commit adding only cgm-remote-monitor's architecture note `write-intent.md` | slices 1–6 built; slices 4 (API v3) and 6 (socket treatments, devicestatus, profile) released by the maintainer 2026-10-29, slice 6 with its extra dedupe gate. On the push-ready head `e8224807` (17 commits on `dev` `e1f7ac41`, 2026-10-29): the write-contract matrix differs from `dev` in 0 cells, the revert was rehearsed, `npm test` 5106/0/3 against `dev`'s 4759/0/3 (read from the queue). CI on `4f9fc4cd`: `pull_request` run 40990198561 and CodeQL passed. *Later*, measured by session -4f at `4f9fc4cd` against `dev` `991b0654`, run one after the other: `npm test` 5206/0/3 against `dev`'s 4917/0/3 (+289 titles, none removed or renamed); tiers 415 files ok; the write-contract matrix (1,929 cells) differs in 0 cells outside `cache` and in 1 cell in `cache` only, no earlier cell differs (pin `tools/qc/results/write-contract-matrix/dev-991b0654-idfirst.json`); the commit-event copy (360 cells) 0 differing, from an earlier overlapping pair, not re-run. The merge revert was rehearsed at `4f9fc4cd`: the reverted tree equals `dev`'s (`a9ae9536`). The PR body names the merge revert as the supported revert; a commit-by-commit revert conflicts after the `dev` merges and, forced, drops BF-209. Needs the maintainer's review and merge; the cohort check below starts at the merge. First in the entry-bar order; not yet through the bar | `WC-STEP-PATCH` |
| ID-FIRST-MATCH: identifier-first on every collection and path, as slices in the order 1 (no outcome change, with the two additive items), 2 (identifier format), 5 (shared identifiers, BF-212's pick), 3 (stays deleted), 4 (merge on match), 6 (identifier first where it is new), 6a (activity) | **draft #8879** (*later* 2026-10-30, base `feat/write-intent`, head `feat/id-first-match` `521e7583`): slice 1 gated, 4 commits on `9919f8ef`; slices 2, 5, 3, 4, 6, 6a follow as commits; design note 2026-10-29 | — | slice 1's gate: the 456 earlier cells unchanged, and among the new cells only the two additive items' cells, predicted by id before the run (about 24 activity cells), with UUID handling on and off. The rules are decided (D-LOOP-ID rules 1–3, ID-Q1..ID-Q11, 2026-10-29); each slice goes to the bar on its own. Slice 1 moves 0 of 1,929 matrix cells; slices 3 to 6a change outcomes (40, 232, 112 and 33 cells, read from the design note's predictions) | `ID-FIRST-MATCH`, `ID-VALIDATE` |
| the `WRITE_*` settings: `WRITE_RESEND=merge\|acknowledge\|refuse`, `WRITE_IDENTIFIER=lenient\|strict`, `WRITE_DELETED_EDIT=ignore\|refuse`, `WRITE_IDENTIFIER_INDEX=try\|require\|off`; default first in each | not started | — | names confirmed by the maintainer 2026-10-29 (the first three) and 2026-10-30 (the index). With `WRITE_VALIDATION`, parsed by one module and read once; an unknown value refuses to start. Per-client D20 quirks may select a `WRITE_RESEND` mode for one registered client | `ID-RESEND-SWITCH`, `ID-VALIDATE`, `ID-FIRST-MATCH`, `ID-UNIQUE-INDEX` |
| ID-UNIQUE-INDEX: a partial unique index on `identifier` per collection, with the try, require and off modes, and an operator-run report and clean tool (P4 pick) | not started | — | in 16.0.0 scope through the bar (maintainer, 2026-10-30); moved from 17.0.0. Under `try` (the default) boot builds the index online; on existing duplicates it logs the counts per collection (never the values), shows them on the status page and runs without it, while the ID-Q5 write rule still refuses a second record with a stored identifier. `require` refuses to start without the index; `off` skips it. Comes before ID-BATCH, with the duplicate-key retry inside the write step (maintainer, *later* 2026-10-30; [decisions](decisions.md)) | `ID-UNIQUE-INDEX` |
| ID-BATCH: per-item results in v1 batch replies | [design note](../../docs/30-design/platform/id-batch-design-note-2026-10-30.md) (session -4f, *later* 2026-10-30); not built | — | eligible through the bar (2026-10-29), after the unique index (2026-10-30). The note proposes one slot per sent item, 200 if any item is not refused and 400 if all are, no 207 (it breaks Loop and three other uploaders), transient failures as a whole-request 5xx, and full `items[]` only on opt-in; five questions stay open until ID-BATCH is next | `ID-BATCH-RESULTS` |
| the re-send switch (D-LOOP-ID rule 3): a site setting plus per-client D20 quirks that opt a client into keep-first or refuse | not started | — | eligible through the bar (2026-10-29); off by default, merge on match stays the default | `ID-RESEND-SWITCH` |
| SPEC-ID-AMEND: the identity specification and conformance cases (mandatory identifier on registered instances; API v3's refusal of a client `_id`) | alignment repository, branch `spec/id-amend-2026-10-30` (*later* 2026-10-30: an agent of session -49 is building it) | — | spec and conformance only; no site behaviour (plan item) | — |
| controller registration S0, S1, S2, S5, off by default | **draft #8857** | `f7a43fed` (last updated 2026-10-27): 109 commits behind `dev`, 12 ahead (`gh api .../compare/dev...f7a43fed`); `mergeable` reads `UNKNOWN` | needs `dev` merged in, with conflicts reported in the plan; *later* 2026-10-30: an agent of session -49 is merging `dev` into it in `externals/work/crm-regcat-flat` (merge, not rebase), with push commands for the maintainer; D-REG-FLAG (where the catalogue lives) is open | `HUB-REG-CRM` |
| ST-HARNESS: a backend-selectable test harness | not started | — | plan item, after `write(intent)` | — |
| ST-EVENT and ST-VIEWS, if they clear the bar | ST-VIEWS: **draft #8875** (`a0470a72`, not wired in) | — | ST-EVENT: D-EVENT deferred 2026-10-27, research continuing. ST-VIEWS: wiring is the maintainer's call, with alarm cohort checks; the alarms are safety-relevant. *Later* 2026-10-30: proposed to the maintainer, not decided: use the views only under `serve` (multitenant alpha) and leave `single` on the resident path, deciding a single-tenant switch from evidence. The maintainer asked for that evidence from labs: a time-stepped replay lab (minute by minute over days of the corpus and synthetic fixtures, with acks, snoozes, two uploaders and the lookback edges, a resident-vs-resident noise floor and the drop-query and tamper controls) is being built by an agent of session -49 on local `lab/views-replay` | — |
| multitenant items (tenant configuration, resolution, tenant-scoped credentials, PostgreSQL) | — | — | optional for 16.0.0: they may ship dormant, labelled alpha behind `serve` (which refuses every role today), or not ship | — |
| BF-72 and BF-161 through their advisory forks | the rows below | `a9da33ff`, `1dce7722` (pushed 2026-10-27) | both contain `dev` `7abe1cf6`; `dev` has moved eight PR merges past it (#8869 to #8865), so a merge of `dev` and a re-run inside each fork is owed before the tag | `BFQ-72`, `BFQ-161` |
| Crowdin translations | `crowdin_incoming`, **#8855** (sulkaharo) | `6a2e84ab` (updated 2026-10-29 20:31Z): 33 files, +1448/−491 | open; `mergeable` reads `UNKNOWN`; not examined; §1a row 3a, low risk | — |
| `master` protection and the staging PR #8824 | repository settings | #8824 at `991b0654` | `master` still requires `Run Tests (22, 4.4)`, which no workflow on `dev` emits; the decided change (only *Tests pass* and one approval) is owed, then #8824 merges and the tag is cut | `RT-16-RELEASE` |

### Cohort check for `write(intent)` release 1 (#8874)

Owned by session -49 (plan owner) from 2026-10-30; the writer list is session -4f's. Since the maintainer's
2026-10-30 decision it is one window over #8874 and identity landings A, B and C together, opened when B
lands, rather than a week per item. Testers on `dev` report any duplicate or missing treatment, device status or
profile, by the path their uploader writes through, because those are the paths the write step now carries:

| path | writers to cover |
|---|---|
| socket | AndroidAPS 3.4.2.x with the v1 NSClient; the web chart's *Move insulin* and *Move carbs* drag |
| API v3 | AndroidAPS NSClientV3; nightguard |
| REST v1 | Loop, Trio, xDrip+, nightscout-connect, the careportal |
| identity landing B (slices 3, 4) | Loop and Trio re-sending changed doses, overrides and temporary targets; re-sends after a delete |
| identity landing C (6, 6a, index) | activity writers; sites whose start-up log or status page reports duplicate identifiers under `WRITE_IDENTIFIER_INDEX=try` |

One volunteer runs `WRITE_VALIDATION=reject` and compares the treatments in their app with the site. Read from
the clients' code by session -4f ([ID-BATCH design note](../../docs/30-design/platform/id-batch-design-note-2026-10-30.md)),
not reproduced: under `reject`, a refused treatment in a v1 batch keeps its reply slot with a `refused` member
and no `_id`; Loop counts a slot without `_id` as uploaded, and Trio and xDrip+ check only the status, so all
three treat the refused treatment as uploaded and do not re-send it. This is behaviour on `dev` today, not
introduced by #8874.

*Rows as recorded to 2026-10-28* (read 2026-10-26, 19:10Z; #8854, #8856 and #8859 updated at 22:13Z; BF-72, BF-161, the CI test fixes, #8864 and the next-gen drafts on 2026-10-27). Every cut is merged
([Merge state](#merge-state)); #8854 is merged ([What is merged so far](#what-is-merged-so-far)).

| work | branch | head | state | queue |
|---|---|---|---|---|
| Crowdin translations | `crowdin_incoming`, **#8855** (sulkaharo) | — | opened 2026-10-26 18:52Z; not examined | — |
| BF-72: a caller-supplied regular expression can hold the database for minutes | `bf/regex-limits` in the private fork of its draft advisory (fork head `532d7d7a`, on `dev` `b29f1bf7`); locally `adv/r3gv-1600` | `a9da33ff` on `adv/r3gv-1600-dev`: `dev` `9668b179` and then `7abe1cf6` merged into the fork branch (`f64f78c4`, already on the fork); **pushed to the fork by the maintainer 2026-10-27** as `bf/regex-limits` `a9da33ff` | in the fork; no fork PR opened yet. 2026-10-27, after #8861, #8863 and #8870: the conflicts resolved as on the candidate, and the read time limit carried onto #8870's single count path; `npm test` 4776 passing, 0 failing, 3 pending; `test:all` 5104 passing, 0 failing, 3 pending (Node 22.23.4, MongoDB 8.0.34); removing the limit from the count path fails the count test | `BFQ-72` |
| BF-161: a deeply nested pattern on three query endpoints makes that request fail | `bf/entries-pattern-limit` in the private fork of its draft advisory (fork head `0e06a36b`, on `dev` `b29f1bf7`); locally `adv/phrf-1600` | `1dce7722` on `adv/phrf-1600-dev`: `dev` `9668b179` and then `7abe1cf6` merged into the fork branch (`8dcf1537`, already on the fork), no conflicts; **pushed to the fork by the maintainer 2026-10-27** as `bf/entries-pattern-limit` `1dce7722` | in the fork; no fork PR opened yet. 2026-10-27: `npm test` 4714 passing, 0 failing, 3 pending; `test:all` 5042 passing, 0 failing, 3 pending; the fix's test file 48 passing | `BFQ-161` |
| the CI pull request: three intermittent test fixes, the MongoDB wait, image publishing, nodemon | `test/16.0.0-ci-flakes`, **#8866** (into `dev`; #8867 merged into it as `7a96b912` at the maintainer's request, 2026-10-27) | `7a96b912`: `c7857735` (concurrent-writes: Notes one second apart), `bdd569a3` (page-startup: the reports page is ready once its first report has loaded), the maintainer's `dev` merge `ddeeff8c`, `65632082` (the dashboard round trip waits for each page before leaving it), and #8867's `56804908`, `04b1f870`, `5d9f84b5`, `e0cfbd0c` | **merged 2026-10-27 19:42:55Z by bewest as `dev` `b84871d7`** (head `f6884342`, after `f6884342` moved the MongoDB 8.0 jobs to `ubuntu-22.04`; both 8.0 jobs passed on `6.8.0-1064-azure` in run 40569981396). Earlier: `65632082` followed WebKit's `page.goForward: WebKit encountered an internal error` on run 40559261253; #8867 was merged in as `7a96b912` and closed at 19:28:02Z | `RT-CI-FLAKES-8DBB60C2`, `BFQ-201`, `BFQ-202` |
| WebKit's cached-bundle startup test, again | `test/16.0.0-reports-ready`, **#8869** (opened by the maintainer 2026-10-27, base `dev`) | `9a44e16f` on `dev` `eed31dca`: `tests/browser/page-startup.test.js` | **merged 2026-10-27 22:23:05Z by bewest as `dev` `b8baf24d`** (head `d9fca2de`, `dev` merged in). Earlier: the first controlled navigation waits for the reports page's first report, and a failure names the page each browser error came from. Not reproduced locally before or after; the cause is not proven, and the new line is there to name it on the next failure. page-startup 28 passing on WebKit, Chromium and Firefox | `RT-CI-WEBKIT-REPORTS` |
| BF-191: a stored treatment can stop the server process, and keeps doing so after a restart | private, through the maintainer's advisory process | — | open in the register | `BFQ-191` |
| BF-193: write paths log whole records | `bf/16.0.0-log-privacy`, **draft #8856** (the maintainer, base `dev`) | `6b6ad320`: one commit (`8ae43eb4`) and a merge of `dev` `7ad3a67f` | **merged 2026-10-27 20:09:35Z by bewest as `dev` `eed31dca`** (head `6c9af523`; `gh pr view 8856`). Earlier: draft PR opened 2026-10-26. `dev` `7ad3a67f` merged in as `6b6ad320` (session -66, no conflicts; pushed by the maintainer 2026-10-26, hosted CI 16 passed, 0 failed, 2 skipped): `npm test` 4436 passing, 0 failing, 3 pending; `test:all` 4764 passing, 0 failing, 3 pending | `BFQ-193` |
| the re-send and merge contract: `ID-SIMPLE-MATCH`, Q1b (a `null` in an update removes the field), BF-195 (a stale profile pushed over the socket after a re-send) and the devicestatus `identifier` rule, one PR | `bf/16.0.0-null-removes`, **draft #8859** (the maintainer, base `dev`) | `5c6ceabb`: five commits on `dev` `47723cda` and a merge of `dev` `7ad3a67f`: `ID-SIMPLE-MATCH` `8d0f9a22`, Q1b `913d0895`, BF-195 `1bdce62c`, merge `cf2a2a67`, the devicestatus `identifier` rule `fc170a4c` (read from `git log`) | **merged 2026-10-27 19:52:21Z by bewest as `dev` `94899828`** (head `87f1aeb8`, `dev` merged in; `gh pr view 8859`) | `ID-SIMPLE-MATCH`, `WRITE-CONTRACT`, `BFQ-195` |
| the IOB pill switching to the treatment-based value during a reconnect | AndyLow91's branch, **#8864** (base `dev`) | `4ed92673`: `lib/data/ddata.js` and a new `tests/data.reconnect-snapshot.test.js` | **merged 2026-10-27 16:55Z by AndyLow91 as `dev` `2dc0c1bc`** (`gh pr view 8864`); opened 13:02Z; read from the PR body, not run here: the socket's reconnect payload is read from the live `ddata` the loader is rebuilding, so a reconnect during a refresh can carry no device statuses and the pill falls back for that moment; the fix reads from the completed snapshot. The PR reports three new tests failing on the unmodified base, and 4 sensor-age failures under `TZ=Europe/London` that it reproduces on the base too. Display of a dosing-relevant value (cycle priority 2) | — |
| next-gen drafts: storage slices, one executable, `serve api`, registration | *Current 2026-10-28 01:15Z:* #8861 **merged** (`84fac457`) and #8863 **merged** (`9668b179`), both 2026-10-27; #8862 **closed** 2026-10-28 01:12Z as superseded by #8865; #8865 open, base `dev`, head `53ba192a`, on the 16.0.0 merge list (its own row below); #8857 open, draft, `f7a43fed`. *As first recorded:* #8861 (`5310a447`, draft), #8863 (`42128f3b`, on #8861, ready for review, pushed 2026-10-27), #8862 (`b63d9b7f`), #8865 (`1dafe2a5`, on #8863), #8857 (`f7a43fed`) | — | Decided 2026-10-27 (Q12): #8861 and #8863 go into 16.0.0 if they meet the [release allocation](../../docs/30-design/platform/release-allocation-2026-10-27.md) B6 entry bar; items 1, 3, 4 and 5 met on local candidates the same day (`cand/with` `d6ba8e18`: matrix, replay and v1 HTTP differential equal, no measurable latency change, one-commit revert restores `cand/without`'s tree), item 2 (BF-72 and BF-161 re-merged in their private forks) met locally the same day; #8859 and #8856 merged (`dev` `eed31dca`); the final heads re-measured on it: #8863 `npm test` 4700/0/3, `test:all` 5028/0/3, 360-cell matrix equal to `dev`; #8861 `npm test` 4685/0/3 (session -2e). Hosted CI has not run on #8863 (its base is not `dev`) and runs once #8861 merges; merge order #8861, #8863 (with the count commit `079f20ae`); #8856 resolved against the slices on `prep/writes-plus-8856` `699a70c4`. #8861 merged as `84fac457`, #8863 as `9668b179` and #8870 (`ST-COUNT-ONEPATH`) as `7abe1cf6` (dev, 2026-10-27, by the maintainer). It was planned before the tag (maintainer, 2026-10-27): one commit removing API v1 count's fallback paths in `lib/server/aggregate.js` (the constructor pipeline hook and the no-store driver path), unreachable over HTTP, so no client-visible change. #8862 if it merges with time on `dev` before the tag | `ST-FILTER-READS`, `ST-WRITES`, `PLAT-ENTRY`, `PLAT-SERVE`, `HUB-REG-CRM` |
| one executable, the image's start and stop, the boot split for a multitenant Nightscout (PLAT-SERVE, PLAT-ENTRY, ST-V3-DECOUPLE) | `feat/nightscout-serve`, **#8865** (base `dev`; supersedes #8862) | `b01b77c3`: #8862's four commits, the image `CMD nightscout single`, SIGTERM/SIGINT shutdown, the healthcheck certificate fix (`f01d67e6`, CodeQL alert 138 fixed), boot profiles, the API v3 role harness, and `serve` reserved for a multitenant Nightscout with the single-tenant api code as `scripts/headless-test-server.js` | **merged 2026-10-30 02:04:14Z by bewest as `dev` `991b0654`** (head `1b2801f7`). Earlier: **in the 16.0.0 merge list (maintainer, 2026-10-27)**; open, no human review yet. API v3 suites 751/0 under single, 643/0/108 pending under headless; image start forms: every `docker run` form that started a server on `dev` starts the same one, `docker stop` 10.1 s/137 becomes 0.13 s/0 (`tools/lab/image-start-forms`) | `PLAT-SERVE` |
| BF-200: the data-snapshot route's unusable time | `bf/16.0.0-ddata-at-crash`, **#8868** (opened by the maintainer 2026-10-27 19:50:31Z, base `dev`) | `2ca7dfc8`: `434c0157` and `2564e5dc` with `dev` `94899828` merged in; 6 files, +176/−12 against `dev` | **merged 2026-10-27 20:01:50Z by bewest as `dev` `88676086`** (`gh pr view 8868`); ready to push 2026-10-27, not pushed. Red controls re-run by session -ee: the new data test on `dev` 1 passing, 5 failing; the new callback-tasks case with the first commit's helper 8 passing, 1 failing; both on the branch 14 passing. `npm test` 4489 passing, 0 failing, 3 pending and `test:all` 4817 passing, 0 failing, 3 pending (session -2e, Node 22.23.4, MongoDB 7.0) | `BFQ-200` |
| BF-201: nodemon's file watches | **#8866** (added to #8867 at the maintainer's request, 2026-10-27; #8867 merged into #8866 as `7a96b912`) | `5d9f84b5` (prepared as `426d2835` on `dev` `2dc0c1bc`): `package.json` nodemonConfig, the watch test and probe, the M24 addendum | merged with #8866 (`b84871d7`, 2026-10-27 19:42:55Z). nodemon watches `lib`, `views`, `translations`, `webpack` and `package.json`; Linux file watches 1,502 → 385 at `dev` `2dc0c1bc`; the watch test fails at `docs/unlisted.js` with the old configuration; `npm test` 4483 passing, 0 failing, 3 pending (Node 22.23.4, MongoDB 8.0.34); developer tooling only | `BFQ-201` |
| BF-203: an editor's file watches | `tooling/jsconfig-watch-scope`, **#8871** (opened by the maintainer 2026-10-27 22:21:20Z, base `dev`; the start of the next tooling PR) | `f28d40bb`: the maintainer's draft `e737d310` (`jsconfig.json`, 8 lines) with `dev` `7abe1cf6` merged in | **merged 2026-10-27 22:51:12Z by bewest as `dev` `dcf20bfb`** (head `57f1d37c`, `dev` merged in). Earlier: open, CI running: an editor opening `lib/server/app.js` from a checkout inside a larger workspace watches 450,689 → 2,007 files, 1.4 GB → 358 MB (tsserver 5.9.3, started as an editor starts it); `npm test` 4700 passing, 0 failing, 3 pending; developer tooling only | `BFQ-203` |

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
| BF-219, BF-220, BF-221: v1 treatment batch replies and PUT announcements | **fixed on `dev` by #8883** (merged 2026-10-31 16:30Z as `2f50d944`; not released). BF-219: a batch with a preBolus answers with more items than were sent, so Loop re-sends it forever. BF-220: a taken `_id` inside a batch answers 5xx after earlier items are stored. BF-221: a v1 PUT reaches open pages 1–57 s late | BF-219 and BF-220 are dosing-relevant (lost or endlessly re-sent treatments); BF-221 is display latency | `BFQ-219`, `BFQ-220`, `BFQ-221` |
| BF-222: API v3 autoPrune leaves pruned records in the cache | **fixed on `dev` by #8883** (merged 2026-10-31 16:30Z as `2f50d944`; still on `v15.0.9`, since #6688; R18) | only where `API3_AUTOPRUNE_<collection>` is shorter than that collection's cache retention; display only | `BFQ-222` |
| BF-215, BF-216: identifier format | **on `dev` now; fixes in #8879** (ID-FIRST-MATCH slice 2, not merged). BF-215: a numeric `identifier`; BF-216: a placeholder `identifier` shared by two apps | BF-216 is dosing-relevant data loss, narrow | `ID-FIRST-MATCH` |
| BF-212, the rest: shared client identity after a chart split | **first part fixed on `dev` 2026-10-30** by #8878 (`d51c7a60`): a new chart split no longer copies the client identity fields. Still open: records split before the fix keep two stored treatments with one identity, and a v1 or in-process re-send of either lands on the older record, so a re-send of the newer one overwrites the older one's amount (API v3 picks the newer record and refuses a re-send of the older one with 400; measured by the extended write-contract matrix). A full re-upload of the original by the client that still holds it writes the moved insulin back, so it is stored and counted twice, with or without identity on the copy. The follow-ups are ID-FIRST-MATCH slice 5 (the P4 pick) and the maintainer's direction that a lossy edit of a controller-claimed record needs a manual confirmation | dosing-relevant data and display, narrow: a chart drag of a record that holds both insulin and carbs; on 15.0.9 and `dev` | `BFQ-212` |
| BF-209: two identical socket treatments within 2 s from different clients stored as one | **fixed on `dev` 2026-10-30** by #8877 (`cf3d4b8f`), for writes that carry `identifier` (scope decided 2026-10-29: in the similar match, `identifier` decides when present); writes without it keep the earlier rule, and recognising `identifier` at any time waits for ID-FIRST-MATCH. Present on 15.0.9. BF-210 (an upload with no amount absorbed by a stored one) was withdrawn 2026-10-29 as intended behaviour | socket writers: AndroidAPS's v1 NSClient (3.4.2.x) and the chart-drag split | `BFQ-209` |
| BF-211: a delete by query empties all three in-memory caches | **fixed on `dev` 2026-10-30** by #8877 (`cf3d4b8f`); present since 14.0.4 and on 15.0.9. Cost, not correctness: the next load re-reads days of data (890 documents and 716,202 bytes after a 3-record delete; 32 documents and 10,289 bytes with the fix, cache-value lab) | sites on transfer-capped MongoDB tiers | `BFQ-211` |
| BF-200: an unusable time on API v2's data-snapshot route stops the server | **fixed on `dev` 2026-10-27** by #8868 (`88676086`); until then: one authenticated read of `/api/v2/ddata/at/:at` with a time the server cannot use makes the data loader throw where nothing catches it, since `26d0908a` replaced `async` with `lib/utils/callback-tasks`; the process exits. v15.0.9 answers 500 and keeps running (checked by session -2e), so this is a regression on `dev` only | every site running `dev` (`2dc0c1bc`) or a `dev` image; not 15.0.9 | `BFQ-200` |
| BF-202: CI's MongoDB 8.0 jobs on Linux 6.19 runners | MongoDB 8.0 refuses to start on Linux 6.19 to 7.0.13 (SERVER-121912); `ubuntu-24.04` image 20261026.354 moved to `7.0.0-1017-azure`, where both 8.0 jobs refused to start on run 40569101512, 8.0.29 included. Mitigated by `f6884342`, merged with #8866 (`b84871d7`): the 8.0 jobs run on `ubuntu-22.04` (Linux 6.8), both passing on run 40569981396 | CI: mitigated on `dev`. Operators running MongoDB 8.0 on such a kernel meet the same MongoDB defect (release-notes line) | `BFQ-202` |
| Firefox legacy-reports wait | `tests/browser/legacy-reports.test.js` "should produce some html" timed out at its fixed 30 s wait (`12154df9`) in one or two Firefox cells of the CI runs on `93f152bd` (`pull_request`) and `a20469dc` (both events), so the push run on `a20469dc` skipped the Docker publish; and once more on #8836's head `df2f37ab` (run 40228187718 attempt 1, *Browser tests (26, firefox)*, 463 passing, 1 failing; attempt 2 passed). Since cut 2 merged (`eb44a9c2`), `dev`'s test uses the progress-aware wait (fails after 15 s with no completed request, 60 s ceiling; `tests/browser/legacy-reports.test.js:136-144`), and *Browser tests (26, firefox)* passed in every push and `pull_request` run on `5de8505d`, `fd3792e5`, `eb44a9c2`, `78524be4` and `b29f1bf7` (one run each, so not yet evidence that the flake is gone) | test only; no register entry filed | `RT-2` (merged) |
| browser tests not running in CI | Since #8839 (`78524be4`), *Browser tests (26, chromium/firefox/webkit)* print no test output and pass: `scripts/test-tiers.js` lists files with `git ls-files`, ignores git's exit status, and inside the Playwright container (step `HOME=/root`) git refuses the checkout as dubious ownership, so the tier has zero files and the runner exits 0 (reproduced by session -5e in a root container over another uid's checkout; job logs read for push runs on `eb44a9c2`, 549 passing, then `78524be4` and `428b20b7`, none, and #8844's run 40253810477, none). Server jobs are unaffected (3820 passing per cell on `428b20b7`) | CI evidence only: no browser test gated `dev` or a PR from 2026-10-25 21:57Z until #8843 merged (2026-10-26 05:20:27Z, `720e60de`); the Chromium job of push run 40369632641 on `47723cda` runs 40 browser test files, 650 passing (job log). The fix (`listTestFiles` throws on git failure, a tier with zero files exits 2, `safe.directory` set system-wide in the browser job) on #8843 as `e767ce4e`, with a harness test that fails on the old runner | `RT-CI-DIAGONAL` (#8843, merged 2026-10-26) |
| dev pushes publish no Docker image | Since #8843 (`720e60de`), `docker-build` needs only `tests-pass`, and its implicit `success()` also sees `docker-build-pr`, which is skipped on pushes, so *Build Docker image* and *Publish to Docker Hub* are skipped: push run 40273692991 on `720e60de` passed every test lane and published nothing (job conclusions read with `gh run view`). The pushes before it (`78524be4`, `b29f1bf7`, `428b20b7`) published, so `dev`'s image stays `428b20b7`'s until the fix lands, and merges of the cuts publish nothing either | no `dev` image from `720e60de`; no release affected. **Fixed** by #8848 (merged 2026-10-26 06:03:54Z as `1f10cd9d`, head `952d0f49`; `864be741`: `!cancelled()` and an explicit `needs.<job>.result == 'success'`): `dev`'s push run 40277667345 built amd64 and arm64 and published to Docker Hub (session -5e, read-derived). #8848 also fixed two order-dependent tests (`c3a42776`, `952d0f49`) | `RT-CI-DIAGONAL` follow-up |
| reports page retained heap over budget | `tests/browser/page-populated.test.js` "initializes populated reports and bounds retained V8 heap" fails on Chromium on `428b20b7`: about 6.20 MB against 4.85 MB (`tools/page-resource-acceptance.js`), 3 of 3 runs (Node 24.22.1) and 2 of 2 (session -f4, Node 22.23.4); about 4.45 MB on `b29f1bf7`, so it arrived with #8542 (AGP reports). Hidden by the row above | a test budget, not an operator-visible failure. Resolved in #8843 (`0a33b7c7`, folded in by the maintainer): the test waits for the page's first report to finish, and the reports ceiling becomes 6,800,000 bytes, measured on `428b20b7`. Since #8542 the reports page draws a report on load; with a report showing, the new code retains about 2 MB less than the old (session -5e's measurement, read-derived) | BF-192, merged 2026-10-26 with #8843 |

Seen in `dev`'s CI on 2026-10-26 and 2026-10-27 (read from the job logs, `gh run view <id> --log-failed`; neither
reproduced locally, no register entry):

| intermittent | run | what |
|---|---|---|
| development watch policy | push run 40350206994 on `89b7ebdd` (#8730) | *Tests without a database (22.23.4)*: 1339 passing, 1 failing, "Development watch policy preserves configured ignores and application watching through two restart cycles" (`tools/probe-development-watch.py`, `assert boots[-1]['value'] == cycle+1`; the test took 8.9 s). *Tests pass* failed, so no image was published from `89b7ebdd`; the `pull_request` run on the same commit passed |
| Firefox job time limit | push run 40356902994 on `09d0def8` (#8555) | *Browser tests (26, firefox)* was cancelled at the job's 10-minute limit, so *Tests pass* failed and no image was published from `09d0def8`. Cut 5's `f4abce3c` raised browser jobs to 15 minutes; Firefox took 8m12s and 10m40s on `47723cda` |
| page-startup reports recovery | `pull_request` run 40273696980 on `720e60de` (#8843) | *Browser tests (26, chromium)*: "Complete page template startup recovers the actual reports page after two failed bundle downloads" exceeded 30 s (172 passing, 2 failing with its `afterEach`); the push run on the same commit passed |
| concurrent-writes `_id` count | push run 40424319822 on `8dbb60c2` (#8860) | *Run Tests (26, 5.0)*: "all documents have unique _id after concurrent inserts", expected 10, got 9. Ten Notes with random times within 10 s; a Note without an `identifier` is matched on its time and event type, so two in the same millisecond are one record (about 1 run in 220). Reproduced with a forced collision (expected 1 to be 10); not reproduced in 30 plain runs. Fix prepared: `RT-CI-FLAKES-8DBB60C2` (R17) |
| WebKit reports-page race | push run 40424319822 and `pull_request` run 40424329138 on `8dbb60c2` | *Browser tests (26, webkit)*: "Complete page template startup boots every page from cached bundles and retires the old cache on upgrade". Push run: fifteen report-page requests "due to access control checks" as uncaught page errors; `pull_request` run: `page.goto: WebKit encountered an internal error` leaving `/report/`. The test leaves the reports page before its deferred first-week report has loaded. Not reproduced locally in CI's image (3 of 3 on `8dbb60c2` and `7ad3a67f`); #8860 does not change what the page fetches. Fix prepared: `RT-CI-FLAKES-8DBB60C2` (R17) |
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
has none until then. The items it is captured over are listed in
[verification-selection.txt](verification-selection.txt) (98 queue ids on 2026-10-31, 90 on 2026-10-30; 65 at the
2026-10-27 dry run: every item this file or [decisions.md](decisions.md) names, and the release items), with
the capture command. The 25 added on 2026-10-30 are the items named since the dry run, fourteen of them from
the 2026-10-27 and 2026-10-28 merges.

**R18, 2026-10-30/31** ([integration record](../../docs/30-design/remedial/rc-16.0.0-integration-record.md)):
#8874's write-contract matrix against the `dev` pins (0 cells outside `wire` and `cache`), the cache
catch-up lab round 3 (BF-222) and BF-222's fix (`npm test` 5216/0/3). `dev` `368e6c23`'s CI passed.

**Journey lab, 2026-10-30/31, #8874 `7463e76d` against `dev` `305a6533`** (maintainer in the browser, two tabs per
site, with session -7d checking the database and socket timing; journey lab `tools/review/journey-lab`, MongoDB 7,
Node 22.23.4, development mode; sites loop, aaps (API v3, mmol/L), aaps-v1 (socket) and rep-trio on each head):
careportal carb correction (REST POST); Loop carbs POST, PUT edit and DELETE by `_id`; the web page's edit-mode drag
(socket `dbUpdate`); AndroidAPS temp target start and cancel over v3 and the socket, carbs, and carb delete; the modern
theme on rep-trio. Every step stored once with the same fields on both heads and showed live in both tabs; deletes
reached the page in 13–30 ms on both heads (3/3). Verdict: no difference between #8874 and `dev` in anything seen or
stored. Found along the way, none caused by #8874: BF-221 (a v1 treatment PUT reaches pages up to a minute late),
DEV-LINT-OVERLAY-REGEX, UI-DRAWER-RESIZE and UI-STALE-SECRET-HASH (queue). The lab's AAPS temp-target cancel was
corrected (`2e484bd33`).

**Dry run, 2026-10-27, `dev` `8dbb60c2`** (reproduced; written to a scratch directory, not kept, because a
record is captured once, at the tag). The generator ran on the selection with its default `static` and
`unit` gate kinds: 65 items, 49 PASS, 4 FAIL, 12 UNMEASURED; 157 gates run or marked, 72 passed, 5 failed,
80 are `no-gate` markers. The five failures: BFQ-72's gate (BF-72 still on `dev`; its fix is in the
advisory fork), BFQ-161's freshness gate (the fork branch owes a merge of `dev`), RT-CONNECT-PIN-CUTS
(the gate refuses to report because every ref it reads now pins `nightscout-connect` 0.1.0) and
RT-NODE-FLOOR-TESTED's two gates (they read the old `origin/chore/*` tips). The dry run found four defects
in the generator and the register, fixed on 2026-10-27 before the tag-time capture (VERIFICATION-RECORDS.md,
"Changes"): register statuses `merged` and `released` were not read as claims of a fix, so every merged
entry was listed as not demonstrated; a failing gate added no gap of its own; an item whose `dev` had
moved past its pinned base was reported as unresolved (35 items); a cell holding an escaped `\|` was split
in two (BF-58), and three §1b rows carried a sixth cell (BF-177, BF-179, BF-182). RT-NODE-FLOOR-TESTED now
gates on `official/dev` (merged-upstream; register BF-58 and BF-59 `merged 2026-10-26`), and
RT-CONNECT-PIN-CUTS gates `dev` and `master` with `v15.0.8` as its bad control (BF-65). Five register
entries written against the cut branches before they merged were re-graded by measurement on `8dbb60c2`,
each with a break-it run where one applies: BF-55, BF-65 and BF-88 `merged 2026-10-26`, BF-56 `closed,
did not occur`, BF-64 `closed, superseded`. **Re-run after the fixes** (same selection and kinds): 65
items, 51 PASS, 2 FAIL, 12 UNMEASURED; the two failures are BFQ-72 and BFQ-161, both pre-tag
requirements in the advisory forks.

## Open items a releaser must settle

As of `dev` `47723cda` (2026-10-26), with item 11 from `7ad3a67f`, and items 1 and 12–15, the entry bar and the
repository settings brought to `dev` `991b0654` on 2026-10-30. The decisions already made are in [decisions.md](decisions.md).
Whether cuts 3–5 ship in 16.0.0 is answered: all three are merged into `dev`, so they ship in 16.0.0
unless reverted.

**Required before the tag** (maintainer, 2026-10-26, session -66; queue `RT-16-RELEASE`): (a) a live
Pushover and APNs delivery check (`RT-16-LIVE-ALARMS`); (b) a real-rig soak on `dev` (`RT-16-RIG-SOAK`);
(c) the BF-72 and BF-161 fork fixes merged and published with 16.0.0 (`BFQ-72`, `BFQ-161`). None is met.
BF-193 is not a pre-tag requirement; its fix shape is decided (debug-gated payload logging through
`DEBUG_LOGGING`, [decisions](decisions.md)) and merged 2026-10-27 as #8856 (`dev` `eed31dca`).
The maintainer's definition of done before the tag (2026-10-27, `RT-16-RELEASE`) adds (d) a short quiet period
on `dev` with the final candidate, days not weeks, and states (b) as cohort confirmations from `dev` users
(AndroidAPS, Loop, Trio, xDrip+, a follower app, an mmol/L site).

**The entry bar** (maintainer, 2026-10-29; scope widened 2026-10-30): every single-tenant item of the next-gen
plan may join the 16.0.0 merge list, in priority order, once its matrix result is as stated, its red controls
and ablations pass, a revert has been rehearsed, and it has had time on `dev` with its cohort check. A miss at
the tag rolls to 16.1.0, or to 17.0.0 if it changes a default. On 2026-10-30 no item in
[In flight](#in-flight-for-this-release) has cleared it; #8874 is first in the order.

**Decisions open, with their owner:**

1. **The scope of BF-161's draft advisory** (maintainer): publish it now for BF-151 (released in 15.0.9)
   with BF-161 as a follow-up, or extend it to include BF-161 and publish it with the release that
   carries the fix. Packet: [bfq-161](../../reports/reviewer-packets/bfq-161-adv-phrf-1600-dev.md).
   *Decided 2026-10-27 (maintainer; queue `BFQ-161`): extend the draft advisory to cover BF-161 as well as
   BF-151, and publish it once, with 16.0.0.*
2. **BF-72's test inputs** (the original author of the regex-limit commits): the tests' hostile inputs
   are to be rebuilt in code before anything is published. Packet:
   [bfq-72](../../reports/reviewer-packets/bfq-72-adv-r3gv-1600-dev.md).
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
    keep the units, convert, or refuse. Queue `BFQ-194`. *2026-10-27 (maintainer): survey the clients first, then likely enforce mg/dL at write (convert a target labelled mmol and relabel it); survey running.* *Decided 2026-10-27 (maintainer): convert and always label. Fixed on local `bf/16.0.0-tt-units` `7b74110c`, **merged** to `dev` 2026-10-27 as `db3b9e4e` (#8872): every write path stores a Temporary Target in mg/dL labelled `mg/dl`; gate PASS, npm test and test:all pass. Owes a release-note line.*
11. **#8854's `failed` slot** (maintainer): under `reject`, a socket treatment array answers an item whose
    write cannot be confirmed (a lookup, similar-record match or insert error, such as a duplicate key) with a
    slot without `_id` carrying `failed: {status: 500, message: "Treatment write could not be confirmed"}`,
    where `47723cda` left the item out of the reply (`lib/server/websocket.js:557-563` on `7ad3a67f`;
    read, not measured). API v1 has no equivalent. List it in the 16.0.0 client notes as it is, or agree it
    alongside `refused` (and whether API v1 should match). Queue `ARCH-8854-FAILED`. *Decided 2026-10-27 (maintainer): ship it as it is, described in the client notes as experimental under `reject`; the per-item reply for every path is settled in ID-BATCH.*

12. **Which items clear the entry bar before the tag** (maintainer; 2026-10-30): in order, `write(intent)`
    release 1 (#8874, `WC-STEP-PATCH`), ID-FIRST-MATCH slices 1, 2, 5, 3, 4, 6 and 6a, ID-BATCH
    (`ID-BATCH-RESULTS`), the re-send switch (`ID-RESEND-SWITCH`), ID-UNIQUE-INDEX with
    `WRITE_IDENTIFIER_INDEX`, SPEC-ID-AMEND, #8857, ST-HARNESS, and ST-EVENT or ST-VIEWS if they clear it.
    Each one that changes a default (merge on match on new paths, stays deleted, the index built at boot under
    `try`) needs its own release-notes line and its cohort check.
13. **#8857's flag and rebase** (maintainer and the author): D-REG-FLAG (where the catalogue lives, and the
    flag's form); the branch is 109 commits behind `dev` with conflicts. Off by default either way.
14. **ST-VIEWS' wiring** (maintainer): #8875 computes the page, socket, plugin and alarm views from bounded
    queries; it is not wired in, and the alarms are safety-relevant (execution plan §7b).
15. **Multitenant items as alpha** (maintainer): whether anything ships dormant behind `serve` in 16.0.0, and
    the release notes' alpha wording (Q12a in the release allocation: the alpha label belongs to the
    multitenant bindings only). `serve` refuses every role on `dev` `991b0654`: no role in
    `lib/server/serve/roles.js` is marked `multitenant` (read-derived).

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
staging PR #8824 cannot meet `master`'s protection as it stands. Read again 2026-10-30 at `dev` `991b0654`:
unchanged.

**Decided, settings change owed** (maintainer, 2026-10-26, relayed via session -66; applied by the
maintainer): `master` requires only the *Tests pass* check (job `tests-pass`, `.github/workflows/main.yml:317`
on `dev`, `if: always()`, needing every test job and the pull-request Docker validation) and one
approving review. The decision as relayed names `master`; `dev`'s required check is not part of it. Caveat: *Tests pass* accepts `skipped` as well as `success` from every job it needs
(`main.yml:327-337`), so a test job skipped in full would still let it pass.

**Follow-ups filed 2026-10-25:** `RT-BUNDLE-THEME-SPLIT` (page-bundle budget option B: load the modern
theme's code only when it is chosen; owner Andy Low or the maintainer; not started). `RT-BOOT-INDEX-AWAIT`
merged with #8849.

**Merge order before the tag** (next-gen plan §1a, 2026-10-29; rows 1, 2 and 2a merged 2026-10-30): #8855
(Crowdin), the BF-72 and BF-161 fork branches brought up to `dev` and merged, then the `master` protection fix
and #8824. The entry-bar items (open item 12) join in their own order as each clears the bar.

**Next merges** (a suggestion for the maintainers, not a decision; written 2026-10-26 and 2026-10-27):

1. The follow-ups, each in a themed PR: `RT-JSDOM-REST` (scope B), `ID-SIMPLE-MATCH` with BF-169's
   remaining client work, `RT-BUNDLE-THEME-SPLIT`.
2. BF-72 and BF-161 through their advisory forks, published with the release that carries them; each has
   a merge of `dev` `8dbb60c2` prepared locally (`f64f78c4`, `8dcf1537`; R17), ready to push to its fork.
   *2026-10-30:* the fork heads are `a9da33ff` and `1dce7722` (pushed 2026-10-27, containing `dev`
   `7abe1cf6`); a merge of `dev` `991b0654` and a re-run in each is owed.

**Before the tag:** the three requirements above (the live delivery check, the real-rig soak, BF-72 and BF-161), the other live acceptance checks #8605 leaves to the maintainer (Pushover emergency
delivery, acknowledgement and cancellation; alarm de-duplication over its real window; APNs delivery
to a phone; production hosting, upgrade and rollback; physical-device accessibility), the call for
testers ([testing-notes.md](testing-notes.md)), the tag message and the release notes (written last,
from the list below), a full run on the candidate in the integration record, the verification record
capture, the reconciliation in [releases/README.md](../README.md).

## For the release notes

A draft list of what the release notes must say; the notes themselves are written last, once the
candidate is named.

- (#8865, if merged) Nightscout stops cleanly on SIGTERM and SIGINT on every start path: it closes
  its connections and exits 0, or exits 1 if it is still open after 8 s. In the Docker image,
  `docker stop` takes well under a second instead of 10 s and a forced kill. One case changes
  outcome: a container under `restart: on-failure` that receives SIGTERM from something other than
  `docker stop` used to ignore it and keep running; it now exits 0 and stays stopped. The image's
  command is `nightscout single` (the same server as `node lib/server/server.js`, which still works
  as an explicit command); tooling that matches PID 1's command line sees the new name. `nightscout`
  is a new executable with `single`, `healthcheck`, `version`, `env` and `diagnose data`;
  `nightscout serve` is reserved for a multitenant Nightscout, which is not built yet, so every
  role exits 64.
- (BF-213, if merged) Sites with `PUMP_ENABLE_ALERTS` get pump alarms at the severity Loop assigns to its pump
  status, with Loop's text: "No Insulin", "Pod Expired" and Medtronic "Signal Loss" now alarm, which they never did.
  Candidate note, read from #8865 at `1b2801f7` by session -7d, not run: a custom entrypoint or command that
  puts `node` in front of the image's default command now runs `node nightscout single` and fails to start.

- The Node floor `^22.23.4 || ^24.22.1 || >=26.12.1`, and the message the server prints when it refuses
  to start.
- The legacy Dexcom Share and MiniMed CareLink bridges are removed; leftover bridge settings stop the
  site with a page naming the replacements; Dexcom Share data comes in through `nightscout-connect`.
- MongoDB 4.4 or newer is required to start (cut 3, driver 7): on 3.6, 4.0 or 4.2 the site does not
  serve data and shows a page naming the database server's version and the minimum it needs (BF-182); the
  fix is to upgrade MongoDB. 5.0 through 8.0 are the supported, tested range; 4.4 starts but is untested.
- MongoDB 8.0 itself does not start on Linux kernels 6.19 to 7.0.13, which includes Ubuntu 26.04's Linux 7.0: it
  logs "MongoDB cannot start: Linux kernel versions 6.19 and newer has a known incompatibility" (MongoDB's
  SERVER-121912, not a Nightscout change). On such a host, run MongoDB 5.0 to 7.0, or keep the database on a host
  with an older kernel, until MongoDB supports it (BF-202).
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
- #8854 under `WRITE_VALIDATION=reject`: the realtime socket checks Temporary Targets too and answers a
  refused one with a `refused` slot in input order, without `_id`, storing the rest of the batch (15.0.9 and
  `47723cda` stored them all); a treatment whose write cannot be confirmed is answered with a `failed` slot
  (open item 11). The `Nightscout-Data-Warnings` header on API v3 reads is experimental and off unless
  `API_V3_DATA_WARNINGS=true`. Nothing changes with `WRITE_VALIDATION` off.
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
- The glucose pentagon and PGR in the Distribution report (#8860): what the five values and the risk figure
  are, that the report withholds them when too little of the period has readings, and the PR's own caveats
  carried verbatim: the withholding rules are "implementation guards, not validated clinical PGR
  thresholds", PGR is a research metric, and the numerical checks "do not constitute third-party clinical
  validation". It is a report figure, not a treatment recommendation; talk to the care team before acting
  on it.
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
