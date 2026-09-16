# Phase 0: how to land ten branches as pull requests

**Status**: ready to push. **Nothing has been pushed.**

> **REWRITTEN 2026-09-15 (evening): the stack is dissolved and the branch SHAs moved.**
> The two-deep stack in earlier revisions of this document existed for exactly one reason — a
> `CHANGELOG.md` collision — and that reason has been removed at the maintainer's instruction. See
> §0b for the rule and §3a for what was done. **The plan is now nine independent PRs onto `dev`,
> plus one independent PR in `nightscout-connect`.** Any document, manifest row or PR body still
> describing a stack, a rebase of `bf/reads` onto `bf/coercion`, or the A–I lettering that encoded
> the order is **stale**.

## The set, measured

**Ten branches: nine in `cgm-remote-monitor`, one in `nightscout-connect`.** All nine
cgm-remote-monitor branches sit **directly on `origin/dev` at `a8888f0d`** in worktrees under
`externals/work/`. There is no branch in this set based on another branch in this set.

| repo | branch | tip | commits | what it is |
|---|---|---|---:|---|
| `cgm-remote-monitor` | `bf/alarms` | `5dcf783f` | 3 | BF-28, BF-29, BF-31 — alarm delivery |
| `cgm-remote-monitor` | `bf/auth` | `64db1f35` | 2 | BF-17, BF-30 — **security** |
| `cgm-remote-monitor` | `bf/cache` | `4f86bab1` | 2 | T0.2, T0.3 — cache clone cost |
| `cgm-remote-monitor` | `bf/coercion` | **`ab197bf8`** | 1 | T0.5 — schema-driven query coercion |
| `cgm-remote-monitor` | `bf/connect-pin` | `0807eb1c` | 1 | connector pin → the `v0.0.14` tarball (one file, +1/−1) |
| `cgm-remote-monitor` | `bf/food` | `73495331` | 1 | BF-16, and **BF-35** surfaced while fixing it |
| `cgm-remote-monitor` | `bf/merge` | `b06c6faf` | 1 | BF-36 |
| `cgm-remote-monitor` | `bf/parms` | `eb0bc918` | 3 | BF-37, BF-38, BF-39 |
| `cgm-remote-monitor` | `bf/reads` | **`2ecfeb53`** | 6 | six read-path fixes — BF-01, BF-05, BF-13, BF-14, BF-15, BF-33 |
| `nightscout-connect` | `fix/connect-timer-jitter` | `c1cce2a2` | — | T0.4 start jitter + **BF-34** |

Plus, prepared locally in `nightscout-connect`: branch `release/v0.0.14` and an annotated tag
`v0.0.14`, both at `649a7de2`.

> **The two SHAs that moved, and why.** `bf/coercion` `88d1f8a4` → **`ab197bf8`** (9 files, code
> only; 40 CHANGELOG lines removed). `bf/reads` `0d19bb31` → **`2ecfeb53`** (the changelog-only
> commit dropped, **and the branch un-stacked from `bf/coercion` and rebased directly onto
> `origin/dev`**, which is why it now carries 6 commits rather than 8). Safety refs
> **`bf/coercion.bak-changelog`** (`88d1f8a4`) and **`bf/reads.bak-changelog`** (`0d19bb31`) are
> kept until the PRs merge, as is the older **`bf/reads-prerebase`** (`824380a0`). Verified at the
> time of the strip: `git range-diff` shows all six `bf/reads` commits content-identical (`=`);
> `bf/coercion` differs from its backup by exactly the 40 changelog lines and no code; messages,
> authorship and dates preserved.

> **`origin/dev` has not moved.** Re-fetched live during this rewrite: `origin/dev` is `a8888f0d`,
> dated **2026-09-09**, and `git rev-list --count a8888f0d..origin/dev` is **0**. Every branch here
> shares that base and **none of them is drifting from anything.** Recorded because the opposite was
> asserted in passing and turned out to be false — the cached `FETCH_HEAD` was a day old, which is
> the same stale-ref trap the handoff rules already warn about, and it caught the person who wrote
> the rule.
>
> **So the argument for landing these is not a clock.** It is that nine branches deep is a
> review-queue problem on its own terms, that the marginal find is now worth less than the marginal
> landing, and that **nine of the defects in this batch were ones no register entry predicted** —
> which says the register has stopped being the bottleneck.

## 0. Publishing is manual, deliberately

**Nothing in this document pushes, tags remotely, merges or publishes. A human does each of those
steps, so that each one gets reviewed.** Agents and automated sessions prepare branches, commits
and tags **locally** and stop. That is a standing rule for this programme, not a property of this
particular batch — see the execution plan's handoff block.

This matters more than usual here because **pushing some branches publishes artefacts**, and
because the code goes to people who dose insulin using it.

### Which branches are safe to push — measured, not assumed

#### `cgm-remote-monitor`

| target | safe to push? | what happens |
|---|---|---|
| **`dev`** | **NO — publishes** | `.github/workflows/main.yml` job `docker-build`, `if: (github.ref == 'refs/heads/master' \|\| github.ref == 'refs/heads/dev') && github.repository_owner == 'nightscout'`, logs into Docker Hub with `secrets.DOCKER_USER`/`DOCKER_PASS` and **pushes an image** |
| **`master`** | **NO — publishes** | same job, same condition |
| **`chore/nightscout-modernization`** | **yes** | no `push:` trigger matches it. PRs *targeting* it run full CI (`main.yml` and CodeQL both list it under `pull_request`) |
| **any other branch on `origin`** | **yes** | `main.yml` and `codeql-analysis.yml` both trigger on push only for `master` and `dev`. A feature-branch push runs **nothing** |
| **the `bewest` fork remote** | **yes**, lowest footprint | `git@github.com/bewest/cgm-remote-monitor.git`, already configured as remote `bewest` |

**So: push the nine `cgm-remote-monitor` Phase 0 branches to `origin` (or to the fork) and open PRs
against `dev`. Never push the branch *onto* `dev`.** The PR is what gets reviewed; the merge is what
publishes.

> **The CodeQL row above was challenged and is CORRECT — re-measured 2026-09-15.** A later document
> "corrected" it to say CodeQL lists only `[dev, master]`. On
> `origin/chore/nightscout-modernization`, `codeql-analysis.yml` line 17 is
> `push: branches: [ dev, master ]` **and line 19 is
> `pull_request: branches: [ dev, master, chore/nightscout-modernization ]`**. The "correction" was
> produced by reading only the `push:` line. `main.yml` on that branch lists the third branch too,
> and carries four jobs `dev` lacks (`maintained-mongo`, `replica-test`, `browser-test`, plus a
> concurrency group). **The sentence here stands; the correction of it does not.**

*One trap worth knowing about the fork route.* `close-accidental-sync-prs.yml` auto-closes a PR
when **all three** hold: it comes from a fork, **its title matches `sync|merge|update|pull|new`**,
and its diff is empty. A real PR is never auto-closed because the third condition fails — but
several natural titles for this batch contain those words, so if a PR ever vanishes, that is why.

#### `nightscout-connect`

| target | safe to push? | what happens |
|---|---|---|
| **any branch, including `main`** | **yes** | the repo has exactly one workflow, `test.yml`, `on: [push, pull_request]`, `permissions: contents: read`. It runs the suite on Node 22 and 24. No secrets, no registry, no publish |
| **tags** | **yes** | there is **no release workflow at all**. Pushing `v0.0.14` runs the same tests and publishes nothing |

**`npm publish` for the connector is entirely manual.** Nothing automates it, so cutting and
pushing the tag is safe and reversible; the publish is a separate, deliberate human act.

### The review rule this encodes

- **Prepare locally, push a branch, open a PR, let a human merge.** Two of five prescribed fixes in
  the backfix register turned out to be wrong when someone actually ran them, and four register
  entries had claims that did not survive contact. Review is where that gets caught.
- **`dev` and `master` are publication events, not branches.** Treat a push to either as shipping.
- **A release is three separate human decisions** — merge the code, push the tag, publish the
  package — and this batch needs all three, in that order.

## 0b. CHANGELOG.md is a release output. Branches never hand-edit it.

**This is the maintainer's rule, and it is why two branches in this set were rewritten.**

> **`CHANGELOG.md` is generated by GitHub tooling between releases. It is an *output* of the release
> process, not an input to it. No branch in this programme may add to it, edit it, or create it.**

Release notes for this batch live **in this control-surface repository, under `releases/`**, as
release assets:

| path | what it is |
|---|---|
| `releases/cgm-remote-monitor-15.0.9/release-notes.md` | operator-facing notes for the 15.0.9 candidate |
| `releases/cgm-remote-monitor-15.0.9/contents.md` | what is in it, per branch, with the measurements |
| `releases/cgm-remote-monitor-15.0.9/tag-message.txt` | the annotated tag body |
| `releases/cgm-remote-monitor-15.0.9/verification-record.{md,json}` | per-item evidence grade |
| `releases/nightscout-connect-v0.0.14/` | the same three for the connector release |
| `releases/_template/` | the shape a new release directory takes |

Per-PR description text lives in `reports/phase0-pr-bodies/` — one file per branch, named for the
branch.

