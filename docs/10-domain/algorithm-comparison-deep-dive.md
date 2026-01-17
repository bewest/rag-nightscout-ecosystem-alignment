# Algorithm Prediction Comparison: Cross-System Deep Dive

This document provides a comprehensive comparison of the dosing algorithms used by Loop, oref0 (OpenAPS), AAPS, and Trio. It explains why the same CGM data can produce different dosing recommendations across systems.

---

## Executive Summary

| Aspect | Loop | oref0 | AAPS | Trio |
|--------|------|-------|------|------|
| **Prediction Style** | Single combined curve | 4 separate curves (IOB, COB, UAM, ZT) | 4 curves (oref port) | 4 curves (oref port) |
| **Primary Dosing** | Temp basal only (Loop 3: optional automatic dosing) | Temp basal + SMB | Temp basal + SMB | Temp basal + SMB |
| **Carb Handling** | Dynamic absorption (adapts to reality) | Linear decay with assumed rate | Linear decay (oref port) | Linear decay (oref port) |
| **Sensitivity Adjustment** | Retrospective Correction | Autosens ratio | Autosens or Dynamic ISF (TDD-based) | Autosens + overrides |
| **UAM Support** | No explicit (via RC) | Yes (dedicated curve) | Yes | Yes |
| **Language** | Swift | JavaScript | Kotlin (ported from JS) | Swift calling JS |

**Note on Loop Dosing**: Loop traditionally uses temp basal adjustments only. Loop 3 introduced an optional "Automatic Bolus" dosing strategy that delivers partial boluses instead of extended high temp basals, but this is fundamentally different from oref0's SMB—Loop does not implement the SMB algorithm. See `loop:Loop/Managers/LoopDataManager+Dosing.swift`.

---

## 1. Prediction Methodology

### 1.1 Loop: Single Combined Prediction

Loop computes **four effect timelines** and combines them into a **single prediction curve**.

```
Final Prediction = Current BG + Σ(Insulin Effects) + Σ(Carb Effects) + Σ(RC Effects) + Momentum Blend
```

#### Effect Components

| Effect | Source | Description |
|--------|--------|-------------|
| **Insulin Effects** | `insulinEffects` | Expected BG change from all insulin doses |
| **Carb Effects** | `carbEffects` | Expected BG rise from carb absorption (dynamic) |
| **Retrospective Correction** | `rcEffect` | Adjustment for unexplained discrepancies |
| **Momentum** | `momentumEffects` | Linear extrapolation of recent 15-min trend |

#### Momentum Blending

Loop blends momentum with other effects using linear interpolation:
- At t=0: 100% momentum, 0% other effects
- At t=15min: 0% momentum, 100% other effects

This captures immediate glucose trajectory without letting momentum dominate the entire prediction.

**Source**: `loop:LoopKit/LoopKit/LoopMath.swift#L118-L175`

### 1.2 oref0/AAPS/Trio: Four Separate Predictions

oref0-based systems generate **four independent prediction curves**, each representing a different scenario:

| Curve | Name | Scenario | Purpose |
|-------|------|----------|---------|
| **IOB** | Insulin On Board | Only insulin affects BG | Conservative low estimate |
| **COB** | Carbs On Board | Carbs absorbing at expected rate | Normal meal scenario |
| **UAM** | Unannounced Meal | Unexplained rises continue | Handle unlogged eating |
| **ZT** | Zero Temp | All insulin delivery stops now | Safety floor estimate |

#### IOB Prediction
```javascript
// Deviation decays linearly over 60 minutes
var predDev = ci * (1 - Math.min(1, IOBpredBGs.length / (60/5)));
IOBpredBG = previousBG + predBGI + predDev;
```

#### COB Prediction
```javascript
// Carb impact decays over absorption time
var predCI = Math.max(0, ci * (1 - COBpredBGs.length / Math.max(cid*2, 1)));
COBpredBG = previousBG + predBGI + predCI + remainingCI;
```

#### UAM Prediction
```javascript
// Uses deviation slope for unexplained rises
var predUCIslope = Math.max(0, uci + (UAMpredBGs.length * slopeFromDeviations));
var predUCImax = Math.max(0, uci * (1 - UAMpredBGs.length / (3*60/5)));
UAMpredBG = previousBG + predBGI + Math.min(predUCIslope, predUCImax);
```

