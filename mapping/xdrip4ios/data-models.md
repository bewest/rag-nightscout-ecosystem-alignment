# xDrip4iOS Data Models

This document maps xDrip4iOS's Swift data models to Nightscout collections, showing how a native iOS CGM app structures and uploads data.

**See also**: [profile-handling.md](profile-handling.md) for detailed NightscoutProfile parsing.

---

## BgReading → entries Collection

Represents glucose readings from CGM sensors.

### Upload Format

```swift
// xdrip:xdrip/Managers/Nightscout/BgReading+Nightscout.swift#L6-L22
func dictionaryRepresentationForNightscoutUpload() -> [String: Any] {
    return [
        "_id": id,
        "device": deviceName ?? "",
        "date": timeStamp.toMillisecondsAsInt64(),
        "dateString": timeStamp.ISOStringFromDate(),
        "type": "sgv",
        "sgv": Int(calculatedValue.round(toDecimalPlaces: 0)),
        "direction": slopeName,
        "filtered": ageAdjustedRawValue * 1000,    // or calculatedValue * 1000
        "unfiltered": ageAdjustedRawValue * 1000,  // or calculatedValue * 1000
        "noise": 1,
        "sysTime": timeStamp.ISOStringFromDate()
    ]
}
```

### Field Mapping

| Swift Field | NS Field | Type | Notes |
|-------------|----------|------|-------|
| `id` | `_id` | String | UUID generated locally |
| `deviceName` | `device` | String | Transmitter name |
| `timeStamp` | `date` | Int64 | Epoch milliseconds |
| `timeStamp` | `dateString` | String | ISO 8601 format |
| (hardcoded) | `type` | String | Always `"sgv"` |
| `calculatedValue` | `sgv` | Int | Rounded glucose value |
| `slopeName` | `direction` | String | Trend arrow name |
| `ageAdjustedRawValue` | `filtered` | Double | Raw * 1000 (or calculatedValue * 1000) |
| `ageAdjustedRawValue` | `unfiltered` | Double | Raw * 1000 (or calculatedValue * 1000) |
| (hardcoded) | `noise` | Int | Always `1` |
| `timeStamp` | `sysTime` | String | ISO 8601 format |

### Direction (slopeName) Values

The `slopeName` property maps calculated slope to NS direction strings:

| Slope Range | Direction String |
|-------------|-----------------|
| slope > 3.5 | "DoubleUp" |
| slope > 2.0 | "SingleUp" |
| slope > 1.0 | "FortyFiveUp" |
| slope > -1.0 | "Flat" |
| slope > -2.0 | "FortyFiveDown" |
| slope > -3.5 | "SingleDown" |
| slope <= -3.5 | "DoubleDown" |

---

## Calibration → entries Collection

Calibration data is uploaded as two separate entries: `cal` (calibration record) and `mbg` (manual BG).

### Calibration Record Upload (type: "cal")

```swift
// xdrip:xdrip/Managers/Nightscout/Calibration+Nightscout.swift#L14-L28
var dictionaryRepresentationForCalRecordNightscoutUpload: [String: Any] {
    return [
        "_id": id,
        "device": deviceName ?? "",
        "date": timeStamp.toMillisecondsAsInt64(),
        "dateString": timeStamp.ISOStringFromDate(),
        "type": "cal",
        "sysTime": timeStamp.ISOStringFromDate(),
        "slope": slope != 0 ? 1000 / slope : 0,
        "intercept": slope != 0 ? -(intercept * 1000) / slope : 0,
        "scale": 1
    ]
}
```

### Manual BG Record Upload (type: "mbg")

```swift
// xdrip:xdrip/Managers/Nightscout/Calibration+Nightscout.swift#L31-L43
var dictionaryRepresentationForMbgRecordNightscoutUpload: [String: Any] {
    return [
        "_id": UniqueId.createEventId(),  // Different ID from cal record
        "device": deviceName ?? "",
        "date": timeStamp.toMillisecondsAsInt64(),
        "dateString": timeStamp.ISOStringFromDate(),
        "type": "mbg",
        "mbg": bg,
        "sysTime": timeStamp.ISOStringFromDate()
    ]
}
```

