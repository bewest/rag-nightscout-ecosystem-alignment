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

# Review packet — BFQ-168

**BF-168 - the context chart's window sometimes cannot be dragged back to now**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/brush-extent` |
| base | `official/dev@43289dde` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-168` is the measurement |
| semver | `patch` |
| register entries | `BF-168` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/client/chart.js only (8 lines): the brush gets an explicit extent from the
context chart's scale and height, and chart.update() calls the brush again
when the size changes, restoring the overlay's selection datum. Tests:
tests/dependency-d3.test.js (2 new) and tests/fixtures/d3-chart.js (an
optional layout argument).

## Why that semver

a client-side display fix

## What an operator would notice

> On the main page, dragging the small chart's window to the right always
> reaches the latest reading. Before, on some page loads, mostly on phones,
> the window stopped part-way and the page stayed showing older readings
> until it was reloaded or the window was resized.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree official/dev bf/brush-extent >/dev/null`** &nbsp;·&nbsp; kind: `static`

Merges into official/dev with no conflict.

**`cd externals/work/crm-bf168 && n exec 22.23.2 npx mocha --timeout 10000 --exit tests/dependency-d3.test.js`** &nbsp;·&nbsp; kind: `unit`

The D3 chart tests, no database; 26 passing. Control, 2026-10-07: on
official/dev 43289dde the 2 new tests fail at [75, 300] (the 300 px default-
size extent); with the extent function removed they fail at [75, 300], with
the re-read in chart.update() removed at [655, 880].

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The browser half is not a gate: tools/lab/brush-extent/probe.js needs
  Playwright, a server and a MongoDB, and the unforced race shows in about 1
  load in 10. Forced (-force), dev and v15.0.8 stop at [245, 300] and the
  branch reaches now (tools/lab/brush-extent/results/).

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/brush-extent/README.md`](../../tools/lab/brush-extent/README.md)
- [`reports/phase0-pr-bodies/brush-extent.md`](../../reports/phase0-pr-bodies/brush-extent.md)

## Notes carried on the item

Filed 2026-10-07 by session -96 from a user's screen recording of dev (Firefox
on Android, landscape). Branch bf/brush-extent b919af9f, one commit on dev
43289dde, not pushed. Full suite 3566/0/4 (Node 22.23.2, MongoDB 7.0.43, dev
3564 plus 2); ESLint clean on the 3 files. Present on v15.0.8 too (2 of 12
unforced phone loads stuck); not a D3 7 regression. Whether it goes into
15.0.9 is not decided. PR body reports/phase0-pr-bodies/brush-extent.md.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-168` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
