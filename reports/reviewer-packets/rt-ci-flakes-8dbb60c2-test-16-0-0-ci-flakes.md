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

# Review packet — RT-CI-FLAKES-8DBB60C2 (PR #8866)

**dev 8dbb60c2's red CI: a concurrent-writes timestamp collision and the WebKit
reports-page race**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `test/16.0.0-ci-flakes` |
| base | `official/dev@8dbb60c2` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=RT-CI-FLAKES-8DBB60C2` is the measurement |
| semver | `n/a` |

## What this changes

Two test files, no production source: tests/concurrent-writes.test.js
(c7857735) and tests/browser/page-startup.test.js (bdd569a3).

## Why that semver

test reliability

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor c7857735 test/16.0.0-ci-flakes`** &nbsp;·&nbsp; kind: `static`

The concurrent-writes fix is on the branch: ten Notes get times one second
apart, so none share the created_at and eventType a Note without an identifier
is matched on.

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor bdd569a3 test/16.0.0-ci-flakes`** &nbsp;·&nbsp; kind: `static`

The page-startup fix is on the branch: the reports page counts as ready once
its deferred first-week report has loaded (dates filled, Show visible, no
jQuery request in flight).

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The WebKit failure was not reproduced locally before or after the fix (CI
  image mcr.microsoft.com/playwright:v1.63.0-noble, Node 26.12.1): the
  mechanism, requests cancelled by navigating away from /report/, is read
  from the job log and the code. After the fix, page-startup.test.js passes
  3 of 3 on WebKit, Chromium and Firefox, 28 passing each. The concurrent-
  writes collision is reproduced: with every Note at one time the test
  fails, expected 1 to be 10; the fix passes 30 of 30 on Node 22.23.4 and
  MongoDB 5.0.33.

## Evidence

- [`docs/30-design/remedial/rc-16.0.0-integration-record.md`](../../docs/30-design/remedial/rc-16.0.0-integration-record.md)

## Notes carried on the item

2026-10-27: dev 8dbb60c2 (#8860) push run 40424319822 failed Browser tests
(26, webkit) and Run Tests (26, 5.0), and pull_request run 40424329138 failed
WebKit; #8860's own run on the identical tree passed. Neither failure is
#8860's: the suites on 8dbb60c2 pass on Node 22.23.4 with MongoDB 5.0.33 and
Node 26.12.1 with 8.0.34 (integration record R17). Branch prepared off
official/dev 8dbb60c2 by session d22eceb7 in externals/work/crm-ci-flakes; not
pushed. The page-startup change may also explain R14's Chromium "recovers the
actual reports page after two failed bundle downloads" timeout, which leaves
the same page; not measured.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-CI-FLAKES-8DBB60C2` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
