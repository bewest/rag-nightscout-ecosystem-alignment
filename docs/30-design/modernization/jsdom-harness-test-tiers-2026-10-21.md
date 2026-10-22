# The jsdom test harness after cut 1: test tiers and per-file disposition, 2026-10-21

*Contributor-facing. Snapshot, 2026-10-21, on `official/dev` `04d435eb` (the 15.0.10 cycle
start; its tests are identical to v15.0.9's `4bca2ac2`), published cut 1
`chore/retire-jsdom` `bce12ecc`, the cut 5 tip `chore/nightscout-modernization` `b1bdaca0`,
the local rehearsal branch `rh/cut1` `c77797e0` (see the
[cut rehearsal](cut-rehearsal-on-15.0.9-rc-2026-09-23.md)) and the cut 1 work branch
`wip/cut1-onto-15.0.10` `8c117dd4`; the last two are not pushed. Read-derived: every row comes
from file contents and `git log`; no suite was run for this note. Item state lives in
`queue/work-queue.yaml` (`RT-1`, `RT-REBASE`, `RT-JSDOM-REST`); defect facts live in the
[backfix register](../remedial/nightscout-backfix-register.md). Re-measure every row when
`RT-JSDOM-REST` starts.*

## 1. What is decided and what is open

**Decided for cut 1** (maintainer, 2026-10-21, recorded in `RT-REBASE`'s notes as option C):
cut 1 ports the D3 (BF-103), clock-client and pill-title coverage to `tests/browser/`, keeps
the jsdom harness for the rest of `dev`'s tests, and a later cut retires the harness
(`RT-JSDOM-REST`, which cut is not decided). `wip/cut1-onto-15.0.10` carries those three
ports (`fcd90f26`, `65248bed`, `853b4145`) and still has jsdom `^26.1.0` and every harness
fixture.

**Decided for `RT-JSDOM-REST`** (maintainer, 2026-10-21): scope B.

| scope | what `RT-JSDOM-REST` removes | jsdom afterwards |
|---|---|---|
| A. Full removal | `benv`/`headless` and `secure-jsdom`; every remaining DOM test becomes a browser test or a DOM-free test | removed |
| **B. Three tiers** (decided) | `benv`/`headless` only; `secure-jsdom` stays for DOM tests with no layout dependency | kept, upgraded to 29.x |

**Why B.** Section 4 shows that A and B differ on four test files today, because
cut 1, the rehearsals and the cut 1 work branch have ported most of the suite. The
difference is in what happens next. Between 2026-09-05 and 2026-10-07 `dev` added 11 jsdom
test files (9 of them on `secure-jsdom`) and changed 4 more and the `d3-chart` fixture
(section 4.1). None of the added files loads on published cut 1, which deletes the fixtures
they require; the rehearsal found four of them as a semantic conflict with no textual conflict
and ported them by hand (`rh/cut1` `5c121e4b`). Under A, every jsdom test a backfix adds to
`dev` needs the same port before the harness can go. Under B, a test written for
`secure-jsdom` stays as it is. B also keeps `npm test` runnable without downloading a
browser.

`dev`'s own `docs/proposals/testing-modernization-proposal.md` (Track 1, "Locked-Down jsdom
Harness", and Track 2, "Logic/DOM Separation") describes tiers 1 and 2. Cut 1 adds tier 3.

Upgrading jsdom in place, keeping `benv`/`headless`, is not one of the scopes: the
whole-bundle harness loads `node_modules/.cache/_ns_cache/public/js/bundle.app.js` (the
stale-bundle trap behind BF-173), and an upgrade changes nothing about stubbed geometry. The
upgrade to 29.x is independent of the scope and can happen in cut 1 or before it (section 2).

## 2. Facts this rests on

| fact | value | anchor |
|---|---|---|
| jsdom on `dev` | `^26.1.0`, locked at 26.1.0 | `package.json`, `package-lock.json` at `04d435eb` |
| Node floor on `dev` | `>=20.x` | `package.json` `engines` at `04d435eb` |
| Node floor decided for cut 1 | `^22.12 \|\| >=24` | decided 2026-09-21; `rt/cut1` `ed21961f` |
| jsdom 29.1.1 engines | `^20.19.0 \|\| ^22.13.0 \|\| >=24.0.0` | `npm view jsdom@29 engines`, 2026-10-21 |
| jsdom 30.1.3 engines (latest) | `^22.22.2 \|\| ^24.15.0 \|\| >=26.0.0` | `npm view jsdom engines`, 2026-10-21 |
| test files on `dev` that use a jsdom harness | 31 (two of them the harness's own tests under `tests/fixtures/`), plus 7 fixture modules; 4 more mention jsdom only in comments | section 4 |
| browser test files | 15 on cut 1; 36 on the cut 5 tip | `git ls-tree` of `tests/browser` |
| browser driver | `playwright-core` 1.63.0, run in CI by `npm run test:browser` | cut 1 `package.json`, `.github/workflows/main.yml` |

jsdom 29 fits both `dev`'s floor (from Node 20.19) and cut 1's decided floor (from Node
22.13). jsdom 30 does not fit cut 1's decided floor: Node 22.12 to 22.22.1 and 24.0 to 24.14
are inside the floor but outside jsdom 30's range. jsdom is a development dependency only, so
no operator install is affected either way; a contributor on one of those Node versions would
get an engines warning, and possibly a failing suite.

`RT-REBASE` and `RT-JSDOM-REST` count 14 files and about 109 cases on `04d435eb`; this note
counts per file across all of `tests/` (section 4), including files that already have a port.

## 3. The tiers

| tier | runs in | belongs here | never here |
|---|---|---|---|
| **T1 DOM-free** | plain mocha (`npm run test:core`, `npm test`) | selection, filtering, unit conversion, duration cutting, URL building: logic moved into `lib/client-core/` or another module with no DOM | anything that reads the DOM |
| **T2 `secure-jsdom`** (scope B only) | plain mocha | DOM structure, form handling, event wiring, text a renderer writes, SVG attributes computed by d3 scales | layout, `getBoundingClientRect`, CSS computed values (`touch-action`), real d3 transitions or timers, a real socket transport, sanitizer and XSS behaviour |
| **T3 browser** | `npm run test:browser` (Playwright) | everything in T2's "never here" column, and whole-page behaviour | logic that T1 can test |

Sanitizer and XSS tests are T3 because a jsdom test checks DOMPurify against jsdom's HTML
parser, not the browser's; mutation-XSS results depend on the parser. Cut 1 already moved
`sanitizer-differential` and the DOMPurify reference tests to the browser.

Rules for T2, so that it stays honest:

1. **Modules, not the bundle.** A T2 test `require`s the `lib/` modules it exercises. Nothing
   in T2 loads the built bundle; `tests/fixtures/headless.js`, `benv-loader.js` and
   `benv-shim.js` are deleted.
2. **No geometry stubs.** A test that needs `getBoundingClientRect`, an explicit chart extent
   or a computed style to pass is T3. `tests/fixtures/d3-chart.js` sets the chart extent by
   hand ("jsdom has no SVG animated width/height"), which is why every test that uses it is
   T3 in section 4.
3. **Network blocked.** `createSecureDOM` blocks resource loads, `fetch` and
   `XMLHttpRequest.send`; tests inject their own stubs. `tests/fixtures/secure-jsdom.test.js`
   and `tests/dependency-jsdom.test.js` stay as the harness's own checks.
4. **T1 first.** Where a T2 test is really checking a calculation, the calculation moves to
   T1 and T2 keeps one rendering check. `tests/profileeditor.records.test.js` (pure modules in
   `lib/client-core/profile-editor/`) is the model.

## 4. Per-file disposition

Column key: **it()** is the number of `it(` call sites in the file (loops expand at run
time). **Harness** is what the file uses on `dev`: `secure` = `fixtures/secure-jsdom`,
`globals` = `fixtures/dom-globals`, `benv` = the `benv` shim, `headless` = the whole-bundle
harness, `raw` = `new JSDOM` directly, `d3-chart` = the stubbed chart fixture. **Port**
names an existing browser or DOM-free port. The last two columns give the disposition under
scopes B and A.

### 4.1 Added or changed on `dev` after cut 1 forked (`9205ea30`, 2026-09-05)

Published cut 1 handles none of these. Ports marked *rh/cut1* were made on the rehearsal
branch (from the cut 5 tip's dev-merge reconciliations `e16302fd`, `e3b22034`, `8ec9f300`);
ports marked *wip* are on `wip/cut1-onto-15.0.10`. Neither branch is pushed.

| file | it() | harness | `dev` change | port | B (tiers) | A (full removal) |
|---|---|---|---|---|---|---|
| `tests/boluscalc.quickpick.test.js` | 11 | secure | added `73495331` 2026-09-15 (BF-35) | rh/cut1 and cut 5: `lib/food/quickpick` cases stay DOM-free, chooser cases become 6 browser scenarios | T1 + T3, take the port | T1 + T3, take the port |
| `tests/boluscalc.quickpick-rebuild.test.js` | 8 | secure | added `83cfff14` 2026-09-22 | none | **T2, unchanged** | T3, extend the quick-pick browser scenarios |
| `tests/client-core/chart-container-height-race.test.js` | 3 | secure, globals, d3-chart | added `0a65fd70` 2026-09-11 | rh/cut1: one browser case asserting all three properties | T3, take the port | T3, take the port |
| `tests/client.alarm-no-reading.test.js` | 4 | headless, benv | added `92544d8f` 2026-09-22 | none | T3: needs the page's alarm handlers, which only the bundle wires | T3 |
| `tests/client.renderer.tooltip-units.test.js` | 14 | secure, globals | added `affbc8fd` 2026-10-02 (BF-124) | none; cut 1's `stored-outputs` has one tooltip-glucose case | **T2, unchanged**; the units choice is a T1 candidate | T3, into `tests/browser/stored-outputs.test.js` |
| `tests/clock-token-link.test.js` | 11 | benv, secure, globals, raw | added `9238fd32` 2026-10-02 (#7377) | none | **T2 on `secure-jsdom` alone** (drop `benv`); the four link-building cases are T1 candidates | T3, into `tests/browser/clock-client.test.js` |
| `tests/food-editor-touch-scroll.test.js` | 4 | secure, globals | added `63e93f3e` 2026-10-01 (#8192) | none | T3: the test resolves `touch-action` from the stylesheet by hand because jsdom does not compute it | T3 |
| `tests/profileeditor.defaults.test.js` | 6 | secure, globals | added `af86787d` 2026-09-13 | rh/cut1: `tests/browser/dev-integration.test.js`, 6 → 6 | T3, take the port | T3, take the port |
| `tests/profileeditor.empty-name.test.js` | 6 | secure, globals | added `e46fdd2a` 2026-09-06 | rh/cut1: `tests/browser/profile-empty-name.test.js`, 6 → 6 | T3, take the port | T3, take the port |
| `tests/report-daytoday-durations.test.js` | 3 | secure, globals | added `bbc6e75e` 2026-09-30 (BF-149) | none | **T2, unchanged**: band positions come from d3 scales, not layout | T3, into `tests/browser/legacy-reports.test.js` |
| `tests/clock-client.test.js` | 16 | benv | changed `06372e1d` 2026-09-06, `48ba1856` 2026-09-25 (BF-55) | wip `65248bed`: both groups in `tests/browser/clock-client.test.js`; the jsdom file is deleted | T3, done in cut 1 | T3, done in cut 1 |
| `tests/dependency-d3.test.js` | 11 | secure, globals, d3-chart | changed `8d797ba4` 2026-09-23 (BF-103), `b919af9f` 2026-10-07 | wip `fcd90f26`: both cases in `tests/browser/chart-interactions.test.js`; the file returns to cut 1's two DOM-free cases | T1 + T3, done in cut 1 | T1 + T3, done in cut 1 |
| `tests/fixtures/d3-chart.js` | — | fixture | changed `b919af9f` 2026-10-07 | kept on wip for `chart-container-height-race` | delete once `chart-container-height-race` takes its port | delete |
| `tests/pluginbase.modern.test.js` | 6 | benv, secure, globals | changed `a2a519cd` 2026-09-13, `8cc30a55` 2026-09-21 | wip `853b4145`: the 4 pill-title cases in `tests/browser/pill-tooltips.test.js`; the jsdom file is deleted | T3, done in cut 1 | T3, done in cut 1 |
| `tests/profile-sinks.test.js` | 6 | secure, globals | changed `4dd5b668` 2026-09-21 (one stand-in line, `hasData`) | cut 1 `tests/browser/profile-settings.test.js`; wip `25dcfa7f` carries the `hasData` line; the jsdom file is still on wip | T3, take the port | T3, take the port |

### 4.2 Unchanged on `dev` since cut 1 forked, ported by cut 1

Same disposition under A and B: take cut 1's port. Each needs only a parity check against
`dev`'s file.

| file | it() | harness | cut 1 port |
|---|---|---|---|
| `tests/admintools.modern.test.js` | 7 | benv, secure, globals | `tests/browser/admin-actions.test.js` |
| `tests/browser-settings.test.js` | 1 | secure, globals | `tests/browser/profile-settings.test.js` (bolus render-over ordering) |
| `tests/bundle.smoke.test.js` | 5 | raw | `tests/browser/bundle.test.js` |
| `tests/careportal.test.js` | 9 | headless, benv | `tests/browser/careportal.test.js` |
| `tests/daterangedelete.test.js` | 3 | benv | `tests/browser/admin-actions.test.js`, `daterangedelete` block |
| `tests/dependency-dompurify.test.js` | 4 | raw | `tests/browser/dompurify.test.js` |
| `tests/dependency-socket-parser.test.js` | 9 | raw | kept by cut 1 without its jsdom block; `tests/browser/socket-client.test.js` |
| `tests/hashauth.modern.test.js` | 8 | benv, secure | `tests/browser/hashauth.test.js` |
| `tests/report-reconnect.test.js` | 2 | secure, globals | `tests/browser/report-sgv-pipeline.test.js`, reconnect block |
| `tests/report-sgv-pipeline.test.js` | 3 | secure, globals | `tests/browser/report-sgv-pipeline.test.js` |
| `tests/reports.test.js` | 0 | headless, benv | `tests/browser/legacy-reports.test.js` |
| `tests/sanitizer-differential.test.js` | 4 | raw | `tests/browser/sanitizer-differential.test.js` |
| `tests/security.test.js` | 18 | raw (one block) | kept by cut 1 without its jsdom block; the inert-parser payloads are in `tests/browser/dompurify.test.js` and `sanitizer-differential.test.js` |
| `tests/stored-output-sinks.test.js` | 8 | secure, globals | `tests/browser/stored-outputs.test.js` |

`tests/client.test.js.temporary_removed` also loads the harness; mocha does not run it, and
cut 1 deletes it.

### 4.3 Harness files

Cut 1 keeps all of these (decided); the columns are what `RT-JSDOM-REST` does.

| file | B (tiers) | A (full removal) |
|---|---|---|
| `tests/fixtures/headless.js` | delete | delete |
| `tests/fixtures/benv-loader.js`, `benv-shim.js`, `benv-shim.fixture-module.js`, `benv-shim.test.js` | delete | delete |
| `tests/fixtures/secure-jsdom.js`, `secure-jsdom.test.js` | **keep** | delete |
| `tests/fixtures/dom-globals.js` | **keep** | delete |
| `tests/dependency-jsdom.test.js` | **keep**, updated for jsdom 29 | delete |
| `jsdom` in `devDependencies` | **keep**, `^29.1.1` | remove |

### 4.4 Matched by name only, already DOM-free

`tests/client-core/captured-fixtures.lint.test.js`,
`tests/client-core/careportal-validate.test.js`, `tests/profileeditor.records.test.js` and
`tests/browser-utils.queryparms.test.js` mention jsdom only in comments ("no jsdom", or "a
stub rather than jsdom"). They are T1 already and need nothing.

## 5. Work each scope leaves for `RT-JSDOM-REST`

Counted after cut 1 as decided: the `clock-client`, `dependency-d3` and `pluginbase.modern`
ports are done on `wip/cut1-onto-15.0.10`.

| work | B (tiers) | A (full removal) |
|---|---|---|
| take an existing port (sections 4.1 and 4.2) | 19 files | 19 files |
| write a new browser port | 2 files (`client.alarm-no-reading`, `food-editor-touch-scroll`) | 6 files (those 2, plus `boluscalc.quickpick-rebuild`, `client.renderer.tooltip-units`, `clock-token-link`, `report-daytoday-durations`) |
| move off `benv` onto `secure-jsdom` | 1 file (`clock-token-link`) | 0 |
| carry unchanged on `secure-jsdom` | 3 files | 0 |
| port each jsdom test a backfix adds to `dev` from now on | only if it is T3 by section 3 | every one |

The four extra browser ports under A replace 36 `it(` call sites that pass on `dev` today.

Each port is checked the way the rehearsal's were: break the fix on the branch, confirm the
ported test fails, restore. Under B, the T1 candidates named in section 4.1 (the BF-124
units choice and the four #7377 link-building cases) can move to `lib/client-core/` at any
time; nothing in `RT-JSDOM-REST` depends on it.

## 6. Run time

Measured 2026-10-21 on `wip/cut1-onto-15.0.10` `8c117dd4` in a scratch worktree (Node
24.15.0, Chromium 153.0.8010.12, 16 cores, load average below 2), `playwright-core` 1.63.0:

| run | cases | wall time | anchor |
|---|---|---|---|
| the four files B keeps on `secure-jsdom` or moves onto it (`boluscalc.quickpick-rebuild`, `client.renderer.tooltip-units`, `clock-token-link`, `report-daytoday-durations`), one mocha process | 36 | 1.93-2.09 s over 3 runs, of which about 1 s is mocha start-up | `npx mocha --exit <files>` |
| the same four, one file per process | 8 / 14 / 11 / 3 | 0.63 / 0.82 / 1.62 / 0.72 s | as above |
| the browser suite, Chromium | 444 | 85.4-87.7 s over 3 clean runs | `npm run test:browser` |

In the browser suite, comparable DOM tests (`stored-outputs`, `profile-settings`,
`pill-tooltips`, `hashauth`) take about 0.2 s per case. At that rate, the 36 cases scope A
would have moved to the browser add an estimated 7 s per browser run, against about 1 s of
in-process jsdom time; this is an estimate from per-case averages, not a measured port. CI
runs the browser suite in 6 cells (Chromium, Firefox and WebKit on Node 22 and 24). The
largest single cost is `tests/browser/clock-client.test.js`: 17 cases, 31 s, of which the four
stale-data cases from `48ba1856` take 29 s (three at about 8 s, one at 4 s; each runs 15 to 30
simulated minutes under `page.clock.runFor`).

One further run, the first of four, reported 408 passing and 6 failing; its failures were not
captured (dot reporter), and the three runs after it passed all 444.
