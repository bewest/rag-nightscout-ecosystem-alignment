# Insulin Curves Deep Dive

This document provides a comprehensive cross-system analysis of insulin activity curves used by AID (Automated Insulin Delivery) systems. Understanding insulin curves is fundamental to IOB (Insulin on Board) calculations and prediction accuracy.

---

## Executive Summary

**Key Finding**: All major AID systems (Loop, oref0, AAPS, Trio) share the **same exponential insulin model formula**. oref0 explicitly credits Loop as the source. However, IOB values are **not directly comparable** without accounting for:

- **Delay offset**: Loop includes a 10-minute delay before insulin activity; oref0/AAPS/Trio assume immediate onset
- **Peak time differences**: Same-named presets use different peaks (e.g., AAPS Lyumjev = 45 min, Loop Lyumjev = 55 min)

**Notable Exception**: xDrip+ uses a **different linear trapezoid model** with support for multiple insulin types including long-acting insulins not modeled by AID systems.

---

## Mathematical Models

### 1. Exponential Model (Loop/oref0/AAPS/Trio)

The exponential model provides a realistic insulin activity curve based on pharmacokinetic studies. This is the **recommended model** for all modern AID systems.

#### Source Attribution

```javascript
// oref0:lib/iob/calculate.js#L125-L129
// Formula source: https://github.com/LoopKit/Loop/issues/388#issuecomment-317938473
// Mapping of original source variable names to those used here:
//   td = end (DIA in minutes)
//   tp = peak (time to peak in minutes)
//   t  = minsAgo (time since dose)
```

This is significant: **oref0, AAPS, Trio, and Loop all use the same exponential insulin model formula**. However, direct IOB comparison requires accounting for:
1. **Delay parameter**: Loop includes a 10-minute delay before activity starts; oref0/AAPS/Trio do not
2. **Peak times differ**: e.g., AAPS Lyumjev = 45 min, Loop Lyumjev = 55 min

#### Formula

Given:
- `t` = time since dose (minutes)
- `tp` = time to peak activity (minutes)
- `td` = Duration of Insulin Action / DIA (minutes)

**Derived Parameters:**
```
τ (tau) = tp × (1 - tp/td) / (1 - 2×tp/td)    // Time constant of exponential decay
a = 2 × τ / td                                  // Rise time factor
S = 1 / (1 - a + (1 + a) × e^(-td/τ))          // Auxiliary scale factor
```

**Activity (rate of insulin action):**
```
activity = dose × (S / τ²) × t × (1 - t/td) × e^(-t/τ)
```

**IOB (remaining insulin):**
```
iob = dose × (1 - S × (1-a) × ((t²/(τ×td×(1-a)) - t/τ - 1) × e^(-t/τ) + 1))
```

#### Implementation References

| System | File | Language |
|--------|------|----------|
| oref0 | `lib/iob/calculate.js#L83-L143` | JavaScript |
| AAPS | `aaps:plugins/insulin/src/main/kotlin/app/aaps/plugins/insulin/InsulinOrefBasePlugin.kt` | Kotlin |
| Loop | `LoopKit/LoopKit/Insulin/ExponentialInsulinModel.swift` | Swift |
| Trio | `trio-oref/lib/iob/index.js` | JavaScript (via oref0) |

#### Curve Shape

```
Activity
    ^
    |       _.--._
    |     .'      '.
    |    /          \
    |   /            `.
    |  /               `-.
    | /                   `--.___
    |/____________________________ > Time
    0     peak        DIA
```

---

### 2. Bilinear Model (oref0 Legacy)

The bilinear model uses a triangular insulin action curve. This is a **legacy model** maintained for backwards compatibility.

**Source**: `oref0:lib/iob/calculate.js#L36-L80`

#### Fixed Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `default_dia` | 3.0 hours | Reference DIA for scaling |
| `peak` | 75 minutes | Time to peak activity |
| `end` | 180 minutes | Duration of action |

