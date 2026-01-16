# oref0 Safety Guards

This document describes the safety mechanisms in oref0 that protect against overdosing and handle edge cases.

## Overview

oref0 implements multiple layers of safety:
1. **Input validation** - Reject stale/noisy CGM data
2. **Prediction guards** - Conservative estimates with multiple scenarios
3. **Rate limits** - Max basal, max IOB, max bolus
4. **SMB constraints** - Timing, size, and enable conditions
5. **Low glucose handling** - Automatic suspend when low predicted

## CGM Data Quality Checks

**Source**: `oref0:lib/determine-basal/determine-basal.js#L168-L221`

### Stale Data

```javascript
var bgTime = new Date(glucose_status.date);
var minAgo = round((systemTime - bgTime) / 60 / 1000, 1);

if (minAgo > 12 || minAgo < -5) {
    rT.reason = "BG data is too old. The last BG was read " + minAgo + "m ago";
    // Cancel any high temps, shorten long zero temps
}
```

| Condition | Action |
|-----------|--------|
| BG > 12 min old | Cancel high temp, shorten zero temp |
| BG in future (> -5 min) | Cancel high temp, shorten zero temp |

### CGM Error States

```javascript
// BG <= 10 is usually a sensor error code
// BG == 38 is xDrip ??? mode (sensor failure)
// noise >= 3 indicates high CGM noise

if (bg <= 10 || bg === 38 || noise >= 3) {
    rT.reason = "CGM is calibrating, in ??? state, or noise is high";
}
```

### Flat CGM Data (Compression/Failure)

```javascript
// BG unchanged for 45+ minutes with minimal delta
if (bg > 60 && 
    glucose_status.delta == 0 && 
    short_avgdelta > -1 && short_avgdelta < 1 &&
    long_avgdelta > -1 && long_avgdelta < 1) {
    
    if (glucose_status.device !== "fakecgm") {
        rT.reason = "CGM data is unchanged";
        // Cancel high temps
    }
}
```

### Noisy CGM - Target Adjustment

**Source**: `oref0:lib/determine-basal/determine-basal.js#L313-L326`

```javascript
if (glucose_status.noise >= 2) {
    // Raise target by 10-30% for noisy data
    var noisyCGMTargetMultiplier = Math.max(1.1, profile.noisyCGMTargetMultiplier);
    target_bg = round(Math.min(200, target_bg * noisyCGMTargetMultiplier));
}
```

## Low Glucose Prevention

### Threshold Calculation

**Source**: `oref0:lib/determine-basal/determine-basal.js#L328-L329`

```javascript
// Suspend threshold scales with target
// min_bg 90 → threshold 65
// min_bg 100 → threshold 70
// min_bg 110 → threshold 75
var threshold = min_bg - 0.5 * (min_bg - 40);
```

| Target BG | Suspend Threshold |
|-----------|-------------------|
| 80 | 60 |
| 90 | 65 |
| 100 | 70 |
| 110 | 75 |
| 120 | 80 |

### Predictive Low Glucose Suspend (PLGS)

**Source**: `oref0:lib/determine-basal/determine-basal.js#L908-L921`

```javascript
if (bg < threshold || minGuardBG < threshold) {
    rT.reason += "minGuardBG " + minGuardBG + "<" + threshold;
    
    // Calculate zero temp duration needed
    bgUndershoot = target_bg - minGuardBG;
    worstCaseInsulinReq = bgUndershoot / sens;
    durationReq = round(60 * worstCaseInsulinReq / profile.current_basal);
    durationReq = Math.min(120, Math.max(30, durationReq));  // 30-120 min
    
    return tempBasalFunctions.setTempBasal(0, durationReq, ...);
}
```

### Carbs Required Alert

**Source**: `oref0:lib/determine-basal/determine-basal.js#L882-L903`

