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
| **2022-02-16** | MongoDB driver v4 upgrade ([commit 0e61bebb](https://github.com/nightscout/cgm-remote-monitor/commit/0e61bebb)) | Stricter ObjectId validation begins |
| **2022-02-28** | Loop override upload added ([commit 3dedcf7](https://github.com/LoopKit/NightscoutService/commit/3dedcf7)) | `_id: syncIdentifier.uuidString` pattern introduced |
| **2023-06-01** | MongoDB v5+ compatibility fix ([commit 32163a0c](https://github.com/nightscout/cgm-remote-monitor/commit/32163a0c)) | `new ObjectId(id)` pattern solidified |
| **2025-04-29** | Trio BloodGlucose uses UUID _id ([commit 99a351e2](https://github.com/nightscout/Trio/commit/99a351e2)) | CGM entries now affected |
| **2026-02-17** | Issue #8450 reported | Override sync breaking in production |
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

| App | Collection | Code | Pattern |
|-----|------------|------|---------|
| **Loop (Overrides)** | treatments | `OverrideTreament.swift:59` | `id: override.syncIdentifier.uuidString` |
| **Trio (Overrides)** | treatments | Inherits Loop | Same as Loop |
| **Trio (Entries)** | entries | `BloodGlucose.swift:105` | `_id: String = UUID().uuidString` |

### Not Affected ❌

| App | Collection | Pattern | Why Safe |
|-----|------------|---------|----------|
| **Loop (Carbs)** | treatments | `syncIdentifier` as separate field | `_id` from ObjectIdCache or nil |
| **Loop (Doses)** | treatments | `syncIdentifier` as separate field | Intentionally omits `_id` on POST |
| **Loop (Entries)** | entries | Server-assigned | No client `_id` |
| **AAPS** | treatments | `identifier: null` on create | Server assigns ObjectId |
| **AAPS** | entries | Server-assigned | No client `_id` |
| **xDrip+** | treatments | `uuid` field (not `_id`) | Server assigns `_id` |

---

## Code Evidence

### Loop Override (PROBLEM)

```swift
// LoopKit/NightscoutService/NightscoutServiceKit/Extensions/OverrideTreament.swift:59
self.init(startDate: override.startDate, 
          enteredBy: enteredBy, 
          reason: reason, 
          duration: duration, 
          correctionRange: nsTargetRange, 
          insulinNeedsScaleFactor: override.settings.insulinNeedsScaleFactor, 
          remoteAddress: remoteAddress, 
          id: override.syncIdentifier.uuidString)  // ← UUID as _id
```

### Loop Carbs (CORRECT PATTERN)

```swift
// LoopKit/LoopKit/SyncCarbObject.swift:25
CarbCorrectionNightscoutTreatment(
    id: objectIdCache.findObjectIdBySyncIdentifier(syncIdentifier),  // ObjectId or nil
    syncIdentifier: syncIdentifier,  // UUID as separate field
    ...
)
```

### Trio Entries (PROBLEM)

```swift
// Trio/Sources/Models/BloodGlucose.swift:105
init(
    _id: String = UUID().uuidString,  // ← UUID as default _id
    sgv: Int? = nil,
    direction: Direction? = nil,
    ...
)
```

### AAPS (CORRECT PATTERN)

```kotlin
// AAPS/plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/NSBolus.kt
NSTreatment(
    identifier = ids.nightscoutId,  // null on create, server ObjectId on update
    ...
)
```

---

## Collections Affected

| Collection | UUID `_id` Issue? | Source App | Server Fix Status |
|------------|-------------------|------------|-------------------|
| **treatments** | ✅ YES | Loop/Trio overrides | ✅ PR #8447 |
| **entries** | ✅ YES | Trio CGM entries | ❌ Not yet |
| **devicestatus** | ❌ No | N/A | Server assigns `_id` |
| **profile** | ❌ No | N/A | Server assigns `_id` |

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
function normalizeTreatmentId(obj) {
  if (obj._id && typeof obj._id === 'string') {
    if (OBJECT_ID_HEX_RE.test(obj._id)) {
      // Valid 24-hex ObjectId string → convert to ObjectId
      obj._id = new ObjectId(obj._id);
    } else {
      // UUID or other string → promote to identifier, generate ObjectId
      obj.identifier = obj.identifier || obj._id;
      obj._id = new ObjectId();
    }
  }
}
```

### Lookup Changes

```javascript
// upsertQueryFor() - check identifier first
function upsertQueryFor(obj) {
  if (obj.identifier) {
    return { identifier: obj.identifier };
  }
  if (obj._id) {
    return { _id: obj._id };
  }
  // Legacy fallback
  return { created_at: obj.created_at, eventType: obj.eventType };
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

Trio's `BloodGlucose` struct defaults `_id` to `UUID().uuidString` for local identification, but this gets sent to Nightscout on upload, causing the same issue.

---

## Remaining Work

| Task | Status | Notes |
|------|--------|-------|
| Treatments fix (PR #8447) | ✅ Ready to merge | Option G implemented, tests pass |
| Entries fix | ❌ Not started | Same pattern needed in `lib/server/entries.js` |
| v3 API alignment | ❌ Not started | v3 API may need similar promotion |
| Trio client fix | Optional | Could change `BloodGlucose._id` default |

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
| 2026-03-11 | Created document, consolidated from GAP-TREAT-012 and session findings |
| 2026-03-10 | Discovered Trio entries also affected |
| 2026-03-10 | Option G tests validated (Swift 7/7, Kotlin 13/13) |
