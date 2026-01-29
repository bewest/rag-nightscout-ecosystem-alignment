# Loop vs oref0 Semantic Equivalence Analysis

This document maps Loop algorithm concepts to oref0 equivalents to enable cross-system conformance testing.

---

## Executive Summary

| Aspect | Loop | oref0 | Compatible? |
|--------|------|-------|-------------|
| **Input Format** | `LoopPredictionInput` (JSON/Swift) | `determine_basal()` arguments | ⚠️ Transform needed |
| **Output Format** | `LoopPrediction` + `DoseRecommendation` | `rT` object | ⚠️ Transform needed |
| **Prediction Model** | Single combined curve | 4 separate curves | ❌ Fundamentally different |
| **Dose Calculation** | Temp basal or auto-bolus | Temp basal + SMB | ❌ Different paradigm |
| **Sensitivity** | Static ISF + RetrospectiveCorrection | Static ISF + Autosens | ⚠️ Partially equivalent |

**Conclusion**: Direct vector compatibility is NOT feasible. Loop requires its own conformance runner that validates internal consistency rather than cross-system output matching.

---

## Input Schema Mapping

### Glucose Status

| oref0 Field | Loop Equivalent | Notes |
|-------------|-----------------|-------|
| `glucose_status.glucose` | `glucoseHistory.last().quantity` | Current BG |
| `glucose_status.delta` | Computed from `glucoseHistory` | 5-min difference |
| `glucose_status.short_avgdelta` | Computed from `glucoseHistory` | ~15 min average |
| `glucose_status.long_avgdelta` | Computed from `glucoseHistory` | ~45 min average |
| `glucose_status.date` | `glucoseHistory.last().startDate` | Timestamp |

**Loop Difference**: Loop expects full glucose history array (t-10h to t), not pre-computed status.

### IOB Data

| oref0 Field | Loop Equivalent | Notes |
|-------------|-----------------|-------|
| `iob_data.iob` | Computed from `doses` | Total IOB |
| `iob_data.basaliob` | Computed from `doses` | Basal IOB |
| `iob_data.bolussnooze` | Computed from `doses` | Bolus IOB |
| `iob_data.activity` | Computed from `doses` | Insulin activity |
| `iob_data.iobWithZeroTemp` | Not applicable | oref0-specific |

**Loop Difference**: Loop computes IOB from dose history during prediction, not as pre-computed input.

### Profile

| oref0 Field | Loop Equivalent | Location |
|-------------|-----------------|----------|
| `profile.current_basal` | `settings.basal[].value` | Schedule-based |
| `profile.sens` | `settings.sensitivity[].value` | mg/dL per unit |
| `profile.carb_ratio` | `settings.carbRatio[].value` | g per unit |
| `profile.min_bg` / `max_bg` | `settings.target[].value.minValue/maxValue` | Target range |
| `profile.max_iob` | `settings.maximumBasalRatePerHour` × DIA | Derived |
| `profile.max_basal` | `settings.maximumBasalRatePerHour` | Direct |
| `profile.dia` | `settings.insulinActivityDuration` | TimeInterval (seconds) |

**Loop Difference**: Loop uses schedule arrays with `startDate`/`endDate` instead of single values.

### Carb Data

| oref0 Field | Loop Equivalent | Notes |
|-------------|-----------------|-------|
| `meal_data.carbs` | Sum of `carbEntries[].quantity` | Total carbs |
| `meal_data.mealCOB` | Computed dynamically | From ICE mapping |
| `meal_data.lastCarbTime` | Max of `carbEntries[].startDate` | Last entry time |
| `meal_data.slopeFromMaxDeviation` | Not applicable | oref0-specific (UAM) |
| `meal_data.slopeFromMinDeviation` | Not applicable | oref0-specific (UAM) |

**Loop Difference**: Loop computes COB dynamically using Insulin Counteraction Effects; doesn't use deviation slopes.

### Current Temp

| oref0 Field | Loop Equivalent | Notes |
|-------------|-----------------|-------|
| `currenttemp.rate` | From `doses` array (type: tempBasal) | Most recent |
| `currenttemp.duration` | Computed from endDate - now | Remaining |

### Autosens

| oref0 Field | Loop Equivalent | Notes |
|-------------|-----------------|-------|
| `autosens_data.ratio` | **None** | Loop uses RetrospectiveCorrection instead |

**Key Gap**: Loop does NOT have Autosens. Uses RetrospectiveCorrection which adjusts prediction, not profile values.

---

## Output Schema Mapping

### oref0 Output (`rT`)

```javascript
{
  "temp": "absolute",
  "bg": 150,
  "tick": "+5",
  "eventualBG": 120,
  "targetBG": 100,
  "insulinReq": 0.5,
  "sensitivityRatio": 1.0,
  "predBGs": {
    "IOB": [...],
    "COB": [...],
    "UAM": [...],
    "ZT": [...]
  },
  "reason": "...",
  "rate": 1.5,
  "duration": 30
}
```

### Loop Output (`LoopPrediction`)

