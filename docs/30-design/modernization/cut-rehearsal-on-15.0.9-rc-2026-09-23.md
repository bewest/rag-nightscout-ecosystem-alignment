# Cut rehearsal on the 15.0.9 candidate, 2026-09-23

*Contributor-facing, with operator-facing lines marked **Operators:**. Snapshot,
2026-09-22/23 (US Pacific), on local branches (not pushed) built on `rc/15.0.9-additions-c`
`b9c9828b`. Current: the latest cut rehearsal. The real propagation is redone on `dev`
after 15.0.9 is tagged, and every count here must be re-measured then; item state is in
`queue/work-queue.yaml` (`RT-1`, `RT-2`, `RT-3`, `RT-5`, `RT-REBASE`). Draft for maintainer
review; it makes no recommendation between the two release shapes.*

Base: `rc/15.0.9-additions-c` **`b9c9828b`** (= `origin/dev` `74fc6619` + eight
additions; record: [15.0.9 integration record](../remedial/rc-15.0.9-integration-record.md)),
used by SHA. Published cuts, unmoved at `git ls-remote` before the run:
cut 1 `origin/chore/retire-jsdom` `bce12ecc`, cut 2
`origin/chore/build-runtime-separation` `b6e8c7cd`, cut 3
`origin/chore/compose-mongodb6` `ebb690cf`, cut 4
`origin/chore/mime-exposure-review` `b80aa147`, cut 5
`origin/chore/nightscout-modernization` `b1bdaca0` (PR #8605). Connector pin on
the candidate and on every rehearsal branch: `nightscout-connect` `0.1.0-dev.1`
(= connector `1946beb`).

## 1. Branches

All in the worktree `externals/work/crm-rh-cuts`, created for this rehearsal.
Nothing was pushed; `externals/work/crm-cuts` (rt/*) was read, never checked out
or modified.

| branch | tip | published cut it starts from | ahead of `b9c9828b` | contains `b9c9828b` | ancestor of next | trial-merge into `b9c9828b` |
|---|---|---|---|---|---|---|
| `rh/cut1` | `c77797e0` | `bce12ecc` | 104 | yes | yes | clean |
| `rh/cut2` | `02205d91` | `b6e8c7cd` | 269 | yes | yes | clean |
| `rh/cut3` | `bb4f678b` | `ebb690cf` | 338 | yes | yes | clean |
| `rh/cut4` | `135faa3b` | `b80aa147` | 424 | yes | yes | clean |
| `rh/cut35` | `cd93d8e8` | `b1bdaca0` | 529 | yes | — | clean |

Each trial merge's tree equals the branch tree (`git merge-tree --write-tree
b9c9828b rh/<cut>` = `rh/<cut>^{tree}`). Controls: the published cut 1 conflicts
with `b9c9828b`, and `rh/cut35` is not an ancestor of `rh/cut1`.

**`rh/cut35` contains cut 4.** Cut 5 descends from cut 4 (`git merge-base
--is-ancestor origin/chore/mime-exposure-review origin/chore/nightscout-modernization`
is true), and `b1bdaca0` already lacks `lib/plugins/mmconnect.js` and
`lib/plugins/bridge.js` and carries `lib/server/mmconnect-connect-compat.js`. No
"cuts 3+5 without 4" tree exists; building one means reverting cut 4 inside cut 5,
which was not attempted. Everything said below about cut 4's behaviour holds for
`rh/cut35`.

## 2. Method

Propagation runs up the stack, as for rt/*: `b9c9828b` merged into the published
cut 1; `rh/cut1` merged into the published cut 2; and so on, then `rh/cut4` into
the published cut 5. Every later fix was committed on the lowest cut it belongs
to and merged up again, so the prefix property holds at every tip. All merges are
`--no-ff`. Commits use git's configured identity and carry no trailers.

**Reuse of rt/* resolutions.** No rerere cache exists in the shared clone. For each
conflicting path that rt/* had resolved, the rt resolution was carried forward
with a three-way file merge: `git merge-file <rt tip file> <rt's base-side file>
<rh base-side file>`. This keeps rt's resolution and applies what changed on the
base side since rt was made (rt/* merged `59430336`, 43 commits behind `b9c9828b`).
Where the base side had not changed, rt's file is taken verbatim. After each merge,
the whole tree was compared with rt's: the files that differ are exactly the files
that differ between rt's base side and rh's base side (`git diff --name-only`
comparison, empty set difference at cuts 2, 3 and 4). The lockfile was never
hand-merged: it was taken from one side and regenerated with npm 10.9.8
`install --package-lock-only`, then checked with `npm ls --package-lock-only`.

For add/add conflicts where one side's file is byte-identical to a modernization
commit that the candidate backported, that commit's blob was used as the merge
base (so "ours = base" and the result is the candidate's file). The blob identity
was checked each time (§4.4).

## 3. Per-cut results

Suite: `npm test` (`tests/*.test.js`) under `my.test.env` = `tests/ci.test.env`
with the connection string pointed at an own database (name ends `_test`, dropped
before each run) on own containers `rhcuts-m7` and `rhcuts-m44` (the official `mongo` image at
tag 7, 7.0.43, and tag 4.4, 4.4.24), bound to 127.0.0.1 with `--ulimit nofile=64000:64000`.
Each run is from a `git archive` of the tip, `npm ci` under the Node version used,
with port 1337 checked free first. Harness control: `b9c9828b` on 22.23.2 /
MongoDB 7 gives **2508 / 0 / 3**, the record's figure.

Browser job: `npm run test:browser` with `NIGHTSCOUT_TEST_BROWSER=chromium`
(Chromium 153.0.8010.12, playwright-core 1.63.0).

| branch (tip) | conflicting paths | Node 22.23.2 · Mongo 7 | Node 24.20.0 · Mongo 7 | other | Chromium browser suite | `npm audit --omit=dev` |
|---|---|---|---|---|---|---|
| `rh/cut1` (`c77797e0`) | 8 | 2104 / 0 / 1 | 2104 / 0 / 1 | Mongo 4.4.24: 2104 / 0 / 1; Node 20.20.0: refused at start (§3.1) | 463 / 0 | 15 (3 high, 11 moderate, 1 low) |
| `rh/cut2` (`02205d91`) | 9 | 2369 / 0 / 1 | 2369 / 0 / 1 | | 547 / 2 (hot middleware) | 4 (4 moderate) |
| `rh/cut3` (`bb4f678b`) | 6 | 2412 / 0 / 1 | 2412 / 0 / 1 | | 573 / 2 (hot middleware) | 4 (4 moderate) |
| `rh/cut4` (`135faa3b`) | 11 | 2457 / 0 / 1 | 2457 / 0 / 1 | | 584 / 3 (hot middleware) | 0 |
| `rh/cut35` (`cd93d8e8`) | 6 | 2578 / 0 / 1 | 2578 / 0 / 1 | Mongo 4.4.24: 2578 / 0 / 1 | 594 / 3 (hot middleware) | 0 |

Counts are passing / failing / pending. Audit counts are from each tip's lockfile
(`npm audit --omit=dev --package-lock-only`, npm 10.9.8, advisory data as of
2026-09-22); they equal the published cuts' own counts except cut 1, whose
published lock has 19 (the candidate's `qs` 6.16.0 override and connector pin
remove four). `b9c9828b` itself has 15. Cut 1's three highs are `browserslist`,
`form-data` and `request`; the moderates include `minimed-connect-to-nightscout`
and `share2nightscout-bridge`, which cut 4 deletes.

**Why the node-suite count drops at cut 1.** Cut 1 retires jsdom. Relative to
`b9c9828b`, 27 test files leave the node suite (469 passing titles leave, 65
arrive); their coverage moves to the browser suite, which does not exist on
`b9c9828b`. The published cut 1's own browser suite is 426 / 0 on this machine;
`rh/cut1`'s is 463 / 0.

**Browser-suite controls.** The three development hot-middleware cases ("Actual
page entries with development hot middleware") time out on `rh/cut2` and above
**and on the published cut 5 `b1bdaca0` (594 / 3)** on this machine, with the same
three titles. They exercise `webpack-hot-middleware` in development mode, not the
production page. They are not introduced by the rehearsal merges; whether they
pass on a CI runner was not checked.

### 3.1 Cut 1 — `rh/cut1`

Merge `4140447d` (`b9c9828b` into `bce12ecc`), 8 conflicting paths:

| path | resolution | source |
|---|---|---|
| `lib/plugins/pluginbase.js` | rt's composed resolution | rt `77d6ffaf`, verbatim (base side unchanged since `59430336`) |
| `tests/clock-client.test.js`, `tests/pluginbase.modern.test.js`, `tests/profile-sinks.test.js` | deleted (jsdom); clock concern/falling coverage kept in `tests/browser/clock-client.test.js` | rt `77d6ffaf`, verbatim, including its browser-test port |
| `lib/server/bootevent.js` | rt's resolution plus the candidate's newer boot changes | rt, carried forward, clean |
| `package.json` | `mongomock` stays removed; `nightscout-connect` `0.1.0-dev.1` | rt, carried forward; one residual hunk (the pin) |
| `README.md` | cut 1's Node/MongoDB lines | new conflict (from `docs/mongodb-floor`); cut 1's CI tests MongoDB 5.0 and 6.0 only |
| `package-lock.json` | `b9c9828b`'s lock, regenerated | — |

Then, on `rh/cut1`:

- `54799da6` — rt/cut1's `ed21961f` (engines `^22.12 || >=24`), applied unchanged
  (patch-id identical).
- `5c121e4b` — **semantic conflict with no textual conflict**: four test files that
  dev's backfixes added (2026-09-06 to 09-15) require `tests/fixtures/secure-jsdom`,
  which cut 1 deletes, so mocha cannot load the suite. rt/cut1 carries the same four
  files unported. Ported by taking the stack tip's own ports (Andy Low's dev-merge
  reconciliations `e16302fd`, `e3b22034`, `8ec9f300`): `tests/browser/dev-integration.test.js`,
  `tests/browser/profile-empty-name.test.js`, the DOM half of
  `tests/boluscalc.quickpick.test.js`, and three entries in
  `tests/browser/modules.source.js`. **Deleted**: `tests/profileeditor.defaults.test.js`,
  `tests/profileeditor.empty-name.test.js`,
  `tests/client-core/chart-container-height-race.test.js`. Case mapping: quick-pick
  chooser 6 → 6 browser scenarios; profile loading/save safeguards 6 → 6; unnamed
  profile editor 6 → 6; zero-height chart 3 → 1 browser case asserting all three
  properties.
- `97ae66ed` — **test fixture changed**: `tests/connect-lifecycle.test.js` (cut 1's own)
  emits a stand-in sandbox without `lastEntry`. Connector `1946beb` no longer returns
  early on an empty `sgvs` array (`b77e5bb7` and `234d47c8` did), so it calls
  `sbx.lastEntry` and the test threw `TypeError: sbx.lastEntry is not a function`.
  Nightscout's real sandbox always has it (`lib/sandbox.js`). The stand-in now has a
  minimal `lastEntry`; assertions unchanged. This is the only change the connector
  repin forced.
- `c77797e0` — browser tests: `pill-tooltips.test.js` passes the `translate` argument
  that dev's #8732 pluginbase needs, and `profile-settings.test.js`'s stand-in gains
  `hasData()`, which dev's profile editor calls (both one-line changes from `e3b22034`);
  `profile-empty-name.test.js` loads whichever page bundles the tree builds, because
  `bundle.profile.js` exists only from cut 2. Assertions unchanged.

Node 20: the run exits 1 before mocha reports, with `ERROR: Node v20.20.0 is not
supported. Nightscout requires Node ^22.12 || >=24. ...` from
`lib/server/runtime-policy.js` — the runtime policy's refusal, not a regression.
Boundary on `rh/cut1` (policy executed directly): 18.20.8 and 20.20.0 refused;
22.12.0, 22.22.0, 22.23.2, 24.15.0, 24.20.0 accepted.

MongoDB 4.4: cut 1's CI matrix is `[5.0, 6.0]` and its README says 4.4 is
unsupported and no longer tested; 15.0.9's README says 4.4 is deprecated and
still tested. `rh/cut1` passes the full suite on 4.4.24 (2104 / 0 / 1), so dropping
4.4 at cut 1 is a support-policy change with no measured break.

### 3.2 Cut 2 — `rh/cut2`

Merge `865392f5`, 9 conflicting paths, **all reused from rt/cut2** (`b5bf7d77` =
`50b84041` + `6106332e` + the floor merge), carried forward:
`README.md`, `lib/api/entries/index.js`, `lib/api/profile/index.js`,
`lib/server/aggregate.js`, `lib/server/query.js`, `tests/api.alexa.test.js`,
`tests/mongo-query-javascript.test.js` (clean); `package.json` (two residual
hunks: cut 2's `mongodb-connection-string-url` and `form-data` 2.5.6 override kept,
pin `0.1.0-dev.1`); lock regenerated. `lib/utils/query-leaves.js` and
`tests/query-leaf-contract.test.js` taken from rt/cut2 verbatim (`6106332e`), outside
the conflict list.

The reused resolution did not pass the suite. Fixed on `rh/cut2`:

- `71a7d2da` — **production**: `lib/api/entries/index.js` required `event-stream`,
  which cut 2's `6b7937cb` removed and which is in no lockfile from cut 2 up; `es`
  is unused. rt/cut2's `50b84041` reintroduced the line. The v1 entries module would
  throw at load.
- `1bdb90e4` — 8 failing cases:
  - `tests/api.alexa.test.js`, `tests/mongo-query-javascript.test.js` (taken from the
    tip by rt) called `lib/middleware/configure-request`, which exists only from cut 5.
    Line dropped.
  - `tests/debug-logging.test.js` (the candidate's) stubs the `bootevent` package,
    which cut 2 replaced (`26ddc260`). The tip's two-line adaptation taken.
  - **Expectations changed to 15.0.9's behaviour**: the v1 count refusal for a
    `pipeline` parameter uses dev's wording in `lib/api/entries/index.js` (cut 2's
    `479a6a4d` had "Custom aggregation pipelines are not supported by the count
    endpoint"), and `tests/count-pipeline-boundary.test.js` asserts it; in
    `tests/mongo-query-javascript.http.test.js` an `$expr` filter with literal
    operands, expected to answer 200 as data, answers 400 under dev's v1 operator
    allowlist (#8743), and moves to its own refusal case. Break-it: restoring cut 2's
    wording fails exactly the two message assertions.

### 3.3 Cut 3 — `rh/cut3`

Merge `9bf0df77`, 6 conflicting paths, **all reused from rt/cut3** (`c313f5b1`),
carried forward: `.github/workflows/main.yml`, `lib/api/entries/index.js`,
`lib/server/food.js` (clean); `lib/authorization/storage.js` (the candidate's
auth-hardening and subject-edit changes merge cleanly with driver-7 code; one
residual hunk, a comment line); `package.json` (`mongodb` `^7.6.0`,
`mongodb-connection-string-url` 7.0.2, pin `0.1.0-dev.1`); lock regenerated.

Fixed on `rh/cut3` (`d0654fdb`), 3 failing cases:

- **Production**: `lib/server/food.js` `listquickpicks` had lost `READ_OPTIONS`.
  rt/cut3's resolution kept dev's new quick-pick filter (`73495331`) and dropped cut
  3's batch-size argument; driver 7 sends no default `batchSize` (BF-18's mechanism),
  so that read had no batch bound. The test showed a 2,399-document batch. Restored
  as the tip has it. Break-it: rt's `food.js` fails exactly "quickpicks preserve
  visibility filtering and position order".
- **Expectation changed**: `tests/mongo-read-batches.test.js` asserted that
  `profile.list(undefined, 0)` returns every record. Under 15.0.9 (RT-COUNT0) a zero
  count answers an empty list. Rewritten with an explicit count of 2501, as the
  tip's `e3b22034` did.
- **Test removed**: `tests/browser-utils.queryparms.test.js` stubs a DOM without
  `createElement`, which cut 3's `f72cb021` now calls. Its case is covered in a real
  browser by `tests/browser/dev-integration.test.js`; the tip removes it too.

CI's Node matrix is `['22','24']` on every rh tip, cut 1 included (`ed21961f`
changed cut 1's), so no CI job runs the floor version 22.12 (BF-59's gap, now from
cut 1). From cut 3 the MongoDB matrix is `5.0.32`, `6.0.27` and `7.0.40`, `8.0.29`. Bundled compose
MongoDB moves 5.0.32 → 6.0.27.

### 3.4 Cut 4 — `rh/cut4` (held; rehearsed to size it)

Merge `2aac2404`, 11 conflicting paths:

| path | resolution | source |
|---|---|---|
| `lib/client/boluscalc.js`, `lib/client/receiveddata.js` | clean carry-forward | rt `95bb6295` |
| `lib/server/bootevent.js` | both sides' additions (cut 4's mmconnect compat require, the candidate's world-readable notice) | rt, carried forward, one residual hunk |
| `lib/server/client-ip.js`, `tests/client-ip.test.js`, `docs/proposals/trusted-proxy-migration.md` | candidate's file | add/add; cut 4's copy is byte-identical to `06c83f2f`, used as base |
| `tests/api3.alarm-logging.test.js` | candidate's file | add/add; cut 4's copy is byte-identical to `31c354d8`, used as base |
| `README.md` | candidate's `TRUST_PROXY` wording (compatibility default), both hunks | new |
| `lib/api/status.js` | cut 4's credential line (`973a2849`) | new |
| `package.json` | pin `0.1.0-dev.1`; `forwarded-for` `^1.1.0` **restored by hand** | rt, carried forward |
| `package-lock.json` | cut 4's lock, regenerated | — |

`forwarded-for`: git kept `06c83f2f`'s removal of the dependency because the base
side never touched that line, yet the candidate's `client-ip.js` (kept above)
requires it. Found by scanning every bare `require` in `lib/` against the declared
dependencies. **Test expectation changed**: the candidate's
`tests/api3.alarm-logging.test.js` drops two acknowledgement assertions that cut 4's
copy had; they are covered by the candidate's `tests/api3.alarm-socket.ack.test.js`.

Fixed on `rh/cut4` (`e4794f22`) — **production, from a clean textual merge**: cut
4's `31c354d8` has `resolveFinishForToken (err)`; the candidate's socket-scope fix
(#8745) uses `auth.shiros` inside that callback. Git merged the body into cut 4's
signature, so every access-token alarm subscription threw `ReferenceError: auth is
not defined` (4 failing in the alarm tests; 61 / 61 after restoring the parameter).

### 3.5 Cuts 3+5 — `rh/cut35`

Merge `e896a6f0` (`rh/cut4` into `b1bdaca0`), 6 conflicting paths; no rt resolution
exists at this level. `lib/server/bootevent.js`, cut 5's conflict against dev,
merged cleanly here.

| path | resolution |
|---|---|
| `lib/server/client-ip.js`, `docs/proposals/trusted-proxy-migration.md` | the candidate's (BF-88, §5); cut 5's copies are `395f3207`'s, used as base |
| `tests/client-ip.test.js` | the candidate's, plus cut 5's Express 5 harness line `require('../lib/middleware/configure-request')(app)` in `appFor()`, which the backport had removed for dev |
| `lib/api/entries/index.js` | the candidate's `getDataRef` (dev's cache fix) and comment; both variants are deep-cloned on the next line |
| `package.json` | cut 5's file (no `overrides` block; `qs` direct 6.16.0), plus engines `^22.12 \|\| >=24`, `forwarded-for` `^1.1.0`, pin `0.1.0-dev.1` |
| `package-lock.json` | cut 5's lock, regenerated; one `qs`, 6.16.0 |

Then `437a6741`: merging the cut 2 fix up removed the Express 5 shim line from
`tests/api.alexa.test.js` and `tests/mongo-query-javascript.test.js` here too
(cut 5's side had not changed those lines since the merge base). Restored.
Propagating a fix that removes a later cut's adaptation is silent; each such
case needs checking at the top of the stack.

## 4. Specific checks

### 4.1 Images (BF-58, RT-NODE-FLOOR-TESTED)

Built with each branch's own `Dockerfile` (`docker build --pull`, unchanged
`FROM node:22-alpine`), from a `git archive`. `node:22-alpine` resolved to
`node@sha256:b6f26b36c8ff…` (created 2026-09-17), **Node v22.23.2**. The images
were built from `rh/cut1` `97ae66ed`, `rh/cut4` `e4794f22` and `rh/cut35` `6029ffb5`;
every later commit on those branches touches only `tests/` (`git diff --stat
<built> <tip> -- . ':(exclude)tests/**'` is empty), and the image contains no
`tests/`.

| image | Node inside | runtime policy | no database: `/` | with MongoDB 7: `/api/v1/status.json` |
|---|---|---|---|---|
| `rh/cut1` | v22.23.2 | accepted | 500, "Mandatory setting missing" page (with `INSECURE_USE_HTTP=true`) | 200, `status: ok` |
| `rh/cut4` | v22.23.2 | accepted | plain HTTP 307; forwarded HTTPS 500, setup page | not run |
| `rh/cut35` | v22.23.2 | accepted | plain HTTP 307; forwarded HTTPS 500, setup page | 200, `status: ok` |

All three boot. `saslprep` check (cut 5's CI step) passes in the cut 4 and cut 3+5
images. **BF-58 no longer reproduces against today's tag**: `node:22-alpine` is
22.23.2, which satisfies even the published floor `^22.23.2 || ^24.20.0`
(control: the published cut 1's `runtime-policy.js` and `engines` accept v22.23.2
inside the `rh/cut1` image and refuse local v22.22.0). The published floor still
rejects any host on 22.12–22.23.1 or 24.0–24.19; `^22.12 || >=24` does not.
**Building with `--pull` refreshed the machine's local `node:22-alpine` tag**
(previously a 2026-01-28 image).

### 4.2 Connector pin (RT-CONNECT-PIN-CUTS, BF-65)

Every rh tip pins exactly `0.1.0-dev.1`, as the candidate does.
`tools/queue/gates/connector-pin-exposure.js --refs …` reports the BF-42/BF-65 arm
ok on all five and bad on the published cut 1 (control). Its BF-43 arm reports
"unresolved" on every ref pinned by version, including `b9c9828b`, because it
resolves only commit or tag pins; checked by hand instead: connector `0.1.0-dev.1`
declares `axios ^1.18.1` and installs axios 1.20.0. The repin loses nothing:
`234d47c8` (dev) and `b77e5bb7` (cuts 4–5) are both ancestors of `1946beb`.
**Future change**: when `0.1.0` is tagged the pin moves from `0.1.0-dev.1` to
`0.1.0` on every cut; npm `next` is already `0.1.0-dev.2`. [2026-09-24: `0.1.0` is
released and `dev` pins it exactly (#8762); the cuts still pin `0.1.0-dev.1`.]

### 4.3 Node floor consistency

`NODE_FLOOR_REF=<ref> node tools/queue/gates/node-floor-consistency.js`: 9 checked,
0 failing on each rh tip; 1 failing on `origin/chore/retire-jsdom` (control).

### 4.4 The bf2 backports and the "trivial conflict" rationale

Backfix-2 plan §2.1 says the backports are content-identical cherry-picks so that
the cut rebase stays trivial. Measured per file (changed lines, ignoring line
numbers and context):

| candidate commit | modernization commit | files with identical changed lines | differs | only in the modernization commit |
|---|---|---|---|---|
| `712c8854` | `06c83f2f` | 17 of 17 | — | `docs/plans/nightscout-modernization.md` |
| `708bbd4b` | `395f3207` | 5 of 5 | — | 3 docs files, `.github/workflows/main.yml` |
| `9c50788e` | `31c354d8` | 1 of 2 | `tests/api3.alarm-logging.test.js` (adapted to dev's alarm socket) | — |
| `b5038500` | `d3ac8026` | 3 of 3 | — | `docs/runtime-upgrade.md` |

The resulting blobs of `client-ip.js`, the proxy guide and (at `712c8854`)
`tests/client-ip.test.js` are identical to the modernization commits'. Git still
reports them as add/add conflicts at cut 4 (nothing below cut 4 has the files), and
as content conflicts at cut 5, where the candidate's later commits (`8b975b41`,
`1114228d`, `29e6430e`) edit them. Using the modernization blob as the merge base
made each resolution mechanical. So the claim holds for the files the backports
carry. The later commits on the candidate are a real conflict (BF-88), and so is
the adapted alarm test. The one production defect in this area (`e4794f22`) came
from the textual merge **succeeding**.

### 4.5 Cut 4 boot errors (RT-5, BF-61)

`lib/server/server.js` (the `npm start` entry) was booted from each tree against
MongoDB 7 under each environment shape, with outbound HTTP(S) sent to a dead local
proxy and dummy credentials. Status codes of `GET /`, `/api/v1/status.json` and
`/api/v1/entries.json`:

| settings | `b9c9828b` (15.0.9 candidate) | `rh/cut4` | `rh/cut35` |
|---|---|---|---|
| none of the below (control) | — | 200 / 401 / 401 | — |
| `ENABLE` includes `mmconnect`, `MMCONNECT_*`, no country | 200 / 401 / 401 | **500 / 500 / 500**, page names `CONNECT_COUNTRY_CODE` | **500 / 500 / 500** |
| as above plus `CONNECT_COUNTRY_CODE=US` | not run | **500 / 500 / 500**, same page | not run |
| as above with `connect` also in `ENABLE` | not run | 200 / 401 / 401, "MMCONNECT credentials are served by Nightscout Connect" | not run |
| `bridge` and `mmconnect` in `ENABLE`, `BRIDGE_*` + `MMCONNECT_*` + country | 200 / 401 / 401 | **500 / 500 / 500**, "cannot run alongside" | **500 / 500 / 500** |
| same with `connect` in `ENABLE` | not run | **500 / 500 / 500** | not run |
| `bridge` only, `BRIDGE_*` | not run | 200 / 401 / 401 | not run |

(401 on the API is the probe's unauthenticated request; it shows the API is up.)

**BF-61 is still true on `rh/cut4` and on `rh/cut35`**: leftover `MMCONNECT_*`
without a country, or `BRIDGE_*` together with `MMCONNECT_*`, turn the whole site
into the boot-error page. The page now shows its message (the candidate's BF-63
renderer guard is in both trees). **New**: setting `CONNECT_COUNTRY_CODE`, which the
page tells the operator to do, is not enough unless `connect` is also in `ENABLE`,
because `CONNECT_*` settings are only read for enabled plugins. The messages still
say the bridges were "retired in Nightscout 15.0.9", which is not the release that
will carry them.

## 5. BF-88: the `TRUST_PROXY` unset default

**Conflict.** With `TRUST_PROXY` unset, cut 5 (`395f3207`) resolves the client address
with a fixed-precedence reimplementation of the legacy headers; the 15.0.9 candidate
(`8b975b41`) uses `forwarded-for`, the same call dev makes today. They differ in four
cases: an IPv6 entry after the first in a comma-and-space `X-Forwarded-For` chain; an
IPv4 entry with a non-numeric port; a request with no socket address; and a request
carrying more than one forwarding-header family.

**Side taken: the candidate's (dev's / 15.0.9's)**, per the brief's default, because
15.0.9 ships it to operators first. At cut 4 this came through the add/add resolution,
and at cut 3+5 through a three-way merge with `395f3207` as base. Consequence at cut
3+5: cut 5's own expectations in `tests/client-ip.test.js` for those four cases are
replaced by the candidate's, and `forwarded-for` stays a dependency. Taking cut 5's
side instead would change the client address an upgrader's failed-login delay keys on
in those four cases, with no warning, and would fail 7 of 48 `tests/client-ip.test.js`
cases (register figure). **Decided 2026-09-23 by the maintainer: keep the candidate's
(15.0.9's) side**, as the rehearsal did; RT-3 records it.

**Operators:** with this choice, upgrading from 15.0.9 to any cut does not change how
Nightscout works out a visitor's address when `TRUST_PROXY` is not set.

## 6. Version numbers

Every rh tip's `package.json` carries `"version": "15.0.9"`, as each published cut
does. Each cut is renumbered when it is rebased; none was renumbered here.

| release | carries now | (a) separate releases | (b) one combined release |
|---|---|---|---|
| cut 1 | 15.0.9 | major on the recorded semver facts (enforced Node floor): 16.0.0 | — |
| cut 2 | 15.0.9 | minor (plugin impact unmeasured): 16.1.0 | — |
| cuts 3+5 (carries 4) | 15.0.9 | major (Express 5, Helmet 8, driver 7; and cut 4's removals): 17.0.0 | — |
| 1+2+3+4+5 | 15.0.9 | — | 16.0.0 |

The (a) numbers follow from the recorded semver classes applied in order; if the
maintainer judges cut 1 minor they shift to 15.1.0 / 15.2.0 / 16.0.0. Not decided here.

## 7. The two release shapes, measured

Production diff excludes `tests/`, `docs/`, `*.md`, `.github/`, `tools/` and
`package-lock.json`.

| | (a) separate: cut 1 | (a) separate: cut 2 | (a) separate: cuts 3+5 | (b) combined 1+2+3+5 |
|---|---|---|---|---|
| diff base → tip | `b9c9828b` → `rh/cut1` | `rh/cut1` → `rh/cut2` | `rh/cut2` → `rh/cut35` | `b9c9828b` → `rh/cut35` |
| production files | 15, +78 / −64 | 65, +954 / −559 | 99, +962 / −757 | 144, +1953 / −1339 |
| of which `lib/` | 9, +63 / −47 | 46, +653 / −304 | 84, +760 / −597 | 112, +1458 / −930 |
| commits | 104 | 165 | 260 | 529 |
| contains cut 4 (MiniMed/Dexcom legacy removal, BF-61) | no | no | **yes** | **yes** |
| node suite, 22.23.2 and 24.20.0, MongoDB 7 | 2104 / 0 / 1 | 2369 / 0 / 1 | 2578 / 0 / 1 | 2578 / 0 / 1 |
| browser suite, Chromium | 463 / 0 | 547 / 2 (hot middleware) | 594 / 3 (hot middleware) | 594 / 3 (hot middleware) |
| image boots (`node:22-alpine` = 22.23.2) | yes | not built | yes | yes |
| `npm audit --omit=dev` | 15 | 4 | 0 | 0 |
| rehearsal fixes needed beyond conflict resolution | 3 test-side, 1 port | 1 production, 1 test-side | cut 3: 1 production, 2 test; cut 4: 1 production; cut 5: 1 test | all of these |

Cut 3's and cut 4's own rows, for reference: cut 3 26 files +314/−65; cut 4 65 files
+318/−536; cut 5 alone 27 files +332/−158.

**What an operator would need to know, per shape** (**Operators:**, plain language):

- **Node.** From cut 1, Nightscout will not start on Node older than 22.12, and not on
  Node 20 at all. It prints a message naming the Node versions it needs. Node 22.12 or
  newer, or Node 24 or newer, works. The Docker image already uses a Node that works.
  Under (a) this appears in the first release; under (b) in the single one.
- **MongoDB.** From cut 1, MongoDB 4.4 is no longer tested. In this rehearsal Nightscout
  still passed its full tests on MongoDB 4.4 at cut 1 and at cuts 3+5
  (2578 / 0 / 1). 15.0.9 calls 4.4 deprecated, and dropping it in the release right
  after is consistent with that only if 15.0.9 has shipped first. From cut 3 the
  bundled Docker Compose setup starts MongoDB 6.0 instead of 5.0.
- **Reverse proxies (`TRUST_PROXY`).** No change from 15.0.9 (§5), in either shape.
- **Third-party plugins that run in the page.** Cut 2 changes how the page's code is
  packaged and started. Test any such plugin before upgrading. Nobody has measured
  this against real plugins.
- **CGM data through the old built-in MiniMed CareLink or Dexcom Share settings.** The
  cuts 3+5 release (a) and the combined release (b) both remove these, because cut 5
  contains cut 4. If `MMCONNECT_*` settings are still present, the whole Nightscout
  site shows an error page instead of your data, unless you set `CONNECT_COUNTRY_CODE`
  **and** add `connect` to `ENABLE`. If you use both the Dexcom and MiniMed settings
  together, the site shows the error page whatever you set. You may not see glucose
  readings in Nightscout until this is fixed, so make sure you have another way to
  check your glucose before upgrading, and talk to your care team about what you rely
  on Nightscout for. This is not medical advice.

## 8. Blockers found

1. **Cuts 3+5 cannot ship without cut 4** as the branches stand (§1). Cut 4 is held,
   and BF-61 is live on `rh/cut35` (§4.5). Either cut 4's hold ends, or cut 4's
   removals are separated out of cut 5, which is unmeasured work.
2. BF-61 and the `ENABLE` gap in its remedy (§4.5), wherever cut 4's code ships.
3. BF-88: decided 2026-09-23, the cuts keep 15.0.9's behaviour (§5), as the rehearsal did.
4. The rt/* propagation is not a usable base as it stands: its reused resolutions
   carried two production defects (`event-stream` at cut 2, the quick-pick batch
   bound at cut 3), four jsdom test files it could not load at cut 1, and cut-5-only
   test harness at cut 2. rh/* fixes them; the real propagation should start from rh/*
   resolutions or re-derive them, and re-run the full suite at each cut.

## 9. Not measured

- Firefox and WebKit browser suites (the pinned revisions are not installed here, and
  installing their system dependencies needs root); CI's matrix runs all three.
- The hot-middleware browser cases on a CI runner.
- Node 22.12.0 and 24.15.0 full suites (only the runtime-policy boundary was run on them).
- MongoDB 5.0, 6.0 and 8.0 suites; the CI matrix covers them.
- Any third-party plugin against cut 2.
- A contract test of the route surface across Express 4 → 5.
- The `rh/cut2` and `rh/cut3` images; the `rh/cut4` image with a database.
- A "cuts 3+5 without 4" tree.
- CI itself: nothing was pushed, so no workflow ran.
- Whether the connector reaches Dexcom or CareLink (outbound traffic was blocked).

## 10. Reproduce

```sh
R=externals/cgm-remote-monitor-official
git -C $R merge-base --is-ancestor b9c9828b rh/cut1            # and each rh/*
git -C $R merge-tree --write-tree b9c9828b rh/cut35             # clean; equals rh/cut35^{tree}
git -C $R show --remerge-diff --stat 77d6ffaf                    # rt/cut1's resolution footprint
git -C $R diff --shortstat b9c9828b rh/cut35 -- . ':(exclude)tests/**' ':(exclude)docs/**' \
  ':(exclude)*.md' ':(exclude).github/**' ':(exclude)package-lock.json' ':(exclude)tools/**'
NODE_FLOOR_REF=rh/cut1 node tools/queue/gates/node-floor-consistency.js
node tools/queue/gates/connector-pin-exposure.js --refs origin/chore/retire-jsdom,rh/cut1,rh/cut35,b9c9828b
# suites: git archive <tip> | tar -x; n exec <ver> npm ci; n exec <ver> npm test   (my.test.env -> own *_test DB)
# browser: NIGHTSCOUT_TEST_BROWSER=chromium n exec <ver> npm run test:browser
# image: docker build --pull -t <tag> . ; docker run --rm <tag> node --version
```
