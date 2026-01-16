# xDrip4iOS Profile Handling

This document details how xDrip4iOS downloads, parses, and uses Nightscout profile data.

---

## Source Files

- `xdrip/Managers/Nightscout/NightscoutProfileModels.swift` (~119 lines)
- `xdrip/Managers/Nightscout/NightscoutSyncManager.swift` (profile download logic)

---

## Profile Download

### API Endpoint

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift#L33
private let nightscoutProfilePath = "/api/v1/profile"
```

### Download Trigger

Profile is downloaded during Nightscout sync operations and cached locally.

---

## Data Models

### Internal Profile Model

The internal model is a simplified representation used throughout the app:

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutProfileModels.swift#L15-L43
struct NightscoutProfile: Codable {
    struct TimeValue: Codable, Hashable {
        var timeAsSecondsFromMidnight: Int  // 0-86399
        var value: Double
        
        func toDate(date: Date) -> Date {
            return date.addingTimeInterval(Double(timeAsSecondsFromMidnight))
        }
    }
    
    var updatedDate: Date = .distantPast
    var lastCheckedDate: Date = .distantPast
    
    var basal: [TimeValue]?       // Basal rates (U/hr)
    var carbratio: [TimeValue]?   // I:C ratios (g/U)
    var sensitivity: [TimeValue]? // ISF (mg/dL/U or mmol/L/U)
    var timezone: String?         // IANA timezone
    var dia: Double?              // Duration of Insulin Action (hours)
    var isMgDl: Bool?             // Units preference
    var startDate: Date = .distantPast
    var createdAt: Date = .distantPast
    var profileName: String?      // Active profile name
    var enteredBy: String?        // Who created the profile
    
    func hasData() -> Bool {
        return updatedDate != .distantPast
    }
}
```

### Response Model (From NS API)

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutProfileModels.swift#L74-L118
struct NightscoutProfileResponse: Codable {
    struct Profile: Codable {
        struct ProfileEntry: Codable {
            let time: String          // "HH:mm" format
            let value: Double
            let timeAsSeconds: Int    // Seconds from midnight
        }
        
        let basal: [ProfileEntry]
        let carbratio: [ProfileEntry]
        let sens: [ProfileEntry]          // ISF (sensitivity)
        let targetLow: [ProfileEntry]
        let targetHigh: [ProfileEntry]
        let timezone: String
        let dia: Double
        let units: String                 // "mg/dl" or "mmol"
    }
    
    let id: String                        // NS document _id
    let store: [String: Profile]          // Named profiles dictionary
    let units: String?
    let defaultProfile: String            // Name of default profile
    let startDate: String                 // ISO 8601
    let enteredBy: String?
}

// CodingKeys for NS field mapping
private enum CodingKeys: String, CodingKey {
    case id = "_id"
    case units
    case startDate
    case defaultProfile
    case enteredBy
    case store
}

// Profile-level CodingKeys
private enum CodingKeys: String, CodingKey {
    case carbratio
    case sens
    case targetHigh = "target_high"
    case timezone
    case dia
    case targetLow = "target_low"
    case basal
    case units
}
```

---

## Response to Internal Conversion

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutProfileModels.swift#L47-L68
extension NightscoutProfile {
    init(from response: NightscoutProfileResponse) {
        self.init()
        
        // Parse startDate (supports fractional seconds)
        let startDateString = response.startDate
        self.startDate = ISO8601DateFormatter.withFractionalSeconds
            .date(from: startDateString) 
            ?? ISO8601DateFormatter().date(from: startDateString) 
            ?? .distantPast
        
        self.profileName = response.defaultProfile
        self.enteredBy = response.enteredBy
        self.updatedDate = .now
        
        // Select profile: default profile or first available
        if let profile = response.store[response.defaultProfile] 
                      ?? response.store.first?.value {
            
            self.timezone = profile.timezone
            self.dia = profile.dia
            self.isMgDl = profile.units.lowercased() == "mg/dl"
            
            // Convert ProfileEntry arrays to TimeValue arrays
            self.basal = profile.basal.map { 
                TimeValue(timeAsSecondsFromMidnight: $0.timeAsSeconds, value: $0.value) 
            }
            self.carbratio = profile.carbratio.map { 
                TimeValue(timeAsSecondsFromMidnight: $0.timeAsSeconds, value: $0.value) 
            }
            self.sensitivity = profile.sens.map { 
                TimeValue(timeAsSecondsFromMidnight: $0.timeAsSeconds, value: $0.value) 
            }
        }
    }
}
```

---

## Time-Based Settings

### TimeValue Structure

Profile settings vary throughout the day. xDrip4iOS uses seconds from midnight:

```swift
struct TimeValue: Codable, Hashable {
    var timeAsSecondsFromMidnight: Int  // 0 = midnight, 43200 = noon
    var value: Double
}
```

