# Loop Prediction Algorithm

This document details Loop's prediction algorithm as implemented in `LoopAlgorithm.swift` and `LoopMath.swift`.

## Overview

Loop uses a **prediction-based control loop** that:
1. Computes multiple glucose effect timelines (insulin, carbs, momentum, retrospective correction)
2. Combines these effects to predict future glucose
3. Uses the prediction to determine dose recommendations

**Key Principle**: Loop predicts glucose into the future, then works backward to determine what dosing action (if any) would keep predicted glucose in range.

---

## Effect Computation Pipeline

### Source: `LoopAlgorithm.generatePrediction()`
**File**: `loop:LoopKit/LoopKit/LoopAlgorithm/LoopAlgorithm.swift#L73-L188`

```swift
public static func generatePrediction(input: LoopPredictionInput, startDate: Date? = nil) throws -> LoopPrediction
```

### Step 1: Annotate Doses with Basal Schedule

```swift
let annotatedDoses = input.doses.annotated(with: input.settings.basal)
```

Before computing insulin effects, Loop overlays the basal rate schedule onto dose entries. This converts temp basals into net delivery relative to scheduled basal:

- **Temp basal at 2.0 U/hr** with scheduled 1.0 U/hr → **net +1.0 U/hr**
- **Temp basal at 0.5 U/hr** with scheduled 1.0 U/hr → **net -0.5 U/hr**
- **Suspend** with scheduled 1.0 U/hr → **net -1.0 U/hr**

**Important**: Doses crossing schedule boundaries are split into multiple entries, each with its own scheduled basal rate.

### Step 2: Compute Insulin Effects

```swift
let insulinEffects = annotatedDoses.glucoseEffects(
    insulinModelProvider: insulinModelProvider,
    longestEffectDuration: settings.insulinActivityDuration,
    insulinSensitivityHistory: settings.sensitivity,
    from: start.addingTimeInterval(-CarbMath.maximumAbsorptionTimeInterval).dateFlooredToTimeInterval(settings.delta),
    to: nil)
```

Computes expected glucose change from all insulin doses, considering:
- Insulin model (exponential decay curve)
- Insulin sensitivity schedule (ISF)
- Dose type (bolus vs temp basal vs suspend)

### Step 3: Compute Insulin Counteraction Effects (ICE)

```swift
let insulinCounteractionEffects = input.glucoseHistory.counteractionEffects(to: insulinEffects)
```

**This is critical for carb absorption estimation.**

ICE measures the difference between:
- Actual glucose change (observed from CGM)
- Expected glucose change (from insulin effects alone)

**Formula**:
```
ICE = (Actual Glucose Change) - (Expected Insulin Effect)
```

If glucose rose more than insulin predicted, ICE is positive → carbs are absorbing.
If glucose fell more than insulin predicted, ICE is negative → something else is happening.

**Source**: `loop:LoopKit/LoopKit/GlucoseKit/GlucoseMath.swift#L151-L229`

### Step 4: Compute Carb Effects (Dynamic)

```swift
let carbEffects = input.carbEntries.map(
    to: insulinCounteractionEffects,
    carbRatio: settings.carbRatio,
    insulinSensitivity: settings.sensitivity
).dynamicGlucoseEffects(
    from: start.addingTimeInterval(-IntegralRetrospectiveCorrection.retrospectionInterval),
    carbRatios: settings.carbRatio,
    insulinSensitivities: settings.sensitivity
)
```

Loop's carb effects are **dynamic** - they adapt based on observed glucose behavior:
1. Map carb entries to observed counteraction effects
2. Adjust absorption rate based on how carbs appear to be absorbing
3. Compute future carb effects using the adjusted absorption model

**Key insight**: Unlike static carb models, Loop's dynamic absorption can speed up or slow down based on real observations.

### Step 5: Compute Retrospective Correction

