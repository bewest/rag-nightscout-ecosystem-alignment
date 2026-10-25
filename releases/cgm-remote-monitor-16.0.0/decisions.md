# cgm-remote-monitor 16.0.0 — decisions

*Contributor-facing. Living record of the decisions that shape 16.0.0, taken from 2026-10-21, as of
`dev` `2bc298b9` (2026-10-25). Each row states the decision as it stands, with its date and who made
it. Item state is in `queue/work-queue.yaml`; what 16.0.0 contains and what is still open is in
[contents.md](contents.md); the test evidence is in the
[16.0.0 integration record](../../docs/30-design/remedial/rc-16.0.0-integration-record.md). BF-72 and
BF-161 appear by mechanism only: both are live on the shipping release, and this repository is
public.*

## The cycle

| decision | who, when | queue | as it stands |
|---|---|---|---|
| **Priorities for the cycle**: (1) modernization, cut 1 first, then cut 2; (2) backfixes that affect dosing or security; (3) other exposure fixes, only where no cut or modernization branch already covers them | maintainer, 2026-10-21 | `RT-REBASE`, `RT-1`, `RT-2` | cut 1 merged 2026-10-25; cut 2 is #8837, open |
| **The next release is 16.0.0, and cut 1 lands on `dev` now**; 15.0.10 is not released as a separate patch | maintainer, 2026-10-21 | `RT-VERSION` (answered) | `806ff2f0` declared 16.0.0; #8828 merged as `eb72a1d3` |
| **#8823 (the `BRIDGE_SERVER` mapping) is folded into cut 1** as `42a2729e`, authorship kept, and closed in favour of #8828 | maintainer, 2026-10-21 | `RT-1` | #8823 was also merged on its own by AndyLow91 on 2026-10-25 (`4c1a5f1a`, before #8828). Checked: one `bridgeServerToConnect` on `eb72a1d3`, and `lib/server/bridge-connect-compat.js` is byte-identical to `806ff2f0`'s; the test file carries the mapping block twice (contents, Merge state) |
| **The dosing changes merge in order**: BF-174's fix (#8826) only with or after BF-173's (#8825), never alone | maintainer, 2026-10-21 (the ordering hazard recorded in `BFQ-174`) | `BFQ-173`, `BFQ-174` | met: #8825 `dfd659ba` at 13:12Z, #8826 `e2857b89` at 13:21Z, 2026-10-25 |
| **The 2026-10-25 merges to `dev`**: #8831, #8825, #8826, #8827, #8823, #8819, #8797, #8816, #8812, #8808 and #8828, with AndyLow91's own commits on #8825 (`b20a710b`), #8819 (`bbca2892`) and #8828 (contents, What is merged so far) | AndyLow91, 2026-10-25 | the items in contents | merged; not released |
| **PR bundling: changes go to `dev` in reasonably sized themed PRs**, not one or two commits per PR | maintainer, 2026-10-25 | `BFQ-163`, `RT-CONNECT-TEARDOWN`, `BFQ-158`, `BFQ-177`, `RT-D3-SUITE`, `RT-TEST-TIERS` | applied: `sanitize-html` 2.18.1 went into #8835 with the dependency refresh; the test and CI follow-ups went together as #8838; the test tiers go as one PR after cut 2 |
| **The later 2026-10-25 merges to `dev`**: #8834 (`93f152bd`), #8835 (`a20469dc`) and #8838 (`2bc298b9`) | bewest, 2026-10-25 | `BFQ-176`, `BFQ-163`, the #8838 items | merged; not released |

## Tests and the jsdom harness

| decision | who, when | queue | as it stands |
|---|---|---|---|
| **Option C for cut 1**: cut 1 ports the D3 chart, clock-client and pill-title coverage to the real-browser suite and keeps the jsdom harness for the rest | maintainer, 2026-10-21 | `RT-1` | on `dev` since #8828 |
| **`RT-JSDOM-REST` scope B**: a later change retires only the whole-bundle harness (`headless.js`, `benv-loader.js`, `benv-shim.js` and fixtures); `secure-jsdom.js`, `dom-globals.js` and `jsdom` stay as the middle test tier, with `jsdom` moving to `^29.1.1` | maintainer, 2026-10-21 | `RT-JSDOM-REST` | not started; on `eb72a1d3` three test files load the whole-bundle harness, one of them new from #8816 |
| **The connector teardown listener stays in the cut 1 merge**; its removal is a follow-up | maintainer, 2026-10-21 | `RT-CONNECT-TEARDOWN` | removed by #8838 (`38049fe6`), merged 2026-10-25 |

## Runtime

| decision | who, when | queue | as it stands |
|---|---|---|---|
| **The Node policy: a modern ceiling and an overlapping floor.** The range is open-ended at the top, so new Node majors start Nightscout without a code change, and the floor admits more than one maintained Node line, so an operator can move between them | maintainer, 2026-10-22 (asked while settling cut 2's CI matrix: "expand our future ceiling to modern while retaining a floor that overlaps with prior work; raising the floor is fine"); the earlier floor `^22.12 \|\| >=24` was decided on 2026-09-21 | `RT-1`, `RT-NODE-FLOOR-TESTED` | the range on `dev` is the row below |
| **The floor is raised to `^22.23.4 \|\| ^24.22.1 \|\| >=26.12.1`** for the Node Brotli security patches (`6a146a4c`, "require Node Brotli security patches"), superseding `^22.12 \|\| >=24`; the Docker image is pinned to `node:24.22.1-alpine` (`32489dc5`) and CI tests the exact floors 22.23.4, 24.22.1 and 26.12.1 beside the latest 22, 24 and 26 | AndyLow91, 2026-10-25, on the cut 1 branch before the merge | `RT-1` | on `dev`. Node 25 and 26.0–26.12.0 are now outside the range as well. CI's exact-floor cells were narrowed to the edges by the row below |
| **MongoDB 4.4 leaves the test matrix**, except one Node 22 × MongoDB 4.4 cell kept as the existing required check until branch protection is updated (`36fa3121`) | MongoDB 4.4 deprecated in 15.0.9 (maintainer, 2026-09-23); the cell kept by AndyLow91, 2026-10-25 | `RT-1` | on `dev`, kept by #8838; the settings change is the maintainer's (contents, Repository settings) |
| **The MongoDB edges are 5.0 and 8.0**, and the README states 5.0 through 8.0, widened after the full suite passed on MongoDB 8.0.29 | maintainer, 2026-10-25 | `RT-2`, #8838 | on `dev` since #8838 (`039be646`): README, `docs/runtime-upgrade.md` and the architecture overview; `npm test` 3409 / 3 / 0 on Node 22.23.4 and 26.12.1 against 8.0.29 (the PR's runs) |
| **CI tests the edges only**: Node at the floor `22.23.4` and the ceiling `'26'` (with `check-latest`); MongoDB `'5.0'` and `'8.0'`, each crossed with both Node edges; browsers, all three engines on Node 26; cells whose names branch protection requires are kept until the settings change | maintainer, 2026-10-25 | `RT-2`, #8838, `RT-NODE-FLOOR-TESTED` | on `dev` since #8838 (`29e8a36b`, `039be646`): 31 test and browser cells → 10, about 81 runner-minutes less per run; cut 2's own `maintained-mongo` and `replica-test` jobs follow it (`a7eb6942`, `bdb6c733`) |

## Query layer

| decision | who, when | queue | as it stands |
|---|---|---|---|
| **Cut 2 keeps its `queryLeaves` walker instead of the `traverse` package** when it takes `dev`'s query rules (the operator allowlist, path-aware value coercion, `$exists` operands, the two forms of `$in`/`$nin` id lists); `lib/utils/query-leaves.js` passes each leaf's key path, which the coercion rules read | maintainer, 2026-10-22 ("keep queryLeaves"); implemented on cut 2 in `948a142e` (2026-10-21) and given its own tests in `32978210` | `RT-2` | `dev` still uses `traverse` (`^0.6.6`); it changes when cut 2 (#8837) merges. Checked against cut 1's `traverse`-based `lib/server/query.js` on 50,000 generated and 20 edge queries: 0 differences (#8837's body) |

## Security fixes

| decision | who, when | queue | as it stands |
|---|---|---|---|
| **BF-72 fix shape (c)**, chosen by the rule that every intended use keeps working (the uses in the maintainer's public gist `dbe590ab`): a length cap on every pattern and a time limit on every query whose filter holds a regular expression, generated ones included; the refusal check applies only to caller-written patterns, and only with `QUERY_REGEX_REFUSE_UNSAFE=true`. **Default off; the name may be revisited** as the release candidate matures. Shape (a) is ruled out: it refuses patterns the `/times` and `/slice` generator builds | maintainer, 2026-10-21 | `BFQ-72` | `bf/regex-limits` `1833ab00`, semver minor |
| **BF-72 and BF-161 go through the private forks of their draft advisories**, not public PRs, and are published with the release that carries them | maintainer, 2026-10-21 | `BFQ-72`, `BFQ-161` | both branches pushed to the forks on 2026-10-21; no fork PR opened yet; both owe a merge of `dev` `eb72a1d3` |
| **BF-161's limit**: a nesting depth of 10, answered 400 before the pattern is parsed or expanded; the deepest intended use nests 1 level | prepared 2026-10-21; the value awaits the maintainer's confirmation | `BFQ-161` | `bf/entries-pattern-limit` `d2c4df9f`, semver patch |

## Packaging

| decision | who, when | queue | as it stands |
|---|---|---|---|
| **BF-176 goes to `dev` as its own PR**, with `axios` moved to `dependencies` at `^0.34.0` and `lodash` declared as exactly `4.18.1`, the version its existing override pins (a caret range fails with `EOVERRIDE`; the overrides block is unchanged); cut 1 was to take it in its next catch-up | maintainer, 2026-10-22 (a PR to `dev` as well; lodash declared in the same commit); the exact `4.18.1` pin chosen by the preparing session as a default for review, because a caret range fails with `EOVERRIDE` | `BFQ-176` | #8828 merged first, so `dev` carried the defect from `eb72a1d3` (16:29Z) to #8834's merge `93f152bd` (17:44:48Z), and `dev`'s Docker image published at 17:15Z carries it; merged 2026-10-25 |
| **The runtime-requires gate's allowlist rule**: every literal `require` in `server.js`, `bin/*.js` and `lib/` (except the browser-only `lib/client`, `lib/report` and `lib/report_plugins`) must be under `dependencies`; `webpack`, `webpack-dev-middleware` and `webpack-hot-middleware` are allowed only inside `lib/server/app.js`'s `NODE_ENV === 'development'` block | the preparing session, 2026-10-22, as a conventional default for the maintainer to review; `webpack` added 2026-10-25, because cut 2 makes it a devDependency required at `lib/server/app.js:340` inside that block | `BFQ-176`, `RT-2` (`tools/queue/gates/runtime-requires-declared.js`) | `dev` `2bc298b9` 41 checked, 0 failing; cut 2 `ee94b148` 32 checked, 0 failing; its control refuses `v15.0.9`, `eb72a1d3` and a stray `webpack-hot-middleware` or `webpack` require outside the guard |
| **The lockfile refresh is redone on `dev` for 16.0.0**: session -40's `wip/15.0.10-lockfile-refresh` `dbc4519f` was never pushed; the refresh is `deps/16.0.0-security-refresh` (`compression`, `follow-redirects`, `source-map-js`) | 2026-10-25 | `BFQ-163` | merged as #8835 (`a20469dc`), 2026-10-25 |
| **`sanitize-html` 2.18 goes to `dev` for 16.0.0, integrated as quickly as possible**, bundled into the dependency refresh PR (themed PRs) rather than a PR of its own | maintainer, 2026-10-25 | `BFQ-163` | merged as 2.18.1 in #8835 (`0293d640`, `1eb986ad`); closes GHSA-x3q4, GHSA-cv27, GHSA-jxwj and GHSA-g8qq (GHSA-374f never applied to 2.17.5); its one stored-text change is in contents, For the release notes |
| **Page-bundle budget option A**: `ee94b148` keeps the earlier allowances, app 349000 and total 417000 gzip bytes, over the measurement on `b8ff91cb` (341123 and 412296, against 334513 and 405305 on `62a9476f`; the growth is #8831's modern theme, which every page loads in `bundle.app.js`) | maintainer, 2026-10-25 | `RT-2` | in #8837 |
| **Page-bundle budget option B as a follow-up**: load the modern theme's code only when it is chosen, as a bundle or chunk of its own | maintainer, 2026-10-25, for Andy Low | `RT-BUNDLE-THEME-SPLIT` | not started; owner Andy Low or the maintainer |

---

*Draft, 2026-10-25. Requires maintainer review before it is relied upon.*
