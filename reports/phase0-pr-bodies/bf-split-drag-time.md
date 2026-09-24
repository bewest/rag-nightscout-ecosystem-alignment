# `bf/split-drag-time`: moving a treatment's time in the web UI no longer leaves IOB and COB at the old time (BF-103)

**DRAFT. Local branch, not pushed.** Branch `bf/split-drag-time` on `origin/dev` `4011193e`, tip
`8d797ba4`, one commit. No `CHANGELOG.md` edit. `git merge-tree` is clean with #8754 (`8211f8e2`)
and #8758 (`6d120fa2`). Evidence:
[`docs/60-research/remedial/bf103-fix-2026-09-23.md`](../../docs/60-research/remedial/bf103-fix-2026-09-23.md);
defect: [`bf103-split-drag-stale-time-2026-09-23.md`](../../docs/60-research/remedial/bf103-split-drag-stale-time-2026-09-23.md).

| what changes | who can see it |
|---|---|
| "Move carbs" / "Move insulin" (dragging a treatment with carbs and insulin into the top or bottom of the chart) writes the new record without the fields the page derived at the old time (`mills`, the page's own `date`, `mgdl`, `scaled`, `endmills`, `cuttedby`, `cutting`). IOB and COB count it at its new time, and it is drawn there | anyone who edits treatments on the chart |
| a plain Move, the half a split leaves behind, and a Save in the Reports treatment editor also clear a stored `mills`, `endmills`, `mgdl` and `scaled`, and move a stored `date` to the record's time. So changing the time of a record already damaged by an earlier split repairs it | sites that already hold such records |
| a treatment that has a stored `date` (API v3 records, such as those from AAPS) keeps it, moved to the new time as epoch ms, instead of keeping the old time | API v3 readers of treatments moved on the chart |
| new `lib/client/treatmenttime.js`, `tests/treatmenttime.test.js` (13 cases); `tests/dependency-d3.test.js` updated to the new emit shape | reviewers |
| the server, `lib/data/ddata.js`'s read rule, API v1 / v3 write paths, and a raw `PUT /api/v1/treatments` are unchanged | nobody; stated so a reviewer does not have to infer it |

## Measured

| | dev `4011193e` | this branch |
|---|---|---|
| Move carbs: COB stored vs the same records counted at `created_at` | 0 vs 25 g | 25 = 25 |
| Move insulin: IOB | 0.998 vs 2.494 U | 2.494 = 2.494 |
| plain Move of a damaged record (15.0.9 rc and 15.0.8 shapes) | stays stale | repaired |
| split of a damaged record, half left behind (IOB) | 1.002 vs 2.46 | 2.46 = 2.46 |
| Reports editor Save of a damaged record | IOB/COB follow; old `date` kept (glyph stays top-left) | repaired |
| raw GET + PUT `/api/v1/treatments` | stale (50 vs 75) | stale (unchanged) |
| `tests/dependency-d3.test.js` with the updated cases | 21 passing, 3 failing | 24 passing |
| full suite, Node 20.20.0 and 22.23.2 | 2440 / 0 / 3 | 2453 / 0 / 3 |

The browser probe is `tools/review/probes/bf103-split-drag-browser.js` in the alignment repository.
It uses real mouse drags in Chrome and the Reports editor, and reads each stored record from
MongoDB. For every phase it runs a restart-and-read control: IOB/COB with the records as stored,
then with the page-derived fields removed. Nine break-its, one per hunk, each go red in the probe;
seven also go red in the unit tests.

## Not in this branch

- The server keeps a stored `mills` (`lib/data/ddata.js:39-40`) and stores what websocket `dbAdd`
  sends. Both alternatives were prototyped and measured (evidence §6); neither is included.
- A split copies the record's `identifier` (and other uploader identity fields) to the new half, as
  it did before.
- The Reports editor sends form-encoded data, so the moved `date` is stored as a digit string (as
  any `date` already was after a Reports edit on dev).
- No repair script and no boot migration. The evidence §8 has a read-only query that lists affected
  records.

---

## What changes for you

*Plain-language summary for people running their own Nightscout site. Nightscout is not a medical
device and none of this is medical advice. If your treatments, IOB or COB look wrong, check them
with your care team before relying on them. This change does not tell you how much insulin to take,
and you should not use it to decide a dose.*

A few words used below:

- **Treatment**: something you recorded in Nightscout, such as a meal bolus with carbs and insulin.
- **IOB (insulin on board)**: Nightscout's estimate of insulin still acting.
- **COB (carbs on board)**: Nightscout's estimate of carbs not yet absorbed.
- **Edit mode**: the pencil button on the main chart that lets you drag treatments to a new time.

### What was wrong

- If you dragged a treatment that has both carbs and insulin to the top ("Move carbs") or bottom
  ("Move insulin") of the chart, Nightscout saved and showed the new time. Its own IOB and COB,
  and the Bolus Wizard that uses them, kept counting the moved part at the old time. After a
  reload the moved part appeared in the top-left corner of the chart.
- Dragging such a damaged treatment again, as a whole, did not fix it.

### What this change does

- The moved part is saved with only the new time, so IOB and COB count it where you put it.
- Moving a treatment that was already damaged this way, or saving it in the Reports treatment
  editor, repairs it.
- Treatments sent by apps that store their own time field (such as AndroidAPS) keep that field,
  set to the new time.

### Do you need to do anything?

- If you have split treatments this way before, some records may still be counted at the old
  time. Your site administrator can list them with the read-only query in the evidence note. After
  this update, moving each one to its intended time on the chart, or saving it in Reports, repairs
  it.
- If you rely on Nightscout's IOB, COB or Bolus Wizard, ask your care team how to handle any
  treatments that were moved this way before you update.
- Changing a treatment's time through another app or a script that writes the whole record back is
  not covered by this change.
