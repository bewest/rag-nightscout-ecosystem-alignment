# Nightscout Write Purification Compatibility Deep Dive

Date: 2026-09-02

## Summary

Nightscout stored-XSS mitigation that purifies write payloads for data collections is expected to have low compatibility impact for typical mobile and edge clients. The reviewed clients model Nightscout treatment metadata as plain strings, JSON objects, or stringified JSON payloads; no reviewed upload path intentionally uses HTML markup in `notes`, `enteredBy`, `reason`, `foodType`, profile names, or treatment event metadata.

The main asymmetry to close is server-side consistency: mutable Nightscout data writes should receive equivalent purification whether they arrive through API v1 REST, API v3 REST, or legacy WebSocket write paths. Output escaping remains necessary because older stored records and non-purified historical data may still be rendered.

## Compatibility Finding

| Client / Library | Write Surface | Evidence | HTML Dependency Assessment |
|------------------|---------------|----------|----------------------------|
| Loop / NightscoutKit | API v1 treatment upload | `NightscoutTreatment.dictionaryRepresentation` serializes `enteredBy`, `notes`, and `eventType` as string fields (`externals/NightscoutKit/Sources/NightscoutKit/Models/Treatments/NightscoutTreatment.swift:105-113`). Loop extensions populate treatment strings such as override `reason`, carb `foodType`, and dose metadata (`externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/Extensions/OverrideTreament.swift`, `SyncCarbObject.swift`, `DoseEntry.swift`). | Plain text. No intentional HTML formatting found. |
| AAPS | API v3 treatment, entries, device status, food, profile writes | API v3 Retrofit endpoints post `RemoteTreatment`, `RemoteEntry`, `RemoteDeviceStatus`, `RemoteFood`, and profile JSON to `/v3/*` (`externals/AndroidAPS/core/nssdk/src/main/kotlin/app/aaps/core/nssdk/networking/NightscoutRemoteService.kt:40-89`). `RemoteTreatment` defines `reason`, `notes`, `enteredBy`, `profileJson`, and `bolusCalculatorResult` as strings (`externals/AndroidAPS/core/nssdk/src/main/kotlin/app/aaps/core/nssdk/remotemodel/RemoteTreatment.kt:52-76`). Conversion extensions pass domain values through as notes/profile JSON rather than markup (`externals/AndroidAPS/plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/ProfileSwitchExtension.kt:19-60`, `BolusCalculatorResultExtension.kt:12-30`). | Plain text/stringified JSON. Sanitization should not affect normal payloads; only unusual literal HTML or angle-bracket text inside free strings would be encoded or stripped. |
| Trio | API v1 treatment model | Trio's Nightscout treatment model stores fields such as `enteredBy`, `notes`, `foodType`, `glucoseType`, `glucose`, and `units` as optional strings (`externals/Trio/Trio/Sources/Models/NightscoutTreatment.swift`). | Plain text. No intentional HTML formatting found. |
| xDrip+ | API v1 / sync treatment JSON | Treatment creation sets `enteredBy` from `XDRIP_TAG`, uses legacy event type `<none>`, stores user notes as a string, and serializes only `notes` and `enteredBy` in `toJSON()` (`externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/models/Treatments.java:287-289`, `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/models/Treatments.java:1358-1359`; wear equivalent at `externals/xDrip/wear/src/main/java/com/eveningoutpost/dexdrip/models/Treatments.java:103-111`, `:1000-1001`). | Plain text. The legacy `<none>` event type is semantic text, not HTML markup; purifier behavior should preserve it as text when stored through normal JSON APIs. |
| xDrip4iOS | Read/display treatment and device-status values | Treatment response parsing reads `eventType` and `enteredBy` as strings (`externals/xdripswift/xDrip/Treatments/TreatmentNSResponse.swift:77-85`). Device-status display decodes escaped comparator entities in OpenAPS reasons (`externals/xdripswift/xDrip/Managers/Nightscout/NightscoutDeviceStatusModels.swift:127-131`). | No treatment upload HTML dependency found. The comparator decoding supports textual math symbols (`<`, `>`, `<=`, `>=`) in reasons, not executable markup. |
| tconnectsync | API v1 Nightscout object generation | Parser constructs treatment dictionaries with `reason`, `notes`, and `enteredBy` fields as strings (`externals/tconnectsync/tconnectsync/parser/nightscout.py:30-40`, `:50-57`, `:169-192`). Profile export notes a Nightscout string requirement for top-level fields, not HTML (`externals/tconnectsync/tconnectsync/parser/nightscout.py:212-226`). | Plain text. No intentional HTML formatting found. |
| LoopCaregiver / follower apps | Mostly read/follow; remote command support via NightscoutKit dependency | LoopCaregiver depends on NightscoutKit (`externals/LoopCaregiver/LoopCaregiverKit/Package.swift:17-25`) and mostly displays treatment data in UI paths. | No independent treatment HTML upload dependency found in reviewed paths. |

## Important Asymmetries

### API v3 write purification parity

API v3 is the most important asymmetry because AAPS is a major v3 client and API v3 treatment writes can reach the same report/dashboard rendering surfaces as v1 and WebSocket writes. A complete mitigation should purify mutable data collection write bodies consistently across API v3 create, replace/upsert, and patch operations.

### WebSocket authorization versus API v3 treatment create

The legacy WebSocket treatment write path requires a broader write-treatment capability than a simple API v3 create. The practical impact statement should avoid saying the bug escalates a no-write actor into a treatment writer. A more accurate statement is that an actor already permitted to write treatments can control stored script content that later executes in another viewer's browser context, changing where, when, and under whose session context the action occurs.

### Structured JSON fields inside data collections

AAPS sends some treatment fields as stringified JSON (`profileJson`, `bolusCalculatorResult`) and sends device-status/profile data as nested JSON objects. Normal generated content does not require HTML, but a sanitizer that recursively purifies every string leaf may encode or strip literal HTML-looking substrings in arbitrary user labels. This is acceptable for a security boundary if documented, but should be included in regression testing with representative AAPS profile-switch and bolus-wizard payloads.

### Settings collection

The `settings` collection should be considered separately from mutable telemetry/treatment collections. It can contain application configuration strings and is typically admin-controlled; applying broad HTML purification there risks behavior changes outside the stored-XSS treatment/report threat path.

## Recommended Clarification for Advisory / PR Text

Recommended impact wording:

> A token or session with treatment-write permission could store crafted treatment fields that later executed JavaScript when viewed in affected Nightscout UI/report surfaces. This does not grant treatment-write permission to an actor who lacks it; instead, it lets an existing treatment writer shift execution into another viewer's browser/session context, potentially causing actions available to that viewer or exposing viewer-context data.

Recommended compatibility wording:

> Reviewed Loop, AAPS, Trio, xDrip+, xDrip4iOS, tconnectsync, and NightscoutKit upload paths treat Nightscout metadata fields as plain text or structured JSON, not intentional HTML. Server-side purification is therefore not expected to break typical mobile/edge-client writes, though literal HTML-looking text in free-text fields may be normalized for safety.

## Recommendations

1. Preserve output escaping in every dashboard/report sink even after input purification, because historical records may already contain unsafe strings.
2. Keep API v1 REST, API v3 REST, and legacy WebSocket write purification behavior aligned for mutable data collections: `entries`, `treatments`, `devicestatus`, `food`, and `profile`.
3. Add regression tests with representative AAPS v3 treatment/profile-switch and xDrip+ `<none>` treatment payloads to demonstrate compatibility and prevent future sanitizer regressions.
4. Exclude or separately risk-assess admin/configuration collections such as `settings` before applying broad recursive purification.

