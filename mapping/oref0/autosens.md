# oref0 Autosens (Sensitivity Detection)

This document describes how oref0's autosens algorithm detects insulin sensitivity changes.

## Overview

Autosens analyzes 24 hours of glucose and insulin data to calculate a **sensitivity ratio** that adjusts the algorithm's behavior:

- **ratio < 1.0** = More sensitive than normal → reduce insulin
- **ratio = 1.0** = Normal sensitivity → no adjustment
- **ratio > 1.0** = More resistant than normal → increase insulin

## Key Source Files

| File | Purpose |
|------|---------|
| `oref0:lib/determine-basal/autosens.js` | Main autosens algorithm |
| `oref0:bin/oref0-detect-sensitivity.js` | CLI wrapper |
| `oref0:bin/oref0-autosens-history.js` | Historical autosens |

## Algorithm Overview

**Source**: `oref0:lib/determine-basal/autosens.js#L11-L454`

1. **Collect 24h of data** (or since last site change if `rewind_resets_autosens` is enabled)
2. **Bucket glucose** into 5-minute intervals
3. **Exclude meal absorption periods** (when COB > 0 or within 4h of carbs)
4. **Calculate deviations** for each interval:
   ```javascript
   deviation = avgDelta - BGI
   ```
5. **Analyze deviation percentiles** to determine sensitivity ratio
6. **Clamp ratio** to `autosens_min` / `autosens_max` range

## Data Window

**Source**: `oref0:lib/determine-basal/autosens.js#L24-L46`

```javascript
// Use last 24h of data by default
var lastSiteChange = new Date(new Date().getTime() - (24 * 60 * 60 * 1000));

// If rewind_resets_autosens, scan for pump rewind events
if (profile.rewind_resets_autosens === true) {
    for (var h = 1; h < history.length; ++h) {
        if (history[h]._type === "Rewind") {
            lastSiteChange = new Date(history[h].timestamp);
            break;
        }
    }
}
```

### Site Change Reset

When `rewind_resets_autosens` is enabled, autosens resets sensitivity calculations after:
- Pump cartridge rewind (site change indicator)
- Battery change (if `battery_indicates_battery_change` is true)
- Prime event (if `prime_indicates_pump_site_change` is true)

This helps autosens respond quickly to absorption changes after a new infusion site.

## Meal Exclusion

**Source**: `oref0:lib/determine-basal/autosens.js#L122-L165`

Autosens excludes data points affected by carb absorption:

```javascript
// Exclude if meal carbs detected or COB > 0
if (meal.carbs > 0 && mealTime > 0) {
    var hoursAfterMeal = (bgTime - mealTime) / (60 * 60 * 1000);
    if (hoursAfterMeal < 4) {
        // Skip this data point - affected by meal
        continue;
    }
}

// Also exclude UAM (unannounced meal) absorption periods
if (deviation > 0 && uamAbsorption) {
    continue;
}
```

## Deviation Analysis

**Source**: `oref0:lib/determine-basal/autosens.js#L200-L280`

For each valid (non-meal) data point:

```javascript
// Calculate expected BG change from insulin
var bgi = Math.round((-iob.activity * sens * 5) * 100) / 100;

// Calculate deviation (actual vs expected)
var deviation = avgDelta - bgi;

// Track deviation (positive or negative)
deviations.push(deviation);
```

## Sensitivity Ratio Calculation

**Source**: `oref0:lib/determine-basal/autosens.js#L300-L400`

Autosens uses percentile analysis of deviations:

```javascript
// Sort deviations
deviations.sort(function(a, b) { return a - b; });

// Calculate percentiles
var pct20 = percentile(deviations, 0.20);
var pct50 = percentile(deviations, 0.50);  // median
var pct80 = percentile(deviations, 0.80);

// Calculate ratio based on deviation pattern
// Negative deviations (BG falling faster) → more sensitive
// Positive deviations (BG rising faster) → more resistant
```

### Ratio Interpretation

| Deviation Pattern | Meaning | Ratio Effect |
|-------------------|---------|--------------|
| Mostly negative | BG dropping more than expected | ratio < 1 (more sensitive) |
| Balanced | BG matching predictions | ratio ≈ 1 (normal) |
| Mostly positive | BG rising more than expected | ratio > 1 (more resistant) |

