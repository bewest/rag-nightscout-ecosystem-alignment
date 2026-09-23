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

15.0.9 is everything in origin/master..origin/dev: master 92d08342 (tag
15.0.8) to dev 74fc6619, measured 2026-09-22. 308 commits, 48 first-parent
merges, 200 files, +14381/-1262. Among them the thirteen backfix PRs from this
programme (#8733, #8734, #8735, #8736, #8737, #8738, #8739, #8740, #8743,
#8744, #8745, #8746, and #8741 from an external contributor on the same work),
the D3 5.16 -> 7.9 chart migration (RT-D3), the opt-in debug logging change
(#8726), profile, treatment-query and clock fixes, report and chart fixes,
dependency updates and translations. Reproduce with `git -C externals/cgm-
remote-monitor-official log --first-parent --oneline
origin/master..origin/dev` and `git diff --shortstat origin/master
origin/dev`.

## Why that semver

GT4: cannot be a patch, for reasons INDEPENDENT of D3. lib/server/env.js gains
DEBUG_LOGGING and CONNECT_DEBUG, debug logging flips to off by default
(removing log lines an operator relies on when diagnosing), and a new API file
lib/api2/loop-notification-errors.js appears.

## What an operator would notice

> Version 15.0.9 is the next Nightscout release. Nothing below reaches your
> site until 15.0.9 is released and your site is updated to it - if you run
> 15.0.8 today, every problem listed here is still present for you. ALARMS:
> the urgent "insulin reservoir change overdue" reminder could never appear
> and now can. If a feature name in your ENABLE setting (the list that
> switches features on) is misspelled or uses a file name instead of the
> feature's short name, Nightscout now warns you instead of silently leaving
> that feature off. The clock view now shows concern when a low reading is
> falling. These change whether an alarm or warning can appear, not the
> thresholds you set. BOLUS CALCULATOR QUICK PICKS: quick picks are saved
> food shortcuts in the Bolus Wizard (the calculator that suggests insulin
> for carbs). Picking one could load a different quick pick's foods or show
> foods meant to be hidden; that is corrected. A separate problem - the
> quick-pick list is built once when the page opens and not refreshed - is
> NOT fixed in this release. DATA SHOWN AND SEARCHED: many searches and
> counts that quietly returned nothing, or the wrong records, now return the
> right ones - for example filtering treatments by insulin, carbs, temporary
> basal rate or duration, and "records missing this field" searches.
> Profiles without a name and profile switches carrying their own schedule
> are handled correctly. Pages that read recent glucose values load faster.
> The carbs-on-board (COB) figure now uses the value reported by the system
> that uploads it (for example your phone app) when that system provides
> one, so the COB you see may differ from before. The main charts are
> rebuilt on a newer version of their drawing library, and several report
> and display fixes are included. SECURITY OF THE LIVE-UPDATE CONNECTION:
> the connection that pushes new readings and alarms to open pages had two
> gaps - recent device status could be sent to a page that had not signed
> in, and alarm messages went to every connected page. Both are closed,
> including on sites set to require sign-in. The "readable by world" warning
> also appears again in one setup where it had been hidden. DEBUG LOGGING
> QUIETER: detailed debug logging is now off unless it is switched on (the
> DEBUG_LOGGING setting), so server logs are shorter; if you or a helper
> rely on those logs to diagnose problems, switch it on. This is not medical
> advice. If a change to alarms or to a number such as carbs on board
> affects how you manage diabetes, talk it through with your care team.

## Who should review this, and why

maintainer, and at least one human reviewer who is not the author. Release PR
#8598 (dev -> master) was, on 2026-09-22, open, mergeable and green on every
CI check, with reviewDecision REVIEW_REQUIRED and zero approving reviews.
Integration PR #8605 carries the modernization cuts (RT-3), not this release.

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/master origin/dev`** &nbsp;·&nbsp; kind: `static`

dev descends from master with no divergence to reconcile

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- CI at dev's tip is not re-run here. Release PR #8598's checks (Node
  20/22/24 x Mongo 4.4/5/6, CodeQL, Docker build and publish) were all green
  on 2026-09-22, read from GitHub. Re-running them needs the full matrix
  with replica sets, and dev has no real-browser test job, so the D3 chart
  behaviour is not covered by that green.
- RT-D3's drag-clamp gap is unresolved and this release ships the D3 7
  charts. The decision to ship anyway is the maintainer's; recording it as a
  no-gate keeps it from reading as covered.

## Blocked on

`RT-D3`, `RT-VERSION`

## Evidence

- [`docs/30-design/modernization/cgm-remote-monitor-release-readiness-2026-09-14.md`](../../docs/30-design/modernization/cgm-remote-monitor-release-readiness-2026-09-14.md)
- [`docs/60-research/modernization/gt4-semver-classification-2026-09-15.md`](../../docs/60-research/modernization/gt4-semver-classification-2026-09-15.md)
- [`docs/30-design/modernization/release-readiness-15.0.9-2026-09-22.md`](../../docs/30-design/modernization/release-readiness-15.0.9-2026-09-22.md)

## Notes carried on the item

DECIDED 2026-09-23 (maintainer) - what 15.0.9 carries beyond dev as it stands:
?count=0 answers an empty list (RT-COUNT0); MongoDB 4.4 is declared deprecated
in the release notes and dropped in a later release; the legacy-ingestion
notice goes in the release notes and RT-4 is dropped; nightscout-connect 0.1.0
is pinned only after longer prerelease testing (P0-TAG); RT-D3 is answered by
a manual check plus an automated browser test. See
docs/30-design/remedial/backfix-2-plan-2026-09-22.md section 1a. First on the
adopted train. Every merged backfix in dev - the items in state merged-
upstream - reaches operators only through this release; until it ships they
are in code nobody runs. Merging dev publishes a Docker Hub image, which is
not a release. dev pins nightscout-connect at 234d47c by source URL (the
commit is in connector dev since #64 merged; measured 2026-09-23 with merge-
base --is-ancestor), where master pins tag v0.0.13 - see P0-PIN and P0-TAG.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-0` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
