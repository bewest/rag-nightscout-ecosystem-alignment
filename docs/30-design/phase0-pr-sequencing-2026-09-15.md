# Phase 0: how to land five branches as pull requests

**Status**: ready to push. **Nothing has been pushed.** Five branches sit on `origin/dev` at
`a8888f0d` in worktrees under `externals/work/`; a sixth is in the `nightscout-connect` repository.

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

**So: push the seven Phase 0 branches to `origin` (or to the fork) and open PRs against `dev`.
Never push the branch *onto* `dev`.** The PR is what gets reviewed; the merge is what publishes.

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

## 1. Do not build a stack. Four of these are independent.

The instinct with five related branches is a stack — each PR based on the last. **Measured, that
would be wrong here.** Every pair was trial-merged with `git merge-tree --write-tree`:

| pair | result |
|---|---|
| `bf/coercion` + `bf/reads` | **CONFLICT** — `CHANGELOG.md` only |
| `bf/auth` + `bf/reads` | clean |
| `bf/cache` + `bf/reads` | clean |
| `bf/alarms` + `bf/reads` | clean |
| `bf/coercion` + `bf/cache` | clean |
| `bf/coercion` + `bf/auth` | clean |

`bf/coercion` and `bf/reads` share **six** files under `lib/server/` — `activity.js`,
`devicestatus.js`, `entries.js`, `profile.js`, `treatments.js` and the query path — and **none of
them conflicts**. The only collision is both branches appending to the same `### Fixed` heading
under `[Unreleased]` in `CHANGELOG.md`.

**A stack costs serial review and serial merge. Buy it only where there is a real dependency.**
Here there is exactly one, so: **four independent PRs off `dev`, and one two-deep stack.**

## 2. The sequence

### Independent — open together, merge in any order

| # | branch | commits | what it is |
|---|---|---|---|
| **A** | `bf/alarms` | 3 | BF-28, BF-29, BF-31. Zero file overlap with anything else. Smallest and most reviewable |
| **B** | `bf/cache` | 2 | T0.2 and T0.3. Self-contained in `cache.js`/`dataloader.js`/`api/entries` |
| **C** | `bf/auth` | 2 | BF-17 and BF-30. **Security — get a human on this one first** |

### Independent, and the one to read first

| # | branch | commits | what it is |
|---|---|---|---|
| **G** | `bf/food` | 1 (`73495331`) | BF-16 and **BF-35**. Trial-merges clean against **all six** other branches |

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

**Two things this branch needs from whoever lands it:**

1. **It deliberately does not create `CHANGELOG.md`.** That file does not exist on `a8888f0d`; both
   `bf/reads` and `bf/coercion` add it, and a third add would be a third add/add conflict for no
   benefit. **BF-35's release note text is in the register** — fold it into whichever branch owns
   the file. It needs one: the quick-pick list changes contents *and* what selecting an entry does,
   so anyone who had learned to work around the mislabelling will see different behaviour.
2. **A drift tripwire fires when this lands, and it is not a breakage.**
   `tools/nsschema/code_model.py`'s `SOURCE_ASSERTIONS` deliberately pins the quoted `'false'` in
   `lib/server/food.js` and `record[key] === 'true'` in `lib/food/food.js`, so that fixing them
   *forces* the food model to be revisited. Both are gone on `bf/food`, so `make schema-code-drift`
   will fail the day this reaches `externals/work/crm-seam` or `externals/cgm-remote-monitor-official`.
   The anchors were left alone because they are still true of both trees today; what to replace them
   with is written into BF-16.

### Independent — second in the batch

| # | branch | commits | what it is |
|---|---|---|---|
| **I** | `bf/parms` | 3 (`522c6ffb`, `eb0bc918`, `c9a7a21c`) | **BF-37**, **BF-39**, **BF-38** — in that order if split. Clean against all seven |

**BF-37 — a bare flag in the URL stops the page loading.** Verified against `origin/dev`:

