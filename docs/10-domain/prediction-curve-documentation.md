# Prediction Curve Documentation

> **Status**: Complete  
> **Last Updated**: 2026-01-30  
> **Task**: Document prediction curve generation across Loop and oref0/AAPS

## Executive Summary

Loop and oref0/AAPS generate fundamentally different prediction structures:

| Aspect | Loop | oref0/AAPS |
|--------|------|------------|
| **Curves** | Single combined prediction | 4 separate curves (IOB, COB, UAM, ZT) |
| **Components** | Effects summed together | Each scenario isolated |
| **Output** | `loop.predicted.values` | `openaps.suggested.predBGs.*` |
| **Resolution** | Variable (5min default) | 5-minute intervals |
| **Max duration** | ~6 hours (insulin activity) | 4 hours (48 data points) |

## Loop Prediction Architecture

### Source Files
- `externals/LoopWorkspace/LoopKit/LoopKit/LoopAlgorithm/LoopAlgorithm.swift:74-188`
- `externals/LoopWorkspace/LoopKit/LoopKit/LoopAlgorithm/LoopPredictionOutput.swift:1-50`
- `externals/LoopWorkspace/Loop/Loop/Managers/LoopDataManager.swift:1228-2040`

### Prediction Generation (LoopAlgorithm.swift:74-188)

Loop generates a **single combined prediction** by summing multiple effect types:

```swift
public static func generatePrediction(input: LoopPredictionInput, startDate: Date? = nil) throws -> LoopPrediction {
    // 1. Insulin effects
    let insulinEffects = annotatedDoses.glucoseEffects(...)
    
    // 2. Insulin Counteraction Effects (ICE)
    let insulinCounteractionEffects = input.glucoseHistory.counteractionEffects(to: insulinEffects)
    
    // 3. Carb effects (dynamic)
    let carbEffects = input.carbEntries.map(...).dynamicGlucoseEffects(...)
    
    // 4. Retrospective Correction
    let rcEffect = rc.computeEffect(...)
    
    // 5. Momentum (short-term trend)
    let momentumEffects = momentumInputData.linearMomentumEffect()
    
    // Combine all effects into single prediction
    var prediction = LoopMath.predictGlucose(
        startingAt: latestGlucose, 
        momentum: momentumEffects, 
        effects: effects
    )
}
```

### Effect Components

Loop tracks 4 effect types that sum to create the prediction:

| Effect | Source | Description |
|--------|--------|-------------|
| `insulin` | `[GlucoseEffect]` | Expected BG drop from active insulin |
| `carbs` | `[GlucoseEffect]` | Expected BG rise from absorbed carbs |
| `retrospectiveCorrection` | `[GlucoseEffect]` | Adjustment for model/actual discrepancy |
| `momentum` | `[GlucoseEffect]` | Short-term BG trend extrapolation |

### Algorithm Effects Options

```swift
public struct AlgorithmEffectsOptions: OptionSet {
    public static let carbs            = AlgorithmEffectsOptions(rawValue: 1 << 0)
    public static let insulin          = AlgorithmEffectsOptions(rawValue: 1 << 1)
    public static let momentum         = AlgorithmEffectsOptions(rawValue: 1 << 2)
    public static let retrospection    = AlgorithmEffectsOptions(rawValue: 1 << 3)
    public static let all: AlgorithmEffectsOptions = [.carbs, .insulin, .momentum, .retrospection]
}
```

### Output Structure

```swift
public struct LoopPrediction: GlucosePrediction {
    public var glucose: [PredictedGlucoseValue]  // Single combined array
    public var effects: LoopAlgorithmEffects     // Component breakdown
}
```

Uploaded to Nightscout as:
```json
{
  "loop": {
    "predicted": {
      "startDate": "2026-01-30T00:00:00Z",
      "values": [120, 115, 110, 105, 100, ...]
    }
  }
}
```

## oref0/AAPS Prediction Architecture

### Source Files
- `externals/oref0/lib/determine-basal/determine-basal.js:442-720`

### Four Prediction Curves

oref0 generates **4 separate prediction arrays**, each modeling a different scenario:

```javascript
// determine-basal.js:442-449
var COBpredBGs = [];
var IOBpredBGs = [];
var UAMpredBGs = [];
var ZTpredBGs = [];
COBpredBGs.push(bg);
IOBpredBGs.push(bg);
ZTpredBGs.push(bg);
UAMpredBGs.push(bg);
```

### Curve Definitions