```swift
let retrospectiveGlucoseDiscrepancies = insulinCounteractionEffects.subtracting(carbEffects)
let retrospectiveGlucoseDiscrepanciesSummed = retrospectiveGlucoseDiscrepancies.combinedSums(of: LoopMath.retrospectiveCorrectionGroupingInterval * 1.01)

let rcEffect = rc.computeEffect(
    startingAt: latestGlucose,
    retrospectiveGlucoseDiscrepanciesSummed: retrospectiveGlucoseDiscrepanciesSummed,
    recencyInterval: TimeInterval(minutes: 15),
    insulinSensitivity: curSensitivity,
    basalRate: curBasal,
    correctionRange: curTarget,
    retrospectiveCorrectionGroupingInterval: LoopMath.retrospectiveCorrectionGroupingInterval
)
```

**Retrospective Correction (RC)** accounts for unexplained glucose discrepancies:
```
RC Input = ICE - Carb Effects
```

If ICE exceeds carb effects, something else is raising glucose (exercise, stress, etc).
If carb effects exceed ICE, something else is lowering glucose.

**Two RC implementations**:
1. **StandardRetrospectiveCorrection** - Simple proportional effect
2. **IntegralRetrospectiveCorrection** - PID-like controller with integral and differential terms

### Step 6: Compute Momentum Effect

```swift
let momentumInputData = input.glucoseHistory.filterDateRange(start.addingTimeInterval(-GlucoseMath.momentumDataInterval), start)
momentumEffects = momentumInputData.linearMomentumEffect()
```

Momentum uses **linear regression** on the last 15 minutes of glucose readings to project short-term trajectory.

**Source**: `loop:LoopKit/LoopKit/GlucoseKit/GlucoseMath.swift#L84-L128`

**Constraints**:
- Requires at least 3 readings
- Readings must be continuous (no gaps > 5 min)
- No calibration entries in the window
- All from same source (provenance)
- Maximum velocity: 4 mg/dL/min

### Step 7: Combine Effects into Prediction

```swift
var prediction = LoopMath.predictGlucose(startingAt: latestGlucose, momentum: momentumEffects, effects: effects)
```

**Source**: `loop:LoopKit/LoopKit/LoopMath.swift#L118-L175`

---

## Effect Combination Logic

### `LoopMath.predictGlucose()`
**File**: `loop:LoopKit/LoopKit/LoopMath.swift#L99-L175`

This function combines multiple effect timelines into a single glucose prediction:

```swift
public static func predictGlucose(startingAt startingGlucose: GlucoseValue, momentum: [GlucoseEffect] = [], effects: [[GlucoseEffect]]) -> [PredictedGlucoseValue]
```

### Step 1: Sum Non-Momentum Effects

```swift
for timeline in effects {
    var previousEffectValue: Double = timeline.first?.quantity.doubleValue(for: unit) ?? 0
    
    for effect in timeline {
        let value = effect.quantity.doubleValue(for: unit)
        effectValuesAtDate[effect.startDate] = (effectValuesAtDate[effect.startDate] ?? 0) + value - previousEffectValue
        previousEffectValue = value
    }
}
```

For each effect timeline (insulin, carbs, RC), Loop:
1. Computes the **delta** between consecutive effect values
2. Sums all deltas at each timestamp across timelines

**Key insight**: Effects are stored as cumulative values, but prediction uses deltas.

### Step 2: Blend Momentum

```swift
if momentum.count > 1 {
    // ... momentum blending logic
    let blendSlope = 1.0 / Double(blendCount)
    
    for (index, effect) in momentum.enumerated() {
        let split = min(1.0, max(0.0, Double(momentum.count - index) / Double(blendCount) - blendSlope + blendOffset))
        let effectBlend = (1.0 - split) * (effectValuesAtDate[effect.startDate] ?? 0)
        let momentumBlend = split * effectValueChange
        
        effectValuesAtDate[effect.startDate] = effectBlend + momentumBlend
    }
}
```

