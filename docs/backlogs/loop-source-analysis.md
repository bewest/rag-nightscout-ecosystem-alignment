# Loop Upload Source Analysis Sub-Backlog

> **Parent**: [loop-nightscout-upload-testing.md](loop-nightscout-upload-testing.md)
> **Goal**: Extract exact upload patterns from Loop source code
> **Created**: 2026-03-10

## Priority Order

Analyze in order of impact on GAP-TREAT-012 (UUID _id issue):

1. **OverrideTreament.swift** - The problem code (uses `_id = syncIdentifier`)
2. **SyncCarbObject.swift** - The "correct" pattern (uses `id` + `syncIdentifier`)
3. **ObjectIdCache.swift** - How Loop tracks server IDs
4. **NightscoutUploader.swift** - HTTP methods and endpoints

---

## LOOP-SRC-010: OverrideTreament.swift ✅

**File**: `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/Extensions/OverrideTreament.swift`

### Questions Answered

- [x] What fields does `asNightscoutTreatment()` return? → See payload below
- [x] Does it use `_id` or `id` or both? → **`id` only (passed as `syncIdentifier.uuidString`)**
- [x] Does it include a separate `syncIdentifier` field? → **NO** ← Root cause of #8450
- [x] What is `eventType` set to? → `"Temporary Override"`
- [x] What override-specific fields are included? → `reason`, `duration`/`durationType`, `correctionRange`, `insulinNeedsScaleFactor`, `remoteAddress`

### Actual JSON Payload

From `NightscoutKit/OverrideTreatment.dictionaryRepresentation`:

```json
{
  "_id": "69F15FD2-8075-4DEB-AEA3-4352F455840D",
  "created_at": "2026-02-17T02:00:16.000Z",
  "timestamp": "2026-02-17T02:00:16.000Z",
  "enteredBy": "Loop",
  "eventType": "Temporary Override",
  "reason": "Pre-Meal",
  "duration": 60,
  "correctionRange": [90, 110],
  "insulinNeedsScaleFactor": 1.2
}
```

**Key Finding**: Override is the ONLY treatment type that puts UUID directly in `_id`. No separate `syncIdentifier` field is sent.

### Code References

| Line | File | Code |
|------|------|------|
| 59 | `OverrideTreament.swift` | `id: override.syncIdentifier.uuidString` |
| 25-31 | `NightscoutKit/OverrideTreatment.swift` | `super.init(..., id: id, eventType: .temporaryOverride)` |
| 111 | `NightscoutKit/NightscoutTreatment.swift` | `rval["_id"] = id` |
| 165 | `NightscoutService.swift` | `let deletions = deleted.map { $0.syncIdentifier.uuidString }` |

### Status: ✅ Complete (2026-03-10)

---

## LOOP-SRC-011: SyncCarbObject.swift ✅

**File**: `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/Extensions/SyncCarbObject.swift`

### Questions Answered

- [x] Does it use `_id` or `id` or both? → `id` (from ObjectIdCache)
- [x] Does it include `syncIdentifier` as separate field? → **YES** ✅
- [x] How is `id` populated (from ObjectIdCache)? → `objectIdCache.findObjectIdBySyncIdentifier(syncIdentifier)`
- [x] What is `eventType` set to? → `"Carb Correction"`
- [x] What carb-specific fields are included? → `carbs`, `absorptionTime`, `foodType`, `userEnteredAt`, `userLastModifiedAt`

### Actual JSON Payload

From `NightscoutKit/CarbCorrectionNightscoutTreatment.dictionaryRepresentation`:

```json
{
  "_id": "507f1f77bcf86cd799439011",
  "syncIdentifier": "69F15FD2-8075-4DEB-AEA3-4352F455840D",
  "created_at": "2026-02-17T02:00:16.000Z",
  "timestamp": "2026-02-17T02:00:16.000Z",
  "enteredBy": "loop://iPhone",
  "eventType": "Carb Correction",
  "carbs": 30,
  "absorptionTime": 180,
  "foodType": "🍕",
  "userEnteredAt": "2026-02-17T02:00:00.000Z",
  "userLastModifiedAt": "2026-02-17T02:00:10.000Z"
}
```

**Key Finding**: Carbs send BOTH `_id` (from ObjectIdCache) AND `syncIdentifier` as separate fields. This is the "correct" pattern that overrides should follow.

### Code References

