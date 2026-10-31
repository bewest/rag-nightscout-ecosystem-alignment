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

# Review packet — UI-DRAWER-RESIZE (PR #8882)

**A drawer opened in a narrow window keeps its narrow size when the window grows
(inline pixel sizes set once in openDrawer)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `hygiene/dev-lint-overlay` |
| base | `official/dev` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=UI-DRAWER-RESIZE` is the measurement |
| semver | `patch` |

## What this changes

lib/client/browser-utils.js openDrawer (about lines 126-160) sets inline width
and height in pixels from the window size when a drawer opens, and no resize
handler recomputes them. Shared by every drawer (settings, careportal, bolus
calculator, admin notifications) in both themes; from 9aab137b (2016-02-17).

## Why that semver

display fix, no data or API change

## What an operator would notice

> none (browser display only)

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- not built yet; the fix's gate is a browser test that opens a drawer at 390
  px, resizes to 1440 px and asserts the drawer's size, red on dev

## Evidence

_None cited in the manifest._

## Notes carried on the item

2026-10-30: fixed in #8882 (cd42dfce) for height changes; a width change
closes the drawer by design since 2016 (chart.js:349-351), kept (maintainer).
Browser test red on dev, suite 679 passing in chromium and firefox.
2026-10-30: seen by the maintainer in the journey-lab session on the modern
theme (relayed by session -7d); identical on dev 305a6533 and #8874 7463e76d,
so not an #8874 regression; the modern theme makes it more visible. Fix
options: size open drawers with CSS (e.g. width: min(350px, 100vw), a dvh-
based height) instead of inline pixels, or re-apply the sizing on resize while
a drawer is open. Being built as a second commit on the hygiene branch with
DEV-LINT-OVERLAY-REGEX.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=UI-DRAWER-RESIZE` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
