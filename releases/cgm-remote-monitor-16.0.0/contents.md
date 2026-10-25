# cgm-remote-monitor 16.0.0 — contents

**Status: in development. Nothing tagged or released.** 16.0.0 is the next release from `dev`
(maintainer, 2026-10-21; queue `RT-VERSION`). Contributor-facing; full technical depth intended.
Measured 2026-10-25 against `official/dev` `eb72a1d3` (the merge of #8828) and `official/master`
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
| `dev` head | `eb72a1d3` (merge of #8828, 2026-10-25 16:29:06Z, by AndyLow91), tree `9444a472` |
| Commits on `dev` | 183 — `git rev-list --count official/master..official/dev` |
| First-parent commits on `dev` | 12 — `git rev-list --first-parent --count official/master..official/dev`: 11 PR merges and the cycle's version bump `04d435eb` (`git log --first-parent --format=%s official/master..official/dev \| grep -vc '^Merge pull request'` prints 1) |
| Diff on `dev` | 187 files, +13205/−5425 — `git diff --shortstat official/master official/dev` |
| `package.json` version | `16.0.0` — `git show official/dev:package.json \| grep '"version"'` |
| `engines.node` | `^22.23.4 \|\| ^24.22.1 \|\| >=26.12.1` (AndyLow91's `6a146a4c`, "require Node Brotli security patches"; supersedes the decided `^22.12 \|\| >=24`) |
| Docker base image | `node:24.22.1-alpine` for builder and runtime (`32489dc5`) |
| Connector pin | `nightscout-connect` exactly `0.1.0`, as in 15.0.9 |
| Staging PR | #8824 (`dev` → `master`, "new dev branch post 15.0.9 release"): open, head `eb72a1d3`, mergeable, `reviewDecision` `REVIEW_REQUIRED`; 72 checks passed, 3 skipped — `gh pr view 8824`, `gh pr checks 8824` |
| CI on `eb72a1d3` | `pull_request` run 40211897810 and `push` run 40211895500: every test and browser cell passed; the push run's *Publish to Docker Hub* passed, so `dev`'s image is published; CodeQL passed on both events — `gh run view <id> --json jobs` |

## Provenance

Every figure below is labelled. **reproduced**: something was executed and the output observed.
**read-derived**: read from source, a PR body or CI metadata. Commit counts, SHAs, PR states, CI
results and the conflict counts are reproduced with the commands shown. No test suite was run on
`eb72a1d3` by this session; the runs reported on it are the dependency refresh session's and the
BF-176 session's (see [In flight](#in-flight-for-this-release) and the integration record). No live site, vendor account or Docker image was run.

## What is merged so far

Merge SHAs: `git log --first-parent --format='%h %ad %an %s' --date=iso official/master..official/dev`.
Every merge below was made by AndyLow91 on 2026-10-25. Register ids refer to the
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

None of these merged trees was re-run locally by this programme; each PR's own CI passed.

## Merge state

- **#8823 merged twice, without duplicated code** (reproduced). It was folded into cut 1 as
  `42a2729e` and also merged on its own as `4c1a5f1a` before #8828. On `eb72a1d3`, `git grep
  bridgeServerToConnect official/dev` finds one definition, in `lib/server/bridge-connect-compat.js`,
  and that file is byte-identical to `806ff2f0`'s (compared by hash). `tests/bridge-connect-compat.test.js`
  carries the `describe('BRIDGE_SERVER mapping')` block twice (lines 127–182 and 184–239, identical),
  so those cases run twice: a test-only clean-up.
- **Cuts 2–5 against `eb72a1d3`** (reproduced; `git rev-list --left-right --count official/dev...<cut>`
  and `git merge-tree --write-tree --name-only --no-messages official/dev <cut>`): cut 2 `b6e8c7cd` 459
  behind / 159 ahead, 20 conflicting paths; cut 3 `ebb690cf` 459 / 222, 25; cut 4 `b80aa147` 459 / 301,
  43; cut 5 `b1bdaca0` (#8605) 335 / 399, 42. Cut 2's catch-up is in progress (below).

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
  and 22.0–22.23.3, 24.0–24.22.0 and 26.0–26.12.0. The test matrix on `dev` is Node 22.23.4, 22,
  24.22.1, 24, 26.12.1 and 26 × MongoDB 5.0 and 6.0, plus one Node 22 × MongoDB 4.4 cell that
  `36fa3121` keeps as "the existing required check until branch protection is updated separately";
  browser tests run on the same six Node versions × Chromium, Firefox and WebKit (read from
  `.github/workflows/main.yml`). MongoDB 4.4 was deprecated in 15.0.9; no server check that refuses it
  was found
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

Branch heads as of 2026-10-25. The maintainer opened #8834 and #8835 against `dev` at 17:28Z; the rest are not open as PRs to `dev`.

| work | branch | head | state | queue |
|---|---|---|---|---|
| cut 2: page bundles and the build/runtime split | `wip/cut2-onto-cut1-16.0.0` (local), catching `chore/build-runtime-separation` up with `dev` `eb72a1d3` | pending (peer session) | in progress; `official/chore/build-runtime-separation` is still `b6e8c7cd` | `RT-2`, `RT-REBASE` |
| BF-176 fix: `axios` and `lodash` declared as runtime dependencies | `bf/axios-runtime-dependency`, **#8834** to `dev` | `f3d73f43` (`43ed462a` plus a merge of `eb72a1d3`; 0 behind, 2 ahead, 3 files) | open PR | `BFQ-176` |
| dependency refresh: `compression` 1.8.2, `follow-redirects` 1.16.1, `source-map-js` 1.2.2 | `deps/16.0.0-security-refresh`, **#8835** to `dev` | `341b843a` (0 behind `eb72a1d3`, 3 ahead, merges cleanly) | open PR | `BFQ-163` |
| `sanitize-html` 2.18, its own PR to `dev` (maintainer: integrate as quickly as possible) | `deps/sanitize-html-2.18` (peer session) | pending | in progress | `BFQ-163` |
| BF-72: a caller-supplied regular expression can hold the database for minutes | `bf/regex-limits`, in the private fork of its draft advisory | `1833ab00` on `dev` `04d435eb` | in the fork; no fork PR opened yet; owes a merge of `dev` `eb72a1d3` | `BFQ-72` |
| BF-161: a deeply nested pattern on three query endpoints makes that request fail | `bf/entries-pattern-limit`, in the private fork of its draft advisory | `d2c4df9f` on `dev` `04d435eb` | in the fork; no fork PR opened yet; owes a merge of `dev` `eb72a1d3` | `BFQ-161` |
| BF-158: the count=0 tests assume an empty database | none found locally or on `official` on 2026-10-25 | — | not started | `BFQ-158` |
| test tier map, tier check and inner-loop selection (`test:affected`, `test:smoke`) | `test/tier-map-and-selection`, **#8839** (draft) to `dev` | `21620995` (`dev` `a20469dc` merged in) | open draft; lands after #8837 (cut 2) and #8838 (test and CI hygiene), rebased onto that `dev` | `RT-TEST-TIERS` |

BF-72's fix, by mechanism: a length cap on every pattern and a time limit on every query whose filter
holds a regular expression, generated ones included; a refusal check for caller-written patterns
only behind `QUERY_REGEX_REFUSE_UNSAFE`, default off. BF-161's fix: a nesting-depth limit checked
before the pattern is parsed or expanded. Both keep the intended uses in the maintainer's public gist
`dbe590ab` working, and each is published with the release that carries it.

The dependency refresh, as its session reports it (read-derived here; not re-run): `feb3944c` moves
`compression` to 1.8.2 (the `package.json` range raised to `^1.8.2`), `ad458fa0` pins
`follow-redirects` 1.16.1 by override, `341b843a` moves `source-map-js` to 1.2.2, and only those three
lockfile entries change. `npm test` is 3378 passing / 3 pending / 1 failing on both `dev` `eb72a1d3` and
the branch, and the Chromium browser suite 455 passing on both (Node 24.22.1, npm 11.19.1, MongoDB
7.0.43). `npm audit` at 2026-10-25 17:13Z: `dev` 23 findings (8 high, 1 critical), the branch 18 (3
high, 1 critical); with `--omit=dev`, 16 and 11. A reading a minute earlier gave 20 on `dev`: a change
in the advisory data, not in the tree. That branch leaves `sanitize-html` at 2.17.5; 2.18 is its own
PR (row above, and open item 2).

## Known defects on `dev` now

| defect | what | exposure | queue |
|---|---|---|---|
| BF-176 | a production install (`npm ci --omit=dev`, the Dockerfile's commands) stops at boot with `Cannot find module 'axios'` (`bootevent.js:114`) when `IMPORT_CONFIG` is set; `lodash` is undeclared and supplied transitively | moved from cut 1 only to `dev` and the 16.0.0 line, because #8828 merged before the fix; **reproduced** on `eb72a1d3` by the BF-176 session (Node 24.22.1, npm 11.19.1, MongoDB 7.0.43; unset, both installs boot; full `npm ci` boots with the settings applied); `dev`'s Docker image is published; no release carries it | `BFQ-176` |
| BF-177 | `tests/glucosedistribution.test.js:116`, "includes the first selected interval when earlier hours are excluded", added by `ba5f7f4b` (#8812's head commit), passes with `TZ=UTC` and fails with `TZ=America/Los_Angeles` ("expected '213.5' to be '117.5'"; deps refresh session's run); CI runs in UTC. The test's stand-in for the profile's time zone uses the machine's zone | test only: the report applies the profile's time zone as intended (read-derived, not run in a browser) | `BFQ-177` |
| duplicated test block | the `BRIDGE_SERVER mapping` cases run twice (see Merge state) | none | — |

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

As of `dev` `eb72a1d3` (2026-10-25). The decisions already made are in [decisions.md](decisions.md).

**Decisions open, with their owner:**

1. **Whether cut 2 ships in 16.0.0 or as its own release** (maintainers). The versioning policy §8.3
   leaves open whether the cuts ship separately or combined.
2. **`sanitize-html` 2.18's stored-output difference** (maintainer, when its PR is open). The maintainer
   asks for 2.18 to be integrated as quickly as possible, as its own PR (`deps/sanitize-html-2.18`, in
   flight). Reported by the deps refresh session: 2.17.6 and later need the htmlparser2 12, domhandler 6,
   domutils 4, dom-serializer 3 and domelementtype 3 majors, and 1 of 35 purifier inputs is stored
   differently (a malformed `textarea` sequence is stored as an `img` element with `src="x"` instead of
   the empty string; the event handler is still stripped). The Node 20 reason given for the pin at
   `lib/server/purifier.js:38` no longer applies under the 16.0.0 floor. The three `sanitize-html`
   advisories named in the 15.0.9 triage stay open until it merges.
3. **The scope of BF-161's draft advisory** (maintainer): publish it now for BF-151 (released in 15.0.9)
   with BF-161 as a follow-up, or extend it to include BF-161 and publish it with the release that
   carries the fix. Packet: [bfq-161](../../reports/reviewer-packets/bfq-161-bf-entries-pattern-limit.md).
4. **BF-72's test inputs** (the original author of the regex-limit commits): the tests' hostile inputs
   are to be rebuilt in code before anything is published. Packet:
   [bfq-72](../../reports/reviewer-packets/bfq-72-bf-regex-limits.md).
5. **BF-95** (maintainer): a notice for readings that arrive dated ahead of the server clock, or the
   status quo. Packet: [bfq-95](../../reports/reviewer-packets/bfq-95.md).
6. **BF-152** (maintainer, with the AndroidAPS developers): is API v3 `settings` meant to be readable
   with a follower's read token, or admin-only? Packet: [bfq-152](../../reports/reviewer-packets/bfq-152.md).
7. **Dependabot configuration** (maintainer): version updates targeting `dev`, dismissing alerts that
   are fixed on `dev` or not reachable, or releasing more often. Packet:
   [dependabot-config](../../reports/reviewer-packets/dependabot-config.md).
8. **Branch protection's required check** (maintainers): `36fa3121` keeps the Node 22 × MongoDB 4.4
   cell only because it is a required check.

**Suggested order of the next merges to `dev`** (a suggestion for the maintainers, not a decision):

1. The BF-176 fix, #8834 (`BFQ-176`): `dev` and its published image carry the boot crash; packaging only.
   Packet: [bfq-176](../../reports/reviewer-packets/bfq-176-bf-axios-runtime-dependency.md).
2. The dependency refresh, #8835, and `sanitize-html` 2.18 (`BFQ-163`), before cut 2, whose catch-up then takes
   the lockfile changes in one merge.
3. Cut 2 (`RT-2`), once its catch-up merge of `dev` is pushed.
4. The follow-ups cut 1 unblocked, each its own PR: `RT-CONNECT-TEARDOWN`, `RT-D3-SUITE`, `BFQ-158`,
   `BFQ-177`, `RT-JSDOM-REST` (scope B), and `ID-SIMPLE-MATCH` with BF-169, which
   touches `lib/server/entries.js`, a file cut 2 also changes, so after cut 2.
5. BF-72 and BF-161 through their advisory forks, each after a merge of `dev`, published with the
   release that carries them.

**Before the tag:** the call for testers ([testing-notes.md](testing-notes.md)), the tag message and the
release notes, which must name the Node floor and the message the server prints when it refuses to
start, the bridge removal and the known issues; a full run on the candidate in the integration record;
the verification record capture; the reconciliation in [releases/README.md](../README.md).

## What a reviewer must verify before this is relied on

1. That AndyLow91's `b20a710b` and `bbca2892` give the results of the 2026-10-21 reproductions for all
   four unit combinations (BF-172, BF-173); the merged trees were not re-run here.
2. Which advisory is the 1 critical in the 2026-10-25 `npm audit` on both `dev` and the refresh
   branch; this file does not name it.
3. BF-177's reading that the glucose distribution report, not only its test, is right outside UTC
   (read-derived).

---

*Draft, 2026-10-25. Prepared locally; nothing pushed, tagged, merged or published by this programme.
Requires maintainer review before anything here is relied upon.*