**Measured after the strip:** none of the nine `cgm-remote-monitor` branches touches `CHANGELOG.md`.
`git diff --name-only origin/dev...<branch> | grep -c '^CHANGELOG.md$'` is **0** for every one of
`bf/alarms`, `bf/auth`, `bf/cache`, `bf/coercion`, `bf/connect-pin`, `bf/food`, `bf/merge`,
`bf/parms` and `bf/reads`. (Reproduced.)

**Three consequences worth stating, because earlier revisions of this document instructed the
opposite:**

1. **`bf/food` no longer needs to avoid creating the file.** The old instruction — "it deliberately
   does not create `CHANGELOG.md` because `bf/reads` and `bf/coercion` both add it" — described a
   collision that no longer exists. Nothing adds it. BF-35's release note belongs in
   `releases/cgm-remote-monitor-15.0.9/`.
2. **"`bf/auth` has no CHANGELOG entry — add one" is withdrawn.** It must not have one. The BF-17
   rotation note and the `replaceOne` narrowing are operator-facing and belong in the release notes
   and in `reports/phase0-pr-bodies/bf-auth.md`.
3. **"Correct the CHANGELOG before the PR" for `bf/reads` is withdrawn** and replaced by: correct
   the *release note*, which is where the too-narrow scope statement now lives. See §4.

## 1. There is no stack. All nine are independent.

The instinct with ten related branches is a stack — each PR based on the last. **Measured, that
would be wrong here, and the one exception that used to exist has been removed.**

**All 36 unordered pairs among the nine `cgm-remote-monitor` branches merge clean, and all nine
merge clean against `origin/dev`.** Reproduced during this rewrite with
`git merge-tree --write-tree` over every pair and against `origin/dev`: **9 clean against dev, 36
pairs, 0 conflicts**, `bf/connect-pin` included. **`bf/coercion` and `bf/reads` are among those 36
and they merge clean with each other.**

**The measurement is not vacuous, and proving that took two attempts — the first control was
mis-scoped and is recorded rather than hidden.**

- **Mis-scoped control (reported as such, per rule 2).** The obvious control,
  `bf/reads.bak-changelog × bf/coercion.bak-changelog`, came back **clean**. That is not evidence
  the harness is blind: `bf/coercion.bak-changelog` **is an ancestor of** `bf/reads.bak-changelog`
  (the backup preserved the stacked shape), so the pair could not conflict. The *ablation* was
  wrong, not the check.
- **Re-scoped control, which fires.** `bf/reads-prerebase × bf/coercion.bak-changelog` exits
  **1** and names `CHANGELOG.md`:

  ```
  CHANGELOG.md
  Auto-merging CHANGELOG.md
  CONFLICT (content): Merge conflict in CHANGELOG.md
  Auto-merging lib/server/activity.js
  Auto-merging lib/server/devicestatus.js
  Auto-merging lib/server/entries.js
  Auto-merging lib/server/profile.js
  Auto-merging lib/server/treatments.js
  ```

  So the harness does detect a conflict when there is one; the 36 clean results are a fact about the
  branches, not about the command.

**`bf/coercion` and `bf/reads` share five files** — `lib/server/activity.js`, `devicestatus.js`,
`entries.js`, `profile.js` and `treatments.js` — **and none of them ever conflicted.** (Earlier
revisions said six by counting "the query path" as a shared file; it is not shared.
`lib/server/query.js`, `query-coercion.js` and `query-coercion.json` are `bf/coercion`'s alone, and
`lib/server/aggregate.js` and `count.js` are `bf/reads`' alone. Reproduced with `comm -12` over the
two name lists.) **The only collision this batch ever had was both branches appending to the same
`### Fixed` heading under `[Unreleased]` in `CHANGELOG.md`, and §0b removed the file from both.**

**A stack costs serial review and serial merge. Buy it only where there is a real dependency.**
After the strip there is **none**, so: **nine independent PRs off `dev`, mergeable in any order**,
plus one independent PR in `nightscout-connect`.

> **What a clean merge does *not* buy you is at §3b.** `bf/coercion` and `bf/reads` compose
> correctly, but that is a separate fact from merging cleanly, and it was established by inspecting
> the merged tree rather than by the absence of a conflict.

## 2. The batch, in the order worth reviewing it

**Order is a review recommendation, not a dependency.** Every one of these can be opened, reviewed
and merged without reference to any other. The ranking is by consequence to a person using the
software.

### First, because it reaches an operator only through a pin move

| branch | repo | what it is |
|---|---|---|
| `fix/connect-timer-jitter` `c1cce2a2` | **`nightscout-connect`** | T0.4 (start jitter) and **BF-34** |
| `bf/connect-pin` `0807eb1c` | `cgm-remote-monitor` | moves the pin to the `v0.0.14` tarball, one file, +1/−1 |

**BF-34 is the highest-value fix in the whole Phase 0 set and it is easy to miss** because it is in
the other repository. `backoff()` merges its options as `{ ...config, ...defaults }` — the spread
order is reversed, so **every value any caller passes is discarded**. All five vendor sources
configure a 2.5-minute retry interval and every one gets the 256 ms default, **586× faster**, with
`use_random_slot` forced `false` so a pool that fails together retries in exact lockstep. Measured:
100 actors delivered the same 800 requests across **3 s before and 67 s after**.

A vendor that is refusing requests gets hammered by every account at once, which is precisely when
it can least afford it — and the behaviour is invisible to the operator whose account is being
rate-limited. **Land this one first if anything is landed first.**

> **BF-34 has a second half that the register entry does not carry, established by the E1 Dexcom
> comparison.** The same `{ ...config, ...defaults }` merge also makes the ceiling **74.6 hours**,
> because `exponent_ceiling` caps the *exponent*, not the *delay*. So the one defect produces a
> retry storm first and a three-day dark window second, and **the dark-window half is the one that
> stops a person's data arriving**. Both halves ship on `dev` today. See
> [E1](../60-research/e1-dexcom-path-comparison-2026-09-15.md) and the register's BF-34.

T0.4 also corrected its own premise: the actors do *not* stay phase-locked, because all four vendor
drivers already spell an 18-second random window into the timestamp they align to. **The start is
the burst, and it does not repeat.**

### Then, because it puts a wrong number in front of a person

| branch | what it is |
|---|---|
| `bf/food` `73495331` | BF-16 and **BF-35**. **Before this lands, `tools/nsschema/code_model.py`'s `SOURCE_ASSERTIONS` must move in the same sitting** — they pin text this branch deletes, so `make schema-code-drift` fails the day it reaches a checked tree. See register BF-16 |

**BF-35 — the bolus calculator's quick-pick chooser resolves the wrong record.** Verified
independently against `origin/dev`:

```js
lib/client/boluscalc.js:648-652   records.forEach(r => { if (r.type == 'quickpick') quickpicks.push(r); });
lib/client/boluscalc.js:654-657   for (var i = 0; i < records.length; i++)          // UNFILTERED
                                    $('#bc_quickpick').append($('<option>').val(i)  // index into records
                                      .text(r.name + ' (' + r.carbs + ' g)'));
lib/client/boluscalc.js:579       var qp = quickpicks[parseInt(qpiselected)];        // FILTERED
lib/client/boluscalc.js:580       foods = JSON.parse(JSON.stringify(qp.foods));      // the carb source
```

The option's **label** comes from `records[i]`; the **foods the calculator totals carbs from** come
from `quickpicks[i]`. Different records, no mismatch reported. The list also offers plain foods that
are not quick picks at all, and selecting a late option throws because `qp` is `undefined`.

**This is the most consequential defect found in Phase 0.** Everything else in this batch returns a
wrong answer to a query or fails to raise an alarm. This one puts a *carbohydrate total the user did
not choose* into a bolus calculation, under a label they did read.

**It has shipped in every release since `3457de5b` (2017-10-16) — eight years.** The same commit
removed the only caller of `/api/v1/food/quickpicks`. In `loadFoodDatabase` the type filter moved
*into* the loop and stayed correct; in `loadFoodQuickpicks` it became a separate pass and the loop
kept iterating the original array. Before that commit the source *was* the quickpicks endpoint,
where every record was a quick pick — **so the code was right when written and made wrong by a
change that did not appear to touch it.** It only bites a site whose food database holds at least
one plain food, which is why it survived.

*A detail worth keeping*: line 655 carries
`/* eslint-disable-next-line security/detect-object-injection */ // verified false positive`.
Somebody examined that exact line, correctly cleared it of the thing the linter flagged, and did not
see the indexing bug beside it.

**BF-16 confirmed, and its reachability claim was wrong** — the fourth such entry. The lexicographic
`position` sort was real and **reached nobody**: `/api/v1/food/quickpicks` has no consumer in the
tree. The order users actually see was broken by the chooser not sorting at all. The type ambiguity
is real and is now reproduced over HTTP rather than read. A **fourth** site the entry did not name,
`restoreBoolValue`, mapped `=== 'true'` and so turned a real boolean `true` into `false`, silently
un-hiding a hidden quick pick on every editor load — the only one of the four *losing* a setting
rather than failing to read one.

**What whoever lands this branch needs to know:**

1. **The release note is required and it does not go in the branch.** The quick-pick list changes
   contents *and* what selecting an entry does, so anyone who had learned to work around the
   mislabelling will see different behaviour. Write it into
   `releases/cgm-remote-monitor-15.0.9/release-notes.md`. See §0b.
