# Trio Insulin Mathematics

This document details how Trio calculates Insulin on Board (IOB) and related insulin metrics using the oref0 algorithm.

## Source Files

| File | Purpose |
|------|---------|
| `trio:trio-oref/lib/iob/index.js` | IOB calculation |
| `trio:Trio/Sources/APS/OpenAPS/OpenAPS.swift` | IOB function call |
| `trio:Trio/Sources/Models/IOBEntry.swift` | IOB data model |
| `trio:Trio/Sources/Models/Preferences.swift` | Insulin curve settings |

---

## IOB Calculation Flow

### OpenAPS.iob()

```swift
// trio:OpenAPS.swift#L433-L446
private func iob(pumphistory: JSON, profile: JSON, clock: JSON, autosens: JSON) -> RawJSON {
    dispatchPrecondition(condition: .onQueue(processQueue))
    return jsWorker.inCommonContext { worker in
        worker.evaluate(script: Script(name: Prepare.log))
        worker.evaluate(script: Script(name: Bundle.iob))
        worker.evaluate(script: Script(name: Prepare.iob))
        return worker.call(function: Function.generate, with: [
            pumphistory,
            profile,
            clock,
            autosens
        ])
    }
}
```

### JavaScript IOB Module

The IOB calculation in `trio-oref/lib/iob/` processes pump history to determine active insulin.

---

## IOB Data Structure

### IOBEntry Model

```swift
// trio:IOBEntry.swift
struct IOBEntry: JSON {
    let iob: Decimal             // Total IOB (units)
    let basaliob: Decimal?       // Basal IOB component
    let activity: Decimal?       // Insulin activity (units/min)
    let time: Date               // Calculation timestamp
    let bolussnooze: Decimal?    // Bolus snooze IOB
    let lastBolusTime: Date?     // Time of last bolus
}
```

### JSON Output

```javascript
// IOB calculation output
{
  "iob": 2.5,
  "basaliob": 0.8,
  "bolussnooze": 1.2,
  "activity": 0.035,
  "time": "2026-01-16T12:00:00Z",
  "lastBolusTime": 1705408800000
}
```

---

## IOB Components

### Total IOB

Total insulin on board from all sources:
```
IOB = bolusIOB + basalIOB
```

### Basal IOB

Insulin from temp basals above or below scheduled basal:
- Positive when temp basal > scheduled
- Negative when temp basal < scheduled (or suspended)

### Bolus Snooze IOB

IOB from recent boluses, used to prevent "stacking" additional boluses too soon after a manual bolus.

### Activity

Rate of insulin action (units/minute), used for:
- Calculating Blood Glucose Impact (BGI)
- Prediction calculations

---

## Insulin Curves

### Curve Types

```swift
// trio:Preferences.swift#L116-L122
enum InsulinCurve: String, JSON {
    case rapidActing = "rapid-acting"   // Peak ~75 min
    case ultraRapid = "ultra-rapid"     // Peak ~55 min
    case bilinear                       // Linear decay
}
```

### Configuration

```swift
// trio:Preferences.swift#L37-L39
var curve: InsulinCurve = .rapidActing
var useCustomPeakTime: Bool = false
var insulinPeakTime: Decimal = 75  // Minutes to peak activity
```

### Peak Times

| Curve | Default Peak | Description |
|-------|--------------|-------------|
| rapid-acting | 75 min | Humalog, NovoRapid, Apidra |
| ultra-rapid | 55 min | Fiasp, Lyumjev |
| bilinear | N/A | Simple linear decay |
| custom | User-defined | Set via `insulinPeakTime` |

---

## Insulin Model Mathematics

### Exponential Model

oref0 uses an exponential insulin model:

```javascript
// Conceptual formula from oref0
function insulinActivityCurve(minutesSinceDose, peakTime, dia) {
    // Time constants
    const tau = peakTime * (1 - peakTime / dia) / (1 - 2 * peakTime / dia);
    const a = 2 * tau / dia;
    const S = 1 / (1 - a + (1 + a) * Math.exp(-dia / tau));
    
    // Activity at time t
    const t = minutesSinceDose;
    const activity = S * (t / Math.pow(tau, 2)) * Math.exp(-t / tau);
    
    return activity;
}
```

