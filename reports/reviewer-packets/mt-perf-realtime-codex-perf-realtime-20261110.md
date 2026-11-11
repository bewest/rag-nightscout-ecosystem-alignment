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

# Review packet — MT-PERF-REALTIME

**Realtime publishes on change; event-driven authorization; queued connects
under pool pressure**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `codex/perf-realtime-20261110` |
| base | `official/workspace/multitenant-20261102@16a1fc2d45e59602eb6ec3e3bf6f506f35bcc5b1` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=MT-PERF-REALTIME` is the measurement |
| semver | `n/a` |
| register entries | `BF-233` |

## What this changes

Multitenant only. Change detection by tenant write clock per interval, frames
only on view change, authorization at connect, expiry and events, connects
queued instead of disconnected.

## Why that semver

unreleased preview

## Who should review this, and why

maintainer; architecture review

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Measured in the lane record; frozen-head acceptance at the next #8898
  batch join.

## Blocked on

`MT-EVALUATOR-PARTITION`

## Evidence

- [`reports/tenancy/perf-realtime-2026-11-10/README.md`](../../reports/tenancy/perf-realtime-2026-11-10/README.md)

## Notes carried on the item

2026-11-10: lane head 6f31c94b; idle frames 20 to 0 per socket-minute,
realtime DB-ms 1,307 to 8 per minute at 1x20. BF-233 open.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-PERF-REALTIME` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
