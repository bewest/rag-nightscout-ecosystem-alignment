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

# Review packet — BFQ-111

**BF-111 - find[_id][$in] misses records stored with a string _id, for reads and
bulk deletes**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `wip/object-id-crud-fixes` |
| base | `official/bf/object-id-crud@6d120fa2` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-111` is the measurement |
| semver | `patch` |
| register entries | `BF-111` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/server/query.js updateIdQuery ($in/$nin leaves) and #8758's
matchEitherForm, which widens only a plain equality.

## Why that semver

a bug fix; the request answers 200 and misses records

## What an operator would notice

> An app that asks for, or deletes, several records at once by their IDs can
> miss records saved by Nightscout 15.0.6 or earlier, or copied in from
> another site, and delete nothing for those. No app we know of does this
> today.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor official/bf/object-id-crud wip/object-id`** &nbsp;·&nbsp; kind: `static`

wip/object-id-crud-fixes is a fast-forward of #8758's head (6d120fa2), so the
push is to bf/object-id-crud with no rebase.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Measured by tools/lab/object-id (probe P-ID-11): a list of a string-stored
  and an ObjectId-stored treatment returns n=1, and its DELETE leaves the
  string one, on v15.0.8, dev ddd9b600 and 6d120fa2. No queue gate wraps the
  lab yet (OID-LAB).
- Fixed by 1c2d1afd on wip/object-id-crud-fixes (local, not pushed), four
  commits on 6d120fa2. Lab 2026-09-24 with the branch as build f beside
  v15.0.8, dev ddd9b600 and 6d120fa2: P-ID-11 on build f: GET n=2 and the
  DELETE leaves neither record (n=1 and the string record left on the other
  three). Every other cell of build f equals 6d120fa2's, so #8758's own
  fixes (P-ID-1 to P-ID-7) are kept. Full suite on the branch, Node 22.23.2,
  MongoDB 7: 2875 passing, 3 pending, 0 failing. Break-it: with lib/
  reverted to 6d120fa2 and the new tests kept, 10 of them fail.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/object-id/results/object-id-2026-09-24.md`](../../tools/lab/object-id/results/object-id-2026-09-24.md)

## Notes carried on the item

Open, found 2026-09-24 in the #8758 review; not a #8758 regression. Natural
follow-up on the #8758 helper once it merges (expand each hex leaf of $in and
$nin to its forms). Candidate for 15.0.10. Fix committed 2026-09-24 as
1c2d1afd on wip/object-id-crud-fixes; folded into #8758 at the maintainer's
request ("fixes we can add to this PR"). Next step: a human pushes wip/object-
id-crud-fixes to official bf/object-id-crud.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-111` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
