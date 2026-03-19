# Trio iOS App: `_id` Field Technical Deep Dive

## Architecture Overview

Trio's `_id` field implementation is part of a three-tier identification system:

```
┌─────────────────────────────────────────────────────┐
│              Application Layer                       │
│  (Trio UI, calculations, loop decisions)            │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│              Storage Layer (CoreData)                │
│  • CarbEntryStored.id: UUID?                        │
│  • GlucoseStored.id: UUID?                          │
│  • PumpEventStored.id: String?                      │
│  • isUploadedToNS: Bool (dedup flag)                │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│           Sync & Conversion Layer                    │
│  • UUID → String conversion                         │
│  • NightscoutTreatment/BloodGlucose construction    │
│  • syncIdentifier assignment (LoopKit)             │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│          Upload & Network Layer                      │
│  • JSONEncoder.encode()                             │
│  • "_id" field in JSON payload                      │
│  • POST to Nightscout API                           │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│              Nightscout (MongoDB)                    │
│  • _id: ObjectId or String (Trio sends String)      │
│  • Document storage and indexing                    │
└─────────────────────────────────────────────────────┘
```

---

## Code Level Details

### 1. CoreData Model Definition

**File**: `Trio/Model/Classes+Properties/GlucoseStored+CoreDataProperties.swift`
```swift
public extension GlucoseStored {
    @nonobjc class func fetchRequest() -> NSFetchRequest<GlucoseStored> {
        NSFetchRequest<GlucoseStored>(entityName: "GlucoseStored")
    }

    @NSManaged var date: Date?
    @NSManaged var direction: String?
    @NSManaged var glucose: Int16
    @NSManaged var id: UUID?               // ← Primary identifier
    @NSManaged var isManual: Bool
    @NSManaged var isUploadedToNS: Bool    // ← Dedup flag
    @NSManaged var isUploadedToHealth: Bool
    @NSManaged var isUploadedToTidepool: Bool
}
```

**Key Points**:
- `id` is optional (`UUID?`) to support migration and manual entries
- `isUploadedToNS` acts as a soft-delete/dedup flag
- Four upload target flags allow independent sync with different systems

### 2. Data Model (Encoding)

**File**: `Trio/Sources/Models/BloodGlucose.swift`
```swift
struct BloodGlucose: JSON, Identifiable, Hashable, Codable {
    enum CodingKeys: String, CodingKey {
        case _id              // ← Direct "_id" JSON key
        case idKey = "id"     // ← Fallback from older format
        case sgv
        case direction
        case date
        case dateString
        // ... other fields
    }

    // Constructor with default UUID
    init(
        _id: String = UUID().uuidString,  // ← Default generation
        sgv: Int? = nil,
        direction: Direction? = nil,
        date: Decimal,
        dateString: Date,
        // ... other params
    ) {
        self._id = _id
        self.sgv = sgv
        // ... initialize other fields
    }

    // Dual decoding: try "_id" first, then "id"
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        
        if let idValue = try container.decodeIfPresent(String.self, forKey: ._id) {
            _id = idValue
        } else {
            _id = try container.decode(String.self, forKey: .idKey)
        }
        
        // ... decode other fields
    }

    var _id: String?
    var id: String {
        _id ?? UUID().uuidString  // ← Fallback at property access
    }
}
```

**Key Points**:
- Dual CodingKey support for backward compatibility
- Lazy fallback UUID generation at property access
- Clean separation of `_id` (Nightscout) vs `id` (Swift property)

### 3. Storage Fetch & Conversion

