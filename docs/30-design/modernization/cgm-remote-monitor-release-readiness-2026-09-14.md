# cgm-remote-monitor: release readiness and modernization sequencing

*Contributor- and maintainer-facing.*

**Snapshot — describes 2026-09-21, `origin/dev` `59430336`.** Status: **superseded for 15.0.9**
by [release readiness for 15.0.9](release-readiness-15.0.9-2026-09-22.md) (measured against
`origin/dev` `74fc6619`); current decisions: the adopted release train in
[the versioning policy §8.3](semver-and-release-versioning-policy-2026-09-15.md#83-the-release-train),
item state in [`queue/work-queue.yaml`](../../../queue/work-queue.yaml) (`RT-*`), and the open
train defect BF-64 in the [backfix register](../remedial/nightscout-backfix-register.md).

Companion to
[the adoption roadmap](../nightscout-adoption-roadmap-2026-09-11.md), which sequences
ecosystem work; this document sequences *release* work in the hub itself.

Refs measured: `origin/dev` at `59430336` (2026-09-21), `origin/master` at `92d08342` =
tag `15.0.8` (2026-09-04), and the five `chore/*` cut tips, of which cuts 1–4 are unmoved
since 2026-09-05/06 and cut 5 is `b1bdaca0`. Commands are reproducible from
`externals/cgm-remote-monitor-official`. Where this document and the
[backfix register](../remedial/nightscout-backfix-register.md) disagree, the register is
authoritative — it carries the per-entry history this document deliberately does not.

---

## TL;DR

**The release candidate and the modernization stack are two different kinds of
risk, and the evidence says to stop treating them as one decision.**

1. **`dev` is a clean, shippable bug-fix release — with one exception.** 299
   commits, 191 files, **+13,405/−1,232**, and most of that is *new tests*. It now
   also carries the ten Phase 0 backfixes merged 2026-09-17 to 09-20. The exception is
   **D3 5.16 → 7.9**, a two-major charting upgrade that reaches
   `lib/client/renderer.js`, `lib/plugins/cob.js` and `lib/client/chart.js`, shipping under
   a patch version number with **no real-browser coverage on `dev`**.
2. **The modernization "mega-PR" is not 573 files of risk.** Categorised,
   #8605 is **136 production files, +1,909/−1,164**. The other 105,687
   insertions are tests (35,165), evidence documents (60,518), lockfile and
   measurement tooling. Production code is **1.8%** of the diff.
3. **It is also already parcelled.** 66 of the 67 `chore/*` branches form a
   single linear stack of 100 individually-CI'd child PRs (#8606–#8723). The
   question is not *whether* to decompose it — that was done — but **where to
   cut it for release**. §5 names five cut points that already exist as branch
   tips.
4. **The governance gap is the real finding.** All 495 stack commits have one
   author; all 100 child PRs were self-merged with **zero human reviews**; and
   the release PR #8598 and integration PR #8605 each carry **zero human
   reviews** (the only entries are `github-advanced-security` bot comments).
   Confidence currently rests entirely on automated gates and the author's own
   evidence documents. Parcelling is the cheapest way to make review tractable.
5. **Holding the train gets more expensive every day, and the price is now known.**
   Cuts 1–4 went from 59 commits behind `dev` to **124** in six days, and their
   conflicting paths from 4–5 each to **7 / 14 / 16 / 18** (§5). Cut 5 is 0 behind only
   because it was re-merged on 2026-09-21. Every further merge into `dev` forces a refresh
   of a 495-commit stack plus its 21-check CI and its recorded measurements.

| Decision | What the evidence supports |
|---|---|
| Ship 15.0.9 soon? | **Yes** — after answering the D3 question (§2) |
| Freeze the window? | **Yes, with a named closing date**, not indefinitely (§4) |
| Land more small fixes first? | **Four of them**, all cheap; the rest wait (§4) |
| One modernization release or several? | **Several.** Five cut points exist as branch tips; the rebase onto current `dev` is prepared (§5) |
| Does any of this block the ecosystem roadmap? | **No.** The `settings` channel is untouched (§6) |

---

## 1. What is actually on `dev`

```
git log --oneline origin/master..origin/dev | wc -l     # 299
git diff --shortstat origin/master origin/dev           # 191 files, +13405 -1232
```

299 commits, 93 of them merge commits. The distribution is lumpy and worth
knowing: **170 of the 299 landed on a single day**, 2026-09-05, when a backlog
of Dependabot proposals was resolved against `dev` in one sitting. The second
cluster is Phase 0 — ten backfix PRs merged between 2026-09-17 and 2026-09-20.

| Date | Commits |
|---|---:|
| 2026-05-10 → 2026-09-04 | 40 |
| **2026-09-05** | **170** |
| 2026-09-06 | 20 |
| 2026-09-09 → 2026-09-16 | 30 |
| **2026-09-17 → 2026-09-21 (Phase 0)** | **37** |

### Content

Thirteen distinct fix branches, eleven resolved Dependabot proposals, one
Crowdin batch, one docs-only MongoDB 4.4 removal, one version bump.

| Fix | Issue |
|---|---|
| `fix/8714-opt-in-debug-logging` — quiet routine server/connector logs | #8714 |
| `fix/empty-profile-name-8562` — preserve unnamed profiles | #8562 |
| `fix/profile-switch-preprocessing-8584` | #8584 |
| `fix/clock-low-trend-8638` | #8638 |
| `fix/treatments-query-errors-8675` | #8675 |
| `fix/8600-npm12-remote` | #8600 |
| `fix/dailystats-a1c-units` (AndyLow91) | — |
| `fix/cache-stale-delete-race` (bjorkert) | — |
| `fix/cob-uploader-reported-value` (bjorkert) | — |
| `fix/report-reinit-on-socket-reconnect` (bjorkert) | — |
| `fix/treatments-event-type-filter` (bjorkert) | — |
| `fix/report-uniq-cascade` (toniuhlemann) | — |
| `fix/opaque-error-response` (NandhaKishorM) | — |

**No schema change, no API contract change, no feature addition.** The largest
source files in the diff are tests: `tests/notifications-v2.test.js` (+311),
`tests/dependency-axios.test.js` (+250), `tests/report-sgv-pipeline.test.js`
(+227). This is a healthy release profile.

### CI

PR **#8598** (`dev` → `master`) is green on every check: Node 20/22/24 ×
MongoDB 4.4/5/6, npm 12 install/build, Docker amd64/arm64, Docker Hub publish,
CodeQL. `mergeable: MERGEABLE`. It carries **zero human reviews**.

---

## 2. The one thing in 15.0.9 that is not a bug fix

Declared dependency changes, `master` → `dev`:

| Package | 15.0.8 | 15.0.9 candidate |
|---|---|---|
| **d3** | **^5.16.0** | **^7.9.0** |
| @babel/core, @babel/preset-env | ^7.18.10 | ^7.29.7 |
| babel-loader | ^8.2.5 | ^9.2.1 |
| jsdom | ^24.1.3 | ^26.1.0 |
| axios | ^0.31.1 | ^0.33.0 |
| dompurify | ^3.4.2 | ^3.4.14 |
| express | 4.22.1 | 4.22.2 |
| body-parser | ^1.20.5 | ^1.20.6 |
| mocha | ^11.7.5 | ^11.8.0 |
| nightscout-connect | tag `v0.0.13` | **raw commit `234d47c8`** |

Two items deserve a decision before the release is cut.

**D3 5 → 7 is a charting migration, not a bump.** Commit `48075a18`
("Migrate charts to D3 7 with interaction regression coverage") changes
`lib/client/renderer.js` (+26/−26), `lib/plugins/cob.js` (+49/−73),
`lib/plugins/loop.js` (+13/−2), `lib/client/clock-client.js` (+5/−1) and
`lib/client/chart.js` (+2/−2). Coverage added is `tests/dependency-d3.test.js` (+218)
plus the existing jsdom-backed `client.renderer` integration test.

> **`dev` has no real-browser test suite.** `npm run test:browser` exists only
> on `chore/nightscout-modernization`. On `dev`, every claim about chart
> *interaction* — pan, zoom, brush, tooltip, touch — rests on jsdom and on
> whatever manual checking was done. The main glucose chart is the screen
> people read to make dosing decisions; a rendering regression there is not a
> cosmetic bug.

This is the sharpest argument in the whole analysis for stepping stones: **the
release shipping first is the one that lacks the test bed the later work
builds.**

**`nightscout-connect` is pinned to an untagged commit SHA.** 15.0.8 pinned
tag `v0.0.13`; the candidate pins `234d47c85510a77f07b3be0d2c026dd0272715d6`
via tarball URL. That is reproducible but unreviewable at a glance and gives
the release no connector version to name in notes. Cutting a
`nightscout-connect` tag before the release is a minutes-long task.

**Options, in order of cost:**

1. Run the modernization branch's browser suite against the release tree as a
   one-off validation (the suite exists; it need not ship to be run).
2. Do a manual browser pass on dashboard + reports + clock at both units, and
   record it in the release notes.
3. Ship and call the D3 migration out explicitly in the release notes so
   operators know where to look if charts misbehave.

Option 1 is the strongest and costs one CI run plus a cherry-pick of
`tests/browser/`.

---

## 3. The modernization stack, measured

### It is one branch made of sixty-six

```
git branch -r | grep -c 'origin/chore/'                          # 67
git rev-list --left-right --count origin/dev...origin/chore/nightscout-modernization
                                                                 # 0  495
```

Sixty-six of the 67 `chore/*` branches are **ancestors of
`chore/nightscout-modernization`** — a linear stack. The exception is
`chore/jsdom-30`, the abandoned upgrade alternative (PR #8613, closed in
favour of removal). The rollup is **495 commits ahead of `dev` and 0 behind**:
it is in sync with the `dev` tip as of today.

The stack was built as **100 child PRs, #8606 → #8723, merged between
2026-09-05 and 2026-09-09** — five days — each with its own CI run against the
integration branch.

### 573 files is the wrong number

```
git diff --numstat origin/dev origin/chore/nightscout-modernization
```

| Category | Files | Insertions | Deletions |
|---|---:|---:|---:|
| **Production** (`lib/`, `views/`, `bin/`, `webpack/`, `static/`) | **136** | **1,909** | **1,164** |
| Tests | 208 | 35,165 | 5,242 |
| Evidence documents (`docs/`) | 166 | 60,518 | 126 |
| Lockfile | 2 | 6,314 | 8,079 |
| Measurement tooling (`tools/`) | 59 | 3,434 | 249 |
| CI workflows | 2 | 256 | 12 |
| **Total** | **573** | **107,596** | **14,872** |

**Production code is 1.8% of the insertions.** The largest single production
files changed are new small local modules replacing packages:
`lib/client/storage.js` (+149), `lib/client/help-tooltips.js` (+122),
`lib/server/pushover-client.js` (+107), `views/service-worker.js` (+73/−124).

Per stack step, the production footprint is smaller still. The largest single
step is `chore/page-bundles` at 11 files, +154/−151. Most steps are a handful
of files and a few dozen lines.

### What it changes for operators

| Change | Branch | Production diff |
|---|---|---|
| Node floor `>=20.x` → `^22.12 \|\| >=24` (§5) | `chore/node-lts-policy` | 16 files, +49/−113 |
| MongoDB 4.4 out of support/CI; 5/6 retained, 7/8 added | `chore/retire-mongodb-44`, `chore/mongodb-driver7` | 14 files |
| **Legacy Dexcom bridge retired** in favour of Connect | `chore/retire-legacy-dexcom-bridge` | 5 files, +38/−183 (`lib/plugins/bridge.js` deleted) |
| **MiniMed Connect retired** in favour of Connect — a path already broken in practice (§5) | `chore/retire-mmconnect` | 4 files, +39/−152 (`lib/plugins/mmconnect.js` deleted) |
| Proxy trust defaults reworked | `chore/explicit-trusted-proxies` | 12 files, +51/−41 |
| Express 5 | `chore/modernization-express5` | 11 files, +55/−24, 47 test files |

### CI difference

`dev` runs 9 matrix jobs (Node 20/22/24 × Mongo 4.4/5/6) plus npm 12, Docker
and CodeQL. #8605 runs **21 green checks**, including:

- Browser tests on **chromium, firefox and webkit** (Node 22/24)
- MongoDB **7.0.40 and 8.0.29** maintained jobs
- **Replica-set** jobs across Mongo 5/6/7/8
- Docker validate on amd64 **and** arm64

The modernization branch is, by CI surface, substantially better tested than
the release about to ship ahead of it.

### The governance fact

```
git log --format='%an' origin/dev..origin/chore/nightscout-modernization | sort -u
# Andy Low   (495 of 495 commits)
```

Sampled child PRs #8606, #8629, #8682, #8721, #8722, #8723: **zero human
reviews** on each; one carries a `github-advanced-security` bot comment. PR
#8605 itself: zero human reviews, two bot comments. PR #8598: zero reviews.

This is stated as fact, not accusation — the plan document itself says the
maintainer will review and run the branch in production, and the automated
gates are unusually thorough. But it means **no second person has yet read
1,909 lines of changed production code**, and it is the single strongest
argument for parcelling: a 136-file production review is plausible; a
573-file one is not, and reviewers bounce off it.

---

## 4. The freeze decision

### What freezing costs

Close to nothing today, and more each day. The stack is **0 behind `dev`**.
Overlap between currently-open PRs and the 573 files the stack touches:

| PR | Files | Overlap with modernization |
|---|---:|---:|
| #8730 Crowdin | 1 | **0** |
| #8729 chart 0-height guard | 2 | 1 |
| #8493 weektoweek report tests | 2 | 1 |
| #8530 48-hour focus range | 1 | 1 |
| #8568 loop status timeline | 3 | 1 |
| #8522 mmol/mg in bolus wizard | 2 | 2 |
| #8385 wake-lock toggle | 5 | 2 |
| #8419 iOS push notification tests | 9 | 3 |
| #8501 externalise snooze to mongo | 9 | 3 |
| #8732 pill/profile editor guards | 14 | 5 |
| #8531 smooth glucose line | 5 | 4 |
| #8580 custom notification webhooks | 8 | 4 |
| #8261 multi-insulin API | 6 | 4 |
| #8526 configurable Y-axis range | 6 | 5 |
| #8555 seconds on dashboard clock | 6 | 5 |
| **#8348 Remove Moment** | **67** | **30** |

Every merge into `dev` above zero overlap forces a stack refresh: rebase 495
commits, re-run 21 checks, and re-record the measurements the evidence
documents assert. That is the price of an open window.

### The four fixes worth landing before the window closes

All were `MERGEABLE`, small, and self-contained. Two have since landed:

| PR | State | Why now |
|---|---|---|
| **#8729** guard `chart.update()` against 0-height container | **merged 2026-09-20** | 2 files, +74/−1. Directly in the D3-migration blast radius (§2) |
| **#8732** pill and profile-editor behaviour on incomplete data | **merged 2026-09-20** | 14 files, +326/−9. Fixes a class of failure on sites with sparse data |
| **#8730** Crowdin updates | open | 1 file, zero overlap, translations are release-shaped |
| **#8522** mg/dL vs mmol/L in Bolus Wizard Preview and profile | open | 2 files, +18/−16. A units bug in a dosing-adjacent display |

> **#8729 and #8732 have never run CI.** The only workflow that executed on
> either is `auto-close`. Both are from first-time contributors, so Actions is
> waiting on maintainer approval. **Approving those two workflow runs is the
> single cheapest piece of release evidence available right now** — as of this
> writing neither fix has been tested by anything.

Everything else on the list is a *feature* (#8526, #8531, #8555, #8385, #8580,
#8261, #8501). Features after a version bump, in a window being frozen, in a
release with an unreviewed charting migration in it, is the combination to
refuse. They cost nothing to defer to 15.1.

### Backlog hygiene — free wins

41 PRs are open: 29 → `dev`, **11 → `master`**, 1 → `wip/next-release`.
18 are `CONFLICTING`. 15 are over a year old; 7 have had no update in six
months.

Three can be closed today with a note, reducing the backlog by 7%:

- **#8498** "[master] Backport CVE-2021-36755: prevent XSS via admin-notifies".
  **Already fixed by other means.** `lib/client/adminnotifiesclient.js` on
  both `dev` and `master` routes title, message and the additional-info string
  through `textAsHtml()` (`lib/utils/html.js`: `decodeHTML` then `escapeText`
  from `entities`, for a text-node context). The cherry-pick of `68f3f90e` is
  not an ancestor of either branch, but the injection points it addressed are
  escaped. Verify and close.
- **#7875** "experiments with playwright and webpack" (2023-02-05, `bewest`).
  Superseded: `chore/retire-jsdom` delivers a working Playwright browser suite
  with 426 cases. Close as superseded, pointing at #8629.
- **#8405** targets `wip/next-release`, whose last commit is 2026-05-07 and
  which no current release process feeds. Retarget to `dev` or close.

**The eleven PRs targeting `master` are mostly mis-targeted** and will never
merge as filed — `master` only receives `dev`. #8540, #8541, #8542
(tim2000s: Trio dark theme, TIR widget, accessibility, AGP report charts),
#8537, #8560, #7656, #7887, #7221 all want `dev`. A single maintainer pass
retargeting them would move real contributions from "permanently stuck" to
"reviewable", at the cost of one comment each.

### The contradiction that needs an answer, not a freeze

**#8348 "Remove Moment"** — 67 files, **+10,042/−6,197**, open since
2025-05-02, updated 2026-09-07. The modernization plan's **M27** records a
documented decision to **retain** narrowed Moment 2.30.1 with an explicit
revisit trigger, after comparing Luxon, Day.js, native `Intl` and Temporal —
and it cites #8348 as an input to that comparison.

So a contributor has a 16,000-line PR that a decision made on another branch
has effectively declined, and nobody has told them. That is a community cost
independent of the release. **The M27 decision document should be posted to
#8348 with a clear verdict** — accept, decline, or "revisit at trigger X" —
before the modernization lands and makes the PR unmergeable by attrition.

---

## 5. Parcelling the modernization: five cuts that already exist

The stack is linear, so a "parcel" is a **prefix** — cut at a branch tip and everything
before it ships. The five cuts below are existing branch tips.

| # | Cut at | Commits | Production diff | Tests | What ships |
|---|---|---:|---|---|---|
| **1** | `chore/retire-jsdom` | 99 | **21 files, +91/−123** | 68 files, +5,138/−5,582 | Mongo 4.4 out of CI; espree lint parser; **jsdom → Playwright browser suite**; Node floor `^22.12 \|\| >=24` |
| **2** | `chore/build-runtime-separation` | 159 | 60 files, +923/−465 | 68 files, +10,754/−120 | Page bundles, narrowed D3, native asset modules, event bus, browser storage, boot sequence, callback tasks, Babel 8, build/runtime separation |
| **3** | `chore/compose-mongodb6` | 63 | 23 files, +294/−54 | 21 files, +1,530/−9 | MongoDB driver 7, maintained jQuery UI, native help tooltips, CI streamlining |
| **4** | `chore/mime-exposure-review` | 79 | 66 files, +324/−511 | 46 files, +1,752/−327 | **Legacy Dexcom and MiniMed retirement**, explicit trusted proxies, maintained csv/semver/webpack/eslint, lint cleanup, DOMPurify and Moment/tz refresh |
| **5** | `chore/nightscout-modernization` | 154 | 36 files, +397/−131 | 90 files, +16,932/−145 | Express 5, Helmet, EJS, Axios, entities, mime-types, APN, Pushover, Mocha 12, Swagger; notification cache; widget decision; final validation |

### The rebase cost, and why it argues for shipping sooner

Cuts 1–4 have not moved since 2026-09-05/06. `dev` has, and the gap is the main cost of
holding the train:

| | 2026-09-15 | 2026-09-21 |
|---|---|---|
| cuts 1–4 behind `dev` | 59 commits | **124** |
| conflicting paths, cut 1 / 2 / 3 / 4 | 4–5 each | **7 / 14 / 16 / 18** |

**The increase is the project's own doing.** Every one of the seven files newly conflicting
on cuts 2–4 — `lib/server/query.js`, `aggregate.js`, `lib/api/entries/index.js`,
`lib/authorization/storage.js`, `lib/server/food.js`, `lib/client/boluscalc.js`,
`tests/mongo-query-javascript.test.js` — was touched by the ten Phase 0 PRs that landed on
`dev` between 2026-09-17 and 2026-09-20. Fixing shipping defects is what made the
modernization harder to land. That is a reason to land the cuts sooner, not a reason to have
delayed the fixes.

Nine of the 25 conflicts are Phase 0 fixes the cuts predate — BF-01, BF-04, BF-07, BF-16,
BF-35, BF-36, BF-70 — where resolving toward the cut silently reintroduces a defect already
fixed on `dev`. Parcelling does not create that hazard, but it does multiply the number of
times someone has to notice it. The rebase is prepared locally as `rt/cut1`…`rt/cut4`
(queue item RT-REBASE), done by propagating up the stack so the prefix property holds.

Cut 5 is the exception: Andy Low merged `dev` into it on 2026-09-21 (`e3b22034`), so it is
0 behind and its tip is `b1bdaca0`.

### Why cut 1 should ship first and alone

It is the smallest production change in the stack — **21 files, +91/−123** — and it delivers
the **browser test suite**. Everything after it, and retroactively the D3 migration already
in 15.0.9, becomes verifiable in a real browser. That is the case for shipping it first, and
it is sufficient on its own.

**It costs operators almost nothing.** Cut 1 sets a Node floor of `^22.12 || >=24`, and the
compatibility behind that number is measured rather than assumed — with the runtime policy
stubbed out so actual behaviour was visible:

| Node | unit suite | Playwright suite |
|---|---|---|
| 24.20.0 / 24.15.0 | 310 passing / 0 failing | — |
| 22.23.2 / 22.22.0 / 22.12.0 | 310 / 0 | 21 / 0 |
| 20.20.0 | 310 / 0 | 21 / 0 |
| 18.20.8 | 295 / **15 failing** | — |

22.12 is the real lower bound and it is a dependency constraint, not an application one: the
15 failures at Node 18 are all `ERR_REQUIRE_ESM` from `sanitize-html` requiring the ESM-only
`htmlparser2`, and `require(esm)` is unflagged in 22.12. Node 20 works and is deliberately
out of range — it reached end of life on 2026-04-30 and receives no security updates, so the
project cannot support it, but nothing is broken for it. Node 22.12+ and 24+ both qualify and
the project's Docker image already satisfies the range, so **most operators need no runtime
change to take cut 1**.

### Why cut 4 is the one to slow down on

`chore/retire-legacy-dexcom-bridge` and `chore/retire-mmconnect` delete two CGM ingestion
paths. They are not equally risky, and the difference decides the schedule.

[Note 2026-09-22: the mmconnect caveat below is the maintainer's operational knowledge, not a
measurement; BF-44/BF-45 are not yet re-graded on it; and whatever mmconnect's state, leftover
`MMCONNECT_*` configuration without `CONNECT_COUNTRY_CODE` produces a whole-site boot error on
cut 4 (BF-61). The current statement is the versioning policy §3.5.]

**MiniMed/mmconnect is already broken** and has been for some time — maintainer knowledge,
not measured here, since it fails at the CareLink vendor API that no local test reaches. If
that holds, deleting it removes nothing an operator has. Cut 4 also carries a migration:
`setupConnect` calls `mmconnectCompat.applyMmconnectToConnectCompatibility(env)` and logs
that MMCONNECT credentials are served by Nightscout Connect.

**The legacy Dexcom bridge is the live path and carries the risk on its own.** It is expected
to map through to compatible `nightscout-connect` options, but that mapping has not been
exercised against a real account, and the branch's own evidence document says so:

> "Required before integration: actual Connect Dexcom transport and ingestion comparisons,
> duplicate/backfill/cutover behavior... **No real Dexcom account or live database has been
> used and no live migration is claimed.**"

If the migration misbehaves for a user, the symptom is that their glucose data stops arriving
— a data-availability failure for someone managing diabetes, not a UI defect. Nightscout is
not a medical device and none of this is medical advice; an operator should have a second way
to see readings regardless.

**Two register entries need re-grading before this parcel is scheduled.** BF-44 (MiniMed
absolute-time divergence across a cutover) and BF-45 (`setupMMConnect` starting the legacy
plugin with no check for `nightscout-connect`, so both paths can run at once) were both
written treating mmconnect as live.

So cut 4 should not travel with a dependency release. It wants its own release, its own
notice period and a documented rollback. Whether it also needs a deprecation release ahead of
it turns on the Dexcom path alone.

### Why "one big modernization release" is the weaker option

- It asks a reviewer to approve 573 files, having never reviewed the 100 PRs
  underneath. In practice that means it merges unreviewed.
- It couples reversible changes to an irreversible one — deleting an ingestion path — in a
  single rollback unit. An operator who hits a Connect problem must roll back Express 5, the
  driver and the bundles too.
- It converts every `dev` merge into a stack refresh for as long as it is open, which the
  59 → 124 measurement above prices.
- It makes bisecting a field report nearly impossible: 495 commits, one author,
  five days, one release boundary.

The counter-argument is real and should be stated: **five releases cost five
release cycles** — five sets of notes, five operator upgrades, five support
waves on the Facebook groups and Discord. For a volunteer project that is not
free. The adopted middle is **cuts 1 and 2 as separate releases** (they buy the
test bed and the browser-cost win, and both are low-blast-radius), then
**3 + 5 combined** as a dependency release, with **4 held back** and released
on its own schedule with a deprecation notice ahead of it.

---

## 6. What none of this changes for the ecosystem roadmap

The [adoption roadmap](../nightscout-adoption-roadmap-2026-09-11.md) Phase 1
depends on the `settings` v3 collection being enabled. It still is, on the
modernization branch:

```js
// lib/api3/index.js:71, chore/nightscout-modernization
app.set('enabledCollections', ['devicestatus', 'entries', 'food', 'profile', 'settings', 'treatments']);
```

Total `lib/api3` change across the whole stack: 12 files, **−39 net lines**,
all mechanical (`body-parser` → `express.json`, trust-proxy compilation,
canonical Location-header construction, credential-free alarm logging). The
`API3_SECURITY_ENABLE` / `API3_DEDUP_FALLBACK_ENABLED` /
`API3_CREATED_AT_FALLBACK_ENABLED` toggles are intact.

**Neither the release nor the modernization advances or blocks Phase 1.**
Phase 1 remains a schema-and-convention task requiring no hub code.

One sequencing note for **Phase 3**: serving controller registrations at a
well-known path is a new route, and `chore/modernization-express5` changes how
routes and parsers are registered. Adding that route *after* the Express 5
parcel avoids writing it twice. It is a small point, but it argues for the
Express 5 parcel landing before any Phase 3 hub work starts, not after.

---

## 7. What is not measured here

- **No runtime validation was performed.** Nothing in this document was run;
  every claim is from git history, the GitHub API, and the branches' own
  evidence documents. The modernization branch's measurements (heap, bundle
  bytes, image sizes, test counts) are **reported as its authors recorded
  them** and were not independently reproduced.
- **No review of the 1,909 changed production lines.** This document sizes the
  review; it does not perform it. "1.8% of the diff" is an argument about
  tractability, not a statement that the code is correct.
- **No user-impact data.** How many sites run MongoDB 4.4 or the legacy Dexcom bridge is
  unknown here, and the Dexcom number is what should actually drive the cut-4 schedule. If
  any telemetry or survey data exists, it outranks everything in §5. The equivalent question
  for MiniMed is settled without telemetry — the path is already broken (§5) — and the Node
  question is moot, since the floor now costs most operators nothing.
- **No assessment of maintainer capacity**, which is the binding constraint on
  whether five releases is better than one.
- Nothing here is clinical or regulatory advice, and the safety observations
  (D3 chart coverage, ingestion-path retirement) are engineering risk
  statements for maintainer judgement, not a safety assessment.

## 8. References

- Release PR [#8598](https://github.com/nightscout/cgm-remote-monitor/pull/8598) — `dev` → `master`, 15.0.9
- Integration PR [#8605](https://github.com/nightscout/cgm-remote-monitor/pull/8605) — modernization → `dev`
- Tracking issue [#8328](https://github.com/nightscout/cgm-remote-monitor/issues/8328)
- `docs/plans/nightscout-modernization.md` on `chore/nightscout-modernization` — the M01–M30 plan
- `docs/test-specs/modernization-completion.md`, `legacy-dexcom-retirement.md`,
  `database-upgrade-recovery.md` — the branch's own evidence set
- [Adoption roadmap](../nightscout-adoption-roadmap-2026-09-11.md) §4 — ecosystem phases
