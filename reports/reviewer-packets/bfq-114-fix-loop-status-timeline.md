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

# Review packet — BFQ-114 (PR #8568)

**BF-114 - an AAPS open-ended loop disable keeps loop and pump alerts off after
the loop is back on**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `fix-loop-status-timeline` |
| base | `origin/dev@4f705217` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-114` is the measurement |
| semver | `patch` |
| register entries | `BF-114` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

PR #8568 (outside contributor, head de8efff0, 0 behind dev): lib/data/ddata.js
normalizeAapsRunningModes, called from processTreatments; tests/ddata.test.js;
and removal of an unused convertToRanges wrapper in
lib/profile/profileeditor.js (dev fails eslint no-unused-vars on it; #8605
makes the same deletion).

## Why that semver

a bug fix in how existing records are read; nothing stored changes

## What an operator would notice

> If you use AndroidAPS and have turned the loop off without an end time,
> then turned it back on, Nightscout may still treat the loop as
> deliberately off. While it does, it does not warn you that the loop has
> stopped running and does not raise pump alerts, and nothing on the page
> says so. Keep the alerts on your phone and pump switched on. The fix is
> not in 15.0.9 yet.

## Who should review this, and why

maintainer, plus someone who runs AndroidAPS

## What was measured

**`git -C externals/cgm-remote-monitor-official grep -q DISABLED_LOOP origin/dev -- lib/`** &nbsp;·&nbsp; kind: `static`

FAILS today: nothing in origin/dev's lib/ handles an AAPS DISABLED_LOOP
record. A presence check only; it goes green when handling lands, and the
probe below is what says whether it works.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour is measured by tools/lab/aaps-offline/probe.js, which needs
  a cgm-remote-monitor tree with node_modules and so is not a queue gate.
  2026-09-25: exit 1 on v15.0.8 92d08342, dev 4f705217 and #8568 de8efff0
  (the last clears the released-AAPS shape but not the AAPS-dev shape); both
  controls behave on all three. The fix is done when the probe exits 0 on
  the candidate.
- Nothing tests the alert level itself or the day-to-day report, which reads
  raw records and still draws the disable open-ended. A test in
  tests/openaps.test.js asserting the level after a re-enable is the missing
  piece.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/aaps-offline/probe.js`](../../tools/lab/aaps-offline/probe.js)

## Notes carried on the item

Open upstream as #8568 (lejcey, opened 2026-07-24), not merged; filed
2026-09-25 from the open-PR triage. Loop's indefinite overrides (durationType
indefinite) have been handled in lib/client/renderer.js since 13.0.0; this is
a different record, and nothing on any branch handled it before #8568.
Suggested to the contributor: also match the AAPS-dev shape (DISABLED_LOOP,
originalDuration 0, a very long duration) and add an alert-level test. Decided
2026-09-25 (maintainer): carry #8568 into 15.0.9; the contributor is asked to
also match the AAPS-dev shape and add an alert-level test.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-114` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
