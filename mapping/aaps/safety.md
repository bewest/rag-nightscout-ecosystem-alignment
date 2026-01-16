# AAPS Safety Constraints

This document describes AAPS's safety constraint system, including hard limits, constraint plugins, and guardrails.

## Overview

AAPS implements a multi-layer safety system:

1. **Hard Limits** - Absolute boundaries that cannot be overridden
2. **Constraints Checker** - Plugin-based constraint aggregation
3. **Algorithm Constraints** - Per-algorithm safety checks
4. **Pump Constraints** - Pump-specific limitations

## Hard Limits

```kotlin
// aaps:core/interfaces/src/main/kotlin/app/aaps/core/interfaces/utils/HardLimits.kt
interface HardLimits {
    companion object {
        const val MIN_ISF = 2.0                  // Minimum ISF (mg/dL per U)
        const val MAX_ISF = 1000.0               // Maximum ISF
        const val MAX_CARBS = 300                // Maximum carbs per entry
        
        // Glucose target limits
        val LIMIT_MIN_BG = arrayOf(72.0, 180.0)      // [min, max] for min_bg
        val LIMIT_MAX_BG = arrayOf(90.0, 270.0)      // [min, max] for max_bg
        val LIMIT_TARGET_BG = arrayOf(80.0, 200.0)   // [min, max] for target
        
        // Temp target limits (wider range)
        val LIMIT_TEMP_MIN_BG = arrayOf(72.0, 180.0)
        val LIMIT_TEMP_MAX_BG = arrayOf(72.0, 270.0)
        val LIMIT_TEMP_TARGET_BG = arrayOf(72.0, 200.0)
    }
    
    fun minDia(): Double      // Minimum DIA (5 hours)
    fun maxDia(): Double      // Maximum DIA
    fun minIC(): Double       // Minimum carb ratio
    fun maxIC(): Double       // Maximum carb ratio
    fun maxBasal(): Double    // Maximum basal rate
}
```

### DIA Limits

```kotlin
// Minimum 5 hours, enforced at insulin model level
override val dia: Double
    get() = if (userDefinedDia >= hardLimits.minDia()) 
                userDefinedDia 
            else hardLimits.minDia()
```

## Constraints Checker

The `ConstraintsChecker` aggregates constraints from all enabled plugins:

```kotlin
// aaps:plugins/constraints/src/main/kotlin/app/aaps/plugins/constraints/ConstraintsCheckerImpl.kt
@Singleton
class ConstraintsCheckerImpl @Inject constructor(
    private val activePlugin: ActivePlugin,
    private val aapsLogger: AAPSLogger
) : ConstraintsChecker {

    override fun isClosedLoopAllowed(value: Constraint<Boolean>): Constraint<Boolean> {
        val constraintsPlugins = activePlugin.getSpecificPluginsListByInterface(PluginConstraints::class.java)
        for (p in constraintsPlugins) {
            if (!p.isEnabled()) continue
            (p as PluginConstraints).isClosedLoopAllowed(value)
        }
        return value
    }
    
    // Similar for all other constraint types...
}
```

### Constraint Types

| Method | Returns | Description |
|--------|---------|-------------|
| `isLoopInvocationAllowed()` | Boolean | Can loop run? |
| `isClosedLoopAllowed()` | Boolean | Can loop make decisions? |
| `isLgsForced()` | Boolean | Force Low Glucose Suspend? |
| `isAutosensModeEnabled()` | Boolean | Can autosens adjust? |
| `isSMBModeEnabled()` | Boolean | Can SMB be used? |
| `isUAMEnabled()` | Boolean | Can UAM detect meals? |
| `isAdvancedFilteringEnabled()` | Boolean | CGM filtering available? |
| `isSuperBolusEnabled()` | Boolean | Can superbolus be used? |
| `isAutomationEnabled()` | Boolean | Can automation run? |
| `getMaxBasalAllowed()` | Double | Maximum basal rate |
| `getMaxIOBAllowed()` | Double | Maximum IOB |
| `getMaxBolusAllowed()` | Double | Maximum bolus |
| `getMaxCarbsAllowed()` | Int | Maximum carb entry |

