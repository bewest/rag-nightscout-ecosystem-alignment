# Trio Data Models

This document maps Trio's Swift data models to their Nightscout equivalents, providing field-level mappings for synchronization.

## Source Files

| File | Purpose |
|------|---------|
| `trio:Trio/Sources/Models/*.swift` | Data model definitions |
| `trio:Trio/Sources/Models/NightscoutTreatment.swift` | NS treatment model |
| `trio:Trio/Sources/Models/NightscoutStatus.swift` | NS devicestatus model |
| `trio:Trio/Sources/Models/TrioSettings.swift` | App settings model |
| `trio:Trio/Sources/Models/TrioCustomOrefVariables.swift` | Custom oref variables |

---

## Glucose Models

### BloodGlucose → entries

```swift
// trio:BloodGlucose.swift
struct BloodGlucose: JSON {
    var _id: String              // → _id
    var sgv: Int?                // → sgv
    var direction: Direction?    // → direction
    let date: Decimal            // → date (epoch ms)
    let dateString: Date         // → dateString
    let unfiltered: Decimal?     // → unfiltered
    let filtered: Decimal?       // → filtered
    let noise: Int?              // → noise
    var glucose: Int?            // → glucose
    let type: String?            // → type
}
```

| Trio Field | NS Field | Notes |
|------------|----------|-------|
| `_id` | `_id` | UUID string |
| `sgv` | `sgv` | Sensor glucose value (mg/dL) |
| `direction` | `direction` | Trend arrow |
| `date` | `date` | Epoch milliseconds |
| `dateString` | `dateString` | ISO 8601 string |
| `noise` | `noise` | CGM noise level (1-4) |
| `type` | `type` | Usually "sgv" |

### Direction Enum

```swift
enum Direction: String {
    case tripleUp = "TripleUp"
    case doubleUp = "DoubleUp"
    case singleUp = "SingleUp"
    case fortyFiveUp = "FortyFiveUp"
    case flat = "Flat"
    case fortyFiveDown = "FortyFiveDown"
    case singleDown = "SingleDown"
    case doubleDown = "DoubleDown"
    case tripleDown = "TripleDown"
    case none = "NONE"
    case notComputable = "NOT COMPUTABLE"
    case rateOutOfRange = "RATE OUT OF RANGE"
}
```

---

## Treatment Models

### NightscoutTreatment → treatments

```swift
// trio:NightscoutTreatment.swift
struct NightscoutTreatment: JSON {
    var duration: Int?           // → duration
    var absolute: Decimal?       // → absolute
    var rate: Decimal?           // → rate
    var eventType: EventType     // → eventType
    var createdAt: Date?         // → created_at
    var enteredBy: String?       // → enteredBy
    var insulin: Decimal?        // → insulin
    var notes: String?           // → notes
    var carbs: Decimal?          // → carbs
    var fat: Decimal?            // → fat
    var protein: Decimal?        // → protein
    var foodType: String?        // → foodType
    let targetTop: Decimal?      // → targetTop
    let targetBottom: Decimal?   // → targetBottom
}
```

| Trio Field | NS Field | Notes |
|------------|----------|-------|
| `eventType` | `eventType` | Treatment type |
| `createdAt` | `created_at` | ISO 8601 timestamp |
| `enteredBy` | `enteredBy` | "Trio" for local entries |
| `duration` | `duration` | Minutes |
| `insulin` | `insulin` | Bolus amount (units) |
| `carbs` | `carbs` | Carb grams |
| `rate` | `rate` | Temp basal rate |
| `absolute` | `absolute` | Absolute temp basal |

### EventType Mappings

```swift
// trio:PumpHistoryEvent.swift
enum EventType: String {
    // Internal types
    case bolus = "Bolus"
    case smb = "SMB"
    case mealBolus = "Meal Bolus"
    case correctionBolus = "Correction Bolus"
    case snackBolus = "Snack Bolus"
    case bolusWizard = "BolusWizard"
    case tempBasal = "TempBasal"
    case tempBasalDuration = "TempBasalDuration"
    case pumpSuspend = "PumpSuspend"
    case pumpResume = "PumpResume"
    case pumpAlarm = "PumpAlarm"
    case pumpBattery = "PumpBattery"
    case rewind = "Rewind"
    case prime = "Prime"
    case journalCarbs = "JournalEntryMealMarker"
    
    // Nightscout types (for upload)
    case nsTempBasal = "Temp Basal"
    case nsCarbCorrection = "Carb Correction"
    case nsTempTarget = "Temporary Target"
    case nsInsulinChange = "Insulin Change"
    case nsSiteChange = "Site Change"
    case nsBatteryChange = "Pump Battery Change"
    case nsAnnouncement = "Announcement"
    case nsSensorChange = "Sensor Start"
    case nsExternalInsulin = "External Insulin"
}
```

