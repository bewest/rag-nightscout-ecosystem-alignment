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

# Review packet — BFQ-207

**BF-207 - sensor age keeps the earliest of a same-hour burst of Sensor Starts;
the newest is intended**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-views-data` |
| base | `official/dev@db3b9e4e` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-207` is the measurement |
| semver | `patch` |
| register entries | `BF-207` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/plugins/sensorage.js (:84-100), the event-replacement rule.

## Why that semver

the intended value, decided by the maintainer; a sensor-age alarm can move by
up to the burst's spread

## What an operator would notice

> If a sensor start is entered several times within a few seconds, the
> sensor start date shown can be the first entry instead of the last. The
> sensor-age alarms are not affected.

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Observed 2026-10-27 by session -65's ST-VIEWS census on a corpus fixture.
  A gate replays a same-hour burst, and one crossing an hour boundary, and
  asserts the newest start is reported; dev db3b9e4e is its failing control.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-27: fixed on local bf/16.0.0-views-data by session -65 (commit
80a414c7; branch head 80a414c7, four commits on dev db3b9e4e, not pushed; the
maintainer asked for a branch and PR). The four new test files, re-run by
session -4f in its own worktree: 39 passing on the branch, 7 failing with lib/
at db3b9e4e. Corrections are in the register entry. Filed 2026-10-27 by
session -4f. Intended behaviour ("latest is correct") decided by the
maintainer in session -65, relayed. ST-VIEWS' bounded view differs from the
resident value here by design.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-207` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