#### ZT (Zero Temp) Prediction
```javascript
// What happens if we stop all insulin now
var predZTBGI = round((-iobTick.iobWithZeroTemp.activity * sens * 5), 2);
ZTpredBG = previousBG + predZTBGI;
```

**Source**: `oref0:lib/determine-basal/determine-basal.js#L439-L695`

### 1.3 Key Differences

| Aspect | Loop | oref0/AAPS/Trio |
|--------|------|-----------------|
| **Output** | Single predicted BG trajectory | Four trajectories to compare |
| **Decision Basis** | Minimize prediction excursions | Compare minPredBG across curves |
| **UAM Handling** | Implicitly via Retrospective Correction | Explicitly via UAM curve |
| **Safety Floor** | Uses prediction minimum | Uses ZT curve as safety floor |
| **Transparency** | Effects combined (harder to debug) | Effects separated (easier to understand) |

### 1.4 Minimum Predicted BG Logic (oref0)

oref0 blends predictions based on remaining carbs:

```javascript
if (minCOBPredBG < 999 && minUAMPredBG < 999) {
    // Weight COB vs UAM based on carbs remaining
    minPredBG = fractionCarbsLeft * minCOBPredBG + 
                (1 - fractionCarbsLeft) * minUAMPredBG;
} else if (enableUAM) {
    minPredBG = round(Math.max(minIOBPredBG, minZTUAMPredBG));
}
```

This approach:
- Uses COB curve when carbs remain
- Transitions to UAM curve as carbs deplete
- Never goes below ZT prediction (safety)

---

## 2. Insulin Models and DIA Handling

### 2.1 Insulin Activity Curves

All systems model insulin as an activity curve where:
- **Peak** = time of maximum insulin activity
- **DIA** = Duration of Insulin Action (total effect time)

| Parameter | Loop | oref0/AAPS/Trio | Notes |
|-----------|------|-----------------|-------|
| **DIA Range** | 5-8 hours | 5+ hours | Both require minimum 5 hours |
| **Curve Type** | Exponential | Exponential | Similar mathematical model |
| **Peak Time** | Model-dependent | Model-dependent | Varies by insulin type |

### 2.2 Loop Insulin Models

Loop provides preset exponential models:

| Model | Peak | DIA | Use Case |
|-------|------|-----|----------|
| **rapidActingAdult** | 75 min | 6 hr | Standard rapid insulin |
| **rapidActingChild** | 65 min | 6 hr | Faster absorption (children) |
| **fiasp** | 55 min | 6 hr | Ultra-rapid insulin |
| **lyumjev** | 55 min | 6 hr | Ultra-rapid insulin |
| **afrezza** | 29 min | Variable | Inhaled insulin |

**Source**: `loop:LoopKit/LoopKit/InsulinKit/ExponentialInsulinModelPreset.swift`

### 2.3 oref0/AAPS/Trio Insulin Models

oref0-based systems also use exponential decay:

```javascript
// Activity at time t
var activity = (t / peak) * Math.exp(1 - t / peak);
```

| Model | Peak | insulinDivisor | Notes |
|-------|------|----------------|-------|
| **Rapid Acting** | 75 min | 75 | Standard NovoLog/Humalog |
| **Ultra Rapid** | 55 min | 65 | Fiasp |
| **Lyumjev** | 45 min | 55 | Lyumjev |

### 2.4 DIA Handling Differences

| Aspect | Loop | oref0/AAPS/Trio |
|--------|------|-----------------|
| **User Configurable** | Model preset selection | DIA field + autotune |
| **Minimum DIA** | Built into model | 5 hours enforced |
| **Effect Duration** | Computed from model | `dia` profile field |
| **Autotune** | No | Yes (adjusts DIA) |

**GAP-ALG-001**: Loop's insulin models are preset-based while oref0 allows direct DIA configuration. This can lead to different IOB calculations for the same insulin doses.

### 2.5 Insulin Activity (BGI)

Blood Glucose Impact (BGI) represents the expected 5-minute BG change from insulin:

**Loop**:
```swift
let insulinEffects = annotatedDoses.glucoseEffects(
    insulinModelProvider: insulinModelProvider,
    longestEffectDuration: settings.insulinActivityDuration,
    insulinSensitivityHistory: settings.sensitivity,
    ...
)
```

**oref0**:
```javascript
var bgi = round((-iob_data.activity * sens * 5), 2);
```

Both use:
```
BGI = -1 × insulin_activity × ISF × time_interval
```

---

## 3. Carbohydrate Absorption Models

### 3.1 Loop: Dynamic Piecewise Linear Absorption

Loop's carb model **adapts based on observed glucose behavior**:

1. **Map carbs to counteraction effects** (ICE)
2. **Adjust absorption rate** based on how carbs appear to be absorbing
3. **Compute future effects** using adjusted model

```swift
let carbEffects = input.carbEntries.map(
    to: insulinCounteractionEffects,
    carbRatio: settings.carbRatio,
    insulinSensitivity: settings.sensitivity
).dynamicGlucoseEffects(...)
```

**Key insight**: Loop's absorption rate speeds up or slows down based on real-time observations.

**Source**: `loop:LoopKit/LoopKit/CarbKit/`

### 3.2 oref0: Linear Decay with Assumed Rate

oref0 uses a simpler linear decay model:

```javascript
// Carb impact decays linearly over absorption time
var predCI = Math.max(0, ci * (1 - COBpredBGs.length / Math.max(cid*2, 1)));
```

The absorption rate is assumed based on:
- `carbs_hr` setting (default: 20-30g/hr)
- Observed deviations (can accelerate detection)

### 3.3 Comparison

| Aspect | Loop | oref0/AAPS/Trio |
|--------|------|-----------------|
| **Model Type** | Dynamic piecewise linear | Linear decay |
| **Adaptation** | Real-time based on ICE | Limited (deviation-based) |
| **Absorption Time** | Per-entry (user or default) | Global carbs_hr rate |
| **Fast Carbs** | Handles via dynamic adaptation | Handled via UAM curve |
| **Slow Carbs** | Handles via dynamic adaptation | May underestimate tail |

**GAP-ALG-002**: Loop's dynamic carb model can handle absorption variability better than oref0's linear assumption, but oref0's UAM curve provides a safety net for unannounced or fast-absorbing carbs.

### 3.4 Insulin Counteraction Effects (Loop)

Loop's key innovation is **Insulin Counteraction Effects (ICE)**:

```swift
let insulinCounteractionEffects = input.glucoseHistory.counteractionEffects(to: insulinEffects)
```

**Formula**:
```
ICE = (Actual Glucose Change) - (Expected Insulin Effect)
```

- If glucose rose more than insulin predicted → carbs are absorbing
- If glucose fell more than insulin predicted → something else happening

This allows Loop to infer carb absorption rate from observed data.

---

## 4. Sensitivity Adjustments

### 4.1 Loop: Retrospective Correction (RC)

Loop uses **Retrospective Correction** to handle unexplained glucose behavior:

```swift
let retrospectiveGlucoseDiscrepancies = insulinCounteractionEffects.subtracting(carbEffects)
let rcEffect = rc.computeEffect(
    startingAt: latestGlucose,
    retrospectiveGlucoseDiscrepanciesSummed: retrospectiveGlucoseDiscrepanciesSummed,
    ...
)
```

**RC Input**:
```
RC = ICE - Carb Effects
```

Two implementations:
1. **StandardRetrospectiveCorrection** - Simple proportional effect
2. **IntegralRetrospectiveCorrection** - PID-like with integral/differential terms

**Effect**: RC adjusts predictions for unexplained discrepancies (stress, exercise, illness).

### 4.2 oref0: Autosens Ratio

oref0 uses **Autosens** to detect sensitivity changes over time:

```javascript
if (autosens_data) {
    sensitivityRatio = autosens_data.ratio;  // e.g., 0.8 = 80% sensitivity
}

// Apply to basal and ISF
basal = profile.current_basal * sensitivityRatio;
sens = profile.sens / sensitivityRatio;
```

Autosens looks at 8-24 hours of data to detect patterns:
- Ratio < 1.0 → More insulin resistant
- Ratio > 1.0 → More insulin sensitive