```javascript
// Calculate carbs needed to prevent low
var zeroTempEffect = profile.current_basal * sens * zeroTempDuration / 60;
var carbsReq = (bgUndershoot - zeroTempEffect) / csf - COBforCarbsReq;

if (carbsReq >= profile.carbsReqThreshold && minutesAboveThreshold <= 45) {
    rT.carbsReq = carbsReq;
    rT.reason += carbsReq + " add'l carbs req w/in " + minutesAboveThreshold + "m";
}
```

## Max Basal Safety

**Source**: `oref0:lib/basal-set-temp.js`

```javascript
function getMaxSafeBasal(profile) {
    return Math.min(
        profile.max_basal,                                    // Hard limit (e.g., 4 U/hr)
        profile.max_daily_basal * profile.max_daily_safety_multiplier,   // e.g., 1.0 * 4 = 4
        profile.current_basal * profile.current_basal_safety_multiplier  // e.g., 1.0 * 5 = 5
    );
}
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_basal` | 4 U/hr | Absolute maximum temp basal |
| `max_daily_safety_multiplier` | 4 | Multiplier on max scheduled basal |
| `current_basal_safety_multiplier` | 5 | Multiplier on current scheduled basal |

**Example**: If max scheduled basal is 1.2 U/hr and current basal is 1.0 U/hr:
- Limit 1: `max_basal` = 4 U/hr
- Limit 2: 1.2 × 4 = 4.8 U/hr
- Limit 3: 1.0 × 5 = 5.0 U/hr
- **Effective max**: min(4, 4.8, 5) = **4 U/hr**

## Max IOB Safety

**Source**: `oref0:lib/determine-basal/determine-basal.js#L1045-L1063`

```javascript
// If IOB exceeds max_iob, just run scheduled basal
if (iob_data.iob > max_iob) {
    rT.reason += "IOB " + iob_data.iob + " > max_iob " + max_iob;
    return tempBasalFunctions.setTempBasal(basal, 30, ...);
}

// Limit insulinReq to stay within max_iob
if (insulinReq > max_iob - iob_data.iob) {
    rT.reason += "max_iob " + max_iob;
    insulinReq = max_iob - iob_data.iob;
}
```

## SMB Safety Constraints

### Size Limits

**Source**: `oref0:lib/determine-basal/determine-basal.js#L1076-1100`

```javascript
// Calculate max bolus based on situation
if (iob_data.iob > mealInsulinReq && iob_data.iob > 0) {
    // IOB > COB → UAM mode, use stricter limit
    maxBolus = profile.current_basal * profile.maxUAMSMBBasalMinutes / 60;
} else {
    // Normal → use standard limit
    maxBolus = profile.current_basal * profile.maxSMBBasalMinutes / 60;
}

// Only deliver half the calculated requirement
var microBolus = Math.min(insulinReq / 2, maxBolus);

// Round down to nearest increment (never round up)
microBolus = Math.floor(microBolus * roundSMBTo) / roundSMBTo;
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `maxSMBBasalMinutes` | 75 min | Max SMB = basal × 75/60 = 1.25× basal |
| `maxUAMSMBBasalMinutes` | 30 min | Max SMB in UAM = basal × 30/60 = 0.5× basal |
| `bolus_increment` | 0.1 U | Minimum SMB step size |

### Timing Constraints

```javascript
// Minimum interval between SMBs
var SMBInterval = profile.SMBInterval || 3;  // Default 3 minutes
SMBInterval = Math.min(10, Math.max(1, SMBInterval));  // Clamp 1-10 min

if (lastBolusAge <= SMBInterval) {
    rT.reason += "Waiting " + nextBolusMins + "m to microbolus again.";
    rT.units = undefined;  // Don't deliver SMB yet
}
```

### BG Threshold

```javascript
// Only SMB when BG is above suspend threshold
if (microBolusAllowed && enableSMB && bg > threshold) {
    // Calculate and deliver SMB
}
```

### Disable for Predicted Lows

**Source**: `oref0:lib/determine-basal/determine-basal.js#L862-L866`

