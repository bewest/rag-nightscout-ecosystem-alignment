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

# Review packet — BFQ-112

**BF-112 - an auth subject created with a hex _id is stored as a string and
cannot be deleted by it**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `wip/object-id-crud-fixes` |
| base | `official/bf/object-id-crud@572bfc32` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-112` is the measurement |
| semver | `patch` |
| register entries | `BF-112` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/authorization/storage.js create and remove.

## Why that semver

a bug fix; admin-only

## What an operator would notice

> If an access entry (a "subject" on the admin page) was restored or created
> by a tool that set its own ID, deleting it from the admin page reports
> success but the entry stays, with its access. Check the list after
> deleting.

## Who should review this, and why

maintainer

## What was measured

**`node tools/queue/gates/bfq-112-oid-cell.js --build externals/work/crm-6a-rc-cand --ref wip/object-id-crud-fixe`** &nbsp;·&nbsp; kind: `integration`

Runs one object-id lab probe (tools/lab/object-id) against the fix branch in
its own mongo:7 container and asserts the fixed cells. Green 2026-09-25 on
ab7b22d6, 63dd716c and cb7d4110; its control (queue/gate-controls.yaml) is
red. Needs docker and n; about 20 s.

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor official/bf/object-id-crud wip/object-id`** &nbsp;·&nbsp; kind: `static`

wip/object-id-crud-fixes is a fast-forward of #8758's head (6d120fa2), so the
push is to bf/object-id-crud with no rebase.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Measured by tools/lab/object-id (probe P-ID-12): POST
  /api/v2/authorization/subjects with a hex _id stores a string, and DELETE
  by that hex answers 200 and leaves it, on v15.0.8, dev ddd9b600 and
  6d120fa2. The lab gate above wraps it.
- Fixed by d2fd9ff6 on wip/object-id-crud-fixes (local, not pushed), four
  commits on 6d120fa2. Lab 2026-09-24 with the branch as build f beside
  v15.0.8, dev ddd9b600 and 6d120fa2: P-ID-12 on build f: the subject is
  stored as an ObjectId and DELETE removes it (string and left on the other
  three). A subject already stored as a string is removed too
  (tests/storage.shape-handling.test.js). Every other cell of build f equals
  6d120fa2's, so #8758's own fixes (P-ID-1 to P-ID-7) are kept. Full suite
  on the branch, Node 22.23.2, MongoDB 7: 2875 passing, 3 pending, 0
  failing. Break-it: with lib/ reverted to 6d120fa2 and the new tests kept,
  10 of them fail.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/object-id/results/object-id-2026-09-24.md`](../../tools/lab/object-id/results/object-id-2026-09-24.md)

## Notes carried on the item

Open, found 2026-09-24 in the #8758 review; same class as BF-99 in
auth_subjects, which #8758 does not touch. The web admin page does not send
_id, so reaching it needs a restore or a tool. The access token digests
_id.toString(), the same for either form, so tokens are unaffected. Fix shape:
toStoredId on create, idForms on remove. Fix committed 2026-09-24 as d2fd9ff6
on wip/object-id-crud-fixes; folded into #8758 at the maintainer's request
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
- [ ] `make queue-status ID=BFQ-112` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
