# Trio-dev oref Integration Mapping

> **Cycle**: 71  
> **Date**: 2026-01-31  
> **Status**: Complete  
> **Backlog Item**: aid-algorithms.md #5 / ECOSYSTEM-BACKLOG Ready Queue #2

## Executive Summary

Trio maintains a fork of oref0 in `trio-oref/lib/` that is a **superset** of upstream oref0. The structure is identical (same files), but Trio adds significant enhancements for dynamic ISF, profile overrides, SMB scheduling, and TDD-based adjustments.

**Key Finding**: Trio has **+451 lines (+37.8%)** in `determine-basal.js` alone, primarily for dynamic ISF and override features. No oref0 functionality is removed.

---

## File Structure Comparison

### Perfect Structural Parity

Both codebases have identical file structure:

```
lib/
├── autotune/
│   └── index.js
├── autotune-prep/
│   ├── categorize.js
│   ├── dosed.js
│   └── index.js
├── determine-basal/
│   ├── autosens.js
│   ├── cob.js
│   └── determine-basal.js
├── iob/
│   ├── calculate.js
│   ├── history.js
│   ├── index.js
│   └── total.js
├── meal/
│   ├── history.js
│   ├── index.js
│   └── total.js
├── profile/
│   ├── basal.js
│   ├── carbs.js
│   ├── index.js
│   ├── isf.js
│   └── targets.js
├── basal-set-temp.js
├── bolus.js
├── calc-glucose-stats.js
├── glucose-get-last.js
├── glucose-stats.js
├── medtronic-clock.js
├── percentile.js
├── pump.js
├── require-utils.js
├── round-basal.js
├── temps.js
└── with-raw-glucose.js
```

---

## Content Divergence Analysis

### determine-basal.js (Core Algorithm)

| Metric | oref0 | Trio | Difference |
|--------|-------|------|------------|
| **Lines** | 1,192 | 1,643 | +451 (+37.8%) |
| **Function Parameters** | 10 | 14 | +4 new params |
| **Trio-specific lines** | 0 | ~500 | +500 |

#### Function Signature Changes

**oref0:**
```javascript
var determine_basal = function determine_basal(
    glucose_status, currenttemp, iob_data, profile, 
    autosens_data, meal_data, tempBasalFunctions, 
    microBolusAllowed, reservoir_data, currentTime
)
```

**Trio:**
```javascript
var determine_basal = function determine_basal(
    glucose_status, currenttemp, iob_data, profile, 
    autosens_data, meal_data, tempBasalFunctions, 
    microBolusAllowed, reservoir_data, currentTime,
    pumphistory, preferences, basalprofile, 
    trio_custom_variables, middleWare  // <-- NEW
)
```

#### Trio-Specific Features

| Feature | Lines | Description |
|---------|-------|-------------|
| **Dynamic ISF** | 200-362 | Logarithmic and sigmoid formulas |
| **Profile Overrides** | 144-186 | Target, ISF, CR, SMB minutes |
| **SMB Scheduling** | 48-70 | Time-windowed SMB disabling |
| **TDD Adjustments** | 212-231 | Weighted 14-day averages |
| **Override Factor** | 177-186 | Percentage-based adjustments |

#### trio_custom_variables Object

```javascript
trio_custom_variables = {
    // Override settings
    useOverride: boolean,
    overrideTarget: number,        // mg/dL
    overridePercentage: number,    // 100 = no change
    
    // SMB scheduling
    smbIsOff: boolean,
    smbIsScheduledOff: boolean,
    start: string,                 // "HH:MM"
    end: string,                   // "HH:MM"
    
    // Advanced settings
    advancedSettings: boolean,
    isfAndCr: boolean,
    isf: number,
    cr: number,
    smbMinutes: number,
    uamMinutes: number,
    
    // TDD data
    currentTDD: number,
    weightedAverage: number,
    average_total_data: number
}
```

---

### autosens.js

| Metric | oref0 | Trio | Difference |
|--------|-------|------|------------|
| **Lines** | 455 | 452 | -3 (-0.7%) |

**Key Addition**: ISF lookup caching with `lastIsfResult` variable

```javascript
// Trio optimization (lines 148-153)
let lastIsfResult;
// ... later ...
const [isfValue, isfReason] = isfLookup(profile, glucose, timestamp);
lastIsfResult = { isfValue, isfReason };
```

---

### cob.js (Carbs on Board)

| Metric | oref0 | Trio | Difference |
|--------|-------|------|------------|
| **Lines** | 212 | 207 | -5 (-2.4%) |

**Key Changes**:
1. Same ISF caching as autosens.js
2. Dynamic meal absorption time:

```javascript
// oref0 (line 57)
var mealWindow = 6;  // hardcoded 6 hours

// Trio (line 57)
var mealWindow = profile.maxMealAbsorptionTime;  // configurable
```