#### Formula

```javascript
// Scale time based on DIA ratio
var timeScalar = default_dia / dia;
var scaled_minsAgo = timeScalar * minsAgo;

// Activity peak height (area under curve = 1)
var activityPeak = 2 / (dia * 60);  // height = 2/base for unit area triangle
var slopeUp = activityPeak / peak;
var slopeDown = -1 * (activityPeak / (end - peak));

if (scaled_minsAgo < peak) {
    // Rising phase
    activityContrib = insulin * (slopeUp * scaled_minsAgo);
    iobContrib = insulin * ((-0.001852*x1*x1) + (0.001852*x1) + 1.0);
} else if (scaled_minsAgo < end) {
    // Falling phase  
    activityContrib = insulin * (activityPeak + (slopeDown * minsPastPeak));
    iobContrib = insulin * ((0.001323*x2*x2) + (-0.054233*x2) + 0.55556);
}
```

#### Curve Shape

```
Activity
    ^
    |      /\
    |     /  \
    |    /    \
    |   /      \
    |  /        \
    | /          \
    |/____________\______> Time
    0    75min   180min
         peak     end
```

---

### 3. Linear Trapezoid Model (xDrip+)

xDrip+ uses a fundamentally different model that supports multiple insulin types including long-acting insulins.

**Source**: `xdrip:app/src/main/java/com/eveningoutpost/dexdrip/insulin/LinearTrapezoidInsulin.java`

#### Parameters

| Parameter | Description |
|-----------|-------------|
| `onset` | Time until insulin starts acting (minutes) |
| `peak` | Time to peak activity (minutes) |
| `duration` | Total duration of action (minutes) |

#### Formula

```java
public double calculateIOB(long timeMs) {
    double minutes = timeMs / 60000.0;
    
    if (minutes <= 0) return 1.0;
    if (minutes >= duration) return 0.0;
    
    // Linear decay after peak
    if (minutes >= peak) {
        return (duration - minutes) / (duration - peak);
    }
    
    // Full IOB before peak (simplified)
    return 1.0;
}

public double calculateActivity(long timeMs) {
    double minutes = timeMs / 60000.0;
    
    if (minutes <= onset) return 0.0;
    if (minutes >= duration) return 0.0;
    
    // Ramp up to peak
    if (minutes >= onset && minutes <= peak) {
        return (minutes - onset) / (peak - onset);
    }
    
    // Decay from peak
    return (duration - minutes) / (duration - peak);
}
```

---

## Cross-System Insulin Type Comparison

### Rapid-Acting Insulins (AID Systems)

| System | Insulin Type | Peak (min) | Delay (min) | DIA | Insulins |
|--------|-------------|------------|-------------|-----|----------|
| **Loop** | `rapidActingAdult` | 75 | 10 | 6 hr | Humalog, NovoRapid, Apidra |
| **Loop** | `rapidActingChild` | 65 | 10 | 6 hr | Pediatric settings |
| **oref0** | `rapid-acting` | 75 (default) | 0 | 5+ hr | Humalog, NovoRapid, Apidra |
| **AAPS** | Rapid-Acting Oref | 75 | 0 | 5+ hr | Port of oref0 |
| **Trio** | `rapid-acting` | 75 | 0 | Profile | Via oref0 |

**Note on Delay Parameter**: Loop's exponential model includes a 10-minute "delay" before insulin activity begins. oref0/AAPS/Trio assume immediate activity onset (delay = 0). This means even with identical peak/DIA settings, Loop IOB curves are time-shifted by 10 minutes relative to oref0-based systems.

### Ultra-Rapid Insulins (AID Systems)

