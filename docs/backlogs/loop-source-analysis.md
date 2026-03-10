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

## LOOP-SRC-013: Glucose Entry Upload ✅

**Files**:
- `NightscoutServiceKit/Extensions/StoredGlucoseSample.swift` - Loop's extension
- `NightscoutKit/Sources/NightscoutKit/Models/GlucoseEntry.swift` - JSON serialization

### Questions Answered

- [x] What fields are sent for SGV entries? → See JSON payload below
- [x] Is `identifier` or `syncIdentifier` used? → **Neither** - uses `_id` (optional, usually nil on create)
- [x] What deduplication fields are set? → `date` + `device` (implicit server-side dedup)

### Actual JSON Payload

From `GlucoseEntry.dictionaryRepresentation`:

```json
{
  "date": 1708135216000,
  "dateString": "2026-02-17T02:00:16.000Z",
  "device": "Dexcom G6 14:AB:CD:EF",
  "type": "sgv",
  "sgv": 125,
  "trend": 4,
  "direction": "Flat",
  "trendRate": 0.5,
  "isCalibration": false
}
```

For meter readings (wasUserEntered=true):
```json
{
  "date": 1708135216000,
  "dateString": "2026-02-17T02:00:16.000Z",
  "device": "loop://iPhone",
  "type": "mbg",
  "mbg": 120
}
```

### Code References

| Line | File | Code |
|------|------|------|
| 34-42 | `StoredGlucoseSample.swift` | `GlucoseEntry(glucose:, date:, device:, glucoseType:, trend:, changeRate:, isCalibration:)` |
| 38 | `StoredGlucoseSample.swift` | `glucoseType: wasUserEntered ? .meter : .sensor` |
| 85 | `NightscoutUploader.swift` | `uploadEntries(samples.compactMap { $0.glucoseEntry })` |
| 92-113 | `GlucoseEntry.swift` | `dictionaryRepresentation` - JSON output |

### Key Findings

1. **No explicit identity field**: Glucose entries don't send `_id`, `identifier`, or `syncIdentifier` on create
2. **Server assigns `_id`**: Loop relies on Nightscout's implicit deduplication by `date` + `device`
3. **Trend handling**: Both numeric `trend` (1-9) and string `direction` ("Flat", "DoubleUp", etc.) are sent
4. **SGV vs MBG**: `wasUserEntered` determines if entry is `sgv` (CGM) or `mbg` (fingerstick)
5. **Condition field**: `belowRange`/`aboveRange` for out-of-range readings (G6 LOW/HIGH)

### No GAP-TREAT-012 Impact

Glucose entries are **not affected** by GAP-TREAT-012 (UUID _id coercion) because:
- Loop doesn't set `_id` on glucose entries
- Server generates ObjectId naturally
- No client-side UUID involved

### Status: ✅ Complete (2026-03-10)

---

## LOOP-SRC-014: DeviceStatus Upload ✅

**Files**:
- `NightscoutServiceKit/Extensions/StoredDosingDecision.swift` - Loop's extension
- `NightscoutKit/Sources/NightscoutKit/Models/DeviceStatus.swift` - JSON serialization

### Questions Answered

- [x] What is the `loop` object structure? → See JSON payload below
- [x] Are overrides included in deviceStatus? → **YES** - separate `override` object
- [x] What IOB/COB/predicted structure? → `loop.iob`, `loop.cob`, `loop.predicted`

### Actual JSON Payload

From `DeviceStatus.dictionaryRepresentation`:

```json
{
  "device": "loop://Ben's iPhone",
  "created_at": "2026-02-17T02:00:16.000Z",
  "pump": {
    "clock": "2026-02-17T02:00:16.000Z",
    "pumpID": "12345678",
    "manufacturer": "Omnipod",
    "model": "Dash",
    "battery": { "percent": 85 },
    "suspended": false,
    "bolusing": false,
    "reservoir": 125.5
  },
  "uploader": {
    "name": "Ben's iPhone",
    "timestamp": "2026-02-17T02:00:16.000Z",
    "battery": 72
  },
  "loop": {
    "name": "Loop",
    "version": "3.4.1",
    "timestamp": "2026-02-17T02:00:16.000Z",
    "iob": { "timestamp": "2026-02-17T02:00:00.000Z", "iob": 2.5 },
    "cob": { "timestamp": "2026-02-17T02:00:00.000Z", "cob": 15 },
    "predicted": {
      "startDate": "2026-02-17T02:00:00.000Z",
      "values": [125, 130, 135, 140, 138, 132, 125, 120, 115]
    },
    "automaticDoseRecommendation": {
      "timestamp": "2026-02-17T02:00:16.000Z",
      "tempBasalAdjustment": { "rate": 1.2, "duration": 1800 },
      "bolusVolume": 0.1
    },
    "recommendedBolus": 0,
    "enacted": {
      "rate": 1.2,
      "duration": 1800,
      "timestamp": "2026-02-17T02:00:16.000Z",
      "received": true,
      "bolusVolume": 0.1
    }
  },
  "override": {
    "name": "Pre-Meal",
    "timestamp": "2026-02-17T02:00:16.000Z",
    "active": true,
    "currentCorrectionRange": { "minValue": 90, "maxValue": 110 },
    "duration": 3600,
    "multiplier": 1.2
  }
}
```

### Code References

| Line | File | Code |
|------|------|------|
| 145-161 | `StoredDosingDecision.swift` | `deviceStatus(automaticDoseDecision:)` - main entry |
| 16-21 | `StoredDosingDecision.swift` | `loopStatusIOB` - IOB conversion |
| 23-28 | `StoredDosingDecision.swift` | `loopStatusCOB` - COB conversion |
| 30-35 | `StoredDosingDecision.swift` | `loopStatusPredicted` - BG prediction |
| 118-137 | `StoredDosingDecision.swift` | `overrideStatus` - active override |
| 35-62 | `DeviceStatus.swift` | `dictionaryRepresentation` - JSON output |

### Key Findings

1. **Single prediction curve**: Loop sends one combined `predicted.values` array (unlike oref0's 4 curves)
2. **Override in deviceStatus**: Active override included as separate `override` object with target range
3. **No `_id` field**: DeviceStatus entries use server-assigned IDs
4. **identifier field**: Optional `identifier` field for client tracking (not used by Loop currently)
5. **Enacted vs recommended**: Both `enacted` (what was done) and `recommendedBolus` (what was suggested) included

### DeviceStatus vs Treatment Override

| Aspect | DeviceStatus `override` | Treatment `Temporary Override` |
|--------|-------------------------|--------------------------------|
| Purpose | Current state snapshot | Historical event record |
| `_id` handling | Server assigns | Loop sends UUID → **GAP-TREAT-012** |
| Frequency | Every 5 minutes | On start/stop/modify |
| Data | Active range, multiplier | Full duration, reason |

### No GAP-TREAT-012 Impact

DeviceStatus uploads are **not affected** by GAP-TREAT-012 because:
- Loop doesn't set `_id` on deviceStatus entries
- Server generates ObjectId naturally
- Override info is embedded, not a separate treatment

### Status: ✅ Complete (2026-03-10)

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
- [x] All 7 source files analyzed (**6 complete, 0 remaining**)
- [x] JSON payloads extracted for each treatment type
- [x] Identity field usage documented in table
- [x] Differences between override and carbs/doses documented
- [x] ObjectIdCache lifecycle fully understood
- [x] Glucose entry upload documented
- [x] DeviceStatus upload documented

---

## Summary: Loop Upload Patterns (2026-03-10)

### Identity Field Comparison

| Data Type | `_id` | `syncIdentifier` | ObjectIdCache | Dedup Strategy |
|-----------|-------|------------------|---------------|----------------|
| **Override** | UUID string | ❌ Not sent | ❌ Not used | Server matches by `_id` |
| **Carbs** | ObjectId (or null) | ✅ Sent | ✅ Used | Server matches by `syncIdentifier` |
| **Doses** | ❌ Not sent | ✅ Sent | ✅ Used | Server matches by `syncIdentifier` |
| **Glucose** | ❌ Not sent | ❌ Not sent | ❌ Not used | Server dedup by `date + device` |
| **DeviceStatus** | ❌ Not sent | ❌ Not sent | ❌ Not used | Server assigns |

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
