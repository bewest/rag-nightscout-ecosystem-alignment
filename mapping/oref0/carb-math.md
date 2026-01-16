# oref0 Carb Math (COB Calculation)

This document describes how oref0 calculates Carbs on Board (COB) and detects carb absorption.

## Overview

Unlike Loop's dynamic piecewise-linear absorption model, oref0 uses a **deviation-based** approach:

1. Calculate expected BG change from insulin (BGI)
2. Observe actual BG change (delta)
3. Attribute the difference (deviation) to carb absorption
4. Use minimum assumed absorption rate (`min_5m_carbimpact`) as a floor

## Key Source Files

| File | Purpose |
|------|---------|
| `oref0:lib/determine-basal/cob.js` | Carb absorption detection |
| `oref0:lib/meal/total.js` | Meal data aggregation |
| `oref0:lib/meal/history.js` | Carb history processing |

## Core Concept: Deviation

**Deviation** is the difference between observed BG change and expected BG change from insulin:

```
deviation = delta - BGI
```

Where:
- `delta` = actual BG change over 5 minutes
- `BGI` = expected BG change from insulin activity

**Positive deviation** = BG rising faster than expected → carbs being absorbed
**Negative deviation** = BG falling faster than expected → less carbs absorbing

## Carb Absorption Detection

**Source**: `oref0:lib/determine-basal/cob.js#L8-L210`

### Algorithm Flow

1. **Bucket glucose data** into 5-minute intervals (interpolate gaps)
2. **Calculate deviations** for each interval:
   ```javascript
   var bgi = Math.round((-iob.activity * sens * 5) * 100) / 100;
   var deviation = delta - bgi;
   ```
3. **Track deviation statistics**:
   - `currentDeviation` - most recent deviation
   - `maxDeviation` - peak positive deviation
   - `minDeviation` - minimum deviation
   - `slopeFromMaxDeviation` - rate of change from peak
4. **Calculate absorbed carbs** from deviation:
   ```javascript
   // If deviation > 2 * min_5m_carbimpact, use deviation/2
   // Otherwise use min_5m_carbimpact (default 8 mg/dL/5m)
   var ci = Math.max(deviation, currentDeviation/2, profile.min_5m_carbimpact);
   var absorbed = ci * profile.carb_ratio / sens;
   carbsAbsorbed += absorbed;
   ```

### min_5m_carbimpact

The minimum assumed carb impact when observed deviation is low or negative.

**Source**: `oref0:lib/determine-basal/cob.js#L189-L194`

| Parameter | Default | Unit | Description |
|-----------|---------|------|-------------|
| `min_5m_carbimpact` | 8 | mg/dL/5min | Minimum assumed BG rise from carbs |

This prevents COB from stalling during:
- Temporary BG drops (compression, activity)
- Protein/fat delayed absorption
- Sensor noise

**Conversion to grams absorbed**:
```javascript
// Carb Sensitivity Factor (CSF)
var csf = sens / carb_ratio;  // mg/dL per gram

// Carbs absorbed = impact / CSF
var absorbed = min_5m_carbimpact / csf;

// Example: 8 mg/dL / (50/10) = 8/5 = 1.6g per 5 min
```

## Carb Impact Duration

**Source**: `oref0:lib/determine-basal/determine-basal.js#L539-L546`

The duration of carb impact is calculated from COB and observed absorption rate:

```javascript
// CI (mg/dL/5m) for duration calculation
// cid = carb impact duration in 5-min intervals
if (ci === 0) {
    cid = 0;
} else {
    cid = Math.min(remainingCATime * 60/5/2, 
                   Math.max(0, meal_data.mealCOB * csf / ci));
}
```

## Carb Absorption Model

oref0 uses a **linear decay** model where carb impact decreases linearly from current level to zero:

**Source**: `oref0:lib/determine-basal/determine-basal.js#L584-L596`

