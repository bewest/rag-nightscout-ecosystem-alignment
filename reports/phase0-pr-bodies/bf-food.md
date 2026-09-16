# G — `bf/food`: the bolus calculator's quick-pick chooser loaded a different meal from the one it named

> **Base: `origin/dev` `a8888f0d`. This is one of NINE INDEPENDENT PRs. There is no stack — no
> Phase 0 branch is based on another, and this one merges cleanly against `origin/dev` and against
> all eight of the others.**
>
> **Its one prerequisite is discharged (2026-09-16); nothing is owed before this merges.** A drift
> tripwire in the control-surface repo pinned text this branch deletes. It has been handled there,
> and deliberately not in the way the register prescribed — see "The drift tripwire" below for what
> was done, and for the one bookkeeping step that is owed *after* merge rather than before it.

## What changes for you

**If you use the bolus calculator's quick-pick list, the entry you choose is now the entry it
loads. Until now, on many sites, it was not.**

A *quick pick* is a saved meal in Nightscout's food editor — "Breakfast, 45 g of carbs" — that you
can select in the bolus calculator instead of typing the carbohydrates in by hand. The calculator
then works from the carbohydrate total of the record you picked.

Three things were wrong with the list you were choosing from:

- **Choosing one entry could load a different one.** The drop-down was built from your *whole*
  food database, but the selection was looked up in the *quick-picks only* list. The two lists
  line up only if every record in your food database is a quick pick. If you have ever saved a
  plain food — a single ingredient, not a saved meal — they stopped lining up, and the entry
  labelled "Breakfast (45 g)" could load Lunch instead. **The carbohydrate number that reached
  the calculation came from a record you did not choose, and nothing on screen said so.**
- **Plain foods appeared in the quick-pick list**, where they do not belong, and
- **choosing the last entry in the list did nothing at all** — the page threw an internal error
  and the selection was silently dropped.

Two further things change, and both restore behaviour that a 2017 change had quietly dropped:

- **Quick picks you marked as hidden stop appearing** in the chooser.
- **The chooser is ordered by the position number you gave each quick pick**, counted properly —
  so a quick pick at position 10 now comes after 9, instead of being sorted between 1 and 2 as if
  the number were a word.

Separately, on the server side, `/api/v1/food/quickpicks` — the address a third-party tool can ask
for your quick picks — **stops leaving out quick picks that were saved by anything other than
Nightscout's own food editor**, and returns them in position order.

### What you should do

**Open the bolus calculator's quick-pick list after upgrading and check that it says what you
expect.** Entries you had hidden will disappear from it, the order may change, and plain foods
will no longer be offered. If you had learned to work around the mislabelling — "I know that
picking Breakfast really gives me Lunch" — **stop doing that**; the list is now literal.

**Nightscout is not a medical device and this note is not medical advice, and neither Nightscout
nor this change decides anyone's insulin dose.** But a calculator that answers for a meal you did
not pick is the wrong kind of wrong. If a carbohydrate figure or a suggested amount ever looks
unexpected, check it against your own records rather than accepting it, and take questions about
dosing to your care team.

---

## Technical detail

Single commit `73495331`. Six files, +477/−17.

### BF-35 (high) — the chooser resolves the wrong record

`lib/client/boluscalc.js` `loadFoodQuickpicks` filtered `client.sbx.data.food` into a `quickpicks`
array, then built the `<option>` list by iterating the **unfiltered** collection while giving each
option a `value` that indexes the **filtered** one. `quickpickChange` and `quickpickHideFood` both
resolve that value against `quickpicks`. The two arrays agree only when every food record is a
quick pick.

| | shipped (`origin/dev`) | fixed |
|---|---|---|
| options offered, given 1 plain food + 2 quick picks | `Apple (12 g)`, `Breakfast (45 g)`, `Lunch (70 g)` | `Breakfast (45 g)`, `Lunch (70 g)` |
| pick the option labelled `Breakfast (45 g)` | loads **Lunch** | loads Breakfast |
| pick the last option | **throws** `Cannot read properties of undefined (reading 'foods')` | loads Lunch |

**It is a regression from `3457de5b` (2017-10-16)**, which moved both food loaders off the REST
endpoints onto `client.sbx.data.food`. In `loadFoodDatabase` the type filter moved *into* the loop
and stayed correct; in `loadFoodQuickpicks` it became a separate pass and the loop kept iterating
the original array. Before that commit the source was `/api/v1/food/quickpicks`, where every record
*was* a quick pick — so the code was right when it was written and was made wrong by a change that
did not look like it touched this file. **It has been in every release since.** A site whose food
database holds only quick picks is unaffected, which is why it survived this long.