| Curve | Name | Purpose | Formula |
|-------|------|---------|---------|
| **IOB** | Insulin On Board | BG if no carbs absorbed | `prevBG + predBGI + predDev` |
| **COB** | Carbs On Board | BG with expected carb absorption | `prevBG + predBGI + predDev + predCI + remainingCI` |
| **UAM** | Unannounced Meal | BG with deviation-based carb impact | `prevBG + predBGI + predDev + predUCI` |
| **ZT** | Zero Temp | BG with zero temp basal | `prevBG + predZTBGI` |

### Prediction Loop (determine-basal.js:574-639)

```javascript
iobArray.forEach(function(iobTick) {
    // Blood Glucose Impact from insulin
    var predBGI = round(( -iobTick.activity * sens * 5 ), 2);
    var predZTBGI = round(( -iobTick.iobWithZeroTemp.activity * sens * 5 ), 2);
    
    // IOB prediction: deviation decays linearly over 60 min
    var predDev = ci * ( 1 - Math.min(1,IOBpredBGs.length/(60/5)) );
    IOBpredBG = IOBpredBGs[IOBpredBGs.length-1] + predBGI + predDev;
    
    // ZT prediction: only insulin effect with zero temp
    var ZTpredBG = ZTpredBGs[ZTpredBGs.length-1] + predZTBGI;
    
    // COB prediction: includes predicted carb impact
    var predCI = Math.max(0, ci * ( 1 - COBpredBGs.length/Math.max(cid*2,1) ) );
    COBpredBG = COBpredBGs[COBpredBGs.length-1] + predBGI + predDev + predCI + remainingCI;
    
    // UAM prediction: uses deviation slope
    var predUCI = Math.min(predUCIslope, predUCImax);
    UAMpredBG = UAMpredBGs[UAMpredBGs.length-1] + predBGI + predDev + predUCI;
    
    // Add to arrays (max 48 points = 4 hours)
    if ( IOBpredBGs.length < 48) { IOBpredBGs.push(IOBpredBG); }
    if ( COBpredBGs.length < 48) { COBpredBGs.push(COBpredBG); }
    if ( UAMpredBGs.length < 48) { UAMpredBGs.push(UAMpredBG); }
    if ( ZTpredBGs.length < 48) { ZTpredBGs.push(ZTpredBG); }
});
```

### Output Assignment (determine-basal.js:649-698)

```javascript
rT.predBGs = {};
rT.predBGs.IOB = IOBpredBGs;  // Always present
rT.predBGs.ZT = ZTpredBGs;    // Always present

// COB only if carbs present
if (meal_data.mealCOB > 0 && (ci > 0 || remainingCIpeak > 0)) {
    rT.predBGs.COB = COBpredBGs;
}

// UAM only if enabled and carb impact detected
if (enableUAM) {
    rT.predBGs.UAM = UAMpredBGs;
}
```

### Uploaded to Nightscout

```json
{
  "openaps": {
    "suggested": {
      "predBGs": {
        "IOB": [120, 115, 110, 105, 100, ...],
        "ZT": [120, 118, 116, 114, 112, ...],
        "COB": [120, 125, 130, 128, 125, ...],
        "UAM": [120, 123, 126, 124, 122, ...]
      }
    }
  }
}
```

## Nightscout Display Handling

### Source File
- `externals/cgm-remote-monitor/lib/report_plugins/daytoday.js:347-360`

### Conditional Parsing

```javascript
// daytoday.js:347-360
if (data.devicestatus[i].loop && data.devicestatus[i].loop.predicted) {
    // Loop: single array
    predictions.push(data.devicestatus[i].loop.predicted);
} else if (data.devicestatus[i].openaps && data.devicestatus[i].openaps.suggested && data.devicestatus[i].openaps.suggested.predBGs) {
    // oref0/AAPS: select best curve
    entry.startDate = data.devicestatus[i].openaps.suggested.timestamp;
    if (data.devicestatus[i].openaps.suggested.predBGs.COB) {
        entry.values = data.devicestatus[i].openaps.suggested.predBGs.COB;
    } else if (data.devicestatus[i].openaps.suggested.predBGs.UAM) {
        entry.values = data.devicestatus[i].openaps.suggested.predBGs.UAM;
    } else {
        entry.values = data.devicestatus[i].openaps.suggested.predBGs.IOB;
    }
}
```

**Selection Priority for oref0:**
1. COB (if available) - meal in progress
2. UAM (if available) - unannounced meal detected
3. IOB (always present) - fallback

## Comparison Matrix

