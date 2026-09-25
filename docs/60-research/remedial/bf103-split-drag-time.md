# BF-103: a split treatment drag stores the old time, so IOB and COB ignore the move

*Contributor-facing and technical. Not medical advice. Status: **merged** into `dev` as #8760
(merge `ddd9b600`, 2026-09-24), **not released**; 15.0.8 (`92d08342`) still has the defect. It
reaches operators with 15.0.9 (queue `RT-0`). Defect facts: [backfix register](../../30-design/remedial/nightscout-backfix-register.md)
BF-103; item state: queue `BFQ-103`. Measured 2026-09-23 on tag `15.0.8`, the 15.0.9 combined
candidate `ec70aab0`, `origin/dev` `4011193e` and fix branch `bf/split-drag-time` `8d797ba4`.*

## Summary

| question | 15.0.8 | `dev` before #8760 (`4011193e`) | with #8760 (`8d797ba4`) |
|---|---|---|---|
| "Move carbs" / "Move insulin" on a treatment with carbs and insulin: does the moved half count toward COB / IOB at its new time? | no (display symptom seen by hand; IOB/COB not run) | no: COB 0 vs 25 g, IOB 0.998 vs 2.494 U | yes: 25 = 25, 2.494 = 2.494 |
| Is the moved half drawn at its new time? | no: top-left corner, `translate(undefined, …)` console errors | no | yes |
| A plain Move (the whole treatment) | not affected | not affected | not affected |
| A plain Move of a record already damaged by a split: repaired? | no | no | yes |
| A raw `PUT /api/v1/treatments` of a damaged record: repaired? | no | no | no (server path; not in #8760's scope) |
| Full suite, Node 20.20.0 and 22.23.2 | | 2440 / 0 / 3 | 2453 / 0 / 3 |

"x vs y" is the control used throughout: the stored value vs the same documents counted at their
`created_at` (see [Method](#method)). It is not a D3 regression: the split handlers are identical on
15.0.8 and the 15.0.9 candidate.

## Mechanism

- `lib/client/renderer.js` `case 'Move insulin'` and `case 'Move carbs'` (15.0.8 `:877` and `:904`)
  unset one field on the original with `dbUpdateUnset`. They then build the new record as
  `JSON.parse(JSON.stringify(treatment))`, delete `_id`, `NSCLIENT_ID` and the other half's field,
  set `created_at` to the new time, and `dbAdd` it over the live connection.
- `treatment` is the page's in-memory object, not the stored document. The page has already added
  `mills` (the original time), `date` (a `Date`, via `getOrAddDate`), and `mgdl` / `scaled`. The copy
  keeps all four, and `date` becomes an ISO string. The server stores them as sent.
- `lib/data/ddata.js:39-40` derives `mills` from `created_at` **only if the record has no `mills`**,
  so the stale stored `mills` is what IOB, COB and everything else keyed on a treatment's time use.
- On the chart, `getOrAddDate` returns the stored `date` string, `xScale` of a string is
  `undefined`, and the glyph's transform is invalid.
- The plain **Move** sends `dbUpdate` with `{ created_at }` only. Its stored document has no `mills`,
  so `ddata` recomputes it; that is why a plain Move neither causes nor repairs the damage.

## What the page adds to a treatment

Each field below was confirmed as page-added in two ways: by reading where it is set, and by reading
the stored document from MongoDB before any drag. None is present on a treatment created through
`POST /api/v1/treatments` or `POST /api/v3/treatments`, and a source read of the uploaders (below)
found none that sends `mgdl`, `scaled`, `endmills`, `cuttedby` or `cutting`.

| field | where it is added | holds | removed from the split copy | cleared on a time change |
|---|---|---|---|---|
| `mills` | `lib/data/ddata.js:39-40`, `lib/data/dataloader.js:20-21` | the old time | yes | yes |
| `date` | `lib/client/renderer.js:29-33` `getOrAddDate`, `lib/client/index.js:167-171`, only when absent | a `Date` at the old time | yes, when it is a `Date` object | a stored `date` is set to the new time |
| `endmills` | `lib/data/ddata.js:53-65`, `lib/profilefunctions.js:300-302` | the old end time | yes | yes |
| `mgdl` | `lib/data/treatmenttocurve.js:69,76,78` | glucose at the old time | yes | yes |
| `scaled` | `lib/sandbox.js:258-264` `scaleEntry` | the same, in display units | yes | yes |
| `cuttedby`, `cutting` | `lib/data/ddata.js:247-248` `processDurations` | profile names at the old overlap | yes | no |

`eventType: ''`, `mmol`, `absolute`, `duration` and `action` are also page-derived but are not
time-derived, or cannot be told apart from a stored value, so they are left alone.

**`date` is the one field that is both page-added and stored by uploaders.** The page adds it as a
`Date` object, and everything that reaches the page arrives as JSON, so a `date` that is not a `Date`
came from storage.

## The fix (#8760)

One commit, `8d797ba4`: new `lib/client/treatmenttime.js` (three functions), wired into
`lib/client/renderer.js` (the three move cases) and `lib/report_plugins/treatments.js` (the Reports
editor's Save); new `tests/treatmenttime.test.js`; `tests/dependency-d3.test.js` updated.

| path | before | with #8760 |
|---|---|---|
| Move carbs / Move insulin, new record (`dbAdd`) | a JSON copy of the page object | the copy without the page-added fields; a stored `date` becomes the new time in epoch ms |
| Move carbs / Move insulin, the half left behind | `dbUpdateUnset {carbs\|insulin}` | also unsets `mills`, `endmills`, `mgdl`, `scaled`, and updates a stored `date` that disagrees with `created_at` |
| plain Move | `dbUpdate {created_at}` | `dbUpdateUnset {mills, endmills, mgdl, scaled}`, then `dbUpdate {created_at[, date]}` |
| Reports editor Save (`PUT /api/v1/treatments`) | the record minus `mills` and `created_at` | also minus `endmills`, `mgdl`, `scaled`; a stored `date` set to the edited time |

**Why `date` is set rather than removed.** API v3 stores a treatment's canonical time in `date` as
epoch ms (`lib/api3/generic/collection.js:176-199`; immutable to v3 clients,
`lib/api3/generic/update/validate.js:21`), and does not synthesise it on read. AAPS NSClientV3 writes
`date` only, AAPS classic NSClient sends `date` as epoch ms over websocket `dbAdd`, and nightguard
sends `date` and `mills` as epoch ms. Removing `date` would take the time away from records those
clients read. A number is used because that is v3's shape and the chart can draw it. A record with no
stored `date` does not gain one.

**A plain Move is two writes**, because the websocket API has no combined `$set` + `$unset`. The
unset goes first; each handler reads the document back after its write, so the later broadcast
carries both changes.

## Method

- **Browser, by hand** (15.0.8 and the 15.0.9 candidate): a Meal Bolus with 25 g and 2.5 U was dropped
  in the chart's "Move carbs" zone, and the stored documents were read from MongoDB. On both trees the
  new record had `created_at` at the new time and `mills` / `date` 13–53 min earlier, plus `mgdl`
  (and `scaled` on the candidate).
- **IOB and COB, controlled.** One treatment of the split's shape was inserted, the server restarted,
  and `GET /api/v2/properties/iob,cob` read. The page-added fields were then `$unset` on the same
  document, and the restart and read repeated. The second read is the control: the same document at
  its `created_at` counts in full (COB 25 g, IOB 2.49 U), so the zero is attributable to the stale
  `mills`.
- **Browser probe** `tools/review/probes/bf103-split-drag-browser.js` (playwright-core driving Chrome;
  synthetic data; own `mongo:7`, `AUTH_DEFAULT_ROLES=denied`). Each phase seeds one treatment, restarts,
  changes its time through the page or the API, and applies the control above. A phase passes only if
  stored equals control, `created_at` is the axis-predicted time (±2 px), no page-added field remains,
  and no glyph has an invalid transform.

| phase | via | before #8760 | with #8760 |
|---|---|---|---|
| splitCarbs | drag Move carbs | COB 0 vs 25, stale fields left, 5 invalid glyphs | 25 = 25, none left |
| splitInsulin | drag Move insulin | IOB 0.998 vs 2.494 | 2.494 = 2.494 |
| moveDamagedRc | plain Move of a record damaged in the 15.0.9-candidate shape | COB 26.19 vs 50 | 50 = 50; glyph redrawn |
| moveDamaged1508 | plain Move, 15.0.8 shape | IOB 3.48 vs 4.986 | 4.986 = 4.986 |
| splitDamaged | Move carbs of a damaged carbs+insulin record | IOB 1.002 vs 2.46; both halves stale | 2.46 = 2.46 |
| moveV3 | plain Move, v3 record | COB 65 = 65, but `date` left 54.9 min before `created_at` | `date` = new time |
| splitV3 | Move carbs, v3 record | COB 0 vs 25 | 25 = 25 |
| reportEditDamaged | Reports editor Save | COB 50 = 50; old `date`, `mgdl`, `scaled` left | none left |
| v1PutDamaged | GET, change `created_at`, PUT | COB 50 vs 75 | 50 vs 75 (unchanged, out of scope) |

**Tests in the suite.** `tests/treatmenttime.test.js`, 13 cases (the file cannot load on `dev` before
#8760). `tests/dependency-d3.test.js` drives the real drag handlers in jsdom: 21 passing / 3 failing
before, 24 passing with the fix.

**Break-its** (one hunk each, restored after, `git status` clean):

| # | break | unit tests | browser probe |
|---|---|---|---|
| B1 | the split copy keeps the page-added fields | 4 failing | splitCarbs stale |
| B2 | the split copy keeps a page-added `Date` `date` | 3 failing | splitCarbs: `date` left, invalid glyphs |
| B3 | a time change unsets nothing | 5 failing | moveDamagedRc stale |
| B4 | a time change never sets `date` | 2 failing | moveV3: `date` stale |
| B5 | plain Move does not emit the unset | 1 failing | moveDamagedRc stale |
| B6 | Move carbs builds the old JSON copy | 1 failing | splitCarbs stale |
| B7 | Move carbs unsets only `carbs` on the half left behind | 1 failing | splitDamaged stale |
| B8 | Move carbs never updates the left-behind `date` | **0 failing** | splitDamaged: `date` stale |
| B9 | Reports editor back to `delete data.mills` only | **0 failing** | reportEditDamaged: fields left |

B8 and B9 are caught only by the browser probe. The maintainer also checked #8760's head by hand in
Chrome ([manual lab](manual-lab-15.0.9-rc-2026-09-23.md)): both split zones land at the new time with
no console errors and survive a reload, and a plain Move of a pre-damaged record repairs it.

## Other ways to change a treatment's time

The main page has no treatment edit dialog, and its Care Portal only creates records. The
time-changing paths are the drag, the Reports editor and the API.

| path | before #8760 | with #8760 |
|---|---|---|
| drag Move of a damaged record | does not repair | repairs |
| Reports > Treatments > edit > Save | IOB/COB follow once the server reloads (about 70 s); `date` stays old, so the chart still draws the record top-left | repairs everything |
| raw `PUT /api/v1/treatments` with the stored document | does not repair (`save` is a `replaceOne` of what is sent) | unchanged |

The Reports editor sends form-encoded data, so every field arrives as a string; `prepareData`
converts the numeric treatment fields back, but not `date`, `mgdl` or `scaled`. With #8760 a moved
`date` is therefore stored as a digit string (the chart draws it; a v3 reader receives a string).

## Server-side alternatives, measured and not built

Both were prototyped on a copy of `dev`, measured with the full suite and the browser probe, and
reverted.

- **(a) `ddata` prefers `created_at` when a stored `mills` disagrees by more than 60 s.** Suite
  2440/0/3. IOB/COB follow on every phase, including the raw v1 PUT and already-damaged records, with
  no write. It leaves every stale `date`, `mgdl` and `scaled`, so damaged glyphs stay top-left and v3
  readers still get the old `date`. The rule is in `processRawDataForRuntime`, which serves every
  collection: it also retimed a device status whose `mills` was 5 min off. A treatments-only form needs
  a collection argument the function does not have.
- **(b) The server drops client-supplied `mills` / `mgdl` / `scaled` on websocket treatment `dbAdd`.**
  Suite 2440/0/3. New splits follow; already-damaged records and the raw v1 PUT do not. The split
  still stores the old `date` as an ISO string. By a source read (not run), only the web page sends
  those fields over websocket: AAPS classic NSClient sends `date` and no `mills`, `mgdl` or `scaled`;
  xDrip+ Android hands `dbAdd` to a paired NSClient with `created_at` only; no treatment `dbAdd` was
  found in xDrip4iOS, LoopFollow, Trio, nightguard, nightscout-connect or NightscoutServiceKit
  (rileylink_ios's NightscoutService was not read). Clone SHAs: AndroidAPS `598e2eb39c`, xDrip
  `1e86d9a2a`, Trio `40f097fdd`, LoopWorkspace `4319ce5`, NightscoutKit `4ec9fd1`, nightguard
  `9ea3dea`, xdripswift `96b6afe2`, LoopFollow `9d2cea6b`, nightscout-connect `649a7de`.

Neither alone repairs the display or the v3 `date`. Only (a) repairs damaged records with no user
action and covers the raw PUT path.

## Found along the way, not changed

- **A split duplicates identity fields.** The copy keeps `identifier` (and `srvCreated` /
  `srvModified` and uploader ids where present), so both halves of a split v3 record carry the same
  `identifier`.
- **Websocket `dbAdd` "similar" dedup** (`lib/server/websocket.js` `processSingleDbAdd`) updates only
  an existing record's `created_at`, which is another time change that can leave a stored `mills`
  behind. Not exercised.
- **Websocket `dbUpdate` does not set `srvModified`**, so API v3 history readers may not see a move.
  Not measured.
- `docs/10-domain/websocket-event-coverage.md:237` says the legacy websocket `dbAdd` / `dbUpdate`
  events are "primarily used by the web interface"; AAPS classic NSClient also uses them.

## Finding affected records (read-only)

This lists treatments whose stored `mills` or `date` disagrees with `created_at` by more than a
minute, whose `date` is a non-numeric string (drawn at the chart's top-left), or whose `created_at`
cannot be read. It changes nothing. It requires MongoDB 4.2 or later.

```js
db.treatments.aggregate([
  { $match: { $or: [ { mills: { $exists: true } }, { date: { $exists: true } } ] } },
  { $addFields: {
      _caMs: { $toLong: { $convert: { input: '$created_at', to: 'date', onError: null, onNull: null } } },
      _millsMs: { $convert: { input: '$mills', to: 'long', onError: null, onNull: null } },
      _dateType: { $type: '$date' },
      _dateMs: { $switch: {
        branches: [
          { case: { $in: [ { $type: '$date' }, [ 'double', 'int', 'long', 'decimal', 'date' ] ] },
            then: { $toLong: '$date' } },
          { case: { $and: [ { $eq: [ { $type: '$date' }, 'string' ] },
                            { $regexMatch: { input: '$date', regex: /^[0-9]+$/ } } ] },
            then: { $toLong: '$date' } },
          { case: { $eq: [ { $type: '$date' }, 'string' ] },
            then: { $toLong: { $convert: { input: '$date', to: 'date', onError: null, onNull: null } } } }
        ],
        default: null } }
  } },
  { $addFields: {
      millsOffMin: { $cond: [ { $and: [ { $ne: [ '$_millsMs', null ] }, { $ne: [ '$_caMs', null ] } ] },
        { $round: [ { $divide: [ { $subtract: [ '$_millsMs', '$_caMs' ] }, 60000 ] }, 1 ] }, null ] },
      dateOffMin: { $cond: [ { $and: [ { $ne: [ '$_dateMs', null ] }, { $ne: [ '$_caMs', null ] } ] },
        { $round: [ { $divide: [ { $subtract: [ '$_dateMs', '$_caMs' ] }, 60000 ] }, 1 ] }, null ] },
      dateIsTextTime: { $and: [ { $eq: [ '$_dateType', 'string' ] },
        { $not: [ { $regexMatch: { input: { $ifNull: [ { $toString: '$date' }, '' ] }, regex: /^[0-9]+$/ } } ] } ] },
      createdAtUnreadable: { $eq: [ '$_caMs', null ] }
  } },
  { $match: { $or: [
      { millsOffMin: { $gt: 1 } }, { millsOffMin: { $lt: -1 } },
      { dateOffMin: { $gt: 1 } }, { dateOffMin: { $lt: -1 } },
      { dateIsTextTime: true }, { createdAtUnreadable: true } ] } },
  { $project: { created_at: 1, eventType: 1, carbs: 1, insulin: 1, mills: 1, date: 1,
      millsOffMin: 1, dateOffMin: 1, dateIsTextTime: 1, createdAtUnreadable: 1 } },
  { $sort: { created_at: -1 } }
]);
```

Checked on 12 synthetic records: it flags the 15.0.9-candidate and 15.0.8 damage shapes, a v3 record
moved before #8760, digit-string and BSON-date `date` values 30 min off, an ISO `date` equal to
`created_at` (as text), and an unreadable `created_at`. It does not flag a v3 record whose `date`
equals `created_at`, a nightguard-style record with `mills` = `date` = `created_at`, a plain v1
record, a `+02:00` `created_at` with matching `mills`, or `mills` 30 s off.

No repair is scripted and no boot migration is added. With #8760, dragging an affected treatment to
its intended time (a plain Move) or saving it in the Reports editor rewrites it. Anyone repairing
records by hand should review each one with the person whose data it is first.

## Open

| item | owner |
|---|---|
| whether the split copy should also drop `identifier` and the other identity fields | maintainer |
| whether to add alternative (a) in a treatments-only form, which reaches existing records and the raw PUT path | maintainer |
| on 15.0.8, a by-hand check that editing a damaged treatment's time in Reports makes IOB/COB follow after the reload. That decides whether it can be published as the workaround for sites still on 15.0.8. It is expected from the code (15.0.8's editor has the same `delete data.mills`, `lib/report_plugins/treatments.js:212`) but not measured | maintainer's lab |

## For people running Nightscout (user-facing)

If you drag a treatment that has both carbs and insulin on the Nightscout chart and drop it in the
"Move carbs" or "Move insulin" area, Nightscout 15.0.8 shows and saves the new time, but its own
insulin-on-board (IOB) and carbs-on-board (COB) figures keep using the old time. The moved item also
appears in the top-left corner of the chart. Moving a whole treatment is not affected.

This is fixed in the development version and arrives with the next release, 15.0.9. Until you are
running 15.0.9, don't drop a treatment in the "Move carbs" or "Move insulin" area. In 15.0.9, moving
an already-affected treatment to its intended time corrects it. If you rely on Nightscout's IOB, COB
or Bolus Wizard, check with your care team about how to handle any treatments already moved this
way. This is not medical advice.
