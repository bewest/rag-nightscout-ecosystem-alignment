# AAPS OpenAPSSMB Algorithm

This document describes the OpenAPSSMB algorithm implementation in AAPS, which is a Kotlin port of the oref0/oref1 determine-basal algorithm.

## Overview

AAPS supports multiple algorithm plugins:

| Algorithm | Description | Key Features |
|-----------|-------------|--------------|
| OpenAPSAMA | Advanced Meal Assist | Temp basals only, no SMB |
| **OpenAPSSMB** | Super Micro Bolus | SMB, UAM, primary algorithm |
| OpenAPSAutoISF | Auto ISF variant | Dynamic ISF adjustments |

This document focuses on **OpenAPSSMB** as the primary algorithm.

## Algorithm Entry Point

```kotlin
// aaps:plugins/aps/src/main/kotlin/app/aaps/plugins/aps/openAPSSMB/OpenAPSSMBPlugin.kt
@Singleton
open class OpenAPSSMBPlugin @Inject constructor(
    // ... dependencies ...
) : PluginBase(...), APS, PluginConstraints {

    override fun invoke(initiator: String, tempBasalFallback: Boolean) {
        // Main algorithm execution
    }
}
```

## Input Data Collection

Before running the algorithm, AAPS collects:

```kotlin
// Glucose status
val glucoseStatus = glucoseStatusProvider.glucoseStatusData

// Current profile
val profile = profileFunction.getProfile()

// Current temp basal
val tb = processedTbrEbData.getTempBasalIncludingConvertedExtended(now)
val currentTemp = CurrentTemp(
    duration = tb?.plannedRemainingMinutes ?: 0,
    rate = tb?.convertedToAbsolute(now, profile) ?: 0.0,
    minutesrunning = tb?.getPassedDurationToTimeInMinutes(now)
)

// IOB array for predictions
val iobArray = iobCobCalculator.calculateIobArrayForSMB(autosensResult, ...)

// Meal data
val mealData = iobCobCalculator.getMealDataWithWaitingForCalculationFinish()
```

## Profile Construction

AAPS builds an `OapsProfile` for the algorithm:

```kotlin
val oapsProfile = OapsProfile(
    dia = 0.0,  // Not used directly
    max_iob = constraintsChecker.getMaxIOBAllowed().value(),
    max_daily_basal = profile.getMaxDailyBasal(),
    max_basal = constraintsChecker.getMaxBasalAllowed(profile).value(),
    min_bg = minBg,
    max_bg = maxBg,
    target_bg = targetBg,
    carb_ratio = profile.getIc(),
    sens = profile.getIsfMgdl("OpenAPSSMBPlugin"),
    
    // Safety multipliers
    max_daily_safety_multiplier = preferences.get(DoubleKey.ApsMaxDailyMultiplier),
    current_basal_safety_multiplier = preferences.get(DoubleKey.ApsMaxCurrentBasalMultiplier),
    
    // SMB settings
    enableSMB_always = preferences.get(BooleanKey.ApsUseSmbAlways),
    enableSMB_with_COB = preferences.get(BooleanKey.ApsUseSmbWithCob),
    enableSMB_with_temptarget = preferences.get(BooleanKey.ApsUseSmbWithLowTt),
    enableSMB_after_carbs = preferences.get(BooleanKey.ApsUseSmbAfterCarbs),
    enableUAM = constraintsChecker.isUAMEnabled().value(),
    
    // ... more settings
)
```

## Glucose Status

```kotlin
// aaps:core/interfaces/src/main/kotlin/app/aaps/core/interfaces/aps/GlucoseStatus.kt
data class GlucoseStatus(
    val glucose: Double,           // Current BG (mg/dL)
    val noise: Double,             // Signal noise level
    val delta: Double,             // 5-min delta
    val shortAvgDelta: Double,     // 15-min average delta
    val longAvgDelta: Double,      // 45-min average delta
    val date: Long                 // Timestamp
)
```

## Core Algorithm: DetermineBasalSMB

The algorithm is implemented in `DetermineBasalSMB.kt`:

```kotlin
// aaps:plugins/aps/src/main/kotlin/app/aaps/plugins/aps/openAPSSMB/DetermineBasalSMB.kt
fun determine_basal(
    glucose_status: GlucoseStatus,
    currenttemp: CurrentTemp,
    iob_data_array: Array<IobTotal>,
    profile: OapsProfile,
    autosens_data: AutosensResult,
    meal_data: MealData,
    microBolusAllowed: Boolean,
    currentTime: Long,
    flatBGsDetected: Boolean,
    dynIsfMode: Boolean
): RT
```

### Step 1: Input Validation

