# Loop Safety Guardrails

This document details Loop's safety mechanisms as implemented across the codebase.

## Overview

Loop implements multiple layers of safety:
1. **Algorithm Limits** - Constraints on dosing calculations
2. **Suspend Threshold** - Absolute floor for delivery
3. **Maximum Limits** - Caps on rates and boluses
4. **Data Freshness** - Requirements for recent data
5. **Error Handling** - Graceful degradation on failures

---

## Suspend Threshold

### Purpose

The suspend threshold is an **absolute safety floor**. If any predicted glucose value falls below this threshold, Loop immediately recommends zero delivery.

### Implementation

```swift
if minPredictedGlucose.quantity < suspendThreshold.quantity {
    return TempBasalRecommendation(unitsPerHour: 0, duration: .minutes(30))
}
```

### Configuration

- User-configurable in settings
- Typically set 10-20 mg/dL below low target
- Common values: 70-80 mg/dL

### Behavior

When triggered:
1. Zero temp basal issued immediately
2. Remains in effect for 30 minutes
3. Re-evaluated each loop cycle

---

## Maximum Basal Rate

### Purpose

Prevents excessive insulin delivery via temp basals.

### Implementation

```swift
let maxRate = min(
    userMaxBasalRate,                 // User-configured max
    4.0 * scheduledBasalRate          // 4x current scheduled rate
)
```

### Dual Constraint

Loop applies **two limits**:
1. User's configured maximum basal rate
2. 4x the currently scheduled basal rate

The lower of the two is used.

### Example

- Scheduled basal: 1.0 U/hr
- User max basal: 3.0 U/hr
- Effective max: min(3.0, 4.0) = 3.0 U/hr

---

## Maximum IOB

### Purpose

Limits total insulin on board to prevent dangerous stacking.

### Implementation (Inferred)

Loop tracks IOB and may limit dosing when at maximum. The exact implementation varies:

**Source**: `loop:Loop/Loop/Managers/LoopDataManager.swift` (dosing decision logic)

**Note**: The specific max IOB enforcement behavior should be verified against current Loop source. This section documents the expected behavior pattern.

### Configuration

- User-configurable in settings
- Should reflect individual insulin tolerance
- Typical range varies by individual needs

### Behavior

When at or near max IOB:
- Automatic dosing may be reduced or suspended
- Manual bolus recommendations may be limited
- The exact constraints depend on Loop version and configuration

---

## Maximum Automatic Bolus

### Purpose

Limits the size of individual automatic (micro) boluses.

### Implementation

```swift
let constrainedBolus = min(bolusUnits, maxAutomaticBolus)
```

### Configuration

- User-configurable in settings
- Typical values: 0.5-3.0 units per cycle

### Partial Application Factor

Automatic boluses also use a partial application factor:
```swift
let bolusUnits = correctionUnits * partialApplicationFactor
```

This ensures only a fraction of the full correction is delivered per 5-minute cycle.

---

## Data Freshness Requirements

### Glucose Data

Loop requires recent glucose data to operate:

```swift
let glucoseRecencyInterval = TimeInterval(minutes: 15)

guard let latestGlucose = glucoseHistory.last,
      latestGlucose.startDate > Date() - glucoseRecencyInterval else {
    // Cannot loop - no recent glucose
    return nil
}
```

If glucose data is older than 15 minutes:
- No new dosing recommendations
- Current temp may continue or cancel
- User is alerted

### Pump Communication

Loop requires successful pump communication:
```swift
guard let pumpManagerStatus = pumpManagerStatus,
      pumpManagerStatus.lastReservoirValue != nil else {
    // Cannot confirm pump state
}
```

---

## Prediction Guardrails

### Minimum Prediction Length

Loop requires sufficient prediction horizon:
```swift
let minimumPredictionHorizon = TimeInterval(hours: 1)
```

### Handling Edge Cases

If prediction is too short or contains invalid values:
- Falls back to conservative dosing
- May suspend or reduce delivery
- Logs warning for debugging

---

## Error Handling

### Algorithm Errors

```swift
public struct StoredDosingDecision {
    public var errors: [Issue] = []
}
```

Loop tracks errors during each dosing decision:
- Insufficient glucose data
- Pump communication failures
- Algorithm exceptions

### Error Impact

When errors occur:
- Dosing may be suspended
- Error reason uploaded to Nightscout
- User notification triggered

### Error Recovery

Loop attempts to recover each cycle:
- Fresh data may resolve issues
- Pump reconnection attempted
- Algorithm re-run with new inputs

---

## Insulin Model Limits

### Action Duration (DIA)

```swift
public var actionDuration: TimeInterval {
    switch self {
    case .rapidActingAdult: return .minutes(360)  // 6 hours
    case .afrezza: return .minutes(300)           // 5 hours
    // ...
    }
}
```

DIA affects how long insulin effect is tracked.

### Peak Activity Time

```swift
public var peakActivity: TimeInterval {
    switch self {
    case .rapidActingAdult: return .minutes(75)
    case .fiasp: return .minutes(55)
    // ...
    }
}
```

---

## Carb Safety

### Maximum Absorption Time

```swift
let maximumAbsorptionTimeInterval = TimeInterval(hours: 10)
```

Carbs are never assumed to absorb longer than 10 hours.

### Absorption Time Override

Users can specify absorption time per carb entry:
- Fast: ~2 hours
- Medium: ~3 hours
- Slow: ~4-5 hours
- Custom: User-specified

---

## Override Safety

### Scale Factor Limits

Override insulin needs scale factor is typically limited:
- Minimum: 0.1 (10% of normal)
- Maximum: 2.0 (200% of normal)

### Target Range Limits

Override targets must be within safe bounds:
- Minimum target: Typically ≥ 80 mg/dL
- Maximum target: Typically ≤ 180 mg/dL

---

## Nightscout Alignment

### Error Reporting

Loop uploads failure reasons to Nightscout:
```json
{
  "loop": {
    "failureReason": "Pump communication failure: timeout"
  }
}
```

### Safety State Visibility

Current safety state uploaded:
```json
{
  "pump": {
    "suspended": false,
    "reservoir": 150.5
  },
  "loop": {
    "enacted": {
      "rate": 0,
      "duration": 1800,
      "received": true
    }
  }
}
```

### Missing Safety Metadata

Not currently synced:
- Which safety limit was hit
- Configured max basal/IOB/bolus values
- Suspend threshold setting
- Data freshness failures

---

## Safety vs oref0

| Safety Feature | Loop | oref0/AAPS/Trio |
|----------------|------|-----------------|
| Suspend threshold | User-configurable | `min_bg` |
| Max basal | Min of user max, 4x scheduled | Similar, varies |
| Max IOB | User-configurable | `max_iob` |
| Max SMB/bolus | User-configurable | `maxSMBBasalMinutes`, etc |
| Data freshness | 15 min glucose | 10-13 min typically |
| Error handling | Per-cycle retry | Similar |
