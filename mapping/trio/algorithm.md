# Trio Algorithm Flow

This document details how Trio executes the oref0 algorithm, including the Swift-JavaScript bridge, data preparation, and result parsing.

## Source Files

| File | Purpose |
|------|---------|
| `trio:FreeAPS/Sources/APS/OpenAPS/OpenAPS.swift` | Main algorithm bridge |
| `trio:FreeAPS/Sources/APS/OpenAPS/JavaScriptWorker.swift` | JS execution engine |
| `trio:FreeAPS/Sources/APS/APSManager.swift` | Loop orchestration |
| `trio:trio-oref/lib/determine-basal/determine-basal.js` | Core oref algorithm |

---

## Algorithm Execution Flow

### 1. Loop Cycle Trigger

The APSManager triggers algorithm execution approximately every 5 minutes:

```swift
// trio:APSManager.swift (conceptual)
// Loop cycle:
// 1. Fetch latest glucose
// 2. Gather pump history
// 3. Run algorithm
// 4. Enact suggestion
```

### 2. OpenAPS.determineBasal()

The main entry point for algorithm execution:

```swift
// trio:OpenAPS.swift#L18-L119
func determineBasal(currentTemp: TempBasal, clock: Date = Date()) -> Future<Suggestion?, Never> {
    Future { promise in
        self.processQueue.async {
            // 1. Save clock
            self.storage.save(clock, as: Monitor.clock)
            
            // 2. Save current temp basal
            let tempBasal = currentTemp.rawJSON
            self.storage.save(tempBasal, as: Monitor.tempBasal)
            
            // 3. Load input files
            let pumpHistory = self.loadFileFromStorage(name: OpenAPS.Monitor.pumpHistory)
            let carbs = self.loadFileFromStorage(name: Monitor.carbHistory)
            let glucose = self.loadFileFromStorage(name: Monitor.glucose)
            let profile = self.loadFileFromStorage(name: Settings.profile)
            let basalProfile = self.loadFileFromStorage(name: Settings.basalProfile)
            
            // 4. Calculate meal data (COB)
            let meal = self.meal(...)
            self.storage.save(meal, as: Monitor.meal)
            
            // 5. Calculate IOB
            let iob = self.iob(...)
            self.storage.save(iob, as: Monitor.iob)
            
            // 6. Get oref2 variables (overrides, TDD)
            let oref2_variables = self.oref2()
            
            // 7. Run determine-basal
            let suggested = self.determineBasal(...)
            
            // 8. Parse and save suggestion
            if var suggestion = Suggestion(from: suggested) {
                suggestion.timestamp = suggestion.deliverAt ?? clock
                self.storage.save(suggestion, as: Enact.suggested)
                promise(.success(suggestion))
            }
        }
    }
}
```

---

## JavaScript Execution

### JavaScriptWorker

Trio uses `JavaScriptCore` to execute oref0 JavaScript:

```swift
// trio:JavaScriptWorker.swift
final class JavaScriptWorker {
    private let jsContext: JSContext
    
    func inCommonContext<T>(_ block: (JavaScriptWorker) -> T) -> T {
        // Execute JavaScript in shared context
    }
    
    func evaluate(script: Script) {
        jsContext.evaluateScript(script.content)
    }
    
    func call(function: String, with arguments: [Any]) -> RawJSON {
        // Call JS function with arguments
    }
}
```

### Script Loading

Scripts are loaded from the `trio-oref/lib/` bundle:

```swift
// trio:OpenAPS.swift#L509-L541
private func determineBasal(...) -> RawJSON {
    return jsWorker.inCommonContext { worker in
        worker.evaluate(script: Script(name: Prepare.log))
        worker.evaluate(script: Script(name: Prepare.determineBasal))
        worker.evaluate(script: Script(name: Bundle.basalSetTemp))
        worker.evaluate(script: Script(name: Bundle.getLastGlucose))
        worker.evaluate(script: Script(name: Bundle.determineBasal))
        
        // Optional middleware for customization
        if let middleware = self.middlewareScript(name: OpenAPS.Middleware.determineBasal) {
            worker.evaluate(script: middleware)
        }
        
        return worker.call(function: Function.generate, with: [...])
    }
}
```

---

## Input Data Structures

### Glucose Status

```javascript
// glucose_status object passed to determine-basal
{
  "glucose": 120,           // Current BG in mg/dL
  "delta": -5,              // 5-min change
  "short_avgdelta": -4,     // 15-min average delta
  "long_avgdelta": -3,      // 45-min average delta
  "date": 1705410000000     // Timestamp (epoch ms)
}
```

### IOB Data