### Example Basal Schedule

```swift
// 00:00 = 0.8 U/hr
// 06:00 = 1.2 U/hr
// 12:00 = 1.0 U/hr
// 18:00 = 0.9 U/hr

basal = [
    TimeValue(timeAsSecondsFromMidnight: 0,     value: 0.8),  // 00:00
    TimeValue(timeAsSecondsFromMidnight: 21600, value: 1.2),  // 06:00
    TimeValue(timeAsSecondsFromMidnight: 43200, value: 1.0),  // 12:00
    TimeValue(timeAsSecondsFromMidnight: 64800, value: 0.9),  // 18:00
]
```

### Converting to Date

```swift
func toDate(date: Date) -> Date {
    return date.addingTimeInterval(Double(timeAsSecondsFromMidnight))
}
```

---

## Local Storage

Profile data is cached in UserDefaults for persistence across app restarts:

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift#L130-L134
if let profileData = sharedUserDefaults?.object(forKey: "nightscoutProfile") as? Data,
   let nightscoutProfile = try? JSONDecoder().decode(NightscoutProfile.self, from: profileData) {
    self.profile = nightscoutProfile
}
```

---

## Unit Detection

Units are detected from the profile's `units` field:

```swift
self.isMgDl = profile.units.lowercased() == "mg/dl"
```

This affects how sensitivity (ISF) values are interpreted:
- `true`: ISF is in mg/dL per unit
- `false`: ISF is in mmol/L per unit

---

## Profile Selection Logic

When multiple profiles exist in the `store`:

1. **First choice**: Use `defaultProfile` name
2. **Fallback**: Use first profile in store

```swift
if let profile = response.store[response.defaultProfile] 
              ?? response.store.first?.value {
    // Use this profile
}
```

---

## Timezone Handling

The profile includes an IANA timezone string:

```swift
self.timezone = profile.timezone  // e.g., "America/New_York"
```

This is used for:
- Displaying profile times in correct local time
- Aligning time-based settings with user's local time

---

## NS Profile Schema Reference

### Nightscout API Response Format

```json
{
    "_id": "507f1f77bcf86cd799439011",
    "defaultProfile": "Default",
    "startDate": "2026-01-16T00:00:00.000Z",
    "enteredBy": "Loop",
    "store": {
        "Default": {
            "basal": [
                {"time": "00:00", "value": 0.8, "timeAsSeconds": 0}
            ],
            "carbratio": [
                {"time": "00:00", "value": 10, "timeAsSeconds": 0}
            ],
            "sens": [
                {"time": "00:00", "value": 50, "timeAsSeconds": 0}
            ],
            "target_low": [
                {"time": "00:00", "value": 100, "timeAsSeconds": 0}
            ],
            "target_high": [
                {"time": "00:00", "value": 120, "timeAsSeconds": 0}
            ],
            "timezone": "America/New_York",
            "dia": 5,
            "units": "mg/dl"
        }
    }
}
```

---

## Field Mapping Summary

| NS Field | Swift Field | Type | Notes |
|----------|-------------|------|-------|
| `_id` | `id` | String | Document ID |
| `defaultProfile` | `profileName` | String | Active profile name |
| `startDate` | `startDate` | Date | Profile activation time |
| `enteredBy` | `enteredBy` | String? | Creator identifier |
| `store[name].basal` | `basal` | [TimeValue] | Basal rates |
| `store[name].carbratio` | `carbratio` | [TimeValue] | I:C ratios |
| `store[name].sens` | `sensitivity` | [TimeValue] | ISF values |
| `store[name].timezone` | `timezone` | String? | IANA timezone |
| `store[name].dia` | `dia` | Double? | Duration of Insulin Action |
| `store[name].units` | `isMgDl` | Bool? | Derived from units string |
| N/A | `updatedDate` | Date | Local tracking |
| N/A | `lastCheckedDate` | Date | Local tracking |

---

## Comparison with Other Apps

| Aspect | xDrip4iOS | Loop | AAPS |
|--------|-----------|------|------|
| **Profile Direction** | Download only | Upload & Download | Upload & Download |
| **Multiple Profiles** | Uses default | Full support | Full support |
| **Profile Switch** | Not supported | Supported | Supported |
| **Target Range** | Not parsed | Used | Used |
| **Override Support** | Not parsed | Supported | Supported |

---

## Code References

| Purpose | Location |
|---------|----------|
| Internal profile model | `NightscoutProfileModels.swift#L15-L43` |
| Response parsing model | `NightscoutProfileModels.swift#L74-L118` |
| Response to internal conversion | `NightscoutProfileModels.swift#L47-L68` |
| Local storage | `NightscoutSyncManager.swift#L130-L134` |
| API path | `NightscoutSyncManager.swift#L33` |
