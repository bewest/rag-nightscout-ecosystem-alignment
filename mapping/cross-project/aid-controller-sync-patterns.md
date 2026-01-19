# AID Controller Sync Patterns

This document provides a deep analysis of how closed-loop AID controllers (Trio, Loop, AAPS) synchronize data with Nightscout. It validates documented deduplication strategies against actual client behavior, identifies undocumented fields and patterns, and feeds into conformance test scenarios.

---

## Executive Summary

| Aspect | Trio | Loop | AAPS |
|--------|------|------|------|
| **API Version** | v1 | v1 | v3 (NSClientV3) |
| **Auth Method** | SHA1 api-secret header | SHA1 api-secret header | JWT Bearer token |
| **Sync Direction** | Bi-directional | Bi-directional | Bi-directional |
| **Identity Strategy** | `enteredBy` filtering | `syncIdentifier` UUID | `identifier` + composite key |
| **Dedup on Upload** | Server-side (POST) | Server-side (POST) | Client-side + server |
| **Dedup on Download** | `enteredBy` exclusion | Not documented | `nightscoutId` matching |
| **Real-time Support** | No | No | WebSocket optional |

---

## 1. Trio Sync Patterns

### 1.1 API Usage

Trio uses Nightscout API v1 exclusively:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/entries/sgv.json` | GET | Fetch glucose readings |
| `/api/v1/entries.json` | POST | Upload glucose readings |
| `/api/v1/treatments.json` | GET/POST/DELETE | Treatments CRUD |
| `/api/v1/devicestatus.json` | POST | Upload loop status |
| `/api/v1/profile.json` | POST | Upload profile |

### 1.2 Identity and Deduplication

**Upload Identity:**
```swift
static let local = "Trio"  // enteredBy field
```

All Trio uploads use `enteredBy: "Trio"` for identification.

**Download Deduplication:**
```swift
// Carbs fetch excludes own entries
components.queryItems = [
    URLQueryItem(name: "find[carbs][$exists]", value: "true"),
    URLQueryItem(name: "find[enteredBy][$ne]", value: CarbsEntry.manual),
    URLQueryItem(name: "find[enteredBy][$ne]", value: NightscoutTreatment.local)  // "Trio"
]
```

| Download Type | Filter Logic | Rationale |
|---------------|--------------|-----------|
| Carbs | `enteredBy != "Trio"` AND `enteredBy != manual` | Avoid processing own entries |
| Temp Targets | `enteredBy != "Trio"` AND `enteredBy != manual` | Avoid processing own entries |
| Glucose | No filter (fetches all) | CGM data is shared across devices |

### 1.3 Upload Triggers

| Data Type | Trigger | Endpoint |
|-----------|---------|----------|
| Device Status | After each loop cycle | `POST /api/v1/devicestatus.json` |
| Treatments | Observer on pump history, carbs, temp targets | `POST /api/v1/treatments.json` |
| Glucose | When `uploadGlucose` setting enabled | `POST /api/v1/entries.json` |
| Profile | On profile/settings change | `POST /api/v1/profile.json` |

### 1.4 Undocumented Fields Used

| Field | Location | Purpose |
|-------|----------|---------|
| `fat` | NightscoutTreatment | Fat grams for FPU calculation |
| `protein` | NightscoutTreatment | Protein grams for FPU calculation |
| `foodType` | NightscoutTreatment | Meal classification |
| `openaps.version` | DeviceStatus | Algorithm version ("0.7.1") |

### 1.5 Retry and Error Handling

```swift
static let retryCount = 1
static let timeout: TimeInterval = 60

return service.run(request)
    .retry(Config.retryCount)
    .decode(type: [BloodGlucose].self, decoder: JSONCoding.decoder)
    .catch { error -> AnyPublisher<[BloodGlucose], Swift.Error> in
        warning(.nightscout, "Glucose fetching error: \(error.localizedDescription)")
        return Just([]).setFailureType(to: Swift.Error.self).eraseToAnyPublisher()
    }