### 4.3 AAPS: Dynamic ISF (TDD-Based)

AAPS offers **Dynamic ISF** based on Total Daily Dose:

```kotlin
// TDD weighting
val tddWeightedFromLast8H = ((1.4 * tddLast4H) + (0.6 * tddLast8to4H)) * 3
val tdd = ((tddWeightedFromLast8H * 0.33) + (tdd7D * 0.34) + (tdd1D * 0.33)) * adjustmentFactor

// Variable sensitivity formula
val variableSensitivity = 1800 / (tdd * ln((glucose / insulinDivisor) + 1))
```

| TDD Component | Weight | Purpose |
|---------------|--------|---------|
| Last 4 hours (weighted) | 33% | Recent trend |
| 7-day average | 34% | Stability |
| Yesterday's total | 33% | Recent pattern |

### 4.4 Trio: Overrides + Autosens

Trio combines oref0 Autosens with **Override system**:

```javascript
if (oref2_variables.useOverride) {
    overrideFactor = oref2_variables.overridePercentage / 100;
    
    if (isfAndCr) {
        sensitivity /= overrideFactor;
        carbRatio /= overrideFactor;
    }
}
```

Overrides can:
- Scale ISF and CR together or separately
- Disable SMB during specific hours
- Set custom targets

### 4.5 Comparison

| Mechanism | Loop | oref0 | AAPS | Trio |
|-----------|------|-------|------|------|
| **Real-time Adjustment** | Retrospective Correction | Via deviation | Via deviation | Via deviation |
| **Historical Pattern** | No | Autosens (8-24h) | Autosens or DynISF | Autosens |
| **TDD-Based** | No | No | Dynamic ISF option | No |
| **User Override** | Override presets | Temp target | Profile switch % | Override profiles |
| **Time of Day** | Via schedules | Via schedules | Via schedules | Via schedules + SMB schedule |

**GAP-ALG-003**: Loop's Retrospective Correction responds faster to acute changes, while Autosens detects longer-term patterns. Neither approach handles both equally well.

---

## 5. Safety Guards

### 5.1 Low Glucose Suspend

All systems implement some form of low glucose protection:

| System | Mechanism | Threshold | Source |
|--------|-----------|-----------|--------|
| **Loop** | Suspend threshold (glucose safety limit) | User-configurable via `suspendThreshold` | `loop:LoopKit/LoopKit/TherapySettings.swift` |
| **oref0** | LGS when minGuardBG < threshold | `min_bg - 10` (derived from target) | `oref0:lib/determine-basal/determine-basal.js#L905` |
| **AAPS** | LGS threshold constraint | `preferences.lgsThreshold` | `aaps:plugins/aps/src/main/kotlin/app/aaps/plugins/aps/openAPSSMB/DetermineBasalSMB.kt` |
| **Trio** | Same as oref0 | `preferences.suspendThreshold` | `trio:trio-oref/lib/determine-basal/determine-basal.js` |

**oref0 LGS Logic**:
```javascript
// Source: oref0:lib/determine-basal/determine-basal.js#L905-L915
if (bg < threshold || minGuardBG < threshold) {
    rT.reason += "minGuardBG " + minGuardBG + "<" + threshold;
    return tempBasalFunctions.setTempBasal(0, durationReq, ...);
}
```

**Loop Suspend Logic**:
Loop suspends insulin delivery when predicted glucose falls below the suspend threshold at any point in the prediction window. The suspend threshold is defined in `TherapySettings.suspendThreshold` and evaluated during prediction-based dosing decisions. See `loop:LoopKit/LoopKit/TherapySettings.swift` for threshold definition and `loop:LoopKit/LoopKit/LoopAlgorithm/LoopAlgorithm.swift` for prediction evaluation.

### 5.2 Maximum IOB Limits

| System | Setting | Effect |
|--------|---------|--------|
| **Loop** | `maximumActiveInsulin` | Limits total IOB |
| **oref0** | `max_iob` | Returns to scheduled basal if exceeded |
| **AAPS** | `preferences.maxIOB` | Constraint checker enforces |
| **Trio** | `preferences.maxIOB` | Same as oref0 |

### 5.3 Maximum Basal Rate

All systems limit temp basal rates:

