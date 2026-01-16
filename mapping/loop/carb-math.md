# Loop Carb Math

This document details Loop's carbohydrate calculations as implemented in `CarbMath.swift` and related files.

## Overview

Loop's carb math provides:
1. **Absorption Models** - Multiple carb absorption curve types
2. **COB Calculation** - Carbs on board at any point in time
3. **Glucose Effects** - Expected glucose rise from carbs
4. **Dynamic Absorption** - Adaptive absorption based on observed glucose

---

## Absorption Models

### Source: `CarbMath.swift`
**File**: `loop:LoopKit/LoopKit/CarbKit/CarbMath.swift#L33-L82`

Loop defines a protocol for absorption models:

```swift
public protocol CarbAbsorptionComputable {
    func percentAbsorptionAtPercentTime(_ percentTime: Double) -> Double
    func percentTimeAtPercentAbsorption(_ percentAbsorption: Double) -> Double
    func absorptionTime(forPercentAbsorption percentAbsorption: Double, atTime time: TimeInterval) -> TimeInterval
    func absorbedCarbs(of total: Double, atTime time: TimeInterval, absorptionTime: TimeInterval) -> Double
    func unabsorbedCarbs(of total: Double, atTime time: TimeInterval, absorptionTime: TimeInterval) -> Double
    func percentRateAtPercentTime(_ percentTime: Double) -> Double
}
```

### 1. Linear Absorption

**File**: `loop:LoopKit/LoopKit/CarbKit/CarbMath.swift#L152-L183`

```swift
struct LinearAbsorption: CarbAbsorptionComputable {
    func percentAbsorptionAtPercentTime(_ percentTime: Double) -> Double {
        switch percentTime {
        case let t where t <= 0.0: return 0.0
        case let t where t < 1.0: return t
        default: return 1.0
        }
    }
}
```

**Behavior**: Constant absorption rate. At 50% of absorption time, 50% of carbs are absorbed.

```
Absorption Rate
     │
     │ ████████████████████████
     │ █                      █
     │ █                      █
     └─────────────────────────→ Time
       0%                   100%
```

### 2. Parabolic Absorption (Scheiner)

**File**: `loop:LoopKit/LoopKit/CarbKit/CarbMath.swift#L109-L148`

```swift
struct ParabolicAbsorption: CarbAbsorptionComputable {
    func percentAbsorptionAtPercentTime(_ percentTime: Double) -> Double {
        switch percentTime {
        case let t where t <= 0.0: return 0.0
        case let t where t <= 0.5: return 2.0 * pow(t, 2)
        case let t where t < 1.0: return -1.0 + 2.0 * t * (2.0 - t)
        default: return 1.0
        }
    }
}
```

**Behavior**: Based on Scheiner's GI curve from "Think Like a Pancreas". Starts slow, peaks at midpoint, slows down again.

```
Absorption Rate
     │
     │        ████████
     │      ██        ██
     │    ██            ██
     │  ██                ██
     └─────────────────────────→ Time
       0%      50%       100%
```

### 3. Piecewise Linear Absorption (Default)

**File**: `loop:LoopKit/LoopKit/CarbKit/CarbMath.swift#L190-L245`

```swift
public struct PiecewiseLinearAbsorption: CarbAbsorptionComputable {
    let percentEndOfRise = 0.15     // 15% of absorption time
    let percentStartOfFall = 0.5    // 50% of absorption time
    
    var scale: Double {
        return 2.0 / (1.0 + percentStartOfFall - percentEndOfRise)
    }
}
```

**Behavior**: 
1. **Rise phase (0-15%)**: Rate increases linearly from 0 to max
2. **Plateau phase (15-50%)**: Constant max rate
3. **Fall phase (50-100%)**: Rate decreases linearly to 0

```
Absorption Rate
     │
     │     ██████████████
     │    █              ██
     │   █                 ██
     │  █                    ██
     │ █                       █
     └─────────────────────────────→ Time
      0%  15%       50%        100%
```

**This is Loop's default absorption model.**

---

## COB Calculation

### Source: `CarbMath.swift`
**File**: `loop:LoopKit/LoopKit/CarbKit/CarbMath.swift#L247-L260`

```swift
func carbsOnBoard(at date: Date, defaultAbsorptionTime: TimeInterval, delay: TimeInterval, absorptionModel: CarbAbsorptionComputable) -> Double {
    let time = date.timeIntervalSince(startDate)
    let value: Double
    
    if time >= 0 {
        value = absorptionModel.unabsorbedCarbs(of: quantity.doubleValue(for: HKUnit.gram()), atTime: time - delay, absorptionTime: absorptionTime ?? defaultAbsorptionTime)
    } else {
        value = 0
    }
    
    return value
}
```

**Formula**:
```
COB = Total Grams × (1 - percentAbsorptionAtPercentTime(elapsed / absorptionTime))
```

### Timeline Generation

```swift
func carbsOnBoard(
    from start: Date? = nil,
    to end: Date? = nil,
    defaultAbsorptionTime: TimeInterval,
    absorptionModel: CarbAbsorptionComputable,
    delay: TimeInterval = TimeInterval(minutes: 10),
    delta: TimeInterval = TimeInterval(minutes: 5)
) -> [CarbValue] {
    // ... generate COB at each delta interval
}
```

---

## Glucose Effect Calculation

### Source: `CarbMath.swift`
**File**: `loop:LoopKit/LoopKit/CarbKit/CarbMath.swift#L279-L288`