```swift
struct LoopPrediction {
    var glucose: [PredictedGlucoseValue]  // Single combined curve
    var effects: LoopAlgorithmEffects {
        insulin: [GlucoseEffect]
        carbs: [GlucoseEffect]
        retrospectiveCorrection: [GlucoseEffect]
        momentum: [GlucoseEffect]
        insulinCounteraction: [GlucoseEffectVelocity]
    }
}
```

### Field Mapping

| oref0 Output | Loop Equivalent | Compatible? |
|--------------|-----------------|-------------|
| `eventualBG` | `glucose.last().quantity` | ⚠️ Different calculation |
| `predBGs.IOB` | Not available | ❌ Loop combines effects |
| `predBGs.COB` | Not available | ❌ Loop combines effects |
| `predBGs.UAM` | Not available | ❌ Loop has no UAM curve |
| `predBGs.ZT` | Not available | ❌ Loop has no ZT curve |
| `rate` | From `DoseRecommendation.basalAdjustment.unitsPerHour` | ⚠️ Separate step |
| `duration` | From `DoseRecommendation.basalAdjustment.duration` | ⚠️ Separate step |
| `insulinReq` | Computed from correction logic | ⚠️ Different formula |
| `sensitivityRatio` | Always 1.0 (no Autosens) | ❌ Not equivalent |

---

## Fundamental Algorithm Differences

### Prediction Methodology

| Aspect | oref0 | Loop |
|--------|-------|------|
| **Curves Generated** | 4 (IOB, COB, UAM, ZT) | 1 (combined) |
| **Safety Floor** | Uses ZT curve minimum | Uses prediction minimum |
| **UAM Handling** | Explicit curve | Implicit via RC |
| **Decision Basis** | minPredBG across curves | Minimize excursions from target |

### Carb Absorption

| Aspect | oref0 | Loop |
|--------|-------|------|
| **Model** | Linear decay + assumed rate | Dynamic piecewise linear |
| **Adaptation** | Limited (deviation-based) | Real-time via ICE |
| **COB Calculation** | Static: `carbs - absorbed` | Dynamic: maps to counteraction |

### Sensitivity Adjustment

| Aspect | oref0 | Loop |
|--------|-------|------|
| **Mechanism** | Autosens ratio (0.7-1.2) | RetrospectiveCorrection |
| **Adjusts** | Profile ISF, basal | Prediction curve |
| **Historical Window** | 8-24 hours | 60 minutes |
| **Output** | `sensitivityRatio` | `rcEffect` array |

### Dosing Strategy

| Aspect | oref0 | Loop |
|--------|-------|------|
| **Primary** | Temp basal + SMB | Temp basal (or auto-bolus) |
| **SMB** | ✅ Supported | ❌ Not supported |
| **Auto-bolus** | N/A | ✅ Optional (different from SMB) |
| **Duration** | 30 minutes default | 30 minutes |

---

## Conformance Testing Approaches

### Option A: Output Comparison (NOT RECOMMENDED)

Direct comparison of Loop and oref0 outputs from same inputs is **not meaningful** because:
1. Different prediction methodologies produce different eventualBG
2. Loop has no equivalent to UAM/ZT curves
3. Dosing decisions use different algorithms

### Option B: Semantic Validation (RECOMMENDED)

Test that Loop maintains internal consistency:

| Test Category | Validation |
|---------------|------------|
| **Prediction Direction** | High BG + negative IOB → prediction should rise |
| **Carb Response** | Recent carbs → prediction should rise then fall |
| **Insulin Response** | Recent bolus → prediction should fall |
| **Safety Bounds** | Prediction never exceeds physiological limits |
| **Dose Safety** | Rate ≤ maxBasalRate, Rate ≥ 0 |
| **Suspend Threshold** | If min(prediction) < suspend → rate = 0 |

### Option C: Effect Isolation (RECOMMENDED)

Test individual effects match expected behavior:

```swift
// Test insulin effect isolation
settings.algorithmEffectsOptions = [.insulin]
let prediction = LoopAlgorithm.generatePrediction(input: input)
// Verify: prediction falls proportional to IOB × ISF
```

```swift
// Test carb effect isolation
settings.algorithmEffectsOptions = [.carbs]
let prediction = LoopAlgorithm.generatePrediction(input: input)
// Verify: prediction rises proportional to COB × CR
```

---

## Implementation Recommendations

### 1. Loop Conformance Runner (Swift)

Create a Swift-based conformance runner that:
- Reads `LoopPredictionInput` JSON fixtures
- Calls `LoopAlgorithm.generatePrediction()`
- Validates semantic assertions

```swift
// conformance/runners/loop-runner.swift
import LoopKit

func runConformanceTest(vectorPath: String) -> TestResult {
    let input = try LoopPredictionInput.load(from: vectorPath)
    let prediction = try LoopAlgorithm.generatePrediction(input: input)
    
    // Semantic validations
    let assertions = loadAssertions(vectorPath)
    return validate(prediction: prediction, against: assertions)
}
```

### 2. Loop Test Vector Format

Extend conformance schema for Loop-specific assertions:

```json
{
  "version": "1.0.0",
  "metadata": {
    "algorithm": "Loop",
    "category": "prediction-direction"
  },
  "input": {
    "glucoseHistory": [...],
    "doses": [...],
    "carbEntries": [...],
    "settings": {...}
  },
  "assertions": [
    {
      "type": "prediction_trend",
      "direction": "falling",
      "reason": "positive IOB should lower BG"
    },
    {
      "type": "final_bg_range",
      "min": 80,
      "max": 180
    },
    {
      "type": "effect_present",
      "effect": "insulin",
      "sign": "negative"
    }
  ]
}
```

### 3. Cross-System Comparison (Long-term)

For meaningful cross-system analysis, compare:

| Metric | How to Compare |
|--------|----------------|
| **Final BG Trend** | Both predict rising/falling/stable? |
| **Dose Direction** | Both increase/decrease/maintain? |
| **Safety Behavior** | Both suspend when appropriate? |
| **Carb Handling** | Both show absorption curve? |

Rather than exact numeric matching.

---

## Gaps Identified

### GAP-ALG-013: Loop Has No Autosens

**Description**: Loop does not implement Autosens sensitivity ratio. Uses RetrospectiveCorrection which adjusts predictions but not profile values.

**Impact**: Cannot compare `sensitivityRatio` across systems.

**Source**: `LoopAlgorithm.swift:120-126`

### GAP-ALG-014: Loop Prediction Is Single Curve

**Description**: Loop produces one combined prediction curve; oref0 produces 4 separate curves (IOB, COB, UAM, ZT).

**Impact**: Cannot compare individual prediction components.

**Source**: `LoopAlgorithm.swift:168` - `LoopMath.predictGlucose()`

### GAP-ALG-015: Loop Does Not Expose UAM Curve

**Description**: Loop has no explicit UAM (Unannounced Meal) curve. Unexpected rises are handled via RetrospectiveCorrection.

**Impact**: Cannot validate UAM-specific behavior in Loop.

**Source**: Algorithm design difference

### GAP-ALG-016: Different IOB/COB Calculation Timing

**Description**: oref0 expects pre-computed IOB/COB as input; Loop computes them from dose/carb history during prediction.

**Impact**: Same input can produce different IOB values due to timing differences.

**Source**: `LoopAlgorithm.swift:95-103` vs `oref0/lib/iob/total.js`

---

## Input Transform Requirements

To run oref0 vectors through Loop, the following transforms are needed:

### 1. Expand Glucose History

oref0 provides `glucose_status` (current + deltas). Loop needs full history:

```javascript
// Transform: glucose_status → glucoseHistory
const glucoseHistory = [];
const now = glucose_status.date;
// Reconstruct from delta (approximation)
glucoseHistory.push({ startDate: now, quantity: glucose_status.glucose });
// Would need additional CGM history for accurate reconstruction
```

### 2. Expand Dose History

oref0 provides `iob_data` (pre-computed). Loop needs dose entries:

```javascript
// Transform: iob_data → doses
// NOT POSSIBLE without original dose records
// oref0 vectors don't include dose history
```

**Blocker**: oref0 vectors don't include raw dose history, only computed IOB.

### 3. Expand Profile to Schedules

```javascript
// Transform: profile → settings
const settings = {
  basal: [{ startDate: startOfDay, endDate: endOfDay, value: profile.current_basal }],
  sensitivity: [{ startDate: startOfDay, endDate: endOfDay, value: profile.sens }],
  carbRatio: [{ startDate: startOfDay, endDate: endOfDay, value: profile.carb_ratio }],
  target: [{ 
    startDate: startOfDay, 
    endDate: endOfDay, 
    value: { minValue: profile.min_bg, maxValue: profile.max_bg }
  }],
  insulinActivityDuration: profile.dia * 3600  // hours to seconds
};
```

---

## Conclusions

1. **Direct output comparison is not feasible** due to fundamental algorithm differences (single vs 4 curves, different sensitivity mechanisms).

2. **Loop requires its own conformance runner** written in Swift that validates semantic correctness rather than numeric output matching.

3. **Cross-system comparison should focus on behavioral equivalence** (dose direction, safety behavior) rather than exact predictions.

4. **oref0 test vectors cannot be directly reused** because Loop needs raw dose/carb history, not pre-computed IOB/COB.

5. **Recommended next step**: Create Loop-specific test vectors from `live_capture_input.json` fixtures with semantic assertions.

---

## Cross-References

- [Algorithm Comparison Deep Dive](./algorithm-comparison-deep-dive.md)
- [AAPS vs oref0 Divergence Analysis](./aaps-oref0-divergence-analysis.md)
- [Terminology Matrix - Algorithm Core](../../mapping/cross-project/terminology-matrix.md#algorithm-core-terminology)
- Loop source: `externals/LoopWorkspace/LoopKit/LoopKit/LoopAlgorithm/`
- Loop fixtures: `externals/LoopWorkspace/Loop/LoopTests/Fixtures/`

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-29 | Agent | Initial semantic equivalence analysis |
