# Bolus Wizard Formula Comparison

**Date:** 2026-01-29  
**Status:** Complete  
**Type:** Cross-controller analysis

## Overview

This document compares bolus calculation formulas across Loop, AAPS, and Trio. The bolus wizard/calculator is a core safety-critical feature that recommends insulin doses based on carbs, current glucose, IOB, and user settings.

## Formula Summary

### Standard Bolus Wizard Formula

```
Total Bolus = Carb Bolus + Correction Bolus - IOB

Where:
  Carb Bolus = Carbs (g) / ICR (g/U)
  Correction Bolus = (BG - Target) / ISF
  IOB = Active insulin from prior doses
```

---

## AAPS Bolus Wizard

**Source:** `externals/AndroidAPS/core/objects/src/main/kotlin/app/aaps/core/objects/wizard/BolusWizard.kt:60-284`

### Formula Implementation

```kotlin
// Lines 228-231: Carb bolus
ic = profile.getIc()
insulinFromCarbs = carbs / ic
insulinFromCOB = if (useCob) (cob / ic) else 0.0

// Lines 210-216: Correction bolus
bgDiff = when {
    bg in targetBGLow..targetBGHigh -> 0.0
    bg <= targetBGLow               -> bg - targetBGLow
    else                            -> bg - targetBGHigh
}
insulinFromBG = bgDiff / sens

// Lines 222-225: Trend correction (optional)
trend = glucoseStatus.shortAvgDelta
insulinFromTrend = trend * 3 / sens  // 15-min trend extrapolated

// Lines 235-242: IOB subtraction
insulinFromBolusIOB = if (includeBolusIOB) bolusIob.iob else 0.0
insulinFromBasalIOB = if (includeBasalIOB) basalIob.basaliob else 0.0

// Line 256: Total calculation
calculatedTotalInsulin = insulinFromBG + insulinFromTrend + insulinFromCarbs 
                       + calculatedTotalIOB + insulinFromCorrection 
                       + insulinFromSuperBolus + insulinFromCOB
```

### AAPS-Specific Features

| Feature | Description | Line |
|---------|-------------|------|
| **Trend correction** | 15-min delta × 3 / ISF | 224 |
| **SuperBolus** | Add 2h basal to bolus | 248-253 |
| **COB coverage** | Include pending carbs | 231 |
| **Percentage adjustment** | Scale total by % | 258-275 |
| **Positive IOB only** | Ignore negative IOB | 242 |
| **Separate basal/bolus IOB** | Optional inclusion | 238-239 |

### Target Handling

AAPS uses a target **range** (low to high):
- If BG is within range: no correction
- If BG < target_low: negative correction (reduces bolus)
- If BG > target_high: positive correction

---

## Loop Bolus Recommendation

**Source:** `externals/LoopWorkspace/LoopKit/LoopKit/LoopAlgorithm/DoseMath.swift:540-575`

### Formula Implementation

Loop uses a **prediction-based** approach rather than simple arithmetic:

```swift
// Lines 540-575: Manual bolus recommendation
public func recommendedManualBolus(
    to correctionRange: GlucoseRangeSchedule,
    suspendThreshold: HKQuantity?,
    sensitivity: InsulinSensitivitySchedule,
    model: InsulinModel,
    pendingInsulin: Double,
    maxBolus: Double
) -> ManualBolusRecommendation {
    
    // Get correction from prediction curve
    let correction = self.insulinCorrection(
        to: correctionRange,
        suspendThreshold: suspendThreshold,
        sensitivity: sensitivity.quantity(at: date),
        model: model
    )
    
    return correction.asManualBolus(
        pendingInsulin: pendingInsulin,
        maxBolus: maxBolus
    )
}
```

### Correction Calculation (Lines 275-332)

```swift
// For each prediction above target:
for prediction in self {
    let predictedGlucoseValue = prediction.quantity.doubleValue(for: unit)
    
    // Compute target as function of time (dynamic target)
    let targetValue = targetGlucoseValue(
        percentEffectDuration: time / model.effectDuration,
        minValue: suspendThresholdValue,
        maxValue: correctionRange.averageValue
    )
    
    // dose = (Glucose Δ) / (% effect × sensitivity)
    correctionUnits = insulinCorrectionUnits(
        fromValue: predictedGlucoseValue,
        toValue: targetValue,
        effectedSensitivity: percentEffected * isf
    )
}
```

### Loop-Specific Features

| Feature | Description |
|---------|-------------|
| **Prediction-based** | Uses future BG curve, not current BG |
| **Dynamic target** | Target rises from suspend threshold to correction range |
| **Effect modeling** | Accounts for insulin % remaining at each time point |
| **Pending insulin** | Subtracts all scheduled/pending insulin |
| **Suspend threshold** | Returns 0 if any prediction below threshold |
| **Min glucose check** | Notices for below-target predictions |

### Key Difference: Loop vs Traditional

Traditional wizard: `(Current BG - Target) / ISF`

Loop: `(Predicted BG at time T - Dynamic Target at T) / (Effect% × ISF)`

Loop's approach considers the **entire prediction curve** and accounts for when insulin will be active, not just current BG.

---

## Trio Bolus Calculation

**Source:** Trio uses oref1 algorithm via JavaScript bridge

Trio inherits LoopKit for UI but uses oref1 for algorithm decisions. The bolus is computed similarly to AAPS/oref0:

```javascript
// oref0/lib/determine-basal/determine-basal.js
var insulinReq = (eventualBG - target) / sens;
```

However, Trio's manual bolus UI may use LoopKit's calculation when not in closed-loop mode.

---

## Comparison Matrix

