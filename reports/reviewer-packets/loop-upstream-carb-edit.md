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

# Review packet — LOOP-UPSTREAM-CARB-EDIT

**Loop 3.14.9 drops a carb edit when the record's _id is no longer in its 24 h
cache (raised with the Loop maintainers)**

| | |
|---|---|
| repository | `LoopKit/NightscoutService` |
| branch | `` |
| base | `LoopWorkspace v3.14.9 548b332` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=LOOP-UPSTREAM-CARB-EDIT` is the measurement |
| semver | `n/a` |

## What this changes

Loop's Nightscout upload (NightscoutService, NightscoutKit): a carb edit is
sent as a v1 PUT by an _id cached for 24 hours; when the _id is not cached the
edit is not sent. Nothing in cgm-remote-monitor changes.

## Why that semver

a client behaviour, raised upstream; nothing ships from here

## What an operator would notice

> If a carb entry is edited in Loop more than a day after it was first
> uploaded, the change can be missing from Nightscout, which keeps showing
> the old amount or time. Loop's own records are not affected.

## Who should review this, and why

the Loop maintainers

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Read from Loop source at LoopWorkspace v3.14.9 (client survey, finding 4:
  NightscoutUploader.swift:30-50, NightscoutService.swift:27, 227,
  NightscoutClient.swift:83-85), not run. Whether Loop changes it cannot be
  checked from here.

## Evidence

- [`docs/60-research/tenancy/identity-resend-survey-2026-10-29.md`](../../docs/60-research/tenancy/identity-resend-survey-2026-10-29.md)
- [`docs/30-design/platform/upstream-asks-loop-identifier/reply.body.md`](../../docs/30-design/platform/upstream-asks-loop-identifier/reply.body.md)
- [`docs/30-design/platform/upstream-asks-loop-identifier/README.md`](../../docs/30-design/platform/upstream-asks-loop-identifier/README.md)

## Notes carried on the item

Raised 2026-10-29 in the published reply's caution ("A carb edit can be lost")
and recorded in the Loop dialogue page's conversation table. With identifier-
first (ID-FIRST-MATCH), a PUT or re-send by syncIdentifier would not need the
cached _id; that is Loop's choice.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=LOOP-UPSTREAM-CARB-EDIT` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