**It surfaced under an eslint suppression.** `/* eslint-disable-next-line
security/detect-object-injection */ // verified false positive` sat on the defective line. The
suppression was a correct answer to the question the linter asked, on a line that had a different
problem.

### BF-16 (medium) — and both halves of its original claim are corrected

BF-16 said the quick-pick list had a type problem whose consequence was *wrong ordering on the
shipping path, with the built-in editor*. **Neither half survived contact with the code.** The
built-in editor does not use `/api/v1/food/quickpicks` at all — it reads `/api/v1/food.json` and
re-sorts numerically itself — and `3457de5b` removed that endpoint's only in-tree consumer. So the
lexicographic sort was real and reached nobody, while the order users actually see was broken by
the chooser not sorting at all.

The underlying type ambiguity is real and is now **reproduced rather than read**: over HTTP against
a live database, a form-encoded write stores `hidden: 'false'` and `position: '1'`; the identical
document sent as `application/json` stores `false` and `2`. Both spellings are already on disk
wherever a non-jQuery client has ever written, so every reader has to accept both. That premise is
asserted as its own test, so the filter can be simplified if the transport ever stops doing it.

Four readers disagreed, and now share one predicate in the new `lib/food/quickpick.js`:

- `listquickpicks` asked `{ hidden: 'false' }` — the string only — hiding every quick pick a JSON
  client ever wrote and every record saved before the field existed. Now
  `{ hidden: { $nin: [true, 'true'] } }`, which a **missing** field also satisfies.
- `listquickpicks` sorted `{position: 1}` in the query; a string sort puts `'10'` between `'1'` and
  `'2'`. Now sorted numerically after the fetch.
- `restoreBoolValue` mapped `=== 'true'`, which turned a **real boolean `true` into `false`** and
  silently un-hid a hidden quick pick every time the editor loaded. **This is the one BF-16 did not
  name, and the only one of the four that lost a setting rather than failing to read one.**
- the chooser did not consider `hidden` at all.

### The drift tripwire — fired as designed, discharged 2026-09-16

`tools/nsschema/code_model.py`'s `SOURCE_ASSERTIONS` in the control-surface repo **deliberately
pins** the quoted `'false'` in `lib/server/food.js` and `record[key] = record[key] === 'true';` in
`lib/food/food.js`, so that fixing them *forces* the food model to be revisited. Both strings are
gone on this branch. **Measured 2026-09-15** with the checker's own regex against the two git
trees: present on `origin/dev` (1 match each), absent on `bf/food` (0 matches each). The tripwire
worked. It is not a defect in this branch, and it is no longer outstanding.

**It is handled, and deliberately not the way register entry BF-16 prescribed.** BF-16 said to
replace the anchors with the post-fix spelling when the branch lands. Replacing them today would
have failed the drift check against every tree that exists — `bf/food` has not merged, and both
source roots still carry the pre-fix text — so the check would have been switched off across
exactly the window in which it is least affordable to lose. Instead each anchor now accepts
**exactly two spellings, the pre-fix one and the post-fix one, and nothing else**, and
`lib/food/quickpick.js`'s `isTrue` went into a separate `SOURCE_ASSERTIONS_IF_PRESENT` tuple that
arms itself when the file appears in a source root. That tuple is kept separate rather than mixed
in among the unconditional entries so a reader can see which claims are being checked now and which
are only waiting.

**Measured: `make schema-code-drift` exits 0 against `crm-seam`, `cgm-remote-monitor-official` and
`crm-bf-food`. The last of those failed on exactly these two anchors beforehand**, which is what
makes this a repair rather than a rewording. Widening an assertion is the move that usually hides a
defect, so it was ablated three ways with each break confirmed to land before the check ran:
narrowing the filter to `{ hidden: false }` — the precise danger BF-16 names — **fails**; rewriting
`restoreBoolValue` to `Boolean()` **fails**; renaming `quickpick.isTrue` **fails**; restoring all
three exits 0, so each failure belonged to its own break rather than to something already broken.

**What is still owed belongs to the merge, not to this PR**, and it is in the control-surface repo
rather than in this branch: delete the pre-fix arm of each anchor and promote the
`SOURCE_ASSERTIONS_IF_PRESENT` entry. Until that is done, a revert of this branch passes the drift
check silently.