**oref0/AAPS/Trio**:
```javascript
var maxSafeBasal = Math.min(
    profile.max_basal,
    profile.max_daily_basal * profile.max_daily_safety_multiplier,
    profile.current_basal * profile.current_basal_safety_multiplier
);
```

| Multiplier | Default | Purpose |
|------------|---------|---------|
| `max_daily_safety_multiplier` | 3x | Cap relative to max scheduled basal |
| `current_basal_safety_multiplier` | 4x | Cap relative to current scheduled basal |

**Loop**: Uses `maximumBasalRatePerHour` as hard limit.

### 5.4 SMB Constraints

SMB (Super Micro Bolus) is only available in oref0-based systems:

| Constraint | oref0 | AAPS | Trio |
|------------|-------|------|------|
| **Max SMB size** | `maxSMBBasalMinutes / 60 * current_basal` | Same | Same |
| **UAM SMB limit** | `maxUAMSMBBasalMinutes / 60 * current_basal` | Same | Same |
| **SMB Interval** | 3 minutes default | 3 minutes | 3 minutes |
| **SMB fraction** | 1/2 of insulinReq | Same | Same |

**oref0 SMB Logic**:
```javascript
if (iob_data.iob > mealInsulinReq) {
    // IOB > COB: use maxUAMSMBBasalMinutes (30 min default)
    maxBolus = profile.current_basal * profile.maxUAMSMBBasalMinutes / 60;
} else {
    // Normal: use maxSMBBasalMinutes (75 min default)
    maxBolus = profile.current_basal * profile.maxSMBBasalMinutes / 60;
}

var microBolus = Math.min(insulinReq / 2, maxBolus);
```

### 5.5 SMB Enable Conditions

| Condition | oref0 | AAPS | Trio |
|-----------|-------|------|------|
| **Always** | `enableSMB_always` | Same | Same |
| **With COB** | `enableSMB_with_COB` | Same | Same |
| **After Carbs** | `enableSMB_after_carbs` (6h window) | Same | Same |
| **With Low TT** | `enableSMB_with_temptarget` | Same | Same |
| **High BG** | `enableSMB_high_bg` | Same | Same |
| **Scheduled Off** | No | No | `smbIsScheduledOff` (Trio-specific) |

### 5.6 SMB Disable Conditions

SMB is automatically disabled under these safety conditions:

```javascript
// Source: oref0:lib/determine-basal/determine-basal.js#L100-L126
// Disable SMB if minGuardBG below threshold
if (minGuardBG < threshold) {
    enableSMB = false;
}

// Disable SMB for sudden rises (> 20% of BG in 45 min)
if (maxDelta > 0.2 * bg) {
    enableSMB = false;
}
```

### 5.7 Safety Guard Comparison Matrix

| Safety Feature | Loop | oref0 | AAPS | Trio |
|----------------|------|-------|------|------|
| **Low Glucose Suspend** | Yes (suspend threshold) | Yes (minGuardBG < threshold) | Yes (lgsThreshold) | Yes (suspendThreshold) |
| **Max IOB Enforcement** | Yes (`maximumActiveInsulin`) | Yes (`max_iob`) | Yes (`preferences.maxIOB`) | Yes (`preferences.maxIOB`) |
| **Max Basal Rate** | Yes (`maximumBasalRatePerHour`) | Yes (3 limits: max_basal, daily multiplier, current multiplier) | Yes (same as oref0) | Yes (same as oref0) |
| **Max SMB Size** | N/A (no SMB) | Yes (`maxSMBBasalMinutes` worth of basal) | Yes (same) | Yes (same) |
| **SMB Safety Gating** | N/A | Yes (minGuardBG, maxDelta checks) | Yes (same) | Yes (same + scheduled disable) |
| **Bolus Wizard Warning** | N/A | Yes (A52 risk, bwFound) | Yes | Yes |
| **Sudden Rise Protection** | N/A | Yes (maxDelta > 20% BG) | Yes | Yes |