```js
lib/client/browser-utils.js:46   // eslint-disable-next-line no-useless-escape
lib/client/browser-utils.js:47   params[item.split('=')[0]] = item.split('=')[1].replace(/[_\+]/g, ' ');
lib/client/index.js:48           client.init = function init (callback) {
lib/client/index.js:52             var token = client.browserUtils.queryParms().token;   // first real statement
```

`[1]` is read without checking it exists. `?debug`, a trailing `&`, a doubled `&&`, a lone `?` —
each throws `Cannot read properties of undefined (reading 'replace')`, **four lines into
`client.init`, before anything is wired up**. No chart, no socket, nothing on screen but the loading
message and a TypeError in a console nobody is reading.

**Placed second, behind BF-35.** It is not a wrong number, so not BF-35's category — but it is a
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

### Green ablations, twice in one day

The BF-36 case was three ablations of which two did not reproduce. The second case, within the hour:
an ablation script mangled its own heredoc quoting, **applied nothing**, and reported every test
passing. That is indistinguishable from "the tests are vacuous" and is in fact "the break did not
break" — caught only because a stray traceback appeared above the green line.

> **When a break comes back green, confirm the break landed before concluding anything about the
> test.**

### Independent — availability, not correctness

| # | branch | commits | what it is |
|---|---|---|---|
| **H** | `bf/merge` | 1 (`b06c6faf`) | **BF-36**. One lib file, one new test file. Trial-merges clean against **all seven** |

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

### Separate repository — open independently, no ordering relationship

| # | branch | repo | what it is |
|---|---|---|---|
| **F** | `fix/connect-timer-jitter` `c1cce2a`, based on `b77e5bb` | **`nightscout-connect`** | T0.4 (start jitter) and **BF-34**. Stands alone — no cgm-remote-monitor change needed. **But see below: merging it ships nothing** |

**BF-34 is the highest-value fix in the whole Phase 0 set and it is easy to miss** because it is in
the other repository. `backoff()` merges its options as `{ ...config, ...defaults }` — the spread
order is reversed, so **every value any caller passes is discarded**. All five vendor sources
configure a 2.5-minute retry interval and every one gets the 256 ms default, **586× faster**, with
`use_random_slot` forced `false` so a pool that fails together retries in exact lockstep. Measured:
100 actors delivered the same 800 requests across **3 s before and 67 s after**.

A vendor that is refusing requests gets hammered by every account at once, which is precisely when
it can least afford it — and the behaviour is invisible to the operator whose account is being
rate-limited. **Land this one first if anything is landed first.**

T0.4 also corrected its own premise: the actors do *not* stay phase-locked, because all four vendor
drivers already spell an 18-second random window into the timestamp they align to. **The start is
the burst, and it does not repeat.**

#### DONE 2026-09-15 — tag cut and pin moved, locally, nothing pushed

**The pin move turned out to be a security fix, and BF-34 is the smaller half of it.**

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

So **15.0.9 as currently pinned ships without three log-redaction fixes.** Making debug logging
opt-in (`234d47c`, the one commit the pin *does* have) narrows *when* those leaks can happen; it
does not stop them happening when an operator turns logging on to diagnose a problem — which is
precisely when they do it.

**What was done, all local:**

| repo | branch / ref | change |
|---|---|---|
| `nightscout-connect` | `release/v0.0.14` → `649a7de` | version `0.0.13` → `0.0.14`; **annotated tag `v0.0.14`** |
| `cgm-remote-monitor` | `bf/connect-pin` → `0807eb1c` | pin → `…/archive/refs/tags/v0.0.14.tar.gz` |

`v0.0.13` (`b394411`, `origin/main`) **fast-forwards** to the release — no merge to reconcile.

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

**`master` is a separate problem.** 15.0.8 depends on `"^0.0.12"` from **npm**, not a tarball — so
none of this reaches a current operator without an `npm publish`. Three pinning mechanisms across
three branches is the underlying defect; a published, tagged release on all three is the end state.

#### BF-34 currently reaches nobody, and fixing that is a release decision

`fix/connect-timer-jitter` is based on `b77e5bb`, **not** on `dev` and not on the connect repo's
`main`. `b77e5bb` is the exact commit `chore/nightscout-modernization` pins. Measured across the
three cgm-remote-monitor branches, **there are three different pinning mechanisms**:

| cgm-remote-monitor branch | how it depends on `nightscout-connect` |
|---|---|
| `master` (15.0.8, **what operators run**) | `"^0.0.12"` — a semver range from **npm** |
| `dev` (15.0.9 candidate) | tarball pinned to **`234d47c8`** |
| `chore/nightscout-modernization` | tarball pinned to **`b77e5bb`** |

So merging in the connect repository **ships BF-34 to nobody**. It reaches an operator only when a
cgm-remote-monitor `package.json` pin moves, and the pin that matters for the next release is
`dev`'s — which is 9 commits behind the base this fix sits on. (Verified: `234d47c8` **is** an
ancestor of `b77e5bb`, so the line is linear and there is no divergence to reconcile.)

**This collides with an open release decision that predates Phase 0.** The release-readiness
review already flagged that `dev` pins an *untagged commit SHA*, which is reproducible but
unreviewable and leaves the release with no connector version to name in its notes.

**One action settles both**: cut a `nightscout-connect` release containing BF-34, publish it, and
have `dev` pin **the tag** rather than a SHA. That ships the highest-value Phase 0 fix, gives
15.0.9 a nameable connector version, and retires the untagged-SHA objection — and it is the
"minutes-long task" the readiness review described.

Note that moving `dev`'s pin forward also pulls in the 9 intervening commits (quiet logging, stop
cleanup). That is a release-content decision, not a mechanical bump, and it is the maintainer's.

**Release note is BF-34's, and it is counter-intuitive**: a vendor outage will now appear to
recover *more slowly*, because the connector has stopped retrying in a burst that could not have
worked. BF-08 needs none — both jitter windows default to `0`, so nothing changes for anyone who
does not set them.

### The one stack

| # | branch | base | why stacked |
|---|---|---|---|
| **D** | `bf/coercion` | `dev` | 1 commit, the largest change. Lands first so the query path settles |
| **E** | `bf/reads` | **`bf/coercion`** | Rebase onto D; its release note is its own commit (`824380a0`), so the `CHANGELOG` conflict is resolved once, by its author, not by whoever merges |

**Why `coercion` before `reads`, and not the reverse.** Three reasons, in order of weight:

1. `bf/reads` keeps its release note in a **separate commit**; `bf/coercion` folded its note into
   its single commit. Rebasing a separate commit over a merged one is a one-hunk fix. The reverse
   means editing a squashed commit.
2. `bf/coercion` changes `query.js`'s signature (a new `collection:` option). `bf/reads` fixes
   `aggregate.js`, which **calls** `query.js`. Landing the callee first makes the caller's gap
   visible rather than latent — see the follow-up below.
3. `bf/coercion` is one commit; if review stalls on it, it blocks one branch rather than four.

### Ordering constraint inside a branch

`bf/reads` has one: **`c8fb536b` (BF-05) must follow `4a398d47` (BF-01)** — they share two files.
The branch is already in that order. Every other commit on every branch lands alone.

## 3. Commands

Nothing below pushes. Run them from `externals/work/crm-seam` (or any worktree on this repo).

```bash
# Rebase E onto D. Do this BEFORE opening either PR.
git rebase --onto bf/coercion origin/dev bf/reads
#   one conflict, CHANGELOG.md: keep BOTH blocks under ### Fixed.

# Confirm each branch still stands alone on dev.
for b in bf/alarms bf/cache bf/auth bf/coercion; do
  git merge-tree --write-tree --messages origin/dev $b | grep -q CONFLICT \
    && echo "CONFLICT $b" || echo "clean $b"
done
```

Then push each branch and open:

- **A, B, C, D** → base `dev`.
- **E** → base **`bf/coercion`**, and retarget it to `dev` once D merges. Most review UIs do that
  automatically; GitHub does.

## 3b. A clean textual merge is not a correct merge

`bf/coercion` and `bf/reads` are **both rewriting query construction**. `merge-tree` says their
six shared `lib/server/*.js` files merge without conflict, and that is a statement about hunks, not
about behaviour. The known instance:

> `bf/coercion` gives `query.js` a new `collection:` option. `bf/reads` fixes `aggregate.js`,
> which **calls** `query.js` and passes no options. Both land clean, and the count path still gets
> the legacy default walker — so `count/.../where` on `devicestatus` stays untyped after two PRs
> that each look complete.

**So D+E get a verification step that neither PR gets alone**: after E is rebased onto D, run the
query and count suites against the *merged* tree, and check the `find[...]` cases from D's release
note through the endpoints E touched. This is cheap and it is the only place in this set where the
merge itself can be wrong.

## 4. What each PR description needs

Every one of these changes what an operator sees. The register's rule 3 applies: *release-note the
behaviour changes*.

- **A** — states plainly that `insulinage`'s urgent alarm **starts firing for operators who have
  never received it**. That is the sentence to put first. Needs a maintainer's explicit yes.
- **B** — a performance change that also **removes a dead write** in `dataloader.js`. Say that the
  T0.3 gate (`< 1 ms`) was **not met** (2.66 ms) and why the remainder was left: 98 % of it is
  devicestatus, and taking it needs proof no plugin writes to a device-status document.
- **C** — two security fixes. Must carry the BF-17 remediation note: **a code fix does not
  invalidate tokens already written**, because the token is deterministic in `_id`, `name` and the
  enclave key. Rotation is the operator's action, and the PR should say which options exist.
- **D** — queries that returned nothing start returning rows; decimal bounds stop rounding down.
- **E** — `?count=0` was answered with the whole collection. Two new **restrictions** beyond the
  defect (`?count=0x10`, `?count=2.5` now `400`) must be called out as restrictions.

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

## 5. Follow-ups, deliberately not in these PRs

1. **`aggregate.js` does not pass a collection to `query.js`.** After D and E both land, the count
   path still gets the legacy default walker, so `count/.../where` on `devicestatus` and friends
   stays untyped. One-line follow-up, but it needs both merged first.
2. **The limit rule is written twice** — `lib/server/count.js` and v3's `parseLimit` — on purpose,
   so each commit lands alone. Unify afterwards. *Two readings of one rule is the root cause of
   this whole family*, so leaving it duplicated is a debt with a name.
3. **`plugins.isPluginEnabled` always returns `true`** (`find` returns `undefined`, compared with
   `!== null`). No caller, so no register id — but it is what the next instrument will reach for.
4. **`lib/authorization/storage.js:84`** has a second unguarded `console.log` on a request path,
   same shape as BF-05, different file.
5. **T0.4** (`nightscout-connect` jitter) is in a different repository and not in this set.
6. **BF-04** needs *extraction* from the seam branch, not a fresh fix.
7. **The alexa `switch` has no `default`** — an unrecognised `request.type` calls neither
   `res.json` nor `next()`, so the request hangs until the client times out. Low reachability, and
   it sits beside the `ctx.language.set(locale)` line `bf/alarms` already changes, so **it should
   land with that branch** rather than on its own.
8. ~~**The second-`=` truncation in `queryParms`**~~ **ANSWERED, not a defect.** A token cannot
   contain `=`: the name is `\w`-stripped and the digest is hex. Recorded rather than fixed.
9. **Audit suppressions outside `lib/`** — `detect-non-literal-fs-filename`,
   `detect-possible-timing-attacks`, `no-cond-assign`. Object-injection's 34 lines yielded two real
   defects; the same reasoning applies to each remaining category.
10. **jsdom test hygiene has no enforcement.** A suite that sets `global.window`/`global.document`
   must restore them in `afterEach` or it breaks `browser-settings.test.js` later in the same run.
   `hashauth.modern.test.js` does the restore; nothing requires it, and the failure lands in a
   different file than the one that caused it.

## 6. After these land

`origin/dev` moves, so **`chore/nightscout-modernization` and the seam branch both need a refresh**
before more tenancy work. The seam branch is 40+ commits of storage work; the longer it sits behind
a moving `dev`, the more the release-readiness document's own objection applies to it.
