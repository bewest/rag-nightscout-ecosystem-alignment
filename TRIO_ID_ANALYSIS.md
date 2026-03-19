# Trio iOS App: Nightscout API `_id` Field Analysis

## Executive Summary

Trio iOS app uses **UUID strings** for the `_id` field across all Nightscout collections. Unlike some systems that omit the field or send MongoDB ObjectIds, Trio explicitly generates and sends `_id` values using Swift's UUID type. The app maintains separate `id` and `syncIdentifier` fields for internal tracking and cross-system synchronization.

---

## Primary Research Questions: Answers

### 1. **What does Trio send to the `_id` field?**

**Answer: UUID Strings (always)**

Trio sends UUID strings (format: `"550e8400-e29b-41d4-a716-446655440000"`) to the `_id` field for all collections.

**Evidence:**
- **BloodGlucose model** - `Trio/Sources/Models/BloodGlucose.swift:117`
  ```swift
  init(
      _id: String = UUID().uuidString,  // ← Default UUID string
      ...
  ) {
      self._id = _id
  }
  ```

- **Glucose upload flow** - `Trio/Sources/APS/Storage/GlucoseStorage.swift:416`
  ```swift
  return fetchedResults.map { result in
      BloodGlucose(
          _id: result.id?.uuidString ?? UUID().uuidString,  // ← UUID conversion
          sgv: Int(result.glucose),
          ...
      )
  }
  ```

- **CarbsEntry model** - `Trio/Sources/Models/CarbsEntry.swift:30`
  ```swift
  private enum CodingKeys: String, CodingKey {
      case id = "_id"  // ← Maps `id` property to `_id` JSON field
  }
  ```

- **Treatment construction** - `Trio/Sources/APS/Storage/CarbsStorage.swift:383`
  ```swift
  NightscoutTreatment(
      ...
      id: result.id?.uuidString  // ← Uses UUID string from CoreData
  )
  ```

### 2. **How does Trio use `identifier` vs `syncIdentifier` fields?**

**Answer: Distinct purposes for sync and LoopKit integration**

Trio uses these fields for different purposes:

- **`_id`**: Nightscout's document identifier (UUID string)
- **`id`**: The Swift property that maps to `_id` during JSON encoding (same value)
- **`syncIdentifier`**: LoopKit sync identifier for cross-system deduplication

**Evidence:**

- **BloodGlucose to StoredGlucoseSample conversion** - `Trio/Sources/Models/BloodGlucose.swift:283`
  ```swift
  func convertStoredGlucoseSample(isManualGlucose: Bool) -> StoredGlucoseSample {
      StoredGlucoseSample(
          syncIdentifier: id,  // ← Uses the `_id` value as syncIdentifier
          startDate: dateString.date,
          quantity: HKQuantity(unit: .milligramsPerDeciliter, doubleValue: Double(glucose!)),
          wasUserEntered: isManualGlucose,
          device: HKDevice.local()
      )
  }
  ```

- **CarbsEntry to SyncCarbObject conversion** - `Trio/Sources/Models/CarbsEntry.swift:53`
  ```swift
  func convertSyncCarb(operation: LoopKit.Operation = .create) -> SyncCarbObject {
      SyncCarbObject(
          ...
          syncIdentifier: id,  // ← Same value as `_id`
          ...
      )
  }
  ```

- **DeviceDataManager Tidepool sync** - `Trio/Sources/APS/DeviceDataManager.swift:335`
  ```swift
  _id: sample.syncIdentifier,  // ← Passes syncIdentifier to Tidepool
  ```

### 3. **Does behavior differ by collection type?**

**Answer: Consistent strategy across all collections, but fields vary**

All collections send UUID strings in `_id`, but the data structures differ by type:

| Collection | Model | `_id` Type | Has `syncIdentifier` | Upload Endpoint |
|-----------|-------|-----------|-------------------|-----------------|
| **Glucose/Entries** | `BloodGlucose` | UUID string | Via conversion | `/api/v1/entries.json` |
| **Treatments** | `NightscoutTreatment` | UUID string (from `id`) | Optional field | `/api/v1/treatments.json` |
| **Carbs** | `NightscoutTreatment` | UUID string | N/A (mapped from id) | `/api/v1/treatments.json` |
| **Manual Glucose** | `NightscoutTreatment` | UUID string | N/A (mapped from id) | `/api/v1/treatments.json` |
| **DeviceStatus** | `NightscoutStatus` | N/A (no _id) | N/A | `/api/v1/devicestatus.json` |

**Evidence:**

- **Entries** - `Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift:340-374`
  ```swift
  func uploadGlucose(_ glucose: [BloodGlucose]) async throws {
      // uploads to /api/v1/entries.json
      let encodedBody = try JSONCoding.encoder.encode(glucose)
  }
  ```