**Source References**:
- Loop: `loop:LoopKit/LoopKit/TherapySettings.swift`, `loop:Loop/Managers/LoopDataManager.swift`
- oref0: `oref0:lib/determine-basal/determine-basal.js#L51-L126` (SMB enable logic)
- AAPS: `aaps:plugins/aps/src/main/kotlin/app/aaps/plugins/aps/openAPSSMB/DetermineBasalSMB.kt`
- Trio: `trio:trio-oref/lib/determine-basal/determine-basal.js#L47-L142`

---

## 6. Why Same CGM → Different Recommendations

### 6.1 Root Causes

| Factor | Impact | Example |
|--------|--------|---------|
| **Prediction Methodology** | Different safety margins | oref0 uses minPredBG across 4 curves; Loop uses single combined |
| **Carb Absorption Model** | Different COB estimates | Loop adapts dynamically; oref0 assumes linear |
| **Sensitivity Approach** | Different ISF adjustments | AAPS DynISF may see 40 ISF; Loop may see 50 ISF |
| **UAM Handling** | Different unexplained rise response | oref0 has explicit UAM curve; Loop uses RC |
| **SMB Availability** | Different dosing aggressiveness | Loop uses temp basal only; oref0 can SMB |

### 6.2 Scenario Analysis

#### Scenario: Post-Meal Rise with 30g Carbs Logged

| System | Behavior |
|--------|----------|
| **Loop** | Uses dynamic absorption; if rise faster than expected, increases absorption rate estimate |
| **oref0** | COB curve assumes linear decay; if rise faster, UAM curve kicks in |
| **AAPS** | Same as oref0; DynISF may also reduce ISF if BG high |
| **Trio** | Same as oref0; override may scale insulin delivery |

#### Scenario: Unexplained Rise (No Carbs Logged)

| System | Behavior |
|--------|----------|
| **Loop** | RC detects discrepancy, adds positive effect to prediction |
| **oref0** | UAM curve activates, projects continued rise |
| **AAPS** | Same as oref0; may enable SMB if `enableSMB_with_UAM` |
| **Trio** | Same as oref0 |

#### Scenario: Exercise (Sensitivity Increase)

| System | Behavior |
|--------|----------|
| **Loop** | User activates workout override (reduces insulin %) |
| **oref0** | High temp target triggers sensitivity calculation |
| **AAPS** | Autosens may detect if sustained; or user uses profile % |
| **Trio** | Override profile with reduced insulin % |

### 6.3 Quantitative Example

**Given**: BG=150, IOB=2.0, COB=20g, ISF=50, CR=10

**Loop** might calculate:
- Insulin effect: -2.0 × 50 = -100 mg/dL
- Carb effect: +20 × 50/10 = +100 mg/dL
- Net effect: 0, eventual BG ≈ 150
- Action: Scheduled basal

**oref0** might calculate:
- IOB curve eventualBG: 150 - (2.0 × 50) = 50 → needs low temp
- COB curve eventualBG: 150 + carb rise - insulin effect → higher
- minPredBG: Uses weighted blend based on remaining carbs
- Action: Depends on minPredBG vs target

**Key difference**: Loop combines effects; oref0 keeps them separate and uses the most conservative minimum.

---

## 7. Identified Gaps

| Gap ID | Description | Systems Affected | Impact | Source |
|--------|-------------|------------------|--------|--------|
| **GAP-ALG-001** | Insulin model configuration differs (preset vs DIA field) | Loop vs oref0/AAPS/Trio | Different IOB calculations possible | Loop: `ExponentialInsulinModelPreset.swift`; oref0: `profile.dia` |
| **GAP-ALG-002** | Carb absorption model differs (dynamic vs linear) | Loop vs oref0/AAPS/Trio | Different COB and carb effect estimates | Loop: `CarbMath.swift`; oref0: `determine-basal.js#L439+` |
| **GAP-ALG-003** | Sensitivity mechanism differs (RC vs Autosens) | Loop vs oref0/AAPS/Trio | Different response to acute vs chronic changes | Loop: `IntegralRetrospectiveCorrection.swift`; oref0: `autosens.js` |
| **GAP-ALG-004** | Loop has no explicit UAM curve | Loop | May be slower to respond to unannounced meals (relies on RC) | Loop algorithm docs show no UAM equivalent |
| **GAP-ALG-005** | Loop has no SMB algorithm | Loop | Uses temp basal only (Loop 3 auto-bolus is different from SMB) | Loop: `LoopDataManager+Dosing.swift` |
| **GAP-ALG-006** | AAPS DynISF is TDD-based while others are deviation-based | AAPS vs others | May produce different ISF under same conditions | AAPS: `OpenAPSSMBPlugin.kt#calculateRawDynIsf` |
| **GAP-ALG-007** | Trio supports SMB time-window scheduling; others don't | Trio | Can disable SMB during specific hours (overnight, etc.) | Trio: `trio-oref/determine-basal.js#L47-60` (`smbIsScheduledOff`) |
| **GAP-ALG-008** | Prediction transparency differs | All | oref0 outputs 4 curves; Loop outputs 1 combined | devicestatus format differences |

