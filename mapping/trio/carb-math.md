# Trio Carbohydrate Mathematics

This document details how Trio calculates Carbs on Board (COB), meal detection, and Unannounced Meal (UAM) handling using the oref0 algorithm.

## Source Files

| File | Purpose |
|------|---------|
| `trio:trio-oref/lib/meal/index.js` | COB and meal calculation |
| `trio:Trio/Sources/APS/OpenAPS/OpenAPS.swift` | Meal function call |
| `trio:Trio/Sources/Models/CarbsEntry.swift` | Carbs data model |
| `trio:Trio/Sources/Models/Preferences.swift` | COB settings |

---

## COB Calculation Flow

### OpenAPS.meal()

```swift
// trio:OpenAPS.swift#L448-L463
private func meal(pumphistory: JSON, profile: JSON, basalProfile: JSON, 
                  clock: JSON, carbs: JSON, glucose: JSON) -> RawJSON {
    dispatchPrecondition(condition: .onQueue(processQueue))
    return jsWorker.inCommonContext { worker in
        worker.evaluate(script: Script(name: Prepare.log))
        worker.evaluate(script: Script(name: Bundle.meal))
        worker.evaluate(script: Script(name: Prepare.meal))
        return worker.call(function: Function.generate, with: [
            pumphistory,
            profile,
            clock,
            glucose,
            basalProfile,
            carbs
        ])
    }
}
```

---

## Meal Data Structure

### JavaScript Output

```javascript
// Meal calculation output
{
  "mealCOB": 25,                    // Current COB (grams)
  "carbs": 50,                      // Total carbs in window
  "lastCarbTime": 1705408200000,    // Last carb entry time
  "slopeFromMaxDeviation": 0.5,     // BG rise slope from max
  "slopeFromMinDeviation": -0.2,    // BG fall slope from min
  "usedMinCarbsImpact": true,       // Used min carb impact
  "bwCarbs": 0,                     // Bolus Wizard carbs
  "bwFound": false                  // Bolus Wizard detected
}
```

---

## COB Decay Model

### Linear Decay

oref0 uses linear carb absorption:

```javascript
// Conceptual COB decay
function cobDecay(carbsInput, absorptionTime, minutesSinceEntry) {
    const carbsAbsorbed = (minutesSinceEntry / absorptionTime) * carbsInput;
    const cob = Math.max(0, carbsInput - carbsAbsorbed);
    return cob;
}
```

### Absorption Time

Carb absorption time is calculated from carb ratio and ISF:

```javascript
// Default: 3-4 hours depending on profile
absorptionTime = carb_ratio * sens * 3;  // Simplified
```

---

## Minimum Carb Impact

### Configuration

```swift
// trio:Preferences.swift#L22
var min5mCarbimpact: Decimal = 8  // min_5m_carbimpact (mg/dL per 5 min)
```

### Purpose

When observed BG rise is less than expected from COB:
- Algorithm assumes at least `min5mCarbimpact` absorption
- Prevents COB from persisting indefinitely
- Accelerates COB decay when absorption is slow

### Usage

```javascript
// In meal calculation
if (observedCarbImpact < min5mCarbimpact) {
    // Use minimum impact to decay COB
    actualCarbImpact = min5mCarbimpact;
    usedMinCarbsImpact = true;
}
```

---

## UAM (Unannounced Meals)

### Detection

UAM detects carb absorption when no carbs are entered:

```swift
// trio:Preferences.swift#L26
var enableUAM: Bool = false  // enableUAM
```

### Mechanism

1. Algorithm calculates expected BG based on IOB
2. Compares expected vs actual BG
3. If BG is rising more than expected:
   - Positive deviation detected
   - UAM assumes carb absorption is occurring
   - Algorithm responds with increased insulin

### UAM Prediction

```javascript
// UAM prediction in predBGs
predBGs.UAM = [];  // Prediction assuming unannounced meal absorption
```

---

## COB Limits

### Maximum COB

```swift
// trio:Preferences.swift#L18
var maxCOB: Decimal = 120  // maxCOB (grams)
```

COB is capped at this value to prevent unrealistic carb tracking.

### Remaining Carbs

```swift
// trio:Preferences.swift#L24-L25
var remainingCarbsFraction: Decimal = 1.0
var remainingCarbsCap: Decimal = 90
```

Controls how remaining carbs are factored into predictions.

---

## Carb Entry Model

### CarbsEntry

