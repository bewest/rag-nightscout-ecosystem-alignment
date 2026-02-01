# Carb Absorption Models: Cross-System Deep Dive

This document provides a comprehensive comparison of carbohydrate absorption models used by Loop, oref0, AAPS, and Trio. Understanding these differences is critical for cross-system data interpretation and explains why the same meal can produce different COB values across platforms.

---

## Executive Summary

| Aspect | Loop | oref0 | AAPS | Trio |
|--------|------|-------|------|------|
| **Absorption Model** | Dynamic (adapts to observed glucose) | Linear decay with min floor | Linear decay (oref0 port) | Dynamic (Loop) + oref0 JS |
| **Curve Shape** | Parabolic, Linear, or PiecewiseLinear | Linear decay | Linear decay | PiecewiseLinear default |
| **UAM Support** | Via Retrospective Correction | Explicit UAM curve | Explicit UAM | Both (RC + UAM) |
| **Extended Carbs (eCarbs)** | No | No | Yes (duration field) | No |
| **Minimum Absorption Rate** | Via clamping logic | `min_5m_carbimpact` (3 mg/dL/5m) | `min_5m_carbimpact` | Clamping logic |
| **Default Absorption Time** | 3 hours | Profile-based | Profile-based | 3 hours |
| **Max Absorption Time** | 10 hours | 6 hours (carb window) | 6 hours | 10 hours |

---

## 1. Mathematical Models

### 1.1 Loop/Trio: Pluggable Absorption Curves

Loop and Trio support three absorption curve models, all implementing the `CarbAbsorptionComputable` protocol:

#### 1.1.1 Parabolic Absorption (Scheiner Model)

Based on the GI curve from *Think Like a Pancreas* by Gary Scheiner. Absorption rate starts slow, peaks at 50% of absorption time, then slows again.

```
For t ∈ [0, 0.5]:  absorbed = 2t²
For t ∈ (0.5, 1]:  absorbed = -1 + 2t(2 - t)
```

Where `t = elapsed_time / absorption_time` (normalized percentage)

**Rate curve:**
```
For t ∈ (0, 0.5]:  rate = 4t
For t ∈ (0.5, 1):  rate = 4 - 4t
```

**Source**: `loop:LoopKit/LoopKit/CarbKit/CarbMath.swift#L109-L148`

#### 1.1.2 Linear Absorption

Simple constant-rate absorption over the absorption time.

```
absorbed = t    (for t ∈ [0, 1])
rate = 1        (constant)
```

**Source**: `loop:LoopKit/LoopKit/CarbKit/CarbMath.swift#L152-L183`

#### 1.1.3 PiecewiseLinear Absorption (Default in Loop/Trio)

A trapezoidal model with:
- **Rise phase**: Absorption rate increases linearly from 0 to max (0% → 15% of time)
- **Plateau phase**: Absorption rate constant at max (15% → 50% of time)
- **Fall phase**: Absorption rate decreases linearly to 0 (50% → 100% of time)

```swift
let percentEndOfRise = 0.15
let percentStartOfFall = 0.5
let scale = 2.0 / (1.0 + percentStartOfFall - percentEndOfRise)  // ≈ 1.48
```

**Absorption formula:**
```
For t ∈ [0, 0.15]:       absorbed = 0.5 * scale * t² / 0.15
For t ∈ [0.15, 0.5):     absorbed = scale * (t - 0.075)
For t ∈ [0.5, 1):        absorbed = scale * (0.425 + (t-0.5) * (1 - 0.5*(t-0.5)/0.5))
```

**Source**: `loop:LoopKit/LoopKit/CarbKit/CarbMath.swift#L186-L245`

### 1.2 oref0/AAPS: Linear Decay with Carb Impact

oref0 uses a fundamentally different approach: instead of modeling absorption directly, it infers **Carb Impact (CI)** from glucose deviations.

#### 1.2.1 Carb Impact Calculation

```javascript
// CI = current carb impact on BG in mg/dL/5m
ci = round((minDelta - bgi), 1);

// CSF = Carb Sensitivity Factor (mg/dL per gram)
var csf = sens / profile.carb_ratio;

// Limit CI to maxCarbAbsorptionRate (30 g/h default)
var maxCI = round(maxCarbAbsorptionRate * csf * 5/60, 1);
if (ci > maxCI) {
    ci = maxCI;
}
```

**Source**: `oref0:lib/determine-basal/determine-basal.js#L469-L486`

