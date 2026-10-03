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

# Review packet — BFQ-124

**BF-124 - the treatment tooltip converts a BG already in display units (issue
#5940)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/tooltip-bg-units` |
| base | `official/dev@74942ec6` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-124` is the measurement |
| semver | `patch` |
| register entries | `BF-124` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/client/renderer.js treatmentTooltip (a few lines) and a jsdom test.
Changes only the BG number in the chart tooltip of treatments with carbs or
insulin; stored data and the API are unchanged.

## Why that semver

a display fix in the browser; no stored data or API changes

## What an operator would notice

> On some Nightscout sites, when you hover over or tap a meal or bolus on
> the chart, the blood glucose (BG) value shown in the pop-up is in the
> wrong units, for example 0.3 instead of 5 mmol/L, or 1621 instead of 90
> mg/dL. It happens when your profile uses different units from the ones
> your site displays. The value you entered is stored correctly; only the
> pop-up is wrong. Check BG values in your meter or CGM app rather than this
> pop-up. The fix is not in any release yet. This is not medical advice.

## Who should review this, and why

maintainer

## What was measured

**`sh -c 'git -C externals/cgm-remote-monitor-official cat-file -e origin/dev:lib/client/renderer.js && ! git -C `** &nbsp;·&nbsp; kind: `static`

FAILS today: origin/dev's treatmentTooltip still decides the conversion from
the profile's units alone. A presence check only; it goes green when that line
changes, and the probe below is what says whether the tooltip is then right.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour is measured by tools/lab/triage-2026-09/tooltip-bg-units.js,
  which needs a cgm-remote-monitor tree with node_modules (jsdom, d3) and so
  is not a queue gate. 2026-09-25: exit 1 on v15.0.8 92d08342 and dev
  4f705217 (tooltip BG 0.3, 1621 and 90 where 5, 90 and 5 were entered); the
  four controls behave. Exit 0 on a scratch copy of dev with the fix sketch.
  The fix is done when the probe exits 0 on the candidate.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/triage-2026-09/tooltip-bg-units.js`](../../tools/lab/triage-2026-09/tooltip-bg-units.js)

## Notes carried on the item

2026-10-03 (session -d4's agent): bf/tooltip-bg-units affbc8fd, one commit on
dev 74942ec6 (lib/client/renderer.js +13/-3; new
tests/client.renderer.tooltip-units.test.js, 14 tests, 7 fail on 74942ec6 with
the register's numbers; mutation checks fail the controls). Chromium,
careportal Meal Bolus BG 5 on an mmol/L site with an mg/dL profile: dev shows
0.3, the branch 5, three runs each. Full suite 3552/0/4 (Node 22.23.2, MongoDB
7.0.43). Not pushed. Side findings: BF-157 (bubble position, filed); an
occasional first-load redirect to /profile in the harness on both trees,
possibly JL-2, not investigated. 2026-10-02 (maintainer, relayed by session
-d4): FIX IN 15.0.9; in RT-0's blocks_on. Local branch bf/tooltip-bg-units
being prepared by -d4's agent in externals/work/crm-bf124 off dev 74942ec6,
not pushed. Filed 2026-09-25 from the GitHub issue triage (issue #5940, opened
2020-09-01). Client-side only. The BG Check tooltip (addTreatmentCircles)
prints the stored value and is not affected.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-124` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
