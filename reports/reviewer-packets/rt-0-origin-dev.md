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

**`node tools/queue/gates/client-unchanged-since-hand-check.js`** &nbsp;·&nbsp; kind: `static`

The 15.0.9 browser checks were done by hand (ec70aab0, and the drag again on
#8760's head 8d797ba4). This rebuilds the candidate, origin/dev merged with
the open 15.0.9 PR heads, and fails if any browser-side file, or any package
outside a server-only list, differs from 8d797ba4. RED means the manual checks
need repeating for what it names. Its control, #8760's own client change, is
seen in the same run. Edit the --with list as 15.0.9 PRs open or merge.

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/master origin/dev`** &nbsp;·&nbsp; kind: `static`

dev descends from master with no divergence to reconcile

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- CI at dev's tip is not re-run here. Release PR #8598's checks (Node
  20/22/24 x Mongo 4.4/5/6, CodeQL, Docker build and publish) were all green
  on 2026-09-22, read from GitHub. Re-running them needs the full matrix
  with replica sets, and dev has no real-browser test job, so the D3 chart
  behaviour is not covered by that green.
- This release ships the D3 7 charts with the drag checked in a real
  browser, not by Nightscout's own mocha suite, which cannot see the drag
  clamps (RT-D3 answered 2026-09-24; the suite gap is RT-D3-SUITE on cut 1).
  Recording it as a no-gate keeps it from reading as covered.

## Blocked on

`RT-VERSION`

## Evidence

- [`docs/30-design/modernization/cgm-remote-monitor-release-readiness-2026-09-14.md`](../../docs/30-design/modernization/cgm-remote-monitor-release-readiness-2026-09-14.md)
- [`docs/60-research/modernization/gt4-semver-classification-2026-09-15.md`](../../docs/60-research/modernization/gt4-semver-classification-2026-09-15.md)
- [`docs/30-design/modernization/release-readiness-15.0.9-2026-09-22.md`](../../docs/30-design/modernization/release-readiness-15.0.9-2026-09-22.md)
- [`docs/60-research/remedial/manual-lab-15.0.9-rc-2026-09-23.md`](../../docs/60-research/remedial/manual-lab-15.0.9-rc-2026-09-23.md)

## Notes carried on the item

2026-09-24 - CONNECTOR PIN DONE: nightscout-connect 0.1.0 released (P0-TAG)
and dev pins it exactly (#8762, dev 153e5658). The run owed after that pin is
green: dev + pin + #8754 + #8758, tree 4114f45a, 3046/0/3 on all six Node x
MongoDB cells (docs/30-design/remedial/rc-15.0.9-combined-010-2026-09-24.md).
#8754's head since moved to 280eccbe (a dev merge only); dev 153e5658 +
280eccbe + #8758 6d120fa2 is the same tree. Open before the tag: #8754, #8758,
the release notes, and a review of #8598. 2026-09-23 - OPEN BEFORE THE TAG:
RT-COUNT-COMPAT, whether the 15.0.9 count rule is a correction or a
compatibility break for oref0 and GluPredKit. Hold #8598 and the tag until the
maintainer decides it. 2026-09-24 - RT-D3 answered (maintainer, session -6a)
and removed from blocks_on; the new first gate keeps the hand checks valid
only while the candidate's browser-side code matches the hand-checked tree.
2026-09-23 - COMBINED RUN GREEN (-59): rc/15.0.9-combined-59 (local) =
ddd9b600, then #8754 ef3404fd (merge 2731b658), then #8758 6d120fa2 (merge
509235b3). Both merges were automatic; tree 2ce67b27. Suite 2453/0/3 on dev,
2548/0/3 with #8754 and 3028/0/3 with #8758, on Node 20, 22 and 24 x MongoDB
4.4 and 7, with the CRUD-by-_id matrix in each cell
(docs/30-design/remedial/rc-15.0.9-combined-59-2026-09-23.md). So #8754 and
#8758 can merge on evidence. Still owed before the tag: one run after the pin
to exact 0.1.0. 2026-09-23 (01:43Z 09-24) - dev ddd9b600 adds #8760 (BF-103).
Open: #8754 (head ef3404fd: three dev merges on 0a74ef4e, its own changes
line-identical to 0a74ef4e) and #8758 (6d120fa2). Their merge with dev is
clean (tree 2ce67b27) and differs from the verified combined rc d087588f in
exactly #8760's five files, so no combined run covers today's candidate.
DECIDED 2026-09-23 (maintainer, relayed via -59) - run the combined suite now
on dev ddd9b600 + #8754 ef3404fd + #8758 6d120fa2, so both PRs can merge on
evidence, and once more after the pin to exact 0.1.0, before the tag. The
first run is rc/15.0.9-combined-59 (session -59). #8598 carries the manual-
check comment and the BF-103 update (2026-09-24 00:33Z and 04:41Z); it still
has zero reviews. 2026-09-23 (late) - dev 4011193e carries #8750, #8752,
#8759, #8757, #8749, #8748, #8755, #8756, #8753 and #8751; open: #8754
(security review: maintainer and Andy) and #8758. The combined rc
(rc/15.0.9-combined-36b d087588f, 3015/0/3 on all six Node x MongoDB cells)
tested exactly this set, so no re-run is owed unless #8754 or #8758 changes
head. Manual checks passed on ec70aab0 (-6d): RT-D3, alarms under
AUTH_DEFAULT_ROLES=denied and with AUTHENTICATION_PROMPT_ON_LOAD (ec70aab0
also carried #8754, which changes lib/api3/alarmSocket.js and is not on
4011193e; every other client file those checks use is identical). Still before
the tag - connector v0.1.0 and a pin to exact 0.1.0 (with a re-run), release
notes, #8598 review. 2026-09-23 - COMBINED CANDIDATE VERIFIED (-1f):
rc/15.0.9-additions-e 1b1977e0 (local only) on dev 74fc6619 contains the live
heads of all nine 15.0.9 PRs - #8748 d19043b2, #8749 46b20b38, #8750 aabce4b1,
#8751 b5038500, #8752 adf5120c, #8753 e6a50e9a, #8754 0a74ef4e, #8755
92544d8f, #8756 83cfff14 (containment checked). 2534/0/3 on all 12 cells (Node
20/22/24 x MongoDB 4.4.24/7.0.43, nofile 64000); break-its red for the
original reason; connector control dev.2 23/23, v0.0.13 18/5. Record:
docs/30-design/remedial/rc-15.0.9-additions-e-2026-09-23.md. Still before the
tag - the swap of #8752 to exact 0.1.0 (a re-run is owed then), reviews,
release notes, #8598. DECIDED 2026-09-23 (maintainer) - what 15.0.9 carries
beyond dev as it stands: ?count=0 answers an empty list (RT-COUNT0); MongoDB
4.4 is declared deprecated in the release notes and dropped in a later
release; the legacy-ingestion notice goes in the release notes and RT-4 is
dropped; nightscout-connect 0.1.0 is pinned only after longer prerelease
testing (P0-TAG); RT-D3 is answered by a manual check plus an automated
browser test. See docs/30-design/remedial/backfix-2-plan-2026-09-22.md section
1a. First on the adopted train. Every merged backfix in dev - the items in
state merged-upstream - reaches operators only through this release; until it
ships they are in code nobody runs. Merging dev publishes a Docker Hub image,
which is not a release. dev pins nightscout-connect at 234d47c by source URL
(the commit is in connector dev since #64 merged; measured 2026-09-23 with
merge-base --is-ancestor), where master pins tag v0.0.13 - see P0-PIN and
P0-TAG.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-0` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-23, against cgm-remote-monitor-official `ddd9b600`.*
