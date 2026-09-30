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

# Review packet — RT-PR-8788 (PR #8788)

**#8788 - the Day to Day report draws an event with a duration on every day it
covers (awss1i; BF-148, fixes #8223); open, 15.0.9 or after is the
maintainer's call**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `awss1i:wip/daytoday-duration-past-midnight` |
| base | `origin/dev@7000eb18` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=RT-PR-8788` is the measurement |
| semver | `patch` |
| register entries | `BF-148` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/report_plugins/daytoday.js only in code (+55/-97): the five copies of the
duration-band code become appendDurationBand, reached through
appendDurationEvent; each band is clipped to its day; after the day's own
treatments, drawChart draws events from datastorage.treatments that began
before the day and are still running at its start (insulin, carbs, temp
basals, combo boluses, profile switches, and notes with Notes off are
skipped). Plus tests/report-daytoday-durations.test.js (jsdom), CHANGELOG.md
[Unreleased] and docs/test-specs/manual-smoke-checklist.md. Browser-side only:
the report bundle changes, the server does not.

## Why that semver

a report draws what it already loads; no API, setting or stored value changes

## What an operator would notice

> In the Day to Day report, an exercise, note, override, temporary target or
> other event with a length that runs past midnight now also shows on the
> next day, and stays inside each day's chart. Nothing else in the report
> changes.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor bbc6e75e origin/dev`** &nbsp;·&nbsp; kind: `static`

#8788's head bbc6e75e is contained in origin/dev. RED while the PR is open
(2026-09-30).

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Measured 2026-09-30 in externals/work/crm-8788 (bbc6e75e, Node 22.23.2):
  the PR's test 3/3, and 1/3 with 7000eb18's daytoday.js (the two failures
  the PR body names); eslint on the two changed JavaScript files clean; git
  diff --check clean. Probes with the PR's harness: a 240 min event from
  22:00 draws 22:00-24:00 and 00:00-02:00; a 30 h event draws on three days;
  a string duration behaves as a number; a cancelled Temporary Target keeps
  its full length (BF-149). Full suite on bbc6e75e: 3481/0/3 (Node 22.23.2,
  MongoDB 7.0.43 in its own container, ci.test.env form), against 3478 on
  7000eb18's own CI; the 3 added are the PR's.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`releases/cgm-remote-monitor-15.0.9/contents.md`](../../releases/cgm-remote-monitor-15.0.9/contents.md)

## Notes carried on the item

Opened 2026-09-30 16:19Z by awss1i (first PR to the repository), one commit
bbc6e75e on dev 7000eb18, MERGEABLE, no review yet; CI ran on the fork PR
(CodeQL and the npm 12 install-and-build check passed; the nine test cells
were running at 2026-09-30 evening). Same-day drawing is unchanged by reading:
every event type reaches the same branch as on 7000eb18 with Other treatments
on or off, and band and label geometry are identical unless the band is
clipped. Cost of merging before the 15.0.9 tag: dev moves past 7000eb18, so
the 15.0.9 records (contents, tag message, release notes, integration record,
RT-0) are re-anchored; lib/report_plugins/daytoday.js joins the files the
browser-check gate names, and the manual smoke checklist's new Day to Day
section is the hand check; the real-site soak ran on 7000eb18, which does not
carry this change. Cost at cut 1 (RT-REBASE): cut 1 retires jsdom, so the new
test is ported to cut 1's Playwright suite or dropped there. The CHANGELOG
entry follows the practice of 12 other dev commits; the rule for that section
is the maintainer's open decision (releases/README.md, "Open item: CHANGELOG
on dev").

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-PR-8788` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