### Slope/Intercept Transformation

xDrip4iOS transforms local calibration values for NS upload:

```swift
NS_slope = 1000 / local_slope
NS_intercept = -(local_intercept * 1000) / local_slope
```

This converts from xDrip4iOS's internal calibration format to Nightscout's expected format.

---

## TreatmentEntry → treatments Collection

Represents therapy events (bolus, carbs, etc.).

### Core Data Model

```swift
// xdrip:xdrip/Core Data/classes/TreatmentEntry+CoreDataClass.swift#L106-L141
public class TreatmentEntry: NSManagedObject {
    var id: String              // NS _id + type extension (e.g., "-insulin")
    var date: Date              // Treatment timestamp
    var value: Double           // Primary value (units, grams, minutes)
    var valueSecondary: Double  // Secondary value (e.g., duration for basal)
    var treatmentType: TreatmentType
    var uploaded: Bool          // Sync status with NS
    var treatmentdeleted: Bool  // Soft delete flag
    var nightscoutEventType: String?  // Original NS eventType (if downloaded)
    var enteredBy: String?      // Source identifier
}
```

### Upload Format

```swift
// xdrip:xdrip/Core Data/classes/TreatmentEntry+CoreDataClass.swift#L149-L201
func dictionaryRepresentationForNightscoutUpload() -> [String: Any] {
    var dict: [String: Any] = [
        "enteredBy": enteredBy ?? "xDrip4iOS",
        "eventTime": self.date.ISOStringFromDate(),
    ]
    
    // Split off type extension from ID
    if id != TreatmentEntry.EmptyId {
        dict["_id"] = id.split(separator: "-")[0]
    }
    
    // Type-specific fields
    switch self.treatmentType {
    case .Insulin:
        dict["eventType"] = "Bolus"
        dict["insulin"] = self.value
    case .Carbs:
        dict["eventType"] = "Carbs"
        dict["carbs"] = self.value
    case .Exercise:
        dict["eventType"] = "Exercise"
        dict["duration"] = self.value
    case .BgCheck:
        dict["eventType"] = "BG Check"
        dict["glucose"] = self.value
        dict["glucoseType"] = "Finger..."
        dict["units"] = "mg/dl"
    case .Basal:
        dict["eventType"] = "Temp Basal"
        dict["rate"] = self.value
        dict["duration"] = self.valueSecondary
    case .SiteChange:
        dict["eventType"] = "Site Change"
    case .SensorStart:
        dict["eventType"] = "Sensor Start"
    case .PumpBatteryChange:
        dict["eventType"] = "Pump Battery Change"
    }
    
    // Preserve original eventType if downloaded from NS
    if let nightscoutEventType = nightscoutEventType {
        dict["eventType"] = nightscoutEventType
    }
    
    return dict
}
```

### TreatmentType Enum

```swift
// xdrip:xdrip/Core Data/classes/TreatmentEntry+CoreDataClass.swift#L18-L27
@objc public enum TreatmentType: Int16 {
    case Insulin         // 0
    case Carbs           // 1
    case Exercise        // 2
    case BgCheck         // 3
    case Basal           // 4
    case SiteChange      // 5
    case SensorStart     // 6
    case PumpBatteryChange // 7
}
```

### ID Extension Pattern

xDrip4iOS uses ID extensions to separate compound NS treatments:

```swift
// xdrip:xdrip/Core Data/classes/TreatmentEntry+CoreDataClass.swift#L73-L77
public func idExtension() -> String {
    return "-" + self.nightscoutFieldname()
}

public func nightscoutFieldname() -> String {
    switch self {
    case .Insulin:  return "insulin"
    case .Carbs:    return "carbs"
    case .Exercise: return "exericse"  // Note: typo in source
    case .BgCheck:  return "glucose"
    case .Basal:    return "rate"
    default:        return ""
    }
}
```