## Constraint Object

Constraints carry both value and reasoning:

```kotlin
// aaps:core/objects/src/main/kotlin/app/aaps/core/objects/constraints/ConstraintObject.kt
class ConstraintObject<T>(
    var value: T,
    private val aapsLogger: AAPSLogger
) : Constraint<T> {
    
    private val reasons = mutableListOf<String>()
    private val mostLimiting = mutableListOf<String>()
    
    override fun set(newValue: T, reason: String, source: Any): Constraint<T> {
        reasons.add("$source: $reason")
        value = newValue
        return this
    }
    
    override fun addReason(reason: String, source: Any): Constraint<T> {
        reasons.add("$source: $reason")
        return this
    }
}
```

## Max Safe Basal

The algorithm enforces maximum safe basal:

```kotlin
// In DetermineBasalSMB.kt
fun getMaxSafeBasal(profile: OapsProfile): Double =
    min(profile.max_basal, 
        min(profile.max_daily_safety_multiplier * profile.max_daily_basal, 
            profile.current_basal_safety_multiplier * profile.current_basal))
```

Where:
- `max_basal` - User-defined maximum
- `max_daily_safety_multiplier` - Multiple of max daily basal (default 3x)
- `current_basal_safety_multiplier` - Multiple of current basal (default 4x)

## Max IOB

Maximum IOB limits total non-bolus insulin on board:

```kotlin
// In OapsProfile
val max_iob = constraintsChecker.getMaxIOBAllowed().value()
```

The algorithm will not recommend insulin that would exceed max_iob:

```kotlin
// In determine_basal
if (iob_data.iob > max_iob) {
    // Reduce or cancel insulin delivery
}
```

## SMB Constraints

SMB delivery has additional constraints:

```kotlin
// Max SMB in one delivery
val maxSMBBasalMinutes = preferences.get(IntKey.ApsMaxSmbMinutes)
val maxUAMBasalMinutes = preferences.get(IntKey.ApsUamMaxMinutesOfBasalToLimitSmb)

// SMB = min(required, maxSMBBasalMinutes of basal)
val smbAmount = min(insulinReq, profile.current_basal * maxSMBBasalMinutes / 60)
```

### SMB Enable Conditions

```kotlin
fun enable_smb(): Boolean {
    if (!microBolusAllowed) return false
    
    // High temp target disables SMB
    if (!profile.allowSMB_with_high_temptarget && 
        profile.temptargetSet && target_bg > ALLOW_SMB_WITH_HIGH_TT) {
        return false
    }
    
    // Must have one enable condition
    return profile.enableSMB_always ||
           (profile.enableSMB_with_COB && meal_data.mealCOB != 0.0) ||
           (profile.enableSMB_after_carbs && meal_data.carbs != 0.0) ||
           (profile.enableSMB_with_temptarget && profile.temptargetSet && target_bg < 100)
}
```

## Low Glucose Suspend (LGS) Threshold

```kotlin
// In OapsProfile
lgsThreshold = profileUtil.convertToMgdlDetect(preferences.get(UnitDoubleKey.ApsLgsThreshold)).toInt()

// In algorithm
var threshold = min_bg - 0.5 * (min_bg - 40)
if (profile.lgsThreshold != null && lgsThreshold > threshold) {
    threshold = lgsThreshold.toDouble()
}
```

When predicted BG falls below threshold, basal is suspended.

## Objectives System

AAPS uses an Objectives system to progressively unlock features:

```kotlin
// aaps:plugins/constraints/src/main/kotlin/app/aaps/plugins/constraints/objectives/ObjectivesPlugin.kt
class ObjectivesPlugin : PluginBase, PluginConstraints {
    
    val objectives = listOf(
        Objective0(rh),  // Basic understanding
        Objective1(rh),  // Open loop
        Objective2(rh),  // Low glucose suspend
        Objective3(rh),  // Closed loop
        Objective4(rh),  // MaxIOB > 0
        Objective5(rh),  // SMB
        // ...
    )
}
```