2. **A drift tripwire fires when this lands, and it is not a breakage.**
   `tools/nsschema/code_model.py`'s `SOURCE_ASSERTIONS` deliberately pins the quoted `'false'` in
   `lib/server/food.js` and `record[key] === 'true'` in `lib/food/food.js`, so that fixing them
   *forces* the food model to be revisited. Both are gone on `bf/food`, so `make schema-code-drift`
   will fail the day this reaches `externals/work/crm-seam` or `externals/cgm-remote-monitor-official`.
   The anchors were left alone because they are still true of both trees today; what to replace them
   with is written into BF-16.

### Then, because the user ends up with no page at all

| branch | commits | what it is |
|---|---|---|
| `bf/parms` `eb0bc918` | 3 (`522c6ffb`, `c9a7a21c`, `eb0bc918`) | **BF-37**, **BF-38**, **BF-39** — **corrected 2026-09-15**: this row had the last two commits and their entries transposed. Measured `git log origin/dev..bf/parms`. BF-37's test is among the 52 neither local script runs — use `npm test` |

**BF-37 — a bare flag in the URL stops the page loading.** Verified against `origin/dev`:

```js
lib/client/browser-utils.js:46   // eslint-disable-next-line no-useless-escape
lib/client/browser-utils.js:47   params[item.split('=')[0]] = item.split('=')[1].replace(/[_\+]/g, ' ');
lib/client/index.js:48           client.init = function init (callback) {
lib/client/index.js:50             client.browserUtils = require('./browser-utils')($);
lib/client/index.js:52             var token = client.browserUtils.queryParms().token;   // first use of a parsed param
```

`[1]` is read without checking it exists. `?debug`, a trailing `&`, a doubled `&&`, a lone `?` —
each throws `Cannot read properties of undefined (reading 'replace')`, **four lines into
`client.init`, before anything is wired up**. No chart, no socket, nothing on screen but the loading
message and a TypeError in a console nobody is reading.

**Placed behind BF-35.** It is not a wrong number, so not BF-35's category — but it is a
total failure to load, reachable by accident (a link with a trailing ampersand; following the
`?mute=true` instruction as `?mute`), and it is the only defect in this batch where the user ends up
with **no working page at all**.

> *The counterweight, recorded so the ordering is not mistaken for a claim about harm:* this failure
> is **self-announcing**. The user sees a page that never loads and knows the tool is not working.
> BF-35 hands them a number and tells them nothing. A caregiver with a blank page at 3 a.m. is a
> serious problem; a caregiver with a confidently wrong carb count is a different and worse one.

The fix reads a valueless parameter as the empty string, which is what both existing callers already
treat as absence (`|| clientToken`, `!== 'true'`). **The split itself is untouched** — including
truncation at a second `=`, a latent issue for a token containing `=`, deliberately left alone with
a test asserting well-formed queries parse byte-identically.

**BF-39 — the `_`→space replacement corrupts access tokens, and nothing notices.** Third commit
(`eb0bc918`). The `+`→space half of `/[_\+]/` is correct; `+` means space in a query string. The
`_` half is not correct in any encoding. `storage.js:190` strips with `\W`, which **keeps**
underscores, so a subject named `mom_phone` gets the token `mom_phone-89e148ac…` and `queryParms`
hands the client `mom phone-89e148ac…`.

**Measured, not reasoned about: both spellings authorise, 200.** `checkToken`
(`storage.js:279-289`) splits on `-`, takes the **last** segment as the prefix, and matches
`subject.digest.indexOf(prefix) === 0` — so the corruption lands entirely in the part nothing reads.

**A real corruption absorbed by a leniency nobody chose — BF-16's shape again**, where two ends
disagree and a third thing hides it. Filed low and fixed as one character, because the point is
**removing the accidental coupling, not the symptom**: this is the kind that breaks when either end
changes for an unrelated reason, and it is worth being written down before somebody tightens
`checkToken`.

*Two things deliberately not done, recorded in the entry rather than left implicit:* **no
`decodeURIComponent`** — it throws on a malformed percent sequence, at the exact call site BF-37
exists to stop throwing at, so a correct-looking decoder there would reinstate BF-37 in a new
costume; and **the second-`=` truncation stays**, because a token cannot contain one.

**BF-38 — `%1` ate `%10`.** Substitution loops forwards and `%1` is a prefix of `%10`, so the first
pass rewrites the `%1` *inside* `%10` and leaves a stray `0`: `'%1|%9|%10|%11'` →
`one|nine|one0|one1`. The same prefix-ordering trap as BF-16's text `position`. **Latent** — no
catalogue uses more than `%3` — so it goes at the back. Worth fixing because it would bite the first
translator to write a tenth substitution, silently, and **it would look like the translation file
was wrong rather than the substituter.**

### Then the query and read paths

| branch | commits | what it is |
|---|---|---|
| `bf/coercion` `ab197bf8` | 1 | T0.5 — schema-driven query coercion. The largest single change in the batch |
| `bf/reads` `2ecfeb53` | 6 | BF-01, BF-05, BF-13, BF-14, BF-15, BF-33 |

**These two used to be a stack and are not any more.** They merge clean with each other and with
everything else, and **they compose correctly** — but that composition is a property of the *pair*,
not of either PR, and it is the one thing in this batch a reviewer cannot see from a single diff.
**§3b is the check that covers it, and it survives the dissolution of the stack.**

`bf/reads`, in branch order:

```
4772b983  count/:storage/where counted nothing because it built its filter from the defaults   (BF-01)
3b588098  Every count request printed its filter, and the filter's values, to stdout           (BF-05)
5a5269a3  v3 paging lost and repeated documents whenever the whole sort chain tied
12207df3  v3 answered a dotted ?fields= with an empty document and HTTP 200
06b133a7  ?count=0 asked for no documents and was answered with the whole collection
2ecfeb53  v3 ?limit=0x10 removed the bound and returned the whole collection                   (BF-33)
```

**Ordering constraint inside the branch: BF-05's commit must follow BF-01's.** They share two files
— `lib/server/aggregate.js` and `tests/api.count-where.test.js` — and the branch is already in that
order. (Reproduced with `git show --stat` on both commits. Earlier revisions named `4a398d47`/
`c8fb536b` and then `af717c8f`/`1d0064bd`; **both pairs are pre-strip and no longer exist on the
branch**. The live pair is `4772b983` then `3b588098`.)

**Every other commit on every branch lands alone.**

### Then availability, not correctness

| branch | what it is |
|---|---|
| `bf/merge` `b06c6faf` | **BF-36**. One lib file, one new test file. **Its test is one of the 52 files neither local script runs** — use `npm test`, not `npm run test:unit`; see register BF-53 |

**BF-36 — `mergeTreatmentUpdate` reads past the array it is splicing.** Verified against
`origin/dev`:

```js
lib/client/receiveddata.js:99    var m = cachedDataArray.length;   // captured ONCE
lib/client/receiveddata.js:104     cachedDataArray.push(no);       // grows it
lib/client/receiveddata.js:107     for (var j = 0; j < m; j++) {   // stale bound
lib/client/receiveddata.js:109       if (no._id === cachedDataArray[j]._id)   // throws
lib/client/receiveddata.js:111         cachedDataArray.splice(j, 1);          // SHRINKS it
```

A `remove` splices the array while `m` stays put, so the next received item that matches nothing
walks `j` past the end and dereferences `undefined._id`. It needs **a splice followed by a miss**,
which is why it survived: two removes do not do it (the second matches and breaks first), and an
insert does not either (`push` grows the array *past* the bound rather than below it). Deleting a
treatment and editing another that is outside the client's two-day window does.

**Severity is medium, and the reasoning is worth keeping because it sets the priority order.** The
throw escapes `receiveDData` into `dataUpdate`, which has no `try`/`catch`, so the page stops
advancing until reloaded. But it is **not silent**: `updateClock` runs on its own `setTimeout`
chain, so the time-ago indicator keeps working and marks the page stale.

> **BF-35 tells you a wrong thing. BF-36 stops telling you things, visibly.** That is the
> distinction that puts one at the front of this batch and the other with the availability entries.

**The two functions had drifted apart.** `mergeDataUpdate`, thirty lines up in the same file,
**re-reads** its bound (`l = newArray.length`, `:25`) before its second loop and walks its purge
backwards. `mergeTreatmentUpdate` does neither. Both are exported with `//expose for tests` and
**neither had a single test**; both are now pinned.

### And the rest, in any order

| branch | what it is |
|---|---|
| `bf/alarms` `5dcf783f` | BF-28, BF-29, BF-31. Zero file overlap with anything else. Smallest and most reviewable |
| `bf/cache` `4f86bab1` | T0.2 and T0.3. Self-contained in `cache.js`/`dataloader.js`/`api/entries` |
| `bf/auth` `64db1f35` | BF-17 and BF-30. **Security — get a human on this one first** |

## 2b. The connector release, in detail

#### DONE 2026-09-15 — tag cut and pin moved, locally, nothing pushed

**The pin move was framed as a security fix. That framing is withdrawn below and the rationale that
survives is nameability, reviewability and three behavioural fixes.** See the correction two
sub-sections down, and the resolved contradiction immediately after the commit list.

`dev` pinned `234d47c8` — an untagged commit on an **unmerged feature branch**. Measured against
the `v0.0.13` tag, that pin contains **exactly one commit**. These six are *not* in it:

