# Phase 0: how to land five branches as pull requests

**Status**: ready to push. **Nothing has been pushed.** Five branches sit on `origin/dev` at
`a8888f0d` in worktrees under `externals/work/`; a sixth is in the `nightscout-connect` repository.

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
| **F** | `fix/connect-timer-jitter` `c1cce2a` | **`nightscout-connect`** | T0.4 (start/interval jitter) and **BF-34** |

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
