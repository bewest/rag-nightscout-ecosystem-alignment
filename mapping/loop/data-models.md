# Loop Data Models

This document details the core data structures used in Loop.

## Dose Data

### DoseEntry

**File**: `loop:LoopKit/LoopKit/InsulinKit/DoseEntry.swift`

```swift
public struct DoseEntry: TimelineValue, Equatable {
    public let type: DoseType
    public let startDate: Date
    public var endDate: Date
    public var programmedUnits: Double
    public var deliveredUnits: Double?
    public var insulinType: InsulinType?
    public var automatic: Bool?
    public var manuallyEntered: Bool
    public var isMutable: Bool
    public var wasProgrammedByPumpUI: Bool
    public var scheduledBasalRate: HKQuantity?
    public internal(set) var syncIdentifier: String?
}
```

### DoseType

```swift
public enum DoseType: String, Codable {
    case basal      // Scheduled basal (not used for IOB)
    case bolus      // Manual or automatic bolus
    case resume     // Pump resumed from suspend
    case suspend    // Pump suspended
    case tempBasal  // Temporary basal rate
}
```

### Computed Properties

| Property | Computation | Purpose |
|----------|-------------|---------|
| `hours` | `(endDate - startDate) / 3600` | Duration in hours |
| `unitsPerHour` | `programmedUnits / hours` | Delivery rate |
| `unitsInDeliverableIncrements` | Rounded for pump precision | Actual deliverable |
| `netBasalUnits` | Units relative to scheduled | For IOB calculation |

---

## Glucose Data

### GlucoseValue Protocol

```swift
public protocol GlucoseValue: SampleValue {
    var quantity: HKQuantity { get }
}
```

### GlucoseSampleValue Protocol

```swift
public protocol GlucoseSampleValue: GlucoseValue {
    var provenanceIdentifier: String { get }
    var isDisplayOnly: Bool { get }
    var wasUserEntered: Bool { get }
}
```

### GlucoseEffect

```swift
public struct GlucoseEffect: SampleValue, Equatable {
    public let startDate: Date
    public let quantity: HKQuantity
}
```

Represents expected glucose change at a point in time.

### GlucoseEffectVelocity

```swift
public struct GlucoseEffectVelocity: TimelineValue, Equatable {
    public let startDate: Date
    public let endDate: Date
    public let quantity: HKQuantity  // mg/dL per second
}
```

Represents rate of glucose change (used for counteraction effects).

### PredictedGlucoseValue

```swift
public struct PredictedGlucoseValue: GlucoseValue {
    public let startDate: Date
    public let quantity: HKQuantity
}
```

A future glucose prediction point.

---

## Carb Data

### CarbEntry Protocol

```swift
public protocol CarbEntry: SampleValue {
    var quantity: HKQuantity { get }
    var startDate: Date { get }
    var foodType: String? { get }
    var absorptionTime: TimeInterval? { get }
}
```

### CarbValue

```swift
public struct CarbValue: SampleValue, Equatable {
    public let startDate: Date
    public let endDate: Date?
    public let value: Double  // grams
}
```

### CarbStatus

```swift
public struct CarbStatus<T: CarbEntry> {
    public let entry: T
    public let absorption: AbsorbedCarbValue?
}
```

Tracks a carb entry with its observed absorption.

### AbsorbedCarbValue

```swift
public struct AbsorbedCarbValue {
    public let startDate: Date
    public let observedGrams: Double
    public let observedDate: Date
    public let estimatedTimeRemaining: TimeInterval
}
```

---

## Override Data

### TemporaryScheduleOverride

```swift
public struct TemporaryScheduleOverride: Hashable {
    public var context: Context
    public var settings: TemporaryScheduleOverrideSettings
    public var startDate: Date
    public let enactTrigger: EnactTrigger
    public let syncIdentifier: UUID
    public var actualEnd: End
    public var duration: Duration
}
```

### Context

```swift
public enum Context: Hashable {
    case preMeal
    case legacyWorkout
    case preset(TemporaryScheduleOverridePreset)
    case custom
}
```

### TemporaryScheduleOverrideSettings

```swift
public struct TemporaryScheduleOverrideSettings: Hashable {
    public var targetRange: ClosedRange<HKQuantity>?
    public var insulinNeedsScaleFactor: Double?
}
```

### Duration

```swift
public enum Duration: Hashable, Comparable {
    case finite(TimeInterval)
    case indefinite
}
```

### End

```swift
public enum End: Equatable, Hashable, Codable {
    case natural     // Ended at scheduled time
    case early(Date) // Cancelled before scheduled end
    case deleted     // Superseded before starting
}
```

### EnactTrigger

```swift
public enum EnactTrigger: Hashable {
    case local
    case remote(String)  // Remote address
}
```

