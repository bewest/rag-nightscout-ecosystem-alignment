# AAPS Insulin Math

This document describes how AAPS calculates Insulin on Board (IOB) and models insulin activity using oref-based curves.

## Overview

AAPS implements insulin models based on the oref0 biexponential curves. These models define:
- **IOB** - Remaining active insulin
- **Activity** - Current insulin effect rate
- **DIA** - Duration of Insulin Action

## Insulin Model Base

```kotlin
// aaps:plugins/insulin/src/main/kotlin/app/aaps/plugins/insulin/InsulinOrefBasePlugin.kt
abstract class InsulinOrefBasePlugin(
    // ... dependencies
) : PluginBase(...), Insulin {

    override fun iobCalcForTreatment(bolus: BS, time: Long, dia: Double): Iob {
        val result = Iob()
        if (bolus.amount != 0.0) {
            val bolusTime = bolus.timestamp
            val t = (time - bolusTime) / 1000.0 / 60.0  // Minutes since bolus
            val td = dia * 60  // DIA in minutes
            val tp = peak.toDouble()  // Peak time in minutes
            
            // Force IOB to 0 after DIA
            if (t < td) {
                val tau = tp * (1 - tp / td) / (1 - 2 * tp / td)
                val a = 2 * tau / td
                val s = 1 / (1 - a + (1 + a) * exp(-td / tau))
                
                // Activity contribution
                result.activityContrib = bolus.amount * (s / tau.pow(2.0)) * t * 
                    (1 - t / td) * exp(-t / tau)
                
                // IOB contribution
                result.iobContrib = bolus.amount * (1 - s * (1 - a) * 
                    ((t.pow(2.0) / (tau * td * (1 - a)) - t / tau - 1) * 
                    exp(-t / tau) + 1))
            }
        }
        return result
    }
}
```

## IOB Calculation Formula

The biexponential model uses these parameters:

| Symbol | Meaning |
|--------|---------|
| t | Time since bolus (minutes) |
| td | Total DIA (minutes) |
| tp | Time to peak (minutes) |
| tau | Curve shape parameter |
| a | Curve area factor |
| s | Scaling factor |

### Derived Parameters

```kotlin
val tau = tp * (1 - tp / td) / (1 - 2 * tp / td)
val a = 2 * tau / td
val s = 1 / (1 - a + (1 + a) * exp(-td / tau))
```

### Activity Calculation

Activity represents the current rate of glucose lowering:

```kotlin
activity = amount * (s / tau²) * t * (1 - t/td) * exp(-t/tau)
```

### IOB Calculation

```kotlin
iob = amount * (1 - s * (1-a) * ((t²/(tau*td*(1-a)) - t/tau - 1) * exp(-t/tau) + 1))
```

## Insulin Types

AAPS provides several insulin model plugins:

### Rapid-Acting (Oref)

```kotlin
// aaps:plugins/insulin/src/main/kotlin/app/aaps/plugins/insulin/InsulinOrefRapidActingPlugin.kt
class InsulinOrefRapidActingPlugin : InsulinOrefBasePlugin {
    override val peak: Int = 75  // Minutes to peak
}
```

### Ultra-Rapid Acting (Oref)

```kotlin
// aaps:plugins/insulin/src/main/kotlin/app/aaps/plugins/insulin/InsulinOrefUltraRapidActingPlugin.kt
class InsulinOrefUltraRapidActingPlugin : InsulinOrefBasePlugin {
    override val peak: Int = 55  // Minutes to peak
}
```

### Lyumjev

```kotlin
// aaps:plugins/insulin/src/main/kotlin/app/aaps/plugins/insulin/InsulinLyumjevPlugin.kt
class InsulinLyumjevPlugin : InsulinOrefBasePlugin {
    override val peak: Int = 45  // Minutes to peak
}
```

### Free Peak (User-Defined)

```kotlin
// aaps:plugins/insulin/src/main/kotlin/app/aaps/plugins/insulin/InsulinOrefFreePeakPlugin.kt
class InsulinOrefFreePeakPlugin : InsulinOrefBasePlugin {
    override val peak: Int
        get() = preferences.get(IntKey.InsulinOrefPeak)  // User-configurable
}
```

## Insulin Model Summary

| Model | Peak (min) | Typical DIA | Use Case |
|-------|------------|-------------|----------|
| Rapid-Acting | 75 | 5-6 hours | NovoRapid, Humalog, Apidra |
| Ultra-Rapid | 55 | 5 hours | Fiasp, NovoRapid U200 |
| Lyumjev | 45 | 4-5 hours | Lyumjev (Lispro-aabc) |
| Free Peak | Configurable | Configurable | Custom tuning |

