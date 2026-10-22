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

# Review packet — RT-1 (PR #8828)

**Cut 1 - chore/retire-jsdom, PR #8828 to dev (16.0.0)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `chore/retire-jsdom` |
| base | `official/dev@04d435eb` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=RT-1` is the measurement |
| semver | `major` |
| register entries | `BF-55`, `BF-58` |

## What this changes

At 806ff2f0 (#8828): 120 commits ahead of official/dev 04d435eb, 0 behind; the
commit list is in RT-REBASE's notes. Before the catch-up merge, bce12ecc was
99 commits. Incremental production diff 11 files +68/-54 (GT2, 2026-09-15),
not the 21 files +91/-123 the release-readiness §5 table publishes - that row
was measured on a different basis from rows 2-5 and counts dev's own commits
as deletions. Total 106 files, not 163.

## Why that semver

GT4: the ENFORCED floor today is Node >=16 in bootevent.js, not the >=20 that
`engines` declares - engines is not enforced on dev or master. Cut 1
introduces runtime-policy.js, which reads engines.node and calls
process.exit(1). So the enforced floor jumps SIX majors, the declared range
becomes ^22.12 || >=24 (decided 2026-09-21; in cut 1 since dfbb611b, the
published bce12ecc declared ^22.23.2), excluding Node 21, 23 and 22.0-22.11,
and the check becomes a hard exit. Cut 1 also removes the legacy Dexcom Share
and MiniMed CareLink bridges and drops MongoDB 4.4 from CI. Maintainer
2026-10-21: the next release is 16.0.0 (RT-VERSION); 806ff2f0 declares it.

## What an operator would notice

> Planned as release 16.0.0. TWO THINGS TO CHECK BEFORE UPGRADING. First, it
> will refuse to start on older versions of Node (the program Nightscout
> runs on). You need Node 22.12 or newer within Node 22, or Node 24 or
> newer. Node 20 no longer works, and neither do Node 21 or 23 - the
> requirement is two ranges, not a single minimum. If Nightscout stops
> starting after this upgrade, that is why. Second, the older built-in
> Dexcom Share and MiniMed CareLink bridges are removed; CGM data from those
> services comes in through Nightscout Connect instead. If old bridge
> settings are left in place, the site stops at a page naming the settings
> that work. Merged into the development branch is not released: nothing
> changes for a running site until 16.0.0 is released and installed.

## Who should review this, and why

maintainer plus a human reviewer; low blast radius is the reason it is second
on the train, not a reason to skip review

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor official/dev official/chore/retire-jsdom`** &nbsp;·&nbsp; kind: `static`

cut 1 contains dev (806ff2f0 contains 04d435eb since 2026-10-21; see RT-
REBASE), so #8828 merges without conflict; red when dev moves ahead

**`NODE_FLOOR_REF=official/chore/retire-jsdom node tools/queue/gates/node-floor-consistency.js`** &nbsp;·&nbsp; kind: `static`

"Trivially revertible - the engines field plus a boot check" is mechanically
true and operationally misleading. Six other files state the floor
independently (.nvmrc, bin/setup.sh, azuredeploy.json, README.md,
CONTRIBUTING.md, docs/meta/architecture-overview.md). This gate checks they
agree; a one-field revert would leave them stale.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Dockerfile is node:22-alpine on both dev and cut 1. Under the published
  bce12ecc's ^22.23.2 that was a floating major tag against a patch floor;
  under 806ff2f0's ^22.12 || >=24 the tag cannot resolve below the floor,
  and node-floor-consistency.js (above) now checks the tag against the
  range: 9/9 ok on 806ff2f0, red on bce12ecc. Nothing pulls or builds the
  image here.
- 2026-10-21: ported under option C. 65248bed moves the 15.0.9 clock
  regression tests to tests/browser/clock-client.test.js (which on 806ff2f0
  mentions concern and falling), fcd90f26 the D3 chart tests and 853b4145
  the pill-title tests; the browser suite is 444/0 on Chromium 153 at
  806ff2f0. No queue gate re-runs the browser suite. Earlier text, kept as
  the record: the clock-client concern/falling coverage is lost in the
  conflict resolution (RT-REBASE). Porting it to the Playwright suite is
  real work nobody has scheduled, and release-readiness §2 Option 1's "one
  CI run plus a cherry-pick of tests/browser/" undercosts it - cut 1 also
  deletes tests/dependency-d3.test.js, tests/fixtures/d3.js,
  tests/fixtures/d3-chart.js and tests/client.renderer.test.js, and its
  browser suite requires a playwright-core fixture and a module builder that
  dev does not have.

## Evidence

