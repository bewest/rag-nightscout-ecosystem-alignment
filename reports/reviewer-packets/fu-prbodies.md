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

# Review packet — FU-PRBODIES

**Merged PR bodies have drifted from the files they were posted from**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `origin/dev@74fc6619` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=FU-PRBODIES` is the measurement |
| semver | `n/a` |

## What this changes

No code. Pull request bodies and the files under reports/phase0-pr-bodies/
they were posted from. Measured 2026-09-23 by tools/queue/gates/pr-body-
parity.js over its eight pairs: #8738, #8740 and #8743 match; #8734, #8735,
#8736, #8737 and #8739 differ. The drift runs in two directions. #8734, #8735,
#8736 and #8737 differ only in documentation paths - the local files were
updated when the docs tree moved into programme subdirectories, so the LIVE
bodies still cite the pre-move spellings (the backfix register without its
`remedial/` segment, the semver classification without `modernization/`), and
those paths no longer resolve. The spellings are deliberately not written out
here: doc-links.js gates this file, and a dead path quoted in a note is
indistinguishable to it from a dead path being relied on. Word counts are
identical each way. #8739 is the opposite: the live body is 1640 words to the
file's 1537 and carries paragraphs the file does not have - the urgent-
severity versus notification-delivery distinction, and a note about Alexa and
Google Home locale handling - added upstream after posting. #8743, #8744 and
#8745, the three advisory fixes, were edited on GitHub on 2026-09-23
(00:28:08Z to 00:28:11Z) from the maintainer's account to withhold detail
until a fixed release ships and the advisories are published; each now opens
"Details withheld". They are 396, 189 and 318 words (`wc -w`). bf-operators.md
was trimmed to #8743's text the same day; the full text is at 9ddad0cc (2641
words) for restoring after release. #8744 and #8745 have no file under
reports/phase0-pr-bodies/, so the gate does not see them; their full drafts
are under docs/30-design/remedial/advisory-response-2026-09/pull-requests/.

## Why that semver

documentation of changes already merged; no shipped behaviour

## Who should review this, and why

MAINTAINER, and the decision is narrow: are merged pull request bodies worth
correcting at all? For: a merged PR body is the durable public record of why a
change was made, and four of these cite file paths that 404 for anybody who
follows them. Against: few people read a merged PR body and the edit costs a
push. If the answer is yes, #8739 must be handled differently from the other
four. Its live body is ahead; the upstream text has to be reconciled INTO
reports/phase0-pr-bodies/bf-alarms.md before anything is pushed, or that work
is destroyed. A one-way `gh pr edit <pr> --body-file <local>` on #8739 would
overwrite it and then report green. Do not restore #8743, #8744 or #8745 to
their long form, and do not overwrite them from any file, until a release
containing their fixes ships and the advisories are published.

## What was measured

**`node tools/queue/gates/pr-body-parity.js`** &nbsp;·&nbsp; kind: `network`

All eight bodies match their files. Red with five failing as of 2026-09-23.
Read-only - it fetches bodies and never edits one. Its direction advice is a
word-count heuristic: read the PR's last-edited time before acting on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Whether a body is TRUE is not measured by anything here, and parity with a
  wrong file is still parity. Figures in these bodies have been wrong before
  - bf/parms had two, bf/reads had four - and only re-running the claim
  catches that.
- Nothing gates the reconciliation of #8739. Merging upstream prose into a
  local file is an editorial act; a gate can say the two differ and cannot
  say the merge was faithful.

## Evidence

- [`tools/queue/gates/pr-body-parity.js`](../../tools/queue/gates/pr-body-parity.js)
- [`reports/phase0-pr-bodies/bf-alarms.md`](../../reports/phase0-pr-bodies/bf-alarms.md)

## Notes carried on the item

DECIDED 2026-09-23 (maintainer) - fix only the dead links in the bodies of
#8734-#8737; do not otherwise re-sync them. Reconcile #8739 the other way: its
file follows the live body. #8743-#8745 are withheld and are not touched until
release. The parity gate belonged to eight Phase 0 items that are all merged-
upstream, so its red reads as expected post-merge noise on rows nobody
revisits; this item gives it an owner. No PR body was edited; all twelve Phase
0 and advisory PR bodies were read on 2026-09-23 with their last-edited times.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=FU-PRBODIES` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-23, against cgm-remote-monitor-official `ddd9b600`.*
