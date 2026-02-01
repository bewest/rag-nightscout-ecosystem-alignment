# Target Range Handling Comparison

> **Status**: Complete  
> **Last Updated**: 2026-01-30  
> **Task**: Compare target glucose range handling across Loop and oref0/AAPS

## Executive Summary

Loop and oref0/AAPS have fundamentally different approaches to target glucose ranges:

| Aspect | Loop | oref0/AAPS |
|--------|------|------------|
| **Structure** | `ClosedRange<HKQuantity>` (min...max) | Separate `min_bg` and `max_bg` fields |
| **Algorithm use** | Correct to range midpoint dynamically | Calculate `target_bg = (min_bg + max_bg) / 2` |
| **Override mechanism** | `GlucoseRangeSchedule.Override` | `temptargetSet` flag with temp target |
| **Sensitivity effect** | No target adjustment | Autosens adjusts targets (sensitivity_raises_target) |

## Loop Target Range Model

### Source Files
- `externals/LoopWorkspace/LoopKit/LoopKit/GlucoseRangeSchedule.swift:57-221`
- `externals/LoopWorkspace/LoopKit/LoopKit/LoopAlgorithm/DoseMath.swift:220-350`
- `externals/LoopWorkspace/LoopKit/LoopKit/CorrectionRangeOverrides.swift:1-50`

### Data Structure

Loop uses `GlucoseRangeSchedule` - a time-varying schedule of glucose ranges:

```swift
// GlucoseRangeSchedule.swift:57
public struct GlucoseRangeSchedule: DailySchedule, Equatable {
    // Time-varying schedule
    var rangeSchedule: DailyQuantitySchedule<DoubleRange>
    
    // Optional override (preMeal, workout)
    public var override: Override?
}
```

Each entry is a `DoubleRange`:
```swift
// GlucoseRangeSchedule.swift:13-20
public struct DoubleRange {
    public let minValue: Double  // Lower bound (e.g., 100 mg/dL)
    public let maxValue: Double  // Upper bound (e.g., 110 mg/dL)
}
```

### Algorithm Usage

Loop corrects to the **dynamic midpoint** of the range, scaling over time:

```swift
// DoseMath.swift:293-297
let targetValue = targetGlucoseValue(
    percentEffectDuration: time / model.effectDuration,
    minValue: suspendThresholdValue,
    maxValue: correctionRange.quantityRange(at: prediction.startDate).averageValue(for: unit)
)
```

The target starts at suspend threshold and rises toward range midpoint:

```swift
// DoseMath.swift:200-214
private func targetGlucoseValue(percentEffectDuration: Double, minValue: Double, maxValue: Double) -> Double {
    let useMinValueUntilPercent = 0.5  // Use minValue for first 50% of effect
    
    guard percentEffectDuration > useMinValueUntilPercent else {
        return minValue
    }
    // Then linearly blend to maxValue
    let slope = (maxValue - minValue) / (1 - useMinValueUntilPercent)
    return minValue + slope * (percentEffectDuration - useMinValueUntilPercent)
}
```

### Override System

Loop has two built-in range overrides:

```swift
// CorrectionRangeOverrides.swift:11-18
public struct CorrectionRangeOverrides {
    public enum Preset: String, CaseIterable {
        case preMeal
        case workout
    }
    public var ranges: [Preset: ClosedRange<HKQuantity>]
}
```

Custom overrides use `TemporaryScheduleOverride`:
```swift
// TemporaryScheduleOverrideSettings.swift:16
public var targetRange: ClosedRange<HKQuantity>? {
    didSet {
        // Applies to entire range schedule
    }
}
```

## oref0/AAPS Target Range Model

### Source Files
- `externals/oref0/lib/determine-basal/determine-basal.js:225-320`
- `externals/AndroidAPS/plugins/aps/src/main/kotlin/app/aaps/plugins/aps/openAPSSMB/DetermineBasalSMB.kt:217-270`

### Data Structure

oref0 uses **three separate values** in the profile:

```javascript
// determine-basal.js:229-243
var target_bg;
var min_bg;
var max_bg;

if (typeof profile.min_bg !== 'undefined') {
    min_bg = profile.min_bg;
}
if (typeof profile.max_bg !== 'undefined') {
    max_bg = profile.max_bg;
}
// Calculate target as simple average
if (typeof profile.min_bg !== 'undefined' && typeof profile.max_bg !== 'undefined') {
    target_bg = (profile.min_bg + profile.max_bg) / 2;
}
```

### Algorithm Usage

oref0 uses `target_bg` directly for correction calculations:

```javascript
// determine-basal.js:31-34
function calculate_expected_delta(target_bg, eventual_bg, bgi) {
    // target_delta is the amount of BG change expected
    var target_delta = target_bg - eventual_bg;
    // ...
}
```

### Temp Target and Sensitivity

oref0 adjusts **both** sensitivity and targets based on temp targets:

```javascript
// determine-basal.js:259-277
if (high_temptarget_raises_sensitivity && profile.temptargetSet && target_bg > normalTarget
    || profile.low_temptarget_lowers_sensitivity && profile.temptargetSet && target_bg < normalTarget) {
    
    var c = halfBasalTarget - normalTarget;
    sensitivityRatio = c / (c + target_bg - normalTarget);
    
    // Limit to autosens bounds
    sensitivityRatio = Math.min(sensitivityRatio, profile.autosens_max);
}
```

oref0 also adjusts targets based on autosens:

```javascript
// determine-basal.js:296-311
if (profile.sensitivity_raises_target && autosens_data.ratio < 1 
    || profile.resistance_lowers_target && autosens_data.ratio > 1) {
    
    // Adjust target based on sensitivity
    min_bg = round((min_bg - 60) / autosens_data.ratio) + 60;
    max_bg = round((max_bg - 60) / autosens_data.ratio) + 60;
    var new_target_bg = round((target_bg - 60) / autosens_data.ratio) + 60;
    
    // Safety: don't allow target_bg below 80
    new_target_bg = Math.max(80, new_target_bg);
    target_bg = new_target_bg;
}
```

### SMB Enable Based on Target

Temp targets enable/disable SMB:

```javascript
// determine-basal.js:63-64
if (!profile.allowSMB_with_high_temptarget && profile.temptargetSet && target_bg > 100) {
    console.error("SMB disabled due to high temptarget of", target_bg);
}

// determine-basal.js:103-107
if (profile.enableSMB_with_temptarget && target_bg < 100) {
    // SMB enabled for low temp target
}
```

## Comparison Matrix

| Feature | Loop | oref0/AAPS |
|---------|------|------------|
| **Target representation** | `ClosedRange<HKQuantity>` | `min_bg`, `max_bg`, `target_bg` |
| **Time-varying** | Yes (`GlucoseRangeSchedule`) | Yes (profile schedule) |
| **Algorithm target** | Dynamic (suspend→midpoint) | Static `(min+max)/2` |
| **Autosens adjusts target** | No | Yes (`sensitivity_raises_target`) |
| **Temp target affects sensitivity** | Via override | Yes (formula-based) |
| **SMB enable by target** | No | Yes (`enableSMB_with_temptarget`) |
| **Safety floor** | Suspend threshold | `target_bg >= 80` |
| **Pre-meal override** | Built-in preset | Manual temp target |
| **Exercise/workout override** | Built-in preset | Manual temp target |

## Nightscout Sync

### Loop to Nightscout
Loop syncs correction range as part of devicestatus:
```json
{
  "loop": {
    "settings": {
      "glucoseTargetRangeSchedule": {
        "unit": "mg/dL",
        "schedule": [
          {"start": 0, "min": 100, "max": 110}
        ]
      }
    }
  }
}
```

### oref0/AAPS to Nightscout
AAPS syncs via profile:
```json
{
  "target_low": [{"time": "00:00", "value": 100}],
  "target_high": [{"time": "00:00", "value": 110}]
}
```

## Parameter Mapping

| Loop Term | oref0 Term | Nightscout |
|-----------|------------|------------|
| `correctionRange.lowerBound` | `min_bg` | `target_low` |
| `correctionRange.upperBound` | `max_bg` | `target_high` |
| `averageValue` | `target_bg` | (calculated) |
| `suspendThreshold` | (derived) | `suspend_threshold` |
| `preMealTargetRange` | (temp target) | `Temporary Target` treatment |
| `workoutTargetRange` | (temp target) | `Temporary Target` treatment |

