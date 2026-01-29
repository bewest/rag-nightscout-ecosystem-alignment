# Sync Identity Field Audit

**Date:** 2026-01-29  
**Status:** Complete  
**Type:** Cross-project verification

## Overview

This document audits how each system in the Nightscout ecosystem identifies and tracks records for synchronization. Consistent identity management is critical for avoiding duplicates and ensuring reliable data sync.

## Sync Identity Summary

| System | Primary ID | Nightscout Mapping | Dedup Strategy |
|--------|------------|-------------------|----------------|
| **Nightscout** | `identifier` | N/A (server) | `device_date_eventType` hash |
| **Loop** | `syncIdentifier` | `objectIdCache` | UUID-based |
| **Trio** | `syncIdentifier` | (inherited from Loop) | UUID-based |
| **AAPS** | `ids.nightscoutId` | `_id` storage | Multi-ID tracking |
| **xDrip+** | `uuid` | `_id` or none | UUID column |

---

## Nightscout Server

**Source:** `externals/cgm-remote-monitor/lib/api3/shared/operationTools.js:97-107`

### Identifier Calculation

Nightscout API v3 calculates identifiers deterministically:

```javascript
function calculateIdentifier (doc) {
  let key = doc.device + '_' + doc.date;
  if (doc.eventType) {
    key += '_' + doc.eventType;
  }
  return uuid.v5(key, uuidNamespace);
}
```

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `identifier` | String (UUID v5) | Calculated from device+date+eventType |
| `_id` | ObjectId | MongoDB internal ID |
| `srvModified` | Number | Server modification timestamp |
| `srvCreated` | Number | Server creation timestamp |

### Deduplication Behavior

1. If client provides `identifier`, server validates it matches calculated value
2. If mismatch, server logs warning but uses client value
3. If no `identifier`, server calculates and assigns it
4. Duplicates detected by `identifier` uniqueness constraint

---

## Loop

**Source:** `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/ObjectIdCache.swift`

### Identity Architecture

Loop maintains a local cache mapping `syncIdentifier` to Nightscout `objectId`:

```swift
public struct ObjectIDMapping {
    var loopSyncIdentifier: String      // Loop's UUID
    var nightscoutObjectId: String      // Nightscout's _id
    var createdAt: Date
}

public struct ObjectIdCache {
    var storageBySyncIdentifier: [String: ObjectIDMapping]
    
    mutating func add(syncIdentifier: String, objectId: String) {
        let mapping = ObjectIDMapping(loopSyncIdentifier: syncIdentifier, 
                                      nightscoutObjectId: objectId)
        storageBySyncIdentifier[syncIdentifier] = mapping
    }
    
    func findObjectIdBySyncIdentifier(_ syncIdentifier: String) -> String? {
        return storageBySyncIdentifier[syncIdentifier]?.nightscoutObjectId
    }
}
```

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `syncIdentifier` | UUID String | Loop-generated, stored locally |
| `nightscoutObjectId` | String | Nightscout's `_id`, cached after upload |

### Sync Flow

1. Loop generates `syncIdentifier` (UUID) for each dose/carb entry
2. On upload, Nightscout returns `_id` 
3. Loop caches `syncIdentifier → _id` mapping
4. Future updates use cached `_id` for PATCH/DELETE

### GAP-SYNC-023: Loop Does Not Send identifier to Nightscout

Loop sends data to Nightscout but does not populate the `identifier` field. This means Nightscout calculates it server-side, potentially causing mismatches if the same data is uploaded from multiple sources.

---

## Trio

**Source:** `externals/Trio/` (inherits LoopKit)

Trio uses the same `syncIdentifier` pattern as Loop via shared LoopKit code.

```swift
// CGMBLEKit/Glucose.swift:101
public var syncIdentifier: String {
    // Generated from timestamp or sensor ID
}

// MinimedPumpManager.swift:437
syncIdentifier: status.glucoseSyncIdentifier ?? UUID().uuidString
```

### Behavior
- Inherits `ObjectIdCache` from LoopKit
- Same mapping strategy as Loop
- Same gap applies (GAP-SYNC-023)

---

## AAPS

**Source:** `externals/AndroidAPS/core/data/src/main/kotlin/app/aaps/core/data/model/IDs.kt`

### Multi-ID Architecture

AAPS tracks multiple IDs per record:

```kotlin
data class IDs(
    var nightscoutSystemId: String? = null,  // NS system identifier
    var nightscoutId: String? = null,        // NS _id
    var pumpType: PumpType? = null,
    var pumpSerial: String? = null,
    var temporaryId: Long? = null,           // Temp ID during sync
    var pumpId: Long? = null,                // Pump history ID
    var startId: Long? = null,
    var endId: Long? = null
)
```

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `nightscoutId` | String | Nightscout's `_id` after sync |
| `nightscoutSystemId` | String | Nightscout system identifier |
| `pumpId` | Long | Pump history sequence number |
| `temporaryId` | Long | Pre-sync temporary ID |

