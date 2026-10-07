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
15.0.8) to dev 7000eb18 (merge of #8786), measured 2026-09-27: 507 commits, 86
first-parent merges (all PR merges), 297 files, +28363/-1722. Among them the
programme's backfix PRs (#8733-#8740 and #8743-#8746 from 2026-09-17 to
2026-09-21; #8748-#8753, #8755-#8757 and #8759 on 2026-09-23; #8760-#8762 and
#8754 (with #8763 and #8765 folded in) on 2026-09-24; #8758 and #8766-#8770 on
2026-09-25; #8771-#8777, #8779, #8780, #8783 and #8784 on 2026-09-26; the
test-only #8785 and #8786 (BF-147) on 2026-09-27), #8741, #8778 and #8781 from
outside contributors on the same work, #8568, #8419 and #8530 carried by the
2026-09-25 decision, the D3 5.16 -> 7.9 chart migration (RT-D3), the opt-in
debug logging change (#8726), the connector pin to exactly 0.1.0 (#8762),
profile, treatment-query and clock fixes, report and chart fixes, dependency
updates and translations. Crowdin #8730 is held out. The candidate is dev
7000eb18: RC run 020 ran on ce30a94d; #8785 changes only
tests/boluswizardpreview.test.js, and #8786 changes two dependency overrides
and nine locked versions (its own nine-cell CI; the production bundle is byte-
identical). Reproduce with `git -C externals/cgm-remote-monitor-official log
--first-parent --oneline origin/master..origin/dev` and `git diff --shortstat
origin/master origin/dev`.

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

`BFQ-102`, `BFQ-114`, `BFQ-118`, `BFQ-119`, `RT-PR-8419`, `RT-PR-8530`, `BFQ-120`, `BFQ-126`, `BFQ-134`, `BFQ-106`, `BFQ-129`, `BFQ-125`, `BFQ-123`, `BFQ-122`, `BFQ-136`, `BFQ-128`, `RT-PR-8778`, `BFQ-80`, `BFQ-121`, `RT-PR-8781`, `BFQ-142`, `BFQ-146`, `RT-PR-8788`, `BFQ-108`, `RT-PR-8790`, `BFQ-151`, `BFQ-73`, `BFQ-153`, `BFQ-155`, `BFQ-CONFIG-DOCS`, `BFQ-94`, `BFQ-124`, `BFQ-127`, `BFQ-162`

## Evidence

- [`releases/cgm-remote-monitor-15.0.9/contents.md`](../../releases/cgm-remote-monitor-15.0.9/contents.md)
- [`docs/60-research/modernization/gt4-semver-classification-2026-09-15.md`](../../docs/60-research/modernization/gt4-semver-classification-2026-09-15.md)
- [`docs/60-research/remedial/manual-lab-15.0.9-rc-2026-09-23.md`](../../docs/60-research/remedial/manual-lab-15.0.9-rc-2026-09-23.md)
- [`docs/30-design/remedial/rc-15.0.9-integration-record.md`](../../docs/30-design/remedial/rc-15.0.9-integration-record.md)

## Notes carried on the item

2026-10-02 (maintainer): RT-VERSION is removed from blocks_on. The dev to
master version is decided (15.0.9); RT-VERSION's red gate measures the
modernization cut tips, which are renumbered when rebased, so it holds the
cuts, not this release. 2026-10-01 - #8790 (awss1i, BF-150, Food Editor touch
scrolling) and #8791 (BF-108) merged into dev (73c9528b, 50bc1084); dev is
50bc1084, 515 commits and 89 first-parent merges ahead of master. Release PR
#8598 at 50bc1084, mergeable, 27 passed and 3 skipped, APPROVED (approvals at
e3adc91d). Decided the same day (maintainer): BF-151 (GHSA-phrf) and BF-73
(GHSA-2m9c) are fixed for 15.0.9 (BFQ-151, BFQ-73 added to blocks_on); the
BF-153 dependency refresh is prepared and decided on its result; moment stays
at 2.30.1. BF-152 (GHSA-25pr) is after 15.0.9 (AndroidAPS contract question).
GHSA-cg6f duplicates GHSA-r3gv, fixed on dev by #8743. The 15.0.9 records are
re-anchored once these merge. 2026-09-30 - #8788 (awss1i, BF-148, Day to Day
report) merged into dev as 3014f883 (22:38Z, tree 3549306b = head bbc6e75e);
RT-PR-8788 added to blocks_on. dev is 3014f883: 509 commits and 87 first-
parent merges ahead of master, 298 files, +28617/-1819. Release PR #8598 is at
3014f883, mergeable, reviewDecision APPROVED (approvals at e3adc91d); CI 27
passed and 3 skipped. Local full suite on bbc6e75e 3481/0/3 (Node 22.23.2,
MongoDB 7.0.43). The browser-check gate names 15 files (adds
lib/report_plugins/daytoday.js; its hand check is the smoke checklist's new
Day to Day section). The real-site soak ran on 7000eb18, before #8788. The
15.0.9 records are re-anchored on 3014f883. Still owed by the maintainer:
browser hand checks, re-approval of #8598 at the final head, the semver
decision. 2026-09-30 - re-measured after fetching official: dev is still
7000eb18 (merged 2026-09-27 20:40Z), 507 commits and 86 first-parent merges
ahead of master; release PR #8598 is at 7000eb18, mergeable, 27 checks passed
and 3 skipped, reviewDecision APPROVED (both approvals given at e3adc91d). No
15.0.9 tag. The maintainer reported the same day that real sites running the
candidate have shown no visible regression so far (the testing notes record
one Loop, one Trio and one AndroidAPS user for about two days as of
2026-09-29), and decided that those real-site runs count as the 24-72 h real-
time soak (RT-SOAK, done). Still owed by the maintainer: browser hand checks,
re-approval of #8598 at the final head, the semver decision. 2026-09-27 -
#8785 (boluswizardpreview test clock; the timing flake that failed one cell of
#8784's CI) merged into dev as 295f1177 (head a9b77d1e, same tree; GitHub
merge time 18:39Z). Test-only, so run 020 on ce30a94d stands; #8785's CI
passed in all nine cells, the file passes 12/12 on 295f1177, the browser gate
names the same 14 paths, package files unchanged. dev is 295f1177: 505 commits
and 85 first-parent merges ahead of master, 296 files, +28279/-1703. Release
PR #8598 is at 295f1177: mergeable, 27 checks passed and 3 skipped,
reviewDecision APPROVED (both approvals given at e3adc91d). 2026-09-27 - npm
audit triage done (contents.md); BF-147 filed and merged as #8786 into dev as
7000eb18 (head 64a9cc13, same tree; 20:40Z): the ajv 6 and request form-data
overrides move to their patch releases and three build tools are refreshed, 9
locked versions, npm audit 17 -> 7 with no highs. Run 020 was not repeated:
#8786's CI passed in all nine cells plus the npm 12 install-and-build check,
one local cell gave 3473/0/3 (Node 24.15.0, MongoDB 7.0.43), and the
production bundle from 295f1177 and 7000eb18 is byte-identical. dev is
7000eb18: 507 commits and 86 first-parent merges ahead of master, 297 files,
+28363/-1722. Release PR #8598 is at 7000eb18: 27 checks passed and 3 skipped,
reviewDecision APPROVED. Still owed by the maintainer: browser hand checks,
the 24-72 h real-time soak, re-approval of #8598 at the final head, the semver
decision. 2026-09-26 - #8784 (BF-146 with BF-133) merged into dev as ce30a94d
(head d235bdf6; GitHub merge time 2026-09-27 05:32Z); BFQ-146 and BFQ-133 are
merged-upstream. dev is ce30a94d: 503 commits and 84 first-parent merges ahead
of master, 295 files, +28274/-1701. Release PR #8598 is at ce30a94d:
mergeable, 27 checks passed and 3 skipped, reviewDecision APPROVED (both
approvals given at e3adc91d). RC run 020 on ce30a94d (2026-09-27, integration
record): 3473/0/3 in six cells; run 019's probes unchanged; BF-146 probe exit
0 (1 on 699eb5fa and 15.0.8); compressed A/B soak recorded in tools/lab/rc-
soak/results/proof-2026-09-27-run020.md. Still owed by the maintainer: browser
hand checks, the 24-72 h real-time soak, re-approval of #8598 at the final
head, the semver decision, the npm audit triage. 2026-09-26 (maintainer: "fix
as appropriate"): BF-146, found by RC run 019's trace (04a873ce), is fixed for
15.0.9 on bf/api3-cache-derived-fields db99bba4, extended to device status by
d235bdf6 (maintainer, same day, for consistency; on official/dev 699eb5fa,
ready-to-push, not pushed); BFQ-146 is added to blocks_on and is not merged-
upstream. The same branch fixes BF-133 (BFQ-133). Same code on 15.0.8, not a
regression. 2026-09-26 (maintainer): BF-141, a regression from #8780 found in
the review of #8778, is fixed for 15.0.9 (BFQ-141, bf/fallback-key-empty-
identifier aaf67785, ready-to-push); BF-142 is after 15.0.9 (BFQ-142). BFQ-141
is the one item in blocks_on that is not merged-upstream, besides RT-VERSION.
2026-09-26 (maintainer, later): BF-142 is fixed for 15.0.9 after all (BFQ-142,
bf/api3-delete-nonstring-identifier 1c3aeb8c on official/dev ce7d754a, ready-
to-push), and BFQ-142 is added to blocks_on; it is not merged-upstream.
2026-09-26 - #8781 (AndyLow91; BF-141, BF-143, BF-144) merged into dev as
ce7d754a; RT-PR-8781 replaces BFQ-141 (closed, superseded; #8782 closed) in
blocks_on. dev is ce7d754a: 498 commits and 82 first-parent merges ahead of
master; release PR #8598 at ce7d754a, 27 checks green, 3 skipped, APPROVED.
Measured 2026-09-26 after fetching official: dev is ff93fa94 (merge of #8780)
and declares 15.0.9. master is 92d08342 = tag 15.0.8; dev is 496 commits and
81 first-parent merges ahead, 0 behind; 291 files, +27503/-1699. Merged
2026-09-26, in this order: #8771 (BF-106, ab9c96e6), #8772 (BF-129, f1151832),
#8773 (BF-125, e759a989), #8774 (BF-123, f0174d05), #8775 (BF-122 and BF-135,
1157a8de), #8776 (BF-136, 13f235e9), #8777 (BF-128, BF-138 and BF-139,
d613c35f), #8779 (BF-80, 750801a9), #8778 (BF-140, AndyLow91, aa1111b2) and
#8780 (BF-121, ff93fa94). Release PR #8598 is at head ff93fa94: mergeable, 27
checks green and 3 skipped, reviewDecision APPROVED (the two approvals were
given at e3adc91d). Full suite on ff93fa94 itself (fresh detached worktree,
tree c342bce0, fresh database): 3396 passing / 0 failing / 3 pending, Node
22.23.2, MongoDB 7.0.43, one cell only (not the six-cell matrix of the
integration record). On the same tree the round-2 probes give their expected
exit codes: bf106 gate 0, maker-language 0, profile-switch-percentage 0,
pebble-units 0, pebble-shared-scaled 0, api3-app-field 0, same-time-carbs 0 (1
with --strict: v3-noid and ws-dbAdd, left by design), api3-empty-identifier-
delete 0, v1-writes-v3-history 1 on the v1 DELETE arm only (kept by decision).
The browser-check gate's --with list and the release notes are not updated
here. Measured 2026-09-25 after fetching official: dev is e3adc91d (merge of
#8770) and declares 15.0.9; it pins nightscout-connect exactly 0.1.0 (P0-PIN).
master is 92d08342 = tag 15.0.8; dev is 461 commits and 71 first-parent merges
ahead. Release PR #8598 (dev -> master, author AndyLow91) is at head e3adc91d:
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
code; the rest need the checks repeated by hand. Partly done 2026-09-26 on
ff93fa94 (the maintainer in Chrome, the journey lab playing the phones, 15.0.8
side by side; no regression; docs/60-research/remedial/journey-lab-
browser-15.0.9-2026-09-26.md): careportal override, remote carbs and cancel
delivered; first load and live updates including deletes while open; the
profile editor; the AAPS percentage switch's basal pill, ISF and carb ratio.
Still owed: a remote bolus, LoopCaregiver from its app, the clock views, the
pump pill, the alarm level labels, and the Bolus Wizard Preview and reports
during a percentage switch. - The release-candidate soak (RT-SOAK) and the npm
audit triage, both open on the integration record's run 017. - The release
notes (releases/cgm-remote-monitor-15.0.9/release-notes.md) for everything
merged on 2026-09-25. - The maintainer tagging. Evidence: run 017 in
docs/30-design/remedial/rc-15.0.9-integration-record.md, dev e3adc91d itself
(tree d7383aae): 3170/0/3 in all six cells (Node 20/22/24 x MongoDB 4.4/7).
The earlier hand checks were on ec70aab0 (docs/60-research/remedial/manual-
lab-15.0.9-rc-2026-09-23.md) and the drag again on #8760's head 8d797ba4.
Decisions: - 2026-09-23 (maintainer): what 15.0.9 carries beyond dev as it
then stood (releases/cgm-remote-monitor-15.0.9/decisions.md): ?count=0 answers
an empty list (RT-COUNT0, later amended by RT-COUNT-COMPAT); MongoDB 4.4 is
declared deprecated in the release notes and dropped in a later release; the
legacy-ingestion notice goes in the release notes and RT-4's separate release
is dropped; nightscout-connect 0.1.0 is pinned only after longer prerelease
testing (done, #8762); RT-D3 is answered by a manual check plus an automated
browser test (answered 2026-09-24). Backfix 2 (bf2/*) and the bf3 fixes the
maintainer chose also ship in 15.0.9. - 2026-09-23 (maintainer, relayed via
-59): run the combined suite before the PRs merge and once more after the pin
to exact 0.1.0, before the tag (both done; run 010 is the latter). -
2026-09-24 (maintainer): RT-COUNT-COMPAT decided (tolerate oref0 and
GluPredKit count shapes, 15.0.9 stays a patch); RT-D3 answered for 15.0.9
(session -6a). First on the adopted train. Every merged backfix in dev (the
items in state merged-upstream) reaches operators only through this release;
until it ships they are in code nobody runs. Merging to dev publishes a Docker
Hub image, which is not a release.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-0` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