## Evidence

- Backfix register `docs/30-design/remedial/nightscout-backfix-register.md` — **BF-35** (high, fixed) and
  **BF-16** (medium, fixed, claim corrected). BF-35's detail section carries the reproduction
  table, the provenance and the ablation list.
- Semver classification `docs/60-research/modernization/gt4-semver-classification-2026-09-15.md`, row 19.
- PR sequencing `docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md`, branch **G**, including the
  drift tripwire and its discharge.

## Test evidence

**`npm run test:unit` is not evidence for BF-35 and must not be quoted as though it were.**
Measured 2026-09-15 by expanding both brace lists with `shopt -s nullglob` in this worktree:
`test:unit` resolves to **44** files and `test:integration` to **90**, and
`tests/boluscalc.quickpick.test.js` — **the only test for BF-35, the high-severity defect** — is in
**neither**. A clean `test:unit` run on this branch never loads it. This is register entry
**BF-53**; CI is not blind to it, because `main.yml` runs `test-ci` over all of `./tests/*.test.js`.

Run these, from `externals/work/crm-bf-food`:

```
TEST=boluscalc.quickpick npm run test-single     # 11 passing, 0 failing, 135 ms, NO database
TEST=api.food.quickpicks npm run test-single     # 3 passing, 0 failing, 369 ms, NEEDS MongoDB
npm test                                         # the whole tree, the only local script that covers both
```

All figures **measured 2026-09-15** in this worktree. `boluscalc.quickpick` needs no database;
`api.food.quickpicks` is an integration test and ran against the mongod on this worktree's port.

**The tests were checked against unfixed code.** Reverting *only* the option loop to its
`origin/dev` shape — rebuilding the `<option>` list from the unfiltered `records` array — takes
`TEST=boluscalc.quickpick` from **11 passing / 0 failing** to **6 passing / 5 failing**, with the
ordering assertion failing as `['(none)', 'Tenth (1 g)', 'Second (2 g)', 'First (3 g)']` against
the expected `['(none)', 'First (3 g)', 'Second (2 g)', 'Tenth (1 g)']`. The worktree was restored
to a clean tree afterwards. The branch author records five further reverts, each caught — the
hidden filter (1 failure), the numeric comparator (1), `isTrue`'s boolean arm (3), the server
filter (1), the server sort (1); those five are read from the commit message, not re-run here.

The jsdom suite restores the globals it replaces. It found that the hard way: without the restore
it left `global.window` pointing at its own DOM and broke `browser-settings` later in the same run.

- Merges clean against `origin/dev` `a8888f0d` — `git merge-tree --write-tree` re-run 2026-09-15,
  and clean against all eight other Phase 0 branches.
- Lint unchanged at 23 problems (read from the commit message, not re-run).

## Semver

**Minor.** `/api/v1/food/quickpicks` (declared surface S1) returns records it previously omitted
and in a different order, and the stored-document contract (S4) is now read leniently on both
spellings. Nothing an operator configured stops working and no action is required, so it is not
major; answers on a declared surface changed, so it is not a patch. Classification from
`docs/60-research/modernization/gt4-semver-classification-2026-09-15.md` row 19.

**The operator-visible text above belongs in the release notes.** It is *not* a `CHANGELOG.md`
entry and this branch adds none: under the maintainer's rule, `CHANGELOG.md` is a **release
output** generated by GitHub tooling between releases, and branches never hand-edit it. Release
notes are prepared as release assets in the control-surface repo. The "What changes for you"
section above is written to be usable verbatim as that source text, and the "What you should do"
paragraph is the part that must not be dropped.

---

## Follow-ups deliberately **not** in this PR

- **`tools/nsschema/code_model.py`'s two food `SOURCE_ASSERTIONS` must move in the same sitting.**
  See above. Control-surface change, not a code change.
- **`/api/v1/food/quickpicks` has no in-tree consumer.** `3457de5b` removed its only one in 2017.
  It is now correct, and whether it should exist at all is a separate question with an operator
  census attached to it.
- **`food` never reaches `lib/server/query.js`**, so `bf/coercion` (D) does not interact with this
  branch: v1 `/food` accepts no filters at all. The food model's numeric fields are
  `['number','string']` unions precisely because the built-in client writes form-encoded.
- **`plugins.isPluginEnabled` always returns `true`** — `find` returns `undefined`, compared
  against `!== null`. No caller, so no register id.
