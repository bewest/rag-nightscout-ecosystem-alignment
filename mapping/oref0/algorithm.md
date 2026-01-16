# oref0 Algorithm (determine-basal)

This document describes the core oref0 algorithm implemented in `determine-basal.js` that decides whether to adjust temp basal rates or deliver SMB (Super Micro Bolus).

## Overview

The determine-basal algorithm:
1. Validates inputs (CGM data, profile, IOB)
2. Applies sensitivity adjustments (autosens or temp targets)
3. Calculates expected BG trajectory
4. Generates four prediction curves (IOB, COB, UAM, ZT)
5. Determines minimum predicted BG considering all scenarios
6. Recommends temp basal and/or SMB to reach target

## Key Source File

| File | Lines | Purpose |
|------|-------|---------|
| `oref0:lib/determine-basal/determine-basal.js` | 1193 | Main algorithm |

## Function Signature

**Source**: `oref0:lib/determine-basal/determine-basal.js#L128`

```javascript
var determine_basal = function determine_basal(
    glucose_status,      // Current CGM reading with deltas
    currenttemp,         // Currently running temp basal
    iob_data,            // IOB array with future projections
    profile,             // User settings and limits
    autosens_data,       // Sensitivity ratio
    meal_data,           // COB and deviation data
    tempBasalFunctions,  // Helper functions for temp basal
    microBolusAllowed,   // Whether SMB is permitted
    reservoir_data,      // Pump reservoir level
    currentTime          // Current timestamp
)
```

## Algorithm Flow

### Phase 1: Input Validation

**Source**: `oref0:lib/determine-basal/determine-basal.js#L138-L221`

Check for error conditions that prevent safe operation:

```javascript
// CGM data too old (> 12 min)
if (minAgo > 12 || minAgo < -5) {
    rT.reason = "BG data is too old";
    return tempBasalFunctions.setTempBasal(0, 0, ...);  // Cancel temp
}

// CGM noise too high
if (bg <= 10 || bg === 38 || noise >= 3) {
    rT.reason = "CGM is calibrating or noise is high";
    // Cancel high temps, shorten long zero temps
}

// CGM data unchanged (flat line)
if (glucose_status.delta == 0 && short_avgdelta < 1) {
    rT.reason = "CGM data is unchanged";
    // Cancel high temps
}
```

### Phase 2: Target and Sensitivity

**Source**: `oref0:lib/determine-basal/determine-basal.js#L223-L311`

Calculate effective target BG and sensitivity:

```javascript
// Get target from profile
target_bg = (profile.min_bg + profile.max_bg) / 2;

// Apply sensitivity adjustments
if (temp_target_set && high_target) {
    // Exercise mode: high target raises sensitivity
    sensitivityRatio = c / (c + target_bg - normalTarget);
} else if (autosens_data) {
    sensitivityRatio = autosens_data.ratio;
}

// Adjust basal and ISF by sensitivity
basal = profile.current_basal * sensitivityRatio;
sens = profile.sens / sensitivityRatio;
```

### Phase 3: Core Calculations

**Source**: `oref0:lib/determine-basal/determine-basal.js#L394-L423`

Calculate key values for predictions:

```javascript
// Blood Glucose Impact (expected 5-min BG change from insulin)
var bgi = round((-iob_data.activity * sens * 5), 2);

// Deviation (projected 30-min unexplained BG change)
var deviation = round((30/5) * (minDelta - bgi));

// Naive eventual BG (based only on IOB)
var naive_eventualBG = round(bg - (iob_data.iob * sens));

// Eventual BG including deviation
var eventualBG = naive_eventualBG + deviation;

// Expected delta (where BG should be heading)
var expectedDelta = calculate_expected_delta(target_bg, eventualBG, bgi);
```

### Phase 4: Prediction Curves

**Source**: `oref0:lib/determine-basal/determine-basal.js#L439-L695`

Generate four prediction curves for different scenarios:

#### IOB Prediction
```javascript
// IOB-only: assumes current deviation decays linearly over 60 min
var predDev = ci * (1 - Math.min(1, IOBpredBGs.length / (60/5)));
IOBpredBG = IOBpredBGs[IOBpredBGs.length-1] + predBGI + predDev;
```

#### COB Prediction
```javascript
// COB: includes carb impact decaying over absorption time
var predCI = Math.max(0, ci * (1 - COBpredBGs.length / Math.max(cid*2, 1)));
COBpredBG = COBpredBGs[COBpredBGs.length-1] + predBGI + predCI + remainingCI;
```

#### UAM Prediction
```javascript
// UAM: uses deviation slope for unexplained rises
var predUCIslope = Math.max(0, uci + (UAMpredBGs.length * slopeFromDeviations));
var predUCImax = Math.max(0, uci * (1 - UAMpredBGs.length / (3*60/5)));
var predUCI = Math.min(predUCIslope, predUCImax);
UAMpredBG = UAMpredBGs[UAMpredBGs.length-1] + predBGI + predUCI;
```

#### Zero Temp (ZT) Prediction
```javascript
// ZT: what happens if we stop all insulin now
var predZTBGI = round((-iobTick.iobWithZeroTemp.activity * sens * 5), 2);
ZTpredBG = ZTpredBGs[ZTpredBGs.length-1] + predZTBGI;
```

### Phase 5: Minimum Predicted BG

**Source**: `oref0:lib/determine-basal/determine-basal.js#L704-L803`

Determine the safest minimum predicted BG across all curves:

```javascript
// Blend predictions based on remaining carbs
if (minCOBPredBG < 999 && minUAMPredBG < 999) {
    // Weight COB vs UAM based on carbs remaining
    minPredBG = fractionCarbsLeft * minCOBPredBG + 
                (1 - fractionCarbsLeft) * minUAMPredBG;
} else if (enableUAM) {
    minPredBG = round(Math.max(minIOBPredBG, minZTUAMPredBG));
}
```

### Phase 6: Decision Logic

**Source**: `oref0:lib/determine-basal/determine-basal.js#L905-1188`

#### Low Glucose Suspend (LGS)
```javascript
if (bg < threshold || minGuardBG < threshold) {
    rT.reason += "minGuardBG " + minGuardBG + "<" + threshold;
    return tempBasalFunctions.setTempBasal(0, durationReq, ...);
}
```

#### Eventual BG Below Target
```javascript
if (eventualBG < min_bg) {
    // Calculate reduced temp basal
    var insulinReq = 2 * Math.min(0, (eventualBG - target_bg) / sens);
    var rate = basal + (2 * insulinReq);
    return tempBasalFunctions.setTempBasal(rate, 30, ...);
}
```

#### Eventual BG Above Target (High Temp / SMB)
```javascript
if (eventualBG >= max_bg) {
    // Calculate additional insulin needed
    insulinReq = round((Math.min(minPredBG, eventualBG) - target_bg) / sens, 2);
    
    if (microBolusAllowed && enableSMB && bg > threshold) {
        // SMB Mode: deliver microbolus
        var maxBolus = profile.current_basal * profile.maxSMBBasalMinutes / 60;
        var microBolus = Math.min(insulinReq / 2, maxBolus);
        rT.units = microBolus;
        // Also set zero or low temp to prevent stacking
    } else {
        // Temp Basal Mode: increase temp basal
        rate = basal + (2 * insulinReq);
        return tempBasalFunctions.setTempBasal(rate, 30, ...);
    }
}
```

## SMB (Super Micro Bolus)

### Enable Conditions

**Source**: `oref0:lib/determine-basal/determine-basal.js#L51-L126`

SMB can be enabled by various conditions:

