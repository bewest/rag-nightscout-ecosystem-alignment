# BF-103: a split treatment drag stores the old time, so IOB and COB ignore the move

> **Snapshot, 2026-09-23, against tag `15.0.8` (`92d08342`) and the 15.0.9 combined release candidate (`ec70aab0` = `origin/dev` `1f9a9d10` plus the nine pending PRs). Historical: the defect record; the fix is [bf103-fix](bf103-fix-2026-09-23.md), merged into `dev` as #8760 (2026-09-24), not released. Current facts: [backfix register](../../30-design/remedial/nightscout-backfix-register.md) BF-103.**

Audience: contributors and the maintainer. Contributor-facing and technical. Not medical advice.

## Summary

| question | 15.0.8 | 15.0.9 rc |
|---|---|---|
| "Move carbs" on a treatment carrying carbs and insulin writes a new record with `created_at` at the new time and `mills` / `date` at the **old** time | yes (found by hand in a browser) | yes (found by hand in a browser) |
| The new record also carries client-only fields `mgdl` and `scaled` | yes | yes |
| After a reload the moved record is drawn at the chart's top-left corner, and the console logs `<g> attribute transform: Expected number, "translate(undefined, …"` | yes | yes |
| A carbs record of that shape counts toward COB at its `mills` time, not its `created_at` | not run | yes: **0 g** with the stale fields, **25 g** with them removed |
| An insulin record of that shape counts toward IOB at its `mills` time | not run | yes: **0 U** with the stale fields, **2.49 U** with them removed |
| A plain Move (the whole treatment) is affected | no | no |

It is not a D3 regression: the split handlers are identical on both trees.

## Mechanism

- `lib/client/renderer.js` `case 'Move insulin'` and `case 'Move carbs'` (15.0.9 rc `:879` and `:906`; 15.0.8 `:877` and `:904`) unset one field on the original with `dbUpdateUnset`. They then build the new record as `JSON.parse(JSON.stringify(treatment))`, delete `_id`, `NSCLIENT_ID` and the other half's field, set `created_at` to the new time, and `dbAdd` it over the live connection.
- `treatment` is the page's in-memory object, not the stored document. The page has already added `mills` (the original time), `date` (a `Date`, via `getOrAddDate`), and `mgdl` / `scaled` (from `sbx.scaleEntry` when the glyph was placed). The copy keeps all four. `date` becomes an ISO string.
- The server stores them as sent.
- `lib/data/ddata.js:39-40` derives `mills` from `created_at` **only if the record has no `mills`**. So the stored stale `mills` is what every later computation uses. IOB, COB, and anything else keyed on a treatment's time see the pre-move time.
- On the chart, `getOrAddDate` returns the stored `date` string, `xScale` of a string is `undefined`, and the glyph's transform is invalid.
- The plain **Move** case sends `dbUpdate` with `{ created_at }` only, which is why it is unaffected. The stored document there has no `mills`, so `ddata` recomputes it.

## Method

1. **Browser, by hand.** A lab instance per tree (`AUTH_DEFAULT_ROLES=denied`, a token for a role with `*:*:read` and `api:treatments:*`, edit mode on). A Meal Bolus with 25 g and 2.5 U was dropped in the top 50 px of the chart and the "Change carbs time" prompt was accepted. The stored documents were then read from MongoDB:

   | tree | new record `created_at` | `mills` / `date` | extra fields |
   |---|---|---|---|
   | 15.0.9 rc | 20:02:06.701Z | 19:09:23.509Z | `mgdl: 110`, `scaled: 110` |
   | 15.0.8 | 19:30:04.900Z | 19:17:09.526Z | `mgdl: 110` |

   Both pages logged the transform error above after the next data update.

2. **IOB and COB, controlled** (15.0.9 rc only). One treatment of the split's shape was inserted directly: `created_at` 10 min ago, `mills` and `date` 2 h ago (carbs) or 6 h ago (insulin), plus `mgdl` / `scaled`. The instance was then restarted, so no server cache could mask the edit, and `GET /api/v2/properties/cob` or `/iob` was read. Next the four stale fields were `$unset` on the same document, and the restart and read were repeated.

   | record | with stale fields | stale fields removed |
   |---|---|---|
   | 25 g carbs | COB 0, source Care Portal | COB 25, source Care Portal |
   | 2.5 U insulin | IOB 0, source Care Portal | IOB 2.487, source Care Portal |

   The removed-fields arm is the control. It shows the same document at its `created_at` counts in full, so the zero is attributable to the stale `mills` and nothing else.

## Not measured

- IOB and COB on 15.0.8 (same code path; only the display symptom was observed there).
- Whether any uploader or follower app (Loop, AndroidAPS, Trio, xDrip+, followers) reads `mills` or `date` from such a record, or `created_at`.
- Records already written this way on existing sites. They can be found by `created_at` and `mills` disagreeing on a treatment.
- A fix. Two candidate shapes, neither run: build the new record from an allowlist of stored fields, or have the server drop client-supplied `mills` / `date` / `mgdl` / `scaled` on treatment writes. The second would also change what uploaders that send `mills` get.

## Operator-facing description (user-facing)

If you drag a treatment that has both carbs and insulin on the Nightscout chart, and drop it in the "Move carbs" or "Move insulin" area, Nightscout shows and saves the new time. But its own insulin-on-board (IOB) and carbs-on-board (COB) figures keep using the old time, and the moved item appears in the top-left corner of the chart. Moving a whole treatment is not affected. Until this is fixed, don't drop a treatment in the "Move carbs" or "Move insulin" area. Nobody has yet checked whether changing the time of an item already moved this way corrects it. If you rely on Nightscout's IOB or COB, or its Bolus Wizard, check with your care team about how to handle any treatments already moved this way. This is not medical advice.
