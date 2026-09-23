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

# Review packet — BFQ-101

**BF-101 - API v3 id filters miss records stored with a string _id**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/api3-string-id` |
| base | `origin/dev@1f9a9d10` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-101` is the measurement |
| semver | `patch` |
| register entries | `BF-101` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/api3/storage/mongoCollection/utils.js filterForOne and identifyingFilter,
plus the shared helper. Two commits, 96eaca1b and 7295bc8c.

## Why that semver

Bug fix.

## What an operator would notice

> Apps that use Nightscout's newer API cannot find, by id, records that were
> saved with a text id through the older API. This is how today's release
> (15.0.8) behaves.

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- New v3 route tests fail 9 of 10 on dev and pass on the branch; suite
  2411/0/3 on Node 20 and 22; explain() keeps IXSCAN, no COLLSCAN. No queue
  gate yet.

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf-api3-string-id.md`](../../reports/phase0-pr-bodies/bf-api3-string-id.md)
- [`docs/60-research/remedial/profile-object-id-2026-09-23.md`](../../docs/60-research/remedial/profile-object-id-2026-09-23.md)
- [`docs/60-research/remedial/object-id-other-collections-2026-09-23.md`](../../docs/60-research/remedial/object-id-other-collections-2026-09-23.md)

## Notes carried on the item

Filed 2026-09-23 beside BF-99; built the same day. Narrow alternative to
BFQ-102 (its commit e). PR body draft reports/phase0-pr-bodies/bf-api3-string-
id.md.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-101` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
