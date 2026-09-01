# Report #1 — Stored XSS via WebSocket Write Purification Bypass

**Date evaluated:** 2026-09-01
**Source materials:** `/home/bewest/Downloads/potential-crm-xss-treatments-01`,
`Screen Recording 2026-09-01 at 10.13.37 pm.mov` (reference only, not
reproduced here)
**Branch:** `wip/bewest/security-hotfix-eval-stored-xss`
**Worktree:** `/home/bewest/src/worktrees/nightscout/cgm-dev-node22`
**Base:** `dev@4982e954`
**Status:** ✅ Fixed, tested, committed (2 commits, working tree clean)

## Claims evaluated

| Claim | Verified? |
|---|---|
| WebSocket `dbAdd`/`dbUpdate` handlers write to Mongo without calling `ctx.purifier.purifyObject()`, unlike the REST `POST` path | ✅ Confirmed in `lib/server/websocket.js` |
| `lib/client/renderer.js` inserts several treatment/food/profile fields into the DOM via jQuery `.html()` without escaping | ✅ Confirmed |
| Asymmetry exists: some REST write paths purify, others (`PUT /treatments/`, `PUT /profile/`, all of `food`/`activity` API) do not | ✅ Confirmed — broader than the original report scope |

## Root-cause fix (commit `a6835ca3`)

- Added `ctx.purifier.purifyObject(data.data)` in `processSingleDbAdd()` and
  the `dbUpdate` handler in `lib/server/websocket.js`.
- Added purification to `PUT /treatments/`, `PUT /profile/`, and both
  `POST`/`PUT` in `lib/api/food/index.js` and `lib/api/activity/index.js`
  (previously had **zero** purification).
- New regression test: `tests/websocket.xss-purification.test.js` (proven to
  fail pre-fix, passes post-fix).

## Defense-in-depth fix (commit `da548d2a`)

- `.html()` → `.text()` conversions and explicit escaping of free-text fields
  across `lib/client/renderer.js`, `lib/report_plugins/daytoday.js`,
  `lib/report_plugins/treatments.js`, `lib/client/boluscalc.js`.
- Escaping implementation: `utils.escapeHtml = require('lodash/escape')` in
  `lib/utils.js` (tree-shaken submodule import, not whole-package
  `require('lodash')`), per `docs/meta/modernization-roadmap.md` §3.1.1
  lodash tree-shaking guidance. Chosen over a custom regex escaper (initial
  implementation, later replaced) and over a DOM/jQuery
  `$('<div/>').text(str).html()` trick — the latter is technically usable
  for the 4 browser-bundle-only call sites but offers no security advantage
  over `lodash/escape` and would require a second escaping implementation
  split out of the otherwise-isomorphic `lib/utils.js`.
- Escaping the 5 markup-significant characters (`& < > " '`) is sufficient
  for XSS prevention (matches PHP `htmlspecialchars()`); full named-entity
  encoding (PHP `htmlentities()`, package `he`) is a display/charset concern,
  not a security requirement, and was not adopted.

## Test/perf outcome

- Full suite: 1360 passing, 3 pending (pre-existing), 0 failing.
- No performance regression from the escaping-library swap (~33ms avg/test,
  ~54s wall time, consistent before/after).
- `npm run bundle-dev` verified clean.

## Prior art referenced

`lib/server/purifier.js` was previously `dompurify` + `jsdom`; replaced with
pure-JS `sanitize-html` (PR #8517) specifically to eliminate jsdom's CVE
surface. This is the direct precedent against reintroducing any DOM-based
approach for HTML escaping in shared server/isomorphic modules.
