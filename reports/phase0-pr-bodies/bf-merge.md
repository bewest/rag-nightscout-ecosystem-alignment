# H — `bf/merge`: deleting one treatment and editing another could freeze the page

> **Base: `origin/dev` `a8888f0d`. This is one of NINE INDEPENDENT PRs. There is no stack — no
> Phase 0 branch is based on another, and this one merges cleanly against `origin/dev` and against
> all eight of the others.**

## What changes for you

**If your Nightscout page has ever stopped updating and only came back when you reloaded it, this
may be why. Nothing you see on screen changes while it is working normally, and no stored data is
touched.**

Nightscout's page does not re-download everything each time something changes. The server sends
small updates — "this treatment was deleted", "this one was edited" — and the browser applies them
to what it already has. That update handler had a counting error: when an update **removed** a
treatment and a later item in the same update **matched nothing the browser was holding**, the
handler read past the end of its own list and threw an internal error.

The error escaped into the code that handles every incoming update, which has no error handling
around it, so **everything after it in that update was abandoned**. From then on the page stopped
advancing and treatments stopped arriving, until it was reloaded. Nothing recovered on its own.

**The good news, and it is the reason this is graded medium and not high: the page did not lie to
you.** Nightscout's clock and its "time since last reading" indicator run on a separate timer that
kept working, so a frozen page **looked stale rather than showing an out-of-date number as if it
were current**. You would see the reading age climbing, which is the signal to reload.

**What triggers it:** deleting a treatment and, in the same batch of updates, editing another one
that your browser is not currently holding — for example a treatment older than the two days of
history the page keeps. Two deletions on their own do not trigger it. Adding a treatment does not
either.

Nightscout is not a medical device and this note is not medical advice. If your page has stopped
updating, the safe habit is unchanged: **do not treat a page that has stopped advancing as current
information — reload it, and check your pump, meter or CGM receiver directly.** Take any questions
about your therapy to your care team.

---

## Technical detail

Single commit `b06c6faf`. Two files, +143/−2 — one library file, one new test file.

`lib/client/receiveddata.js` `mergeTreatmentUpdate` walks the received items against the cached
array **while splicing and pushing that same array**, and it captured the cached array's length
once, before the walk:

```js
var m = cachedDataArray.length;          // captured once
for (var i = 0; i < l; i++) { ...
  for (var j = 0; j < m; j++) { ...      // bound goes stale the first time a splice fires
    if (no._id === cachedDataArray[j]._id) { ...
```

The bound went stale the first time a `remove` matched: the array shrank, `m` did not, and the next
received item that matched nothing ran the inner loop past the end and threw on `undefined._id`.

```js
mergeTreatmentUpdate(true,
  [{_id:'a'},{_id:'b'},{_id:'c'}],
  [{_id:'a', action:'remove'}, {_id:'not-in-cache', action:'update'}])
-> TypeError: Cannot read properties of undefined (reading '_id')
```

Two removes do not trigger it, because the second one matches and `break`s before reaching the
stale index. An insert does not either, because `push` grows the array **past** the bound rather
than below it. It needs a splice followed by a miss.

The throw escapes `receiveDData` into `lib/client/index.js` `dataUpdate`, which has no
`try`/`catch`, so the rest of that handler is abandoned.

**Fixed by reading the bound fresh on each comparison.** That is not a new idea in this file —
`mergeDataUpdate`, thirty lines up, already does exactly that, and its purge walks backwards for
the same reason. The two functions had drifted apart; both are now pinned by tests so they cannot
silently do so again.

**How it was found.** By auditing the 34 eslint `security/detect-object-injection` suppressions
after **BF-35** turned up under one of them. This is the only other one of the 34 that was hiding
something; the rest index the array their bound came from. The food-database chooser in
`boluscalc.js` is the instructive contrast — it filters with `continue` rather than into a second
array, so its index stays valid.

## Evidence

- Backfix register `docs/30-design/nightscout-backfix-register.md` — **BF-36** (medium, fixed),
  and the suppression-audit corollary that groups BF-35, BF-36, BF-37, BF-38 and BF-39.
- Semver classification `docs/60-research/gt4-semver-classification-2026-09-15.md`, row 4.
- PR sequencing `docs/30-design/phase0-pr-sequencing-2026-09-15.md`, branch **H**.

## Test evidence

**`tests/receiveddata.merge.test.js` is one of the 52 files that match NEITHER local npm script.**
Measured 2026-09-15 by expanding both brace lists with `shopt -s nullglob` in this worktree:
`test:unit` resolves to 44 files, `test:integration` to 89, and this file is in neither. **A clean
`npm run test:unit` on this branch is not evidence that this fix works.** CI is not blind to it —
`main.yml` runs `test-ci` over all of `./tests/*.test.js` — but the local scripts are.

Run this, from `externals/work/crm-bf-merge`:

```
TEST=receiveddata.merge npm run test-single      # 12 passing, 0 failing, 6 ms, NO database
npm test                                         # the whole tree, the only local script that covers it
```

Measured 2026-09-15. Twelve tests: eight for `mergeTreatmentUpdate`, four for `mergeDataUpdate`.
Both functions were already exported with the comment *"expose for tests"* and had no tests at all.

**The test was checked by putting the bug back.** Restoring the captured-bound shape **scoped to
`mergeTreatmentUpdate` only** takes the file from **12 passing / 0 failing** to **10 passing /
2 failing**, both failures being `TypeError: Cannot read properties of undefined (reading '_id')` —
exactly the production error. The worktree was restored to a clean tree afterwards.

> Note for anyone repeating this: the same loop shape appears in `mergeDataUpdate` thirty lines
> above, and editing the first textual match hits that function instead. The revert has to be scoped
> to `mergeTreatmentUpdate`.

- Merges clean against `origin/dev` `a8888f0d` — `git merge-tree --write-tree` re-run 2026-09-15,
  and clean against all eight other Phase 0 branches.
- Full suite at the time of the commit: 2040 passing, 3 pending, 0 failing; lint clean. Read from
  the commit message, not re-run here.

## Semver

**Patch.** No declared surface moves: nothing on the wire changes, no API response changes shape,
no environment variable is added or removed, no default flips. This is a client-side array-bounds
fix with no contract. Classification from
`docs/60-research/gt4-semver-classification-2026-09-15.md` row 4.

**The operator-visible text above belongs in the release notes.** It is *not* a `CHANGELOG.md`
entry and this branch adds none: under the maintainer's rule, `CHANGELOG.md` is a **release
output** generated by GitHub tooling between releases, and branches never hand-edit it. The "What
changes for you" section is written to be usable verbatim as the release-note source text.

---

## Follow-ups deliberately **not** in this PR

- **`lib/client/index.js` `dataUpdate` has no `try`/`catch`.** This PR removes one way to throw
  inside it; it does not make the handler resilient to the next one. Any throw from any update
  handler still abandons the rest of that update silently. No register id allocated — it is a
  design question, not a defect with a reproduction.
- **The remaining 32 `security/detect-object-injection` suppressions** were audited and found to
  index the array their bound came from. That audit is recorded in the register corollary, not
  re-run here.
- **`plugins.isPluginEnabled` always returns `true`** — `find` returns `undefined`, compared
  against `!== null`. No caller, so no register id.