**File**: `Trio/Sources/APS/Storage/GlucoseStorage.swift:400-429`
```swift
func getGlucoseNotYetUploadedToNightscout() async throws -> [BloodGlucose] {
    // Step 1: Fetch from CoreData with predicate
    let results = try await CoreDataStack.shared.fetchEntitiesAsync(
        ofType: GlucoseStored.self,
        onContext: context,
        predicate: NSPredicate.glucoseNotYetUploadedToNightscout,
        key: "date",
        ascending: false
    )

    // Step 2: Transform CoreData → Swift Model
    return try await context.perform {
        guard let fetchedResults = results as? [GlucoseStored] else {
            throw CoreDataError.fetchError(function: #function, file: #file)
        }

        // Step 3: Map UUID → String for upload
        return fetchedResults.map { result in
            BloodGlucose(
                _id: result.id?.uuidString ?? UUID().uuidString,  // ← Conversion
                sgv: Int(result.glucose),
                direction: BloodGlucose.Direction(from: result.direction ?? ""),
                date: Decimal(result.date?.timeIntervalSince1970 ?? Date().timeIntervalSince1970) * 1000,
                dateString: result.date ?? Date(),
                unfiltered: Decimal(result.glucose),
                filtered: Decimal(result.glucose),
                noise: nil,
                glucose: Int(result.glucose),
                type: "sgv"
            )
        }
    }
}
```

**Key Points**:
- Three-step process: Fetch → Guard → Map
- UUID to String conversion happens in map closure
- Fallback UUID generation if CoreData id is nil
- Async context handling for thread safety

### 4. Manual Glucose Treatment Conversion

**File**: `Trio/Sources/APS/Storage/GlucoseStorage.swift:433-475`
```swift
func getManualGlucoseNotYetUploadedToNightscout() async throws -> [NightscoutTreatment] {
    let results = try await CoreDataStack.shared.fetchEntitiesAsync(
        ofType: GlucoseStored.self,
        onContext: context,
        predicate: NSPredicate.manualGlucoseNotYetUploadedToNightscout,
        key: "date",
        ascending: false
    )

    return try await context.perform {
        guard let fetchedResults = results as? [GlucoseStored] else {
            throw CoreDataError.fetchError(function: #function, file: #file)
        }

        return fetchedResults.map { result in
            NightscoutTreatment(
                duration: nil,
                rawDuration: nil,
                rawRate: nil,
                absolute: nil,
                rate: nil,
                eventType: .capillaryGlucose,        // ← Special event type
                createdAt: result.date,
                enteredBy: CarbsEntry.local,
                bolus: nil,
                insulin: nil,
                notes: "Trio User",
                carbs: nil,
                fat: nil,
                protein: nil,
                foodType: nil,
                targetTop: nil,
                targetBottom: nil,
                glucoseType: "Manual",               // ← Distinguishes from CGM
                glucose: self.settingsManager.settings.units == .mgdL 
                    ? (self.glucoseFormatter.string(from: Int(result.glucose) as NSNumber) ?? "")
                    : (self.glucoseFormatter.string(from: Decimal(result.glucose).asMmolL as NSNumber) ?? ""),
                units: self.settingsManager.settings.units == .mmolL ? "mmol" : "mg/dl",
                id: result.id?.uuidString             // ← Treatment uses 'id' field
            )
        }
    }
}
```

**Key Points**:
- NightscoutTreatment uses `id` field (different model than BloodGlucose)
- Unit conversion applied based on settings
- `glucoseType: "Manual"` distinguishes from CGM readings

### 5. Treatment Model Definition

**File**: `Trio/Sources/Models/NightscoutTreatment.swift`
```swift
struct NightscoutTreatment: JSON, Hashable, Equatable {
    var duration: Int?
    // ... many fields ...
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
    var id: String?        // ← Maps to "_id" in JSON
    var fpuID: String?

    static let local = "Trio"

    static func == (lhs: NightscoutTreatment, rhs: NightscoutTreatment) -> Bool {
        (lhs.createdAt ?? Date()) == (rhs.createdAt ?? Date())
    }

    func hash(into hasher: inout Hasher) {
        hasher.combine(createdAt ?? Date())
    }
}

extension NightscoutTreatment {
    private enum CodingKeys: String, CodingKey {
        case duration
        case rawDuration = "raw_duration"
        // ... many mappings ...
        case carbs
        case fat
        case protein
        case foodType
        // ... other fields ...
        case id            // ← Simple mapping (no explicit "_id")
        case fpuID
    }
}
```

**Key Points**:
- `id` field is `String?` (not UUID)
- Equality based on `createdAt` timestamp
- Hashing also uses timestamp
- No explicit `syncIdentifier` field in model

### 6. JSONEncoder Configuration