- **Treatments** - `Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift:299-338`
  ```swift
  func uploadTreatments(_ treatments: [NightscoutTreatment]) async throws {
      // uploads to /api/v1/treatments.json
      let encodedBody = try JSONCoding.encoder.encode(treatments)
  }
  ```

- **DeviceStatus** - `Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift:376-409`
  ```swift
  func uploadDeviceStatus(_ status: NightscoutStatus) async throws {
      // uploads to /api/v1/devicestatus.json
      let encodedBody = try JSONCoding.encoder.encode(status)
      // NightscoutStatus has NO _id field
  }
  ```

### 4. **How does Trio handle sync identity and deduplication?**

**Answer: Multi-level approach using UUIDs, uploaded flags, and syncIdentifier**

Trio employs a sophisticated deduplication strategy:

1. **CoreData UUID Storage**: Each record stores a `UUID?` in CoreData
2. **Upload Flag Tracking**: Records marked `isUploadedToNS` are skipped
3. **SyncIdentifier Mapping**: UUID converted to string for LoopKit's sync system
4. **Predicate-based Filtering**: Only fetch records not yet marked as uploaded

**Evidence:**

- **CoreData Models** - `Trio/Model/Classes+Properties/`
  ```swift
  // CarbEntryStored+CoreDataProperties.swift
  @NSManaged var id: UUID?
  @NSManaged var isUploadedToNS: Bool
  
  // GlucoseStored+CoreDataProperties.swift
  @NSManaged var id: UUID?
  @NSManaged var isUploadedToNS: Bool
  
  // PumpEventStored+CoreDataProperties.swift
  @NSManaged var id: String?
  @NSManaged var isUploadedToNS: Bool
  ```

- **Predicate Filtering** - `Trio/Model/Helper/CarbEntryStored+helper.swift:20-27`
  ```swift
  static var carbsNotYetUploadedToNightscout: NSPredicate {
      let date = Date.oneDayAgo
      return NSPredicate(
          format: "date >= %@ AND isUploadedToNS == %@ AND isFPU == %@ AND carbs > 0",
          date as NSDate,
          false as NSNumber,  // ← Only fetch records NOT yet uploaded
          false as NSNumber
      )
  }
  ```

- **Post-Upload Flag Update** - `Trio/Sources/Services/Network/Nightscout/NightscoutManager.swift:1022-1042`
  ```swift
  private func updateCarbsAsUploaded(_ treatments: [NightscoutTreatment]) async {
      await backgroundContext.perform {
          let ids = treatments.map(\.id) as NSArray
          let fetchRequest: NSFetchRequest<CarbEntryStored> = CarbEntryStored.fetchRequest()
          fetchRequest.predicate = NSPredicate(format: "id IN %@", ids)
          
          do {
              let results = try self.backgroundContext.fetch(fetchRequest)
              for result in results {
                  result.isUploadedToNS = true  // ← Mark as uploaded
              }
              try self.backgroundContext.save()
          }
      }
  }
  ```

### 5. **What would be the impact of MongoDB's UUID_HANDLING quirk on Trio?**

**Answer: Minimal impact due to explicit UUID string encoding**

MongoDB's UUID_HANDLING behavior affects how BinData(4) binary UUIDs are compared with string representations. However:

**Trio's approach is resilient because:**

1. **Trio always sends UUID strings**, not binary data
2. The `_id` field is a string (`UUID().uuidString`), not a BinData representation
3. MongoDB stores these as simple strings, not BinData subtypes

**Potential issues only if:**
- **Cross-system deduplication needed**: If Nightscout receives entries with binary UUIDs from other sources (e.g., AndroidAPS) alongside Trio's string UUIDs, duplication could occur
- **Query comparison**: Direct MongoDB queries comparing Trio's `_id` strings against converted BinData values would fail

**Evidence:**
- BloodGlucose encoding: `Trio/Sources/Models/BloodGlucose.swift:117`
  ```swift
  _id: String = UUID().uuidString  // ← Always a string, never binary
  ```

- Standard JSONEncoder: `Trio/Sources/Helpers/JSON.swift:84-89`
  ```swift
  static var encoder: JSONEncoder {
      let encoder = JSONEncoder()
      encoder.outputFormatting = [.prettyPrinted, .withoutEscapingSlashes]
      encoder.dateEncodingStrategy = .customISO8601
      // ← Default string encoding for UUID
      return encoder
  }
  ```

**Recommendation**: Ensure Nightscout's UUID comparison logic treats string UUIDs and binary UUIDs as equivalent, or standardize on one format across all integrations.

### 6. **Does Trio inherit patterns from Loop/NightscoutKit or have its own implementation?**

**Answer: Hybrid approach - uses LoopKit for sync but has custom Nightscout integration**

