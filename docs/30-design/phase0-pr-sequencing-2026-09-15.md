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

## 6. After these land

`origin/dev` moves, so **`chore/nightscout-modernization` and the seam branch both need a refresh**
before more tenancy work. The seam branch is 40+ commits of storage work; the longer it sits behind
a moving `dev`, the more the release-readiness document's own objection applies to it.
