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

# Review packet — BFQ-102 (PR #8758)

**bf/object-id-consistency - one rule for a record's own hex _id across profile,
devicestatus, food, activity, treatments, entries and API v3**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/object-id-crud` |
| base | `origin/dev@1f9a9d10` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-102` is the measurement |
| semver | `patch` |
| register entries | `BF-99`, `BF-100`, `BF-101`, `BF-102` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

Five commits to 597e2899: the helper lib/server/object-id-forms.js; profile
(BF-99); devicestatus, food, activity (BF-100); treatments and entries, moved
onto the helper with the UUID path unchanged (BF-102); API v3 filters
(BF-101). Then bf/object-id-crud adds eight commits to 6d120fa2: entry re-POST
with its own _id ($setOnInsert), upper-case hex on /entries/<id>, websocket
dbAdd/dbUpdate/dbRemove through the helper, a 336-cell CRUD-by-id matrix over
v1, v3 and the websocket, then the maintainer's D2 (v3 reaches non-hex string
_ids), D3 (entries POST answers the stored _id), D1 (devicestatus re-send
guard) and D4 (helper header). The only existing test changed is
tests/api3.storage.modify.test.js, three filter-shape assertions (D2).

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
  2483, 2496, 2832, 2848, 2858, 2866, 2866 passing, 0 failing, 3 pending per
  commit on Node 20 and 22; matrix 336/336 on MongoDB 7 and 4.4 (dev:
  176/336). No queue gate runs them yet.

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf-object-id-crud.md`](../../reports/phase0-pr-bodies/bf-object-id-crud.md)
- [`docs/60-research/remedial/object-id-other-collections-2026-09-23.md`](../../docs/60-research/remedial/object-id-other-collections-2026-09-23.md)
- [`docs/60-research/remedial/profile-object-id-2026-09-23.md`](../../docs/60-research/remedial/profile-object-id-2026-09-23.md)
- [`docs/60-research/remedial/crud-by-id-matrix-2026-09-23.md`](../../docs/60-research/remedial/crud-by-id-matrix-2026-09-23.md)

## Notes carried on the item

Open upstream as #8758 (head 6d120fa2, 2026-09-23), CI green, zero reviews
(2026-09-24). One PR from bf/object-id-crud, which contains bf/object-id-
consistency 597e2899. Owed: a review and the merge, before the 15.0.9 tag.
Evidence: the combined run rc-15.0.9-combined-010
(docs/30-design/remedial/rc-15.0.9-integration-record.md) includes 6d120fa2:
3046/0/3 on Node 20/22/24 x MongoDB 4.4/7 with the CRUD-by-_id matrix in each
cell. Per-commit suites and the 336-cell matrix are in the no-gate. The D1
check adds about 1 ms to a 100-row devicestatus batch that carries hex _ids
and nothing without. The narrow alternatives (BFQ-99 9b8cc2f9, BFQ-100
2fac53f5, BFQ-101 7295bc8c) conflict with it and are not to land. It enables
the connector's profile update-on-change (BFQ-97). PR body draft
reports/phase0-pr-bodies/bf-object-id-consistency.md. Decisions: - 2026-09-23
(maintainer): this ships in 15.0.9 instead of BFQ-99, with consistent working
CRUD across the API (plan section 1a, "15.0.9 ID consistency"). - 2026-09-23
(maintainer): D1 to D4 (plan section 1a), applied: D1 devicestatus re-send
guard, D2 v3 reaches non-hex string _ids, D3 entries POST answers the stored
_id, D4 helper header. Review 2026-09-24 (tools/lab/object-id, 43 cells
against v15.0.8, dev ddd9b600 and 6d120fa2): three pre-release findings on
this head, BF-109 (BFQ-109, v3 writes take the v1 half of a pair), BF-110
(BFQ-110, a delete by hex removes both twins; the body's "you can now delete
it" advice leads there; needs a decision) and BF-113 (BFQ-113, idForms accepts
12-character strings). The body's "Nothing in your database changes until a
record is edited or deleted" is wrong for new records, which are now stored as
ObjectId. The entries POST now answers the stored _id and drops a different
sent _id without an error (D3, as decided; worth one line in the notes). Two
shipping defects in the same class that this PR does not touch: BF-111
(BFQ-111) and BF-112 (BFQ-112).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-102` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
