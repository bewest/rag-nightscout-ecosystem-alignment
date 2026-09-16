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

# Review packet — P0-B (PR #8740)

**bf/cache - PR #8740, T0.2 and T0.3 read-path cost**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/cache` |
| base | `origin/dev@a8888f0d` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=P0-B` is the measurement |
| semver | `patch` |
| register entries | `BF-06`, `BF-07` |

## What this changes

2 commits at 4f86bab1, 6 files, +385/-8. lib/server/cache.js,
lib/data/dataloader.js, lib/api/entries/index.js, plus three test files. NOTE
the dataloader path - this entry said lib/server/dataloader.js, which does not
exist; the file is lib/data/dataloader.js.

## Why that semver

performance only; no declared surface moves.

## What an operator would notice

> Pages that read recent glucose values get faster. Nothing you see changes
> value or meaning.

## Who should review this, and why

maintainer. OPENED 2026-09-16 as PR #8740, base dev. No decision is asked of
the reviewer, which makes it the odd one out in this set - but it is the
branch that ships with a target it did not hit, and the body says so in the
operator-facing text rather than only in the technical detail. What cannot be
read off the diff: T0.2's gate is MET (0.7x against a 2x budget, dev fails at
42x) and T0.3's is NOT (2.66 ms against 1 ms), and both are now re-runnable
from this repository with one command each.

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/dev bf/cache`** &nbsp;·&nbsp; kind: `static`

bf/cache has not fallen behind origin/dev

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/cache >/dev/null`** &nbsp;·&nbsp; kind: `static`

trial-merge into origin/dev is conflict-free

**`node tools/queue/gates/t02-read-ratio.js`** &nbsp;·&nbsp; kind: `integration`

T0.2's stated gate, RUN LIVE, AND IT IS MET - an untyped /api/v1/entries read
must come within 2x of a typed one at count=10, and it is 0.7x. It is carried
beside the T0.3 gate on purpose: that one is red and this one is green, and an
item showing only the failure would misrepresent this branch as much as one
showing only the win. NON-VACUITY IS STRUCTURAL: the harness reads
lib/api/entries/index.js out of the worktree and names the shape it found -
clone-then-slice on dev, slice-then-clone on the branch. Measured 2026-09-16:
dev FAILS at 42.3x, the branch PASSES at 0.7x, so it distinguishes them. SKIPS
when the worktree has no node_modules.

**`node tools/queue/gates/t03-cycle-clone-budget.js`** &nbsp;·&nbsp; kind: `integration`

T0.3's stated gate, RUN LIVE, AND IT IS RED ON PURPOSE - the budget is under 1
ms and the three cycle calls are 2.66. THE MARKER THAT WAS HERE SAID THIS
COULD NOT BE RE-RUN, because "the workload that produced those two figures is
not recorded anywhere in this repository". That was FALSE when it was written:
docs/60-research/remedial/t02-t03-cache-clone-2026-09-15.md §2 names the
harness (tools/mt-bench/apitier.js, arm `cycle`) and the fixture - 576
entries, 600 treatments of which 361 survive retention, 576 device statuses
with 72-point prediction arrays, DEVICESTATUS_DAYS=2 - and §10 gives the
command. The cost of the wrong marker was that queue-status printed CLAIM
UNBACKED on this item: the state said gate-not-met while every runnable gate
passed and the failing property hid behind a marker nobody could run. RE-
MEASURED 2026-09-16 on Node v24.15.0: branch 2.656 ms against a recorded
2.657, origin/dev 3.929 against a recorded 3.747 - ordinary variance on a
timing bench, same direction and magnitude. NON-VACUITY IS STRUCTURAL: the
harness reads the live call sites out of the worktree and prints them (dev
entries=insertData, branch entries=insertDataRef) and throws on a tree it
cannot recognise, so it cannot report the branch's number for dev's code.
Reproduced anyway - --budget 5 passes, proving it can go green. SKIPS when the
worktree has no node_modules.

**`git -C externals/cgm-remote-monitor-official ls-remote --heads origin bf/cache | grep -q 4f86bab1637e926502c9b`** &nbsp;·&nbsp; kind: `network`

the branch behind PR #8740 is on the remote at the exact tip this item was
measured against. Read-only. Verified 2026-09-16.

**`node tools/queue/gates/pr-body-parity.js --only 8740`** &nbsp;·&nbsp; kind: `network`

the live body of PR #8740 still matches the file it was posted from. It does
NOT measure whether the body is true - and this body's headline figure WAS
wrong once, in the branch's own favour: it claimed 33x where the measurement
is 64x, which is the direction nobody checks.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The 98% of the remaining cost is devicestatus, whose caller rewrites
  fields in place. Taking it needs proof that nothing in the plugin tier
  writes to a device-status document. A grep is not that proof when the
  failure mode is a field silently vanishing from every API read served out
  of the cache. There is no test that would catch it.
- Review and merge state of PR #8740 is upstream's, and cannot be gated from
  here without a GitHub API call. Tracked, not driven.

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf-cache.md`](../../reports/phase0-pr-bodies/bf-cache.md)
- [`docs/60-research/remedial/t02-t03-cache-clone-2026-09-15.md`](../../docs/60-research/remedial/t02-t03-cache-clone-2026-09-15.md)
- [`docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`](../../docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md)
- [`tools/mt-bench/apitier.js`](../../tools/mt-bench/apitier.js)

## Notes carried on the item

THIS ITEM WILL REPORT FAIL FOREVER UNDER INTEGRATION=1, AND THAT IS THE
DESIGN. The T0.3 gate asserts a budget of under 1 ms and the branch ships at
2.66 ms. The target was deliberately not met - 98% of the remainder is
devicestatus and taking it needs a proof nobody has produced - and the branch
was opened saying so in its operator-facing text. So the red is the record of
a decision, not a regression, and anyone who sees it should read the gate's
own output, which says as much in its first line. The risk this creates is
that a permanently-red gate becomes background noise and stops being read at
all; the counterweight is that T0.2's gate sits beside it and is GREEN, so the
pair moves if either target does. THE EARLIER NOTE ABOUT CLAIM UNBACKED IS NOW
OBSOLETE and is removed rather than left to confuse: that warning fires when a
state of gate-not-met is contradicted by passing gates, and this item is no
longer gate-not-met. What remains true from it is the operational bit - both
performance gates are kind: integration because they run a benchmark, so a
default queue-status skips them. Use `make queue-status ID=P0-B INTEGRATION=1`
before drawing any conclusion from this row. --- Sequencing letter B. T0.2
passed its gate (0.837 -> 0.025 ms, asserted identical over HTTP). T0.3 did
not. A dead `mills` write at dataloader.js:203 was found and removed with a
test that goes red if it returns.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-B` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-15, against cgm-remote-monitor-official `a8888f0d`.*