| System | Insulin Type | Peak (min) | Delay (min) | DIA | Insulins |
|--------|-------------|------------|-------------|-----|----------|
| **Loop** | `fiasp` | 55 | 10 | 6 hr | Fiasp |
| **Loop** | `lyumjev` | 55 | 10 | 6 hr | Lyumjev |
| **Loop** | `afrezza` | 29 | 10 | 5 hr | Inhaled insulin |
| **oref0** | `ultra-rapid` | 55 (default) | 0 | 5+ hr | Fiasp, Lyumjev |
| **AAPS** | Ultra-Rapid Oref | 55 | 0 | 5+ hr | Fiasp |
| **AAPS** | Lyumjev | 45 | 0 | 5+ hr | Lyumjev-specific |
| **AAPS** | Free Peak | Configurable | 0 | 5+ hr | User-defined |
| **Trio** | `ultra-rapid` | 55 | 0 | Profile | Via oref0 |

**Important Note**: Loop's presets include a 10-minute **delay** parameter before insulin activity begins, while oref0/AAPS/Trio assume activity starts immediately. This means Loop and oref0 curves are offset by 10 minutes even though they use the same exponential formula. Additionally, AAPS Lyumjev uses **45 min peak** while Loop Lyumjev uses **55 min peak** - these are NOT equivalent despite having the same name.

### xDrip+ Insulin Profiles

xDrip+ supports a broader range of insulin types via JSON configuration:

**Source**: `xdrip:app/src/main/res/raw/insulin_profiles.json`

| Insulin | Type | Onset | Peak | Duration |
|---------|------|-------|------|----------|
| **FIASP** | Ultra-fast | 2 min | 45 min | 300 min (5 hr) |
| **Afrezza** | Inhaled | 5 min | 50 min | 150 min (2.5 hr) |
| **Apidra** | Ultra-fast | 10 min | 60-180 min | 300 min (5 hr) |
| **NovoRapid** | Rapid | 10 min | 75 min | 180 min (3 hr) |
| **Humalog** | Rapid | 10 min | 75 min | 180 min (3 hr) |
| **Lispro** | Rapid | 15 min | 90 min | 210 min (3.5 hr) |
| **Actrapid** | Short | 30 min | 60-240 min | 480 min (8 hr) |
| **Insulatard** | NPH | 60 min | 120-720 min | 1440 min (24 hr) |
| **Lantus** | Long | 60 min | 420-1200 min | 2160 min (36 hr) |
| **Levemir** | Long | 60 min | 180-840 min | 1500 min (25 hr) |
| **Basaglar** | Long | 60 min | 480-1140 min | 1440 min (24 hr) |
| **Tresiba** | Ultra-long | 90 min | 120-2460 min | 2520 min (42 hr) |
| **Toujeo** | Long | 180 min | 480 min | 2160 min (36 hr) |

**Note**: xDrip+ can track multi-insulin treatments (e.g., NovoRapid + Lantus in same entry) via `insulinJSON` field. See [xDrip+ Insulin Management](../../mapping/xdrip-android/insulin-management.md).

---

## DIA (Duration of Insulin Action) Constraints

### System-Specific Minimums

| System | Minimum DIA | Default DIA | Enforcement |
|--------|-------------|-------------|-------------|
| **Loop** | Fixed per model | 5-6 hr | Hardcoded in model presets |
| **oref0 (bilinear)** | 3 hours | 3 hours | Soft clamp in code |
| **oref0 (exponential)** | 5 hours | 5 hours | `requireLongDia` flag |
| **AAPS** | 5 hours | 5 hours | `hardLimits.minDia()` |
| **Trio** | 5 hours | Profile | Via oref0 |
| **xDrip+** | None | Per profile | User configurable |

### oref0 DIA Enforcement

**Source**: `oref0:lib/iob/total.js#L24-L27, L60-L63`

```javascript
// Force minimum DIA of 3h (bilinear)
if (dia < 3) {
    dia = 3;
}

// Force minimum of 5h DIA for exponential curves
if (defaults.requireLongDia && dia < 5) {
    dia = 5;
}
```

### AAPS DIA Enforcement

**Source**: `aaps:plugins/insulin/src/main/kotlin/app/aaps/plugins/insulin/InsulinOrefBasePlugin.kt`

