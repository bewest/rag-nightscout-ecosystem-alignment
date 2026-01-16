# Loop Dose Math

This document details Loop's dosing logic as implemented in `DoseMath.swift`.

## Overview

Loop's dose math handles:
1. **Correction Calculations** - Determining insulin needed to reach target
2. **Temp Basal Recommendations** - When to adjust delivery rate
3. **Bolus Recommendations** - Manual and automatic bolus suggestions
4. **Safety Constraints** - Guardrails and limits

---

## Dosing Decision Flow

### Source: `DoseMath.swift`
**File**: `loop:LoopKit/LoopKit/LoopAlgorithm/DoseMath.swift`

Loop determines dosing in this order:
1. Check if looping is enabled
2. Evaluate predicted glucose against targets
3. Calculate correction needed
4. Apply safety guardrails
5. Determine delivery method (temp basal vs bolus)

---

## Correction Calculation

### Minimum Predicted Glucose

Loop first identifies the **minimum predicted glucose** (nadir):

```swift
let eventualGlucose = prediction.last
let minPredictedGlucose = prediction.min(by: { $0.quantity < $1.quantity })
```

### Correction Formula

```swift
let correctionGlucose = max(eventualGlucose, minPredictedGlucose)
let glucoseError = correctionGlucose - targetGlucose
let correctionUnits = glucoseError / insulinSensitivity
```

**Key insight**: Loop uses the higher of eventual glucose and minimum predicted glucose for correction. This prevents overshooting if glucose is temporarily rising but expected to fall.

### Target Selection

```swift
let targetGlucose = (correctionRange.lowerBound + correctionRange.upperBound) / 2
```

Loop aims for the **midpoint** of the correction range, not the lower bound.

---

## Temp Basal Recommendations

### Source: `DoseMath.swift`
**File**: `loop:LoopKit/LoopKit/LoopAlgorithm/DoseMath.swift`

### Decision Logic

```swift
public func recommendTempBasal(
    for glucose: [PredictedGlucoseValue],
    at date: Date,
    suspendThreshold: GlucoseThreshold,
    sensitivity: InsulinSensitivitySchedule,
    activeInsulinModel: InsulinModel,
    basal: BasalRateSchedule,
    maxBasalRate: Double,
    lastTempBasal: DoseEntry?
) -> TempBasalRecommendation?
```

### Case 1: Below Suspend Threshold

```swift
if minPredictedGlucose.quantity < suspendThreshold.quantity {
    return TempBasalRecommendation(unitsPerHour: 0, duration: .minutes(30))
}
```

If any predicted glucose falls below suspend threshold → recommend **zero temp basal**.

### Case 2: Below Target Range

```swift
if minPredictedGlucose.quantity < correctionRange.lowerBound {
    let tempRate = scheduledBasalRate * (minPredictedGlucose / correctionRange.lowerBound)
    return TempBasalRecommendation(unitsPerHour: max(0, tempRate), duration: .minutes(30))
}
```

If predicted minimum is below target but above suspend → **reduce basal proportionally**.

### Case 3: Above Target Range

```swift
let correctionUnits = (eventualGlucose - targetMidpoint) / insulinSensitivity
let correctionRate = correctionUnits / correctionDuration
let targetRate = scheduledBasalRate + correctionRate
```

If prediction is above target → **increase basal** up to max basal rate.

### Case 4: In Target Range

```swift
// Check if current temp can be cancelled
if let lastTempBasal = lastTempBasal,
   lastTempBasal.unitsPerHour != scheduledBasalRate,
   lastTempBasal.endDate > date
{
    return nil  // Let current temp continue or cancel naturally
}
```

If prediction is in range → **maintain or cancel current temp**.

---

## Automatic Bolus Recommendations

### Source: `DoseMath.swift`

Loop supports automatic boluses (microboluses) in addition to temp basals:

```swift
public func recommendAutomaticDose(
    for glucose: [PredictedGlucoseValue],
    at date: Date,
    suspendThreshold: GlucoseThreshold,
    sensitivity: InsulinSensitivitySchedule,
    activeInsulinModel: InsulinModel,
    basal: BasalRateSchedule,
    maxAutomaticBolus: Double,
    partialApplicationFactor: Double
) -> AutomaticDoseRecommendation?
```

### Partial Application Factor

```swift
let bolusUnits = correctionUnits * partialApplicationFactor
```

