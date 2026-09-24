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

# Review packet — BFQ-103 (PR #8760)

**BF-103 - a split drag stores the old time, so IOB and COB ignore the move**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/split-drag-time` |
| base | `origin/dev@4011193e` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-103` is the measurement |
| semver | `patch` |
| register entries | `BF-103` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

One commit 8d797ba4 on dev 4011193e: new lib/client/treatmenttime.js, wired
into lib/client/renderer.js (Move, Move carbs, Move insulin) and
lib/report_plugins/treatments.js (Reports editor save);
tests/treatmenttime.test.js (13) and tests/dependency-d3.test.js updated to
the new emitted messages. ddata.js's read rule and the server write path are
unchanged.

## Why that semver

a client bug fix

## What an operator would notice

> If you drag a treatment on the chart into the "Move carbs" or "Move
> insulin" area to split it, the chart shows the moved part at its new time,
> but Nightscout keeps using the old time when it works out insulin on board
> and carbs on board. Until this is fixed, avoid splitting a treatment by
> dragging it into those areas. This is not medical advice; talk to your
> care team about any treatment record you are unsure of.

## Who should review this, and why

SAFETY - the move changes when carbs or insulin count for IOB and COB

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Reproduced by hand on 15.0.8 and the combined rc ec70aab0 with a control
  (COB 0 vs 25 g, IOB 0 vs 2.49 U for the same record). No fix and no
  automated test yet; the test to add drags into each split zone and asserts
  the stored mills and date of the new record.

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf-split-drag-time.md`](../../reports/phase0-pr-bodies/bf-split-drag-time.md)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/60-research/remedial/bf103-split-drag-stale-time-2026-09-23.md`](../../docs/60-research/remedial/bf103-split-drag-stale-time-2026-09-23.md)
- [`docs/60-research/remedial/bf103-fix-2026-09-23.md`](../../docs/60-research/remedial/bf103-fix-2026-09-23.md)
- [`docs/60-research/remedial/manual-lab-15.0.9-rc-2026-09-23.md`](../../docs/60-research/remedial/manual-lab-15.0.9-rc-2026-09-23.md)

## Notes carried on the item

2026-09-23 - VERIFIED BY HAND on #8760 8d797ba4 (the maintainer, manual lab
port 15204, Chrome, mouse): Move carbs and Move insulin land at the new time
with no console errors and survive a reload; plain move, cancel and both edge
limits unchanged; a plain move of a pre-damaged record (stale mills, date
string, mgdl, scaled) cleared mills, mgdl and scaled and set date to the new
created_at as a number. Stored split records carry none of the page fields.
Not shown live: COB for the repaired record (its new time was past
absorption). Record: docs/60-research/remedial/manual-
lab-15.0.9-rc-2026-09-23.md. 2026-09-23 - OPEN upstream as #8760 (head
8d797ba4, verified with ls-remote). BUILT 2026-09-23, CLEAN by the plan
section 1a conditions, so it goes into 15.0.9: browser probe red on dev and
green on the branch for split, plain move of a damaged record (both stored
shapes), split of a damaged record and a v3 record (e.g. COB 0 vs 25 on dev,
equal on the branch); dependency-d3 21/3 on dev, 24/0 on the branch; suite
2440/0/3 dev, 2453/0/3 branch on Node 20 and 22 (after npm run bundle); 9 of 9
break-its caught by the browser probe (7 by unit tests); merge-tree clean with
#8754 8211f8e2 and #8758 6d120fa2. The split copy drops page-added mills,
endmills, mgdl, scaled, cuttedby, cutting and a Date-typed date; a move clears
them on the stored record and sets a disagreeing stored date to the new time
(API v3 and AAPS use date). A raw v1 PUT still leaves a stale mills (server-
side, not in scope). Server-side options measured, not built: ddata preferring
created_at retimes other collections too; stripping on websocket dbAdd leaves
existing records stale. Read-only repair query in the evidence section 8.
Evidence docs/60-research/remedial/bf103-fix-2026-09-23.md; PR body
reports/phase0-pr-bodies/bf-split-drag-time.md. DECIDED 2026-09-23
(maintainer): into 15.0.9 if bf/split-drag-time comes back clean (plan section
1a, "BF-103"); otherwise a known issue (advice: avoid splitting by drag; edit-
the-time is unmeasured). Branch being built by session -36b (worktree
externals/work/crm-bf-split-drag). Filed 2026-09-23 by -6d (register
0c022da5); queue item added by -59. Graded medium to high in the register. Not
a 15.0.9 blocker as recorded; it is on 15.0.8 too. Scope for 15.0.9 is the
maintainer's.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-103` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-23, against cgm-remote-monitor-official `4011193e`.*