```
9fa2c3c  Prevent Dexcom credentials and sessions from reaching runtime logs
5349d47  Keep MiniMed credentials and patient data out of runtime logs
77e2396  Keep internal output payloads out of runtime logs
8406edf  Preserve MiniMed glucose and measurement-time status contracts
51b6e6e  Release connector listeners and settle output waits on stop
c1cce2a  BF-34 and start jitter
```

So **15.0.9 as currently pinned ships without three log-redaction fixes.**

> **CONTRADICTION FOUND AND RESOLVED HERE, 2026-09-16 (adversarial review).** This paragraph used to
> continue: *"Making debug logging opt-in (`234d47c`, the one commit the pin does have) narrows when
> those leaks can happen; it does not stop them happening when an operator turns logging on to
> diagnose a problem."* That is **the same sentence this section later calls refuted** — see the
> two-corrections block below — so the document was asserting in its own voice, three paragraphs
> earlier, a claim it then withdrew. Reproduced with `git show --stat 234d47c8`: that commit is
> **18 files, +379/−146**, and it *rewrites* the logging call sites rather than gating them, so
> "it only narrows *when* the leak happens" is wrong about what the commit does.
> **What survives:** `dev`'s pin genuinely lacks the three named redaction commits, which is a real
> coverage gap — but `dev`'s pin is among the *safest* in flight and `master`'s `v0.0.13` is the
> leaking one. **The pin move is not primarily a security fix.** The rationale that stands is
> nameability, reviewability, BF-34, the MiniMed contract fix, the listener-release fix, and
> v0.0.14 being the first ref carrying both redaction lines.

**What was done, all local:**

| repo | branch / ref | change |
|---|---|---|
| `nightscout-connect` | `release/v0.0.14` → `649a7de2` | version `0.0.13` → `0.0.14`; **annotated tag `v0.0.14`** (also `649a7de2`) |
| `cgm-remote-monitor` | `bf/connect-pin` → `0807eb1c` | pin → `…/archive/refs/tags/v0.0.14.tar.gz` |

`v0.0.13` (`b394411a`, `origin/main`) **fast-forwards** to the release — no merge to reconcile.

**One thing deliberately left undone, and it must not be papered over.** `package-lock.json` is
**not** updated. Its `integrity` is a hash over the tarball GitHub generates, which does not exist
until the tag is pushed, and a hash invented locally would break `npm ci` for everyone. Leaving the
lock on the old SHA makes `npm ci` fail **loudly** as out-of-sync, which is the correct failure.
**Regenerate with `npm install` once the tag is pushed, in the same PR.**

**To publish (maintainer, in order):**

```bash
# 1. connect: fast-forward main and push the tag
git -C externals/nightscout-connect push origin release/v0.0.14:main
git -C externals/nightscout-connect push origin v0.0.14
npm publish                      # optional but see below

# 2. crm: regenerate the lock against the now-real tarball, then push
cd externals/work/crm-bf-connect-pin && npm install   # updates package-lock.json
git commit -am "Regenerate the lock against connect v0.0.14"
```

**`master` is a separate problem, but not the one this paragraph used to describe.**

> **CORRECTED 2026-09-15, measured three times independently.** `origin/master:package.json` pins
> `https://github.com/nightscout/nightscout-connect/archive/refs/tags/v0.0.13.tar.gz`. It does
> **not** depend on `"^0.0.12"` from npm, and has not since commits `a91e8ee4` and `561974de`
> replaced that pin on 2026-07-07. The `^0.2.12` that *does* appear on `master` is
> **`share2nightscout-bridge`**, a different package; the two were conflated.
>
> Three consequences, and they strengthen rather than weaken the section's conclusion:
>
> 1. **There is no npm semver range for the connector anywhere in the tree.** Every pin is a tarball
>    URL, so the shapes are two (tag tarball, commit tarball), not three.
> 2. **`master` is already on v0.0.13**, so `bf/connect-pin`-style work on it is a one-tag-step bump.
> 3. **The delivery mechanism is a TAG PUSH, not an `npm publish`.** The conclusion that merging in
>    the connect repository ships BF-34 to nobody survives and is in fact stronger — npm's caret on
>    a `0.0.z` version matches that version exactly and would have floated nothing either.

#### BF-34 currently reaches nobody, and fixing that is a release decision

`fix/connect-timer-jitter` is based on `b77e5bb`, **not** on `dev` and not on the connect repo's
`main`. `b77e5bb` is the exact commit `chore/nightscout-modernization` pins. **There are FOUR
distinct pins in flight, not three** — measured 2026-09-15 by reading `package.json` on every ref:

| cgm-remote-monitor ref | `nightscout-connect` pin | commits past v0.0.13 |
|---|---|---|
| `master` (15.0.8, **what operators run**) | **v0.0.13 tag** tarball | 0 |
| `dev` (15.0.9 candidate) | commit **`234d47c8`** | 1 |
| `chore/retire-jsdom`, `chore/build-runtime-separation`, `chore/compose-mongodb6` (parcels 1-3) | **v0.0.13 tag** tarball | 0 |
| `chore/mime-exposure-review` (parcel 4) | commit **`c962a13f`** | 5 |
| `chore/nightscout-modernization` (parcel 5) | commit **`b77e5bb`** | 9 |
| `bf/connect-pin` (local, unpushed) | **v0.0.14 tag** tarball | 11 |

**And the two mitigations are split across the two release trains.** `dev`'s `234d47c8` carries the
debug-logging-opt-in rewrite — which *deletes* the leaking call sites, an 18-file change, not merely
a gate — but none of the three named log-redaction commits. Parcel 4's `c962a13f` carries the
redaction and the MiniMed contract fix but **not** the opt-in rewrite, and **still leaks
LibreLinkUp credentials**. Verified by `merge-base --is-ancestor`: `234d47c8` is **not** an ancestor
of `c962a13f` and `c962a13f` is not an ancestor of `234d47c8` — **they are incomparable**,
converging only at parcel 5. So "the line is linear and there is no divergence to reconcile" is true
of `dev` and parcel 5 and **false of the pair that matters**. **v0.0.14 is the first ref carrying
all seven post-v0.0.13 commits**, and moving `dev` to it is what reconciles them.

> **Two further corrections to widely-repeated statements.** (a) Moving `dev`'s pin forward pulls in
> **11** commits (7 non-merge), not 9; nine is the count from v0.0.13 to parcel 5's pin, a different
> span. (b) `master`'s pin is the **leaking** one and `dev`'s is among the safest — the opposite of
> how the security rationale has been framed. **`bf/connect-pin`'s commit message `0807eb1c` carries
> the refuted rationale** ("Making logging opt-in narrows when those leaks can happen; it does not
> stop them happening…") and should be amended before the PR is opened, because commit messages are
> permanent. The rationale that survives is: nameability — an untagged commit cannot go in release
> notes — reviewability, BF-34, the MiniMed contract fix, the listener-release fix, and v0.0.14 being
> the first ref with both redaction lines. See the register's **BF-42** and
> [connector pin consolidation](../40-migration/connector-pin-consolidation-2026-09-15.md).

So merging in the connect repository **ships BF-34 to nobody**. It reaches an operator only when a
cgm-remote-monitor `package.json` pin moves.

**This collides with an open release decision that predates Phase 0.** The release-readiness
review already flagged that `dev` pins an *untagged commit SHA*, which is reproducible but
unreviewable and leaves the release with no connector version to name in its notes.

**One action settles both**: cut a `nightscout-connect` release containing BF-34, publish it, and
have `dev` pin **the tag** rather than a SHA. That ships the highest-value Phase 0 fix, gives
15.0.9 a nameable connector version, and retires the untagged-SHA objection — and it is the
"minutes-long task" the readiness review described.

Note that moving `dev`'s pin forward also pulls in the intervening commits (quiet logging, stop
cleanup). That is a release-content decision, not a mechanical bump, and it is the maintainer's.

> **`bf/connect-pin` is also load-bearing for the MiniMed retirement, which earlier revisions of
> this document did not know.** The E2 comparison reproduced that the **pins operators can reach
> today are the bad ones for CareLink**: neither `v0.0.13` (which `master` pins) nor `234d47c8`
> (which `dev` pins) has the `sg !== 0 && kind === 'SG'` gap-sentinel filter, so a CareLink gap is
> ingested as `sgv 0`; and while a `0` is the newest entry, `lib/plugins/simplealarms.js` skips the
> entire high/low evaluation because of `lastSGVEntry.mgdl > 39`. That is fixed only from `c962a13f`
> onward — i.e. in the parcels and in **v0.0.14**. `dev` already prints a boot-time deprecation
> warning pointing operators at Connect, so **live advice is currently landing on the bad pin.**
> **`bf/connect-pin` should land before any operator is advised to migrate MiniMed.** See
> [E2](../60-research/e2-medtronic-path-comparison-2026-09-15.md).
>
> **But v0.0.14 is not a clean bill of health for MiniMed, and this document should not read as if
> it were (added 2026-09-16, adversarial review).** E2 reproduced, driving the connector's own
> `lib/builder.js` and `lib/machines/*` with only the network stubbed, that
> `lib/sources/minimedcarelink/index.js` guards `data.medicalDeviceFamily` and then does
> `data.markers.filter(...)` **unguarded**: a CareLink payload with no `markers` key throws a
> synchronous `TypeError` that escapes `transformService` before `Promise.resolve`, so `onError`
> never sees it — and cgm-remote-monitor registers no `uncaughtException` handler, so the Nightscout
> process dies. **Independently confirmed here, read-derived:** `var markers = data.markers` followed
> by `markers_to_treatment(markers)` is present at `v0.0.13`, `234d47c8`, `c962a13f` **and
> `v0.0.14`** (`git show <ref>:lib/sources/minimedcarelink/index.js`). Whether a real CareLink
> payload ever omits `markers` is one of the things no account on this machine can settle; the
> retired package's own recorded payloads have no `markers` key, and every occurrence in the
> connector's test suite is an injected `markers: []`, so the absence has **zero coverage**.
> `bf/connect-pin` fixes the gap-sentinel and `created_at` defects; it does **not** fix this one.