---

### iob/calculate.js

| Metric | oref0 | Trio | Difference |
|--------|-------|------|------------|
| **Lines** | 147 | 145 | -2 (-1.4%) |

**Differences**: Minimal - oref0 adds `'use strict';` directive. Functionally identical.

---

## Trio-Specific Enhancements Summary

### 1. Dynamic ISF (Insulin Sensitivity Factor)

Trio implements two dynamic ISF formulas:

**Logarithmic:**
```javascript
// lines 283-320
var dynISF = Math.log10(bg / ins_val) * 1800 / (tdd * ln_multiplier);
```

**Sigmoid:**
```javascript
// lines 322-365
var dynISF = adjustmentFactor / (1 + Math.exp(-0.01 * (bg - 120))) * sens;
```

### 2. Profile Overrides

```javascript
// lines 144-186
if (trio_custom_variables.useOverride) {
    overrideFactor = trio_custom_variables.overridePercentage / 100;
    if (overrideTarget != 0 && !profile.temptargetSet) {
        target_bg = overrideTarget;
    }
}
```

### 3. SMB Scheduling

```javascript
// lines 48-70
if (trio_custom_variables.smbIsScheduledOff) {
    let startTime = trio_custom_variables.start;
    let endTime = trio_custom_variables.end;
    // ... check if current time is in scheduled-off window
}
```

### 4. TDD-Based Adjustments

```javascript
// lines 212-231
let tdd = trio_custom_variables.currentTDD;
const weightedAverage = trio_custom_variables.weightedAverage;
// ... calculate basal/ISF ratios based on TDD
```

---

## Backward Compatibility

| Aspect | Status | Notes |
|--------|--------|-------|
| File structure | ✅ Identical | Same files in same locations |
| Function signatures | ⚠️ Extended | Extra params with defaults |
| Core oref0 logic | ✅ Preserved | No removals |
| Profile format | ✅ Compatible | Extensions are additive |
| Output format | ✅ Compatible | Same `reason` object structure |

**Conclusion**: Trio's oref fork is **fully backward-compatible** with upstream oref0. The changes are additive.

---

## Sync Considerations

### Trio → oref0 Backport Feasibility

| Feature | Backportable | Effort |
|---------|--------------|--------|
| Dynamic ISF | ⚠️ Maybe | High - requires preferences |
| SMB Scheduling | ⚠️ Maybe | Medium - needs UI |
| TDD Adjustments | ⚠️ Maybe | Medium - needs history |
| ISF Caching | ✅ Yes | Low - pure optimization |
| Meal Absorption | ✅ Yes | Low - profile field |

### oref0 → Trio Sync

Trio should periodically merge upstream oref0 changes, particularly:
- Bug fixes in core logic
- Insulin curve updates
- Safety constraint changes

---

## Gap Analysis

| ID | Gap | Impact |
|----|-----|--------|
| GAP-OREF-001 | Trio's trio_custom_variables not documented | Hard to understand integration |
| GAP-OREF-002 | Dynamic ISF formulas not in upstream oref0 | Feature disparity |
| GAP-OREF-003 | No automated sync between Trio and oref0 | Manual merge required |

---

## Requirements

| ID | Requirement |
|----|-------------|
| REQ-OREF-001 | Trio SHOULD document trio_custom_variables interface |
| REQ-OREF-002 | Trio SHOULD track upstream oref0 version |
| REQ-OREF-003 | Breaking oref0 changes MUST be evaluated before merge |

---

## Source Files Analyzed

### Trio
- `externals/Trio/trio-oref/lib/determine-basal/determine-basal.js` (1,643 lines)
- `externals/Trio/trio-oref/lib/determine-basal/autosens.js` (452 lines)
- `externals/Trio/trio-oref/lib/determine-basal/cob.js` (207 lines)
- `externals/Trio/trio-oref/lib/iob/calculate.js` (145 lines)

### oref0
- `externals/oref0/lib/determine-basal/determine-basal.js` (1,192 lines)
- `externals/oref0/lib/determine-basal/autosens.js` (455 lines)
- `externals/oref0/lib/determine-basal/cob.js` (212 lines)
- `externals/oref0/lib/iob/calculate.js` (147 lines)

---

## Conclusion

Trio's `trio-oref` is a **well-maintained superset** of oref0 with significant enhancements:

1. **+451 lines** in determine-basal.js (37.8% larger)
2. **Dynamic ISF** with logarithmic and sigmoid formulas
3. **Profile overrides** with scheduling
4. **TDD-based adjustments** for personalization
5. **Full backward compatibility** with oref0

The primary challenge is **keeping Trio synced with upstream oref0** bug fixes while maintaining Trio-specific features.