---

## 8. Devicestatus Representation

### 8.1 Loop Predictions in Nightscout

```json
{
  "loop": {
    "predicted": {
      "startDate": "2026-01-17T12:00:00Z",
      "values": [120, 118, 115, 112, 110, ...]
    },
    "iob": { "iob": 2.5 },
    "cob": { "cob": 20 }
  }
}
```

**Missing**: Individual effect timelines (insulin, carbs, RC, momentum).

### 8.2 oref0/AAPS/Trio Predictions in Nightscout

```json
{
  "openaps": {
    "suggested": {
      "predBGs": {
        "IOB": [120, 115, 110, ...],
        "COB": [120, 125, 128, ...],
        "UAM": [120, 118, 116, ...],
        "ZT": [120, 115, 110, ...]
      },
      "eventualBG": 120,
      "sensitivityRatio": 1.0,
      "reason": "COB: 20g; Dev: -15; BGI: -2.5; ..."
    }
  }
}
```

**Advantage**: All four prediction curves visible for debugging.

### 8.3 Recommendation

For algorithm interoperability, a unified prediction format could include:

```json
{
  "predictions": {
    "combined": [120, 118, 115, ...],
    "iob_only": [120, 115, 110, ...],
    "cob_included": [120, 125, 128, ...],
    "uam": [120, 118, 116, ...],
    "zero_temp": [120, 115, 110, ...]
  },
  "effects": {
    "insulin": [...],
    "carbs": [...],
    "sensitivity_adjustment": [...],
    "momentum": [...]
  }
}
```

---

## 9. Key Constants Reference

### 9.1 Loop Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `retrospectiveCorrectionGroupingInterval` | 30 min | Window for aggregating discrepancies |
| `retrospectiveCorrectionEffectDuration` | 60 min | How long RC effect lasts |
| `momentumDataInterval` | 15 min | Glucose history for momentum |
| `momentumDuration` | 15 min | How far momentum projects |
| `defaultDelta` | 5 min | Time step for effect timelines |
| `maximumAbsorptionTimeInterval` | 10 hr | Maximum carb absorption window |

### 9.2 oref0 Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `SMBInterval` | 3 min | Minimum time between SMBs |
| `maxSMBBasalMinutes` | 75 min | Max SMB as minutes of basal |
| `maxUAMSMBBasalMinutes` | 30 min | Max SMB when IOB > COB |
| `maxCOB` | 120g | Maximum tracked COB |
| `remainingCarbsCap` | 90g | Cap on remaining carbs calculation |
| Deviation decay | 60 min | Time for deviation to decay to 0 |
| UAM decay | 3 hr | Time for UAM effect to decay |

---

## 10. Cross-References

- [Loop Prediction Algorithm](../../mapping/loop/algorithm.md) - Detailed Loop algorithm analysis
- [oref0 Algorithm](../../mapping/oref0/algorithm.md) - Detailed oref0 algorithm analysis
- [AAPS OpenAPSSMB](../../mapping/aaps/algorithm.md) - AAPS algorithm implementation
- [Trio Algorithm Flow](../../mapping/trio/algorithm.md) - Trio's JS bridge and execution
- [Terminology Matrix - Algorithm Concepts](../../mapping/cross-project/terminology-matrix.md#algorithmcontroller-concepts) - Term translations
- [Profile/Therapy Settings Comparison](../60-research/profile-therapy-settings-comparison.md) - Cross-system profile analysis

---

## 11. Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Initial comprehensive algorithm comparison |