**Key Differences:**

| Aspect | Trio | NightscoutKit (Loop) |
|--------|------|-------------------|
| **`_id` field** | UUID string (always sent) | Optional; sent if provided |
| **`syncIdentifier`** | Used as LoopKit sync identifier | Separate field in dictionary representation |
| **Treatment model** | Flat `NightscoutTreatment` structure | Polymorphic type hierarchy (Bolus, Carb, TempBasal) |
| **Encoding strategy** | Standard JSONEncoder with ISO8601 dates | DictionaryRepresentable protocol |
| **Upload pipeline** | Event-driven throttled pipeline | Direct method calls |

**Evidence:**

- **NightscoutKit (Loop) approach** - `externals/NightscoutKit/Sources/NightscoutKit/Models/Treatments/NightscoutTreatment.swift:73-120`
  ```swift
  public class NightscoutTreatment: DictionaryRepresentable {
      public let id: String?  // ← Optional
      public let syncIdentifier: String?  // ← Separate field
      
      public var dictionaryRepresentation: [String: Any] {
          var rval = [
              "created_at": TimeFormat.timestampStrFromDate(timestamp),
              ...
          ]
          rval["_id"] = id  // ← Only included if set
          rval["syncIdentifier"] = syncIdentifier  // ← Explicitly added
          return rval
      }
  }
  ```

- **Trio approach** - `Trio/Sources/Models/NightscoutTreatment.swift:40-65`
  ```swift
  struct NightscoutTreatment: JSON, Hashable, Equatable {
      var id: String?  // ← Optional, maps to "_id" via CodingKeys
      // NO separate syncIdentifier field
      
      private enum CodingKeys: String, CodingKey {
          case id  // ← Simple mapping, no explicit "_id"
          ...
      }
  }
  ```

**LoopKit Integration:**
- Trio uses `StoredGlucoseSample` (LoopKit type): `Trio/Sources/Models/BloodGlucose.swift:281-289`
  ```swift
  func convertStoredGlucoseSample(isManualGlucose: Bool) -> StoredGlucoseSample {
      StoredGlucoseSample(
          syncIdentifier: id,  // ← Passes Trio's UUID string to LoopKit
          startDate: dateString.date,
          ...
      )
  }
  ```

---

## Data Flow Summary

### Carbs Upload Flow
```
CarbEntryStored (CoreData)
  ↓ id: UUID?
  ↓ isUploadedToNS: Bool
  └→ getCarbsNotYetUploadedToNightscout()
      ↓
      ├→ NightscoutTreatment {
      │    id: result.id?.uuidString  // UUID→String
      │    eventType: .nsCarbCorrection
      │    ...
      │  }
      │
      └→ uploadTreatments([NightscoutTreatment])
          ↓
          JSONEncoder
          ↓
          POST /api/v1/treatments.json
          ↓
          {"id": "550e8400-e29b-41d4-a716-446655440000", ...}
          ↓
          updateCarbsAsUploaded() → isUploadedToNS = true
```

### Glucose Upload Flow
```
GlucoseStored (CoreData)
  ↓ id: UUID?
  ↓ isUploadedToNS: Bool
  └→ getGlucoseNotYetUploadedToNightscout()
      ↓
      ├→ BloodGlucose {
      │    _id: result.id?.uuidString ?? UUID().uuidString
      │    sgv: Int(result.glucose)
      │    ...
      │  }
      │
      └→ uploadGlucose([BloodGlucose])
          ↓
          JSONEncoder (Codable)
          ↓
          POST /api/v1/entries.json
          ↓
          {"_id": "550e8400-e29b-41d4-a716-446655440000", "sgv": 145, ...}
          ↓
          updateGlucoseAsUploaded() → isUploadedToNS = true
```

### LoopKit Sync Flow
```
BloodGlucose._id (UUID string)
  ↓
  convertStoredGlucoseSample()
  ↓
  StoredGlucoseSample.syncIdentifier = _id
  ↓
  LoopKit's sync deduplication system
```

---

## Key Patterns and Implementation Details

### 1. **UUID Generation Strategy**

- **Default generation**: `UUID().uuidString` at time of creation
- **Persistence**: Stored in CoreData as `UUID?` type
- **Conversion**: `?.uuidString` to convert to string for API upload
- **Fallback**: `?? UUID().uuidString` generates new UUID if missing

### 2. **Upload Pipeline Architecture**

- **Throttled requests**: Separate `PassthroughSubject` per pipeline
- **Deduplication**: Throttle window prevents double-uploads
- **Batching**: Records uploaded in chunks of 100

**Code**: `Trio/Sources/Services/Network/Nightscout/NightscoutManager.swift:62-102`

### 3. **Encoding Strategy**

