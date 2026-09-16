# GT2: re-measuring the five modernization cuts against today's `dev`

Date: 2026-09-15. Audience: contributors and the maintainer. Status: measurement report.
Companion to and **partial correction of**
[cgm-remote-monitor release readiness](../30-design/cgm-remote-monitor-release-readiness-2026-09-14.md) §2 and §5.

## Measurement basis

All figures below are from `externals/cgm-remote-monitor-official`, a clone of
`nightscout/cgm-remote-monitor`, **last fetched 2026-09-14 18:56** (`.git/FETCH_HEAD` mtime).
No fetch was performed for this report and nothing was pushed, rebased or modified on any branch.

| Ref | SHA | Committed |
|---|---|---|
| `origin/dev` | `a8888f0d` | 2026-09-09 18:27 |
| `origin/master` (= 15.0.8) | `92d08342` | 2026-09-04 19:12 |
| `origin/chore/retire-jsdom` | `bce12ecc` | 2026-09-05 22:26 |
| `origin/chore/build-runtime-separation` | `b6e8c7cd` | 2026-09-06 14:31 |
| `origin/chore/compose-mongodb6` | `ebb690cf` | 2026-09-06 16:20 |
| `origin/chore/mime-exposure-review` | `b80aa147` | 2026-09-06 20:23 |
| `origin/chore/nightscout-modernization` | `0a4109f6` | 2026-09-09 19:12 |

Because the cut branch tips are all dated 2026-09-05/06 and `dev`'s tip is dated 2026-09-09,
**every finding below was already true on 2026-09-14** when release-readiness was written.
This is not drift that happened since; it is a measurement error in the original document.

---

## 1. The load-bearing premise is false, and was false when it was written

Release-readiness §5 states, of the four cut points:

> "The four cuts below are existing branch tips, so **each costs zero rebase work today**."

and TL;DR item 5:

> "The stack is currently **0 commits behind `dev`**."

**The second sentence is true only of the stack tip. The first sentence is false for all four
cut points.** Measured with `git rev-list --left-right --count <cut>...origin/dev`:

| Cut | Branch | Ahead of `dev` | **Behind `dev`** | Merge-base with `dev` |
|---|---|---:|---:|---|
| 1 | `chore/retire-jsdom` | 99 | **59** | `9205ea30` (2026-09-05) |
| 2 | `chore/build-runtime-separation` | 258 | **59** | `9205ea30` |
| 3 | `chore/compose-mongodb6` | 321 | **59** | `9205ea30` |
| 4 | `chore/mime-exposure-review` | 400 | **59** | `9205ea30` |
| 5 | `chore/nightscout-modernization` | 495 | **0** | `a8888f0d` = `dev` tip |

The reason is a single commit. `0a4109f6` — *"Merge dev into modernization and preserve connector
fixes"* — is the **tip** of `chore/nightscout-modernization` and the only commit in the stack that
contains `origin/dev`:

```
git log --oneline --reverse --ancestry-path origin/dev..origin/chore/nightscout-modernization | head -1
# 0a4109f6 Merge dev into modernization and preserve connector fixes
```

The stack's "in sync with `dev`" status is **one commit deep**. Cut anywhere below that commit and
you are cutting at a point that predates 59 commits of `dev`.

### What the 59 commits are

Mostly translations, but not only:

| Commit | Subject | Ships in 15.0.9 |
|---|---|---|
| `c2ac743c` | Default routine server and connector logs to quiet mode | yes (PR #8726) |
| `e46fdd2a` | fix: preserve unnamed profiles across loading and editing | yes |
| `8f86cee0` | fix: preprocess embedded profile switch schedules | yes |
| `06372e1d` | fix: show concern for low and falling clock readings | yes |
| `02161b93` | fix: handle treatments query failures without crashing | yes |
| 54 others | i18n: contributed Lithuanian/German/Slovenian/Russian work + Crowdin syncs | yes |

Aggregate `9205ea30..origin/dev`: **63 files, +2,011/−95**.

**Consequence for the adopted train.** The train ships cuts 1 and 2 as separate releases *after*
15.0.9. Each of those releases must first absorb these 59 commits, including four user-visible bug
fixes and a large body of volunteer translation work. That absorption is not free and is not
currently budgeted anywhere in the plan.

---

## 2. Merge cost, measured

`git merge-tree --write-tree --name-only origin/dev origin/<cut>`. No rebase was performed.

| Cut | Result | Conflicting files |
|---|---|---|
| 1 `chore/retire-jsdom` | **CONFLICT** | `lib/server/bootevent.js`, `package.json`, `package-lock.json`, `tests/clock-client.test.js` (modify/delete) |
| 2 `chore/build-runtime-separation` | **CONFLICT** | above + `README.md` |
| 3 `chore/compose-mongodb6` | **CONFLICT** | same five as cut 2 |
| 4 `chore/mime-exposure-review` | **CONFLICT** | same five as cut 2 |
| 5 `chore/nightscout-modernization` | **CLEAN** (tree `048bb28e`) | — |

Four of the five conflicts are mechanical:

- `package.json` / `package-lock.json` — adjacent dependency edits.
- `README.md` — adjacent prose.
- `lib/server/bootevent.js` — `dev` gated three `console.info` tick/data-load lines behind
  `env.debug.logging` and dropped an unused `ctx` parameter from `migrateBridgeToConnect`; the cuts
  replaced the `checkNodeVersion` body with `require('./runtime-policy')()` and reordered the
  `bootevent` acquire chain. Different intents, overlapping region. Small.

**The fifth is not mechanical, and it is the finding that matters.**

### `tests/clock-client.test.js`: a shipped fix loses its only test

```
CONFLICT (modify/delete): tests/clock-client.test.js deleted in origin/chore/retire-jsdom
and modified in origin/dev.
```

- `dev` commit `06372e1d` *"fix: show concern for low and falling clock readings"* changes
  `lib/client/clock-client.js` (+5/−1) and adds **+56 lines** to `tests/clock-client.test.js`,
  covering the low-and-falling concern face across six falling directions, five non-falling
  directions, both unit systems and a stale-reading case.
- Cut 1 **deletes** `tests/clock-client.test.js` as part of jsdom retirement, replacing it with
  `tests/browser/clock-client.test.js` (116 lines, Playwright).
- The replacement covers face-component construction and markup/XSS injection. It contains
  **zero** references to `concern` or `falling`
  (positive control: the same grep returns 3 hits against `dev`'s version).
- `lib/client/clock-client.js` itself is **not** touched by cut 1, so the production fix
  auto-merges silently.

The net effect of resolving that conflict the obvious way — take the deletion, it is the jsdom
retirement — is that a glucose-display behaviour that ships in 15.0.9 keeps its code and loses its
entire test. The clock view is a screen someone reads at a glance to decide whether to act. This
conflict must be resolved by **porting** the 56 lines into the Playwright suite, not by taking
either side.

---

## 3. Production vs test/evidence/lockfile diff, per cut

Method reproduced from release-readiness §3. Categoriser validated against the published figure:
`git diff --numstat origin/dev origin/chore/nightscout-modernization` yields
**Production 136 files, +1,909/−1,164, total 573 files, +107,596/−14,872** — an exact match, so
the buckets are the document's own.

### 3a. The §5 table measures cut 1 on a different basis from cuts 2–5

Reproducing each row two ways:

| Cut | §5 published production diff | Incremental (previous cut point → this cut) | `origin/dev` → this cut |
|---|---|---|---|
| 1 | 21 files, +91/−123 | **11 files, +68/−54** | **21 files, +91/−123** |
| 2 | 60 files, +923/−465 | **60 files, +923/−465** | 74 files, +1,013/−587 |
| 3 | 23 files, +294/−54 | **23 files, +294/−54** | 89 files, +1,307/−641 |
| 4 | 66 files, +324/−511 | **66 files, +324/−511** | 125 files, +1,618/−1,139 |
| 5 | 36 files, +397/−131 | **36 files, +397/−131** | 136 files, +1,909/−1,164 |

Rows 2–5 are incremental. **Row 1 is not** — it is measured against `dev`, which in that direction
also shows `dev`'s own 59 commits as deletions. The true incremental production change for cut 1 is
**11 files, +68/−54**.

This cuts in the project's favour on the headline argument ("cut 1 is the smallest production
change in the stack" is *more* true than stated), but the published number is not comparable to the
rows beneath it, and the same frame inflates cut 1's total from 106 files to 163.

### 3b. The §5 commit counts are not additive

99 + 159 + 63 + 79 + 154 = **554**, against a stack of **495**. The discrepancy is exactly 59:

```
git rev-list --count origin/chore/mime-exposure-review..origin/chore/nightscout-modernization             # 154
git rev-list --count origin/chore/mime-exposure-review..origin/chore/nightscout-modernization --not origin/dev  # 95
git rev-list --count origin/chore/mime-exposure-review..origin/dev                                        # 59
```

Cut 5's "154 commits" is **95 commits of modernization work plus the 59 `dev` commits** pulled in by
the tip merge. Stated as modernization work, cut 5 is 95 commits, and 95 + 400 = 495.

### 3c. Full categorisation, incremental frame

| Cut | Production | Tests | Evidence docs | Lockfile | Tooling | CI | Other | Total |
|---|---|---|---|---|---|---|---|---|
| 1 | 11 f, +68/−54 | 57 f, +5,083/−4,773 | 20 f, +911/−122 | 1 f, +18/−409 | 8 f, +846/−0 | 2 f, +70/−10 | 7 f, +43/−34 | 106 f, +7,039/−5,402 |
| 2 | 60 f, +923/−465 | 68 f, +10,754/−120 | 50 f, +7,997/−22 | 1 f, +1,943/−2,582 | 11 f, +708/−0 | 1 f, +100/−2 | 8 f, +75/−85 | 199 f, +22,500/−3,276 |
| 3 | 23 f, +294/−54 | 21 f, +1,530/−9 | 24 f, +6,955/−6 | 1 f, +444/−34 | 6 f, +376/−0 | 1 f, +44/−16 | 3 f, +20/−10 | 79 f, +9,663/−129 |
| 4 | 66 f, +324/−511 | 46 f, +1,752/−327 | 35 f, +4,342/−69 | 1 f, +668/−1,404 | 5 f, +252/−0 | 1 f, +12/−0 | 7 f, +94/−94 | 161 f, +7,444/−2,405 |
| 5 | 36 f, +397/−131 | 90 f, +16,932/−145 | 62 f, +40,849/−150 | 2 f, +763/−1,172 | 20 f, +1,021/−8 | 1 f, +48/−2 | 39 f, +869/−65 | 250 f, +60,879/−1,673 |

The "production is a small fraction of the diff" conclusion survives the recategorisation intact,
at every cut point.

---

## 4. Linearity: confirmed

`git merge-base --is-ancestor` for each consecutive pair:

```
retire-jsdom            -> build-runtime-separation   OK
build-runtime-separation-> compose-mongodb6           OK
compose-mongodb6        -> mime-exposure-review       OK
mime-exposure-review    -> nightscout-modernization   OK
```

**The parcel-as-prefix model holds.** Every cut point is an ancestor of the next, so cutting at a
branch tip does ship everything before it.

Two qualifications the §5 framing does not carry:

1. `origin/dev` is **not** an ancestor of cuts 1–4 (it is an ancestor only of cut 5). The prefixes
   are prefixes *of the stack*, not of a line that starts at today's `dev`.
2. The history is linear in ancestry but not flat: 254 of the 495 commits are merges (the child-PR
   merge commits). `git log --first-parent` is required for any per-step accounting.

---

## 5. CI reality per cut

Read from `.github/workflows/*.yml` on each branch. Three workflow files exist on every ref:
`main.yml`, `codeql-analysis.yml`, `close-accidental-sync-prs.yml`.

### Triggers

Identical on all five cut branches and on `dev`:

```yaml
# main.yml
on:
  push:        branches: [master, dev]
  pull_request: branches: [master, dev, chore/nightscout-modernization]   # 3rd entry: cut branches only
# codeql-analysis.yml
on:
  push:        branches: [dev, master]
  pull_request: branches: [dev, master, chore/nightscout-modernization]
```

Confirms the three facts carried in the brief: `docker-build` and `publish` are gated on
`(github.ref == 'refs/heads/master' || github.ref == 'refs/heads/dev') && github.repository_owner == 'nightscout'`
and push-publish an image to Docker Hub; push triggers exist only for `master` and `dev`; PRs
targeting `chore/nightscout-modernization` run full CI.

**A push to any `chore/*` branch runs nothing.** The recorded green checks for these branches come
from PRs that targeted `chore/nightscout-modernization`, i.e. they were evaluated against the
integration branch as base — **not** against `dev`.

### Jobs present, by cut

| Ref | `test` matrix | `maintained-mongo` | `replica-test` | `browser-test` | concurrency group |
|---|---|---|---|---|---|
| `dev` | Node 20/22/24 × Mongo 4.4/5.0/6.0 = 9 | — | — | — | no |
| Cut 1 | Node 22.23.2/22/24.20.0/24 × Mongo 5.0/6.0 = 8 | — | — | 2 Node × 3 browsers = 6 | no |
| Cut 2 | same 8 | 2 × Mongo 7.0.40/8.0.29 = 4 | 2 Node × 4 Mongo = 8 | 6 | no |
| Cut 3 | Node 22/24 × Mongo 5.0.32/6.0.27 = 4 | 4 | 4 (explicit include) | reduced matrix | **yes** |
| Cut 4 | 4 | 4 | 4 | reduced | yes |
| Cut 5 | 4 | 4 | 4 | reduced | yes |

Cut 1 also makes `docker-build` and `docker-build-pr` depend on `needs: [test, browser-test]`,
so from cut 1 onward a browser-test failure blocks image publication.

### Does each tip pass?

**Not re-verified, and it cannot be from here.** Establishing it would require either a network
query of GitHub check state or a local run of the full 21-check matrix (multiple Mongo versions,
replica sets, three browser engines). Neither was done — no network calls were made. The only
evidence for "21 green checks" remains release-readiness §3, which records the state of PR #8605 on
2026-09-14 against the integration branch base.

**What can be said, and is new:** a PR opening cut 1 → `dev` today has an unresolvable merge (§2).
GitHub cannot compute `refs/pull/N/merge` for a conflicted PR, so `actions/checkout`'s default ref
does not exist. Expect the PR to show as conflicted with CI unable to run at all, rather than as a
red check. *(Inferred from the conflict measurement plus GitHub's documented merge-ref behaviour;
not observed.)*

---

## 6. Blast radius of cut 1

### The Node floor is real and is encoded in one place that matters

| Ref | `engines.node` |
|---|---|
| `origin/master` (15.0.8) | `>=20.x` |
| `origin/dev` (15.0.9) | `>=20.x` |
| Cut 1 onward | `^22.23.2 \|\| ^24.20.0` |

Commit `a95c2ce5` *"Require supported Node 22 and 24 LTS runtimes before startup"* adds
`lib/server/runtime-policy.js`:

```js
const semver = require('semver');
const supported = require('../../package.json').engines.node;
module.exports = function checkRuntime () {
  if (!semver.satisfies(process.version, supported)) {
    console.error('ERROR: Node ' + process.version + ' is not supported. ...');
    process.exit(1);
  }
};
```

called from `lib/server/server.js` before configuration load and from `bootevent.js`'s
`checkNodeVersion`, which is also moved ahead of `startBoot` in the acquire chain.

### "Trivially revertible": true mechanically, misleading operationally

**True:** `runtime-policy.js` derives the accepted range from `package.json` `engines.node`. Editing
that one field restores Node 20 acceptance everywhere. There is no second hard-coded version.

**Three qualifications:**

1. **Reverting the field gives you an untested Node 20.** Cut 1 removes Node 20 from the `test`
   matrix in the same commit. After a revert, `engines` would permit a runtime that **no CI job
   exercises**. A revert therefore restores the permission, not the assurance.
2. **The floor is written in six other places** that a one-field revert leaves stale and
   contradictory: `.nvmrc` (`22` → `24`), `bin/setup.sh` (`setup_20.x` → `setup_24.x`),
   `azuredeploy.json`, `README.md`, `CONTRIBUTING.md`, `docs/meta/architecture-overview.md`.
   Operators following the install docs would be pointed at Node 24 by a tree that accepts Node 20.
3. **`Dockerfile` is unchanged at `node:22-alpine` on both `dev` and cut 1**, while `engines`
   requires `^22.23.2`. The floating major tag satisfies the patch floor today and will continue to,
   but any cached or pinned older `node:22-alpine` layer produces a container that boots and
   immediately `process.exit(1)`s with the runtime-policy message. Worth naming in release notes as
   the expected symptom, so an operator recognises it.

**Operator-facing framing (plain language), for the release notes.** Cut 1 raises the minimum
version of Node.js — the program that runs Nightscout on your server — from 20 to 22.23.2 or 24.20.0.
If you upgrade Nightscout without first upgrading Node, Nightscout will refuse to start and print a
message saying which version it needs. It will not start with a partly-working configuration and it
will not change any of your data. Nightscout stopping means your glucose data stops being collected
and displayed until you upgrade Node and restart, so plan the upgrade for a time when you can
watch it, and know how to get your readings from your pump or CGM app directly in the meantime.
This is not medical advice; if Nightscout is part of how you or a family member manage diabetes,
talk to your care team about a fallback before you upgrade.

---

## 7. The D3 question

### 7a. The version delta is confirmed; the file list in §2 is wrong

`d3` is `^5.16.0` on `origin/master` and `^7.9.0` on `origin/dev`. Confirmed.

Release-readiness §2 attributes five production files to commit `48075a18`
*"Migrate charts to D3 7 with interaction regression coverage"*. **Three of the five are not in that
commit and are not D3 work.** `git show --numstat 48075a18` gives, for production:

| File | In `48075a18` | §2 claims |
|---|---|---|
| `lib/client/renderer.js` | **+25/−25** | +26/−26 |
| `lib/client/chart.js` | **+2/−2** | +2/−2 |
| `lib/report_plugins/daytoday.js` | **+3/−3** | *not listed* |
| `lib/plugins/cob.js` | **not touched** | +49/−73 |
| `lib/plugins/loop.js` | **not touched** | +13/−2 |
| `lib/client/clock-client.js` | **not touched** | +5/−1 |

The three misattributed files come from three unrelated `dev` commits:

```
git log --oneline origin/master..origin/dev -- lib/plugins/cob.js
# 34e9b2da fix(cob): use the COB reported by the uploading system
git log --oneline origin/master..origin/dev -- lib/plugins/loop.js
# 893e50bb Handle Loop transport and authorization failures clearly
git log --oneline origin/master..origin/dev -- lib/client/clock-client.js
# 06372e1d fix: show concern for low and falling clock readings
```

§2's numbers are the `master`→`dev` *aggregate* per file, presented as one commit's diff.

**This error matters in the direction that costs something.** The genuine D3 blast radius is
smaller than stated — three files, 30 changed lines. But the largest chart-adjacent production
change on `dev`, `lib/plugins/cob.js` **+49/−73**, is a **behaviour change to carbs-on-board
reporting** ("use the COB reported by the uploading system"), filed in the release document under
the D3 heading. COB feeds what a user reads when deciding about food and correction. It is more
than twice the size of the entire D3 migration and it currently has no line of its own in the
release decision. It should get one before 15.0.9 is cut.

### 7b. What coverage those files actually have on `dev` today — measured

`dev` has `tests/dependency-d3.test.js` (218 lines). Contrary to the impression left by §2's
"rests on jsdom and on whatever manual checking was done", this is a **real interaction suite**. It
loads the actual `lib/client/renderer.js` and `lib/client/chart.js` through
`tests/fixtures/d3-chart.js` against the official D3 7 browser bundle, and covers brush
centre/clamp/move, context-window drag, treatment drag by mouse and touch, hover tooltips, profile
switch details, both unit systems, and the confirmed/cancelled emission of all six treatment
operations.

Executed on an isolated copy of `origin/dev` (Node v24.15.0, d3 7.9.0, jsdom 26.1.0):
**24 passing, 0 failing, 550ms.**

Other coverage of the three genuinely-D3-touched files on `dev`:
`tests/client.renderer.test.js`, `tests/profile-empty-name.test.js`,
`tests/stored-output-sinks.test.js` (renderer and `daytoday`), `tests/fixtures/d3-chart.js` (chart).

### 7c. Non-vacuity: the suite was broken deliberately, and it has one gap that is not cosmetic

Per the programme's non-vacuity rule, each check was tested by breaking the code under it. Every
break was applied to an isolated copy of the tree restored from `origin/dev` between runs; the
shared checkout was never modified.

| Break | Description | Result |
|---|---|---|
| B1 | Revert all `.on('mouseover', function(event, d)` to the D3-5 signature `function(d)` | **caught** (2 failing, run aborted at 12/24) |
| B2 | `Math.min(Math.max(0, event.x), chart().charts.attr('width'))` → `event.x` in the treatment drag handler | **NOT caught — 24 passing** |
| B3 | `Math.min(Math.max(0, event.y), chart().focusHeight)` → `event.y` | **NOT caught — 24 passing** |
| B2+B3 | both clamps removed together | **NOT caught — 24 passing** |
| B5 | `tooltipLeft` always returns 0 | **caught** (3 failing) |
| B6 | `chart.js` `d3.pointer(...)` → `event.pageX` at the `beforeBrushStarted` migration site | **caught** (2 failing) |

The suite is mostly live. B1 and B6 confirm it distinguishes the D3 5 and D3 7 branches at the
migration's core hazard — the D3 6 change that makes the event object the listener's first
argument.

**B2/B3 are a genuine, measured coverage gap.** Instrumenting the handler shows it is not dead code:

```
### drag handler invocations: 25
DRAG raw x=20  y=20 | 150 | 380   attrWidth="900"  focusHeight=399
DRAG raw x=400 y=20 | 150 | 380
```

The handler runs 25 times, but with only **two** x values (20, 400) and three y values, every one
strictly inside `0..900` and `0..399`. The clamp is executed on every call and **its boundary is
never reached**. That is the second way a check goes vacuous: the code distinguishes the branches,
the corpus never exercises the property.

The clamp is not decorative. In `lib/client/renderer.js:764` and `:770`:

```js
var x = Math.min(Math.max(0, event.x), chart().charts.attr('width'));
newTime = new Date(chart().xScale.invert(x));
```

and on drag end, with `operation === 'Move'`, `newTime.toISOString()` is emitted as a `dbUpdate`
rewriting a treatment's `created_at`. The clamp is what bounds a user-initiated rewrite of a
**treatment's timestamp** to the visible chart window — and a treatment's timestamp is what IOB and
COB calculations key off. The same expression also selects the drop-zone operation
(`Remove` / `Remove insulin` / `Remove carbs` / `Move carbs` / `Move insulin`) via `isInRect`.

These are the exact lines the D3 6 migration rewrote (`d3.event.x` → `event.x`). They are the least
covered lines it touched.

### 7d. What this does and does not settle for 15.0.9

**Settled:** `dev` has real, non-vacuous D3 7 interaction coverage for `renderer.js` and `chart.js`
at the migration sites. §2's implication that chart interaction rests on manual checking is too
pessimistic. The D3 migration itself is 3 files and 30 lines.

**Not settled, and the honest residual gap:** the coverage is jsdom, and the fixture names its own
blind spot — `// jsdom has no SVG animated width/height; provide the same explicit chart extent`,
plus a stubbed `getBoundingClientRect() => ({width: 900, height: 600})`. Chart interaction *logic*
is tested. Chart *geometry* derived from real layout is not, and cannot be by this fixture. So:
pan/zoom/brush/tooltip/touch logic — covered. Rendered position against a real measured SVG —
uncovered. Out-of-bounds treatment drag — uncovered in either dimension.

**On §2's Option 1** ("run the modernization branch's browser suite against the release tree; costs
one CI run plus a cherry-pick of `tests/browser/`"): the cherry-pick is larger than stated. Cut 1's
`tests/browser/chart-interactions.test.js` requires `./fixture` (Playwright via `playwright-core`),
`./modules` (`buildModules`) and `./hooks.js`, and cut 1 **deletes** `tests/dependency-d3.test.js`,
`tests/fixtures/d3.js`, `tests/fixtures/d3-chart.js` and `tests/client.renderer.test.js`.
Running it against `dev` means porting the Playwright harness and its module-building fixture onto
a tree that has neither, not copying a directory. Still the strongest option; not a one-CI-run task.

**Cheapest thing that closes a real gap today, independent of any of the above:** add two cases to
`tests/dependency-d3.test.js` dragging a treatment to `x = -50` and `x = 1200` and asserting the
resulting `newTime` stays inside the chart window. Both currently pass with the clamp deleted.

---

## 8. Corrections owed to release-readiness 2026-09-14

| § | Statement | Correction |
|---|---|---|
| TL;DR 5 | "The stack is currently 0 commits behind `dev`" | True of the tip only, and only because of tip commit `0a4109f6`. Cuts 1–4 are 59 behind. |
| TL;DR table | "Four cut points exist today at zero rebase cost" | All four conflict against `dev` in 4–5 files. Cost is not zero and never was. |
| §5 intro | "each costs zero rebase work today" | Same. |
| §5 table, row 1 | cut 1 production diff "21 files, +91/−123" | That is the `dev`-based frame. Incremental is 11 files, +68/−54. Rows 2–5 are incremental; row 1 is not. |
| §5 table, commits column | 99 / 159 / 63 / 79 / 154 | Sums to 554 against a 495-commit stack. Cut 5 is 95 modernization commits + the 59 `dev` commits. |
| §5 "trivially revertible" | engines field plus a boot check | Mechanically true; leaves Node 20 with no CI job, and six other files stating the floor. |
| §2 | `48075a18` changes `renderer.js`, `cob.js`, `loop.js`, `clock-client.js`, `chart.js` | It changes `renderer.js` (+25/−25), `chart.js` (+2/−2), `daytoday.js` (+3/−3). `cob.js`, `loop.js`, `clock-client.js` are three other commits. |
| §2 | chart interaction "rests on jsdom and on whatever manual checking was done" | Understates it: a 218-line interaction suite exists and was verified non-vacuous by deliberate breakage. The real gap is jsdom's stubbed geometry and the unexercised drag clamps. |
| §3 | "linear stack" | Confirmed by `--is-ancestor`, with the caveat that 254 of 495 commits are merges and `dev` is an ancestor only of cut 5. |

## 9. What did not change

- Linearity holds; parcel-as-prefix is sound (§4).
- "Production code is a small fraction of the diff" holds at every cut point (§3c).
- Cut 1 is the smallest production change in the stack — by more than the document claims.
- Cut 4 remains the one to slow down on; nothing measured here touches that judgement.
- The governance finding (one author, zero human reviews) is untouched by this re-measurement.

## 10. Reproducing

From `externals/cgm-remote-monitor-official`, with no fetch:

```sh
for B in chore/retire-jsdom chore/build-runtime-separation chore/compose-mongodb6 \
         chore/mime-exposure-review chore/nightscout-modernization; do
  echo "$B $(git rev-list --left-right --count origin/$B...origin/dev)"   # ahead behind
  git merge-tree --write-tree --name-only origin/dev origin/$B | head -1 >/dev/null || true
done
```

The diff categoriser used for §3 is at
`/tmp/.../scratchpad/cat.sh` (session-local); it buckets `git diff --numstat` output by path into
Production (`lib|views|bin|webpack|static`, plus `server.js`/`app.js`), Tests (`tests/`), Evidence
docs (`docs/`), Lockfile, Tooling (`tools/`), CI (`.github/workflows/`) and Other. It is validated
by reproducing release-readiness §3's published 136 / +1,909 / −1,164 exactly.

The non-vacuity runs of §7c used an isolated `git archive origin/dev` extraction with
`node_modules` symlinked from the shared checkout; the shared checkout was not modified at any
point and is still clean at `a8888f0d`.
