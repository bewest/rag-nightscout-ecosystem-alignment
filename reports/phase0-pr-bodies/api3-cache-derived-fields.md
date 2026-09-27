<!-- Draft body for branch bf/api3-cache-derived-fields at d235bdf6 (two commits on dev 699eb5fa: db99bba4, d235bdf6), 2026-09-26. This comment is hidden on GitHub. Not opened; not pushed. -->
Treatments and device status written through API v3 now enter the server's in-memory data with the same time fields as those written through API v1 (BF-146). Two commits on `dev` `699eb5fa`: `db99bba4` (treatments) and `d235bdf6` (device status, added for consistency by the maintainer's decision of 2026-09-26). This also fixes BF-133 (the COB pill's "last carbs" line naming an older entry). The same code is in `v15.0.8`, so this is not a regression. Found by the 15.0.9 release-candidate soak (run 019). The maintainer decided on 2026-09-26 to fix it for 15.0.9. Nothing stored in MongoDB changes, and API v3 responses do not change.

## What changes for you

*A plain-language summary for people who run their own Nightscout site, for themselves or for a family member. Nightscout is not a medical device, and nothing here is medical advice. Nothing here tells you how to dose. If your carb or insulin numbers look wrong, check them against the app that entered them and talk to your care team before you rely on them.*

A few words used below:

- **Treatment**: a saved carb entry, insulin dose (bolus), temporary basal, temporary target or note.
- **IOB (insulin on board)**: how much insulin from earlier doses Nightscout estimates is still working.
- **COB (carbs on board)**: how many grams of carbs from earlier entries Nightscout estimates are still being absorbed.
- **Device status**: a regular report from your phone app or pump, which can include the app's own IOB and COB.
- **API v3**: one of the ways apps talk to Nightscout. AndroidAPS uses it to upload and edit treatments.

**What was wrong.** Nightscout works out IOB and COB from your treatments. When an app that uses API v3 (such as AndroidAPS) uploaded a bolus or a carb entry **late** (for example after the phone had been offline for a while), or **edited an older** treatment, Nightscout could keep that treatment in memory without the time field its calculations use. Until the Nightscout server was restarted:

- that bolus or carb entry was **left out** of the IOB and COB Nightscout works out from treatments, both on the server and in the browser;
- the treatments were **no longer in time order**. The COB calculation depends on that order, so the COB number could come out **too high** (carbs that had already been absorbed were counted again), and the "last carbs" line under the COB pill could name an **older** carb entry instead of the newest.

A treatment uploaded on time, or through API v1, was counted as normal. A server restart put everything right until the next late upload or edit.

**Which numbers could have been wrong.** The IOB and COB that Nightscout works out from treatments: the IOB and COB pills when no current value comes from device status, the "last carbs" line, the values other apps read from Nightscout's properties, and the same numbers worked out in the browser. **If your app reports its own IOB and COB in device status** (an AndroidAPS site that uploads its device status does), the pills show the app's values instead, so they were not affected. AndroidAPS works out its own IOB and COB on the phone; the numbers affected here are the ones Nightscout shows and shares.

**Device status.** The same gap affected device status sent late through API v3: when another app asked Nightscout for the latest device statuses, such a status could be listed after older ones, or left out of a short list.

**What this change does.** A treatment or device status written through API v3 now enters Nightscout's memory with the same time field as one written through API v1, so treatments count in IOB and COB, the treatments stay in time order, and device statuses are listed in time order.

**Do you need to do anything?** No. After updating, the numbers are right from the first load.

## Technical detail

### The defect

Every v1 write path in `lib/server/treatments.js` emits its documents to the cache through `ddata.processRawDataForRuntime`, which adds `mills` (from `created_at`) and `endmills` (from a duration). The API v3 storage wrapper `lib/api3/storage/mongoCachedCollection/index.js` (`updateInCache`) emitted the stored document as it is. The cache keeps such a record, since its age falls back to `date`.

Once the cache holds at least 20 treatments (`cache.isEmpty`), the dataloader refetches only its most recent minutes from MongoDB. A v3 record inside that window comes back with `mills` and replaces the cached copy; a record dated earlier does not. So a late v3 upload, or a v3 PUT or PATCH of an older record, stays in memory without `mills` until restart or until it leaves the cache's retention. Then:

- `lib/plugins/iob.js` counts a treatment only when `mills <= time`, and `cob.js` only when `mills < time`, so the record counts in neither.
- The dataloader sorts the treatments with `(a, b) => a.mills - b.mills`. With one record lacking `mills` the comparator returns `NaN` for every pair that includes it, and the array is no longer in time order. `cob.js` takes "last carbs" as the last carb entry in array order, and chains each entry's decay (`lastDecayedBy`) on the one before it in array order, so an absorbed entry that comes after a newer one is counted again.
- The websocket sends the same array to the browser, whose IOB and COB use the same plugins.

### What the commits do

`updateInCache` passes treatments (`db99bba4`) and device status (`d235bdf6`) through `ctx.ddata.processRawDataForRuntime` before the `data-update` event, the helper the v1 paths in `lib/server/treatments.js` and `lib/server/devicestatus.js` use. It derives on a copy, so nothing stored changes (the v1 paths store no `mills` either). Entries are passed on as before: their readers take the time from `date` (measured: a late v3 reading is in its place in `GET /api/v1/entries` and in the page's glucose data).

One visible side effect: `GET /api/v1/treatments` served from memory (no query other than `count`) now shows `mills` on v3-written records too (and `endmills`, or a `duration` derived from `durationInMilliseconds`, where the helper adds them), as it already did on v1-written records. Their order there is unchanged, since the cache already ordered them by `date`.

`GET /api/v1/devicestatus` served from memory (no query other than `count`) sorts the cached records by `mills`, counting a missing one as 0. A v3 status dated before the refetch window was therefore placed after every other one. With the second commit it takes its place by time and shows `mills`, as v1-written records there already do. For the whole held set the records returned are the same and only that status moves (last to first in the test); for a smaller count, such a status can now be inside the window where it was left out. The dataloader, the pills and the page data already derived `mills` for device status and do not change. With `DENORMALIZE_DATES` on, that read rewrites `created_at` on the cached records in place (existing behaviour); the derived `mills` still matches the record's time over repeated reads.

## Tests

`tests/api3.cache-derived-fields.test.js`, 15 tests on a real MongoDB. 24 note treatments and 24 device statuses are written first so that every test runs on the incremental load; `beforeEach` hooks check that `cache.isEmpty` is false for both.

- **Fail on `dev` `699eb5fa` and on `v15.0.8` `92d08342`** with the original symptom (10): a v3 bolus dated 40 minutes ago gives IOB 0; v3 carbs dated 40 minutes ago give COB 0; the same bolus after a v3 PATCH and a v3 PUT gives IOB 0; the page data sent over the socket gives IOB 0; mixed v1 and v3 writes load in reverse time order; "last carbs" names the older entry after a v3 write and an edit of that older entry (BF-133); COB is 34.5 g where the same records in time order give 10 g; a late v3 device status newer than all others is missing from the default `GET /api/v1/devicestatus`; the whole held set comes back with it last instead of first; the same with `DENORMALIZE_DATES` on.
- **Pass on all trees** (the controls, 5): a v1 bolus of the same age counts; a v3 bolus dated now counts; a v1 status of the same age is in its place; a v3 status dated now is first; the page's device status holds the late v3 status with its time.
- On `db99bba4` (treatments only) the 3 device status tests fail and the other 12 pass.

### Break-it

Deriving the fields and then dropping `mills` gives the same red (7 treatment tests; 3 device status tests). Deriving them only for a create, not a PUT or PATCH, turns the PUT/PATCH test red. Leaving device status out turns the 3 device status tests red. Restored, 15 passing.

### Full suite

`npm test` on `d235bdf6`, fresh database: **3473 passing, 0 failing, 3 pending** (Node 22.23.2, MongoDB 7.0.43 read from the server). `dev` `699eb5fa` is 3458/0/3 and `db99bba4` 3467/0/3; the difference is the 15 new tests. No existing test changed.

### Probes (alignment repo, `tools/lab/triage-2026-09/`)

`same-time-carbs.js`, `same-time-resend-shapes.js`, `retry-keeps-srvcreated.js` and `v1-writes-v3-history.js` give the same output on `699eb5fa`, `db99bba4` and `d235bdf6`. `v1-writes-v3-history.js` exits 1 on all of them, on its v1 DELETE arm only, as before.

## Client impact

AndroidAPS uploads and edits treatments through API v3; its late uploads and edits of older treatments are the records this change makes count. Clients that read IOB and COB from Nightscout's properties, and the Nightscout page itself, get the corrected treatment-based values. Clients that read the latest device statuses through `GET /api/v1/devicestatus` with only a `count` get a late AndroidAPS status in its place by time. Where a current IOB or COB comes from device status, that value is still preferred, as before.
