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

# Review packet — RT-CI-DIAGONAL (PR #8843)

**CI runs the Node x MongoDB diagonal, the no-database tiers on their own, a
Tests pass check and seeded test-file order**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `ci/edge-diagonal-matrix` |
| base | `official/dev@b29f1bf7` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=RT-CI-DIAGONAL` is the measurement |
| semver | `n/a` |

## What this changes

CI, test scripts and tests only. .github/workflows/main.yml: Run Tests runs
the integration and stress tiers on (22.23.4, 8.0) and (26, 5.0) (the extended
run keeps every pair); a new test-no-db job runs unit, dom, dependency, core
and harness on Node 22.23.4 and 26 with no MongoDB; maintained-mongo runs (26,
8.0.29) only; each diagonal cell takes TZ=America/Los_Angeles or a seeded file
order; a Tests pass job needs every test job and docker-build waits on it; the
(24, 6) and (22, 6) cells stay until branch protection changes. New
.github/workflows/extended-weekly.yml dispatches the extended run on dev every
Monday (starts once on master). scripts/test-tiers.js gains TEST_SHUFFLE_SEED.
Fixes six tests that passed only in alphabetical order (loop and openaps
plugin-wiring, storage.shape-handling, api3.search, security, api.count-where)
and makes the stress tier remove the records it writes (BF-185; XX_clean also
wipes devicestatus). CONTRIBUTING.md, docs/runtime-upgrade.md and docs/test-
specs/maintained-mongodb.md describe the new jobs. Drops the replica-set job
(maintainer; the validator stays in tools/). Sets fail-fast: false on the two
diagonal matrices. Fixes browser CI, which ran no tests since #8839.

## Why that semver

CI and test infrastructure; no product code changes

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- To write when the PR opens: on the branch, TEST_SHUFFLE_SEED=40226791404
  node scripts/test-tiers.js run integration,stress against an empty MongoDB
  exits 0, with the branch's test fixes reverted as the red control (35
  failing on 2026-10-25: 33 API3 SEARCH, 2 API_SECRET); and
  TEST_SHUFFLE_SEED=5 node scripts/test-tiers.js run core exits 0, red with
  b0d6ef7a reverted (4 failing).

## Evidence

- [`releases/cgm-remote-monitor-16.0.0/decisions.md`](../../releases/cgm-remote-monitor-16.0.0/decisions.md)

## Notes carried on the item

2026-10-25, night: pushed by the maintainer; #8843 head 7fd2415e, every CI
lane passes including Tests pass: Tests without a database (22.23.4, 26); Run
Tests (22.23.4, 8.0), (26, 5.0), (24, 6), (22, 6); Maintained MongoDB (26,
8.0.29); browsers chromium, firefox and webkit each 26 files, 554 passing;
Docker amd64/arm64, npm 12, CodeQL. Waiting on the maintainer's merge;
recommended to merge before cuts 3-5 so their CI runs the browser tier and the
shuffled, DST lanes. 2026-10-25, night: #8843 at 0a33b7c7 failed only Browser
tests (26, webkit), twice (run and re-run), on the profile-settings treatment
editor case: the fixture server 404s /images/report-edit.png and WebKit gives
a broken <img> without alt no box, so the edit icon is never visible (20 of 20
local failures in mcr.microsoft.com/playwright: v1.63.0-noble). Our test, not
GitHub. Fixed locally in 7fd2415e (the fixture serves static/images PNGs by
base name): 5 of 5 on each engine; the whole browser tier on WebKit in that
container: 554 passing. Ready to push (fast-forward over 0a33b7c7).
2026-10-25, night: the maintainer chose to fold the BF-192 budget change into
#8843 (rather than a separate PR or merging red). Local 0a33b7c7 over
e767ce4e, ready to push: page-populated waits for the reports page's first
report (svg under #pluginchartplaceholders and an empty #info);
heapLimits.reports 4,850,000 -> 6,800,000, 1.097 x the max of seven samples on
428b20b7 (6,181,516 to 6,197,116); spec docs/test-specs/page-bundles.md
records it. Evidence it is the screen, not the cost: #8542 draws the first
report on load (loadInitialReport -> show()); retained heap loaded 4.43 ->
6.19 MB, after one Show 9.24 -> 7.18 MB, after five 9.93 -> 7.46 MB (b29f1bf7
-> 428b20b7); D3 7.9.0 on both; reports bundle +36 KB; snapshot growth is 576
SVG circles, about 4,000 Dates, DOM 873 -> 2,756 elements. Open: both
revisions retain about 170 KB (before) and 70 KB (after) more per further
Show. page-populated passes on Chromium and Firefox locally; WebKit could not
launch locally (missing libavif16). 2026-10-25, evening: pushed by the
maintainer; #8843 head e767ce4e. CI (run on e767ce4e): every lane passes
except Browser tests (26, chromium), which runs 26 files, 553 passing, 1
failing: reports retained heap 6189016 > 4850000 (BF-192, filed by session
-f4). Firefox 554 passing and WebKit 554 passing, so the browser tier runs
again (it printed no "# browser:" line before the fix). No replica-set lanes.
Tests pass fails on the Chromium lane, as designed. The heap budget is
tools/page-resource-acceptance.js heapLimits.reports (AndyLow91, 79864ce8,
from docs/audits/page-startup-baseline.json); #8542 also moved D3 from v5 to
v7 (3a4621af). Waiting on the maintainer: raise the budget from a fresh
measurement, or slim the reports page. 2026-10-25, evening: local update ready
to push at e767ce4e over #8843's 57717695 (fast-forward): replica-set job
dropped (Ben: "I thought we decided against need for testing against
replicaset?" - the earlier "except replica set" meant drop it, not leave it);
fail-fast off; two more order fixes from #8843's first CI run (ar2 after
simplealarms' mmol suite, seed 40252793228; both boluscalc quick-pick tests
after clock-token-link, seeds 9 and 11); dev 428b20b7 merged in. Session -f8
found browser CI has run zero tests since #8839 (78524be4): git refused the
checkout as root in the Playwright container (dubious ownership),
listTestFiles ignored git's exit status, the tier had no members and the job
passed. Fixed (e767ce4e): listTestFiles throws, run() exits 2 on a git failure
or an empty requested tier, the browser job sets system safe.directory; red
control in node:24 as root (0 files and exit 0 before, exit 2 after, 319 files
with safe.directory) and a new harness test red against the old runner. That
exposes dev 428b20b7's page-populated failure on Chromium (reports retained
heap 6189888 > 4850000; about 4.45 MB on b29f1bf7; likely #8542), being filed
by -f4; the budget-or-page decision is the maintainer's, and #8843 stays red
on Chromium until it is made. Local on the merge: all four CI cells and seeds
9 and 11 pass; Chromium browser tier 553 passing, 1 failing (the heap test).
2026-10-25: pushed by the maintainer; PR #8843 to dev at 57717695. GitHub
created the diagonal as intended: Run Tests (22.23.4, 8.0), (26, 5.0), (24, 6)
and (22, 6); Tests without a database (22.23.4) and (26); Maintained MongoDB
(26, 8.0.29). 2026-10-25, later: ready to push at 57717695 (11 commits over
dev b29f1bf7, dev unmoved). BF-185 (filed by session -f4 on records/f4-2510,
not on main yet, so not in register: above): the stress tier left 10
devicestatus records that API3 SEARCH counted; the victim side is b9b5ef29,
the polluter side 57717695. The five shuffled seeds that timed out under load
(555, 8, 11, 12, 13) all pass run one at a time on Node 22.23.4 against
MongoDB 8.0. Final pass on 57717695 (load average about 8): the no-database
tiers on 22.23.4 in America/Los_Angeles and on 26.12.1 with seed 40226791404
(unit 1218, dom 160, dependency 340 + 3 pending, core 316, harness 70);
integration and stress on (22.23.4, MongoDB 8.0) with seed 40226791404 and on
(26.12.1, MongoDB 5.0) in America/Los_Angeles (1994 + 1 pending, stress 18).
Maintainer pushes. 2026-10-25: decided by the maintainer in session -5e
("build the branch with all seven; except replica set"); the decisions row is
on records/16.0.0-cuts-2510 (session -f8's 16.0.0 records, landing after cut
5). Local branch ci/edge-diagonal-matrix, 9 commits over dev b29f1bf7 (head
b9b5ef29), not pushed, no PR. Measured locally (Node 22.23.4, 24.22.1 and
26.12.1 official tarballs; MongoDB 5.0, 7.0.43 and 8.0 containers): the no-
database tiers pass on 22.23.4 in America/Los_Angeles and on 26.12.1 shuffled
(core after the wiring fix); the core tier passes under 21 seeds; integration
and stress pass in fixed order on (22.23.4, 8.0) and on (26.12.1, 5.0) in
America/Los_Angeles. Before the integration fixes seed 40226791404 failed 35
every time; after them 11 of 16 shuffled runs passed and every failure in the
other 5 was a timeout while the machine's load average was 26 to 52 on 16
cores; the fixed-order run failed the same way under that load. Serial re-runs
of those seeds pending. Coordination: cut 3 to 5 catch-ups (session -f8) keep
dev's main.yml, so whichever lands second merges the other's. The answer to
"do feature branches need the full suite": keep it on PRs to dev (about 3
minutes per lane, lanes in parallel; selection cannot see cross-file state,
which is what the shuffle found); test:affected --since official/dev belongs
in the pre-push check.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-CI-DIAGONAL` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