```kotlin
// Check for CGM issues
if (bg <= 10 || bg == 38.0 || noise >= 3) {
    rT.reason.append("CGM is calibrating, in ??? state, or noise is high")
}
if (minAgo > 12 || minAgo < -5) {
    rT.reason.append("BG data is too old")
}
if (bg > 60 && flatBGsDetected) {
    rT.reason.append("CGM data is unchanged for the past ~45m")
}
```

### Step 2: Sensitivity Adjustment

```kotlin
// High temp target raises sensitivity
if (high_temptarget_raises_sensitivity && profile.temptargetSet && target_bg > normalTarget) {
    val c = (halfBasalTarget - normalTarget).toDouble()
    sensitivityRatio = c / (c + target_bg - normalTarget)
    sensitivityRatio = min(sensitivityRatio, profile.autosens_max)
}

// Apply autosens ratio
basal = profile.current_basal * sensitivityRatio
```

### Step 3: BGI Calculation

Blood Glucose Impact (BGI) represents how much BG should change based on insulin activity:

```kotlin
// BGI = negative activity * sensitivity * 5 minutes
val bgi = round((-iob_data.activity * sens * 5), 2)
```

### Step 4: Deviation Calculation

Deviation projects how BG differs from insulin-only predictions:

```kotlin
// 30-minute projection of deviation
var deviation = round(30 / 5 * (minDelta - bgi))

// Use more conservative delta if deviation is negative
if (deviation < 0) {
    deviation = round((30 / 5) * (minAvgDelta - bgi))
    if (deviation < 0) {
        deviation = round((30 / 5) * (glucose_status.longAvgDelta - bgi))
    }
}
```

### Step 5: Eventual BG Calculation

```kotlin
// Naive eventualBG based on IOB
val naive_eventualBG = if (dynIsfMode) {
    round(bg - (iob_data.iob * sens), 0)
} else {
    if (iob_data.iob > 0) round(bg - (iob_data.iob * sens), 0)
    else round(bg - (iob_data.iob * min(sens, profile.sens)), 0)
}

// Adjusted for deviation
var eventualBG = naive_eventualBG + deviation
```

### Step 6: Generate Predictions

AAPS generates multiple prediction curves:

| Prediction | Description |
|------------|-------------|
| IOBpredBG | Based on insulin only |
| COBpredBG | Based on COB absorption |
| aCOBpredBG | Accelerated COB (for fast absorbing) |
| UAMpredBG | Unannounced Meal detection |
| ZTpredBG | Zero Temp (what if no basal) |

### Step 7: SMB Decision

```kotlin
fun enable_smb(profile: OapsProfile, microBolusAllowed: Boolean, 
               meal_data: MealData, target_bg: Double): Boolean {
    if (!microBolusAllowed) return false
    
    // High temp target disables SMB
    if (!profile.allowSMB_with_high_temptarget && 
        profile.temptargetSet && target_bg > Constants.ALLOW_SMB_WITH_HIGH_TT) {
        return false
    }
    
    // SMB always on
    if (profile.enableSMB_always) return true
    
    // SMB with COB
    if (profile.enableSMB_with_COB && meal_data.mealCOB != 0.0) return true
    
    // SMB after carbs (6 hour window)
    if (profile.enableSMB_after_carbs && meal_data.carbs != 0.0) return true
    
    // SMB with low temp target
    if (profile.enableSMB_with_temptarget && 
        profile.temptargetSet && target_bg < 100) return true
    
    return false
}
```

## Dynamic ISF

AAPS supports TDD-based dynamic ISF:

```kotlin
// aaps:plugins/aps/src/main/kotlin/app/aaps/plugins/aps/openAPSSMB/OpenAPSSMBPlugin.kt
private fun calculateRawDynIsf(multiplier: Double): DynIsfResult {
    val dynIsfResult = DynIsfResult()
    
    // Calculate TDD components
    dynIsfResult.tdd1D = tddCalculator.averageTDD(tddCalculator.calculate(1))?.data?.totalAmount
    dynIsfResult.tdd7D = tddCalculator.averageTDD(tddCalculator.calculate(7))?.data?.totalAmount
    dynIsfResult.tddLast24H = tddCalculator.calculateDaily(-24, 0)?.totalAmount
    dynIsfResult.tddLast4H = tddCalculator.calculateDaily(-4, 0)?.totalAmount
    dynIsfResult.tddLast8to4H = tddCalculator.calculateDaily(-8, -4)?.totalAmount
    
    // Insulin divisor based on insulin type
    dynIsfResult.insulinDivisor = when {
        insulin.peak > 65 -> 55   // rapid peak: 75
        insulin.peak > 50 -> 65   // ultra rapid peak: 55
        else              -> 75   // lyumjev peak: 45
    }
    
    // Calculate weighted TDD
    val tddWeightedFromLast8H = ((1.4 * tddLast4H) + (0.6 * tddLast8to4H)) * 3
    dynIsfResult.tdd = ((tddWeightedFromLast8H * 0.33) + (tdd7D * 0.34) + (tdd1D * 0.33)) 
        * adjustmentFactor / 100.0 * multiplier
    
    // Variable sensitivity formula
    dynIsfResult.variableSensitivity = Round.roundTo(
        1800 / (tdd * ln((glucose / insulinDivisor) + 1)), 
        0.1
    )
    
    return dynIsfResult
}
```

