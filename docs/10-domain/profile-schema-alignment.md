# Profile Schema Alignment

**Date:** 2026-01-29  
**Status:** Complete  
**Type:** Cross-controller analysis

## Overview

This document compares how therapy settings (profiles) are structured across Loop, AAPS, Trio, and Nightscout. Profiles contain the core therapy parameters that AID systems use for insulin dosing decisions.

## Core Profile Fields

### Field Mapping Matrix

| Concept | Nightscout | Loop | AAPS | Trio |
|---------|------------|------|------|------|
| **Basal rates** | `basal[]` | `basalRateSchedule` | `basalBlocks` | Uses LoopKit |
| **ISF** | `sens[]` | `insulinSensitivitySchedule` | `isfBlocks` | Uses LoopKit |
| **Carb ratio** | `carbratio[]` | `carbRatioSchedule` | `icBlocks` | Uses LoopKit |
| **Target low** | `target_low[]` | `glucoseTargetRangeSchedule.lowerBound` | `targetBlocks.lowTarget` | Uses LoopKit |
| **Target high** | `target_high[]` | `glucoseTargetRangeSchedule.upperBound` | `targetBlocks.highTarget` | Uses LoopKit |
| **DIA** | `dia` | `defaultRapidActingModel` | `dia` | oref1 model |
| **Timezone** | `timezone` | Schedule timeZone | `timeZone` | Schedule timeZone |
| **Units** | `units` | HKUnit | `glucoseUnit` | HKUnit |

---

## Nightscout Profile Schema

**Source:** `externals/cgm-remote-monitor/lib/profile/profileeditor.js:30-70`

```javascript
{
  "dia": 3,                    // Duration of Insulin Action (hours)
  "carbratio": [               // Carb ratio schedule
    { "time": "00:00", "value": 10 }
  ],
  "sens": [                    // Insulin Sensitivity Factor
    { "time": "00:00", "value": 50 }
  ],
  "basal": [                   // Basal rate schedule
    { "time": "00:00", "value": 1.0 }
  ],
  "target_low": [              // Target range low bound
    { "time": "00:00", "value": 100 }
  ],
  "target_high": [             // Target range high bound
    { "time": "00:00", "value": 120 }
  ],
  "timezone": "UTC",           // Profile timezone
  "units": "mg/dl"             // Glucose units
}
```

### Key Characteristics
- **Time-based arrays** - Each setting has `time` + `value` pairs
- **Time format** - 24-hour string "HH:MM"
- **Single DIA value** - Not scheduled
- **Separate target arrays** - `target_low` and `target_high` must have matching lengths

---

## Loop Profile Schema (TherapySettings)

**Source:** `externals/LoopWorkspace/LoopKit/LoopKit/TherapySettings.swift:11-69`

```swift
public struct TherapySettings: Equatable {
    public var glucoseTargetRangeSchedule: GlucoseRangeSchedule?
    public var correctionRangeOverrides: CorrectionRangeOverrides?
    public var overridePresets: [TemporaryScheduleOverridePreset]?
    public var maximumBasalRatePerHour: Double?
    public var maximumBolus: Double?
    public var suspendThreshold: GlucoseThreshold?
    public var insulinSensitivitySchedule: InsulinSensitivitySchedule?
    public var carbRatioSchedule: CarbRatioSchedule?
    public var basalRateSchedule: BasalRateSchedule?
    public var defaultRapidActingModel: ExponentialInsulinModelPreset?
}
```

### Key Characteristics
- **Schedule types** - Dedicated schedule classes (e.g., `InsulinSensitivitySchedule`)
- **Range schedule** - `GlucoseRangeSchedule` holds both low and high as `DoubleRange`
- **Override presets** - Built-in override support
- **Suspend threshold** - Explicit safety limit
- **Insulin model** - Preset-based rather than raw DIA

### Loop-Specific Fields (not in Nightscout)
- `maximumBasalRatePerHour` - Safety limit
- `maximumBolus` - Bolus cap
- `suspendThreshold` - Low glucose suspend
- `correctionRangeOverrides` - Pre-meal and workout targets
- `overridePresets` - Named override configurations

---

## AAPS Profile Schema (PureProfile)

**Source:** `externals/AndroidAPS/core/interfaces/src/main/kotlin/app/aaps/core/interfaces/profile/PureProfile.kt:9-18`