**Release note is BF-34's, and it is counter-intuitive**: a vendor outage will now appear to
recover *more slowly*, because the connector has stopped retrying in a burst that could not have
worked. BF-08 needs none — both jitter windows default to `0`, so nothing changes for anyone who
does not set them.

## 3. Commands

Nothing below pushes. Run them from `externals/cgm-remote-monitor-official` (or any worktree on
that repo).

```bash
# Confirm each branch still merges clean against dev, and against every other branch.
BR="bf/alarms bf/auth bf/cache bf/coercion bf/connect-pin bf/food bf/merge bf/parms bf/reads"
for b in $BR; do
  git merge-tree --write-tree origin/dev $b >/dev/null 2>&1 \
    && echo "clean  $b" || echo "CONFLICT $b"
done
for a in $BR; do for b in $BR; do [ "$a" \< "$b" ] || continue
  git merge-tree --write-tree $a $b >/dev/null 2>&1 || echo "CONFLICT $a $b"
done; done
# Measured 2026-09-15 (post-strip): 9 clean against dev, 36 pairs, 0 conflicts.

# Confirm no branch hand-edits the release output (§0b).
for b in $BR; do
  printf '%-18s %s\n' "$b" "$(git diff --name-only origin/dev...$b | grep -c '^CHANGELOG.md$')"
done
# Measured: 0 for all nine.

# CONTROL, so the loop above is not taken on trust. Use the PRE-STRIP pair:
git merge-tree --write-tree --name-only bf/reads-prerebase bf/coercion.bak-changelog \
  >/dev/null 2>&1 && echo "CLEAN -- harness vacuous" || echo "CONFLICT -- harness is live"
# Measured: CONFLICT, naming CHANGELOG.md.
# NOT this pair -- it is mis-scoped, because coercion.bak is an ANCESTOR of reads.bak:
#   git merge-tree --write-tree bf/reads.bak-changelog bf/coercion.bak-changelog   # always clean
```

Then push each branch and open **nine PRs, every one based on `dev`**. There is no retargeting step
and no branch in this set is the base of another.

## 3a. DONE — the CHANGELOG strip and the un-stacking

**Done locally at the maintainer's instruction. Nothing pushed. No code changed.**

| branch | before | after | what happened |
|---|---|---|---|
| `bf/coercion` | `88d1f8a4` | **`ab197bf8`** | 40 CHANGELOG lines removed; 9 files, code only |
| `bf/reads` | `0d19bb31` | **`2ecfeb53`** | changelog-only commit dropped, **and un-stacked from `bf/coercion`, rebased directly onto `origin/dev`** |

**Safety refs kept until the PRs merge**, then delete: `bf/coercion.bak-changelog` (`88d1f8a4`),
`bf/reads.bak-changelog` (`0d19bb31`), `bf/reads-prerebase` (`824380a0`).

**Verified at the time of the strip**: `git range-diff` shows all six `bf/reads` commits
content-identical (`=`); `bf/coercion` differs from its backup by exactly the 40 changelog lines and
no code; messages, authorship and dates preserved; targeted tests pass (`bf/reads` 5+13+3+6+8 = 35
passing, 0 failing; `bf/coercion` `query` 28 passing).

**Re-verified during this rewrite** (reproduced): `git merge-base --is-ancestor bf/coercion bf/reads`
is **false** — the branches are siblings, both with merge-base `a8888f0d` against `origin/dev`.
`bf/reads` carries **6** commits, not the 8 the pre-strip revision listed.

> **What is now stale everywhere else.** Any text that says `bf/reads` is based on `bf/coercion`;
> any instruction to run `git rebase --onto bf/coercion origin/dev bf/reads`; any list of
> `bf/reads`' commits beginning with `88d1f8a4`; the A–I lettering; "eight independent PRs and one
> two-deep stack"; and the claim that the two branches share six `lib/server` files (it is five).

## 3b. A clean textual merge is not a correct merge — and this check survives the dissolution

**This section is no longer about a merge conflict.** It never was about `CHANGELOG.md`; that was
the *other* interaction, and it is gone. What it is about is that `bf/coercion` and `bf/reads` are
**both rewriting query construction**, and `merge-tree` reporting no conflict across their five
shared `lib/server/*.js` files is a statement about hunks, not about behaviour.

**The specific interaction, stated precisely, because two different wrong versions of it are in
circulation:**

- **`bf/coercion` supplies the `collection:` keys.** It adds `collection: 'entries'`,
  `'treatments'`, `'devicestatus'`, `'profile'` and `'activity'` to each collection's `queryOpts`,
  and teaches `lib/server/query.js` to type a filter from that collection's schema
  (`opts.walker = opts.collection ? { } : { date: parseInt, sgv: parseInt }`).
- **`bf/reads` supplies the call.** BF-01 changes `lib/server/aggregate.js` from
  `find_options(opts)` — no options at all, hence the legacy default walker — to
  `api.query_for(opts)`, the collection's own builder.
- **Neither branch alone closes the gap, and that is the whole point.**

**Reproduced, by computing the merged tree rather than reading either branch** —
`git merge-tree --write-tree bf/coercion bf/reads` → tree `93b50740`, then reading the files out of
that tree:

| ref | `aggregate.js` builds the filter with | `devicestatus.queryOpts` | count path typed? |
|---|---|---|---|
| `origin/dev` | `find_options(opts)` | `{ dateField: 'created_at' }` | **no** |
| `bf/coercion` alone | `find_options(opts)` | `{ collection: 'devicestatus', dateField: 'created_at' }` | **no** — the key exists, nothing consults it |
| `bf/reads` alone | `api.query_for(opts)` | `{ dateField: 'created_at' }` | **no** — the call exists, there is no collection to name |
| **merged tree `93b50740`** | **`api.query_for(opts)`** | **`{ collection: 'devicestatus', dateField: 'created_at' }`** | **yes** |

**So the composition is correct, and it is correct only in combination.** All five collections name
themselves on the merged tree (`entries`, `treatments`, `devicestatus`, `profile`, `activity`), and
`aggregate.js` routes through `query_for`, so `collection:` reaches `query.js` on the count path.

**What that leaves, and it is why this section stays in the document:**

1. **An interim window, not a follow-up.** Between the two merges the count path is still untyped.
   If `bf/coercion` lands first, `count/.../where` on `devicestatus` is *exactly as broken as it is
   on `dev` today* until `bf/reads` lands, and the `collection:` keys sitting in the tree make it
   look fixed. **Do not mark BF-01 or T0.5 closed on the strength of one merge.** This is not a
   reason to re-stack the branches — a stack would serialise review for a property a single check
   confirms in seconds.
2. **The verification step both PRs need and neither gets alone.** Run the `query` and `count`
   suites against the *merged* tree, and check the `find[...]` cases from `bf/coercion`'s release
   note through the endpoints `bf/reads` touches. This is cheap and it is the only place in this set
   where the merge itself can be wrong.
3. **The named follow-up that genuinely survives** is at §5.1: **there is no end-to-end assertion
   that a numeric filter on `count/devicestatus/where` returns rows on the merged tree.** The table
   above is a source-level reproduction on the real merged tree — stronger than the reading it
   replaces, still short of a request-and-response.

> **Evidence grade, per this document's own rule (§4b).** The table above is **reproduced**: the
> merge was executed and the file contents were read out of the resulting tree object. It is *not*
> an end-to-end run. The earlier revision of this section asserted the same conclusion as
> **read-derived**, from a quotation of `entries.js` on the then-stacked `bf/reads`; that quotation
> was accurate but it described a branch shape that no longer exists, so the conclusion needed
> re-establishing rather than re-copying.

### The `$exists` claim that used to block this branch — DISCHARGED, and why it must stay written down

`bf/coercion`'s `CHANGELOG.md` used to tell operators something false. Lines 35-39:

> *"`find[sgv][$exists]=true` became `$exists: NaN`, which MongoDB reads as **false**, so the query
> returned exactly the records you did not ask for."*

**Measured 2026-09-15 against seven live `mongod` instances (3.6.8 and 7.0.43, identical on all
seven): MongoDB reads `{$exists: NaN}` as TRUE.** Numeric truthiness is `value != 0`, and
`NaN != 0`. The query returned exactly the records you **did** ask for. The wrong reading came from
`mingo`, the D8 oracle, which applies JavaScript truthiness — a limit on that oracle nothing had
recorded.