| Feature | Loop | oref0/AAPS |
|---------|------|------------|
| **Number of curves** | 1 | 4 |
| **Curve names** | `predicted.values` | `IOB`, `COB`, `UAM`, `ZT` |
| **Max duration** | ~6h (insulin activity) | 4h (48 × 5min) |
| **Resolution** | Variable | Fixed 5min |
| **Effect breakdown** | Available in `effects` | Implicit in curves |
| **ZT scenario** | Not separate | Explicit curve |
| **Momentum** | Included | Not explicit |

## Use Case Comparison

### Loop Single Curve
- **Pro**: Simpler to display and interpret
- **Pro**: Effects available separately for debugging
- **Con**: Cannot show "what if no carbs" scenario

### oref0 Four Curves
- **Pro**: Shows multiple scenarios simultaneously
- **Pro**: ZT curve shows safety net
- **Con**: More complex to display
- **Con**: Nightscout must choose which to show

## Decision Logic Comparison

### Loop
Uses single prediction to determine:
- Temp basal adjustment
- Bolus recommendation
- High/low alerts

### oref0/AAPS
Uses **minimum of curves** for safety (determine-basal.js:704-720):
```javascript
minIOBPredBG = Math.max(39, minIOBPredBG);
minCOBPredBG = Math.max(39, minCOBPredBG);
minUAMPredBG = Math.max(39, minUAMPredBG);
minPredBG = round(minIOBPredBG);

// Weight COB vs UAM based on remaining carbs
if (minUAMPredBG < 999 && minCOBPredBG < 999) {
    avgPredBG = round((1-fractionCarbsLeft)*UAMpredBG + fractionCarbsLeft*COBpredBG);
}
```

## Gaps Identified

### GAP-PRED-001: Prediction Structure Incompatibility

**Description**: Loop outputs single combined curve; oref0 outputs 4 separate curves.

**Affected Systems**: Loop, AAPS, Trio, Nightscout

**Evidence**:
- Loop: `LoopAlgorithm.swift:168` - single `prediction` array
- oref0: `determine-basal.js:649-690` - `predBGs.IOB/COB/UAM/ZT`

**Impact**: Nightscout must conditionally parse both formats.

**Remediation**: Documented in Nightscout; no alignment needed (design difference).

### GAP-PRED-002: No ZT Curve in Loop

**Description**: Loop does not generate a "zero temp" prediction scenario.

**Affected Systems**: Loop vs oref0/AAPS

**Evidence**:
- oref0: `determine-basal.js:445,583` - ZTpredBGs with `iobWithZeroTemp`
- Loop: No equivalent

**Impact**: Loop cannot show "what if pump suspended" scenario.

**Remediation**: Design difference - Loop handles differently.

### GAP-PRED-003: Momentum Not Explicit in oref0

**Description**: oref0 does not have explicit momentum effect like Loop.

**Affected Systems**: Loop vs oref0

**Evidence**:
- Loop: `LoopAlgorithm.swift:160-166` - `momentumEffects`
- oref0: Uses `delta` and `avgDelta` but not as separate effect

**Impact**: Short-term trend handling differs.

**Remediation**: Document in algorithm comparison.

### GAP-PRED-004: Curve Selection in Nightscout Display

**Description**: Nightscout arbitrarily selects COB > UAM > IOB for display.

**Affected Systems**: Nightscout

**Evidence**: `daytoday.js:353-357` - priority selection logic

**Impact**: Users may not see all prediction scenarios.

**Remediation**: Consider UI option to show all curves.

## Requirements

### REQ-PRED-001: Prediction Structure Documentation

**Statement**: AID systems MUST document their prediction curve structure and meaning.

**Rationale**: Users and developers need to understand what predictions represent.

**Verification**: Documentation review.

### REQ-PRED-002: Prediction Curve Labeling

**Statement**: Systems displaying predictions SHOULD label curve type (Loop, IOB, COB, UAM, ZT).

**Rationale**: Different curves have different meanings and use cases.

**Verification**: UI audit.

### REQ-PRED-003: Multi-Curve Display Option

**Statement**: Nightscout SHOULD provide option to display all oref0 prediction curves.

**Rationale**: Users benefit from seeing all scenarios, especially ZT for safety.

**Verification**: Settings UI check.

## References

- [OpenAPS Predictions Documentation](https://openaps.readthedocs.io/en/latest/docs/While%20You%20Wait%20For%20Gear/Understand-determine-basal.html)
- [LoopDocs Algorithm](https://loopkit.github.io/loopdocs/operation/algorithm/prediction/)
- Nightscout daytoday.js prediction handling