```

**Behavior:** Silent failure with empty result on error (1 retry, 60s timeout).

---

## 2. Loop Sync Patterns

### 2.1 API Usage

Loop uses Nightscout API v1:

| Data Type | Method | Notes |
|-----------|--------|-------|
| Doses (bolus, temp basal, suspend) | POST | `syncIdentifier` for dedup |
| Carbs | POST | `identifier` for dedup |
| Overrides | POST | UUID-based `_id` |
| Device Status | POST | Per loop cycle |

### 2.2 Identity and Deduplication

**Device Identity:**
```swift
device: "loop://\(UIDevice.current.name)"
```

**Sync Identifier Strategy:**

| Loop Type | Sync ID Format | Nightscout Field |
|-----------|----------------|------------------|
| Dose | UUID from pump or generated | `syncIdentifier` |
| Carb | UUID generated on entry | `identifier` |
| Override | `TemporaryScheduleOverride.syncIdentifier` | `_id` |

**Critical Issue (GAP-SYNC-001):**
```swift
/* id: objectId, */ /// Specifying _id only works when doing a put (modify); 
/// all dose uploads are currently posting
```

Loop uses POST (not PUT), which may create duplicates in Nightscout if the server's dedup logic doesn't recognize the `syncIdentifier`.

### 2.3 Upload Mappings

**Bolus:**
| Loop Field | Nightscout Field |
|------------|------------------|
| `startDate` | `timestamp` |
| `deliveredUnits` / `programmedUnits` | `amount` |
| `automatic` | `automatic` |
| `syncIdentifier` | `syncIdentifier` |
| `insulinType?.brandName` | `insulinType` |
| `duration >= 30 min` | `bolusType: Square` |

**Temp Basal:**
| Loop Field | Nightscout Field |
|------------|------------------|
| `unitsPerHour` | `rate`, `absolute` |
| `endDate - startDate` | `duration` |
| `automatic` | `automatic` (defaults true) |

**Suspend:** Uploaded as temp basal with `rate: 0` and `reason: "suspend"`.

### 2.4 Device Status Structure

Loop's devicestatus differs from oref0-based systems:

```json
{
  "device": "loop://iPhone",
  "loop": {
    "iob": { "timestamp": "...", "iob": 2.35 },
    "cob": { "timestamp": "...", "cob": 45.5 },
    "predicted": {
      "startDate": "...",
      "values": [120, 125, 130, ...]  // Single array
    },
    "enacted": { "rate": 1.2, "duration": 30, "received": true }
  }
}
```

**Key Difference:** Loop uploads single `predicted.values` array. oref0-based systems (Trio, AAPS) upload separate `predBGs.IOB[]`, `predBGs.COB[]`, `predBGs.UAM[]`, `predBGs.ZT[]`.

### 2.5 Data Not Uploaded

Loop computes but does **not** upload:
- `effects.insulin[]` - Expected glucose change from insulin
- `effects.carbs[]` - Expected glucose change from carbs
- `effects.momentum[]` - Short-term trajectory
- `effects.retrospectiveCorrection[]` - Unexplained discrepancy correction
- Algorithm parameters (insulin model, RC type, carb absorption details)
- Override supersession relationships

---

## 3. AAPS Sync Patterns

### 3.1 API Usage

AAPS NSClientV3 uses Nightscout API v3:

| Worker | Purpose | Endpoint Pattern |
|--------|---------|-----------------|
| `LoadBgWorker` | Download glucose | `GET /api/v3/entries` |
| `LoadTreatmentsWorker` | Download treatments | `GET /api/v3/treatments` |
| `LoadProfileStoreWorker` | Download profiles | `GET /api/v3/profile` |
| `LoadDeviceStatusWorker` | Download device status | `GET /api/v3/devicestatus` |
| `DataSyncWorker` | Upload local changes | `POST/PUT /api/v3/*` |

### 3.2 Identity and Deduplication

**Multi-field Identity:**
```kotlin
val identifier: String?       // Client-generated UUID
val pumpId: Long?             // Pump event ID
val pumpType: String?         // Pump driver type
val pumpSerial: String?       // Pump serial number
```

**Deduplication Strategy:**
1. **Primary Key:** `identifier` (client UUID) for updates/deletes
2. **Composite Key:** `pumpId` + `pumpType` + `pumpSerial` for pump events
3. **Timestamp Key:** `srvModified` for change detection

**Local Storage:**
```kotlin
data class InterfaceIDs(
    var nightscoutId: String? = null,  // NS _id
    var pumpId: Long? = null,
    var pumpType: String? = null,
    var pumpSerial: String? = null,
    var temporaryId: Long? = null,
    var endId: Long? = null
)
```

### 3.3 Sync State Tracking

```kotlin
data class LastModified(val collections: Collections) {
    data class Collections(
        var entries: Long = 0,
        var treatments: Long = 0,
        var profile: Long = 0,
        var devicestatus: Long = 0,
        var foods: Long = 0
    )
}
```

AAPS tracks per-collection:
- `lastLoadedSrvModified` - Last fetched timestamp
- `newestDataOnServer` - Server's newest timestamp
- `firstLoadContinueTimestamp` - Resume point for initial load

### 3.4 Sync Modes

| Mode | Behavior |
|------|----------|
| **Initial Sync** | Fetch up to 500 records per batch, max 100 days history |
| **Incremental Sync** | Fetch only records with `srvModified > lastLoadedSrvModified` |
| **Full Sync** | Clears sync state, re-fetches all data within age limit |

### 3.5 WebSocket Support

```kotlin
val status = when {
    preferences.get(BooleanKey.NsClient3UseWs) && 
        nsClientV3Service?.wsConnected == true  -> "WS: Connected"
    // ... polling fallback
}
```

AAPS optionally uses WebSocket for real-time updates, falling back to polling.

### 3.6 Error Handling

```kotlin
// Exception hierarchy
NightscoutException                    // Base
InvalidAccessTokenException            // Auth failure → re-auth
DateHeaderOutOfToleranceException      // Time sync issue → warn user
InvalidFormatNightscoutException       // Data format error → skip record
UnsuccessfulNightscoutException        // API error → retry with backoff
```

---

## 4. Cross-Controller Comparison

### 4.1 Deduplication Strategy Matrix

| Controller | Upload Dedup | Download Dedup | Conflict Resolution |
|------------|--------------|----------------|---------------------|
| Trio | Relies on server (POST) | `enteredBy` exclusion filter | None (overwrites) |
| Loop | Relies on server (POST) | None documented | None documented |
| AAPS | Client `identifier` + server | `nightscoutId` matching | Server timestamp wins |

### 4.2 Identity Field Usage

| Controller | Primary Identity | Nightscout Field | Notes |
|------------|------------------|------------------|-------|
| Trio | `enteredBy: "Trio"` | `enteredBy` | Simple string match |
| Loop | UUID `syncIdentifier` | `syncIdentifier` | Per-record UUID |
| AAPS | UUID `identifier` + pump composite | `identifier`, pump fields | Multi-strategy |
| xDrip | UUID `uuid` | `uuid` | Client-generated |

**GAP-003:** No unified sync identity field exists across controllers.

### 4.3 API Version Implications

| Aspect | API v1 (Trio, Loop) | API v3 (AAPS) |
|--------|---------------------|---------------|
| Auth | SHA1 api-secret header | JWT Bearer token |
| Dedup | Server heuristics | Explicit identifier |
| History | Manual timestamp queries | `/history` endpoint |
| Soft Delete | Not supported | `isValid=false` |
| Conflict Detection | None | `If-Unmodified-Since` header |

### 4.4 DeviceStatus Structure Comparison

| Field Path | Trio | Loop | AAPS |
|------------|------|------|------|
| `device` | `"Trio"` | `"loop://DeviceName"` | `"openaps://phoneModel"` |
| `openaps.iob` | Yes | No | Yes |
| `openaps.suggested` | Yes | No | Yes |
| `openaps.enacted` | Yes | No | Yes |
| `loop.iob` | No | Yes | No |
| `loop.cob` | No | Yes | No |
| `loop.predicted.values` | No | Yes (single array) | No |
| `openaps.suggested.predBGs.*` | Yes (IOB/COB/UAM/ZT) | No | Yes |
| `pump.reservoir` | Yes | Yes | Yes |
| `pump.battery` | Yes | Yes | Yes |
| `uploader.battery` | Yes | Yes | Yes |

---

## 5. Nightscout Server Deduplication

### 5.1 API v3 Fallback Rules

When `API3_DEDUP_FALLBACK_ENABLED=true`:

| Collection | Duplicate Criteria |
|------------|-------------------|
| `devicestatus` | `created_at` + `device` |
| `entries` | `date` + `type` |
| `treatments` | `created_at` + `eventType` |
| `profile` | `created_at` |
| `food` | `created_at` |

**Behavior:** POST returns 200 (instead of 201) if duplicate detected, returning existing document.

### 5.2 Controller Alignment with Server Dedup

| Controller | Relies on Server Dedup | Sends Unique Identifiers | Risk |
|------------|------------------------|--------------------------|------|
| Trio | Yes (POST only) | No explicit sync ID | Medium - depends on timestamp precision |
| Loop | Yes (POST only) | `syncIdentifier` (not always recognized) | High - duplicates possible |
| AAPS | Partial (also client-side) | `identifier` (explicit) | Low - client prevents duplicates |

---

## 6. Identified Gaps and Recommendations

### 6.1 Critical Gaps

| Gap ID | Description | Affected Controllers | Impact |
|--------|-------------|---------------------|--------|
| GAP-SYNC-001 | Loop uses POST without PUT, may create duplicates | Loop | Data integrity |
| GAP-SYNC-002 | Effect timelines not uploaded | Loop | Debugging difficulty |
| GAP-SYNC-003 | No unified sync identity across controllers | All | Reconciliation complexity |
| GAP-SYNC-004 | Override supersession not tracked | Loop, Trio | History inaccuracy |
| GAP-SYNC-005 | Algorithm parameters not synced | All | Cross-system comparison impossible |

### 6.2 Undocumented Fields Relied Upon

| Field | Used By | Not in NS Schema |
|-------|---------|------------------|
| `fat`, `protein` | Trio | Informal extension |
| `syncIdentifier` | Loop | Not in v1 schema |
| `insulinType` | Loop, AAPS | Informal extension |
| `automatic` | Loop, AAPS | Boolean for SMB identification |

### 6.3 Conformance Test Recommendations

Based on this analysis, the following conformance tests should be added:

1. **SYNC-DEDUP-001:** Verify server rejects duplicate based on `created_at` + `eventType`
2. **SYNC-DEDUP-002:** Verify `identifier` field takes precedence over timestamp-based dedup
3. **SYNC-DEDUP-003:** Verify `enteredBy` filter correctly excludes self-uploaded records
4. **SYNC-DEDUP-004:** Verify `syncIdentifier` is preserved through upload/download cycle
5. **SYNC-IDENTITY-001:** Verify controller can identify own records after server restart
6. **SYNC-HISTORY-001:** Verify incremental sync using `srvModified` timestamp
7. **SYNC-CONFLICT-001:** Verify `If-Unmodified-Since` header prevents concurrent updates

---

## 7. Recommendations for Alignment

### 7.1 Short-term (No Breaking Changes)

1. **Document `syncIdentifier` behavior** in Nightscout v1 API
2. **Add optional `identifier` field** to treatments in v1 API
3. **Standardize `enteredBy` format** across controllers (currently varies)

### 7.2 Medium-term (Backward Compatible)

1. **Migrate all controllers to API v3** for explicit identity management
2. **Add `supersedes` field** to override treatments
3. **Upload effect timelines** in devicestatus for debugging

### 7.3 Long-term (Breaking Changes)

1. **Unified sync protocol** with explicit conflict resolution
2. **Mandatory `identifier` field** for all records
3. **Standardized prediction format** across algorithms

---

## 8. Source References

### 8.1 Primary Source Files

#### Trio
| File | Purpose | Key Lines | Evidence For |
|------|---------|-----------|--------------|
| `trio:Trio/Sources/Services/Network/Nightscout/NightscoutManager.swift` | Sync orchestration | L303-376, L407-553, L555-569 | Upload triggers, profile sync |
| `trio:Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift` | HTTP client | L46-50, L60-98, L101-142, L202-244 | Auth, glucose/carbs/temp target fetch |
| `trio:Trio/Sources/Models/NightscoutTreatment.swift` | Treatment model | L12-30, L31 | Field mapping, `enteredBy: "Trio"` |

#### Loop
| File | Purpose | Key Lines | Evidence For |
|------|---------|-----------|--------------|
| `loop:NightscoutService/NightscoutServiceKit/Extensions/DoseEntry.swift` | Dose upload | L29-42, L56-70 | Bolus/temp basal mapping, `syncIdentifier` |
| `loop:NightscoutService/NightscoutServiceKit/Extensions/StoredDosingDecision.swift` | Device status | L115-124, L128-141 | DeviceStatus structure |
| `loop:NightscoutService/NightscoutServiceKit/RemoteCommands/Actions/` | Remote commands | Full directory | OverrideAction, CarbAction, BolusAction |

#### AAPS
| File | Purpose | Key Lines | Evidence For |
|------|---------|-----------|--------------|
| `aaps:plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/NSClientV3Plugin.kt` | Plugin | Full file | NSClientV3 architecture |
| `aaps:plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/` | Converters | Directory | toNS* conversion functions |
| `aaps:database/impl/src/main/kotlin/app/aaps/database/entities/embedments/InterfaceIDs.kt` | Identity storage | Full file | `nightscoutId`, pump composite key |
| `aaps:core/nssdk/src/main/kotlin/app/aaps/core/nssdk/remotemodel/LastModified.kt` | Sync state | Full file | Per-collection timestamp tracking |

#### Nightscout Server
| File | Purpose | Key Lines | Evidence For |
|------|---------|-----------|--------------|
| `crm:lib/api3/swagger.yaml` | API v3 spec | Full file | Endpoint definitions, schema |
| `crm:lib/api3/generic/create/validate.js` | Dedup validation | Dedup section | Fallback dedup rules |
| `crm:lib/server/treatments.js` | Treatment handling | Full file | V1 treatment processing |

### 8.2 Cross-Reference to Existing Mapping Documents

This document synthesizes and extends analysis from:

| Document | Contribution |
|----------|--------------|
| [mapping/trio/nightscout-sync.md](../trio/nightscout-sync.md) | Trio API usage, field mappings, upload flows |
| [mapping/loop/nightscout-sync.md](../loop/nightscout-sync.md) | Loop dose upload, device status, identified gaps |
| [mapping/aaps/nightscout-sync.md](../aaps/nightscout-sync.md) | AAPS NSClientV3 architecture, sync modes |
| [mapping/nightscout/data-collections.md](../nightscout/data-collections.md) | Sync identity per controller |
| [specs/openapi/nightscout-api3-summary.md](../../specs/openapi/nightscout-api3-summary.md) | API v3 dedup rules, field immutability |

### 8.3 Evidence Traceability

| Claim | Evidence Location |
|-------|-------------------|
| Trio uses `enteredBy: "Trio"` | `trio:NightscoutTreatment.swift#L31` |
| Trio excludes own entries with `$ne` filter | `trio:NightscoutAPI.swift#L296-298` |
| Loop uses `syncIdentifier` for dedup | `loop:DoseEntry.swift#L39` |
| Loop uses POST only (no PUT) | `loop:DoseEntry.swift#L30-31` (comment) |
| AAPS uses `identifier` as primary key | `aaps:InterfaceIDs.kt` |
| AAPS uses pump composite key | `aaps:InterfaceIDs.kt#pumpId,pumpType,pumpSerial` |
| API v3 dedup uses `created_at` + `eventType` | `specs/openapi/nightscout-api3-summary.md#create-post-collection` |

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Initial deep dive on AID controller sync patterns |