Loop applies only a **fraction** of the calculated correction per cycle:
- Typical value: 0.4 (40% of correction delivered each 5 minutes)
- This creates a "pulse" effect smoothing delivery over time

### Maximum Automatic Bolus

```swift
let constrainedBolus = min(bolusUnits, maxAutomaticBolus)
```

User-configurable limit on per-cycle automatic bolus size.

---

## Manual Bolus Recommendations

### Meal Bolus

```swift
public func recommendBolus(
    forPrediction prediction: [PredictedGlucoseValue],
    consideringPotentialCarbEntry potentialCarbEntry: NewCarbEntry?,
    replacingCarbEntry replacedCarbEntry: StoredCarbEntry?,
    at date: Date,
    ...
) -> ManualBolusRecommendation
```

When carbs are entered, Loop:
1. Predicts glucose with carb effect
2. Calculates full correction to target
3. Subtracts any pending automatic bolus
4. Returns recommended manual bolus

### Correction Bolus

If no carbs are entered, Loop can still recommend a correction bolus:
1. Identifies eventual glucose above range
2. Calculates insulin needed to correct
3. Applies any safety limits

---

## Safety Guardrails

### Maximum Basal Rate

```swift
let maxRate = min(
    userMaxBasalRate,
    4 * scheduledBasalRate  // No more than 4x scheduled
)
```

### Maximum IOB

Loop tracks total IOB and may limit further dosing:
```swift
if currentIOB >= maxIOB {
    // Limit additional dosing
}
```

### Suspend Threshold

Absolute glucose floor below which all delivery stops:
```swift
if minPredictedGlucose < suspendThreshold {
    return zeroTemp
}
```

### Minimum BG Guard

Loop won't bolus if current glucose is below a minimum:
```swift
if currentGlucose < minimumBGGuard {
    return nil  // No bolus recommendation
}
```

---

## Temp Basal vs Bolus Decision

### When Loop Uses Temp Basals

- Gradual corrections over time
- Below-target predictions (reducing delivery)
- When automatic dosing is disabled

### When Loop Uses Automatic Boluses

- Faster correction needed
- When feature is enabled in settings
- Above-target predictions with high confidence

### Hybrid Approach

Loop may combine both:
```swift
AutomaticDoseRecommendation(
    basalAdjustment: tempBasalAdjustment,  // Reduce or increase basal
    bolusUnits: automaticBolusUnits         // Plus a microbolus
)
```

---

## Dosing Interval

Loop runs its algorithm every 5 minutes (tied to CGM data frequency):

```swift
let loopInterval: TimeInterval = .minutes(5)
```

Each cycle:
1. Receives new glucose reading
2. Re-computes prediction
3. Issues new temp basal or bolus if needed

---

## Key Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `tempBasalDuration` | 30 min | Standard temp basal duration |
| `loopInterval` | 5 min | Algorithm execution frequency |
| `retrospectiveCorrectionIntegrationInterval` | 30 min | IRC grouping window |
| `maximumBasalRateMultiplier` | 4.0 | Max basal as multiple of scheduled |

---

## Nightscout Alignment

### Recommendation Upload

Loop uploads `automaticDoseRecommendation` to device status:
```json
{
  "loop": {
    "automaticDoseRecommendation": {
      "timestamp": "2026-01-16T12:00:00Z",
      "tempBasalAdjustment": {
        "rate": 1.5,
        "duration": 1800
      },
      "bolusVolume": 0.15
    }
  }
}
```

### Enacted Upload

When dose is delivered:
```json
{
  "loop": {
    "enacted": {
      "rate": 1.5,
      "duration": 1800,
      "timestamp": "2026-01-16T12:00:00Z",
      "received": true,
      "bolusVolume": 0.15
    }
  }
}
```

### Missing Metadata

Not currently uploaded:
- Correction calculation details
- Which safety limit was hit (if any)
- Target glucose used
- Insulin sensitivity used
- Partial application factor

---

## Algorithm Differences from oref0

| Aspect | Loop | oref0/AAPS/Trio |
|--------|------|-----------------|
| SMB | Automatic bolus (similar concept) | Super Micro Bolus |
| UAM | No explicit support | Unannounced Meal detection |
| Partial Application | Configurable factor | Built-in SMB/bolus limits |
| Zero Temp | At suspend threshold | At `min_bg` |
| Target | Midpoint of range | Low end or profile target |