- [`docs/60-research/modernization/gt2-cut-remeasure-2026-09-15.md`](../../docs/60-research/modernization/gt2-cut-remeasure-2026-09-15.md)
- [`docs/60-research/modernization/gt4-semver-classification-2026-09-15.md`](../../docs/60-research/modernization/gt4-semver-classification-2026-09-15.md)

## Notes carried on the item

2026-10-21, later: pushed and in review. The maintainer pushed chore/retire-
jsdom as a fast-forward of official/chore/retire-jsdom bce12ecc -> 806ff2f0
and opened #8828 (chore/retire-jsdom -> dev, "Cut 1: retire jsdom, Node floor
^22.12 || >=24, retire the legacy Dexcom and MiniMed bridges (16.0.0)").
Decided the same day: cut 1 lands on dev now and the next release is 16.0.0
(RT-VERSION). RT-REBASE's cut 1 part is done (dev 04d435eb merged in as
4b617f78; 0 behind, 120 ahead), so RT-REBASE is removed from blocks_on. Tests
on 806ff2f0: npm test 3224 passing / 3 pending / 0 failing (Node 24.20.0,
MongoDB 7.0.43 in a container); browser suite Chromium 153 444/0. On 8c117dd4,
before the last two commits: Node 22.12.0 3209/3/0, Firefox 155 444/0,
test:core 286/0. WebKit did not launch on the host; #8828's CI run 39704672667
on 806ff2f0 reports Browser tests (22, webkit) and (24, webkit) as success,
with all Run Tests cells (Node 22 and 24 x MongoDB 5 and 6) and the other
browser cells passing, and the two Docker validation jobs still in progress
when read. dev baseline on 04d435eb: 3569/4/0. Gates on official/*: node-
floor-consistency 9/9 ok (red on bce12ecc), connector-pin-exposure ok at
v0.1.0 (bce12ecc pinned the v0.0.13 tag), cut 1 contains dev. #8823 ("Fix
BRIDGE_SERVER=US/ous/URL mapping in bridge-connect compatibility", no queue
item of its own) is folded into cut 1 as 42a2729e with its authorship kept;
its 15 tests are unchanged and 7 of them fail with the fix reverted. It is
closed in favour of #8828; the close comment is the maintainer's (#8823 still
read OPEN at f75f9401 when measured). Follow-ups from cut 1, each its own
item: RT-CONNECT-TEARDOWN (the redundant connector teardown listener in
bootevent.js), BFQ-158 (the count=0 tests on a reused database). RT-JSDOM-REST
and RT-D3-SUITE already wait on this item. 2026-10-21: 15.0.9 is released, so
RT-0 is removed from blocks_on; cut 1 waits on its catch-up merge (RT-REBASE,
in progress on wip/cut1-onto-15.0.10, not pushed). Cut 1 is first in the
cycle's priorities (maintainer, 2026-10-21). Decided the same day: option C
(port the D3, clock-client and pill-title coverage to tests/browser in cut 1,
keep the jsdom harness for the rest, retire it later: RT-JSDOM-REST); the Node
floor ^22.12 || >=24 (ed21961f) and the legacy bridge removal (c043fb2d) come
into the merge; the connector teardown listener stays, its removal a follow-
up. The clock-client no-gate below is the coverage option C ports. Blocked on
15.0.9 (RT-0) and the rebase (RT-REBASE). The published cut 1
(origin/chore/retire-jsdom bce12ecc) is 175 commits behind dev 153e5658 and
conflicts in nine paths (RT-REBASE). Decisions: - 2026-09-23 (maintainer): the
legacy CGM bridge removal (MiniMed mmconnect and Dexcom share2nightscout-
bridge) moves from cut 4 onto cut 1. Rehearsed on local rh/cut1-retire-legacy
(c043fb2d, from rh/cut1, not pushed): 8 cherry-picks plus the BF-61 decision-A
fixes (the named fix boots, no release number in the message, BF-62 logged).
Node suite 2121/0/1 on 22.23.2 and 24.20.0 x Mongo 7; npm audit --omit=dev 15
-> 9 (request and form-data highs clear). Leftover MMCONNECT_* settings stop
the site with a page naming the fix. See
docs/60-research/modernization/cut1-legacy-bridge-lift-2026-09-23.md. That
rehearsal pins connector 0.1.0-dev.1; at the real rebase cut 1 takes dev's
exact 0.1.0 pin (RT-CONNECT-PIN-CUTS). - 2026-09-21 (maintainer): the Node
floor becomes ^22.12 || >=24 (RT-NODE-FLOOR-TESTED); prepared on rt/cut1, not
pushed. From cut 1 onward docker-build and docker-build-pr carry needs: [test,
browser-test], so a browser-test failure blocks image publication. On dev,
docker-build has needs: test only.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-1` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
