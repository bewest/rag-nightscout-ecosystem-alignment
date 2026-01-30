# Carb Absorption Model Comparison

> **Status**: Complete  
> **Last Updated**: 2026-01-29  
> **Task**: Compare carb absorption algorithms across Loop, oref0/AAPS, and Nightscout

## Executive Summary

Loop and oref0/AAPS use fundamentally different approaches to carb absorption modeling:

| Aspect | Loop | oref0/AAPS |
|--------|------|------------|
| **Philosophy** | Model-based prediction | Deviation-based detection |
| **Absorption curves** | Parabolic/Piecewise linear | min_5m_carbimpact floor |
| **Adaptation** | Observed vs modeled progress | UAM (Unannounced Meal) |
| **Time window** | Up to 10h max | 6h after meal |
| **Default duration** | 3h per entry | Linear decay to 0 |

## Loop Carb Absorption Model

### Source Files
- `externals/LoopWorkspace/LoopKit/LoopKit/CarbKit/CarbMath.swift:1-200`
- `externals/LoopWorkspace/LoopKit/LoopKit/CarbKit/AbsorbedCarbValue.swift:1-80`
- `externals/LoopWorkspace/LoopKit/LoopKit/CarbKit/CarbStore.swift`

### Constants

```swift
// CarbMath.swift:12-17
public static let maximumAbsorptionTimeInterval: TimeInterval = .hours(10)
public static let defaultAbsorptionTime: TimeInterval = .hours(3)
public static let defaultAbsorptionTimeOverrun: Double = 1.5
public static let defaultEffectDelay: TimeInterval = .minutes(10)
```

### Absorption Models

Loop supports multiple absorption curve shapes via the `CarbAbsorptionComputable` protocol:

#### 1. Linear Absorption (CarbMath.swift:151-183)
- Simple constant rate: `percentAbsorption = percentTime`
- Rate = 1.0 throughout absorption

#### 2. Parabolic Absorption (CarbMath.swift:109-148)
- Based on Scheiner GI curve (Think Like a Pancreas, Fig 7-8)
- Ramps up then down in a symmetric curve:
  - First half: `absorption = 2 * t²`
  - Second half: `absorption = -1 + 2t(2-t)`
- Peak rate at 50% of absorption time

#### 3. Piecewise Linear (CarbMath.swift:185-200)
- Non-symmetric absorption curve
- Rise phase: 0% to 15% of time (linear increase)
- Plateau phase: 15% to 50% of time (constant rate)
- Fall phase: 50% to 100% of time (linear decrease)
- More realistic for mixed meals

### Dynamic Adaptation

Loop tracks `observedProgress` vs modeled progress (AbsorbedCarbValue.swift:41-53):

```swift
public var observedProgress: HKQuantity {
    let totalGrams = total.doubleValue(for: gram)
    return HKQuantity(
        unit: percent,
        doubleValue: observed.doubleValue(for: gram) / totalGrams
    )
}
```

**Adaptive Rate** (CarbModelSettings):
- `adaptiveAbsorptionRateEnabled`: Adjust rate based on observed absorption
- `adaptiveRateStandbyIntervalFraction`: 0.2 (20% standby before adaptation kicks in)
- `initialAbsorptionTimeOverrun`: 1.5x multiplier for slow absorption

## oref0/AAPS Carb Absorption Model

### Source Files
- `externals/oref0/lib/determine-basal/cob.js:1-200`
- `externals/oref0/lib/determine-basal/determine-basal.js:500-660`
- `externals/oref0/lib/profile/index.js:35`

### Core Algorithm: Deviation-Based Detection

oref0 calculates carb absorption from **glucose deviations** rather than a predefined curve:

```javascript
// cob.js:186-194
// if bgTime is more recent than mealTime
if(bgTime > mealTime) {
    // figure out how many carbs that represents
    var ci = Math.max(deviation, currentDeviation/2, profile.min_5m_carbimpact);
    var absorbed = ci * profile.carb_ratio / sens;
    carbsAbsorbed += absorbed;
}
```

### min_5m_carbimpact Parameter

The `min_5m_carbimpact` ensures minimum absorption rate even when BG is flat:

```javascript
// profile/index.js:35
min_5m_carbimpact: 8 // mg/dL per 5m (8 mg/dL/5m = 24g/hr at CSF of 4 mg/dL/g)
```

| Algorithm | Default | Range | Notes |
|-----------|---------|-------|-------|
| AMA | 3 mg/dL/5m | 1-12 | More conservative |
| SMB | 8 mg/dL/5m | 1-12 | More aggressive |

### Carb Impact Duration (determine-basal.js:510-528)

```javascript
// Linear decay assumption
var totalCI = Math.max(0, ci / 5 * 60 * remainingCATime / 2);
var totalCA = totalCI / csf;
var remainingCarbs = Math.max(0, meal_data.mealCOB - totalCA);

// Bilinear /\ shaped absorption curve for remaining carbs
var remainingCIpeak = remainingCarbs * csf * 5 / 60 / (remainingCATime/2);
```

### UAM (Unannounced Meal) Detection

UAM handles carbs not explicitly entered (determine-basal.js:597-610):

```javascript
// for UAMpredBGs, predicted carb impact drops at slopeFromDeviations
var predUCIslope = Math.max(0, uci + (UAMpredBGs.length * slopeFromDeviations));
// fallback: linear decay over 3h
var predUCImax = Math.max(0, uci * (1 - UAMpredBGs.length / Math.max(3*60/5, 1)));
var predUCI = Math.min(predUCIslope, predUCImax);
```

**UAM enables:**
- Responding to rising BG without carb entry
- Backup for underestimated carb entries
- Handling of slow-absorbing meals