```kotlin
class PureProfile(
    var jsonObject: JSONObject,       // Source JSON (Nightscout format)
    var basalBlocks: List<Block>,     // Basal schedule
    var isfBlocks: List<Block>,       // ISF schedule
    var icBlocks: List<Block>,        // I:C schedule (carb ratio)
    var targetBlocks: List<TargetBlock>, // Target range schedule
    var dia: Double,                  // Duration of Insulin Action
    var glucoseUnit: GlucoseUnit,     // mg/dL or mmol/L
    var timeZone: TimeZone            // Profile timezone
)
```

### AAPS Profile Interface

**Source:** `externals/AndroidAPS/core/interfaces/src/main/kotlin/app/aaps/core/interfaces/profile/Profile.kt:14-133`

```kotlin
interface Profile {
    val units: GlucoseUnit
    val dia: Double
    val percentage: Int      // Profile percentage (for switching)
    val timeshift: Int       // Time shift (for switching)
    
    fun getBasal(): Double
    fun getBasal(timestamp: Long): Double
    fun getIc(): Double
    fun getIc(timestamp: Long): Double
    fun getIsfMgdl(caller: String): Double
    fun getTargetMgdl(): Double
    fun getTargetLowMgdl(): Double
    fun getTargetHighMgdl(): Double
    
    fun toPureNsJson(dateUtil: DateUtil): JSONObject
    fun getBasalValues(): Array<ProfileValue>
    fun getIcsValues(): Array<ProfileValue>
    fun getIsfsMgdlValues(): Array<ProfileValue>
}
```

### Key Characteristics
- **Block-based schedules** - Uses `Block` and `TargetBlock` classes
- **Nightscout JSON source** - Stores original NS JSON for round-trip
- **Percentage/timeshift** - Profile switching features
- **Autosens integration** - `sensitivityRatio` affects ISF dynamically
- **Dynamic ISF option** - `hasDynamicIsf` for algorithm variants

### AAPS-Specific Features (not in Nightscout)
- `percentage` - Scale entire profile (50-200%)
- `timeshift` - Shift schedule by hours
- `sensitivityRatio` - Autosens multiplier
- Profile switching with copy-on-write

---

## Trio Profile Schema

**Uses LoopKit** - Trio inherits from LoopKit's `TherapySettings` structure.

**Source:** `externals/Trio/` (LoopKit submodule)

Trio passes profile to oref1 algorithm, which expects:

```json
{
  "min_5m_carbimpact": 8,
  "dia": 6,
  "basalprofile": [...],
  "isfProfile": {...},
  "carb_ratio": 10,
  "autosens_max": 1.2,
  "autosens_min": 0.7
}
```

### Key Characteristics
- **LoopKit types internally** - Same schedule structures as Loop
- **oref1 format for algorithm** - Converts to oref1 expected format
- **Extended settings** - Autosens bounds, SMB settings

---

## Schema Differences Summary

### Time Representation

| System | Format | Example |
|--------|--------|---------|
| Nightscout | String "HH:MM" | `"time": "08:00"` |
| Loop | Seconds from midnight | `timeAsSeconds: 28800` |
| AAPS | Seconds from midnight | `timeAsSeconds: 28800` |

### Target Range Representation

| System | Format |
|--------|--------|
| Nightscout | Separate `target_low[]` and `target_high[]` arrays |
| Loop | Combined `GlucoseRangeSchedule` with `DoubleRange` |
| AAPS | Combined `TargetBlock` with `lowTarget` and `highTarget` |

### DIA Representation

| System | Format | Default |
|--------|--------|---------|
| Nightscout | Scalar hours | 3.0 |
| Loop | Insulin model preset | Rapid acting curves |
| AAPS | Scalar hours | 5.0 |
| Trio/oref1 | Scalar hours | 6.0 |

---

## Gaps Identified

### GAP-PROF-001: Time Format Incompatibility

**Description:** Nightscout uses string "HH:MM" format while Loop/AAPS use integer seconds from midnight.

**Source:** 
- `externals/cgm-remote-monitor/lib/profile/profileeditor.js:32`
- `externals/AndroidAPS/core/interfaces/src/main/kotlin/app/aaps/core/interfaces/profile/Profile.kt:133`