**File**: `Trio/Sources/Helpers/JSON.swift:83-96`
```swift
enum JSONCoding {
    static var encoder: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .withoutEscapingSlashes]
        encoder.dateEncodingStrategy = .customISO8601  // ← Custom date format
        return encoder
    }

    static var decoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .customISO8601  // ← Match encoder
        return decoder
    }
}
```

**Key Points**:
- Pretty-printed JSON for debugging
- No escaping of slashes (important for URLs in notes)
- Custom ISO8601 date format (likely with fractional seconds)
- Consistent encoder/decoder pair

### 7. Upload Methods

**File**: `Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift`

#### Glucose Upload
```swift
func uploadGlucose(_ glucose: [BloodGlucose]) async throws {
    var components = URLComponents()
    components.scheme = url.scheme
    components.host = url.host
    components.port = url.port
    components.path = Config.uploadEntriesPath  // ← /api/v1/entries.json

    var request = URLRequest(url: components.url!)
    request.allowsConstrainedNetworkAccess = false
    request.timeoutInterval = Config.timeout
    request.addValue("application/json", forHTTPHeaderField: "Content-Type")

    if let secret = secret {
        request.addValue(secret.sha1(), forHTTPHeaderField: "api-secret")
    }

    do {
        let encodedBody = try JSONCoding.encoder.encode(glucose)  // ← Codable
        request.httpBody = encodedBody
    } catch {
        debugPrint("Error encoding payload: \(error)")
        throw error
    }

    request.httpMethod = "POST"

    let (_, response) = try await URLSession.shared.data(for: request)

    guard let httpResponse = response as? HTTPURLResponse, 200 ..< 300 ~= httpResponse.statusCode else {
        throw URLError(.badServerResponse)
    }
}
```

#### Treatment Upload
```swift
func uploadTreatments(_ treatments: [NightscoutTreatment]) async throws {
    var components = URLComponents()
    components.scheme = url.scheme
    components.host = url.host
    components.port = url.port
    components.path = Config.treatmentsPath  // ← /api/v1/treatments.json

    guard let requestURL = components.url else {
        throw URLError(.badURL)
    }

    var request = URLRequest(url: requestURL)
    request.allowsConstrainedNetworkAccess = false
    request.timeoutInterval = Config.timeout
    request.addValue("application/json", forHTTPHeaderField: "Content-Type")

    if let secret = secret {
        request.addValue(secret.sha1(), forHTTPHeaderField: "api-secret")
    }

    do {
        let encodedBody = try JSONCoding.encoder.encode(treatments)
        request.httpBody = encodedBody
    } catch {
        debugPrint("Error encoding payload: \(error)")
        throw error
    }

    request.httpMethod = "POST"

    let (_, response) = try await URLSession.shared.data(for: request)

    guard let httpResponse = response as? HTTPURLResponse, 200 ..< 300 ~= httpResponse.statusCode else {
        throw URLError(.badServerResponse)
    }
}
```

**Key Points**:
- Both use standard JSON encoding (Codable)
- Different endpoints (entries vs treatments)
- API secret hashing (SHA1)
- Simple status code validation

### 8. Deduplication & Upload Tracking

**File**: `Trio/Sources/Services/Network/Nightscout/NightscoutManager.swift:884-904`
```swift
private func updateGlucoseAsUploaded(_ glucose: [BloodGlucose]) async {
    await backgroundContext.perform {
        // Extract IDs from uploaded records
        let ids = glucose.map(\.id) as NSArray  // ← Get _id values
        
        let fetchRequest: NSFetchRequest<GlucoseStored> = GlucoseStored.fetchRequest()
        fetchRequest.predicate = NSPredicate(format: "id IN %@", ids)  // ← Match by UUID

        do {
            let results = try self.backgroundContext.fetch(fetchRequest)
            for result in results {
                result.isUploadedToNS = true  // ← Set dedup flag
            }

            guard self.backgroundContext.hasChanges else { return }
            try self.backgroundContext.save()  // ← Persist to CoreData
        } catch let error as NSError {
            debugPrint(
                "\(DebuggingIdentifiers.failed) \(#file) \(#function) Failed to update isUploadedToNS: \(error.userInfo)"
            )
        }
    }
}
```

**Key Points**:
- Matches CoreData records by UUID `id` field
- Sets `isUploadedToNS = true` flag
- Runs on background context for thread safety
- Saves immediately after marking