```javascript
// For COBpredBGs, carb impact drops linearly
var predCI = Math.max(0, ci * (1 - COBpredBGs.length / Math.max(cid*2, 1)));

// Remaining carbs after linear decay absorb in /\ bilinear curve
var intervals = Math.min(COBpredBGs.length, (remainingCATime*12) - COBpredBGs.length);
var remainingCI = Math.max(0, intervals / (remainingCATime/2*12) * remainingCIpeak);
```

### Absorption Curve Shape

```
Carb Impact
    ^
    |\ 
    | \          /\
    |  \        /  \     <- remaining carbs bilinear
    |   \      /    \
    |    \    /      \
    |     \  /        \
    |      \/          \
    |________|__________|_______> Time
    now    cid    remainingCATime
```

## Remaining Carbs Estimation

**Source**: `oref0:lib/determine-basal/determine-basal.js#L511-L528`

```javascript
// Total CI over remaining absorption time
var totalCI = Math.max(0, ci / 5 * 60 * remainingCATime / 2);

// Total carbs absorbed = totalCI / CSF
var totalCA = totalCI / csf;

// Remaining carbs = COB - expected absorption
var remainingCarbs = Math.max(0, meal_data.mealCOB - totalCA - 
                              meal_data.carbs * remainingCarbsIgnore);
remainingCarbs = Math.min(remainingCarbsCap, remainingCarbs);  // Cap at 90g
```

## Key Constants and Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_5m_carbimpact` | 8 mg/dL/5m | Minimum assumed absorption rate |
| `maxCOB` | 120g | Maximum COB allowed |
| `remainingCarbsCap` | 90g | Cap on remaining carbs estimate |
| `remainingCarbsFraction` | 1.0 | Fraction of carbs to consider |
| `maxCarbAbsorptionRate` | 30g/hr | Maximum assumed absorption rate |
| `assumedCarbAbsorptionRate` | 20g/hr | Default assumed rate for duration |
| `remainingCATimeMin` | 3 hours | Minimum remaining absorption time |

## Meal Data Structure

**Source**: `oref0:lib/meal/total.js`

```json
{
  "carbs": 60,
  "mealCOB": 45,
  "currentDeviation": 2.5,
  "maxDeviation": 5.0,
  "minDeviation": 0.5,
  "slopeFromMaxDeviation": -0.5,
  "slopeFromMinDeviation": 0.2,
  "allDeviations": [2, 3, 5, 4, 2],
  "lastCarbTime": 1527923100000,
  "bwFound": false
}
```

## UAM (Unannounced Meals)

When `enableUAM` is true, oref0 can detect and respond to unannounced carbs by observing positive deviations even without carb entries.

**Source**: `oref0:lib/determine-basal/determine-basal.js#L597-L610`

```javascript
// UAM uses deviation slope to predict future impact
var predUCIslope = Math.max(0, uci + (UAMpredBGs.length * slopeFromDeviations));

// Fallback: linear decay over 3 hours if slope is too flat
var predUCImax = Math.max(0, uci * (1 - UAMpredBGs.length / Math.max(3*60/5, 1)));

// Use the lesser of slope-based or DIA-based prediction
var predUCI = Math.min(predUCIslope, predUCImax);
```

## Comparison with Other Projects

| Aspect | oref0 | Loop | AAPS |
|--------|-------|------|------|
| Model Type | Deviation-based | Dynamic absorption | Same as oref0 |
| Absorption Curve | Linear decay | PiecewiseLinear | Linear decay |
| Min Rate | min_5m_carbimpact | absorptionTimeOverrun | min_5m_carbimpact |
| Adaptivity | Static assumptions | Observes actual rate | Static assumptions |
| UAM Support | Yes | No explicit | Yes |
| COB Cap | 120g (maxCOB) | Based on carb entry | 120g (maxCOB) |

## Cross-Project Note: GAP-SYNC-002

The COB prediction curve (`predBGs.COB[]`) is output separately from `predBGs.IOB[]`, enabling comparison of:
- oref0/AAPS: Separate `predBGs.COB[]`
- Loop: Combined prediction only (individual effects not uploaded)

This separation is valuable for algorithm comparison and debugging.
