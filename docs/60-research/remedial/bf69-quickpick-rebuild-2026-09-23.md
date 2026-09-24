# BF-69: the Bolus Wizard quick-pick chooser is built once, from nothing — reproduction, fix and browser evidence

> **Snapshot, 2026-09-22 (US local; run clock 2026-09-23 UTC), against `origin/master` `92d08342` (tag 15.0.8), `origin/dev` `74fc6619` (which carries #8735, the BF-35 fix) and local branch `bf3/quickpick-rebuild` at `83cfff14`. Historical: the fix is merged into `dev` as #8756, not released; 15.0.8 still has BF-69. Current facts about the defect live in the [backfix register](../../30-design/remedial/nightscout-backfix-register.md) (BF-69, BF-35, BF-16) and item `BFQ-69` in [`queue/work-queue.yaml`](../../../queue/work-queue.yaml).**

Audience: contributors and the maintainer, except §1, which is written for operators and users.

## 1. What a person sees (plain language)

The Bolus Wizard is Nightscout's built-in bolus calculator. It has a **Quickpick** list of saved meals. Each quick pick has a name and a total amount of carbohydrate. Choosing one is meant to fill in the carbs for you.

**Before the fix** (15.0.8 and the development branch), that list only ever showed `(none)`, however many quick picks were saved. The screenshot from the test shows it: the Bolus Wizard is open, the page holds six food records, and the Quickpick menu offers `(none)` and nothing else. Nothing showed a wrong number. The feature simply did nothing, so people had to add foods one at a time with *Add from database*, which did work.

**After the fix**, opening the Bolus Wizard shows the saved quick picks, in their saved order. Choosing one fills the Carbs box with that quick pick's own total. In the test, `bf69-breakfast (45 g)` entered 45, `bf69-lunch (70 g)` entered 70, and `bf69-snack (20 g)` entered 20. Quick picks marked hidden are not listed. A quick pick set to "hide after use" disappears from the list the next time you open the Bolus Wizard, after you submit with it.

**Two things to know:**

- **The Bolus Wizard is not shown to everyone.** It appears only if the site owner lists `boluscalc` in `SHOW_PLUGINS`, and only to a viewer who is allowed to enter treatments. An anonymous viewer on the default settings does not see it.
- **A quick pick added or changed elsewhere does not appear on a page that is already open.** It appears after the page reloads or reconnects. That is a separate, pre-existing limit of how Nightscout sends food data to open pages (§8), and this fix does not change it.

Whatever the calculator shows, check the carbs against the meal you are actually eating before you rely on them. This software does not decide a dose. This is not medical advice. If you use quick picks for meal dosing, go over how you use them with your care team.

## 2. Mechanism

`lib/client/index.js` on dev: `:239` creates `client.sbx` from an empty `ddata`. `:323` constructs `boluscalc`, and its last lines called `loadFoodQuickpicks()`, which read `client.sbx.data.food === []`. `:596` replaces `client.sbx` when data arrives. `updateVisualisations` (`:637`) never touches the chooser. `git grep loadFoodQuickpicks` on dev finds the definition and one call. The register's reading was **confirmed in a browser** (§4, "before any click": 0 options with 6 food records in the page).

## 3. The fix (`bf3/quickpick-rebuild`, `83cfff14`, `lib/client/boluscalc.js` only)

- `prepare()`, which `toggleDrawer` runs on every open (and close), now begins with `rebuildQuickpickChooser()`. That calls the existing `loadFoodQuickpicks()`.
- **The rebuild happens there and nowhere else, deliberately.** An option's value is an index into the module's `quickpicks` array, so rebuilding on a data update while a pick is selected would move that index under the selection and under `quickpickHideFood`. That is BF-35's failure class. `prepare` resets the selection to `(none)` in the same step.
- The `change` handler is bound once at construction instead of inside `loadFoodQuickpicks`. The register's "one-line" candidate (a call from `prepare`, binding left in place) stacks one more handler per open. Break B1 below shows 4 handlers after 3 opens.
- `loadFoodQuickpicks` is otherwise untouched. It still builds from `quickpick.selectable` (#8735), so hidden picks stay out, the order is by `position`, and each option indexes the array it was built from.

**The sequencing constraint is met.** The register requires that this not ship before #8735. #8735 is on dev (`74fc6619`) and the branch is based on it.

**Tests:** `tests/boluscalc.quickpick-rebuild.test.js`, 8 tests (new file; `tests/boluscalc.quickpick.test.js` from #8735 is unchanged). The calculator is constructed against the empty sandbox, then `client.sbx` is **replaced**, as `index.js` does. The drawer is opened through its own toggle, and records are named through a getter on `foods`, as #8735's tests do.

| test | kind | dev boluscalc.js | branch |
|---|---|---|---|
| starts empty (constructed before food) | invariant | green | green |
| offers picks that arrived after construction, on open | discriminates | **red** `['(none)']` | green |
| follows a change to the food data between two openings | discriminates | **red** | green |
| resolves the pick it names after the rebuild, plain foods interleaved (BF-35) | discriminates | **red** (no such option) | green |
| hidden picks stay out of the rebuilt chooser, both spellings | discriminates | **red** | green |
| a pick hidden since the last opening is not offered | discriminates | **red** | green |
| opens with nothing selected | discriminates | **red** | green |
| change handler bound once however often the drawer opens | guard against the naive fix | green | green |

## 4. Browser evidence

Probe: [`tools/review/probes/quickpick-rebuild-browser.js`](../../../tools/review/probes/quickpick-rebuild-browser.js), one instance per build, via [`w2-instance.sh`](../../../tools/review/probes/w2-instance.sh), with `NODE_ENV=development`, `ENABLE="careportal basal iob cob bwp boluscalc food"` and `SHOW_PLUGINS="careportal boluscalc iob cob"`. Chrome 149.0.7827.102 was driven by playwright-core 1.63.0. Each run used a fresh database and synthetic data. The seed was 2 plain foods and 4 quick picks (one hidden, one hide-after-use), inserted interleaved and out of `position` order. Every pick's `carbs` equals the sum of its foods' carbs × portions, and no two totals match. MongoDB counts were food 6 (4 quick picks) and entries 12 on every run.

**Provenance** (`--unit bf3/quickpick-rebuild`, token `rebuildQuickpickChooser`, verbatim and eval-escaped): BASE dev 0, candidate 3, bundles differ (10933669 B vs 10935837 B). **Pass.**

| arm | 15.0.8 | dev | branch |
|---|---|---|---|
| before any click (observation) | 0 options, 6 food records in page | 0 options, 6 food records | 0 options, 6 food records |
| after one click on the Bolus Wizard | **`[]`** | **`[]`** | `bf69-breakfast (45 g) \| bf69-lunch (70 g) \| bf69-snack (20 g)` |
| no plain food / hidden pick offered (invariant) | ok (nothing offered) | ok | ok |
| each pick enters its own label's carbs | **0 of 0** | **0 of 0** | 3 of 3: 45→45, 70→70, 20→20; `(none)`→0 |
| a pick added while the page is open reaches the page by broadcast (observation) | no | no | no |
| …after a transport drop and automatic reconnect | yes | yes | yes |
| …and the next open offers it | **no** | **no** | yes (`bf69-late (33 g)`) |
| hide-after-use via Submit: entered / confirmation / stored treatment / stored pick hidden / offered on reopen | **not reachable** | **not reachable** | 20 g / "Carbs Given: 20" / `{eventType: "Bolus Wizard", carbs: 20}` / `true` / not offered |
| page errors | 0 | 0 | 0 |
| anonymous viewer shown the Bolus Wizard toggle (observation) | no | no | no |

The register's existing two-instance probe, `quickpick-chooser-browser.js` (seeded by `seed.js`, food 8 / quick picks 3 in MongoDB), gave: BASE dev **0** options (RED, feature inert) and BASE 15.0.8 **0**. The candidate branch offered `review-qp-visible (30 g) | review-qp-strfalse (40 g)` with 0 page errors. 4/4 pass on each pairing.

## 5. BF-35 re-run on the branch

`probes/food-boluscalc-browser.js` (unchanged; it calls `loadFoodQuickpicks()` directly, which is how BF-35 was made observable), `seed.js` seed:

| BASE | CANDIDATE | result |
|---|---|---|
| 15.0.8 (no #8735) | `bf3/quickpick-rebuild` | **5/5 pass**. Candidate offers 2 (the two visible picks) with 0 page errors. BASE offers 8 (every plain food and the hidden pick) with 5 page errors `Cannot read properties of undefined (reading 'foods')` |
| 15.0.8 | dev (control) | 5/5 pass, same figures |

The new probe also measures what the BF-35 probe says it could not: **the carbs entered for each pick** (§4, 3 of 3 match). With BF-35's loop put back on the branch (break B3), it shows the dose-adjacent symptom directly: `bf69-apple (12 g)` enters **45** g, `bf69-hidden (99 g)` enters 20, `bf69-bread (15 g)` enters 20, and there are 4 page errors (`reading 'foods'`).

## 6. Break-its (each run, then restored from the saved fixed file; `git diff` checked)

| break | unit result | browser result | reproduces |
|---|---|---|---|
| B1: the register's candidate as written (binding back inside `loadFoodQuickpicks`) | 1 of 19 red: handler count **4**, want 1 | not run | shows why the binding moved |
| B2: `rebuildQuickpickChooser()` removed from `prepare` | 6 of 19 red, `['(none)']` | 4 arms red, chooser `[]`, nothing to select | yes, BF-69 exactly |
| B3: option loop over every record (BF-35's pre-#8735 loop) | 8 of 19 red, across both files, including `picking "Breakfast" must load Breakfast`, and `reading 'foods'` | 6 arms red, wrong carbs as in §5 | yes, BF-35 exactly |

## 7. Suite (`npm test`, own MongoDB 7.0.43, production bundle rebuilt first)

| tree | Node | passing | failing | pending |
|---|---|---|---|---|
| dev `74fc6619` | 20.20.0 | 2386 | 0 | 3 |
| dev `74fc6619` | 22.23.2 | 2386 | 0 | 3 |
| `bf3/quickpick-rebuild` `83cfff14` | 20.20.0 | 2394 | 0 | 3 |
| `bf3/quickpick-rebuild` `83cfff14` | 22.23.2 | 2394 | 0 | 3 |

That is exactly +8, the eight new tests. No existing test expectation was changed.

## 8. Found on the way (not fixed here)

1. **Food changes do not reach open pages.** `lib/data/calcdelta.js` `compressArrays` covers `sgvs, treatments, mbgs, cals, devicestatus`, and `food` is in neither that list nor the skippable objects. So a food written through the API, or the food editor in another tab, reaches a page only on a full load (connect or reconnect). This was measured on 15.0.8, dev and the branch alike. Any stale quick pick (including an edited carb total) stays on an open page until it reconnects. Because the chooser now rebuilds from the page's data, it shows exactly what the page holds, stale or not. Proposed as a register entry.
2. `lib/settings.js` `adjustShownPlugins`: `showPluginsUnset = settings.showPlugins && 0 === settings.showPlugins.length` can never be true (an empty string is falsy). The "show everything enabled" branch is dead, so the Bolus Wizard is hidden unless `SHOW_PLUGINS` names it. This is from reading the code only, not a measurement.

## 9. For the reviewer to decide or verify

- Rebuilding at drawer open, rather than on every data update, is the design choice here (§3). The trade-off is the stale-while-open behaviour in §8.1, which exists whichever way the rebuild is triggered.
- The hide-after-use arm submits a real `Bolus Wizard` treatment with synthetic values. Its insulin figure is not asserted and is not meaningful.

## 10. Reproduce

```bash
export W2_STATE=<scratch>/w2 W2_MONGO_CONTAINER=bf3cli-mongo W2_MONGO_PORT=27193 W2_NODE=20.20.0
export NSREVIEW_DEPS=<dir>/node_modules NSREVIEW_PLAYWRIGHT=$NSREVIEW_DEPS/playwright-core
H=tools/review/probes/w2-instance.sh; SEC="$(cat "$W2_STATE/secret")"
export ENABLE="careportal basal iob cob bwp boluscalc food" SHOW_PLUGINS="careportal boluscalc iob cob"
$H reset q-fix "$PWD/externals/work/crm-bf3-quickpick" 14973 bf3q_fix readable
node tools/review/probes/provenance.js --base http://127.0.0.1:14971 --candidate http://127.0.0.1:14973 --unit bf3/quickpick-rebuild
node tools/review/probes/quickpick-rebuild-browser.js --url http://127.0.0.1:14973 --secret "$SEC" \
  --mongo mongodb://127.0.0.1:27193 --db bf3q_fix --label fix
# BF-35 and the two-instance BF-69 probe: reset, `node tools/review/seed.js --url … --secret …` on each, then
node tools/review/probes/food-boluscalc-browser.js --base http://127.0.0.1:14972 --candidate http://127.0.0.1:14973 --secret "$SEC"
node tools/review/probes/quickpick-chooser-browser.js --base http://127.0.0.1:14971 --candidate http://127.0.0.1:14973 --secret "$SEC"
```