### 9. Predicate for Upload Filtering

**File**: `Trio/Model/Helper/GlucoseStored+helper.swift`
```swift
extension NSPredicate {
    static var glucoseNotYetUploadedToNightscout: NSPredicate {
        NSPredicate(
            format: "date >= %@ AND isUploadedToNS == %@",
            Date.oneDayAgo as NSDate,
            false as NSNumber  // ← Filter: isUploadedToNS == false
        )
    }
}
```

**Key Points**:
- Fetches only records with `isUploadedToNS == false`
- Time-filters to 1-day window
- Used in `getGlucoseNotYetUploadedToNightscout()`

### 10. LoopKit Sync Integration

**File**: `Trio/Sources/Models/BloodGlucose.swift:281-289`
```swift
extension BloodGlucose {
    func convertStoredGlucoseSample(isManualGlucose: Bool) -> StoredGlucoseSample {
        StoredGlucoseSample(
            syncIdentifier: id,  // ← Pass _id as syncIdentifier
            startDate: dateString.date,
            quantity: HKQuantity(unit: .milligramsPerDeciliter, doubleValue: Double(glucose!)),
            wasUserEntered: isManualGlucose,
            device: HKDevice.local()
        )
    }
}
```

**File**: `Trio/Sources/Models/CarbsEntry.swift:44-62`
```swift
extension CarbsEntry {
    func convertSyncCarb(operation: LoopKit.Operation = .create) -> SyncCarbObject {
        SyncCarbObject(
            absorptionTime: nil,
            createdByCurrentApp: true,
            foodType: nil,
            grams: Double(carbs),
            startDate: createdAt,
            uuid: UUID(uuidString: id!),  // ← Convert string back to UUID
            provenanceIdentifier: enteredBy ?? "Trio",
            syncIdentifier: id,           // ← Pass id as syncIdentifier
            syncVersion: nil,
            userCreatedDate: nil,
            userUpdatedDate: nil,
            userDeletedDate: nil,
            operation: operation,
            addedDate: nil,
            supercededDate: nil
        )
    }
}
```

**Key Points**:
- `syncIdentifier` is the Nightscout `_id` value (UUID string)
- UUID string is converted back to UUID for LoopKit
- LoopKit uses this for cross-system deduplication

---

## Data Flow Diagrams

### Complete Carb Upload Flow
```
User enters carb in Trio UI
    ↓
CarbEntryStored created in CoreData
    • id: UUID() generated by iOS
    • date: Date()
    • carbs: Decimal
    • isUploadedToNS: false
    ↓
Upload pipeline triggered
    ↓
carbsStorage.getCarbsNotYetUploadedToNightscout()
    ├─ Query: NSPredicate.carbsNotYetUploadedToNightscout
    │  (date >= 1 day ago, isUploadedToNS == false, isFPU == false, carbs > 0)
    │
    └─ Map each CarbEntryStored:
        NightscoutTreatment {
            id: result.id?.uuidString,        // ← UUID→String
            eventType: .nsCarbCorrection,
            createdAt: result.date,
            carbs: Decimal(result.carbs),
            enteredBy: "Trio",
            ...
        }
    ↓
uploadTreatments([NightscoutTreatment])
    ├─ JSONCoding.encoder.encode(treatments)
    │  {
    │    "id": "550e8400-e29b-41d4-a716-446655440000",
    │    "eventType": "Carb Correction",
    │    "created_at": "2023-11-15T10:00:00.000Z",
    │    "carbs": 30,
    │    "enteredBy": "Trio",
    │    ...
    │  }
    │
    └─ POST /api/v1/treatments.json
        ↓
        Nightscout API (/api/v1/treatments.json)
        ├─ Save to MongoDB
        │  (_id: 550e8400-e29b-41d4-a716-446655440000)
        │
        └─ Return 200 OK
    ↓
updateCarbsAsUploaded(treatments)
    ├─ Query CoreData for id IN [550e8400...]
    ├─ Set isUploadedToNS = true
    └─ Save CoreData
    ↓
SUCCESS: Carb marked as uploaded
```