## Gaps Identified

### GAP-TGT-001: Different Algorithm Targeting Behavior

**Description**: Loop uses dynamic targeting (suspend→midpoint over time); oref0 uses static midpoint.

**Affected Systems**: Loop vs oref0/AAPS

**Evidence**:
- Loop: `DoseMath.swift:200-214` - `targetGlucoseValue()` blends over effect duration
- oref0: `determine-basal.js:243` - Static `(min_bg + max_bg) / 2`

**Impact**: Same target range settings produce different correction behavior.

**Remediation**: Document for users migrating between systems.

### GAP-TGT-002: Autosens Target Adjustment Not in Loop

**Description**: oref0 adjusts targets based on autosens ratio; Loop does not.

**Affected Systems**: Loop vs oref0/AAPS

**Evidence**:
- oref0: `determine-basal.js:296-311` - `sensitivity_raises_target`, `resistance_lowers_target`
- Loop: No equivalent in `DoseMath.swift`

**Impact**: oref0 is more aggressive in adjusting for insulin resistance/sensitivity.

**Remediation**: Design difference - document expected behavior.

### GAP-TGT-003: Temp Target Sensitivity Adjustment

**Description**: oref0 adjusts sensitivity ratio based on temp target magnitude; Loop overrides are simpler.

**Affected Systems**: Loop vs oref0/AAPS

**Evidence**:
- oref0: `determine-basal.js:259-277` - Formula: `c/(c+target_bg-normalTarget)`
- Loop: Override just replaces range, no sensitivity calculation

**Impact**: Exercise modes behave differently between systems.

**Remediation**: Document the formula for users expecting equivalent behavior.

### GAP-TGT-004: SMB Enable Tied to Target in oref0

**Description**: oref0 enables/disables SMB based on target value; Loop has no such coupling.

**Affected Systems**: Loop vs oref0/AAPS

**Evidence**:
- oref0: `determine-basal.js:63-64, 103-107` - `enableSMB_with_temptarget`, high target disables SMB
- Loop: Auto bolus enable is independent of target

**Impact**: Temp targets have different side effects between systems.

**Remediation**: Document for users expecting similar behavior.

## Requirements

### REQ-TGT-001: Target Range Format Documentation

**Statement**: Systems MUST document whether target range is stored as min/max pair or single value.

**Rationale**: Different formats can cause sync/import issues.

**Verification**: Schema review.

### REQ-TGT-002: Target Calculation Transparency

**Statement**: Systems SHOULD document how the algorithm uses target ranges (midpoint, dynamic, etc.).

**Rationale**: Users need to understand correction behavior.

**Verification**: Algorithm documentation review.

### REQ-TGT-003: Temp Target Side Effects

**Statement**: Systems MUST document any side effects of temp targets (sensitivity adjustment, SMB enable).

**Rationale**: Users may expect simple target changes but get algorithm behavior changes.

**Verification**: Documentation audit.

## References

- [Loop Correction Range Documentation](https://loopkit.github.io/loopdocs/operation/features/correction-range/)
- [OpenAPS Target BG Documentation](https://openaps.readthedocs.io/en/latest/docs/Customize-Iterate/autotune.html)
- [AAPS Profile Documentation](https://androidaps.readthedocs.io/en/latest/Configuration/Config-Builder.html#profile)

---

## Conformance Assertions

The following conformance assertions cover target range documentation requirements:

| Assertion File | Requirements | Assertions |
|----------------|--------------|------------|
| `conformance/assertions/algorithm-docs.yaml` | REQ-TGT-001, REQ-TGT-002, REQ-TGT-003 | 11 |

**Key Assertions**:
- `doc-tgt-001`: Loop ClosedRange target format documentation
- `doc-tgt-002`: AAPS/oref0 min_bg/max_bg format documentation
- `doc-tgt-004`: Loop dynamic target behavior documentation
- `doc-tgt-006`: AAPS temp target SMB enable side effects

See `traceability/domain-matrices/aid-algorithms-matrix.md` for full coverage matrix.
