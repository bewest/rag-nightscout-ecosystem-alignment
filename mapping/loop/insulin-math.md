# Loop Insulin Math

This document details Loop's insulin calculations as implemented in `InsulinMath.swift` and related files.

## Overview

Loop's insulin math handles:
1. **IOB Calculation** - Tracking insulin remaining to act
2. **Glucose Effects** - Computing expected glucose change from insulin
3. **Dose Reconciliation** - Cleaning up overlapping/inconsistent pump data
4. **Basal Annotation** - Overlaying scheduled rates onto delivery records

---

## Insulin Models

### Source: `ExponentialInsulinModelPreset.swift`
**File**: `loop:LoopKit/LoopKit/Insulin/ExponentialInsulinModelPreset.swift`

Loop uses **exponential insulin models** with configurable parameters:

| Preset | Action Duration | Peak Activity | Delay |
|--------|-----------------|---------------|-------|
| `rapidActingAdult` | 360 min (6 hr) | 75 min | 10 min |
| `rapidActingChild` | 360 min (6 hr) | 65 min | 10 min |
| `fiasp` | 360 min (6 hr) | 55 min | 10 min |
| `lyumjev` | 360 min (6 hr) | 55 min | 10 min |
| `afrezza` | 300 min (5 hr) | 29 min | 10 min |

### Key Methods

```swift
public protocol InsulinModel {
    var effectDuration: TimeInterval { get }
    func percentEffectRemaining(at time: TimeInterval) -> Double
}
```

- `effectDuration` - How long insulin remains active (DIA)
- `percentEffectRemaining(at:)` - Returns 0.0-1.0 indicating how much insulin effect remains

### Model Selection

```swift
public struct PresetInsulinModelProvider: InsulinModelProvider {
    public func model(for type: InsulinType?) -> InsulinModel {
        switch type {
        case .fiasp: return ExponentialInsulinModelPreset.fiasp
        case .lyumjev: return ExponentialInsulinModelPreset.lyumjev
        case .afrezza: return ExponentialInsulinModelPreset.afrezza
        default: return defaultRapidActingModel ?? ExponentialInsulinModelPreset.rapidActingAdult
        }
    }
}
```

Loop selects insulin model based on `insulinType` field in dose entries, falling back to user's default.

---

## IOB Calculation

### Source: `InsulinMath.swift`
**File**: `loop:LoopKit/LoopKit/InsulinKit/InsulinMath.swift#L17-L51`

### For Momentary Doses (boluses, short temps)

```swift
func insulinOnBoard(at date: Date, model: InsulinModel, delta: TimeInterval) -> Double {
    let time = date.timeIntervalSince(startDate)
    guard time >= 0 else { return 0 }
    
    // Consider doses within the delta time window as momentary
    if endDate.timeIntervalSince(startDate) <= 1.05 * delta {
        return netBasalUnits * model.percentEffectRemaining(at: time)
    } else {
        return netBasalUnits * continuousDeliveryInsulinOnBoard(at: date, model: model, delta: delta)
    }
}
```

**Logic**:
- If dose duration ≤ 1.05× delta (typically 5.25 min), treat as instantaneous
- IOB = dose units × percent effect remaining at current time

### For Continuous Doses (extended temps)

```swift
private func continuousDeliveryInsulinOnBoard(at date: Date, model: InsulinModel, delta: TimeInterval) -> Double {
    let doseDuration = endDate.timeIntervalSince(startDate)
    let time = date.timeIntervalSince(startDate)
    var iob: Double = 0
    var doseDate = TimeInterval(0)
    
    repeat {
        let segment: Double
        if doseDuration > 0 {
            segment = max(0, min(doseDate + delta, doseDuration) - doseDate) / doseDuration
        } else {
            segment = 1
        }
        iob += segment * model.percentEffectRemaining(at: time - doseDate)
        doseDate += delta
    } while doseDate <= min(floor((time + model.delay) / delta) * delta, doseDuration)
    
    return iob
}
```

**Logic**:
- Divide dose into segments of `delta` duration
- For each segment, compute IOB based on when that segment was delivered
- Sum all segments

This properly handles extended boluses and temp basals where insulin was delivered over time.

---