```javascript
// iob_data array from iob calculation
[{
  "iob": 1.5,
  "basaliob": 0.8,
  "bolussnooze": 0.3,
  "activity": 0.02,
  "lastBolusTime": 1705408800000,
  "time": "2026-01-16T12:00:00Z"
}]
```

### Meal Data

```javascript
// meal_data object from meal calculation
{
  "mealCOB": 20,
  "carbs": 45,
  "lastCarbTime": 1705408200000,
  "slopeFromMaxDeviation": 0.5,
  "slopeFromMinDeviation": -0.2,
  "usedMinCarbsImpact": true,
  "bwCarbs": 0,
  "bwFound": false
}
```

### Profile

```javascript
// profile object
{
  "max_iob": 8,
  "max_basal": 3,
  "min_bg": 100,
  "max_bg": 120,
  "target_bg": 110,
  "sens": 50,
  "carb_ratio": 10,
  "dia": 5,
  "current_basal": 1.0,
  "temptargetSet": false,
  // ... many more settings
}
```

### oref2 Variables

```swift
// trio:OpenAPS.swift#L121-L300
func oref2() -> RawJSON {
    // Fetches from CoreData:
    // - TDD history (10 days)
    // - Override settings
    // - Temp target slider state
    
    let averages = Oref2_variables(
        average_total_data: average14,      // 10-day TDD average
        weightedAverage: weighted_average,   // Weighted TDD
        past2hoursAverage: average2hours,    // Recent TDD
        isEnabled: temptargetActive,
        presetActive: isPercentageEnabled,
        overridePercentage: overridePercentage,
        useOverride: useOverride,
        duration: duration,
        unlimited: unlimited,
        hbt: hbt_,                           // Half-basal target
        overrideTarget: overrideTarget,
        smbIsOff: disableSMBs,
        advancedSettings: advancedSettings,
        isfAndCr: isfAndCr,                  // Override affects ISF and CR
        isf: isf,                            // Override affects ISF only
        cr: cr_,                             // Override affects CR only
        smbIsScheduledOff: smbIsScheduledOff,
        start: start,                        // SMB schedule start
        end: end,                            // SMB schedule end
        smbMinutes: smbMinutes,
        uamMinutes: uamMinutes
    )
}
```

---

## Algorithm Output (Suggestion)

### determine-basal.js Output

```javascript
// Return value from determine_basal()
{
  "reason": "COB: 20g; Dev: -15; BGI: -2.5; ISF: 50; CR: 10; ...",
  "units": 0.3,           // SMB amount (if any)
  "rate": 1.2,            // Temp basal rate
  "duration": 30,         // Temp basal duration (minutes)
  "deliverAt": "2026-01-16T12:00:00Z",
  "IOB": 1.5,
  "COB": 20,
  "eventualBG": 120,
  "sensitivityRatio": 1.0,
  "predBGs": {
    "IOB": [115, 110, 105, ...],
    "COB": [120, 125, 130, ...],
    "UAM": [115, 108, 102, ...],
    "ZT": [100, 95, 90, ...]
  },
  "bg": 120,
  "reservoir": 150,
  "insulinReq": 0.5,
  "carbsReq": 0,
  "TDD": 45.5,
  "insulin": {
    "TDD": 45.5,
    "bolus": 12.5,
    "temp_basal": 3.0,
    "scheduled_basal": 24.0
  },
  "current_target": 100,
  "minDelta": -8,
  "expectedDelta": -5,
  "minGuardBG": 85,
  "minPredBG": 90,
  "threshold": 65
}
```

### Swift Suggestion Model

```swift
// trio:Suggestion.swift#L3-L32
struct Suggestion: JSON, Equatable {
    let reason: String
    let units: Decimal?           // SMB units
    let insulinReq: Decimal?
    let eventualBG: Int?
    let sensitivityRatio: Decimal?
    let rate: Decimal?            // Temp basal rate
    let duration: Int?            // Temp basal duration
    let iob: Decimal?
    let cob: Decimal?
    var predictions: Predictions?
    let deliverAt: Date?
    let carbsReq: Decimal?
    let temp: TempType?
    let bg: Decimal?
    let reservoir: Decimal?
    let isf: Decimal?
    var timestamp: Date?
    var recieved: Bool?           // Enacted flag
    let tdd: Decimal?
    let insulin: Insulin?
    let current_target: Decimal?
    let insulinForManualBolus: Decimal?
    let manualBolusErrorString: Decimal?
    let minDelta: Decimal?
    let expectedDelta: Decimal?
    let minGuardBG: Decimal?
    let minPredBG: Decimal?
    let threshold: Decimal?
}
```

---

