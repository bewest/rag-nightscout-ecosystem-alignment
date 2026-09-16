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

# Review packet — P0-G (PR #8735)

**bf/food - PR #8735, BF-16 quick-pick filter, BF-35 bolus calculator chooser**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/food` |
| base | `origin/dev@a8888f0d` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=P0-G` is the measurement |
| semver | `minor` |
| register entries | `BF-16`, `BF-35` |

## What this changes

1 commit. lib/client/boluscalc.js, lib/food/food.js, lib/food/quickpick.js
(new), lib/server/food.js, 2 new test files.

## Why that semver

GT4: it changes an HTTP API v1 response. /api/v1/food/quickpicks goes from
filtering on the literal string {hidden:'false'} to
{hidden:{$nin:[true,'true']}}, so quick picks written by any JSON client, and
any record saved before the field existed, start appearing. Position ordering
moves from lexicographic (in-query) to numeric (in-process). Records appear
that did not; none disappears.

## What an operator would notice

> IMPORTANT. In the bolus calculator, choosing a quick pick could load a
> DIFFERENT record's food, so the carbohydrate number that went into the
> insulin calculation came from a record you did not choose, and nothing on
> screen said so. Picking the last entry in the list could throw an error,
> and plain foods that are not quick picks appeared in the chooser. This is
> fixed. Separately, quick picks saved by a JSON client, or saved before the
> "hidden" setting existed, were missing from the quick-pick list and now
> appear. If you have used the bolus calculator's quick picks, the amount it
> suggested may not have matched the food you selected. The calculator is a
> suggestion tool, not a dosing instruction - please raise this with your
> care team if you think a past suggestion was wrong. This is not medical
> advice.

## Who should review this, and why

maintainer - the sequencing document calls this the one to read first, and
BF-35 is why. OPENED 2026-09-16 as PR #8735, base dev. Still wants a reviewer
who has not self-merged in this stack (the governance finding), and an
explicit yes on the /api/v1/food/quickpicks filter change.

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/dev bf/food`** &nbsp;·&nbsp; kind: `static`

bf/food has not fallen behind origin/dev

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/food >/dev/null`** &nbsp;·&nbsp; kind: `static`

trial-merge into origin/dev is conflict-free

**`TEST=boluscalc.quickpick npm run test-single`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-food`

BF-35's own test, 11 cases. THIS IS THE GATE GT1 WARNED ABOUT: the file is in
NEITHER the test:unit nor the test:integration brace list, so a green `npm run
test:unit` on this branch is not evidence that BF-35's fix works. Named
explicitly here for that reason.

**`TEST=api.food.quickpicks npm run test-single`** &nbsp;·&nbsp; kind: `integration` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-food`

BF-16 over the real HTTP path; needs MongoDB

**`git -C externals/cgm-remote-monitor-official ls-remote --heads origin bf/food | grep -q 73495331e68c4cda3a63e8`** &nbsp;·&nbsp; kind: `network`

the branch behind PR #8735 is on the remote at the exact tip this item was
measured against. Read-only. Verified 2026-09-16.

**`node tools/queue/gates/pr-body-parity.js --only 8735`** &nbsp;·&nbsp; kind: `network`

the live body of PR #8735 still matches the file it was posted from. Bodies
drift in one direction - a correction gets written into the file first - and
the only previous record that one was owed was a sentence in a notes: field,
which is what let #8738 stay wrong in public for a day. It does NOT measure
whether the body is TRUE: parity with a wrong file is still parity, and every
figure in these bodies has been wrong at least once. NON-VACUITY, reproduced
2026-09-16: one altered file gives 1 failing, an empty body dir gives 6
failing. SKIPS with exit 0 when gh is unauthenticated.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Review and merge state of PR #8735 is upstream's, and cannot be gated from
  here without a GitHub API call. Tracked, not driven.

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf-food.md`](../../reports/phase0-pr-bodies/bf-food.md)
- [`docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md`](../../docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md)

## Notes carried on the item

Sequencing letter G. BF-35 is a regression from 3457de5b (2017) and was found
while fixing BF-16 - which is the argument for landing BF-16 even though BF-16
itself has no in-tree consumer. PREREQUISITE DISCHARGED 2026-09-16. This item
carried a blocker - the SOURCE_ASSERTIONS in tools/nsschema/code_model.py pin
text bf/food deletes, so `make schema-code-drift` would fail the day the
branch reached a checked tree. It is handled, and NOT the way BF-16
prescribed. The register said "replace the anchors when the branch lands";
replacing them now would fail the check against both SOURCE_ROOTS, which still
carry the pre-fix text because bf/food has not merged. Instead each anchor now
accepts EXACTLY the pre-fix and post-fix spelling and nothing else, and
lib/food/quickpick.js isTrue went into a new SOURCE_ASSERTIONS_IF_PRESENT
tuple that arms when the file appears. Measured: schema-code-drift exits 0
against crm-seam, cgm-remote-monitor-official AND crm-bf-food; crm-bf-food
failed on exactly these two anchors beforehand. Ablated three ways with each
break confirmed to land first - filter narrowed to `{ hidden: false }` FAILS,
restoreBoolValue rewritten to Boolean() FAILS, quickpick.isTrue renamed FAILS,
all three restored exits 0. STILL OWED AT MERGE, not now: delete the pre-fix
arm of each anchor and promote the quickpick.js entry, or a revert passes
silently.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-G` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-15, against cgm-remote-monitor-official `a8888f0d`.*
