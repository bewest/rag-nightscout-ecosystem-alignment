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

# Review packet — BFQ-185 (PR #8843)

**BF-185 - the stress test tier leaves devicestatus documents that break
api3.search in a later run**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `ci/edge-diagonal-matrix` |
| base | `official/dev@b29f1bf7` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-185` is the measurement |
| semver | `n/a` |
| register entries | `BF-185` |

## What this changes

Tests only: the stress tier (polluter) and tests/api3.search.test.js before()
(victim). No product code.

## Why that semver

test only

## What an operator would notice

> Nothing an operator runs changes. Contributors running the tests locally
> can see API v3 search tests fail depending on file order.

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Reproduced 2026-10-25 on dev b29f1bf7 (test:stress then api3.search, 28
  failing, "expected 20 to be 10") and by session -b7 on MongoDB 7.0. The
  victim-side fix b9b5ef29 on session -b7's local ci/edge-diagonal-matrix
  passes 151 in the same sequence; the gate is that sequence, control dev
  b29f1bf7.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-25: both fixes are in PR #8843 to dev (session -b7's CI matrix PR),
head 57717695: victim b9b5ef29, polluter 57717695. Filed 2026-10-25 by session
f4 from the resilience lane's smoke run. Both sides are fixed on session -b7's
local ci/edge-diagonal-matrix: victim b9b5ef29 (api3.search starts empty) and
polluter 57717695 (concurrent-writes.test.js afterEach and XX_clean remove
devicestatus and entries; the stress tier leaves 0 on MongoDB 7.0). Closes
with that PR.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-185` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
