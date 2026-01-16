# xDrip4iOS Treatment Classification

This document details how xDrip4iOS classifies, parses, and maps treatment types to/from Nightscout.

---

## TreatmentType Enum

### Definition

```swift
// xdrip:xdrip/Core Data/classes/TreatmentEntry+CoreDataClass.swift#L18-L27
@objc public enum TreatmentType: Int16 {
    case Insulin          = 0
    case Carbs            = 1
    case Exercise         = 2
    case BgCheck          = 3
    case Basal            = 4
    case SiteChange       = 5
    case SensorStart      = 6
    case PumpBatteryChange = 7
}
```

**Warning**: The enum uses `Int16` raw values for CoreData storage. Adding new cases must be done at the end to avoid data migration issues.

---

## Treatment Type Mapping

### Upload Mapping (xDrip4iOS → Nightscout)

| TreatmentType | NS eventType | NS Fields |
|---------------|--------------|-----------|
| `.Insulin` | "Bolus" | `insulin` |
| `.Carbs` | "Carbs" | `carbs` |
| `.Exercise` | "Exercise" | `duration` |
| `.BgCheck` | "BG Check" | `glucose`, `glucoseType`, `units` |
| `.Basal` | "Temp Basal" | `rate`, `duration` |
| `.SiteChange` | "Site Change" | (none) |
| `.SensorStart` | "Sensor Start" | (none) |
| `.PumpBatteryChange` | "Pump Battery Change" | (none) |

### Upload Code

```swift
// xdrip:xdrip/Core Data/classes/TreatmentEntry+CoreDataClass.swift#L166-L194
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
    dict["glucoseType"] = "Finger" + mmolAnnotation
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
```

---

## Download Parsing (Nightscout → xDrip4iOS)

### Parsing Logic

xDrip4iOS parses NS treatments by checking for specific fields, not just `eventType`:

```swift
// xdrip:xdrip/Treatments/TreatmentNSResponse.swift#L83-L131
public static func fromNightscout(dictionary: NSDictionary) -> [TreatmentNSResponse] {
    var responses: [TreatmentNSResponse] = []
    
    // CARBS: Any treatment with carbs field
    if let carbs = dictionary["carbs"] as? Double {
        responses.append(TreatmentNSResponse(
            id: id + TreatmentType.Carbs.idExtension(),  // "-carbs"
            eventType: .Carbs,
            value: carbs
        ))
    }
    
    // INSULIN: Any treatment with insulin field
    if let insulin = dictionary["insulin"] as? Double {
        responses.append(TreatmentNSResponse(
            id: id + TreatmentType.Insulin.idExtension(),  // "-insulin"
            eventType: .Insulin,
            value: insulin
        ))
    }
    
    // EXERCISE: Requires eventType == "Exercise" AND duration
    if nightscoutEventType == "Exercise", 
       let duration = dictionary["duration"] as? Double {
        responses.append(TreatmentNSResponse(
            id: id + TreatmentType.Carbs.idExtension(),  // Note: uses Carbs extension
            eventType: .Exercise,
            value: duration
        ))
    }
    
    // BG CHECK: Any treatment with glucose AND units
    if let glucose = dictionary["glucose"] as? Double, 
       let units = dictionary["units"] as? String {
        let value = units == "mg/dl" ? glucose : glucose.mmolToMgdl()
        responses.append(TreatmentNSResponse(
            id: id + TreatmentType.BgCheck.idExtension(),  // "-glucose"
            eventType: .BgCheck,
            value: value
        ))
    }
    
    // BASAL: Any treatment with rate AND duration
    if let rate = dictionary["rate"] as? Double, 
       let duration = dictionary["duration"] as? Double {
        responses.append(TreatmentNSResponse(
            id: id + TreatmentType.Basal.idExtension(),  // "-rate"
            eventType: .Basal,
            value: rate,
            valueSecondary: duration
        ))
    }
    
    // SITE CHANGE: Exact eventType match
    if nightscoutEventType == "Site Change" {
        responses.append(TreatmentNSResponse(
            id: id + TreatmentType.SiteChange.idExtension(),
            eventType: .SiteChange,
            value: 0
        ))
    }
    
    // SENSOR START: Exact eventType match
    if nightscoutEventType == "Sensor Start" {
        responses.append(TreatmentNSResponse(
            id: id + TreatmentType.SensorStart.idExtension(),
            eventType: .SensorStart,
            value: 0
        ))
    }
    
    // PUMP BATTERY CHANGE: Exact eventType match
    if nightscoutEventType == "Pump Battery Change" {
        responses.append(TreatmentNSResponse(
            id: id + TreatmentType.PumpBatteryChange.idExtension(),
            eventType: .PumpBatteryChange,
            value: 0
        ))
    }
    
    return responses
}
```

