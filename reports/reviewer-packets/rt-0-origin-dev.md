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

# Review packet — RT-0 (PR #8598)

**Release 15.0.9**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `origin/dev` |
| base | `origin/master` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=RT-0` is the measurement |
| semver | `minor` |

## What this changes

dev vs master. Includes four user-visible bug fixes plus i18n.

## Why that semver

GT4: cannot be a patch, for reasons INDEPENDENT of D3. lib/server/env.js gains
DEBUG_LOGGING and CONNECT_DEBUG, debug logging flips to off by default
(removing log lines an operator relies on when diagnosing), and a new API file
lib/api2/loop-notification-errors.js appears.

## What an operator would notice

> A bug-fix release. Fixes for unnamed profiles, embedded profile switch
> schedules, treatments query failures, and a clock display that now shows
> concern for a low and falling reading. Debug logging becomes opt-in, so
> your logs get quieter unless you turn it on.

## Who should review this, and why

maintainer, and at least one human reviewer who is not the author - release PR
#8598 and integration PR #8605 each carry ZERO human reviews

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/master origin/dev`** &nbsp;·&nbsp; kind: `static`

dev descends from master with no divergence to reconcile

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- CI state at dev's tip is not re-verified here. The only evidence is
  release-readiness §3's record of 21 green checks on PR #8605 as of
  2026-09-14, evaluated against the INTEGRATION branch as base, not against
  dev. Re-running it needs the full matrix (three Mongo versions, replica
  sets) and, for the browser half, three browser engines.
- RT-D3's drag-clamp gap is unresolved and this release ships the D3 7
  charts. The decision to ship anyway is the maintainer's; recording it as a
  no-gate keeps it from reading as covered.

## Blocked on

`RT-D3`, `RT-VERSION`

## Evidence

- [`docs/30-design/modernization/cgm-remote-monitor-release-readiness-2026-09-14.md`](../../docs/30-design/modernization/cgm-remote-monitor-release-readiness-2026-09-14.md)
- [`docs/60-research/modernization/gt4-semver-classification-2026-09-15.md`](../../docs/60-research/modernization/gt4-semver-classification-2026-09-15.md)

## Notes carried on the item

First on the adopted train. Phase 0's branches target dev, so landing them
changes what 15.0.9 contains - that collision is why there is one queue.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-0` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-15, against cgm-remote-monitor-official `a8888f0d`.*