### Glucose Upload to LoopKit Flow
```
CGM sends glucose reading
    ↓
GlucoseStored created in CoreData
    • id: UUID() generated
    • glucose: Int16
    • date: Date()
    ↓
Glucose upload pipeline
    ↓
glucoseStorage.getGlucoseNotYetUploadedToNightscout()
    ├─ Map GlucoseStored → BloodGlucose
    │  _id: result.id?.uuidString ?? UUID().uuidString
    │
    └─ uploadGlucose([BloodGlucose])
        ├─ JSONCoding.encoder.encode(glucose)
        │  {
        │    "_id": "550e8400-e29b-41d4-a716-446655440000",
        │    "type": "sgv",
        │    "sgv": 145,
        │    "dateString": "2023-11-15T10:00:00.000Z",
        │    ...
        │  }
        │
        └─ POST /api/v1/entries.json
            ↓
            Nightscout stores glucose
    ↓
updateGlucoseAsUploaded(glucose)
    ├─ Set isUploadedToNS = true
    └─ Save CoreData
    ↓
PARALLEL: Convert to LoopKit
    ├─ glucose.convertStoredGlucoseSample()
    │  syncIdentifier: "550e8400-e29b-41d4-a716-446655440000"
    │
    └─ LoopKit deduplication system
        (LoopKit checks syncIdentifier to prevent duplicates)
    ↓
SUCCESS: Glucose available to LoopKit & Nightscout
```

---

## Comparison with NightscoutKit (Loop)

**NightscoutKit Model** (Trio's comparison reference):
```swift
public class NightscoutTreatment {
    public let id: String?
    public let syncIdentifier: String?
    
    public var dictionaryRepresentation: [String: Any] {
        var rval = [...]
        rval["_id"] = id              // ← Only if present
        rval["syncIdentifier"] = syncIdentifier  // ← Explicit
        return rval
    }
}
```

**Trio's Approach**:
```swift
struct NightscoutTreatment {
    var id: String?  // ← Always included in encoding
    // NO explicit syncIdentifier field
    
    private enum CodingKeys: String, CodingKey {
        case id  // ← Simple mapping
    }
}
```

**Key Differences**:
1. **Optional vs Explicit**: Loop makes `_id` optional; Trio always sends it
2. **syncIdentifier**: Loop explicitly includes it; Trio omits from Nightscout payload
3. **Encoding**: Loop uses `DictionaryRepresentable`; Trio uses `Codable`
4. **Type safety**: Trio uses Swift `Codable`; Loop builds dictionaries manually

---

## Potential Compatibility Issues

### Issue 1: Missing syncIdentifier in Nightscout Payload
**Status**: By design  
**Impact**: If Nightscout needs to read Trio's syncIdentifier, it won't find it  
**Mitigation**: Add syncIdentifier to NightscoutTreatment model if needed

### Issue 2: String UUID vs Binary UUID
**Status**: Trio sends strings; Nightscout might expect binary  
**Impact**: MongoDB comparison queries might fail  
**Mitigation**: Ensure Nightscout treats string UUIDs as primary IDs

### Issue 3: DeviceStatus without _id
**Status**: By design  
**Impact**: Can't deduplicate DeviceStatus by ID  
**Mitigation**: Use timestamp-based dedup or add _id field

### Issue 4: Type Inconsistency in CoreData
**Status**: PumpEventStored uses String; others use UUID  
**Impact**: Inconsistent handling at fetch layer  
**Mitigation**: Standardize on UUID type, convert at usage boundary

---

## Performance Considerations

1. **UUID Generation**: `UUID().uuidString` is fast (microseconds)
2. **JSON Encoding**: Codable encoding adds minimal overhead
3. **Deduplication**: CoreData predicate filtering is efficient
4. **Batch Uploads**: Chunking at 100 records optimizes bandwidth
5. **Async/Await**: Non-blocking upload keeps UI responsive

---

## Testing Strategy

### Unit Tests
- UUID string format validation (RFC 4122)
- JSON encoding/decoding round-trip
- CoreData predicate accuracy

### Integration Tests
- End-to-end upload flow
- Deduplication flag update
- Multiple collection types

### System Tests
- UUID uniqueness across multiple runs
- Nightscout deduplication
- LoopKit sync integration