**The block is discharged twice over**: the CHANGELOG no longer exists on either branch (§0b), and
the corrected version is already written into
`releases/cgm-remote-monitor-15.0.9/contents.md` and `release-notes.md`, and into
`reports/phase0-pr-bodies/bf-coercion.md`. **It stays written down here because the release notes
are still to be generated, and this is precisely the sentence that would be re-derived from the
commit history by anyone who did not read this far.**

**What the release note must say instead**, all of it measured:

- The coercion of operator **operands** was wrong and the fix is right — that argument does not
  depend on which way MongoDB read the result.
- What it genuinely broke is **`$regex`**: `{$regex: NaN}` is a **server error**
  (*"$regex has to be a string"*), so `find[sgv][$regex]=...` returned HTTP 500 and now returns an
  empty 200.
- **`$exists=false` is wrong before *and* after this branch**, on every field, because the string
  `"false"` is truthy to MongoDB too. It is filed as **BF-40** and is **not** fixed here. A release
  note that implies `$exists` filtering is now correct would be its own defect.

See the register's BF-32 (refutation) and BF-40 (the residual).

## 4. What each PR description needs

Every one of these changes what an operator sees. The register's rule 3 applies: *release-note the
behaviour changes*. **The text goes in `reports/phase0-pr-bodies/<branch>.md` and in
`releases/cgm-remote-monitor-15.0.9/`, never in `CHANGELOG.md` (§0b).**

- **`bf/alarms`** — states plainly that `insulinage`'s urgent alarm **starts firing for operators
  who have never received it**. That is the sentence to put first. Needs a maintainer's explicit yes.
- **`bf/cache`** — a performance change that also **removes a dead write** in `dataloader.js`. Say
  that the T0.3 gate (`< 1 ms`) was **not met** (2.66 ms) and why the remainder was left: 98 % of it
  is devicestatus, and taking it needs proof no plugin writes to a device-status document.
- **`bf/auth`** — two security fixes. Must carry the BF-17 remediation note: **a code fix does not
  invalidate tokens already written**, because the token is deterministic in `_id`, `name` and the
  enclave key. Rotation is the operator's action, and the PR should say which options exist.
  **And its third change needs its own line**: the branch narrows subject and role storage to an
  allow-list, written with `replaceOne`, so a field a third-party administration tool has stored is
  destroyed on the next edit. **It narrows a loss that already exists** rather than introducing it —
  `dev`'s `save()` is already a `replaceOne` of a `pick()`ed object, so an admin-UI edit destroys
  `notes` and `created_at` today; see register **BF-47**. But it is still **the one irreversible
  change in this batch**, a code revert does not recover the data, and it is what makes `bf/auth` a
  major rather than a minor. It needs an explicit maintainer yes.
  *(The old instruction here — "`bf/auth` has no `CHANGELOG.md` entry at all … Add one" — is
  withdrawn. It must not have one. The rotation note and the `replaceOne` narrowing go in the
  release notes and the PR body.)*
- **`bf/coercion`** — queries that returned nothing start returning rows; decimal bounds stop
  rounding down. **Do not restate the refuted `$exists` sentence** — see §3b.
- **`bf/food`** — the quick-pick list changes contents *and* what selecting an entry does. Anyone
  who learned to work around the mislabelling sees different behaviour.
- **`bf/reads`** — `?count=0` was answered with the whole collection. **Six** new restrictions
  beyond the defect, not two: `0`, `0x10`, `2.5`, `-3`, `1e2` and `abc` all now return `400`, plus
  integers above `MAX_SAFE_INTEGER`. (`1`, `10`, `" 5 "`, absent and empty are unchanged.) All six
  must be called out as restrictions.
  **And the scope is wider than the branch's own note used to state.** The withdrawn CHANGELOG block
  listed read routes only. The validator is `app.use`'d on the whole API v1 app **before every
  router**, so it also covers `/treatments`, `/profile`, `/devicestatus`, `/notifications`,
  `/activity`, `/food`, `/status`, `/alexa`, `/googlehome` — and **writes** as well as reads: a
  `POST /api/v1/treatments?count=0` that previously succeeded now returns `400`. **A breaking change
  documented more narrowly than it behaves is worse than one documented plainly**, because the
  operator who reads the note concludes they are unaffected. One mount point is **not** covered:
  `/experiments` is mounted before the validator. **Fix this in the release note and the PR body,
  not in a CHANGELOG.**
- **`bf/merge`** — the page stops advancing until reloaded; the time-ago indicator keeps working and
  marks it stale, so it is visible rather than silent.
- **`bf/parms`** — a bare flag in the URL stopped the page loading entirely. Also note the token
  corruption (BF-39) is invisible today only because `checkToken` is lenient.
- **`bf/connect-pin`** — amend the commit message first (§2b), then describe the pin move as
  nameability plus BF-34 plus the MiniMed contract fix, and say that `package-lock.json` must be
  regenerated in the same PR once the tag is pushed.
- **`fix/connect-timer-jitter`** — the counter-intuitive one: a vendor outage will appear to recover
  *more slowly*, because the connector has stopped retrying in a burst that could not have worked.

## 4b. Which entries failed, and the one thing they have in common

Five backfix-register entries had claims that did not survive contact with running code:

| entry | what was wrong |
|---|---|
| **BF-12** | `entries.js` coerces `rssi`, never `rawbg`. A mis-transcription; the entry was **invalid** |
| **BF-31** | "reaches alarm text" does not hold — the catalogue is loaded once at boot |
| **BF-14** | the **prescribed fix** was itself defective; copying it would have spread an unbounded read |
| **BF-16** | the sort defect was real and **reached nobody**; the endpoint has no consumer |
| **BF-03** | closes for two of its four collections; the other two have nothing to fix |

Plus **BF-30**, whose preferred fix measured as a net regression, and **BF-08**, where half the
premise was wrong.

**All of them were derived from reading the source. Not one entry that began with a reproduction
has had to be retracted.**

That is not an argument for fewer entries — **reading found all five, and four of them were real
defects sitting next to a wrong explanation.** It is an argument for marking which kind each entry
is, so a later reader knows whether "the fix is X" has been executed or merely reasoned. A
suggested fix is a hypothesis until someone runs it, and twice here the hypothesis would have made
things worse.

## 4c. The cheapest audit surface in the tree is the suppression list

BF-35 and BF-36 were both found by the same route, and it generalises.

`boluscalc.js:655` and `receiveddata.js:101`/`:108` each carry
`/* eslint-disable-next-line security/detect-object-injection */ // verified false positive`.
In every case somebody examined that exact line, correctly cleared it of **the thing the linter
flagged**, and did not see the defect beside it.

> **A suppression records that *one* question was asked and answered — and then reads like a record
> that the line is fine.**

There are **34** such suppressions in `lib/`. They are pre-selected as places a human already found
confusing *and* annotated with which question was not the interesting one. Reading all 34 turned up
one further defect (BF-36) and **nothing else** — the other 32 index the array their bound came
from, or guard a keyed lookup with `hasOwnProperty`. The negative result is worth recording: the
surface is now audited for this category.

**The sharpest contrast is inside `boluscalc.js` itself.** Its **food-database** chooser filters
with `continue` inside a single loop over `foodlist` and appends `.val(i)`, so the index stays
valid. Its **quick-pick** chooser filtered into a second array and did not. Same file, same author,
same pattern, opposite outcome.

**Only `detect-object-injection` was audited.** `detect-non-literal-fs-filename`,
`detect-possible-timing-attacks` and `no-cond-assign` are untouched and are the obvious next pass.

### An ablation that kept passing was the finding

Worth propagating, because it is the failure mode the non-vacuity rule does not by itself catch.
Two of three ablations for BF-36 **did not reproduce the defect, and the tests rightly kept
passing** — the first moved the length capture *inside* the outer loop, where it is recomputed and
harmless; the second edited the first matching loop in the file, which belongs to
`mergeDataUpdate`. Only the third, scoped to the right function with both halves applied together,
failed with the production error.

**The arm that kept passing is what said the ablation was wrong, rather than the test.** A green
break is not automatically a vacuous check; it can equally be a break that did not break anything.
Distinguishing the two is the whole skill.

> **A third instance, added by this rewrite, in §1.** The obvious negative control for the
> merge-clean matrix came back green. It was not a vacuous harness — the two backup refs are in an
> ancestor relationship, so no conflict was possible. Re-scoped to the pair that actually collided,
> the control fires. **Three for three: every green break in this programme so far has been a
> mis-scoped ablation, not a vacuous check.**

### Green ablations, twice in one day

The BF-36 case was three ablations of which two did not reproduce. The second case, within the hour:
an ablation script mangled its own heredoc quoting, **applied nothing**, and reported every test
passing. That is indistinguishable from "the tests are vacuous" and is in fact "the break did not
break" — caught only because a stray traceback appeared above the green line.

> **When a break comes back green, confirm the break landed before concluding anything about the
> test.**

## 4d. The audit is complete, and the severity labels point the wrong way

45 suppressions in `lib/`, **four defects, 41 exactly what they claimed to be.**

| rule suppressed | sites | defects |
|---|---:|---:|
| `security/detect-object-injection` | 34 | 2 — BF-35, BF-36 |
| `no-cond-assign` | 3 | 0 |
| `security/detect-non-literal-fs-filename` | 3 | 0 |
| **`no-useless-escape`** | **2** | **2 — BF-37, BF-38** |
| four others | 3 | 0 |