---

## Carbs Models

### CarbsEntry → treatments (Carb Correction)

```swift
// trio:CarbsEntry.swift
struct CarbsEntry: JSON {
    let id: String?
    let createdAt: Date          // → created_at
    var carbs: Decimal           // → carbs
    var fat: Decimal?            // → fat
    var protein: Decimal?        // → protein
    let note: String?            // → notes
    var enteredBy: String?       // → enteredBy
    var fpuID: String?           // FPU tracking
}
```

---

## Temp Target Models

### TempTarget → treatments (Temporary Target)

```swift
// trio:TempTarget.swift
struct TempTarget: JSON {
    let id: String
    let createdAt: Date          // → created_at
    let targetTop: Decimal       // → targetTop
    let targetBottom: Decimal    // → targetBottom
    let duration: Decimal        // → duration
    let enteredBy: String?       // → enteredBy
    let reason: String?          // → reason
}
```

---

## DeviceStatus Models

### NightscoutStatus → devicestatus

```swift
// trio:NightscoutStatus.swift
struct NightscoutStatus: JSON {
    let device: String           // → device ("Trio")
    let openaps: OpenAPSStatus   // → openaps
    let pump: NSPumpStatus       // → pump
    let uploader: Uploader       // → uploader
}
```

### OpenAPSStatus

```swift
struct OpenAPSStatus: JSON {
    let iob: IOBEntry?           // → openaps.iob
    let suggested: Suggestion?   // → openaps.suggested
    let enacted: Suggestion?     // → openaps.enacted
    let version: String          // → openaps.version
}
```

### NSPumpStatus

```swift
struct NSPumpStatus: JSON {
    let clock: Date              // → pump.clock
    let battery: Battery?        // → pump.battery
    let reservoir: Decimal?      // → pump.reservoir
    let status: PumpStatus?      // → pump.status
}
```

---

## Algorithm Models

### Suggestion

```swift
// trio:Suggestion.swift
struct Suggestion: JSON {
    let reason: String           // → reason
    let units: Decimal?          // → units (SMB)
    let insulinReq: Decimal?     // → insulinReq
    let eventualBG: Int?         // → eventualBG
    let sensitivityRatio: Decimal?
    let rate: Decimal?           // → rate
    let duration: Int?           // → duration
    let iob: Decimal?            // → IOB
    let cob: Decimal?            // → COB
    var predictions: Predictions? // → predBGs
    let deliverAt: Date?         // → deliverAt
    let carbsReq: Decimal?       // → carbsReq
    let temp: TempType?          // → temp
    let bg: Decimal?             // → bg
    let reservoir: Decimal?      // → reservoir
    let isf: Decimal?            // → ISF
    var timestamp: Date?
    var recieved: Bool?          // → received (enacted)
    let tdd: Decimal?            // → TDD
    let insulin: Insulin?        // → insulin
    let current_target: Decimal?
    let minDelta: Decimal?
    let expectedDelta: Decimal?
    let minGuardBG: Decimal?
    let minPredBG: Decimal?
    let threshold: Decimal?
}
```

### Predictions

```swift
struct Predictions: JSON {
    let iob: [Int]?    // → predBGs.IOB
    let zt: [Int]?     // → predBGs.ZT
    let cob: [Int]?    // → predBGs.COB
    let uam: [Int]?    // → predBGs.UAM
}
```

### IOBEntry

```swift
// trio:IOBEntry.swift
struct IOBEntry: JSON {
    let iob: Decimal             // → iob
    let basaliob: Decimal?       // → basaliob
    let activity: Decimal?       // → activity
    let time: Date               // → time
    let bolussnooze: Decimal?    // → bolussnooze
    let lastBolusTime: Date?     // → lastBolusTime
}
```

---

## Profile Models

### NightscoutProfileStore → profile