**Momentum is blended linearly** with other effects:
- At time 0 (current glucose): 100% momentum
- At end of momentum duration: 0% momentum, 100% other effects
- Linear interpolation between

This prevents momentum from dominating the entire prediction while capturing immediate glucose trajectory.

### Step 3: Accumulate Prediction

```swift
let prediction = effectValuesAtDate.sorted { $0.0 < $1.0 }.reduce([PredictedGlucoseValue(startDate: startingGlucose.startDate, quantity: startingGlucose.quantity)]) { (prediction, effect) -> [PredictedGlucoseValue] in
    if effect.0 > startingGlucose.startDate, let lastValue = prediction.last {
        let nextValue = PredictedGlucoseValue(
            startDate: effect.0,
            quantity: HKQuantity(unit: unit, doubleValue: effect.1 + lastValue.quantity.doubleValue(for: unit))
        )
        return prediction + [nextValue]
    } else {
        return prediction
    }
}
```

Starting from current glucose, Loop accumulates effect deltas to build the prediction timeline.

---

## Key Constants

| Constant | Value | Location | Purpose |
|----------|-------|----------|---------|
| `retrospectiveCorrectionGroupingInterval` | 30 min | LoopMath | Window for aggregating discrepancies |
| `retrospectiveCorrectionEffectDuration` | 60 min | LoopMath | How long RC effect lasts |
| `momentumDataInterval` | 15 min | GlucoseMath | How much glucose history for momentum |
| `momentumDuration` | 15 min | GlucoseMath | How far momentum projects |
| `defaultDelta` | 5 min | GlucoseMath | Time step for effect timelines |
| `maximumAbsorptionTimeInterval` | 10 hr | CarbMath | Maximum carb absorption window |

---

## Output Structure

### `LoopPrediction`

```swift
public struct LoopPrediction: GlucosePrediction {
    public var glucose: [PredictedGlucoseValue]
    public var effects: LoopAlgorithmEffects
}

public struct LoopAlgorithmEffects {
    public var insulin: [GlucoseEffect]
    public var carbs: [GlucoseEffect]
    public var retrospectiveCorrection: [GlucoseEffect]
    public var momentum: [GlucoseEffect]
    public var insulinCounteraction: [GlucoseEffectVelocity]
}
```

The prediction includes both:
1. The final glucose prediction timeline
2. All individual effect timelines (for debugging/analysis)

---

## Algorithm Variants

Loop supports two **AlgorithmEffectsOptions** configurations:

```swift
public struct AlgorithmEffectsOptions: OptionSet {
    public static let carbs            = AlgorithmEffectsOptions(rawValue: 1 << 0)
    public static let insulin          = AlgorithmEffectsOptions(rawValue: 1 << 1)
    public static let momentum         = AlgorithmEffectsOptions(rawValue: 1 << 2)
    public static let retrospection    = AlgorithmEffectsOptions(rawValue: 1 << 3)
    
    public static let all: AlgorithmEffectsOptions = [.carbs, .insulin, .momentum, .retrospection]
}
```

By default, all effects are included. This can be configured for testing or specialized use cases.

---

## Nightscout Alignment Notes

### What Loop Uploads

Loop uploads to `devicestatus.loop`:
- `predicted.values[]` - The final prediction array
- `iob` - Insulin on board
- `cob` - Carbs on board

### What's Missing

Loop does **not** upload individual effect timelines to Nightscout. For full algorithm transparency, consider uploading:
- `effects.insulin[]`
- `effects.carbs[]`
- `effects.momentum[]`
- `effects.retrospectiveCorrection[]`
- `effects.insulinCounteraction[]`

### Prediction Format Differences

| Loop | Nightscout (oref0-style) |
|------|--------------------------|
| Single `predicted[]` array | Separate `predBGs.IOB[]`, `predBGs.COB[]`, `predBGs.UAM[]`, `predBGs.ZT[]` |
| Effects pre-combined | Effects kept separate |
| Momentum blended in | Momentum can be separate |