---

## Insulin Models

### InsulinModel Protocol

```swift
public protocol InsulinModel {
    var effectDuration: TimeInterval { get }
    func percentEffectRemaining(at time: TimeInterval) -> Double
}
```

### ExponentialInsulinModelPreset

```swift
public enum ExponentialInsulinModelPreset: String, Codable {
    case rapidActingAdult
    case rapidActingChild
    case fiasp
    case lyumjev
    case afrezza
}
```

### InsulinType

```swift
public enum InsulinType: String, Codable, CaseIterable {
    case novolog
    case humalog
    case fiasp
    case lyumjev
    case apidra
    case afrezza
}
```

---

## Algorithm Output

### LoopPrediction

```swift
public struct LoopPrediction: GlucosePrediction {
    public var glucose: [PredictedGlucoseValue]
    public var effects: LoopAlgorithmEffects
}
```

### LoopAlgorithmEffects

```swift
public struct LoopAlgorithmEffects {
    public var insulin: [GlucoseEffect]
    public var carbs: [GlucoseEffect]
    public var retrospectiveCorrection: [GlucoseEffect]
    public var momentum: [GlucoseEffect]
    public var insulinCounteraction: [GlucoseEffectVelocity]
}
```

### TempBasalRecommendation

```swift
public struct TempBasalRecommendation {
    public let unitsPerHour: Double
    public let duration: TimeInterval
}
```

### AutomaticDoseRecommendation

```swift
public struct AutomaticDoseRecommendation {
    public let basalAdjustment: TempBasalRecommendation?
    public let bolusUnits: Double?
}
```

### ManualBolusRecommendation

```swift
public struct ManualBolusRecommendation {
    public let amount: Double
    public let pendingInsulin: Double
    public let notice: BolusRecommendationNotice?
}
```

---

## Schedule Data

### BasalRateSchedule

```swift
public typealias BasalRateSchedule = DailyValueSchedule<Double>
```

Array of `(startTime, rateValue)` pairs defining 24-hour basal schedule.

### InsulinSensitivitySchedule

```swift
public typealias InsulinSensitivitySchedule = DailyQuantitySchedule<HKUnit>
```

ISF schedule in mg/dL or mmol/L per unit.

### CarbRatioSchedule

```swift
public typealias CarbRatioSchedule = DailyQuantitySchedule<HKUnit>
```

Carb ratio schedule in grams per unit.

### GlucoseRangeSchedule

```swift
public typealias GlucoseRangeSchedule = DailyQuantitySchedule<DoubleRange>
```

Target glucose range schedule.

---

## Dosing Decision

### StoredDosingDecision

```swift
public struct StoredDosingDecision {
    public let date: Date
    public var insulinOnBoard: InsulinValue?
    public var carbsOnBoard: CarbValue?
    public var predictedGlucose: [PredictedGlucoseValue]?
    public var glucoseTargetRangeSchedule: GlucoseRangeSchedule?
    public var scheduleOverride: TemporaryScheduleOverride?
    public var automaticDoseRecommendation: AutomaticDoseRecommendation?
    public var manualBolusRecommendation: ManualBolusRecommendation?
    public var pumpManagerStatus: PumpManagerStatus?
    public var errors: [Issue]
}
```

### InsulinValue

```swift
public struct InsulinValue: SampleValue {
    public let startDate: Date
    public let value: Double  // Units
}
```

---

## Nightscout Mapping

| Loop Type | Nightscout Collection | Event Type |
|-----------|----------------------|------------|
| `DoseEntry` (bolus) | `treatments` | `Bolus` |
| `DoseEntry` (tempBasal) | `treatments` | `Temp Basal` |
| `DoseEntry` (suspend) | `treatments` | `Temp Basal` (rate=0) |
| `CarbEntry` | `treatments` | `Carb Correction` |
| `TemporaryScheduleOverride` | `treatments` | `Temporary Override` |
| `StoredDosingDecision` | `devicestatus` | N/A |
| `PredictedGlucoseValue[]` | `devicestatus.loop.predicted` | N/A |

---

## HealthKit Integration

Loop stores and retrieves data from HealthKit:

| Data Type | HKQuantityTypeIdentifier |
|-----------|--------------------------|
| Glucose | `.bloodGlucose` |
| Carbs | `.dietaryCarbohydrates` |
| Insulin | `.insulinDelivery` |
| Basal Rate | N/A (stored in Loop's database) |

### Units

| Measurement | HKUnit |
|-------------|--------|
| Glucose | `.milligramsPerDeciliter` or `.millimolesPerLiter` |
| Carbs | `.gram()` |
| Insulin | `.internationalUnit()` |
| Time | `.second()` |