```swift
// trio:NightscoutStatus.swift
struct NightscoutProfileStore: JSON {
    let defaultProfile: String   // → defaultProfile
    let startDate: Date          // → startDate
    let mills: Int               // → mills
    let units: String            // → units
    let enteredBy: String        // → enteredBy
    let store: [String: ScheduledNightscoutProfile]  // → store
}

struct ScheduledNightscoutProfile: JSON {
    let dia: Decimal             // → dia
    let carbs_hr: Int            // → carbs_hr
    let delay: Decimal           // → delay
    let timezone: String         // → timezone
    let target_low: [NightscoutTimevalue]   // → target_low
    let target_high: [NightscoutTimevalue]  // → target_high
    let sens: [NightscoutTimevalue]         // → sens
    let basal: [NightscoutTimevalue]        // → basal
    let carbratio: [NightscoutTimevalue]    // → carbratio
    let units: String            // → units
}

struct NightscoutTimevalue: JSON {
    let time: String             // → time (HH:MM)
    let value: Decimal           // → value
    let timeAsSeconds: Int?      // → timeAsSeconds
}
```

---

## Pump History Models

### PumpHistoryEvent

```swift
// trio:PumpHistoryEvent.swift
struct PumpHistoryEvent: JSON {
    let id: String               // Unique ID
    let type: EventType          // _type
    let timestamp: Date          // timestamp
    let amount: Decimal?         // amount (insulin)
    let duration: Int?           // duration
    let durationMin: Int?        // duration (min)
    let rate: Decimal?           // rate
    let temp: TempType?          // temp (absolute/percent)
    let carbInput: Int?          // carb_input
    let fatInput: Int?           // fatInput
    let proteinInput: Int?       // proteinInput
    let note: String?            // note
    let isSMB: Bool?             // isSMB
    let isExternalInsulin: Bool? // isExternalInsulin
}
```

---

## Override Models

### Oref2_variables

```swift
// trio:Oref2_variables.swift
struct Oref2_variables: JSON {
    let average_total_data: Decimal
    let weightedAverage: Decimal
    let past2hoursAverage: Decimal
    let date: Date
    let isEnabled: Bool          // Temp target active
    let presetActive: Bool       // Preset active
    let overridePercentage: Decimal
    let useOverride: Bool
    let duration: Decimal
    let unlimited: Bool          // Indefinite override
    let hbt: Decimal             // Half-basal target
    let overrideTarget: Decimal
    let smbIsOff: Bool
    let advancedSettings: Bool
    let isfAndCr: Bool
    let isf: Bool
    let cr: Bool
    let smbIsScheduledOff: Bool
    let start: Decimal
    let end: Decimal
    let smbMinutes: Decimal
    let uamMinutes: Decimal
}
```

---

## Settings Models

### Preferences

```swift
// trio:Preferences.swift
struct Preferences: JSON {
    var maxIOB: Decimal                    // max_iob
    var maxDailySafetyMultiplier: Decimal  // max_daily_safety_multiplier
    var currentBasalSafetyMultiplier: Decimal
    var autosensMax: Decimal               // autosens_max
    var autosensMin: Decimal               // autosens_min
    var smbDeliveryRatio: Decimal          // smb_delivery_ratio
    var enableUAM: Bool                    // enableUAM
    var enableSMBWithCOB: Bool             // enableSMB_with_COB
    var enableSMBAlways: Bool              // enableSMB_always
    var maxSMBBasalMinutes: Decimal        // maxSMBBasalMinutes
    var curve: InsulinCurve                // curve
    var insulinPeakTime: Decimal           // insulinPeakTime
    // ... many more
}
```

### TrioSettings

