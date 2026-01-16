# Loop Quirks and Edge Cases

This document captures non-obvious behaviors, timing details, and gotchas discovered in Loop's implementation.

## Timing Quirks

### Delta Window for Momentary Doses

**Source**: `InsulinMath.swift#L28-L35`

Loop considers a dose "momentary" (instantaneous) if its duration is ≤ 1.05× delta:

```swift
if endDate.timeIntervalSince(startDate) <= 1.05 * delta {
    return netBasalUnits * model.percentEffectRemaining(at: time)
}
```

With default delta of 5 minutes, this means:
- Doses ≤ 5.25 minutes are treated as instant boluses
- Doses > 5.25 minutes use continuous delivery calculation

**Implication**: A 5-minute temp basal is treated as a bolus, but a 6-minute temp basal is treated as continuous.

---

### Temp Basal 30-Minute Duration

Loop issues 30-minute temp basals even though it evaluates every 5 minutes:

```swift
TempBasalRecommendation(unitsPerHour: rate, duration: .minutes(30))
```

**Why**: If Loop stops running (app crash, phone off), the pump continues the temp for up to 30 minutes, providing some protection.

---

### Retrospective Correction Grouping

**Source**: `LoopMath.swift`

Discrepancies are grouped in 30-minute windows:

```swift
let retrospectiveCorrectionGroupingInterval = TimeInterval(minutes: 30)
```

Discrepancies are summed with a 1% tolerance:
```swift
retrospectiveGlucoseDiscrepancies.combinedSums(of: LoopMath.retrospectiveCorrectionGroupingInterval * 1.01)
```

The 1% extra prevents floating-point edge cases at interval boundaries.

---

## Dose Reconciliation Quirks

### Suspend Followed by Temp Without Resume

If pump history shows:
1. Suspend at 10:00
2. Temp basal at 10:30 (no explicit resume)

Loop infers a resume at 10:30:
```swift
// If a temp basal follows suspend without resume, assume pump resumed at temp start
```

**Implication**: Missing resume events don't cause data corruption.

---

### Overlapping Temp Basals

When two temp basals overlap, Loop truncates the first:

```
Input:
  Temp A: 10:00-10:45 at 1.5 U/hr
  Temp B: 10:30-11:30 at 2.0 U/hr

Output:
  Temp A: 10:00-10:30 at 1.5 U/hr  (truncated)
  Temp B: 10:30-11:30 at 2.0 U/hr
```

The pump may report overlapping records, but Loop handles this cleanly.

---

### Basal Schedule Boundary Splitting

If a temp basal crosses a schedule change:

```
Scheduled: 1.0 U/hr until midnight, then 0.8 U/hr
Temp: 2.0 U/hr from 23:30 to 00:30

Result (annotated):
  Temp 2.0 U/hr 23:30-00:00, scheduledBasalRate=1.0
  Temp 2.0 U/hr 00:00-00:30, scheduledBasalRate=0.8
```

The temp is split so each segment has correct `netBasalUnits`.

---

## Insulin Model Quirks

### 10-Minute Delay

All insulin models include a 10-minute delay:

```swift
public var delay: TimeInterval {
    return .minutes(10)  // All presets return 10 min
}
```

This represents time from injection to first effect.

---

### Afrezza's Different Duration

Afrezza (inhaled insulin) has shorter action:

```swift
case .afrezza:
    return .minutes(300)  // 5 hours vs 6 hours for others
```

---

### Walsh Model Deprecated

Loop previously supported Walsh insulin curves but now only uses exponential models. Old profiles may need migration.

---

## Carb Quirks

### 10-Minute Carb Delay

Carbs don't start absorbing until 10 minutes after entry:

```swift
let defaultEffectDelay = TimeInterval(minutes: 10)
```

This models digestion delay before glucose rises.

---

### Maximum Absorption Overrun

Carb effects can extend 1.5× beyond specified absorption time:

```swift
let defaultAbsorptionTimeOverrun = 1.5
```

If 3-hour absorption is specified, effects may extend to 4.5 hours if dynamic absorption is running slow.

---

### Overlapping Carb Attribution

When multiple carb entries have overlapping absorption windows, they're grouped:

```swift
func groupedByOverlappingAbsorptionTimes(...)
```

Glucose effects are attributed proportionally to each entry in the group.

---

## Override Quirks

### Indefinite Duration Encoding

Internally: `.indefinite` with `TimeInterval.infinity`
In Nightscout: encoded as `0`