**Example**: A NS treatment `_id: "abc123"` with both insulin and carbs becomes:
- `TreatmentEntry(id: "abc123-insulin", treatmentType: .Insulin, ...)`
- `TreatmentEntry(id: "abc123-carbs", treatmentType: .Carbs, ...)`

---

## TreatmentNSResponse (Download Parsing)

Parses downloaded NS treatments into local TreatmentEntry objects.

### Parsing Logic

```swift
// xdrip:xdrip/Treatments/TreatmentNSResponse.swift#L39-L135
public static func fromNightscout(dictionary: NSDictionary) -> [TreatmentNSResponse] {
    var responses: [TreatmentNSResponse] = []
    
    // Parse created_at with format detection
    if createdAt.contains(".") {
        // Loop, FreeAPS, OpenAPS format (with ms)
        dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"
    } else {
        // AndroidAPS format (without ms)
        dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss'Z'"
    }
    
    // Extract multiple treatment types from single NS record
    if let carbs = dictionary["carbs"] as? Double {
        responses.append(TreatmentNSResponse(
            id: id + "-carbs",
            eventType: .Carbs,
            value: carbs
        ))
    }
    
    if let insulin = dictionary["insulin"] as? Double {
        responses.append(TreatmentNSResponse(
            id: id + "-insulin",
            eventType: .Insulin,
            value: insulin
        ))
    }
    
    // ... similar for Exercise, BgCheck, Basal, SiteChange, etc.
}
```

### Supported NS eventTypes (Download)

| NS eventType | TreatmentType | Fields Extracted |
|--------------|---------------|------------------|
| (any with `carbs`) | `.Carbs` | `carbs` |
| (any with `insulin`) | `.Insulin` | `insulin` |
| "Exercise" | `.Exercise` | `duration` |
| (any with `glucose`) | `.BgCheck` | `glucose`, `units` |
| (any with `rate`) | `.Basal` | `rate`, `duration` |
| "Site Change" | `.SiteChange` | (none) |
| "Sensor Start" | `.SensorStart` | (none) |
| "Pump Battery Change" | `.PumpBatteryChange` | (none) |

### Unit Conversion on Download

BgCheck glucose values are converted to mg/dL if needed:

```swift
// xdrip:xdrip/Treatments/TreatmentNSResponse.swift#L101-L105
if let glucose = dictionary["glucose"] as? Double, 
   let units = dictionary["units"] as? String {
    let value = units == "mg/dl" ? glucose : glucose.mmolToMgdl()
    responses.append(TreatmentNSResponse(..., value: value, ...))
}
```

---

## NightscoutProfile → profile Collection

Stores therapy settings (basal rates, ISF, carb ratios).

### Internal Model

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutProfileModels.swift#L15-L43
struct NightscoutProfile: Codable {
    struct TimeValue: Codable {
        var timeAsSecondsFromMidnight: Int
        var value: Double
    }
    
    var updatedDate: Date = .distantPast
    var lastCheckedDate: Date = .distantPast
    
    var basal: [TimeValue]?
    var carbratio: [TimeValue]?
    var sensitivity: [TimeValue]?
    var timezone: String?
    var dia: Double?
    var isMgDl: Bool?
    var startDate: Date = .distantPast
    var createdAt: Date = .distantPast
    var profileName: String?
    var enteredBy: String?
}
```

### Download Response Model

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutProfileModels.swift#L74-L118
struct NightscoutProfileResponse: Codable {
    struct Profile: Codable {
        struct ProfileEntry: Codable {
            let time: String          // "HH:mm"
            let value: Double
            let timeAsSeconds: Int    // Seconds from midnight
        }
        
        let basal: [ProfileEntry]
        let carbratio: [ProfileEntry]
        let sens: [ProfileEntry]
        let targetLow: [ProfileEntry]
        let targetHigh: [ProfileEntry]
        let timezone: String
        let dia: Double
        let units: String            // "mg/dl" or "mmol"
    }
    
    let id: String                   // "_id" from NS
    let store: [String: Profile]     // Named profiles
    let units: String?
    let defaultProfile: String       // Name of default profile
    let startDate: String            // ISO 8601
    let enteredBy: String?
}
```

