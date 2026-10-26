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

# Review packet — ARCH-8854-FAILED

**Decide: the socket's failed slot that #8854 adds under WRITE_VALIDATION=reject
- ship as is, or agree it alongside refused (and on API v1?)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `official/dev@7ad3a67f` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=ARCH-8854-FAILED` is the measurement |
| semver | `n/a` |

## What this changes

lib/server/websocket.js on dev 7ad3a67f (:557-563 unconfirmedTreatmentWrite,
:634-644, :721-723, :784-785, :804-807): socket treatment array replies under
WRITE_VALIDATION=reject. API v1's batch reply (#8841's refused slots) has no
failed member.

## Why that semver

inside the 16.0.0 major; a decision about a reply member already on dev

## What an operator would notice

> Nothing changes unless WRITE_VALIDATION=reject is set. With it, when
> Nightscout cannot confirm that a treatment sent over the realtime socket
> was saved, the reply now says so for that item instead of leaving it out.
> Whether apps are told about this shape in the release notes as it is, or
> it is first agreed with app developers, is open.

## Who should review this, and why

maintainer, and the AndroidAPS, Loop and Trio developers on the reply shape

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- A decision item. The behaviour is read from 246313e4 and not measured: the
  client replay and the socket probe (integration record R16) inject no
  storage faults. A gate, once decided, would force an insert error on a
  socket treatment array under reject and assert the slot shape; control:
  dev 47723cda, where the item drops out of the reply.

## Blocked on

`ARCH-8854`

## Evidence

- [`docs/30-design/remedial/rc-16.0.0-integration-record.md`](../../docs/30-design/remedial/rc-16.0.0-integration-record.md)
- [`releases/cgm-remote-monitor-16.0.0/decisions.md`](../../releases/cgm-remote-monitor-16.0.0/decisions.md)

## Notes carried on the item

Filed 2026-10-26 from session -66's review of the merged #8854 (ARCH-8854's
notes). Options: (a) list failed in the 16.0.0 client notes as it is; (b)
agree it alongside refused before the tag, and decide whether API v1's batch
reply should carry the same member. Not asked for in the four outcome-B
points.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=ARCH-8854-FAILED` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