#### 1.2.2 COB Decay Formula

COB decays linearly over the carb impact duration (cid):

```javascript
// Duration in 5-minute intervals
cid = Math.min(remainingCATime*60/5/2, Math.max(0, meal_data.mealCOB * csf / ci));

// Predicted carb impact decays linearly
var predCI = Math.max(0, ci * (1 - COBpredBGs.length / Math.max(cid*2, 1)));
```

**Source**: `oref0:lib/determine-basal/determine-basal.js#L541-L586`

#### 1.2.3 Minimum Carb Impact Floor

oref0 enforces a minimum absorption rate via `min_5m_carbimpact`:

```javascript
// Default: 3 mg/dL per 5 minutes (8 mg/dL/5m for low-carb)
var ci = Math.max(deviation, currentDeviation/2, profile.min_5m_carbimpact);
var absorbed = ci * profile.carb_ratio / sens;
```

This prevents "zombie carbs" where COB persists indefinitely when no absorption is detected.

**Source**: `oref0:lib/determine-basal/cob.js#L189-L194`

---

## 2. Dynamic vs Static Absorption

### 2.1 Loop/Trio: Observation-Based Dynamic Absorption

Loop's key innovation is **dynamic absorption** that adapts to observed glucose changes:

#### 2.1.1 Absorption State Tracking

```swift
public struct AbsorbedCarbValue {
    let observed: HKQuantity      // Carbs absorbed based on glucose changes
    let clamped: HKQuantity       // Observed, clamped to predicted bounds
    let total: HKQuantity         // Total carbs entered
    let remaining: HKQuantity     // Carbs still expected to absorb
    let observedDate: DateInterval
    let estimatedTimeRemaining: TimeInterval
    let timeToAbsorbObservedCarbs: TimeInterval
}
```

**Source**: `loop:LoopKit/LoopKit/CarbKit/AbsorbedCarbValue.swift#L13-L35`

#### 2.1.2 Observed Timeline

Loop maintains an `observedTimeline` of actual carb absorption:

```swift
func dynamicCarbsOnBoard(at date: Date, ...) -> Double {
    guard let observedTimeline = observedTimeline,
          let observationEnd = observedTimeline.last?.endDate else {
        // Fall back to modeled absorption
        return absorptionModel.unabsorbedCarbs(of: total, atTime: time, absorptionTime: absorptionTime)
    }
    
    if date <= observationEnd {
        // Use observed absorption
        return observedTimeline.filter({ $0.endDate <= date }).reduce(total) { ... }
    } else {
        // Predict remaining based on observed rate
        let effectiveTime = date.timeIntervalSince(observationEnd) + absorption.timeToAbsorbObservedCarbs
        return absorptionModel.unabsorbedCarbs(of: total, atTime: effectiveTime, ...)
    }
}
```

**Source**: `loop:LoopKit/LoopKit/CarbKit/CarbStatus.swift#L45-L79`

#### 2.1.3 Clamping Logic

Loop clamps observed absorption to prevent unrealistic values:

- **Minimum**: Based on `initialAbsorptionTimeOverrun` (default 1.5x) to ensure minimum progress
- **Maximum**: Capped at total carbs entered

**Configuration Source**: `CarbMath.swift#L15` (`defaultAbsorptionTimeOverrun = 1.5`), `CarbMath.swift#L19-31` (`CarbModelSettings` struct)

