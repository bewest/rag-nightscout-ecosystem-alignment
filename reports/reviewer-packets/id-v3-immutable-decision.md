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

# Review packet — ID-V3-IMMUTABLE-DECISION

**Decide: on an identifier match, may date, device or eventType change?**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `official/dev@fade2299` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=ID-V3-IMMUTABLE-DECISION` is the measurement |
| semver | `n/a` |

## What this changes

A decision row, no code. Its answer sets the write step's rule for
lib/api3/generic/update/validate.js (immutable fields) and for the v1 paths.

## Why that semver

a decision; the code that follows is classed in ID-FIRST-MATCH

## Who should review this, and why

maintainer, after the Loop maintainers answer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- A decision, not measurable. Today, measured 2026-10-17
  (tools/lab/v3-identifier-immutable): API v3 answers 400 and keeps one
  record; v1 treatments update created_at on the identifier match; v1
  entries store a second record.

## Blocked on

`LOOP-ID-REPLY`

## Evidence

- [`tools/lab/v3-identifier-immutable/results/v3-identifier-immutable-2026-10-17.md`](../../tools/lab/v3-identifier-immutable/results/v3-identifier-immutable-2026-10-17.md)
- [`docs/30-design/platform/upstream-asks-loop-identifier/reply.body.md`](../../docs/30-design/platform/upstream-asks-loop-identifier/reply.body.md)

## Notes carried on the item

The three paths disagree today. The reply asks Loop whether an identified
record's time can be corrected by a re-send. 2026-10-17: the rewritten Loop
reply no longer asks this; it lists the v3 immutable date and device, and
edit-versus-duplicate, under "later, only if needed". After ID-SIMPLE-MATCH, a
v1 entries re-send with the same identifier and a new time would update the
stored entry, as v1 treatments do.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=ID-V3-IMMUTABLE-DECISION` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
