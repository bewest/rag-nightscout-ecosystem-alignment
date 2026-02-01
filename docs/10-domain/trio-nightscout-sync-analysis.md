# Trio Nightscout Sync Analysis

> **Deep Dive Document** | Created: 2026-01-31
> **Source**: Ready Queue #3 (aid-algorithms.md #6)
> **Files Analyzed**: ~2,336 lines across Nightscout sync components

## Executive Summary

Trio implements a **unidirectional upload-only sync** architecture with Nightscout, fundamentally different from Loop's bidirectional approach. Key findings:

1. **Upload Pipelines**: 7 throttled upload channels (carbs, glucose, pump history, etc.)
2. **Fetch Filtering**: Excludes data from Trio, AndroidAPS, iAPS, Loop via `enteredBy` filter
3. **Identity Tracking**: Local `isUploadedToNS` flag, NO syncIdentifier↔objectId mapping
4. **Profile Sync**: Includes APNS push token and override presets in profile upload
5. **Delete Operations**: Uses `find[id][$eq]` query, relies on local `id` field

## Architecture Comparison

### Trio vs Loop Sync Approaches

| Aspect | Trio | Loop |
|--------|------|------|
| **Sync Direction** | Upload primary, download for remote carbs | Bidirectional create/update/delete |
| **Identity Mapping** | None (local `id` field only) | `ObjectIdCache` maps syncIdentifier↔objectId |
| **Duplicate Prevention** | `isUploadedToNS` flag per entity | syncIdentifier uniqueness |
| **Batch Upload** | Chunks of 100 | Individual or batched |
| **Throttling** | 2-second per-pipeline window | None (on-demand) |
| **API Version** | v1 only | v1 only |
| **Delete Mechanism** | `find[id][$eq]` query | `deleteTreatmentsById` via cached objectId |

### Key Architectural Differences

**Loop**: Maintains `ObjectIdCache` that maps Loop's internal `syncIdentifier` to Nightscout's `_id` (objectId). This enables reliable updates and deletes:

```swift
// Loop: ObjectIdCache.swift
struct ObjectIDMapping {
    var loopSyncIdentifier: String      // Loop's internal ID
    var nightscoutObjectId: String      // Nightscout's _id
    var createdAt: Date
}
```

**Trio**: Does NOT maintain objectId cache. Uses local `id` field (UUID) and sets `isUploadedToNS = true` after upload:

```swift
// Trio: No objectId mapping
// Delete via find query:
components.queryItems = [
    URLQueryItem(name: "find[id][$eq]", value: id)  // Local UUID
]
```

## Trio Sync Components

### File Structure (~2,336 lines)

| File | Lines | Purpose |
|------|-------|---------|
| `NightscoutManager.swift` | 1,451 | Core sync orchestration |
| `NightscoutAPI.swift` | 575 | HTTP operations |
| `NightscoutUploadPipeline.swift` | 42 | Pipeline definitions |
| `BaseNightscoutManager+Subscribers.swift` | 90 | Combine subscribers |
| `NightscoutTreatment.swift` | 65 | Treatment model |
| `NightscoutStatus.swift` | 71 | DeviceStatus model |
| `NightscoutExercise.swift` | 30 | Override model |

### Upload Pipelines

```swift
// NightscoutUploadPipeline.swift:6-14
public enum NightscoutUploadPipeline: String, CaseIterable {
    case carbs
    case pumpHistory
    case overrides
    case tempTargets
    case glucose
    case manualGlucose
    case deviceStatus
}
```

Each pipeline has a **2-second throttle window** to coalesce rapid duplicate requests:

```swift
// NightscoutManager.swift:55-57
let uploadPipelineInterval: [NightscoutUploadPipeline: TimeInterval] = [
    .carbs: 2, .pumpHistory: 2, .overrides: 2, .tempTargets: 2,
    .glucose: 2, .manualGlucose: 2, .deviceStatus: 2
]
```

### API Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/entries/sgv.json` | GET | Fetch glucose |
| `/api/v1/entries.json` | POST | Upload glucose |
| `/api/v1/treatments.json` | GET/POST/DELETE | Treatments CRUD |
| `/api/v1/devicestatus.json` | POST | Upload loop status |
| `/api/v1/profile.json` | GET/POST | Profile import/export |

## Sync Identity Analysis

### Fetch Filtering (Deduplication)

Trio excludes treatments created by itself and other AID apps:

```swift
// NightscoutAPI.swift:23-29
private let excludedEnteredBy: [String] = [
    NightscoutTreatment.local,   // "Trio"
    "AndroidAPS",
    "openaps://AndroidAPS",
    "iAPS",
    "loop://iPhone"
]
```

Query construction:
```swift
// NightscoutAPI.swift:109-115
func makeNeQueryItems() -> [URLQueryItem] {
    excludedEnteredBy.enumerated().map { idx, value in
        URLQueryItem(
            name: "find[$and][\(idx)][enteredBy][$ne]",
            value: value
        )
    }
}
```

### Upload Tracking

Each Core Data entity has `isUploadedToNS` boolean:

```swift
// Various storage classes
newItem.isUploadedToNS = false  // Initial state
// After successful upload:
result.isUploadedToNS = true
```

### Delete Operations

Trio uses local `id` field for deletions:

```swift
// NightscoutAPI.swift:169-171
components.queryItems = [
    URLQueryItem(name: "find[id][$eq]", value: id)
]
request.httpMethod = "DELETE"
```

**GAP**: This relies on Nightscout storing the local `id` field and making it queryable. If Nightscout assigns a different `_id` and the local `id` isn't indexed, deletes may fail silently.

## Treatment Sync Details

### NightscoutTreatment Model

```swift
// NightscoutTreatment.swift
struct NightscoutTreatment: JSON, Hashable, Equatable {
    var duration: Int?
    var rawDuration: PumpHistoryEvent?
    var rawRate: PumpHistoryEvent?
    var absolute: Decimal?
    var rate: Decimal?
    var eventType: PumpEventStored.EventType
    var createdAt: Date?
    var enteredBy: String?
    var bolus: PumpHistoryEvent?
    var insulin: Decimal?
    var notes: String?
    var carbs: Decimal?
    var fat: Decimal?
    var protein: Decimal?
    var foodType: String?
    let targetTop: Decimal?
    let targetBottom: Decimal?
    var glucoseType: String?
    var glucose: String?
    var units: String?
    var id: String?       // Local UUID used for sync identity
    var fpuID: String?
    
    static let local = "Trio"
}
```

### Override Sync Special Handling

Overrides require delete-then-reupload when duration changes:

```swift
// NightscoutManager.swift:1057-1063
try await overridesStorage.checkIfShouldDeleteNightscoutOverrideEntry(
    forCreatedAt: createdAtString,
    newDuration: override.duration,
    using: nightscout
)
```

This is because Nightscout doesn't re-render chart elements when only duration changes.

## DeviceStatus Upload

### NightscoutStatus Structure

```swift
// NightscoutStatus.swift
struct NightscoutStatus: JSON {
    let device: String           // "Trio"
    let openaps: OpenAPSStatus   // Algorithm state
    let pump: NSPumpStatus       // Pump metrics
    let uploader: Uploader       // Phone battery
}

struct OpenAPSStatus: JSON {
    let iob: IOBEntry?
    let suggested: Determination?
    let enacted: Determination?
    let version: String
    let recommendedBolus: Decimal?
}
```

### mmol/L Conversion

Trio converts glucose values in reason string for mmol/L users:

```swift
// NightscoutManager.swift:1286-1410
func parseReasonGlucoseValuesToMmolL(_ reason: String) -> String
```

Handles patterns: `ISF:`, `Target:`, `minPredBG`, `minGuardBG`, `Dev:`, `BGI`, etc.

### TDD Injection

Total Daily Dose is injected into reason string:

```swift
// NightscoutManager.swift:1421-1451
func injectTDD(into reason: String, tdd: Decimal?) -> String
// Result: "minPredBG 5.2, TDD: 45.3 U"
```

## Profile Sync

### Unique Fields Uploaded

Trio includes app-specific fields in profile:

```swift
// NightscoutManager.swift:743-756
let profileStore = NightscoutProfileStore(
    defaultProfile: defaultProfile,
    startDate: now,
    mills: Int(now.timeIntervalSince1970) * 1000,
    units: nsUnits,
    enteredBy: NightscoutTreatment.local,
    store: [defaultProfile: scheduledProfile],
    bundleIdentifier: bundleIdentifier,       // iOS app identifier
    deviceToken: deviceToken,                  // APNS push token
    isAPNSProduction: isAPNSProduction,       // APNS environment
    overridePresets: presetOverrides,         // Override configurations
    teamID: teamID,                            // Apple Team ID
    expirationDate: expireDate                 // Build expiration
)
```

**Security Note**: APNS push token and Team ID enable remote commands via Nightscout.

## Gaps Identified

### GAP-SYNC-042: Trio Missing objectId Cache