```swift
fileprivate func glucoseEffect(
    at date: Date,
    carbRatio: HKQuantity,
    insulinSensitivity: HKQuantity,
    defaultAbsorptionTime: TimeInterval,
    delay: TimeInterval,
    absorptionModel: CarbAbsorptionComputable
) -> Double {
    return insulinSensitivity.doubleValue(for: HKUnit.milligramsPerDeciliter) / carbRatio.doubleValue(for: .gram()) * absorbedCarbs(at: date, absorptionTime: absorptionTime ?? defaultAbsorptionTime, delay: delay, absorptionModel: absorptionModel)
}
```

**Formula**:
```
Glucose Effect = (ISF / CR) × Absorbed Carbs
               = CSF × Absorbed Carbs

Where CSF (Carb Sensitivity Factor) = ISF / CR
```

**Example**: 
- ISF = 50 mg/dL per unit
- CR = 10g per unit
- CSF = 50/10 = 5 mg/dL per gram
- 30g carbs absorbed → 150 mg/dL rise expected

---

## Dynamic Absorption

Loop adapts carb absorption based on observed glucose behavior. This is the key differentiator from static models.

### CarbStatus

**File**: `loop:LoopKit/LoopKit/CarbKit/CarbStatus.swift`

```swift
public struct CarbStatus<T: CarbEntry> {
    public let entry: T
    public let absorption: AbsorbedCarbValue?
    
    // The observed absorption based on counteraction effects
    // Used to adapt the absorption model
}
```

### Dynamic Carb Mapping

**Source**: `CarbMath.swift` (collections extension)

Loop maps carb entries to observed insulin counteraction effects (ICE):
1. For each carb entry, look at ICE during the expected absorption window
2. If glucose rose more than insulin predicted → carbs are absorbing
3. Compute observed absorption rate vs expected rate
4. Adjust future carb effects accordingly

### Dynamic COB

**File**: `loop:LoopKit/LoopKit/CarbKit/CarbMath.swift#L444-L475`

```swift
public func dynamicCarbsOnBoard<T>(
    from start: Date? = nil,
    to end: Date? = nil,
    defaultAbsorptionTime: TimeInterval = TimeInterval(3 * 60 * 60),
    absorptionModel: CarbAbsorptionComputable = PiecewiseLinearAbsorption(),
    delay: TimeInterval = TimeInterval(10 * 60),
    delta: TimeInterval = TimeInterval(5 * 60)
) -> [CarbValue] where Element == CarbStatus<T>
```

Uses observed absorption to compute COB rather than assuming default absorption.

### Dynamic Glucose Effects

**File**: `loop:LoopKit/LoopKit/CarbKit/CarbMath.swift#L477-L516`

```swift
public func dynamicGlucoseEffects<T>(
    from start: Date? = nil,
    to end: Date? = nil,
    carbRatios: [AbsoluteScheduleValue<Double>],
    insulinSensitivities: [AbsoluteScheduleValue<HKQuantity>],
    defaultAbsorptionTime: TimeInterval = CarbMath.defaultAbsorptionTime,
    absorptionModel: CarbAbsorptionComputable = PiecewiseLinearAbsorption(),
    delay: TimeInterval = CarbMath.defaultEffectDelay,
    delta: TimeInterval = GlucoseMath.defaultDelta
) -> [GlucoseEffect] where Element == CarbStatus<T>
```

Computes future glucose effects using dynamically adapted absorption rates.

---

## Key Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `maximumAbsorptionTimeInterval` | 10 hr | Upper limit for carb absorption |
| `defaultAbsorptionTime` | 3 hr | Default if not specified |
| `defaultAbsorptionTimeOverrun` | 1.5 | Multiplier for max absorption time |
| `defaultEffectDelay` | 10 min | Delay before carbs start absorbing |

---

## Carb Entry Grouping

### Source: `CarbMath.swift`
**File**: `loop:LoopKit/LoopKit/CarbKit/CarbMath.swift#L338-L354`

```swift
func groupedByOverlappingAbsorptionTimes(
    defaultAbsorptionTime: TimeInterval
) -> [[Iterator.Element]] {
    var batches: [[Iterator.Element]] = []
    
    for entry in sorted(by: { $0.startDate < $1.startDate }) {
        if let lastEntry = batches.last?.last,
            lastEntry.startDate.addingTimeInterval(lastEntry.absorptionTime ?? defaultAbsorptionTime) > entry.startDate
        {
            batches[batches.count - 1].append(entry)
        } else {
            batches.append([entry])
        }
    }
    
    return batches
}
```

Groups carb entries with overlapping absorption windows for proper attribution of observed effects.

---

## Nightscout Alignment

### Carb Entry Upload

**Source**: `loop:NightscoutService/NightscoutServiceKit/Extensions/SyncCarbObject.swift`

Loop uploads carb entries to Nightscout `treatments`:

| Loop Field | Nightscout Field |
|------------|------------------|
| `quantity` | `carbs` |
| `startDate` | `timestamp` |
| `absorptionTime` | `absorptionTime` |
| `foodType` | `foodType` |
| `syncIdentifier` | `identifier` |

### COB Upload

Loop uploads COB to `devicestatus.loop.cob`:
```json
{
  "cob": {
    "timestamp": "2026-01-16T12:00:00Z",
    "cob": 45.5
  }
}
```

### Missing in Nightscout

1. **Absorption model type** - No field to indicate which model was used
2. **Observed absorption rate** - Dynamic absorption insights not synced
3. **Carb sensitivity factor** - Not explicitly stored
4. **Effect delay** - Assumed 10 min but not configurable per entry

### Alignment Opportunities

1. Add `absorptionModel` field to carb entries
2. Add `observedAbsorption` object showing actual vs expected
3. Include CSF in calculations metadata
