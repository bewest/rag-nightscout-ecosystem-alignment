# AAPS Carb Math

This document describes how AAPS calculates Carbs on Board (COB) and handles meal detection, including Unannounced Meal (UAM) detection.

## Overview

AAPS tracks carbohydrate absorption to predict glucose effects. Unlike Loop's dynamic absorption model, AAPS uses a simpler assumed linear absorption rate with UAM detection for unannounced carbs.

## Key Concepts

| Term | Description |
|------|-------------|
| COB | Carbs on Board - remaining unabsorbed carbs |
| CI | Carb Impact - effect on BG in mg/dL per 5 min |
| CSF | Carb Sensitivity Factor - mg/dL per gram |
| UAM | Unannounced Meal - detected carbs not entered |

## MealData Structure

```kotlin
// aaps:core/interfaces/src/main/kotlin/app/aaps/core/interfaces/aps/MealData.kt
data class MealData(
    val carbs: Double,                // Total carbs in window
    val mealCOB: Double,              // Current COB
    val lastBolusTime: Long,          // Last bolus timestamp
    val lastCarbTime: Long,           // Last carb entry timestamp
    val lastEatTime: Long,            // Last eating time
    val usedMinCarbsImpact: Double,   // Minimum carb impact used
    val slopeFromMaxDeviation: Double,
    val slopeFromMinDeviation: Double
)
```

## COB Calculation

COB is calculated by the `IobCobCalculator`:

```kotlin
// Calculate remaining carbs from each entry
for (carbEntry in carbEntries) {
    val elapsed = now - carbEntry.timestamp
    val absorptionTime = carbEntry.absorptionTime ?: defaultAbsorptionTime
    
    if (elapsed < absorptionTime) {
        // Linear decay
        val remaining = carbEntry.amount * (1 - elapsed / absorptionTime)
        totalCOB += remaining
    }
}
```

### Default Absorption Times

AAPS uses profile-defined absorption times:
- Fast carbs: ~30 minutes
- Medium carbs: ~60 minutes (default)
- Slow carbs: ~120+ minutes

## Carb Impact (CI)

Carb Impact represents the current glucose effect from carbs:

```kotlin
// In DetermineBasalSMB.determine_basal()
// CI = current carb impact on BG in mg/dL per 5m
val ci = round((minDelta - bgi), 1)
val uci = round((minDelta - bgi), 1)  // Unannounced carb impact
```

Where:
- `minDelta` = minimum of recent glucose deltas
- `bgi` = Blood Glucose Impact from insulin

If glucose is rising more than expected from insulin, the difference is attributed to carbs (announced or unannounced).

## Carb Sensitivity Factor (CSF)

CSF converts carbs to glucose effect:

```kotlin
// CSF = ISF / CR
// (mg/dL per U) / (g per U) = mg/dL per g
val csf = sens / profile.carb_ratio
```

## Maximum Carb Absorption Rate

AAPS limits assumed carb absorption:

```kotlin
val maxCarbAbsorptionRate = 30  // g/h maximum
val maxCI = round(maxCarbAbsorptionRate * csf * 5 / 60, 1)

if (ci > maxCI) {
    consoleError.add("Limiting carb impact from $ci to $maxCI mg/dL/5m")
    ci = maxCI
}
```

## Remaining Carb Absorption Time

```kotlin
var remainingCATimeMin = 3.0  // hours; default duration

// Adjust for sensitivity
remainingCATimeMin = remainingCATimeMin / sensitivityRatio

// Adjust for actual carb amount
if (meal_data.carbs != 0.0) {
    val assumedCarbAbsorptionRate = 20  // g/h
    remainingCATimeMin = max(remainingCATimeMin, meal_data.mealCOB / assumedCarbAbsorptionRate)
    
    val lastCarbAge = (now - meal_data.lastCarbTime) / 60000.0  // minutes
    val remainingCATime = remainingCATimeMin + 1.5 * lastCarbAge / 60
}
```

## Remaining Carbs Prediction

AAPS predicts remaining carb impact using a triangular absorption model:

```kotlin
// Total CI over remaining time (triangle area)
val totalCI = max(0.0, ci / 5 * 60 * remainingCATime / 2)

// Convert to carbs
val totalCA = totalCI / csf

// Cap remaining carbs
var remainingCarbs = max(0.0, meal_data.mealCOB - totalCA)
remainingCarbs = min(remainingCarbsCap.toDouble(), remainingCarbs)

// Peak remaining carb impact (triangular shape)
val remainingCIpeak = remainingCarbs * csf * 5 / 60 / (remainingCATime / 2)
```

