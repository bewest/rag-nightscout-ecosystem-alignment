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

# Review packet — RT-D3

**Answer the D3 question before 15.0.9 ships**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `origin/dev` |
| base | `origin/master` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=RT-D3` is the measurement |
| semver | `minor` |
| register entries | `BF-54`, `BF-57` |

## What this changes

GT2 re-measured: commit 48075a18 touches THREE production files -
lib/client/renderer.js +25/-25, lib/client/chart.js +2/-2,
lib/report_plugins/daytoday.js +3/-3. 30 lines, not the five files the
release-readiness document lists.

## Why that semver

GT4: D3 5.16 -> 7.9 by itself moves NO declared surface, so it forces neither
minor nor major. 15.0.9 is a minor for reasons independent of D3 -
lib/server/env.js gains DEBUG_LOGGING and CONNECT_DEBUG, debug logging flips
to off by default, and a new lib/api2/loop-notification-errors.js appears.

## What an operator would notice

> The charts on the main page were rebuilt on a new version of the drawing
> library. What is being checked is whether dragging a treatment on the
> chart still behaves - because dragging one changes the time that treatment
> is recorded at, and insulin-on-board and carbs-on-board are calculated
> from that time.

## Who should review this, and why

maintainer - this is the decision the adopted train puts first

## What was measured

**`TEST=dependency-d3 npm run test-single`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/cgm-remote-monitor-official`

GT2 ran this: 24 passing, driving the REAL renderer and chart against the D3 7
browser bundle. Non-vacuous - it catches reverting mouseover handlers to the
D3-5 signature and catches breaking d3.pointer.

**`node tools/queue/gates/d3-drag-clamp-covered.js`** &nbsp;·&nbsp; kind: `static`

THE GAP. GT2 deleted BOTH treatment-drag clamps at renderer.js:764 and 770-771
and the suite stayed at 24/24 - the handler runs 25 times with only x in
{20,400}, all strictly inside 0..900, so the boundary is never reached. This
gate re-runs that ablation and FAILS while the clamps are uncovered.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- lib/plugins/cob.js +49/-73 is filed under the D3 heading in release-
  readiness §2 and is NOT D3 work - it is 34e9b2da, "fix(cob): use the COB
  reported by the uploading system". It is more than twice the size of the
  entire D3 migration, it changes what a user reads when deciding about food
  and correction, and it has no line of its own in the 15.0.9 release
  decision. Nothing gates it because nobody has decided what it is.

## Evidence

- [`docs/60-research/modernization/gt2-cut-remeasure-2026-09-15.md`](../../docs/60-research/modernization/gt2-cut-remeasure-2026-09-15.md)
- [`docs/30-design/modernization/cgm-remote-monitor-release-readiness-2026-09-14.md`](../../docs/30-design/modernization/cgm-remote-monitor-release-readiness-2026-09-14.md)

## Notes carried on the item

The clamps bound a user-initiated rewrite of a treatment's created_at emitted
over the socket, and a treatment's timestamp is what IOB/COB key off. They are
the exact lines the D3 6 migration rewrote and the least covered lines it
touched.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-D3` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-15, against cgm-remote-monitor-official `a8888f0d`.*