## Prediction Types

The algorithm produces four prediction curves:

| Curve | Description |
|-------|-------------|
| `IOB` | Prediction assuming only insulin on board affects BG |
| `COB` | Prediction including carb absorption |
| `UAM` | Unannounced meal prediction (uses deviation pattern) |
| `ZT` | Zero-temp prediction (what happens if basal stops) |

```swift
// trio:Suggestion.swift#L34-L39
struct Predictions: JSON, Equatable {
    let iob: [Int]?    // predBGs.IOB
    let zt: [Int]?     // predBGs.ZT
    let cob: [Int]?    // predBGs.COB
    let uam: [Int]?    // predBGs.UAM
}
```

---

## SMB Decision Logic

The determine-basal.js contains SMB enable/disable logic:

```javascript
// trio:trio-oref/lib/determine-basal/determine-basal.js#L47-L142
function enable_smb(profile, microBolusAllowed, meal_data, bg, target_bg, high_bg, oref_variables, time) {
    // Check scheduled SMB disable (override feature)
    if (oref_variables.smbIsScheduledOff) {
        // Check if current time is in disabled window
        if (currentHour >= startTime && currentHour < endTime) {
            return false;
        }
    }
    
    // Disable for high temp target
    if (!profile.allowSMB_with_high_temptarget && profile.temptargetSet && target_bg > 100) {
        return false;
    }
    
    // Disable for bolus wizard activity
    if (meal_data.bwFound && !profile.A52_risk_enable) {
        return false;
    }
    
    // Enable conditions (in order of priority):
    if (profile.enableSMB_always) return true;
    if (profile.enableSMB_with_COB && meal_data.mealCOB) return true;
    if (profile.enableSMB_after_carbs && meal_data.carbs) return true;
    if (profile.enableSMB_with_temptarget && target_bg < 100) return true;
    if (profile.enableSMB_high_bg && bg >= high_bg) return true;
    
    return false;
}
```

---

## Override Effects on Algorithm

When an override is active, Trio adjusts algorithm inputs:

```javascript
// trio:trio-oref/lib/determine-basal/determine-basal.js#L145-L203
var overrideFactor = 1;
var sensitivity = profile.sens;
var carbRatio = profile.carb_ratio;

if (oref2_variables.useOverride) {
    overrideFactor = oref2_variables.overridePercentage / 100;
    
    if (isfAndCr) {
        // Both ISF and CR scaled
        sensitivity /= overrideFactor;
        carbRatio /= overrideFactor;
    } else {
        // Individual scaling
        if (cr_) { carbRatio /= overrideFactor; }
        if (isf) { sensitivity /= overrideFactor; }
    }
}
```

---

## Autosens Calculation

```swift
// trio:OpenAPS.swift#L302-L331
func autosense() -> Future<Autosens?, Never> {
    Future { promise in
        self.processQueue.async {
            let autosensResult = self.autosense(
                glucose: glucose,
                pumpHistory: pumpHistory,
                basalprofile: basalProfile,
                profile: profile,
                carbs: carbs,
                temptargets: tempTargets
            )
            
            if var autosens = Autosens(from: autosensResult) {
                autosens.timestamp = Date()
                self.storage.save(autosens, as: Settings.autosense)
                promise(.success(autosens))
            }
        }
    }
}
```

### Autosens Output

```swift
// trio:Autosens.swift
struct Autosens: JSON {
    let ratio: Decimal          // Sensitivity ratio
    let newisf: Decimal?        // Adjusted ISF
    var timestamp: Date?
}
```

---

## Autotune

Trio supports autotune for profile optimization:

```swift
// trio:OpenAPS.swift#L333-L372
func autotune(categorizeUamAsBasal: Bool = false, tuneInsulinCurve: Bool = false) -> Future<Autotune?, Never> {
    // 1. Prepare autotune data
    let autotunePreppedGlucose = self.autotunePrepare(...)
    
    // 2. Run autotune
    let autotuneResult = self.autotuneRun(
        autotunePreparedData: autotunePreppedGlucose,
        previousAutotuneResult: previousAutotune ?? profile,
        pumpProfile: pumpProfile
    )
    
    // 3. Save result
    self.storage.save(autotuneResult, as: Settings.autotune)
}
```

---

## Middleware Support

Trio supports custom JavaScript middleware for algorithm modification:

```swift
// trio:OpenAPS.swift#L531-L533
if let middleware = self.middlewareScript(name: OpenAPS.Middleware.determineBasal) {
    worker.evaluate(script: middleware)
}
```

This allows advanced users to customize algorithm behavior without modifying core files.

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial algorithm documentation from source analysis |