| Feature | AAPS | Loop | Trio |
|---------|------|------|------|
| **Carb bolus** | `carbs / ICR` | `carbs / ICR` | `carbs / ICR` |
| **Correction formula** | `(BG - target) / ISF` | Prediction-based | `(eventualBG - target) / ISF` |
| **BG used** | Current | Predicted curve | Eventual (5h) |
| **Target handling** | Range (low-high) | Range (dynamic) | Single midpoint |
| **Trend adjustment** | Optional (15min × 3) | Included in prediction | Via algorithm |
| **IOB subtraction** | Explicit toggle | Pending insulin | Automatic |
| **Basal IOB** | Optional toggle | Included | Included |
| **SuperBolus** | ✅ Supported | ❌ Not available | ❌ Not available |
| **COB inclusion** | Optional toggle | Via prediction | Via algorithm |
| **Percentage scaling** | ✅ 0-200% | ❌ Not available | ❌ Not available |

---

## IOB Handling Differences

### AAPS IOB

```kotlin
// Lines 235-242
insulinFromBolusIOB = if (includeBolusIOB) bolusIob.iob else 0.0
insulinFromBasalIOB = if (includeBasalIOB) basalIob.basaliob else 0.0

// User can toggle each separately
// Can also use "positive IOB only" to ignore negative IOB
```

### Loop IOB

```swift
// pendingInsulin includes all active insulin
pendingInsulin: Double  // Combined IOB from all sources

// Subtracted in asManualBolus:
units = Swift.max(0, units - pendingInsulin)
```

### Key Difference

- **AAPS**: Separates bolus IOB and basal IOB, user chooses which to include
- **Loop**: Single "pending insulin" value, always subtracted

---

## Rounding and Constraints

### AAPS

```kotlin
// Line 277-280
val bolusStep = activePlugin.activePump.pumpDescription.bolusStep
calculatedTotalInsulin = Round.roundTo(calculatedTotalInsulin, bolusStep)
insulinAfterConstraints = constraintChecker.applyBolusConstraints(...)
```

### Loop

```swift
// DoseMath.swift:97
units = Swift.min(maxBolus, Swift.max(0, units))
// volumeRounder callback for pump-specific rounding
volumeRounder?(partialDose) ?? partialDose
```

---

## Safety Checks

### AAPS Safety

1. **Max bolus constraint** - Applied via ConstraintsChecker
2. **Pump step size** - Rounded to pump capabilities
3. **Target range** - No correction if in range
4. **Negative result** - Returns carb equivalents instead

### Loop Safety

1. **Suspend threshold** - Returns 0 if any prediction below threshold
2. **Max bolus** - Hard cap applied
3. **Below-target notice** - Warns but may still recommend
4. **Pending insulin** - Always subtracted to prevent stacking

---

## Gaps Identified

### GAP-BOLUS-001: Prediction-Based vs Arithmetic Formula

**Description:** Loop uses prediction-based bolus calculation while AAPS uses traditional arithmetic formula. Same inputs produce different recommendations.

**Source:** 
- `externals/AndroidAPS/.../BolusWizard.kt:210-216`
- `externals/LoopWorkspace/.../DoseMath.swift:275-332`

**Impact:** Users switching between systems will see different bolus recommendations for identical situations.

**Remediation:** Document expected differences; no standardization needed as different approaches are intentional.

### GAP-BOLUS-002: IOB Handling Mismatch

**Description:** AAPS separates bolus/basal IOB with user toggles; Loop uses combined pending insulin.

**Source:** 
- `externals/AndroidAPS/.../BolusWizard.kt:235-242`
- `externals/LoopWorkspace/.../DoseMath.swift:546`

**Impact:** Different IOB subtraction behavior; AAPS allows excluding basal IOB.

**Remediation:** Document as intentional design difference.

### GAP-BOLUS-003: SuperBolus Not Portable

**Description:** AAPS SuperBolus feature (add 2h basal to bolus) has no Loop equivalent.

**Source:** `externals/AndroidAPS/.../BolusWizard.kt:248-253`

**Impact:** Feature not available when switching to Loop.

**Remediation:** Document as AAPS-specific feature.

### GAP-BOLUS-004: Trend Correction Differences

**Description:** AAPS has explicit trend correction toggle; Loop incorporates trend via prediction.

**Source:** `externals/AndroidAPS/.../BolusWizard.kt:222-225`

**Impact:** AAPS trend correction is linear extrapolation; Loop uses full prediction model.

**Remediation:** Document different approaches.

---

## Nightscout Treatment Sync

Bolus wizard results sync to Nightscout as treatments:

### AAPS → Nightscout

```kotlin
// BolusWizard.kt:286-300
fun createBolusCalculatorResult(): BCR {
    return BCR(
        targetBGLow, targetBGHigh,
        isf, ic,
        bolusIOB, basalIOB,
        glucoseValue, glucoseDifference,
        // ... all inputs preserved
    )
}
```

### Loop → Nightscout

Loop sends bolus treatments but not detailed wizard inputs to Nightscout.

---

## Source File References

| Project | File | Key Lines |
|---------|------|-----------|
| AAPS | `core/objects/wizard/BolusWizard.kt` | 154-284 (doCalc) |
| Loop | `LoopKit/LoopAlgorithm/DoseMath.swift` | 540-575 (recommendedManualBolus) |
| Loop | `LoopKit/LoopAlgorithm/DoseMath.swift` | 275-332 (correction calculation) |
| Trio | Uses oref1 via JavaScript | - |

---

## Related Documents

- `docs/10-domain/profile-schema-alignment.md` - ISF, ICR, targets
- `docs/10-domain/algorithm-comparison-deep-dive.md` - Algorithm differences
- `mapping/cross-project/terminology-matrix.md` - Term mappings