- **Standard Swift Codable**: Uses `@NSManaged` properties
- **Custom CodingKeys**: Maps Swift property names to Nightscout field names
- **ISO8601 dates**: Custom date encoding with fractional seconds
- **No special UUID handling**: UUID encodes as standard string

### 4. **Collection-specific Behaviors**

| Collection | eventType Examples | `_id` Required? |
|-----------|---|---|
| Carbs | `.nsCarbCorrection` | Yes (required) |
| Bolus | `.bolusCorrection`, `.mealBolus`, `.smbBolus` | Yes (required) |
| Temp Basal | `.nsTempBasal` | Yes (required) |
| Manual Glucose | `.capillaryGlucose` | Yes (required) |
| DeviceStatus | N/A | No (`_id` not present) |

---

## File Reference Guide

### Core API Implementation
- **NightscoutAPI.swift**: Upload methods for all collections
  - `uploadTreatments()`: line 299-338
  - `uploadGlucose()`: line 340-374
  - `uploadDeviceStatus()`: line 376-409

### Data Models
- **BloodGlucose.swift**: Glucose entry model with UUID handling
- **NightscoutTreatment.swift**: Treatment base model
- **CarbsEntry.swift**: Carb entry model
- **TempTarget.swift**: Temp target model

### Storage & Sync
- **GlucoseStorage.swift**: Glucose fetch and conversion (line 400-475)
- **CarbsStorage.swift**: Carbs fetch and conversion (line 350-427)
- **PumpHistoryStorage.swift**: Pump event fetch and conversion (line 303-427)

### CoreData Models
- **CarbEntryStored+CoreDataProperties.swift**: `id: UUID?`
- **GlucoseStored+CoreDataProperties.swift**: `id: UUID?`
- **PumpEventStored+CoreDataProperties.swift**: `id: String?`

### Helpers
- **JSON.swift**: JSONEncoder/Decoder configuration

---

## Nightscout Payload Examples

### Glucose Entry Upload
```json
{
  "_id": "550e8400-e29b-41d4-a716-446655440000",
  "type": "sgv",
  "sgv": 145,
  "date": 1700000000000,
  "dateString": "2023-11-15T10:00:00.000Z",
  "direction": "Flat",
  "device": "Trio"
}
```

### Carb Correction Upload
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "eventType": "Carb Correction",
  "created_at": "2023-11-15T10:00:00.000Z",
  "timestamp": "2023-11-15T10:00:00.000Z",
  "carbs": 30,
  "fat": 10,
  "protein": 5,
  "enteredBy": "Trio",
  "notes": "Lunch"
}
```

### Bolus Upload
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440002",
  "eventType": "Correction Bolus",
  "created_at": "2023-11-15T10:00:00.000Z",
  "timestamp": "2023-11-15T10:00:00.000Z",
  "insulin": 2.5,
  "enteredBy": "Trio"
}
```

---

## Potential Issues and Recommendations

### Issue 1: UUID vs ObjectId Mismatch
- **Impact**: If Nightscout expects MongoDB ObjectIds, Trio's UUIDs will not be recognized as valid IDs
- **Recommendation**: Verify Nightscout accepts string UUIDs in `_id` field

### Issue 2: Missing syncIdentifier in NightscoutTreatment
- **Impact**: Unlike NightscoutKit (Loop), Trio's treatment model doesn't have explicit `syncIdentifier` field for upload
- **Current workaround**: Used only for LoopKit conversion, not Nightscout upload
- **Recommendation**: If Nightscout needs syncIdentifier, add it to NightscoutTreatment model

### Issue 3: DeviceStatus lacks _id
- **Impact**: DeviceStatus documents won't have `_id` field, MongoDB will auto-generate
- **Recommendation**: Add `_id` field to DeviceStatus if deduplication needed

### Issue 4: Upload Flag Persistence
- **Impact**: If app crashes between upload and flag update, records could duplicate on retry
- **Recommendation**: Use transactional updates or implement idempotency at Nightscout level

---

## Summary Table: `_id` Field Behavior

| Aspect | Value | Notes |
|--------|-------|-------|
| **Type** | UUID String | `"550e8400-e29b-41d4-a716-446655440000"` |
| **Source** | CoreData `id: UUID?` | Converted to string via `.uuidString` |
| **Format** | RFC 4122 compliant | Standard UUID format |
| **Default** | `UUID().uuidString` | Generated if missing |
| **Encoding** | JSON string | Via standard Codable |
| **Present in Glucose** | Yes | Via `_id` CodingKey |
| **Present in Treatments** | Yes | Via `id` property (maps to `_id`) |
| **Present in DeviceStatus** | No | N/A |
| **Sync Integration** | Via `syncIdentifier` | Passed to LoopKit |
| **Deduplication** | Upload flag + UUID | Two-level approach |

