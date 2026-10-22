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

# Review packet — BFQ-157 (PR #8827)

**BF-157 - a treatment's glucose bubble is placed as mg/dL when its units are
spelled mmol/L**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/treatment-bubble-units` |
| base | `official/dev@04d435eb` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-157` is the measurement |
| semver | `patch` |
| register entries | `BF-157` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/report_plugins/utils.js:69-77 and lib/data/treatmenttocurve.js:66: read
the units with the same normalisation BF-124's fix uses. The branch changes
those two files (+7/-3) and adds 8 tests (tests/data.treatmenttocurve.test.js,
tests/report-utils.treatment-units.test.js).

## Why that semver

a display position

## What an operator would notice

> On a site that shows mmol/L, a treatment saved with its glucose in
> "mmol/L" could be drawn in the wrong place on the chart. The number itself
> is not affected.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor official/dev bf/treatment-bubble-units`** &nbsp;·&nbsp; kind: `static`

the branch contains official/dev (04d435eb on 2026-10-21), so it can be pushed
without a further merge; goes red when dev moves ahead

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The defect was read, not run, on dev 74942ec6; the fix is covered by its 8
  unit tests (full suite 3577/0/4 on a9c6b3d1) and was not measured in a
  browser.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-21 (later): pushed by the maintainer and opened as #8827 against dev
(bf/treatment-bubble-units, head a9c6b3d1; checked with gh). 2026-10-21:
bf/treatment-bubble-units a9c6b3d1, on dev 04d435eb
(lib/data/treatmenttocurve.js and lib/report_plugins/utils.js, +7/-3; 8
tests); full suite 3577/0/4; not measured in a browser; not pushed. A similar
exact match, units == 'mmol', converts temp targets in lib/data/ddata.js:466,
where a below-20 check catches mmol/L values whatever the spelling; filed as
candidate BF-175 (BFQ-175), not changed on this branch. Filed 2026-10-03 from
session -d4's BF-124 work. Not decided for 15.0.9.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-157` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
