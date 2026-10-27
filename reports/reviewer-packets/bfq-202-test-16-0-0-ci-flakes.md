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

# Review packet — BFQ-202 (PR #8866)

**BF-202 - CI's MongoDB 8.0 jobs fail on hosted runners with Linux 6.19 or newer
(MongoDB refuses to start, SERVER-121912)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `test/16.0.0-ci-flakes` |
| base | `official/dev@2dc0c1bc` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-202` is the measurement |
| semver | `n/a` |
| register entries | `BF-202` |

## What this changes

.github/workflows/main.yml's MongoDB 8.0 jobs, Run Tests (22.23.4, 8.0) and
Maintained MongoDB (26, 8.0.29). The diagnosis aid in #8866 is tools/wait-for-
mongodb.js (e0cfbd0c) and the mitigation f6884342 (the MongoDB 8.0 jobs run on
ubuntu-22.04).

## Why that semver

CI only

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official show test/16.0.0-ci-flakes:tools/wait-for-mongodb.js | grep -q 'o`** &nbsp;·&nbsp; kind: `static`

#8866's branch has the MongoDB wait that prints the runner's kernel
(e0cfbd0c), so a failed or passing 8.0 job records which kernel it ran on.
This is the diagnosis aid, not the fix.

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor f6884342 test/16.0.0-ci-flakes`** &nbsp;·&nbsp; kind: `static`

The mitigation is on #8866's branch: Run Tests' MongoDB 8.0 cells and
Maintained MongoDB run on ubuntu-22.04 (Linux 6.8).

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The defect is in MongoDB and in which host GitHub assigns, so it cannot be
  reproduced on demand. Seen 2026-10-27: #8866 run 40532337252 (Maintained
  MongoDB, 212 failing), #8867 run 40557880084 (Run Tests (22.23.4, 8.0)
  logged MongoDB's refusal to start on Linux 6.19 and newer while 8.0.29 in
  the same run started), #8866 run 40566855699 (both 8.0 jobs over 9 minutes
  in Run Tests, cancelled).

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-27: filed at the maintainer's request. Kernel readings on run
40569101512: both 8.0 jobs on 7.0.0-1017-azure refused to start (8.0.29
included); 5.0 and 6.0 on 6.17.0-1022-azure passed; ubuntu-24.04 image
20261026.354 moves 6.17 to 7.0. The maintainer chose a runner image with an
older kernel over an older MongoDB patch: f6884342, pushed to #8866; run
40569981396 passed both 8.0 jobs on 6.8.0-1064-azure. Revisit at kernel
7.0.14+, MongoDB support for 6.19+, or before ubuntu-22.04 is retired.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-202` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
