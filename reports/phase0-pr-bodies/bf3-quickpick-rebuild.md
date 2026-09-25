# `bf3/quickpick-rebuild` — the Bolus Wizard's Quickpick list shows your saved quick picks again

**DRAFT — for maintainer review. Not pushed, not opened.** Branch `bf3/quickpick-rebuild`, one
commit `83cfff14` on `origin/dev` `74fc6619` (register BF-69, queue BFQ-69). No `CHANGELOG.md`
edit. **Ships in 15.0.9** (decided 2026-09-23). Evidence:
`docs/60-research/remedial/bf69-quickpick-rebuild-2026-09-23.md`. The combined run with the other
15.0.9 additions is recorded in `docs/30-design/remedial/rc-15.0.9-integration-record.md`.

> **Ordering: this must ship with or after #8735 (BF-35).** #8735 made each quick-pick option load
> the record its label names. This PR makes the list non-empty, so without #8735 it would expose
> BF-35's wrong-record defect. #8735 is in `dev` `74fc6619`, and this branch is based on it. Do not
> backport this PR to a line that lacks #8735.

---

## What changes for you

*Plain-language summary for people using Nightscout. Nightscout is not a medical device and none
of this is medical advice.*

A few words used below:

- **Bolus Wizard** — Nightscout's built-in bolus calculator, in the Care Portal area of the page.
- **Quick pick** — a saved meal in Nightscout's food editor, with a name and a total amount of
  carbohydrate, for example "Breakfast, 45 g".
- **Quickpick list** — the drop-down in the Bolus Wizard that is meant to offer your quick picks, so
  that choosing one fills in the carbs for you.

### What was wrong

On 15.0.8 and on the development branch, the Quickpick list only ever showed `(none)`, however many
quick picks you had saved. Nothing showed a wrong number. The list simply did nothing. *Add from
database*, which adds foods one at a time, worked all along.

### What changes

When you open the Bolus Wizard, the Quickpick list shows your saved quick picks, in the order you
gave them. Choosing one fills in the Carbs box with that quick pick's own total. Quick picks you
marked as hidden are not listed. A quick pick set to "hide after use" is gone from the list the
next time you open the Bolus Wizard after you submit with it.

### Two things to know

- **Not everyone sees the Bolus Wizard.** It appears only if the site owner lists `boluscalc` in
  `SHOW_PLUGINS`, and only to someone allowed to enter treatments. An anonymous viewer on the
  default settings does not see it.
- **A quick pick added or changed somewhere else does not appear on a page that is already open.**
  It appears after the page reloads or reconnects. This is an older limit of how Nightscout sends
  food data to open pages, and this change does not alter it. If you edit a quick pick's carbs in
  another tab, reload the page before you use it.

### What you should do

After upgrading, open the Bolus Wizard and check that the Quickpick list shows what you expect.
Whatever the calculator shows, check the carbs against the meal you are actually eating before you
rely on them. Nightscout does not decide a dose, and this change does not change how the calculator
works anything out. If you use quick picks for meals, go over how you use them with your care team.

---

## Technical detail

### The defect

`lib/client/index.js` creates `client.sbx` from an empty `ddata`, then constructs `boluscalc`,
whose last lines called `loadFoodQuickpicks()`. That read `client.sbx.data.food`, which was `[]`.
When data arrives, `client.sbx` is **replaced**, and nothing rebuilt the chooser.
`git grep loadFoodQuickpicks` on `dev` finds the definition and that one call. Confirmed in a
browser: before any click, 0 options with 6 food records in the page.

### The fix (`83cfff14`, `lib/client/boluscalc.js` only)

- `prepare()`, which the drawer toggle runs on every open, now begins with
  `rebuildQuickpickChooser()`, which calls the existing `loadFoodQuickpicks()`.
- **The rebuild happens there and nowhere else, on purpose.** An option's value is an index into
  the module's `quickpicks` array. Rebuilding on a data update while a pick is selected would move
  that index under the selection and under `quickpickHideFood`, which is BF-35's failure class.
  `prepare` resets the selection to `(none)` in the same step.
- The `change` handler is bound once at construction, instead of inside `loadFoodQuickpicks`. The
  register's one-line candidate (call it from `prepare`, leave the binding where it was) stacks one
  more handler on every open: 4 handlers after 3 opens, measured.