## Glucose Effect Calculation

### Source: `InsulinMath.swift`
**File**: `loop:LoopKit/LoopKit/InsulinKit/InsulinMath.swift#L75-L88`

```swift
func glucoseEffect(at date: Date, model: InsulinModel, insulinSensitivity: Double, delta: TimeInterval) -> Double {
    let time = date.timeIntervalSince(startDate)
    guard time >= 0 else { return 0 }
    
    // Consider doses within the delta time window as momentary
    if endDate.timeIntervalSince(startDate) <= 1.05 * delta {
        return netBasalUnits * -insulinSensitivity * (1.0 - model.percentEffectRemaining(at: time))
    } else {
        return netBasalUnits * -insulinSensitivity * continuousDeliveryGlucoseEffect(at: date, model: model, delta: delta)
    }
}
```

**Formula**:
```
Glucose Effect = Units × (-ISF) × (1 - percentEffectRemaining)
```

- Negative because insulin lowers glucose
- Effect increases as insulin acts (percentEffectRemaining decreases)
- At time 0: effect = 0 (no insulin has acted yet)
- At end of DIA: effect = -Units × ISF (full effect realized)

---

## Net Basal Units

### Source: `DoseEntry.swift`
**File**: `loop:LoopKit/LoopKit/InsulinKit/DoseEntry.swift#L92-L115`

```swift
public var netBasalUnits: Double {
    switch type {
    case .bolus:
        return deliveredUnits ?? programmedUnits
    case .basal:
        return 0
    case .resume, .suspend, .tempBasal:
        break
    }
    
    guard hours > 0 else { return 0 }
    
    let scheduledUnitsPerHour: Double
    if let basalRate = scheduledBasalRate {
        scheduledUnitsPerHour = basalRate.doubleValue(for: DoseEntry.unitsPerHour)
    } else {
        scheduledUnitsPerHour = 0
    }
    
    let scheduledUnits = scheduledUnitsPerHour * hours
    return unitsInDeliverableIncrements - scheduledUnits
}
```

**Key insight**: For temp basals, Loop computes **net** units relative to scheduled basal:
- Temp at 2.0 U/hr for 30 min with scheduled 1.0 U/hr = (2.0 × 0.5) - (1.0 × 0.5) = **+0.5 U net**
- Suspend for 30 min with scheduled 1.0 U/hr = (0.0 × 0.5) - (1.0 × 0.5) = **-0.5 U net**

This allows IOB calculation to account for both above-basal and below-basal delivery.

---

## Dose Reconciliation

### Source: `InsulinMath.swift`
**File**: `loop:LoopKit/LoopKit/InsulinKit/InsulinMath.swift#L396-L520`

Loop must handle messy real-world pump data where entries can overlap or have gaps.

```swift
func reconciled() -> [DoseEntry] {
    var reconciled: [DoseEntry] = []
    var lastSuspend: DoseEntry?
    var lastBasal: DoseEntry?
    
    for dose in self {
        switch dose.type {
        case .bolus:
            reconciled.append(dose)
        case .basal, .tempBasal:
            // Handle overlapping temps...
        case .resume:
            // Pair with preceding suspend...
        case .suspend:
            // Start tracking suspend period...
        }
    }
    // ... handle trailing entries
}
```

### Reconciliation Rules

1. **Boluses** - Always kept as-is
2. **Overlapping temps** - Previous temp is trimmed to end when new temp starts
3. **Suspend** - Creates a zero-delivery period until resume
4. **Resume** - Ends the suspend period, may continue previous temp if it extends beyond resume
5. **Missing resume** - If temp basal follows suspend without resume, assume resume at temp start
6. **Trailing suspend** - Marked as mutable (not finalized)

### Example

```
Input:
  TempBasal 2.0 U/hr: 10:00-10:30
  Suspend:            10:15
  Resume:             10:25
  TempBasal 1.5 U/hr: 10:30-11:00

Output (reconciled):
  TempBasal 2.0 U/hr: 10:00-10:15  (trimmed by suspend)
  Suspend:            10:15-10:25
  TempBasal 2.0 U/hr: 10:25-10:30  (continued after resume)
  TempBasal 1.5 U/hr: 10:30-11:00
```

