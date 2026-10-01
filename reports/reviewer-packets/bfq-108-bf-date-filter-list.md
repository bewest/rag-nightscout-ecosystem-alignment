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

# Review packet — BFQ-108

**BF-108 - a list of timestamps under the date field answers 500, so bulk
deletes by timestamp do nothing**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/date-filter-list` |
| base | `official/dev@3014f883` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-108` is the measurement |
| semver | `patch` |
| register entries | `BF-108` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/server/query.js enforceDateFilter: each element of a list operand ($in,
$nin) under the date field goes through the single-date rewrite (new
normalizeDate, the old body unchanged); single operands unchanged. Tests in
tests/query.test.js (3) and tests/api.entries.test.js (1). Branch bf/date-
filter-list 350f6f09, one commit on dev 3014f883, local worktree
externals/work/crm-bf108, not pushed.

## Why that semver

a bug fix; the request answers 500 today

## What an operator would notice

> If you use xDrip4iOS, readings it asks Nightscout to delete in bulk stay
> on your site. Nothing is lost or changed; the extra readings are ones the
> app meant to remove.

## Who should review this, and why

maintainer

## What was measured

**`node tools/queue/gates/bf108-date-in-list.js --ref bf/date-filter-list`** &nbsp;·&nbsp; kind: `static`

Builds the entries query from the fix branch's own query.js with a two-
timestamp find[date][$in]; its control is the same filter with one timestamp.
GREEN on bf/date-filter-list 350f6f09; RED on v15.0.8, dev ddd9b600, 3014f883
and the candidate 1067e668 (run without --ref it measures origin/dev). Once
merged, measure origin/dev again.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The tests need MongoDB and a tree with node_modules, so they are not a
  queue gate. 2026-09-30 in externals/work/crm-bf108 (Node 22.23.2, MongoDB
  7.0.43, dedicated container): tests/query.test.js and
  tests/api.entries.test.js 65 passing on the branch; with 3014f883's
  query.js 61 passing and the 4 new tests failing. Full suite 3485/0/3 (3481
  on 3014f883). A DELETE listing 50 of 60 posted readings deletes those 50
  (deletedCount 50, 10 left).

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/60-research/remedial/consumer-impact-15.0.9-2026-09-23.md`](../../docs/60-research/remedial/consumer-impact-15.0.9-2026-09-23.md)

## Notes carried on the item

2026-09-30: fixed on local branch bf/date-filter-list 350f6f09 (one commit on
dev 3014f883), not pushed; PR body draft reports/phase0-pr-bodies/date-filter-
list.md. Whether it goes into 15.0.9 is the maintainer's call (not in RT-0's
blocks_on). Reproduced 2026-09-23 by the consumer-replay lab on v15.0.8, dev
ddd9b600 and the candidate, with a one-value control; the gate is red on
origin/dev 153e5658 (2026-09-24). xdripswift c268542e
NightscoutSyncManager.swift:794-806 is the client that sends it. Filed by
session -6a.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-108` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
