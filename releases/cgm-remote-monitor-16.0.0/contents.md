# cgm-remote-monitor 16.0.0 — contents

**Status: in development. Nothing tagged or released.** 16.0.0 is the next release from `dev`
(maintainer, 2026-10-21; queue `RT-VERSION`). Contributor-facing; full technical depth intended.
Measured 2026-10-25 (to 19:51Z) against `official/dev` `2bc298b9` (the merge of #8838) and `official/master`
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
| `dev` head | `2bc298b9` (merge of #8838, 2026-10-25 19:42:01Z, by bewest), tree `2b9ee5c7` |
| Commits on `dev` | 204 — `git rev-list --count official/master..official/dev` |
| First-parent commits on `dev` | 15 — `git rev-list --first-parent --count official/master..official/dev`: 14 PR merges and the cycle's version bump `04d435eb` |
| Diff on `dev` | 192 files, +13540/−5507 — `git diff --shortstat official/master official/dev` |
| `package.json` version | `16.0.0` — `git show official/dev:package.json \| grep '"version"'` |
| `engines.node` | `^22.23.4 \|\| ^24.22.1 \|\| >=26.12.1` (AndyLow91's `6a146a4c`, "require Node Brotli security patches"; supersedes the decided `^22.12 \|\| >=24`) |
| Docker base image | `node:24.22.1-alpine` for builder and runtime (`32489dc5`) |
| Connector pin | `nightscout-connect` exactly `0.1.0`, as in 15.0.9 |
| Supported MongoDB | 5.0 through 8.0 (`README.md` on `dev`, from #8838's `039be646`); 4.4 and earlier unsupported |
| Staging PR | #8824 (`dev` → `master`, "new dev branch post 15.0.9 release"): open, head `2bc298b9`, mergeable, `reviewDecision` `REVIEW_REQUIRED`; 30 checks passed, 3 skipped — `gh pr view 8824`, `gh pr checks 8824` |
| CI on `2bc298b9` | `push` run 40227267487 and `pull_request` run 40227271881 passed every cell of the edge matrix (below); the push run's *Publish to Docker Hub* passed at 19:48:15Z, so `dev`'s published image is `2bc298b9`'s; CodeQL passed on both events — `gh run view <id> --json jobs` |
| CI on the merges before it | `eb72a1d3` push run 40211895500 published an image at 17:15:18Z (it carries BF-176); `93f152bd` push run 40217943528 published one at 17:53:31Z (BF-176 fixed); `a20469dc` push run 40219064024 failed *Browser tests* (24.22.1, firefox) and (26, firefox) and skipped publishing; the `pull_request` runs of `93f152bd` and `a20469dc` each failed one Firefox cell. Each Firefox failure is `tests/browser/legacy-reports.test.js` "should produce some html", `page.waitForFunction: Timeout 30000ms exceeded` with the report still loading (454 passing, 1 failing) |

## Provenance

Every figure below is labelled. **reproduced**: something was executed and the output observed.
**read-derived**: read from source, a PR body or CI metadata. Commit counts, SHAs, PR states, CI
results and the conflict counts are reproduced with the commands shown. No test suite was run on
`dev` by this session; the runs reported are the PR authors' and peer sessions', read from the PR
bodies (see the integration record). No live site, vendor account or Docker image was run.

## What is merged so far

Merge SHAs: `git log --first-parent --format='%h %ad %an %s' --date=iso official/master..official/dev`.
Every merge below was made on 2026-10-25: the first eleven by AndyLow91, #8834, #8835 and #8838 by
bewest. Register ids refer to the
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

None of these merged trees was re-run locally by this programme. The merged trees' CI is in
[Identity](#identity).

## Merge state

- **#8823 merged twice, without duplicated code** (reproduced). It was folded into cut 1 as
  `42a2729e` and also merged on its own as `4c1a5f1a` before #8828. On `eb72a1d3`, `git grep
  bridgeServerToConnect official/dev` finds one definition, in `lib/server/bridge-connect-compat.js`,
  and that file is byte-identical to `806ff2f0`'s (compared by hash). The test block that ran twice
  was removed by #8838 (`879ab51e`); on `2bc298b9` `tests/bridge-connect-compat.test.js` has one
  `describe('BRIDGE_SERVER mapping')`.
- **Cuts 2–5 against `2bc298b9`** (reproduced; `git rev-list --left-right --count official/dev...<cut>`
  and `git merge-tree --write-tree --name-only --no-messages official/dev <cut>`): cut 2
  `official/chore/build-runtime-separation` `ee94b148` (#8837) 11 behind / 185 ahead, merges cleanly; the
  published cut 2 `b6e8c7cd`, 21 conflicting paths; cut 3 `ebb690cf` 480 / 222, 26; cut 4 `b80aa147`
  480 / 301, 44; cut 5 `b1bdaca0` (#8605) 356 / 399, 43.

## Version: 16.0.0, major

Decided by the maintainer on 2026-10-21 (`RT-VERSION` answered). Surfaces touched (versioning policy
§6.2), read from the merged PRs:

- [x] S1 the realtime socket contract: #8797 stores records the socket used to drop as copies (a
  correction)
- [ ] S2 plugin interface, boot sequence or client bundle: #8831 adds an opt-in theme; no plugin
  interface change was found
- [x] S3 environment-variable surface: `THEME=modern` (#8831, a new value); leftover legacy bridge
  settings stop the site with a page naming the replacements (cut 1)
- [ ] S4 stored document shape
- [x] S5 Node or MongoDB runtime floor, **major**: `lib/server/runtime-policy.js` reads `engines.node`
  and exits at boot outside `^22.23.4 || ^24.22.1 || >=26.12.1`, which stops Node 20, 21, 23 and 25,
  and 22.0–22.23.3, 24.0–24.22.0 and 26.0–26.12.0. The README states MongoDB 5.0 through 8.0 (#8838);
  4.4 and earlier are unsupported, and no server check that refuses them was found. The test matrix on
  `dev` (#8838, the edge policy) is Node 22.23.4 and 26 × MongoDB 5.0 and 8.0, plus the cells branch
  protection requires, (24, 6), (22, 6) and (22, 4.4); browser tests run on Node 26 × Chromium, Firefox
  and WebKit (read from `.github/workflows/main.yml`)
- [x] S6 an ingestion path, **major**: the legacy Dexcom Share bridge and MiniMed CareLink
  (mmconnect) are removed; Dexcom Share data comes in through `nightscout-connect`
- [ ] S7 alarms or notifications: #8816 changes how long a snooze lasts on a page that is not signed
  in (a correction)
- [x] S8 the version string: `16.0.0`
- [x] S9 what the client computes and shows a person: BF-172, BF-173 and BF-174 change the Bolus Wizard
  Preview and the Careportal Bolus Wizard where the profile and display units differ, or where a
  profile other than the active one is chosen; #8812 and #8808 change report figures

**Classification:** MAJOR, because of S5 and S6 (cut 1). **Directory name says:** 16.0.0.
**Settled?** Yes, by the maintainer, 2026-10-21.

## In flight for this release

Branch heads as of 2026-10-25, 19:51Z.

| work | branch | head | state | queue |
|---|---|---|---|---|
| cut 2: page bundles and the build/runtime split | `chore/build-runtime-separation`, **#8837** to `dev` (opened 19:22Z) | `ee94b148`; the fix `bd941200` and a merge of `dev` `2bc298b9` are on `wip/cut2-onto-cut1-16.0.0` (local, peer session), not pushed | open PR; its CI failed the required check (below) | `RT-2` |
| test tier map, tier check and inner-loop selection (`test:affected`, `test:smoke`) | `test/tier-map-and-selection`, **#8839** (draft) to `dev` | `21620995` (`dev` `a20469dc` merged in) | open draft; lands after #8837 (cut 2) and #8838 (test and CI hygiene), rebased onto that `dev` | `RT-TEST-TIERS` |
| BF-72: a caller-supplied regular expression can hold the database for minutes | `bf/regex-limits`, in the private fork of its draft advisory | `1833ab00` on `dev` `04d435eb` | in the fork; no fork PR opened yet; owes a merge of `dev` | `BFQ-72` |
| BF-161: a deeply nested pattern on three query endpoints makes that request fail | `bf/entries-pattern-limit`, in the private fork of its draft advisory | `d2c4df9f` on `dev` `04d435eb` | in the fork; no fork PR opened yet; owes a merge of `dev` | `BFQ-161` |

BF-72's fix, by mechanism: a length cap on every pattern and a time limit on every query whose filter
holds a regular expression, generated ones included; a refusal check for caller-written patterns
only behind `QUERY_REGEX_REFUSE_UNSAFE`, default off. BF-161's fix: a nesting-depth limit checked
before the pattern is parsed or expanded. Both keep the intended uses in the maintainer's public gist
`dbe590ab` working, and each is published with the release that carries it.

**Cut 2, #8837** (read from the PR body and `git log`; the runs are the preparing session's). The
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
The fix is `bd941200` (peer session: `--all=false` on the inner nyc, plus
`docs/test-specs/env-runner.md`), on `wip/cut2-onto-cut1-16.0.0`, not pushed; cut 2 also merges `dev`
`2bc298b9` before its next push.

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

## Known defects on `dev` now

| defect | what | exposure | queue |
|---|---|---|---|
| Firefox legacy-reports wait | `tests/browser/legacy-reports.test.js` "should produce some html" timed out at its fixed 30 s wait (`12154df9`) in one or two Firefox cells of the CI runs on `93f152bd` (`pull_request`) and `a20469dc` (both events); the push run on `a20469dc` therefore skipped the Docker publish. It passed on `2bc298b9`. Cut 2 replaces the fixed wait with a progress-aware one (fails after 15 s with no completed request, 60 s ceiling) | test only; no register entry filed | `RT-2` |

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

As of `dev` `2bc298b9` (2026-10-25). The decisions already made are in [decisions.md](decisions.md).

**Decisions open, with their owner:**

1. **Whether cut 2 ships in 16.0.0 or as its own release** (maintainers). The versioning policy §8.3
   leaves open whether the cuts ship separately or combined; #8837 targets `dev`, and its body says it
   ships in 16.0.0.
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

**Repository settings, for the maintainer** (from #8838's body; branch protection read 2026-10-25:
`dev` requires `Run Tests (24, 6)`; `master` requires `Run Tests (22, 6)`, `Run Tests (22, 4.4)` and
`Run Tests (24, 6)`; no rulesets). Nothing in a PR changes these:

1. `master`: drop the required check `Run Tests (22, 4.4)`; MongoDB 4.4 is unsupported and the cell
   exists only for this check. Then delete its `include` entry.
2. `dev` and `master`: move the `Run Tests (24, 6)` and `Run Tests (22, 6)` requirements to edge cells
   (for example `Run Tests (22.23.4, 8.0)` and `Run Tests (26, 8.0)`, and `(22.23.4, 5.0)` and
   `(26, 5.0)` if the MongoDB floor should also gate merges), then delete those `include` entries.
3. Optionally, require `Browser tests (26, chromium)`, `(26, firefox)` and `(26, webkit)`, whose names
   are now stable.

**Follow-ups filed 2026-10-25:** `RT-BUNDLE-THEME-SPLIT` (page-bundle budget option B: load the modern
theme's code only when it is chosen; owner Andy Low or the maintainer; not started) and
`RT-BOOT-INDEX-AWAIT` (boot awaits its collection and index creation, the cause of the API3 hook
timeout; a product change; not started).

**Merge order** (a suggestion for the maintainers, not a decision): #8837 and #8838 in either order (a
`git merge-tree` of the two was clean); #8838 merged first. Then:

1. Cut 2, #8837 (`RT-2`), once `bd941200` and its merge of `dev` `2bc298b9` are pushed and its CI passes.
2. Peer session -b7's test tiers (`RT-TEST-TIERS`), rebased onto that `dev`, as one PR.
3. The other follow-ups, each in a themed PR: `RT-JSDOM-REST` (scope B), `ID-SIMPLE-MATCH` with BF-169
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
- MongoDB 5.0 through 8.0 are supported; 4.4 and earlier are not.
- The opt-in `THEME=modern` dashboard (#8831).
- The Bolus Wizard Preview and Careportal Bolus Wizard unit fixes (BF-172, BF-173) and the profile
  picker (BF-174); BF-09 (the socket's duplicate check keeps zero temps, cancels and zero amounts); #8816's snooze; #8812 and #8808's report figures.
- One stored-text change from `sanitize-html` 2.18.1 (#8835): a malformed empty
  `<textarea></textarea/>` followed by an image with an event handler is now stored as the image tag
  without its handler (`<img src="x" />`), where 2.17.5 stored nothing (the empty string). The other 34
  corpus inputs are stored identically.
- If cut 2 ships in 16.0.0: page bundles, build and runtime separated (`npm ci` with development
  dependencies, then prune), no late minification, `DEBUG_MINIFY` without effect, the load-failure
  panel, and a third-party plugin that hooks into the page to be tested before upgrading.
- The known issues at the tag.

## What a reviewer must verify before this is relied on

1. That AndyLow91's `b20a710b` and `bbca2892` give the results of the 2026-10-21 reproductions for all
   four unit combinations (BF-172, BF-173); the merged trees were not re-run here.
2. Which advisory is the 1 critical in the 2026-10-25 `npm audit` on both `dev` and the refresh
   branch; this file does not name it.
3. That the PR-body figures recorded here for #8835, #8837 and #8838 match a re-run; none was re-run
   by this programme.

---

*Draft, 2026-10-25. Prepared locally; nothing pushed, tagged, merged or published by this programme.
Requires maintainer review before anything here is relied upon.*