### Key Insight: Field-Based vs EventType-Based Parsing

| Detection Method | Treatment Types |
|-----------------|-----------------|
| **Field-based** (checks specific fields) | Carbs, Insulin, BgCheck, Basal |
| **EventType-based** (exact string match) | Exercise, SiteChange, SensorStart, PumpBatteryChange |

This means a NS treatment with eventType "Snack Bolus" containing both `insulin` and `carbs` fields will create TWO local TreatmentEntry objects.

---

## ID Extension System

### Purpose

xDrip4iOS appends type-specific suffixes to NS `_id` values to handle compound treatments.

### Extension Mapping

```swift
// xdrip:xdrip/Core Data/classes/TreatmentEntry+CoreDataClass.swift#L73-L95
public func idExtension() -> String {
    return "-" + self.nightscoutFieldname()
}

public func nightscoutFieldname() -> String {
    switch self {
    case .Insulin:  return "insulin"
    case .Carbs:    return "carbs"
    case .Exercise: return "exericse"  // Note: typo in source code
    case .BgCheck:  return "glucose"
    case .Basal:    return "rate"
    default:        return ""
    }
}
```

| TreatmentType | Extension | Example Full ID |
|---------------|-----------|-----------------|
| `.Insulin` | `-insulin` | `abc123-insulin` |
| `.Carbs` | `-carbs` | `abc123-carbs` |
| `.Exercise` | `-exericse` | `abc123-exericse` |
| `.BgCheck` | `-glucose` | `abc123-glucose` |
| `.Basal` | `-rate` | `abc123-rate` |
| `.SiteChange` | (empty) | `abc123` |
| `.SensorStart` | (empty) | `abc123` |
| `.PumpBatteryChange` | (empty) | `abc123` |

### Upload ID Stripping

When uploading, the extension is stripped to get the original NS ID:

```swift
// xdrip:xdrip/Core Data/classes/TreatmentEntry+CoreDataClass.swift#L161-L163
if id != TreatmentEntry.EmptyId {
    dict["_id"] = id.split(separator: "-")[0]  // "abc123-insulin" → "abc123"
}
```

---

## Compound Treatment Example

### NS Treatment (Download)

```json
{
    "_id": "abc123",
    "eventType": "Snack Bolus",
    "insulin": 2.5,
    "carbs": 30,
    "created_at": "2026-01-16T12:00:00.000Z"
}
```

### xDrip4iOS Creates TWO TreatmentEntry Objects

```swift
TreatmentEntry(
    id: "abc123-insulin",
    treatmentType: .Insulin,
    value: 2.5,
    nightscoutEventType: "Snack Bolus"
)

TreatmentEntry(
    id: "abc123-carbs", 
    treatmentType: .Carbs,
    value: 30,
    nightscoutEventType: "Snack Bolus"
)
```

### Upload (if modified)

Each is uploaded separately but with same base `_id`:

```json
// First upload
{
    "_id": "abc123",
    "eventType": "Snack Bolus",
    "insulin": 2.5,
    "enteredBy": "xDrip4iOS"
}

// Second upload  
{
    "_id": "abc123",
    "eventType": "Snack Bolus",
    "carbs": 30,
    "enteredBy": "xDrip4iOS"
}
```

---

## enteredBy Field

### Upload

```swift
// xdrip:xdrip/Core Data/classes/TreatmentEntry+CoreDataClass.swift#L151-L155
let enteredByString = enteredBy ?? "xDrip4iOS"

var dict: [String: Any] = [
    "enteredBy": enteredByString,
    // ...
]
```

### Download Preservation

```swift
// xdrip:xdrip/Treatments/TreatmentNSResponse.swift#L81
let enteredBy: String? = dictionary["enteredBy"] as? String
```

The original `enteredBy` is preserved when downloading treatments, allowing xDrip4iOS to display the source (e.g., "androidaps", "Loop", "openaps").

---

## Date Parsing

### Format Detection

xDrip4iOS detects date format based on presence of milliseconds:

```swift
// xdrip:xdrip/Treatments/TreatmentNSResponse.swift#L54-L67
if createdAt.contains(".") {
    // Loop, FreeAPS (Loop), OpenAPS, FreeAPS X format
    dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"
} else {
    // AndroidAPS format
    dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss'Z'"
}
```

### Timezone

All dates are parsed and stored in UTC:

```swift
dateFormatter.locale = Locale(identifier: "en_US_POSIX")
dateFormatter.timeZone = TimeZone(abbreviation: "GMT")
```

---

## Unit Handling

### BgCheck Download

```swift
// xdrip:xdrip/Treatments/TreatmentNSResponse.swift#L101-L105
if let glucose = dictionary["glucose"] as? Double, 
   let units = dictionary["units"] as? String {
    // Convert mmol/L to mg/dL if needed
    let value = units == "mg/dl" ? glucose : glucose.mmolToMgdl()
}
```

### BgCheck Upload

```swift
// xdrip:xdrip/Core Data/classes/TreatmentEntry+CoreDataClass.swift#L177-L181
case .BgCheck:
    dict["eventType"] = "BG Check"
    dict["glucose"] = self.value  // Always mg/dL internally
    dict["glucoseType"] = "Finger" + mmolAnnotation  // Shows mmol if user preference
    dict["units"] = ConstantsNightscout.mgDlNightscoutUnitString  // "mg/dl"
```

---

## Treatment Matching

### Deduplication Check

```swift
// xdrip:xdrip/Treatments/TreatmentNSResponse.swift#L170-L174
public func matchesTreatmentEntry(_ entry: TreatmentEntry) -> Bool {
    return entry.date.toMillisecondsAsInt64() == self.createdAt.toMillisecondsAsInt64() 
        && entry.treatmentType == self.eventType 
        && entry.value == self.value
}
```

Matching is based on:
1. Timestamp (millisecond precision)
2. Treatment type
3. Value

---

## NS EventTypes Not Handled

xDrip4iOS does not create local TreatmentEntry objects for these NS eventTypes:

| NS eventType | Reason |
|--------------|--------|
| "Temp Target" | Not implemented |
| "Temporary Target" | Not implemented |
| "Profile Switch" | Not implemented |
| "Announcement" | Not implemented |
| "Note" | Not implemented |
| "Question" | Not implemented |
| "Combo Bolus" | Only `insulin`/`carbs` fields extracted |

These treatments are simply ignored during download.

---

## Code References

| Purpose | File | Lines |
|---------|------|-------|
| TreatmentType enum | `Core Data/classes/TreatmentEntry+CoreDataClass.swift` | 18-96 |
| Upload dictionary | `Core Data/classes/TreatmentEntry+CoreDataClass.swift` | 147-201 |
| Download parsing | `Treatments/TreatmentNSResponse.swift` | 39-135 |
| Treatment matching | `Treatments/TreatmentNSResponse.swift` | 170-174 |
