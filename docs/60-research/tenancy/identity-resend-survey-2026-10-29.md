# Re-sends with the same identity: what clients rely on

> **Snapshot, 2026-10-29.** Contributor-facing. Read-only survey of client source at the refs below; server behaviour from the record-identity and v3-identifier-immutable labs. Input to D-LOOP-ID rule 3 (decided 2026-10-29: merge on match stays the default; a switch may select keep-first or refuse for clients that opt in).

Refs: LoopWorkspace v3.14.9 548b332 (Loop c30b5c89, LoopKit d9f14373, NightscoutService 2cef4896, NightscoutKit 4ec9fd1); Trio v1.0.2 0b29cd53; AndroidAPS 7e1d537d (master aa16db64 spot-checked); xDrip 2026.09.18 1ed76004; xdripswift 7.1.1 c268542e; nightscout-connect dev 04102f9d; tconnectsync v3.0.1 7c4b2f4; oref0 dev d219baf9; LoopFollow 4a74b781, LoopCaregiver 2305718, nightguard 75404bd; server cgm-remote-monitor ca1652d6.

## Answer
Loop (mutable doses, early-ended overrides) and Trio (finalized boluses/temp basals, temp targets) depend on update-on-re-send on v1 treatments, keyed by the time key or client id, and by `identifier` for Loop overrides. No client read relies on an API v3 re-send updating a record.

## Key findings
1. Loop doses: a mutable dose that changes is POSTed again with the same syncIdentifier ("all dose uploads are currently posting so they can be either create or update", NightscoutService Extensions/DoseEntry.swift:30,61; InsulinDeliveryStore.swift:454-458, 896-905; NightscoutUploader.swift:120-147; NightscoutClient.swift:62-68) [R].
2. Loop overrides: an early-ended override is re-sent with the new end (TemporaryScheduleOverrideHistory.swift:291-295), POSTed with `_id` = its syncIdentifier UUID (OverrideTreament.swift:59; NightscoutService.swift:157-186), which UUID_HANDLING moves to `identifier`. The newest override is also re-sent unchanged on every upload (anchor test `>=`) [R].
3. Trio pump events: when a finalized amount/rate/duration differs, the row is POSTed again with the same `id` ("the re-POST replaces the NS document in place", PumpHistoryStorage.swift:244-246, 259-261, 282-284; NightscoutManager.swift:1047-1094). Temp targets are re-POSTed with no id at the same created_at (TempTargetsStorage.swift:312-330). Overrides are deleted by created_at and re-POSTed when the duration changes (OverrideStorage.swift:372-375). Unverified: whether the bolus eventType changes at finalization (isSMB, PumpHistoryStorage.swift:258) [R].
4. Carb edits never re-send: Loop keeps syncIdentifier, bumps syncVersion (CachedCarbObject+CoreDataClass.swift:127-131) and sends a v1 PUT by an `_id` cached for 24 h; if the `_id` is not cached the edit is dropped silently (NightscoutUploader.swift:30-50, 36-41; NightscoutService.swift:27, 227; NightscoutClient.swift:83-85). Trio deletes and creates with a new UUID. AAPS PATCHes by identifier. xDrip and xDrip4iOS PUT by `_id`. The Loop reply's case 2 (carb edit as a re-send) does not match Loop 3.14.9 [R].
5. v1 PUT on treatments goes through the same upsert path as POST [M]. Any refusal rule must exempt PUT.
6. No shipping client sends one identity from two devices: Loop's watch doesn't link NightscoutKit; Trio watch carbs go via the phone with a new UUID (AppleWatchManager.swift:855, 919); AAPS followers ignore records from NS (DataSyncSelectorV3.kt:176-180). Case 1 (watch+phone G7) is Loop's proposal, not current behaviour. Not checked: xDrip+ Wear standalone upload; two nightscout-connect instances on one Glooko account (same identifier, map.js:35-40) [R].
7. Version fields: only Loop carbs send userEnteredAt/userLastModifiedAt (CarbCorrectionNightscoutTreatment.swift:99-104). syncVersion is never sent to Nightscout [R].
8. AAPS NSClientV3 creates once without identifier (server derives it, BolusExtension.kt:44), then PATCHes /api/v3/treatments/{identifier} or DELETEs (DataSyncSelectorV3.kt:175-196; NightscoutApi.kt:160-168); clears date/utcOffset before PATCH (NSAndroidClientImpl.kt:413-416); ignores isDeduplication (NSClientV3Plugin.kt:1033-1080). A v3 POST that matches replaces the stored record (lib/api3/generic/create/operation.js:47-59 @ca1652d6) [R].
9. xDrip4iOS BG rewrites drop `_id` and rely on the entries sysTime+type upsert (NightscoutSyncManager.swift:403-428) [R].