```kotlin
override val dia: Double
    get(): Double {
        val dia = userDefinedDia
        return if (dia >= hardLimits.minDia()) {
            dia
        } else {
            sendShortDiaNotification(dia)
            hardLimits.minDia()  // Returns 5.0
        }
    }
```

---

## Custom Peak Time Configuration

### oref0 Peak Ranges

**Source**: `oref0:lib/iob/calculate.js#L86-L116`

| Curve Type | Default Peak | Minimum | Maximum |
|------------|-------------|---------|---------|
| `rapid-acting` | 75 min | 50 min | 120 min |
| `ultra-rapid` | 55 min | 35 min | 100 min |

Configuration via profile:
```json
{
  "curve": "rapid-acting",
  "useCustomPeakTime": true,
  "insulinPeakTime": 90
}
```

### AAPS Free Peak

**Source**: `aaps:plugins/insulin/src/main/kotlin/app/aaps/plugins/insulin/InsulinOrefFreePeakPlugin.kt`

```kotlin
class InsulinOrefFreePeakPlugin : InsulinOrefBasePlugin {
    override val peak: Int
        get() = preferences.get(IntKey.InsulinOrefPeak)  // User-configurable
}
```

---

## IOB Components and Aggregation

### IOB Structure

All oref0-based systems track multiple IOB components:

| Component | Description | Use Case |
|-----------|-------------|----------|
| `iob` | Total IOB (basaliob + bolusiob) | Primary constraint |
| `basaliob` | IOB from temp basals | Can be negative |
| `bolusiob` | IOB from boluses | Always positive |
| `activity` | Current insulin activity (U/min) | BGI calculation |
| `iobWithZeroTemp` | IOB if TBR set to 0 now | ZT prediction |
| `bolussnooze` | Recent bolus IOB | Stacking prevention |

### Aggregation Logic

**Source**: `oref0:lib/iob/total.js#L67-L92`

```javascript
treatments.forEach(function(treatment) {
    if (treatment.date <= now) {
        var dia_ago = now - dia * 60 * 60 * 1000;
        if (treatment.date > dia_ago) {
            var tIOB = iobCalc(treatment, time, curve, dia, peak, profile);
            if (tIOB.iobContrib) { iob += tIOB.iobContrib; }
            if (tIOB.activityContrib) { activity += tIOB.activityContrib; }
            
            // Separate basal vs bolus IOB
            if (treatment.insulin < 0.1) {
                basaliob += tIOB.iobContrib;
                netbasalinsulin += treatment.insulin;
            } else {
                bolusiob += tIOB.iobContrib;
                bolusinsulin += treatment.insulin;
            }
        }
    }
});
```

---

## Blood Glucose Impact (BGI)

BGI represents the expected glucose change from insulin activity over a 5-minute period.

### Formula

```
BGI = -activity × ISF × 5
```

Where:
- `activity` = current insulin activity (U/min)
- `ISF` = insulin sensitivity factor (mg/dL per U)
- `5` = 5-minute interval

### Example

If `activity = 0.02 U/min` and `ISF = 50 mg/dL/U`:
```
BGI = -0.02 × 50 × 5 = -5 mg/dL
```
BG expected to drop 5 mg/dL in the next 5 minutes.

### Implementation

**oref0**: `lib/determine-basal/determine-basal.js#L398`
```javascript
var bgi = round((-iob_data.activity * sens * 5), 2);
```

**AAPS**: `plugins/aps/src/main/kotlin/.../DetermineBasalSMB.kt`
```kotlin
val bgi = round((-iob_data.activity * sens * 5), 2)
```

---

## Dynamic ISF and Insulin Peak Interaction

AAPS implements Dynamic ISF which adjusts sensitivity based on insulin type:

**Source**: `aaps:plugins/aps/src/main/kotlin/app/aaps/plugins/aps/openAPSSMB/OpenAPSSMBPlugin.kt`