## Ratio Constraints

**Source**: `oref0:lib/determine-basal/autosens.js#L380-L400`

```javascript
// Constrain ratio to safe limits
ratio = Math.max(profile.autosens_min, ratio);
ratio = Math.min(profile.autosens_max, ratio);
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `autosens_min` | 0.5 | Minimum sensitivity ratio (2x more sensitive) |
| `autosens_max` | 2.0 | Maximum sensitivity ratio (2x more resistant) |

## How Ratio is Applied

**Source**: `oref0:lib/determine-basal/determine-basal.js#L249-L311`

The sensitivity ratio adjusts three key parameters:

### 1. Basal Rate

```javascript
basal = profile.current_basal * sensitivityRatio;
```

### 2. Insulin Sensitivity Factor (ISF)

```javascript
sens = profile.sens / sensitivityRatio;
```

### 3. Target BG (optional)

When `sensitivity_raises_target` or `resistance_lowers_target` is enabled:

```javascript
if (profile.sensitivity_raises_target && sensitivityRatio < 1) {
    // More sensitive → raise target to avoid lows
    target_bg = round((target_bg - 60) / sensitivityRatio) + 60;
}
if (profile.resistance_lowers_target && sensitivityRatio > 1) {
    // More resistant → lower target to be more aggressive
    target_bg = round((target_bg - 60) / sensitivityRatio) + 60;
}
```

## Temp Target Sensitivity Override

**Source**: `oref0:lib/determine-basal/determine-basal.js#L251-L277`

Temp targets can override autosens with exercise/activity sensitivity:

```javascript
if (high_temptarget_raises_sensitivity && target_bg > normalTarget) {
    // High temp target → calculate sensitivity from target
    var c = halfBasalTarget - normalTarget;  // default 60
    sensitivityRatio = c / (c + target_bg - normalTarget);
    
    // Example: target 160 → ratio = 60/(60+60) = 0.5 (50% basal)
}
```

| Temp Target | Sensitivity Ratio | Basal Effect |
|-------------|-------------------|--------------|
| 100 (normal) | 1.0 | 100% basal |
| 120 | 0.75 | 75% basal |
| 140 | 0.60 | 60% basal |
| 160 | 0.50 | 50% basal |
| 200 | 0.38 | 38% basal |

## Autosens Output

```json
{
  "ratio": 0.9,
  "sensitivityRatio": 0.9
}
```

## Comparison with Other Projects

| Aspect | oref0 Autosens | AAPS Autosens | Loop Retrospective Correction |
|--------|----------------|---------------|------------------------------|
| Window | 24h (or since site change) | 24h | ~30 min |
| Approach | Deviation percentiles | Same (Kotlin port) | Integral error correction |
| Adjusts | Basal, ISF, Target | Same | ISF (via RC effect) |
| Meal Handling | Excludes meal periods | Same | Subtracts carb effects |
| Min/Max | 0.5 - 2.0 | Same | N/A (continuous) |

### Key Difference from Loop

Loop uses **Retrospective Correction (RC)** which is fundamentally different:
- RC continuously adjusts based on recent (30 min) unexplained BG changes
- Autosens analyzes 24h of fasting/between-meal data
- RC is reactive; autosens is more predictive/stable

## AAPS Dynamic ISF

AAPS has an alternative to autosens called **Dynamic ISF** which:
- Uses Total Daily Dose (TDD) to calculate sensitivity
- Adjusts more rapidly than traditional autosens
- Not present in original oref0

## Configuration Options

| Parameter | Default | Description |
|-----------|---------|-------------|
| `autosens_max` | 2.0 | Maximum sensitivity ratio |
| `autosens_min` | 0.5 | Minimum sensitivity ratio |
| `rewind_resets_autosens` | false | Reset autosens on pump rewind |
| `sensitivity_raises_target` | false | Raise target when more sensitive |
| `resistance_lowers_target` | false | Lower target when more resistant |
| `high_temptarget_raises_sensitivity` | false | High TT reduces basal |
| `low_temptarget_lowers_sensitivity` | false | Low TT increases basal |
| `exercise_mode` | false | Enable exercise sensitivity adjustments |
| `half_basal_exercise_target` | 160 | Target at which basal is halved |
