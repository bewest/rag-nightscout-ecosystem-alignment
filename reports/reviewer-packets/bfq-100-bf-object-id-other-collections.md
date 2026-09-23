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

# Review packet — BFQ-100

**BF-100 - devicestatus, food and activity store a hex _id as a string**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/object-id-other-collections` |
| base | `origin/dev@1f9a9d10` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-100` is the measurement |
| semver | `patch` |
| register entries | `BF-100` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/server/devicestatus.js, food.js and activity.js create, update, remove and
find[_id], plus the shared helper lib/server/object-id-forms.js. Two commits,
1a445864 and 2fac53f5.

## Why that semver

Bug fix, same shape as BF-99.

## What an operator would notice

> Records sent with their own id by another program can end up impossible to
> delete by that id, and editing a food or activity record that way adds a
> second copy. This is how today's release (15.0.8) behaves.

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- New tests fail 27 of 31 on dev 1f9a9d10 and pass on the branch; suite
  2432/0/3 on Node 20 and 22. No queue gate runs them yet.

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf-object-id-other-collections.md`](../../reports/phase0-pr-bodies/bf-object-id-other-collections.md)
- [`docs/60-research/remedial/profile-object-id-2026-09-23.md`](../../docs/60-research/remedial/profile-object-id-2026-09-23.md)
- [`docs/60-research/remedial/object-id-other-collections-2026-09-23.md`](../../docs/60-research/remedial/object-id-other-collections-2026-09-23.md)

## Notes carried on the item

Filed 2026-09-23 beside BF-99; built the same day. Narrow alternative to
BFQ-102, which includes it as commit c. devicestatus has no create guard; the
connector's in-process output does not re-send (strict created_at watermark,
measured). PR body draft reports/phase0-pr-bodies/bf-object-id-other-
collections.md.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-100` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