- `loadFoodQuickpicks` is otherwise untouched. It still builds from `quickpick.selectable` (#8735),
  so hidden picks stay out, the order is by `position`, and each option indexes the array it was
  built from.

### Tests

`tests/boluscalc.quickpick-rebuild.test.js`, 8 tests, new file. `tests/boluscalc.quickpick.test.js`
from #8735 is unchanged. The calculator is constructed against the empty sandbox and `client.sbx`
is then replaced, as `index.js` does. The drawer is opened through its own toggle.

| test | kind | with `dev`'s `boluscalc.js` | on this branch |
|---|---|---|---|
| starts empty, because it is constructed before any food has arrived | invariant | passes | passes |
| offers the quick picks that arrived after construction when the drawer opens | discriminates | fails, `['(none)']` | passes |
| follows a change to the food data between two openings | discriminates | fails | passes |
| resolves the quick pick it names after the rebuild, with plain foods in the collection (BF-35) | discriminates | fails (no such option) | passes |
| keeps hidden quick picks out of the rebuilt chooser, in either spelling | discriminates | fails | passes |
| does not offer a quick pick hidden since the last opening | discriminates | fails | passes |
| opens with nothing selected, whatever was selected before | discriminates | fails | passes |
| binds the change handler once, however often the drawer opens | guard against the naive fix | passes | passes |

Each was checked by breaking the fix (the 19 are these 8 plus #8735's 11):

| break | result |
|---|---|
| the register's candidate as written (binding back inside `loadFoodQuickpicks`) | 1 of 19 fails: handler count 4, want 1 |
| `rebuildQuickpickChooser()` removed from `prepare` | 6 of 19 fail, chooser `['(none)']` |
| option loop over every record (BF-35's pre-#8735 loop) | 8 of 19 fail across both files, including `picking "Breakfast" must load Breakfast` and `reading 'foods'` |

### Full suite, Node 20.20.0 and 22.23.2, MongoDB 7.0.43

| build | passing | failing | pending |
|---|---|---|---|
| `dev` `74fc6619` | 2386 | 0 | 3 |
| this branch `83cfff14` | 2394 | 0 | 3 |

Exactly +8, the eight new tests. No existing test expectation was changed.

### Browser evidence

Measured in Chrome against a real server for 15.0.8, `dev` and this branch, seeded with 2 plain
foods and 4 quick picks (one hidden, one hide-after-use), inserted interleaved and out of
`position` order, with no two carb totals equal. The data was synthetic.

| | 15.0.8 | `dev` | this branch |
|---|---|---|---|
| Quickpick list after opening the Bolus Wizard | empty | empty | the three visible picks, in `position` order |
| each pick enters its own label's carbs | 0 of 0 | 0 of 0 | 3 of 3 (45, 70, 20); `(none)` enters 0 |
| a pick added while the page is open, offered on the next open | no | no | only after a reconnect |
| hide-after-use via Submit | not reachable | not reachable | stored pick hidden, not offered on reopen |
| page errors | 0 | 0 | 0 |

With BF-35's loop put back on this branch, the same probe shows the wrong-record symptom directly
(`bf69-apple (12 g)` enters 45 g). The BF-35 browser probe passes 5/5 against this branch. Full
tables: the research doc, §4 and §5.

## For the reviewer to decide or verify

1. Rebuilding at drawer open, not on every data update, is the design choice (see "The fix"). The
   trade-off is the stale-while-open behaviour below, which exists whichever way the rebuild is
   triggered.
2. The hide-after-use browser arm submits a real `Bolus Wizard` treatment with synthetic values. Its
   insulin figure is not asserted and is not meaningful.

## Found on the way, not in this PR

- **Food changes do not reach open pages.** `lib/data/calcdelta.js` `compressArrays` does not cover
  `food`, so a food written through the API or another tab reaches a page only on a full load. The
  chooser now shows exactly what the page holds, stale or not. Proposed as its own register entry.
- `lib/settings.js` `adjustShownPlugins`: the "show everything enabled" branch can never run,
  because an empty `SHOW_PLUGINS` string is falsy. So the Bolus Wizard is hidden unless
  `SHOW_PLUGINS` names it. From reading the code only.

## Tested together with the other 15.0.9 changes

On a local integration branch (`rc/15.0.9-additions-d`) cut from the eight-unit 15.0.9 branch
(`b9c9828b`, 2508/0/3), this branch was merged tenth of ten, after `bf3/alarm-no-reading`. The merge
had no conflicts. The full suite went from 2512 to 2520 passing, with 0 failing and 3 pending, on
Node 20.20.0 and MongoDB 7.0.43. The difference is the 8 tests above, and no other test changed
state. After both merges, the full suite passes on Node 20, 22 and 24 against both MongoDB 4.4.24
and 7.0.43 (2520/0/3 each).

On the integrated tree, reverting this commit's `lib/client/boluscalc.js` hunk made 6 of 19 tests
fail, each seeing only `(none)` in the chooser. #8735's 11 tests and the handler-count guard still
passed.
