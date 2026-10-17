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

# Review packet — ID-FORMAT-DECISION

**Decide: the client identifier's format (opaque string with limits; UUID
recommended, not required)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `official/dev@fade2299` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=ID-FORMAT-DECISION` is the measurement |
| semver | `n/a` |

## What this changes

A decision row, no code. Its answer sets ID-VALIDATE's limits and
ID-V1-LOOKUP's matching, and is published in the API description.

## Why that semver

a decision; the code that follows is classed in ID-VALIDATE and ID-V1-LOOKUP

## Who should review this, and why

maintainer, after the Loop maintainers answer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- A decision, not measurable. Proposed 2026-10-17 in the Loop reply:
  identifier is a non-empty string with a length limit and character set;
  the recommended form is a UUID, v5 of a source-derived key when several
  devices must agree, v4 created once for manual entries; the server never
  depends on its shape; one identifier names one record, the client's
  responsibility. Open: the limit, the character set, and whether the server
  compares UUIDs without regard to case.

## Blocked on

`LOOP-ID-REPLY`

## Evidence

- [`docs/30-design/platform/upstream-asks-loop-identifier/reply.body.md`](../../docs/30-design/platform/upstream-asks-loop-identifier/reply.body.md)
- [`docs/60-research/tenancy/identifier-duplicates-2026-10-17.md`](../../docs/60-research/tenancy/identifier-duplicates-2026-10-17.md)

## Notes carried on the item

Today: v1 recognises only UUID-shaped values as identifiers in by-id routes
(UUID_RE, case-insensitive, lib/server/query.js:12 at dev fade2299), while
stored identifiers are compared exactly, so Loop's upper-case override UUIDs
match only themselves. API v3 computes uuid.v5(device_date[_eventType],
"NightscoutRocks!") when none is sent (lib/api3/shared/operationTools.js:6,
106). A random UUID cannot serve the phone-and-watch case, where both devices
must derive the same value; AndroidAPS keys on pump event ids. Not required:
changing an existing client's identifiers, which would break matching against
records it already stored.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=ID-FORMAT-DECISION` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
