# Loop Sync Identity Fields Extraction

> **Source**: `externals/LoopWorkspace/`  
> **Last Updated**: 2026-01-29

## Overview

This document extracts how Loop identifies treatments for Nightscout synchronization. Loop uses `syncIdentifier` as the primary identity field, with a local `ObjectIdCache` mapping to Nightscout's `_id`.

---

## Core Identity Pattern

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│    Loop      │    │ ObjectIdCache│    │  Nightscout  │
│              │    │              │    │              │
│syncIdentifier│───▶│   Mapping    │───▶│    _id       │
│   (String)   │    │              │    │  (ObjectId)  │
└──────────────┘    └──────────────┘    └──────────────┘
```

**Key Insight**: Loop maintains a **bidirectional cache** that maps `syncIdentifier` to Nightscout `_id`, enabling updates and deletes without re-querying Nightscout.

---

## syncIdentifier Definition

### Protocol Definition

**File**: `LoopKit/LoopKit/GlucoseKit/GlucoseSampleValue.swift:31`

```swift
public protocol GlucoseSampleValue {
    var syncIdentifier: String? { get }
    // ...
}
```

### Property in Data Types

| Type | File | Definition |
|------|------|------------|
| `DoseEntry` | `InsulinKit/DoseEntry.swift:24` | `public internal(set) var syncIdentifier: String?` |
| `StoredGlucoseSample` | `GlucoseKit/StoredGlucoseSample.swift:18` | `public let syncIdentifier: String?` |
| `SyncCarbObject` | `CarbKit/SyncCarbObject.swift:26` | `public let syncIdentifier: String?` |
| `StoredCarbEntry` | `CarbKit/StoredCarbEntry.swift` | `public let syncIdentifier: String?` |

---

## syncIdentifier Generation

### Pump Events → Hex String

**File**: `LoopKit/LoopKit/PumpManager/NewPumpEvent.swift:33`

```swift
dose?.syncIdentifier = raw.hexadecimalString
```

The `syncIdentifier` is the **hexadecimal representation of raw pump event data**, ensuring cryptographic uniqueness for each pump-originated treatment.

### Carb Entries → UUID String

For user-entered carbs, `syncIdentifier` is derived from a UUID:

```swift
public let uuid: UUID
public let syncIdentifier: String?  // uuid.uuidString
```

---

## ObjectIdCache

**File**: `NightscoutService/NightscoutServiceKit/ObjectIdCache.swift`

### Structure

```swift
struct ObjectIDMapping {
    var loopSyncIdentifier: String      // Loop's syncIdentifier
    var nightscoutObjectId: String      // Nightscout's _id
}

class ObjectIdCache {
    private var cache: [ObjectIDMapping] = []
    
