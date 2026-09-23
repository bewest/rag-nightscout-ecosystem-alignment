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

# Review packet — BFQ-102

**bf/object-id-consistency - one rule for a record's own hex _id across profile,
devicestatus, food, activity, treatments, entries and API v3**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/object-id-crud` |
| base | `origin/dev@1f9a9d10` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-102` is the measurement |
| semver | `patch` |
| register entries | `BF-99`, `BF-100`, `BF-101`, `BF-102` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

Five commits to 597e2899: the helper lib/server/object-id-forms.js; profile
(BF-99); devicestatus, food, activity (BF-100); treatments and entries, moved
onto the helper with the UUID path unchanged (BF-102); API v3 filters
(BF-101). Then bf/object-id-crud adds four commits to c721e202: entry re-POST
with its own _id ($setOnInsert), upper-case hex on /entries/<id>, websocket
dbAdd/dbUpdate/dbRemove through the helper, and a 336-cell CRUD-by-id matrix
over v1, v3 and the websocket. No existing test changed.

## Why that semver

Bug fixes; no API or setting moves.

## What an operator would notice

> Records that arrive with their own id (copied from another Nightscout by
> the connector, restored from an export, or saved by 15.0.6 or earlier) can
> be edited and deleted normally: an edit replaces the record instead of
> adding a second copy. Nothing in the database changes until a record is
> edited or deleted. This is not medical advice; if settings or history look
> wrong, check them with your care team.

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- New tests red on dev (11/13, 27/31, 13/15, 9/10); each commit's full suite
  green on Node 20 and 22 (2401, 2414, 2445, 2460, 2470 passing, 0 failing,
  3 pending); every hunk broken singly goes red. bf/object-id-crud: 2478,
  2483, 2496, 2832 passing, 0 failing, 3 pending per commit on Node 20 and
  22; matrix 336/336 on MongoDB 7 and 4.4 (dev: 194/336). No queue gate runs
  them yet.

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf-object-id-crud.md`](../../reports/phase0-pr-bodies/bf-object-id-crud.md)
- [`docs/60-research/remedial/object-id-other-collections-2026-09-23.md`](../../docs/60-research/remedial/object-id-other-collections-2026-09-23.md)
- [`docs/60-research/remedial/profile-object-id-2026-09-23.md`](../../docs/60-research/remedial/profile-object-id-2026-09-23.md)
- [`docs/60-research/remedial/crud-by-id-matrix-2026-09-23.md`](../../docs/60-research/remedial/crud-by-id-matrix-2026-09-23.md)

## Notes carried on the item

One PR from bf/object-id-crud (contains bf/object-id-consistency 597e2899).
Open for the maintainer: D1 devicestatus re-send check, D2 API v3 reaching
non-hex v1 _ids (patch measured, not committed; changes two filter-shape
tests), D3 entries POST response _id when matched, D4 upper-case string ids on
disk (evidence section 5). Built 2026-09-23 on the maintainer's question
whether one PR could carry the through-line. Merge-tree clean with every open
15.0.9 PR head and rc/15.0.9-additions-e 1b1977e0; conflicts with bf/profile-
object-id (BFQ-99) in lib/server/profile.js, so land one. Merged trees not run
through the suite. DECIDED 2026-09-23 (maintainer): this ships in 15.0.9
instead of BFQ-99, with consistent working CRUD across the API (plan section
1a, "15.0.9 ID consistency"). PR body draft reports/phase0-pr-bodies/bf-
object-id-consistency.md.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-102` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