**Description**: Trio does not maintain mapping between local `id` and Nightscout `_id` (objectId).

**Impact**: 
- Delete operations rely on `find[id][$eq]` query which may fail if `id` field isn't indexed
- No reliable way to update existing Nightscout records
- May cause orphaned records on delete failures

**Affected Systems**: Trio → Nightscout

**Remediation**: Implement objectId cache similar to Loop's `ObjectIdCache`

### GAP-SYNC-043: No Update Operation Support

**Description**: Trio only supports create and delete, not update operations on Nightscout.

**Impact**: Treatment modifications require delete + re-create, which may cause temporary gaps in data visibility.

**Affected Systems**: Trio treatments, overrides

**Remediation**: Add PUT/PATCH support with objectId tracking

### GAP-SYNC-044: Profile Contains Sensitive Push Credentials

**Description**: APNS device token, Team ID, and bundle identifier uploaded to Nightscout profile.

**Impact**: Anyone with read access to profile endpoint can see push notification credentials. Combined with Nightscout credentials, could enable unauthorized remote commands.

**Affected Systems**: Trio profile sync

**Remediation**: Encrypt sensitive fields or use separate authenticated endpoint

## Requirements

### REQ-SYNC-010: Sync Identity Mapping

**Statement**: AID apps MUST maintain mapping between local sync identifiers and Nightscout objectIds.

**Rationale**: Required for reliable update and delete operations.

**Verification**: Confirm objectId cache implementation with create/update/delete cycle test.

### REQ-SYNC-011: Delete Operation Validation

**Statement**: Delete operations MUST verify success by checking response or re-querying.

**Rationale**: Silent delete failures lead to duplicate records and sync divergence.

**Verification**: Test delete with network interruption; confirm retry or error reporting.

### REQ-SYNC-012: Sensitive Credential Separation

**Statement**: Push notification credentials MUST NOT be stored in publicly readable collections.

**Rationale**: APNS tokens combined with API access could enable unauthorized remote commands.

**Verification**: Audit profile endpoint; confirm credentials not included or are encrypted.

## Comparison Matrix

| Feature | Trio | Loop | AAPS |
|---------|------|------|------|
| API Version | v1 | v1 | v1/v3 |
| objectId Cache | ❌ | ✅ | ✅ |
| Update Operations | ❌ | ✅ | ✅ |
| Delete Operations | Query-based | ID-based | ID-based |
| Throttling | Per-pipeline | None | Batched |
| Bidirectional Sync | Partial (fetch carbs) | Full | Full |
| enteredBy Filtering | ✅ | ✅ | ✅ |
| Profile Push Creds | ✅ (included) | ❌ | ❌ |

## Recommendations

### 1. Implement ObjectId Cache (Priority: High)

Add `ObjectIdCache` similar to Loop:

```swift
struct TrioObjectIdCache {
    var mappings: [String: String]  // localId → nightscoutObjectId
    
    mutating func add(localId: String, objectId: String)
    func findObjectId(for localId: String) -> String?
}
```

### 2. Add Update Operation Support (Priority: Medium)

Implement PUT operations for treatment updates:

```swift
func updateTreatment(_ treatment: NightscoutTreatment, objectId: String) async throws
```

### 3. Secure Profile Credentials (Priority: High)

Move APNS credentials to separate authenticated endpoint or encrypt:

```swift
struct SecureProfileExtension: JSON {
    let encryptedDeviceToken: String
    let encryptedTeamID: String
}
```

### 4. Add Sync Verification (Priority: Medium)

Implement periodic sync verification to detect divergence:

```swift
func verifySyncIntegrity() async -> SyncReport
```

## Code References

| Component | File | Lines |
|-----------|------|-------|
| Upload Pipeline | `NightscoutUploadPipeline.swift` | 1-42 |
| Core Manager | `NightscoutManager.swift` | 1-1451 |
| API Client | `NightscoutAPI.swift` | 1-575 |
| Treatment Model | `NightscoutTreatment.swift` | 1-65 |
| Status Model | `NightscoutStatus.swift` | 1-71 |
| Loop ObjectId Cache | `ObjectIdCache.swift` (LoopWorkspace) | 1-70 |
| Loop Sync Service | `NightscoutService.swift` (LoopWorkspace) | 1-260 |

## Related Documents

- `docs/10-domain/trio-oref-integration-mapping.md` - Trio algorithm analysis
- `traceability/aid-sync-gaps.md` - Sync gap registry
- `specs/openapi/aid-treatments-2025.yaml` - Treatment schema
