# Client-Supplied `_id` Handling in Nightscout

**Status**: Active Issue  
**Primary Gap**: GAP-TREAT-012  
**Fix**: PR #8447 (Option G / REQ-SYNC-072)  
**Last Updated**: 2026-03-11

## Executive Summary

Some AID apps send client-generated UUIDs as the `_id` field when creating records via Nightscout's v1 API. MongoDB expects `_id` to be an ObjectId (24-char hex), causing failures when the server later attempts to coerce these UUIDs. This document tracks which apps exhibit this behavior, when the issue started, and the solution.

---

## Timeline

| Date | Event | Impact |
|------|-------|--------|
| **2022-02-16** | MongoDB driver v4 upgrade | Stricter ObjectId validation begins |
| **2022-02-28** | Loop override upload added ([commit 3dedcf7](https://github.com/LoopKit/NightscoutService/commit/3dedcf7)) | `_id: syncIdentifier.uuidString` pattern introduced |
| **2023-06-01** | MongoDB v5+ compatibility fix ([commit 32163a0c](https://github.com/nightscout/cgm-remote-monitor/commit/32163a0c)) | `new ObjectId(id)` pattern solidified |
| **2025-04-29** | Trio BloodGlucose uses UUID _id ([commit 99a351e2](https://github.com/nightscout/Trio/commit/99a351e2)) | CGM entries now affected |
| **2026-03-08** | Issue #8450 reported | Override sync breaking in production |
| **2026-03-10** | Option G implemented (PR #8447) | Fix for treatments collection |

---

## Problem Statement

### What Happens

1. **Client POSTs** a treatment/entry with `_id: "550e8400-e29b-41d4-a716-446655440000"` (UUID)
2. **Server accepts** it (v1 API doesn't validate `_id` format on create)
3. **Later operations** (GET, PUT, DELETE) call `new ObjectId(id)` which throws for UUIDs
4. **Result**: Records become orphaned, sync loops, duplicate uploads

### Error Example

```
CastError: Cast to ObjectId failed for value "550e8400-e29b-41d4-a716-446655440000" 
at path "_id" for model "Treatment"
```

---

## Apps That Send Client `_id` on POST

### Affected ✅

| App | Collection | Source File | Pattern |
|-----|------------|-------------|---------|
| **Loop (Overrides)** | treatments | `NightscoutServiceKit/Extensions/OverrideTreament.swift:59` | `id: override.syncIdentifier.uuidString` |
| **Trio (Entries)** | entries | `Trio/Sources/APS/DeviceDataManager.swift:335` | `_id: sample.syncIdentifier` |
| **Trio (Entries)** | entries | `Trio/Sources/APS/Storage/GlucoseStorage.swift:415` | `_id: result.id?.uuidString ?? UUID().uuidString` |

### Not Affected ❌

| App | Collection | Pattern | Why Safe |
|-----|------------|---------|----------|
| **Loop (Carbs)** | treatments | `syncIdentifier` as separate field | `_id` from ObjectIdCache or nil |
| **Loop (Doses)** | treatments | `syncIdentifier` as separate field | Intentionally omits `_id` on POST |
| **Loop (Entries)** | entries | Server-assigned | No client `_id` |
| **Trio (Treatments)** | treatments | `id` field (not `_id`) | Uses `NightscoutTreatment.id`, server assigns `_id` |
| **AAPS** | treatments | `identifier: null` on create | Server assigns ObjectId |
| **AAPS** | entries | `identifier: null` on create | Server assigns ObjectId |
| **xDrip+** | treatments | `uuid` field (not `_id`) | Server assigns `_id` |

> **Note**: Trio does not upload override treatments to Nightscout (unlike Loop). Trio's override handling is local only.

---

## Code Evidence

### Loop Override (PROBLEM)

```swift
// externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/Extensions/OverrideTreament.swift:59
self.init(startDate: override.startDate, 
          enteredBy: enteredBy, 
          reason: reason, 
          duration: duration, 
          correctionRange: nsTargetRange, 
          insulinNeedsScaleFactor: override.settings.insulinNeedsScaleFactor, 
          remoteAddress: remoteAddress, 
          id: override.syncIdentifier.uuidString)  // ← UUID as _id
```

### Trio Entries - Path 1 (PROBLEM)

```swift
// externals/Trio/Trio/Sources/APS/DeviceDataManager.swift:332-346
let results = glucose.enumerated().map { index, sample -> BloodGlucose in
    let value = Int(sample.quantity.doubleValue(for: .milligramsPerDeciliter))
    return BloodGlucose(
        _id: sample.syncIdentifier,  // ← UUID as _id
        sgv: value,
        direction: directions[index],
        date: Decimal(Int(sample.date.timeIntervalSince1970 * 1000)),
        dateString: sample.date,
        ...
    )
}
```

### Trio Entries - Path 2 (PROBLEM)

```swift
// externals/Trio/Trio/Sources/APS/Storage/GlucoseStorage.swift:413-426
return fetchedResults.map { result in
    BloodGlucose(
        _id: result.id?.uuidString ?? UUID().uuidString,  // ← UUID as _id
        sgv: Int(result.glucose),
        direction: BloodGlucose.Direction(from: result.direction ?? ""),
        date: Decimal(result.date?.timeIntervalSince1970 ?? Date().timeIntervalSince1970) * 1000,
        dateString: result.date ?? Date(),
        ...
    )
}
```

### Loop Carbs (CORRECT PATTERN)

```swift
// externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/Extensions/SyncCarbObject.swift:16-28
func carbCorrectionNightscoutTreatment(withObjectId objectId: String? = nil) -> CarbCorrectionNightscoutTreatment? {
    return CarbCorrectionNightscoutTreatment(
        timestamp: startDate,
        enteredBy: "loop://\(UIDevice.current.name)",
        id: objectId,                    // ObjectId from cache, or nil
        carbs: lround(grams),
        absorptionTime: absorptionTime,
        foodType: foodType,
        syncIdentifier: syncIdentifier,  // UUID as separate field ✓
        ...
    )
}
```

### Loop Doses (CORRECT PATTERN)

```swift
// externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/Extensions/DoseEntry.swift:30
/* id: objectId, */ /// Specifying _id only works when doing a put (modify);
                    /// all dose uploads are currently posting so they can be either create or update
syncIdentifier: syncIdentifier,  // UUID as separate field ✓
```

### Trio Treatments (CORRECT PATTERN)

```swift
// externals/Trio/Trio/Sources/Models/NightscoutTreatment.swift:24,62
var id: String?  // Uses "id" field, NOT "_id"

private enum CodingKeys: String, CodingKey {
    ...
    case id  // Encodes as "id", not "_id" ✓
}
```

### AAPS (CORRECT PATTERN)

```kotlin
// externals/AndroidAPS/plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/BolusExtension.kt:33
fun BS.toNSBolus(): NSBolus =
    NSBolus(
        ...
        identifier = ids.nightscoutId,  // null on create, server ObjectId on update ✓
        ...
    )
```

### xDrip+ (CORRECT PATTERN)

```java
// externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/models/Treatments.java:96-97
@Column(name = "uuid", unique = true, onUniqueConflicts = Column.ConflictAction.IGNORE)
public String uuid;  // UUID stored in separate field, not _id ✓
```

---

## Collections Affected

| Collection | UUID `_id` Issue? | Source App | Server Fix Status |
|------------|-------------------|------------|-------------------|
| **treatments** | ✅ YES | Loop overrides | ✅ PR #8447 (`lib/server/treatments.js`) |
| **entries** | ✅ YES | Trio CGM entries | ❌ Not yet (`lib/server/entries.js` needs fix) |
| **devicestatus** | ❌ No | N/A | Server assigns `_id` |
| **profile** | ❌ No | N/A | Server assigns `_id` |

> **Key Finding**: Trio does NOT upload override treatments to Nightscout. The `treatments` fix in PR #8447 only affects **Loop overrides**. Trio's CGM **entries** remain affected until `entries.js` is patched.

---

## Solution: Option G (REQ-SYNC-072)

### Transparent UUID Promotion

On POST, if client sends non-ObjectId `_id`:
1. **Move** UUID to `identifier` field (preserves client reference)
2. **Generate** server ObjectId for `_id` (clean MongoDB)
3. **Return** both in response (client can use either)

```
Input:  { "_id": "550e8400-e29b-41d4-a716-446655440000", "eventType": "Temporary Override" }
Output: { "_id": "507f1f77bcf86cd799439011", "identifier": "550e8400-e29b-41d4-a716-446655440000", ... }
```

### Implementation

```javascript
// lib/server/treatments.js - normalizeTreatmentId()
function normalizeTreatmentId (obj) {
  // Extract client sync identity from ANY source
  var clientIdentifier = obj.identifier 
    || obj.syncIdentifier                    // Loop carbs/doses
    || obj.uuid                              // xDrip+
    || (typeof obj._id === 'string' && !OBJECT_ID_HEX_RE.test(obj._id) ? obj._id : null);  // UUID _id (Loop overrides)
  
  if (clientIdentifier && !obj.identifier) {
    obj.identifier = clientIdentifier;
  }
  
  // Convert valid ObjectId strings to ObjectId objects
  if (obj._id && typeof obj._id === 'string' && OBJECT_ID_HEX_RE.test(obj._id)) {
    obj._id = new ObjectID(obj._id);
  }
  // Non-ObjectId _id will be stripped in upsertQueryFor when identifier is present
}
```

### Lookup Changes

```javascript
// upsertQueryFor() - check identifier first
function upsertQueryFor (obj, results) {
  // 1. Prefer identifier for dedup (handles Loop re-uploads after cache clear)
  if (obj.identifier) {
    delete obj._id;  // Let MongoDB handle _id
    return { identifier: obj.identifier };
  }
  // 2. Fall back to _id if present and valid
  if (obj._id) {
    return { _id: obj._id };
  }
  // 3. Last resort: time + eventType
  return { created_at: results.created_at, eventType: obj.eventType };
}
```

---

## Test Validation

### Swift Tests (Loop Patterns) - 7/7 ✅

| Test | Validates |
|------|-----------|
| `testPostOverrideWithUUID` | UUID `_id` → `identifier` promotion |
| `testReuploadOverrideDeduplicates` | Same UUID = upsert, no duplicate |
| `testDeleteOverrideByObjectId` | Delete using server ObjectId |
| `testBatchUploadWithUUIDs` | Array upload preserves order |
| `testObjectIdCacheWorkflow` | syncIdentifier → ObjectId caching |

### Kotlin Tests (AAPS Patterns) - 13/13 ✅

| Test | Validates |
|------|-----------|
| `testPostBolusWithIdentifier` | `identifier` field preserved |
| `testReuploadBolusDeduplicates` | Same identifier = upsert |
| `testBatchUploadWithIdentifiers` | Array upload order preserved |

**Full results**: [`docs/reports/option-g-test-validation-report.md`](../reports/option-g-test-validation-report.md)

---

## Why This Pattern Exists

### Loop Override vs Other Treatments

Loop's override upload was added later (2022-02-28) and took a shortcut:

| Treatment Type | Upload Pattern | Reason |
|----------------|----------------|--------|
| Carbs/Doses | `syncIdentifier` + ObjectIdCache | Original design, server assigns `_id` |
| **Overrides** | `_id = syncIdentifier` | Simpler, no cache needed, direct UUID |

The dose code even has a comment explaining why `_id` is omitted:
```swift
/* id: objectId, */ /// Specifying _id only works when doing a put (modify);
                    /// all dose uploads are currently posting so they can be either create or update
```

### Trio Entries

Trio's `BloodGlucose` struct defaults `_id` to `UUID().uuidString` for local identification. This UUID gets sent to Nightscout on upload via two code paths:

1. **DeviceDataManager.swift:335** - Uses `sample.syncIdentifier` as `_id`
2. **GlucoseStorage.swift:415** - Uses `result.id?.uuidString ?? UUID().uuidString` as `_id`

Both paths POST to `/api/v1/entries.json`, which does not yet have the identifier promotion fix.

---

## Remaining Work

| Task | Status | Notes |
|------|--------|-------|
| Treatments fix (PR #8447) | ✅ Ready to merge | Option G implemented, tests pass |
| Entries fix | ❌ Not started | Same pattern needed in `lib/server/entries.js` for Trio CGM |
| v3 API alignment | ❌ Not started | v3 API may need similar promotion |
| Trio client fix | Optional | Could change upload to use `identifier` field instead of `_id` |

### Entries Fix Details

The `lib/server/entries.js` file needs the same `normalizeEntryId()` function pattern:

```javascript
function normalizeEntryId (obj) {
  var clientIdentifier = obj.identifier 
    || (typeof obj._id === 'string' && !OBJECT_ID_HEX_RE.test(obj._id) ? obj._id : null);
  
  if (clientIdentifier && !obj.identifier) {
    obj.identifier = clientIdentifier;
  }
  
  if (obj._id && typeof obj._id === 'string' && OBJECT_ID_HEX_RE.test(obj._id)) {
    obj._id = new ObjectID(obj._id);
  }
}
```

---

## References

- **Issue**: [nightscout/cgm-remote-monitor#8450](https://github.com/nightscout/cgm-remote-monitor/issues/8450)
- **Fix PR**: [nightscout/cgm-remote-monitor#8447](https://github.com/nightscout/cgm-remote-monitor/pull/8447)
- **Requirement**: [REQ-SYNC-072](../../traceability/sync-identity-requirements.md#req-sync-072)
- **Gap**: [GAP-TREAT-012](../../traceability/treatments-gaps.md#gap-treat-012)
- **Test Report**: [option-g-test-validation-report.md](../reports/option-g-test-validation-report.md)

---

## Change Log

| Date | Change |
|------|--------|
| 2026-03-11 | **Major revision**: Verified all affected apps against source code; corrected Trio (does NOT upload overrides); added two Trio entry upload paths (DeviceDataManager.swift:335, GlucoseStorage.swift:415); expanded Code Evidence with all verified patterns; added entries.js fix template |
| 2026-03-11 | Verified all code references against source; fixed issue #8450 date (was 2026-02-17, corrected to 2026-03-08); updated implementation snippets to match actual PR #8447 code |
| 2026-03-11 | Created document, consolidated from GAP-TREAT-012 and session findings |
| 2026-03-10 | Discovered Trio entries also affected |
| 2026-03-10 | Option G tests validated (Swift 7/7, Kotlin 13/13) |