### Profile Parsing

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutProfileModels.swift#L47-L68
extension NightscoutProfile {
    init(from response: NightscoutProfileResponse) {
        self.startDate = ISO8601DateFormatter.withFractionalSeconds
            .date(from: response.startDate) ?? .distantPast
        self.profileName = response.defaultProfile
        self.enteredBy = response.enteredBy
        
        // Use default profile or first available
        if let profile = response.store[response.defaultProfile] 
                      ?? response.store.first?.value {
            self.timezone = profile.timezone
            self.dia = profile.dia
            self.isMgDl = profile.units.lowercased() == "mg/dl"
            self.basal = profile.basal.map { 
                TimeValue(timeAsSecondsFromMidnight: $0.timeAsSeconds, value: $0.value) 
            }
            self.carbratio = profile.carbratio.map { ... }
            self.sensitivity = profile.sens.map { ... }
        }
    }
}
```

---

## FollowerBgReading (Follower Mode)

Represents glucose readings downloaded in follower mode.

```swift
// xdrip:xdrip/Managers/Followers/FollowerBgReading.swift
struct FollowerBgReading {
    var timeStamp: Date
    var sgv: Double
}
```

### Conversion to BgReading

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutFollowManager.swift#L103-L118
public func createBgReading(followGlucoseData: FollowerBgReading) -> BgReading {
    let bgReading = BgReading(
        timeStamp: followGlucoseData.timeStamp,
        sensor: nil,
        calibration: nil,
        rawData: followGlucoseData.sgv,  // Using SGV as rawData
        deviceName: nil,
        nsManagedObjectContext: coreDataManager.mainManagedObjectContext
    )
    
    bgReading.calculatedValue = followGlucoseData.sgv
    bgReading.calculatedValueSlope = findSlope()
    
    return bgReading
}
```

---

## DeviceStatus (Upload)

Battery and device information uploaded to NS.

### Transmitter Battery Upload

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift#L933-L958
var dataToUpload = [
    "uploader": [
        "name": "transmitter",
        "battery": transmitterBatteryInfo.value
    ]
] as [String: Any]

// For Dexcom (has batteryVoltage)
if transmitterBatteryInfoAsKeyValue.key != "battery" {
    dataToUpload = [
        "uploader": [
            "name": "transmitter",
            "battery": Int(UIDevice.current.batteryLevel * 100.0),
            transmitterBatteryInfoAsKeyValue.key: transmitterBatteryInfoAsKeyValue.value
        ]
    ]
}

uploadData(dataToUpload: dataToUpload, path: nightscoutDeviceStatusPath)
```

### Sensor Start Upload

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift#L964-L982
let dataToUpload = [
    "_id": sensor.id,
    "eventType": "Sensor Start",
    "created_at": sensor.startDate.ISOStringFromDate(),
    "enteredBy": ConstantsHomeView.applicationName  // "xDrip4iOS"
]

uploadData(dataToUpload: dataToUpload, path: nightscoutTreatmentPath)
```

---

## Code References Summary

| Model | Source File | Lines |
|-------|-------------|-------|
| BgReading upload | `Managers/Nightscout/BgReading+Nightscout.swift` | 6-22 |
| Calibration upload | `Managers/Nightscout/Calibration+Nightscout.swift` | 14-45 |
| TreatmentEntry | `Core Data/classes/TreatmentEntry+CoreDataClass.swift` | All |
| TreatmentNSResponse | `Treatments/TreatmentNSResponse.swift` | All |
| NightscoutProfile | `Managers/Nightscout/NightscoutProfileModels.swift` | All |
| FollowerBgReading | `Managers/Followers/FollowerBgReading.swift` | All |
| DeviceStatus upload | `Managers/Nightscout/NightscoutSyncManager.swift` | 920-982 |