### IOB from Activity

IOB is the integral of remaining activity:
```javascript
function iobFromActivity(minutesSinceDose, peakTime, dia) {
    // IOB = 1 - integral of activity from 0 to t
    const t = minutesSinceDose;
    const tau = calculateTau(peakTime, dia);
    const a = 2 * tau / dia;
    const S = 1 / (1 - a + (1 + a) * Math.exp(-dia / tau));
    
    const iob = 1 - S * (1 - a) * ((Math.pow(t, 2) / (tau * dia * (1 - a)) - t / tau - 1) * Math.exp(-t / tau) + 1);
    
    return Math.max(0, iob);
}
```

---

## Duration of Insulin Action (DIA)

### Configuration

```swift
// Stored in pump settings
let insulinActionCurve: Decimal  // DIA in hours
```

### Effect on IOB

| DIA | Description |
|-----|-------------|
| 3 hours | Faster insulin (Lyumjev) |
| 4 hours | Typical for ultra-rapid |
| 5 hours | Standard for rapid-acting |
| 6 hours | Conservative setting |

**Note**: Shorter DIA means IOB decays faster, potentially leading to insulin stacking if set too low.

---

## Blood Glucose Impact (BGI)

BGI is calculated from insulin activity and ISF:

```javascript
// BGI = insulin activity × ISF
bgi = activity * sens;
```

Where:
- `activity` = insulin activity (units/min)
- `sens` = insulin sensitivity factor (mg/dL per unit)

---

## IOB in Algorithm

The IOB array is used throughout determine-basal:

```javascript
// trio:trio-oref/lib/determine-basal/determine-basal.js
function determine_basal(glucose_status, currenttemp, iob_data, profile, ...) {
    var iob = iob_data[0].iob;
    var basaliob = iob_data[0].basaliob;
    var bgi = iob_data[0].activity * sens;
    
    // IOB limits insulin delivery
    if (iob > profile.max_iob) {
        // Block additional insulin
    }
    
    // BGI affects predicted glucose
    eventualBG = bg - bgi * (dia * 60 / 5);
}
```

---

## Autosens Effect on IOB

Autosens adjusts the effective sensitivity used in IOB calculations:

```swift
// trio:OpenAPS.swift#L47-L54
let autosens = self.loadFileFromStorage(name: Settings.autosense)
let iob = self.iob(
    pumphistory: pumpHistory,
    profile: profile,
    clock: clock,
    autosens: autosens.isEmpty ? .null : autosens
)
```

---

## Suspend Zeros IOB

```swift
// trio:Preferences.swift#L42
var suspendZerosIOB: Bool = false  // suspend_zeros_iob
```

When enabled:
- IOB is set to 0 during pump suspend
- Affects predictions during suspend periods

---

## Pump History Processing

IOB calculation requires pump history with:

| Event Type | Effect on IOB |
|------------|---------------|
| Bolus | Adds to IOB (full amount) |
| SMB | Adds to IOB (automatic bolus) |
| Temp Basal | Adds/subtracts from basalIOB |
| Suspend | Subtracts scheduled basal from IOB |
| Resume | Restores scheduled basal |

---

## Nightscout Sync

IOB is uploaded to devicestatus:

```json
{
  "openaps": {
    "iob": {
      "iob": 2.5,
      "basaliob": 0.8,
      "activity": 0.035,
      "time": "2026-01-16T12:00:00Z"
    }
  }
}
```

---

## Comparison with Other Systems

| Aspect | Trio (oref0) | Loop | AAPS |
|--------|--------------|------|------|
| Model | Exponential | Exponential | Biexponential |
| Peak Config | Via curve type | Via insulin model | Via plugin |
| DIA | Profile setting | Insulin model | Profile setting |
| Activity | Calculated | Calculated | Calculated |
| Autosens Effect | Yes | Via RC | Yes |

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial insulin math documentation from source analysis |