**Both `no-useless-escape` sites had a real defect on the same line.** Two for two, on the most
trivial rule in the list.

> **A suppression for a *trivial* rule is the strongest signal of all.** It marks a line somebody
> looked at and dismissed *quickly* — precisely because what the linter said was obviously
> unimportant. `detect-object-injection` at least makes a reader think about whether the index is
> right. `/[_\+]/` does not make anyone think about anything.

That inverts the intuition the rule names invite: the security-prefixed rules yielded 2 defects in
37 sites; the cosmetic one yielded 2 in 2.

**The clean categories are recorded with their reasons**, not as a count, so nobody re-derives them:
`ss.quantile` sorts internally and returns `null` on empty, so `hourlystats`' truthiness guard is
cosmetic; two of the three `non-literal-fs-filename` sites are `Dropdown.open()`, not `fs.open`; the
alexa fallthrough is deliberate and commented.

**`lib/` is now fully audited for suppressions.** The client bundle and `tests/` are not.

## 5. Follow-ups, deliberately not in these PRs

1. **No end-to-end assertion on the composed count path.** `bf/coercion` + `bf/reads` compose
   correctly on the merged tree (§3b, reproduced), but nothing asserts over HTTP that a numeric
   filter on `count/devicestatus/where` returns rows. **This is the follow-up that survives from the
   old §3b**, restated for the right reason: not a merge hazard, a missing test. Until it exists,
   §3b's table is a source-level reproduction, not a behavioural one.
2. **The limit rule is written twice** — `lib/server/count.js` and v3's `parseLimit` — on purpose,
   so each commit lands alone. Unify afterwards. *Two readings of one rule is the root cause of
   this whole family*, so leaving it duplicated is a debt with a name.
   **Note the tense**: `lib/server/count.js` does **not** exist on `origin/dev` — `bf/reads` creates
   it — so the duplication does not exist yet and is *created* by landing `bf/reads`.
3. **`plugins.isPluginEnabled` always returns `true`** (`find` returns `undefined`, compared with
   `!== null`). No caller, so no register id — but it is what the next instrument will reach for.
4. **A second unguarded `console.log` on a request path in `lib/authorization/storage.js`**, same
   shape as BF-05, different file. **Both line numbers that have been quoted for it are right and
   neither named its ref**: it is **`:84` on `origin/dev`** and **`:113` on `bf/auth`**. The fix
   lands on `dev`, so **`:84` is the number a register reader needs.**
5. **BF-04** needs *extraction* from the seam branch, not a fresh fix.
6. **The alexa `switch` has no `default`** — an unrecognised `request.type` calls neither
   `res.json` nor `next()`, so the request hangs until the client times out. Low reachability, and
   it sits beside the `ctx.language.set(locale)` line `bf/alarms` already changes, so **it should
   land with that branch** rather than on its own.
7. ~~**The second-`=` truncation in `queryParms`**~~ **ANSWERED, not a defect.** A token cannot
   contain `=`: the name is `\w`-stripped and the digest is hex. Recorded rather than fixed.
8. **Audit suppressions outside `lib/`** — `detect-non-literal-fs-filename`,
   `detect-possible-timing-attacks`, `no-cond-assign`. Object-injection's 34 lines yielded two real
   defects; the same reasoning applies to each remaining category.
9. **jsdom test hygiene has no enforcement.** A suite that sets `global.window`/`global.document`
   must restore them in `afterEach` or it breaks `browser-settings.test.js` later in the same run.
   `hashauth.modern.test.js` does the restore; nothing requires it, and the failure lands in a
   different file than the one that caused it.
10. **Worktree mongod isolation is not what the handoff notes claim.** Re-measured 2026-09-16:
    **four** worktrees share port **27033** — `crm-bf-cache`, `crm-bf-food`, `crm-bf-merge` and
    `crm-bf-parms` (`crm-bf-cache` was missing from the earlier list of three); `crm-bf-coercion`
    names 27030 and `crm-bf-alarms` names 27034 **with nothing listening on either** (confirmed by
    connecting to each port); `crm-bf-auth` 27031 and `crm-bf-reads` 27032 are up;
    `crm-bf-connect-pin` has no `my.test.env` at all. The concrete consequence is that **`bf/alarms`' two API test files cannot
    be run on this machine as configured.** Fix before relying on per-branch targeted runs.

> *T0.4 used to be listed here as a follow-up "in a different repository and not in this set". It
> **is** in this set — it is `fix/connect-timer-jitter`, §2b. Removed from the follow-up list.*

## 6. Where this batch sits: the maintainer's linear model

Stated 2026-09-15. A linear flow, to stabilise behaviour, fix bugs, bring dependencies current, and
then bring down the cost of hosting many tenants in one cohesive codebase:

1. **REMEDIAL / BACKFIX work** → PRs onto official current `dev` — *the current release cycle.*
   **That is this document.** The backfix queue is the candidate pool.
2. **MODERNIZATION work** → the five parcels, in order, **each taking `dev` first.**
3. **MULTITENANT work** → on a stabilised, current base.

**The consequence earlier agents could not settle, and it follows from step 2's proviso:** a parcel
that has not taken `dev` first does not merely miss the remedial fixes — **merging it can silently
revert them**, because the parcels rewrite the same files.

**Measured during this rewrite (reproduced):**

| parcel | branch | tip | `dev` commits it lacks | own commits ahead of `dev` |
|---|---|---|---:|---:|
| 1 | `chore/retire-jsdom` | `bce12ecc` | **59** | 99 |
| 2 | `chore/build-runtime-separation` | `b6e8c7cd` | **59** | 258 |
| 3 | `chore/compose-mongodb6` | `ebb690cf` | **59** | 321 |
| 4 | `chore/mime-exposure-review` | `b80aa147` | **59** | 400 |
| 5 | `chore/nightscout-modernization` | `0a4109f6` | **0** | 495 |

> **CORRECTION, and it matters for how the rule is stated.** "The parcels are ~59 commits behind
> `dev`" is true of **parcels 1-4** and **false of parcel 5**, which already **contains** `origin/dev`
> at `a8888f0d` (`git merge-base --is-ancestor origin/dev chore/nightscout-modernization` succeeds).
> The rule itself is unaffected and in fact illustrated: parcel 5 is current **because it has
> already taken `dev` once**. **The moment these nine PRs merge, `dev` moves and parcel 5 is behind
> again** — so "take `dev` first" is a standing requirement before each parcel ships, not a
> one-time cleanup, and the 59 is a number with a date on it, not a property of the parcels.

**The overlap that makes "silently reverts" concrete, not rhetorical.** Phase 0 touches **57
distinct paths**. Parcel 4 and parcel 5 each modify **24 of those same 57** relative to `dev` —
including every file the query and count work touches:

```
lib/server/aggregate.js      lib/server/query.js        lib/server/entries.js
lib/server/devicestatus.js   lib/server/profile.js      lib/server/treatments.js
lib/server/activity.js       lib/server/food.js
lib/authorization/storage.js lib/authorization/index.js lib/api/index.js
lib/api/entries/index.js     lib/api3/security.js       lib/api3/alarmSocket.js
lib/client/boluscalc.js      lib/client/browser-utils.js lib/client/receiveddata.js
lib/data/dataloader.js       lib/food/food.js           lib/language.js
lib/server/websocket.js      package.json
tests/api.alexa.test.js      tests/api.entries.test.js
```

That is BF-35 (`boluscalc.js`), BF-36 (`receiveddata.js`), BF-37/BF-39 (`browser-utils.js`),
BF-17/BF-30 (`authorization/`), all of T0.5 and all of the read-path fixes. **A parcel merged
without first taking a `dev` that carries these fixes is a merge that can put the old lines back.**

## 7. Parcels 4 and 5 travel together, behind a deprecation release

**DECIDED by the maintainer, 2026-09-15: parcels 4 and 5 travel together behind a deprecation
release, with little or no waiting period.**

**The structural half of that is not a preference, it is a measurement.** Each earlier parcel is
**contained in** the later one — verified with `merge-base --is-ancestor`, **all four consecutive
pairs linear** (reproduced during this rewrite):

```
chore/retire-jsdom  ⊂  chore/build-runtime-separation  ⊂  chore/compose-mongodb6
                    ⊂  chore/mime-exposure-review      ⊂  chore/nightscout-modernization
```

**So "ship parcel 5 but hold parcel 4 back" is NOT ACHIEVABLE as a merge.** Parcel 4 —
**the legacy Dexcom and MiniMed retirement** — is inside parcel 5. Shipping Express 5, Helmet, EJS,
Axios, Mocha 12 and Swagger ships the retirement with them, or it ships nothing.

**The waiting-period half is the maintainer's domain judgement, it was explicitly hedged, and it has
now been tested against source.** The reasoning, in the maintainer's own words: *"The old medtronic
does not work, and the nightscout-connect module works better regardless, with modern dependencies
and includes an auto adoption/migration path, so nothing is lost."* On Dexcom: *"even for Dexcom,
nightscout-connect has some adjustments that allow more consistent access, from what I understand."*