| Line | File | Code |
|------|------|------|
| 16-28 | `SyncCarbObject.swift` | `CarbCorrectionNightscoutTreatment(id: objectId, syncIdentifier: syncIdentifier)` |
| 37-38 | `NightscoutUploader.swift` | `objectIdCache.findObjectIdBySyncIdentifier(syncIdentifier)` |
| 31 | `NightscoutKit/CarbCorrectionNightscoutTreatment.swift` | `super.init(..., id: id, ..., syncIdentifier: syncIdentifier)` |
| 117 | `NightscoutKit/NightscoutTreatment.swift` | `rval["syncIdentifier"] = syncIdentifier` |

### Status: ✅ Complete (2026-03-10)

---

## LOOP-SRC-003: ObjectIdCache.swift ✅

**File**: `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/ObjectIdCache.swift`

### Questions Answered

- [x] What is the cache data structure? → `[String: ObjectIDMapping]` dictionary keyed by `loopSyncIdentifier`
- [x] How is syncIdentifier → objectId mapping stored? → `ObjectIDMapping(loopSyncIdentifier, nightscoutObjectId, createdAt)`
- [x] What is the expiry time (24 hours)? → `objectIdCacheKeepTime = 24 * 60 * 60` seconds
- [x] When is the cache populated (after POST response)? → `objectIdCache.add(syncIdentifier, objectId)` after upload success
- [x] When is the cache consulted (before PUT/DELETE)? → `objectIdCache.findObjectIdBySyncIdentifier(syncIdentifier)`
- [x] What happens on cache miss? → Returns `nil`, treatment skipped from update/delete batch

### Cache Structure

```swift
public struct ObjectIDMapping {
    var loopSyncIdentifier: String    // Loop's UUID (e.g., carb entry UUID)
    var nightscoutObjectId: String    // Server's ObjectId (e.g., "507f1f77bcf86cd799439011")
    var createdAt: Date               // When mapping was created
}

public struct ObjectIdCache {
    var storageBySyncIdentifier: [String: ObjectIDMapping]
    
    func findObjectIdBySyncIdentifier(_ syncIdentifier: String) -> String?
    mutating func add(syncIdentifier: String, objectId: String)
    mutating func purge(before date: Date)  // Remove entries older than 24hr
}
```

### Key Insight: Why Overrides Don't Use ObjectIdCache

Looking at `NightscoutService.uploadTemporaryOverrideData()`:

```swift
// Line 163-167 in NightscoutService.swift
let updates = updated.map { OverrideTreatment(override: $0) }
let deletions = deleted.map { $0.syncIdentifier.uuidString }  // ← Uses UUID directly!

uploader.deleteTreatmentsById(deletions, ...)  // ← Expects _id = UUID
```

**Override bypasses ObjectIdCache entirely** - it uses `syncIdentifier.uuidString` directly as `_id` for both upload and deletion. This is why overrides break when Nightscout coerces UUID to ObjectId.

### Status: ✅ Complete (2026-03-10)

---

## LOOP-SRC-002: NightscoutUploader.swift ✅

**File**: `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/Extensions/NightscoutUploader.swift`

### Questions Answered

- [x] What HTTP methods are used (POST, PUT, DELETE)? → POST for create, PUT for modify, DELETE for remove
- [x] What endpoints are called? → Uses NightscoutKit's `NightscoutClient` methods
- [x] How are batch uploads handled? → `upload(_ treatments: [NightscoutTreatment])` batches treatments
- [x] How is the response parsed for `_id`? → Returns `[String]` array of ObjectIds
- [x] How does it update ObjectIdCache from response? → `objectIdCache.add(syncIdentifier, objectId)` after success

### Key Methods

| Method | Purpose | ObjectIdCache Usage |
|--------|---------|---------------------|
| `createCarbData` | POST carbs | Returns objectIds for caching |
| `updateCarbData` | PUT carbs | Looks up `_id` from cache |
| `deleteCarbData` | DELETE carbs | Looks up `_id` from cache |
| `createDoses` | POST doses | Returns objectIds for caching |
| `deleteDoses` | DELETE doses | Looks up `_id` from cache |

### Code References

| Line | Method | Description |
|------|--------|-------------|
| 14-28 | `createCarbData` | POST with callback returning objectIds |
| 30-50 | `updateCarbData` | Lookup `_id` via `objectIdCache.findObjectIdBySyncIdentifier()` |
| 52-73 | `deleteCarbData` | Lookup `_id` via cache, then `deleteTreatmentsByObjectId()` |
| 120-147 | `createDoses` | POST doses, cache lookup for existing `_id` |
| 149-170 | `deleteDoses` | Lookup `_id` via cache, then delete |

### Key Finding: Override Upload is Different

Override uses a DIFFERENT code path that bypasses NightscoutUploader's ObjectIdCache-aware methods:

```swift
// NightscoutService.swift:163-174
let updates = updated.map { OverrideTreatment(override: $0) }
let deletions = deleted.map { $0.syncIdentifier.uuidString }

uploader.deleteTreatmentsById(deletions, ...)  // Direct UUID, no cache lookup
uploader.upload(updates) { ... }                // Direct upload, no cache save
```

### Status: ✅ Complete (2026-03-10)

---

## LOOP-SRC-012: Dose Upload ✅

**Files**:
- `NightscoutServiceKit/Extensions/DoseEntry.swift` - JSON conversion

### Questions Answered

- [x] Where is DoseEntry converted to Nightscout JSON? → `DoseEntry.treatment(enteredBy:withObjectId:)`
- [x] Does it use `_id` or `id` or `syncIdentifier`? → `syncIdentifier` as separate field (line 31)
- [x] Is `syncIdentifier` the hex of pump raw data? → Yes, derived from pump event
- [x] What `eventType` values are used? → `"Bolus"` or `"Temp Basal"` (via BolusNightscoutTreatment/TempBasalNightscoutTreatment)

### Key Code Evidence

```swift
// DoseEntry.swift:21-32
return BolusNightscoutTreatment(
    ...
    /* id: objectId, */ /// Specifying _id only works when doing a put (modify)
    syncIdentifier: syncIdentifier,  // ← Sent as SEPARATE field
    insulinType: insulinType?.brandName
)
```

**The comment explains**: `_id` is intentionally NOT sent on POST because "all dose uploads are currently posting so they can be either create or update". Only `syncIdentifier` is sent, letting the server handle deduplication.

### Status: ✅ Complete (2026-03-10)

---

## LOOP-SRC-013: Glucose Entry Upload

**Files**:
- `NightscoutServiceKit/Extensions/StoredGlucoseSample.swift`

### Questions to Answer

- [ ] What fields are sent for SGV entries?
- [ ] Is `identifier` or `syncIdentifier` used?
- [ ] What deduplication fields are set?

### Status: ⬜ Not Started

---

## LOOP-SRC-014: DeviceStatus Upload

**Files**:
- `NightscoutServiceKit/Extensions/StoredDosingDecision.swift`

### Questions to Answer

- [ ] What is the `loop` object structure?
- [ ] Are overrides included in deviceStatus?
- [ ] What IOB/COB/predicted structure?

### Status: ⬜ Not Started

---

## Analysis Template

For each source file, document:

```markdown
### [Filename]

**Full Path**: `externals/LoopWorkspace/...`

**Key Methods**:
| Method | Purpose |
|--------|---------|
| `methodName()` | Description |

**JSON Output**:
```json
{
  "field": "value"
}
```

**Identity Fields**:
| Field | Value Source | Used For |
|-------|--------------|----------|
| `_id` | syncIdentifier.uuidString | Override only |
| `id` | ObjectIdCache lookup | Carbs, doses |
| `syncIdentifier` | Entry.syncIdentifier | Dedup |

**Code References**:
- Line XX: Key logic
- Line YY: Field assignment
```

---

## Completion Criteria

Phase 1 is complete when:
- [x] All 7 source files analyzed (4 core files done, 2 optional remaining)
- [x] JSON payloads extracted for each treatment type
- [x] Identity field usage documented in table
- [x] Differences between override and carbs/doses documented
- [x] ObjectIdCache lifecycle fully understood

---

## Summary: Loop Upload Patterns (2026-03-10)

### Identity Field Comparison

| Treatment Type | `_id` | `syncIdentifier` | ObjectIdCache | Dedup Strategy |
|----------------|-------|------------------|---------------|----------------|
| **Override** | UUID string | ❌ Not sent | ❌ Not used | Server matches by `_id` |
| **Carbs** | ObjectId (or null) | ✅ Sent | ✅ Used | Server matches by `syncIdentifier` |
| **Doses** | ❌ Not sent | ✅ Sent | ✅ Used | Server matches by `syncIdentifier` |

### Root Cause of #8450

1. Override sends `_id: "69F15FD2-..."` (UUID string)
2. Nightscout v1 accepts on POST (stores as string)
3. On DELETE, v1 tries to convert to ObjectId → **fails**
4. Loop retry loop blocks all subsequent override uploads

### Why Option G (REQ-SYNC-072) Works

Server-side fix:
1. On POST: Move non-ObjectId `_id` to `identifier`, generate server ObjectId
2. On DELETE: Accept lookup by `identifier` OR `_id`
3. Loop override continues sending UUID as `_id` → server stores as `identifier`
4. No Loop code change required