## DIA Enforcement

AAPS enforces minimum DIA via hard limits:

```kotlin
override val dia: Double
    get(): Double {
        val dia = userDefinedDia
        return if (dia >= hardLimits.minDia()) {
            dia
        } else {
            sendShortDiaNotification(dia)
            hardLimits.minDia()
        }
    }
```

**Minimum DIA**: 5 hours (hardcoded in `HardLimits`)

## Dynamic ISF and Insulin Peak

Dynamic ISF adjusts the insulin divisor based on insulin type:

```kotlin
// In OpenAPSSMBPlugin.calculateRawDynIsf()
dynIsfResult.insulinDivisor = when {
    insulin.peak > 65 -> 55   // Rapid peak: 75
    insulin.peak > 50 -> 65   // Ultra-rapid peak: 55
    else              -> 75   // Lyumjev peak: 45
}
```

This affects the variable sensitivity formula:
```kotlin
variableSensitivity = 1800 / (tdd * ln((glucose / insulinDivisor) + 1))
```

## IOB Array Generation

For predictions, AAPS generates IOB projections:

```kotlin
// aaps:core/interfaces/src/main/kotlin/app/aaps/core/interfaces/iob/IobCobCalculator.kt
fun calculateIobArrayForSMB(
    autosensResult: AutosensResult,
    exercise_mode: Boolean,
    half_basal_exercise_target: Int,
    isTempTarget: Boolean
): Array<IobTotal>
```

This returns IOB values at future time points (typically 5-minute intervals).

## IobTotal Structure

```kotlin
// aaps:core/interfaces/src/main/kotlin/app/aaps/core/interfaces/aps/IobTotal.kt
data class IobTotal(
    val time: Long,
    var iob: Double = 0.0,           // Total IOB
    var basaliob: Double = 0.0,      // IOB from basals only
    var bolussnooze: Double = 0.0,   // IOB from recent boluses (for bolus snooze)
    var activity: Double = 0.0,      // Current activity
    var lastBolusTime: Long = 0,     // Last bolus timestamp
    var iobWithZeroTemp: IobTotal? = null  // IOB if temp basals were zero
)
```

## Bolus IOB Calculation

For each bolus, IOB is calculated and summed:

```kotlin
// Pseudo-code flow
var totalIob = IobTotal(time = now)

for (bolus in bolusHistory) {
    val iobFromBolus = insulin.iobCalcForTreatment(bolus, now, dia)
    totalIob.iob += iobFromBolus.iobContrib
    totalIob.activity += iobFromBolus.activityContrib
}

for (tempBasal in tempBasalHistory) {
    val iobFromTempBasal = calculateTempBasalIob(tempBasal, now)
    totalIob.iob += iobFromTempBasal.iobContrib
    totalIob.basaliob += iobFromTempBasal.iobContrib
    totalIob.activity += iobFromTempBasal.activityContrib
}
```

## Temp Basal IOB

Temp basals are converted to equivalent boluses for IOB calculation:

1. Calculate actual delivered insulin for each 5-min segment
2. Compare to scheduled basal
3. Calculate IOB contribution using same biexponential curve

## BGI (Blood Glucose Impact)

BGI represents how much BG should change based on insulin activity:

```kotlin
// In DetermineBasalSMB.determine_basal()
val bgi = round((-iob_data.activity * sens * 5), 2)
```

Where:
- `activity` = current insulin activity rate
- `sens` = insulin sensitivity factor (mg/dL per U)
- `5` = 5-minute period

## Comparison with Loop

| Aspect | AAPS | Loop |
|--------|------|------|
| Model | Biexponential (oref) | Exponential decay |
| Peak Parameter | Explicit peak time | Model-specific curves |
| DIA | User-configurable (min 5h) | Model-determined |
| Models | Rapid, Ultra-Rapid, Lyumjev, Free | Walsh, Rapid, Fiasp, Afrezza |

## Insulin Configuration Storage

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/embedments/InsulinConfiguration.kt
data class InsulinConfiguration(
    val insulinLabel: String,         // Display name
    val insulinEndTime: Long,         // DIA in ms
    val insulinPeakTime: Long         // Peak time in ms
)
```

This is embedded in bolus and profile switch entities for historical accuracy.

## Key Insights

1. **All insulin types use same formula** - Only peak time differs
2. **DIA affects curve shape** - Longer DIA = slower decay
3. **Activity peaks then decays** - Maximum around peak time
4. **IOB monotonically decreases** - After initial bolus
5. **Hard minimum DIA** - 5 hours prevents unsafe configurations
