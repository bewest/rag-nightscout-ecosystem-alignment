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

# Review packet — BFQ-95

**BF-95 - an uploader clock running ahead delays the stale-data alarm**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `origin/dev@74fc6619` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=BFQ-95` is the measurement |
| semver | `minor` |
| register entries | `BF-95` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/sandbox.js lastEntry, lib/plugins/timeago.js checkStatus. v1 entries store
no server-receipt time (lib/server/entries.js:118-126), so an arrival-based
check needs new data.

## Why that semver

any fix changes when an alarm that is on by default fires

## What an operator would notice

> If the phone or device uploading your readings has its clock set ahead of
> the real time, Nightscout treats each reading as newer than it is. If your
> readings then stop, the stale-data warning comes late, by roughly how far
> ahead that clock is: an hour fast means the 15-minute warning comes after
> about an hour and a quarter. Check the date, time and time zone on the
> uploading device, and have another way to notice that readings have
> stopped. This is not medical advice; talk to your care team about what you
> rely on Nightscout for.

## Who should review this, and why

maintainer - a design decision before code

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Characterised by tools/remedial/bf3/bf41-real-sandbox.js cases F7 and F8
  (it always exits 0 - a characterisation, not a gate). A gate needs the
  decided product first, because which way it should go red depends on it.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/60-research/remedial/bf41-future-reading-2026-09-23.md`](../../docs/60-research/remedial/bf41-future-reading-2026-09-23.md)

## Notes carried on the item

Filed 2026-09-23 from the BF-41 measurement (F7/F8) when BF-41 was closed.
Open, needs a design decision; one option is a notice for readings that arrive
already ahead of the clock (evidence section 5, option 3). 15.0.9 carries it
as a known issue. BF-44 (BFQ-MINIMED) is a shipping source of forward skew.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-95` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-23, against cgm-remote-monitor-official `4011193e`.*