**Impact:** Profile sync requires format conversion; potential off-by-one errors at midnight boundary.

**Remediation:** Standardize on seconds from midnight with conversion utilities.

### GAP-PROF-002: Missing Safety Limits in Nightscout

**Description:** Nightscout profile lacks `maximumBasalRatePerHour`, `maximumBolus`, and `suspendThreshold` found in Loop.

**Source:** `externals/LoopWorkspace/LoopKit/LoopKit/TherapySettings.swift:19-23`

**Impact:** Safety limits not portable between systems; each controller must manage locally.

**Remediation:** Add optional safety limit fields to Nightscout profile schema.

### GAP-PROF-003: No Override Presets in Nightscout

**Description:** Loop's `overridePresets` and `correctionRangeOverrides` have no Nightscout equivalent.

**Source:** `externals/LoopWorkspace/LoopKit/LoopKit/TherapySettings.swift:15-17`

**Impact:** Override configurations not synced; must be configured separately on each device.

**Remediation:** Add override preset array to Nightscout profile collection.

### GAP-PROF-004: Profile Switching Features (AAPS-only)

**Description:** AAPS supports `percentage` and `timeshift` for profile switching; not in Loop or Nightscout.

**Source:** `externals/AndroidAPS/core/interfaces/src/main/kotlin/app/aaps/core/interfaces/profile/Profile.kt:36-41`

**Impact:** Profile switch events sync as treatments but actual percentages not in profile.

**Remediation:** Document as AAPS-specific feature; consider adding to Nightscout profile.

### GAP-PROF-005: DIA vs Insulin Model Mismatch

**Description:** Nightscout/AAPS use scalar DIA hours while Loop uses exponential insulin model presets.

**Source:**
- `externals/cgm-remote-monitor/lib/profile/profileeditor.js:30`
- `externals/LoopWorkspace/LoopKit/LoopKit/TherapySettings.swift:31`

**Impact:** Loop's curve-based insulin action doesn't map to simple DIA value.

**Remediation:** Define mapping between Loop model presets and equivalent DIA values.

---

## Nightscout Profile Sync

### Loop → Nightscout

**Source:** `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/Extensions/ProfileSet.swift:35-80`

Loop converts `TherapySettings` to Nightscout profile format:
- `insulinSensitivitySchedule` → `sens[]`
- `carbRatioSchedule` → `carbratio[]`
- `basalRateSchedule` → `basal[]`
- `glucoseTargetRangeSchedule` → `target_low[]` + `target_high[]`

### AAPS → Nightscout

**Source:** `externals/AndroidAPS/core/interfaces/src/main/kotlin/app/aaps/core/interfaces/profile/Profile.kt:123`

AAPS uses `toPureNsJson()` to serialize profile to Nightscout format.

### Trio → Nightscout

Trio uses LoopKit conversion via NightscoutService (same as Loop).

---

## Recommendations

### For Nightscout

1. **Add safety limits** - Optional fields for maxBasal, maxBolus, suspendThreshold
2. **Add override presets** - Array of named override configurations
3. **Standardize time format** - Document seconds-from-midnight as canonical

### For Controllers

1. **Document conversions** - Clear mapping from internal to Nightscout format
2. **Preserve source JSON** - AAPS pattern of keeping original NS JSON
3. **Handle missing fields** - Graceful defaults for optional fields

### For OpenAPI Spec

1. **Profile collection spec** - Add to `aid-profile-2025.yaml`
2. **Document all fields** - Including controller-specific extensions
3. **Annotate x-aid-controllers** - Which fields supported by which systems

---

## Source File References

| Project | File | Key Lines |
|---------|------|-----------|
| Nightscout | `lib/profile/profileeditor.js` | 30-70, 142-150 |
| Loop | `LoopKit/TherapySettings.swift` | 11-69 |
| Loop | `NightscoutServiceKit/Extensions/ProfileSet.swift` | 35-80 |
| AAPS | `core/interfaces/profile/Profile.kt` | 14-133 |
| AAPS | `core/interfaces/profile/PureProfile.kt` | 9-18 |

---

## Related Documents

- `specs/openapi/aid-profile-2025.yaml` - OpenAPI specification
- `mapping/nightscout/profile-fields.md` - Field mapping
- `docs/10-domain/algorithm-comparison-deep-dive.md` - Algorithm differences