### TDD Weighting

| Component | Weight | Description |
|-----------|--------|-------------|
| tddWeightedFromLast8H | 33% | Recent trend (weighted 4h vs 8-4h) |
| tdd7D | 34% | 7-day average stability |
| tdd1D | 33% | Yesterday's total |

## Autosens

When not using Dynamic ISF, AAPS uses Autosens:

```kotlin
if (constraintsChecker.isAutosensModeEnabled().value()) {
    val autosensData = iobCobCalculator.getLastAutosensDataWithWaitForCalculationFinish("OpenAPSPlugin")
    autosensResult = autosensData.autosensResult
}
```

Autosens adjusts:
- Basal rate
- ISF (insulin sensitivity factor)
- Target BG (optional)

## Safety Constraints

Before invoking the algorithm, hard limits are checked:

```kotlin
// DIA limits
hardLimits.checkHardLimits(profile.dia, R.string.profile_dia, 
    hardLimits.minDia(), hardLimits.maxDia())

// CR limits
hardLimits.checkHardLimits(profile.getIc(), R.string.profile_carbs_ratio_value,
    hardLimits.minIC(), hardLimits.maxIC())

// ISF limits
hardLimits.checkHardLimits(profile.getIsfMgdl(), R.string.profile_sensitivity_value,
    HardLimits.MIN_ISF, HardLimits.MAX_ISF)

// Max basal limits
hardLimits.checkHardLimits(profile.getMaxDailyBasal(), R.string.profile_max_daily_basal_value,
    0.02, hardLimits.maxBasal())
```

## Max Safe Basal

```kotlin
fun getMaxSafeBasal(profile: OapsProfile): Double =
    min(profile.max_basal, 
        min(profile.max_daily_safety_multiplier * profile.max_daily_basal, 
            profile.current_basal_safety_multiplier * profile.current_basal))
```

## Output: RT (Result)

The algorithm returns an `RT` object:

```kotlin
data class RT(
    val algorithm: APSResult.Algorithm,
    val runningDynamicIsf: Boolean,
    val timestamp: Long,
    var bg: Double = 0.0,
    var tick: String = "",
    var eventualBG: Double = 0.0,
    var targetBG: Double = 0.0,
    var insulinReq: Double = 0.0,
    var deliverAt: Long = 0,
    var sensitivityRatio: Double = 1.0,
    var rate: Double = 0.0,
    var duration: Int = 0,
    var units: Double = 0.0,           // SMB amount
    val reason: StringBuilder = StringBuilder(),
    val consoleLog: MutableList<String>,
    val consoleError: MutableList<String>,
    val variable_sens: Double? = null
)
```

## Predictions Structure

```kotlin
data class Predictions(
    val IOB: MutableList<Double>,
    val COB: MutableList<Double>,
    val aCOB: MutableList<Double>,
    val UAM: MutableList<Double>,
    val ZT: MutableList<Double>
)
```

## Comparison with Loop

| Aspect | AAPS OpenAPSSMB | Loop |
|--------|-----------------|------|
| Origin | oref0/oref1 ported to Kotlin | Custom Swift implementation |
| SMB | Explicit Super Micro Bolus | Automatic Dose (similar concept) |
| UAM | Built-in detection | No explicit UAM |
| Sensitivity | Autosens or TDD-based DynISF | Retrospective Correction |
| Predictions | IOB, COB, UAM, ZT curves | Combined effect blending |
| Carb model | Assumed linear absorption rate | Dynamic piecewise linear |

## Key Constants

From `SMBDefaults`:

```kotlin
object SMBDefaults {
    const val adv_target_adjustments = false
    const val exercise_mode = false
    const val half_basal_exercise_target = 160
    const val maxCOB = 120
    const val remainingCarbsCap = 90
}
```

## Algorithm Variants

### OpenAPSAMA (Legacy)
- Temp basals only (no SMB)
- Simpler, more conservative
- Still used by some users

### OpenAPSAutoISF
- Dynamic ISF based on BG delta patterns
- More aggressive ISF adjustments
- Separate glucose status calculator
