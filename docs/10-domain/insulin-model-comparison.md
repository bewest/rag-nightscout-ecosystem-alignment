# Insulin Model Comparison

> **Status**: Complete  
> **Last Updated**: 2026-01-30  
> **Task**: Compare insulin activity models across Loop and oref0/AAPS

## Executive Summary

Loop and oref0/AAPS use the **same exponential insulin model formula** but with different default parameters and additional curve options:

| Aspect | Loop | oref0/AAPS |
|--------|------|------------|
| **Primary model** | Exponential | Exponential + Bilinear |
| **Formula source** | Loop/LoopKit | Shared (Loop issue #388) |
| **Parameters** | actionDuration, peakActivityTime, delay | dia, peak, curve type |
| **Delay** | 10 min default | Not separate (included in peak) |
| **Curve presets** | Fiasp, Humalog, etc. | rapid-acting, ultra-rapid |

## Loop Insulin Model

### Source File
- `externals/LoopWorkspace/LoopKit/LoopKit/InsulinKit/ExponentialInsulinModel.swift:1-99`

### Model Structure

```swift
public struct ExponentialInsulinModel {
    public let actionDuration: TimeInterval   // DIA in seconds
    public let peakActivityTime: TimeInterval // Peak time in seconds
    public let delay: TimeInterval            // Effect delay (default 600s = 10min)
    
    // Precomputed terms
    fileprivate let τ: Double  // Time constant
    fileprivate let a: Double  // Rise time factor
    fileprivate let S: Double  // Scale factor
}
```

### Formula (ExponentialInsulinModel.swift:32-34)

```swift
self.τ = peakActivityTime * (1 - peakActivityTime / actionDuration) / (1 - 2 * peakActivityTime / actionDuration)
self.a = 2 * τ / actionDuration
self.S = 1 / (1 - a + (1 + a) * exp(-actionDuration / τ))
```

### IOB Calculation (ExponentialInsulinModel.swift:54-66)

```swift
public func percentEffectRemaining(at time: TimeInterval) -> Double {
    let timeAfterDelay = time - delay
    switch timeAfterDelay {
    case let t where t <= 0:
        return 1
    case let t where t >= actionDuration:
        return 0
    default:
        let t = timeAfterDelay
        return 1 - S * (1 - a) *
            ((pow(t, 2) / (τ * actionDuration * (1 - a)) - t / τ - 1) * exp(-t / τ) + 1)
    }
}
```

### Loop Insulin Presets

| Preset | DIA | Peak | Delay |
|--------|-----|------|-------|
| Rapid-Acting (Humalog/Novolog) | 6h | 75 min | 10 min |
| Fiasp | 6h | 55 min | 10 min |
| Lyumjev | 6h | 55 min | 10 min |
| Afrezza | 5h | 29 min | 10 min |

## oref0/AAPS Insulin Model

### Source File
- `externals/oref0/lib/iob/calculate.js:1-146`

### Dual Model Support

oref0 supports both **bilinear** and **exponential** curves:

```javascript
function iobCalc(treatment, time, curve, dia, peak, profile) {
    if (curve === 'bilinear') {
        return iobCalcBilinear(treatment, minsAgo, dia);
    } else {
        return iobCalcExponential(treatment, minsAgo, dia, peak, profile);
    }
}
```

### Bilinear Model (Legacy)

```javascript
// calculate.js:36-80
function iobCalcBilinear(treatment, minsAgo, dia) {
    var default_dia = 3.0  // assumed duration, hours
    var peak = 75;         // assumed peak, minutes
    var end = 180;         // assumed end, minutes

    // Scale by dia ratio
    var timeScalar = default_dia / dia; 
    var scaled_minsAgo = timeScalar * minsAgo;

    // Triangle-based activity curve
    var activityPeak = 2 / (dia * 60)  
    var slopeUp = activityPeak / peak
    var slopeDown = -1 * (activityPeak / (end - peak))
}
```

### Exponential Model (calculate.js:83-143)

Uses **identical formula** to Loop (from Loop issue #388):

```javascript
// Formula source: https://github.com/LoopKit/Loop/issues/388#issuecomment-317938473
var tau = peak * (1 - peak / end) / (1 - 2 * peak / end);
var a = 2 * tau / end;
var S = 1 / (1 - a + (1 + a) * Math.exp(-end / tau));

activityContrib = treatment.insulin * (S / Math.pow(tau, 2)) * minsAgo * 
    (1 - minsAgo / end) * Math.exp(-minsAgo / tau);
iobContrib = treatment.insulin * (1 - S * (1 - a) * 
    ((Math.pow(minsAgo, 2) / (tau * end * (1 - a)) - minsAgo / tau - 1) * 
    Math.exp(-minsAgo / tau) + 1));
```

### Curve Presets

```javascript
// calculate.js:86-116
if (profile.curve === "rapid-acting") {
    peak = 75;  // Default, customizable 50-120 min
} else if (profile.curve === "ultra-rapid") {
    peak = 55;  // Default, customizable 35-100 min
}
```

| Curve | Default Peak | Min Peak | Max Peak |
|-------|--------------|----------|----------|
| rapid-acting | 75 min | 50 min | 120 min |
| ultra-rapid | 55 min | 35 min | 100 min |

## Comparison Matrix

| Feature | Loop | oref0/AAPS |
|---------|------|------------|
| **Exponential model** | ✅ Yes | ✅ Yes (identical formula) |
| **Bilinear model** | ❌ No | ✅ Yes (legacy) |
| **Delay parameter** | ✅ Yes (10 min default) | ❌ No (baked into peak) |
| **Custom peak time** | ✅ Per preset | ✅ useCustomPeakTime setting |
| **DIA units** | Seconds (TimeInterval) | Hours |
| **Activity output** | Separate method | activityContrib in result |
| **IOB output** | percentEffectRemaining | iobContrib in result |

## Parameter Mapping

| Loop Term | oref0 Term | Description |
|-----------|------------|-------------|
| actionDuration | dia × 60 | Total duration in minutes |
| peakActivityTime | peak | Time to peak activity |
| delay | (none) | Effect delay before curve starts |
| τ (tau) | tau | Time constant of decay |
| a | a | Rise time factor |
| S | S | Auxiliary scale factor |

## Key Differences

### 1. Delay Handling
- **Loop**: Explicit `delay` parameter (default 10 min) shifts curve start
- **oref0**: No separate delay; peak time includes any delay

### 2. Model Options
- **Loop**: Exponential only (with presets)
- **oref0**: Bilinear (legacy) or exponential

### 3. Customization
- **Loop**: Fixed presets (Humalog, Fiasp, etc.)
- **oref0**: `useCustomPeakTime` allows per-user adjustment

### 4. Units
- **Loop**: TimeInterval (seconds)
- **oref0**: Minutes for peak, hours for DIA

## Gaps Identified

### GAP-INS-001: Bilinear Model Not in Loop

**Description**: Loop only supports exponential model; oref0 has legacy bilinear option.

**Affected Systems**: Loop vs oref0/AAPS

**Evidence**:
- oref0: `calculate.js:24-28` - conditional bilinear/exponential selection
- Loop: Only ExponentialInsulinModel.swift

**Impact**: Some users may prefer simpler bilinear model.

**Remediation**: Minor - exponential is more accurate; bilinear is legacy.

### GAP-INS-002: Delay Parameter Not in oref0

**Description**: Loop has explicit delay parameter; oref0 does not.

**Affected Systems**: Loop vs oref0

**Evidence**:
- Loop: `ExponentialInsulinModel.swift:14` - `public let delay: TimeInterval`
- oref0: No delay parameter in calculate.js

**Impact**: Slightly different curve start behavior.

**Remediation**: Document for users migrating between systems.

### GAP-INS-003: Custom Peak Time Validation Differs

**Description**: Loop uses fixed presets; oref0 allows custom peak with bounds.

**Affected Systems**: Loop vs oref0/AAPS

**Evidence**:
- oref0: `calculate.js:87-116` - peak bounds 50-120 (rapid) or 35-100 (ultra)
- Loop: Fixed values per insulin type

**Impact**: oref0 users have more flexibility.

**Remediation**: Consider adding custom peak to Loop presets.

### GAP-INS-004: DIA Range Validation Differs

**Description**: Default and valid DIA ranges differ between systems.

**Affected Systems**: Loop vs oref0/AAPS

**Evidence**:
- Loop: Typically 5-7h depending on preset
- oref0: `default_dia = 3.0` in bilinear (legacy)

**Impact**: Misconfigured DIA can cause safety issues.

**Remediation**: Validate DIA on import/sync.

## Requirements

### REQ-INS-001: Formula Consistency

**Statement**: Systems using exponential insulin model MUST use compatible formula.

**Rationale**: Loop and oref0 share the same formula source (issue #388).

**Verification**: Compare IOB output for same inputs.

### REQ-INS-002: DIA Range Validation

**Statement**: Systems MUST validate DIA is within safe bounds (typically 3-8 hours).

**Rationale**: Extreme DIA values can cause unsafe dosing.

**Verification**: Test boundary values.

### REQ-INS-003: Peak Time Documentation

**Statement**: Systems SHOULD document peak time values for each insulin preset.

**Rationale**: Users need to understand how insulin curve affects dosing.

**Verification**: Documentation review.

## References

- [Loop Issue #388](https://github.com/LoopKit/Loop/issues/388#issuecomment-317938473) - Exponential insulin model derivation
- [OpenAPS Insulin Model Documentation](https://openaps.readthedocs.io/en/latest/docs/While%20You%20Wait%20For%20Gear/understanding-insulin-on-board-calculations.html)
- [LoopDocs Insulin Models](https://loopkit.github.io/loopdocs/operation/features/insulin-model/)