**The evidence is in the migration plan and two research documents, and they should be read before
the deprecation notice is written. They do not simply confirm the premise.** The plan of record is
[legacy CGM ingestion to Connect](../40-migration/legacy-cgm-ingestion-to-connect-2026-09-15.md);
E1 and E2 below are the measurements it rests on, and both correct it. Headlines, with the full
findings in the documents:

- [E1 — Dexcom path comparison](../60-research/e1-dexcom-path-comparison-2026-09-15.md).
  **The auto-adoption path is already on `dev`, not on parcel 4.** `lib/server/bridge-connect-compat.js`
  and `migrateBridgeToConnect()` ship on `a8888f0d` (introduced by `a91e8ee4`), so any site with
  `BRIDGE_USER_NAME`/`BRIDGE_PASSWORD` is **already served by nightscout-connect today** unless it
  sets `DEXCOM_BRIDGE_USE_LEGACY=true`. **Parcels 4/5 remove the fallback, not the migration — the
  deprecation clock started at `a91e8ee4`.** Also: `dev` does **not** pin v0.0.13; it pins
  `234d47c8` (`git describe` = `v0.0.12-28-g234d47c`). And connect is **not** uniformly better —
  on a server-invalidated session it stays Active with a dead token for up to 24 h, where legacy
  recovers on the next poll.
- [E2 — MiniMed path comparison](../60-research/e2-medtronic-path-comparison-2026-09-15.md).
  **The MiniMed shim `lib/server/mmconnect-connect-compat.js` does NOT exist on `dev` or `master`** —
  it is a parcel-4 artefact, so "includes an auto adoption/migration path" is true of the release
  being prepared and false of everything shipped so far. **Every MMCONNECT operator must act by
  hand**, and `CONNECT_COUNTRY_CODE` is a new mandatory variable whose omission pushes a `bootError`
  that takes the whole site down (BF-61). One total break in legacy *is* proved: CareLink
  care-partner (follower) accounts cannot work through Nightscout at all, because
  `lib/plugins/mmconnect.js` `getOptions` never plumbs `patientId`.
  **And the item E2 ranks above every other finding it made was missing from this section until the
  2026-09-16 review put it back.** Reproduced end to end through both shipping transforms and the
  shipping `lib/plugins/timeago.js`: with a payload whose timestamps carry **no zone designator** —
  the shape the retired package's own recorded fixtures use — and a pump **east of the server
  clock**, *legacy* files the reading at the true instant and raises the urgent stale-data alarm,
  while **Connect files it in the future** (a UTC+2 pump, a genuinely dead 40-minute feed, and the
  reading lands at age −80 minutes), `checkStatus` returns `current`, the browser alarm is false and
  **zero push alarms are sent**. That is BF-44 chaining into BF-41. Controls: at UTC+0 all three
  agree; at UTC−7 Connect alarms but is 7 h 40 m wrong; a zone-**bearing** payload inverts the roles.
  **So the retirement improves this hazard for some users and causes it for others**, and which is
  decided by a vendor payload property nobody in this programme has observed on a real account.
  A second detector goes quiet with it: `lib/plugins/pump.js` does `moment(pump.clock)`, which for an
  unparseable value makes `urgent.isAfter(...)` false, so the pump-stale warning cannot fire either.
  **Also: do not advise staging `CONNECT_*` settings alongside `MMCONNECT_*`.** BF-45, reproduced:
  `lib/plugins/mmconnect.js` `init` returns a live runner whether or not
  `connect.source === 'minimedcarelink'`, so both ingestion paths poll at once — and because the two
  paths compute different `sysTime` values the upsert does **not** absorb the duplicates. That
  advice is safe for Dexcom and unsafe for MiniMed.

**Two things to carry into the deprecation notice, in this order. The ranking was wrong here until
the 2026-09-16 review and the correction matters, because the two items have different failure
modes.**

**First, the timestamp hazard above**, because E2 states plainly that *of everything it studied,
only that section has a failure mode where a person's glucose data stops and the software does not
say so.* It is the item that should decide whether the retirement ships behind a fix or behind a
notice. This document previously gave that ranking to the settings item below, which is not what the
evidence says.

**Second, "nothing is lost" is true of stored glucose history and false of settings.** Five
`BRIDGE_*` and five `MMCONNECT_*` controls are silently dropped, the `device` label changes
(`share2` → `nightscout-connect`, `connect-paradigm` →
`nightscout-connect://minimedcarelink/PARADIGM`) which splits chart history, and several
configurations legacy tolerated stop working — notably `BRIDGE_SERVER=US`, which becomes the
unresolvable host `https://US` while `validate()` returns `ok: true`. That last one *is* a silent
stop, and it is why the `BRIDGE_SERVER` census below sets the length of the notice.

> **The "no duplicate readings" half is Dexcom-only and was stated too broadly here.** For **Dexcom**,
> E1 reproduced that entry records are field-for-field and value-for-value identical except `device`,
> and that `entries.create()` upserts on `{sysTime, type}` — which does not include `device` — so the
> cutover cannot duplicate history. For **MiniMed** that does not follow: E2 reproduced that legacy
> and Connect compute **different `sysTime` values** for the same reading whenever the payload
> carries no zone designator, so if both paths run (BF-45) the upsert absorbs nothing and the site
> gets two traces offset by the pump's UTC offset. Do not carry the Dexcom sentence into a MiniMed
> notice.

**What has NOT been retired, and belongs in the notice as the case *for* the change.** The
adversarial review found this section listing only corrections, which reads as a case against a
decision the evidence partly supports. E1 and E2 also **confirm**, by reproduction: legacy Dexcom
dies with an uncaught `TypeError: glucose.map is not a function` on a non-array body with HTTP <400,
and cgm-remote-monitor registers **no** `uncaughtException` handler, so that kills the Nightscout
process, where Connect's `Array.isArray` guard continues; legacy authenticates ~550 times a day
against Connect's ~1; legacy sets `rejectUnauthorized: false` on all four request types; legacy
prints every CGM reading to the server log on every poll; legacy has no backoff term anywhere and
its session-rejection path is an unbounded delay-free loop; and `BRIDGE_MAX_FAILURES`, documented as
"how many failures before giving up", is **unreachable at its default**. On MiniMed, legacy's entire
US login branch is dead code (`if (1 || CARELINK_EU)`), `MMCONNECT_MAX_RETRY_DURATION` does nothing
(`let maxRetry = 1; // No retry`), and follower accounts cannot work at all. **Those are a sufficient
case for retirement on their own and do not depend on the unproven claim that legacy MiniMed "does
not work".**

**What cannot be settled on this machine, and should be said plainly rather than assumed away:**
whether Dexcom Share throttles or locks accounts under legacy's ~550 authentications/day; how often
Dexcom invalidates a session server-side; whether real CareLink payloads carry zone designators
(which decides whether the future-dated-reading hazard is latent or active); and **how many
operators are actually on a non-`EU`, non-dotted `BRIDGE_SERVER`**. That last one is the single
highest-value thing that could be done before deciding, **and it is the item that should set the
length of the deprecation notice.** None of these needs a real account to *describe*; all of them
need one to *measure*, and no vendor account has been used anywhere in this programme.

> **Audience note.** The deprecation notice is **operator- and user-facing**. It is read by people
> managing their own or a family member's diabetes. Plain language, define every term (`BRIDGE_*`,
> `CONNECT_SOURCE`, "pin", "parcel"), preserve every safety caveat, never give individualised dosing
> advice, and state that it is not medical advice and that changes to how glucose data reaches
> Nightscout are worth mentioning to a care team. **The migration plan and both research documents
> are drafts requiring review by the maintainer before anything is published.**
>
> **And it must tell people how to NOTICE a problem, not only how to fix one.** Every silent-stop
> mechanism measured here looks, from the outside, like a site that is working. The notice should
> tell an operator, in plain words, what to check in the first hours after switching over: that new
> glucose readings are still appearing on the graph and that the "time since last reading" indicator
> is counting in minutes rather than sitting still or showing a time that has not happened yet; that
> the reading shown matches the one on the phone or receiver; that the source label on the chart has
> changed from the old name to the new one, which is expected and is why older readings may look like
> a separate trace; and that alarms they rely on still arrive — a deliberate test of the
> missing-readings alarm is worth doing, because the hazard above is one where **no alarm is the
> symptom**. It should say where to look when something is wrong (the site's status page and the
> server log) and that a feed that stops is a reason to fall back to the receiver or phone app and to
> contact the community for help. **It is not medical advice, and anyone unsure should talk to their
> care team before changing how they get their glucose data.**

## 8. After these land

`origin/dev` moves, so **every modernization parcel and the seam branch need a refresh** before more
tenancy work — see §6 for why that is a correctness requirement and not hygiene. Parcel 5 is
current against today's `dev` and **stops being current the moment the first of these nine merges.**

The seam branch is 40+ commits of storage work; the longer it sits behind a moving `dev`, the more
the release-readiness document's own objection applies to it.

---

**Draft status.** This document is a working control-surface record, not a published plan. The
branch set, SHAs, merge results, parcel containment and file overlaps in it were reproduced on
2026-09-15/16 against `origin/dev` at `a8888f0d`; anything that moves invalidates the numbers, not
the method. **Nothing here has been pushed, merged, tagged or published, and each of those remains a
human decision.** The maintainer should verify: the branch-by-branch release-note assignments in
§4, the deprecation-window judgement in §7, and the `bf/auth` irreversible-change call.
