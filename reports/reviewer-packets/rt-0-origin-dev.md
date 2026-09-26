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
15.0.8) to dev 4f705217, measured 2026-09-25: 384 commits, 62 first-parent
merges, 226 files, +18167/-1403. Among them the programme's backfix PRs
(#8733-#8740 and #8743-#8746 from 2026-09-17 to 2026-09-21; #8748-#8753,
#8755-#8757 and #8759 on 2026-09-23; #8760-#8762 and #8754 (with #8763 and
#8765 folded in) on 2026-09-24; and #8741 from an external contributor on the
same work), the D3 5.16 -> 7.9 chart migration (RT-D3), the opt-in debug
logging change (#8726), the connector pin to exactly 0.1.0 (#8762), profile,
treatment-query and clock fixes, report and chart fixes, dependency updates
and translations. One open PR is planned to join it: #8758. Reproduce with
`git -C externals/cgm-remote-monitor-official log --first-parent --oneline
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
> foods meant to be hidden; that is corrected. The quick-pick list, which on
> 15.0.8 always showed (none), now shows your saved quick picks each time
> you open the Bolus Wizard; a food changed elsewhere while a page is open
> still appears only after that page reloads. TREATMENT DRAG: dragging a
> treatment into the "Move carbs" or "Move insulin" area to split it now
> stores the new time, so insulin on board and carbs on board follow the
> move. DATA SHOWN AND SEARCHED: many searches and counts that quietly
> returned nothing, or the wrong records, now return the right ones - for
> example filtering treatments by insulin, carbs, temporary basal rate or
> duration, and "records missing this field" searches. Profiles without a
> name and profile switches carrying their own schedule are handled
> correctly. Pages that read recent glucose values load faster. The carbs-
> on-board (COB) figure now uses the value reported by the system that
> uploads it (for example your phone app) when that system provides one, so
> the COB you see may differ from before. The main charts are rebuilt on a
> newer version of their drawing library, and several report and display
> fixes are included. SECURITY OF THE LIVE-UPDATE CONNECTION: the connection
> that pushes new readings and alarms to open pages had two gaps - recent
> device status could be sent to a page that had not signed in, and alarm
> messages went to every connected page. Both are closed, including on sites
> set to require sign-in. The "readable by world" warning also appears again
> in one setup where it had been hidden. CGM CONNECTOR: the built-in
> connector that fetches readings from CGM vendors' online services moves to
> version 0.1.0, which stops writing your CGM account's username, password,
> session tokens and readings into the server log, and stops a CareLink "no
> reading" marker being stored as a glucose value of 0. If Nightscout 15.0.8
> fetches your readings from a CGM vendor's online service (for example with
> Dexcom Share or LibreLinkUp settings), treat that account's password as
> exposed: change it, and change it anywhere else you have used it. OLDER
> APPS: OpenAPS and GluPredKit keep reading data the way they did on 15.0.8,
> with a deprecation warning; badly formed record counts are refused with an
> error. DATABASE: MongoDB 4.4 still works and is still tested, but is
> deprecated; plan to upgrade. DEBUG LOGGING QUIETER: detailed debug logging
> is now off unless it is switched on (the DEBUG_LOGGING setting), so server
> logs are shorter; if you or a helper rely on those logs to diagnose
> problems, switch it on. This is not medical advice. If a change to alarms
> or to a number such as carbs on board affects how you manage diabetes,
> talk it through with your care team.

## Who should review this, and why

maintainer, and at least one human reviewer who is not the author. Release PR
#8598 is authored by AndyLow91 and approved twice by the maintainer
(2026-09-26 00:39Z) at head e3adc91d. Integration PR #8605 carries the
modernization cuts (RT-3), not this release.

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

`RT-VERSION`, `BFQ-102`, `BFQ-114`, `BFQ-118`, `BFQ-119`, `RT-PR-8419`, `RT-PR-8530`, `BFQ-120`, `BFQ-126`, `BFQ-134`

## Evidence

- [`releases/cgm-remote-monitor-15.0.9/contents.md`](../../releases/cgm-remote-monitor-15.0.9/contents.md)
- [`docs/60-research/modernization/gt4-semver-classification-2026-09-15.md`](../../docs/60-research/modernization/gt4-semver-classification-2026-09-15.md)
- [`docs/60-research/remedial/manual-lab-15.0.9-rc-2026-09-23.md`](../../docs/60-research/remedial/manual-lab-15.0.9-rc-2026-09-23.md)

## Notes carried on the item

Measured 2026-09-25 after fetching official: dev is e3adc91d (merge of #8770)
and declares 15.0.9; it pins nightscout-connect exactly 0.1.0 (P0-PIN). master
is 92d08342 = tag 15.0.8; dev is 461 commits and 71 first-parent merges ahead.
Release PR #8598 (dev -> master, author AndyLow91) is at head e3adc91d:
mergeable, 27 checks green and 3 skipped, reviewDecision APPROVED (two
approvals by the maintainer, 2026-09-26 00:39Z). dev e3adc91d holds every PR
decided for 15.0.9 except #8730, which is held out (decided 2026-09-25,
maintainer; BF-132: its Crowdin sync reverts dev's corrected translations).
Merged 2026-09-25: #8530, #8766 (BF-118), #8767 (BF-119), #8758 (BFQ-102, head
f1e8398b, merge 4d9ecc3b), #8568 (BF-114), #8768 (BF-120), #8769 (BF-126),
#8419 and #8770 (BF-134). Every item in blocks_on is merged-upstream except
RT-VERSION, whose red gate is on the cut branches, which are renumbered when
rebased (decided 2026-09-23). Still before the tag: - The browser checks.
client-unchanged-since-hand-check.js on e3adc91d names 12 files that changed
after the hand-checked 8d797ba4: lib/api2/index.js and notifications-v2.js
(the Loop remote-command path, #8764), lib/client/clock-client.js (#8768),
lib/data/calcdelta.js, dataloader.js and ddata.js, lib/plugins/pump.js
(#8767), lib/profile/profileeditor.js, lib/settings.js (#8766),
views/index.html, .gitignore and .nycrc.json. The last two are not browser
code; the rest need the checks repeated by hand. - The release-candidate soak
(RT-SOAK) and the npm audit triage, both open on the integration record's run
017. - The release notes (releases/cgm-remote-monitor-15.0.9/release-notes.md)
for everything merged on 2026-09-25. - The maintainer tagging. Evidence: run
017 in docs/30-design/remedial/rc-15.0.9-integration-record.md, dev e3adc91d
itself (tree d7383aae): 3170/0/3 in all six cells (Node 20/22/24 x MongoDB
4.4/7). The earlier hand checks were on ec70aab0
(docs/60-research/remedial/manual-lab-15.0.9-rc-2026-09-23.md) and the drag
again on #8760's head 8d797ba4. Decisions: - 2026-09-23 (maintainer): what
15.0.9 carries beyond dev as it then stood (releases/cgm-remote-
monitor-15.0.9/decisions.md): ?count=0 answers an empty list (RT-COUNT0, later
amended by RT-COUNT-COMPAT); MongoDB 4.4 is declared deprecated in the release
notes and dropped in a later release; the legacy-ingestion notice goes in the
release notes and RT-4's separate release is dropped; nightscout-connect 0.1.0
is pinned only after longer prerelease testing (done, #8762); RT-D3 is
answered by a manual check plus an automated browser test (answered
2026-09-24). Backfix 2 (bf2/*) and the bf3 fixes the maintainer chose also
ship in 15.0.9. - 2026-09-23 (maintainer, relayed via -59): run the combined
suite before the PRs merge and once more after the pin to exact 0.1.0, before
the tag (both done; run 010 is the latter). - 2026-09-24 (maintainer): RT-
COUNT-COMPAT decided (tolerate oref0 and GluPredKit count shapes, 15.0.9 stays
a patch); RT-D3 answered for 15.0.9 (session -6a). First on the adopted train.
Every merged backfix in dev (the items in state merged-upstream) reaches
operators only through this release; until it ships they are in code nobody
runs. Merging to dev publishes a Docker Hub image, which is not a release.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-0` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-25, against cgm-remote-monitor-official `e3adc91d`.*
