# oref0 Insulin Math (IOB Calculation)

This document describes how oref0 calculates Insulin on Board (IOB) and insulin activity.

## Overview

oref0 calculates IOB by summing the remaining insulin from all treatments (boluses and temp basals) over the Duration of Insulin Action (DIA). It supports two mathematical models:

1. **Bilinear** - Legacy triangular curve (simple, less accurate)
2. **Exponential** - Realistic curve based on pharmacokinetic studies (recommended)

## Key Source Files

| File | Purpose |
|------|---------|
| `oref0:lib/iob/calculate.js` | Core IOB calculation (both curves) |
| `oref0:lib/iob/total.js` | Aggregates IOB across all treatments |
| `oref0:lib/iob/history.js` | Processes pump history into treatments |

## IOB Calculation Overview

**Source**: `oref0:lib/iob/calculate.js#L3-L7`

```javascript
function iobCalc(treatment, time, curve, dia, peak, profile) {
    // Returns two variables:
    //   activityContrib = units of treatment.insulin used in previous minute
    //   iobContrib = units of treatment.insulin still remaining at a given point in time
```

For each insulin treatment (bolus or temp basal increment):
1. Calculate minutes since delivery
2. Apply curve formula to get remaining IOB and current activity
3. Sum across all treatments within DIA window

## Bilinear Curve

The bilinear model uses a triangular insulin action curve that peaks at 75 minutes and ends at 180 minutes, scaled by DIA.

**Source**: `oref0:lib/iob/calculate.js#L36-L80`

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `default_dia` | 3.0 hours | Reference DIA for scaling |
| `peak` | 75 minutes | Time to peak activity |
| `end` | 180 minutes | Duration of action |

### Formula

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

### Curve Shape

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

## Exponential Curve

The exponential model provides a more realistic insulin activity curve based on pharmacokinetic studies. **This curve was sourced from Loop.**

**Source**: `oref0:lib/iob/calculate.js#L83-L143`

### Loop Origin

```javascript
// oref0:lib/iob/calculate.js#L125-L128
// Formula source: https://github.com/LoopKit/Loop/issues/388#issuecomment-317938473
// Mapping of original source variable names to those used here:
//   td = end
//   tp = peak
//   t  = minsAgo
```

This is significant: **oref0 and Loop use the same exponential insulin model**, enabling direct cross-project comparison.

### Insulin Types

| Curve Type | Default Peak | Peak Range | Use Case |
|------------|--------------|------------|----------|
| `rapid-acting` | 75 min | 50-120 min | Novolog, Novorapid, Humalog, Apidra |
| `ultra-rapid` | 55 min | 35-100 min | Fiasp, Lyumjev |

**Source**: `oref0:lib/iob/calculate.js#L86-L116`

```javascript
if (profile.curve === "rapid-acting") {
    if (profile.useCustomPeakTime && profile.insulinPeakTime) {
        peak = Math.max(50, Math.min(120, profile.insulinPeakTime));
    } else {
        peak = 75;
    }
} else if (profile.curve === "ultra-rapid") {
    if (profile.useCustomPeakTime && profile.insulinPeakTime) {
        peak = Math.max(35, Math.min(100, profile.insulinPeakTime));
    } else {
        peak = 55;
    }
}
```

### Formula

**Source**: `oref0:lib/iob/calculate.js#L130-L136`

```javascript
var end = dia * 60;  // DIA in minutes

// Time constant of exponential decay
var tau = peak * (1 - peak / end) / (1 - 2 * peak / end);

// Rise time factor
var a = 2 * tau / end;

// Auxiliary scale factor
var S = 1 / (1 - a + (1 + a) * Math.exp(-end / tau));

// Insulin activity at time t
activityContrib = insulin * (S / Math.pow(tau, 2)) * minsAgo * 
                  (1 - minsAgo / end) * Math.exp(-minsAgo / tau);

// Remaining IOB at time t
iobContrib = insulin * (1 - S * (1 - a) * 
             ((Math.pow(minsAgo, 2) / (tau * end * (1 - a)) - 
               minsAgo / tau - 1) * Math.exp(-minsAgo / tau) + 1));
```

### Curve Shape

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

## DIA Constraints

**Source**: `oref0:lib/iob/total.js#L24-L27`, `L60-L63`

```javascript
// Force minimum DIA of 3h
if (dia < 3) {
    dia = 3;
}

// Force minimum of 5h DIA for exponential curves
if (defaults.requireLongDia && dia < 5) {
    dia = 5;
}
```

| Curve | Minimum DIA |
|-------|-------------|
| Bilinear | 3 hours |
| Exponential | 5 hours |

## IOB Aggregation

**Source**: `oref0:lib/iob/total.js#L67-L92`

The total IOB sums contributions from all treatments within the DIA window:

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

### IOB Components

| Component | Description |
|-----------|-------------|
| `iob` | Total IOB (basaliob + bolusiob) |
| `basaliob` | IOB from temp basals (can be negative if running low) |
| `bolusiob` | IOB from boluses |
| `activity` | Current insulin activity (for BGI calculation) |
| `netbasalinsulin` | Net deviation from scheduled basal |
| `bolusinsulin` | Total bolus insulin |

## Blood Glucose Impact (BGI)

BGI is the expected BG change from insulin activity over 5 minutes:

**Source**: `oref0:lib/determine-basal/determine-basal.js#L398`

```javascript
var bgi = round((-iob_data.activity * sens * 5), 2);
```

Where:
- `activity` = current insulin activity (units/min)
- `sens` = insulin sensitivity factor (mg/dL per unit)
- `5` = 5-minute interval

**Example**: If activity = 0.02 U/min and sens = 50 mg/dL/U:
- BGI = -0.02 * 50 * 5 = -5 mg/dL (BG expected to drop 5 mg/dL in 5 min)

## Curve Comparison with Other Projects

| Project | Curve Options | Default Peak | Formula Source |
|---------|---------------|--------------|----------------|
| oref0 | bilinear, rapid-acting, ultra-rapid | 75 min | Loop (exponential) |
| AAPS | Same (Kotlin port) | 75 min | oref0 |
| Loop | Exponential only | 75 min | Original |
| Trio | Same as oref0 | 75 min | oref0 |

## iobWithZeroTemp

For safety predictions, oref0 calculates what IOB would be if temp basals were set to zero from now on:

**Source**: `oref0:lib/iob/history.js` (calculation), used in `ZTpredBG`

```json
{
  "iob": -0.106,
  "activity": 0.0002,
  "iobWithZeroTemp": {
    "iob": -0.207,
    "activity": 0
  }
}
```

This enables the ZT (Zero Temp) prediction curve which answers "what will BG do if we stop all insulin now?"