## AAPS Implementation

### Source Files
- `externals/AndroidAPS/core/data/src/main/kotlin/app/aaps/core/data/iob/CobInfo.kt`
- `externals/AndroidAPS/core/interfaces/src/main/kotlin/app/aaps/core/interfaces/aps/AutosensData.kt`
- `externals/AndroidAPS/core/interfaces/src/main/kotlin/app/aaps/core/interfaces/aps/MealData.kt`
- `externals/AndroidAPS/core/keys/src/main/kotlin/app/aaps/core/keys/DoubleKey.kt:35-36`

### CobInfo Structure

```kotlin
// CobInfo.kt
data class CobInfo(
    val timestamp: Long,
    val displayCob: Double?,
    val futureCarbs: Double  // carbs not yet processed
)
```

### AutosensData.CarbsInPast

```kotlin
// AutosensData.kt:5-14
data class CarbsInPast(
    var time: Long,
    var carbs: Double,
    var min5minCarbImpact: Double = 0.0,
    var remaining: Double
)
```

### Per-Algorithm min_5m_carbimpact

```kotlin
// DoubleKey.kt:35-36
ApsAmaMin5MinCarbsImpact("openapsama_min_5m_carbimpact", 3.0, 1.0, 12.0),
ApsSmbMin5MinCarbsImpact("openaps_smb_min_5m_carbimpact", 8.0, 1.0, 12.0),
```

### MealData Fields

```kotlin
// MealData.kt
data class MealData(
    var carbs: Double = 0.0,
    var mealCOB: Double = 0.0,
    var slopeFromMaxDeviation: Double = 0.0,
    var slopeFromMinDeviation: Double = 999.0,
    var lastBolusTime: Long = 0,
    var lastCarbTime: Long = 0L,
    var usedMinCarbsImpact: Double = 0.0
)
```

## Comparison Matrix

| Feature | Loop | oref0/AAPS |
|---------|------|------------|
| **Absorption curve** | Configurable (linear/parabolic/piecewise) | Deviation-driven with min floor |
| **Maximum duration** | 10 hours | 6 hours after meal |
| **Default duration** | 3 hours | Based on current carb impact |
| **Minimum rate** | None (model-driven) | min_5m_carbimpact (3-8 mg/dL/5m) |
| **Adaptation** | observedProgress tracking | UAM detection |
| **Entry delay** | 10 min effectDelay | Immediate impact |
| **Remaining carbs** | Estimated from model + observation | totalCA calculation |
| **Meal backup** | Absorption time overrun (1.5x) | UAM prediction curve |

## Prediction Curve Generation

### Loop COB Prediction
- Uses modeled absorption curve shape
- Adjusts based on observed absorption progress
- Single integrated prediction

### oref0/AAPS COB Prediction (determine-basal.js:593-615)
- Generates separate **COBpredBGs** array
- Adds predCI (predicted carb impact) each 5m tick
- Adds remainingCI for unabsorbed carbs beyond current rate
- Truncated at 4 hours (48 data points)

### UAM Prediction
- Separate **UAMpredBGs** array
- Uses slopeFromDeviations to project future impact
- Falls back to linear decay over 3h
- Enables dosing for unannounced meals

## Nightscout Display

Nightscout displays COB from uploading systems but does not recalculate:

```
devicestatus.openaps.suggested.COB  // oref0/AAPS
devicestatus.loop.cob               // Loop
```

No Nightscout-native carb absorption calculation exists.

## Gaps Identified

### GAP-CARB-001: Absorption Model Incompatibility
- **Description**: Loop uses model-based curves; oref0 uses deviation detection
- **Impact**: COB values differ between systems for same meal
- **Remediation**: Document expected variance; no alignment needed (design difference)

### GAP-CARB-002: min_5m_carbimpact Not in Loop
- **Description**: Loop has no equivalent to min_5m_carbimpact floor
- **Impact**: Loop may underestimate absorption during flat BG
- **Remediation**: Loop uses absorption time overrun instead

### GAP-CARB-003: UAM Not Available in Loop
- **Description**: Loop lacks Unannounced Meal detection
- **Impact**: Loop requires explicit carb entry for all meals
- **Remediation**: Design difference; Loop users must log carbs accurately

### GAP-CARB-004: Maximum Duration Mismatch
- **Description**: Loop 10h max vs oref0 6h after meal
- **Impact**: Very slow absorbing meals handled differently
- **Remediation**: Document in user guidance

## Requirements

### REQ-CARB-001: COB Display Source Attribution
- **Statement**: Systems displaying COB MUST indicate which algorithm calculated it
- **Rationale**: Loop and oref0 COB values are not directly comparable
- **Verification**: Check for source indicator in UI

### REQ-CARB-002: min_5m_carbimpact Configuration
- **Statement**: oref0-based systems SHOULD expose min_5m_carbimpact setting
- **Rationale**: Critical tuning parameter for carb absorption
- **Verification**: Check settings UI includes parameter

### REQ-CARB-003: Absorption Model Documentation
- **Statement**: AID systems MUST document their absorption model type
- **Rationale**: Users need to understand how COB is calculated
- **Verification**: Documentation review

## References

- Scheiner, Gary. "Think Like a Pancreas" - Chapter 7, Fig 7-8 (parabolic absorption)
- [OpenAPS oref0 COB documentation](https://openaps.readthedocs.io/en/latest/docs/While%20You%20Wait%20For%20Gear/understanding-insulin-on-board-calculations.html)
- [LoopDocs Carb Entry](https://loopkit.github.io/loopdocs/operation/features/carbs/)
