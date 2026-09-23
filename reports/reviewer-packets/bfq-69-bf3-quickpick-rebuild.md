<!--
  ============================================================================
  GENERATED FILE - MUST NOT BE HAND-EDITED.

  Source of truth:  queue/work-queue.yaml
  Generator:        tools/queue/emit_packets.py   (make packets)
  Staleness check:  python3 tools/queue/emit_packets.py --check

  Review NOTES belong on the pull request, not here. This file is a projection
  of the manifest; anything written into it is destroyed by the next run.
  ============================================================================
-->

# Review packet — BFQ-69

**BF-69 - the Bolus Wizard quick-pick chooser is built once, from nothing**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf3/quickpick-rebuild` |
| base | `origin/dev@74fc6619` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-69` is the measurement |
| semver | `patch` |
| register entries | `BF-69` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

One commit, 83cfff14, 2 files, +215/-2. lib/client/boluscalc.js only -
prepare() begins with rebuildQuickpickChooser(), which calls the existing
loadFoodQuickpicks(); the change handler is bound once at construction.
tests/boluscalc.quickpick-rebuild.test.js (new, 8 tests); #8735's
tests/boluscalc.quickpick.test.js unchanged. Client-side, so it needs a
rebundle, not a restart.

## Why that semver

Restores a documented feature that is inert. No API or configuration surface
changes.

## What an operator would notice

> Not released. The Bolus Wizard is Nightscout's built-in bolus calculator.
> It has a Quickpick list of saved meals, each with a name and a total
> amount of carbohydrate. On today's release that list only ever shows
> (none), however many quick picks are saved, so people have to add foods
> one at a time instead. After this fix, opening the Bolus Wizard shows the
> saved quick picks in their saved order, and choosing one fills in that
> quick pick's own carb total. Hidden quick picks are not listed, and one
> set to "hide after use" disappears the next time you open the Bolus Wizard
> after you submit with it. Two things to know - the Bolus Wizard appears
> only if the site owner lists boluscalc in SHOW_PLUGINS, and only to a
> viewer who is allowed to enter treatments; and a quick pick added or
> changed elsewhere does not appear on a page that is already open until
> that page reloads or reconnects (see BFQ-93). Whatever the calculator
> shows, check the carbs against the meal you are actually eating before you
> rely on them; this software does not decide a dose. This is not medical
> advice - if you use quick picks for meal dosing, go over how you use them
> with your care team.

## Who should review this, and why

maintainer, and whoever reviewed P0-G (#8735). The design choice to confirm is
rebuilding at drawer open only, not on every data update: an option's value is
an index into the quick-pick array, so a rebuild under a selection is BF-35's
failure class.

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf3/quickpick-rebuild >/dev/nu`** &nbsp;·&nbsp; kind: `static`

Merges into origin/dev with no conflict.

**`cd externals/work/crm-bf3-quickpick && n exec 20.20.0 npx mocha --timeout 30000 --exit tests/boluscalc.quickpi`** &nbsp;·&nbsp; kind: `unit`

The 8 new tests and #8735's quick-pick tests, no database; 19 passing. These
require lib/client/boluscalc.js directly, not the bundle. Control, run
2026-09-23 with tools/queue/gates/ablate.sh (boluscalc.js put back to
origin/dev) - the new test file exits 6, the chooser offering only (none). The
evidence's break-its B1 (the register's one-line candidate, handler stacked 4
times), B2 (rebuild removed) and B3 (BF-35's loop put back, wrong carbs) are
each red.

**`NSREVIEW_ROOT=${NSREVIEW_ROOT:?} node tools/review/probes/quickpick-chooser-browser.js --base "$NSREVIEW_BASE_`** &nbsp;·&nbsp; kind: `integration`

Clicks the Bolus Wizard exactly as a user does and reads the chooser. It does
not call loadFoodQuickpicks itself, which probes/food-boluscalc-browser.js
does deliberately to reach BF-35; the difference between the two probes is
this defect. Green only when the chooser is both populated and correct,
because a build that repairs it without bf/food offers 8 entries and throws 5
times. 4/4 on the branch against dev and against 15.0.8, 2026-09-23.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The sequencing constraint (never ship before P0-G, #8735) is met by
  ancestry - the branch is one commit on 74fc6619, which carries #8735 - and
  blocks_on still records it. Nothing gates a reviewer cherry-picking the
  commit onto a base without #8735. The full suite (2394/0/3 on Node 20.20.0
  and 22.23.2, +8 exactly) needs MongoDB and a rebuilt bundle and is
  recorded in the evidence.

## Blocked on

`P0-G`

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf3-quickpick-rebuild.md`](../../reports/phase0-pr-bodies/bf3-quickpick-rebuild.md)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/60-research/remedial/bf69-quickpick-rebuild-2026-09-23.md`](../../docs/60-research/remedial/bf69-quickpick-rebuild-2026-09-23.md)
- [`docs/30-design/remedial/dev-cycle-review-harness-plan-2026-09-17.md`](../../docs/30-design/remedial/dev-cycle-review-harness-plan-2026-09-17.md)

## Notes carried on the item

PREPARED 2026-09-23 - bf3/quickpick-rebuild 83cfff14, one commit on 74fc6619,
not pushed. BF-35's probes still pass on the branch (food-boluscalc-browser.js
5/5 against 15.0.8). The register's one-line candidate was not used as
written, because it stacks one more change handler per open. Destination
release not decided. Reproduced 2026-09-17 in a browser against the review
harness, on a8888f0d and on rc/2026-09-dev-cycle: 8 food records present,
chooser empty on both. SEQUENCING, MEASURED: the one-line change applied to
a8888f0d without bf/food makes the chooser offer eight entries - every plain
food plus the quick pick the user hid - and selecting them throws five times.
BF-35's dose consequence is latent on 15.0.8 only because BF-69 hides it.
Repairing the chooser first converts a latent high-severity defect into a live
one in a bolus calculator. Ship with P0-G (merged to dev as #8735) or after
it, never before.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-69` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