**Note**: The clamping implementation logic resides in `CarbStatusBuilder` (CarbMath.swift#L548+). Full traceability of clamping algorithm requires further analysis of this builder class.

### 2.2 oref0: Deviation-Based Inference

oref0 doesn't track individual carb entries' absorption. Instead:

1. **Observe deviation**: `deviation = delta - bgi` (actual glucose change minus expected from insulin)
2. **Infer carb impact**: Positive deviations indicate carbs absorbing
3. **Decay COB**: Reduce COB based on cumulative inferred absorption

```javascript
// Detect carb absorption from glucose deviations
function detectCarbAbsorption(inputs) {
    // ...
    var ci = Math.max(deviation, currentDeviation/2, profile.min_5m_carbimpact);
    var absorbed = ci * profile.carb_ratio / sens;
    carbsAbsorbed += absorbed;
    // ...
}
```

**Source**: `oref0:lib/determine-basal/cob.js#L8-L211`

---

## 3. COB Calculation Methods

### 3.1 Loop: Sum of Individual Entry COB

```swift
func carbsOnBoard(...) -> [CarbValue] {
    repeat {
        let value = reduce(0.0) { (value, entry) -> Double in
            return value + entry.carbsOnBoard(at: date, ...)
        }
        values.append(CarbValue(startDate: date, value: value))
        date = date.addingTimeInterval(delta)
    } while date <= endDate
    
    return values
}
```

Each carb entry independently calculates its remaining COB using the absorption model.

**Source**: `loop:LoopKit/LoopKit/CarbKit/CarbMath.swift#L356-L381`

### 3.2 oref0: Global COB with Stacking Detection

```javascript
// Calculate COB for each meal, find maximum
treatments.forEach(function(treatment) {
    if (treatment.carbs >= 1) {
        carbs += parseFloat(treatment.carbs);
        var myCarbsAbsorbed = detectCarbAbsorption(COB_inputs).carbsAbsorbed;
        var myMealCOB = Math.max(0, carbs - myCarbsAbsorbed);
        mealCOB = Math.max(mealCOB, myMealCOB);
    }
});

// Hard cap for safety
mealCOB = Math.min(profile.maxCOB, mealCOB);
```

**Source**: `oref0:lib/meal/total.js#L46-L112`

### 3.3 AAPS: Extended Carbs (eCarbs)

AAPS uniquely supports carbs with a **duration** field, spreading absorption over time:

```kotlin
data class Carbs(
    override var timestamp: Long,
    override var duration: Long,  // in milliseconds
    var amount: Double,
    var notes: String? = null
) : TraceableDBEntry, DBEntryWithTimeAndDuration
```

**Key differences:**
- Duration = 0: Immediate carbs (like other systems)
- Duration > 0: Carbs spread linearly over the duration

**Source**: `aaps:database/impl/src/main/kotlin/app/aaps/database/entities/Carbs.kt#L28-L42`

---

## 4. Unannounced Meal (UAM) Detection

### 4.1 oref0/AAPS/Trio: Explicit UAM Curve

UAM handles unexplained glucose rises (eating without logging carbs).

#### 4.1.1 UAM Prediction Curve

```javascript
// Calculate predicted CI from UAM based on deviationSlope
var predUCIslope = Math.max(0, uci + (UAMpredBGs.length * slopeFromDeviations));

// Linear decay fallback over 3 hours
var predUCImax = Math.max(0, uci * (1 - UAMpredBGs.length / Math.max(3*60/5, 1)));

// Use lesser of slope-based or time-based decay
var predUCI = Math.min(predUCIslope, predUCImax);
UAMpredBG = UAMpredBGs[UAMpredBGs.length-1] + predBGI + Math.min(0, predDev) + predUCI;
```

**Source**: `oref0:lib/determine-basal/determine-basal.js#L597-L610`

#### 4.1.2 UAM Enabling Conditions

```javascript
var enableUAM = profile.enableUAM;
// UAM used when COB is exhausted but deviations persist
```

### 4.2 Loop: Retrospective Correction

Loop doesn't have explicit UAM but handles unexplained changes via **Retrospective Correction (RC)**:

- RC adjusts predictions based on recent glucose discrepancies
- Unexplained rises increase predicted glucose
- Acts as implicit UAM handling

---

## 5. Absorption Time Settings

### 5.1 Default Values

| System | Default Absorption Time | Maximum Absorption Time | Delay | Source |
|--------|------------------------|------------------------|-------|--------|
| **Loop** | 3 hours | 10 hours | 10 minutes | `CarbMath.swift#L12-17` |
| **oref0** | Profile-based | 6 hours (carb window) | None | `total.js#L49` |
| **AAPS** | Profile-based | 6 hours | None | oref0 port |
| **Trio** | 3 hours | 10 hours | 10 minutes | Shared `CarbMath` |

### 5.2 Loop Constants (Verified from Source)

```swift
public struct CarbMath {
    public static let maximumAbsorptionTimeInterval: TimeInterval = .hours(10)
    public static let defaultAbsorptionTime: TimeInterval = .hours(3)
    public static let defaultAbsorptionTimeOverrun: Double = 1.5
    public static let defaultEffectDelay: TimeInterval = .minutes(10)
}
```

**Source**: `loop:LoopKit/LoopKit/CarbKit/CarbMath.swift#L12-L17`

### 5.3 oref0 Carb Window

```javascript
// Consider carbs from up to 6 hours ago
var carbWindow = now - 6 * 60 * 60 * 1000;

// Remaining CA time adjusts based on carb amount
var remainingCATimeMin = 3;  // hours minimum
remainingCATimeMin = Math.max(remainingCATimeMin, meal_data.mealCOB / assumedCarbAbsorptionRate);
```

**Source**: `oref0:lib/meal/total.js#L48-L49`, `oref0:lib/determine-basal/determine-basal.js#L487-L499`

---

## 6. Glucose Effect Calculation

### 6.1 Loop: Carb Sensitivity Factor

```swift
func glucoseEffect(at date: Date, carbRatio: HKQuantity, insulinSensitivity: HKQuantity, ...) -> Double {
    // CSF = ISF / CR (mg/dL per gram of carbs)
    return insulinSensitivity.doubleValue(for: .milligramsPerDeciliter) / 
           carbRatio.doubleValue(for: .gram()) * 
           absorbedCarbs(at: date, ...)
}
```

**Source**: `loop:LoopKit/LoopKit/CarbKit/CarbMath.swift#L279-L288`

### 6.2 oref0: Carb Sensitivity Factor

```javascript
// CSF (mg/dL/g) = ISF (mg/dL/U) / CR (g/U)
var csf = sens / profile.carb_ratio;
```

**Source**: `oref0:lib/determine-basal/determine-basal.js#L477`

---

## 7. Cross-System Data Model Comparison

### 7.1 Carb Entry Fields

| Field | Loop | oref0 | AAPS | Nightscout |
|-------|------|-------|------|------------|
| **Amount (grams)** | `quantity` | `carbs` | `amount` | `carbs` |
| **Timestamp** | `startDate` | `timestamp` | `timestamp` | `created_at` |
| **Absorption Time** | `absorptionTime` | Profile-based | Profile-based | `absorptionTime` |
| **Duration (eCarbs)** | N/A | N/A | `duration` | `duration` |
| **Sync ID** | `syncIdentifier` | N/A | `nightscoutId` | `identifier` (v3) |
| **Notes** | N/A | N/A | `notes` | `notes` |

### 7.2 COB Reporting

| Field | Loop | oref0 | AAPS | Nightscout devicestatus |
|-------|------|-------|------|------------------------|
| **Current COB** | Computed | `mealCOB` | `displayCob` | `loop.cob.cob` / `openaps.suggested.COB` |
| **Carbs Entered** | N/A | `carbs` | N/A | `meal_data.carbs` |
| **Future Carbs** | N/A | N/A | `futureCarbs` | N/A |

---

## 8. Algorithm Interaction: Prediction Curves

### 8.1 COB Prediction (oref0)

```javascript
// COB prediction: carb impact decays linearly
var predCI = Math.max(0, ci * (1 - COBpredBGs.length / Math.max(cid*2, 1)));
var remainingCI = Math.max(0, intervals / (remainingCATime/2*12) * remainingCIpeak);
COBpredBG = COBpredBGs[COBpredBGs.length-1] + predBGI + Math.min(0, predDev) + predCI + remainingCI;
```

### 8.2 Blending COB and UAM (oref0)

```javascript
if (minCOBPredBG < 999 && minUAMPredBG < 999) {
    // Weight based on fraction of carbs remaining
    var fractionCarbsLeft = meal_data.mealCOB / meal_data.carbs;
    minPredBG = fractionCarbsLeft * minCOBPredBG + (1 - fractionCarbsLeft) * minUAMPredBG;
}
```

**Source**: `oref0:lib/determine-basal/determine-basal.js#L709-L720`

---

## 9. Key Configuration Parameters

### 9.1 oref0 Profile Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_5m_carbimpact` | 3 mg/dL/5m | Minimum assumed carb absorption rate |
| `carb_ratio` | User-set | Grams per unit of insulin (CR) |
| `maxCOB` | 120g | Hard cap on calculated COB |
| `remainingCarbsCap` | 90g | Cap on remaining carbs for prediction |
| `remainingCarbsFraction` | 1.0 | Fraction of carbs to consider |
| `maxCarbAbsorptionRate` | 30 g/h | Maximum carb absorption rate |
| `assumedCarbAbsorptionRate` | 20 g/h | Default assumed rate |

### 9.2 Loop Model Settings

```swift
struct CarbModelSettings {
    var absorptionModel: CarbAbsorptionComputable  // Parabolic, Linear, or PiecewiseLinear
    var initialAbsorptionTimeOverrun: Double       // Default 1.5
    var adaptiveAbsorptionRateEnabled: Bool        // Enable dynamic adaptation
    var adaptiveRateStandbyIntervalFraction: Double // Default 0.2
}
```

**Source**: `loop:LoopKit/LoopKit/CarbKit/CarbMath.swift#L19-L31`

---

## 10. Identified Gaps

### GAP-CARB-001: Absorption Model Not Synced

**Description**: No system syncs which absorption curve model is in use to Nightscout.

**Impact**: Cannot compare COB values between systems without knowing their curve models.

### GAP-CARB-002: Dynamic Absorption State Not Exported

**Description**: Loop's `observedTimeline` and `AbsorbedCarbValue` are not synced to Nightscout.

**Impact**: Rich absorption tracking data is lost; only final COB value appears in devicestatus.

### GAP-CARB-003: eCarbs Not Supported by iOS Apps

**Description**: Loop and Trio do not support AAPS's extended carbs (duration field).

**Impact**: Carb entries with duration from AAPS/Nightscout are treated as instant absorption by iOS apps.

### GAP-CARB-004: min_5m_carbimpact Variance

**Description**: Default `min_5m_carbimpact` varies (3 vs 8 mg/dL/5m for low-carb diets).

**Impact**: COB decay rates differ significantly between configurations.

### GAP-CARB-005: COB Maximum Limits Differ

**Description**: Loop has no hard maxCOB; oref0 defaults to 120g cap.

**Impact**: Same carb entries can produce different COB values due to capping.

---

## 11. Requirements Derived

| ID | Requirement | Systems |
|----|-------------|---------|
| REQ-CARB-001 | Systems SHOULD document COB calculation time granularity | All |
| REQ-CARB-002 | Systems SHOULD report absorption model in devicestatus | All |
| REQ-CARB-003 | Extended carbs (duration > 0) MUST be clearly distinguished from instant carbs | AAPS, Nightscout |
| REQ-CARB-004 | CSF calculation MUST use same formula: ISF / CR | All |
| REQ-CARB-005 | Systems that support per-entry absorption time SHOULD preserve it during sync | Loop, Trio |
| REQ-CARB-006 | COB hard limits SHOULD be configurable and clearly documented | All |

---

## 12. Source File Reference

| System | Key Files |
|--------|-----------|
| **Loop** | `LoopKit/LoopKit/CarbKit/CarbMath.swift`, `CarbStatus.swift`, `AbsorbedCarbValue.swift` |
| **oref0** | `lib/determine-basal/cob.js`, `lib/meal/total.js`, `lib/determine-basal/determine-basal.js` |
| **AAPS** | `database/impl/.../entities/Carbs.kt`, `core/data/.../iob/CobInfo.kt` |
| **Trio** | `LoopKit/LoopKit/CarbKit/*` (shared with Loop), oref0 JS execution |
| **Nightscout** | `lib/api/treatments/index.js`, Treatment schema |

---

## 13. Conclusion

The fundamental difference between systems:

1. **Loop/Trio**: Model-first approach with dynamic adaptation. Uses mathematical curves (Parabolic/PiecewiseLinear) as the baseline but adjusts based on observed glucose effects.

2. **oref0/AAPS**: Observation-first approach. Infers carb absorption from glucose deviations, using `min_5m_carbimpact` as a floor to ensure progress.

3. **AAPS Extended Carbs**: Unique feature allowing explicit time-spreading of carb absorption.

For cross-system interoperability, the key challenges are:
- Different default absorption times and curves
- eCarbs not portable to iOS systems
- Dynamic absorption state not exported
- Varying COB cap configurations

---

## 14. Conformance Assertions

The following conformance assertions cover carb absorption requirements:

| Assertion File | Requirements | Assertions |
|----------------|--------------|------------|
| `conformance/assertions/carb-absorption.yaml` | REQ-CARB-001 through REQ-CARB-006 | 34 |

**Key Assertions**:
- `carb-model-001-004`: COB model type annotation in devicestatus
- `carb-impact-001-004`: min_5m_carbimpact documentation
- `carb-select-001-004`: Absorption model selection
- `csf-calc-001-004`: CSF formula consistency
- `abs-time-001-005`: Per-entry absorption time support
- `cob-max-001-006`: COB maximum limits documentation

See `traceability/domain-matrices/aid-algorithms-matrix.md` for full coverage matrix.