```kotlin
// In calculateRawDynIsf()
dynIsfResult.insulinDivisor = when {
    insulin.peak > 65 -> 55   // Rapid peak: 75
    insulin.peak > 50 -> 65   // Ultra-rapid peak: 55
    else              -> 75   // Lyumjev peak: 45
}

// Variable sensitivity formula
variableSensitivity = 1800 / (tdd * ln((glucose / insulinDivisor) + 1))
```

This creates a coupling between insulin model selection and sensitivity calculation in AAPS that doesn't exist in other systems.

---

## Nightscout Representation

### IOB in devicestatus

**Loop format**:
```json
{
  "loop": {
    "iob": {
      "timestamp": "2026-01-17T12:00:00Z",
      "iob": 2.35
    }
  }
}
```

**oref0/AAPS/Trio format**:
```json
{
  "openaps": {
    "iob": {
      "iob": 2.5,
      "basaliob": 0.8,
      "bolussnooze": 1.2,
      "activity": 0.035,
      "time": "2026-01-17T12:00:00Z",
      "lastBolusTime": 1705408800000
    }
  }
}
```

### Missing Metadata

Nightscout does not capture:
- Which insulin curve type was used for the calculation
- Peak time parameter (default vs custom)
- DIA setting at time of calculation
- Insulin brand/type for dosing decisions

See [GAP-INS-001](#related-gaps) for details.

---

## Cross-System Comparison Summary

| Aspect | Loop | oref0 | AAPS | Trio | xDrip+ |
|--------|------|-------|------|------|--------|
| **Primary Model** | Exponential | Exponential | Exponential | Exponential | Linear Trapezoid |
| **Legacy Model** | N/A | Bilinear | N/A | Bilinear | N/A |
| **Formula Source** | Original | Loop | oref0 | oref0 | Independent |
| **DIA Configurable** | Fixed per preset | Yes (min 5h) | Yes (min 5h) | Yes (min 5h) | Yes |
| **Peak Configurable** | Per preset | Yes (ranges) | Yes (free peak) | Yes (via oref0) | Per profile |
| **Multi-Insulin** | No | No | No | No | Yes |
| **Long-Acting Support** | No | No | No | No | Yes (13+ types) |
| **Concentration Support** | N/A | N/A | U100-U200 | N/A | U100-U500 |

---

## Related Gaps

- **GAP-INS-001**: Insulin model metadata not synced to Nightscout
- **GAP-INS-002**: No standardized multi-insulin representation
- **GAP-INS-003**: Peak time customization not captured in treatments
- **GAP-INS-004**: xDrip+ linear trapezoid model incompatible with AID exponential

---

## Conformance Assertions

See [`conformance/assertions/insulin-model.yaml`](../../conformance/assertions/insulin-model.yaml) for 18 test assertions covering:

| Requirement | Description | Assertions |
|-------------|-------------|------------|
| REQ-INS-001 | Exponential formula consistency | 6 |
| REQ-INS-004 | Activity calculation for BGI | 6 |
| REQ-INS-005 | Insulin model metadata sync | 6 |

---

## Source File References

| System | Key Files |
|--------|-----------|
| **oref0** | `lib/iob/calculate.js`, `lib/iob/total.js`, `lib/iob/history.js` |
| **AAPS** | `plugins/insulin/src/main/kotlin/.../InsulinOref*.kt` |
| **Loop** | `LoopKit/LoopKit/Insulin/ExponentialInsulinModel.swift`, `InsulinMath.swift` |
| **Trio** | `trio-oref/lib/iob/`, `Trio/Sources/Models/Preferences.swift` |
| **xDrip+** | `insulin/LinearTrapezoidInsulin.java`, `res/raw/insulin_profiles.json`, `models/Iob.java` |

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-02-01 | Agent | Added conformance assertions section (18 assertions) |
| 2026-01-17 | Agent | Initial insulin curves deep dive from source analysis |