New users cannot enable SMB until completing earlier objectives.

## Pump Constraints

Each pump driver can add constraints:

```kotlin
interface PumpPluginBase : PluginConstraints {
    override fun applyBasalConstraints(absoluteRate: Constraint<Double>, profile: Profile): Constraint<Double> {
        // Limit to pump's maximum basal rate
        absoluteRate.setIfSmaller(pumpDescription.maxTempBasal, ...)
        return absoluteRate
    }
}
```

## BG Quality Check

```kotlin
// aaps:plugins/constraints/src/main/kotlin/app/aaps/plugins/constraints/bgQualityCheck/BgQualityCheckPlugin.kt
class BgQualityCheckPlugin : PluginBase, PluginConstraints, BgQualityCheck {
    
    override fun isLoopInvocationAllowed(value: Constraint<Boolean>): Constraint<Boolean> {
        if (!isBgQualitySufficient()) {
            value.set(false, "BG quality insufficient", this)
        }
        return value
    }
}
```

Checks for:
- Flat BG readings (sensor failure)
- Noisy readings
- Stale data

## Safety Defaults

```kotlin
// aaps:core/data/src/main/kotlin/app/aaps/core/data/aps/SMBDefaults.kt
object SMBDefaults {
    const val adv_target_adjustments = false
    const val exercise_mode = false
    const val half_basal_exercise_target = 160
    const val maxCOB = 120
    const val remainingCarbsCap = 90
}
```

## Algorithm Hard Limit Checks

Before running, the algorithm validates:

```kotlin
// In OpenAPSSMBPlugin.invoke()
if (!hardLimits.checkHardLimits(profile.dia, R.string.profile_dia, 
        hardLimits.minDia(), hardLimits.maxDia())) return

if (!hardLimits.checkHardLimits(profile.getIc(), R.string.profile_carbs_ratio_value,
        hardLimits.minIC(), hardLimits.maxIC())) return

if (!hardLimits.checkHardLimits(profile.getIsfMgdl(), R.string.profile_sensitivity_value,
        HardLimits.MIN_ISF, HardLimits.MAX_ISF)) return

if (!hardLimits.checkHardLimits(profile.getMaxDailyBasal(), R.string.profile_max_daily_basal_value,
        0.02, hardLimits.maxBasal())) return

if (!hardLimits.checkHardLimits(pump.baseBasalRate, R.string.current_basal_value,
        0.01, hardLimits.maxBasal())) return
```

## Error States

The algorithm returns safely on error conditions:

```kotlin
// CGM issues
if (bg <= 10 || bg == 38.0 || noise >= 3 || minAgo > 12 || flatBGsDetected) {
    if (currenttemp.rate > basal) {
        // Cancel high temp
        rT.rate = basal
        rT.duration = 30
    } else if (currenttemp.rate == 0.0 && currenttemp.duration > 30) {
        // Shorten long zero temp
        rT.duration = 30
    }
    return rT  // Take no aggressive action
}
```

## Summary Table

| Constraint | Type | Default | Purpose |
|------------|------|---------|---------|
| Max IOB | User setting | 0 initially | Limit total active insulin |
| Max Basal | User setting | Profile max | Limit temp basal rate |
| Max SMB | User setting | 3 min of basal | Limit SMB size |
| LGS Threshold | User setting | Based on target | Suspend threshold |
| DIA | Hard limit | 5 hours min | Minimum duration |
| ISF | Hard limit | 2-1000 mg/dL/U | Sensitivity range |
| Objectives | Progressive | Locked features | Safety onboarding |

## Comparison with Loop

| Safety Feature | AAPS | Loop |
|---------------|------|------|
| Max IOB | Explicit setting | Computed from settings |
| Max Basal | Multi-factor (max of multipliers) | Single max setting |
| SMB | Conditional enable flags | Always with appropriate dose |
| LGS | Configurable threshold | Suspend threshold |
| Objectives | Progressive unlock | N/A |
| Constraint plugins | Plugin architecture | Built-in limits |
