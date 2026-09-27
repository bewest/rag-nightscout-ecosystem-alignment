<!-- Draft body for branch bf/api3-cache-derived-fields at db99bba4 (one commit on dev 699eb5fa), 2026-09-26. This comment is hidden on GitHub. Not opened; not pushed. -->
Treatments written through API v3 now enter the server's in-memory data with the same time fields as treatments written through API v1 (BF-146). One commit (`db99bba4`, on `dev` `699eb5fa`). This also fixes BF-133 (the COB pill's "last carbs" line naming an older entry). The same code is in `v15.0.8`, so this is not a regression. Found by the 15.0.9 release-candidate soak (run 019). The maintainer decided on 2026-09-26 to fix it for 15.0.9. Nothing stored in MongoDB changes, and API v3 responses do not change.

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

**What this change does.** A treatment written through API v3 now enters Nightscout's memory with the same time field as one written through API v1, so it counts in IOB and COB and the treatments stay in time order.

**Do you need to do anything?** No. After updating, the numbers are right from the first load.

## Technical detail

### The defect

Every v1 write path in `lib/server/treatments.js` emits its documents to the cache through `ddata.processRawDataForRuntime`, which adds `mills` (from `created_at`) and `endmills` (from a duration). The API v3 storage wrapper `lib/api3/storage/mongoCachedCollection/index.js` (`updateInCache`) emitted the stored document as it is. The cache keeps such a record, since its age falls back to `date`.

Once the cache holds at least 20 treatments (`cache.isEmpty`), the dataloader refetches only its most recent minutes from MongoDB. A v3 record inside that window comes back with `mills` and replaces the cached copy; a record dated earlier does not. So a late v3 upload, or a v3 PUT or PATCH of an older record, stays in memory without `mills` until restart or until it leaves the cache's retention. Then:

- `lib/plugins/iob.js` counts a treatment only when `mills <= time`, and `cob.js` only when `mills < time`, so the record counts in neither.
- The dataloader sorts the treatments with `(a, b) => a.mills - b.mills`. With one record lacking `mills` the comparator returns `NaN` for every pair that includes it, and the array is no longer in time order. `cob.js` takes "last carbs" as the last carb entry in array order, and chains each entry's decay (`lastDecayedBy`) on the one before it in array order, so an absorbed entry that comes after a newer one is counted again.
- The websocket sends the same array to the browser, whose IOB and COB use the same plugins.

### What the commit does

`updateInCache` passes treatments through `ctx.ddata.processRawDataForRuntime` before the `data-update` event, the helper the v1 paths use. It derives on a copy, so nothing stored changes (the v1 paths store no `mills` either). Entries and device status are passed on as before: the dataloader builds the entries' `mills` from `date` and adds `mills` to its own copy of device status.

One visible side effect: `GET /api/v1/treatments` served from memory (no query other than `count`) now shows `mills` on v3-written records too (and `endmills`, or a `duration` derived from `durationInMilliseconds`, where the helper adds them), as it already did on v1-written records. Their order there is unchanged, since the cache already ordered them by `date`.

## Tests

`tests/api3.cache-derived-fields.test.js`, 9 tests on a real MongoDB. 24 note treatments are written first so that every test runs on the incremental load; a `beforeEach` checks that `cache.isEmpty('treatments')` is false.

- **Fail on `dev` `699eb5fa` and on `v15.0.8` `92d08342`** with the original symptom (7): a v3 bolus dated 40 minutes ago gives IOB 0; v3 carbs dated 40 minutes ago give COB 0; the same bolus after a v3 PATCH and a v3 PUT gives IOB 0; the page data sent over the socket gives IOB 0; mixed v1 and v3 writes load in reverse time order; "last carbs" names the older entry after a v3 write and an edit of that older entry (BF-133); COB is 34.5 g where the same records in time order give 10 g.
- **Pass on all three trees** (the controls, 2): a v1 bolus of the same age counts; a v3 bolus dated now counts.

### Break-it

Deriving the fields and then dropping `mills` gives the same 7 red. Deriving them only for a create, not a PUT or PATCH, turns the PUT/PATCH test red. Restored, 9 passing.

### Full suite

`npm test` on `db99bba4`, fresh database: **3467 passing, 0 failing, 3 pending** (Node 22.23.2, MongoDB 7.0.43 read from the server). `dev` `699eb5fa` is 3458/0/3; the difference is the 9 new tests.

### Probes (alignment repo, `tools/lab/triage-2026-09/`)

`same-time-carbs.js`, `same-time-resend-shapes.js`, `retry-keeps-srvcreated.js` and `v1-writes-v3-history.js` give the same output on `699eb5fa` and `db99bba4`. `v1-writes-v3-history.js` exits 1 on both, on its v1 DELETE arm only, as before.

### Not changed

`GET /api/v1/devicestatus` served from memory sorts the cached records by `mills`, counting a missing one as 0, so a late v3 device status is placed after every other one and can be missing from the default read (measured). Passing device status through the same helper would fix that, but it changes which records that read returns, so it is left for a separate decision.

## Client impact

AndroidAPS uploads and edits treatments through API v3; its late uploads and edits of older treatments are the records this change makes count. Clients that read IOB and COB from Nightscout's properties, and the Nightscout page itself, get the corrected treatment-based values. Where a current IOB or COB comes from device status, that value is still preferred, as before.