## UAM (Unannounced Meal) Detection

UAM detects carbs that weren't entered:

```kotlin
// Enable UAM if:
// 1. UAM enabled in preferences
// 2. BG is rising faster than expected from insulin
val enableUAM = profile.enableUAM

// UAM prediction uses deviation to estimate glucose rise
if (enableUAM && uci > 0) {
    // Project UAM effect forward
    for (i in 1..48) {  // 4 hours of 5-min intervals
        var UAMpredBG = UAMpredBGs.last() + uci
        // ... decay and constraints
        UAMpredBGs.add(UAMpredBG)
    }
}
```

### UAM Behavior

1. **Detection**: BG rising faster than BGI predicts
2. **Prediction**: Project continued rise with decay
3. **Response**: Increase insulin delivery (temp basal or SMB)

## SMB with COB

SMB delivery is enabled based on carb state:

```kotlin
// Enable SMB if COB present
if (profile.enableSMB_with_COB && meal_data.mealCOB != 0.0) {
    consoleError.add("SMB enabled for COB of ${meal_data.mealCOB}")
    return true
}

// Enable SMB for 6 hours after carb entry
if (profile.enableSMB_after_carbs && meal_data.carbs != 0.0) {
    consoleError.add("SMB enabled for 6h after carb entry")
    return true
}
```

## COB Prediction Curves

AAPS generates multiple COB-based predictions:

### COBpredBG (Standard COB)

```kotlin
// Linear decay of remaining carbs
for (i in predictions) {
    val carbsRemaining = remainingCarbs * decayFactor
    val carbEffect = carbsRemaining * csf / absorptionTime
    COBpredBGs.add(currentBG + carbEffect - insulinEffect)
}
```

### aCOBpredBG (Accelerated COB)

Used when absorption appears faster than expected:
```kotlin
// Use actual observed CI rather than assumed
aCOBpredBGs.add(currentBG + actualCI - insulinEffect)
```

## Carb Entry Extended (eCarbs)

AAPS supports extended carb entries:

```kotlin
// NSCarbs model
data class NSCarbs(
    val carbs: Double,        // Carb amount
    val duration: Long?       // Duration for extended absorption (ms)
) : NSTreatment
```

Extended carbs spread absorption over a longer period for:
- High-fat meals (pizza, etc.)
- Slow-absorbing foods
- Multi-course meals

## Comparison with Loop

| Aspect | AAPS | Loop |
|--------|------|------|
| Model | Linear decay (assumed rate) | Piecewise linear (adaptive) |
| UAM | Explicit detection | No UAM (uses RC) |
| Adaptation | None (uses assumed rates) | Dynamic based on observed absorption |
| Extended Carbs | Explicit duration field | N/A (uses absorption time) |
| Min Impact | min_5m_carbimpact setting | Implicitly handled |

## Key Parameters

| Parameter | Typical Value | Description |
|-----------|---------------|-------------|
| maxCarbAbsorptionRate | 30 g/h | Maximum assumed absorption |
| assumedCarbAbsorptionRate | 20 g/h | Default expected rate |
| remainingCarbsCap | 90 g | Maximum remaining carbs to consider |
| maxCOB | 120 g | Maximum COB limit |
| min_5m_carbimpact | 3-8 mg/dL | Minimum carb impact per 5 min |

## Carb Entry Best Practices

1. **Enter carbs before eating** - Allows pre-bolus calculation
2. **Use accurate amounts** - Affects predictions significantly
3. **Choose appropriate absorption time** - Fast vs slow carbs
4. **Consider UAM for unpredictable meals** - Enable when needed
5. **Extended carbs for complex meals** - Pizza, high-fat foods

## Database Entity

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/Carbs.kt
data class Carbs(
    override var id: Long = 0,
    override var timestamp: Long,
    override var utcOffset: Long,
    var amount: Double,               // Carb grams
    var duration: Long = 0,           // Extended duration (ms)
    var notes: String? = null
) : TraceableDBEntry, DBEntryWithTime
```

## Nightscout Mapping

| AAPS Field | Nightscout Field | Notes |
|------------|------------------|-------|
| `amount` | `carbs` | Grams |
| `duration` | `duration` | For eCarbs |
| `timestamp` | `created_at` / `date` | Entry time |
| `notes` | `notes` | Free text |
| eventType | `Carb Correction` | Default |
