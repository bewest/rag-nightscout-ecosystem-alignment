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

# Review packet — BFQ-109

**BF-109 - on #8758, API v3 DELETE and PUT by identifier write the v1 half of a
v1/v3 pair**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `wip/object-id-crud-fixes` |
| base | `official/bf/object-id-crud@572bfc32` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-109` is the measurement |
| semver | `patch` |
| register entries | `BF-109` |

## What this changes

lib/api3/storage/mongoCollection/utils.js filterForOne and identifyingFilter
as #8758 changes them, and the unsorted replaceOne/updateOne/deleteOne in
modify.js that use them.

## Why that semver

a defect in an unmerged fix; no API or setting moves

## What an operator would notice

> Only on the change that is not released yet (#8758). If your site has a
> record that an app using API v3, such as AndroidAPS, once saved a second
> copy of, deleting it from that app would report success and the record
> would stay visible; changing it would leave two copies. Nothing changes
> for anyone running 15.0.8 today.

## Who should review this, and why

maintainer

## What was measured

**`node tools/queue/gates/bfq-109-oid-cell.js --build externals/work/crm-6a-rc-cand --ref wip/object-id-crud-fixe`** &nbsp;·&nbsp; kind: `integration`

Runs one object-id lab probe (tools/lab/object-id) against the fix branch in
its own mongo:7 container and asserts the fixed cells. Green 2026-09-25 on
ab7b22d6, 63dd716c and cb7d4110; its control (queue/gate-controls.yaml) is
red. Needs docker and n; about 20 s.

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor official/bf/object-id-crud wip/object-id`** &nbsp;·&nbsp; kind: `static`

wip/object-id-crud-fixes is a fast-forward of #8758's head (6d120fa2), so the
push is to bf/object-id-crud with no rebase.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Measured by tools/lab/object-id (probe P-ID-10; needs mongo:7 in docker
  and the three worktrees, about 3 minutes; lab.sh up, run, down). On
  6d120fa2 "hex DELETE, then GET" reads "200 / v1-original(invalid),v3-copy
  / GET 200 v3-copy" where v15.0.8 and dev ddd9b600 read "...
  v3-copy(invalid) / GET 410"; "hex PUT" leaves identifier=X n=2 where both
  controls leave n=1. Same for a non-hex identifier. The lab gate above
  wraps it.
- Fixed by a2c7eb39 on wip/object-id-crud-fixes (local, not pushed), four
  commits on 6d120fa2. Lab 2026-09-24 with the branch as build f beside
  v15.0.8, dev ddd9b600 and 6d120fa2: P-ID-10 on build f reads as v15.0.8
  and dev (DELETE leaves v3-copy(invalid), GET 410; PUT leaves identifier=X
  n=1) and P-ID-2 still reads as 6d120fa2 (200). The fix is in modify.js,
  not utils.js: each write first finds its target with the read's sort
  ({identifier: -1}) and then writes by that document's _id; utils.js is
  unchanged. Every other cell of build f equals 6d120fa2's, so #8758's own
  fixes (P-ID-1 to P-ID-7) are kept. Full suite on the branch, Node 22.23.2,
  MongoDB 7: 2875 passing, 3 pending, 0 failing. Break-it: with lib/
  reverted to 6d120fa2 and the new tests kept, 10 of them fail.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/object-id/results/object-id-2026-09-24.md`](../../tools/lab/object-id/results/object-id-2026-09-24.md)

## Notes carried on the item

Open, found 2026-09-24 in the review of #8758, which it blocks in the review's
judgement; whether it holds the merge is the maintainer's call. Ablation
2026-09-24: 6d120fa2 with only utils.js reverted to 1f9a9d10 gives dev's
P-ID-10 cells and loses #8758's P-ID-2 fix (v3 GET/PATCH/DELETE of a string-
_id record back to 404), so a fix must keep P-ID-2 and change only which
document a write takes. Fix shape, not measured: resolve the target with the
sorted findOneFilter, then write by its exact _id. Fix committed 2026-09-24 as
a2c7eb39 on wip/object-id-crud-fixes; folded into #8758 at the maintainer's
request ("fixes we can add to this PR"). Pushed to #8758 2026-09-24
(dd2cf8f1); the maintainer then merged dev on GitHub (572bfc32), and CI failed
one test there, the BF-112 create test, because #8754 made subject create keep
only owned fields. Follow-up ab7b22d6 on wip/object-id-crud-fixes (fast-
forward of 572bfc32) drops the create half and keeps remove; with dev 4f705217
merged, Node 22.23.2, MongoDB 7: 3066 passing, 0 failing, 3 pending. Next
step: a human pushes ab7b22d6 and uploads reports/phase0-pr-
bodies/pr-8758-body.md as the PR body.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-109` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