```swift
// trio:CarbsEntry.swift
struct CarbsEntry: JSON {
    let id: String?
    let createdAt: Date          // Entry timestamp
    var carbs: Decimal           // Carb grams
    var fat: Decimal?            // Fat grams (for FPU)
    var protein: Decimal?        // Protein grams (for FPU)
    let note: String?
    var enteredBy: String?
    var fpuID: String?           // Fat-Protein-Unit tracking ID
}
```

### Fat and Protein Units (FPU)

Trio supports extended carb entries for fat and protein:
- Fat and protein are converted to "fake carbs"
- Absorbed over extended period (hours)
- Tracked via `fpuID` for deletion

---

## Carb Window

The meal calculation looks back over a carb window (typically 6 hours):

```javascript
// Carb window for meal detection
const carbWindow = 6 * 60;  // 6 hours in minutes
```

This affects:
- Total carbs considered
- `enableSMB_after_carbs` timing
- Bolus Wizard detection

---

## Bolus Wizard Detection

```javascript
// In meal_data
{
  "bwCarbs": 25,      // Carbs from Bolus Wizard
  "bwFound": true     // Bolus Wizard activity detected
}
```

When Bolus Wizard is detected:
- SMBs may be disabled (safety)
- `A52_risk_enable` controls this behavior

---

## Carb Ratio Effect

Carb ratio affects glucose predictions:

```javascript
// Carb effect on glucose
carbEffect = carbs * (sens / carb_ratio);
```

Where:
- `carbs` = COB (grams)
- `sens` = ISF (mg/dL per unit)
- `carb_ratio` = CR (grams per unit)

---

## Nightscout Carb Sync

### Upload

Carbs are uploaded as treatments:

```json
{
  "eventType": "Carb Correction",
  "created_at": "2026-01-16T12:00:00.000Z",
  "enteredBy": "Trio",
  "carbs": 45,
  "fat": 10,
  "protein": 15,
  "notes": "Lunch"
}
```

### Download

Carbs are fetched from Nightscout:

```swift
// trio:NightscoutAPI.swift#L101-L142
func fetchCarbs(sinceDate: Date? = nil) -> AnyPublisher<[CarbsEntry], Swift.Error> {
    components.queryItems = [
        URLQueryItem(name: "find[carbs][$exists]", value: "true"),
        URLQueryItem(name: "find[enteredBy][$ne]", value: CarbsEntry.manual),
        URLQueryItem(name: "find[enteredBy][$ne]", value: NightscoutTreatment.local)
    ]
}
```

**Note**: Trio excludes its own carb entries to avoid duplicates.

### Delete

Carbs can be deleted via Nightscout:

```swift
// trio:NightscoutManager.swift#L179-L234
func deleteCarbs(at date: Date, isFPU: Bool?, fpuID: String?, syncID: String) {
    // Deletes from HealthKit
    healthkitManager.deleteCarbs(syncID: syncID, fpuID: fpuID ?? "")
    
    // Deletes from Nightscout
    if let isFPU = isFPU, isFPU {
        // Delete all FPU entries with matching fpuID
        let dates = allValues.filter { $0.fpuID == fpuID }.map(\.createdAt)
        // Delete each date
    } else {
        nightscout.deleteCarbs(at: date)
    }
}
```

---

## COB in Algorithm

COB affects predictions and dosing:

```javascript
// trio:trio-oref/lib/determine-basal/determine-basal.js
// COB prediction
if (meal_data.mealCOB > 0) {
    // Include carb effect in predictions
    predBGs.COB = calculateCOBPrediction(...);
}

// SMB enable with COB
if (profile.enableSMB_with_COB && meal_data.mealCOB) {
    smbEnabled = true;
}
```

---

## Deviation Analysis

The meal module calculates glucose deviations:

| Metric | Description |
|--------|-------------|
| `slopeFromMaxDeviation` | Rate of BG rise from maximum deviation point |
| `slopeFromMinDeviation` | Rate of BG fall from minimum deviation point |

Used for:
- UAM detection
- Carb absorption rate estimation
- Prediction refinement

---

## Comparison with Other Systems

| Aspect | Trio (oref0) | Loop | AAPS |
|--------|--------------|------|------|
| Absorption Model | Linear decay | Dynamic/adaptive | Linear (oref0-based) |
| Min Carb Impact | Yes (min_5m_carbimpact) | Yes (min absorption) | Yes |
| UAM | Yes | No | Yes |
| FPU/eCarbs | Yes | Via absorption time | Yes (eCarbs) |
| Max COB | Configurable | Implicit | Configurable |

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial carb math documentation from source analysis |