### Sync Strategy

1. AAPS creates record with `temporaryId`
2. On Nightscout upload, stores `nightscoutId` from response
3. Uses `nightscoutId` for updates/deletes
4. Tracks pump origin via `pumpSerial` + `pumpId`

### Advantage

AAPS can trace records back to pump history, enabling pump-authoritative sync.

---

## xDrip+

**Source:** `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/models/Treatments.java:95-96`

### UUID Column

```java
@Column(name = "uuid", unique = true, onUniqueConflicts = Column.ConflictAction.IGNORE)
public String uuid;
```

### Sync Behavior

```java
// GoogleDriveInterface.java:557
if (!doesRemoteFileExist(thistreatment.uuid)) {
    // Upload new treatment
}
```

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `uuid` | String | Client-generated UUID |
| `_id` | Long | Local SQLite row ID |

### GAP-SYNC-024: xDrip+ UUID Not Mapped to Nightscout identifier

xDrip+ generates UUIDs locally but doesn't send them as `identifier` to Nightscout API v3. This prevents server-side deduplication from working correctly.

---

## Cross-System Identity Mapping

### Current State

```
Loop syncIdentifier ─────┐
                         │
Trio syncIdentifier ─────┼──→ Nightscout _id (cached locally)
                         │         │
AAPS ids.nightscoutId ───┘         ▼
                            Nightscout identifier
xDrip+ uuid ─────────────────────────────→ (not mapped)
```

### Desired State

```
Loop syncIdentifier ─────┐
                         │
Trio syncIdentifier ─────┼──→ Nightscout identifier ←──→ Nightscout _id
                         │
AAPS ids.nightscoutId ───┤
                         │
xDrip+ uuid ─────────────┘
```

---

## Gaps Identified

### GAP-SYNC-023: Loop/Trio Missing identifier Field

**Description:** Loop and Trio cache Nightscout `_id` locally but don't send `identifier` on uploads. Server calculates identifier, which may differ from client's `syncIdentifier`.

**Source:** 
- `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/ObjectIdCache.swift:56-58`

**Impact:** 
- Cross-device sync may create duplicates
- Server's `identifier` won't match client's `syncIdentifier`

**Remediation:** 
1. Send `syncIdentifier` as `identifier` field in upload payload
2. Use UUID v5 with same namespace as Nightscout for compatibility

### GAP-SYNC-024: xDrip+ UUID Not Sent as identifier

**Description:** xDrip+ generates local UUIDs but doesn't send them to Nightscout, relying on Last-Modified header for sync instead.

**Source:** `externals/xDrip/.../Treatments.java:95-96`

**Impact:** No server-side deduplication based on client identity.

**Remediation:** Send `uuid` as `identifier` in Nightscout API calls.

### GAP-SYNC-025: No Cross-Controller Identity Standard

**Description:** Each system uses different ID naming conventions (`syncIdentifier`, `nightscoutId`, `uuid`). No shared standard for portable identity.

**Impact:** Records uploaded from different controllers may duplicate.

**Remediation:** 
1. Define standard `identifier` format in OpenAPI spec
2. All clients adopt `device_date_eventType` UUID v5 calculation
3. Or: Each client prefixes identifier with controller name

---

## Recommendations

### For All Clients

1. **Send `identifier` on every upload** - Use deterministic calculation
2. **Store Nightscout `_id` for updates** - Required for PATCH/DELETE
3. **Use UTC timestamps** - Ensure consistent date component

### For Nightscout Server

1. **Document identifier calculation** - Publish UUID namespace
2. **Accept client-provided identifiers** - Trust if well-formed
3. **Return identifier in responses** - Help clients track

### Identifier Format Recommendation

```
identifier = UUID_v5(namespace, "${device}_${epochMillis}_${eventType}")
```

Where:
- `namespace` = Nightscout's published UUID namespace
- `device` = Controller name (e.g., "Loop", "AAPS", "xDrip")
- `epochMillis` = Timestamp in milliseconds
- `eventType` = Event type if applicable

---

## Source File References

| Project | File | Lines |
|---------|------|-------|
| Nightscout | `lib/api3/shared/operationTools.js` | 97-107, 114-126 |
| Loop | `NightscoutServiceKit/ObjectIdCache.swift` | 11-67 |
| Loop | `NightscoutServiceKit/NightscoutService.swift` | 41, 209-212 |
| AAPS | `core/data/src/main/kotlin/.../IDs.kt` | 1-17 |
| Trio | `CGMBLEKit/Glucose.swift` | 101 |
| xDrip+ | `models/Treatments.java` | 95-96 |

---

## Related Documents

- `docs/10-domain/cross-controller-conflicts-deep-dive.md` - Multi-controller scenarios
- `traceability/sync-identity-gaps.md` - Full gap list
- `mapping/cross-project/terminology-matrix.md` - Term definitions
