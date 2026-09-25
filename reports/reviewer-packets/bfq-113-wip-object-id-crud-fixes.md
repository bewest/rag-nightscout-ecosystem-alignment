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

# Review packet — BFQ-113

**BF-113 - on #8758, idForms accepts a 12-character string and unguarded callers
widen to its forms**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `wip/object-id-crud-fixes` |
| base | `official/bf/object-id-crud@572bfc32` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-113` is the measurement |
| semver | `patch` |
| register entries | `BF-113` |

## What this changes

lib/server/object-id-forms.js idForms; profile.js save; the remove() of food,
activity and profile.

## Why that semver

a defect in an unmerged fix, reachable only in-process

## Who should review this, and why

maintainer

## What was measured

**`node tools/queue/gates/bf113-idforms-guard.js --ref wip/object-id-crud-fixes`** &nbsp;·&nbsp; kind: `static`

Loads official/bf/object-id-crud's object-id-forms.js and calls
idForms('abcdefghijkl'); its control is a 24-hex id, which must give
[ObjectId, hex]. RED on 6d120fa2 (three forms). Positive control run
2026-09-24: the same file with an isHexId guard in idForms, committed to a
scratch repository under QUEUE_GATE_ROOT, goes green. On wip/object-id-crud-
fixes dd2cf8f1 it is green; without --ref it still measures the PR head and is
red until the push.

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor official/bf/object-id-crud wip/object-id`** &nbsp;·&nbsp; kind: `static`

wip/object-id-crud-fixes is a fast-forward of #8758's head (6d120fa2), so the
push is to bf/object-id-crud with no rebase.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Fixed by dd2cf8f1 on wip/object-id-crud-fixes (local, not pushed), four
  commits on 6d120fa2. Lab 2026-09-24 with the branch as build f beside
  v15.0.8, dev ddd9b600 and 6d120fa2: no lab cell; the helper gate below.
  Every other cell of build f equals 6d120fa2's, so #8758's own fixes
  (P-ID-1 to P-ID-7) are kept. Full suite on the branch, Node 22.23.2,
  MongoDB 7: 2875 passing, 3 pending, 0 failing. Break-it: with lib/
  reverted to 6d120fa2 and the new tests kept, 10 of them fail.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

Open, found 2026-09-24 in the #8758 review. The v1 routes refuse non-hex ids
with 400; only in-process callers (the connector's internal output) can pass
one. The effect through profile.save and remove is read, not run. Small enough
to fold into #8758 with BFQ-109. Fix committed 2026-09-24 as dd2cf8f1 on
wip/object-id-crud-fixes; folded into #8758 at the maintainer's request
("fixes we can add to this PR"). Pushed to #8758 2026-09-24 (dd2cf8f1); the
maintainer then merged dev on GitHub (572bfc32), and CI failed one test there,
the BF-112 create test, because #8754 made subject create keep only owned
fields. Follow-up ab7b22d6 on wip/object-id-crud-fixes (fast-forward of
572bfc32) drops the create half and keeps remove; with dev 4f705217 merged,
Node 22.23.2, MongoDB 7: 3066 passing, 0 failing, 3 pending. Next step: a
human pushes ab7b22d6 and uploads reports/phase0-pr-bodies/pr-8758-body.md as
the PR body.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-113` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
