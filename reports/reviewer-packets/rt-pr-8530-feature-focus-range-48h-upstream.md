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

# Review packet — RT-PR-8530 (PR #8530)

**#8530 - a 48-hour option in the focus range selector (alanshurafa), carried
into 15.0.9**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `feature/focus-range-48h-upstream` |
| base | `origin/dev@4f705217` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=RT-PR-8530` is the measurement |
| semver | `minor` |

## What this changes

One line of views/index.html: a 48 entry in the focus chart's hour selector.
Head 5353ff64, 0 behind dev 4f705217; merges cleanly with dev and with #8758
(measured 2026-09-25).

## Why that semver

An added option. The versioning policy classes a new user-visible option as
minor; 15.0.9 carries it under a patch number by the maintainer's decision
(2026-09-25), which the policy records as a departure.

## What an operator would notice

> The main chart's hour selector gains a 48-hour choice beside 24.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev refs/triage/pr-8530 >/dev/null`** &nbsp;·&nbsp; kind: `static`

#8530's head merges into origin/dev without conflict. Needs `git -C
externals/cgm-remote-monitor-official fetch official
pull/8530/head:refs/triage/pr-8530` first.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- No test covers the selector, and nobody has checked in a browser that the
  chart renders at 48 hours (the focus chart's data window and tick density
  at that range).

## Evidence

- [`releases/cgm-remote-monitor-15.0.9/contents.md`](../../releases/cgm-remote-monitor-15.0.9/contents.md)

## Notes carried on the item

Outside contributor (alanshurafa); the maintainer merged dev into it on
2026-09-24. Decided 2026-09-25 (maintainer): carry into 15.0.9.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-PR-8530` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