    func findObjectIdBySyncIdentifier(_ syncIdentifier: String) -> String?
    func addMapping(syncIdentifier: String, objectId: String)
    func purgeOldEntries()  // Removes entries > 24 hours old
}
```

### Cache Lifetime

**File**: `NightscoutService/NightscoutServiceKit/NightscoutService.swift:27`

```swift
private let objectIdCacheKeepTime: TimeInterval = 24 * 60 * 60  // 24 hours
```

---

## Treatment Types

### DoseEntry (Insulin)

**File**: `LoopKit/LoopKit/InsulinKit/DoseEntry.swift`

```swift
public struct DoseEntry {
    public let type: DoseType           // basal, bolus, tempBasal, suspend, resume
    public let startDate: Date
    public let endDate: Date
    public let value: Double
    public let unit: DoseUnit           // units or unitsPerHour
    public var deliveredUnits: Double?
    public var syncIdentifier: String?
    public let insulinType: InsulinType?
    public let automatic: Bool?
    public let manuallyEntered: Bool
    public let isMutable: Bool
    public let wasProgrammedByPumpUI: Bool
    public var scheduledBasalRate: HKQuantity?
}
```

**DoseType Enum**:
- `basal` - Scheduled basal
- `bolus` - Normal bolus
- `tempBasal` - Temporary basal rate
- `suspend` - Pump suspend
- `resume` - Pump resume

### StoredCarbEntry (Carbs)

**File**: `LoopKit/LoopKit/CarbKit/StoredCarbEntry.swift`

```swift
public struct StoredCarbEntry {
    public let uuid: UUID
    public let provenanceIdentifier: String  // "com.LoopKit.Loop"
    public let syncIdentifier: String?
    public let syncVersion: Int?
    public let startDate: Date
    public let quantity: HKQuantity          // grams
    public let foodType: String?
    public let absorptionTime: TimeInterval?
    public let createdByCurrentApp: Bool
    public let userCreatedDate: Date?
    public let userUpdatedDate: Date?
}
```

---

## HealthKit Metadata

Loop stores treatments in HealthKit with metadata keys that enable sync:

### Insulin Samples

**File**: `LoopKit/LoopKit/InsulinKit/HKQuantitySample+InsulinKit.swift`

| Metadata Key | Purpose |
|--------------|---------|
| `HKMetadataKeySyncIdentifier` | Links to Loop's syncIdentifier |
| `HKMetadataKeySyncVersion` | Version for conflict resolution |
| `HKMetadataKeyInsulinDeliveryReason` | `.basal` or `.bolus` |
| `MetadataKeyScheduledBasalRate` | Scheduled rate for temp basals |
| `MetadataKeyInsulinType` | Insulin model (rapid, regular, etc.) |
| `MetadataKeyManuallyEntered` | User-entered vs pump-reported |
| `MetadataKeyAutomaticallyIssued` | Loop-issued vs manual |
| `MetadataKeyIsSuspend` | Suspend event flag |

### Carb Samples

**File**: `LoopKit/LoopKit/CarbKit/HKQuantitySample+CarbKit.swift`

| Metadata Key | Purpose |
|--------------|---------|
| `HKMetadataKeyFoodType` | Food description |
| `com.loopkit.AbsorptionTime` | Expected absorption duration |
| `com.loopkit.CarbKit.UserCreatedDate` | Original entry time |
| `com.loopkit.CarbKit.UserUpdatedDate` | Last modification time |

---

## Nightscout Upload Flow

### Service Layer

**File**: `NightscoutService/NightscoutServiceKit/NightscoutService.swift`

Loop implements `RemoteDataService` protocol for uploading:
- `uploadTreatmentData()` - Insulin and carb treatments
- `uploadGlucoseData()` - CGM readings
- `uploadDosingDecision()` - Loop state (devicestatus)

### Treatment Mapping

**File**: `NightscoutService/NightscoutServiceKit/Extensions/DoseEntry.swift`

| Loop Type | Nightscout eventType |
|-----------|---------------------|
| `DoseEntry.bolus` | `BolusNightscoutTreatment` |
| `DoseEntry.tempBasal` | `TempBasalNightscoutTreatment` |
| `DoseEntry.suspend` | `TempBasalNightscoutTreatment` (rate=0) |
| `StoredCarbEntry` | `CarbCorrectionNightscoutTreatment` |
| `Override` | `OverrideTreatment` |

### Upload with Deduplication

**File**: `NightscoutService/NightscoutServiceKit/Extensions/NightscoutUploader.swift:37-40`

```swift
if let syncIdentifier = carbEntry.syncIdentifier,
   let objectId = objectIdCache.findObjectIdBySyncIdentifier(syncIdentifier) {
    // Update existing treatment
    return carbEntry.carbCorrectionNightscoutTreatment(withObjectId: objectId)
} else {
    // Create new treatment
    return carbEntry.carbCorrectionNightscoutTreatment()
}
```

---

## Sync Identity Comparison

| System | Primary ID | Secondary ID | Storage | Dedup Strategy |
|--------|-----------|--------------|---------|----------------|
| **Loop** | `syncIdentifier` | HealthKit UUID | ObjectIdCache | Local cache maps to NS `_id` |
| **AAPS** | `interfaceIDs.nightscoutId` | `pumpId+pumpType+pumpSerial` | Room DB | Check before insert |
| **Trio** | `syncIdentifier` | N/A | CoreData | Similar to Loop |
| **xDrip+** | `uuid` | N/A | SQLite | Upsert by uuid |

### Key Differences

| Aspect | Loop | AAPS |
|--------|------|------|
| **ID Source** | Pump event hex / UUID | Nightscout _id |
| **Cache** | 24-hour ObjectIdCache | Persistent Room DB |
| **API** | v1 POST | v3 PUT |
| **Batch** | Yes (zip pattern) | Sequential single-doc |

---

## Gaps Identified

### GAP-SYNC-005: Loop ObjectIdCache Not Persistent

**Description**: Loop's ObjectIdCache is memory-only with 24-hour purge. App restart or cache expiry can cause duplicate uploads.

**Source**: `NightscoutService/NightscoutServiceKit/ObjectIdCache.swift`

**Impact**:
- Duplicate treatments if app restarts
- Lost mapping after 24 hours
- No recovery mechanism

### GAP-SYNC-006: Loop Uses v1 API Only

**Description**: Loop uploads via API v1 POST, not v3 PUT. This prevents server-side deduplication.

**Source**: `NightscoutService/NightscoutServiceKit/NightscoutUploader.swift`

**Impact**:
- Must rely on ObjectIdCache for updates
- No server-side `identifier` deduplication
- Same pattern as all bridges (tconnectsync, librelink-up)

### GAP-SYNC-007: syncIdentifier Format Not Standardized

**Description**: `syncIdentifier` can be pump event hex, UUID string, or other formats. No standard specification.

**Source**: Various files in LoopKit

**Impact**:
- Cannot parse syncIdentifier to extract metadata
- Cross-system sync relies on opaque strings
- No validation possible

---

## Source File Reference

### Core Identity
- `externals/LoopWorkspace/LoopKit/LoopKit/GlucoseKit/GlucoseSampleValue.swift` - Protocol
- `externals/LoopWorkspace/LoopKit/LoopKit/InsulinKit/DoseEntry.swift` - Dose model
- `externals/LoopWorkspace/LoopKit/LoopKit/CarbKit/StoredCarbEntry.swift` - Carb model
- `externals/LoopWorkspace/LoopKit/LoopKit/CarbKit/SyncCarbObject.swift` - Sync object

### HealthKit Integration
- `externals/LoopWorkspace/LoopKit/LoopKit/InsulinKit/HKQuantitySample+InsulinKit.swift`
- `externals/LoopWorkspace/LoopKit/LoopKit/CarbKit/HKQuantitySample+CarbKit.swift`

### Nightscout Service
- `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/NightscoutService.swift`
- `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/ObjectIdCache.swift`
- `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/Extensions/NightscoutUploader.swift`
- `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/Extensions/DoseEntry.swift`

---

## Summary

| Aspect | Loop Pattern |
|--------|--------------|
| **Primary ID** | `syncIdentifier` (String) |
| **Generation** | Pump event hex or UUID |
| **NS Mapping** | ObjectIdCache (24hr, memory-only) |
| **API Version** | v1 POST |
| **Dedup Strategy** | Local cache lookup before upload |
| **HealthKit Sync** | Metadata keys for round-trip |

Loop's sync identity pattern is robust for normal operation but has edge cases around app restarts and cache expiry that can cause duplicates.