```swift
// trio:Trio/Sources/Models/TrioSettings.swift
struct TrioSettings: JSON, Equatable {
    // Core settings
    var units: GlucoseUnits = .mgdL
    var closedLoop: Bool = false
    var isUploadEnabled: Bool = false
    var isDownloadEnabled: Bool = false
    var uploadGlucose: Bool = true
    
    // CGM settings
    var cgm: CGMType = .none
    var cgmPluginIdentifier: String = ""
    var useLocalGlucoseSource: Bool = false
    var localGlucosePort: Int = 8080
    var smoothGlucose: Bool = false
    
    // Glucose display
    var glucoseBadge: Bool = false
    var lowGlucose: Decimal = 72
    var highGlucose: Decimal = 270
    var high: Decimal = 180
    var low: Decimal = 70
    var glucoseColorScheme: GlucoseColorScheme = .staticColor
    
    // Notifications
    var notificationsPump: Bool = true
    var notificationsCgm: Bool = true
    var notificationsCarb: Bool = true
    var notificationsAlgorithm: Bool = true
    var glucoseNotificationsOption: GlucoseNotificationsOption = .onlyAlarmLimits
    var addSourceInfoToGlucoseNotifications: Bool = false
    var carbsRequiredThreshold: Decimal = 10
    var showCarbsRequiredBadge: Bool = true
    
    // Meal handling
    var useFPUconversion: Bool = true
    var individualAdjustmentFactor: Decimal = 0.5
    var timeCap: Decimal = 8
    var minuteInterval: Decimal = 30
    var delay: Decimal = 60
    var maxCarbs: Decimal = 250
    var maxFat: Decimal = 250
    var maxProtein: Decimal = 250
    var fattyMeals: Bool = false           // NEW
    var fattyMealFactor: Decimal = 0.7     // NEW
    var sweetMeals: Bool = false           // NEW
    var sweetMealFactor: Decimal = 1       // NEW
    
    // Override settings
    var overrideFactor: Decimal = 0.8
    var displayPresets: Bool = true
    
    // Bolus settings
    var confirmBolusFaster: Bool = false
    var confirmBolus: Bool = false
    var bolusShortcut: BolusShortcutLimit = .notAllowed  // NEW
    
    // iOS features
    var useLiveActivity: Bool = false              // NEW
    var lockScreenView: LockScreenView = .simple   // NEW
    var smartStackView: LockScreenView = .simple   // NEW
    var useAppleHealth: Bool = false
    var useCalendar: Bool = false
    var displayCalendarIOBandCOB: Bool = false
    var displayCalendarEmojis: Bool = false
    
    // Chart settings
    var xGridLines: Bool = true
    var yGridLines: Bool = true
    var rulerMarks: Bool = true
    var forecastDisplayType: ForecastDisplayType = .cone
    var eA1cDisplayUnit: EstimatedA1cDisplayUnit = .percent
    var timeInRangeType: TimeInRangeType = .timeInTightRange  // NEW
    
    // Debug
    var debugOptions: Bool = false
}
```

### BolusShortcutLimit (NEW)

```swift
// trio:Trio/Sources/Models/TrioSettings.swift
enum BolusShortcutLimit: String, JSON, CaseIterable {
    case notAllowed        // Shortcuts cannot trigger bolus
    case limitBolusMax     // Limited to max bolus setting
}
```

---

## Remote Command Model (NEW)

### CommandPayload

```swift
// Used by TrioRemoteControl for encrypted APNS commands
struct CommandPayload: Codable {
    let commandType: CommandType
    let timestamp: TimeInterval       // Unix epoch seconds
    
    // Bolus
    let bolusAmount: Decimal?
    
    // Meal
    let carbAmount: Decimal?
    let fatAmount: Decimal?
    let proteinAmount: Decimal?
    
    // Temp Target
    let targetBG: Decimal?
    let duration: Decimal?
    
    // Override
    let overrideName: String?
    
    // Response
    let returnNotification: ReturnNotificationInfo?
}

enum CommandType: String, Codable {
    case bolus
    case meal
    case tempTarget
    case cancelTempTarget
    case startOverride
    case cancelOverride
}
```

**Note**: The legacy Announcement model for Nightscout-based remote commands has been deprecated in favor of the encrypted CommandPayload system.

---

## Cross-Reference Table

| Trio Model | NS Collection | Key Fields |
|------------|---------------|------------|
| `BloodGlucose` | `entries` | sgv, date, direction |
| `NightscoutTreatment` | `treatments` | eventType, created_at, insulin, carbs |
| `CarbsEntry` | `treatments` | carbs, created_at |
| `TempTarget` | `treatments` | targetTop, targetBottom, duration |
| `NightscoutStatus` | `devicestatus` | openaps, pump, uploader |
| `NightscoutProfileStore` | `profile` | store, defaultProfile |
| `Announcement` | `treatments` | eventType=Announcement, notes |

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Updated paths to Trio/, added TrioSettings with new fields, added CommandPayload model |
| 2026-01-16 | Agent | Initial data models documentation from source analysis |