```swift
case .indefinite:
    nsDuration = 0
```

---

### Precondition Crash on Overlap

If the override system detects overlapping overrides:

```swift
preconditionFailure("No overrides should overlap.")
```

This crashes the app. It's a defensive measure that should never trigger in production.

---

### Override Ends One Second Early

Overrides ending "early" use `.nearestPrevious`:

```swift
let overrideEnd = min(override.startDate.nearestPrevious, enableDate)
```

This prevents two overrides from sharing the exact same boundary timestamp.

---

## Prediction Quirks

### Momentum Blend Zone

Momentum is blended with other effects over 15 minutes:

```swift
let blendCount = momentum.count  // Number of momentum samples
let blendSlope = 1.0 / Double(blendCount)
```

At each time point in the blend zone:
- Earlier = more momentum weight
- Later = more other-effects weight

---

### Effect Delta Accumulation

Effects are stored as cumulative values but applied as deltas:

```swift
let value = effect.quantity.doubleValue(for: unit)
effectValuesAtDate[effect.startDate] = (effectValuesAtDate[effect.startDate] ?? 0) + value - previousEffectValue
previousEffectValue = value
```

This can be confusing when debugging—the raw effect values don't add directly.

---

### Empty Prediction Fallback

If prediction generation fails (no glucose data, etc):

```swift
guard !prediction.glucose.isEmpty else {
    return .failure(.missingGlucoseData)
}
```

Loop returns an error rather than an empty prediction.

---

## Nightscout Sync Quirks

### Sync Identifier Reuse

Loop uses `syncIdentifier` for idempotent uploads. If the same syncIdentifier is uploaded again:
- Nightscout should update (not duplicate) the record
- Currently uses POST (not PUT), which may cause duplicates in some Nightscout versions

---

### No CRUD for Overrides

Override treatments don't have full CRUD in Nightscout:
- Created on start
- No explicit update on early end
- Supersession not tracked

---

### Resume Events Not Uploaded

`.resume` dose type is never uploaded:

```swift
case .resume:
    return nil
```

The suspend duration implicitly ends at resume time.

---

### IOB Not Recalculated for Nightscout

Loop uploads its own IOB, not Nightscout's:

```swift
iob: nil,  // Pump's reported IOB isn't relevant
```

This ensures consistency but may differ from Nightscout's calculations.

---

## Data Model Quirks

### Delivered vs Programmed Units

```swift
return deliveredUnits ?? programmedUnits
```

Loop prefers `deliveredUnits` (actual delivery) but falls back to `programmedUnits` (commanded) if delivery isn't confirmed.

---

### Units Per Hour vs Net Units

- `unitsPerHour` - The rate being delivered
- `netBasalUnits` - Total units relative to scheduled basal

These are different! A 2.0 U/hr temp for 30 min with scheduled 1.0 U/hr:
- `unitsPerHour` = 2.0
- `netBasalUnits` = +0.5 (net extra delivered)

---

### HKQuantity Unit Handling

Loop uses HealthKit quantities with units:

```swift
HKQuantity(unit: .milligramsPerDeciliter, doubleValue: 120)
```

All internal calculations are in mg/dL. Conversion to mmol/L happens only for display.

---

## Algorithm Variant Quirks

### Integral vs Standard Retrospective Correction

Two implementations exist:

1. **StandardRetrospectiveCorrection**: Simple proportional
2. **IntegralRetrospectiveCorrection**: PID-like with integral/differential

IRC parameters:
```swift
static let currentDiscrepancyGain: Double = 1.0
static let persistentDiscrepancyGain: Double = 2.0
static let correctionTimeConstant: TimeInterval = TimeInterval(minutes: 60.0)
static let differentialGain: Double = 2.0
```

---

### Algorithm Effects Options

Effects can be selectively enabled/disabled:

```swift
public static let all: AlgorithmEffectsOptions = [.carbs, .insulin, .momentum, .retrospection]
```

This is mainly for testing—production uses all effects.

---

## Known Issues

### GAP-001: Override Supersession Not Synced

When Override B supersedes Override A, the relationship isn't captured in Nightscout.

### GAP-002: Effect Timelines Not Uploaded

Individual `insulin`, `carbs`, `momentum`, `rc` effects aren't synced.

### GAP-003: Prediction Format Incompatibility

Loop's single `predicted[]` differs from oref0's `predBGs.IOB[]`, `predBGs.COB[]`, etc.