| Condition | Profile Setting | Description |
|-----------|-----------------|-------------|
| Always | `enableSMB_always` | SMB enabled at all times |
| With COB | `enableSMB_with_COB` | SMB enabled when COB > 0 |
| After Carbs | `enableSMB_after_carbs` | SMB enabled for 6h after any carbs |
| With Temp Target | `enableSMB_with_temptarget` | SMB enabled with low temp target |
| High BG | `enableSMB_high_bg` | SMB enabled above threshold BG |

### SMB Constraints

**Source**: `oref0:lib/determine-basal/determine-basal.js#L1076-1100`

```javascript
// Never bolus more than maxSMBBasalMinutes worth of basal
if (iob_data.iob > mealInsulinReq) {
    // IOB > COB: use maxUAMSMBBasalMinutes (default 30 min)
    maxBolus = profile.current_basal * profile.maxUAMSMBBasalMinutes / 60;
} else {
    // Normal: use maxSMBBasalMinutes (default 75 min)
    maxBolus = profile.current_basal * profile.maxSMBBasalMinutes / 60;
}

// Bolus 1/2 the insulinReq, up to maxBolus
var microBolus = Math.min(insulinReq / 2, maxBolus);

// Round down to bolus increment
microBolus = Math.floor(microBolus * roundSMBTo) / roundSMBTo;
```

### SMB Timing

```javascript
// Default: allow SMBs every 3 minutes
var SMBInterval = profile.SMBInterval || 3;  // range 1-10

if (lastBolusAge > SMBInterval) {
    rT.units = microBolus;
    rT.reason += "Microbolusing " + microBolus + "U. ";
} else {
    rT.reason += "Waiting " + nextBolusMins + "m to microbolus again.";
}
```

## Safety Limits

### Max Basal

**Source**: `oref0:lib/basal-set-temp.js`

```javascript
var maxSafeBasal = Math.min(
    profile.max_basal,
    profile.max_daily_basal * profile.max_daily_safety_multiplier,
    profile.current_basal * profile.current_basal_safety_multiplier
);
```

### Max IOB

```javascript
if (iob_data.iob > max_iob) {
    rT.reason += "IOB " + iob_data.iob + " > max_iob " + max_iob;
    return tempBasalFunctions.setTempBasal(basal, 30, ...);  // Just run scheduled basal
}
```

### SMB Disable Conditions

```javascript
// Disable SMB if minGuardBG below threshold
if (minGuardBG < threshold) {
    enableSMB = false;
}

// Disable SMB for sudden rises (> 20% of BG in 45 min)
if (maxDelta > 0.2 * bg) {
    enableSMB = false;
}
```

## Output Structure

```javascript
return {
    temp: 'absolute',
    bg: bg,
    tick: tick,
    eventualBG: eventualBG,
    sensitivityRatio: sensitivityRatio,
    insulinReq: insulinReq,
    
    predBGs: {
        IOB: IOBpredBGs,    // [101, 100, 98, 97, ...]
        ZT: ZTpredBGs,      // [101, 100, 99, 98, ...]
        COB: COBpredBGs,    // [101, 102, 103, ...]
        UAM: UAMpredBGs     // [101, 100, 99, ...]
    },
    
    COB: meal_data.mealCOB,
    IOB: iob_data.iob,
    BGI: bgi,
    deviation: deviation,
    ISF: sens,
    CR: profile.carb_ratio,
    target_bg: target_bg,
    
    reason: "human readable explanation",
    
    rate: 0.5,           // Temp basal rate (U/hr)
    duration: 30,        // Temp basal duration (min)
    units: 0.3           // SMB size (units), if applicable
};
```

## Cross-Project Comparison

| Aspect | oref0 | Loop | Notes |
|--------|-------|------|-------|
| Predictions | 4 curves (IOB, COB, UAM, ZT) | 1 combined | oref0 outputs more detail |
| SMB | Yes | Automatic Dose | Similar concept |
| UAM | Yes | No explicit | oref0 handles unannounced meals |
| Decision | Rule-based | Prediction minimization | Different approaches |
| Sensitivity | Autosens ratio | Retrospective Correction | Different mechanisms |
