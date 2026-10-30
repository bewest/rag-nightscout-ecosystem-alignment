# Upstream ask (draft): AndroidAPS NSClientV3, bound or handle a 410 reply

*Contributor-facing outreach draft, 2026-10-30, prepared by session -4f from the AndroidAPS code (read, not run). Not sent. Companion to the [questions for controller and uploader authors](README.md).*

**To:** AndroidAPS maintainers (nightscout/AndroidAPS), NSClientV3 plugin
**From:** Nightscout cgm-remote-monitor maintainers
**Status:** draft for the upstream-asks list, not filed
**Pins:** AndroidAPS `7e1d537d49`, unchanged on `origin/dev` `325e562380`; cgm-remote-monitor `dev` `ca1652d6`

## Summary

When Nightscout's API v3 answers an NSClientV3 upload with **410 Gone**, NSClientV3 stops uploading that collection and retries the same record without limit. API v3 answers 410 when a client updates a record that is soft-deleted on the server. We ask that NSClientV3 bound or handle 410, the way it already bounds 404.

## What happens today

- **What 410 means:** API v3 answers `PATCH`/`PUT /api/v3/{collection}/{identifier}` with 410 when the stored record is soft-deleted (`isValid: false`). This is documented API v3 behaviour, and Nightscout 16.0.0 keeps it.
- **How NSClientV3 handles each status:** `dbOperation*` in `plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/NSClientV3Plugin.kt` (e.g. treatments, `:1012-1030`) branches on the status:
  - 200, 201 and 400 advance the cursor. 400 is logged as FAIL and dropped.
  - 404 retries an UPDATE up to `maxUpdateRetries`, then gives up (`retryUpdateLater`, `:720-730`).
  - **Any other status, 410 included, takes `else -> return config.isEnabled(IGNORE_NS_V3_ERRORS)`.** With that option off (the default), the call returns `false`, the collection's sync cursor does not advance, and the next round sends the same update again. Nothing bounds it.
- **Where else:** the same `else` branch appears in the profile store, device status, entries, calibrations and food paths (`:761-763`, `:786-788` and the matching blocks below them).

## How a record reaches that state

1. **A record deleted on the server while AndroidAPS still holds it as valid.** A caregiver or the user deletes a treatment in Nightscout's web UI, or another uploader deletes it. The AndroidAPS row is still valid locally. The next local change to it (a temp target ended, a temp basal or extended bolus closed, a profile switch updated) is sent as a `PATCH` and answered 410. This can happen with today's released servers.
2. **A re-entry that matches a deleted record.** This is the case we weighed for 16.0.0.
   - AndroidAPS treatments carry no `device`, so the identifier API v3 computes is `undefined_<date>_<eventType>`.
   - A carb entry deleted and re-entered at the same minute through the time picker (seconds set to zero, `EventTimePickers.kt`) gets the identifier of the deleted record.
   - If the server keeps that record deleted, any later update to the new row is answered 410.
   - For this reason, Nightscout 16.0.0 keeps **reviving** a deleted treatment on such a re-create. Bounding 410 in NSClientV3 would let a future version stop reviving it.

## Effect on the user

Uploads for that collection stop until the user notices and acts. For treatments, that means boluses, carbs, temp basals and temp targets stop reaching Nightscout. Followers, caregivers and reports then see stale data. The phone keeps looping, so this does not affect dosing on the phone. It does affect everyone who relies on Nightscout to see what happened.

## What we ask

Any of the following, in order of preference:

1. **Treat 410 on an UPDATE as final for that record.** Log it, mark the local row as synced or as deleted on the server (as the download path already does for `isValid: false`), and advance the cursor.
2. **Bound it like 404:** route 410 through `retryUpdateLater`, so the cursor advances after `maxUpdateRetries`.
3. At minimum, show the user a notification naming the stuck record, so the stall is visible.

Optionally: on 410, read the record (`GET /api/v3/{collection}/{identifier}`) and copy `isValid: false` into the local row, matching `SyncNs*Transaction`.

## What Nightscout does in 16.0.0

- API v3 `PATCH`/`PUT` of a soft-deleted record keeps answering 410.
- A v3 create that matches a deleted **treatment** keeps reviving it, as it does today (decided 2026-10-30, because of this stall).
- For entries, profile, food and settings, a re-create that matches a deleted record is acknowledged (200 with the stored identifier), and the record stays deleted. AndroidAPS handles that reply as it handles today's (stores `nightscoutId`, marks the row synced). It never updates these records after creating them, except glucose values; see "For AndroidAPS to verify".
- We would like to treat treatments the same way once NSClientV3 bounds or handles 410.

## For AndroidAPS to verify

- Whether a glucose value can be PATCHed while it is valid. Our reading says no, which is why entries can stay deleted in 16.0.0:
  - an invalidated glucose value is sent as a v3 DELETE, which answers 404 for an already-deleted record, and NSClientV3 counts that as success (`NSAndroidClientImpl.kt:228-231`);
  - `UpdateGlucoseValueTransaction` has no non-test caller;
  - a change that only adds an NS id is not uploaded (`DataSyncSelectorV3.kt:471`).
  Please confirm no other path updates a valid glucose value.
- That `getByNSId` returns the older, already-invalid row first when two local rows share a `nightscoutId`.
- Whether a bolus and a carb entry can be stored with the same timestamp. They would then share a computed identifier, independent of deletes.