---

## Basal Annotation

### Source: `InsulinMath.swift`
**File**: `loop:LoopKit/LoopKit/InsulinKit/InsulinMath.swift#L263-L319`

Before computing effects, doses are annotated with scheduled basal rates:

```swift
fileprivate func annotated(with basalSchedule: BasalRateSchedule) -> [DoseEntry] {
    switch type {
    case .tempBasal, .suspend, .resume:
        guard scheduledBasalRate == nil else { return [self] }
        break
    case .basal, .bolus:
        return [self]
    }
    
    let basalItems = basalSchedule.between(start: startDate, end: endDate)
    return annotated(with: basalItems)
}
```

### Schedule Boundary Splitting

```swift
fileprivate func annotated(with basalHistory: [AbsoluteScheduleValue<Double>]) -> [DoseEntry] {
    var doses: [DoseEntry] = []
    
    for (index, basalItem) in basalHistory.enumerated() {
        // ... split logic
        var dose = trimmed(from: startDate, to: endDate, syncIdentifier: syncIdentifier)
        dose.scheduledBasalRate = HKQuantity(unit: DoseEntry.unitsPerHour, doubleValue: basalItem.value)
        doses.append(dose)
    }
    
    return doses
}
```

**Key behavior**: If a temp basal crosses a schedule boundary (e.g., basal changes from 1.0 to 0.8 at midnight), Loop splits it into two entries with appropriate scheduled rates.

---

## IOB Timeline Generation

### Source: `InsulinMath.swift`
**File**: `loop:LoopKit/LoopKit/InsulinKit/InsulinMath.swift#L578-L602`

```swift
public func insulinOnBoard(
    insulinModelProvider: InsulinModelProvider = PresetInsulinModelProvider(defaultRapidActingModel: nil),
    longestEffectDuration: TimeInterval = InsulinMath.defaultInsulinActivityDuration,
    from start: Date? = nil,
    to end: Date? = nil,
    delta: TimeInterval = TimeInterval(5*60)
) -> [InsulinValue] {
    guard let (start, end) = LoopMath.simulationDateRangeForSamples(self, from: start, to: end, duration: longestEffectDuration, delta: delta) else {
        return []
    }
    
    var date = start
    var values = [InsulinValue]()
    
    repeat {
        let value = reduce(0) { (value, dose) -> Double in
            return value + dose.insulinOnBoard(at: date, model: insulinModelProvider.model(for: dose.insulinType), delta: delta)
        }
        values.append(InsulinValue(startDate: date, value: value))
        date = date.addingTimeInterval(delta)
    } while date <= end
    
    return values
}
```

Generates a timeline of IOB values at `delta` intervals by summing IOB from all doses at each timestamp.

---

## Key Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `defaultInsulinActivityDuration` | 6 hr 10 min | Default DIA for IOB calculations |
| `minimumMinimedIncrementPerUnit` | 20 | Rounding factor for Medtronic pump delivery |
| `delta` (default) | 5 min | Time step for IOB/effect calculations |

---

## Nightscout Alignment

### Dose Upload Mapping

**Source**: `loop:NightscoutService/NightscoutServiceKit/Extensions/DoseEntry.swift`

| Loop `DoseEntry.type` | Nightscout Treatment |
|-----------------------|---------------------|
| `.bolus` | `BolusNightscoutTreatment` |
| `.tempBasal` | `TempBasalNightscoutTreatment` |
| `.suspend` | `TempBasalNightscoutTreatment` with `rate: 0`, `reason: "suspend"` |
| `.resume` | Not uploaded (paired with suspend) |
| `.basal` | Not uploaded (scheduled basal) |

### IOB Upload

Loop uploads IOB to `devicestatus.loop.iob`:
```json
{
  "iob": {
    "timestamp": "2026-01-16T12:00:00Z",
    "iob": 2.35
  }
}
```

### Missing Fields

Loop dose uploads include:
- `syncIdentifier` - Unique ID for syncing
- `automatic` - Whether Loop commanded the dose
- `insulinType` - Brand name if known

Nightscout could benefit from:
- Net basal units (relative to scheduled)
- Scheduled basal rate at time of dose
- Insulin model parameters used