## Reaction to a 4xx
| client | behaviour |
|---|---|
| Loop | any non-200 fails the batch; anchor not advanced; retried on every trigger indefinitely, log only; a length-mismatched 200 also fails (NightscoutClient.swift:545-547, 486-501; RemoteDataServicesManager.swift:279-288, 106-111, 183) |
| Trio | throws, stays unsent, retried each pass, stops at first failing chunk of 100, not shown (NightscoutAPI.swift:331-333; NightscoutManager.swift:1034-1044, 1100-1112) |
| AAPS v3 | 400: logs FAIL, advances cursor, drops the record (NSAndroidClientImpl.kt:393-406; NSClientV3Plugin.kt:1012-1031, 700-731) |
| xDrip | pending, retried, optional notification (NightscoutUploader.java:518-522, 589-601, 619-640) |
| xDrip4iOS | unsent, retried; 500 with Mongo code 66 counts as success (:1692-1724) |
| nightscout-connect | backoff retry (not traced deeply) |
| tconnectsync | raises ApiException (caller not traced) |
| oref0 | curl -s without --fail: a 4xx exits 0 and logs "Uploaded" (bin/ns-upload.sh:41-51) |
| nightguard | shown to user |

## Summary
| client | edit mechanism | identity | version? | 4xx | depends on update-on-re-send |
|---|---|---|---|---|---|
| Loop carbs | v1 PUT, cached _id (dropped if uncached) | syncIdentifier + _id | userLastModifiedAt | batch retried forever | no |
| Loop doses | re-POST same syncIdentifier | syncIdentifier | no | same | yes (v1 time key / client id) |
| Loop overrides | re-POST same UUID _id -> identifier | _id UUID | no | same | yes (v1 identifier) |
| Trio carbs | delete + new UUID | id | no | retried | no |
| Trio boluses / temp basals | re-POST same id | id | no | retried | yes |
| Trio temp targets | re-POST same created_at | none | no | retried | yes (time key) |
| Trio overrides | delete + POST, or re-POST | none | no | retried | partly |
| AAPS NSClientV3 | v3 PATCH by identifier; DELETE | server identifier | no | 400 dropped | no |
| AAPS NSClient v1 | socket dbUpdate by _id | NSCLIENT_ID / _id | no | not traced | no |
| xDrip | v1 PUT, _id from uuid | uuid / _id | no | retried | no |
| xDrip4iOS treatments | v1 PUT by server _id | _id | no | retried | no |
| xDrip4iOS BG rewrite | re-POST no _id, same time | none | no | retried | yes (entries time key) |
| nightscout-connect | same identifier re-sent; changes get new id + delete | identifier hash | no | backoff | unknown |
| tconnectsync | delete + POST; profile PUT | pump_event_id | no | raises | no |
| oref0 | append-only | none | no | ignored | no |
| nightguard / LoopFollow / LoopCaregiver | no treatment edits | — | — | — | no |

## Not checked
Server handling of the Loop/Trio re-sends was not re-measured; AAPS read on a dev ref; xDrip+ Wear, Glooko guid stability, tconnectsync/nightscout-connect retry depth, Trio eventType at finalization.