```javascript
if (enableSMB && minGuardBG < threshold) {
    console.error("minGuardBG", minGuardBG, "projected below", threshold, "- disabling SMB");
    enableSMB = false;
}
```

### Disable for Sudden Rises

**Source**: `oref0:lib/determine-basal/determine-basal.js#L867-L880`

```javascript
// Sudden rises may be calibration artifacts
var maxDelta_bg_threshold = profile.maxDelta_bg_threshold || 0.2;
maxDelta_bg_threshold = Math.min(maxDelta_bg_threshold, 0.3);  // Cap at 30%

if (maxDelta > maxDelta_bg_threshold * bg) {
    // e.g., if BG rose 25 in 45 min when BG is 100, that's 25%
    console.error("maxDelta " + maxDelta + " > " + (100 * maxDelta_bg_threshold) + 
                  "% of BG - disabling SMB");
    enableSMB = false;
}
```

### Bolus Wizard (A52 Risk) Warning

**Source**: `oref0:lib/determine-basal/determine-basal.js#L66-L75`

```javascript
if (meal_data.bwFound === true && profile.A52_risk_enable === false) {
    console.error("SMB disabled due to Bolus Wizard activity in the last 6 hours.");
    return false;  // Disable SMB
}

// Warning even if enabled
if (meal_data.bwFound) {
    console.error("Warning: SMB enabled within 6h of using Bolus Wizard: " +
                  "be sure to easy bolus 30s before using Bolus Wizard");
}
```

## Temp Basal Validation

**Source**: `oref0:lib/determine-basal/determine-basal.js#L366-L392`

```javascript
// Cancel temp if currenttemp doesn't match pumphistory
if (microBolusAllowed && 
    currenttemp.rate !== iob_data.lastTemp.rate && 
    lastTempAge > 10 && 
    currenttemp.duration) {
    
    rT.reason = "Warning: currenttemp rate " + currenttemp.rate + 
                " != lastTemp rate " + iob_data.lastTemp.rate + 
                " from pumphistory; canceling temp";
    return tempBasalFunctions.setTempBasal(0, 0, ...);
}
```

## DIA Minimum Enforcement

**Source**: `oref0:lib/iob/total.js#L24-L27`, `L60-L63`

```javascript
// Force minimum DIA of 3h for all curves
if (dia < 3) {
    dia = 3;
}

// Force minimum DIA of 5h for exponential curves
if (defaults.requireLongDia && dia < 5) {
    dia = 5;
}
```

## Summary of Safety Parameters

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `max_basal` | 4 U/hr | Hard limit on temp basal rate |
| `max_iob` | 6 U | Maximum insulin on board |
| `maxSMBBasalMinutes` | 75 min | Max SMB size (as minutes of basal) |
| `maxUAMSMBBasalMinutes` | 30 min | Max SMB in UAM mode |
| `SMBInterval` | 3 min | Minimum time between SMBs |
| `max_daily_safety_multiplier` | 4 | Multiplier on max daily basal |
| `current_basal_safety_multiplier` | 5 | Multiplier on current basal |
| `autosens_min` | 0.5 | Minimum autosens ratio |
| `autosens_max` | 2.0 | Maximum autosens ratio |
| `maxDelta_bg_threshold` | 0.2 | Max BG rise % before SMB disabled |
| `carbsReqThreshold` | 1 | Minimum carbs to trigger alert |

## Comparison with Other Projects

| Safety Feature | oref0 | AAPS | Loop |
|----------------|-------|------|------|
| CGM staleness check | > 12 min | Same | > 15 min |
| Max IOB | Yes | Yes | Yes |
| Max basal multipliers | Yes | Yes | No (uses max basal only) |
| SMB constraints | Yes | Yes | N/A (auto-bolus) |
| PLGS (low suspend) | Yes | Yes | Yes |
| Noise handling | Raise target | Same | Suspend if noisy |
| Bolus Wizard warning | Yes | Yes | N/A |
