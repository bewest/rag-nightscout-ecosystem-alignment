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

# Review packet — RT-2 (PR #8837)

**Cut 2 - chore/build-runtime-separation**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `chore/build-runtime-separation` |
| base | `official/dev@a20469dc` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=RT-2` is the measurement |
| semver | `minor` |

## What this changes

#8837, head ee94b148: 185 commits ahead of dev a20469dc (11 behind dev
2bc298b9, the merge of #8838). Page bundles, narrowed D3, event bus, boot
sequence, Babel 8, build/runtime split (webpack and Babel become
devDependencies), express-minify removed. The published cut b6e8c7cd (159
commits ahead of dev before cut 1) is kept unchanged.

## Why that semver

GT4's judgement, explicitly UNMEASURED against any third-party plugin corpus -
none exists on this machine to run. The boot sequence and event bus are where
a plugin would break.

## What an operator would notice

> A maintenance release that changes how the page's code is packaged and
> loaded. You should see no difference. If you run a third-party plugin that
> hooks into the page, test it before upgrading.

## Who should review this, and why

maintainer plus a human reviewer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree official/dev official/chore/build-runtime`** &nbsp;·&nbsp; kind: `static`

#8837's branch trial-merges into official/dev cleanly (clean against dev
2bc298b9 on 2026-10-25; the published cut b6e8c7cd had 20 conflicting paths
against eb72a1d3)

**`RUNTIME_REQUIRES_REF=official/chore/build-runtime-separation node tools/queue/gates/runtime-requires-declared.`** &nbsp;·&nbsp; kind: `static`

every package cut 2's server code loads is under dependencies; webpack, now a
devDependency, is required only inside lib/server/app.js's NODE_ENV ===
'development' block (:333, require at :340). 32 checked, 0 failing on ee94b148

**`NODE_FLOOR_REF=official/chore/build-runtime-separation node tools/queue/gates/node-floor-consistency.js`** &nbsp;·&nbsp; kind: `static`

every file that states a Node version on cut 2 agrees with engines.node
^22.23.4 || ^24.22.1 || >=26.12.1 (.nvmrc 24.22.1 read as a version); 9
checked, 0 failing on ee94b148

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The minor classification rests on no plugin ever being run against it. A
  plugin corpus does not exist here. Until one does, "minor" is a judgement
  and the queue says so rather than letting the field imply a measurement.

## Evidence

- [`docs/60-research/modernization/gt2-cut-remeasure-2026-09-15.md`](../../docs/60-research/modernization/gt2-cut-remeasure-2026-09-15.md)
- [`docs/30-design/remedial/rc-16.0.0-integration-record.md`](../../docs/30-design/remedial/rc-16.0.0-integration-record.md)

## Notes carried on the item

2026-10-25, 19:22Z: #8837 ("Cut 2: page bundles and the build/runtime split
(16.0.0)") opened against dev, head ee94b148, OPEN (gh pr view 8837).
official/chore/build-runtime-separation is a fast-forward of the published
b6e8c7cd: 26 first-parent commits on top of it, 185 commits ahead of dev
a20469dc. Merges of dev: 04a7968d (eb72a1d3, 9 conflicting paths), dd2e0cfd
(93f152bd, #8834), 94242483 (a20469dc, #8835). Follow-ups: 14ba4686
(lib/d3.mjs exports bisector, curveBasis and curveMonotoneX, which #8831's
modern chart uses; without them the production main page with THEME=modern
threw while drawing the trend), 17a9d48a (page fixtures render templates with
server settings), 4354fac3 (service-worker assets test against cut 2's
worker), 1e9ea6f6 (modern theme test reads storage through cut 2's adapter),
ba32eca4 (lodash exactly 4.18.1), the CI edge commits a7eb6942, bdb6c733 and
b8ff91cb, and ee94b148 (the page-bundle budget, option A). Tests on ee94b148
(Node 24.22.1, TZ=UTC, MongoDB 7.0.43): npm test 3691/4/0, Chromium 540/0,
page-bundle budget 9/9. On b8ff91cb (host zone America/Los_Angeles): Node
22.23.4, 24.22.1 and 26.12.1 each 3542/4/4 (the two budget cases, BF-177's
test and the API3 SEARCH hook timeout), Firefox 540/0. queryLeaves checked
against traverse on 50,000 generated and 20 edge queries: 0 differences. All
figures from the PR body (the preparing session's runs). CI on ee94b148 (run
40225696687, attempts 1 and 2) failed the required check Run Tests (24, 6) and
Maintained MongoDB (26, 8.0.29): "Native env runner process contract passes
file values through nyc into a Mocha child" exceeded its 10 s timeout (3690
passing, 1 failing). tests/env-runner.test.js's nyc child case instruments all
of lib/ (.nycrc all: true) under test-ci's outer nyc; local runs without
coverage did not see it. The fix, bd941200 (peer session: --all=false on the
inner nyc, plus docs/test-specs/env-runner.md), is on wip/cut2-onto-
cut1-16.0.0 and not pushed; cut 2 also merges dev 2bc298b9 (#8838) before its
next push. git merge-tree of #8837 and #8838 was clean before #8838 merged,
and cut 2 is clean against dev 2bc298b9. 2026-10-25: cut 1 merged (RT-1,
#8828, dev eb72a1d3), so cut 2 is next on the train. A peer session is merging
dev eb72a1d3 into cut 2 on the local branch wip/cut2-onto-cut1-16.0.0 (head
pending; not pushed; official/chore/build-runtime-separation is still
b6e8c7cd). Its result, conflicts and test counts are that session's to record.
Cut 2 at d660e272 already declares axios as a runtime dependency (BFQ-176).
Blocked on cut 1 (RT-1). Third on the adopted train, as a separate low-blast-
radius release. The published cut 2 is 175 commits behind dev 153e5658 and
conflicts in fifteen paths (RT-REBASE, 2026-09-24).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-2` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
